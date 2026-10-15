#!/usr/bin/env python3
"""Fail-closed evidence validation for the frozen TeaStore candidate pilot.

The validator deliberately distinguishes three things that are easy to conflate:

* an expected path opportunity, allocated before a journey starts;
* independent application-side evidence that the path actually executed; and
* reconstruction of that executed path from one original native Kieker trace.

Missing execution or correlation evidence is ``unsupported`` and produces a
null endpoint.  It is never interpreted as an observed reconstruction failure.

Shape expectations are keyed on the replayed activation closure, not the
posture name (F-ADH-066): when the closure omits the trace-root sensor, native
traces are per-worker-thread, so per-request path reconstruction is
*structurally absent* rather than defective. Such runs release a
``request-root-structurally-absent`` endpoint whose per-request fraction is
honestly 0 alongside a clearly-labeled trace-level auth->persistence coverage
aggregate; they are never scored as per-request reconstruction, and no
detection or RCA claim follows (claimBoundary unchanged).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


CONTRACT = "teastore-candidate-pilot-evidence-v1"
STUDY_EPOCH = "teastore-candidate-pilot-sys-v1"
POPULATION = "login-browse-v1"
SUT_COMMIT = "34b37f7e7be433ce72d5f9455e66922a13116749"
POSTURES = ("none", "selected", "full")
REGIMES = (
    "no-fault-cost",
    "auth-freeze-effect",
    "persistence-crash-effect",
)
SCENARIOS = {
    "auth-freeze-effect": "auth-freeze",
    "persistence-crash-effect": "persistence-crash",
}
EXPECTED_SCHEDULES = {
    "no-fault-cost": [
        ["full", "none", "selected"],
        ["selected", "full", "none"],
        ["none", "selected", "full"],
    ],
    "auth-freeze-effect": [
        ["selected", "full", "none"],
        ["none", "selected", "full"],
        ["full", "none", "selected"],
    ],
    "persistence-crash-effect": [
        ["none", "full", "selected"],
        ["selected", "none", "full"],
        ["full", "selected", "none"],
    ],
}
EXPECTED_SELECTOR_DIGESTS = {
    "no-fault-cost": "49dce5c55c33d6f5dbbb864fc7cef0c89af74a067d8f47e5d7e7f01cc83c7429",
    "auth-freeze-effect": "c84e7290a894b14522df38e894386d8e79d0ec8d2361cc98e306f73ef5e99243",
    "persistence-crash-effect": "efd0b6deecaa19b3c372c1a0ed873fddfd3977417bd913bcb30f46f34906031f",
}
EXPECTED_PATH = {
    "id": "login-path-v1",
    "claim": "expected-not-executed",
    "requiredLogicalSensors": ["operation:auth", "operation:persistence"],
    "requiredDirectEdge": {
        "parent": "operation:auth",
        "child": "operation:persistence",
        "predicate": "persistence.parentId == auth.spanId in same original native trace",
    },
}
TOKEN_CONTRACT = {
    "generation": "uuid4-before-outcome",
    "requestInjection": {"header": "X-Observability-Journey-Id", "step": "login"},
    "applicationWitnessExtraction": "required-independent-artifact",
    "nativeTraceExtraction": "required-original-trace-token",
    "uniqueness": "one-token-per-offered-journey",
    "mapping": "one-token-to-one-journey-and-at-most-one-native-trace",
}
REQUIRED_FILES = (
    "receipt.json",
    "resources.json",
    "journey-ledger.plan.json",
    "journey-ledger.jsonl",
    "auth.log",
    "persistence.log",
    "app-witness.jsonl",
    "app-witness-extraction.json",
    "service-log-capture.json",
    "native-token-correlation.json",
    "native-token-correlation-extraction.json",
    "kieker-amqp.spool",
    "traces.json",
    "runtime-images.json",
    "capture-terminal.json",
    "posture-proof.json",
    "queue-proof.json",
    "system-samples.json",
)
# sys lineage: cgroup-v2 samples in every cell (collectors/system_probe.py).
SYSTEM_SAMPLES_KIND = "teastore-system-samples-v1"
SYSTEM_SAMPLE_INTERVAL_SECONDS = 5.0
SYSTEM_SAMPLE_WINDOW_SECONDS = 600.0
SYSTEM_SAMPLE_COUNT = 121  # both window edges: 600 / 5 + 1
SYSTEM_REQUIRED_SERVICES = ("auth", "image", "persistence", "recommender", "webui")
SYSTEM_ROW_KEYS = frozenset({
    "cpuUsageUsec", "memoryCurrent", "rbytes", "wbytes",
    "psiCpuSomeTotalUsec", "psiMemorySomeTotalUsec", "psiIoSomeTotalUsec",
})
APP_WITNESS_MARKER = "OBSERVABILITY_APP_WITNESS "
APP_OBSERVATION_SCHEMA = "teastore.app-witness-observation"
APP_OBSERVATION_KEYS = {
    "schema", "schemaVersion", "observedAtUtc", "journeyId", "service", "event",
}
APP_EVENTS = {"auth": "login-persistence-request", "persistence": "login-user-lookup"}
SECRET_KEYS = {
    "authorization", "cookie", "credential", "password", "requestbody", "session", "sid",
}

_SECRET_SCAN_PATH = Path(__file__).with_name("secret_scan.py")
_SECRET_SCAN_SPEC = importlib.util.spec_from_file_location(
    "teastore_secret_scan_for_candidate", _SECRET_SCAN_PATH)
if _SECRET_SCAN_SPEC is None or _SECRET_SCAN_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot load TeaStore secret scanner: {_SECRET_SCAN_PATH}")
_SECRET_SCAN = importlib.util.module_from_spec(_SECRET_SCAN_SPEC)
_SECRET_SCAN_SPEC.loader.exec_module(_SECRET_SCAN)
JOURNEY_TOKEN_RE = re.compile(r"^journey-[0-9a-f]{32}$")
TOKEN_SMUGGLING_FIELDS = {
    "opaqueToken", "token", "journeyId", "observabilityJourneyId",
    "X-Observability-Journey-Id",
}
TRUSTED_ATTRIBUTION_STATES = {
    "runtime-host-only",
    "runtime-host-and-signature-agree",
    "runtime-host-overrides-shared-signature",
}
NATIVE_RECORD_CLASSES = {
    "kieker.common.record.controlflow.OperationExecutionRecord",
    "tools.descartes.teastore.kieker.probes.records.OperationExecutionWithParametersRecord",
}


def _study_epoch_module():
    """The tree's study-epoch selector (execution/study_epoch.py), loaded by path (python3 -I)."""
    path = Path(__file__).resolve().parents[1] / "execution/study_epoch.py"
    name = "teastore_study_epoch_" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:  # pragma: no cover - install defect
            raise RuntimeError(f"cannot load the study-epoch selector: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


# Traffic sweep (teastore-traffic-sweep-v1, 2026-10-03).  With no selector EPOCH is the frozen epoch and every
# constant above keeps its c1724b1 value; with the selector the run-level numbers come from the cell's compiled
# timing (``_sweep_timing``), never from the receipt alone.
EPOCH = _study_epoch_module().active(Path(__file__).resolve().parents[3])
SWEEP = EPOCH["sweep"] is True
if SWEEP:
    STUDY_EPOCH = EPOCH["studyEpoch"]
    POSTURES = tuple(EPOCH["postures"])
    REGIMES = tuple(EPOCH["regimes"])
    SCENARIOS = {regime: fault for regime, fault in EPOCH["scenarios"].items() if fault is not None}
    REQUIRED_FILES = (*REQUIRED_FILES, "application.log")
FAULT_SERVICES = {
    "auth-freeze": "auth", "persistence-crash": "persistence", "persistence-cpu-throttle": "persistence",
}
APPLICATION_SERVICES = ("auth", "image", "persistence", "recommender", "webui")
COMPOSE_LOG_LINE_RE = re.compile(
    r"^(?P<container>[a-z0-9][a-z0-9_.-]*)\s+\|\s(?P<stamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:Z|[+-]\d{2}:\d{2}))\s")


def _sweep_compiler():
    return _study_epoch_module().sweep_compiler(Path(__file__).resolve().parents[3])


def _fault_harness_problem(intervention: dict, sweep_record: dict, harness: Any, timing: dict,
                           expected_scenario: str) -> Any:
    """Campaign B, H10: None when the probe policy holds, else the first reason.  BLOCKING for the cell.

    The policy is re-derived here from the receipt's own stamps and the cell's compiled timing; nothing the
    producer wrote is trusted.  Only called for a cell whose plan declares ``timing.faultHarness``.  The H4 freeze
    stamps are NOT judged here: they are record-not-block (decision 69), see ``_freeze_stamp_problems``.
    """
    if (not isinstance(harness, dict) or harness.get("version") != "h4-h10-v1"
            or harness.get("noProbeDuringFault") is not True or harness.get("freezeStamps") is not True
            or harness.get("freezeFailure") != "record-not-block"):
        return "the cell's fault harness declaration is not h4-h10-v1"
    stamps = sweep_record["commandStamps"]
    issued = float(stamps["onsetCommandIssuedMonotonicOffsetSeconds"])
    reverted = float(stamps["revertCommandReturnedMonotonicOffsetSeconds"])
    scored_end = float(timing["faultOnsetSeconds"]) + float(timing["faultHoldSeconds"])
    policy = sweep_record["probePolicy"]
    if (not isinstance(policy, dict) or set(policy) != {
            "version", "noProbeFromMonotonicOffsetSeconds", "scoredWindowEndMonotonicOffsetSeconds",
            "noProbeUntilMonotonicOffsetSeconds"} or policy["version"] != harness["version"]):
        return "probePolicy fields differ"
    until = max(scored_end, reverted)
    if (not math.isclose(float(policy["noProbeFromMonotonicOffsetSeconds"]), issued, abs_tol=1e-9)
            or not math.isclose(float(policy["scoredWindowEndMonotonicOffsetSeconds"]), scored_end, abs_tol=1e-9)
            or not math.isclose(float(policy["noProbeUntilMonotonicOffsetSeconds"]), until, abs_tol=1e-9)):
        return "probePolicy window is not [onset command issued, max(scored window end, revert returned)]"
    for row in sweep_record["probes"]:
        if float(row["startMonotonicOffsetSeconds"]) < until:
            return "a readiness probe starts at %s inside the no-probe window ending %s (H10)" % (
                row["startMonotonicOffsetSeconds"], until)
    return None


def _freeze_stamp_problems(intervention: dict, sweep_record: dict, harness: dict, timing: dict,
                           expected_scenario: str) -> list:
    """Campaign B, H4 (decision 69, record-not-block): every reason the freeze record is not a usable stamp.

    Re-derived from the receipt's own stamps; never raises (an unreadable record is one reason).  An empty list means
    the record is complete and consistent.  The caller reports the result and never blocks the cell on it: a reader of a
    cell with reasons falls back to [onset command issued, onset command returned].
    """
    problems: list = []
    try:
        freeze = sweep_record["freezeStamps"]
        if not isinstance(freeze, dict):
            return ["freezeStamps is absent or not an object: %r" % (freeze,)]
        for reason in freeze.get("failures") or []:
            problems.append("producer: %s" % (reason,))
        if freeze.get("status") not in ("recorded", "missing"):
            problems.append("freezeStamps status is neither recorded nor missing")
        elif (freeze["status"] == "missing") is not bool(freeze.get("failures")):
            problems.append("freezeStamps status and failures disagree")
        if freeze.get("failureCount") != len(freeze.get("failures") or []):
            problems.append("freezeStamps failureCount is not the number of failures")
        if freeze.get("status") == "missing":
            return problems                       # the producer said it is missing; nothing more to re-derive
        stamps = sweep_record["commandStamps"]
        issued = float(stamps["onsetCommandIssuedMonotonicOffsetSeconds"])
        returned = float(stamps["onsetCommandReturnedMonotonicOffsetSeconds"])
        reverting = float(stamps["revertCommandIssuedMonotonicOffsetSeconds"])
        reverted = float(stamps["revertCommandReturnedMonotonicOffsetSeconds"])
        tolerance = harness.get("freezeEventToleranceSeconds")
        if (set(freeze) != {"schemaVersion", "version", "scenario", "targetContainerId", "toleranceSeconds", "commands",
                            "readbacks", "clock", "events", "status", "failures", "failureCount"}
                or freeze["schemaVersion"] != 1 or freeze["version"] != harness["version"]
                or freeze["scenario"] != expected_scenario
                or freeze["targetContainerId"] != intervention.get("targetContainerId")
                or type(tolerance) not in (int, float) or not 0 < tolerance <= 1.0
                or freeze["toleranceSeconds"] != tolerance):
            problems.append("freezeStamps header differs")
            return problems
        if freeze["commands"] != {
                "onsetIssuedMonotonicOffsetSeconds": issued, "onsetReturnedMonotonicOffsetSeconds": returned,
                "revertIssuedMonotonicOffsetSeconds": reverting, "revertReturnedMonotonicOffsetSeconds": reverted}:
            problems.append("freezeStamps commands differ from the command stamps")
        samples = intervention["duringStateSamples"]
        readbacks = freeze["readbacks"]
        if (not isinstance(readbacks, list) or len(readbacks) != len(samples) or [
                row.get("phase") for row in readbacks] != [sample["phase"] for sample in samples]):
            problems.append("readbacks are not one per target-state sample")
        else:
            for row, sample in zip(readbacks, samples):
                if (set(row) != {"phase", "issuedMonotonicOffsetSeconds", "returnedMonotonicOffsetSeconds", "paused",
                                 "nanoCpus"}
                        or row["issuedMonotonicOffsetSeconds"] != sample["observedAtMonotonicOffsetSeconds"]
                        or not issued <= returned <= float(row["issuedMonotonicOffsetSeconds"])
                        <= float(row["returnedMonotonicOffsetSeconds"])):
                    problems.append("a readback stamp is missing, unordered or differs from its sample")
                    break
                if expected_scenario == "auth-freeze" and (row["paused"] is not True or row["nanoCpus"] is not None):
                    problems.append("a pause readback does not show the container paused")
                    break
                if expected_scenario == "persistence-cpu-throttle" and (
                        row["paused"] is not False or row["nanoCpus"] != timing.get("cpuThrottleNanoCpus")):
                    problems.append("a throttle readback does not show the applied quota")
                    break
        events, clock = freeze["events"], freeze["clock"]
        if expected_scenario != "auth-freeze":
            if events is not None or clock is not None:
                problems.append("a throttle cell carries Docker events")
            return problems
        if (not isinstance(events, dict) or set(events) != {"command", "returnCode", "error", "rows"}
                or events["returnCode"] != 0 or events["error"] is not None or not isinstance(events["rows"], list)):
            problems.append("the Docker events were not collected: %s" % (
                events.get("error") if isinstance(events, dict) else events))
            return problems
        if (not isinstance(clock, dict) or set(clock) != {
                "barrierWallEpochSeconds", "barrierMonotonicOffsetSeconds", "collectedWallEpochSeconds",
                "collectedMonotonicOffsetSeconds", "mapping"} or clock["barrierMonotonicOffsetSeconds"] != 0.0):
            problems.append("the event clock mapping differs")
            return problems
        barrier_wall = float(clock["barrierWallEpochSeconds"])
        collected_wall = float(clock["collectedWallEpochSeconds"])
        collected_mono = float(clock["collectedMonotonicOffsetSeconds"])
        if not (collected_wall > barrier_wall and collected_mono >= float(
                sweep_record["probes"][-1]["endMonotonicOffsetSeconds"])):
            problems.append("the events were collected before the readiness")
            return problems
        rows = events["rows"]
        if [row.get("action") for row in rows] != ["pause", "unpause"]:
            problems.append("the target's Docker events are not exactly one pause then one unpause: %s" % (
                [row.get("action") for row in rows],))
            return problems
        for row in rows:
            if (set(row) != {"action", "type", "containerId", "timeNano", "monotonicOffsetSeconds"}
                    or row["type"] != "container" or row["containerId"] != intervention.get("targetContainerId")
                    or type(row["timeNano"]) is not int):
                problems.append("a Docker event row differs or names another container")
                return problems
            recomputed = (row["timeNano"] / 1e9 - barrier_wall) * (collected_mono / (collected_wall - barrier_wall))
            if not math.isclose(float(row["monotonicOffsetSeconds"]), recomputed, abs_tol=1e-6):
                problems.append("a Docker event's monotonic offset does not follow from its time and the clock mapping")
                return problems
        paused_at, unpaused_at = (float(row["monotonicOffsetSeconds"]) for row in rows)
        if not issued - tolerance <= paused_at <= returned + tolerance:
            problems.append("the pause event (%s) is outside the pause command [%s, %s]" % (paused_at, issued, returned))
        if not reverting - tolerance <= unpaused_at <= reverted + tolerance:
            problems.append("the unpause event (%s) is outside the unpause command [%s, %s]" % (
                unpaused_at, reverting, reverted))
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        problems.append("the freeze record could not be read: %s: %s" % (type(exc).__name__, exc))
    return problems


def _protocol_gates():
    path = Path(__file__).with_name("protocol_gates.py")
    name = "teastore_protocol_gates_" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:  # pragma: no cover - install defect
            raise RuntimeError(f"cannot load the vendored protocol gates: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


def _sweep_timing(receipt: dict[str, Any], run_key: dict[str, Any]) -> dict[str, Any]:
    """The compiled cell's timing for this receipt's run ID; the receipt's own copy must equal it exactly."""
    run = receipt.get("run") if isinstance(receipt.get("run"), dict) else {}
    compiled = _sweep_compiler().compiled_cell(run.get("runId"))
    if compiled["runKey"] != run_key:
        raise ValueError("receipt run key differs from the compiled sweep cell")
    if _canonical_bytes(receipt.get("timing")) != _canonical_bytes(compiled["timing"]):
        raise ValueError("receipt timing differs from the compiled sweep plan")
    return compiled["timing"]


def _application_log_check(path: Path) -> tuple[bool, dict[str, Any]]:
    """Traffic sweep: every application service has Docker-timestamped lines in application.log."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return False, {"error": f"{type(exc).__name__}: {exc}"}
    text = raw.decode("utf-8", errors="replace")      # retained as raw bytes; a stray byte is counted, not fatal
    stamped: Counter[str] = Counter()
    unstamped = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        match = COMPOSE_LOG_LINE_RE.match(line)
        if match is None:
            unstamped += 1
            continue
        parts = re.match(
            r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$",
            match.group("stamp"))
        try:
            # RFC 3339 with nanoseconds; Python 3.9's fromisoformat takes at most microseconds.
            datetime.fromisoformat("%s.%s%s" % (
                parts.group(1), (parts.group(2) or "")[:6].ljust(6, "0"),
                "+00:00" if parts.group(3) == "Z" else parts.group(3)))
        except (AttributeError, ValueError):
            unstamped += 1
            continue
        # Compose prefixes "<service>-<index>" (v2) or, in older releases, the full container name.
        container = re.sub(r"[-_]\d+$", "", match.group("container"))
        service = next((name for name in APPLICATION_SERVICES
                        if container == name or container.endswith(("-" + name, "_" + name))), container)
        stamped[service] += 1
    missing = [service for service in APPLICATION_SERVICES if not stamped.get(service)]
    observation = {
        "bytes": len(raw),
        "undecodableCharacters": text.count("\ufffd"),
        "stampedLinesByService": dict(sorted(stamped.items())),
        "unstampedLines": unstamped,
        "servicesWithoutStampedLines": missing,
        # Recorded, not blocking: the frozen design retained only the bounded, scanned auth/persistence logs.
        "secretBearingTextDetected": bool(_SECRET_SCAN.contains_secret_text(text, jvm_source_locations=SWEEP)),
    }
    return not missing, observation


def _sweep_ledger_rows(journeys: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """GATES.md mapping (TeaStore): barrier-relative stamps; ok iff succeeded, timeout iff timeout."""
    rows = []
    for row in journeys:
        outcome = row.get("outcome")
        rows.append({
            "scheduled": float(row["scheduledMonotonicOffsetSeconds"]),
            "started": (None if row.get("actualStartMonotonic") is None
                        else float(row["actualStartMonotonic"])),
            "ended": None if row.get("actualEndMonotonic") is None else float(row["actualEndMonotonic"]),
            "status": "ok" if outcome == "succeeded" else "timeout" if outcome == "timeout" else "failed",
        })
    return rows


def sweep_protocol_gates(
    *, run_id: str, posture: str, timing: dict[str, Any], plan: dict[str, Any],
    journeys: list[dict[str, Any]], intervention: Any, harness_valid: bool,
) -> dict[str, Any]:
    """F1, G1, G2, G4 (blocking) and R2.recovery (recorded) of the vendored protocol gates for one sweep cell."""
    gates = _protocol_gates()
    schedule = plan.get("schedule") if isinstance(plan.get("schedule"), dict) else {}
    fault_cell = timing.get("faultApplied") is True
    cell: dict[str, Any] = {
        "cellId": run_id,
        "kind": "fault" if fault_cell else "nofault",
        "posture": posture,
        "valid": harness_valid,
        "plan": {
            "offered": schedule.get("offered"),
            "rate": schedule.get("journeysPerSecond"),
            "durationSeconds": schedule.get("durationSeconds"),
            "window": list(timing["scoredWindowSeconds"]),
        },
        "measurement": [0.0, float(timing["measurementSeconds"])],
        "ledgerKind": "ledger",
        "ledger": _sweep_ledger_rows(journeys),
        "fault": None,
    }
    if fault_cell:
        sweep = intervention.get("sweep") if isinstance(intervention, dict) else None
        stamps = sweep.get("commandStamps") if isinstance(sweep, dict) else None
        stamps = stamps if isinstance(stamps, dict) else {}
        recovery = intervention.get("recoveryAction") if isinstance(intervention, dict) else None
        recovery_result = recovery.get("commandResult") if isinstance(recovery, dict) else None
        cell["fault"] = {
            "scheduledOnset": timing["faultOnsetSeconds"],
            "scheduledHold": timing["faultHoldSeconds"],
            "onsetCommandIssued": stamps.get("onsetCommandIssuedMonotonicOffsetSeconds"),
            "onsetCommandReturned": stamps.get("onsetCommandReturnedMonotonicOffsetSeconds"),
            "revertCommandIssued": stamps.get("revertCommandIssuedMonotonicOffsetSeconds"),
            "revertCommandReturned": stamps.get("revertCommandReturnedMonotonicOffsetSeconds"),
            "onsetSource": sweep.get("onsetSource") if isinstance(sweep, dict) else None,
            "manifested": isinstance(intervention, dict) and intervention.get("manifested") is True,
            "reverted": (
                isinstance(intervention, dict) and intervention.get("recovered") is True
                and isinstance(recovery_result, dict) and recovery_result.get("returnCode") == 0),
        }
    profile = {"sut": "teastore", "routes": [timing["route"]], "rate": timing["journeysPerSecond"],
               "services": [], "channels": {posture: []}, "emitters": {posture: []}}
    verdicts = []
    if fault_cell:
        verdicts.append(gates.f1(cell))
    verdicts.extend([gates.g1(cell), gates.g2(cell), gates.g4(cell, profile), gates.r2_recovery(cell)])
    blocking = [record["gate"] for record in verdicts if record["gate"] != "R2.recovery"]
    failed = [record["gate"] for record in verdicts
              if record["gate"] in blocking and record["verdict"] != "pass"]
    return {
        "module": "validation/protocol_gates.py",
        "blocking": blocking,
        "notEvaluated": ["P0", "R1", "R2"],
        "failedGates": failed,
        "verdicts": verdicts,
    }


def _resource_validator():
    path = Path(__file__).parents[1] / "collectors" / "performance_probe_v3.py"
    spec = importlib.util.spec_from_file_location("candidate_resource_probe_v3", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load candidate resource validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _native_token_validator():
    path = Path(__file__).with_name("native_token_correlation.py")
    spec = importlib.util.spec_from_file_location(
        "candidate_native_token_correlation_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load native-token validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _native_collector():
    path = Path(__file__).parents[1] / "collectors" / "kieker_native.py"
    spec = importlib.util.spec_from_file_location("candidate_native_spool_replay", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load native spool replayer: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _selection_compiler():
    path = Path(__file__).parents[3] / "src/obsplacement/selection.py"
    spec = importlib.util.spec_from_file_location("candidate_selection_replay", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load selection compiler: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _queue_checker():
    path = Path(__file__).parents[1] / "execution/performance_campaign.py"
    spec = importlib.util.spec_from_file_location("candidate_queue_replay", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load queue checker: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_operational_proofs(
    root: Path, *, posture: str,
) -> dict[str, Any]:
    """Replay posture catalog/closure/AOP bytes and the full queue lifecycle."""
    root = Path(root)
    posture_proof = _read_json(root / "posture-proof.json")
    queue_proof = _read_json(root / "queue-proof.json")
    catalog_path = Path(__file__).parents[1] / "activation/catalog.json"
    catalog = _read_json(catalog_path)
    compiler = _selection_compiler()
    # F-ADH-072: every posture is re-derived from the catalog by the same
    # compiler, so `full` is checked against rendered bytes exactly like
    # `selected`. Campaign #6 could not see a mis-realised `full`/`none`
    # because only `selected` carried an AOP digest.
    goal_path = Path(__file__).parents[1] / "goals/fault-qualification.json"
    selection_ids = {
        "selected": "fault-qualification", "full": "catalog-all", "none": "catalog-empty",
    }
    requested = (
        sorted(_read_json(goal_path)["logicalSensors"]) if posture == "selected"
        else sorted(row["id"] for row in catalog["logicalSensors"]) if posture == "full"
        else []
    )
    compiled = compiler.compile_selection(catalog, requested)
    catalog_groups = sorted(row["id"] for row in catalog["activationGroups"])
    required = list(compiled["selectedActivationGroups"])
    expected_aop = hashlib.sha256(compiler.render_aop(compiled).encode()).hexdigest()
    enabled = posture != "none"
    expected_configuration = f"kieker.monitoring.enabled={'true' if enabled else 'false'}"
    if not isinstance(posture_proof, dict) or set(posture_proof) != {
        "schemaVersion", "requested", "catalogId", "catalogSha256",
        "selectionId", "goalLogicalSensors", "closureGroups", "requiredGroups",
        "forbiddenGroups", "aopSha256", "manifestSha256", "monitoringEnabled",
        "services",
    }:
        raise ValueError("posture proof fields differ")
    services = posture_proof["services"]
    if (
        posture_proof["schemaVersion"] != 3
        or posture_proof["requested"] != posture
        or posture_proof["catalogId"] != catalog["id"]
        or posture_proof["catalogSha256"] != _sha256(catalog_path)
        or posture_proof["selectionId"] != selection_ids[posture]
        or posture_proof["goalLogicalSensors"] != requested
        or posture_proof["closureGroups"] != required
        or posture_proof["requiredGroups"] != required
        or posture_proof["forbiddenGroups"] != sorted(set(catalog_groups) - set(required))
        or posture_proof["aopSha256"] != expected_aop
        or posture_proof["monitoringEnabled"] is not enabled
        or not isinstance(services, dict)
        or set(services) != {"auth", "image", "persistence", "recommender", "webui"}
    ):
        raise ValueError("posture proof catalog, goal, closure, or service set differs")
    for service, observation in services.items():
        if not isinstance(observation, dict):
            raise ValueError(f"posture proof {service} observation is malformed")
        if observation != {
            "aopSha256": expected_aop,
            "configuration": expected_configuration,
            "writerInitializationFailed": False,
        }:
            raise ValueError(f"posture proof {service} woven bytes or monitoring state differs")
    _queue_checker().validate_queue_proof(
        queue_proof, expected_project=queue_proof.get("composeProject"),
    )
    if not (
        queue_proof["purge"]["before"]["consumers"] == 0
        and queue_proof["purge"]["after"]["messages"] == 0
        and queue_proof["measurement"]["before"]["messages"] == 0
        and queue_proof["measurement"]["consumerAtStart"]["messages"] == 0
        and queue_proof["measurement"]["consumerAtStart"]["consumers"] == 1
        and queue_proof["measurement"]["after"]["messages"] == 0
        and queue_proof["measurement"]["after"]["consumers"] == 0
    ):
        raise ValueError("queue lifecycle semantic state differs")
    return {
        "postureProofSha256": _sha256(root / "posture-proof.json"),
        "queueProofSha256": _sha256(root / "queue-proof.json"),
        "requiredGroups": required,
        "aopSha256": expected_aop,
        # F-ADH-073: validate_queue_proof raises unless the broker proves
        # heartbeat 0, a reject-publish kieker queue, and no client that
        # negotiated a nonzero heartbeat -- the campaign #6 loss mechanism.
        "brokerHeartbeatDisabled": True,
        "zeroConsumerPurge": True,
        "emptySingleCollectorBarrier": True,
        "terminalDrain": True,
    }


def _iso(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp has no UTC offset")
    return parsed


def _native_time(event: dict[str, Any]) -> datetime:
    value = event.get("nativeTimestamp", event.get("timestamp"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(float(value), tz=_iso("1970-01-01T00:00:00+00:00").tzinfo)
    return _iso(value)


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _strict_json(value: str) -> Any:
    return json.loads(
        value, object_pairs_hook=_no_duplicate_keys, parse_constant=_reject_constant,
    )


def _application_source_observations(path: Path, service: str) -> list[dict[str, Any]]:
    """Strictly replay the raw, independent application-witness log."""

    rows: list[dict[str, Any]] = []
    raw_text = path.read_text(encoding="utf-8")
    # JVM stack-frame source locations are not assignments in the traffic sweep only (secret_scan.JVM_SOURCE_KEY).
    if _SECRET_SCAN.contains_secret_text(raw_text, jvm_source_locations=SWEEP):
        raise ValueError(f"{service} source log contains secret-bearing raw text")
    for line_number, line in enumerate(raw_text.splitlines(), 1):
        if APP_WITNESS_MARKER not in line:
            continue
        row = _strict_json(line.split(APP_WITNESS_MARKER, 1)[1])
        if not isinstance(row, dict) or set(row) != APP_OBSERVATION_KEYS:
            raise ValueError(f"{service} source row {line_number} fields differ")
        normalized = {str(key).replace("_", "").replace("-", "").casefold() for key in row}
        if normalized & SECRET_KEYS:
            raise ValueError(f"{service} source row {line_number} exposes a secret-bearing field")
        if (row.get("schema") != APP_OBSERVATION_SCHEMA
                or row.get("schemaVersion") != 1
                or row.get("service") != service
                or row.get("event") != APP_EVENTS[service]
                or not isinstance(row.get("journeyId"), str)
                or JOURNEY_TOKEN_RE.fullmatch(row["journeyId"]) is None):
            raise ValueError(f"{service} source row {line_number} contract differs")
        _iso(row.get("observedAtUtc"))
        rows.append(row)
    return rows


def _original_native_trace_id(event: dict[str, Any]) -> str | None:
    generic = event.get("trace_id")
    kieker = event.get("kieker_trace_id")
    if (event.get("source") == "kieker_native" and generic is not None and kieker is not None
            and str(generic) == str(kieker)
            and event.get("nativeTraceIdSource") in {None, "kieker-original"}):
        try:
            text = str(int(str(generic)))
        except ValueError:
            return None
        if text != str(generic) or int(text) == -1 or not -(2**63) <= int(text) <= 2**63 - 1:
            return None
        explicit = event.get("original_native_trace_id")
        if explicit is not None and str(explicit) != text:
            return None
        return text
    return None


def _parent_id(event: dict[str, Any]) -> Any:
    return event.get("parent_id", event.get("parent_span_id"))


def _logical_role(event: dict[str, Any]) -> str | None:
    service = event.get("service")
    return str(service) if service in {"auth", "persistence"} else None


def _read_json(path: Path) -> Any:
    return _strict_json(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    payload = path.read_bytes()
    if not payload:
        raise ValueError("JSONL artifact is empty")
    if not payload.endswith(b"\n"):
        raise ValueError("JSONL artifact has a truncated final line")
    try:
        lines = payload.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("JSONL artifact is not UTF-8") from exc
    if any(not line.strip() for line in lines):
        raise ValueError("JSONL artifact contains an empty line")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(lines, 1):
        value = _strict_json(line)
        if not isinstance(value, dict):
            raise ValueError(f"line {number} is not an object")
        rows.append(value)
    return rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _schedule_candidates() -> list[list[list[str]]]:
    first_rows = [
        ["none", "selected", "full"],
        ["none", "full", "selected"],
        ["selected", "none", "full"],
        ["selected", "full", "none"],
        ["full", "none", "selected"],
        ["full", "selected", "none"],
    ]
    candidates: list[list[list[str]]] = []
    for row in first_rows:
        left = [row[index:] + row[:index] for index in range(3)]
        right = [row[-index:] + row[:-index] if index else row[:] for index in range(3)]
        candidates.extend((left, right))
    return candidates


def recompute_schedule() -> tuple[dict[str, str], dict[str, list[list[str]]]]:
    """Recompute the frozen allocation without Python pseudo-randomness."""
    candidates = _schedule_candidates()
    used: set[int] = set()
    digests: dict[str, str] = {}
    schedules: dict[str, list[list[str]]] = {}
    for regime in REGIMES:
        raw = f"{STUDY_EPOCH}\0{regime}\0schedule-v1".encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        index = int(digest, 16) % len(candidates)
        while index in used:
            index = (index + 1) % len(candidates)
        used.add(index)
        digests[regime] = digest
        schedules[regime] = candidates[index]
    return digests, schedules


class _Report:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.invalid = False
        self.unsupported = False
        self.missing = False

    def check(
        self,
        gate: str,
        passed: bool,
        observation: Any,
        inference: str,
        conclusion: str,
        *,
        failure: str = "invalid",
    ) -> bool:
        self.rows.append({
            "gate": gate,
            "status": "pass" if passed else "fail",
            "observation": observation,
            "inference": inference,
            "conclusion": conclusion,
            "failureClass": None if passed else failure,
        })
        if not passed:
            if failure == "unsupported":
                self.unsupported = True
            elif failure == "missing-artifact":
                self.missing = True
            else:
                self.invalid = True
        return passed

    @property
    def cell_status(self) -> str:
        if self.missing:
            return "missing-artifact"
        if self.unsupported:
            return "unsupported"
        if self.invalid:
            return "invalid"
        return "valid"

    @property
    def verdict(self) -> str:
        return "pass" if self.cell_status == "valid" else "blocked"


def _base_result(report: _Report, run_key: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "contract": CONTRACT,
        "kind": "run-validation",
        "runKey": run_key,
        "verdict": report.verdict,
        "cellStatus": report.cell_status,
        "validationTable": report.rows,
        "views": {
            "raw": None,
            "signatureWeighted": None,
            "path": None,
        },
        "reconstruction": {
            "status": "unsupported",
            "eligibleExecutedPaths": None,
            "reconstructedPaths": None,
            "fraction": None,
        },
        "claimBoundary": (
            "Candidate-pilot evidence only. Raw records are event observations, not unique "
            "call diversity; no canonical, causal, optimizer, or cross-host claim follows."
        ),
    }


def _artifact_load(root: Path, report: _Report) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    present = {name: (root / name).is_file() for name in REQUIRED_FILES}
    witness_names = {
        "auth.log", "persistence.log", "app-witness.jsonl", "app-witness-extraction.json",
        "service-log-capture.json", "native-token-correlation.json",
        "native-token-correlation-extraction.json",
    }
    report.check(
        "app-witness-presence", all(present[name] for name in witness_names),
        {name: present[name] for name in sorted(witness_names)},
        "Without an independent application witness, expected opportunities do not define an executed-path denominator.",
        "Application witness artifact is present." if present["app-witness.jsonl"] else "Executed-path evidence is unsupported.",
        failure="unsupported",
    )
    if not present["receipt.json"]:
        report.check(
            "artifact-presence", False,
            {"present": present, "requiredForThisRegime": ["receipt.json"]},
            "The receipt is required before regime-specific artifact requirements can be evaluated.",
            "Run receipt is absent.", failure="missing-artifact",
        )
        return None, {}
    try:
        receipt = _read_json(root / "receipt.json")
    except (OSError, ValueError, TypeError) as exc:
        report.check(
            "receipt-parse", False, str(exc), "The run identity cannot be recovered.",
            "Receipt is unreadable.", failure="missing-artifact",
        )
        return None, {}
    run = receipt.get("run") if isinstance(receipt, dict) and isinstance(receipt.get("run"), dict) else {}
    cost_resources_required = run.get("regime") == "no-fault-cost"
    core_names = tuple(
        name for name in REQUIRED_FILES
        if name not in witness_names
        and (name != "resources.json" or cost_resources_required)
    )
    core_present = all(present[name] for name in core_names)
    report.check(
        "artifact-presence", core_present,
        {
            "present": present,
            "requiredForThisRegime": list(core_names),
            "resourcesRequiredForCostClaim": cost_resources_required,
        },
        "Cost cells require replayable resource evidence; effect cells require only artifacts used by the effect claim.",
        "Required artifact set is complete." if core_present else "Required artifacts for this regime are absent.",
        failure="missing-artifact",
    )
    data: dict[str, Any] = {}
    readers = {
        "resources": ("resources.json", _read_json),
        "plan": ("journey-ledger.plan.json", _read_json),
        "journeys": ("journey-ledger.jsonl", _read_jsonl),
        "witnesses": ("app-witness.jsonl", _read_jsonl),
        "witnessExtraction": ("app-witness-extraction.json", _read_json),
        "serviceLogCapture": ("service-log-capture.json", _read_json),
        "nativeTokenCorrelation": ("native-token-correlation.json", _read_json),
        "nativeTokenExtraction": ("native-token-correlation-extraction.json", _read_json),
        "traces": ("traces.json", _read_json),
        "runtimeImages": ("runtime-images.json", _read_json),
        "capture": ("capture-terminal.json", _read_json),
        "systemSamples": ("system-samples.json", _read_json),
    }
    for key, (name, reader) in readers.items():
        if not present[name]:
            data[key] = None
            continue
        try:
            value = reader(root / name)
            if key == "plan" and not isinstance(value, dict):
                raise ValueError("journey-ledger.plan.json is not an object")
            if key == "traces" and not isinstance(value, list):
                raise ValueError("traces.json is not an array")
            if key == "capture" and not isinstance(value, dict):
                raise ValueError("capture-terminal.json is not an object")
            if key == "runtimeImages" and not isinstance(value, dict):
                raise ValueError("runtime-images.json is not an object")
            if key == "resources" and not isinstance(value, dict):
                raise ValueError("resources.json is not an object")
            if key == "witnessExtraction" and not isinstance(value, dict):
                raise ValueError("app-witness-extraction.json is not an object")
            if key == "serviceLogCapture" and not isinstance(value, dict):
                raise ValueError("service-log-capture.json is not an object")
            if key == "nativeTokenCorrelation" and not isinstance(value, list):
                raise ValueError("native-token-correlation.json is not an array")
            if key == "nativeTokenExtraction" and not isinstance(value, dict):
                raise ValueError("native-token-correlation-extraction.json is not an object")
            data[key] = value
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            data[key] = None
            if key == "resources" and not cost_resources_required:
                data["resourceParseError"] = str(exc)
                continue
            report.check(
                f"{key}-parse", False, str(exc), "Malformed evidence cannot be scored.",
                f"{name} is unreadable.",
                failure="unsupported" if key in {
                    "witnesses", "witnessExtraction", "serviceLogCapture",
                    "nativeTokenCorrelation", "nativeTokenExtraction",
                } else "missing-artifact",
            )
    return receipt, data


def system_samples_check(
    samples: Any, *, no_fault: bool, measurement_start_epoch: float | None,
    window_seconds: float = SYSTEM_SAMPLE_WINDOW_SECONDS, sample_count: int = SYSTEM_SAMPLE_COUNT,
) -> tuple[bool, dict[str, Any]]:
    """Replay the shape of ``system-samples.json`` for one cell.

    Every cell needs 121 samples on the 5 s grid of the 600 s window and every
    required service present in the first sample.  A no-fault cell must have
    every required service in every sample; a fault cell may carry ``null``
    rows (a stopped container has no cgroup scope), which are never zero.
    """
    errors: list[str] = []
    nulls: dict[str, int] = {service: 0 for service in SYSTEM_REQUIRED_SERVICES}
    if not isinstance(samples, dict):
        return False, {"errors": ["system-samples.json is absent or not an object"]}
    if samples.get("schemaVersion") != 1 or samples.get("kind") != SYSTEM_SAMPLES_KIND:
        errors.append("kind or schemaVersion differs")
    if samples.get("intervalSeconds") != SYSTEM_SAMPLE_INTERVAL_SECONDS:
        errors.append("sampling interval differs from 5 s")
    if samples.get("durationSeconds") != window_seconds:
        errors.append(f"sampling duration differs from the {window_seconds:g} s window")
    if samples.get("requiredServices") != list(SYSTEM_REQUIRED_SERVICES):
        errors.append("required service set differs")
    if samples.get("requiredMissingAtStart") != []:
        errors.append("probe reported required services missing at start")
    start = samples.get("startAtEpoch")
    if (
        measurement_start_epoch is None
        or not isinstance(start, (int, float)) or isinstance(start, bool)
        or abs(float(start) - measurement_start_epoch) > 1e-3
    ):
        errors.append("sampling start differs from the shared measurement barrier")
        start = None
    rows = samples.get("samples")
    if not isinstance(rows, list) or len(rows) != sample_count:
        errors.append(
            f"expected {sample_count} samples, got "
            f"{len(rows) if isinstance(rows, list) else None}")
        rows = rows if isinstance(rows, list) else []
    for index, row in enumerate(rows):
        services = row.get("services") if isinstance(row, dict) else None
        if not isinstance(services, dict):
            errors.append(f"sample {index} has no service map")
            continue
        epoch = row.get("epoch")
        if start is not None and (
            not isinstance(epoch, (int, float)) or isinstance(epoch, bool)
            # rel_tol=0: at epoch magnitude (~1.8e9) the default relative
            # tolerance alone would accept a shift of more than a second.
            or not math.isclose(float(epoch), float(start) + index * SYSTEM_SAMPLE_INTERVAL_SECONDS,
                                rel_tol=0.0, abs_tol=1e-6)
        ):
            errors.append(f"sample {index} is off the 5 s grid")
        for service in SYSTEM_REQUIRED_SERVICES:
            if service not in services:
                errors.append(f"sample {index} omits {service}")
                continue
            value = services[service]
            if value is None:
                nulls[service] += 1
                if index == 0 or no_fault:
                    errors.append(f"sample {index} has null {service}")
            elif not isinstance(value, dict) or set(value) != SYSTEM_ROW_KEYS:
                errors.append(f"sample {index} {service} row fields differ")
    observation = {
        "kind": samples.get("kind"),
        "sampleCount": len(rows),
        "noFaultCell": no_fault,
        "nullSamplesByService": nulls,
        "maximumLateSeconds": max(
            (row.get("lateSeconds") for row in rows
             if isinstance(row, dict) and isinstance(row.get("lateSeconds"), (int, float))),
            default=None),
        "errors": errors[:20],
        "errorCount": len(errors),
    }
    return not errors, observation


def _duplicates(values: Iterable[Any]) -> list[Any]:
    counts = Counter(values)
    return sorted((value for value, count in counts.items() if count > 1), key=str)


def _valid_sha1(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(c in "0123456789abcdef" for c in value.lower())


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    # F-ADH-069: this replay is compared bit-for-bit against the workload
    # driver's declaration, so the interpolation must be the driver's exact
    # expression (workload/fixed_load.py percentile) — the algebraically equal
    # subtract-multiply-add form can differ in the last ulp and fail the gate.
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def _phase_for(journey: dict[str, Any], regime: str, intervention: dict[str, Any] | None) -> str:
    if regime == "no-fault-cost":
        return "measurement"
    assert intervention is not None
    start = float(journey["actualStartMonotonic"])
    end = float(journey["actualEndMonotonic"])
    onset = float(intervention["actualOnsetMonotonicOffsetSeconds"])
    offset = float(intervention["actualOffsetMonotonicOffsetSeconds"])
    readiness = float(intervention["readiness"]["observedAtMonotonicOffsetSeconds"])
    # F-ADH-079: identical formula to the extractor's, span-based, so the two
    # partitions cannot disagree on a boundary journey.
    if end <= onset:
        return "before"
    if start >= readiness:
        return "after"
    if start < offset:
        return "during"
    return "recovery"


def _drain_excused(journey: dict[str, Any], regime: str, intervention: Any,
                   timing: dict[str, Any] | None) -> bool:
    """Traffic sweep, Q3: a failed journey that started in [readiness, readiness + allowance) of a fault cell.

    The allowance is the compiled plan's (client timeout + 2 s); frozen and no-fault cells have none, so this is
    False for them and their zero-failure rule is unchanged.
    """
    if not SWEEP or regime not in SCENARIOS or not isinstance(intervention, dict) or not isinstance(timing, dict):
        return False
    if _phase_for(journey, regime, intervention) != "after":
        return False
    return _study_epoch_module().drain_excused(
        journey.get("actualStartMonotonic"),
        intervention["readiness"]["observedAtMonotonicOffsetSeconds"],
        journey.get("outcome"), timing.get("drainAllowanceSeconds"))


NATIVE_BRIDGE_MARKER = "OBSERVABILITY_NATIVE_TRACE_BRIDGE "


def sweep_trace_completeness(
    *, traces: list[Any], journeys: list[dict[str, Any]], auth_log_text: str, intervention: Any,
    timing: dict[str, Any], regime: str, measurement_start_epoch: float, defective_rows: set,
    duplicate_keys: list, logging_seconds: Any, fraction: float,
) -> dict[str, Any]:
    """Shared trace-completeness rule (protocol decision 25), in TeaStore's journey unit, for one sweep cell.

    A journey is incomplete if a record of one of its native traces is defective (``defective_rows``: a
    correlation error, an unresolved parent or a repeated native identity), if one of its traces repeats a
    (message, trace, eoi/ess) identity (``duplicate_keys``) or has an execution-order-index gap, or if none of
    its traces carries the required auth->persistence edge.  Traces are attributed to journeys by the auth
    native-trace bridge in ``auth.log``.  Window (i), fault cells only: start in [onset command issued,
    readiness + drainAllowanceSeconds), recorded, never blocking.  Window (ii): every other journey, and every
    journey of a no-fault cell; the cell blocks only if incomplete (ii) journeys exceed
    max(1, floor(fraction x successful (ii) journeys)).  A defective trace no bridge names is one unattributable
    cluster: inside (i) when the logging time of every defective record lies in window (i), recorded; otherwise
    it counts as one incomplete journey in (ii).
    """
    fault_cell = regime in SCENARIOS
    window_i = None
    if fault_cell:
        stamps = intervention["sweep"]["commandStamps"]
        readiness = float(intervention["readiness"]["observedAtMonotonicOffsetSeconds"])
        window_i = (float(stamps["onsetCommandIssuedMonotonicOffsetSeconds"]),
                    readiness + float(timing["drainAllowanceSeconds"]))
    # bridge: token -> native trace ids (every bridge line, every phase)
    token_traces: dict[str, set] = defaultdict(set)
    for line in auth_log_text.splitlines():
        if NATIVE_BRIDGE_MARKER not in line:
            continue
        row = _strict_json(line.split(NATIVE_BRIDGE_MARKER, 1)[1])
        token_traces[str(row["token"])].add(str(row["nativeTraceId"]))
    events_by_trace: dict[str, list] = defaultdict(list)
    for index, event in enumerate(traces):
        trace_id = _original_native_trace_id(event)
        if trace_id is not None:
            events_by_trace[str(trace_id)].append((index, event))
    # Every defective record counted once, whatever made it defective.
    defect_rows: dict[str, set] = defaultdict(set)
    defect_kinds: dict[str, Counter] = defaultdict(Counter)
    for index in sorted(defective_rows):
        event = traces[index]
        trace_id = str(_original_native_trace_id(event))
        defect_rows[trace_id].add(index)
        for error in (event.get("correlation_errors") or ["unresolved-parent-or-identity"]):
            defect_kinds[trace_id][str(error).split(":")[0]] += 1
    for message, trace_id, _span in duplicate_keys:
        trace_id = str(trace_id)
        defect_kinds[trace_id]["repeated-native-identity"] += 1
        defect_rows[trace_id].update(
            index for index, event in events_by_trace.get(trace_id, []) if event.get("message_sha1") == message)
    for trace_id, rows in events_by_trace.items():
        ordered = sorted(((event["eoi"], index) for index, event in rows
                          if isinstance(event.get("eoi"), int) and not isinstance(event.get("eoi"), bool)),
                         key=lambda pair: pair[0])
        for (previous, _), (following, index) in zip(ordered, ordered[1:]):
            if following - previous > 1:
                defect_kinds[trace_id]["eoi-gap"] += 1
                defect_rows[trace_id].add(index)
    defect_times = {
        trace_id: [float(logging_seconds(traces[index])) - measurement_start_epoch for index in sorted(rows)]
        for trace_id, rows in defect_rows.items()
    }

    def has_required_edge(trace_ids: set) -> bool:
        for trace_id in trace_ids:
            events = [event for _, event in events_by_trace.get(trace_id, [])]
            auth_spans = {event.get("span_id") for event in events if _logical_role(event) == "auth"}
            if any(_logical_role(event) == "persistence" and _parent_id(event) in auth_spans for event in events):
                return True
        return False

    def window_of_start(start: float) -> str:
        if window_i is None:
            return "whole-measurement"
        if start < window_i[0]:
            return "pre-onset"
        return "fault-and-drain" if start < window_i[1] else "after-drain"

    names = ["fault-and-drain", "pre-onset", "after-drain"] if fault_cell else ["whole-measurement"]
    windows = {name: {"journeys": 0, "successfulJourneys": 0, "untracedJourneys": 0, "incompleteJourneys": 0,
                      "incompleteJourneyIds": [], "reasons": Counter(), "unattributableClusters": 0,
                      "unattributableTraceIds": [], "defectiveRecordsByLoggingTime": 0} for name in names}
    attributed: set = set()
    for journey in journeys:
        start = journey.get("actualStartMonotonic")
        name = window_of_start(float(start if start is not None else journey["actualEndMonotonic"]))
        bucket = windows[name]
        bucket["journeys"] += 1
        bucket["successfulJourneys"] += int(journey.get("outcome") == "succeeded")
        trace_ids = token_traces.get(str(journey.get("opaqueToken")), set())
        attributed |= trace_ids
        if not trace_ids:
            bucket["untracedJourneys"] += 1
            continue
        reasons = sorted({kind for trace_id in trace_ids for kind in defect_kinds.get(trace_id, {})})
        if not has_required_edge(trace_ids):
            reasons.append("missing-auth-persistence-edge")
        if reasons:
            bucket["incompleteJourneys"] += 1
            bucket["incompleteJourneyIds"].append(journey.get("journeyId"))
            bucket["reasons"].update(reasons)
    for trace_id in sorted(set(defect_kinds) - attributed):
        times = defect_times.get(trace_id) or [math.inf]
        inside = window_i is not None and all(window_i[0] <= value < window_i[1] for value in times)
        name = "fault-and-drain" if inside else (
            "whole-measurement" if window_i is None else "pre-onset" if min(times) < window_i[0] else "after-drain")
        windows[name]["unattributableClusters"] += 1
        windows[name]["unattributableTraceIds"].append(trace_id)
    for trace_id, times in defect_times.items():
        for value in times:
            name = ("whole-measurement" if window_i is None else "pre-onset" if value < window_i[0]
                    else "fault-and-drain" if value < window_i[1] else "after-drain")
            windows[name]["defectiveRecordsByLoggingTime"] += 1
    rule_two = [name for name in names if name != "fault-and-drain"]
    incomplete_ii = sum(windows[name]["incompleteJourneys"] + windows[name]["unattributableClusters"]
                        for name in rule_two)
    successful_ii = sum(windows[name]["successfulJourneys"] for name in rule_two)
    allowance = max(1, int(math.floor(fraction * successful_ii + 1e-9)))
    for bucket in windows.values():
        bucket["reasons"] = dict(sorted(bucket["reasons"].items()))   # every id is kept: (iii) reports them all
    return {
        "rule": "protocol decision 25 (shared trace-completeness rule), journey unit",
        "windowIMonotonicSeconds": list(window_i) if window_i is not None else None,
        "fraction": fraction,
        "successfulJourneysInRuleTwo": successful_ii,
        "incompleteInRuleTwo": incomplete_ii,
        "allowance": allowance,
        "blocking": incomplete_ii > allowance,
        "windows": windows,
    }


def _candidate_spool_observation(
    root: Path,
    receipt: dict[str, Any],
    runtime_images: dict[str, Any],
    traces: list[Any],
) -> tuple[bool, Any]:
    """Replay raw AMQP bytes and bind exact collector attribution/counters."""

    try:
        native = _native_collector()
        runtime_path = root / "runtime-images.json"
        runtime_aliases = native.load_runtime_host_service_map(runtime_path)
        configuration, configuration_sha256 = native.frozen_attribution_configuration(
            runtime_aliases,
        )
        replayed, spool_summary, counts = native.replay_spooled_events(
            root / "kieker-amqp.spool",
            re.compile(native.DEFAULT_SERVICE_REGEX),
            native.DEFAULT_SERVICE_MAP,
            configuration["effectiveHostAliases"],
        )
        if spool_summary.get("complete") is not True:
            raise ValueError(f"raw spool is incomplete: {spool_summary.get('blockers')}")
        if replayed != traces:
            raise ValueError("traces.json differs from independent raw-spool replay")
        posture = receipt.get("run", {}).get("posture")
        # F-ADH-084: identical formula to performance_campaign / srv5_terminal.
        # The diagnostics are re-derived from the retained bytes here, so a
        # rejected container is netted out only when those bytes themselves
        # prove it is the intervention's own restart banner inside its window.
        try:
            failures = native.spool_container_parse_diagnostics(root / "kieker-amqp.spool")
        except Exception as exc:  # noqa: BLE001 - an unreadable spool tolerates nothing
            raise ValueError(f"container parse diagnostics failed: {type(exc).__name__}: {exc}")
        if len(failures) != counts["containers_bad"]:
            raise ValueError("candidate container parse diagnostics do not account for every rejection")
        # SCENARIOS is the authoritative regime -> fault map; no-fault-cost has
        # no entry, so a cost cell can never net out a rejected container.
        tolerance = _queue_checker().exposure_tolerance(
            replayed, receipt.get("intervention"),
            fault=SCENARIOS.get(receipt.get("run", {}).get("regime"), "none"),
            container_failures=failures,
        )
        if (counts["containers_bad"] - tolerance["toleratedContainerParseFailures"] != 0
                or counts["records_bad"] != 0):
            raise ValueError("candidate raw spool contains parse failures")
        if posture == "none":
            if (counts["messages"] != 0 or counts["containers_ok"] != 0
                    or counts["records_ok"] != 0 or replayed != []
                    or spool_summary.get("deliveryCount") != 0
                    or spool_summary.get("uniqueBodyCount") != 0
                    or spool_summary.get("rawBodyBytes") != 0):
                raise ValueError("none posture raw spool is not exactly empty")
        elif posture in {"selected", "full"}:
            if (counts["messages"] <= 0 or counts["containers_ok"] <= 0
                    or counts["records_ok"] <= 0 or not replayed):
                raise ValueError("instrumented posture raw spool is empty")
        else:
            raise ValueError("candidate posture is invalid for raw-spool replay")

        telemetry = receipt.get("telemetry")
        stats = telemetry.get("collectorStats") if isinstance(telemetry, dict) else None
        expected_stat_fields = {
            "messages", "containers_ok", "containers_bad", "records_ok", "records_bad",
            "record_parse_success_ratio", "container_parse_success_ratio",
            "acknowledgement_mode", "runtime_host_map_loaded",
            "attribution_configuration", "attribution_configuration_sha256",
            "correlation", "spool",
        }
        if not isinstance(stats, dict) or set(stats) != expected_stat_fields:
            raise ValueError("collector stats fields differ from candidate schema v2")
        for field, expected in counts.items():
            if stats.get(field) != expected or type(stats.get(field)) is not int:
                raise ValueError(f"collector counter differs from spool replay: {field}")
        record_total = counts["records_ok"] + counts["records_bad"]
        container_total = counts["containers_ok"] + counts["containers_bad"]
        expected_record_ratio = counts["records_ok"] / record_total if record_total else 0.0
        expected_container_ratio = (
            counts["containers_ok"] / container_total if container_total else 0.0
        )
        if (stats.get("record_parse_success_ratio") != expected_record_ratio
                or stats.get("container_parse_success_ratio") != expected_container_ratio
                or stats.get("acknowledgement_mode") != "manual"
                or stats.get("runtime_host_map_loaded") is not True
                or stats.get("attribution_configuration") != configuration
                or stats.get("attribution_configuration_sha256") != configuration_sha256
                or stats.get("spool") != spool_summary):
            raise ValueError("collector terminal projection differs from spool/config replay")

        parent_states = Counter(event.get("parent_resolution") for event in replayed)
        attribution_states = Counter(
            event.get("service_attribution_status") for event in replayed
        )
        native = _native_collector()
        expected_correlation = {
            "events": len(replayed),
            "parentResolution": dict(parent_states),
            "serviceAttribution": dict(attribution_states),
            "eventsWithCorrelationErrors": sum(
                bool(event.get("correlation_errors")) for event in replayed
            ),
            "eventsWithUnwovenRootParent": native.count_unwoven_root_parents(replayed),
            "eventsWithProbeOrphanRoot": native.count_probe_orphan_roots(replayed),
            "eventsWithCorrelationWarnings": sum(
                bool(event.get("correlation_warnings")) for event in replayed
            ),
            "eventsWithServiceAttributionErrors": sum(
                bool(event.get("service_attribution_errors")) for event in replayed
            ),
            "traceCompleteness": native.trace_completeness(
                native.collect_trace_eois(replayed)),
        }
        if stats.get("correlation") != expected_correlation:
            raise ValueError("collector correlation summary differs from replayed events")
        source = receipt.get("source")
        if not isinstance(source, dict):
            raise ValueError("receipt source is absent")
        bindings = {
            "spoolSha256": hashlib.sha256(
                (root / "kieker-amqp.spool").read_bytes()
            ).hexdigest(),
            "runtimeImagesSha256": hashlib.sha256(
                (root / "runtime-images.json").read_bytes()
            ).hexdigest(),
            "collectorAttributionConfigurationSha256": configuration_sha256,
        }
        if any(source.get(field) != value for field, value in bindings.items()):
            raise ValueError("receipt source does not bind spool/runtime attribution inputs")
        return True, {
            "counts": counts,
            "spool": spool_summary,
            "attributionConfigurationSha256": configuration_sha256,
            "runtimeServiceCount": len(runtime_images.get("services", {})),
        }
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


def validate_run(root: Path, expected: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate one immutable run directory and return a machine-readable table."""
    root = Path(root)
    report = _Report()
    receipt, data = _artifact_load(root, report)
    if receipt is None:
        return _base_result(report)

    run = receipt.get("run") if isinstance(receipt.get("run"), dict) else {}
    run_key = {
        "studyEpoch": receipt.get("studyEpoch"),
        "regime": run.get("regime"),
        "block": run.get("block"),
        "posture": run.get("posture"),
        "attempt": run.get("attempt"),
    }
    result = _base_result(report, run_key)
    regime = run.get("regime")
    posture = run.get("posture")

    # Run-level numbers.  Frozen epoch: the c1724b1 literals.  Traffic sweep: the compiled cell's timing, after
    # the receipt's copy has been checked against the compiled plan (a receipt cannot bring its own numbers).
    timing: dict[str, Any] | None = None
    if SWEEP:
        try:
            timing = _sweep_timing(receipt, run_key)
            timing_observation: Any = {"runId": run.get("runId"), "timing": timing}
        except Exception as exc:  # noqa: BLE001 - plan replay must fail closed
            timing_observation = f"{type(exc).__name__}: {exc}"
        report.check(
            "sweep-compiled-timing", timing is not None, timing_observation,
            "Rate, measurement, onset, hold and floors are plan values of the compiled sweep cell; the receipt's copy must equal them byte for byte.",
            "The receipt carries its compiled cell's timing." if timing is not None
            else "The receipt's timing is absent or differs from the compiled sweep plan.",
        )
    design = {
        "warmupSeconds": 120, "measurementSeconds": 600, "rate": 0.15, "offered": 90,
        "population": POPULATION, "onsetSeconds": 180, "holdSeconds": 150,
        "phaseFloors": {"before": 20, "during": 20, "after": 20},
        "systemWindowSeconds": SYSTEM_SAMPLE_WINDOW_SECONDS, "systemSampleCount": SYSTEM_SAMPLE_COUNT,
        "journeyKind": "login-browse",
    } if not SWEEP else {
        "warmupSeconds": (timing or {}).get("warmupSeconds"),
        "measurementSeconds": (timing or {}).get("measurementSeconds"),
        "rate": (timing or {}).get("journeysPerSecond"),
        "offered": (timing or {}).get("offered"),
        "population": (timing or {}).get("workloadId"),
        "onsetSeconds": (timing or {}).get("faultOnsetSeconds"),
        "holdSeconds": (timing or {}).get("faultHoldSeconds"),
        "phaseFloors": (timing or {}).get("minimumActualStartsByPhase"),
        "systemWindowSeconds": float((timing or {}).get("measurementSeconds") or 0.0),
        "systemSampleCount": (timing or {}).get("systemSampleCount"),
        "journeyKind": (timing or {}).get("journeyKind"),
    }
    offered_design = design["offered"]

    identity_ok = (
        receipt.get("schemaVersion") == 2
        and receipt.get("contract") == CONTRACT
        and receipt.get("studyEpoch") == STUDY_EPOCH
        and regime in REGIMES
        and posture in POSTURES
        and type(run.get("block")) is int and 1 <= run["block"] <= EPOCH["blocksPerRegime"]
        and type(run.get("attempt")) is int and run["attempt"] == 1
        and isinstance(run.get("runId"), str) and bool(run["runId"])
        and receipt.get("population") == design["population"]
        and (
            (posture == "selected" and receipt.get("selectionId") == "fault-qualification")
            or (posture in {"none", "full"} and receipt.get("selectionId") is None)
        )
    )
    report.check(
        "frozen-run-identity", identity_ok, run_key | {
            "contract": receipt.get("contract"), "population": receipt.get("population"),
            "selectionId": receipt.get("selectionId"),
        },
        "The endpoint is meaningful only for the frozen epoch, population, posture, and first attempt.",
        "Run identity matches the frozen candidate pilot." if identity_ok else "Run identity drifted.",
    )
    try:
        operational_proofs = validate_operational_proofs(root, posture=posture)
        operational_ok = True
    except Exception as exc:  # noqa: BLE001 - evidence replay must fail closed
        operational_proofs = f"{type(exc).__name__}: {exc}"
        operational_ok = False
    report.check(
        "posture-and-queue-semantic-replay", operational_ok, operational_proofs,
        "Catalog closure, required/forbidden groups, AOP bytes, purge, barrier, collector exclusivity, and terminal drain must replay from retained artifacts.",
        "Posture and queue proofs semantically replay." if operational_ok
        else "Posture or queue proof does not semantically replay.",
        failure="unsupported",
    )
    # F-ADH-066: gates whose expectations depend on per-request trace shape are
    # keyed on the replayed closure (which activation groups were actually
    # woven), not on the posture name, so a future placement sweep cannot
    # silently inherit selected-specific relaxations. An unresolved closure
    # stays strict (entry point treated as woven).
    closure_groups = (
        operational_proofs.get("requiredGroups")
        if operational_ok and isinstance(operational_proofs, dict) else None
    )
    try:
        _native = _native_collector()
        entry_woven = bool(_native.entry_point_woven(closure_groups))
        unwoven_root_error = str(_native.UNWOVEN_ROOT_PARENT_ERROR)
    except Exception:  # noqa: BLE001 - closure resolution must fail closed (strict)
        entry_woven = True
        unwoven_root_error = "missing-parent-at-depth-0"
    source = receipt.get("source") if isinstance(receipt.get("source"), dict) else {}
    provenance_ok = (
        source.get("sutCommit") == SUT_COMMIT
        and isinstance(source.get("frameworkCommit"), str) and len(source["frameworkCommit"]) == 40
        and all(character in "0123456789abcdef" for character in source["frameworkCommit"].lower())
        and source.get("frameworkDirty") is False
        and source.get("host") == "fb14srv5"
        and source.get("exclusiveLease") is True
        and isinstance(source.get("imageDigests"), dict) and bool(source["imageDigests"])
        and all(isinstance(value, str) and "@sha256:" in value for value in source["imageDigests"].values())
    )
    report.check(
        "provenance-and-host-lease", provenance_ok, source,
        "The frozen SUT, clean harness, immutable images, and exclusive authorized host bound the observation domain.",
        "Source, images, and host lease are proven." if provenance_ok else "Source or host provenance is incomplete.",
    )
    if expected is not None:
        expected_ok = all(
            type(run_key.get(key)) is type(value) and run_key.get(key) == value
            for key, value in expected.items() if key != "runId"
        ) and ("runId" not in expected or run.get("runId") == expected["runId"])
        report.check(
            "campaign-run-binding", expected_ok,
            {"expected": expected, "observed": run_key},
            "A receipt cannot choose a more convenient scheduled cell after observing outcomes.",
            "Receipt matches its independently scheduled cell." if expected_ok else "Receipt does not match its scheduled cell.",
        )

    artifacts = receipt.get("artifacts") if isinstance(receipt.get("artifacts"), dict) else {}
    hash_observed: dict[str, Any] = {}
    hashes_ok = True
    required_sidecars = tuple(
        name for name in REQUIRED_FILES[1:]
        if name != "resources.json" or regime == "no-fault-cost"
    )
    for name in required_sidecars:
        if (root / name).is_file():
            actual = _sha256(root / name)
            declared = artifacts.get(name, {}).get("sha256") if isinstance(artifacts.get(name), dict) else None
            hash_observed[name] = {"declared": declared, "actual": actual}
            hashes_ok &= declared == actual
        else:
            hashes_ok = False
    missing_sidecars = [name for name in required_sidecars if not (root / name).is_file()]
    witness_sidecars = {
        "auth.log", "persistence.log", "app-witness.jsonl", "app-witness-extraction.json",
        "service-log-capture.json", "native-token-correlation.json",
        "native-token-correlation-extraction.json",
    }
    if missing_sidecars and set(missing_sidecars) <= witness_sidecars:
        hash_failure_class = "unsupported"
    elif any(name not in witness_sidecars for name in missing_sidecars):
        hash_failure_class = "missing-artifact"
    else:
        hash_failure_class = "invalid"
    report.check(
        "artifact-hash-binding", hashes_ok, hash_observed,
        "Sidecars must be the exact bytes named by the immutable receipt.",
        "All sidecar hashes reconcile." if hashes_ok else "One or more sidecars are unbound or changed.",
        failure=hash_failure_class,
    )

    window = receipt.get("window") if isinstance(receipt.get("window"), dict) else {}
    window_ok = False
    measurement_start = measurement_end = None
    try:
        warmup_start = _iso(window["warmupStartedAt"])
        warmup_end = _iso(window["warmupEndedAt"])
        warmup_settled = _iso(window["warmupSettledAt"])
        measurement_start = _iso(window["measurementStartedAt"])
        measurement_end = _iso(window["measurementEndedAt"])
        wall_warmup = (warmup_end - warmup_start).total_seconds()
        setup_gap = (measurement_start - warmup_end).total_seconds()
        settled_gap = (measurement_start - warmup_settled).total_seconds()
        wall_measurement = (measurement_end - measurement_start).total_seconds()
        mono_measurement = float(window["measurementEndMonotonic"]) - float(window["measurementStartMonotonic"])
        window_ok = (
            type(window.get("warmupDurationSeconds")) is int
            and window["warmupDurationSeconds"] == design["warmupSeconds"]
            and math.isclose(wall_warmup, float(design["warmupSeconds"]), abs_tol=1e-6)
            and setup_gap >= 0.0
            and settled_gap >= 0.0
            and warmup_start <= warmup_settled
            and math.isclose(wall_measurement, float(design["measurementSeconds"]), abs_tol=1.0)
            and math.isclose(mono_measurement, float(design["measurementSeconds"]), abs_tol=0.1)
            and bool(window.get("sharedBarrierId"))
        )
        window_observation: Any = {
            "wallWarmupSeconds": wall_warmup,
            "setupGapSeconds": setup_gap,
            "warmupSettledBeforeMeasurementSeconds": settled_gap,
            "wallMeasurementSeconds": wall_measurement,
            "monotonicMeasurementSeconds": mono_measurement,
            "sharedBarrierId": window.get("sharedBarrierId"),
        }
    except (KeyError, TypeError, ValueError) as exc:
        window_observation = str(exc)
    report.check(
        "shared-window", window_ok, window_observation,
        "The frozen 120 s warm-up is retained separately from the non-negative setup gap before the shared 600 s measurement clock.",
        "Warm-up, setup gap, and measurement boundaries match the frozen design." if window_ok else "Window or shared barrier is invalid.",
    )

    plan = data.get("plan")
    ledger_records = data.get("journeys")
    witnesses = data.get("witnesses")
    witness_extraction = data.get("witnessExtraction")
    native_token_correlation = data.get("nativeTokenCorrelation")
    traces = data.get("traces")
    runtime_images = data.get("runtimeImages")
    capture = data.get("capture")
    if not isinstance(plan, dict):
        plan = {}
    if not isinstance(ledger_records, list):
        ledger_records = []
    if not isinstance(witnesses, list):
        witnesses = []
    if not isinstance(witness_extraction, dict):
        witness_extraction = {}
    if not isinstance(native_token_correlation, list):
        native_token_correlation = []
    if not isinstance(traces, list):
        traces = []
    if not isinstance(runtime_images, dict):
        runtime_images = {}
    if not isinstance(capture, dict):
        capture = {}

    plan_keys = {
        "artifactType", "schemaVersion", "workloadId", "barrierId",
        "controllerStartedAt", "barrierAt", "clock", "schedule",
        "expectedPath", "tokenContract", "opportunities",
    }
    opportunity_keys = {
        "sequence", "journeyId", "opportunityId", "opaqueToken", "tokenAllocatedAt",
        "scheduledAt", "scheduledMonotonicOffsetSeconds",
    }
    common_record_keys = {
        "artifactType", "schemaVersion", "recordType", "recordSequence",
        "previousRecordSha256", "recordSha256", "planSha256", "workloadId", "barrierId",
    }
    terminal_record_keys = common_record_keys | {
        "sequence", "journeyId", "opportunityId", "opaqueToken", "tokenAllocatedAt",
        "scheduledAt", "scheduledMonotonicOffsetSeconds", "actualStartMonotonic",
        "actualEndMonotonic", "startedAt", "endedAt", "expectedPath", "requests",
        "requestCount", "outcome", "errors", "terminalSettled", "endedAfterNominalWindow",
    }
    reconciliation_record_keys = common_record_keys | {
        "state", "terminalReason", "expectedJourneys", "terminalJourneys",
        "terminalJourneyIdsSha256", "terminalOpportunityIdsSha256", "finalizedAt",
        "terminalSettled",
    }
    plan_errors: list[str] = []
    opportunities_plan: list[dict[str, Any]] = []
    try:
        if set(plan) != plan_keys:
            raise ValueError(f"plan keys differ: {sorted(set(plan) ^ plan_keys)}")
        if (plan["artifactType"] != "teastore-expected-opportunity-plan"
                or plan["schemaVersion"] != 1 or plan["workloadId"] != design["population"]
                or plan["barrierId"] != window.get("sharedBarrierId")
                or plan["clock"] != {
                    "wallClock": "UTC", "monotonicValues": "seconds-relative-to-barrier"
                }
                or plan["schedule"] != {
                    "kind": "fixed-open-loop", "journeysPerSecond": design["rate"],
                    "durationSeconds": design["measurementSeconds"], "offered": offered_design,
                }
                or plan["expectedPath"] != EXPECTED_PATH
                or plan["tokenContract"] != TOKEN_CONTRACT):
            raise ValueError("plan contract differs")
        controller_started = _iso(plan["controllerStartedAt"])
        plan_barrier = _iso(plan["barrierAt"])
        if controller_started > plan_barrier or plan_barrier != measurement_start:
            raise ValueError("plan/controller/barrier timestamps differ")
        opportunities_plan = plan["opportunities"]
        if not isinstance(opportunities_plan, list) or len(opportunities_plan) != offered_design:
            raise ValueError(f"plan does not contain {offered_design} opportunities")
        planned_journey_ids: set[str] = set()
        planned_opportunity_ids: set[str] = set()
        for index, opportunity in enumerate(opportunities_plan):
            if set(opportunity) != opportunity_keys:
                raise ValueError(f"opportunity {index} keys differ")
            offset = index / design["rate"]
            journey_id = opportunity.get("journeyId")
            opaque_token = opportunity.get("opaqueToken")
            opportunity_id = opportunity.get("opportunityId")
            if (opportunity["sequence"] != index
                    or not isinstance(journey_id, str) or not journey_id.startswith("journey-")
                    or len(journey_id) != 40
                    or any(character not in "0123456789abcdef" for character in journey_id[8:])
                    or opaque_token != journey_id
                    or opportunity_id != f"{design['population']}:{index:06d}"
                    or journey_id in planned_journey_ids
                    or opportunity_id in planned_opportunity_ids
                    or not math.isclose(float(opportunity["scheduledMonotonicOffsetSeconds"]), offset,
                                        abs_tol=1e-9)
                    # F-ADH-070: the plan producer truncates fractional-second
                    # schedule offsets to microseconds while timedelta rounds
                    # them, so exact datetime equality aborts on a one-microsecond
                    # rounding difference that depends on the barrier's own
                    # microseconds. Mirror the workload driver's own acceptance
                    # (fixed_load plan validation: +/-1 microsecond, and 1 ms of
                    # token-allocation clock slack) instead of being stricter
                    # than the system's producing contract.
                    or abs((_iso(opportunity["scheduledAt"])
                            - (plan_barrier + timedelta(seconds=offset))).total_seconds()) > 1e-6
                    or not (controller_started - timedelta(milliseconds=1)
                            ) <= _iso(opportunity["tokenAllocatedAt"]) <= plan_barrier):
                raise ValueError(f"opportunity {index} schedule or allocation differs")
            planned_journey_ids.add(journey_id)
            planned_opportunity_ids.add(opportunity_id)
    except (KeyError, TypeError, ValueError) as exc:
        plan_errors.append(str(exc))

    journeys = [row for row in ledger_records if row.get("recordType") == "journey-terminal"]
    reconciliations = [row for row in ledger_records if row.get("recordType") == "reconciliation"]
    chain_errors: list[str] = []
    try:
        plan_sha = _canonical_sha256(plan)
        previous = "0" * 64
        for index, record in enumerate(ledger_records):
            expected_keys = (
                terminal_record_keys if index < offered_design else reconciliation_record_keys)
            if set(record) != expected_keys:
                raise ValueError(f"record {index} keys differ: {sorted(set(record) ^ expected_keys)}")
            if (record["artifactType"] != "teastore-journey-ledger-record"
                    or record["schemaVersion"] != 1
                    or record["recordSequence"] != index
                    or record["previousRecordSha256"] != previous
                    or record["planSha256"] != plan_sha
                    or record["workloadId"] != design["population"]
                    or record["barrierId"] != plan.get("barrierId")):
                raise ValueError(f"record {index} binding differs")
            without_self = {key: value for key, value in record.items() if key != "recordSha256"}
            actual_self = _canonical_sha256(without_self)
            if record["recordSha256"] != actual_self:
                raise ValueError(f"record {index} self hash differs")
            previous = actual_self
        if (len(ledger_records) != offered_design + 1 or len(journeys) != offered_design
                or len(reconciliations) != 1):
            raise ValueError(
                f"ledger must contain {offered_design} terminal rows and one reconciliation")
        reconciliation = reconciliations[0]
        if reconciliation is not ledger_records[-1]:
            raise ValueError("reconciliation is not the final record")
        journey_ids = sorted(str(row["journeyId"]) for row in journeys)
        opportunity_ids = sorted(str(row["opportunityId"]) for row in journeys)
        if (reconciliation["state"] != "completed"
                or reconciliation["terminalReason"] is not None
                or reconciliation["expectedJourneys"] != offered_design
                or reconciliation["terminalJourneys"] != offered_design
                or reconciliation["terminalJourneyIdsSha256"] != _canonical_sha256(journey_ids)
                or reconciliation["terminalOpportunityIdsSha256"] != _canonical_sha256(opportunity_ids)
                or reconciliation["terminalSettled"] is not True
                or _iso(reconciliation["finalizedAt"]) < measurement_start):
            raise ValueError("terminal reconciliation differs")
        if len(opportunities_plan) == offered_design:
            # F-ADH-081: the driver appends terminal rows in COMPLETION order
            # under a lock, so two journeys timing out together under a fault
            # land swapped relative to the schedule (rows 27/28, 11 ms apart,
            # on the campaign #8 cell). Bind each row to its opportunity by id
            # and require the id sets to coincide; the hash chain above already
            # pins the order the rows were actually written in.
            planned = {str(row["opportunityId"]): row for row in opportunities_plan}
            if sorted(planned) != opportunity_ids:
                raise ValueError("terminal opportunity ids differ from the pre-outcome plan")
            bound_fields = (
                "sequence", "journeyId", "opportunityId", "opaqueToken", "tokenAllocatedAt",
                "scheduledAt", "scheduledMonotonicOffsetSeconds",
            )
            for journey in journeys:
                opportunity = planned[str(journey["opportunityId"])]
                if any(journey[field] != opportunity[field] for field in bound_fields):
                    raise ValueError(
                        f"terminal row {journey['opportunityId']} differs from its pre-outcome opportunity")
    except (KeyError, TypeError, ValueError) as exc:
        chain_errors.append(str(exc))
    ledger_binding_ok = not plan_errors and not chain_errors
    report.check(
        "pre-outcome-plan-and-ledger-chain", ledger_binding_ok,
        {"planErrors": plan_errors, "chainErrors": chain_errors,
         "planOpportunities": len(opportunities_plan), "terminalRecords": len(journeys),
         "reconciliationRecords": len(reconciliations)},
        "Expected opportunities are frozen before outcomes, then terminal rows are hash-chained and reconciled one-to-one.",
        "Pre-outcome plan and terminal ledger reconcile." if ledger_binding_ok else "Opportunity plan or ledger chain is invalid.",
        failure="unsupported",
    )

    offered = receipt.get("workload", {}).get("offered") if isinstance(receipt.get("workload"), dict) else None
    ids = [row.get("journeyId") for row in journeys]
    opportunities = [row.get("opportunityId") for row in journeys]
    tokens = [row.get("opaqueToken") for row in journeys]
    ledger_shape_ok = (
        offered == offered_design == len(journeys)
        and not _duplicates(ids) and None not in ids
        and not _duplicates(opportunities) and None not in opportunities
        and not _duplicates(tokens) and None not in tokens and "" not in tokens
    )
    report.check(
        "offered-ledger-denominator", ledger_shape_ok,
        {"receiptOffered": offered, "ledgerRows": len(journeys),
         "duplicateJourneyIds": _duplicates(ids), "duplicateOpportunityIds": _duplicates(opportunities),
         "duplicateOpaqueTokens": _duplicates(tokens)},
        "One pre-allocated row per offered journey is the workload and expected-opportunity denominator.",
        f"Ledger has {offered_design} unique offered opportunities." if ledger_shape_ok else "Ledger denominator is incomplete or duplicated.",
    )

    barrier_id = window.get("sharedBarrierId")
    row_errors: list[dict[str, Any]] = []
    for index, journey in enumerate(journeys):
        try:
            allocated = _iso(journey["tokenAllocatedAt"])
            started = _iso(journey["startedAt"])
            ended = _iso(journey["endedAt"])
            actual_start = float(journey["actualStartMonotonic"])
            actual_end = float(journey["actualEndMonotonic"])
            scheduled = float(journey["scheduledMonotonicOffsetSeconds"])
            requests = journey["requests"]
            steps = [request.get("step") for request in requests]
            routes = {
                "login": "login-action", "browse-home": "home", "browse-category": "category",
                "browse-product": "product", "return-home": "home",
            }
            for request_index, request in enumerate(requests):
                request_start = _iso(request["startedAt"])
                request_end = _iso(request["endedAt"])
                request_start_mono = float(request["actualStartMonotonic"])
                request_end_mono = float(request["actualEndMonotonic"])
                if not (
                    set(request) == {
                        "sequence", "step", "routeId", "target", "actualStartMonotonic",
                        "actualEndMonotonic", "startedAt", "endedAt", "latencyMs",
                        "statusCode", "outcome", "error",
                    }
                    and request.get("sequence") == request_index
                    and request.get("step") in routes
                    and request.get("routeId") == routes[request["step"]]
                    and isinstance(request.get("target"), str) and request["target"].startswith("/")
                    and started <= request_start <= request_end <= ended
                    and actual_start <= request_start_mono <= request_end_mono <= actual_end
                    and math.isclose(
                        float(request["latencyMs"]),
                        (request_end_mono - request_start_mono) * 1000, abs_tol=1.0,
                    )
                    and request.get("outcome") in {"succeeded", "failed"}
                    and (request.get("statusCode") is None or (
                        isinstance(request.get("statusCode"), int)
                        and not isinstance(request.get("statusCode"), bool)
                        and 100 <= request["statusCode"] <= 599
                    ))
                    and (request.get("error") is None or (
                        isinstance(request.get("error"), dict)
                        and set(request["error"]) == {"type"}
                        and isinstance(request["error"]["type"], str)
                    ))
                    and ((request.get("outcome") == "succeeded") is (request.get("error") is None))
                ):
                    raise ValueError("request timestamp outside journey")
            valid = (
                allocated <= started <= ended
                and actual_start <= actual_end
                and scheduled >= 0
                and journey.get("barrierId") == barrier_id
                and journey.get("expectedPath") == EXPECTED_PATH
                and ((
                    design["journeyKind"] == "login-browse"
                    and len(steps) >= 3 and steps[0:2] == ["login", "browse-home"]
                    and steps[-1] == "return-home"
                    and steps.count("browse-category") <= 3
                    and steps.count("browse-product") <= 9
                ) or (
                    # Traffic sweep: one login request per journey (an unanswered login still
                    # leaves its one request row).
                    design["journeyKind"] == "login-only" and steps == ["login"]
                ))
                and journey.get("requestCount") == len(requests)
                and journey.get("outcome") in {"succeeded", "failed", "timeout", "interrupted", "aborted"}
                and isinstance(journey.get("errors"), list)
                and all(
                    isinstance(error, dict) and set(error) == {"type", "scope", "requestSequence"}
                    and isinstance(error["type"], str)
                    and error["scope"] in {"journey", "request"}
                    and (error["requestSequence"] is None or isinstance(error["requestSequence"], int))
                    for error in journey["errors"]
                )
                and journey.get("terminalSettled") is True
                and measurement_start is not None and measurement_end is not None
                and measurement_start <= started < measurement_end
                and journey.get("endedAfterNominalWindow") is (ended > measurement_end)
                and math.isclose(
                    actual_start,
                    (started - measurement_start).total_seconds(), abs_tol=1.0,
                )
                and math.isclose(
                    actual_end,
                    (ended - measurement_start).total_seconds(), abs_tol=1.0,
                )
            )
            if not valid:
                raise ValueError("field or ordering constraint failed")
        except (KeyError, TypeError, ValueError) as exc:
            row_errors.append({"row": index + 1, "error": str(exc)})
    report.check(
        "journey-ledger-integrity", not row_errors,
        {"invalidRows": row_errors[:20], "invalidRowCount": len(row_errors)},
        "Tokens must predate outcomes, requests must be bounded, and every row must settle on the shared barrier.",
        "Journey rows are temporally and structurally complete." if not row_errors else "Journey rows are malformed or unsettled.",
    )

    outcome_counts = Counter(row.get("outcome") for row in journeys)
    successful_durations = [
        (float(row["actualEndMonotonic"]) - float(row["actualStartMonotonic"])) * 1000
        for row in journeys if row.get("outcome") == "succeeded"
        and isinstance(row.get("actualStartMonotonic"), (int, float))
        and isinstance(row.get("actualEndMonotonic"), (int, float))
    ]
    workload_receipt = receipt.get("workload") if isinstance(receipt.get("workload"), dict) else {}
    latency_receipt = receipt.get("latencyMs") if isinstance(receipt.get("latencyMs"), dict) else {}
    computed_latency = {
        "denominator": "successful-journeys",
        "count": len(successful_durations),
        "p50": _percentile(successful_durations, 0.50),
        "p95": _percentile(successful_durations, 0.95),
        "p99": _percentile(successful_durations, 0.99),
        # F-ADH-069: the driver declares statistics.fmean; a naive sum/len can
        # differ in the last ulp and fail the bit-for-bit comparison below.
        "mean": statistics.fmean(successful_durations) if successful_durations else None,
    }
    denominator_ok = (
        workload_receipt.get("offered") == len(journeys)
        and workload_receipt.get("successful") == outcome_counts["succeeded"]
        and workload_receipt.get("failed") == outcome_counts["failed"]
        and workload_receipt.get("timedOut") == outcome_counts["timeout"]
        and workload_receipt.get("requests") == sum(len(row.get("requests", [])) for row in journeys)
        and outcome_counts["interrupted"] == 0 and outcome_counts["aborted"] == 0
        and latency_receipt == computed_latency
    )
    report.check(
        "outcome-and-latency-denominators", denominator_ok,
        {"declaredWorkload": workload_receipt, "computedOutcomes": dict(outcome_counts),
         "declaredLatencyMs": latency_receipt, "computedLatencyMs": computed_latency},
        "Offered journeys define burden; only successful journeys define latency, and an empty latency is null rather than zero.",
        "Outcome and latency denominators reconcile." if denominator_ok else "Outcome or latency denominator drifted.",
    )

    intervention = receipt.get("intervention")
    analysis_kind = receipt.get("analysisKind")
    resource_use = receipt.get("resourceUse")
    resources = data.get("resources")
    resource_receipt = receipt.get("resources") if isinstance(receipt.get("resources"), dict) else {}
    if regime == "no-fault-cost":
        resource_replay: dict[str, Any] = {
            "verdict": "blocked", "blockers": ["missing resources.json"],
        }
        resource_projection_ok = False
        resource_observation: dict[str, Any] = {"replay": resource_replay}
        if isinstance(resources, dict) and measurement_start is not None:
            try:
                resource_replay = _resource_validator().validate_resource_evidence(
                    resources,
                    required_services={"auth", "image", "persistence", "recommender", "webui"},
                    expected_barrier_id=window.get("sharedBarrierId"),
                    expected_start_epoch=measurement_start.timestamp(),
                    expected_duration_seconds=float(design["measurementSeconds"]),
                )
                offered = workload_receipt.get("offered")
                cpu = resources.get("applicationCpuSeconds")
                endpoint = (
                    float(cpu) / offered
                    if isinstance(offered, int) and not isinstance(offered, bool) and offered > 0
                    and isinstance(cpu, (int, float)) and not isinstance(cpu, bool)
                    else None
                )
                expected_projection = {
                    "applicationCpuSeconds": cpu,
                    "applicationMemoryPeakBytes": resources.get("applicationMemoryPeakBytes"),
                    "hostCpuSeconds": resources.get("hostCpuSeconds"),
                    "contract": resources.get("contract"),
                    "artifactSha256": _sha256(root / "resources.json"),
                    "nominalStartAtEpoch": resources.get("nominalStartAtEpoch"),
                    "nominalEndAtEpoch": resources.get("nominalEndAtEpoch"),
                    "measurementDurationSeconds": resources.get("measurementDurationSeconds"),
                    "samplingIntervalSeconds": (
                        resources.get("sampling", {}).get("intervalSeconds")
                        if isinstance(resources.get("sampling"), dict) else None
                    ),
                    "offeredJourneys": offered,
                    "applicationCpuSecondsPerOfferedJourney": endpoint,
                }
                resource_projection_ok = (
                    resource_replay.get("verdict") == "pass"
                    and resources.get("sampling", {}).get("intervalSeconds") == 5.0
                    and resource_receipt == expected_projection
                )
                resource_observation = {
                    "replay": resource_replay,
                    "declared": resource_receipt,
                    "expected": expected_projection,
                }
            except Exception as exc:  # noqa: BLE001 - retained evidence must fail closed
                resource_observation = {
                    "replay": resource_replay,
                    "error": f"{type(exc).__name__}: {exc}",
                }
        report.check(
            "resource-cost-evidence", resource_projection_ok, resource_observation,
            "The cost proxy requires hash-bound fixed-rate samples, stable service identities, replayable slot arithmetic, and the offered-journey denominator.",
            "Resource evidence and per-offered-journey projection replay." if resource_projection_ok else "Resource/cost evidence is missing, mutable, or not replayable.",
            failure="missing-artifact" if not isinstance(resources, dict) else "invalid",
        )
    else:
        resource_path = root / "resources.json"
        declared_resource = artifacts.get("resources.json")
        declared_sha = (
            declared_resource.get("sha256") if isinstance(declared_resource, dict) else None
        )
        actual_sha = _sha256(resource_path) if resource_path.is_file() else None
        if not resource_path.is_file():
            availability = "absent"
        elif not isinstance(resources, dict):
            availability = "unavailable"
        elif declared_sha != actual_sha:
            availability = "unbound"
        else:
            availability = "available-but-excluded"
        receipt_resource_projection = receipt.get("resources")
        no_receipt_cost_projection = receipt_resource_projection is None
        boundary_ok = (
            regime in SCENARIOS
            and analysis_kind == "effect"
            and resource_use == "diagnostic-only"
            and no_receipt_cost_projection
        )
        report.check(
            "resource-effect-claim-boundary", boundary_ok,
            {
                "analysisKind": analysis_kind,
                "resourceUse": resource_use,
                "artifactAvailability": availability,
                "artifactSha256": {"declared": declared_sha, "actual": actual_sha},
                "parseError": data.get("resourceParseError"),
                "resourcesExcludedFromEffectClaims": True,
                "costProjection": None,
                "receiptResourceProjection": {
                    "present": "resources" in receipt,
                    "isNull": receipt_resource_projection is None,
                    "fields": (
                        sorted(receipt_resource_projection)
                        if isinstance(receipt_resource_projection, dict) else None
                    ),
                },
                "strictResourceReplay": "not-run-for-effect-cell",
            },
            "Diagnostic resource artifacts are outside the effect estimand, and the effect receipt must not carry a cost projection.",
            "Resources are explicitly excluded from this effect claim." if boundary_ok else "Effect receipt leaks a cost projection or lacks diagnostic-only separation.",
        )

    system_ok, system_observation = system_samples_check(
        data.get("systemSamples"), no_fault=regime == "no-fault-cost",
        measurement_start_epoch=(
            measurement_start.timestamp() if measurement_start is not None else None),
        window_seconds=design["systemWindowSeconds"], sample_count=design["systemSampleCount"],
    )
    report.check(
        "system-samples", system_ok, system_observation,
        "Every cell carries 121 cgroup-v2 samples on the shared 600 s window; a no-fault cell has every application service in every sample, a fault cell may carry null rows for a stopped container. Fault-window samples are detection signals, never cost estimates.",
        "System samples cover the window." if system_ok else "System samples are missing, off-grid, or lack a required service.",
        failure="missing-artifact" if not isinstance(data.get("systemSamples"), dict) else "invalid",
    )

    regime_ok = False
    phase_counts: Counter[str] = Counter()
    if regime == "no-fault-cost":
        intervention_path = root / "intervention.json"
        intervention_artifact_ok = (
            not intervention_path.exists() and "intervention.json" not in artifacts
        )
        report.check(
            "intervention-artifact-binding", intervention_artifact_ok,
            {"exists": intervention_path.exists(), "declared": artifacts.get("intervention.json")},
            "A no-fault run has no intervention thread or intervention artifact.",
            "No intervention artifact exists." if intervention_artifact_ok else "No-fault run contains intervention evidence.",
        )
        regime_ok = (
            analysis_kind == "cost" and intervention is None
            and receipt.get("resourceUse") == "cost-proxy"
        )
        phase_counts["measurement"] = len(journeys)
        report.check(
            "cost-effect-separation", regime_ok,
            {"analysisKind": analysis_kind, "intervention": intervention,
             "resourceUse": receipt.get("resourceUse")},
            "The burden endpoint is estimated only in a no-fault deployment with no intervention thread.",
            "This is a no-fault cost run." if regime_ok else "Cost and fault/effect evidence are mixed.",
        )
        no_fault_failures = sum(row.get("outcome") != "succeeded" for row in journeys)
        report.check(
            "no-fault-workload-context", no_fault_failures == 0,
            {"failedOrTimedOut": no_fault_failures},
            "A no-fault failure invalidates the cost context rather than becoming an effect outcome.",
            "No-fault journeys succeeded." if no_fault_failures == 0 else "No-fault workload context failed.",
        )
    elif regime in SCENARIOS:
        expected_scenario = SCENARIOS[regime]
        intervention_path = root / "intervention.json"
        intervention_artifact_error: str | None = None
        intervention_artifact = None
        try:
            intervention_artifact = _read_json(intervention_path)
            declared_intervention_sha = (
                artifacts.get("intervention.json", {}).get("sha256")
                if isinstance(artifacts.get("intervention.json"), dict) else None
            )
            intervention_artifact_ok = (
                intervention_artifact == intervention
                and declared_intervention_sha == _sha256(intervention_path)
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            intervention_artifact_ok = False
            intervention_artifact_error = str(exc)
        report.check(
            "intervention-artifact-binding", intervention_artifact_ok,
            {"path": str(intervention_path), "error": intervention_artifact_error,
             "equalsReceipt": intervention_artifact == intervention},
            "Effect ground truth is scored only from the exact separately retained intervention receipt bytes.",
            "Intervention artifact and receipt reconcile." if intervention_artifact_ok else "Intervention artifact is missing or unbound.",
            failure="missing-artifact" if not intervention_path.is_file() else "invalid",
        )
        effect_shape = (
            isinstance(intervention, dict) and analysis_kind == "effect"
            and receipt.get("resourceUse") == "diagnostic-only"
        )
        ground_truth_ok = False
        ground_truth_observation: Any = intervention
        if effect_shape:
            try:
                scientific_keys = {
                    "schemaVersion", "scenario", "service", "independentOfKieker",
                    "intervalLabel", "functionalOutage", "measurementBarrier",
                    "requestedHoldSeconds", "targetContainerId", "targetImage", "preState",
                    "commandVector", "commandResult", "actualOnsetWall",
                    "actualOnsetMonotonicOffsetSeconds", "actualOffsetWall",
                    "actualOffsetMonotonicOffsetSeconds", "duringStateSamples",
                    "recoveryAction", "sameTargetIdentity", "readiness", "postState",
                    "interventionThreadJoined", "laterInterventionMutationObserved",
                    "manifested", "recovered", "outageHeld", "successful", "error",
                    "operational",
                }
                if SWEEP:
                    # Traffic sweep: pre-command / revert stamps, readiness probes and the throttle record.
                    scientific_keys = scientific_keys | {"sweep"}
                if set(intervention) != scientific_keys or intervention.get("schemaVersion") != 3:
                    raise ValueError(f"intervention scientific fields differ: {sorted(set(intervention) ^ scientific_keys)}")
                onset_wall = _iso(intervention["actualOnsetWall"])
                offset_wall = _iso(intervention["actualOffsetWall"])
                readiness = intervention["readiness"]
                readiness_wall = _iso(readiness["observedAtWall"])
                onset_mono = float(intervention["actualOnsetMonotonicOffsetSeconds"])
                offset_mono = float(intervention["actualOffsetMonotonicOffsetSeconds"])
                readiness_mono = float(readiness["observedAtMonotonicOffsetSeconds"])
                barrier = intervention["measurementBarrier"]
                samples = intervention["duringStateSamples"]
                state_ok = all(
                    set(sample) == {"phase", "observedAtWall", "observedAtMonotonicOffsetSeconds", "state"}
                    and onset_wall <= _iso(sample["observedAtWall"]) <= offset_wall
                    and onset_mono <= float(sample["observedAtMonotonicOffsetSeconds"]) <= offset_mono
                    for sample in samples
                ) and bool(samples)
                if expected_scenario == "auth-freeze":
                    state_ok &= (
                        intervention.get("preState", {}).get("running") is True
                        and intervention.get("preState", {}).get("paused") is False
                        and intervention.get("postState", {}).get("running") is True
                        and intervention.get("postState", {}).get("paused") is False
                        and all(sample.get("state", {}).get("running") is True
                                and sample.get("state", {}).get("paused") is True
                                for sample in samples)
                    )
                elif expected_scenario == "persistence-cpu-throttle":
                    throttle = (intervention.get("sweep") or {}).get("throttle") or {}
                    host_quota = throttle.get("hostNanoCpus")
                    state_ok &= (
                        type(host_quota) is int and host_quota >= 1_000_000_000
                        and throttle.get("nanoCpus") == (timing or {}).get("cpuThrottleNanoCpus")
                        and throttle.get("cpus") == (timing or {}).get("cpuThrottleCpus")
                        and throttle.get("revertCpus") == str(host_quota // 1_000_000_000)
                        and throttle.get("preNanoCpus") == intervention.get("preState", {}).get("nanoCpus")
                        and intervention.get("preState", {}).get("running") is True
                        and intervention.get("preState", {}).get("paused") is False
                        and intervention.get("preState", {}).get("nanoCpus") in (0, host_quota)
                        and intervention.get("postState", {}).get("running") is True
                        and intervention.get("postState", {}).get("paused") is False
                        and intervention.get("postState", {}).get("nanoCpus") == host_quota
                        and all(sample.get("state", {}).get("running") is True
                                and sample.get("state", {}).get("paused") is False
                                and sample.get("state", {}).get("nanoCpus") == throttle.get("nanoCpus")
                                for sample in samples)
                        and intervention.get("commandVector") == [
                            "docker", "update", "--cpus", throttle.get("cpus"),
                            intervention.get("targetContainerId")]
                        and (intervention.get("recoveryAction") or {}).get("commandVector") == [
                            "docker", "update", "--cpus", throttle.get("revertCpus"),
                            intervention.get("targetContainerId")]
                    )
                else:
                    state_ok &= (
                        intervention.get("preState", {}).get("running") is True
                        and intervention.get("postState", {}).get("running") is True
                        and all(sample.get("state", {}).get("running") is False for sample in samples)
                    )
                command_result = intervention["commandResult"]
                recovery_action = intervention["recoveryAction"]
                operational = intervention["operational"]
                ground_truth_ok = (
                    intervention.get("scenario") == expected_scenario
                    and intervention.get("service") == FAULT_SERVICES.get(expected_scenario)
                    and intervention.get("independentOfKieker") is True
                    and intervention.get("intervalLabel") == "intervention-exposure"
                    and intervention.get("functionalOutage") is None
                    and set(barrier) == {"id", "wall", "scheduledOnsetSeconds", "scheduledOnsetWall"}
                    and barrier.get("id") == barrier_id
                    # F-ADH-070: the producer derives these walls from epoch-float
                    # arithmetic (fromtimestamp(epoch + offset)) while this replay
                    # uses datetime+timedelta; compare within the driver's 1
                    # microsecond instead of exactly.
                    and abs((_iso(barrier["wall"]) - measurement_start).total_seconds()) <= 1e-6
                    and barrier.get("scheduledOnsetSeconds") == design["onsetSeconds"]
                    and abs((_iso(barrier["scheduledOnsetWall"])
                             - (measurement_start + timedelta(seconds=design["onsetSeconds"]))
                             ).total_seconds()) <= 1e-6
                    and bool(intervention.get("targetContainerId"))
                    and bool(intervention.get("targetImage"))
                    and isinstance(intervention.get("commandVector"), list)
                    and isinstance(command_result, dict)
                    and set(command_result) == {"command", "returnCode", "stdout", "stderr"}
                    and command_result.get("returnCode") == 0
                    and command_result.get("command") == intervention.get("commandVector")
                    and isinstance(recovery_action, dict)
                    and set(recovery_action) == {"commandVector", "commandResult"}
                    and isinstance(recovery_action.get("commandVector"), list)
                    and isinstance(recovery_action.get("commandResult"), dict)
                    and set(recovery_action["commandResult"]) == {"command", "returnCode", "stdout", "stderr"}
                    and recovery_action["commandResult"].get("returnCode") == 0
                    and recovery_action["commandResult"].get("command") == recovery_action["commandVector"]
                    and intervention.get("sameTargetIdentity") is True
                    and set(readiness) == {
                        "predicate", "observedAtWall", "observedAtMonotonicOffsetSeconds", "successful"
                    }
                    and readiness.get("successful") is True
                    and isinstance(readiness.get("predicate"), str) and bool(readiness["predicate"])
                    and intervention.get("manifested") is True
                    and intervention.get("recovered") is True
                    and intervention.get("outageHeld") is True
                    and intervention.get("successful") is True
                    and intervention.get("error") is None
                    and intervention.get("interventionThreadJoined") is True
                    and intervention.get("laterInterventionMutationObserved") is False
                    and set(operational) == {
                        "controllerStartedAt", "controllerEndedAt", "commandResults",
                        "actualHoldSeconds", "continuousTargetStateProven",
                    }
                    and _iso(operational["controllerStartedAt"]) <= onset_wall
                    and _iso(operational["controllerEndedAt"]) >= readiness_wall
                    and operational.get("commandResults") == [
                        command_result, recovery_action["commandResult"]
                    ]
                    and math.isclose(
                        float(operational["actualHoldSeconds"]), offset_mono - onset_mono,
                        abs_tol=1e-9,
                    )
                    and operational.get("continuousTargetStateProven") is False
                    and intervention.get("requestedHoldSeconds") == design["holdSeconds"]
                    and math.isclose(offset_mono - onset_mono, float(design["holdSeconds"]), abs_tol=1.0)
                    and [sample.get("phase") for sample in samples] == [
                        "manifested", "hold-midpoint", "hold-end"
                    ]
                    and onset_wall < offset_wall <= readiness_wall
                    and onset_mono < offset_mono <= readiness_mono
                    and measurement_start is not None and measurement_end is not None
                    and measurement_start <= onset_wall < offset_wall <= readiness_wall <= measurement_end
                    and state_ok
                )
                ground_truth_observation = {
                    "scenario": intervention.get("scenario"),
                    "targetContainerId": intervention.get("targetContainerId"),
                    "holdSeconds": offset_mono - onset_mono,
                    "stateSamples": len(samples),
                    "manifested": intervention.get("manifested"),
                    "recovered": intervention.get("recovered"),
                    "threadJoined": intervention.get("interventionThreadJoined"),
                    "laterMutation": intervention.get("laterInterventionMutationObserved"),
                }
            except (KeyError, TypeError, ValueError) as exc:
                ground_truth_observation = str(exc)
        report.check(
            "cost-effect-separation", effect_shape,
            {"analysisKind": analysis_kind, "hasIntervention": isinstance(intervention, dict),
             "resourceUse": receipt.get("resourceUse")},
            "Effect runs have a separate cold-start root and exactly one declared training fault.",
            "This is an effect run." if effect_shape else "Effect evidence is missing or mixed with cost evidence.",
        )
        report.check(
            "independent-fault-ground-truth", ground_truth_ok, ground_truth_observation,
            "A successful command is insufficient; independent target state, recovery, and joined-thread evidence are required.",
            "Intervention manifestation and recovery are proven." if ground_truth_ok else "Fault ground truth is incomplete.",
        )
        if isinstance(intervention, dict):
            for journey in journeys:
                try:
                    phase_counts[_phase_for(journey, regime, intervention)] += 1
                except (KeyError, TypeError, ValueError):
                    phase_counts["unknown"] += 1
        floors = design["phaseFloors"] if isinstance(design["phaseFloors"], dict) else {}
        floors_ok = bool(floors) and all(
            phase_counts[phase] >= floors.get(phase, math.inf) for phase in ("before", "during", "after"))
        report.check(
            "actual-phase-start-floor", floors_ok,
            dict(phase_counts) if not SWEEP else {"observed": dict(phase_counts), "floors": floors},
            "Nominal scheduling does not prove exposure; actual monotonic starts supply phase denominators.",
            ("Each effect phase has at least 20 actual starts." if floors_ok
             else "An effect phase has fewer than 20 actual starts.") if not SWEEP else (
                "Each effect phase meets its plan-derived actual-start floor." if floors_ok
                else "An effect phase misses its plan-derived actual-start floor."),
        )
        if SWEEP:
            stamp_ok = False
            stamp_observation: Any = None
            try:
                sweep_record = intervention["sweep"]
                stamps = sweep_record["commandStamps"]
                probes = sweep_record["probes"]
                harness = (timing or {}).get("faultHarness")
                if set(sweep_record) != {"schemaVersion", "onsetSource", "commandStamps", "probes", "throttle"} | (
                        {"probePolicy", "freezeStamps"} if harness is not None else set()):
                    raise ValueError("sweep receipt fields differ")
                if set(stamps) != {
                    "onsetCommandIssuedWall", "onsetCommandIssuedMonotonicOffsetSeconds",
                    "onsetCommandReturnedMonotonicOffsetSeconds", "revertCommandIssuedWall",
                    "revertCommandIssuedMonotonicOffsetSeconds", "revertCommandReturnedMonotonicOffsetSeconds",
                }:
                    raise ValueError("command stamp fields differ")
                issued = float(stamps["onsetCommandIssuedMonotonicOffsetSeconds"])
                returned = float(stamps["onsetCommandReturnedMonotonicOffsetSeconds"])
                reverting = float(stamps["revertCommandIssuedMonotonicOffsetSeconds"])
                reverted = float(stamps["revertCommandReturnedMonotonicOffsetSeconds"])
                onset_mono = float(intervention["actualOnsetMonotonicOffsetSeconds"])
                offset_mono = float(intervention["actualOffsetMonotonicOffsetSeconds"])
                readiness_mono = float(intervention["readiness"]["observedAtMonotonicOffsetSeconds"])
                probe_rows_ok = bool(probes) and all(
                    isinstance(row, dict) and set(row) == {
                        "phase", "request", "startMonotonicOffsetSeconds", "endMonotonicOffsetSeconds",
                        "ready",
                    }
                    and row["phase"] == "post-revert-readiness"
                    and reverted <= float(row["startMonotonicOffsetSeconds"])
                    <= float(row["endMonotonicOffsetSeconds"]) <= readiness_mono
                    and (row["ready"] is True) is (index == len(probes) - 1)
                    for index, row in enumerate(probes)
                )
                stamp_ok = (
                    sweep_record["schemaVersion"] == 1
                    and sweep_record["onsetSource"] == "pre-command"
                    # The controller sleeps until the scheduled onset before it stamps, so an earlier stamp
                    # is not the command's (F-ADH-085 class); F1 bounds the lateness.
                    and issued >= float(design["onsetSeconds"]) - 0.05
                    and issued <= returned <= onset_mono <= offset_mono <= reverting <= reverted
                    <= readiness_mono
                    and _iso(stamps["onsetCommandIssuedWall"]) <= _iso(intervention["actualOnsetWall"])
                    and _iso(intervention["actualOffsetWall"]) <= _iso(stamps["revertCommandIssuedWall"])
                    and probe_rows_ok
                    and (sweep_record["throttle"] is None) is (expected_scenario != "persistence-cpu-throttle")
                )
                harness_problem = (
                    _fault_harness_problem(intervention, sweep_record, harness, timing, expected_scenario)
                    if harness is not None else None)
                stamp_ok = stamp_ok and harness_problem is None
                # H4 is record-not-block (decision 69): its reasons are reported, never a reason to block the cell.
                freeze_problems = (
                    _freeze_stamp_problems(intervention, sweep_record, harness, timing, expected_scenario)
                    if harness is not None else None)
                stamp_observation = {
                    "onsetIssuedLateSeconds": issued - float(design["onsetSeconds"]),
                    "onsetCommandSeconds": returned - issued,
                    "holdBetweenCommandsSeconds": reverting - issued,
                    "probes": len(probes),
                    **({} if harness is None else {
                        "faultHarness": harness["version"], "faultHarnessProblem": harness_problem,
                        "h4": {"status": "recorded" if not freeze_problems else "missing",
                               "reasons": freeze_problems, "failureCount": len(freeze_problems)}}),
                    "probeWindowSeconds": [
                        float(probes[0]["startMonotonicOffsetSeconds"]),
                        float(probes[-1]["endMonotonicOffsetSeconds"]),
                    ] if probes else None,
                }
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                stamp_observation = f"{type(exc).__name__}: {exc}"
            report.check(
                "sweep-fault-command-stamps", stamp_ok, stamp_observation,
                "The onset is stamped immediately before the command and the revert around its command; every post-revert readiness request is stamped so the analysis can exclude it.",
                "Command stamps and probe windows are complete and ordered." if stamp_ok
                else "Command stamps or probe windows are missing, early, or unordered.",
            )
        drain_ids = [
            row.get("journeyId") for row in journeys
            if _drain_excused(row, regime, intervention, timing)
        ] if isinstance(intervention, dict) and ground_truth_ok else []
        context_failures = [
            row.get("journeyId") for row in journeys
            if _phase_for(row, regime, intervention) in {"before", "after"}
            and row.get("outcome") != "succeeded"
            and row.get("journeyId") not in set(drain_ids)
        ] if isinstance(intervention, dict) and ground_truth_ok else []
        context_observation: Any = {
            "preOrPostFailures": context_failures[:20], "count": len(context_failures)}
        if SWEEP:
            allowance = (timing or {}).get("drainAllowanceSeconds")
            readiness = (intervention or {}).get("readiness", {}).get("observedAtMonotonicOffsetSeconds") \
                if isinstance(intervention, dict) else None
            result["drainAllowance"] = {
                "allowanceSeconds": allowance,
                "rule": "fault cells: journeys STARTING in [readiness, readiness + allowance) may fail; recorded, "
                        "excluded from the zero-failure rule and from the scored population (Q3, 2026-10-03)",
                "windowMonotonicSeconds": (
                    [readiness, readiness + allowance]
                    if isinstance(readiness, (int, float)) and allowance is not None else None),
                "excusedFailures": len(drain_ids),
                "excusedJourneyIds": drain_ids,
            }
            context_observation["drainExcusedFailures"] = len(drain_ids)
            context_observation["drainExcusedJourneyIds"] = drain_ids[:50]
        report.check(
            "effect-context", not context_failures,
            context_observation,
            "During-fault failures are outcomes, while pre-fault or post-readiness failures invalidate context.",
            "Effect context is stable outside intervention." if not context_failures else "Effect context failed outside intervention.",
        )

    if SWEEP:
        gates_ok = False
        try:
            if timing is None:
                raise ValueError("no compiled timing")
            gate_record = sweep_protocol_gates(
                run_id=str(run.get("runId")), posture=str(posture), timing=timing, plan=plan,
                journeys=journeys, intervention=intervention,
                harness_valid=report.cell_status == "valid",
            )
            gates_ok = not gate_record["failedGates"]
        except Exception as exc:  # noqa: BLE001 - a gate that cannot run blocks
            gate_record = {"error": f"{type(exc).__name__}: {exc}"}
        result["protocolGates"] = gate_record
        report.check(
            "protocol-gates", gates_ok,
            {"failedGates": gate_record.get("failedGates"), "error": gate_record.get("error")},
            "Vendored protocol gates: F1 fault truth (fault cells), G1 traffic, G2 healthy before onset, G4 bookkeeping; R2.recovery is recorded, not blocking; P0, R1, R2 have no harness inputs.",
            "F1/G1/G2/G4 pass." if gates_ok else "A blocking protocol gate did not pass.",
        )
        log_ok, log_observation = _application_log_check(root / "application.log")
        report.check(
            "application-log-timestamps", log_ok, log_observation,
            "docker compose logs --timestamps retains every application service's log with Docker receive times.",
            "Every application service has timestamped log lines." if log_ok
            else "application.log lacks timestamped lines of an application service.",
            failure="missing-artifact" if not (root / "application.log").is_file() else "invalid",
        )

    spool_ok, spool_observation = _candidate_spool_observation(
        root, receipt, runtime_images, traces,
    )
    report.check(
        "native-spool-collector-and-attribution-binding", spool_ok,
        spool_observation,
        "Candidate traces must be reproduced from a sealed raw AMQP spool under the exact frozen service-attribution configuration.",
        "Raw spool, collector counters, runtime host proof, and attribution digest reconcile."
        if spool_ok else "Raw spool or collector attribution binding is absent or changed.",
        failure="unsupported",
    )

    # The capture is checked independently of the numbers declared in its terminal receipt.
    trace_times: list[datetime] = []
    malformed_trace_rows: list[int] = []
    for index, event in enumerate(traces):
        try:
            trace_times.append(_native_time(event))
        except (TypeError, ValueError, OverflowError, OSError):
            malformed_trace_rows.append(index + 1)
    measurement_events = [
        event for event, timestamp in zip(traces, trace_times)
        if measurement_start is not None and measurement_end is not None
        and measurement_start <= timestamp < measurement_end
    ] if len(trace_times) == len(traces) else []
    tail_events = len(traces) - len(measurement_events)
    timestamp_ok = not malformed_trace_rows
    report.check(
        "native-timestamp-window", timestamp_ok,
        {"malformedRows": malformed_trace_rows, "measurementRecords": len(measurement_events),
         "diagnosticTailOrOutsideRecords": tail_events},
        "Only native event timestamps inside the shared interval may enter scored views; tail remains diagnostic.",
        "All trace records have clip-able native timestamps." if timestamp_ok else "Trace timestamps cannot be clipped safely.",
    )

    native_ids = [_original_native_trace_id(event) for event in traces]
    provenance_ok = all(bool(native_id) for native_id in native_ids)
    report.check(
        "original-native-trace-provenance", provenance_ok,
        {"rawRecords": len(traces), "recordsWithOriginalNativeId": sum(bool(value) for value in native_ids),
         "genericTraceIdFieldsPresent": sum("trace_id" in event for event in traces),
         "scraperGeneratedIdsObserved": sum(
             str(event.get("trace_id", "")).startswith("scraped_") for event in traces)},
        "Scraper-generated trace_id values are never treated or named as original Kieker trace IDs.",
        "Every scored record identifies one proven original native trace." if provenance_ok else "Original native trace identity is unproven.",
        failure="unsupported",
    )

    _pc = _queue_checker()
    # SCENARIOS is the authoritative regime -> injected fault map; no-fault-cost
    # has no entry and therefore never carries an exposure window.
    fault = SCENARIOS.get(regime, "none")
    exposure_window = _pc.exposure_window(intervention, fault)
    exposure_bounds = (
        (exposure_window["startEpoch"], exposure_window["endEpoch"])
        if exposure_window else None
    )

    def _exposure_seconds(row: dict[str, Any]) -> float:
        return float(row.get("collector_timestamp") or row.get("timestamp") or 0.0)

    unhashed = [index + 1 for index, event in enumerate(traces)
                if not _valid_sha1(event.get("message_sha1")) or not _valid_sha1(event.get("signature_sha1"))]
    moments_by_key: dict[Any, list[float]] = {}
    for event in traces:
        if event.get("message_sha1") and _original_native_trace_id(event):
            key = (event.get("message_sha1"), _original_native_trace_id(event), event.get("span_id"))
            moments_by_key.setdefault(key, []).append(_exposure_seconds(event))
    # F-ADH-082: a thawed upstream replays the requests it could not serve with
    # the SAME propagated Kieker header, so distinct executions carry one
    # (message, trace, eoi/ess) identity. When every member of such a key lies
    # inside a proven exposure window that is the fault's own signature and is
    # counted, not blocked. Outside the window, or on a cost cell, exact
    # redelivery still blocks.
    exposure_replay_keys = [
        key for key, moments in moments_by_key.items()
        if len(moments) > 1 and exposure_bounds
        and all(exposure_bounds[0] <= moment <= exposure_bounds[1] for moment in moments)
    ]
    duplicate_events = [key for key, moments in moments_by_key.items()
                        if len(moments) > 1 and key not in set(exposure_replay_keys)]
    duplicate_events.sort(key=str)
    # Traffic sweep (decision 25): a repeated (message, trace, eoi/ess) identity is a trace-completeness defect of
    # its trace, decided per journey by the trace-completeness rule below; whole-message redelivery stays caught
    # by the spool and capture checks.  The frozen epoch is unchanged.
    replay_ok = not unhashed and (SWEEP or not duplicate_events)
    report.check(
        "replay-and-duplicate-control", replay_ok,
        {"unhashedRows": unhashed, "duplicateHashedNativeEventKeys": duplicate_events,
         "exposureReplayDuplicateKeys": len(exposure_replay_keys),
         **({"duplicateKeysDecidedByTraceCompleteness": len(duplicate_events)} if SWEEP else {})},
        "Message/signature hashes plus native event identity allow many rows per message but detect exact redelivery.",
        "Capture has complete hashes and no detected replay." if replay_ok else "Replay or duplicate risk is unresolved.",
    )

    raw_view = {
        "records": len(measurement_events),
        "originalNativeTraces": len({_original_native_trace_id(event) for event in measurement_events}),
        "uniqueMessageBodies": len({event.get("message_sha1") for event in measurement_events}),
        "diagnosticTailOrOutsideRecords": tail_events,
    }
    operation_counts = Counter(str(event.get("operation")) for event in measurement_events)
    signature_counts = Counter(str(event.get("signature_sha1")) for event in measurement_events)
    top_operation_count = max(operation_counts.values(), default=0)
    signature_view = {
        "uniqueSignatures": len(signature_counts),
        "signatureWeightedRecords": sum(1 / count for count in signature_counts.values() for _ in range(count)),
        "topOperation": operation_counts.most_common(1)[0][0] if operation_counts else None,
        "topOperationCount": top_operation_count,
        "topOperationConcentration": (top_operation_count / len(measurement_events)) if measurement_events else None,
    }
    terminal_counts_ok = (
        capture.get("complete") is True
        and capture.get("settled") is True
        and capture.get("hashReconciled") is True
        and capture.get("queuePurgedBefore") is True
        and capture.get("queueMessagesAtBarrier") == 0
        and capture.get("exclusiveCollector") is True
        and capture.get("foreignWriters") == 0
        and capture.get("unjoinedChildren") == 0
        and capture.get("rawRecords") == len(traces)
        and capture.get("measurementRecords") == len(measurement_events)
        and capture.get("uniqueNativeTraces") == len(set(native_ids))
        and capture.get("uniqueSignatures") == len({event.get("signature_sha1") for event in traces})
        and capture.get("uniqueMessageBodies") == len({event.get("message_sha1") for event in traces})
        and capture.get("redeliveredMessageSha1") == []
    )
    report.check(
        "terminal-capture-reconciliation", terminal_counts_ok,
        {"declared": capture, "computed": raw_view | {
            "allRawRecords": len(traces), "allUniqueNativeTraces": len(set(native_ids)),
            "allUniqueSignatures": len({event.get("signature_sha1") for event in traces}),
            "allUniqueMessageBodies": len({event.get("message_sha1") for event in traces}),
        }},
        "A settled terminal receipt must reconcile to the capture bytes; an empty or partial read is not zero.",
        "Terminal capture reconciles." if terminal_counts_ok else "Terminal capture is incomplete or inconsistent.",
        failure="unsupported",
    )

    posture_capture_ok = (not traces) if posture == "none" else bool(traces)
    report.check(
        "posture-capture-domain", posture_capture_ok,
        {"posture": posture, "rawRecords": len(traces)},
        "None must be terminally empty; selected and full must have non-empty complete capture.",
        "Capture cardinality matches posture." if posture_capture_ok else "Capture cardinality contradicts posture.",
        failure="unsupported",
    )

    native_token_validation: dict[str, Any]
    try:
        native_token_validation = _native_token_validator().validate_retained(root)
        native_token_artifact_ok = native_token_validation.get("outcome") == "pass"
    except Exception as exc:  # noqa: BLE001 - evidence replay must fail closed
        native_token_validation = {
            "outcome": "blocked",
            "blockers": [f"{type(exc).__name__}: {exc}"],
        }
        native_token_artifact_ok = False
    report.check(
        "native-token-correlation-artifact", native_token_artifact_ok,
        native_token_validation,
        "The auth-log bridge must replay to a one-to-one, hash-bound mapping; native events never carry workload tokens.",
        "Native-token correlation replays." if native_token_artifact_ok
        else "Native-token correlation is absent, ambiguous, or unbound.",
        failure="unsupported",
    )

    native_integrity_errors: list[dict[str, Any]] = []
    defective_rows: set = set()
    unwoven_root_events = 0
    tolerated_exposure_events = 0
    probe_orphan_events = 0
    # F-ADH-083: the harness's own readiness probes mint parentless traces after
    # a fault recovery. Accepted only when the entry point IS woven (otherwise
    # the unwoven-root shape already covers them), the four structural
    # conjuncts of kieker_native.probe_orphan_root_indices hold, AND no ledger
    # token maps to the trace (this validator has the mapping; the producer
    # gate does not). Fails closed to "no probe orphans" on any exception.
    try:
        probe_orphan_rows = set(_native_collector().probe_orphan_root_indices(
            [event if isinstance(event, dict) else {} for event in traces]))
        token_traces = {
            str(row.get("nativeTraceId")) for row in (native_token_correlation or [])
            if isinstance(row, dict)
        }
        probe_orphan_rows = {
            row for row in probe_orphan_rows
            if str(_original_native_trace_id(traces[row])) not in token_traces
        }
    except (TypeError, KeyError, ValueError, IndexError):
        # Malformed rows excuse nothing; a missing collector function must
        # raise so a rename cannot silently turn this into a fault-path gate.
        probe_orphan_rows = set()
    for index, event in enumerate(traces, 1):
        if not isinstance(event, dict):
            native_integrity_errors.append({"row": index, "error": "not-an-object"})
            continue
        smuggled = sorted(TOKEN_SMUGGLING_FIELDS & set(event))
        native_id = _original_native_trace_id(event)
        attribution_ok = (
            isinstance(event.get("service"), str)
            and event.get("native_record_class") in NATIVE_RECORD_CLASSES
            and event.get("runtime_host_service") == event.get("service")
            and event.get("service_attribution_status") in TRUSTED_ATTRIBUTION_STATES
            and event.get("service_attribution_errors") == []
        )
        errors = event.get("correlation_errors")
        # F-ADH-066 (lineage F-ADH-062/064/065): when the replayed closure omits
        # the trace-root activation group, each per-thread trace's shallowest
        # execution legitimately misses only its depth-0 parent. Any deeper
        # missing parent, mixed errors, warning, or duplicate identity stays a
        # defect in every posture.
        unwoven_root_shape = (
            not entry_woven
            and isinstance(errors, list) and bool(errors)
            and all(error == unwoven_root_error for error in errors)
            and event.get("parent_resolution") == "missing"
        )
        probe_orphan_shape = (
            entry_woven
            and (index - 1) in probe_orphan_rows
            and isinstance(errors, list) and bool(errors)
            and all(error == unwoven_root_error for error in errors)
            and event.get("parent_resolution") == "missing"
        )
        # F-ADH-074: inside a proven exposure window, a late-flushed ambiguous
        # parent is the injected fault's own signature. Scoped by record
        # timestamp; loss outside the window stays a defect.
        exposure_shape = bool(
            exposure_bounds
            and isinstance(errors, list) and bool(errors)
            and all(str(error).startswith(_pc.EXPOSURE_TOLERABLE_ERROR_PREFIXES)
                    for error in errors)
            and event.get("parent_resolution") in {"missing", "ambiguous"}
            and exposure_bounds[0] <= _exposure_seconds(event) <= exposure_bounds[1]
        )
        # F-ADH-082: `conflicting-native-identity` is emitted ONLY when an
        # identity occurs more than once, so demanding a unique identity here
        # made the F-ADH-076 tolerance unsatisfiable for its own signature
        # (55 events, 0 tolerated, on the campaign #8 cell). Inside the window
        # the repeated identity IS the tolerated error; everywhere else a
        # repeated identity stays a defect.
        identity_unique = (
            event.get("native_identity_occurrences") == 1
            and event.get("native_identity_message_bodies") == 1
        )
        correlation_ok_for_event = event.get("correlation_warnings") == [] and (
            (
                (
                    errors == []
                    and event.get("parent_resolution") in {"root", "resolved"}
                ) or unwoven_root_shape or probe_orphan_shape
            ) and identity_unique
            or exposure_shape
        )
        if not (smuggled or native_id is None or not attribution_ok or not correlation_ok_for_event):
            unwoven_root_events += int(unwoven_root_shape)
            probe_orphan_events += int(probe_orphan_shape)
            tolerated_exposure_events += int(
                exposure_shape and not unwoven_root_shape and not probe_orphan_shape)
        # Traffic sweep (decision 25): a record whose only defect is its parentage or identity is a
        # trace-completeness defect, decided per journey below, not an integrity failure of the cell.
        clean_record = (
            errors == [] and event.get("parent_resolution") in {"root", "resolved"} and identity_unique)
        completeness_only = (
            SWEEP and not smuggled and native_id is not None and attribution_ok
            and event.get("correlation_warnings") == [] and isinstance(errors, list))
        if SWEEP and completeness_only and not (clean_record or unwoven_root_shape or probe_orphan_shape):
            defective_rows.add(index - 1)
        if completeness_only and not correlation_ok_for_event:
            continue
        if smuggled or native_id is None or not attribution_ok or not correlation_ok_for_event:
            native_integrity_errors.append({
                "row": index,
                "tokenSmugglingFields": smuggled,
                "originalNativeTraceId": native_id,
                "service": event.get("service"),
                "nativeRecordClass": event.get("native_record_class"),
                "runtimeHostService": event.get("runtime_host_service"),
                "serviceAttributionStatus": event.get("service_attribution_status"),
                "serviceAttributionErrors": event.get("service_attribution_errors"),
                "parentResolution": event.get("parent_resolution"),
                "correlationErrors": event.get("correlation_errors"),
                "correlationWarnings": event.get("correlation_warnings"),
                "nativeIdentityOccurrences": event.get("native_identity_occurrences"),
                "nativeIdentityMessageBodies": event.get("native_identity_message_bodies"),
            })
    native_integrity_ok = not native_integrity_errors
    report.check(
        "native-event-correlation-and-attribution-integrity", native_integrity_ok,
        {"rawRecords": len(traces), "errors": native_integrity_errors[:20],
         "entryPointWoven": entry_woven, "unwovenRootEvents": unwoven_root_events,
         "probeOrphanRootEvents": probe_orphan_events,
         "toleratedExposureEvents": tolerated_exposure_events,
         "exposureWindow": exposure_window,
         **({"recordsDecidedByTraceCompleteness": len(defective_rows)} if SWEEP else {})},
        "Only original Kieker identity with globally resolved parents, unique events, and "
        "runtime-host service attribution can support path reconstruction; when the replayed "
        "closure omits the trace-root sensor, a missing depth-0 parent alone is the expected "
        "unwoven-root shape, not a defect (F-ADH-066; lineage F-ADH-064/065).",
        "Native correlation and attribution are terminally unambiguous."
        if native_integrity_ok else "Native identity, parentage, duplication, or service attribution is ambiguous.",
        failure="unsupported",
    )

    # F-ADH-074: the producer's tolerance is re-derived here from the retained
    # traces and intervention, so a receipt cannot claim a tolerance the
    # evidence does not support.
    # F-ADH-084: the rejected-container diagnostics are re-derived from the same
    # retained spool bytes, so the receipt cannot claim a rejection is benign.
    try:
        recomputed_container_failures = _native_collector(
        ).spool_container_parse_diagnostics(root / "kieker-amqp.spool")
        container_diagnostic_error = None
    except Exception as exc:  # noqa: BLE001 - an unreadable spool tolerates nothing
        recomputed_container_failures = ()
        container_diagnostic_error = f"{type(exc).__name__}: {exc}"
    recomputed_tolerance = _pc.exposure_tolerance(
        traces, intervention, fault=fault,
        container_failures=recomputed_container_failures,
    )
    receipt_tolerance = receipt.get("exposureTolerance")
    tolerance_ok = (
        container_diagnostic_error is None
        and receipt_tolerance == recomputed_tolerance
        and recomputed_tolerance["toleratedCorrelationErrorEvents"] == tolerated_exposure_events
        # Traffic sweep (decision 25): residual parentage / identity / EOI loss is decided per journey by the
        # trace-completeness rule; the tolerance record must still replay exactly.
        and (SWEEP or recomputed_tolerance["residualCorrelationErrorEvents"] == 0)
        and (SWEEP or recomputed_tolerance["residualEoiGapTraces"] == 0)
        and (SWEEP or recomputed_tolerance["residualMissingEoiCount"] == 0)
        and recomputed_tolerance["residualContainerParseFailures"] == 0
        and (recomputed_tolerance["applied"] is (fault != "none"))
    )
    report.check(
        "exposure-tolerance-binding", tolerance_ok,
        {"recomputed": recomputed_tolerance,
         "receiptMatches": receipt_tolerance == recomputed_tolerance,
         "toleratedExposureEvents": tolerated_exposure_events,
         "containerDiagnosticError": container_diagnostic_error},
        "Telemetry loss may only be excused inside the recorded exposure window of a proven "
        "intervention, re-derived independently from the retained records; residual loss "
        "outside that window is a pipeline defect in every regime (F-ADH-074).",
        "The receipt's exposure tolerance replays exactly and leaves no residual loss."
        if tolerance_ok else
        "The receipt's exposure tolerance does not replay, or residual loss remains.",
        failure="unsupported",
    )

    if SWEEP:
        completeness: Any = None
        try:
            if timing is None or measurement_start is None:
                raise ValueError("no compiled timing or measurement start")
            completeness = sweep_trace_completeness(
                traces=traces, journeys=journeys,
                auth_log_text=(root / "auth.log").read_text(encoding="utf-8", errors="replace"),
                intervention=intervention, timing=timing, regime=regime,
                measurement_start_epoch=measurement_start.timestamp(),
                defective_rows=defective_rows, duplicate_keys=duplicate_events,
                logging_seconds=_pc._logging_seconds,
                fraction=float(_sweep_compiler().TRACE_INCOMPLETE_FRACTION),
            )
            completeness_ok = completeness["blocking"] is False
        except Exception as exc:  # noqa: BLE001 - a rule that cannot run blocks
            completeness = {"error": f"{type(exc).__name__}: {exc}"}
            completeness_ok = False
        result["traceCompleteness"] = completeness
        report.check(
            "trace-completeness", completeness_ok,
            {key: completeness.get(key) for key in (
                "windowIMonotonicSeconds", "successfulJourneysInRuleTwo", "incompleteInRuleTwo", "allowance",
                "error")},
            "Decision 25: journeys starting in the fault or drain window may have incomplete traces (recorded); "
            "elsewhere at most max(1, floor(1% of successful journeys)) may; every incomplete trace is reported "
            "per window in traceCompleteness.",
            "Incomplete traces outside the fault and drain window are within the allowance." if completeness_ok
            else "More incomplete traces outside the fault and drain window than the allowance.",
        )

    witness_by_opportunity: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for witness in witnesses:
        witness_by_opportunity[witness.get("opportunityId")].append(witness)
    ledger_opportunity_ids = {row.get("opportunityId") for row in journeys}
    scored_journeys: list[dict[str, Any]] = []
    for journey in journeys:
        if regime == "no-fault-cost":
            scored_journeys.append(journey)
        elif isinstance(intervention, dict):
            try:
                if (_phase_for(journey, regime, intervention) in {"before", "after"}
                        and not _drain_excused(journey, regime, intervention, timing)):
                    scored_journeys.append(journey)
            except (KeyError, TypeError, ValueError):
                pass
    scored_ids = {row.get("opportunityId") for row in scored_journeys}
    source_replay_ok = False
    source_replay_observation: Any = None
    source_counts = {
        "authObservations": 0,
        "persistenceObservations": 0,
        "completeWitnessPaths": 0,
        "partialOptionalObservations": 0,
        "unscoredExcludedObservations": 0,
    }
    try:
        auth_source = _application_source_observations(root / "auth.log", "auth")
        persistence_source = _application_source_observations(
            root / "persistence.log", "persistence")
        source_counts["authObservations"] = len(auth_source)
        source_counts["persistenceObservations"] = len(persistence_source)
        source_by_token: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
            lambda: {"auth": [], "persistence": []})
        for row in [*auth_source, *persistence_source]:
            source_by_token[row["journeyId"]][row["service"]].append(row)
        expected_tokens = {str(row.get("opaqueToken")) for row in journeys}
        unknown_tokens = sorted(set(source_by_token) - expected_tokens)
        if unknown_tokens:
            raise ValueError(f"source observations use unknown tokens: {unknown_tokens[:10]}")
        witness_by_token: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for witness in witnesses:
            witness_by_token[str(witness.get("opaqueToken"))].append(witness)
        paired_tokens: set[str] = set()
        for journey in journeys:
            token = str(journey.get("opaqueToken"))
            grouped = source_by_token[token]
            auth_rows = grouped["auth"]
            persistence_rows = grouped["persistence"]
            required = journey.get("opportunityId") in scored_ids
            if len(auth_rows) > 1 or len(persistence_rows) > 1:
                if required:
                    raise ValueError(f"duplicate source observation for token {token}")
                # F-ADH-077, replayed independently of the extractor's own count.
                source_counts["unscoredExcludedObservations"] += (
                    len(auth_rows) + len(persistence_rows))
                if witness_by_token.get(token):
                    raise ValueError(
                        f"excluded unscored source path emitted a witness for token {token}")
                continue
            if bool(auth_rows) != bool(persistence_rows):
                if required:
                    raise ValueError(f"required source path is partial for token {token}")
                source_counts["partialOptionalObservations"] += 1
                if witness_by_token.get(token):
                    raise ValueError(f"partial source path emitted a witness for token {token}")
                continue
            if not auth_rows:
                if required:
                    raise ValueError(f"required source path is absent for token {token}")
                if witness_by_token.get(token):
                    raise ValueError(f"absent source path emitted a witness for token {token}")
                continue
            auth_time = _iso(auth_rows[0]["observedAtUtc"])
            persistence_time = _iso(persistence_rows[0]["observedAtUtc"])
            journey_start = _iso(journey["startedAt"])
            journey_end = _iso(journey["endedAt"])
            if not journey_start <= auth_time <= persistence_time <= journey_end:
                if required:
                    raise ValueError(
                        f"required source pair is outside or reversed for token {token}")
                source_counts["unscoredExcludedObservations"] += (
                    len(auth_rows) + len(persistence_rows))
                if witness_by_token.get(token):
                    raise ValueError(
                        f"excluded unscored source path emitted a witness for token {token}")
                continue
            paired_tokens.add(token)
            source_counts["completeWitnessPaths"] += 1
            matches = witness_by_token.get(token, [])
            if len(matches) != 1:
                raise ValueError(f"source pair/witness cardinality differs for token {token}")
            witness = matches[0]
            if (witness.get("authObservedAtUtc") != auth_rows[0]["observedAtUtc"]
                    or witness.get("persistenceObservedAtUtc") != persistence_rows[0]["observedAtUtc"]):
                raise ValueError(f"source pair/witness projection differs for token {token}")
        if set(witness_by_token) != paired_tokens:
            raise ValueError("witness token set differs from independently replayed source pairs")
        source_replay_ok = True
        source_replay_observation = dict(source_counts)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        source_replay_observation = str(exc)
    report.check(
        "application-source-log-replay", source_replay_ok, source_replay_observation,
        "Raw service logs, not a self-declared extraction count, define the independent execution witness.",
        "Application source logs replay to the witness rows." if source_replay_ok else "Application source logs do not support the witness artifact.",
        failure="unsupported",
    )
    extraction_ok = False
    extraction_observation: Any = witness_extraction
    try:
        extraction_counts = witness_extraction["counts"]
        extraction_inputs = witness_extraction["inputs"]
        extraction_ok = (
            set(witness_extraction) == {
                "schema", "schemaVersion", "status", "sourceCommit", "regime",
                "measurementWindow", "counts", "inputs", "journeyLedgerValidation",
                "appWitnessSha256",
            }
            and witness_extraction.get("schema") == "teastore.app-witness-extraction-receipt"
            and witness_extraction.get("schemaVersion") == 1
            and witness_extraction.get("status") == "complete"
            and witness_extraction.get("sourceCommit") == SUT_COMMIT
            and witness_extraction.get("regime") == regime
            and witness_extraction.get("measurementWindow") == {
                "startedAt": window.get("measurementStartedAt"),
                "endedAt": window.get("measurementEndedAt"),
            }
            and set(extraction_counts) == {
                "ledgerOpportunities", "requiredScoredOpportunities", "completeWitnessPaths",
                "partialOptionalObservations", "unscoredExcludedObservations",
                "authObservations", "persistenceObservations", "phases",
            }
            and extraction_counts.get("ledgerOpportunities") == len(journeys)
            and extraction_counts.get("requiredScoredOpportunities") == len(scored_journeys)
            and extraction_counts.get("completeWitnessPaths") == len(witnesses)
            and extraction_counts.get("completeWitnessPaths")
                == source_counts["completeWitnessPaths"]
            and isinstance(extraction_counts.get("partialOptionalObservations"), int)
            and not isinstance(extraction_counts.get("partialOptionalObservations"), bool)
            and 0 <= extraction_counts["partialOptionalObservations"] <= (
                len(journeys) - len(scored_journeys)
            )
            and extraction_counts["partialOptionalObservations"]
                == source_counts["partialOptionalObservations"]
            and isinstance(extraction_counts.get("unscoredExcludedObservations"), int)
            and not isinstance(extraction_counts.get("unscoredExcludedObservations"), bool)
            and extraction_counts["unscoredExcludedObservations"] >= 0
            and extraction_counts["unscoredExcludedObservations"]
                == source_counts["unscoredExcludedObservations"]
            and isinstance(extraction_counts.get("authObservations"), int)
            and not isinstance(extraction_counts.get("authObservations"), bool)
            and isinstance(extraction_counts.get("persistenceObservations"), int)
            and not isinstance(extraction_counts.get("persistenceObservations"), bool)
            and extraction_counts["authObservations"] >= len(witnesses)
            and extraction_counts["persistenceObservations"] >= len(witnesses)
            and extraction_counts["authObservations"] == source_counts["authObservations"]
            and extraction_counts["persistenceObservations"]
                == source_counts["persistenceObservations"]
            and extraction_counts["authObservations"]
                + extraction_counts["persistenceObservations"]
                == 2 * len(witnesses) + extraction_counts["partialOptionalObservations"]
                + extraction_counts["unscoredExcludedObservations"]
            and extraction_counts.get("phases") == dict(sorted(phase_counts.items()))
            and set(extraction_inputs) == {
                "authLogSha256", "persistenceLogSha256", "journeyLedgerSha256",
                "journeyPlanSha256",
            }
            and extraction_inputs.get("authLogSha256") == _sha256(root / "auth.log")
            and extraction_inputs.get("persistenceLogSha256") == _sha256(root / "persistence.log")
            and extraction_inputs.get("journeyLedgerSha256") == _sha256(root / "journey-ledger.jsonl")
            and extraction_inputs.get("journeyPlanSha256") == _sha256(root / "journey-ledger.plan.json")
            and ledger_binding_ok
            and witness_extraction.get("journeyLedgerValidation") == {
                "verdict": "pass",
                "planSha256": _canonical_sha256(plan),
                "lastRecordSha256": (
                    ledger_records[-1].get("recordSha256") if ledger_records else None
                ),
                "terminalJourneys": len(journeys),
                "state": (
                    reconciliations[0].get("state") if len(reconciliations) == 1 else None
                ),
            }
            and witness_extraction.get("appWitnessSha256") == _sha256(root / "app-witness.jsonl")
            and source_replay_ok
        )
        extraction_observation = {
            "status": witness_extraction.get("status"), "counts": extraction_counts,
            "inputs": extraction_inputs, "appWitnessSha256": witness_extraction.get("appWitnessSha256"),
        }
    except (KeyError, TypeError, ValueError, OSError) as exc:
        extraction_observation = str(exc)
    report.check(
        "application-witness-extraction", extraction_ok, extraction_observation,
        "The independent source logs, scored population, and emitted witness rows require terminal hash reconciliation.",
        "Application witness extraction reconciles." if extraction_ok else "Application witness extraction is incomplete or unbound.",
        failure="unsupported",
    )
    witness_errors: list[dict[str, Any]] = [
        {"opportunityId": opportunity_id, "witnessRows": len(witness_by_opportunity.get(opportunity_id, []))}
        for opportunity_id in sorted(scored_ids, key=str)
        if len(witness_by_opportunity.get(opportunity_id, [])) != 1
    ]
    witness_errors.extend(
        {"opportunityId": opportunity_id, "witnessRows": len(matches), "error": "duplicate witness"}
        for opportunity_id, matches in witness_by_opportunity.items() if len(matches) > 1
    )
    witness_errors.extend(
        {"opportunityId": opportunity_id, "error": "not in expected-opportunity ledger"}
        for opportunity_id in witness_by_opportunity if opportunity_id not in ledger_opportunity_ids
    )
    eligible: list[dict[str, Any]] = []
    for journey in scored_journeys:
        matches = witness_by_opportunity.get(journey.get("opportunityId"), [])
        if len(matches) != 1:
            witness_errors.append({"opportunityId": journey.get("opportunityId"), "witnessRows": len(matches)})
            continue
        witness = matches[0]
        try:
            journey_started = _iso(journey["startedAt"])
            journey_ended = _iso(journey["endedAt"])
            auth_observed = _iso(witness["authObservedAtUtc"])
            persistence_observed = _iso(witness["persistenceObservedAtUtc"])
            witness_time_ok = (
                journey_started <= auth_observed <= persistence_observed <= journey_ended
                and _iso(witness["observedAt"]) == persistence_observed
            )
        except (KeyError, TypeError, ValueError):
            witness_time_ok = False
        observed_operations = [
            operation for operation, present in (
                ("auth", witness.get("authTraversed")),
                ("persistence", witness.get("persistenceTraversed")),
            ) if present is True
        ]
        exact = (
            set(witness) == {
                "schema", "schemaVersion", "journeyId", "opportunityId", "opaqueToken",
                "source", "independentOfKieker", "observedAt", "authObservedAtUtc",
                "persistenceObservedAtUtc", "authTraversed", "persistenceTraversed",
                "executedPath",
            }
            and witness.get("schema") == "teastore.app-witness"
            and witness.get("schemaVersion") == 1
            and witness.get("journeyId") == journey.get("journeyId")
            and witness.get("opaqueToken") == journey.get("opaqueToken")
            and witness.get("source") == "application-side"
            and witness.get("independentOfKieker") is True
            and witness.get("executedPath") == observed_operations
            and witness_time_ok
        )
        if not exact:
            witness_errors.append({"opportunityId": journey.get("opportunityId"), "error": "identity/source/path mismatch"})
            continue
        if witness["executedPath"] == ["auth", "persistence"]:
            eligible.append(journey)
    witness_ok = not witness_errors and bool(scored_journeys)
    report.check(
        "independent-execution-denominator", witness_ok,
        {"scoredExpectedOpportunities": len(scored_journeys), "witnessRows": len(witnesses),
         "eligibleExecutedPaths": len(eligible), "errors": witness_errors[:20]},
        "Expected opportunities do not prove execution; an independent application witness defines eligibility.",
        "Executed-path denominator is independently observed." if witness_ok else "Executed-path denominator is unsupported.",
        failure="unsupported",
    )

    reconstructed = 0
    correlation_errors: list[dict[str, Any]] = []
    path_details: list[dict[str, Any]] = []
    trace_coverage: dict[str, Any] | None = None
    if posture == "none":
        correlation_ok = (
            witness_ok and bool(eligible) and terminal_counts_ok and not traces
            and native_token_artifact_ok and not native_token_correlation
            and native_integrity_ok
        )
        if correlation_ok:
            path_details = [{"opportunityId": row["opportunityId"], "reconstructed": False} for row in eligible]
    else:
        mappings_by_token: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        tokens_by_trace: dict[Any, set[Any]] = defaultdict(set)
        for mapping_index, mapping in enumerate(native_token_correlation, 1):
            if not isinstance(mapping, dict):
                correlation_errors.append({
                    "mappingRow": mapping_index, "error": "mapping row is not an object"})
                continue
            mapping_token = mapping.get("token")
            mapping_trace = mapping.get("nativeTraceId")
            try:
                hash(mapping_token)
                hash(mapping_trace)
            except TypeError:
                correlation_errors.append({
                    "mappingRow": mapping_index,
                    "error": "mapping identity is not scalar/hashable",
                })
                continue
            mappings_by_token[mapping_token].append(mapping)
            tokens_by_trace[mapping_trace].add(mapping_token)
        eligible_tokens = {journey.get("opaqueToken") for journey in eligible}
        unexpected_mapping_tokens = sorted(
            (token for token in mappings_by_token if token not in eligible_tokens),
            key=str,
        )
        if unexpected_mapping_tokens:
            correlation_errors.append({
                "error": "native mapping contains tokens outside the independently eligible denominator",
                "tokens": unexpected_mapping_tokens[:20],
            })
        events_by_trace: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for event in measurement_events:
            events_by_trace[_original_native_trace_id(event)].append(event)
        trace_edges: dict[Any, dict[str, bool]] = {}
        for journey in eligible:
            token = journey.get("opaqueToken")
            mappings = mappings_by_token.get(token, [])
            if len(mappings) != 1:
                correlation_errors.append({"opportunityId": journey.get("opportunityId"),
                                           "mappingCount": len(mappings)})
                continue
            mapping = mappings[0]
            native_trace_id = mapping.get("nativeTraceId")
            events = events_by_trace.get(native_trace_id, [])
            if not events:
                correlation_errors.append({"opportunityId": journey.get("opportunityId"),
                                           "error": "mapped native trace has no measurement events"})
                continue
            if not entry_woven:
                # F-ADH-066 measure-don't-reject: without the trace-root sensor a
                # native trace is per-worker-thread, spanning many journeys and
                # tokens, so per-request window containment and the trace<->token
                # bijection are structurally absent rather than defective. The
                # real auth->persistence coverage is measured at trace
                # granularity instead; request-root reconstruction stays 0.
                if native_trace_id not in trace_edges:
                    auth_span_ids = {event.get("span_id") for event in events
                                     if _logical_role(event) == "auth"}
                    trace_edges[native_trace_id] = {
                        "hasAuthOperations": bool(auth_span_ids),
                        "hasPersistenceOperations": any(
                            _logical_role(event) == "persistence" for event in events),
                        "directAuthPersistenceEdge": any(
                            _logical_role(event) == "persistence"
                            and _parent_id(event) in auth_span_ids
                            for event in events
                        ),
                    }
                path_details.append({
                    "opportunityId": journey.get("opportunityId"),
                    "mappingId": mapping.get("mappingId"),
                    "originalNativeTraceId": native_trace_id,
                    "reconstructed": False,
                    "requestRootReconstruction": "structurally-absent",
                    "traceLevelDirectEdge": trace_edges[native_trace_id]["directAuthPersistenceEdge"],
                })
                continue
            try:
                journey_start = _iso(journey["startedAt"])
                journey_end = _iso(journey["endedAt"])
                if not all(journey_start <= _native_time(event) <= journey_end for event in events):
                    correlation_errors.append({"opportunityId": journey.get("opportunityId"),
                                               "error": "native event outside correlated journey window"})
                    continue
            except (KeyError, TypeError, ValueError, OverflowError, OSError):
                correlation_errors.append({"opportunityId": journey.get("opportunityId"),
                                           "error": "correlated timestamp unavailable"})
                continue
            if tokens_by_trace[native_trace_id] != {token}:
                correlation_errors.append({"opportunityId": journey.get("opportunityId"),
                                           "error": "native trace maps to multiple tokens"})
                continue
            auth_span_ids = {event.get("span_id") for event in events if _logical_role(event) == "auth"}
            has_persistence = any(_logical_role(event) == "persistence" for event in events)
            direct = any(
                _logical_role(event) == "persistence" and _parent_id(event) in auth_span_ids
                for event in events
            )
            is_reconstructed = bool(auth_span_ids) and has_persistence and direct
            reconstructed += int(is_reconstructed)
            path_details.append({
                "opportunityId": journey.get("opportunityId"),
                "mappingId": mapping.get("mappingId"),
                "originalNativeTraceId": native_trace_id,
                "requiredOperationsPresent": bool(auth_span_ids) and has_persistence,
                "directAuthPersistenceEdge": direct,
                "reconstructed": is_reconstructed,
            })
        if not entry_woven:
            trace_coverage = {
                "mappedTraces": len(trace_edges),
                "tracesWithDirectAuthPersistenceEdge": sum(
                    edge["directAuthPersistenceEdge"] for edge in trace_edges.values()),
                "eligibleJourneysOnTracesWithDirectEdge": sum(
                    1 for detail in path_details if detail.get("traceLevelDirectEdge")),
            }
        correlation_ok = (
            witness_ok and bool(eligible) and native_token_artifact_ok
            and native_integrity_ok and not correlation_errors
        )
    report.check(
        "opaque-token-native-trace-correlation", correlation_ok,
        {"eligibleExecutedPaths": len(eligible), "correlationErrors": correlation_errors[:20],
         "entryPointWoven": entry_woven, "traceLevelCoverage": trace_coverage},
        "Each pre-outcome workload token must join through the separately extracted auth-log "
        "bridge to exactly one original native trace; native events carry no workload token. "
        "When the replayed closure omits the trace-root sensor, per-request window containment "
        "and the trace<->token bijection are structurally absent and are measured as trace-level "
        "coverage instead of being required (F-ADH-066).",
        "Correlation is complete." if correlation_ok else "Correlation is missing or ambiguous; zero is not observed.",
        failure="unsupported",
    )

    result["views"] = {
        "raw": raw_view,
        "signatureWeighted": signature_view,
        "path": {
            "expectedOpportunities": len(scored_journeys),
            "eligibleExecutedPaths": len(eligible) if witness_ok else None,
            "details": path_details if correlation_ok else [],
        },
    }
    # A numeric endpoint is released only after every gate, including replay and
    # window checks, is green.  Diagnostic counts remain visible above.
    if report.verdict == "pass" and correlation_ok:
        denominator = len(eligible)
        if posture != "none" and not entry_woven and trace_coverage is not None:
            # F-ADH-066: the per-request fraction remains the endpoint and is
            # honestly 0 without a request root; trace-level coverage is a
            # distinct, clearly-labeled aggregate crediting the placement's real
            # auth->persistence visibility. No detection/RCA claim follows.
            result["reconstruction"] = {
                "status": "request-root-structurally-absent",
                "eligibleExecutedPaths": denominator,
                "reconstructedPaths": 0,
                "fraction": 0.0,
                "traceLevelCoverage": trace_coverage | {
                    "journeyFraction": (
                        trace_coverage["eligibleJourneysOnTracesWithDirectEdge"] / denominator),
                },
            }
        else:
            result["reconstruction"] = {
                "status": "supported",
                "eligibleExecutedPaths": denominator,
                "reconstructedPaths": reconstructed,
                "fraction": reconstructed / denominator,
            }
    result["verdict"] = report.verdict
    result["cellStatus"] = report.cell_status
    result["validationTable"] = report.rows
    return result


def validate_campaign(root: Path) -> dict[str, Any]:
    """Validate the exact frozen 27-cell allocation and every declared run root."""
    root = Path(root)
    report = _Report()
    manifest_path = root / "campaign.json"
    if not manifest_path.is_file():
        report.check(
            "campaign-manifest", False, {"path": str(manifest_path)},
            "The scheduled population must exist before outcomes are read.",
            "campaign.json is absent.", failure="missing-artifact",
        )
        return {
            "schemaVersion": 1, "contract": CONTRACT, "kind": "campaign-validation",
            "verdict": report.verdict, "campaignStatus": report.cell_status,
            "validationTable": report.rows, "runReports": [],
        }
    try:
        manifest = _read_json(manifest_path)
    except (OSError, ValueError, TypeError) as exc:
        report.check(
            "campaign-manifest", False, str(exc), "The scheduled population cannot be parsed.",
            "campaign.json is unreadable.", failure="missing-artifact",
        )
        return {
            "schemaVersion": 1, "contract": CONTRACT, "kind": "campaign-validation",
            "verdict": report.verdict, "campaignStatus": report.cell_status,
            "validationTable": report.rows, "runReports": [],
        }

    if SWEEP:
        # Traffic sweep: the allocation is recompiled from the installed descriptor (pinned digests).
        sweep_compiler = _sweep_compiler()
        sweep_plan = sweep_compiler.compile_plan(sweep_compiler.load_descriptor(
            Path(__file__).resolve().parents[3] / sweep_compiler.DESCRIPTOR_RELATIVE))
        allocation = sweep_plan["scheduleAllocation"]
        computed_digests = {regime: allocation[regime]["selectorSha256"] for regime in allocation}
        computed_schedules = {regime: allocation[regime]["blocks"] for regime in allocation}
        schedule_ok = (
            manifest.get("contract") == CONTRACT
            and manifest.get("studyEpoch") == STUDY_EPOCH
            and manifest.get("scheduleVersion") == sweep_compiler.SCHEDULE_CONTEXT
            and manifest.get("selectorDigests") == computed_digests
            and manifest.get("schedules") == computed_schedules
        )
    else:
        computed_digests, computed_schedules = recompute_schedule()
        schedule_ok = (
            manifest.get("contract") == CONTRACT
            and manifest.get("studyEpoch") == STUDY_EPOCH
            and manifest.get("scheduleVersion") == "schedule-v1"
            and manifest.get("selectorDigests") == computed_digests == EXPECTED_SELECTOR_DIGESTS
            and manifest.get("schedules") == computed_schedules == EXPECTED_SCHEDULES
        )
    report.check(
        "frozen-schedule-recomputation", schedule_ok,
        {"declaredDigests": manifest.get("selectorDigests"), "computedDigests": computed_digests,
         "declaredSchedules": manifest.get("schedules"), "computedSchedules": computed_schedules},
        "The exact hash allocation is recomputed independently and cannot be rerandomized on resume.",
        "Frozen schedule matches recomputation." if schedule_ok else "Schedule bytes or allocation drifted.",
    )

    declared_runs = manifest.get("runs") if isinstance(manifest.get("runs"), list) else []
    if SWEEP:
        expected_cells = [
            {**cell["runKey"], "ordinal": cell["ordinalPosition"], "runId": cell["runId"]}
            for cell in sweep_compiler.flatten_cells(sweep_plan)
        ]
    else:
        expected_cells = [
            {"studyEpoch": STUDY_EPOCH, "regime": regime, "block": block,
             "posture": posture, "attempt": 1, "ordinal": ordinal}
            for regime in REGIMES
            for block, row in enumerate(EXPECTED_SCHEDULES[regime], 1)
            for ordinal, posture in enumerate(row, 1)
        ]
    observed_cells = [{key: item.get(key) for key in (*expected_cells[0].keys(),)} for item in declared_runs]
    population_ok = observed_cells == expected_cells and len(declared_runs) == EPOCH["runCount"]
    paths = [item.get("path") for item in declared_runs]
    paths_ok = (
        not _duplicates(paths)
        and all(
            isinstance(item.get("path"), str)
            and Path(item["path"]).parts[:2] == ("runs", item.get("regime"))
            and not Path(item["path"]).is_absolute()
            and ".." not in Path(item["path"]).parts
            for item in declared_runs
        )
    )
    report.check(
        "scheduled-cell-population", population_ok,
        {"declaredCells": len(declared_runs), "expectedCells": EPOCH["runCount"],
         "firstMismatch": next((index for index, pair in enumerate(zip(observed_cells, expected_cells), 1)
                                if pair[0] != pair[1]), None)},
        "All 27 cells, including failed attempts, remain in exact randomized order.",
        "Scheduled population is exact." if population_ok else "Scheduled population is incomplete, duplicated, or reordered.",
    )
    report.check(
        "separate-regime-artifact-roots", paths_ok,
        {"duplicatePaths": _duplicates(paths), "paths": paths},
        "Cost and each effect regime require distinct cold-start artifact roots.",
        "Run roots are unique and regime-separated." if paths_ok else "Run roots overlap or escape their regime.",
    )

    run_reports: list[dict[str, Any]] = []
    if population_ok and paths_ok:
        for item in declared_runs:
            expected = {key: item[key] for key in ("studyEpoch", "regime", "block", "posture", "attempt")}
            if SWEEP:
                expected["runId"] = item["runId"]
            run_report = validate_run(root / item["path"], expected)
            run_reports.append(run_report)
        child_ok = all(child["verdict"] == "pass" for child in run_reports)
        report.check(
            "all-run-evidence", child_ok,
            {"valid": sum(child["verdict"] == "pass" for child in run_reports),
             "blocked": sum(child["verdict"] != "pass" for child in run_reports)},
            "A campaign endpoint cannot substitute a diagnostic rerun for an invalid scheduled cell.",
            "All scheduled cells validate." if child_ok else "At least one scheduled cell is not valid.",
            failure="unsupported" if any(child["cellStatus"] == "unsupported" for child in run_reports) else "invalid",
        )
    result = {
        "schemaVersion": 1,
        "contract": CONTRACT,
        "kind": "campaign-validation",
        "verdict": report.verdict,
        "campaignStatus": report.cell_status,
        "validationTable": report.rows,
        "runReports": run_reports,
        "claimBoundary": (
            "Complete valid blocks permit descriptive paired deltas only; no p-value, canonical "
            "evidence, causal, optimizer, or generality claim follows."
        ),
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_root", type=Path)
    parser.add_argument("--campaign", action="store_true", help="validate campaign.json and all 27 run roots")
    parser.add_argument("--output", type=Path, help="also write the JSON report atomically")
    args = parser.parse_args(argv)
    result = validate_campaign(args.artifact_root) if args.campaign else validate_run(args.artifact_root)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(encoded, end="")
    if args.output:
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(args.output)
    return 0 if result["verdict"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
