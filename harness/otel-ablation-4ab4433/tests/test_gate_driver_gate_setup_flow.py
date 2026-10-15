import pytest

from obsplacement.gate_driver.errors import ConcurrentRunError, PathAlreadyExists
from obsplacement.gate_driver.fs_guards import SingleFlightLock
from obsplacement.gate_driver.gate_paths import GatePaths
from obsplacement.gate_driver.gate_setup_flow import cmd_install, cmd_prepare, cmd_readiness, cmd_record_plan
from obsplacement.gate_driver.json_io import read_json
from obsplacement.gate_driver.module_loader import load_binding_keys
from obsplacement.gate_driver.sentence import SentenceMismatch

from gate_driver_fakes import FakeAdapter, FakeGatePlanRejected, FakeTransport, make_config

FRAMEWORK_COMMIT = "e29e6664e3647e17646c979100964f317ac51551"


def wire(tmp_path):
    config = make_config(tmp_path)
    paths = GatePaths(config.gates_dir)
    adapter = FakeAdapter()
    transport = FakeTransport()
    return config, paths, adapter, transport


def test_prepare_writes_target_proof_and_bundle_and_returns_sentence(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    result = cmd_prepare(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT)
    assert paths.target_proof.is_file()
    assert paths.release_bundle.is_file()
    assert paths.release_manifest.is_file()
    assert result.gate_plan_sentence == adapter.expected_gate_plan_text(result.bindings)


def test_prepare_is_idempotent_before_any_approval(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    cmd_prepare(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT)
    cmd_prepare(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT)  # must not raise


def test_record_plan_fails_closed_on_sentence_mismatch(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    cmd_prepare(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT)
    with pytest.raises(SentenceMismatch):
        cmd_record_plan(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT, typed="not it")
    assert not paths.gate_plan.exists()  # nothing recorded on a failed verification


def test_record_plan_writes_gate_plan_and_setup_authorization(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    prepared = cmd_prepare(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT)
    result = cmd_record_plan(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT,
                              typed=prepared.gate_plan_sentence)
    gate_plan = read_json(paths.gate_plan)
    assert gate_plan["approvedBy"] == config.approved_by
    assert gate_plan["typedApproval"] == prepared.gate_plan_sentence
    assert gate_plan["runtimeAuthorized"] is False
    assert gate_plan["promotionAuthorized"] is False
    setup_authorization = read_json(paths.setup_authorization)
    assert setup_authorization["setupId"] == result.setup_id
    assert setup_authorization["experimentalCellsAuthorized"] == 0


def test_record_plan_refuses_to_overwrite_a_prior_gate_plan(tmp_path):
    """Non-negotiable property #5, at the point that actually matters: a
    second record-plan run (e.g. an accidental re-invocation) must not
    silently replace an already-recorded GATE-PLAN approval."""
    config, paths, adapter, transport = wire(tmp_path)
    prepared = cmd_prepare(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT)
    cmd_record_plan(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT,
                     typed=prepared.gate_plan_sentence)
    with pytest.raises(PathAlreadyExists):
        cmd_record_plan(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT,
                         typed=prepared.gate_plan_sentence)


def test_install_fails_closed_on_sentence_mismatch_and_never_calls_transport(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    prepared = cmd_prepare(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT)
    cmd_record_plan(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT,
                     typed=prepared.gate_plan_sentence)
    with pytest.raises(SentenceMismatch):
        cmd_install(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                     typed="wrong sentence", trace_path=tmp_path / "install-trace.log")
    assert transport.calls == []  # no subprocess/remote call happened
    assert not paths.gate_setup.exists()


def test_install_writes_gate_setup_and_receipt_and_traces_the_mutation(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    prepared = cmd_prepare(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT)
    plan_result = cmd_record_plan(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT,
                                   typed=prepared.gate_plan_sentence)
    trace_path = tmp_path / "install-trace.log"
    receipt = cmd_install(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                           typed=plan_result.gate_setup_sentence, trace_path=trace_path)
    assert receipt["releaseRoot"] == "/releases/fake"
    assert read_json(paths.install_receipt) == receipt
    assert read_json(paths.gate_setup)["gate"] == "GATE-SETUP"
    assert trace_path.is_file()
    assert len(transport.calls) == 1  # exactly the traced setup() call


def test_install_refuses_to_overwrite_a_prior_gate_setup(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    prepared = cmd_prepare(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT)
    plan_result = cmd_record_plan(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT,
                                   typed=prepared.gate_plan_sentence)
    cmd_install(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                typed=plan_result.gate_setup_sentence, trace_path=tmp_path / "t1.log")
    with pytest.raises(PathAlreadyExists):
        cmd_install(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                    typed=plan_result.gate_setup_sentence, trace_path=tmp_path / "t2.log")


def test_readiness_sources_binding_keys_from_the_loaded_installer_and_refuses_stale_fetch(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    prepared = cmd_prepare(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT)
    plan_result = cmd_record_plan(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT,
                                   typed=prepared.gate_plan_sentence)
    cmd_install(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                typed=plan_result.gate_setup_sentence, trace_path=tmp_path / "install.log")

    installer_dir = config.root / "modules/fake-sut/execution"
    installer_dir.mkdir(parents=True, exist_ok=True)
    (installer_dir / "candidate_release_installer.py").write_text(
        "RELEASE_BINDING_KEYS = ('bindingKeyA', 'bindingKeyB')\n"
    )
    binding_keys = load_binding_keys(config.root, config.installer_module)

    admission = cmd_readiness(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                               binding_keys=binding_keys, trace_path=tmp_path / "readiness.log")
    assert admission["readinessCanonicalSha256"] == "fakereadinesssha"
    assert paths.fetched_readiness_document.is_file()

    # Property #5: a second readiness capture must not silently merge into
    # a prior fetch -- gate_setup.py's own guard, generalized.
    with pytest.raises(PathAlreadyExists):
        cmd_readiness(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                       binding_keys=binding_keys, trace_path=tmp_path / "readiness-2.log")


def _prepared_and_planned(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    prepared = cmd_prepare(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT)
    plan_result = cmd_record_plan(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT,
                                   typed=prepared.gate_plan_sentence)
    return config, paths, adapter, transport, plan_result


def test_install_rejects_a_corrupted_gate_plan(tmp_path):
    """Section 2.3: `cmd_install` must re-validate the recorded gate-plan.json
    against currently-installed bindings, not merely trust that it once
    passed `cmd_record_plan`."""
    config, paths, adapter, transport, plan_result = _prepared_and_planned(tmp_path)
    adapter.reject_gate_plan_reason = "corrupted shape"
    with pytest.raises(FakeGatePlanRejected):
        cmd_install(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                    typed=plan_result.gate_setup_sentence, trace_path=tmp_path / "install.log")
    assert transport.calls == []
    assert not paths.gate_setup.exists()


def test_readiness_rejects_a_corrupted_gate_plan(tmp_path):
    config, paths, adapter, transport, plan_result = _prepared_and_planned(tmp_path)
    cmd_install(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                typed=plan_result.gate_setup_sentence, trace_path=tmp_path / "install.log")
    installer_dir = config.root / "modules/fake-sut/execution"
    installer_dir.mkdir(parents=True, exist_ok=True)
    (installer_dir / "candidate_release_installer.py").write_text(
        "RELEASE_BINDING_KEYS = ('bindingKeyA', 'bindingKeyB')\n"
    )
    binding_keys = load_binding_keys(config.root, config.installer_module)

    adapter.reject_gate_plan_reason = "corrupted shape"
    with pytest.raises(FakeGatePlanRejected):
        cmd_readiness(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                       binding_keys=binding_keys, trace_path=tmp_path / "readiness.log")
    assert not paths.fetched_readiness_document.exists()


def test_install_refuses_a_second_concurrent_attempt(tmp_path):
    """`cmd_install` now runs under `paths.auto_lock`, the same lock
    `campaign_setup_flow.cmd_auto` holds for its own install step."""
    config, paths, adapter, transport, plan_result = _prepared_and_planned(tmp_path)
    paths.gates_dir.mkdir(parents=True, exist_ok=True)
    with SingleFlightLock(paths.auto_lock):
        with pytest.raises(ConcurrentRunError):
            cmd_install(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                        typed=plan_result.gate_setup_sentence, trace_path=tmp_path / "install.log")
    assert not paths.gate_setup.exists()


def test_readiness_refuses_a_second_concurrent_attempt(tmp_path):
    config, paths, adapter, transport, plan_result = _prepared_and_planned(tmp_path)
    cmd_install(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                typed=plan_result.gate_setup_sentence, trace_path=tmp_path / "install.log")
    installer_dir = config.root / "modules/fake-sut/execution"
    installer_dir.mkdir(parents=True, exist_ok=True)
    (installer_dir / "candidate_release_installer.py").write_text(
        "RELEASE_BINDING_KEYS = ('bindingKeyA', 'bindingKeyB')\n"
    )
    binding_keys = load_binding_keys(config.root, config.installer_module)

    with SingleFlightLock(paths.auto_lock):
        with pytest.raises(ConcurrentRunError):
            cmd_readiness(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                           binding_keys=binding_keys, trace_path=tmp_path / "readiness.log")
