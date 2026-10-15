"""hotel-traffic-sweep-v1: a second, parameterised Hotel epoch beside the frozen selected-v1.

Covers: the 64-cell plan is deterministic from its seed; offered per cell is rate x measurement; the frozen
epoch's digests, launcher and runner arguments are unchanged; the committed selector activates the sweep;
the validators accept a planted correct ledger at every rate and reject one with a request missing; the
plan-derived fault-truth bounds and phase floors; one fake-driven execution of the per-cell runner for each
epoch (the suite otherwise never executes run_cell); the 3.9 floor of every changed target-side file; and
protocol decision 25 (trace completeness: recorded inside the fault+drain window, max(1, 1 %) outside it,
the frozen epoch unchanged), starting from a synthetic copy of the relaunch-2 cell-15 incident.

The sweep is exercised in a copy of the module tree with execution/study-epoch.json written into it, which is
exactly what the target sees after the selector is committed; the worktree itself stays on the frozen epoch.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/hotel-reservation"
SWEEP = "hotel-traffic-sweep-v1"
RATES = (10.0, 1.0, 0.2, 0.05)
BARRIER = 1000.0
BARRIER_AT = datetime(2026, 10, 3, 1, 0, tzinfo=timezone.utc)

# Pinned at e4fd4c7 (the frozen epoch this change must leave alone).
FROZEN_DESCRIPTOR_SHA256 = "4e8c19b8210b0a593ab94ed309c24f9799ae4b3408409c254fc475af11530f5c"
FROZEN_PLAN_SHA256 = "189604cc901f53207e16fed8c924b66dc6ba96cb61c0a3e8f706689ab8a5b4af"
FROZEN_LAUNCHER_SHA256 = "e86e3cb34fd8cae2d09112672a952212dcdcde0ffd4caaacb495991165406c12"
FROZEN_CONTROLLER_KEYS = {
    "candidate-compiler", "candidate-runtime", "candidate-cell-runner", "candidate-terminal",
    "candidate-materializer", "candidate-workload", "candidate-resources", "candidate-witness",
    "request-emission-patch", "patch-manifest", "runtime-input-lock", "runtime-policy",
    "base-materializer", "base-smoke", "fault-adapter", "fault-adapter-lmt", "system-collector",
    "jaeger-collector", "jaeger-normalizer", "compose-overlay", "source-lock", "candidate-descriptor",
}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sweep = load("hotel_traffic_sweep_compiler_test", MODULE / "execution/candidate_sweep.py")
frozen_compiler = load("hotel_traffic_sweep_frozen_compiler_test", MODULE / "execution/candidate_pilot.py")
frozen_runtime = load("hotel_traffic_sweep_frozen_runtime_test", MODULE / "execution/candidate_runtime.py")
workload = load("hotel_traffic_sweep_workload_test", MODULE / "workload/candidate_search.py")


def _git_blob_sha256(relative: str) -> str:
    blob = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"e4fd4c7:{relative}"], capture_output=True, check=True,
    ).stdout
    return hashlib.sha256(blob).hexdigest()


# ------------------------------------------------------------------------------------------- the copied tree
@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    """A copy of the module tree with the selector committed: modules loaded from it run the sweep epoch."""
    root = tmp_path_factory.mktemp("sweep-tree")
    shutil.copytree(MODULE, root / "modules/hotel-reservation",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (root / "pipelines/campaigns").mkdir(parents=True)
    for path in (ROOT / "pipelines/campaigns").glob("hotel-*.json"):
        shutil.copyfile(path, root / "pipelines/campaigns" / path.name)
    (root / "modules/hotel-reservation/execution/study-epoch.json").write_text(
        json.dumps({"schemaVersion": 1, "studyEpoch": SWEEP}) + "\n"
    )
    module = root / "modules/hotel-reservation"
    loaded = {
        "root": root,
        "runtime": load("hotel_sweep_tree_runtime", module / "execution/candidate_runtime.py"),
        "terminal": load("hotel_sweep_tree_terminal", module / "validation/candidate_terminal.py"),
    }
    loaded["workload"] = loaded["terminal"].workload
    loaded["witness"] = loaded["terminal"].witness
    loaded["resources"] = loaded["terminal"].resources
    return loaded


def _admission(runtime, artifact_root: Path, *, plan_sha256: str, run_count: int, wall: int) -> dict:
    body = {
        "schemaVersion": 1, "kind": runtime.ADMISSION_KIND,
        "bindings": {
            "campaignId": "hotel-v1-20261003t010203z-deadbeef",
            "projectPrefix": "hotel_candidate_v4",
            "artifactRoot": str(artifact_root),
            "ports": {"frontend": 35005, "jaegerQuery": 36685},
            "transportId": "ssh-compose", "target": "fb14srv4",
            "leasePath": str(artifact_root.parent / ".lease"),
            "deadline": "2099-01-01T00:00:00Z",
            "compiledPlanCanonicalSha256": plan_sha256,
            "runCount": run_count, "maximumWallSeconds": wall, "cleanupReserveSeconds": 300,
            "cleanupActions": [
                "unpause-owned-fault-target-if-needed",
                "docker-compose-down-volumes-remove-orphans",
                "verify-zero-owned-containers-networks-volumes",
                "release-exact-campaign-lease-even-if-cleanup-fails",
            ],
            "foreignProject": None,
        },
        "runtimeAuthorized": True, "externalMutationAuthorized": True, "promotionAuthorized": False,
        "issuedAt": "2026-10-03T00:00:00Z",
    }
    return {**body, "admissionCanonicalSha256": runtime.canonical_sha256(body)}


def _sweep_contracts(tree, artifact_root: Path) -> list:
    runtime = tree["runtime"]
    document = _admission(
        runtime, artifact_root, plan_sha256=sweep.EXPECTED_PLAN_SHA256,
        run_count=sweep.TOTAL_RUNS, wall=sweep.MAXIMUM_WALL_SECONDS,
    )
    return document, runtime.cell_contracts(document)


# ------------------------------------------------------------------------------------------ 1. the sweep plan
def test_sweep_plan_is_64_cells_and_deterministic_from_its_recorded_seed(monkeypatch):
    descriptor = sweep.load_descriptor()
    assert sweep.canonical_sha256(descriptor) == sweep.EXPECTED_DESCRIPTOR_SHA256
    # The checked-in descriptor is the generator's output, byte for byte (regenerate, never hand-edit).
    assert sweep.DEFAULT_DESCRIPTOR.read_bytes() == sweep.descriptor_bytes()
    first, second = sweep.compile_plan(descriptor), sweep.compile_plan(copy.deepcopy(descriptor))
    assert first == second and first["planCanonicalSha256"] == sweep.EXPECTED_PLAN_SHA256
    assert descriptor["schedule"]["seed"] == sweep.SCHEDULE_SEED == 20261003
    cells = sweep.flatten_cells(first)
    assert first["runCount"] == len(cells) == len({cell["runId"] for cell in cells}) == 64
    canonical = [(regime, rate) for regime in sweep.REGIMES for rate in RATES]
    for block in first["blocks"]:
        pairs = [(cell["runKey"]["regime"], cell["runKey"]["requestsPerSecond"]) for cell in block["cells"]]
        assert sorted(pairs) == sorted(canonical)            # every (regime, rate) pair exactly once
        assert pairs != canonical                             # and not in declaration order
        assert [cell["position"] for cell in block["cells"]] == list(range(1, 17))
        assert {cell["runKey"]["posture"] for cell in block["cells"]} == {"full"}
    assert len({tuple(block["order"]) for block in first["blocks"]}) == 4   # blocks are shuffled apart
    # A different seed gives a different order: the order is the seed's, not an accident.
    monkeypatch.setattr(sweep, "SCHEDULE_SEED", 1)
    assert [row["regime"] for row in sweep.block_order(1)] != [
        cell["runKey"]["regime"] for cell in first["blocks"][0]["cells"]
    ]


def test_offered_is_rate_times_measurement_and_the_onset_phase_is_seeded_per_cell():
    plan = sweep.compile_plan(sweep.load_descriptor())
    by_rate: dict = {}
    for cell in sweep.flatten_cells(plan):
        timing = cell["timing"]
        rate = timing["requestsPerSecond"]
        assert timing["offered"] == round(rate * 180) == {10.0: 1800, 1.0: 180, 0.2: 36, 0.05: 9}[rate]
        assert timing["measurementSeconds"] == 180 and timing["faultHoldSeconds"] == 60
        assert timing["warmupSeconds"] == 30 and timing["warmupRequestsPerSecond"] == 10.0
        offset = timing["faultOnsetPhaseOffsetSeconds"]
        assert 0 <= offset < 1 / rate
        assert timing["faultOnsetSeconds"] == pytest.approx(60 + offset, abs=1e-6)
        assert timing["scoredWindowSeconds"] == [timing["faultOnsetSeconds"],
                                                 round(timing["faultOnsetSeconds"] + 60, 6)]
        assert timing["faultApplied"] is (cell["fault"] is not None)
        floors = timing["minimumWitnessedStartsByPhase"]
        if cell["fault"] is None:
            assert floors is None
        else:
            onset = timing["faultOnsetSeconds"]
            slots = [k / rate for k in range(timing["offered"])]
            post = [t for t in slots if t >= onset + 60 + sweep.POST_RECOVERY_ALLOWANCE_SECONDS]
            assert 1 <= floors["post-readiness"] <= len(post)
            assert 1 <= floors["pre"] <= len([t for t in slots if t < onset])
        by_rate.setdefault(rate, set()).add(offset)
    # 16 cells per rate, 16 distinct offsets: the phase is drawn per cell, not fixed by the plan.
    assert {rate: len(offsets) for rate, offsets in by_rate.items()} == {rate: 16 for rate in RATES}
    assert sweep.MAXIMUM_WALL_SECONDS == 21600 and sweep.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS == 21300
    assert sweep.MAXIMUM_WALL_SECONDS >= 64 * sweep.CELL_PERIOD_ESTIMATE_SECONDS + 900


def test_without_the_onset_offset_every_low_rate_onset_falls_on_a_scheduled_request(monkeypatch):
    """Why the offset exists: 60 s is a multiple of every planned inter-arrival."""
    monkeypatch.setattr(sweep, "ONSET_PHASE_OFFSET", "none")
    for rate in RATES:
        timing = sweep.cell_timing("search-pause-effect-r%s-b01-full-a01" % sweep.rate_token(rate),
                                   "search-pause-effect", rate)
        assert timing["faultOnsetSeconds"] == 60
        assert any(abs(k / rate - 60) < 1e-9 for k in range(timing["offered"]))


# ------------------------------------------------------------------------------ 2. the frozen epoch is intact
def test_frozen_epoch_digests_files_and_runtime_shape_are_unchanged(tmp_path):
    assert frozen_compiler.EXPECTED_DESCRIPTOR_SHA256 == FROZEN_DESCRIPTOR_SHA256
    assert frozen_compiler.EXPECTED_PLAN_SHA256 == FROZEN_PLAN_SHA256
    descriptor = frozen_compiler.load_descriptor()
    assert frozen_compiler.compile_plan(descriptor)["planCanonicalSha256"] == FROZEN_PLAN_SHA256
    for relative in (
        "modules/hotel-reservation/execution/candidate_pilot.py",
        "pipelines/campaigns/hotel-reservation-selected-v1.json",
        "modules/hotel-reservation/execution/runtime-policy.json",
    ):
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == _git_blob_sha256(relative)
    assert not (MODULE / "execution/study-epoch.json").exists()
    assert frozen_runtime.STUDY_EPOCH == "hotel-reservation-selected-v1"
    assert frozen_runtime.CELL_COUNT == 80
    assert (frozen_runtime.MAXIMUM_WALL_SECONDS, frozen_runtime.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS) == (
        18000, 17700)
    assert set(frozen_runtime.CONTROLLER_PATHS) == FROZEN_CONTROLLER_KEYS
    assert frozen_runtime.CONTROLLER_PATHS["candidate-compiler"].endswith("candidate_pilot.py")
    assert hashlib.sha256(frozen_runtime.REMOTE_DETACHED_LAUNCH.encode()).hexdigest() == FROZEN_LAUNCHER_SHA256
    document = _admission(frozen_runtime, tmp_path / "campaign", plan_sha256=FROZEN_PLAN_SHA256,
                          run_count=80, wall=18000)
    contracts = frozen_runtime.cell_contracts(document)
    assert len(contracts) == 80 and all("timing" not in row for row in contracts)
    timing = frozen_runtime.cell_timing(contracts[0])
    assert (timing["requestsPerSecond"], timing["measurementSeconds"], timing["offered"]) == (10, 120, 1200)
    assert (timing["faultOnsetSeconds"], timing["faultHoldSeconds"], timing["warmupSeconds"]) == (45, 15, 30)
    assert timing["tcpSnapshotOffsetsSeconds"] == {"pre-fault": 30, "during-fault": 52}
    assert (timing["jaegerQueryWindowSeconds"], timing["minimumSystemSamples"]) == (125, 24)
    assert timing["applicationLogTimestamps"] is False and timing["jaegerAllServicesRemainder"] is False


def test_frozen_run_ids_keep_the_frozen_workload_guards():
    compiled = FROZEN_PLAN_SHA256
    plan = workload.build_plan("net-delay-effect-b02-full-a01", compiled, BARRIER_AT, BARRIER,
                               created_at=BARRIER_AT - timedelta(minutes=1))
    assert (plan["rate"], plan["durationSeconds"], plan["offered"]) == (10.0, 120.0, 1200)
    with pytest.raises(workload.LedgerError, match="exactly 10/s"):
        workload.build_plan("net-delay-effect-b02-full-a01", compiled, BARRIER_AT, BARRIER, rate=1.0)
    with pytest.raises(workload.LedgerError, match="exactly 120s"):
        workload.build_plan("net-delay-effect-b02-full-a01", compiled, BARRIER_AT, BARRIER,
                            duration_seconds=180.0)


# ------------------------------------------------------------------------- 3. the committed selector activates
def test_the_committed_selector_activates_the_sweep_epoch_with_a_derived_budget(tree, tmp_path):
    runtime = tree["runtime"]
    assert runtime.STUDY_EPOCH == SWEEP and runtime.CELL_COUNT == 64
    assert (runtime.MAXIMUM_WALL_SECONDS, runtime.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS) == (21600, 21300)
    policy = runtime._validate_policy(runtime._json_file(runtime.POLICY, "policy"))
    frozen_policy = json.loads((MODULE / "execution/runtime-policy.json").read_text())
    changed = {key for key in policy if policy[key] != frozen_policy[key]}
    assert changed == {"studyEpoch", "maximumCells", "maximumWallSeconds", "minimumFirstMutationRemainingSeconds"}
    for name in ("protocol-gates", "study-epoch-selector", "frozen-compiler"):
        assert (tree["root"] / runtime.CONTROLLER_PATHS[name]).is_file()
    assert runtime.CONTROLLER_PATHS["candidate-compiler"].endswith("candidate_sweep.py")
    document, contracts = _sweep_contracts(tree, tmp_path / "campaign")
    assert len(contracts) == 64 and all(set(row["timing"]) == runtime.CELL_TIMING_KEYS for row in contracts)
    assert runtime.frozen_cell_contracts(document) == contracts
    assert [row["ordinal"] for row in contracts] == list(range(1, 65))
    for row in contracts:
        assert runtime.cell_timing(row) == row["timing"]
    planted = copy.deepcopy(contracts[5])
    planted["timing"]["offered"] += 1
    with pytest.raises(runtime.GateError, match="not the active compiled plan"):
        runtime.cell_timing(planted)
    launcher = runtime.REMOTE_DETACHED_LAUNCH
    compile(launcher, "sweep-launcher", "exec")
    assert 'binding.get("maximumWallSeconds")!=21600' in launcher
    assert "remaining < 21300 or remaining > 21605" in launcher and "17700" not in launcher
    runtime.validate_embedded_remote_programs()
    text = runtime.expected_gate_run_text({**document["bindings"], "frameworkCommit": "a" * 40,
                                           "readinessCaptureId": "x", "readinessObservedAt": "y",
                                           "transportUser": "root", "setupUser": "root",
                                           "executionUser": "fhuebscher", "executionUid": 1007,
                                           "executionGid": 1007, "dockerGid": 998})
    assert f"study={SWEEP} " in text and "cells=64 " in text and "wallSeconds=21600 " in text


def test_a_selector_naming_no_declared_epoch_refuses_to_load(tmp_path):
    root = tmp_path / "bad"
    shutil.copytree(MODULE, root / "modules/hotel-reservation",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (root / "pipelines/campaigns").mkdir(parents=True)
    for path in (ROOT / "pipelines/campaigns").glob("hotel-*.json"):
        shutil.copyfile(path, root / "pipelines/campaigns" / path.name)
    selector = root / "modules/hotel-reservation/execution/study-epoch.json"
    for value in ("hotel-reservation-selected-v1", "hotel-traffic-sweep-v2"):
        selector.write_text(json.dumps({"schemaVersion": 1, "studyEpoch": value}))
        with pytest.raises(Exception, match="names no declared non-frozen epoch"):
            load("hotel_sweep_bad_selector_runtime", root / "modules/hotel-reservation/execution/candidate_runtime.py")


# ------------------------------------------------------------------------------------------ 4. the workload
@pytest.mark.parametrize("rate", RATES)
def test_workload_preallocates_rate_times_measurement_and_refuses_another_rate(rate):
    run_id = "net-delay-effect-r%s-b03-full-a01" % sweep.rate_token(rate)
    plan = workload.build_plan(run_id, sweep.EXPECTED_PLAN_SHA256, BARRIER_AT, BARRIER, rate=rate,
                               duration_seconds=180.0, created_at=BARRIER_AT - timedelta(minutes=1))
    assert plan["offered"] == len(plan["opportunities"]) == round(rate * 180)
    assert workload.validate_plan(plan) == plan
    assert [row["scheduledMonotonicOffsetSeconds"] for row in plan["opportunities"][:2]] == [0.0, 1 / rate]
    with pytest.raises(workload.LedgerError, match="rate its run ID was compiled for"):
        workload.build_plan(run_id, sweep.EXPECTED_PLAN_SHA256, BARRIER_AT, BARRIER, rate=rate * 2,
                            duration_seconds=180.0, created_at=BARRIER_AT - timedelta(minutes=1))
    with pytest.raises(workload.LedgerError, match="positive integer number"):
        workload.build_plan(run_id, sweep.EXPECTED_PLAN_SHA256, BARRIER_AT, BARRIER, rate=rate,
                            duration_seconds=180.0 + 0.37 / rate, created_at=BARRIER_AT - timedelta(minutes=1))


# --------------------------------------------------------------------------- 5. sealed full-posture sweep cells
SHAPE = [
    ("frontend", "HTTP GET /hotels", None),
    ("search", "/search.Search/Nearby", 0),
    ("geo", "/geo.Geo/Nearby", 1),
    ("rate", "/rate.Rate/GetRates", 1),
    ("reservation", "/reservation.Reservation/CheckAvailability", 0),
    ("profile", "/profile.Profile/GetProfiles", 0),
]


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _ledger(work, plan: dict, *, failing=lambda offset: False) -> list:
    previous, rows = "0" * 64, []
    for index, opportunity in enumerate(plan["opportunities"]):
        offset = opportunity["scheduledMonotonicOffsetSeconds"]
        bad = failing(offset)
        result = {
            **opportunity,
            "actualStartMonotonic": BARRIER + offset + 0.001,
            "actualEndMonotonic": BARRIER + offset + (1.001 if bad else 0.02),
            "startedAt": opportunity["scheduledAt"], "endedAt": opportunity["scheduledAt"],
            "outcome": "transport-error" if bad else "completed",
            "statusCode": None if bad else 200,
            "error": "TimeoutError: timed out" if bad else None,
            "terminalSettled": True,
        }
        row = work._ledger_record(result, index, previous, plan)
        rows.append(row)
        previous = row["recordSha256"]
    return rows


def _raw_trace(index: int, token: str, start_us: int) -> dict:
    trace_id = "%016x" % index
    processes = {"p%d" % n: {"serviceName": service} for n, (service, _, _) in enumerate(SHAPE)}
    spans = []
    for n, (service, operation, parent) in enumerate(SHAPE):
        spans.append({
            "traceID": trace_id, "spanID": "%016x" % (n + 1), "operationName": operation,
            "references": [] if parent is None else [
                {"refType": "CHILD_OF", "traceID": trace_id, "spanID": "%016x" % (parent + 1)}],
            "startTime": start_us + n, "duration": 10, "processID": "p%d" % n,
            "tags": [{"key": "obsplacement.opaque_token", "type": "string", "value": token}] if parent is None else [],
        })
    return {"traceID": trace_id, "spans": spans, "processes": processes}


def _seal_sweep_cell(tree, root: Path, contract: dict, *, drop_last_request: bool = False,
                     plan_duration: float | None = None, receipt: dict | None = None,
                     drop_spans=lambda row: frozenset(), extra_services=(), docker_events=()) -> None:
    """``receipt`` seals a fault cell; ``drop_spans(row)`` names the services whose raw spans that request loses.

    ``extra_services`` are collected beside the ten application services in every collector file (hotel-offpath-v1:
    consul); ``docker_events(ids)`` returns the docker event rows to retain, given the service -> container id map."""
    work, witness, resources, terminal = tree["workload"], tree["witness"], tree["resources"], tree["terminal"]
    runtime = tree["runtime"]
    timing = contract["timing"]
    root.mkdir(parents=True)
    _write(root / "cell-contract.json", contract)
    if receipt is not None:
        _write(root / "fault-receipt.json", receipt)
    plan = work.build_plan(contract["runId"], contract["compiledPlanCanonicalSha256"], BARRIER_AT, BARRIER,
                           rate=timing["requestsPerSecond"],
                           duration_seconds=float(plan_duration or timing["measurementSeconds"]),
                           created_at=BARRIER_AT - timedelta(minutes=1))
    _write(root / "opportunity-plan.json", plan)
    rows = _ledger(work, plan)
    if drop_last_request:
        rows = rows[:-1]
    (root / "opportunity-ledger.jsonl").write_bytes(b"".join(work.canonical_bytes(row) + b"\n" for row in rows))
    validation = work.validate_ledger(plan, root / "opportunity-ledger.jsonl") if not drop_last_request else {}
    _write(root / "workload-reconciliation.json", {
        "schemaVersion": 1, "kind": "hotel-candidate-workload-reconciliation-v1",
        "planSha256": plan["planCanonicalSha256"],
        "ledgerSha256": hashlib.sha256((root / "opportunity-ledger.jsonl").read_bytes()).hexdigest(),
        "offered": len(rows), "terminalSettled": len(rows), "completed": len(rows), "failed": 0,
        "firstRecordSha256": rows[0]["recordSha256"], "lastRecordSha256": rows[-1]["recordSha256"],
        "validation": validation,
    })
    start_us = int(BARRIER_AT.timestamp() * 1_000_000)
    start_ns = start_us * 1000
    lines = []
    for index, row in enumerate(rows, 1):
        # docker compose logs --timestamps prefixes every line; both parsers locate their marker anywhere.
        stamp = "frontend-1  | 2026-10-03T01:00:%02d.123456789Z " % (index % 60)
        lines.append(stamp + "OBSPLACEMENT_WITNESS " + json.dumps({
            "schema": "hotel-application-request-witness-v1", "opaqueToken": row["opaqueToken"],
            "method": "GET", "routePattern": "/hotels", "statusCode": 200,
            "startedAtUnixNano": start_ns + index, "endedAtUnixNano": start_ns + index + 1,
        }, separators=(",", ":")))
        lines.append(stamp + resources.EMISSION_PREFIX + json.dumps({
            "schema": "hotel-source-emitted-span-v1", "service": "frontend", "traceId": "%016x" % index,
            "spanId": "%016x" % 1, "startedAtUnixNano": start_ns + 1000 + index,
            "endedAtUnixNano": start_ns + 2000 + index, "compactThriftSpanBytes": 120, "wireBytes": False,
        }, separators=(",", ":")))
    application_log = "\n".join(lines) + "\n"
    (root / "application.log").write_text(application_log)
    window_us = timing["jaegerQueryWindowSeconds"] * 1_000_000
    data = [_raw_trace(index, row["opaqueToken"], start_us + index * 1000) for index, row in enumerate(rows, 1)]
    for trace, row in zip(data, rows):
        dropped = {pid for pid, process in trace["processes"].items() if process["serviceName"] in drop_spans(row)}
        trace["spans"] = [span for span in trace["spans"] if span["processID"] not in dropped]
    raw = {
        "schemaVersion": 1, "collector": "jaeger-query-api-v1", "collectedAtEpoch": 1.0,
        "window": {"startUs": start_us, "endUs": start_us + window_us}, "limitPerService": 10000,
        "queries": [{"service": "frontend", "url": "http://jaeger/api/traces", "traceCount": len(data),
                     "response": {"data": data, "errors": None}}],
    }
    normalized = terminal.jaeger_normalizer.normalize(raw)
    capture = {"schemaVersion": 1, "kind": "hotel-jaeger-capture-terminal-v1", "queriesComplete": True,
               "collectorTailComplete": True, "backendReadyAtTerminal": True}
    _write(root / "jaeger-raw.json", raw)
    _write(root / "traces-normalized.json", normalized)
    _write(root / "capture-terminal.json", capture)
    _write(root / terminal.JAEGER_REMAINDER, {
        "schemaVersion": 1, "kind": "hotel-jaeger-all-services-remainder-v1", "window": raw["window"],
        "limitPerService": 10000, "frontendTraceCount": len(data),
        "queries": [{"service": s, "traceCount": len(data), "traces": []}
                    for s in terminal.APPLICATION_SERVICES if s != "frontend"],
    })
    if not drop_last_request:
        correlation = witness.correlate(
            plan, rows, application_log, normalized, posture="full", scenario=contract["fault"],
            fault_receipt=receipt, raw=raw, capture_terminal=capture,
            unsupported_postures=runtime.posture_ceiling()["unsupportedPostures"], timing=timing,
        )
        _write(root / "correlation.json", correlation)
    else:
        _write(root / "correlation.json", {})
    measurement = timing["measurementSeconds"]
    _write(root / "emissions.json", resources.parse_emissions(
        application_log, start_ns, start_ns + measurement * 1_000_000_000))
    scope = tuple(resources.APPLICATION_SERVICES) + tuple(extra_services)
    identities = {"%064x" % n: s for n, s in enumerate(scope, 1)}
    cpu_rows = [{"service": s, "containerId": c, "cpuPercent": 10.0 if s in resources.APPLICATION_SERVICES else 5.0}
                for c, s in identities.items()]
    _write(root / "cpu.json", {
        "schemaVersion": 1, "contract": resources.RESOURCE_CONTRACT, "project": contract["project"],
        "applicationServices": list(scope), "containerIdentities": identities,
        "windowStartMonotonic": BARRIER, "windowEndMonotonic": BARRIER + measurement, "intervalSeconds": 10.0,
        "samples": [{"capturedAtEpoch": BARRIER + t, "capturedAtMonotonic": BARRIER + t, "containers": cpu_rows,
                     "applicationCpuPercent": 100.0} for t in range(0, measurement + 1, 10)],
        "captureComplete": True, "applicationCpuSeconds": float(measurement),
    })
    services = sorted(identities.values())
    daemons = ("docker.service", "containerd.service")
    start_edge = {"label": "window-start", "at": "x", "monotonic": BARRIER + 0.01,
                  "containersUsageUsec": {s: 1_000_000 for s in services},
                  "daemonsUsageUsec": {u: 5_000_000 for u in daemons}}
    end_edge = {"label": "window-end", "at": "y", "monotonic": BARRIER + measurement + 0.02,
                "containersUsageUsec": {s: 3_500_000 for s in services},
                "daemonsUsageUsec": {u: 5_300_000 for u in daemons}}
    windows = end_edge["monotonic"] - start_edge["monotonic"]
    _write(root / "cost-cgroup.json", {
        "schemaVersion": 1, "kind": "hotel-lmt-cost-cgroup-v1", "start": start_edge, "end": end_edge,
        "windowSeconds": windows,
        "containersCpuSeconds": {s: 2.5 for s in services},
        "daemonsCpuSeconds": {u: (5_300_000 - 5_000_000) / 1e6 for u in daemons},
    })
    _write(root / "system-samples.json", {
        "schemaVersion": 1, "kind": "hotel-lmt-system-samples-v1", "intervalSeconds": 5.0,
        "samples": [{"monotonic": BARRIER + 5.0 * k, "at": "z", "services": {
            s: {"cpuUsageUsec": k, "memoryCurrent": 1, "rbytes": 0, "wbytes": 0, "psiCpuSomeTotalUsec": 0,
                "psiMemorySomeTotalUsec": 0, "psiIoSomeTotalUsec": None} for s in services}}
            for k in range(measurement // 5 + 1)],
    })
    _write(root / "tcp-snapshots.json", {
        "schemaVersion": 1, "kind": "hotel-lmt-tcp-snapshots-v1",
        "snapshots": [{"label": label, "at": "t", "monotonic": BARRIER + offset,
                       "services": {s: {"ips": [], "established": []} for s in services}}
                      for label, offset in timing["tcpSnapshotOffsetsSeconds"].items()],
    })
    event_rows = docker_events({s: c for c, s in identities.items()}) if callable(docker_events) else []
    (root / "docker-events.jsonl").write_text("".join(json.dumps(row) + "\n" for row in event_rows))
    _write(root / "docker-events.json", {"schemaVersion": 1, "kind": "hotel-lmt-docker-events-v1",
                                         "startedAt": "a", "stoppedAt": "b", "rows": len(event_rows), "stderr": ""})
    _write(root / "posture-proof.json", {
        "schemaVersion": 3, "requested": "full",
        "expectedSampleRatio": {s: "1" for s in terminal.APPLICATION_SERVICES},
        "services": {s: "1" for s in terminal.APPLICATION_SERVICES},
        "tracedServices": sorted(terminal.APPLICATION_SERVICES), "logLevel": "info", "metricSampler": True,
        "sourceWorkDisabled": False, "classification": "logs-info-sampler-on-tracer-full-sampling",
    })
    source_sha, image_id = "2" * 64, "sha256:" + "3" * 64
    module = tree["root"] / "modules/hotel-reservation"
    lock = json.loads((module / "deployment/runtime-inputs.lock.json").read_text())
    inputs_sha = hashlib.sha256((module / "deployment/runtime-inputs.lock.json").read_bytes()).hexdigest()
    _write(root / "source-proof.json", {
        "upstreamCommit": "6ecb09706140f8730b5385c08f1386c654c3c526", "sourceCheckoutClean": True,
        "candidatePatchId": "hotel-lmt-pilot-witness-and-log-fatal-v1",
        "candidatePatchSha256": hashlib.sha256(
            (module / "witness/hotel-candidate-witness.patch").read_bytes()).hexdigest(),
        "patchManifestSha256": hashlib.sha256((module / "witness/patch-manifest.json").read_bytes()).hexdigest(),
        "runtimeInputsSha256": inputs_sha, "runtimeImages": lock["images"], "materializedSourceSha256": source_sha,
    })
    reference = "obsplacement/hotel-reservation-candidate:" + source_sha[:16]
    _write(root / "application-build-proof.json", {
        "schemaVersion": 1, "imageReference": reference, "imageId": image_id,
        "materializedSourceSha256": source_sha, "builderReference": lock["images"]["builder"],
        "runtimeInputsSha256": inputs_sha,
    })
    _write(root / "images.json", {
        "schemaVersion": 1, "project": contract["project"], "materializedSourceSha256": source_sha,
        "applicationImageId": image_id, "applicationImageReference": reference, "runtimeInputsSha256": inputs_sha,
        # An extra collected service (consul) runs its own pinned image, so its image ID is not the application's.
        "containers": [{"service": s, "containerId": "%064x" % n, "project": contract["project"],
                        "imageId": image_id if s in resources.APPLICATION_SERVICES else "sha256:" + "4" * 64}
                       for n, s in enumerate(scope, 1)],
    })
    compose = {}
    for service in terminal.COMPOSE_SERVICES:
        if service in terminal.APPLICATION_SERVICES:
            environment = {"JAEGER_SAMPLE_RATIO": "1", "JAEGER_DISABLED": "false", "TLS": "0", "GC": "100",
                           "LOG_LEVEL": "info"}
            if service in {"review", "attractions"}:
                environment["MEMC_TIMEOUT"] = "2"
            compose[service] = {"image": reference, "environment": environment}
        elif service in ("consul", "jaeger"):
            compose[service] = {"image": lock["images"][service]}
        else:
            compose[service] = {"image": lock["images"]["memcached" if service.startswith("memcached-") else "mongo"]}
    compose["frontend"]["ports"] = [{"target": 5000, "published": "35005", "host_ip": "127.0.0.1", "protocol": "tcp"}]
    compose["jaeger"]["ports"] = [{"target": 16686, "published": "36685", "host_ip": "127.0.0.1", "protocol": "tcp"}]
    _write(root / "compose-rendered.yml", {"services": compose})
    snapshot = {"capturedAt": "c", "loadAverage": [1.0, 1.0, 1.0], "foreignProject": None, "foreignRows": []}
    _write(root / "nuisance.json", {
        "schemaVersion": 2, "kind": "hotel-srv4-cell-nuisance-v2", "factors": list(runtime.NUISANCE_FACTORS),
        "hostCondition": runtime.HOST_CONDITION_ID, "poolingBoundary": runtime.POOLING_BOUNDARY,
        "notPoolableWith": runtime.not_poolable_with(), "before": snapshot, "after": snapshot,
        "foreignMutationActions": [], "absoluteCostOrLatencyCanonical": False,
    })
    _write(root / "cell-cleanup.json", {
        "schemaVersion": 1, "kind": "hotel-candidate-cell-cleanup-v1", "project": contract["project"],
        "unpauseAttempted": True, "composeDownReturnCode": 0,
        "ownedResourcesRemaining": {"containers": [], "networks": [], "volumes": []},
        "foreignResourcesMutated": False, "artifactDeletionAttempted": False,
    })
    terminal.write_manifest(root)


def _calibration_contract(tree, campaign: Path, rate: float) -> dict:
    _, contracts = _sweep_contracts(tree, campaign)
    token = sweep.rate_token(rate)
    return next(row for row in contracts if row["runId"] == "no-fault-calibration-r%s-b01-full-a01" % token)


@pytest.mark.parametrize("rate", RATES)
def test_validator_accepts_a_planted_correct_ledger_at_every_rate(tree, tmp_path, rate):
    contract = _calibration_contract(tree, tmp_path / "campaign", rate)
    root = Path(contract["runtimeArtifactRoot"])
    _seal_sweep_cell(tree, root, contract)
    result = tree["terminal"].validate_cell(root, contract)
    assert result["candidateCellValid"] is True
    assert result["opportunities"]["offered"] == round(rate * 180)
    gates = {row["gate"]: row["verdict"] for row in result["protocolGates"]["verdicts"]}
    assert result["protocolGates"]["blocking"] == ["G1", "G2", "G4"]
    assert {gate: gates[gate] for gate in ("G1", "G2", "G4")} == {"G1": "pass", "G2": "pass", "G4": "pass"}
    assert result["protocolGates"]["canFire"] is True
    assert result["jaegerAllServicesRemainder"]["remainderTraces"] == 0
    assert result["system"]["systemSamples"] == 37


@pytest.mark.parametrize("rate", RATES)
def test_validator_rejects_a_ledger_with_one_request_missing(tree, tmp_path, rate):
    contract = _calibration_contract(tree, tmp_path / "campaign", rate)
    root = Path(contract["runtimeArtifactRoot"])
    _seal_sweep_cell(tree, root, contract, drop_last_request=True)
    with pytest.raises(ValueError, match="row count differs from offered denominator"):
        tree["terminal"].validate_cell(root, contract)
    # The shared gate catches the same loss on its own: offered != plan.offered.
    plan = json.loads((root / "opportunity-plan.json").read_text())
    rows = [json.loads(line) for line in (root / "opportunity-ledger.jsonl").read_text().splitlines()]
    with pytest.raises(tree["terminal"].TerminalError, match="G4"):
        tree["terminal"].protocol_gate_record(contract, contract["timing"], plan, rows, None)


def test_validator_rejects_an_opportunity_plan_that_is_not_the_cells_compiled_timing(tree, tmp_path):
    """The workload accepts any integral duration for a sweep run ID; the terminal binds it to the plan."""
    contract = _calibration_contract(tree, tmp_path / "campaign", 1.0)
    root = Path(contract["runtimeArtifactRoot"])
    _seal_sweep_cell(tree, root, contract, plan_duration=120.0)
    with pytest.raises(tree["terminal"].TerminalError, match="differs from the cell's compiled timing"):
        tree["terminal"].validate_cell(root, contract)


def test_validator_rejects_a_contract_carrying_its_own_timing(tree, tmp_path):
    contract = _calibration_contract(tree, tmp_path / "campaign", 1.0)
    root = Path(contract["runtimeArtifactRoot"])
    planted = copy.deepcopy(contract)
    planted["timing"]["measurementSeconds"] = 120          # a retained contract cannot bring its own numbers
    root.mkdir(parents=True)
    _write(root / "cell-contract.json", planted)
    with pytest.raises(tree["terminal"].TerminalError, match="timing"):
        tree["terminal"].validate_cell(root, None)


# --------------------------------------------------------------------- 6. fault cells: F1, G1, G2 and phase floors
def _fault_cell(tree, campaign: Path, regime: str, rate: float, block: int = 2):
    _, contracts = _sweep_contracts(tree, campaign)
    contract = next(row for row in contracts
                    if row["runId"] == "%s-r%s-b%02d-full-a01" % (regime, sweep.rate_token(rate), block))
    timing = contract["timing"]
    plan = tree["workload"].build_plan(contract["runId"], contract["compiledPlanCanonicalSha256"], BARRIER_AT,
                                       BARRIER, rate=rate, duration_seconds=180.0,
                                       created_at=BARRIER_AT - timedelta(minutes=1))
    onset, hold = timing["faultOnsetSeconds"], timing["faultHoldSeconds"]
    pause = contract["fault"] == "search-pause"
    started = BARRIER + onset + 0.18                     # measured onset lateness <= 0.224 s (sel1, lmt2)
    failing = (lambda t: onset <= t <= onset + hold) if pause else (lambda t: False)
    rows = _ledger(tree["workload"], plan, failing=failing)
    common = {
        "schemaVersion": 1, "scenario": contract["fault"], "targetService": sweep.frozen.FAULT_TARGETS[contract["fault"]],
        "scheduledAtSeconds": onset, "startedAt": "2026-10-03T01:01:00Z", "endedAt": "2026-10-03T01:02:01Z",
        "manifested": True, "recovered": True, "successful": True, "preRouteAvailable": True,
        # Real adapters: pause holds from the stamp (compose_pause.py), degradation from applied (lmt_faults.py).
        "startedMonotonic": started, "appliedMonotonic": started + 0.27,
        "revertingMonotonic": started + hold if pause else started + 0.27 + hold,
        "readyAtMonotonic": started + 0.27 + hold + 0.4, "endedMonotonic": started + 0.27 + hold + 0.5,
        "error": None,
        # Probe stamps (sweep timing probeStamps): the pre-probe ends before the stamp, the during-probe starts
        # at applied.
        "probes": [{"phase": "pre", "startMonotonic": started - 0.05, "endMonotonic": started - 0.01, "available": True},
                   {"phase": "during", "startMonotonic": started + 0.27, "endMonotonic": started + 0.37,
                    "available": not pause}],
    }
    if pause:
        receipt = {**common, "faultKind": "pause", "requestedOutageSeconds": hold, "outageObserved": True,
                   "preState": {"running": True, "paused": False}, "duringState": {"running": True, "paused": True},
                   "recoveryState": {"running": True, "paused": False}, "unpausedAtMonotonic": started + hold + 0.1,
                   "actualOutageSeconds": hold + 0.1,
                   "commands": [{"action": a, "returnCode": 0, "stdout": "", "stderr": ""} for a in ("pause", "unpause")]}
    else:
        receipt = {**common, "faultKind": "degradation", "requestedHoldSeconds": hold, "reverted": True,
                   "preClean": True, "routeAvailableDuring": True, "revertedAtMonotonic": started + 0.27 + hold + 0.1,
                   "actualHoldSeconds": float(hold),
                   "commands": [{"action": a, "returnCode": 0, "stdout": "", "stderr": ""} for a in ("apply", "revert")]}
    return contract, plan, rows, receipt


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("regime", ["search-pause-effect", "cpu-throttle-effect", "net-delay-effect"])
def test_fault_cell_passes_f1_g1_g2_g4_and_the_plan_derived_fault_truth(tree, tmp_path, regime, rate):
    contract, plan, rows, receipt = _fault_cell(tree, tmp_path / "c", regime, rate)
    witness, terminal = tree["witness"], tree["terminal"]
    truth = witness.validate_fault_receipt(receipt, contract["fault"], barrier_monotonic=BARRIER,
                                           timing=contract["timing"])
    assert truth["state"] == "supported"
    record = terminal.protocol_gate_record(contract, contract["timing"], plan, rows, receipt)
    verdicts = {row["gate"]: row["verdict"] for row in record["verdicts"]}
    assert record["blocking"] == ["F1", "G1", "G2", "G4"]
    assert all(verdicts[gate] == "pass" for gate in record["blocking"])
    # The frozen 45 s schedule is not this cell's schedule.
    with pytest.raises(witness.WitnessError):
        witness.validate_fault_receipt(receipt, contract["fault"], barrier_monotonic=BARRIER)


@pytest.mark.parametrize("rate", RATES)
def test_fault_truth_is_bounded_by_the_scheduled_command(tree, tmp_path, rate):
    """F-ADH-085: the onset stamp precedes the command and lies in [onset - 0.05, onset + 2] s."""
    contract, plan, rows, receipt = _fault_cell(tree, tmp_path / "c", "net-delay-effect", rate)
    witness, terminal, timing = tree["witness"], tree["terminal"], contract["timing"]
    stamps = ("startedMonotonic", "appliedMonotonic", "revertingMonotonic", "revertedAtMonotonic",
              "readyAtMonotonic", "endedMonotonic")

    def shifted(delta):
        return dict(receipt, **{key: receipt[key] + delta for key in stamps})

    witness.validate_fault_receipt(shifted(1.8), contract["fault"], barrier_monotonic=BARRIER, timing=timing)
    for delta in (-0.24, 1.83):     # onset stamp 0.06 s early / 2.01 s late against the schedule
        planted = shifted(delta)
        with pytest.raises(witness.WitnessError, match="onset differs"):
            witness.validate_fault_receipt(planted, contract["fault"], barrier_monotonic=BARRIER, timing=timing)
    # An onset stamped after the command returned (a post-command probe) breaks the ordering.
    planted = dict(receipt, startedMonotonic=receipt["appliedMonotonic"] + 0.01)
    with pytest.raises(witness.WitnessError, match="monotonic truth"):
        witness.validate_fault_receipt(planted, contract["fault"], barrier_monotonic=BARRIER, timing=timing)
    # F1 refuses an onset more than ONSET_TOLERANCE_S late even where the witness bound (2 s) admits it.
    late = shifted(1.32)            # 1.5 s late
    with pytest.raises(terminal.TerminalError, match="F1"):
        terminal.protocol_gate_record(contract, timing, plan, rows, late)


def test_g2_blocks_a_cell_that_was_failing_before_the_fault(tree, tmp_path):
    contract, plan, _, receipt = _fault_cell(tree, tmp_path / "c", "cpu-throttle-effect", 0.05)
    rows = _ledger(tree["workload"], plan, failing=lambda t: t == 20.0)
    with pytest.raises(tree["terminal"].TerminalError, match="G2"):
        tree["terminal"].protocol_gate_record(contract, contract["timing"], plan, rows, receipt)


def test_witness_phase_floors_come_from_the_plan_not_the_frozen_100(tree, tmp_path):
    contract, plan, rows, receipt = _fault_cell(tree, tmp_path / "c", "cpu-throttle-effect", 0.05)
    witness = tree["witness"]
    data = [_raw_trace(index, row["opaqueToken"], 1) for index, row in enumerate(rows, 1)]
    raw = {"schemaVersion": 1, "collector": "jaeger-query-api-v1", "window": {"startUs": 1, "endUs": 2},
           "limitPerService": 10000, "queries": [{"service": "frontend", "traceCount": len(data),
                                                   "response": {"data": data, "errors": None}}]}
    normalized = tree["terminal"].jaeger_normalizer.normalize(raw)

    def log(keep):
        return "\n".join("OBSPLACEMENT_WITNESS " + json.dumps({
            "schema": "hotel-application-request-witness-v1", "opaqueToken": row["opaqueToken"], "method": "GET",
            "routePattern": "/hotels", "statusCode": 200, "startedAtUnixNano": 1, "endedAtUnixNano": 2,
        }, separators=(",", ":")) for row in rows if keep(row)) + "\n"

    kwargs = dict(posture="full", scenario=contract["fault"], fault_receipt=receipt, raw=raw, capture_terminal={},
                  unsupported_postures=tree["runtime"].posture_ceiling()["unsupportedPostures"])
    witnessed = {row["opaqueToken"] for row in rows}
    planted = copy.deepcopy(normalized)
    planted["events"] = [e for e in normalized["events"]
                         if e["tags"].get("obsplacement.opaque_token", "x") in witnessed or e["parentSpanId"]]
    result = witness.correlate(plan, rows, log(lambda row: True), planted, timing=contract["timing"], **kwargs)
    assert result["phaseExecutedCounts"]["during"] >= contract["timing"]["minimumWitnessedStartsByPhase"]["during"]
    # Without the cell's timing the frozen 100-per-phase rule applies and nine requests can never meet it.
    with pytest.raises(witness.WitnessError):
        witness.correlate(plan, rows, log(lambda row: True), planted, **kwargs)
    # Lose every post-readiness witness: the plan-derived floor blocks.
    ready = receipt["readyAtMonotonic"] + 1.0
    late = {row["opaqueToken"] for row in rows if row["actualStartMonotonic"] >= ready}
    thinned = copy.deepcopy(normalized)
    trace_of = {e["tags"].get("obsplacement.opaque_token"): e["traceId"] for e in normalized["events"]
                if e["parentSpanId"] is None}
    dropped = {trace_of[token] for token in late}
    thinned["events"] = [e for e in normalized["events"] if e["traceId"] not in dropped]
    with pytest.raises(witness.WitnessError, match="post-readiness"):
        witness.correlate(plan, rows, log(lambda row: row["opaqueToken"] not in late), thinned,
                          timing=contract["timing"], **kwargs)


# ------------------------------------------------------------- 7. one fake-driven execution of the cell runner
class _Done:
    def __init__(self, stdout: str = "", returncode: int = 0):
        self.stdout, self.stderr, self.returncode = stdout, "", returncode


def _drive_run_cell(monkeypatch, cell, contract: dict, admission: dict, artifact: Path, *,
                    extra_services=(), real_cleanup: bool = False) -> dict:
    """Execute candidate_cell.run_cell with every host action faked and every argument recorded.

    ``extra_services`` exist as containers beside the ten application services (hotel-offpath-v1: consul); the
    faked ``_container_identities`` answers for exactly the services it is asked about, so a scope the runner
    does not ask for is not collected.  ``real_cleanup`` runs the real ``_owned_cleanup`` against the faked shell."""
    calls: dict = {"commands": [], "collect": [], "tcp": []}
    (artifact / "runs").mkdir(parents=True)
    (artifact / "materialization-proof.json").write_text(json.dumps({
        "materializedSourceSha256": "2" * 64,
        "runtimeImages": {"consul": "c", "jaeger": "j", "memcached": "m", "mongo": "o", "builder": "b"},
    }))
    (artifact / "application-build-proof.json").write_text(json.dumps({"imageId": "sha256:" + "3" * 64}))
    everyone = {"%064x" % n: s for n, s in enumerate(tuple(cell.APPLICATION_SERVICES) + tuple(extra_services), 1)}

    def container_identities(source, project, environment, services=cell.APPLICATION_SERVICES):
        calls["identitiesAsked"] = list(services)
        return {cid: service for cid, service in everyone.items() if service in services}

    def command(arguments, *, environment=None, timeout=600, check=True, binary=False):
        calls["commands"].append({"argv": list(arguments), "timeout": timeout, "binary": binary})
        if binary:
            # A stray non-UTF-8 byte (0xbf, as in sweep1 cell 26) must not lose the cell.
            done = _Done(b"frontend-1  | \xbf partial line\n")
            done.stderr = b""
            return done
        return _Done("{}" if "config" in arguments else "")

    class Events:
        def __init__(self, project, output):
            output.write_text("")

        def stop(self):
            return {"rows": 0}

    class Sampler:
        error = None

        def __init__(self, identities, start, end):
            calls["sampler"] = (start, end)
            calls["samplerServices"] = sorted(identities.values())

        def start(self):
            pass

        def join(self, timeout=None):
            calls["samplerJoin"] = timeout

        def is_alive(self):
            return False

        def document(self):
            return {}

    def execute_plan(plan, base_url, ledger_path, *, concurrency, timeout):
        calls["execute"] = {"concurrency": concurrency, "timeout": timeout, "offered": plan["offered"],
                            "rate": plan["rate"], "duration": plan["durationSeconds"]}
        return {}

    def inject(source, project, scenario, fault_at, hold, probe_url, output, cancel, *, env,
               scheduled_at_seconds, start_at_monotonic, record_probes=False):
        calls["inject"] = {"scenario": scenario, "faultAt": fault_at, "hold": hold, "scheduled": scheduled_at_seconds,
                           "recordProbes": record_probes,
                           "startAfterBarrier": start_at_monotonic}
        return {"receipt": True}

    def collect(url, services, start_us, end_us, limit=10000, timeout=30.0):
        calls["collect"].append({"services": list(services), "windowUs": end_us - start_us})
        return {"schemaVersion": 1, "collector": "jaeger-query-api-v1", "collectedAtEpoch": 1.0,
                "window": {"startUs": start_us, "endUs": end_us}, "limitPerService": limit,
                "queries": [{"service": services[0], "url": "u", "traceCount": 0,
                             "response": {"data": [], "errors": None}}]}

    def correlate(*args, **kwargs):
        calls["correlate"] = kwargs
        return {}

    def parse_emissions(text, start_ns, end_ns):
        calls["emissionWindowNs"] = end_ns - start_ns
        return {}

    def collect_cpu(project, identities, start, end):
        calls["cpu"] = end - start
        calls["cpuServices"] = sorted(identities.values())
        return {}

    def tcp_snapshot(identities, label):
        calls["tcp"].append(label)
        calls["tcpServices"] = sorted(identities.values())
        return {}

    def cost_edges(identities, label):
        calls["costServices"] = sorted(identities.values())
        return {}

    def image_receipt(source, project, environment, proof, build, services=cell.APPLICATION_SERVICES):
        calls["imageServices"] = list(services)
        return {}

    monkeypatch.setattr(cell, "_require_lease", lambda admission: None)
    monkeypatch.setattr(cell, "_deadline", lambda admission, reserve=300: None)
    monkeypatch.setattr(cell, "_bindings", lambda admission: (cell.ROOT, artifact))
    monkeypatch.setattr(cell, "_nuisance_snapshot", lambda: {"loadAverage": [0, 0, 0]})
    monkeypatch.setattr(cell, "_boundary_clean", lambda project: (True, 0.0))
    monkeypatch.setattr(cell, "_command", command)
    monkeypatch.setattr(cell, "_validate_rendered_compose", lambda *a: None)
    monkeypatch.setattr(cell, "_container_identities", container_identities)
    monkeypatch.setattr(cell, "_image_receipt", image_receipt)
    monkeypatch.setattr(cell, "_posture_receipt", lambda *a: {})
    if real_cleanup:
        monkeypatch.setattr(cell.smoke, "project_resources",
                            lambda project: {"containers": [], "networks": [], "volumes": []})
    else:
        monkeypatch.setattr(cell, "_owned_cleanup",
                            lambda *a: {"composeDownReturnCode": 0, "ownedResourcesRemaining": {}})
    monkeypatch.setattr(cell.smoke, "wait_ready", lambda url, timeout=300: None)
    monkeypatch.setattr(cell.smoke, "image_receipt", lambda project: {})
    monkeypatch.setattr(cell.smoke, "validate_published_ports", lambda *a: None)
    monkeypatch.setattr(cell.smoke, "request_ok", lambda url: True)
    monkeypatch.setattr(cell.system, "EventStream", Events)
    monkeypatch.setattr(cell.system, "SystemSampler", Sampler)
    monkeypatch.setattr(cell.system, "cost_edges", cost_edges)
    monkeypatch.setattr(cell.system, "cost_document", lambda a, b: {})
    monkeypatch.setattr(cell.system, "tcp_snapshot", tcp_snapshot)
    monkeypatch.setattr(cell.resources, "collect_cpu", collect_cpu)
    monkeypatch.setattr(cell.resources, "parse_emissions", parse_emissions)
    monkeypatch.setattr(cell.workload, "execute_plan", execute_plan)
    monkeypatch.setattr(cell.faults, "inject", inject)
    monkeypatch.setattr(cell.collector, "collect", collect)
    monkeypatch.setattr(cell.witness, "correlate", correlate)
    monkeypatch.setattr(cell.witness, "ledger_rows", lambda path: [])
    monkeypatch.setattr(cell.terminal, "write_manifest", lambda root: None)
    monkeypatch.setattr(cell.terminal, "validate_cell", lambda root, contract: {"candidateCellValid": True})
    monkeypatch.setattr(cell.time, "sleep", lambda seconds: None)
    assert cell.run_cell(admission, contract) == {"candidateCellValid": True}
    run_root = Path(contract["runtimeArtifactRoot"])
    calls["plan"] = json.loads((run_root / "opportunity-plan.json").read_text())
    calls["files"] = sorted(path.name for path in run_root.iterdir())
    return calls


def _warmup(calls: dict) -> dict:
    row = next(row for row in calls["commands"] if row["argv"][1].endswith("fixed_search.py"))
    argv = row["argv"]
    return {flag: argv[argv.index(flag) + 1] for flag in ("--rate", "--duration", "--concurrency")} | {
        "timeout": row["timeout"]}


def _logs_argv(calls: dict) -> list:
    return next(row["argv"] for row in calls["commands"] if "logs" in row["argv"])


def test_run_cell_passes_the_frozen_epochs_literals_unchanged(monkeypatch, tmp_path):
    cell = load("hotel_traffic_sweep_frozen_cell_test", MODULE / "execution/candidate_cell.py")
    artifact = tmp_path / "campaign"
    document = _admission(cell.runtime, artifact, plan_sha256=FROZEN_PLAN_SHA256, run_count=80, wall=18000)
    contract = next(row for row in cell.runtime.cell_contracts(document)
                    if row["runId"] == "search-pause-effect-b01-full-a01")
    calls = _drive_run_cell(monkeypatch, cell, contract, document, artifact)
    assert _warmup(calls) == {"--rate": "10", "--duration": "30", "--concurrency": "16", "timeout": 90}
    assert calls["execute"] == {"concurrency": 16, "timeout": 1, "offered": 1200, "rate": 10.0, "duration": 120.0}
    assert calls["inject"]["faultAt"] == 45 and calls["inject"]["hold"] == 15
    assert calls["inject"]["recordProbes"] is False
    assert calls["inject"]["scheduled"] == 45
    assert calls["inject"]["startAfterBarrier"] - calls["plan"]["barrierMonotonic"] == pytest.approx(45)
    assert calls["collect"] == [{"services": ["frontend"], "windowUs": 125_000_000}]
    assert calls["emissionWindowNs"] == 120_000_000_000 and calls["cpu"] == pytest.approx(120)
    assert calls["tcp"] == ["pre-fault", "during-fault"]
    assert "--timestamps" not in _logs_argv(calls)
    assert calls["correlate"]["timing"] is None
    assert "jaeger-raw-remainder.json" not in calls["files"]


def test_run_cell_reads_every_sweep_value_from_the_cell_timing(monkeypatch, tree, tmp_path):
    cell = load("hotel_traffic_sweep_tree_cell_test", tree["root"] / "modules/hotel-reservation/execution/candidate_cell.py")
    artifact = tmp_path / "campaign"
    document, contracts = _sweep_contracts(tree, artifact)
    document = _admission(cell.runtime, artifact, plan_sha256=sweep.EXPECTED_PLAN_SHA256, run_count=64,
                          wall=sweep.MAXIMUM_WALL_SECONDS)
    contract = next(row for row in cell.runtime.cell_contracts(document)
                    if row["runId"] == "search-pause-effect-r0p05-b01-full-a01")
    timing = contract["timing"]
    calls = _drive_run_cell(monkeypatch, cell, contract, document, artifact)
    assert _warmup(calls) == {"--rate": "10", "--duration": "30", "--concurrency": "16", "timeout": 90.0}
    assert calls["execute"] == {"concurrency": 16, "timeout": 1.0, "offered": 9, "rate": 0.05, "duration": 180.0}
    assert calls["inject"]["faultAt"] == calls["inject"]["scheduled"] == timing["faultOnsetSeconds"]
    assert calls["inject"]["hold"] == 60 and timing["faultOnsetSeconds"] != 60
    assert calls["inject"]["recordProbes"] is True
    assert calls["inject"]["startAfterBarrier"] - calls["plan"]["barrierMonotonic"] == pytest.approx(
        timing["faultOnsetSeconds"])
    assert calls["collect"][0] == {"services": ["frontend"], "windowUs": 185_000_000}
    assert [row["services"] for row in calls["collect"][1:]] == [
        [s] for s in cell.APPLICATION_SERVICES if s != "frontend"]
    assert calls["emissionWindowNs"] == 180_000_000_000 and calls["cpu"] == pytest.approx(180)
    assert calls["samplerJoin"] == 30
    assert "--timestamps" in _logs_argv(calls)
    # Raw bytes in, run completes: the fake log carries a stray 0xbf (sweep1 attempt 2, cell 26).
    assert next(row["binary"] for row in calls["commands"] if "logs" in row["argv"]) is True
    assert calls["correlate"]["timing"] == timing
    assert "jaeger-raw-remainder.json" in calls["files"]


# ---------------------------------------------------------------------------------- 8. the 3.9 floor and vendoring
CHANGED_TARGET_FILES = (
    "execution/candidate_sweep.py", "execution/candidate_runtime.py", "execution/candidate_cell.py",
    "validation/candidate_terminal.py", "validation/protocol_gates.py", "witness/candidate_evidence.py",
    "workload/candidate_search.py",
)


@pytest.mark.parametrize("relative", CHANGED_TARGET_FILES)
def test_changed_target_side_files_parse_with_the_39_grammar(relative):
    source = (MODULE / relative).read_text()
    tree_ = ast.parse(source, feature_version=(3, 9))
    lazy = any(isinstance(node, ast.ImportFrom) and node.module == "__future__"
               and any(alias.name == "annotations" for alias in node.names) for node in tree_.body)
    for node in ast.walk(tree_):
        # PEP 604 outside an annotation is evaluated on 3.9 even under the __future__ import.
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("isinstance", "issubclass"):
            assert not any(isinstance(arg, ast.BinOp) for arg in node.args), relative
        if not lazy and isinstance(node, (ast.arg, ast.AnnAssign)) and node.annotation is not None:
            assert not any(isinstance(n, ast.BinOp) for n in ast.walk(node.annotation)), relative
        if not lazy and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
            assert not any(isinstance(n, ast.BinOp) for n in ast.walk(node.returns)), relative


PY39 = Path("/usr/bin/python3")


@pytest.mark.skipif(not PY39.exists(), reason="no /usr/bin/python3 on this machine")
def test_sweep_compiler_and_runtime_import_and_compile_identically_under_python39_isolated(tree, tmp_path):
    version = subprocess.run([str(PY39), "-c", "import sys; print(sys.version_info[:2])"],
                             capture_output=True, text=True, check=True).stdout.strip()
    if version != "(3, 9)":
        pytest.skip("/usr/bin/python3 is %s, not 3.9" % version)
    module = tree["root"] / "modules/hotel-reservation"
    program = (
        "import importlib.util,json,sys\n"
        "def load(n,p):\n"
        " s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;"
        "s.loader.exec_module(m);return m\n"
        "c=load('c',%r)\n"
        "load('cell',%r)\n"
        "r=sys.modules['hotel_candidate_cell_runtime']\n"
        "p=c.compile_plan(c.load_descriptor())\n"
        "print(json.dumps([r.STUDY_EPOCH,r.CELL_COUNT,r.MAXIMUM_WALL_SECONDS,p['planCanonicalSha256']]))\n"
    ) % (str(module / "execution/candidate_sweep.py"), str(module / "execution/candidate_cell.py"))
    # -X pycache_prefix: a fresh cache, so the Apple 3.9 cache cannot serve a stale module (CLAUDE.md trap).
    result = subprocess.run([str(PY39), "-X", "pycache_prefix=" + str(tmp_path / "pyc"), "-I", "-c", program],
                            capture_output=True, text=True, cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [SWEEP, 64, 21600, sweep.EXPECTED_PLAN_SHA256]


def test_vendored_protocol_gates_is_byte_identical_to_the_measurement_repo_source():
    source = ROOT.parent / "observability-placement/src/obsplacement/protocol_gates.py"
    if not source.exists():
        pytest.skip("measurement repo not checked out beside this worktree")
    assert (MODULE / "validation/protocol_gates.py").read_bytes() == source.read_bytes()


# ---------------------------------------------------------------------------------- 9. the gate-driver config
def test_driver_config_follows_the_selector_of_the_tree_it_reads(tree):
    """No selector at ROOT: the frozen study and 5 h window; with one: the sweep and its 6 h window."""
    pytest.importorskip("obsplacement.gate_driver.contract")
    config = load("hotel_sweep_driver_config_test", MODULE / "drivers/gate_driver_config.py")
    assert config._active_epoch(ROOT) == ("hotel-reservation-selected-v1", 5)
    assert config._active_epoch(tree["root"]) == (SWEEP, 6)


def test_probe_stamps_are_required_and_checked_only_for_sweep_cells(tree, tmp_path):
    """Sweep receipts carry the readiness probes' windows (excluded from sensor scoring); frozen ones do not."""
    contract, plan, rows, receipt = _fault_cell(tree, tmp_path / "c", "search-pause-effect", 0.05)
    witness = tree["witness"]
    timing = contract["timing"]
    assert witness.validate_fault_receipt(receipt, contract["fault"], barrier_monotonic=BARRIER,
                                          timing=timing)["state"] == "supported"
    missing = {key: value for key, value in receipt.items() if key != "probes"}
    with pytest.raises(witness.WitnessError, match="fields differ"):
        witness.validate_fault_receipt(missing, contract["fault"], barrier_monotonic=BARRIER, timing=timing)
    reversed_probe = dict(receipt, probes=[dict(receipt["probes"][0], endMonotonic=receipt["probes"][0]["startMonotonic"] - 1)])
    with pytest.raises(witness.WitnessError, match="probe stamps are malformed"):
        witness.validate_fault_receipt(reversed_probe, contract["fault"], barrier_monotonic=BARRIER, timing=timing)


def test_stratified_onsets_span_every_quarter_and_block_one_leads_with_r10_pause():
    plan = sweep.compile_plan(sweep.load_descriptor())
    cells = sweep.flatten_cells(plan)
    assert cells[0]["runId"] == "search-pause-effect-r10-b01-full-a01"
    strata = {}
    for cell in cells:
        timing = cell["timing"]
        key = (cell["runKey"]["regime"], timing["requestsPerSecond"])
        strata.setdefault(key, []).append(int(4 * timing["faultOnsetPhaseOffsetSeconds"] / timing["interArrivalSeconds"]))
    assert len(strata) == 16 and all(sorted(value) == [0, 1, 2, 3] for value in strata.values())


# ------------------------------------------------- 10. decision 25: the shared trace-completeness rule (sweep only)
# sweep1 relaunch 2 ran this harness (7a1d97b); cell 15 stopped on a during-fault missing edge
INCIDENT_COMMIT = "7a1d97b13f34ef123bfa6e6adc267c051d5fee6b"


def _witness_at(commit: str, root: Path):
    """The witness exactly as `commit` shipped it, beside the files it reads relative to its own ROOT."""
    for relative in ("modules/hotel-reservation/witness/candidate_evidence.py",
                     "modules/hotel-reservation/workload/candidate_search.py",
                     "pipelines/campaigns/hotel-reservation-selected-v1.json"):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{relative}"],
                                          capture_output=True, check=True).stdout)
    return load("hotel_sweep_witness_at_%s_%d" % (commit, id(root)),
                root / "modules/hotel-reservation/witness/candidate_evidence.py")


def _witness_log(rows) -> str:
    return "\n".join("OBSPLACEMENT_WITNESS " + json.dumps({
        "schema": "hotel-application-request-witness-v1", "opaqueToken": row["opaqueToken"], "method": "GET",
        "routePattern": "/hotels", "statusCode": 200, "startedAtUnixNano": 1, "endedAtUnixNano": 2,
    }, separators=(",", ":")) for row in rows) + "\n"


def _drop_services(*services):
    return lambda events: [event for event in events if event["service"] not in services]


def _duplicate_span(events):
    return events + [copy.deepcopy(events[-1])]


def _correlate_planted(tree, contract, plan, rows, receipt, planted: dict, *, witness=None, timing="cell"):
    """Correlate full-posture traces, with planted[token](events) applied to that request's normalized trace."""
    witness = witness or tree["witness"]
    data = [_raw_trace(index, row["opaqueToken"], 1) for index, row in enumerate(rows, 1)]
    raw = {"schemaVersion": 1, "collector": "jaeger-query-api-v1", "window": {"startUs": 1, "endUs": 2},
           "limitPerService": 10000, "queries": [{"service": "frontend", "traceCount": len(data),
                                                   "response": {"data": data, "errors": None}}]}
    normalized = tree["terminal"].jaeger_normalizer.normalize(raw)
    by_trace: dict = {}
    for event in normalized["events"]:
        by_trace.setdefault(event["traceId"], []).append(event)
    events = []
    for index, row in enumerate(rows, 1):
        trace = by_trace["%016x" % index]
        events.extend(planted[row["opaqueToken"]](trace) if row["opaqueToken"] in planted else trace)
    normalized = dict(normalized, events=events)
    return witness.correlate(
        plan, rows, _witness_log(rows), normalized, posture="full", scenario=contract["fault"],
        fault_receipt=receipt, raw=raw, capture_terminal={},
        unsupported_postures=tree["runtime"].posture_ceiling()["unsupportedPostures"],
        timing=contract["timing"] if timing == "cell" else timing,
    )


def _windows(contract, rows, receipt):
    """Ledger rows per decision-25 window, from the receipt and the cell's own client timeout (not a literal)."""
    start = receipt["startedMonotonic"]
    end = receipt["readyAtMonotonic"] + contract["timing"]["requestTimeoutSeconds"] + 2.0
    return {
        "pre": [row for row in rows if row["actualStartMonotonic"] < start],
        "fault-drain": [row for row in rows if start <= row["actualStartMonotonic"] < end],
        "post-drain": [row for row in rows if row["actualStartMonotonic"] >= end],
    }


def test_incident_cell15_missing_rate_edges_inside_the_fault_window_are_recorded_not_blocking(tree, tmp_path):
    """sweep1 relaunch 2, cell 15 (net-delay r10 b01): 10 traces starting in the fault window lack search->rate.

    7a1d97b raised `native trace lacks a required same-trace service edge` and stopped the campaign; under decision
    25 the cell is valid and the ten traces are its fault effect, counted with their tokens.
    """
    contract, plan, rows, receipt = _fault_cell(tree, tmp_path / "c", "net-delay-effect", 10.0, block=1)
    assert contract["runId"] == "net-delay-effect-r10-b01-full-a01"
    inside = _windows(contract, rows, receipt)["fault-drain"]
    hit = [row["opaqueToken"] for row in inside[100:600:50]]
    assert len(hit) == 10
    planted = {token: _drop_services("rate") for token in hit}
    old = _witness_at(INCIDENT_COMMIT, tmp_path / "old")
    with pytest.raises(old.WitnessError, match="required same-trace service edge"):
        _correlate_planted(tree, contract, plan, rows, receipt, planted, witness=old)
    result = _correlate_planted(tree, contract, plan, rows, receipt, planted)
    report = result["traceCompleteness"]
    assert report["rule"] == "protocol-decision-25-v1"
    assert report["drainAfterReadySeconds"] == 3.0          # Hotel's 1 s client timeout + 2 s
    assert report["faultDrainWindowMonotonic"] == [receipt["startedMonotonic"], receipt["readyAtMonotonic"] + 3.0]
    assert {name: row["incomplete"] for name, row in report["windows"].items()} == {
        "pre": 0, "fault-drain": 10, "post-drain": 0}
    assert report["windows"]["fault-drain"]["incompleteByReason"] == {"required-edge-missing": 10}
    assert [row["opaqueToken"] for row in report["windows"]["fault-drain"]["incompleteTraces"]] == sorted(hit)
    assert report["allowance"]["incomplete"] == 0 and report["allowance"]["windows"] == ["pre", "post-drain"]
    marked = {row["opaqueToken"]: row for row in result["rows"] if row["reason"] == "native-trace-incomplete"}
    assert set(marked) == set(hit)
    assert all(row["state"] == "unsupported" and row["reconstructed"] is None for row in marked.values())


def test_incident_cell_seals_valid_and_the_terminal_reports_the_window_counts(tree, tmp_path):
    contract, _, rows, receipt = _fault_cell(tree, tmp_path / "c", "net-delay-effect", 10.0, block=1)
    hit = {row["opaqueToken"] for row in _windows(contract, rows, receipt)["fault-drain"][:10]}
    root = Path(contract["runtimeArtifactRoot"])
    _seal_sweep_cell(tree, root, contract, receipt=receipt,
                     drop_spans=lambda row: {"rate"} if row["opaqueToken"] in hit else set())
    result = tree["terminal"].validate_cell(root, contract)
    assert result["candidateCellValid"] is True
    assert result["traceCompleteness"]["windows"]["fault-drain"]["incomplete"] == 10
    assert result["traceCompleteness"] == json.loads((root / "correlation.json").read_text())["traceCompleteness"]


@pytest.mark.parametrize("defect, reason", [
    (_drop_services("rate"), "required-edge-missing"),
    (_drop_services("search"), "dangling-parent"),        # geo and rate keep search's span ID as their parent
    (lambda events: [], "trace-missing"),                  # the request is witnessed, its whole trace is not
    (_duplicate_span, "span-id-missing-or-duplicate"),     # malformed, not incomplete: still never blocks in (i)
])
def test_nothing_blocks_inside_the_fault_drain_window(tree, tmp_path, defect, reason):
    contract, plan, rows, receipt = _fault_cell(tree, tmp_path / "c", "cpu-throttle-effect", 1.0)
    inside = _windows(contract, rows, receipt)["fault-drain"]
    # Every request of window (i), including the last ones started after readiness (phase post-readiness).
    assert inside[-1]["actualStartMonotonic"] >= receipt["readyAtMonotonic"] + 1.0
    result = _correlate_planted(tree, contract, plan, rows, receipt, {row["opaqueToken"]: defect for row in inside})
    window = result["traceCompleteness"]["windows"]["fault-drain"]
    assert window["incomplete"] == len(inside) and window["incompleteByReason"] == {reason: len(inside)}


def test_a_pause_cell_keeps_its_during_policy_and_a_trace_failing_it_inside_window_i_is_recorded(tree, tmp_path):
    contract, plan, rows, receipt = _fault_cell(tree, tmp_path / "c", "search-pause-effect", 1.0)
    inside = _windows(contract, rows, receipt)["fault-drain"]
    during = [row for row in inside if row["actualStartMonotonic"] < receipt["readyAtMonotonic"] + 1.0]
    truncated, lost = during[:3], during[3:5]
    planted = {row["opaqueToken"]: _drop_services("geo", "rate") for row in truncated}       # the pause's signature
    planted.update({row["opaqueToken"]: _drop_services("search", "geo", "rate") for row in lost})   # prefix lost
    result = _correlate_planted(tree, contract, plan, rows, receipt, planted)
    assert result["faultPathTruth"]["duringTracesTruncated"] == 3           # permitted truncation, not incomplete
    assert result["traceCompleteness"]["windows"]["fault-drain"]["incompleteByReason"] == {
        "attempted-prefix-missing": 2}
    old = _witness_at(INCIDENT_COMMIT, tmp_path / "old")
    with pytest.raises(old.WitnessError, match="attempted prefix"):
        _correlate_planted(tree, contract, plan, rows, receipt, planted, witness=old)


@pytest.mark.parametrize("rate", [10.0, 0.05])
def test_outside_window_i_exactly_the_allowance_passes_and_one_more_blocks(tree, tmp_path, rate):
    contract, plan, rows, receipt = _fault_cell(tree, tmp_path / "c", "net-delay-effect", rate)
    windows = _windows(contract, rows, receipt)
    outside = windows["pre"] + windows["post-drain"]
    allowance = max(1, len(outside) // 100)                  # every synthetic request succeeds
    if rate == 0.05:
        assert 5 <= len(outside) <= 6 and allowance == 1     # low rate: n ~ 5, the floor of 1 binds
    else:
        assert allowance == len(outside) // 100 > 1
    # Pre and post-drain are pooled: alternate the planted traces between them.
    spread = [row for pair in zip(windows["pre"], reversed(windows["post-drain"])) for row in pair]
    at_limit = {row["opaqueToken"]: _drop_services("rate") for row in spread[:allowance]}
    result = _correlate_planted(tree, contract, plan, rows, receipt, at_limit)
    assert result["traceCompleteness"]["allowance"] == {
        "windows": ["pre", "post-drain"], "successful": len(outside), "incomplete": allowance,
        "maximum": allowance, "rule": "block-if-incomplete-exceeds-max(1, floor(1 % x successful))"}
    over = dict(at_limit, **{spread[allowance]["opaqueToken"]: _drop_services("rate")})
    with pytest.raises(tree["witness"].WitnessError, match="exceed max\\(1, 1 %% of %d successful requests\\) = %d"
                       % (len(outside), allowance)):
        _correlate_planted(tree, contract, plan, rows, receipt, over)


def test_window_i_is_half_open_at_both_edges(tree, tmp_path):
    """A start exactly at the receipt's start is inside (i); a start exactly at readyAt + timeout + 2 s is not."""
    contract, plan, rows, receipt = _fault_cell(tree, tmp_path / "c", "net-delay-effect", 10.0)
    rows = copy.deepcopy(rows)
    start = receipt["startedMonotonic"]
    end = receipt["readyAtMonotonic"] + contract["timing"]["requestTimeoutSeconds"] + 2.0
    first_in = next(row for row in rows if row["actualStartMonotonic"] >= start)
    first_after = next(row for row in rows if row["actualStartMonotonic"] >= end)
    first_in["actualStartMonotonic"], first_after["actualStartMonotonic"] = start, end
    planted = {row["opaqueToken"]: _drop_services("rate") for row in (first_in, first_after)}
    report = _correlate_planted(tree, contract, plan, rows, receipt, planted)["traceCompleteness"]
    assert report["faultDrainWindowMonotonic"] == [start, end]
    assert [e["opaqueToken"] for e in report["windows"]["fault-drain"]["incompleteTraces"]] == [first_in["opaqueToken"]]
    assert [e["opaqueToken"] for e in report["windows"]["post-drain"]["incompleteTraces"]] == [
        first_after["opaqueToken"]]
    assert report["windows"]["pre"]["incomplete"] == 0 and report["allowance"]["incomplete"] == 1


def test_a_malformed_trace_outside_window_i_stays_fatal(tree, tmp_path):
    contract, plan, rows, receipt = _fault_cell(tree, tmp_path / "c", "net-delay-effect", 10.0)
    token = _windows(contract, rows, receipt)["pre"][5]["opaqueToken"]
    with pytest.raises(tree["witness"].WitnessError, match="missing or duplicate span ID"):
        _correlate_planted(tree, contract, plan, rows, receipt, {token: _duplicate_span})


@pytest.mark.parametrize("rate", [1.0, 0.05])
def test_a_no_fault_cell_applies_the_allowance_over_its_whole_window(tree, tmp_path, rate):
    contract = _calibration_contract(tree, tmp_path / "c", rate)
    timing = contract["timing"]
    plan = tree["workload"].build_plan(contract["runId"], contract["compiledPlanCanonicalSha256"], BARRIER_AT,
                                       BARRIER, rate=rate, duration_seconds=180.0,
                                       created_at=BARRIER_AT - timedelta(minutes=1))
    rows = _ledger(tree["workload"], plan)
    allowance = max(1, len(rows) // 100)
    assert allowance == 1                                    # 180 and 9 successful requests
    # Inside the pseudo window [onset, onset + hold): no fault, so no window (i) and no excuse.
    pseudo = [row for row in rows
              if timing["faultOnsetSeconds"] <= row["actualStartMonotonic"] - BARRIER < sum(timing["scoredWindowSeconds"][1:])]
    one = {pseudo[0]["opaqueToken"]: _drop_services("rate")}
    result = _correlate_planted(tree, contract, plan, rows, None, one)
    report = result["traceCompleteness"]
    assert report["faultDrainWindowMonotonic"] is None and report["drainAfterReadySeconds"] is None
    assert list(report["windows"]) == ["measurement"] and report["windows"]["measurement"]["incomplete"] == 1
    assert report["allowance"]["windows"] == ["measurement"] and report["allowance"]["maximum"] == 1
    two = dict(one, **{pseudo[-1]["opaqueToken"]: _drop_services("rate")})
    with pytest.raises(tree["witness"].WitnessError, match="exceed max\\(1, 1 % of"):
        _correlate_planted(tree, contract, plan, rows, None, two)


def test_frozen_epoch_correlation_is_unchanged_by_decision_25(tree, tmp_path):
    """timing=None (the frozen epoch): byte-identical output to 7a1d97b and every trace defect still fatal."""
    old = _witness_at(INCIDENT_COMMIT, tmp_path / "old")
    contract = _calibration_contract(tree, tmp_path / "c", 1.0)
    plan = tree["workload"].build_plan(contract["runId"], contract["compiledPlanCanonicalSha256"], BARRIER_AT,
                                       BARRIER, rate=1.0, duration_seconds=180.0,
                                       created_at=BARRIER_AT - timedelta(minutes=1))
    rows = _ledger(tree["workload"], plan)
    clean = _correlate_planted(tree, contract, plan, rows, None, {}, timing=None)
    assert clean == _correlate_planted(tree, contract, plan, rows, None, {}, witness=old, timing=None)
    assert "traceCompleteness" not in clean
    token = rows[7]["opaqueToken"]
    for defect, message in ((_drop_services("rate"), "required same-trace service edge"),
                            (_drop_services("search"), "parentSpanId is missing"),
                            (lambda events: [], "bijective")):
        for witness in (tree["witness"], old):
            with pytest.raises(witness.WitnessError, match=message):
                _correlate_planted(tree, contract, plan, rows, None, {token: defect}, witness=witness, timing=None)
