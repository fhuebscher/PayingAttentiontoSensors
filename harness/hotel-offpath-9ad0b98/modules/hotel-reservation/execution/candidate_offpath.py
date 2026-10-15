#!/usr/bin/env python3
"""Compile the Hotel off-path epoch (hotel-offpath-v1) without executing it.

A fourth epoch beside the frozen ``candidate_pilot.py`` (hotel-reservation-selected-v1), the traffic sweep
``candidate_sweep.py`` (hotel-traffic-sweep-v1, plan 766063c5...) and the quiet calibration ``candidate_quiet.py``;
this file changes none of them and reads the sweep compiler as a library.  Budget:
research/traffic-sweep/BUDGET_OVERNIGHT_20261014.md item 4; declaration: research/traffic-sweep/
DECLARATION_HOTEL_OFFPATH.md (measurement repo).

The question the epoch asks: Hotel's counterpart of the OTel and TeaStore off-path epochs.  A 60 s pause of the
``consul`` container is the declared off-path fault: consul is not on the request path (services register without
health checks, registry.go:77-92, and the frontend's grpc-consul-resolver watch keeps its existing connections), so
the pause is expected to leave the route up; ``search-pause-effect`` (the sweep's mechanism, unchanged) is the
on-path control, and ``no-fault-calibration`` the no-fault cell.  Whether the route stays up is recorded, never
required: an off-path manifestation is the container read back as paused plus the docker pause/unpause events on
its own container id (faults/compose_pause.py, witness/candidate_evidence.py, validation/candidate_terminal.py).

What is the sweep's, read from candidate_sweep.py and never restated here: route, warm-up (30 s at 10/s), 180 s
measurement, posture full, pseudo/fault window base (60 s) and hold (60 s), client timeout, concurrency, sampling and
capture flags, TCP snapshot placement, the per-phase witnessed-start floors (``phase_floors``), the seeded stratified
onset rule's form, the cell timing keys and every descriptor section that does not describe the design.  What is this
epoch's: three regimes, the two rates 10 and 1 req/s (both from the sweep's set), 5 blocks (so 5 onset strata per
regime and rate), the schedule seed 20261015, one seeded Fisher-Yates order per block over the 6 (regime, rate)
pairs (no lead cell), the ground truth for ``consul-pause``, and the collection scope (consul is collected beside
the ten application services, for this epoch only).

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
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DESCRIPTOR = ROOT / "pipelines/campaigns/hotel-offpath-v1.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The sweep compiler supplies the cell shape, its descriptor and its helpers; it is read, never edited, and its own
# digests stay pinned in its own file (loading it verifies nothing; compile_plan below does).
sweep = _load("hotel_offpath_sweep_compiler", HERE / "candidate_sweep.py")
frozen = sweep.frozen
ProtocolError = sweep.ProtocolError
canonical_sha256 = sweep.canonical_sha256
strict_json_file = sweep.strict_json_file
rate_token = sweep.rate_token
offered_for = sweep.offered_for

EPOCH = "hotel-offpath-v1"
SUT_COMMIT = sweep.SUT_COMMIT
WORKLOAD = sweep.WORKLOAD

# ---------------------------------------------------------------- parameters (the rest is the sweep's)
POSTURES = sweep.POSTURES
REGIMES = ("no-fault-calibration", "consul-pause-effect", "search-pause-effect")
FAULTS = {
    "no-fault-calibration": None,
    "consul-pause-effect": "consul-pause",       # off-path: consul is not on the request path
    "search-pause-effect": "search-pause",       # on-path control: the sweep's mechanism
}
ARTIFACT_ROOTS = {
    "no-fault-calibration": "calibration",
    "consul-pause-effect": "effect/consul-pause",
    "search-pause-effect": "effect/search-pause",
}
REGIME_ROLES = {
    "no-fault-calibration": "no-fault",
    "consul-pause-effect": "off-path-pause",
    "search-pause-effect": "on-path-control",
}
FAULT_TARGETS = {"search-pause": "search", "consul-pause": "consul"}
RATES = (10.0, 1.0)                              # requests per second, both in the sweep's rate set
BLOCKS = 5                                       # per (regime, rate); also the number of onset strata
SCHEDULE_SEED = 20261015
SCHEDULE_CONTEXT = "offpath-schedule-v1"
EXTRA_COLLECTED_SERVICES = ("consul",)           # collected beside the ten application services in this epoch
ONSET_PHASE_OFFSET = sweep.ONSET_PHASE_OFFSET
ONSET_PHASE_OFFSETS = sweep.ONSET_PHASE_OFFSETS
# ---------------------------------------------------------------- derived (the sweep's budget rule, this count)

CELLS_PER_BLOCK = len(REGIMES) * len(RATES)
TOTAL_RUNS = CELLS_PER_BLOCK * BLOCKS
CELL_PERIOD_ESTIMATE_SECONDS = sweep.CELL_PERIOD_ESTIMATE_SECONDS
MINIMUM_TIMED_SECONDS = TOTAL_RUNS * (sweep.WARMUP_SECONDS + sweep.MEASUREMENT_SECONDS)
# Whole hours, because the gate driver's GATE-RUN deadline is `run_window_hours` (an int) after approval.
MAXIMUM_WALL_SECONDS = 3600 * int(math.ceil(
    (TOTAL_RUNS * CELL_PERIOD_ESTIMATE_SECONDS + sweep.PREPARE_RESERVE_SECONDS + sweep.CLEANUP_RESERVE_SECONDS)
    / 3600.0
))
MINIMUM_FIRST_MUTATION_REMAINING_SECONDS = MAXIMUM_WALL_SECONDS - sweep.CLEANUP_RESERVE_SECONDS
EXPECTED_DESCRIPTOR_SHA256 = "d9bf052eac10b3f74c95e25b24bc5fb46fda62173dcb2aa0c5110bd5285eae23"
EXPECTED_PLAN_SHA256 = "90b7b621c8a1e54a92a78f813bb9c73ee829eddf4ef615e8806edd50d1df2f2a"
RUN_ID = re.compile(r"^(?P<regime>[a-z]+(?:-[a-z]+)*)-r(?P<rate>[0-9]+(?:p[0-9]+)?)-b(?P<block>[0-9]{2})-full-a01$")


def _check_parameters() -> None:
    if any(rate not in sweep.RATES for rate in RATES):
        raise ProtocolError("the off-path rates must be members of the sweep's rate set")
    if len(set(RATES)) != len(RATES) or any(not (math.isfinite(rate) and rate > 0) for rate in RATES):
        raise ProtocolError("rates must be distinct, finite and positive")
    if set(FAULTS) != set(REGIMES) or set(ARTIFACT_ROOTS) != set(REGIMES) or set(REGIME_ROLES) != set(REGIMES):
        raise ProtocolError("every regime needs a fault, an artifact root and a role")
    if sum(1 for regime in REGIMES if FAULTS[regime] is None) != 1:
        raise ProtocolError("exactly one regime is the no-fault regime")
    if POSTURES != ("full",):
        raise ProtocolError("the off-path epoch runs the full posture only")
    if ONSET_PHASE_OFFSET not in ONSET_PHASE_OFFSETS:
        raise ProtocolError("onset phase offset rule is not declared")


_check_parameters()


def run_id_for(regime: str, rate: float, block: int, posture: str) -> str:
    return sweep.run_id_for(regime, rate, block, posture)


def onset_phase_offset(run_id: str, rate: float) -> float:
    """The sweep's seeded stratified rule (candidate_sweep.onset_phase_offset) with this epoch's seed, name and
    BLOCKS strata: the blocks of one (regime, rate) pair take the BLOCKS strata of one inter-arrival in a seeded
    order, and the position inside a stratum is a seeded uniform draw."""
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


def cell_timing(run_id: str, regime: str, rate: float) -> Dict[str, Any]:
    """candidate_sweep.cell_timing with this epoch's onset offset; every other value is the sweep's."""
    measurement = sweep.MEASUREMENT_SECONDS
    offset = onset_phase_offset(run_id, rate)
    onset = round(sweep.FAULT_ONSET_BASE_SECONDS + offset, 6)
    hold = sweep.FAULT_HOLD_SECONDS
    if not 0 < onset < onset + hold < measurement:
        raise ProtocolError("fault window must lie strictly inside the measurement")
    fault = FAULTS[regime]
    floors = None
    if fault is not None:
        floors = sweep.phase_floors(rate, measurement, onset, hold)
    return {
        "requestsPerSecond": float(rate),
        "interArrivalSeconds": 1.0 / float(rate),
        "concurrency": sweep.CONCURRENCY,
        "requestTimeoutSeconds": sweep.REQUEST_TIMEOUT_SECONDS,
        "warmupSeconds": sweep.WARMUP_SECONDS,
        "warmupRequestsPerSecond": sweep.WARMUP_REQUESTS_PER_SECOND,
        "measurementSeconds": measurement,
        "offered": offered_for(rate, measurement),
        "faultApplied": fault is not None,
        "faultOnsetBaseSeconds": sweep.FAULT_ONSET_BASE_SECONDS,
        "faultOnsetPhaseOffsetSeconds": offset,
        "faultOnsetSeconds": onset,
        "faultHoldSeconds": hold,
        # A no-fault cell carries the same (seeded) window as a pseudo window for G1/G2 and false alarms.
        "scoredWindowSeconds": [onset, round(onset + hold, 6)],
        "minimumWitnessedStartsByPhase": floors,
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


def block_order(block: int) -> List[Dict[str, Any]]:
    """Every (regime, rate) pair once, Fisher-Yates shuffled by SHA-256 draws keyed by seed and block (the sweep's
    encoding with this epoch's seed, name and context; no lead cell)."""
    pairs = [{"regime": regime, "rate": float(rate)} for regime in REGIMES for rate in RATES]
    for index in range(len(pairs) - 1, 0, -1):
        draw = int(hashlib.sha256(
            ("%s\0%s\0block-%02d\0draw-%d\0%s" % (SCHEDULE_SEED, EPOCH, block, index, SCHEDULE_CONTEXT))
            .encode("utf-8")
        ).hexdigest(), 16)
        other = draw % (index + 1)
        pairs[index], pairs[other] = pairs[other], pairs[index]
    return pairs


def allocate_schedule() -> List[Dict[str, Any]]:
    blocks = []
    for block in range(1, BLOCKS + 1):
        order = block_order(block)
        run_ids = [run_id_for(row["regime"], row["rate"], block, POSTURES[0]) for row in order]
        blocks.append({"block": block, "runIds": run_ids, "orderSha256": canonical_sha256(run_ids)})
    every = [run_id for row in blocks for run_id in row["runIds"]]
    if len(every) != TOTAL_RUNS or len(set(every)) != TOTAL_RUNS:
        raise ProtocolError("schedule does not contain every cell exactly once")
    return blocks


def _ground_truth() -> Dict[str, Any]:
    """The frozen ground truth, restricted to this epoch's on-path fault and extended by the off-path one; the
    frozen descriptor itself is read, never edited."""
    truth = frozen.frozen_descriptor()["groundTruth"]
    on_path = {fault for fault in FAULTS.values() if fault is not None and fault != "consul-pause"}
    truth["fault"]["scenarioContracts"] = [
        row for row in truth["fault"]["scenarioContracts"] if row["scenario"] in on_path
    ] + [{
        "scenario": "consul-pause", "service": "consul",
        "prePredicate": "running-and-unpaused",
        "duringPredicate": "running-and-paused-and-docker-pause-event",
        "postPredicate": "running-and-unpaused-and-route-ready",
        "routeOutageDuringHold": "recorded-not-required",
        "prePathTruth": "hotel-search-normal-v1",
        "duringPathTruth": "hotel-search-normal-v1",
        "postReadinessPathTruth": "hotel-search-normal-v1",
    }]
    truth["fault"]["offPathManifestation"] = {
        "scenarios": ["consul-pause"],
        "rule": "container read back as paused (receipt duringState.paused) and docker pause then unpause events on "
                "the target's own container id (terminal replay); the route outage is recorded (outageObserved) and "
                "not required",
        "onPathRule": "manifested = paused and route outage observed (unchanged for search-pause)",
    }
    truth["path"]["faultSpecific"] = [
        row for row in truth["path"]["faultSpecific"] if row["fault"] in on_path
    ]
    return truth


def frozen_descriptor() -> Dict[str, Any]:
    """The sweep's descriptor with exactly the design sections replaced (a test enumerates the difference)."""
    descriptor = copy.deepcopy(sweep.frozen_descriptor())
    base_timing = descriptor["timing"]
    base_regimes = {row["id"]: row for row in descriptor["design"]["regimes"]}
    descriptor["id"] = EPOCH
    descriptor["declaration"] = (
        "research/traffic-sweep/DECLARATION_HOTEL_OFFPATH.md (measurement repo; committed alone before the first cell)"
    )
    descriptor["workload"] = dict(descriptor["workload"], requestsPerSecondLevels=list(RATES))
    regimes = []
    for regime in REGIMES:
        row = base_regimes.get(regime)
        if row is None:
            row = {"id": regime, "kind": "effect", "fault": FAULTS[regime], "artifactRootClass": ARTIFACT_ROOTS[regime]}
        if (row["fault"], row["artifactRootClass"]) != (FAULTS[regime], ARTIFACT_ROOTS[regime]):
            raise ProtocolError("regime %r differs from the sweep's declaration of it" % (regime,))
        regimes.append(dict(row, role=REGIME_ROLES[regime]))
    descriptor["design"] = {
        "postures": list(POSTURES),
        "postureRoles": descriptor["design"]["postureRoles"],
        "unsupportedPostures": descriptor["design"]["unsupportedPostures"],
        "regimes": regimes,
        "rates": list(RATES),
        "episodesPerRegimeAndRate": BLOCKS,
        "blocks": BLOCKS,
        "cellsPerBlock": CELLS_PER_BLOCK,
        "totalRuns": TOTAL_RUNS,
        "blockRule": "each-block-holds-every-(regime,rate)-pair-exactly-once",
        "coldStartEachRun": True,
        "faultAppliedToEveryEffectCell": True,
        "noFaultCellsCarryPseudoWindow": True,
        "offPathRegime": "consul-pause-effect",
        "onPathControlRegime": "search-pause-effect",
        "offPathRouteOutageRequired": False,
    }
    descriptor["timing"] = dict(base_timing, **{
        "leadCell": None,
        "onsetStrataPerRegimeAndRate": BLOCKS,
        "offeredByRate": {rate_token(rate): offered_for(rate, sweep.MEASUREMENT_SECONDS) for rate in RATES},
        "minimumTimedSeconds": MINIMUM_TIMED_SECONDS,
        "budget": dict(base_timing["budget"], **{
            "maximumWallSeconds": MAXIMUM_WALL_SECONDS,
            "minimumFirstMutationRemainingSeconds": MINIMUM_FIRST_MUTATION_REMAINING_SECONDS,
        }),
    })
    descriptor["schedule"] = {
        "version": SCHEDULE_CONTEXT,
        "seed": SCHEDULE_SEED,
        "shuffle": "fisher-yates-over-regimes-x-rates-with-sha256-draws",
        "drawEncoding": "UTF-8(seed || NUL || epoch || NUL || block-NN || NUL || draw-i || NUL || version)",
        "blocks": allocate_schedule(),
    }
    descriptor["groundTruth"] = _ground_truth()
    protocol_gates = copy.deepcopy(descriptor["protocolGates"])
    protocol_gates["f1OffPathManifestation"] = (
        "an off-path pause is manifested by the receipt's container read back as paused; the docker pause/unpause "
        "events on the target are checked at terminal replay before the gates run; the route outage is recorded"
    )
    descriptor["protocolGates"] = protocol_gates
    descriptor["collection"] = dict(descriptor["collection"], **{
        "scopeServices": list(frozen.APPLICATION_SERVICES) + list(EXTRA_COLLECTED_SERVICES),
        "extraScopeServices": list(EXTRA_COLLECTED_SERVICES),
        "extraScopeChannels": [
            "application-log", "docker-stats-cpu", "cost-cgroup", "system-sampler-cgroup-5s",
            "tcp-snapshots", "image-receipt",
        ],
        "extraScopeRule": "consul is collected beside the ten application services in this epoch only; "
                          "applicationCpu* sums the ten application containers, consul is a separate row",
    })
    descriptor["faultParameters"] = dict(descriptor["faultParameters"], targets=dict(sorted(FAULT_TARGETS.items())))
    descriptor["analysis"] = {
        "comparativeUnit": "(fault, rate) over blocks",
        "descriptiveOnly": True,
        "detectionTimeMissCharge": "window-end (hold end), averaged over all episodes",
        "analysisCode": "research/detection-time/ (measurement repo), frozen by digest before any off-path cell is read",
        "placementVerdict": None,
        "forbidden": descriptor["analysis"]["forbidden"],
    }
    descriptor["derivedFrom"] = {
        "studyEpoch": sweep.EPOCH,
        "descriptorCanonicalSha256": sweep.EXPECTED_DESCRIPTOR_SHA256,
        "planCanonicalSha256": sweep.EXPECTED_PLAN_SHA256,
        "regimes": ["no-fault-calibration", "search-pause-effect"],
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
