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


def collector_stats_with_unwoven_roots(count):
    return {
        "acknowledgement_mode": "manual",
        "runtime_host_map_loaded": True,
        "correlation": {
            "eventsWithCorrelationErrors": count,
            "eventsWithUnwovenRootParent": count,
            "eventsWithProbeOrphanRoot": 0,
            "eventsWithCorrelationWarnings": 0,
            "eventsWithServiceAttributionErrors": 0,
            "traceCompleteness": {
                "tracesWithEoiGaps": 0,
                "missingEoiCount": 0,
            },
        },
    }


def test_unwoven_roots_block_when_closure_weaves_the_entry_point():
    value = receipt()
    value["posture"] = "selected"
    value["telemetry"]["collectorStats"] = collector_stats_with_unwoven_roots(5)
    value["postureProof"] = {
        "closureGroups": ["aspectj:auth", "aspectj:webui", "manual:registry-client"],
    }
    report = performance_receipt.validate(value)
    assert report["verdict"] == "blocked"
    assert any("missing native trace roots" in item for item in report["blockers"])


def test_unwoven_roots_accepted_when_closure_omits_the_entry_point():
    value = receipt()
    value["posture"] = "selected"
    value["telemetry"]["collectorStats"] = collector_stats_with_unwoven_roots(5)
    value["postureProof"] = {
        "closureGroups": ["aspectj:auth", "aspectj:persistence", "manual:registry-client"],
    }
    assert performance_receipt.validate(value)["verdict"] == "pass"


def test_missing_posture_proof_falls_back_to_posture_name():
    value = receipt()
    value["posture"] = "selected"
    value["telemetry"]["collectorStats"] = collector_stats_with_unwoven_roots(5)
    assert performance_receipt.validate(value)["verdict"] == "pass"

    value["posture"] = "full"
    report = performance_receipt.validate(value)
    assert report["verdict"] == "blocked"
    assert any("missing native trace roots" in item for item in report["blockers"])


def test_malformed_closure_groups_fail_closed_to_woven():
    value = receipt()
    value["posture"] = "selected"
    value["telemetry"]["collectorStats"] = collector_stats_with_unwoven_roots(5)
    value["postureProof"] = {"closureGroups": "aspectj:auth"}
    report = performance_receipt.validate(value)
    assert report["verdict"] == "blocked"
    assert any("missing native trace roots" in item for item in report["blockers"])


def test_receipt_does_not_ignore_collector_correlation_errors():
    value = receipt()
    value["telemetry"]["collectorStats"] = {
        "acknowledgement_mode": "manual",
        "runtime_host_map_loaded": True,
        "correlation": {
            "eventsWithCorrelationErrors": 1,
            "eventsWithUnwovenRootParent": 0,
            "eventsWithProbeOrphanRoot": 0,
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
            "eventsWithUnwovenRootParent": 0,
            "eventsWithProbeOrphanRoot": 0,
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


def test_probe_orphan_roots_are_excused_only_up_to_the_unwoven_count():
    """F-ADH-083: readiness-probe orphans are a counted subset of the unwoven
    roots; they never excuse a missing root that is not one of them, and on a
    cost receipt (the fixture) any nonzero count is itself a blocker."""
    value = receipt()
    value["posture"] = "full"
    stats = collector_stats_with_unwoven_roots(2)
    stats["correlation"]["eventsWithProbeOrphanRoot"] = 2
    value["telemetry"]["collectorStats"] = stats
    report = performance_receipt.validate(value)
    assert report["verdict"] == "blocked"
    assert not any("missing native trace roots" in item for item in report["blockers"])
    assert any("readiness-probe orphans on cost evidence" in item for item in report["blockers"])

    stats["correlation"]["eventsWithProbeOrphanRoot"] = 1
    report = performance_receipt.validate(value)
    assert any("missing native trace roots" in item for item in report["blockers"])

    stats["correlation"]["eventsWithProbeOrphanRoot"] = 3
    report = performance_receipt.validate(value)
    assert any("probe-orphan-root count is inconsistent" in item for item in report["blockers"])


# F-ADH-084: this validator never looked at containers_bad at all, so a rejected
# AMQP container was invisible here while it aborted the campaign upstream. It
# now surfaces the counter and nets it out by the same rule as the producer.
CRASH_BANNER_DIAGNOSTIC = {
    "schemaVersion": 1, "sequence": 1399, "bodyBytes": 155, "bodySha256": "e" * 64,
    "error": "37 unconsumed records-region bytes",
    "recordClasses": ["kieker.common.record.misc.KiekerMetadataRecord"],
    "parsedExecutionRecords": 0,
    "loggingTimestampNs": 1_788_693_604_746_414_240,
    "registryContainerIds": ["640b7c0a2577"],
}


def crash_receipt(**tolerance_updates):
    value = receipt()
    value["posture"] = "full"
    value["analysisKind"] = "effect"
    value["resourceUse"] = "diagnostic-only"
    value["resources"] = None
    value["schemaVersion"] = 2
    value["telemetry"]["collectorStats"] = {
        "messages": 3013, "containers_ok": 3012, "containers_bad": 1,
        "records_ok": 75548, "records_bad": 0,
        "acknowledgement_mode": "manual", "runtime_host_map_loaded": True,
        "correlation": {
            "events": 75548, "eventsWithCorrelationErrors": 6,
            "eventsWithUnwovenRootParent": 6, "eventsWithProbeOrphanRoot": 6,
            "eventsWithCorrelationWarnings": 0,
            "eventsWithServiceAttributionErrors": 0,
            "traceCompleteness": {"traces": 1161, "tracesWithEoiGaps": 0,
                                  "missingEoiCount": 0, "tracesNotStartingAtZero": 6},
        },
    }
    tolerance = {
        "applied": True, "toleratedCorrelationErrorEvents": 0,
        "toleratedContainerParseFailures": 1,
        "residualContainerParseFailures": 0,
        "containerParseFailures": [CRASH_BANNER_DIAGNOSTIC],
    }
    tolerance.update(tolerance_updates)
    value["exposureTolerance"] = tolerance
    return value


def container_blockers(value) -> list[str]:
    return [blocker for blocker in performance_receipt.validate(value)["blockers"]
            if "container parse" in blocker]


def test_receipt_validator_surfaces_and_scopes_container_parse_failures():
    assert container_blockers(crash_receipt()) == []
    # No tolerance at all, or a cost cell, keeps the rejection blocking.
    bare = crash_receipt()
    del bare["exposureTolerance"]
    assert container_blockers(bare) == ["collector container parse failures are nonzero"]
    cost = crash_receipt()
    cost["analysisKind"] = "cost"
    cost["resourceUse"] = "measured"
    assert "cost evidence carries a nonzero container parse tolerance" in container_blockers(cost)
    assert "collector container parse failures are nonzero" in container_blockers(cost)
    for updates in ({"containerParseFailures": []},
                    {"toleratedContainerParseFailures": 2},
                    {"containerParseFailures": "one"}):
        blockers = container_blockers(crash_receipt(**updates))
        assert "container parse tolerance is not accounted for by its diagnostics" in blockers
        assert "collector container parse failures are nonzero" in blockers
    assert "container parse tolerance counter is invalid" in container_blockers(
        crash_receipt(toleratedContainerParseFailures=-1))
