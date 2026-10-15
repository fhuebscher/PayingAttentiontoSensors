# Lane tables, 2026-10-13 (written 2026-10-14)

**POST HOC, EXPLORATORY (not preregistered; computed after the readouts were seen).** Scope of every table: **instance** (one SUT, one host, one campaign family per row). Produced by `research/lanes/lanes_tables.py` from the frozen readouts and the retained raw cells, read-only; no frozen file was edited and no reader constant was changed. Plan: `research/PLAN_LANES_20261014.md`, Directions O1-O5.

Inputs: OTel campaign E `research/traffic-sweep/readout-otel-e-score-v3.2/sweep_analysis_v3_2.json` (20 cells: 15 fault episodes + 5 no-fault, 3 training no-fault cells calibrate, T_r = 0.15 h, train-only calibration for every episode); TeaStore C `research/traffic-sweep/readout-teastore-c-v3.1/sweep_analysis_v3.json` (6 campaigns pooled; 28 auth-freeze, 28 persistence-cpu-throttle, 101 no-fault cells); Hotel: `research/traffic-sweep/readout-hotel-primary-v3.1/sweep_analysis_v3.json`, the v3.1 re-read of the same `tmp/hotelsweep3-evidence` cells as `readout-hotel-r3-v2.4` (16 search-pause episodes) plus the two Hotel quiet campaigns (96 no-fault cells in all: 16 in the sweep campaign, 80 in the quiet ones). v3.1 is used because v2.4 carries no calibration, so no prices; the 16 search-pause episodes are identical.

Readings: a fire counts only through `celf_v3.counted` and only if its `counts` flag is true. Placement-style rows: bc `e-only`, own `exclude` (the scorer's). Lane 1: own `only`, bc `count-all`. Lane 2: bc `count-all`. Times are seconds after the pre-command onset stamp, a miss is `—` in the time columns and is charged the hold only in `mean (miss = hold)`.

## Cross-checks (computed here against the repository's own numbers)

| check | ok |
|---|---|
| recomputed ledger alone equals otel-e.json ttd on the 6 test episodes | PASS |
| recomputed frozen @6/T_r equals otel-e.json ttd on the 6 test episodes | PASS |
| recomputed inf set equals otel-e.json ttd on the 6 test episodes | PASS |
| recomputed full (V_r) equals otel-e.json ttd on the 6 test episodes | PASS |
| full (V_r) charged price equals placement-e.json comparators.full.charged | PASS |
| inf set charged price equals placement-e.json grid inf point | PASS |
| accounting test blocks 4/5: frozen set misses, inf set detects at ~44.3/44.1 s, own orders_receive absent at ~1.0/1.45 s | PASS |
| poisson_upper equals the frozen reader's for k = 0..6 | PASS |
| zero-alarm price 2.9957/T_r equals the honest bound of a zero-alarm evaluated E sensor (19.9715/h at T_r = 0.15 h) | PASS |
| E training and scoring readouts: identical calibration and identical fires on blocks 1-3 (decision 102) | PASS |


## O1 lane 1: own silence (`absent` on the paused target's own sensors)

Scope: instance. Denominator: episodes of the regime and rate in the readout. `any own rule` counts own fires of every rule (S-family medians etc.), `absent` only the silence rule. Cheapest sensor = the cheapest of the own `absent` sensors with the largest coverage; price = honest upper bound per hour (`—` = evaluated in 0 folds, no bound) and the decision-73 charge.

| system | regime | rate | detected (absent) | min s | median s | max s | any own rule | cheapest own sensor | honest upper /h | charged /h | evaluated |
|---|---|---|---|---|---|---|---|---|---|---|---|
| otel | accounting-pause-effect | 25.00 | 5/5 | 0.88 | 1.34 | 1.51 | 5/5, med 1.34 | span:accountingservice:orders_receive (5/5) | 31.63 | 31.63 | 3 folds |
| otel | fraud-pause-effect | 25.00 | 5/5 | 1.15 | 1.28 | 1.55 | 5/5, med 1.28 | log:frauddetectionservice:0a3d12f34da2 (5/5) | 19.97 | 19.97 | 3 folds |
| otel | frontend-pause-effect | 25.00 | 5/5 | 0.29 | 0.35 | 0.41 | 5/5, med 0.35 | span:frontend:grpc.oteldemo.RecommendationService/ListRecommendations (5/5) | 19.97 | 19.97 | 3 folds |
| otel (test blocks 4-5 only) | accounting-pause-effect | 25.00 | 2/2 | 1.02 | 1.23 | 1.45 | 2/2, med 1.23 | span:accountingservice:orders_receive (2/2) | 31.63 | 31.63 | 3 folds |
| otel (test blocks 4-5 only) | fraud-pause-effect | 25.00 | 2/2 | 1.18 | 1.36 | 1.55 | 2/2, med 1.36 | log:frauddetectionservice:0a3d12f34da2 (2/2) | 19.97 | 19.97 | 3 folds |
| otel (test blocks 4-5 only) | frontend-pause-effect | 25.00 | 2/2 | 0.29 | 0.35 | 0.41 | 2/2, med 0.35 | span:frontend:grpc.oteldemo.RecommendationService/ListRecommendations (2/2) | 19.97 | 19.97 | 3 folds |
| teastore | auth-freeze-effect | 0.05 | 7/7 | 1.35 | 6.86 | 18.37 | 7/7, med 6.86 | span:auth:BCryptProvider.checkPassword (7/7) | 2.40 | 2.40 | 25 folds |
| teastore | auth-freeze-effect | 0.20 | 7/7 | 2.79 | 4.65 | 6.56 | 7/7, med 4.65 | span:auth:BCryptProvider.checkPassword (7/7) | 2.40 | 2.40 | 25 folds |
| teastore | auth-freeze-effect | 1.00 | 7/7 | 0.93 | 1.49 | 1.66 | 7/7, med 1.49 | span:auth:BCryptProvider.checkPassword (7/7) | 2.30 | 2.30 | 26 folds |
| teastore | auth-freeze-effect | 10.00 | 7/7 | 0.45 | 0.47 | 0.52 | 7/7, med 0.47 | span:auth:ShaSecurityProvider.getKeyProvider (7/7) | 3.80 | 3.80 | 25 folds |
| teastore | persistence-cpu-throttle-effect | 0.05 | 0/7 | — | — | — | 7/7, med 2.61 | — | — | — | — |
| teastore | persistence-cpu-throttle-effect | 0.20 | 3/7 | 18.51 | 47.39 | 50.00 | 7/7, med 3.30 | span:persistence:UserRepository.getUserByName (3/7) | 3.80 | 3.80 | 25 folds |
| teastore | persistence-cpu-throttle-effect | 1.00 | 7/7 | 4.81 | 23.17 | 36.69 | 7/7, med 1.15 | span:persistence:CategoryEndpoint.listAllEntities (7/7) | 4.84 | 4.84 | 26 folds |
| teastore | persistence-cpu-throttle-effect | 10.00 | 7/7 | 1.54 | 2.25 | 3.35 | 7/7, med 0.92 | span:persistence:PersistenceCategory.getId (7/7) | 2.40 | 2.40 | 25 folds |
| hotel | cpu-throttle-effect | 0.05 | 0/4 | — | — | — | 4/4, med 2.60 | — | — | — | — |
| hotel | cpu-throttle-effect | 0.20 | 0/4 | — | — | — | 3/4, med 6.92 | — | — | — | — |
| hotel | cpu-throttle-effect | 1.00 | 0/4 | — | — | — | 1/4, med 14.74 | — | — | — | — |
| hotel | cpu-throttle-effect | 10.00 | 0/4 | — | — | — | 4/4, med 4.76 | — | — | — | — |
| hotel | net-delay-effect | 0.05 | 0/4 | — | — | — | 4/4, med 4.35 | — | — | — | — |
| hotel | net-delay-effect | 0.20 | 4/4 | 0.41 | 2.16 | 4.77 | 4/4, med 2.16 | span:rate:/rate.Rate/GetRates (4/4) | 6.46 | 6.46 | 24 folds |
| hotel | net-delay-effect | 1.00 | 0/4 | — | — | — | 4/4, med 0.53 | — | — | — | — |
| hotel | net-delay-effect | 10.00 | 4/4 | 0.14 | 0.16 | 0.20 | 4/4, med 0.16 | span:rate:memcached_get_multi_rate (4/4) | 5.25 | 5.25 | 24 folds |
| hotel | search-pause-effect | 0.05 | 4/4 | 11.63 | 20.51 | 27.67 | 4/4, med 11.76 | span:search:/rate.Rate/GetRates (4/4) | 2.50 | 2.50 | 24 folds |
| hotel | search-pause-effect | 0.20 | 4/4 | 1.94 | 3.78 | 5.01 | 4/4, med 3.78 | span:search:/search.Search/Nearby (4/4) | 3.95 | 3.95 | 24 folds |
| hotel | search-pause-effect | 1.00 | 4/4 | 0.70 | 1.19 | 1.54 | 4/4, med 1.19 | span:search:/geo.Geo/Nearby (4/4) | 3.95 | 3.95 | 24 folds |
| hotel | search-pause-effect | 10.00 | 4/4 | 0.21 | 0.24 | 0.28 | 4/4, med 0.24 | span:search:/rate.Rate/GetRates (4/4) | 3.95 | 3.95 | 24 folds |
| hotel (v2.4 readout: the plan's numbers, no prices) | search-pause-effect | 0.05 | 4/4 | 21.64 | 30.52 | 37.68 | 4/4, med 30.52 | span:search:/geo.Geo/Nearby (4/4) | — | — | — |
| hotel (v2.4 readout: the plan's numbers, no prices) | search-pause-effect | 0.20 | 4/4 | 6.94 | 8.78 | 10.01 | 4/4, med 8.78 | span:search:/geo.Geo/Nearby (4/4) | — | — | — |
| hotel (v2.4 readout: the plan's numbers, no prices) | search-pause-effect | 1.00 | 4/4 | 1.20 | 1.69 | 2.04 | 4/4, med 1.69 | span:search:/geo.Geo/Nearby (4/4) | — | — | — |
| hotel (v2.4 readout: the plan's numbers, no prices) | search-pause-effect | 10.00 | 4/4 | 0.27 | 0.30 | 0.33 | 4/4, med 0.30 | span:search:/geo.Geo/Nearby (4/4) | — | — | — |

Reader version matters for Hotel: the `hotel` rows are the v3.1 re-read (calibrated `absent` gap scale per sensor); the `hotel (v2.4 ...)` rows are `readout-hotel-r3-v2.4`, the source of the plan's table (v2.4: the gap scale is a fixed multiple of the pooled largest gap, so later and without prices). Same 16 cells, different detector, so the Hotel search-pause medians differ by reader version; v3.1 is the primary Hotel reading because it carries prices.


**What this cannot say.** The own sensors measure the injection (decisions 84/111): a pause of the service that emits is seen by that service's silence by construction (BC-downstream-absent), so this is a ceiling for a monitor that knows which service to watch, not a placement result. Lane 1 does not detect non-pause faults (cpu-throttle, net-delay rows show it). A frozen reading of E's own fires uses the readout's train-only calibration; the `absent` rule's gap scale is calibrated per rate.


## O2 lane 2: coordinator side

Ids found by service and template text in the raw `application.log` (the reader's masked message, `<n>` = a masked number).

**OTel, service `kafka`, GroupCoordinator templates seen in the 20 E cells:**

| id | group | lane-2 template | message |
|---|---|---|---|
| log:kafka:28ec81d9cba3 | accountingservice | failed | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Member rdkafka-<uuid> in group accountingservice has failed, removing it from the group (ka |
| log:kafka:3e54cbc78de3 | frauddetectionservice | rebalance | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Preparing to rebalance group frauddetectionservice in state PreparingRebalance with old gen |
| log:kafka:45faa121d71d | — | — | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Dynamic member with unknown member id joins group accountingservice in Empty state. Created |
| log:kafka:49ecae86dd5a | — | — | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Assignment received from leader consumer-frauddetectionservice-<n>-<uuid> for group fraudde |
| log:kafka:4c8031c4a7a1 | frauddetectionservice | empty | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Group frauddetectionservice with generation <n> is now empty (__consumer_offsets-<n>) (kafk |
| log:kafka:60a3d40666a9 | — | — | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Elected as the group coordinator for partition <n> in epoch <n> (kafka.coordinator.group.Gr |
| log:kafka:7732ee59ae2e | — | — | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Stabilized group frauddetectionservice generation <n> (__consumer_offsets-<n>) with <n> mem |
| log:kafka:794df5201c50 | — | — | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Stabilized group accountingservice generation <n> (__consumer_offsets-<n>) with <n> members |
| log:kafka:7c2475963700 | — | — | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Dynamic member with unknown member id joins group frauddetectionservice in Empty state. Cre |
| log:kafka:7f314c46ac6f | accountingservice | — | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Preparing to rebalance group accountingservice in state PreparingRebalance with old generat |
| log:kafka:8f9d8866e174 | frauddetectionservice | failed | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Member consumer-frauddetectionservice-<n>-<uuid> in group frauddetectionservice has failed, |
| log:kafka:a120e94d78d7 | frauddetectionservice | — | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Preparing to rebalance group frauddetectionservice in state PreparingRebalance with old gen |
| log:kafka:c60d8c14048c | accountingservice | empty | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Group accountingservice with generation <n> is now empty (__consumer_offsets-<n>) (kafka.co |
| log:kafka:cc23ac6fcc18 | accountingservice | rebalance | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Preparing to rebalance group accountingservice in state PreparingRebalance with old generat |
| log:kafka:e209b130ab15 | — | — | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Assignment received from leader rdkafka-<uuid> for group accountingservice for generation < |
| log:kafka:ecad6237dd0c | — | — | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Starting up. (kafka.coordinator.group.GroupCoordinator) |
| log:kafka:fe5bc2cd9f19 | — | — | [<n>-<n>-<n> <n>:<n>:<n>,<n>] INFO [GroupCoordinator <n>]: Startup complete. (kafka.coordinator.group.GroupCoordinator) |

**TeaStore, service `registry`, templates containing `since it failed the heartbeat`:**

| id | template | message |
|---|---|---|
| log:registry:1b6e1f5f63fc | heartbeat-removal | Removed tools.descartes.teastore.auth@auth:<n> since it failed the heartbeat! |
| log:registry:3746091e2305 | heartbeat-removal | Removed tools.descartes.teastore.persistence@persistence:<n> since it failed the heartbeat! |

Records of the lane-2 ids inside the measurement window of every retained no-fault cell of the readout (a template never seen counts 0): OTel {"kafka:28ec81d9cba3": 0, "kafka:cc23ac6fcc18": 0, "kafka:c60d8c14048c": 0, "kafka:8f9d8866e174": 0, "kafka:3e54cbc78de3": 0, "kafka:4c8031c4a7a1": 0} over 5 cells; TeaStore {"registry:1b6e1f5f63fc": 0, "registry:3746091e2305": 0} over 101 cells. A zero here is why `foldsEvaluated` is 0 and decision 73 charges the fill.


### otel

| regime | rate | detected (count-all) | min s | median s | max s | of which scorer-counted (e-only) | fired by other group's ids | matched ids | 1 id charged /h | 1 id if zero alarms /h | all matched ids charged /h | all matched ids if zero alarms /h | honest bound of id 1 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| accounting-pause-effect | 25.00 | 5/5 | 43.71 | 44.18 | 44.32 | 5 | 0 | 3 | 183.07 | 19.97 | 549.21 | 59.91 | — |
| fraud-pause-effect | 25.00 | 5/5 | 43.37 | 43.85 | 43.94 | 5 | 0 | 3 | 183.07 | 19.97 | 549.21 | 59.91 | — |
| frontend-pause-effect | 25.00 | 0/5 | — | — | — | 0 | 0 | 6 | 183.07 | 19.97 | 1098.42 | 119.83 | — |

### teastore

| regime | rate | detected (count-all) | min s | median s | max s | of which scorer-counted (e-only) | fired by other group's ids | matched ids | 1 id charged /h | 1 id if zero alarms /h | all matched ids charged /h | all matched ids if zero alarms /h | honest bound of id 1 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| auth-freeze-effect | 0.05 | 7/7 | 9.07 | 10.18 | 11.72 | 0 | 0 | 1 | 11.98 | 2.40 | 11.98 | 2.40 | — |
| auth-freeze-effect | 0.20 | 7/7 | 9.89 | 10.59 | 11.67 | 0 | 0 | 1 | 59.91 | 2.40 | 59.91 | 2.40 | — |
| auth-freeze-effect | 1.00 | 7/7 | 9.66 | 11.41 | 11.75 | 0 | 0 | 1 | 51.25 | 2.30 | 51.25 | 2.30 | — |
| auth-freeze-effect | 10.00 | 7/7 | 9.79 | 10.20 | 11.73 | 0 | 0 | 1 | 59.91 | 2.40 | 59.91 | 2.40 | — |
| persistence-cpu-throttle-effect | 0.05 | 2/7 | 21.52 | 34.75 | 47.98 | 0 | 0 | 1 | 11.98 | 2.40 | 11.98 | 2.40 | — |
| persistence-cpu-throttle-effect | 0.20 | 2/7 | 53.14 | 54.15 | 55.16 | 0 | 0 | 1 | 59.91 | 2.40 | 59.91 | 2.40 | — |
| persistence-cpu-throttle-effect | 1.00 | 4/7 | 19.50 | 31.90 | 44.66 | 0 | 0 | 1 | 51.25 | 2.30 | 51.25 | 2.30 | — |
| persistence-cpu-throttle-effect | 10.00 | 6/7 | 17.56 | 30.55 | 59.05 | 0 | 0 | 1 | 59.91 | 2.40 | 59.91 | 2.40 | — |

Hotel: — (Hotel registers services in consul without health checks; consul writes no log in the retained application.log).

**What this cannot say.** The coordinator ids never occur in a no-fault cell, so no honest bound exists and the price is a convention (decision 73's fill, or 2.9957/T_r if one assumes zero alarms); neither is an observed false-alarm rate. The Kafka lane is the session timeout (about 44 s) and the registry lane the 10 s heartbeat window: both are properties of those two SUTs' defaults, one SUT each. The two Kafka groups have disjoint ids (class-matched columns). The TeaStore fire is BC-caller-log flagged, which the scorer reads as a miss.


## O3 lane 3: backlog/lag metrics of E (arming status; the frozen reader was not re-run)

Not re-run: MIN_BASELINE_POOLED is read from research/protocol/parameters.json by the frozen v2.4 reader at import (sweep_analysis_v2.py:216; the registry digest is recorded in every readout) and the reader offers no override, so a lowered value needs an edit to that registry or an in-process monkeypatch of a frozen module, and it would change the arming of every level rule, not only the lag metrics. Reported instead: arming status, pooled n from the cells' own segLevel (the Fit's input), and a descriptive look at the pause window.

| metric id | unarmed rules | placeable | folds evaluated | pooled n (train cells' fault-free segments) | pooled median | min | max | points inside the pause hold, per fraud episode | fraud episodes with a hold point outside the pooled range |
|---|---|---|---|---|---|---|---|---|---|
| metric:accountingservice:process.runtime.dotnet.thread_pool.queue.length | spike,run3,median | False | 0 | — | — | — | — | — | — |
| metric:frauddetectionservice:kafka.consumer.last_poll_seconds_ago | spike,run3,median | False | 0 | 18 | 0.00 | 0.00 | 0.00 | [0, 0, 0, 0, 0] of 5 eps | 0 |
| metric:frauddetectionservice:kafka.consumer.records_lag | spike,run3,median | False | 0 | 18 | 0.00 | 0.00 | 0.00 | [0, 0, 0, 0, 0] of 5 eps | 0 |
| metric:frauddetectionservice:kafka.consumer.records_lag_avg | spike,run3,median | False | 0 | 18 | 0.00 | 0.00 | 0.00 | [0, 0, 0, 0, 0] of 5 eps | 0 |
| metric:frauddetectionservice:kafka.consumer.records_lag_max | spike,run3,median | False | 0 | 18 | 0.00 | 0.00 | 0.00 | [0, 0, 0, 0, 0] of 5 eps | 0 |
| metric:frauddetectionservice:kafka.consumer.records_lead | spike,run3,median | False | 0 | 18 | 34.00 | 32.00 | 211.00 | [0, 0, 0, 0, 0] of 5 eps | 0 |
| metric:frauddetectionservice:kafka.consumer.records_lead_avg | spike,run3,median | False | 0 | 18 | 17.00 | 16.00 | 171.50 | [0, 0, 0, 0, 0] of 5 eps | 0 |
| metric:frauddetectionservice:kafka.consumer.records_lead_min | spike,run3,median | False | 0 | 18 | 0.00 | 0.00 | 132.00 | [0, 0, 0, 0, 0] of 5 eps | 0 |
| metric:frauddetectionservice:kafka.consumer.time_between_poll_avg | spike,run3,median | False | 0 | 18 | 98.31 | 91.12 | 98.97 | [0, 0, 0, 0, 0] of 5 eps | 0 |
| metric:frauddetectionservice:kafka.consumer.time_between_poll_max | spike,run3,median | False | 0 | 18 | 300.50 | 101.00 | 345.00 | [0, 0, 0, 0, 0] of 5 eps | 0 |
| metric:frauddetectionservice:queueSize | spike,run3,median | False | 0 | — | — | — | — | — | — |
| metric:kafka:kafka.lag.max | spike,run3,median | False | 0 | 6 | 0.00 | 0.00 | 0.00 | [1, 1, 1, 1, 1] of 5 eps | 0 |
| metric:kafka:kafka.message.count | spike,run3,median | False | 0 | 3 | 1.87 | 1.87 | 1.90 | [0, 0, 0, 0, 0] of 5 eps | 0 |
| metric:kafka:kafka.request.count | spike,run3,median | False | 0 | 3 | 7.13 | 7.13 | 7.30 | [0, 0, 0, 0, 0] of 5 eps | 0 |
| metric:kafka:queueSize | spike,run3,median | False | 0 | — | — | — | — | — | — |

113 of the 113 kafka/lag/queue metric ids of E's ground set matched here are unarmed on `spike`, `run3` and `median` (these need pooled n >= MIN_BASELINE_POOLED = 20); the metrics exported at a 60 s cadence give n of a few points per cell. The last two columns are descriptive only (fraud pause cells): they show whether the metric exports anything at all inside the 60 s pause and whether such a point leaves the pooled fault-free range; no rule was applied.

`metric:kafka:kafka.lag.max` is, by its OpenTelemetry Kafka-JMX name, the broker's follower-replica lag, not consumer-group lag (its description was not checked in this repository); only `frauddetectionservice`'s `kafka.consumer.*` ids are client-side consumer metrics, and E's ground set holds no `kafka.*` metric id for `accountingservice` (its consumer is rdkafka).

**What this cannot say.** Whether a lag metric would move in a pause is not answered here: no lowered-threshold reading was made. A paused JVM exports nothing, so the client-side lag metric is silent rather than high; group lag needs a broker-side source (the plan's S1). Pooled n here counts the fault-free segments of the nine training fault cells and three no-fault cells.


## O4 shared-fate silence sensor per container

A sensor per service: alarm at (last record + w) when no record of any kind arrives for longer than w. **Records**: every compose-log line with a Docker stamp in `application.log`; spans (the readers' kept spans, probe traces excluded; span times are the service-side start stamps, so a real monitor would see them later by the export delay, not measured here); for OTel also the OTLP metric points of the service (the spanmetrics connector's `calls` and `duration*` are the collector's, excluded). TeaStore/Hotel system samples (cgroup, docker stats) are excluded: the harness pulls them, the service does not emit them. OTLP log records and resource-only exports were not counted (more records would shorten gaps, so w here is conservative). **Window** per cell: the measurement window [barrier, barrier + 180 s]; its edges are virtual records, so a service silent for the whole window has a gap of 180 s.

**Calibration**: w = the largest gap of that service in calibration cells, so a calibration cell cannot alarm. OTel: no-fault blocks 1-3 train (3 cells, 0.15 h), blocks 4-5 held out (2 cells, 0.10 h). TeaStore/Hotel have no registry split: leave-one-cell-out over the rate's no-fault cells (posture full), so the held-out hours equal the calibration hours; fault episodes use w from all of them. Alarm bound: exact Poisson 95 % upper limit per service / held-out hours.


### otel

| rate | services (sensors) | held-out | held-out alarms (all services) | sum of upper bounds /h | regime | episodes | target sensor detected | min s | median s | max s | any service detected | median s | target w (median s) | target pre-onset alarms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 25 | 16 | 2 cells, 0.100 h | 7 | 594.86 | accounting-pause-effect | 5 | 5/5 | 0.43 | 0.89 | 1.06 | 5/5 | 0.89 | 0.90 | 0 |
| 25 | 16 | 2 cells, 0.100 h | 7 | 594.86 | fraud-pause-effect | 5 | 5/5 | 0.68 | 0.81 | 1.08 | 5/5 | 0.81 | 0.93 | 0 |
| 25 | 16 | 2 cells, 0.100 h | 7 | 594.86 | frontend-pause-effect | 5 | 5/5 | 0.30 | 0.31 | 0.32 | 5/5 | 0.31 | 0.12 | 0 |

w per service (s, from blocks 1-3): accountingservice 0.90 (held-out alarms 0), adservice 0.74 (held-out alarms 3), cartservice 0.27 (held-out alarms 0), checkoutservice 0.86 (held-out alarms 0), currencyservice 0.88 (held-out alarms 0), emailservice 0.89 (held-out alarms 0), flagd 0.57 (held-out alarms 0), frauddetectionservice 0.93 (held-out alarms 0), frontend 0.12 (held-out alarms 0), frontendproxy 0.12 (held-out alarms 2), kafka 14.98 (held-out alarms 1), paymentservice 0.89 (held-out alarms 0), productcatalogservice 0.17 (held-out alarms 1), quoteservice 0.89 (held-out alarms 0), recommendationservice 0.72 (held-out alarms 0), shippingservice 0.88 (held-out alarms 0).


Services with a sensor (16): accountingservice, adservice, cartservice, checkoutservice, currencyservice, emailservice, flagd, frauddetectionservice, frontend, frontendproxy, kafka, paymentservice, productcatalogservice, quoteservice, recommendationservice, shippingservice. Services of the universe (ground-set services plus every container with a compose-log line) with NO record inside any calibration window at the first rate listed, so no w and no sensor (they never emit in normal operation or emit outside the window) (3): flagdui, imageprovider, loadgenerator.


### teastore

| rate | services (sensors) | held-out | held-out alarms (all services) | sum of upper bounds /h | regime | episodes | target sensor detected | min s | median s | max s | any service detected | median s | target w (median s) | target pre-onset alarms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.05 | 4 | 25 cells, 1.250 h | 4 | 15.18 | auth-freeze-effect | 7 | 7/7 | 1.34 | 6.85 | 18.36 | 7/7 | 6.85 | 20.00 | 0 |
| 0.2 | 4 | 25 cells, 1.250 h | 4 | 15.18 | auth-freeze-effect | 7 | 7/7 | 1.12 | 3.34 | 5.16 | 7/7 | 2.08 | 4.99 | 0 |
| 1 | 4 | 26 cells, 1.300 h | 4 | 14.60 | auth-freeze-effect | 7 | 7/7 | 0.36 | 0.93 | 1.10 | 7/7 | 0.93 | 1.03 | 0 |
| 10 | 4 | 25 cells, 1.250 h | 4 | 15.18 | auth-freeze-effect | 7 | 7/7 | 0.40 | 0.43 | 0.47 | 7/7 | 0.43 | 0.29 | 0 |

Services with a sensor (4): auth, image, persistence, webui. Services of the universe (ground-set services plus every container with a compose-log line) with NO record inside any calibration window at the first rate listed, so no w and no sensor (they never emit in normal operation or emit outside the window) (4): db, rabbitmq, recommender, registry.


### hotel

| rate | services (sensors) | held-out | held-out alarms (all services) | sum of upper bounds /h | regime | episodes | target sensor detected | min s | median s | max s | any service detected | median s | target w (median s) | target pre-onset alarms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.05 | 6 | 24 cells, 1.200 h | 6 | 23.72 | search-pause-effect | 4 | 4/4 | 20.01 | 20.01 | 20.01 | 4/4 | 20.01 | 20.02 | 0 |
| 0.2 | 6 | 24 cells, 1.200 h | 6 | 23.72 | search-pause-effect | 4 | 4/4 | 5.00 | 5.00 | 5.01 | 4/4 | 5.00 | 5.00 | 0 |
| 1 | 6 | 24 cells, 1.200 h | 9 | 27.52 | search-pause-effect | 4 | 4/4 | 1.00 | 1.00 | 1.03 | 4/4 | 1.00 | 1.00 | 0 |
| 10 | 6 | 24 cells, 1.200 h | 6 | 23.72 | search-pause-effect | 4 | 4/4 | 0.15 | 0.18 | 0.22 | 4/4 | 0.18 | 0.11 | 0 |

Services with a sensor (6): frontend, geo, profile, rate, reservation, search. Services of the universe (ground-set services plus every container with a compose-log line) with NO record inside any calibration window at the first rate listed, so no w and no sensor (they never emit in normal operation or emit outside the window) (4): attractions, recommendation, review, user.

**What this cannot say.** w is the maximum of a few cells (OTel 3 cells, 540 s), an extreme-value estimate with no coverage guarantee (under leave-one-cell-out the cell holding the largest gap alarms when left out, so each service shows about one alarm per rate by exchangeability: the TeaStore and Hotel held-out counts are close to the number of services, which is that rule's false-alarm rate, 1 per n cells per service, not a defect); the held-out alarm count is a count over 0.10 h (OTel) and the Poisson bound on 0 alarms is 2.9957/H per service, 30/h per service at H = 0.10 h, so the summed bound is large however well the sensor behaves. The load is a deterministic constant-rate schedule, so at TeaStore and Hotel rates the calibrated w is about the request interval (Hotel: 20 / 5 / 1 / 0.1 s at 0.05 / 0.2 / 1 / 10 req/s) and the detection time is about w: the sensor watches the load schedule as much as the service. A silence sensor needs a service that emits during normal operation (see the services without a sensor). It detects the paused service, not a degraded one, and it does not distinguish the pause from a collector or host failure (shared fate). Records are service-side stamps for spans and metrics.


## O5 price versus detection (table only)

x = summed price per hour of the set's sensors. **Charged** = decision 73 (honest upper bound, the rate's largest evidenced bound for sensors evaluated in 0 folds). **If evaluated at zero alarms** = honest bound where one exists, else 2.9957/T_r. The ledger is in every set and is not priced (`0`). The silence lane's price is the sum of per-service held-out Poisson bounds (a different estimator; target-only row has no price). y = pause-type episodes detected / total by (ledger union set) under the reading in the `reading` column; median over detected; `mean (miss = hold)` is the objective's penalised mean. Frozen/inf/out-of-the-box rows exist only where a frozen set was scored (E, TeaStore C); Hotel has none.


**otel, off-path pooled, blocks 1-5, rate 25.00**

| lane | set | reading | x charged /h | x if zero alarms /h | detected | median s | min s | mean (miss = hold) | note |
|---|---|---|---|---|---|---|---|---|---|
| ledger | ledger alone | e-only/exclude | 0.00 | 0.00 | 3/10 | 37.19 | 20.25 | 52.34 | request ledger E is in every set and is not priced here |
| frozen | frozen set @6/T_r (1 sensor) | e-only/exclude | 19.97 | 19.97 | 4/10 | 5.02 | 4.56 | 39.52 |  |
| inf | inf set (4 sensors) | e-only/exclude | 569.18 | 79.89 | 10/10 | 41.18 | 4.56 | 29.38 |  |
| out-of-the-box | out of the box (344) | e-only/exclude | 9997.39 | 9834.29 | 7/10 | 5.33 | 0.32 | 23.10 |  |
| full | full (V_r, 4417) | e-only/exclude | 709682.96 | 98388.54 | 10/10 | 0.35 | 0.12 | 1.14 |  |
| own | own: cheapest full-coverage own sensor per class (2) | count-all/own-only | 51.60 | 51.60 | 10/10 | 1.29 | 0.88 | 1.26 | uses the injected target's own telemetry (decisions 84/111 exclude it from the rules) |
| coordinator | coordinator: one Kafka id per class (2) | count-all/exclude | 366.14 | 39.94 | 10/10 | 43.89 | 20.25 | 40.89 |  |
| silence | silence: all services, earliest alarm anywhere | own records | 594.86 | 594.86 | 10/10 | 0.82 | 0.43 | 0.81 | price = sum over the 16 services of the held-out Poisson 95 % upper bound / held-out hours (blocks 4-5, 0.10 h); not the LOCO bound |
| silence | silence: the target's sensor only (target known) | own records | — | — | 10/10 | 0.82 | 0.43 | 0.81 | needs the injected target's identity |

**otel, off-path test blocks 4-5, rate 25.00**

| lane | set | reading | x charged /h | x if zero alarms /h | detected | median s | min s | mean (miss = hold) | note |
|---|---|---|---|---|---|---|---|---|---|
| ledger | ledger alone | e-only/exclude | 0.00 | 0.00 | 1/4 | 20.25 | 20.25 | 50.11 | request ledger E is in every set and is not priced here |
| frozen | frozen set @6/T_r (1 sensor) | e-only/exclude | 19.97 | 19.97 | 1/4 | 20.25 | 20.25 | 50.11 |  |
| inf | inf set (4 sensors) | e-only/exclude | 569.18 | 79.89 | 4/4 | 44.01 | 20.25 | 38.14 |  |
| out-of-the-box | out of the box (344) | e-only/exclude | 9997.39 | 9834.29 | 3/4 | 13.08 | 0.32 | 22.47 |  |
| full | full (V_r, 4417) | e-only/exclude | 709682.96 | 98388.54 | 4/4 | 2.87 | 0.32 | 2.47 |  |
| own | own: cheapest full-coverage own sensor per class (2) | count-all/own-only | 51.60 | 51.60 | 4/4 | 1.32 | 1.02 | 1.30 | uses the injected target's own telemetry (decisions 84/111 exclude it from the rules) |
| coordinator | coordinator: one Kafka id per class (2) | count-all/exclude | 366.14 | 39.94 | 4/4 | 44.01 | 20.25 | 38.14 |  |
| silence | silence: all services, earliest alarm anywhere | own records | 594.86 | 594.86 | 4/4 | 0.86 | 0.57 | 0.84 | price = sum over the 16 services of the held-out Poisson 95 % upper bound / held-out hours (blocks 4-5, 0.10 h); not the LOCO bound |
| silence | silence: the target's sensor only (target known) | own records | — | — | 4/4 | 0.86 | 0.57 | 0.84 | needs the injected target's identity |

**teastore, auth-freeze-effect pooled, rate 10.00**

| lane | set | reading | x charged /h | x if zero alarms /h | detected | median s | min s | mean (miss = hold) | note |
|---|---|---|---|---|---|---|---|---|---|
| ledger | ledger alone | e-only/exclude | 0.00 | 0.00 | 7/7 | 0.51 | 0.48 | 0.51 | request ledger E is in every set and is not priced here |
| frozen | primary 6/h (1 sensor(s); frozen before campaign C) | e-only/exclude | 3.80 | 3.80 | 7/7 | 0.51 | 0.48 | 0.51 | includes episodes of the placement's own training campaigns (in-sample for those) |
| inf | primary inf (2 sensor(s); frozen before campaign C) | e-only/exclude | 7.59 | 7.59 | 7/7 | 0.51 | 0.48 | 0.51 | includes episodes of the placement's own training campaigns (in-sample for those) |
| full | full (V_r, 464) | e-only/exclude | 1808.10 | 1290.44 | 7/7 | 0.51 | 0.48 | 0.51 |  |
| own | own: cheapest full-coverage own sensor (1) | count-all/own-only | 3.80 | 3.80 | 7/7 | 0.47 | 0.45 | 0.47 | uses the injected target's own telemetry (decisions 84/111 exclude it from the rules) |
| coordinator | coordinator: registry heartbeat removal (1) | count-all/exclude | 59.91 | 2.40 | 7/7 | 0.51 | 0.48 | 0.51 |  |
| silence | silence: all 4 services, earliest alarm anywhere | own records | 15.18 | 15.18 | 7/7 | 0.43 | 0.40 | 0.43 | price = sum over services of the leave-one-cell-out Poisson 95 % upper bound / held-out hours |
| silence | silence: the target's sensor only (target known) | own records | — | — | 7/7 | 0.43 | 0.40 | 0.44 |  |

**teastore, auth-freeze-effect pooled, rate 1.00**

| lane | set | reading | x charged /h | x if zero alarms /h | detected | median s | min s | mean (miss = hold) | note |
|---|---|---|---|---|---|---|---|---|---|
| ledger | ledger alone | e-only/exclude | 0.00 | 0.00 | 7/7 | 1.61 | 1.04 | 1.44 | request ledger E is in every set and is not priced here |
| frozen | primary 6/h (1 sensor(s); frozen before campaign C) | e-only/exclude | 3.65 | 3.65 | 7/7 | 1.61 | 1.04 | 1.44 | includes episodes of the placement's own training campaigns (in-sample for those) |
| inf | primary inf (2 sensor(s); frozen before campaign C) | e-only/exclude | 8.49 | 8.49 | 7/7 | 1.61 | 1.04 | 1.44 | includes episodes of the placement's own training campaigns (in-sample for those) |
| full | full (V_r, 463) | e-only/exclude | 1649.58 | 1258.00 | 7/7 | 1.61 | 1.04 | 1.44 |  |
| own | own: cheapest full-coverage own sensor (1) | count-all/own-only | 2.30 | 2.30 | 7/7 | 1.50 | 0.93 | 1.33 | uses the injected target's own telemetry (decisions 84/111 exclude it from the rules) |
| coordinator | coordinator: registry heartbeat removal (1) | count-all/exclude | 51.25 | 2.30 | 7/7 | 1.61 | 1.04 | 1.44 |  |
| silence | silence: all 4 services, earliest alarm anywhere | own records | 14.60 | 14.60 | 7/7 | 0.93 | 0.36 | 0.76 | price = sum over services of the leave-one-cell-out Poisson 95 % upper bound / held-out hours |
| silence | silence: the target's sensor only (target known) | own records | — | — | 7/7 | 0.93 | 0.36 | 0.76 |  |

**teastore, auth-freeze-effect pooled, rate 0.20**

| lane | set | reading | x charged /h | x if zero alarms /h | detected | median s | min s | mean (miss = hold) | note |
|---|---|---|---|---|---|---|---|---|---|
| ledger | ledger alone | e-only/exclude | 0.00 | 0.00 | 7/7 | 4.71 | 2.83 | 4.98 | request ledger E is in every set and is not priced here |
| frozen | primary 6/h (1 sensor(s); frozen before campaign C) | e-only/exclude | 2.40 | 2.40 | 7/7 | 4.71 | 2.83 | 4.98 | includes episodes of the placement's own training campaigns (in-sample for those) |
| inf | primary inf (2 sensor(s); frozen before campaign C) | e-only/exclude | 6.19 | 6.19 | 7/7 | 4.71 | 2.83 | 4.98 | includes episodes of the placement's own training campaigns (in-sample for those) |
| full | full (V_r, 464) | e-only/exclude | 1862.90 | 1287.72 | 7/7 | 4.71 | 2.83 | 4.98 |  |
| own | own: cheapest full-coverage own sensor (1) | count-all/own-only | 2.40 | 2.40 | 7/7 | 4.65 | 2.79 | 4.93 | uses the injected target's own telemetry (decisions 84/111 exclude it from the rules) |
| coordinator | coordinator: registry heartbeat removal (1) | count-all/exclude | 59.91 | 2.40 | 7/7 | 4.71 | 2.83 | 4.98 |  |
| silence | silence: all 4 services, earliest alarm anywhere | own records | 15.18 | 15.18 | 7/7 | 2.08 | 0.28 | 2.36 | price = sum over services of the leave-one-cell-out Poisson 95 % upper bound / held-out hours |
| silence | silence: the target's sensor only (target known) | own records | — | — | 7/7 | 3.34 | 1.12 | 3.06 |  |

**teastore, auth-freeze-effect pooled, rate 0.05**

| lane | set | reading | x charged /h | x if zero alarms /h | detected | median s | min s | mean (miss = hold) | note |
|---|---|---|---|---|---|---|---|---|---|
| ledger | ledger alone | e-only/exclude | 0.00 | 0.00 | 7/7 | 6.93 | 1.43 | 9.03 | request ledger E is in every set and is not priced here |
| frozen | primary 6/h (2 sensor(s); frozen before campaign C) | e-only/exclude | 4.79 | 4.79 | 7/7 | 6.93 | 1.43 | 7.61 | includes episodes of the placement's own training campaigns (in-sample for those) |
| inf | primary inf (3 sensor(s); frozen before campaign C) | e-only/exclude | 8.59 | 8.59 | 7/7 | 6.93 | 1.43 | 7.61 | includes episodes of the placement's own training campaigns (in-sample for those) |
| full | full (V_r, 461) | e-only/exclude | 1253.01 | 1195.49 | 7/7 | 6.93 | 1.43 | 7.61 |  |
| own | own: cheapest full-coverage own sensor (1) | count-all/own-only | 2.40 | 2.40 | 7/7 | 6.86 | 1.35 | 8.95 | uses the injected target's own telemetry (decisions 84/111 exclude it from the rules) |
| coordinator | coordinator: registry heartbeat removal (1) | count-all/exclude | 11.98 | 2.40 | 7/7 | 6.93 | 1.43 | 7.16 |  |
| silence | silence: all 4 services, earliest alarm anywhere | own records | 15.18 | 15.18 | 7/7 | 6.85 | 1.34 | 8.94 | price = sum over services of the leave-one-cell-out Poisson 95 % upper bound / held-out hours |
| silence | silence: the target's sensor only (target known) | own records | — | — | 7/7 | 6.85 | 1.34 | 8.94 |  |

**hotel, search-pause-effect pooled, rate 10.00**

| lane | set | reading | x charged /h | x if zero alarms /h | detected | median s | min s | mean (miss = hold) | note |
|---|---|---|---|---|---|---|---|---|---|
| ledger | ledger alone | e-only/exclude | 0.00 | 0.00 | 4/4 | 0.25 | 0.22 | 0.25 | request ledger E is in every set and is not priced here |
| full | full (V_r, 266) | e-only/exclude | 956.81 | 808.32 | 4/4 | 0.25 | 0.22 | 0.25 |  |
| own | own: cheapest full-coverage own sensor (1) | count-all/own-only | 3.95 | 3.95 | 4/4 | 0.24 | 0.21 | 0.25 | uses the injected target's own telemetry (decisions 84/111 exclude it from the rules) |
| coordinator | coordinator | — | — | — | — | — | — | — | none in Hotel: the lane does not exist (no row of detections, no price) |
| silence | silence: all 6 services, earliest alarm anywhere | own records | 23.72 | 23.72 | 4/4 | 0.18 | 0.15 | 0.18 | price = sum over services of the leave-one-cell-out Poisson 95 % upper bound / held-out hours |
| silence | silence: the target's sensor only (target known) | own records | — | — | 4/4 | 0.18 | 0.15 | 0.18 |  |

**hotel, search-pause-effect pooled, rate 1.00**

| lane | set | reading | x charged /h | x if zero alarms /h | detected | median s | min s | mean (miss = hold) | note |
|---|---|---|---|---|---|---|---|---|---|
| ledger | ledger alone | e-only/exclude | 0.00 | 0.00 | 4/4 | 1.20 | 0.72 | 1.17 | request ledger E is in every set and is not priced here |
| full | full (V_r, 266) | e-only/exclude | 1142.88 | 964.39 | 4/4 | 1.20 | 0.72 | 1.17 |  |
| own | own: cheapest full-coverage own sensor (1) | count-all/own-only | 3.95 | 3.95 | 4/4 | 1.19 | 0.70 | 1.15 | uses the injected target's own telemetry (decisions 84/111 exclude it from the rules) |
| coordinator | coordinator | — | — | — | — | — | — | — | none in Hotel: the lane does not exist (no row of detections, no price) |
| silence | silence: all 6 services, earliest alarm anywhere | own records | 27.52 | 27.52 | 4/4 | 1.00 | 1.00 | 1.01 | price = sum over services of the leave-one-cell-out Poisson 95 % upper bound / held-out hours |
| silence | silence: the target's sensor only (target known) | own records | — | — | 4/4 | 1.00 | 1.00 | 1.01 |  |

**hotel, search-pause-effect pooled, rate 0.20**

| lane | set | reading | x charged /h | x if zero alarms /h | detected | median s | min s | mean (miss = hold) | note |
|---|---|---|---|---|---|---|---|---|---|
| ledger | ledger alone | e-only/exclude | 0.00 | 0.00 | 4/4 | 4.77 | 2.93 | 4.62 | request ledger E is in every set and is not priced here |
| full | full (V_r, 266) | e-only/exclude | 1098.31 | 926.06 | 4/4 | 4.77 | 2.93 | 4.62 |  |
| own | own: cheapest full-coverage own sensor (1) | count-all/own-only | 3.95 | 3.95 | 4/4 | 3.78 | 1.94 | 3.63 | uses the injected target's own telemetry (decisions 84/111 exclude it from the rules) |
| coordinator | coordinator | — | — | — | — | — | — | — | none in Hotel: the lane does not exist (no row of detections, no price) |
| silence | silence: all 6 services, earliest alarm anywhere | own records | 23.72 | 23.72 | 4/4 | 5.00 | 5.00 | 5.00 | price = sum over services of the leave-one-cell-out Poisson 95 % upper bound / held-out hours |
| silence | silence: the target's sensor only (target known) | own records | — | — | 4/4 | 5.00 | 5.00 | 5.00 |  |

**hotel, search-pause-effect pooled, rate 0.05**

| lane | set | reading | x charged /h | x if zero alarms /h | detected | median s | min s | mean (miss = hold) | note |
|---|---|---|---|---|---|---|---|---|---|
| ledger | ledger alone | e-only/exclude | 0.00 | 0.00 | 4/4 | 11.48 | 2.59 | 11.05 | request ledger E is in every set and is not priced here |
| full | full (V_r, 265) | e-only/exclude | 845.48 | 734.12 | 4/4 | 5.89 | 2.59 | 7.05 |  |
| own | own: cheapest full-coverage own sensor (1) | count-all/own-only | 2.50 | 2.50 | 4/4 | 11.48 | 2.59 | 11.05 | uses the injected target's own telemetry (decisions 84/111 exclude it from the rules) |
| coordinator | coordinator | — | — | — | — | — | — | — | none in Hotel: the lane does not exist (no row of detections, no price) |
| silence | silence: all 6 services, earliest alarm anywhere | own records | 23.72 | 23.72 | 4/4 | 20.01 | 20.01 | 20.01 | price = sum over services of the leave-one-cell-out Poisson 95 % upper bound / held-out hours |
| silence | silence: the target's sensor only (target known) | own records | — | — | 4/4 | 20.01 | 20.01 | 20.01 |  |

**What this cannot say.** One SUT, host and campaign per row; no row is a comparison across SUTs. The sets are not on a common footing: the frozen sets were chosen on training episodes by the repository's objective, the lane sets were chosen here after seeing all episodes (in-sample by construction; the own sensor is the injection itself); `full` is the ceiling and its price is a convention for 85 % of sensors (fill). Prices of different estimators (leave-one-out honest bound, held-out Poisson, fill) are shown side by side and are not comparable to one decimal. n is 10 off-path episodes (4 test) for E, 28 (7 per rate) for TeaStore, 16 (4 per rate) for Hotel. TeaStore and Hotel faults are on the request path, so the ledger already detects most of them; no off-path TeaStore or Hotel episode exists.

