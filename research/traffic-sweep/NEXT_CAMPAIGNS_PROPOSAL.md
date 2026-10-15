# Next campaigns: proposal (2026-10-04; sizes are the user's to set, nothing frozen)

Agreed in protocol round 9, item 46:
- (1) a long no-fault calibration run per system;
- (2) repeat episodes on TeaStore and OTel;
- (3) closing the loop, after the placement step.

The harness changes agreed for later runs: H10 (no readiness probe during the fault) and H4 (stamp the freeze). Costs
use the measured cell durations, about 4.2 min per cell on Hotel (64 cells, 13:46-18:14Z on 2026-10-03), about 5.6 on
TeaStore and about 5.5 on OTel. The three hosts run in parallel.

## A. Quiet calibration run (no faults): what false-alarm rate can be certified
- **Why.** With 0 false alarms in T hours of quiet data, the 95 % upper bound is 3/T per hour. Today a rate has ~12 min
  of no-fault time, ~24 min with pre-onset minutes, so ≤ 15/h is the best certifiable. That is too loose for detectors
  that should be quiet.
- **Design.** No-fault cells only, same shape as the sweep (30 s warm-up, 180 s measurement, posture `full`), at each of
  the 4 rates. Same cell shape means no harness change, so no new guard surprises.

| target (95 %, 0 alarms) | quiet time per rate | no-fault cells per system | Hotel | TeaStore | OTel |
|---|---|---|---|---|---|
| ≤ 6/h | 30 min | 40 | ~2.8 h | ~3.7 h | ~3.7 h |
| ≤ 3/h | 60 min | 80 | ~5.6 h | ~7.5 h | ~7.3 h |

Quiet cells from B below add to these totals.

## B. Repeat episodes on TeaStore and OTel
- **Why.** One episode per condition is descriptive only. Cross-system claims need repeats; Hotel has 4.
- **Design.** 3 more blocks each, giving 4 like Hotel: 3 regimes × 4 rates × 3 = 36 cells per system, ~3.4 h on
  TeaStore and ~3.3 h on OTel. Each block's 4 no-fault cells also add 12 min of quiet time per rate.
- **Harness first:** H10 (no readiness probe during the fault, which removes the 5 s sensor handicap under a pause) and
  H4 (record when the fault command returns for throttle and netem; the Docker `pause` event is already kept). Each SUT
  then needs a new epoch commit, a re-pin, tests and a dry run, about half a day of build per SUT, with the usual
  first-run risk.

## C. Closing the loop (later)
Run the placement CELF chooses as a real posture and compare predicted vs measured detection. This comes after the
placement step; it gets its own proposal then.

## Recommendation
- **A at ≤ 6/h** on all three systems, now (no harness change).
- **B with the H10/H4 harness**, after A. Repeats run on the corrected harness rather than repeating its known flaws.
- A new budget and stop rule, committed alone before either, following `BUDGET_REPLICATION.md`: 2 relaunches per
  campaign, and 3 critical-path defects stop the SUT.
