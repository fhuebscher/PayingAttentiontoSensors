#!/usr/bin/env python3
"""Validate required TeaStore sensor/path retention against explicit fault ground truth."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path


DEFAULT_GOAL = Path("modules/teastore/goals/fault-qualification.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _edges(events: list[dict]) -> dict[tuple[str, str], int]:
    by_span = {event.get("span_id"): event for event in events if event.get("span_id")}
    result: dict[tuple[str, str], int] = {}
    for event in events:
        parent = by_span.get(event.get("parent_span_id"))
        edge = (parent.get("service"), event.get("service")) if parent else None
        if edge and edge[0] and edge[1] and edge[0] != edge[1]:
            result[edge] = result.get(edge, 0) + 1
    return result


def _inside_window(receipt: dict, intervention: dict) -> bool:
    try:
        window_start = datetime.fromisoformat(receipt["window"]["startedAt"])
        window_end = datetime.fromisoformat(receipt["window"]["endedAt"])
        fault_start = datetime.fromisoformat(intervention["startedAt"])
        fault_end = datetime.fromisoformat(intervention["endedAt"])
    except (KeyError, TypeError, ValueError):
        return False
    return window_start <= fault_start < fault_end <= window_end


def _phases(events: list[dict], intervention: dict) -> dict[str, list[dict]]:
    start = datetime.fromisoformat(intervention["startedAt"]).timestamp()
    end = datetime.fromisoformat(intervention["endedAt"]).timestamp()
    return {
        "before": [event for event in events if event.get("timestamp", 0) < start],
        "during": [event for event in events if start <= event.get("timestamp", 0) <= end],
        "after": [event for event in events if event.get("timestamp", 0) > end],
    }


def validate(root: Path, scenario: str, blocks: int, goal_path: Path = DEFAULT_GOAL) -> dict:
    goal = json.loads(goal_path.read_text())
    if scenario not in goal["scenarios"]:
        raise ValueError(f"scenario {scenario!r} absent from goal {goal['id']}")
    ground_truth = goal["scenarios"][scenario]
    required_services = {sensor.split(":", 1)[1] for sensor in ground_truth["requiredSensors"]
                         if sensor.startswith("operation:")}
    required_edges = {tuple(edge) for edge in ground_truth["requiredServiceEdges"]}
    failures: list[str] = []
    counts = {"selected": 0, "full": 0}
    reactions = {"selected": 0, "full": 0}
    retained = {"selected": [], "full": []}
    for receipt_path in sorted(root.glob("*/receipt.json")):
        receipt = json.loads(receipt_path.read_text())
        posture = receipt.get("posture")
        run_id = receipt.get("runId", receipt_path.parent.name)
        if posture not in counts:
            failures.append(f"{run_id}: unexpected posture {posture}")
            continue
        counts[posture] += 1
        intervention = receipt.get("intervention") or {}
        source = receipt.get("source", {})
        if source.get("selectionId") != "fault-qualification" or source.get("selectionSourceSha256") != _sha256(goal_path):
            failures.append(f"{run_id}: receipt is not bound to the fault qualification goal")
        if intervention.get("scenario") != scenario or not intervention.get("successful"):
            failures.append(f"{run_id}: manifested and recovered intervention not proven")
        if not _inside_window(receipt, intervention):
            failures.append(f"{run_id}: intervention not contained by measurement window")
        trace_path = receipt_path.parent / "traces.json"
        events = json.loads(trace_path.read_text()) if trace_path.exists() else []
        phases = _phases(events, intervention) if intervention.get("startedAt") and intervention.get("endedAt") else {
            "before": [], "during": [], "after": []}
        phase_evidence = {}
        for phase, phase_events in phases.items():
            services = {event.get("service") for event in phase_events}
            observed_edges = _edges(phase_events)
            phase_evidence[phase] = {
                "records": len(phase_events),
                "requiredServiceCounts": {service: sum(event.get("service") == service for event in phase_events)
                                          for service in sorted(required_services)},
                "requiredEdgeCounts": {"->".join(edge): observed_edges.get(edge, 0)
                                       for edge in sorted(required_edges)},
            }
            if phase in {"before", "after"}:
                missing_services = sorted(required_services - services)
                missing_edges = sorted(required_edges - set(observed_edges))
                if missing_services:
                    failures.append(f"{run_id}: {phase}-fault logical sensors absent for services {missing_services}")
                if missing_edges:
                    failures.append(f"{run_id}: {phase}-fault service edges absent {missing_edges}")
        unhashed = sum(not event.get("message_sha1") or not event.get("signature_sha1") for event in events)
        if unhashed:
            failures.append(f"{run_id}: {unhashed} trace records lack replay/signature hashes")
        if receipt.get("canonicality", {}).get("blockers"):
            failures.append(f"{run_id}: receipt blockers {receipt['canonicality']['blockers']}")
        if receipt.get("workload", {}).get("failed", 0) > 0:
            reactions[posture] += 1
        retained[posture].append({"runId": run_id, "phases": phase_evidence})
    expected = {"selected": blocks, "full": blocks}
    if counts != expected:
        failures.append(f"posture counts {counts}, expected {expected}")
    return {
        "schemaVersion": 1, "goalId": goal["id"], "goalSha256": _sha256(goal_path),
        "scenario": scenario, "groundTruth": ground_truth, "counts": counts,
        "retainedEvidence": retained, "runsWithWorkloadFailures": reactions,
        "verdict": "pass" if not failures else "blocked", "failures": failures,
        "claimBoundary": goal["claimBoundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--blocks", type=int, default=3)
    parser.add_argument("--goal", type=Path, default=DEFAULT_GOAL)
    args = parser.parse_args()
    report = validate(args.campaign, args.scenario, args.blocks, args.goal)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["verdict"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
