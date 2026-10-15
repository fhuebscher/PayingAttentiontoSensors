from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/hotel-reservation/execution/candidate_pilot.py"
DESCRIPTOR = ROOT / "pipelines/campaigns/hotel-reservation-selected-v1.json"
SPEC = importlib.util.spec_from_file_location("hotel_candidate_pilot", MODULE)
candidate_pilot = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = candidate_pilot
SPEC.loader.exec_module(candidate_pilot)


def descriptor() -> dict:
    return candidate_pilot.strict_json_file(DESCRIPTOR)


def set_path(document: dict, path: tuple, value):
    result = copy.deepcopy(document)
    target = result
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return result


def cells(plan: dict) -> list[dict]:
    return [
        cell
        for root in plan["regimeRoots"]
        for block in root["blocks"]
        for cell in block["cells"]
    ]


def test_frozen_descriptor_and_compiled_plan_are_exact_and_deterministic():
    document = descriptor()
    assert document == candidate_pilot.frozen_descriptor()
    first = candidate_pilot.compile_plan(document)
    second = candidate_pilot.compile_plan(copy.deepcopy(document))
    assert candidate_pilot.canonical_json_bytes(first) == candidate_pilot.canonical_json_bytes(second)
    assert candidate_pilot.validate_plan(first, document) == first
    # LMT+S pilot: 4 blocks x 4 postures x 5 regimes.
    assert first["runCount"] == candidate_pilot.TOTAL_RUNS == 80
    assert first["minimumTimedSeconds"] == candidate_pilot.TOTAL_RUNS * (
        candidate_pilot.WARMUP_SECONDS + candidate_pilot.MEASUREMENT_SECONDS
    ) == 12000
    assert first["runtimeAllowed"] is False
    assert first["externalMutationAllowed"] is False
    assert first["transport"] is None
    assert first["placementOrSourceCostEligible"] is False
    assert first["canonical"] is False


def test_standard_construction_api_is_digest_bound_and_never_authorizes_runtime():
    document = candidate_pilot.load_descriptor()
    plan = candidate_pilot.compile_plan(document)
    report = candidate_pilot.readiness_report(document, plan)
    assert candidate_pilot.canonical_sha256(document) == (
        candidate_pilot.EXPECTED_DESCRIPTOR_SHA256
    )
    assert plan["planCanonicalSha256"] == candidate_pilot.EXPECTED_PLAN_SHA256
    assert report == {
        "schemaVersion": 1,
        "studyEpoch": "hotel-reservation-selected-v1",
        "constructionReady": True,
        "descriptorCanonicalSha256": candidate_pilot.EXPECTED_DESCRIPTOR_SHA256,
        "planCanonicalSha256": candidate_pilot.EXPECTED_PLAN_SHA256,
        "runCount": candidate_pilot.TOTAL_RUNS,
        "runtimeAuthorized": False,
        "candidateEvidenceEligible": False,
        "placementOrSourceCostEligible": False,
        "constructionState": "local-construction-only",
        "blockers": [
            "runtime-adapter-absent-by-design",
            "source-off-and-selected-postures-unsupported",
            "native-operation-ground-truth-unqualified",
        ],
    }
    serialized = candidate_pilot.canonical_json_bytes(report)
    assert b"root-routing" not in serialized
    assert b"admission" not in serialized


def test_schedule_allocation_is_randomized_position_balanced_and_frozen():
    candidates = candidate_pilot.schedule_candidates()
    postures = candidate_pilot.POSTURES
    assert postures == ("none", "metrics", "selected", "full")
    assert candidate_pilot.FIRST_POSITIONS_PER_POSTURE == 1
    # 4 postures x 4 blocks: 4! = 24 first-position sequences, each posture
    # opening exactly one block (the preregistered property), and, by the
    # cyclic rotation within a block, each posture at EVERY position exactly
    # once per regime (a 4x4 Latin square).
    assert len(candidates) == 24 == len(set(candidates))
    for schedule in candidates:
        assert len(schedule) == candidate_pilot.BLOCKS_PER_REGIME == 4
        assert all(tuple(sorted(block)) == tuple(sorted(postures)) for block in schedule)
        for position in range(len(postures)):
            for posture in postures:
                assert [block[position] for block in schedule].count(posture) == 1
        for block in schedule:
            start = postures.index(block[0])
            assert block == tuple(postures[(start + k) % len(postures)] for k in range(len(postures)))

    allocation = candidate_pilot.allocate_schedules()
    # Frozen: selector digests are deterministic, so these indices are the receipts.
    assert [allocation[regime]["selectedCandidateIndex"] for regime in candidate_pilot.REGIMES] == [
        0, 7, 8, 23, 1,
    ]
    # Frozen: under the selected-v1 digests reservation-pause collided once and moved one index on.
    assert [allocation[regime]["collisionIncrements"] for regime in candidate_pilot.REGIMES] == [0, 0, 1, 0, 0]
    # The collision rule gives every regime its own schedule.
    assert len({allocation[regime]["selectedCandidateIndex"] for regime in candidate_pilot.REGIMES}) == len(
        candidate_pilot.REGIMES
    ) == 5
    receipts = {row["regime"]: row for row in descriptor()["schedule"]["receipts"]}
    for regime in candidate_pilot.REGIMES:
        assert allocation[regime]["blocks"] == receipts[regime]["blocks"]
        assert [block[0] for block in allocation[regime]["blocks"]] != [block[0] for block in allocation[
            candidate_pilot.REGIMES[
                (candidate_pilot.REGIMES.index(regime) + 1) % len(candidate_pilot.REGIMES)
            ]]["blocks"]]
    assert allocation["no-fault-cost"]["blocks"] == [
        ["full", "none", "metrics", "selected"], ["metrics", "selected", "full", "none"],
        ["none", "metrics", "selected", "full"], ["selected", "full", "none", "metrics"],
    ]


def test_compiler_emits_separate_noneligible_roots_and_faults_every_effect_cell():
    plan = candidate_pilot.compile_plan(descriptor())
    all_cells = cells(plan)
    assert len(all_cells) == len({cell["runId"] for cell in all_cells}) == candidate_pilot.TOTAL_RUNS
    assert len({cell["artifactRoot"] for cell in all_cells}) == candidate_pilot.TOTAL_RUNS
    assert all(cell["scheduledState"] == "not-started" for cell in all_cells)
    assert all(cell["candidateCellEligible"] is False for cell in all_cells)
    assert all(cell["runtimeAdapter"] is None for cell in all_cells)
    assert {cell["postureRole"] for cell in all_cells} == {
        "logs-fatal-sampler-off-tracer-disabled",
        "logs-info-sampler-on-tracer-disabled",
        "logs-info-sampler-on-tracer-frontend-only",
        "logs-info-sampler-on-tracer-full-sampling",
    }
    # Every (regime, block) holds each posture exactly once, and every posture
    # sits at every position exactly once per regime.
    for root in plan["regimeRoots"]:
        assert len(root["blocks"]) == 4
        for block in root["blocks"]:
            assert sorted(cell["runKey"]["posture"] for cell in block["cells"]) == sorted(
                candidate_pilot.POSTURES
            )
            assert [cell["position"] for cell in block["cells"]] == [1, 2, 3, 4]
        for position in range(1, 5):
            assert sorted(
                cell["runKey"]["posture"] for block in root["blocks"] for cell in block["cells"]
                if cell["position"] == position
            ) == sorted(candidate_pilot.POSTURES)

    roots = {root["regime"]: root for root in plan["regimeRoots"]}
    assert roots["no-fault-cost"]["fault"] is None
    assert all(
        block["comparativeState"] == "unsupported-source-cost"
        for block in roots["no-fault-cost"]["blocks"]
    )
    assert set(roots) == set(candidate_pilot.REGIMES)
    for regime, fault in (
        ("search-pause-effect", "search-pause"),
        ("reservation-pause-effect", "reservation-pause"),
        ("cpu-throttle-effect", "profile-cpu-throttle"),
        ("net-delay-effect", "rate-net-delay"),
    ):
        effect_cells = [cell for block in roots[regime]["blocks"] for cell in block["cells"]]
        assert effect_cells and all(cell["fault"] == fault for cell in effect_cells)


def test_windows_have_independent_denominators_and_do_not_supply_cross_regime_cost():
    timing = descriptor()["timing"]
    assert timing["costWindowContainsFault"] is False
    assert timing["effectWindowMaySupplyCostEstimate"] is False
    assert timing["separateArtifactRootsRequired"] is True
    assert timing["nominalScheduledStartsByPhase"] == {
        "pre": 450, "during": 150, "post-readiness": 600
    }
    assert sum(timing["nominalScheduledStartsByPhase"].values()) == timing["offeredRequestsPerRun"]
    assert all(
        count >= timing["minimumActualRequestStartsPerPhase"]
        for count in timing["nominalScheduledStartsByPhase"].values()
    )
    windows = timing["windowContracts"]
    assert windows["no-fault-cost"] == {
        "kind": "single-no-fault-measurement-window",
        "fault": None,
        "phaseNames": [],
        "denominator": "offered-request-ledger-rows-in-shared-window",
    }
    assert windows["fault-effect"]["regimes"] == [
        "search-pause-effect", "reservation-pause-effect",
        "cpu-throttle-effect", "net-delay-effect",
    ]
    assert windows["fault-effect"]["denominator"] == (
        "independently-witnessed-executed-opportunities-per-phase"
    )
    outcomes = descriptor()["outcomes"]
    assert outcomes["offeredRequestsAreDenominator"] is True
    assert outcomes["sourceCostComparisonState"] == "unsupported"
    assert outcomes["sourceCostComparisonValue"] is None
    assert outcomes["effectResourcesAreCostEstimates"] is False


def test_ground_truth_is_offered_request_native_trace_and_fault_specific():
    truth = descriptor()["groundTruth"]
    assert truth["fault"]["source"].endswith("independent-of-jaeger")
    assert truth["fault"]["commandSuccessAloneEstablishesTruth"] is False
    scenario_contracts = truth["fault"]["scenarioContracts"]
    assert {item["scenario"] for item in scenario_contracts} == {
        "search-pause", "reservation-pause", "profile-cpu-throttle", "rate-net-delay",
    }
    assert {item["scenario"]: item["service"] for item in scenario_contracts} == (
        candidate_pilot.FAULT_TARGETS
    )
    assert all(
        item["prePathTruth"] == "hotel-search-normal-v1"
        and item["postReadinessPathTruth"] == "hotel-search-normal-v1"
        for item in scenario_contracts
    )
    # A pause is an absence and preregisters a truncated prefix; a degradation
    # is not an absence and keeps the normal path during the fault.
    for item in scenario_contracts:
        if item["scenario"] in candidate_pilot.PAUSE_FAULTS:
            assert item["duringPathTruth"].endswith("-prefix-v1")
        else:
            assert item["duringPathTruth"] == "hotel-search-normal-v1"
    path = truth["path"]
    assert path["opportunitySource"] == "offered-request-ledger-before-scored-telemetry"
    assert path["executedDenominator"] == "independent-application-side-witness"
    assert path["expectedOpportunityIsExecutionProof"] is False
    assert path["normal"]["oneOriginalNativeTraceRequired"] is True
    assert path["normal"]["crossTraceAssemblyAllowed"] is False
    assert {item["fault"] for item in path["faultSpecific"]} == {
        "search-pause", "reservation-pause"
    }
    assert all(
        item["nativeOperationQualification"] == "unsupported-until-runtime-characterization"
        and item["numericValueWhenUnsupported"] is None
        for item in path["faultSpecific"]
    )
    assert path["missingWitnessOrCorrelationState"] == "unsupported"
    assert path["missingWitnessOrCorrelationValue"] is None


@pytest.mark.parametrize(
    ("path", "defect"),
    [
        # Immutable/randomized schedule defects.
        (("schedule", "receipts", 0, "selectedCandidateIndex"), 1),
        (("schedule", "receipts", 1, "selectorSha256"), "0" * 64),
        (("schedule", "receipts", 2, "blocks", 0), ["full", "selected", "metrics", "none"]),
        (("schedule", "receipts", 4, "selectedCandidateIndex"), 16),
        (("design", "blocksPerRegime"), 3),
        (("design", "totalRuns"), 79),
        # Window conflation defects.
        (("design", "costAndEffectPoolable"), True),
        (("design", "faultAppliedToEveryEffectCell"), False),
        (("design", "regimes", 0, "fault"), "search-pause"),
        (("design", "regimes", 1, "artifactRootClass"), "cost"),
        (("timing", "separateArtifactRootsRequired"), False),
        (("timing", "costWindowContainsFault"), True),
        (("timing", "effectWindowMaySupplyCostEstimate"), True),
        (("timing", "phaseAssignmentSource"), "nominal-only"),
        (("timing", "windowContracts", "no-fault-cost", "phaseNames"), ["during"]),
        (("timing", "windowContracts", "fault-effect", "denominator"), "traces"),
        (("outcomes", "effectResourcesAreCostEstimates"), True),
        # Missing or endogenous denominators/path truth.
        (("workload", "opportunityLedger", "oneRowPerOfferedRequest"), False),
        (("workload", "opportunityLedger", "requiredFields"), ["sequence"]),
        (("timing", "offeredRequestsPerRun"), 1199),
        (("timing", "nominalScheduledStartsByPhase", "during"), 0),
        (("outcomes", "offeredRequestsAreDenominator"), False),
        (("groundTruth", "path", "normal", "requiredSensors"), []),
        (("groundTruth", "path", "normal", "crossTraceAssemblyAllowed"), True),
        (("groundTruth", "path", "faultSpecific"), []),
        (("groundTruth", "fault", "scenarioContracts", 0, "prePathTruth"),
         "hotel-search-search-pause-prefix-v1"),
        (("groundTruth", "fault", "scenarioContracts", 1,
          "postReadinessPathTruth"), "hotel-search-reservation-pause-prefix-v1"),
        (("groundTruth", "path", "executedDenominator"), "observed-traces"),
        (("groundTruth", "path", "expectedOpportunityIsExecutionProof"), True),
        (("groundTruth", "path", "missingWitnessOrCorrelationValue"), 0),
        (("groundTruth", "fault", "commandSuccessAloneEstablishesTruth"), True),
        # Unsupported-posture/source-cost overclaims.
        (("design", "postures"), ["none", "selected", "full"]),
        (("design", "postureRoles", "none"), "source-off"),
        (("design", "unsupportedPostures", 0, "state"), "valid"),
        (("design", "unsupportedPostures", 0, "numericValue"), 0),
        (("postureProof", "none", "sourceWorkDisabled"), True),
        # LMT+S collection ladder: log level, sampler and tracer per posture.
        (("postureProof", "none", "logLevel"), "info"),
        (("postureProof", "none", "metricSampler"), True),
        # `selected` traces frontend only: widening it, or claiming full sampling for it, fails closed.
        (("collection", "tracedServicesByPosture", "selected"), ["frontend", "search"]),
        (("design", "postureRoles", "selected"), "logs-info-sampler-on-tracer-full-sampling"),
        (("postureProof", "metrics", "metricSampler"), False),
        (("collection", "logLevelByPosture", "none"), "info"),
        (("collection", "metricSamplerPostures"), ["full"]),
        (("collection", "tracePostures"), ["metrics", "full"]),
        (("collection", "alwaysOnCostMeasured"), True),
        # Degradation parameters and path truth.
        (("faultParameters", "cpuThrottleCpus"), "0.5"),
        (("faultParameters", "netDelayMilliseconds"), 10),
        (("faultParameters", "targets", "rate-net-delay"), "search"),
        (("groundTruth", "fault", "scenarioContracts", 0, "duringPathTruth"),
         "hotel-search-search-pause-prefix-v1"),
        (("outcomes", "sourceCostComparisonState"), "supported"),
        (("outcomes", "sourceCostComparisonValue"), 0),
        (("evidence", "placementOrSourceCostEligible"), True),
        # Runtime and missingness boundaries.
        (("transport", "executor"), "compose"),
        (("transport", "runtimeAllowed"), True),
        (("transport", "externalMutationAllowed"), True),
        (("missingness", "abstentionState"), "valid"),
        (("missingness", "abstentionNumericValue"), 0),
        (("missingness", "numericMissingValue"), 0),
        (("missingness", "silentRetryAllowed"), True),
    ],
)
def test_planted_descriptor_defects_fail_closed(path, defect):
    with pytest.raises(candidate_pilot.ProtocolError):
        candidate_pilot.validate_descriptor(set_path(descriptor(), path, defect))


def test_unknown_missing_and_boolean_for_integer_fail_closed():
    unknown = descriptor()
    unknown["helpfulNote"] = "not frozen"
    missing = descriptor()
    del missing["groundTruth"]
    boolean = set_path(descriptor(), ("design", "totalRuns"), True)
    for attacked in (unknown, missing, boolean):
        with pytest.raises(candidate_pilot.ProtocolError):
            candidate_pilot.validate_descriptor(attacked)


@pytest.mark.parametrize(
    "payload",
    [
        '{"schemaVersion":1,"schemaVersion":1}',
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":-Infinity}',
        '{"value":1} {"value":2}',
        '{"unterminated":',
    ],
)
def test_strict_json_parser_rejects_concealment_and_malformed_values(payload):
    with pytest.raises(candidate_pilot.ProtocolError):
        candidate_pilot.strict_json_loads(payload)


@pytest.mark.parametrize(
    ("path", "defect"),
    [
        (("runCount",), 79),
        (("runtimeAllowed",), True),
        (("transport",), "compose"),
        (("placementOrSourceCostEligible",), True),
        (("regimeRoots", 0, "artifactRootClass"), "effect/search-pause"),
        (("regimeRoots", 1, "blocks", 0, "order"), ["none", "metrics", "selected", "full"]),
        (("regimeRoots", 1, "blocks", 0, "cells", 0, "fault"), None),
        (("regimeRoots", 3, "blocks", 0, "cells", 0, "fault"), "search-pause"),
        (("regimeRoots", 1, "blocks", 0, "cells", 0, "candidateCellEligible"), True),
        (("missingnessBoundary", "numericMissingValue"), 0),
        (("outcomeBoundary", "sourceCostComparisonState"), "supported"),
    ],
)
def test_compiled_plan_drift_fails_closed(path, defect):
    document = descriptor()
    attacked = set_path(candidate_pilot.compile_plan(document), path, defect)
    with pytest.raises(candidate_pilot.ProtocolError):
        candidate_pilot.validate_plan(attacked, document)


def test_plan_write_is_idempotent_but_refuses_drift(tmp_path: Path):
    plan = candidate_pilot.compile_plan(descriptor())
    output = tmp_path / "plan.json"
    candidate_pilot.write_plan(output, plan)
    before = output.read_bytes()
    candidate_pilot.write_plan(output, copy.deepcopy(plan))
    assert output.read_bytes() == before
    attacked = copy.deepcopy(plan)
    attacked["runCount"] = 23
    with pytest.raises(candidate_pilot.ProtocolError, match="immutable plan"):
        candidate_pilot.write_plan(output, attacked)
    assert output.read_bytes() == before


def test_compiler_has_no_executor_or_transport_import_seam():
    source = MODULE.read_text(encoding="utf-8")
    for forbidden_import in (
        "import subprocess", "import socket", "import urllib", "import requests",
        "import paramiko",
    ):
        assert forbidden_import not in source
    plan = candidate_pilot.compile_plan(descriptor())
    assert plan["transport"] is None
    assert all(cell["runtimeAdapter"] is None for cell in cells(plan))
