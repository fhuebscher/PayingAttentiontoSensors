#!/usr/bin/env python3
"""Compile and validate the frozen TeaStore candidate-pilot schedule.

This module is deliberately not an experiment runner.  It turns the frozen
protocol descriptor into an immutable, reviewable run plan and calculates
whether a requested candidate or diagnostic schedule fits a proposed time
window.  Feasibility is never runtime authorization.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DESCRIPTOR = ROOT / "pipelines/campaigns/teastore-candidate-pilot-sys-v1.json"

# sys lineage (2026-09-29): successor of teastore-candidate-pilot-v1 (f352f8d) that adds
# cgroup-v2 system samples to every cell.  The epoch string seeds the schedule
# selector, so the block orders below are re-derived, not copied from v1.
EPOCH = "teastore-candidate-pilot-sys-v1"
SUT_COMMIT = "34b37f7e7be433ce72d5f9455e66922a13116749"
WORKLOAD = "login-browse-v1"
POSTURES = ("none", "selected", "full")
POSTURE_CODES = {"N": "none", "S": "selected", "F": "full"}
REGIMES = ("no-fault-cost", "auth-freeze-effect", "persistence-crash-effect")
FAULTS = {
    "no-fault-cost": None,
    "auth-freeze-effect": "auth-freeze",
    "persistence-crash-effect": "persistence-crash",
}
ARTIFACT_CLASSES = {
    "no-fault-cost": "cost",
    "auth-freeze-effect": "effect/auth-freeze",
    "persistence-crash-effect": "effect/persistence-crash",
}
BASE_ROWS = (
    ("N", "S", "F"),
    ("N", "F", "S"),
    ("S", "N", "F"),
    ("S", "F", "N"),
    ("F", "N", "S"),
    ("F", "S", "N"),
)
SCHEDULE_CONTEXT = "schedule-v1"
EXPECTED_SELECTION = {
    "no-fault-cost": {
        "selectorSha256": "49dce5c55c33d6f5dbbb864fc7cef0c89af74a067d8f47e5d7e7f01cc83c7429",
        "initialCandidateIndex": 9,
        "selectedCandidateIndex": 9,
        "blocks": (
            ("full", "none", "selected"),
            ("selected", "full", "none"),
            ("none", "selected", "full"),
        ),
    },
    "auth-freeze-effect": {
        "selectorSha256": "c84e7290a894b14522df38e894386d8e79d0ec8d2361cc98e306f73ef5e99243",
        "initialCandidateIndex": 7,
        "selectedCandidateIndex": 7,
        "blocks": (
            ("selected", "full", "none"),
            ("none", "selected", "full"),
            ("full", "none", "selected"),
        ),
    },
    "persistence-crash-effect": {
        "selectorSha256": "efd0b6deecaa19b3c372c1a0ed873fddfd3977417bd913bcb30f46f34906031f",
        "initialCandidateIndex": 3,
        "selectedCandidateIndex": 3,
        "blocks": (
            ("none", "full", "selected"),
            ("selected", "none", "full"),
            ("full", "selected", "none"),
        ),
    },
}

BLOCKS_PER_REGIME = 3
RUNS_PER_BLOCK = 3
TOTAL_RUNS = 27
WARMUP_SECONDS = 120
MEASUREMENT_SECONDS = 600
JOURNEYS_PER_SECOND = 0.15
CONCURRENCY = 8
OFFERED_PER_RUN = 90
OFFERED_TOTAL = 2430
FAULT_ONSET_SECONDS = 180
INTERVENTION_HOLD_SECONDS = 150
MINIMUM_PHASE_STARTS = 20
MINIMUM_TIMED_SECONDS = TOTAL_RUNS * (WARMUP_SECONDS + MEASUREMENT_SECONDS)
OPERATIONAL_ESTIMATE_SECONDS = {"lower": 6 * 3600, "upper": 8 * 3600}

DESIGN_LABEL = "method-design-only"
DIAGNOSTIC_LABEL = "smoke-validation"
CANDIDATE_LABEL = "candidate-evidence"


class ProtocolError(ValueError):
    """The descriptor or compiled plan differs from the frozen protocol."""


class AdmissionError(ValueError):
    """A requested execution is outside the frozen authorization boundary."""


def _reject_constant(value: str) -> NoReturn:
    raise ProtocolError(f"non-finite JSON value is forbidden: {value}")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_loads(value: str) -> Any:
    """Parse one RFC-8259-style JSON value, rejecting concealment primitives."""
    try:
        return json.loads(
            value,
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except ProtocolError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ProtocolError(f"invalid JSON: {exc}") from exc


def strict_json_file(path: Path) -> Any:
    try:
        return strict_json_loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProtocolError(f"cannot read {path}: {exc}") from exc


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"value is not canonical JSON: {exc}") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def schedule_candidates() -> tuple[tuple[tuple[str, ...], ...], ...]:
    """Enumerate six first rows, each left then right rotation (indices 0..11)."""
    candidates: list[tuple[tuple[str, ...], ...]] = []
    for coded_row in BASE_ROWS:
        row = tuple(POSTURE_CODES[item] for item in coded_row)
        left = (row, row[1:] + row[:1], row[2:] + row[:2])
        right = (row, row[-1:] + row[:-1], row[-2:] + row[:-2])
        candidates.extend((left, right))
    return tuple(candidates)


def allocate_schedules() -> dict[str, dict[str, Any]]:
    """Allocate outcome-independent constrained schedules in frozen regime order."""
    candidates = schedule_candidates()
    used: set[int] = set()
    allocation: dict[str, dict[str, Any]] = {}
    for regime in REGIMES:
        selector = EPOCH.encode() + b"\0" + regime.encode() + b"\0" + SCHEDULE_CONTEXT.encode()
        digest = hashlib.sha256(selector).hexdigest()
        initial = int.from_bytes(bytes.fromhex(digest), "big") % len(candidates)
        selected = initial
        while selected in used:
            selected = (selected + 1) % len(candidates)
        used.add(selected)
        allocation[regime] = {
            "selectorBytes": f"{EPOCH}\\0{regime}\\0{SCHEDULE_CONTEXT}",
            "selectorSha256": digest,
            "initialCandidateIndex": initial,
            "selectedCandidateIndex": selected,
            "collisionIncrements": (selected - initial) % len(candidates),
            "blocks": [list(block) for block in candidates[selected]],
        }
    return allocation


def frozen_descriptor() -> dict[str, Any]:
    allocation = allocate_schedules()
    return {
        "schemaVersion": 1,
        "id": EPOCH,
        "status": DESIGN_LABEL,
        "module": "teastore",
        "targetHost": "fb14srv5",
        "source": {
            "sutCommit": SUT_COMMIT,
            "frameworkCommitPolicy": "full-clean-commit-at-materialization",
        },
        "workload": {
            "id": WORKLOAD,
            "kind": "fixed-open-loop",
            "journeysPerSecond": JOURNEYS_PER_SECOND,
            "concurrency": CONCURRENCY,
            "population": "login, home, up-to-3-categories, up-to-3-products-per-category, home",
            "excludedActions": ["cart", "checkout", "confirmation"],
            "journeyLedger": {
                "appendOnly": True,
                "oneRowPerOfferedJourney": True,
                "requiredFields": [
                    "recordType", "recordSequence", "previousRecordSha256", "recordSha256",
                    "planSha256", "workloadId", "barrierId", "sequence", "journeyId",
                    "opportunityId", "opaqueToken", "tokenAllocatedAt", "scheduledAt",
                    "scheduledMonotonicOffsetSeconds", "actualStartMonotonic",
                    "actualEndMonotonic", "startedAt", "endedAt", "expectedPath",
                    "requests", "requestCount", "outcome", "errors", "terminalSettled",
                    "endedAfterNominalWindow",
                ],
                "requestRequiredFields": [
                    "sequence", "step", "routeId", "target", "actualStartMonotonic",
                    "actualEndMonotonic", "startedAt", "endedAt", "latencyMs",
                    "statusCode", "outcome", "error",
                ],
            },
        },
        "design": {
            "postures": list(POSTURES),
            "selectedSource": "fault-qualification",
            "regimes": [
                {"id": "no-fault-cost", "kind": "cost", "fault": None,
                 "artifactRootClass": "cost"},
                {"id": "auth-freeze-effect", "kind": "effect", "fault": "auth-freeze",
                 "artifactRootClass": "effect/auth-freeze"},
                {"id": "persistence-crash-effect", "kind": "effect",
                 "fault": "persistence-crash",
                 "artifactRootClass": "effect/persistence-crash"},
            ],
            "blocksPerRegime": BLOCKS_PER_REGIME,
            "runsPerBlock": RUNS_PER_BLOCK,
            "totalRuns": TOTAL_RUNS,
            "coldStartEachRun": True,
            "deploymentQueueAttemptArtifactReuse": False,
            "costAndEffectPoolable": False,
        },
        "timing": {
            "warmupSeconds": WARMUP_SECONDS,
            "measurementSeconds": MEASUREMENT_SECONDS,
            "offeredJourneysPerRun": OFFERED_PER_RUN,
            "offeredJourneysTotal": OFFERED_TOTAL,
            "faultOnsetSeconds": FAULT_ONSET_SECONDS,
            "interventionHoldSeconds": INTERVENTION_HOLD_SECONDS,
            "minimumActualJourneyStartsPerPhase": MINIMUM_PHASE_STARTS,
            "phaseNames": ["pre", "during", "post"],
            "phaseAssignmentSource": "observed-intervention-and-readiness-monotonic-times",
            "sharedBarrierParticipants": ["workload", "resource-probe", "collector", "intervention"],
            "minimumTimedSeconds": MINIMUM_TIMED_SECONDS,
            "minimumTimedHours": 5.4,
            "operationalEstimateSeconds": OPERATIONAL_ESTIMATE_SECONDS,
            "lifecycleIncludedInMinimum": False,
        },
        "schedule": {
            "version": SCHEDULE_CONTEXT,
            "selectorEncoding": "UTF-8(epoch || NUL || regime || NUL || schedule-v1)",
            "integerEncoding": "unsigned-big-endian",
            "candidateRule": "six-first-rows-each-left-then-right-rotation",
            "firstRows": [list(row) for row in BASE_ROWS],
            "collisionRule": "increment-modulo-12-until-unused",
            "regimeOrder": list(REGIMES),
            "receipts": [
                {
                    "regime": regime,
                    "selectorSha256": allocation[regime]["selectorSha256"],
                    "initialCandidateIndex": allocation[regime]["initialCandidateIndex"],
                    "selectedCandidateIndex": allocation[regime]["selectedCandidateIndex"],
                    "collisionIncrements": allocation[regime]["collisionIncrements"],
                    "blocks": allocation[regime]["blocks"],
                }
                for regime in REGIMES
            ],
        },
        "runIdentity": {
            "fields": ["studyEpoch", "regime", "block", "posture", "attempt"],
            "initialAttempt": 1,
            "attemptBeginsBeforeFirstExternalMutation": True,
            "retryMayReplaceCell": False,
            "diagnosticRerunMayRestoreComparativeEligibility": False,
            "maximumLaterDiagnosticAttempts": 1,
        },
        "groundTruth": {
            "fault": {
                "source": "controller-and-target-state-probes-independent-of-kieker",
                "requiredReceiptFields": [
                    "schemaVersion", "scenario", "service", "independentOfKieker",
                    "intervalLabel", "functionalOutage", "measurementBarrier",
                    "requestedHoldSeconds", "targetContainerId", "targetImage", "preState",
                    "commandVector", "commandResult", "actualOnsetWall",
                    "actualOnsetMonotonicOffsetSeconds", "actualOffsetWall",
                    "actualOffsetMonotonicOffsetSeconds", "duringStateSamples",
                    "recoveryAction", "sameTargetIdentity", "readiness", "postState",
                    "interventionThreadJoined", "laterInterventionMutationObserved",
                    "manifested", "recovered", "outageHeld", "successful", "error",
                    "operational",
                ],
                "intervalLabel": "intervention-exposure",
                "functionalOutageWithoutContinuousWitness": None,
                "scenarioContracts": [
                    {
                        "scenario": "auth-freeze", "service": "auth",
                        "containerIdentityRule": "same-container-pre-during-post",
                        "commandFamily": "docker-pause-unpause",
                        "prePredicate": "running-and-unpaused",
                        "duringPredicate": "running-and-paused",
                        "postPredicate": "running-and-unpaused",
                    },
                    {
                        "scenario": "persistence-crash", "service": "persistence",
                        "containerIdentityRule": "same-container-pre-during-post",
                        "commandFamily": "docker-stop-start",
                        "prePredicate": "running",
                        "duringPredicate": "stopped",
                        "postPredicate": "running-and-ready",
                    },
                ],
                "commandSuccessAloneEstablishesTruth": False,
                "failedManifestationOrRecovery": "invalid-and-safety-stop",
            },
            "path": {
                "opportunitySource": "offered-schedule-before-scored-telemetry",
                "opportunityWorkload": WORKLOAD,
                "expectedOpportunityIsExecutionProof": False,
                "scoredPhases": ["pre", "post-readiness"],
                "duringFaultOpportunitiesReportedSeparately": True,
                "requiredSensors": ["operation:auth", "operation:persistence"],
                "requiredEdge": "auth->persistence",
                "directEdgePredicate": (
                    "persistence.parentId == auth.spanId in same original native trace"
                ),
                "executedDenominator": "independent-application-side-witness",
                "correlation": "pre-outcome-opaque-token-one-to-one-original-native-trace",
                "tokenContractFrozenBeforeOutcomes": True,
                "tokenContractRequiredCoverage": [
                    "generation", "login-request-injection", "application-witness-extraction",
                    "native-trace-extraction", "uniqueness", "one-to-one-mapping",
                ],
                "missingWitnessOrCorrelationState": "unsupported",
                "missingWitnessOrCorrelationValue": None,
                "crossTraceAssemblyAllowed": False,
                "noneZeroRequires": [
                    "independently-proven-executed-opportunity",
                    "terminal-complete-hash-reconciled-empty-capture",
                ],
            },
        },
        "outcomes": {
            "offeredJourneysAreDenominator": True,
            "latencyPopulation": "successful-journeys-only",
            "emptyLatencyValue": None,
            "costRegimeOnly": "no-fault-cost",
            "primaryCostEndpoint": "sampled-application-cpu-seconds-proxy-per-offered-journey",
            "retainedTraceBytesAreWireBytes": False,
            "effectResourcesAreCostEstimates": False,
            "windowMembership": "native-event-timestamps-clipped-to-shared-interval",
            "collectorTailUse": "diagnostic-only",
        },
        "systemSamples": {
            "artifact": "system-samples.json",
            "kind": "teastore-system-samples-v1",
            "collector": "modules/teastore/collectors/system_probe.py",
            "source": "cgroup-v2-per-container-scope-and-docker-containerd-units",
            "cells": "every-cell-cost-and-effect",
            "intervalSeconds": 5,
            "samplesPerRun": 121,
            "sharedBarrierParticipant": False,
            "requiredServicesAtFirstSample": ["auth", "image", "persistence", "recommender", "webui"],
            "noFaultNullSampleAllowed": False,
            "stoppedContainerValue": None,
            "faultWindowSamplesAreCostEstimates": False,
            "use": "detection-signal-only-in-effect-cells",
        },
        "postureProof": {
            "selected": {
                "selectionId": "fault-qualification",
                "requires": [
                    "goal-and-catalog-digests", "dependency-closure", "activation-manifest",
                    "exact-aop-bytes", "required-groups-present", "forbidden-groups-absent",
                ],
            },
            "none": {
                "requires": [
                    "kieker-disabled-before-jvm-start-all-application-services",
                    "exact-aop-bytes",
                ],
                "fixedSupportDisclosed": True,
                "zeroOperationalCostClaim": False,
            },
            "full": {
                "requires": [
                    "all-declared-groups-active", "exact-aop-bytes",
                    "goal-and-catalog-digests",
                ],
            },
        },
        "queueProof": {
            "requires": [
                "purge-with-zero-consumers", "zero-messages-at-measurement-barrier",
                "exactly-one-collector", "settled-drain", "complete-message-sha1",
                "complete-signature-sha1", "no-redelivered-message-body",
                "terminal-reconciliation",
            ],
            "manyRowsPerMessageAllowed": True,
            "postureLabelAloneProvesMaterialization": False,
        },
        "missingness": {
            "cellStates": [
                "valid", "invalid", "aborted", "not-started", "missing-artifact", "unsupported"
            ],
            "numericMissingValue": None,
            "failedAttemptsRetainedAndCharged": True,
            "silentRetryAllowed": False,
        },
        "analysis": {
            "comparativeUnit": "complete-(regime,block)",
            "descriptiveOnly": True,
            "report": ["raw-blocks", "paired-deltas", "ranges", "order-time-thermal-diagnostics"],
            "independentSequentialBlocksClaim": False,
            "directedCarryoverBalancedClaim": False,
            "forbidden": [
                "p-value", "confirmatory-interval", "carryover-adjusted-effect",
                "optimizer-front", "generality-claim", "observation-count-as-replication",
            ],
            "materialOrderOrThermalTrendResult": "unsupported",
        },
        "evidence": {
            "designLabel": DESIGN_LABEL,
            "diagnosticLabel": DIAGNOSTIC_LABEL,
            "maximumPilotLabel": CANDIDATE_LABEL,
            "canonical": False,
            "promotionRequiresSeparateHumanGate": True,
        },
        "continuation": {
            "outcomeTriggeredExtensionAllowed": False,
            "earlySuccessStopAllowed": False,
            "selectedRecompilationAllowed": False,
            "sixBlockContinuationRequiresNewPreOutcomeEpoch": True,
        },
    }


def _first_difference(expected: Any, actual: Any, path: str = "$") -> str | None:
    if type(expected) is not type(actual):  # bool must not pass as int
        return f"{path}: expected {type(expected).__name__}, got {type(actual).__name__}"
    if isinstance(expected, dict):
        if set(expected) != set(actual):
            missing = sorted(set(expected) - set(actual))
            unknown = sorted(set(actual) - set(expected))
            return f"{path}: field set differs; missing={missing}, unknown={unknown}"
        for key in expected:
            difference = _first_difference(expected[key], actual[key], f"{path}.{key}")
            if difference:
                return difference
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path}: expected {len(expected)} items, got {len(actual)}"
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            difference = _first_difference(expected_item, actual_item, f"{path}[{index}]")
            if difference:
                return difference
        return None
    if expected != actual:
        return f"{path}: expected {expected!r}, got {actual!r}"
    return None


def _verify_allocation(allocation: dict[str, dict[str, Any]]) -> None:
    for regime in REGIMES:
        expected = EXPECTED_SELECTION[regime]
        actual = allocation[regime]
        for field in ("selectorSha256", "initialCandidateIndex", "selectedCandidateIndex"):
            if actual[field] != expected[field]:
                raise ProtocolError(f"frozen selector mismatch for {regime}: {field}")
        if tuple(tuple(block) for block in actual["blocks"]) != expected["blocks"]:
            raise ProtocolError(f"frozen schedule mismatch for {regime}")


def validate_descriptor(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ProtocolError("descriptor must be a JSON object")
    allocation = allocate_schedules()
    _verify_allocation(allocation)
    difference = _first_difference(frozen_descriptor(), document)
    if difference:
        raise ProtocolError(f"descriptor differs from frozen candidate-pilot {EPOCH}: {difference}")
    return document


def compile_plan(document: Any) -> dict[str, Any]:
    descriptor = validate_descriptor(document)
    allocation = allocate_schedules()
    roots: list[dict[str, Any]] = []
    seen_run_ids: set[str] = set()
    for regime in REGIMES:
        blocks: list[dict[str, Any]] = []
        for block_number, order in enumerate(allocation[regime]["blocks"], start=1):
            if set(order) != set(POSTURES) or len(order) != len(POSTURES):
                raise ProtocolError(f"schedule block is not a posture permutation: {regime}/{block_number}")
            cells: list[dict[str, Any]] = []
            for position, posture in enumerate(order, start=1):
                run_id = f"{EPOCH}/{regime}/b{block_number:02d}/{posture}/a01"
                if run_id in seen_run_ids:
                    raise ProtocolError(f"duplicate run id: {run_id}")
                seen_run_ids.add(run_id)
                cells.append({
                    "runId": run_id,
                    "runKey": {
                        "studyEpoch": EPOCH, "regime": regime, "block": block_number,
                        "posture": posture, "attempt": 1,
                    },
                    "ordinalPosition": position,
                    "artifactRoot": (
                        f"{ARTIFACT_CLASSES[regime]}/block-{block_number:02d}/"
                        f"{posture}/attempt-01"
                    ),
                    "fault": FAULTS[regime],
                    "coldStart": True,
                    "selectionId": "fault-qualification" if posture == "selected" else None,
                    "scheduledState": "not-started",
                    "intendedEvidenceCeiling": CANDIDATE_LABEL,
                    "mayReplaceFailedCell": False,
                })
            blocks.append({
                "block": block_number,
                "comparativeUnit": [regime, block_number],
                "order": list(order),
                "completeRequired": True,
                "pairedContrastEligibleInitially": False,
                "cells": cells,
            })
        roots.append({
            "regime": regime,
            "artifactRootClass": ARTIFACT_CLASSES[regime],
            "fault": FAULTS[regime],
            "blocks": blocks,
        })
    if len(seen_run_ids) != TOTAL_RUNS:
        raise ProtocolError(f"compiled plan has {len(seen_run_ids)} runs, expected {TOTAL_RUNS}")
    return {
        "schemaVersion": 1,
        "kind": "candidate-pilot-plan",
        "studyEpoch": EPOCH,
        "descriptorId": descriptor["id"],
        "descriptorSha256": canonical_sha256(descriptor),
        "designEvidenceLabel": DESIGN_LABEL,
        "maximumRunEvidenceLabel": CANDIDATE_LABEL,
        "canonical": False,
        "runCount": TOTAL_RUNS,
        "minimumTimedSeconds": MINIMUM_TIMED_SECONDS,
        "operationalEstimateSeconds": dict(OPERATIONAL_ESTIMATE_SECONDS),
        "scheduleAllocation": allocation,
        "regimeRoots": roots,
        "analysisBoundary": copy.deepcopy(descriptor["analysis"]),
        "missingnessBoundary": copy.deepcopy(descriptor["missingness"]),
    }


def validate_plan(document: Any, plan: Any) -> dict[str, Any]:
    expected = compile_plan(document)
    if not isinstance(plan, dict):
        raise ProtocolError("compiled plan must be a JSON object")
    difference = _first_difference(expected, plan)
    if difference:
        raise ProtocolError(f"compiled plan differs from deterministic output: {difference}")
    return plan


def _aware_datetime(value: str | datetime, field: str) -> datetime:
    if isinstance(value, str):
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            result = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise AdmissionError(f"{field} must be an ISO-8601 timestamp") from exc
    elif isinstance(value, datetime):
        result = value
    else:
        raise AdmissionError(f"{field} must be a datetime or ISO-8601 string")
    if result.tzinfo is None or result.utcoffset() is None:
        raise AdmissionError(f"{field} must include a UTC offset")
    return result.astimezone(timezone.utc)


def _strict_nonnegative_int(value: Any, field: str, *, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise AdmissionError(f"{field} must be a {qualifier} integer")
    return value


def assess_time_window(
    document: Any,
    *,
    mode: str,
    evidence_label: str,
    now: str | datetime,
    authorization_deadline: str | datetime,
    time_budget_seconds: int,
    diagnostic_run_count: int = 1,
    diagnostic_warmup_seconds: int = 0,
    diagnostic_measurement_seconds: int = 60,
    lifecycle_allowance_seconds: int = 0,
) -> dict[str, Any]:
    """Return a non-authorizing time-window feasibility receipt or fail closed.

    Candidate mode reserves the upper end of the frozen 6--8 hour operational
    estimate.  Diagnostic mode is explicitly non-comparative and can use a
    shorter caller-supplied duration, but only under ``smoke-validation``.  A
    feasible result cannot launch either mode; candidate runtime authority can
    come only from the separately gated runtime adapter.
    """
    validate_descriptor(document)
    observed_now = _aware_datetime(now, "now")
    deadline = _aware_datetime(authorization_deadline, "authorization_deadline")
    budget = _strict_nonnegative_int(time_budget_seconds, "time_budget_seconds", positive=True)
    allowance = _strict_nonnegative_int(
        lifecycle_allowance_seconds, "lifecycle_allowance_seconds"
    )
    deadline_seconds = math.floor((deadline - observed_now).total_seconds())
    if deadline_seconds <= 0:
        raise AdmissionError("authorization deadline is not in the future")

    if mode == "candidate":
        if evidence_label != CANDIDATE_LABEL:
            raise AdmissionError(f"candidate execution requires evidence label {CANDIDATE_LABEL!r}")
        required_timed = MINIMUM_TIMED_SECONDS
        required_authorization = OPERATIONAL_ESTIMATE_SECONDS["upper"] + allowance
        run_count = TOTAL_RUNS
        warmup = WARMUP_SECONDS
        measurement = MEASUREMENT_SECONDS
        intended_comparative_execution = True
    elif mode == "diagnostic":
        if evidence_label != DIAGNOSTIC_LABEL:
            raise AdmissionError(
                f"short diagnostic execution requires evidence label {DIAGNOSTIC_LABEL!r}"
            )
        run_count = _strict_nonnegative_int(
            diagnostic_run_count, "diagnostic_run_count", positive=True
        )
        warmup = _strict_nonnegative_int(
            diagnostic_warmup_seconds, "diagnostic_warmup_seconds"
        )
        measurement = _strict_nonnegative_int(
            diagnostic_measurement_seconds, "diagnostic_measurement_seconds", positive=True
        )
        required_timed = run_count * (warmup + measurement)
        if required_timed >= MINIMUM_TIMED_SECONDS:
            raise AdmissionError("diagnostic request is not shorter than the frozen candidate pilot")
        required_authorization = required_timed + allowance
        intended_comparative_execution = False
    else:
        raise AdmissionError("mode must be 'candidate' or 'diagnostic'")

    blockers: list[str] = []
    if required_authorization > budget:
        blockers.append(
            f"required {required_authorization}s exceeds supplied time budget {budget}s"
        )
    if required_authorization > deadline_seconds:
        blockers.append(
            f"required {required_authorization}s exceeds {deadline_seconds}s until authorization deadline"
        )
    if blockers:
        raise AdmissionError("; ".join(blockers))

    return {
        "schemaVersion": 2,
        "kind": "time-window-feasibility",
        "studyEpoch": EPOCH,
        "descriptorSha256": canonical_sha256(document),
        "mode": mode,
        "evidenceLabel": evidence_label,
        "canonical": False,
        "feasible": True,
        "admitted": False,
        "runtimeAuthorized": False,
        "candidateEvidenceAuthorized": False,
        "now": observed_now.isoformat().replace("+00:00", "Z"),
        "authorizationDeadline": deadline.isoformat().replace("+00:00", "Z"),
        "suppliedTimeBudgetSeconds": budget,
        "secondsUntilDeadline": deadline_seconds,
        "requiredTimedSeconds": required_timed,
        "requiredAuthorizationSeconds": required_authorization,
        "lifecycleAllowanceSeconds": allowance,
        "runCount": run_count,
        "warmupSeconds": warmup,
        "measurementSeconds": measurement,
        "comparativeDesignRequested": intended_comparative_execution,
        "comparativeEligible": False,
        "mayReplaceCandidateCell": False,
        "promotionAuthorized": False,
        "requiresFreshGateRun": True,
        "deadlineWouldBeHardMutationCeilingIfAuthorized": True,
        "feasibilityDoesNotProveHarnessConformance": True,
        "unsupportedNumericValue": None,
    }


def admit_runtime(
    document: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Compatibility alias that never admits or authorizes runtime.

    Existing diagnostic evidence replayers still import this name.  Keeping the
    alias avoids making those retained receipts unreadable while its schema-v2
    result makes the construction ceiling explicit.
    """

    return assess_time_window(document, **kwargs)


def _write_json(value: Any, output: Path | None) -> None:
    rendered = json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    if output is None:
        sys.stdout.write(rendered)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with output.open("x", encoding="utf-8") as handle:
                handle.write(rendered)
        except FileExistsError as exc:
            raise ProtocolError(f"refusing to overwrite retained output: {output}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate the frozen descriptor/plan")
    validate.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    validate.add_argument("--plan", type=Path)

    descriptor_command = subparsers.add_parser(
        "descriptor", help="write the frozen descriptor that validate accepts")
    descriptor_command.add_argument("--output", type=Path)

    compile_command = subparsers.add_parser("compile", help="compile deterministic run plan")
    compile_command.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    compile_command.add_argument("--output", type=Path)

    window = subparsers.add_parser(
        "check-window", help="calculate non-authorizing time-window feasibility"
    )
    window.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    window.add_argument("--mode", choices=("candidate", "diagnostic"), required=True)
    window.add_argument("--evidence-label", required=True)
    window.add_argument("--now", required=True, help="timezone-aware ISO-8601 timestamp")
    window.add_argument("--authorization-deadline", required=True,
                       help="timezone-aware ISO-8601 timestamp")
    window.add_argument("--time-budget-seconds", type=int, required=True)
    window.add_argument("--diagnostic-run-count", type=int, default=1)
    window.add_argument("--diagnostic-warmup-seconds", type=int, default=0)
    window.add_argument("--diagnostic-measurement-seconds", type=int, default=60)
    window.add_argument("--lifecycle-allowance-seconds", type=int, default=0)
    window.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "descriptor":
            _write_json(validate_descriptor(frozen_descriptor()), args.output)
            return 0
        descriptor = strict_json_file(args.descriptor)
        if args.command == "validate":
            validate_descriptor(descriptor)
            result: dict[str, Any] = {
                "valid": True,
                "descriptorId": descriptor["id"],
                "descriptorSha256": canonical_sha256(descriptor),
            }
            if args.plan:
                validate_plan(descriptor, strict_json_file(args.plan))
                result["planValid"] = True
            _write_json(result, None)
        elif args.command == "compile":
            _write_json(compile_plan(descriptor), args.output)
        else:
            receipt = assess_time_window(
                descriptor,
                mode=args.mode,
                evidence_label=args.evidence_label,
                now=args.now,
                authorization_deadline=args.authorization_deadline,
                time_budget_seconds=args.time_budget_seconds,
                diagnostic_run_count=args.diagnostic_run_count,
                diagnostic_warmup_seconds=args.diagnostic_warmup_seconds,
                diagnostic_measurement_seconds=args.diagnostic_measurement_seconds,
                lifecycle_allowance_seconds=args.lifecycle_allowance_seconds,
            )
            _write_json(receipt, args.output)
    except (ProtocolError, AdmissionError) as exc:
        print(f"candidate-pilot: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
