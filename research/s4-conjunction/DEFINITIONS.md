# Conjunction objective with non-trace requirement sets: definitions (FROZEN 2026-09-26)

**Frozen before any S4 value is computed.** Committed on its own, before `research/s4-conjunction/conjunction.py`
exists. On 2026-09-26 the user delegated U1–U13 ("S4 you can start them"). **Every U decision takes the draft
default in §13**, including U9 (H-B stays primary and run 1 stays separate, so the sprint comparison holds) and U13 (read the TeaStore
corpus read-only now; nothing is written to it). A change after this commit is an amendment, dated and committed on its own.
The draft this came from is `research/prep-20260925/S4_CONJUNCTION_DEFINITIONS_DRAFT.md` (2026-09-25).

**Status: DRAFT. Not frozen.** The user has not given the go-ahead for S4 (`research/NEXT_STEPS_20260925.md` §2).
Section 13 lists the choices that are the user's. The draft freezes only after the user answers U1–U13. It is then
copied to `research/s4-conjunction/CONJUNCTION_DEFINITIONS.md` and committed on its own, before any code that reads
an outcome value. Template and style: `research/sprint-draft2/DETECTION_DEFINITIONS.md`.
Nobody has reviewed this draft, neither the judge nor a separate session.

**Question.** CLAUDE.md ("Modality scope") says the binding constraint is how `R(p)` is built. When requirement
sets may contain `log:` and `metric:` sensors, and are built with a validity gate the old builder lacked, what does
the conjunction objective `f_all(S) = |{p : ∅ ≠ R(p) ⊆ S}|` look like on the evidence we have? The comparison is
against the sprint's detection counts (`research/sprint-draft2/DETECTION_RESULT.md`). Scope label for every
output: **instance**. Each generation is one host, one workload and one fault catalogue.

## 1. Disclosed prior look (before these definitions)

The sprint's detection counts are already known and are used below. Beyond them, the following values were seen
while drafting. Everything else is unread.

- **Old TeaStore repo (`../test-repos/TeaStore`, "TS"):**
  - `data/experiments/baseline/ground_truth.json`: all 16 paths, with their events and messages.
  - `by_server/fb14srv6/{fault_image_crash_20260718_052446, baseline_ref_1_20260718_045834, fault_registry_restart_20260718_053002}`:
    path-type counts, prefix combinations, and whether the events fall inside the run's window.
    For example, `baseline_ref_1` is a no-fault run with 92 `error_propagation` paths, 33 of them outside `[start_time, end_time]`.
  - `fault_auth_freeze_20260718_002411`: the first record of each sidecar file, plus `metadata.json`.
  - `paper_recompute/paper_numbers.json` → `h2_modality` (already quoted in CLAUDE.md).
- **Hotel #6, run `7fd8717d`, reservation-pause b05:**
  - line-layout counts in `application.log` for all three postures;
  - the first `cpu.json` sample and the fault/warm-up timestamps;
  - incidentally, `workload-reconciliation.json` of the sample-zero cell: 140 failed of 1,200 offered.
- **TeaStore e3-a5:** one span record, from `persistence-crash-effect/b01-02-full/traces.json`.

The predictions in §10 that restate sprint numbers are therefore **consistency predictions, not independent tests**.

## 2. Facts this draft rests on (each with its command)

Scripts are in `…/scratchpad/fan1/s4/inventory/` (session scratchpad; copy them into the repo on freeze). All of
them are read-only and run under `/usr/bin/python3 -B`.

| # | Fact | Command / source |
|---|---|---|
| F1 | The 527 old `ground_truth__trace.json` files cover **three SUTs**: TeaStore/Kieker 155, Hotel/DeathStarBench 110, OTel demo 262. CLAUDE.md calls them "TeaStore ground truths". | `old_gt_suts.py TS/data/experiments` (reads the first 8 KB of each file, where `build_params.compose_file` sits) |
| F2 | Old TeaStore generation **G-old**: `by_server/fb14srv6`, `trace_collection.collector = kieker_native`, 300 s runs, dated 2026-07-17/18. It has 140 runs: 11 fault families × 10, plus 30 `baseline_ref`. Every run keeps `ground_truth.json`, `logs.json`, `metrics.json`, `proc_metrics.json`, `docker_events.json` and `traces.json`. 110/110 fault runs carry `fault_started_at`. Fault at 75 s. | `old_population.py TS/data/experiments/by_server/fb14srv6` |
| F3 | The old TeaStore corpus mixes many harness generations: 66 metadata signatures, covering macOS Docker Desktop in Jan 2026, srv5/srv6 from Mar to Jul 2026, and load generators that differ. Top-level dirs duplicate `by_server/` dirs by name. | inline scan while drafting (grouped by metadata keys, collector, load command, duration, `fault_at`); `by_server/fb14srv6/DATA_STATE.md` |
| F4 | Old Hotel and OTel runs have `metrics.json` ≤ 1 KB and **no `metadata.json`**, so no fault timestamps (Hotel: 110/110 without metadata). They cannot be windowed, so they are out. | same scan (sidecar presence per SUT) |
| F5 | In `baseline/ground_truth.json` (Jan 2026), **8/8** `error_propagation` paths have events about 32,660 s *before* `metadata.start_time`. They were built from unwindowed `logs_full.json`: MariaDB `[Warning] 'proxies_priv'` and `InnoDB` startup lines paired with persistence startup lines. | `baseline_gt_window.py TS/data/experiments/baseline` |
| F6 | The old `level` field depends on the generation. In the Jan 2026 `logs_full.json`, the line `[main] WARN …InitialDataGenerationDaemon - Exception connecting to database…` carries `level: ERROR`. The collector at TS HEAD takes the first `\b(FATAL\|SEVERE\|ERROR\|WARN…)\b` anywhere in the message (`tools/collectors/collect_logs_docker.py:146-156`), which is a regex over line text. On an unparseable docker timestamp it falls back to `time.time()` (`:141`). | read; one line matched against the GT event |
| F7 | G-old `logs.json` is windowed with a **180 s pre-buffer and a 30 s post-buffer** (`metadata.log_filter_stats`, 140/140 runs), so stack start-up is inside the file. Stack-trace frames are separate records. With the collector's `strip()`, they have lost their leading tab and default to `INFO`. | `fault_auth_freeze_20260718_002411/{logs.json, metadata.json}` first records |
| F8 | Old builder: `metric:` is emitted only paired with `log:` (`build_propagation_paths.py:543-544`, `_extract_resource_contention`). The ACSOS H2 "metrics 0" also comes from a single-modality greedy restricted to the `metric:` prefix (`tools/recompute_paper_artifacts.py:287-300`). Under `f_all`, that greedy cannot satisfy a path that also needs `log:`. **Metrics = 0 is true by construction twice over.** | read |
| F9 | ACSOS H2 population: `paper_numbers.json` (27 Jun) → `servers.fb14srv5.root = by_server/fb14srv5`, selected through a campaign manifest. `by_server/fb14srv5/campaign_latest.json` is dated 2026-07-12, after 27 Jun, so the exact H2 GT set is **?**. | read |
| F10 | No application log line in any generation carries a trace or request id. The only Hotel lines with `traceId` are the harness's `OBSPLACEMENT_EMISSION` span witnesses (`full` only). Request witnesses (`OBSPLACEMENT_WITNESS`) carry a harness `opaqueToken`. Application layouts: zerolog JSON has keys `{level, message, time}` (30/30 JSON lines in the sampled cell); zerolog ConsoleWriter and Go `log` have no id field; TeaStore log4j `[thread] LEVEL logger - msg` and JUL have no MDC. **A trace-correlated log join is impossible on this evidence.** Only (service, time) joins are available. | layout count on the `7fd8717d` b05 cells; `DETECTION_DEFINITIONS.md` §Families and A1 |
| F11 | Hotel `application.log` covers the whole container lifetime. The sampled cell starts at 03:50:36Z, warm-up ends at 03:51:14.9Z, the first `cpu.json` sample (t0) is at 03:51:20.5Z, and the fault starts at 03:52:05.1Z (scheduled at 45 s). | same cell: `warmup.json`, `cpu.json`, `fault-receipt.json` |
| F12 | Hotel has two plan generations with retained logs. **H-A**, plan `98773760` (two postures): #1 `bbf7f360` has 8 valid no-fault cells and **0** fault cells (its search-pause cell is blocked-evidence only); #2 `fb8dcd9e` and #5 `658f9b6a` have 8 no-fault, 8 reservation and 8 search cells each (4 per posture). **H-B**, plan `ac60dbbc` (three postures, #6): 6 per regime × posture per run, runs 1 and 3–6. Application logs for #3 and #4 were not found under `tmp/` or `.local/` (**?**). | `hotel_lineages.py <run roots>`; `find tmp .local -name application.log` |
| F13 | TeaStore e3-a5 (**T-new**) has 36 runs and 32 valid. There are 4 postures (`none`, `selected`, `auth-persistence-webui`, `full`) × 3 blocks per regime, so there are **3 `full` episodes per regime**. Logs cover 2 of 5 services (`auth.log`, `persistence.log`). There is no metric family in fault cells. | `campaign-terminal-validation.json`; `DETECTION_DEFINITIONS.md` |
| F14 | Kieker span records (G-old and T-new) have `status_code: null` in the sampled records. Whether any record carries an error mark is **?**. The sprint's error-span trace detector may therefore be undefined for TeaStore. | first records; the script must count non-null `status_code` |
| F15 | Empty requirement sets are handled in two different ways. `src/obsplacement/placement.py` `objective_value(all)` counts `∅` as 0. `research/submodularity.py:103` `make_f` counts `∅ ⊆ S` as 1 for every S. | read |
| F16 | Catalog trace sensors: Hotel has 6 `span:<svc>:<op>` sensors (frontend, search, geo, rate, reservation, profile). TeaStore has 6 (`operation:{auth,image,persistence,recommender,webui}`, `propagation:registry-client`). | `modules/*/activation/catalog.json` |

## 3. Generations and population (compared, never pooled)

A generation is a harness signature: plan digest (OP) or metadata signature (TS) × host. Every number is reported
per generation, and no statistic is computed across generations.

| id | SUT | Where | Episodes used for R(p) | No-fault set (calibration) |
|---|---|---|---|---|
| **H-B** | Hotel | #6 runs 3–6 (`969a1362`, `a8e7e72e`, `88b7bf7c`, `7fd8717d`), fb14srv4, plan `ac60dbbc`, `candidateCellValid` | `full` cells: 24 reservation-pause, 24 search-pause | 72 no-fault cells (all postures) |
| H-B′ | Hotel | #6 run 1 `210a480a` (same plan) | 6 + 6 `full` | 18 |
| **H-A** | Hotel | #2 `fb8dcd9e` and #5 `658f9b6a`, plan `98773760` | 8 + 8 `full` | 16 |
| **G-old** | TeaStore | TS `by_server/fb14srv6`, kieker_native, 2026-07-17/18 (F2) | 110 fault runs (11 families × 10) | 30 `baseline_ref` |
| **T-new** | TeaStore | `tmp/teastore-e3-user-a5-evidence`, validCells | 3 + 3 `full`; all postures for log-only rows | 12 no-fault |

- **H-B′.** It is reported beside H-B, not pooled with it. The detection sprint left run 1 out, and H-B must stay
  comparable with the sprint. For the cost result, the user pooled run 1 (L1, `ee11f0d`); U9 asks whether to pool here too.
- **Excluded, with reasons:**
  - old Hotel and OTel: no timing metadata (F4);
  - all other TS signatures: F3, since pooling them is forbidden, and none but G-old keeps every sidecar with fault timing on one host at n=10;
  - Hotel #1: no valid fault cell;
  - #3 and #4: no logs found;
  - Online Boutique: the hold-out; no fault regime, and not touched before the method digest is frozen.
- **The 60 GB corpus is read, never written.** Only the files of the 140 G-old runs are opened, one run at a time. No
  `ground_truth__*.json` above 1 MB is loaded; the G-old `ground_truth.json` files are the old builder's output for exactly these runs.

## 4. Path unit and sensor universe

**Primary unit, P-EP (episode).** One path per valid fault episode in the table above. `R(p)` is the episode's
**admissible multi-family footprint**: every sensor whose event (§5) fires inside the episode window and passes the
gate (§6). `f_all(S)` counts episodes whose whole footprint is observed. `f_any(S)` restricted to one family is the
sprint's detection. The sprint's detection is therefore the any-view of the same object, and this draft adds the all-view.

**Secondary unit, P-JT (journey × time co-occurrence).** Computed only where timestamped logs exist: H-B, H-B′, H-A
and G-old `full`. One path per trace that starts inside W:
- **Trace part of R(j):** the observed service set, mapped to catalog sensors, as `research/observed_requirements.py` does.
- **`log:s`:** added iff s is on the trace and an admissible `log:s` event falls in the seconds `[floor(start), end]` of the trace.
- **`metric:s:cpu`:** added iff s is on the trace and an admissible metric event's sample interval `(t_{k-1}, t_k]` intersects the trace.

This is **time co-occurrence at 1 s (Hotel) or docker-timestamp (G-old) resolution. It is not correlation (F10).**
It is labelled that way everywhere. At concurrency 16, every trace through s in that second receives the sensor.

**Rejected units:**
- **Service relabelling** ("a trace needs `log:s` whenever s is on it"): true by construction. It reproduces the trace conjunction under new names.
- **Old-builder hop pairs** (`log:up`→`log:down` over the compose graph, first pair in `error_lag`): the choice of pair is arbitrary, and the path map is not sensor-independent. Memory "traces are a lane, not the canals": no sensor-independent call graph exists yet, so hop paths are deferred.

**Universe U = U_trace ∪ U_log ∪ U_metric, per generation.**
- **U_trace** is the catalog's trace sensors (F16). For G-old, `trace:<svc>:<op>` collapses to `operation:<svc>`, and
  the Kieker-instrumented services outside the OP catalog get G-old-only ids (the list is written when the population
  is read, U12). The live catalogs are not edited.
- **U_log** is `log:<svc>`, one per service whose stream the generation captures:
  - Hotel: 10 application services;
  - G-old: 7 compose services (auth, db, image, persistence, recommender, registry, webui);
  - T-new: auth and persistence only.
  - Each sensor means "this service's log stream at level ≥ WARN" (U4).
- **U_metric** is `metric:<svc>:cpu`, for Hotel (10, `cpu.json`) and G-old (7, docker stats). T-new has none (`—`).
  Memory, network, `contention:` and `error:` are excluded (U2):
  - `error:<svc>:<action>` is the docker event of the injection itself, so it is true by construction;
  - memory, network and contention exist only in G-old and have no counterpart in any other generation.

## 5. How a non-trace requirement enters R(p)

The join key is **(service, time window)**. No trace correlation is possible (F10).

- **Episode window W.**
  - Hotel: `[startedAt, endedAt]` from `fault-receipt.json`. This is the sprint's definition, with 1 s timestamps: a line at second t is in W if `floor(start) ≤ t ≤ end`.
  - G-old: `[fault_started_at, fault_finished_at]` from `metadata.fault`.
  - Tail T after the window end: 0 (primary), 30 s (declared sensitivity, U7).
  - T-new: **cell-level** (log4j lines have no timestamp). It is labelled cell-level. Windowed JUL lines are backlog (DETECTION_RESULT "Correction").
- **No-fault pseudo-window.**
  - Hotel: `[t0+45 s, t0+60 s]`, t0 = first `cpu.json` sample (sprint).
  - G-old: `[start_time+75 s, start_time+75 s+D_f]`, where D_f is the median of `fault_finished_at − fault_started_at` for family f in G-old. This uses timing metadata only.
  - T-new: the whole no-fault cell.
- **Events.**
  - **Log.** `log:s` fires in W iff at least one reconstructed log *record* (§7) of s, at level ≥ WARN, lies in W and passes G1–G6.
    Frozen levels are:
    - zerolog `warn`/`error`/`fatal`/`panic`;
    - gRPC `WARNING`/`ERROR`/`FATAL`;
    - log4j/slf4j `WARN`/`ERROR`/`FATAL`;
    - JUL `WARNING`/`SEVERE`;
    - MariaDB `[Warning]`/`[ERROR]`.
  - **Metric.** `metric:s:cpu` fires in W iff a sample in W satisfies `|x − m_s| ≥ 4·σ_s` and `|x − m_s| ≥ 1 pp`:
    - m_s is the median of the samples before W, from t0 onward; σ_s = 1.4826 · MAD over the same samples;
    - this is the sprint's detector, parameters unchanged (U11); sensitivity: floor 2 pp (SWEEP_PLAN).
    - **It is evaluated on its own.** No rule makes a metric (or any family) conditional on another family's event (G4).
  - **Trace (U8).** Primary: `trace` sensor s fires iff at least one span of s starts in W (presence; the live `f(S)` semantics, defined on both SUTs).
    Variant, Hotel only: the sprint's error-marked span. TeaStore's error variant is `—` unless F14 finds error marks.
    The trace family exists only in `full` cells, which is why P-EP uses `full` episodes.

## 6. Validity gate (the old builder had none of these)

- **G1 start-up.** An event counts only if `t ≥ t0` and `t ∈ W` (or `W+T`).
  - Hotel: t0 = first `cpu.json` sample (after warm-up, F11).
  - G-old: t0 = `metadata.start_time`. The 180 s pre-buffer (F7) and everything before are out.
  - This removes the F5/F7 class (stack start-up paired across services) by construction.
  - Lines with a timestamp after `end_time + log_post_buffer_seconds` are flagged as collector-fallback stamps (F6) and excluded. Their count is reported.
- **G2 fault-self.** Primary R(p) excludes every sensor of the fault's own target service. This covers a paused
  target's CPU and its missing spans, and a crashed target's restart and start-up lines. All of these are close to
  true by construction (DETECTION_RESULT "What it does not support").
  - The variant R⁺(p) includes them (U5).
  - G-old targets are fixed by family from `metadata.fault.fault_command`:
    - auth: auth_freeze, and orderitems_timeout (the Byteman rule runs in `auth`);
    - db: db_crash;
    - image: image_crash, image_loss;
    - persistence: persistence_crash, persistence_latency;
    - recommender: recommender_crash, recommender_exception, recommender_latency;
    - registry: registry_restart.
- **G3 no-fault admissibility, calibrated inside each generation only.**
  - *Log (template level).* Template = (service, level, logger) for log4j and JUL; (service, level, caller) for zerolog;
    (service, level, `go-log`) for Go `log`; (service, level, `mariadb`) for MariaDB. A record counts toward `log:s`
    only if its template occurs in at most ⌊0.05·n₀⌋ no-fault pseudo-windows of the generation, where n₀ is the
    number of no-fault windows. For T-new, where n₀ = 12, that means 0. Known templates are down-weighted, not
    deleted, and every excluded template is listed with its no-fault count. This inverts the old substring blacklist
    (`configs/teastore.yaml:41-45`), which is not used.
  - *Metric (sensor level).* `metric:s:cpu` is admissible only if its false-alarm rate over the no-fault
    pseudo-windows is ≤ ⌊0.05·n₀⌋ / n₀.
  - τ = 5 % is U6.
- **G4 no conjunction artefact.** A metric requirement enters R(p) iff its own event fires (§5). A self-check with a
  synthetic cell (metric event, no log event) must yield R ∋ `metric:*` and R ∌ `log:*`. The report states how many
  episodes have metric ∈ R and no log ∈ R. The old builder gives 0 by construction (F8).
- **G5 harness output is not application output.** Excluded before parsing:
  - Hotel `OBSPLACEMENT_EMISSION` and `OBSPLACEMENT_WITNESS` lines;
  - TeaStore `OBSERVABILITY_*` witness lines;
  - compose CLI lines without a `<service>-<n> |` prefix;
  - the old collector's `level` field, which is ignored and re-parsed (F6).
- **G6 unparsed.** A line that starts no record in any layout (§7) and cannot be attached as a continuation is
  counted as unparsed and never fires a sensor. The unparsed share is reported per generation and per service.

## 7. Parsers (typed, framework layouts; no regex over line text specific to one codebase)

- **Framing.**
  - Hotel: compose stream `<service>-<n> | <payload>`, SGR stripped (ECMA-48).
  - G-old: `logs.json` records `{timestamp, service, container, message}`, timestamps from the docker receive stamp.
  - T-new: per-file.
- **Record-start layouts** (each is a published framework format):
  - zerolog JSON (`level`, `time`, `message`, optional `caller`);
  - zerolog ConsoleWriter `<RFC3339> <LVL> <caller> > <msg>`;
  - Go `log` `2006/01/02 15:04:05 <msg>`, with the gRPC severity prefix (A1);
  - log4j/slf4j-simple `[<thread>] <LEVEL> <logger> - <msg>`;
  - Tomcat/JUL OneLineFormatter `dd-MMM-yyyy HH:mm:ss.SSS <LEVEL> [<thread>] <logger> <msg>`;
  - MariaDB error log `<date> <time> <thread-id> [<Level>] <msg>`.
- **Multi-line records.** A line that matches no record-start layout is a continuation of the previous record of
  the same container. This is the standard multi-line rule of Fluent Bit and Logstash ("negate, match after").
  JVM stack traces and Go panics therefore inherit their parent's level and never fire on their own. Orphan
  continuations with no parent are unparsed (G6).
- **Levels come from the layout's level field only.** They never come from searching the message.
- **Timestamps.**
  - Hotel: the payload's own time (container clock UTC), cross-checked against `cpu.json` epochs as in A1.
  - G-old: the docker receive stamp.
- **Stop condition S-P (§12).** An unparsed share above 5 % of a generation's non-harness lines means the parser is
  incomplete for that generation. The log family of that generation stops, and no pattern is added to close it.

## 8. Objective and computations

- **The objective is taken from `src/obsplacement/placement.py`.**
  - `f_all` and `f_any` are used as defined there. `f_partial` (sqrt) is reported only as a selection surrogate.
  - `∅` contributes 0 (U10). Episodes with `R(p) = ∅` are counted and reported ("unobservable footprint").
  - `submodularity.make_f`, which counts `∅` as satisfied, is not used here (F15).
- **Placement domain.** The catalog-feasible trace placements (activation closure, `research/submodularity.py`
  `closure_feasible`), crossed with the power set of U_log ∪ U_metric. No activation dependencies are assumed among
  log or metric sensors (engineering default, recorded). The sizes are at most about 2 × 2²⁰ (Hotel) and 33 × 2¹⁴
  (G-old; the trace domain is **?** until U12 fixes the G-old trace ids). The Hotel figure of 2 trace-feasible
  placements comes from the memory note on the conditional vocabulary and is unverified here: run `closure_feasible`
  on the Hotel catalog before quoting it.
- **Exact optimum at budget k** is computed by enumerating unions of distinct R sets. If there are more than 20
  distinct sets, greedy is used and labelled as greedy.
- **Reported per generation, unit and variant:**
  - n episodes;
  - the `|R(p)|` distribution;
  - family composition per episode (the sprint's "overlap" becomes composition);
  - the number of distinct R sets;
  - level sets over the domain;
  - the exact `max f_all` and `max f_any` per k;
  - whether the maximisers differ;
  - the G4 count;
  - the G1/G3 exclusion counts.
- **No intervals and no p-values.**

## 9. Comparison with the sprint's detection counts

- **C1 bridge (identity check).**
  - Setup: G2 off, G3 off, T = 0, the error-span trace variant, and the level detector.
  - Requirement: `f_any` per family, over **all postures**, must reproduce DETECTION_RESULT exactly:
    - H-B tables;
    - sweep row "warn+";
    - T-new level `11/11`, `0/9`, no-fault `0/12`.
  - This is a check that the code implements the sprint's detectors. It is not a finding.
- **C2 gate effect.**
  - The same `f_any` table with G1–G6 on, beside the C1 table.
  - Every change is traced to the gate that caused it.
- **C3 conjunction.**
  - The §8 outputs for P-EP, beside the sprint's family-overlap counts.
  - The sprint's "log + both metric parts 47" becomes an R-composition count under G2/G3.
- **C4 old builder vs gated builder (G-old only).**
  - From each run's `ground_truth.json`: old path counts by type and prefix combination, the share of old log and
    metric path events outside W and outside `[start_time, end_time]`, and the count of old `metric:` requirements
    without `log:` (expected 0, per F8 and MIGRATION_LOSS §0.4).
  - Then the same quantities for the gated R(p).
  - The ACSOS H2 numbers are not re-derived, because their population is **?** (F9).
- **C5 generations.** For the two fault families present in both TeaStore generations, the per-generation R composition
  is shown side by side and never combined:
  - auth-freeze: pause auth, 45 s in G-old and 15 s in T-new;
  - persistence-crash.
  H-A vs H-B is shown the same way.

## 10. Predictions (written before any S4 value is read)

Items marked "(sprint)" restate the sprint's counts, so they are consistency checks, not tests.

- **P1** (hard gate): C1 reproduces DETECTION_RESULT exactly. (sprint)
- **P2** H-B P-EP: `log:frontend` ∈ R(p) in ≥ 20/24 reservation-pause episodes and 0/24 search-pause episodes. (sprint, but
  now under G3)
- **P3** H-B P-EP: in search-pause, ≥ 20/24 episodes have at least one `metric:` sensor and no `log:` sensor in R(p).
  A G3 metric exclusion may break this; if it does, that breakage is the gate's measured effect.
- **P4** H-B P-EP: at least 2 distinct R sets across the 48 episodes. No R set occurs in both regimes.
- **P5** G-old P-EP (primary, G2 on):
  - auth_freeze has a non-self `log:` sensor in R(p) in ≤ 2/10 runs;
  - persistence_crash has one in ≥ 8/10;
  - db_crash has one in ≤ 2/10.

  These borrow from ACSOS H2 and from T-new, with a different builder and population. The prediction is directional.
- **P6** G-old: C4 finds old `metric:` requirements without `log:` = 0/total. The gated R(p) has ≥ 1 metric-without-log
  episode in every family in which the CPU detector fires at all.
- **P7** H-A vs H-B: the same regime-level composition as P2/P3 in both generations. This is instance scope per
  generation, not replication across them.

## 11. True by construction (listed so that none is reported as a result)

- `f_all` over any conjunction family is supermodular. Adding families cannot make it submodular.
- More distinct R sets means more level sets, mechanically.
- Trace sensors are silent under `none` and `sample-zero`.
- The G-old "metrics 0" (F8).
- C1's agreement with the sprint.
- A metric requirement under the always-on status (U3 option b) never constrains a placement.
- Under G2-off (R⁺):
  - a paused target's CPU event;
  - a crash target's restart lines;
  - `error:` sensors, excluded for this reason.
- The share of old-builder baseline events that fall outside a 45 s pseudo-window of a 300 s run.

## 12. Stop rules and budget

- **Budget: 1 day** (NEXT_STEPS S4), split as follows:
  - parsers and multi-line: 2 h;
  - R(p) builder and gate: 3 h;
  - G-old streaming read: 2 h;
  - optimisation and report: 2 h;
  - slack: 1 h.
  - At 50 % over (12 h), stop and write a ledger row.
- **S-B:** if P1 fails, stop. No conjunction number is reported, and a ledger row explains the mismatch.
- **S-G:** generations are compared, never pooled. A script that computes a statistic across generation ids refuses to run.
- **S-P:** no regex over line text specific to one codebase. An unparsed share above 5 % stops that generation's log family (§7).
- **S-Z:** a family that never fires in a generation is carried as `0/n`. A family with no data is `—` (T-new metric). Unknown is `?`.
- **S-A:** any definition changed after the first S4 value is an amendment, marked post hoc. The frozen result stays primary (as in A1).
- **S-J:** one judge call per claim before it enters any document. Apply NEXT_STEPS §4: for an edit, read the correctness vote on the current text.
- **S-D:** the TS corpus is read-only. If a G-old run lacks a field the definitions need, it is excluded and counted. If more than 10 % of G-old runs are excluded, G-old stops.
- **S-O:** outputs go to a new path per run (`tmp/s4-conjunction/<utc-stamp>/`). Evidence stays out of git; the result doc is committed.

## 13. Decisions

**Preregistration decisions: the user's.** Each one changes `f(S)`, what counts as a requirement, or the population.

| # | Decision | Draft default | Alternatives |
|---|---|---|---|
| U1 | Path unit | P-EP primary, P-JT secondary | P-JT primary; P-EP only |
| U2 | Families in U | trace + `log:<svc>` + `metric:<svc>:cpu` | add G-old memory, network or contention (G-old-only rows) |
| U3 | Activation status of metrics (harness-observed, MIGRATION_LOSS §4(b)) | (a) selectable at unit cost, labelled "hypothetical activation choice" | (b) always on at zero cost, which makes metric requirements vacuous; report both |
| U4 | Log-sensor granularity | one per service at ≥ WARN | per level (old builder); per template |
| U5 | Fault-self exclusion | excluded in primary (G2), R⁺ as variant | included in primary |
| U6 | Admissibility τ | 5 % of no-fault windows; template level for logs, sensor level for metrics | sensor level for logs; τ = 0 |
| U7 | Window tail T | 0 primary, 30 s sensitivity | 5 s (the old `error_lag`) |
| U8 | Trace event in R(p) | presence (the live f(S) semantics) | error span (Hotel only) |
| U9 | Population | H-B primary; H-B′, H-A, G-old, T-new each separate | pool run 1 into H-B (as L1 did for cost); drop T-new (n = 3 `full` per regime) |
| U10 | Empty R | contributes 0; count reported | counts as satisfied (`make_f`) |
| U11 | Metric detector | sprint frozen: k = 4, floor 1 pp | floor 2 pp primary (0/72 false alarms in the sweep) |
| U12 | G-old trace ids | collapse to `operation:<svc>`, G-old-only ids for services outside the catalog | op-level `trace:<svc>:<op>` |
| U13 | Timing relative to S1 | read the TS corpus read-only now | back up the 60 GB first (S1), then read |

**Engineering defaults (picked here; recorded in the descriptor on freeze):**
- the parsers and multi-line rule of §7;
- the harness-line exclusions of G5;
- collector-fallback timestamp exclusion;
- the 5 % stop share for unparsed lines;
- exact optimisation by distinct-R unions, with a greedy fallback above 20 sets;
- no activation dependencies among log or metric sensors;
- `/usr/bin/python3 -B`, clearing `~/Library/Caches/com.apple.python/` before any replay;
- script at `research/s4-conjunction/conjunction.py`, with `--self-check` covering G4 and the parser fixtures;
- output paths per S-O;
- refusing any cell whose `cpu.json` or receipt `schemaVersion` differs within a generation.

## 14. Corrections to existing notes, found while drafting (not yet applied anywhere)

- CLAUDE.md "Modality scope" calls the 527 `ground_truth__trace.json` files TeaStore ground truths. They are
  155 TeaStore, 110 Hotel and 262 OTel (F1).
- The old corpus is not one generation (F3). Any "previous version" number needs its signature.
- The ACSOS H2 population cannot be identified from `campaign_latest.json` (F9).
- The baseline `error_0` startup-noise caveat (MIGRATION_LOSS §1.7) is stronger than stated. All 8 error paths of
  that GT lie about 9 h before its run window (F5), and the level labels there were assigned from message text (F6).

## 15. Open questions (for the append-only log)

- F14: does any Kieker record carry an error mark? If none does, U8's error variant is Hotel-only by design.
- Hotel #3/#4 application logs: are they archived anywhere outside `tmp/` and `.local/`? (**?**)
- Should G-old's 11 fault families all enter, or only the families shared with a current generation (auth-freeze,
  persistence-crash)? The draft enters all 11 and reports the shared two side by side (C5).
