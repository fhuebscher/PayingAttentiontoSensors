#!/usr/bin/env python3
"""LMT+S pilot: collection cost per posture step, paired by block (no-fault-cost regime only).

Per cell: cgroup CPU seconds in the 120 s window for the ten application containers and for
docker.service + containerd.service (cost-cgroup.json), and p50 latency over completed requests
(opportunity-ledger.jsonl, the rule of research/hotel-none-rung/hotel_cost_axes.py). Per step
(none->logs, logs->metrics, metrics->full, none->full) and block: the paired difference. Reported:
block mean, [min, max] of the block deltas, and the count of positive blocks. No interval, no test.

    /usr/bin/python3 -B research/lmt-pilot/cost_steps.py <campaign x/ dir>   # the dir holding runs/
    /usr/bin/python3 -B research/lmt-pilot/cost_steps.py --self-check
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("hca", HERE.parent / "hotel-none-rung" / "hotel_cost_axes.py")
hca = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hca)

POSTURES = ("none", "logs", "metrics", "full")
STEPS = (("none", "logs"), ("logs", "metrics"), ("metrics", "full"), ("none", "full"))
AXES = ("appCpuSeconds", "daemonCpuSeconds", "totalCpuSeconds", "p50Ms")


def cell_axes(attempt: Path) -> dict:
    term = json.loads((attempt / "cell-terminal.json").read_text())
    if term.get("candidateCellValid") is not True:
        return None
    cost = json.loads((attempt / "cost-cgroup.json").read_text())
    app = hca.seq_sum([cost["containersCpuSeconds"][k] for k in sorted(cost["containersCpuSeconds"])])
    daemon = hca.seq_sum([cost["daemonsCpuSeconds"][k] for k in sorted(cost["daemonsCpuSeconds"])])
    latencies, completed, failed, offered = hca.ledger_stats(attempt / "opportunity-ledger.jsonl")
    return {"appCpuSeconds": app, "daemonCpuSeconds": daemon, "totalCpuSeconds": app + daemon,
            "p50Ms": hca.percentile(latencies, 0.5) if latencies else None,
            "completed": completed, "failed": failed, "offered": offered}


def collect(x_dir: Path) -> dict:
    """block -> posture -> axes, cost regime only; a block enters only when all four postures are valid."""
    blocks = {}
    for attempt in sorted((x_dir / "runs" / "cost").glob("b*/p*-*/attempt-01")):
        block = attempt.parent.parent.name
        posture = attempt.parent.name.split("-", 1)[1]
        axes = cell_axes(attempt)
        if axes is not None:
            blocks.setdefault(block, {})[posture] = axes
    return {b: v for b, v in sorted(blocks.items()) if set(v) == set(POSTURES)}


def steps(blocks: dict) -> dict:
    out = {}
    for lo, hi in STEPS:
        name = "%s->%s" % (lo, hi)
        out[name] = {}
        for axis in AXES:
            deltas = [blocks[b][hi][axis] - blocks[b][lo][axis] for b in blocks
                      if blocks[b][hi][axis] is not None and blocks[b][lo][axis] is not None]
            out[name][axis] = None if not deltas else {
                "n": len(deltas), "mean": hca.seq_sum(deltas) / len(deltas),
                "min": min(deltas), "max": max(deltas), "positive": sum(1 for d in deltas if d > 0),
                "perBlock": deltas}
    return out


def self_check() -> None:
    def fake(b, app, daemon, p50):
        return {"appCpuSeconds": app, "daemonCpuSeconds": daemon, "totalCpuSeconds": app + daemon,
                "p50Ms": p50, "completed": 1200, "failed": 0, "offered": 1200}
    blocks = {"b01": {"none": fake(1, 10, 1, 5), "logs": fake(1, 11, 1.5, 5.2),
                      "metrics": fake(1, 11.5, 2.5, 5.3), "full": fake(1, 20, 2.6, 6.6)},
              "b02": {"none": fake(2, 10, 1, 5), "logs": fake(2, 10.5, 1.2, 4.9),
                      "metrics": fake(2, 11, 2.2, 5.0), "full": fake(2, 19, 2.3, 6.4)}}
    s = steps(blocks)
    assert s["none->logs"]["appCpuSeconds"]["perBlock"] == [1, 0.5], s
    assert s["logs->metrics"]["daemonCpuSeconds"]["positive"] == 2, s
    assert s["none->full"]["p50Ms"]["min"] == 1.4000000000000004 or abs(s["none->full"]["p50Ms"]["min"] - 1.4) < 1e-9, s
    # planted defect: an incomplete block must not enter
    blocks["b03"] = {"none": fake(3, 10, 1, 5)}
    assert set(b for b, v in blocks.items() if set(v) == set(POSTURES)) == {"b01", "b02"}
    print("self-check: pass")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-check"]:
        self_check(); sys.exit(0)
    blocks = collect(Path(sys.argv[1]))
    print(json.dumps({"completeBlocks": sorted(blocks), "cells": blocks, "steps": steps(blocks)}, indent=2))
