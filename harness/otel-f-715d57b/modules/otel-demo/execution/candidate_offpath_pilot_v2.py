#!/usr/bin/env python3
"""Compile the OTel Demo off-path manifestation pilot v2 (otel-offpath-pilot-v2) without executing it.

Authority: main repo research/traffic-sweep/BUDGET_E.md amendment 1 (d4e8e52) and protocol decision 108 (user 2026-10-12): the first
off-path pilot (``candidate_offpath_pilot.py``, otel-offpath-pilot-v1, attempt 1, harness 8c53cb2) stopped at its cell 2: at 100 req/s
of the upstream task mix productcatalogservice was memcg-OOM-killed at its upstream 20 MiB limit and Docker restarted it (the
container-health guard invalidated the cell).  The user chose a second pilot at **25 and 50 req/s** of the same mix with every SUT
memory limit at upstream's, otelcol and jaeger at 1 GiB (decision 103), the productcatalogservice throttle DROPPED.

This file is v1's compiler as a parameterised copy: same mix (``MIX``, byte for byte), same pause scenarios, same cell shape (campaign
C's ``cell_timing`` through ``candidate_repeat_c.py``, read, never edited), same H10/H4, collector log sampler off, trace rules,
per-route completeness and gates.  What differs from v1:

* epoch ``otel-offpath-pilot-v2`` (every runKey, run ID and host path is new), declaration
  research/traffic-sweep/DECLARATION_PILOT_OFFPATH_V2_OTEL.md, seed 20261012 (the build date);
* rates 25 and 50 req/s of the whole mix; regimes no fault, frauddetectionservice pause, accountingservice pause, frontend pause (the
  throttle is dropped); 8 cells in three segments (coordinator default S8): no-fault 25 and the two off-path pauses at 25 (seeded), no-fault 50
  and the two off-path pauses at 50 (seeded), then the frontend pause at 25 and at 50;
* sizing by the same rules at 50 req/s: concurrency ceil(2 x 50 x 15) = 1500, open files concurrency + 1024 = 2524, frontendproxy
  memory 256 MiB (0.3 MB per waiting request at rate x timeout = 750 requests = 225 MB, rounded up to a power of two; C's own value),
  otelcol and jaeger 1 GiB (decision 103), 300 s of overhead per cell, a 3 h GATE-RUN window.

The epoch is active only when the committed selector ``execution/study-epoch.json`` names it.

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
DEFAULT_DESCRIPTOR = ROOT / "pipelines/campaigns/otel-offpath-pilot-v2.json"


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
repeat_c = _load("otel_offpath_pilot_v2_c_compiler", HERE / "candidate_repeat_c.py")
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

EPOCH = "otel-offpath-pilot-v2"
PREDECESSOR_EPOCH = repeat_c.EPOCH                    # otel-repeat-episodes-c-v1: the cell this pilot runs at 25/50 /s
MODULE_ID = repeat_c.MODULE_ID
APPLICATION_FAMILY = repeat_c.APPLICATION_FAMILY
CHANNEL = repeat_c.CHANNEL
SCHEDULE_CONTEXT = "offpath-pilot-v2-schedule-v1"
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
RATES = (25.0, 50.0)                                # total requests per second of the whole mix, in run order
NO_FAULT_REGIME = repeat_c.NO_FAULT_REGIME            # "no-fault-calibration"
FRONTEND_PAUSE_REGIME = "frontend-pause-effect"
FRAUD_PAUSE_REGIME = "fraud-pause-effect"
ACCOUNTING_PAUSE_REGIME = "accounting-pause-effect"
REGIMES = (NO_FAULT_REGIME, FRONTEND_PAUSE_REGIME, FRAUD_PAUSE_REGIME, ACCOUNTING_PAUSE_REGIME)
FAULTS = {
    NO_FAULT_REGIME: None,
    FRONTEND_PAUSE_REGIME: repeat_c.FAULTS[FRONTEND_PAUSE_REGIME],
    FRAUD_PAUSE_REGIME: "fraud-pause",
    ACCOUNTING_PAUSE_REGIME: "accounting-pause",
}
ARTIFACT_ROOTS = {
    NO_FAULT_REGIME: repeat_c.ARTIFACT_ROOTS[NO_FAULT_REGIME],
    FRONTEND_PAUSE_REGIME: repeat_c.ARTIFACT_ROOTS[FRONTEND_PAUSE_REGIME],
    FRAUD_PAUSE_REGIME: "effect/fraud-pause",
    ACCOUNTING_PAUSE_REGIME: "effect/accounting-pause",
}
# The regime whose compiled cell timing a pause of another service reuses: C's timing names no scenario, only
# ``faultApplied``, and the pause mechanism is the frontend pause's.
TIMING_TEMPLATE_REGIME = {
    FRAUD_PAUSE_REGIME: FRONTEND_PAUSE_REGIME, ACCOUNTING_PAUSE_REGIME: FRONTEND_PAUSE_REGIME,
}
SCENARIOS = copy.deepcopy(repeat_c.SCENARIOS)
del SCENARIOS["productcatalog-cpu-throttle"]                    # dropped (decision 108)
SCENARIOS["fraud-pause"] = {
    "service": "frauddetectionservice", "action": "pause",
    "applyCommand": "docker compose pause frauddetectionservice",
    "revertCommand": "docker compose unpause frauddetectionservice",
    "duringPredicate": "running-and-paused",
    "entryRouteDuringFault": repeat_c.ENTRY_ROUTE_DURING_FAULT,
}
SCENARIOS["accounting-pause"] = {
    "service": "accountingservice", "action": "pause",
    "applyCommand": "docker compose pause accountingservice",
    "revertCommand": "docker compose unpause accountingservice",
    "duringPredicate": "running-and-paused",
    "entryRouteDuringFault": repeat_c.ENTRY_ROUTE_DURING_FAULT,
}
SCENARIOS = {name: SCENARIOS[name] for name in sorted(SCENARIOS)}
# One cell per (regime, rate): one episode, one onset stratum.
EPISODES = 1
ONSET_STRATA = 1
# Engineering default recorded in the declaration: the build date plus one day (the pilot is built on 2026-10-12 and ready on
# 2026-10-13); with the epoch id alone every draw already differs from every earlier epoch's.
SCHEDULE_SEED = 20261012
ONSET_PHASE_OFFSET = repeat_c.ONSET_PHASE_OFFSET
DURING_FAULT_PROBE = repeat_c.DURING_FAULT_PROBE      # H10: False
FREEZE_STAMPS = repeat_c.FREEZE_STAMPS                # H4: True
REQUEST_TIMEOUT_SECONDS = sweep.REQUEST_TIMEOUT_SECONDS
# The sweep's open-loop rule (research/load-generator/DESIGN.md L1) at this pilot's top rate: ceil(2 x 50 x 15) = 1500 for
# every cell, as the sweep used its max rate for all.  A journey's dependent request waits for its predecessor inside a worker,
# bounded by the timeout, so the 2x margin also covers the waiting workers.
CONCURRENCY = int(math.ceil(sweep.CONCURRENCY_MARGIN * max(RATES) * REQUEST_TIMEOUT_SECONDS))
GENERATOR_FILE_RESERVE = 1024
GENERATOR_OPEN_FILES_MINIMUM = CONCURRENCY + GENERATOR_FILE_RESERVE
# The sweep's frontendproxy rule (0.3 MB per waiting request) at rate x timeout = 50 x 15 = 750 waiting requests: 225 MB,
# rounded up to a power of two (256 MiB, C's own value).
FRONTENDPROXY_BYTES_PER_WAITING_REQUEST = 300 * 1000
FRONTENDPROXY_MEMORY_LIMIT_BYTES = 256 * 1024 * 1024
# User decision 2026-10-12 (on the build's risk 3): the telemetry backend, and only it, gets 1 GiB: otelcol (upstream 200M, no
# memory_limiter, the debug exporter prints every span, an estimated 0.7k spans/s at 50 req/s) and jaeger (upstream 400M, holds traces in
# memory).  Every SUT service limit stays upstream's.  Applied by `docker update --memory` like frontendproxy's.
TELEMETRY_BACKEND_MEMORY_LIMIT_BYTES = {"otelcol": 1024 * 1024 * 1024, "jaeger": 1024 * 1024 * 1024}
UPSTREAM_TELEMETRY_BACKEND_LIMITS = {"otelcol": "209715200 bytes (200M; upstream docker-compose.yml)", "jaeger": "419430400 bytes (400M; upstream docker-compose.yml)"}
SERVICE_MEMORY_LIMIT_BYTES = {"frontendproxy": FRONTENDPROXY_MEMORY_LIMIT_BYTES, **TELEMETRY_BACKEND_MEMORY_LIMIT_BYTES}
# Wall budget (engineering defaults).  The load pilot's measured tail after the window (request-ledger endedAtEpoch to the next
# barrier, fb14srv6, 2026-10-12): 142.2-150.0 s at 50 req/s and 158.7-167.4 s at 100 req/s, about 1.35 ms per offered request
# (the load pilot projected 162 s at 100 req/s).  This pilot offers 9,000 requests at its top rate and its mix emits several
# times the spans per request of the load pilot's one product route, so the collector log, the capture and their parsing are
# larger: 300 s per cell (about 2x the load pilot's measured 142-150 s at 50 req/s of one route, for the mix's larger log).
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
    "research/traffic-sweep/DECLARATION_PILOT_OFFPATH_V2_OTEL.md (measurement repo; frozen and committed alone before the "
    "first cell)"
)
AMENDMENTS: List[str] = []
AUTHORITY = (
    "main repo research/traffic-sweep/BUDGET_E.md (ec4b9fa, committed alone before any E work; user decisions 2026-10-12: the "
    "upstream Locust task mix as an open loop with a request ledger, off-path faults on frauddetectionservice and "
    "accountingservice with the frontend pause as the on-path control, a manifestation pilot at two total "
    "rates, criteria per fault declared before launch); load pilot result research/placement/pilot-load/RESULT_P1.md "
    "(v1 attempt 1 stopped at its cell 2: productcatalogservice OOM at 20 MiB at 100 req/s; amendment 1, decision 108); campaign C's decisions 25, 56, 66 and 69 carried "
    "over unchanged"
)
MANIFESTATION_CRITERION = (
    "per fault and rate, one cell: the frontend pause manifests if at least 90 % of the requests scheduled in the first 45 s of the hold fail and "
    "checkout requests sent in them (by send time) succeed in at most 10 % of cases (the pause command takes a moment to bite); an off-path pause manifests if the target service's consumer-side "
    "spans started in the hold number at most 10 % of those started in the pre-onset 60 s AND checkout requests scheduled in "
    "the hold keep succeeding (at least 95 % ok); in every case the rate's no-fault cell shows neither the effect nor the failure, and a valid no-fault cell that fails its "
    "precondition (checkout rows and all rows >= 95 % ok in its pseudo window) makes the verdict '—' for that rate"
)
MANIFESTATION_CRITERION_DEFAULTS = {
    "unit": "one cell per (fault, rate); a verdict is per (fault, rate); a fault is kept for campaign E iff it manifests at >= 1 rate",
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
# ---------------------------------------------------------------- derived

TOTAL_RUNS = len(REGIMES) * len(RATES) * EPISODES                              # 8
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
    "timing": frozenset({"budget", "faultOnsetStrata", "offeredByRate", "generatorOpenFilesMinimum", "workloadMix"}),
    "workload": frozenset({
        "kind", "concurrency", "concurrencyRule", "requestsPerSecondLevels", "generatorOpenFiles", "mix", "ledger", "warmup",
        "arrivals", "readiness", "traceContext", "routeServices", "routeDerivation", "probeRoute",
    }),
    "analysis": frozenset({
        "comparativeUnit", "analysisFreeze", "manifestationCriterion", "manifestationCriterionDefaults", "traceCompleteness",
    }),
    "collection": frozenset({"requestWitness"}),
}
EXPECTED_DESCRIPTOR_SHA256 = "b22c4ee66526ba18dcfc2c6f372c3f74c127ad73273b6b7a8d98825b5bc8f6a9"


def mix_route_services() -> List[str]:
    """Every service some route of the mix is guaranteed to reach, sorted (the runtime derives the same list from the cell's timing,
    whose JSON keys are sorted, so the order must not depend on the routes' order)."""
    return sorted({service for route in MIX["routes"].values() for service in route["requiredServices"]})


def onset_phase_offset(regime: str, rate: float, block: int) -> float:
    if ONSET_PHASE_OFFSET != "seeded-stratified-within-one-inter-arrival":
        raise ProtocolError("the off-path pilot keeps the sweep's seeded onset rule")
    if int(block) != 1:
        raise ProtocolError("the off-path pilot has one episode per (regime, rate): block %r" % (block,))
    return quiet.stratified_onset_offset(SCHEDULE_SEED, EPOCH, ONSET_STRATA, regime, rate, 1)


# Run order (coordinator's engineering default S8, 2026-10-12, after the v2 GO review): no-fault 25, the two off-path pauses at 25 (seeded),
# no-fault 50, the two off-path pauses at 50 (seeded), then the frontend pause at 25 and at 50 (the on-path control last: its cells are the
# ones a 256 MiB frontendproxy could still kill, and the off-path answers must not depend on them).  A segment is a run of cells with its
# rates; the groups are indices into ORDER_GROUPS.
ORDER_GROUPS = (
    (NO_FAULT_REGIME,),
    (FRAUD_PAUSE_REGIME, ACCOUNTING_PAUSE_REGIME),
    (FRONTEND_PAUSE_REGIME,),
)
GROUP_OF = {regime: index for index, group in enumerate(ORDER_GROUPS) for regime in group}
SEGMENTS = (
    {"rates": (RATES[0],), "groups": (0, 1)},
    {"rates": (RATES[1],), "groups": (0, 1)},
    {"rates": tuple(RATES), "groups": (2,)},
)


def segment_cells(segment: int) -> List[Dict[str, Any]]:
    """The cells of one segment (1-based), in a fixed declaration order (regimes in REGIMES order, rates ascending)."""
    if not 1 <= int(segment) <= len(SEGMENTS):
        raise ProtocolError("segment %r is outside 1..%d" % (segment, len(SEGMENTS)))
    spec = SEGMENTS[int(segment) - 1]
    return [
        {"regime": regime, "rate": float(rate), "block": 1}
        for regime in REGIMES if GROUP_OF[regime] in spec["groups"] for rate in spec["rates"]
    ]


def segment_order(segment: int) -> List[Dict[str, Any]]:
    """The segment's cells group by group, a group of several regimes Fisher-Yates shuffled by SHA-256 draws keyed by seed, epoch and
    segment (the quiet compiler's ``fisher_yates`` with this epoch's context and the group number; the segment number is its block
    argument); a group of one regime runs its rates ascending."""
    if sorted(GROUP_OF) != sorted(REGIMES):
        raise ProtocolError("the order groups do not cover the regimes exactly once")
    cells = segment_cells(segment)
    order: List[Dict[str, Any]] = []
    for index in SEGMENTS[int(segment) - 1]["groups"]:
        members = [row for row in cells if GROUP_OF[row["regime"]] == index]
        if len(ORDER_GROUPS[index]) > 1:
            members = quiet.fisher_yates(members, SCHEDULE_SEED, EPOCH, int(segment), "%s-group%d" % (SCHEDULE_CONTEXT, index))
        order += members
    return order


def cell_label(row: Mapping[str, Any]) -> str:
    return "%s@r%s#b%d" % (row["regime"], rate_token(row["rate"]), int(row["block"]))


def cell_timing(regime: str, rate: float, block: int) -> Dict[str, Any]:
    """C's cell timing for (regime, rate) at the pilot rate, with this epoch's onset draw and the keys that follow from it
    (C's formulas), the pilot's concurrency, run count, budget and frontendproxy memory limit, the generator's open-file minimum
    and the workload mix."""
    if regime not in REGIMES:
        raise ProtocolError("unknown regime %r" % (regime,))
    if float(rate) not in RATES:
        raise ProtocolError("rate %r is not a pilot rate" % (rate,))
    timing = repeat_c.cell_timing(TIMING_TEMPLATE_REGIME.get(regime, regime), rate, 1)
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
        "workloadMix": copy.deepcopy(MIX),
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
    """The design-level schedule receipt (attempt-free): per segment, the cell order."""
    if POSTURES != ("full",):
        raise ProtocolError("the off-path pilot runs the full posture only")
    if list(RATES) != sorted(set(RATES)) or any(not (math.isfinite(rate) and rate > 0) for rate in RATES):
        raise ProtocolError("rates must be distinct, finite, positive and ascending (the run order)")
    segments = []
    for segment, spec in enumerate(SEGMENTS, start=1):
        order = [cell_label(row) for row in segment_order(segment)]
        segments.append({
            "segment": segment, "rates": [float(rate) for rate in spec["rates"]], "order": order, "orderSha256": canonical_sha256(order),
        })
    every = [item for row in segments for item in row["order"]]
    if len(every) != TOTAL_RUNS or len(set(every)) != TOTAL_RUNS:
        raise ProtocolError("schedule does not contain every cell exactly once")
    return segments


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


def derive_pilot_descriptor(predecessor_path: Path = None) -> Dict[str, Any]:
    """Generate the off-path pilot's descriptor from campaign C's pinned descriptor.

    This function IS the descriptor's source: the checked-in otel-offpath-pilot-v2.json must equal ``_pretty_bytes`` of its
    result (tested), so the file is regenerated, never hand-edited.  Replaced: ``REPLACED_DESCRIPTOR_KEYS`` and
    ``REPLACED_DESCRIPTOR_SUBKEYS``; every other key is C's (H10/H4, the trace rules per cell kind
    apart from the completeness wording, protocolGates, containerHealthGuard, workflow, ...).
    """
    path = Path(predecessor_path) if predecessor_path is not None else repeat_c.DEFAULT_DESCRIPTOR
    base = repeat_c.load_descriptor(path)
    if base["id"] != PREDECESSOR_EPOCH:
        raise ProtocolError("the off-path pilot is derived from campaign C's descriptor only")
    document = copy.deepcopy(base)
    document["id"] = EPOCH
    document["declaration"] = DECLARATION
    document["amendments"] = list(AMENDMENTS)
    design = copy.deepcopy(base["design"])
    for key in ("blockRule", "blocks", "cellsPerBlock"):
        design.pop(key)
    design.update({
        "purpose": (
            "off-path manifestation pilot (BUDGET_E.md): does a pause of frauddetectionservice or accountingservice (the "
            "asynchronous Kafka consumers of the orders topic) manifest as a collapse of the target's consumer-side spans "
            "while checkout requests keep succeeding, and does the frontend pause fail the mix, at 25 and 50 "
            "req/s of the upstream task mix; decides which faults enter campaign E"
        ),
        "rates": list(RATES),
        "regimes": [
            {"id": regime, "kind": "no-fault-calibration" if FAULTS[regime] is None else "effect",
             "fault": FAULTS[regime], "artifactRootClass": ARTIFACT_ROOTS[regime]}
            for regime in REGIMES
        ],
        "omittedRegimes": copy.deepcopy(base["design"]["omittedRegimes"]),
        "episodesPerRegimeAndRate": EPISODES,
        "segments": len(SEGMENTS),
        "cellsPerSegment": [len(segment_cells(n)) for n in range(1, len(SEGMENTS) + 1)],
        "segmentRule": (
            "three segments in this order: (1) the no-fault cell at 25 req/s, then the two off-path pauses (fraud, accounting) at 25 "
            "req/s in a seeded order; (2) the same at 50 req/s; (3) the frontend pause at 25 then at 50 req/s; the runKey's block is 1"
        ),
        "segmentOrderRationale": (
            "coordinator engineering default S8 (2026-10-12): the campaign stops on its first invalid cell; every rate's baseline "
            "precedes its off-path pauses, no 25 req/s off-path cell depends on a 50 req/s cell, and the on-path control, whose cells "
            "are the ones a 256 MiB frontendproxy could still kill under a pause, runs last so that no off-path answer depends on it"
        ),
        "totalRuns": TOTAL_RUNS,
        "cellShape": (
            "campaign C's cell (candidate_repeat_c.cell_timing(regime, rate, 1); a pause of frauddetectionservice or "
            "accountingservice takes the frontend pause's) at the pilot rate; only the seeded onset (1 stratum), the slots per "
            "phase it implies, the concurrency, the plan-level run count and minimum remaining time, the frontendproxy, otelcol and jaeger memory "
            "limit, the generator's open-file minimum and the workload mix differ"
        ),
        "doses": (
            "the pauses are the frontend pause's mechanism (docker compose pause / unpause) for a hold of 60 s on "
            "frauddetectionservice and accountingservice; the throttle of v1 is dropped (decision 108)"
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
        "shuffle": "segments-no-fault-then-fisher-yates-over-the-two-off-path-pauses-per-rate-then-the-frontend-pause-per-rate-with-sha256-draws",
        "drawEncoding": "UTF-8(seed || NUL || epoch || NUL || block-NN (NN = segment number) || NUL || draw-i || NUL || version)",
        "segmentOrder": "nf25-pauses25-nf50-pauses50-fp25-fp50",
        "leadCell": None,
        "segments": allocate_schedule(),
    }
    timing = copy.deepcopy(base["timing"])
    timing["faultOnsetStrata"] = ONSET_STRATA
    timing["offeredByRate"] = {rate_token(rate): offered_for(rate, timing["measurementSeconds"]) for rate in RATES}
    timing["generatorOpenFilesMinimum"] = GENERATOR_OPEN_FILES_MINIMUM
    timing["workloadMix"] = copy.deepcopy(MIX)
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
            "ceil(2 x max rate x request timeout) = ceil(2 x 50 x 15): the worker cap covers rate x timeout with the sweep's "
            "2x margin; one thread per in-flight, waiting or scheduled-ahead request"
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
        "carrier's rule): a 50 req/s cell writes 9,300 lines (~3.7 MB at 0.4 kB, inside upstream's 5m x 2 bound of 5 to 10 MB; the retention is kept as v1's so the materialized source is unchanged); "
        "a lost line fails the terminal's witness check; every request of the mix, POSTs included, is one witnessed token"
    )
    document["collection"] = collection
    document["faultDesign"] = copy.deepcopy(base["faultDesign"])
    document["faultDesign"]["scenarios"] = copy.deepcopy(SCENARIOS)
    document["faultDesign"]["manifestation"] = (
        base["faultDesign"]["manifestation"]
        + ". Off-path pauses (frauddetectionservice, accountingservice) are proven by the paused container state read back and the "
        "Docker pause event, like the frontend's; whether the consumer-side effect shows in the target's spans, and that checkout "
        "requests keep succeeding, is the pilot's question (analysis.manifestationCriterion), not a harness condition"
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
            row["pilot"] = "%d bytes (256 MiB)" % FRONTENDPROXY_MEMORY_LIMIT_BYTES
            row["pilotRule"] = (
                "the sweep's rule (0.3 MB per waiting request, twice the cost the attempt-1 kill implies) at rate x timeout = "
                "50 x 15 = 750 waiting requests = 225 MB, rounded up to 256 MiB"
            )
            row["scope"] = "the off-path pilot's cells; C's epoch and every frozen epoch keep their limit"
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
                "telemetry backend, not a SUT service (user decision 2026-10-12): at 50 req/s of the mix the collector's debug "
                "exporter prints every span (a few thousand per second, no memory_limiter in its config) and jaeger holds the "
                "traces in memory; an OOM kill of either would invalidate the cell (container-health guard)"
            ),
            "scope": "the off-path pilot's cells only; every SUT service limit stays upstream's; C's epoch and every frozen epoch keep upstream's",
        })
    deviations.append({
        "service": "frontendproxy",
        "setting": "json-file log rotation",
        "upstream": "max-size 5m, max-file 2 (x-default-logging)",
        "pilot": "max-size 4g, max-file 1 (the collector carrier's rule, compose.otel-placement.yml)",
        "mechanism": "materialize.py renders it into the materialized compose.otel-placement.yml when the selector names the pilot",
        "reason": (
            "the request witness is the frontendproxy access log; at 50 req/s a cell writes ~3.7 MB of it (estimated), inside "
            "upstream's bound; kept as v1's so the materialized source is unchanged"
        ),
        "scope": "the load pilot's and this pilot's materialized source; every other epoch renders the overlay byte for byte",
    })
    document["sutDeviations"] = deviations
    document["outcomes"] = {
        "primary": "per (fault, rate): whether the fault manifests by the declared criterion (analysis.manifestationCriterion)",
        "secondary": (
            "per cell: request outcomes and latency by route over pre-onset, hold and post-revert; the target's consumer-side "
            "spans per second; productcatalogservice and frontend CPU; the dependency waits of the checkout journeys"
        ),
        "costRegimeOnly": None,
        "offeredRequestsAreDenominator": True,
        "windowMembership": "monotonic-shared-barrier",
    }
    analysis = copy.deepcopy(base["analysis"])
    analysis.update({
        "comparativeUnit": "(fault, rate); one cell per pair and one no-fault cell per rate, read by the manifestation criterion only",
        "analysisFreeze": (
            "exploratory pilot: no placement is scored on these cells; the manifestation criteria are declared before launch "
            "(BUDGET_E.md) and applied once"
        ),
        "manifestationCriterion": MANIFESTATION_CRITERION,
        "manifestationCriterionDefaults": copy.deepcopy(MANIFESTATION_CRITERION_DEFAULTS),
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
            raise ProtocolError("campaign C's completeness wording changed; the off-path pilot's replacement did not apply")
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
        "predecessorDerivedFrom": copy.deepcopy(base["derivedFrom"]),
        "disposition": (
            "campaign C's epoch is not superseded: it keeps its own descriptor, plan, admission history and spent attempts; the "
            "off-path pilot is a separate epoch selected by execution/study-epoch.json"
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
        raise ProtocolError("off-path pilot descriptor must be one JSON object")
    expected = derive_pilot_descriptor()
    if canonical_json_bytes(document) != canonical_json_bytes(expected):
        raise ProtocolError("off-path pilot descriptor differs from its generator")
    digest = canonical_sha256(document)
    if digest != EXPECTED_DESCRIPTOR_SHA256:
        raise ProtocolError(
            "off-path pilot descriptor canonical digest differs from the reviewed pin: expected %s, found %s"
            % (EXPECTED_DESCRIPTOR_SHA256, digest)
        )
    return document


def load_descriptor(path: Path = DEFAULT_DESCRIPTOR) -> Dict[str, Any]:
    try:
        payload = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProtocolError("cannot read off-path pilot descriptor: %s" % exc) from exc
    return copy.deepcopy(validate_descriptor(strict_json_loads(payload)))


def _compile(document: Mapping[str, Any], attempt: int) -> Dict[str, Any]:
    """B's plan layout, with one entry per segment under ``blocks`` (the runtime runs the cells in that order)."""
    attempt = validate_attempt(attempt)
    segments = []
    run_ids: List[str] = []
    position = 0
    for receipt in document["schedule"]["segments"]:
        number = receipt["segment"]
        cells = []
        for index, row in enumerate(segment_order(number)):
            regime, rate, episode, posture = row["regime"], row["rate"], row["block"], POSTURES[0]
            if cell_label(row) != receipt["order"][index] or float(rate) not in receipt["rates"]:
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
            "segment": number, "rates": list(receipt["rates"]),
            "order": [cell["runId"] for cell in cells], "cells": cells,
        })
    return {
        "schemaVersion": 1,
        "kind": "otel-demo-offpath-pilot-compiled-plan",
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
                {"segment": row["segment"], "rates": row["rates"], "order": list(row["order"]),
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
    """The one attempt every cell of a compiled off-path-pilot plan carries."""
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
    if [segment["rates"] for segment in plan["blocks"]] != [[float(r) for r in spec["rates"]] for spec in SEGMENTS]:
        raise ProtocolError("compiled plan segments are not the declared segments")
    if [cell["ordinalPosition"] for cell in cells] != list(range(1, TOTAL_RUNS + 1)):
        raise ProtocolError("compiled plan ordinal positions are not 1..%d in run order" % TOTAL_RUNS)
    for number, segment in enumerate(plan["blocks"], start=1):
        held = sorted(
            (cell["runKey"]["regime"], cell["runKey"]["requestsPerSecond"], cell["runKey"]["block"])
            for cell in segment["cells"]
        )
        if held != sorted((row["regime"], row["rate"], row["block"]) for row in segment_cells(number)):
            raise ProtocolError("segment %r does not hold its cells exactly once" % segment["segment"])
        groups = [GROUP_OF[cell["runKey"]["regime"]] for cell in segment["cells"]]
        if groups != sorted(groups) or (0 in groups and segment["cells"][0]["fault"] is not None):
            raise ProtocolError(
                "segment %r does not run its no-fault cell, then the off-path pauses, then the frontend pause" % segment["segment"]
            )
    sequence = [(GROUP_OF[cell["runKey"]["regime"]], cell["runKey"]["requestsPerSecond"]) for cell in cells]
    frontend = [index for index, (group, _) in enumerate(sequence) if group == 2]
    if frontend != list(range(len(cells) - len(frontend), len(cells))) or [rate for group, rate in sequence if group == 2] != sorted(
        rate for group, rate in sequence if group == 2
    ):
        raise ProtocolError("the frontend-pause cells are not last, rate-ascending")
    baselines = [index for index, (group, _) in enumerate(sequence) if group == 0]
    if len(baselines) != len(RATES) or any(sequence[index + 1][0] != 1 for index in baselines):
        raise ProtocolError("each no-fault cell must be followed by the off-path pauses of its rate")
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
        help="write (exclusive-create) or byte-verify <root> as the off-path pilot descriptor derived from campaign C's",
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
        frozen._install_or_verify(Path(args.root), _pretty_bytes(derive_pilot_descriptor()), "off-path pilot descriptor")
        print(canonical_sha256(derive_pilot_descriptor()))
        return 0
    print(json.dumps(materialize(args.root, args.descriptor, args.attempt), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
