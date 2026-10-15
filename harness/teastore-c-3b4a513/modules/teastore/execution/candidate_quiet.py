#!/usr/bin/env python3
"""Compile the TeaStore quiet calibration epoch (teastore-quiet-calibration-v1) without executing it.

A third epoch beside the frozen 27-cell pilot (``candidate_pilot.py``, teastore-candidate-pilot-sys-v1) and the traffic
sweep (``candidate_sweep.py``, teastore-traffic-sweep-v1, relaunch 2 terminal-valid 12/12 on 2026-10-04), both of which
this file only reads.  Authority: measurement repo research/PROTOCOL_DRAFT_20261002.md decision 48 (user 2026-10-04: a
quiet calibration run at <= 6/h, 40 no-fault cells per system, 10 per rate x 4 rates, the sweep's cell shape); budget
and stop rule research/traffic-sweep/BUDGET_CALIBRATION.md (committed alone before the work).

Every cell is the sweep's no-fault calibration cell: ``cell_timing`` takes the sweep compiler's own
``cell_timing(<the sweep's no-fault run ID at that rate>, "no-fault-cost", rate)`` and replaces only the seeded onset of
the pseudo window (the sweep's stratified rule, drawn with this epoch's seed and name over its 10 blocks), i.e. the
three keys in ``OWN_TIMING_KEYS``.  Route, rates, client timeout, concurrency, warm-up, measurement, hold, sampling,
capture flags, the Q3 drain rule (none in a no-fault cell), decision 25's trace-completeness rule, the JVM-frame scanner
of 0588a41 and the protocol gates are the sweep's, by construction.  No fault is applied in any cell.  The regime id is
the sweep's ``no-fault-cost``, so every regime-keyed reader (the frozen no-fault path with its performance probe and
``resources.json``, the terminal's required artifacts) is unchanged.

Schedule: 10 blocks; each block holds every rate exactly once, in a Fisher-Yates order drawn with SHA-256 from seed
20261004 (the sweep's block rule and draw encoding with this epoch's name and schedule version; no lead cell).  The
seed and the draw encoding are recorded in the descriptor (``schedule``), every block's order in the descriptor and in
the compiled plan (``blocks[].order``).

The plan keeps the sweep plan's schema (the frozen plan's top-level keys, cells in ``blocks``), so the orchestrator,
adapter, transport, installer and validators replay it with the sweep's code: ``study_epoch.active`` reports this epoch
as a sweep-mode epoch ("sweep": True) whose compiler is this file.  It is active only when the committed selector
``modules/teastore/execution/study-epoch.json`` names it.

Construction only: no Docker, SSH, subprocess, socket or transport surface.  Runs as ``python3 -I`` on CPython 3.9 on
the target: standard library only, sibling files are loaded by path (``-I`` drops this directory from ``sys.path``),
no PEP 604 annotation evaluated at runtime.
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
DESCRIPTOR_RELATIVE = "pipelines/campaigns/teastore-quiet-calibration-v1.json"
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
# The sweep compiler supplies the cell shape (its no-fault cell timing), the onset and shuffle rules this epoch
# re-draws with its own seed, the JSON helpers and, through its pinned-digest check, the descriptor this epoch is
# derived from.  It is read, never edited.
sweep = _load("teastore_quiet_sweep_compiler_" + _TAG, HERE / "candidate_sweep.py")
frozen = sweep.frozen
gates = sweep.gates
ProtocolError = sweep.ProtocolError
AdmissionError = sweep.AdmissionError
canonical_sha256 = sweep.canonical_sha256
canonical_json_bytes = sweep.canonical_json_bytes
strict_json_loads = sweep.strict_json_loads
strict_json_file = sweep.strict_json_file
rate_token = sweep.rate_token
offered_for = sweep.offered_for

EPOCH = "teastore-quiet-calibration-v1"
PREDECESSOR_EPOCH = sweep.EPOCH                       # teastore-traffic-sweep-v1: the cell shape this epoch repeats
SUT_COMMIT = sweep.SUT_COMMIT
WORKLOAD = sweep.WORKLOAD
JOURNEY_KIND = sweep.JOURNEY_KIND

# ---------------------------------------------------------------- parameters (decision 48, user 2026-10-04)
POSTURES = sweep.POSTURES                             # ("full",)
RATES = sweep.RATES                                   # 10, 1, 0.2, 0.05 login journeys/s
REGIME = "no-fault-cost"                              # the sweep's no-fault regime id; every regime-keyed reader keys on it
REGIMES = (REGIME,)
FAULTS = {REGIME: None}
ARTIFACT_CLASSES = {REGIME: sweep.ARTIFACT_CLASSES[REGIME]}
BLOCKS = 10                                           # 10 cells per rate x 180 s = 30 min of quiet time per rate
EPISODES = BLOCKS                                     # the name study_epoch.active() reads as blocksPerRegime
SCHEDULE_SEED = 20261004
SCHEDULE_CONTEXT = "quiet-schedule-v1"
# The pseudo window's onset follows the sweep's rule (60 s + a seeded offset, stratified over the blocks of one
# (regime, rate) pair inside one inter-arrival); with 10 blocks there are 10 strata per rate.
ONSET_PHASE_OFFSET = sweep.ONSET_PHASE_OFFSET
WARMUP_SECONDS = sweep.WARMUP_SECONDS
MEASUREMENT_SECONDS = sweep.MEASUREMENT_SECONDS
FAULT_ONSET_BASE_SECONDS = sweep.FAULT_ONSET_BASE_SECONDS
TRACE_INCOMPLETE_FRACTION = sweep.TRACE_INCOMPLETE_FRACTION
# Wall budget: the sweep's rule and engineering defaults (225 s timed + 300 s overhead = 525 s per cell), checked
# against sweep relaunch 2 (fb14srv5, 2026-10-04): the 11 consecutive runtime-journal recordedAt gaps over its 12 cells
# are 324.9-423.4 s (median 330.5, mean 343.2), all below the 525 s estimate.
CELL_OVERHEAD_SECONDS = sweep.CELL_OVERHEAD_SECONDS
CELL_OVERHEAD_LOWER_SECONDS = sweep.CELL_OVERHEAD_LOWER_SECONDS
PREPARE_RESERVE_SECONDS = sweep.PREPARE_RESERVE_SECONDS
CLEANUP_RESERVE_SECONDS = sweep.CLEANUP_RESERVE_SECONDS
MEASURED_CELL_PERIOD_SECONDS = {
    "source": (
        "teastore-traffic-sweep-v1 relaunch 2 (fb14srv5, 2026-10-04 07:53-08:57Z), consecutive runtime-journal "
        "recordedAt gaps"
    ),
    "cells": 12, "gaps": 11, "minimum": 324.9, "median": 330.5, "mean": 343.2, "maximum": 423.4,
}
DECLARATION = (
    "research/traffic-sweep/DECLARATION_QUIET_TEASTORE.md (measurement repo; frozen and committed alone before the "
    "first cell)"
)
AUTHORITY = (
    "measurement repo research/PROTOCOL_DRAFT_20261002.md decision 48 (user 2026-10-04: quiet calibration run at "
    "<= 6/h, 40 no-fault cells per system, 10 per rate x 4 rates, same cell shape as the sweep); budget and stop rule "
    "research/traffic-sweep/BUDGET_CALIBRATION.md (committed alone before the work); proposal "
    "research/traffic-sweep/NEXT_CAMPAIGNS_PROPOSAL.md section A"
)
# The sweep compiler and the sweep descriptor are inputs of this compiler, so the runtime adapter digest-binds them
# beside this epoch's own descriptor (study_epoch.active() hands these to the adapter's controller set).
ADDITIONAL_CONTROLLER_PATHS = {
    "sweep-compiler": "modules/teastore/execution/candidate_sweep.py",
    "sweep-descriptor": sweep.DESCRIPTOR_RELATIVE,
    "quiet-descriptor": DESCRIPTOR_RELATIVE,
}
# ---------------------------------------------------------------- derived

TOTAL_RUNS = len(REGIMES) * len(RATES) * BLOCKS
CELLS_PER_BLOCK = len(REGIMES) * len(RATES)
QUIET_SECONDS_PER_RATE = BLOCKS * MEASUREMENT_SECONDS
TIMED_SECONDS_PER_CELL = sweep.TIMED_SECONDS_PER_CELL
CELL_PERIOD_ESTIMATE_SECONDS = sweep.CELL_PERIOD_ESTIMATE_SECONDS
MINIMUM_TIMED_SECONDS = TOTAL_RUNS * (WARMUP_SECONDS + MEASUREMENT_SECONDS)
OPERATIONAL_ESTIMATE_SECONDS = {
    "lower": TOTAL_RUNS * (TIMED_SECONDS_PER_CELL + CELL_OVERHEAD_LOWER_SECONDS),
    "upper": TOTAL_RUNS * CELL_PERIOD_ESTIMATE_SECONDS,
}
# The sweep's rule (the frozen epoch's: the upper estimate + the cleanup reserve).
MINIMUM_FIRST_MUTATION_REMAINING_SECONDS = OPERATIONAL_ESTIMATE_SECONDS["upper"] + CLEANUP_RESERVE_SECONDS
# Whole hours, because the gate driver's GATE-RUN deadline is RUN_WINDOW_HOURS after approval.
RUN_WINDOW_HOURS = int(math.ceil(
    (MINIMUM_FIRST_MUTATION_REMAINING_SECONDS + PREPARE_RESERVE_SECONDS) / 3600.0
))
MAXIMUM_WALL_SECONDS = RUN_WINDOW_HOURS * 3600
EXPECTED_DESCRIPTOR_SHA256 = "338226d05f8e9d3557918ef9120727094bd71532f4eba72cc9191070f102315b"
EXPECTED_PLAN_SHA256 = "879a81ab0c3f2e960ee11a282c8200e58b98e97bc8a541cbcc5704654f858266"

DESIGN_LABEL = sweep.DESIGN_LABEL
CANDIDATE_LABEL = sweep.CANDIDATE_LABEL


def _unit_draw(*parts: Any) -> float:
    return sweep._unit_draw(*parts)


def run_id_for(regime: str, rate: float, block: int, posture: str) -> str:
    """The sweep's run-ID shape with this epoch's name: no quiet run ID can equal a sweep run ID."""
    return "%s/%s/r%s/b%02d/%s/a01" % (EPOCH, regime, rate_token(rate), block, posture)


def _run_id_parts(run_id: str) -> Dict[str, Any]:
    parts = run_id.split("/") if isinstance(run_id, str) else []
    if (len(parts) != 6 or parts[0] != EPOCH or parts[1] not in REGIMES or not parts[2].startswith("r")
            or not parts[3].startswith("b") or not parts[3][1:].isdigit() or parts[4] not in POSTURES
            or parts[5] != "a01"):
        raise ProtocolError("run ID %r is not a quiet-calibration run ID" % (run_id,))
    return {"regime": parts[1], "rateToken": parts[2][1:], "block": int(parts[3][1:]), "posture": parts[4]}


def stratified_onset_offset(seed: Any, epoch: str, episodes: int, run_id: str, regime: str, rate: float,
                            block: int) -> float:
    """The sweep's onset_phase_offset with its seed, epoch, stratum count and run ID as arguments.

    The ``episodes`` blocks of one (regime, rate) pair take the ``episodes`` equal strata of one inter-arrival in a
    seeded order, uniform inside the stratum.  Given the sweep's values it reproduces the sweep's own offsets (tested).
    """
    if not 1 <= int(block) <= int(episodes):
        raise ProtocolError("block %r is outside 1..%d" % (block, episodes))
    inter_arrival = 1.0 / float(rate)
    strata = sorted(range(int(episodes)), key=lambda stratum: _unit_draw(
        seed, epoch, regime, rate_token(rate), "onset-stratum", stratum))
    stratum = strata[int(block) - 1]
    position = _unit_draw(seed, epoch, run_id, "onset-phase")
    offset = round((stratum + position) / int(episodes) * inter_arrival, 6)
    return min(offset, round(inter_arrival - 1e-6, 6))


def onset_phase_offset(run_id: str, rate: float) -> float:
    if ONSET_PHASE_OFFSET != "seeded-stratified-within-one-inter-arrival":
        raise ProtocolError("the quiet epoch keeps the sweep's seeded stratified onset rule")
    parts = _run_id_parts(run_id)
    if parts["rateToken"] != rate_token(rate):
        raise ProtocolError("run ID %r was not compiled for rate %r" % (run_id, rate))
    return stratified_onset_offset(SCHEDULE_SEED, EPOCH, BLOCKS, run_id, parts["regime"], rate, parts["block"])


def cell_timing(run_id: str, regime: str, rate: float) -> Dict[str, Any]:
    """The sweep's no-fault cell timing at ``rate``, with this epoch's pseudo-window onset."""
    if regime != REGIME or FAULTS.get(regime, "unknown") is not None:
        raise ProtocolError("the quiet epoch compiles no-fault cells only")
    timing = sweep.cell_timing(sweep.run_id_for(REGIME, rate, 1, POSTURES[0]), REGIME, rate)
    if (timing["faultApplied"] is not False or timing["fault"] is not None
            or timing["minimumActualStartsByPhase"] is not None or timing["drainAllowanceSeconds"] is not None):
        raise ProtocolError("the sweep's no-fault cell shape changed")
    offset = onset_phase_offset(run_id, rate)
    onset = round(FAULT_ONSET_BASE_SECONDS + offset, 6)
    hold = timing["faultHoldSeconds"]
    if not 0 < onset < onset + hold + timing["postRecoveryAllowanceSeconds"] < timing["measurementSeconds"]:
        raise ProtocolError("pseudo window must lie strictly inside the measurement")
    timing.update({
        "faultOnsetPhaseOffsetSeconds": offset,
        "faultOnsetSeconds": onset,
        "scoredWindowSeconds": [onset, round(onset + hold, 6)],
    })
    return timing


# The timing keys this epoch sets itself; every other key is the sweep's no-fault value (tested).
OWN_TIMING_KEYS = frozenset({"faultOnsetPhaseOffsetSeconds", "faultOnsetSeconds", "scoredWindowSeconds"})


def fisher_yates(pairs: List[Dict[str, Any]], seed: Any, epoch: str, block: int, context: str) -> List[Dict[str, Any]]:
    """The sweep's block shuffle (block_order before its lead-cell move), with seed, epoch and context as arguments."""
    pairs = [dict(row) for row in pairs]
    for index in range(len(pairs) - 1, 0, -1):
        draw = int(hashlib.sha256(
            ("%s\0%s\0block-%02d\0draw-%d\0%s" % (seed, epoch, block, index, context)).encode("utf-8")
        ).hexdigest(), 16)
        other = draw % (index + 1)
        pairs[index], pairs[other] = pairs[other], pairs[index]
    return pairs


def block_order(block: int) -> List[Dict[str, Any]]:
    """Every rate once in this block, Fisher-Yates shuffled by SHA-256 draws keyed by seed and block; no lead cell."""
    if not 1 <= int(block) <= BLOCKS:
        raise ProtocolError("block %r is outside 1..%d" % (block, BLOCKS))
    return fisher_yates(
        [{"regime": regime, "rate": float(rate)} for regime in REGIMES for rate in RATES],
        SCHEDULE_SEED, EPOCH, int(block), SCHEDULE_CONTEXT,
    )


def allocate_schedule() -> List[Dict[str, Any]]:
    """The schedule receipt: per block, the run IDs in execution order."""
    if POSTURES != ("full",):
        raise ProtocolError("the quiet calibration runs the full posture only")
    if len(set(RATES)) != len(RATES) or any(not (math.isfinite(rate) and rate > 0) for rate in RATES):
        raise ProtocolError("rates must be distinct, finite and positive")
    if set(REGIMES) != set(FAULTS) or set(REGIMES) != set(ARTIFACT_CLASSES) or any(FAULTS.values()):
        raise ProtocolError("the quiet epoch holds the no-fault regime only")
    blocks = []
    for block in range(1, BLOCKS + 1):
        run_ids = [run_id_for(row["regime"], row["rate"], block, POSTURES[0]) for row in block_order(block)]
        blocks.append({"block": block, "runIds": run_ids, "orderSha256": canonical_sha256(run_ids)})
    every = [run_id for row in blocks for run_id in row["runIds"]]
    if len(every) != TOTAL_RUNS or len(set(every)) != TOTAL_RUNS:
        raise ProtocolError("schedule does not contain every cell exactly once")
    return blocks


def schedule_allocation(schedule: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """The sweep's (and the frozen) ``scheduleAllocation`` shape: regime -> selector digest and per-block postures."""
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
    """The quiet descriptor, generated from the pinned sweep descriptor.

    Named like the sweep's (and the frozen compiler's) generator, because the shared producer code calls it.  This
    function IS the descriptor's source: the checked-in teastore-quiet-calibration-v1.json must equal
    ``descriptor_bytes()`` (tested), so the file is regenerated, never hand-edited.  Carried over unchanged from the
    sweep: schemaVersion, status, module, targetHost, source, workload, runIdentity, groundTruth (its fault contracts
    are inherited and unused: no quiet cell has a fault), systemSamples, collection, faultParameters (likewise),
    postureProof, queueProof, missingness, evidence.  Replaced: id, declaration, design, timing (budget, strata, lead
    cell), schedule, outcomes, analysis, continuation, protocolGates.blocking; added: derivedFrom.
    """
    path = sweep.DEFAULT_DESCRIPTOR
    base = sweep.load_descriptor(path)                # the sweep's own pinned-digest check
    if base["id"] != PREDECESSOR_EPOCH:
        raise ProtocolError("the quiet epoch is derived from the sweep descriptor only")
    schedule = allocate_schedule()
    document = copy.deepcopy(base)
    document["id"] = EPOCH
    document["declaration"] = DECLARATION
    omitted = {
        regime["id"]: "fault regime of the sweep; this epoch applies no fault (decision 48)"
        for regime in base["design"]["regimes"] if regime["fault"] is not None
    }
    omitted.update(copy.deepcopy(base["design"]["omittedRegimes"]))
    document["design"] = {
        "purpose": (
            "false-alarm calibration: certify a false-alarm rate <= 6/h per rate (95 %, 0 alarms: 3 / quiet hours) on "
            "no-fault time (research/PROTOCOL_DRAFT_20261002.md decision 48)"
        ),
        "postures": list(POSTURES),
        "selectedSource": None,
        "regimes": [
            {"id": REGIME, "kind": "no-fault-calibration", "fault": None, "artifactRootClass": ARTIFACT_CLASSES[REGIME]}
        ],
        "omittedRegimes": omitted,
        "rates": list(RATES),
        "episodesPerRate": BLOCKS,
        "blocks": BLOCKS,
        "cellsPerBlock": CELLS_PER_BLOCK,
        "totalRuns": TOTAL_RUNS,
        "quietSecondsPerRate": QUIET_SECONDS_PER_RATE,
        "blockRule": "each-block-holds-every-rate-exactly-once",
        "coldStartEachRun": True,
        "deploymentQueueAttemptArtifactReuse": False,
        "faultAppliedToAnyCell": False,
        "noFaultCellsCarryPseudoWindow": True,
        "cellShape": (
            "the sweep's no-fault calibration cell (candidate_sweep.cell_timing(<sweep run ID>, 'no-fault-cost', "
            "rate)); only the pseudo window's seeded onset differs (faultOnsetPhaseOffsetSeconds, faultOnsetSeconds, "
            "scoredWindowSeconds)"
        ),
        "noFaultRegimeReusesFrozenPath": base["design"]["noFaultRegimeReusesFrozenPath"],
    }
    timing = document["timing"]
    timing["leadCell"] = None
    timing["faultOnsetStrata"] = BLOCKS
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
        "shuffle": "fisher-yates-over-rates-within-each-block-with-sha256-draws",
        "drawEncoding": "UTF-8(seed || NUL || epoch || NUL || block-NN || NUL || draw-i || NUL || version)",
        "leadCell": None,
        "blocks": schedule,
    }
    document["outcomes"] = {
        **copy.deepcopy(base["outcomes"]),
        "primary": (
            "quiet time per rate, for the false-alarm rate per hour of each detector at a common operating point "
            "(decisions 33 and 48); with 0 alarms in T quiet hours the 95 % upper bound is 3 / T per hour"
        ),
    }
    document["analysis"] = {
        "comparativeUnit": "rate; 10 no-fault cells per rate",
        "analysisFreeze": (
            "no analysis of this epoch's evidence until analysis v2 is frozen (BUDGET_CALIBRATION.md stop rule 4; "
            "research/protocol/METHODOLOGY_HARDENING.md section 4)"
        ),
        "analysisCode": "fixed by analysis v2 before any quiet cell is read (measurement repo)",
        "forbidden": copy.deepcopy(base["analysis"]["forbidden"]),
    }
    continuation = copy.deepcopy(base["continuation"])
    continuation.pop("initialTestOnly")
    continuation["calibrationOnly"] = True
    document["continuation"] = continuation
    document["protocolGates"]["blocking"] = ["G1", "G2", "G4"]
    document["protocolGates"]["blockingNote"] = "F1 is evaluated in fault cells only; this epoch has none"
    document["derivedFrom"] = {
        "authority": AUTHORITY,
        "studyEpoch": PREDECESSOR_EPOCH,
        "descriptorPath": sweep.DESCRIPTOR_RELATIVE,
        "descriptorByteSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "descriptorCanonicalSha256": canonical_sha256(base),
        "planCanonicalSha256": sweep.EXPECTED_PLAN_SHA256,
        "disposition": (
            "the sweep epoch is not superseded: it keeps its own descriptor, plan and admission history; the quiet "
            "epoch is a separate epoch selected by modules/teastore/execution/study-epoch.json"
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
    for block in plan["blocks"]:
        rates = sorted(cell["timing"]["journeysPerSecond"] for cell in block["cells"])
        if rates != sorted(float(rate) for rate in RATES):
            raise ProtocolError("block %r does not hold every rate exactly once" % block["block"])
    for cell in cells:
        if (cell["fault"] is not None or cell["runKey"]["regime"] != REGIME or cell["timing"]["faultApplied"]
                or cell["timing"]["fault"] is not None):
            raise ProtocolError("the quiet plan holds a fault cell")


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
    raise ProtocolError("run ID %r is not in the compiled quiet plan" % (run_id,))


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
