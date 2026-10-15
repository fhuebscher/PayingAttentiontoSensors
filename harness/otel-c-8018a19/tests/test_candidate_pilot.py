from __future__ import annotations

import copy
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


MODULE = Path(__file__).parents[1] / "modules/teastore/execution/candidate_pilot.py"
SPEC = importlib.util.spec_from_file_location("teastore_candidate_pilot", MODULE)
candidate_pilot = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(candidate_pilot)

DESCRIPTOR_PATH = (
    Path(__file__).parents[1] / "pipelines/campaigns/teastore-candidate-pilot-v1.json"
)


def descriptor() -> dict:
    return candidate_pilot.strict_json_file(DESCRIPTOR_PATH)


def set_path(document: dict, path: tuple[object, ...], value: object) -> dict:
    result = copy.deepcopy(document)
    cursor: object = result
    for part in path[:-1]:
        cursor = cursor[part]  # type: ignore[index]
    cursor[path[-1]] = value  # type: ignore[index]
    return result


def test_frozen_descriptor_and_exact_selector_receipts_are_recomputed():
    document = descriptor()
    assert candidate_pilot.validate_descriptor(document) is document
    assert document == candidate_pilot.frozen_descriptor()

    allocation = candidate_pilot.allocate_schedules()
    assert [allocation[item]["selectorSha256"] for item in candidate_pilot.REGIMES] == [
        "53361e7ca83e9fb0183c50ba0c99fbe7046a1bde42cdaf816f6d42851dc47664",
        "21e2aee52a8f274721f0ccc6ed94514dd633946f894af4d45dbd23492d94b911",
        "d7d887c81a71799eff4bcbbdf54a0056520940aec2f8622960d4a35dc94f36ee",
    ]
    assert [allocation[item]["selectedCandidateIndex"] for item in candidate_pilot.REGIMES] == [
        4, 5, 10
    ]
    assert allocation["no-fault-cost"]["blocks"] == [
        ["selected", "none", "full"],
        ["none", "full", "selected"],
        ["full", "selected", "none"],
    ]
    assert allocation["auth-freeze-effect"]["blocks"] == [
        ["selected", "none", "full"],
        ["full", "selected", "none"],
        ["none", "full", "selected"],
    ]
    assert allocation["persistence-crash-effect"]["blocks"] == [
        ["full", "selected", "none"],
        ["selected", "none", "full"],
        ["none", "full", "selected"],
    ]


def test_candidates_are_six_rows_each_left_then_right_rotation():
    candidates = candidate_pilot.schedule_candidates()
    assert len(candidates) == 12
    assert candidates[0] == (
        ("none", "selected", "full"),
        ("selected", "full", "none"),
        ("full", "none", "selected"),
    )
    assert candidates[1] == (
        ("none", "selected", "full"),
        ("full", "none", "selected"),
        ("selected", "full", "none"),
    )
    for schedule in candidates:
        assert len(set(schedule)) == 3
        assert all(set(row) == set(candidate_pilot.POSTURES) for row in schedule)
        for position in range(3):
            assert {row[position] for row in schedule} == set(candidate_pilot.POSTURES)


def test_compiler_emits_27_unique_noneligible_cells_in_separate_roots():
    document = descriptor()
    first = candidate_pilot.compile_plan(document)
    second = candidate_pilot.compile_plan(copy.deepcopy(document))
    assert candidate_pilot.canonical_json_bytes(first) == candidate_pilot.canonical_json_bytes(second)
    assert first["runCount"] == 27
    assert first["minimumTimedSeconds"] == 19440
    assert first["canonical"] is False

    roots = {item["regime"]: item for item in first["regimeRoots"]}
    assert {item["artifactRootClass"] for item in roots.values()} == {
        "cost", "effect/auth-freeze", "effect/persistence-crash"
    }
    cells = [
        cell
        for root in roots.values()
        for block in root["blocks"]
        for cell in block["cells"]
    ]
    assert len(cells) == len({cell["runId"] for cell in cells}) == 27
    assert all(cell["runKey"]["attempt"] == 1 for cell in cells)
    assert all(cell["scheduledState"] == "not-started" for cell in cells)
    assert all(cell["mayReplaceFailedCell"] is False for cell in cells)
    assert all(
        block["pairedContrastEligibleInitially"] is False
        for root in roots.values()
        for block in root["blocks"]
    )
    assert all(
        len({cell["runKey"]["posture"] for cell in block["cells"]}) == 3
        for root in roots.values()
        for block in root["blocks"]
    )
    assert all(
        cell["selectionId"] == ("fault-qualification" if cell["runKey"]["posture"] == "selected" else None)
        for cell in cells
    )


@pytest.mark.parametrize(
    ("path", "defect"),
    [
        (("id",), "teastore-candidate-pilot-v2"),
        (("status",), "candidate-evidence"),
        (("targetHost",), "fb14srv6"),
        (("source", "sutCommit"), "0" * 40),
        (("source", "frameworkCommitPolicy"), "any-commit"),
        (("workload", "id"), "full-journey"),
        (("workload", "journeysPerSecond"), 0.2),
        (("workload", "concurrency"), 7),
        (("workload", "excludedActions"), ["cart"]),
        (("workload", "journeyLedger", "oneRowPerOfferedJourney"), False),
        (("workload", "journeyLedger", "requiredFields"), ["journeyId"]),
        (("workload", "journeyLedger", "requestRequiredFields"), ["routeIdentity"]),
        (("design", "postures"), ["none", "full", "selected"]),
        (("design", "selectedSource"), "auth"),
        (("design", "blocksPerRegime"), 6),
        (("design", "totalRuns"), 18),
        (("design", "coldStartEachRun"), False),
        (("design", "deploymentQueueAttemptArtifactReuse"), True),
        (("design", "costAndEffectPoolable"), True),
        (("design", "regimes", 0, "fault"), "auth-freeze"),
        (("design", "regimes", 1, "artifactRootClass"), "cost"),
        (("timing", "warmupSeconds"), 0),
        (("timing", "measurementSeconds"), 599),
        (("timing", "offeredJourneysPerRun"), 89),
        (("timing", "offeredJourneysTotal"), 2429),
        (("timing", "faultOnsetSeconds"), 181),
        (("timing", "interventionHoldSeconds"), 149),
        (("timing", "minimumActualJourneyStartsPerPhase"), 19),
        (("timing", "sharedBarrierParticipants"), ["workload", "collector"]),
        (("timing", "phaseAssignmentSource"), "nominal-schedule"),
        (("timing", "minimumTimedSeconds"), 18000),
        (("schedule", "version"), "schedule-v2"),
        (("schedule", "firstRows", 0), ["N", "F", "S"]),
        (("schedule", "receipts", 0, "selectorSha256"), "0" * 64),
        (("schedule", "receipts", 1, "selectedCandidateIndex"), 4),
        (("schedule", "receipts", 2, "blocks", 0), ["none", "selected", "full"]),
        (("runIdentity", "initialAttempt"), 0),
        (("runIdentity", "retryMayReplaceCell"), True),
        (("runIdentity", "diagnosticRerunMayRestoreComparativeEligibility"), True),
        (("groundTruth", "fault", "source"), "kieker"),
        (("groundTruth", "fault", "intervalLabel"), "functional-outage"),
        (("groundTruth", "fault", "functionalOutageWithoutContinuousWitness"), False),
        (("groundTruth", "fault", "commandSuccessAloneEstablishesTruth"), True),
        (("groundTruth", "fault", "scenarioContracts", 0, "duringPredicate"), "running"),
        (("groundTruth", "fault", "scenarioContracts", 1, "containerIdentityRule"), "any"),
        (("groundTruth", "path", "requiredSensors"), ["operation:auth"]),
        (("groundTruth", "path", "directEdgePredicate"), "aggregate-phase-presence"),
        (("groundTruth", "path", "executedDenominator"), "expected-opportunities"),
        (("groundTruth", "path", "crossTraceAssemblyAllowed"), True),
        (("groundTruth", "path", "expectedOpportunityIsExecutionProof"), True),
        (("groundTruth", "path", "scoredPhases"), ["during"]),
        (("groundTruth", "path", "tokenContractFrozenBeforeOutcomes"), False),
        (("groundTruth", "path", "tokenContractRequiredCoverage"), ["generation"]),
        (("groundTruth", "path", "missingWitnessOrCorrelationState"), "failed"),
        (("groundTruth", "path", "missingWitnessOrCorrelationValue"), 0),
        (("groundTruth", "path", "noneZeroRequires"), []),
        (("outcomes", "offeredJourneysAreDenominator"), False),
        (("outcomes", "emptyLatencyValue"), 0),
        (("outcomes", "costRegimeOnly"), "all"),
        (("outcomes", "retainedTraceBytesAreWireBytes"), True),
        (("outcomes", "windowMembership"), "collector-retention-window"),
        (("outcomes", "collectorTailUse"), "scored"),
        (("postureProof", "selected", "selectionId"), "auth"),
        (("postureProof", "none", "zeroOperationalCostClaim"), True),
        (("postureProof", "full", "requires"), []),
        (("queueProof", "manyRowsPerMessageAllowed"), False),
        (("queueProof", "postureLabelAloneProvesMaterialization"), True),
        (("queueProof", "requires"), ["exactly-one-collector"]),
        (("missingness", "numericMissingValue"), 0),
        (("missingness", "failedAttemptsRetainedAndCharged"), False),
        (("missingness", "silentRetryAllowed"), True),
        (("analysis", "comparativeUnit"), "journey"),
        (("analysis", "descriptiveOnly"), False),
        (("analysis", "independentSequentialBlocksClaim"), True),
        (("analysis", "directedCarryoverBalancedClaim"), True),
        (("analysis", "materialOrderOrThermalTrendResult"), "valid"),
        (("evidence", "designLabel"), "candidate-evidence"),
        (("evidence", "diagnosticLabel"), "candidate-evidence"),
        (("evidence", "canonical"), True),
        (("evidence", "promotionRequiresSeparateHumanGate"), False),
        (("continuation", "outcomeTriggeredExtensionAllowed"), True),
        (("continuation", "earlySuccessStopAllowed"), True),
    ],
)
def test_planted_descriptor_defects_fail_closed(path, defect):
    with pytest.raises(candidate_pilot.ProtocolError):
        candidate_pilot.validate_descriptor(set_path(descriptor(), path, defect))


def test_unknown_missing_and_wrong_typed_fields_fail_closed():
    unknown = descriptor()
    unknown["helpfulNote"] = "not frozen"
    missing = descriptor()
    del missing["analysis"]
    wrong_type = set_path(descriptor(), ("timing", "warmupSeconds"), True)
    for attacked in (unknown, missing, wrong_type):
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
def test_strict_json_parser_rejects_duplicate_nonfinite_and_malformed_values(payload):
    with pytest.raises(candidate_pilot.ProtocolError):
        candidate_pilot.strict_json_loads(payload)


@pytest.mark.parametrize(
    ("path", "defect"),
    [
        (("runCount",), 26),
        (("canonical",), True),
        (("scheduleAllocation", "no-fault-cost", "selectedCandidateIndex"), 5),
        (("regimeRoots", 0, "artifactRootClass"), "effect"),
        (("regimeRoots", 0, "blocks", 0, "order"), ["none", "selected", "full"]),
        (("regimeRoots", 0, "blocks", 0, "pairedContrastEligibleInitially"), True),
        (("regimeRoots", 0, "blocks", 0, "cells", 0, "runId"), "overwritten"),
        (("regimeRoots", 0, "blocks", 0, "cells", 0, "runKey", "attempt"), 2),
        (("regimeRoots", 0, "blocks", 0, "cells", 0, "artifactRoot"), "shared"),
        (("regimeRoots", 0, "blocks", 0, "cells", 0, "mayReplaceFailedCell"), True),
        (("missingnessBoundary", "numericMissingValue"), 0),
        (("analysisBoundary", "descriptiveOnly"), False),
    ],
)
def test_planted_compiled_plan_defects_are_detected(path, defect):
    document = descriptor()
    plan = candidate_pilot.compile_plan(document)
    attacked = set_path(plan, path, defect)
    with pytest.raises(candidate_pilot.ProtocolError):
        candidate_pilot.validate_plan(document, attacked)


def test_five_hour_window_refuses_full_candidate_pilot():
    with pytest.raises(candidate_pilot.AdmissionError, match="exceeds supplied time budget") as caught:
        candidate_pilot.assess_time_window(
            descriptor(), mode="candidate", evidence_label="candidate-evidence",
            now="2026-08-29T01:40:00+10:00",
            authorization_deadline="2026-08-29T06:40:00+10:00",
            time_budget_seconds=5 * 3600,
        )
    assert "authorization deadline" in str(caught.value)


def test_candidate_window_requires_upper_operational_allowance_and_exact_label():
    receipt = candidate_pilot.assess_time_window(
        descriptor(), mode="candidate", evidence_label="candidate-evidence",
        now="2026-08-28T15:00:00Z", authorization_deadline="2026-08-28T23:00:00Z",
        time_budget_seconds=8 * 3600,
    )
    assert receipt["requiredTimedSeconds"] == 19440
    assert receipt["requiredAuthorizationSeconds"] == 28800
    assert receipt["runCount"] == 27
    assert receipt["schemaVersion"] == 2
    assert receipt["kind"] == "time-window-feasibility"
    assert receipt["feasible"] is True
    assert receipt["comparativeDesignRequested"] is True
    assert receipt["comparativeEligible"] is False
    assert receipt["admitted"] is False
    assert receipt["runtimeAuthorized"] is False
    assert receipt["candidateEvidenceAuthorized"] is False
    assert receipt["promotionAuthorized"] is False
    with pytest.raises(candidate_pilot.AdmissionError, match="candidate execution requires"):
        candidate_pilot.assess_time_window(
            descriptor(), mode="candidate", evidence_label="smoke-validation",
            now="2026-08-28T15:00:00Z", authorization_deadline="2026-08-28T23:00:01Z",
            time_budget_seconds=28801,
        )
    with pytest.raises(candidate_pilot.AdmissionError, match="exceeds"):
        candidate_pilot.assess_time_window(
            descriptor(), mode="candidate", evidence_label="candidate-evidence",
            now="2026-08-28T15:00:00Z", authorization_deadline="2026-08-28T23:00:00Z",
            time_budget_seconds=28800, lifecycle_allowance_seconds=1,
        )


@pytest.mark.parametrize(
    ("hours", "allowance"),
    ((8, 0), (9, 300)),
)
def test_eight_and_nine_hour_candidate_windows_never_admit_or_authorize(
    hours: int, allowance: int,
) -> None:
    now = datetime(2026, 8, 28, 15, tzinfo=timezone.utc)
    deadline = now.replace(hour=23) if hours == 8 else datetime(
        2026, 8, 29, 0, tzinfo=timezone.utc
    )
    receipt = candidate_pilot.assess_time_window(
        descriptor(), mode="candidate", evidence_label="candidate-evidence",
        now=now, authorization_deadline=deadline,
        time_budget_seconds=hours * 3600,
        lifecycle_allowance_seconds=allowance,
    )
    assert receipt["feasible"] is True
    assert receipt["requiredTimedSeconds"] == 19_440
    assert receipt["requiredAuthorizationSeconds"] == 28_800 + allowance
    assert {
        "admitted": receipt["admitted"],
        "runtimeAuthorized": receipt["runtimeAuthorized"],
        "candidateEvidenceAuthorized": receipt["candidateEvidenceAuthorized"],
        "promotionAuthorized": receipt["promotionAuthorized"],
    } == {
        "admitted": False,
        "runtimeAuthorized": False,
        "candidateEvidenceAuthorized": False,
        "promotionAuthorized": False,
    }
    assert receipt["requiresFreshGateRun"] is True


def test_legacy_admit_name_is_a_non_authorizing_compatibility_alias() -> None:
    receipt = candidate_pilot.admit_runtime(
        descriptor(), mode="candidate", evidence_label="candidate-evidence",
        now="2026-08-28T15:00:00Z",
        authorization_deadline="2026-08-28T23:00:00Z",
        time_budget_seconds=28_800,
    )
    assert receipt == candidate_pilot.assess_time_window(
        descriptor(), mode="candidate", evidence_label="candidate-evidence",
        now="2026-08-28T15:00:00Z",
        authorization_deadline="2026-08-28T23:00:00Z",
        time_budget_seconds=28_800,
    )
    assert receipt["admitted"] is receipt["runtimeAuthorized"] is False


def test_short_diagnostic_is_noncomparative_nonpromotional_and_nonreplacement():
    receipt = candidate_pilot.assess_time_window(
        descriptor(), mode="diagnostic", evidence_label="smoke-validation",
        now=datetime(2026, 8, 28, 15, tzinfo=timezone.utc),
        authorization_deadline="2026-08-28T20:00:00Z",
        time_budget_seconds=18000,
        diagnostic_run_count=3,
        diagnostic_warmup_seconds=30,
        diagnostic_measurement_seconds=120,
        lifecycle_allowance_seconds=300,
    )
    assert receipt["requiredTimedSeconds"] == 450
    assert receipt["requiredAuthorizationSeconds"] == 750
    assert receipt["comparativeEligible"] is False
    assert receipt["comparativeDesignRequested"] is False
    assert receipt["mayReplaceCandidateCell"] is False
    assert receipt["admitted"] is False
    assert receipt["runtimeAuthorized"] is False
    assert receipt["candidateEvidenceAuthorized"] is False
    assert receipt["promotionAuthorized"] is False
    assert receipt["requiresFreshGateRun"] is True
    assert receipt["deadlineWouldBeHardMutationCeilingIfAuthorized"] is True
    assert receipt["feasibilityDoesNotProveHarnessConformance"] is True
    assert receipt["unsupportedNumericValue"] is None


def test_diagnostic_cannot_borrow_candidate_label_or_candidate_length():
    with pytest.raises(candidate_pilot.AdmissionError, match="short diagnostic execution"):
        candidate_pilot.assess_time_window(
            descriptor(), mode="diagnostic", evidence_label="candidate-evidence",
            now="2026-08-28T15:00:00Z", authorization_deadline="2026-08-29T15:00:00Z",
            time_budget_seconds=86400,
        )
    with pytest.raises(candidate_pilot.AdmissionError, match="not shorter"):
        candidate_pilot.assess_time_window(
            descriptor(), mode="diagnostic", evidence_label="smoke-validation",
            now="2026-08-28T15:00:00Z", authorization_deadline="2026-08-29T15:00:00Z",
            time_budget_seconds=86400, diagnostic_run_count=27,
            diagnostic_warmup_seconds=120, diagnostic_measurement_seconds=600,
        )


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"time_budget_seconds": 59}, "time budget"),
        ({"authorization_deadline": "2026-08-28T15:00:59Z"}, "authorization deadline"),
        ({"authorization_deadline": "2026-08-28T14:59:59Z"}, "not in the future"),
        ({"now": "2026-08-28T15:00:00"}, "UTC offset"),
        ({"mode": "full"}, "mode must"),
        ({"diagnostic_run_count": True}, "positive integer"),
        ({"diagnostic_measurement_seconds": 0}, "positive integer"),
        ({"lifecycle_allowance_seconds": -1}, "non-negative integer"),
    ],
)
def test_time_window_planted_boundary_defects_fail_closed(kwargs, match):
    parameters = {
        "mode": "diagnostic",
        "evidence_label": "smoke-validation",
        "now": "2026-08-28T15:00:00Z",
        "authorization_deadline": "2026-08-28T16:00:00Z",
        "time_budget_seconds": 3600,
        "diagnostic_run_count": 1,
        "diagnostic_warmup_seconds": 0,
        "diagnostic_measurement_seconds": 60,
        "lifecycle_allowance_seconds": 0,
    }
    parameters.update(kwargs)
    with pytest.raises(candidate_pilot.AdmissionError, match=match):
        candidate_pilot.assess_time_window(descriptor(), **parameters)


def test_cli_compiles_validates_and_refuses_five_hour_candidate_window(tmp_path, capsys):
    plan_path = tmp_path / "plan.json"
    assert candidate_pilot.main([
        "compile", "--descriptor", str(DESCRIPTOR_PATH), "--output", str(plan_path)
    ]) == 0
    assert candidate_pilot.main([
        "validate", "--descriptor", str(DESCRIPTOR_PATH), "--plan", str(plan_path)
    ]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["valid"] is True and validation["planValid"] is True

    assert candidate_pilot.main([
        "check-window", "--descriptor", str(DESCRIPTOR_PATH), "--mode", "candidate",
        "--evidence-label", "candidate-evidence", "--now", "2026-08-29T01:40:00+10:00",
        "--authorization-deadline", "2026-08-29T06:40:00+10:00",
        "--time-budget-seconds", "18000",
    ]) == 2
    assert "exceeds" in capsys.readouterr().err


def test_cli_check_window_is_explicitly_non_authorizing_and_admit_name_is_absent(capsys):
    assert candidate_pilot.main([
        "check-window", "--descriptor", str(DESCRIPTOR_PATH), "--mode", "candidate",
        "--evidence-label", "candidate-evidence", "--now", "2026-08-28T15:00:00Z",
        "--authorization-deadline", "2026-08-28T23:00:00Z",
        "--time-budget-seconds", "28800",
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["kind"] == "time-window-feasibility"
    assert receipt["feasible"] is True
    assert receipt["admitted"] is False
    assert receipt["runtimeAuthorized"] is False
    assert receipt["candidateEvidenceAuthorized"] is False
    with pytest.raises(SystemExit):
        candidate_pilot._parser().parse_args(["admit"])


def test_cli_plan_parser_rejects_duplicate_keys(tmp_path, capsys):
    plan = candidate_pilot.compile_plan(descriptor())
    plan_path = tmp_path / "plan.json"
    rendered = json.dumps(plan)
    plan_path.write_text(rendered[:-1] + ',"runCount":27}', encoding="utf-8")
    assert candidate_pilot.main([
        "validate", "--descriptor", str(DESCRIPTOR_PATH), "--plan", str(plan_path)
    ]) == 2
    assert "duplicate JSON key" in capsys.readouterr().err


def test_cli_refuses_to_overwrite_a_retained_plan(tmp_path, capsys):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("retained\n")
    assert candidate_pilot.main([
        "compile", "--descriptor", str(DESCRIPTOR_PATH), "--output", str(plan_path)
    ]) == 2
    assert plan_path.read_text() == "retained\n"
    assert "refusing to overwrite" in capsys.readouterr().err
