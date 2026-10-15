#!/usr/bin/env python3
"""Compile the Hotel quiet calibration epoch (hotel-quiet-calibration-v1) without executing it.

A third epoch beside the frozen ``candidate_pilot.py`` (hotel-reservation-selected-v1) and the traffic sweep
``candidate_sweep.py`` (hotel-traffic-sweep-v1, plan 766063c5...); this file changes neither and reads the
sweep compiler as a library.  It runs the sweep's no-fault-calibration cell and nothing else: 10 blocks x the
sweep's 4 rates = 40 cells, 30 min of quiet measurement per rate (protocol decision 48: with 0 false alarms in
T hours the 95 % upper bound is 3/T per hour, so 0.5 h certifies <= 6/h).  Declaration:
research/traffic-sweep/DECLARATION_QUIET_HOTEL.md (measurement repo).

What is the sweep's, read from candidate_sweep.py and never restated here: route, rates, posture, warm-up,
measurement, pseudo-window base and hold, client timeout, concurrency, sampling and capture flags, the onset
rule (seeded, stratified within one inter-arrival), the cell timing keys and the descriptor sections that do not
describe the design (workload, ground truth, gates, collection, evidence, transport, ...).  What is this
epoch's: one regime, 10 blocks (so 10 onset strata per rate), the schedule seed 20261004, and one seeded
Fisher-Yates order over all 40 cells (no block-wise order, no lead cell).

Runs as ``python3 -I`` on CPython 3.9 on the target: standard library only, sibling files are loaded by
path (``-I`` drops this directory from ``sys.path``), no PEP 604 annotation evaluated at runtime.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DESCRIPTOR = ROOT / "pipelines/campaigns/hotel-quiet-calibration-v1.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The sweep compiler supplies the cell shape, its descriptor and its helpers; it is read, never edited, and
# its own digests stay pinned in its own file (loading it verifies nothing; compile_plan below does).
sweep = _load("hotel_quiet_sweep_compiler", HERE / "candidate_sweep.py")
frozen = sweep.frozen
ProtocolError = sweep.ProtocolError
canonical_sha256 = sweep.canonical_sha256
strict_json_file = sweep.strict_json_file
rate_token = sweep.rate_token
offered_for = sweep.offered_for

EPOCH = "hotel-quiet-calibration-v1"
SUT_COMMIT = sweep.SUT_COMMIT
WORKLOAD = sweep.WORKLOAD

# ---------------------------------------------------------------- parameters (decision 48; the rest is the sweep's)
REGIME = "no-fault-calibration"                # the sweep's regime id, artifact root and no-fault capture
POSTURES = sweep.POSTURES
RATES = sweep.RATES
BLOCKS = 10                                    # per rate; also the number of onset strata per rate
SCHEDULE_SEED = 20261004
SCHEDULE_CONTEXT = "quiet-schedule-v1"
ONSET_PHASE_OFFSET = sweep.ONSET_PHASE_OFFSET
ONSET_PHASE_OFFSETS = sweep.ONSET_PHASE_OFFSETS
# ---------------------------------------------------------------- derived (the sweep's budget rule, this count)

if sweep.FAULTS[REGIME] is not None:
    raise ProtocolError("the quiet calibration regime must be the sweep's no-fault regime")
TOTAL_RUNS = len(RATES) * BLOCKS
CELL_PERIOD_ESTIMATE_SECONDS = sweep.CELL_PERIOD_ESTIMATE_SECONDS
MINIMUM_TIMED_SECONDS = TOTAL_RUNS * (sweep.WARMUP_SECONDS + sweep.MEASUREMENT_SECONDS)
MAXIMUM_WALL_SECONDS = 3600 * int(math.ceil(
    (TOTAL_RUNS * CELL_PERIOD_ESTIMATE_SECONDS + sweep.PREPARE_RESERVE_SECONDS + sweep.CLEANUP_RESERVE_SECONDS)
    / 3600.0
))
MINIMUM_FIRST_MUTATION_REMAINING_SECONDS = MAXIMUM_WALL_SECONDS - sweep.CLEANUP_RESERVE_SECONDS
EXPECTED_DESCRIPTOR_SHA256 = "fa42391ddb766e03bfbbf0eb212bff0b5409ed8def238a754199c17a4301efea"
EXPECTED_PLAN_SHA256 = "554a7a1e753a7f3535a7ae1c796cceee986bf0b1ae4b629858de2a547d79b127"
RUN_ID = re.compile(r"^(?P<regime>[a-z]+(?:-[a-z]+)*)-r(?P<rate>[0-9]+(?:p[0-9]+)?)-b(?P<block>[0-9]{2})-full-a01$")


def run_id_for(rate: float, block: int) -> str:
    return sweep.run_id_for(REGIME, rate, block, POSTURES[0])


def onset_phase_offset(run_id: str, rate: float) -> float:
    """The sweep's seeded stratified rule (candidate_sweep.onset_phase_offset) with this epoch's seed, name and
    BLOCKS strata: the ten blocks of one rate take the ten strata of one inter-arrival in a seeded order."""
    if ONSET_PHASE_OFFSET == "none":
        return 0.0
    inter_arrival = 1.0 / float(rate)
    match = RUN_ID.fullmatch(run_id)
    if match is None or not 1 <= int(match.group("block")) <= BLOCKS:
        raise ProtocolError("run ID %r has no regime and block of this epoch" % (run_id,))
    strata = sorted(range(BLOCKS), key=lambda stratum: sweep._unit_draw(
        SCHEDULE_SEED, EPOCH, match.group("regime"), rate_token(rate), "onset-stratum", stratum))
    stratum = strata[int(match.group("block")) - 1]
    position = sweep._unit_draw(SCHEDULE_SEED, EPOCH, run_id, "onset-phase")
    offset = round((stratum + position) / BLOCKS * inter_arrival, 6)
    return min(offset, round(inter_arrival - 1e-6, 6))


def cell_timing(run_id: str, rate: float) -> Dict[str, Any]:
    """candidate_sweep.cell_timing for a no-fault cell; only the seeded onset offset is this epoch's."""
    measurement = sweep.MEASUREMENT_SECONDS
    offset = onset_phase_offset(run_id, rate)
    onset = round(sweep.FAULT_ONSET_BASE_SECONDS + offset, 6)
    hold = sweep.FAULT_HOLD_SECONDS
    if not 0 < onset < onset + hold < measurement:
        raise ProtocolError("pseudo window must lie strictly inside the measurement")
    return {
        "requestsPerSecond": float(rate),
        "interArrivalSeconds": 1.0 / float(rate),
        "concurrency": sweep.CONCURRENCY,
        "requestTimeoutSeconds": sweep.REQUEST_TIMEOUT_SECONDS,
        "warmupSeconds": sweep.WARMUP_SECONDS,
        "warmupRequestsPerSecond": sweep.WARMUP_REQUESTS_PER_SECOND,
        "measurementSeconds": measurement,
        "offered": offered_for(rate, measurement),
        "faultApplied": False,
        "faultOnsetBaseSeconds": sweep.FAULT_ONSET_BASE_SECONDS,
        "faultOnsetPhaseOffsetSeconds": offset,
        "faultOnsetSeconds": onset,
        "faultHoldSeconds": hold,
        "scoredWindowSeconds": [onset, round(onset + hold, 6)],
        "minimumWitnessedStartsByPhase": None,
        "tcpSnapshotOffsetsSeconds": {
            "pre-fault": round(onset - sweep.TCP_PRE_FAULT_LEAD_SECONDS, 6),
            "during-fault": round(onset + sweep.TCP_DURING_FAULT_LAG_SECONDS, 6),
        },
        "jaegerQueryWindowSeconds": measurement + sweep.JAEGER_TAIL_SECONDS,
        "minimumSystemSamples": int(measurement // sweep.SYSTEM_SAMPLE_INTERVAL_SECONDS),
        "collectorJoinSlackSeconds": 1.0 / float(rate),
        "applicationLogTimestamps": True,
        "jaegerAllServicesRemainder": True,
        "probeStamps": True,
    }


def sequence_order() -> List[Dict[str, Any]]:
    """Every (rate, block) cell once, one Fisher-Yates shuffle over all of them with SHA-256 draws.

    Starting order: block-major, rates in declaration order.  Draw i: SHA-256 of
    UTF-8(seed NUL epoch NUL all-cells NUL draw-i NUL version), as an integer, modulo i + 1.
    """
    cells = [{"rate": float(rate), "block": block} for block in range(1, BLOCKS + 1) for rate in RATES]
    for index in range(len(cells) - 1, 0, -1):
        draw = int(hashlib.sha256(
            ("%s\0%s\0all-cells\0draw-%d\0%s" % (SCHEDULE_SEED, EPOCH, index, SCHEDULE_CONTEXT)).encode("utf-8")
        ).hexdigest(), 16)
        other = draw % (index + 1)
        cells[index], cells[other] = cells[other], cells[index]
    return cells


def allocate_schedule() -> Dict[str, Any]:
    if POSTURES != ("full",):
        raise ProtocolError("the quiet calibration runs the full posture only")
    if ONSET_PHASE_OFFSET not in ONSET_PHASE_OFFSETS:
        raise ProtocolError("onset phase offset rule is not declared")
    run_ids = [run_id_for(row["rate"], row["block"]) for row in sequence_order()]
    if len(run_ids) != TOTAL_RUNS or len(set(run_ids)) != TOTAL_RUNS:
        raise ProtocolError("schedule does not contain every cell exactly once")
    return {"runIds": run_ids, "orderSha256": canonical_sha256(run_ids)}


def frozen_descriptor() -> Dict[str, Any]:
    """The sweep's descriptor with exactly the design sections replaced (a test enumerates the difference)."""
    descriptor = copy.deepcopy(sweep.frozen_descriptor())
    base_timing = descriptor["timing"]
    regime = [row for row in descriptor["design"]["regimes"] if row["id"] == REGIME]
    if len(regime) != 1:
        raise ProtocolError("the sweep descriptor has no single no-fault regime")
    descriptor["id"] = EPOCH
    descriptor["declaration"] = (
        "research/traffic-sweep/DECLARATION_QUIET_HOTEL.md (measurement repo; committed alone before the first cell)"
    )
    descriptor["design"] = {
        "postures": list(POSTURES),
        "postureRoles": descriptor["design"]["postureRoles"],
        "unsupportedPostures": descriptor["design"]["unsupportedPostures"],
        "regimes": regime,
        "rates": list(RATES),
        "blocks": BLOCKS,
        "cellsPerBlock": len(RATES),
        "totalRuns": TOTAL_RUNS,
        "blockRule": "each-block-holds-every-rate-exactly-once; execution order is one shuffle over all cells",
        "coldStartEachRun": True,
        "faultAppliedToAnyCell": False,
        "noFaultCellsCarryPseudoWindow": True,
        "quietMeasurementSecondsPerRate": BLOCKS * sweep.MEASUREMENT_SECONDS,
    }
    descriptor["timing"] = dict(base_timing, **{
        "leadCell": None,
        "onsetStrataPerRate": BLOCKS,
        "minimumTimedSeconds": MINIMUM_TIMED_SECONDS,
        "budget": dict(base_timing["budget"], **{
            "maximumWallSeconds": MAXIMUM_WALL_SECONDS,
            "minimumFirstMutationRemainingSeconds": MINIMUM_FIRST_MUTATION_REMAINING_SECONDS,
        }),
    })
    descriptor["schedule"] = {
        "version": SCHEDULE_CONTEXT,
        "seed": SCHEDULE_SEED,
        "shuffle": "fisher-yates-over-all-cells-with-sha256-draws",
        "startingOrder": "block-major, rates in declaration order",
        "drawEncoding": "UTF-8(seed || NUL || epoch || NUL || all-cells || NUL || draw-i || NUL || version)",
        "order": allocate_schedule(),
    }
    descriptor["analysis"] = {
        "comparativeUnit": "rate over blocks (false alarms per hour of quiet time)",
        "descriptiveOnly": True,
        "falseAlarmBound": "0 alarms in T quiet hours bounds the rate at 3/T per hour (95 %); 0.5 h per rate -> 6/h",
        "analysisCode": "research/detection-time/ analysis v2 (measurement repo), frozen before any quiet cell is read",
        "forbidden": descriptor["analysis"]["forbidden"],
    }
    descriptor["derivedFrom"] = {
        "studyEpoch": sweep.EPOCH,
        "descriptorCanonicalSha256": sweep.EXPECTED_DESCRIPTOR_SHA256,
        "planCanonicalSha256": sweep.EXPECTED_PLAN_SHA256,
        "regime": REGIME,
    }
    return descriptor


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
    receipt = descriptor["schedule"]["order"]["runIds"]
    cells = []
    for position, row in enumerate(sequence_order(), start=1):
        rate, block, posture = row["rate"], row["block"], POSTURES[0]
        run_id = run_id_for(rate, block)
        if run_id != receipt[position - 1]:
            raise ProtocolError("compiled order differs from the descriptor's schedule receipt")
        cells.append({
            "runId": run_id,
            "runKey": {
                "studyEpoch": EPOCH, "regime": REGIME, "requestsPerSecond": rate,
                "block": block, "posture": posture, "attempt": 1,
            },
            "position": position,
            "artifactRoot": "%s/r%s/b%02d/p%02d-%s/attempt-01" % (
                sweep.ARTIFACT_ROOTS[REGIME], rate_token(rate), block, position, posture),
            "fault": None,
            "postureRole": role[posture],
            "timing": cell_timing(run_id, rate),
            "scheduledState": "not-started",
            "candidateCellEligible": False,
            "runtimeAdapter": None,
        })
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
        # One seeded order over all cells; the runtime executes `sequence.cells` in this order.
        "sequence": {"seed": SCHEDULE_SEED, "order": list(receipt), "cells": cells},
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
    return list(plan["sequence"]["cells"])


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
