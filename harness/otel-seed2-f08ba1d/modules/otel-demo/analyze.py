#!/usr/bin/env python3
"""Analyze paired OTel source-off/full receipts and collector export summaries."""
from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path


def trace_stats(path: Path) -> dict:
    spans = [int(value) for value in re.findall(r'TracesExporter.*?"spans":\s*(\d+)', path.read_text())]
    return {"batches": len(spans), "spans": sum(spans)}


def analyze(root: Path) -> dict:
    runs = {}
    for path in sorted(root.glob("b*/receipt.json")):
        receipt = json.loads(path.read_text())
        receipt["telemetryRecomputed"] = trace_stats(path.with_name("otelcol.log"))
        runs[receipt["runId"]] = receipt
    blocks = []
    for number in sorted({run_id.split("-")[0] for run_id in runs}):
        full, off = runs[f"{number}-full"], runs[f"{number}-source-off"]
        blocks.append({"block": int(number[1:]),
                       "fullMinusSourceOffP50Ms": round(full["latencyMs"]["p50"] - off["latencyMs"]["p50"], 3),
                       "fullMinusSourceOffP95Ms": round(full["latencyMs"]["p95"] - off["latencyMs"]["p95"], 3),
                       "fullMinusSourceOffFrontendMeanCpuPercent": round(
                           full["resources"]["frontend"]["meanCpuPercent"] -
                           off["resources"]["frontend"]["meanCpuPercent"], 4),
                       "fullExportedSpans": full["telemetryRecomputed"]["spans"],
                       "sourceOffExportedSpans": off["telemetryRecomputed"]["spans"],
                       "fullRequests": full["workload"], "sourceOffRequests": off["workload"],
                       "faultRecoveryProven": bool(full["intervention"]["successful"] and
                                                   off["intervention"]["successful"])})
    keys = ("fullMinusSourceOffP50Ms", "fullMinusSourceOffP95Ms",
            "fullMinusSourceOffFrontendMeanCpuPercent")
    return {"schema": 1, "sut": "otel-demo", "goal": "otel-path-cost",
            "verdict": "noncanonical-control-smoke",
            "qualification": ("SDK-and-proxy-disabled target-path control only; "
                              "request-path source-work removal is not proven"),
            "blocks": blocks,
            "meanDeltas": {key: round(statistics.mean(block[key] for block in blocks), 4) for key in keys},
            "allFaultRecoveriesProven": all(block["faultRecoveryProven"] for block in blocks),
            "limitations": ["three paired blocks on one host", "source-off is a legacy posture identifier",
                            "frontend no-op API calls and recommendation auto-instrument launch remain",
                            "non-target demo services remain instrumented",
                            "CPU is the mean of repeated docker-stats samples, not cumulative CPU time",
                            "collector export totals include startup and warm-up telemetry",
                            "the load generator injects a forged W3C traceparent into every request; "
                            "this becomes the root of the SUT's own native trace whenever any hop's "
                            "SDK is active (full) and has no native-telemetry footprint at all when "
                            "disabled (source-off), so full-posture traces are not unperturbed"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(analyze(args.root), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(result)
    else:
        print(result, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
