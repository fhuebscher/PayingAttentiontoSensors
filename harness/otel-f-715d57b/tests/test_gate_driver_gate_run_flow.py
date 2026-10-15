import json
from datetime import timedelta

import pytest

from obsplacement.gate_driver.errors import (
    ConcurrentRunError,
    GateDriverError,
    MissingDerivationReceipt,
    PathAlreadyExists,
    PreflightExpired,
    RunAuthorizationDrift,
)
from obsplacement.gate_driver.freshness import PREFLIGHT_MAX_AGE_SECONDS, now, stamp
from obsplacement.gate_driver.fs_guards import SingleFlightLock
from obsplacement.gate_driver.gate_paths import GatePaths
from obsplacement.gate_driver.gate_run_flow import (
    RefreshFailed,
    cmd_execute,
    cmd_refresh,
    derive_run_authorization,
    run_dry_run,
)
from obsplacement.gate_driver.gate_setup_flow import cmd_install, cmd_prepare, cmd_readiness, cmd_record_plan
from obsplacement.gate_driver.json_io import read_json, write_json
from obsplacement.gate_driver.module_loader import load_binding_keys
from obsplacement.gate_driver.sentence import SentenceMismatch

from gate_driver_fakes import FakeAdapter, FakeGatePlanRejected, FakeTransport, make_config

FRAMEWORK_COMMIT = "e29e6664e3647e17646c979100964f317ac51551"


def bootstrap_through_readiness(tmp_path):
    """Drive gate_setup_flow up through a fetched readiness -- the
    precondition every gate_run_flow function assumes, exactly like the real
    GATE-RUN driver assumes gate_setup.py has already run."""
    config = make_config(tmp_path)
    paths = GatePaths(config.gates_dir)
    adapter = FakeAdapter()
    transport = FakeTransport()

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
    cmd_readiness(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                   binding_keys=binding_keys, trace_path=tmp_path / "readiness.log")
    return config, paths, adapter, transport


def test_derive_run_authorization_writes_run_authorization_and_sentence(tmp_path):
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    derivation = derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    assert paths.run_authorization.is_file()
    assert derivation.sentence == adapter.expected_gate_run_text(derivation.authorization)
    assert read_json(paths.run_authorization) == derivation.authorization


def test_derive_run_authorization_is_regenerable_across_refreshes(tmp_path):
    """Unlike gate-plan/gate-setup/gate-run, run-authorization.json must be
    freely regenerable -- refreshing the preflight repeatedly, right up
    until a typed GATE-RUN sentence is verified, is the whole point of the
    oneshot route (non-negotiable property #3)."""
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    first = derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    second = derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)  # must not raise
    assert read_json(paths.run_authorization) == second.authorization


def test_cmd_refresh_fails_closed_when_the_injected_refresh_reports_failure(tmp_path):
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    with pytest.raises(RefreshFailed):
        cmd_refresh(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT,
                    refresh_readiness=lambda: 1)


def test_cmd_refresh_fails_closed_when_gate_plan_goes_missing_after_refresh(tmp_path):
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    paths.gate_plan.unlink()
    with pytest.raises(RefreshFailed):
        cmd_refresh(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT,
                    refresh_readiness=lambda: 0)


def test_cmd_refresh_derives_run_authorization_on_success(tmp_path):
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    derivation = cmd_refresh(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT,
                              refresh_readiness=lambda: 0)
    assert paths.run_authorization.is_file()
    assert derivation.sentence


def test_dry_run_ok_when_everything_the_remote_would_check_passes(tmp_path):
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    result = run_dry_run(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                          scratch_dir=tmp_path / "dryrun")
    assert result.ok is True
    assert result.reasons == ()
    assert result.remote_input is not None


def test_dry_run_never_writes_to_the_real_gates_directory(tmp_path):
    """Property #4: the dry-run probe document must never land where a real
    GATE-RUN document would (paths.gate_run), and its approver must be
    unmistakably not a human."""
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    scratch = tmp_path / "dryrun"
    run_dry_run(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT, scratch_dir=scratch)
    assert not paths.gate_run.exists()
    probe = read_json(scratch / "gate-run.probe.json")
    assert probe["approvedBy"] == "DRY-RUN PLUMBING PROBE - NOT A HUMAN APPROVAL"


def test_dry_run_fails_when_remote_output_path_already_exists(tmp_path):
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    transport._remote_output_exists = True
    derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    result = run_dry_run(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                          scratch_dir=tmp_path / "dryrun")
    assert result.ok is False
    assert any("remote output path already exists" in reason for reason in result.reasons)


def test_dry_run_fails_when_remote_precheck_rejects_the_package(tmp_path):
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    transport._precheck_ok = False
    transport._precheck_detail = "installed validators reject this package"
    derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    result = run_dry_run(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                          scratch_dir=tmp_path / "dryrun")
    assert result.ok is False
    assert any("installed validators reject" in reason for reason in result.reasons)


def test_dry_run_accumulates_multiple_failure_reasons_at_once(tmp_path):
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    transport._remote_output_exists = True
    transport._precheck_ok = False
    derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    result = run_dry_run(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                          scratch_dir=tmp_path / "dryrun")
    assert result.ok is False
    assert len(result.reasons) >= 2


def test_execute_fails_closed_on_sentence_mismatch_before_any_launch(tmp_path):
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    calls_before = list(transport.calls)  # bootstrap already exercised install/readiness
    with pytest.raises(SentenceMismatch):
        cmd_execute(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                    typed="not the sentence", trace_path=tmp_path / "campaign-trace.log")
    assert not paths.gate_run.exists()
    assert transport.calls == calls_before  # no NEW (launch) call happened


def test_execute_launches_exactly_once_and_refuses_a_second_launch(tmp_path):
    """The one-shot guarantee: a second cmd_execute against the same
    run-authorization (i.e. no fresh refresh happened) must fail closed
    rather than launch the campaign twice."""
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    derivation = derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    result = cmd_execute(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                          typed=derivation.sentence, trace_path=tmp_path / "campaign-trace.log")
    assert result["state"] == "running"
    assert paths.gate_run.is_file()
    assert paths.runtime_package.is_file()
    assert paths.campaign_terminal.is_file()

    with pytest.raises(PathAlreadyExists):
        cmd_execute(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                    typed=derivation.sentence, trace_path=tmp_path / "campaign-trace-2.log")


def test_derive_run_authorization_writes_a_derivation_receipt(tmp_path):
    """Section 2.2: the receipt is what `cmd_execute` re-checks against --
    it must exist and carry the fields `cmd_execute` depends on, independent
    of whatever keys the adapter's own `run_authorization` document has."""
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    receipt = read_json(paths.run_authorization_receipt)
    assert receipt["campaignId"] == config.campaign_id
    assert receipt["frameworkCommit"] == FRAMEWORK_COMMIT
    assert receipt["gatePlanCanonicalSha256"] == adapter.canonical_sha256(read_json(paths.gate_plan))
    assert receipt["derivedAt"]
    assert receipt["preflightCapturedAt"]


def test_cmd_execute_rejects_a_stale_run_authorization(tmp_path):
    """Section 2.1: `PREFLIGHT_MAX_AGE_SECONDS` must actually be enforced at
    execute time, not merely exist as an unread `SutConfig` field."""
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    derivation = derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    receipt = read_json(paths.run_authorization_receipt)
    stale = stamp(now() - timedelta(seconds=PREFLIGHT_MAX_AGE_SECONDS + 1))
    receipt["derivedAt"] = stale
    receipt["preflightCapturedAt"] = stale
    write_json(paths.run_authorization_receipt, receipt)

    with pytest.raises(PreflightExpired):
        cmd_execute(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                    typed=derivation.sentence, trace_path=tmp_path / "campaign-trace.log")
    assert not paths.gate_run.exists()


def test_cmd_execute_rejects_a_substituted_gate_plan(tmp_path):
    """Section 2.2: a gate-plan.json swapped after derivation but before
    execution must be caught by a fresh digest comparison, not silently
    accepted because the typed sentence still matches the (unrelated)
    run-authorization.json on disk."""
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    derivation = derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    tampered = read_json(paths.gate_plan)
    tampered["payload"] = {**tampered.get("payload", {}), "runs": ["substituted-run"]}
    paths.gate_plan.write_text(json.dumps(tampered))

    with pytest.raises(RunAuthorizationDrift) as excinfo:
        cmd_execute(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                    typed=derivation.sentence, trace_path=tmp_path / "campaign-trace.log")
    assert excinfo.value.field == "gatePlanCanonicalSha256"
    assert not paths.gate_run.exists()


def test_cmd_execute_rejects_a_missing_derivation_receipt(tmp_path):
    """Fail closed rather than assume freshness for a run-authorization.json
    whose receipt is absent (e.g. hand-authored, or removed independently)."""
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    derivation = derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    paths.run_authorization_receipt.unlink()

    with pytest.raises(MissingDerivationReceipt):
        cmd_execute(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                    typed=derivation.sentence, trace_path=tmp_path / "campaign-trace.log")


def test_cmd_execute_consults_remote_output_exists_before_launch(tmp_path):
    """Section 2.2: `remote_output_exists` was only ever consulted from
    `run_dry_run`; a real `cmd_execute` must refuse before launching too."""
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    derivation = derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    transport._remote_output_exists = True
    calls_before = list(transport.calls)

    with pytest.raises(GateDriverError):
        cmd_execute(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                    typed=derivation.sentence, trace_path=tmp_path / "campaign-trace.log")
    assert transport.calls == calls_before  # no launch call happened
    assert not paths.runtime_package.exists()
    assert not paths.campaign_terminal.exists()


def test_derive_run_authorization_rejects_a_corrupted_gate_plan(tmp_path):
    """Section 2.3: `derive_run_authorization` must call the *validating*
    `adapter.validate_gate_plan`, not a plain `canonical_sha256` re-hash that
    would hash a corrupted-but-well-formed document fine either way."""
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    adapter.reject_gate_plan_reason = "corrupted shape"

    with pytest.raises(FakeGatePlanRejected):
        derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    assert not paths.run_authorization_receipt.exists()


def test_cmd_execute_refuses_a_second_concurrent_attempt(tmp_path):
    """SingleFlightLock now guards `cmd_execute`, not just `cmd_auto`."""
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    derivation = derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    with SingleFlightLock(paths.run_lock):
        with pytest.raises(ConcurrentRunError):
            cmd_execute(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                        typed=derivation.sentence, trace_path=tmp_path / "campaign-trace.log")
    assert not paths.gate_run.exists()


def test_derive_run_authorization_refuses_a_second_concurrent_attempt(tmp_path):
    """SingleFlightLock now guards `derive_run_authorization` too."""
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    with SingleFlightLock(paths.run_lock):
        with pytest.raises(ConcurrentRunError):
            derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
