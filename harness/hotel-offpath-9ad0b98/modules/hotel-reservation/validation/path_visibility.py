#!/usr/bin/env python3
"""Validate required Hotel Reservation path retention against explicit ground truth."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


DEFAULT_GOAL = Path(__file__).resolve().parents[1] / "goals" / "search-path.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sensor(event: dict) -> str:
    return f"span:{event.get('service')}:{event.get('operation')}"


def validate(normalized: dict, goal: dict, intervention: dict | None = None) -> dict:
    failures: list[str] = []
    if normalized.get("schemaVersion") != 1 or normalized.get("normalizer") != "hotel-reservation-jaeger-v1":
        failures.append("unsupported or missing normalized evidence contract")
    scenario = goal.get("scenario", {})
    required_sensors = set(scenario.get("requiredSensors", []))
    required_edges = {tuple(edge) for edge in scenario.get("requiredServiceEdges", [])}
    if not required_sensors or not required_edges:
        failures.append("ground truth has no required sensors or service edges")

    by_trace: dict[str, list[dict]] = defaultdict(list)
    seen_ids: set[tuple[str, str]] = set()
    for event in normalized.get("events", []):
        identity = (event.get("traceId"), event.get("spanId"))
        if not all(identity) or identity in seen_ids:
            failures.append(f"missing or duplicate native span identity: {identity}")
        seen_ids.add(identity)
        by_trace[str(event.get("traceId"))].append(event)

    aggregate_sensors = {sensor(event) for events in by_trace.values() for event in events}
    aggregate_edges = {(event.get("parentService"), event.get("service"))
                       for events in by_trace.values() for event in events
                       if event.get("parentService") and event.get("parentService") != event.get("service")}
    complete_traces = []
    trace_evidence = []
    for trace_id, events in sorted(by_trace.items()):
        sensors = {sensor(event) for event in events}
        edges = {(event.get("parentService"), event.get("service")) for event in events
                 if event.get("parentService") and event.get("parentService") != event.get("service")}
        missing_sensors = sorted(required_sensors - sensors)
        missing_edges = sorted(required_edges - edges)
        trace_evidence.append({"traceId": trace_id, "spanCount": len(events),
                               "missingSensors": missing_sensors,
                               "missingServiceEdges": [list(edge) for edge in missing_edges]})
        if not missing_sensors and not missing_edges:
            complete_traces.append(trace_id)
    if not complete_traces:
        failures.append("no individual trace retains the complete required path")
    missing_sensors = sorted(required_sensors - aggregate_sensors)
    missing_edges = sorted(required_edges - aggregate_edges)
    if missing_sensors:
        failures.append(f"required sensors absent: {missing_sensors}")
    if missing_edges:
        failures.append(f"required service edges absent: {missing_edges}")
    if normalized.get("uniqueTraceCount", 0) <= 0 or normalized.get("spanCount", 0) <= 0:
        failures.append("trace evidence is empty")
    if normalized.get("queryLimitReached"):
        failures.append("at least one Jaeger query reached its limit; evidence may be truncated")

    if intervention is not None:
        expected = {item["id"]: item for item in scenario.get("representativeFaults", [])}
        fault_id = intervention.get("scenario")
        if fault_id not in expected:
            failures.append(f"intervention {fault_id!r} is not explicit ground truth")
        if not intervention.get("manifested") or not intervention.get("recovered") or not intervention.get("successful"):
            failures.append("fault manifestation and recovery are not proven")

    return {
        "schemaVersion": 1, "goalId": goal.get("id"),
        "requiredSensorRetention": ((len(required_sensors) - len(missing_sensors)) / len(required_sensors)
                                     if required_sensors else 0.0),
        "requiredEdgeRetention": ((len(required_edges) - len(missing_edges)) / len(required_edges)
                                   if required_edges else 0.0),
        "completePathTraceCount": len(complete_traces),
        "uniqueTraceCount": normalized.get("uniqueTraceCount", 0),
        "spanCount": normalized.get("spanCount", 0),
        "uniqueSpanSignatureCount": normalized.get("uniqueSpanSignatureCount", 0),
        "topSignatureConcentration": normalized.get("topSignatureConcentration"),
        "traceEvidence": trace_evidence,
        "verdict": "pass" if not failures else "blocked", "failures": failures,
        "claimBoundary": goal.get("claimBoundary"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("normalized", type=Path)
    parser.add_argument("--goal", type=Path, default=DEFAULT_GOAL)
    parser.add_argument("--intervention", type=Path)
    args = parser.parse_args()
    result = validate(json.loads(args.normalized.read_text()), json.loads(args.goal.read_text()),
                      json.loads(args.intervention.read_text()) if args.intervention else None)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
