# TeaStore off-path pause (recommender), replication 2 on the barrier-fixed harness: result (2026-10-15)

Scope: **instance** (TeaStore at 34b37f7, fb14srv5, login-only workload at 10 and 1 req/s, 5 blocks; 10 recommender-pause episodes, 10 auth-freeze, 10
no-fault). No placement verdict was declared for this epoch; it measures lanes against predictions stated before launch. Every number below is copied from
the committed file named beside it.

- Declaration `DECLARATION_TEASTORE_OFFPATH_REP2.md` (`5b9236f`); `DECLARATION_TEASTORE_OFFPATH.md` (`f40e786`) stays binding for everything not changed
  there. Predictions `research/protocol/PREDICTIONS_OVERNIGHT_20261014.md/.json` (`8b89d43`, ids TSR-*), committed before launch.
- **What changed against relaunch 1:** harness `04254228aba90566dfeca603dfcc7b05b7d8d2e3` (relaunch 1: `f74b29b`). The Kieker-queue barrier acknowledgement
  re-queries the queue every 1 s until it reads empty, starting no probe that would complete later than 5 s after the barrier, and records every probe in
  `queue-proof.json` (`measurement.barrierProbes`); a queue still non-empty at the bound stops the campaign (declaration, section "What changed"). Plan
  `5a8e385e` and descriptor `127e8263` are unchanged. Setup ID `cbe9920a4b95f47d60054186641e754c`.
- Run: fb14srv5, 30/30 valid; the runtime journal's first `valid` record is 2026-10-14T15:23:41Z and its last 18:17:32Z. Host terminal validation `pass`, 30 of
  30, no blockers (`campaign-terminal-validation.json` sha256 `2d27626a92d4da40885d3cdd373b35acfa6632271b6861aada639af9db1a986d`, `terminal-replay-rep2.json` field `hostTerminalValidation`). Fetch 667/667
  byte-verified (`tmp/teastore-offpath-evidence/rep2-fetch`).
- Offline replay under `/usr/bin/python3` 3.9 with a cleared Apple bytecode cache: `terminal-replay-rep2.json` (`a66b6de`, sha256 `4ecffc5545d69c673d6b9997e4a4afff5caec2e36f6070f32045a693fcc9b8ae`), driver
  `replay_ts_rep2.py` (`95a027d`). 30/30 cells replay to `pass`; 10 byte-equal to the retained report, 20 differ only in
  `/validationTable[]/observation/path`; the campaign-level byte-exact replay is `blocked` (same host-path deviation as relaunch 1, recorded in
  `FREEZE_V33_20261014.md`). Driver note: `replay_ts_r1.py` takes the worktree as an argument and does not pin `f74b29b`; `replay_ts_rep2.py` is a thin copy
  that changes only the output labels and adds four assertions (package `frameworkCommit` and setup ID, worktree HEAD `04254228`, worktree clean). No harness edit.
- Readout `readout-teastore-offpath-rep2-v3.3` (`cde33b9`) and post hoc `out-ts-rep2-posthoc` (`4412acf`) committed unedited before any value was read;
  `campaignsRead` lists exactly one campaign directory (`tmp/teastore-offpath-evidence/rep2-fetch/x/teastore-offpath-v1`, found 30, valid 30; setup ID
  `cbe9920a...` from its `.packages`, and the post hoc run passed `--expect-setup-id`). No other TeaStore fetch was passed to a reader. The post hoc script is
  the post-deviation version (sha256 `b203c2c3...`). The readout flags all 30 cells F5 (`04254228` is not in the reader's HARNESS_PROVENANCE table) and its
  header text ("not frozen", harness 91c4967) is the same stale boilerplate as relaunch 1.

## Barrier probes (validity data; `barrier-probes.json`, `c9a49c0`)

- 30 cells: 29 have 1 probe, 1 has 2 probes. The acknowledging probe (the last one) read 0 messages and 1 consumer in 30/30; `consumerAtStart` read 0
  messages in 30/30.
- Acknowledging probe completion offset after the barrier: 1.199-1.429 s in the 29 one-probe cells; 3.629 s in the one two-probe cell.
- The two-probe cell is `no-fault-cost/r10/b01/full/a01`: probe 1 started at 0.012 s, completed at 1.393 s and read 1 message; probe 2 started at 2.395 s,
  completed at 3.629 s and read 0. The declaration records a non-empty read at the acknowledgement as what stopped the two earlier replication attempts.
- First probe start offsets 0.0003-0.0182 s.

## Declared predictions (T-L1, T-L2, T-OFF, T-C), side by side with relaunch 1

Sources: `side_by_side.json` (`42a2efc`; both columns from the committed readouts and post hoc outputs), `RESULT_TS_OFFPATH.md` for relaunch 1's recorded sentence.

| id | rule | relaunch 1 (`f74b29b`) | replication 2 (`04254228`) |
|---|---|---|---|
| T-L1 own silence | recommender cgroup CPU down-fire < 5 s in >= 9/10 | **miss**, 0/10 | **miss**, 0/10 |
| T-L2 coordinator | registry removal line 7.5-12.5 s in >= 9/10, both rates | **hit**, 10/10 at 8.37-12.03 s (rate 10: 8.37-12.03; rate 1: 9.45-11.31); medians 9.70 / 10.24 s | **hit**, 10/10 at 9.09-12.47 s (rate 10: 9.09-12.47; rate 1: 9.12-11.81); medians 9.48 / 10.34 s; all 10 in the by-construction field (`BC-caller-log`), counted 0/10 |
| T-OFF stays off the login route | ok share >= 95 % in >= 9/10 and no counted ledger fire | **miss** (second clause): ok share 1.0 in 10/10; 1 episode with a counted ledger `spike` (rate 10, block 5, 5.07 s) | **miss** (second clause): ok share 1.0 in 10/10 (602/602 or 603/603 per episode at rate 10; 60/60 or 61/61 at rate 1); 1 episode with a counted ledger `spike` (`ledger:webui:login-only-v1`, rate 1, block 3, 27.86 s) |
| T-C on-path control | auth-freeze P1 holds | **hit**, 10/10 (5 per rate) | **hit**, 10/10 (5 per rate) |

The T-L1 sentence is as for relaunch 1: no calibrated `sys_cpu` down fire in 0/10 episodes. The own lane's counted fires differ between the two runs:

| recommender own lane (counted fires, `side_by_side.json`) | relaunch 1 | replication 2 |
|---|---|---|
| rate 10, episodes with an own fire / earliest | 5/5 at 14.86-14.92 s; sensors `sys_io` and `sys_psi_cpu` (median, run3) | 5/5 at 14.84-14.93 s; sensor `sys_io` (median) |
| rate 1, episodes with an own fire / earliest | 0/5 | 5/5 at 4.15, 14.13, 14.47, 14.72, 14.97 s; `sys_io` (median) in 5/5, plus `sys_memory` (spike 4.15 s, run3 and median 14.15 s) in block 4 |

| auth-freeze (on-path control), earliest fire by lane, either field | relaunch 1 | replication 2 |
|---|---|---|
| own, rate 10 / rate 1 | 0.33-0.44 / 0.41-1.08 s | 0.40-0.46 / 0.92-1.54 s |
| coordinator (registry log), rate 10 / rate 1 | 9.80-11.94 / 9.83-12.30 s | 10.02-11.98 / 9.86-12.19 s (10/10 by-construction, counted 0/10) |
| ledger, rate 10 / rate 1 | 0.51-0.61 / 0.47-1.13 s | 0.44-0.51 / 1.01-1.63 s |

## Predictions TSR-* (`PREDICTIONS_SCORED.md/.json`, `75326e3`): 10 hit, 1 miss, 2 ontology rows as verdicts

| id | result | numbers (denominator in each) |
|---|---|---|
| TSR-L2 | hit | 10/10 in [7.5, 12.5] s (9.09-12.47 s), by-construction field 10/10, counted 0/10 |
| TSR-L2a | hit | auth-freeze 10/10 in [7.5, 12.5] s (9.86-12.19 s), by-construction 10/10, counted 0/10 |
| TSR-L1 | hit | cgroup CPU down-fire < 5 s in 0/10 (ceiling 1); cross-check, any own-lane fire < 5 s: 1/10 (the `sys_memory` spike, rate 1, block 4) |
| TSR-L1b | **miss** | rate 10: own fire in [12, 18] s in 5/5 (need 3): clause holds. Rate 1: own fire in 5/5 episodes (ceiling 1/5): clause fails |
| TSR-L1c | hit | auth own lane detects 10/10; max 0.459 s at rate 10 (limit 1.0), max 1.537 s at rate 1 (limit 2.5) |
| TSR-OFF | hit | ok share >= 95 % in 10/10 (need 9); 1/10 episodes with a counted ledger fire (ceiling 2). Declared T-OFF itself: miss (clause b) |
| TSR-W | hit | `log:webui:d4d75ec135e6` counted in 10/10 episodes, 10.06-13.97 s, 0.94-2.05 s after the registry removal |
| TSR-C | hit | auth-freeze P1 holds, 10/10 |
| TSR-D1 | hit | auth own, median 0.454 s (rate 10) vs 1.313 s (rate 1), ratio 0.345 (limit 0.5); max(rate 10) 0.459 < min(rate 1) 0.923 |
| TSR-D2 | hit | auth-freeze coordinator medians 10.11 / 9.97 s, difference 0.14 s, ranges overlap; recommender-pause 9.48 / 10.34 s, difference 0.86 s, ranges overlap (limit 2.5 s) |
| TSR-D3 | hit | auth ledger medians 0.500 s (rate 10) vs 1.395 s (rate 1), ratio 0.358 (limit 0.5), 10/10 detected |
| TSR-ONT-recommender | verdict items | own lane predicted `no`: measured 10/10 episodes (counted 10/10), disagree (relaunch 1: 5/10); coordinator predicted `no`: measured 10/10 (counted 0/10), disagree; lag: not comparable; CQ-C1 `no-liveness-check`: measured class by-construction hit in 10/10, disagree; CQ-L2: no window predicted, coordinator 9.09-12.47 s, not predicted; CQ-B1 entry reached: ledger lane any in 1/10, agree |
| TSR-ONT-auth | verdict items | own lane predicted `no`: measured 10/10, disagree; coordinator predicted `no`: measured 10/10 (counted 0/10), disagree; lag: not comparable; CQ-C1: disagree (10/10 by-construction); CQ-L2: not predicted; CQ-B1: ledger any 10/10 (counted 0/10), agree |

TSR-L1b is the only miss. The rate-1 recommender episodes carry a counted `sys_io` median down-fire in 5/5 (14.13-14.97 s); relaunch 1 had none at rate 1.

## What this does and does not say

- The registry's heartbeat-removal line marks the paused off-path recommender in 10/10 episodes at 9.09-12.47 s (relaunch 1: 8.37-12.03 s), and the auth
  removal line in 10/10 auth-freeze episodes at 9.86-12.19 s; neither is in the counted field. Coordinator times show a rate difference of 0.14 s (auth) and
  0.86 s (recommender) in medians.
- The recommender's cgroup CPU counter produced no calibrated `sys_cpu` down fire in 0/10 episodes in either run; T-L1 is a miss of the detector in both.
  The own lane fires at about 14-15 s on `sys_io` in 10/10 episodes here (relaunch 1: 5/10, rate 10 only). `sys_psi_cpu` has no counted own fire here
  (relaunch 1: 5/5 at rate 10). These differences are reported; this note does not explain them.
- The login route stayed available in every pause episode (ok share 1.0 in 10/10; relaunch 1 the same). The one counted ledger spike per run sits at a
  different rate, block and time (5.07 s, rate 10, block 5 vs 27.86 s, rate 1, block 3); with 1 episode each it is not separated here from ledger noise. The
  request-level detail of the replication-2 spike was not examined.
- Webui's Ribbon "current list of Servers=[]" line (`log:webui:d4d75ec135e6`) is counted in 10/10 recommender-pause episodes (relaunch 1: 10/10); it was a
  TSR prediction for the first time here and the rule held.
- Barrier: all 30 cells reached the acknowledgement with an empty queue at the acknowledging probe; one cell needed a second probe. The probe summary is
  validity data, not a measurement of the SUT. No comparison of cell records between the old and the new acknowledgement was run here.
- The two TeaStore off-path runs differ in harness commit, host-time and (by the numbers above) in the own lane; the comparison across them is two
  instances on one host, one SUT. n = 5 episodes per rate. No cross-SUT claim.
- Review status: no independent review of this note or of the scoring has been run (the `judge` MCP server failed to connect in this session). The scorer
  is a post hoc script over committed outputs; an independent review is owed before any sentence here enters a document.
