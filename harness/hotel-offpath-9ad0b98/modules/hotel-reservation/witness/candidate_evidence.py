#!/usr/bin/env python3
"""Replay request witnesses and original-Jaeger-trace correlation for Hotel."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, NoReturn


ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "modules" / "hotel-reservation"
WORKLOAD_MODULE = MODULE / "workload" / "candidate_search.py"
WITNESS_PREFIX = "OBSPLACEMENT_WITNESS "
TOKEN = re.compile(r"^hr-[0-9a-f]{32}$")
TRACE_ID = re.compile(r"^[0-9a-f]{16}(?:[0-9a-f]{16})?$")
# Bounded settle after the readiness probe during which a request still counts
# as `during` (see phaseBoundaries below). Measured spill-over across all 16
# full fault cells of Hotel #2/#3: one request at +0.020 s; the margin is 50x
# that and 1/15 of the hold, so it cannot absorb loss the pause does not explain.
POST_READINESS_SETTLE_SECONDS = 1.0
WITNESS_FIELDS = {
    "schema", "opaqueToken", "method", "routePattern", "statusCode",
    "startedAtUnixNano", "endedAtUnixNano",
}


class WitnessError(ValueError):
    """The application witness, fault truth, or native correlation is invalid."""


class TraceDefect(WitnessError):
    """One correlated native trace fails its structural ground truth (same messages as before).

    ``absence`` marks an incomplete trace in the sense of protocol decision 25 (a missing required service edge,
    span or parent); every other defect (duplicate span IDs, a second root, a parentService that disagrees with
    its parent, a cycle) is malformed, not incomplete.  The frozen epoch treats both as the WitnessError it always
    raised.
    """

    def __init__(self, message: str, code: str, *, absence: bool) -> None:
        super().__init__(message)
        self.code = code
        self.absence = absence


# Protocol decision 25 (user, 2026-10-03; measurement repo research/PROTOCOL_DRAFT_20261002.md), parameterised
# (sweep) epochs only.  (i) Requests whose ledger start lies in [fault receipt start, readyAt + the cell's client
# timeout + TRACE_DRAIN_MARGIN_SECONDS) may have incomplete traces: recorded as fault effect, never blocking.
# (ii) Everywhere else (pre-onset, after the drain window, a no-fault cell's whole window) the cell blocks only
# when more than max(TRACE_INCOMPLETE_MINIMUM, floor(TRACE_INCOMPLETE_PERCENT % of the successful requests there))
# traces are incomplete.  (iii) Every incomplete trace is counted and reported per window.
TRACE_COMPLETENESS_RULE = "protocol-decision-25-v1"
TRACE_DRAIN_MARGIN_SECONDS = 2.0
TRACE_INCOMPLETE_PERCENT = 1
TRACE_INCOMPLETE_MINIMUM = 1
FAULT_DRAIN_WINDOW = "fault-drain"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise WitnessError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


workload = _load("hotel_candidate_workload_for_witness", WORKLOAD_MODULE)


def _reject_constant(value: str) -> NoReturn:
    raise WitnessError(f"non-finite JSON value is forbidden: {value}")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise WitnessError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json(value: str, where: str) -> Any:
    try:
        return json.loads(value, object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except WitnessError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WitnessError(f"invalid JSON in {where}: {exc}") from exc


def _number(value: Any, *, minimum: float | None = None) -> bool:
    valid = (
        isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(float(value))
    )
    return valid and (minimum is None or float(value) >= minimum)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, allow_nan=False, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def ledger_rows(path: Path) -> list[dict[str, Any]]:
    try:
        payload = path.read_bytes()
        text = payload.decode("utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise WitnessError(f"cannot read opportunity ledger: {exc}") from exc
    if not payload.endswith(b"\n"):
        raise WitnessError("opportunity ledger is truncated")
    rows = [strict_json(line, f"ledger line {index + 1}") for index, line in enumerate(text.splitlines())]
    if not rows:
        raise WitnessError("opportunity ledger is empty")
    return rows


def parse_application_witnesses(log_text: str) -> list[dict[str, Any]]:
    rows = []
    identities: set[str] = set()
    for line_number, line in enumerate(log_text.splitlines(), start=1):
        marker = line.find(WITNESS_PREFIX)
        if marker < 0:
            continue
        row = strict_json(line[marker + len(WITNESS_PREFIX):], f"witness line {line_number}")
        if not isinstance(row, dict) or set(row) != WITNESS_FIELDS:
            raise WitnessError("application witness fields differ")
        token = row.get("opaqueToken")
        if (
            row.get("schema") != "hotel-application-request-witness-v1"
            or TOKEN.fullmatch(str(token)) is None
            or token in identities
            or row.get("method") != "GET"
            or row.get("routePattern") != "/hotels"
            or type(row.get("statusCode")) is not int
            or not 100 <= row["statusCode"] <= 599
            or type(row.get("startedAtUnixNano")) is not int
            or type(row.get("endedAtUnixNano")) is not int
            or row["endedAtUnixNano"] < row["startedAtUnixNano"]
        ):
            raise WitnessError("application witness identity or execution bounds differ")
        identities.add(token)
        rows.append(row)
    return sorted(rows, key=lambda row: row["opaqueToken"])


PAUSE_TARGETS = {"search-pause": "search", "reservation-pause": "reservation"}
# hotel-offpath-v1: a pause of a container off the request path.  Same receipt, same ordering and hold rules as an
# on-path pause; the differences are (1) the route outage is recorded but not required (receipt `manifested` is the
# container read back as paused) and (2) no fault-specific path ground truth: it is not in PAUSE_TARGETS, so
# during-fault traces keep the normal path and no truncation is excused (as for the degradations).
OFFPATH_PAUSE_TARGETS = {"consul-pause": "consul"}
DEGRADATION_TARGETS = {"profile-cpu-throttle": "profile", "rate-net-delay": "rate"}


def _commands_ok(commands: Any, actions: list[str]) -> bool:
    return (
        isinstance(commands, list)
        and [row.get("action") for row in commands if isinstance(row, dict)] == actions
        and not any(
            not isinstance(row, dict)
            or set(row) != {"action", "returnCode", "stdout", "stderr"}
            or row["returnCode"] != 0
            or not isinstance(row["stdout"], str)
            or not isinstance(row["stderr"], str)
            for row in commands
        )
    )


# The frozen epoch's schedule (onset 45 s, hold 15 s, >= 100 witnessed starts per phase).  A parameterised
# epoch passes its cell's compiled `timing` instead; `timing=None` is the frozen epoch, unchanged.
FROZEN_FAULT_ONSET_SECONDS = 45
FROZEN_FAULT_HOLD_SECONDS = 15
FROZEN_MINIMUM_PHASE_STARTS = 100
ONSET_EARLY_TOLERANCE_SECONDS = 0.05
ONSET_LATE_TOLERANCE_SECONDS = 2.0


def _schedule(timing: Any) -> tuple[Any, Any]:
    if timing is None:
        return FROZEN_FAULT_ONSET_SECONDS, FROZEN_FAULT_HOLD_SECONDS
    if not isinstance(timing, dict) or not _number(timing.get("faultOnsetSeconds"), minimum=0) or not _number(
        timing.get("faultHoldSeconds"), minimum=0
    ):
        raise WitnessError("cell timing lacks a fault onset and hold")
    return timing["faultOnsetSeconds"], timing["faultHoldSeconds"]


def validate_fault_receipt(
    receipt: Any, scenario: str | None, *, barrier_monotonic: float | None = None,
    timing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if scenario is None:
        if receipt is not None:
            raise WitnessError("no-fault cost cell contains an intervention receipt")
        return {
            "state": "not-applicable", "valid": True, "scenario": None,
            "phaseBoundaries": None, "detectionWindowMonotonic": None,
        }
    if scenario in PAUSE_TARGETS or scenario in OFFPATH_PAUSE_TARGETS:
        required = {
            "schemaVersion", "faultKind", "scenario", "targetService", "scheduledAtSeconds",
            "requestedOutageSeconds", "startedAt", "endedAt", "manifested",
            "outageObserved", "recovered", "successful", "preState",
            "preRouteAvailable", "duringState", "recoveryState", "startedMonotonic",
            "appliedMonotonic", "revertingMonotonic",
            "unpausedAtMonotonic", "readyAtMonotonic", "endedMonotonic", "commands",
            "error", "actualOutageSeconds",
        }
        target = PAUSE_TARGETS[scenario] if scenario in PAUSE_TARGETS else OFFPATH_PAUSE_TARGETS[scenario]
        kind, hold_key, actual_key = "pause", "requestedOutageSeconds", "actualOutageSeconds"
        end_key, actions = "unpausedAtMonotonic", ["pause", "unpause"]
    elif scenario in DEGRADATION_TARGETS:
        required = {
            "schemaVersion", "faultKind", "scenario", "targetService", "scheduledAtSeconds",
            "requestedHoldSeconds", "startedAt", "endedAt", "manifested", "reverted",
            "recovered", "successful", "preClean", "preRouteAvailable", "routeAvailableDuring",
            "startedMonotonic", "appliedMonotonic", "revertingMonotonic", "revertedAtMonotonic",
            "readyAtMonotonic", "endedMonotonic", "commands", "error", "actualHoldSeconds",
        }
        target, kind, hold_key, actual_key = DEGRADATION_TARGETS[scenario], "degradation", "requestedHoldSeconds", "actualHoldSeconds"
        end_key, actions = "revertedAtMonotonic", ["apply", "revert"]
    else:
        raise WitnessError("fault scenario is not declared")
    stamped = bool(timing is not None and timing.get("probeStamps"))
    if stamped:
        required = required | {"probes"}
    if not isinstance(receipt, dict) or set(receipt) != required:
        raise WitnessError("fault receipt fields differ")
    if stamped:
        probes = receipt["probes"]
        if (not isinstance(probes, list)
                or any(not isinstance(row, dict)
                       or set(row) != {"phase", "startMonotonic", "endMonotonic", "available"}
                       or row["phase"] not in ("pre", "during")
                       or not isinstance(row["available"], bool)
                       or not all(isinstance(row[key], (int, float)) and math.isfinite(row[key])
                                  for key in ("startMonotonic", "endMonotonic"))
                       or row["endMonotonic"] < row["startMonotonic"]
                       for row in probes)
                or [row["phase"] for row in probes] not in ([], ["pre"], ["pre", "during"])):
            raise WitnessError("fault receipt probe stamps are malformed")
    scheduled_onset, scheduled_hold = _schedule(timing)
    started = receipt.get("startedMonotonic")
    applied = receipt.get("appliedMonotonic")
    reverting = receipt.get("revertingMonotonic")
    ended_fault = receipt.get(end_key)
    ready = receipt.get("readyAtMonotonic")
    ended = receipt.get("endedMonotonic")
    try:
        started_wall = workload.parse_iso(receipt.get("startedAt"), "fault startedAt")
        ended_wall = workload.parse_iso(receipt.get("endedAt"), "fault endedAt")
    except workload.LedgerError as exc:
        raise WitnessError(str(exc)) from exc
    common_bad = (
        receipt.get("schemaVersion") != 1
        or receipt.get("faultKind") != kind
        or receipt.get("scenario") != scenario
        or receipt.get("targetService") != target
        or receipt.get("successful") is not True
        or receipt.get("manifested") is not True
        or receipt.get("recovered") is not True
        or receipt.get("preRouteAvailable") is not True
        or receipt.get("error") is not None
        or receipt.get("scheduledAtSeconds") != scheduled_onset
        or receipt.get(hold_key) != scheduled_hold
        or ended_wall < started_wall
        or not all(_number(value, minimum=0) for value in (started, applied, reverting, ended_fault, ready, ended))
        or not float(started) <= float(applied) < float(reverting) <= float(ended_fault) <= float(ready) <= float(ended)
        or not _number(receipt.get(actual_key), minimum=float(receipt[hold_key]))
        # D21: the hold must be the preregistered duration, not "at least" it;
        # 2 s covers the command round trips, not a probe timeout.
        or float(receipt[actual_key]) > float(receipt[hold_key]) + 2.0
        or not _commands_ok(receipt.get("commands"), actions)
    )
    if kind == "pause":
        pre, during, recovery = receipt.get("preState"), receipt.get("duringState"), receipt.get("recoveryState")
        kind_bad = (
            # On-path: the outage must be observed.  Off-path: it is recorded (a bool), never required.
            (receipt.get("outageObserved") is not True if scenario in PAUSE_TARGETS
             else not isinstance(receipt.get("outageObserved"), bool))
            or not isinstance(pre, dict) or pre.get("running") is not True or pre.get("paused") is not False
            or not isinstance(during, dict) or during.get("running") is not True or during.get("paused") is not True
            or not isinstance(recovery, dict) or recovery.get("running") is not True or recovery.get("paused") is not False
        )
    else:
        kind_bad = (
            receipt.get("preClean") is not True or receipt.get("reverted") is not True
            or not isinstance(receipt.get("routeAvailableDuring"), bool)
        )
    if common_bad or kind_bad:
        raise WitnessError("fault manifestation, recovery, or monotonic truth differs")
    if barrier_monotonic is not None:
        if not _number(barrier_monotonic, minimum=0):
            raise WitnessError("fault barrier monotonic value is invalid")
        onset = float(started) - float(barrier_monotonic)
        # F-ADH-085: `startedMonotonic` is stamped immediately BEFORE the fault command (compose_pause.py,
        # lmt_faults.py), so the onset is bounded by the scheduled command, never by a later probe.
        if timing is None:
            if onset < 44.95 or onset > 47.0:
                raise WitnessError("observed fault onset differs from the admitted 45-second schedule")
        elif (
            onset < float(scheduled_onset) - ONSET_EARLY_TOLERANCE_SECONDS
            or onset > float(scheduled_onset) + ONSET_LATE_TOLERANCE_SECONDS
        ):
            raise WitnessError(
                "observed fault onset differs from the admitted %.6f-second schedule" % float(scheduled_onset)
            )
    return {
        "state": "supported", "valid": True, "scenario": scenario, "faultKind": kind,
        "phaseBoundaries": {
            "faultStartedMonotonic": started,
            "faultUnpausedMonotonic": ended_fault,
            "postReadinessMonotonic": ready,
            # See Hotel #3 cell 24: requests inside this bounded settle margin after
            # the readiness probe still count as `during`.
            "duringSettleEndMonotonic": ready + POST_READINESS_SETTLE_SECONDS,
            "postReadinessSettleSeconds": POST_READINESS_SETTLE_SECONDS,
        },
        # LMT+S pilot: the detection window, strictly inside the fault.
        "detectionWindowMonotonic": [applied, reverting],
    }


# Postures whose native capture must be terminally complete and empty, with the
# classification each one is allowed to claim.  ``sample-zero`` builds a real
# jaeger.Tracer with ratio 0 (acquisition-negative); ``none`` is JAEGER_DISABLED
# -> opentracing.NoopTracer (tracer-disabled).  Neither is source-off: the
# nethttp/otgrpc wrappers stay installed on every handler and dialer.
EMPTY_CAPTURE_POSTURES = {
    "none": "logs-fatal-sampler-off-tracer-disabled",
    "metrics": "logs-info-sampler-on-tracer-disabled",
}
SUPPORTED_POSTURES = ("none", "metrics", "selected", "full")
# Postures that trace a subset only: each trace must be one frontend-rooted tree whose every span comes from
# a traced service; the normal-path edges cannot exist in it by construction, so they are not required.
PARTIAL_TRACE_SERVICES = {"selected": frozenset({"frontend"})}


def empty_capture_proof(
    posture: str, raw: Any, normalized: Any, capture_terminal: Any,
) -> dict[str, Any] | None:
    if posture not in EMPTY_CAPTURE_POSTURES:
        return None
    if not isinstance(raw, dict) or not isinstance(normalized, dict) or not isinstance(capture_terminal, dict):
        raise WitnessError(f"{posture} empty capture inputs are missing")
    queries = raw.get("queries")
    if (
        raw.get("schemaVersion") != 1
        or raw.get("collector") != "jaeger-query-api-v1"
        or not isinstance(queries, list) or not queries
        or any(
            not isinstance(query, dict)
            or query.get("response", {}).get("errors")
            or query.get("traceCount") != 0
            or query.get("response", {}).get("data") != []
            for query in queries
        )
        or normalized.get("normalizer") != "hotel-reservation-jaeger-v1"
        or normalized.get("spanCount") != 0
        or normalized.get("uniqueTraceCount") != 0
        or normalized.get("queryLimitReached") is not False
        or capture_terminal != {
            "schemaVersion": 1,
            "kind": "hotel-jaeger-capture-terminal-v1",
            "queriesComplete": True,
            "collectorTailComplete": True,
            "backendReadyAtTerminal": True,
        }
    ):
        raise WitnessError(f"{posture} capture is not terminally complete and empty")
    return {
        "schemaVersion": 1,
        "kind": f"hotel-{posture}-empty-capture-proof-v1",
        "verdict": "pass",
        "spanCount": 0,
        "uniqueTraceCount": 0,
        "executedOpportunityRequired": True,
        "sourceWorkDisabled": False,
        "classification": EMPTY_CAPTURE_POSTURES[posture],
    }


def _native_tree(
    events: list[dict[str, Any]], *, unreported_parents: frozenset[str],
) -> dict[str, Any]:
    """Walk one native span tree, returning its edges and its unreported parents.

    ``unreported_parents`` names the services whose own spans the caller has
    independently proven may be absent from this trace.  A dangling parentSpanId
    is admissible only for a child of one of those services; every other
    structural claim (one frontend root, unique span IDs, parentService agreeing
    with the resolved parent, acyclic parent chains) stays unconditional.
    """
    by_span: dict[str, dict[str, Any]] = {}
    for event in events:
        span_id = event.get("spanId")
        if not isinstance(span_id, str) or not span_id or span_id in by_span:
            raise TraceDefect("native trace contains a missing or duplicate span ID", "span-id-missing-or-duplicate",
                              absence=False)
        by_span[span_id] = event
    roots = [event for event in events if event.get("parentSpanId") is None]
    if len(roots) != 1 or roots[0].get("service") != "frontend":
        raise TraceDefect("native trace does not have exactly one frontend root", "root-not-one-frontend",
                          absence=False)
    observed_edges: set[tuple[str, str]] = set()
    dangling: list[str] = []
    for event in events:
        parent_id = event.get("parentSpanId")
        if parent_id is None:
            if event.get("parentService") is not None:
                raise TraceDefect("native root unexpectedly declares a parent service", "root-declares-parent",
                                  absence=False)
            continue
        parent = by_span.get(parent_id)
        if parent is None:
            # An unreported parent is only ever admissible for a child of a
            # service whose spans the caller proved cannot have been reported;
            # Jaeger also cannot name such a parent, hence parentService None.
            if (
                str(event.get("service")) not in unreported_parents
                or event.get("parentService") is not None
            ):
                raise TraceDefect("native trace parentSpanId is missing from the same trace", "dangling-parent",
                                  absence=True)
            dangling.append(str(event.get("service")))
            continue
        if event.get("parentService") != parent.get("service"):
            raise TraceDefect("native trace parentService disagrees with parentSpanId", "parent-service-disagrees",
                              absence=False)
        observed_edges.add((str(parent.get("service")), str(event.get("service"))))
    # Following parent IDs must terminate at the sole root or at an admissible
    # unreported parent; this also rejects cycles.
    for event in events:
        seen: set[str] = set()
        cursor = event
        while cursor.get("parentSpanId") is not None:
            span_id = str(cursor.get("spanId"))
            if span_id in seen:
                raise TraceDefect("native trace parent graph contains a cycle", "parent-cycle", absence=False)
            seen.add(span_id)
            parent = by_span.get(str(cursor["parentSpanId"]))
            if parent is None:
                break
            cursor = parent
    return {
        "observedEdges": observed_edges,
        "danglingParentServices": sorted(dangling),
        "attemptedServices": {str(event.get("service")) for event in events},
    }


def _validate_native_trace(
    trace_id: str, events: list[dict[str, Any]], required_edges: list[list[str]],
) -> None:
    """Require one internally consistent native span tree and its service edges."""
    tree = _native_tree(events, unreported_parents=frozenset())
    required = {tuple(edge) for edge in required_edges}
    if not required.issubset(tree["observedEdges"]):
        raise TraceDefect("native trace lacks a required same-trace service edge", "required-edge-missing",
                          absence=True)


def _validate_partial_trace(trace_id: str, events: list[dict[str, Any]], traced: frozenset) -> None:
    """One internally consistent tree, every span from a traced service (a partial posture's whole claim)."""
    _native_tree(events, unreported_parents=frozenset())
    services = {event.get("service") for event in events}
    if not services or not services <= traced:
        raise TraceDefect("partial-posture trace carries a span of an untraced service", "untraced-service-span",
                          absence=False)


def _fault_specific_truth(path_truth: dict[str, Any], scenario: str) -> dict[str, Any]:
    """Return the one preregistered fault-specific path ground truth for a scenario."""
    candidates = path_truth.get("faultSpecific")
    if not isinstance(candidates, list):
        raise WitnessError("descriptor lacks fault-specific path ground truth")
    matches = [
        row for row in candidates
        if isinstance(row, dict) and row.get("fault") == scenario
    ]
    if len(matches) != 1:
        raise WitnessError("descriptor lacks exactly one fault-specific path ground truth")
    truth = matches[0]
    if (
        set(truth) != {
            "id", "fault", "targetService", "requiredAttemptedPrefix",
            "downstreamNotRequiredDuringFault", "nativeOperationQualification",
            "numericValueWhenUnsupported",
        }
        or not isinstance(truth["id"], str) or not truth["id"]
        or not isinstance(truth["targetService"], str) or not truth["targetService"]
        or not isinstance(truth["requiredAttemptedPrefix"], list)
        or not truth["requiredAttemptedPrefix"]
        or not all(isinstance(name, str) and name for name in truth["requiredAttemptedPrefix"])
        or not isinstance(truth["downstreamNotRequiredDuringFault"], list)
        or truth["nativeOperationQualification"] != "unsupported-until-runtime-characterization"
        or truth["numericValueWhenUnsupported"] is not None
    ):
        raise WitnessError("fault-specific path ground truth is incomplete")
    return truth


def _service_by_operation(required_sensors: list[str]) -> dict[str, str]:
    """Map every ground-truth operation to the single service that serves it."""
    mapping: dict[str, str] = {}
    for sensor in required_sensors:
        parts = str(sensor).split(":", 2)
        if len(parts) != 3 or parts[0] != "span" or not parts[1] or not parts[2]:
            raise WitnessError("required sensor is not span:<service>:<operation>")
        if mapping.setdefault(parts[2], parts[1]) != parts[1]:
            raise WitnessError("required sensors map one operation to two services")
    return mapping


def _fault_path_policy(
    path_truth: dict[str, Any], scenario: str,
) -> dict[str, Any]:
    """Compile the descriptor's during-fault structural allowances for a scenario.

    Nothing here is invented: the permitted-missing edges and the attempted
    prefix are read verbatim out of ``groundTruth.path.faultSpecific``, and the
    edges into the paused target are permitted-missing because a paused
    container provably cannot report its own spans.
    """
    truth = _fault_specific_truth(path_truth, scenario)
    normal = path_truth["normal"]
    target = truth["targetService"]
    normal_edges = {tuple(edge) for edge in normal["requiredServiceEdges"]}
    permitted_missing: set[tuple[str, str]] = {
        edge for edge in normal_edges if edge[1] == target
    }
    for entry in truth["downstreamNotRequiredDuringFault"]:
        parts = str(entry).split("->")
        if len(parts) != 2 or (parts[0], parts[1]) not in normal_edges:
            raise WitnessError("downstream-not-required entry is not a normal path edge")
        permitted_missing.add((parts[0], parts[1]))
    if not permitted_missing:
        raise WitnessError("fault-specific ground truth permits no truncation at all")
    return {
        "truth": truth,
        "targetService": target,
        "normalEdges": normal_edges,
        "permittedMissingEdges": permitted_missing,
        # A paused target cannot flush its own spans, so its own children and the
        # children of the services it fans out to may lose their parent span.
        "unreportedParents": frozenset(
            {target} | {edge[1] for edge in normal_edges if edge[0] == target}
        ),
        "attemptedPrefix": frozenset(truth["requiredAttemptedPrefix"]),
        "serviceByOperation": _service_by_operation(normal["requiredSensors"]),
    }


def _validate_during_native_trace(
    trace_id: str, events: list[dict[str, Any]], policy: dict[str, Any],
) -> dict[str, Any]:
    """Require the preregistered attempted prefix and only preregistered truncation.

    The normal-path service edges are NOT the ground truth for a during-fault
    trace: the descriptor preregisters, per scenario, that the paused target's
    own spans and the edges it lists as downstream-not-required may be absent
    (``groundTruth.path.faultSpecific``).  What stays hard is that the attempt
    still reached every service of the preregistered prefix, and that no edge
    outside the preregistered set is ever missing -- so a fault cannot be used
    to excuse losing evidence that the fault does not explain.
    """
    tree = _native_tree(events, unreported_parents=policy["unreportedParents"])
    attempted = set(tree["attemptedServices"])
    for event in events:
        served_by = policy["serviceByOperation"].get(str(event.get("operation")))
        if served_by is not None:
            attempted.add(served_by)
    if not policy["attemptedPrefix"].issubset(attempted):
        raise TraceDefect("during-fault native trace lacks the required attempted prefix",
                          "attempted-prefix-missing", absence=True)
    missing = policy["normalEdges"] - tree["observedEdges"]
    if not missing.issubset(policy["permittedMissingEdges"]):
        raise TraceDefect("during-fault native trace lost an edge the fault does not explain",
                          "unexplained-edge-missing", absence=True)
    return {
        "missingEdges": sorted("->".join(edge) for edge in missing),
        "danglingParentServices": tree["danglingParentServices"],
        "spanCount": len(events),
    }


def _adapter_route_probes(
    untagged: set[str],
    events_by_trace: dict[str, list[dict[str, Any]]],
    plan: dict[str, Any],
    fault_receipt: Any,
    scenario: str | None,
) -> list[str]:
    """Account for every untagged native trace as a fault-adapter route probe.

    The Compose pause adapter proves the outage end to end by fetching the
    frontend search route itself (``faults/compose_pause.py`` ``route_available``
    / ``wait_recovered``).  Those fetches carry no opportunity-token header, so
    the patched frontend leaves them untagged and they arrive as extra native
    traces.  They are admissible only on a fault cell, only on the adapter's own
    probe route, and only inside the window the fault receipt itself brackets --
    from the admitted schedule instant to the adapter's recorded end.  Any other
    untagged trace is unexplained traffic against the measured system and keeps
    blocking with the original message.
    """
    unexplained = WitnessError(
        "one native trace/root maps to zero or multiple opportunity tokens"
    )
    if not untagged:
        return []
    if scenario is None or not isinstance(fault_receipt, dict):
        raise unexplained
    try:
        barrier_wall = workload.parse_iso(plan["barrierAt"], "plan barrierAt").timestamp()
    except workload.LedgerError as exc:
        raise WitnessError(str(exc)) from exc
    barrier_monotonic = plan["barrierMonotonic"]
    ended_monotonic = fault_receipt["endedMonotonic"]
    scheduled = fault_receipt["scheduledAtSeconds"]
    if not all(
        _number(value, minimum=0)
        for value in (barrier_monotonic, ended_monotonic, scheduled)
    ) or float(ended_monotonic) < float(barrier_monotonic):
        raise WitnessError("fault adapter probe window is not bracketed by the receipt")
    # The adapter cannot touch the route before the admitted schedule instant and
    # cannot touch it after the end it recorded; both bounds come from evidence.
    window_start = barrier_wall + float(scheduled)
    window_end = barrier_wall + (float(ended_monotonic) - float(barrier_monotonic))
    probe_path = workload.search_url("", 0)
    probes: list[str] = []
    for trace_id in sorted(untagged):
        events = events_by_trace[trace_id]
        roots = [event for event in events if event.get("parentSpanId") is None]
        if len(roots) != 1:
            raise unexplained
        root = roots[0]
        tags = root.get("tags")
        started = root.get("startTimeUs")
        if (
            root.get("service") != "frontend"
            or tags.get("span.kind") != "server"
            or tags.get("http.url") != probe_path
            or not _number(started, minimum=0)
            or not window_start <= float(started) / 1_000_000.0 <= window_end
        ):
            raise unexplained
        probes.append(trace_id)
    return probes


def correlate(
    plan: dict[str, Any],
    ledger: list[dict[str, Any]],
    application_log: str,
    normalized: dict[str, Any],
    *, posture: str,
    scenario: str | None,
    fault_receipt: dict[str, Any] | None,
    raw: dict[str, Any],
    capture_terminal: dict[str, Any],
    unsupported_postures: list[dict[str, Any]],
    timing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workload.validate_plan(plan)
    if posture not in SUPPORTED_POSTURES:
        raise WitnessError("posture is not supported by the Hotel candidate")
    if any(row.get("id") == posture for row in unsupported_postures):
        raise WitnessError("posture is declared unsupported by the bound ceiling")
    if len(ledger) != plan["offered"]:
        raise WitnessError("ledger denominator differs from opportunity plan")
    witnesses = parse_application_witnesses(application_log)
    if not witnesses:
        raise WitnessError("cell has no independently witnessed application request")
    witness_by_token = {row["opaqueToken"]: row for row in witnesses}
    ledger_tokens = {row.get("opaqueToken") for row in ledger}
    if not set(witness_by_token).issubset(ledger_tokens):
        raise WitnessError("application witness contains a token outside the opportunity ledger")
    fault = validate_fault_receipt(
        fault_receipt, scenario, barrier_monotonic=plan["barrierMonotonic"], timing=timing,
    )
    empty = empty_capture_proof(posture, raw, normalized, capture_terminal)

    events = normalized.get("events")
    if (
        normalized.get("schemaVersion") != 1
        or normalized.get("normalizer") != "hotel-reservation-jaeger-v1"
        or not isinstance(events, list)
        or normalized.get("queryLimitReached") is not False
    ):
        raise WitnessError("normalized Jaeger capture is incomplete")
    trace_tokens: dict[str, set[str]] = defaultdict(set)
    tokens_by_trace: dict[str, set[str]] = defaultdict(set)
    events_by_trace: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        trace_id = event.get("traceId")
        if TRACE_ID.fullmatch(str(trace_id)) is None:
            raise WitnessError("normalized event lacks an original Jaeger trace ID")
        events_by_trace[trace_id].append(event)
        tags = event.get("tags")
        if not isinstance(tags, dict):
            raise WitnessError("normalized event tags are malformed")
        token = tags.get("obsplacement.opaque_token")
        if token is not None:
            if (
                TOKEN.fullmatch(str(token)) is None
                or event.get("service") != "frontend"
                or event.get("parentSpanId") is not None
            ):
                raise WitnessError("correlation tag is not on one original frontend root span")
            trace_tokens[str(token)].add(trace_id)
            tokens_by_trace[trace_id].add(str(token))

    descriptor = strict_json(
        (ROOT / "pipelines/campaigns/hotel-reservation-selected-v1.json").read_text(),
        "candidate descriptor",
    )
    path_truth = descriptor["groundTruth"]["path"]["normal"]
    # Degradations are not an absence: during-fault traces keep the normal path
    # ground truth, and no truncation is excused.  Decision 25 (parameterised
    # epochs) does not excuse one either: a trace failing it inside the fault+drain
    # window is counted and reported as fault effect instead of stopping the cell.
    fault_policy = (
        None if scenario is None or scenario not in PAUSE_TARGETS
        else _fault_path_policy(descriptor["groundTruth"]["path"], scenario)
    )
    route_probes: list[str] = []
    traced_posture = posture == "full" or posture in PARTIAL_TRACE_SERVICES
    # Decision 25 binds parameterised epochs only: `timing=None` (the frozen epoch) keeps every trace defect fatal.
    completeness = traced_posture and timing is not None
    if traced_posture:
        witnessed_tokens = set(witness_by_token)
        # Under decision 25 a witnessed request with no trace at all is an incomplete trace, counted per window
        # below; a trace carrying a token nobody witnessed stays fatal in every epoch.
        if (set(trace_tokens) - witnessed_tokens) if completeness else (set(trace_tokens) != witnessed_tokens):
            raise WitnessError(f"{posture} posture lacks a bijective witnessed-token to native-trace mapping")
        if any(len(value) != 1 for value in trace_tokens.values()):
            raise WitnessError("one opportunity token maps to multiple native traces")
        if any(len(value) != 1 for value in tokens_by_trace.values()):
            raise WitnessError("one native trace/root maps to zero or multiple opportunity tokens")
        route_probes = _adapter_route_probes(
            set(events_by_trace) - set(tokens_by_trace),
            events_by_trace, plan, fault_receipt, scenario,
        )

    boundaries = fault["phaseBoundaries"]
    drain_window = None
    if completeness and boundaries is not None:
        # (i): from the receipt's start (stamped before the fault command) to readyAt + the cell's client timeout
        # + the rule's margin; the timeout is the plan's own value, so the drain follows the cell's timing.
        if not _number(timing.get("requestTimeoutSeconds"), minimum=0):
            raise WitnessError("cell timing lacks the client request timeout the drain window derives from")
        drain_window = (
            float(boundaries["faultStartedMonotonic"]),
            float(boundaries["postReadinessMonotonic"])
            + float(timing["requestTimeoutSeconds"]) + TRACE_DRAIN_MARGIN_SECONDS,
        )
    window_names = ["measurement"] if drain_window is None else ["pre", FAULT_DRAIN_WINDOW, "post-drain"]
    windows = {name: {"requests": 0, "successful": 0, "incomplete": []} for name in window_names}
    rows = []
    phase_counts = defaultdict(int)
    truncation: dict[str, dict[str, Any]] = {}
    for opportunity in ledger:
        token = opportunity["opaqueToken"]
        witness = witness_by_token.get(token)
        if boundaries is None:
            phase = "measurement"
        elif opportunity["actualStartMonotonic"] < boundaries["faultStartedMonotonic"]:
            phase = "pre"
        elif opportunity["actualStartMonotonic"] < boundaries.get(
            "duringSettleEndMonotonic", boundaries["postReadinessMonotonic"]
        ):
            phase = "during"
        else:
            phase = "post-readiness"
        if drain_window is None:
            window = "measurement"
        elif opportunity["actualStartMonotonic"] < drain_window[0]:
            window = "pre"
        elif opportunity["actualStartMonotonic"] < drain_window[1]:
            window = FAULT_DRAIN_WINDOW
        else:
            window = "post-drain"
        windows[window]["requests"] += 1
        # Successful as in the terminal's protocol cell (candidate_terminal._ledger_status "ok").
        if opportunity.get("outcome") == "completed" and opportunity.get("statusCode") == 200:
            windows[window]["successful"] += 1
        if witness is not None:
            phase_counts[phase] += 1
        traces = sorted(trace_tokens.get(token, set()))
        incomplete = None
        if witness is None:
            state, value, reason, trace_id = "unsupported", None, "application-witness-missing", None
        elif posture in EMPTY_CAPTURE_POSTURES:
            if traces:
                raise WitnessError(f"{posture} token unexpectedly correlates to a trace")
            state, value, reason, trace_id = "supported", False, "terminal-complete-empty-capture", None
        elif len(traces) != 1:
            state, value, reason, trace_id = "unsupported", None, "one-to-one-original-trace-missing", None
            if completeness:
                incomplete = "trace-missing"
        else:
            state, trace_id = "supported", traces[0]
            trace_events = events_by_trace[trace_id]
            try:
                if posture in PARTIAL_TRACE_SERVICES:
                    _validate_partial_trace(trace_id, trace_events, PARTIAL_TRACE_SERVICES[posture])
                elif phase == "during" and fault_policy is not None:
                    # The descriptor preregisters a different structural ground truth
                    # while the target is paused; applying the normal-path one here
                    # rejects the fault's own signature as if it were evidence loss.
                    truncation[trace_id] = _validate_during_native_trace(
                        trace_id, trace_events, fault_policy,
                    )
                else:
                    _validate_native_trace(trace_id, trace_events, path_truth["requiredServiceEdges"])
            except TraceDefect as defect:
                # Decision 25: nothing blocks per trace inside window (i); outside it an incomplete trace counts
                # against the allowance below, and a malformed one (not an absence) stays fatal as before.
                if not completeness or (window != FAULT_DRAIN_WINDOW and not defect.absence):
                    raise
                incomplete = defect.code
            if incomplete is not None:
                state, value, reason = "unsupported", None, "native-trace-incomplete"
            else:
                sensors = {f"span:{event.get('service')}:{event.get('operation')}" for event in trace_events}
                required = set(path_truth["requiredSensors"])
                paused_during = phase == "during" and fault_policy is not None
                value = required.issubset(sensors) if not paused_during else None
                reason = (
                    "one-original-native-trace-normal-path"
                    if not paused_during
                    else "fault-specific-native-operation-ground-truth-unqualified"
                )
                if paused_during:
                    state = "unsupported"
        if incomplete is not None:
            windows[window]["incomplete"].append(
                {"opaqueToken": token, "originalJaegerTraceId": trace_id, "reason": incomplete}
            )
        rows.append({
            "opportunityId": opportunity["opportunityId"],
            "opaqueToken": token,
            "phase": phase,
            "applicationWitness": witness is not None,
            "state": state,
            "reconstructed": value,
            "originalJaegerTraceId": trace_id,
            "reason": reason,
        })
    if timing is None:
        if scenario is not None and any(
            phase_counts[name] < FROZEN_MINIMUM_PHASE_STARTS for name in ("pre", "during", "post-readiness")
        ):
            raise WitnessError("effect cell lacks 100 independently witnessed starts in every observed phase")
    elif scenario is not None:
        floors = timing.get("minimumWitnessedStartsByPhase")
        if not isinstance(floors, dict) or set(floors) != {"pre", "during", "post-readiness"}:
            raise WitnessError("cell timing lacks its per-phase witnessed-start floors")
        short = sorted(name for name, floor in floors.items() if phase_counts[name] < floor)
        if short:
            raise WitnessError(
                "effect cell lacks its plan-derived witnessed starts in phase(s) %s: observed %s, floors %s"
                % (", ".join(short), dict(sorted(phase_counts.items())), dict(sorted(floors.items())))
            )
    completeness_record = None
    if completeness:
        # (ii): the windows outside (i), pooled; integer arithmetic, so 3.9 and 3.13 agree on every boundary.
        scope = [name for name in window_names if name != FAULT_DRAIN_WINDOW]
        successful = sum(windows[name]["successful"] for name in scope)
        observed = sum(len(windows[name]["incomplete"]) for name in scope)
        allowance = max(TRACE_INCOMPLETE_MINIMUM, successful * TRACE_INCOMPLETE_PERCENT // 100)
        report = {}
        for name in window_names:
            entries = sorted(windows[name]["incomplete"], key=lambda entry: entry["opaqueToken"])
            reasons: dict[str, int] = {}
            for entry in entries:
                reasons[entry["reason"]] = reasons.get(entry["reason"], 0) + 1
            report[name] = {
                "requests": windows[name]["requests"],
                "successful": windows[name]["successful"],
                "incomplete": len(entries),
                "incompleteByReason": dict(sorted(reasons.items())),
                "incompleteTraces": entries,
            }
        if observed > allowance:
            raise WitnessError(
                "%d incomplete native trace(s) outside the fault+drain window exceed max(%d, %d %% of %d successful "
                "requests) = %d (decision 25): %s"
                % (observed, TRACE_INCOMPLETE_MINIMUM, TRACE_INCOMPLETE_PERCENT, successful, allowance,
                   {name: report[name]["incompleteByReason"] for name in scope})
            )
        completeness_record = {
            "rule": TRACE_COMPLETENESS_RULE,
            "faultDrainWindowMonotonic": None if drain_window is None else list(drain_window),
            "drainAfterReadySeconds": (
                None if drain_window is None
                else float(timing["requestTimeoutSeconds"]) + TRACE_DRAIN_MARGIN_SECONDS
            ),
            "windows": report,
            "allowance": {
                "windows": scope,
                "successful": successful,
                "incomplete": observed,
                "maximum": allowance,
                "rule": "block-if-incomplete-exceeds-max(%d, floor(%d %% x successful))"
                % (TRACE_INCOMPLETE_MINIMUM, TRACE_INCOMPLETE_PERCENT),
            },
        }
    body = {
        "schemaVersion": 1,
        "kind": "hotel-candidate-request-trace-correlation-v1",
        "posture": posture,
        "scenario": scenario,
        "offered": len(ledger),
        "executedWitnesses": len(witnesses),
        "phaseExecutedCounts": dict(sorted(phase_counts.items())),
        "faultTruth": fault,
        "emptyCaptureProof": empty,
        "rows": rows,
        "sourceCostComparison": {
            "state": "unsupported", "numericValue": None,
            "reason": "no-posture-is-source-off",
        },
        # The ceiling is versioned policy, passed in by the caller: the cell
        # runner supplies the current ceiling, the terminal replay supplies the
        # ceiling bound to the cell's compiled-plan digest.
        "unsupportedPostures": [
            {"id": row["id"], "state": row["state"], "numericValue": row["numericValue"]}
            for row in unsupported_postures
        ],
    }
    if fault_policy is not None:
        # Reported, never hidden: exactly which during-fault traces were
        # truncated, which edges they lost, and which extra native traces were
        # accounted for as the adapter's own route probes.  Cost cells carry no
        # such block at all, so their correlation document is unchanged.
        missing_edge_counts: dict[str, int] = {}
        for entry in truncation.values():
            for edge in entry["missingEdges"]:
                missing_edge_counts[edge] = missing_edge_counts.get(edge, 0) + 1
        body["faultPathTruth"] = {
            "groundTruthId": fault_policy["truth"]["id"],
            "targetService": fault_policy["targetService"],
            "requiredAttemptedPrefix": list(fault_policy["truth"]["requiredAttemptedPrefix"]),
            "permittedMissingEdges": sorted(
                "->".join(edge) for edge in fault_policy["permittedMissingEdges"]
            ),
            "duringTracesValidated": len(truncation),
            "duringTracesTruncated": sum(
                1 for entry in truncation.values() if entry["missingEdges"]
            ),
            "duringTracesWithUnreportedParent": sum(
                1 for entry in truncation.values() if entry["danglingParentServices"]
            ),
            "missingEdgeCounts": dict(sorted(missing_edge_counts.items())),
            "adapterRouteProbeTraces": sorted(route_probes),
        }
    if completeness_record is not None:
        # (iii) Parameterised epochs only: counted per window even when every count is zero (absence is not zero).
        body["traceCompleteness"] = completeness_record
    return {**body, "canonicalSha256": canonical_sha256(body)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--application-log", required=True, type=Path)
    parser.add_argument("--normalized", required=True, type=Path)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--capture-terminal", required=True, type=Path)
    parser.add_argument("--posture", choices=SUPPORTED_POSTURES, required=True)
    parser.add_argument("--scenario", choices=tuple(PAUSE_TARGETS) + tuple(OFFPATH_PAUSE_TARGETS) + tuple(DEGRADATION_TARGETS))
    parser.add_argument("--fault-receipt", type=Path)
    parser.add_argument("--cell-contract", type=Path,
                        help="a parameterised-epoch cell contract; its `timing` replaces the frozen 45/15/100 rules")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = correlate(
            workload.strict_json(args.plan.read_text(), str(args.plan)),
            ledger_rows(args.ledger), args.application_log.read_text(encoding="utf-8", errors="replace"),
            strict_json(args.normalized.read_text(), str(args.normalized)),
            posture=args.posture, scenario=args.scenario,
            fault_receipt=(strict_json(args.fault_receipt.read_text(), str(args.fault_receipt)) if args.fault_receipt else None),
            raw=strict_json(args.raw.read_text(), str(args.raw)),
            capture_terminal=strict_json(args.capture_terminal.read_text(), str(args.capture_terminal)),
            # Standalone invocation writes under the *current* declared ceiling;
            # the terminal replay passes the ceiling bound to the cell's plan digest.
            unsupported_postures=_load(
                "hotel_candidate_witness_runtime_policy", MODULE / "execution" / "candidate_runtime.py",
            ).posture_ceiling()["unsupportedPostures"],
            timing=(
                strict_json(args.cell_contract.read_text(), str(args.cell_contract)).get("timing")
                if args.cell_contract else None
            ),
        )
    except WitnessError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in ("offered", "executedWitnesses", "canonicalSha256")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
