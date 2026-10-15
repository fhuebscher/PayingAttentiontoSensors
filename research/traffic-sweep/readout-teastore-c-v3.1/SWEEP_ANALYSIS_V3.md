# Traffic sweep, TeaStore: analysis v3 (v3.1), exploratory, not frozen (every cell of this system was read under v2.4 before v3 was written) (teastore-traffic-sweep-v1 + teastore-traffic-sweep-b-v1 + teastore-quiet-calibration-v1 + teastore-quiet-calibration-v1 + teastore-quiet-calibration-v1 + teastore)

**Exploratory, not frozen.** Protocol rounds 15 and 17 (decisions 61-65 as amended by 67) on v2.4's readers and rules; every cell read here was read under v2.4 first. **Scope: instance** (one SUT, one host). `—` = absent or not evaluable, never 0. Each (sensor, rule) is calibrated per rate by the zero-held-out-alarm selection; **no false-alarm figure here is that selection's own zero**: every count of false alarms is the honest nested leave-one-cell-out count (V3_NESTED_RULE), with its exact 95 % bound.

Binding documents and inputs: research/PROTOCOL_DRAFT_20261002.md round 15 (decisions 61-65, 252cfcd); research/protocol/ANALYSIS_V3_DESIGN.md (252cfcd); research/traffic-sweep/SYNTHESIS_V2_4.md; research/protocol/parameters_v3.json (decision 37); research/traffic-sweep/DECLARATION_TEASTORE.md (c9f072b); research/traffic-sweep/AMENDMENT_TEASTORE_1.md (bbbd80b); research/traffic-sweep/AMENDMENT_TEASTORE_2.md (b840353); research/traffic-sweep/DECLARATION_QUIET_TEASTORE.md (fc64a6d); research/protocol/METHODOLOGY_HARDENING.md (H1-H11); research/PROTOCOL_DRAFT_20261002.md rounds 7-14 (decisions 26-60; decision 57 = d126589, round 13 = 6162c37, round 14 = c17f6a6); harness observability-placement-runtime-teastore-protocol 91c4967 (the cell writer and validator); research/protocol/parameters.json (decision 37).

Analysis: `research/detection-time/sweep_analysis_v3.py` v3 (sha256 `2e7ec5c387fa906a02026f0d1a5212b974f17751c24f76526a1d8418b2fd4fdd`) on v2.4 `sweep_analysis_v2.py` (sha256 `075c43e5870170c8b59cdbe1a970b56dc03920d67514027b9a95e5de38d962e9`), parameters.json `7447b492abf64f42ebaf547a640c84929ac15b59ebc1e495d5082f279373fc68`, parameters_v3.json `212830bec3e6669bc211d5cffa48d61fa3bf0f6d4dd5ceaf79d3e2bcc7c4d000`, HEAD `fdbdb16bc30fc8ffb0b631bb133d49871ed17e24`, Python 3.13.12.

## Outputs that are — by construction

- family M (primary and secondary columns, operating point, P4 candidates): docker-stats samples (resources.json) are written in no-fault cells only (the frozen no-fault-cost path, DECLARATION_TEASTORE.md Regimes): no fault episode has M, so it is not read (FAMILY_CHANNELS).
- availability-clock P4 verdict for family T: no measured collector receive stamp (AVAILABILITY_SOURCES, decision 43).
- P3 (every fault): no family is traffic-independent by mechanism (H11).
- harness provenance of 105 cell(s): receipt source.frameworkCommit `3b4a513ff3c4b00b65131dbc82ba1b472d1c0548`, `bb3717e8adeeaa05a45fd8e587cee481da206ac7`, `bbb6b1165410be5bd4eb304b56c4eac9490310d1` is not listed in HARNESS_PROVENANCE (F5): read, flagged.
- Docker pause event as the onset interval's upper bound (H4) in 4 of 28 pause episodes: those cells carry no freeze-event source (V3_FREEZE_EVENTS_RULE): the interval is [command issued, command returned], v2.4's.
- a false-alarm figure from the zero-alarm selection itself: never printed (decision 67): the selected value has 0 held-out alarms on the cells it was chosen on by construction; every false-alarm count below is the honest nested one.

## What was read

Campaigns pooled (H1; decision 68: quiet runs A and A2 pool with the sweep):

- `tmp/teastoresweep2-evidence/x/teastore-traffic-sweep-v1`: 12 valid of 12 (auth-freeze 4, no-fault-cost 4, persistence-cpu-throttle 4)
- `tmp/teastoreb1-evidence/faultview/x/teastore-traffic-sweep-b-v1`: 24 valid of 24 (auth-freeze 12, persistence-cpu-throttle 12)
- `tmp/teastorequiet1-evidence/x/teastore-quiet-calibration-v1`: 40 valid of 40 (no-fault-cost 40)
- `tmp/teastorequiet2-evidence/x/teastore-quiet-calibration-v1`: 17 valid of 18 (no-fault-cost 17)
- `tmp/teastorequiet2r1-evidence/x/teastore-quiet-calibration-v1`: 40 valid of 40 (no-fault-cost 40)
- `tmp/c-fault-copy/teastore`: 24 valid of 24 (auth-freeze 12, persistence-cpu-throttle 12)

| class | r10 valid/found | r1 valid/found | r0.2 valid/found | r0.05 valid/found |
|---|---|---|---|---|
| no-fault-cost | 25/25 | 26/26 | 25/25 | 25/25 |
| auth-freeze | 7/7 | 7/7 | 7/7 | 7/7 |
| persistence-cpu-throttle | 7/7 | 7/7 | 7/7 | 7/7 |

Cells not scored: `tmp/teastorequiet2-evidence/x/teastore-quiet-calibration-v1/runs/no-fault-cost/b05-02-full.blocked-evidence` (blocked evidence (the producer refused the cell)).

Provenance: harness commit `0588a412ea7355f0aaa143b5468e8c4b9b7f0943, 3b4a513ff3c4b00b65131dbc82ba1b472d1c0548, 91c4967f2d9c12a25eeeaf097f998856c377ca7f, bb3717e8adeeaa05a45fd8e587cee481da206ac7, bbb6b1165410be5bd4eb304b56c4eac9490310d1`; input digest `14a57765231c7a666cf4fde46bc79f92abb6fc1524c5131676748509a0875707` over 1312 files (v2.4's file set plus docker-events.json[l]).

H4 freeze record per harness and status (V3_FREEZE_EVENTS_RULE; decision 69: a missing or contradictory record keeps the sweep's bound and is counted): B: recorded (throttle: command and readback stamps; v2.4's bound kept) 24, used 24; sweep: not recorded (sweep harness) 8; reasons: none.

Reader statistics over the valid cells (F11; a drop is counted, never silent): bridgeMappings 75082; bridgeTokensWithSeveralTraces 0; bridgeTracesWithSeveralTokens 0; bridgeRowsDropped 0; tracesWithoutToken 76837; probeTracesExcluded 1286; probeSpansExcluded 20577; spansIncomplete 0; spansUnusable 0; duplicateSpans 45433; journeysWithoutStart 0; samplePairsSkipped 0; logRecordsUntimed 0; composeCliLines 0.

## Calibration per (sensor, rule) on the no-fault cells (decisions 61-63, 67)

Each armed (sensor, rule) takes the smallest grid value with zero held-out alarms over the rate's no-fault cells, each scored leave-one-cell-out (v2.4's fit, H1; class-independent). Level rules: K_GRID (<= 100; K = 100 flagged at grid edge), then the range fallback (discrete in effect; up-only for spans and the ledger; may apply where MAD = 0, decision 52 kept for K); `absent`: m x G on m in {1, 1.5, 2, 3, 5}, G including the censored silences of cells with records; an `absent` whose gap exceeds the shortest hold (60.097 s) is **inert**; `appear` per stream; the ledger's `failed` exempt. **honest** = the nested count (each held-out cell at the value re-selected without it), the false-alarm figure; its rate per hour of no-fault time T.

| rate | no-fault cells | T (h) | rules calibrated / dropped / inert / unarmed | at grid edge | range (of them MAD = 0) | sensors placeable / appear-only / not (L, M, S, T) | dof | E `failed` in no-fault (exempt) | calibrated rules: median folds armed of the rate's cells · out of the detector in every nested fold · honest — (no nested evidence) | placeable sensors with CELF cost — |
|---|---|---|---|---|---|---|---|---|---|---|
| r10 | 25 | 1.250 | 587 / 21 / 0 / 460 | 2 | 38 (27) | 60 / 404 / 8 | 183 | login-only-v1 0 | 25 of 25 · 0 · 0 | 9 |
| r1 | 26 | 1.300 | 595 / 12 / 0 / 459 | 1 | 43 (30) | 60 / 403 / 8 | 192 | login-only-v1 0 | 26 of 26 · 0 · 0 | 8 |
| r0.2 | 25 | 1.250 | 592 / 16 / 0 / 460 | 0 | 37 (29) | 60 / 404 / 8 | 188 | login-only-v1 0 | 25 of 25 · 0 · 0 | 10 |
| r0.05 | 25 | 1.250 | 591 / 14 / 0 / 454 | 0 | 36 (28) | 60 / 401 / 8 | 190 | login-only-v1 0 | 25 of 25 · 0 · 0 | 6 |

Per family and rule (primary): calibrated / dropped / inert / unarmed.

| rate | family | appear | absent | spike | run3 | median |
|---|---|---|---|---|---|---|
| r10 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r10 | L | 400 / 0 / 0 / 0 | 0 / 0 / 0 / 400 | — | — | — |
| r10 | S | — | — | 27 / 13 / 0 / 8 | 40 / 0 / 0 / 8 | 40 / 0 / 0 / 8 |
| r10 | T | 4 / 0 / 0 / 20 | 20 / 0 / 0 / 4 | 12 / 8 / 0 / 4 | 20 / 0 / 0 / 4 | 20 / 0 / 0 / 4 |
| r1 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r1 | L | 399 / 0 / 0 / 0 | 0 / 0 / 0 / 399 | — | — | — |
| r1 | S | — | — | 34 / 6 / 0 / 8 | 40 / 0 / 0 / 8 | 40 / 0 / 0 / 8 |
| r1 | T | 4 / 0 / 0 / 20 | 20 / 0 / 0 / 4 | 14 / 6 / 0 / 4 | 20 / 0 / 0 / 4 | 20 / 0 / 0 / 4 |
| r0.2 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r0.2 | L | 400 / 0 / 0 / 0 | 0 / 0 / 0 / 400 | — | — | — |
| r0.2 | S | — | — | 29 / 11 / 0 / 8 | 40 / 0 / 0 / 8 | 40 / 0 / 0 / 8 |
| r0.2 | T | 4 / 0 / 0 / 20 | 20 / 0 / 0 / 4 | 15 / 5 / 0 / 4 | 20 / 0 / 0 / 4 | 20 / 0 / 0 / 4 |
| r0.05 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r0.05 | L | 398 / 0 / 0 / 0 | 0 / 0 / 0 / 398 | — | — | — |
| r0.05 | S | — | — | 28 / 12 / 0 / 8 | 40 / 0 / 0 / 8 | 40 / 0 / 0 / 8 |
| r0.05 | T | 3 / 0 / 0 / 20 | 20 / 0 / 0 / 3 | 18 / 2 / 0 / 3 | 20 / 0 / 0 / 3 | 20 / 0 / 0 / 3 |

**The ledger E** per rate (route; `failed` **exempt**, decision 63: never calibrated, always compared; its no-fault count is reported):

- r10: `absent` calibrated (m 1, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 16, honest 0).
- r1: `absent` calibrated (m 1.5, honest 1); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 16, honest 1).
- r0.2: `absent` calibrated (m 1.5, honest 1); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 5, honest 1).
- r0.05: `absent` calibrated (m 1, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 3, honest 1).
- E's catching rule in the episodes (primary): auth-freeze r0.05: `absent` 7; auth-freeze r0.2: `absent` 7; auth-freeze r1: `absent` 7; auth-freeze r10: `absent` 7; persistence-cpu-throttle r0.05: `absent` 6, `spike` 1; persistence-cpu-throttle r0.2: `absent` 1, `spike` 6; persistence-cpu-throttle r1: `median` 3, `spike` 4; persistence-cpu-throttle r10: `median` 3, `run3` 2, `spike` 2.

**Dropped (sensor, rule) pairs** (held-out alarms at the last grid value; honest count beside), primary:

- r10 (21): `metric:auth:sys_psi_io/spike` 2 (honest —), `metric:auth:sys_io/spike` 1 (honest 1), `metric:db:sys_psi_cpu/spike` 1 (honest —), `metric:image:sys_io/spike` 1 (honest —), `metric:image:sys_psi_io/spike` 1 (honest —), `metric:persistence:sys_io/spike` 1 (honest 1), `metric:persistence:sys_psi_io/spike` 1 (honest —), `metric:rabbitmq:sys_psi_io/spike` 1 (honest 1), `metric:recommender:sys_io/spike` 1 (honest —), `metric:recommender:sys_psi_io/spike` 1 (honest 1), `metric:registry:sys_psi_io/spike` 1 (honest —), `metric:webui:sys_io/spike` 1 (honest —), `metric:webui:sys_psi_io/spike` 1 (honest —), `span:auth:RandomSessionIdGenerator.getSessionId/spike` 1 (honest 1), `span:auth:ShaSecurityProvider.getKeyProvider/spike` 1 (honest —), `span:image:AbstractCache.getEntries/spike` 1 (honest —), `span:image:AbstractCache.loadData/spike` 1 (honest —), `span:image:ImageProvider.getImageFor/spike` 1 (honest —), `span:persistence:CategoryEndpoint.listAllEntities/spike` 1 (honest —), `span:persistence:PersistenceCategory.getId/spike` 1 (honest —), `span:persistence:PersistenceUser.getId/spike` 1 (honest —)
- r1 (12): `metric:auth:sys_psi_io/spike` 1 (honest —), `metric:image:sys_io/spike` 1 (honest —), `metric:persistence:sys_psi_io/spike` 1 (honest —), `metric:rabbitmq:sys_psi_io/spike` 1 (honest —), `metric:registry:sys_psi_io/spike` 1 (honest 1), `metric:webui:sys_psi_io/spike` 1 (honest —), `span:auth:ShaSecurityProvider.getKeyProvider/spike` 1 (honest 1), `span:auth:ShaSecurityProvider.getSha512/spike` 1 (honest 1), `span:image:AbstractCache.loadData/spike` 1 (honest 1), `span:persistence:PersistenceCategory.getId/spike` 1 (honest —), `span:persistence:UserEndpoint.findById/spike` 1 (honest 1), `span:persistence:UserRepository.getUserByName/spike` 1 (honest 1)
- r0.2 (16): `metric:auth:sys_io/spike` 1 (honest 1), `metric:image:sys_io/spike` 1 (honest —), `metric:image:sys_psi_io/spike` 1 (honest 1), `metric:persistence:sys_io/spike` 1 (honest 1), `metric:persistence:sys_psi_io/spike` 1 (honest —), `metric:rabbitmq:sys_psi_io/spike` 1 (honest —), `metric:recommender:sys_io/spike` 1 (honest 1), `metric:recommender:sys_psi_io/spike` 1 (honest 1), `metric:registry:sys_psi_io/spike` 1 (honest —), `metric:webui:sys_io/spike` 1 (honest 1), `metric:webui:sys_psi_io/spike` 1 (honest —), `span:auth:RandomSessionIdGenerator.getSessionId/spike` 1 (honest 1), `span:auth:ShaSecurityProvider.getKeyProvider/spike` 1 (honest 1), `span:persistence:PersistenceCategory.getId/spike` 1 (honest —), `span:persistence:UserEndpoint.findById/spike` 1 (honest 1), `span:persistence:UserRepository.getUserByName/spike` 1 (honest 1)
- r0.05 (14): `metric:auth:sys_io/spike` 1 (honest —), `metric:auth:sys_psi_io/spike` 1 (honest 1), `metric:image:sys_io/spike` 1 (honest —), `metric:image:sys_psi_io/spike` 1 (honest —), `metric:persistence:sys_io/spike` 1 (honest —), `metric:persistence:sys_psi_io/spike` 1 (honest —), `metric:rabbitmq:sys_io/spike` 1 (honest —), `metric:recommender:sys_io/spike` 1 (honest —), `metric:recommender:sys_psi_io/spike` 1 (honest 1), `metric:registry:sys_psi_io/spike` 1 (honest —), `metric:webui:sys_io/spike` 1 (honest —), `metric:webui:sys_psi_io/spike` 1 (honest —), `span:auth:RandomSessionIdGenerator.getSessionId/spike` 1 (honest 1), `span:persistence:PersistenceCategory.getId/spike` 1 (honest —)

**Inert** (calibrated by the selection, but the gap exceeds the hold; not placeable), **at grid edge** (K = 100) and **appear-only** sensors (placeable through `appear` alone, listed apart), primary:

- r10: inert 0: none; at grid edge 2: `span:image:ImageProviderEndpoint.getWebUIImages/spike`, `span:persistence:UserRepository.getUserByName/spike`; appear-only 404: `log:auth:059f77b5fee4`, `log:auth:0788a45dbb86`, `log:auth:0ae227c4f15d`, `log:auth:13e7be34fb70`, `log:auth:16e888bf8922`, `log:auth:16f327e6bd4d`, `log:auth:2d7f16630b87`, `log:auth:2ff20a342a41`, `log:auth:319b41b82d9b`, `log:auth:3219d9dbbaed`, `log:auth:35563463c928`, `log:auth:35873ee1cc7e`, `log:auth:3917ffeac5ec`, `log:auth:3b1fa69c3451`, `log:auth:3f00555a765d`, `log:auth:407989c51698`, `log:auth:4a79ac521b28`, `log:auth:4de8468724c7`, `log:auth:52a075c95ff9`, `log:auth:56bcc1a07d39`, `log:auth:56c309f6427c`, `log:auth:6c19cf62298a`, `log:auth:6e7a7f83a9e6`, `log:auth:7197cbb5d81b`, `log:auth:72ae3fa150b5`, `log:auth:7568b9fca9ad`, `log:auth:7877eab35e98`, `log:auth:7b327c4594ff`, `log:auth:811e1f658b4b`, `log:auth:8733ab2f4543`, `log:auth:87614f556af3`, `log:auth:8b277994d6dd`, `log:auth:8ddb5025ba7f`, `log:auth:8eb94ac35bf9`, `log:auth:955560e889b3`, `log:auth:96ea0f608ef2`, `log:auth:9c6795a8c551`, `log:auth:a0105883ccdd`, `log:auth:a07c7bcc6c3d`, `log:auth:a59061884c18` (+364 more in the JSON).
- r1: inert 0: none; at grid edge 1: `span:persistence:PersistenceUser.getId/spike`; appear-only 403: `log:auth:059f77b5fee4`, `log:auth:0788a45dbb86`, `log:auth:0ae227c4f15d`, `log:auth:13e7be34fb70`, `log:auth:16e888bf8922`, `log:auth:16f327e6bd4d`, `log:auth:2d7f16630b87`, `log:auth:2ff20a342a41`, `log:auth:319b41b82d9b`, `log:auth:3219d9dbbaed`, `log:auth:35563463c928`, `log:auth:35873ee1cc7e`, `log:auth:3917ffeac5ec`, `log:auth:3b1fa69c3451`, `log:auth:3f00555a765d`, `log:auth:407989c51698`, `log:auth:4a79ac521b28`, `log:auth:4de8468724c7`, `log:auth:52a075c95ff9`, `log:auth:56bcc1a07d39`, `log:auth:56c309f6427c`, `log:auth:6c19cf62298a`, `log:auth:6e7a7f83a9e6`, `log:auth:7197cbb5d81b`, `log:auth:72ae3fa150b5`, `log:auth:7568b9fca9ad`, `log:auth:7877eab35e98`, `log:auth:7b327c4594ff`, `log:auth:811e1f658b4b`, `log:auth:8733ab2f4543`, `log:auth:87614f556af3`, `log:auth:8b277994d6dd`, `log:auth:8ddb5025ba7f`, `log:auth:8eb94ac35bf9`, `log:auth:955560e889b3`, `log:auth:96ea0f608ef2`, `log:auth:9c6795a8c551`, `log:auth:a0105883ccdd`, `log:auth:a07c7bcc6c3d`, `log:auth:a59061884c18` (+363 more in the JSON).
- r0.2: inert 0: none; at grid edge 0: none; appear-only 404: `log:auth:059f77b5fee4`, `log:auth:0788a45dbb86`, `log:auth:0ae227c4f15d`, `log:auth:13e7be34fb70`, `log:auth:16e888bf8922`, `log:auth:16f327e6bd4d`, `log:auth:2d7f16630b87`, `log:auth:2ff20a342a41`, `log:auth:319b41b82d9b`, `log:auth:3219d9dbbaed`, `log:auth:35563463c928`, `log:auth:35873ee1cc7e`, `log:auth:3917ffeac5ec`, `log:auth:3b1fa69c3451`, `log:auth:3f00555a765d`, `log:auth:407989c51698`, `log:auth:4a79ac521b28`, `log:auth:4de8468724c7`, `log:auth:52a075c95ff9`, `log:auth:56bcc1a07d39`, `log:auth:56c309f6427c`, `log:auth:686c713da873`, `log:auth:6c19cf62298a`, `log:auth:6e7a7f83a9e6`, `log:auth:7197cbb5d81b`, `log:auth:72ae3fa150b5`, `log:auth:7568b9fca9ad`, `log:auth:7877eab35e98`, `log:auth:7b327c4594ff`, `log:auth:811e1f658b4b`, `log:auth:8733ab2f4543`, `log:auth:87614f556af3`, `log:auth:8b277994d6dd`, `log:auth:8ddb5025ba7f`, `log:auth:8eb94ac35bf9`, `log:auth:955560e889b3`, `log:auth:96ea0f608ef2`, `log:auth:9c6795a8c551`, `log:auth:a0105883ccdd`, `log:auth:a07c7bcc6c3d` (+364 more in the JSON).
- r0.05: inert 0: none; at grid edge 0: none; appear-only 401: `log:auth:059f77b5fee4`, `log:auth:0788a45dbb86`, `log:auth:0ae227c4f15d`, `log:auth:13e7be34fb70`, `log:auth:16e888bf8922`, `log:auth:16f327e6bd4d`, `log:auth:2d7f16630b87`, `log:auth:2ff20a342a41`, `log:auth:319b41b82d9b`, `log:auth:3219d9dbbaed`, `log:auth:35563463c928`, `log:auth:35873ee1cc7e`, `log:auth:3917ffeac5ec`, `log:auth:3b1fa69c3451`, `log:auth:3f00555a765d`, `log:auth:407989c51698`, `log:auth:4a79ac521b28`, `log:auth:4de8468724c7`, `log:auth:52a075c95ff9`, `log:auth:56bcc1a07d39`, `log:auth:56c309f6427c`, `log:auth:6c19cf62298a`, `log:auth:6e7a7f83a9e6`, `log:auth:7197cbb5d81b`, `log:auth:72ae3fa150b5`, `log:auth:7568b9fca9ad`, `log:auth:7877eab35e98`, `log:auth:7b327c4594ff`, `log:auth:811e1f658b4b`, `log:auth:8733ab2f4543`, `log:auth:87614f556af3`, `log:auth:8b277994d6dd`, `log:auth:8ddb5025ba7f`, `log:auth:8eb94ac35bf9`, `log:auth:955560e889b3`, `log:auth:96ea0f608ef2`, `log:auth:9c6795a8c551`, `log:auth:a0105883ccdd`, `log:auth:a07c7bcc6c3d`, `log:auth:a59061884c18` (+361 more in the JSON).

**Not placeable at this quiet time** (L, M, S, T sensors with no calibrated rule), by family (with a dropped rule / inert / unarmed only), then those with a dropped rule:

- r10: 8 sensors (S 0/0/8); with a dropped rule: none
- r1: 8 sensors (S 0/0/8); with a dropped rule: none
- r0.2: 8 sensors (S 0/0/8); with a dropped rule: none
- r0.05: 8 sensors (S 0/0/8); with a dropped rule: none

- `appear` (V3_APPEAR_RULE): new streams in no-fault cells per service, summed over the held-out cells (they enter the honest counts): r10 none; r1 none; r0.2 none; r0.05 none.
- **floor arm (share 0.05)**: r10 587/21/0/460 rules, 60 placeable + 404 appear-only sensors; r1 595/12/0/459 rules, 60 placeable + 403 appear-only sensors; r0.2 592/16/0/460 rules, 60 placeable + 404 appear-only sensors; r0.05 591/14/0/454 rules, 60 placeable + 401 appear-only sensors.
- **sensitivity, <= 1 held-out alarm (K_GRID only, no range fallback)**: r10 549/23/0/496 rules, 44 placeable + 404 appear-only sensors; r1 558/13/0/495 rules, 44 placeable + 403 appear-only sensors; r0.2 559/13/0/496 rules, 44 placeable + 404 appear-only sensors; r0.05 556/13/0/490 rules, 44 placeable + 401 appear-only sensors.

## Honest false alarms (decisions 64, 67): nested leave-one-cell-out unions on the no-fault cells

Union of the sensors' rules, each held-out no-fault cell scored at the values re-selected without it (its leave-one-cell-out fit), restarted after each alarm: count (/h [exact 95 % bound]); per family also the sum of its calibrated rules' honest counts (the reviewer's tally). The honest per-sensor rate is the sensor's false-alarm cost for CELF (JSON calibration.*.sensors.*.honestPerHour). Campaign B's fresh check can certify at best 20.0/h (0 alarms in 0.15 h per rate).

| setting | rate | T (h) | E | L | M | S | T | all placeable L, M, S, T |
|---|---|---|---|---|---|---|---|---|
| primary | r10 | 1.250 | 0 (0.0/h [2.4], 1.250 of 1.25 h) · sum 0 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [2.4], 1.250 of 1.25 h) · sum 0 · no evidence: 0 rules, 5 sensors | — | 16 (12.8/h [19.4], 1.250 of 1.25 h) · sum 13 · no evidence: 0 rules, 0 sensors | 34 (27.2/h [36.2], 1.250 of 1.25 h) · sum 28 · no evidence: 0 rules, 4 sensors | 61 (48.8/h [60.4], 1.25 of 1.25 h) |
| primary | r1 | 1.300 | 2 (1.5/h [4.8], 1.300 of 1.30 h) · sum 2 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [2.3], 1.300 of 1.30 h) · sum 0 · no evidence: 0 rules, 4 sensors | — | 37 (28.5/h [37.4], 1.300 of 1.30 h) · sum 39 · no evidence: 0 rules, 0 sensors | 95 (73.1/h [86.7], 1.300 of 1.30 h) · sum 90 · no evidence: 0 rules, 4 sensors | 140 (107.7/h [123.9], 1.30 of 1.30 h) |
| primary | r0.2 | 1.250 | 2 (1.6/h [5.0], 1.250 of 1.25 h) · sum 2 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [2.4], 1.250 of 1.25 h) · sum 0 · no evidence: 0 rules, 6 sensors | — | 59 (47.2/h [58.6], 1.250 of 1.25 h) · sum 80 · no evidence: 0 rules, 0 sensors | 35 (28.0/h [37.1], 1.250 of 1.25 h) · sum 31 · no evidence: 0 rules, 4 sensors | 101 (80.8/h [95.3], 1.25 of 1.25 h) |
| primary | r0.05 | 1.250 | 1 (0.8/h [3.8], 1.250 of 1.25 h) · sum 1 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [2.4], 1.250 of 1.25 h) · sum 0 · no evidence: 0 rules, 3 sensors | — | 23 (18.4/h [26.1], 1.250 of 1.25 h) · sum 21 · no evidence: 0 rules, 0 sensors | 29 (23.2/h [31.6], 1.250 of 1.25 h) · sum 28 · no evidence: 0 rules, 3 sensors | 59 (47.2/h [58.6], 1.25 of 1.25 h) |
| atMostOne | r10 | 1.250 | 0 (0.0/h [2.4], 1.250 of 1.25 h) · sum 0 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [2.4], 1.250 of 1.25 h) · sum 0 · no evidence: 0 rules, 5 sensors | — | 26 (20.8/h [28.9], 1.250 of 1.25 h) · sum 24 · no evidence: 0 rules, 0 sensors | 91 (72.8/h [86.7], 1.250 of 1.25 h) · sum 53 · no evidence: 0 rules, 4 sensors | 129 (103.2/h [119.4], 1.25 of 1.25 h) |
| atMostOne | r1 | 1.300 | 2 (1.5/h [4.8], 1.300 of 1.30 h) · sum 2 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [2.3], 1.300 of 1.30 h) · sum 0 · no evidence: 0 rules, 4 sensors | — | 51 (39.2/h [49.5], 1.300 of 1.30 h) · sum 53 · no evidence: 0 rules, 0 sensors | 127 (97.7/h [113.2], 1.300 of 1.30 h) · sum 124 · no evidence: 0 rules, 4 sensors | 190 (146.2/h [164.8], 1.30 of 1.30 h) |
| atMostOne | r0.2 | 1.250 | 3 (2.4/h [6.2], 1.250 of 1.25 h) · sum 3 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [2.4], 1.250 of 1.25 h) · sum 0 · no evidence: 0 rules, 6 sensors | — | 71 (56.8/h [69.2], 1.250 of 1.25 h) · sum 93 · no evidence: 0 rules, 0 sensors | 66 (52.8/h [64.8], 1.250 of 1.25 h) · sum 72 · no evidence: 0 rules, 4 sensors | 154 (123.2/h [140.8], 1.25 of 1.25 h) |
| atMostOne | r0.05 | 1.250 | 1 (0.8/h [3.8], 1.250 of 1.25 h) · sum 1 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [2.4], 1.250 of 1.25 h) · sum 0 · no evidence: 0 rules, 3 sensors | — | 31 (24.8/h [33.5], 1.250 of 1.25 h) · sum 31 · no evidence: 0 rules, 0 sensors | 53 (42.4/h [53.3], 1.250 of 1.25 h) · sum 46 · no evidence: 0 rules, 3 sensors | 100 (80.0/h [94.5], 1.25 of 1.25 h) |

P4-selected sets (the sensors P4 selected over its folds, or with one episode the candidates judged a win), honest nested union, primary:

- P4a auth-freeze-effect r0.05: `log:webui:d4d75ec135e6` -> 0 (0.0/h [2.4], 1.25 of 1.25 h) · sum over the sensors 0
- P4a auth-freeze-effect r0.2: `span:webui:LoginActionServlet.handlePOSTRequest` -> 1 (0.8/h [3.8], 1.25 of 1.25 h) · sum over the sensors 1
- P4a auth-freeze-effect r1: `span:webui:LoginActionServlet.handlePOSTRequest` -> 1 (0.8/h [3.6], 1.30 of 1.30 h) · sum over the sensors 1
- P4a auth-freeze-effect r10: `span:webui:LoginActionServlet.handlePOSTRequest` -> 1 (0.8/h [3.8], 1.25 of 1.25 h) · sum over the sensors 1
- P4a persistence-cpu-throttle-effect r0.05: `span:image:AbstractCache.getEntries` -> 1 (0.8/h [3.8], 1.25 of 1.25 h) · sum over the sensors 1
- P4a persistence-cpu-throttle-effect r0.2: `span:webui:IndexServlet.handleGETRequest` -> 1 (0.8/h [3.8], 1.25 of 1.25 h) · sum over the sensors 1
- P4a persistence-cpu-throttle-effect r1: `span:auth:AuthUserActionsRest.login`, `span:webui:IndexServlet.handleGETRequest` -> 3 (2.3/h [6.0], 1.30 of 1.30 h) · sum over the sensors 3
- P4a persistence-cpu-throttle-effect r10: `span:auth:AuthUserActionsRest.login` -> 1 (0.8/h [3.8], 1.25 of 1.25 h) · sum over the sensors 1
- P4b auth-freeze-effect r1: `metric:auth:sys_psi_cpu` -> 1 (0.8/h [3.6], 1.30 of 1.30 h) · sum over the sensors 1
- P4b auth-freeze-effect r10: `metric:auth:sys_psi_cpu` -> 1 (0.8/h [3.8], 1.25 of 1.25 h) · sum over the sensors 1
- P4b persistence-cpu-throttle-effect r0.05: `span:persistence:CategoryEndpoint.listAllEntities`, `span:persistence:UserRepository.getUserByName` -> 1 (0.8/h [3.8], 1.25 of 1.25 h) · sum over the sensors 1
- P4b persistence-cpu-throttle-effect r0.2: `span:persistence:CategoryEndpoint.listAllEntities` -> 1 (0.8/h [3.8], 1.25 of 1.25 h) · sum over the sensors 1
- P4b persistence-cpu-throttle-effect r1: `span:persistence:CategoryEndpoint.listAllEntities` -> 2 (1.5/h [4.8], 1.30 of 1.30 h) · sum over the sensors 2
- P4b persistence-cpu-throttle-effect r10: `span:persistence:UserRepository.getUserByName` -> 2 (1.6/h [5.0], 1.25 of 1.25 h) · sum over the sensors 2

## v2.4 reference row: family operating point (decision 53, 15/h, from v2.4's own code)

K per family: E 10, L 2.5, M —, S —, T 80, system —.

| class | family | r10 | r1 | r0.2 | r0.05 |
|---|---|---|---|---|---|
| auth-freeze | E | ok (K 10) | ok (K 10) | ok (K 10) | ok (K 10) |
| auth-freeze | L | ok (K 2.5) | ok (K 2.5) | ok (K 2.5) | ok (K 2.5) |
| auth-freeze | M | n/c | n/c | n/c | n/c |
| auth-freeze | S | no | no | no | no |
| auth-freeze | T | no | no | no | ok (K 80) |
| persistence-cpu-throttle | E | ok (K 10) | ok (K 10) | ok (K 10) | ok (K 10) |
| persistence-cpu-throttle | L | ok (K 2.5) | ok (K 2.5) | ok (K 2.5) | ok (K 2.5) |
| persistence-cpu-throttle | M | n/c | n/c | n/c | n/c |
| persistence-cpu-throttle | S | no | no | no | no |
| persistence-cpu-throttle | T | no | no | no | ok (K 80) |

## Predictions (primary: calibrated arm, floor primary)

- **P1** (auth-freeze; decision 54's interval, observed = first `failed` catch): 28/28; per rate r10 7/7, r1 7/7, r0.2 7/7, r0.05 7/7; not evaluable 0; holds by branch: error answer before the timeout (declared alternative) 9, timeout interval 19; verdict **holds**.
- **P2** r10 (failed before the first `failed` catch <= 153.00): 7/7, counts [116, 129, 117, 118, 123, 124, 115], verdict — (n < 4).
- **P2** r1 (failed before the first `failed` catch <= 18.00): 7/7, counts [16, 16, 16, 16, 16, 16, 16], verdict — (n < 4).
- **P2** r0.2 (failed before the first `failed` catch <= 6.00): 7/7, counts [4, 4, 4, 4, 4, 4, 4], verdict — (n < 4).
- **P2** r0.05 (failed before the first `failed` catch <= 3.75): 7/7, counts [1, 1, 1, 1, 1, 1, 1], verdict — (n < 4).
- **P3** auth-freeze: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P3** persistence-cpu-throttle: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P4** compares against the ledger E as the OR of its calibrated rules, its `failed` rule exempt from calibration (decisions 63, 70; V3_P4_LEDGER_READING = `calibrated-ledger`): a dropped ledger rule is listed below, not a reason for `—`. Two arms (decision 67): calibrated (primary) and optimistic bound (dropped rules armed at K = 100 / m = 5, beside, not evidence).
- Dropped ledger rules per rate (decision 70: listed; the ledger compares by its calibrated rules): r10 none; r1 none; r0.2 none; r0.05 none.
- **P4a** auth-freeze (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 0/7 (ledger missed, sensor caught: 0); r1 0/7 (ledger missed, sensor caught: 0); r0.2 0/7 (ledger missed, sensor caught: 0); r0.05 2/7 (ledger missed, sensor caught: 0); highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/7 (ledger missed, sensor caught: 0); r1 0/7 (ledger missed, sensor caught: 0); r0.2 0/7 (ledger missed, sensor caught: 0); r0.05 3/7 (ledger missed, sensor caught: 0); highest rate — at {10, 1, 0.2, 0.05}.
- **P4a** persistence-cpu-throttle (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 3/7 (ledger missed, sensor caught: 0); r1 3/7 (ledger missed, sensor caught: 0); r0.2 6/7 (ledger missed, sensor caught: 0); r0.05 0/7 (ledger missed, sensor caught: 0); highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 3/7 (ledger missed, sensor caught: 0); r1 3/7 (ledger missed, sensor caught: 0); r0.2 6/7 (ledger missed, sensor caught: 0); r0.05 0/7 (ledger missed, sensor caught: 0); highest rate — at {10, 1, 0.2, 0.05}.
- **P4b** auth-freeze (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 0/7 (ledger missed, sensor caught: 0); r1 0/7 (ledger missed, sensor caught: 0); r0.2 0/7 (ledger missed, sensor caught: 0); r0.05 0/7 (ledger missed, sensor caught: 0); highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/7 (ledger missed, sensor caught: 0); r1 0/7 (ledger missed, sensor caught: 0); r0.2 2/7 (ledger missed, sensor caught: 0); r0.05 6/7 (ledger missed, sensor caught: 0); highest rate — at {10, 1, 0.2, 0.05}.
- **P4b** persistence-cpu-throttle (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 1/7 (ledger missed, sensor caught: 0); r1 5/7 (ledger missed, sensor caught: 0); r0.2 5/7 (ledger missed, sensor caught: 0); r0.05 0/7 (ledger missed, sensor caught: 0); highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 4/7 (ledger missed, sensor caught: 0); r1 5/7 (ledger missed, sensor caught: 0); r0.2 5/7 (ledger missed, sensor caught: 0); r0.05 0/7 (ledger missed, sensor caught: 0); highest rate — at {10, 1, 0.2, 0.05}.

### P4 per class and rate: placeable sensors, dropped rules and non-placeable sensors on the affected path

- auth-freeze r10: placeable sensors 464 (candidates with a catch: 6); dropped on the path: `metric:auth:sys_io/spike`, `metric:auth:sys_psi_io/spike`, `metric:persistence:sys_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_io/spike`, `metric:webui:sys_psi_io/spike`, `span:auth:RandomSessionIdGenerator.getSessionId/spike`, `span:auth:ShaSecurityProvider.getKeyProvider/spike`, `span:persistence:CategoryEndpoint.listAllEntities/spike`, `span:persistence:PersistenceCategory.getId/spike`, `span:persistence:PersistenceUser.getId/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- auth-freeze r1: placeable sensors 463 (candidates with a catch: 9); dropped on the path: `metric:auth:sys_psi_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_psi_io/spike`, `span:auth:ShaSecurityProvider.getKeyProvider/spike`, `span:auth:ShaSecurityProvider.getSha512/spike`, `span:persistence:PersistenceCategory.getId/spike`, `span:persistence:UserEndpoint.findById/spike`, `span:persistence:UserRepository.getUserByName/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- auth-freeze r0.2: placeable sensors 464 (candidates with a catch: 4); dropped on the path: `metric:auth:sys_io/spike`, `metric:persistence:sys_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_io/spike`, `metric:webui:sys_psi_io/spike`, `span:auth:RandomSessionIdGenerator.getSessionId/spike`, `span:auth:ShaSecurityProvider.getKeyProvider/spike`, `span:persistence:PersistenceCategory.getId/spike`, `span:persistence:UserEndpoint.findById/spike`, `span:persistence:UserRepository.getUserByName/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- auth-freeze r0.05: placeable sensors 461 (candidates with a catch: 5); dropped on the path: `metric:auth:sys_io/spike`, `metric:auth:sys_psi_io/spike`, `metric:persistence:sys_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_io/spike`, `metric:webui:sys_psi_io/spike`, `span:auth:RandomSessionIdGenerator.getSessionId/spike`, `span:persistence:PersistenceCategory.getId/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- persistence-cpu-throttle r10: placeable sensors 464 (candidates with a catch: 32); dropped on the path: `metric:auth:sys_io/spike`, `metric:auth:sys_psi_io/spike`, `metric:persistence:sys_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_io/spike`, `metric:webui:sys_psi_io/spike`, `span:auth:RandomSessionIdGenerator.getSessionId/spike`, `span:auth:ShaSecurityProvider.getKeyProvider/spike`, `span:persistence:CategoryEndpoint.listAllEntities/spike`, `span:persistence:PersistenceCategory.getId/spike`, `span:persistence:PersistenceUser.getId/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- persistence-cpu-throttle r1: placeable sensors 463 (candidates with a catch: 30); dropped on the path: `metric:auth:sys_psi_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_psi_io/spike`, `span:auth:ShaSecurityProvider.getKeyProvider/spike`, `span:auth:ShaSecurityProvider.getSha512/spike`, `span:persistence:PersistenceCategory.getId/spike`, `span:persistence:UserEndpoint.findById/spike`, `span:persistence:UserRepository.getUserByName/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- persistence-cpu-throttle r0.2: placeable sensors 464 (candidates with a catch: 23); dropped on the path: `metric:auth:sys_io/spike`, `metric:persistence:sys_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_io/spike`, `metric:webui:sys_psi_io/spike`, `span:auth:RandomSessionIdGenerator.getSessionId/spike`, `span:auth:ShaSecurityProvider.getKeyProvider/spike`, `span:persistence:PersistenceCategory.getId/spike`, `span:persistence:UserEndpoint.findById/spike`, `span:persistence:UserRepository.getUserByName/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- persistence-cpu-throttle r0.05: placeable sensors 461 (candidates with a catch: 15); dropped on the path: `metric:auth:sys_io/spike`, `metric:auth:sys_psi_io/spike`, `metric:persistence:sys_io/spike`, `metric:persistence:sys_psi_io/spike`, `metric:webui:sys_io/spike`, `metric:webui:sys_psi_io/spike`, `span:auth:RandomSessionIdGenerator.getSessionId/spike`, `span:persistence:PersistenceCategory.getId/spike`; not placeable on the path: `metric:auth:sys_psi_memory`, `metric:persistence:sys_psi_memory`, `metric:webui:sys_psi_memory`; dropped ledger rules (listed, decision 70): none

### P4 folds (sensor rule vs ledger rule; lead, margin; category)

**Calibrated arm**

- P4a auth-freeze r10 (candidates 6; paired differences ledger - sensor: mean -10.227 [-10.877, -9.797] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 10.477 vs E `absent` 0.539; lead -9.938, margin 4.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 11.425 vs E `absent` 0.548; lead -10.877, margin 2.2e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 10.348 vs E `absent` 0.509; lead -9.839, margin 2.8e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 10.425 vs E `absent` 0.513; lead -9.911, margin 4.6e-05; tied 1 (win share 0/1); **not faster**
  - ep5 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 11.047 vs E `absent` 0.485; lead -10.563, margin 1.4e-05; tied 1 (win share 0/1); **not faster**
  - ep6 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 11.160 vs E `absent` 0.493; lead -10.667, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep7 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 10.279 vs E `absent` 0.482; lead -9.797, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
- P4a auth-freeze r1 (candidates 9; paired differences ledger - sensor: mean -17.842 [-18.196, -17.334] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.248 vs E `absent` 1.057; lead -18.191, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.475 vs E `absent` 1.279; lead -18.196, margin 2.1e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.480 vs E `absent` 1.708; lead -17.772, margin 7.2e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.537 vs E `absent` 1.615; lead -17.922, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
  - ep5 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.115 vs E `absent` 1.781; lead -17.334, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
  - ep6 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 18.411 vs E `absent` 1.042; lead -17.369, margin 7.2e-06; tied 1 (win share 0/1); **not faster**
  - ep7 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.728 vs E `absent` 1.614; lead -18.114, margin 2.6e-06; tied 1 (win share 0/1); **not faster**
- P4a auth-freeze r0.2 (candidates 4; paired differences ledger - sensor: mean -16.691 [-16.829, -16.546] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 23.363 vs E `absent` 6.606; lead -16.757, margin 1.9e-06; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.522 vs E `absent` 2.833; lead -16.689, margin 2.4e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 22.511 vs E `absent` 5.965; lead -16.546, margin 1.9e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 21.272 vs E `absent` 4.705; lead -16.567, margin 1.9e-06; tied 1 (win share 0/1); **not faster**
  - ep5 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 21.312 vs E `absent` 4.482; lead -16.829, margin 2.1e-06; tied 1 (win share 0/1); **not faster**
  - ep6 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 23.241 vs E `absent` 6.498; lead -16.743, margin 2.1e-06; tied 1 (win share 0/1); **not faster**
  - ep7 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 20.455 vs E `absent` 3.750; lead -16.705, margin 1.7e-06; tied 1 (win share 0/1); **not faster**
- P4a auth-freeze r0.05 (candidates 5; paired differences ledger - sensor: mean -12.191 [-19.270, 6.463] s; availability-clock wins 2 of 7 evaluable):
  - ep1 b1: log:webui:d4d75ec135e6 `appear` 25.896 vs E `absent` 6.817; lead -19.079, margin 0.97; tied 1 (win share 0/1); **not faster**
  - ep2 b1: log:webui:d4d75ec135e6 `appear` 20.493 vs E `absent` 1.426; lead -19.067, margin 0.96; tied 1 (win share 0/1); **not faster**
  - ep3 b2: log:webui:d4d75ec135e6 `appear` 13.252 vs E `absent` 16.775; lead 3.523, margin 1; tied 1 (win share 1/1); **win**
  - ep4 b3: log:webui:d4d75ec135e6 `appear` 29.799 vs E `absent` 10.529; lead -19.270, margin 1; tied 1 (win share 0/1); **not faster**
  - ep5 b1: log:webui:d4d75ec135e6 `appear` 25.921 vs E `absent` 6.932; lead -18.989, margin 0.97; tied 1 (win share 0/1); **not faster**
  - ep6 b2: log:webui:d4d75ec135e6 `appear` 11.977 vs E `absent` 18.440; lead 6.463, margin 0.97; tied 1 (win share 1/1); **win**
  - ep7 b3: log:webui:d4d75ec135e6 `appear` 21.239 vs E `absent` 2.324; lead -18.915, margin 0.92; tied 1 (win share 0/1); **not faster**
- P4a persistence-cpu-throttle r10 (candidates 32; paired differences ledger - sensor: mean -0.076 [-1.005, 0.196] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:auth:AuthUserActionsRest.login `spike` 0.210 vs E `median` 0.235; lead 0.024, margin 1.3e-05; tied 1 (win share 0/1); **same request**
  - ep2 b1: span:auth:AuthUserActionsRest.login `run3` 1.293 vs E `run3` 1.296; lead 0.003, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep3 b2: span:auth:AuthUserActionsRest.login `spike` 0.283 vs E `median` 0.408; lead 0.125, margin 1.4e-05; tied 1 (win share 1/1); **win**
  - ep4 b3: span:auth:AuthUserActionsRest.login `spike` 1.298 vs E `median` 0.293; lead -1.005, margin 2.7e-05; tied 1 (win share 0/1); **not faster**
  - ep5 b1: span:auth:AuthUserActionsRest.login `run3` 0.600 vs E `run3` 0.629; lead 0.029, margin 6.4e-05; tied 1 (win share 0/1); **same request**
  - ep6 b2: span:auth:AuthUserActionsRest.login `run3` 1.082 vs E `spike` 1.277; lead 0.196, margin 2.8e-05; tied 1 (win share 1/1); **win**
  - ep7 b3: span:auth:AuthUserActionsRest.login `spike` 0.838 vs E `spike` 0.933; lead 0.095, margin 1.3e-05; tied 1 (win share 0/1); **same request**
- P4a persistence-cpu-throttle r1 (candidates 30; paired differences ledger - sensor: mean -1.289 [-4.002, 0.003] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:IndexServlet.handleGETRequest `median` 2.927 vs E `median` 2.929; lead 0.002, margin 1.4e-05; tied 1 (win share 1/1); **win**
  - ep2 b1: span:auth:AuthUserActionsRest.login `spike` 4.000 vs E `median` 2.818; lead -1.182, margin 1.5e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:auth:AuthUserActionsRest.login `spike` 6.167 vs E `median` 2.165; lead -4.002, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:webui:IndexServlet.handleGETRequest `spike` 1.859 vs E `spike` 1.862; lead 0.003, margin 1.2e-05; tied 1 (win share 1/1); **win**
  - ep5 b1: span:webui:IndexServlet.handleGETRequest `spike` 5.029 vs E `spike` 5.031; lead 0.002, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep6 b2: span:webui:IndexServlet.handleGETRequest `median` 2.236 vs E `spike` 1.482; lead -0.754, margin 1.7e-05; tied 1 (win share 0/1); **not faster**
  - ep7 b3: span:webui:IndexServlet.handleGETRequest `median` 3.612 vs E `spike` 0.516; lead -3.096, margin 1.5e-05; tied 1 (win share 0/1); **not faster**
- P4a persistence-cpu-throttle r0.2 (candidates 23; paired differences ledger - sensor: mean 0.002 [0.001, 0.003] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:IndexServlet.handleGETRequest `spike` 9.185 vs E `spike` 9.187; lead 0.002, margin 4.1e-06; tied 1 (win share 1/1); **win**
  - ep2 b1: span:webui:IndexServlet.handleGETRequest `absent` 18.589 vs E `absent` 18.590; lead 0.001, margin 1.1e-05; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0017 start + -0.00016 gap + 0]
  - ep3 b2: span:webui:IndexServlet.handleGETRequest `spike` 2.542 vs E `spike` 2.545; lead 0.003, margin 1e-05; tied 1 (win share 1/1); **win**
  - ep4 b3: span:webui:IndexServlet.handleGETRequest `spike` 3.468 vs E `spike` 3.469; lead 0.001, margin 1.1e-05; tied 1 (win share 1/1); **win**
  - ep5 b1: span:webui:IndexServlet.handleGETRequest `spike` 4.936 vs E `spike` 4.938; lead 0.002, margin 2.1e-06; tied 1 (win share 1/1); **win**
  - ep6 b2: span:webui:IndexServlet.handleGETRequest `spike` 5.664 vs E `spike` 5.667; lead 0.003, margin 2.1e-06; tied 1 (win share 1/1); **win**
  - ep7 b3: span:webui:IndexServlet.handleGETRequest `spike` 21.920 vs E `spike` 21.922; lead 0.002, margin 2.4e-06; tied 1 (win share 1/1); **win**
- P4a persistence-cpu-throttle r0.05 (candidates 15; paired differences ledger - sensor: mean 0.017 [0.009, 0.021] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:image:AbstractCache.getEntries `absent` 34.000 vs E `absent` 34.017; lead 0.017, margin 1.7e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0072 start + 0.0098 gap + 0]
  - ep2 b1: span:image:AbstractCache.getEntries `absent` 5.437 vs E `spike` 5.446; lead 0.009, margin 9.5e-07; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request)
  - ep3 b2: span:image:AbstractCache.getEntries `absent` 7.735 vs E `absent` 7.754; lead 0.019, margin 1.2e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0087 start + 0.0098 gap + 0]
  - ep4 b3: span:image:AbstractCache.getEntries `absent` 57.393 vs E `absent` 57.410; lead 0.017, margin 2.9e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0076 start + 0.0098 gap + 0]
  - ep5 b1: span:image:AbstractCache.getEntries `absent` 27.180 vs E `absent` 27.196; lead 0.016, margin 1.4e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.006 start + 0.0098 gap + 0]
  - ep6 b2: span:image:AbstractCache.getEntries `absent` 0.556 vs E `absent` 0.577; lead 0.021, margin 1.9e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.011 start + 0.0098 gap + 0]
  - ep7 b3: span:image:AbstractCache.getEntries `absent` 18.252 vs E `absent` 18.272; lead 0.019, margin 1.2e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0097 start + 0.0098 gap + 0]
- P4b auth-freeze r10 (candidates 1; paired differences ledger - sensor: mean -14.402 [-14.487, -14.299] s; availability-clock wins 0 of 7 evaluable):
  - ep1 b1: metric:auth:sys_psi_cpu `run3` 14.947 vs E `absent` 0.539; lead -14.408, margin 4.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: metric:auth:sys_psi_cpu `run3` 14.847 vs E `absent` 0.548; lead -14.299, margin 2.3e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:auth:sys_psi_cpu `run3` 14.914 vs E `absent` 0.509; lead -14.404, margin 2.8e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:auth:sys_psi_cpu `run3` 14.922 vs E `absent` 0.513; lead -14.409, margin 4.6e-05; tied 1 (win share 0/1); **not faster**
  - ep5 b1: metric:auth:sys_psi_cpu `run3` 14.897 vs E `absent` 0.485; lead -14.413, margin 1.4e-05; tied 1 (win share 0/1); **not faster**
  - ep6 b2: metric:auth:sys_psi_cpu `run3` 14.980 vs E `absent` 0.493; lead -14.487, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep7 b3: metric:auth:sys_psi_cpu `run3` 14.879 vs E `absent` 0.482; lead -14.397, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
- P4b auth-freeze r1 (candidates 1; paired differences ledger - sensor: mean -12.967 [-13.266, -12.248] s; availability-clock wins 0 of 7 evaluable):
  - ep1 b1: metric:auth:sys_psi_cpu `median` 14.323 vs E `absent` 1.057; lead -13.266, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: metric:auth:sys_psi_cpu `run3` 14.539 vs E `absent` 1.279; lead -13.260, margin 2.2e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:auth:sys_psi_cpu `median` 13.956 vs E `absent` 1.708; lead -12.248, margin 7.3e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:auth:sys_psi_cpu `median` 14.862 vs E `absent` 1.615; lead -13.247, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
  - ep5 b1: metric:auth:sys_psi_cpu `median` 14.036 vs E `absent` 1.781; lead -12.255, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
  - ep6 b2: metric:auth:sys_psi_cpu `run3` 14.289 vs E `absent` 1.042; lead -13.247, margin 7.3e-06; tied 1 (win share 0/1); **not faster**
  - ep7 b3: metric:auth:sys_psi_cpu `run3` 14.859 vs E `absent` 1.614; lead -13.245, margin 2.7e-06; tied 1 (win share 0/1); **not faster**
- P4b auth-freeze r0.2 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `absent` 6.606; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b1: — `—` — vs E `absent` 2.833; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b2: — `—` — vs E `absent` 5.965; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b3: — `—` — vs E `absent` 4.705; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep5 b1: — `—` — vs E `absent` 4.482; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep6 b2: — `—` — vs E `absent` 6.498; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep7 b3: — `—` — vs E `absent` 3.750; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b auth-freeze r0.05 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `absent` 6.817; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b1: — `—` — vs E `absent` 1.426; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b2: — `—` — vs E `absent` 16.775; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b3: — `—` — vs E `absent` 10.529; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep5 b1: — `—` — vs E `absent` 6.932; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep6 b2: — `—` — vs E `absent` 18.440; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep7 b3: — `—` — vs E `absent` 2.324; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b persistence-cpu-throttle r10 (candidates 5; paired differences ledger - sensor: mean -0.142 [-0.985, 0.215] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:UserRepository.getUserByName `spike` 0.288 vs E `median` 0.235; lead -0.054, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:persistence:UserRepository.getUserByName `spike` 1.482 vs E `run3` 1.296; lead -0.187, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:persistence:UserRepository.getUserByName `spike` 0.460 vs E `median` 0.408; lead -0.052, margin 1.4e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:persistence:UserRepository.getUserByName `spike` 1.278 vs E `median` 0.293; lead -0.985, margin 2.7e-05; tied 1 (win share 0/1); **not faster**
  - ep5 b1: span:persistence:UserRepository.getUserByName `spike` 0.580 vs E `run3` 0.629; lead 0.049, margin 6.4e-05; tied 1 (win share 0/1); **same request**
  - ep6 b2: span:persistence:UserRepository.getUserByName `spike` 1.063 vs E `spike` 1.277; lead 0.215, margin 2.8e-05; tied 1 (win share 0/1); **same request**
  - ep7 b3: span:persistence:UserRepository.getUserByName `spike` 0.915 vs E `spike` 0.933; lead 0.018, margin 1.3e-05; tied 1 (win share 1/1); **win**
- P4b persistence-cpu-throttle r1 (candidates 5; paired differences ledger - sensor: mean -0.106 [-3.780, 1.938] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 1.009 vs E `median` 2.929; lead 1.920, margin 1.4e-05; tied 1 (win share 1/1); **win**
  - ep2 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 0.881 vs E `median` 2.818; lead 1.938, margin 1.5e-05; tied 1 (win share 1/1); **win**
  - ep3 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 1.148 vs E `median` 2.165; lead 1.018, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep4 b3: span:persistence:CategoryEndpoint.listAllEntities `spike` 5.641 vs E `spike` 1.862; lead -3.780, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
  - ep5 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 5.010 vs E `spike` 5.031; lead 0.021, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep6 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 0.261 vs E `spike` 1.482; lead 1.221, margin 1.7e-05; tied 1 (win share 1/1); **win**
  - ep7 b3: span:persistence:CategoryEndpoint.listAllEntities `spike` 3.595 vs E `spike` 0.516; lead -3.079, margin 1.5e-05; tied 1 (win share 0/1); **not faster**
- P4b persistence-cpu-throttle r0.2 (candidates 5; paired differences ledger - sensor: mean -0.681 [-4.976, 0.092] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 9.095 vs E `spike` 9.187; lead 0.092, margin 4.1e-06; tied 1 (win share 1/1); **win**
  - ep2 b1: span:persistence:CategoryEndpoint.listAllEntities `absent` 18.568 vs E `absent` 18.590; lead 0.023, margin 1.1e-05; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.023 start + 0.00031 gap + -1.2e-07]
  - ep3 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 2.517 vs E `spike` 2.545; lead 0.029, margin 1e-05; tied 1 (win share 1/1); **win**
  - ep4 b3: span:persistence:CategoryEndpoint.listAllEntities `spike` 3.449 vs E `spike` 3.469; lead 0.020, margin 1.1e-05; tied 1 (win share 1/1); **win**
  - ep5 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 9.915 vs E `spike` 4.938; lead -4.976, margin 2.1e-06; tied 1 (win share 0/1); **not faster**
  - ep6 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 5.643 vs E `spike` 5.667; lead 0.024, margin 2.1e-06; tied 1 (win share 1/1); **win**
  - ep7 b3: span:persistence:CategoryEndpoint.listAllEntities `spike` 21.896 vs E `spike` 21.922; lead 0.026, margin 2.4e-06; tied 1 (win share 1/1); **win**
- P4b persistence-cpu-throttle r0.05 (candidates 6; paired differences ledger - sensor: mean -10.295 [-40.123, -0.113] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:UserRepository.getUserByName `spike` 34.190 vs E `absent` 34.017; lead -0.172, margin 1.7e-06; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:persistence:UserRepository.getUserByName `spike` 30.528 vs E `spike` 5.446; lead -25.081, margin 9.5e-07; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:persistence:UserRepository.getUserByName `spike` 7.867 vs E `absent` 7.754; lead -0.113, margin 1.2e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:persistence:UserRepository.getUserByName `—` — vs E `absent` 57.410; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep5 b1: span:persistence:UserRepository.getUserByName `spike` 27.328 vs E `absent` 27.196; lead -0.132, margin 1.4e-06; tied 1 (win share 0/1); **not faster**
  - ep6 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 40.699 vs E `absent` 0.577; lead -40.123, margin 1.9e-06; tied 1 (win share 0/1); **not faster**
  - ep7 b3: span:persistence:UserRepository.getUserByName `spike` 21.996 vs E `absent` 18.272; lead -3.724, margin 1.2e-06; tied 1 (win share 0/1); **not faster**

**Optimistic bound (not evidence)**

- P4a auth-freeze r10 (candidates 8; paired differences ledger - sensor: mean -11.165 [-19.306, -4.405] s; availability-clock wins 0 of 5 evaluable):
  - ep1 b1: metric:webui:sys_io `spike` 14.947 vs E `absent` 0.539; lead -14.408, margin 4.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: metric:webui:sys_io `spike` 19.854 vs E `absent` 0.548; lead -19.306, margin 2.3e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:webui:sys_io `spike` 4.914 vs E `absent` 0.509; lead -4.405, margin 2.8e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:webui:sys_io `spike` 4.922 vs E `absent` 0.513; lead -4.409, margin 4.6e-05; tied 1 (win share 0/1); **not faster**
  - ep5 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 11.047 vs E `absent` 0.485; lead -10.563, margin 1.4e-05; tied 1 (win share 0/1); **not faster**
  - ep6 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 11.160 vs E `absent` 0.493; lead -10.667, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep7 b3: metric:webui:sys_io `spike` 14.879 vs E `absent` 0.482; lead -14.397, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
- P4a auth-freeze r1 (candidates 9; paired differences ledger - sensor: mean -17.842 [-18.196, -17.334] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.248 vs E `absent` 1.057; lead -18.191, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.475 vs E `absent` 1.279; lead -18.196, margin 2.1e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.480 vs E `absent` 1.708; lead -17.772, margin 7.2e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.537 vs E `absent` 1.615; lead -17.922, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
  - ep5 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.115 vs E `absent` 1.781; lead -17.334, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
  - ep6 b2: span:webui:LoginActionServlet.handlePOSTRequest `spike` 18.411 vs E `absent` 1.042; lead -17.369, margin 7.2e-06; tied 1 (win share 0/1); **not faster**
  - ep7 b3: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.728 vs E `absent` 1.614; lead -18.114, margin 2.6e-06; tied 1 (win share 0/1); **not faster**
- P4a auth-freeze r0.2 (candidates 7; paired differences ledger - sensor: mean -20.737 [-22.364, -16.689] s; availability-clock wins 0 of 5 evaluable):
  - ep1 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 23.363 vs E `absent` 6.606; lead -16.757, margin 1.9e-06; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:webui:LoginActionServlet.handlePOSTRequest `spike` 19.522 vs E `absent` 2.833; lead -16.689, margin 2.4e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:webui:sys_io `spike` 28.302 vs E `absent` 5.965; lead -22.337, margin 2e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:webui:sys_io `spike` 27.030 vs E `absent` 4.705; lead -22.325, margin 2e-06; tied 1 (win share 0/1); **not faster**
  - ep5 b1: metric:webui:sys_io `spike` 26.847 vs E `absent` 4.482; lead -22.364, margin 2.2e-06; tied 1 (win share 0/1); **not faster**
  - ep6 b2: metric:webui:sys_io `spike` 28.843 vs E `absent` 6.498; lead -22.345, margin 2.2e-06; tied 1 (win share 0/1); **not faster**
  - ep7 b3: metric:webui:sys_io `spike` 26.088 vs E `absent` 3.750; lead -22.338, margin 1.8e-06; tied 1 (win share 0/1); **not faster**
- P4a auth-freeze r0.05 (candidates 6; paired differences ledger - sensor: mean -7.706 [-24.854, 15.161] s; availability-clock wins 3 of 7 evaluable):
  - ep1 b1: metric:webui:sys_io `spike` 1.683 vs E `absent` 6.817; lead 5.134, margin 1.3e-06; tied 1 (win share 1/1); **win**
  - ep2 b1: metric:webui:sys_io `spike` 26.276 vs E `absent` 1.426; lead -24.850, margin 1.3e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:webui:sys_io `spike` 1.614 vs E `absent` 16.775; lead 15.161, margin 1.5e-06; tied 1 (win share 1/1); **win**
  - ep4 b3: metric:webui:sys_io `spike` 5.374 vs E `absent` 10.529; lead 5.156, margin 1.3e-06; tied 1 (win share 1/1); **win**
  - ep5 b1: metric:webui:sys_io `spike` 31.786 vs E `absent` 6.932; lead -24.854, margin 2e-06; tied 1 (win share 0/1); **not faster**
  - ep6 b2: metric:webui:sys_io `spike` 23.294 vs E `absent` 18.440; lead -4.854, margin 1.5e-06; tied 1 (win share 0/1); **not faster**
  - ep7 b3: metric:webui:sys_io `spike` 27.161 vs E `absent` 2.324; lead -24.837, margin 1.1e-06; tied 1 (win share 0/1); **not faster**
- P4a persistence-cpu-throttle r10 (candidates 33; paired differences ledger - sensor: mean -0.076 [-1.005, 0.196] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:auth:AuthUserActionsRest.login `spike` 0.210 vs E `median` 0.235; lead 0.024, margin 1.3e-05; tied 1 (win share 0/1); **same request**
  - ep2 b1: span:auth:AuthUserActionsRest.login `run3` 1.293 vs E `run3` 1.296; lead 0.003, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep3 b2: span:auth:AuthUserActionsRest.login `spike` 0.283 vs E `median` 0.408; lead 0.125, margin 1.4e-05; tied 1 (win share 1/1); **win**
  - ep4 b3: span:auth:AuthUserActionsRest.login `spike` 1.298 vs E `median` 0.293; lead -1.005, margin 2.7e-05; tied 1 (win share 0/1); **not faster**
  - ep5 b1: span:auth:AuthUserActionsRest.login `run3` 0.600 vs E `run3` 0.629; lead 0.029, margin 6.4e-05; tied 1 (win share 0/1); **same request**
  - ep6 b2: span:auth:AuthUserActionsRest.login `run3` 1.082 vs E `spike` 1.277; lead 0.196, margin 2.8e-05; tied 1 (win share 1/1); **win**
  - ep7 b3: span:auth:AuthUserActionsRest.login `spike` 0.838 vs E `spike` 0.933; lead 0.095, margin 1.3e-05; tied 1 (win share 0/1); **same request**
- P4a persistence-cpu-throttle r1 (candidates 30; paired differences ledger - sensor: mean -1.289 [-4.002, 0.003] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:IndexServlet.handleGETRequest `median` 2.927 vs E `median` 2.929; lead 0.002, margin 1.4e-05; tied 1 (win share 1/1); **win**
  - ep2 b1: span:auth:AuthUserActionsRest.login `spike` 4.000 vs E `median` 2.818; lead -1.182, margin 1.5e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:auth:AuthUserActionsRest.login `spike` 6.167 vs E `median` 2.165; lead -4.002, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:webui:IndexServlet.handleGETRequest `spike` 1.859 vs E `spike` 1.862; lead 0.003, margin 1.2e-05; tied 1 (win share 1/1); **win**
  - ep5 b1: span:webui:IndexServlet.handleGETRequest `spike` 5.029 vs E `spike` 5.031; lead 0.002, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep6 b2: span:webui:IndexServlet.handleGETRequest `median` 2.236 vs E `spike` 1.482; lead -0.754, margin 1.7e-05; tied 1 (win share 0/1); **not faster**
  - ep7 b3: span:webui:IndexServlet.handleGETRequest `median` 3.612 vs E `spike` 0.516; lead -3.096, margin 1.5e-05; tied 1 (win share 0/1); **not faster**
- P4a persistence-cpu-throttle r0.2 (candidates 25; paired differences ledger - sensor: mean 0.002 [0.001, 0.003] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:webui:IndexServlet.handleGETRequest `spike` 9.185 vs E `spike` 9.187; lead 0.002, margin 4.1e-06; tied 1 (win share 1/1); **win**
  - ep2 b1: span:webui:IndexServlet.handleGETRequest `absent` 18.589 vs E `absent` 18.590; lead 0.001, margin 1.1e-05; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0017 start + -0.00016 gap + 0]
  - ep3 b2: span:webui:IndexServlet.handleGETRequest `spike` 2.542 vs E `spike` 2.545; lead 0.003, margin 1e-05; tied 1 (win share 1/1); **win**
  - ep4 b3: span:webui:IndexServlet.handleGETRequest `spike` 3.468 vs E `spike` 3.469; lead 0.001, margin 1.1e-05; tied 1 (win share 1/1); **win**
  - ep5 b1: span:webui:IndexServlet.handleGETRequest `spike` 4.936 vs E `spike` 4.938; lead 0.002, margin 2.1e-06; tied 1 (win share 1/1); **win**
  - ep6 b2: span:webui:IndexServlet.handleGETRequest `spike` 5.664 vs E `spike` 5.667; lead 0.003, margin 2.1e-06; tied 1 (win share 1/1); **win**
  - ep7 b3: span:webui:IndexServlet.handleGETRequest `spike` 21.920 vs E `spike` 21.922; lead 0.002, margin 2.4e-06; tied 1 (win share 1/1); **win**
- P4a persistence-cpu-throttle r0.05 (candidates 17; paired differences ledger - sensor: mean 0.017 [0.009, 0.021] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:image:AbstractCache.getEntries `absent` 34.000 vs E `absent` 34.017; lead 0.017, margin 1.7e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0072 start + 0.0098 gap + 0]
  - ep2 b1: span:image:AbstractCache.getEntries `absent` 5.437 vs E `spike` 5.446; lead 0.009, margin 9.5e-07; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request)
  - ep3 b2: span:image:AbstractCache.getEntries `absent` 7.735 vs E `absent` 7.754; lead 0.019, margin 1.2e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0087 start + 0.0098 gap + 0]
  - ep4 b3: span:image:AbstractCache.getEntries `absent` 57.393 vs E `absent` 57.410; lead 0.017, margin 2.9e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0076 start + 0.0098 gap + 0]
  - ep5 b1: span:image:AbstractCache.getEntries `absent` 27.180 vs E `absent` 27.196; lead 0.016, margin 1.4e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.006 start + 0.0098 gap + 0]
  - ep6 b2: span:image:AbstractCache.getEntries `absent` 0.556 vs E `absent` 0.577; lead 0.021, margin 1.9e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.011 start + 0.0098 gap + 0]
  - ep7 b3: span:image:AbstractCache.getEntries `absent` 18.252 vs E `absent` 18.272; lead 0.019, margin 1.2e-06; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.0097 start + 0.0098 gap + 0]
- P4b auth-freeze r10 (candidates 2; paired differences ledger - sensor: mean -8.684 [-9.483, -4.396] s; availability-clock wins 0 of 7 evaluable):
  - ep1 b1: metric:auth:sys_io `spike` 9.942 vs E `absent` 0.539; lead -9.403, margin 4.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: metric:auth:sys_io `spike` 9.844 vs E `absent` 0.548; lead -9.296, margin 2.3e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:auth:sys_io `spike` 9.904 vs E `absent` 0.509; lead -9.395, margin 2.8e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:auth:sys_io `spike` 9.917 vs E `absent` 0.513; lead -9.404, margin 4.6e-05; tied 1 (win share 0/1); **not faster**
  - ep5 b1: metric:auth:sys_io `spike` 9.893 vs E `absent` 0.485; lead -9.408, margin 1.4e-05; tied 1 (win share 0/1); **not faster**
  - ep6 b2: metric:auth:sys_io `spike` 9.976 vs E `absent` 0.493; lead -9.483, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep7 b3: metric:auth:sys_io `spike` 4.878 vs E `absent` 0.482; lead -4.396, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
- P4b auth-freeze r1 (candidates 1; paired differences ledger - sensor: mean -12.967 [-13.266, -12.248] s; availability-clock wins 0 of 7 evaluable):
  - ep1 b1: metric:auth:sys_psi_cpu `median` 14.323 vs E `absent` 1.057; lead -13.266, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: metric:auth:sys_psi_cpu `run3` 14.539 vs E `absent` 1.279; lead -13.260, margin 2.2e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:auth:sys_psi_cpu `median` 13.956 vs E `absent` 1.708; lead -12.248, margin 7.3e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:auth:sys_psi_cpu `median` 14.862 vs E `absent` 1.615; lead -13.247, margin 1.1e-05; tied 1 (win share 0/1); **not faster**
  - ep5 b1: metric:auth:sys_psi_cpu `median` 14.036 vs E `absent` 1.781; lead -12.255, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
  - ep6 b2: metric:auth:sys_psi_cpu `run3` 14.289 vs E `absent` 1.042; lead -13.247, margin 7.3e-06; tied 1 (win share 0/1); **not faster**
  - ep7 b3: metric:auth:sys_psi_cpu `run3` 14.859 vs E `absent` 1.614; lead -13.245, margin 2.7e-06; tied 1 (win share 0/1); **not faster**
- P4b auth-freeze r0.2 (candidates 1; paired differences ledger - sensor: mean -2.340 [-7.364, 2.663] s; availability-clock wins 2 of 7 evaluable):
  - ep1 b1: metric:auth:sys_io `spike` 3.943 vs E `absent` 6.606; lead 2.663, margin 2e-06; tied 1 (win share 1/1); **win**
  - ep2 b1: metric:auth:sys_io `spike` 10.179 vs E `absent` 2.833; lead -7.347, margin 2.5e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:auth:sys_io `spike` 8.300 vs E `absent` 5.965; lead -2.335, margin 2e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:auth:sys_io `spike` 7.024 vs E `absent` 4.705; lead -2.319, margin 2e-06; tied 1 (win share 0/1); **not faster**
  - ep5 b1: metric:auth:sys_io `spike` 11.847 vs E `absent` 4.482; lead -7.364, margin 2.2e-06; tied 1 (win share 0/1); **not faster**
  - ep6 b2: metric:auth:sys_io `spike` 8.835 vs E `absent` 6.498; lead -2.337, margin 2.2e-06; tied 1 (win share 0/1); **not faster**
  - ep7 b3: metric:auth:sys_io `spike` 1.089 vs E `absent` 3.750; lead 2.661, margin 1.8e-06; tied 1 (win share 1/1); **win**
- P4b auth-freeze r0.05 (candidates 1; paired differences ledger - sensor: mean 3.008 [-4.836, 10.155] s; availability-clock wins 6 of 7 evaluable):
  - ep1 b1: metric:auth:sys_io `spike` 6.683 vs E `absent` 6.817; lead 0.134, margin 1.3e-06; tied 1 (win share 1/1); **win**
  - ep2 b1: metric:auth:sys_io `spike` 1.277 vs E `absent` 1.426; lead 0.149, margin 1.3e-06; tied 1 (win share 1/1); **win**
  - ep3 b2: metric:auth:sys_io `spike` 11.613 vs E `absent` 16.775; lead 5.161, margin 1.5e-06; tied 1 (win share 1/1); **win**
  - ep4 b3: metric:auth:sys_io `spike` 0.374 vs E `absent` 10.529; lead 10.155, margin 1.3e-06; tied 1 (win share 1/1); **win**
  - ep5 b1: metric:auth:sys_io `spike` 6.786 vs E `absent` 6.932; lead 0.146, margin 2e-06; tied 1 (win share 1/1); **win**
  - ep6 b2: metric:auth:sys_io `spike` 8.292 vs E `absent` 18.440; lead 10.148, margin 1.5e-06; tied 1 (win share 1/1); **win**
  - ep7 b3: metric:auth:sys_io `spike` 7.160 vs E `absent` 2.324; lead -4.836, margin 1.1e-06; tied 1 (win share 0/1); **not faster**
- P4b persistence-cpu-throttle r10 (candidates 7; paired differences ledger - sensor: mean -0.142 [-0.985, 0.218] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 0.589 vs E `median` 0.235; lead -0.354, margin 1.3e-05; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 1.183 vs E `run3` 1.296; lead 0.113, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep3 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 0.560 vs E `median` 0.408; lead -0.152, margin 1.4e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:persistence:UserRepository.getUserByName `spike` 1.278 vs E `median` 0.293; lead -0.985, margin 2.7e-05; tied 1 (win share 0/1); **not faster**
  - ep5 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 0.480 vs E `run3` 0.629; lead 0.149, margin 6.4e-05; tied 1 (win share 1/1); **win**
  - ep6 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 1.263 vs E `spike` 1.277; lead 0.015, margin 2.8e-05; tied 1 (win share 1/1); **win**
  - ep7 b3: span:persistence:CategoryEndpoint.listAllEntities `spike` 0.715 vs E `spike` 0.933; lead 0.218, margin 1.3e-05; tied 1 (win share 1/1); **win**
- P4b persistence-cpu-throttle r1 (candidates 6; paired differences ledger - sensor: mean -0.106 [-3.780, 1.938] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 1.009 vs E `median` 2.929; lead 1.920, margin 1.4e-05; tied 1 (win share 1/1); **win**
  - ep2 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 0.881 vs E `median` 2.818; lead 1.938, margin 1.5e-05; tied 1 (win share 1/1); **win**
  - ep3 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 1.148 vs E `median` 2.165; lead 1.018, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep4 b3: span:persistence:CategoryEndpoint.listAllEntities `spike` 5.641 vs E `spike` 1.862; lead -3.780, margin 1.2e-05; tied 1 (win share 0/1); **not faster**
  - ep5 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 5.010 vs E `spike` 5.031; lead 0.021, margin 1.3e-05; tied 1 (win share 1/1); **win**
  - ep6 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 0.261 vs E `spike` 1.482; lead 1.221, margin 1.7e-05; tied 1 (win share 1/1); **win**
  - ep7 b3: span:persistence:CategoryEndpoint.listAllEntities `spike` 3.595 vs E `spike` 0.516; lead -3.079, margin 1.5e-05; tied 1 (win share 0/1); **not faster**
- P4b persistence-cpu-throttle r0.2 (candidates 7; paired differences ledger - sensor: mean -0.681 [-4.976, 0.092] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 9.095 vs E `spike` 9.187; lead 0.092, margin 4.1e-06; tied 1 (win share 1/1); **win**
  - ep2 b1: span:persistence:CategoryEndpoint.listAllEntities `absent` 18.568 vs E `absent` 18.590; lead 0.023, margin 1.1e-05; tied 1 (win share 0/1); **unclassifiable (no silence-ending or silence-starting token)** (decision 57: the silence-ending observation names no request; decision 58: the silence-starting observation names no request) [lead = 0.023 start + 0.00031 gap + -1.2e-07]
  - ep3 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 2.517 vs E `spike` 2.545; lead 0.029, margin 1e-05; tied 1 (win share 1/1); **win**
  - ep4 b3: span:persistence:CategoryEndpoint.listAllEntities `spike` 3.449 vs E `spike` 3.469; lead 0.020, margin 1.1e-05; tied 1 (win share 1/1); **win**
  - ep5 b1: span:persistence:CategoryEndpoint.listAllEntities `spike` 9.915 vs E `spike` 4.938; lead -4.976, margin 2.1e-06; tied 1 (win share 0/1); **not faster**
  - ep6 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 5.643 vs E `spike` 5.667; lead 0.024, margin 2.1e-06; tied 1 (win share 1/1); **win**
  - ep7 b3: span:persistence:CategoryEndpoint.listAllEntities `spike` 21.896 vs E `spike` 21.922; lead 0.026, margin 2.4e-06; tied 1 (win share 1/1); **win**
- P4b persistence-cpu-throttle r0.05 (candidates 8; paired differences ledger - sensor: mean -10.295 [-40.123, -0.113] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:persistence:UserRepository.getUserByName `spike` 34.190 vs E `absent` 34.017; lead -0.172, margin 1.7e-06; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:persistence:UserRepository.getUserByName `spike` 30.528 vs E `spike` 5.446; lead -25.081, margin 9.5e-07; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:persistence:UserRepository.getUserByName `spike` 7.867 vs E `absent` 7.754; lead -0.113, margin 1.2e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:persistence:UserRepository.getUserByName `—` — vs E `absent` 57.410; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep5 b1: span:persistence:UserRepository.getUserByName `spike` 27.328 vs E `absent` 27.196; lead -0.132, margin 1.4e-06; tied 1 (win share 0/1); **not faster**
  - ep6 b2: span:persistence:CategoryEndpoint.listAllEntities `spike` 40.699 vs E `absent` 0.577; lead -40.123, margin 1.9e-06; tied 1 (win share 0/1); **not faster**
  - ep7 b3: span:persistence:UserRepository.getUserByName `spike` 21.996 vs E `absent` 18.272; lead -3.724, margin 1.2e-06; tied 1 (win share 0/1); **not faster**

**Per harness** (decision 49 pools the sweep's episode with campaign B's three; V3_HARNESS_TAG_RULE; tags B, sweep). Episodes per class and rate: auth-freeze r0.05 B 6, sweep 1; auth-freeze r0.2 B 6, sweep 1; auth-freeze r1 B 6, sweep 1; auth-freeze r10 B 6, sweep 1; persistence-cpu-throttle r0.05 B 6, sweep 1; persistence-cpu-throttle r0.2 B 6, sweep 1; persistence-cpu-throttle r1 B 6, sweep 1; persistence-cpu-throttle r10 B 6, sweep 1.

- P1 holds per harness: B 24/24, sweep 4/4; P2 within the bound per harness: r10 B 6/6, sweep 1/1; r1 B 6/6, sweep 1/1; r0.2 B 6/6, sweep 1/1; r0.05 B 6/6, sweep 1/1.
- P4 optimistic P4a auth-freeze r0.05: wins / folds by the held-out episode's harness: B 2/6, sweep 1/1
- P4 optimistic P4a auth-freeze r0.2: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4a auth-freeze r1: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4a auth-freeze r10: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4a persistence-cpu-throttle r0.05: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4a persistence-cpu-throttle r0.2: wins / folds by the held-out episode's harness: B 5/6, sweep 1/1
- P4 optimistic P4a persistence-cpu-throttle r1: wins / folds by the held-out episode's harness: B 2/6, sweep 1/1
- P4 optimistic P4a persistence-cpu-throttle r10: wins / folds by the held-out episode's harness: B 3/6, sweep 0/1
- P4 optimistic P4b auth-freeze r0.05: wins / folds by the held-out episode's harness: B 5/6, sweep 1/1
- P4 optimistic P4b auth-freeze r0.2: wins / folds by the held-out episode's harness: B 1/6, sweep 1/1
- P4 optimistic P4b auth-freeze r1: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4b auth-freeze r10: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4b persistence-cpu-throttle r0.05: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4b persistence-cpu-throttle r0.2: wins / folds by the held-out episode's harness: B 4/6, sweep 1/1
- P4 optimistic P4b persistence-cpu-throttle r1: wins / folds by the held-out episode's harness: B 4/6, sweep 1/1
- P4 optimistic P4b persistence-cpu-throttle r10: wins / folds by the held-out episode's harness: B 4/6, sweep 0/1
- P4 primary P4a auth-freeze r0.05: wins / folds by the held-out episode's harness: B 2/6, sweep 0/1
- P4 primary P4a auth-freeze r0.2: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4a auth-freeze r1: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4a auth-freeze r10: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4a persistence-cpu-throttle r0.05: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4a persistence-cpu-throttle r0.2: wins / folds by the held-out episode's harness: B 5/6, sweep 1/1
- P4 primary P4a persistence-cpu-throttle r1: wins / folds by the held-out episode's harness: B 2/6, sweep 1/1
- P4 primary P4a persistence-cpu-throttle r10: wins / folds by the held-out episode's harness: B 3/6, sweep 0/1
- P4 primary P4b auth-freeze r0.05: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4b auth-freeze r0.2: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4b auth-freeze r1: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4b auth-freeze r10: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4b persistence-cpu-throttle r0.05: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4b persistence-cpu-throttle r0.2: wins / folds by the held-out episode's harness: B 4/6, sweep 1/1
- P4 primary P4b persistence-cpu-throttle r1: wins / folds by the held-out episode's harness: B 4/6, sweep 1/1
- P4 primary P4b persistence-cpu-throttle r10: wins / folds by the held-out episode's harness: B 1/6, sweep 0/1

**Beside the primary** (highest rate where P4 holds):

| verdict | calibrated (primary) | floor arm | <= 1 held-out alarm | optimistic bound (not evidence) |
|---|---|---|---|---|
| P4a auth-freeze | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a persistence-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b auth-freeze | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b persistence-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC auth-freeze | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC persistence-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC auth-freeze | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC persistence-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |

## Out-of-sample check (decision 65, 67): calibrated detectors on --validation no-fault cells, no refit

Validation campaigns: `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1` (input digest `f5e8db0bce46d85a1670b024586e6293e31f69963094e6f8ff6d880116e662ce`). Not used: `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/auth-freeze-effect/b01-01-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/auth-freeze-effect/b01-04-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/auth-freeze-effect/b01-09-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/auth-freeze-effect/b01-10-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/auth-freeze-effect/b02-01-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/auth-freeze-effect/b02-02-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/auth-freeze-effect/b02-07-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/auth-freeze-effect/b02-09-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/auth-freeze-effect/b03-06-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/auth-freeze-effect/b03-07-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/auth-freeze-effect/b03-09-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/auth-freeze-effect/b03-10-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/persistence-cpu-throttle-effect/b01-03-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/persistence-cpu-throttle-effect/b01-06-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/persistence-cpu-throttle-effect/b01-07-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/persistence-cpu-throttle-effect/b01-11-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/persistence-cpu-throttle-effect/b02-06-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/persistence-cpu-throttle-effect/b02-08-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/persistence-cpu-throttle-effect/b02-11-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/persistence-cpu-throttle-effect/b02-12-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/persistence-cpu-throttle-effect/b03-01-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/persistence-cpu-throttle-effect/b03-04-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/persistence-cpu-throttle-effect/b03-05-full` (a fault cell (validation uses no-fault cells only)); `tmp/teastorec1r1-evidence/x/teastore-traffic-sweep-c-v1/runs/persistence-cpu-throttle-effect/b03-12-full` (a fault cell (validation uses no-fault cells only)).

- r10: 3 cells, 0.150 h (limit of this check: 20.0/h for 0 alarms); rules alarming 10 of 588 calibrated: `metric:auth:sys_psi_cpu/spike 1`, `metric:persistence:sys_psi_cpu/run3 1`, `metric:rabbitmq:sys_psi_cpu/median 1`, `span:auth:AuthUserActionsRest.isLoggedIn/spike 1`, `span:auth:AuthUserActionsRest.login/spike 1`, `span:auth:RandomSessionIdGenerator.getSessionId/median 1`, `span:auth:ShaSecurityProvider.validate/spike 1`, `span:image:ImageProvider.getImageFor/run3 1`, `span:image:ImageProviderEndpoint.getWebUIImages/run3 1`, `span:image:ImageProviderEndpoint.getWebUIImages/spike 1`; sensors alarming 9 of 464 placeable; all placeable sensors' union 13 (86.7/h [137.8], 0.15 of 0.15 h)
  - P4a auth-freeze-effect r10: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4a persistence-cpu-throttle-effect r10: 1 (6.7/h [31.6], 0.15 of 0.15 h)
  - P4b auth-freeze-effect r10: 1 (6.7/h [31.6], 0.15 of 0.15 h)
  - P4b persistence-cpu-throttle-effect r10: 0 (0.0/h [20.0], 0.15 of 0.15 h)
- r1: 3 cells, 0.150 h (limit of this check: 20.0/h for 0 alarms); rules alarming 2 of 596 calibrated: `span:auth:ShaSecurityProvider.getKeyProvider/run3 9`, `span:persistence:CategoryEndpoint.listAllEntities/spike 1`; sensors alarming 2 of 463 placeable; all placeable sensors' union 18 (120.0/h [177.9], 0.15 of 0.15 h)
  - P4a auth-freeze-effect r1: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4a persistence-cpu-throttle-effect r1: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4b auth-freeze-effect r1: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4b persistence-cpu-throttle-effect r1: 1 (6.7/h [31.6], 0.15 of 0.15 h)
- r0.2: 3 cells, 0.150 h (limit of this check: 20.0/h for 0 alarms); rules alarming 3 of 593 calibrated: `ledger:webui:login-only-v1/spike 1`, `metric:persistence:sys_psi_cpu/spike 1`, `span:webui:IndexServlet.handleGETRequest/spike 1`; sensors alarming 2 of 464 placeable; all placeable sensors' union 2 (13.3/h [42.0], 0.15 of 0.15 h)
  - P4a auth-freeze-effect r0.2: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4a persistence-cpu-throttle-effect r0.2: 1 (6.7/h [31.6], 0.15 of 0.15 h)
  - P4b persistence-cpu-throttle-effect r0.2: 0 (0.0/h [20.0], 0.15 of 0.15 h)
- r0.05: 3 cells, 0.150 h (limit of this check: 20.0/h for 0 alarms); rules alarming 2 of 592 calibrated: `metric:registry:sys_cpu/run3 1`, `span:persistence:PersistenceCategory.getId/run3 1`; sensors alarming 2 of 461 placeable; all placeable sensors' union 3 (20.0/h [51.7], 0.15 of 0.15 h)
  - P4a auth-freeze-effect r0.05: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4a persistence-cpu-throttle-effect r0.05: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4b persistence-cpu-throttle-effect r0.05: 0 (0.0/h [20.0], 0.15 of 0.15 h)

## Primary outcome: time to detection at the calibrated values, misses charged at the hold end

Detected k/n · median [min-max] · **mean over all n** (with BC catches), then without BC. `—` = channel missing.

| class | rate | n | E | E no BC | L | L no BC | M | M no BC | S | S no BC | T | T no BC | L:own | L:own no BC | M:own | M:own no BC | S:own | S:own no BC | T:own | T:own no BC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| auth-freeze | 10 | 7 | 7/7 · 0.51 [0.48–0.55] · **0.51** | (= E) | 7/7 · 10.20 [9.79–11.73] · **10.51** | 7/7 · 16.55 [16.40–17.28] · **16.70** | — | — | 7/7 · 14.91 [14.85–14.98] · **14.91** | 7/7 · 14.91 [14.85–14.98] · **14.91** | 7/7 · 0.46 [0.43–0.50] · **0.46** | 7/7 · 10.48 [10.28–11.43] · **10.74** | 0/7 · **60.24** | 0/7 · **60.24** | — | — | 7/7 · 4.91 [4.85–4.98] · **4.91** | 7/7 · 14.91 [14.85–14.98] · **14.91** | 7/7 · 0.47 [0.45–0.52] · **0.47** | 0/7 · **60.24** |
| auth-freeze | 1 | 7 | 7/7 · 1.61 [1.04–1.78] · **1.44** | (= E) | 7/7 · 11.41 [9.66–11.75] · **10.93** | 7/7 · 30.00 [29.05–31.62] · **30.22** | — | — | 7/7 · 14.32 [13.96–14.86] · **14.41** | 7/7 · 23.95 [14.04–54.29] · **24.41** | 7/7 · 1.49 [0.92–1.66] · **1.32** | 7/7 · 19.47 [18.41–19.73] · **19.28** | 0/7 · **60.24** | 0/7 · **60.24** | — | — | 7/7 · 14.32 [13.96–14.86] · **14.41** | 7/7 · 14.32 [13.96–14.86] · **14.41** | 7/7 · 1.49 [0.93–1.66] · **1.32** | 0/7 · **60.24** |
| auth-freeze | 0.2 | 7 | 7/7 · 4.71 [2.83–6.61] · **4.98** | (= E) | 7/7 · 10.59 [9.89–11.67] · **10.82** | 7/7 · 29.03 [27.49–31.32] · **29.37** | — | — | 7/7 · 28.30 [11.09–31.84] · **25.17** | 6/7 · 28.57 [22.03–31.84] · **32.19** | 7/7 · 4.62 [2.80–6.52] · **4.91** | 7/7 · 21.31 [19.52–23.36] · **21.67** | 0/7 · **60.24** | 0/7 · **60.24** | — | — | 0/7 · **60.24** | 0/7 · **60.24** | 7/7 · 4.65 [2.79–6.56] · **4.93** | 0/7 · **60.24** |
| auth-freeze | 0.05 | 7 | 7/7 · 6.93 [1.43–18.44] · **9.03** | (= E) | 7/7 · 10.18 [9.07–11.72] · **10.29** | 7/7 · 21.24 [11.98–29.80] · **21.23** | — | — | 6/7 · 22.45 [12.16–31.68] · **28.14** | 6/7 · 22.45 [12.16–31.68] · **28.14** | 7/7 · 6.91 [1.41–18.42] · **9.01** | 5/7 · 25.89 [20.48–29.79] · **34.83** | 0/7 · **60.24** | 0/7 · **60.24** | — | — | 0/7 · **60.24** | 0/7 · **60.24** | 7/7 · 6.86 [1.35–18.37] · **8.95** | 0/7 · **60.24** |
| persistence-cpu-throttle | 10 | 7 | 7/7 · 0.63 [0.23–1.30] · **0.72** | (= E) | 7/7 · 11.79 [10.06–13.34] · **11.78** | 7/7 · 11.79 [10.06–13.34] · **11.78** | — | — | 7/7 · 14.90 [10.00–14.94] · **14.20** | 7/7 · 14.90 [10.00–14.94] · **14.20** | 7/7 · 0.60 [0.21–1.29] · **0.66** | 7/7 · 0.60 [0.21–1.29] · **0.66** | 0/7 · **60.12** | 0/7 · **60.12** | — | — | 7/7 · 4.92 [4.84–5.00] · **4.92** | 0/7 · **60.12** | 7/7 · 0.92 [0.29–1.48] · **0.85** | 7/7 · 0.92 [0.29–1.48] · **0.85** |
| persistence-cpu-throttle | 1 | 7 | 7/7 · 2.17 [0.52–5.03] · **2.40** | (= E) | 4/7 · 30.46 [17.44–42.92] · **43.09** | 4/7 · 30.70 [17.44–42.92] · **43.16** | — | — | 4/7 · 14.74 [14.31–39.78] · **37.71** | 4/7 · 14.74 [14.31–39.78] · **37.71** | 7/7 · 2.16 [0.42–4.73] · **2.29** | 7/7 · 2.16 [0.42–4.73] · **2.29** | 0/7 · **60.12** | 0/7 · **60.12** | — | — | 7/7 · 4.48 [4.04–4.86] · **4.47** | 0/7 · **60.12** | 7/7 · 1.15 [0.26–5.64] · **2.51** | 7/7 · 1.15 [0.26–5.64] · **2.51** |
| persistence-cpu-throttle | 0.2 | 7 | 7/7 · 5.67 [2.55–21.92] · **9.47** | (= E) | 2/7 · 54.15 [53.14–55.16] · **58.41** | 2/7 · 55.11 [54.53–55.68] · **58.68** | — | — | 5/7 · 11.78 [10.53–13.30] · **25.60** | 5/7 · 11.78 [10.53–13.30] · **25.60** | 7/7 · 5.66 [2.54–21.92] · **9.47** | 7/7 · 5.66 [2.54–21.92] · **9.47** | 0/7 · **60.11** | 0/7 · **60.11** | — | — | 7/7 · 3.30 [0.93–5.53] · **3.24** | 0/7 · **60.11** | 7/7 · 9.10 [2.52–21.90] · **10.15** | 7/7 · 9.10 [2.52–21.90] · **10.15** |
| persistence-cpu-throttle | 0.05 | 7 | 7/7 · 18.27 [0.58–57.41] · **21.52** | (= E) | 2/7 · 34.75 [21.52–47.98] · **52.87** | 2/7 · 35.14 [22.06–48.21] · **52.98** | — | — | 0/7 · **60.12** | 0/7 · **60.12** | 7/7 · 18.19 [0.49–57.39] · **21.47** | 7/7 · 18.19 [0.49–57.39] · **21.47** | 0/7 · **60.12** | 0/7 · **60.12** | — | — | 7/7 · 2.61 [0.43–5.32] · **2.81** | 5/7 · 37.06 [10.42–58.88] · **44.22** | 7/7 · 22.00 [0.60–57.50] · **22.13** | 7/7 · 22.00 [0.60–57.50] · **22.13** |

## P1 detail (H4, decision 54)

- r10 b1: interval 0.201 s (intervention sweep.commandStamps onsetCommandReturnedMonotonicOffsetSeconds (the cell keeps no Docker events: [command issued, command returned])); expected [14.933, 15.233] +- 0.051 s; observed 11.804; holds via **error answer before the timeout (declared alternative)**
- r10 b1: interval 0.183 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.033, 15.233] +- 0.052 s; observed 13.094; holds via **error answer before the timeout (declared alternative)**
- r10 b2: interval 0.187 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [14.999, 15.200] +- 0.052 s; observed 11.825; holds via **error answer before the timeout (declared alternative)**
- r10 b3: interval 0.169 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.008, 15.208] +- 0.053 s; observed 11.931; holds via **error answer before the timeout (declared alternative)**
- r10 b1: interval 0.172 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [14.985, 15.185] +- 0.050 s; observed 12.447; holds via **error answer before the timeout (declared alternative)**
- r10 b2: interval 0.183 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [14.965, 15.165] +- 0.051 s; observed 12.501; holds via **error answer before the timeout (declared alternative)**
- r10 b3: interval 0.152 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [14.964, 15.165] +- 0.051 s; observed 11.574; holds via **error answer before the timeout (declared alternative)**
- r1 b1: interval 0.180 s (intervention sweep.commandStamps onsetCommandReturnedMonotonicOffsetSeconds (the cell keeps no Docker events: [command issued, command returned])); expected [15.310, 15.310] +- 0.062 s; observed 15.327; holds via **timeout interval**
- r1 b1: interval 0.179 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.525, 15.525] +- 0.066 s; observed 15.541; holds via **timeout interval**
- r1 b2: interval 0.169 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [14.942, 15.942] +- 0.063 s; observed 15.960; holds via **timeout interval**
- r1 b3: interval 0.161 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.848, 15.848] +- 0.067 s; observed 15.863; holds via **timeout interval**
- r1 b1: interval 0.163 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.023, 16.023] +- 0.063 s; observed 16.039; holds via **timeout interval**
- r1 b2: interval 0.158 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.281, 15.281] +- 0.063 s; observed 15.295; holds via **timeout interval**
- r1 b3: interval 0.188 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.850, 15.850] +- 0.065 s; observed 15.868; holds via **timeout interval**
- r0.2 b1: interval 0.182 s (intervention sweep.commandStamps onsetCommandReturnedMonotonicOffsetSeconds (the cell keeps no Docker events: [command issued, command returned])); expected [18.932, 18.932] +- 0.075 s; observed 18.950; holds via **timeout interval**
- r0.2 b1: interval 0.179 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [15.167, 15.167] +- 0.059 s; observed 15.184; holds via **timeout interval**
- r0.2 b2: interval 0.167 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [18.293, 18.293] +- 0.073 s; observed 18.311; holds via **timeout interval**
- r0.2 b3: interval 0.194 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [17.023, 17.023] +- 0.078 s; observed 17.041; holds via **timeout interval**
- r0.2 b1: interval 0.176 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [16.837, 16.837] +- 0.063 s; observed 16.852; holds via **timeout interval**
- r0.2 b2: interval 0.179 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [18.830, 18.830] +- 0.074 s; observed 18.847; holds via **timeout interval**
- r0.2 b3: interval 0.140 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [16.080, 16.080] +- 0.065 s; observed 16.098; holds via **timeout interval**
- r0.05 b1: interval 0.177 s (intervention sweep.commandStamps onsetCommandReturnedMonotonicOffsetSeconds (the cell keeps no Docker events: [command issued, command returned])); expected [21.686, 21.686] +- 0.083 s; observed 21.702; holds via **timeout interval**
- r0.05 b1: interval 0.185 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [16.282, 16.282] +- 0.085 s; observed 16.296; holds via **timeout interval**
- r0.05 b2: interval 0.145 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [31.619, 31.619] +- 0.083 s; observed 17.903; holds via **error answer before the timeout (declared alternative)**
- r0.05 b3: interval 0.139 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [25.379, 25.379] +- 0.078 s; observed 25.384; holds via **timeout interval**
- r0.05 b1: interval 0.207 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [21.791, 21.791] +- 0.078 s; observed 21.809; holds via **timeout interval**
- r0.05 b2: interval 0.194 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [33.296, 33.296] +- 0.075 s; observed 19.805; holds via **error answer before the timeout (declared alternative)**
- r0.05 b3: interval 0.192 s (Docker `pause` event of auth, intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped to the ledger's)); expected [17.166, 17.166] +- 0.083 s; observed 17.181; holds via **timeout interval**

- The ledger's calibrated `absent` against the client timeout: r10 login-only-v1: calibrated m 1 g 0.365 s vs timeout 15 s; `absent` before the first `failed` in 7/7 pause episodes; r1 login-only-v1: calibrated m 1.5 g 1.696 s vs timeout 15 s; `absent` before the first `failed` in 7/7 pause episodes; r0.2 login-only-v1: calibrated m 1.5 g 7.595 s vs timeout 15 s; `absent` before the first `failed` in 7/7 pause episodes; r0.05 login-only-v1: calibrated m 1 g 20.066 s vs timeout 15 s; `absent` before the first `failed` in 7/7 pause episodes.

## Exposure (H5): recorded, the objective unchanged

Route call path: auth, persistence, webui. Episodes with no request started in the fault window: 0 of 56. Never-exposed sensors: 265.

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
