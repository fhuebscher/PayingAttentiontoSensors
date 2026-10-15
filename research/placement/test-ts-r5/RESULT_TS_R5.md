# R5: TeaStore off-path placement, same-plan repeat of R1 (relaunch r5r1) + transfer of R1's frozen sets: result (2026-10-15/16)

Scope: **instance** (TeaStore at 34b37f7 (`sutCommit` in the fetched cells), fb14srv5, login-only workload at 10 and 1 req/s, 5 blocks; trained on blocks 1-3, scored on blocks 4-5; n = 2 test
episodes per class and rate). Every number from the replay line on is copied from the committed file named beside it; the run and fetch lines come from the
uncommitted local logs `scratchpad/gate-drivers/teastore-r5r1-launch.log` (sha256 `b178590e…`) and `scratchpad/gate-drivers/fetch_r5-r5r1.out` (sha256 `b8f9ef11…`). `—` = absent.
**Review status: one same-provider adversarial review (Claude `adversarial-review` subagent, read-only, 2026-10-15 ~19:05Z): every number and the chain order
confirmed, no number wrong; 9 sentences replaced and 7 items added; no cross-provider review yet.** Commit order is shown by git; that
outputs were unread before commit is probable, not provable.

- Declaration `research/traffic-sweep/DECLARATION_TEASTORE_R5.md` (`c61cde6`, predictions TS5-*), budget `BUDGET_OVERNIGHT_20261015.md` (`bfc9417`, amendment
  `b43a5dd`), run order `research/placement/test-ts-r5/RUN_ORDER.md` (`bff05a6`, setup ID filled `04e1a42`). `DECLARATION_TEASTORE_OFFPATH_PLACEMENT.md` (`42c04f3`)
  stays binding for design and rule; frozen chain `research/protocol/FREEZE_V36_20261015.md`. Harness `04254228`, plan `5a8e385e…` (same seed, order, onsets and host
  as R1; new cells under a new setup ID). R1's, replication 2's and the stopped attempt's cells were not read and not pooled.
- Stopped first attempt (setup `b4bdd8e0…`): stopped at cell 5 (`auth-freeze-effect/r10/b01`, `RuntimeError: TeaStore readiness failed`; classified infrastructure,
  cause not established; `STOP_TEASTORE_R5_ATTEMPT1.md`, `7c36497`); its cells were never read.
- Run: relaunch `r5r1`, setup `9e9443fb6252e0ac7e1c6d374be15b24` (last `APPROVE GATE-RUN … release=` line of the launch log); launcher started 14:57:16Z after DRY_RUN
  `r5r1dry` passed (14:57:06Z, `teastore-r5r1dry-launch.log`), campaign unit started 15:07:49Z (`oneshot rc=0`), terminal 18:25:57Z (`state=complete`, 30 journal
  rows, `terminal=True`, `abort=False`; launch log). srv5 checked by the host before the fetch (18:26:55Z: 0 containers, 0 active `candidate-v4` units; a
  main-session command whose output is in neither log). Fetch `tmp/teastore-offpath-evidence/r5-fetch`: host files 667, OK 667, shasum rc 0 (fetch log). Binding
  check: package `setupId` `9e9443fb…`, `frameworkCommit` `04254228…`, 30 cells, exit 0 (command output not retained; the same values are in the committed
  `ts-r5.override.json` `fetch.packageSetupId` / `packageFrameworkCommit` and `terminal-replay-r5.json` `setupId`, 30 cells); `source.txt` ends in the setup ID.
- Deviations not in the declaration: the launcher ran without `caffeinate` (launch log line 2, WARN; the declaration's launch line uses `nohup caffeinate -i`), with
  no gap in the 5-min watcher rows; the wandb follower ran offline (`scratchpad/gate-drivers/wandb-r5r1.out`, run `8w9fook2`, not synced).
- Step 0: the seven frozen digests equal RUN_ORDER's; the five test files ran 115 passed, not RUN_ORDER's 114: the +1 is `tests/test_score_rep_ts5.py:208`, which
  parametrises over `EARLIER_SETUP_IDS`, raised from 7 to 8 by `03cffbd` (after RUN_ORDER was written); 115 needs `4a53697` as well (`03cffbd` alone fails
  `test_score_rep_ts5.py:108`). The 115-passed output was not retained in a file; the tests ran at ~18:27Z, concurrently with the start of the fetch and before any
  fetched file was read (RUN_ORDER asks for them before the fetch is opened).
- Offline terminal replay under `/usr/bin/python3` 3.9.6 with a fresh empty `PYTHONPYCACHEPREFIX` (`tmp/pycache-r5.183912`), bytecode writing disabled
  (`terminal-replay-r5.json`, `be93041`; command in `terminal-replay-r5.cmd.txt`; driver `replay_ts_r5.py`, sha256 `ba0e13e9…`): 30 of 30 cells replay to pass,
  10 byte-equal to the retained validation, 20 differ only in the observation path; `hostTerminalValidation` 30/30 pass; the campaign-level replay is `blocked`
  by host-path embedding, the same recorded deviation as R1.
- Chain, each output committed unedited before it was read (stdout of each step captured to the scratchpad and read after the commit): training readout
  `readout-teastore-offpath-r5-train-v3.6` (`c4110f7`; `campaignsRead` = this fetch only, 18 of 18 valid, 6 per regime; json sha256 `0071c2d9…`, not R1's `b00bafd0…`;
  `provenance.input.sha256` `408e9d7b…`), placement `placement-r5.json` (`0918b0e`, sha256 `5f68c81d…`, R5's pin; not R1's `f7f5c04a…`; committed before the scoring
  readout existed), scoring readout `readout-teastore-offpath-r5-score-v3.6` (`7251410`; 30 of 30 valid; json sha256 `41bf1c39…`, not R1's `b53521c9…`), scorer
  `ts-r5.json` / `.md` / `.override.json` (`a8e84d3`; `score_rep_ts5.py` with `--setup-id`; the sidecar records placement commit `0918b0e`, setup `9e9443fb…`, R1's pin
  unchanged before and after), transfer `transfer-r5/` and `transfer-r5-own/` (`00c08a1`), predictions `PREDICTIONS_SCORED_TS5.json` / `.md` (`8345617`; script
  `score_predictions_ts5.py`, committed `54764b6` before it ran; the commit message's "c2a4840" is that script's sha256 prefix, not a commit). Script digests:
  `placement-r5.json` `inputs.scriptSha256` `05c5c58a…` (celf_v3_6, unchanged since R1), readouts `scriptSha256` `98d7832c…`. Each step's captured stdout was
  created after the previous step's commit (local birth times; replay 18:39:12Z … predictions 18:46:00Z). The scoring readout was written and committed by one
  command, the commit in the same second as the readout's last write (18:45:00Z), so "committed before it was read" is not strictly provable for that step; the
  transfer stdouts carry the full verdict table and were displayed (first 5 lines) only after `00c08a1`.
- Wrapper digest: `score_rep_ts5.py` ran at sha256 `5a9e0266…` (`03cffbd`, eight earlier setup IDs including `b4bdd8e0…`), not the `dc22b6a3…` (`190bced`, seven IDs)
  RUN_ORDER step 6 cites; the "recorded gap" named there (the stopped attempt's ID missing from the wrapper's refuse list) was closed by `03cffbd` (15:00:35Z; its test expectation fixed by `4a53697`, 15:00:50Z), after the relaunch's launcher
  started (14:57:16Z) and before the campaign unit started (15:07:49Z, `oneshot rc=0`) and before the fetch.

## Verdicts (V36_PASS_RULE; `ts-r5.json` `inputs.passRuleSource`; its `passRuleNote` text is score_test_v3_2's inherited label)

| class, rate | frozen set (frontier any/any @6/T_r) | price, budget | test: ledger / set (s) | g (test, class) | improved | verdict |
|---|---|---|---|---|---|---|
| recommender pause, 1 req/s | `log:webui:d4d75ec135e6` | 19.97/h, 40/h | miss / 11.40, miss / 11.95 | 48.542 | 2 of 2 | **PASS** |
| recommender pause, 10 req/s | `log:webui:d4d75ec135e6` | 19.97/h, 40/h | miss / 11.70, miss / 11.10 | 48.814 | 2 of 2 | **PASS** |

T_r = 0.15 h per rate (`placement-r5.json` `rates.*.hours`), so 6/T_r = 40/h and 19.97/h is the zero-alarm floor of 0.15 h (the webui line: 0 training no-fault
alarms at both rates, training readout `placementFalseAlarms.primary.allPlaceable.*.perSensor`). Ground set 461 sensors per rate, all tier-missing
(`tiersMissingForGroundSet` 461 of 461). After the recurrence rule, 3 (1 req/s) and 7 (10 req/s) of 461 sensors are admitted (`recurrence.removedFromGroundSet`
458 / 454). Recurring on the recommender class in training (`recurringByClass`): 1 req/s `{log:webui:d4d75ec135e6}`; 10 req/s `{log:webui:d4d75ec135e6,
span:image:AbstractCache.loadData}` (the image span priced 41.97/h, above 40/h alone). The @3/T_r, @6/T_r and @inf sets are the webui line alone at both rates; @6/h
is empty. Training g at @6/T_r over the 6 training episodes per rate (both classes): 24.567 (1 req/s), 13.885 (10 req/s). At @inf, where the image span is
affordable, it was not added at 10 req/s: its counted `run3` fires (50.50, 17.33, 37.81 s) all came after the webui line's in training, so it added no training gain
(D at @inf = D at @6/T_r = 6.201).

`span:auth:BCryptProvider.checkPassword` (R1's 10 req/s set) did not recur on the recommender class in R5's training at either rate: its counted `median` fire came in
0 of 3 training episodes at 1 req/s and 1 of 3 at 10 req/s (block 3, 0.69 s); training no-fault alarms 37 (1 req/s) and 177 (10 req/s) in 0.15 h, priced 324.50/h and
1336.66/h (R1: 2 and 0 alarms, 41.97/h and 19.97/h).

Auth freeze (on-path control, no verdict): the ledger detects all 4 test episodes, at 0.83 / 1.06 s (1 req/s) and 0.36 / 0.41 s (10 req/s); the set's entry equals the
ledger's in all 4.

## Test episodes (`ts-r5.json` `rates.*.episodes`; set = frontier any/any @6/T_r, ledger included; hold 60.2 s; a miss is charged the hold)

| rate | class | block | cell | ledger (s) | set (s) | set improves |
|---|---|---|---|---|---|---|
| 1 | auth freeze | 4 | `b04-05-full` | 0.83 | 0.83 | no |
| 1 | auth freeze | 5 | `b05-06-full` | 1.06 | 1.06 | no |
| 1 | recommender pause | 4 | `b04-02-full` | miss | 11.40 | yes |
| 1 | recommender pause | 5 | `b05-03-full` | miss | 11.95 | yes |
| 10 | auth freeze | 4 | `b04-04-full` | 0.36 | 0.36 | no |
| 10 | auth freeze | 5 | `b05-01-full` | 0.41 | 0.41 | no |
| 10 | recommender pause | 4 | `b04-06-full` | miss | 11.70 | yes |
| 10 | recommender pause | 5 | `b05-05-full` | miss | 11.10 | yes |

Fires behind it (scoring readout `episodes[].fires`; its blocks 1-3 equal the training readout's for the rows below): the webui line's counted `appear` fire came
10.13-12.26 s after the onset stamp in 10 of 10 recommender-pause episodes (5 per rate, training and test). It also fires in 10 of 10 auth-freeze episodes (5 per rate, training and test), later than the
ledger (29.13-30.83 s at 1 req/s, 16.51-17.28 s at 10 req/s). The ledger (`ledger:webui:login-only-v1`) fired a counted `spike` at 29.70 and 29.50 s in 2 of 3
training recommender-pause episodes at 10 req/s (blocks 1, 3; training @0 `detectedEpisodes` 5 of 6) and in none of the 1 req/s ones or of the 4 test ones.

## Transfer of R1's frozen sets (post hoc to the sets, declared before this fetch; `transfer-r5/transfer.json`, `transfer_score.py` sha256 `b438fcaf…`)

Readout argument = the scorer's `inputs.readout` (same path, sha256 `41bf1c39…` in both `ts-r5.json` and `transfer.json`; checked). R1's placement
`placement-rep3r1.json` sha256 `f7f5c04a…`. Thresholds from R5's own training calibration; the price is R5's training price (`placement-r5.json`
`rates.*.costs`; `transfer.json` carries none), reported, not a condition.

| R1 set, rate | members | price in R5's training | test: ledger / set (s) | g (test, class) | improved | absent members | verdict |
|---|---|---|---|---|---|---|---|
| 1 req/s | `log:webui:d4d75ec135e6` | 19.97/h | miss / 11.40, miss / 11.95 | 48.542 | 2 of 2 | none | **PASS** |
| 10 req/s | `span:auth:BCryptProvider.checkPassword` | 1336.66/h | miss / 0.64, miss / miss | 29.787 | 1 of 2 | none | **FAIL** |

In R1 the same rate-10 set also improved 1 of 2, in the other block (R1: block 4 miss, block 5 0.23 s; R5: block 4 0.64 s, block 5 miss). Auth-freeze rows equal the
ledger in all 4 (not tabulated).

Consistency check (budget item 2): `transfer_score.py` on R5's own placement (`transfer-r5-own/transfer.json`, placement `5f68c81d…`) reproduces `ts-r5.json`'s
per-episode outcomes and its @6/T_r verdicts at both rates (`PREDICTIONS_SCORED_TS5.json` `consistencyCheck` `pass`, 0 mismatches), so TS5-T1 and TS5-T10 are scored,
not `—`.

## Predictions (declared before launch, INFORMED BY SEEN DATA: R1 and its review, replication 2 and its v3.6 dry run, off-path relaunch 1; `PREDICTIONS_SCORED_TS5.md`)

| id | prediction | result |
|---|---|---|
| TS5-V1 | PASS at rate 1 | **hit**: PASS (g 48.542, 2 of 2) |
| TS5-V10 | PASS at rate 10 (low confidence) | **hit**: PASS (g 48.814, 2 of 2) |
| TS5-S | the frozen @6/T_r set contains `log:webui:d4d75ec135e6` at both rates | **hit**: the webui line alone at both rates |
| TS5-T1 | R1's rate-1 set `{webui line}` improves on the ledger in 2 of 2 rate-1 test episodes | **hit**: 2 of 2 |
| TS5-T10 | R1's rate-10 set `{auth span}` improves in at most 1 of 2 rate-10 test episodes (low confidence) | **hit**: 1 of 2 |
| TS5-L | the ledger alone misses 4 of 4 off-path test episodes (a check, not counted) | **hit** (check): 4 of 4 missed |
| TS5-C | auth freeze: the ledger detects 4 of 4 test episodes | **hit**: 4 of 4 |

Tally: 6 hit, 0 miss, 0 undecided, of 6 counted (TS5-L not counted).

## What this does and does not say
- The frozen rule passed at both rates on this run (instance). On R1, a same-plan run on the same host, it passed at 1 req/s and failed at 10 req/s. Two runs of the
  same plan, both scored; the verdicts agree at 1 req/s and differ at 10 req/s. Two runs do not estimate how often each verdict occurs.
  A third complete run of this plan, replication 2 (`cbe9920a…`), was scored only post hoc in the v3.6 dry run (webui line at both rates, PASS at both;
  `RESULT_TS_PLACEMENT.md`, "What this does and does not say") and is not counted here.
- The selected set at 10 req/s differed between the two runs (R1: the auth span; R5: the webui line); at 1 req/s it was the webui line in both. In R5's training the
  auth span fired in 1 of 3 recommender-pause episodes at 10 req/s and carried 177 no-fault alarms in 0.15 h; in R1 it fired in 3 of 3 with 0. Why its behaviour
  differed between the two runs is not established here; the readout marks it `onPath: false` for this class, as in R1.
- R1's 10 req/s set, scored on this run's test blocks, improved 1 of 2 (FAIL), as on R1's own test blocks, but in the other block. R1's 1 req/s set is the same sensor
  as R5's own set at both rates, so its transfer PASS at 1 req/s is the same per-episode computation as the scorer's (the consistency check above).
- Both PASSes are through the webui log template whose text, found post hoc in the review of off-path relaunch 1 (for this epoch; the template
  was already identified on 2026-09-27, `research/s4-conjunction/REVIEW_RESULT_BASELINE_20260927.md:60`), is Ribbon's server-list line ("current list of
  Servers=[]"). It also recurs on the auth-freeze class in training at both rates (`recurringByClass`) and fires there 16.5-30.8 s after onset. By decision 111's
  reading (stated for OTel's E, `research/PROTOCOL_DRAFT_20261002.md:634-638`, applied here by analogy), a PASS says which lane sees this fault and when, not a
  measure of the placement method's power.
- The ledger missed 4 of 4 off-path test episodes. No request touched the recommender (scoring readout `exposure.neverExposedServices` includes it), the
  declaration's condition for calling TS5-L true by construction; yet the ledger is not blind to this class on this run: it fired a counted `spike` at 29.70 and
  29.50 s in 2 of 3 rate-10 training recommender-pause episodes (0 of 3 at 1 req/s; R1: 0 of 10 off-path episodes), so the 4 test misses are an observation, not a
  consequence of exposure alone. What moved the ledger is not established here. TS5-L is reported as a check, as declared.
- The predictions were informed by already-read data (declaration), so a 6 of 6 tally is not a blind test. TS5-T1 and TS5-V1 are
  decided by the same computation (R1's rate-1 set equals R5's own set; same episodes), so the 6 counted rows are not 6 independent outcomes. TS5-T10 holds at 1 of 2, the declared boundary.
- The effort/runtime axes carry no information here (every candidate tier-missing; `runtimeCost` `—` for the chosen set); every non-any/any cell equals the ledger by
  construction. Fresh false alarms of the frozen sets on no-fault cells: not computed (`—`).
- Power is low: 2 test episodes per class and rate, 3 training episodes per class and rate, T_r = 0.15 h. Scope: one host, one SUT, one workload, two runs of one
  plan (R1 and R5, never pooled).
