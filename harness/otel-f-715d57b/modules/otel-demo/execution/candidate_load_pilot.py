#!/usr/bin/env python3
"""Compile the OTel Demo load-pilot epoch (otel-load-pilot-v1) without executing it.

Authority: main repo research/traffic-sweep/BUDGET_D.md amendment 1 (user 2026-10-12, committed alone before the pilot
work): OTel's 0.1-core productcatalogservice CPU throttle never took effect at 0.05-10 req/s (research/placement/test-c/
DIAGNOSIS_OTEL_THROTTLE.md, aa461f8: about 1.07 ms productcatalog CPU per request, so it should start to bind near 93
req/s); the user chose higher traffic (no new fault code) and a load pilot before campaign D, first at 100 and 200 req/s,
then (user 2026-10-12, after C's frontend CPU of ~10 ms per request put 200 req/s near two cores of a one-process frontend)
at **50 and 100 req/s**, with the SUT memory limits left as in C (productcatalogservice 20 MiB, frontend 250 MiB).

What the pilot keeps from campaign C (``candidate_repeat_c.py``, otel-repeat-episodes-c-v1, read, never edited): the
posture (``full``), the route, the throttle (productcatalogservice to 0.1 core, C's scenario, onset base 60 s and hold
60 s), H10 and H4 (H4 recorded, never blocking, decision 69), the collector log sampler off (decision 66), decision 25
in fault cells and decision 56 in no-fault cells, warm-up, measurement, client timeout and every gate.  By construction:
``cell_timing`` takes C's own ``cell_timing(regime, rate, 1)`` at the pilot rate and replaces only the keys listed in
``REPLACED_TIMING_KEYS`` (plus one new key, ``generatorOpenFilesMinimum``); the descriptor is generated from C's pinned
descriptor and replaces only the keys listed in ``REPLACED_DESCRIPTOR_KEYS`` / ``REPLACED_DESCRIPTOR_SUBKEYS``.

What differs from C, and why (engineering defaults are recorded in the descriptor and the declaration draft):

* rates 50 and 100 req/s (amendment 1, user decision 2026-10-12); regimes no fault and productcatalog CPU throttle only (no frontend pause);
* 6 cells: per rate 2 throttle cells (episodes 1 and 2, the runKey's ``block``) and 1 no-fault cell (episode 1);
* run order: rate-ascending segments (every 50 req/s cell before any 100 req/s cell), a seeded Fisher-Yates order
  inside each segment.  Engineering default: the campaign stops on its first invalid cell, and 100 req/s is the rate
  most likely to break something (the frontend's ~10 ms CPU per request at r10 in C puts its single Node process near
  one core at 100 req/s), so the 50 req/s cells must not depend on a 100 req/s cell succeeding;
* concurrency ceil(2 x 100 x 15) = 3000 (the sweep's own rule, ``candidate_sweep.CONCURRENCY_MARGIN``, applied to the
  pilot's rates), and the generator's open-file soft limit must reach concurrency + 1024 before the cell starts
  (``generatorOpenFilesMinimum``; a systemd unit's default soft limit is 1024, and a socket refused for EMFILE would
  read as a failed request of the target);
* frontendproxy memory limit 512 MiB (the sweep's own rule: 0.3 MB per waiting request at rate x timeout = 1500 waiting
  requests = 450 MB, rounded up to a power of two; C has 256 MiB, sized for 300);
* budget: 450 s overhead per cell (C: 120 s; C's measured tail after the window rose ~2.2 ms per offered request from
  r0.05 to r10, so ~162 s at r100 if linear; 450 s, ~2.8x that, covers a superlinear tshark/collector-log pass), 3 h
  GATE-RUN window;
* new epoch id (in every runKey, so every run ID and host path is new), seed 20261012 (the build date, as every earlier
  epoch's), declaration path research/traffic-sweep/DECLARATION_PILOT_LOAD_OTEL.md.

The epoch is active only when the committed selector ``execution/study-epoch.json`` names it.

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
DEFAULT_DESCRIPTOR = ROOT / "pipelines/campaigns/otel-load-pilot-v1.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# C's compiler supplies the cell shape (through B's and the sweep's), the H10/H4 flags, the trace rule per cell kind, the
# draw functions, the JSON helpers and the attempt rule.  ``quiet``, ``sweep`` and ``frozen`` are the very module
# instances C loaded, so every ProtocolError is one class.
repeat_c = _load("otel_load_pilot_c_compiler", HERE / "candidate_repeat_c.py")
repeat_b = repeat_c.repeat_b
quiet = repeat_c.quiet
sweep = repeat_c.sweep
frozen = repeat_c.frozen
gates = repeat_c.gates
ProtocolError = repeat_c.ProtocolError
canonical_sha256 = repeat_c.canonical_sha256
canonical_json_bytes = repeat_c.canonical_json_bytes
strict_json_loads = repeat_c.strict_json_loads
ATTEMPT_ENVIRONMENT = repeat_c.ATTEMPT_ENVIRONMENT
DEFAULT_ATTEMPT = repeat_c.DEFAULT_ATTEMPT
campaign_attempt = repeat_c.campaign_attempt
validate_attempt = repeat_c.validate_attempt
rate_token = repeat_c.rate_token
offered_for = repeat_c.offered_for

EPOCH = "otel-load-pilot-v1"
PREDECESSOR_EPOCH = repeat_c.EPOCH                    # otel-repeat-episodes-c-v1: the cell this pilot runs at 50/100 /s
MODULE_ID = repeat_c.MODULE_ID
APPLICATION_FAMILY = repeat_c.APPLICATION_FAMILY
CHANNEL = repeat_c.CHANNEL
SCHEDULE_CONTEXT = "load-pilot-schedule-v1"
MAXIMUM_EVIDENCE_LABEL = repeat_c.MAXIMUM_EVIDENCE_LABEL

# ---------------------------------------------------------------- parameters (BUDGET_D.md amendment 1, user 2026-10-12)
POSTURES = repeat_c.POSTURES                          # ("full",)
RATES = (50.0, 100.0)                                 # requests per second, in run order (rate-ascending segments)
NO_FAULT_REGIME = repeat_c.NO_FAULT_REGIME            # "no-fault-calibration"
THROTTLE_REGIME = "productcatalog-cpu-throttle-effect"
REGIMES = (NO_FAULT_REGIME, THROTTLE_REGIME)
FAULTS = {regime: repeat_c.FAULTS[regime] for regime in REGIMES}
ARTIFACT_ROOTS = {regime: repeat_c.ARTIFACT_ROOTS[regime] for regime in REGIMES}
# Episodes per (regime, rate): the throttle twice, the no-fault cell once.  The runKey's ``block`` is the episode number,
# as in B and C (where every block held every pair once); here the episodes do not form complete blocks.
EPISODES = {THROTTLE_REGIME: 2, NO_FAULT_REGIME: 1}
ONSET_STRATA = max(EPISODES.values())                 # 2: the throttle's two onsets take the two halves of one inter-arrival
# Engineering default recorded in the declaration: the build date, as every earlier epoch's seed (sweep 20261003, quiet
# 20261004, B 20261009, C 20261011).
SCHEDULE_SEED = 20261012
ONSET_PHASE_OFFSET = repeat_c.ONSET_PHASE_OFFSET
DURING_FAULT_PROBE = repeat_c.DURING_FAULT_PROBE      # H10: False
FREEZE_STAMPS = repeat_c.FREEZE_STAMPS                # H4: True
REQUEST_TIMEOUT_SECONDS = sweep.REQUEST_TIMEOUT_SECONDS
# The sweep's open-loop rule (research/load-generator/DESIGN.md L1): the worker cap covers rate x timeout with the sweep's
# 2x margin, at the pilot's highest rate: ceil(2 x 100 x 15) = 3000 for every cell, as the sweep used its max rate for all.
CONCURRENCY = int(math.ceil(sweep.CONCURRENCY_MARGIN * max(RATES) * REQUEST_TIMEOUT_SECONDS))
# Every in-flight request holds one socket in the generator process; the controller itself holds the pcap, the logs,
# subprocess pipes and the Docker socket.  The soft RLIMIT_NOFILE of a systemd unit defaults to 1024, below the 1500
# sockets a binding throttle at 100 req/s can hold for the 15 s timeout, and an EMFILE would be recorded as a failed
# request of the target.  candidate_remote raises the soft limit to this value (never above the hard limit) before the
# cell starts, or refuses the cell.
GENERATOR_FILE_RESERVE = 1024
GENERATOR_OPEN_FILES_MINIMUM = CONCURRENCY + GENERATOR_FILE_RESERVE
# The sweep's frontendproxy rule (candidate_sweep.SERVICE_MEMORY_LIMIT_BYTES: 0.3 MB per waiting request, twice the cost
# the attempt-1 kill implies) at rate x timeout = 100 x 15 = 1500 waiting requests: 450 MB, rounded up to 512 MiB.
FRONTENDPROXY_BYTES_PER_WAITING_REQUEST = 300 * 1000
FRONTENDPROXY_MEMORY_LIMIT_BYTES = 512 * 1024 * 1024
SERVICE_MEMORY_LIMIT_BYTES = {"frontendproxy": FRONTENDPROXY_MEMORY_LIMIT_BYTES}
# Wall budget (engineering defaults).  C's measured tail after the window (request-ledger endedAtEpoch to the next
# barrier, fb14srv6, 2026-10-11) was 122-134 s at r <= 10 and rose ~4 s from r0.05 to r10 (~2.2 ms per offered request):
# ~162 s at r100 if linear.  450 s per cell (~2.8x) covers a superlinear tshark and collector-log pass over ~10x C's r10
# volume.
CELL_OVERHEAD_SECONDS = 450
TIMED_SECONDS_PER_CELL = sweep.TIMED_SECONDS_PER_CELL                # 211: warm-up 30 + barrier lead 1 + measurement 180
CELL_PERIOD_ESTIMATE_SECONDS = TIMED_SECONDS_PER_CELL + CELL_OVERHEAD_SECONDS
CELL_DEADLINE_RESERVE_SECONDS = repeat_c.CELL_DEADLINE_RESERVE_SECONDS
CLEANUP_RESERVE_SECONDS = repeat_c.CLEANUP_RESERVE_SECONDS
APPROVAL_TO_FIRST_MUTATION_SECONDS = repeat_c.APPROVAL_TO_FIRST_MUTATION_SECONDS
MEASURED_TAIL_SECONDS = {
    "source": "otel-repeat-episodes-c-v1 attempt 1 (fb14srv6, 2026-10-11), request-ledger endedAtEpoch to the next cell's barrierEpoch, 35 gaps",
    "minimum": 122.3, "maximum": 133.9, "r10Minus_r0p05Seconds": 4.0,
}
DECLARATION = (
    "research/traffic-sweep/DECLARATION_PILOT_LOAD_OTEL.md (measurement repo; frozen and committed alone before the "
    "first cell)"
)
AMENDMENTS: List[str] = []
AUTHORITY = (
    "main repo research/traffic-sweep/BUDGET_D.md amendment 1 (user 2026-10-12: higher traffic, no new fault code; a "
    "load pilot on OTel (fb14srv6) with the same throttle, fault cells plus one no-fault cell per rate, a manifestation "
    "criterion declared before launch); user decisions 2026-10-12: rates 50 and 100 req/s, SUT memory limits as in C; "
    "diagnosis research/placement/test-c/"
    "DIAGNOSIS_OTEL_THROTTLE.md (aa461f8); campaign C's decisions 25, 56, 66 and 69 carried over unchanged"
)
MANIFESTATION_CRITERION = (
    "the throttle manifests at a rate if, in both throttle cells, the median productcatalogservice GetProduct "
    "server-span duration over the hold is >= 2x its median over the pre-onset segment, and the frontend->productcatalog "
    "gRPC client span median rises too; the no-fault cell at that rate shows neither (same statistic at the same window "
    "position)"
)
# Engineering defaults that close the criterion's open wording (coordinator, 2026-10-12; recorded in the declaration).
MANIFESTATION_CRITERION_DEFAULTS = {
    "spanSelection": "by span start time; all spans regardless of status",
    "preOnsetSegment": "[onset - 60 s, onset)",
    "hold": "[onset, onset + hold)",
    "onset": "fault cells: the onset command issued (intervention.json); no-fault cell: its pseudo onset (the seeded window position, timing.scoredWindowSeconds[0])",
    "serverSpanRatio": "median productcatalogservice GetProduct server-span duration, hold / pre-onset >= 2.0",
    "clientSpanRatio": "median frontend->productcatalog gRPC client-span duration, hold / pre-onset >= 1.25 (= 'rises')",
    "noFaultCell": "same statistics at its pseudo onset; must show neither the >= 2x server-span ratio nor the >= 1.25x client-span ratio",
    "verdictPerRate": "manifests / does not manifest / '—' (fewer than 2 valid throttle cells, or an invalid no-fault cell, at that rate)",
}
# ---------------------------------------------------------------- derived

TOTAL_RUNS = sum(EPISODES[regime] for regime in REGIMES) * len(RATES)            # 6
CELLS_PER_SEGMENT = sum(EPISODES.values())                                       # 3
MINIMUM_REMAINING_SECONDS = (
    TOTAL_RUNS * CELL_PERIOD_ESTIMATE_SECONDS + CELL_DEADLINE_RESERVE_SECONDS + CLEANUP_RESERVE_SECONDS
)
RUN_WINDOW_HOURS = int(math.ceil((MINIMUM_REMAINING_SECONDS + APPROVAL_TO_FIRST_MUTATION_SECONDS) / 3600.0))
# The four timing keys that follow from the onset draw, and the four this epoch sizes itself; every other key of a cell is
# C's value for the same (regime, rate) (tested key by key).  ``generatorOpenFilesMinimum`` is new (no earlier epoch has it).
ONSET_TIMING_KEYS = repeat_c.ONSET_TIMING_KEYS
SIZED_TIMING_KEYS = frozenset({
    "concurrency", "planRunCount", "planMinimumRemainingSeconds", "serviceMemoryLimitBytes",
})
REPLACED_TIMING_KEYS = ONSET_TIMING_KEYS | SIZED_TIMING_KEYS
NEW_TIMING_KEYS = frozenset({"generatorOpenFilesMinimum"})
# The descriptor keys this epoch replaces in C's descriptor; everything else is C's, byte for byte (tested).
REPLACED_DESCRIPTOR_KEYS = frozenset({
    "id", "declaration", "amendments", "schedule", "derivedFrom", "design", "outcomes", "sutDeviations",
})
REPLACED_DESCRIPTOR_SUBKEYS = {
    "timing": frozenset({"budget", "faultOnsetStrata", "offeredByRate", "generatorOpenFilesMinimum"}),
    "workload": frozenset({"concurrency", "concurrencyRule", "requestsPerSecondLevels", "generatorOpenFiles"}),
    "analysis": frozenset({"comparativeUnit", "analysisFreeze", "manifestationCriterion", "manifestationCriterionDefaults"}),
    "collection": frozenset({"requestWitness"}),
}
EXPECTED_DESCRIPTOR_SHA256 = "45b79b0cf552b12a111ed047803ee535aabdb6d0400d05ce108e5a119a65ac46"


def onset_phase_offset(regime: str, rate: float, block: int) -> float:
    if ONSET_PHASE_OFFSET != "seeded-stratified-within-one-inter-arrival":
        raise ProtocolError("the load pilot keeps the sweep's seeded onset rule")
    if not 1 <= int(block) <= EPISODES[regime]:
        raise ProtocolError("episode %r is outside 1..%d for %s" % (block, EPISODES[regime], regime))
    return quiet.stratified_onset_offset(SCHEDULE_SEED, EPOCH, ONSET_STRATA, regime, rate, block)


def segment_cells(rate: float) -> List[Dict[str, Any]]:
    """The cells of one rate segment, (regime, episode) pairs in the regimes' declared order."""
    return [
        {"regime": regime, "rate": float(rate), "block": episode}
        for regime in REGIMES for episode in range(1, EPISODES[regime] + 1)
    ]


def segment_order(segment: int) -> List[Dict[str, Any]]:
    """Every (regime, episode) of the segment's rate once, Fisher-Yates shuffled by SHA-256 draws keyed by seed, epoch and
    segment (the quiet compiler's ``fisher_yates`` with this epoch's context; the segment number is its block argument)."""
    if not 1 <= int(segment) <= len(RATES):
        raise ProtocolError("segment %r is outside 1..%d" % (segment, len(RATES)))
    return quiet.fisher_yates(segment_cells(RATES[int(segment) - 1]), SCHEDULE_SEED, EPOCH, int(segment), SCHEDULE_CONTEXT)


def cell_label(row: Mapping[str, Any]) -> str:
    return "%s@r%s#b%d" % (row["regime"], rate_token(row["rate"]), int(row["block"]))


def cell_timing(regime: str, rate: float, block: int) -> Dict[str, Any]:
    """C's cell timing for (regime, rate) at the pilot rate, with this epoch's onset draw and the keys that follow from it
    (C's formulas), the pilot's concurrency, run count, budget and frontendproxy memory limit, and the generator's
    open-file minimum."""
    if regime not in REGIMES:
        raise ProtocolError("unknown regime %r" % (regime,))
    if float(rate) not in RATES:
        raise ProtocolError("rate %r is not a pilot rate" % (rate,))
    timing = repeat_c.cell_timing(regime, rate, 1)
    faulted = FAULTS[regime] is not None
    if timing["faultApplied"] is not faulted:
        raise ProtocolError("C's fault/no-fault cell boundary changed")
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
        "concurrency": CONCURRENCY,
        "planRunCount": TOTAL_RUNS,
        "planMinimumRemainingSeconds": MINIMUM_REMAINING_SECONDS,
        "serviceMemoryLimitBytes": dict(SERVICE_MEMORY_LIMIT_BYTES),
        "generatorOpenFilesMinimum": GENERATOR_OPEN_FILES_MINIMUM,
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
    """The design-level schedule receipt (attempt-free): per rate segment, the (regime, episode) order."""
    if POSTURES != ("full",):
        raise ProtocolError("the load pilot runs the full posture only")
    if list(RATES) != sorted(set(RATES)) or any(not (math.isfinite(rate) and rate > 0) for rate in RATES):
        raise ProtocolError("rates must be distinct, finite, positive and ascending (the run order)")
    segments = []
    for segment, rate in enumerate(RATES, start=1):
        order = [cell_label(row) for row in segment_order(segment)]
        segments.append({
            "segment": segment, "requestsPerSecond": float(rate), "order": order, "orderSha256": canonical_sha256(order),
        })
    every = [item for row in segments for item in row["order"]]
    if len(every) != TOTAL_RUNS or len(set(every)) != TOTAL_RUNS:
        raise ProtocolError("schedule does not contain every cell exactly once")
    return segments


def derive_pilot_descriptor(predecessor_path: Path = None) -> Dict[str, Any]:
    """Generate the load pilot's descriptor from campaign C's pinned descriptor.

    This function IS the descriptor's source: the checked-in otel-load-pilot-v1.json must equal ``_pretty_bytes`` of its
    result (tested), so the file is regenerated, never hand-edited.  Replaced: ``REPLACED_DESCRIPTOR_KEYS`` and
    ``REPLACED_DESCRIPTOR_SUBKEYS``; every other key is C's (faultDesign with the throttle scenario and H10/H4,
    groundTruth, the trace rules per cell kind, protocolGates, containerHealthGuard, workflow, ...).
    """
    path = Path(predecessor_path) if predecessor_path is not None else repeat_c.DEFAULT_DESCRIPTOR
    base = repeat_c.load_descriptor(path)
    if base["id"] != PREDECESSOR_EPOCH:
        raise ProtocolError("the load pilot is derived from campaign C's descriptor only")
    document = copy.deepcopy(base)
    document["id"] = EPOCH
    document["declaration"] = DECLARATION
    document["amendments"] = list(AMENDMENTS)
    design = copy.deepcopy(base["design"])
    for key in ("blockRule", "blocks", "cellsPerBlock"):
        design.pop(key)
    design.update({
        "purpose": (
            "load pilot (BUDGET_D.md amendment 1): does campaign C's 0.1-core productcatalogservice throttle take effect "
            "at 50 and 100 req/s, where its CPU demand (~1.07 ms per request in C) reaches the cap; decides whether "
            "and at which rates campaign D runs"
        ),
        "rates": list(RATES),
        "regimes": [row for row in base["design"]["regimes"] if row["id"] in REGIMES],
        "omittedRegimes": dict(base["design"]["omittedRegimes"], **{
            "frontend-pause-effect": "not part of the pilot: the question is whether the throttle binds (amendment 1)",
        }),
        "episodesPerRegimeAndRate": dict(EPISODES),
        "segments": len(RATES),
        "cellsPerSegment": CELLS_PER_SEGMENT,
        "segmentRule": (
            "one segment per rate, rate-ascending (every 50 req/s cell runs before any 100 req/s cell); each segment "
            "holds the throttle twice (episodes 1 and 2) and the no-fault cell once (episode 1), in a seeded order; the "
            "runKey's block is the episode"
        ),
        "segmentOrderRationale": (
            "engineering default: the campaign stops on its first invalid cell, and 100 req/s is the rate most likely to "
            "break the harness or the SUT, so no 50 req/s cell depends on a 100 req/s cell"
        ),
        "totalRuns": TOTAL_RUNS,
        "cellShape": (
            "campaign C's cell (candidate_repeat_c.cell_timing(regime, rate, 1)) at the pilot rate; only the seeded "
            "onset (2 strata), the slots per phase it implies, the concurrency, the plan-level run count and minimum "
            "remaining time, the frontendproxy memory limit and the generator's open-file minimum differ"
        ),
    })
    document["design"] = design
    document["schedule"] = {
        "version": SCHEDULE_CONTEXT,
        "seed": SCHEDULE_SEED,
        "shuffle": "fisher-yates-over-(regime,episode)-within-each-rate-segment-with-sha256-draws",
        "drawEncoding": "UTF-8(seed || NUL || epoch || NUL || block-NN (NN = segment number) || NUL || draw-i || NUL || version)",
        "segmentOrder": "rate-ascending",
        "leadCell": None,
        "segments": allocate_schedule(),
    }
    timing = copy.deepcopy(base["timing"])
    timing["faultOnsetStrata"] = ONSET_STRATA
    timing["offeredByRate"] = {rate_token(rate): offered_for(rate, timing["measurementSeconds"]) for rate in RATES}
    timing["generatorOpenFilesMinimum"] = GENERATOR_OPEN_FILES_MINIMUM
    timing["budget"].update({
        "cellOverheadSeconds": CELL_OVERHEAD_SECONDS,
        "cellPeriodEstimateSeconds": CELL_PERIOD_ESTIMATE_SECONDS,
        "minimumRemainingSeconds": MINIMUM_REMAINING_SECONDS,
        "runWindowHours": RUN_WINDOW_HOURS,
        "measuredTailSeconds": copy.deepcopy(MEASURED_TAIL_SECONDS),
    })
    document["timing"] = timing
    workload = copy.deepcopy(base["workload"])
    workload.update({
        "concurrency": CONCURRENCY,
        "concurrencyRule": (
            "ceil(2 x max rate x request timeout) = ceil(2 x 100 x 15): the worker cap covers rate x timeout with the "
            "sweep's 2x margin; one thread per in-flight or scheduled-ahead request"
        ),
        "requestsPerSecondLevels": list(RATES),
        "generatorOpenFiles": (
            "the controller raises its RLIMIT_NOFILE soft limit to concurrency + %d = %d (never above the hard limit) "
            "before the cell starts, or refuses the cell: every in-flight request holds a socket, and an EMFILE would read "
            "as a failed request of the target" % (GENERATOR_FILE_RESERVE, GENERATOR_OPEN_FILES_MINIMUM)
        ),
    })
    document["workload"] = workload
    collection = copy.deepcopy(base["collection"])
    collection["requestWitness"] = (
        "frontendproxy JSON access log, unchanged; its json-file log is one unrotated segment bounded at 4g (the "
        "collector carrier's rule), because upstream's 5m x 2 keeps between 5 and 10 MB and one access-log line is "
        "~0.4 kB on disk (estimated), so the 18,300 requests of a 100 req/s cell (~7.3 MB) keep only a ~27 % margin below "
        "upstream's bound, which a 0.55 kB line would exceed; a lost line fails the terminal's witness check"
    )
    document["collection"] = collection
    deviations = []
    for row in base["sutDeviations"]:
        row = copy.deepcopy(row)
        if row["service"] == "frontendproxy" and row["setting"] == "memory limit (HostConfig.Memory)":
            row["pilot"] = "%d bytes (512 MiB)" % FRONTENDPROXY_MEMORY_LIMIT_BYTES
            row["pilotRule"] = (
                "the sweep's rule (0.3 MB per waiting request, twice the cost the attempt-1 kill implies) at rate x "
                "timeout = 100 x 15 = 1500 waiting requests = 450 MB, rounded up to 512 MiB"
            )
            row["scope"] = "the load pilot's cells; C's epoch and every frozen epoch keep their limit"
        deviations.append(row)
    deviations.append({
        "service": "frontendproxy",
        "setting": "json-file log rotation",
        "upstream": "max-size 5m, max-file 2 (x-default-logging)",
        "pilot": "max-size 4g, max-file 1 (the collector carrier's rule, compose.otel-placement.yml)",
        "mechanism": "materialize.py renders it into the materialized compose.otel-placement.yml when the selector names the pilot",
        "reason": (
            "the request witness is the frontendproxy access log; at 100 req/s a cell writes ~7.3 MB of it (estimated), "
            "within ~27 % of upstream's 10 MB loss bound"
        ),
        "scope": "the load pilot's materialized source only; every other epoch renders the overlay byte for byte",
    })
    document["sutDeviations"] = deviations
    document["outcomes"] = {
        "primary": "per rate: whether the throttle manifests by the declared criterion (analysis.manifestationCriterion)",
        "secondary": (
            "per cell: request outcomes and latency over pre-onset, hold and post-revert; productcatalogservice CPU; "
            "the frontend's CPU (whether 50 or 100 req/s saturates the route without a fault)"
        ),
        "costRegimeOnly": None,
        "offeredRequestsAreDenominator": True,
        "windowMembership": "monotonic-shared-barrier",
    }
    analysis = copy.deepcopy(base["analysis"])
    analysis.update({
        "comparativeUnit": "rate; 2 throttle episodes and 1 no-fault cell per rate, read by the manifestation criterion only",
        "analysisFreeze": (
            "exploratory pilot: no placement is scored on these cells; the manifestation criterion is declared before "
            "launch (BUDGET_D.md amendment 1) and applied once"
        ),
        "manifestationCriterion": MANIFESTATION_CRITERION,
        "manifestationCriterionDefaults": copy.deepcopy(MANIFESTATION_CRITERION_DEFAULTS),
    })
    document["analysis"] = analysis
    document["derivedFrom"] = {
        "authority": AUTHORITY,
        "studyEpoch": PREDECESSOR_EPOCH,
        "descriptorPath": str(path_relative(path)),
        "descriptorByteSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "descriptorCanonicalSha256": canonical_sha256(base),
        "inheritedAmendments": copy.deepcopy(base["amendments"]),
        "predecessorDerivedFrom": copy.deepcopy(base["derivedFrom"]),
        "disposition": (
            "campaign C's epoch is not superseded: it keeps its own descriptor, plan, admission history and spent "
            "attempts; the load pilot is a separate epoch selected by execution/study-epoch.json"
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
        raise ProtocolError("load pilot descriptor must be one JSON object")
    expected = derive_pilot_descriptor()
    if canonical_json_bytes(document) != canonical_json_bytes(expected):
        raise ProtocolError("load pilot descriptor differs from its generator")
    digest = canonical_sha256(document)
    if digest != EXPECTED_DESCRIPTOR_SHA256:
        raise ProtocolError(
            "load pilot descriptor canonical digest differs from the reviewed pin: expected %s, found %s"
            % (EXPECTED_DESCRIPTOR_SHA256, digest)
        )
    return document


def load_descriptor(path: Path = DEFAULT_DESCRIPTOR) -> Dict[str, Any]:
    try:
        payload = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProtocolError("cannot read load pilot descriptor: %s" % exc) from exc
    return copy.deepcopy(validate_descriptor(strict_json_loads(payload)))


def _compile(document: Mapping[str, Any], attempt: int) -> Dict[str, Any]:
    """B's plan layout, with one entry per rate segment under ``blocks`` (the runtime runs the cells in that order)."""
    attempt = validate_attempt(attempt)
    segments = []
    run_ids: List[str] = []
    position = 0
    for receipt in document["schedule"]["segments"]:
        number = receipt["segment"]
        cells = []
        for index, row in enumerate(segment_order(number)):
            regime, rate, episode, posture = row["regime"], row["rate"], row["block"], POSTURES[0]
            if cell_label(row) != receipt["order"][index] or float(rate) != receipt["requestsPerSecond"]:
                raise ProtocolError("compiled order differs from the descriptor's schedule receipt")
            position += 1
            key = run_key_for(regime, rate, episode, posture, attempt)
            run_id = run_id_for(key)
            run_ids.append(run_id)
            cells.append({
                "runKey": key,
                "runId": run_id,
                "ordinalPosition": position,
                "artifactRoot": "runs/%s/r%s-b%02d-%02d-%s" % (
                    ARTIFACT_ROOTS[regime], rate_token(rate), episode, position, posture),
                "realizationStatus": document["postureRealization"][posture]["status"],
                "fault": FAULTS[regime],
                "timing": cell_timing(regime, rate, episode),
            })
        segments.append({
            "segment": number, "requestsPerSecond": float(receipt["requestsPerSecond"]),
            "order": [cell["runId"] for cell in cells], "cells": cells,
        })
    return {
        "schemaVersion": 1,
        "kind": "otel-demo-load-pilot-compiled-plan",
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
            "segmentOrders": [
                {"segment": row["segment"], "requestsPerSecond": row["requestsPerSecond"], "order": list(row["order"]),
                 "orderSha256": row["orderSha256"]}
                for row in document["schedule"]["segments"]
            ],
        },
        "blocks": segments,
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
    """The one attempt every cell of a compiled load-pilot plan carries."""
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
    if [segment["requestsPerSecond"] for segment in plan["blocks"]] != list(RATES):
        raise ProtocolError("compiled plan segments are not the rates in ascending order")
    if [cell["ordinalPosition"] for cell in cells] != list(range(1, TOTAL_RUNS + 1)):
        raise ProtocolError("compiled plan ordinal positions are not 1..%d in run order" % TOTAL_RUNS)
    for segment in plan["blocks"]:
        held = sorted(
            (cell["runKey"]["regime"], cell["runKey"]["requestsPerSecond"], cell["runKey"]["block"])
            for cell in segment["cells"]
        )
        if held != sorted((row["regime"], row["rate"], row["block"]) for row in segment_cells(segment["requestsPerSecond"])):
            raise ProtocolError("segment %r does not hold every (regime, episode) of its rate exactly once" % segment["segment"])
    for cell in cells:
        if (cell["fault"] is None) != (cell["runKey"]["regime"] == NO_FAULT_REGIME):
            raise ProtocolError("fault/no-fault cell boundary differs")
        timing = cell["timing"]
        if (
            timing["duringFaultProbe"] is not False or timing["freezeStamps"] is not True
            or ("traceCompletenessRule" in timing) != (cell["fault"] is None)
            or timing["concurrency"] < timing["requestsPerSecond"] * timing["requestTimeoutSeconds"]
            or timing["generatorOpenFilesMinimum"] < timing["concurrency"]
        ):
            raise ProtocolError("a cell's H10/H4 flags, trace rule or generator sizing differ from the epoch's")


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
        help="write (exclusive-create) or byte-verify <root> as the load pilot descriptor derived from campaign C's",
    )
    parser.add_argument("--print-digests", action="store_true",
                        help="print the unpinned descriptor and attempt plan digests (for re-pinning after a change)")
    args = parser.parse_args(argv)
    if args.print_digests:
        document = derive_pilot_descriptor()
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
        frozen._install_or_verify(Path(args.root), _pretty_bytes(derive_pilot_descriptor()), "load pilot descriptor")
        print(canonical_sha256(derive_pilot_descriptor()))
        return 0
    print(json.dumps(materialize(args.root, args.descriptor, args.attempt), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
