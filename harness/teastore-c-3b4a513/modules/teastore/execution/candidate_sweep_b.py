#!/usr/bin/env python3
"""Compile the TeaStore campaign-B epoch (teastore-traffic-sweep-b-v1) without executing it.

A fourth epoch beside the frozen 27-cell pilot (``candidate_pilot.py``), the traffic sweep (``candidate_sweep.py``,
teastore-traffic-sweep-v1, one block, 12 cells) and the quiet calibration (``candidate_quiet.py``), all of which this
file only reads or leaves alone.  Authority: measurement repo research/PROTOCOL_DRAFT_20261002.md decision 49 (user
2026-10-04: three more blocks on TeaStore and OTel after the H10/H4 harness change, four in all like Hotel), decision
50 (fault doses inherited as a fixed factor) and decision 69 (H4 is record-not-block); design research/traffic-sweep/NEXT_CAMPAIGNS_PROPOSAL.md section B;
budget and stop rule research/traffic-sweep/BUDGET_B.md (committed alone before the work, 92ca1c7).

Every cell has the sweep's shape: the same route, rates, client timeout, concurrency, warm-up, measurement, hold,
onset rule, drain allowance, sampling, captures, posture ``full``, doses (auth pause; persistence CPU throttle to 0.1
cores) and protocol gates.  ``cell_timing`` takes the sweep compiler's own ``cell_timing(<the sweep's run ID of that
regime and rate>, regime, rate)`` and replaces only what depends on this epoch's seeded onset (the three onset keys and
the plan-derived phase floors of a fault cell) and adds the harness-change declaration (``faultHarness``, below).

Schedule: 3 blocks; each block holds every (regime, rate) pair exactly once (12 cells), in a Fisher-Yates order drawn
with SHA-256 from seed 20261009 (the sweep's block rule and draw encoding with this epoch's name and schedule version;
no lead cell: the sweep's lead cell existed to show the first pause at 10/s early, and that has run).  The onset's
stratified offset is drawn with the same seed and name over the 3 blocks of each (regime, rate) pair.

Harness change for later runs (research/protocol/METHODOLOGY_HARDENING.md, H10 and H4), carried by the plan cell's
``timing.faultHarness`` (fault cells only; a no-fault cell has ``None``), so the sweep and quiet epochs, whose cells
carry no such key, behave byte for byte as before:

* H10: no readiness probe from the fault onset to the end of the scored window and the revert.  The probes of
  the sweep already start after the revert command returned; this epoch records the window (``sweep.probePolicy``),
  refuses to probe inside it, and has the validator re-check every probe against it.
* H4: stamp the freeze, record-not-block (decision 69: a failure leaves the cell valid, marked missing).  Pause: the Docker ``pause`` / ``unpause`` events of the target container, with the cell's
  monotonic mapping; throttle: the command-issued and command-returned stamps plus the applied-state readback stamps
  (``sweep.freezeStamps``, schema in the declaration draft).

The plan keeps the sweep plan's schema (cells in ``blocks``), so the orchestrator, adapter, transport, installer and
validators replay it with the sweep's code: ``study_epoch.active`` reports this epoch as a sweep-mode epoch
("sweep": True) whose compiler is this file.  It is active only when the committed selector
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
DESCRIPTOR_RELATIVE = "pipelines/campaigns/teastore-traffic-sweep-b-v1.json"
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
# The sweep compiler supplies the cell shape (its cell timing), the onset and shuffle rules this epoch re-draws with
# its own seed, the JSON helpers and, through its pinned-digest check, the descriptor this epoch is derived from.  It is
# read, never edited.
sweep = _load("teastore_sweep_b_sweep_compiler_" + _TAG, HERE / "candidate_sweep.py")
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

EPOCH = "teastore-traffic-sweep-b-v1"
PREDECESSOR_EPOCH = sweep.EPOCH                       # teastore-traffic-sweep-v1: the cell shape this epoch repeats
SUT_COMMIT = sweep.SUT_COMMIT
WORKLOAD = sweep.WORKLOAD
JOURNEY_KIND = sweep.JOURNEY_KIND

# ---------------------------------------------------------------- parameters (decision 49, user 2026-10-04)
POSTURES = sweep.POSTURES                             # ("full",)
RATES = sweep.RATES                                   # 10, 1, 0.2, 0.05 login journeys/s
REGIMES = sweep.REGIMES                               # no-fault-cost, auth-freeze-effect, persistence-cpu-throttle-effect
FAULTS = dict(sweep.FAULTS)
ARTIFACT_CLASSES = dict(sweep.ARTIFACT_CLASSES)
FAULT_TARGETS = dict(sweep.FAULT_TARGETS)
OMITTED_REGIMES = dict(sweep.OMITTED_REGIMES)         # net-delay: still no mechanism without sudo on fb14srv5
BLOCKS = 3                                            # three more blocks (four with the sweep's one, like Hotel)
EPISODES = BLOCKS                                     # the name study_epoch.active() reads as blocksPerRegime
SCHEDULE_SEED = 20261009
SCHEDULE_CONTEXT = "sweep-b-schedule-v1"
ONSET_PHASE_OFFSET = sweep.ONSET_PHASE_OFFSET
WARMUP_SECONDS = sweep.WARMUP_SECONDS
MEASUREMENT_SECONDS = sweep.MEASUREMENT_SECONDS
FAULT_ONSET_BASE_SECONDS = sweep.FAULT_ONSET_BASE_SECONDS
TRACE_INCOMPLETE_FRACTION = sweep.TRACE_INCOMPLETE_FRACTION
# Harness change for later runs, declared per fault cell (the plan digest binds it).  ``version`` names the schema of
# ``sweep.probePolicy`` and ``sweep.freezeStamps`` in intervention.json.  The event tolerance is an engineering default:
# a Docker pause (unpause) event is emitted by the daemon between the command's issue and its return, so it must map
# into [issued, returned] within this slack after the clock mapping.
FAULT_HARNESS = {
    "version": "h4-h10-v1",
    "noProbeDuringFault": True,
    "freezeStamps": True,
    "freezeFailure": "record-not-block",
    "freezeEventToleranceSeconds": 0.25,
}
# Wall budget: the sweep's rule and engineering defaults (225 s timed + 300 s overhead = 525 s per cell), checked
# against sweep relaunch 2 (fb14srv5, 2026-10-04), the same measured periods the quiet calibration cites.
CELL_OVERHEAD_SECONDS = sweep.CELL_OVERHEAD_SECONDS
CELL_OVERHEAD_LOWER_SECONDS = sweep.CELL_OVERHEAD_LOWER_SECONDS
PREPARE_RESERVE_SECONDS = sweep.PREPARE_RESERVE_SECONDS
CLEANUP_RESERVE_SECONDS = sweep.CLEANUP_RESERVE_SECONDS
MEASURED_CELL_PERIOD_SECONDS = {
    "source": (
        "teastore-traffic-sweep-v1 relaunch 2 (fb14srv5, 2026-10-04 07:53-08:57Z), consecutive runtime-journal "
        "recordedAt gaps; its 12 cells are this epoch's cell shape"
    ),
    "cells": 12, "gaps": 11, "minimum": 324.9, "median": 330.5, "mean": 343.2, "maximum": 423.4,
}
DECLARATION = (
    "research/traffic-sweep/DECLARATION_B_TEASTORE.md (measurement repo; frozen and committed alone before the "
    "first cell)"
)
AUTHORITY = (
    "measurement repo research/PROTOCOL_DRAFT_20261002.md decision 49 (user 2026-10-04: three more blocks on TeaStore "
    "and OTel after the H10/H4 harness change) and decision 50 (fault doses inherited, a fixed factor); budget and "
    "stop rule research/traffic-sweep/BUDGET_B.md (92ca1c7, committed alone before the work); proposal "
    "research/traffic-sweep/NEXT_CAMPAIGNS_PROPOSAL.md section B; harness change "
    "research/protocol/METHODOLOGY_HARDENING.md H4 and H10"
)
# The sweep compiler and the sweep descriptor are inputs of this compiler, so the runtime adapter digest-binds them
# beside this epoch's own descriptor (study_epoch.active() hands these to the adapter's controller set).
ADDITIONAL_CONTROLLER_PATHS = {
    "sweep-compiler": "modules/teastore/execution/candidate_sweep.py",
    "sweep-descriptor": sweep.DESCRIPTOR_RELATIVE,
    "sweep-b-descriptor": DESCRIPTOR_RELATIVE,
}
# ---------------------------------------------------------------- derived

TOTAL_RUNS = len(REGIMES) * len(RATES) * BLOCKS
CELLS_PER_BLOCK = len(REGIMES) * len(RATES)
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
EXPECTED_DESCRIPTOR_SHA256 = "d4d846337263f57bfe2b9a0d8de8f0f9cde319157ad8e7611b62faecfe99b7c7"
EXPECTED_PLAN_SHA256 = "aa3469708cc7f27f3262e12a6293a4a77bc6af1ec9e06cc4156f8bdd123101db"

DESIGN_LABEL = sweep.DESIGN_LABEL
CANDIDATE_LABEL = sweep.CANDIDATE_LABEL


def _unit_draw(*parts: Any) -> float:
    return sweep._unit_draw(*parts)


def run_id_for(regime: str, rate: float, block: int, posture: str) -> str:
    """The sweep's run-ID shape with this epoch's name: no B run ID can equal a sweep or quiet run ID."""
    return "%s/%s/r%s/b%02d/%s/a01" % (EPOCH, regime, rate_token(rate), block, posture)


def _run_id_parts(run_id: str) -> Dict[str, Any]:
    parts = run_id.split("/") if isinstance(run_id, str) else []
    if (len(parts) != 6 or parts[0] != EPOCH or parts[1] not in REGIMES or not parts[2].startswith("r")
            or not parts[3].startswith("b") or not parts[3][1:].isdigit() or parts[4] not in POSTURES
            or parts[5] != "a01"):
        raise ProtocolError("run ID %r is not a campaign-B run ID" % (run_id,))
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
        raise ProtocolError("campaign B keeps the sweep's seeded stratified onset rule")
    parts = _run_id_parts(run_id)
    if parts["rateToken"] != rate_token(rate):
        raise ProtocolError("run ID %r was not compiled for rate %r" % (run_id, rate))
    return stratified_onset_offset(SCHEDULE_SEED, EPOCH, BLOCKS, run_id, parts["regime"], rate, parts["block"])


def cell_timing(run_id: str, regime: str, rate: float) -> Dict[str, Any]:
    """The sweep's cell timing of ``regime`` at ``rate``, with this epoch's onset and the harness declaration."""
    if regime not in REGIMES or FAULTS.get(regime, "unknown") != sweep.FAULTS.get(regime, "unknown"):
        raise ProtocolError("campaign B compiles the sweep's regimes only")
    timing = sweep.cell_timing(sweep.run_id_for(regime, rate, 1, POSTURES[0]), regime, rate)
    fault = FAULTS[regime]
    if timing["faultApplied"] is not (fault is not None) or timing["fault"] != fault:
        raise ProtocolError("the sweep's cell shape changed")
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
        "faultHarness": dict(FAULT_HARNESS) if fault is not None else None,
    })
    return timing


# The timing keys this epoch sets itself; every other key is the sweep's value of that cell (tested).
OWN_TIMING_KEYS = frozenset({
    "faultOnsetPhaseOffsetSeconds", "faultOnsetSeconds", "scoredWindowSeconds", "minimumActualStartsByPhase",
    "faultHarness",
})


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
        raise ProtocolError("campaign B runs the full posture only")
    if len(set(RATES)) != len(RATES) or any(not (math.isfinite(rate) and rate > 0) for rate in RATES):
        raise ProtocolError("rates must be distinct, finite and positive")
    if set(REGIMES) != set(FAULTS) or set(REGIMES) != set(ARTIFACT_CLASSES):
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
    """The campaign-B descriptor, generated from the pinned sweep descriptor.

    Named like the sweep's (and the frozen compiler's) generator, because the shared producer code calls it.  This
    function IS the descriptor's source: the checked-in teastore-traffic-sweep-b-v1.json must equal
    ``descriptor_bytes()`` (tested), so the file is regenerated, never hand-edited.  Carried over unchanged from the
    sweep: schemaVersion, status, module, targetHost, source, workload, runIdentity, systemSamples, postureProof,
    queueProof, missingness, evidence, protocolGates, faultParameters (the doses, decision 50).  Replaced: id,
    declaration, design, timing (budget, strata, lead cell, harness declaration), schedule, groundTruth (two receipt
    notes), collection (+freezeStamps), outcomes, analysis, continuation; added: derivedFrom.
    """
    path = sweep.DEFAULT_DESCRIPTOR
    base = sweep.load_descriptor(path)                # the sweep's own pinned-digest check
    if base["id"] != PREDECESSOR_EPOCH:
        raise ProtocolError("campaign B is derived from the sweep descriptor only")
    schedule = allocate_schedule()
    document = copy.deepcopy(base)
    document["id"] = EPOCH
    document["declaration"] = DECLARATION
    design = document["design"]
    design.update({
        "purpose": (
            "repeat episodes: three more blocks of the traffic sweep's 12 (regime, rate) cells on the H10/H4 harness "
            "(research/PROTOCOL_DRAFT_20261002.md decision 49; four blocks with the sweep's one, like Hotel)"
        ),
        "episodesPerRegimeAndRate": BLOCKS,
        "blocks": BLOCKS,
        "cellsPerBlock": CELLS_PER_BLOCK,
        "totalRuns": TOTAL_RUNS,
        "cellShape": (
            "the sweep's cell of the same regime and rate (candidate_sweep.cell_timing(<sweep run ID>, regime, rate)); "
            "only the seeded onset (faultOnsetPhaseOffsetSeconds, faultOnsetSeconds, scoredWindowSeconds), the "
            "plan-derived phase floors that follow from it, and the harness declaration (faultHarness) differ"
        ),
        "faultDoses": "inherited from the sweep, a fixed factor (decision 50): pause on auth; --cpus 0.1 on persistence",
    })
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
    timing["faultHarness"] = {
        **FAULT_HARNESS,
        "appliesTo": "fault cells only (timing.faultHarness is null in a no-fault cell)",
        "h10": (
            "no readiness probe from the fault onset (the onset command's issue) to the later of the scored "
            "window's end and the revert command's return; the producer refuses to probe earlier, records the "
            "window in sweep.probePolicy, and the validator rejects any probe that starts inside it"
        ),
        "h4": (
            "sweep.freezeStamps: pause = the Docker pause and unpause events of the target container (event time in "
            "ns, mapped to the cell's monotonic offsets by linear interpolation between the barrier and the "
            "collection instant) beside the command stamps; throttle = the command-issued and command-returned "
            "stamps plus the applied-state readback stamps; both = one readback stamp pair per target-state sample"
        ),
        "h4Failure": (
            "record, don't block (protocol decision 69): a failed or contradictory Docker events query or freeze-stamp "
            "check leaves the cell valid; the record carries status 'missing', every reason in failures and their number "
            "in failureCount, and the reader falls back to [onset command issued, onset command returned].  H10 stays "
            "blocking."
        ),
    }
    document["schedule"] = {
        "version": SCHEDULE_CONTEXT,
        "seed": SCHEDULE_SEED,
        "shuffle": "fisher-yates-over-regimes-x-rates-with-sha256-draws",
        "drawEncoding": "UTF-8(seed || NUL || epoch || NUL || block-NN || NUL || draw-i || NUL || version)",
        "leadCell": None,
        "blocks": schedule,
    }
    fault = document["groundTruth"]["fault"]
    fault["probeStamps"] = (
        "every post-revert readiness request (GET /status) is stamped in the receipt's probes list; none starts "
        "before the revert command returned (H10: sweep.probePolicy)"
    )
    fault["freezeStamps"] = "sweep.freezeStamps (H4), schema h4-h10-v1"
    document["collection"]["freezeStamps"] = (
        "fault cells: intervention.json sweep.freezeStamps (Docker pause/unpause events for the auth pause; command "
        "and applied-state readback stamps for both faults) and sweep.probePolicy"
    )
    document["outcomes"] = {
        **copy.deepcopy(base["outcomes"]),
        "primary": "time to detection per sensor and for the ledger, per (fault, rate), repeated over blocks",
    }
    document["analysis"] = {
        "comparativeUnit": "(fault, rate); 3 episodes each in this epoch, one more in the sweep",
        "detectionTimeMissCharge": base["analysis"]["detectionTimeMissCharge"],
        "analysisFreeze": (
            "no analysis of this epoch's evidence until analysis v3 is frozen and reviewed (BUDGET_B.md stop rule 4)"
        ),
        "analysisCode": "fixed by analysis v3 before any cell of this epoch is read (measurement repo)",
        "forbidden": copy.deepcopy(base["analysis"]["forbidden"]),
    }
    continuation = copy.deepcopy(base["continuation"])
    continuation.pop("initialTestOnly")
    continuation.pop("sixBlockContinuationRequiresNewPreOutcomeEpoch")
    continuation["repeatOfSweepEpoch"] = PREDECESSOR_EPOCH
    continuation["furtherBlocksRequireNewPreOutcomeEpoch"] = True
    document["continuation"] = continuation
    document["derivedFrom"] = {
        "authority": AUTHORITY,
        "studyEpoch": PREDECESSOR_EPOCH,
        "descriptorPath": sweep.DESCRIPTOR_RELATIVE,
        "descriptorByteSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "descriptorCanonicalSha256": canonical_sha256(base),
        "planCanonicalSha256": sweep.EXPECTED_PLAN_SHA256,
        "disposition": (
            "the sweep and quiet epochs are not superseded: each keeps its own descriptor, plan and admission "
            "history; this epoch is a separate epoch selected by modules/teastore/execution/study-epoch.json"
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
                or (timing["faultHarness"] is not None) is not (fault is not None)):
            raise ProtocolError("cell %s disagrees with its regime's fault or harness declaration" % cell["runId"])


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
    raise ProtocolError("run ID %r is not in the compiled campaign-B plan" % (run_id,))


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
