"""The OTel Demo gate-driver shims, against the real orchestrator.

Mirrors tests/test_hotel_gate_driver_{config,mating,shims}.py. Nothing here
contacts fb14srv6: every remote effect goes through a recorded fake runner,
and the three offline subcommands (propose / authorize / status) are driven
against a throwaway gates directory.
"""
from __future__ import annotations

import json
import os
import shlex
import socket
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "modules/otel-demo/drivers"))

from obsplacement.gate_driver.contract import (  # noqa: E402
    campaign_identity,
    check_adapter_contract,
    check_transport_contract,
)
from obsplacement.gate_driver.gate_paths import GatePaths  # noqa: E402
from obsplacement.gate_driver.module_loader import load_binding_keys, load_sut_module  # noqa: E402
from obsplacement.gate_driver import campaign_setup_flow as setup_flow  # noqa: E402

from gate_driver_config import CONFIG  # noqa: E402


@pytest.fixture(scope="module")
def adapter():
    module = load_sut_module(CONFIG.root, CONFIG.adapter_module, "otel_candidate_runtime_adapter")
    check_adapter_contract(module, label=CONFIG.adapter_module)
    return module


@pytest.fixture(scope="module", autouse=True)
def unspent_attempt(adapter):
    """The driver path refuses attempt 1 (spent by run 1); drive it as the first unspent attempt from 2 on.

    2026-10-10: the quiet epoch (selected for run A2) has attempts 1 and 2 spent, so a literal 2 no longer works for it; the
    first unspent attempt is read from the adapter's own spent table of the epoch the selector names."""
    attempt = next(number for number in range(2, 100) if number not in adapter.SPENT_ATTEMPTS)
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("OTEL_CANDIDATE_ATTEMPT", str(attempt))
        yield


@pytest.fixture(scope="module")
def transport():
    module = load_sut_module(CONFIG.root, CONFIG.transport_module, "otel_candidate_transport")
    check_transport_contract(module, label=CONFIG.transport_module)
    return module


@pytest.fixture(scope="module")
def bindings(adapter, tmp_path_factory):
    plan_dir = tmp_path_factory.mktemp("otel-plan")
    return adapter.inspect_campaign(plan_dir, "0" * 40)


class RecordedRunner:
    """A fake `CommandRunner`/`subprocess_runner`, recording and scripted."""

    def __init__(self, script=None, *, default=1):
        self.calls = []
        self.script = script or {}
        self.default = default

    def __call__(self, argv, data=None, *, input=None):  # noqa: A002
        argv = [str(item) for item in argv]
        self.calls.append(argv)
        for needle, (code, out) in self.script.items():
            if needle in " ".join(argv):
                return subprocess.CompletedProcess(argv, code, out, b"")
        return subprocess.CompletedProcess(argv, self.default, b"", b"")


# --------------------------------------------------------------------------
# 1-3: the config says what the installed controllers say
# --------------------------------------------------------------------------

def test_config_target_and_users_match_the_reviewed_allocation(adapter):
    """The one field a Hotel reader expects to be wrong: execution user."""
    allocation = adapter.runtime.target_allocation()
    identity = allocation["executionIdentities"][0]
    assert CONFIG.target_host == allocation["host"] == "fb14srv6"
    assert CONFIG.transport_user == allocation["transportUsers"][0] == "root"
    assert CONFIG.execution_user == identity["user"] == "stig"
    # srv6's stig is 1016, not srv5's 1015 and not Hotel's fhuebscher/1007.
    assert (identity["uid"], identity["gid"], identity["supplementalGids"]) == (1016, 1016, [998])
    assert adapter.EXECUTION_USER == CONFIG.execution_user


def test_config_identity_matches_the_installed_setup_controller():
    """candidate_setup's four identity constants are the same four facts."""
    installer = load_sut_module(
        CONFIG.root, "modules/otel-demo/execution/candidate_setup.py", "otel_setup_probe",
    )
    assert installer.TARGET_HOST == CONFIG.target_host
    assert installer.TRANSPORT_USER == CONFIG.transport_user
    assert installer.EXECUTION_USER == CONFIG.execution_user
    assert (installer.EXECUTION_UID, installer.EXECUTION_GID) == (1016, 1016)
    assert installer.DOCKER_GID == 998


def test_d22_setup_campaign_window_is_one_week():
    assert CONFIG.setup_campaign_window_hours == 168


# --------------------------------------------------------------------------
# 4-6: the offline half of the chain
# --------------------------------------------------------------------------

def test_inspect_campaign_replays_the_thirty_six_cell_plan_offline(bindings):
    identity = campaign_identity(bindings)
    assert identity.run_count == 36
    assert len(identity.descriptor_sha256) == 64 and len(identity.plan_sha256) == 64


def test_propose_then_authorize_then_status_works_with_no_target(adapter, tmp_path):
    """propose -> type -> status, entirely offline; no transport is loaded."""
    import dataclasses  # noqa: PLC0415
    paths = GatePaths(tmp_path / "gates")
    config = dataclasses.replace(CONFIG, plan_dir=tmp_path / "plan")
    pending = setup_flow.cmd_propose(config, adapter, paths, framework_commit="a" * 40)
    sentence = pending["expectedText"]
    assert "study=otel-demo-offpath-v1" in sentence
    assert "change=admit-otel-demo-candidate-pilot-v2" in sentence
    assert f"descriptor={adapter.runtime.frozen_descriptor() and pending['invariants']['descriptorCanonicalSha256']}" in sentence
    assert pending["invariants"]["descriptorCanonicalSha256"] == adapter.pilot.EXPECTED_DESCRIPTOR_SHA256
    assert "target=fb14srv6" in sentence
    assert "transport-user=root" in sentence
    assert "execution-user=stig" in sentence
    assert "runs=36" in sentence

    setup_flow.cmd_authorize(config, paths, typed=sentence)
    report = setup_flow.cmd_status(config, adapter, paths, framework_commit="a" * 40)
    assert report.has_campaign and report.live and report.invariants_match

    # A byte off and nothing is recorded.
    paths.setup_campaign_authorization.unlink()
    setup_flow.cmd_propose(config, adapter, paths, framework_commit="a" * 40)
    with pytest.raises(Exception):
        setup_flow.cmd_authorize(config, paths, typed=sentence.replace("runs=36", "runs=37"))


def test_release_binding_keys_are_probed_not_written_down(adapter):
    """Property #2: the key set is the installed framework's own projection."""
    keys = load_binding_keys(CONFIG.root, CONFIG.installer_module)
    probe = {name: name for name in keys if name != "setupReceiptSha256"}
    projected = adapter.runtime.installed_bindings(probe, "setupReceiptSha256")
    assert set(keys) == set(projected)
    assert "imageIds" in keys and "materializedSourceSha256" in keys


def test_driver_identity_equals_the_runtime_and_compiler_constants(adapter):
    """study / campaign_id are the offpath epoch everywhere a sentence is derived; the
    change stays v2's admission change (v3/offpath have no OpenSpec change of their own)."""
    assert CONFIG.study == adapter.runtime.STUDY_EPOCH == adapter.pilot.EPOCH == "otel-demo-offpath-v1"
    assert CONFIG.change == adapter.runtime.CHANGE_ID == "admit-otel-demo-candidate-pilot-v2"
    assert adapter.CAMPAIGN_ID == CONFIG.campaign_id == "otel-demo-offpath-v1"
    assert CONFIG.supported_postures == frozenset(adapter.pilot.POSTURES) == frozenset(adapter.runtime.POSTURES)
    # 36 cells: the window must cover the target's minimum remaining time.
    assert CONFIG.run_window_hours * 3600 > adapter.runtime.MINIMUM_REMAINING_SECONDS == 36_000
    assert len(adapter.CAMPAIGN_ID) <= 40


def test_campaign_id_is_a_shared_library_safe_slug():
    """The campaign id must satisfy the SHARED validator, not a local relaxation.

    This is defect seven of the 2026-09-15 session: the dry run refused with
    `campaignId 'otel_demo_candidate_pilot_v2' is not a safe slug` because the
    adapter derived an underscore form. The regex is imported from the shared
    library rather than restated, so a future widening of the library (which
    TeaStore and Hotel also depend on) cannot make this test vacuous, and a
    future underscore in OTel's id fails here instead of on a real host.
    """
    from obsplacement.gate_driver.gate_run_flow import _SAFE_CAMPAIGN_SLUG

    assert _SAFE_CAMPAIGN_SLUG.fullmatch(CONFIG.campaign_id) is not None
    assert "_" not in CONFIG.campaign_id


def test_compose_project_keeps_the_underscore_spelling_the_target_guards_expect(adapter):
    """The campaign id and the Compose project are separable, and both contracts hold.

    The id is hyphenated for the shared slug validator; the Compose project the
    target's guards were written against is unchanged. Pinned as exact strings
    because `candidate_remote.EXPECTED_PROJECT_PREFIX` and the
    `systemdUnit == f"{composeProject}.service"` guard are literals on the
    target, not derivations that would follow a rename.
    """
    project = adapter.runtime.compose_project_for(CONFIG.campaign_id, "otel_candidate_v4")
    assert project == "otel_candidate_v4_otel_demo_offpath_v1"
    assert adapter.runtime.SAFE_NAME.fullmatch(project) is not None
    assert len(project) <= 63
    # And the paths follow the ID, not the Compose name: `candidate_remote`
    # asserts `root.name == document["campaignId"]`, so a Compose-spelled
    # artifact root would be refused on the target.
    assert project.rsplit("otel_candidate_v4_", 1)[1] != CONFIG.campaign_id


# --------------------------------------------------------------------------
# 6b: the v2 GATE-SETUP precondition -- a posture-probe receipt before `auto`
# --------------------------------------------------------------------------

PROBE_PASS = (
    "OTEL_PLACEMENT_ENABLED=false otlp-connections=0 cartservice=running checkoutservice=running "
    "currencyservice=running productcatalogservice=running shippingservice=running \n"
    "OTEL_PLACEMENT_ENABLED=true otlp-connections=43 cartservice=running checkoutservice=running "
    "currencyservice=running productcatalogservice=running shippingservice=running \n"
    "PROBE OK: disabled posture is silent, enabled posture exports\n"
)


def test_probe_transcript_parser_accepts_the_measured_pass_and_rejects_every_other_shape():
    import campaign_setup  # noqa: PLC0415
    assert campaign_setup.parse_probe_transcript(PROBE_PASS) == {
        "disabledOtlpConnections": 0, "enabledOtlpConnections": 43,
    }
    bad = {
        "leak": PROBE_PASS.replace("=false otlp-connections=0", "=false otlp-connections=7"),
        "silent-enabled": PROBE_PASS.replace("=true otlp-connections=43", "=true otlp-connections=0"),
        "no-verdict": PROBE_PASS.replace("PROBE OK: disabled posture is silent, enabled posture exports\n", "PROBE FAILED\n"),
        "one-posture": PROBE_PASS.split("\n", 1)[1],
        "empty": "",
    }
    for label, transcript in bad.items():
        with pytest.raises(campaign_setup.GateDriverError):
            campaign_setup.parse_probe_transcript(transcript), label


def test_probe_receipt_binds_upstream_pin_and_script_bytes(adapter, tmp_path, monkeypatch):
    import campaign_setup  # noqa: PLC0415
    receipt = campaign_setup.build_probe_receipt(
        adapter, PROBE_PASS, materialized_root="/tmp/materialized", framework_commit="a" * 40,
    )
    assert receipt["kind"] == campaign_setup.PROBE_RECEIPT_KIND
    assert receipt["upstreamCommit"] == adapter.runtime.target_allocation()["source"]["upstreamCommit"]
    assert receipt["probeScriptSha256"] == campaign_setup._probe_script_sha256()
    assert receipt["runtimeAuthorized"] is False
    path = tmp_path / "posture-probe-receipt.json"
    with pytest.raises(campaign_setup.GateDriverError, match="no posture-probe receipt"):
        campaign_setup.require_probe_receipt(adapter, path)
    campaign_setup.write_json(path, receipt)
    assert campaign_setup.require_probe_receipt(adapter, path) == receipt
    # An upstream re-pin or a probe-script edit invalidates the receipt by itself.
    stale = dict(receipt, upstreamCommit="f" * 40)
    campaign_setup.write_json(path, stale)
    with pytest.raises(campaign_setup.GateDriverError, match="different upstream pin"):
        campaign_setup.require_probe_receipt(adapter, path)
    stale = dict(receipt, probeScriptSha256="0" * 64)
    campaign_setup.write_json(path, stale)
    with pytest.raises(campaign_setup.GateDriverError, match="different probe-script bytes"):
        campaign_setup.require_probe_receipt(adapter, path)
    leaky = dict(receipt, disabledOtlpConnections=7)
    campaign_setup.write_json(path, leaky)
    with pytest.raises(campaign_setup.GateDriverError, match="not a clean two-posture pass"):
        campaign_setup.require_probe_receipt(adapter, path)


def test_auto_refuses_before_the_setup_flow_without_a_probe_receipt(tmp_path, monkeypatch, capsys):
    import campaign_setup  # noqa: PLC0415
    monkeypatch.setattr(campaign_setup, "PROBE_RECEIPT", tmp_path / "absent-receipt.json")

    def never(*_args, **_kwargs):
        raise AssertionError("flow.cmd_auto must not run without a probe receipt")

    monkeypatch.setattr(campaign_setup.flow, "cmd_auto", never)
    assert campaign_setup.cmd_auto() == 1
    assert "no posture-probe receipt" in capsys.readouterr().out


def test_record_probe_writes_the_receipt_auto_reads(adapter, tmp_path, monkeypatch, capsys):
    import campaign_setup  # noqa: PLC0415
    receipt_path = tmp_path / "gates" / "posture-probe-receipt.json"
    monkeypatch.setattr(campaign_setup, "PROBE_RECEIPT", receipt_path)
    transcript = tmp_path / "probe.log"
    transcript.write_text(PROBE_PASS)
    assert campaign_setup.cmd_record_probe(transcript, tmp_path / "materialized") == 0
    assert campaign_setup.require_probe_receipt(adapter, receipt_path)["enabledOtlpConnections"] == 43
    transcript.write_text(PROBE_PASS.replace("otlp-connections=0", "otlp-connections=2"))
    assert campaign_setup.cmd_record_probe(transcript, tmp_path / "materialized") == 2
    assert "FATAL" in capsys.readouterr().out


# --------------------------------------------------------------------------
# 7-9: Hotel lesson 2 -- the remote words survive root's zsh
# --------------------------------------------------------------------------

def test_every_remote_word_is_quoted_for_the_remote_login_shell(adapter):
    """`ssh host a b c` is re-parsed by the remote shell; _ssh quotes it."""
    argv = adapter.runtime._ssh("root@fb14srv6", ["python3", "-c", "print(1); f()"])
    assert argv[:3] == ["ssh", "--", "root@fb14srv6"]
    assert len(argv) == 4
    # zsh would have choked on the parens; shlex round-trips them exactly.
    assert shlex.split(argv[3]) == ["python3", "-c", "print(1); f()"]


def test_a_path_with_a_space_or_quote_cannot_be_resplit(adapter):
    tokens = ["install", "-d", "--", "/home/stig/a b'c/d"]
    argv = adapter.runtime._ssh("root@fb14srv6", tokens)
    assert shlex.split(argv[3]) == tokens


def test_no_ssh_argv_is_built_without_the_quoting_helper():
    """A future ssh site that bypasses `_ssh` fails this test, not a campaign."""
    source = (ROOT / "modules/otel-demo/execution/candidate_runtime.py").read_text()
    body = source.split("def _ssh(", 1)[1].split("\n\n\n", 1)[1]
    assert '"ssh", "--"' not in body
    assert body.count("_ssh(destination") >= 6


# --------------------------------------------------------------------------
# 10-12: Hotel lesson 3 -- umask, modes, and the verification
# --------------------------------------------------------------------------

def test_installer_sets_an_explicit_umask_and_declares_every_mode():
    installer = load_sut_module(
        CONFIG.root, "modules/otel-demo/execution/candidate_setup.py", "otel_setup_probe",
    )
    assert installer.INSTALL_UMASK == 0o022
    assert set(installer.EXPECTED_DIRECTORY_MODES) == {
        "releaseParent", "artifactParent", "releaseRoot", "repositoryRoot",
        "remoteArtifactRoot", "controllerRoot",
    }
    # The execution identity must be able to traverse the release tree.
    assert installer.EXPECTED_DIRECTORY_MODES["releaseRoot"] & 0o055 == 0o055
    source = (ROOT / "modules/otel-demo/execution/candidate_setup.py").read_text()
    assert "os.umask(INSTALL_UMASK)" in source


def test_enforce_directory_mode_repairs_a_umask_077_directory(tmp_path):
    """The measured fb14srv6 failure, reproduced locally and then repaired."""
    installer = load_sut_module(
        CONFIG.root, "modules/otel-demo/execution/candidate_setup.py", "otel_setup_probe",
    )
    previous = os.umask(0o077)
    try:
        target = tmp_path / "release"
        target.mkdir(mode=0o755)
        # This is the bug: 0o755 & ~0o077 == 0o700, so nobody else can enter.
        assert stat.S_IMODE(target.lstat().st_mode) == 0o700
        installer.enforce_directory_mode(target, 0o755, "release root")
        assert stat.S_IMODE(target.lstat().st_mode) == 0o755
    finally:
        os.umask(previous)


def test_enforce_directory_mode_fails_closed_when_the_mode_cannot_take(tmp_path, monkeypatch):
    installer = load_sut_module(
        CONFIG.root, "modules/otel-demo/execution/candidate_setup.py", "otel_setup_probe",
    )
    target = tmp_path / "artifacts"
    target.mkdir()
    monkeypatch.setattr(installer.os, "chmod", lambda *a, **k: None)
    target.chmod(0o700)
    with pytest.raises(installer.SetupFailure, match=r"mode is 0\d{3}, not the required 0750"):
        installer.enforce_directory_mode(target, 0o750, "artifact root")


# --------------------------------------------------------------------------
# 13-14: Hotel lesson 8 -- SO_REUSEADDR
# --------------------------------------------------------------------------

def test_port_probe_enables_so_reuseaddr_in_both_copies():
    setup_source = (ROOT / "modules/otel-demo/execution/candidate_setup.py").read_text()
    runtime_source = (ROOT / "modules/otel-demo/execution/candidate_runtime.py").read_text()
    for source in (setup_source, runtime_source):
        assert "SO_REUSEADDR, 1)" in source
        assert "SO_REUSEADDR, 0)" not in source


def test_port_probe_still_reports_a_live_listener_as_occupied(adapter):
    """SO_REUSEADDR must not turn the check into a no-op."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("0.0.0.0", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        occupied = adapter.runtime._probe_reserved_ports([port], wait_seconds=0)
        assert occupied == [port]
    finally:
        listener.close()


# --------------------------------------------------------------------------
# 15-17: Hotel lesson 5 -- status answers for a not-yet-launched identity
# --------------------------------------------------------------------------

REMOTE_INPUT = {
    "campaignId": "otel-demo-candidate-pilot-v2",
    "systemdUnit": "otel-candidate-v4-" + "f" * 32,
    "remoteArtifactRoot": "/home/stig/observability-placement-candidate-v4-runs/x",
    "target": {"host": "fb14srv6", "transportUser": "root"},
}


def test_status_of_a_never_launched_identity_is_not_terminal(transport):
    runner = RecordedRunner({"systemctl show": (0, b"LoadState=not-found\nActiveState=inactive\nSubState=dead\nResult=success\n")})
    status = transport.remote_status(REMOTE_INPUT, "a" * 64, runner=runner)
    assert status["state"] == "not-launched"
    assert status["terminalExists"] is False and status["abortExists"] is False
    assert status["transportOk"] is True
    # The shared `is_terminal` fail-safe OR still fires here, and is left
    # alone; the per-SUT driver is what treats this state as pre-terminal.
    import campaign_status  # noqa: PLC0415
    assert status["state"] in campaign_status.PRE_TERMINAL_STATES


def test_status_of_a_failed_ssh_is_unknown_not_terminal(transport):
    runner = RecordedRunner({"systemctl show": (255, b"")})
    status = transport.remote_status(REMOTE_INPUT, "a" * 64, runner=runner)
    assert status["state"] == "unknown" and status["transportOk"] is False
    # No completion probe is even attempted when the transport failed.
    assert status["completionProbes"] == []


def test_status_reports_terminal_once_the_receipt_exists(transport):
    runner = RecordedRunner({
        "systemctl show": (0, b"LoadState=loaded\nActiveState=inactive\nSubState=dead\nResult=success\n"),
        "remote-terminal.json": (0, b""),
    })
    status = transport.remote_status(REMOTE_INPUT, "a" * 64, runner=runner)
    assert status["state"] == "stopped" and status["terminalExists"] is True


# --------------------------------------------------------------------------
# 18-19: read-only one-shot precondition
# --------------------------------------------------------------------------

def test_remote_output_exists_is_false_for_a_fresh_identity(transport):
    runner = RecordedRunner({"test -e": (1, b"")})
    assert transport.remote_output_exists(REMOTE_INPUT, runner=runner) is False
    assert all(call[0] == "ssh" for call in runner.calls)
    assert len(runner.calls) == 4
    assert all(call[3].startswith("test -e ") for call in runner.calls)


def test_remote_output_exists_raises_rather_than_reading_an_outage_as_clean(transport):
    runner = RecordedRunner({"test -e": (255, b"")})
    with pytest.raises(Exception, match="read-only remote probe failed"):
        transport.remote_output_exists(REMOTE_INPUT, runner=runner)


# --------------------------------------------------------------------------
# 20-21: Hotel lesson 6 -- the child can read its own admission
# --------------------------------------------------------------------------

def _launch_code() -> str:
    """`launch`'s executable lines only: comments name the defective spellings."""
    source = (ROOT / "modules/otel-demo/execution/candidate_runtime.py").read_text()
    body = source.split("def launch(self, package", 1)[1].split("def status(", 1)[0]
    return "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )


def test_launch_proves_readability_as_the_execution_user_before_systemd_run():
    source = (ROOT / "modules/otel-demo/execution/candidate_runtime.py").read_text()
    launch = source.split("def launch(self, package", 1)[1].split("def status(", 1)[0]
    probe = launch.index('tools["runuser"], "--user", "stig", "--", "test", "-r", remote_package')
    run = launch.index('"systemd-run"')
    assert probe < run, "the readability probe must run before the unit is created"


def test_launch_probe_and_unit_spend_the_same_runuser_token():
    """2026-09-17, instance nine: the probe said bare `runuser` (PATH-resolved,
    worked) and the unit said `/usr/sbin/runuser` (absent on fb14srv5/6). The
    guard exercised a different code path than the thing it guarded, so it
    passed and the unit died in 0 s. Both must spend one resolved token."""
    launch = _launch_code()
    assert '"/usr/sbin/runuser"' not in launch and '"/sbin/runuser"' not in launch
    assert '"runuser", "--user"' not in launch, "no unresolved runuser spelling in the launch argv"
    assert launch.count('tools["runuser"]') == 2, "probe and unit both spend the resolved token"


def test_launch_argv_bakes_no_absolute_binary_path_and_no_numeric_group():
    """The class, not the instance. Every binary and group spelling on the
    launch argv is resolved on the target; the three hosts genuinely differ."""
    launch = _launch_code()
    systemd = launch.split('"systemd-run"', 1)[1].split("\n", 1)[0]
    for literal in ('"/usr/bin/flock"', '"/usr/bin/python3"', '"/usr/sbin/runuser"'):
        assert literal not in systemd, f"{literal} is a host-specific literal"
    for literal in ('"1016"', '"998"'):
        assert f'"--group", {literal}' not in systemd
        assert f'"--supp-group", {literal}' not in systemd
    for token in ('tools["flock"]', 'tools["python3"]', 'groups[1016]', 'groups[998]'):
        assert token in systemd, f"{token} must be resolved on the target"


def test_launch_verifies_the_unit_is_active_not_merely_accepted():
    """`systemd-run` returns 0 on acceptance. The launch path must ask the host."""
    source = (ROOT / "modules/otel-demo/execution/candidate_runtime.py").read_text()
    launch = _launch_code()
    assert "_verify_unit_active(destination, unit)" in launch
    verify = source.split("def _verify_unit_active", 1)[1].split("\n    def ", 1)[0]
    assert '"LoadState"' in verify and '"ActiveState"' in verify
    assert '"active"' in verify
    assert "raise GateError" in verify


def test_installer_proves_traversal_as_the_execution_user():
    source = (ROOT / "modules/otel-demo/execution/candidate_setup.py").read_text()
    assert "verify_execution_identity_can_traverse(" in source
    assert '"runuser", "--user", EXECUTION_USER, "--", "test", "-x"' in source


# --------------------------------------------------------------------------
# 22: Hotel lesson 9 -- aborted run state is archived, not deleted
# --------------------------------------------------------------------------

def test_archive_run_moves_the_write_new_json_documents_aside(tmp_path, monkeypatch):
    import dataclasses  # noqa: PLC0415
    import gate_run  # noqa: PLC0415
    gates = tmp_path / "gates"
    gates.mkdir()
    for name in gate_run.RUN_PHASE_DOCUMENTS:
        (gates / name).write_text("{}")
    monkeypatch.setattr(gate_run, "CONFIG", dataclasses.replace(gate_run.CONFIG, gates_dir=gates))
    monkeypatch.setattr(gate_run, "PATHS", GatePaths(gates))
    assert gate_run.cmd_archive_run() == 0
    archives = [p for p in gates.iterdir() if p.name.startswith("archived-run-")]
    assert len(archives) == 1
    assert sorted(p.name for p in archives[0].iterdir()) == sorted(gate_run.RUN_PHASE_DOCUMENTS)
    for name in gate_run.RUN_PHASE_DOCUMENTS:
        assert not (gates / name).exists()


# --------------------------------------------------------------------------
# 23-24: the transport contract's own fail-closed behaviour
# --------------------------------------------------------------------------

def test_plan_binding_refuses_before_the_release_is_bound(adapter, tmp_path):
    fresh = adapter.inspect_campaign(tmp_path / "plan", "b" * 40)
    with pytest.raises(adapter.runtime.GateError, match="release bundle digests"):
        adapter.plan_binding(fresh)


def test_capture_spec_round_trips_and_refuses_a_different_install(transport, bindings, tmp_path):
    binding = {"setupReceiptSha256": "c" * 64, "releaseRoot": "/home/stig/x"}
    archive = tmp_path / "capture-spec.tar"
    transport.build_capture_spec(bindings, binding, archive_path=archive)
    assert transport._read_capture_spec(archive)["releaseBinding"] == binding
    controller = transport.BoundedSetupController(bindings=bindings)
    with pytest.raises(transport.runtime.GateError, match="differs from the install receipt"):
        controller.admit_readiness(
            archive_path=archive,
            release_binding={"setupReceiptSha256": "d" * 64, "releaseRoot": "/home/stig/x"},
            local_output=tmp_path / "out",
        )


def test_runtime_package_carries_the_identity_the_watcher_reads_back(transport, monkeypatch):
    class FakePackage:
        gate_plan = {"binding": {
            "campaignId": "otel-demo-candidate-pilot-v2",
            "remoteArtifactRoot": "/home/stig/observability-placement-candidate-v4-runs/x",
            "target": {"host": "fb14srv6", "transportUser": "root"},
        }}

    document = {"systemdUnit": "otel-candidate-v4-" + "e" * 32, "kind": "x"}
    monkeypatch.setattr(transport.runtime, "execution_package", lambda package: document)
    built = transport.build_runtime_package(FakePackage())
    assert built["campaignId"] == "otel-demo-candidate-pilot-v2"
    assert built["systemdUnit"] == document["systemdUnit"]
    # The watcher reads campaignId, systemdUnit and remoteArtifactRoot back out
    # of this file long after the RuntimePackage object is gone.
    assert json.loads(json.dumps(built))["executionPackage"] == document
    assert transport._remote_input(built)["unit"] == document["systemdUnit"]


def test_execution_identity_accepts_the_groups_runuser_actually_produces():
    """`runuser --user stig --group stig --supp-group docker` yields [998, 1016].

    The old assertion demanded exactly [998], which no process could satisfy: Linux
    getgroups() includes the primary gid. It had never executed because the numeric
    --group spelling failed earlier in the argv, so a green suite said nothing.
    """
    import importlib.util, pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "otel_remote", root / "modules/otel-demo/execution/candidate_remote.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def check(groups):
        return mod.validate_local_target(
            mod.EXPECTED_TARGET, observed_host="fb14srv6", observed_user="stig",
            observed_uid=1016, observed_gid=1016, observed_groups=groups)

    # what runuser really produces, either order
    assert check([998, 1016])["supplementalGids"] == [998, 1016]
    assert check([1016, 998])["supplementalGids"] == [998, 1016]

    # still refuses anything else: missing docker, an extra group, or the old shape
    for bad in ([998], [1016], [998, 1016, 27], [27, 998], []):
        try:
            check(bad)
        except Exception:
            continue
        raise AssertionError(f"identity check accepted {bad!r}, it must not")
