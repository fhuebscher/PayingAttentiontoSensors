# posthoc-lanes-v33: OTel lane rows (POST HOC (not a preregistered verdict; written under FREEZE_V33_20261014.md addendum, condition 2), scope instance)

Inputs: training readout `research/traffic-sweep/readout-otel-f-nolag-train-v3.5/sweep_analysis_v3_5.json`, scoring readout `research/traffic-sweep/readout-otel-f-nolag-score-v3.5/sweep_analysis_v3_5.json`, frozen placement `research/placement/test-f-nolag/placement-nolag.json`. Test blocks [4, 5] (heldOut episodes). No pass or fail rule is applied to anything below.

## 1. Zero-alarm pricing frontier (post hoc)

sensors with appearOnly True, foldsEvaluated 0 and no honest upper bound are priced 2.9957/T_r (T_r = the rate's training no-fault hours) instead of decision 73's fill

Flag meaning: foldsEvaluated 0 = the sensor had a scored record in the fit of every leave-one-cell-out fold (the fit pools every other valid cell, fault cells' fault-free segments included); not proven equal to 'no record in any training no-fault cell'

Decision-73 rerun equals the frozen placement's `rates`: **True**.

### Rate 25 (T_r = 0.3000 h; zero-alarm price 9.986 /h; decision-73 fill 183.07 /h; repriced ids 3621; unevaluated ids left at the fill 5)

Unrestricted cell (effort<=any, runtime<=any); sets differ from decision 73's: {'0': False, '3/T_r': False, '6/T_r': False, '6/h': False, 'inf': False}.

| budget | set (zero-alarm row) | size | D_E | g_E (test) | detected | decision-73 set size | decision-73 g_E |
|---|---|---|---|---|---|---|---|
| 0 | — | 0 | 39.310 | 0.000 | 3/6 | 0 | 0.000 |
| 3/T_r | metric:cartservice:calls [evidenced] | 1 | 8.964 | 30.346 | 6/6 | 1 | 30.346 |
| 6/T_r | metric:kafka:kafka.request.count [evidenced] | 1 | 5.242 | 34.068 | 6/6 | 1 | 34.068 |
| 6/h | — | 0 | 39.310 | 0.000 | 3/6 | 0 | 0.000 |
| inf | metric:kafka:kafka.request.count [evidenced] | 1 | 5.242 | 34.068 | 6/6 | 1 | 34.068 |

Per class at 3/T_r (zero-alarm row): accounting-pause-effect: g=46.810, improved 2/2; fraud-pause-effect: g=44.228, improved 2/2; frontend-pause-effect: g=0.000, improved 0/2
Per class at 6/T_r (zero-alarm row): accounting-pause-effect: g=51.060, improved 2/2; fraud-pause-effect: g=51.144, improved 2/2; frontend-pause-effect: g=0.000, improved 0/2

## 2. Lane predictions on the test-block episodes (heldOut)

| id | result | reason | key numbers |
|---|---|---|---|
| F-L1 | **hit** | off-path test episodes 4 (declared 4), frontend 2 (declared 2) | {"k": 4, "n": 4} |
| F-L2 | **hit** | off-path test episodes 4 (declared 4), frontend 2 (declared 2) | {"frontendNoCountedFire": true, "frontendNoFireEitherField": true, "n": 4, "offpathInWindow": 4} |
| F-L3 | **—** | no kafka.consumer_group.lag* id in the calibration (absent: not collected or dropped by the adapter) | {"armed": 0, "lagIdsInCalibration": 0} |
| F-M | **hit** | 231 SDK + 44 spanmetrics-derived non-flagd placeable metric ids at 25 req/s | {"placeableFlagd": 9, "placeableNonFlagdSdk": 231, "placeableNonFlagdSpanmetrics": 44} |

