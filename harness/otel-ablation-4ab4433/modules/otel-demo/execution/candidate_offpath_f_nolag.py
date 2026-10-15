#!/usr/bin/env python3
"""Compile the OTel Demo campaign-F ablation epoch (otel-offpath-f-nolag-v1) without executing it.

Authority: main repo research/traffic-sweep/BUDGET_OVERNIGHT_20261014.md item 2 (user, 2026-10-14 ~14:45Z).  The epoch is campaign F's design
(``candidate_offpath_f.py``, read nowhere and never edited here: its descriptor is pinned by digest) with EXACTLY ONE change: the collector's
``kafkametrics`` receiver, its ``resource/kafka`` processor, its ``metrics/kafka`` pipeline and ``otelcol``'s ``depends_on: kafka`` are NOT
rendered.  Everything else is F's, byte for byte (tested): the upstream Locust task mix as an open loop at 25 req/s, the regimes no-fault,
frauddetectionservice pause, accountingservice pause and the frontend pause, 5 blocks (1-3 training, 4-5 test), two no-fault cells per block
(25 cells), ``OTEL_METRIC_EXPORT_INTERVAL=5000`` on the 18 services with an ``OTEL_METRICS_EXPORTER`` line, spanmetrics ``metrics_flush_interval: 5s``,
collector log sampler off, trace rules, per-route completeness, gates, posture ``full`` and the sizing rules.  Differences from F in the compiler:
epoch id, schedule version and seed (20261015, the build date: the epoch id is in every draw, so the onset strata and block orders differ from
F's whatever the seed), the descriptor's ``design.ablation`` record and the absence of the kafkametrics rows.

The question it answers (budget item 2): does F's pass hold without the lag receiver.  The consumer-group lag lane has no kafkametrics signal in this
epoch; the broker's own Java-agent metrics (the ``kafka`` service is in the posture's active set) are unchanged.

The epoch is active only when the committed selector ``execution/study-epoch.json`` names it.  Rendering is epoch-gated in ``materialize.py``
(``TELEMETRY_CADENCE_EPOCHS`` carries the interval and the flush, ``KAFKAMETRICS_EPOCHS`` only F carries the receiver, its processor and pipeline
and otelcol's wait for kafka).

Construction only: no Docker, SSH, subprocess, socket or transport surface.  Runs as ``python3 -I`` on CPython 3.9 on the target (the
runtime imports it there): standard library only, sibling files are loaded by path, no PEP 604 annotation evaluated at runtime.
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
DEFAULT_DESCRIPTOR = ROOT / "pipelines/campaigns/otel-offpath-f-nolag-v1.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# C's compiler supplies the cell shape (through B's and the sweep's), the H10/H4 flags, the trace rule per cell kind, the
# draw functions, the JSON helpers and the attempt rule.  ``quiet``, ``sweep`` and ``frozen`` are the very module instances C
# loaded, so every ProtocolError is one class.
repeat_c = _load("otel_offpath_f_nolag_c_compiler", HERE / "candidate_repeat_c.py")
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

EPOCH = "otel-offpath-f-nolag-v1"
DESIGN_EPOCH = "otel-offpath-f-v1"                    # the design this epoch copies (F); its descriptor is pinned below, never read
DESIGN_DESCRIPTOR_SHA256 = "6164052dc62c323be37c286afd0f41a90808bbd251f62d56eb959eec01233b7e"      # F (25 req/s, all three faults, 2 no-fault cells per block)
BASE_DESIGN_EPOCH = "otel-offpath-e-v1"               # F's own design source (E), recorded for the lineage
BASE_DESIGN_DESCRIPTOR_SHA256 = "a17ac3d676a85dd9b488bd100a925679322ff93ec6c4257e8f102acd700e4398"
PREDECESSOR_EPOCH = repeat_c.EPOCH                    # otel-repeat-episodes-c-v1: the cell this campaign runs at RATE req/s
MODULE_ID = repeat_c.MODULE_ID
APPLICATION_FAMILY = repeat_c.APPLICATION_FAMILY
CHANNEL = repeat_c.CHANNEL
SCHEDULE_CONTEXT = "offpath-f-nolag-schedule-v1"
MAXIMUM_EVIDENCE_LABEL = repeat_c.MAXIMUM_EVIDENCE_LABEL

# ---------------------------------------------------------------- the workload: the upstream Locust task mix
MIX_KIND = "otel-demo-upstream-locust-mix-v1"
# upstream/opentelemetry-demo 2d4661e src/loadgenerator/locustfile.py (sha256 84815ac2...) and people.json (sha256 2e780c99...).
UPSTREAM_LOCUSTFILE_SHA256 = "84815ac2e778192ebd6e56e428271b8568a261e87df6658ed87cdbf37e71328e"
UPSTREAM_PEOPLE_SHA256 = "2e780c99cd1950213c798ba086c184b6ae89a98af8a6df4bb190b2e19bcf77ab"
MIX_PRODUCTS = (
    "0PUK6V6EV0", "1YMWWN1N4O", "2ZYFJ3GM2N", "66VCHSJNUP", "6E92ZMYYFZ", "9SIQT8TOJO", "L9ECAV7KIM", "LS4PSXUNUM",
    "OLJCESPC7Z", "HQTGWGPNH4",
)
MIX_CATEGORIES = ("binoculars", "telescopes", "accessories", "assembly", "travel", "books", None)
MIX_QUANTITIES = (1, 2, 3, 4, 5, 10)
MIX_MULTI_ADDS = (2, 3, 4)
MIX_PEOPLE_JSON = (
    '[{"email":"larry_sergei@example.com","address":{"streetAddress":"1600 Amphitheatre Parkway","zipCode":"94043","city":"Mountain View","state":"CA","country":"United States"},"userCurrency":"USD","creditCard":{"creditCardNumber":"4432-8015-6152-0454","creditCardExpirationMonth":1,"creditCardExpirationYear":2039,"creditCardCvv":672}},'
    '{"email":"bill@example.com","address":{"streetAddress":"One Microsoft Way","zipCode":"98052","city":"Redmond","state":"WA","country":"United States"},"userCurrency":"USD","creditCard":{"creditCardNumber":"4532-4211-7434-1278","creditCardExpirationMonth":2,"creditCardExpirationYear":2039,"creditCardCvv":114}},'
    '{"email":"steve@example.com","address":{"streetAddress":"One Apple Park Way","zipCode":"95014","city":"Cupertino","state":"CA","country":"United States"},"userCurrency":"USD","creditCard":{"creditCardNumber":"4532-6178-2799-1951","creditCardExpirationMonth":3,"creditCardExpirationYear":2039,"creditCardCvv":239}},'
    '{"email":"mark@example.com","address":{"streetAddress":"1 Hacker Way","zipCode":"94025","city":"Menlo Park","state":"CA","country":"United States"},"userCurrency":"USD","creditCard":{"creditCardNumber":"4539-1103-5661-7083","creditCardExpirationMonth":4,"creditCardExpirationYear":2039,"creditCardCvv":784}},'
    '{"email":"jeff@example.com","address":{"streetAddress":"410 Terry Ave N","zipCode":"98109","city":"Seattle","state":"WA","country":"United States"},"userCurrency":"USD","creditCard":{"creditCardNumber":"4916-0816-6217-7968","creditCardExpirationMonth":5,"creditCardExpirationYear":2039,"creditCardCvv":397}},'
    '{"email":"reed@example.com","address":{"streetAddress":"100 Winchester Circle","zipCode":"95032","city":"Los Gatos","state":"CA","country":"United States"},"userCurrency":"USD","creditCard":{"creditCardNumber":"4929-5431-0337-5647","creditCardExpirationMonth":6,"creditCardExpirationYear":2039,"creditCardCvv":793}},'
    '{"email":"tobias@example.com","address":{"streetAddress":"150 Elgin St","zipCode":"K2P1L4","city":"Ottawa","state":"ON","country":"Canada"},"userCurrency":"CAD","creditCard":{"creditCardNumber":"4763-1844-9699-8031","creditCardExpirationMonth":7,"creditCardExpirationYear":2039,"creditCardCvv":488}},'
    '{"email":"jack@example.com","address":{"streetAddress":"1355 Market St","zipCode":"94103","city":"San Francisco","state":"CA","country":"United States"},"userCurrency":"USD","creditCard":{"creditCardNumber":"4929-6495-8333-3657","creditCardExpirationMonth":8,"creditCardExpirationYear":2039,"creditCardCvv":159}},'
    '{"email":"moore@example.com","address":{"streetAddress":"2200 Mission College Blvd","zipCode":"95054","city":"Santa Clara","state":"CA","country":"United States"},"userCurrency":"USD","creditCard":{"creditCardNumber":"4485-4803-8707-3547","creditCardExpirationMonth":9,"creditCardExpirationYear":2039,"creditCardCvv":682}}]'
)
# The services a request of each route is guaranteed to reach (a conservative subset, from upstream source reading, unexecuted
# at these rates; flagd is left out of every set because its presence depends on the flag in use and on the product).  The
# trace-completeness rule (decision 25 in fault cells, 56 in no-fault cells) calls a request's trace complete when its own
# trace id was observed and its observed services include the route's set.  Services the route may reach in addition (flagd,
# and for checkout the async consumers accountingservice, frauddetectionservice and kafka through the order message) are
# not required and never counted as unexpected.
MIX_ROUTES = {
    "index": {
        "method": "GET", "path": "/",
        "requiredServices": ["frontendproxy", "frontend"],
        "derivation": "frontendproxy -> frontend renders the shell; the product list is fetched client side (pages/index.tsx)",
    },
    "product": {
        "method": "GET", "path": "/api/products/{productId}",
        "requiredServices": ["frontendproxy", "frontend", "productcatalogservice"],
        "derivation": (
            "frontend pages/api/products/[productId]/index.ts -> productcatalogservice GetProduct; flagd only for "
            "OLJCESPC7Z (productcatalogservice main.go checkProductFailure); no currency call without a currencyCode"
        ),
    },
    "recommendations": {
        "method": "GET", "path": "/api/recommendations?productIds={productId}",
        "requiredServices": ["frontendproxy", "frontend", "recommendationservice", "productcatalogservice"],
        "derivation": (
            "frontend pages/api/recommendations.ts -> recommendationservice ListRecommendations (-> flagd, productcatalogservice "
            "ListProducts), then productcatalogservice GetProduct for up to 4 products"
        ),
    },
    "ads": {
        "method": "GET", "path": "/api/data?contextKeys={category}",
        "requiredServices": ["frontendproxy", "frontend", "adservice"],
        "derivation": (
            "frontend pages/api/data.ts -> adservice GetAds (-> flagd); a None category sends no query (requests drops None); "
            "upstream spells the path /api/data/ and relies on Next.js's 308 redirect to /api/data (trailingSlash is unset), "
            "which Python 3.9's urllib does not follow and which would show the request token to the proxy twice, so the "
            "canonical path is sent (a declared deviation in spelling, not in route)"
        ),
    },
    "view-cart": {
        "method": "GET", "path": "/api/cart",
        "requiredServices": ["frontendproxy", "frontend", "cartservice"],
        "derivation": (
            "frontend pages/api/cart.ts GET -> cartservice GetCart (valkey); upstream sends no sessionId, so the cart is the "
            "empty one of session '' and no productcatalogservice call follows"
        ),
    },
    "add-to-cart": {
        "method": "POST", "path": "/api/cart",
        "requiredServices": ["frontendproxy", "frontend", "cartservice"],
        "derivation": "frontend pages/api/cart.ts POST -> cartservice AddItem, then GetCart (valkey); no productcatalogservice call",
    },
    "checkout": {
        "method": "POST", "path": "/api/checkout",
        "requiredServices": [
            "frontendproxy", "frontend", "cartservice", "checkoutservice", "productcatalogservice", "currencyservice",
            "shippingservice", "quoteservice", "paymentservice", "emailservice",
        ],
        "derivation": (
            "frontend pages/api/checkout.ts -> checkoutservice PlaceOrder -> cartservice GetCart/EmptyCart, productcatalogservice "
            "GetProduct, currencyservice Convert, shippingservice GetQuote (-> quoteservice) and ShipOrder, paymentservice Charge, "
            "emailservice (HTTP), then the order message to Kafka topic orders (asynchronous: accountingservice, "
            "frauddetectionservice, whose consumer spans start their own traces, so they are never in the checkout request's "
            "trace); the offpath epoch's path check observed these ten plus flagd on every successful journey"
        ),
    },
}
# Upstream's tasks and weights (locustfile.py 109-172, flood_home dropped: weight 5 but 0 requests at the default flag value);
# the request sequence of a task is code in candidate_remote.mix_task_requests, keyed by the task id.
MIX_TASKS = (
    {"id": "index", "weight": 1, "requests": "GET /"},
    {"id": "browse_product", "weight": 10, "requests": "GET /api/products/{p}"},
    {"id": "get_recommendations", "weight": 3, "requests": "GET /api/recommendations?productIds={p}"},
    {"id": "get_ads", "weight": 3, "requests": "GET /api/data?contextKeys={c} (upstream: /api/data/)"},
    {"id": "view_cart", "weight": 3, "requests": "GET /api/cart"},
    {"id": "add_to_cart", "weight": 2, "requests": "GET /api/products/{p}; POST /api/cart {item, userId}"},
    {"id": "checkout", "weight": 1, "requests": "add_to_cart(user); POST /api/checkout {person, userId}"},
    {"id": "checkout_multi", "weight": 1, "requests": "2-4 x add_to_cart(user); POST /api/checkout {person, userId}"},
)


def build_mix() -> Dict[str, Any]:
    """The workload mix as data: what candidate_remote.mix_plan reads from every cell's timing."""
    return {
        "kind": MIX_KIND,
        "source": {
            "repository": "upstream/opentelemetry-demo 2d4661e", "locustfileSha256": UPSTREAM_LOCUSTFILE_SHA256,
            "peopleSha256": UPSTREAM_PEOPLE_SHA256,
            "dropped": (
                "flood_home (weight 5: issues get_flagd_value('loadgeneratorFloodHomepage') homepage requests, 0 at the default "
                "flag, and asks flagd on every call); the 1-10 s think time (arrival spacing replaces it); the browser "
                "(Playwright) tasks; the baggage and OTel instrumentation of the Locust process; on_start's index request"
            ),
        },
        "tasks": [dict(task) for task in MIX_TASKS],
        "cycleWeight": sum(task["weight"] for task in MIX_TASKS),
        "routes": copy.deepcopy(MIX_ROUTES),
        "products": list(MIX_PRODUCTS),
        "categories": list(MIX_CATEGORIES),
        "quantities": list(MIX_QUANTITIES),
        "multiAdds": list(MIX_MULTI_ADDS),
        "people": json.loads(MIX_PEOPLE_JSON),
        "taskOrder": (
            "smooth weighted round-robin (nginx's algorithm) over the integer task weights, ties to the earlier task; "
            "24 tasks per cycle, so every window of one cycle holds each task's weight exactly"
        ),
        "requestOrder": (
            "the tasks' requests in task order, flattened; request i is scheduled at barrier + i / rate; the last task is cut "
            "at the cell's offered count"
        ),
        "draws": (
            "every parameter is an integer from sha256(namespace NUL 'mix' NUL taskIndex NUL label) mod n (no stdlib RNG): "
            "identical on 3.9 and 3.13, a pure function of (runId or warm-up namespace, task index)"
        ),
        "journeys": (
            "a task is a journey: its requests are adjacent plan slots and run sequentially in the open loop's slots; a request "
            "that needs a predecessor's effect (POST /api/checkout needs the cart the preceding POST /api/cart filled, held in "
            "valkey under the journey's userId) is dispatched at max(its slot, the predecessor's end), is sent even if the "
            "predecessor failed (upstream's behaviour; no row is skipped, so every offered token is witnessed), and records its "
            "predecessor (dependsOn) in its row"
        ),
        "sessions": (
            "userId = 'u' + first 24 hex of sha256(namespace NUL 'mix' NUL taskIndex NUL 'user'), one per journey, so carts "
            "never mix across journeys (upstream uses uuid1 per journey); GET /api/cart sends no sessionId, as upstream"
        ),
        "propagation": (
            "every request carries traceparent 00-<trace id>-<span id>-01 and x-obsplacement-request-token, one trace per "
            "request, the offpath identity rule (candidate_remote.request_identity); the upstream loadgenerator is removed"
        ),
        "requestShares": (
            "per 24 tasks (34 requests with multiAdds' mean of 3): GET /api/products 16 (47 %), POST /api/cart 6 (17.6 %), "
            "recommendations, ads and view-cart 3 each (8.8 %), POST /api/checkout 2 (5.9 %), GET / 1 (2.9 %) (DESIGN.md 2.3)"
        ),
    }


MIX = build_mix()

# ---------------------------------------------------------------- parameters
POSTURES = repeat_c.POSTURES                          # ("full",)
NO_FAULT_REGIME = repeat_c.NO_FAULT_REGIME            # "no-fault-calibration"
FRONTEND_PAUSE_REGIME = "frontend-pause-effect"
FRAUD_PAUSE_REGIME = "fraud-pause-effect"
ACCOUNTING_PAUSE_REGIME = "accounting-pause-effect"
REGIME_OF_FAULT = {
    "fraud-pause": FRAUD_PAUSE_REGIME, "accounting-pause": ACCOUNTING_PAUSE_REGIME, "frontend-pause": FRONTEND_PAUSE_REGIME,
}
OFF_PATH_FAULTS = ("fraud-pause", "accounting-pause")

# ================================================================ THE PARAMETERS
# This epoch has ONE prepared variant (F's, which is E's rate and fault set: 25 req/s of the whole mix, all three faults, two no-fault cells), so the three lines below are pinned,
# not switches: a value outside ALLOWED_* is refused at import (fail closed) and the descriptor digest of the one allowed variant is pinned
# in EXPECTED_DESCRIPTOR_SHA256_BY_VARIANT below.  NO_FAULT_CELLS_PER_BLOCK is F's (BUDGET_F change 4, engineering default; E had 1), kept.
RATE = 25.0
KEPT_FAULTS = ("fraud-pause", "accounting-pause", "frontend-pause")
NO_FAULT_CELLS_PER_BLOCK = 2
# ================================================================

ALLOWED_RATES = (25.0,)
ALLOWED_KEPT_FAULTS = (("fraud-pause", "accounting-pause", "frontend-pause"),)
ALLOWED_NO_FAULT_CELLS_PER_BLOCK = (2,)


def check_parameters(rate: Any, kept: Any, no_fault_cells: Any = NO_FAULT_CELLS_PER_BLOCK) -> None:
    if isinstance(rate, bool) or not isinstance(rate, float) or rate not in ALLOWED_RATES:
        raise ProtocolError("RATE %r is not one of %r" % (rate, ALLOWED_RATES))
    if not isinstance(kept, tuple) or kept not in ALLOWED_KEPT_FAULTS:
        raise ProtocolError("KEPT_FAULTS %r is not one of the prepared fault sets %r" % (kept, ALLOWED_KEPT_FAULTS))
    if isinstance(no_fault_cells, bool) or not isinstance(no_fault_cells, int) or no_fault_cells not in ALLOWED_NO_FAULT_CELLS_PER_BLOCK:
        raise ProtocolError(
            "NO_FAULT_CELLS_PER_BLOCK %r is not one of %r" % (no_fault_cells, ALLOWED_NO_FAULT_CELLS_PER_BLOCK)
        )


check_parameters(RATE, KEPT_FAULTS, NO_FAULT_CELLS_PER_BLOCK)
RATES = (RATE,)                                       # one rate per campaign; the tuple keeps v2's name for the shared code
REGIMES = (NO_FAULT_REGIME,) + tuple(REGIME_OF_FAULT[fault] for fault in KEPT_FAULTS)
FAULTS = {NO_FAULT_REGIME: None, **{REGIME_OF_FAULT[fault]: fault for fault in KEPT_FAULTS}}
_ALL_ARTIFACT_ROOTS = {
    NO_FAULT_REGIME: repeat_c.ARTIFACT_ROOTS[NO_FAULT_REGIME],
    FRONTEND_PAUSE_REGIME: repeat_c.ARTIFACT_ROOTS[FRONTEND_PAUSE_REGIME],
    FRAUD_PAUSE_REGIME: "effect/fraud-pause",
    ACCOUNTING_PAUSE_REGIME: "effect/accounting-pause",
}
ARTIFACT_ROOTS = {regime: _ALL_ARTIFACT_ROOTS[regime] for regime in REGIMES}
# The regime whose compiled cell timing a pause of another service reuses: C's timing names no scenario, only
# ``faultApplied``, and the pause mechanism is the frontend pause's.
TIMING_TEMPLATE_REGIME = {
    FRAUD_PAUSE_REGIME: FRONTEND_PAUSE_REGIME, ACCOUNTING_PAUSE_REGIME: FRONTEND_PAUSE_REGIME,
}
_ALL_SCENARIOS = copy.deepcopy(repeat_c.SCENARIOS)
del _ALL_SCENARIOS["productcatalog-cpu-throttle"]                    # dropped (decision 108)
_ALL_SCENARIOS["fraud-pause"] = {
    "service": "frauddetectionservice", "action": "pause",
    "applyCommand": "docker compose pause frauddetectionservice",
    "revertCommand": "docker compose unpause frauddetectionservice",
    "duringPredicate": "running-and-paused",
    "entryRouteDuringFault": repeat_c.ENTRY_ROUTE_DURING_FAULT,
}
_ALL_SCENARIOS["accounting-pause"] = {
    "service": "accountingservice", "action": "pause",
    "applyCommand": "docker compose pause accountingservice",
    "revertCommand": "docker compose unpause accountingservice",
    "duringPredicate": "running-and-paused",
    "entryRouteDuringFault": repeat_c.ENTRY_ROUTE_DURING_FAULT,
}
SCENARIOS = {name: _ALL_SCENARIOS[name] for name in sorted(KEPT_FAULTS)}      # only the kept faults are in the descriptor
# Decision 100: 5 blocks, blocks 1-3 training, blocks 4-5 test (the split is declared in the descriptor and in the plan).
BLOCKS = 5
TRAINING_BLOCKS = (1, 2, 3)
TEST_BLOCKS = (4, 5)
ONSET_STRATA = BLOCKS                                 # campaign C's rule: per (regime, rate) one stratum per block, in a seeded order
# Engineering default recorded in the declaration: the build date (F used 20261014); the epoch id alone already makes every draw differ.
SCHEDULE_SEED = 20261015
ONSET_PHASE_OFFSET = repeat_c.ONSET_PHASE_OFFSET
DURING_FAULT_PROBE = repeat_c.DURING_FAULT_PROBE      # H10: False
FREEZE_STAMPS = repeat_c.FREEZE_STAMPS                # H4: True
REQUEST_TIMEOUT_SECONDS = sweep.REQUEST_TIMEOUT_SECONDS
# The sweep's open-loop rule (research/load-generator/DESIGN.md L1) at this campaign's rate: ceil(2 x RATE x 15) (750 at 25 req/s, 1500
# at 50) for every cell.  A journey's dependent request waits for its predecessor inside a worker, bounded by the timeout, so the 2x margin
# also covers the waiting workers.
CONCURRENCY = int(math.ceil(sweep.CONCURRENCY_MARGIN * RATE * REQUEST_TIMEOUT_SECONDS))
GENERATOR_FILE_RESERVE = 1024
GENERATOR_OPEN_FILES_MINIMUM = CONCURRENCY + GENERATOR_FILE_RESERVE
# The sweep's frontendproxy rule (0.3 MB per waiting request at rate x timeout waiting requests: 112.5 MB at 25 req/s, 225 MB at 50),
# rounded up to a power of two as v2 did (225 MB -> 256 MiB), with a floor at C's own 256 MiB: the literal rule gives 128 MiB at 25 req/s,
# which is below the 256 MiB the sweep ran at 10 req/s (90 MB at its 300-request worker cap) and the 256 MiB pilot v2's 25 req/s frontend pause
# runs at.  Recorded as an engineering default; the descriptor states both numbers.
FRONTENDPROXY_BYTES_PER_WAITING_REQUEST = 300 * 1000
FRONTENDPROXY_MEMORY_FLOOR_BYTES = 256 * 1024 * 1024
FRONTENDPROXY_RULE_BYTES = int(math.ceil(FRONTENDPROXY_BYTES_PER_WAITING_REQUEST * RATE * REQUEST_TIMEOUT_SECONDS))
FRONTENDPROXY_RULE_POWER_OF_TWO_BYTES = 1 << (FRONTENDPROXY_RULE_BYTES - 1).bit_length()
FRONTENDPROXY_MEMORY_LIMIT_BYTES = max(FRONTENDPROXY_MEMORY_FLOOR_BYTES, FRONTENDPROXY_RULE_POWER_OF_TWO_BYTES)
# User decision 2026-10-12 (decision 103): the telemetry backend, and only it, gets 1 GiB: otelcol (upstream 200M, no memory_limiter, the
# debug exporter prints every span) and jaeger (upstream 400M, holds traces in memory).  Every SUT service limit stays upstream's.  Applied
# by `docker update --memory` like frontendproxy's.
TELEMETRY_BACKEND_MEMORY_LIMIT_BYTES = {"otelcol": 1024 * 1024 * 1024, "jaeger": 1024 * 1024 * 1024}
UPSTREAM_TELEMETRY_BACKEND_LIMITS = {"otelcol": "209715200 bytes (200M; upstream docker-compose.yml)", "jaeger": "419430400 bytes (400M; upstream docker-compose.yml)"}
SERVICE_MEMORY_LIMIT_BYTES = {"frontendproxy": FRONTENDPROXY_MEMORY_LIMIT_BYTES, **TELEMETRY_BACKEND_MEMORY_LIMIT_BYTES}
# Wall budget (engineering defaults, v2's): 300 s of overhead per cell on top of the 211 timed seconds (the load pilot's measured tail at 50
# req/s of one route was 142.2-150.0 s; the mix's collector log and capture are larger).  Pilot v2's own measured tails may refine this
# before launch; it is not one of the two parameters.
CELL_OVERHEAD_SECONDS = 300
TIMED_SECONDS_PER_CELL = sweep.TIMED_SECONDS_PER_CELL                # 211: warm-up 30 + barrier lead 1 + measurement 180
CELL_PERIOD_ESTIMATE_SECONDS = TIMED_SECONDS_PER_CELL + CELL_OVERHEAD_SECONDS
CELL_DEADLINE_RESERVE_SECONDS = repeat_c.CELL_DEADLINE_RESERVE_SECONDS
CLEANUP_RESERVE_SECONDS = repeat_c.CLEANUP_RESERVE_SECONDS
APPROVAL_TO_FIRST_MUTATION_SECONDS = repeat_c.APPROVAL_TO_FIRST_MUTATION_SECONDS
MEASURED_TAIL_SECONDS = {
    "source": "otel-load-pilot-v1 attempt 1 (fb14srv6, 2026-10-12), request-ledger endedAtEpoch to the next cell's barrierEpoch, 5 gaps",
    "r50Minimum": 142.2, "r50Maximum": 150.0, "r100Minimum": 158.7, "r100Maximum": 167.4,
}
DECLARATION = (
    "research/traffic-sweep/DECLARATION_F_NOLAG_OTEL.md (measurement repo; frozen and committed alone before the first cell; not yet written)"
)
AMENDMENTS: List[str] = []
AUTHORITY = (
    "main repo research/traffic-sweep/BUDGET_OVERNIGHT_20261014.md item 2 (user, 2026-10-14 ~14:45Z, committed alone before this work): campaign F's "
    "design (BUDGET_F.md db3be09, PLAN_LANES_20261014.md c2914de: the upstream Locust task mix as an open loop at 25 req/s, off-path faults on "
    "frauddetectionservice and accountingservice with the frontend pause as the on-path control, 5 blocks, blocks 1-3 training and 4-5 test, two "
    "no-fault cells per block, SDK metric export interval and spanmetrics flush at 5 s) without the collector's kafkametrics receiver, its "
    "resource/kafka processor, its metrics/kafka pipeline and otelcol's wait for kafka; campaign C's decisions 25, 56, 66 and 69 and pilot v2's "
    "sizing carried over unchanged"
)
# The pilot's criteria fields are v2's byte for byte (the same defaults object): F re-uses them as the definition of 'manifests' in its
# own descriptor, never as a gate (a cell is valid or blocked by the harness's gates; the verdict is the analysis's).
MANIFESTATION_CRITERION = (
    "per fault and rate, one cell: the frontend pause manifests if at least 90 % of the requests scheduled in the first 45 s of the hold fail and "
    "checkout requests sent in them (by send time) succeed in at most 10 % of cases (the pause command takes a moment to bite); an off-path pause manifests if the target service's consumer-side "
    "spans started in the hold number at most 10 % of those started in the pre-onset 60 s AND checkout requests scheduled in "
    "the hold keep succeeding (at least 95 % ok); in every case the rate's no-fault cell shows neither the effect nor the failure, and a valid no-fault cell that fails its "
    "precondition (checkout rows and all rows >= 95 % ok in its pseudo window) makes the verdict '—' for that rate"
)
MANIFESTATION_CRITERION_DEFAULTS = {
    "unit": "one cell per (fault, rate); a verdict is per (fault, rate); a fault is kept for campaign F-nolag iff it manifests at >= 1 rate",
    "validCell": (
        "a cell counts iff its host receipt says valid and an offline validate_cell replay of it passes (the witness check runs "
        "only in the terminal); the no-fault cell of the rate must be valid too, else the verdict is '—'"
    ),
    "spanSelection": "by span start time; all spans regardless of status; spans from otelcol.log (Start time, UTC)",
    "onset": (
        "fault cells: intervention.json freeze.commandIssuedOffsetSeconds (= actualOnsetMonotonicOffsetSeconds, pre-command), "
        "mapped to wall clock with request-ledger.json barrierEpoch; no-fault cell: its pseudo onset, "
        "timing.scoredWindowSeconds[0]"
    ),
    "preOnsetSegment": "[onset - 60 s, onset)",
    "hold": "[onset, onset + 60 s)",
    "minimumSpans": "a segment with fewer than 20 spans of the statistic gives '—' for that statistic",
    "frontendPause": (
        "ledger rows scheduled in [onset, onset + 45 s) (the hold minus the client timeout of 15 s: a request scheduled later "
        "can be served after the unpause inside its own timeout; request-ledger.json, every route): the share with outcome ok is "
        "<= 10 %, and the checkout rows (route=checkout) SENT in it (startedAtEpoch - barrierEpoch in [onset, onset + 45 s), because a "
        "checkout waits for its cart POST and can leave its slot by up to 20 s) succeed in <= 10 % (the first requests before the pause bites succeed); the no-fault cell's rows in the "
        "same window at its pseudo onset succeed in >= 95 % (each share needs >= 20 rows, else '—')"
    ),
    "offPathPause": (
        "consumer-side spans of the target service: service.name = the target (frauddetectionservice or accountingservice) and "
        "Kind=Consumer; count started in the hold <= 10 % of the count started in the pre-onset 60 s (pre-onset count >= 20, else "
        "'—'); AND checkout rows (route=checkout) scheduled in the hold: outcome ok >= 95 % (and >= 20 rows, else '—'); AND the "
        "no-fault cell at its pseudo onset has a hold/pre-onset count ratio > 10 % and its checkout rows >= 95 % ok"
    ),
    "noFaultCell": "the same statistics at its pseudo onset must show neither the effect nor the failure",
    "noFaultPrecondition": (
        "a valid no-fault cell must itself be healthy in its pseudo hold [onset, onset + 60 s): checkout rows (route=checkout, "
        "scheduled in it) >= 95 % ok and all rows >= 95 % ok, each with >= 20 rows; if it is not, the verdict of every fault at that "
        "rate is '—' (the fault's effect cannot be told from a baseline that already fails), not 'does not manifest'; this is a "
        "property of the cell, reported with the numbers"
    ),
    "verdict": "manifests / does not manifest / '—' (a statistic below its minimum, an invalid cell, an invalid no-fault cell, or a no-fault cell that fails its precondition, at that rate)",
}
# ---------------------------------------------------------------- the telemetry cadence (F's changes 1 and 2; F's change 3, kafkametrics, is the one removed)
METRIC_EXPORT_INTERVAL_NOTE = (
    "set: OTEL_METRIC_EXPORT_INTERVAL=5000 for every service that carries OTEL_METRICS_EXPORTER in the posture overlay (18 of the catalog's 19, not frontendproxy; materialize.py renders it into compose.candidate-postures.yml for "
    "this epoch only); the SDKs that honour it are listed in collection.telemetryCadence.sdkCoverage, the others keep their own 60 s "
    "(or, flagd, 2 s) cadence; an emission change relative to campaigns B, C, the pilots and E, and the same as campaign F's (declared)"
)
SDK_METRIC_EXPORT_INTERVAL_MILLISECONDS = 5000        # OTEL_METRIC_EXPORT_INTERVAL on the 18 services with an OTEL_METRICS_EXPORTER line (materialize.py renders it)
SPANMETRICS_FLUSH_INTERVAL = "5s"                      # connectors.spanmetrics.metrics_flush_interval (collector 0.108 default 60 s)
# The ablation, as the descriptor records it (design.ablation): what is removed relative to F, and what is asserted to stay.
ABLATION_REMOVED = (
    "receivers.kafkametrics (brokers kafka:9092, scrapers consumers, collection_interval 5s)",
    "processors.resource/kafka (service.name upsert kafka)",
    "pipelines.metrics/kafka (kafkametrics -> resource/kafka, batch -> debug)",
    "otelcol depends_on kafka service_healthy",
)
ABLATION_KEPT = (
    "OTEL_METRIC_EXPORT_INTERVAL=5000 on the 18 services with an OTEL_METRICS_EXPORTER line",
    "connectors.spanmetrics.metrics_flush_interval 5s",
    "two no-fault cells per block, 25 cells, rate 25 req/s, kept faults, 5 blocks and the 1-3 / 4-5 split",
    "sizing, gates, posture full, collector log sampler off, frontendproxy log retention",
)
# Which SDKs honour OTEL_METRIC_EXPORT_INTERVAL in the pinned demo (1.12.0 images, upstream 2d4661e), by service.  ``honours``: yes / no /
# not-applicable (no SDK metrics) / unverified.  ``basis`` names what was read.  Read 2026-10-14 (WebFetch of the SDK source at the pinned
# version, and the demo's own code in this checkout); nothing here was observed on a running stack.
SDK_COVERAGE = (
    {"language": "Java (agent)", "services": ["adservice", "frauddetectionservice", "kafka"], "honours": "yes",
     "basis": "autoconfigure property otel.metric.export.interval (spec-compliance-matrix: Java +); the agent builds the reader, the demo sets none"},
    {"language": "PHP", "services": ["quoteservice"], "honours": "yes",
     "basis": "upstream src/quoteservice/public/index.php:71 reads Variables::OTEL_METRIC_EXPORT_INTERVAL for its flush timer"},
    {"language": "Go (otel-go sdk/metric v1.27.0)", "services": ["checkoutservice", "productcatalogservice"], "honours": "yes",
     "basis": "periodic_reader.go newPeriodicReaderConfig: interval = envDuration(envInterval, 60 s); main.go:115 / :108 passes no WithInterval"},
    {"language": "Go (flagd v0.11.2)", "services": ["flagd"], "honours": "no",
     "basis": "core/pkg/telemetry/builder.go passes WithInterval(2 s) (a package constant), which overrides the variable; flagd already exports every 2 s"},
    {"language": "Python (sdk 1.25.0)", "services": ["recommendationservice", "loadgenerator"], "honours": "yes",
     "basis": "PeriodicExportingMetricReader.__init__: export_interval_millis None -> environ.get(OTEL_METRIC_EXPORT_INTERVAL, 60000); the demo passes none"},
    {"language": ".NET (OpenTelemetry 1.9.0)", "services": ["cartservice"], "honours": "yes",
     "basis": "PeriodicExportingMetricReaderOptions reads OTEL_METRIC_EXPORT_INTERVAL (OTelMetricExportIntervalEnvVarKey); cartservice Program.cs uses AddOtlpExporter()"},
    {"language": ".NET (OpenTelemetry.AutoInstrumentation 1.8.0)", "services": ["accountingservice"], "honours": "unverified",
     "basis": "same SDK code path as cartservice, but the version the auto-instrumentation bundles was not read; the spec-compliance matrix marks .NET +"},
    {"language": "Node.js (sdk-metrics 1.24.1 / 1.25.1, NodeSDK 0.51.1 / 0.52.1)", "services": ["frontend", "paymentservice"], "honours": "no",
     "basis": "PeriodicExportingMetricReader: exportIntervalMillis ?? 60000, reads no environment; the demo builds the reader with the exporter only (opentelemetry.js:25, Instrumentation.js:25), so its interval is 60 s"},
    {"language": "C++ (opentelemetry-cpp 1.15.0)", "services": ["currencyservice"], "honours": "no",
     "basis": "PeriodicExportingMetricReaderOptions default is 60000 ms and reads no environment; currencyservice/src/meter_common.h:26 uses the default options"},
    {"language": "Rust (opentelemetry 0.22, feature trace only)", "services": ["shippingservice"], "honours": "not-applicable",
     "basis": "Cargo.toml enables only the trace feature; no metrics SDK"},
    {"language": "Ruby (opentelemetry-sdk 1.4.1)", "services": ["emailservice"], "honours": "not-applicable",
     "basis": "Gemfile has no metrics SDK gem and email_server.rb records no metrics (read in this checkout)"},
    {"language": "Node.js (Next.js, @vercel/otel)", "services": ["flagd-ui"], "honours": "unverified",
     "basis": "src/instrumentation.ts only calls registerOTel({serviceName}); whether @vercel/otel builds a metric reader, and from this variable, was not read"},
    {"language": "nginx otel module", "services": ["imageprovider"], "honours": "not-applicable", "basis": "nginx.conf.template configures otel_trace only"},
    {"language": "Envoy", "services": ["frontendproxy"], "honours": "not-applicable", "basis": "envoy.tmpl.yaml configures the opentelemetry tracer only"},
)


# ---------------------------------------------------------------- derived

CELLS_PER_BLOCK = NO_FAULT_CELLS_PER_BLOCK + len(KEPT_FAULTS)                 # 2 + 3
TOTAL_RUNS = BLOCKS * CELLS_PER_BLOCK                                          # 25
MINIMUM_REMAINING_SECONDS = (
    TOTAL_RUNS * CELL_PERIOD_ESTIMATE_SECONDS + CELL_DEADLINE_RESERVE_SECONDS + CLEANUP_RESERVE_SECONDS
)
RUN_WINDOW_HOURS = int(math.ceil((MINIMUM_REMAINING_SECONDS + APPROVAL_TO_FIRST_MUTATION_SECONDS) / 3600.0))
# The four timing keys that follow from the onset draw, and the four this epoch sizes itself; every other key of a cell is C's
# value for the same (regime, rate) (tested key by key).  ``generatorOpenFilesMinimum`` and ``workloadMix`` are new.
ONSET_TIMING_KEYS = repeat_c.ONSET_TIMING_KEYS
SIZED_TIMING_KEYS = frozenset({
    "concurrency", "planRunCount", "planMinimumRemainingSeconds", "serviceMemoryLimitBytes",
})
REPLACED_TIMING_KEYS = ONSET_TIMING_KEYS | SIZED_TIMING_KEYS
NEW_TIMING_KEYS = frozenset({"generatorOpenFilesMinimum", "workloadMix"})
# The descriptor keys this epoch replaces in C's descriptor; everything else is C's, byte for byte (tested).
REPLACED_DESCRIPTOR_KEYS = frozenset({
    "id", "declaration", "amendments", "schedule", "derivedFrom", "design", "outcomes", "sutDeviations", "faultDesign",
    "groundTruth",
})
REPLACED_DESCRIPTOR_SUBKEYS = {
    "timing": frozenset({
        "budget", "faultOnsetStrata", "offeredByRate", "generatorOpenFilesMinimum", "workloadMix", "metricExportIntervalMilliseconds",
        "metricExportIntervalNote",
    }),
    "workload": frozenset({
        "kind", "concurrency", "concurrencyRule", "requestsPerSecondLevels", "generatorOpenFiles", "mix", "ledger", "warmup",
        "arrivals", "readiness", "traceContext", "routeServices", "routeDerivation", "probeRoute",
    }),
    "analysis": frozenset({
        "comparativeUnit", "analysisFreeze", "manifestationCriterion", "manifestationCriterionDefaults", "traceCompleteness",
        "split", "passRule", "calibration",
    }),
    "collection": frozenset({"requestWitness", "telemetryCadence"}),
}
# The reviewed canonical descriptor digest of each prepared variant (rate, kept faults), computed by this generator and pinned here so
# that setting the two parameters needs no further pin edit: a variant outside this table cannot be loaded.
EXPECTED_DESCRIPTOR_SHA256_BY_VARIANT: Dict[Any, str] = {
    (25.0, ('fraud-pause', 'accounting-pause', 'frontend-pause')): 'a65f4e33ae7698cfc6bd43829857bfda02030af546e712a471687031f1ca4dd8',
}
EXPECTED_DESCRIPTOR_SHA256 = EXPECTED_DESCRIPTOR_SHA256_BY_VARIANT.get((RATE, KEPT_FAULTS))


def mix_route_services() -> List[str]:
    """Every service some route of the mix is guaranteed to reach, sorted (the runtime derives the same list from the cell's timing,
    whose JSON keys are sorted, so the order must not depend on the routes' order)."""
    return sorted({service for route in MIX["routes"].values() for service in route["requiredServices"]})


def replicates_of(regime: str) -> int:
    """Cells of one regime in one block: the no-fault regime has NO_FAULT_CELLS_PER_BLOCK, every other one cell."""
    return NO_FAULT_CELLS_PER_BLOCK if regime == NO_FAULT_REGIME else 1


def onset_phase_offset(regime: str, rate: float, block: int, replicate: int = 1) -> float:
    """Campaign C's strata rule over this epoch's blocks: per (regime, rate) the BLOCKS blocks take the BLOCKS strata of one inter-arrival
    in a seeded order, uniform inside the stratum (the no-fault cell's pseudo onset included).  A second no-fault cell takes its own
    permutation of the strata (the draw's regime label carries the replicate), so each replicate covers the 5 strata once over the blocks;
    replicate 1 uses the regime id itself, as every other cell."""
    if ONSET_PHASE_OFFSET != "seeded-stratified-within-one-inter-arrival":
        raise ProtocolError("campaign F-nolag keeps the sweep's seeded onset rule")
    if not 1 <= int(block) <= BLOCKS:
        raise ProtocolError("block %r is outside 1..%d" % (block, BLOCKS))
    if not 1 <= int(replicate) <= replicates_of(regime):
        raise ProtocolError("replicate %r is outside 1..%d for regime %r" % (replicate, replicates_of(regime), regime))
    label = regime if int(replicate) == 1 else "%s#replicate-%d" % (regime, int(replicate))
    return quiet.stratified_onset_offset(SCHEDULE_SEED, EPOCH, ONSET_STRATA, label, rate, block)


def block_split(block: int) -> str:
    check_split()
    if int(block) in TRAINING_BLOCKS:
        return "training"
    if int(block) in TEST_BLOCKS:
        return "test"
    raise ProtocolError("block %r is outside 1..%d" % (block, BLOCKS))


def check_split() -> None:
    """The split partitions the blocks: every block is training or test, none both."""
    if sorted(TRAINING_BLOCKS + TEST_BLOCKS) != list(range(1, BLOCKS + 1)):
        raise ProtocolError("training blocks %r and test blocks %r do not partition blocks 1..%d" % (TRAINING_BLOCKS, TEST_BLOCKS, BLOCKS))


def split_record() -> Dict[str, Any]:
    check_split()
    return {
        "trainingBlocks": list(TRAINING_BLOCKS),
        "testBlocks": list(TEST_BLOCKS),
        "rule": (
            "decision 100 (user 2026-10-12): 5 blocks; the placement is solved on blocks 1-3, frozen with the pass rule, and scored once "
            "on blocks 4-5; the detectors that score the test blocks are calibrated on the training blocks only (decision 102)"
        ),
        "declaredBeforeLaunch": True,
    }


# Run order inside a block (E's group order, per block): the no-fault cells first (two in F; a seeded Fisher-Yates draw orders the two like
# any group of more than one), then the kept off-path pauses in a seeded order (one Fisher-Yates draw per block), then the frontend pause
# (the on-path control) last.  There is no lead cell (E has none).  A group with no kept member is empty.
ORDER_GROUPS = (
    (NO_FAULT_REGIME,),
    (FRAUD_PAUSE_REGIME, ACCOUNTING_PAUSE_REGIME),
    (FRONTEND_PAUSE_REGIME,),
)
GROUP_OF = {regime: index for index, group in enumerate(ORDER_GROUPS) for regime in group}


def block_cells(block: int) -> List[Dict[str, Any]]:
    """The cells of one block (1-based), in a fixed declaration order (REGIMES order)."""
    if not 1 <= int(block) <= BLOCKS:
        raise ProtocolError("block %r is outside 1..%d" % (block, BLOCKS))
    return [
        {"regime": regime, "rate": float(RATE), "block": int(block), "replicate": replicate}
        for regime in REGIMES for replicate in range(1, replicates_of(regime) + 1)
    ]


def block_order(block: int) -> List[Dict[str, Any]]:
    """The block's cells group by group; the kept off-path pauses are Fisher-Yates shuffled by SHA-256 draws keyed by seed, epoch and block
    (the quiet compiler's ``fisher_yates`` with this epoch's context and the group number; the block number is its block argument)."""
    if sorted(GROUP_OF) != sorted(_ALL_ARTIFACT_ROOTS):
        raise ProtocolError("the order groups do not cover the regimes exactly once")
    cells = block_cells(block)
    order: List[Dict[str, Any]] = []
    for index in range(len(ORDER_GROUPS)):
        members = [row for row in cells if GROUP_OF[row["regime"]] == index]
        if len(members) > 1:
            members = quiet.fisher_yates(members, SCHEDULE_SEED, EPOCH, int(block), "%s-group%d" % (SCHEDULE_CONTEXT, index))
        order += members
    return order


def cell_label(row: Mapping[str, Any]) -> str:
    return "%s@r%s#b%d#n%d" % (row["regime"], rate_token(row["rate"]), int(row["block"]), int(row["replicate"]))


def cell_timing(regime: str, rate: float, block: int, replicate: int = 1) -> Dict[str, Any]:
    """C's cell timing for (regime, rate) at the campaign rate, with this epoch's onset draw (C's strata rule over the 5 blocks) and the
    keys that follow from it (C's formulas), the campaign's concurrency, run count, budget and frontendproxy memory limit, the generator's
    open-file minimum and the workload mix."""
    if regime not in REGIMES:
        raise ProtocolError("unknown regime %r" % (regime,))
    if float(rate) not in RATES:
        raise ProtocolError("rate %r is not the campaign rate" % (rate,))
    # C's own block argument selects only C's onset draw, which this epoch replaces: any C block gives the same other keys (tested).
    timing = repeat_c.cell_timing(TIMING_TEMPLATE_REGIME.get(regime, regime), rate, 1)
    faulted = FAULTS[regime] is not None
    if timing["faultApplied"] is not faulted:
        raise ProtocolError("C's fault/no-fault cell boundary changed")
    offset = onset_phase_offset(regime, rate, block, replicate)
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
        "workloadMix": copy.deepcopy(MIX),
    })
    return timing


def run_key_for(regime: str, rate: float, block: int, posture: str, attempt: int, replicate: int = 1) -> Dict[str, Any]:
    """E's run key plus ``replicate`` (1 for every cell but the second no-fault cell of a block, which is 2): the run ID is the hash of the
    key, and the two no-fault cells of a block share regime, rate, block and posture."""
    if not 1 <= int(replicate) <= replicates_of(regime):
        raise ProtocolError("replicate %r is outside 1..%d for regime %r" % (replicate, replicates_of(regime), regime))
    return {
        "studyEpoch": EPOCH, "regime": regime, "requestsPerSecond": float(rate),
        "block": int(block), "replicate": int(replicate), "posture": posture, "attempt": validate_attempt(attempt),
    }


def run_id_for(run_key: Mapping[str, Any]) -> str:
    return sweep.run_id_for(run_key)


def allocate_schedule() -> List[Dict[str, Any]]:
    """The design-level schedule receipt (attempt-free): per block, the cell order."""
    if POSTURES != ("full",):
        raise ProtocolError("campaign F-nolag runs the full posture only")
    if len(RATES) != 1 or not (math.isfinite(RATES[0]) and RATES[0] > 0):
        raise ProtocolError("campaign F-nolag has one finite positive rate")
    blocks = []
    for block in range(1, BLOCKS + 1):
        order = [cell_label(row) for row in block_order(block)]
        blocks.append({"block": block, "split": block_split(block), "order": order, "orderSha256": canonical_sha256(order)})
    every = [item for row in blocks for item in row["order"]]
    if len(every) != TOTAL_RUNS or len(set(every)) != TOTAL_RUNS:
        raise ProtocolError("schedule does not contain every cell exactly once")
    return blocks


def _scenario_contract(name: str) -> Dict[str, Any]:
    return {
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


def telemetry_cadence() -> Dict[str, Any]:
    """The descriptor's record of F's changes 1 and 2 (what materialize.py renders and the runtime plumbs), with the SDK coverage."""
    return {
        "sdkMetricExportIntervalMilliseconds": SDK_METRIC_EXPORT_INTERVAL_MILLISECONDS,
        "sdkMechanism": (
            "OTEL_METRIC_EXPORT_INTERVAL on every service with an OTEL_METRICS_EXPORTER line in the overlay (18 of the catalog's 19; not frontendproxy): materialize.py renders it into the materialized "
            "compose.candidate-postures.yml (after each OTEL_METRICS_EXPORTER line) as ${OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL:?candidate "
            "posture required}; candidate_runtime.posture_environment and candidate_setup.compose_environment supply the value; the repository's "
            "overlay file is unchanged, so every other epoch renders it as before"
        ),
        "sdkCoverage": copy.deepcopy(list(SDK_COVERAGE)),
        "sdkCoverageStatus": (
            "read from SDK source at the pinned versions and from the demo's own code; not observed on a running stack: whether each SDK's "
            "export cadence is 5 s is read back from the collector log's data-point timestamps by the DRY_RUN, not asserted here"
        ),
        "spanmetricsFlushInterval": SPANMETRICS_FLUSH_INTERVAL,
        "spanmetricsMechanism": "materialize.py renders connectors.spanmetrics.metrics_flush_interval into otelcol-placement.yml for this epoch only",
        "kafkametrics": None,
        "kafkametricsNote": (
            "not rendered in this epoch: the one change from otel-offpath-f-v1 (receivers.kafkametrics, processors.resource/kafka, pipelines.metrics/kafka); "
            "the consumer-group lag signal of F does not exist here; the kafka service's own Java-agent metrics are unchanged"
        ),
        "collectorStartOrder": (
            "this epoch's rendered compose.otel-placement.yml has no depends_on for otelcol (as campaign E's and the pilots'): the collector "
            "does not wait for kafka, there being no kafkametrics receiver to start against it"
        ),
    }


def ablation_record() -> Dict[str, Any]:
    """design.ablation: the one change from the design epoch (F), what it removes and what is held."""
    return {
        "designEpoch": DESIGN_EPOCH,
        "designDescriptorCanonicalSha256": DESIGN_DESCRIPTOR_SHA256,
        "change": "the collector's kafkametrics receiver, its resource/kafka processor, its metrics/kafka pipeline and otelcol's depends_on kafka are not rendered; nothing else differs from the design epoch's rendering",
        "removed": list(ABLATION_REMOVED),
        "kept": list(ABLATION_KEPT),
        "question": "does campaign F's pass hold without the lag receiver (BUDGET_OVERNIGHT_20261014.md item 2)",
        "scheduleDiffersFromDesignEpoch": "epoch id, schedule version and seed (20261015 against F's 20261014) differ, so block orders and onset strata are new draws of the same rules",
    }


def derive_f_descriptor(predecessor_path: Path = None) -> Dict[str, Any]:
    """Generate campaign F-nolag's descriptor from campaign C's pinned descriptor (as F's generator does; F's own descriptor is pinned, not read).

    This function IS the descriptor's source: the checked-in otel-offpath-f-nolag-v1.json must equal ``_pretty_bytes`` of its
    result (tested), so the file is regenerated, never hand-edited (``--emit-descriptor``).  Replaced: ``REPLACED_DESCRIPTOR_KEYS`` and
    ``REPLACED_DESCRIPTOR_SUBKEYS``; every other key is C's (H10/H4, the trace rules per cell kind
    apart from the completeness wording, protocolGates, containerHealthGuard, workflow, ...).
    """
    path = Path(predecessor_path) if predecessor_path is not None else repeat_c.DEFAULT_DESCRIPTOR
    base = repeat_c.load_descriptor(path)
    if base["id"] != PREDECESSOR_EPOCH:
        raise ProtocolError("campaign F-nolag is derived from campaign C's descriptor only")
    document = copy.deepcopy(base)
    document["id"] = EPOCH
    document["declaration"] = DECLARATION
    document["amendments"] = list(AMENDMENTS)
    design = copy.deepcopy(base["design"])
    for key in ("blockRule", "blocks", "cellsPerBlock"):
        design.pop(key)
    design.update({
        "ablation": ablation_record(),
        "purpose": (
            "campaign F-nolag (BUDGET_OVERNIGHT_20261014.md item 2): campaign F's design (E's with a 5 s metric cadence and two no-fault cells per block) "
            "without the kafkametrics lag signal, for the detection lanes; the upstream task mix as an open loop at %s req/s, 5 blocks of %d no-fault cells and one cell per kept "
            "fault (%s); blocks 1-3 train the placement, blocks 4-5 test it (decision 100)"
            % (rate_token(RATE), NO_FAULT_CELLS_PER_BLOCK, ", ".join(KEPT_FAULTS))
        ),
        "rates": list(RATES),
        "keptFaults": list(KEPT_FAULTS),
        "keptFaultsRule": (
            "campaign E's kept set, fixed by BUDGET_F: fraud-pause, accounting-pause and frontend-pause; any other set is refused at import"
        ),
        "rateRule": "campaign E's rate, fixed by BUDGET_F: 25 req/s of the whole mix; any other rate is refused at import",
        "regimes": [
            {"id": regime, "kind": "no-fault-calibration" if FAULTS[regime] is None else "effect",
             "fault": FAULTS[regime], "artifactRootClass": ARTIFACT_ROOTS[regime]}
            for regime in REGIMES
        ],
        "omittedRegimes": copy.deepcopy(base["design"]["omittedRegimes"]),
        "blocks": BLOCKS,
        "episodesPerRegimeAndRate": {regime: BLOCKS * replicates_of(regime) for regime in REGIMES},
        "noFaultCellsPerBlock": NO_FAULT_CELLS_PER_BLOCK,
        "noFaultCellsRule": (
            "BUDGET_F change 4 (kept from F; engineering default, final count declared in DECLARATION_F_NOLAG): E had one no-fault cell per block, this epoch has two; both carry the "
            "regime no-fault-calibration (the runtime keys on it) and differ by the run key's replicate (1, 2); every other cell has replicate 1; each "
            "replicate takes its own seeded permutation of the 5 onset strata over the blocks"
        ),
        "cellsPerBlock": CELLS_PER_BLOCK,
        "split": split_record(),
        "blockRule": (
            "each block holds the two no-fault cells (a seeded Fisher-Yates draw orders them), then the kept off-path pauses in a seeded "
            "Fisher-Yates order (one draw per block), then the frontend pause when it is kept; there is no lead cell; the runKey's block is the block"
        ),
        "totalRuns": TOTAL_RUNS,
        "cellShape": (
            "campaign C's cell (candidate_repeat_c.cell_timing(regime, rate, 1); a pause of frauddetectionservice or "
            "accountingservice takes the frontend pause's) at the campaign rate; only the seeded onset (C's strata rule over the 5 blocks), "
            "the slots per phase it implies, the concurrency, the plan-level run count and minimum remaining time, the frontendproxy, otelcol and "
            "jaeger memory limit, the generator's open-file minimum and the workload mix differ"
        ),
        "doses": (
            "the pauses are the frontend pause's mechanism (docker compose pause / unpause) for a hold of 60 s on the kept services; "
            "the throttle is not in F (decision 108)"
        ),
        "offPathFraming": (
            "frauddetectionservice and accountingservice consume the orders topic asynchronously in their own consumer groups; "
            "the checkout route returns without waiting for them (checkoutservice sends the message and continues), so a "
            "pause of either must not make any route unavailable"
        ),
    })
    document["design"] = design
    document["schedule"] = {
        "version": SCHEDULE_CONTEXT,
        "seed": SCHEDULE_SEED,
        "shuffle": "per-block-no-fault-cells-then-fisher-yates-over-the-kept-off-path-pauses-then-the-frontend-pause-with-sha256-draws",
        "drawEncoding": "UTF-8(seed || NUL || epoch || NUL || block-NN (NN = block number) || NUL || draw-i || NUL || version)",
        "blockOrder": "no-fault cells (2, seeded order), kept off-path pauses (seeded), frontend pause (when kept)",
        "onsetRule": (
            "campaign C's strata rule over the 5 blocks: per (regime, rate) the blocks take the 5 strata of one inter-arrival in a seeded order "
            "(quiet.stratified_onset_offset with 5 episodes), uniform inside the stratum; the no-fault cells' pseudo onsets included, the second "
            "no-fault cell with its own permutation (draw label regime#replicate-2)"
        ),
        "leadCell": None,
        "split": split_record(),
        "blocks": allocate_schedule(),
    }
    timing = copy.deepcopy(base["timing"])
    timing["faultOnsetStrata"] = ONSET_STRATA
    timing["offeredByRate"] = {rate_token(rate): offered_for(rate, timing["measurementSeconds"]) for rate in RATES}
    timing["generatorOpenFilesMinimum"] = GENERATOR_OPEN_FILES_MINIMUM
    timing["workloadMix"] = copy.deepcopy(MIX)
    timing["metricExportIntervalMilliseconds"] = SDK_METRIC_EXPORT_INTERVAL_MILLISECONDS
    timing["metricExportIntervalNote"] = METRIC_EXPORT_INTERVAL_NOTE
    timing["budget"].update({
        "cellOverheadSeconds": CELL_OVERHEAD_SECONDS,
        "cellPeriodEstimateSeconds": CELL_PERIOD_ESTIMATE_SECONDS,
        "minimumRemainingSeconds": MINIMUM_REMAINING_SECONDS,
        "runWindowHours": RUN_WINDOW_HOURS,
        "measuredTailSeconds": copy.deepcopy(MEASURED_TAIL_SECONDS),
    })
    document["timing"] = timing
    workload = copy.deepcopy(base["workload"])
    services = mix_route_services()
    workload.update({
        "kind": "multi-route-open-loop-mix",
        "probeRoute": (
            "%s %s (method and path above, services frontendproxy, frontend, productcatalogservice): the stack-readiness probe "
            "and the post-revert readiness probes only; it is not a route of the mix" % (base["workload"]["method"], base["workload"]["path"])
        ),
        "routeServices": services,
        "routeDerivation": [
            "%s %s: %s" % (route["method"], route["path"], route["derivation"]) for route in MIX["routes"].values()
        ],
        "mix": copy.deepcopy(MIX),
        "concurrency": CONCURRENCY,
        "concurrencyRule": (
            "ceil(2 x rate x request timeout) = ceil(2 x %s x 15) = %d: the worker cap covers rate x timeout with the sweep's "
            "2x margin; one thread per in-flight, waiting or scheduled-ahead request" % (rate_token(RATE), CONCURRENCY)
        ),
        "requestsPerSecondLevels": list(RATES),
        "arrivals": (
            "constant spacing (offset = sequence / rate) from the shared barrier, over the requests of the mix; the rate is "
            "the total requests per second of the whole mix"
        ),
        "generatorOpenFiles": (
            "the controller raises its RLIMIT_NOFILE soft limit to concurrency + %d = %d (never above the hard limit) "
            "before the cell starts, or refuses the cell: every in-flight request holds a socket, and an EMFILE would read "
            "as a failed request of the target" % (GENERATOR_FILE_RESERVE, GENERATOR_OPEN_FILES_MINIMUM)
        ),
        "ledger": (
            "request-ledger.json (kind otel-demo-mix-ledger-v1): one row per scheduled request with its route, task, journey, "
            "step, method, target, bodySha256 and dependsOn, scheduledOffsetSeconds, scheduledAtEpoch, "
            "startedAtEpoch/endedAtEpoch, startedMonotonic/endedMonotonic (the fault receipt's clock), status, bytes, error and "
            "outcome ok|timeout|failed; the terminal replays every row's identity, route and parameters from the plan"
        ),
        "warmup": "30 s at 10/s of the same mix (its own token namespace), never scored",
        "readiness": (
            "the harness's checkout-journey readiness (one complete journey, stack-wide) and then one request of the probe route "
            "(path above) returning 200; both carry the token readiness-not-scored and run before the warm-up; the post-revert "
            "readiness probes of a fault cell use the probe route too"
        ),
        "traceContext": MIX["propagation"],
    })
    document["workload"] = workload
    collection = copy.deepcopy(base["collection"])
    collection["requestWitness"] = (
        "frontendproxy JSON access log, unchanged; its json-file log is one unrotated segment bounded at 4g (the collector "
        "carrier's rule): a %s req/s cell writes about %d lines (~0.4 kB each, inside upstream's 5m x 2 bound of 5 to 10 MB at 50 req/s; the "
        "retention is kept as the pilots' so the materialized source is unchanged); "
        "a lost line fails the terminal's witness check; every request of the mix, POSTs included, is one witnessed token"
        % (rate_token(RATE), int(RATE * 186))
    )
    collection["telemetryCadence"] = telemetry_cadence()
    document["collection"] = collection
    document["faultDesign"] = copy.deepcopy(base["faultDesign"])
    document["faultDesign"]["scenarios"] = copy.deepcopy(SCENARIOS)
    document["faultDesign"]["metricExportIntervalMilliseconds"] = SDK_METRIC_EXPORT_INTERVAL_MILLISECONDS
    document["faultDesign"]["manifestation"] = (
        base["faultDesign"]["manifestation"]
        + ". Off-path pauses (frauddetectionservice, accountingservice) are proven by the paused container state read back and the "
        "Docker pause event, like the frontend's; whether the consumer-side effect shows in the target's spans, and that checkout "
        "requests keep succeeding, is the pilot's question, re-measured here per block (analysis.manifestationCriterion), not a harness condition"
    )
    truth = copy.deepcopy(base["groundTruth"])
    truth["fault"]["scenarioContracts"] = [_scenario_contract(name) for name in sorted(SCENARIOS)]
    path_truth = truth["path"]
    path_truth["expectedNoFaultPath"] = list(services)
    path_truth["expectedNoFaultPathByRoute"] = {
        route_id: list(route["requiredServices"]) for route_id, route in MIX["routes"].items()
    }
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
    deviations = []
    for row in base["sutDeviations"]:
        row = copy.deepcopy(row)
        if row["service"] == "frontendproxy" and row["setting"] == "memory limit (HostConfig.Memory)":
            row["pilot"] = "%d bytes (%d MiB)" % (FRONTENDPROXY_MEMORY_LIMIT_BYTES, FRONTENDPROXY_MEMORY_LIMIT_BYTES // 1024 ** 2)
            row["pilotRule"] = (
                "the sweep's rule (0.3 MB per waiting request, twice the cost the attempt-1 kill implies) at rate x timeout = "
                "%s x 15 = %d waiting requests = %d bytes, rounded up to a power of two (%d bytes) with a floor at C's own 256 MiB (%d bytes)"
                % (rate_token(RATE), int(RATE * 15), FRONTENDPROXY_RULE_BYTES, FRONTENDPROXY_RULE_POWER_OF_TWO_BYTES,
                   FRONTENDPROXY_MEMORY_FLOOR_BYTES)
            )
            row["scope"] = "campaign F-nolag's cells (as F's and E's); C's epoch and every frozen epoch keep their limit"
        deviations.append(row)
    for service, limit in sorted(TELEMETRY_BACKEND_MEMORY_LIMIT_BYTES.items()):
        deviations.append({
            "service": service,
            "setting": "memory limit (HostConfig.Memory)",
            "upstream": UPSTREAM_TELEMETRY_BACKEND_LIMITS[service],
            "pilot": "%d bytes (1 GiB)" % limit,
            "mechanism": (
                "docker update --memory <bytes> --memory-swap <same ratio as before> on the running container, right after compose "
                "up and before readiness; verified by inspect and recorded in container-health.json (the frontendproxy's mechanism)"
            ),
            "reason": (
                "telemetry backend, not a SUT service (user decision 2026-10-12, decision 103): at 25 to 50 req/s of the mix the collector's debug "
                "exporter prints every span (a few thousand per second, no memory_limiter in its config) and jaeger holds the "
                "traces in memory; an OOM kill of either would invalidate the cell (container-health guard)"
            ),
            "scope": "campaign F-nolag's cells (as F's and E's) only; every SUT service limit stays upstream's; C's epoch and every frozen epoch keep upstream's",
        })
    deviations.append({
        "service": "frontendproxy",
        "setting": "json-file log rotation",
        "upstream": "max-size 5m, max-file 2 (x-default-logging)",
        "pilot": "max-size 4g, max-file 1 (the collector carrier's rule, compose.otel-placement.yml)",
        "mechanism": "materialize.py renders it into the materialized compose.otel-placement.yml when the selector names the epoch",
        "reason": (
            "the request witness is the frontendproxy access log; at 50 req/s a cell writes ~3.7 MB of it (estimated), inside "
            "upstream's bound; kept as the pilots' so the materialized source is unchanged"
        ),
        "scope": "the load pilot's, the off-path pilots', campaign E's, campaign F's and campaign F-nolag's materialized source; every other epoch renders the overlay byte for byte",
    })
    deviations.append({
        "service": "the 18 catalog services with an OTEL_METRICS_EXPORTER line in the posture overlay (not frontendproxy)",
        "setting": "OTEL_METRIC_EXPORT_INTERVAL",
        "upstream": "not set (every SDK keeps its own cadence, 60 s for the Java, Go, Python, PHP, .NET, Node.js and C++ SDKs)",
        "pilot": "5000 ms",
        "mechanism": "materialize.py renders it into the materialized compose.candidate-postures.yml for this epoch only",
        "reason": "BUDGET_F change 1 (kept from F): a 5 s metric cadence so consumer-group and request-rate signals have enough points per window for the lanes",
        "scope": "campaign F's and campaign F-nolag's cells only; honoured only by the SDKs in collection.telemetryCadence.sdkCoverage",
    })
    deviations.append({
        "service": "otelcol",
        "setting": "connectors.spanmetrics.metrics_flush_interval",
        "upstream": "not set (collector 0.108 default)",
        "pilot": SPANMETRICS_FLUSH_INTERVAL,
        "mechanism": "materialize.py renders it into the materialized otelcol-placement.yml for this epoch only",
        "reason": "BUDGET_F change 2 (kept from F): 5 s span-derived metrics (calls, duration) for the lanes",
        "scope": "campaign F's and campaign F-nolag's cells only",
    })
    document["sutDeviations"] = deviations
    document["outcomes"] = {
        "primary": (
            "per detection lane (own silence, coordinator side; the consumer-group lag lane has no kafkametrics signal in this epoch) and off-path class "
            "(frauddetectionservice pause, accountingservice pause): the manifestation and prediction text of DECLARATION_F_NOLAG_OTEL.md, scored on the test blocks; "
            "on-path cells are reported without a verdict"
        ),
        "secondary": (
            "per cell: request outcomes and latency by route over pre-onset, hold and post-revert; the target's consumer-side "
            "spans per second; productcatalogservice and frontend CPU; the dependency waits of the checkout journeys; per block the "
            "manifestation statistics of the pilot's criterion"
        ),
        "costRegimeOnly": None,
        "offeredRequestsAreDenominator": True,
        "windowMembership": "monotonic-shared-barrier",
    }
    analysis = copy.deepcopy(base["analysis"])
    analysis.update({
        "comparativeUnit": (
            "(off-path class and lane); 5 blocks of two no-fault cells and one cell per kept fault at one rate; the placement is solved on blocks 1-3 "
            "and scored once on blocks 4-5"
        ),
        "analysisFreeze": (
            "no F-nolag cell is read (validity fields only) before reader v3.3, the training placement and the pass rule are frozen by digest "
            "(BUDGET_OVERNIGHT_20261014.md stop rule 4); the test blocks are then read only through the frozen placement"
        ),
        "manifestationCriterion": MANIFESTATION_CRITERION,
        "manifestationCriterionDefaults": copy.deepcopy(MANIFESTATION_CRITERION_DEFAULTS),
        "split": split_record(),
        "passRule": (
            "not set by the harness: the pass rule is frozen in DECLARATION_F_NOLAG_OTEL.md before launch; campaign F's rule is the reference, "
            "not carried over by this descriptor"
        ),
        "calibration": (
            "decision 102 (user 2026-10-12): the detectors that score the test blocks are calibrated on the training blocks (1-3) only and "
            "applied unchanged to the test blocks (4-5)"
        ),
        "noFaultCells": (
            "the manifestation criterion's wording ('the rate's no-fault cell') is campaign E's; this epoch has 10 no-fault cells (5 blocks x 2 replicates); how "
            "a statistic over several no-fault cells is formed is the declaration's decision, not the harness's"
        ),
    })
    completeness = copy.deepcopy(base["analysis"]["traceCompleteness"])
    old_complete = "Complete = the request's own trace id observed and exactly the route's services."
    new_complete = (
        "Complete = the request's own trace id observed and every service its route is guaranteed to reach "
        "(workload.mix.routes[route].requiredServices, a conservative subset) observed in that trace (a request of the mix has "
        "its route's set; services beyond the set, such as flagd or the async consumers, are neither required nor unexpected; "
        "C's 'exactly the route's services' was for its single route)."
    )
    for kind in ("faultCells", "noFaultCells"):
        if completeness[kind]["rule"].count(old_complete) != 1:
            raise ProtocolError("campaign C's completeness wording changed; campaign F-nolag's replacement did not apply")
        completeness[kind]["rule"] = completeness[kind]["rule"].replace(old_complete, new_complete)
    analysis["traceCompleteness"] = completeness
    document["analysis"] = analysis
    document["derivedFrom"] = {
        "authority": AUTHORITY,
        "studyEpoch": PREDECESSOR_EPOCH,
        "descriptorPath": str(path_relative(path)),
        "descriptorByteSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "descriptorCanonicalSha256": canonical_sha256(base),
        "inheritedAmendments": copy.deepcopy(base["amendments"]),
        "designSource": {
            "studyEpoch": DESIGN_EPOCH,
            "descriptorCanonicalSha256": DESIGN_DESCRIPTOR_SHA256,
            "note": "campaign F's descriptor (25 req/s, all three faults, two no-fault cells per block), pinned by digest; this generator does not read F's descriptor or compiler",
            "baseDesignSource": {"studyEpoch": BASE_DESIGN_EPOCH, "descriptorCanonicalSha256": BASE_DESIGN_DESCRIPTOR_SHA256},
        },
        "predecessorDerivedFrom": copy.deepcopy(base["derivedFrom"]),
        "disposition": (
            "campaign C's epoch is not superseded: it keeps its own descriptor, plan, admission history and spent attempts; the "
            "campaign F-nolag is a separate epoch selected by execution/study-epoch.json; campaign F's and campaign E's epochs are not superseded either"
        ),
    }
    return document


def path_relative(path: Path) -> Path:
    return Path(path).resolve().relative_to(ROOT)


def _pretty_bytes(value: Any) -> bytes:
    return frozen._pretty_bytes(value)


def validate_descriptor(document: Any) -> Dict[str, Any]:
    """Exactly the generated document, and the reviewed digest of its (rate, kept faults) variant (this epoch has one)."""
    if not isinstance(document, dict):
        raise ProtocolError("campaign F-nolag descriptor must be one JSON object")
    expected = derive_f_descriptor()
    if canonical_json_bytes(document) != canonical_json_bytes(expected):
        raise ProtocolError("campaign F-nolag descriptor differs from its generator")
    digest = canonical_sha256(document)
    if EXPECTED_DESCRIPTOR_SHA256 is None or digest != EXPECTED_DESCRIPTOR_SHA256:
        raise ProtocolError(
            "campaign F-nolag descriptor canonical digest differs from the reviewed pin of variant (%r, %r): expected %s, found %s"
            % (RATE, KEPT_FAULTS, EXPECTED_DESCRIPTOR_SHA256, digest)
        )
    return document


def load_descriptor(path: Path = DEFAULT_DESCRIPTOR) -> Dict[str, Any]:
    try:
        payload = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProtocolError("cannot read campaign F-nolag descriptor: %s" % exc) from exc
    return copy.deepcopy(validate_descriptor(strict_json_loads(payload)))


def _compile(document: Mapping[str, Any], attempt: int) -> Dict[str, Any]:
    """C's plan layout (one entry per block under ``blocks``, the runtime runs the cells in that order), this epoch's orders, run keys
    and timings."""
    attempt = validate_attempt(attempt)
    blocks = []
    run_ids: List[str] = []
    position = 0
    for receipt in document["schedule"]["blocks"]:
        number = receipt["block"]
        cells = []
        for index, row in enumerate(block_order(number)):
            regime, rate, episode, posture, replicate = row["regime"], row["rate"], row["block"], POSTURES[0], row["replicate"]
            if cell_label(row) != receipt["order"][index] or receipt["split"] != block_split(number):
                raise ProtocolError("compiled order differs from the descriptor's schedule receipt")
            position += 1
            key = run_key_for(regime, rate, episode, posture, attempt, replicate)
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
                "timing": cell_timing(regime, rate, episode, replicate),
            })
        blocks.append({
            "block": number, "split": block_split(number),
            "order": [cell["runId"] for cell in cells], "cells": cells,
        })
    return {
        "schemaVersion": 1,
        "kind": "otel-demo-offpath-f-nolag-compiled-plan",
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
                {"block": row["block"], "split": row["split"], "order": list(row["order"]), "orderSha256": row["orderSha256"]}
                for row in document["schedule"]["blocks"]
            ],
        },
        "split": split_record(),
        "rate": float(RATE),
        "keptFaults": list(KEPT_FAULTS),
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
    """The one attempt every cell of a compiled campaign-F-nolag plan carries."""
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
    if plan.get("split") != split_record() or [
        (block["block"], block["split"]) for block in plan["blocks"]
    ] != [(n, "training" if n in TRAINING_BLOCKS else "test") for n in range(1, BLOCKS + 1)]:
        raise ProtocolError("compiled plan split is not blocks %s training and %s test" % (TRAINING_BLOCKS, TEST_BLOCKS))
    if [cell["ordinalPosition"] for cell in cells] != list(range(1, TOTAL_RUNS + 1)):
        raise ProtocolError("compiled plan ordinal positions are not 1..%d in run order" % TOTAL_RUNS)
    for block in plan["blocks"]:
        held = sorted(
            (cell["runKey"]["regime"], cell["runKey"]["requestsPerSecond"], cell["runKey"]["block"], cell["runKey"]["replicate"])
            for cell in block["cells"]
        )
        if held != sorted((row["regime"], row["rate"], row["block"], row["replicate"]) for row in block_cells(block["block"])):
            raise ProtocolError("block %r does not hold its cells exactly once" % block["block"])
        # The rule is written on the regimes themselves, not on ORDER_GROUPS: no-fault first, the kept off-path pauses, the frontend pause last.
        regimes = [cell["runKey"]["regime"] for cell in block["cells"]]
        off_path = [regime for regime in regimes if regime in (FRAUD_PAUSE_REGIME, ACCOUNTING_PAUSE_REGIME)]
        tail = [FRONTEND_PAUSE_REGIME] if FRONTEND_PAUSE_REGIME in REGIMES else []
        if (
            regimes != [NO_FAULT_REGIME] * NO_FAULT_CELLS_PER_BLOCK + off_path + tail
            or any(cell["fault"] is not None for cell in block["cells"][:NO_FAULT_CELLS_PER_BLOCK])
            or sorted(cell["runKey"]["replicate"] for cell in block["cells"][:NO_FAULT_CELLS_PER_BLOCK])
            != list(range(1, NO_FAULT_CELLS_PER_BLOCK + 1))
        ):
            raise ProtocolError(
                "block %r does not run its no-fault cells, then the off-path pauses, then the frontend pause" % block["block"]
            )
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
        if canonical_json_bytes(timing["workloadMix"]) != canonical_json_bytes(MIX):
            raise ProtocolError("a cell's workload mix differs from the epoch's")


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
        help="write (exclusive-create) or byte-verify <root> as campaign F-nolag's descriptor derived from campaign C's",
    )
    parser.add_argument("--print-digests", action="store_true",
                        help="print the unpinned descriptor and attempt plan digests (for re-pinning after a change)")
    args = parser.parse_args(argv)
    if args.print_digests:
        document = derive_f_descriptor()
        attempt = campaign_attempt() if args.attempt is None else args.attempt
        print(json.dumps({
            "studyEpoch": EPOCH,
            "rate": RATE,
            "keptFaults": list(KEPT_FAULTS),
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
        frozen._install_or_verify(Path(args.root), _pretty_bytes(derive_f_descriptor()), "campaign F-nolag descriptor")
        print(canonical_sha256(derive_f_descriptor()))
        return 0
    print(json.dumps(materialize(args.root, args.descriptor, args.attempt), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
