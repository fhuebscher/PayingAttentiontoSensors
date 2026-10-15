# R1: TeaStore off-path placement test (relaunch 1 of the third run of `teastore-offpath-v1`): result (2026-10-15)

Scope: **instance** (TeaStore at 34b37f7, fb14srv5, login-only workload at 10 and 1 req/s, 5 blocks; trained on blocks 1-3, scored on blocks 4-5; n = 2 test
episodes per class and rate). Every number from the replay line on is copied from the committed file named beside it; the run and fetch lines come from the
uncommitted local logs `scratchpad/gate-drivers/teastore-rep3r1-launch.log` and `fetch-teastorerep3r1.log`. `—` = absent. **Review status: one same-provider adversarial review (2026-10-15 ~13:22Z): chain order and every verdict-table number confirmed; one price corrected; five sentences replaced; no cross-provider review yet.** Commit order is shown by git; that outputs were unread before commit is probable, not provable.

- Declarations `research/traffic-sweep/DECLARATION_TEASTORE_OFFPATH_PLACEMENT.md` (`42c04f3`, predictions TS3-*) and `_RELAUNCH1.md` (`102a8cf`; the first attempt,
  setup `416ea06f…`, stopped at cell 6 on a witness window check after 5 valid cells and is not read); budget `2501e86`. Frozen chain
  `research/protocol/FREEZE_V36_20261015.md` (`975b7a1`, step-1 amendment `fbcabc4`, fetch-name note `684284f`, step 2 `8db907a`). Harness `04254228`, plan
  `5a8e385e…` (same seed, order and onsets as replication 2; new cells).
- Run: setup `dcc8b664a9d0602e019a45322d93dbf1`, terminal 12:48:02Z (`state=complete`, 30 journal rows, `abort=False`; launch log, uncommitted; committed `terminal-replay-rep3r1.json`: setupId `dcc8b664…`, `hostTerminalValidation` 30/30 pass).
  Disclosure: the stopped first attempt (setup `416ea06f`) stopped on cell 6, `recommender-pause-effect/r10/b01`, the same class and rate that FAILed; its cause is
  "not established" (`DECLARATION_TEASTORE_OFFPATH_PLACEMENT_RELAUNCH1.md`); the relaunch passed the same witness check in 30/30 cells; the stopped attempt's cells
  were never read. Fetch
  `tmp/teastore-offpath-evidence/rep3r1-fetch`: host files 667, OK 667, shasum rc 0 (fetch log, uncommitted).
- Offline terminal replay under `/usr/bin/python3` 3.9 with a fresh empty `PYTHONPYCACHEPREFIX`, bytecode writing disabled (`terminal-replay-rep3r1.json`, `ea06a50`; command in
  `terminal-replay-rep3r1.cmd.txt`; driver `replay_ts_rep3r1.py`, a copy of `test-ts-rep2/replay_ts_rep2.py` with labels and the setup pin changed):
  30 of 30 cells replay to pass, 10 byte-equal to the retained validation, 20 differ only in the observation path; the campaign-level replay is `blocked` by
  host-path embedding, the same recorded deviation as relaunch 1 and replication 2.
- Chain, each output committed unedited before it was read: training readout `readout-teastore-offpath-rep3r1-train-v3.6` (`bddd9d3`; `campaignsRead` = this
  fetch only, 18 of 18 valid training cells, 6 per regime; `provenance.input.sha256` `7c78b0df…`), placement `placement-rep3r1.json` (`694851c`, sha256
  `f7f5c04a…`, `inputs.scriptSha256` `05c5c58a…` = celf_v3_6 at step 1), pin `174ba4b`, scoring readout `readout-teastore-offpath-rep3r1-score-v3.6` (`9bcb7c1`),
  scorer `ts-rep3r1.json` / `.md` (`4da3d99`), predictions `PREDICTIONS_SCORED_TS3.json` / `.md` (`9c5634a`; script `score_predictions_ts3.py`, `493732b`,
  committed before it ran). The pin line in `score_test_v3_6.py` keeps its pre-pin comment ("empty until …"); the value is the pin (cosmetic, not edited further).

## Verdicts (V36_PASS_RULE; `ts-rep3r1.json` `inputs.passRuleSource`; its `passRuleNote` text is score_test_v3_2's inherited label)

| class, rate | frozen set (frontier any/any @6/T_r) | price, budget | test: ledger / set (s) | g (test, class) | improved | verdict |
|---|---|---|---|---|---|---|
| recommender pause, 1 req/s | `log:webui:d4d75ec135e6` | 19.97/h, 40/h | miss / 11.38, miss / 12.14 | 48.460 | 2 of 2 | **PASS** |
| recommender pause, 10 req/s | `span:auth:BCryptProvider.checkPassword` | 19.97/h, 40/h | miss / miss, miss / 0.23 | 29.987 | 1 of 2 | **FAIL** |

T_r = 0.15 h per rate (3 training no-fault cells; `placement-rep3r1.json` `rates.*.hours`), so 6/T_r = 40/h and 19.97/h is the zero-alarm floor of 0.15 h. Ground set
461 sensors per rate, all tier-missing (only the any/any cell is defined). Candidates recurring on the recommender class in training, at both rates:
`log:webui:d4d75ec135e6` (19.97/h at both rates) and `span:auth:BCryptProvider.checkPassword` (19.97/h at 10 req/s; 41.97/h at 1 req/s, 2 training no-fault alarms in
0.15 h, above 40/h alone) (`rates.*.costs`; training readout `placementFalseAlarms.primary`). After the recurrence rule, 5 (1 req/s) and 7 (10 req/s) of 461 sensors
are admitted (`recurrence.removedFromGroundSet` 456 / 454). The 1 req/s set is the webui line alone because webui wins alone on training gain (24.02 vs 18.59) and the
auth span alone is priced above the 40/h budget; the @inf set {webui, auth} costs 61.94/h. Post hoc counterfactual: with the pair the 1 req/s test would still improve
2 of 2 (11.38, 2.94 s). Auth freeze (on-path control, no verdict): the ledger detects all 4 test episodes, at 0.87 / 1.07 s (1 req/s) and 0.38 / 0.42 s (10 req/s).

## Why 10 req/s failed (from the committed readouts; post hoc reading of committed values, no rule changed)
Fires in the recommender-pause episodes at 10 req/s (`episodes[].fires` of the scoring readout, whose blocks 1-3 equal the training readout's):

| block | `span:auth:BCryptProvider.checkPassword` (`median`, up) | `log:webui:d4d75ec135e6` (`appear`) |
|---|---|---|
| 1 (training) | 8.40 s | 12.18 s |
| 2 (training) | 0.55 s | 12.36 s |
| 3 (training) | 0.20 s | 11.62 s |
| 4 (test) | — | 12.17 s |
| 5 (test) | 0.23 s | 11.74 s |

In training the auth span fired before the webui line in 3 of 3 episodes, so CELF chose it, and the webui line then added no training gain and was not added
(both together would have cost 39.94/h, inside 40/h). On the test blocks the auth span fired in 1 of 2 episodes; the webui line fired in 2 of 2 but was not in
the set. At 10 req/s its first counted `median` (up) fire came 0.20-8.40 s after the onset stamp in 4 of 5 recommender-pause episodes (3 of 3 training, 1 of 2 test), with 0
training no-fault alarms in 0.15 h. At 1 req/s it came 2.94-16.19 s after onset in 4 of 5, with 2 training no-fault alarms in 0.15 h. What moves its median during a
recommender pause is not established here; the readout marks it `onPath: false` for this class (`affectedPath` = [recommender]); the login workload exposes auth,
persistence and webui (`exposure.exposedServices`). Context: in the uncommitted rep2 dry run the auth span did not recur on the recommender class at either rate (priced
41.97 and 51.69/h); untested hypothesis: fires at 0.20-0.55 s may come from windows straddling the onset.

## Predictions (declared before launch, informed by the replication-2 dry run; `PREDICTIONS_SCORED_TS3.md`)
| id | prediction | result |
|---|---|---|
| TS3-V | PASS at rate 10 and at rate 1 | **miss**: PASS at 1 req/s, FAIL at 10 req/s |
| TS3-S | the frozen set at both rates is `log:webui:d4d75ec135e6` alone | **miss**: yes at 1 req/s; `span:auth:BCryptProvider.checkPassword` at 10 req/s |
| TS3-T | the set's first counted fire (`ttd`) is 9-15 s in 4 of 4 off-path test episodes | **miss**: 11.38, 12.14 s at 1 req/s; — and 0.23 s at 10 req/s |
| TS3-L | the ledger alone misses 4 of 4 off-path test episodes | **hit**: 4 of 4 missed |
| TS3-C | auth freeze: the ledger detects 4 of 4 test episodes | **hit**: 4 of 4 |

## What this does and does not say
- The frozen rule passed at 1 req/s and failed at 10 req/s (instance). The dry run on replication 2 (post hoc, `FREEZE_V36` dry-run section; uncommitted output,
  placement `3ad5bb86…`) had chosen the webui line at both rates and passed both; on this run the training blocks at 10 req/s preferred an auth-span `median`
  (up) sensor whose first counted fire preceded the webui line in 3 of 3 training episodes; on the test blocks it fired in 1 of 2 (0.23 s), so the set improved 1 of 2.
  Commit `9536499`'s message carried the earlier wrong wording ("did not repeat"); commit messages are not rewritten. The selected sensor differed between two runs of the same plan at one of two rates (instance), as it did
  between F's runs.
- The 1 req/s PASS is through a webui log template whose text is Ribbon's server-list line ("current list of Servers=[]"), found post hoc in the review of relaunch 1,
  which also recurs on the auth-freeze class in training at both rates (`recurringByClass`). By decision 111's reading a PASS says which lane sees this
  fault and when, not that the method generalises. The predictions were informed by already-read data (declaration), so TS3-* are not blind.
- The ledger detected 0 of 4 off-path test episodes (and 0 of 3 training per rate; `ledger alone` `detectedEpisodes` 3 of 6 = the auth-freeze episodes), as expected when
  no request in the window touches the paused service (instance). TS3-L is a hit by construction.
- The effort/runtime axes carry no information here (every candidate tier-missing); every non-any/any cell equals the ledger by construction.
- Power is low: 2 test episodes per rate, 3 training episodes per class and rate, T_r = 0.15 h. Fresh false alarms of the frozen sets: not computed (`—`).
- Scope: one host, one run, 2 test episodes per class and rate.
