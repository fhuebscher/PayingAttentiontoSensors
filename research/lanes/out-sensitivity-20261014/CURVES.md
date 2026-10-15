# Sensitivity curves: detection versus false-alarm budget (2026-10-14)

**POST HOC (not preregistered; computed after the readouts were seen).** Scope of every number: **instance** (one SUT, one host, one rate, one readout pair per system; test episodes: OTel E 6 (4 off-path, 2 on-path), TeaStore C 6 per rate, Hotel 12 per rate). Produced by `research/lanes/sensitivity_curves.py` from the committed readouts; nothing here is a pass rule and no frozen file was edited. Unknown is `—`, never 0.

## Definition

- **x**: false-alarm budget per hour, the knapsack budget B of decision 76. `0` = the ledger alone (plus any cost-0 sensor); then m x 3/T_r for m in 0.5, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64 (T_r = the rate's training no-fault hours; the unit is the frozen named 3/T_r = 3.0/T_r, not the exact zero-alarm bound 2.9957/T_r, so the points m = 1 and m = 2 are exactly the declared 3/T_r and 6/T_r); then 6, 20, 60, 200, 600, 2000 per hour; then `inf`. Budgets tied within 1e-9 merge. Declared points: 0, 3/T_r, 6/T_r, 6/h, inf (6/T_r is a v3.2 name; the grid carries it for every system).
- **set**: the CELF frontier set (effort<=any, runtime<=any) solved on the TRAINING readout at that budget with the frozen `celf_v3.solve` (OTel E: over the candidates that pass decision 112's recurrence rule, as `celf_v3_2.frontier_rate`; TeaStore and Hotel: `celf_v3`'s primary arm, which has neither tiers nor the recurrence rule). Two prices: **decision 73** as frozen, and the **post hoc zero-alarm** price (`posthoc_lanes_v33.zero_alarm_costs`: an appear-only id evaluated in 0 folds costs 2.9957/T_r instead of the rate's largest evidenced bound).
- **test episodes**: OTel E, the scoring readout's held-out blocks 4-5 (frozen sets scored as frozen); TeaStore, campaign C (campaignIndex 5 of the C readout) with the set solved on the training readout; **Hotel has no held-out campaign, so the curve is leave-one-block-out on its training readout** (celf_v3's fold key (harness, block); each block scored with the set solved on the other three blocks, the 12 held-out episodes pooled). A set member absent from the scoring readout's ground set never fires.
- **partial**: share of test episodes detected (a counted fire of the ledger or of a set member within the hold). **strict**: share of fault classes in which every test episode is detected. **median penalised s**: median over test episodes of the time to detection, a miss charged the hold (~60 s). **g**: D(ledger alone) - D(set), the frozen class-weighted mean penalised time, weights recomputed on the group's episodes (as the frozen scorer does).
- **groups**: OTel E is split into `offpath` (fraud and accounting pauses, 2 + 2 episodes) and `onpath` (frontend pause, 2 episodes); TeaStore and Hotel use `all` classes. With 2 classes strict takes the values 0, 0.5, 1; with 1 class 0 or 1.
- **comparators** are drawn at their charged price: `full` (the training ground set), `out of the box` (E: every ground-set sensor of effort tier 0; there is no effort file for TeaStore or Hotel, so there the declared postures `none` and `selected` stand in, restriction estimates of decision 78 and not the shipped system).
- **plotted rate**: OTel E has one rate (25 req/s). TeaStore and Hotel have four; the figure shows r0.2 (an engineering default: the rate decision 89 used; not a preregistered choice). All four rates are in `curves.json` and below.

## Cross-checks

All 16 checks PASS.

| check | ok |
|---|---|
| E decision 73 @0: set equals placement-e.json | PASS |
| E decision 73 @0: g and detected episodes equal otel-e.json | PASS |
| E decision 73 @3/T_r: set equals placement-e.json | PASS |
| E decision 73 @3/T_r: g and detected episodes equal otel-e.json | PASS |
| E decision 73 @6/T_r: set equals placement-e.json | PASS |
| E decision 73 @6/T_r: g and detected episodes equal otel-e.json | PASS |
| E decision 73 @6/h: set equals placement-e.json | PASS |
| E decision 73 @6/h: g and detected episodes equal otel-e.json | PASS |
| E decision 73 @inf: set equals placement-e.json | PASS |
| E decision 73 @inf: g and detected episodes equal otel-e.json | PASS |
| E comparator full: g and detected equal otel-e.json | PASS |
| E comparator out of the box: g and detected equal otel-e.json | PASS |
| E comparator ledger alone: g and detected equal otel-e.json | PASS |
| E zero-alarm @6/T_r: g = 5.292 and 5 of 6 detected (posthoc_lanes_v33 on E) | PASS |
| TeaStore decision 73 at the 4 named budgets x 4 rates (16 points): set equals the frozen placement, g and detected equal teastore-c.json | PASS |
| Hotel decision 73: the leave-one-block-out set of every fold at the named budgets equals the frozen placement's heldOut fold (64 folds) | PASS |

## OTel Demo, campaign E (off-path pauses)

**rate 25, decision73 pricing, group `offpath` (T_r = 0.15 h; 4 test episodes in the group)**

| budget /h | grid label | declared point | set size | charged /h | partial | strict | median penalised s | g s |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0.00 | 0.250 | 0.000 | 60.06 | 0.000 |
| 6 | 6/h | 6/h | 0 | 0.00 | 0.250 | 0.000 | 60.06 | 0.000 |
| 10 | 0.5x3/T_r |  | 0 | 0.00 | 0.250 | 0.000 | 60.06 | 0.000 |
| 20 | 1x3/T_r | 3/T_r | 1 | 19.97 | 0.250 | 0.000 | 60.06 | 0.000 |
| 40 | 2x3/T_r | 6/T_r | 1 | 19.97 | 0.250 | 0.000 | 60.06 | 0.000 |
| 60 | 3x3/T_r |  | 1 | 19.97 | 0.250 | 0.000 | 60.06 | 0.000 |
| 80 | 4x3/T_r |  | 1 | 19.97 | 0.250 | 0.000 | 60.06 | 0.000 |
| 120 | 6x3/T_r |  | 1 | 19.97 | 0.250 | 0.000 | 60.06 | 0.000 |
| 160 | 8x3/T_r |  | 1 | 19.97 | 0.250 | 0.000 | 60.06 | 0.000 |
| 200 | 200/h |  | 1 | 19.97 | 0.250 | 0.000 | 60.06 | 0.000 |
| 240 | 12x3/T_r |  | 2 | 203.04 | 0.750 | 0.500 | 44.18 | 7.938 |
| 320 | 16x3/T_r |  | 2 | 203.04 | 0.750 | 0.500 | 44.18 | 7.938 |
| 480 | 24x3/T_r |  | 3 | 386.11 | 1.000 | 1.000 | 44.01 | 11.972 |
| 600 | 600/h |  | 4 | 569.18 | 1.000 | 1.000 | 44.01 | 11.972 |
| 640 | 32x3/T_r |  | 4 | 569.18 | 1.000 | 1.000 | 44.01 | 11.972 |
| 960 | 48x3/T_r |  | 4 | 569.18 | 1.000 | 1.000 | 44.01 | 11.972 |
| 1280 | 64x3/T_r |  | 4 | 569.18 | 1.000 | 1.000 | 44.01 | 11.972 |
| 2000 | 2000/h |  | 4 | 569.18 | 1.000 | 1.000 | 44.01 | 11.972 |
| inf | inf | inf | 4 | 569.18 | 1.000 | 1.000 | 44.01 | 11.972 |

**rate 25, decision73 pricing, group `onpath` (T_r = 0.15 h; 2 test episodes in the group)**

| budget /h | grid label | declared point | set size | charged /h | partial | strict | median penalised s | g s |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0.00 | 1.000 | 1.000 | 0.36 | 0.000 |
| 6 | 6/h | 6/h | 0 | 0.00 | 1.000 | 1.000 | 0.36 | 0.000 |
| 10 | 0.5x3/T_r |  | 0 | 0.00 | 1.000 | 1.000 | 0.36 | 0.000 |
| 20 | 1x3/T_r | 3/T_r | 1 | 19.97 | 1.000 | 1.000 | 0.36 | 0.000 |
| 40 | 2x3/T_r | 6/T_r | 1 | 19.97 | 1.000 | 1.000 | 0.36 | 0.000 |
| 60 | 3x3/T_r |  | 1 | 19.97 | 1.000 | 1.000 | 0.36 | 0.000 |
| 80 | 4x3/T_r |  | 1 | 19.97 | 1.000 | 1.000 | 0.36 | 0.000 |
| 120 | 6x3/T_r |  | 1 | 19.97 | 1.000 | 1.000 | 0.36 | 0.000 |
| 160 | 8x3/T_r |  | 1 | 19.97 | 1.000 | 1.000 | 0.36 | 0.000 |
| 200 | 200/h |  | 1 | 19.97 | 1.000 | 1.000 | 0.36 | 0.000 |
| 240 | 12x3/T_r |  | 2 | 203.04 | 1.000 | 1.000 | 0.36 | 0.000 |
| 320 | 16x3/T_r |  | 2 | 203.04 | 1.000 | 1.000 | 0.36 | 0.000 |
| 480 | 24x3/T_r |  | 3 | 386.11 | 1.000 | 1.000 | 0.36 | 0.000 |
| 600 | 600/h |  | 4 | 569.18 | 1.000 | 1.000 | 0.36 | 0.000 |
| 640 | 32x3/T_r |  | 4 | 569.18 | 1.000 | 1.000 | 0.36 | 0.000 |
| 960 | 48x3/T_r |  | 4 | 569.18 | 1.000 | 1.000 | 0.36 | 0.000 |
| 1280 | 64x3/T_r |  | 4 | 569.18 | 1.000 | 1.000 | 0.36 | 0.000 |
| 2000 | 2000/h |  | 4 | 569.18 | 1.000 | 1.000 | 0.36 | 0.000 |
| inf | inf | inf | 4 | 569.18 | 1.000 | 1.000 | 0.36 | 0.000 |

**rate 25, decision73 pricing, group `all` (T_r = 0.15 h; 6 test episodes in the group)**

| budget /h | grid label | declared point | set size | charged /h | partial | strict | median penalised s | g s |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0.00 | 0.500 | 0.333 | 40.15 | 0.000 |
| 6 | 6/h | 6/h | 0 | 0.00 | 0.500 | 0.333 | 40.15 | 0.000 |
| 10 | 0.5x3/T_r |  | 0 | 0.00 | 0.500 | 0.333 | 40.15 | 0.000 |
| 20 | 1x3/T_r | 3/T_r | 1 | 19.97 | 0.500 | 0.333 | 40.15 | 0.000 |
| 40 | 2x3/T_r | 6/T_r | 1 | 19.97 | 0.500 | 0.333 | 40.15 | 0.000 |
| 60 | 3x3/T_r |  | 1 | 19.97 | 0.500 | 0.333 | 40.15 | 0.000 |
| 80 | 4x3/T_r |  | 1 | 19.97 | 0.500 | 0.333 | 40.15 | 0.000 |
| 120 | 6x3/T_r |  | 1 | 19.97 | 0.500 | 0.333 | 40.15 | 0.000 |
| 160 | 8x3/T_r |  | 1 | 19.97 | 0.500 | 0.333 | 40.15 | 0.000 |
| 200 | 200/h |  | 1 | 19.97 | 0.500 | 0.333 | 40.15 | 0.000 |
| 240 | 12x3/T_r |  | 2 | 203.04 | 0.833 | 0.667 | 32.17 | 5.292 |
| 320 | 16x3/T_r |  | 2 | 203.04 | 0.833 | 0.667 | 32.17 | 5.292 |
| 480 | 24x3/T_r |  | 3 | 386.11 | 1.000 | 1.000 | 32.09 | 7.981 |
| 600 | 600/h |  | 4 | 569.18 | 1.000 | 1.000 | 32.09 | 7.981 |
| 640 | 32x3/T_r |  | 4 | 569.18 | 1.000 | 1.000 | 32.09 | 7.981 |
| 960 | 48x3/T_r |  | 4 | 569.18 | 1.000 | 1.000 | 32.09 | 7.981 |
| 1280 | 64x3/T_r |  | 4 | 569.18 | 1.000 | 1.000 | 32.09 | 7.981 |
| 2000 | 2000/h |  | 4 | 569.18 | 1.000 | 1.000 | 32.09 | 7.981 |
| inf | inf | inf | 4 | 569.18 | 1.000 | 1.000 | 32.09 | 7.981 |

Comparators (decision73 pricing, rate 25):

| comparator | members (in training ground set) | charged /h | offpath partial / strict / g | onpath partial / strict / g | all partial / strict / g |
|---|---|---|---|---|---|
| ledger alone | 0 (0) | 0.0 | 0.250 / 0.000 / 0.000 | 1.000 / 1.000 / 0.000 | 0.500 / 0.333 / 0.000 |
| full | 4417 (4417) | 709683.0 | 1.000 / 1.000 / 47.639 | 1.000 / 1.000 / 0.000 | 1.000 / 1.000 / 31.759 |
| out of the box | 344 (344) | 9997.4 | 0.750 / 0.500 / 27.638 | 1.000 / 1.000 / 0.000 | 0.833 / 0.667 / 18.425 |

**rate 25, zeroAlarm pricing, group `offpath` (T_r = 0.15 h; 4 test episodes in the group)**

| budget /h | grid label | declared point | set size | charged /h | partial | strict | median penalised s | g s |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0.00 | 0.250 | 0.000 | 60.06 | 0.000 |
| 6 | 6/h | 6/h | 0 | 0.00 | 0.250 | 0.000 | 60.06 | 0.000 |
| 10 | 0.5x3/T_r |  | 0 | 0.00 | 0.250 | 0.000 | 60.06 | 0.000 |
| 20 | 1x3/T_r | 3/T_r | 1 | 19.97 | 0.250 | 0.000 | 60.06 | 0.000 |
| 40 | 2x3/T_r | 6/T_r | 2 | 39.94 | 0.750 | 0.500 | 44.18 | 7.938 |
| 60 | 3x3/T_r |  | 3 | 59.91 | 1.000 | 1.000 | 44.01 | 11.972 |
| 80 | 4x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 44.01 | 11.972 |
| 120 | 6x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 44.01 | 11.972 |
| 160 | 8x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 44.01 | 11.972 |
| 200 | 200/h |  | 4 | 79.89 | 1.000 | 1.000 | 44.01 | 11.972 |
| 240 | 12x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 44.01 | 11.972 |
| 320 | 16x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 44.01 | 11.972 |
| 480 | 24x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 44.01 | 11.972 |
| 600 | 600/h |  | 4 | 79.89 | 1.000 | 1.000 | 44.01 | 11.972 |
| 640 | 32x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 44.01 | 11.972 |
| 960 | 48x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 44.01 | 11.972 |
| 1280 | 64x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 44.01 | 11.972 |
| 2000 | 2000/h |  | 4 | 79.89 | 1.000 | 1.000 | 44.01 | 11.972 |
| inf | inf | inf | 4 | 79.89 | 1.000 | 1.000 | 44.01 | 11.972 |

**rate 25, zeroAlarm pricing, group `onpath` (T_r = 0.15 h; 2 test episodes in the group)**

| budget /h | grid label | declared point | set size | charged /h | partial | strict | median penalised s | g s |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0.00 | 1.000 | 1.000 | 0.36 | 0.000 |
| 6 | 6/h | 6/h | 0 | 0.00 | 1.000 | 1.000 | 0.36 | 0.000 |
| 10 | 0.5x3/T_r |  | 0 | 0.00 | 1.000 | 1.000 | 0.36 | 0.000 |
| 20 | 1x3/T_r | 3/T_r | 1 | 19.97 | 1.000 | 1.000 | 0.36 | 0.000 |
| 40 | 2x3/T_r | 6/T_r | 2 | 39.94 | 1.000 | 1.000 | 0.36 | 0.000 |
| 60 | 3x3/T_r |  | 3 | 59.91 | 1.000 | 1.000 | 0.36 | 0.000 |
| 80 | 4x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 0.36 | 0.000 |
| 120 | 6x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 0.36 | 0.000 |
| 160 | 8x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 0.36 | 0.000 |
| 200 | 200/h |  | 4 | 79.89 | 1.000 | 1.000 | 0.36 | 0.000 |
| 240 | 12x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 0.36 | 0.000 |
| 320 | 16x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 0.36 | 0.000 |
| 480 | 24x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 0.36 | 0.000 |
| 600 | 600/h |  | 4 | 79.89 | 1.000 | 1.000 | 0.36 | 0.000 |
| 640 | 32x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 0.36 | 0.000 |
| 960 | 48x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 0.36 | 0.000 |
| 1280 | 64x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 0.36 | 0.000 |
| 2000 | 2000/h |  | 4 | 79.89 | 1.000 | 1.000 | 0.36 | 0.000 |
| inf | inf | inf | 4 | 79.89 | 1.000 | 1.000 | 0.36 | 0.000 |

**rate 25, zeroAlarm pricing, group `all` (T_r = 0.15 h; 6 test episodes in the group)**

| budget /h | grid label | declared point | set size | charged /h | partial | strict | median penalised s | g s |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0.00 | 0.500 | 0.333 | 40.15 | 0.000 |
| 6 | 6/h | 6/h | 0 | 0.00 | 0.500 | 0.333 | 40.15 | 0.000 |
| 10 | 0.5x3/T_r |  | 0 | 0.00 | 0.500 | 0.333 | 40.15 | 0.000 |
| 20 | 1x3/T_r | 3/T_r | 1 | 19.97 | 0.500 | 0.333 | 40.15 | 0.000 |
| 40 | 2x3/T_r | 6/T_r | 2 | 39.94 | 0.833 | 0.667 | 32.17 | 5.292 |
| 60 | 3x3/T_r |  | 3 | 59.91 | 1.000 | 1.000 | 32.09 | 7.981 |
| 80 | 4x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 32.09 | 7.981 |
| 120 | 6x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 32.09 | 7.981 |
| 160 | 8x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 32.09 | 7.981 |
| 200 | 200/h |  | 4 | 79.89 | 1.000 | 1.000 | 32.09 | 7.981 |
| 240 | 12x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 32.09 | 7.981 |
| 320 | 16x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 32.09 | 7.981 |
| 480 | 24x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 32.09 | 7.981 |
| 600 | 600/h |  | 4 | 79.89 | 1.000 | 1.000 | 32.09 | 7.981 |
| 640 | 32x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 32.09 | 7.981 |
| 960 | 48x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 32.09 | 7.981 |
| 1280 | 64x3/T_r |  | 4 | 79.89 | 1.000 | 1.000 | 32.09 | 7.981 |
| 2000 | 2000/h |  | 4 | 79.89 | 1.000 | 1.000 | 32.09 | 7.981 |
| inf | inf | inf | 4 | 79.89 | 1.000 | 1.000 | 32.09 | 7.981 |

Comparators (zeroAlarm pricing, rate 25):

| comparator | members (in training ground set) | charged /h | offpath partial / strict / g | onpath partial / strict / g | all partial / strict / g |
|---|---|---|---|---|---|
| ledger alone | 0 (0) | 0.0 | 0.250 / 0.000 / 0.000 | 1.000 / 1.000 / 0.000 | 0.500 / 0.333 / 0.000 |
| full | 4417 (4417) | 99204.0 | 1.000 / 1.000 / 47.639 | 1.000 / 1.000 / 0.000 | 1.000 / 1.000 / 31.759 |
| out of the box | 344 (344) | 9834.3 | 0.750 / 0.500 / 27.638 | 1.000 / 1.000 / 0.000 | 0.833 / 0.667 / 18.425 |


## TeaStore, campaign C (test)

- rate 0.05, decision73 (T_r = 1.25 h): partial at budget 0 = 1.000, reaches 1 at 0; strict at 0 = 1.000, reaches 1 at 0; g at inf = 1.796
- rate 0.05, zeroAlarm (T_r = 1.25 h): partial at budget 0 = 1.000, reaches 1 at 0; strict at 0 = 1.000, reaches 1 at 0; g at inf = 1.796
**rate 0.2, decision73 pricing, group `all` (T_r = 1.25 h; 6 test episodes in the group)**

| budget /h | grid label | declared point | set size | charged /h | partial | strict | median penalised s | g s |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0.00 | 1.000 | 1.000 | 5.30 | 0.000 |
| 1.2 | 0.5x3/T_r |  | 0 | 0.00 | 1.000 | 1.000 | 5.30 | 0.000 |
| 2.4 | 1x3/T_r | 3/T_r | 1 | 2.40 | 1.000 | 1.000 | 5.30 | 1.691 |
| 4.8 | 2x3/T_r | 6/T_r | 1 | 2.40 | 1.000 | 1.000 | 5.30 | 1.691 |
| 6 | 6/h | 6/h | 1 | 2.40 | 1.000 | 1.000 | 5.30 | 1.691 |
| 7.2 | 3x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 9.6 | 4x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 14.4 | 6x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 19.2 | 8x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 20 | 20/h |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 28.8 | 12x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 38.4 | 16x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 57.6 | 24x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 60 | 60/h |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 76.8 | 32x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 115.2 | 48x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 153.6 | 64x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 200 | 200/h |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 600 | 600/h |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 2000 | 2000/h |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| inf | inf | inf | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |

Comparators (decision73 pricing, rate 0.2):

| comparator | members (in training ground set) | charged /h | all partial / strict / g |
|---|---|---|---|
| ledger alone | 0 (0) | 0.0 | 1.000 / 1.000 / 0.000 |
| full | 462 (462) | 1737.5 | 1.000 / 1.000 / 1.692 |
| posture none | 449 (439) | 1465.2 | 1.000 / 1.000 / 1.691 |
| posture selected | 463 (453) | 1524.3 | 1.000 / 1.000 / 1.691 |

**rate 0.2, zeroAlarm pricing, group `all` (T_r = 1.25 h; 6 test episodes in the group)**

| budget /h | grid label | declared point | set size | charged /h | partial | strict | median penalised s | g s |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0.00 | 1.000 | 1.000 | 5.30 | 0.000 |
| 1.2 | 0.5x3/T_r |  | 0 | 0.00 | 1.000 | 1.000 | 5.30 | 0.000 |
| 2.4 | 1x3/T_r | 3/T_r | 1 | 2.40 | 1.000 | 1.000 | 5.30 | 1.691 |
| 4.8 | 2x3/T_r | 6/T_r | 1 | 2.40 | 1.000 | 1.000 | 5.30 | 1.691 |
| 6 | 6/h | 6/h | 1 | 2.40 | 1.000 | 1.000 | 5.30 | 1.691 |
| 7.2 | 3x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 9.6 | 4x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 14.4 | 6x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 19.2 | 8x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 20 | 20/h |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 28.8 | 12x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 38.4 | 16x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 57.6 | 24x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 60 | 60/h |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 76.8 | 32x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 115.2 | 48x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 153.6 | 64x3/T_r |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 200 | 200/h |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 600 | 600/h |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| 2000 | 2000/h |  | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |
| inf | inf | inf | 2 | 6.19 | 1.000 | 1.000 | 5.30 | 1.692 |

Comparators (zeroAlarm pricing, rate 0.2):

| comparator | members (in training ground set) | charged /h | all partial / strict / g |
|---|---|---|---|
| ledger alone | 0 (0) | 0.0 | 1.000 / 1.000 / 0.000 |
| full | 462 (462) | 1277.3 | 1.000 / 1.000 / 1.692 |
| posture none | 449 (439) | 1177.6 | 1.000 / 1.000 / 1.691 |
| posture selected | 463 (453) | 1236.7 | 1.000 / 1.000 / 1.691 |

- rate 1, decision73 (T_r = 1.3 h): partial at budget 0 = 1.000, reaches 1 at 0; strict at 0 = 1.000, reaches 1 at 0; g at inf = 0.083
- rate 1, zeroAlarm (T_r = 1.3 h): partial at budget 0 = 1.000, reaches 1 at 0; strict at 0 = 1.000, reaches 1 at 0; g at inf = 0.083
- rate 10, decision73 (T_r = 1.25 h): partial at budget 0 = 1.000, reaches 1 at 0; strict at 0 = 1.000, reaches 1 at 0; g at inf = 0.053
- rate 10, zeroAlarm (T_r = 1.25 h): partial at budget 0 = 1.000, reaches 1 at 0; strict at 0 = 1.000, reaches 1 at 0; g at inf = 0.053

## Hotel Reservation, leave-one-block-out

- rate 0.05, decision73 (T_r = 1.2 h): partial at budget 0 = 0.667, reaches 1 at 10/h; strict at 0 = 0.667, reaches 1 at 10/h; g at inf = 17.232
- rate 0.05, zeroAlarm (T_r = 1.2 h): partial at budget 0 = 0.667, reaches 1 at 10/h; strict at 0 = 0.667, reaches 1 at 10/h; g at inf = 17.232
**rate 0.2, decision73 pricing, group `all` (T_r = 1.2 h; 12 test episodes in the group)**

| budget /h | grid label | declared point | set size | charged /h | partial | strict | median penalised s | g s |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0.00 | 0.00 | 0.750 | 0.667 | 5.16 | 0.000 |
| 1.25 | 0.5x3/T_r |  | 0.00 | 0.00 | 0.750 | 0.667 | 5.16 | 0.000 |
| 2.5 | 1x3/T_r | 3/T_r | 1.00 | 2.50 | 0.750 | 0.667 | 5.01 | 0.091 |
| 5 | 2x3/T_r | 6/T_r | 1.00 | 3.95 | 0.750 | 0.667 | 5.01 | 0.092 |
| 6 | 6/h | 6/h | 1.00 | 5.25 | 1.000 | 1.000 | 5.16 | 13.903 |
| 7.5 | 3x3/T_r |  | 1.00 | 5.25 | 1.000 | 1.000 | 5.16 | 13.903 |
| 10 | 4x3/T_r |  | 2.00 | 9.20 | 1.000 | 1.000 | 5.01 | 13.995 |
| 15 | 6x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 20 | 8x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 30 | 12x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 40 | 16x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 60 | 24x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 80 | 32x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 120 | 48x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 160 | 64x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 200 | 200/h |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 600 | 600/h |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 2000 | 2000/h |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| inf | inf | inf | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |

Comparators (decision73 pricing, rate 0.2):

| comparator | members (in training ground set) | charged /h | all partial / strict / g |
|---|---|---|---|
| ledger alone | 0 (0) | 0.0 | 0.750 / 0.667 / 0.000 |
| full | 266 (266) | 1098.3 | 1.000 / 1.000 / 14.028 |
| posture none | 60 (30) | 232.0 | 0.833 / 0.667 / 3.741 |
| posture sample-zero | 209 (208) | 576.8 | 0.750 / 0.667 / 0.000 |
| posture selected | 285 (254) | 987.5 | 1.000 / 1.000 / 14.028 |

**rate 0.2, zeroAlarm pricing, group `all` (T_r = 1.2 h; 12 test episodes in the group)**

| budget /h | grid label | declared point | set size | charged /h | partial | strict | median penalised s | g s |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0.00 | 0.00 | 0.750 | 0.667 | 5.16 | 0.000 |
| 1.25 | 0.5x3/T_r |  | 0.00 | 0.00 | 0.750 | 0.667 | 5.16 | 0.000 |
| 2.5 | 1x3/T_r | 3/T_r | 1.00 | 2.50 | 0.750 | 0.667 | 5.01 | 0.091 |
| 5 | 2x3/T_r | 6/T_r | 1.00 | 3.95 | 0.750 | 0.667 | 5.01 | 0.092 |
| 6 | 6/h | 6/h | 1.00 | 5.25 | 1.000 | 1.000 | 5.16 | 13.903 |
| 7.5 | 3x3/T_r |  | 1.00 | 5.25 | 1.000 | 1.000 | 5.16 | 13.903 |
| 10 | 4x3/T_r |  | 2.00 | 9.20 | 1.000 | 1.000 | 5.01 | 13.995 |
| 15 | 6x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 20 | 8x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 30 | 12x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 40 | 16x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 60 | 24x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 80 | 32x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 120 | 48x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 160 | 64x3/T_r |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 200 | 200/h |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 600 | 600/h |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| 2000 | 2000/h |  | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |
| inf | inf | inf | 2.75 | 13.13 | 1.000 | 1.000 | 5.01 | 13.995 |

Comparators (zeroAlarm pricing, rate 0.2):

| comparator | members (in training ground set) | charged /h | all partial / strict / g |
|---|---|---|---|
| ledger alone | 0 (0) | 0.0 | 0.750 / 0.667 / 0.000 |
| full | 266 (266) | 926.1 | 1.000 / 1.000 / 14.028 |
| posture none | 60 (30) | 232.0 | 0.833 / 0.667 / 3.741 |
| posture sample-zero | 209 (208) | 576.8 | 0.750 / 0.667 / 0.000 |
| posture selected | 285 (254) | 872.6 | 1.000 / 1.000 / 14.028 |

- rate 1, decision73 (T_r = 1.2 h): partial at budget 0 = 0.667, reaches 1 at —; strict at 0 = 0.667, reaches 1 at —; g at inf = 0.002
- rate 1, zeroAlarm (T_r = 1.2 h): partial at budget 0 = 0.667, reaches 1 at —; strict at 0 = 0.667, reaches 1 at —; g at inf = 0.002
- rate 10, decision73 (T_r = 1.2 h): partial at budget 0 = 0.833, reaches 1 at —; strict at 0 = 0.667, reaches 1 at —; g at inf = 4.993
- rate 10, zeroAlarm (T_r = 1.2 h): partial at budget 0 = 0.833, reaches 1 at —; strict at 0 = 0.667, reaches 1 at —; g at inf = 4.993

## Reading (grid values, post hoc)

- otel-e, decision73, `offpath` (rate 25, 4 episodes): ledger alone partial 0.250, strict 0.000; partial reaches 1 at 480/h, strict at 480/h; g first above 0 at 240/h, reaches 90% of its grid maximum (11.97 s) at 480/h.
- otel-e, decision73, `onpath` (rate 25, 2 episodes): ledger alone partial 1.000, strict 1.000; partial reaches 1 at 0, strict at 0; g first above 0 at never (g = 0 at every grid budget), reaches 90% of its grid maximum (0.00 s) at —.
- otel-e, decision73, `all` (rate 25, 6 episodes): ledger alone partial 0.500, strict 0.333; partial reaches 1 at 480/h, strict at 480/h; g first above 0 at 240/h, reaches 90% of its grid maximum (7.98 s) at 480/h.
- otel-e, zeroAlarm, `offpath` (rate 25, 4 episodes): ledger alone partial 0.250, strict 0.000; partial reaches 1 at 60/h, strict at 60/h; g first above 0 at 40/h, reaches 90% of its grid maximum (11.97 s) at 60/h.
- otel-e, zeroAlarm, `onpath` (rate 25, 2 episodes): ledger alone partial 1.000, strict 1.000; partial reaches 1 at 0, strict at 0; g first above 0 at never (g = 0 at every grid budget), reaches 90% of its grid maximum (0.00 s) at —.
- otel-e, zeroAlarm, `all` (rate 25, 6 episodes): ledger alone partial 0.500, strict 0.333; partial reaches 1 at 60/h, strict at 60/h; g first above 0 at 40/h, reaches 90% of its grid maximum (7.98 s) at 60/h.
- teastore, decision73, `all` (rate 0.2, 6 episodes): ledger alone partial 1.000, strict 1.000; partial reaches 1 at 0, strict at 0; g first above 0 at 2.4/h, reaches 90% of its grid maximum (1.69 s) at 2.4/h.
- teastore, zeroAlarm, `all` (rate 0.2, 6 episodes): ledger alone partial 1.000, strict 1.000; partial reaches 1 at 0, strict at 0; g first above 0 at 2.4/h, reaches 90% of its grid maximum (1.69 s) at 2.4/h.
- hotel, decision73, `all` (rate 0.2, 12 episodes): ledger alone partial 0.750, strict 0.667; partial reaches 1 at 6/h, strict at 6/h; g first above 0 at 2.5/h, reaches 90% of its grid maximum (13.99 s) at 6/h.
- hotel, zeroAlarm, `all` (rate 0.2, 12 episodes): ledger alone partial 0.750, strict 0.667; partial reaches 1 at 6/h, strict at 6/h; g first above 0 at 2.5/h, reaches 90% of its grid maximum (13.99 s) at 6/h.

## Caveats and what could not be computed

- **x is a charged budget, not a measured false-alarm rate.** The price of a set is the sum of its members' training upper bounds (decision 73 or the zero-alarm row); the frozen sets' fresh false alarms on the test no-fault cells have no validated path (decision 88 analogue), so no curve here has a realised false-alarm axis.
- **Granularity.** Test episodes: OTel E off-path 4 (strict takes 0, 0.5, 1 over 2 classes), on-path 2; TeaStore C 6 per rate; Hotel 12 per rate (3 classes x 4 blocks, strict takes multiples of 1/3). `reaches 1 at` and the knee are grid values: the true step lies between that budget and the one before it. Greedy sets are not nested in the budget, so the curves are not forced monotone; curves that dip (a larger budget, a lower value): hotel r10 decision73 all g, hotel r10 zeroAlarm all g.
- **TeaStore.** The ledger alone detects every campaign-C episode at rates 0.05, 0.2, 1, 10 (of 0.05, 0.2, 1, 10), so there partial and strict are 1 at every budget and only the penalised time and g move.
- **Hotel is leave-one-block-out, not a held-out campaign.** Each fold's set is solved on the other three blocks with the price table of the full readout (the same as the frozen `celf_v3.held_out`), so prices are in-sample for the fold; the 12 held-out episodes are pooled. The fixed comparators are scored on all 12 episodes (they have no fold).
- **Comparators.** `out of the box` exists for OTel E only (the effort file `otel.effort.json`); TeaStore and Hotel have no effort file, so the declared postures `none` and `selected` (restriction estimates, decision 78) stand in and are not the shipped system. Hotel `sample-zero` is in the JSON and the table, not drawn.
- **Zero-alarm price.** It reprices only ids the reader flags (appearOnly, foldsEvaluated 0, no honest bound): E 3743, TeaStore r0.2 8, Hotel r0.2 3 ids. For TeaStore and Hotel the sets differ between the two prices at: TeaStore no budget; Hotel no budget (grid labels, rate 0.2).
- **Other rates.** TeaStore and Hotel have rates 0.05, 0.2, 1, 10 req/s; only r0.2 is drawn (engineering default). The others are in `curves.json` and summarised in one line each above. OTel E has one rate. Rates where the partial curve (decision-73 price; E off-path, others all classes) never reaches 1 on the grid: hotel r1 (maximum 0.667), hotel r10 (maximum 0.917); no mechanism is claimed.
