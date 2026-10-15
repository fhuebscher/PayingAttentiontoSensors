# R2: campaign F with a new seed (attempt 4): result (2026-10-16)

Scope: **instance** (OTel Demo 1.12.0, fb14srv6, 25 req/s of the upstream mix, 5 blocks, n = 2 test episodes per class). Every number below is copied from the
committed file named beside it. **Review status:** one same-provider adversarial review (2026-10-15 ~14:00Z): chain order, verdicts, set, prices, lanes, fresh false
alarms and prediction scoring confirmed; three sentences replaced; no cross-provider review of this note. Two steps share one second with their commit, so "committed
before it ran" is consistent but not strictly provable there.

- Declaration `research/traffic-sweep/DECLARATION_F_OTEL_SEED2.md` (committed alone before launch); `DECLARATION_F_OTEL.md` (`8845721`) binding for the design,
  pass rule (V32_PASS_RULE) and decision 73. Harness `f08ba1d` (= F's `715d57b` + schedule seed 20261016; 4 of 5 block orders and all 25 onsets differ from F's),
  plan `6bc8c84a…` (attempt 4). Run order `research/placement/test-f-seed2/RUN_ORDER.md` (`644f0c5`; deviation `b5b4a90`: the fetch read is `fs1-fetch2`, because a VPN
  drop interrupted `fs1-fetch`, kept unverified and unused).
- Run: launched 2026-10-15 08:16Z, terminal 10:43:53Z (launch log `scratchpad/gate-drivers/otel-offpath-f-v1-fs1-launch.log`, uncommitted). Fetch
  `tmp/otel-f-evidence/fs1-fetch2`: 437/437 byte-verified (`fetch-otelFS1b.log`, uncommitted).
- Offline terminal replay at `f08ba1d` (`terminal-replay-fs1.json`, `8171b16`; command in the commit message; byte-equal under `/usr/bin/python3` 3.9.6): `pass`, 25 of 25
  valid, all attempt 4.
- Chain, each output committed unedited before it was read: training readout `readout-otel-fs1-train-v3.3` (`1207a39`; `campaignsRead` = fs1-fetch2 only, 15/15;
  calibration byte-equal on a second run), placement `placement-fs1.json` (`005a3a5`, sha256 `633b89f1…`), pin record in `FREEZE_V33_20261014.md` ("Replicate FS1 pin",
  `eda57e5`), scoring readout `readout-otel-fs1-score-v3.3` (`9d140f7`; 25/25), scorer `otel-fs1.json`/`.md`/`.override.json` (`8ae993f`; recorded pin 633b89f1, F's pin
  unchanged), post hoc lanes `research/lanes/out-fs1-posthoc` (`f3723cf`), fresh false alarms `fresh-fa-fs1` (`e6cbdab`) and `fresh-fa-fs1-flagd.json` (script `fresh_fa_partial_fs1.py`
  committed before it ran), predictions `PREDICTIONS_SCORED_FS_v2` (script committed before it ran; see "Corrections").

## Verdicts (V32_PASS_RULE, `otel-fs1.json` `rates.25.verdicts`)

| class | set | verdict |
|---|---|---|
| frauddetectionservice pause | `frontier (effort<=any, runtime<=any) @6/T_r` | **PASS** (g = 55.825 s, 2 of 2 improved) |
| accountingservice pause | same | **PASS** (g = 55.898 s, 2 of 2 improved) |

The frozen @6/T_r set has **two** members: `metric:kafka:kafka.consumer_group.lag` and `metric:flagd:feature_flag.flagd.impression`, each priced 9.99/h
(`placement-fs1.json` `rates.25.costs`), summed 19.97/h under 6/T_r = 20.0/h with T_r = 0.30 h. The @3/T_r set is the lag sensor alone (6/6 detected, g over all six
test episodes 37.240 s vs 37.241 s for the @6/T_r set; `otel-fs1.json`).

## Test episodes (`otel-fs1.json` `rates.25.episodes`; seconds after the pause command's stamp; "miss" = no counted fire in the hold)

| test episode | ledger alone | frozen set |
|---|---|---|
| accounting, block 4 | miss | 4.04 |
| accounting, block 5 | miss | 4.26 |
| fraud, block 4 | miss | 4.37 |
| fraud, block 5 | miss | 4.10 |
| frontend, block 4 | 0.46 | 0.46 |
| frontend, block 5 | 0.39 | 0.39 |

In accounting b4, b5 and fraud b4 the first counted fire is the lag sensor's `spike` rule (4.04-4.37 s; scoring readout `episodes[].fires`); in fraud block 5 flagd's
`median` fires at 4.097 s, 4.5 ms before lag's `spike` at 4.102 s, which is why the set's fraud g (55.825) is above lag alone (55.823, lanes zero-alarm row). flagd has no
counted fire in the other three off-path test episodes. **Not specific to the off-path faults:** in both frontend-pause test episodes the set has counted fires too (flagd
impression at 4.31 and 4.47 s; lag `run3`/`median` at 14.09-14.32 s), after the ledger (0.39-0.46 s), so g = 0 for that class. Lag's `spike` also fires uncounted at
4.32 / 4.09 s; every member fire in the frontend episodes points down, every member fire in the off-path episodes points up (scoring readout `episodes[].fires`).
"Not specific" holds for a counted fire, not for its direction.

## Lanes (post hoc, `research/lanes/out-fs1-posthoc/posthoc_lanes_v33_otel.json`, F's lane rules)
- Own silence (by-construction field): 1.32-1.56 s in 4/4 off-path test episodes (`orders_receive` `absent`).
- Kafka coordinator log (counted): 42.50-43.79 s in 4/4; no fire in either field in the two frontend episodes.
- Lag: 2 lag ids armed; lag fires before the coordinator in 4/4.

## Fresh false alarms on R2's 4 held-out no-fault cells (POST HOC; 0.2 h; frozen training calibration)
| sensor | alarms | 95 % upper /h | training price /h | source |
|---|---|---|---|---|
| `kafka.consumer_group.lag` (R2's and F's frozen member) | 0 | 14.98 | 9.99 | `fresh-fa-fs1/fresh_fa_f.json` |
| `kafka.request.count` (F's @3/T_r and the ablation's set) | 0 | 14.98 | 15.81 | same |
| `feature_flag.flagd.impression` (R2's second member; calibrated rules run3 + median only, spike dropped in calibration) | 1 (median) | 23.72 | 9.99 | `fresh-fa-fs1-flagd.json` |
The frozen set raised 1 alarm in 0.2 h. With 0.2 h no outcome can bound a rate below 14.98/h; not an equivalence test. flagd's fresh 95 % upper bound 23.72/h is above the 20/h budget (as the rerun's note
stated for its own sensor). FS-FA was scored through the post hoc partial script, a path the declaration does not name; both tmp validation readouts already held flagd = 1
when that script was written (its logic does not depend on the result). `fresh_fa_fs1.py` refuses the flagd sensor by
its documented assertion (all three rules calibrated), hence the separate calibrated-rules count; that script checks its calibration equals the training readout's.

## Predictions (declared before launch; `PREDICTIONS_SCORED_FS_v2.md`)
| id | prediction | result |
|---|---|---|
| FS-V1 | PASS for both off-path classes | **hit** |
| FS-V2 | the frozen @6/T_r set is one `metric:kafka:*` id | **miss**: two members, lag and a flagd metric |
| FS-L1 | ledger detects at most 1 of 4 off-path test episodes | **hit**: 0 of 4 |
| FS-L2 | counted Kafka coordinator log fire 42-47 s in 4/4 | **hit**: 42.50-43.79 s |
| FS-C | frontend: ledger first (< 1 s) in 2/2, g = 0 | **hit**: 0.39 / 0.46 s, g 0 |
| FS-FA | frozen set raises at most 2 alarms in 0.2 h | **hit**: 1 |

## What this does and does not say
- With a new seed (new block orders and onsets), F's rule passes both off-path classes again (instance), the third PASS of this design under V32_PASS_RULE (F
  attempt 1, F's same-schedule rerun attempt 3, R2 attempt 4); the no-lag ablation, a variant without the kafkametrics receiver (4ab4433, v3.5 chain), also passed under the
  same rule; each verdict rests on 2 test episodes per class on one host at one rate.
- The frozen set differs again: F chose lag alone, F's rerun `purgatory.size`, the ablation `request.count`, R2 lag plus a flagd metric. Lag returns here, priced 9.99/h
  (F: 15.81/h; rerun: 35.04/h, above the budget). Across the three runs of this design the @6/T_r set is {lag}, {purgatory.size}, {lag, flagd}; lag is chosen in 2 of 3 (priced 15.81, 35.04, 9.99/h); the
  ablation, without lag ids by construction, chose request.count. Each run's chosen ids have counted fires in 2 of 2 frontend-pause test episodes (the F, rerun and ablation
  scoring readouts: readout-otel-f-score-v3.3, readout-otel-f3-score-v3.3, and the ablation's v3.5 scoring readout). Post hoc (review's check from the committed scoring
  readouts): lag has a counted fire in 4 of 4 off-path test episodes in each of F, the rerun and R2 (12 of 12, first fires 4.04-9.40 s); purgatory.size has 0 of 8 counted
  off-path fires across F and R2. That the placement replicates cannot be said: three runs gave three sets.
- R2 vs F is a new draw of the same randomisation (onsets move by at most 31.5 ms, order at 10 of 25 positions), not a test of sensitivity to onset timing. The compiler's
  order rule (`candidate_offpath_f.py:25-26`, fseed worktree) always puts the two no-fault cells first and the frontend pause last, so the seed only swaps the no-fault pair
  and the fraud/accounting pair within a block (order differs at 10 of 25 positions, blocks 1, 3, 4, 5; onsets differ by 0.062-31.508 ms). F and its rerun had identical
  schedules (`test-f-rep1/onsets_f1_vs_f3.json`) and still chose different sets, so the instability cannot be attributed to the seed.

## Corrections
- The first prediction output (`PREDICTIONS_SCORED_FS.json/.md`, `f5ced86`) scored FS-FA `-` because the script looked up fresh-FA rows by the short metric name
  while the rows carry the full sensor id; the script was corrected (`4971108`) and re-run to `PREDICTIONS_SCORED_FS_v2` (`c04794f`). The first output is kept.
- An attempt to price the flagd member with `fresh_fa_fs1.py --set` refused (assertion, spike not calibrated); it left an empty directory
  `research/placement/test-f-seed2/fresh-fa-fs1-own/` (untracked) and a 78 MB validation readout in `tmp/fresh-fa-fs1-own/`, which `fresh_fa_partial_fs1.py` reads.
