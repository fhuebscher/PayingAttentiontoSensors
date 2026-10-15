# R6: campaign F's design on new cells (attempt 8): result (2026-10-15 UTC)

Scope: **instance** (OTel Demo 1.12.0, fb14srv6, 25 req/s of the upstream mix, 5 blocks, n = 2 test episodes per class). Every number below is copied from the
file named beside it: committed unless marked uncommitted; the host-check, step 0 and step 1b numbers come from session output copied into commit messages (last section).
**Review status:** one same-provider adversarial review (Claude `adversarial-review` subagent, 2026-10-15, received ~20:12Z): every checked number and the chain order confirmed; sentences replaced and
omissions added as listed in `research/protocol/REVIEWS_LAST_RUNS_20261015.md`; no cross-provider review. By the budget (`BUDGET_OVERNIGHT_20261015.md:26`) a result enters the paper only after
one same-provider review, by 2026-10-16 06:00Z.

- Declaration `research/traffic-sweep/DECLARATION_OTEL_R6.md` (`0ee8d62`, committed alone before launch; its status line records the same-provider review as NO-GO on text points T1-T13, applied there, and no separate GO record was found;
  the budget (`BUDGET_OVERNIGHT_20261015.md:22`) requires a review GO of the declaration before launch: whether a GO was given and not recorded is for the user to state); `DECLARATION_F_OTEL.md` (`8845721`) binding for the design,
  pass rule (V32_PASS_RULE) and decision 73. F's descriptor `6164052d…`, F's harness `715d57b` (worktree `observability-placement-runtime-otel-protocol`, clean), plan
  `38ff4d32d6060f7f73dd29d57718ef0d9c6234ed74214bb60d22888903e41b3c` (attempt 8; from the replayed plan's `construction-receipt.json`). Run order
  `research/placement/test-f-r6/RUN_ORDER.md` (`7894b9b`, addendum `d9526d0`, host archive output `813047b`).
- Run: DRY_RUN `r6dry` 16:42:56Z (`paths=0`, `DRY RUN: all guards passed`; `scratchpad/gate-drivers/otel-offpath-f-v1-r6dry-launch.log`, uncommitted, sha256 `8b6b71c5…`);
  launcher started 16:43:07Z (GATE-RUN executed 16:47:00Z, `gate-run.json` `approvedAt`; `oneshot rc=0` 16:48:26Z), terminal 19:10:47Z (`state=stopped systemd=inactive/dead result=success terminal=True abort=False`; launch log
  `scratchpad/gate-drivers/otel-offpath-f-v1-r6-launch.log`, uncommitted, sha256 `c115b2bf898de7c2cd5daeba3c021795b5e6bd8e985512cf1248ade853c8414b`). The launcher's
  "not under caffeinate" WARN is present, as the declaration expects. Host checked before the fetch (19:11:48Z host clock): 0 containers, 0 running/activating candidate units
  (two TeaStore `teastore-candidate-v4-*` units from earlier work are listed in state `failed`, not running; no OTel unit). `remote-terminal.json`: attemptedCells 25, validCells 25,
  stopped false.
- Fetch `tmp/otel-f-evidence/r6-fetch` (`bash scratchpad/gate-drivers/fetch_r6.sh otelR6`, sha256 `906e5173…`, `26223b5`): host package check `cells 25 bad 0`; host files 437, OK 437,
  shasum rc 0 (`scratchpad/gate-drivers/fetch-r6.out`, uncommitted, sha256 `43c6dd22…`).
- Binding check (RUN_ORDER step 1b), rc 0: `cells 25 sortedRunIdSha256 ed0d0764ed158209a57f2a11062561ccca0cce8b2c38b568e0a497c98b4ed45f badCells []`; execution package sha256 `4f83d093…`.
  `G/gate-run.json` is R6's: `frameworkCommit` `715d57b5…`, `binding.attempt` 8, `typedApproval` equal to the launch log's GATE-RUN line.
  That sentence was harness-derived and executed without a prompt (launch log :50-58), although `gate-run.json` records `approvedBy` "Florian Huebscher". SETUP-CAMPAIGN was renewed
  at launch after `invariants match=False` (:17); the log marks it "typed by Claude under the TEMP delegation" (:29).
- Offline terminal replay at `715d57b` (`terminal-replay-r6.json`, `be2339f`, sha256 `a84413df…`; command and input digests in the commit message; byte-equal under `/usr/bin/python3` 3.9.6):
  `pass`, 25 of 25 valid, all attempt 8.
- Chain, each output committed unedited before it was read (stdout of every tool redirected to a log, read only after the commit; the exception is the declared determinism
  pre-check, which compared the training readout's calibration with a second run before the commit; the training and scoring readouts record repo HEAD `be2339f` and `8f7fdc1` in
  `frameworkCommit`, so the scoring readout ran after the freeze entry; the scorer output is 3 s after the scoring readout's commit and records no HEAD, so that order is consistent
  with the timestamps, not proven by them; every recorded input digest equals the committed file): training readout `readout-otel-r6-train-v3.3`
  (`cbbbf45`, sha256 `c7e11e2e…`; `campaignsRead` = r6-fetch only, 15/15; calibration equal as sorted-key JSON on a second run), placement `placement-r6.json` (`dbe2df7`, sha256
  `89b8a58c9f7a8285ca621172b33410a54e51c225356d86c64d0f5f32bd722373`), pin record in `FREEZE_V33_20261014.md` ("Replicate R6 pin", `8f7fdc1`, committed alone), scoring readout
  `readout-otel-r6-score-v3.3` (`7e36fc7`, sha256 `13d7d5d5…`; 25/25; calibration equal to the training readout's), scorer `otel-r6.json`/`.md`/`.override.json` (`b1a18d9`; recorded pin
  89b8a58c, F's pin unchanged), transfer `transfer-r6/` and consistency run `transfer-r6-own/` (`553879a`; `tests/test_transfer_score.py` 13 passed first, session output, not retained), predictions `PREDICTIONS_SCORED_R6` (`60de8b4`).
  Step 0 (frozen digests): exactly one line, `research/placement/score_test_v3_3.py: FAILED`, as expected.
  `score_rep_r6.py` and `score_predictions_r6.py` were tested on synthetic and R2 inputs only, with the `score_test_v3_3.main` override path stubbed, and had no independent review
  before this run (RUN_ORDER, "What this record does not cover").

## Verdicts (V32_PASS_RULE, `otel-r6.json` `rates.25.verdicts`)

| class | set | verdict |
|---|---|---|
| frauddetectionservice pause | `frontier (effort<=any, runtime<=any) @6/T_r` | **PASS** (g = 55.813 s, 2 of 2 improved) |
| accountingservice pause | same | **PASS** (g = 55.721 s, 2 of 2 improved) |

g_E is the class mean over 2 test episodes of (ledger penalised - set ttd). A ledger miss is charged the measured hold (60.05-60.06 s, `holdSeconds`), so 55.7-55.8 s is the hold
minus the set's 4.1-4.6 s: it follows from the miss charge, not from a measured ledger time.

## Frozen set and prices (`placement-r6.json` `rates.25`, grid cell (any, any))

| point | set | charged /h |
|---|---|---|
| @3/T_r (budget 10.0/h) | `metric:kafka:kafka.consumer_group.lag` | 9.99 |
| **@6/T_r** (budget 20.0/h) | `metric:kafka:kafka.consumer_group.lag` | 9.99 |
| @inf | lag + `span:cartservice:POST_/oteldemo.CartService/AddItem` (15.81/h) | 25.80 |

T_r = 0.30 h of training no-fault time (`hours`). The lag sensor raised 0 alarms on the training no-fault cells (training readout `placementFalseAlarms.primary.allPlaceable.25.perSensor`);
its price 9.986/h is the zero-alarm upper bound (`honestUpperPerHour`, 2.996 per T_r = 0.30 h), set by T_r and not by an observed alarm; R2's two members carry the same figure for the same reason (instance, OTel, one run; analysis item 3: no fresh-false-alarm check, so this price is not checked
on held-out time). The @6/T_r set has the same member id as F's @6/T_r set; the two placement files differ (`89b8a58c…` vs `ce6bfc1b…`) they are computed from different training readouts (F priced lag 15.81/h, R6 9.99/h).
Training fit (blocks 1-3, 9 episodes): g 37.205 s, 9/9 detected (`points["6/T_r"]`). Test (6 episodes, all classes): D 2.988 s vs ledger 40.166 s, g 37.178 s, 6/6 detected (`otel-r6.json` `rates.25.sets["frontier (effort<=any, runtime<=any) @6/T_r"]`).

## Test episodes (`otel-r6.json` `rates.25.episodes`; seconds after the pause command's stamp; "miss" = no counted fire in the hold, about 60 s)

| test episode | ledger alone | frozen set {lag} |
|---|---|---|
| accounting, block 4 | miss | 4.09 |
| accounting, block 5 | miss | 4.57 |
| fraud, block 4 | miss | 4.13 |
| fraud, block 5 | miss | 4.36 |
| frontend, block 4 | 0.42 | 0.42 |
| frontend, block 5 | 0.35 | 0.35 |

In all four off-path test episodes the frozen set's first counted fire is lag's `spike` rule, direction up (4.09-4.57 s), followed by `run3`/`median` 10.00-10.01 s later (scoring readout `episodes[].fires`).
`kafka.purgatory.size` and `feature_flag.flagd.impression` have no fire in any of the four off-path test episodes. **Not specific to the off-path faults:** in both frontend-pause test
episodes lag has counted fires too (`run3`/`median` at 14.30 and 14.78 s, direction down; its `spike` fires uncounted at 4.30 / 4.78 s, down), after the ledger (0.35-0.42 s), so g = 0
for that class. As in R2, every lag fire in the frontend episodes points down and every lag fire in the off-path episodes points up; "not specific" holds for a counted fire, not for its direction.

## Transfer of the frozen sets (POST HOC to the sets; `transfer-r6/transfer.json`, thresholds from R6's own training calibration, @6/T_r, test blocks 4-5)

| frozen set (source) | class | improved | g (s) | verdict |
|---|---|---|---|---|
| F {lag} (`placement-f.json`, `ce6bfc1b…`) | fraud | 2/2 | 55.813 | PASS |
| | accounting | 2/2 | 55.721 | PASS |
| rerun {purgatory.size} (`placement-f3.json`, `674580e0…`) | fraud | 0/2 | 0.000 | FAIL |
| | accounting | 0/2 | 0.000 | FAIL |
| R2 {lag, flagd impression} (`placement-fs1.json`, `633b89f1…`) | fraud | 2/2 | 55.813 | PASS |
| | accounting | 2/2 | 55.721 | PASS |

No member is absent from R6's scoring ground set (`absent members: none`). Consistency check (budget item 2): `transfer-r6-own` on `placement-r6.json` reproduces `otel-r6.json` `rates.25`
episodes and @6/T_r verdicts (`PREDICTIONS_SCORED_R6.json` `consistencyCheck: pass`, 0 mismatches), so, by the declared rule, the transfer rows are not dashed. F's set and R6's own set have the same member, so
F's transfer rows repeat R6's own verdicts by construction (same set, episodes and thresholds); R2's set adds flagd, which has no off-path fire here, so its rows equal lag's.

## Predictions (declared before launch; `PREDICTIONS_SCORED_R6.md`; counted 5 hit, 0 miss, 0 undecided, of 5)

| id | prediction | result |
|---|---|---|
| FR6-V1 | PASS for both off-path classes | **hit** |
| FR6-V2 | the frozen @6/T_r set contains `kafka.consumer_group.lag` | **hit**: {lag} |
| FR6-L1 | ledger detects at most 1 of 4 off-path test episodes | **hit**: 0 of 4 |
| FR6-C | frontend: ledger first (< 1 s) in 2/2, g = 0 (control, not counted) | **hit**: 0.42 / 0.35 s, g 0 |
| TR6-LAG | F's {lag} transfers: PASS both classes | **hit** |
| TR6-R2 | R2's {lag, flagd} transfers: PASS both classes (reported, not counted) | **hit** |
| TR6-PUR | the rerun's {purgatory.size}: not PASS for at least one class | **hit**: FAIL both |

FR6-V1 and TR6-LAG are one result counted twice: R6's set equals F's ({lag}), so both score the same set on the same episodes with the same thresholds. FR6-V2 says only that the
set contains lag; the equality, not FR6-V2, makes them the same. The 5 counted hits are 4 distinct outcomes.
No `—` arose, so the dash readings of the addendum (item 4) were not exercised.

## What this does and does not say
- On new cells with F's descriptor and F's schedule, F's rule passes both off-path classes (instance). Across the runs of this design under V32_PASS_RULE that verdict is PASS in
  4 of 4 scored runs (F attempt 1, F's rerun attempt 3, R2 attempt 4, R6 attempt 8); two other executed attempts of this design have no verdict: attempt 2 stopped after 13 cells
  (`RESULT_F_REP1.md:92`), and attempt 6 (R4) ran the same schedule but its 15 fault cells are unread by its declaration; the no-lag ablation, a variant, also passed and is not in that count. Each verdict rests on 2 test episodes
  per class on one host at one rate; nothing here is pooled.
- R6 is a same-descriptor, same-schedule rerun (order and onsets equal to attempts 1 and 3 at every cell, per the declaration's pre-launch compile check, output not retained), not a new draw of the
  randomisation; it says nothing about sensitivity to the schedule. F and its rerun had identical schedules and chose different sets; R6, on the same schedule, chose F's.
- The @6/T_r set across the four runs: {lag}, {purgatory.size}, {lag, flagd impression}, {lag}; lag chosen in 3 of 4, at training prices 15.81, —, 9.99, 9.99/h (the rerun priced lag
  at 35.04/h, above its budget, and did not choose it). That the placement is stable cannot be said from four runs that gave three distinct sets.
- Counted fires in off-path test episodes (scoring readouts): lag 4 of 4 in each of F, rerun and R2 (post hoc, `RESULT_F_SEED2.md:85`) and in R6; purgatory.size 0 of 4 in each of F,
  R2 and R6, against 4 of 4 on the rerun's own run (first counted fires 1.15-11.65 s, `readout-otel-f3-score-v3.3`, equal to the set ttd in `test-f-rep1/otel-f3.json`). Not summed: the
  rerun and R6 share F's schedule, and nothing here is pooled. The transfer FAIL of {purgatory.size} is a statement about these cells; why the rerun's sensor fired there and not here is not established.
- The ledger alone detects 0 of 4 off-path test episodes here (F 1/4, rerun 0/4, R2 0/4). The lag member also fires (counted, down) in both frontend-pause test episodes, after the ledger.
- No mechanism is claimed. The price 9.99/h rests on 0 alarms in 0.30 h of training time; no held-out false-alarm check was declared for R6.

## Notes and small deviations
- RUN_ORDER step 1 asks for "no `otel_candidate`/`candidate-v4` unit". `systemctl list-units --all` lists two `teastore-candidate-v4-*` units in state `failed` (TeaStore releases, framework
  `8c4d805b`), not running; the declaration's own check form (`--state=running,activating`) counts 0. Recorded, not treated as a blocker.
- RUN_ORDER step 2 asks for the Apple bytecode cache to be cleared. It held 0 entries for the worktree's paths, so nothing was deleted; both replays ran with their own fresh
  `PYTHONPYCACHEPREFIX` and `PYTHONDONTWRITEBYTECODE=1`.
- The scorer's markdown header reads "Campaign E test scoring": it is `score_test_v3_3`'s fixed template text (unedited frozen file), not a label of this run.
- Steps 0, 1b and the host checks printed their outputs to the session only; their numbers are copied into the replay commit message (`be2339f`) and the freeze entry (`8f7fdc1`); the
  terminal outputs themselves are not retained as files. Also not retained: the 3.9 replay scratch output (byte-equal, sha256 in `be2339f`) and the pytest run.
- RUN_ORDER addendum item 2: the fetch is a separate script, `fetch_r6.sh`, not a case added to `fetch_overnight.sh` as the declaration's "Fetch" line says.
- RUN_ORDER addendum item 5: `score_rep_r6.py` carries `campaignsRead`/`calibration` refusals beyond the declaration's "changed only in"; both passed on R6's readouts.
- wandb logged the run offline (`tmp/wandb/wandb/offline-run-20261016_034308-i9ok2xta`, `scratchpad/gate-drivers/wandb-r6.out`); not synced.
- The launcher archived R4's local gate working set under the name `archived-run-20261015T164334Z-aborted` (launch log :9), although R4 ended normally; that is the launcher's naming only.
