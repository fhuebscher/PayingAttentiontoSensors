import pytest

from obsplacement.gate_driver.campaign_setup_flow import (
    cmd_auto,
    cmd_authorize,
    cmd_propose,
    cmd_status,
    require_live_campaign_from_disk,
)
from obsplacement.gate_driver.errors import CampaignDrift, ConcurrentRunError, GateDriverError, NoLiveCampaign
from obsplacement.gate_driver.gate_paths import GatePaths
from obsplacement.gate_driver.json_io import read_json, write_json
from obsplacement.gate_driver.sentence import SentenceMismatch

from gate_driver_fakes import FakeAdapter, FakeTransport, make_config

FRAMEWORK_COMMIT = "e29e6664e3647e17646c979100964f317ac51551"


def wire(tmp_path):
    config = make_config(tmp_path)
    paths = GatePaths(config.gates_dir)
    adapter = FakeAdapter()
    transport = FakeTransport()
    return config, paths, adapter, transport


def authorize_campaign(config, paths, adapter, framework_commit=FRAMEWORK_COMMIT):
    pending = cmd_propose(config, adapter, paths, framework_commit=framework_commit)
    return cmd_authorize(config, paths, typed=pending["expectedText"])


def test_authorize_without_propose_fails_closed(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    with pytest.raises(NoLiveCampaign):
        cmd_authorize(config, paths, typed="anything")


def test_authorize_fails_closed_on_sentence_mismatch(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    cmd_propose(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    with pytest.raises(SentenceMismatch):
        cmd_authorize(config, paths, typed="not the sentence")
    assert not paths.setup_campaign_authorization.exists()
    assert paths.setup_campaign_pending.exists()  # untouched by the failed attempt


def test_authorize_records_and_clears_pending_and_audits(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    record = authorize_campaign(config, paths, adapter)
    assert not paths.setup_campaign_pending.exists()
    assert read_json(paths.setup_campaign_authorization) == record
    audit_lines = paths.setup_campaign_audit.read_text().strip().splitlines()
    assert len(audit_lines) == 1
    assert '"event": "campaign-authorized"' in audit_lines[0]


def test_authorize_rejects_a_forged_deadline(tmp_path):
    """Section 2.5: `pending["deadline"]` must be recomputed from
    `pending["proposedAt"]` + `config.setup_campaign_window_hours`, not
    trusted verbatim from the editable pending file -- an operator with
    filesystem access between propose and authorize could otherwise edit
    both `deadline` and `expectedText` consistently and have
    `verify_typed_sentence` alone never notice."""
    config, paths, adapter, transport = wire(tmp_path)
    pending = cmd_propose(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    forged = dict(pending)
    forged["deadline"] = "2099-01-01T00:00:00Z"
    write_json(paths.setup_campaign_pending, forged)

    with pytest.raises(GateDriverError):
        cmd_authorize(config, paths, typed=pending["expectedText"])
    assert not paths.setup_campaign_authorization.exists()


def test_require_live_campaign_raises_no_live_campaign_when_never_authorized(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    with pytest.raises(NoLiveCampaign):
        require_live_campaign_from_disk(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)


def test_require_live_campaign_raises_drift_when_run_count_changes(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    authorize_campaign(config, paths, adapter)

    class DriftedAdapter(FakeAdapter):
        def inspect_campaign(self, plan_dir, framework_commit):
            bindings = super().inspect_campaign(plan_dir, framework_commit)
            bindings.run_ids = tuple(bindings.run_ids) + ("extra-run",)
            return bindings

    with pytest.raises(CampaignDrift):
        require_live_campaign_from_disk(config, DriftedAdapter(), paths, framework_commit=FRAMEWORK_COMMIT)


def test_cmd_auto_requires_a_live_campaign_authorization(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    with pytest.raises(NoLiveCampaign):
        cmd_auto(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                 trace_dir=tmp_path / "traces")


def test_cmd_auto_runs_prepare_install_readiness_under_a_live_campaign(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    authorize_campaign(config, paths, adapter)

    installer_dir = config.root / "modules/fake-sut/execution"
    installer_dir.mkdir(parents=True, exist_ok=True)
    (installer_dir / "candidate_release_installer.py").write_text(
        "RELEASE_BINDING_KEYS = ('bindingKeyA', 'bindingKeyB')\n"
    )

    admission = cmd_auto(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                          trace_dir=tmp_path / "traces")
    assert admission["readinessCanonicalSha256"] == "fakereadinesssha"
    assert paths.gate_plan.is_file()
    assert paths.gate_setup.is_file()
    assert paths.install_receipt.is_file()
    assert paths.fetched_readiness_document.is_file()
    events = [line for line in paths.setup_campaign_audit.read_text().splitlines()]
    assert any('"event": "auto-begin"' in line for line in events)
    assert any('"event": "installed"' in line for line in events)
    assert any('"event": "readiness-admitted"' in line for line in events)


def test_cmd_auto_archives_rather_than_silently_replaces_a_prior_attempt(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    authorize_campaign(config, paths, adapter)
    installer_dir = config.root / "modules/fake-sut/execution"
    installer_dir.mkdir(parents=True, exist_ok=True)
    (installer_dir / "candidate_release_installer.py").write_text(
        "RELEASE_BINDING_KEYS = ('bindingKeyA', 'bindingKeyB')\n"
    )
    cmd_auto(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
              trace_dir=tmp_path / "traces")
    first_receipt = read_json(paths.install_receipt)

    cmd_auto(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
              trace_dir=tmp_path / "traces")

    archives = sorted(p for p in paths.gates_dir.iterdir() if p.name.startswith("attempt-"))
    assert len(archives) == 1
    assert read_json(archives[0] / "install-receipt.json") == first_receipt


def test_cmd_auto_refuses_a_second_concurrent_run(tmp_path):
    from obsplacement.gate_driver.fs_guards import SingleFlightLock

    config, paths, adapter, transport = wire(tmp_path)
    authorize_campaign(config, paths, adapter)
    paths.gates_dir.mkdir(parents=True, exist_ok=True)
    with SingleFlightLock(paths.auto_lock):
        with pytest.raises(ConcurrentRunError):
            cmd_auto(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                      trace_dir=tmp_path / "traces")


def test_cmd_status_reports_no_campaign_when_none_recorded(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    report = cmd_status(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    assert report.has_campaign is False


def test_cmd_status_reports_live_and_matching_after_authorization(tmp_path):
    config, paths, adapter, transport = wire(tmp_path)
    authorize_campaign(config, paths, adapter)
    report = cmd_status(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    assert report.has_campaign is True
    assert report.live is True
    assert report.invariants_match is True
