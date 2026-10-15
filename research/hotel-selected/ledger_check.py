#!/usr/bin/env python3
"""POST HOC (after the Fable review of sel1, 2026-09-29): does the workload's own request ledger, with no tracer, show each
fault class? Per effect cell: requests started inside the fault window (receipt appliedMonotonic..revertingMonotonic, same
host monotonic clock as the ledger) vs before it; a cell "shows" the fault if any in-window request failed or the in-window
median latency exceeds the pre-window median by max(3 x pre-window MAD, 1 ms). Reported per regime x posture.

    /usr/bin/python3 -B research/hotel-selected/ledger_check.py <campaign x/ dir>
"""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def cell(attempt: Path) -> dict:
    receipt = json.loads((attempt / "fault-receipt.json").read_text())
    a, b = receipt["appliedMonotonic"], receipt["revertingMonotonic"]
    pre, inside = [], []
    for line in (attempt / "opportunity-ledger.jsonl").open():
        row = json.loads(line)
        start = row["actualStartMonotonic"]
        ms = (row["actualEndMonotonic"] - start) * 1000.0
        ok = row["outcome"] == "completed" and row.get("statusCode") == 200
        if start < a:
            pre.append((ms, ok))
        elif start <= b:
            inside.append((ms, ok))
    pre_ms = [m for m, ok in pre if ok]
    med = statistics.median(pre_ms)
    mad = statistics.median(abs(m - med) for m in pre_ms)
    in_med = statistics.median(m for m, _ in inside)
    failed = sum(1 for _, ok in inside if not ok)
    return {"inWindow": len(inside), "failedInWindow": failed, "preMedianMs": med, "inMedianMs": in_med,
            "shows": failed > 0 or in_med > med + max(3 * mad, 1.0)}


def main(x: Path) -> dict:
    out = defaultdict(lambda: {"cells": 0, "shows": 0, "failedInWindow": [], "inMedianMs": []})
    attempts = sorted((x / "runs" / "effect").glob("*/b*/p*-*/attempt-01"))
    if not attempts:
        sys.exit("no effect cells under %s" % x)
    for attempt in attempts:
        regime, posture = attempt.parts[-4], attempt.parts[-2].split("-", 1)[1]
        c = cell(attempt)
        row = out["%s/%s" % (regime, posture)]
        row["cells"] += 1
        row["shows"] += c["shows"]
        row["failedInWindow"].append(c["failedInWindow"])
        row["inMedianMs"].append(round(c["inMedianMs"], 1))
    return dict(sorted(out.items()))


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1])), indent=1))
