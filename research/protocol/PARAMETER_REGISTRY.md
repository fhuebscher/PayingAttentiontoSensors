# Parameter registry: every hyperparameter and sensitivity setting in the traffic-sweep analysis and campaigns

Built per the user's provenance rule, protocol decision 37 (`research/PROTOCOL_DRAFT_20261002.md:326-327`, round 8,
2026-10-04): "every hyperparameter and sensitivity setting is traced to its origin and tracked: decision, literature
source, or measurement with its command. Nothing in the analysis is 'random'." Scope: `research/detection-time/
sweep_analysis.py` and `detection_time.py`; `research/traffic-sweep/DECLARATION*.md` and `AMENDMENT*.md` (Hotel,
TeaStore, OTel); `research/PROTOCOL_DRAFT_20261002.md`; `research/protocol/METHODOLOGY_HARDENING.md` (H1-H11);
the shared gate module `src/obsplacement/protocol_gates.py` and its source `research/visibility-map/traffic_gate.py`;
and the per-system harness constants in the sibling worktrees that the declarations bind to
(`observability-placement-runtime-{hotel,teastore,otel}-protocol`), read read-only.

Origin types: **decision** (a numbered protocol decision or a frozen declaration/amendment line) · **literature**
(a source id in `LIT_*.md`, or a paper named directly in the protocol before the literature notes existed) ·
**measured** (a command or file that produced the number) · **upstream** (the SUT's or an existing tool's own
default) · **engineering default** (recorded as such, with no preregistration claim) · **unknown** (no record found
anywhere in the repo of why this number and not another). No origin is invented: where the search below found
nothing, the row says `unknown`, not a guess.

This file is read-only research output; the repo and the analysis scripts were not modified to produce it.

---

## Summary

### Counts by origin type
Counted programmatically over every data row of the seven tables below (84 rows; one row = one named constant, or
one tightly-coupled group of constants sharing one citation, e.g. `GRID_K`/`GRID_FLOOR_MS`), by parsing the "origin
type" column of each row for its tag words. 7 rows carry two tags (e.g. a value that is `engineering default` today
and `decision, not yet implemented` for its declared replacement, or `decision` for the mapping plus `upstream` for
the reused magnitude), so the 91 tag instances below are counted from 84 rows, not a disjoint partition of them.

| origin type | tag instances | examples |
|---|---:|---|
| decision | 37 | `RATES`, `EPISODES`, `P2_EPS`, `TRACE_DRAIN_MARGIN_SECONDS`, `PATH_FILTER`, `FLOOR`/`PRE_FAIL_MAX`/`SCOPE_MIN` |
| engineering default | 23 | `K`, `SCALE`, `MIN_BASELINE`, `RUN_N`, `ABSENT_GAP_MULT`, `LEDGER_FLOOR_MS`, `SEEDS`, `REF` |
| decision, not yet implemented | 15 | H1 pooled baseline (n≥20), H2 false-alarms/hour, H3 matched-rate P4, H4 onset interval, H7 per-system K, H8 two-clock win, H9 probabilistic prior, the two relative-floor replacements (`LEDGER_FLOOR_MS`, `LAT_FLOOR_S`) |
| upstream | 6 | TeaStore/OTel client timeout 15 s, `ONSET_TOLERANCE_S` (cited in both the timing and gates tables), CPU-throttle 0.1 and net-delay 100 ms magnitudes, the fault-target mapping |
| measured | 3 | OTel frontendproxy memory 256 MiB, TeaStore `POST_RECOVERY_ALLOWANCE_SECONDS`, the P3 sampling-cadence tolerance |
| literature | 3 | CELF / Leskovec et al. 2007 objective, the submodularity gap (Heavey et al. 2022), the Leskovec censoring rule behind "misses at hold end" |
| **unknown** | **4** | `TAU` = 0.05 (G3/admissibility share, appears in both the false-alarm and gates tables), `SYS_FLOORS` per-resource magnitudes, `SCALE` precision beyond "standard MAD constant" |

37 + 23 + 15 + 6 + 3 + 3 + 4 = 91 tag instances over 84 rows. The verification script is reproducible: parse each
table's rows, split on `|`, read column 4 (origin type), and tally the keyword(s) present.

### The unknown list (what the user must not have)
1. **`TAU = 0.05`** (G3/admissibility false-alarm share). Reused in five independent files (`detection_time.py:109`,
   `research/protocol/sensor_rep/catch.py:46`, `research/lmt-pilot/lmt_detect.py:36`,
   `src/obsplacement/protocol_gates.py:104,127`, `research/detection-time/sweep_analysis.py:130` as `G3_TAU`) as if
   settled, but its own module labels it **"provisional (PLAN_FABLE part 2); draft 3 decision 5 sets it after the
   scope mapping"** (`protocol_gates.py:104`). Decision 5 (`PROTOCOL_DRAFT_20261002.md:202`) deferred K, τ and window
   defaults to the scope-mapping document; that document says explicitly **"no new value is argued here"**
   (`research/scope-20261002/SCOPE.md:316`). So 0.05 has been carried forward by repetition since round 3 and never
   actually ratified. It is load-bearing: it is the admissibility cutoff for every sensor family's false-alarm rule.
2. **`SYS_FLOORS`** per-resource metric floor magnitudes (`sys_cpu` 0.05 cores, `sys_io` 65,536 B/s, `sys_psi_cpu` /
   `sys_psi_memory` / `sys_psi_io` 1,000 stall-µs/s; `research/lmt-pilot/lmt_detect.py:34`). The *mechanism* ("a
   per-resource floor, else 2% of the baseline median") is a recorded engineering default
   (`research/protocol/sensor_rep/catch.py:25-27`); the five specific numbers carry no comment beyond their units and
   no citation to a decision, a paper, or a measurement was found anywhere in the repo.
3. **`SCALE = 1.4826`** (MAD-to-SD consistency factor). It is the standard constant for a normal distribution
   (1/Φ⁻¹(¾)), but no file in this repo says so or cites a source for using it here; it is simply declared beside `K`
   under the "engineering defaults, recorded" heading (`detection_time.py:26-27`, `catch.py:85`). Functionally safe
   (it is a textbook constant), but by the letter of the provenance rule it has no origin recorded in-repo.
4. **Why 0.1 cores / 100 ms specifically for the throttle and delay faults**, beyond "Hotel's pre-existing `profile`
   fault already used it." `research/READING_20261003.md:56` and `DECLARATION.md:32` both only say the magnitude was
   *reused*, not chosen or validated for the sweep's purpose (triggering a detectable-but-not-ledger-dominant effect
   at every rate). No dosing rationale (e.g. "N× the ledger's threshold") was found; `research/scope-20261002/
   SCOPE.md:281` proposes exactly this kind of dosing for a *future* Z2 sub-threshold test but it was not applied
   here.

### Literals that duplicate a declared value instead of reading it (drift risk)
Ranked by how surprising the duplication is, i.e. by how far apart the two copies live and how easy it would be for
one to be edited without the other.

| value | copies found | risk |
|---|---|---|
| `K = 4.0` | `research/detection-time/detection_time.py:107`; `research/protocol/sensor_rep/catch.py:45`; `research/traffic-sweep/readout-hotel-r3/review/recompute.py:5`; indirectly `research/s4-conjunction/symptoms.py:59` (`K = DET.K`, a fourth source) | **High.** Four independent declarations of the same number across three code generations (old rule, new rule, and a one-off review script), with no equality test found tying them together. |
| `TAU = 0.05` | the five files in unknown item 1 above | **High**, compounded by the fact the value itself is unratified (see above): five copies of a number nobody actually set. |
| `RATES = (10.0, 1.0, 0.2, 0.05)` | `research/detection-time/sweep_analysis.py:115`; and independently inside each sibling worktree's `candidate_sweep.py` (Hotel `:59`, TeaStore `:69`, OTel `:75`) | **Medium.** Four copies of one decided tuple (decision 16), each in a different git repository; nothing cross-checks them against each other at runtime except that the frozen plan digests would change if one drifted, which would be caught at the next DRY_RUN, not immediately. |
| `WARMUP_SECONDS=30`, `MEASUREMENT_SECONDS=180`, `FAULT_ONSET_BASE_SECONDS=60`, `FAULT_HOLD_SECONDS=60` | each independently literal in all three `candidate_sweep.py` files (Hotel/TeaStore/OTel) | **Medium**, same shape as `RATES`: one decision (`READING_20261003.md` row 2), three copy-pasted repos. |
| trace-completeness drain margin (`2.0` s) | `TRACE_DRAIN_MARGIN_SECONDS` in Hotel's `candidate_evidence.py:60` and OTel's `candidate_sweep.py:188`; `DRAIN_ALLOWANCE_MARGIN_SECONDS` in TeaStore's `candidate_sweep.py:120` | **Medium.** Same decided value (decision 25), three names, three files; currently in sync, verified by amendment-stage tests, but nothing stops them diverging on a future change to one harness only. |
| trace-completeness allowance share (1%, minimum 1) | Hotel `TRACE_INCOMPLETE_PERCENT = 1` (integer percent; `candidate_evidence.py:61-62`) vs TeaStore `TRACE_INCOMPLETE_FRACTION = 0.01` (`candidate_sweep.py:125`) vs OTel `TRACE_INCOMPLETE_ALLOWANCE_SHARE = 0.01` / `..._MINIMUM = 1` (`candidate_sweep.py:190-191`) | **Low-medium.** Same decided number, but two different *encodings* (integer percent vs. float fraction) of it, which is itself a second, smaller drift surface (an edit to "1" meaning 1% in one file and 100% in another if ever copied across). |
| `FLOOR = 0.5`, `PRE_FAIL_MAX = 0.05`, `SCOPE_MIN = 0.95` | `research/visibility-map/traffic_gate.py:44-46` (source) and `src/obsplacement/protocol_gates.py:123-125` (vendored copy) | **Low.** This duplication is deliberate and self-documented ("vendored byte-identically into the three harnesses, with a test that the copies match", `PROTOCOL_DRAFT_20261002.md:128-129`); unlike the rows above, an equality test exists. Listed for completeness, not as a live risk. |

---

## 1. Detection rules

| name | value / unit | where it lives | origin type | origin reference | differs across systems? |
|---|---|---|---|---|---|
| `K` (robust-threshold multiplier) | 4.0 | `detection_time.py:107`; `sensor_rep/catch.py:45`; `symptoms.py:59` (`K = DET.K`); `readout-hotel-r3/review/recompute.py:5` | engineering default (kept as reference by decision) | self-labelled "engineering defaults, recorded" at `detection_time.py:26-27`; `DETECTION_TIME.md:619` ("this analysis's engineering default, not a preregistered rule, and no other was run"); kept as the **reference** value by decision 31, `PROTOCOL_DRAFT_20261002.md:316-317` | no (same value everywhere; H7 — fit per system — is decided, not implemented) |
| `SCALE` (MAD→SD consistency factor) | 1.4826 | `detection_time.py:108`; `catch.py:85` | **unknown** (standard statistical constant, but no in-repo citation) | none found; see Summary, unknown item 3 | no |
| `MIN_BASELINE` (min pre-window samples for a level threshold) | 3 | `detection_time.py:110`; `catch.py:47` | engineering default; **decision, not yet implemented** (H1: n ≥ 20, pooled) | `detection_time.py:26,165`; H1 decided `METHODOLOGY_HARDENING.md:82` ("Require n ≥ 20 baseline points, else `—`"), ratified `PROTOCOL_DRAFT_20261002.md:316` (decision 31) | no |
| `RUN_N` (consecutive in-window samples for `run3`) | 3 | `detection_time.py:111` | engineering default | `detection_time.py:26,35` | no |
| `ABSENT_MIN` (min pre-window records before `absent` applies) | 5 | `detection_time.py:112` | engineering default | `detection_time.py:26,39` | no |
| `ABSENT_GAP_MULT` (silence = this × longest pre-window gap) | 2.0 | `detection_time.py:113` | engineering default | `detection_time.py:26,39-40` | no |
| `LEDGER_FLOOR_MS` (ledger latency floor) | 1.0 ms | `detection_time.py:114`; `catch.py:50` | engineering default; **decision, not yet implemented** (relative floor) | `DETECTION_TIME.md:633` ("ledger 1 ms"); decision 27 (round 7, `PROTOCOL_DRAFT_20261002.md:298-299`) changes it to `max(statistical threshold, 10% of baseline median, clock resolution)` with a 5% sensitivity arm, ratified as decision 32 (`:318`) | no (same in both files; the replacement rule is not yet coded in either) |
| `LAT_FLOOR_S` (span latency floor) | 0.001 s (1 ms) | `catch.py:49`; `symptoms.py:64` | engineering default; **decision, not yet implemented** (same relative-floor replacement as `LEDGER_FLOOR_MS`) | `catch.py:25`; decisions 27/32 as above | no |
| `MEM_REL_FLOOR` (memory floor, share of baseline median) | 0.02 (2%) | `catch.py:52`; `symptoms.py:61` | engineering default (self-labelled) | `symptoms.py:61` inline: `"engineering default, see draft"` | no |
| `COUNT_FLOOR` / `BURST_FLOOR` (log/template count floor) | 2.0 | `catch.py:48`; `symptoms.py:65` | engineering default | `catch.py:25` | no |
| `SYS_FLOORS` (per-resource metric floors: `sys_cpu` 0.05 cores, `sys_io` 65,536 B/s, `sys_psi_cpu`/`sys_psi_memory`/`sys_psi_io` 1,000 stall-µs/s) | as listed | `research/lmt-pilot/lmt_detect.py:34` | **unknown** | none found beyond the units comment; see Summary, unknown item 2 | no |
| Comparator is inclusive (`>=`, never `>`) | boolean | `detection_time.py:128` (`INCLUSIVE`); `catch.py:20` | engineering default (cross-module convention) | `catch.py:20` ("Comparisons are inclusive (`>=`), as symptoms.py") | no |
| `PATH_FILTER` (a single-sample spike counts only on the affected call path) | boolean, True | `detection_time.py:129` | decision | round 4 decision 7, `research/protocol/OFFLINE_RESULTS_20261002.md:76-79` | no |
| `LOG_UPPER` / `LOG_HOLD_CAP` (whole-second log stamp timed at s+1, capped at hold end) | booleans, True | `detection_time.py:131-132` | engineering default | `detection_time.py:48-50` docstring | no |
| `WS_PER_CELL` (whole-second log rule decided per cell, not campaign-wide) | boolean, True | `sweep_analysis.py:160`; `:1125` | decision | review M1, cited inline at `sweep_analysis.py:1125` | n/a (Hotel only so far) |
| `GRID_K` × `GRID_FLOOR_MS` (K×floor robustness grid) | K ∈ {3,4,5}; floor ∈ {0.5,1,2} ms | `sweep_analysis.py:121-122` | decision | `PROTOCOL_DRAFT_20261002.md:106` (§3 "Robustness grid"), citing `otel-offpath/DECLARATION.md` erratum 1 and H4 | no |
| `REF` (reference grid point used for headline verdicts) | K=4.0, floor=1.0 ms | `sweep_analysis.py:123` | engineering default | comment "dbebcbb's setting", `sweep_analysis.py:123`; matches `K`/`LEDGER_FLOOR_MS` above | no |
| By-construction taxonomy, incl. `BC-caller-log` | rule set | `detection_time.py:61-68` | decision | round 4 decision 2, `OFFLINE_RESULTS_20261002.md:65-70`; extended to every fault class (not only stopping faults) by `AMENDMENT_3.md` item 2 | yes — caller-span variant `kind` (dbebcbb) vs `content` (primary since Amendment 3) are both computed, `content` primary |
| H8: both clocks computed, a P4 "win" must hold in event time **and** availability time | — | not implemented as a code constant | **decision, not yet implemented** | decision 34, `PROTOCOL_DRAFT_20261002.md:321`; `METHODOLOGY_HARDENING.md` row 8, H8 (§3) | n/a |
| H4: onset as an interval, P1's expected catch as an interval | — | not implemented (`P1_TOL_S` is still a point ± tolerance) | **decision, not yet implemented** | decision 36, `PROTOCOL_DRAFT_20261002.md:323-325`; `METHODOLOGY_HARDENING.md` row 10, H4 (§3) | n/a |
| H3: tie margin derived from measured timing uncertainty | — | not implemented (no margin constant exists) | **decision, not yet implemented** | decision 35, `PROTOCOL_DRAFT_20261002.md:322`; `METHODOLOGY_HARDENING.md` H3(b) (§3) | n/a |
| H11: restrict P3 to traffic-independent signals by mechanism | — | not implemented (`P3_TESTABLE`/`P3_RATES` still the originally declared set) | **decision, not yet implemented** | `METHODOLOGY_HARDENING.md` row 12, H11 ("Recommend restrict"); folded into round 8 but no numbered decision line names it explicitly | n/a |

## 2. False-alarm / admissibility

| name | value / unit | where it lives | origin type | origin reference | differs across systems? |
|---|---|---|---|---|---|
| `TAU` / `G3_TAU` (G3 admissibility share: inadmissible iff k > τ·n_eff) | 0.05 | `detection_time.py:109`; `catch.py:46`; `lmt_detect.py:36`; `protocol_gates.py:104,127`; `sweep_analysis.py:130` | **unknown** | labelled "provisional (PLAN_FABLE part 2)" at `protocol_gates.py:104`; deferred by decision 5 (`PROTOCOL_DRAFT_20261002.md:202`) to the scope mapping, which declined to set a value (`research/scope-20261002/SCOPE.md:316`, "no new value is argued here"); see Summary, unknown item 1 | no (same literal in all five files) |
| `G3_PER_RATE` (false alarms keyed by rate, never pooled across rates) | boolean, True | `sweep_analysis.py:161` | decision | `research/READING_20261003.md:67` (row 16), ratified as decision 16, `PROTOCOL_DRAFT_20261002.md:259` | n/a (Hotel only so far; design states the rule applies to all three) |
| `WINDOW_OVERRUN_S` (G3 no-fault window generation tolerance) | 1.0 s | `detection_time.py:115` | engineering default | `detection_time.py:54-56` docstring | no |
| H2: false-alarm rate reported per hour, compared at a matched operating point; ≤ 15/h is the most the current quiet time certifies | — | not implemented (current reporting is k/n windows per rate, leave-one-cell-out) | **decision, not yet implemented** | decision 33, `PROTOCOL_DRAFT_20261002.md:319-320`; `METHODOLOGY_HARDENING.md` §3 H2, with the 15/h arithmetic worked there | n/a |
| H7: common false-alarm operating point, K fitted per system from fault-free data (frozen K=4 kept only as the reference row) | — | not implemented (K is fixed at 4.0 for every system) | **decision, not yet implemented** | decision 31, `PROTOCOL_DRAFT_20261002.md:316-317`; `METHODOLOGY_HARDENING.md` §3 H7 | n/a |
| G3 (campaign-gate side), `n_eff = 0` fails, never reported admissible | boolean rule | `protocol_gates.py:90-92` | engineering default (shares `TAU` above) | `protocol_gates.py:101-104` | no (one vendored module, tested byte-identical across the three harnesses, `PROTOCOL_DRAFT_20261002.md:128-129`) |

## 3. Baseline

| name | value / unit | where it lives | origin type | origin reference | differs across systems? |
|---|---|---|---|---|---|
| Baseline window = the cell's own pre-onset data, per request/per sample | — | `detection_time.py:194-200` (`route_baselines`) | decision | "Ledger spread: per request (decision 9's rule)", round 4 decision 3, `OFFLINE_RESULTS_20261002.md:71`; `DECLARATION.md` "Ledger baselines: each cell's own pre-window per request (dbebcbb)" | no |
| H1: baseline pooled across same-rate quiet cells, cross-fitted, leave-one-cell-out for false alarms, n ≥ 20 required | — | not implemented; `detection_time.py:634` records the pooled baseline was explicitly **rejected** at declaration freeze ("The pooled no-fault baseline of brief A B9 was not adopted") before being re-decided | **decision, not yet implemented** (history: proposed in brief A item B9 → rejected at freeze → re-decided as H1) | decision 31, `PROTOCOL_DRAFT_20261002.md:316`; `METHODOLOGY_HARDENING.md` §3 H1, row 3 and row 1 of the "challenge" table (D2,D5,D6,D10,D13) | n/a |
| LOEO (leave-one-episode-out sensor selection for P4) | boolean, True | `sweep_analysis.py:158` | decision; scope narrowed by a later decision | `research/READING_20261003.md:65` (row 14), ratified as decision 16; narrowed to "Hotel only, none for TeaStore/OTel" by `METHODOLOGY_HARDENING.md` §2 row 14 (1 episode makes selection impossible there) | yes (Hotel only; TeaStore/OTel report descriptive per-sensor times, no selection) |
| Calibration boundary: no post-onset data of an evidence episode ever fits a scoring rule, with 3 declared exceptions (calibration runs, the H9 exploratory model, P4's LOEO selection) | — | not enforced as a single code invariant; achieved today only by construction (pre-window = `[t0, onset)`) | **decision, not yet implemented** as an explicit guard | decision 31; `METHODOLOGY_HARDENING.md` §3 H1 opening bullet, hardened across judge rounds v1→v6 (`:164-202`) | n/a |

## 4. Timing / onset

| name | value / unit | where it lives | origin type | origin reference | differs across systems? |
|---|---|---|---|---|---|
| Onset bound = the fault-receipt's pre-command stamp (never a post-command probe) | — | Hotel: `fault-receipt.startedMonotonic`; TeaStore: `measurementBarrier.scheduledOnsetSeconds`; OTel: `actualOnsetMonotonicOffsetSeconds` (`detection_time.py:17-24`) | decision (fixing defect F-ADH-085) | `detection_time.py:17` ("F-ADH-085: bounded by the scheduled command, never by a probe"); gate `F1`, `protocol_gates.py:72-75` | yes — different field per system, same rule |
| `FAULT_HOLD_SECONDS` (hold length) | 60 s | hotel `candidate_sweep.py:65`; teastore `:75`; otel `:97` | decision | `research/READING_20261003.md:53` (row 2), decision 16 | no (identical, 3 independent copies — see drift-risk table) |
| `FAULT_ONSET_BASE_SECONDS` + seeded stratified offset within one inter-arrival | 60 s + offset | hotel `:64,71-72`; teastore `:74`; otel `:96` | decision | `research/READING_20261003.md:54` (row 3), decision 16; approved for TeaStore/OTel (1 stratum = the whole inter-arrival) in `DECLARATION_TEASTORE.md`/`DECLARATION_OTEL.md` | yes in granularity (Hotel: 4 strata of one inter-arrival across its 4 blocks; TeaStore/OTel: 1 episode = the whole inter-arrival), no in the 60 s base |
| `ONSET_TOLERANCE_S` (F1 gate: onset within this of schedule) | 1.0 s | `protocol_gates.py:128` | upstream | "TeaStore's controller refuses an onset > 1 s late", `protocol_gates.py:105`, pointing to `performance_campaign.py:1938-1940` | no |
| `HOLD_TOLERANCE_S` | 1.0 s | `protocol_gates.py:129` | engineering default | `protocol_gates.py:106` | no |
| `P1_TOL_S` (positive-control tolerance) | 0.5 s | `sweep_analysis.py:128` | decision; **flagged for replacement** | `DECLARATION.md` Predictions, P1; H4 (`METHODOLOGY_HARDENING.md` row 10) calls ±0.5 s "shorter than the gap between requests at ≤ 1/s" and not yet replaced by an interval tolerance (decision 36) | n/a (Hotel only) |
| `P2_DOBS_S`, `P2_EPS` (P2 slope bound: failed ≤ 1 + rate·`P2_DOBS_S` + `P2_EPS`) | 1.0 s, 2.0 | `sweep_analysis.py:129-130` | decision | `DECLARATION.md` Predictions, P2; ε drafted as "e.g. 1 request" in brief 5e (`research/decisions-20261003/B_OBJECTIVE_MEASUREMENT.md:363`), frozen at 2 in the declaration itself | n/a (Hotel only; TeaStore/OTel P2 restated with their own timeout in their declarations) |
| `P4_MIN` (wins needed, of 4 paired episodes) | 3 | `sweep_analysis.py:134` | decision; **flagged for replacement** | `DECLARATION.md` Predictions, P4; `research/READING_20261003.md:63` (row 12), decision 16; H3 (`METHODOLOGY_HARDENING.md` row 13) notes p=0.31 at 3/4 and recommends a matched-false-alarm-rate comparison instead (not yet coded) | n/a (Hotel only; 1-episode TeaStore/OTel report descriptive, no win criterion) |
| `P3_CADENCE_S` (sampling-cadence tolerance: M ≈ 3 s, S = 5 s) | {"M": 3.0, "S": 5.0} | `sweep_analysis.py:131` | measured + decision | cadence measured from the harness's own sampler interval (`DECLARATION.md` "Sampling: cgroup sampler 5 s, docker stats as before"; TeaStore's `SYSTEM_SAMPLE_INTERVAL_SECONDS = 5.0`, `candidate_sweep.py:126`); the "+ one cadence" rule itself is decision 16 row 11 | yes — OTel's metric cadence is the OTLP SDK default (~60 s observed, unchanged), making its own P3 tolerance 60 s instead of 3-5 s (`DECLARATION_OTEL.md` "Metric export interval unchanged") |
| `P3_TESTABLE` / `P3_RATES` (declared testable (regime, family) set, from 10/s evidence) | 2 cells; rates {10, 0.05} | `sweep_analysis.py:132-133` | decision | `DECLARATION.md` Predictions, P3 ("Testable set (from the 10/s evidence): ...") | n/a (Hotel only) |
| Log time = Docker receive stamp (a receipt-time proxy, not write time); per-line receipt delay is a measured bound | boolean `DOCKER_STAMP`, True | `sweep_analysis.py:154`; `detection_time.py:48-51` | decision (keep, relabelled); **measurement not yet computed** | `METHODOLOGY_HARDENING.md` row 7 ("keep, labelled as receipt time"); the per-line delay bound for the H3(b) margin is declared but not computed anywhere in the scripts found | no |
| Episode/cell-order shuffle seed | `20261003` | `DECLARATION.md` "seed 20261003"; `DECLARATION_TEASTORE.md`, `DECLARATION_OTEL.md` (same literal) | engineering default (the freeze date, reused deliberately for reproducibility, not drift) | declaration text itself | no (same literal by design, not an accidental duplicate) |
| `SEEDS` (Monte Carlo seeds per (cell, thinning fraction), offline traffic-thinning analysis) | 200 | `detection_time.py:122` | engineering default | `detection_time.py:73` docstring | no |
| `THIN_P` (traffic-thinning grid) | (1.0, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001) | `detection_time.py:121` | engineering default | exploratory; no decision cited beyond the general thinning analysis described at `detection_time.py:71-83` | no |

## 5. Campaign design

| name | value / unit | where it lives | origin type | origin reference | differs across systems? |
|---|---|---|---|---|---|
| `RATES` (request rates swept) | (10.0, 1.0, 0.2, 0.05) req/s | `sweep_analysis.py:115`; hotel `candidate_sweep.py:59`; teastore `:69`; otel `:75` | decision | `research/READING_20261003.md:52` (row 1: "spans the ledger's thinning knee ... goes past the sampler's 5 s"), ratified as decision 16 | no (identical; 4 independent literal copies, see drift-risk table) |
| `WARMUP_SECONDS` @ 10/s for every rate | 30 s | hotel `:60-61`; teastore `:71-72`; otel `:93-94` | decision | `research/READING_20261003.md:53` (row 2) | no |
| `MEASUREMENT_SECONDS` | 180 s | hotel `:63`; teastore `:73`; otel `:95` | decision | `research/READING_20261003.md:53` (row 2) | no |
| `EPISODES` (blocks per (regime, rate)) | Hotel 4; TeaStore 1; OTel 1 | hotel `:78`; teastore `:87`; otel `:115` | decision | Hotel: `research/READING_20261003.md:55` (row 4), decision 16; TeaStore/OTel: shakedown scope, `BUDGET_REPLICATION.md` "1 block (one cell per regime × rate)" | **yes** |
| `REQUEST_TIMEOUT_SECONDS` (client per-request timeout) | Hotel 1.0 s; TeaStore 15.0 s; OTel 15.0 s | hotel `:76`; teastore `:82`; otel `:109` | upstream (each system's existing client default, reused) | Hotel: "the frozen epoch's per-request client timeout" (`:76` comment); TeaStore: "`fixed_load.py`'s `--timeout` default" (`:82` comment, `DECLARATION_TEASTORE.md`); OTel: "the harness's own per-request timeout" (`DECLARATION_OTEL.md`) | **yes** |
| `CONCURRENCY` (open-loop worker pool) | Hotel 16; TeaStore 240 = ⌈1.6×10×15⌉; OTel 300 = ⌈2×10×15⌉ | hotel `:77`; teastore `:85-87` (`CONCURRENCY_MARGIN=1.6`); otel `:113-114` (`CONCURRENCY_MARGIN=2`) | decision (the margin-ratio rule); derived arithmetic per system | Hotel's 1.6× margin set by `research/READING_20261003.md` design; reused for TeaStore (`DECLARATION_TEASTORE.md` "Hotel's margin ratio"); OTel doubled it to 2× citing its own open-loop rule "`DESIGN.md` L1 ... worker cap ≥ rate × timeout" (`DECLARATION_OTEL.md`) | **yes**, both the margin ratio (1.6× vs 2×) and the resulting pool size |
| Fault set and targets | Hotel: search-pause / profile-cpu-throttle(0.1) / rate-net-delay(100 ms); TeaStore: auth-freeze / persistence-cpu-throttle(0.1) / net-delay **omitted**; OTel: frontend-pause / productcatalog-cpu-throttle(0.1) / net-delay **omitted** | `DECLARATION*.md` "Regimes" | decision (fault choice and target mapping); upstream (the 0.1/100 ms magnitudes, reused unchanged) | Hotel: `research/READING_20261003.md:56` (row 5); TeaStore/OTel mappings: round 6 decision 23 "accept all" (`PROTOCOL_DRAFT_20261002.md:274`); net-delay omission: no passwordless sudo on srv5/srv6, recorded as a declared limit in both declarations | **yes** — net-delay present on Hotel only; targets differ per SUT's architecture |
| CPU-throttle magnitude | `--cpus 0.1` | all three declarations | upstream (Hotel's pre-existing `profile` fault, reused unchanged) | `research/READING_20261003.md:56` ("profile uses ~0.03 cores at 10/s"); see Summary, unknown item 4 for why 0.1 and not another dose | no |
| Net-delay magnitude (Hotel only) | 100 ms | `DECLARATION.md:32` | upstream (reused from the earlier LMT pilot) | `DETECTION_TIME.md:623` ("Configured netem delay ... 100 ms on lmt2/sel1, `lmt_faults.py:37`") | n/a (Hotel only) |
| Trace-completeness drain margin | 2.0 s, added to the request timeout | Hotel `TRACE_DRAIN_MARGIN_SECONDS`, `candidate_evidence.py:60`; TeaStore `DRAIN_ALLOWANCE_MARGIN_SECONDS`, `candidate_sweep.py:120`; OTel `TRACE_DRAIN_MARGIN_SECONDS`, `candidate_sweep.py:188` | decision | decision 25, `PROTOCOL_DRAFT_20261002.md:280-288`; TeaStore's Q3 brief fixed the margin at 2 s first (`AMENDMENT_TEASTORE_1.md`), then decision 25 generalised it to all three | no (same 2.0 s; **effective total drain differs**: 3.0 s for Hotel's 1 s timeout, 17.0 s for TeaStore/OTel's 15 s timeout) |
| Trace-completeness allowance share / minimum | max(1, 1% of successful requests) | Hotel `TRACE_INCOMPLETE_PERCENT=1` int percent (`candidate_evidence.py:61-62`); TeaStore `TRACE_INCOMPLETE_FRACTION=0.01` (`candidate_sweep.py:125`); OTel `TRACE_INCOMPLETE_ALLOWANCE_SHARE=0.01`/`_MINIMUM=1` (`candidate_sweep.py:190-191`) | decision | decision 25, `PROTOCOL_DRAFT_20261002.md:280-288` | no (same decided share; two different numeric encodings, see drift-risk table) |
| OTel's superseded trace rule (M1: block below 99% share, pooled) | 99% | `DECLARATION_OTEL.md` "Trace completeness" | decision, **superseded** | round 6 decision 23 ("M1 99%", `PROTOCOL_DRAFT_20261002.md:276-277`); replaced by decision 25 for the relaunch (`AMENDMENT_OTEL_1.md` §1) | historical only; no longer in effect |
| TeaStore `POST_RECOVERY_ALLOWANCE_SECONDS` (R2.recovery window derivation) | 2.0 s | teastore `candidate_sweep.py:116` (sibling worktree `observability-placement-runtime-teastore-protocol`) | measured | "the frozen auth-freeze receipts show 0.44-0.60 s from the last hold sample to readiness (n = 28, campaigns #12-#15 and the srv6 partial run); 2 s = Hotel's allowance" (inline comment) | n/a (TeaStore only) |
| OTel loadgenerator removed after `up`, before readiness | mechanism | `DECLARATION_OTEL.md` "Upstream loadgenerator OFF" | decision | C_HARNESS_INFRA finding #10 (`research/decisions-20261003/C_HARNESS_INFRA.md`), applied in `DECLARATION_OTEL.md` | n/a (OTel only; it runs in every earlier OTel cell, so OTel sweep costs are not poolable with v3/offpath evidence) |
| OTel frontendproxy memory limit | 50 MiB (upstream) → 256 MiB (sweep epoch only) | `AMENDMENT_OTEL_1.md` §2; compiled timing `serviceMemoryLimitBytes` | measured, with an arithmetic margin | kernel OOM-kill evidence at 11:46:59Z/11:59:31Z on fb14srv6 (`AMENDMENT_OTEL_1.md` §2), sized to ~1.6× the worst-case estimated requirement | n/a (OTel-only deviation; Hotel/TeaStore keep upstream defaults) |
| OTel per-cell container-health guard (OOMKilled / restart / limit-applied check) | boolean gate | `AMENDMENT_OTEL_1.md` §3 | decision | user's option-A decision plus decision 25, `AMENDMENT_OTEL_1.md` header | **yes** (OTel-only; Hotel/TeaStore have no equivalent guard) |
| Campaign wall budget | Hotel 21,600 s (6 h, derived from the plan); TeaStore/OTel 3 h window (derived) | `BUDGET.md`; `DECLARATION_TEASTORE.md`/`DECLARATION_OTEL.md` "Binding" | engineering default (derived from plan length) | `BUDGET.md` "the campaign's own window is 6 h (21,600 s, derived from the plan)" | yes (window size scales with plan size) |
| Kill date / relaunch cap | 2026-10-06 12:00Z; at most 2 relaunches per SUT | `BUDGET.md` rules 1,4; `BUDGET_REPLICATION.md` | decision | user, 2026-10-03, "we will get there in 3 days; if not we readjust" (`BUDGET.md` header) | no (same rule for all three; Hotel's 3rd relaunch under decision 25 needed an explicit override, `AMENDMENT_2.md`) |
| Disk guard: campaign blocked below 40 GB free | 40 GB | launcher guard (project rule) | engineering default | `CLAUDE.md` "Hosts and campaigns": "Disk is a silent campaign blocker (a launcher guard refuses below 40 GB free)" | no |
| "Blocked" cells preserved, not fatal, unless ≥3 blocked with 0 valid; vs. "invalid" cell stops the runtime immediately | two distinct stop thresholds | `CLAUDE.md` "Gates" section; `BUDGET.md` rule 3 | decision (project-level rule) | `CLAUDE.md`: "Blocked cells are preserved and flagged, not fatal. A launcher stops only on >=3 blocked with 0 valid."; `BUDGET.md` rule 3: "the runtime stops on the first invalid cell" | no — same two rules apply to all three sweeps; "blocked" (capture-level) and "invalid" (gate failure) are different concepts, not a contradiction |

## 6. Gates

| name | value / unit | where it lives | origin type | origin reference | differs across systems? |
|---|---|---|---|---|---|
| `FLOOR`, `PRE_FAIL_MAX`, `SCOPE_MIN` (G1/G2/G4 thresholds: ⌈0.5×rate×s⌉ opportunities, ≤5% failure share, ≥95% record coverage) | 0.5, 0.05, 0.95 | `src/obsplacement/protocol_gates.py:123-125`; source `research/visibility-map/traffic_gate.py:44-46` | decision | `PROTOCOL_DRAFT_20261002.md:115-125` (§4 "Gates, generic and parameterised by the profile") | no — one module vendored byte-identically into all three harnesses, with a test enforcing the copies match (`PROTOCOL_DRAFT_20261002.md:128-129`) |
| `SCOPE_SLACK_S` (records within this of the measurement window still count as inside) | 5.0 s | `protocol_gates.py:126` | engineering default | `protocol_gates.py:103`, citing `traffic_gate.py:157-159` | no |
| `G1_MIN_DISPATCHED` (G1 also requires ≥1 actual start in the window, not just scheduled opportunities) | 1 | `protocol_gates.py:132` | decision, **flagged open** | `protocol_gates.py:82,108`: "deviation from draft 3's wording, flagged for the user"; an addition beyond `PROTOCOL_DRAFT_20261002.md` §4's literal text, made at review 2026-10-02 | no |
| `RECOVERY_WINDOW_S`, `RECOVERY_P50_RATIO` (R2.recovery, non-blocking) | 60.0 s, 1.5× | `protocol_gates.py:130-131` | engineering default (self-labelled "non-blocking, so not preregistration-class") | `protocol_gates.py:107` | no |
| `ONSET_TOLERANCE_S` (F1: onset within this of schedule) | 1.0 s | `protocol_gates.py:128` | upstream | see Timing/onset table above | no |
| `HOLD_TOLERANCE_S` | 1.0 s | `protocol_gates.py:129` | engineering default | `protocol_gates.py:106` | no |
| `TAU` (gate-side G3 share) | 0.05 | `protocol_gates.py:104,127` | **unknown** | see Summary, unknown item 1 | no |
| Campaign stop rule: stop and ask the user on the first invalid cell | boolean | `protocol_gates.py:98-99`; `BUDGET.md` rule 3 | decision | `PROTOCOL_DRAFT_20261002.md:126` ("Campaign stop: stop and ask the user on the first invalid cell (replaces three different abort rules)") | no |

## 7. Placement

| name | value / unit | where it lives | origin type | origin reference | differs across systems? |
|---|---|---|---|---|---|
| CELF retained as the optimiser; objective reframed to detected/not, time-to-detection, impact-before-detection | — | `research/PROTOCOL_DRAFT_20261002.md:236-248` | literature | Leskovec et al., *Cost-effective outbreak detection in networks*, KDD 2007 (named directly in the protocol, predates the `LIT_*.md` catalogue) | n/a |
| Misses charged at the hold end (= Leskovec's min{t, T_max}, restricted mean survival time) | — | `detection_time.py` docstring and every TTD computation | decision; literature-grounded | decision 15, `PROTOCOL_DRAFT_20261002.md:249-251`; kept per `METHODOLOGY_HARDENING.md` row 9, citing D30-D35 and M1 §5.7 | no |
| The submodularity gap: CELF's (1−1/e) bound covers detection-probability/time-saved, not detection time itself | — | motivates the whole detection-time analysis | literature | Heavey et al., AAAI 2022, cited at `PROTOCOL_DRAFT_20261002.md:252-253` and `DECLARATION.md` "Question" | n/a |
| CELF / enumerated placements, D3 probabilistic detection, D4 max-min, D5 labels | — | **not computed** | decision, exploratory | `sweep_analysis.py:1156-1157` ("Not computed: CELF / enumerated placements, D3 probabilistic detection, D4 max-min, D5 labels (exploratory in `[D]`)") | n/a |
| H5: exposure recorded per (sensor, fault, episode); objective unchanged (misses still charged everywhere) | — | **not implemented** | **decision, not yet implemented** | `METHODOLOGY_HARDENING.md` §3 H5 | n/a |
| H6: pessimistic/optimistic CELF placement bounds (unseen = 0 vs unseen = best rate of its channel×role class) | — | **not implemented** | **decision, not yet implemented** | `METHODOLOGY_HARDENING.md` §3 H6 | n/a |
| D4: compare the expected objective against a robust/dropout (max-min) variant | — | **not implemented** | **decision, not yet implemented** | decision 36, `PROTOCOL_DRAFT_20261002.md:323-325` | n/a |
| H9: hierarchical probabilistic detection model; prior for an unseen sensor starts at the miss penalty, reduced by neighbouring-edge evidence | — | **not implemented**, exploratory/next-paper | **decision, not yet implemented** | decision 38, `PROTOCOL_DRAFT_20261002.md:328-330`; `METHODOLOGY_HARDENING.md` §3 H9 | n/a |
| By-construction catches excluded from P4 candidate pool, never from the ledger baseline | — | `detection_time.py:61-68`; `sweep_analysis.py` P4 scoring | decision | round 3 decision 11, `PROTOCOL_DRAFT_20261002.md:214-217` | no |
| `G2` own-sensor exclusion (target's own sensors reported apart from "outside" placement credit) | — | `detection_time.py:59-60` | decision | round 3 decision 11, `PROTOCOL_DRAFT_20261002.md:214-217` | n/a (OTel's target is its entry service, so its ledger counts as the target's own sensor there, `detection_time.py:59-60`) |

---

## How to read "decided, not yet implemented"

Ten items above (H1 n≥20/pooled baseline, H2 false-alarms/hour, H3 matched-rate P4, H4 onset interval, H7 per-system
fitted K, H8 two-clock win, H9 probabilistic prior, H11 P3 restriction, D4 robust/dropout comparison, H5/H6 exposure
and placement bounds) were decided by the user in round 8 (`PROTOCOL_DRAFT_20261002.md:315-336`, 2026-10-04) on the
strength of `METHODOLOGY_HARDENING.md`'s literature review and a six-round judge check (v1→v6, 4/11 → 10/11 criteria,
`METHODOLOGY_HARDENING.md:162-211`). None of them is yet a constant in `detection_time.py` or `sweep_analysis.py`:
both files' timestamps (2026-10-03/04 00:20-00:22) predate the round-8 decisions (~08:30Z-20:00Z on 2026-10-04). The
order of work for implementing them is itself decided: `METHODOLOGY_HARDENING.md` §4, "v2 implements H1-H5, H8, rows
15 and 19 ... regenerated into a new directory ... frozen before any TeaStore or OTel cell is read."
