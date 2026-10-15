"""Conservatively adapt heterogeneous SUT receipts to common objectives.

Missing or incommensurable measurements remain ``None``. In particular,
collector log size is not telemetry bytes and sampled CPU percentages are not
application CPU-seconds.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any


OBJECTIVE_DIRECTIONS = {
    "required_sensor_retention": "maximize",
    "required_edge_retention": "maximize",
    "request_success_rate": "maximize",
    "latency_p95_ms": "minimize",
    "latency_p99_ms": "minimize",
    "application_cpu_seconds_per_success": "minimize",
    "telemetry_bytes_per_success": "minimize",
    "telemetry_records_per_success": "minimize",
    "activation_count": "minimize",
    "operational_complexity": "minimize",
}


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result = float(value)
        if math.isfinite(result):
            return result
    return None


def _ratio(numerator: Any, denominator: Any) -> float | None:
    left, right = _number(numerator), _number(denominator)
    return (left / right if left is not None and left >= 0 and right is not None and right > 0
            else None)


def _nonnegative(value: Any) -> float | None:
    result = _number(value)
    return result if result is not None and result >= 0 else None


def _unit_interval(value: Any) -> float | None:
    result = _number(value)
    return result if result is not None and 0 <= result <= 1 else None


def _success_rate(completed: Any, offered: Any) -> float | None:
    value = _ratio(completed, offered)
    return value if value is not None and value <= 1 else None


def _aligned_measurement_window(receipt: dict[str, Any], completed: float | None) -> bool:
    """Require evidence that resource/telemetry counters share the request window.

    A collector total or a serialized trace file cannot safely be normalized by
    completed requests unless the receipt identifies a bounded measurement
    window and its latency denominator agrees with the completed workload.
    """
    window = receipt.get("window") if isinstance(receipt.get("window"), dict) else {}
    latency = receipt.get("latencyMs") if isinstance(receipt.get("latencyMs"), dict) else {}
    count = _number(latency.get("count"))
    started, ended = window.get("startedAt"), window.get("endedAt")
    if not (completed is not None and isinstance(started, str) and isinstance(ended, str)
            and count is not None and count == completed):
        return False
    try:
        return datetime.fromisoformat(ended) >= datetime.fromisoformat(started)
    except (TypeError, ValueError):
        return False


def receipt_objectives(receipt: dict[str, Any]) -> dict[str, Any]:
    workload = receipt.get("workload") if isinstance(receipt.get("workload"), dict) else {}
    latency = receipt.get("latencyMs") if isinstance(receipt.get("latencyMs"), dict) else {}
    resources = receipt.get("resources") if isinstance(receipt.get("resources"), dict) else {}
    telemetry = receipt.get("telemetry") if isinstance(receipt.get("telemetry"), dict) else {}
    visibility = receipt.get("visibility") if isinstance(receipt.get("visibility"), dict) else {}
    completed = _number(workload.get("completed"))
    aligned = _aligned_measurement_window(receipt, completed)
    records = (_number(telemetry.get("records")) if aligned else None)
    # ``telemetry.bytes`` in legacy receipts may be a serialized artifact size,
    # not emitted wire bytes. Only an explicit semantics declaration can make it
    # a common cost objective.
    byte_semantics = telemetry.get("bytesSemantics")
    emitted_bytes = (_number(telemetry.get("bytes"))
                     if aligned and byte_semantics == "emitted-on-wire" else None)
    canonicality = receipt.get("canonicality") if isinstance(receipt.get("canonicality"), dict) else {}
    blockers = canonicality.get("blockers") if isinstance(canonicality.get("blockers"), list) else []
    values = {
        "required_sensor_retention": _unit_interval(visibility.get("requiredSensorRetention")),
        "required_edge_retention": _unit_interval(visibility.get("requiredEdgeRetention")),
        "request_success_rate": _success_rate(completed, workload.get("offered")),
        "latency_p95_ms": _nonnegative(latency.get("p95")),
        "latency_p99_ms": _nonnegative(latency.get("p99")),
        "application_cpu_seconds_per_success": (_ratio(resources.get("applicationCpuSeconds"), completed)
                                                if aligned else None),
        "telemetry_bytes_per_success": _ratio(emitted_bytes, completed),
        "telemetry_records_per_success": _ratio(records, completed),
        "activation_count": _nonnegative(receipt.get("activationCount")),
        "operational_complexity": _nonnegative(receipt.get("operationalComplexity")),
    }
    missing_reasons = {
        "required_sensor_retention": "receipt lacks explicit required-sensor retention",
        "required_edge_retention": "receipt lacks explicit required-edge retention",
        "request_success_rate": "offered/completed denominator is missing, invalid, or outside [0,1]",
        "latency_p95_ms": "receipt lacks a finite p95 latency",
        "latency_p99_ms": "receipt lacks a finite p99 latency",
        "application_cpu_seconds_per_success": (
            "application CPU-seconds and a workload-aligned measurement window are required"),
        "telemetry_bytes_per_success": (
            "workload-aligned bytes with bytesSemantics=emitted-on-wire are required"),
        "telemetry_records_per_success": (
            "workload-aligned telemetry.records and a completed denominator are required"),
        "activation_count": "receipt lacks an explicit activation count",
        "operational_complexity": "receipt lacks an explicit operational-complexity value",
    }
    return {
        "schemaVersion": 2,
        "directions": OBJECTIVE_DIRECTIONS,
        "values": values,
        "observed": sorted(key for key, value in values.items() if value is not None),
        "missing": sorted(key for key, value in values.items() if value is None),
        "missingReasons": {key: missing_reasons[key] for key, value in values.items() if value is None},
        "feasibility": {
            "declaredLabel": str(canonicality.get("label", "unknown")),
            "blockerCount": len(blockers),
            "feasibleAtDeclaredScope": not blockers,
        },
    }
