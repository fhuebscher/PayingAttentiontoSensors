# Campaign F replication 1 (attempt 3, OTel off-path faults): result (2026-10-15)

Scope: **instance** (OTel Demo 1.12.0, fb14srv6, 25 req/s of the upstream mix, 5 blocks, n = 2 test episodes per class). One replicate, analysed alone; it is not pooled with F.
F's numbers are copied from `research/placement/test-f/RESULT_F.md` and `otel-f.json`; the replicate's from the files named below (all committed unedited; the readouts, scorer and lanes output were committed before they were read; the fresh-false-alarm tables were seen on stdout first, deviation 6).

- Declarations: `DECLARATION_F_OTEL.md` (`8845721`), `DECLARATION_F_OTEL_REP1.md` (`d0ef902`), `DECLARATION_F_OTEL_REP1_RELAUNCH1.md` (`7f4382e`). Harness `715d57b`, plan `56bdaa62c41555957004a6264026282afad16272b92abe5377b51a5e7f345c94`
  (attempt 3, 25 cells). Predictions FR1-* `PREDICTIONS_OVERNIGHT_20261014.json` (`8b89d43`), committed before attempt 3 launched.
- Run: terminal `remote-terminal.json` attempted 25, valid 25, stopped false. Fetched to `tmp/otel-f-evidence/f3-fetch2/x`, 437/437 byte-verified (host manifest, re-checked locally, 0 mismatches).
  Offline terminal replay at `715d57b`: `terminal-replay-f3.json`, verdict `pass`, 25 of 25 valid (`ce71bb8`; exact command in the commit message).
- Chain (frozen v3.3, run order `RUN_ORDER.md` with f3 names): training readout `186c34b` (15 of 15 valid, `campaignsRead` one entry; determinism pre-check: `calibration` blocks equal), placement `95a011d`
  (sha256 `674580e08353e667ea32d587091fc38327db6d68e1d3f2142fdd94c9e433b606`, F's is `ce6bfc1b...`), freeze entry `0a6f52f`, scoring readout `063be58` (25 of 25 valid), scorer `d3224e6`
  (`otel-f3.json`, under the recorded pin override; F's pin unchanged), post hoc lanes `47a3f15` (decision-73 rerun equals `placement-f3.json`), fresh false alarms `2e5d517` and `fa7a17f`,
  predictions scored `849be21`. Python 3.13.12.

## Verdicts (the preregistered rule; `otel-f3.json`, `rates.25.verdicts`)

| class | set | F | replicate (attempt 3) |
|---|---|---|---|
| frauddetectionservice pause | `frontier (effort<=any, runtime<=any) @6/T_r` | PASS (g = 42.05 s, 2 of 2 improved) | PASS (g = 53.655 s, 2 of 2 improved) |
| accountingservice pause | same | PASS (g = 53.23 s, 2 of 2 improved) | PASS (g = 58.5469 s, 2 of 2 improved) |

Unrounded g, replicate: fraud 53.654993411153555, accounting 58.546938721090555 (F: 42.04993839934468, 53.227133959531784).

## Frozen set

| | F | replicate |
|---|---|---|
| `@6/T_r` set | `metric:kafka:kafka.consumer_group.lag` (1 sensor) | `metric:kafka:kafka.purgatory.size` (1 sensor) |
| `@3/T_r` set | `metric:kafka:kafka.request.count` (1 sensor) | `metric:kafka:kafka.purgatory.size` (same set as `@6/T_r`) |
| training price of the `@6/T_r` sensor | 15.81 /h (budget 6/T_r = 20.0 /h, T_r = 0.30 h) | 9.99 /h (9.985774245179966; budget 20.0 /h, T_r = 0.30 h) |
| training price of `kafka.consumer_group.lag` / `kafka.request.count` / `kafka.purgatory.size` (`placement-*.json`, `rates.25.costs`) | 15.81 / 9.99 / 9.99 | 35.04 / 15.81 / 9.99 |
| set-level D(S), D(ledger), g over all 6 test episodes | 4.73, 36.49, 31.76 | 2.77, 40.17, 37.40 |
| episodes detected by the set | 6 of 6 | 6 of 6 |

The two placements differ (sha256 above); the replicate's frozen set does not contain the lag sensor. In the replicate the lag ids are armed (2 ids) and `kafka.consumer_group.lag` is priced 35.04 /h, above the 20 /h budget.
The post hoc zero-alarm row of the replicate (`out-f3-posthoc`) gives the same `@3/T_r` and `@6/T_r` set and the same g as decision 73.

## Test episodes (`otel-f.json` / `otel-f3.json`, `rates.25.episodes`; seconds after the pause command's pre-command stamp; "miss" = no counted fire in the 60 s hold)

| test episode | F: ledger alone | F: frozen `@6/T_r` set | replicate: ledger alone | replicate: frozen `@6/T_r` set |
|---|---|---|---|---|
| accounting, block 4 | miss | 4.51 | miss | 1.59 |
| accounting, block 5 | miss | 9.16 | miss | 1.44 |
| fraud, block 4 | 38.12 | 4.77 | miss | 1.15 |
| fraud, block 5 | miss | 9.31 | miss | 11.65 |
| frontend, block 4 | 0.35 | 0.35 | 0.40 | 0.40 |
| frontend, block 5 | 0.31 | 0.31 | 0.37 | 0.37 |

In the frontend (on-path control) episodes the frozen set's time equals the ledger's in both runs, so no frontend episode improves (0 of 2 in both; the class has no pass rule).

## Lane predictions (post hoc script, not a verdict; `research/lanes/out-f3-posthoc`, F: `out-f-posthoc2`)

| id | F | replicate |
|---|---|---|
| F-L1 own silence (by-construction field) < 2.0 s | hit, 0.84-1.52 s, 4/4 | hit, 0.95-1.18 s, 4/4 |
| F-L2 coordinator counted fire 42-47 s in 4/4; none in the 2 frontend episodes | hit, 43.3-44.0 s | hit, counted 42.94-43.79 s, 4/4; frontend none in either field. One episode (accounting, block 5) also has a by-construction fire at 26.00 s |
| F-L3 lag armed, fires before the coordinator in >= 3/4 | hit, 4.5-9.3 s | hit, 4.38-9.40 s in 4/4 (the lag ids, which are not the frozen set) |
| F-M placeable non-flagd metric ids | hit, 236 SDK + 44 spanmetrics-derived | hit, 236 SDK + 44 spanmetrics-derived |

## Fresh false alarms on the held-out no-fault cells (POST HOC; frozen v3.3 reader's `--validation` path; calibration byte-equal to the training readout in both runs)

4 cells (`r25-b04-16-full`, `r25-b04-17-full`, `r25-b05-21-full`, `r25-b05-22-full`), 0.2000 h. Union of the sensor's 3 rules; 95 % Poisson upper bound per hour; "training" = the sensor's honest training bound.

| set checked | sensor | alarms | upper /h | training /h | source |
|---|---|---|---|---|---|
| F: `@6/T_r` | `kafka.consumer_group.lag` | 0 | 14.98 | 15.81 | `0790f24` (F's cells) |
| F: `@3/T_r` | `kafka.request.count` | 2 | 31.48 | 9.99 | `0790f24` (F's cells) |
| F's `@6/T_r` set on the replicate's cells | `kafka.consumer_group.lag` | 0 | 14.98 | 35.04 | `fresh-fa-f3/` |
| F's `@3/T_r` set on the replicate's cells | `kafka.request.count` | 0 | 14.98 | 15.81 | `fresh-fa-f3/` |
| the replicate's own frozen set (`@6/T_r` = `@3/T_r`) | `kafka.purgatory.size` | 1 (`spike`; `run3` 0, `median` 0) | 23.72 | 9.99 | `fresh-fa-f3-own/` |

The replicate's own frozen sensor raised 1 alarm in 0.2 h (5.00 /h observed); its 95 % Poisson upper bound (23.72 /h) lies above the 6/T_r budget of 20.0 /h and above its training bound of 9.99 /h. Not an equivalence test; n = 4 cells, 0.2 h.

## FR1 predictions (`PREDICTIONS_SCORED.md/.json`, by each prediction's declared rule)

FR1-L1 hit, FR1-L2 hit, FR1-L3 hit (lag fires in the stated 3-15 s band in 4/4), FR1-M hit, FR1-V1 hit (the set holds `metric:kafka:kafka.purgatory.size`), FR1-V2 hit (PASS), FR1-V3 hit (PASS),
FR1-V4 hit (0 of 2 frontend episodes improved), FR1-V5 hit (1 alarm for the replicate's own `@6/T_r` set, <= 4).
Ontology items (`research/ontology/compare.py` rules, scored one by one): fraud row: own disagree, coordinator agree, lag disagree, class agree, window disagree (predicted [45, 45] s, measured 42.94-43.33 s), entry-reached agree.
Accounting row: own disagree, coordinator agree, lag disagree, class agree, window disagree (measured any-field range 26.00-43.78 s; counted 43.78-43.79 s), entry-reached agree.
Frontend row: coordinator agree, class agree, window agree (none predicted, coordinator silent), entry-reached agree; own and lag not comparable (the post hoc output has no own or lag row for the frontend episodes).
Compared with the prior comparison on F attempt 1, the fraud-row entry-reached item is `agree` here (the ledger alone had no counted fire in the 2 fraud episodes; in F it fired in one).

## What this does and does not say
- Scope: instance. n = 2 test episodes per class, one host, one rate, one SUT, one replicate. Under the preregistered rule both off-path classes pass in F and in the replicate.
- The frozen `@6/T_r` set differs between F and the replicate (a different sensor, a lower training price); the PASS rests on a different sensor in each. The design does not say why the set differs.
- In all four replicate off-path episodes the ledger alone has no counted fire in the 60 s hold; in F it had one of four.
- The two no-fault cells per block are siblings in leave-one-cell-out calibration (fold false-alarm estimates optimistic), as in F.
- Fresh false alarms of the replicate's own set: 1 alarm in 0.2 h, upper bound 23.72 /h against a training bound of 9.99 /h; 0.2 h is too short to separate the two.
- The scorer's generated `otel-f3.md` is headed "Campaign E test scoring" and names E's no-fault cells (labels inherited from v3.2; not edited). `fresh_fa_f.md` names F and `RESULT_F.md` in its heading; its rows are the replicate's.

## Deviations (recorded; none changed a computation)
1. **Attempt 2 stopped** after 13 cells (12 valid) at 15:45:21Z on 2026-10-14: cell 13 invalid, `opensearch` container unhealthy at stack start (classified an infrastructure flake in `7f4382e`). Attempt 3 is the one relaunch the budget allows. Attempt 2 launched before the predictions commit `8b89d43`; it is not read and not scored here. Its evidence (`f2-fetch`, `f2-fetch2`) was never passed to a reader by this worker.
2. **Fetch directory:** the declaration names `tmp/otel-f-evidence/f3-fetch`; that fetch was interrupted by a VPN drop (rc 255), is kept unverified and unused. The analysis reads `tmp/otel-f-evidence/f3-fetch2/x` (case `otelF3b`, 437/437 byte-verified). `scratchpad/gate-drivers/fetch_overnight.sh` carries the `otelF3b` case uncommitted and was not edited here. Recorded in the freeze entry `0a6f52f`.
3. **Frozen digest table:** exactly the one expected line differs (`score_test_v3_3.py`, pre-pin digest in the table, F's post-pin file installed).
4. **`fresh_fa_rep.py` refused attempt 3** (it hard-codes `ATTEMPT = 2`; refusal verbatim: `refusing: cell r25-b04-16-full is attempt 3 of 'otel-offpath-f-v1', not attempt 2 of otel-offpath-f-v1 (not the replicate)`; no output created). A new file `fresh_fa_rep_f3.py` (`310580c`, ATTEMPT = 3 and f3 default paths, nothing else; the original is untouched) was committed before it ran. It has no planted-defect test of its own. The second fresh-false-alarm run (own set) was given explicit `--farm` and `--readout-dir` paths because the defaults were taken by the first.
5. **Terminal replay command:** F's exact replay command was not recorded; the replay here is the `candidate_terminal.py` CLI of the `715d57b` worktree (command in `ce71bb8`), run under `uv run python -I` 3.13; a scratch run under `/usr/bin/python3` 3.9.6 `-I` with a fresh bytecode cache prefix gave a byte-equal output.
6. The stdout tails of the two fresh-false-alarm runs (the last table rows) were visible when each run ended, before its output was committed (the files are committed unedited). The first run's tail showed the `@3/T_r` rows; the second run's tail showed `kafka.purgatory.size` rows.
7. `score_rep.py`, `fresh_fa_rep_f3.py` and `score_predictions_fr1.py` have had no independent review; `score_predictions_fr1.py` has no test. The commits carry `Co-Authored-By: Claude Sonnet 5.5` (the run order text names Opus 5.5).
8. No independent review of this note (no judge call; the judge server did not connect in this session, no adversarial-review subagent was run).

## Review corrections and caveats (same-provider adversarial review, 2026-10-15; every number confirmed)
- **The frozen sensor is not specific to the off-path faults.** `metric:kafka:kafka.purgatory.size` also has counted `run3`/`median` fires (direction up) in
  5 of 5 replicate frontend-pause episodes (test blocks: 12.01 and 11.13 s) and in 5 of 5 in F (11.63-11.92 s). The frontend class shows 0 of 2 improved
  only because the ledger fires first (0.37-0.40 s), so FR1-V4's hit follows from the ledger's timing, not from the sensor's specificity.
- **Why the sets differ, as counts:** in F's readouts `purgatory.size` (9.99/h) has 0 fires of any kind in all 10 off-path episodes; in the replicate it has
  a counted down fire in 10 of 10. Consumer-group lag's price rose from 15.81/h (F) to 35.04/h (replicate), above the 20/h budget; the lag ids still fire in
  4 of 4 replicate off-path test episodes (4.38-9.40 s). Both frozen sets are one `metric:kafka:*` id, and the ids differ. Scope: instance (one replicate).
- **FR1-V2 and FR1-V3** are hits by their rule (PASS), but their "implied by F" clause did not hold: it expected a broker metric firing at 4.5-9.3 s and the
  ledger firing in 1-2 of 4 off-path test episodes; measured 1.15-11.65 s from a different id, ledger 0 of 4.
- **Launch:** the launcher log says `WARN: not under caffeinate` although the declared command uses `nohup caffeinate -i` (not recorded before).
- **Replay:** the terminal replay is `canonical: false`, `maximumEvidenceLabel: candidate-evidence`.


## Same plan, checked (POST HOC, 2026-10-15)
`onsets_f1_vs_f3.py` reads both byte-verified execution packages (`f1-fetch`, `f3-fetch2`): the 25 cells of attempt 1 and attempt 3 have the same order
(ordinal, cell path) and the same `faultOnsetSeconds` and phase offsets, 25 of 25 (`onsets_f1_vs_f3.json`, `identicalOrderAndOnsets: true`). The compiler
draws onsets from (seed, epoch, strata, regime label, rate, block) and the order from (seed, epoch, block), not from the attempt
(`candidate_offpath_f.py`, `onset_phase_offset`, run order). Run IDs differ. Raised by a cross-provider review (gpt-6.1-sol, `eval_e5b3c8f2…`), which
found the claim unsupported by the evidence it was given.
