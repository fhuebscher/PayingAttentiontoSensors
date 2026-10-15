# OTel off-path manifestation pilot v2 (25 and 50 req/s of the upstream task mix, no throttle): declaration (frozen 2026-10-12)

**Status: frozen** by committing this file alone, before launch. Written by the harness-building agent (Sonnet 5.5); reviewed
GO-with-fixes by a same-provider adversarial-review subagent (2026-10-12 ~11:25-11:55Z; the cross-provider judge server fails to
connect); its fixes are applied in harness `ff29b93` and below. Scope of every number here: **instance** (one SUT, OTel Demo 1.12.0
at 2d4661e, one host, fb14srv6). Unknown values are `?`.

**DRY_RUN `opv2dry2` passed** 2026-10-12 11:52:28Z at HEAD `ff29b9305787…`, plan `a929b4d9…` ("DRY RUN: all guards passed; stopping
before the first mutation"; `scratchpad/gate-drivers/otel-offpath-pilot-v2-opv2dry2-launch.log`; the earlier `opv2dry1` at
`a045b9c` also passed, srv6: units 0, containers 0, lease none, 239 GB free, v2 paths 0).

## Why a second pilot: what v1 attempt 1 showed
The first off-path pilot (`DECLARATION_PILOT_OFFPATH_OTEL.md` `64854c2`, harness `8c53cb2`, plan `8b3d7aa8`, 100 and 150 req/s, launched
2026-10-12 09:37Z, stopped 09:57Z, 2 attempted / 1 valid, fetched and byte-verified 40/40) stopped at its cell 2: cell 1 (no-fault, 100 req/s,
the mix) was valid; cell 2 (fraud pause, 100 req/s) was invalid because **productcatalogservice was memcg-OOM-killed at its upstream 20 MiB limit
(09:50:16Z)**, restarted by Docker, and the container-health guard invalidated the cell. Recorded without changing the guard: the retained
`container-health.json` shows `oomKilled` false after the restart (the restart guard is what caught it). Authority for v2: BUDGET_E
amendment 1 (`d4e8e52`) and protocol decision 108 (`639bf73`), user 2026-10-12: a second pilot at **25 and 50 req/s** of the same mix,
**regimes no fault, frauddetectionservice pause, accountingservice pause, frontend pause (the throttle is dropped)**, SUT memory limits upstream's,
otelcol and jaeger 1 GiB (decision 103), criteria identical to v1's frozen declaration minus the throttle row. v1 attempt 1 is recorded spent in the
adapter (`12b626a`); v2 is a new epoch (`otel-offpath-pilot-v2`), so no host path collides with v1's.

Deadlines: harness ready **2026-10-12 12:45Z**; review and DRY_RUN by 13:30Z (coordinator); **terminal and fetched 15:30Z**; if the window runs past it,
BUDGET_E stop rule 1 decides (a missed deadline stops that step; no extension without the user). Relaunch allowance, E-rate rule and run order carry over
from v1 (decided there): **at most 1 relaunch, harness or infrastructure defects only; E's rate rule: the lowest rate at which every kept fault
manifests, else the highest at which any does; run order (S8, coordinator default after the v2 GO review): no-fault 25, the two off-path pauses at 25 (seeded), no-fault 50, the two off-path pauses at 50 (seeded), then the frontend pause at 25 and at 50.** If no
off-path fault manifests, E is not launched (BUDGET_E stop rule 5).

## Manifestation criteria (declared before launch)
One cell per (fault, rate) and one no-fault cell per rate: **n = 1 per pair**, so a verdict is about that cell, not a rate or a
mechanism. All windows: onset = `intervention.json` `freeze.commandIssuedOffsetSeconds` (the pre-command stamp) mapped to wall clock
with `request-ledger.json` `barrierEpoch`; the no-fault cell's pseudo onset is `timing.scoredWindowSeconds[0]`. Pre-onset segment
[onset - 60 s, onset); hold [onset, onset + 60 s). Spans come from `otelcol.log` (log sampler off, decision 66), selected by span
**start time**, all statuses. Spans of a consumer: fraud (Java agent) emits "orders receive" and "orders process" (both Consumer) per batch, accounting (.NET) one "orders receive" whose start is the `Consume()` call; counts are compared within a service only. `Start time` has 0 to 9 fraction digits (the frontend's has 2, .NET's 7), so the parser must not assume 9. The no-fault pseudo onset `timing.scoredWindowSeconds[0]` is not in any cell file: it comes from the compiled plan. A statistic with fewer than **20** items in a segment is `—` (engineering default). A cell counts only if
its host receipt says valid **and** an offline `validate_cell` replay passes (the witness check runs only in the terminal); the rate's
no-fault cell must count too, else the verdict is `—`. **A valid no-fault cell that fails its own precondition (checkout rows and all rows
in its pseudo hold >= 95 % ok, each with >= 20 rows) also gives `—` for every fault at that rate** (the effect cannot be told from a
baseline that already fails; the numbers are reported).

| fault | manifests at a rate iff (all of) | computable from |
|---|---|---|
| frontend pause (on-path control) | of ledger rows (every route) **scheduled** in [onset, onset + **45 s**) at most **10 %** have outcome ok, and of the `route=checkout` rows **sent** in that window (`startedAtEpoch - barrierEpoch`, not the scheduled time: a checkout waits up to 20 s for its cart POST) at most **10 %** (the pause command takes a moment to bite); the no-fault cell's rows in the same window are >= **95 %** ok. The first 45 s, not 60: a request scheduled in the last 15 s can be served after the unpause inside its own 15 s timeout (the terminal's own comment, 2026-10-02), so "all of the hold fails" would be false by construction | request-ledger.json, intervention.json |
| frauddetectionservice pause, accountingservice pause (off-path) | consumer-side spans of the target (`service.name` = the target, `Kind=Consumer`, any name) **started in the hold <= 10 %** of those started in the pre-onset 60 s (pre-onset count >= 20; a frozen process emits nothing, so this collapse is near-true by construction: the informative parts are that each accepted order produced a consumer span before the pause and that checkout stays >= 95 % ok); **and** `route=checkout` ledger rows scheduled in the hold are **>= 95 % ok** (>= 20 rows); **and** the no-fault cell at its pseudo onset has hold/pre-onset > 10 % for that service and its checkout rows >= 95 % ok | otelcol.log, request-ledger.json, intervention.json |

The throttle row of v1 is dropped (decision 108); every other row, bound and window is v1's frozen text (declaration `64854c2` with its review fixes and
coordinator notes (a) the frontend-pause checkout bound <= 10 % and (b) witness rows carry `response_code`/`response_flags`), and the
ambiguity rule of `research/placement/pilot-offpath/AMBIGUITY_RESOLUTION.md` (`b6a750f`: the harness reference functions decide) applies.
The descriptor binds them (`analysis.manifestationCriterionDefaults`, identical to v1's minus the two `throttle*` keys; tested).

A fault is **kept for campaign E iff it manifests at >= 1 rate**; which rate(s) E uses is BUDGET_E step 4's choice (proposal, to be
confirmed: the lowest rate at which every kept fault manifests, else the highest rate at which any does; **decided as a coordinator default, the user may veto**).

How the criteria were checked for computability (executed, on a fake target, not on the SUT): `tests/test_otel_offpath_pilot.py` (v1's reference functions) and `tests/test_otel_offpath_pilot_v2.py`
(`statistics_of`, `verdict`; v2's own tests run them on v2's fake cells) computes every statistic above from nothing but a cell's retained `otelcol.log`, `request-ledger.json`
and `intervention.json`/timing, on all four regimes (no fault, fraud pause, accounting pause, frontend pause), with planted defects (a consumer that keeps working through its pause, a pause
that takes checkout down, each gives "does not manifest"). The span parser reads a real
debug-exporter block (the retained v3a2 `b02-02-full` accountingservice `orders receive` span, Kind Consumer). **What no test can
settle:** how many consumer spans the real consumers emit per order in this SUT's collector output. Both services' `Kind=Consumer` spans
**were seen** in the load pilot's retained `otelcol.log` (all 6 cells; accountingservice `orders receive`, frauddetectionservice
`orders receive` and `orders process`), so the span predicates are confirmed against real output; the per-order counts at the mix's
checkout rate are not. With the sampler off (decision 66; rendered by `materialize.py`, tested) the spans are
retained. If a consumer emits fewer than 20 `Consumer` spans in the pre-onset 60 s, its off-path criterion is `—` and that fault is not decided by this pilot. The post-fetch script also cross-checks each witness row's `response_code` against the ledger's status for the same token (the witness rows carry `response_code` and `response_flags`). The criteria script is written after the fetch, implements exactly the rules above and is committed
before it is run on the cells.

**The 20-item minimums at 25 req/s (checked, as the build was asked).** At the lowest rate the mix offers 4,500 requests per cell; checkout is 5.9 %
of them (design), so ~1.5 checkouts/s: ~66 checkout rows per 45 s and ~88 per 60 s hold (both >= 20), ~1,100 rows of the mix in the 45 s window,
and one accepted order per checkout gives >= 88 consumer spans per service in the pre-onset 60 s (accounting one per message, fraud two). The same
arithmetic is asserted on v2's executed fake cells (`test_the_20_item_minimums_are_reachable_at_25_req_per_second`: checkout rows >= 60 per hold
and >= 40 by send time in 45 s, consumer spans >= 60, rows >= 1,000). Not measured on the SUT: the real per-order consumer span counts.

## The workload: the upstream Locust task mix, open loop, one ledger row per request
Tasks and weights are upstream's (`src/loadgenerator/locustfile.py` at 2d4661e, checked against the file in the test): index 1,
browse_product 10, get_recommendations 3, get_ads 3, view_cart 3, add_to_cart 2, checkout 1, checkout_multi 1; `flood_home` dropped
(0 requests at its default flag, and it asks flagd on every call). Smooth weighted round-robin over the 24-weight cycle; 34 requests
per cycle on average. Request shares (design, DESIGN.md 2.3): GET /api/products 47 %, POST /api/cart 17.6 %, recommendations, ads
and view-cart 8.8 % each, POST /api/checkout 5.9 %, GET / 2.9 %. **The offered rate is the rate of the whole mix in requests per
second**: 4,500 requests per 180 s at 25 req/s, 9,000 at 50 req/s; request i is scheduled at barrier + i / rate.

Choices recorded (each is an engineering default unless marked):
- **Cart dependency** (DESIGN.md does not say; my choice): a task is a journey whose requests take adjacent plan slots, with one
  userId per journey (so carts never mix). `POST /api/checkout` needs the cart the preceding `POST /api/cart` filled in valkey, so it is
  dispatched at max(its slot, the predecessor's end), waits at most 15 s + 5 s, and **is sent whatever the predecessor's outcome**
  (upstream's behaviour; D-LG7 in DESIGN.md, "skip the remainder", is preregistration-class and not taken, and a skipped row would
  leave an unwitnessed token). Every row records `dependsOn`; the terminal refuses a checkout that started before its predecessor
  ended unless it waited out the bound. Within a journey the loop is closed (DESIGN.md 3.1, limit 3); across journeys it is open.
- **One trace per request**; the token, trace id and traceparent rule is the sweep's. The consumers' spans start their own traces (retained
  load-pilot `otelcol.log`), so they are never in a checkout request's trace; the off-path criterion counts them by `service.name`.
- **Within a journey the GET product and the cart POST are adjacent slots and run concurrently** (upstream runs a task's requests one
  after another), and a checkout waits only for its immediate cart POST (earlier adds of `checkout_multi` are not awaited). A checkout
  whose cart POST failed is sent anyway and PlaceOrder on an empty cart still returns 200 but never calls productcatalogservice: it
  then counts as an incomplete trace, mostly inside the fault-and-drain window (recorded, not blocking).
- `GET /api/cart` sends no sessionId, as upstream (the empty cart; cartservice -> valkey).
- **One spelling change:** upstream requests `/api/data/`; Next.js (trailingSlash unset) answers with a 308 to `/api/data`, which
  Python 3.9's urllib does not follow and which would show the request token to the proxy twice. The mix sends `/api/data`.
- Parameters (product, category, quantity, person, number of adds) are integers from `sha256(namespace NUL 'mix' NUL taskIndex NUL
  label)`; identical on 3.9 and 3.13 (tested). People: upstream's 9 entries of `people.json` (sha256 in the descriptor).
- Warm-up: the same mix at 10 req/s for 30 s under its own token namespace, never scored. Stack readiness and the post-revert
  readiness probes are unchanged (the harness's checkout journey, then one GET of the probe route `/api/products/66VCHSJNUP`).
- The upstream loadgenerator is removed after `up`, as in C (`upstream-generator.json` per cell).

### What the old single-route design assumed, and what changed
| component | single-route assumption | now |
|---|---|---|
| request ledger | `otel-demo-route-ledger-v1`: one URL, GET, rows without a route | **`otel-demo-mix-ledger-v1`**: every row carries route, task, journey (`taskIndex`), step, method, target, `bodySha256`, `dependsOn`; header carries `mixSha256`, task and route counts. The terminal replays every row from `mix_plan(mix, runId, offered)` and refuses any difference |
| witness (frontendproxy access log) | one GET per token | unchanged logic: every request of the mix, POSTs included, carries its own token; offered tokens must be witnessed exactly once. Retention 4g x 1 (9,300 lines at 50 req/s ~ 3.7 MB, inside upstream's 5m x 2 bound; kept as v1's rendering) |
| G1 / G2 / G4 | rows pooled over one route | **unchanged code, wider meaning**: G2's 5 % pre-onset failure share is over the whole mix, so a route that fails persistently (checkout is 5.9 %) can invalidate a cell; G1's floor counts all rows; G4's `offered == len(rows)` and rate == profile rate hold (rate = total req/s); `profile.routes` names only the probe route (informational) |
| trace completeness (decisions 25 / 56) | exactly the one route's services on the clipped path | **per route**: the request's own trace id observed and every service its route is *guaranteed* to reach observed in that trace (a conservative subset per route, `workload.mix.routes[route].requiredServices`; flagd and the async consumers are neither required nor unexpected). The rule's allowance (max(1, 1 %)), windows and drain are unchanged. **This changes what "complete" means: a preregistration-adjacent adaptation, flagged below for the user** |
| posture proof | route services must appear among the collector's signals | the union over the mix's routes (sorted) must appear: 12 services, incl. recommendationservice, adservice, checkoutservice, paymentservice, shippingservice, quoteservice, currencyservice, emailservice, cartservice |
| terminal correlation | full path = the route's clipped services | per request, on the unclipped trace services of the request's route |
| probe route / readiness | the cell's route | `/api/products/66VCHSJNUP` (C's route), used only for readiness |
| concurrency, open files, memory | 300 / - / 256 MiB (C); 4500 / 5524 / 1 GiB (v1) | **1500 / 2524 / 256 MiB** (rules below) |

## What differs from v1
| item | v1 (attempt 1) | **v2** |
|---|---|---|
| study epoch / compiler | `otel-offpath-pilot-v1`, `candidate_offpath_pilot.py` | **`otel-offpath-pilot-v2`**, `candidate_offpath_pilot_v2.py` (v1's compiler as a parameterised copy; the mix is byte for byte v1's, tested) |
| rates (total req/s of the whole mix) | 100, 150 | **25, 50** (4,500 and 9,000 requests per 180 s) |
| regimes | no fault, frontend pause, throttle, fraud pause, accounting pause | **no fault, fraud pause, accounting pause, frontend pause** (throttle dropped: no throttle scenario, row, command or key anywhere; tested) |
| cells | 10 | **8** = per rate one cell per regime; **run order NF25, the two off-path pauses at 25 (seeded Fisher-Yates), NF50, the two pauses at 50 (seeded), then the frontend pause at 25 and at 50** (S8: the on-path control last) |
| seed | 20261013 | **20261012** (the build date) |
| concurrency / open files / frontendproxy memory | 4500 / 5524 / 1 GiB | **1500 / 2524 / 256 MiB** (the sweep's rules at 50 x 15 = 750 waiting requests x 0.3 MB = 225 MB, rounded up; C's own value) |
| SUT service memory limits | upstream | **upstream (unchanged)** |
| otelcol / jaeger memory | 1 GiB each | **1 GiB each** (decision 103) |
| frontendproxy log | 4g x 1 | 4g x 1 (v1's rendering: the materialized source `031fcc1e...` is the load pilot's and v1's, tested; at 50 req/s the access log is ~3.7 MB, inside upstream's bound, so the retention is not needed but harmless) |
| cell overhead / minimum remaining / GATE-RUN window | 500 s / 8,610 s / 4 h | **300 s / 5,588 s / 3 h** (watcher cap 4 h) |
| criteria | v1 frozen text | **identical minus the throttle row** (the descriptor's `manifestationCriterionDefaults` = v1's minus `throttleServerSpan`, `throttleClientSpan`; tested) |
| H10 / H4 / sampler / trace rule per cell kind / per-route completeness | as C's | same |
| descriptor | `2136639d...b557a` | **`b22c4ee66526ba18dcfc2c6f372c3f74c127ad73273b6b7a8d98825b5bc8f6a9`** |
| plan, attempt 1 | `8b3d7aa8...4814` | **`a929b4d92df25f71264057a535cd7bbe337155a746a8e0aa19ee3c6cd003f021`** |
| run count | 10 | **8** |

Every other timing key of a cell equals C's for the same (regime, rate) (the pauses take the frontend pause's timing): tested key by key; the
descriptor equals C's except for the declared keys. Both digests are identical under `/usr/bin/python3 -I` (3.9) and `uv run python -I` (3.13).

### Why these sizes (engineering defaults, recorded in the descriptor)
- **Concurrency 1500** = ceil(2 x 50 x 15); a paused frontend holds rate x timeout = 750 requests; waiting dependents add at most ~6 % of that.
- **Open files 2524** = concurrency + 1024, raised before `compose up` or the cell is refused (tested).
- **frontendproxy 256 MiB**: 0.3 MB x 750 waiting requests = 225 MB, rounded up to a power of two (C's own limit). **otelcol and jaeger 1 GiB each**
  by user decision 103 (no sizing rule). Envoy's default circuit breakers (1024) are not reachable at 750 outstanding requests (v1's risk 8 is moot here).
- **300 s overhead per cell.** The load pilot measured 142.2-150.0 s of tail at 50 req/s of one product route (9,000 requests); the mix's
  larger collector log and capture raise it; 300 s is about 2x. Cell 1 of v1 (the mix at 100 req/s, 18,000 requests) was valid on the host
  within its 500 s budget (its actual tail is in the coordinator's fetch; not read here). A budget, not a measurement.

### Host limits
Read read-only on fb14srv6 by the coordinator on 2026-10-12 (v1 declaration, risk 9): `runuser stig`: `ulimit -u` 1,031,179, `ulimit -n` soft
1024 / hard 1,048,576, `user-1016.slice` TasksMax 680,578, `pid_max` 4,194,304, `user.slice` `pids.max` max; earlier: nproc 24, threads-max
2,062,359, nf_conntrack_max 262,144, ip_local_port_range 32768-60999. 1500 threads, a soft open-file limit of 2524 and ~750 sockets in flight (~12k
conntrack entries, ~3k ports in TIME_WAIT at 50 conn/s: estimates) are inside every limit read. **Not re-read for v2** (no host contact).

### Expected volumes and duration (estimates)
Per cell at 50 req/s: the load pilot's r50 cell (one product route, 9,000 requests) was 85 MB of collector log, 66 MB of pcap and 5 MB of ledger; the
mix's cell is plausibly 0.2-0.5 GB of log and about as much pcap (`?`); v1's first valid cell at 100 req/s is the measured upper side (not read here).
Pilot total plausibly 1-3 GB. Duration: 8 x (211 s timed + 150-300 s tail) = 0.8-1.1 h of cells plus setup (the materialized source is v1's, so its
images are probably already on the host: `?`). Expected launch to terminal about 1-1.5 h, inside the 3 h window.

## Commits in the OTel worktree (branch `otel-protocol-20261002`, on top of `8c53cb2`)
| commit | what | governed file moved? |
|---|---|---|
| `12b626a979f0cfc8261ed13c071cd1dc29623728` | v1 attempt 1 recorded spent (launched 09:37Z, stopped 09:57Z, harness 8c53cb2, plan 8b3d7aa8, 2 attempted / 1 valid, fetched 40/40); v1 tests updated | `candidate_runtime_adapter.py` |
| `ada5965593678844d68e235bbc4fdb8b0dab5ed0` | v2 epoch, not activated: `candidate_offpath_pilot_v2.py`, `pipelines/campaigns/otel-offpath-pilot-v2.json`, v2 in the repeat family, controller sets, timing keys, materialize tuples, `SPENT[v2] = {}`, ledger +1 (33), `tests/test_otel_offpath_pilot_v2.py` (28), pinned-tuple tests updated | `candidate_runtime.py`, `candidate_runtime_adapter.py` |
| `b8a3ba7278004e6a86b6cd443b976a4075d06b93` | governance re-pin of the two | re-pin |
| `a045b9c1a92a4fbad29101423cb43f0d020b6118` | activation: selector names v2; tombstone `("otel-offpath-pilot-v2",)` in `candidate_setup.py` and `candidate_remote.py` | no |
| `66b559a9d3552432b63f88cbe9d501e79dff53e3` | run order S8: NF25, off-path pauses 25, NF50, off-path pauses 50, then the frontend pauses; three segments, `validate_plan` enforces it; new pins | no |
| `ff29b9305787c602c7e5466d39498569b45e5756` | activation confirmed on the re-derived plan (HEAD) | no |

**Launcher values:** `EXPECTED_PLAN=a929b4d92df25f71264057a535cd7bbe337155a746a8e0aa19ee3c6cd003f021`, `RUN_COUNT=8`, `COMPILER=candidate_offpath_pilot_v2.py`, `CAMPAIGN=otel-offpath-pilot-v2`.
The launcher's local plan check and drivers check were reproduced locally (no host contact) and print
`otel-offpath-pilot-v2 8 a929b4d92df25f71264057a535cd7bbe337155a746a8e0aa19ee3c6cd003f021` and `otel-offpath-pilot-v2 otel-offpath-pilot-v2 3`.

## The 8 cells (attempt 1; run order; onset = seconds after the barrier at which the fault command is issued)
| pos | rate /s | regime | onset s | run id | artifact root |
|---|---|---|---|---|---|
| 1 | 25 | no-fault (pseudo onset) | 60.006238 | 02257a574d3395770136e1c0 | runs/calibration/r25-b01-01-full |
| 2 | 25 | accounting-pause | 60.004758 | ddd3db6531e3f456ceb3369f | runs/effect/accounting-pause/r25-b01-02-full |
| 3 | 25 | fraud-pause | 60.014859 | 25b4b978c23a4af695ce08f9 | runs/effect/fraud-pause/r25-b01-03-full |
| 4 | 50 | no-fault (pseudo onset) | 60.010958 | 59b65b20177ac00b5e617783 | runs/calibration/r50-b01-04-full |
| 5 | 50 | fraud-pause | 60.019909 | 20db7d6b7e34858a352ded64 | runs/effect/fraud-pause/r50-b01-05-full |
| 6 | 50 | accounting-pause | 60.004029 | fb1b1a80adbf4c5442e88f0c | runs/effect/accounting-pause/r50-b01-06-full |
| 7 | 25 | frontend-pause | 60.019673 | 10502d9a9bf6b28693586d15 | runs/effect/frontend-pause/r25-b01-07-full |
| 8 | 50 | frontend-pause | 60.008359 | 4da3a8464a4093f8b610ad9f | runs/effect/frontend-pause/r50-b01-08-full |

No run ID equals one from sweep attempts 1-2, quiet attempts 1-3, B attempt 1, C attempt 1, the load pilot's attempt 1 or v1's attempt 1 (tested).
The campaign stops on its first invalid cell. Each rate's no-fault cell (cells 1 and 4) is followed by the never-run off-path pauses of that rate; the
frontend pauses (the on-path control) are the last two cells (7 and 8), so no off-path answer depends on them and an early stop leaves every baseline.
The plan is three segments (`[NF25, pauses25]`, `[NF50, pauses50]`, `[FP25, FP50]`); `validate_plan` enforces the order (tested, planted).

## Risks the build cannot settle without running the pilot
1. **productcatalogservice at its upstream 20 MiB limit may be OOM-killed again.** v1's cell 1 (the mix at 100 req/s, no fault) was valid, its cell 2
   (fraud pause at 100 req/s) was OOM-killed **~14.7 s before the pause command** (barrier 09:49:30.907Z + onset 60.012 s; OOM 09:50:16Z), so the pause did
   not cause it. Cross-cell growth is excluded (every cell starts a fresh project: `compose down --volumes`, new container IDs). The cause is therefore the
   load within the cell at 100 req/s (warm-up, then the measured window). At 25 and 50 req/s the demand is a quarter and a half of v1's; whether that is
   enough is exactly what is unknown. An OOM is a result, not a defect (the limit is the user's, decision 108).
2. **The other SUT memory limits stay upstream's** (checkoutservice 20M, currencyservice 20M, shippingservice 20M, valkey-cart 20M, quoteservice 40M,
   emailservice 100M, accountingservice 120M); at half of v1's top-rate demand they are less exposed, and v1's valid cell 1 ran all of them at 100 req/s.
3. **Fault-cell validity of the pauses under the mix.** v1's cell 2 was the fraud pause; its own validity fields were all fine (intervention
   successful and recovered, docker-events status ok, protocol gates with no failure, trace completeness valid with 75 incomplete requests, all pre-onset);
   **only the container-health restart guard failed (productcatalogservice)**. The accounting pause and the frontend pause under the mix are unobserved. After 60 s
   paused, a Kafka consumer's session (45 s default) has expired and it rejoins on unpause; whether either consumer then exits or is restarted is unobserved.
4. **Decision 25 per-route sets** (a conservative subset from source reading, checked against v1's valid no-fault cell only in the offline replay, not
   read here): a route whose spans are lost above max(1, 1 %) outside the fault-and-drain window invalidates a fault cell.
5. **Witness check.** Every offered token must appear exactly once in the access log, POSTs included.
6. **The generator in Python threads.** 1500 threads, 9,000 requests per cell on 3.9; the per-cell runner has run on the host only in v1 (cell 1 valid);
   the 1500 cap is asserted, not exercised, in tests.
7. **Parallel cart POSTs (deviation from upstream)** of a `checkout_multi` journey may lose an item; checkout success is unaffected (declared in v1, risk 11).
8. **The fake target is not the SUT on an empty cart** (v1, risk 12): a checkout whose cart POST failed returns 200 on the SUT but skips productcatalogservice.
9. **The 256 MiB frontendproxy and the frontend pauses (S6).** The limit stays at C's 256 MiB (user decision: no other SUT/infrastructure limit changes).
   Only the last two cells (the frontend pauses) are exposed: a paused frontend holds rate x timeout = 375 (25 req/s) and 750 (50 req/s) requests in Envoy. The review's
   arithmetic: with the attempt-1 kill-implied baseline (~87 MB at ~120 waiting requests, of which ~41 MB file-rss) the rule's 2x factor at 750 waiting requests gives
   ~294 MB, above 268 MB (256 MiB). An OOM kill there invalidates that cell and the verdict for that frontend pause is `—`; the off-path cells are unaffected
   (they run first).
10. **Otelcol and jaeger are not in `APP_SERVICES`** (N7): the restart/replace guard looks at application services only, and `oomKilled` reads false after Docker restarts a
    container (v1's productcatalog OOM showed as a restart with `oomKilled` false). An OOM-restart of otelcol or jaeger (1 GiB each now) would therefore not
    invalidate a cell by itself; it would show as a gap in the collector's records, which the carrier-coverage and trace-completeness checks may or may not catch. Left as is (the guard is unchanged).
11. **Collector log volume** (up to a few hundred MB per cell) is read into memory on the host and by the terminal; bounded.

## Ledger rows (review notes recorded, not fixed here)
- **Misnamed test:** `tests/test_otel_offpath_pilot_v2.py::test_each_fault_manifests_by_v1s_declared_criterion_at_25_and_50_req_per_second` loops `(25.0,)` only
  (the 50 req/s fault cells are validated by the terminal, not scored by `verdict()` in that test).
- **N1 (v2 GO review):** `candidate_offpath_pilot_v2.py` comment says the seed is "the build date plus one day"; the seed is 20261012 (docstring and descriptor agree). Comment only; not edited (it would move the compiler digest).
- **N2:** the compiler's `AUTHORITY` string wraps v1's stop inside the load-pilot RESULT_P1.md parenthetical, so it reads as if RESULT_P1 records v1's stop. Descriptor prose; not edited.
- **N3:** the descriptor's inherited `faultDesign` prose (C's text) still mentions throttle stamps; no lookup reads it and no throttle identifier (`productcatalog-cpu-throttle`, `cpu-throttle`, `nanoCpus`) remains in the descriptor. "No throttle key anywhere" holds for identifiers, not for that prose.
- The v1 declaration's coordinator notes and its criteria text are unchanged by the order change.

## Launch (worktree HEAD must still be `ff29b9305787`)
From the measurement repo (re-run `git -C ../observability-placement-runtime-otel-protocol rev-parse HEAD` first):
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
DRY_RUN=1 OTEL_CANDIDATE_ATTEMPT=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_offpath_pilot_v2.py EXPECTED_PLAN=a929b4d92df25f71264057a535cd7bbe337155a746a8e0aa19ee3c6cd003f021 \
  RUN_COUNT=8 CAMPAIGN=otel-offpath-pilot-v2 LOG_PREFIX=otel-offpath-pilot-v2 \
  zsh scratchpad/gate-drivers/launch_otel_offpath.sh opv2dry1 ff29b9305787c602c7e5466d39498569b45e5756 \
  > scratchpad/gate-drivers/otel-offpath-pilot-v2-opv2dry1.out 2>&1
```
Launch (after a passing DRY_RUN; same variables, no `DRY_RUN`):
```
LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_offpath_pilot_v2.py EXPECTED_PLAN=a929b4d92df25f71264057a535cd7bbe337155a746a8e0aa19ee3c6cd003f021 \
  RUN_COUNT=8 CAMPAIGN=otel-offpath-pilot-v2 LOG_PREFIX=otel-offpath-pilot-v2 \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh opv2 ff29b9305787c602c7e5466d39498569b45e5756 \
  > scratchpad/gate-drivers/otel-offpath-pilot-v2-opv2.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow otel-offpath-pilot-v2-opv2 scratchpad/gate-drivers/otel-offpath-pilot-v2-opv2-launch.log \
  > scratchpad/gate-drivers/otel-offpath-pilot-v2-opv2-wandb.out 2>&1 &
```
After the first cell seals, check the validity fields only: `receipt.json` state, `protocol-gates.json` failedGates, `container-health.json` reasons
(restart counts included: v1's OOM showed as a restart, `oomKilled` false), `trace-completeness.json` valid. After terminal, fetch to a **new** path with
`fetch_overnight.sh`, which needs one new case (not edited here; the coordinator adds it):
```
  otelpilot3) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-offpath-pilot-v2; O=tmp/otel-offpath-pilot-v2-evidence/p1-fetch ;;
```
(with `otelpilot3` in its usage line). Then apply the criteria once (the coordinator adapts `research/placement/manifestation_offpath_pilot.py` for v2:
epoch name, no throttle).

## Tests (OTel worktree)
- `tests/test_otel_offpath_pilot_v2.py` at HEAD: 28 passed (~1 min; the order test now covers S8): plan pin (descriptor, plan; 3.9/3.13), C-identity and v1-identity (mix byte for byte,
  pause scenarios, criteria = v1's minus the two throttle keys), sizing at 50 req/s, group order, no run-ID reuse (v1 attempt 1 included), spent rows,
  runtime/gate chain/host paths disjoint from every earlier epoch (v1 included), every regime end to end at 25 req/s plus a fraud pause at 50 req/s on the
  fake target with the terminal's replay, the 20-item minimums at 25 req/s, no throttle command, rendered tree (same materialized digest as v1's), 3.9
  floor. In-test plants: an edited descriptor/plan (incl. a re-added throttle scenario, v1's seed/concurrency/rates/declaration, a mix weight),
  a C-sized generator and a SUT limit smuggled into the sizing, planted compilers whose segments run the frontend pause before the 50 req/s cells, a no-fault cell after its pauses, or the 50 req/s pauses before their baseline, a descending rate list, v1's epoch reusing run
  IDs, a selector without v2's controller set, v2 missing from the family tuple, a consumer that ignores its pause, v2 missing from the sampler tuple.
  v1's tests (88) exercise the shared mix, ledger, terminal replay and completeness code and still pass.
- **Source plants (each restored), 8 of 8 caught** by the v2 file (first failing test, `-x`), the last three for the S8 order (the baseline-followed check was missed by the first two planted configs and is caught by the third): v2 dropped from `REPEAT_STUDY_EPOCHS`; `workloadMix` dropped from
  v2's runtime key set; frontendproxy at v1's 1 GiB; the throttle scenario kept; the telemetry backend dropped from the sizing; the frontend-last check removed; the baseline-followed check removed; the segments back to rate-ascending.
- Measurement repo `tests/test_unbound_names.py`: 320 passed (one parametrisation per compiler: `candidate_load_pilot.py`, `candidate_offpath_pilot.py`, `candidate_offpath_pilot_v2.py`).
- Full worktree suite (`uv run pytest -q -p no:cacheprovider -rf --ignore=tests/test_mlflow_manifest.py`) at HEAD `ff29b93`: **29 failed, 2349 passed, 145 skipped**
  (857 s). The sorted `FAILED` name list is identical to the load pilot's at `7b20ec4` (`diff`, no output; none is OTel). Delta against `7b20ec4`
  (2232 passed): +117 = +88 v1 file, +28 v2 file, +1 net in `tests/test_otel_load_pilot.py`.

## Open at freeze: decisions needed
- **Decided (user, decision 108 and BUDGET_E amendment 1):** the second pilot at 25 and 50 req/s, throttle dropped, SUT limits upstream, otelcol and jaeger 1 GiB,
  criteria v1's minus the throttle row. **Carried over from v1 (decided there, the user may veto):** at most 1 relaunch for harness or infrastructure
  defects; E's rate rule; the order inside a rate.
- **Still open for the user:** nothing blocking.
- Engineering defaults taken: seed 20261012, 300 s overhead, frontendproxy 256 MiB, the retained proxy-log rendering.
- Reviewed: the v2 GO review (same-provider, GO-with-fixes, 2026-10-12), fixes applied; the judge MCP server failed to connect in the build session.
