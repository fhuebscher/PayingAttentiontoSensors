# Traffic sweep, OTel Demo: analysis v3 (v3.1), exploratory, not frozen (every cell of this system was read under v2.4 before v3 was written) (x)

**Exploratory, not frozen.** Protocol rounds 15 and 17 (decisions 61-65 as amended by 67) on v2.4's readers and rules; every cell read here was read under v2.4 first. **Scope: instance** (one SUT, one host). `—` = absent or not evaluable, never 0. Each (sensor, rule) is calibrated per rate by the zero-held-out-alarm selection; **no false-alarm figure here is that selection's own zero**: every count of false alarms is the honest nested leave-one-cell-out count (V3_NESTED_RULE), with its exact 95 % bound.

Binding documents and inputs: research/PROTOCOL_DRAFT_20261002.md round 15 (decisions 61-65, 252cfcd); research/protocol/ANALYSIS_V3_DESIGN.md (252cfcd); research/traffic-sweep/SYNTHESIS_V2_4.md; research/protocol/parameters_v3.json (decision 37); research/traffic-sweep/DECLARATION_OTEL.md (da95915); research/traffic-sweep/AMENDMENT_OTEL_1.md (16ae373); research/traffic-sweep/DECLARATION_QUIET_OTEL.md (593d4ee); research/protocol/METHODOLOGY_HARDENING.md (H1-H11); research/PROTOCOL_DRAFT_20261002.md rounds 7-14 (decisions 26-60; decision 57 = d126589, round 13 = 6162c37, round 14 = c17f6a6); harness observability-placement-runtime-otel-protocol 6e37ec2 (the cell writer and terminal); research/protocol/parameters.json (decision 37).

Analysis: `research/detection-time/sweep_analysis_v3_3.py` v3 (sha256 `c8cd5072ed4b22cae9360e6446f969c75b4e66b900a08d3cfe0efbdadcd36e18`) on v2.4 `sweep_analysis_v2.py` (sha256 `075c43e5870170c8b59cdbe1a970b56dc03920d67514027b9a95e5de38d962e9`), parameters.json `7447b492abf64f42ebaf547a640c84929ac15b59ebc1e495d5082f279373fc68`, parameters_v3.json `212830bec3e6669bc211d5cffa48d61fa3bf0f6d4dd5ceaf79d3e2bcc7c4d000`, HEAD `0a6f52fb8081661f075685516ae066f40958b83f`, Python 3.13.12.

## Outputs that are — by construction

- family S (primary and secondary columns, operating point, P4 candidates): OTel sweep cells keep no cgroup or docker-stats sampler (resources.json holds two docker-engine CPU counters, before and after the window; FAMILY_CHANNELS).
- availability-clock P4 verdict for family M: no measured collector receive stamp (AVAILABILITY_SOURCES, decision 43).
- availability-clock P4 verdict for family T: no measured collector receive stamp (AVAILABILITY_SOURCES, decision 43).
- P3 (every fault): no family is traffic-independent by mechanism (H11).
- out-of-sample check (decision 65): no --validation cells given (campaign B's no-fault cells are the declared source).
- a false-alarm figure from the zero-alarm selection itself: never printed (decision 67): the selected value has 0 held-out alarms on the cells it was chosen on by construction; every false-alarm count below is the honest nested one.

## What was read

Campaigns pooled (H1; decision 68: quiet runs A and A2 pool with the sweep):

- `tmp/otel-f-evidence/f3-fetch2/x`: 25 valid of 25 (accounting-pause 5, fraud-pause 5, frontend-pause 5, no-fault-calibration 10)

| class | r10 valid/found | r1 valid/found | r0.2 valid/found | r0.05 valid/found |
|---|---|---|---|---|
| no-fault-calibration | — | — | — | — |
| frontend-pause | — | — | — | — |
| productcatalog-cpu-throttle | — | — | — | — |
| fraud-pause | — | — | — | — |
| accounting-pause | — | — | — | — |

Cells not scored: none.

Provenance: harness commit —; input digest `f0111965b05a3f6a9487119478876d2bc542b6ce08d0f2f20fc6f0a7441f83b0` over 130 files (v2.4's file set plus docker-events.json[l]).

H4 freeze record per harness and status (V3_FREEZE_EVENTS_RULE; decision 69: a missing or contradictory record keeps the sweep's bound and is counted): B: used 15; reasons: none.

Reader statistics over the valid cells (F11; a drop is counted, never silent): bridgeMappings 0; bridgeTokensWithSeveralTraces 0; bridgeTracesWithSeveralTokens 0; bridgeRowsDropped 0; tracesWithoutToken 21030; probeTracesExcluded 17; probeSpansExcluded 109; spansIncomplete 0; spansUnusable 0; duplicateSpans 0; journeysWithoutStart 0; samplePairsSkipped 0; logRecordsUntimed 0; composeCliLines 0.

## Calibration per (sensor, rule) on the no-fault cells (decisions 61-63, 67)

Each armed (sensor, rule) takes the smallest grid value with zero held-out alarms over the rate's no-fault cells, each scored leave-one-cell-out (v2.4's fit, H1; class-independent). Level rules: K_GRID (<= 100; K = 100 flagged at grid edge), then the range fallback (discrete in effect; up-only for spans and the ledger; may apply where MAD = 0, decision 52 kept for K); `absent`: m x G on m in {1, 1.5, 2, 3, 5}, G including the censored silences of cells with records; an `absent` whose gap exceeds the shortest hold (60.037 s) is **inert**; `appear` per stream; the ledger's `failed` exempt. **honest** = the nested count (each held-out cell at the value re-selected without it), the false-alarm figure; its rate per hour of no-fault time T.

| rate | no-fault cells | T (h) | rules calibrated / dropped / inert / unarmed | at grid edge | range (of them MAD = 0) | sensors placeable / appear-only / not (L, M, S, T) | dof | E `failed` in no-fault (exempt) | calibrated rules: median folds armed of the rate's cells · out of the detector in every nested fold · honest — (no nested evidence) | placeable sensors with CELF cost — |
|---|---|---|---|---|---|---|---|---|---|---|
| r25 | 6 | 0.300 | 5490 / 3812 / 52 / 13016 | 3 | 170 (123) | 398 / 4328 / 6126 | 1162 | add-to-cart 0, ads 0, checkout 0, index 0, product 0, recommendations 0, view-cart 0 | 6 of 6 · 3 · 3 | 3631 |

Per family and rule (primary): calibrated / dropped / inert / unarmed.

| rate | family | appear | absent | spike | run3 | median |
|---|---|---|---|---|---|---|
| r25 | E | — | 7 / 0 / 0 / 0 | 7 / 0 / 0 / 0 | 7 / 0 / 0 / 0 | 7 / 0 / 0 / 0 |
| r25 | L | 4302 / 3749 / 0 / 2311 | 39 / 8 / 52 / 10263 | — | — | — |
| r25 | M | — | — | 247 / 43 / 0 / 104 | 287 / 3 / 0 / 104 | 289 / 1 / 0 / 104 |
| r25 | T | 26 / 0 / 0 / 70 | 70 / 0 / 0 / 15 | 62 / 8 / 0 / 15 | 70 / 0 / 0 / 15 | 70 / 0 / 0 / 15 |

**The ledger E** per rate (route; `failed` **exempt**, decision 63: never calibrated, always compared; its no-fault count is reported):

- r25: `absent` calibrated (m 1, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 3, honest 0); `run3` calibrated (K 3, honest 1); `spike` calibrated (K 80, honest 1); `absent` calibrated (m 1.5, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 40, honest 1); `absent` calibrated (m 1, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 3.5, honest 1); `spike` calibrated (K 16, honest 1); `absent` calibrated (m 1, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 3, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 8, honest 1); `absent` calibrated (m 1, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 12.5, honest 1); `run3` calibrated (K 4, honest 2); `spike` calibrated (K 80, honest 1); `absent` calibrated (m 1.5, honest 1); `failed` exempt (no-fault count 0); `median` calibrated (K 4, honest 1); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 50, honest 2); `absent` calibrated (m 1.5, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 4, honest 1); `run3` calibrated (K 3.5, honest 2); `spike` calibrated (K 50, honest 1).
- E's catching rule in the episodes (primary): accounting-pause r25: `spike` 1, `—` 4; fraud-pause r25: `—` 5; frontend-pause r25: `absent` 5.

**Dropped (sensor, rule) pairs** (held-out alarms at the last grid value; honest count beside), primary:

- r25 (3812): `metric:kafka:jvm.memory.used_after_last_gc/spike` 35 (honest —), `metric:kafka:jvm.memory.used_after_last_gc/run3` 11 (honest —), `metric:kafka:jvm.memory.used_after_last_gc/median` 7 (honest —), `metric:cartservice:process.runtime.dotnet.thread_pool.threads.count/spike` 4 (honest 4), `metric:cartservice:process.thread.count/spike` 4 (honest 4), `metric:kafka:kafka.logs.flush.Count/spike` 3 (honest 3), `metric:shippingservice:calls/spike` 3 (honest —), `metric:shippingservice:duration~rate/spike` 3 (honest —), `metric:flagd:calls/spike` 2 (honest 0), `metric:flagd:duration~rate/spike` 2 (honest 0), `metric:frauddetectionservice:calls/spike` 2 (honest —), `metric:frauddetectionservice:duration~rate/spike` 2 (honest —), `metric:kafka:kafka.request.time.50p/spike` 2 (honest —), `span:quoteservice:POST_/getquote/spike` 2 (honest 2), `span:quoteservice:{closure}/spike` 2 (honest —), `log:checkoutservice:007326c5f618/appear` 1 (honest 1), `log:checkoutservice:00761e02ec9b/appear` 1 (honest 1), `log:checkoutservice:009ee53cae3d/appear` 1 (honest 1), `log:checkoutservice:00b6ad7a763f/appear` 1 (honest 1), `log:checkoutservice:00cbc3d36d69/appear` 1 (honest 1), `log:checkoutservice:011973c7d9cd/appear` 1 (honest 1), `log:checkoutservice:013c4f8adefe/appear` 1 (honest 1), `log:checkoutservice:0143da4762bf/appear` 1 (honest 1), `log:checkoutservice:0173e7968cef/appear` 1 (honest 1), `log:checkoutservice:0179a5a94274/appear` 1 (honest 1), `log:checkoutservice:01857fdda71a/appear` 1 (honest 1), `log:checkoutservice:01f2553f8ba0/appear` 1 (honest 1), `log:checkoutservice:01f9af01cdc4/appear` 1 (honest 1), `log:checkoutservice:023b1aa5a499/appear` 1 (honest 1), `log:checkoutservice:02a242272030/appear` 1 (honest 1), `log:checkoutservice:02d2e2ae9aa0/appear` 1 (honest 1), `log:checkoutservice:02e0aba92a3a/appear` 1 (honest 1), `log:checkoutservice:033fd165901e/appear` 1 (honest 1), `log:checkoutservice:036bef3460ac/appear` 1 (honest 1), `log:checkoutservice:036f3d453110/appear` 1 (honest 1), `log:checkoutservice:0389a816d13c/appear` 1 (honest 1), `log:checkoutservice:038b8d984c9b/appear` 1 (honest 1), `log:checkoutservice:0390ee1cf7e2/appear` 1 (honest 1), `log:checkoutservice:039db18e1bb7/appear` 1 (honest 1), `log:checkoutservice:03ac43696fd2/appear` 1 (honest 1) (+3772 more in the JSON)

**Inert** (calibrated by the selection, but the gap exceeds the hold; not placeable), **at grid edge** (K = 100) and **appear-only** sensors (placeable through `appear` alone, listed apart), primary:

- r25: inert 52: `log:checkoutservice:0e13dbc9fcd1/absent`, `log:checkoutservice:13543c5f5f6f/absent`, `log:checkoutservice:13d16841d4f8/absent`, `log:checkoutservice:2a9fcbbf70c5/absent`, `log:checkoutservice:2ffab91d523a/absent`, `log:checkoutservice:34bacbc4b75b/absent`, `log:checkoutservice:38ee07570cbe/absent`, `log:checkoutservice:3e1152e7e0e2/absent`, `log:checkoutservice:4af4c4d821b1/absent`, `log:checkoutservice:50fe13ab9a5a/absent`, `log:checkoutservice:5207a3d2f487/absent`, `log:checkoutservice:5e348483dd56/absent`, `log:checkoutservice:617303abf0d3/absent`, `log:checkoutservice:78a3b5faeed8/absent`, `log:checkoutservice:83bb79d6c2b3/absent`, `log:checkoutservice:8b280c303dcf/absent`, `log:checkoutservice:8ca156b78a3b/absent`, `log:checkoutservice:90117c3c0547/absent`, `log:checkoutservice:93f73e69d885/absent`, `log:checkoutservice:9940a99a9a58/absent`, `log:checkoutservice:998500ab0e90/absent`, `log:checkoutservice:a5520c812d79/absent`, `log:checkoutservice:a7b689e68a47/absent`, `log:checkoutservice:aeb397052dfb/absent`, `log:checkoutservice:b9ff3581a20c/absent`, `log:checkoutservice:c69f76e1e861/absent`, `log:checkoutservice:c89041a852fa/absent`, `log:checkoutservice:cb53f2e81fbe/absent`, `log:checkoutservice:d117981136d2/absent`, `log:checkoutservice:d1ff44daf980/absent`, `log:checkoutservice:d85149b5b9d9/absent`, `log:checkoutservice:dd4b5c63f163/absent`, `log:checkoutservice:df417ff3326b/absent`, `log:checkoutservice:dfc973b49747/absent`, `log:checkoutservice:e2bb20161875/absent`, `log:checkoutservice:e6f26b8a856d/absent`, `log:checkoutservice:f48c61a3fd14/absent`, `log:checkoutservice:fa374823bcdd/absent`, `log:checkoutservice:fd39b12534d6/absent`, `log:emailservice:3c27c4f1f296/absent` (+12 more in the JSON); at grid edge 3: `metric:recommendationservice:system.disk.io/spike`, `metric:recommendationservice:system.disk.operations/spike`, `span:frontend:executing_api_route_(pages)_/api/products/[productId]/spike`; appear-only 4328: `log:accountingservice:020200dc7516`, `log:accountingservice:0cbef0efec68`, `log:accountingservice:0de465075c04`, `log:accountingservice:1beb330393a9`, `log:accountingservice:2af1c460813c`, `log:accountingservice:33a6342b9bdb`, `log:accountingservice:34d5bac2ad4c`, `log:accountingservice:4effb619229a`, `log:accountingservice:4fafe2bb2232`, `log:accountingservice:6914926388fe`, `log:accountingservice:777c0dd6ebb5`, `log:accountingservice:7f002e6ec6b1`, `log:accountingservice:9a7a46c343db`, `log:accountingservice:9b571bf8f84c`, `log:accountingservice:a103a6589a2b`, `log:accountingservice:b526f7e58c37`, `log:accountingservice:b6f2976d0cc7`, `log:accountingservice:b8c4b352bb62`, `log:accountingservice:d226aab7909f`, `log:accountingservice:d40fabb1daa8`, `log:accountingservice:ed7c55d1722e`, `log:accountingservice:f6d2a8fd7279`, `log:accountingservice:f70ba64be717`, `log:accountingservice:f904ab2a1231`, `log:adservice:15386f04ccf3`, `log:adservice:237bd2e48941`, `log:adservice:46aa7009ba09`, `log:adservice:5966dd28c645`, `log:adservice:6b83755ca1d0`, `log:adservice:eb13be1d2f61`, `log:adservice:ec57eec38dad`, `log:adservice:f7061b25a6f8`, `log:cartservice:9d2d534593fb`, `log:cartservice:f3b5e31a4607`, `log:checkoutservice:0026966c9817`, `log:checkoutservice:0029ed656800`, `log:checkoutservice:00a439b58a0c`, `log:checkoutservice:00b898905cdc`, `log:checkoutservice:00bbf3375858`, `log:checkoutservice:00c91439ede2` (+4288 more in the JSON).

**Not placeable at this quiet time** (L, M, S, T sensors with no calibrated rule), by family (with a dropped rule / inert / unarmed only), then those with a dropped rule:

- r25: 6126 sensors (L 3757/52/2212, M 1/0/104); with a dropped rule: `log:checkoutservice:007326c5f618`, `log:checkoutservice:00761e02ec9b`, `log:checkoutservice:009ee53cae3d`, `log:checkoutservice:00b6ad7a763f`, `log:checkoutservice:00cbc3d36d69`, `log:checkoutservice:011973c7d9cd`, `log:checkoutservice:013c4f8adefe`, `log:checkoutservice:0143da4762bf`, `log:checkoutservice:0173e7968cef`, `log:checkoutservice:0179a5a94274`, `log:checkoutservice:01857fdda71a`, `log:checkoutservice:01f2553f8ba0`, `log:checkoutservice:01f9af01cdc4`, `log:checkoutservice:023b1aa5a499`, `log:checkoutservice:02a242272030`, `log:checkoutservice:02d2e2ae9aa0`, `log:checkoutservice:02e0aba92a3a`, `log:checkoutservice:033fd165901e`, `log:checkoutservice:036bef3460ac`, `log:checkoutservice:036f3d453110`, `log:checkoutservice:0389a816d13c`, `log:checkoutservice:038b8d984c9b`, `log:checkoutservice:0390ee1cf7e2`, `log:checkoutservice:039db18e1bb7`, `log:checkoutservice:03ac43696fd2`, `log:checkoutservice:03d24f0f87d8`, `log:checkoutservice:03f97b12b4ed`, `log:checkoutservice:0406515da8f9`, `log:checkoutservice:04210bb6f40f`, `log:checkoutservice:045634945b0b`, `log:checkoutservice:046034c224e7`, `log:checkoutservice:04bdf2258e5c`, `log:checkoutservice:05265db0c0e7`, `log:checkoutservice:0539367934ad`, `log:checkoutservice:055dd1fb8d5a`, `log:checkoutservice:0589245ffc53`, `log:checkoutservice:058f703d02cb`, `log:checkoutservice:05d3940dfce0`, `log:checkoutservice:05d692170c18`, `log:checkoutservice:0602886774ff` (+3718 more in the JSON)

- `appear` (V3_APPEAR_RULE): new streams in no-fault cells per service, summed over the held-out cells (they enter the honest counts): r25 checkoutservice 1605, paymentservice 2, recommendationservice 2142.
- **floor arm (share 0.05)**: r25 5490/3812/52/13016 rules, 398 placeable + 4328 appear-only sensors.
- **sensitivity, <= 1 held-out alarm (K_GRID only, no range fallback)**: r25 5342/71/54/16903 rules, 357 placeable + 4328 appear-only sensors.

## Honest false alarms (decisions 64, 67): nested leave-one-cell-out unions on the no-fault cells

Union of the sensors' rules, each held-out no-fault cell scored at the values re-selected without it (its leave-one-cell-out fit), restarted after each alarm: count (/h [exact 95 % bound]); per family also the sum of its calibrated rules' honest counts (the reviewer's tally). The honest per-sensor rate is the sensor's false-alarm cost for CELF (JSON calibration.*.sensors.*.honestPerHour). Campaign B's fresh check can certify at best 20.0/h (0 alarms in 0.15 h per rate).

| setting | rate | T (h) | E | L | M | S | T | all placeable L, M, S, T |
|---|---|---|---|---|---|---|---|---|
| primary | r25 | 0.300 | 18 (60.0/h [89.0], 0.300 of 0.30 h) · sum 18 · no evidence: 0 rules, 7 sensors | 3778 (12593.3/h [12935.6], 0.300 of 0.30 h) · sum 13 · no evidence: 0 rules, 3626 sensors | 191 (636.7/h [717.8], 0.300 of 0.30 h) · sum 241 · no evidence: 3 rules, 1 sensors | — | 180 (600.0/h [678.9], 0.300 of 0.30 h) · sum 128 · no evidence: 0 rules, 4 sensors | 423 (1410.0/h [1528.1], 0.30 of 0.30 h) |
| atMostOne | r25 | 0.300 | 25 (83.3/h [116.4], 0.300 of 0.30 h) · sum 26 · no evidence: 0 rules, 7 sensors | 3800 (12666.7/h [13009.9], 0.300 of 0.30 h) · sum 31 · no evidence: 0 rules, 3626 sensors | 232 (773.3/h [862.2], 0.300 of 0.30 h) · sum 305 · no evidence: 3 rules, 1 sensors | — | 298 (993.3/h [1093.3], 0.300 of 0.30 h) · sum 221 · no evidence: 0 rules, 4 sensors | 592 (1973.3/h [2112.1], 0.30 of 0.30 h) |

P4-selected sets (the sensors P4 selected over its folds, or with one episode the candidates judged a win), honest nested union, primary:

- none

## v2.4 reference row: family operating point (decision 53, 15/h, from v2.4's own code)

K per family: E 80, L —, M —, S —, T 63, system —.

| class | family | r10 | r1 | r0.2 | r0.05 |
|---|---|---|---|---|---|
| frontend-pause | E | — | — | — | — |
| frontend-pause | L | — | — | — | — |
| frontend-pause | M | — | — | — | — |
| frontend-pause | S | — | — | — | — |
| frontend-pause | T | — | — | — | — |
| productcatalog-cpu-throttle | E | — | — | — | — |
| productcatalog-cpu-throttle | L | — | — | — | — |
| productcatalog-cpu-throttle | M | — | — | — | — |
| productcatalog-cpu-throttle | S | — | — | — | — |
| productcatalog-cpu-throttle | T | — | — | — | — |
| fraud-pause | E | — | — | — | — |
| fraud-pause | L | — | — | — | — |
| fraud-pause | M | — | — | — | — |
| fraud-pause | S | — | — | — | — |
| fraud-pause | T | — | — | — | — |
| accounting-pause | E | — | — | — | — |
| accounting-pause | L | — | — | — | — |
| accounting-pause | M | — | — | — | — |
| accounting-pause | S | — | — | — | — |
| accounting-pause | T | — | — | — | — |

## Predictions (primary: calibrated arm, floor primary)

- **P1** (frontend-pause; decision 54's interval, observed = first `failed` catch): 5/5; per rate r10 —, r1 —, r0.2 —, r0.05 —; not evaluable 0; holds by branch: timeout interval 5; verdict **holds**.
- **P2** r10 (failed before the first `failed` catch <= 153.00): —.
- **P2** r1 (failed before the first `failed` catch <= 18.00): —.
- **P2** r0.2 (failed before the first `failed` catch <= 6.00): —.
- **P2** r0.05 (failed before the first `failed` catch <= 3.75): —.
- **P3** frontend-pause: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P3** productcatalog-cpu-throttle: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P3** fraud-pause: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P3** accounting-pause: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P4** compares against the ledger E as the OR of its calibrated rules, its `failed` rule exempt from calibration (decisions 63, 70; V3_P4_LEDGER_READING = `calibrated-ledger`): a dropped ledger rule is listed below, not a reason for `—`. Two arms (decision 67): calibrated (primary) and optimistic bound (dropped rules armed at K = 100 / m = 5, beside, not evidence).
- Dropped ledger rules per rate (decision 70: listed; the ledger compares by its calibrated rules): r25 none.
- **P4a** frontend-pause (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 —; r1 —; r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 —; r1 —; r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4a** productcatalog-cpu-throttle (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 —; r1 —; r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 —; r1 —; r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4a** fraud-pause (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 —; r1 —; r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 —; r1 —; r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4a** accounting-pause (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 —; r1 —; r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 —; r1 —; r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4b** frontend-pause (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 —; r1 —; r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 —; r1 —; r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4b** productcatalog-cpu-throttle (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 —; r1 —; r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 —; r1 —; r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4b** fraud-pause (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 —; r1 —; r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 —; r1 —; r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4b** accounting-pause (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 —; r1 —; r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 —; r1 —; r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.

### P4 per class and rate: placeable sensors, dropped rules and non-placeable sensors on the affected path


### P4 folds (sensor rule vs ledger rule; lead, margin; category)

**Calibrated arm**


**Optimistic bound (not evidence)**


**Per harness** (decision 49 pools the sweep's episode with campaign B's three; V3_HARNESS_TAG_RULE; tags B). Episodes per class and rate: accounting-pause r25 B 5; fraud-pause r25 B 5; frontend-pause r25 B 5.

- P1 holds per harness: B 5/5; P2 within the bound per harness: —.

**Beside the primary** (highest rate where P4 holds):

| verdict | calibrated (primary) | floor arm | <= 1 held-out alarm | optimistic bound (not evidence) |
|---|---|---|---|---|
| P4a frontend-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a productcatalog-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a fraud-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a accounting-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b frontend-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b productcatalog-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b fraud-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b accounting-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC frontend-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC productcatalog-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC fraud-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC accounting-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC frontend-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC productcatalog-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC fraud-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC accounting-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |

## Out-of-sample check (decision 65, 67): calibrated detectors on --validation no-fault cells, no refit

Not computed (no --validation cells given; campaign B's no-fault cells are the declared source; at 0.15 h per rate they can certify at best 20.0/h).

## Primary outcome: time to detection at the calibrated values, misses charged at the hold end

Detected k/n · median [min-max] · **mean over all n** (with BC catches), then without BC. `—` = channel missing.

| class | rate | n | E | E no BC | L | L no BC | M | M no BC | S | S no BC | T | T no BC | L:own | L:own no BC | M:own | M:own no BC | S:own | S:own no BC | T:own | T:own no BC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| frontend-pause | 10 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| frontend-pause | 1 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| frontend-pause | 0.2 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| frontend-pause | 0.05 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| productcatalog-cpu-throttle | 10 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| productcatalog-cpu-throttle | 1 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| productcatalog-cpu-throttle | 0.2 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| productcatalog-cpu-throttle | 0.05 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| fraud-pause | 10 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| fraud-pause | 1 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| fraud-pause | 0.2 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| fraud-pause | 0.05 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| accounting-pause | 10 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| accounting-pause | 1 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| accounting-pause | 0.2 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| accounting-pause | 0.05 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |

## P1 detail (H4, decision 54)

- r25 b1: interval 0.227 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [14.994, 15.219] +- 0.009 s; observed 15.222; holds via **timeout interval**
- r25 b2: interval 0.245 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [15.019, 15.241] +- 0.009 s; observed 15.245; holds via **timeout interval**
- r25 b3: interval 0.245 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [14.993, 15.233] +- 0.009 s; observed 15.235; holds via **timeout interval**
- r25 b4: interval 0.216 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [14.964, 15.244] +- 0.009 s; observed 15.247; holds via **timeout interval**
- r25 b5: interval 0.225 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [15.020, 15.212] +- 0.009 s; observed 15.214; holds via **timeout interval**

- The ledger's calibrated `absent` against the client timeout: r25 add-to-cart: calibrated m 1 g 0.588 s vs timeout 15 s; `absent` before the first `failed` in 5/15 pause episodes; r25 ads: calibrated m 1.5 g 1.128 s vs timeout 15 s; `absent` before the first `failed` in 5/15 pause episodes; r25 checkout: calibrated m 1 g 0.887 s vs timeout 15 s; `absent` before the first `failed` in 5/15 pause episodes; r25 index: calibrated m 1 g 1.485 s vs timeout 15 s; `absent` before the first `failed` in 5/15 pause episodes; r25 product: calibrated m 1 g 0.231 s vs timeout 15 s; `absent` before the first `failed` in 5/15 pause episodes; r25 recommendations: calibrated m 1.5 g 1.123 s vs timeout 15 s; `absent` before the first `failed` in 5/15 pause episodes; r25 view-cart: calibrated m 1.5 g 1.079 s vs timeout 15 s; `absent` before the first `failed` in 5/15 pause episodes.

## Exposure (H5): recorded, the objective unchanged

Route call path: adservice, cartservice, checkoutservice, currencyservice, emailservice, flagd, frontend, frontendproxy, paymentservice, productcatalogservice, quoteservice, recommendationservice, shippingservice. Episodes with no request started in the fault window: 0 of 15. Never-exposed sensors: 569.

## Defaults and declared limits (v3)

- V3_LEVEL_GRID_RULE (parameters_v3.json): level rules (spike, run3, median; the ledger's on ok latency) try K_GRID in ascending order (K <= 100, decision 55, threshold max(K x MAD_SCALE x MAD, relative floor, resolution) as v2.4), then the range fallback (V3_RANGE_FALLBACK_RULE); the first value with at most the criterion's held-out alarms is the rule's calibrated value; none: the rule is dropped. Each rule is calibrated on its own (its own threshold), so run3 and median may fire before spike.
- V3_RANGE_FALLBACK_RULE (parameters_v3.json): range fallback of a level rule: lower = min - V3_RANGE_WIDEN_STEPS x resolution, upper = max + V3_RANGE_WIDEN_STEPS x resolution, min/max over the pooled fault-free level values of the fit's cells (the same probe-excluded segment values the median and MAD come from), resolution = the instrument resolution of RESOLUTION_RULE (0 if none). Thresholds per direction: upper - median (up), median - lower (down), compared with dt.beyond (inclusive), so a value one resolution step beyond the fit range fires. Two-sided for metrics, up-only for the latency channels (span durations, ledger latency). Decision 52 kept: a sensor whose fault-free MAD is 0 has no K rule, and the range fallback may apply to it (it needs the median and n >= MIN_BASELINE_POOLED only). Labelled 'range fallback (discrete in effect)': a continuous series always leaves held-out alarms, so in effect it rescues discrete series only. Not tried in the <= 1 alarm sensitivity setting. A range with no instrument resolution in the fit (a constant instrument, e.g. Hotel's sys_io, sys_psi_io, sys_psi_memory at 0.0 everywhere) or a threshold <= 0 is degenerate: the rule is unarmed with the reason 'range degenerate: no instrument resolution in the fit', never a value, never re-armed in the optimistic arm.
- V3_ABSENT_CENSORED_RULE (parameters_v3.json): G = the largest of, over the fit's cells that have at least one record of the stream in their fault-free segment: the largest inter-arrival gap between records in the segment, the censored silence from the segment start to the first record, and the censored silence from the last record to the segment end. The segment is H1's (segment_stats): a no-fault cell from the barrier to the measurement end, a fault cell from the barrier to startedMonotonic (its trailing silence ends at the onset), whole-second logs cut at the floor of the onset as in v2.4. A cell with no record of the stream contributes nothing (there is no first or last record). Arming unchanged: the pooled record count must reach MIN_BASELINE_POOLED, else the rule is unarmed. The ledger's `absent` uses the completions of its route the same way.
- V3_APPEAR_RULE (parameters_v3.json): `appear` unchanged (fires on a stream with no record in the fault-free data of the fit); per (sensor, appear) its held-out count is the number of held-out no-fault cells in which the stream appears while having no record in that fold's fit; above the criterion it is dropped. A stream with a record in the pooled scoring fit cannot fire `appear` in an episode and is unarmed for `appear` (unless dropped). Because a stream that can fire `appear` in an episode has no no-fault record, its held-out count is 0 by construction; the held-out `appear` alarms per service (new templates or operations in no-fault time) are reported beside, as the vocabulary-level rate. Sensors whose only calibrated rule is `appear` are listed apart from the other placeable sensors (decision 67).
- V3_LEDGER_RULE (parameters_v3.json): the ledger E (per route): `failed` is exempt from calibration (the client's definition of failure, the positive control of P1/P2) and always armed; its count in the no-fault cells of each rate is reported. E's `spike`, `run3`, `median` (ok latency) and `absent` (completions) are calibrated like any sensor's rules.
- V3_CALIBRATION_SCOPE_RULE (parameters_v3.json): calibration is per rate and independent of the fault class: a held-out fold is one no-fault cell of the rate scored with v2.4's leave-one-cell-out fit (every valid cell of the rate except that cell, fault cells contributing their pre-onset segment, H1); every armed (sensor, rule) is counted on its own fires, with the detector restarted after each alarm (v2.4's restart semantics restricted to that rule). The episodes are scored with the pooled fit (H1) at each rule's calibrated value. Decision 55's scored-set calibration (M3) is not applied: the unit is the rule, and the class's path filter and by-construction flags still decide which fires count in scoring.
- V3_STATUS_RULE (parameters_v3.json): each (sensor, rule) at a rate is: calibrated (armed in scoring, held-out count within the criterion at its value, and able to fire inside the hold), dropped (armed, no grid value within the criterion; listed with its held-out count at the last grid value), inert (calibrated by the criterion but unable to fire inside the hold: an `absent` whose scoring gap g exceeds the shortest fault hold of the system; neither calibrated nor a reason to call the sensor placeable), unarmed (cannot fire in scoring at this rate: no pooled level data, pooled n < MIN_BASELINE_POOLED, for K values MAD = 0, for `appear` a record in the pooled fit; listed with the reason) or exempt (the ledger's `failed`). Placeability is per (sensor, rule): a rule is placeable iff calibrated; a sensor with no calibrated rule is 'not placeable at this quiet time'. A K = 100 selection is flagged 'at grid edge'.
- V3_NESTED_RULE (parameters_v3.json): honest nested leave-one-cell-out count of a (sensor, rule) at a rate: for each no-fault cell X of the rate, the grid value is re-selected by the same criterion on the other no-fault cells Y, each scored with a fit that excludes both X and Y (every valid cell of the rate except X and Y, H1); X is then scored at that value with its own leave-one-cell-out fit (exact count, restarted after each alarm). Where no value meets the criterion without X, the rule is not in X's detector (0). Summed over X: the honest count; / T: the honest rate, with its exact bound. A sensor's honest count is the union of its rules so re-selected, simulated per X; a sensor set's likewise (V3_PLACEMENT_FAR_RULE). The honest per-sensor rate is the sensor's false-alarm cost for CELF. F2: the honest count and its hours run over the held-out cells where the rule was in the detector and armed in that cell's fit (`foldsEvaluated`, `honestHours`; the rate's whole T beside); with no such cell the count is — (not evaluable), and a sensor (or set) with no evaluated cell has CELF cost —, never 0.
- V3_TESTABLE_RULE (parameters_v3.json): a held-out fold whose fit cannot arm a (sensor, rule) (level: no pooled scale, n < MIN_BASELINE_POOLED, MAD = 0 for K, a degenerate range; absent: n < MIN_BASELINE_POOLED; appear: a record in the fold's fit) is no evidence: it adds no alarm and no test. A grid value needs at least one armed fold; a rule with no testable value is unarmed ('not testable'). The same holds in the nested re-selection. A rule calibrated on the leave-one-cell-out folds may still be out of the detector, or unarmed, in every nested fold (OTel: 411-460 calibrated rules per rate armed with one cell left out but not with two): its honest count is then — (no nested evidence), never 0 (V3_NESTED_RULE).
- V3_INERT_RULE (parameters_v3.json): an `absent` whose calibrated scoring gap g = m x G exceeds the shortest fault hold among the system's episodes cannot respond to a silence starting at or after the onset inside the hold: status inert (V3_STATUS_RULE); it is not in the scoring detector, and in the nested count it is left out of a held-out cell's detector where its gap in that cell's fit exceeds the hold.
- V3_PLACEMENT_FAR_RULE (parameters_v3.json): placement-level false alarms of a sensor set at a rate: the honest nested union (V3_NESTED_RULE) of its sensors' rules on the rate's no-fault cells: for each held-out cell, the rules at the values re-selected without that cell, simulated together on it with its leave-one-cell-out fit, the union detector restarted after each alarm; count, hours, rate and the exact one-sided FAR_CONFIDENCE Poisson bound; the sum of the members' counts beside (no independence assumed). On validation cells (campaign B): the calibrated values with the pooled fit. No constraint inside the objective. Only held-out cells where at least one of the set's rules is in the detector and armed count, alarms and hours alike; with none the count is —.
- V3_P4_RULE (parameters_v3.json): P4 compares the ledger with the placeable sensors in two arms: calibrated (primary: candidates = fires of calibrated rules only) and optimistic (beside: dropped rules also armed at the largest grid value, K = 100 for level rules, m = 5 for `absent`), as H6's pessimistic and optimistic bounds; decision 55's B1 does not apply. Each (class, rate) names the dropped (sensor, rule) pairs and the non-placeable sensors on the class's affected path. The ledger is the OR of its calibrated rules (decision 70, V3_P4_LEDGER_READING); a dropped ledger rule is listed per rate, not a reason for —. P4 is — where fewer episodes than declared exist (as v2.4). The ledger's `failed` is exempt from calibration, always compared, and labelled so in the readout.
- V3_OPTIMISTIC_ARM_RULE (parameters_v3.json): the optimistic P4 arm scores the episodes with the calibrated detector plus every dropped (sensor, rule) armed at the largest grid value: level rules at K = the last K_GRID value (100), `absent` at the last V3_ABSENT_M_GRID value (5); inert and unarmed rules stay out. It is a bound beside the calibrated arm, never the primary. Printed as 'optimistic bound (not evidence)', never in bold.
- V3_VALIDATION_RULE (parameters_v3.json): out-of-sample check: no-fault cells given with --validation are never pooled into a fit or a calibration; each calibrated (sensor, rule) of the rate, each placeable sensor (OR of its rules) and each reported sensor set (union) is run on them with the pooled scoring fit of the main cells, without refitting; counts, hours and the exact bound are reported. Fault cells given as validation are listed and not used.
- V3_FREEZE_EVENTS_RULE (parameters_v3.json): campaign-B reader (TeaStore, OTel), decisions 54 and 69: a fault cell whose H4 record carries exactly one Docker `pause` event of its target container, inside [command issued - V3_FREEZE_EVENT_TOLERANCE_S, the cell's v2.4 upper bound + V3_FREEZE_EVENT_TOLERANCE_S], with no problem, gets that event as its onset interval's upper bound; P1's tolerance then adds the Docker event granularity and the alignment residual (v2.4's p1_tolerance). Otherwise (decision 69) its H4 record is `missing` with the reasons; the cell stays valid, keeps the sweep's bound and is counted per harness. The sweep's bound is v2.4's per system (decision 69: 'as in the sweep'): TeaStore [command issued, command returned]; OTel [startedMonotonic, appliedMonotonic], appliedMonotonic being the OTel sweep's own bound (F6). Problems: TeaStore sweep.freezeStamps (bbb6b11) status other than `recorded` (its failures become the reasons), failureCount != len(failures), `missing` with no failure, `recorded` with failures (contradictory), the validator's h4 status disagreeing, a null record ('freezeStamps null'); rows of another container or type are left out (F11). OTel docker-events.json (c4aa313) verdict status other than `ok` (its reasons become the reasons), failures != len(reasons), `ok` with reasons or with a stream error / exitedBeforeStop / parseProblems (contradictory), containerId not the receipt's target, an event monotonic that does not replay the producer's bm + (timeNano/1e9 - be) (F7); OTel intervention.freeze.stampCheck status other than `ok` likewise, commandIssuedMonotonic not replaying startedMonotonic, a null `freeze`. Also: zero or several pause events, an event outside the window, no record in a B cell. Hotel's docker-events.jsonl line format is still read (timeNano mapped wall -> ledger clock by the cell's fit). Record key sets are pinned (V3_B_RECORD_KEYS): another key set or an unknown version or kind stops the run (UnknownSchema). Throttle cells keep v2.4's bound; their command, readback and stampCheck records are kept (a problem there marks the record missing, counted).
- V3_HARNESS_TAG_RULE (parameters_v3.json): every cell and episode carries its harness: `B` (a campaign-B study epoch, STUDY_EPOCHS_B: H10 and H4 in the harness) or `sweep` (the traffic sweep's and quiet runs' harness; Hotel's cells are all `sweep`). P2 and P4 pool the sweep's episode with B's three per (fault, rate), 'k of 4' against EPISODES_<SUT> = 4 (decision 49); beside every pooled verdict the readout prints the per-harness breakdown (P4 folds by the held-out episode's harness, P2 episodes, P1 episodes, H4 record status per fault cell).
- V3_POOL_KEY_RULE (parameters_v3.json): a cell's identity in a pooled run is (its campaign directory, its path inside it); a cell given twice stops the run. Quiet run A2 repeats A's plan and run IDs under a new campaign (decision 68), so a run ID or run path alone is not an identity.
- V3_ACCEPTED_DEFAULTS (parameters_v3.json): ['full nesting of the honest count: the inner fits exclude both the held-out and the inner cell (V3_NESTED_RULE)', 'a held-out fold that cannot arm a rule is no evidence (V3_TESTABLE_RULE)', 'inert = an `absent` whose calibrated gap exceeds the shortest episode hold, 60 s on the existing cells (V3_INERT_RULE)', 'P4 is — where an armed ledger rule is dropped at the rate (V3_P4_RULE) — superseded by decision 70 (round 19): the ledger is the OR of its calibrated rules', "the throttle onset bound stays v2.4's (TeaStore command returned, OTel appliedMonotonic) (V3_FREEZE_EVENTS_RULE)", '`appear` on a stream with fault-free records is unarmed; calibration is class-independent (V3_APPEAR_RULE, V3_CALIBRATION_SCOPE_RULE)']
- Known limitation (parameters_v3.json V3_KNOWN_LIMITATIONS): L66 (decision 66, round 16, e12e98f; research/traffic-sweep/OTEL_LOST_BATCH_DIAGNOSIS.md): otelcol.log is a lossy carrier in the existing OTel sweep and quiet cells (the collector's log sampling is on): a span or metric missing there may be a carrier drop, not a system loss. Campaign B's OTel cells disable the sampling, so B's fault cells are read through a lossless carrier while the quiet calibration cells were not; the direction is conservative for `absent` and the level rules (calibration sees extra silences, so gaps and K are larger than a lossless carrier would give).
- Known limitation (parameters_v3.json V3_KNOWN_LIMITATIONS): L-H10 (DECLARATION_B_OTEL_DRAFT.md H10; coordinator 2026-10-09): the sweep's OTel fault cells probed the route right after the fault command (a `during-fault` readiness probe, scope-excluded from L and M scoring by v2.4's probe windows); campaign B's cells do not probe from the onset to the end of the hold. The four pooled episodes per (fault, rate) therefore come from two harnesses (sweep 1, B 3), not one design; the per-harness breakdown is printed beside every pooled verdict.
- Known limitation F7 (v2.4, registry KNOWN_LIMITATIONS): TeaStore fixture cells are written by the harness's test writer (tests/test_teastore_traffic_sweep.py make_sweep_run), which writes resources.json in every cell; the producer writes it in no-fault cells only (modules/teastore/execution/performance_campaign.py:1690-1693). The reader never reads M on TeaStore (FAMILY_CHANNELS), so the fixture difference is untested, not a reader path.
- Known limitation F9 (v2.4, registry KNOWN_LIMITATIONS): TeaStore S samples are placed on the wall clock through the producer's barrier pair (CLOCK_RULE_TEASTORE), not the ledger fit; the P4 margin of an S-vs-ledger lead omits that mapping term, which P1's tolerance includes (receipt-alignment residual). Immaterial at a 5 s cadence; recorded.
- Known limitation F10 (v2.4, registry KNOWN_LIMITATIONS): OTel cell validity is the target-side receipt.json state (it folds in F1/G1/G2/G4, trace completeness and container health); the coordinator-side terminal replay (candidate_terminal.validate_campaign, remote-terminal.json) is not read. TeaStore reads the validator's candidate-validation.json.
- Known limitation F11 (v2.4, registry KNOWN_LIMITATIONS): The harness refuses a cell when one token maps to several Kieker traces, and (woven entry point) when one trace maps to several tokens (modules/teastore/witness/extract_native_token_correlation.py:449-467); the reader drops such bridge rows instead and counts them (readout: reader statistics, bridgeTokensWithSeveralTraces / bridgeTracesWithSeveralTokens). On harness-validated cells both counts are expected 0.
- Known limitation G4 (v2.4, registry KNOWN_LIMITATIONS): OTel: productcatalogservice logs through logrus's default TextFormatter (upstream src/productcatalogservice/main.go:57, not JSON) and frontend writes plain console output, so neither carries an app stamp the reader parses (JSON_LOG_STAMP_RULE notParsed): their L leads read "log lead not counted (no app stamp)" and their lines do not enter LOG_RECEIPT_RULE's bound. Recorded, not fixed (a logfmt reader would be a new layout).
- Not frozen: v3.1 (decision 67) is built; its freeze and review come before campaign B is read.

## v3.2 additions (campaign E)

Frozen v3.2 (FREEZE_V32_20261013.md); harness names pinned at 6a5c2a9 (V32_EPOCH_PROFILES, V32_LEDGER_SCHEMAS).

- Epochs read: `otel-offpath-f-v1` 25. Admitted explicitly: `otel-offpath-e-v1`, `otel-offpath-f-v1`, `otel-offpath-pilot-v1`, `otel-offpath-pilot-v2`.
- Ledger routes: `add-to-cart`, `ads`, `checkout`, `index`, `product`, `recommendations`, `view-cart`.
- Ledger rule: The ledger sensor E fires on any route: every route has its own ledger streams (`ledger:<entry>:<route>`: the `failed` rule exempt, `spike`/`run3`/`median` on the route's ok latencies, `absent` on the route's completions), each calibrated per (sensor, rule) at the rate by v3.1's criterion (zero held-out alarms, honest nested counts) with the route's own baseline; E's detection time in an episode is the earliest counted fire over all routes and rules (v2.4 col_fire / celf_v3 build_table: min over the family). A route with no baseline in a cell has no latency verdict (listed, ledgerRoutesWithoutBaseline). E's false alarms are the union of the routes' alarms (counted per route and rule in the calibration). The route key is the ledger row's `route` field.
- Block selection: all; excluded by the split: 0 cell(s); split file sha256 107cb13aeb52e009754744b136f33b63af69c67d9a2b50e8d9bce14a0e719844.
- Off-path classes scored like the others: `accounting-pause-effect` (accountingservice), `fraud-pause-effect` (frauddetectionservice).
- Declared call-graph edges not observed in the no-fault traces: ['adservice->flagd', 'checkoutservice->kafka', 'kafka->accountingservice', 'kafka->frauddetectionservice', 'paymentservice->flagd', 'productcatalogservice->flagd']; observed edges not declared: [].


## v3.3 additions (campaign F, TeaStore off-path epoch; admission and lanes)

Frozen v3.3 (FREEZE_V33_20261014.md); harness names pinned at 715d57b (OTel F) and f74b29b (teastore-offpath-v1). Scope: instance; a report, no mechanism claim.

- Epochs added by v3.3: `otel-offpath-f-v1`.
- TeaStore pause regimes (explicit targets): —; P1 and P2 declared for `—`.
- Lane rule: Per regime (and per rate), for every fault episode, the earliest COUNTED fire of each lane: (a) own = sensors of the episode's target (excluded from the placement by decisions 84/111; this is a separate report row, the exclusion is unchanged), (b) coordinator = log ids of the system's coordinator service, (c) lag = consumer-group lag metric ids. A lane's cell reads `—` (JSON null) when no sensor of the lane was collected in the cell (`collectedSensors` 0) and 0 fires when sensors were collected and none fired; the summary counts episodes with a fire over episodes with collected sensors, never over all episodes. Beside the counted fire, each lane carries the earliest fire dropped ONLY by a BC flag (`earliestByConstruction`, with `bcFlags`, label 'by construction, not counted'); counting, placement and the pass rule are unchanged. The time is the fire's `ttd` in seconds after the onset command, the readout's conservative time (a whole-second log stamp is timed at the end of its second, detection_time.log_ttd); `ttdLo` is the lower end. Scope: instance (one SUT, one host, one campaign); nothing is a mechanism claim.

### Lanes, `accounting-pause-effect` (target `accountingservice`)

| rate | lane | episodes with collected sensors | with a counted fire | earliest counted fire, median [min, max] | with a by-construction fire (by construction, not counted) | earliest by-construction fire, median [min, max] |
|---|---|---|---|---|---|---|
| 25 | own | 5 of 5 | 5 of 5 | 13.3 s [13.2 s, 17.8 s] | 5 of 5 | 1.4 s [1.0 s, 1.5 s] |
| 25 | coordinator | 5 of 5 | 5 of 5 | 43.9 s [43.8 s, 45.2 s] | 1 of 5 | 26.0 s [26.0 s, 26.0 s] |
| 25 | lag | 5 of 5 | 5 of 5 | 9.3 s [4.4 s, 13.8 s] | 0 of 5 | — [—, —] |

### Lanes, `fraud-pause-effect` (target `frauddetectionservice`)

| rate | lane | episodes with collected sensors | with a counted fire | earliest counted fire, median [min, max] | with a by-construction fire (by construction, not counted) | earliest by-construction fire, median [min, max] |
|---|---|---|---|---|---|---|
| 25 | own | 5 of 5 | 5 of 5 | 13.4 s [12.9 s, 13.6 s] | 5 of 5 | 1.2 s [1.1 s, 1.5 s] |
| 25 | coordinator | 5 of 5 | 5 of 5 | 43.3 s [42.9 s, 43.5 s] | 1 of 5 | 7.3 s [7.3 s, 7.3 s] |
| 25 | lag | 5 of 5 | 5 of 5 | 9.4 s [4.0 s, 9.6 s] | 0 of 5 | — [—, —] |

### Lanes, `frontend-pause-effect` (target `frontend`)

| rate | lane | episodes with collected sensors | with a counted fire | earliest counted fire, median [min, max] | with a by-construction fire (by construction, not counted) | earliest by-construction fire, median [min, max] |
|---|---|---|---|---|---|---|
| 25 | own | 5 of 5 | 5 of 5 | 13.3 s [13.0 s, 13.5 s] | 5 of 5 | 0.4 s [0.3 s, 0.4 s] |
| 25 | coordinator | 5 of 5 | 0 of 5 | — [—, —] | 0 of 5 | — [—, —] |
| 25 | lag | 5 of 5 | 5 of 5 | 14.4 s [14.0 s, 14.6 s] | 0 of 5 | — [—, —] |

