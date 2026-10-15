#!/usr/bin/env python3
"""Compile the OTel Demo quiet calibration epoch (otel-quiet-calibration-v1) without executing it.

A third epoch beside the frozen offpath compiler (``candidate_pilot.py``) and the finished traffic sweep
(``candidate_sweep.py``, otel-traffic-sweep-v1, relaunch 1 terminal-valid 12/12 on 2026-10-03), both of which this
file only reads.  Authority: main repo research/PROTOCOL_DRAFT_20261002.md decision 48 (user 2026-10-04: a quiet
calibration run at <= 6/h, 40 no-fault cells per system, 10 per rate x 4 rates, the sweep's cell shape), budget
research/traffic-sweep/BUDGET_CALIBRATION.md (committed alone before the work).

Every cell is the sweep's no-fault calibration cell: ``cell_timing`` takes the sweep compiler's own
``cell_timing("no-fault-calibration", rate, 1)`` and replaces only what belongs to this epoch -- the seeded onset of
the pseudo window (the sweep's stratified rule, drawn with this epoch's seed over its 10 blocks) and the plan-level
run count and minimum remaining time.  Route, rates, client timeout, concurrency, warm-up, measurement, hold, the
upstream generator removal, the frontendproxy memory limit, the container-health guard and the protocol gates are the
sweep's values, by construction.  No fault is applied in any cell.

Trace completeness (protocol decision 56, user 2026-10-04, after attempt 1 stopped on one lost batch of
productcatalogservice spans; main repo research/traffic-sweep/STOP_QUIET_OTEL_A1.md): the cell timing adds one key,
``traceCompletenessRule = "protocol-decision-56"``, under which the target records incomplete traces as telemetry loss
(per window, per missing service, with their contiguous runs) and never blocks.  The sweep's own timing has no such
key and keeps decision 25.  Attempt 1 is spent (candidate_runtime_adapter.SPENT_ATTEMPTS_BY_EPOCH); relaunch 1 is
attempt 2.

Schedule: 10 blocks; each block holds every rate exactly once, in a Fisher-Yates order drawn with SHA-256 from seed
20261004 (the sweep's block rule and draw encoding, with no lead cell).  The seed and every block's order are
recorded in the descriptor and in the compiled plan.

The epoch is active only when the committed selector ``execution/study-epoch.json`` names it
(``candidate_runtime.EPOCH_SELECTOR``).

Construction only: no Docker, SSH, subprocess, socket or transport surface.  Runs as ``python3 -I`` on CPython 3.9 on
the target (the runtime imports it there): standard library only, sibling files are loaded by path (``-I`` drops this
directory from ``sys.path``), no PEP 604 annotation evaluated at runtime.
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
from typing import Any, Dict, List, Mapping


HERE = Path(__file__).resolve().parent
MODULE = HERE.parent
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DESCRIPTOR = ROOT / "pipelines/campaigns/otel-quiet-calibration-v1.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The sweep compiler supplies the cell shape (its no-fault cell timing), the onset and shuffle rules this epoch
# re-draws with its own seed, the JSON helpers and the attempt rule.  It is read, never edited; its descriptor is
# loaded through its own pinned-digest check, so this epoch cannot derive from a drifted sweep.
sweep = _load("otel_quiet_sweep_compiler", HERE / "candidate_sweep.py")
frozen = sweep.frozen
gates = sweep.gates
ProtocolError = sweep.ProtocolError
canonical_sha256 = sweep.canonical_sha256
canonical_json_bytes = sweep.canonical_json_bytes
strict_json_loads = sweep.strict_json_loads
ATTEMPT_ENVIRONMENT = sweep.ATTEMPT_ENVIRONMENT
DEFAULT_ATTEMPT = sweep.DEFAULT_ATTEMPT
campaign_attempt = sweep.campaign_attempt
validate_attempt = sweep.validate_attempt
rate_token = sweep.rate_token
offered_for = sweep.offered_for

EPOCH = "otel-quiet-calibration-v1"
PREDECESSOR_EPOCH = sweep.EPOCH                       # otel-traffic-sweep-v1: the cell shape this epoch repeats
MODULE_ID = sweep.MODULE_ID
APPLICATION_FAMILY = sweep.APPLICATION_FAMILY
CHANNEL = sweep.CHANNEL
SCHEDULE_CONTEXT = "quiet-schedule-v1"
MAXIMUM_EVIDENCE_LABEL = sweep.MAXIMUM_EVIDENCE_LABEL

# ---------------------------------------------------------------- parameters (decision 48, user 2026-10-04)
POSTURES = sweep.POSTURES                             # ("full",)
RATES = sweep.RATES                                   # 10, 1, 0.2, 0.05 /s
REGIME = "no-fault-calibration"                       # the sweep's no-fault regime id; the runtime keys on it
REGIMES = (REGIME,)
FAULTS = {REGIME: None}
ARTIFACT_ROOTS = {REGIME: sweep.ARTIFACT_ROOTS[REGIME]}
BLOCKS = 10                                           # 10 cells per rate x 180 s = 30 min of quiet time per rate
SCHEDULE_SEED = 20261004
# The pseudo window's onset follows the sweep's rule (60 s + a seeded offset, stratified over the blocks of one
# (regime, rate) pair inside one inter-arrival); with 10 blocks there are 10 strata per rate.
ONSET_PHASE_OFFSET = sweep.ONSET_PHASE_OFFSET
# Wall budget: the sweep's engineering defaults, checked against relaunch 1 (fb14srv6, 2026-10-03): consecutive
# barrierEpoch gaps over its 12 cells are 302.7-314.9 s, mean 309.6 s (n = 11), below the 331 s estimate.
CELL_PERIOD_ESTIMATE_SECONDS = sweep.CELL_PERIOD_ESTIMATE_SECONDS
CELL_DEADLINE_RESERVE_SECONDS = sweep.CELL_DEADLINE_RESERVE_SECONDS
CLEANUP_RESERVE_SECONDS = sweep.CLEANUP_RESERVE_SECONDS
APPROVAL_TO_FIRST_MUTATION_SECONDS = sweep.APPROVAL_TO_FIRST_MUTATION_SECONDS
MEASURED_CELL_PERIOD_SECONDS = {
    "source": "otel-traffic-sweep-v1 relaunch 1 (fb14srv6, 2026-10-03), consecutive request-ledger barrierEpoch gaps",
    "cells": 12, "gaps": 11, "minimum": 302.7, "mean": 309.6, "maximum": 314.9,
}
DECLARATION = (
    "research/traffic-sweep/DECLARATION_QUIET_OTEL.md (measurement repo; frozen and committed alone before the first "
    "cell)"
)
# Protocol decision 56 (user 2026-10-04, research/PROTOCOL_DRAFT_20261002.md round 12): this epoch's trace rule, named
# in every cell's compiled timing and read by candidate_remote.trace_completeness (candidate_remote.TRACE_LOSS_RULE).
TRACE_COMPLETENESS_RULE = "protocol-decision-56"
AMENDMENTS = [
    "research/traffic-sweep/AMENDMENT_QUIET_OTEL_1.md (measurement repo): incomplete traces recorded as telemetry loss, "
    "never blocking, in this epoch's cells (research/PROTOCOL_DRAFT_20261002.md decision 56, user 2026-10-04); "
    "attempt 1 spent (stopped at cell 8, 7 of 8 valid; research/traffic-sweep/STOP_QUIET_OTEL_A1.md); relaunch 1 of "
    "2, all 40 cells, attempt 2",
]
AUTHORITY = (
    "main repo research/PROTOCOL_DRAFT_20261002.md decision 48 (user 2026-10-04: quiet calibration run at <= 6/h, "
    "40 no-fault cells per system, 10 per rate x 4 rates, same cell shape as the sweep); budget and stop rule "
    "research/traffic-sweep/BUDGET_CALIBRATION.md (committed alone before the work); proposal "
    "research/traffic-sweep/NEXT_CAMPAIGNS_PROPOSAL.md section A"
)
# ---------------------------------------------------------------- derived

TOTAL_RUNS = len(REGIMES) * len(RATES) * BLOCKS
CELLS_PER_BLOCK = len(REGIMES) * len(RATES)
QUIET_SECONDS_PER_RATE = BLOCKS * sweep.MEASUREMENT_SECONDS
MINIMUM_REMAINING_SECONDS = (
    TOTAL_RUNS * CELL_PERIOD_ESTIMATE_SECONDS + CELL_DEADLINE_RESERVE_SECONDS + CLEANUP_RESERVE_SECONDS
)
RUN_WINDOW_HOURS = int(math.ceil((MINIMUM_REMAINING_SECONDS + APPROVAL_TO_FIRST_MUTATION_SECONDS) / 3600.0))
EXPECTED_DESCRIPTOR_SHA256 = "36a7fd173a9995e6b0c0e9897d98ff76995ca375e045b90804fe92221dfd2286"


def _unit_draw(*parts: Any) -> float:
    return sweep._unit_draw(*parts)


def stratified_onset_offset(seed: int, epoch: str, episodes: int, regime: str, rate: float, block: int) -> float:
    """The sweep's onset_phase_offset with its seed, epoch and stratum count as arguments (tested to reproduce the
    sweep's own offsets when given the sweep's values)."""
    if not 1 <= int(block) <= int(episodes):
        raise ProtocolError("block %r is outside 1..%d" % (block, episodes))
    inter_arrival = 1.0 / float(rate)
    strata = sorted(range(episodes), key=lambda stratum: _unit_draw(
        seed, epoch, regime, rate_token(rate), "onset-stratum", stratum))
    stratum = strata[int(block) - 1]
    position = _unit_draw(seed, epoch, regime, rate_token(rate), "b%02d" % int(block), "onset-phase")
    offset = round((stratum + position) / episodes * inter_arrival, 6)
    return min(offset, round(inter_arrival - 1e-6, 6))


def onset_phase_offset(regime: str, rate: float, block: int) -> float:
    if ONSET_PHASE_OFFSET != "seeded-stratified-within-one-inter-arrival":
        raise ProtocolError("the quiet epoch keeps the sweep's seeded onset rule")
    return stratified_onset_offset(SCHEDULE_SEED, EPOCH, BLOCKS, regime, rate, block)


def fisher_yates(pairs: List[Dict[str, Any]], seed: int, epoch: str, block: int, context: str) -> List[Dict[str, Any]]:
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


def cell_timing(regime: str, rate: float, block: int) -> Dict[str, Any]:
    """The sweep's no-fault cell timing, with this epoch's onset draw, plan-level budget and trace rule."""
    if regime != REGIME or FAULTS[regime] is not None:
        raise ProtocolError("the quiet epoch compiles no-fault cells only")
    timing = sweep.cell_timing(REGIME, rate, 1)
    if timing["faultApplied"] is not False or timing["scheduledSlotsByPhase"] is not None:
        raise ProtocolError("the sweep's no-fault cell shape changed")
    offset = onset_phase_offset(regime, rate, block)
    onset = round(sweep.FAULT_ONSET_BASE_SECONDS + offset, 6)
    hold = timing["faultHoldSeconds"]
    if not 0 < onset < onset + hold + timing["postRecoveryAllowanceSeconds"] < timing["measurementSeconds"]:
        raise ProtocolError("pseudo window must lie strictly inside the measurement")
    timing.update({
        "faultOnsetPhaseOffsetSeconds": offset,
        "faultOnsetSeconds": onset,
        "scoredWindowSeconds": [onset, round(onset + hold, 6)],
        "planRunCount": TOTAL_RUNS,
        "planMinimumRemainingSeconds": MINIMUM_REMAINING_SECONDS,
        "traceCompletenessRule": TRACE_COMPLETENESS_RULE,
    })
    return timing


# The timing keys this epoch sets itself; every other key is the sweep's no-fault value (tested).
# traceCompletenessRule is the one key the sweep's timing does not have (decision 56).
OWN_TIMING_KEYS = frozenset({
    "faultOnsetPhaseOffsetSeconds", "faultOnsetSeconds", "scoredWindowSeconds", "planRunCount",
    "planMinimumRemainingSeconds", "traceCompletenessRule",
})


def run_key_for(regime: str, rate: float, block: int, posture: str, attempt: int) -> Dict[str, Any]:
    return {
        "studyEpoch": EPOCH, "regime": regime, "requestsPerSecond": float(rate),
        "block": int(block), "posture": posture, "attempt": validate_attempt(attempt),
    }


def run_id_for(run_key: Mapping[str, Any]) -> str:
    return sweep.run_id_for(run_key)


def allocate_schedule() -> List[Dict[str, Any]]:
    """The design-level schedule receipt (attempt-free): per block, the rate order."""
    if POSTURES != ("full",):
        raise ProtocolError("the quiet calibration runs the full posture only")
    if len(set(RATES)) != len(RATES) or any(not (math.isfinite(rate) and rate > 0) for rate in RATES):
        raise ProtocolError("rates must be distinct, finite and positive")
    blocks = []
    for block in range(1, BLOCKS + 1):
        order = ["%s@r%s" % (row["regime"], rate_token(row["rate"])) for row in block_order(block)]
        blocks.append({"block": block, "order": order, "orderSha256": canonical_sha256(order)})
    every = [(row["block"], item) for row in blocks for item in row["order"]]
    if len(every) != TOTAL_RUNS or len(set(every)) != TOTAL_RUNS:
        raise ProtocolError("schedule does not contain every cell exactly once")
    return blocks


def derive_quiet_descriptor(predecessor_path: Path = None) -> Dict[str, Any]:
    """Generate the quiet descriptor from the pinned sweep descriptor.

    This function IS the descriptor's source: the checked-in otel-quiet-calibration-v1.json must equal
    ``_pretty_bytes`` of its result (tested), so the file is regenerated, never hand-edited.  Carried over unchanged
    from the sweep: evidence, missingness, module, postureRealization, setupPreconditions, source, status, target,
    workload, collection, sutDeviations, containerHealthGuard, workflow.  Replaced: id, declaration, amendments,
    design, schedule, runIdentity, timing.budget, faultDesign (no scenario), groundTruth's fault contracts,
    outcomes, analysis (traceCompleteness: decision 56), protocolGates.blocking, and a ``derivedFrom`` record (the
    sweep is not superseded).
    """
    path = Path(predecessor_path) if predecessor_path is not None else sweep.DEFAULT_DESCRIPTOR
    base = sweep.load_descriptor(path)
    if base["id"] != PREDECESSOR_EPOCH:
        raise ProtocolError("the quiet epoch is derived from the sweep descriptor only")
    schedule = allocate_schedule()
    document = {key: copy.deepcopy(base[key]) for key in (
        "collection", "containerHealthGuard", "evidence", "missingness", "module", "postureRealization",
        "setupPreconditions", "source", "status", "sutDeviations", "target", "workflow", "workload",
    )}
    document["id"] = EPOCH
    document["declaration"] = DECLARATION
    document["amendments"] = list(AMENDMENTS)
    document["design"] = {
        "purpose": (
            "false-alarm calibration: certify a false-alarm rate <= 6/h per rate (95 %, 0 alarms: 3 / quiet hours) "
            "on no-fault time (research/PROTOCOL_DRAFT_20261002.md decision 48)"
        ),
        "postures": list(POSTURES),
        "regimes": [
            {"id": REGIME, "kind": "no-fault-calibration", "fault": None, "artifactRootClass": ARTIFACT_ROOTS[REGIME]}
        ],
        "omittedRegimes": {
            regime["id"]: "fault regime of the sweep; this epoch applies no fault (decision 48)"
            for regime in base["design"]["regimes"] if regime["fault"] is not None
        },
        "rates": list(RATES),
        "blocks": BLOCKS,
        "episodesPerRate": BLOCKS,
        "cellsPerBlock": CELLS_PER_BLOCK,
        "totalRuns": TOTAL_RUNS,
        "quietSecondsPerRate": QUIET_SECONDS_PER_RATE,
        "blockRule": "each-block-holds-every-rate-exactly-once",
        "coldStartEachRun": True,
        "faultAppliedToAnyCell": False,
        "noFaultCellsCarryPseudoWindow": True,
        "cellShape": (
            "the sweep's no-fault calibration cell (candidate_sweep.cell_timing('no-fault-calibration', rate, 1)); "
            "only the pseudo window's seeded onset and the plan-level run count and minimum remaining time differ"
        ),
        "postureRule": base["design"]["postureRule"],
    }
    document["schedule"] = {
        "version": SCHEDULE_CONTEXT,
        "seed": SCHEDULE_SEED,
        "shuffle": "fisher-yates-over-rates-within-each-block-with-sha256-draws",
        "drawEncoding": "UTF-8(seed || NUL || epoch || NUL || block-NN || NUL || draw-i || NUL || version)",
        "leadCell": None,
        "blocks": schedule,
    }
    document["runIdentity"] = copy.deepcopy(base["runIdentity"])
    timing = copy.deepcopy(base["timing"])
    timing["faultOnsetStrata"] = BLOCKS
    timing["budget"].update({
        "minimumRemainingSeconds": MINIMUM_REMAINING_SECONDS,
        "runWindowHours": RUN_WINDOW_HOURS,
        "measuredCellPeriodSeconds": copy.deepcopy(MEASURED_CELL_PERIOD_SECONDS),
    })
    document["timing"] = timing
    fault_design = copy.deepcopy(base["faultDesign"])
    fault_design["scenarios"] = {}
    fault_design["noFault"] = (
        "no fault is applied in any cell; every cell carries the pseudo window [onset, onset + hold] at the seeded "
        "onset (the sweep's no-fault rule), used for G1/G2 and for false alarms at the same onset phase"
    )
    document["faultDesign"] = fault_design
    truth = copy.deepcopy(base["groundTruth"])
    truth["fault"]["scenarioContracts"] = []
    truth["path"]["faultSpecificTruth"] = {}
    document["groundTruth"] = truth
    document["outcomes"] = {
        "primary": (
            "quiet time per rate, for the false-alarm rate per hour of each detector at a common operating point "
            "(decisions 33 and 48); with 0 alarms in T quiet hours the 95 % upper bound is 3 / T per hour"
        ),
        "secondary": None,
        "costRegimeOnly": None,
        "offeredRequestsAreDenominator": True,
        "windowMembership": "monotonic-shared-barrier",
    }
    analysis = copy.deepcopy(base["analysis"])
    # The sweep's one-episode framing (descriptive only, shakedown, miss charged at the hold end) is not this epoch's;
    # what replaces it is analysis v2's to say, so the keys are dropped rather than given new values.
    for key in ("descriptiveOnly", "initialTest", "detectionTimeMissCharge"):
        analysis.pop(key)
    analysis.update({
        "comparativeUnit": "rate; 10 no-fault cells per rate",
        "analysisFreeze": (
            "no analysis of this epoch's evidence until analysis v2 is frozen (BUDGET_CALIBRATION.md stop rule 4; "
            "research/protocol/METHODOLOGY_HARDENING.md section 4)"
        ),
        "traceCompleteness": {
            "authority": (
                "research/PROTOCOL_DRAFT_20261002.md decision 56 (user 2026-10-04, round 12, on "
                "research/traffic-sweep/STOP_QUIET_OTEL_A1.md); this epoch only, the sweep keeps decision 25"
            ),
            "ruleId": TRACE_COMPLETENESS_RULE,
            "timingKey": "traceCompletenessRule",
            "blocking": False,
            "rule": (
                "one whole-measurement window (every cell is a no-fault cell). Complete = the request's own trace id "
                "observed and exactly the route's services. A successful request without a complete trace is "
                "telemetry loss: counted and recorded, never blocking. trace-completeness.json records per window the "
                "successful, complete and incomplete requests (unsuccessful separately); for every incomplete request "
                "its scheduled offset, whether its own trace id was observed and which required path services were "
                "missing; the count of incomplete requests per missing service; and the contiguous runs of "
                "consecutively scheduled requests that are each successful and incomplete (first and last scheduled "
                "offset, request count, missing services), so a lost export batch shows as one run. Evaluated on the "
                "target before the next cell and replayed byte for byte by the terminal"
            ),
            "decision25Counterfactual": (
                "recorded per cell, not applied: max(allowanceMinimum, floor(allowanceShare x successful requests)) "
                "and whether the incomplete count exceeds it"
            ),
            "allowanceShare": sweep.TRACE_INCOMPLETE_ALLOWANCE_SHARE,
            "allowanceMinimum": sweep.TRACE_INCOMPLETE_ALLOWANCE_MINIMUM,
            "stillBlocking": (
                "G1, G2, G4, the container-health guard, and the terminal's ledger, application-witness, "
                "generator-absence, posture and application-log checks"
            ),
        },
    })
    document["analysis"] = analysis
    protocol = copy.deepcopy(base["protocolGates"])
    protocol["blocking"] = ["G1", "G2", "G4"]
    protocol["blockingNote"] = "F1 is evaluated in fault cells only; this epoch has none"
    document["protocolGates"] = protocol
    document["derivedFrom"] = {
        "authority": AUTHORITY,
        "studyEpoch": PREDECESSOR_EPOCH,
        "descriptorPath": str(path_relative(path)),
        "descriptorByteSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "descriptorCanonicalSha256": canonical_sha256(base),
        "inheritedAmendments": copy.deepcopy(base["amendments"]),
        "disposition": (
            "the sweep epoch is not superseded: it keeps its own descriptor, plan, admission history and spent "
            "attempts; the quiet epoch is a separate epoch selected by execution/study-epoch.json"
        ),
    }
    return document


def path_relative(path: Path) -> Path:
    return Path(path).resolve().relative_to(ROOT)


def _pretty_bytes(value: Any) -> bytes:
    return frozen._pretty_bytes(value)


def validate_descriptor(document: Any) -> Dict[str, Any]:
    """Exactly the generated document, and the reviewed digest."""
    if not isinstance(document, dict):
        raise ProtocolError("quiet descriptor must be one JSON object")
    expected = derive_quiet_descriptor()
    if canonical_json_bytes(document) != canonical_json_bytes(expected):
        raise ProtocolError("quiet descriptor differs from its generator")
    digest = canonical_sha256(document)
    if digest != EXPECTED_DESCRIPTOR_SHA256:
        raise ProtocolError(
            "quiet descriptor canonical digest differs from the reviewed pin: expected %s, found %s"
            % (EXPECTED_DESCRIPTOR_SHA256, digest)
        )
    return document


def load_descriptor(path: Path = DEFAULT_DESCRIPTOR) -> Dict[str, Any]:
    try:
        payload = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProtocolError("cannot read quiet descriptor: %s" % exc) from exc
    return copy.deepcopy(validate_descriptor(strict_json_loads(payload)))


def _compile(document: Mapping[str, Any], attempt: int) -> Dict[str, Any]:
    attempt = validate_attempt(attempt)
    blocks = []
    run_ids: List[str] = []
    for receipt in document["schedule"]["blocks"]:
        number = receipt["block"]
        cells = []
        for position, pair in enumerate(block_order(number), start=1):
            regime, rate, posture = pair["regime"], pair["rate"], POSTURES[0]
            if "%s@r%s" % (regime, rate_token(rate)) != receipt["order"][position - 1]:
                raise ProtocolError("compiled order differs from the descriptor's schedule receipt")
            key = run_key_for(regime, rate, number, posture, attempt)
            run_id = run_id_for(key)
            run_ids.append(run_id)
            cells.append({
                "runKey": key,
                "runId": run_id,
                "ordinalPosition": position,
                "artifactRoot": "runs/%s/r%s-b%02d-%02d-%s" % (
                    ARTIFACT_ROOTS[regime], rate_token(rate), number, position, posture),
                "realizationStatus": document["postureRealization"][posture]["status"],
                "fault": FAULTS[regime],
                "timing": cell_timing(regime, rate, number),
            })
        blocks.append({"block": number, "order": [cell["runId"] for cell in cells], "cells": cells})
    return {
        "schemaVersion": 1,
        "kind": "otel-demo-quiet-calibration-compiled-plan",
        "studyEpoch": EPOCH,
        "module": MODULE_ID,
        "applicationFamily": APPLICATION_FAMILY,
        "channel": CHANNEL,
        "descriptorSha256": canonical_sha256(document),
        "scheduleVersion": SCHEDULE_CONTEXT,
        "schedule": {
            "seed": document["schedule"]["seed"],
            "shuffle": document["schedule"]["shuffle"],
            "drawEncoding": document["schedule"]["drawEncoding"],
            "blockOrders": [
                {"block": row["block"], "order": list(row["order"]), "orderSha256": row["orderSha256"]}
                for row in document["schedule"]["blocks"]
            ],
        },
        "blocks": blocks,
        "runCount": len(run_ids),
        "uniqueRunCount": len(set(run_ids)),
        "minimumRemainingSeconds": MINIMUM_REMAINING_SECONDS,
        "runWindowHours": RUN_WINDOW_HOURS,
        "runtimeReady": False,
        "runtimeAuthorized": False,
        "candidateExecutionEnabled": False,
        "maximumEvidenceLabel": MAXIMUM_EVIDENCE_LABEL,
        "blockers": copy.deepcopy(document["workflow"]["constructionBlockers"]),
    }


def flatten_cells(plan: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [copy.deepcopy(cell) for block in plan["blocks"] for cell in block["cells"]]


def plan_attempt(plan: Any) -> int:
    """The one attempt every cell of a compiled quiet plan carries."""
    try:
        attempts = {cell["runKey"]["attempt"] for block in plan["blocks"] for cell in block["cells"]}
    except (KeyError, TypeError) as exc:
        raise ProtocolError("compiled plan cells carry no attempt") from exc
    if len(attempts) != 1:
        raise ProtocolError("compiled plan mixes attempts %s" % sorted(map(repr, attempts)))
    return validate_attempt(next(iter(attempts)))


def compile_plan(document: Mapping[str, Any], attempt: int = DEFAULT_ATTEMPT) -> Dict[str, Any]:
    validate_descriptor(document)
    plan = _compile(document, attempt)
    validate_plan(document, plan)
    return copy.deepcopy(plan)


def validate_plan(document: Mapping[str, Any], plan: Any) -> None:
    validate_descriptor(document)
    expected = _compile(document, plan_attempt(plan))
    if canonical_json_bytes(plan) != canonical_json_bytes(expected):
        raise ProtocolError("compiled plan differs from the frozen schedule")
    cells = flatten_cells(plan)
    if (
        plan.get("runCount") != TOTAL_RUNS or plan.get("uniqueRunCount") != TOTAL_RUNS
        or len(cells) != TOTAL_RUNS or len({cell["runId"] for cell in cells}) != TOTAL_RUNS
        or plan.get("runtimeReady") is not False or plan.get("runtimeAuthorized") is not False
        or plan.get("candidateExecutionEnabled") is not False
    ):
        raise ProtocolError("compiled plan geometry or runtime denial differs")
    if [block["block"] for block in plan["blocks"]] != list(range(1, BLOCKS + 1)):
        raise ProtocolError("compiled plan blocks are not 1..%d in order" % BLOCKS)
    for block in plan["blocks"]:
        rates = sorted(cell["runKey"]["requestsPerSecond"] for cell in block["cells"])
        if rates != sorted(float(rate) for rate in RATES):
            raise ProtocolError("block %r does not hold every rate exactly once" % block["block"])
    for cell in cells:
        if cell["fault"] is not None or cell["runKey"]["regime"] != REGIME or cell["timing"]["faultApplied"]:
            raise ProtocolError("the quiet plan holds a fault cell")


def readiness_report(document: Mapping[str, Any], plan: Mapping[str, Any]) -> Dict[str, Any]:
    validate_plan(document, plan)
    return {
        "schemaVersion": 1,
        "kind": "otel-demo-candidate-construction-readiness",
        "studyEpoch": EPOCH,
        "descriptorSha256": canonical_sha256(document),
        "planSha256": canonical_sha256(plan),
        "runCount": TOTAL_RUNS,
        "unsupportedPostures": [],
        "constructionValid": True,
        "runtimeReady": False,
        "runtimeAuthorized": False,
        "candidateExecutionEnabled": False,
        "blockers": copy.deepcopy(document["workflow"]["constructionBlockers"]),
    }


def materialize(root: Path, descriptor_path: Path = DEFAULT_DESCRIPTOR, attempt: int = None) -> Dict[str, Any]:
    """Create or exactly replay the local construction artifacts (the frozen compiler's file rule)."""
    root = Path(root).resolve()
    if root in {Path("/"), Path.home(), ROOT} or root in ROOT.parents:
        raise ProtocolError("unsafe construction root: %s" % root)
    document = load_descriptor(descriptor_path)
    plan = compile_plan(document, campaign_attempt() if attempt is None else attempt)
    receipt = readiness_report(document, plan)
    frozen._install_or_verify(root / frozen.DESCRIPTOR_COPY, _pretty_bytes(document), frozen.DESCRIPTOR_COPY)
    frozen._install_or_verify(root / frozen.PLAN_COPY, _pretty_bytes(plan), frozen.PLAN_COPY)
    frozen._install_or_verify(root / frozen.RECEIPT_COPY, _pretty_bytes(receipt), frozen.RECEIPT_COPY)
    retained_document = strict_json_loads((root / frozen.DESCRIPTOR_COPY).read_text())
    retained_plan = strict_json_loads((root / frozen.PLAN_COPY).read_text())
    retained_receipt = strict_json_loads((root / frozen.RECEIPT_COPY).read_text())
    validate_plan(retained_document, retained_plan)
    if canonical_json_bytes(retained_receipt) != canonical_json_bytes(readiness_report(retained_document, retained_plan)):
        raise ProtocolError("retained construction receipt differs")
    return copy.deepcopy(retained_receipt)


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?")
    parser.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    parser.add_argument("--attempt", type=int, default=None)
    parser.add_argument(
        "--emit-descriptor", action="store_true",
        help="write (exclusive-create) or byte-verify <root> as the quiet descriptor derived from the sweep",
    )
    parser.add_argument("--print-digests", action="store_true",
                        help="print the unpinned descriptor and attempt plan digests (for re-pinning after a change)")
    args = parser.parse_args(argv)
    if args.print_digests:
        document = derive_quiet_descriptor()
        attempt = campaign_attempt() if args.attempt is None else args.attempt
        print(json.dumps({
            "studyEpoch": EPOCH,
            "descriptorCanonicalSha256": canonical_sha256(document),
            "attempt": attempt,
            "planCanonicalSha256": canonical_sha256(_compile(document, attempt)),
            "runCount": TOTAL_RUNS,
            "minimumRemainingSeconds": MINIMUM_REMAINING_SECONDS,
            "runWindowHours": RUN_WINDOW_HOURS,
        }, indent=2, sort_keys=True))
        return 0
    if args.root is None:
        parser.error("root is required")
    if args.emit_descriptor:
        frozen._install_or_verify(Path(args.root), _pretty_bytes(derive_quiet_descriptor()), "quiet descriptor")
        print(canonical_sha256(derive_quiet_descriptor()))
        return 0
    print(json.dumps(materialize(args.root, args.descriptor, args.attempt), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
