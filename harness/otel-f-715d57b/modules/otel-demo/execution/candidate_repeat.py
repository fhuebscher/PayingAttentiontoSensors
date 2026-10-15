#!/usr/bin/env python3
"""Compile the OTel Demo repeat-episodes epoch (otel-repeat-episodes-v1, campaign B) without executing it.

A fourth epoch beside the frozen offpath compiler (``candidate_pilot.py``), the traffic sweep (``candidate_sweep.py``,
otel-traffic-sweep-v1, relaunch 1 terminal-valid 12/12 on 2026-10-03) and the quiet calibration (``candidate_quiet.py``,
otel-quiet-calibration-v1), all of which this file only reads.  Authority: main repo research/PROTOCOL_DRAFT_20261002.md
decision 49 (user 2026-10-04: 3 more blocks on TeaStore and OTel, after the H10/H4 harness change), decision 50 (fault
doses inherited from Hotel: CPU throttle to 0.1 cores, a fixed factor), decision 56 (trace loss recorded, never blocking,
in no-fault cells); budget research/traffic-sweep/BUDGET_B.md (92ca1c7, committed alone before the work); design
research/traffic-sweep/NEXT_CAMPAIGNS_PROPOSAL.md section B; harness changes research/protocol/METHODOLOGY_HARDENING.md
H10 and H4.

The design is the sweep's: one route (GET /api/products/66VCHSJNUP) at 10, 1, 0.2 and 0.05 requests per second, three
regimes (no fault, frontend pause, productcatalogservice CPU throttle to 0.1 cores), posture ``full`` only, the sweep's
client timeout, concurrency, warm-up, measurement, hold, upstream generator removal, frontendproxy memory limit,
container-health guard and protocol gates -- by construction: ``cell_timing`` takes the sweep compiler's own
``cell_timing(regime, rate, 1)`` and replaces only what belongs to this epoch.  What is new:

* 3 blocks (36 cells), each block holding every (regime, rate) pair once in a Fisher-Yates order drawn with SHA-256 from
  seed 20261009 (the quiet epoch's draw encoding; no lead cell), and one seeded fault onset per (regime, rate, block)
  stratified over the 3 blocks inside one inter-arrival.
* H10: no readiness probe from the fault onset to the end of the hold (``duringFaultProbe`` False).  Probes outside that
  window (stack and route readiness before the warm-up, the post-revert readiness probes) are unchanged.
* H4: the freeze is stamped (``freezeStamps`` True): every fault receipt carries ``freeze`` (command issued, command
  returned, applied-state readback, and a ``stampCheck`` record), and a pause cell retains ``docker-events.json`` with the
  Docker ``pause`` and ``unpause`` events of the target container (event time in nanoseconds and the cell's monotonic
  mapping).  Decision 69 (user 2026-10-09): H4 is RECORDED, never blocking -- a failed, dead or contradictory stream or stamp
  leaves the cell valid with its record marked ``missing`` or ``contradictory`` (reason and failure count); only a record
  that does not replay from its own retained inputs (tampering) is refused.
* Trace completeness: fault cells keep the sweep's decision-25 rule (no timing key); no-fault cells carry
  ``traceCompletenessRule = "protocol-decision-56"`` (recorded, never blocking), as the quiet epoch's cells do.

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
DEFAULT_DESCRIPTOR = ROOT / "pipelines/campaigns/otel-repeat-episodes-v1.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The quiet compiler supplies the stratified onset and the block shuffle (both already parameterised by seed, epoch and
# stratum count and tested to reproduce the sweep's own draws), the decision-56 rule id and its descriptor block; it in
# turn loads the sweep compiler, which supplies the cell shape, the scenarios, the JSON helpers and the attempt rule.
# Both are read, never edited; their descriptors are loaded through their own pinned-digest checks.  ``sweep`` is the
# very module instance the quiet compiler loaded, so every ProtocolError is one class.
quiet = _load("otel_repeat_quiet_compiler", HERE / "candidate_quiet.py")
sweep = quiet.sweep
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

EPOCH = "otel-repeat-episodes-v1"
PREDECESSOR_EPOCH = sweep.EPOCH                       # otel-traffic-sweep-v1: the cell shape this epoch repeats
MODULE_ID = sweep.MODULE_ID
APPLICATION_FAMILY = sweep.APPLICATION_FAMILY
CHANNEL = sweep.CHANNEL
SCHEDULE_CONTEXT = "repeat-schedule-v1"
MAXIMUM_EVIDENCE_LABEL = sweep.MAXIMUM_EVIDENCE_LABEL

# ---------------------------------------------------------------- parameters (decisions 49 and 50, user 2026-10-04)
POSTURES = sweep.POSTURES                             # ("full",)
RATES = sweep.RATES                                   # 10, 1, 0.2, 0.05 /s
REGIMES = sweep.REGIMES
FAULTS = dict(sweep.FAULTS)
ARTIFACT_ROOTS = dict(sweep.ARTIFACT_ROOTS)
NO_FAULT_REGIME = "no-fault-calibration"
BLOCKS = 3                                            # 3 more blocks; with the sweep's one, 4 in total, like Hotel
SCHEDULE_SEED = 20261009
ONSET_PHASE_OFFSET = sweep.ONSET_PHASE_OFFSET
# H10 (METHODOLOGY_HARDENING.md row 6 and section 3; decision 42): no readiness probe during the fault, and H4: stamp
# the freeze.  Both are named in every cell's compiled timing and read by candidate_remote / candidate_terminal.
DURING_FAULT_PROBE = False
FREEZE_STAMPS = True
# Under H10 no probe observes the route during the fault, so a scenario's entry-route expectation is "not probed": a
# pause is proven by the paused container state plus the Docker ``pause`` event, a throttle by the applied quota.
ENTRY_ROUTE_DURING_FAULT = "not-probed-h10"
SCENARIOS = copy.deepcopy(sweep.SCENARIOS)
for _scenario in SCENARIOS.values():
    _scenario["entryRouteDuringFault"] = ENTRY_ROUTE_DURING_FAULT
# Wall budget: the sweep's engineering defaults, checked against relaunch 1 (fb14srv6, 2026-10-03): consecutive
# barrierEpoch gaps over its 12 cells are 302.7-314.9 s, mean 309.6 s (n = 11), below the 331 s estimate.
CELL_PERIOD_ESTIMATE_SECONDS = sweep.CELL_PERIOD_ESTIMATE_SECONDS
CELL_DEADLINE_RESERVE_SECONDS = sweep.CELL_DEADLINE_RESERVE_SECONDS
CLEANUP_RESERVE_SECONDS = sweep.CLEANUP_RESERVE_SECONDS
APPROVAL_TO_FIRST_MUTATION_SECONDS = sweep.APPROVAL_TO_FIRST_MUTATION_SECONDS
MEASURED_CELL_PERIOD_SECONDS = copy.deepcopy(quiet.MEASURED_CELL_PERIOD_SECONDS)
DECLARATION = (
    "research/traffic-sweep/DECLARATION_B_OTEL.md (measurement repo; frozen and committed alone before the first cell)"
)
AMENDMENTS: List[str] = []
AUTHORITY = (
    "main repo research/PROTOCOL_DRAFT_20261002.md decision 49 (user 2026-10-04: B, 3 more blocks on TeaStore and OTel, "
    "after the H10/H4 harness change), decision 50 (fault doses inherited from Hotel, a fixed factor), decision 56 "
    "(trace loss recorded, never blocking, in no-fault cells), decision 69 (H4 recorded, never blocking); budget and stop rule research/traffic-sweep/BUDGET_B.md "
    "(92ca1c7, committed alone before the work); proposal research/traffic-sweep/NEXT_CAMPAIGNS_PROPOSAL.md section B; "
    "harness changes research/protocol/METHODOLOGY_HARDENING.md H10 and H4"
)
# ---------------------------------------------------------------- derived

TOTAL_RUNS = len(REGIMES) * len(RATES) * BLOCKS
CELLS_PER_BLOCK = len(REGIMES) * len(RATES)
MINIMUM_REMAINING_SECONDS = (
    TOTAL_RUNS * CELL_PERIOD_ESTIMATE_SECONDS + CELL_DEADLINE_RESERVE_SECONDS + CLEANUP_RESERVE_SECONDS
)
RUN_WINDOW_HOURS = int(math.ceil((MINIMUM_REMAINING_SECONDS + APPROVAL_TO_FIRST_MUTATION_SECONDS) / 3600.0))
EXPECTED_DESCRIPTOR_SHA256 = "6e5d0f3460d28142428221c259994011a3a02973392aca4ffe6a4eb47a81a4ce"


def onset_phase_offset(regime: str, rate: float, block: int) -> float:
    if ONSET_PHASE_OFFSET != "seeded-stratified-within-one-inter-arrival":
        raise ProtocolError("the repeat epoch keeps the sweep's seeded onset rule")
    return quiet.stratified_onset_offset(SCHEDULE_SEED, EPOCH, BLOCKS, regime, rate, block)


def block_order(block: int) -> List[Dict[str, Any]]:
    """Every (regime, rate) pair once in this block, Fisher-Yates shuffled by SHA-256 draws keyed by seed and block (the
    sweep's rule and draw encoding, with this epoch's seed, epoch and context); no lead cell."""
    if not 1 <= int(block) <= BLOCKS:
        raise ProtocolError("block %r is outside 1..%d" % (block, BLOCKS))
    return quiet.fisher_yates(
        [{"regime": regime, "rate": float(rate)} for regime in REGIMES for rate in RATES],
        SCHEDULE_SEED, EPOCH, int(block), SCHEDULE_CONTEXT,
    )


def cell_timing(regime: str, rate: float, block: int) -> Dict[str, Any]:
    """The sweep's cell timing for the regime and rate, with this epoch's onset draw, plan-level budget, H10/H4 flags and
    (no-fault cells only) the decision-56 trace rule."""
    if regime not in REGIMES:
        raise ProtocolError("unknown regime %r" % (regime,))
    faulted = FAULTS[regime] is not None
    timing = sweep.cell_timing(regime, rate, 1)
    if timing["faultApplied"] is not faulted:
        raise ProtocolError("the sweep's fault/no-fault cell boundary changed")
    offset = onset_phase_offset(regime, rate, block)
    onset = round(sweep.FAULT_ONSET_BASE_SECONDS + offset, 6)
    hold = timing["faultHoldSeconds"]
    if not 0 < onset < onset + hold + timing["postRecoveryAllowanceSeconds"] < timing["measurementSeconds"]:
        raise ProtocolError("fault window must lie strictly inside the measurement")
    timing.update({
        "faultOnsetPhaseOffsetSeconds": offset,
        "faultOnsetSeconds": onset,
        "scoredWindowSeconds": [onset, round(onset + hold, 6)],
        "scheduledSlotsByPhase": (
            sweep.scheduled_slots_by_phase(rate, timing["measurementSeconds"], onset, hold) if faulted else None
        ),
        "planRunCount": TOTAL_RUNS,
        "planMinimumRemainingSeconds": MINIMUM_REMAINING_SECONDS,
        "duringFaultProbe": DURING_FAULT_PROBE,
        "freezeStamps": FREEZE_STAMPS,
    })
    if not faulted:
        timing["traceCompletenessRule"] = quiet.TRACE_COMPLETENESS_RULE
    return timing


# The timing keys this epoch sets itself; every other key is the sweep's value for the cell (tested).  The trace-rule
# key is on no-fault cells only: fault cells keep the sweep's decision-25 rule, which has no key.
OWN_TIMING_KEYS = frozenset({
    "faultOnsetPhaseOffsetSeconds", "faultOnsetSeconds", "scoredWindowSeconds", "scheduledSlotsByPhase", "planRunCount",
    "planMinimumRemainingSeconds", "duringFaultProbe", "freezeStamps",
})
NO_FAULT_ONLY_TIMING_KEYS = frozenset({"traceCompletenessRule"})


def run_key_for(regime: str, rate: float, block: int, posture: str, attempt: int) -> Dict[str, Any]:
    return {
        "studyEpoch": EPOCH, "regime": regime, "requestsPerSecond": float(rate),
        "block": int(block), "posture": posture, "attempt": validate_attempt(attempt),
    }


def run_id_for(run_key: Mapping[str, Any]) -> str:
    return sweep.run_id_for(run_key)


def allocate_schedule() -> List[Dict[str, Any]]:
    """The design-level schedule receipt (attempt-free): per block, the (regime, rate) order."""
    if POSTURES != ("full",):
        raise ProtocolError("the repeat epoch runs the full posture only")
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


def derive_repeat_descriptor(predecessor_path: Path = None) -> Dict[str, Any]:
    """Generate the repeat descriptor from the pinned sweep descriptor.

    This function IS the descriptor's source: the checked-in otel-repeat-episodes-v1.json must equal ``_pretty_bytes``
    of its result (tested), so the file is regenerated, never hand-edited.  Carried over unchanged from the sweep:
    evidence, missingness, module, postureRealization, setupPreconditions, source, status, target, workload, collection
    (plus the H4 record), sutDeviations, containerHealthGuard, workflow, protocolGates.  Replaced: id, declaration,
    amendments, design, schedule, runIdentity, timing (budget, H10/H4), faultDesign (scenarios, probes, freeze),
    groundTruth's fault contracts, outcomes, analysis (traceCompleteness per cell kind) and a ``derivedFrom`` record
    (the sweep is not superseded).
    """
    path = Path(predecessor_path) if predecessor_path is not None else sweep.DEFAULT_DESCRIPTOR
    base = sweep.load_descriptor(path)
    if base["id"] != PREDECESSOR_EPOCH:
        raise ProtocolError("the repeat epoch is derived from the sweep descriptor only")
    schedule = allocate_schedule()
    document = {key: copy.deepcopy(base[key]) for key in (
        "containerHealthGuard", "evidence", "missingness", "module", "postureRealization", "protocolGates",
        "setupPreconditions", "source", "status", "sutDeviations", "target", "workflow", "workload",
    )}
    document["id"] = EPOCH
    document["declaration"] = DECLARATION
    document["amendments"] = list(AMENDMENTS)
    design = copy.deepcopy(base["design"])
    design.update({
        "purpose": (
            "repeat episodes: 3 more blocks of the traffic sweep's 12 (regime, rate) cells on a harness with H10 (no "
            "readiness probe during the fault) and H4 (the freeze is stamped), so that with the sweep's own block there "
            "are 4 episodes per cell, like Hotel (decision 49)"
        ),
        "blocks": BLOCKS,
        "episodesPerRegimeAndRate": BLOCKS,
        "cellsPerBlock": CELLS_PER_BLOCK,
        "totalRuns": TOTAL_RUNS,
        "cellShape": (
            "the sweep's cell (candidate_sweep.cell_timing(regime, rate, 1)); only the seeded fault onset (3 strata), "
            "the slots per phase it implies, the plan-level run count and minimum remaining time, the H10/H4 flags and, "
            "in no-fault cells, the decision-56 trace rule differ"
        ),
        "doses": "inherited from the sweep and Hotel's fault catalogue as a fixed factor (decision 50): CPU throttle to 0.1 cores",
        "harnessChanges": {
            "H10": "no readiness probe from the fault onset to the end of the hold; probes outside that window unchanged",
            "H4": (
                "the freeze is stamped and RECORDED, never blocking (decision 69): command issued, command returned, "
                "applied-state readback (every fault); the Docker pause and unpause events of the target container "
                "with event time in ns and the cell's monotonic mapping (pause cells)"
            ),
        },
    })
    document["design"] = design
    document["schedule"] = {
        "version": SCHEDULE_CONTEXT,
        "seed": SCHEDULE_SEED,
        "shuffle": "fisher-yates-over-regimes-x-rates-with-sha256-draws",
        "drawEncoding": "UTF-8(seed || NUL || epoch || NUL || block-NN || NUL || draw-i || NUL || version)",
        "leadCell": None,
        "blocks": schedule,
    }
    document["runIdentity"] = copy.deepcopy(base["runIdentity"])
    timing = copy.deepcopy(base["timing"])
    timing["faultOnsetStrata"] = BLOCKS
    timing["duringFaultProbe"] = DURING_FAULT_PROBE
    timing["duringFaultProbeRule"] = (
        "H10: no readiness probe from the fault onset to the end of the hold (scored window [onset, onset + hold]); the "
        "post-revert readiness probes start after the revert command returns, and the stack and route readiness before "
        "the warm-up are unchanged"
    )
    timing["freezeStamps"] = FREEZE_STAMPS
    timing["budget"].update({
        "minimumRemainingSeconds": MINIMUM_REMAINING_SECONDS,
        "runWindowHours": RUN_WINDOW_HOURS,
        "measuredCellPeriodSeconds": copy.deepcopy(MEASURED_CELL_PERIOD_SECONDS),
    })
    document["timing"] = timing
    fault_design = copy.deepcopy(base["faultDesign"])
    fault_design["scenarios"] = copy.deepcopy(SCENARIOS)
    fault_design["probes"] = (
        "H10: no route probe is sent from the onset to the end of the hold; the post-revert readiness probes are "
        "stamped into the receipt's probes list (phase, start/end monotonic, available) so the analysis can exclude "
        "their windows from sensor scoring; probe requests carry the token readiness-not-scored. duringRouteAvailable "
        "is null"
    )
    fault_design["manifestation"] = (
        "pause: the paused container state read back after the command; throttle: the applied NanoCpus read back. The "
        "Docker pause event is evidence recorded beside it, not a condition of manifestation (decision 69). The entry "
        "route is not probed during the fault (scenario entryRouteDuringFault is not-probed-h10)"
    )
    fault_design["freezeStamps"] = {
        "authority": "METHODOLOGY_HARDENING.md H4 (decision 42, user 2026-10-04); recorded, never blocking: decision 69 (user 2026-10-09)",
        "rule": (
            "H4 never invalidates a cell. A failed, dead or contradictory event stream or stamp leaves the cell valid and "
            "the freeze record marked missing (an absence: no stream, no event) or contradictory (events or stamps that "
            "disagree), with its reasons and a failure count per cell, in docker-events.json verdict and in "
            "intervention.json freeze.stampCheck. The terminal replays and byte-compares whatever was retained: a record "
            "that does not replay from its own raw lines, clock and receipt is refused (integrity), a record that "
            "replays and says missing or contradictory is accepted (availability)"
        ),
        "receipt": (
            "intervention.json freeze = {schemaVersion 1, kind otel-demo-fault-freeze-stamps-v1, action, "
            "commandIssuedMonotonic (= startedMonotonic), commandReturnedMonotonic (taken when the fault command "
            "returns, before the state readback), stateReadbackMonotonic (= appliedMonotonic), the three barrier-"
            "relative offsets, dockerEventsFile, stampCheck {status ok|missing|contradictory, failures, reasons}}; "
            "expected: commandIssued <= commandReturned <= stateReadback, issued = startedMonotonic, readback = "
            "appliedMonotonic, returned <= revertingMonotonic"
        ),
        "dockerEvents": (
            "pause cells only: docker-events.json, kind otel-demo-fault-docker-events-v1, retained beside "
            "intervention.json. A live `docker events` stream (filters type=container, event=pause, event=unpause, "
            "label com.docker.compose.project=<project>) is started before the measurement barrier and stopped after "
            "the fault worker has settled, so the daemon's bounded event buffer cannot lose the event. The file holds "
            "the stream's raw JSON lines, the parsed events (action, containerId, service, timeNano, monotonic and "
            "barrier-relative offset by the cell's mapping), parseProblems for lines that could not be parsed, and the "
            "mapping. Verdict {status ok|missing|contradictory, failures, reasons[{kind, reason}], ...}: ok iff the "
            "stream was alive when stopped, there is exactly one pause event and one unpause event of the target "
            "container, the pause event lies in [commandIssued, commandReturned] and the unpause event in "
            "[revertCommandIssued, revertCommandReturned], each widened by the declared tolerance (0.25 s), and the "
            "unpause follows the pause; absences are missing, anything that disagrees is contradictory"
        ),
        "throttleStamps": "command issued and command returned monotonic stamps and the applied-state readback stamp; no events",
        "onsetInterval": (
            "pause: [commandIssued, Docker pause event]; throttle: [commandIssued, commandReturned] plus the applied "
            "quota read back"
        ),
    }
    document["faultDesign"] = fault_design
    truth = copy.deepcopy(base["groundTruth"])
    fault = truth["fault"]
    for contract in fault["scenarioContracts"]:
        contract["entryRouteDuringFault"] = ENTRY_ROUTE_DURING_FAULT
    fault["requiredReceiptFields"] = sorted(set(fault["requiredReceiptFields"]) | {"freeze"})
    fault["freezeStamps"] = "pause: docker-events.json beside intervention.json; every fault: intervention.json freeze"
    document["groundTruth"] = truth
    document["outcomes"] = {
        "primary": (
            "time to detection per sensor and for the request ledger, per (fault, rate) over the sweep's episode and "
            "these three (4 episodes like Hotel); analysis v3's to define (decision 49)"
        ),
        "secondary": "impact before detection: failed requests started before the first catch, by scheduled time",
        "costRegimeOnly": None,
        "offeredRequestsAreDenominator": True,
        "windowMembership": "monotonic-shared-barrier",
    }
    analysis = copy.deepcopy(base["analysis"])
    # The sweep's one-episode framing (descriptive only, shakedown, miss charged at the hold end) is not this epoch's;
    # what replaces it is analysis v3's to say, so the keys are dropped rather than given new values.
    for key in ("descriptiveOnly", "initialTest", "detectionTimeMissCharge"):
        analysis.pop(key)
    decision25 = analysis["traceCompleteness"]
    decision56 = quiet.derive_quiet_descriptor()["analysis"]["traceCompleteness"]
    analysis.update({
        "comparativeUnit": "(fault, rate); 3 episodes per pair here, 4 with the sweep's",
        "analysisFreeze": (
            "no analysis of this epoch's evidence until analysis v3 is frozen and reviewed (BUDGET_B.md stop rule 4; "
            "this is the first data read under v3)"
        ),
        "duringFaultProbes": "none (H10): the receipt's probes are the post-revert readiness probes only",
        "traceCompleteness": {
            "authority": (
                "fault cells: research/PROTOCOL_DRAFT_20261002.md decision 25 (user 2026-10-03, as the sweep); no-fault "
                "cells: decision 56 (user 2026-10-04, as the quiet epoch)"
            ),
            "ruleByCellKind": {
                "fault": "protocol-decision-25 (no timing key; blocking above max(1, 1 %) outside the fault-and-drain window)",
                "no-fault": quiet.TRACE_COMPLETENESS_RULE + " (timing key traceCompletenessRule; recorded, never blocking)",
            },
            "timingKey": "traceCompletenessRule (no-fault cells only)",
            "faultCells": decision25,
            "noFaultCells": decision56,
        },
    })
    document["analysis"] = analysis
    collection = copy.deepcopy(base["collection"])
    collection["dockerEvents"] = (
        "pause cells: docker-events.json (live docker events stream of the project's pause and unpause events, raw and "
        "parsed, with the cell's wall-to-monotonic mapping); H4"
    )
    document["collection"] = collection
    document["derivedFrom"] = {
        "authority": AUTHORITY,
        "studyEpoch": PREDECESSOR_EPOCH,
        "descriptorPath": str(path_relative(path)),
        "descriptorByteSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "descriptorCanonicalSha256": canonical_sha256(base),
        "inheritedAmendments": copy.deepcopy(base["amendments"]),
        "disposition": (
            "the sweep epoch is not superseded: it keeps its own descriptor, plan, admission history and spent "
            "attempts; the repeat epoch is a separate epoch selected by execution/study-epoch.json"
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
        raise ProtocolError("repeat descriptor must be one JSON object")
    expected = derive_repeat_descriptor()
    if canonical_json_bytes(document) != canonical_json_bytes(expected):
        raise ProtocolError("repeat descriptor differs from its generator")
    digest = canonical_sha256(document)
    if digest != EXPECTED_DESCRIPTOR_SHA256:
        raise ProtocolError(
            "repeat descriptor canonical digest differs from the reviewed pin: expected %s, found %s"
            % (EXPECTED_DESCRIPTOR_SHA256, digest)
        )
    return document


def load_descriptor(path: Path = DEFAULT_DESCRIPTOR) -> Dict[str, Any]:
    try:
        payload = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProtocolError("cannot read repeat descriptor: %s" % exc) from exc
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
        "kind": "otel-demo-repeat-episodes-compiled-plan",
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
    """The one attempt every cell of a compiled repeat plan carries."""
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
    pairs = {(regime, float(rate)) for regime in REGIMES for rate in RATES}
    for block in plan["blocks"]:
        held = sorted((cell["runKey"]["regime"], cell["runKey"]["requestsPerSecond"]) for cell in block["cells"])
        if held != sorted(pairs):
            raise ProtocolError("block %r does not hold every (regime, rate) pair exactly once" % block["block"])
    for cell in cells:
        if (cell["fault"] is None) != (cell["runKey"]["regime"] == NO_FAULT_REGIME):
            raise ProtocolError("fault/no-fault cell boundary differs")
        timing = cell["timing"]
        if (
            timing["duringFaultProbe"] is not False or timing["freezeStamps"] is not True
            or ("traceCompletenessRule" in timing) != (cell["fault"] is None)
        ):
            raise ProtocolError("a cell's H10/H4 flags or trace rule differ from the epoch's")


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
        help="write (exclusive-create) or byte-verify <root> as the repeat descriptor derived from the sweep",
    )
    parser.add_argument("--print-digests", action="store_true",
                        help="print the unpinned descriptor and attempt plan digests (for re-pinning after a change)")
    args = parser.parse_args(argv)
    if args.print_digests:
        document = derive_repeat_descriptor()
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
        frozen._install_or_verify(Path(args.root), _pretty_bytes(derive_repeat_descriptor()), "repeat descriptor")
        print(canonical_sha256(derive_repeat_descriptor()))
        return 0
    print(json.dumps(materialize(args.root, args.descriptor, args.attempt), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
