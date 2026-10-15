"""Run-level paired analysis for randomized instrumentation blocks."""
from __future__ import annotations

import json
import math
import random
import statistics
from datetime import datetime
from pathlib import Path


METRICS = {
    "latency_mean_ms": ("latencyMs", "mean"),
    "latency_p95_ms": ("latencyMs", "p95"),
    "application_cpu_seconds": ("resources", "applicationCpuSeconds"),
    "host_cpu_seconds": ("resources", "hostCpuSeconds"),
    "telemetry_records": ("telemetry", "records"),
    "telemetry_bytes": ("telemetry", "bytes"),
}


# Receipt schema drift, handled here rather than at every call site: telemetry
# volume moved from telemetry.{records,bytes} under telemetry.spool, and run
# identity moved from a flat "b01-selected" runId into a nested `run` object.
# Every accessor below reads either shape, so this tool works on current
# campaigns without invalidating older fetched evidence.
_TELEMETRY_FALLBACK = {
    "records": ("spool", "replayedEventCount"),
    "bytes": ("spool", "rawBodyBytes"),  # payload on the wire, not spoolBytes
}                                        # (which adds on-disk framing overhead)


def _value(receipt: dict, path: tuple[str, str]) -> float:
    section, key = path
    values = receipt[section]
    if key in values:
        return float(values[key])
    if section == "telemetry" and key in _TELEMETRY_FALLBACK:
        outer, inner = _TELEMETRY_FALLBACK[key]
        return float(values[outer][inner])
    raise KeyError(f"{section}.{key}")


def _run_id(receipt: dict) -> str:
    return receipt.get("runId") or receipt.get("run", {}).get("runId", "")


def _posture(receipt: dict) -> str | None:
    return receipt.get("posture") or receipt.get("run", {}).get("posture")


def _block(receipt: dict) -> str | None:
    """Block label from either schema: "b01-selected" or run.block == 1."""
    flat = receipt.get("runId", "")
    if "-" in flat:
        return flat.split("-", 1)[0]
    block = receipt.get("run", {}).get("block")
    return f"b{block:02d}" if isinstance(block, int) else None


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _bootstrap_mean_ci(values: list[float], seed: int, samples: int = 20_000) -> list[float]:
    rng = random.Random(seed)
    means = [sum(rng.choice(values) for _ in values) / len(values) for _ in range(samples)]
    return [_percentile(means, 0.025), _percentile(means, 0.975)]


# Two-sided 95% Student-t quantiles, df = 1..9. statistics has no t inverse and
# scipy is not a dependency, so the small-sample table is inlined.
_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
         6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}
MINIMUM_BOOTSTRAP_BLOCKS = 5


def _t_interval_95(values: list[float]) -> list[float] | None:
    """Student-t interval on the paired mean; None when df is outside the table."""
    n = len(values)
    if n < 2 or (n - 1) not in _T975:
        return None
    mean = sum(values) / n
    half = _T975[n - 1] * statistics.stdev(values) / math.sqrt(n)
    return [mean - half, mean + half]


def _slope(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    center = (len(values) - 1) / 2
    denominator = sum((index - center) ** 2 for index in range(len(values)))
    return sum((index - center) * value for index, value in enumerate(values)) / denominator


def _influence(values: list[float], labels: list[str]) -> dict:
    if len(values) < 3:
        return {"madOutlierBlocks": [], "materialOutlierBlocks": [], "leaveOneOutMeanRange": None}
    median = statistics.median(values)
    mad = statistics.median(abs(value - median) for value in values)
    outliers = ([label for label, value in zip(labels, values) if value != median]
                if mad == 0 else
                [label for label, value in zip(labels, values) if abs(value - median) > 3 * mad])
    scale = max(abs(median), statistics.median(abs(value) for value in values), 1e-12)
    material = [label for label, value in zip(labels, values)
                if label in outliers and abs(value - median) / scale >= 0.05]
    leave_one_out = [(sum(values) - value) / (len(values) - 1) for value in values]
    return {"median": median, "mad": mad, "madOutlierBlocks": outliers,
            "materialOutlierBlocks": material,
            "leaveOneOutMeanRange": [min(leave_one_out), max(leave_one_out)]}


def _started_at_text(receipt: dict) -> str | None:
    window = receipt.get("window", {})
    return window.get("startedAt") or window.get("measurementStartedAt")


def _started(receipt: dict) -> float | None:
    window = receipt.get("window", {})
    value = window.get("startedAt") or window.get("measurementStartedAt")
    if not value:
        return None
    return datetime.fromisoformat(value).timestamp()


def analyze(receipts: list[dict], *, seed: int = 20260803) -> dict:
    blocks: dict[str, dict[str, dict]] = {}
    failures: list[str] = []
    for receipt in receipts:
        run_id = _run_id(receipt)
        block = _block(receipt)
        posture = _posture(receipt)
        if block is None or posture is None:
            failures.append(f"unparseable run id: {run_id}")
            continue
        if posture in blocks.setdefault(block, {}):
            failures.append(f"duplicate posture {posture} in {block}")
        blocks[block][posture] = receipt
        if receipt.get("canonicality", {}).get("blockers"):
            failures.append(f"blocked receipt: {run_id}")
    sources = set()
    for receipt in receipts:
        telemetry = receipt.get("telemetry", {})
        sources.add("telemetry.bytes(traces.json size)" if "bytes" in telemetry
                    else "telemetry.spool.rawBodyBytes" if "spool" in telemetry else "absent")
    if len(sources) != 1:
        failures.append(f"mixed telemetry byte sources: {sorted(sources)}")
    expected = {"none", "selected", "full"}
    for block, values in blocks.items():
        if set(values) != expected:
            failures.append(f"incomplete block {block}: {sorted(values)}")
    comparisons = {}
    for left, right in (("selected", "none"), ("full", "none"), ("selected", "full")):
        label = f"{left}_minus_{right}"
        comparisons[label] = {}
        for offset, (metric, path) in enumerate(METRICS.items()):
            complete = [(block, values) for block, values in blocks.items() if set(values) == expected]
            labels = [block for block, _ in complete]
            differences = [_value(values[left], path) - _value(values[right], path)
                           for _, values in complete]
            comparisons[label][metric] = {
                "n": len(differences),
                "pairedDifferences": differences,
                "meanDifference": sum(differences) / len(differences) if differences else None,
                "pairedDifferenceRange": [min(differences), max(differences)] if differences else None,
                "tInterval95": _t_interval_95(differences),
                "bootstrapPercentileInterval95": (
                    _bootstrap_mean_ci(differences, seed + offset)
                    if len(differences) >= MINIMUM_BOOTSTRAP_BLOCKS else None
                ),
                "influence": _influence(differences, labels),
            }
    chronological = sorted(((_started(receipt), receipt) for receipt in receipts if _started(receipt) is not None),
                           key=lambda item: item[0])
    order = [{"position": index + 1, "runId": _run_id(receipt), "posture": _posture(receipt),
              "startedAt": _started_at_text(receipt)}
             for index, (_, receipt) in enumerate(chronological)]
    drift = {}
    for metric, path in METRICS.items():
        drift[metric] = {}
        for posture in sorted(expected):
            values = [_value(receipt, path) for _, receipt in chronological if _posture(receipt) == posture]
            slope = _slope(values)
            center = statistics.median(values) if values else 0
            drift[metric][posture] = {"valuesInExecutionOrder": values,
                                      "slopePerRun": slope,
                                      "relativeSlopePerRun": slope / center if slope is not None and center else None}
    diagnostics = {"executionOrder": order, "postureDrift": drift,
                   "warnings": []}
    if len(order) != len(receipts):
        diagnostics["warnings"].append("one or more receipts lack a parseable start timestamp")
    host_outliers = comparisons.get("full_minus_none", {}).get("host_cpu_seconds", {}).get(
        "influence", {}).get("materialOutlierBlocks", [])
    if host_outliers:
        diagnostics["warnings"].append(f"host CPU paired outlier blocks: {host_outliers}")
    for comparison, metrics in comparisons.items():
        for metric, result in metrics.items():
            outliers = result["influence"]["materialOutlierBlocks"]
            warning = f"{comparison} {metric} paired outlier blocks: {outliers}"
            if outliers and warning not in diagnostics["warnings"]:
                diagnostics["warnings"].append(warning)
    for metric, postures in drift.items():
        for posture, result in postures.items():
            relative = result["relativeSlopePerRun"]
            if relative is not None and abs(relative) >= 0.02:
                diagnostics["warnings"].append(
                    f"{posture} {metric} absolute drift is at least 2% of its median per run"
                )
    return {
        "schemaVersion": 1,
        "unitOfAnalysis": "randomized-block repetition",
        "blocks": len(blocks),
        "verdict": "pass" if not failures else "blocked",
        "failures": failures,
        "comparisons": comparisons,
        "diagnostics": diagnostics,
        "telemetryBytesSource": {
            "source": next(iter(sources)) if len(sources) == 1 else sorted(sources),
            "definition": (
                "spool.rawBodyBytes = AMQP body bytes transported from the SUT (Kieker binary "
                "chunks incl. Kieker's string registry); excludes AMQP frame overhead and the "
                "collector's on-disk spool framing (spoolBytes). Stage 4 (transported)."
            ),
        },
        "cautions": [
            f"Intervals describe {len(blocks)} run-level blocks, not request-level confidence intervals. "
            f"tInterval95 is a Student-t interval on the paired mean (df = n-1); pairedDifferenceRange is the "
            f"sample range. No bootstrap interval is emitted below {MINIMUM_BOOTSTRAP_BLOCKS} blocks: with n = 3 "
            "the percentile bootstrap of the mean collapses to the sample range and cannot contain zero.",
            "A direction is not a causal instrumentation effect if execution-order or host-interference checks fail.",
        ],
    }


def analyze_directory(root: Path) -> dict:
    receipts = [json.loads(path.read_text()) for path in sorted(root.glob("*/receipt.json"))]
    return analyze(receipts)
