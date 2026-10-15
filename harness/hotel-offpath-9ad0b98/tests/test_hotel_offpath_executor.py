"""The executor changes behind hotel-offpath-v1: an off-path pause fault and a per-epoch collection scope.

Covers (every check names its planted defect; "planted" means the test builds the defect and the code must refuse it):

1. The fault adapter: ``consul-pause`` is a declared off-path scenario; its manifestation is the container read back as
   paused, the route outage is recorded and not required; the on-path pauses keep the outage rule (planted: a
   search-pause whose route stayed up is not manifested; a consul pause whose container never paused is not).
2. The witness validates a consul receipt, with the route up or down, and still refuses a receipt that did not
   manifest, a wrong target, a late onset, an unknown scenario, and an on-path pause without its outage.
3. The CPU scope: the ten application services unless the epoch adds consul; a missing or an extra container is
   refused, and ``applicationCpu*`` never includes consul.
4. Earlier epochs are unchanged.  The pins of the sweep harness files at ca58974 (candidate_cell, candidate_terminal,
   candidate_evidence) could not survive these edits; what replaces them is a differential: the same sealed sweep
   cells go through the ca58974 terminal and the current one and must give byte-identical results (manifest
   included), the same fake-driven runs through both cell runners must issue identical commands, and a planted
   change of the scope declaration must break that equality (the comparison can fail).
5. The 3.9 grammar floor of every changed target-side file.
"""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/hotel-reservation"
SWEEP = "hotel-traffic-sweep-v1"
SWEEP_COMMIT = "ca58974785c97fe54afe351f928c65fa46f18403"   # the harness of sweep relaunch 3
BARRIER = 1000.0


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


quiet_tests = load("hotel_offpath_exec_test_quiet_tests", Path(__file__).parent / "test_hotel_quiet_calibration.py")
helpers = quiet_tests.helpers                      # the sweep tests' sealing and fake-driving helpers
sweep = quiet_tests.sweep
pause = load("hotel_offpath_exec_pause", MODULE / "faults/compose_pause.py")
lmt = load("hotel_offpath_exec_lmt", MODULE / "faults/lmt_faults.py")
witness = load("hotel_offpath_exec_witness", MODULE / "witness/candidate_evidence.py")
resources = load("hotel_offpath_exec_resources", MODULE / "collectors/candidate_resources.py")

COMPOSE_ENV = {"HR_FRONTEND_PORT": "35005", "HR_JAEGER_QUERY_PORT": "36685", "HR_SOURCE_SHA256": "a" * 64}


# ------------------------------------------------------------------------------------------ 1. the fault adapter
def _run_pause(monkeypatch, tmp_path: Path, scenario: str, *, route_during: bool, paused_during: bool = True):
    """pause.inject with the shell faked: the container reads back paused (or not), the route is up (or not)."""
    states = iter(({"exists": True, "running": True, "paused": False},
                   {"exists": True, "running": True, "paused": paused_during},
                   {"exists": True, "running": True, "paused": False}))
    availability = iter((True, route_during))
    commands = []
    monkeypatch.setattr(pause, "container_state", lambda *_args, **_kwargs: next(states))
    monkeypatch.setattr(pause, "route_available", lambda *_args: next(availability))
    monkeypatch.setattr(pause, "wait_recovered", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(pause.time, "sleep", lambda _seconds: None)
    monotonic = iter((0.0, 0.05, 5.0, 15.0, 15.02, 15.1, 15.2))
    monkeypatch.setattr(pause.time, "monotonic", lambda: next(monotonic))

    def record(args, check=True, env=None):
        commands.append(list(args))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(pause, "command", record)
    receipt = pause.inject(tmp_path, "project", scenario, 1, 15, "http://host/hotels", tmp_path / "receipt.json",
                           env=COMPOSE_ENV)
    return receipt, commands


def test_consul_pause_is_a_declared_offpath_scenario_and_the_on_path_pauses_are_unchanged():
    assert pause.ALLOWED == {"search-pause": "search", "reservation-pause": "reservation"}
    assert pause.OFFPATH_ALLOWED == {"consul-pause": "consul"}
    assert pause.validate("consul-pause", 1, 15) == "consul"
    assert pause.validate("search-pause", 1, 15) == "search"
    with pytest.raises(ValueError, match="consul-pause"):
        pause.validate("jaeger-pause", 1, 15)               # planted: a container nobody declared
    with pytest.raises(ValueError):
        pause.validate("consul-pause", 1, 0)                # the parameter checks apply to it too


def test_an_offpath_pause_is_manifested_by_the_read_back_pause_with_the_route_up(monkeypatch, tmp_path: Path):
    receipt, commands = _run_pause(monkeypatch, tmp_path, "consul-pause", route_during=True)
    assert receipt["targetService"] == "consul" and receipt["faultKind"] == "pause"
    assert receipt["outageObserved"] is False                # recorded, not required
    assert receipt["duringState"]["paused"] is True
    assert receipt["manifested"] is True and receipt["recovered"] is True and receipt["successful"] is True
    assert [cmd[-2:] for cmd in commands if "pause" in cmd or "unpause" in cmd] == [
        ["pause", "consul"], ["unpause", "consul"]]


def test_an_offpath_pause_whose_route_also_went_down_is_still_manifested(monkeypatch, tmp_path: Path):
    receipt, _ = _run_pause(monkeypatch, tmp_path, "consul-pause", route_during=False)
    assert receipt["outageObserved"] is True and receipt["manifested"] is True and receipt["successful"] is True


def test_planted_offpath_pause_that_never_paused_is_not_manifested(monkeypatch, tmp_path: Path):
    receipt, _ = _run_pause(monkeypatch, tmp_path, "consul-pause", route_during=True, paused_during=False)
    assert receipt["duringState"]["paused"] is False
    assert receipt["manifested"] is False and receipt["successful"] is False


def test_planted_on_path_pause_whose_route_stayed_up_is_not_manifested(monkeypatch, tmp_path: Path):
    """The outage rule of the on-path pauses is intact: the off-path rule did not loosen it."""
    receipt, _ = _run_pause(monkeypatch, tmp_path, "search-pause", route_during=True)
    assert receipt["outageObserved"] is False
    assert receipt["manifested"] is False and receipt["successful"] is False
    receipt, _ = _run_pause(monkeypatch, tmp_path / "again", "search-pause", route_during=False)
    assert receipt["manifested"] is True and receipt["successful"] is True


def test_the_lmt_dispatcher_hands_consul_pause_to_the_pause_adapter(monkeypatch, tmp_path: Path):
    seen = {}
    monkeypatch.setattr(lmt.pause, "inject", lambda *args, **kwargs: seen.update(scenario=args[2]) or {"ok": True})
    assert lmt.inject(tmp_path, "project", "consul-pause", 60, 60, "u", tmp_path / "r.json",
                      start_at_monotonic=1.0) == {"ok": True}
    assert seen == {"scenario": "consul-pause"}
    with pytest.raises(ValueError, match="consul-pause"):
        lmt.inject(tmp_path, "project", "jaeger-pause", 60, 60, "u", tmp_path / "r2.json", start_at_monotonic=1.0)


# ----------------------------------------------------------------------------------------------- 2. the witness
def _timing(regime: str = "search-pause-effect", rate: float = 1.0) -> dict:
    return sweep.cell_timing("%s-r%s-b01-full-a01" % (regime, sweep.rate_token(rate)), regime, rate)


def _consul_receipt(timing: dict, *, route_during: bool = True, **overrides) -> dict:
    onset, hold = timing["faultOnsetSeconds"], timing["faultHoldSeconds"]
    started = BARRIER + onset + 0.18
    receipt = {
        "schemaVersion": 1, "faultKind": "pause", "scenario": "consul-pause", "targetService": "consul",
        "scheduledAtSeconds": onset, "requestedOutageSeconds": hold,
        "startedAt": "2026-10-15T01:01:00Z", "endedAt": "2026-10-15T01:02:01Z",
        "manifested": True, "outageObserved": not route_during, "recovered": True, "successful": True,
        "preState": {"running": True, "paused": False}, "preRouteAvailable": True,
        "duringState": {"running": True, "paused": True}, "recoveryState": {"running": True, "paused": False},
        "startedMonotonic": started, "appliedMonotonic": started + 0.27, "revertingMonotonic": started + hold,
        "unpausedAtMonotonic": started + hold + 0.1, "readyAtMonotonic": started + 0.27 + hold + 0.4,
        "endedMonotonic": started + 0.27 + hold + 0.5, "actualOutageSeconds": hold + 0.1,
        "commands": [{"action": a, "returnCode": 0, "stdout": "", "stderr": ""} for a in ("pause", "unpause")],
        "error": None,
        "probes": [{"phase": "pre", "startMonotonic": started - 0.05, "endMonotonic": started - 0.01,
                    "available": True},
                   {"phase": "during", "startMonotonic": started + 0.27, "endMonotonic": started + 0.37,
                    "available": route_during}],
    }
    return {**receipt, **overrides}


def _validate(receipt: dict, timing: dict, scenario: str = "consul-pause"):
    return witness.validate_fault_receipt(receipt, scenario, barrier_monotonic=BARRIER, timing=timing)


@pytest.mark.parametrize("route_during", [True, False])
def test_witness_accepts_a_consul_receipt_with_the_route_up_or_down(route_during):
    timing = _timing()
    truth = _validate(_consul_receipt(timing, route_during=route_during), timing)
    assert truth["state"] == "supported" and truth["faultKind"] == "pause"
    started = BARRIER + timing["faultOnsetSeconds"] + 0.18
    assert truth["detectionWindowMonotonic"] == pytest.approx([started + 0.27, started + timing["faultHoldSeconds"]])


@pytest.mark.parametrize("defect, match", [
    ({"manifested": False}, "manifestation"),
    ({"duringState": {"running": True, "paused": False}}, "manifestation"),     # never read back as paused
    ({"recoveryState": {"running": True, "paused": True}}, "manifestation"),    # still paused afterwards
    ({"targetService": "search"}, "manifestation"),                             # another container's receipt
    ({"outageObserved": "no"}, "manifestation"),                                # not even a recorded bool
    ({"recovered": False}, "manifestation"),
    ({"successful": False}, "manifestation"),
    ({"scheduledAtSeconds": 45}, "manifestation"),                              # not this cell's schedule
    ({"actualOutageSeconds": 70.0}, "manifestation"),                           # held 10 s too long
])
def test_planted_consul_receipt_defects_are_refused(defect, match):
    timing = _timing()
    with pytest.raises(witness.WitnessError, match=match):
        _validate(_consul_receipt(timing, **defect), timing)


def test_planted_consul_receipt_without_the_recorded_outage_field_or_with_a_late_onset_is_refused():
    timing = _timing()
    receipt = _consul_receipt(timing)
    del receipt["outageObserved"]
    with pytest.raises(witness.WitnessError, match="fields differ"):
        _validate(receipt, timing)
    late = _consul_receipt(timing)
    for key in ("startedMonotonic", "appliedMonotonic", "revertingMonotonic", "unpausedAtMonotonic",
                "readyAtMonotonic", "endedMonotonic"):
        late[key] += 2.5
    with pytest.raises(witness.WitnessError, match="onset differs"):
        _validate(late, timing)


def test_witness_refuses_an_unknown_scenario_and_keeps_the_on_path_outage_rule():
    timing = _timing()
    with pytest.raises(witness.WitnessError, match="not declared"):
        _validate(_consul_receipt(timing, scenario="jaeger-pause"), timing, scenario="jaeger-pause")
    # A search-pause receipt that never saw its outage is still refused (planted: the off-path rule must not leak).
    receipt = _consul_receipt(timing, scenario="search-pause", targetService="search", route_during=True)
    with pytest.raises(witness.WitnessError, match="manifestation"):
        _validate(receipt, timing, scenario="search-pause")
    receipt["outageObserved"], receipt["probes"][1]["available"] = True, False
    assert _validate(receipt, timing, scenario="search-pause")["state"] == "supported"


def test_consul_pause_has_no_fault_specific_path_truth_so_no_truncation_is_excused():
    assert "consul-pause" not in witness.PAUSE_TARGETS and witness.OFFPATH_PAUSE_TARGETS == {"consul-pause": "consul"}
    assert set(witness.PAUSE_TARGETS) == {"search-pause", "reservation-pause"}


# ---------------------------------------------------------------------------------------------- 3. the CPU scope
def _cpu_document(scope, *, measurement: int = 180, consul_percent: float = 5.0, aggregate: float = 100.0) -> dict:
    identities = {"%064x" % n: s for n, s in enumerate(scope, 1)}
    rows = [{"service": s, "containerId": c, "cpuPercent": 10.0 if s in resources.APPLICATION_SERVICES else consul_percent}
            for c, s in identities.items()]
    return {
        "schemaVersion": 1, "contract": resources.RESOURCE_CONTRACT,
        "project": "hotel_candidate_v4_deadbeef_01", "applicationServices": list(scope),
        "containerIdentities": identities, "windowStartMonotonic": BARRIER,
        "windowEndMonotonic": BARRIER + measurement, "intervalSeconds": 10.0,
        "samples": [{"capturedAtEpoch": BARRIER + t, "capturedAtMonotonic": BARRIER + t, "containers": rows,
                     "applicationCpuPercent": aggregate} for t in range(0, measurement + 1, 10)],
        "captureComplete": True, "applicationCpuSeconds": float(measurement),
    }


def test_cpu_scope_is_the_ten_application_services_unless_the_epoch_adds_consul():
    app, extended = resources.APPLICATION_SERVICES, resources.EXTENDED_SERVICES
    assert extended == app + ("consul",)
    assert resources.validate_cpu(_cpu_document(app))["applicationCpuSeconds"] == pytest.approx(180.0)
    assert resources.validate_cpu(_cpu_document(app), app)["verdict"] == "pass"
    # Extended scope: consul's own 5 % is a row, and the application aggregate (100 % = ten x 10 %) is unchanged.
    result = resources.validate_cpu(_cpu_document(extended), extended)
    assert result["applicationCpuSeconds"] == pytest.approx(180.0)
    # Planted: the aggregate that includes consul (105 %) is not the application CPU.
    with pytest.raises(resources.ResourceError, match="aggregate differs"):
        resources.validate_cpu(_cpu_document(extended, aggregate=105.0), extended)
    # Planted: a consul row where the epoch declares none, and no consul row where it declares one.
    with pytest.raises(resources.ResourceError):
        resources.validate_cpu(_cpu_document(extended), app)
    with pytest.raises(resources.ResourceError):
        resources.validate_cpu(_cpu_document(app), extended)
    with pytest.raises(resources.ResourceError, match="not a declared scope"):
        resources.validate_cpu(_cpu_document(app), app + ("jaeger",))


def test_cpu_collector_scope_follows_the_container_identities_it_is_given():
    app, extended = resources.APPLICATION_SERVICES, resources.EXTENDED_SERVICES
    assert resources.scope_of(app) == app and resources.scope_of(extended) == extended
    with pytest.raises(resources.ResourceError):
        resources.scope_of(app[:-1])                          # a missing application container
    with pytest.raises(resources.ResourceError):
        resources.scope_of(extended + ("jaeger",))            # a container nobody declared
    identities = {"%064x" % n: s for n, s in enumerate(extended, 1)}
    stdout = "".join(json.dumps({"Container": cid, "CPUPerc": "%s%%" % (10 if s != "consul" else 5)}) + "\n"
                     for cid, s in identities.items())
    assert [row["service"] for row in resources.parse_stats(stdout, identities)] == sorted(extended)
    with pytest.raises(resources.ResourceError, match="omitted"):
        resources.parse_stats(stdout.splitlines(True)[1] + "", identities)
    sample = resources.docker_sample(identities, run_command=lambda *a, **k: subprocess.CompletedProcess(
        a, 0, stdout, ""))
    assert sample["applicationCpuPercent"] == pytest.approx(100.0)       # consul's 5 % is not in it


def test_cpu_collector_records_the_extended_scope_it_was_given():
    extended = resources.EXTENDED_SERVICES
    identities = {"%064x" % n: s for n, s in enumerate(extended, 1)}
    stdout = "".join(json.dumps({"Container": cid, "CPUPerc": "10%" if s != "consul" else "5%"}) + "\n"
                     for cid, s in identities.items())
    sample = lambda ids: resources.docker_sample(                                       # noqa: E731
        ids, run_command=lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout, ""))
    start = time.monotonic() + 0.3
    document = resources.collect_cpu("hotel_candidate_v4_deadbeef_01", identities, start, start + 0.9,
                                     interval_seconds=0.25, sample=sample)
    assert document["applicationServices"] == list(extended)
    assert all(len(row["containers"]) == 11 and row["applicationCpuPercent"] == pytest.approx(100.0)
               for row in document["samples"])
    assert resources.validate_cpu(document, extended)["verdict"] == "pass"
    with pytest.raises(resources.ResourceError):
        resources.validate_cpu(document)                     # the default (ten-service) scope refuses it


# -------------------------------------------------------------------------- 4. earlier epochs are unchanged
@pytest.fixture(scope="module")
def trees(tmp_path_factory):
    """The ca58974 sweep tree and the current tree, both under the sweep's selector."""
    base = tmp_path_factory.mktemp("offpath-exec")
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", SWEEP_COMMIT,
                              "modules/hotel-reservation", "pipelines/campaigns"],
                             capture_output=True, check=True).stdout
    source = base / "ca58974"
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(source, filter="data")
    old = quiet_tests._tree(base / "old", SWEEP, source=source)
    new = quiet_tests._tree(base / "new", SWEEP)
    for tree in (old, new):
        assert tree["runtime"].STUDY_EPOCH == SWEEP
    return {"old": old, "new": new}


def _sweep_cells(tree, campaign: Path) -> dict:
    """Three sweep cells: no fault, an on-path pause, a degradation (contract and fault receipt from the sweep tests)."""
    cells = {"no-fault": (helpers._calibration_contract(tree, campaign, 1.0), None)}
    for regime in ("search-pause-effect", "net-delay-effect"):
        contract, _, _, receipt = helpers._fault_cell(tree, campaign, regime, 1.0, block=2)
        cells[regime] = (contract, receipt)
    return cells


def _pause_events(service: str):
    """Docker event rows of a pause fault on ``service``'s own container (what the real event stream retains)."""
    return lambda ids: [{"Action": action, "Actor": {"ID": ids[service]}} for action in ("pause", "unpause")]


@pytest.mark.parametrize("key", ["no-fault", "search-pause-effect", "net-delay-effect"])
def test_sealed_sweep_cells_validate_byte_identically_under_the_ca58974_and_the_current_terminal(trees, tmp_path, key):
    results = {}
    for name in ("old", "new"):
        tree = trees[name]
        campaign = tmp_path / "campaign"          # one artifact path for both, so even the manifest digest compares
        contract, receipt = _sweep_cells(tree, campaign)[key]
        root = Path(contract["runtimeArtifactRoot"])
        events = _pause_events("search") if key == "search-pause-effect" else ()
        helpers._seal_sweep_cell(tree, root, contract, receipt=receipt, docker_events=events)
        results[name] = tree["terminal"].validate_cell(root, contract)
        shutil.rmtree(campaign)
    assert results["old"]["candidateCellValid"] is True
    assert json.dumps(results["old"], sort_keys=True) == json.dumps(results["new"], sort_keys=True)
    assert "costExtraServicesCpuSeconds" not in results["new"]["system"]       # no extra scope in an earlier epoch


def test_the_sealed_cell_comparison_can_fail_a_planted_scope_change_is_seen(trees, tmp_path):
    """Planted: declare consul as a collected service of the sweep epoch; the sealed cells then differ."""
    new = trees["new"]
    contract, _ = _sweep_cells(new, tmp_path / "campaign")["no-fault"]
    root = Path(contract["runtimeArtifactRoot"])
    helpers._seal_sweep_cell(new, root, contract)                               # ten services collected
    runtime = new["terminal"].runtime_policy
    original = dict(runtime.COLLECTION_EXTRA_SERVICES)
    try:
        runtime.COLLECTION_EXTRA_SERVICES[SWEEP] = ("consul",)
        with pytest.raises(new["terminal"].TerminalError, match="application image provenance"):
            new["terminal"].validate_cell(root, contract)
    finally:
        runtime.COLLECTION_EXTRA_SERVICES.clear()
        runtime.COLLECTION_EXTRA_SERVICES.update(original)
    assert new["terminal"].validate_cell(root, contract)["candidateCellValid"] is True


def _drive(monkeypatch, tree, name: str, tmp_path: Path, run_id: str, **kwargs) -> dict:
    cell = load("hotel_offpath_exec_cell_%s_%s" % (name, abs(hash(run_id)) % 10**6),
                tree["root"] / "modules/hotel-reservation/execution/candidate_cell.py")
    artifact = tmp_path / name
    document = helpers._admission(cell.runtime, artifact, plan_sha256=sweep.EXPECTED_PLAN_SHA256,
                                  run_count=sweep.TOTAL_RUNS, wall=sweep.MAXIMUM_WALL_SECONDS)
    contract = next(row for row in cell.runtime.cell_contracts(document) if row["runId"] == run_id)
    with monkeypatch.context() as patch:
        calls = helpers._drive_run_cell(patch, cell, contract, document, artifact, real_cleanup=True, **kwargs)
    calls["_roots"] = (str(tree["root"]), str(artifact))
    return calls


def _normalised(calls: dict) -> dict:
    root, artifact = calls["_roots"]
    clean = lambda text: text.replace(artifact, "<artifact>").replace(root, "<tree>")      # noqa: E731
    commands = [[clean(arg) for arg in row["argv"] if "hotel_candidate_v4_" not in arg] for row in calls["commands"]]
    keep = ("execute", "collect", "tcp", "emissionWindowNs", "cpu", "samplerJoin", "files", "identitiesAsked",
            "cpuServices", "costServices", "tcpServices", "samplerServices", "imageServices")
    inject = {key: value for key, value in calls.get("inject", {}).items() if key != "startAfterBarrier"}
    return {"commands": commands, "inject": inject, **{key: calls.get(key) for key in keep}}


@pytest.mark.parametrize("run_id", [
    "no-fault-calibration-r0p05-b01-full-a01",
    "search-pause-effect-r0p05-b01-full-a01",
    "cpu-throttle-effect-r1-b01-full-a01",
])
def test_run_cell_issues_identical_commands_under_the_ca58974_and_the_current_runner(monkeypatch, trees, tmp_path, run_id):
    old = _normalised(_drive(monkeypatch, trees["old"], "old", tmp_path, run_id))
    new = _normalised(_drive(monkeypatch, trees["new"], "new", tmp_path, run_id))
    assert old == new
    unpause = next(cmd for cmd in new["commands"] if "unpause" in cmd)
    assert unpause[unpause.index("unpause"):] == ["unpause", "search", "reservation"]    # no consul in an earlier epoch
    logs = next(cmd for cmd in new["commands"] if "logs" in cmd)
    assert logs[-10:] == list(resources.APPLICATION_SERVICES) and "consul" not in logs
    assert new["cpuServices"] == sorted(resources.APPLICATION_SERVICES)


def test_the_command_comparison_can_fail_a_planted_scope_change_is_seen(monkeypatch, trees, tmp_path):
    """Planted: the sweep epoch declares consul as collected; the runner then asks for it and the argv differs."""
    run_id = "no-fault-calibration-r0p05-b01-full-a01"
    old = _normalised(_drive(monkeypatch, trees["old"], "old2", tmp_path, run_id))
    cell = load("hotel_offpath_exec_planted_cell", trees["new"]["root"] / "modules/hotel-reservation/execution/candidate_cell.py")
    cell.runtime.COLLECTION_EXTRA_SERVICES[SWEEP] = ("consul",)
    try:
        artifact = tmp_path / "planted"
        document = helpers._admission(cell.runtime, artifact, plan_sha256=sweep.EXPECTED_PLAN_SHA256,
                                      run_count=sweep.TOTAL_RUNS, wall=sweep.MAXIMUM_WALL_SECONDS)
        contract = next(row for row in cell.runtime.cell_contracts(document) if row["runId"] == run_id)
        with monkeypatch.context() as patch:
            calls = helpers._drive_run_cell(patch, cell, contract, document, artifact, real_cleanup=True,
                                            extra_services=("consul",))
        calls["_roots"] = (str(trees["new"]["root"]), str(artifact))
        assert _normalised(calls) != old
        assert "consul" in _normalised(calls)["cpuServices"]
    finally:
        cell.runtime.COLLECTION_EXTRA_SERVICES.pop(SWEEP, None)


def test_campaign_cleanup_unpauses_the_same_containers_as_ca58974_in_the_sweep_epoch(monkeypatch, trees, tmp_path):
    argvs = {}
    for name in ("old", "new"):
        tree = trees[name]
        cell = load("hotel_offpath_exec_cleanup_" + name,
                    tree["root"] / "modules/hotel-reservation/execution/candidate_cell.py")
        artifact = tmp_path / name
        (artifact).mkdir(parents=True)
        (artifact / "materialization-proof.json").write_text(json.dumps({
            "materializedSourceSha256": "2" * 64,
            "runtimeImages": {"consul": "c", "jaeger": "j", "memcached": "m", "mongo": "o", "builder": "b"}}))
        document = helpers._admission(cell.runtime, artifact, plan_sha256=sweep.EXPECTED_PLAN_SHA256,
                                      run_count=3, wall=sweep.MAXIMUM_WALL_SECONDS)
        recorded = []
        with monkeypatch.context() as patch:
            patch.setattr(cell, "_require_lease", lambda admission: None)
            patch.setattr(cell, "_bindings", lambda admission: (cell.ROOT, artifact))
            patch.setattr(cell, "_command", lambda arguments, **kw: recorded.append(
                [a.replace(str(artifact), "<artifact>").replace(str(tree["root"]), "<tree>") for a in arguments])
                      or helpers._Done("", 0))
            patch.setattr(cell.smoke, "project_resources",
                          lambda project: {"containers": [], "networks": [], "volumes": []})
            result = cell.cleanup_campaign(document)
        assert result["ownedResourcesRemaining"] == []
        argvs[name] = [[a for a in argv if "hotel_candidate_v4_" not in a] for argv in recorded]
    assert argvs["old"] == argvs["new"]
    assert [argv[argv.index("unpause"):] for argv in argvs["new"] if "unpause" in argv] == [
        ["unpause", "search", "reservation"]] * 3


# ------------------------------------------------------------------------------------ 5. the 3.9 grammar floor
@pytest.mark.parametrize("relative", [
    "faults/compose_pause.py", "faults/lmt_faults.py", "collectors/candidate_resources.py",
    "execution/candidate_cell.py", "execution/candidate_runtime.py", "validation/candidate_terminal.py",
    "witness/candidate_evidence.py",
])
def test_changed_executor_files_parse_with_the_39_grammar(relative):
    helpers.test_changed_target_side_files_parse_with_the_39_grammar(relative)
