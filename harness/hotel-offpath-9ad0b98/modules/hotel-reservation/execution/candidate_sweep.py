#!/usr/bin/env python3
"""Compile the Hotel traffic-sweep epoch (hotel-traffic-sweep-v1) without executing it.

A second, separate epoch beside the frozen ``candidate_pilot.py`` (hotel-reservation-selected-v1, plan
189604cc...), which this file never changes.  Here request rate, measurement length, fault onset, hold and
the offered count are per-cell plan values: every compiled cell carries a ``timing`` block, and the cell
runner, the workload, the witness and the terminal validator read the cell's timing instead of the frozen
epoch's literals.  Proposal: research/traffic-sweep/DECLARATION_DRAFT.md (measurement repo; a draft,
not frozen).  Every value below the "parameters" line is a declaration proposal with that draft's
default; changing one changes the descriptor and plan digests, by design.

Runs as ``python3 -I`` on CPython 3.9 on the target: standard library only, sibling files are loaded by
path (``-I`` drops this directory from ``sys.path``), no PEP 604 annotation evaluated at runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


HERE = Path(__file__).resolve().parent
MODULE = HERE.parent
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DESCRIPTOR = ROOT / "pipelines/campaigns/hotel-traffic-sweep-v1.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The frozen epoch supplies the posture vocabulary, the ground truth and the JSON helpers; it is read, never
# edited, and its own digests stay pinned in its own file.  The vendored protocol gates supply need() and the
# gate thresholds, so the phase floors here are the gates' own rule, not a second copy of it.
frozen = _load("hotel_sweep_frozen_compiler", HERE / "candidate_pilot.py")
gates = _load("hotel_sweep_protocol_gates", MODULE / "validation" / "protocol_gates.py")
ProtocolError = frozen.ProtocolError
canonical_sha256 = frozen.canonical_sha256
strict_json_file = frozen.strict_json_file

EPOCH = "hotel-traffic-sweep-v1"
SUT_COMMIT = frozen.SUT_COMMIT
WORKLOAD = frozen.WORKLOAD

# ---------------------------------------------------------------- parameters (declaration draft defaults)
POSTURES = ("full",)
RATES = (10.0, 1.0, 0.2, 0.05)                 # requests per second; inter-arrival 0.1, 1, 5, 20 s
WARMUP_SECONDS = 30
WARMUP_REQUESTS_PER_SECOND = 10.0              # every cell warms up at 10/s (user 2026-10-03): warming at the
                                               # cell's rate gives 1-2 requests at 0.05/s and confounds rate with warmth
MEASUREMENT_SECONDS = 180
FAULT_ONSET_BASE_SECONDS = 60                  # the seeded phase offset below is added per cell
FAULT_HOLD_SECONDS = 60
# 60 s is a multiple of every planned inter-arrival, so without an offset every onset falls on a scheduled
# request and the first request after onset sits exactly one inter-arrival later: time to detection at low
# rate would be set by the plan, not measured.  Stratified (user 2026-10-03): the EPISODES blocks of one
# (regime, rate) pair take the EPISODES equal strata of one inter-arrival in a seeded order, and the position
# inside a stratum is a seeded uniform draw, so the four episodes always span the whole inter-arrival.
ONSET_PHASE_OFFSET = "seeded-stratified-within-one-inter-arrival"   # or "none" to restore the bare base onset
ONSET_PHASE_OFFSETS = ("seeded-stratified-within-one-inter-arrival", "none")
# The first cell of block 1 is fixed (user 2026-10-03): a 60 s pause at 10/s had never run, so it goes first
# and its capture is checked while the campaign continues; the other 15 cells of block 1 keep their shuffle.
LEAD_CELL = ("search-pause-effect", 10.0)
REQUEST_TIMEOUT_SECONDS = 1.0                  # the frozen epoch's per-request client timeout
CONCURRENCY = 16
EPISODES = 4                                   # per (regime, rate); block b holds episode b of every pair
SCHEDULE_SEED = 20261003
REGIMES = (
    "no-fault-calibration",
    "search-pause-effect",
    "cpu-throttle-effect",
    "net-delay-effect",
)
FAULTS = {
    "no-fault-calibration": None,
    "search-pause-effect": "search-pause",
    "cpu-throttle-effect": "profile-cpu-throttle",
    "net-delay-effect": "rate-net-delay",
}
ARTIFACT_ROOTS = {
    "no-fault-calibration": "calibration",
    "search-pause-effect": "effect/search-pause",
    "cpu-throttle-effect": "effect/cpu-throttle",
    "net-delay-effect": "effect/net-delay",
}
# TCP snapshots keep the frozen epoch's placement relative to onset (45 - 15 = 30, 45 + 7 = 52).
TCP_PRE_FAULT_LEAD_SECONDS = 15
TCP_DURING_FAULT_LAG_SECONDS = 7
POST_RECOVERY_ALLOWANCE_SECONDS = 2.0          # witness settle (1 s) + unpause/readiness round trip
JAEGER_TAIL_SECONDS = 5                        # frozen: query window = measurement + 5 s
SYSTEM_SAMPLE_INTERVAL_SECONDS = 5             # collectors/system_state.py SAMPLE_INTERVAL_SECONDS
# Wall budget (engineering defaults; the frozen Hotel campaigns sel1 and lmt2 ran 160 cells at a median
# period of 184.6 s against 155 s timed, i.e. ~30 s overhead, max ~37 s; 60 s here also covers 1.5x the
# traces at 10/s and the nine extra Jaeger queries of the all-services capture).
BARRIER_LEAD_SECONDS = 5                       # candidate_cell.py: barrier = now + 5 s after warm-up
CELL_OVERHEAD_SECONDS = 60
PREPARE_RESERVE_SECONDS = 600
CLEANUP_RESERVE_SECONDS = 300
# ---------------------------------------------------------------- derived

TOTAL_RUNS = len(REGIMES) * len(RATES) * EPISODES
CELLS_PER_BLOCK = len(REGIMES) * len(RATES)
SCHEDULE_CONTEXT = "sweep-schedule-v1"
CELL_PERIOD_ESTIMATE_SECONDS = (
    WARMUP_SECONDS + BARRIER_LEAD_SECONDS + MEASUREMENT_SECONDS + CELL_OVERHEAD_SECONDS
)
MINIMUM_TIMED_SECONDS = TOTAL_RUNS * (WARMUP_SECONDS + MEASUREMENT_SECONDS)
# Whole hours, because the gate driver's GATE-RUN deadline is `run_window_hours` (an int) after approval.
MAXIMUM_WALL_SECONDS = 3600 * int(math.ceil(
    (TOTAL_RUNS * CELL_PERIOD_ESTIMATE_SECONDS + PREPARE_RESERVE_SECONDS + CLEANUP_RESERVE_SECONDS) / 3600.0
))
MINIMUM_FIRST_MUTATION_REMAINING_SECONDS = MAXIMUM_WALL_SECONDS - CLEANUP_RESERVE_SECONDS
EXPECTED_DESCRIPTOR_SHA256 = "788ff28cc44248fec518fd04e3e0f91ab6d92229888a1412a52e50f9dd889dab"
EXPECTED_PLAN_SHA256 = "766063c5a0f0b90ab1aba1ada29b86e152e8ec1e7f7bd048d4c802c10b7bbc72"


def rate_token(rate: float) -> str:
    """10 -> '10', 0.2 -> '0p2', 0.05 -> '0p05'; the run ID carries the rate it was compiled for."""
    text = "%g" % float(rate)
    if "e" in text or "-" in text or not text:
        raise ProtocolError("rate %r has no plain decimal run-ID token" % (rate,))
    return text.replace(".", "p")


def offered_for(rate: float, seconds: float) -> int:
    product = float(rate) * float(seconds)
    offered = int(round(product))
    if offered < 1 or abs(product - offered) > 1e-9:
        raise ProtocolError("rate x measurement must be a positive integer: %r x %r" % (rate, seconds))
    return offered


def _unit_draw(*parts: Any) -> float:
    """Uniform in [0, 1) from SHA-256 of the NUL-joined parts (no stdlib RNG: identical on 3.9 and 3.13)."""
    text = "\0".join(str(part) for part in parts)
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16) / float(1 << 64)


def onset_phase_offset(run_id: str, rate: float) -> float:
    if ONSET_PHASE_OFFSET == "none":
        return 0.0
    inter_arrival = 1.0 / float(rate)
    match = re.match(r"^(?P<regime>.+)-r[0-9p]+-b(?P<block>[0-9]{2})-[a-z]+-a01$", run_id)
    if match is None:
        raise ProtocolError("run ID %r has no regime and block" % (run_id,))
    strata = sorted(range(EPISODES), key=lambda stratum: _unit_draw(
        SCHEDULE_SEED, EPOCH, match.group("regime"), rate_token(rate), "onset-stratum", stratum))
    stratum = strata[int(match.group("block")) - 1]
    position = _unit_draw(SCHEDULE_SEED, EPOCH, run_id, "onset-phase")
    offset = round((stratum + position) / EPISODES * inter_arrival, 6)
    return min(offset, round(inter_arrival - 1e-6, 6))


def phase_floors(rate: float, measurement: float, onset: float, hold: float) -> Dict[str, int]:
    """Witnessed-start floor per phase: max(1, ceil(FLOOR x the plan's own slots in that phase)).

    Counted on the workload's own schedule (offset = sequence / rate), not on nominal seconds: at 0.05/s a
    seconds-based floor is 2 for every onset offset below 20 s, while only one slot is left after recovery
    once the offset passes ~18.7 s, so it would fail by construction.  `post-readiness` slots start
    POST_RECOVERY_ALLOWANCE_SECONDS after the scheduled revert (the witness's 1 s settle plus the unpause
    and readiness probe).  A phase with no scheduled slot cannot be witnessed and is refused here.
    """
    offsets = [sequence / float(rate) for sequence in range(offered_for(rate, measurement))]
    counts = {
        "pre": sum(1 for value in offsets if value < onset),
        "during": sum(1 for value in offsets if onset <= value < onset + hold),
        "post-readiness": sum(
            1 for value in offsets if value >= onset + hold + POST_RECOVERY_ALLOWANCE_SECONDS
        ),
    }
    if any(count < 1 for count in counts.values()):
        raise ProtocolError("a fault phase has no scheduled request at rate %r" % (rate,))
    return {name: max(1, int(math.ceil(gates.FLOOR * count - 1e-9))) for name, count in counts.items()}


def cell_timing(run_id: str, regime: str, rate: float) -> Dict[str, Any]:
    """Every per-cell value the runner and the validators read, derived from the parameters above."""
    measurement = MEASUREMENT_SECONDS
    offset = onset_phase_offset(run_id, rate)
    onset = round(FAULT_ONSET_BASE_SECONDS + offset, 6)
    hold = FAULT_HOLD_SECONDS
    if not 0 < onset < onset + hold < measurement:
        raise ProtocolError("fault window must lie strictly inside the measurement")
    fault = FAULTS[regime]
    floors = None
    if fault is not None:
        floors = phase_floors(rate, measurement, onset, hold)
    return {
        "requestsPerSecond": float(rate),
        "interArrivalSeconds": 1.0 / float(rate),
        "concurrency": CONCURRENCY,
        "requestTimeoutSeconds": REQUEST_TIMEOUT_SECONDS,
        "warmupSeconds": WARMUP_SECONDS,
        "warmupRequestsPerSecond": WARMUP_REQUESTS_PER_SECOND,
        "measurementSeconds": measurement,
        "offered": offered_for(rate, measurement),
        "faultApplied": fault is not None,
        "faultOnsetBaseSeconds": FAULT_ONSET_BASE_SECONDS,
        "faultOnsetPhaseOffsetSeconds": offset,
        "faultOnsetSeconds": onset,
        "faultHoldSeconds": hold,
        # A no-fault cell carries the same (seeded) window as a pseudo window for G1/G2 and false alarms.
        "scoredWindowSeconds": [onset, round(onset + hold, 6)],
        "minimumWitnessedStartsByPhase": floors,
        "tcpSnapshotOffsetsSeconds": {
            "pre-fault": round(onset - TCP_PRE_FAULT_LEAD_SECONDS, 6),
            "during-fault": round(onset + TCP_DURING_FAULT_LAG_SECONDS, 6),
        },
        "jaegerQueryWindowSeconds": measurement + JAEGER_TAIL_SECONDS,
        "minimumSystemSamples": int(measurement // SYSTEM_SAMPLE_INTERVAL_SECONDS),
        "collectorJoinSlackSeconds": 1.0 / float(rate),
        "applicationLogTimestamps": True,
        "jaegerAllServicesRemainder": True,
        "probeStamps": True,
    }


def run_id_for(regime: str, rate: float, block: int, posture: str) -> str:
    return "%s-r%s-b%02d-%s-a01" % (regime, rate_token(rate), block, posture)


def block_order(block: int) -> List[Dict[str, Any]]:
    """Every (regime, rate) pair once, Fisher-Yates shuffled by SHA-256 draws keyed by seed and block."""
    pairs = [{"regime": regime, "rate": float(rate)} for regime in REGIMES for rate in RATES]
    for index in range(len(pairs) - 1, 0, -1):
        draw = int(hashlib.sha256(
            ("%s\0%s\0block-%02d\0draw-%d\0%s" % (SCHEDULE_SEED, EPOCH, block, index, SCHEDULE_CONTEXT))
            .encode("utf-8")
        ).hexdigest(), 16)
        other = draw % (index + 1)
        pairs[index], pairs[other] = pairs[other], pairs[index]
    if block == 1:
        lead = [row for row in pairs if (row["regime"], row["rate"]) == (LEAD_CELL[0], float(LEAD_CELL[1]))]
        if len(lead) != 1:
            raise ProtocolError("lead cell is not in block 1")
        pairs = lead + [row for row in pairs if row is not lead[0]]
    return pairs


def allocate_schedule() -> List[Dict[str, Any]]:
    if POSTURES != ("full",):
        raise ProtocolError("the traffic sweep runs the full posture only")
    if ONSET_PHASE_OFFSET not in ONSET_PHASE_OFFSETS:
        raise ProtocolError("onset phase offset rule is not declared")
    if len(set(RATES)) != len(RATES) or any(not (math.isfinite(rate) and rate > 0) for rate in RATES):
        raise ProtocolError("rates must be distinct, finite and positive")
    blocks = []
    for block in range(1, EPISODES + 1):
        order = block_order(block)
        run_ids = [run_id_for(row["regime"], row["rate"], block, POSTURES[0]) for row in order]
        blocks.append({
            "block": block,
            "runIds": run_ids,
            "orderSha256": canonical_sha256(run_ids),
        })
    every = [run_id for row in blocks for run_id in row["runIds"]]
    if len(every) != TOTAL_RUNS or len(set(every)) != TOTAL_RUNS:
        raise ProtocolError("schedule does not contain every cell exactly once")
    return blocks


def _ground_truth() -> Dict[str, Any]:
    truth = frozen.frozen_descriptor()["groundTruth"]
    faults = {fault for fault in FAULTS.values() if fault is not None}
    truth["fault"]["scenarioContracts"] = [
        row for row in truth["fault"]["scenarioContracts"] if row["scenario"] in faults
    ]
    truth["path"]["faultSpecific"] = [
        row for row in truth["path"]["faultSpecific"] if row["fault"] in faults
    ]
    return truth


def frozen_descriptor() -> Dict[str, Any]:
    base = frozen.frozen_descriptor()
    schedule = allocate_schedule()
    faults = sorted(fault for fault in FAULTS.values() if fault is not None)
    return {
        "schemaVersion": 1,
        "id": EPOCH,
        "status": "method-design-only",
        "module": "hotel-reservation",
        "declaration": "research/traffic-sweep/DECLARATION.md (measurement repo; frozen 2026-10-03)",
        "source": base["source"],
        "workload": {
            "id": WORKLOAD,
            "kind": "fixed-open-loop",
            "method": "GET",
            "route": "/hotels",
            "requestsPerSecondLevels": list(RATES),
            "concurrency": CONCURRENCY,
            "requestTimeoutSeconds": REQUEST_TIMEOUT_SECONDS,
            "opportunityLedger": base["workload"]["opportunityLedger"],
        },
        "design": {
            "postures": list(POSTURES),
            "postureRoles": {posture: base["design"]["postureRoles"][posture] for posture in POSTURES},
            "unsupportedPostures": base["design"]["unsupportedPostures"],
            "regimes": [
                {"id": regime,
                 "kind": "no-fault-calibration" if FAULTS[regime] is None else "effect",
                 "fault": FAULTS[regime], "artifactRootClass": ARTIFACT_ROOTS[regime]}
                for regime in REGIMES
            ],
            "rates": list(RATES),
            "episodesPerRegimeAndRate": EPISODES,
            "blocks": EPISODES,
            "cellsPerBlock": CELLS_PER_BLOCK,
            "totalRuns": TOTAL_RUNS,
            "blockRule": "each-block-holds-every-(regime,rate)-pair-exactly-once",
            "coldStartEachRun": True,
            "faultAppliedToEveryEffectCell": True,
            "noFaultCellsCarryPseudoWindow": True,
        },
        "timing": {
            "warmupSeconds": WARMUP_SECONDS,
            "warmupRequestsPerSecond": WARMUP_REQUESTS_PER_SECOND,
            "leadCell": "%s-r%s-b01 first in block 1" % (LEAD_CELL[0], rate_token(LEAD_CELL[1])),
            "measurementSeconds": MEASUREMENT_SECONDS,
            "offeredRule": "requests-per-second-x-measurement-seconds-integral",
            "offeredByRate": {rate_token(rate): offered_for(rate, MEASUREMENT_SECONDS) for rate in RATES},
            "faultOnsetBaseSeconds": FAULT_ONSET_BASE_SECONDS,
            "faultOnsetPhaseOffset": ONSET_PHASE_OFFSET,
            "faultOnsetPhaseSelectorEncoding": "stratum order: UTF-8(seed || NUL || epoch || NUL || regime || NUL || rate token || NUL || onset-stratum || NUL || stratum); position: UTF-8(seed || NUL || epoch || NUL || runId || NUL || onset-phase)",
            "faultHoldSeconds": FAULT_HOLD_SECONDS,
            "faultOnsetAcceptanceSeconds": [-0.05, 2.0],
            "faultHoldAcceptanceSeconds": [0.0, 2.0],
            "minimumWitnessedStartsByPhaseRule": (
                "max(1, ceil(protocol_gates.FLOOR x scheduled slots in the phase)); pre = slots before onset, "
                "during = slots in [onset, onset + hold), post-readiness = slots from onset + hold + "
                "postRecoveryAllowanceSeconds"
            ),
            "postRecoveryAllowanceSeconds": POST_RECOVERY_ALLOWANCE_SECONDS,
            "phaseNames": ["pre", "during", "post-readiness"],
            "requestTimeoutSeconds": REQUEST_TIMEOUT_SECONDS,
            "jaegerQueryWindowSeconds": MEASUREMENT_SECONDS + JAEGER_TAIL_SECONDS,
            "minimumTimedSeconds": MINIMUM_TIMED_SECONDS,
            "budget": {
                "barrierLeadSeconds": BARRIER_LEAD_SECONDS,
                "cellOverheadSeconds": CELL_OVERHEAD_SECONDS,
                "cellPeriodEstimateSeconds": CELL_PERIOD_ESTIMATE_SECONDS,
                "prepareReserveSeconds": PREPARE_RESERVE_SECONDS,
                "cleanupReserveSeconds": CLEANUP_RESERVE_SECONDS,
                "rule": "ceil-to-whole-hours(totalRuns x cellPeriod + prepare + cleanup)",
                "maximumWallSeconds": MAXIMUM_WALL_SECONDS,
                "minimumFirstMutationRemainingSeconds": MINIMUM_FIRST_MUTATION_REMAINING_SECONDS,
            },
        },
        "schedule": {
            "version": SCHEDULE_CONTEXT,
            "seed": SCHEDULE_SEED,
            "shuffle": "fisher-yates-over-regimes-x-rates-with-sha256-draws",
            "drawEncoding": "UTF-8(seed || NUL || epoch || NUL || block-NN || NUL || draw-i || NUL || version)",
            "blocks": schedule,
        },
        "runIdentity": {
            **base["runIdentity"],
            "fields": ["studyEpoch", "regime", "requestsPerSecond", "block", "posture", "attempt"],
        },
        "groundTruth": _ground_truth(),
        "protocolGates": {
            "module": "modules/hotel-reservation/validation/protocol_gates.py",
            "vendoredFrom": "src/obsplacement/protocol_gates.py (measurement repo), byte-identical",
            "blocking": ["F1", "G1", "G2", "G4"],
            "recordedNotBlocking": ["R2.recovery"],
            "notEvaluated": {
                "P0": "harness records no per-service connection counts or emitted-byte observations",
                "R1": "harness records no per-channel recordsAfterWarmup and no per-route readiness map",
                "R2": "fresh project and down -v are enforced by the cell runner, not recorded as a gate input",
            },
            "g4ChannelScope": "ledger-only (no per-channel in-cell / total counts are recorded)",
            "thresholds": {
                "FLOOR": gates.FLOOR, "PRE_FAIL_MAX": gates.PRE_FAIL_MAX, "SCOPE_MIN": gates.SCOPE_MIN,
                "SCOPE_SLACK_S": gates.SCOPE_SLACK_S, "ONSET_TOLERANCE_S": gates.ONSET_TOLERANCE_S,
                "HOLD_TOLERANCE_S": gates.HOLD_TOLERANCE_S, "G1_MIN_DISPATCHED": gates.G1_MIN_DISPATCHED,
            },
            "stopRule": "first-invalid-cell",
        },
        "outcomes": base["outcomes"],
        "postureProof": {posture: base["postureProof"][posture] for posture in POSTURES},
        "collection": {
            "logLevelByPosture": {posture: frozen.LOG_LEVEL_BY_POSTURE[posture] for posture in POSTURES},
            "metricSamplerPostures": [p for p in POSTURES if p in frozen.SAMPLER_POSTURES],
            "metricSamplerIntervalSeconds": base["collection"]["metricSamplerIntervalSeconds"],
            "tracePostures": [p for p in POSTURES if p in frozen.TRACE_POSTURES],
            "tracedServicesByPosture": {p: list(frozen.TRACED_SERVICES_BY_POSTURE[p]) for p in POSTURES},
            "alwaysOn": base["collection"]["alwaysOn"],
            "applicationLogTimestamps": "docker-compose-logs-timestamps",
            "jaegerCapture": "frontend-query-plus-deduplicated-remainder-of-the-other-application-services",
            "costAxis": base["collection"]["costAxis"],
            "alwaysOnCostMeasured": False,
        },
        "faultParameters": {
            **base["faultParameters"],
            "targets": {fault: frozen.FAULT_TARGETS[fault] for fault in faults},
        },
        "missingness": base["missingness"],
        "analysis": {
            "comparativeUnit": "(fault, rate) over episodes",
            "descriptiveOnly": True,
            "detectionTimeMissCharge": "window-end (hold end), averaged over all episodes",
            "analysisCode": "research/detection-time/ (measurement repo), to be extended and fixed before the first cell",
            "forbidden": base["analysis"]["forbidden"],
        },
        "evidence": base["evidence"],
        "transport": base["transport"],
    }


def validate_descriptor(document: Any) -> Dict[str, Any]:
    if not isinstance(document, dict):
        raise ProtocolError("descriptor must contain one JSON object")
    frozen._assert_exact(frozen_descriptor(), document)
    return document


def load_descriptor(path: Path = DEFAULT_DESCRIPTOR) -> Dict[str, Any]:
    document = validate_descriptor(strict_json_file(path))
    digest = canonical_sha256(document)
    if digest != EXPECTED_DESCRIPTOR_SHA256:
        raise ProtocolError(
            "descriptor canonical digest differs from the reviewed freeze: "
            "expected %s, found %s" % (EXPECTED_DESCRIPTOR_SHA256, digest)
        )
    return document


def plan_body(document: Any) -> Dict[str, Any]:
    descriptor = validate_descriptor(document)
    role = descriptor["design"]["postureRoles"]
    blocks = []
    for receipt in descriptor["schedule"]["blocks"]:
        number = receipt["block"]
        cells = []
        for position, pair in enumerate(block_order(number), start=1):
            regime, rate, posture = pair["regime"], pair["rate"], POSTURES[0]
            run_id = run_id_for(regime, rate, number, posture)
            if run_id != receipt["runIds"][position - 1]:
                raise ProtocolError("compiled order differs from the descriptor's schedule receipt")
            cells.append({
                "runId": run_id,
                "runKey": {
                    "studyEpoch": EPOCH, "regime": regime, "requestsPerSecond": rate,
                    "block": number, "posture": posture, "attempt": 1,
                },
                "position": position,
                "artifactRoot": "%s/r%s/b%02d/p%02d-%s/attempt-01" % (
                    ARTIFACT_ROOTS[regime], rate_token(rate), number, position, posture),
                "fault": FAULTS[regime],
                "postureRole": role[posture],
                "timing": cell_timing(run_id, regime, rate),
                "scheduledState": "not-started",
                "candidateCellEligible": False,
                "runtimeAdapter": None,
            })
        blocks.append({"block": number, "order": list(receipt["runIds"]), "cells": cells})
    return {
        "schemaVersion": 1,
        "studyEpoch": EPOCH,
        "descriptorCanonicalSha256": canonical_sha256(descriptor),
        "runCount": TOTAL_RUNS,
        "minimumTimedSeconds": MINIMUM_TIMED_SECONDS,
        "maximumWallSeconds": MAXIMUM_WALL_SECONDS,
        "runtimeAllowed": False,
        "externalMutationAllowed": False,
        "transport": None,
        "canonical": False,
        "placementOrSourceCostEligible": False,
        "blocks": blocks,
        "unsupportedPostures": descriptor["design"]["unsupportedPostures"],
        "missingnessBoundary": descriptor["missingness"],
        "groundTruthBoundary": descriptor["groundTruth"],
        "outcomeBoundary": descriptor["outcomes"],
        "analysisBoundary": descriptor["analysis"],
    }


def compile_plan(document: Any) -> Dict[str, Any]:
    body = plan_body(document)
    digest = canonical_sha256(body)
    if digest != EXPECTED_PLAN_SHA256:
        raise ProtocolError(
            "compiled plan digest differs from the reviewed freeze: "
            "expected %s, found %s" % (EXPECTED_PLAN_SHA256, digest)
        )
    return dict(body, planCanonicalSha256=digest)


def validate_plan(plan: Any, descriptor: Any) -> Dict[str, Any]:
    expected = compile_plan(descriptor)
    frozen._assert_exact(expected, plan)
    body = {key: value for key, value in plan.items() if key != "planCanonicalSha256"}
    if plan["planCanonicalSha256"] != canonical_sha256(body):
        raise ProtocolError("compiled plan digest mismatch")
    return plan


def flatten_cells(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [cell for block in plan["blocks"] for cell in block["cells"]]


def readiness_report(document: Any, plan: Any) -> Dict[str, Any]:
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
        "blockers": ["declaration-draft-not-frozen", "native-operation-ground-truth-unqualified"],
    }


def descriptor_bytes() -> bytes:
    return json.dumps(frozen_descriptor(), indent=2, allow_nan=False).encode("utf-8") + b"\n"


def write_descriptor(path: Path) -> None:
    """Regenerate the checked-in descriptor; refuses to change an existing file that differs."""
    payload = descriptor_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ProtocolError("refusing to change existing descriptor %s; move it aside first" % path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write-descriptor", type=Path)
    parser.add_argument("--print-digests", action="store_true",
                        help="print the unpinned descriptor and plan digests (for re-pinning after a change)")
    args = parser.parse_args()
    try:
        if args.write_descriptor is not None:
            write_descriptor(args.write_descriptor)
        if args.print_digests:
            descriptor = frozen_descriptor()
            print(json.dumps({
                "descriptorCanonicalSha256": canonical_sha256(descriptor),
                "planCanonicalSha256": canonical_sha256(plan_body(descriptor)),
            }, indent=2, sort_keys=True))
            return 0
        descriptor = load_descriptor(args.descriptor)
        plan = compile_plan(descriptor)
        if args.output is not None:
            frozen.write_plan(args.output, plan)
    except ProtocolError as exc:
        parser.error(str(exc))
    print(json.dumps({
        "studyEpoch": plan["studyEpoch"],
        "descriptorCanonicalSha256": plan["descriptorCanonicalSha256"],
        "planCanonicalSha256": plan["planCanonicalSha256"],
        "runCount": plan["runCount"],
        "maximumWallSeconds": plan["maximumWallSeconds"],
        "runtimeAllowed": plan["runtimeAllowed"],
        "placementOrSourceCostEligible": plan["placementOrSourceCostEligible"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
