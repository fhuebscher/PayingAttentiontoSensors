# R3: Hotel off-path placement test (second run of `hotel-offpath-v1`, the declared negative control): result (2026-10-15)

Scope: **instance** (Hotel Reservation, fb14srv4, rates 10 and 1 req/s, 5 blocks; trained on blocks 1-3, scored on blocks 4-5; n = 2 test episodes per class and rate).
Every number from the replay line on is copied from the committed file named beside it; the run and fetch lines come from the uncommitted local logs
`scratchpad/gate-drivers/hotel-off2-launch.log` and `fetch-hoteloff2.log`. `—` = absent. **Review status:** one same-provider adversarial review (2026-10-15
~11:20Z): every number confirmed, seven sentences replaced below; no cross-provider review of this note.

- Declaration `research/traffic-sweep/DECLARATION_HOTEL_OFFPATH_PLACEMENT.md` (committed alone before launch); budget amendment `369b18c`; frozen chain
  `research/protocol/FREEZE_V37_20261015.md` (`0cede5c`, step-1 amendment `fbcabc4`, step 2 `f76f8cb`). Harness `9ad0b98`, plan `90b7b621…` (same seed, order and onsets
  as the first run; new cells).
- Run: campaign `hotel-v1-20261015t080538z-cb803aec`, launched 08:05Z, terminal 10:14:50Z (`state=stopped`, `terminal=True`, `abort=False`; `hotel-off2-launch.log`, uncommitted). Fetch
  `tmp/hotel-offpath-evidence/off2-fetch`: host files 2878, OK 2878, shasum rc 0.
- Offline terminal replay under `/usr/bin/python3` 3.9.6 with a cleared Apple bytecode cache (`terminal-replay-off2.json`, `8d904a6`; command in
  `terminal-replay-off2.cmd.txt`; driver `replay_hotel_off2.py`, `81a835a`): 30 of 30 cells replay valid, 30 of 30 byte-equal to the retained cell terminal, campaign level
  `candidateCampaignValid` true and byte-equal to the host's `campaign-terminal.json`.
- Chain, each output committed unedited before it was read: training readout `readout-hotel-offpath-off2-train-v3.7` (`488ebd1`; `campaignsRead` = off2 only, 18 of
  18 valid training cells; `provenance.input.sha256` `0a92f754…`; the scoring readout's is `aaa6e3b1…`, not off1's `5c8e5013…`, the like-for-like comparison; neither readout records the
campaign ID and the run IDs equal off1's, so identity rests on the fetch path, the content digests and the replay's campaign-ID assertion), placement `placement-off2.json` (`5f0504c`, sha256 `625d2b8b…`), pin `f93062c`, scoring
  readout `readout-hotel-offpath-off2-score-v3.7` (`67d50d4`), scorer `hotel-off2.json` / `.md` (`ea3491f`), predictions `PREDICTIONS_SCORED_HO2.json` (`967306d`, script
  `12e56a9` committed before it ran).

## Verdicts (V37_PASS_RULE; `hotel-off2.json` `inputs.passRuleSource`; its `passRuleNote` text is score_test_v3_2's inherited label)

| class, rate | frozen set (frontier any/any @6/T_r) | price, budget | training g (all 6 training episodes) | test: ledger / set (s) | g (test, class / all) | improved | verdict |
|---|---|---|---|---|---|---|---|
| consul pause, 1 req/s | empty (ledger only) | 0, 40/h | 0.000 | miss / miss, miss / miss | 0.000 | 0 of 2 | **FAIL** |
| consul pause, 10 req/s | `metric:attractions:sys_memory` | 19.97/h, 40/h | 15.054 | miss / 14.78, miss / miss | 22.608 / 11.304 | 1 of 2 | **FAIL** |

T_r = 0.15 h per rate (3 training no-fault cells; `placement-off2.json` `rates.*.hours`), so 6/T_r = 40/h and 19.97/h is the zero-alarm floor of 0.15 h. Ground set 302
(rate 1) and 303 (rate 10) sensors in the placement, all tier-missing (only the any/any cell is defined). Training detections by the @6/T_r point: 3 of 6 episodes at
rate 1, 5 of 6 at rate 10 (`placement-off2.json`, grid `describe.detectedEpisodes`). Absent members: 0.
Search pause (on-path control, no verdict): the ledger detects all 4 test episodes at 0.31 / 0.83 s (rate 1) and 0.26 / 0.28 s (rate 10). Every hold is 60.0 s.

## Predictions (declared before launch, informed by the off1 dry run; `PREDICTIONS_SCORED_HO2.md`)
| id | prediction | result |
|---|---|---|
| HO2-V | not PASS at either rate | **hit**: FAIL at rate 1 and at rate 10 |
| HO2-L | the ledger alone detects at most 1 of the 4 off-path test episodes | **hit**: 0 of 4 |
| HO2-C | search pause: the ledger detects 4 of 4 test episodes | **hit**: 4 of 4 |

## What this does and does not say
- On the declared negative control the frozen rule did not pass at either rate (instance). At rate 1 the FAIL is fixed by training: no sensor had a counted fire in
  >= 2 of the 3 training consul-pause episodes, so the set is empty and g = 0 by construction. At rate 10 the set is a single memory sample (`sys_memory`) of a service that is not
  the target (`attractions`), priced at the zero-alarm floor, which fires in 1 of the 2 consul-pause test episodes (14.78 s) and not in the other; the rule's ">= 2 of 2"
  requirement is what makes this a FAIL (g 22.608 > 0). The declaration's premise is that no coordinator observes consul and there is no queue; this run does not test it. The fire is not shown to be related to the
  pause: in training the same sensor recurs on the search-pause class as well as the consul-pause class (`placement-off2.json` `rates.10.recurrence.recurringByClass`),
  and at rate 1 it is priced 316.94/h (`rates.1.costs`).
- The rate-10 set differs from the post hoc off1 dry run's (`span:rate:/rate.Rate/GetRates`, also 1 of 2; FREEZE_V37 dry-run section; uncommitted output, placement
  `61fd3472…`): the selected sensor differed between the two runs of the same plan (instance), as between F and F's rerun.
- Power is low: n = 2 test episodes per rate, and the recurrence filter (decision 112) leaves 2 of 302 (rate 1) and 7 of 303 (rate 10) candidates, of which 0 and 1
  recur on the consul-pause class; the budget did not bind (the @6/T_r set equals the @inf set at both rates).
- A FAIL here is weak evidence (instance, n = 2 per rate): it says only that this rule did not produce a false pass on this run. It does not say that no sensor fires
  during the consul pause: the unbudgeted `full` comparator has a counted fire in 3 of the 4 consul-pause test episodes (rate 1: 3.33 s, 7.24 s; rate 10: 14.78 s;
  `hotel-off2.json`), and its fresh false-alarm rate is `—`.
- Scope: one host, one run, 2 test episodes per class and rate. The readout's inherited `v32.edgesDeclaredNotObserved` / `offPathClasses` / `v33.epochsAddedByV33` fields are
  not quoted (review N2 of v3.7).
