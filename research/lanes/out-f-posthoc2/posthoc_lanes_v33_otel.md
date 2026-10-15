# posthoc-lanes-v33: OTel lane rows (POST HOC (not a preregistered verdict; written under FREEZE_V33_20261014.md addendum, condition 2), scope instance)

Inputs: training readout `research/traffic-sweep/readout-otel-f-train-v3.3/sweep_analysis_v3_3.json`, scoring readout `research/traffic-sweep/readout-otel-f-score-v3.3/sweep_analysis_v3_3.json`, frozen placement `research/placement/test-f/placement-f.json`. Test blocks [4, 5] (heldOut episodes). No pass or fail rule is applied to anything below.

## 1. Zero-alarm pricing frontier (post hoc)

sensors with appearOnly True, foldsEvaluated 0 and no honest upper bound are priced 2.9957/T_r (T_r = the rate's training no-fault hours) instead of decision 73's fill

Flag meaning: foldsEvaluated 0 = the sensor had a scored record in the fit of every leave-one-cell-out fold (the fit pools every other valid cell, fault cells' fault-free segments included); not proven equal to 'no record in any training no-fault cell'

Decision-73 rerun equals the frozen placement's `rates`: **True**.

### Rate 25 (T_r = 0.3000 h; zero-alarm price 9.986 /h; decision-73 fill 108.62 /h; repriced ids 3633; unevaluated ids left at the fill 0)

Unrestricted cell (effort<=any, runtime<=any); sets differ from decision 73's: {'0': False, '3/T_r': False, '6/T_r': False, '6/h': False, 'inf': False}.

| budget | set (zero-alarm row) | size | D_E | g_E (test) | detected | decision-73 set size | decision-73 g_E |
|---|---|---|---|---|---|---|---|
| 0 | — | 0 | 36.493 | 0.000 | 3/6 | 0 | 0.000 |
| 3/T_r | metric:kafka:kafka.request.count [evidenced] | 1 | 4.607 | 31.886 | 6/6 | 1 | 31.886 |
| 6/T_r | metric:kafka:kafka.consumer_group.lag [evidenced] | 1 | 4.734 | 31.759 | 6/6 | 1 | 31.759 |
| 6/h | — | 0 | 36.493 | 0.000 | 3/6 | 0 | 0.000 |
| inf | metric:kafka:kafka.consumer_group.lag [evidenced], metric:kafka:kafka.request.count [evidenced] | 2 | 3.760 | 32.733 | 6/6 | 2 | 32.733 |

Per class at 3/T_r (zero-alarm row): accounting-pause-effect: g=53.279, improved 2/2; fraud-pause-effect: g=42.377, improved 2/2; frontend-pause-effect: g=0.000, improved 0/2
Per class at 6/T_r (zero-alarm row): accounting-pause-effect: g=53.227, improved 2/2; fraud-pause-effect: g=42.050, improved 2/2; frontend-pause-effect: g=0.000, improved 0/2

## 2. Lane predictions on the test-block episodes (heldOut)

| id | result | reason | key numbers |
|---|---|---|---|
| F-L1 | **hit** | off-path test episodes 4 (declared 4), frontend 2 (declared 2) | {"k": 4, "n": 4} |
| F-L2 | **hit** | off-path test episodes 4 (declared 4), frontend 2 (declared 2) | {"frontendNoCountedFire": true, "frontendNoFireEitherField": true, "n": 4, "offpathInWindow": 4} |
| F-L3 | **hit** | off-path test episodes 4 (declared 4), frontend 2 (declared 2) | {"armed": 2, "k": 4, "lagIdsInCalibration": 2, "n": 4} |
| F-M | **hit** | 236 SDK + 44 spanmetrics-derived non-flagd placeable metric ids at 25 req/s | {"placeableFlagd": 9, "placeableNonFlagdSdk": 236, "placeableNonFlagdSpanmetrics": 44} |

