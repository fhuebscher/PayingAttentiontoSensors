#!/usr/bin/env python3
"""Compile the OTel Demo traffic-sweep epoch (otel-traffic-sweep-v1) without executing it.

A second epoch beside the frozen ``candidate_pilot.py`` (otel-demo-offpath-v1, descriptor 1491657d..., attempt-1
plan 168699c4...), which this file never changes and only reads.  It replicates the Hotel traffic sweep
(main repo research/traffic-sweep/DECLARATION.md, frozen 2026-10-03; OTel declaration
research/traffic-sweep/DECLARATION_OTEL.md, frozen 2026-10-03): one route through the entry point at four request rates, a
fault at a seeded onset, posture ``full`` only, one block.  Request rate, measurement length, onset, hold and the
offered count are per-cell plan values: every compiled cell carries a ``timing`` block, and the target
controller, the runtime and the terminal validator read the cell's timing instead of the frozen epoch's
literals.  Every value under "parameters" is the frozen declaration's (user 2026-10-03: "accept all, M1 99 %");
changing one changes the descriptor and plan digests, by design.

The epoch is active only when the committed selector ``execution/study-epoch.json`` names it
(``candidate_runtime.EPOCH_SELECTOR``); without the selector the runtime is the frozen epoch, byte for byte.

Construction only: no Docker, SSH, subprocess, socket or transport surface.  Runs as ``python3 -I`` on
CPython 3.9 on the target (the runtime imports it there): standard library only, sibling files are loaded by
path (``-I`` drops this directory from ``sys.path``), no PEP 604 annotation evaluated at runtime.
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
DEFAULT_DESCRIPTOR = ROOT / "pipelines/campaigns/otel-traffic-sweep-v1.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The frozen compiler supplies the JSON helpers, the attempt rule and the offpath descriptor this epoch is derived
# from; it is read, never edited.  The vendored protocol gates supply need() and the gate thresholds, so the
# compile-time phase check below is the gates' own rule, not a second copy of it.
frozen = _load("otel_sweep_frozen_compiler", HERE / "candidate_pilot.py")
gates = _load("otel_sweep_protocol_gates", MODULE / "validation" / "protocol_gates.py")
ProtocolError = frozen.ProtocolError
canonical_sha256 = frozen.canonical_sha256
canonical_json_bytes = frozen.canonical_json_bytes
strict_json_loads = frozen.strict_json_loads
ATTEMPT_ENVIRONMENT = frozen.ATTEMPT_ENVIRONMENT
DEFAULT_ATTEMPT = frozen.DEFAULT_ATTEMPT
campaign_attempt = frozen.campaign_attempt
validate_attempt = frozen.validate_attempt

EPOCH = "otel-traffic-sweep-v1"
PREDECESSOR_EPOCH = frozen.EPOCH                       # otel-demo-offpath-v1: the descriptor this one derives from
MODULE_ID = frozen.MODULE
APPLICATION_FAMILY = frozen.APPLICATION_FAMILY
CHANNEL = frozen.CHANNEL
SCHEDULE_CONTEXT = "sweep-schedule-v1"
DESIGN_LABEL = frozen.DESIGN_LABEL
MAXIMUM_EVIDENCE_LABEL = frozen.MAXIMUM_EVIDENCE_LABEL

# ---------------------------------------------------------------- parameters (frozen declaration, 2026-10-03)
POSTURES = ("full",)
RATES = (10.0, 1.0, 0.2, 0.05)                 # requests per second; inter-arrival 0.1, 1, 5, 20 s
# One route through the entry point that reaches the frontend and one backend (upstream 2d4661e code reading:
# src/frontend/pages/api/products/[productId]/index.ts -> services/ProductCatalog.service.ts getProduct ->
# ProductCatalogGateway.getProduct; no currency call without a currencyCode).  The product is NOT OLJCESPC7Z:
# productcatalogservice asks flagd (productCatalogFailure) for that one product only (main.go checkProductFailure),
# so any other product keeps flagd off the route.  66VCHSJNUP is the catalog's second product.
ROUTE_METHOD = "GET"
ROUTE_PRODUCT_ID = "66VCHSJNUP"
ROUTE_PATH = "/api/products/" + ROUTE_PRODUCT_ID
ROUTE_SERVICES = ("frontendproxy", "frontend", "productcatalogservice")   # traversal order
ROUTE_DERIVATION = [
    "frontendproxy -> frontend: Envoy routes /api/* to the Next.js frontend (src/frontendproxy/envoy.tmpl.yaml)",
    "frontend: src/frontend/pages/api/products/[productId]/index.ts GET -> ProductCatalogService.getProduct "
    "(services/ProductCatalog.service.ts) -> ProductCatalogGateway.getProduct (productcatalogservice gRPC); "
    "CurrencyGateway.convert only when currencyCode is set and not USD (none is sent)",
    "productcatalogservice: src/productcatalogservice/main.go GetProduct; checkProductFailure asks flagd only "
    "for id OLJCESPC7Z, so the route product 66VCHSJNUP keeps flagd off the route",
]
WARMUP_SECONDS = 30
WARMUP_REQUESTS_PER_SECOND = 10.0              # every cell warms up at 10/s (Hotel decision, user 2026-10-03)
MEASUREMENT_SECONDS = 180
FAULT_ONSET_BASE_SECONDS = 60                  # the seeded phase offset below is added per cell
FAULT_HOLD_SECONDS = 60
# Hotel's onset_phase_offset, copied: 60 s is a multiple of every planned inter-arrival, so without an offset every
# onset falls on a scheduled request.  The EPISODES blocks of one (regime, rate) pair take the EPISODES strata of
# one inter-arrival in a seeded order, uniform inside the stratum; with one block that is one seeded uniform
# draw over the whole inter-arrival.  Keyed by (regime, rate, block), never by attempt, so a relaunch under a
# new attempt keeps the design.
ONSET_PHASE_OFFSET = "seeded-stratified-within-one-inter-arrival"
ONSET_PHASE_OFFSETS = ("seeded-stratified-within-one-inter-arrival", "none")
# The lead cell is fixed (Hotel decision): the 60 s pause at 10/s goes first so its capture can be checked while
# the campaign runs; the rest of block 1 keeps its seeded shuffle.
LEAD_CELL = ("frontend-pause-effect", 10.0)
# The harness's per-request client timeout: the offpath journey's stepTimeoutSeconds (descriptor workload).
REQUEST_TIMEOUT_SECONDS = 15.0
# Open-loop rule (research/load-generator/DESIGN.md L1, which Hotel's 16 >= 10/s x 1 s met with a 1.6x margin): the
# worker cap must cover rate x timeout, or a stalled target (a paused frontend holds every request for the full
# timeout) stalls the generator's starts.  Derived with a 2x margin, not the offpath 32: 2 x 10/s x 15 s = 300.
CONCURRENCY_MARGIN = 2
CONCURRENCY = int(math.ceil(CONCURRENCY_MARGIN * max(RATES) * REQUEST_TIMEOUT_SECONDS))
EPISODES = 1                                   # one block: every (regime, rate) pair exactly once
SCHEDULE_SEED = 20261003
REGIMES = (
    "no-fault-calibration",
    "frontend-pause-effect",
    "productcatalog-cpu-throttle-effect",
)
FAULTS = {
    "no-fault-calibration": None,
    "frontend-pause-effect": "frontend-pause",
    "productcatalog-cpu-throttle-effect": "productcatalog-cpu-throttle",
}
ARTIFACT_ROOTS = {
    "no-fault-calibration": "calibration",
    "frontend-pause-effect": "effect/frontend-pause",
    "productcatalog-cpu-throttle-effect": "effect/productcatalog-cpu-throttle",
}
# docker update --cpus is a docker-API call (docker group, no sudo).  0.1 CPU is Hotel's profile-cpu-throttle.
CPU_THROTTLE_CPUS = "0.1"
CPU_THROTTLE_NANOCPUS = 100_000_000
SCENARIOS: Dict[str, Dict[str, Any]] = {
    "frontend-pause": {
        "service": "frontend", "action": "pause",
        "applyCommand": "docker compose pause frontend", "revertCommand": "docker compose unpause frontend",
        "duringPredicate": "running-and-paused",
        "entryRouteDuringFault": "must-be-unavailable",
    },
    "productcatalog-cpu-throttle": {
        "service": "productcatalogservice", "action": "cpu-throttle",
        "cpus": CPU_THROTTLE_CPUS, "nanoCpus": CPU_THROTTLE_NANOCPUS,
        "applyCommand": "docker update --cpus 0.1 <container>",
        "revertCommand": (
            "docker update --cpus <original> <container>; an unset original (NanoCpus 0) is lifted to every host "
            "CPU instead, because docker update --cpus 0 is a no-op (measured on fb14srv4 2026-09-28, Hotel "
            "lmt_faults.py); the container is removed at the end of the cell"
        ),
        "duringPredicate": "running-and-nanocpus-equal-the-throttle",
        "entryRouteDuringFault": "recorded-not-required",
    },
}
OMITTED_REGIMES = {
    "net-delay": (
        "no no-sudo mechanism exists in this harness: fb14srv6 grants sudo only for tcpdump, the only netem "
        "mechanism the project has is `sudo -n nsenter -t <pid> -n tc` (Hotel faults/lmt_faults.py), and the "
        "docker-sidecar netem of decision round 4 item 6 is not built (it would also need an image with iproute2 "
        "pinned on the host)"
    ),
}
UPSTREAM_GENERATORS_OFF = ("loadgenerator",)
# Declared deviation from upstream 2d4661e (user 2026-10-03, option A after attempt 1): frontendproxy's memory limit is
# raised from upstream's 50M (docker-compose.yml:319-320) for this epoch only.  Attempt 1's lead cell (frontend pause
# at 10/s) had Envoy killed by the memory cgroup (srv6 kernel log 11:46:59Z, anon-rss ~46 MB + file-rss ~41 MB) with
# ~120 requests waiting; at 10/s x 15 s up to 150 wait (300 if both timeouts were absent).  256 MiB is ~2.5x the
# memory at the kill, extrapolated to 300 waiting requests at 0.3 MB each (twice the cost the kill implies), so the
# proxy holds a full pause; the per-cell OOM guard invalidates a cell if it does not.  Applied by
# `docker update --memory` right after `compose up`, before readiness; the overlays and the frozen epochs are unchanged.
SERVICE_MEMORY_LIMIT_BYTES = {"frontendproxy": 256 * 1024 * 1024}
UPSTREAM_MEMORY_LIMIT_BYTES = {"frontendproxy": 50 * 1024 * 1024}
# Removed right after `up`, before readiness: frontendproxy has a required `depends_on: loadgenerator`, so
# `up --scale loadgenerator=0` would depend on Compose-version semantics (review 2026-10-03, B1).
UPSTREAM_GENERATOR_MECHANISM = "docker compose rm --stop --force loadgenerator, after up and before readiness"
# Metric export interval is NOT changed in this initial test (an emission change): the SDK default stays.
METRIC_EXPORT_INTERVAL_MILLISECONDS = None
POST_RECOVERY_ALLOWANCE_SECONDS = 2.0          # revert command plus route probe round trip
# The terminal validator classifies a request within this many seconds of a fault edge as during-fault
# (candidate_terminal.FAULT_EDGE_SLACK_SECONDS); the compile-time phase check uses the same slack.
FAULT_EDGE_SLACK_SECONDS = 5
# Trace completeness (protocol decision 25, user 2026-10-03, shared by all three sweeps; replaces M1's 99 % after OTel
# attempt 1 stopped at 20/21): (i) a request that STARTS in the fault-and-drain window [onset command issued, route
# ready + drain] may lack a complete trace: counted and recorded as the fault's effect, never blocking; (ii) everywhere
# else (before onset, after the drain, every no-fault cell) the cell is blocked only if more than
# max(TRACE_INCOMPLETE_ALLOWANCE_MINIMUM, floor(TRACE_INCOMPLETE_ALLOWANCE_SHARE x successful requests)) successful
# requests lack a complete trace.  The drain is the client timeout + TRACE_DRAIN_MARGIN_SECONDS (TeaStore's Q3).
TRACE_DRAIN_MARGIN_SECONDS = 2.0
TRACE_DRAIN_SECONDS = REQUEST_TIMEOUT_SECONDS + TRACE_DRAIN_MARGIN_SECONDS
TRACE_INCOMPLETE_ALLOWANCE_SHARE = 0.01
TRACE_INCOMPLETE_ALLOWANCE_MINIMUM = 1
# Wall budget (engineering defaults).  Measured overhead per cell over its timed part: run 3 13.4 min and v3r1
# 13.3 min per cell for 720 s timed, i.e. 80-84 s (compose up, readiness, 15 s collector settle, posture proof,
# tshark, compose down); 120 s here is that plus ~40 s margin for the per-cell application-log capture.
BARRIER_LEAD_SECONDS = 1                       # candidate_remote.run_cell sleeps 1 s after starting the capture
CELL_OVERHEAD_SECONDS = 120
CELL_DEADLINE_RESERVE_SECONDS = 900            # candidate_remote.run_cell refuses a cell this close to the deadline
CLEANUP_RESERVE_SECONDS = 600                  # candidate_runtime.CLEANUP_RESERVE_SECONDS
APPROVAL_TO_FIRST_MUTATION_SECONDS = 3600      # the frozen epoch's slack: 11 h window over a 10 h minimum
# ---------------------------------------------------------------- derived

TOTAL_RUNS = len(REGIMES) * len(RATES) * EPISODES
CELLS_PER_BLOCK = len(REGIMES) * len(RATES)
TIMED_SECONDS_PER_CELL = WARMUP_SECONDS + BARRIER_LEAD_SECONDS + MEASUREMENT_SECONDS
CELL_PERIOD_ESTIMATE_SECONDS = TIMED_SECONDS_PER_CELL + CELL_OVERHEAD_SECONDS
# What the controller must still have at its first mutation: every cell, the last cell's deadline reserve, and
# the owned cleanup.  The GATE-RUN window adds the approval-to-launch slack, in whole hours because the gate
# driver's deadline is `run_window_hours` (an int) after approval.
MINIMUM_REMAINING_SECONDS = (
    TOTAL_RUNS * CELL_PERIOD_ESTIMATE_SECONDS + CELL_DEADLINE_RESERVE_SECONDS + CLEANUP_RESERVE_SECONDS
)
RUN_WINDOW_HOURS = int(math.ceil((MINIMUM_REMAINING_SECONDS + APPROVAL_TO_FIRST_MUTATION_SECONDS) / 3600.0))
EXPECTED_DESCRIPTOR_SHA256 = "be5b0b4dcd212aaa47908a6dd533e5cb73a104ab22b1b9e04a147e21ccb2c86d"
DECLARATION = "research/traffic-sweep/DECLARATION_OTEL.md (measurement repo; frozen 2026-10-03)"
AMENDMENTS = [
    "research/traffic-sweep/AMENDMENT_OTEL_1.md (measurement repo): shared trace-completeness rule, "
    "research/PROTOCOL_DRAFT_20261002.md decision 25 (user 2026-10-03); frontendproxy memory limit 50M -> 256M "
    "(user 2026-10-03, option A) and the per-cell container-health guard; relaunch 1 of 2, all 12 cells, attempt 2",
]
AUTHORITY = (
    "main repo research/traffic-sweep/BUDGET_REPLICATION.md (user 2026-10-03: replicate the Hotel sweep on OTel as "
    "an initial test); design values from research/traffic-sweep/DECLARATION.md (Hotel, frozen 2026-10-03); "
    "OTel mapping choices accepted by the user 2026-10-03 (\"accept all, M1 99 %\") and frozen in "
    "research/traffic-sweep/DECLARATION_OTEL.md"
)


def rate_token(rate: float) -> str:
    """10 -> '10', 0.2 -> '0p2', 0.05 -> '0p05'."""
    text = "%g" % float(rate)
    if "e" in text or "-" in text or not text:
        raise ProtocolError("rate %r has no plain decimal token" % (rate,))
    return text.replace(".", "p")


def offered_for(rate: float, seconds: float) -> int:
    product = float(rate) * float(seconds)
    offered = int(round(product))
    if offered < 1 or abs(product - offered) > 1e-9:
        raise ProtocolError("rate x seconds must be a positive integer: %r x %r" % (rate, seconds))
    return offered


def _unit_draw(*parts: Any) -> float:
    """Uniform in [0, 1) from SHA-256 of the NUL-joined parts (no stdlib RNG: identical on 3.9 and 3.13)."""
    text = "\0".join(str(part) for part in parts)
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16) / float(1 << 64)


def onset_phase_offset(regime: str, rate: float, block: int) -> float:
    """Hotel's stratified seeded offset (candidate_sweep.onset_phase_offset), keyed by (regime, rate, block)."""
    if ONSET_PHASE_OFFSET == "none":
        return 0.0
    if not 1 <= int(block) <= EPISODES:
        raise ProtocolError("block %r is outside 1..%d" % (block, EPISODES))
    inter_arrival = 1.0 / float(rate)
    strata = sorted(range(EPISODES), key=lambda stratum: _unit_draw(
        SCHEDULE_SEED, EPOCH, regime, rate_token(rate), "onset-stratum", stratum))
    stratum = strata[int(block) - 1]
    position = _unit_draw(SCHEDULE_SEED, EPOCH, regime, rate_token(rate), "b%02d" % int(block), "onset-phase")
    offset = round((stratum + position) / EPISODES * inter_arrival, 6)
    return min(offset, round(inter_arrival - 1e-6, 6))


def scheduled_slots_by_phase(rate: float, measurement: float, onset: float, hold: float) -> Dict[str, int]:
    """Planned request slots per phase as the terminal validator classifies them (by scheduled offset, with the
    fault-edge slack): pre < onset - slack; during in [onset - slack, revert + slack]; post-readiness after the
    scheduled revert + the recovery allowance + slack.  A fault cell with an empty phase is refused here, because
    the terminal validator would refuse it by construction."""
    offsets = [sequence / float(rate) for sequence in range(offered_for(rate, measurement))]
    revert = onset + hold + POST_RECOVERY_ALLOWANCE_SECONDS
    counts = {
        "pre-fault": sum(1 for value in offsets if value < onset - FAULT_EDGE_SLACK_SECONDS),
        "during-fault": sum(
            1 for value in offsets
            if onset - FAULT_EDGE_SLACK_SECONDS <= value <= revert + FAULT_EDGE_SLACK_SECONDS
        ),
        "post-readiness": sum(1 for value in offsets if value > revert + FAULT_EDGE_SLACK_SECONDS),
    }
    if any(count < 1 for count in counts.values()):
        raise ProtocolError("a fault phase has no scheduled request at rate %r (onset %r)" % (rate, onset))
    return counts


def cell_timing(regime: str, rate: float, block: int) -> Dict[str, Any]:
    """Every per-cell value the target controller and the validators read, derived from the parameters above."""
    measurement = MEASUREMENT_SECONDS
    offset = onset_phase_offset(regime, rate, block)
    onset = round(FAULT_ONSET_BASE_SECONDS + offset, 6)
    hold = FAULT_HOLD_SECONDS
    if not 0 < onset < onset + hold + POST_RECOVERY_ALLOWANCE_SECONDS < measurement:
        raise ProtocolError("fault window must lie strictly inside the measurement")
    fault = FAULTS[regime]
    slots = scheduled_slots_by_phase(rate, measurement, onset, hold) if fault is not None else None
    return {
        "requestsPerSecond": float(rate),
        "interArrivalSeconds": 1.0 / float(rate),
        "concurrency": CONCURRENCY,
        "requestTimeoutSeconds": REQUEST_TIMEOUT_SECONDS,
        "warmupSeconds": WARMUP_SECONDS,
        "warmupRequestsPerSecond": WARMUP_REQUESTS_PER_SECOND,
        "warmupOffered": offered_for(WARMUP_REQUESTS_PER_SECOND, WARMUP_SECONDS),
        "measurementSeconds": measurement,
        "offered": offered_for(rate, measurement),
        "faultApplied": fault is not None,
        "faultOnsetBaseSeconds": FAULT_ONSET_BASE_SECONDS,
        "faultOnsetPhaseOffsetSeconds": offset,
        "faultOnsetSeconds": onset,
        "faultHoldSeconds": hold,
        # A no-fault cell carries the same (seeded) window as a pseudo window for G1/G2 and false alarms.
        "scoredWindowSeconds": [onset, round(onset + hold, 6)],
        "postRecoveryAllowanceSeconds": POST_RECOVERY_ALLOWANCE_SECONDS,
        "scheduledSlotsByPhase": slots,
        "route": {"method": ROUTE_METHOD, "path": ROUTE_PATH, "services": list(ROUTE_SERVICES)},
        "upstreamGeneratorsOff": list(UPSTREAM_GENERATORS_OFF),
        "planRunCount": TOTAL_RUNS,
        "planMinimumRemainingSeconds": MINIMUM_REMAINING_SECONDS,
        "traceDrainSeconds": TRACE_DRAIN_SECONDS,
        "traceIncompleteAllowanceShare": TRACE_INCOMPLETE_ALLOWANCE_SHARE,
        "traceIncompleteAllowanceMinimum": TRACE_INCOMPLETE_ALLOWANCE_MINIMUM,
        "serviceMemoryLimitBytes": dict(SERVICE_MEMORY_LIMIT_BYTES),
        "containerHealthGuard": True,
        "applicationLogTimestamps": True,
        "probeStamps": True,
        "protocolGates": True,
    }


def run_key_for(regime: str, rate: float, block: int, posture: str, attempt: int) -> Dict[str, Any]:
    return {
        "studyEpoch": EPOCH, "regime": regime, "requestsPerSecond": float(rate),
        "block": int(block), "posture": posture, "attempt": validate_attempt(attempt),
    }


def run_id_for(run_key: Mapping[str, Any]) -> str:
    """The frozen compiler's rule: the first 24 hex of the runKey's canonical sha256."""
    return hashlib.sha256(canonical_json_bytes(dict(run_key))).hexdigest()[:24]


def block_order(block: int) -> List[Dict[str, Any]]:
    """Every (regime, rate) pair once, Fisher-Yates shuffled by SHA-256 draws keyed by seed and block (Hotel's
    rule); block 1 then starts with the lead cell."""
    pairs = [{"regime": regime, "rate": float(rate)} for regime in REGIMES for rate in RATES]
    for index in range(len(pairs) - 1, 0, -1):
        draw = int(hashlib.sha256(
            ("%s\0%s\0block-%02d\0draw-%d\0%s" % (SCHEDULE_SEED, EPOCH, block, index, SCHEDULE_CONTEXT))
            .encode("utf-8")
        ).hexdigest(), 16)
        other = draw % (index + 1)
        pairs[index], pairs[other] = pairs[other], pairs[index]
    if block == 1:
        lead = [row for row in pairs if (row["regime"], row["rate"]) == (LEAD_CELL[0], float(LEAD_CELL[1]))]
        if len(lead) != 1:
            raise ProtocolError("lead cell is not in block 1")
        pairs = lead + [row for row in pairs if row is not lead[0]]
    return pairs


def allocate_schedule() -> List[Dict[str, Any]]:
    """The design-level schedule receipt (attempt-free): per block, the (regime, rate) order."""
    if POSTURES != ("full",):
        raise ProtocolError("the traffic sweep runs the full posture only")
    if ONSET_PHASE_OFFSET not in ONSET_PHASE_OFFSETS:
        raise ProtocolError("onset phase offset rule is not declared")
    if len(set(RATES)) != len(RATES) or any(not (math.isfinite(rate) and rate > 0) for rate in RATES):
        raise ProtocolError("rates must be distinct, finite and positive")
    if METRIC_EXPORT_INTERVAL_MILLISECONDS is not None:
        raise ProtocolError("a metric export interval override is an emission change this epoch does not make")
    blocks = []
    for block in range(1, EPISODES + 1):
        order = ["%s@r%s" % (row["regime"], rate_token(row["rate"])) for row in block_order(block)]
        blocks.append({"block": block, "order": order, "orderSha256": canonical_sha256(order)})
    every = [item for row in blocks for item in row["order"]]
    if len(every) != TOTAL_RUNS or len(set(every)) != TOTAL_RUNS:
        raise ProtocolError("schedule does not contain every cell exactly once")
    return blocks


def derive_sweep_descriptor(predecessor_path: Path = None) -> Dict[str, Any]:
    """Generate the sweep descriptor from the byte-pinned offpath descriptor.

    This function IS the descriptor's source: the checked-in otel-traffic-sweep-v1.json must equal
    ``_pretty_bytes`` of its result (tested), so the file is regenerated, never hand-edited.  Carried over
    unchanged from offpath: source, target, postureRealization (the runtime's catalog and D13 boundary checks
    read all four postures), setupPreconditions, missingness, evidence, status.  Replaced: id, design,
    schedule, timing, workload, faultDesign, groundTruth, outcomes, analysis, runIdentity, workflow blockers,
    and the supersession record becomes a ``derivedFrom`` record (the offpath epoch is not superseded).
    """
    path = Path(predecessor_path) if predecessor_path is not None else frozen.EPOCHS[PREDECESSOR_EPOCH]["descriptor"]
    base = frozen.load_descriptor(path)
    if base["id"] != PREDECESSOR_EPOCH:
        raise ProtocolError("the sweep is derived from the offpath descriptor only")
    schedule = allocate_schedule()
    document = {key: copy.deepcopy(base[key]) for key in (
        "evidence", "missingness", "module", "postureRealization", "setupPreconditions", "source", "status",
        "target",
    )}
    document["id"] = EPOCH
    document["declaration"] = DECLARATION
    document["amendments"] = list(AMENDMENTS)
    document["design"] = {
        "postures": list(POSTURES),
        "regimes": [
            {"id": regime, "kind": "no-fault-calibration" if FAULTS[regime] is None else "effect",
             "fault": FAULTS[regime], "artifactRootClass": ARTIFACT_ROOTS[regime]}
            for regime in REGIMES
        ],
        "omittedRegimes": copy.deepcopy(OMITTED_REGIMES),
        "rates": list(RATES),
        "episodesPerRegimeAndRate": EPISODES,
        "blocks": EPISODES,
        "cellsPerBlock": CELLS_PER_BLOCK,
        "totalRuns": TOTAL_RUNS,
        "blockRule": "each-block-holds-every-(regime,rate)-pair-exactly-once",
        "coldStartEachRun": True,
        "faultAppliedToEveryEffectCell": True,
        "noFaultCellsCarryPseudoWindow": True,
        "postureRule": (
            "full only; placements are evaluated by restriction of full cells (an approximation: a sensor can "
            "behave differently when other sensors are off)"
        ),
    }
    document["schedule"] = {
        "version": SCHEDULE_CONTEXT,
        "seed": SCHEDULE_SEED,
        "shuffle": "fisher-yates-over-regimes-x-rates-with-sha256-draws",
        "drawEncoding": "UTF-8(seed || NUL || epoch || NUL || block-NN || NUL || draw-i || NUL || version)",
        "leadCell": "%s at %s/s first in block 1" % (LEAD_CELL[0], rate_token(LEAD_CELL[1])),
        "blocks": schedule,
    }
    document["runIdentity"] = {
        "attemptBeginsBeforeFirstExternalMutation": True,
        "fields": ["studyEpoch", "regime", "requestsPerSecond", "block", "posture", "attempt"],
        "initialAttempt": DEFAULT_ATTEMPT,
        "retryMayReplaceCell": False,
        "runIdRule": "first 24 hex of sha256(canonical runKey) (the frozen compiler's rule)",
        "onsetOffsetDependsOnAttempt": False,
    }
    document["timing"] = {
        "warmupSeconds": WARMUP_SECONDS,
        "warmupRequestsPerSecond": WARMUP_REQUESTS_PER_SECOND,
        "measurementSeconds": MEASUREMENT_SECONDS,
        "offeredRule": "requests-per-second-x-measurement-seconds-integral",
        "offeredByRate": {rate_token(rate): offered_for(rate, MEASUREMENT_SECONDS) for rate in RATES},
        "faultOnsetBaseSeconds": FAULT_ONSET_BASE_SECONDS,
        "faultOnsetPhaseOffset": ONSET_PHASE_OFFSET,
        "faultOnsetPhaseSelectorEncoding": (
            "stratum order: UTF-8(seed || NUL || epoch || NUL || regime || NUL || rate token || NUL || "
            "onset-stratum || NUL || stratum); position: UTF-8(seed || NUL || epoch || NUL || regime || NUL || "
            "rate token || NUL || bNN || NUL || onset-phase)"
        ),
        "faultHoldSeconds": FAULT_HOLD_SECONDS,
        "faultOnsetAcceptanceSeconds": [-gates.ONSET_TOLERANCE_S, gates.ONSET_TOLERANCE_S],
        "postRecoveryAllowanceSeconds": POST_RECOVERY_ALLOWANCE_SECONDS,
        "faultEdgeSlackSeconds": FAULT_EDGE_SLACK_SECONDS,
        "requestTimeoutSeconds": REQUEST_TIMEOUT_SECONDS,
        "metricExportIntervalMilliseconds": METRIC_EXPORT_INTERVAL_MILLISECONDS,
        "metricExportIntervalNote": (
            "not set: every SDK keeps its own default (60 s observed, research/system-profiles/otel.md); changing it "
            "is an emission change this initial test does not make (a declared limit)"
        ),
        "budget": {
            "barrierLeadSeconds": BARRIER_LEAD_SECONDS,
            "timedSecondsPerCell": TIMED_SECONDS_PER_CELL,
            "cellOverheadSeconds": CELL_OVERHEAD_SECONDS,
            "cellPeriodEstimateSeconds": CELL_PERIOD_ESTIMATE_SECONDS,
            "cellDeadlineReserveSeconds": CELL_DEADLINE_RESERVE_SECONDS,
            "cleanupReserveSeconds": CLEANUP_RESERVE_SECONDS,
            "approvalToFirstMutationSeconds": APPROVAL_TO_FIRST_MUTATION_SECONDS,
            "minimumRemainingRule": "totalRuns x cellPeriod + cellDeadlineReserve + cleanupReserve",
            "minimumRemainingSeconds": MINIMUM_REMAINING_SECONDS,
            "runWindowRule": "ceil-to-whole-hours(minimumRemaining + approvalToFirstMutation)",
            "runWindowHours": RUN_WINDOW_HOURS,
        },
    }
    document["workload"] = {
        "kind": "single-route-open-loop",
        "entry": "frontendproxy",
        "method": ROUTE_METHOD,
        "path": ROUTE_PATH,
        "productId": ROUTE_PRODUCT_ID,
        "routeServices": list(ROUTE_SERVICES),
        "routeDerivation": list(ROUTE_DERIVATION),
        "requestsPerSecondLevels": list(RATES),
        "arrivals": "constant spacing (offset = sequence / rate) from the shared barrier",
        "window": "the workload returns no earlier than barrier + measurementSeconds at every rate (the CPU and capture windows are the same length at every rate)",
        "concurrency": CONCURRENCY,
        "concurrencyRule": "ceil(2 x max rate x request timeout): the worker cap covers rate x timeout with a 2x margin",
        "requestTimeoutSeconds": REQUEST_TIMEOUT_SECONDS,
        "traceContext": (
            "every request carries traceparent 00-<trace id>-<span id>-01 and x-obsplacement-request-token, the "
            "offpath identity rule (candidate_remote.request_identity)"
        ),
        "ledger": (
            "request-ledger.json: one row per scheduled request with scheduledOffsetSeconds, scheduledAtEpoch, "
            "startedAtEpoch/endedAtEpoch, startedMonotonic/endedMonotonic (the fault receipt's clock), status, "
            "bytes, error and outcome ok|timeout|failed"
        ),
        "warmup": "30 s at 10/s for every rate on the same route, never scored",
        "readiness": (
            "the harness's checkout-journey readiness (one complete journey, stack-wide) and then one route request "
            "returning 200; both carry the token readiness-not-scored and run before the warm-up"
        ),
        "upstreamGenerators": {
            "off": list(UPSTREAM_GENERATORS_OFF),
            "mechanism": UPSTREAM_GENERATOR_MECHANISM,
            "why": (
                "the upstream Locust loadgenerator runs in every offpath/v3 cell (LOCUST_HEADLESS true overrides "
                "LOCUST_AUTOSTART false; retained v3a2 b03-03-full otelcol.log: 360 loadgenerator records, "
                "Starting Locust 2.18.2, GET http://frontend-proxy:18080/ failing) and asks flagd on every task; "
                "the sweep's rate must be the only traffic"
            ),
            "proof": (
                "upstream-generator.json per cell: zero containers carrying the project's service label after the "
                "removal and after the window (asked of the Docker engine)"
            ),
            "runsOnlyBetweenUpAndRemoval": True,
        },
    }
    document["faultDesign"] = {
        "scenarios": copy.deepcopy(SCENARIOS),
        "onsetBaseSeconds": FAULT_ONSET_BASE_SECONDS,
        "holdSeconds": FAULT_HOLD_SECONDS,
        "onsetStamp": "pre-command (actualOnsetMonotonicOffsetSeconds is taken immediately before the command; F-ADH-085)",
        "containerResolvedBeforeOnset": True,
        "probes": (
            "every route probe the fault worker sends inside the measurement (during-fault, post-revert readiness) "
            "is stamped into the receipt's probes list (phase, start/end monotonic, available) so the analysis "
            "can exclude its windows from sensor scoring; probe requests carry the token readiness-not-scored"
        ),
        "omitted": copy.deepcopy(OMITTED_REGIMES),
        "metricExportIntervalMilliseconds": METRIC_EXPORT_INTERVAL_MILLISECONDS,
    }
    truth = copy.deepcopy(base["groundTruth"])
    fault = truth["fault"]
    fault["scenarioContracts"] = [
        {
            "scenario": name, "service": SCENARIOS[name]["service"], "action": SCENARIOS[name]["action"],
            "containerIdentityRule": "same-container-pre-during-post",
            "prePredicate": "running-and-unpaused" if SCENARIOS[name]["action"] == "pause" else "running-and-unthrottled",
            "duringPredicate": SCENARIOS[name]["duringPredicate"],
            "postPredicate": (
                "running-and-unpaused-and-route-ready" if SCENARIOS[name]["action"] == "pause"
                else "running-and-nanocpus-reverted-and-route-ready"
            ),
            "entryRouteDuringFault": SCENARIOS[name]["entryRouteDuringFault"],
        }
        for name in sorted(SCENARIOS)
    ]
    fault.pop("offPathFraming", None)
    fault["requiredReceiptFields"] = sorted(set(fault["requiredReceiptFields"]) | {"probes"})
    path_truth = truth["path"]
    path_truth["expectedNoFaultPath"] = list(ROUTE_SERVICES)
    path_truth["faultSpecificTruth"] = {
        name: {
            "duringFaultExpectedOutcome": "offered-request-outcome-not-presumed",
            "duringFaultFullPathRequired": False,
            "postRecoveryFullPathRequired": True,
            "preFaultFullPathRequired": True,
        }
        for name in sorted(SCENARIOS)
    }
    document["groundTruth"] = truth
    document["outcomes"] = {
        "primary": "time to detection per sensor and for the request ledger (first catch after onset; a miss "
                   "is charged at the hold end; averaged over episodes)",
        "secondary": "impact before detection: failed requests started before the first catch, by scheduled time",
        "costRegimeOnly": None,
        "offeredRequestsAreDenominator": True,
        "windowMembership": "monotonic-shared-barrier",
    }
    document["analysis"] = {
        "comparativeUnit": "(fault, rate); one episode per pair in this initial test",
        "descriptiveOnly": True,
        "initialTest": "shakedown, not confirmatory (BUDGET_REPLICATION.md)",
        "detectionTimeMissCharge": "window-end (hold end)",
        "probeWindowsExcludedFromSensorScoring": True,
        "traceCompleteness": {
            "authority": (
                "research/PROTOCOL_DRAFT_20261002.md decision 25 (user 2026-10-03, all three sweeps); replaces the "
                "M1 99 % rule after OTel attempt 1 stopped at cell 8 (20/21)"
            ),
            "drainSeconds": TRACE_DRAIN_SECONDS,
            "drainRule": "client timeout + %g s (TeaStore Q3)" % TRACE_DRAIN_MARGIN_SECONDS,
            "allowanceShare": TRACE_INCOMPLETE_ALLOWANCE_SHARE,
            "allowanceMinimum": TRACE_INCOMPLETE_ALLOWANCE_MINIMUM,
            "rule": (
                "windows by request start on the fault receipt's monotonic clock. Fault cells: pre-onset = start before "
                "the onset command was issued; fault-and-drain = start in [onset command issued, route ready + "
                "drainSeconds]; after-drain = later. No-fault cells: one whole-measurement window. (i) incomplete "
                "traces of fault-and-drain requests are counted and recorded (with request tokens) as the fault's "
                "effect, never blocking; (ii) the cell is blocked only if the successful requests of the other windows "
                "with an incomplete trace number more than max(allowanceMinimum, floor(allowanceShare x their "
                "successful requests)). Complete = the request's own trace id observed and exactly the route's "
                "services. Every incomplete trace is counted per window (successful and unsuccessful separately) in "
                "trace-completeness.json, evaluated on the target before the next cell and replayed by the terminal"
            ),
        },
        "forbidden": copy.deepcopy(base["analysis"]["forbidden"]),
    }
    document["protocolGates"] = {
        "module": "modules/otel-demo/validation/protocol_gates.py",
        "vendoredFrom": "src/obsplacement/protocol_gates.py (measurement repo, d3fc741), byte-identical",
        "evaluatedOn": "the target, per cell, before the next cell (candidate_remote); replayed by the terminal validator",
        "blocking": ["F1", "G1", "G2", "G4"],
        "recordedNotBlocking": ["R2.recovery"],
        "notEvaluated": {
            "P0": "the per-cell posture proof is config- and probe-based; no per-service connection count is recorded",
            "R1": "no per-channel recordsAfterWarmup and no per-route readiness map is recorded",
            "R2": "fresh project and down -v are enforced by the cell runner, not recorded as a gate input",
        },
        "g4ChannelScope": "ledger-only (no per-channel in-cell / total counts are recorded)",
        "thresholds": {
            "FLOOR": gates.FLOOR, "PRE_FAIL_MAX": gates.PRE_FAIL_MAX, "SCOPE_MIN": gates.SCOPE_MIN,
            "SCOPE_SLACK_S": gates.SCOPE_SLACK_S, "ONSET_TOLERANCE_S": gates.ONSET_TOLERANCE_S,
            "HOLD_TOLERANCE_S": gates.HOLD_TOLERANCE_S, "G1_MIN_DISPATCHED": gates.G1_MIN_DISPATCHED,
        },
        "stopRule": "first-invalid-cell",
    }
    document["collection"] = {
        "collectorCarrier": "otelcol debug exporter, one unrotated json-file segment (otelcol.log), unchanged",
        "requestWitness": "frontendproxy JSON access log, unchanged",
        "applicationLogs": (
            "application.log: docker compose logs --no-color --timestamps for every started application service "
            "except the collector (its output is otelcol.log); Docker's RFC3339Nano receive stamp prefixes every line"
        ),
        "cpu": "docker-engine cumulative CPU before and after the window, unchanged (diagnostic in every cell)",
        "telemetryBytes": "sudo -n tcpdump on OTLP ports, unchanged (the only sudo on fb14srv6)",
    }
    workflow = copy.deepcopy(base["workflow"])
    workflow["constructionBlockers"] = ["gate-plan-pending", "gate-run-not-requested"]
    document["workflow"] = workflow
    document["sutDeviations"] = [
        {
            "service": service,
            "setting": "memory limit (HostConfig.Memory)",
            "upstream": "%d bytes (50M; upstream 2d4661e docker-compose.yml:319-320)" % UPSTREAM_MEMORY_LIMIT_BYTES[service],
            "sweep": "%d bytes (256M)" % limit,
            "mechanism": (
                "docker update --memory <bytes> --memory-swap <same ratio as before> on the running container, right "
                "after compose up and before readiness; verified by inspect and recorded in container-health.json"
            ),
            "reason": (
                "attempt 1 (2026-10-03): Envoy killed by the memory cgroup 12 s into the frontend pause at 10/s (srv6 "
                "kernel log 11:46:59Z; again 11:59:31Z after cell 3's window); 124 of 1,800 requests lost their "
                "access-log line and the cell failed the terminal's witness check; user decision option A"
            ),
            "scope": "this epoch only; the overlays and every frozen epoch keep upstream's limit",
        }
        for service, limit in sorted(SERVICE_MEMORY_LIMIT_BYTES.items())
    ]
    document["containerHealthGuard"] = {
        "authority": "user 2026-10-03 (with option A)",
        "rule": (
            "every project container is inspected right before the warm-up (baseline) and after the cell's captures, "
            "before cleanup (final): State.OOMKilled, RestartCount, status and HostConfig.Memory are recorded in "
            "container-health.json; the cell is invalid if any container has OOMKilled true, if an application "
            "container restarted or was replaced between baseline and final, or if a declared memory limit is not "
            "in effect; replayed by the terminal"
        ),
    }
    document["derivedFrom"] = {
        "authority": AUTHORITY,
        "studyEpoch": PREDECESSOR_EPOCH,
        "descriptorPath": str(path_relative(path)),
        "descriptorByteSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "descriptorCanonicalSha256": canonical_sha256(base),
        "disposition": (
            "the offpath epoch is not superseded: it keeps its own descriptor, plan and admission; the sweep is a "
            "separate epoch selected by execution/study-epoch.json"
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
        raise ProtocolError("sweep descriptor must be one JSON object")
    expected = derive_sweep_descriptor()
    if canonical_json_bytes(document) != canonical_json_bytes(expected):
        raise ProtocolError("sweep descriptor differs from its generator")
    digest = canonical_sha256(document)
    if digest != EXPECTED_DESCRIPTOR_SHA256:
        raise ProtocolError(
            "sweep descriptor canonical digest differs from the reviewed pin: expected %s, found %s"
            % (EXPECTED_DESCRIPTOR_SHA256, digest)
        )
    return document


def load_descriptor(path: Path = DEFAULT_DESCRIPTOR) -> Dict[str, Any]:
    try:
        payload = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProtocolError("cannot read sweep descriptor: %s" % exc) from exc
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
        "kind": "otel-demo-traffic-sweep-compiled-plan",
        "studyEpoch": EPOCH,
        "module": MODULE_ID,
        "applicationFamily": APPLICATION_FAMILY,
        "channel": CHANNEL,
        "descriptorSha256": canonical_sha256(document),
        "scheduleVersion": SCHEDULE_CONTEXT,
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
    """The one attempt every cell of a compiled sweep plan carries."""
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
    pairs = {(cell["runKey"]["regime"], cell["runKey"]["requestsPerSecond"]) for cell in cells}
    if pairs != {(regime, float(rate)) for regime in REGIMES for rate in RATES}:
        raise ProtocolError("compiled plan does not hold every (regime, rate) pair")
    first = cells[0]["runKey"]
    if (first["regime"], first["requestsPerSecond"]) != (LEAD_CELL[0], float(LEAD_CELL[1])):
        raise ProtocolError("the lead cell is not first in the plan")
    for cell in cells:
        if (cell["fault"] is None) != (cell["runKey"]["regime"] == "no-fault-calibration"):
            raise ProtocolError("fault/no-fault cell boundary differs")


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
        help="write (exclusive-create) or byte-verify <root> as the sweep descriptor derived from offpath",
    )
    parser.add_argument("--print-digests", action="store_true",
                        help="print the unpinned descriptor and attempt plan digests (for re-pinning after a change)")
    args = parser.parse_args(argv)
    if args.print_digests:
        document = derive_sweep_descriptor()
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
        frozen._install_or_verify(Path(args.root), _pretty_bytes(derive_sweep_descriptor()), "sweep descriptor")
        print(canonical_sha256(derive_sweep_descriptor()))
        return 0
    print(json.dumps(materialize(args.root, args.descriptor, args.attempt), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
