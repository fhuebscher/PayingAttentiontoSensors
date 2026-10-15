# OTel off-path manifestation pilot (100 and 150 req/s of the upstream task mix): declaration (frozen 2026-10-12)

**Status: frozen** by committing this file alone, before launch. Written by the harness-building agent (Sonnet 5.5), reviewed
GO-with-fixes by a same-provider adversarial-review subagent (2026-10-12 ~08:30Z; the cross-provider judge server fails to
connect); every fix is applied in harness `8c53cb2` and in the text below. Scope of every number here: **instance** (one SUT,
OTel Demo 1.12.0 at 2d4661e, one host, fb14srv6). Unknown values are `?`. Dates written "2026-10-13" in the text below were
the build's planning dates; the build ran on 2026-10-12.

**DRY_RUN `opdry2` passed** 2026-10-12 09:36:52Z at HEAD `8c53cb24581d…`, plan `8b3d7aa8…` ("DRY RUN: all guards passed;
stopping before the first mutation"; srv6: running units 0, containers 0, lease holders none, free 240 GB, pilot paths 0;
`scratchpad/gate-drivers/otel-offpath-pilot-opdry2-launch.log`).

**Coordinator notes at freeze:** (a) the frontend-pause checkout bound is **<= 10 %** ok (the review's draft said 5 %): the
build agent loosened it before any SUT cell existed, because a pause takes a moment to bite (the fake target's own pause let
~5 % through in its first ~1.5 s); recorded here as a pre-launch, outcome-blind change. (b) Witness rows carry
`response_code` and `response_flags` (checked by the coordinator on the load pilot's `application-witness.json`: 9000 rows,
both keys), so Envoy overflow 503s are separable offline. (c) Rates 100/150 are the user's decision 107; 100/200 in the first
build was the coordinator's prompt.

Authority: `research/traffic-sweep/BUDGET_E.md` (`ec4b9fa`, committed alone before any E work; user decisions 2026-10-12): the
upstream Locust task mix as an open loop with a request ledger; off-path faults (frauddetectionservice pause, accountingservice
pause), the frontend pause as on-path control and the productcatalogservice 0.1-core throttle at a rate where it binds; a
manifestation pilot at two total rates, criteria per fault declared before launch. A fault that does not manifest is dropped from E;
if no off-path fault manifests, E is not launched (BUDGET_E stop rule 5).

Deadlines (BUDGET_E): harness ready **2026-10-13 06:00Z** (this build); independent review GO, this declaration committed alone and
DRY_RUN passed **10:00Z**; pilot terminal and fetched **16:00Z**. **At most 1 relaunch, harness or infrastructure defects only** (coordinator default, decided; carried from the load pilot).

**User decisions 2026-10-12 on the build's risks, bound in this build:** (1) **only otelcol and jaeger memory are raised, to 1 GiB each**
(telemetry backend; upstream 200M and 400M; applied like the frontendproxy's, recorded in `container-health.json`, declared as
`sutDeviations` rows); every SUT service limit stays upstream's. (2) The off-path pause hold stays 60 s. (3) Per-route trace completeness
(conservative required-service subsets, allowance and windows unchanged) is confirmed. (4) Envoy's circuit breakers stay upstream defaults.
**User decision (6): the rates are 100 and 150 req/s** (100/200 was the build prompt's value, not the user's).
Coordinator engineering defaults: (5) **within each rate the no-fault cell runs first, then the two off-path pauses (fraud,
accounting; seeded order between them), then the frontend pause and the throttle (seeded order between them)**; rate-ascending segments
kept; (7) **at most 1 relaunch** (harness or infrastructure defects only); (8) **E's rate rule: the lowest rate at which every kept fault
manifests, else the highest rate at which any does** (the user may veto).

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
| productcatalogservice throttle | median duration of `service.name=productcatalogservice, Name=oteldemo.ProductCatalogService/GetProduct, Kind=Server` hold / pre-onset >= **2.0**; median of `service.name=frontend, Name=grpc.oteldemo.ProductCatalogService/GetProduct, Kind=Client` hold / pre-onset >= **1.25**; the no-fault cell shows neither ratio (same statistic at its pseudo onset) | otelcol.log, intervention.json |
| frontend pause (on-path control) | of ledger rows (every route) **scheduled** in [onset, onset + **45 s**) at most **10 %** have outcome ok, and of the `route=checkout` rows **sent** in that window (`startedAtEpoch - barrierEpoch`, not the scheduled time: a checkout waits up to 20 s for its cart POST) at most **10 %** (the pause command takes a moment to bite); the no-fault cell's rows in the same window are >= **95 %** ok. The first 45 s, not 60: a request scheduled in the last 15 s can be served after the unpause inside its own 15 s timeout (the terminal's own comment, 2026-10-02), so "all of the hold fails" would be false by construction | request-ledger.json, intervention.json |
| frauddetectionservice pause, accountingservice pause (off-path) | consumer-side spans of the target (`service.name` = the target, `Kind=Consumer`, any name) **started in the hold <= 10 %** of those started in the pre-onset 60 s (pre-onset count >= 20; a frozen process emits nothing, so this collapse is near-true by construction: the informative parts are that each accepted order produced a consumer span before the pause and that checkout stays >= 95 % ok); **and** `route=checkout` ledger rows scheduled in the hold are **>= 95 % ok** (>= 20 rows); **and** the no-fault cell at its pseudo onset has hold/pre-onset > 10 % for that service and its checkout rows >= 95 % ok | otelcol.log, request-ledger.json, intervention.json |

A fault is **kept for campaign E iff it manifests at >= 1 rate**; which rate(s) E uses is BUDGET_E step 4's choice (proposal, to be
confirmed: the lowest rate at which every kept fault manifests, else the highest rate at which any does; **decided as a coordinator default, the user may veto**).

How the criteria were checked for computability (executed, on a fake target, not on the SUT): `tests/test_otel_offpath_pilot.py`
(`statistics_of`, `verdict`, with a unit test each for the send-time selection and the no-fault precondition) computes every statistic above from nothing but a cell's retained `otelcol.log`, `request-ledger.json`
and `intervention.json`/timing, on all five regimes, with planted defects (a consumer that keeps working through its pause, a pause
that takes checkout down, a throttle that does not bind: each gives "does not manifest"). The span parser reads a real
debug-exporter block (the retained v3a2 `b02-02-full` accountingservice `orders receive` span, Kind Consumer). **What no test can
settle:** how many consumer spans the real consumers emit per order in this SUT's collector output. Both services' `Kind=Consumer` spans
**were seen** in the load pilot's retained `otelcol.log` (all 6 cells; accountingservice `orders receive`, frauddetectionservice
`orders receive` and `orders process`), so the span predicates are confirmed against real output; the per-order counts at the mix's
checkout rate are not. With the sampler off (decision 66; rendered by `materialize.py`, tested) the spans are
retained. If a consumer emits fewer than 20 `Consumer` spans in the pre-onset 60 s, its off-path criterion is `—` and that fault is not decided by this pilot. The post-fetch script also cross-checks each witness row's `response_code` against the ledger's status for the same token (the witness rows carry `response_code` and `response_flags`). The criteria script is written after the fetch, implements exactly the rules above and is committed
before it is run on the cells.

## The workload: the upstream Locust task mix, open loop, one ledger row per request
Tasks and weights are upstream's (`src/loadgenerator/locustfile.py` at 2d4661e, checked against the file in the test): index 1,
browse_product 10, get_recommendations 3, get_ads 3, view_cart 3, add_to_cart 2, checkout 1, checkout_multi 1; `flood_home` dropped
(0 requests at its default flag, and it asks flagd on every call). Smooth weighted round-robin over the 24-weight cycle; 34 requests
per cycle on average. Request shares (design, DESIGN.md 2.3): GET /api/products 47 %, POST /api/cart 17.6 %, recommendations, ads
and view-cart 8.8 % each, POST /api/checkout 5.9 %, GET / 2.9 %. **The offered rate is the rate of the whole mix in requests per
second**: 18,000 requests per 180 s at 100 req/s, 27,000 at 150 req/s; request i is scheduled at barrier + i / rate.

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
| witness (frontendproxy access log) | one GET per token | unchanged logic: every request of the mix, POSTs included, carries its own token; offered tokens must be witnessed exactly once. Retention 4g x 1 (27,300 lines at 150 req/s ~ 11 MB, above upstream's 5m x 2 bound of 5 to 10 MB) |
| G1 / G2 / G4 | rows pooled over one route | **unchanged code, wider meaning**: G2's 5 % pre-onset failure share is over the whole mix, so a route that fails persistently (checkout is 5.9 %) can invalidate a cell; G1's floor counts all rows; G4's `offered == len(rows)` and rate == profile rate hold (rate = total req/s); `profile.routes` names only the probe route (informational) |
| trace completeness (decisions 25 / 56) | exactly the one route's services on the clipped path | **per route**: the request's own trace id observed and every service its route is *guaranteed* to reach observed in that trace (a conservative subset per route, `workload.mix.routes[route].requiredServices`; flagd and the async consumers are neither required nor unexpected). The rule's allowance (max(1, 1 %)), windows and drain are unchanged. **This changes what "complete" means: a preregistration-adjacent adaptation, flagged below for the user** |
| posture proof | route services must appear among the collector's signals | the union over the mix's routes (sorted) must appear: 12 services, incl. recommendationservice, adservice, checkoutservice, paymentservice, shippingservice, quoteservice, currencyservice, emailservice, cartservice |
| terminal correlation | full path = the route's clipped services | per request, on the unclipped trace services of the request's route |
| probe route / readiness | the cell's route | `/api/products/66VCHSJNUP` (C's route), used only for readiness |
| concurrency, open files, memory | 300 / - / 256 MiB (C); 3000 / 4024 / 512 MiB (load pilot) | **4500 / 5524 / 1 GiB** (rules below) |

## What differs from campaign C and the load pilot
| item | C (attempt 1) | load pilot | this pilot |
|---|---|---|---|
| study epoch / compiler | `otel-repeat-episodes-c-v1` | `otel-load-pilot-v1` | **`otel-offpath-pilot-v1`**, `candidate_offpath_pilot.py` (reads C's compiler and descriptor, edits neither) |
| rates (total req/s) | 10, 1, 0.2, 0.05 | 50, 100 | **100, 150** |
| regimes | no fault, frontend pause, throttle | no fault, throttle | **no fault, frontend pause, throttle, frauddetectionservice pause, accountingservice pause** |
| cells | 36 | 6 | **10** = per rate one cell per regime, rate-ascending segments; **inside a segment: the no-fault cell, then the two off-path pauses (seeded), then the frontend pause and the throttle (seeded)**; one onset stratum |
| seed | 20261011 | 20261012 | **20261013** (engineering default) |
| workload | one product route | one product route | **the upstream mix (above)** |
| concurrency / open files / frontendproxy memory | 300 / - / 256 MiB | 3000 / 4024 / 512 MiB | **4500 / 5524 / 1 GiB** (the sweep's rules at 150 x 15 = 2250 waiting requests x 0.3 MB = 675 MB, rounded up) |
| frontendproxy log | upstream 5m x 2 | 4g x 1 | 4g x 1 (same rendered tree as the load pilot's: materialized source `031fcc1e...`, tested) |
| cell overhead / minimum remaining / GATE-RUN window | 120 s / 13,416 s / 5 h | 450 s / 5,466 s / 3 h | **500 s / 8,610 s / 4 h** (watcher cap 5 h) |
| H10 / H4 / collector sampler / trace rule per cell kind | B's | same | same (H4 recorded, never blocking; sampler off; decision 25 in fault cells, 56 in no-fault cells) |
| SUT service memory limits | upstream | upstream | **upstream (unchanged, user decision 2026-10-12; see risk 3)** |
| telemetry backend memory (otelcol / jaeger) | upstream 200M / 400M | upstream | **1 GiB each** (user decision 2026-10-12) |
| descriptor | `6dd3cb72...3721` | `45b79b0c...ac46` | **`2136639d30bfa33e4ea9f7f1a5a7dd1382841c9c9b5444725e58cb77ba7b557a`** |
| plan, attempt 1 | `ece8caa0...b744` | `aea94eb9...25d6` | **`8b3d7aa84e26c31de724c3686331b1f7347b9fd086a1debfefdea80799104814`** |
| run count | 36 | 6 | **10** |

The new scenarios are `docker compose pause frauddetectionservice` / `accountingservice` (the frontend pause's mechanism, scenario
contract `not-probed-h10`; the fraud pause was built in `candidate_pilot.py:84-87`, never run). Every other timing key of a cell equals
C's for the same (regime, rate) (the pauses take the frontend pause's timing, which names no scenario): tested key by key; the
descriptor equals C's except for the declared keys (`REPLACED_DESCRIPTOR_KEYS`, `_SUBKEYS`, tested). Both digests are identical under
`/usr/bin/python3 -I` (3.9) and `uv run python -I` (3.13).

### Why these sizes (engineering defaults, recorded in the descriptor)
- **Concurrency 4500** = ceil(2 x 150 x 15). A paused frontend holds rate x timeout = 2250 requests; waiting dependents add at most
  ~6 % of that (they wait for a predecessor that is itself bounded by the timeout).
- **Open files 5524** = concurrency + 1024, raised before `compose up` or the cell is refused (tested; the load pilot's rule).
- **frontendproxy 1 GiB**: 0.3 MB x 2250 waiting requests = 675 MB, rounded up to a power of two. **otelcol and jaeger 1 GiB each** by user decision (no
  sizing rule; the collector has no memory_limiter and prints every span, jaeger holds traces in memory).
- **500 s overhead per cell.** The load pilot's measured tail after the window (ledger end to the next barrier, 5 gaps) was
  142.2-150.0 s at 50 req/s and 158.7-167.4 s at 100 req/s, about 1.35 ms per offered request. This pilot offers 27,000 requests at
  its top rate and the mix emits several times the load pilot's spans per request (the load pilot's r100 cell: 128,231 spans, 152 MB of
  collector log, 126 MB of pcap for 18,000 requests, ~7 spans per request; the mix's per-request count is `?`, checkout traces are the
  largest), so the log, capture and parsing grow faster than the request count. A budget, not a measurement.

### Host limits
Read by the coordinator on 2026-10-12 ~03:05Z for the load pilot (nproc 24; threads-max 2,062,359; DefaultLimitNOFILE 524,288;
nf_conntrack_max 262,144; ip_local_port_range 32768-60999; DefaultTasksMax 309,353), and **again, read-only on fb14srv6, 2026-10-12
(coordinator; resolves the thread-budget question)**: `runuser stig`: `ulimit -u` 1,031,179 (hard the same), `ulimit -n` soft 1024 / hard
1,048,576; `user-1016.slice` TasksMax 680,578; `pid_max` 4,194,304; `user.slice` `pids.max` max. So 4500 generator threads and a raise of
the soft open-file limit to 5524 are inside every limit read (the cell raises the soft limit itself and refuses if the hard limit is lower).
Other needs at 150 req/s (estimates, kernel defaults assumed): ~2250+ sockets in flight, conntrack ~36k (150 conn/s x 2 hops x 120 s
TIME_WAIT), ~9k ports in TIME_WAIT (150 conn/s x 60 s, of 28,232).

### Expected volumes and duration (estimates, not measured at these rates)
Per cell at 150 req/s: otelcol.log, pcap and ledger scale with requests and spans per request: the load pilot's r100 cell was 152 MB,
126 MB and 9.9 MB; the mix's r150 cell is plausibly 0.4-1.2 GB of log and about as much pcap (`?`). The pilot total plausibly 4-10 GB on
fb14srv6 (the launcher guard is 40 GB free; 242 GB were free on 2026-10-12) and the same fetched to the laptop (588 GB free).
Duration: 10 x (211 s timed + 160-500 s tail) = 1.0-2.0 h of cells, plus setup (the materialized source digest is the load pilot's,
so its images may still be on the host: `?`). Expected launch to terminal about 1.5-2.5 h, inside the 4 h window. To meet 16:00Z
terminal-and-fetched, launch by about 11:00Z.

## Commits in the OTel worktree (branch `otel-protocol-20261002`, on top of `7b20ec4`)
| commit | what | governed file moved? |
|---|---|---|
| `ba27afcb31d0d8c3083a4765564c5048434ddc4d` | load pilot attempt 1 recorded as spent (launched 2026-10-12 03:52Z, terminal 04:33Z, harness 7b20ec4, plan aea94eb9, 6/6 valid, fetched 107/107); +2 tests, 1 updated | `candidate_runtime_adapter.py` |
| `cda90758225e9afbf16e3beaa377aac7e0545bce` | off-path epoch, not activated: compiler `candidate_offpath_pilot.py`, descriptor `pipelines/campaigns/otel-offpath-pilot-v1.json`, the mix and its ledger/dispatch in `candidate_remote.py`, per-route completeness, terminal ledger replay, runtime/setup controller sets and timing keys, `SPENT[pilot] = {}`, materialize tuples, ledger +1, `tests/test_otel_offpath_pilot.py` | `candidate_runtime.py`, `candidate_runtime_adapter.py`, `candidate_terminal.py` |
| `d8644d97357cb41352ddcf0a6b6e951617abfb93` | governance re-pin of the three | re-pin |
| `bed0e3ca9149d6e6685b46fe2c65361806c0a613` | activation: selector names the pilot; tombstone `("otel-offpath-pilot-v1",)` in `candidate_setup.py` and `candidate_remote.py` | no |
| `40228b7...` (review fixes) | terminal hashes the mix with the producer's canonical function; consumer-trace wording; descriptor and plan re-pinned | `candidate_terminal.py` |
| `bff9fcaaa140162c87c9393f0424b59325b67cec` | governance re-pin of `candidate_terminal.py` | re-pin |
| `1bf919c325cc8089e1964966824933c07011b170` | otelcol and jaeger 1 GiB (user decision), no-fault cell first per rate (coordinator default); new pins | no (compiler and descriptor are not governance-bound) |
| `f8d5cbea71b55aa66cca56d2903257184e81e87b` | activation confirmed on the re-derived plan (selector and tombstone unchanged; ledger names the decisions)  | no |
| `3c165daa8c8a4fe9ea661470d1ef270aac37bb3c` | rates 100 and 150 (user decision; sizing re-derived: 4500 / 5524 / 1 GiB, 500 s, 8,610 s), group run order (no-fault, off-path pauses, frontend pause and throttle), criteria B1 (send time) and S2 (no-fault precondition); new pins | no |
| `8c53cb24581d7805df691c64d8ec26bd90573b2e` | activation confirmed on the plan of rates 100 and 150 (HEAD) | no |

**Launcher values:** `EXPECTED_PLAN=8b3d7aa84e26c31de724c3686331b1f7347b9fd086a1debfefdea80799104814`, `RUN_COUNT=10`, `COMPILER=candidate_offpath_pilot.py`, `CAMPAIGN=otel-offpath-pilot-v1`.
The launcher's local plan check and drivers check were reproduced locally (no host contact) and print
`otel-offpath-pilot-v1 10 8b3d7aa84e26c31de724c3686331b1f7347b9fd086a1debfefdea80799104814` and `otel-offpath-pilot-v1 otel-offpath-pilot-v1 4`.

## The 10 cells (attempt 1; run order; onset = seconds after the barrier at which the fault command is issued)
| pos | rate /s | regime | onset s | run id | artifact root |
|---|---|---|---|---|---|
| 1 | 100 | no-fault (pseudo onset) | 60.002657 | dfca9709df028f2c8c3c4c2b | runs/calibration/r100-b01-01-full |
| 2 | 100 | fraud-pause | 60.009706 | 03e521f07361fedbb2c7cc12 | runs/effect/fraud-pause/r100-b01-02-full |
| 3 | 100 | accounting-pause | 60.001366 | c10e03c3e8665e511aa51b2b | runs/effect/accounting-pause/r100-b01-03-full |
| 4 | 100 | productcatalog-cpu-throttle | 60.009636 | 5f96768a7430cf2f0884a519 | runs/effect/productcatalog-cpu-throttle/r100-b01-04-full |
| 5 | 100 | frontend-pause | 60.007107 | 46c10631150260456c57cb2d | runs/effect/frontend-pause/r100-b01-05-full |
| 6 | 150 | no-fault (pseudo onset) | 60.003979 | aa38cae3ab9cdab1ef993a76 | runs/calibration/r150-b01-06-full |
| 7 | 150 | accounting-pause | 60.006381 | c88f974697f77ca9382fd626 | runs/effect/accounting-pause/r150-b01-07-full |
| 8 | 150 | fraud-pause | 60.003256 | f5a0eb2f9f45c9a5625a9d16 | runs/effect/fraud-pause/r150-b01-08-full |
| 9 | 150 | productcatalog-cpu-throttle | 60.005646 | ddba58c31bd5be46e7f7c072 | runs/effect/productcatalog-cpu-throttle/r150-b01-09-full |
| 10 | 150 | frontend-pause | 60.002924 | 238e6605c2a54ad418279073 | runs/effect/frontend-pause/r150-b01-10-full |

No run ID equals one from sweep attempts 1-2, quiet attempts 1-3, B attempt 1, C attempt 1 or the load pilot's attempt 1 (tested).
The campaign stops on its first invalid cell. The no-fault cell opens each rate segment (cells 1 and 6), so an early stop still
leaves that rate's baseline; the two never-run off-path pauses follow it (cells 2-3 and 7-8), then the frontend pause and the throttle
(see risk 4).

## Risks the build cannot settle without running the pilot
1. **The frontend may saturate at 150 req/s of the mix.** The load pilot measured the frontend at ~0.53 core at 100 req/s of one
   product route (5.4 ms CPU per request) on one Node process; the mix's per-request cost is `?` (checkout, recommendations and
   the cart POSTs call more services). At 150 req/s G2 (pre-onset failure share > 5 %) or decision 25 may invalidate a cell and stop
   the pilot. Frontend saturation is a result, not a defect.
2. **The throttle may still not bind.** Estimate, not a measurement: productcatalogservice sees ~1.4 calls per request in the mix
   (products 16, recommendations 5 each, checkout ~5 per 34 requests; unexecuted source reading) at ~0.85 ms CPU per call (load pilot
   r100) = ~0.12 core at 100 req/s and ~0.18 core at 150 req/s against the 0.1 cap. At 100 req/s it is marginal; 150 is the rate
   at which the throttle is expected to bind (a lower top rate than the first build's 200, by user decision).
3. **SUT memory limits stay upstream's** (user decision 2026-10-12), sized for ~1 req/s of journeys, not for 150 req/s of the mix:
   checkoutservice 20M (a Go service at ~9 orders/s at 150 req/s), productcatalogservice 20M (the throttle test itself: ~100 hung
   calls/s pile up), currencyservice 20M, shippingservice 20M, valkey-cart 20M, quoteservice 40M, emailservice 100M, accountingservice
   120M, prometheus 300M, grafana 100M. The container-health guard invalidates a cell on **any** OOM kill (infrastructure included) and
   the campaign stops. **otelcol and jaeger are raised to 1 GiB each** (decision 1), which removes the two infrastructure risks I
   named; the SUT ones remain and an OOM there is a result, not a defect.
4. **Fault-cell validity of a never-run scenario.** After 60 s paused, a Kafka consumer's session (45 s default) has expired; on
   unpause it rejoins. If a consumer process exits or Docker restarts it, the health guard (`restartCount`) invalidates the cell.
   Unknown for frauddetectionservice (JVM) and accountingservice (.NET); that would be a harness-visible but SUT-caused stop.
5. **Decision 25 per-route sets.** The required services per route are a conservative subset from unexecuted source reading; if a
   route's spans are lost above max(1, 1 %) of successful requests outside the fault-and-drain window (SDK queues at 150 req/s), a
   fault cell is invalid. The sets were checked against the posture catalog only.
6. **Witness check.** Every offered token must appear exactly once in the access log, POSTs included; a connection refused before
   Envoy (listen backlog, docker-proxy) would leave a token unwitnessed.
7. **The generator in Python threads.** 4500 threads and ~27,000 requests per cell on 3.9 under the GIL; dispatch lag is recorded in
   every row (`startedMonotonic` minus the slot) and the terminal only bounds it from below. A generator that cannot keep up shows as
   late starts, which G1 does not count against the cell. Exercised only on the fake target with a 256-thread pool (2048 for the
   frontend pause; the 4500 cap is asserted, not exercised); **the per-cell runner has run only against the fake target.**
8. **Envoy's default circuit breakers** (1024 connections and 1024 pending requests per cluster; neither the upstream config nor the harness sets any) would answer the excess of ~2250 outstanding requests with an immediate 503 during a frontend pause (every route) or a binding throttle (about 75 hung gRPC calls/s per 150 req/s, no client deadline in the frontend). Failures on routes the fault does not touch can therefore appear in the evidence; the pre-onset G2 is not affected and the throttle criterion reads spans. **They are separable offline:** the witness rows (`application-witness.json`) carry `response_code` and `response_flags` (the proxy's access-log fields; an overflow shows as 503 with `UO`), so the post-fetch script can cross-check them against the ledger status. Left at upstream defaults (user decision 2026-10-12). Also: the 1 GiB frontendproxy sizing assumes queueing that Envoy may refuse.
9. **Thread budget**: 4500 generator threads (the load pilot peaked at 3000). **Resolved by the coordinator's read-only host check** (above): `ulimit -u` 1,031,179, `user-1016.slice` TasksMax 680,578, `pid_max` 4,194,304, `user.slice` `pids.max` max.
10. **Collector log volume** (up to ~1 GB) read into memory on the host and again by the terminal on the laptop; slow but bounded.
11. **Parallel cart POSTs (deviation from upstream).** Upstream runs a task's requests one after another. Here the `checkout_multi` journey's 2-4 cart POSTs of one user are adjacent slots with no dependency between them, so they can run concurrently and a read-modify-write in cartservice/valkey may lose an item; the checkout waits only for the last one. The checkout's items, and so the productcatalog and currency calls it makes, can then differ from upstream's. Declared as a deviation; `route=checkout` success is unaffected (an empty cart still returns 200).
12. **The fake target is not the SUT on an empty cart.** The test's fake fails a checkout whose cart is empty (500); the real PlaceOrder on an empty cart returns 200 and skips productcatalogservice (review finding). The planted test "a runner that ignores the dependency fails G2" is therefore a property of the fake; on the SUT an ignored dependency would show as incomplete traces and the terminal's order check, not as a G2 failure.

## Launch (worktree HEAD must still be `8c53cb24581d`)
From the measurement repo (re-run `git -C ../observability-placement-runtime-otel-protocol rev-parse HEAD` first):
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
DRY_RUN=1 OTEL_CANDIDATE_ATTEMPT=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_offpath_pilot.py EXPECTED_PLAN=8b3d7aa84e26c31de724c3686331b1f7347b9fd086a1debfefdea80799104814 \
  RUN_COUNT=10 CAMPAIGN=otel-offpath-pilot-v1 LOG_PREFIX=otel-offpath-pilot \
  zsh scratchpad/gate-drivers/launch_otel_offpath.sh opdry1 8c53cb24581d7805df691c64d8ec26bd90573b2e \
  > scratchpad/gate-drivers/otel-offpath-pilot-opdry1.out 2>&1
```
Launch (after a passing DRY_RUN; same variables, no `DRY_RUN`):
```
LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_offpath_pilot.py EXPECTED_PLAN=8b3d7aa84e26c31de724c3686331b1f7347b9fd086a1debfefdea80799104814 \
  RUN_COUNT=10 CAMPAIGN=otel-offpath-pilot-v1 LOG_PREFIX=otel-offpath-pilot \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh op1 8c53cb24581d7805df691c64d8ec26bd90573b2e \
  > scratchpad/gate-drivers/otel-offpath-pilot-op1.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow otel-offpath-pilot-op1 scratchpad/gate-drivers/otel-offpath-pilot-op1-launch.log \
  > scratchpad/gate-drivers/otel-offpath-pilot-op1-wandb.out 2>&1 &
```
After the first cell seals, check the validity fields only: `receipt.json` state, `protocol-gates.json` failedGates,
`container-health.json` reasons, `trace-completeness.json` valid. After terminal, fetch to a **new** path. `fetch_overnight.sh` needs
one new case (**already added by the coordinator** in the uncommitted `scratchpad/gate-drivers/fetch_overnight.sh`, not part of the
declaration commit):
```
  otelpilot2) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-offpath-pilot-v1; O=tmp/otel-offpath-pilot-evidence/p1-fetch ;;
```
(with `otelpilot2` in its usage line). Expect several GB: fetch to the laptop with the host-side sha256 manifest as before. Then apply
the criteria once, with the defaults above.

## Tests (OTel worktree)
- `tests/test_otel_offpath_pilot.py` at HEAD: 88 passed (~2.5 min; plan pin, C-identity, mix, sizing, order, run-ID reuse, gate chain, every regime
  end to end on the fake target with the consumers' spans, the criteria computed from retained artifacts, ledger/witness plants,
  per-route completeness, rendered tree, 3.9 floor). In-test plants: edited descriptor/plan (incl. mix weights, a route's required
  services, a scenario's service), C-sized and load-pilot-sized generator, descending rate order, load-pilot run-ID reuse, an unknown
  task / skewed weights, an upstream spelling of the ads path (308), a consumer that ignores its pause, a pause that takes checkout
  down, a throttle that does not bind, 14 ledger-row plants (route, target, body digest, predecessor, dependency order, counts, mix
  digest, ledger kind, missing request, rescheduled request, missing key, outcome), a lost POST witness, a mix dropped from the
  contract, a lost route span (no-fault: recorded; fault cell: blocks), a runner that ignores the dependency (G2 fails on the
  target), a runner that falls back to one route (terminal refuses), a hard open-file limit of 4096, a SUT limit smuggled into the sizing, the no-fault cell moved last in a segment, an unapplied otelcol limit and a jaeger limit not in effect, a compiler with the order groups swapped, `verdict()` with a failed no-fault precondition (S2) and the send-time selection of the frontend-pause checkouts (B1); a 150 req/s no-fault cell (27,000 requests, cap 4500) runs end to end.
- **Source plants (each restored), 14 of 14 caught** by `tests/test_otel_offpath_pilot.py` (first failing test, `-x`): pilot dropped from
  `REPEAT_STUDY_EPOCHS`; `workloadMix` dropped from the runtime's key set; `run_cell_workload` ignoring the mix; per-route completeness
  replaced by the single route; the dependency wait removed; the terminal not replaying rows against the plan; the terminal not
  checking dependency order; the terminal judging correlation on the clipped path (**missed at first, caught after adding a coverage
  assertion**); `ensure_generator_open_files` removed; the ledger row losing its route; the telemetry backend dropped from the sizing; the segment order shuffling all cells; the group-order check removed from `validate_plan`; the off-path and on-path groups swapped. Two more plants (pilot dropped from the
  sampler-off and retention tuples) are in-test.
- Measurement repo `tests/test_unbound_names.py`: 319 passed (one parametrisation is `candidate_offpath_pilot.py`; CLAUDE.md says 317, the load pilot made it 318).
- Full worktree suite (`uv run pytest -q -p no:cacheprovider -rf --ignore=tests/test_mlflow_manifest.py`) at HEAD `8c53cb2`: **29 failed, 2321 passed,
  145 skipped** (792 s). The sorted `FAILED` name list is identical to the load pilot's at `7b20ec4` (`diff`, no output; none is OTel). Delta
  against `7b20ec4` (2232 passed): +89 = +88 new file, +1 net in `tests/test_otel_load_pilot.py` (attempt-1-spent tests). (The first run
  at the activation edits showed 30 failed: one TeaStore test refuses a dirty tree; it passes on the committed tree.)
- Independent review (same-provider read-only subagent, Fable-class not available): no defect failing every cell; findings folded in
  above (risks 2, 8, 9; the canonical-JSON fix; the consumer-trace wording). **Not yet reviewed by a second provider; the judge MCP server failed to connect.**

## Open at freeze: decisions needed
- **Decided (user, 2026-10-12):** otelcol and jaeger 1 GiB, SUT limits upstream; off-path hold 60 s; per-route completeness confirmed;
  Envoy circuit breakers upstream. **User (6): rates 100 and 150 req/s.** **Decided (coordinator defaults, user may veto):** order inside a rate (no-fault, off-path
  pauses, frontend pause and throttle); at most 1 relaunch for harness or infrastructure defects; E's rate rule (lowest rate at which every
  kept fault manifests, else the highest rate at which any does).
- **Still open for the user:** nothing blocking.
- Engineering defaults taken and recorded: the cart dependency and send-anyway rule, the canonical `/api/data` path, the 45 s window for
  the frontend-pause criterion, the 20-item minimum, 500 s overhead, seed 20261013, the 10 % checkout bound and send-time selection of the frontend-pause criterion, the no-fault precondition (`—`).
- Reviewed by a same-provider read-only subagent only; the judge MCP server failed to connect in the build session.
