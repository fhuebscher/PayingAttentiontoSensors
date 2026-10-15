#!/usr/bin/env python3
"""Compile the TeaStore traffic-sweep epoch (teastore-traffic-sweep-v1) without executing it.

A second, separate epoch beside the frozen ``candidate_pilot.py`` (teastore-candidate-pilot-sys-v1, 27 cells),
which this file never changes.  Request rate, measurement length, fault onset, hold and the offered count are
per-cell plan values: every compiled cell carries a ``timing`` block, and the cell producer
(performance_campaign.py), the workload, the witness extractors and the validators read the cell's timing instead
of the frozen epoch's literals.  It replicates the Hotel sweep (hotel-traffic-sweep-v1) as an initial test:
proposal ``research/traffic-sweep/DECLARATION_TEASTORE_DRAFT.md`` (measurement repo; a draft, not frozen).  Every
value below the "parameters" line is a declaration proposal; changing one changes the descriptor and plan digests,
by design.

The plan keeps the frozen plan's top-level schema (scheduleAllocation, runCount, descriptorSha256, ...) so the
orchestrator, adapter, transport and installer replay it with the same code, but holds its cells in ``blocks``
(execution order: the lead cell, then a seeded shuffle) instead of the frozen regime-major ``regimeRoots``.

Runs as ``python3 -I`` on CPython 3.9 on the target: standard library only, sibling files are loaded by path
(``-I`` drops this directory from ``sys.path``), no PEP 604 annotation evaluated at runtime.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List


HERE = Path(__file__).resolve().parent
MODULE = HERE.parent
ROOT = Path(__file__).resolve().parents[3]
DESCRIPTOR_RELATIVE = "pipelines/campaigns/teastore-traffic-sweep-v1.json"
DEFAULT_DESCRIPTOR = ROOT / DESCRIPTOR_RELATIVE


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_TAG = hashlib.sha256(str(HERE).encode("utf-8")).hexdigest()[:12]
# The frozen epoch supplies the ground truth, posture proof, queue proof and the JSON helpers; it is read, never
# edited.  The vendored protocol gates supply FLOOR, so the phase floors are the gates' own rule.
frozen = _load("teastore_sweep_frozen_compiler_" + _TAG, HERE / "candidate_pilot.py")
gates = _load("teastore_sweep_protocol_gates_" + _TAG, MODULE / "validation" / "protocol_gates.py")
ProtocolError = frozen.ProtocolError
AdmissionError = frozen.AdmissionError
canonical_sha256 = frozen.canonical_sha256
canonical_json_bytes = frozen.canonical_json_bytes
strict_json_loads = frozen.strict_json_loads
strict_json_file = frozen.strict_json_file

EPOCH = "teastore-traffic-sweep-v1"
SUT_COMMIT = frozen.SUT_COMMIT
WORKLOAD = "login-only-v1"
JOURNEY_KIND = "login-only"

# ---------------------------------------------------------------- parameters (declaration draft defaults)
POSTURES = ("full",)
RATES = (10.0, 1.0, 0.2, 0.05)                 # login journeys (one POST each) per second; inter-arrival 0.1-20 s
ROUTE = "POST /tools.descartes.teastore.webui/loginAction"   # urllib follows the 302 to / (frozen login step)
WARMUP_SECONDS = 30
WARMUP_JOURNEYS_PER_SECOND = 10.0              # every cell warms up at 10/s (Hotel decision, 2026-10-03)
MEASUREMENT_SECONDS = 180
FAULT_ONSET_BASE_SECONDS = 60                  # the seeded phase offset below is added per cell
FAULT_HOLD_SECONDS = 60
# Hotel's rule, copied: the EPISODES blocks of one (regime, rate) pair take the EPISODES equal strata of one
# inter-arrival in a seeded order, uniform inside the stratum.  With one block the stratum is the whole
# inter-arrival.
ONSET_PHASE_OFFSET = "seeded-stratified-within-one-inter-arrival"
ONSET_PHASE_OFFSETS = ("seeded-stratified-within-one-inter-arrival", "none")
LEAD_CELL = ("auth-freeze-effect", 10.0)       # the pause at 10/s runs first (Hotel M3 / lead-cell rule)
REQUEST_TIMEOUT_SECONDS = 15.0                 # fixed_load.py --timeout default; the frozen cell runner passes none
# Open loop under a full outage: at most rate x timeout requests are in flight (150 at 10/s), so the pool must
# exceed that or starts lag their schedule.  Same margin ratio as Hotel (16 workers for 10/s x 1 s = 1.6).
CONCURRENCY_MARGIN = 1.6
CONCURRENCY = int(math.ceil(CONCURRENCY_MARGIN * max(RATES) * REQUEST_TIMEOUT_SECONDS))
EPISODES = 1                                   # initial test: one block, one cell per (regime, rate)
SCHEDULE_SEED = 20261003
REGIMES = (
    "no-fault-cost",                           # no-fault calibration; reuses the frozen harness's no-fault path
    "auth-freeze-effect",                      # docker compose pause auth (the frozen auth-freeze fault)
    "persistence-cpu-throttle-effect",         # docker update --cpus 0.1 on persistence, reverted to the host NCPU
)
FAULTS = {
    "no-fault-cost": None,
    "auth-freeze-effect": "auth-freeze",
    "persistence-cpu-throttle-effect": "persistence-cpu-throttle",
}
ARTIFACT_CLASSES = {
    "no-fault-cost": "cost",
    "auth-freeze-effect": "effect/auth-freeze",
    "persistence-cpu-throttle-effect": "effect/persistence-cpu-throttle",
}
FAULT_TARGETS = {"auth-freeze": "auth", "persistence-cpu-throttle": "persistence"}
CPU_THROTTLE_CPUS = "0.1"
CPU_THROTTLE_NANOCPUS = 100_000_000
OMITTED_REGIMES = {
    "net-delay": (
        "no mechanism without sudo: netem needs root in the target's network namespace and fb14srv5 grants the "
        "execution user no passwordless sudo; a docker sidecar sharing the netns needs an image with tc that is "
        "not provisioned or digest-pinned on fb14srv5"
    ),
}
# Readiness after the revert: the frozen auth-freeze receipts show 0.44-0.60 s from the last hold sample to the
# readiness observation (n = 28, campaigns #12-#15 and the srv6 partial run).  2 s = Hotel's allowance.
POST_RECOVERY_ALLOWANCE_SECONDS = 2.0
# Q3 (user, 2026-10-03, "Q3 17 s"): journeys that START in [readiness, readiness + allowance) may fail without
# invalidating a fault cell (they meet the backlog the revert releases); recorded and excluded from the zero-failure
# rule.  allowance = the plan's client timeout + this margin (17 s at 15 s); no-fault cells have none.
DRAIN_ALLOWANCE_MARGIN_SECONDS = 2.0
# Shared trace-completeness rule (protocol decision 25, user 2026-10-03 ~13:00Z, all three sweeps): journeys that
# start in [onset command issued, readiness + drain allowance) may have incomplete traces (recorded, never
# blocking); everywhere else, and in every no-fault cell, a cell blocks only if more than
# max(1, floor(TRACE_INCOMPLETE_FRACTION x successful journeys there)) journeys have an incomplete trace.
TRACE_INCOMPLETE_FRACTION = 0.01
SYSTEM_SAMPLE_INTERVAL_SECONDS = 5.0           # performance_campaign.SYSTEM_SAMPLE_INTERVAL_SECONDS
BARRIER_LEAD_SECONDS = 15.0                    # performance_campaign.MEASUREMENT_BARRIER_LEAD_SECONDS
# Wall budget (engineering defaults).  Frozen TeaStore cells (#12-#15, srv5) ran at a median period of 865 s
# against 735 s timed (120 warm-up + 15 barrier lead + 600 measurement): 130 s overhead, 192 s at most.  300 s
# also covers a 10/s capture's larger spool replay and validation.
CELL_OVERHEAD_SECONDS = 300
CELL_OVERHEAD_LOWER_SECONDS = 130
PREPARE_RESERVE_SECONDS = 1800                 # refresh, derive, dry run, package, launch before the first cell
CLEANUP_RESERVE_SECONDS = 300                  # candidate_runtime_adapter.CLEANUP_RESERVE_SECONDS
# ---------------------------------------------------------------- derived

TOTAL_RUNS = len(REGIMES) * len(RATES) * EPISODES
CELLS_PER_BLOCK = len(REGIMES) * len(RATES)
SCHEDULE_CONTEXT = "sweep-schedule-v1"
TIMED_SECONDS_PER_CELL = WARMUP_SECONDS + int(BARRIER_LEAD_SECONDS) + MEASUREMENT_SECONDS
CELL_PERIOD_ESTIMATE_SECONDS = TIMED_SECONDS_PER_CELL + CELL_OVERHEAD_SECONDS
MINIMUM_TIMED_SECONDS = TOTAL_RUNS * (WARMUP_SECONDS + MEASUREMENT_SECONDS)
OPERATIONAL_ESTIMATE_SECONDS = {
    "lower": TOTAL_RUNS * (TIMED_SECONDS_PER_CELL + CELL_OVERHEAD_LOWER_SECONDS),
    "upper": TOTAL_RUNS * CELL_PERIOD_ESTIMATE_SECONDS,
}
# Same rule as the frozen epoch (29,100 = the 8 h upper estimate + the 300 s cleanup reserve).
MINIMUM_FIRST_MUTATION_REMAINING_SECONDS = OPERATIONAL_ESTIMATE_SECONDS["upper"] + CLEANUP_RESERVE_SECONDS
# Whole hours, because the gate driver's GATE-RUN deadline is RUN_WINDOW_HOURS after approval.
RUN_WINDOW_HOURS = int(math.ceil(
    (MINIMUM_FIRST_MUTATION_REMAINING_SECONDS + PREPARE_RESERVE_SECONDS) / 3600.0
))
MAXIMUM_WALL_SECONDS = RUN_WINDOW_HOURS * 3600
EXPECTED_DESCRIPTOR_SHA256 = "f90bd64c13075c3019c03c4aee4df3744bb1494b194645b17d246bea063b160a"
EXPECTED_PLAN_SHA256 = "88a3017a781233a4848f7ea638b4763f82f63bc902d848514cd8ae5089529355"

DESIGN_LABEL = frozen.DESIGN_LABEL
CANDIDATE_LABEL = frozen.CANDIDATE_LABEL


def rate_token(rate: float) -> str:
    """10 -> '10', 0.2 -> '0p2', 0.05 -> '0p05'; the run ID carries the rate it was compiled for."""
    text = "%g" % float(rate)
    if "e" in text or "-" in text or not text:
        raise ProtocolError("rate %r has no plain decimal run-ID token" % (rate,))
    return text.replace(".", "p")


def offered_for(rate: float, seconds: float) -> int:
    """rate x seconds, which must be a positive integer; equals fixed_load's max(1, floor(rate x duration))."""
    product = float(rate) * float(seconds)
    offered = int(round(product))
    if offered < 1 or abs(product - offered) > 1e-9 or max(1, math.floor(product)) != offered:
        raise ProtocolError("rate x measurement must be a positive integer: %r x %r" % (rate, seconds))
    return offered


def _unit_draw(*parts: Any) -> float:
    """Uniform in [0, 1) from SHA-256 of the NUL-joined parts (no stdlib RNG: identical on 3.9 and 3.13)."""
    text = "\0".join(str(part) for part in parts)
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16) / float(1 << 64)


def run_id_for(regime: str, rate: float, block: int, posture: str) -> str:
    return "%s/%s/r%s/b%02d/%s/a01" % (EPOCH, regime, rate_token(rate), block, posture)


def _run_id_parts(run_id: str) -> Dict[str, Any]:
    parts = run_id.split("/")
    if (len(parts) != 6 or parts[0] != EPOCH or parts[1] not in REGIMES or not parts[2].startswith("r")
            or not parts[3].startswith("b") or not parts[3][1:].isdigit() or parts[5] != "a01"):
        raise ProtocolError("run ID %r is not a sweep run ID" % (run_id,))
    return {"regime": parts[1], "rateToken": parts[2][1:], "block": int(parts[3][1:]), "posture": parts[4]}


def onset_phase_offset(run_id: str, rate: float) -> float:
    """Hotel's onset_phase_offset, copied: stratum by seeded order, position uniform inside the stratum."""
    if ONSET_PHASE_OFFSET == "none":
        return 0.0
    inter_arrival = 1.0 / float(rate)
    parts = _run_id_parts(run_id)
    if parts["rateToken"] != rate_token(rate):
        raise ProtocolError("run ID %r was not compiled for rate %r" % (run_id, rate))
    strata = sorted(range(EPISODES), key=lambda stratum: _unit_draw(
        SCHEDULE_SEED, EPOCH, parts["regime"], rate_token(rate), "onset-stratum", stratum))
    stratum = strata[parts["block"] - 1]
    position = _unit_draw(SCHEDULE_SEED, EPOCH, run_id, "onset-phase")
    offset = round((stratum + position) / EPISODES * inter_arrival, 6)
    return min(offset, round(inter_arrival - 1e-6, 6))


def phase_floors(rate: float, measurement: float, onset: float, hold: float) -> Dict[str, int]:
    """Actual-start floor per TeaStore phase: max(1, ceil(FLOOR x the plan's own slots in that phase)).

    Replaces the frozen ``>= 20`` literal (validation/candidate_pilot.py, actual-phase-start-floor), which a
    0.05/s cell (9 journeys in all) cannot meet.  Counted on the workload's own schedule (offset =
    sequence / rate): ``before`` = slots before onset, ``during`` = slots in [onset, onset + hold), ``after`` =
    slots from onset + hold + POST_RECOVERY_ALLOWANCE_SECONDS.  A phase with no scheduled slot is refused here.
    """
    offsets = [sequence / float(rate) for sequence in range(offered_for(rate, measurement))]
    counts = {
        "before": sum(1 for value in offsets if value < onset),
        "during": sum(1 for value in offsets if onset <= value < onset + hold),
        "after": sum(1 for value in offsets if value >= onset + hold + POST_RECOVERY_ALLOWANCE_SECONDS),
    }
    if any(count < 1 for count in counts.values()):
        raise ProtocolError("a fault phase has no scheduled journey at rate %r" % (rate,))
    return {name: max(1, int(math.ceil(gates.FLOOR * count - 1e-9))) for name, count in counts.items()}


def cell_timing(run_id: str, regime: str, rate: float) -> Dict[str, Any]:
    """Every per-cell value the producer, workload and validators read, derived from the parameters above."""
    measurement = MEASUREMENT_SECONDS
    offset = onset_phase_offset(run_id, rate)
    onset = round(FAULT_ONSET_BASE_SECONDS + offset, 6)
    hold = FAULT_HOLD_SECONDS
    if not 0 < onset < onset + hold + POST_RECOVERY_ALLOWANCE_SECONDS < measurement:
        raise ProtocolError("fault window must lie strictly inside the measurement")
    fault = FAULTS[regime]
    floors = phase_floors(rate, measurement, onset, hold) if fault is not None else None
    return {
        "journeyKind": JOURNEY_KIND,
        "workloadId": WORKLOAD,
        "route": ROUTE,
        "journeysPerSecond": float(rate),
        "interArrivalSeconds": 1.0 / float(rate),
        "concurrency": CONCURRENCY,
        "requestTimeoutSeconds": REQUEST_TIMEOUT_SECONDS,
        "warmupSeconds": WARMUP_SECONDS,
        "warmupJourneysPerSecond": WARMUP_JOURNEYS_PER_SECOND,
        "warmupOffered": offered_for(WARMUP_JOURNEYS_PER_SECOND, WARMUP_SECONDS),
        "barrierLeadSeconds": BARRIER_LEAD_SECONDS,
        "measurementSeconds": measurement,
        "offered": offered_for(rate, measurement),
        "faultApplied": fault is not None,
        "fault": fault,
        "faultTarget": FAULT_TARGETS.get(fault) if fault is not None else None,
        "cpuThrottleCpus": CPU_THROTTLE_CPUS if fault == "persistence-cpu-throttle" else None,
        "cpuThrottleNanoCpus": CPU_THROTTLE_NANOCPUS if fault == "persistence-cpu-throttle" else None,
        "faultOnsetBaseSeconds": FAULT_ONSET_BASE_SECONDS,
        "faultOnsetPhaseOffsetSeconds": offset,
        "faultOnsetSeconds": onset,
        "faultHoldSeconds": hold,
        # A no-fault cell carries the same (seeded) window as a pseudo window for G1/G2 and false alarms.
        "scoredWindowSeconds": [onset, round(onset + hold, 6)],
        "postRecoveryAllowanceSeconds": POST_RECOVERY_ALLOWANCE_SECONDS,
        "drainAllowanceSeconds": (
            REQUEST_TIMEOUT_SECONDS + DRAIN_ALLOWANCE_MARGIN_SECONDS if fault is not None else None),
        "minimumActualStartsByPhase": floors,
        "systemSampleIntervalSeconds": SYSTEM_SAMPLE_INTERVAL_SECONDS,
        "systemSampleCount": int(measurement // SYSTEM_SAMPLE_INTERVAL_SECONDS) + 1,
        "applicationLogTimestamps": True,
        "probeStamps": True,
        "protocolGates": ["F1", "G1", "G2", "G4"],
    }


def block_order(block: int) -> List[Dict[str, Any]]:
    """Every (regime, rate) pair once, Fisher-Yates shuffled by SHA-256 draws keyed by seed and block (Hotel's)."""
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
    if set(REGIMES) != set(FAULTS) or set(REGIMES) != set(ARTIFACT_CLASSES):
        raise ProtocolError("regime tables differ")
    blocks = []
    for block in range(1, EPISODES + 1):
        order = block_order(block)
        run_ids = [run_id_for(row["regime"], row["rate"], block, POSTURES[0]) for row in order]
        blocks.append({"block": block, "runIds": run_ids, "orderSha256": canonical_sha256(run_ids)})
    every = [run_id for row in blocks for run_id in row["runIds"]]
    if len(every) != TOTAL_RUNS or len(set(every)) != TOTAL_RUNS:
        raise ProtocolError("schedule does not contain every cell exactly once")
    return blocks


def schedule_allocation(schedule: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """The frozen ``scheduleAllocation`` shape (regime -> selector digest and per-block posture order).

    ``selectorSha256`` is the canonical digest of the regime's run IDs in execution order and ``blocks`` lists,
    per block, the posture of each of the regime's cells in that order; the campaign manifest copies both.
    """
    allocation = {}
    for regime in REGIMES:
        ordered = [run_id for row in schedule for run_id in row["runIds"] if _run_id_parts(run_id)["regime"] == regime]
        allocation[regime] = {
            "selectorBytes": "canonical-json(run IDs of %s in execution order)" % regime,
            "selectorSha256": canonical_sha256(ordered),
            "runIds": ordered,
            "blocks": [
                [_run_id_parts(run_id)["posture"] for run_id in row["runIds"]
                 if _run_id_parts(run_id)["regime"] == regime]
                for row in schedule
            ],
        }
    return allocation


def _ground_truth() -> Dict[str, Any]:
    truth = frozen.frozen_descriptor()["groundTruth"]
    contracts = [row for row in truth["fault"]["scenarioContracts"] if row["scenario"] == "auth-freeze"]
    contracts.append({
        "scenario": "persistence-cpu-throttle", "service": "persistence",
        "containerIdentityRule": "same-container-pre-during-post",
        "commandFamily": "docker-update-cpus",
        "prePredicate": "running-and-unpaused-and-cpu-unthrottled",
        "duringPredicate": "running-and-unpaused-and-nanocpus-equal-throttle",
        "postPredicate": "running-and-unpaused-and-nanocpus-lifted-to-host-ncpu",
    })
    truth["fault"]["scenarioContracts"] = contracts
    truth["fault"]["onsetStamp"] = "pre-command (commandStamps.onsetCommandIssuedMonotonicOffsetSeconds)"
    truth["fault"]["probeStamps"] = (
        "every post-revert readiness request (GET /status) is stamped in the receipt's probes list"
    )
    truth["path"]["opportunityWorkload"] = WORKLOAD
    return truth


def frozen_descriptor() -> Dict[str, Any]:
    """The sweep descriptor (named like the frozen compiler's generator so the shared replay code calls it)."""
    base = frozen.frozen_descriptor()
    schedule = allocate_schedule()
    faults = sorted(fault for fault in FAULTS.values() if fault is not None)
    return {
        "schemaVersion": 1,
        "id": EPOCH,
        "status": DESIGN_LABEL,
        "module": "teastore",
        "targetHost": "fb14srv5",
        "declaration": "research/traffic-sweep/DECLARATION_TEASTORE.md (measurement repo; frozen 2026-10-03)",
        "source": base["source"],
        "workload": {
            "id": WORKLOAD,
            "kind": "fixed-open-loop",
            "journeyKind": JOURNEY_KIND,
            "route": ROUTE,
            "redirectFollowed": True,
            "journeysPerSecondLevels": list(RATES),
            "concurrency": CONCURRENCY,
            "concurrencyRule": "ceil(%s x max rate x request timeout)" % CONCURRENCY_MARGIN,
            "requestTimeoutSeconds": REQUEST_TIMEOUT_SECONDS,
            "requestTimeoutSource": "workload/fixed_load.py --timeout default (the frozen cell runner passes none)",
            "population": "login only (one POST /loginAction per journey; the 302 to / is followed)",
            "excludedActions": base["workload"]["excludedActions"] + ["browse-home", "browse-category",
                                                                      "browse-product", "return-home"],
            "journeyLedger": base["workload"]["journeyLedger"],
        },
        "design": {
            "postures": list(POSTURES),
            "selectedSource": None,
            "regimes": [
                {"id": regime,
                 "kind": "no-fault-calibration" if FAULTS[regime] is None else "effect",
                 "fault": FAULTS[regime], "artifactRootClass": ARTIFACT_CLASSES[regime]}
                for regime in REGIMES
            ],
            "omittedRegimes": OMITTED_REGIMES,
            "rates": list(RATES),
            "episodesPerRegimeAndRate": EPISODES,
            "blocks": EPISODES,
            "cellsPerBlock": CELLS_PER_BLOCK,
            "totalRuns": TOTAL_RUNS,
            "blockRule": "each-block-holds-every-(regime,rate)-pair-exactly-once",
            "coldStartEachRun": True,
            "deploymentQueueAttemptArtifactReuse": False,
            "faultAppliedToEveryEffectCell": True,
            "noFaultCellsCarryPseudoWindow": True,
            "noFaultRegimeReusesFrozenPath": (
                "no-fault-cost: the frozen no-fault code path (performance probe, resources.json) runs unchanged; "
                "the sweep reads its cells as calibration, not cost"
            ),
        },
        "timing": {
            "warmupSeconds": WARMUP_SECONDS,
            "warmupJourneysPerSecond": WARMUP_JOURNEYS_PER_SECOND,
            "leadCell": "%s at %s/s first in block 1" % (LEAD_CELL[0], rate_token(LEAD_CELL[1])),
            "measurementSeconds": MEASUREMENT_SECONDS,
            "barrierLeadSeconds": BARRIER_LEAD_SECONDS,
            "offeredRule": "journeys-per-second-x-measurement-seconds-integral",
            "offeredByRate": {rate_token(rate): offered_for(rate, MEASUREMENT_SECONDS) for rate in RATES},
            "faultOnsetBaseSeconds": FAULT_ONSET_BASE_SECONDS,
            "faultOnsetPhaseOffset": ONSET_PHASE_OFFSET,
            "faultOnsetPhaseSelectorEncoding": (
                "stratum order: UTF-8(seed || NUL || epoch || NUL || regime || NUL || rate token || NUL || "
                "onset-stratum || NUL || stratum); position: UTF-8(seed || NUL || epoch || NUL || runId || NUL || "
                "onset-phase)"
            ),
            "faultHoldSeconds": FAULT_HOLD_SECONDS,
            "faultOnsetAcceptanceSeconds": [0.0, gates.ONSET_TOLERANCE_S],
            "holdRule": "revert issued after the last hold sample, taken >= hold after the first post-command sample",
            "minimumActualStartsByPhaseRule": (
                "max(1, ceil(protocol_gates.FLOOR x scheduled slots in the phase)); before = slots before onset, "
                "during = slots in [onset, onset + hold), after = slots from onset + hold + "
                "postRecoveryAllowanceSeconds"
            ),
            "postRecoveryAllowanceSeconds": POST_RECOVERY_ALLOWANCE_SECONDS,
            "drainAllowanceRule": (
                "fault cells: a journey that STARTS in [readiness, readiness + requestTimeoutSeconds + %g s) may fail "
                "without invalidating the cell; it is recorded (count and ids in candidate-validation.json) and "
                "excluded from the zero-failure rule and from the scored population; no-fault cells have none"
                % DRAIN_ALLOWANCE_MARGIN_SECONDS
            ),
            "drainAllowanceMarginSeconds": DRAIN_ALLOWANCE_MARGIN_SECONDS,
            "traceCompleteness": {
                "source": "research/PROTOCOL_DRAFT_20261002.md decision 25 (shared by the three sweeps)",
                "unit": "journey (one login request)",
                "incompleteJourney": (
                    "any record of the journey's native trace(s) carries a correlation error (missing or ambiguous "
                    "parent, conflicting native identity), the trace has an execution-order-index gap or a "
                    "repeated (message, trace, eoi/ess) identity, or it lacks the required auth->persistence edge; "
                    "traces are attributed to journeys by the auth native-trace bridge"
                ),
                "windowI": "fault cells: start in [onset command issued, readiness + drainAllowanceSeconds): "
                           "recorded as fault effect, never blocking",
                "windowII": "pre-onset, after the drain window, and every no-fault cell: block only if incomplete "
                            "journeys > max(1, floor(fraction x successful journeys there))",
                "fraction": TRACE_INCOMPLETE_FRACTION,
                "unattributable": (
                    "an incomplete native trace no journey's bridge names is one cluster; inside window I by the "
                    "logging time of all its defective records: recorded; otherwise it counts as one incomplete "
                    "journey in window II"
                ),
                "harnessProbeOrphans": "excused as before (F-ADH-083)",
            },
            "phaseNames": ["before", "during", "recovery", "after"],
            "phaseAssignmentSource": "observed-intervention-and-readiness-monotonic-times",
            "sharedBarrierParticipants": base["timing"]["sharedBarrierParticipants"],
            "requestTimeoutSeconds": REQUEST_TIMEOUT_SECONDS,
            "minimumTimedSeconds": MINIMUM_TIMED_SECONDS,
            "operationalEstimateSeconds": OPERATIONAL_ESTIMATE_SECONDS,
            "lifecycleIncludedInMinimum": False,
            "budget": {
                "timedSecondsPerCell": TIMED_SECONDS_PER_CELL,
                "cellOverheadSeconds": CELL_OVERHEAD_SECONDS,
                "cellOverheadLowerSeconds": CELL_OVERHEAD_LOWER_SECONDS,
                "cellPeriodEstimateSeconds": CELL_PERIOD_ESTIMATE_SECONDS,
                "prepareReserveSeconds": PREPARE_RESERVE_SECONDS,
                "cleanupReserveSeconds": CLEANUP_RESERVE_SECONDS,
                "minimumFirstMutationRemainingSeconds": MINIMUM_FIRST_MUTATION_REMAINING_SECONDS,
                "minimumFirstMutationRule": "totalRuns x cellPeriodEstimate + cleanupReserve",
                "runWindowHours": RUN_WINDOW_HOURS,
                "runWindowRule": "ceil-to-whole-hours(minimumFirstMutationRemaining + prepareReserve)",
                "maximumWallSeconds": MAXIMUM_WALL_SECONDS,
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
            "runIdShape": "{studyEpoch}/{regime}/r{rate token}/b{block}/{posture}/a01",
            "runKeyFields": ["studyEpoch", "regime", "block", "posture", "attempt"],
            "rateCarriedBy": ["runId", "timing.journeysPerSecond"],
        },
        "groundTruth": _ground_truth(),
        "systemSamples": {
            **base["systemSamples"],
            "samplesPerRun": int(MEASUREMENT_SECONDS // SYSTEM_SAMPLE_INTERVAL_SECONDS) + 1,
            "windowSeconds": MEASUREMENT_SECONDS,
        },
        "protocolGates": {
            "module": "modules/teastore/validation/protocol_gates.py",
            "vendoredFrom": "src/obsplacement/protocol_gates.py (measurement repo), byte-identical",
            "blocking": ["F1", "G1", "G2", "G4"],
            "recordedNotBlocking": ["R2.recovery"],
            "notEvaluated": {
                "P0": "harness records no per-service connection counts or emitted-byte observations",
                "R1": "harness records no per-channel recordsAfterWarmup and no per-route readiness map",
                "R2": "fresh project and down -v are enforced by the cell producer, not recorded as a gate input",
            },
            "g4ChannelScope": "ledger-only (no per-channel in-cell / total counts are recorded)",
            "thresholds": {
                "FLOOR": gates.FLOOR, "PRE_FAIL_MAX": gates.PRE_FAIL_MAX, "SCOPE_MIN": gates.SCOPE_MIN,
                "SCOPE_SLACK_S": gates.SCOPE_SLACK_S, "ONSET_TOLERANCE_S": gates.ONSET_TOLERANCE_S,
                "HOLD_TOLERANCE_S": gates.HOLD_TOLERANCE_S, "G1_MIN_DISPATCHED": gates.G1_MIN_DISPATCHED,
            },
            "stopRule": "first-invalid-cell",
        },
        "collection": {
            "applicationLogTimestamps": "docker-compose-logs-timestamps (application.log, every service)",
            "witnessLogs": "auth.log and persistence.log as frozen (docker logs --since/--until)",
            "witnessLogSecretScan": (
                "fail-closed raw-text secret scan of auth.log and persistence.log as frozen "
                "(modules/teastore/validation/secret_scan.py), except that a JVM stack-frame source location "
                "'(<File>.java|kt|scala|groovy:<ASCII digits>)' followed by whitespace or the end of the text, with "
                "a key of at most 256 characters, is not an assignment (sweep only; TeaStore relaunch 1 cell 11, "
                "2026-10-03); every other assignment, including a frame-shaped location with any other value or "
                "with text glued to its ')', still blocks the cell"
            ),
            "traces": "kieker AMQP spool and traces.json as frozen",
            "systemSamples": "cgroup-v2 system-samples.json in every cell as frozen",
        },
        "faultParameters": {
            "auth-freeze": {"target": "auth", "command": "docker compose pause auth",
                            "revert": "docker compose unpause auth"},
            "persistence-cpu-throttle": {
                "target": "persistence", "cpus": CPU_THROTTLE_CPUS, "nanoCpus": CPU_THROTTLE_NANOCPUS,
                "command": "docker update --cpus %s <persistence container>" % CPU_THROTTLE_CPUS,
                "revert": "docker update --cpus <docker info NCPU> <persistence container>",
                "revertRule": (
                    "docker update --cpus 0 is a no-op (Hotel LMT pilot, fb14srv4 2026-09-28), so the quota is "
                    "lifted to every host CPU instead of unset; the pre-state must be unset (0) or that value"
                ),
            },
        },
        "postureProof": {posture: base["postureProof"][posture] for posture in POSTURES},
        "queueProof": base["queueProof"],
        "missingness": base["missingness"],
        "outcomes": {
            **base["outcomes"],
            "costRegimeOnly": None,
            "primaryCostEndpoint": None,
        },
        "analysis": {
            "comparativeUnit": "(fault, rate); one episode each in this initial test",
            "descriptiveOnly": True,
            "detectionTimeMissCharge": "window-end (hold end), averaged over all episodes",
            "analysisCode": "research/detection-time/ (measurement repo), to be extended before the first cell",
            "forbidden": base["analysis"]["forbidden"],
        },
        "evidence": base["evidence"],
        "continuation": {
            **base["continuation"],
            "initialTestOnly": True,
        },
    }


def validate_descriptor(document: Any) -> Dict[str, Any]:
    if not isinstance(document, dict):
        raise ProtocolError("descriptor must be a JSON object")
    difference = frozen._first_difference(frozen_descriptor(), document)
    if difference:
        raise ProtocolError("descriptor differs from %s: %s" % (EPOCH, difference))
    return document


def load_descriptor(path: Path = DEFAULT_DESCRIPTOR) -> Dict[str, Any]:
    document = validate_descriptor(strict_json_file(path))
    digest = canonical_sha256(document)
    if digest != EXPECTED_DESCRIPTOR_SHA256:
        raise ProtocolError(
            "descriptor canonical digest differs from the reviewed freeze: expected %s, found %s"
            % (EXPECTED_DESCRIPTOR_SHA256, digest)
        )
    return document


def plan_body(document: Any) -> Dict[str, Any]:
    descriptor = validate_descriptor(document)
    blocks = []
    seen = set()
    for receipt in descriptor["schedule"]["blocks"]:
        number = receipt["block"]
        cells = []
        for position, pair in enumerate(block_order(number), start=1):
            regime, rate, posture = pair["regime"], pair["rate"], POSTURES[0]
            run_id = run_id_for(regime, rate, number, posture)
            if run_id != receipt["runIds"][position - 1] or run_id in seen:
                raise ProtocolError("compiled order differs from the descriptor's schedule receipt")
            seen.add(run_id)
            cells.append({
                "runId": run_id,
                "runKey": {
                    "studyEpoch": EPOCH, "regime": regime, "block": number,
                    "posture": posture, "attempt": 1,
                },
                "ordinalPosition": position,
                "artifactRoot": "%s/r%s/block-%02d/%s/attempt-01" % (
                    ARTIFACT_CLASSES[regime], rate_token(rate), number, posture),
                "fault": FAULTS[regime],
                "coldStart": True,
                "selectionId": None,
                "scheduledState": "not-started",
                "intendedEvidenceCeiling": CANDIDATE_LABEL,
                "mayReplaceFailedCell": False,
                "timing": cell_timing(run_id, regime, rate),
            })
        blocks.append({
            "block": number, "order": list(receipt["runIds"]),
            "orderSha256": receipt["orderSha256"], "cells": cells,
        })
    if len(seen) != TOTAL_RUNS:
        raise ProtocolError("compiled plan has %d runs, expected %d" % (len(seen), TOTAL_RUNS))
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
        "minimumFirstMutationRemainingSeconds": MINIMUM_FIRST_MUTATION_REMAINING_SECONDS,
        "runWindowHours": RUN_WINDOW_HOURS,
        "maximumWallSeconds": MAXIMUM_WALL_SECONDS,
        "scheduleVersion": SCHEDULE_CONTEXT,
        "scheduleAllocation": schedule_allocation(descriptor["schedule"]["blocks"]),
        "blocks": blocks,
        "analysisBoundary": copy.deepcopy(descriptor["analysis"]),
        "missingnessBoundary": copy.deepcopy(descriptor["missingness"]),
    }


def compile_plan(document: Any) -> Dict[str, Any]:
    body = plan_body(document)
    digest = canonical_sha256(body)
    if digest != EXPECTED_PLAN_SHA256:
        raise ProtocolError(
            "compiled plan digest differs from the reviewed freeze: expected %s, found %s"
            % (EXPECTED_PLAN_SHA256, digest)
        )
    return body


def validate_plan(document: Any, plan: Any) -> Dict[str, Any]:
    """Frozen-compiler signature: (descriptor, plan)."""
    expected = compile_plan(document)
    if not isinstance(plan, dict):
        raise ProtocolError("compiled plan must be a JSON object")
    difference = frozen._first_difference(expected, plan)
    if difference:
        raise ProtocolError("compiled plan differs from deterministic output: %s" % difference)
    return plan


def flatten_cells(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [cell for block in plan["blocks"] for cell in block["cells"]]


def compiled_cell(run_id: str, root: Path = ROOT) -> Dict[str, Any]:
    """The compiled plan cell for one run ID, from the descriptor at ``root`` (pinned digests checked)."""
    plan = compile_plan(load_descriptor(Path(root) / DESCRIPTOR_RELATIVE))
    for cell in flatten_cells(plan):
        if cell["runId"] == run_id:
            return cell
    raise ProtocolError("run ID %r is not in the compiled sweep plan" % (run_id,))


def descriptor_bytes() -> bytes:
    """The checked-in descriptor file: the frozen compiler's own rendering (indent 2, sorted keys)."""
    return (json.dumps(validate_descriptor(frozen_descriptor()), allow_nan=False, indent=2, sort_keys=True)
            + "\n").encode("utf-8")


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


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    parser.add_argument("--output", type=Path, help="write the compiled plan (refuses to overwrite)")
    parser.add_argument("--write-descriptor", type=Path)
    parser.add_argument("--print-digests", action="store_true",
                        help="print the unpinned descriptor and plan digests (for re-pinning after a change)")
    args = parser.parse_args(argv)
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
            frozen._write_json(plan, args.output)
    except ProtocolError as exc:
        parser.error(str(exc))
    print(json.dumps({
        "studyEpoch": plan["studyEpoch"],
        "descriptorCanonicalSha256": plan["descriptorSha256"],
        "planCanonicalSha256": canonical_sha256(plan),
        "runCount": plan["runCount"],
        "runWindowHours": plan["runWindowHours"],
        "minimumFirstMutationRemainingSeconds": plan["minimumFirstMutationRemainingSeconds"],
        "firstRunId": plan["blocks"][0]["cells"][0]["runId"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
