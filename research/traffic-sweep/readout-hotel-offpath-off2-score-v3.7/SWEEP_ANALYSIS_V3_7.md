# Traffic sweep, Hotel: analysis v3 (v3.1), exploratory, not frozen (every cell of this system was read under v2.4 before v3 was written) (x)

**Exploratory, not frozen.** Protocol rounds 15 and 17 (decisions 61-65 as amended by 67) on v2.4's readers and rules; every cell read here was read under v2.4 first. **Scope: instance** (one SUT, one host). `—` = absent or not evaluable, never 0. Each (sensor, rule) is calibrated per rate by the zero-held-out-alarm selection; **no false-alarm figure here is that selection's own zero**: every count of false alarms is the honest nested leave-one-cell-out count (V3_NESTED_RULE), with its exact 95 % bound.

Binding documents and inputs: research/PROTOCOL_DRAFT_20261002.md round 15 (decisions 61-65, 252cfcd); research/protocol/ANALYSIS_V3_DESIGN.md (252cfcd); research/traffic-sweep/SYNTHESIS_V2_4.md; research/protocol/parameters_v3.json (decision 37); research/traffic-sweep/DECLARATION.md (a795fc9); research/traffic-sweep/AMENDMENT_1.md (6aca1ff); research/traffic-sweep/AMENDMENT_2.md (ddf03df); research/traffic-sweep/AMENDMENT_3.md (a7d509d); research/protocol/METHODOLOGY_HARDENING.md (H1-H11); research/PROTOCOL_DRAFT_20261002.md rounds 7-14 (decisions 26-60; round 11 = aae8898, decision 57 = d126589, round 13 = 6162c37, round 14 = c17f6a6); research/traffic-sweep/readout-hotel-r3/REVIEW.md (a61801c, the v1 review); research/traffic-sweep/readout-hotel-r3-v2-fix1/REVIEW.md (cb795c5, the v2 review); research/protocol/parameters.json (decision 37).

Analysis: `research/detection-time/sweep_analysis_v3_7.py` v3 (sha256 `c657d976332c29900c09ea885be73c7351d3a716ed171333d28906a756eaa97b`) on v2.4 `sweep_analysis_v2.py` (sha256 `075c43e5870170c8b59cdbe1a970b56dc03920d67514027b9a95e5de38d962e9`), parameters.json `7447b492abf64f42ebaf547a640c84929ac15b59ebc1e495d5082f279373fc68`, parameters_v3.json `212830bec3e6669bc211d5cffa48d61fa3bf0f6d4dd5ceaf79d3e2bcc7c4d000`, HEAD `f76f8cb255971e0098e95dbee1e723e627d5b95e`, Python 3.13.12.

## Outputs that are — by construction

- availability-clock P4 verdict for family T: no measured collector receive stamp (AVAILABILITY_SOURCES, decision 43).
- P3 (every fault): no family is traffic-independent by mechanism (H11).
- out-of-sample check (decision 65): no --validation cells given (campaign B's no-fault cells are the declared source).
- a false-alarm figure from the zero-alarm selection itself: never printed (decision 67): the selected value has 0 held-out alarms on the cells it was chosen on by construction; every false-alarm count below is the honest nested one.

## What was read

Campaigns pooled (H1; decision 68: quiet runs A and A2 pool with the sweep):

- `tmp/hotel-offpath-evidence/off2-fetch/x`: 30 valid of 30 (consul-pause 10, no-fault-calibration 10, search-pause 10)

| class | r10 valid/found | r1 valid/found | r0.2 valid/found | r0.05 valid/found |
|---|---|---|---|---|
| no-fault-calibration | 5/5 | 5/5 | — | — |
| search-pause | 5/5 | 5/5 | — | — |
| cpu-throttle | — | — | — | — |
| net-delay | — | — | — | — |
| consul-pause | 5/5 | 5/5 | — | — |

Cells not scored: none.

Provenance: harness commit `9ad0b98194f715b921aba187df5ed511082f1f7b`; input digest `aaa6e3b1e6b95c512d967785e1307f9c1c162d678a7d4d209f3871d911fab57e` over 381 files (v2.4's file set plus docker-events.json[l]).

H4 freeze record per harness and status (V3_FREEZE_EVENTS_RULE; decision 69: a missing or contradictory record keeps the sweep's bound and is counted): sweep: Hotel: docker-events.jsonl (v2.4) 20; reasons: none.

## Calibration per (sensor, rule) on the no-fault cells (decisions 61-63, 67)

Each armed (sensor, rule) takes the smallest grid value with zero held-out alarms over the rate's no-fault cells, each scored leave-one-cell-out (v2.4's fit, H1; class-independent). Level rules: K_GRID (<= 100; K = 100 flagged at grid edge), then the range fallback (discrete in effect; up-only for spans and the ledger; may apply where MAD = 0, decision 52 kept for K); `absent`: m x G on m in {1, 1.5, 2, 3, 5}, G including the censored silences of cells with records; an `absent` whose gap exceeds the shortest hold (60.000 s) is **inert**; `appear` per stream; the ledger's `failed` exempt. **honest** = the nested count (each held-out cell at the value re-selected without it), the false-alarm figure; its rate per hour of no-fault time T.

| rate | no-fault cells | T (h) | rules calibrated / dropped / inert / unarmed | at grid edge | range (of them MAD = 0) | sensors placeable / appear-only / not (L, M, S, T) | dof | E `failed` in no-fault (exempt) | calibrated rules: median folds armed of the rate's cells · out of the detector in every nested fold · honest — (no nested evidence) | placeable sensors with CELF cost — |
|---|---|---|---|---|---|---|---|---|---|---|
| r10 | 3 | 0.150 | 503 / 3 / 0 / 224 | 0 | 114 (114) | 92 / 211 / 1 | 292 | hotel-search-v1 0 | 3 of 3 · 0 · 0 | 4 |
| r1 | 3 | 0.150 | 499 / 6 / 0 / 224 | 0 | 132 (132) | 92 / 210 / 1 | 289 | hotel-search-v1 0 | 3 of 3 · 0 · 0 | 3 |

Per family and rule (primary): calibrated / dropped / inert / unarmed.

| rate | family | appear | absent | spike | run3 | median |
|---|---|---|---|---|---|---|
| r10 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r10 | L | 207 / 0 / 0 / 1 | 0 / 0 / 0 / 208 | — | — | — |
| r10 | M | — | — | 11 / 0 / 0 / 0 | 11 / 0 / 0 / 0 | 11 / 0 / 0 / 0 |
| r10 | S | — | — | 63 / 3 / 0 / 0 | 66 / 0 / 0 / 0 | 66 / 0 / 0 / 0 |
| r10 | T | 4 / 0 / 0 / 15 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 |
| r1 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r1 | L | 207 / 0 / 0 / 1 | 0 / 0 / 0 / 208 | — | — | — |
| r1 | M | — | — | 9 / 2 / 0 / 0 | 11 / 0 / 0 / 0 | 11 / 0 / 0 / 0 |
| r1 | S | — | — | 62 / 4 / 0 / 0 | 66 / 0 / 0 / 0 | 66 / 0 / 0 / 0 |
| r1 | T | 3 / 0 / 0 / 15 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 |

**The ledger E** per rate (route; `failed` **exempt**, decision 63: never calibrated, always compared; its no-fault count is reported):

- r10: `absent` calibrated (m 1.5, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 25, honest 1).
- r1: `absent` calibrated (m 1, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 5, honest 1).
- E's catching rule in the episodes (primary): consul-pause r1: `—` 5; consul-pause r10: `—` 5; search-pause r1: `absent` 5; search-pause r10: `absent` 5.

**Dropped (sensor, rule) pairs** (held-out alarms at the last grid value; honest count beside), primary:

- r10 (3): `metric:attractions:sys_io/spike` 1 (honest 1), `metric:geo:sys_psi_cpu/spike` 1 (honest 1), `metric:profile:sys_io/spike` 1 (honest 1)
- r1 (6): `metric:rate:sys_psi_cpu/spike` 2 (honest —), `metric:review:cpu/spike` 2 (honest —), `metric:frontend:sys_psi_cpu/spike` 1 (honest 1), `metric:profile:sys_io/spike` 1 (honest 1), `metric:reservation:sys_psi_cpu/spike` 1 (honest 1), `metric:user:cpu/spike` 1 (honest —)

**Inert** (calibrated by the selection, but the gap exceeds the hold; not placeable), **at grid edge** (K = 100) and **appear-only** sensors (placeable through `appear` alone, listed apart), primary:

- r10: inert 0: none; at grid edge 0: none; appear-only 211: `log:attractions:01e8eaa045e2`, `log:attractions:055dfa393986`, `log:attractions:276af8399ab1`, `log:attractions:2921b55e8c5d`, `log:attractions:35a7c43dcf3a`, `log:attractions:3d4eddfab798`, `log:attractions:40123bda2132`, `log:attractions:4110dcc48969`, `log:attractions:4ff7b7b4686d`, `log:attractions:54654c857d3a`, `log:attractions:5936d995d33c`, `log:attractions:6c24cb701e52`, `log:attractions:8c534c41c8a4`, `log:attractions:9056009088d7`, `log:attractions:9430a0f79158`, `log:attractions:9a746e6bda81`, `log:attractions:b73537dfcea0`, `log:attractions:bd7a3576df3d`, `log:attractions:cf8f513bcc77`, `log:attractions:dbfb07b81d0d`, `log:attractions:eb790194c36c`, `log:attractions:f23bf73a52ab`, `log:attractions:f598fad96168`, `log:attractions:fbcffe4122dc`, `log:frontend:01e8eaa045e2`, `log:frontend:4c991508b008`, `log:frontend:4ff7b7b4686d`, `log:frontend:54654c857d3a`, `log:frontend:58101b7e189c`, `log:frontend:6409fbc62d41`, `log:frontend:6afb7a2a9a8a`, `log:frontend:76ad34b88297`, `log:frontend:7a40a8b4a863`, `log:frontend:9056009088d7`, `log:frontend:905fd48af873`, `log:frontend:9430a0f79158`, `log:frontend:9545bd7940eb`, `log:frontend:9b2f7fc21c10`, `log:frontend:c2625d3f7b03`, `log:frontend:dc0a2b88d05c` (+171 more in the JSON).
- r1: inert 0: none; at grid edge 0: none; appear-only 210: `log:attractions:01e8eaa045e2`, `log:attractions:055dfa393986`, `log:attractions:276af8399ab1`, `log:attractions:2921b55e8c5d`, `log:attractions:35a7c43dcf3a`, `log:attractions:3d4eddfab798`, `log:attractions:40123bda2132`, `log:attractions:4110dcc48969`, `log:attractions:4ff7b7b4686d`, `log:attractions:54654c857d3a`, `log:attractions:5936d995d33c`, `log:attractions:6c24cb701e52`, `log:attractions:8c534c41c8a4`, `log:attractions:9056009088d7`, `log:attractions:9430a0f79158`, `log:attractions:9a746e6bda81`, `log:attractions:b73537dfcea0`, `log:attractions:bd7a3576df3d`, `log:attractions:cf8f513bcc77`, `log:attractions:dbfb07b81d0d`, `log:attractions:eb790194c36c`, `log:attractions:f23bf73a52ab`, `log:attractions:f598fad96168`, `log:attractions:fbcffe4122dc`, `log:frontend:01e8eaa045e2`, `log:frontend:4c991508b008`, `log:frontend:4ff7b7b4686d`, `log:frontend:54654c857d3a`, `log:frontend:58101b7e189c`, `log:frontend:6409fbc62d41`, `log:frontend:6afb7a2a9a8a`, `log:frontend:76ad34b88297`, `log:frontend:7a40a8b4a863`, `log:frontend:9056009088d7`, `log:frontend:905fd48af873`, `log:frontend:9430a0f79158`, `log:frontend:9545bd7940eb`, `log:frontend:9b2f7fc21c10`, `log:frontend:c2625d3f7b03`, `log:frontend:dc0a2b88d05c` (+170 more in the JSON).

**Not placeable at this quiet time** (L, M, S, T sensors with no calibrated rule), by family (with a dropped rule / inert / unarmed only), then those with a dropped rule:

- r10: 1 sensors (L 0/0/1); with a dropped rule: none
- r1: 1 sensors (L 0/0/1); with a dropped rule: none

- `appear` (V3_APPEAR_RULE): new streams in no-fault cells per service, summed over the held-out cells (they enter the honest counts): r10 none; r1 none.
- **floor arm (share 0.05)**: r10 503/3/0/224 rules, 92 placeable + 211 appear-only sensors; r1 499/6/0/224 rules, 92 placeable + 210 appear-only sensors.
- **sensitivity, <= 1 held-out alarm (K_GRID only, no range fallback)**: r10 389/0/0/341 rules, 53 placeable + 211 appear-only sensors; r1 367/0/0/362 rules, 46 placeable + 210 appear-only sensors.

## Honest false alarms (decisions 64, 67): nested leave-one-cell-out unions on the no-fault cells

Union of the sensors' rules, each held-out no-fault cell scored at the values re-selected without it (its leave-one-cell-out fit), restarted after each alarm: count (/h [exact 95 % bound]); per family also the sum of its calibrated rules' honest counts (the reviewer's tally). The honest per-sensor rate is the sensor's false-alarm cost for CELF (JSON calibration.*.sensors.*.honestPerHour). Campaign B's fresh check can certify at best 20.0/h (0 alarms in 0.15 h per rate).

| setting | rate | T (h) | E | L | M | S | T | all placeable L, M, S, T |
|---|---|---|---|---|---|---|---|---|
| primary | r10 | 0.150 | 1 (6.7/h [31.6], 0.150 of 0.15 h) · sum 1 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [20.0], 0.150 of 0.15 h) · sum 0 · no evidence: 0 rules, 0 sensors | 18 (120.0/h [177.9], 0.150 of 0.15 h) · sum 19 · no evidence: 0 rules, 0 sensors | 92 (613.3/h [729.4], 0.150 of 0.15 h) · sum 303 · no evidence: 0 rules, 0 sensors | 126 (840.0/h [973.9], 0.150 of 0.15 h) · sum 96 · no evidence: 0 rules, 4 sensors | 277 (1846.7/h [2039.9], 0.15 of 0.15 h) |
| primary | r1 | 0.150 | 1 (6.7/h [31.6], 0.150 of 0.15 h) · sum 1 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [20.0], 0.150 of 0.15 h) · sum 0 · no evidence: 0 rules, 0 sensors | 22 (146.7/h [209.4], 0.150 of 0.15 h) · sum 20 · no evidence: 0 rules, 0 sensors | 42 (280.0/h [362.2], 0.150 of 0.15 h) · sum 300 · no evidence: 0 rules, 0 sensors | 15 (100.0/h [154.0], 0.150 of 0.15 h) · sum 13 · no evidence: 0 rules, 3 sensors | 83 (553.3/h [664.1], 0.15 of 0.15 h) |
| atMostOne | r10 | 0.150 | 2 (13.3/h [42.0], 0.150 of 0.15 h) · sum 2 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [20.0], 0.150 of 0.15 h) · sum 0 · no evidence: 0 rules, 0 sensors | 22 (146.7/h [209.4], 0.150 of 0.15 h) · sum 31 · no evidence: 0 rules, 0 sensors | 91 (606.7/h [722.2], 0.150 of 0.15 h) · sum 326 · no evidence: 0 rules, 0 sensors | 213 (1420.0/h [1590.8], 0.150 of 0.15 h) · sum 176 · no evidence: 0 rules, 4 sensors | 364 (2426.7/h [2646.6], 0.15 of 0.15 h) |
| atMostOne | r1 | 0.150 | 1 (6.7/h [31.6], 0.150 of 0.15 h) · sum 1 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [20.0], 0.150 of 0.15 h) · sum 0 · no evidence: 0 rules, 0 sensors | 39 (260.0/h [339.6], 0.150 of 0.15 h) · sum 38 · no evidence: 0 rules, 0 sensors | 49 (326.7/h [414.5], 0.150 of 0.15 h) · sum 323 · no evidence: 0 rules, 0 sensors | 34 (226.7/h [301.8], 0.150 of 0.15 h) · sum 29 · no evidence: 0 rules, 3 sensors | 121 (806.7/h [938.1], 0.15 of 0.15 h) |

P4-selected sets (the sensors P4 selected over its folds, or with one episode the candidates judged a win), honest nested union, primary:

- P4a consul-pause-effect r1: `metric:user:sys_memory` -> 0 (0.0/h [20.0], 0.15 of 0.15 h) · sum over the sensors 0
- P4a consul-pause-effect r10: `metric:attractions:sys_memory` -> 0 (0.0/h [20.0], 0.15 of 0.15 h) · sum over the sensors 0
- P4a search-pause-effect r1: `span:frontend:HTTP_GET_/hotels` -> 1 (6.7/h [31.6], 0.15 of 0.15 h) · sum over the sensors 1
- P4a search-pause-effect r10: `span:frontend:HTTP_GET_/hotels` -> 3 (20.0/h [51.7], 0.15 of 0.15 h) · sum over the sensors 3
- P4b consul-pause-effect r1: `metric:consul:sys_psi_cpu` -> 0 (0.0/h [20.0], 0.15 of 0.15 h) · sum over the sensors 0
- P4b search-pause-effect r10: `metric:search:sys_psi_cpu` -> 16 (106.7/h [162.0], 0.15 of 0.15 h) · sum over the sensors 16

## v2.4 reference row: family operating point (decision 53, 15/h, from v2.4's own code)

K per family: E —, L —, M —, S —, T —, system —.

| class | family | r10 | r1 | r0.2 | r0.05 |
|---|---|---|---|---|---|
| search-pause | E | no | no | — | — |
| search-pause | L | no | no | — | — |
| search-pause | M | no | no | — | — |
| search-pause | S | no | no | — | — |
| search-pause | T | no | no | — | — |
| cpu-throttle | E | no | no | — | — |
| cpu-throttle | L | no | no | — | — |
| cpu-throttle | M | no | no | — | — |
| cpu-throttle | S | no | no | — | — |
| cpu-throttle | T | no | no | — | — |
| net-delay | E | no | no | — | — |
| net-delay | L | no | no | — | — |
| net-delay | M | no | no | — | — |
| net-delay | S | no | no | — | — |
| net-delay | T | no | no | — | — |
| consul-pause | E | no | no | — | — |
| consul-pause | L | no | no | — | — |
| consul-pause | M | no | no | — | — |
| consul-pause | S | no | no | — | — |
| consul-pause | T | no | no | — | — |

## Predictions (primary: calibrated arm, floor primary)

- **P1** (search-pause; decision 54's interval, observed = first `failed` catch): 10/10; per rate r10 5/5, r1 5/5, r0.2 —, r0.05 —; not evaluable 0; holds by branch: timeout interval 10; verdict **holds**.
- **P2** r10 (failed before the first `failed` catch <= 13.00): 5/5, counts [11, 11, 11, 11, 11], verdict — (n < 4).
- **P2** r1 (failed before the first `failed` catch <= 4.00): 5/5, counts [2, 2, 2, 2, 2], verdict — (n < 4).
- **P2** r0.2 (failed before the first `failed` catch <= 3.20): —.
- **P2** r0.05 (failed before the first `failed` catch <= 3.05): —.
- **P3** search-pause: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P3** cpu-throttle: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P3** net-delay: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P3** consul-pause: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P4** compares against the ledger E as the OR of its calibrated rules, its `failed` rule exempt from calibration (decisions 63, 70; V3_P4_LEDGER_READING = `calibrated-ledger`): a dropped ledger rule is listed below, not a reason for `—`. Two arms (decision 67): calibrated (primary) and optimistic bound (dropped rules armed at K = 100 / m = 5, beside, not evidence).
- Dropped ledger rules per rate (decision 70: listed; the ledger compares by its calibrated rules): r10 none; r1 none.
- **P4a** search-pause (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 0/5 (ledger missed, sensor caught: 0); r1 0/5 (ledger missed, sensor caught: 0); r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/5 (ledger missed, sensor caught: 0); r1 0/5 (ledger missed, sensor caught: 0); r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4a** cpu-throttle (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 —; r1 —; r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 —; r1 —; r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4a** net-delay (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 —; r1 —; r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 —; r1 —; r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4a** consul-pause (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 0/5 (ledger missed, sensor caught: 3); r1 0/5 (ledger missed, sensor caught: 3); r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/5 (ledger missed, sensor caught: 3); r1 0/5 (ledger missed, sensor caught: 3); r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4b** search-pause (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 0/5 (ledger missed, sensor caught: 0); r1 0/5 (ledger missed, sensor caught: 0); r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/5 (ledger missed, sensor caught: 0); r1 0/5 (ledger missed, sensor caught: 0); r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4b** cpu-throttle (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 —; r1 —; r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 —; r1 —; r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4b** net-delay (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 —; r1 —; r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 —; r1 —; r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4b** consul-pause (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 0/5 (ledger missed, sensor caught: 0); r1 0/5 (ledger missed, sensor caught: 5); r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/5 (ledger missed, sensor caught: 0); r1 0/5 (ledger missed, sensor caught: 5); r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.

### P4 per class and rate: placeable sensors, dropped rules and non-placeable sensors on the affected path

- search-pause r10: placeable sensors 303 (candidates with a catch: 9); dropped on the path: `metric:geo:sys_psi_cpu/spike`; not placeable on the path: `log:frontend:1c9632baa7b5`; dropped ledger rules (listed, decision 70): none
- search-pause r1: placeable sensors 302 (candidates with a catch: 4); dropped on the path: `metric:frontend:sys_psi_cpu/spike`, `metric:rate:sys_psi_cpu/spike`; not placeable on the path: `log:frontend:1c9632baa7b5`; dropped ledger rules (listed, decision 70): none
- consul-pause r10: placeable sensors 303 (candidates with a catch: 3); dropped on the path: none; not placeable on the path: none; dropped ledger rules (listed, decision 70): none
- consul-pause r1: placeable sensors 302 (candidates with a catch: 5); dropped on the path: none; not placeable on the path: none; dropped ledger rules (listed, decision 70): none

### P4 folds (sensor rule vs ledger rule; lead, margin; category)

**Calibrated arm**

- P4a search-pause r10 (candidates 9; paired differences ledger - sensor: mean -0.915 [-0.917, -0.914] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:HTTP_GET_/hotels `spike` 1.110 vs E `absent` 0.195; lead -0.915, margin 9.3e-05; tied 2 (win share 0/2); **not faster**
  - ep2 b2: span:frontend:HTTP_GET_/hotels `spike` 1.159 vs E `absent` 0.244; lead -0.915, margin 7.2e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b3: span:frontend:HTTP_GET_/hotels `spike` 1.144 vs E `absent` 0.228; lead -0.916, margin 0.00011; tied 2 (win share 0/2); **not faster**
  - ep4 b4: span:frontend:HTTP_GET_/hotels `spike` 1.177 vs E `absent` 0.261; lead -0.917, margin 0.00023; tied 2 (win share 0/2); **not faster**
  - ep5 b5: span:frontend:HTTP_GET_/hotels `spike` 1.196 vs E `absent` 0.282; lead -0.914, margin 8.6e-05; tied 2 (win share 0/2); **not faster**
- P4a search-pause r1 (candidates 4; paired differences ledger - sensor: mean -0.984 [-0.987, -0.978] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:HTTP_GET_/hotels `spike` 1.624 vs E `absent` 0.640; lead -0.984, margin 0.00032; tied 2 (win share 0/2); **not faster**
  - ep2 b2: span:frontend:HTTP_GET_/hotels `spike` 1.929 vs E `absent` 0.942; lead -0.987, margin 6e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b3: span:frontend:HTTP_GET_/hotels `spike` 2.095 vs E `absent` 1.108; lead -0.987, margin 6.3e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b4: span:frontend:HTTP_GET_/hotels `spike` 1.293 vs E `absent` 0.311; lead -0.982, margin 7e-05; tied 2 (win share 0/2); **not faster**
  - ep5 b5: span:frontend:HTTP_GET_/hotels `spike` 1.806 vs E `absent` 0.828; lead -0.978, margin 0.00031; tied 2 (win share 0/2); **not faster**
- P4a consul-pause r10 (candidates 3; paired differences ledger - sensor: mean 27.108 [0.000, 45.216] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:attractions:sys_memory `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b2: metric:attractions:sys_memory `run3` 14.847 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: metric:attractions:sys_memory `run3` 14.830 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep4 b4: metric:attractions:sys_memory `run3` 14.784 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep5 b5: metric:attractions:sys_memory `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4a consul-pause r1 (candidates 5; paired differences ledger - sensor: mean 27.378 [0.000, 45.962] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:user:sys_memory `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b2: metric:user:sys_memory `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b3: metric:user:sys_memory `run3` 14.746 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep4 b4: metric:user:sys_memory `run3` 14.325 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep5 b5: metric:user:sys_memory `run3` 14.039 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
- P4b search-pause r10 (candidates 1; paired differences ledger - sensor: mean -19.573 [-19.613, -19.513] s; availability-clock wins 0 of 5 evaluable):
  - ep1 b1: metric:search:sys_psi_cpu `median` 19.808 vs E `absent` 0.195; lead -19.613, margin 9.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b2: metric:search:sys_psi_cpu `median` 19.856 vs E `absent` 0.244; lead -19.612, margin 7.2e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b3: metric:search:sys_psi_cpu `median` 19.841 vs E `absent` 0.228; lead -19.613, margin 0.00011; tied 1 (win share 0/1); **not faster**
  - ep4 b4: metric:search:sys_psi_cpu `median` 19.775 vs E `absent` 0.261; lead -19.514, margin 0.00023; tied 1 (win share 0/1); **not faster**
  - ep5 b5: metric:search:sys_psi_cpu `median` 19.796 vs E `absent` 0.282; lead -19.513, margin 8.6e-05; tied 1 (win share 0/1); **not faster**
- P4b search-pause r1 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `absent` 0.640; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b2: — `—` — vs E `absent` 0.942; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b3: — `—` — vs E `absent` 1.108; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b4: — `—` — vs E `absent` 0.311; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep5 b5: — `—` — vs E `absent` 0.828; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b consul-pause r10 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b2: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b3: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b4: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep5 b5: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b consul-pause r1 (candidates 1; paired differences ledger - sensor: mean 53.630 [50.835, 55.675] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:consul:sys_psi_cpu `spike` 4.574 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep2 b2: metric:consul:sys_psi_cpu `spike` 9.165 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: metric:consul:sys_psi_cpu `spike` 4.746 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep4 b4: metric:consul:sys_psi_cpu `spike` 4.325 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep5 b5: metric:consul:sys_psi_cpu `spike` 9.039 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**

**Optimistic bound (not evidence)**

- P4a search-pause r10 (candidates 9; paired differences ledger - sensor: mean -0.915 [-0.917, -0.914] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:HTTP_GET_/hotels `spike` 1.110 vs E `absent` 0.195; lead -0.915, margin 9.3e-05; tied 2 (win share 0/2); **not faster**
  - ep2 b2: span:frontend:HTTP_GET_/hotels `spike` 1.159 vs E `absent` 0.244; lead -0.915, margin 7.2e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b3: span:frontend:HTTP_GET_/hotels `spike` 1.144 vs E `absent` 0.228; lead -0.916, margin 0.00011; tied 2 (win share 0/2); **not faster**
  - ep4 b4: span:frontend:HTTP_GET_/hotels `spike` 1.177 vs E `absent` 0.261; lead -0.917, margin 0.00023; tied 2 (win share 0/2); **not faster**
  - ep5 b5: span:frontend:HTTP_GET_/hotels `spike` 1.196 vs E `absent` 0.282; lead -0.914, margin 8.6e-05; tied 2 (win share 0/2); **not faster**
- P4a search-pause r1 (candidates 5; paired differences ledger - sensor: mean -0.984 [-0.987, -0.978] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:HTTP_GET_/hotels `spike` 1.624 vs E `absent` 0.640; lead -0.984, margin 0.00032; tied 2 (win share 0/2); **not faster**
  - ep2 b2: span:frontend:HTTP_GET_/hotels `spike` 1.929 vs E `absent` 0.942; lead -0.987, margin 6e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b3: span:frontend:HTTP_GET_/hotels `spike` 2.095 vs E `absent` 1.108; lead -0.987, margin 6.3e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b4: span:frontend:HTTP_GET_/hotels `spike` 1.293 vs E `absent` 0.311; lead -0.982, margin 7e-05; tied 2 (win share 0/2); **not faster**
  - ep5 b5: span:frontend:HTTP_GET_/hotels `spike` 1.806 vs E `absent` 0.828; lead -0.978, margin 0.00031; tied 2 (win share 0/2); **not faster**
- P4a consul-pause r10 (candidates 3; paired differences ledger - sensor: mean 27.108 [0.000, 45.216] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:attractions:sys_memory `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b2: metric:attractions:sys_memory `run3` 14.847 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: metric:attractions:sys_memory `run3` 14.830 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep4 b4: metric:attractions:sys_memory `run3` 14.784 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep5 b5: metric:attractions:sys_memory `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4a consul-pause r1 (candidates 5; paired differences ledger - sensor: mean 27.378 [0.000, 45.962] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:user:sys_memory `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b2: metric:user:sys_memory `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b3: metric:user:sys_memory `run3` 14.746 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep4 b4: metric:user:sys_memory `run3` 14.325 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep5 b5: metric:user:sys_memory `run3` 14.039 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
- P4b search-pause r10 (candidates 1; paired differences ledger - sensor: mean -19.573 [-19.613, -19.513] s; availability-clock wins 0 of 5 evaluable):
  - ep1 b1: metric:search:sys_psi_cpu `median` 19.808 vs E `absent` 0.195; lead -19.613, margin 9.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b2: metric:search:sys_psi_cpu `median` 19.856 vs E `absent` 0.244; lead -19.612, margin 7.2e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b3: metric:search:sys_psi_cpu `median` 19.841 vs E `absent` 0.228; lead -19.613, margin 0.00011; tied 1 (win share 0/1); **not faster**
  - ep4 b4: metric:search:sys_psi_cpu `median` 19.775 vs E `absent` 0.261; lead -19.514, margin 0.00023; tied 1 (win share 0/1); **not faster**
  - ep5 b5: metric:search:sys_psi_cpu `median` 19.796 vs E `absent` 0.282; lead -19.513, margin 8.6e-05; tied 1 (win share 0/1); **not faster**
- P4b search-pause r1 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `absent` 0.640; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b2: — `—` — vs E `absent` 0.942; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b3: — `—` — vs E `absent` 1.108; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b4: — `—` — vs E `absent` 0.311; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep5 b5: — `—` — vs E `absent` 0.828; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b consul-pause r10 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b2: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b3: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b4: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep5 b5: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b consul-pause r1 (candidates 1; paired differences ledger - sensor: mean 53.630 [50.835, 55.675] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:consul:sys_psi_cpu `spike` 4.574 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep2 b2: metric:consul:sys_psi_cpu `spike` 9.165 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: metric:consul:sys_psi_cpu `spike` 4.746 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep4 b4: metric:consul:sys_psi_cpu `spike` 4.325 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep5 b5: metric:consul:sys_psi_cpu `spike` 9.039 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**

**Per harness** (decision 49 pools the sweep's episode with campaign B's three; V3_HARNESS_TAG_RULE; tags sweep). Episodes per class and rate: consul-pause r1 sweep 5; consul-pause r10 sweep 5; search-pause r1 sweep 5; search-pause r10 sweep 5.

- P1 holds per harness: sweep 10/10; P2 within the bound per harness: r10 sweep 5/5; r1 sweep 5/5.
- P4 optimistic P4a consul-pause r1: wins / folds by the held-out episode's harness: sweep 0/5
- P4 optimistic P4a consul-pause r10: wins / folds by the held-out episode's harness: sweep 0/5
- P4 optimistic P4a search-pause r1: wins / folds by the held-out episode's harness: sweep 0/5
- P4 optimistic P4a search-pause r10: wins / folds by the held-out episode's harness: sweep 0/5
- P4 optimistic P4b consul-pause r1: wins / folds by the held-out episode's harness: sweep 0/5
- P4 optimistic P4b consul-pause r10: wins / folds by the held-out episode's harness: sweep 0/5
- P4 optimistic P4b search-pause r1: wins / folds by the held-out episode's harness: sweep 0/5
- P4 optimistic P4b search-pause r10: wins / folds by the held-out episode's harness: sweep 0/5
- P4 primary P4a consul-pause r1: wins / folds by the held-out episode's harness: sweep 0/5
- P4 primary P4a consul-pause r10: wins / folds by the held-out episode's harness: sweep 0/5
- P4 primary P4a search-pause r1: wins / folds by the held-out episode's harness: sweep 0/5
- P4 primary P4a search-pause r10: wins / folds by the held-out episode's harness: sweep 0/5
- P4 primary P4b consul-pause r1: wins / folds by the held-out episode's harness: sweep 0/5
- P4 primary P4b consul-pause r10: wins / folds by the held-out episode's harness: sweep 0/5
- P4 primary P4b search-pause r1: wins / folds by the held-out episode's harness: sweep 0/5
- P4 primary P4b search-pause r10: wins / folds by the held-out episode's harness: sweep 0/5

**Beside the primary** (highest rate where P4 holds):

| verdict | calibrated (primary) | floor arm | <= 1 held-out alarm | optimistic bound (not evidence) |
|---|---|---|---|---|
| P4a search-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a net-delay | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a consul-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b search-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b net-delay | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b consul-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC search-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC net-delay | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC consul-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC search-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC net-delay | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC consul-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |

## Out-of-sample check (decision 65, 67): calibrated detectors on --validation no-fault cells, no refit

Not computed (no --validation cells given; campaign B's no-fault cells are the declared source; at 0.15 h per rate they can certify at best 20.0/h).

## Primary outcome: time to detection at the calibrated values, misses charged at the hold end

Detected k/n · median [min-max] · **mean over all n** (with BC catches), then without BC. `—` = channel missing.

| class | rate | n | E | E no BC | L | L no BC | M | M no BC | S | S no BC | T | T no BC | L:own | L:own no BC | M:own | M:own no BC | S:own | S:own no BC | T:own | T:own no BC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| search-pause | 10 | 5 | 5/5 · 0.24 [0.19–0.28] · **0.24** | (= E) | 0/5 · **60.00** | 0/5 · **60.00** | 5/5 · 1.86 [1.84–1.94] · **1.88** | 0/5 · **60.00** | 5/5 · 4.81 [4.77–4.86] · **4.81** | 5/5 · 14.81 [14.77–14.86] · **14.81** | 5/5 · 0.24 [0.19–0.27] · **0.23** | 5/5 · 1.16 [1.11–1.20] · **1.16** | 0/5 · **60.00** | 0/5 · **60.00** | 5/5 · 14.14 [14.13–14.24] · **14.17** | 0/5 · **60.00** | 5/5 · 9.81 [9.77–9.85] · **9.81** | 5/5 · 19.81 [19.77–19.86] · **19.81** | 5/5 · 0.24 [0.19–0.27] · **0.23** | 0/5 · **60.00** |
| search-pause | 1 | 5 | 5/5 · 0.83 [0.31–1.11] · **0.77** | (= E) | 0/5 · **60.00** | 0/5 · **60.00** | 5/5 · 7.50 [7.13–8.02] · **7.55** | 0/5 · **60.00** | 5/5 · 4.29 [3.92–4.80] · **4.35** | 3/5 · 19.29 [8.92–29.09] · **35.46** | 5/5 · 0.81 [0.30–1.10] · **0.75** | 5/5 · 1.81 [1.29–2.10] · **1.75** | 0/5 · **60.00** | 0/5 · **60.00** | 0/5 · **60.00** | 0/5 · **60.00** | 5/5 · 9.29 [8.92–9.80] · **9.35** | 0/5 · **60.00** | 5/5 · 0.81 [0.30–1.10] · **0.75** | 0/5 · **60.00** |
| search-pause | 0.2 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| search-pause | 0.05 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| cpu-throttle | 10 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| cpu-throttle | 1 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| cpu-throttle | 0.2 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| cpu-throttle | 0.05 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| net-delay | 10 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| net-delay | 1 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| net-delay | 0.2 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| net-delay | 0.05 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| consul-pause | 10 | 5 | 0/5 · **60.00** | (= E) | 0/5 · **60.00** | 0/5 · **60.00** | 0/5 · **60.00** | 0/5 · **60.00** | 3/5 · 14.83 [14.78–14.85] · **32.89** | 3/5 · 14.83 [14.78–14.85] · **32.89** | 1/5 · 47.89 · **57.58** | 1/5 · 47.89 · **57.58** | 0/5 · **60.00** | 0/5 · **60.00** | 5/5 · 1.87 [1.81–4.97] · **2.48** | 0/5 · **60.00** | 5/5 · 4.82 [4.76–4.84] · **4.81** | 0/5 · **60.00** | 0/5 · **60.00** | 0/5 · **60.00** |
| consul-pause | 1 | 5 | 0/5 · **60.00** | (= E) | 0/5 · **60.00** | 0/5 · **60.00** | 2/5 · 7.60 [7.24–7.95] · **39.04** | 2/5 · 7.60 [7.24–7.95] · **39.04** | 3/5 · 14.32 [14.04–14.75] · **32.62** | 3/5 · 14.32 [14.04–14.75] · **32.62** | 1/5 · 3.33 · **48.67** | 1/5 · 3.33 · **48.67** | 0/5 · **60.00** | 0/5 · **60.00** | 5/5 · 1.63 [1.09–4.47] · **2.04** | 0/5 · **60.00** | 5/5 · 4.33 [4.04–4.75] · **4.37** | 5/5 · 4.75 [4.33–9.17] · **6.37** | 0/5 · **60.00** | 0/5 · **60.00** |
| consul-pause | 0.2 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| consul-pause | 0.05 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |

## P1 detail (H4, decision 54)

- r10 b1: interval 0.106 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.008, 1.108] +- 0.012 s; observed 1.110; holds via **timeout interval**
- r10 b2: interval 0.111 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.056, 1.156] +- 0.012 s; observed 1.159; holds via **timeout interval**
- r10 b3: interval 0.106 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.041, 1.141] +- 0.012 s; observed 1.144; holds via **timeout interval**
- r10 b4: interval 0.105 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.075, 1.175] +- 0.012 s; observed 1.177; holds via **timeout interval**
- r10 b5: interval 0.121 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [0.994, 1.194] +- 0.012 s; observed 1.196; holds via **timeout interval**
- r1 b1: interval 0.113 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.621, 1.621] +- 0.013 s; observed 1.624; holds via **timeout interval**
- r1 b2: interval 0.110 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.926, 1.926] +- 0.012 s; observed 1.929; holds via **timeout interval**
- r1 b3: interval 0.108 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.092, 2.093] +- 0.012 s; observed 2.095; holds via **timeout interval**
- r1 b4: interval 0.103 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.291, 1.291] +- 0.012 s; observed 1.293; holds via **timeout interval**
- r1 b5: interval 0.124 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.803, 1.803] +- 0.013 s; observed 1.805; holds via **timeout interval**

- The ledger's calibrated `absent` against the client timeout: r10 hotel-search-v1: calibrated m 1.5 g 0.179 s vs timeout 1 s; `absent` before the first `failed` in 5/10 pause episodes; r1 hotel-search-v1: calibrated m 1 g 1.009 s vs timeout 1 s; `absent` before the first `failed` in 5/10 pause episodes.

## Exposure (H5): recorded, the objective unchanged

Route call path: frontend, geo, memcached-profile, memcached-rate, memcached-reserve, mongodb-geo, mongodb-profile, mongodb-rate, mongodb-reservation, profile, rate, reservation, search. Episodes with no request started in the fault window: 0 of 20. Never-exposed sensors: 121.

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
- Known limitation F7 (v2.4, registry KNOWN_LIMITATIONS): TeaStore fixture cells are written by the harness's test writer (tests/test_teastore_traffic_sweep.py make_sweep_run), which writes resources.json in every cell; the producer writes it in no-fault cells only (modules/teastore/execution/performance_campaign.py:1690-1693). The reader never reads M on TeaStore (FAMILY_CHANNELS), so the fixture difference is untested, not a reader path.
- Known limitation F9 (v2.4, registry KNOWN_LIMITATIONS): TeaStore S samples are placed on the wall clock through the producer's barrier pair (CLOCK_RULE_TEASTORE), not the ledger fit; the P4 margin of an S-vs-ledger lead omits that mapping term, which P1's tolerance includes (receipt-alignment residual). Immaterial at a 5 s cadence; recorded.
- Known limitation F10 (v2.4, registry KNOWN_LIMITATIONS): OTel cell validity is the target-side receipt.json state (it folds in F1/G1/G2/G4, trace completeness and container health); the coordinator-side terminal replay (candidate_terminal.validate_campaign, remote-terminal.json) is not read. TeaStore reads the validator's candidate-validation.json.
- Known limitation F11 (v2.4, registry KNOWN_LIMITATIONS): The harness refuses a cell when one token maps to several Kieker traces, and (woven entry point) when one trace maps to several tokens (modules/teastore/witness/extract_native_token_correlation.py:449-467); the reader drops such bridge rows instead and counts them (readout: reader statistics, bridgeTokensWithSeveralTraces / bridgeTracesWithSeveralTokens). On harness-validated cells both counts are expected 0.
- Known limitation G4 (v2.4, registry KNOWN_LIMITATIONS): OTel: productcatalogservice logs through logrus's default TextFormatter (upstream src/productcatalogservice/main.go:57, not JSON) and frontend writes plain console output, so neither carries an app stamp the reader parses (JSON_LOG_STAMP_RULE notParsed): their L leads read "log lead not counted (no app stamp)" and their lines do not enter LOG_RECEIPT_RULE's bound. Recorded, not fixed (a logfmt reader would be a new layout).
- Not frozen: v3.1 (decision 67) is built; its freeze and review come before campaign B is read.

## v3.2 additions (campaign E)

Frozen v3.2 (FREEZE_V32_20261013.md); harness names pinned at 6a5c2a9 (V32_EPOCH_PROFILES, V32_LEDGER_SCHEMAS).

- Epochs read: `hotel-offpath-v1` 30. Admitted explicitly: `hotel-offpath-v1`.
- Ledger routes: `hotel-search-v1`.
- Ledger rule: The ledger sensor E fires on any route: every route has its own ledger streams (`ledger:<entry>:<route>`: the `failed` rule exempt, `spike`/`run3`/`median` on the route's ok latencies, `absent` on the route's completions), each calibrated per (sensor, rule) at the rate by v3.1's criterion (zero held-out alarms, honest nested counts) with the route's own baseline; E's detection time in an episode is the earliest counted fire over all routes and rules (v2.4 col_fire / celf_v3 build_table: min over the family). A route with no baseline in a cell has no latency verdict (listed, ledgerRoutesWithoutBaseline). E's false alarms are the union of the routes' alarms (counted per route and rule in the calibration). The route key is the ledger row's `route` field.
- Block selection: all; excluded by the split: 0 cell(s); split file sha256 107cb13aeb52e009754744b136f33b63af69c67d9a2b50e8d9bce14a0e719844.
- Off-path classes scored like the others: —.
- Declared call-graph edges not observed in the no-fault traces: ['adservice->flagd', 'cartservice->flagd', 'checkoutservice->cartservice', 'checkoutservice->currencyservice', 'checkoutservice->emailservice', 'checkoutservice->kafka', 'checkoutservice->paymentservice', 'checkoutservice->productcatalogservice', 'checkoutservice->shippingservice', 'frontend->adservice', 'frontend->cartservice', 'frontend->checkoutservice', 'frontend->productcatalogservice', 'frontend->recommendationservice', 'frontendproxy->frontend', 'kafka->accountingservice', 'kafka->frauddetectionservice', 'paymentservice->flagd', 'productcatalogservice->flagd', 'recommendationservice->flagd', 'recommendationservice->productcatalogservice', 'shippingservice->quoteservice']; observed edges not declared: [].


## v3.3 additions (campaign F, TeaStore off-path epoch; admission and lanes)

Frozen v3.3 (FREEZE_V33_20261014.md); harness names pinned at 715d57b (OTel F) and f74b29b (teastore-offpath-v1). Scope: instance; a report, no mechanism claim.

- Epochs added by v3.3: `hotel-offpath-v1`.
- TeaStore pause regimes (explicit targets): —; P1 and P2 declared for `—`.
- Lane rule: Per regime (and per rate), for every fault episode, the earliest COUNTED fire of each lane: (a) own = sensors of the episode's target (excluded from the placement by decisions 84/111; this is a separate report row, the exclusion is unchanged), (b) coordinator = log ids of the system's coordinator service, (c) lag = consumer-group lag metric ids. A lane's cell reads `—` (JSON null) when no sensor of the lane was collected in the cell (`collectedSensors` 0) and 0 fires when sensors were collected and none fired; the summary counts episodes with a fire over episodes with collected sensors, never over all episodes. Beside the counted fire, each lane carries the earliest fire dropped ONLY by a BC flag (`earliestByConstruction`, with `bcFlags`, label 'by construction, not counted'); counting, placement and the pass rule are unchanged. The time is the fire's `ttd` in seconds after the onset command, the readout's conservative time (a whole-second log stamp is timed at the end of its second, detection_time.log_ttd); `ttdLo` is the lower end. Scope: instance (one SUT, one host, one campaign); nothing is a mechanism claim.

### Lanes, `consul-pause-effect` (target `consul`)

| rate | lane | episodes with collected sensors | with a counted fire | earliest counted fire, median [min, max] | with a by-construction fire (by construction, not counted) | earliest by-construction fire, median [min, max] |
|---|---|---|---|---|---|---|
| 10 | own | 5 of 5 | 0 of 5 | — [—, —] | 5 of 5 | 1.9 s [1.8 s, 4.8 s] |
| 10 | coordinator | — | — | — (no coordinator lane is declared for this system) | — | — |
| 10 | lag | — | — | — (no lag lane is declared for this system) | — | — |
| 1 | own | 5 of 5 | 5 of 5 | 4.7 s [4.3 s, 9.2 s] | 5 of 5 | 1.6 s [1.1 s, 4.3 s] |
| 1 | coordinator | — | — | — (no coordinator lane is declared for this system) | — | — |
| 1 | lag | — | — | — (no lag lane is declared for this system) | — | — |

### Lanes, `search-pause-effect` (target `search`)

| rate | lane | episodes with collected sensors | with a counted fire | earliest counted fire, median [min, max] | with a by-construction fire (by construction, not counted) | earliest by-construction fire, median [min, max] |
|---|---|---|---|---|---|---|
| 10 | own | 5 of 5 | 5 of 5 | 19.8 s [19.8 s, 19.9 s] | 5 of 5 | 0.2 s [0.2 s, 0.3 s] |
| 10 | coordinator | — | — | — (no coordinator lane is declared for this system) | — | — |
| 10 | lag | — | — | — (no lag lane is declared for this system) | — | — |
| 1 | own | 5 of 5 | 0 of 5 | — [—, —] | 5 of 5 | 0.8 s [0.3 s, 1.1 s] |
| 1 | coordinator | — | — | — (no coordinator lane is declared for this system) | — | — |
| 1 | lag | — | — | — (no lag lane is declared for this system) | — | — |


## v3.4 additions (Hotel off-path epoch; admission and lanes)

Frozen v3.4 (FREEZE_V34_20261015.md); harness names pinned at Hotel 9ad0b98. Scope: instance; a report, no mechanism claim.

- Epochs added by v3.4: `hotel-offpath-v1`.
- Hotel off-path epoch read: `hotel-offpath-v1`; Hotel rules active: True.
- Hotel pause regimes (explicit targets): {'consul-pause-effect': 'consul', 'search-pause-effect': 'search'}; P1 and P2 declared for `search-pause-effect`.
- Rule: Hotel off-path readout (v3.4 block): (1) the epoch's cells are admitted as the Hotel sweep layout with the declared regimes, targets, rates and postures; a regime outside the epoch's declared set, a fault receipt naming another target than its regime declares, a rate outside the declared rates, a block outside 1..5, a posture other than full, an epoch the registry does not know in a run that contains the off-path epoch, and any regime outside the legacy Hotel set in any campaign (which v2.4 would drop silently as `not scored`) stop the run; (2) legacy Hotel cells of any kind beside the off-path epoch are refused (a legacy cell never collected consul and v3.1's calibration reads a fold without data as zero false alarms, so pooling it would calibrate consul's sensors on absence; legacy fault cells would also enter the calibration under another design); a (regime, rate, block) of the epoch given twice is refused; --split and --test-blocks are refused for Hotel; (3) P1 and P2 are declared for search-pause-effect only; (4) per consul-pause episode the readout records the off-path manifestation fields (receipt manifested, duringState.paused, outageObserved, and whether docker-events.jsonl carries a pause and an unpause event of service consul), none of which changes a verdict; (5) the extra collected service (consul) is reported per channel with the number of valid cells that collected it, `—` when none did (absence is not zero); (6) the declared design (episodes per regime and rate) is reported against the cells found and valid, and consul's possible listing among the never-exposed services is flagged as the exposure rule's; (7) the lanes block is v3.3's, with Hotel's rules: own = the target's sensors, coordinator and lag `—`. Scope: instance (one SUT, one host, one campaign); nothing is a mechanism claim.

### Extra collected service `hotel-offpath-v1:consul`

- valid cells of the epoch: 30; with any sensor of the service: 30 (metric 30); distinct sensors: 7.
- application.log lines of the service: 6543 in 30 cell(s); log sensors: 0.
- **6543 log line(s) of `consul` are in application.log but no Hotel log layout (zerolog JSON, zerolog console, Go log: sensor_rep/parsers/hotel.py, symptoms.HOTEL_LAYOUTS) parsed one: the service has no log sensor, its log channel is a dead channel for this reader**
- v2.4's exposure rule (route services from the no-fault traces) lists `consul` among the never-exposed services although it is the fault target of its own regime: consul has no spans and is on no route, so that listing is the rule's, not a finding.

### Declared design against cells found

| regime, rate | declared | found | valid |
|---|---|---|---|
| consul-pause-effect r10 | 5 | 5 | 5 |
| consul-pause-effect r1 | 5 | 5 | 5 |
| no-fault-calibration r10 | 5 | 5 | 5 |
| no-fault-calibration r1 | 5 | 5 | 5 |
| search-pause-effect r10 | 5 | 5 | 5 |
| search-pause-effect r1 | 5 | 5 | 5 |

### Off-path manifestation record

Rule: off-path: the container read back as paused (fault-receipt duringState.paused, manifested) plus a docker pause event and an unpause event on the target's own container (docker-events.jsonl, service label consul); the route outage (fault-receipt outageObserved) is recorded, not required

| cell | rate | block | manifested | during paused | outage observed (recorded, not required) | docker pause / unpause events | manifested by rule |
|---|---|---|---|---|---|---|---|
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/hotel-offpath-evidence/off2-fetch/x :: runs/effect/consul-pause/r10/b01/p03-full/attempt-01 | 10 | 1 | True | True | False | 1 / 1 | True |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/hotel-offpath-evidence/off2-fetch/x :: runs/effect/consul-pause/r10/b02/p04-full/attempt-01 | 10 | 2 | True | True | False | 1 / 1 | True |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/hotel-offpath-evidence/off2-fetch/x :: runs/effect/consul-pause/r10/b03/p02-full/attempt-01 | 10 | 3 | True | True | False | 1 / 1 | True |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/hotel-offpath-evidence/off2-fetch/x :: runs/effect/consul-pause/r10/b04/p04-full/attempt-01 | 10 | 4 | True | True | False | 1 / 1 | True |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/hotel-offpath-evidence/off2-fetch/x :: runs/effect/consul-pause/r10/b05/p01-full/attempt-01 | 10 | 5 | True | True | False | 1 / 1 | True |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/hotel-offpath-evidence/off2-fetch/x :: runs/effect/consul-pause/r1/b01/p04-full/attempt-01 | 1 | 1 | True | True | False | 1 / 1 | True |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/hotel-offpath-evidence/off2-fetch/x :: runs/effect/consul-pause/r1/b02/p01-full/attempt-01 | 1 | 2 | True | True | False | 1 / 1 | True |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/hotel-offpath-evidence/off2-fetch/x :: runs/effect/consul-pause/r1/b03/p04-full/attempt-01 | 1 | 3 | True | True | False | 1 / 1 | True |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/hotel-offpath-evidence/off2-fetch/x :: runs/effect/consul-pause/r1/b04/p06-full/attempt-01 | 1 | 4 | True | True | False | 1 / 1 | True |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/hotel-offpath-evidence/off2-fetch/x :: runs/effect/consul-pause/r1/b05/p06-full/attempt-01 | 1 | 5 | True | True | False | 1 / 1 | True |


## v3.7 additions (Hotel off-path epoch read as campaign-E; admission only)

Frozen v3.7 (FREEZE_V37_20261015.md). Scope: instance; a report, no mechanism claim.

- Epoch admitted as campaign-E by v3.7: `hotel-offpath-v1`.
- Campaign-E epoch read: `hotel-offpath-v1`.

