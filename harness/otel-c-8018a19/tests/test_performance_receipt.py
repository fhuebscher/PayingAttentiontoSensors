import importlib.util
from pathlib import Path


MODULE = Path(__file__).parents[1] / "modules/teastore/validation/performance_receipt.py"
SPEC = importlib.util.spec_from_file_location("performance_receipt", MODULE)
performance_receipt = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(performance_receipt)


def receipt():
    return {
        "posture": "none", "source": {"dirty": False},
        "workload": {"offered": 10, "completed": 10, "failed": 0, "concurrency": 1},
        "latencyMs": {"count": 10, "p50": 1, "p95": 2, "p99": 3},
        "resources": {"applicationCpuSeconds": 1, "applicationMemoryPeakBytes": 2, "hostCpuSeconds": 3},
        "telemetry": {"records": 0, "bytes": 0, "uniqueSignatures": 0, "parseFailures": 0},
        "queue": {"purgedBefore": True, "messagesBefore": 0, "messagesAfter": 0, "exclusiveConsumer": True},
    }


def test_accepts_complete_matched_receipt():
    assert performance_receipt.validate(receipt())["verdict"] == "pass"


def test_blocks_denominator_and_none_posture_violation():
    value = receipt()
    value["latencyMs"]["count"] = 9
    value["telemetry"]["records"] = 1
    report = performance_receipt.validate(value)
    assert report["verdict"] == "blocked"
    assert len(report["blockers"]) == 2


def test_enriched_receipt_keeps_empty_latency_null_and_disjoint_outcomes():
    value = receipt()
    value["workload"] = {
        "offered": 10, "completed": 0, "successful": 0, "failed": 7,
        "timedOut": 3, "settled": 10, "concurrency": 1,
    }
    value["latencyMs"] = {
        "denominator": "successful-journeys", "count": 0,
        "p50": None, "p95": None, "p99": None, "mean": None,
    }
    assert performance_receipt.validate(value)["verdict"] == "pass"

    value["latencyMs"]["p50"] = 0
    report = performance_receipt.validate(value)
    assert report["verdict"] == "blocked"
    assert any("must be null" in item for item in report["blockers"])


def test_effect_receipt_excludes_resource_cost_projection():
    value = receipt()
    value.update(analysisKind="effect", resourceUse="diagnostic-only", resources=None)
    assert performance_receipt.validate(value)["verdict"] == "pass"

    value["resources"] = {
        "applicationCpuSeconds": 1,
        "applicationMemoryPeakBytes": 2,
        "hostCpuSeconds": 3,
        "applicationCpuSecondsPerOfferedJourney": 0.1,
    }
    report = performance_receipt.validate(value)
    assert report["verdict"] == "blocked"
    assert "effect receipt exposes a resource cost projection" in report["blockers"]


def test_single_parse_failure_is_effect_only_and_explicit():
    value = receipt()
    value["telemetry"]["parseFailures"] = 1
    assert performance_receipt.validate(value)["verdict"] == "blocked"

    value.update(analysisKind="effect", resourceUse="diagnostic-only", resources=None)
    assert performance_receipt.validate(value)["verdict"] == "pass"

    value["telemetry"]["parseFailures"] = 2
    assert performance_receipt.validate(value)["verdict"] == "blocked"


def test_parse_failure_count_rejects_boolean_projection():
    value = receipt()
    value["telemetry"]["parseFailures"] = False
    report = performance_receipt.validate(value)
    assert report["verdict"] == "blocked"
    assert any("non-negative integer" in item for item in report["blockers"])


def test_receipt_does_not_ignore_collector_correlation_errors():
    value = receipt()
    value["telemetry"]["collectorStats"] = {
        "acknowledgement_mode": "manual",
        "runtime_host_map_loaded": True,
        "correlation": {
            "eventsWithCorrelationErrors": 1,
            "eventsWithCorrelationWarnings": 0,
            "eventsWithServiceAttributionErrors": 0,
            "traceCompleteness": {
                "tracesWithEoiGaps": 0,
                "missingEoiCount": 0,
            },
        },
    }
    report = performance_receipt.validate(value)
    assert report["verdict"] == "blocked"
    assert any("parent correlation errors" in item for item in report["blockers"])


def test_receipt_blocks_forged_automatic_acknowledgement_mode():
    value = receipt()
    value["telemetry"]["collectorStats"] = {
        "acknowledgement_mode": "automatic",
        "runtime_host_map_loaded": True,
        "correlation": {
            "eventsWithCorrelationErrors": 0,
            "eventsWithCorrelationWarnings": 0,
            "eventsWithServiceAttributionErrors": 0,
            "traceCompleteness": {
                "tracesWithEoiGaps": 0,
                "missingEoiCount": 0,
            },
        },
    }
    report = performance_receipt.validate(value)
    assert report["verdict"] == "blocked"
    assert any("acknowledgement mode was not manual" in item
               for item in report["blockers"])
