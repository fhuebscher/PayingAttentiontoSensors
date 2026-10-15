#!/usr/bin/env python3
"""Compile the OTel Demo campaign-C epoch (otel-repeat-episodes-c-v1) without executing it.

Campaign C is a clean placement test run (main repo research/PROTOCOL_DRAFT_20261002.md decision 82, user 2026-10-10;
budget and stop rule research/traffic-sweep/BUDGET_C.md, d5b9af0, committed alone before any C work): **campaign B's
shape exactly** -- 3 blocks x 3 regimes x 4 rates = 36 cells, H10 and H4 as in B (H4 recorded, never blocking, decision
69), the collector log sampler off (decision 66), decision 25 in fault cells and decision 56 in no-fault cells -- with
new blocks and run IDs under a new study epoch.  Nothing else changes.  Its fault cells are read only through the frozen
placement (BUDGET_PLACEMENT.md step 6); its no-fault cells are a second fresh false-alarm check, never pooled into a
calibration.

B's compiler (``candidate_repeat.py``, otel-repeat-episodes-v1, attempt 1 ran 2026-10-09) is read, never edited, and is
this file's only source of cell shape: ``cell_timing`` takes B's own ``cell_timing(regime, rate, block)`` and replaces
only the four keys that follow from this epoch's onset draw; the descriptor is generated from B's pinned descriptor
(loaded through B's digest check) and replaces only this epoch's identity, schedule, purpose, outcome and analysis-freeze
text and the derivation record.  What differs from B, and nothing else:

* the epoch id (in every runKey, so every run ID, artifact root and host path is new);
* the schedule seed (20261011, the date this epoch was built; B used 20261009), which with the new epoch id gives new
  block orders and new seeded onsets through the same draw functions (the quiet compiler's ``fisher_yates`` and
  ``stratified_onset_offset``, B's schedule context ``repeat-schedule-v1``);
* the declaration path (research/traffic-sweep/DECLARATION_C_OTEL.md).

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
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping


HERE = Path(__file__).resolve().parent
MODULE = HERE.parent
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DESCRIPTOR = ROOT / "pipelines/campaigns/otel-repeat-episodes-c-v1.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# B's compiler supplies the cell shape, the budget, the H10/H4 flags, the scenarios and (through the quiet and sweep
# compilers it loads) the draw functions, the trace rule, the JSON helpers and the attempt rule.  ``quiet`` and ``sweep``
# are the very module instances B loaded, so every ProtocolError is one class.
repeat_b = _load("otel_repeat_c_b_compiler", HERE / "candidate_repeat.py")
quiet = repeat_b.quiet
sweep = repeat_b.sweep
frozen = repeat_b.frozen
gates = repeat_b.gates
ProtocolError = repeat_b.ProtocolError
canonical_sha256 = repeat_b.canonical_sha256
canonical_json_bytes = repeat_b.canonical_json_bytes
strict_json_loads = repeat_b.strict_json_loads
ATTEMPT_ENVIRONMENT = repeat_b.ATTEMPT_ENVIRONMENT
DEFAULT_ATTEMPT = repeat_b.DEFAULT_ATTEMPT
campaign_attempt = repeat_b.campaign_attempt
validate_attempt = repeat_b.validate_attempt
rate_token = repeat_b.rate_token
offered_for = repeat_b.offered_for

EPOCH = "otel-repeat-episodes-c-v1"
PREDECESSOR_EPOCH = repeat_b.EPOCH                    # otel-repeat-episodes-v1: the shape this epoch repeats exactly
MODULE_ID = repeat_b.MODULE_ID
APPLICATION_FAMILY = repeat_b.APPLICATION_FAMILY
CHANNEL = repeat_b.CHANNEL
SCHEDULE_CONTEXT = repeat_b.SCHEDULE_CONTEXT          # "repeat-schedule-v1": B's draw encoding
MAXIMUM_EVIDENCE_LABEL = repeat_b.MAXIMUM_EVIDENCE_LABEL

# ---------------------------------------------------------------- parameters: B's, except the seed (decision 82)
POSTURES = repeat_b.POSTURES
RATES = repeat_b.RATES
REGIMES = repeat_b.REGIMES
FAULTS = dict(repeat_b.FAULTS)
ARTIFACT_ROOTS = dict(repeat_b.ARTIFACT_ROOTS)
NO_FAULT_REGIME = repeat_b.NO_FAULT_REGIME
BLOCKS = repeat_b.BLOCKS                              # 3
# Engineering default recorded in the declaration: the build date, as every earlier epoch's seed (sweep 20261003, quiet
# 20261004, B 20261009).  With the new epoch id alone the draws would already differ; the new seed makes it explicit.
SCHEDULE_SEED = 20261011
ONSET_PHASE_OFFSET = repeat_b.ONSET_PHASE_OFFSET
DURING_FAULT_PROBE = repeat_b.DURING_FAULT_PROBE      # H10: False
FREEZE_STAMPS = repeat_b.FREEZE_STAMPS                # H4: True
ENTRY_ROUTE_DURING_FAULT = repeat_b.ENTRY_ROUTE_DURING_FAULT
SCENARIOS = copy.deepcopy(repeat_b.SCENARIOS)
CELL_PERIOD_ESTIMATE_SECONDS = repeat_b.CELL_PERIOD_ESTIMATE_SECONDS
CELL_DEADLINE_RESERVE_SECONDS = repeat_b.CELL_DEADLINE_RESERVE_SECONDS
CLEANUP_RESERVE_SECONDS = repeat_b.CLEANUP_RESERVE_SECONDS
APPROVAL_TO_FIRST_MUTATION_SECONDS = repeat_b.APPROVAL_TO_FIRST_MUTATION_SECONDS
TOTAL_RUNS = repeat_b.TOTAL_RUNS                      # 36
CELLS_PER_BLOCK = repeat_b.CELLS_PER_BLOCK
MINIMUM_REMAINING_SECONDS = repeat_b.MINIMUM_REMAINING_SECONDS   # 13,416 s
RUN_WINDOW_HOURS = repeat_b.RUN_WINDOW_HOURS          # 5
OWN_TIMING_KEYS = repeat_b.OWN_TIMING_KEYS
NO_FAULT_ONLY_TIMING_KEYS = repeat_b.NO_FAULT_ONLY_TIMING_KEYS
DECLARATION = (
    "research/traffic-sweep/DECLARATION_C_OTEL.md (measurement repo; frozen and committed alone before the first cell)"
)
AMENDMENTS: List[str] = []
AUTHORITY = (
    "main repo research/PROTOCOL_DRAFT_20261002.md decision 82 (user 2026-10-10: clean placement test runs, campaign C "
    "on TeaStore and OTel with campaign B's 36-cell shape and new blocks, after the placement design is frozen by digest; "
    "fault cells scored only by the frozen placement); budget and stop rule research/traffic-sweep/BUDGET_C.md (d5b9af0, "
    "committed alone before any C work); B's decisions 49, 50, 56, 66 and 69 carried over unchanged"
)
# The four timing keys that follow from the onset draw; every other key of a cell is B's value for the same
# (regime, rate, block) (tested key by key).
ONSET_TIMING_KEYS = frozenset({
    "faultOnsetPhaseOffsetSeconds", "faultOnsetSeconds", "scoredWindowSeconds", "scheduledSlotsByPhase",
})
# The descriptor keys this epoch replaces in B's descriptor; everything else is B's, byte for byte (tested).
REPLACED_DESCRIPTOR_KEYS = frozenset({"id", "declaration", "amendments", "schedule", "derivedFrom"})
REPLACED_DESCRIPTOR_SUBKEYS = {
    "design": frozenset({"purpose"}),
    "outcomes": frozenset({"primary"}),
    "analysis": frozenset({"comparativeUnit", "analysisFreeze"}),
}
# ---------------------------------------------------------------- derived

EXPECTED_DESCRIPTOR_SHA256 = "6dd3cb7215db438cdf2f0618dd62eed583b86004f5f0254c565eabe93cc13721"


def onset_phase_offset(regime: str, rate: float, block: int) -> float:
    if ONSET_PHASE_OFFSET != "seeded-stratified-within-one-inter-arrival":
        raise ProtocolError("campaign C keeps the sweep's seeded onset rule")
    return quiet.stratified_onset_offset(SCHEDULE_SEED, EPOCH, BLOCKS, regime, rate, block)


def block_order(block: int) -> List[Dict[str, Any]]:
    """Every (regime, rate) pair once in this block, Fisher-Yates shuffled by SHA-256 draws keyed by this epoch's seed,
    epoch and block (B's rule, draw encoding and context); no lead cell."""
    if not 1 <= int(block) <= BLOCKS:
        raise ProtocolError("block %r is outside 1..%d" % (block, BLOCKS))
    return quiet.fisher_yates(
        [{"regime": regime, "rate": float(rate)} for regime in REGIMES for rate in RATES],
        SCHEDULE_SEED, EPOCH, int(block), SCHEDULE_CONTEXT,
    )


def cell_timing(regime: str, rate: float, block: int) -> Dict[str, Any]:
    """B's cell timing for the same (regime, rate, block) with this epoch's onset draw and the keys that follow from it
    (B's formulas): the onset and its phase offset, the scored window and, in fault cells, the slots per phase."""
    if regime not in REGIMES:
        raise ProtocolError("unknown regime %r" % (regime,))
    timing = repeat_b.cell_timing(regime, rate, block)
    faulted = FAULTS[regime] is not None
    if timing["faultApplied"] is not faulted:
        raise ProtocolError("B's fault/no-fault cell boundary changed")
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
    })
    return timing


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
        raise ProtocolError("campaign C runs the full posture only")
    blocks = []
    for block in range(1, BLOCKS + 1):
        order = ["%s@r%s" % (row["regime"], rate_token(row["rate"])) for row in block_order(block)]
        blocks.append({"block": block, "order": order, "orderSha256": canonical_sha256(order)})
    every = [(row["block"], item) for row in blocks for item in row["order"]]
    if len(every) != TOTAL_RUNS or len(set(every)) != TOTAL_RUNS:
        raise ProtocolError("schedule does not contain every cell exactly once")
    return blocks


def derive_c_descriptor(predecessor_path: Path = None) -> Dict[str, Any]:
    """Generate campaign C's descriptor from B's pinned descriptor.

    This function IS the descriptor's source: the checked-in otel-repeat-episodes-c-v1.json must equal ``_pretty_bytes``
    of its result (tested), so the file is regenerated, never hand-edited.  Replaced: ``REPLACED_DESCRIPTOR_KEYS`` and
    ``REPLACED_DESCRIPTOR_SUBKEYS``; every other key is B's (timing and budget, faultDesign with H10/H4, groundTruth,
    collection, analysis.traceCompleteness per cell kind, workflow, protocolGates, ...).
    """
    path = Path(predecessor_path) if predecessor_path is not None else repeat_b.DEFAULT_DESCRIPTOR
    base = repeat_b.load_descriptor(path)
    if base["id"] != PREDECESSOR_EPOCH:
        raise ProtocolError("campaign C is derived from campaign B's descriptor only")
    document = copy.deepcopy(base)
    document["id"] = EPOCH
    document["declaration"] = DECLARATION
    document["amendments"] = list(AMENDMENTS)
    document["design"]["purpose"] = (
        "clean placement test run (campaign C, decision 82): campaign B's 36 cells (3 blocks of the traffic sweep's 12 "
        "(regime, rate) cells, H10 and H4, collector log sampler off) with new blocks and run IDs; fault cells are "
        "scored only by the frozen placement, no-fault cells are a second fresh false-alarm check"
    )
    document["schedule"] = {
        "version": SCHEDULE_CONTEXT,
        "seed": SCHEDULE_SEED,
        "shuffle": base["schedule"]["shuffle"],
        "drawEncoding": base["schedule"]["drawEncoding"],
        "leadCell": None,
        "blocks": allocate_schedule(),
    }
    document["outcomes"]["primary"] = (
        "per (fault, rate): detection and time to detection of the frozen placement (BUDGET_PLACEMENT.md step 6), "
        "never used to tune it; no-fault cells: false alarms of the frozen detectors (decision 82, BUDGET_C.md)"
    )
    document["analysis"]["comparativeUnit"] = (
        "(fault, rate); 3 episodes per pair, scored by the frozen placement and never pooled into a calibration"
    )
    document["analysis"]["analysisFreeze"] = (
        "no C cell is read (validity fields only) before the placement is frozen (BUDGET_C.md stop rule 4); fault cells "
        "are then read only through the frozen placement"
    )
    document["derivedFrom"] = {
        "authority": AUTHORITY,
        "studyEpoch": PREDECESSOR_EPOCH,
        "descriptorPath": str(path_relative(path)),
        "descriptorByteSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "descriptorCanonicalSha256": canonical_sha256(base),
        "inheritedAmendments": copy.deepcopy(base["amendments"]),
        "predecessorDerivedFrom": copy.deepcopy(base["derivedFrom"]),
        "disposition": (
            "campaign B's epoch is not superseded: it keeps its own descriptor, plan, admission history and spent "
            "attempts; campaign C is a separate epoch selected by execution/study-epoch.json"
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
        raise ProtocolError("campaign C descriptor must be one JSON object")
    expected = derive_c_descriptor()
    if canonical_json_bytes(document) != canonical_json_bytes(expected):
        raise ProtocolError("campaign C descriptor differs from its generator")
    digest = canonical_sha256(document)
    if digest != EXPECTED_DESCRIPTOR_SHA256:
        raise ProtocolError(
            "campaign C descriptor canonical digest differs from the reviewed pin: expected %s, found %s"
            % (EXPECTED_DESCRIPTOR_SHA256, digest)
        )
    return document


def load_descriptor(path: Path = DEFAULT_DESCRIPTOR) -> Dict[str, Any]:
    try:
        payload = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProtocolError("cannot read campaign C descriptor: %s" % exc) from exc
    return copy.deepcopy(validate_descriptor(strict_json_loads(payload)))


def _compile(document: Mapping[str, Any], attempt: int) -> Dict[str, Any]:
    """B's plan layout (``repeat_b._compile``), with this epoch's orders, run keys and timings."""
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
    """The one attempt every cell of a compiled campaign-C plan carries."""
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
        help="write (exclusive-create) or byte-verify <root> as the campaign C descriptor derived from campaign B's",
    )
    parser.add_argument("--print-digests", action="store_true",
                        help="print the unpinned descriptor and attempt plan digests (for re-pinning after a change)")
    args = parser.parse_args(argv)
    if args.print_digests:
        document = derive_c_descriptor()
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
        frozen._install_or_verify(Path(args.root), _pretty_bytes(derive_c_descriptor()), "campaign C descriptor")
        print(canonical_sha256(derive_c_descriptor()))
        return 0
    print(json.dumps(materialize(args.root, args.descriptor, args.attempt), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
