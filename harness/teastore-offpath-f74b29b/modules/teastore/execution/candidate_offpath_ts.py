#!/usr/bin/env python3
"""Compile the TeaStore off-path epoch (teastore-offpath-v1) without executing it.

A sixth epoch beside the frozen 27-cell pilot (``candidate_pilot.py``), the traffic sweep (``candidate_sweep.py``), the quiet
calibration (``candidate_quiet.py``), campaign B (``candidate_sweep_b.py``) and campaign C (``candidate_sweep_c.py``), all
of which this file only reads or leaves alone.  Authority: budget and stop rule
research/traffic-sweep/BUDGET_TEASTORE_OFFPATH.md (measurement repo, user 2026-10-13, committed alone before the work); plan
research/PLAN_LANES_20261014.md.

What it measures.  Three regimes of login-only traffic at two rates, five blocks:

* ``no-fault-cost``: no fault (the sweep's no-fault cell);
* ``recommender-pause-effect``: ``docker compose pause recommender`` for the hold.  The recommender is NOT on the login
  route (webui -> auth -> persistence, then the redirect to ``/`` which reads persistence and image): none of the login
  POST, the servlet it redirects to, or the services behind them calls it.  It is a registry client, so the registry drops
  it after the 10 s alive window (``Registry.heartBeatCleanup``, a WARN line "Removed ...recommender@... since it failed the
  heartbeat!" in the registry's own log, kept in ``application.log``) and its cgroup CPU stops (``system-samples.json``);
* ``auth-freeze-effect``: the on-path control, the sweep's own auth pause (same mechanism, same hold).

Cell shape: campaign B's.  ``cell_timing`` takes campaign B's own ``cell_timing`` of the same (regime, rate) (for the
recommender pause: B's auth-pause cell, the one pause cell B has) and replaces only what depends on this epoch's seeded
onset (``ONSET_TIMING_KEYS``: the three onset keys and the plan-derived phase floors of a fault cell) and, for the
recommender pause, the two keys that name the fault (``FAULT_TIMING_KEYS``: ``fault`` and ``faultTarget``).  So the route,
warm-up, measurement, hold, drain allowance, sampling, captures, posture ``full``, gates and the H10/H4 harness declaration
(``timing.faultHarness``) are B's by construction.  ``timing.applicationLogTimestamps`` is B's ``True``: ``application.log``
(``docker compose logs --timestamps``, every service including the registry) is written for every cell of this epoch, which
is what keeps the registry lines (tested).  The descriptor is generated from campaign B's pinned descriptor and differs from
it only where this epoch differs (tested).

Rates 10 and 1 login journeys/s (a subset of the sweep's {10, 1, 0.2, 0.05}), 5 blocks, 3 regimes: 30 cells, each block
holding every (regime, rate) pair once (6 cells) in a Fisher-Yates order drawn with SHA-256 from seed 20261014 under schedule
version ``offpath-schedule-v1`` (B's rule and draw encoding with this epoch's name, seed and version; no lead cell).  The
onset's stratified offset is drawn with the same seed and name over the 5 blocks of each (regime, rate) pair.  Run IDs are
B's shape with this epoch's name, ``teastore-offpath-v1/<regime>/r<rate>/b01..b05/full/a01``.

The plan keeps the sweep plan's schema (cells in ``blocks``), so the runtime replays it with the sweep's code:
``study_epoch.active`` reports this epoch as a sweep-mode epoch ("sweep": True) whose compiler is this file.  It is active only
when the committed selector ``modules/teastore/execution/study-epoch.json`` names it (activation is a separate commit).

Construction only: no Docker, SSH, subprocess, socket or transport surface.  Runs as ``python3 -I`` on CPython 3.9 on the
target: standard library only, sibling files are loaded by path (``-I`` drops this directory from ``sys.path``), no PEP 604
annotation evaluated at runtime.
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
DESCRIPTOR_RELATIVE = "pipelines/campaigns/teastore-offpath-v1.json"
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
# Campaign B's compiler supplies the cell shape (its cell timing, harness declaration and constants), the shuffle and onset
# rules this epoch re-draws with its own seed, and, through its pinned-digest check, the descriptor this epoch is derived
# from.  It is read, never edited; it reads the sweep compiler in turn.
b = _load("teastore_offpath_b_compiler_" + _TAG, HERE / "candidate_sweep_b.py")
sweep = b.sweep
frozen = b.frozen
gates = b.gates
ProtocolError = b.ProtocolError
AdmissionError = b.AdmissionError
canonical_sha256 = b.canonical_sha256
canonical_json_bytes = b.canonical_json_bytes
strict_json_loads = b.strict_json_loads
strict_json_file = b.strict_json_file
rate_token = b.rate_token
offered_for = b.offered_for

EPOCH = "teastore-offpath-v1"
PREDECESSOR_EPOCH = b.EPOCH                           # teastore-traffic-sweep-b-v1: the cell shape and harness this repeats
SUT_COMMIT = b.SUT_COMMIT
WORKLOAD = b.WORKLOAD
JOURNEY_KIND = b.JOURNEY_KIND

# ---------------------------------------------------------------- parameters (engineering defaults, BUDGET_TEASTORE_OFFPATH.md)
POSTURES = b.POSTURES                                 # ("full",)
RATES = (10.0, 1.0)                                   # login journeys/s, a subset of the sweep's set
REGIMES = ("no-fault-cost", "recommender-pause-effect", "auth-freeze-effect")
FAULTS = {
    "no-fault-cost": None,
    "recommender-pause-effect": "recommender-pause",  # off-path: docker compose pause recommender
    "auth-freeze-effect": "auth-freeze",              # on-path control: docker compose pause auth (the sweep's fault)
}
ARTIFACT_CLASSES = {
    "no-fault-cost": "cost",
    "recommender-pause-effect": "effect/recommender-pause",
    "auth-freeze-effect": "effect/auth-freeze",
}
# The one service each pause scenario pauses: the compiled plan's ``faultTarget``, which the fault controller checks against
# its own allow-list (performance_campaign.PAUSE_FAULT_SERVICES, tested equal).
FAULT_TARGETS = {"auth-freeze": "auth", "recommender-pause": "recommender"}
# The B regime whose cell this epoch's regime is shaped on.  The recommender pause is the auth pause with another target.
SHAPE_REGIMES = {
    "no-fault-cost": "no-fault-cost",
    "recommender-pause-effect": "auth-freeze-effect",
    "auth-freeze-effect": "auth-freeze-effect",
}
OMITTED_REGIMES = dict(b.OMITTED_REGIMES)
BLOCKS = 5
EPISODES = BLOCKS                                     # the name study_epoch.active() reads as blocksPerRegime
SCHEDULE_SEED = 20261014
SCHEDULE_CONTEXT = "offpath-schedule-v1"
ONSET_PHASE_OFFSET = b.ONSET_PHASE_OFFSET
WARMUP_SECONDS = b.WARMUP_SECONDS
MEASUREMENT_SECONDS = b.MEASUREMENT_SECONDS
FAULT_ONSET_BASE_SECONDS = b.FAULT_ONSET_BASE_SECONDS
TRACE_INCOMPLETE_FRACTION = b.TRACE_INCOMPLETE_FRACTION
FAULT_HARNESS = dict(b.FAULT_HARNESS)                 # H10 and H4 as in B (record-not-block, decision 69)
CELL_OVERHEAD_SECONDS = b.CELL_OVERHEAD_SECONDS
CELL_OVERHEAD_LOWER_SECONDS = b.CELL_OVERHEAD_LOWER_SECONDS
PREPARE_RESERVE_SECONDS = b.PREPARE_RESERVE_SECONDS
CLEANUP_RESERVE_SECONDS = b.CLEANUP_RESERVE_SECONDS
# Campaign C's runtime-journal recordedAt gaps (fb14srv5, 2026-10-11 02:20-05:44Z): the same host, harness and cell shape as
# this epoch's, so the best measure of this epoch's period.  Per (regime, rate) means are listed for the cells this epoch
# repeats; the recommender pause is the auth pause with another target and is assumed to take the auth pause's period (not
# measured: no recommender pause has run).
MEASURED_CELL_PERIOD_SECONDS = {
    "source": (
        "teastore-traffic-sweep-c-v1 (fb14srv5, 2026-10-11 02:20-05:44Z), consecutive runtime-journal recordedAt gaps over "
        "its 36 cells (all rates and regimes); the per-(regime, rate) means below are those of the cells this epoch repeats"
    ),
    "cells": 36, "gaps": 35, "minimum": 325.2, "median": 334.5, "mean": 348.6, "maximum": 446.3,
    "meanByRegimeAndRate": {
        "no-fault-cost/r10": 389.0, "no-fault-cost/r1": 335.5,
        "auth-freeze-effect/r10": 374.4, "auth-freeze-effect/r1": 334.2,
    },
    "recommenderPauseAssumedEqualTo": "auth-freeze-effect",
}
DECLARATION = (
    "research/traffic-sweep/DECLARATION_TEASTORE_OFFPATH.md (measurement repo; frozen and committed alone before the "
    "first cell)"
)
AUTHORITY = (
    "measurement repo research/traffic-sweep/BUDGET_TEASTORE_OFFPATH.md (user 2026-10-13, committed alone before the work) "
    "and research/PLAN_LANES_20261014.md: pause the recommender (off the login route), with the auth freeze as the on-path "
    "control; lanes read later under reader v3.3 (BUDGET_F.md step 4)"
)
# The sweep compiler, the sweep descriptor, campaign B's compiler and campaign B's descriptor are inputs of this compiler, so
# the runtime adapter digest-binds them beside this epoch's own descriptor.
ADDITIONAL_CONTROLLER_PATHS = {
    "sweep-compiler": "modules/teastore/execution/candidate_sweep.py",
    "sweep-descriptor": sweep.DESCRIPTOR_RELATIVE,
    "sweep-b-compiler": "modules/teastore/execution/candidate_sweep_b.py",
    "sweep-b-descriptor": b.DESCRIPTOR_RELATIVE,
    "offpath-descriptor": DESCRIPTOR_RELATIVE,
}
# ---------------------------------------------------------------- derived (B's rules over this epoch's cell count)

TOTAL_RUNS = len(REGIMES) * len(RATES) * BLOCKS
CELLS_PER_BLOCK = len(REGIMES) * len(RATES)
TIMED_SECONDS_PER_CELL = b.TIMED_SECONDS_PER_CELL
CELL_PERIOD_ESTIMATE_SECONDS = b.CELL_PERIOD_ESTIMATE_SECONDS
MINIMUM_TIMED_SECONDS = TOTAL_RUNS * (WARMUP_SECONDS + MEASUREMENT_SECONDS)
OPERATIONAL_ESTIMATE_SECONDS = {
    "lower": TOTAL_RUNS * (TIMED_SECONDS_PER_CELL + CELL_OVERHEAD_LOWER_SECONDS),
    "upper": TOTAL_RUNS * CELL_PERIOD_ESTIMATE_SECONDS,
}
MINIMUM_FIRST_MUTATION_REMAINING_SECONDS = OPERATIONAL_ESTIMATE_SECONDS["upper"] + CLEANUP_RESERVE_SECONDS
RUN_WINDOW_HOURS = int(math.ceil(
    (MINIMUM_FIRST_MUTATION_REMAINING_SECONDS + PREPARE_RESERVE_SECONDS) / 3600.0
))
MAXIMUM_WALL_SECONDS = RUN_WINDOW_HOURS * 3600
EXPECTED_DESCRIPTOR_SHA256 = "127e8263947c13799128c6ff4ff787d648ce967c54d09bfc3703a7409ffe2b76"
EXPECTED_PLAN_SHA256 = "5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a"

DESIGN_LABEL = b.DESIGN_LABEL
CANDIDATE_LABEL = b.CANDIDATE_LABEL


def _unit_draw(*parts: Any) -> float:
    return b._unit_draw(*parts)


def run_id_for(regime: str, rate: float, block: int, posture: str) -> str:
    """B's run-ID shape with this epoch's name: no run ID of this epoch equals one of any other epoch."""
    return "%s/%s/r%s/b%02d/%s/a01" % (EPOCH, regime, rate_token(rate), block, posture)


def _run_id_parts(run_id: str) -> Dict[str, Any]:
    parts = run_id.split("/") if isinstance(run_id, str) else []
    if (len(parts) != 6 or parts[0] != EPOCH or parts[1] not in REGIMES or not parts[2].startswith("r")
            or not parts[3].startswith("b") or not parts[3][1:].isdigit() or parts[4] not in POSTURES
            or parts[5] != "a01"):
        raise ProtocolError("run ID %r is not a teastore-offpath-v1 run ID" % (run_id,))
    return {"regime": parts[1], "rateToken": parts[2][1:], "block": int(parts[3][1:]), "posture": parts[4]}


def stratified_onset_offset(seed: Any, epoch: str, episodes: int, run_id: str, regime: str, rate: float,
                            block: int) -> float:
    """Campaign B's (the sweep's) stratified onset rule; B's function, called with this epoch's arguments."""
    return b.stratified_onset_offset(seed, epoch, episodes, run_id, regime, rate, block)


def onset_phase_offset(run_id: str, rate: float) -> float:
    if ONSET_PHASE_OFFSET != "seeded-stratified-within-one-inter-arrival":
        raise ProtocolError("teastore-offpath-v1 keeps the sweep's seeded stratified onset rule")
    parts = _run_id_parts(run_id)
    if parts["rateToken"] != rate_token(rate):
        raise ProtocolError("run ID %r was not compiled for rate %r" % (run_id, rate))
    return stratified_onset_offset(SCHEDULE_SEED, EPOCH, BLOCKS, run_id, parts["regime"], rate, parts["block"])


# The timing keys this epoch sets itself; every other key is campaign B's value of the shape cell (tested).
ONSET_TIMING_KEYS = frozenset({
    "faultOnsetPhaseOffsetSeconds", "faultOnsetSeconds", "scoredWindowSeconds", "minimumActualStartsByPhase",
})
# The two keys that name the fault: a recommender-pause cell differs from B's auth-pause cell in these and the onset keys only.
FAULT_TIMING_KEYS = frozenset({"fault", "faultTarget"})
OWN_TIMING_KEYS = ONSET_TIMING_KEYS | FAULT_TIMING_KEYS


def cell_timing(run_id: str, regime: str, rate: float) -> Dict[str, Any]:
    """Campaign B's cell timing of this regime's shape cell at ``rate``, with this epoch's onset and fault name."""
    if regime not in REGIMES or float(rate) not in RATES:
        raise ProtocolError("teastore-offpath-v1 compiles its own regimes and rates only")
    shape = SHAPE_REGIMES[regime]
    timing = b.cell_timing(b.run_id_for(shape, rate, 1, POSTURES[0]), shape, rate)
    fault = FAULTS[regime]
    if (timing["faultApplied"] is not (fault is not None)
            or timing["faultHarness"] != (FAULT_HARNESS if fault is not None else None)
            or (fault is not None and timing["fault"] != "auth-freeze")):
        raise ProtocolError("campaign B's cell shape changed")
    if fault is not None:
        timing["fault"] = fault
        timing["faultTarget"] = FAULT_TARGETS[fault]
    offset = onset_phase_offset(run_id, rate)
    onset = round(FAULT_ONSET_BASE_SECONDS + offset, 6)
    hold = timing["faultHoldSeconds"]
    if not 0 < onset < onset + hold + timing["postRecoveryAllowanceSeconds"] < timing["measurementSeconds"]:
        raise ProtocolError("fault window must lie strictly inside the measurement")
    timing.update({
        "faultOnsetPhaseOffsetSeconds": offset,
        "faultOnsetSeconds": onset,
        "scoredWindowSeconds": [onset, round(onset + hold, 6)],
        "minimumActualStartsByPhase": (
            sweep.phase_floors(rate, timing["measurementSeconds"], onset, hold) if fault is not None else None),
    })
    if timing["applicationLogTimestamps"] is not True:
        # application.log carries the registry's own lines, the coordinator-side lane of this epoch.
        raise ProtocolError("this epoch retains application.log in every cell")
    return timing


def fisher_yates(pairs: List[Dict[str, Any]], seed: Any, epoch: str, block: int, context: str) -> List[Dict[str, Any]]:
    """Campaign B's block shuffle (the sweep's, before its lead-cell move); B's function."""
    return b.fisher_yates(pairs, seed, epoch, block, context)


def block_order(block: int) -> List[Dict[str, Any]]:
    """Every (regime, rate) pair once in this block, Fisher-Yates shuffled by SHA-256 draws; no lead cell."""
    if not 1 <= int(block) <= BLOCKS:
        raise ProtocolError("block %r is outside 1..%d" % (block, BLOCKS))
    return fisher_yates(
        [{"regime": regime, "rate": float(rate)} for regime in REGIMES for rate in RATES],
        SCHEDULE_SEED, EPOCH, int(block), SCHEDULE_CONTEXT,
    )


def allocate_schedule() -> List[Dict[str, Any]]:
    """The schedule receipt: per block, the run IDs in execution order."""
    if POSTURES != ("full",):
        raise ProtocolError("teastore-offpath-v1 runs the full posture only")
    if len(set(RATES)) != len(RATES) or any(not (math.isfinite(rate) and rate > 0) for rate in RATES):
        raise ProtocolError("rates must be distinct, finite and positive")
    if not set(RATES) <= set(b.RATES):
        raise ProtocolError("rates must come from the sweep's set")
    if set(REGIMES) != set(FAULTS) or set(REGIMES) != set(ARTIFACT_CLASSES) or set(REGIMES) != set(SHAPE_REGIMES):
        raise ProtocolError("regime tables differ")
    blocks = []
    for block in range(1, BLOCKS + 1):
        run_ids = [run_id_for(row["regime"], row["rate"], block, POSTURES[0]) for row in block_order(block)]
        blocks.append({"block": block, "runIds": run_ids, "orderSha256": canonical_sha256(run_ids)})
    every = [run_id for row in blocks for run_id in row["runIds"]]
    if len(every) != TOTAL_RUNS or len(set(every)) != TOTAL_RUNS:
        raise ProtocolError("schedule does not contain every cell exactly once")
    return blocks


def schedule_allocation(schedule: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """The sweep's (and B's) ``scheduleAllocation`` shape: regime -> selector digest and per-block postures."""
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


def frozen_descriptor() -> Dict[str, Any]:
    """The teastore-offpath-v1 descriptor, generated from campaign B's pinned descriptor.

    Named like the sweep's and B's generator, because the shared producer code calls it.  This function IS the descriptor's
    source: the checked-in teastore-offpath-v1.json must equal ``descriptor_bytes()`` (tested), so the file is regenerated,
    never hand-edited.  Carried over unchanged from B: schemaVersion, status, module, targetHost, source, workload (but its
    rate levels), runIdentity, systemSamples, postureProof, queueProof, missingness, evidence, protocolGates and, in
    ``timing``, the H10/H4 declaration, doses of the hold, drain allowance and trace-completeness rules.  Replaced: id,
    declaration, design, the schedule, the budget and rate-dependent timing, the pause contracts and fault parameters,
    collection (+ registry lines), outcomes (lanes), analysis and continuation; added: derivedFrom.
    """
    path = b.DEFAULT_DESCRIPTOR
    base = b.load_descriptor(path)                    # B's own pinned-digest check
    if base["id"] != PREDECESSOR_EPOCH:
        raise ProtocolError("teastore-offpath-v1 is derived from campaign B's descriptor only")
    document = copy.deepcopy(base)
    document["id"] = EPOCH
    document["declaration"] = DECLARATION
    document["workload"]["journeysPerSecondLevels"] = list(RATES)
    design = document["design"]
    design.update({
        "purpose": (
            "off-path pause: pause the recommender (not on the login route) with the auth freeze as the on-path control, "
            "login-only traffic at 10 and 1 journeys/s, 5 blocks; lanes: the registry's heartbeat-removal log line and the "
            "paused container's cgroup CPU (BUDGET_TEASTORE_OFFPATH.md, PLAN_LANES_20261014.md)"
        ),
        "regimes": [
            {"id": regime,
             "kind": "no-fault-calibration" if FAULTS[regime] is None else "effect",
             "fault": FAULTS[regime], "artifactRootClass": ARTIFACT_CLASSES[regime],
             **({} if FAULTS[regime] is None else {
                 "pathRelation": "off-path" if regime == "recommender-pause-effect" else "on-path-control"})}
            for regime in REGIMES
        ],
        "rates": list(RATES),
        "episodesPerRegimeAndRate": BLOCKS,
        "blocks": BLOCKS,
        "cellsPerBlock": CELLS_PER_BLOCK,
        "totalRuns": TOTAL_RUNS,
        "cellShape": (
            "campaign B's cell of the same regime and rate (candidate_sweep_b.cell_timing; the recommender pause is shaped "
            "on B's auth-pause cell); only the seeded onset (faultOnsetPhaseOffsetSeconds, faultOnsetSeconds, "
            "scoredWindowSeconds), the plan-derived phase floors that follow from it, and for the recommender pause the "
            "fault name and target (fault, faultTarget) differ"
        ),
        "faultDoses": (
            "pause on the target for the hold: recommender (off-path) and auth (the sweep's fault, on-path control); the "
            "pause target is the allow-list {auth, recommender} of the fault controller"
        ),
    })
    timing = document["timing"]
    timing["faultOnsetStrata"] = BLOCKS
    timing["offeredByRate"] = {rate_token(rate): offered_for(rate, MEASUREMENT_SECONDS) for rate in RATES}
    timing["minimumTimedSeconds"] = MINIMUM_TIMED_SECONDS
    timing["operationalEstimateSeconds"] = dict(OPERATIONAL_ESTIMATE_SECONDS)
    timing["budget"].update({
        "minimumFirstMutationRemainingSeconds": MINIMUM_FIRST_MUTATION_REMAINING_SECONDS,
        "runWindowHours": RUN_WINDOW_HOURS,
        "maximumWallSeconds": MAXIMUM_WALL_SECONDS,
        "measuredCellPeriodSeconds": copy.deepcopy(MEASURED_CELL_PERIOD_SECONDS),
    })
    document["schedule"] = {
        "version": SCHEDULE_CONTEXT,
        "seed": SCHEDULE_SEED,
        "shuffle": "fisher-yates-over-regimes-x-rates-with-sha256-draws",
        "drawEncoding": "UTF-8(seed || NUL || epoch || NUL || block-NN || NUL || draw-i || NUL || version)",
        "leadCell": None,
        "blocks": allocate_schedule(),
    }
    contracts = [row for row in document["groundTruth"]["fault"]["scenarioContracts"] if row["scenario"] == "auth-freeze"]
    contracts.append({
        **copy.deepcopy(contracts[0]),
        "scenario": "recommender-pause", "service": "recommender",
    })
    document["groundTruth"]["fault"]["scenarioContracts"] = contracts
    document["groundTruth"]["fault"]["pathRelation"] = {
        "auth-freeze": "on-path: the login POST calls auth, which calls persistence",
        "recommender-pause": (
            "off-path by the code of the pinned SUT (the login POST, the redirect's index page and the services behind "
            "them do not call the recommender; webui reaches it only from product, cart and status pages); the epoch "
            "records what happens, it does not assume it: a pause that fails journeys is reported as observed "
            "(BUDGET_TEASTORE_OFFPATH.md stop rule 4)"
        ),
    }
    document["faultParameters"] = {
        "auth-freeze": copy.deepcopy(base["faultParameters"]["auth-freeze"]),
        "recommender-pause": {"target": "recommender", "command": "docker compose pause recommender",
                              "revert": "docker compose unpause recommender"},
    }
    document["collection"]["freezeStamps"] = (
        "fault cells: intervention.json sweep.freezeStamps (Docker pause/unpause events of the paused container, command "
        "and applied-state readback stamps) and sweep.probePolicy"
    )
    document["collection"]["registryLog"] = (
        "application.log (docker compose logs --timestamps, every service) keeps the registry's own lines, among them the "
        "heartbeat removal ('Removed <service>@<host> since it failed the heartbeat!', Registry.heartBeatCleanup, alive "
        "window 10 s, clients heartbeat every 2.5 s) and the later registration; the validator requires timestamped lines "
        "of the five application services"
    )
    document["outcomes"] = {
        **copy.deepcopy(base["outcomes"]),
        "primary": (
            "per fault and rate, repeated over blocks: the coordinator-side lane (registry heartbeat-removal line) and the "
            "own-silence lane (cgroup CPU of the paused container), each against its no-fault cells"
        ),
    }
    document["analysis"] = {
        "comparativeUnit": "(fault, rate); 5 episodes each in this epoch; the recommender pause is off-path, the auth freeze is the on-path control",
        "detectionTimeMissCharge": base["analysis"]["detectionTimeMissCharge"],
        "analysisFreeze": (
            "no cell of this epoch is read beyond its validity before reader v3.3 is frozen (BUDGET_F.md step 4; "
            "BUDGET_TEASTORE_OFFPATH.md step 4)"
        ),
        "analysisCode": "reader v3.3 of the measurement repo, fixed before any cell of this epoch is read",
        "forbidden": copy.deepcopy(base["analysis"]["forbidden"]),
    }
    continuation = copy.deepcopy(base["continuation"])
    continuation.pop("repeatOfSweepEpoch")
    continuation["offPathPauseOfEpoch"] = PREDECESSOR_EPOCH
    continuation["furtherBlocksRequireNewPreOutcomeEpoch"] = True
    document["continuation"] = continuation
    document["derivedFrom"] = {
        "authority": AUTHORITY,
        "studyEpoch": PREDECESSOR_EPOCH,
        "descriptorPath": b.DESCRIPTOR_RELATIVE,
        "descriptorByteSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "descriptorCanonicalSha256": canonical_sha256(base),
        "planCanonicalSha256": b.EXPECTED_PLAN_SHA256,
        "sweepDerivation": copy.deepcopy(base["derivedFrom"]),
        "disposition": (
            "the sweep, quiet, campaign-B and campaign-C epochs are not superseded: each keeps its own descriptor, plan and "
            "admission history; this epoch is a separate epoch selected by modules/teastore/execution/study-epoch.json"
        ),
    }
    return document


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


def _check_geometry(plan: Dict[str, Any]) -> None:
    cells = flatten_cells(plan)
    if (plan.get("runCount") != TOTAL_RUNS or len(cells) != TOTAL_RUNS
            or len({cell["runId"] for cell in cells}) != TOTAL_RUNS):
        raise ProtocolError("compiled plan does not hold exactly %d distinct cells" % TOTAL_RUNS)
    if [block["block"] for block in plan["blocks"]] != list(range(1, BLOCKS + 1)):
        raise ProtocolError("compiled plan blocks are not 1..%d in order" % BLOCKS)
    expected_pairs = sorted((regime, float(rate)) for regime in REGIMES for rate in RATES)
    for block in plan["blocks"]:
        pairs = sorted((cell["runKey"]["regime"], cell["timing"]["journeysPerSecond"]) for cell in block["cells"])
        if pairs != expected_pairs:
            raise ProtocolError("block %r does not hold every (regime, rate) pair exactly once" % block["block"])
    for cell in cells:
        fault = FAULTS[cell["runKey"]["regime"]]
        timing = cell["timing"]
        if (cell["fault"] != fault or timing["fault"] != fault or timing["faultApplied"] is not (fault is not None)
                or (timing["faultHarness"] is not None) is not (fault is not None)
                or timing["faultTarget"] != (FAULT_TARGETS[fault] if fault is not None else None)
                or timing["applicationLogTimestamps"] is not True):
            raise ProtocolError("cell %s disagrees with its regime's fault, target or harness declaration" % cell["runId"])


def compile_plan(document: Any) -> Dict[str, Any]:
    body = plan_body(document)
    _check_geometry(body)
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
    raise ProtocolError("run ID %r is not in the compiled teastore-offpath-v1 plan" % (run_id,))


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
            body = plan_body(descriptor)
            _check_geometry(body)
            print(json.dumps({
                "studyEpoch": EPOCH,
                "descriptorCanonicalSha256": canonical_sha256(descriptor),
                "planCanonicalSha256": canonical_sha256(body),
                "runCount": TOTAL_RUNS,
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
