# Traffic sweep, TeaStore: analysis v3 (v3.1), exploratory, not frozen (every cell of this system was read under v2.4 before v3 was written) (teastore-offpath-v1)

**Exploratory, not frozen.** Protocol rounds 15 and 17 (decisions 61-65 as amended by 67) on v2.4's readers and rules; every cell read here was read under v2.4 first. **Scope: instance** (one SUT, one host). `—` = absent or not evaluable, never 0. Each (sensor, rule) is calibrated per rate by the zero-held-out-alarm selection; **no false-alarm figure here is that selection's own zero**: every count of false alarms is the honest nested leave-one-cell-out count (V3_NESTED_RULE), with its exact 95 % bound.

Binding documents and inputs: research/PROTOCOL_DRAFT_20261002.md round 15 (decisions 61-65, 252cfcd); research/protocol/ANALYSIS_V3_DESIGN.md (252cfcd); research/traffic-sweep/SYNTHESIS_V2_4.md; research/protocol/parameters_v3.json (decision 37); research/traffic-sweep/DECLARATION_TEASTORE.md (c9f072b); research/traffic-sweep/AMENDMENT_TEASTORE_1.md (bbbd80b); research/traffic-sweep/AMENDMENT_TEASTORE_2.md (b840353); research/traffic-sweep/DECLARATION_QUIET_TEASTORE.md (fc64a6d); research/protocol/METHODOLOGY_HARDENING.md (H1-H11); research/PROTOCOL_DRAFT_20261002.md rounds 7-14 (decisions 26-60; decision 57 = d126589, round 13 = 6162c37, round 14 = c17f6a6); harness observability-placement-runtime-teastore-protocol 91c4967 (the cell writer and validator); research/protocol/parameters.json (decision 37).

Analysis: `research/detection-time/sweep_analysis_v3_6.py` v3 (sha256 `98d7832c4dad50149b53bebf191682dce991877a136e6db548b9c152131df83a`) on v2.4 `sweep_analysis_v2.py` (sha256 `075c43e5870170c8b59cdbe1a970b56dc03920d67514027b9a95e5de38d962e9`), parameters.json `7447b492abf64f42ebaf547a640c84929ac15b59ebc1e495d5082f279373fc68`, parameters_v3.json `212830bec3e6669bc211d5cffa48d61fa3bf0f6d4dd5ceaf79d3e2bcc7c4d000`, HEAD `ea06a506f19c2b74853680174d5372afaf6b4740`, Python 3.13.12.

## Outputs that are — by construction

- family M (primary and secondary columns, operating point, P4 candidates): docker-stats samples (resources.json) are written in no-fault cells only (the frozen no-fault-cost path, DECLARATION_TEASTORE.md Regimes): no fault episode has M, so it is not read (FAMILY_CHANNELS).
- availability-clock P4 verdict for family T: no measured collector receive stamp (AVAILABILITY_SOURCES, decision 43).
- P3 (every fault): no family is traffic-independent by mechanism (H11).
- harness provenance of 18 cell(s): receipt source.frameworkCommit `04254228aba90566dfeca603dfcc7b05b7d8d2e3` is not listed in HARNESS_PROVENANCE (F5): read, flagged.
- P2 and P4 verdicts ('k of 4') at auth-freeze r1 (n = 3), auth-freeze r10 (n = 3), recommender-pause r1 (n = 3), recommender-pause r10 (n = 3): fewer episodes than declared (EPISODES); P4's single-episode comparison is reported where n = 1, descriptive.
- out-of-sample check (decision 65): no --validation cells given (campaign B's no-fault cells are the declared source).
- a false-alarm figure from the zero-alarm selection itself: never printed (decision 67): the selected value has 0 held-out alarms on the cells it was chosen on by construction; every false-alarm count below is the honest nested one.

## What was read

Campaigns pooled (H1; decision 68: quiet runs A and A2 pool with the sweep):

- `tmp/teastore-offpath-evidence/rep3r1-fetch/x/teastore-offpath-v1`: 18 valid of 18 (auth-freeze 6, no-fault-cost 6, recommender-pause 6)

| class | r10 valid/found | r1 valid/found | r0.2 valid/found | r0.05 valid/found |
|---|---|---|---|---|
| no-fault-cost | 3/3 | 3/3 | — | — |
| auth-freeze | 3/3 | 3/3 | — | — |
| persistence-cpu-throttle | — | — | — | — |
| recommender-pause | 3/3 | 3/3 | — | — |

Cells not scored: none.

Provenance: harness commit `04254228aba90566dfeca603dfcc7b05b7d8d2e3`; input digest `7c78b0dfcb4c9f5770ab3613c296869e4ed58294026b50d17f11020307c56b91` over 156 files (v2.4's file set plus docker-events.json[l]).

H4 freeze record per harness and status (V3_FREEZE_EVENTS_RULE; decision 69: a missing or contradictory record keeps the sweep's bound and is counted): B: used 12; reasons: none.

Reader statistics over the valid cells (F11; a drop is counted, never silent): bridgeMappings 16105; bridgeTokensWithSeveralTraces 0; bridgeTracesWithSeveralTokens 0; bridgeRowsDropped 0; tracesWithoutToken 17378; probeTracesExcluded 218; probeSpansExcluded 3386; spansIncomplete 0; spansUnusable 0; duplicateSpans 1240; journeysWithoutStart 0; samplePairsSkipped 0; logRecordsUntimed 0; composeCliLines 0.

## Calibration per (sensor, rule) on the no-fault cells (decisions 61-63, 67)

Each armed (sensor, rule) takes the smallest grid value with zero held-out alarms over the rate's no-fault cells, each scored leave-one-cell-out (v2.4's fit, H1; class-independent). Level rules: K_GRID (<= 100; K = 100 flagged at grid edge), then the range fallback (discrete in effect; up-only for spans and the ledger; may apply where MAD = 0, decision 52 kept for K); `absent`: m x G on m in {1, 1.5, 2, 3, 5}, G including the censored silences of cells with records; an `absent` whose gap exceeds the shortest hold (60.193 s) is **inert**; `appear` per stream; the ledger's `failed` exempt. **honest** = the nested count (each held-out cell at the value re-selected without it), the false-alarm figure; its rate per hour of no-fault time T.

| rate | no-fault cells | T (h) | rules calibrated / dropped / inert / unarmed | at grid edge | range (of them MAD = 0) | sensors placeable / appear-only / not (L, M, S, T) | dof | E `failed` in no-fault (exempt) | calibrated rules: median folds armed of the rate's cells · out of the detector in every nested fold · honest — (no nested evidence) | placeable sensors with CELF cost — |
|---|---|---|---|---|---|---|---|---|---|---|
| r10 | 3 | 0.150 | 594 / 11 / 0 / 454 | 3 | 40 (31) | 60 / 401 / 8 | 193 | login-only-v1 0 | 3 of 3 · 0 · 0 | 6 |
| r1 | 3 | 0.150 | 598 / 7 / 0 / 454 | 0 | 44 (32) | 60 / 401 / 8 | 197 | login-only-v1 0 | 3 of 3 · 0 · 0 | 6 |

Per family and rule (primary): calibrated / dropped / inert / unarmed.

| rate | family | appear | absent | spike | run3 | median |
|---|---|---|---|---|---|---|
| r10 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r10 | L | 398 / 0 / 0 / 0 | 0 / 0 / 0 / 398 | — | — | — |
| r10 | S | — | — | 31 / 9 / 0 / 8 | 40 / 0 / 0 / 8 | 40 / 0 / 0 / 8 |
| r10 | T | 3 / 0 / 0 / 20 | 20 / 0 / 0 / 3 | 18 / 2 / 0 / 3 | 20 / 0 / 0 / 3 | 20 / 0 / 0 / 3 |
| r1 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r1 | L | 398 / 0 / 0 / 0 | 0 / 0 / 0 / 398 | — | — | — |
| r1 | S | — | — | 33 / 7 / 0 / 8 | 40 / 0 / 0 / 8 | 40 / 0 / 0 / 8 |
| r1 | T | 3 / 0 / 0 / 20 | 20 / 0 / 0 / 3 | 20 / 0 / 0 / 3 | 20 / 0 / 0 / 3 | 20 / 0 / 0 / 3 |

**The ledger E** per rate (route; `failed` **exempt**, decision 63: never calibrated, always compared; its no-fault count is reported):

- r10: `absent` calibrated (m 1.5, honest 1); `failed` exempt (no-fault count 0); `median` calibrated (K 3.5, honest 1); `run3` calibrated (K 3, honest 0); `spike` calibrated (K 10, honest 1).
- r1: `absent` calibrated (m 1, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 6.3, honest 3).
- E's catching rule in the episodes (primary): auth-freeze r1: `absent` 3; auth-freeze r10: `absent` 3; recommender-pause r1: `—` 3; recommender-pause r10: `—` 3.

**Dropped (sensor, rule) pairs** (held-out alarms at the last grid value; honest count beside), primary:

- r10 (11): `metric:recommender:sys_io/spike` 4 (honest 3), `span:auth:RandomSessionIdGenerator.getSessionId/spike` 2 (honest 4), `metric:auth:sys_io/spike` 1 (honest 30), `metric:db:sys_psi_cpu/spike` 1 (honest —), `metric:image:sys_psi_io/spike` 1 (honest 1), `metric:persistence:sys_io/spike` 1 (honest 1), `metric:persistence:sys_psi_io/spike` 1 (honest 1), `metric:registry:sys_io/spike` 1 (honest 1), `metric:registry:sys_psi_io/spike` 1 (honest 1), `metric:webui:sys_psi_io/spike` 1 (honest 1), `span:persistence:PersistenceCategory.getId/spike` 1 (honest 1)
- r1 (7): `metric:auth:sys_io/spike` 1 (honest 1), `metric:image:sys_psi_io/spike` 1 (honest 1), `metric:persistence:sys_io/spike` 1 (honest —), `metric:persistence:sys_psi_io/spike` 1 (honest —), `metric:rabbitmq:sys_psi_io/spike` 1 (honest 1), `metric:registry:sys_psi_io/spike` 1 (honest 1), `metric:webui:sys_io/spike` 1 (honest 1)

**Inert** (calibrated by the selection, but the gap exceeds the hold; not placeable), **at grid edge** (K = 100) and **appear-only** sensors (placeable through `appear` alone, listed apart), primary:

- r10: inert 0: none; at grid edge 3: `metric:rabbitmq:sys_cpu/spike`, `metric:rabbitmq:sys_memory/spike`, `span:image:AbstractCache.loadData/spike`; appear-only 401: `log:auth:059f77b5fee4`, `log:auth:0788a45dbb86`, `log:auth:0ae227c4f15d`, `log:auth:13e7be34fb70`, `log:auth:16e888bf8922`, `log:auth:16f327e6bd4d`, `log:auth:2d7f16630b87`, `log:auth:2ff20a342a41`, `log:auth:319b41b82d9b`, `log:auth:3219d9dbbaed`, `log:auth:35563463c928`, `log:auth:35873ee1cc7e`, `log:auth:3917ffeac5ec`, `log:auth:3b1fa69c3451`, `log:auth:3f00555a765d`, `log:auth:407989c51698`, `log:auth:4a79ac521b28`, `log:auth:4de8468724c7`, `log:auth:52a075c95ff9`, `log:auth:56bcc1a07d39`, `log:auth:56c309f6427c`, `log:auth:6c19cf62298a`, `log:auth:6e7a7f83a9e6`, `log:auth:7197cbb5d81b`, `log:auth:72ae3fa150b5`, `log:auth:7568b9fca9ad`, `log:auth:7877eab35e98`, `log:auth:7b327c4594ff`, `log:auth:811e1f658b4b`, `log:auth:8733ab2f4543`, `log:auth:87614f556af3`, `log:auth:8b277994d6dd`, `log:auth:8ddb5025ba7f`, `log:auth:8eb94ac35bf9`, `log:auth:955560e889b3`, `log:auth:96ea0f608ef2`, `log:auth:9c6795a8c551`, `log:auth:a0105883ccdd`, `log:auth:a07c7bcc6c3d`, `log:auth:a59061884c18` (+361 more in the JSON).
- r1: inert 0: none; at grid edge 0: none; appear-only 401: `log:auth:059f77b5fee4`, `log:auth:0788a45dbb86`, `log:auth:0ae227c4f15d`, `log:auth:13e7be34fb70`, `log:auth:16e888bf8922`, `log:auth:16f327e6bd4d`, `log:auth:2d7f16630b87`, `log:auth:2ff20a342a41`, `log:auth:319b41b82d9b`, `log:auth:3219d9dbbaed`, `log:auth:35563463c928`, `log:auth:35873ee1cc7e`, `log:auth:3917ffeac5ec`, `log:auth:3b1fa69c3451`, `log:auth:3f00555a765d`, `log:auth:407989c51698`, `log:auth:4a79ac521b28`, `log:auth:4de8468724c7`, `log:auth:52a075c95ff9`, `log:auth:56bcc1a07d39`, `log:auth:56c309f6427c`, `log:auth:6c19cf62298a`, `log:auth:6e7a7f83a9e6`, `log:auth:7197cbb5d81b`, `log:auth:72ae3fa150b5`, `log:auth:7568b9fca9ad`, `log:auth:7877eab35e98`, `log:auth:7b327c4594ff`, `log:auth:811e1f658b4b`, `log:auth:8733ab2f4543`, `log:auth:87614f556af3`, `log:auth:8b277994d6dd`, `log:auth:8ddb5025ba7f`, `log:auth:8eb94ac35bf9`, `log:auth:955560e889b3`, `log:auth:96ea0f608ef2`, `log:auth:9c6795a8c551`, `log:auth:a0105883ccdd`, `log:auth:a07c7bcc6c3d`, `log:auth:a59061884c18` (+361 more in the JSON).

**Not placeable at this quiet time** (L, M, S, T sensors with no calibrated rule), by family (with a dropped rule / inert / unarmed only), then those with a dropped rule:

- r10: 8 sensors (S 0/0/8); with a dropped rule: none
- r1: 8 sensors (S 0/0/8); with a dropped rule: none

- `appear` (V3_APPEAR_RULE): new streams in no-fault cells per service, summed over the held-out cells (they enter the honest counts): r10 none; r1 none.
- **floor arm (share 0.05)**: r10 594/11/0/454 rules, 60 placeable + 401 appear-only sensors; r1 598/7/0/454 rules, 60 placeable + 401 appear-only sensors.
- **sensitivity, <= 1 held-out alarm (K_GRID only, no range fallback)**: r10 555/14/0/490 rules, 44 placeable + 401 appear-only sensors; r1 554/15/0/490 rules, 44 placeable + 401 appear-only sensors.

## Honest false alarms (decisions 64, 67): nested leave-one-cell-out unions on the no-fault cells

Union of the sensors' rules, each held-out no-fault cell scored at the values re-selected without it (its leave-one-cell-out fit), restarted after each alarm: count (/h [exact 95 % bound]); per family also the sum of its calibrated rules' honest counts (the reviewer's tally). The honest per-sensor rate is the sensor's false-alarm cost for CELF (JSON calibration.*.sensors.*.honestPerHour). Campaign B's fresh check can certify at best 20.0/h (0 alarms in 0.15 h per rate).

| setting | rate | T (h) | E | L | M | S | T | all placeable L, M, S, T |
|---|---|---|---|---|---|---|---|---|
| primary | r10 | 0.150 | 3 (20.0/h [51.7], 0.150 of 0.15 h) · sum 3 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [20.0], 0.150 of 0.15 h) · sum 0 · no evidence: 0 rules, 3 sensors | — | 69 (460.0/h [562.0], 0.150 of 0.15 h) · sum 90 · no evidence: 0 rules, 0 sensors | 401 (2673.3/h [2903.6], 0.150 of 0.15 h) · sum 54 · no evidence: 0 rules, 3 sensors | 660 (4400.0/h [4692.3], 0.15 of 0.15 h) |
| primary | r1 | 0.150 | 3 (20.0/h [51.7], 0.150 of 0.15 h) · sum 3 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [20.0], 0.150 of 0.15 h) · sum 0 · no evidence: 0 rules, 3 sensors | — | 66 (440.0/h [540.1], 0.150 of 0.15 h) · sum 145 · no evidence: 0 rules, 0 sensors | 67 (446.7/h [547.4], 0.150 of 0.15 h) · sum 54 · no evidence: 0 rules, 3 sensors | 151 (1006.7/h [1152.2], 0.15 of 0.15 h) |
| atMostOne | r10 | 0.150 | 6 (40.0/h [78.9], 0.150 of 0.15 h) · sum 6 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [20.0], 0.150 of 0.15 h) · sum 0 · no evidence: 0 rules, 3 sensors | — | 73 (486.7/h [591.3], 0.150 of 0.15 h) · sum 78 · no evidence: 0 rules, 0 sensors | 577 (3846.7/h [4120.7], 0.150 of 0.15 h) · sum 112 · no evidence: 0 rules, 3 sensors | 694 (4626.7/h [4926.2], 0.15 of 0.15 h) |
| atMostOne | r1 | 0.150 | 3 (20.0/h [51.7], 0.150 of 0.15 h) · sum 3 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [20.0], 0.150 of 0.15 h) · sum 0 · no evidence: 0 rules, 3 sensors | — | 72 (480.0/h [584.0], 0.150 of 0.15 h) · sum 125 · no evidence: 0 rules, 0 sensors | 124 (826.7/h [959.6], 0.150 of 0.15 h) · sum 85 · no evidence: 0 rules, 3 sensors | 201 (1340.0/h [1506.2], 0.15 of 0.15 h) |

P4-selected sets (the sensors P4 selected over its folds, or with one episode the candidates judged a win), honest nested union, primary:

- P4a auth-freeze-effect r1: `metric:recommender:sys_io`, `span:webui:LoginActionServlet.handlePOSTRequest` -> 5 (33.3/h [70.1], 0.15 of 0.15 h) · sum over the sensors 5
- P4a auth-freeze-effect r10: `span:webui:LoginActionServlet.handlePOSTRequest` -> 3 (20.0/h [51.7], 0.15 of 0.15 h) · sum over the sensors 3
- P4a recommender-pause-effect r1: `log:webui:d4d75ec135e6`, `span:auth:BCryptProvider.checkPassword` -> 2 (13.3/h [42.0], 0.15 of 0.15 h) · sum over the sensors 2
- P4a recommender-pause-effect r10: `span:auth:BCryptProvider.checkPassword` -> 0 (0.0/h [20.0], 0.15 of 0.15 h) · sum over the sensors 0
- P4b auth-freeze-effect r1: `metric:auth:sys_psi_cpu` -> 2 (13.3/h [42.0], 0.15 of 0.15 h) · sum over the sensors 2
- P4b auth-freeze-effect r10: `metric:auth:sys_psi_cpu` -> 0 (0.0/h [20.0], 0.15 of 0.15 h) · sum over the sensors 0
- P4b recommender-pause-effect r1: `metric:recommender:sys_io` -> 4 (26.7/h [61.0], 0.15 of 0.15 h) · sum over the sensors 4
- P4b recommender-pause-effect r10: `metric:recommender:sys_io` -> 3 (20.0/h [51.7], 0.15 of 0.15 h) · sum over the sensors 3

## v2.4 reference row: family operating point (decision 53, 15/h, from v2.4's own code)

K per family: E —, L —, M —, S —, T —, system —.

| class | family | r10 | r1 | r0.2 | r0.05 |
|---|---|---|---|---|---|
| auth-freeze | E | no | no | — | — |
| auth-freeze | L | no | no | — | — |
| auth-freeze | M | n/c | n/c | — | — |
| auth-freeze | S | no | no | — | — |
| auth-freeze | T | no | no | — | — |
| persistence-cpu-throttle | E | no | no | — | — |
| persistence-cpu-throttle | L | no | no | — | — |
| persistence-cpu-throttle | M | n/c | n/c | — | — |
| persistence-cpu-throttle | S | no | no | — | — |
| persistence-cpu-throttle | T | no | no | — | — |
| recommender-pause | E | no | no | — | — |
| recommender-pause | L | no | no | — | — |
| recommender-pause | M | n/c | n/c | — | — |
| recommender-pause | S | no | no | — | — |
| recommender-pause | T | no | no | — | — |

## Predictions (primary: calibrated arm, floor primary)

- **P1** (auth-freeze; decision 54's interval, observed = first `failed` catch): 6/6; per rate r10 3/3, r1 3/3, r0.2 —, r0.05 —; not evaluable 0; holds by branch: error answer before the timeout (declared alternative) 3, timeout interval 3; verdict **holds**.
- **P2** r10 (failed before the first `failed` catch <= 153.00): 3/3, counts [119, 122, 119], verdict — (n < 4).
- **P2** r1 (failed before the first `failed` catch <= 18.00): 3/3, counts [16, 16, 16], verdict — (n < 4).
- **P2** r0.2 (failed before the first `failed` catch <= 6.00): —.
- **P2** r0.05 (failed before the first `failed` catch <= 3.75): —.
- **P3** auth-freeze: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P3** persistence-cpu-throttle: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P3** recommender-pause: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P4** compares against the ledger E as the OR of its calibrated rules, its `failed` rule exempt from calibration (decisions 63, 70; V3_P4_LEDGER_READING = `calibrated-ledger`): a dropped ledger rule is listed below, not a reason for `—`. Two arms (decision 67): calibrated (primary) and optimistic bound (dropped rules armed at K = 100 / m = 5, beside, not evidence).
- Dropped ledger rules per rate (decision 70: listed; the ledger compares by its calibrated rules): r10 none; r1 none.
- **P4a** auth-freeze (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 0/3 (ledger missed, sensor caught: 0); r1 0/3 (ledger missed, sensor caught: 0); r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/3 (ledger missed, sensor caught: 0); r1 0/3 (ledger missed, sensor caught: 0); r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4a** persistence-cpu-throttle (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 —; r1 —; r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 —; r1 —; r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4a** recommender-pause (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 0/3 (ledger missed, sensor caught: 3); r1 0/3 (ledger missed, sensor caught: 2); r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/3 (ledger missed, sensor caught: 3); r1 0/3 (ledger missed, sensor caught: 2); r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4b** auth-freeze (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 0/3 (ledger missed, sensor caught: 0); r1 0/3 (ledger missed, sensor caught: 0); r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/3 (ledger missed, sensor caught: 0); r1 0/3 (ledger missed, sensor caught: 0); r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4b** persistence-cpu-throttle (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 —; r1 —; r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 —; r1 —; r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.
- **P4b** recommender-pause (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 0/3 (ledger missed, sensor caught: 3); r1 0/3 (ledger missed, sensor caught: 3); r0.2 —; r0.05 —; highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/3 (ledger missed, sensor caught: 3); r1 0/3 (ledger missed, sensor caught: 3); r0.2 —; r0.05 —; highest rate — at {10, 1, 0.2, 0.05}.

### P4 per class and rate: placeable sensors, dropped rules and non-placeable sensors on the affected path

- auth-freeze r10: placeable sensors 461 (candidates with a catch: 10); dropped on the path: `metric:auth:sys_io/spike`, `metric:persistence:sys_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_psi_io/spike`, `span:auth:RandomSessionIdGenerator.getSessionId/spike`, `span:persistence:PersistenceCategory.getId/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- auth-freeze r1: placeable sensors 461 (candidates with a catch: 6); dropped on the path: `metric:auth:sys_io/spike`, `metric:persistence:sys_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_io/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- recommender-pause r10: placeable sensors 461 (candidates with a catch: 5); dropped on the path: `metric:recommender:sys_io/spike`; not placeable on the path: `metric:recommender:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- recommender-pause r1: placeable sensors 461 (candidates with a catch: 5); dropped on the path: none; not placeable on the path: `metric:recommender:sys_psi_memory`; dropped ledger rules (listed, decision 70): none

### P4 folds (sensor rule vs ledger rule; lead, margin; category)

**Calibrated arm**

- P4a auth-freeze r10 (candidates 10; paired differences ledger - sensor: mean -10.252 [-10.372, -10.142] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 10.657 vs E `absent` 0.416; lead -10.241, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 10.734 vs E `absent` 0.362; lead -10.372, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 10.469 vs E `absent` 0.327; lead -10.142, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
- P4a auth-freeze r1 (candidates 6; paired differences ledger - sensor: mean -32.406 [-59.851, -18.409] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.046 vs E `absent` 0.638; lead -18.409, margin 1e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b2: metric:recommender:sys_io `—` — vs E `absent` 0.389; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.848 vs E `absent` 0.890; lead -18.958, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
- P4a recommender-pause r10 (candidates 5; paired differences ledger - sensor: mean 57.176 [51.825, 60.047] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:auth:BCryptProvider.checkPassword `median` 8.395 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep2 b2: span:auth:BCryptProvider.checkPassword `median` 0.551 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: span:auth:BCryptProvider.checkPassword `median` 0.200 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
- P4a recommender-pause r1 (candidates 5; paired differences ledger - sensor: mean 31.447 [0.000, 47.868] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:auth:BCryptProvider.checkPassword `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b2: log:webui:d4d75ec135e6 `appear` 13.745 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: log:webui:d4d75ec135e6 `appear` 12.370 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
- P4b auth-freeze r10 (candidates 1; paired differences ledger - sensor: mean -14.515 [-14.593, -14.473] s; availability-clock wins 0 of 3 evaluable):
  - ep1 b1: metric:auth:sys_psi_cpu `run3` 14.889 vs E `absent` 0.416; lead -14.473, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b2: metric:auth:sys_psi_cpu `run3` 14.841 vs E `absent` 0.362; lead -14.480, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b3: metric:auth:sys_psi_cpu `run3` 14.920 vs E `absent` 0.327; lead -14.593, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
- P4b auth-freeze r1 (candidates 1; paired differences ledger - sensor: mean -13.884 [-13.893, -13.875] s; availability-clock wins 0 of 3 evaluable):
  - ep1 b1: metric:auth:sys_psi_cpu `run3` 14.523 vs E `absent` 0.638; lead -13.885, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b2: metric:auth:sys_psi_cpu `median` 14.264 vs E `absent` 0.389; lead -13.875, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b3: metric:auth:sys_psi_cpu `run3` 14.783 vs E `absent` 0.890; lead -13.893, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
- P4b recommender-pause r10 (candidates 1; paired differences ledger - sensor: mean 45.359 [45.341, 45.372] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:recommender:sys_io `median` 14.879 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep2 b2: metric:recommender:sys_io `median` 14.836 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: metric:recommender:sys_io `median` 14.885 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
- P4b recommender-pause r1 (candidates 1; paired differences ledger - sensor: mean 45.775 [45.512, 46.055] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:recommender:sys_io `median` 14.469 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep2 b2: metric:recommender:sys_io `median` 14.163 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: metric:recommender:sys_io `median` 14.726 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**

**Optimistic bound (not evidence)**

- P4a auth-freeze r10 (candidates 11; paired differences ledger - sensor: mean -10.252 [-10.372, -10.142] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 10.657 vs E `absent` 0.416; lead -10.241, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 10.734 vs E `absent` 0.362; lead -10.372, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 10.469 vs E `absent` 0.327; lead -10.142, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
- P4a auth-freeze r1 (candidates 8; paired differences ledger - sensor: mean -35.876 [-59.851, -23.884] s; availability-clock wins 0 of 2 evaluable):
  - ep1 b1: metric:webui:sys_io `spike` 24.522 vs E `absent` 0.638; lead -23.884, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b2: metric:recommender:sys_io `—` — vs E `absent` 0.389; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b3: metric:webui:sys_io `spike` 24.783 vs E `absent` 0.890; lead -23.893, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
- P4a recommender-pause r10 (candidates 5; paired differences ledger - sensor: mean 57.176 [51.825, 60.047] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:auth:BCryptProvider.checkPassword `median` 8.395 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep2 b2: span:auth:BCryptProvider.checkPassword `median` 0.551 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: span:auth:BCryptProvider.checkPassword `median` 0.200 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
- P4a recommender-pause r1 (candidates 5; paired differences ledger - sensor: mean 31.447 [0.000, 47.868] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:auth:BCryptProvider.checkPassword `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b2: log:webui:d4d75ec135e6 `appear` 13.745 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: log:webui:d4d75ec135e6 `appear` 12.370 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
- P4b auth-freeze r10 (candidates 2; paired differences ledger - sensor: mean -7.852 [-9.481, -4.596] s; availability-clock wins 0 of 3 evaluable):
  - ep1 b1: metric:auth:sys_io `spike` 9.897 vs E `absent` 0.416; lead -9.481, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b2: metric:auth:sys_io `spike` 9.839 vs E `absent` 0.362; lead -9.477, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b3: metric:auth:sys_io `spike` 4.923 vs E `absent` 0.327; lead -4.596, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
- P4b auth-freeze r1 (candidates 2; paired differences ledger - sensor: mean -8.885 [-8.889, -8.882] s; availability-clock wins 0 of 3 evaluable):
  - ep1 b1: metric:auth:sys_io `spike` 9.520 vs E `absent` 0.638; lead -8.882, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b2: metric:auth:sys_io `spike` 9.273 vs E `absent` 0.389; lead -8.883, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b3: metric:auth:sys_io `spike` 9.779 vs E `absent` 0.890; lead -8.889, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
- P4b recommender-pause r10 (candidates 1; paired differences ledger - sensor: mean 50.359 [50.348, 50.371] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:recommender:sys_io `spike` 9.872 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep2 b2: metric:recommender:sys_io `spike` 9.838 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: metric:recommender:sys_io `spike` 9.888 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
- P4b recommender-pause r1 (candidates 1; paired differences ledger - sensor: mean 45.775 [45.512, 46.055] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:recommender:sys_io `median` 14.469 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep2 b2: metric:recommender:sys_io `median` 14.163 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: metric:recommender:sys_io `median` 14.726 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**

**Per harness** (decision 49 pools the sweep's episode with campaign B's three; V3_HARNESS_TAG_RULE; tags B). Episodes per class and rate: auth-freeze r1 B 3; auth-freeze r10 B 3; recommender-pause r1 B 3; recommender-pause r10 B 3.

- P1 holds per harness: B 6/6; P2 within the bound per harness: r10 B 3/3; r1 B 3/3.
- P4 optimistic P4a auth-freeze r1: wins / folds by the held-out episode's harness: B 0/3
- P4 optimistic P4a auth-freeze r10: wins / folds by the held-out episode's harness: B 0/3
- P4 optimistic P4a recommender-pause r1: wins / folds by the held-out episode's harness: B 0/3
- P4 optimistic P4a recommender-pause r10: wins / folds by the held-out episode's harness: B 0/3
- P4 optimistic P4b auth-freeze r1: wins / folds by the held-out episode's harness: B 0/3
- P4 optimistic P4b auth-freeze r10: wins / folds by the held-out episode's harness: B 0/3
- P4 optimistic P4b recommender-pause r1: wins / folds by the held-out episode's harness: B 0/3
- P4 optimistic P4b recommender-pause r10: wins / folds by the held-out episode's harness: B 0/3
- P4 primary P4a auth-freeze r1: wins / folds by the held-out episode's harness: B 0/3
- P4 primary P4a auth-freeze r10: wins / folds by the held-out episode's harness: B 0/3
- P4 primary P4a recommender-pause r1: wins / folds by the held-out episode's harness: B 0/3
- P4 primary P4a recommender-pause r10: wins / folds by the held-out episode's harness: B 0/3
- P4 primary P4b auth-freeze r1: wins / folds by the held-out episode's harness: B 0/3
- P4 primary P4b auth-freeze r10: wins / folds by the held-out episode's harness: B 0/3
- P4 primary P4b recommender-pause r1: wins / folds by the held-out episode's harness: B 0/3
- P4 primary P4b recommender-pause r10: wins / folds by the held-out episode's harness: B 0/3

**Beside the primary** (highest rate where P4 holds):

| verdict | calibrated (primary) | floor arm | <= 1 held-out alarm | optimistic bound (not evidence) |
|---|---|---|---|---|
| P4a auth-freeze | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a persistence-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a recommender-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b auth-freeze | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b persistence-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b recommender-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC auth-freeze | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC persistence-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC recommender-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC auth-freeze | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC persistence-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC recommender-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |

## Out-of-sample check (decision 65, 67): calibrated detectors on --validation no-fault cells, no refit

Not computed (no --validation cells given; campaign B's no-fault cells are the declared source; at 0.15 h per rate they can certify at best 20.0/h).

## Primary outcome: time to detection at the calibrated values, misses charged at the hold end

Detected k/n · median [min-max] · **mean over all n** (with BC catches), then without BC. `—` = channel missing.

| class | rate | n | E | E no BC | L | L no BC | M | M no BC | S | S no BC | T | T no BC | L:own | L:own no BC | M:own | M:own no BC | S:own | S:own no BC | T:own | T:own no BC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| auth-freeze | 10 | 3 | 3/3 · 0.36 [0.33–0.42] · **0.37** | (= E) | 3/3 · 10.24 [10.06–10.89] · **10.40** | 3/3 · 16.75 [16.58–16.82] · **16.72** | — | — | 3/3 · 14.89 [14.84–14.92] · **14.88** | 3/3 · 14.89 [14.84–14.92] · **14.88** | 3/3 · 0.25 [0.23–0.28] · **0.25** | 3/3 · 10.66 [10.47–10.73] · **10.62** | 0/3 · **60.22** | 0/3 · **60.22** | — | — | 3/3 · 4.89 [4.84–4.92] · **4.88** | 3/3 · 14.89 [14.84–14.92] · **14.88** | 3/3 · 0.22 [0.21–0.28] · **0.24** | 0/3 · **60.22** |
| auth-freeze | 1 | 3 | 3/3 · 0.64 [0.39–0.89] · **0.64** | (= E) | 3/3 · 9.95 [8.17–11.84] · **9.99** | 3/3 · 28.85 [26.55–32.04] · **29.15** | — | — | 3/3 · 14.52 [14.26–14.78] · **14.52** | 3/3 · 14.78 [14.52–24.27] · **17.86** | 3/3 · 0.57 [0.32–0.82] · **0.57** | 3/3 · 19.05 [19.03–19.85] · **19.31** | 0/3 · **60.23** | 0/3 · **60.23** | — | — | 3/3 · 14.52 [14.26–14.78] · **14.52** | 3/3 · 14.52 [14.26–14.78] · **14.52** | 3/3 · 0.56 [0.31–0.81] · **0.56** | 0/3 · **60.23** |
| auth-freeze | 0.2 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| auth-freeze | 0.05 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| persistence-cpu-throttle | 10 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| persistence-cpu-throttle | 1 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| persistence-cpu-throttle | 0.2 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| persistence-cpu-throttle | 0.05 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| recommender-pause | 10 | 3 | 0/3 · **60.23** | (= E) | 3/3 · 10.72 [9.88–10.91] · **10.51** | 3/3 · 12.18 [11.62–12.36] · **12.05** | — | — | 0/3 · **60.23** | 0/3 · **60.23** | 3/3 · 0.33 [0.20–8.40] · **2.98** | 3/3 · 0.33 [0.20–8.40] · **2.98** | 0/3 · **60.23** | 0/3 · **60.23** | — | — | 3/3 · 14.88 [14.84–14.88] · **14.87** | 3/3 · 14.88 [14.84–14.88] · **14.87** | 0/3 · **60.23** | 0/3 · **60.23** |
| recommender-pause | 1 | 3 | 0/3 · **60.23** | (= E) | 3/3 · 11.13 [9.38–12.13] · **10.88** | 3/3 · 12.37 [10.44–13.74] · **12.18** | — | — | 2/3 · 14.32 [14.16–14.47] · **29.62** | 2/3 · 14.32 [14.16–14.47] · **29.62** | 2/3 · 2.97 [1.19–4.75] · **22.05** | 2/3 · 2.97 [1.19–4.75] · **22.05** | 0/3 · **60.23** | 0/3 · **60.23** | — | — | 3/3 · 14.47 [14.16–14.73] · **14.45** | 3/3 · 14.47 [14.16–14.73] · **14.45** | 0/3 · **60.23** | 0/3 · **60.23** |
| recommender-pause | 0.2 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| recommender-pause | 0.05 | 0 | — | (= E) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |

## P1 detail (H4, decision 54)

- r10 b1: interval 0.178 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [14.982, 15.182] +- 0.042 s; observed 12.003; holds via **error answer before the timeout (declared alternative)**
- r10 b2: interval 0.139 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.032, 15.132] +- 0.044 s; observed 12.306; holds via **error answer before the timeout (declared alternative)**
- r10 b3: interval 0.128 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.009, 15.108] +- 0.045 s; observed 11.988; holds via **error answer before the timeout (declared alternative)**
- r1 b1: interval 0.155 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.513, 15.513] +- 0.046 s; observed 15.528; holds via **timeout interval**
- r1 b2: interval 0.165 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.259, 15.259] +- 0.053 s; observed 15.276; holds via **timeout interval**
- r1 b3: interval 0.151 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.769, 15.769] +- 0.044 s; observed 15.786; holds via **timeout interval**

- The ledger's calibrated `absent` against the client timeout: r10 login-only-v1: calibrated m 1.5 g 0.280 s vs timeout 15 s; `absent` before the first `failed` in 3/6 pause episodes; r1 login-only-v1: calibrated m 1 g 1.080 s vs timeout 15 s; `absent` before the first `failed` in 3/6 pause episodes.

## Exposure (H5): recorded, the objective unchanged

Route call path: auth, persistence, webui. Episodes with no request started in the fault window: 0 of 12. Never-exposed sensors: 265.

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
- Known limitation (parameters_v3.json V3_KNOWN_LIMITATIONS): L-H4 (DECLARATION_B_TEASTORE_DRAFT.md; coordinator 2026-10-09): the sweep's TeaStore fault cell has no H4 record (its onset interval is [command issued, command returned]), B's have the Docker pause event; the sweep already probed only after the revert, so H10 changes nothing there. The four pooled episodes per (fault, rate) come from two harnesses (sweep 1, B 3); the per-harness breakdown is printed beside every pooled verdict.
- Known limitation F7 (v2.4, registry KNOWN_LIMITATIONS): TeaStore fixture cells are written by the harness's test writer (tests/test_teastore_traffic_sweep.py make_sweep_run), which writes resources.json in every cell; the producer writes it in no-fault cells only (modules/teastore/execution/performance_campaign.py:1690-1693). The reader never reads M on TeaStore (FAMILY_CHANNELS), so the fixture difference is untested, not a reader path.
- Known limitation F9 (v2.4, registry KNOWN_LIMITATIONS): TeaStore S samples are placed on the wall clock through the producer's barrier pair (CLOCK_RULE_TEASTORE), not the ledger fit; the P4 margin of an S-vs-ledger lead omits that mapping term, which P1's tolerance includes (receipt-alignment residual). Immaterial at a 5 s cadence; recorded.
- Known limitation F10 (v2.4, registry KNOWN_LIMITATIONS): OTel cell validity is the target-side receipt.json state (it folds in F1/G1/G2/G4, trace completeness and container health); the coordinator-side terminal replay (candidate_terminal.validate_campaign, remote-terminal.json) is not read. TeaStore reads the validator's candidate-validation.json.
- Known limitation F11 (v2.4, registry KNOWN_LIMITATIONS): The harness refuses a cell when one token maps to several Kieker traces, and (woven entry point) when one trace maps to several tokens (modules/teastore/witness/extract_native_token_correlation.py:449-467); the reader drops such bridge rows instead and counts them (readout: reader statistics, bridgeTokensWithSeveralTraces / bridgeTracesWithSeveralTokens). On harness-validated cells both counts are expected 0.
- Known limitation G4 (v2.4, registry KNOWN_LIMITATIONS): OTel: productcatalogservice logs through logrus's default TextFormatter (upstream src/productcatalogservice/main.go:57, not JSON) and frontend writes plain console output, so neither carries an app stamp the reader parses (JSON_LOG_STAMP_RULE notParsed): their L leads read "log lead not counted (no app stamp)" and their lines do not enter LOG_RECEIPT_RULE's bound. Recorded, not fixed (a logfmt reader would be a new layout).
- Not frozen: v3.1 (decision 67) is built; its freeze and review come before campaign B is read.

## v3.2 additions (campaign E)

Frozen v3.2 (FREEZE_V32_20261013.md); harness names pinned at 6a5c2a9 (V32_EPOCH_PROFILES, V32_LEDGER_SCHEMAS).

- Epochs read: `teastore-offpath-v1` 18. Admitted explicitly: `teastore-offpath-v1`.
- Ledger routes: `login-only-v1`.
- Ledger rule: The ledger sensor E fires on any route: every route has its own ledger streams (`ledger:<entry>:<route>`: the `failed` rule exempt, `spike`/`run3`/`median` on the route's ok latencies, `absent` on the route's completions), each calibrated per (sensor, rule) at the rate by v3.1's criterion (zero held-out alarms, honest nested counts) with the route's own baseline; E's detection time in an episode is the earliest counted fire over all routes and rules (v2.4 col_fire / celf_v3 build_table: min over the family). A route with no baseline in a cell has no latency verdict (listed, ledgerRoutesWithoutBaseline). E's false alarms are the union of the routes' alarms (counted per route and rule in the calibration). The route key is the ledger row's `route` field.
- Block selection: [1, 2, 3]; excluded by the split: 12 cell(s); split file sha256 107cb13aeb52e009754744b136f33b63af69c67d9a2b50e8d9bce14a0e719844.
- Off-path classes scored like the others: `recommender-pause-effect` (recommender).
- Declared call-graph edges not observed in the no-fault traces: []; observed edges not declared: [].


## v3.3 additions (campaign F, TeaStore off-path epoch; admission and lanes)

Frozen v3.3 (FREEZE_V33_20261014.md); harness names pinned at 715d57b (OTel F) and f74b29b (teastore-offpath-v1). Scope: instance; a report, no mechanism claim.

- Epochs added by v3.3: `teastore-offpath-v1`.
- TeaStore pause regimes (explicit targets): {'recommender-pause-effect': 'recommender', 'auth-freeze-effect': 'auth'}; P1 and P2 declared for `auth-freeze-effect`.
- Lane rule: Per regime (and per rate), for every fault episode, the earliest COUNTED fire of each lane: (a) own = sensors of the episode's target (excluded from the placement by decisions 84/111; this is a separate report row, the exclusion is unchanged), (b) coordinator = log ids of the system's coordinator service, (c) lag = consumer-group lag metric ids. A lane's cell reads `—` (JSON null) when no sensor of the lane was collected in the cell (`collectedSensors` 0) and 0 fires when sensors were collected and none fired; the summary counts episodes with a fire over episodes with collected sensors, never over all episodes. Beside the counted fire, each lane carries the earliest fire dropped ONLY by a BC flag (`earliestByConstruction`, with `bcFlags`, label 'by construction, not counted'); counting, placement and the pass rule are unchanged. The time is the fire's `ttd` in seconds after the onset command, the readout's conservative time (a whole-second log stamp is timed at the end of its second, detection_time.log_ttd); `ttdLo` is the lower end. Scope: instance (one SUT, one host, one campaign); nothing is a mechanism claim.

### Lanes, `auth-freeze-effect` (target `auth`)

| rate | lane | episodes with collected sensors | with a counted fire | earliest counted fire, median [min, max] | with a by-construction fire (by construction, not counted) | earliest by-construction fire, median [min, max] |
|---|---|---|---|---|---|---|
| 10 | own | 3 of 3 | 3 of 3 | 14.9 s [14.8 s, 14.9 s] | 3 of 3 | 0.2 s [0.2 s, 0.3 s] |
| 10 | coordinator | 3 of 3 | 0 of 3 | — [—, —] | 3 of 3 | 10.2 s [10.1 s, 10.9 s] |
| 10 | lag | — | — | — (no lag lane is declared for this system) | — | — |
| 1 | own | 3 of 3 | 3 of 3 | 14.5 s [14.3 s, 14.8 s] | 3 of 3 | 0.6 s [0.3 s, 0.8 s] |
| 1 | coordinator | 3 of 3 | 0 of 3 | — [—, —] | 3 of 3 | 9.9 s [8.2 s, 11.8 s] |
| 1 | lag | — | — | — (no lag lane is declared for this system) | — | — |

### Lanes, `recommender-pause-effect` (target `recommender`)

| rate | lane | episodes with collected sensors | with a counted fire | earliest counted fire, median [min, max] | with a by-construction fire (by construction, not counted) | earliest by-construction fire, median [min, max] |
|---|---|---|---|---|---|---|
| 10 | own | 3 of 3 | 3 of 3 | 14.9 s [14.8 s, 14.9 s] | 0 of 3 | — [—, —] |
| 10 | coordinator | 3 of 3 | 0 of 3 | — [—, —] | 3 of 3 | 10.7 s [9.9 s, 10.9 s] |
| 10 | lag | — | — | — (no lag lane is declared for this system) | — | — |
| 1 | own | 3 of 3 | 3 of 3 | 14.5 s [14.2 s, 14.7 s] | 0 of 3 | — [—, —] |
| 1 | coordinator | 3 of 3 | 0 of 3 | — [—, —] | 3 of 3 | 11.1 s [9.4 s, 12.1 s] |
| 1 | lag | — | — | — (no lag lane is declared for this system) | — | — |


## v3.6 additions (TeaStore off-path epoch read as campaign-E; admission only)

Frozen v3.6 (FREEZE_V36_20261015.md). Scope: instance; a report, no mechanism claim.

- Epoch re-admitted as campaign-E by v3.6: `teastore-offpath-v1`.
- Campaign-E epoch read: `teastore-offpath-v1`.

