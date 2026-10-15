# Traffic sweep, TeaStore: analysis v3 (v3.1), exploratory, not frozen (every cell of this system was read under v2.4 before v3 was written) (teastore-traffic-sweep-v1 + teastore-traffic-sweep-b-v1 + teastore-quiet-calibration-v1)

**Exploratory, not frozen.** Protocol rounds 15 and 17 (decisions 61-65 as amended by 67) on v2.4's readers and rules; every cell read here was read under v2.4 first. **Scope: instance** (one SUT, one host). `—` = absent or not evaluable, never 0. Each (sensor, rule) is calibrated per rate by the zero-held-out-alarm selection; **no false-alarm figure here is that selection's own zero**: every count of false alarms is the honest nested leave-one-cell-out count (V3_NESTED_RULE), with its exact 95 % bound.

Binding documents and inputs: research/PROTOCOL_DRAFT_20261002.md round 15 (decisions 61-65, 252cfcd); research/protocol/ANALYSIS_V3_DESIGN.md (252cfcd); research/traffic-sweep/SYNTHESIS_V2_4.md; research/protocol/parameters_v3.json (decision 37); research/traffic-sweep/DECLARATION_TEASTORE.md (c9f072b); research/traffic-sweep/AMENDMENT_TEASTORE_1.md (bbbd80b); research/traffic-sweep/AMENDMENT_TEASTORE_2.md (b840353); research/traffic-sweep/DECLARATION_QUIET_TEASTORE.md (fc64a6d); research/protocol/METHODOLOGY_HARDENING.md (H1-H11); research/PROTOCOL_DRAFT_20261002.md rounds 7-14 (decisions 26-60; decision 57 = d126589, round 13 = 6162c37, round 14 = c17f6a6); harness observability-placement-runtime-teastore-protocol 91c4967 (the cell writer and validator); research/protocol/parameters.json (decision 37).

Analysis: `research/detection-time/sweep_analysis_v3.py` v3 (sha256 `2e7ec5c387fa906a02026f0d1a5212b974f17751c24f76526a1d8418b2fd4fdd`) on v2.4 `sweep_analysis_v2.py` (sha256 `075c43e5870170c8b59cdbe1a970b56dc03920d67514027b9a95e5de38d962e9`), parameters.json `7447b492abf64f42ebaf547a640c84929ac15b59ebc1e495d5082f279373fc68`, parameters_v3.json `f6257b78fedfdcab9577f37cdba77a6fc6d785e4b0b34641cb18de6bb21ade9a`, HEAD `48829ff2ed17165a9586b1b84a55cfb8664d78a2`, Python 3.13.12.

## Outputs that are — by construction

- family M (primary and secondary columns, operating point, P4 candidates): docker-stats samples (resources.json) are written in no-fault cells only (the frozen no-fault-cost path, DECLARATION_TEASTORE.md Regimes): no fault episode has M, so it is not read (FAMILY_CHANNELS).
- availability-clock P4 verdict for family T: no measured collector receive stamp (AVAILABILITY_SOURCES, decision 43).
- P3 (every fault): no family is traffic-independent by mechanism (H11).
- harness provenance of 24 cell(s): receipt source.frameworkCommit `bbb6b1165410be5bd4eb304b56c4eac9490310d1` is not listed in HARNESS_PROVENANCE (F5): read, flagged.
- Docker pause event as the onset interval's upper bound (H4) in 4 of 16 pause episodes: those cells carry no freeze-event source (V3_FREEZE_EVENTS_RULE): the interval is [command issued, command returned], v2.4's.
- a false-alarm figure from the zero-alarm selection itself: never printed (decision 67): the selected value has 0 held-out alarms on the cells it was chosen on by construction; every false-alarm count below is the honest nested one.

## What was read

Campaigns pooled (H1; decision 68: quiet runs A and A2 pool with the sweep):

- `tmp/teastoresweep2-evidence/x/teastore-traffic-sweep-v1`: 12 valid of 12 (auth-freeze 4, no-fault-cost 4, persistence-cpu-throttle 4)
- `tmp/teastoreb1-evidence/faultview/x/teastore-traffic-sweep-b-v1`: 24 valid of 24 (auth-freeze 12, persistence-cpu-throttle 12)
- `tmp/teastorequiet1-evidence/x/teastore-quiet-calibration-v1`: 40 valid of 40 (no-fault-cost 40)

| class | r10 valid/found | r1 valid/found | r0.2 valid/found | r0.05 valid/found |
|---|---|---|---|---|
| no-fault-cost | 11/11 | 11/11 | 11/11 | 11/11 |
| auth-freeze | 4/4 | 4/4 | 4/4 | 4/4 |
| persistence-cpu-throttle | 4/4 | 4/4 | 4/4 | 4/4 |

Cells not scored: none.

Provenance: harness commit `0588a412ea7355f0aaa143b5468e8c4b9b7f0943, 91c4967f2d9c12a25eeeaf097f998856c377ca7f, bbb6b1165410be5bd4eb304b56c4eac9490310d1`; input digest `dacc89f6c491f57149849e6eeac3038077876ba15cff8ec3bd28f3b15d3dc6f8` over 640 files (v2.4's file set plus docker-events.json[l]).

H4 freeze record per harness and status (V3_FREEZE_EVENTS_RULE; decision 69: a missing or contradictory record keeps the sweep's bound and is counted): B: recorded (throttle: command and readback stamps; v2.4's bound kept) 12, used 12; sweep: not recorded (sweep harness) 8; reasons: none.

Reader statistics over the valid cells (F11; a drop is counted, never silent): bridgeMappings 36149; bridgeTokensWithSeveralTraces 0; bridgeTracesWithSeveralTokens 0; bridgeRowsDropped 0; tracesWithoutToken 37084; probeTracesExcluded 692; probeSpansExcluded 11111; spansIncomplete 0; spansUnusable 0; duplicateSpans 27870; journeysWithoutStart 0; samplePairsSkipped 0; logRecordsUntimed 0; composeCliLines 0.

## Calibration per (sensor, rule) on the no-fault cells (decisions 61-63, 67)

Each armed (sensor, rule) takes the smallest grid value with zero held-out alarms over the rate's no-fault cells, each scored leave-one-cell-out (v2.4's fit, H1; class-independent). Level rules: K_GRID (<= 100; K = 100 flagged at grid edge), then the range fallback (discrete in effect; up-only for spans and the ledger; may apply where MAD = 0, decision 52 kept for K); `absent`: m x G on m in {1, 1.5, 2, 3, 5}, G including the censored silences of cells with records; an `absent` whose gap exceeds the shortest hold (60.097 s) is **inert**; `appear` per stream; the ledger's `failed` exempt. **honest** = the nested count (each held-out cell at the value re-selected without it), the false-alarm figure; its rate per hour of no-fault time T.

| rate | no-fault cells | T (h) | rules calibrated / dropped / inert / unarmed | at grid edge | range (of them MAD = 0) | sensors placeable / appear-only / not (L, M, S, T) | dof | E `failed` in no-fault (exempt) | calibrated rules: median folds armed of the rate's cells · out of the detector in every nested fold · honest — (no nested evidence) | placeable sensors with CELF cost — |
|---|---|---|---|---|---|---|---|---|---|---|
| r10 | 11 | 0.550 | 588 / 20 / 0 / 460 | 1 | 38 (28) | 60 / 404 / 8 | 184 | login-only-v1 0 | 11 of 11 · 0 · 0 | 11 |
| r1 | 11 | 0.550 | 600 / 7 / 0 / 459 | 0 | 43 (30) | 60 / 403 / 8 | 197 | login-only-v1 0 | 11 of 11 · 0 · 0 | 8 |
| r0.2 | 11 | 0.550 | 593 / 12 / 0 / 454 | 0 | 38 (30) | 60 / 401 / 8 | 192 | login-only-v1 0 | 11 of 11 · 0 · 0 | 8 |
| r0.05 | 11 | 0.550 | 593 / 12 / 0 / 454 | 0 | 36 (29) | 60 / 401 / 8 | 192 | login-only-v1 0 | 11 of 11 · 0 · 0 | 6 |

Per family and rule (primary): calibrated / dropped / inert / unarmed.

| rate | family | appear | absent | spike | run3 | median |
|---|---|---|---|---|---|---|
| r10 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r10 | L | 400 / 0 / 0 / 0 | 0 / 0 / 0 / 400 | — | — | — |
| r10 | S | — | — | 30 / 10 / 0 / 8 | 40 / 0 / 0 / 8 | 40 / 0 / 0 / 8 |
| r10 | T | 4 / 0 / 0 / 20 | 20 / 0 / 0 / 4 | 10 / 10 / 0 / 4 | 20 / 0 / 0 / 4 | 20 / 0 / 0 / 4 |
| r1 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r1 | L | 399 / 0 / 0 / 0 | 0 / 0 / 0 / 399 | — | — | — |
| r1 | S | — | — | 34 / 6 / 0 / 8 | 40 / 0 / 0 / 8 | 40 / 0 / 0 / 8 |
| r1 | T | 4 / 0 / 0 / 20 | 20 / 0 / 0 / 4 | 19 / 1 / 0 / 4 | 20 / 0 / 0 / 4 | 20 / 0 / 0 / 4 |
| r0.2 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r0.2 | L | 398 / 0 / 0 / 0 | 0 / 0 / 0 / 398 | — | — | — |
| r0.2 | S | — | — | 30 / 10 / 0 / 8 | 40 / 0 / 0 / 8 | 40 / 0 / 0 / 8 |
| r0.2 | T | 3 / 0 / 0 / 20 | 20 / 0 / 0 / 3 | 18 / 2 / 0 / 3 | 20 / 0 / 0 / 3 | 20 / 0 / 0 / 3 |
| r0.05 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r0.05 | L | 398 / 0 / 0 / 0 | 0 / 0 / 0 / 398 | — | — | — |
| r0.05 | S | — | — | 29 / 11 / 0 / 8 | 40 / 0 / 0 / 8 | 40 / 0 / 0 / 8 |
| r0.05 | T | 3 / 0 / 0 / 20 | 20 / 0 / 0 / 3 | 19 / 1 / 0 / 3 | 20 / 0 / 0 / 3 | 20 / 0 / 0 / 3 |

**The ledger E** per rate (route; `failed` **exempt**, decision 63: never calibrated, always compared; its no-fault count is reported):

- r10: `absent` calibrated (m 1.5, honest 1); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 16, honest 1).
- r1: `absent` calibrated (m 1.5, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 10, honest 1).
- r0.2: `absent` calibrated (m 1, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 2.5, honest 0).
- r0.05: `absent` calibrated (m 1, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 2.5, honest 0).
- E's catching rule in the episodes (primary): auth-freeze r0.05: `absent` 4; auth-freeze r0.2: `absent` 4; auth-freeze r1: `absent` 4; auth-freeze r10: `absent` 4; persistence-cpu-throttle r0.05: `absent` 3, `spike` 1; persistence-cpu-throttle r0.2: `absent` 3, `spike` 1; persistence-cpu-throttle r1: `median` 2, `spike` 2; persistence-cpu-throttle r10: `median` 3, `run3` 1.

**Dropped (sensor, rule) pairs** (held-out alarms at the last grid value; honest count beside), primary:

- r10 (20): `metric:auth:sys_psi_io/spike` 2 (honest —), `metric:db:sys_psi_cpu/spike` 1 (honest —), `metric:image:sys_io/spike` 1 (honest 1), `metric:image:sys_psi_io/spike` 1 (honest —), `metric:persistence:sys_psi_io/spike` 1 (honest —), `metric:rabbitmq:sys_psi_io/spike` 1 (honest 1), `metric:recommender:sys_io/spike` 1 (honest 1), `metric:registry:sys_psi_io/spike` 1 (honest —), `metric:webui:sys_io/spike` 1 (honest 1), `metric:webui:sys_psi_io/spike` 1 (honest —), `span:auth:RandomSessionIdGenerator.getSessionId/spike` 1 (honest —), `span:auth:ShaSecurityProvider.blobToString/spike` 1 (honest 1), `span:auth:ShaSecurityProvider.getKeyProvider/spike` 1 (honest —), `span:auth:ShaSecurityProvider.getSha512/spike` 1 (honest —), `span:auth:ShaSecurityProvider.secure/spike` 1 (honest 1), `span:image:AbstractCache.getEntries/spike` 1 (honest —), `span:image:AbstractCache.loadData/spike` 1 (honest 1), `span:image:ImageProvider.getImageFor/spike` 1 (honest 1), `span:persistence:PersistenceCategory.getId/spike` 1 (honest —), `span:persistence:PersistenceUser.getId/spike` 1 (honest —)
- r1 (7): `metric:auth:sys_psi_io/spike` 1 (honest —), `metric:image:sys_psi_io/spike` 1 (honest —), `metric:persistence:sys_psi_io/spike` 1 (honest —), `metric:rabbitmq:sys_io/spike` 1 (honest —), `metric:rabbitmq:sys_psi_io/spike` 1 (honest —), `metric:registry:sys_psi_io/spike` 1 (honest —), `span:persistence:PersistenceCategory.getId/spike` 1 (honest —)
- r0.2 (12): `metric:auth:sys_io/spike` 1 (honest —), `metric:image:sys_io/spike` 1 (honest —), `metric:image:sys_psi_io/spike` 1 (honest —), `metric:persistence:sys_io/spike` 1 (honest 1), `metric:persistence:sys_psi_io/spike` 1 (honest —), `metric:rabbitmq:sys_psi_io/spike` 1 (honest —), `metric:recommender:sys_io/spike` 1 (honest —), `metric:recommender:sys_psi_io/spike` 1 (honest 1), `metric:registry:sys_psi_io/spike` 1 (honest —), `metric:webui:sys_io/spike` 1 (honest 1), `span:auth:ShaSecurityProvider.getKeyProvider/spike` 1 (honest 1), `span:persistence:PersistenceCategory.getId/spike` 1 (honest —)
- r0.05 (12): `metric:auth:sys_io/spike` 1 (honest —), `metric:auth:sys_psi_io/spike` 1 (honest —), `metric:image:sys_io/spike` 1 (honest —), `metric:image:sys_psi_io/spike` 1 (honest 1), `metric:persistence:sys_io/spike` 1 (honest —), `metric:persistence:sys_psi_io/spike` 1 (honest —), `metric:rabbitmq:sys_io/spike` 1 (honest 1), `metric:recommender:sys_io/spike` 1 (honest —), `metric:registry:sys_psi_io/spike` 1 (honest —), `metric:webui:sys_io/spike` 1 (honest 1), `metric:webui:sys_psi_io/spike` 1 (honest —), `span:persistence:PersistenceCategory.getId/spike` 1 (honest —)

**Inert** (calibrated by the selection, but the gap exceeds the hold; not placeable), **at grid edge** (K = 100) and **appear-only** sensors (placeable through `appear` alone, listed apart), primary:

- r10: inert 0: none; at grid edge 1: `span:persistence:UserRepository.getUserByName/spike`; appear-only 404: `log:auth:059f77b5fee4`, `log:auth:0788a45dbb86`, `log:auth:0ae227c4f15d`, `log:auth:13e7be34fb70`, `log:auth:16e888bf8922`, `log:auth:16f327e6bd4d`, `log:auth:2d7f16630b87`, `log:auth:2ff20a342a41`, `log:auth:319b41b82d9b`, `log:auth:3219d9dbbaed`, `log:auth:35563463c928`, `log:auth:35873ee1cc7e`, `log:auth:3917ffeac5ec`, `log:auth:3b1fa69c3451`, `log:auth:3f00555a765d`, `log:auth:407989c51698`, `log:auth:4a79ac521b28`, `log:auth:4de8468724c7`, `log:auth:52a075c95ff9`, `log:auth:56bcc1a07d39`, `log:auth:56c309f6427c`, `log:auth:6c19cf62298a`, `log:auth:6e7a7f83a9e6`, `log:auth:7197cbb5d81b`, `log:auth:72ae3fa150b5`, `log:auth:7568b9fca9ad`, `log:auth:7877eab35e98`, `log:auth:7b327c4594ff`, `log:auth:811e1f658b4b`, `log:auth:8733ab2f4543`, `log:auth:87614f556af3`, `log:auth:8b277994d6dd`, `log:auth:8ddb5025ba7f`, `log:auth:8eb94ac35bf9`, `log:auth:955560e889b3`, `log:auth:96ea0f608ef2`, `log:auth:9c6795a8c551`, `log:auth:a0105883ccdd`, `log:auth:a07c7bcc6c3d`, `log:auth:a59061884c18` (+364 more in the JSON).
- r1: inert 0: none; at grid edge 0: none; appear-only 403: `log:auth:059f77b5fee4`, `log:auth:0788a45dbb86`, `log:auth:0ae227c4f15d`, `log:auth:13e7be34fb70`, `log:auth:16e888bf8922`, `log:auth:16f327e6bd4d`, `log:auth:2d7f16630b87`, `log:auth:2ff20a342a41`, `log:auth:319b41b82d9b`, `log:auth:3219d9dbbaed`, `log:auth:35563463c928`, `log:auth:35873ee1cc7e`, `log:auth:3917ffeac5ec`, `log:auth:3b1fa69c3451`, `log:auth:3f00555a765d`, `log:auth:407989c51698`, `log:auth:4a79ac521b28`, `log:auth:4de8468724c7`, `log:auth:52a075c95ff9`, `log:auth:56bcc1a07d39`, `log:auth:56c309f6427c`, `log:auth:6c19cf62298a`, `log:auth:6e7a7f83a9e6`, `log:auth:7197cbb5d81b`, `log:auth:72ae3fa150b5`, `log:auth:7568b9fca9ad`, `log:auth:7877eab35e98`, `log:auth:7b327c4594ff`, `log:auth:811e1f658b4b`, `log:auth:8733ab2f4543`, `log:auth:87614f556af3`, `log:auth:8b277994d6dd`, `log:auth:8ddb5025ba7f`, `log:auth:8eb94ac35bf9`, `log:auth:955560e889b3`, `log:auth:96ea0f608ef2`, `log:auth:9c6795a8c551`, `log:auth:a0105883ccdd`, `log:auth:a07c7bcc6c3d`, `log:auth:a59061884c18` (+363 more in the JSON).
- r0.2: inert 0: none; at grid edge 0: none; appear-only 401: `log:auth:059f77b5fee4`, `log:auth:0788a45dbb86`, `log:auth:0ae227c4f15d`, `log:auth:13e7be34fb70`, `log:auth:16e888bf8922`, `log:auth:16f327e6bd4d`, `log:auth:2d7f16630b87`, `log:auth:2ff20a342a41`, `log:auth:319b41b82d9b`, `log:auth:3219d9dbbaed`, `log:auth:35563463c928`, `log:auth:35873ee1cc7e`, `log:auth:3917ffeac5ec`, `log:auth:3b1fa69c3451`, `log:auth:3f00555a765d`, `log:auth:407989c51698`, `log:auth:4a79ac521b28`, `log:auth:4de8468724c7`, `log:auth:52a075c95ff9`, `log:auth:56bcc1a07d39`, `log:auth:56c309f6427c`, `log:auth:6c19cf62298a`, `log:auth:6e7a7f83a9e6`, `log:auth:7197cbb5d81b`, `log:auth:72ae3fa150b5`, `log:auth:7568b9fca9ad`, `log:auth:7877eab35e98`, `log:auth:7b327c4594ff`, `log:auth:811e1f658b4b`, `log:auth:8733ab2f4543`, `log:auth:87614f556af3`, `log:auth:8b277994d6dd`, `log:auth:8ddb5025ba7f`, `log:auth:8eb94ac35bf9`, `log:auth:955560e889b3`, `log:auth:96ea0f608ef2`, `log:auth:9c6795a8c551`, `log:auth:a0105883ccdd`, `log:auth:a07c7bcc6c3d`, `log:auth:a59061884c18` (+361 more in the JSON).
- r0.05: inert 0: none; at grid edge 0: none; appear-only 401: `log:auth:059f77b5fee4`, `log:auth:0788a45dbb86`, `log:auth:0ae227c4f15d`, `log:auth:13e7be34fb70`, `log:auth:16e888bf8922`, `log:auth:16f327e6bd4d`, `log:auth:2d7f16630b87`, `log:auth:2ff20a342a41`, `log:auth:319b41b82d9b`, `log:auth:3219d9dbbaed`, `log:auth:35563463c928`, `log:auth:35873ee1cc7e`, `log:auth:3917ffeac5ec`, `log:auth:3b1fa69c3451`, `log:auth:3f00555a765d`, `log:auth:407989c51698`, `log:auth:4a79ac521b28`, `log:auth:4de8468724c7`, `log:auth:52a075c95ff9`, `log:auth:56bcc1a07d39`, `log:auth:56c309f6427c`, `log:auth:6c19cf62298a`, `log:auth:6e7a7f83a9e6`, `log:auth:7197cbb5d81b`, `log:auth:72ae3fa150b5`, `log:auth:7568b9fca9ad`, `log:auth:7877eab35e98`, `log:auth:7b327c4594ff`, `log:auth:811e1f658b4b`, `log:auth:8733ab2f4543`, `log:auth:87614f556af3`, `log:auth:8b277994d6dd`, `log:auth:8ddb5025ba7f`, `log:auth:8eb94ac35bf9`, `log:auth:955560e889b3`, `log:auth:96ea0f608ef2`, `log:auth:9c6795a8c551`, `log:auth:a0105883ccdd`, `log:auth:a07c7bcc6c3d`, `log:auth:a59061884c18` (+361 more in the JSON).

**Not placeable at this quiet time** (L, M, S, T sensors with no calibrated rule), by family (with a dropped rule / inert / unarmed only), then those with a dropped rule:

- r10: 8 sensors (S 0/0/8); with a dropped rule: none
- r1: 8 sensors (S 0/0/8); with a dropped rule: none
- r0.2: 8 sensors (S 0/0/8); with a dropped rule: none
- r0.05: 8 sensors (S 0/0/8); with a dropped rule: none

- `appear` (V3_APPEAR_RULE): new streams in no-fault cells per service, summed over the held-out cells (they enter the honest counts): r10 none; r1 none; r0.2 none; r0.05 none.
- **floor arm (share 0.05)**: r10 588/20/0/460 rules, 60 placeable + 404 appear-only sensors; r1 600/7/0/459 rules, 60 placeable + 403 appear-only sensors; r0.2 593/12/0/454 rules, 60 placeable + 401 appear-only sensors; r0.05 593/12/0/454 rules, 60 placeable + 401 appear-only sensors.
- **sensitivity, <= 1 held-out alarm (K_GRID only, no range fallback)**: r10 554/18/0/496 rules, 44 placeable + 404 appear-only sensors; r1 558/13/0/495 rules, 44 placeable + 403 appear-only sensors; r0.2 556/13/0/490 rules, 44 placeable + 401 appear-only sensors; r0.05 557/12/0/490 rules, 45 placeable + 401 appear-only sensors.

## Honest false alarms (decisions 64, 67): nested leave-one-cell-out unions on the no-fault cells

Union of the sensors' rules, each held-out no-fault cell scored at the values re-selected without it (its leave-one-cell-out fit), restarted after each alarm: count (/h [exact 95 % bound]); per family also the sum of its calibrated rules' honest counts (the reviewer's tally). The honest per-sensor rate is the sensor's false-alarm cost for CELF (JSON calibration.*.sensors.*.honestPerHour). Campaign B's fresh check can certify at best 20.0/h (0 alarms in 0.15 h per rate).

| setting | rate | T (h) | E | L | M | S | T | all placeable L, M, S, T |
|---|---|---|---|---|---|---|---|---|
| primary | r10 | 0.550 | 2 (3.6/h [11.4], 0.550 of 0.55 h) · sum 2 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [5.4], 0.550 of 0.55 h) · sum 0 · no evidence: 0 rules, 7 sensors | — | 22 (40.0/h [57.1], 0.550 of 0.55 h) · sum 20 · no evidence: 0 rules, 0 sensors | 61 (110.9/h [137.3], 0.550 of 0.55 h) · sum 37 · no evidence: 0 rules, 4 sensors | 95 (172.7/h [204.8], 0.55 of 0.55 h) |
| primary | r1 | 0.550 | 1 (1.8/h [8.6], 0.550 of 0.55 h) · sum 1 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [5.4], 0.550 of 0.55 h) · sum 0 · no evidence: 0 rules, 4 sensors | — | 41 (74.5/h [96.7], 0.550 of 0.55 h) · sum 39 · no evidence: 0 rules, 0 sensors | 25 (45.5/h [63.5], 0.550 of 0.55 h) · sum 25 · no evidence: 0 rules, 4 sensors | 72 (130.9/h [159.3], 0.55 of 0.55 h) |
| primary | r0.2 | 0.550 | 0 (0.0/h [5.4], 0.550 of 0.55 h) · sum 0 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [5.4], 0.550 of 0.55 h) · sum 0 · no evidence: 0 rules, 5 sensors | — | 29 (52.7/h [71.9], 0.550 of 0.55 h) · sum 34 · no evidence: 0 rules, 0 sensors | 24 (43.6/h [61.4], 0.550 of 0.55 h) · sum 20 · no evidence: 0 rules, 3 sensors | 64 (116.4/h [143.3], 0.55 of 0.55 h) |
| primary | r0.05 | 0.550 | 0 (0.0/h [5.4], 0.550 of 0.55 h) · sum 0 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [5.4], 0.550 of 0.55 h) · sum 0 · no evidence: 0 rules, 3 sensors | — | 20 (36.4/h [52.8], 0.550 of 0.55 h) · sum 19 · no evidence: 0 rules, 0 sensors | 31 (56.4/h [76.1], 0.550 of 0.55 h) · sum 27 · no evidence: 0 rules, 3 sensors | 61 (110.9/h [137.3], 0.55 of 0.55 h) |
| atMostOne | r10 | 0.550 | 2 (3.6/h [11.4], 0.550 of 0.55 h) · sum 2 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [5.4], 0.550 of 0.55 h) · sum 0 · no evidence: 0 rules, 7 sensors | — | 40 (72.7/h [94.7], 0.550 of 0.55 h) · sum 38 · no evidence: 0 rules, 0 sensors | 119 (216.4/h [251.9], 0.550 of 0.55 h) · sum 91 · no evidence: 0 rules, 4 sensors | 171 (310.9/h [353.0], 0.55 of 0.55 h) |
| atMostOne | r1 | 0.550 | 3 (5.5/h [14.1], 0.550 of 0.55 h) · sum 3 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [5.4], 0.550 of 0.55 h) · sum 0 · no evidence: 0 rules, 4 sensors | — | 56 (101.8/h [127.2], 0.550 of 0.55 h) · sum 37 · no evidence: 0 rules, 0 sensors | 67 (121.8/h [149.3], 0.550 of 0.55 h) · sum 62 · no evidence: 0 rules, 4 sensors | 110 (200.0/h [234.3], 0.55 of 0.55 h) |
| atMostOne | r0.2 | 0.550 | 0 (0.0/h [5.4], 0.550 of 0.55 h) · sum 0 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [5.4], 0.550 of 0.55 h) · sum 0 · no evidence: 0 rules, 5 sensors | — | 39 (70.9/h [92.6], 0.550 of 0.55 h) · sum 48 · no evidence: 0 rules, 0 sensors | 66 (120.0/h [147.3], 0.550 of 0.55 h) · sum 65 · no evidence: 0 rules, 3 sensors | 111 (201.8/h [236.3], 0.55 of 0.55 h) |
| atMostOne | r0.05 | 0.550 | 0 (0.0/h [5.4], 0.550 of 0.55 h) · sum 0 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [5.4], 0.550 of 0.55 h) · sum 0 · no evidence: 0 rules, 3 sensors | — | 37 (67.3/h [88.5], 0.550 of 0.55 h) · sum 40 · no evidence: 0 rules, 0 sensors | 50 (90.9/h [115.1], 0.550 of 0.55 h) · sum 47 · no evidence: 0 rules, 3 sensors | 100 (181.8/h [214.7], 0.55 of 0.55 h) |

P4-selected sets (the sensors P4 selected over its folds, or with one episode the candidates judged a win), honest nested union, primary:

- P4a auth-freeze-effect r0.05: `log:webui:d4d75ec135e6`, `span:webui:LoginActionServlet.handlePOSTRequest` -> 1 (1.8/h [8.6], 0.55 of 0.55 h) · sum over the sensors 1
- P4a auth-freeze-effect r0.2: `span:webui:LoginActionServlet.handlePOSTRequest` -> 1 (1.8/h [8.6], 0.55 of 0.55 h) · sum over the sensors 1
- P4a auth-freeze-effect r1: `span:webui:LoginActionServlet.handlePOSTRequest` -> 1 (1.8/h [8.6], 0.55 of 0.55 h) · sum over the sensors 1
- P4a auth-freeze-effect r10: `span:webui:LoginActionServlet.handlePOSTRequest` -> 1 (1.8/h [8.6], 0.55 of 0.55 h) · sum over the sensors 1
- P4a persistence-cpu-throttle-effect r0.05: `span:image:AbstractCache.getEntries` -> 1 (1.8/h [8.6], 0.55 of 0.55 h) · sum over the sensors 1
- P4a persistence-cpu-throttle-effect r0.2: `span:auth:AuthUserActionsRest.login`, `span:auth:ShaSecurityProvider.validate` -> 2 (3.6/h [11.4], 0.55 of 0.55 h) · sum over the sensors 2
- P4a persistence-cpu-throttle-effect r1: `span:webui:IndexServlet.handleGETRequest` -> 0 (0.0/h [5.4], 0.55 of 0.55 h) · sum over the sensors 0
- P4a persistence-cpu-throttle-effect r10: `span:auth:AuthUserActionsRest.login`, `span:webui:IndexServlet.handleGETRequest` -> 3 (5.5/h [14.1], 0.55 of 0.55 h) · sum over the sensors 3
- P4b auth-freeze-effect r0.2: `metric:auth:sys_psi_cpu` -> 1 (1.8/h [8.6], 0.55 of 0.55 h) · sum over the sensors 1
- P4b auth-freeze-effect r1: `metric:auth:sys_psi_cpu` -> 1 (1.8/h [8.6], 0.55 of 0.55 h) · sum over the sensors 1
- P4b auth-freeze-effect r10: `metric:auth:sys_psi_cpu` -> 1 (1.8/h [8.6], 0.55 of 0.55 h) · sum over the sensors 1
- P4b persistence-cpu-throttle-effect r0.05: `span:persistence:CategoryEndpoint.listAllEntities` -> 2 (3.6/h [11.4], 0.55 of 0.55 h) · sum over the sensors 2
- P4b persistence-cpu-throttle-effect r0.2: `span:persistence:CategoryEndpoint.listAllEntities` -> 1 (1.8/h [8.6], 0.55 of 0.55 h) · sum over the sensors 1
- P4b persistence-cpu-throttle-effect r1: `span:persistence:CategoryEndpoint.listAllEntities` -> 0 (0.0/h [5.4], 0.55 of 0.55 h) · sum over the sensors 0
- P4b persistence-cpu-throttle-effect r10: `span:persistence:CategoryEndpoint.listAllEntities`, `span:persistence:UserRepository.getUserByName` -> 4 (7.3/h [16.6], 0.55 of 0.55 h) · sum over the sensors 4

## v2.4 reference row: family operating point (decision 53, 15/h, from v2.4's own code)

K per family: E 12.5, L 2.5, M —, S —, T —, system —.

| class | family | r10 | r1 | r0.2 | r0.05 |
|---|---|---|---|---|---|
| auth-freeze | E | ok (K 12.5) | ok (K 12.5) | ok (K 12.5) | ok (K 12.5) |
| auth-freeze | L | ok (K 2.5) | ok (K 2.5) | ok (K 2.5) | ok (K 2.5) |
| auth-freeze | M | n/c | n/c | n/c | n/c |
| auth-freeze | S | no | no | no | no |
| auth-freeze | T | no | no | no | no |
| persistence-cpu-throttle | E | ok (K 12.5) | ok (K 12.5) | ok (K 12.5) | ok (K 12.5) |
| persistence-cpu-throttle | L | ok (K 2.5) | ok (K 2.5) | ok (K 2.5) | ok (K 2.5) |
| persistence-cpu-throttle | M | n/c | n/c | n/c | n/c |
| persistence-cpu-throttle | S | no | no | no | no |
| persistence-cpu-throttle | T | no | no | no | no |

## Predictions (primary: calibrated arm, floor primary)

- **P1** (auth-freeze; decision 54's interval, observed = first `failed` catch): 16/16; per rate r10 4/4, r1 4/4, r0.2 4/4, r0.05 4/4; not evaluable 0; holds by branch: error answer before the timeout (declared alternative) 5, timeout interval 11; verdict **holds**.
- **P2** r10 (failed before the first `failed` catch <= 153.00): 4/4, counts [116, 129, 117, 118], verdict holds.
- **P2** r1 (failed before the first `failed` catch <= 18.00): 4/4, counts [16, 16, 16, 16], verdict holds.
- **P2** r0.2 (failed before the first `failed` catch <= 6.00): 4/4, counts [4, 4, 4, 4], verdict holds.
- **P2** r0.05 (failed before the first `failed` catch <= 3.75): 4/4, counts [1, 1, 1, 1], verdict holds.
- **P3** auth-freeze: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P3** persistence-cpu-throttle: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P4** compares against the ledger E as the OR of its calibrated rules, its `failed` rule exempt from calibration (decisions 63, 70; V3_P4_LEDGER_READING = `calibrated-ledger`): a dropped ledger rule is listed below, not a reason for `—`. Two arms (decision 67): calibrated (primary) and optimistic bound (dropped rules armed at K = 100 / m = 5, beside, not evidence).
- Dropped ledger rules per rate (decision 70: listed; the ledger compares by its calibrated rules): r10 none; r1 none; r0.2 none; r0.05 none.
- **P4a** auth-freeze (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 0/4 (ledger missed, sensor caught: 0); r1 0/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 0); r0.05 0/4 (ledger missed, sensor caught: 0); highest rate **none in {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/4 (ledger missed, sensor caught: 0); r1 0/4 (ledger missed, sensor caught: 0); r0.2 2/4 (ledger missed, sensor caught: 0); r0.05 3/4 (ledger missed, sensor caught: 0); highest rate 0.05.
- **P4a** persistence-cpu-throttle (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 1/4 (ledger missed, sensor caught: 0); r1 3/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 0); r0.05 0/4 (ledger missed, sensor caught: 0); highest rate **1**.
  - optimistic bound (not evidence): r10 1/4 (ledger missed, sensor caught: 0); r1 3/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 0); r0.05 0/4 (ledger missed, sensor caught: 0); highest rate 1.
- **P4b** auth-freeze (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 0/4 (ledger missed, sensor caught: 0); r1 0/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 0); r0.05 0/4 (ledger missed, sensor caught: 0); highest rate **none in {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/4 (ledger missed, sensor caught: 0); r1 0/4 (ledger missed, sensor caught: 0); r0.2 1/4 (ledger missed, sensor caught: 0); r0.05 4/4 (ledger missed, sensor caught: 0); highest rate 0.05.
- **P4b** persistence-cpu-throttle (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 1/4 (ledger missed, sensor caught: 0); r1 3/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 0); r0.05 1/4 (ledger missed, sensor caught: 0); highest rate **1**.
  - optimistic bound (not evidence): r10 1/4 (ledger missed, sensor caught: 0); r1 3/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 0); r0.05 1/4 (ledger missed, sensor caught: 0); highest rate 1.

### P4 per class and rate: placeable sensors, dropped rules and non-placeable sensors on the affected path

- auth-freeze r10: placeable sensors 464 (candidates with a catch: 7); dropped on the path: `metric:auth:sys_psi_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_io/spike`, `metric:webui:sys_psi_io/spike`, `span:auth:RandomSessionIdGenerator.getSessionId/spike`, `span:auth:ShaSecurityProvider.blobToString/spike`, `span:auth:ShaSecurityProvider.getKeyProvider/spike`, `span:auth:ShaSecurityProvider.getSha512/spike`, `span:auth:ShaSecurityProvider.secure/spike`, `span:persistence:PersistenceCategory.getId/spike`, `span:persistence:PersistenceUser.getId/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- auth-freeze r1: placeable sensors 463 (candidates with a catch: 8); dropped on the path: `metric:auth:sys_psi_io/spike`, `metric:persistence:sys_psi_io/spike`, `span:persistence:PersistenceCategory.getId/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- auth-freeze r0.2: placeable sensors 461 (candidates with a catch: 4); dropped on the path: `metric:auth:sys_io/spike`, `metric:persistence:sys_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_io/spike`, `span:auth:ShaSecurityProvider.getKeyProvider/spike`, `span:persistence:PersistenceCategory.getId/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- auth-freeze r0.05: placeable sensors 461 (candidates with a catch: 5); dropped on the path: `metric:auth:sys_io/spike`, `metric:auth:sys_psi_io/spike`, `metric:persistence:sys_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_io/spike`, `metric:webui:sys_psi_io/spike`, `span:persistence:PersistenceCategory.getId/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- persistence-cpu-throttle r10: placeable sensors 464 (candidates with a catch: 32); dropped on the path: `metric:auth:sys_psi_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_io/spike`, `metric:webui:sys_psi_io/spike`, `span:auth:RandomSessionIdGenerator.getSessionId/spike`, `span:auth:ShaSecurityProvider.blobToString/spike`, `span:auth:ShaSecurityProvider.getKeyProvider/spike`, `span:auth:ShaSecurityProvider.getSha512/spike`, `span:auth:ShaSecurityProvider.secure/spike`, `span:persistence:PersistenceCategory.getId/spike`, `span:persistence:PersistenceUser.getId/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- persistence-cpu-throttle r1: placeable sensors 463 (candidates with a catch: 28); dropped on the path: `metric:auth:sys_psi_io/spike`, `metric:persistence:sys_psi_io/spike`, `span:persistence:PersistenceCategory.getId/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- persistence-cpu-throttle r0.2: placeable sensors 461 (candidates with a catch: 20); dropped on the path: `metric:auth:sys_io/spike`, `metric:persistence:sys_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_io/spike`, `span:auth:ShaSecurityProvider.getKeyProvider/spike`, `span:persistence:PersistenceCategory.getId/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- persistence-cpu-throttle r0.05: placeable sensors 461 (candidates with a catch: 13); dropped on the path: `metric:auth:sys_io/spike`, `metric:auth:sys_psi_io/spike`, `metric:persistence:sys_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_io/spike`, `metric:webui:sys_psi_io/spike`, `span:persistence:PersistenceCategory.getId/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none

### P4 folds (sensor rule vs ledger rule; lead, margin; category)

**Calibrated arm**

- P4a auth-freeze r10 (candidates 7; paired differences ledger - sensor: mean -10.013 [-10.749, -9.711] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 10.477 vs E `absent` 0.667; lead -9.810, margin 4.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 11.425 vs E `absent` 0.677; lead -10.749, margin 2.2e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 10.348 vs E `absent` 0.638; lead -9.711, margin 2.8e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 10.425 vs E `absent` 0.642; lead -9.783, margin 4.6e-05; tied 1 (win share 0/1); **not faster**
- P4a auth-freeze r1 (candidates 8; paired differences ledger - sensor: mean -18.099 [-18.275, -17.850] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.248 vs E `absent` 0.979; lead -18.269, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.475 vs E `absent` 1.200; lead -18.275, margin 2.1e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.480 vs E `absent` 1.630; lead -17.850, margin 7.2e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.537 vs E `absent` 1.536; lead -18.001, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
- P4a auth-freeze r0.2 (candidates 4; paired differences ledger - sensor: mean -19.196 [-19.313, -19.102] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 23.363 vs E `absent` 4.050; lead -19.313, margin 1.9e-06; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.522 vs E `absent` 0.277; lead -19.245, margin 2.4e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 22.511 vs E `absent` 3.409; lead -19.102, margin 1.9e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 21.272 vs E `absent` 2.149; lead -19.123, margin 1.9e-06; tied 1 (win share 0/1); **not faster**
- P4a auth-freeze r0.05 (candidates 5; paired differences ledger - sensor: mean -25.215 [-43.445, -19.067] s; availability-clock wins 0 of 3 evaluable):
  - ep1 b1: log:webui:d4d75ec135e6 `appear` 25.896 vs E `absent` 6.817; lead -19.079, margin 0.97; tied 1 (win share 0/1); **not faster**
  - ep2 b1: log:webui:d4d75ec135e6 `appear` 20.493 vs E `absent` 1.426; lead -19.067, margin 0.96; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:webui:LoginActionServlet.handlePOSTRequest `—` — vs E `absent` 16.775; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b3: log:webui:d4d75ec135e6 `appear` 29.799 vs E `absent` 10.529; lead -19.270, margin 1; tied 1 (win share 0/1); **not faster**
- P4a persistence-cpu-throttle r10 (candidates 32; paired differences ledger - sensor: mean -0.559 [-1.005, 0.003] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:IndexServlet.handleGETRequest `median` 0.604 vs E `median` 0.235; lead -0.369, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:auth:AuthUserActionsRest.login `run3` 1.293 vs E `run3` 1.296; lead 0.003, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep3 b2: span:webui:IndexServlet.handleGETRequest `spike` 1.274 vs E `median` 0.408; lead -0.866, margin 1.4e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:auth:AuthUserActionsRest.login `spike` 1.298 vs E `median` 0.293; lead -1.005, margin 2.7e-05; tied 1 (win share 0/1); **not faster**
- P4a persistence-cpu-throttle r1 (candidates 28; paired differences ledger - sensor: mean -0.473 [-1.897, 0.003] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:IndexServlet.handleGETRequest `median` 2.927 vs E `spike` 1.029; lead -1.897, margin 1.4e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:webui:IndexServlet.handleGETRequest `median` 2.817 vs E `median` 2.818; lead 0.002, margin 1.5e-05; tied 1 (win share 1/1); **win**
  - ep3 b2: span:webui:IndexServlet.handleGETRequest `median` 2.164 vs E `median` 2.165; lead 0.002, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep4 b3: span:webui:IndexServlet.handleGETRequest `spike` 1.859 vs E `spike` 1.862; lead 0.003, margin 1.2e-05; tied 1 (win share 1/1); **win**
- P4a persistence-cpu-throttle r0.2 (candidates 20; paired differences ledger - sensor: mean -8.741 [-20.025, 0.029] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:auth:ShaSecurityProvider.validate `absent` 9.049 vs E `absent` 9.078; lead 0.029, margin 4.1e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.021 start + 0.0078 gap + 0]
  - ep2 b1: span:auth:ShaSecurityProvider.validate `absent` 16.013 vs E `spike` 1.021; lead -14.991, margin 1.1e-05; tied 1 (win share 0/1); **not faster** (decision 57: the silence-ending observation names no request)
  - ep3 b2: span:auth:AuthUserActionsRest.login `spike` 22.539 vs E `absent` 2.514; lead -20.025, margin 1e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:auth:ShaSecurityProvider.validate `absent` 3.376 vs E `absent` 3.400; lead 0.024, margin 1.1e-05; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.016 start + 0.0078 gap + 0]
- P4a persistence-cpu-throttle r0.05 (candidates 13; paired differences ledger - sensor: mean 0.016 [0.009, 0.019] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:image:AbstractCache.getEntries `absent` 34.000 vs E `absent` 34.017; lead 0.017, margin 1.7e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0072 start + 0.0098 gap + 0]
  - ep2 b1: span:image:AbstractCache.getEntries `absent` 5.437 vs E `spike` 5.446; lead 0.009, margin 9.5e-07; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request)
  - ep3 b2: span:image:AbstractCache.getEntries `absent` 7.735 vs E `absent` 7.754; lead 0.019, margin 1.2e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0087 start + 0.0098 gap + 0]
  - ep4 b3: span:image:AbstractCache.getEntries `absent` 57.393 vs E `absent` 57.410; lead 0.017, margin 2.9e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0076 start + 0.0098 gap + 0]
- P4b auth-freeze r10 (candidates 1; paired differences ledger - sensor: mean -14.252 [-14.281, -14.171] s; availability-clock wins 0 of 4 evaluable):
  - ep1 b1: metric:auth:sys_psi_cpu `run3` 14.947 vs E `absent` 0.667; lead -14.280, margin 4.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: metric:auth:sys_psi_cpu `run3` 14.847 vs E `absent` 0.677; lead -14.171, margin 2.3e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:auth:sys_psi_cpu `run3` 14.914 vs E `absent` 0.638; lead -14.276, margin 2.8e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:auth:sys_psi_cpu `run3` 14.922 vs E `absent` 0.642; lead -14.281, margin 4.6e-05; tied 1 (win share 0/1); **not faster**
- P4b auth-freeze r1 (candidates 1; paired differences ledger - sensor: mean -13.084 [-13.345, -12.326] s; availability-clock wins 0 of 4 evaluable):
  - ep1 b1: metric:auth:sys_psi_cpu `median` 14.323 vs E `absent` 0.979; lead -13.345, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: metric:auth:sys_psi_cpu `run3` 14.539 vs E `absent` 1.200; lead -13.338, margin 2.2e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:auth:sys_psi_cpu `median` 13.956 vs E `absent` 1.630; lead -12.326, margin 7.3e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:auth:sys_psi_cpu `run3` 14.862 vs E `absent` 1.536; lead -13.326, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
- P4b auth-freeze r0.2 (candidates 1; paired differences ledger - sensor: mean -9.890 [-9.902, -9.883] s; availability-clock wins 0 of 4 evaluable):
  - ep1 b1: metric:auth:sys_psi_cpu `median` 13.940 vs E `absent` 4.050; lead -9.890, margin 2e-06; tied 1 (win share 0/1); **not faster**
  - ep2 b1: metric:auth:sys_psi_cpu `median` 10.179 vs E `absent` 0.277; lead -9.902, margin 2.5e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:auth:sys_psi_cpu `median` 13.294 vs E `absent` 3.409; lead -9.886, margin 2e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:auth:sys_psi_cpu `median` 12.033 vs E `absent` 2.149; lead -9.883, margin 2e-06; tied 1 (win share 0/1); **not faster**
- P4b auth-freeze r0.05 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `absent` 6.817; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b1: — `—` — vs E `absent` 1.426; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b2: — `—` — vs E `absent` 16.775; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b3: — `—` — vs E `absent` 10.529; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b persistence-cpu-throttle r10 (candidates 6; paired differences ledger - sensor: mean -0.345 [-0.985, 0.113] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 0.589 vs E `median` 0.235; lead -0.354, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 1.183 vs E `run3` 1.296; lead 0.113, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep3 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 0.560 vs E `median` 0.408; lead -0.152, margin 1.4e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:persistence:UserRepository.getUserByName `spike` 1.278 vs E `median` 0.293; lead -0.985, margin 2.7e-05; tied 1 (win share 0/1); **not faster**
- P4b persistence-cpu-throttle r1 (candidates 6; paired differences ledger - sensor: mean -0.201 [-3.780, 1.938] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 1.009 vs E `spike` 1.029; lead 0.020, margin 1.4e-05; tied 1 (win share 1/1); **win**
  - ep2 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 0.881 vs E `median` 2.818; lead 1.938, margin 1.5e-05; tied 1 (win share 1/1); **win**
  - ep3 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 1.148 vs E `median` 2.165; lead 1.018, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep4 b3: span:persistence:CategoryEndpoint.listAllEntities `spike` 5.641 vs E `spike` 1.862; lead -3.780, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
- P4b persistence-cpu-throttle r0.2 (candidates 5; paired differences ledger - sensor: mean -4.390 [-17.492, -0.002] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 9.095 vs E `absent` 9.078; lead -0.017, margin 4.1e-06; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:persistence:CategoryEndpoint.listAllEntities `absent` 18.513 vs E `spike` 1.021; lead -17.492, margin 1.1e-05; tied 1 (win share 0/1); **not faster** (decision 57: the silence-ending observation names no request)
  - ep3 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 2.517 vs E `absent` 2.514; lead -0.002, margin 1e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:persistence:CategoryEndpoint.listAllEntities `spike` 3.449 vs E `absent` 3.400; lead -0.049, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
- P4b persistence-cpu-throttle r0.05 (candidates 6; paired differences ledger - sensor: mean -0.312 [-0.613, 0.023] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 34.590 vs E `absent` 34.017; lead -0.572, margin 1.7e-06; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 5.424 vs E `spike` 5.446; lead 0.023, margin 9.5e-07; tied 1 (win share 1/1); **win**
  - ep3 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 8.367 vs E `absent` 7.754; lead -0.613, margin 1.2e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:persistence:CategoryEndpoint.listAllEntities `spike` 57.495 vs E `absent` 57.410; lead -0.085, margin 2.9e-06; tied 1 (win share 0/1); **not faster**

**Optimistic bound (not evidence)**

- P4a auth-freeze r10 (candidates 8; paired differences ledger - sensor: mean -13.238 [-19.178, -9.711] s; availability-clock wins 0 of 2 evaluable):
  - ep1 b1: metric:webui:sys_io `spike` 14.947 vs E `absent` 0.667; lead -14.280, margin 4.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: metric:webui:sys_io `spike` 19.854 vs E `absent` 0.677; lead -19.178, margin 2.3e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 10.348 vs E `absent` 0.638; lead -9.711, margin 2.8e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 10.425 vs E `absent` 0.642; lead -9.783, margin 4.6e-05; tied 1 (win share 0/1); **not faster**
- P4a auth-freeze r1 (candidates 8; paired differences ledger - sensor: mean -18.099 [-18.275, -17.850] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.248 vs E `absent` 0.979; lead -18.269, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.475 vs E `absent` 1.200; lead -18.275, margin 2.1e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.480 vs E `absent` 1.630; lead -17.850, margin 7.2e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.537 vs E `absent` 1.536; lead -18.001, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
- P4a auth-freeze r0.2 (candidates 6; paired differences ledger - sensor: mean -12.392 [-24.893, 0.107] s; availability-clock wins 2 of 4 evaluable):
  - ep1 b1: metric:webui:sys_io `spike` 3.943 vs E `absent` 4.050; lead 0.107, margin 2e-06; tied 1 (win share 1/1); **win**
  - ep2 b1: metric:webui:sys_io `spike` 0.176 vs E `absent` 0.277; lead 0.101, margin 2.5e-06; tied 1 (win share 1/1); **win**
  - ep3 b2: metric:webui:sys_io `spike` 28.302 vs E `absent` 3.409; lead -24.893, margin 2e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:webui:sys_io `spike` 27.030 vs E `absent` 2.149; lead -24.881, margin 2e-06; tied 1 (win share 0/1); **not faster**
- P4a auth-freeze r0.05 (candidates 6; paired differences ledger - sensor: mean 0.150 [-24.850, 15.161] s; availability-clock wins 3 of 4 evaluable):
  - ep1 b1: metric:webui:sys_io `spike` 1.683 vs E `absent` 6.817; lead 5.134, margin 1.3e-06; tied 1 (win share 1/1); **win**
  - ep2 b1: metric:webui:sys_io `spike` 26.276 vs E `absent` 1.426; lead -24.850, margin 1.3e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:webui:sys_io `spike` 1.614 vs E `absent` 16.775; lead 15.161, margin 1.5e-06; tied 1 (win share 1/1); **win**
  - ep4 b3: metric:webui:sys_io `spike` 5.374 vs E `absent` 10.529; lead 5.156, margin 1.3e-06; tied 1 (win share 1/1); **win**
- P4a persistence-cpu-throttle r10 (candidates 33; paired differences ledger - sensor: mean -0.559 [-1.005, 0.003] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:IndexServlet.handleGETRequest `median` 0.604 vs E `median` 0.235; lead -0.369, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:auth:AuthUserActionsRest.login `run3` 1.293 vs E `run3` 1.296; lead 0.003, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep3 b2: span:webui:IndexServlet.handleGETRequest `spike` 1.274 vs E `median` 0.408; lead -0.866, margin 1.4e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:auth:AuthUserActionsRest.login `spike` 1.298 vs E `median` 0.293; lead -1.005, margin 2.7e-05; tied 1 (win share 0/1); **not faster**
- P4a persistence-cpu-throttle r1 (candidates 28; paired differences ledger - sensor: mean -0.473 [-1.897, 0.003] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:IndexServlet.handleGETRequest `median` 2.927 vs E `spike` 1.029; lead -1.897, margin 1.4e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:webui:IndexServlet.handleGETRequest `median` 2.817 vs E `median` 2.818; lead 0.002, margin 1.5e-05; tied 1 (win share 1/1); **win**
  - ep3 b2: span:webui:IndexServlet.handleGETRequest `median` 2.164 vs E `median` 2.165; lead 0.002, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep4 b3: span:webui:IndexServlet.handleGETRequest `spike` 1.859 vs E `spike` 1.862; lead 0.003, margin 1.2e-05; tied 1 (win share 1/1); **win**
- P4a persistence-cpu-throttle r0.2 (candidates 22; paired differences ledger - sensor: mean -8.741 [-20.025, 0.029] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:auth:ShaSecurityProvider.validate `absent` 9.049 vs E `absent` 9.078; lead 0.029, margin 4.1e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.021 start + 0.0078 gap + 0]
  - ep2 b1: span:auth:ShaSecurityProvider.validate `absent` 16.013 vs E `spike` 1.021; lead -14.991, margin 1.1e-05; tied 1 (win share 0/1); **not faster** (decision 57: the silence-ending observation names no request)
  - ep3 b2: span:auth:AuthUserActionsRest.login `spike` 22.539 vs E `absent` 2.514; lead -20.025, margin 1e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:auth:ShaSecurityProvider.validate `absent` 3.376 vs E `absent` 3.400; lead 0.024, margin 1.1e-05; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.016 start + 0.0078 gap + 0]
- P4a persistence-cpu-throttle r0.05 (candidates 14; paired differences ledger - sensor: mean 0.016 [0.009, 0.019] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:image:AbstractCache.getEntries `absent` 34.000 vs E `absent` 34.017; lead 0.017, margin 1.7e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0072 start + 0.0098 gap + 0]
  - ep2 b1: span:image:AbstractCache.getEntries `absent` 5.437 vs E `spike` 5.446; lead 0.009, margin 9.5e-07; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request)
  - ep3 b2: span:image:AbstractCache.getEntries `absent` 7.735 vs E `absent` 7.754; lead 0.019, margin 1.2e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0087 start + 0.0098 gap + 0]
  - ep4 b3: span:image:AbstractCache.getEntries `absent` 57.393 vs E `absent` 57.410; lead 0.017, margin 2.9e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0076 start + 0.0098 gap + 0]
- P4b auth-freeze r10 (candidates 1; paired differences ledger - sensor: mean -14.252 [-14.281, -14.171] s; availability-clock wins 0 of 4 evaluable):
  - ep1 b1: metric:auth:sys_psi_cpu `run3` 14.947 vs E `absent` 0.667; lead -14.280, margin 4.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: metric:auth:sys_psi_cpu `run3` 14.847 vs E `absent` 0.677; lead -14.171, margin 2.3e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:auth:sys_psi_cpu `run3` 14.914 vs E `absent` 0.638; lead -14.276, margin 2.8e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:auth:sys_psi_cpu `run3` 14.922 vs E `absent` 0.642; lead -14.281, margin 4.6e-05; tied 1 (win share 0/1); **not faster**
- P4b auth-freeze r1 (candidates 1; paired differences ledger - sensor: mean -13.084 [-13.345, -12.326] s; availability-clock wins 0 of 4 evaluable):
  - ep1 b1: metric:auth:sys_psi_cpu `median` 14.323 vs E `absent` 0.979; lead -13.345, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: metric:auth:sys_psi_cpu `run3` 14.539 vs E `absent` 1.200; lead -13.338, margin 2.2e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:auth:sys_psi_cpu `median` 13.956 vs E `absent` 1.630; lead -12.326, margin 7.3e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:auth:sys_psi_cpu `run3` 14.862 vs E `absent` 1.536; lead -13.326, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
- P4b auth-freeze r0.2 (candidates 2; paired differences ledger - sensor: mean -4.890 [-9.902, 0.107] s; availability-clock wins 1 of 4 evaluable):
  - ep1 b1: metric:auth:sys_io `spike` 3.943 vs E `absent` 4.050; lead 0.107, margin 2e-06; tied 1 (win share 1/1); **win**
  - ep2 b1: metric:auth:sys_io `spike` 10.179 vs E `absent` 0.277; lead -9.902, margin 2.5e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:auth:sys_io `spike` 8.300 vs E `absent` 3.409; lead -4.891, margin 2e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:auth:sys_io `spike` 7.024 vs E `absent` 2.149; lead -4.875, margin 2e-06; tied 1 (win share 0/1); **not faster**
- P4b auth-freeze r0.05 (candidates 1; paired differences ledger - sensor: mean 3.900 [0.134, 10.155] s; availability-clock wins 4 of 4 evaluable):
  - ep1 b1: metric:auth:sys_io `spike` 6.683 vs E `absent` 6.817; lead 0.134, margin 1.3e-06; tied 1 (win share 1/1); **win**
  - ep2 b1: metric:auth:sys_io `spike` 1.277 vs E `absent` 1.426; lead 0.149, margin 1.3e-06; tied 1 (win share 1/1); **win**
  - ep3 b2: metric:auth:sys_io `spike` 11.613 vs E `absent` 16.775; lead 5.161, margin 1.5e-06; tied 1 (win share 1/1); **win**
  - ep4 b3: metric:auth:sys_io `spike` 0.374 vs E `absent` 10.529; lead 10.155, margin 1.3e-06; tied 1 (win share 1/1); **win**
- P4b persistence-cpu-throttle r10 (candidates 7; paired differences ledger - sensor: mean -0.345 [-0.985, 0.113] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 0.589 vs E `median` 0.235; lead -0.354, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 1.183 vs E `run3` 1.296; lead 0.113, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep3 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 0.560 vs E `median` 0.408; lead -0.152, margin 1.4e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:persistence:UserRepository.getUserByName `spike` 1.278 vs E `median` 0.293; lead -0.985, margin 2.7e-05; tied 1 (win share 0/1); **not faster**
- P4b persistence-cpu-throttle r1 (candidates 7; paired differences ledger - sensor: mean -0.201 [-3.780, 1.938] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 1.009 vs E `spike` 1.029; lead 0.020, margin 1.4e-05; tied 1 (win share 1/1); **win**
  - ep2 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 0.881 vs E `median` 2.818; lead 1.938, margin 1.5e-05; tied 1 (win share 1/1); **win**
  - ep3 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 1.148 vs E `median` 2.165; lead 1.018, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep4 b3: span:persistence:CategoryEndpoint.listAllEntities `spike` 5.641 vs E `spike` 1.862; lead -3.780, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
- P4b persistence-cpu-throttle r0.2 (candidates 7; paired differences ledger - sensor: mean -18.553 [-56.698, -0.002] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 9.095 vs E `absent` 9.078; lead -0.017, margin 4.1e-06; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:persistence:CategoryEndpoint.listAllEntities `absent` 18.513 vs E `spike` 1.021; lead -17.492, margin 1.1e-05; tied 1 (win share 0/1); **not faster** (decision 57: the silence-ending observation names no request)
  - ep3 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 2.517 vs E `absent` 2.514; lead -0.002, margin 1e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:persistence:sys_io `—` — vs E `absent` 3.400; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4b persistence-cpu-throttle r0.05 (candidates 7; paired differences ledger - sensor: mean -0.312 [-0.613, 0.023] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 34.590 vs E `absent` 34.017; lead -0.572, margin 1.7e-06; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 5.424 vs E `spike` 5.446; lead 0.023, margin 9.5e-07; tied 1 (win share 1/1); **win**
  - ep3 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 8.367 vs E `absent` 7.754; lead -0.613, margin 1.2e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:persistence:CategoryEndpoint.listAllEntities `spike` 57.495 vs E `absent` 57.410; lead -0.085, margin 2.9e-06; tied 1 (win share 0/1); **not faster**

**Per harness** (decision 49 pools the sweep's episode with campaign B's three; V3_HARNESS_TAG_RULE; tags B, sweep). Episodes per class and rate: auth-freeze r0.05 B 3, sweep 1; auth-freeze r0.2 B 3, sweep 1; auth-freeze r1 B 3, sweep 1; auth-freeze r10 B 3, sweep 1; persistence-cpu-throttle r0.05 B 3, sweep 1; persistence-cpu-throttle r0.2 B 3, sweep 1; persistence-cpu-throttle r1 B 3, sweep 1; persistence-cpu-throttle r10 B 3, sweep 1.

- P1 holds per harness: B 12/12, sweep 4/4; P2 within the bound per harness: r10 B 3/3, sweep 1/1; r1 B 3/3, sweep 1/1; r0.2 B 3/3, sweep 1/1; r0.05 B 3/3, sweep 1/1.
- P4 optimistic P4a auth-freeze r0.05: wins / folds by the held-out episode's harness: B 2/3, sweep 1/1
- P4 optimistic P4a auth-freeze r0.2: wins / folds by the held-out episode's harness: B 1/3, sweep 1/1
- P4 optimistic P4a auth-freeze r1: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 optimistic P4a auth-freeze r10: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 optimistic P4a persistence-cpu-throttle r0.05: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 optimistic P4a persistence-cpu-throttle r0.2: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 optimistic P4a persistence-cpu-throttle r1: wins / folds by the held-out episode's harness: B 3/3, sweep 0/1
- P4 optimistic P4a persistence-cpu-throttle r10: wins / folds by the held-out episode's harness: B 1/3, sweep 0/1
- P4 optimistic P4b auth-freeze r0.05: wins / folds by the held-out episode's harness: B 3/3, sweep 1/1
- P4 optimistic P4b auth-freeze r0.2: wins / folds by the held-out episode's harness: B 0/3, sweep 1/1
- P4 optimistic P4b auth-freeze r1: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 optimistic P4b auth-freeze r10: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 optimistic P4b persistence-cpu-throttle r0.05: wins / folds by the held-out episode's harness: B 1/3, sweep 0/1
- P4 optimistic P4b persistence-cpu-throttle r0.2: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 optimistic P4b persistence-cpu-throttle r1: wins / folds by the held-out episode's harness: B 2/3, sweep 1/1
- P4 optimistic P4b persistence-cpu-throttle r10: wins / folds by the held-out episode's harness: B 1/3, sweep 0/1
- P4 primary P4a auth-freeze r0.05: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 primary P4a auth-freeze r0.2: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 primary P4a auth-freeze r1: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 primary P4a auth-freeze r10: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 primary P4a persistence-cpu-throttle r0.05: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 primary P4a persistence-cpu-throttle r0.2: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 primary P4a persistence-cpu-throttle r1: wins / folds by the held-out episode's harness: B 3/3, sweep 0/1
- P4 primary P4a persistence-cpu-throttle r10: wins / folds by the held-out episode's harness: B 1/3, sweep 0/1
- P4 primary P4b auth-freeze r0.05: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 primary P4b auth-freeze r0.2: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 primary P4b auth-freeze r1: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 primary P4b auth-freeze r10: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 primary P4b persistence-cpu-throttle r0.05: wins / folds by the held-out episode's harness: B 1/3, sweep 0/1
- P4 primary P4b persistence-cpu-throttle r0.2: wins / folds by the held-out episode's harness: B 0/3, sweep 0/1
- P4 primary P4b persistence-cpu-throttle r1: wins / folds by the held-out episode's harness: B 2/3, sweep 1/1
- P4 primary P4b persistence-cpu-throttle r10: wins / folds by the held-out episode's harness: B 1/3, sweep 0/1

**Beside the primary** (highest rate where P4 holds):

| verdict | calibrated (primary) | floor arm | <= 1 held-out alarm | optimistic bound (not evidence) |
|---|---|---|---|---|
| P4a auth-freeze | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | 0.05 |
| P4a persistence-cpu-throttle | 1 | 1 | none in {10, 1, 0.2, 0.05} | 1 |
| P4b auth-freeze | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | 0.05 |
| P4b persistence-cpu-throttle | 1 | 1 | none in {10, 1, 0.2, 0.05} | 1 |
| P4a withBC auth-freeze | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} |
| P4a withBC persistence-cpu-throttle | 1 | 1 | none in {10, 1, 0.2, 0.05} | 1 |
| P4b withBC auth-freeze | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | 0.05 |
| P4b withBC persistence-cpu-throttle | 1 | 1 | 0.2 | 1 |

## Out-of-sample check (decision 65, 67): calibrated detectors on --validation no-fault cells, no refit

Validation campaigns: `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1` (input digest `83ce4c47a9fb54110b673dc5676d6a41990261336dc88903af6e099a42daf3d1`). Not used: `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/auth-freeze-effect/b01-02-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/auth-freeze-effect/b01-04-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/auth-freeze-effect/b01-07-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/auth-freeze-effect/b01-11-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/auth-freeze-effect/b02-07-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/auth-freeze-effect/b02-08-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/auth-freeze-effect/b02-09-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/auth-freeze-effect/b02-10-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/auth-freeze-effect/b03-03-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/auth-freeze-effect/b03-09-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/auth-freeze-effect/b03-10-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/auth-freeze-effect/b03-11-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/persistence-cpu-throttle-effect/b01-01-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/persistence-cpu-throttle-effect/b01-03-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/persistence-cpu-throttle-effect/b01-09-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/persistence-cpu-throttle-effect/b01-10-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/persistence-cpu-throttle-effect/b02-01-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/persistence-cpu-throttle-effect/b02-02-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/persistence-cpu-throttle-effect/b02-03-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/persistence-cpu-throttle-effect/b02-04-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/persistence-cpu-throttle-effect/b03-02-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/persistence-cpu-throttle-effect/b03-04-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/persistence-cpu-throttle-effect/b03-05-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastoreb1-evidence/x/teastore-traffic-sweep-b-v1/runs/persistence-cpu-throttle-effect/b03-07-full` (a fault cell (validation uses no-fault cells only)).

- r10: 3 cells, 0.150 h (limit of this check: 20.0/h for 0 alarms); rules alarming 14 of 589 calibrated: `metric:auth:sys_memory/spike 8`, `metric:image:sys_memory/spike 7`, `metric:image:sys_memory/median 3`, `metric:image:sys_memory/run3 3`, `metric:auth:sys_memory/run3 2`, `span:auth:ShaSecurityProvider.getKeyProvider/run3 2`, `span:persistence:CategoryEndpoint.listAllEntities/spike 2`, `metric:auth:sys_io/spike 1`, `metric:persistence:sys_cpu/spike 1`, `metric:persistence:sys_io/spike 1`, `metric:registry:sys_memory/spike 1`, `metric:webui:sys_psi_cpu/spike 1`, `span:auth:ShaSecurityProvider.blobToString/run3 1`, `span:persistence:PersistenceCategory.getId/run3 1`; sensors alarming 11 of 464 placeable; all placeable sensors' union 33 (220.0/h [294.2], 0.15 of 0.15 h)
  - P4a auth-freeze-effect r10: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4a persistence-cpu-throttle-effect r10: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4b auth-freeze-effect r10: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4b persistence-cpu-throttle-effect r10: 2 (13.3/h [42.0], 0.15 of 0.15 h)
- r1: 3 cells, 0.150 h (limit of this check: 20.0/h for 0 alarms); rules alarming 11 of 601 calibrated: `span:auth:ShaSecurityProvider.getKeyProvider/median 22`, `span:auth:ShaSecurityProvider.getKeyProvider/run3 17`, `metric:image:sys_cpu/spike 2`, `metric:image:sys_memory/spike 2`, `metric:image:sys_io/spike 1`, `metric:image:sys_memory/median 1`, `metric:rabbitmq:sys_memory/run3 1`, `metric:webui:sys_psi_io/spike 1`, `span:auth:BCryptProvider.checkPassword/spike 1`, `span:auth:ShaSecurityProvider.getKeyProvider/spike 1`, `span:auth:ShaSecurityProvider.getSha512/run3 1`; sensors alarming 8 of 463 placeable; all placeable sensors' union 32 (213.3/h [286.5], 0.15 of 0.15 h)
  - P4a auth-freeze-effect r1: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4a persistence-cpu-throttle-effect r1: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4b auth-freeze-effect r1: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4b persistence-cpu-throttle-effect r1: 0 (0.0/h [20.0], 0.15 of 0.15 h)
- r0.2: 3 cells, 0.150 h (limit of this check: 20.0/h for 0 alarms); rules alarming 6 of 594 calibrated: `metric:persistence:sys_psi_cpu/spike 1`, `metric:webui:sys_psi_io/spike 1`, `span:auth:AuthUserActionsRest.login/spike 1`, `span:auth:ShaSecurityProvider.getSha512/spike 1`, `span:persistence:UserEndpoint.findById/spike 1`, `span:persistence:UserRepository.getUserByName/spike 1`; sensors alarming 6 of 461 placeable; all placeable sensors' union 14 (93.3/h [145.9], 0.15 of 0.15 h)
  - P4a auth-freeze-effect r0.2: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4a persistence-cpu-throttle-effect r0.2: 1 (6.7/h [31.6], 0.15 of 0.15 h)
  - P4b auth-freeze-effect r0.2: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4b persistence-cpu-throttle-effect r0.2: 0 (0.0/h [20.0], 0.15 of 0.15 h)
- r0.05: 3 cells, 0.150 h (limit of this check: 20.0/h for 0 alarms); rules alarming 12 of 594 calibrated: `metric:webui:sys_memory/spike 20`, `metric:persistence:sys_io/median 11`, `metric:webui:sys_memory/median 10`, `metric:webui:sys_memory/run3 6`, `metric:recommender:sys_psi_cpu/median 2`, `metric:registry:sys_psi_cpu/spike 2`, `metric:recommender:sys_psi_cpu/run3 1`, `metric:recommender:sys_psi_io/spike 1`, `span:image:AbstractCache.getEntries/median 1`, `span:image:AbstractCache.getEntries/spike 1`, `span:persistence:PersistenceUser.getId/spike 1`, `span:webui:IndexServlet.handleGETRequest/spike 1`; sensors alarming 8 of 461 placeable; all placeable sensors' union 49 (326.7/h [414.5], 0.15 of 0.15 h)
  - P4a auth-freeze-effect r0.05: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4a persistence-cpu-throttle-effect r0.05: 2 (13.3/h [42.0], 0.15 of 0.15 h)
  - P4b persistence-cpu-throttle-effect r0.05: 0 (0.0/h [20.0], 0.15 of 0.15 h)

## Primary outcome: time to detection at the calibrated values, misses charged at the hold end

Detected k/n · median [min-max] · **mean over all n** (with BC catches), then without BC. `—` = channel missing.

| class | rate | n | E | E no BC | L | L no BC | M | M no BC | S | S no BC | T | T no BC | L:own | L:own no BC | M:own | M:own no BC | S:own | S:own no BC | T:own | T:own no BC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| auth-freeze | 10 | 4 | 4/4 · 0.65 [0.64–0.68] · **0.66** | (= E) | 4/4 · 10.15 [10.09–10.26] · **10.16** | 4/4 · 16.52 [16.44–16.64] · **16.53** | — | — | 4/4 · 14.92 [14.85–14.95] · **14.91** | 4/4 · 14.92 [14.85–14.95] · **14.91** | 4/4 · 0.47 [0.45–0.50] · **0.47** | 4/4 · 10.45 [10.35–11.43] · **10.67** | 0/4 · **60.24** | 0/4 · **60.24** | — | — | 4/4 · 4.92 [4.85–4.94] · **4.91** | 4/4 · 14.92 [14.85–14.95] · **14.91** | 4/4 · 0.47 [0.45–0.49] · **0.47** | 0/4 · **60.24** |
| auth-freeze | 1 | 4 | 4/4 · 1.37 [0.98–1.63] · **1.34** | (= E) | 4/4 · 11.50 [10.07–11.75] · **11.20** | 4/4 · 30.38 [29.05–30.98] · **30.20** | — | — | 4/4 · 14.43 [13.96–14.86] · **14.42** | 4/4 · 24.14 [14.54–24.86] · **21.92** | 4/4 · 1.30 [0.92–1.55] · **1.27** | 4/4 · 19.48 [19.25–19.54] · **19.43** | 0/4 · **60.24** | 0/4 · **60.24** | — | — | 4/4 · 14.43 [13.96–14.86] · **14.42** | 4/4 · 14.43 [13.96–14.86] · **14.42** | 4/4 · 1.33 [0.94–1.59] · **1.30** | 0/4 · **60.24** |
| auth-freeze | 0.2 | 4 | 4/4 · 2.78 [0.28–4.05] · **2.47** | (= E) | 4/4 · 10.40 [9.89–11.67] · **10.59** | 4/4 · 28.69 [27.49–31.27] · **29.03** | — | — | 4/4 · 28.62 [22.03–30.17] · **27.36** | 4/4 · 28.62 [22.03–30.17] · **27.36** | 4/4 · 2.77 [0.26–4.03] · **2.46** | 4/4 · 21.89 [19.52–23.36] · **21.67** | 0/4 · **60.25** | 0/4 · **60.25** | — | — | 4/4 · 12.66 [10.18–13.94] · **12.36** | 4/4 · 12.66 [10.18–13.94] · **12.36** | 4/4 · 2.75 [0.25–4.02] · **2.45** | 0/4 · **60.25** |
| auth-freeze | 0.05 | 4 | 4/4 · 8.67 [1.43–16.77] · **8.89** | (= E) | 4/4 · 9.81 [9.07–11.60] · **10.07** | 4/4 · 23.19 [13.25–29.80] · **22.36** | — | — | 4/4 · 21.44 [10.37–31.68] · **21.23** | 4/4 · 21.44 [10.37–31.68] · **21.23** | 4/4 · 8.65 [1.41–16.74] · **8.86** | 3/4 · 25.89 [20.48–29.79] · **34.10** | 0/4 · **60.23** | 0/4 · **60.23** | — | — | 0/4 · **60.23** | 0/4 · **60.23** | 4/4 · 8.59 [1.35–16.68] · **8.80** | 0/4 · **60.23** |
| persistence-cpu-throttle | 10 | 4 | 4/4 · 0.35 [0.23–1.30] · **0.56** | (= E) | 4/4 · 11.49 [10.28–13.09] · **11.59** | 4/4 · 11.49 [10.28–13.09] · **11.59** | — | — | 4/4 · 14.88 [10.00–14.94] · **13.68** | 4/4 · 14.88 [10.00–14.94] · **13.68** | 4/4 · 0.29 [0.21–1.29] · **0.52** | 4/4 · 0.29 [0.21–1.29] · **0.52** | 0/4 · **60.11** | 0/4 · **60.11** | — | — | 4/4 · 4.92 [4.87–5.00] · **4.93** | 1/4 · 59.87 · **60.05** | 4/4 · 0.42 [0.29–1.18] · **0.58** | 4/4 · 0.42 [0.29–1.18] · **0.58** |
| persistence-cpu-throttle | 1 | 4 | 4/4 · 2.01 [1.03–2.82] · **1.97** | (= E) | 2/4 · 36.68 [30.44–42.92] · **48.40** | 2/4 · 36.92 [30.91–42.92] · **48.52** | — | — | 2/4 · 27.32 [14.86–39.78] · **43.72** | 2/4 · 27.32 [14.86–39.78] · **43.72** | 4/4 · 2.49 [1.66–2.89] · **2.38** | 4/4 · 2.49 [1.66–2.89] · **2.38** | 0/4 · **60.12** | 0/4 · **60.12** | — | — | 4/4 · 4.63 [4.04–4.86] · **4.54** | 1/4 · 4.86 · **46.30** | 4/4 · 1.08 [0.88–4.64] · **1.92** | 4/4 · 1.08 [0.88–4.64] · **1.92** |
| persistence-cpu-throttle | 0.2 | 4 | 4/4 · 2.96 [1.02–9.08] · **4.00** | (= E) | 1/4 · 55.16 · **58.88** | 1/4 · 55.68 · **59.01** | — | — | 2/4 · 12.45 [10.93–13.97] · **36.28** | 2/4 · 12.45 [10.93–13.97] · **36.28** | 4/4 · 2.93 [0.97–9.01] · **3.96** | 4/4 · 2.93 [0.97–9.01] · **3.96** | 0/4 · **60.12** | 0/4 · **60.12** | — | — | 4/4 · 2.86 [0.93–3.97] · **2.65** | 0/4 · **60.12** | 4/4 · 6.22 [2.52–18.46] · **8.36** | 4/4 · 6.22 [2.52–18.46] · **8.36** |
| persistence-cpu-throttle | 0.05 | 4 | 4/4 · 20.89 [5.45–57.41] · **26.16** | (= E) | 1/4 · 47.98 · **57.08** | 1/4 · 48.21 · **57.14** | — | — | 0/4 · **60.12** | 0/4 · **60.12** | 4/4 · 20.81 [5.44–57.39] · **26.11** | 4/4 · 20.81 [5.44–57.39] · **26.11** | 0/4 · **60.12** | 0/4 · **60.12** | — | — | 4/4 · 3.24 [2.28–5.32] · **3.52** | 2/4 · 31.47 [10.32–52.61] · **45.79** | 4/4 · 21.03 [5.42–57.50] · **26.24** | 4/4 · 21.03 [5.42–57.50] · **26.24** |

## P1 detail (H4, decision 54)

- r10 b1: interval 0.201 s (intervention sweep.commandStamps onsetCommandReturnedMonotonicOffsetSeconds (the cell keeps no Docker events: [command issued, command returned])); expected [14.933, 15.233] +- 0.051 s; observed 11.804; holds via **error answer before the timeout (declared alternative)**
- r10 b1: interval 0.183 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.033, 15.233] +- 0.052 s; observed 13.094; holds via **error answer before the timeout (declared alternative)**
- r10 b2: interval 0.187 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [14.999, 15.200] +- 0.052 s; observed 11.825; holds via **error answer before the timeout (declared alternative)**
- r10 b3: interval 0.169 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.008, 15.208] +- 0.053 s; observed 11.931; holds via **error answer before the timeout (declared alternative)**
- r1 b1: interval 0.180 s (intervention sweep.commandStamps onsetCommandReturnedMonotonicOffsetSeconds (the cell keeps no Docker events: [command issued, command returned])); expected [15.310, 15.310] +- 0.062 s; observed 15.327; holds via **timeout interval**
- r1 b1: interval 0.179 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.525, 15.525] +- 0.066 s; observed 15.541; holds via **timeout interval**
- r1 b2: interval 0.169 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [14.942, 15.942] +- 0.063 s; observed 15.960; holds via **timeout interval**
- r1 b3: interval 0.161 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.848, 15.848] +- 0.067 s; observed 15.863; holds via **timeout interval**
- r0.2 b1: interval 0.182 s (intervention sweep.commandStamps onsetCommandReturnedMonotonicOffsetSeconds (the cell keeps no Docker events: [command issued, command returned])); expected [18.932, 18.932] +- 0.075 s; observed 18.950; holds via **timeout interval**
- r0.2 b1: interval 0.179 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.167, 15.167] +- 0.059 s; observed 15.184; holds via **timeout interval**
- r0.2 b2: interval 0.167 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [18.293, 18.293] +- 0.073 s; observed 18.311; holds via **timeout interval**
- r0.2 b3: interval 0.194 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [17.023, 17.023] +- 0.078 s; observed 17.041; holds via **timeout interval**
- r0.05 b1: interval 0.177 s (intervention sweep.commandStamps onsetCommandReturnedMonotonicOffsetSeconds (the cell keeps no Docker events: [command issued, command returned])); expected [21.686, 21.686] +- 0.083 s; observed 21.702; holds via **timeout interval**
- r0.05 b1: interval 0.185 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [16.282, 16.282] +- 0.085 s; observed 16.296; holds via **timeout interval**
- r0.05 b2: interval 0.145 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [31.619, 31.619] +- 0.083 s; observed 17.903; holds via **error answer before the timeout (declared alternative)**
- r0.05 b3: interval 0.139 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [25.379, 25.379] +- 0.078 s; observed 25.384; holds via **timeout interval**

- The ledger's calibrated `absent` against the client timeout: r10 login-only-v1: calibrated m 1.5 g 0.493 s vs timeout 15 s; `absent` before the first `failed` in 4/4 pause episodes; r1 login-only-v1: calibrated m 1.5 g 1.617 s vs timeout 15 s; `absent` before the first `failed` in 4/4 pause episodes; r0.2 login-only-v1: calibrated m 1 g 5.039 s vs timeout 15 s; `absent` before the first `failed` in 4/4 pause episodes; r0.05 login-only-v1: calibrated m 1 g 20.066 s vs timeout 15 s; `absent` before the first `failed` in 4/4 pause episodes.

## Exposure (H5): recorded, the objective unchanged

Route call path: auth, persistence, webui. Episodes with no request started in the fault window: 0 of 32. Never-exposed sensors: 265.

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
