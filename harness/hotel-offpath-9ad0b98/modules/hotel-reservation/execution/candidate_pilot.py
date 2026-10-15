#!/usr/bin/env python3
"""Compile the Hotel Reservation candidate-pilot contract without executing it.

This module has no executor or transport seam.  It validates one frozen,
construction-only descriptor and emits a deterministic plan that a future,
separately authorized runtime adapter may consume.  Stock ``sample-zero`` is
kept as an acquisition-negative control; it is never treated as ``none``,
``selected``, ``source-off``, or proof of source-work removal.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any, NoReturn


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DESCRIPTOR = (
    ROOT / "pipelines/campaigns/hotel-reservation-selected-v1.json"
)

# 2026-09-29 Hotel `selected` (research/hotel-selected/DECLARATION.md in the measurement repo):
# successor of the LMT+S pilot (lmt-pilot-20260928, 40682b7) on branch selected-20260929.
# lmt2 replays on 40682b7, Hotel #6 on 31d69af, not here.
EPOCH = "hotel-reservation-selected-v1"
SUT_COMMIT = "6ecb09706140f8730b5385c08f1386c654c3c526"
WORKLOAD = "hotel-search-v1"
# Nested by what is switched on: logs + the metric sampler, then the frontend tracer, then every tracer.
POSTURES = ("none", "metrics", "selected", "full")
LOG_LEVEL_BY_POSTURE = {"none": "fatal", "metrics": "info", "selected": "info", "full": "info"}
SAMPLER_POSTURES = ("metrics", "selected", "full")
APPLICATION_SERVICES = (
    "frontend", "search", "geo", "rate", "reservation", "profile",
    "user", "recommendation", "review", "attractions",
)
# `selected` = the placement derived from lmt2 (frontend spans catch every class any span catches there).
TRACED_SERVICES_BY_POSTURE = {
    "none": (), "metrics": (), "selected": ("frontend",), "full": APPLICATION_SERVICES,
}
TRACE_POSTURES = tuple(p for p in POSTURES if TRACED_SERVICES_BY_POSTURE[p])   # postures with any tracer on


def traces(posture: str, service: str) -> bool:
    """True when ``service`` runs a real tracer (ratio 1) in ``posture``; else NoopTracer, ratio 0."""
    return service in TRACED_SERVICES_BY_POSTURE[posture]
REGIMES = (
    "no-fault-cost",
    "search-pause-effect",
    "reservation-pause-effect",
    "cpu-throttle-effect",
    "net-delay-effect",
)
FAULTS = {
    "no-fault-cost": None,
    "search-pause-effect": "search-pause",
    "reservation-pause-effect": "reservation-pause",
    "cpu-throttle-effect": "profile-cpu-throttle",
    "net-delay-effect": "rate-net-delay",
}
PAUSE_FAULTS = ("search-pause", "reservation-pause")
FAULT_TARGETS = {
    "search-pause": "search", "reservation-pause": "reservation",
    "profile-cpu-throttle": "profile", "rate-net-delay": "rate",
}
CPU_THROTTLE_CPUS = "0.1"
NET_DELAY_MS = 100
ARTIFACT_ROOTS = {
    "no-fault-cost": "cost",
    "search-pause-effect": "effect/search-pause",
    "reservation-pause-effect": "effect/reservation-pause",
    "cpu-throttle-effect": "effect/cpu-throttle",
    "net-delay-effect": "effect/net-delay",
}
SCHEDULE_CONTEXT = "schedule-v1"

BLOCKS_PER_REGIME = 4
RUNS_PER_BLOCK = 4
TOTAL_RUNS = BLOCKS_PER_REGIME * RUNS_PER_BLOCK * len(REGIMES)
WARMUP_SECONDS = 30
MEASUREMENT_SECONDS = 120
REQUESTS_PER_SECOND = 10
CONCURRENCY = 16
OFFERED_PER_RUN = 1200
OFFERED_TOTAL = TOTAL_RUNS * OFFERED_PER_RUN
FAULT_ONSET_SECONDS = 45
FAULT_HOLD_SECONDS = 15
MINIMUM_PHASE_STARTS = 100
MINIMUM_TIMED_SECONDS = TOTAL_RUNS * (WARMUP_SECONDS + MEASUREMENT_SECONDS)
EXPECTED_DESCRIPTOR_SHA256 = (
    "4e8c19b8210b0a593ab94ed309c24f9799ae4b3408409c254fc475af11530f5c"
)
EXPECTED_PLAN_SHA256 = (
    "189604cc901f53207e16fed8c924b66dc6ba96cb61c0a3e8f706689ab8a5b4af"
)

NORMAL_SENSORS = (
    "span:frontend:HTTP GET /hotels",
    "span:search:/search.Search/Nearby",
    "span:geo:/geo.Geo/Nearby",
    "span:rate:/rate.Rate/GetRates",
    "span:reservation:/reservation.Reservation/CheckAvailability",
    "span:profile:/profile.Profile/GetProfiles",
)
NORMAL_EDGES = (
    ("frontend", "search"),
    ("search", "geo"),
    ("search", "rate"),
    ("frontend", "reservation"),
    ("frontend", "profile"),
)


class ProtocolError(ValueError):
    """The descriptor or compiled plan differs from the frozen contract."""


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


FIRST_POSITIONS_PER_POSTURE = 1


def schedule_candidates() -> tuple[tuple[tuple[str, ...], ...], ...]:
    """Return every block schedule in which each posture is first exactly ``FIRST_POSITIONS_PER_POSTURE`` times.

    LMT+S pilot: four postures, four blocks, one first position each, so 4! = 24 candidates
    and a 4x4 Latin square per regime.  The v1 text below describes the Hotel #6 shape.

    The preregistered balancing property is position balance of the *first*
    cell: with ``BLOCKS_PER_REGIME == FIRST_POSITIONS_PER_POSTURE * len(POSTURES)``
    each posture opens exactly two blocks.  Within a block the postures follow
    the cyclic rotation of ``POSTURES`` that starts at the first posture, so a
    candidate is fully determined by its first-position sequence and every
    posture occupies every position exactly ``FIRST_POSITIONS_PER_POSTURE`` times
    per regime (a Latin-square balance).  With two postures and four blocks the
    rotation is simply "the other posture" and this is the original six-candidate
    set; with three postures and six blocks it is the 6!/(2!2!2!) = 90 distinct
    first-position sequences.
    """
    if BLOCKS_PER_REGIME != FIRST_POSITIONS_PER_POSTURE * len(POSTURES):
        raise ProtocolError("blocks per regime must give every posture exactly one first position")
    if RUNS_PER_BLOCK != len(POSTURES):
        raise ProtocolError("every block must contain each posture exactly once")
    multiset = tuple(itertools.chain.from_iterable(
        (posture,) * FIRST_POSITIONS_PER_POSTURE for posture in POSTURES
    ))
    first_sequences = sorted(set(itertools.permutations(multiset)))
    candidates = []
    for sequence in first_sequences:
        candidates.append(tuple(
            tuple(
                POSTURES[(POSTURES.index(first) + offset) % len(POSTURES)]
                for offset in range(len(POSTURES))
            )
            for first in sequence
        ))
    return tuple(candidates)


def allocate_schedules() -> dict[str, dict[str, Any]]:
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
            "selectorSha256": digest,
            "initialCandidateIndex": initial,
            "selectedCandidateIndex": selected,
            "collisionIncrements": (selected - initial) % len(candidates),
            "blocks": [list(block) for block in candidates[selected]],
        }
    return allocation


def _normal_path() -> dict[str, Any]:
    return {
        "id": "hotel-search-normal-v1",
        "requiredSensors": list(NORMAL_SENSORS),
        "requiredServiceEdges": [list(edge) for edge in NORMAL_EDGES],
        "oneOriginalNativeTraceRequired": True,
        "crossTraceAssemblyAllowed": False,
    }


def frozen_descriptor() -> dict[str, Any]:
    allocation = allocate_schedules()
    return {
        "schemaVersion": 1,
        "id": EPOCH,
        "status": "method-design-only",
        "module": "hotel-reservation",
        "source": {
            "sutCommit": SUT_COMMIT,
            "frameworkCommitPolicy": "full-clean-commit-at-materialization",
        },
        "workload": {
            "id": WORKLOAD,
            "kind": "fixed-open-loop",
            "method": "GET",
            "route": "/hotels",
            "requestsPerSecond": REQUESTS_PER_SECOND,
            "concurrency": CONCURRENCY,
            "opportunityLedger": {
                "appendOnly": True,
                "oneRowPerOfferedRequest": True,
                "allocatedBeforeTelemetry": True,
                "requiredFields": [
                    "recordSequence", "previousRecordSha256", "recordSha256",
                    "planSha256", "workloadId", "barrierId", "sequence",
                    "opportunityId", "opaqueToken", "scheduledAt",
                    "scheduledMonotonicOffsetSeconds", "actualStartMonotonic",
                    "actualEndMonotonic", "startedAt", "endedAt", "outcome",
                    "statusCode", "error", "terminalSettled",
                ],
            },
        },
        "design": {
            "postures": list(POSTURES),
            "postureRoles": {
                "none": "logs-fatal-sampler-off-tracer-disabled",
                "metrics": "logs-info-sampler-on-tracer-disabled",
                "selected": "logs-info-sampler-on-tracer-frontend-only",
                "full": "logs-info-sampler-on-tracer-full-sampling",
            },
            "unsupportedPostures": [
                {"id": "source-off", "state": "unsupported", "numericValue": None},
            ],
            "regimes": [
                {"id": regime,
                 "kind": "cost-characterization" if FAULTS[regime] is None else "effect",
                 "fault": FAULTS[regime], "artifactRootClass": ARTIFACT_ROOTS[regime]}
                for regime in REGIMES
            ],
            "blocksPerRegime": BLOCKS_PER_REGIME,
            "runsPerBlock": RUNS_PER_BLOCK,
            "totalRuns": TOTAL_RUNS,
            "coldStartEachRun": True,
            "costAndEffectPoolable": False,
            "faultAppliedToEveryEffectCell": True,
        },
        "timing": {
            "warmupSeconds": WARMUP_SECONDS,
            "measurementSeconds": MEASUREMENT_SECONDS,
            "offeredRequestsPerRun": OFFERED_PER_RUN,
            "offeredRequestsTotal": OFFERED_TOTAL,
            "faultOnsetSeconds": FAULT_ONSET_SECONDS,
            "faultHoldSeconds": FAULT_HOLD_SECONDS,
            "minimumActualRequestStartsPerPhase": MINIMUM_PHASE_STARTS,
            "nominalScheduledStartsByPhase": {
                "pre": 450, "during": 150, "post-readiness": 600,
            },
            "phaseNames": ["pre", "during", "post-readiness"],
            "phaseAssignmentSource": "observed-intervention-and-readiness-monotonic-times",
            "separateArtifactRootsRequired": True,
            "costWindowContainsFault": False,
            "effectWindowMaySupplyCostEstimate": False,
            "minimumTimedSeconds": MINIMUM_TIMED_SECONDS,
            "windowContracts": {
                "no-fault-cost": {
                    "kind": "single-no-fault-measurement-window",
                    "fault": None,
                    "phaseNames": [],
                    "denominator": "offered-request-ledger-rows-in-shared-window",
                },
                "fault-effect": {
                    "kind": "observed-intervention-phase-windows",
                    "regimes": [regime for regime in REGIMES if FAULTS[regime]],
                    "phaseNames": ["pre", "during", "post-readiness"],
                    "denominator": (
                        "independently-witnessed-executed-opportunities-per-phase"
                    ),
                },
            },
        },
        "schedule": {
            "version": SCHEDULE_CONTEXT,
            "selectorEncoding": "UTF-8(epoch || NUL || regime || NUL || schedule-v1)",
            "candidateRule": (
                f"all-{BLOCKS_PER_REGIME}-block-{FIRST_POSITIONS_PER_POSTURE}-first-position-"
                "each-posture-cyclic-rotation-within-block"
            ),
            "collisionRule": f"increment-modulo-{len(schedule_candidates())}-until-unused",
            "regimeOrder": list(REGIMES),
            "receipts": [
                {"regime": regime, **allocation[regime]}
                for regime in REGIMES
            ],
        },
        "runIdentity": {
            "fields": ["studyEpoch", "regime", "block", "posture", "attempt"],
            "initialAttempt": 1,
            "attemptBeginsBeforeExternalMutation": True,
            "retryMayReplaceCell": False,
            "failedAttemptsRetainedAndCharged": True,
        },
        "groundTruth": {
            "fault": {
                "source": "controller-target-state-and-route-probes-independent-of-jaeger",
                "commandSuccessAloneEstablishesTruth": False,
                "failedManifestationOrRecovery": "invalid-and-safety-stop",
                "scenarioContracts": [
                    {
                        "scenario": "profile-cpu-throttle", "service": "profile",
                        "prePredicate": "running-and-unthrottled",
                        "duringPredicate": f"running-and-nanocpus-{CPU_THROTTLE_CPUS}",
                        "postPredicate": "running-and-unthrottled-and-route-ready",
                        "prePathTruth": "hotel-search-normal-v1",
                        "duringPathTruth": "hotel-search-normal-v1",
                        "postReadinessPathTruth": "hotel-search-normal-v1",
                    },
                    {
                        "scenario": "rate-net-delay", "service": "rate",
                        "prePredicate": "running-and-no-qdisc",
                        "duringPredicate": f"running-and-netem-delay-{NET_DELAY_MS}ms",
                        "postPredicate": "running-and-no-qdisc-and-route-ready",
                        "prePathTruth": "hotel-search-normal-v1",
                        "duringPathTruth": "hotel-search-normal-v1",
                        "postReadinessPathTruth": "hotel-search-normal-v1",
                    },
                    {
                        "scenario": "search-pause", "service": "search",
                        "prePredicate": "running-and-unpaused",
                        "duringPredicate": "running-and-paused-and-route-fails",
                        "postPredicate": "running-and-unpaused-and-route-ready",
                        "prePathTruth": "hotel-search-normal-v1",
                        "duringPathTruth": "hotel-search-search-pause-prefix-v1",
                        "postReadinessPathTruth": "hotel-search-normal-v1",
                    },
                    {
                        "scenario": "reservation-pause", "service": "reservation",
                        "prePredicate": "running-and-unpaused",
                        "duringPredicate": "running-and-paused-and-route-fails",
                        "postPredicate": "running-and-unpaused-and-route-ready",
                        "prePathTruth": "hotel-search-normal-v1",
                        "duringPathTruth": "hotel-search-reservation-pause-prefix-v1",
                        "postReadinessPathTruth": "hotel-search-normal-v1",
                    },
                ],
            },
            "path": {
                "normal": _normal_path(),
                "faultSpecific": [
                    {
                        "id": "hotel-search-search-pause-prefix-v1",
                        "fault": "search-pause",
                        "targetService": "search",
                        "requiredAttemptedPrefix": ["frontend", "search"],
                        "downstreamNotRequiredDuringFault": [
                            "search->geo", "search->rate", "frontend->reservation",
                            "frontend->profile",
                        ],
                        "nativeOperationQualification": "unsupported-until-runtime-characterization",
                        "numericValueWhenUnsupported": None,
                    },
                    {
                        "id": "hotel-search-reservation-pause-prefix-v1",
                        "fault": "reservation-pause",
                        "targetService": "reservation",
                        "requiredAttemptedPrefix": [
                            "frontend", "search", "geo", "rate", "reservation"
                        ],
                        "downstreamNotRequiredDuringFault": ["frontend->profile"],
                        "nativeOperationQualification": "unsupported-until-runtime-characterization",
                        "numericValueWhenUnsupported": None,
                    },
                ],
                "opportunitySource": "offered-request-ledger-before-scored-telemetry",
                "executedDenominator": "independent-application-side-witness",
                "expectedOpportunityIsExecutionProof": False,
                "correlation": "opaque-token-one-to-one-original-native-trace",
                "tokenContractRequiredCoverage": [
                    "generation", "request-injection", "application-witness-extraction",
                    "native-trace-extraction", "uniqueness", "one-to-one-mapping",
                ],
                "missingWitnessOrCorrelationState": "unsupported",
                "missingWitnessOrCorrelationValue": None,
                "sampleZeroFalseRequires": [
                    "independently-proven-executed-opportunity",
                    "terminal-complete-empty-capture",
                ],
            },
        },
        "outcomes": {
            "offeredRequestsAreDenominator": True,
            "costRegimeOnly": "no-fault-cost",
            "sourceCostComparisonState": "unsupported",
            "sourceCostComparisonValue": None,
            "sourceCostUnsupportedReason": "no-posture-is-source-off",
            "retainedTraceBytesAreWireBytes": False,
            "effectResourcesAreCostEstimates": False,
            "emptyLatencyValue": None,
            "windowMembership": "native-event-timestamps-clipped-to-shared-interval",
            "collectorTailUse": "diagnostic-only",
        },
        "postureProof": {
            posture: {
                "sourceWorkDisabled": False,
                "logLevel": LOG_LEVEL_BY_POSTURE[posture],
                "metricSampler": posture in SAMPLER_POSTURES,
                "requires": (
                    ["sample-ratio-one-all-declared-services", "immutable-image-ids"]
                    if posture == "full" else
                    ["sample-ratio-one-frontend", "jaeger-disabled-other-declared-services",
                     "immutable-image-ids"]
                    if posture == "selected" else [
                        "jaeger-disabled-all-declared-services",
                        "sample-ratio-zero-all-declared-services",
                        "terminal-complete-empty-capture",
                    ]
                ) + [f"log-level-{LOG_LEVEL_BY_POSTURE[posture]}-all-declared-services"],
            }
            for posture in POSTURES
        },
        "collection": {
            "logLevelByPosture": dict(LOG_LEVEL_BY_POSTURE),
            "metricSamplerPostures": list(SAMPLER_POSTURES),
            "metricSamplerIntervalSeconds": 1,
            "tracePostures": list(TRACE_POSTURES),
            "tracedServicesByPosture": {p: list(TRACED_SERVICES_BY_POSTURE[p]) for p in POSTURES},
            "alwaysOn": [
                "request-witness-stdout", "docker-events-stream",
                "system-sampler-cgroup-5s", "cost-cgroup-cpu-window-edges",
            ],
            "costAxis": "cgroup-cpu-usage-delta-ten-app-containers-plus-docker-and-containerd",
            "alwaysOnCostMeasured": False,
        },
        "faultParameters": {
            "targets": dict(FAULT_TARGETS),
            "cpuThrottleCpus": CPU_THROTTLE_CPUS,
            "netDelayMilliseconds": NET_DELAY_MS,
            "netDelayMechanism": "sudo-nsenter-net-tc-netem-on-eth0",
            "cpuThrottleMechanism": "docker-update-cpus",
            "windowEdges": "post-apply-command-to-pre-revert-command",
        },
        "missingness": {
            "cellStates": [
                "valid", "invalid", "aborted", "not-started",
                "missing-artifact", "unsupported",
            ],
            "abstentionState": "unsupported",
            "abstentionNumericValue": None,
            "numericMissingValue": None,
            "silentRetryAllowed": False,
        },
        "analysis": {
            "comparativeUnit": "complete-(regime,block)",
            "descriptiveOnly": True,
            "positionBalanced": True,
            "independentSequentialBlocksClaim": False,
            "forbidden": [
                "source-off-claim", "selected-posture-claim", "source-cost-effect",
                "p-value", "confirmatory-interval", "optimizer-front",
                "observation-count-as-replication",
            ],
        },
        "evidence": {
            "designLabel": "method-design-only",
            "maximumSupportedFutureLabel": "candidate-evidence",
            "placementOrSourceCostEligible": False,
            "canonical": False,
            "promotionRequiresSeparateHumanGate": True,
        },
        "transport": {
            "executor": None,
            "transport": None,
            "runtimeAllowed": False,
            "externalMutationAllowed": False,
            "runtimeAdapterState": "absent-by-design",
        },
    }


def _assert_exact(expected: Any, actual: Any, path: str = "$") -> None:
    if type(actual) is not type(expected):
        raise ProtocolError(
            f"{path}: expected {type(expected).__name__}, found {type(actual).__name__}"
        )
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            missing = sorted(set(expected) - set(actual))
            unknown = sorted(set(actual) - set(expected))
            raise ProtocolError(f"{path}: key mismatch missing={missing} unknown={unknown}")
        for key in expected:
            _assert_exact(expected[key], actual[key], f"{path}.{key}")
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ProtocolError(f"{path}: expected {len(expected)} items, found {len(actual)}")
        for index, value in enumerate(expected):
            _assert_exact(value, actual[index], f"{path}[{index}]")
    elif actual != expected:
        raise ProtocolError(f"{path}: expected {expected!r}, found {actual!r}")


def validate_descriptor(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ProtocolError("descriptor must contain one JSON object")
    _assert_exact(frozen_descriptor(), document)
    return document


def load_descriptor(path: Path = DEFAULT_DESCRIPTOR) -> dict[str, Any]:
    """Load the checked-in contract and prove its reviewed canonical digest."""
    document = validate_descriptor(strict_json_file(path))
    digest = canonical_sha256(document)
    if digest != EXPECTED_DESCRIPTOR_SHA256:
        raise ProtocolError(
            "descriptor canonical digest differs from the reviewed freeze: "
            f"expected {EXPECTED_DESCRIPTOR_SHA256}, found {digest}"
        )
    return document


def compile_plan(document: Any) -> dict[str, Any]:
    descriptor = validate_descriptor(document)
    roots = []
    receipts = {item["regime"]: item for item in descriptor["schedule"]["receipts"]}
    for regime in REGIMES:
        blocks = []
        for block_number, order in enumerate(receipts[regime]["blocks"], start=1):
            cells = []
            for position, posture in enumerate(order, start=1):
                run_id = f"{regime}-b{block_number:02d}-{posture}-a01"
                cells.append({
                    "runId": run_id,
                    "runKey": {
                        "studyEpoch": EPOCH,
                        "regime": regime,
                        "block": block_number,
                        "posture": posture,
                        "attempt": 1,
                    },
                    "position": position,
                    "artifactRoot": (
                        f"{ARTIFACT_ROOTS[regime]}/b{block_number:02d}/"
                        f"p{position:02d}-{posture}/attempt-01"
                    ),
                    "fault": FAULTS[regime],
                    "postureRole": descriptor["design"]["postureRoles"][posture],
                    "scheduledState": "not-started",
                    "candidateCellEligible": False,
                    "runtimeAdapter": None,
                })
            blocks.append({
                "block": block_number,
                "order": order,
                "cells": cells,
                "comparativeState": (
                    "unsupported-source-cost" if regime == "no-fault-cost"
                    else "not-started"
                ),
            })
        roots.append({
            "regime": regime,
            "artifactRootClass": ARTIFACT_ROOTS[regime],
            "analysisKind": (
                "cost-characterization" if regime == "no-fault-cost" else "effect"
            ),
            "fault": FAULTS[regime],
            "blocks": blocks,
        })
    body = {
        "schemaVersion": 1,
        "studyEpoch": EPOCH,
        "descriptorCanonicalSha256": canonical_sha256(descriptor),
        "runCount": TOTAL_RUNS,
        "minimumTimedSeconds": MINIMUM_TIMED_SECONDS,
        "runtimeAllowed": False,
        "externalMutationAllowed": False,
        "transport": None,
        "canonical": False,
        "placementOrSourceCostEligible": False,
        "regimeRoots": roots,
        "unsupportedPostures": descriptor["design"]["unsupportedPostures"],
        "missingnessBoundary": descriptor["missingness"],
        "groundTruthBoundary": descriptor["groundTruth"],
        "outcomeBoundary": descriptor["outcomes"],
        "analysisBoundary": descriptor["analysis"],
    }
    plan_digest = canonical_sha256(body)
    if plan_digest != EXPECTED_PLAN_SHA256:
        raise ProtocolError(
            "compiled plan digest differs from the reviewed freeze: "
            f"expected {EXPECTED_PLAN_SHA256}, found {plan_digest}"
        )
    return {**body, "planCanonicalSha256": plan_digest}


def validate_plan(plan: Any, descriptor: Any) -> dict[str, Any]:
    expected = compile_plan(descriptor)
    _assert_exact(expected, plan)
    body = {key: value for key, value in plan.items() if key != "planCanonicalSha256"}
    if plan["planCanonicalSha256"] != canonical_sha256(body):
        raise ProtocolError("compiled plan digest mismatch")
    return plan


def readiness_report(document: Any, plan: Any) -> dict[str, Any]:
    """Return a pure construction receipt; never imply runtime authorization."""
    descriptor = validate_descriptor(document)
    compiled = validate_plan(plan, descriptor)
    return {
        "schemaVersion": 1,
        "studyEpoch": EPOCH,
        "constructionReady": True,
        "descriptorCanonicalSha256": canonical_sha256(descriptor),
        "planCanonicalSha256": compiled["planCanonicalSha256"],
        "runCount": compiled["runCount"],
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


def write_plan(path: Path, plan: dict[str, Any]) -> None:
    payload = json.dumps(plan, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ProtocolError(f"refusing to change immutable plan: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        descriptor = load_descriptor(args.descriptor)
        plan = compile_plan(descriptor)
        if args.output is not None:
            write_plan(args.output, plan)
    except ProtocolError as exc:
        parser.error(str(exc))
    print(json.dumps({
        "studyEpoch": plan["studyEpoch"],
        "descriptorCanonicalSha256": plan["descriptorCanonicalSha256"],
        "planCanonicalSha256": plan["planCanonicalSha256"],
        "runCount": plan["runCount"],
        "runtimeAllowed": plan["runtimeAllowed"],
        "placementOrSourceCostEligible": plan["placementOrSourceCostEligible"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
