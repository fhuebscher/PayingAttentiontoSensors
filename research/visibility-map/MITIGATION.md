# No-traffic fault corpora: root cause, exposure, gates (2026-10-02)

Follow-up to `MAP.md` (7fabefe) and `research/WRITEUP_20261001.md` §5.2 row (vi). Offline and read-only. The old repo
`../test-repos/TeaStore` is read-only reference: its files are cited, never changed. `TS` below means
`../test-repos/TeaStore`, and `C6` means `TS/data/experiments/by_server/fb14srv6`. Every number is **instance**
scope unless a row says otherwise. Gate numbers come from
`/usr/bin/python3 -B research/visibility-map/traffic_gate.py --legacy --by-family`, the script committed with this
file (§3.2).

## 1. Root cause

### 1.1 What the corpus is

The scored corpus ("G-old") is the **first** TeaStore 10x nightly attempt on fb14srv6. It ran from 2026-07-17 17:54
to 2026-07-18 06:11 CEST (last run started 06:06): 10 reps × 14 runs (3 `baseline_ref` + 11 fault families) in 10 manifests,
`C6/fault_campaign_20260717_175409.json` … `_20260718_045834.json`. In every rep the runs follow one fixed order:
db_crash, auth_freeze, image_crash, registry_restart, persistence_crash, recommender_crash, recommender_latency,
image_loss, persistence_latency, recommender_exception, orderitems_timeout. Each fault starts at 75 s
(`metadata.fault.fault_at_seconds`, 110/110 runs).

### 1.2 What happened, from the corpus's own files

1. **No readiness gate at start-up.** The old repo's own postmortem, dated 2026-07-18 and committed only as a
   shell comment (`TS/tools/run_nightly_replication.sh:32-38`, commit ef6f945f, 2026-07-20), says three things. A
   `sleep 30` after `up` stood in for readiness. Every rep started at 2/5 services. webui's Kieker AMQP writer
   raced RabbitMQ and died for the JVM's lifetime. The corpus agrees on the last point: webui emits **0 spans in
   110/110 fault runs** (`visibility.json`, `populations.teastore-Gold.episodes[].workload.spanServices`). The postmortem's
   "2/5" is not exact. The load generator's status line in each rep's first run reads `healthy (5/5)` in 4 of 10 reps
   and `DEGRADED (2/5)` or `(3/5)` in 6. Every later run in a rep reads `(4/5)` or `(0/5)`, except rep 10's runs 7–14,
   which have no status line (the first `SYSTEM` or `System` line of each run's `load_gen.log`).
2. **The system was failing before any fault.** Within each rep, only the first run after the reset
   (`baseline_ref_1`) gets real work done: 19 to 29 cycles and about 455 HTTP 200s, in 9 of 10 reps. The two
   no-fault baselines that follow it, and db_crash and auth_freeze, return **0 HTTP 200s** in 3 to 4 cycles of
   about 20 s per request, all non-200 (477 HTTP 500 and 108 HTTP 404 over the 10 reps). In the gate's terms, G2 (healthy before the fault) holds in 9/30 baselines
   and 0/110 fault runs.
3. **image_crash is the exception, and it is inverted.** In `fault_image_crash_20260717_182020`, image is stopped
   at 18:21:35 (`fault.log:2-3`). The first HTTP 200 of the run comes 23 s later (`load_gen.log:121`), and 200s keep
   coming until 18:22:41 (`load_gen.log:882`), 11 s after image restarts (`fault.log:5-6`). Across the corpus,
   image_crash has 1 request before the fault (HTTP 500) and 336 to 364 OK requests inside it, in 9/9 runs that
   have traffic. **The fault is what turned the traffic on.** The mechanism the old postmortem gives, that load on a
   cold stack wedged image, is consistent with this contrast but not shown by it.
4. **One wedge carries over to every later family.** From image's restart onward, every request hangs until the
   next rep's `down -v`. For example, the status check of `fault_registry_restart_20260717_182535` blocks from
   18:25:35 to 19:07:27 (`load_gen.log:4-5`), and rep 2's reset is at 17:07:16Z = 19:07:16 CEST
   (`C6/nightly_replication.log:3793`). The load generator that ran had no curl timeout, so it never got past its
   status check: **0 cycles**. `--max-time` was added afterwards, with the comment "2026-07-18: hung webui -> 3
   cycles/300s instead of ~99" (`TS/tools/load_gen_loop.sh:57-58`, ef6f945f). Its health check only logs `DEGRADED`
   and carries on (`load_gen_loop.sh:65-74`).
5. **Why the result is "10 of 10 runs each".** The order is fixed, so the same 8 families come after image_crash in
   every rep. Rep 4 (2026-07-17 21:35) is dead from its second run; its first, `baseline_ref_1`, got 7 cycles and 26 OK. That is the "1/10 has no request in the window" in
   auth_freeze, db_crash and image_crash. Rep 10's logs end before the hang releases, which is the "1/10 no cycle
   line".

**Verdict.** The chain starts with the **start-up order** and the missing readiness gate: the broker race, a stack at
2/5 to 4/5 services, and a stack that wedged under load before any fault. The **load generator** made it total: it
had no request timeout, and its health check did not stop it. It was **not** a fault applied before warm-up, since
every fault is at 75 s. A **carry-over between runs** turned one wedge into 8 empty families, because the order was
fixed and nothing checked recovery between runs. The fault catalogue was never exercised on a working system:
image_crash's traffic is an artefact of its own fault.

### 1.3 Why nobody noticed for weeks

The defect was found and fixed in the harness the next day, but the fix never reached the data:

| Check | Existed? | What it said about this corpus |
|---|---|---|
| nightly rep exit codes (`run_nightly_replication.sh`, `REP n OK`) | yes | `all reps done … failed: 0/10` (`C6/nightly_replication.log:7321`). It checks exit codes, not content. |
| collector parse statistics (`metadata.trace_collection.native_parse_stats`) | yes, never thresholded | `record_parse_success_ratio` is 1.0 in 72/110 fault runs, 0.83 in 9, ≥ 0.999 in 20, and **0.0 in 9** (rep 4, 0 records). Even the 0.0s raised nothing. |
| record counts (`metadata.counts.traces`) | recorded, never thresholded | `5` in most later-family runs, against 24,678 in image_crash |
| a dose floor for traces | **OTel only** (`check_otel_dose`, `TS/tools/run_nightly_10x.sh:92`; `ensure_load`, `TS/tools/run_otel_faults.sh:121`) | none for TeaStore or HotelReservation |
| TeaStore readiness (`wait_teastore_ready`, `amqp_writer_ok`) | **added after this corpus** (`run_nightly_replication.sh:39,54`) | — |
| a starvation marker on the data | **no** | The postmortem is a comment in a script. The starved runs stayed in `C6`, intact and unflagged, beside the healthy re-run. |
| S4 population selection (`research/s4-conjunction/symptoms.py:620-650`; `DEFINITIONS.md:49,82`) | yes, **by completeness** | It kept runs that carry every sidecar. It excluded 7 runs as `partial campaign` (the healthy 5/5 smoke campaign `fault_campaign_20260717_162748`) and 112 as `missing sidecar` (the post-fix re-run, which was fetched as per-trace ground truth only). The rule chose the starved attempt because it was the only complete one. |
| S4 exclusion rule S-D (`DEFINITIONS.md:318`) | yes, **field presence** | 110/110 carry `fault_started_at`, so 0 excluded |
| requests or spans per scored window | **no**, until `MAP.md` (2026-10-01) | — |

The numbers looked plausible:

- `metrics.json` held 418 to 427 docker-stats samples in every fault run, whatever the traffic
  (`metadata.counts.metrics`, 110/110).
- Logs were windowed with a 180-s pre-buffer that takes in stack start-up (`DEFINITIONS.md` F7): 0 to 7,173 records per
  run, median 131 (`metadata.counts.logs`).
- Log templates still fired, for example `L:registry:*` in 10/10 auth_freeze runs (`MAP.md`, its catching-sensors
  table).
- The span family still "caught" 9/10 in most families, from the trace stream of an idle or down system (at most 5
  start-up spans per run; `MAP.md` reading, `visibility.py:918-919`).
- False alarms were 0/30 in every family (`research/s4-conjunction/RESULT_BASELINE.md:96`), which reads as perfect
  specificity, not as a rate that cannot fail.
- n = 10 per family, 110 episodes, 101 of 110 caught at k = 4.
- These rows held in the paper from rc4 (2026-09-28) through rc10 (`papers/current/lncs/paper.rc{4..10}-*.tex`, the
  lines matching "earlier corpus"), 7 tags.

## 2. Exposure audit

A **Gate** column marked `[proxy]` means a trace-only population. It has no request ledger, so its rows are trace
starts, `ok` means the trace has no error span (or `ok` is unknown), and its windows are inferred from the runner's
timing constants. G1 is traffic in the scored window, G2 is a healthy system before the fault, G3 is a
false-alarm rate that can fail, and G4 is provenance (§3). Denominators are cells or windows. `—` means not
computable or not local.

| Population (where used) | Evidence | G1 fault windows | G2 pre-fault healthy | G3 FA n_eff/n | G4 | Exposure |
|---|---|---|---|---|---|---|
| Earlier TeaStore corpus G-old (paper rc4–rc10 Table 1; S4 `RESULT_BASELINE.md` findings 8–12; `MAP.md`) | `C6`, 110 fault + 30 baseline | 9/110 (image_crash only) | **0/110** | **0/30 FAIL** | FAIL (ledger 0/140) | **Vacuous.** Dropped in rc11. `RESULT_BASELINE.md` findings 8–12 still read as valid (§5). |
| Fig. 3(b) HR fault row, 10 campaigns `hr_campaign_20260717_*`, 70 scenarios (rc11 §7: "1.1 M paths, +11.2 points at budget 10") | `TS/…/fb14srv5`, traces only `[proxy]` | 50/70 | 70/70 | 10/10 | **FAIL: scope** | Traffic is present and the pre-fault system is healthy, but there is a **different defect**: each scenario's `traces.json` holds the campaign's history, not the scenario. File span has median 1,298 s against a 240-s scenario. Of the 1,095,499 fault-file traces, **22.6 %** start inside their own scenario and **6.4 %** inside its fault window. In 2 campaigns checked, 10–13 % of trace ids appear in more than one file. Low in-window counts: `geo_latency` 288 vs floor 526 and `profile_latency` 39.5 vs 449 (medians, 10/10 each). Cause: either the closed-loop generator slowing down or Jaeger's fetch cap; which one is `?`. |
| Fig. 3(a) OTel lab mix, `otel_campaign_20260712_124211`, 10 scenarios, 47,132 paths | traces only `[proxy]` | 9/10 | 9/10 | 3/3 | FAIL (no ledger, no fault timing) | `fault_productCatalogFailure`'s trace stream **ends at 76 s, before its 90-s fault**: 0 traces in the window, so its 1,178 paths (2.5 %) are all pre-fault. `fault_productcatalog_crash` has one trace at 0 s and none until 74 s, and its pre-window has 300 ok against 55 failed. The window is inferred from `run_otel_faults.sh:38-39`, which was committed after the campaign. |
| Fig. 3(c) TeaStore native, 2,201 traces | one file `[proxy]` | — | — | — | FAIL (no fault timing) | Traffic is present: 184 s, webui 2,198 spans. The fault window cannot be checked. |
| Fig. 3(d) HR construct row, 1,602 traces | one file `[proxy]` | — | — | — | FAIL (no ledger) | A construct row with no fault. 1,586 of 1,602 traces fall in one 40-s burst, so it is not exposed to vacuity. |
| §3 TeaStore 11,262 traces (`research/observed_requirements.py:33`) | e3-user a5, 9 `*-full` cells | 6/6 | 6/6 | 3/3 | **FAIL: invalid scored** | Traffic is fine. **1 of 9 cells is `unsupported`** (`auth-freeze-effect/b03-03-full`, 1,151 traces). Known since `research/paper-provenance/PROVENANCE_20260923.md:10` ("10,111 without the blocked cell") and still undisclosed in `paper.rc11-20261001.tex:214`. |
| §6 HotelReservation, runs 1, 3–6 (rc11 Table 1, 72 episodes per class; cost 30 blocks) | `tmp/sprint-hotel6-x` | 36/36 per run | 36/36 per run | 18/18 per run | PASS | none |
| HotelReservation lmt2, sel1, int1, rep1 (§6 degradations, replication) | `tmp/hotel{lmt2,sel1,int1,rep1}-evidence/x` | 64/64 each | 64/64 each | 16/16 each | PASS | none |
| TeaStore #16 (rc11 Table 1) and the e3-user rung | `tmp/teastore16-evidence`, `tmp/teastore-e3-user-a5-evidence` | 18/18; 20/20 | 18/18; 20/20 | 9/9; 12/12 | PASS | none |
| TeaStore ladder and replications #9–#15, #17, #18 (§5 cost, 21 blocks) | extracted `tmp/teastore1*-evidence`, `research/campaign9-evidence` | all pass where fault cells exist | all pass | PASS, or `—` if cost-only | PASS | none |
| OTel run 2, run 3, v3 | `tmp/otel-{run2,run3,v3}-evidence` | 9/9, 9/9, 12/12 | same | 9/9, 9/9, 12/12 | PASS | none. The margin is thin: 85 starts in the window against a floor of 78, while a no-fault window of the same length holds 155. The frontend pause stalls the concurrency-capped generator (concurrency 8, 8-s start gaps every 15 s in `b01-01-async`), so on OTel G1 is confounded with the fault's effect (§3.1). |
| **Current** campaigns: Hotel replication 2 (`1e6003bc`), TeaStore #19, OTel v3 attempt 2 | not fetched | — | — | — | — | Run the gate after fetch (§4). |
| Old thesis draft, `TS/research/THESIS_DRAFT.md:177` ("TeaStore native: exact tie, ±0.00 in all 110 lane-runs") | `?` | — | — | — | — | 110 = 11 × 10 is one TeaStore 10x attempt. `TS/tools/build_gt_pertrace_batch.py` globs both attempts (`fault_campaign_2026071*_*.json`), and that glob also matches the six 2026-07-12/13 manifests in `C6`, so which campaigns fed it is `?`. If it was G-old, the tie is vacuous. Its HR line (`:169-171`, +11.2 pp) is Fig. 3(b), with the scope defect. |
| Post-fix TeaStore attempt (unscored; §4) | `C6/*_2026071[89]_*` after 14:32, ground truth only `[proxy]` | 40/110 | **110/110** | 30/30 | FAIL (no ledger, no fault timing) | Healthy before every fault: about 1,597 traces in the first 75 s. The low in-window counts are the faults throttling a closed-loop generator (db_crash 12.5, persistence_latency 12.5, auth_freeze 145, against about 950 for baselines). That is an effect, not starvation. |

**Panel (b)'s other 69 scenarios** have traffic and a healthy system before the fault (G2 70/70), so the no-traffic
class does not reach Figure 3(b). Its own exposure is the window: at most a quarter of each scenario's paths belong
to that scenario, and about one path in sixteen to its fault. The panel is labelled a "fault row" in rc11 §7 and
`figure_manifest.json`, but it is mostly baseline and earlier-scenario traffic. Its curves are a property of that
mixed traffic. Whether the +11.2-point margin survives a window-scoped rebuild is `?` (§5).

## 3. Preventive gates

### 3.1 The four gates

| Gate | Rule (engineering defaults, recorded here) | Where it belongs | Exists today | Cost |
|---|---|---|---|---|
| **G1 traffic per scored window** | Request **starts** in the window ≥ 0.5 × declared rate × window seconds. Count starts, not completions or spans: a fault that slows a closed-loop generator lowers completions legitimately. | Terminal validator first, then the analysis entry and the visibility map | TeaStore: `actual-phase-start-floor`, ≥ 20 journeys before, during and after, as a **literal** (`../observability-placement-runtime-teastore-sys/modules/teastore/validation/candidate_pilot.py:1751-1756`); it ran and passed 18/18 on #16. OTel: a ≥ 1-request floor per phase (`tmp/otel-v2-admission/modules/otel-demo/validation/candidate_terminal.py:421-422`), plus `completed + failed == offered` (`:560-568`). Hotel: none. Its validator checks only `completed + failed == 1200` (`…-runtime-hotel-srv4/modules/hotel-reservation/validation/candidate_terminal.py:490-506`). Starts are **not** scheduled by construction: OTel's concurrency-capped generator starts 85 instead of 155 in a pause window. A G1 floor on fault windows is therefore confounded with the effect on OTel, and with any fault that saturates the generator's concurrency. Either count scheduled opportunities in the window, or set the floor from the concurrency cap. `visibility.py` flags `LOW-WORKLOAD` from spans (1 span/s), not from the ledger. | Analysis: done (`traffic_gate.py`), 0 h. Validators: about 20 lines each. **Any framework commit invalidates an approved GATE-PLAN** (CLAUDE.md), so fold it into the next planned harness commit, not a standalone one. |
| **G2 healthy before fault** | Successes in [measurement start, onset) ≥ 0.5 × rate × seconds, and failure share ≤ 5 %. | Terminal validator and analysis | TeaStore: `effect-context`, no pre- or post-fault failures (`candidate_pilot.py:1757-1767`), and `no-fault-workload-context` (`:1562-1568`). Hotel: a 30-s warm-up with 0 failures, else the cell aborts (`…/workload/fixed_search.py:138`, `…/execution/candidate_cell.py:760-767`), plus one route probe (`preRouteAvailable`, `faults/compose_pause.py:145`). Nothing checks the measured ledger's pre-window. OTel: a correlation check on every successful pre-fault request (`candidate_terminal.py:347-365`), but no failure-share or count floor. | As G1. The analysis side is done. |
| **G3 non-vacuous false-alarm rate** | Report k/n_eff, where n_eff counts no-fault windows that pass G1 and G2 **and** in which a planted failure makes the rule fire. For the any-failure entry-point rule, the plant always fires once the window holds a request and the pre-window is defined, so in `traffic_gate.py` this reduces to G1 ∧ G2 ∧ (≥ 1 request in the window). A real planted-positive test is needed only for detectors with a latency or rate half. n_eff < n is PARTIAL; n_eff = 0 is "the rate cannot fail" and is **not reported**. | Analysis scripts that print FA rates: `research/lmt-pilot/lmt_detect.py`, `research/s4-conjunction/relevance.py`, `visibility.py` | No. The entry-point rule's precondition is implicit: `ledger_check.cell` raises on an empty pre-window (`research/hotel-selected/ledger_check.py:30`), and `visibility.ledger_rule` returns unknown. | Entry-point rule: done in `traffic_gate.py`. Per detector family, a planted positive (inject one template line, one metric step, one span error) is about half a day each, for L, M and T. |
| **G4 provenance** | Every scored cell has a start-stamped request ledger, fault cells have fault timing, every cell has a validity verdict, the scored set holds no invalid cell, and ≥ 95 % of the cell's records lie inside its own measurement. A selection rule lists the runs it excluded and their G1/G2 verdicts. | Visibility map and analysis entry, before any scoring | Partly: the harness writes all of these for Hotel, TeaStore and OTel. Nothing **refuses** a population that lacks them, and `observed_requirements.py` reads invalid cells. | 0 h to run. Each consumer needs one call to the gate before scoring, about 1 h in total. |

Not proposed as a gate: a starvation **marker** on old data. That would mean writing into `../test-repos`, which is
read-only. G4's exclusion listing covers the same need from this side.

### 3.2 The gate built: `research/visibility-map/traffic_gate.py`

The script implements G1–G4 over normalised cells. It has adapters for the three harness ledgers, the old
`load_gen.log`, and the trace-only legacy corpora. It writes nothing.

- **Self-check, three states.** The check exists, it ran, and it was seen failing on a planted defect.
  - `--self-check` builds one healthy population and five planted defects in memory: no traffic in the window, failing
    before the fault, idle no-fault windows, no ledger, and an invalid cell scored.
  - Each defect flips its gate and the healthy population passes all four: `self-check: PASS (0 mismatches)`, exit 0.
  - With any one gate disabled (`--break G1`, `G2`, `G3`, `G4`), the self-check exits **1**. That is what it looks like
    when a gate misses its planted defect.
- **Run.** `--legacy --by-family`, python 3.9.6, about 10 min, most of it reading the 7 GB of Fig. 3(b) traces. The
  output is the table in §2. The per-family G-old lines read: the 8 dead families have in-window median 0 and a
  pre-window median of 0 rows; auth_freeze, db_crash and image_crash have a pre-window median of 1 row, with 0 ok and
  1 failed.
- **Rate sources.**
  - Plan rate: Hotel 10/s, TeaStore 0.15 journeys/s, OTel 1/s.
  - G-old: the same host's healthy (5/5) smoke campaign two hours earlier, 11.14 HTTP lines/s. That is the median
    over 1 baseline and 6 fault runs with faults at 30 s of 122 s, so it is a conservative floor, not a no-fault rate.
    It is external to the corpus, so a corpus that starved as a whole cannot lower its own floor.
- **Kind and scope.**
  - A cell's kind (fault or no-fault) comes from its path, and its fault timing from its receipt. A fault cell with a
    missing receipt fails G4; it is not reclassified as no-fault.
  - G4's scope clause is computed for every population. G-old's minimum is 0.80, because `load_gen.log` kept being
    appended after its run ended (§1.2, point 4).
  - A fault population with no rate reference gets `—`, never PASS.
  - Trace-only corpora: their own baselines (Fig. 3(b): per-file density, because the Jaeger fetch is capped).

Verbatim summary table of that run (script sha256 `2e2aa6b74826302b8c69388761796c35f396ad3898b52330ddc113c1ad6bb947`):

| population | cells | G1 fault windows | in-window median [min] / floor | G2 pre-fault healthy | G1 no-fault windows | G2 no-fault healthy | G3 FA n_eff/n | G4 provenance |
|---|---|---|---|---|---|---|---|---|
| hotel-run1 | 54 (54 scored, 0 invalid excluded) | 36/36 | 152.0 [152] / 77.0 | 36/36 | 18/18 | 18/18 | 18/18 PASS | PASS |
| hotel-run3 | 54 (54 scored, 0 invalid excluded) | 36/36 | 152.0 [152] / 77.0 | 36/36 | 18/18 | 18/18 | 18/18 PASS | PASS |
| hotel-run4 | 54 (54 scored, 0 invalid excluded) | 36/36 | 152.0 [152] / 77.0 | 36/36 | 18/18 | 18/18 | 18/18 PASS | PASS |
| hotel-run5 | 54 (54 scored, 0 invalid excluded) | 36/36 | 152.0 [152] / 77.0 | 36/36 | 18/18 | 18/18 | 18/18 PASS | PASS |
| hotel-run6 | 54 (54 scored, 0 invalid excluded) | 36/36 | 152.0 [152] / 77.0 | 36/36 | 18/18 | 18/18 | 18/18 PASS | PASS |
| hotel-lmt2 | 80 (80 scored, 0 invalid excluded) | 64/64 | 149.0 [147] / 75.0 | 64/64 | 16/16 | 16/16 | 16/16 PASS | PASS |
| hotel-sel1 | 80 (80 scored, 0 invalid excluded) | 64/64 | 149.0 [147] / 75.0 | 64/64 | 16/16 | 16/16 | 16/16 PASS | PASS |
| hotel-int1 | 80 (80 scored, 0 invalid excluded) | 64/64 | 150.0 [147] / 76.0 | 64/64 | 16/16 | 16/16 | 16/16 PASS | PASS |
| hotel-rep1 | 80 (80 scored, 0 invalid excluded) | 64/64 | 149.0 [147] / 75.0 | 64/64 | 16/16 | 16/16 | 16/16 PASS | PASS |
| teastore-T9 | 12 (11 scored, 1 invalid excluded) | 2/2 | 22.0 [22] / 12.0 | 2/2 | 9/9 | 9/9 | 9/9 PASS | PASS |
| teastore-T10 | 19 (18 scored, 1 invalid excluded) | 9/9 | 22 [22] / 12 | 9/9 | 9/9 | 9/9 | 9/9 PASS | PASS |
| teastore-T11 | 27 (27 scored, 0 invalid excluded) | 18/18 | 22.5 [22] / 12.0 | 18/18 | 9/9 | 9/9 | 9/9 PASS | PASS |
| teastore-T12 | 12 (11 scored, 1 invalid excluded) | 2/2 | 22.0 [22] / 12.0 | 2/2 | 9/9 | 9/9 | 9/9 PASS | PASS |
| teastore-T13 | 27 (27 scored, 0 invalid excluded) | 18/18 | 22.5 [22] / 12.0 | 18/18 | 9/9 | 9/9 | 9/9 PASS | PASS |
| teastore-T14 | 27 (27 scored, 0 invalid excluded) | 18/18 | 22.5 [22] / 12.0 | 18/18 | 9/9 | 9/9 | 9/9 PASS | PASS |
| teastore-T15 | 18 (17 scored, 1 invalid excluded) | 8/8 | 22.0 [22] / 12.0 | 8/8 | 9/9 | 9/9 | 9/9 PASS | PASS |
| teastore-T17 | 13 (12 scored, 1 invalid excluded) | 3/3 | 22 [22] / 12 | 3/3 | 9/9 | 9/9 | 9/9 PASS | PASS |
| teastore-T18 | 6 (5 scored, 1 invalid excluded) | — | — [—] / — | — | 5/5 | 5/5 | — — | PASS |
| teastore-T16 | 27 (27 scored, 0 invalid excluded) | 18/18 | 22.5 [22] / 12.0 | 18/18 | 9/9 | 9/9 | 9/9 PASS | PASS |
| teastore-Tnew | 36 (32 scored, 4 invalid excluded) | 20/20 | 23.0 [22] / 12.0 | 20/20 | 12/12 | 12/12 | 12/12 PASS | PASS |
| teastore-Tnew-sec3 | 9 (9 scored, 0 invalid excluded) | 6/6 | 22.5 [22] / 12.0 | 6/6 | 3/3 | 3/3 | 3/3 PASS | FAIL (ledger 9/9, faultTiming 6/6, validity 9/9, invalidScored 1, scope min 1.00) |
| otel-run2 | 18 (18 scored, 0 invalid excluded) | 9/9 | 85 [85] / 78 | 9/9 | 9/9 | 9/9 | 9/9 PASS | PASS |
| otel-run3 | 18 (18 scored, 0 invalid excluded) | 9/9 | 85 [85] / 78 | 9/9 | 9/9 | 9/9 | 9/9 PASS | PASS |
| otel-v3 | 24 (24 scored, 0 invalid excluded) | 12/12 | 85.0 [85] / 78.0 | 12/12 | 12/12 | 12/12 | 12/12 PASS | PASS |
| teastore-Gold | 140 (140 scored, 0 invalid excluded) | 9/110 | 0.0 [0] / 256.0 | 0/110 | 0/30 | 9/30 | 0/30 FAIL | FAIL (ledger 0/140, faultTiming 110/110, validity 0/140, invalidScored 0, scope min 0.80) |
| fig3a-otel-lab [proxy] | 13 (13 scored, 0 invalid excluded) | 9/10 | 3223.0 [0] / 1562.0 | 9/10 | 3/3 | 3/3 | 3/3 PASS | FAIL (ledger 0/13, faultTiming 0/10, validity 0/13, invalidScored 0, scope min 0.96) |
| fig3b-hr10 [proxy] | 80 (80 scored, 0 invalid excluded) | 50/70 | 826.0 [29] / 554.0 | 70/70 | 10/10 | 10/10 | 10/10 PASS | FAIL (ledger 0/80, faultTiming 0/70, validity 0/80, invalidScored 0, scope min 0.11) |
| fig3c-teastore-native [proxy] | 1 (1 scored, 0 invalid excluded) | — | — [—] / — | — | — | 1/1 | — — | FAIL (ledger 0/1, faultTiming —, validity 0/1, invalidScored 0, scope min 1.00) |
| fig3d-hr-construct [proxy] | 1 (1 scored, 0 invalid excluded) | — | — [—] / — | — | — | 1/1 | — — | FAIL (ledger 0/1, faultTiming —, validity 0/1, invalidScored 0, scope min 1.00) |
| teastore-Gold-postfix [proxy] | 140 (140 scored, 0 invalid excluded) | 40/110 | 459.5 [6] / 481.0 | 110/110 | 30/30 | 30/30 | 30/30 PASS | FAIL (ledger 0/140, faultTiming 0/110, validity 0/140, invalidScored 0, scope min 1.00) |

**Limits.** G1 on trace proxies is not interpretable for faults that slow a closed-loop generator; G2 is the test
that separates starvation from effect there. The G2 tolerance of 5 % absorbs journeys that start before onset and
fail inside the window: TeaStore #16 shows a median of 1 such journey per auth-freeze cell, while the harness's own
phase rule counts 0. Inferred windows depend on runner constants that were committed after some of the runs.

## 4. Salvage

- **image_crash alone: no.** Its pre-window holds 1 request (HTTP 500) in 9/9 runs with traffic, and all its traffic
  exists because the fault stopped the service that wedged webui (§1.2, point 3). A catch there compares a dead
  system with one that the fault revived, which inverts the fault. webui emits no spans in it, so the entry span is
  missing too.
- **The post-fix re-run is the only honest TeaStore 10x data in the old corpus.** It is attempt 2: 2026-07-18 14:32
  to 07-19 02:10, 10 manifests, 140 runs. G2 holds in 110/110 fault runs, webui is present, and fault effects show
  in the window. Locally it is **ground truth only** (`ground_truth__trace.json`, about 75 MB each). It has no raw
  traces, logs, metrics, `metadata.json` or `load_gen.log`, so no fault timing (the window is assumed to be 75 s +
  D_f) and no ledger. The old harness never had a start-stamped ledger anyway: `load_gen.log` stamps completions at
  1 s. Whether the raw sidecars survive on fb14srv6 is `?` (no ssh in this session).
- **Worth it: not for this paper.** It could support at most a trace-only, inferred-window row on a different host
  and harness generation from #16, and it would need a fetch (one approved ssh action) plus a fresh S4-style run. It
  cannot answer the entry-point question, which is the map's main column. The current harness already has TeaStore
  with a ledger. Recommended: one disclosed sentence, "a second attempt exists and was not scored", and nothing more.

## 5. Open

1. `research/s4-conjunction/RESULT_BASELINE.md` findings 8–12 (G-old) have no defect banner. This session was
   limited to writing this file and the script, so that edit is not done here.
2. Fig. 3(b): rebuild the 70 ground truths from each scenario's own window, [last start − 240 s, last start] or
   better, then re-run `TS/tools/make_final_figures.py` (old repo: a copy, not an edit) and check whether +11.2 points
   at budget 10 survives. Until then, the rc11 §7 sentence and the panel label "HR fault row" carry the scope defect.
   This is a **preregistration-adjacent decision for the user**, because it changes what the panel measures.
3. Fig. 3(a): one scenario (productCatalogFailure) has no traffic in its fault window. Drop it, or disclose it in the
   caption.
4. §3's 11,262 includes 1 unsupported cell (1,151 traces). Disclose it, or recompute on 8 cells (10,111 traces).
5. The old thesis line "±0.00 in all 110 lane-runs": which attempt fed it is `?`.
6. Current campaigns (Hotel replication 2, TeaStore #19, OTel v3 attempt 2): run `traffic_gate.py` on each after
   fetch. Add their paths to `populations()` when they land.
7. Terminal-validator versions of G1 and G2 for Hotel and OTel, and a rate-derived TeaStore floor in place of the
   literal 20. Ship them with the next planned framework commit, because that commit forces a re-derived GATE-PLAN
   anyway.
8. Planted-positive G3 checks for the L, M and T detectors (§3.1).
9. Independent review: one adversarial-review subagent (model Fable, read-only), 2026-10-02. It made 11 findings: 2
   wrong (parse ratio, rep 4), 5 labels or logic (OTel starts are not scheduled by construction, the scope clause, kind
   taken from a file's existence, the tautological plant, the rate reference), and 4 minor. All are applied above and
   in the script. It re-ran every population except fig3b and the post-fix attempt (7 GB), so those two rows have not
   been checked independently.
