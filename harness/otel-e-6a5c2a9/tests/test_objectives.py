from obsplacement.objectives import receipt_objectives


def test_objective_adapter_preserves_missing_and_normalizes_explicit_units():
    adapted = receipt_objectives({
        "workload": {"offered": 10, "completed": 8},
        "latencyMs": {"count": 8, "p95": 20, "p99": 40},
        "window": {"startedAt": "2026-08-09T00:00:00+00:00",
                   "endedAt": "2026-08-09T00:01:00+00:00"},
        "resources": {"applicationCpuSeconds": 4},
        "telemetry": {"records": 80, "bytes": 800, "bytesSemantics": "emitted-on-wire"},
        "visibility": {"requiredSensorRetention": 0.75, "requiredEdgeRetention": 1},
        "canonicality": {"label": "candidate-evidence", "blockers": []},
    })
    values = adapted["values"]
    assert values["request_success_rate"] == 0.8
    assert values["application_cpu_seconds_per_success"] == 0.5
    assert values["telemetry_bytes_per_success"] == 100
    assert values["required_sensor_retention"] == 0.75
    assert values["activation_count"] is None
    assert adapted["schemaVersion"] == 2
    assert "activation_count" in adapted["missingReasons"]


def test_collector_log_bytes_and_cpu_percent_are_not_mislabeled_as_cost():
    adapted = receipt_objectives({
        "workload": {"offered": 10, "completed": 10},
        "resources": {"frontend": {"meanCpuPercent": 3.2}},
        "telemetry": {"collectorLogBytes": 1234, "exportedSpans": 20},
        "canonicality": {"label": "noncanonical-control-smoke", "blockers": []},
    })
    values = adapted["values"]
    assert values["application_cpu_seconds_per_success"] is None
    assert values["telemetry_bytes_per_success"] is None
    assert values["telemetry_records_per_success"] is None


def test_serialized_artifact_bytes_and_unaligned_collector_totals_stay_missing():
    adapted = receipt_objectives({
        "workload": {"offered": 10, "completed": 10},
        "latencyMs": {"count": 10, "p95": 4, "p99": 5},
        "window": {"startedAt": "2026-08-09T00:00:00+00:00",
                   "endedAt": "2026-08-09T00:01:00+00:00"},
        "telemetry": {"records": 20, "bytes": 2},
    })
    assert adapted["values"]["telemetry_records_per_success"] == 2
    assert adapted["values"]["telemetry_bytes_per_success"] is None


def test_invalid_ratios_and_ranges_are_not_logged_as_objectives():
    adapted = receipt_objectives({
        "workload": {"offered": 2, "completed": 3},
        "latencyMs": {"p95": -1, "p99": float("inf")},
        "visibility": {"requiredSensorRetention": 1.1, "requiredEdgeRetention": -0.1},
    })
    assert all(value is None for key, value in adapted["values"].items()
               if key in {"request_success_rate", "latency_p95_ms", "latency_p99_ms",
                          "required_sensor_retention", "required_edge_retention"})
