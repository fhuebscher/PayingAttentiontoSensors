# S4 relevance baseline: result (2026-09-27, first and only computation)

**Corrections applied 2026-09-28 (from REVIEW_RESULT_BASELINE_20260927.md):** finding 12 replaces the greedy G-old `f_all` values with
the exact optimum and states the empty-set count alongside the non-empty count; finding 6 discloses the by-construction zero on the
auth-freeze side of the `log:auth:6c19cf62298a` contrast and gives its recovered template text; finding 8 discloses that template
sensors include INFO/level-less records, narrows the WARN+ log split to 6 families (not 7), and names the heartbeat-expiry and
MariaDB templates; finding 3, the A-P3 row and TBC1 replace the "TBC1 label was wrong" claim with the frozen-window (W) explanation for
why `missing_expected` cannot fire; finding 11 adds the Check 5 span-sensitivity numbers, labelled post-hoc; the header's test-suite
line is corrected to the observed `test_relevance.py` run only; the Judge section discloses the `llm_as_judge` MCP deviation from the
Fable-subagent instruction and names the Fable review as the independent review of record; and reading R3 is named as a conflict
between two frozen documents. The "Generated tables" section is untouched.

**Spec.** `AMENDMENT_1.md` section 4 (FROZEN 2026-09-27, commit 33dec5f) over `DEFINITIONS.md` (frozen 962bf4f: gate G1–G6,
predictions section 10, true-by-construction section 11, stop rules section 12).
**Inputs.** Bags `tmp/s4-symptoms/20260927T100543Z/` (9,832 rows, 2,441 hashed inputs), produced by the committed
`research/s4-conjunction/symptoms.py`, sha256 `7f33203647ce7ed6aedec53be996f0a4ee543b952474d9265b1094ccf65a6fb8`; the
relevance script verified that the bags' manifest carries this sha and that it equals the file at `HEAD` before reading a row.
**Script.** `research/s4-conjunction/relevance.py` (`--self-check` passes; `tests/test_relevance.py`, 20 fixture-only tests, observed
20 passed (`PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_relevance.py`); the full suite total was not
re-run for this document. Run once: `/usr/bin/python3 -B research/s4-conjunction/relevance.py
tmp/s4-symptoms/20260927T100543Z --out tmp/s4-relevance`, 10 s, output stamp **`tmp/s4-relevance/20260927T102324Z/`**
(`relevance.json` 19 MB with every count, `tables.md` 315 KB with every table incl. per-service and per-posture blocks; evidence stays out of git).
**Scope label for every number below: instance.** One host, one workload, one fault catalogue per generation. Generations are
compared, never pooled (S-G). No intervals, no p-values. Postures are pooled only inside one generation and only for log and
metric symbols, as section 4 says; span symbols, combinations and R(p) use the span-exporting posture (`full`; G-old `kieker-native`).
**Values were computed once**, under the readings listed in "Readings" below, which were written into the script before the run.
No reading was changed after a value was seen. Independent review: one adversarial judge call per lead finding (S-J; the
"Judge" section below records ids and what changed). This document is the ledger of counts; no sentence here is thesis text yet.

## Findings that matter for "which sensors are relevant alone vs only in combination, per fault class"

Each line names its generation, population and denominator. "Relevant alone" means the sensor fires in k of n episodes of
the class under the section 4 firing rule with G3 applied, with its false alarms over n0 no-fault pseudo rows beside it.

1. **H-B (Hotel #6 runs 3–6, fb14srv4). The log family is one template.** Of 162 H-B log templates, exactly one fires in any
   fault row: `log:frontend:4ae82b46d72e` (zerolog-console `ERR` at `services/frontend/server.go:271`; the tid was recovered by
   re-parsing one manifest input, sha-checked). It fires 72/72 reservation-pause and 0/72 search-pause, pooled over the three
   postures (24 each), false alarms 0/72. Its rate subsensor `log:rate:4ae82b46d72e:high` also fires 72/72 and 0/72.
   No template fires in search-pause (0/72 for all 162), so the search-pause log family is `0/72`, not absent.
2. **H-B. Metric sensors separate the two regimes by service, all in the "down" direction.** On `full` (24 per regime):
   `metric:rate:cpu` 24/24 search-pause and 0/24 reservation-pause (FA 0/24); `metric:search:cpu` 24/24 and 0/24 (target of
   search-pause, G2); `metric:geo:cpu` 22/24 and 0/24; `metric:reservation:cpu` 24/24 in **both** regimes (target of one, not of the
   other; FA 0/24); `metric:profile:cpu` 24/24 both (FA 2/24); `metric:frontend:cpu` 21/24 and 24/24 (FA 0/24; pooled 68/72, 72/72,
   FA 4/72). The symptoms carrying every one of these are `metric:cpu:plateau_down` (72/72 both regimes, FA 0/72) and
   `metric:cpu:spike_down` (72/72, FA 1/72); `metric:cpu:spike_up` fires 0/72 in both regimes with FA 9/72. No metric sensor fires
   only in reservation-pause. attractions, recommendation, review, user: 0/72 in both regimes (0/n, not absent).
3. **H-B. Span sensors: the paused service's own operation stays `present`.** `span:<op>:missing_expected` fires 0/24 for
   reservation in reservation-pause and 0/24 for search in search-pause; instead `span:reservation:/reservation.Reservation/CheckAvailability`
   fires 24/24 through `latency_high`, `span:search:/geo.Geo/Nearby` 24/24 through `error`, and `span:search:/rate.Rate/GetRates` 24/24 as
   a sensor through `error` in 20/24 and `latency_high` in 14/24 of search's rows (their union is 24).
   Amendment P3's first half **failed** under the frozen window W = [`startedAt`, `endedAt`], which begins before the pause command
   and ends after recovery (`compose_pause.py:108`, `:143`); the target's operation keeps 28–71 spans in W (150 per 15-s pseudo
   window), so `present` holds and `missing_expected` cannot fire by construction of W. TBC1's second half described the pause
   interval, not W; the sensor question is open.
   Frontend: `span:frontend:HTTP_GET_/hotels` 24/24 in both regimes (error and latency_high), `span:frontend:/reservation…CheckAvailability`
   24/24 (error) vs 16/24 (latency), `span:frontend:/search.Search/Nearby` 0/24 vs 24/24. Span FA is 0/24 for every span sensor.
4. **H-B. No combination is needed for detection at n = 24: every class has several single sensors at 24/24** (reservation-pause six,
   of which four are not the target's: the log template, `metric:profile:cpu`, `span:frontend:HTTP_GET_/hotels`, `span:frontend:/reservation…CheckAvailability`;
   search-pause nine, of which six are not search's). Reservation-pause
   (11 sensors fire in ≥ 1 of 24 `full` episodes): 15 of 55 pairs co-fire in 24/24, 52/55 pairs are redundant (conjunction = smaller
   single count), 3 are complementary and every one of them joins two partial sensors (e.g. `metric:frontend:cpu` 21 + `span:reservation:memcached_capacity_get_multi_number`
   10 → union 23) without exceeding the best single sensor (24). Search-pause (16 sensors): 36 of 120 pairs at 24/24, 106 redundant,
   14 complementary, again all among partial sensors (`metric:geo:cpu` 22 + `span:rate:/rate.Rate/GetRates` 22 → 24). Triples beyond
   every sub-pair: 1 of 165 and 3 of 560, all among partial sensors. On this population every union of sensors is bounded by the
   saturated singles, so the pair and triple counts are a consequence of saturation at n = 24 and say nothing about combinations at a
   controlled false-alarm rate or about sensors that fire in fewer than 24 episodes (a 22 + 22 → 24 pair is a real union gain for those two).
5. **H-B. R(p) under G1–G6 (48 `full` episodes): 0 empty, |R| 4–11, 17 distinct sets, none shared across regimes.** Composition:
   reservation-pause `log+metric+span` 24/24; search-pause `metric+span` 24/24, so the G4 count is 24/48 (metric in R, no log in R).
   G3 removed 0 sensors on H-B; G2 removed 58 and 72 target-service sensor firings. Exact optimum (17 distinct sets): `f_any` is 48/48
   at k = 1; `f_all` is 0/48 up to k = 3, 2/48 at k = 4, 12/48 at k = 5, 24/48 at k = 8. A conjunction over the alphabet needs four
   sensors before it covers one episode.
6. **T-new (e3-a5, fb14srv5) and T-16 (#16, fb14srv5). Window-level log detection of persistence-crash exists on TeaStore.**
   `log:auth:6c19cf62298a` (a JUL `WARNING` template of auth, timestamped, inside the `fault` window) fires 9/9 persistence-crash and
   0/8 auth-freeze on T-new (postures none/selected/full pooled; a-p-w's 48 rows excluded, 22 invalid rows excluded) and 9/9, 0/9 on
   T-16; FA 0/9 on both, **0 by construction (TBC5)**. Disclosed: the auth-freeze side of this contrast (0/8, 0/9) is zero by
   construction, not by measurement — auth is the paused target in auth-freeze, so its freeze-window rows carry 0 log symbols, and
   persistence (the only other stream) also carries 0 log symbols in that window. Template text (recovered from the sha-checked
   `auth.log`): JUL WARNING `org.glassfish.jersey.server.ServerRuntime$Responder.process — An exception mapping did not successfully
   produce and processed a response…` — the caller's (auth's) default exception mapper firing on the failed downstream call to
   persistence. It is the only one of 58 templates that fires in any `fault` row (log4j templates
   have no timestamp and live in the `cell` row only, TBC9). DETECTION_RESULT's "Correction" listed window-level TeaStore detection as
   backlog; the count is now 9/9 per generation. `span:<op>:error` is 0 in every TeaStore row of all three generations (no Kieker
   record carried a status code other than null/200/0), so F14 stays `—` for TeaStore.
7. **T-new / T-16. Spans: non-target services lose operations in both classes.** On `full` (T-new: freeze 2, crash 3; T-16: 3 and 3),
   `missing_expected` fires as follows on T-new. Auth-freeze: auth's nine operations 2/2 (target, G2); as non-target, four persistence
   operations (`PersistenceUser.getId`, `ProductEndpoint.findEntityById`, `UserEndpoint.findById`, `UserRepository.getUserByName`) 2/2,
   recommender's four operations 2/2, webui `ProductServlet.handleGETRequest` 2/2. Persistence-crash: persistence's 12 operations 3/3
   (target); as non-target, six auth operations (`BCryptProvider.checkPassword`, `RandomSessionIdGenerator.getSessionId`, four
   `ShaSecurityProvider.*`) 3/3, recommender's four 3/3, image's `DriveStorage.loadData` and `ImageProviderEndpoint.getProductImages` 3/3,
   webui `CategoryServlet` and `ProductServlet` 3/3. T-16 has the same rows at 3/3.
   R(p): auth-freeze `span` only (2/2, 3/3), persistence-crash `log+span` (3/3, 3/3); |R| 9–16, so `f_all` is 0 for every reported
   k ≤ 8 (a display bound, not re-run) while `f_any` is 5/5 and 6/6 at k = 1. With n = 2 or 3 episodes, every pair is redundant
   (190/190 and 378/378) and the combination tables carry no information at this n.
8. **G-old (old TeaStore, fb14srv6, 11 families × 10 runs, n0 = 30 pseudo rows per family). Log sensors split the catalogue 7 : 4.**
   `log:*` fires 10/10 in auth_freeze, db_crash, image_crash, image_loss, persistence_crash, recommender_crash, registry_restart and
   0/10 in orderitems_timeout, persistence_latency, recommender_exception, recommender_latency, with FA 0/30 in every family. 23 template
   sensors fire at all (171 templates × 7 services; 151 templates are 0/n in every family). Disclosed: template sensors as defined
   include INFO/level-less records, not only WARN+. `log:webui:d4d75ec135e6` (firing in auth_freeze, persistence_crash and
   registry_restart) is a log4j record with level None — an INFO-level Ribbon line, `com.netflix.loadbalancer.BaseLoadBalancer —
   Client: instantiated a LoadBalancer: {… current list of Servers=[] …}`. Restricted to WARN+ templates only, registry_restart is
   0/10: its 10/10 log family is carried by `d4d75ec135e6` alone, a level-less template. So WARN+ logs cover 6 families at 10/10, not
   7; registry_restart's log family is level-less-only. The non-self part (what enters R under G2): auth_freeze `log:webui:d4d75ec135e6`
   10/10, `log:registry:1b6e1f5f63fc` 10/10 (registry's own heartbeat-expiry WARN template, `Removed tools.descartes.teastore.<svc>@…
   since it failed the heartbeat!`, with siblings `3746091e2305`, `7450b9d707e0`, `c2797874a226`; this WARN template, not
   `d4d75ec135e6`, is what makes D-P5 fail at 10/10), `log:webui:d4bab19c5a03` 9/10; persistence_crash `log:{auth,image,recommender}:d4d75ec135e6`
   10/10 each, `log:registry:3746091e2305` 10/10, `log:webui:d4d75ec135e6` 9/10; image_loss `log:db:0fa0e0318a07` 10/10 (MariaDB
   `[Warning] Aborted connection … (Got timeout reading communication packets)`, a non-target DB reaction); db_crash 0/10
   (its ten firing sensors are all `log:db:*`, including `a7ff7976a62f`, MariaDB `[Warning] Aborted connection … (Got an error reading
   communication packets)`, a TCP reset when the persistence container dies). DEFINITIONS P5 (auth_freeze non-self log ≤ 2/10) **failed** at 10/10; its
   persistence_crash ≥ 8/10 and db_crash ≤ 2/10 parts are met. One template id, `d4d75ec135e6`, fires in four services.
9. **G-old. A known template is relevant through its rate.** `log:webui:a273f9c494c5` occurs in 18/30 no-fault pseudo windows (inadmissible
   under G3, τ = 5 % of 30 → 1) yet the sensor fires 9/10 in image_crash via `log:rate:a273f9c494c5:high`, 0/10 elsewhere, FA 0/30; the same
   template is present 9/10 in db_crash without a high rate (0/10). This is the CloudWatch-metric-filter subsensor of the amendment
   doing what it was added for, under reading R2.
10. **G-old. CPU spikes are inadmissible everywhere; memory drops are the crash target's own; the surviving non-target metrics are few.**
    `metric:cpu:spike_up` fires in 25–27/30 no-fault pseudo rows per family (pooled over services; per service 4–16/30) and is G3-removed
    in every family (G3 removed 12–49 sensor firings per family). `metric:mem:spike_down` (FA 1/30) fires 9–10/10 for db, image,
    persistence, recommender, registry in their own crash/restart family, i.e. for the target (G2, TBC7). Non-target metric sensors that
    survive G3: image_crash `metric:persistence:mem` 8/10, `metric:persistence:cpu` 5/10, `metric:webui:cpu` 5/10 (FA 0/30); db_crash
    `metric:auth:mem` 3/10 (FA 1/30); persistence_crash `metric:image:mem` 2/10. DEFINITIONS P6 (second half) **failed**: image_crash has a
    metric in R in 9/10 but metric-without-log in 0/10 (its logs fire 10/10); metric-without-log ≥ 1 holds in db_crash 6, orderitems_timeout 2,
    persistence_latency 1, recommender_exception 2 (G4 count 11/110). Amendment P6 is **held as written** (its row rule names no
    admissibility): a non-target `metric:*:spike_*` with no `log:level:*` in the same row occurs in 8–10/10 runs of all 11 families.
    A post-hoc check (after the run, not part of section 4) restricted the same row rule to G3-admissible spike symbols: auth_freeze 1/10,
    db_crash 2/10, image_crash 8/10, image_loss 0/10, orderitems_timeout 2/10, persistence_crash 0/10, persistence_latency 0/10,
    recommender_crash 2/10, recommender_exception 2/10, recommender_latency 0/10, registry_restart 1/10, so one family instead of the
    predicted two reaches 5/10 under admissibility.
11. **G-old. Span `missing_expected` fires in 28/30 no-fault pseudo windows of the 45-s families.** `span:persistence:PersistenceUser.getId`,
    `UserEndpoint.findById` and `UserRepository.getUserByName` fire 9/10, 9/10 and 2/10, 2/10 in auth_freeze and db_crash, and 28/30 in the
    pseudo rows of the seven families whose D_f is 45.2–47.5 s against 10/30 for the four 55.5–55.6-s families (`span:*` FA 28/30 vs 10/30;
    an observed grouping over eleven families, not a tested one). Section 4 applies no G3 to spans, so they enter R(p): the only span
    sensors that fire in auth_freeze are these three, so the auth_freeze composition `log+span` 8/10 is built with span sensors whose FA is
    28/30. By contrast `span:image:*` (four operations, `missing_expected`) fires 9/10 in seven non-image families and in image_loss (its
    own target, G2), with FA 0/30, and 0/10 in auth_freeze, db_crash and image_crash. Post-hoc sensitivity (not a re-run of section 4):
    dropping the three FA-28/30 persistence span sensors from R changes the auth_freeze composition from `log+span` 8/10 to `log`
    9/10 + `log+metric` 1/10; the distinct-set count (finding 12) goes from 34 to 33 non-empty; `f_any` and the exact `f_all` at
    k = 1..4 are unchanged.
12. **G-old. R(p): 110 episodes, 4 empty (one each in the four latency/timeout/exception families), 35 distinct sets including the
    empty set (34 non-empty), |R| 0–11.** Composition
    per family in the table below; greedy optimum (34 non-empty distinct sets > 20): `f_any` 63/110 at k = 1, 101/110 at k = 4, 106/110 at
    k = 8 (an independent exact re-derivation confirms greedy is optimal here for k ≤ 4). `f_all` is supermodular, so greedy stalls at
    zero marginal gain past k = 1: greedy lower bound `f_all` ≥ 10/110 at k = 1 (image_loss: R = {`log:db:0fa0e0318a07`} in 10/10);
    exact optimum (post-hoc bounded union search, not part of section 4): 10, 11, 12, 31, 41, 43, 49, 52 for k = 1..8; 31/110 at k = 4
    is the four `span:image:*` sensors covering the 31 span-only episodes (orderitems_timeout 7, persistence_latency 8,
    recommender_exception 7, recommender_latency 9). Combinations: db_crash has 25
    complementary pairs of 190 and 25 triples beyond every sub-pair (of 1,140), all joining partial metric sensors and the FA-prone
    persistence spans; auth_freeze, image_loss, orderitems_timeout, recommender_crash, recommender_latency have 0 complementary pairs.
13. **Mutual information (ranking aid, plug-in, class sizes printed).** H-B: 12 symbols sit at the maximum 0.918 bits for three balanced
    classes (72/72/72): the log template/level/rate trio, `metric:cpu:plateau_down` pooled, and six span error/latency symbols of frontend and
    search; 172/191 symbols carry 0 bits. G-old (10 per family vs 330 no-fault rows, so the no-fault class dominates): the four
    `span:image:*:missing_expected` 0.558, `log:template:novel` 0.511, `log:template:d4d75ec135e6` 0.476, `log:exception:ClientException`
    0.448 (webui; it fires in 27/30 no-fault windows too, and belongs to no sensor under R1).

**What this does not support.** Nothing here is a cross-SUT or method claim. Every count is one detector configuration frozen before
counting, at instance scope. "Relevant alone" is a count inside a fault window; it is not attribution to the faulted service. The H-B
combination result is bounded by n = 24 and by a class in which several single sensors already saturate; the TeaStore combination
result is uninformative at n = 2–3; the G-old span rows carry the FA above.

## Readings of the amendment's text (chosen before the run, from its own wording; recorded, not tuned)

R1–R11 are written into `relevance.py` (`READINGS`) and into `relevance.json`.

- **R1** `log:level:*`, `log:template:novel`, `log:exception:*` belong to no section 2 sensor (one log sensor per template; a throwable
  record has no template). They appear in the symbol tables only. Cost of the reading: 11 G-old fault rows (0 on H-B, T-new, T-16)
  carry an exception class and no firing template sensor.
- **R2** `log:<svc>:<tid>` fires iff `log:template:<tid>` is in the row and G3-admissible, or `log:rate:<tid>:high` is in the row (the
  rate symbol is calibrated on the same no-fault windows; vocab.json carries no FA column for it, so G3 is not applied to it).
- **R3** G3 for metrics is per (service, symbol), following AMENDMENT_1 section 4's literal text ("applied to log templates and metric
  symbols"), which **conflicts with DEFINITIONS G3 "Metric (sensor level)"** (per sensor, not per symbol) — this is a conflict between
  two frozen documents, not a single unambiguous reading. Outcome-changing: under per-sensor G3, every G-old `metric:<svc>:cpu` with
  `spike_up` (FA 25–27/30) would be inadmissible wholesale, wiping findings 10, D-P6 and the A-P6 post-hoc.
- **R4** G-old's only posture `kieker-native` exports spans and is its `full`.
- **R5** Pairs and triples are computed on the span-exporting episodes only (all three modalities in one population).
- **R6** Span symbols' and span sensors' FA denominator is the span-exporting posture's pseudo rows (24 on H-B); log and metric use
  every posture except a-p-w, per posture and pooled.
- **R7** P1 is checked on the sprint's population: T-new's 11/11, 0/9, 0/12 include the a-p-w cells. A15 governs the section 4 tables.
- **R8** MI's no-fault class is every pseudo row of the symbol's population (G-old: 330).
- **R9** G-old admissibility uses the vocab key `<svc>/window:<regime>`; Hotel/TeaStore `<svc>/window`. T-new's `noFaultWindows`
  (12 for auth and persistence) was written by the frozen script with the three a-p-w no-fault cells included; it changes nothing,
  since no TeaStore template occurs in any no-fault window.
- **R10** Amendment P4 and DEFINITIONS P2–P4 on the span-exporting posture (other postures shown); amendment P5 on the `cell` row over all
  valid cells including a-p-w (its denominators 11 and 9 require them); amendment P6 counts a run when some non-target row carries a
  metric spike and no `log:level:*`.
- **R11** Optimum per budget k: unit costs, no activation dependencies, exact by union enumeration when ≤ 20 distinct R sets, else
  greedy and labelled; k = 1..8 (a display bound; on TeaStore min |R| = 9, so `f_all` = 0 there for the whole range). Level sets over
  the catalogue domain: `—` (op-level trace ids have no catalogue closure).

Not a reading but a bound of this run: `MAX_K = 8` and `TRIPLE_LIMIT = 200` (section 4's number; every generation had ≤ 42 firing sensors).

## Disclosed prior look (this session, beyond AMENDMENT_1 section 1)

- While checking the bag structure before writing the script, two H-B calibration values were seen: `frontend/window`
  `metric:cpu:spike_down` 1 and `metric:cpu:spike_up` 3 (of 72). No value by regime was seen before the run.
- After the run, to explain the one differing sweep row (below), the three T-new `none` persistence-crash `persistence.log` files were
  grepped: 1 JUL `SEVERE` line and 0 log4j `ERROR` lines each.

## P1 / C1 bridge: PASS (S-B did not fire)

Every row named in section 4 matches DETECTION_RESULT exactly; the bridge reconstructs the sprint's detectors from the bags
(level = any `log:level:*` in any service's fault row; metric-target / metric-other = the target's / the other services' `metric:cpu:spike_*`;
trace-error = any `span:*:error`).

| row | got | expected |
|---|---|---|
| H-B reservation-pause level none / sample-zero / full | 24/24, 24/24, 24/24 | 24/24 ×3 |
| H-B reservation-pause metric-target | 23/24, 24/24, 24/24 | same |
| H-B reservation-pause metric-other | 24/24 ×3 | same |
| H-B reservation-pause trace-error | 0/24, 0/24, 24/24 | same (TBC3) |
| H-B search-pause level | 0/24 ×3 | same |
| H-B search-pause metric-target | 24/24, 23/24, 24/24 | same |
| H-B search-pause metric-other | 24/24 ×3 | same |
| H-B search-pause trace-error | 0/24, 0/24, 24/24 | same (TBC3) |
| H-B FA over 72: level / metric-target / metric-other / trace-error | reservation 0, 0, 10, 0; search 0, 4, 6, 0 | same |
| H-B sweep warn+ (pooled 72) | reservation 72/72, search 0/72, FA 0/72 | same |
| T-new warn+ (cell level, all four postures) | persistence-crash 11/11, auth-freeze 0/9, no-fault 0/12 | same |

One sweep row **outside** the P1 set differs and is reported as such: T-new **error+** is 3/11 here against the sprint's 0/11
(auth-freeze 0/9 and no-fault 0/12 match). The three records are one JUL `SEVERE` line each in `persistence.log` of the three `none`
persistence-crash cells; the sprint parsed log4j only (DETECTION_RESULT "Correction"), and log4j `ERROR` lines are 0 in those files.
All three lie outside the fault window (they are in the `cell` row only). P1 as narrowed by the amendment names the level rows and
the warn+ sweep row, so this is not a P1 mismatch; it is recorded because "exactly" was the requirement.

## Predictions (DEFINITIONS section 10 = D-Px; AMENDMENT_1 section 8 = A-Px)

| id | prediction | observed | verdict |
|---|---|---|---|
| D-P1 / A-P1 | C1 reproduces DETECTION_RESULT (sprint) | all named rows match | held (TBC6: a check, not a finding) |
| D-P2 | H-B `log:frontend` ∈ R(p) ≥ 20/24 reservation-pause, 0/24 search-pause, G3 on | 24/24, 0/24 | held |
| D-P3 | H-B search-pause ≥ 20/24 episodes with metric ∈ R and no log ∈ R | 24/24 | held |
| D-P4 | H-B ≥ 2 distinct R sets over 48; none in both regimes | 17 distinct, 0 shared | held |
| D-P5 | G-old non-self log in R: auth_freeze ≤ 2/10, persistence_crash ≥ 8/10, db_crash ≤ 2/10 | 10/10, 10/10, 0/10 | **failed** (auth_freeze) |
| D-P6 | C4 old metric-without-log = 0/total; gated R has ≥ 1 metric-without-log episode in every family where a metric enters R | C4 `—` (needs `ground_truth.json`, not in the bags); image_crash 0 of 9, persistence_crash 0 of 2, recommender_crash 0 of 2, registry_restart 0 of 2, auth_freeze 0 of 1 | **failed** (second half); first half `—` |
| D-P7 | H-A vs H-B | H-A dropped (A14) | `—` |
| A-P2 | H-B `full`: `log:level:error` in frontend's fault row ≥ 20/24 reservation-pause, carried by server.go:271's template; search-pause no `log:level:*` ≥ 20/24 | 24/24; template `4ae82b46d72e` present 24/24; 24/24 | held |
| A-P3 | H-B `full`: target's own operation `missing_expected` ≥ 20/24 per regime; frontend `span:<op>:error` ≥ 20/24 | 0/24 and 0/24; 24/24 and 24/24 | **failed** (first half, under the frozen window W = [`startedAt`, `endedAt`]; `missing_expected` cannot fire by construction of W — `compose_pause.py:108`, `:143`; TBC1's second half described the pause interval, not W; the sensor question is open) |
| A-P4 | H-B: a `log:rate:<tid>:high` outside the target in ≥ 12/24 reservation-pause | 24/24 on `full` (24/24 on none and sample-zero) | held |
| A-P5 | T-new: `log:exception:ClientException` in auth's `cell` row ≥ 8/11 persistence-crash, 0/9 auth-freeze | 11/11, 0/9 | held (consistency; TBC2) |
| A-P6 | G-old: ≥ 2 families with a non-target `metric:*:spike_*` and no `log:level:*` in that row in ≥ 5/10 | 11 of 11 families (8–10/10) | held as written; post hoc, with G3-admissible spike symbols only, 1 family (image_crash 8/10) reaches 5/10 (finding 10) |
| A-P7 | withdrawn | — | `—` |

## True-by-construction items, where they appear in the tables

- **TBC1** (paused target's `metric:cpu:spike_down`/`plateau_down`; its `missing_expected`): the first half is what `metric:reservation:cpu` 24/24
  in reservation-pause and `metric:search:cpu` 24/24 in search-pause show; the second half described the pause interval, not the frozen
  window W = [`startedAt`, `endedAt`] (`compose_pause.py:108`, `:143`), under which `missing_expected` cannot fire by construction of W
  (0/24 in both regimes); the sensor question is open, not settled.
  G2 removes the first from R(p) anyway.
- **TBC2** (crash target's restart templates are novel; its exception classes in its callers): G-old `log:db:*` 10/10 in db_crash,
  `metric:mem:spike_down` of every crash target; T-new/T-16 `log:template:novel` 9/9 persistence-crash; A-P5.
- **TBC3** (spans silent under none / sample-zero): every span row and the trace-error 0/24 rows of P1.
- **TBC4** (a template in every no-fault cell is inadmissible): H-B, 162 − 1 templates never fire in a fault row, and none of them is what G3
  removed (G3 removed 0 on H-B); G-old `log:webui:a273f9c494c5` 18/30 is removed as a template and survives as a rate (finding 9).
- **TBC5** (T-new/T-16 log FA 0, novelty 1, rate high): every TeaStore log FA of `0/9` in the tables, `log:template:novel` 9/9, `log:rate:…:high` 8/9.
- **TBC6** (C1 agreement): the P1 table.
- **TBC7** (R+ target events): the R+ optimum lines; the G2-removed counts per class.
- **TBC8** (`log:level:warn` on TeaStore crash cells is the sprint's ServiceLoadBalancer count): the `cell`-row level counts behind P1.
- **TBC9** (log4j templates are `cell`-row only on TeaStore): 57 of 58 T-new templates are 0/n in every `fault`-row table.
- Amendment section 9, "more templates means more distinct R sets": H-B 17 distinct sets over 48 episodes, G-old 35 over 110 — mechanical, not results.

## Exclusions, printed

- a-p-w rows (A15): 48 in the bags, in no table. Invalid rows: 22 on T-new (blocked cells), 0 elsewhere.
- Missing rows (a service with no row in an episode): TeaStore image, recommender, webui have rows only under `full` (spans); their
  per-service denominators are therefore the `full` counts, and the exclusion counts are printed beside every per-service cell of
  `tables.md` (`x<m>`). Hotel and G-old: 0 missing rows.
- G-old population: 140 runs kept, 112 excluded for a missing sidecar (empty dirs of later campaigns), 7 for the partial first campaign
  (from `summary.json`; A7).
- Symbols with 0 detections and 0 false alarms in every class are listed by name under each table below as `0/n` (H-B 162, H-B′ 161,
  T-new 64, T-16 64, G-old 187).

## Judge (2026-09-27; `judge_adversarial`, panel of 2: the third provider failed on an expired SSO token)

Per the standing rule for edits, the correctness vote on the current text decides; the significance lens refuted every finding as
"bookkeeping" and is recorded, not acted on. **Deviation, disclosed 2026-09-28:** this step used the `llm_as_judge` MCP, not a Fable
subagent, in deviation from the user's 2026-09-25 instruction (`research/NEXT_STEPS_20260925.md:207`) to use a Fable 5.1
`adversarial-review` subagent for independent review of a result document; the S2 `llm_as_judge` fix was deferred, not withdrawn. The
independent review of record for this document is the Fable 5.1 adversarial review, `REVIEW_RESULT_BASELINE_20260927.md`.

| finding | eval | correctness | what changed |
|---|---|---|---|
| 1 (H-B one template) | `eval_3367718f…` | accepted | nothing |
| 4 (H-B combinations) | `eval_6e0267e4…` | refuted: "adds coverage only for sensors not relevant alone" is not established; partial sensors are not irrelevant | closing sentence replaced by the saturation bound and the 22 + 22 → 24 example |
| 3 (H-B missing_expected 0/24) | `eval_39fa119d…` | refuted on one number: `/rate.Rate/GetRates:error` is 20/24, not 24/24 | corrected to the sensor's 24/24 as error 20/24 ∪ latency_high 14/24 |
| 6 (TeaStore window-level 9/9) | `eval_1efd8efd…` | accepted (limits stated: n = 9, FA 0 by construction, template text not given) | nothing |
| 8 (G-old 7 : 4, D-P5) | `eval_d03f3e09…` | accepted | nothing |
| 9 (G-old rate subsensor) | `eval_5ca213e1…` | accepted as an R2-specific observation | nothing |
| 10 (G-old metrics, A-P6) | `eval_51278a18…` | refuted: "held only through an inadmissible symbol" was not verified | replaced by the post-hoc admissible-only count (1 of 11 families) |
| 11 (G-old span FA 28/30) | `eval_e2c43896…` | refuted: image spans fire 9/10 in image_loss (target), eight positive families include it | corrected; D_f grouping labelled observed, not tested |

## Open questions appended (append-only)

- Amendment TBC1 second half: on H-B the paused service's own operation is `present` in 24/24 episodes of both regimes. Whether the
  Jaeger export's span start times or the 15-s window explain this is not a question the bags answer; it is a definition question for
  `missing_expected` (A2-level) and is left open, not re-run.
- G-old span FA 28/30 vs 10/30 by D_f class: the span rule has no no-fault calibration by design (section 4). Whether G3 should
  extend to span symbols is a preregistration decision (the user's), not an engineering default.
- MAX_K = 8 hides `f_all` on TeaStore (min |R| = 9). A later run may raise the bound; this run's values stand.

---

# Generated tables (verbatim from `tmp/s4-relevance/20260927T102324Z/tables.md`; per-service and per-posture blocks and the full MI rankings are in that file)

## Generation H-B

- services: attractions, frontend, geo, profile, rate, recommendation, reservation, review, search, user; postures: full, none, sample-zero; span-exporting posture: full; fault classes: reservation-pause-effect, search-pause-effect
- episodes per class per posture: {"reservation-pause-effect": {"full": 24, "none": 24, "sample-zero": 24}, "search-pause-effect": {"full": 24, "none": 24, "sample-zero": 24}}
- no-fault pseudo units per posture: {"full": 24, "none": 24, "sample-zero": 24}; per class (G-old per-family): {"reservation-pause-effect": 72, "search-pause-effect": 72}
- rows excluded: a-p-w 0, invalid 0 (both in the bags, in no table)
- symbols: 191 (log 165, metric 3, span 23); sensors: 22; fault rows whose only log symptom is an exception class (reading R1): 0
- true by construction here: TBC3 (span tables are `full` only); TBC1 (target's cpu spike_down/plateau_down and missing_expected)

### H-B: per symbol x fault class, pooled over postures (span: `full` only) and over services

| symbol | postures | reservation-pause-effect k/n (FA k/n0) | search-pause-effect k/n (FA k/n0) |
|---|---|---|---|
| `log:level:error` | full+none+sample-zero | 72/72 (0/72) | 0/72 (0/72) |
| `log:rate:4ae82b46d72e:high` | full+none+sample-zero | 72/72 (0/72) | 0/72 (0/72) |
| `log:template:4ae82b46d72e` | full+none+sample-zero | 72/72 (0/72) | 0/72 (0/72) |
| `metric:cpu:plateau_down` | full+none+sample-zero | 72/72 (0/72) | 72/72 (0/72) |
| `metric:cpu:spike_down` | full+none+sample-zero | 72/72 (1/72) | 72/72 (1/72) |
| `metric:cpu:spike_up` | full+none+sample-zero | 0/72 (9/72) | 0/72 (9/72) |
| `span:/geo.Geo/Nearby:error` | full | 0/24 (0/24) | 24/24 (0/24) |
| `span:/geo.Geo/Nearby:present` | full | 24/24 (24/24) | 24/24 (24/24) |
| `span:/profile.Profile/GetProfiles:latency_high` | full | 12/24 (0/24) | 10/24 (0/24) |
| `span:/profile.Profile/GetProfiles:present` | full | 24/24 (24/24) | 24/24 (24/24) |
| `span:/rate.Rate/GetRates:error` | full | 0/24 (0/24) | 20/24 (0/24) |
| `span:/rate.Rate/GetRates:latency_high` | full | 0/24 (0/24) | 23/24 (0/24) |
| `span:/rate.Rate/GetRates:present` | full | 24/24 (24/24) | 24/24 (24/24) |
| `span:/reservation.Reservation/CheckAvailability:error` | full | 24/24 (0/24) | 0/24 (0/24) |
| `span:/reservation.Reservation/CheckAvailability:latency_high` | full | 24/24 (0/24) | 16/24 (0/24) |
| `span:/reservation.Reservation/CheckAvailability:present` | full | 24/24 (24/24) | 24/24 (24/24) |
| `span:/search.Search/Nearby:error` | full | 0/24 (0/24) | 24/24 (0/24) |
| `span:/search.Search/Nearby:latency_high` | full | 0/24 (0/24) | 24/24 (0/24) |
| `span:/search.Search/Nearby:present` | full | 24/24 (24/24) | 24/24 (24/24) |
| `span:HTTP_GET_/hotels:error` | full | 24/24 (0/24) | 24/24 (0/24) |
| `span:HTTP_GET_/hotels:latency_high` | full | 24/24 (0/24) | 24/24 (0/24) |
| `span:HTTP_GET_/hotels:present` | full | 24/24 (24/24) | 24/24 (24/24) |
| `span:memcached_capacity_get_multi_number:latency_high` | full | 10/24 (0/24) | 0/24 (0/24) |
| `span:memcached_capacity_get_multi_number:present` | full | 24/24 (24/24) | 24/24 (24/24) |
| `span:memcached_get_multi_rate:latency_high` | full | 0/24 (0/24) | 2/24 (0/24) |
| `span:memcached_get_multi_rate:present` | full | 24/24 (24/24) | 24/24 (24/24) |
| `span:memcached_get_profile:latency_high` | full | 1/24 (0/24) | 1/24 (0/24) |
| `span:memcached_get_profile:present` | full | 24/24 (24/24) | 24/24 (24/24) |
| `span:memcached_reserve_get_multi_number:present` | full | 24/24 (24/24) | 24/24 (24/24) |

162 symbols with 0 detections and 0 false alarms in every class (0/n, never dropped; denominators per class as above): `log:template:00536b7b94d5`, `log:template:01e8eaa045e2`, `log:template:055dfa393986`, `log:template:07dd481b9396`, `log:template:09e555132864`, `log:template:11cdf7dd8eaf`, `log:template:12e505c76c0d`, `log:template:13acccf59a97`, `log:template:15acb10ef6f8`, `log:template:1804abfb53da`, `log:template:1c44ffd3cb53`, `log:template:1c9632baa7b5`, `log:template:1f0ece6acb13`, `log:template:1fe01766a3d6`, `log:template:21cd2b59cad4`, `log:template:232853820fe3`, `log:template:258078459703`, `log:template:26291a53ad9e`, `log:template:271959dda561`, `log:template:276af8399ab1`, `log:template:2921b55e8c5d`, `log:template:2c48eb3b7cb0`, `log:template:2e83da16e465`, `log:template:2f21f3c8631a`, `log:template:308d2e26ff38`, `log:template:332ea9e697a5`, `log:template:35a7c43dcf3a`, `log:template:37444c18f485`, `log:template:375916223155`, `log:template:3882cefd51f9`, `log:template:38a718b1543d`, `log:template:38bbbe87b5b6`, `log:template:3b05e7bf5ece`, `log:template:3b216cf602b5`, `log:template:3d4eddfab798`, `log:template:40123bda2132`, `log:template:4110dcc48969`, `log:template:414549186b26`, `log:template:46623cd55a79`, `log:template:4b01134c0baf`, `log:template:4b4dd0bb0c54`, `log:template:4c991508b008`, `log:template:4f3f1a51602e`, `log:template:4ff7b7b4686d`, `log:template:53e3b96770d2`, `log:template:54654c857d3a`, `log:template:55f2ea63fd18`, `log:template:576f30ceac4f`, `log:template:58101b7e189c`, `log:template:5936d995d33c`, `log:template:5a877fb96fa2`, `log:template:5ee6f3b52002`, `log:template:5fbd576cb30b`, `log:template:5fc85944d625`, `log:template:5fe79e84a21f`, `log:template:60a19cf37708`, `log:template:6409fbc62d41`, `log:template:67231ce16f6f`, `log:template:68a5dcda0eee`, `log:template:6afb7a2a9a8a`, `log:template:6c24cb701e52`, `log:template:6c3c861138d6`, `log:template:6d202ee13920`, `log:template:6e715f477a9a`, `log:template:6fe0d55eab17`, `log:template:718138701d5d`, `log:template:75c8cde0a174`, `log:template:76ad34b88297`, `log:template:78552450c79e`, `log:template:7a40a8b4a863`, `log:template:7a5118d938e8`, `log:template:7c526b5b77e7`, `log:template:7d1b15f0b95d`, `log:template:806e53e0c908`, `log:template:82bdf2bc9957`, `log:template:82bef6413f49`, `log:template:8318e9df0f1b`, `log:template:84c3691d2428`, `log:template:850b093f28a5`, `log:template:86e2a49a0a3e`, `log:template:8788e4e9bcb1`, `log:template:8c534c41c8a4`, `log:template:8ff1c15e29dd`, `log:template:9056009088d7`, `log:template:905fd48af873`, `log:template:93986c7d83ea`, `log:template:9430a0f79158`, `log:template:9545bd7940eb`, `log:template:9569f534c2ff`, `log:template:95a770be796b`, `log:template:98d52494ad7f`, `log:template:99c1757edb61`, `log:template:9a746e6bda81`, `log:template:9b2f7fc21c10`, `log:template:9d762f84d590`, `log:template:9e0b362c3c24`, `log:template:9e5a8a14a00a`, `log:template:9eb914cc11d6`, `log:template:a0b297cd71df`, `log:template:a3cb73cdae9c`, `log:template:a4a9e78d113f`, `log:template:abb314f13725`, `log:template:ad516ece47b6`, `log:template:ad9508bcc9f6`, `log:template:ae2cf39559bf`, `log:template:b1f2644df67a`, `log:template:b3561ff8f6dc`, `log:template:b73537dfcea0`, `log:template:ba29678497f0`, `log:template:ba9b6d6b4560`, `log:template:bab9d2072595`, `log:template:bbb5934ce436`, `log:template:bc4eda04de34`, `log:template:bc8293e7a085`, `log:template:bcb678f33ee2`, `log:template:bd7a3576df3d`, `log:template:c06d936e284f`, `log:template:c2625d3f7b03`, `log:template:ce3fd2dcaaeb`, `log:template:cf8f513bcc77`, `log:template:cfe286dc968b`, `log:template:d27c36018a8f`, `log:template:d480f656f3db`, `log:template:d49a85f863ee`, `log:template:d4b09dbd2a1e`, `log:template:d679c0fc8abb`, `log:template:d7b759103302`, `log:template:dac5c0218fcb`, `log:template:dbfb07b81d0d`, `log:template:dc0a2b88d05c`, `log:template:dd002687d281`, `log:template:dd00e063dd7f`, `log:template:dddc2cc40e03`, `log:template:ddf53a329161`, `log:template:dff1c3922d14`, `log:template:e0aa1bbe7892`, `log:template:e20a26205fdc`, `log:template:e42d91bde647`, `log:template:e52457774520`, `log:template:e54ae26d0d63`, `log:template:e76a0f85848f`, `log:template:e7bae46473f9`, `log:template:e86f9382b2bb`, `log:template:ea57197164f4`, `log:template:eb790194c36c`, `log:template:ed317a4e966b`, `log:template:edb2bd9fc569`, `log:template:f0069aa10447`, `log:template:f04748941ec8`, `log:template:f23bf73a52ab`, `log:template:f598fad96168`, `log:template:f59b2912851f`, `log:template:f97fe20ae1f6`, `log:template:fa19b441278d`, `log:template:fa4e75e1ff8e`, `log:template:fb9f0e7f82f6`, `log:template:fba999b5ca8c`, `log:template:fbcffe4122dc`, `log:template:fce1da47ee9f`, `log:template:ff07d12b0f30`, `log:template:ffb561d3b3b5`, `log:template:novel`

### H-B: per sensor x fault class (firing rule, G3 applied; `<mod>:*` = any sensor of the modality, `<mod>:<svc>:*` = any of the service)

| symbol | postures | reservation-pause-effect k/n (FA k/n0) | search-pause-effect k/n (FA k/n0) |
|---|---|---|---|
| `log:frontend:4ae82b46d72e` | full+none+sample-zero | 72/72 (0/72) | 0/72 (0/72) |
| `metric:frontend:cpu` | full+none+sample-zero | 68/72 (4/72) | 72/72 (4/72) |
| `metric:geo:cpu` | full+none+sample-zero | 0/72 (0/72) | 22/72 (0/72) |
| `metric:profile:cpu` | full+none+sample-zero | 71/72 (2/72) | 71/72 (2/72) |
| `metric:rate:cpu` | full+none+sample-zero | 0/72 (0/72) | 72/72 (0/72) |
| `metric:reservation:cpu` | full+none+sample-zero | 71/72 (0/72) | 70/72 (0/72) |
| `metric:search:cpu` | full+none+sample-zero | 0/72 (0/72) | 71/72 (0/72) |
| `span:frontend:/profile.Profile/GetProfiles` | full | 12/24 (0/24) | 10/24 (0/24) |
| `span:frontend:/reservation.Reservation/CheckAvailability` | full | 24/24 (0/24) | 16/24 (0/24) |
| `span:frontend:/search.Search/Nearby` | full | 0/24 (0/24) | 24/24 (0/24) |
| `span:frontend:HTTP_GET_/hotels` | full | 24/24 (0/24) | 24/24 (0/24) |
| `span:profile:/profile.Profile/GetProfiles` | full | 3/24 (0/24) | 0/24 (0/24) |
| `span:profile:memcached_get_profile` | full | 1/24 (0/24) | 1/24 (0/24) |
| `span:rate:/rate.Rate/GetRates` | full | 0/24 (0/24) | 22/24 (0/24) |
| `span:rate:memcached_get_multi_rate` | full | 0/24 (0/24) | 2/24 (0/24) |
| `span:reservation:/reservation.Reservation/CheckAvailability` | full | 24/24 (0/24) | 7/24 (0/24) |
| `span:reservation:memcached_capacity_get_multi_number` | full | 10/24 (0/24) | 0/24 (0/24) |
| `span:search:/geo.Geo/Nearby` | full | 0/24 (0/24) | 24/24 (0/24) |
| `span:search:/rate.Rate/GetRates` | full | 0/24 (0/24) | 24/24 (0/24) |
| `log:*` | full+none+sample-zero | 72/72 (0/72) | 0/72 (0/72) |
| `metric:*` | full+none+sample-zero | 72/72 (6/72) | 72/72 (6/72) |
| `span:*` | full | 24/24 (0/24) | 24/24 (0/24) |
| `log:frontend:*` | full+none+sample-zero | 72/72 (0/72) | 0/72 (0/72) |
| `metric:frontend:*` | full+none+sample-zero | 68/72 (4/72) | 72/72 (4/72) |
| `metric:geo:*` | full+none+sample-zero | 0/72 (0/72) | 22/72 (0/72) |
| `metric:profile:*` | full+none+sample-zero | 71/72 (2/72) | 71/72 (2/72) |
| `metric:rate:*` | full+none+sample-zero | 0/72 (0/72) | 72/72 (0/72) |
| `metric:reservation:*` | full+none+sample-zero | 71/72 (0/72) | 70/72 (0/72) |
| `metric:search:*` | full+none+sample-zero | 0/72 (0/72) | 71/72 (0/72) |
| `span:frontend:*` | full | 24/24 (0/24) | 24/24 (0/24) |
| `span:profile:*` | full | 3/24 (0/24) | 1/24 (0/24) |
| `span:rate:*` | full | 0/24 (0/24) | 22/24 (0/24) |
| `span:reservation:*` | full | 24/24 (0/24) | 7/24 (0/24) |
| `span:search:*` | full | 0/24 (0/24) | 24/24 (0/24) |

4 symbols with 0 detections and 0 false alarms in every class (0/n, never dropped; denominators per class as above): `span:geo:/geo.Geo/Nearby`, `span:reservation:memcached_reserve_get_multi_number`, `span:search:/search.Search/Nearby`, `span:geo:*`

### H-B: combinations on valid fault cells of posture full (sensors firing in >= 1 episode: 19; triples computed)

| class | n | sensors firing | pairs | redundant (conj = min single) | complementary (union > max single) | pairs with conjunction = n | triples beyond every sub-pair |
|---|---|---|---|---|---|---|---|
| reservation-pause-effect | 24 | 11 | 55 | 52 | 3 | 15 | 1 of 165 |
| search-pause-effect | 24 | 16 | 120 | 106 | 14 | 36 | 3 of 560 |

Complementary pairs, reservation-pause-effect (n = 24): `metric:frontend:cpu`(21)+`span:frontend:/profile.Profile/GetProfiles`(12) union 22 conj 11; `metric:frontend:cpu`(21)+`span:reservation:memcached_capacity_get_multi_number`(10) union 23 conj 8; `span:frontend:/profile.Profile/GetProfiles`(12)+`span:reservation:memcached_capacity_get_multi_number`(10) union 18 conj 4

Complementary pairs, search-pause-effect (n = 24): `metric:geo:cpu`(22)+`span:frontend:/profile.Profile/GetProfiles`(10) union 23 conj 9; `metric:geo:cpu`(22)+`span:frontend:/reservation.Reservation/CheckAvailability`(16) union 24 conj 14; `metric:geo:cpu`(22)+`span:rate:/rate.Rate/GetRates`(22) union 24 conj 20; `metric:geo:cpu`(22)+`span:reservation:/reservation.Reservation/CheckAvailability`(7) union 24 conj 5; `span:frontend:/profile.Profile/GetProfiles`(10)+`span:frontend:/reservation.Reservation/CheckAvailability`(16) union 20 conj 6; `span:frontend:/profile.Profile/GetProfiles`(10)+`span:rate:/rate.Rate/GetRates`(22) union 24 conj 8; `span:frontend:/profile.Profile/GetProfiles`(10)+`span:rate:memcached_get_multi_rate`(2) union 12 conj 0; `span:frontend:/profile.Profile/GetProfiles`(10)+`span:reservation:/reservation.Reservation/CheckAvailability`(7) union 15 conj 2; `span:frontend:/reservation.Reservation/CheckAvailability`(16)+`span:profile:memcached_get_profile`(1) union 17 conj 0; `span:frontend:/reservation.Reservation/CheckAvailability`(16)+`span:rate:/rate.Rate/GetRates`(22) union 23 conj 15; `span:profile:memcached_get_profile`(1)+`span:rate:/rate.Rate/GetRates`(22) union 23 conj 0; `span:profile:memcached_get_profile`(1)+`span:rate:memcached_get_multi_rate`(2) union 3 conj 0; `span:profile:memcached_get_profile`(1)+`span:reservation:/reservation.Reservation/CheckAvailability`(7) union 8 conj 0; `span:rate:memcached_get_multi_rate`(2)+`span:reservation:/reservation.Reservation/CheckAvailability`(7) union 9 conj 0

### H-B: mutual information I(symbol; class), bits, plug-in (ranking aid, no test)

| symbol | pooled bits (n; class sizes) | per service (bits, n) |
|---|---|---|
| `log:level:error` | 0.918 (216; {"reservation-pause-effect": 72, "search-pause-effect": 72, "no-fault": 72}) | frontend 0.918 (216) |
| `log:rate:4ae82b46d72e:high` | 0.918 (216; {"reservation-pause-effect": 72, "search-pause-effect": 72, "no-fault": 72}) | frontend 0.918 (216) |
| `log:template:4ae82b46d72e` | 0.918 (216; {"reservation-pause-effect": 72, "search-pause-effect": 72, "no-fault": 72}) | frontend 0.918 (216) |
| `metric:cpu:plateau_down` | 0.918 (216; {"reservation-pause-effect": 72, "search-pause-effect": 72, "no-fault": 72}) | frontend 0.747 (216); geo 0.170 (216); profile 0.857 (216); rate 0.918 (216); reservation 0.835 (216); search 0.878 (216) |
| `span:/geo.Geo/Nearby:error` | 0.918 (72; {"reservation-pause-effect": 24, "search-pause-effect": 24, "no-fault": 24}) | search 0.918 (72) |
| `span:/reservation.Reservation/CheckAvailability:error` | 0.918 (72; {"reservation-pause-effect": 24, "search-pause-effect": 24, "no-fault": 24}) | frontend 0.918 (72) |
| `span:/search.Search/Nearby:error` | 0.918 (72; {"reservation-pause-effect": 24, "search-pause-effect": 24, "no-fault": 24}) | frontend 0.918 (72) |
| `span:/search.Search/Nearby:latency_high` | 0.918 (72; {"reservation-pause-effect": 24, "search-pause-effect": 24, "no-fault": 24}) | frontend 0.918 (72) |
| `span:HTTP_GET_/hotels:error` | 0.918 (72; {"reservation-pause-effect": 24, "search-pause-effect": 24, "no-fault": 24}) | frontend 0.918 (72) |
| `span:HTTP_GET_/hotels:latency_high` | 0.918 (72; {"reservation-pause-effect": 24, "search-pause-effect": 24, "no-fault": 24}) | frontend 0.918 (72) |
| `metric:cpu:spike_down` | 0.878 (216; {"reservation-pause-effect": 72, "search-pause-effect": 72, "no-fault": 72}) | frontend 0.793 (216); geo 0.179 (216); profile 0.857 (216); rate 0.918 (216); reservation 0.835 (216); search 0.878 (216) |
| `span:/rate.Rate/GetRates:latency_high` | 0.820 (72; {"reservation-pause-effect": 24, "search-pause-effect": 24, "no-fault": 24}) | rate 0.750 (72); search 0.384 (72) |
| `span:/reservation.Reservation/CheckAvailability:latency_high` | 0.685 (72; {"reservation-pause-effect": 24, "search-pause-effect": 24, "no-fault": 24}) | frontend 0.685 (72); reservation 0.696 (72) |
| `span:/rate.Rate/GetRates:error` | 0.636 (72; {"reservation-pause-effect": 24, "search-pause-effect": 24, "no-fault": 24}) | search 0.636 (72) |
| `span:memcached_capacity_get_multi_number:latency_high` | 0.255 (72; {"reservation-pause-effect": 24, "search-pause-effect": 24, "no-fault": 24}) | reservation 0.255 (72) |

(top 15 of the ranking; the full ranking is in `tables.md`)
symbols with I = 0 bits pooled: 172 of 191

### H-B: R(p) with G1-G6 (span-exporting episodes)

- episodes: 48; |R| distribution: {"4": 2, "5": 11, "6": 8, "7": 2, "8": 5, "9": 9, "10": 10, "11": 1}; distinct R sets: 17; empty R: 0; G4 metric-without-log: 24
- composition per class: {"reservation-pause-effect": {"log+metric+span": 24}, "search-pause-effect": {"metric+span": 24}}
- G2 removed (target-service sensors) per class: {"reservation-pause-effect": 58, "search-pause-effect": 72}; G3 removed per class: {"reservation-pause-effect": 0, "search-pause-effect": 0}
- max f_all / f_any per k (exact (union enumeration over 17 distinct R sets)): k=1 all 0 any 48 (exact); k=2 all 0 any 48 (exact); k=3 all 0 any 48 (exact); k=4 all 2 any 48 (exact); k=5 all 12 any 48 (exact); k=6 all 21 any 48 (exact); k=7 all 23 any 48 (exact); k=8 all 24 any 48 (exact)
- R+ (G2 off): distinct 19; max f_all per k: k=1 0; k=2 0; k=3 0; k=4 0; k=5 0; k=6 0; k=7 6; k=8 14
- level sets over the catalogue domain: -- (R11)

## Generation H-Bp

- services: attractions, frontend, geo, profile, rate, recommendation, reservation, review, search, user; postures: full, none, sample-zero; span-exporting posture: full; fault classes: reservation-pause-effect, search-pause-effect
- episodes per class per posture: {"reservation-pause-effect": {"full": 6, "none": 6, "sample-zero": 6}, "search-pause-effect": {"full": 6, "none": 6, "sample-zero": 6}}
- no-fault pseudo units per posture: {"full": 6, "none": 6, "sample-zero": 6}; per class (G-old per-family): {"reservation-pause-effect": 18, "search-pause-effect": 18}
- rows excluded: a-p-w 0, invalid 0 (both in the bags, in no table)
- symbols: 189 (log 164, metric 3, span 22); sensors: 22; fault rows whose only log symptom is an exception class (reading R1): 0
- true by construction here: TBC3 (span tables are `full` only); TBC1 (target's cpu spike_down/plateau_down and missing_expected)

### H-Bp: per symbol x fault class, pooled over postures (span: `full` only) and over services

| symbol | postures | reservation-pause-effect k/n (FA k/n0) | search-pause-effect k/n (FA k/n0) |
|---|---|---|---|
| `log:level:error` | full+none+sample-zero | 18/18 (0/18) | 1/18 (0/18) |
| `log:rate:4ae82b46d72e:high` | full+none+sample-zero | 18/18 (0/18) | 0/18 (0/18) |
| `log:template:4ae82b46d72e` | full+none+sample-zero | 18/18 (0/18) | 1/18 (0/18) |
| `metric:cpu:plateau_down` | full+none+sample-zero | 18/18 (0/18) | 18/18 (0/18) |
| `metric:cpu:spike_down` | full+none+sample-zero | 18/18 (0/18) | 18/18 (0/18) |
| `metric:cpu:spike_up` | full+none+sample-zero | 0/18 (1/18) | 0/18 (1/18) |
| `span:/geo.Geo/Nearby:error` | full | 0/6 (0/6) | 6/6 (0/6) |
| `span:/geo.Geo/Nearby:present` | full | 6/6 (6/6) | 6/6 (6/6) |
| `span:/profile.Profile/GetProfiles:latency_high` | full | 4/6 (0/6) | 2/6 (0/6) |
| `span:/profile.Profile/GetProfiles:present` | full | 6/6 (6/6) | 6/6 (6/6) |
| `span:/rate.Rate/GetRates:error` | full | 0/6 (0/6) | 6/6 (0/6) |
| `span:/rate.Rate/GetRates:latency_high` | full | 0/6 (0/6) | 5/6 (0/6) |
| `span:/rate.Rate/GetRates:present` | full | 6/6 (6/6) | 6/6 (6/6) |
| `span:/reservation.Reservation/CheckAvailability:error` | full | 6/6 (0/6) | 1/6 (0/6) |
| `span:/reservation.Reservation/CheckAvailability:latency_high` | full | 6/6 (0/6) | 4/6 (0/6) |
| `span:/reservation.Reservation/CheckAvailability:present` | full | 6/6 (6/6) | 6/6 (6/6) |
| `span:/search.Search/Nearby:error` | full | 0/6 (0/6) | 6/6 (0/6) |
| `span:/search.Search/Nearby:latency_high` | full | 0/6 (0/6) | 6/6 (0/6) |
| `span:/search.Search/Nearby:present` | full | 6/6 (6/6) | 6/6 (6/6) |
| `span:HTTP_GET_/hotels:error` | full | 6/6 (0/6) | 6/6 (0/6) |
| `span:HTTP_GET_/hotels:latency_high` | full | 6/6 (0/6) | 6/6 (0/6) |
| `span:HTTP_GET_/hotels:present` | full | 6/6 (6/6) | 6/6 (6/6) |
| `span:memcached_capacity_get_multi_number:latency_high` | full | 1/6 (0/6) | 0/6 (0/6) |
| `span:memcached_capacity_get_multi_number:present` | full | 6/6 (6/6) | 6/6 (6/6) |
| `span:memcached_get_multi_rate:present` | full | 6/6 (6/6) | 6/6 (6/6) |
| `span:memcached_get_profile:latency_high` | full | 2/6 (0/6) | 0/6 (0/6) |
| `span:memcached_get_profile:present` | full | 6/6 (6/6) | 6/6 (6/6) |
| `span:memcached_reserve_get_multi_number:present` | full | 6/6 (6/6) | 6/6 (6/6) |

161 symbols with 0 detections and 0 false alarms in every class (0/n, never dropped; denominators per class as above): `log:template:00536b7b94d5`, `log:template:01e8eaa045e2`, `log:template:055dfa393986`, `log:template:07dd481b9396`, `log:template:09e555132864`, `log:template:11cdf7dd8eaf`, `log:template:12e505c76c0d`, `log:template:13acccf59a97`, `log:template:15acb10ef6f8`, `log:template:1804abfb53da`, `log:template:1c44ffd3cb53`, `log:template:1c9632baa7b5`, `log:template:1f0ece6acb13`, `log:template:1fe01766a3d6`, `log:template:21cd2b59cad4`, `log:template:232853820fe3`, `log:template:258078459703`, `log:template:26291a53ad9e`, `log:template:271959dda561`, `log:template:276af8399ab1`, `log:template:2921b55e8c5d`, `log:template:2c48eb3b7cb0`, `log:template:2e83da16e465`, `log:template:2f21f3c8631a`, `log:template:308d2e26ff38`, `log:template:332ea9e697a5`, `log:template:35a7c43dcf3a`, `log:template:37444c18f485`, `log:template:375916223155`, `log:template:3882cefd51f9`, `log:template:38a718b1543d`, `log:template:38bbbe87b5b6`, `log:template:3b05e7bf5ece`, `log:template:3b216cf602b5`, `log:template:3d4eddfab798`, `log:template:40123bda2132`, `log:template:4110dcc48969`, `log:template:414549186b26`, `log:template:46623cd55a79`, `log:template:4b01134c0baf`, `log:template:4c991508b008`, `log:template:4f3f1a51602e`, `log:template:4ff7b7b4686d`, `log:template:53e3b96770d2`, `log:template:54654c857d3a`, `log:template:55f2ea63fd18`, `log:template:576f30ceac4f`, `log:template:58101b7e189c`, `log:template:5936d995d33c`, `log:template:5a877fb96fa2`, `log:template:5ee6f3b52002`, `log:template:5fbd576cb30b`, `log:template:5fc85944d625`, `log:template:5fe79e84a21f`, `log:template:60a19cf37708`, `log:template:6409fbc62d41`, `log:template:67231ce16f6f`, `log:template:68a5dcda0eee`, `log:template:6afb7a2a9a8a`, `log:template:6c24cb701e52`, `log:template:6c3c861138d6`, `log:template:6d202ee13920`, `log:template:6e715f477a9a`, `log:template:6fe0d55eab17`, `log:template:718138701d5d`, `log:template:75c8cde0a174`, `log:template:76ad34b88297`, `log:template:78552450c79e`, `log:template:7a40a8b4a863`, `log:template:7a5118d938e8`, `log:template:7c526b5b77e7`, `log:template:7d1b15f0b95d`, `log:template:806e53e0c908`, `log:template:82bdf2bc9957`, `log:template:82bef6413f49`, `log:template:8318e9df0f1b`, `log:template:84c3691d2428`, `log:template:850b093f28a5`, `log:template:86e2a49a0a3e`, `log:template:8788e4e9bcb1`, `log:template:8c534c41c8a4`, `log:template:8ff1c15e29dd`, `log:template:9056009088d7`, `log:template:905fd48af873`, `log:template:93986c7d83ea`, `log:template:9430a0f79158`, `log:template:9545bd7940eb`, `log:template:9569f534c2ff`, `log:template:95a770be796b`, `log:template:98d52494ad7f`, `log:template:99c1757edb61`, `log:template:9a746e6bda81`, `log:template:9b2f7fc21c10`, `log:template:9d762f84d590`, `log:template:9e0b362c3c24`, `log:template:9e5a8a14a00a`, `log:template:9eb914cc11d6`, `log:template:a0b297cd71df`, `log:template:a3cb73cdae9c`, `log:template:a4a9e78d113f`, `log:template:abb314f13725`, `log:template:ad516ece47b6`, `log:template:ad9508bcc9f6`, `log:template:ae2cf39559bf`, `log:template:b1f2644df67a`, `log:template:b3561ff8f6dc`, `log:template:b73537dfcea0`, `log:template:ba29678497f0`, `log:template:ba9b6d6b4560`, `log:template:bab9d2072595`, `log:template:bbb5934ce436`, `log:template:bc4eda04de34`, `log:template:bc8293e7a085`, `log:template:bcb678f33ee2`, `log:template:bd7a3576df3d`, `log:template:c06d936e284f`, `log:template:c2625d3f7b03`, `log:template:ce3fd2dcaaeb`, `log:template:cf8f513bcc77`, `log:template:cfe286dc968b`, `log:template:d27c36018a8f`, `log:template:d480f656f3db`, `log:template:d49a85f863ee`, `log:template:d4b09dbd2a1e`, `log:template:d679c0fc8abb`, `log:template:d7b759103302`, `log:template:dac5c0218fcb`, `log:template:dbfb07b81d0d`, `log:template:dc0a2b88d05c`, `log:template:dd002687d281`, `log:template:dd00e063dd7f`, `log:template:dddc2cc40e03`, `log:template:ddf53a329161`, `log:template:dff1c3922d14`, `log:template:e0aa1bbe7892`, `log:template:e20a26205fdc`, `log:template:e42d91bde647`, `log:template:e52457774520`, `log:template:e54ae26d0d63`, `log:template:e76a0f85848f`, `log:template:e7bae46473f9`, `log:template:e86f9382b2bb`, `log:template:ea57197164f4`, `log:template:eb790194c36c`, `log:template:ed317a4e966b`, `log:template:edb2bd9fc569`, `log:template:f0069aa10447`, `log:template:f04748941ec8`, `log:template:f23bf73a52ab`, `log:template:f598fad96168`, `log:template:f59b2912851f`, `log:template:f97fe20ae1f6`, `log:template:fa19b441278d`, `log:template:fa4e75e1ff8e`, `log:template:fb9f0e7f82f6`, `log:template:fba999b5ca8c`, `log:template:fbcffe4122dc`, `log:template:fce1da47ee9f`, `log:template:ff07d12b0f30`, `log:template:ffb561d3b3b5`, `log:template:novel`

### H-Bp: per sensor x fault class (firing rule, G3 applied; `<mod>:*` = any sensor of the modality, `<mod>:<svc>:*` = any of the service)

| symbol | postures | reservation-pause-effect k/n (FA k/n0) | search-pause-effect k/n (FA k/n0) |
|---|---|---|---|
| `log:frontend:4ae82b46d72e` | full+none+sample-zero | 18/18 (0/18) | 1/18 (0/18) |
| `metric:frontend:cpu` | full+none+sample-zero | 18/18 (0/18) | 18/18 (0/18) |
| `metric:geo:cpu` | full+none+sample-zero | 0/18 (0/18) | 5/18 (0/18) |
| `metric:profile:cpu` | full+none+sample-zero | 18/18 (0/18) | 17/18 (0/18) |
| `metric:rate:cpu` | full+none+sample-zero | 0/18 (0/18) | 18/18 (0/18) |
| `metric:reservation:cpu` | full+none+sample-zero | 17/18 (0/18) | 18/18 (0/18) |
| `metric:search:cpu` | full+none+sample-zero | 0/18 (0/18) | 18/18 (0/18) |
| `span:frontend:/profile.Profile/GetProfiles` | full | 4/6 (0/6) | 2/6 (0/6) |
| `span:frontend:/reservation.Reservation/CheckAvailability` | full | 6/6 (0/6) | 5/6 (0/6) |
| `span:frontend:/search.Search/Nearby` | full | 0/6 (0/6) | 6/6 (0/6) |
| `span:frontend:HTTP_GET_/hotels` | full | 6/6 (0/6) | 6/6 (0/6) |
| `span:profile:/profile.Profile/GetProfiles` | full | 2/6 (0/6) | 0/6 (0/6) |
| `span:profile:memcached_get_profile` | full | 2/6 (0/6) | 0/6 (0/6) |
| `span:rate:/rate.Rate/GetRates` | full | 0/6 (0/6) | 4/6 (0/6) |
| `span:reservation:/reservation.Reservation/CheckAvailability` | full | 4/6 (0/6) | 0/6 (0/6) |
| `span:reservation:memcached_capacity_get_multi_number` | full | 1/6 (0/6) | 0/6 (0/6) |
| `span:search:/geo.Geo/Nearby` | full | 0/6 (0/6) | 6/6 (0/6) |
| `span:search:/rate.Rate/GetRates` | full | 0/6 (0/6) | 6/6 (0/6) |
| `log:*` | full+none+sample-zero | 18/18 (0/18) | 1/18 (0/18) |
| `metric:*` | full+none+sample-zero | 18/18 (0/18) | 18/18 (0/18) |
| `span:*` | full | 6/6 (0/6) | 6/6 (0/6) |
| `log:frontend:*` | full+none+sample-zero | 18/18 (0/18) | 1/18 (0/18) |
| `metric:frontend:*` | full+none+sample-zero | 18/18 (0/18) | 18/18 (0/18) |
| `metric:geo:*` | full+none+sample-zero | 0/18 (0/18) | 5/18 (0/18) |
| `metric:profile:*` | full+none+sample-zero | 18/18 (0/18) | 17/18 (0/18) |
| `metric:rate:*` | full+none+sample-zero | 0/18 (0/18) | 18/18 (0/18) |
| `metric:reservation:*` | full+none+sample-zero | 17/18 (0/18) | 18/18 (0/18) |
| `metric:search:*` | full+none+sample-zero | 0/18 (0/18) | 18/18 (0/18) |
| `span:frontend:*` | full | 6/6 (0/6) | 6/6 (0/6) |
| `span:profile:*` | full | 2/6 (0/6) | 0/6 (0/6) |
| `span:rate:*` | full | 0/6 (0/6) | 4/6 (0/6) |
| `span:reservation:*` | full | 4/6 (0/6) | 0/6 (0/6) |
| `span:search:*` | full | 0/6 (0/6) | 6/6 (0/6) |

5 symbols with 0 detections and 0 false alarms in every class (0/n, never dropped; denominators per class as above): `span:geo:/geo.Geo/Nearby`, `span:rate:memcached_get_multi_rate`, `span:reservation:memcached_reserve_get_multi_number`, `span:search:/search.Search/Nearby`, `span:geo:*`

### H-Bp: combinations on valid fault cells of posture full (sensors firing in >= 1 episode: 18; triples computed)

| class | n | sensors firing | pairs | redundant (conj = min single) | complementary (union > max single) | pairs with conjunction = n | triples beyond every sub-pair |
|---|---|---|---|---|---|---|---|
| reservation-pause-effect | 6 | 11 | 55 | 50 | 5 | 15 | 0 of 165 |
| search-pause-effect | 6 | 14 | 91 | 87 | 4 | 36 | 0 of 364 |

Complementary pairs, reservation-pause-effect (n = 6): `span:frontend:/profile.Profile/GetProfiles`(4)+`span:reservation:/reservation.Reservation/CheckAvailability`(4) union 5 conj 3; `span:profile:/profile.Profile/GetProfiles`(2)+`span:reservation:/reservation.Reservation/CheckAvailability`(4) union 5 conj 1; `span:profile:/profile.Profile/GetProfiles`(2)+`span:reservation:memcached_capacity_get_multi_number`(1) union 3 conj 0; `span:profile:memcached_get_profile`(2)+`span:reservation:/reservation.Reservation/CheckAvailability`(4) union 5 conj 1; `span:profile:memcached_get_profile`(2)+`span:reservation:memcached_capacity_get_multi_number`(1) union 3 conj 0

Complementary pairs, search-pause-effect (n = 6): `log:frontend:4ae82b46d72e`(1)+`span:frontend:/profile.Profile/GetProfiles`(2) union 3 conj 0; `metric:geo:cpu`(5)+`span:rate:/rate.Rate/GetRates`(4) union 6 conj 3; `span:frontend:/profile.Profile/GetProfiles`(2)+`span:rate:/rate.Rate/GetRates`(4) union 5 conj 1; `span:frontend:/reservation.Reservation/CheckAvailability`(5)+`span:rate:/rate.Rate/GetRates`(4) union 6 conj 3

### H-Bp: mutual information I(symbol; class), bits, plug-in (ranking aid, no test)

| symbol | pooled bits (n; class sizes) | per service (bits, n) |
|---|---|---|
| `log:rate:4ae82b46d72e:high` | 0.918 (54; {"reservation-pause-effect": 18, "search-pause-effect": 18, "no-fault": 18}) | frontend 0.918 (54) |
| `metric:cpu:plateau_down` | 0.918 (54; {"reservation-pause-effect": 18, "search-pause-effect": 18, "no-fault": 18}) | frontend 0.833 (54); geo 0.161 (54); profile 0.833 (54); rate 0.918 (54); reservation 0.833 (54); search 0.918 (54) |
| `metric:cpu:spike_down` | 0.918 (54; {"reservation-pause-effect": 18, "search-pause-effect": 18, "no-fault": 18}) | frontend 0.918 (54); geo 0.161 (54); profile 0.833 (54); rate 0.918 (54); reservation 0.833 (54); search 0.918 (54) |
| `span:/geo.Geo/Nearby:error` | 0.918 (18; {"reservation-pause-effect": 6, "search-pause-effect": 6, "no-fault": 6}) | search 0.918 (18) |
| `span:/rate.Rate/GetRates:error` | 0.918 (18; {"reservation-pause-effect": 6, "search-pause-effect": 6, "no-fault": 6}) | search 0.918 (18) |
| `span:/search.Search/Nearby:error` | 0.918 (18; {"reservation-pause-effect": 6, "search-pause-effect": 6, "no-fault": 6}) | frontend 0.918 (18) |
| `span:/search.Search/Nearby:latency_high` | 0.918 (18; {"reservation-pause-effect": 6, "search-pause-effect": 6, "no-fault": 6}) | frontend 0.918 (18) |
| `span:HTTP_GET_/hotels:error` | 0.918 (18; {"reservation-pause-effect": 6, "search-pause-effect": 6, "no-fault": 6}) | frontend 0.918 (18) |
| `span:HTTP_GET_/hotels:latency_high` | 0.918 (18; {"reservation-pause-effect": 6, "search-pause-effect": 6, "no-fault": 6}) | frontend 0.918 (18) |
| `log:level:error` | 0.833 (54; {"reservation-pause-effect": 18, "search-pause-effect": 18, "no-fault": 18}) | frontend 0.833 (54) |
| `log:template:4ae82b46d72e` | 0.833 (54; {"reservation-pause-effect": 18, "search-pause-effect": 18, "no-fault": 18}) | frontend 0.833 (54) |
| `span:/reservation.Reservation/CheckAvailability:error` | 0.747 (18; {"reservation-pause-effect": 6, "search-pause-effect": 6, "no-fault": 6}) | frontend 0.747 (18) |
| `span:/reservation.Reservation/CheckAvailability:latency_high` | 0.685 (18; {"reservation-pause-effect": 6, "search-pause-effect": 6, "no-fault": 6}) | frontend 0.685 (18); reservation 0.458 (18) |
| `span:/rate.Rate/GetRates:latency_high` | 0.636 (18; {"reservation-pause-effect": 6, "search-pause-effect": 6, "no-fault": 6}) | rate 0.458 (18); search 0.636 (18) |
| `span:/profile.Profile/GetProfiles:latency_high` | 0.306 (18; {"reservation-pause-effect": 6, "search-pause-effect": 6, "no-fault": 6}) | frontend 0.306 (18); profile 0.197 (18) |

(top 15 of the ranking; the full ranking is in `tables.md`)
symbols with I = 0 bits pooled: 171 of 189

### H-Bp: R(p) with G1-G6 (span-exporting episodes)

- episodes: 12; |R| distribution: {"5": 2, "6": 2, "7": 1, "8": 3, "9": 2, "10": 2}; distinct R sets: 9; empty R: 0; G4 metric-without-log: 5
- composition per class: {"reservation-pause-effect": {"log+metric+span": 6}, "search-pause-effect": {"metric+span": 5, "log+metric+span": 1}}
- G2 removed (target-service sensors) per class: {"reservation-pause-effect": 11, "search-pause-effect": 18}; G3 removed per class: {"reservation-pause-effect": 0, "search-pause-effect": 0}
- max f_all / f_any per k (exact (union enumeration over 9 distinct R sets)): k=1 all 0 any 12 (exact); k=2 all 0 any 12 (exact); k=3 all 0 any 12 (exact); k=4 all 0 any 12 (exact); k=5 all 2 any 12 (exact); k=6 all 4 any 12 (exact); k=7 all 4 any 12 (exact); k=8 all 6 any 12 (exact)
- R+ (G2 off): distinct 12; max f_all per k: k=1 0; k=2 0; k=3 0; k=4 0; k=5 0; k=6 1; k=7 2; k=8 3
- level sets over the catalogue domain: -- (R11)

## Generation T-new

- services: auth, image, persistence, recommender, webui; postures: full, none, selected; span-exporting posture: full; fault classes: auth-freeze-effect, persistence-crash-effect
- episodes per class per posture: {"auth-freeze-effect": {"full": 2, "none": 3, "selected": 3}, "persistence-crash-effect": {"full": 3, "none": 3, "selected": 3}}
- no-fault pseudo units per posture: {"full": 3, "none": 3, "selected": 3}; per class (G-old per-family): {"auth-freeze-effect": 9, "persistence-crash-effect": 9}
- rows excluded: a-p-w 48, invalid 22 (both in the bags, in no table)
- symbols: 137 (log 68, metric 0, span 69); sensors: 38; fault rows whose only log symptom is an exception class (reading R1): 0
- true by construction here: TBC3 (span tables are `full` only); TBC5 (every log FA is 0/n0 and every template is novel by construction); TBC9 (log4j templates are cell-row only); TBC8

### T-new: per symbol x fault class, pooled over postures (span: `full` only) and over services

| symbol | postures | auth-freeze-effect k/n (FA k/n0) | persistence-crash-effect k/n (FA k/n0) |
|---|---|---|---|
| `log:level:warn` | full+none+selected | 0/8 (0/9) | 9/9 (0/9) |
| `log:rate:6c19cf62298a:high` | full+none+selected | 0/8 (0/9) | 8/9 (0/9) |
| `log:template:6c19cf62298a` | full+none+selected | 0/8 (0/9) | 9/9 (0/9) |
| `log:template:novel` | full+none+selected | 0/8 (0/9) | 9/9 (0/9) |
| `span:AbstractCache.getEntries:present` | full | 2/2 (3/3) | 3/3 (3/3) |
| `span:AbstractCache.loadData:present` | full | 2/2 (3/3) | 3/3 (3/3) |
| `span:AuthUserActionsRest.isLoggedIn:missing_expected` | full | 2/2 (0/3) | 0/3 (0/3) |
| `span:AuthUserActionsRest.isLoggedIn:present` | full | 0/2 (3/3) | 3/3 (3/3) |
| `span:AuthUserActionsRest.login:missing_expected` | full | 2/2 (0/3) | 0/3 (0/3) |
| `span:AuthUserActionsRest.login:present` | full | 0/2 (3/3) | 3/3 (3/3) |
| `span:BCryptProvider.checkPassword:missing_expected` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:BCryptProvider.checkPassword:present` | full | 0/2 (3/3) | 0/3 (3/3) |
| `span:CategoryEndpoint.findEntityById:missing_expected` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:CategoryEndpoint.findEntityById:present` | full | 2/2 (3/3) | 0/3 (3/3) |
| `span:CategoryEndpoint.listAllEntities:missing_expected` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:CategoryEndpoint.listAllEntities:present` | full | 2/2 (3/3) | 0/3 (3/3) |
| `span:CategoryServlet.handleGETRequest:latency_high` | full | 1/2 (0/3) | 0/3 (0/3) |
| `span:CategoryServlet.handleGETRequest:missing_expected` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:CategoryServlet.handleGETRequest:present` | full | 2/2 (3/3) | 0/3 (3/3) |
| `span:DriveStorage.loadData:missing_expected` | full | 1/2 (0/3) | 3/3 (0/3) |
| `span:DriveStorage.loadData:present` | full | 0/2 (3/3) | 0/3 (3/3) |
| `span:ImageProvider.getImageFor:present` | full | 2/2 (3/3) | 3/3 (3/3) |
| `span:ImageProvider.scaleAndRegisterImg:present` | full | 0/2 (3/3) | 0/3 (3/3) |
| `span:ImageProviderEndpoint.getProductImages:missing_expected` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:ImageProviderEndpoint.getProductImages:present` | full | 2/2 (3/3) | 0/3 (3/3) |
| `span:ImageProviderEndpoint.getWebUIImages:present` | full | 2/2 (3/3) | 3/3 (3/3) |
| `span:IndexServlet.handleGETRequest:latency_high` | full | 0/2 (0/3) | 2/3 (0/3) |
| `span:IndexServlet.handleGETRequest:present` | full | 2/2 (3/3) | 3/3 (3/3) |
| `span:LoginActionServlet.handlePOSTRequest:present` | full | 2/2 (3/3) | 3/3 (3/3) |
| `span:LoginServlet.handleGETRequest:present` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:PersistenceCategory.getId:missing_expected` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:PersistenceCategory.getId:present` | full | 2/2 (3/3) | 0/3 (3/3) |
| `span:PersistenceProduct.getId:missing_expected` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:PersistenceProduct.getId:present` | full | 2/2 (3/3) | 0/3 (3/3) |
| `span:PersistenceUser.getId:missing_expected` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:PersistenceUser.getId:present` | full | 0/2 (3/3) | 0/3 (3/3) |
| `span:PopularityBasedRecommender.execute:missing_expected` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:PopularityBasedRecommender.execute:present` | full | 0/2 (3/3) | 0/3 (3/3) |
| `span:ProductEndpoint.countForCategory:missing_expected` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:ProductEndpoint.countForCategory:present` | full | 2/2 (3/3) | 0/3 (3/3) |
| `span:ProductEndpoint.findEntityById:missing_expected` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:ProductEndpoint.findEntityById:present` | full | 0/2 (3/3) | 0/3 (3/3) |
| `span:ProductEndpoint.listAllForCategory:missing_expected` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:ProductEndpoint.listAllForCategory:present` | full | 2/2 (3/3) | 0/3 (3/3) |
| `span:ProductRepository.getAllEntities:missing_expected` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:ProductRepository.getAllEntities:present` | full | 2/2 (3/3) | 0/3 (3/3) |
| `span:ProductRepository.getProductCount:missing_expected` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:ProductRepository.getProductCount:present` | full | 2/2 (3/3) | 0/3 (3/3) |
| `span:ProductServlet.handleGETRequest:latency_high` | full | 1/2 (0/3) | 0/3 (0/3) |
| `span:ProductServlet.handleGETRequest:missing_expected` | full | 1/2 (0/3) | 3/3 (0/3) |
| `span:ProductServlet.handleGETRequest:present` | full | 1/2 (3/3) | 0/3 (3/3) |
| `span:RandomSessionIdGenerator.getSessionId:missing_expected` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:RandomSessionIdGenerator.getSessionId:present` | full | 0/2 (3/3) | 0/3 (3/3) |
| `span:RecommendEndpoint.recommend:missing_expected` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:RecommendEndpoint.recommend:present` | full | 0/2 (3/3) | 0/3 (3/3) |
| `span:RecommenderSelector.recommendProducts:missing_expected` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:RecommenderSelector.recommendProducts:present` | full | 0/2 (3/3) | 0/3 (3/3) |
| `span:ShaSecurityProvider.blobToString:missing_expected` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:ShaSecurityProvider.blobToString:present` | full | 0/2 (3/3) | 0/3 (3/3) |
| `span:ShaSecurityProvider.getKeyProvider:missing_expected` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:ShaSecurityProvider.getKeyProvider:present` | full | 0/2 (3/3) | 0/3 (3/3) |
| `span:ShaSecurityProvider.getSha512:missing_expected` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:ShaSecurityProvider.getSha512:present` | full | 0/2 (3/3) | 0/3 (3/3) |
| `span:ShaSecurityProvider.secure:missing_expected` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:ShaSecurityProvider.secure:present` | full | 0/2 (3/3) | 0/3 (3/3) |
| `span:ShaSecurityProvider.validate:missing_expected` | full | 2/2 (0/3) | 0/3 (0/3) |
| `span:ShaSecurityProvider.validate:present` | full | 0/2 (3/3) | 3/3 (3/3) |
| `span:SlopeOneRecommender.execute:missing_expected` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:SlopeOneRecommender.execute:present` | full | 0/2 (3/3) | 0/3 (3/3) |
| `span:UserEndpoint.findById:missing_expected` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:UserEndpoint.findById:present` | full | 0/2 (3/3) | 0/3 (3/3) |
| `span:UserRepository.getUserByName:missing_expected` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:UserRepository.getUserByName:present` | full | 0/2 (3/3) | 0/3 (3/3) |

64 symbols with 0 detections and 0 false alarms in every class (0/n, never dropped; denominators per class as above): `log:exception:ClientException`, `log:exception:ProcessingException`, `log:exception:StringIndexOutOfBoundsException`, `log:exception:UnresolvedAddressException`, `log:level:error`, `log:rate:c5fb88a70fe6:high`, `log:rate:d4d75ec135e6:high`, `log:template:0098f0714240`, `log:template:059f77b5fee4`, `log:template:0788a45dbb86`, `log:template:0ae227c4f15d`, `log:template:13e7be34fb70`, `log:template:147f864363b1`, `log:template:16e888bf8922`, `log:template:16f327e6bd4d`, `log:template:25e233b98160`, `log:template:2d7f16630b87`, `log:template:2ff20a342a41`, `log:template:319b41b82d9b`, `log:template:3219d9dbbaed`, `log:template:35563463c928`, `log:template:35873ee1cc7e`, `log:template:3917ffeac5ec`, `log:template:3b1fa69c3451`, `log:template:407989c51698`, `log:template:4a79ac521b28`, `log:template:4de8468724c7`, `log:template:52a075c95ff9`, `log:template:546670de7509`, `log:template:56bcc1a07d39`, `log:template:56c309f6427c`, `log:template:61451078c684`, `log:template:66d09055f528`, `log:template:6e7a7f83a9e6`, `log:template:7197cbb5d81b`, `log:template:72ae3fa150b5`, `log:template:798861287e32`, `log:template:811e1f658b4b`, `log:template:8733ab2f4543`, `log:template:87614f556af3`, `log:template:8b277994d6dd`, `log:template:8eb94ac35bf9`, `log:template:955560e889b3`, `log:template:96ea0f608ef2`, `log:template:96eef0c939e4`, `log:template:9c6795a8c551`, `log:template:a0105883ccdd`, `log:template:a07c7bcc6c3d`, `log:template:a59061884c18`, `log:template:a74d4d35b085`, `log:template:b0050c407330`, `log:template:b0d51430f4f6`, `log:template:b5817707b6af`, `log:template:bf4825e3b3aa`, `log:template:c5fb88a70fe6`, `log:template:c903b1580c37`, `log:template:cddc73e6ce12`, `log:template:d4d75ec135e6`, `log:template:d8d13b373282`, `log:template:dbc2068221c1`, `log:template:de632223ece8`, `log:template:e2ba6e194695`, `log:template:ea6f76fe6100`, `log:template:fcad10148b7d`

### T-new: per sensor x fault class (firing rule, G3 applied; `<mod>:*` = any sensor of the modality, `<mod>:<svc>:*` = any of the service)

| symbol | postures | auth-freeze-effect k/n (FA k/n0) | persistence-crash-effect k/n (FA k/n0) |
|---|---|---|---|
| `log:auth:6c19cf62298a` | full+none+selected | 0/8 (0/9) | 9/9 (0/9) |
| `span:auth:AuthUserActionsRest.isLoggedIn` | full | 2/2 (0/3) | 0/3 (0/3) |
| `span:auth:AuthUserActionsRest.login` | full | 2/2 (0/3) | 0/3 (0/3) |
| `span:auth:BCryptProvider.checkPassword` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:auth:RandomSessionIdGenerator.getSessionId` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:auth:ShaSecurityProvider.blobToString` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:auth:ShaSecurityProvider.getKeyProvider` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:auth:ShaSecurityProvider.getSha512` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:auth:ShaSecurityProvider.secure` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:auth:ShaSecurityProvider.validate` | full | 2/2 (0/3) | 0/3 (0/3) |
| `span:image:DriveStorage.loadData` | full | 1/2 (0/3) | 3/3 (0/3) |
| `span:image:ImageProviderEndpoint.getProductImages` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:persistence:CategoryEndpoint.findEntityById` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:persistence:CategoryEndpoint.listAllEntities` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:persistence:PersistenceCategory.getId` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:persistence:PersistenceProduct.getId` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:persistence:PersistenceUser.getId` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:persistence:ProductEndpoint.countForCategory` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:persistence:ProductEndpoint.findEntityById` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:persistence:ProductEndpoint.listAllForCategory` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:persistence:ProductRepository.getAllEntities` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:persistence:ProductRepository.getProductCount` | full | 0/2 (0/3) | 3/3 (0/3) |
| `span:persistence:UserEndpoint.findById` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:persistence:UserRepository.getUserByName` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:recommender:PopularityBasedRecommender.execute` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:recommender:RecommendEndpoint.recommend` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:recommender:RecommenderSelector.recommendProducts` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:recommender:SlopeOneRecommender.execute` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:webui:CategoryServlet.handleGETRequest` | full | 1/2 (0/3) | 3/3 (0/3) |
| `span:webui:IndexServlet.handleGETRequest` | full | 0/2 (0/3) | 2/3 (0/3) |
| `span:webui:ProductServlet.handleGETRequest` | full | 2/2 (0/3) | 3/3 (0/3) |
| `log:*` | full+none+selected | 0/8 (0/9) | 9/9 (0/9) |
| `span:*` | full | 2/2 (0/3) | 3/3 (0/3) |
| `log:auth:*` | full+none+selected | 0/8 (0/9) | 9/9 (0/9) |
| `span:auth:*` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:image:*` | full | 1/2 (0/3) | 3/3 (0/3) |
| `span:persistence:*` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:recommender:*` | full | 2/2 (0/3) | 3/3 (0/3) |
| `span:webui:*` | full | 2/2 (0/3) | 3/3 (0/3) |

7 symbols with 0 detections and 0 false alarms in every class (0/n, never dropped; denominators per class as above): `span:image:AbstractCache.getEntries`, `span:image:AbstractCache.loadData`, `span:image:ImageProvider.getImageFor`, `span:image:ImageProvider.scaleAndRegisterImg`, `span:image:ImageProviderEndpoint.getWebUIImages`, `span:webui:LoginActionServlet.handlePOSTRequest`, `span:webui:LoginServlet.handleGETRequest`

### T-new: combinations on valid fault cells of posture full (sensors firing in >= 1 episode: 31; triples computed)

| class | n | sensors firing | pairs | redundant (conj = min single) | complementary (union > max single) | pairs with conjunction = n | triples beyond every sub-pair |
|---|---|---|---|---|---|---|---|
| auth-freeze-effect | 2 | 20 | 190 | 190 | 0 | 153 | 0 of 1140 |
| persistence-crash-effect | 3 | 28 | 378 | 378 | 0 | 351 | 0 of 3276 |

### T-new: mutual information I(symbol; class), bits, plug-in (ranking aid, no test)

| symbol | pooled bits (n; class sizes) | per service (bits, n) |
|---|---|---|
| `span:BCryptProvider.checkPassword:missing_expected` | 0.954 (8; {"auth-freeze-effect": 2, "persistence-crash-effect": 3, "no-fault": 3}) | auth 0.954 (8) |
| `span:BCryptProvider.checkPassword:present` | 0.954 (8; {"auth-freeze-effect": 2, "persistence-crash-effect": 3, "no-fault": 3}) | auth 0.954 (8) |
| `span:CategoryEndpoint.findEntityById:missing_expected` | 0.954 (8; {"auth-freeze-effect": 2, "persistence-crash-effect": 3, "no-fault": 3}) | persistence 0.954 (8) |
| `span:CategoryEndpoint.findEntityById:present` | 0.954 (8; {"auth-freeze-effect": 2, "persistence-crash-effect": 3, "no-fault": 3}) | persistence 0.954 (8) |
| `span:CategoryEndpoint.listAllEntities:missing_expected` | 0.954 (8; {"auth-freeze-effect": 2, "persistence-crash-effect": 3, "no-fault": 3}) | persistence 0.954 (8) |
| `span:CategoryEndpoint.listAllEntities:present` | 0.954 (8; {"auth-freeze-effect": 2, "persistence-crash-effect": 3, "no-fault": 3}) | persistence 0.954 (8) |
| `span:CategoryServlet.handleGETRequest:missing_expected` | 0.954 (8; {"auth-freeze-effect": 2, "persistence-crash-effect": 3, "no-fault": 3}) | webui 0.954 (8) |
| `span:CategoryServlet.handleGETRequest:present` | 0.954 (8; {"auth-freeze-effect": 2, "persistence-crash-effect": 3, "no-fault": 3}) | webui 0.954 (8) |
| `span:DriveStorage.loadData:present` | 0.954 (8; {"auth-freeze-effect": 2, "persistence-crash-effect": 3, "no-fault": 3}) | image 0.954 (8) |
| `span:ImageProvider.scaleAndRegisterImg:present` | 0.954 (8; {"auth-freeze-effect": 2, "persistence-crash-effect": 3, "no-fault": 3}) | image 0.954 (8) |
| `span:ImageProviderEndpoint.getProductImages:missing_expected` | 0.954 (8; {"auth-freeze-effect": 2, "persistence-crash-effect": 3, "no-fault": 3}) | image 0.954 (8) |
| `span:ImageProviderEndpoint.getProductImages:present` | 0.954 (8; {"auth-freeze-effect": 2, "persistence-crash-effect": 3, "no-fault": 3}) | image 0.954 (8) |
| `span:LoginServlet.handleGETRequest:present` | 0.954 (8; {"auth-freeze-effect": 2, "persistence-crash-effect": 3, "no-fault": 3}) | webui 0.954 (8) |
| `span:PersistenceCategory.getId:missing_expected` | 0.954 (8; {"auth-freeze-effect": 2, "persistence-crash-effect": 3, "no-fault": 3}) | persistence 0.954 (8) |
| `span:PersistenceCategory.getId:present` | 0.954 (8; {"auth-freeze-effect": 2, "persistence-crash-effect": 3, "no-fault": 3}) | persistence 0.954 (8) |

(top 15 of the ranking; the full ranking is in `tables.md`)
symbols with I = 0 bits pooled: 70 of 137

### T-new: R(p) with G1-G6 (span-exporting episodes)

- episodes: 5; |R| distribution: {"9": 1, "11": 1, "15": 1, "16": 2}; distinct R sets: 4; empty R: 0; G4 metric-without-log: 0
- composition per class: {"auth-freeze-effect": {"span": 2}, "persistence-crash-effect": {"log+span": 3}}
- G2 removed (target-service sensors) per class: {"auth-freeze-effect": 18, "persistence-crash-effect": 36}; G3 removed per class: {"auth-freeze-effect": 0, "persistence-crash-effect": 0}
- max f_all / f_any per k (exact (union enumeration over 4 distinct R sets)): k=1 all 0 any 5 (exact); k=2 all 0 any 5 (exact); k=3 all 0 any 5 (exact); k=4 all 0 any 5 (exact); k=5 all 0 any 5 (exact); k=6 all 0 any 5 (exact); k=7 all 0 any 5 (exact); k=8 all 0 any 5 (exact)
- R+ (G2 off): distinct 4; max f_all per k: k=1 0; k=2 0; k=3 0; k=4 0; k=5 0; k=6 0; k=7 0; k=8 0
- level sets over the catalogue domain: -- (R11)

## Generation T-16

- services: auth, image, persistence, recommender, webui; postures: full, none, selected; span-exporting posture: full; fault classes: auth-freeze-effect, persistence-crash-effect
- episodes per class per posture: {"auth-freeze-effect": {"full": 3, "none": 3, "selected": 3}, "persistence-crash-effect": {"full": 3, "none": 3, "selected": 3}}
- no-fault pseudo units per posture: {"full": 3, "none": 3, "selected": 3}; per class (G-old per-family): {"auth-freeze-effect": 9, "persistence-crash-effect": 9}
- rows excluded: a-p-w 0, invalid 0 (both in the bags, in no table)
- symbols: 138 (log 68, metric 0, span 70); sensors: 38; fault rows whose only log symptom is an exception class (reading R1): 0
- true by construction here: TBC3 (span tables are `full` only); TBC5 (every log FA is 0/n0 and every template is novel by construction); TBC9 (log4j templates are cell-row only); TBC8

### T-16: per symbol x fault class, pooled over postures (span: `full` only) and over services

| symbol | postures | auth-freeze-effect k/n (FA k/n0) | persistence-crash-effect k/n (FA k/n0) |
|---|---|---|---|
| `log:level:warn` | full+none+selected | 0/9 (0/9) | 9/9 (0/9) |
| `log:rate:6c19cf62298a:high` | full+none+selected | 0/9 (0/9) | 8/9 (0/9) |
| `log:template:6c19cf62298a` | full+none+selected | 0/9 (0/9) | 9/9 (0/9) |
| `log:template:novel` | full+none+selected | 0/9 (0/9) | 9/9 (0/9) |
| `span:AbstractCache.getEntries:present` | full | 3/3 (3/3) | 3/3 (3/3) |
| `span:AbstractCache.loadData:present` | full | 3/3 (3/3) | 3/3 (3/3) |
| `span:AuthUserActionsRest.isLoggedIn:missing_expected` | full | 3/3 (0/3) | 0/3 (0/3) |
| `span:AuthUserActionsRest.isLoggedIn:present` | full | 0/3 (3/3) | 3/3 (3/3) |
| `span:AuthUserActionsRest.login:missing_expected` | full | 3/3 (0/3) | 0/3 (0/3) |
| `span:AuthUserActionsRest.login:present` | full | 0/3 (3/3) | 3/3 (3/3) |
| `span:BCryptProvider.checkPassword:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:BCryptProvider.checkPassword:present` | full | 0/3 (3/3) | 0/3 (3/3) |
| `span:CategoryEndpoint.findEntityById:missing_expected` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:CategoryEndpoint.findEntityById:present` | full | 3/3 (3/3) | 0/3 (3/3) |
| `span:CategoryEndpoint.listAllEntities:missing_expected` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:CategoryEndpoint.listAllEntities:present` | full | 3/3 (3/3) | 0/3 (3/3) |
| `span:CategoryServlet.handleGETRequest:latency_high` | full | 2/3 (0/3) | 0/3 (0/3) |
| `span:CategoryServlet.handleGETRequest:missing_expected` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:CategoryServlet.handleGETRequest:present` | full | 3/3 (3/3) | 0/3 (3/3) |
| `span:DriveStorage.loadData:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:DriveStorage.loadData:present` | full | 0/3 (3/3) | 0/3 (3/3) |
| `span:ImageProvider.getImageFor:present` | full | 3/3 (3/3) | 3/3 (3/3) |
| `span:ImageProvider.scaleAndRegisterImg:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:ImageProvider.scaleAndRegisterImg:present` | full | 0/3 (3/3) | 0/3 (3/3) |
| `span:ImageProviderEndpoint.getProductImages:latency_high` | full | 1/3 (0/3) | 0/3 (0/3) |
| `span:ImageProviderEndpoint.getProductImages:missing_expected` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:ImageProviderEndpoint.getProductImages:present` | full | 3/3 (3/3) | 0/3 (3/3) |
| `span:ImageProviderEndpoint.getWebUIImages:present` | full | 3/3 (3/3) | 3/3 (3/3) |
| `span:IndexServlet.handleGETRequest:present` | full | 3/3 (3/3) | 3/3 (3/3) |
| `span:LoginActionServlet.handlePOSTRequest:present` | full | 3/3 (3/3) | 3/3 (3/3) |
| `span:LoginServlet.handleGETRequest:present` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:PersistenceCategory.getId:missing_expected` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:PersistenceCategory.getId:present` | full | 3/3 (3/3) | 0/3 (3/3) |
| `span:PersistenceProduct.getId:missing_expected` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:PersistenceProduct.getId:present` | full | 3/3 (3/3) | 0/3 (3/3) |
| `span:PersistenceUser.getId:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:PersistenceUser.getId:present` | full | 0/3 (3/3) | 0/3 (3/3) |
| `span:PopularityBasedRecommender.execute:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:PopularityBasedRecommender.execute:present` | full | 0/3 (3/3) | 0/3 (3/3) |
| `span:ProductEndpoint.countForCategory:missing_expected` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:ProductEndpoint.countForCategory:present` | full | 3/3 (3/3) | 0/3 (3/3) |
| `span:ProductEndpoint.findEntityById:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:ProductEndpoint.findEntityById:present` | full | 0/3 (3/3) | 0/3 (3/3) |
| `span:ProductEndpoint.listAllForCategory:missing_expected` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:ProductEndpoint.listAllForCategory:present` | full | 3/3 (3/3) | 0/3 (3/3) |
| `span:ProductRepository.getAllEntities:missing_expected` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:ProductRepository.getAllEntities:present` | full | 3/3 (3/3) | 0/3 (3/3) |
| `span:ProductRepository.getProductCount:missing_expected` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:ProductRepository.getProductCount:present` | full | 3/3 (3/3) | 0/3 (3/3) |
| `span:ProductServlet.handleGETRequest:latency_high` | full | 2/3 (0/3) | 0/3 (0/3) |
| `span:ProductServlet.handleGETRequest:missing_expected` | full | 1/3 (0/3) | 3/3 (0/3) |
| `span:ProductServlet.handleGETRequest:present` | full | 2/3 (3/3) | 0/3 (3/3) |
| `span:RandomSessionIdGenerator.getSessionId:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:RandomSessionIdGenerator.getSessionId:present` | full | 0/3 (3/3) | 0/3 (3/3) |
| `span:RecommendEndpoint.recommend:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:RecommendEndpoint.recommend:present` | full | 0/3 (3/3) | 0/3 (3/3) |
| `span:RecommenderSelector.recommendProducts:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:RecommenderSelector.recommendProducts:present` | full | 0/3 (3/3) | 0/3 (3/3) |
| `span:ShaSecurityProvider.blobToString:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:ShaSecurityProvider.blobToString:present` | full | 0/3 (3/3) | 0/3 (3/3) |
| `span:ShaSecurityProvider.getKeyProvider:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:ShaSecurityProvider.getKeyProvider:present` | full | 0/3 (3/3) | 0/3 (3/3) |
| `span:ShaSecurityProvider.getSha512:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:ShaSecurityProvider.getSha512:present` | full | 0/3 (3/3) | 0/3 (3/3) |
| `span:ShaSecurityProvider.secure:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:ShaSecurityProvider.secure:present` | full | 0/3 (3/3) | 0/3 (3/3) |
| `span:ShaSecurityProvider.validate:missing_expected` | full | 3/3 (0/3) | 0/3 (0/3) |
| `span:ShaSecurityProvider.validate:present` | full | 0/3 (3/3) | 3/3 (3/3) |
| `span:SlopeOneRecommender.execute:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:SlopeOneRecommender.execute:present` | full | 0/3 (3/3) | 0/3 (3/3) |
| `span:UserEndpoint.findById:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:UserEndpoint.findById:present` | full | 0/3 (3/3) | 0/3 (3/3) |
| `span:UserRepository.getUserByName:missing_expected` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:UserRepository.getUserByName:present` | full | 0/3 (3/3) | 0/3 (3/3) |

64 symbols with 0 detections and 0 false alarms in every class (0/n, never dropped; denominators per class as above): `log:exception:ClientException`, `log:exception:ProcessingException`, `log:exception:StringIndexOutOfBoundsException`, `log:exception:UnresolvedAddressException`, `log:level:error`, `log:rate:c5fb88a70fe6:high`, `log:rate:d4d75ec135e6:high`, `log:template:0098f0714240`, `log:template:059f77b5fee4`, `log:template:0788a45dbb86`, `log:template:0ae227c4f15d`, `log:template:13e7be34fb70`, `log:template:147f864363b1`, `log:template:16e888bf8922`, `log:template:16f327e6bd4d`, `log:template:25e233b98160`, `log:template:2d7f16630b87`, `log:template:2ff20a342a41`, `log:template:319b41b82d9b`, `log:template:3219d9dbbaed`, `log:template:35563463c928`, `log:template:35873ee1cc7e`, `log:template:3917ffeac5ec`, `log:template:3b1fa69c3451`, `log:template:407989c51698`, `log:template:4a79ac521b28`, `log:template:4de8468724c7`, `log:template:52a075c95ff9`, `log:template:546670de7509`, `log:template:56bcc1a07d39`, `log:template:56c309f6427c`, `log:template:61451078c684`, `log:template:66d09055f528`, `log:template:6e7a7f83a9e6`, `log:template:7197cbb5d81b`, `log:template:72ae3fa150b5`, `log:template:798861287e32`, `log:template:811e1f658b4b`, `log:template:8733ab2f4543`, `log:template:87614f556af3`, `log:template:8b277994d6dd`, `log:template:8eb94ac35bf9`, `log:template:955560e889b3`, `log:template:96ea0f608ef2`, `log:template:96eef0c939e4`, `log:template:9c6795a8c551`, `log:template:a0105883ccdd`, `log:template:a07c7bcc6c3d`, `log:template:a59061884c18`, `log:template:a74d4d35b085`, `log:template:b0050c407330`, `log:template:b0d51430f4f6`, `log:template:b5817707b6af`, `log:template:bf4825e3b3aa`, `log:template:c5fb88a70fe6`, `log:template:c903b1580c37`, `log:template:cddc73e6ce12`, `log:template:d4d75ec135e6`, `log:template:d8d13b373282`, `log:template:dbc2068221c1`, `log:template:de632223ece8`, `log:template:e2ba6e194695`, `log:template:ea6f76fe6100`, `log:template:fcad10148b7d`

### T-16: per sensor x fault class (firing rule, G3 applied; `<mod>:*` = any sensor of the modality, `<mod>:<svc>:*` = any of the service)

| symbol | postures | auth-freeze-effect k/n (FA k/n0) | persistence-crash-effect k/n (FA k/n0) |
|---|---|---|---|
| `log:auth:6c19cf62298a` | full+none+selected | 0/9 (0/9) | 9/9 (0/9) |
| `span:auth:AuthUserActionsRest.isLoggedIn` | full | 3/3 (0/3) | 0/3 (0/3) |
| `span:auth:AuthUserActionsRest.login` | full | 3/3 (0/3) | 0/3 (0/3) |
| `span:auth:BCryptProvider.checkPassword` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:auth:RandomSessionIdGenerator.getSessionId` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:auth:ShaSecurityProvider.blobToString` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:auth:ShaSecurityProvider.getKeyProvider` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:auth:ShaSecurityProvider.getSha512` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:auth:ShaSecurityProvider.secure` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:auth:ShaSecurityProvider.validate` | full | 3/3 (0/3) | 0/3 (0/3) |
| `span:image:DriveStorage.loadData` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:image:ImageProvider.scaleAndRegisterImg` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:image:ImageProviderEndpoint.getProductImages` | full | 1/3 (0/3) | 3/3 (0/3) |
| `span:persistence:CategoryEndpoint.findEntityById` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:persistence:CategoryEndpoint.listAllEntities` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:persistence:PersistenceCategory.getId` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:persistence:PersistenceProduct.getId` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:persistence:PersistenceUser.getId` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:persistence:ProductEndpoint.countForCategory` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:persistence:ProductEndpoint.findEntityById` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:persistence:ProductEndpoint.listAllForCategory` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:persistence:ProductRepository.getAllEntities` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:persistence:ProductRepository.getProductCount` | full | 0/3 (0/3) | 3/3 (0/3) |
| `span:persistence:UserEndpoint.findById` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:persistence:UserRepository.getUserByName` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:recommender:PopularityBasedRecommender.execute` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:recommender:RecommendEndpoint.recommend` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:recommender:RecommenderSelector.recommendProducts` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:recommender:SlopeOneRecommender.execute` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:webui:CategoryServlet.handleGETRequest` | full | 2/3 (0/3) | 3/3 (0/3) |
| `span:webui:ProductServlet.handleGETRequest` | full | 3/3 (0/3) | 3/3 (0/3) |
| `log:*` | full+none+selected | 0/9 (0/9) | 9/9 (0/9) |
| `span:*` | full | 3/3 (0/3) | 3/3 (0/3) |
| `log:auth:*` | full+none+selected | 0/9 (0/9) | 9/9 (0/9) |
| `span:auth:*` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:image:*` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:persistence:*` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:recommender:*` | full | 3/3 (0/3) | 3/3 (0/3) |
| `span:webui:*` | full | 3/3 (0/3) | 3/3 (0/3) |

7 symbols with 0 detections and 0 false alarms in every class (0/n, never dropped; denominators per class as above): `span:image:AbstractCache.getEntries`, `span:image:AbstractCache.loadData`, `span:image:ImageProvider.getImageFor`, `span:image:ImageProviderEndpoint.getWebUIImages`, `span:webui:IndexServlet.handleGETRequest`, `span:webui:LoginActionServlet.handlePOSTRequest`, `span:webui:LoginServlet.handleGETRequest`

### T-16: combinations on valid fault cells of posture full (sensors firing in >= 1 episode: 31; triples computed)

| class | n | sensors firing | pairs | redundant (conj = min single) | complementary (union > max single) | pairs with conjunction = n | triples beyond every sub-pair |
|---|---|---|---|---|---|---|---|
| auth-freeze-effect | 3 | 22 | 231 | 231 | 0 | 190 | 0 of 1540 |
| persistence-crash-effect | 3 | 28 | 378 | 378 | 0 | 378 | 0 of 3276 |

### T-16: mutual information I(symbol; class), bits, plug-in (ranking aid, no test)

| symbol | pooled bits (n; class sizes) | per service (bits, n) |
|---|---|---|
| `log:level:warn` | 0.918 (27; {"auth-freeze-effect": 9, "persistence-crash-effect": 9, "no-fault": 9}) | auth 0.918 (27) |
| `log:template:6c19cf62298a` | 0.918 (27; {"auth-freeze-effect": 9, "persistence-crash-effect": 9, "no-fault": 9}) | auth 0.918 (27) |
| `log:template:novel` | 0.918 (27; {"auth-freeze-effect": 9, "persistence-crash-effect": 9, "no-fault": 9}) | auth 0.918 (27) |
| `span:AuthUserActionsRest.isLoggedIn:missing_expected` | 0.918 (9; {"auth-freeze-effect": 3, "persistence-crash-effect": 3, "no-fault": 3}) | auth 0.918 (9) |
| `span:AuthUserActionsRest.isLoggedIn:present` | 0.918 (9; {"auth-freeze-effect": 3, "persistence-crash-effect": 3, "no-fault": 3}) | auth 0.918 (9) |
| `span:AuthUserActionsRest.login:missing_expected` | 0.918 (9; {"auth-freeze-effect": 3, "persistence-crash-effect": 3, "no-fault": 3}) | auth 0.918 (9) |
| `span:AuthUserActionsRest.login:present` | 0.918 (9; {"auth-freeze-effect": 3, "persistence-crash-effect": 3, "no-fault": 3}) | auth 0.918 (9) |
| `span:BCryptProvider.checkPassword:missing_expected` | 0.918 (9; {"auth-freeze-effect": 3, "persistence-crash-effect": 3, "no-fault": 3}) | auth 0.918 (9) |
| `span:BCryptProvider.checkPassword:present` | 0.918 (9; {"auth-freeze-effect": 3, "persistence-crash-effect": 3, "no-fault": 3}) | auth 0.918 (9) |
| `span:CategoryEndpoint.findEntityById:missing_expected` | 0.918 (9; {"auth-freeze-effect": 3, "persistence-crash-effect": 3, "no-fault": 3}) | persistence 0.918 (9) |
| `span:CategoryEndpoint.findEntityById:present` | 0.918 (9; {"auth-freeze-effect": 3, "persistence-crash-effect": 3, "no-fault": 3}) | persistence 0.918 (9) |
| `span:CategoryEndpoint.listAllEntities:missing_expected` | 0.918 (9; {"auth-freeze-effect": 3, "persistence-crash-effect": 3, "no-fault": 3}) | persistence 0.918 (9) |
| `span:CategoryEndpoint.listAllEntities:present` | 0.918 (9; {"auth-freeze-effect": 3, "persistence-crash-effect": 3, "no-fault": 3}) | persistence 0.918 (9) |
| `span:CategoryServlet.handleGETRequest:missing_expected` | 0.918 (9; {"auth-freeze-effect": 3, "persistence-crash-effect": 3, "no-fault": 3}) | webui 0.918 (9) |
| `span:CategoryServlet.handleGETRequest:present` | 0.918 (9; {"auth-freeze-effect": 3, "persistence-crash-effect": 3, "no-fault": 3}) | webui 0.918 (9) |

(top 15 of the ranking; the full ranking is in `tables.md`)
symbols with I = 0 bits pooled: 70 of 138

### T-16: R(p) with G1-G6 (span-exporting episodes)

- episodes: 6; |R| distribution: {"11": 1, "12": 1, "13": 1, "16": 3}; distinct R sets: 4; empty R: 0; G4 metric-without-log: 0
- composition per class: {"auth-freeze-effect": {"span": 3}, "persistence-crash-effect": {"log+span": 3}}
- G2 removed (target-service sensors) per class: {"auth-freeze-effect": 27, "persistence-crash-effect": 36}; G3 removed per class: {"auth-freeze-effect": 0, "persistence-crash-effect": 0}
- max f_all / f_any per k (exact (union enumeration over 4 distinct R sets)): k=1 all 0 any 6 (exact); k=2 all 0 any 6 (exact); k=3 all 0 any 6 (exact); k=4 all 0 any 6 (exact); k=5 all 0 any 6 (exact); k=6 all 0 any 6 (exact); k=7 all 0 any 6 (exact); k=8 all 0 any 6 (exact)
- R+ (G2 off): distinct 4; max f_all per k: k=1 0; k=2 0; k=3 0; k=4 0; k=5 0; k=6 0; k=7 0; k=8 0
- level sets over the catalogue domain: -- (R11)

## Generation G-old

- services: auth, db, image, persistence, recommender, registry, webui; postures: kieker-native; span-exporting posture: kieker-native; fault classes: auth_freeze, db_crash, image_crash, image_loss, orderitems_timeout, persistence_crash, persistence_latency, recommender_crash, recommender_exception, recommender_latency, registry_restart
- episodes per class per posture: {"auth_freeze": {"kieker-native": 10}, "db_crash": {"kieker-native": 10}, "image_crash": {"kieker-native": 10}, "image_loss": {"kieker-native": 10}, "orderitems_timeout": {"kieker-native": 10}, "persistence_crash": {"kieker-native": 10}, "persistence_latency": {"kieker-native": 10}, "recommender_crash": {"kieker-native": 10}, "recommender_exception": {"kieker-native": 10}, "recommender_latency": {"kieker-native": 10}, "registry_restart": {"kieker-native": 10}}
- no-fault pseudo units per posture: {"kieker-native": 330}; per class (G-old per-family): {"auth_freeze": 30, "db_crash": 30, "image_crash": 30, "image_loss": 30, "orderitems_timeout": 30, "persistence_crash": 30, "persistence_latency": 30, "recommender_crash": 30, "recommender_exception": 30, "recommender_latency": 30, "registry_restart": 30}
- rows excluded: a-p-w 0, invalid 0 (both in the bags, in no table)
- symbols: 283 (log 221, metric 7, span 55); sensors: 69; fault rows whose only log symptom is an exception class (reading R1): 11
- true by construction here: TBC1 (auth_freeze target), TBC2 (crash families' restart templates and exception classes)

### G-old: per symbol x fault class, pooled over postures (span: `kieker-native` only) and over services

| symbol | postures | auth_freeze k/n (FA k/n0) | db_crash k/n (FA k/n0) | image_crash k/n (FA k/n0) | image_loss k/n (FA k/n0) | orderitems_timeout k/n (FA k/n0) | persistence_crash k/n (FA k/n0) | persistence_latency k/n (FA k/n0) | recommender_crash k/n (FA k/n0) | recommender_exception k/n (FA k/n0) | recommender_latency k/n (FA k/n0) | registry_restart k/n (FA k/n0) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `log:exception:ClientException` | kieker-native | 9/10 (27/30) | 9/10 (27/30) | 9/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) |
| `log:exception:ConnectException` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 3/10 (0/30) |
| `log:exception:ProcessingException` | kieker-native | 9/10 (27/30) | 9/10 (27/30) | 9/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 10/10 (27/30) |
| `log:exception:SocketTimeoutException` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) |
| `log:exception:TimeoutException` | kieker-native | 9/10 (27/30) | 9/10 (27/30) | 9/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) |
| `log:exception:UnknownHostException` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) |
| `log:exception:UnresolvedAddressException` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:level:warn` | kieker-native | 10/10 (18/30) | 9/10 (18/30) | 10/10 (18/30) | 10/10 (18/30) | 0/10 (18/30) | 10/10 (18/30) | 0/10 (18/30) | 10/10 (18/30) | 0/10 (18/30) | 0/10 (18/30) | 0/10 (18/30) |
| `log:rate:a273f9c494c5:high` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:rate:a7ff7976a62f:high` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 2/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:rate:d4bab19c5a03:high` | kieker-native | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:rate:d4d75ec135e6:high` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) |
| `log:rate:e2bf3a4aa0ce:high` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:0e5686851972` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:0fa0e0318a07` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:1b6e1f5f63fc` | kieker-native | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:3746091e2305` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:5cbcfab6ff10` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:5ddf0cdb464c` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:6f2fdc7ec786` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:7450b9d707e0` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:7539c70752c0` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:7b72c11b2351` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:91b7cf88164f` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:93f7a39b1898` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:a273f9c494c5` | kieker-native | 0/10 (18/30) | 9/10 (18/30) | 9/10 (18/30) | 0/10 (18/30) | 0/10 (18/30) | 0/10 (18/30) | 0/10 (18/30) | 0/10 (18/30) | 0/10 (18/30) | 0/10 (18/30) | 0/10 (18/30) |
| `log:template:a74e9a3a9aed` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:a7ff7976a62f` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:c2797874a226` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:d4bab19c5a03` | kieker-native | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:d4d75ec135e6` | kieker-native | 10/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) |
| `log:template:e2bf3a4aa0ce` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:fa49e8ca36da` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:template:novel` | kieker-native | 10/10 (0/30) | 10/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `metric:cpu:plateau_up` | kieker-native | 0/10 (0/30) | 1/10 (0/30) | 8/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `metric:cpu:spike_down` | kieker-native | 1/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 2/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `metric:cpu:spike_up` | kieker-native | 9/10 (25/30) | 10/10 (26/30) | 10/10 (27/30) | 8/10 (25/30) | 10/10 (25/30) | 9/10 (27/30) | 10/10 (25/30) | 10/10 (27/30) | 9/10 (25/30) | 10/10 (25/30) | 10/10 (27/30) |
| `metric:mem:plateau_down` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 1/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `metric:mem:plateau_up` | kieker-native | 1/10 (14/30) | 5/10 (14/30) | 3/10 (17/30) | 1/10 (14/30) | 1/10 (14/30) | 3/10 (17/30) | 1/10 (14/30) | 1/10 (17/30) | 1/10 (14/30) | 6/10 (14/30) | 2/10 (17/30) |
| `metric:mem:spike_down` | kieker-native | 0/10 (1/30) | 9/10 (1/30) | 10/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 10/10 (1/30) | 0/10 (1/30) | 10/10 (1/30) | 1/10 (1/30) | 0/10 (1/30) | 10/10 (1/30) |
| `metric:mem:spike_up` | kieker-native | 4/10 (22/30) | 7/10 (23/30) | 8/10 (23/30) | 1/10 (22/30) | 2/10 (22/30) | 3/10 (23/30) | 2/10 (22/30) | 3/10 (23/30) | 2/10 (22/30) | 7/10 (22/30) | 4/10 (23/30) |
| `span:AbstractCache.getEntries:missing_expected` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) |
| `span:AbstractCache.loadData:missing_expected` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) |
| `span:CategoryEndpoint.findEntityById:missing_expected` | kieker-native | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) |
| `span:CategoryEndpoint.findEntityById:present` | kieker-native | 0/10 (8/30) | 0/10 (8/30) | 9/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) |
| `span:CategoryEndpoint.listAllEntities:latency_high` | kieker-native | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) |
| `span:CategoryEndpoint.listAllEntities:missing_expected` | kieker-native | 0/10 (7/30) | 0/10 (7/30) | 0/10 (6/30) | 0/10 (7/30) | 0/10 (7/30) | 0/10 (6/30) | 0/10 (7/30) | 0/10 (6/30) | 0/10 (7/30) | 0/10 (7/30) | 0/10 (6/30) |
| `span:CategoryEndpoint.listAllEntities:present` | kieker-native | 9/10 (21/30) | 9/10 (21/30) | 9/10 (22/30) | 0/10 (21/30) | 0/10 (21/30) | 0/10 (22/30) | 0/10 (21/30) | 0/10 (22/30) | 0/10 (21/30) | 0/10 (21/30) | 0/10 (22/30) |
| `span:ImageProvider.getImageFor:missing_expected` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) |
| `span:ImageProviderEndpoint.getWebUIImages:missing_expected` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) |
| `span:OrderEndpoint.createEntity:missing_expected` | kieker-native | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) |
| `span:OrderEndpoint.createEntity:present` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `span:OrderEndpoint.listAllEntities:missing_expected` | kieker-native | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) |
| `span:OrderItemEndpoint.createEntity:missing_expected` | kieker-native | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) |
| `span:OrderItemEndpoint.createEntity:present` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `span:OrderItemEndpoint.listAllEntities:missing_expected` | kieker-native | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) |
| `span:OrderItemRepository.createEntity:missing_expected` | kieker-native | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) |
| `span:OrderItemRepository.createEntity:present` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `span:OrderRepository.createEntity:missing_expected` | kieker-native | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) |
| `span:OrderRepository.createEntity:present` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `span:OrderRepository.updateEntity:missing_expected` | kieker-native | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) |
| `span:PersistenceCategory.getId:missing_expected` | kieker-native | 0/10 (1/30) | 9/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) |
| `span:PersistenceCategory.getId:present` | kieker-native | 9/10 (27/30) | 0/10 (27/30) | 9/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) | 0/10 (27/30) |
| `span:PersistenceOrder.getId:missing_expected` | kieker-native | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) |
| `span:PersistenceOrder.getId:present` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `span:PersistenceOrder.setUser:missing_expected` | kieker-native | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) |
| `span:PersistenceOrder.setUser:present` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `span:PersistenceOrderItem.getId:missing_expected` | kieker-native | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) |
| `span:PersistenceOrderItem.getId:present` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `span:PersistenceOrderItem.getOrder:missing_expected` | kieker-native | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) |
| `span:PersistenceOrderItem.setOrder:missing_expected` | kieker-native | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) |
| `span:PersistenceOrderItem.setOrder:present` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `span:PersistenceOrderItem.setProduct:missing_expected` | kieker-native | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) |
| `span:PersistenceOrderItem.setProduct:present` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `span:PersistenceProduct.getId:missing_expected` | kieker-native | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) |
| `span:PersistenceProduct.getId:present` | kieker-native | 0/10 (9/30) | 0/10 (9/30) | 9/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) |
| `span:PersistenceProduct.setCategory:missing_expected` | kieker-native | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) |
| `span:PersistenceUser.getId:missing_expected` | kieker-native | 9/10 (28/30) | 9/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (28/30) | 0/10 (10/30) |
| `span:PersistenceUser.getId:present` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (18/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (18/30) | 0/10 (0/30) | 0/10 (18/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (18/30) |
| `span:ProductEndpoint.countForCategory:latency_high` | kieker-native | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) |
| `span:ProductEndpoint.countForCategory:missing_expected` | kieker-native | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) |
| `span:ProductEndpoint.countForCategory:present` | kieker-native | 0/10 (8/30) | 0/10 (8/30) | 9/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) |
| `span:ProductEndpoint.findEntityById:present` | kieker-native | 0/10 (9/30) | 0/10 (9/30) | 9/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) |
| `span:ProductEndpoint.listAllForCategory:missing_expected` | kieker-native | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) |
| `span:ProductEndpoint.listAllForCategory:present` | kieker-native | 0/10 (8/30) | 0/10 (8/30) | 9/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) |
| `span:ProductRepository.createEntity:missing_expected` | kieker-native | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) |
| `span:ProductRepository.getAllEntities:missing_expected` | kieker-native | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) |
| `span:ProductRepository.getAllEntities:present` | kieker-native | 0/10 (8/30) | 0/10 (8/30) | 9/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) |
| `span:ProductRepository.getProductCount:latency_high` | kieker-native | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) |
| `span:ProductRepository.getProductCount:missing_expected` | kieker-native | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) |
| `span:ProductRepository.getProductCount:present` | kieker-native | 0/10 (8/30) | 0/10 (8/30) | 9/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (8/30) |
| `span:UserEndpoint.findById:missing_expected` | kieker-native | 9/10 (28/30) | 2/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (28/30) | 0/10 (10/30) |
| `span:UserEndpoint.findById:present` | kieker-native | 0/10 (0/30) | 7/10 (0/30) | 9/10 (18/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (18/30) | 0/10 (0/30) | 0/10 (18/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (18/30) |
| `span:UserRepository.createEntity:missing_expected` | kieker-native | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) |
| `span:UserRepository.getUserByName:missing_expected` | kieker-native | 9/10 (28/30) | 2/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (28/30) | 0/10 (10/30) |
| `span:UserRepository.getUserByName:present` | kieker-native | 0/10 (0/30) | 7/10 (0/30) | 9/10 (18/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (18/30) | 0/10 (0/30) | 0/10 (18/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (18/30) |

187 symbols with 0 detections and 0 false alarms in every class (0/n, never dropped; denominators per class as above): `log:exception:InvocationTargetException`, `log:exception:NullPointerException`, `log:rate:021a8aa8313d:high`, `log:rate:0385d1e8a237:high`, `log:rate:108f20ca5942:high`, `log:rate:174c232a6df8:high`, `log:rate:274a9cc10ee1:high`, `log:rate:2e80f08bc40d:high`, `log:rate:31f42b2e2545:high`, `log:rate:3af9d4450cd5:high`, `log:rate:3d57491a794a:high`, `log:rate:49ff16437282:high`, `log:rate:575d3d78cbc5:high`, `log:rate:5ddf0cdb464c:high`, `log:rate:6d23b0131e22:high`, `log:rate:71ec4ccbf8cc:high`, `log:rate:75f1f3b25cc3:high`, `log:rate:807480e1893d:high`, `log:rate:8d3268564c27:high`, `log:rate:90ea341a44f3:high`, `log:rate:a6f638d3b44a:high`, `log:rate:a9f80d2730ab:high`, `log:rate:b4f0dde41ef9:high`, `log:rate:b5dc07bc654d:high`, `log:rate:b7e13e3480cb:high`, `log:rate:c11fbd838212:high`, `log:rate:c4c6c64833dc:high`, `log:rate:c58eeeaa6dcb:high`, `log:rate:c5fb88a70fe6:high`, `log:rate:cbfacd345c37:high`, `log:rate:ccb9e2917bc9:high`, `log:rate:d019021d1533:high`, `log:rate:d40e3c335c8d:high`, `log:rate:d9046b197c9a:high`, `log:rate:e47383689b0d:high`, `log:rate:e83a88582757:high`, `log:template:0098f0714240`, `log:template:021a8aa8313d`, `log:template:02c96b0ed9ed`, `log:template:0385d1e8a237`, `log:template:059f77b5fee4`, `log:template:05f1534577c8`, `log:template:0604d48d1b31`, `log:template:0788a45dbb86`, `log:template:0977fbdd24cf`, `log:template:0ae227c4f15d`, `log:template:0e25e6b9bdcc`, `log:template:108f20ca5942`, `log:template:121b08a570d0`, `log:template:13e7be34fb70`, `log:template:16e888bf8922`, `log:template:16f327e6bd4d`, `log:template:172817f680e0`, `log:template:174c232a6df8`, `log:template:187b60c19b14`, `log:template:274a9cc10ee1`, `log:template:2d7f16630b87`, `log:template:2e660505e3e7`, `log:template:2e80f08bc40d`, `log:template:2ff20a342a41`, `log:template:319b41b82d9b`, `log:template:31f42b2e2545`, `log:template:3219d9dbbaed`, `log:template:33eb96d5e2a8`, `log:template:35563463c928`, `log:template:35873ee1cc7e`, `log:template:36e9c777d081`, `log:template:387cdf52c159`, `log:template:3917ffeac5ec`, `log:template:3af9d4450cd5`, `log:template:3b1fa69c3451`, `log:template:3cb2f50dac16`, `log:template:3d57491a794a`, `log:template:3f00555a765d`, `log:template:407989c51698`, `log:template:41fa6b24cf64`, `log:template:477fab032a80`, `log:template:49ff16437282`, `log:template:4a79ac521b28`, `log:template:4a84f564be33`, `log:template:4c3e66422a15`, `log:template:4de8468724c7`, `log:template:4f5268078aa8`, `log:template:4f5565156d76`, `log:template:51d9c8f8ecc0`, `log:template:52a075c95ff9`, `log:template:53a8051ea582`, `log:template:546670de7509`, `log:template:56bcc1a07d39`, `log:template:56c309f6427c`, `log:template:56d7416611a3`, `log:template:575d3d78cbc5`, `log:template:61451078c684`, `log:template:6461680726da`, `log:template:66d09055f528`, `log:template:6d23b0131e22`, `log:template:6d28533dbce5`, `log:template:6e7a7f83a9e6`, `log:template:6f050226b2ee`, `log:template:7197cbb5d81b`, `log:template:71ec4ccbf8cc`, `log:template:72ae3fa150b5`, `log:template:7568b9fca9ad`, `log:template:75f1f3b25cc3`, `log:template:769ee6e16eae`, `log:template:7877eab35e98`, `log:template:798861287e32`, `log:template:7b327c4594ff`, `log:template:807480e1893d`, `log:template:811e1f658b4b`, `log:template:815c7f2d4034`, `log:template:854718040dc1`, `log:template:85ec951231f8`, `log:template:8733ab2f4543`, `log:template:87614f556af3`, `log:template:8a7a034b37fb`, `log:template:8b277994d6dd`, `log:template:8d3268564c27`, `log:template:8ddb5025ba7f`, `log:template:8eb94ac35bf9`, `log:template:90ea341a44f3`, `log:template:928966ec6375`, `log:template:932b14674732`, `log:template:955560e889b3`, `log:template:96ea0f608ef2`, `log:template:96eef0c939e4`, `log:template:9c216e86cbe0`, `log:template:9c6795a8c551`, `log:template:9e8e1facfd8b`, `log:template:a0105883ccdd`, `log:template:a07c7bcc6c3d`, `log:template:a27a60232a9b`, `log:template:a334dde6539e`, `log:template:a3c65268469c`, `log:template:a59061884c18`, `log:template:a6f638d3b44a`, `log:template:a74d4d35b085`, `log:template:a9f80d2730ab`, `log:template:aa34b2496579`, `log:template:b0050c407330`, `log:template:b04ab1d383f9`, `log:template:b08a8924253e`, `log:template:b0d51430f4f6`, `log:template:b20ccf8cc8fe`, `log:template:b4f0dde41ef9`, `log:template:b5817707b6af`, `log:template:b5dc07bc654d`, `log:template:b7e13e3480cb`, `log:template:bcfefc9bed93`, `log:template:bf4825e3b3aa`, `log:template:c11fbd838212`, `log:template:c4c6c64833dc`, `log:template:c51ed5649ba1`, `log:template:c58eeeaa6dcb`, `log:template:c5fb88a70fe6`, `log:template:c903b1580c37`, `log:template:c99c0fd0ffe1`, `log:template:cb2c391e378a`, `log:template:cbfacd345c37`, `log:template:ccb9e2917bc9`, `log:template:cddc73e6ce12`, `log:template:cfd4612a22e5`, `log:template:d019021d1533`, `log:template:d0fdd311d3b7`, `log:template:d18ec6c972b3`, `log:template:d40e3c335c8d`, `log:template:d5ddda374d8f`, `log:template:d62043f9dd8d`, `log:template:d8d13b373282`, `log:template:d9046b197c9a`, `log:template:dbc2068221c1`, `log:template:dd3aae02667f`, `log:template:de632223ece8`, `log:template:e0b8255b61ec`, `log:template:e2ba6e194695`, `log:template:e47383689b0d`, `log:template:e7a070876136`, `log:template:e83a88582757`, `log:template:e97615b92477`, `log:template:e9d47a440c34`, `log:template:ea6f76fe6100`, `log:template:ece032577585`, `log:template:ee1b103359ab`, `log:template:eef2fcd01823`, `log:template:f264f62c3cac`, `log:template:fbe94e29d596`, `log:template:fcad10148b7d`

### G-old: per sensor x fault class (firing rule, G3 applied; `<mod>:*` = any sensor of the modality, `<mod>:<svc>:*` = any of the service)

| symbol | postures | auth_freeze k/n (FA k/n0) | db_crash k/n (FA k/n0) | image_crash k/n (FA k/n0) | image_loss k/n (FA k/n0) | orderitems_timeout k/n (FA k/n0) | persistence_crash k/n (FA k/n0) | persistence_latency k/n (FA k/n0) | recommender_crash k/n (FA k/n0) | recommender_exception k/n (FA k/n0) | recommender_latency k/n (FA k/n0) | registry_restart k/n (FA k/n0) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `log:auth:d4d75ec135e6` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) |
| `log:db:0e5686851972` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:db:0fa0e0318a07` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:db:5cbcfab6ff10` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:db:5ddf0cdb464c` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:db:6f2fdc7ec786` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:db:7539c70752c0` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:db:7b72c11b2351` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:db:91b7cf88164f` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:db:93f7a39b1898` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:db:a74e9a3a9aed` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:db:a7ff7976a62f` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:db:fa49e8ca36da` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:image:d4d75ec135e6` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) |
| `log:recommender:d4d75ec135e6` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) |
| `log:registry:1b6e1f5f63fc` | kieker-native | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:registry:3746091e2305` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:registry:7450b9d707e0` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:registry:c2797874a226` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:webui:a273f9c494c5` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:webui:d4bab19c5a03` | kieker-native | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:webui:d4d75ec135e6` | kieker-native | 10/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) |
| `log:webui:e2bf3a4aa0ce` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `metric:auth:cpu` | kieker-native | 0/10 (0/30) | 1/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `metric:auth:mem` | kieker-native | 0/10 (1/30) | 3/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) |
| `metric:db:mem` | kieker-native | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `metric:image:mem` | kieker-native | 0/10 (0/30) | 1/10 (0/30) | 10/10 (1/30) | 1/10 (0/30) | 0/10 (0/30) | 2/10 (1/30) | 1/10 (0/30) | 0/10 (1/30) | 0/10 (0/30) | 0/10 (0/30) | 1/10 (1/30) |
| `metric:persistence:cpu` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 5/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `metric:persistence:mem` | kieker-native | 1/10 (0/30) | 1/10 (0/30) | 8/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 1/10 (0/30) | 2/10 (0/30) | 1/10 (0/30) | 0/10 (0/30) | 1/10 (0/30) |
| `metric:recommender:cpu` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 1/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `metric:recommender:mem` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `metric:registry:cpu` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 1/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `metric:registry:mem` | kieker-native | 0/10 (1/30) | 1/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 1/10 (1/30) | 0/10 (1/30) | 10/10 (1/30) |
| `metric:webui:cpu` | kieker-native | 1/10 (0/30) | 0/10 (0/30) | 5/10 (0/30) | 0/10 (0/30) | 2/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `span:image:AbstractCache.getEntries` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) |
| `span:image:AbstractCache.loadData` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) |
| `span:image:ImageProvider.getImageFor` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) |
| `span:image:ImageProviderEndpoint.getWebUIImages` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) |
| `span:persistence:CategoryEndpoint.findEntityById` | kieker-native | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) |
| `span:persistence:CategoryEndpoint.listAllEntities` | kieker-native | 0/10 (8/30) | 0/10 (8/30) | 0/10 (7/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (7/30) | 0/10 (8/30) | 0/10 (7/30) | 0/10 (8/30) | 0/10 (8/30) | 0/10 (7/30) |
| `span:persistence:OrderEndpoint.createEntity` | kieker-native | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) |
| `span:persistence:OrderEndpoint.listAllEntities` | kieker-native | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) |
| `span:persistence:OrderItemEndpoint.createEntity` | kieker-native | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) | 0/10 (9/30) |
| `span:persistence:OrderItemEndpoint.listAllEntities` | kieker-native | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) |
| `span:persistence:OrderItemRepository.createEntity` | kieker-native | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) |
| `span:persistence:OrderRepository.createEntity` | kieker-native | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) |
| `span:persistence:OrderRepository.updateEntity` | kieker-native | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) |
| `span:persistence:PersistenceCategory.getId` | kieker-native | 0/10 (1/30) | 9/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) |
| `span:persistence:PersistenceOrder.getId` | kieker-native | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) |
| `span:persistence:PersistenceOrder.setUser` | kieker-native | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) |
| `span:persistence:PersistenceOrderItem.getId` | kieker-native | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) |
| `span:persistence:PersistenceOrderItem.getOrder` | kieker-native | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) | 0/10 (6/30) |
| `span:persistence:PersistenceOrderItem.setOrder` | kieker-native | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) |
| `span:persistence:PersistenceOrderItem.setProduct` | kieker-native | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) | 0/10 (10/30) |
| `span:persistence:PersistenceProduct.getId` | kieker-native | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) |
| `span:persistence:PersistenceProduct.setCategory` | kieker-native | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) |
| `span:persistence:PersistenceUser.getId` | kieker-native | 9/10 (28/30) | 9/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (28/30) | 0/10 (10/30) |
| `span:persistence:ProductEndpoint.countForCategory` | kieker-native | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) |
| `span:persistence:ProductEndpoint.listAllForCategory` | kieker-native | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) |
| `span:persistence:ProductRepository.createEntity` | kieker-native | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) |
| `span:persistence:ProductRepository.getAllEntities` | kieker-native | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) | 0/10 (2/30) |
| `span:persistence:ProductRepository.getProductCount` | kieker-native | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) | 0/10 (3/30) |
| `span:persistence:UserEndpoint.findById` | kieker-native | 9/10 (28/30) | 2/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (28/30) | 0/10 (10/30) |
| `span:persistence:UserRepository.createEntity` | kieker-native | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) | 0/10 (5/30) |
| `span:persistence:UserRepository.getUserByName` | kieker-native | 9/10 (28/30) | 2/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (28/30) | 0/10 (10/30) |
| `log:*` | kieker-native | 10/10 (0/30) | 10/10 (0/30) | 10/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) |
| `metric:*` | kieker-native | 1/10 (2/30) | 9/10 (2/30) | 10/10 (3/30) | 1/10 (2/30) | 2/10 (2/30) | 10/10 (3/30) | 2/10 (2/30) | 10/10 (3/30) | 2/10 (2/30) | 0/10 (2/30) | 10/10 (3/30) |
| `span:*` | kieker-native | 9/10 (28/30) | 9/10 (28/30) | 0/10 (10/30) | 9/10 (28/30) | 9/10 (28/30) | 9/10 (10/30) | 9/10 (28/30) | 9/10 (10/30) | 9/10 (28/30) | 9/10 (28/30) | 9/10 (10/30) |
| `log:auth:*` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) |
| `log:db:*` | kieker-native | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:image:*` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) |
| `log:recommender:*` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) |
| `log:registry:*` | kieker-native | 10/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `log:webui:*` | kieker-native | 10/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) |
| `metric:auth:*` | kieker-native | 0/10 (1/30) | 4/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) |
| `metric:db:*` | kieker-native | 0/10 (0/30) | 9/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `metric:image:*` | kieker-native | 0/10 (0/30) | 1/10 (0/30) | 10/10 (1/30) | 1/10 (0/30) | 0/10 (0/30) | 2/10 (1/30) | 1/10 (0/30) | 0/10 (1/30) | 0/10 (0/30) | 0/10 (0/30) | 1/10 (1/30) |
| `metric:persistence:*` | kieker-native | 1/10 (0/30) | 1/10 (0/30) | 8/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 1/10 (0/30) | 2/10 (0/30) | 1/10 (0/30) | 0/10 (0/30) | 1/10 (0/30) |
| `metric:recommender:*` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 1/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 10/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `metric:registry:*` | kieker-native | 0/10 (1/30) | 1/10 (1/30) | 1/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 0/10 (1/30) | 1/10 (1/30) | 0/10 (1/30) | 10/10 (1/30) |
| `metric:webui:*` | kieker-native | 1/10 (0/30) | 0/10 (0/30) | 5/10 (0/30) | 0/10 (0/30) | 2/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) |
| `span:image:*` | kieker-native | 0/10 (0/30) | 0/10 (0/30) | 0/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) | 9/10 (0/30) |
| `span:persistence:*` | kieker-native | 9/10 (28/30) | 9/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (10/30) | 0/10 (28/30) | 0/10 (28/30) | 0/10 (10/30) |

4 symbols with 0 detections and 0 false alarms in every class (0/n, never dropped; denominators per class as above): `metric:db:cpu`, `metric:image:cpu`, `metric:webui:mem`, `span:persistence:ProductEndpoint.findEntityById`

### G-old: combinations on valid fault cells of posture kieker-native (sensors firing in >= 1 episode: 42; triples computed)

| class | n | sensors firing | pairs | redundant (conj = min single) | complementary (union > max single) | pairs with conjunction = n | triples beyond every sub-pair |
|---|---|---|---|---|---|---|---|
| auth_freeze | 10 | 8 | 28 | 28 | 0 | 1 | 0 of 56 |
| db_crash | 10 | 20 | 190 | 165 | 25 | 45 | 25 of 1140 |
| image_crash | 10 | 10 | 45 | 41 | 4 | 1 | 0 of 120 |
| image_loss | 10 | 6 | 15 | 15 | 0 | 0 | 0 of 20 |
| orderitems_timeout | 10 | 5 | 10 | 10 | 0 | 0 | 0 of 10 |
| persistence_crash | 10 | 12 | 66 | 61 | 5 | 15 | 0 of 220 |
| persistence_latency | 10 | 6 | 15 | 14 | 1 | 0 | 0 of 20 |
| recommender_crash | 10 | 8 | 28 | 28 | 0 | 1 | 0 of 56 |
| recommender_exception | 10 | 6 | 15 | 14 | 1 | 0 | 0 of 20 |
| recommender_latency | 10 | 4 | 6 | 6 | 0 | 0 | 0 of 4 |
| registry_restart | 10 | 11 | 55 | 54 | 1 | 6 | 0 of 165 |

Complementary pairs, db_crash (n = 10): `metric:auth:cpu`(1)+`metric:auth:mem`(3) union 4 conj 0; `metric:auth:cpu`(1)+`metric:image:mem`(1) union 2 conj 0; `metric:auth:cpu`(1)+`metric:persistence:mem`(1) union 2 conj 0; `metric:auth:cpu`(1)+`metric:registry:mem`(1) union 2 conj 0; `metric:auth:cpu`(1)+`span:persistence:UserEndpoint.findById`(2) union 3 conj 0; `metric:auth:cpu`(1)+`span:persistence:UserRepository.getUserByName`(2) union 3 conj 0; `metric:auth:mem`(3)+`metric:image:mem`(1) union 4 conj 0; `metric:auth:mem`(3)+`metric:registry:mem`(1) union 4 conj 0; `metric:auth:mem`(3)+`span:persistence:UserEndpoint.findById`(2) union 5 conj 0; `metric:auth:mem`(3)+`span:persistence:UserRepository.getUserByName`(2) union 5 conj 0; `metric:db:mem`(9)+`span:persistence:PersistenceCategory.getId`(9) union 10 conj 8; `metric:db:mem`(9)+`span:persistence:PersistenceUser.getId`(9) union 10 conj 8; `metric:db:mem`(9)+`span:persistence:UserEndpoint.findById`(2) union 10 conj 1; `metric:db:mem`(9)+`span:persistence:UserRepository.getUserByName`(2) union 10 conj 1; `metric:image:mem`(1)+`metric:persistence:mem`(1) union 2 conj 0; `metric:image:mem`(1)+`metric:registry:mem`(1) union 2 conj 0; `metric:image:mem`(1)+`span:persistence:UserEndpoint.findById`(2) union 3 conj 0; `metric:image:mem`(1)+`span:persistence:UserRepository.getUserByName`(2) union 3 conj 0; `metric:persistence:mem`(1)+`metric:registry:mem`(1) union 2 conj 0; `metric:persistence:mem`(1)+`span:persistence:UserEndpoint.findById`(2) union 3 conj 0; `metric:persistence:mem`(1)+`span:persistence:UserRepository.getUserByName`(2) union 3 conj 0; `metric:registry:mem`(1)+`span:persistence:PersistenceCategory.getId`(9) union 10 conj 0; `metric:registry:mem`(1)+`span:persistence:PersistenceUser.getId`(9) union 10 conj 0; `metric:registry:mem`(1)+`span:persistence:UserEndpoint.findById`(2) union 3 conj 0; `metric:registry:mem`(1)+`span:persistence:UserRepository.getUserByName`(2) union 3 conj 0

Complementary pairs, image_crash (n = 10): `metric:persistence:cpu`(5)+`metric:recommender:cpu`(1) union 6 conj 0; `metric:persistence:cpu`(5)+`metric:webui:cpu`(5) union 8 conj 2; `metric:persistence:mem`(8)+`metric:webui:cpu`(5) union 9 conj 4; `metric:recommender:cpu`(1)+`metric:registry:cpu`(1) union 2 conj 0

Complementary pairs, persistence_crash (n = 10): `log:webui:d4d75ec135e6`(9)+`metric:image:mem`(2) union 10 conj 1; `metric:image:mem`(2)+`span:image:AbstractCache.getEntries`(9) union 10 conj 1; `metric:image:mem`(2)+`span:image:AbstractCache.loadData`(9) union 10 conj 1; `metric:image:mem`(2)+`span:image:ImageProvider.getImageFor`(9) union 10 conj 1; `metric:image:mem`(2)+`span:image:ImageProviderEndpoint.getWebUIImages`(9) union 10 conj 1

Complementary pairs, persistence_latency (n = 10): `metric:image:mem`(1)+`metric:persistence:mem`(1) union 2 conj 0

Complementary pairs, recommender_exception (n = 10): `metric:persistence:mem`(1)+`metric:registry:mem`(1) union 2 conj 0

Complementary pairs, registry_restart (n = 10): `metric:image:mem`(1)+`metric:persistence:mem`(1) union 2 conj 0

### G-old: mutual information I(symbol; class), bits, plug-in (ranking aid, no test)

| symbol | pooled bits (n; class sizes) | per service (bits, n) |
|---|---|---|
| `span:AbstractCache.getEntries:missing_expected` | 0.558 (440; {"auth_freeze": 10, "db_crash": 10, "image_crash": 10, "image_loss": 10, "orderitems_timeout": 10, "persistence_crash": 10, "persistence_latency": 10, "recommender_crash": 10, "recommender_exception": 10, "recommender_latency": 10, "registry_restart": 10, "no-fault": 330}) | image 0.558 (440) |
| `span:AbstractCache.loadData:missing_expected` | 0.558 (440; {"auth_freeze": 10, "db_crash": 10, "image_crash": 10, "image_loss": 10, "orderitems_timeout": 10, "persistence_crash": 10, "persistence_latency": 10, "recommender_crash": 10, "recommender_exception": 10, "recommender_latency": 10, "registry_restart": 10, "no-fault": 330}) | image 0.558 (440) |
| `span:ImageProvider.getImageFor:missing_expected` | 0.558 (440; {"auth_freeze": 10, "db_crash": 10, "image_crash": 10, "image_loss": 10, "orderitems_timeout": 10, "persistence_crash": 10, "persistence_latency": 10, "recommender_crash": 10, "recommender_exception": 10, "recommender_latency": 10, "registry_restart": 10, "no-fault": 330}) | image 0.558 (440) |
| `span:ImageProviderEndpoint.getWebUIImages:missing_expected` | 0.558 (440; {"auth_freeze": 10, "db_crash": 10, "image_crash": 10, "image_loss": 10, "orderitems_timeout": 10, "persistence_crash": 10, "persistence_latency": 10, "recommender_crash": 10, "recommender_exception": 10, "recommender_latency": 10, "registry_restart": 10, "no-fault": 330}) | image 0.558 (440) |
| `log:template:novel` | 0.511 (440; {"auth_freeze": 10, "db_crash": 10, "image_crash": 10, "image_loss": 10, "orderitems_timeout": 10, "persistence_crash": 10, "persistence_latency": 10, "recommender_crash": 10, "recommender_exception": 10, "recommender_latency": 10, "registry_restart": 10, "no-fault": 330}) | db 0.267 (440); registry 0.439 (440); webui 0.133 (440) |
| `span:PersistenceCategory.getId:present` | 0.488 (440; {"auth_freeze": 10, "db_crash": 10, "image_crash": 10, "image_loss": 10, "orderitems_timeout": 10, "persistence_crash": 10, "persistence_latency": 10, "recommender_crash": 10, "recommender_exception": 10, "recommender_latency": 10, "registry_restart": 10, "no-fault": 330}) | persistence 0.488 (440) |
| `log:template:d4d75ec135e6` | 0.476 (440; {"auth_freeze": 10, "db_crash": 10, "image_crash": 10, "image_loss": 10, "orderitems_timeout": 10, "persistence_crash": 10, "persistence_latency": 10, "recommender_crash": 10, "recommender_exception": 10, "recommender_latency": 10, "registry_restart": 10, "no-fault": 330}) | auth 0.267 (440); image 0.267 (440); recommender 0.267 (440); webui 0.441 (440) |
| `log:exception:ClientException` | 0.448 (440; {"auth_freeze": 10, "db_crash": 10, "image_crash": 10, "image_loss": 10, "orderitems_timeout": 10, "persistence_crash": 10, "persistence_latency": 10, "recommender_crash": 10, "recommender_exception": 10, "recommender_latency": 10, "registry_restart": 10, "no-fault": 330}) | webui 0.448 (440) |
| `log:exception:TimeoutException` | 0.448 (440; {"auth_freeze": 10, "db_crash": 10, "image_crash": 10, "image_loss": 10, "orderitems_timeout": 10, "persistence_crash": 10, "persistence_latency": 10, "recommender_crash": 10, "recommender_exception": 10, "recommender_latency": 10, "registry_restart": 10, "no-fault": 330}) | webui 0.448 (440) |
| `log:exception:ProcessingException` | 0.413 (440; {"auth_freeze": 10, "db_crash": 10, "image_crash": 10, "image_loss": 10, "orderitems_timeout": 10, "persistence_crash": 10, "persistence_latency": 10, "recommender_crash": 10, "recommender_exception": 10, "recommender_latency": 10, "registry_restart": 10, "no-fault": 330}) | auth 0.156 (440); image 0.156 (440); persistence 0.156 (440); recommender 0.156 (440); webui 0.413 (440) |
| `metric:mem:spike_down` | 0.401 (440; {"auth_freeze": 10, "db_crash": 10, "image_crash": 10, "image_loss": 10, "orderitems_timeout": 10, "persistence_crash": 10, "persistence_latency": 10, "recommender_crash": 10, "recommender_exception": 10, "recommender_latency": 10, "registry_restart": 10, "no-fault": 330}) | db 0.133 (440); image 0.156 (440); persistence 0.156 (440); recommender 0.156 (440); registry 0.117 (440) |
| `span:UserEndpoint.findById:missing_expected` | 0.316 (440; {"auth_freeze": 10, "db_crash": 10, "image_crash": 10, "image_loss": 10, "orderitems_timeout": 10, "persistence_crash": 10, "persistence_latency": 10, "recommender_crash": 10, "recommender_exception": 10, "recommender_latency": 10, "registry_restart": 10, "no-fault": 330}) | persistence 0.316 (440) |
| `span:UserRepository.getUserByName:missing_expected` | 0.316 (440; {"auth_freeze": 10, "db_crash": 10, "image_crash": 10, "image_loss": 10, "orderitems_timeout": 10, "persistence_crash": 10, "persistence_latency": 10, "recommender_crash": 10, "recommender_exception": 10, "recommender_latency": 10, "registry_restart": 10, "no-fault": 330}) | persistence 0.316 (440) |
| `span:PersistenceUser.getId:missing_expected` | 0.315 (440; {"auth_freeze": 10, "db_crash": 10, "image_crash": 10, "image_loss": 10, "orderitems_timeout": 10, "persistence_crash": 10, "persistence_latency": 10, "recommender_crash": 10, "recommender_exception": 10, "recommender_latency": 10, "registry_restart": 10, "no-fault": 330}) | persistence 0.315 (440) |
| `span:CategoryEndpoint.listAllEntities:present` | 0.292 (440; {"auth_freeze": 10, "db_crash": 10, "image_crash": 10, "image_loss": 10, "orderitems_timeout": 10, "persistence_crash": 10, "persistence_latency": 10, "recommender_crash": 10, "recommender_exception": 10, "recommender_latency": 10, "registry_restart": 10, "no-fault": 330}) | persistence 0.292 (440) |

(top 15 of the ranking; the full ranking is in `tables.md`)
symbols with I = 0 bits pooled: 187 of 283

### G-old: R(p) with G1-G6 (span-exporting episodes)

- episodes: 110; |R| distribution: {"0": 4, "1": 13, "2": 3, "3": 5, "4": 34, "5": 7, "6": 20, "7": 4, "8": 9, "9": 2, "10": 8, "11": 1}; distinct R sets: 35; empty R: 4; G4 metric-without-log: 11
- composition per class: {"auth_freeze": {"log+span": 8, "log": 1, "log+metric+span": 1}, "db_crash": {"span": 4, "metric+span": 5, "metric": 1}, "image_crash": {"log+metric": 9, "log": 1}, "image_loss": {"log": 10}, "orderitems_timeout": {"span": 7, "empty": 1, "metric+span": 2}, "persistence_crash": {"log+span": 8, "log+metric+span": 1, "log+metric": 1}, "persistence_latency": {"span": 8, "empty": 1, "metric+span": 1}, "recommender_crash": {"log+span": 7, "log": 1, "log+metric+span": 2}, "recommender_exception": {"span": 7, "empty": 1, "metric+span": 2}, "recommender_latency": {"span": 9, "empty": 1}, "registry_restart": {"log+span": 7, "log+metric+span": 2, "log": 1}}
- G2 removed (target-service sensors) per class: {"auth_freeze": 0, "db_crash": 109, "image_crash": 10, "image_loss": 37, "orderitems_timeout": 0, "persistence_crash": 10, "persistence_latency": 1, "recommender_crash": 10, "recommender_exception": 0, "recommender_latency": 0, "registry_restart": 10}; G3 removed per class: {"auth_freeze": 16, "db_crash": 49, "image_crash": 47, "image_loss": 12, "orderitems_timeout": 14, "persistence_crash": 25, "persistence_latency": 13, "recommender_crash": 31, "recommender_exception": 17, "recommender_latency": 16, "registry_restart": 32}
- max f_all / f_any per k (greedy (34 distinct sets > 20)): k=1 all 10 any 63 (greedy); k=2 all 11 any 82 (greedy); k=3 all 12 any 92 (greedy); k=4 all 13 any 101 (greedy); k=5 all 13 any 103 (greedy); k=6 all 13 any 104 (greedy); k=7 all 13 any 105 (greedy); k=8 all 13 any 106 (greedy)
- R+ (G2 off): distinct 37; max f_all per k: k=1 1; k=2 1; k=3 1; k=4 1; k=5 1; k=6 1; k=7 2; k=8 2
- level sets over the catalogue domain: -- (R11)
