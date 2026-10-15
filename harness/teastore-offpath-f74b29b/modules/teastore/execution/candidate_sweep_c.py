#!/usr/bin/env python3
"""Compile the TeaStore campaign-C epoch (teastore-traffic-sweep-c-v1) without executing it.

A fifth epoch beside the frozen 27-cell pilot (``candidate_pilot.py``), the traffic sweep (``candidate_sweep.py``), the
quiet calibration (``candidate_quiet.py``) and campaign B (``candidate_sweep_b.py``), all of which this file only reads
or leaves alone.  Authority: measurement repo research/PROTOCOL_DRAFT_20261002.md decision 82 (round 22: campaign C
tests the frozen placement); budget and stop rule research/traffic-sweep/BUDGET_C.md (committed alone before the work,
d5b9af0): "campaign B's shape (3 blocks x 3 regimes x 4 rates = 36 cells, H10 and H4 as in B), new blocks and run IDs,
a new study epoch; nothing else changes".

Campaign B's shape, exactly: ``cell_timing`` takes campaign B's own ``cell_timing`` of the same (regime, rate) and
replaces only what depends on the seeded onset (``ONSET_TIMING_KEYS``: the three onset keys and the plan-derived phase
floors of a fault cell), so the harness declaration (``timing.faultHarness``: H10 probe window, H4 freeze stamps,
record-not-block), doses, route, rates, warm-up, measurement, hold, drain allowance, sampling, captures, posture
``full`` and gates are B's by construction.  The descriptor is generated from campaign B's pinned descriptor and differs
from it only in the epoch's identity, its schedule, its purpose and analysis boundary, and its provenance (tested).

New draws, nothing else: 3 blocks, each holding every (regime, rate) pair once (12 cells), in a Fisher-Yates order drawn
with SHA-256 from seed 20261011 under schedule version ``sweep-c-schedule-v1`` (B's rule and draw encoding with this
epoch's name, seed and version; no lead cell, as in B); the onset's stratified offset is drawn with the same seed and
name over the 3 blocks of each (regime, rate) pair.  Run IDs are B's shape with this epoch's name,
``teastore-traffic-sweep-c-v1/<regime>/r<rate>/b01..b03/full/a01``, so no run ID equals a sweep, quiet or B run ID
(blocks are keyed by the epoch name, not renumbered 4-6: the producer's and validator's ``1 <= block <=
blocksPerRegime`` guards stay as they are).

The plan keeps the sweep plan's schema (cells in ``blocks``), so the runtime replays it with the sweep's code:
``study_epoch.active`` reports this epoch as a sweep-mode epoch ("sweep": True) whose compiler is this file.  It is
active only when the committed selector ``modules/teastore/execution/study-epoch.json`` names it.

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
DESCRIPTOR_RELATIVE = "pipelines/campaigns/teastore-traffic-sweep-c-v1.json"
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
# Campaign B's compiler supplies the cell shape (its cell timing, harness declaration and constants), the shuffle and
# onset rules this epoch re-draws with its own seed, and, through its pinned-digest check, the descriptor this epoch is
# derived from.  It is read, never edited; it reads the sweep compiler in turn.
b = _load("teastore_sweep_c_b_compiler_" + _TAG, HERE / "candidate_sweep_b.py")
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

EPOCH = "teastore-traffic-sweep-c-v1"
PREDECESSOR_EPOCH = b.EPOCH                           # teastore-traffic-sweep-b-v1: the shape this epoch repeats
SUT_COMMIT = b.SUT_COMMIT
WORKLOAD = b.WORKLOAD
JOURNEY_KIND = b.JOURNEY_KIND

# ---------------------------------------------------------------- parameters (BUDGET_C.md: B's shape, new draws)
POSTURES = b.POSTURES                                 # ("full",)
RATES = b.RATES                                       # 10, 1, 0.2, 0.05 login journeys/s
REGIMES = b.REGIMES                                   # no-fault-cost, auth-freeze-effect, persistence-cpu-throttle-effect
FAULTS = dict(b.FAULTS)
ARTIFACT_CLASSES = dict(b.ARTIFACT_CLASSES)
FAULT_TARGETS = dict(b.FAULT_TARGETS)
OMITTED_REGIMES = dict(b.OMITTED_REGIMES)
BLOCKS = b.BLOCKS                                     # 3, as in B
EPISODES = BLOCKS                                     # the name study_epoch.active() reads as blocksPerRegime
SCHEDULE_SEED = 20261011                              # new draws (B: 20261009, sweep: 20261003)
SCHEDULE_CONTEXT = "sweep-c-schedule-v1"
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
MEASURED_CELL_PERIOD_SECONDS = copy.deepcopy(b.MEASURED_CELL_PERIOD_SECONDS)
DECLARATION = (
    "research/traffic-sweep/DECLARATION_C_TEASTORE.md (measurement repo; frozen and committed alone before the "
    "first cell)"
)
AUTHORITY = (
    "measurement repo research/PROTOCOL_DRAFT_20261002.md decision 82 (round 22: placement test runs) and D-p4 / "
    "decision 74; budget and stop rule research/traffic-sweep/BUDGET_C.md (d5b9af0, committed alone before the work): "
    "campaign B's shape, new blocks and run IDs, a new study epoch, nothing else changes"
)
# The sweep compiler, the sweep descriptor, campaign B's compiler and campaign B's descriptor are inputs of this
# compiler, so the runtime adapter digest-binds them beside this epoch's own descriptor.
ADDITIONAL_CONTROLLER_PATHS = {
    "sweep-compiler": "modules/teastore/execution/candidate_sweep.py",
    "sweep-descriptor": sweep.DESCRIPTOR_RELATIVE,
    "sweep-b-compiler": "modules/teastore/execution/candidate_sweep_b.py",
    "sweep-b-descriptor": b.DESCRIPTOR_RELATIVE,
    "sweep-c-descriptor": DESCRIPTOR_RELATIVE,
}
# ---------------------------------------------------------------- derived (B's values: same shape, same budget)

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
EXPECTED_DESCRIPTOR_SHA256 = "ee01552936cfcef21b0826480a1c844e30aa67b418a99555e9f163a270c49711"
EXPECTED_PLAN_SHA256 = "e55b4f59e3ff8895b3f7d44d89114436fae89b6096fc7d6204d9e0579872eb29"

DESIGN_LABEL = b.DESIGN_LABEL
CANDIDATE_LABEL = b.CANDIDATE_LABEL


def _unit_draw(*parts: Any) -> float:
    return b._unit_draw(*parts)


def run_id_for(regime: str, rate: float, block: int, posture: str) -> str:
    """B's run-ID shape with this epoch's name: no C run ID can equal a sweep, quiet or B run ID."""
    return "%s/%s/r%s/b%02d/%s/a01" % (EPOCH, regime, rate_token(rate), block, posture)


def _run_id_parts(run_id: str) -> Dict[str, Any]:
    parts = run_id.split("/") if isinstance(run_id, str) else []
    if (len(parts) != 6 or parts[0] != EPOCH or parts[1] not in REGIMES or not parts[2].startswith("r")
            or not parts[3].startswith("b") or not parts[3][1:].isdigit() or parts[4] not in POSTURES
            or parts[5] != "a01"):
        raise ProtocolError("run ID %r is not a campaign-C run ID" % (run_id,))
    return {"regime": parts[1], "rateToken": parts[2][1:], "block": int(parts[3][1:]), "posture": parts[4]}


def stratified_onset_offset(seed: Any, epoch: str, episodes: int, run_id: str, regime: str, rate: float,
                            block: int) -> float:
    """Campaign B's (the sweep's) stratified onset rule; B's function, called with this epoch's arguments."""
    return b.stratified_onset_offset(seed, epoch, episodes, run_id, regime, rate, block)


def onset_phase_offset(run_id: str, rate: float) -> float:
    if ONSET_PHASE_OFFSET != "seeded-stratified-within-one-inter-arrival":
        raise ProtocolError("campaign C keeps the sweep's seeded stratified onset rule")
    parts = _run_id_parts(run_id)
    if parts["rateToken"] != rate_token(rate):
        raise ProtocolError("run ID %r was not compiled for rate %r" % (run_id, rate))
    return stratified_onset_offset(SCHEDULE_SEED, EPOCH, BLOCKS, run_id, parts["regime"], rate, parts["block"])


# The timing keys this epoch sets itself; every other key is campaign B's value of that (regime, rate) (tested).
ONSET_TIMING_KEYS = frozenset({
    "faultOnsetPhaseOffsetSeconds", "faultOnsetSeconds", "scoredWindowSeconds", "minimumActualStartsByPhase",
})
# B's name for the keys an epoch sets beyond the sweep's cell; the same set as B's (faultHarness is B's value here).
OWN_TIMING_KEYS = b.OWN_TIMING_KEYS


def cell_timing(run_id: str, regime: str, rate: float) -> Dict[str, Any]:
    """Campaign B's cell timing of ``regime`` at ``rate``, with this epoch's onset (and the floors that follow)."""
    if regime not in REGIMES or FAULTS.get(regime, "unknown") != b.FAULTS.get(regime, "unknown"):
        raise ProtocolError("campaign C compiles campaign B's regimes only")
    timing = b.cell_timing(b.run_id_for(regime, rate, 1, POSTURES[0]), regime, rate)
    fault = FAULTS[regime]
    if (timing["faultApplied"] is not (fault is not None) or timing["fault"] != fault
            or timing["faultHarness"] != (FAULT_HARNESS if fault is not None else None)):
        raise ProtocolError("campaign B's cell shape changed")
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
        raise ProtocolError("campaign C runs the full posture only")
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
    """The campaign-C descriptor, generated from campaign B's pinned descriptor.

    Named like the sweep's and B's generator, because the shared producer code calls it.  This function IS the
    descriptor's source: the checked-in teastore-traffic-sweep-c-v1.json must equal ``descriptor_bytes()`` (tested), so
    the file is regenerated, never hand-edited.  Carried over unchanged from B: every key but id, declaration, design
    (purpose only), schedule (version, seed, blocks), analysis, continuation and derivedFrom; in particular timing
    (budget, strata, harness declaration), faultParameters (the doses), workload, protocolGates and collection.
    """
    path = b.DEFAULT_DESCRIPTOR
    base = b.load_descriptor(path)                    # B's own pinned-digest check
    if base["id"] != PREDECESSOR_EPOCH:
        raise ProtocolError("campaign C is derived from campaign B's descriptor only")
    document = copy.deepcopy(base)
    document["id"] = EPOCH
    document["declaration"] = DECLARATION
    document["design"]["purpose"] = (
        "placement test run: campaign B's shape (3 blocks of the traffic sweep's 12 (regime, rate) cells on the H10/H4 "
        "harness) with new blocks, run IDs and draws in a new study epoch (BUDGET_C.md; protocol decision 82)"
    )
    document["schedule"] = {
        **copy.deepcopy(base["schedule"]),
        "version": SCHEDULE_CONTEXT,
        "seed": SCHEDULE_SEED,
        "blocks": allocate_schedule(),
    }
    document["analysis"] = {
        **copy.deepcopy(base["analysis"]),
        "comparativeUnit": "(fault, rate); 3 episodes each in this epoch, read through the frozen placement",
        "analysisFreeze": (
            "no cell of this epoch is read beyond its validity before the placement is frozen (BUDGET_C.md stop rule 4); "
            "fault cells are read only through the frozen placement (research/protocol/BUDGET_PLACEMENT.md step 6), "
            "never to tune it; no-fault cells are a second fresh false-alarm check, never pooled into a calibration"
        ),
        "analysisCode": "the frozen placement and analysis of the measurement repo, fixed before any cell of this epoch is read",
    }
    continuation = copy.deepcopy(base["continuation"])
    continuation["repeatOfEpoch"] = PREDECESSOR_EPOCH
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
            "the sweep, quiet and campaign-B epochs are not superseded: each keeps its own descriptor, plan and "
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
    raise ProtocolError("run ID %r is not in the compiled campaign-C plan" % (run_id,))


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
