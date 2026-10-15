# Traffic sweep, OTel Demo: analysis v3 (v3.1), exploratory, not frozen (every cell of this system was read under v2.4 before v3 was written) (retained + retained + retained + retained + otel)

**Exploratory, not frozen.** Protocol rounds 15 and 17 (decisions 61-65 as amended by 67) on v2.4's readers and rules; every cell read here was read under v2.4 first. **Scope: instance** (one SUT, one host). `—` = absent or not evaluable, never 0. Each (sensor, rule) is calibrated per rate by the zero-held-out-alarm selection; **no false-alarm figure here is that selection's own zero**: every count of false alarms is the honest nested leave-one-cell-out count (V3_NESTED_RULE), with its exact 95 % bound.

Binding documents and inputs: research/PROTOCOL_DRAFT_20261002.md round 15 (decisions 61-65, 252cfcd); research/protocol/ANALYSIS_V3_DESIGN.md (252cfcd); research/traffic-sweep/SYNTHESIS_V2_4.md; research/protocol/parameters_v3.json (decision 37); research/traffic-sweep/DECLARATION_OTEL.md (da95915); research/traffic-sweep/AMENDMENT_OTEL_1.md (16ae373); research/traffic-sweep/DECLARATION_QUIET_OTEL.md (593d4ee); research/protocol/METHODOLOGY_HARDENING.md (H1-H11); research/PROTOCOL_DRAFT_20261002.md rounds 7-14 (decisions 26-60; decision 57 = d126589, round 13 = 6162c37, round 14 = c17f6a6); harness observability-placement-runtime-otel-protocol 6e37ec2 (the cell writer and terminal); research/protocol/parameters.json (decision 37).

Analysis: `research/detection-time/sweep_analysis_v3.py` v3 (sha256 `2e7ec5c387fa906a02026f0d1a5212b974f17751c24f76526a1d8418b2fd4fdd`) on v2.4 `sweep_analysis_v2.py` (sha256 `075c43e5870170c8b59cdbe1a970b56dc03920d67514027b9a95e5de38d962e9`), parameters.json `7447b492abf64f42ebaf547a640c84929ac15b59ebc1e495d5082f279373fc68`, parameters_v3.json `212830bec3e6669bc211d5cffa48d61fa3bf0f6d4dd5ceaf79d3e2bcc7c4d000`, HEAD `fdbdb16bc30fc8ffb0b631bb133d49871ed17e24`, Python 3.13.12.

## Outputs that are — by construction

- family S (primary and secondary columns, operating point, P4 candidates): OTel sweep cells keep no cgroup or docker-stats sampler (resources.json holds two docker-engine CPU counters, before and after the window; FAMILY_CHANNELS).
- availability-clock P4 verdict for family M: no measured collector receive stamp (AVAILABILITY_SOURCES, decision 43).
- availability-clock P4 verdict for family T: no measured collector receive stamp (AVAILABILITY_SOURCES, decision 43).
- P3 (every fault): no family is traffic-independent by mechanism (H11).
- Docker pause event as the onset interval's upper bound (H4) in 4 of 28 pause episodes: those cells carry no freeze-event source (V3_FREEZE_EVENTS_RULE): the interval is [command issued, command returned], v2.4's.
- a false-alarm figure from the zero-alarm selection itself: never printed (decision 67): the selected value has 0 held-out alarms on the cells it was chosen on by construction; every false-alarm count below is the honest nested one.

## What was read

Campaigns pooled (H1; decision 68: quiet runs A and A2 pool with the sweep):

- `tmp/otel-sweep-evidence/relaunch1-fetch/retained`: 12 valid of 12 (frontend-pause 4, no-fault-calibration 4, productcatalog-cpu-throttle 4)
- `tmp/otel-b-evidence/b1-faultview/retained`: 24 valid of 24 (frontend-pause 12, productcatalog-cpu-throttle 12)
- `tmp/otel-quiet-evidence/relaunch1-fetch/retained`: 40 valid of 40 (no-fault-calibration 40)
- `tmp/otel-quiet-evidence/a2-fetch/retained`: 40 valid of 40 (no-fault-calibration 40)
- `tmp/c-fault-copy/otel`: 24 valid of 24 (frontend-pause 12, productcatalog-cpu-throttle 12)

| class | r10 valid/found | r1 valid/found | r0.2 valid/found | r0.05 valid/found |
|---|---|---|---|---|
| no-fault-calibration | 21/21 | 21/21 | 21/21 | 21/21 |
| frontend-pause | 7/7 | 7/7 | 7/7 | 7/7 |
| productcatalog-cpu-throttle | 7/7 | 7/7 | 7/7 | 7/7 |

Cells not scored: none.

Provenance: harness commit —; input digest `23d9621645a7c95644d002b28025c9daf93cdc9670ecf511ec180405add61b13` over 640 files (v2.4's file set plus docker-events.json[l]).

H4 freeze record per harness and status (V3_FREEZE_EVENTS_RULE; decision 69: a missing or contradictory record keeps the sweep's bound and is counted): B: recorded (throttle: command and readback stamps; v2.4's bound kept) 24, used 24; sweep: not recorded (sweep harness) 8; reasons: none.

Reader statistics over the valid cells (F11; a drop is counted, never silent): bridgeMappings 0; bridgeTokensWithSeveralTraces 0; bridgeTracesWithSeveralTokens 0; bridgeRowsDropped 0; tracesWithoutToken 45177; probeTracesExcluded 67; probeSpansExcluded 452; spansIncomplete 0; spansUnusable 0; duplicateSpans 0; journeysWithoutStart 0; samplePairsSkipped 0; logRecordsUntimed 1; composeCliLines 0.

## Calibration per (sensor, rule) on the no-fault cells (decisions 61-63, 67)

Each armed (sensor, rule) takes the smallest grid value with zero held-out alarms over the rate's no-fault cells, each scored leave-one-cell-out (v2.4's fit, H1; class-independent). Level rules: K_GRID (<= 100; K = 100 flagged at grid edge), then the range fallback (discrete in effect; up-only for spans and the ledger; may apply where MAD = 0, decision 52 kept for K); `absent`: m x G on m in {1, 1.5, 2, 3, 5}, G including the censored silences of cells with records; an `absent` whose gap exceeds the shortest hold (60.011 s) is **inert**; `appear` per stream; the ledger's `failed` exempt. **honest** = the nested count (each held-out cell at the value re-selected without it), the false-alarm figure; its rate per hour of no-fault time T.

| rate | no-fault cells | T (h) | rules calibrated / dropped / inert / unarmed | at grid edge | range (of them MAD = 0) | sensors placeable / appear-only / not (L, M, S, T) | dof | E `failed` in no-fault (exempt) | calibrated rules: median folds armed of the rate's cells · out of the detector in every nested fold · honest — (no nested evidence) | placeable sensors with CELF cost — |
|---|---|---|---|---|---|---|---|---|---|---|
| r10 | 21 | 1.050 | 1577 / 10 / 32 / 1436 | 1 | 198 (189) | 238 / 872 / 148 | 705 | /api/products/66VCHSJNUP 6 | 21 of 21 · 27 · 27 | 146 |
| r1 | 21 | 1.050 | 1608 / 7 / 32 / 1462 | 2 | 190 (186) | 238 / 900 / 147 | 708 | /api/products/66VCHSJNUP 0 | 21 of 21 · 27 · 27 | 142 |
| r0.2 | 21 | 1.050 | 1604 / 10 / 32 / 1461 | 0 | 192 (185) | 238 / 899 / 147 | 705 | /api/products/66VCHSJNUP 0 | 21 of 21 · 30 · 30 | 171 |
| r0.05 | 21 | 1.050 | 1579 / 10 / 32 / 1439 | 6 | 218 (209) | 239 / 871 / 149 | 708 | /api/products/66VCHSJNUP 0 | 21 of 21 · 21 · 21 | 139 |

Per family and rule (primary): calibrated / dropped / inert / unarmed.

| rate | family | appear | absent | spike | run3 | median |
|---|---|---|---|---|---|---|
| r10 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r10 | L | 808 / 0 / 0 / 35 | 5 / 0 / 29 / 809 | — | — | — |
| r10 | M | — | — | 213 / 10 / 0 / 118 | 223 / 0 / 0 / 118 | 223 / 0 / 0 / 118 |
| r10 | T | 64 / 0 / 0 / 10 | 7 / 0 / 3 / 57 | 10 / 0 / 0 / 57 | 10 / 0 / 0 / 57 | 10 / 0 / 0 / 57 |
| r1 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r1 | L | 836 / 0 / 0 / 34 | 5 / 0 / 29 / 836 | — | — | — |
| r1 | M | — | — | 217 / 6 / 0 / 118 | 223 / 0 / 0 / 118 | 223 / 0 / 0 / 118 |
| r1 | T | 64 / 0 / 0 / 10 | 7 / 0 / 3 / 57 | 9 / 1 / 0 / 57 | 10 / 0 / 0 / 57 | 10 / 0 / 0 / 57 |
| r0.2 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r0.2 | L | 835 / 0 / 0 / 34 | 5 / 0 / 29 / 835 | — | — | — |
| r0.2 | M | — | — | 213 / 10 / 0 / 118 | 223 / 0 / 0 / 118 | 223 / 0 / 0 / 118 |
| r0.2 | T | 64 / 0 / 0 / 10 | 7 / 0 / 3 / 57 | 10 / 0 / 0 / 57 | 10 / 0 / 0 / 57 | 10 / 0 / 0 / 57 |
| r0.05 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r0.05 | L | 807 / 0 / 0 / 34 | 5 / 0 / 29 / 807 | — | — | — |
| r0.05 | M | — | — | 214 / 10 / 0 / 120 | 224 / 0 / 0 / 120 | 224 / 0 / 0 / 120 |
| r0.05 | T | 64 / 0 / 0 / 10 | 7 / 0 / 3 / 57 | 10 / 0 / 0 / 57 | 10 / 0 / 0 / 57 | 10 / 0 / 0 / 57 |

**The ledger E** per rate (route; `failed` **exempt**, decision 63: never calibrated, always compared; its no-fault count is reported):

- r10: `absent` calibrated (m 1, honest 0); `failed` exempt (no-fault count 6); `median` calibrated (K 4, honest 1); `run3` calibrated (K 12.5, honest 1); `spike` calibrated (range, honest 0).
- r1: `absent` calibrated (m 1, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 16, honest 1); `run3` calibrated (K 8, honest 0); `spike` calibrated (K 31.5, honest 1).
- r0.2: `absent` calibrated (m 1.5, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 80, honest 1).
- r0.05: `absent` calibrated (m 1.5, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 8, honest 0).
- E's catching rule in the episodes (primary): frontend-pause r0.05: `absent` 7; frontend-pause r0.2: `absent` 7; frontend-pause r1: `absent` 7; frontend-pause r10: `absent` 7; productcatalog-cpu-throttle r0.05: `—` 7; productcatalog-cpu-throttle r0.2: `—` 7; productcatalog-cpu-throttle r1: `spike` 1, `—` 6; productcatalog-cpu-throttle r10: `—` 7.

**Dropped (sensor, rule) pairs** (held-out alarms at the last grid value; honest count beside), primary:

- r10 (10): `metric:productcatalogservice:process.runtime.go.gc.count/spike` 2 (honest —), `metric:productcatalogservice:process.runtime.go.gc.pause_ns~rate/spike` 2 (honest —), `metric:adservice:jvm.gc.duration~rate/spike` 1 (honest —), `metric:cartservice:process.runtime.dotnet.thread_pool.threads.count/spike` 1 (honest 1), `metric:cartservice:process.thread.count/spike` 1 (honest 1), `metric:frauddetectionservice:jvm.gc.duration~rate/spike` 1 (honest —), `metric:frauddetectionservice:kafka.consumer.connection_close_rate/spike` 1 (honest 1), `metric:frauddetectionservice:kafka.consumer.failed_rebalance_rate_per_hour/spike` 1 (honest 1), `metric:frauddetectionservice:kafka.consumer.incoming_byte_rate/spike` 1 (honest —), `metric:recommendationservice:system.cpu.utilization/spike` 1 (honest —)
- r1 (7): `metric:frauddetectionservice:kafka.consumer.heartbeat_response_time_max/spike` 2 (honest 5), `metric:adservice:jvm.gc.duration~rate/spike` 1 (honest —), `metric:frauddetectionservice:jvm.cpu.recent_utilization/spike` 1 (honest 1), `metric:frauddetectionservice:jvm.gc.duration~rate/spike` 1 (honest 1), `metric:frauddetectionservice:jvm.thread.count/spike` 1 (honest 1), `metric:recommendationservice:system.cpu.utilization/spike` 1 (honest 1), `span:frontend:GET/spike` 1 (honest 1)
- r0.2 (10): `metric:adservice:jvm.gc.duration~rate/spike` 1 (honest —), `metric:adservice:jvm.thread.count/spike` 1 (honest 1), `metric:frauddetectionservice:jvm.gc.duration~rate/spike` 1 (honest —), `metric:frauddetectionservice:jvm.thread.count/spike` 1 (honest 1), `metric:frauddetectionservice:kafka.consumer.connection_close_rate/spike` 1 (honest —), `metric:frauddetectionservice:kafka.consumer.connection_creation_rate/spike` 1 (honest 1), `metric:frauddetectionservice:kafka.consumer.failed_rebalance_rate_per_hour/spike` 1 (honest —), `metric:frauddetectionservice:kafka.consumer.heartbeat_response_time_max/spike` 1 (honest 1), `metric:frauddetectionservice:kafka.consumer.incoming_byte_rate/spike` 1 (honest —), `metric:recommendationservice:system.cpu.utilization/spike` 1 (honest 1)
- r0.05 (10): `metric:frontend:calls/spike` 2 (honest —), `metric:frontend:duration~rate/spike` 2 (honest —), `metric:frontend:http.server.duration~rate/spike` 2 (honest —), `metric:adservice:jvm.gc.duration~rate/spike` 1 (honest —), `metric:checkoutservice:process.runtime.go.gc.count/spike` 1 (honest 1), `metric:checkoutservice:process.runtime.go.gc.pause_ns~rate/spike` 1 (honest 1), `metric:frauddetectionservice:jvm.gc.duration~rate/spike` 1 (honest —), `metric:frontend:app.frontend.requests/spike` 1 (honest 1), `metric:productcatalogservice:process.runtime.go.gc.pause_total_ns/spike` 1 (honest —), `metric:recommendationservice:system.cpu.utilization/spike` 1 (honest 1)

**Inert** (calibrated by the selection, but the gap exceeds the hold; not placeable), **at grid edge** (K = 100) and **appear-only** sensors (placeable through `appear` alone, listed apart), primary:

- r10: inert 32: `log:frontendproxy:1982b925695b/absent`, `log:frontendproxy:d2080adea2c3/absent`, `log:kafka:1367c637eda2/absent`, `log:kafka:19ebc4c406cc/absent`, `log:kafka:1b6bb55dcf25/absent`, `log:kafka:1c75c94f4019/absent`, `log:kafka:209d095cee84/absent`, `log:kafka:23de8a6634a0/absent`, `log:kafka:2848bf7b5ce9/absent`, `log:kafka:2f43a13b18ce/absent`, `log:kafka:4af8ca5c0f4a/absent`, `log:kafka:51bdc291db56/absent`, `log:kafka:530e610ccce9/absent`, `log:kafka:5dc9c5402d61/absent`, `log:kafka:6f8bc6db7c40/absent`, `log:kafka:70cc1a05fda1/absent`, `log:kafka:7d4c1c1d3761/absent`, `log:kafka:84752691105b/absent`, `log:kafka:8ab6ffc7e081/absent`, `log:kafka:90a317961466/absent`, `log:kafka:b4f1a5dde2b9/absent`, `log:kafka:b8bad87e414f/absent`, `log:kafka:c18fc626cf23/absent`, `log:kafka:dd1c07008ef5/absent`, `log:kafka:dfe6bc88aede/absent`, `log:kafka:ed47e2a9155d/absent`, `log:kafka:efc900fc673f/absent`, `log:kafka:f2af4ad9f40a/absent`, `log:kafka:f8e6273cf6c7/absent`, `span:frontend:GET_//absent`, `span:frontend:render_route_(pages)_//absent`, `span:frontend:resolve_page_components/absent`; at grid edge 1: `span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct/spike`; appear-only 872: `log:accountingservice:020200dc7516`, `log:accountingservice:0de465075c04`, `log:accountingservice:1beb330393a9`, `log:accountingservice:33a6342b9bdb`, `log:accountingservice:34d5bac2ad4c`, `log:accountingservice:396e4d6de49a`, `log:accountingservice:4effb619229a`, `log:accountingservice:4fafe2bb2232`, `log:accountingservice:6914926388fe`, `log:accountingservice:777c0dd6ebb5`, `log:accountingservice:7f002e6ec6b1`, `log:accountingservice:9a7a46c343db`, `log:accountingservice:9b571bf8f84c`, `log:accountingservice:b526f7e58c37`, `log:accountingservice:b6f2976d0cc7`, `log:accountingservice:b8c4b352bb62`, `log:accountingservice:d226aab7909f`, `log:accountingservice:d40fabb1daa8`, `log:accountingservice:ed7c55d1722e`, `log:accountingservice:f6d2a8fd7279`, `log:accountingservice:f70ba64be717`, `log:accountingservice:f904ab2a1231`, `log:adservice:15386f04ccf3`, `log:adservice:237bd2e48941`, `log:adservice:46aa7009ba09`, `log:adservice:5966dd28c645`, `log:adservice:6b83755ca1d0`, `log:adservice:eb13be1d2f61`, `log:adservice:ec57eec38dad`, `log:adservice:f7061b25a6f8`, `log:cartservice:9d2d534593fb`, `log:cartservice:aa11e5efcab9`, `log:cartservice:f3b5e31a4607`, `log:checkoutservice:00c505ab948d`, `log:checkoutservice:0275347e05a2`, `log:checkoutservice:033988248b04`, `log:checkoutservice:03df4624025e`, `log:checkoutservice:047f41bbf6c2`, `log:checkoutservice:04f6d3111fab`, `log:checkoutservice:0533d4fad6dc` (+832 more in the JSON).
- r1: inert 32: `log:frontendproxy:1982b925695b/absent`, `log:frontendproxy:d2080adea2c3/absent`, `log:kafka:1367c637eda2/absent`, `log:kafka:19ebc4c406cc/absent`, `log:kafka:1b6bb55dcf25/absent`, `log:kafka:1c75c94f4019/absent`, `log:kafka:209d095cee84/absent`, `log:kafka:23de8a6634a0/absent`, `log:kafka:2848bf7b5ce9/absent`, `log:kafka:2f43a13b18ce/absent`, `log:kafka:4af8ca5c0f4a/absent`, `log:kafka:51bdc291db56/absent`, `log:kafka:530e610ccce9/absent`, `log:kafka:5dc9c5402d61/absent`, `log:kafka:6f8bc6db7c40/absent`, `log:kafka:70cc1a05fda1/absent`, `log:kafka:7d4c1c1d3761/absent`, `log:kafka:84752691105b/absent`, `log:kafka:8ab6ffc7e081/absent`, `log:kafka:90a317961466/absent`, `log:kafka:b4f1a5dde2b9/absent`, `log:kafka:b8bad87e414f/absent`, `log:kafka:c18fc626cf23/absent`, `log:kafka:dd1c07008ef5/absent`, `log:kafka:dfe6bc88aede/absent`, `log:kafka:ed47e2a9155d/absent`, `log:kafka:efc900fc673f/absent`, `log:kafka:f2af4ad9f40a/absent`, `log:kafka:f8e6273cf6c7/absent`, `span:frontend:GET_//absent`, `span:frontend:render_route_(pages)_//absent`, `span:frontend:resolve_page_components/absent`; at grid edge 2: `metric:frauddetectionservice:kafka.consumer.incoming_byte_rate/spike`, `span:frontend:resolve_page_components/spike`; appear-only 900: `log:accountingservice:020200dc7516`, `log:accountingservice:0de465075c04`, `log:accountingservice:1beb330393a9`, `log:accountingservice:33a6342b9bdb`, `log:accountingservice:34d5bac2ad4c`, `log:accountingservice:396e4d6de49a`, `log:accountingservice:4effb619229a`, `log:accountingservice:4fafe2bb2232`, `log:accountingservice:6914926388fe`, `log:accountingservice:777c0dd6ebb5`, `log:accountingservice:7f002e6ec6b1`, `log:accountingservice:9a7a46c343db`, `log:accountingservice:9b571bf8f84c`, `log:accountingservice:b526f7e58c37`, `log:accountingservice:b6f2976d0cc7`, `log:accountingservice:b8c4b352bb62`, `log:accountingservice:d226aab7909f`, `log:accountingservice:d40fabb1daa8`, `log:accountingservice:ed7c55d1722e`, `log:accountingservice:f6d2a8fd7279`, `log:accountingservice:f70ba64be717`, `log:accountingservice:f904ab2a1231`, `log:adservice:15386f04ccf3`, `log:adservice:237bd2e48941`, `log:adservice:46aa7009ba09`, `log:adservice:5966dd28c645`, `log:adservice:6b83755ca1d0`, `log:adservice:eb13be1d2f61`, `log:adservice:ec57eec38dad`, `log:adservice:f7061b25a6f8`, `log:cartservice:9d2d534593fb`, `log:cartservice:aa11e5efcab9`, `log:cartservice:f3b5e31a4607`, `log:checkoutservice:00c505ab948d`, `log:checkoutservice:0275347e05a2`, `log:checkoutservice:033988248b04`, `log:checkoutservice:03d4d9803271`, `log:checkoutservice:03df4624025e`, `log:checkoutservice:047f41bbf6c2`, `log:checkoutservice:04f6d3111fab` (+860 more in the JSON).
- r0.2: inert 32: `log:frontendproxy:1982b925695b/absent`, `log:frontendproxy:d2080adea2c3/absent`, `log:kafka:1367c637eda2/absent`, `log:kafka:19ebc4c406cc/absent`, `log:kafka:1b6bb55dcf25/absent`, `log:kafka:1c75c94f4019/absent`, `log:kafka:209d095cee84/absent`, `log:kafka:23de8a6634a0/absent`, `log:kafka:2848bf7b5ce9/absent`, `log:kafka:2f43a13b18ce/absent`, `log:kafka:4af8ca5c0f4a/absent`, `log:kafka:51bdc291db56/absent`, `log:kafka:530e610ccce9/absent`, `log:kafka:5dc9c5402d61/absent`, `log:kafka:6f8bc6db7c40/absent`, `log:kafka:70cc1a05fda1/absent`, `log:kafka:7d4c1c1d3761/absent`, `log:kafka:84752691105b/absent`, `log:kafka:8ab6ffc7e081/absent`, `log:kafka:90a317961466/absent`, `log:kafka:b4f1a5dde2b9/absent`, `log:kafka:b8bad87e414f/absent`, `log:kafka:c18fc626cf23/absent`, `log:kafka:dd1c07008ef5/absent`, `log:kafka:dfe6bc88aede/absent`, `log:kafka:ed47e2a9155d/absent`, `log:kafka:efc900fc673f/absent`, `log:kafka:f2af4ad9f40a/absent`, `log:kafka:f8e6273cf6c7/absent`, `span:frontend:GET_//absent`, `span:frontend:render_route_(pages)_//absent`, `span:frontend:resolve_page_components/absent`; at grid edge 0: none; appear-only 899: `log:accountingservice:020200dc7516`, `log:accountingservice:0de465075c04`, `log:accountingservice:1beb330393a9`, `log:accountingservice:33a6342b9bdb`, `log:accountingservice:34d5bac2ad4c`, `log:accountingservice:396e4d6de49a`, `log:accountingservice:4effb619229a`, `log:accountingservice:4fafe2bb2232`, `log:accountingservice:6914926388fe`, `log:accountingservice:777c0dd6ebb5`, `log:accountingservice:7f002e6ec6b1`, `log:accountingservice:9a7a46c343db`, `log:accountingservice:9b571bf8f84c`, `log:accountingservice:b526f7e58c37`, `log:accountingservice:b6f2976d0cc7`, `log:accountingservice:b8c4b352bb62`, `log:accountingservice:d226aab7909f`, `log:accountingservice:d40fabb1daa8`, `log:accountingservice:ed7c55d1722e`, `log:accountingservice:f6d2a8fd7279`, `log:accountingservice:f70ba64be717`, `log:accountingservice:f904ab2a1231`, `log:adservice:15386f04ccf3`, `log:adservice:237bd2e48941`, `log:adservice:46aa7009ba09`, `log:adservice:5966dd28c645`, `log:adservice:6b83755ca1d0`, `log:adservice:eb13be1d2f61`, `log:adservice:ec57eec38dad`, `log:adservice:f7061b25a6f8`, `log:cartservice:9d2d534593fb`, `log:cartservice:aa11e5efcab9`, `log:cartservice:f3b5e31a4607`, `log:checkoutservice:00c505ab948d`, `log:checkoutservice:0275347e05a2`, `log:checkoutservice:033988248b04`, `log:checkoutservice:03d4d9803271`, `log:checkoutservice:03df4624025e`, `log:checkoutservice:047f41bbf6c2`, `log:checkoutservice:04f6d3111fab` (+859 more in the JSON).
- r0.05: inert 32: `log:frontendproxy:1982b925695b/absent`, `log:frontendproxy:d2080adea2c3/absent`, `log:kafka:1367c637eda2/absent`, `log:kafka:19ebc4c406cc/absent`, `log:kafka:1b6bb55dcf25/absent`, `log:kafka:1c75c94f4019/absent`, `log:kafka:209d095cee84/absent`, `log:kafka:23de8a6634a0/absent`, `log:kafka:2848bf7b5ce9/absent`, `log:kafka:2f43a13b18ce/absent`, `log:kafka:4af8ca5c0f4a/absent`, `log:kafka:51bdc291db56/absent`, `log:kafka:530e610ccce9/absent`, `log:kafka:5dc9c5402d61/absent`, `log:kafka:6f8bc6db7c40/absent`, `log:kafka:70cc1a05fda1/absent`, `log:kafka:7d4c1c1d3761/absent`, `log:kafka:84752691105b/absent`, `log:kafka:8ab6ffc7e081/absent`, `log:kafka:90a317961466/absent`, `log:kafka:b4f1a5dde2b9/absent`, `log:kafka:b8bad87e414f/absent`, `log:kafka:c18fc626cf23/absent`, `log:kafka:dd1c07008ef5/absent`, `log:kafka:dfe6bc88aede/absent`, `log:kafka:ed47e2a9155d/absent`, `log:kafka:efc900fc673f/absent`, `log:kafka:f2af4ad9f40a/absent`, `log:kafka:f8e6273cf6c7/absent`, `span:frontend:GET_//absent`, `span:frontend:render_route_(pages)_//absent`, `span:frontend:resolve_page_components/absent`; at grid edge 6: `metric:productcatalogservice:process.runtime.go.mem.heap_sys/median`, `metric:productcatalogservice:process.runtime.go.mem.heap_sys/run3`, `metric:productcatalogservice:process.runtime.go.mem.heap_sys/spike`, `span:frontend:GET/spike`, `span:frontendproxy:ingress/spike`, `span:frontendproxy:router_frontend_egress/spike`; appear-only 871: `log:accountingservice:020200dc7516`, `log:accountingservice:0de465075c04`, `log:accountingservice:1beb330393a9`, `log:accountingservice:33a6342b9bdb`, `log:accountingservice:34d5bac2ad4c`, `log:accountingservice:396e4d6de49a`, `log:accountingservice:4effb619229a`, `log:accountingservice:4fafe2bb2232`, `log:accountingservice:6914926388fe`, `log:accountingservice:777c0dd6ebb5`, `log:accountingservice:7f002e6ec6b1`, `log:accountingservice:9a7a46c343db`, `log:accountingservice:9b571bf8f84c`, `log:accountingservice:b526f7e58c37`, `log:accountingservice:b6f2976d0cc7`, `log:accountingservice:b8c4b352bb62`, `log:accountingservice:d226aab7909f`, `log:accountingservice:d40fabb1daa8`, `log:accountingservice:ed7c55d1722e`, `log:accountingservice:f6d2a8fd7279`, `log:accountingservice:f70ba64be717`, `log:accountingservice:f904ab2a1231`, `log:adservice:15386f04ccf3`, `log:adservice:237bd2e48941`, `log:adservice:46aa7009ba09`, `log:adservice:5966dd28c645`, `log:adservice:6b83755ca1d0`, `log:adservice:eb13be1d2f61`, `log:adservice:ec57eec38dad`, `log:adservice:f7061b25a6f8`, `log:cartservice:9d2d534593fb`, `log:cartservice:aa11e5efcab9`, `log:cartservice:f3b5e31a4607`, `log:checkoutservice:00c505ab948d`, `log:checkoutservice:033988248b04`, `log:checkoutservice:03d4d9803271`, `log:checkoutservice:03df4624025e`, `log:checkoutservice:04f6d3111fab`, `log:checkoutservice:0533d4fad6dc`, `log:checkoutservice:06fd3f03716d` (+831 more in the JSON).

**Not placeable at this quiet time** (L, M, S, T sensors with no calibrated rule), by family (with a dropped rule / inert / unarmed only), then those with a dropped rule:

- r10: 148 sensors (L 0/29/1, M 0/0/118); with a dropped rule: none
- r1: 147 sensors (L 0/29/0, M 0/0/118); with a dropped rule: none
- r0.2: 147 sensors (L 0/29/0, M 0/0/118); with a dropped rule: none
- r0.05: 149 sensors (L 0/29/0, M 0/0/120); with a dropped rule: none

- `appear` (V3_APPEAR_RULE): new streams in no-fault cells per service, summed over the held-out cells (they enter the honest counts): r10 none; r1 none; r0.2 none; r0.05 none.
- **floor arm (share 0.05)**: r10 1577/10/32/1436 rules, 238 placeable + 872 appear-only sensors; r1 1608/7/32/1462 rules, 238 placeable + 900 appear-only sensors; r0.2 1597/17/32/1461 rules, 238 placeable + 899 appear-only sensors; r0.05 1579/10/32/1439 rules, 239 placeable + 871 appear-only sensors.
- **sensitivity, <= 1 held-out alarm (K_GRID only, no range fallback)**: r10 1383/12/29/1631 rules, 173 placeable + 872 appear-only sensors; r1 1422/7/29/1651 rules, 175 placeable + 900 appear-only sensors; r0.2 1416/9/29/1653 rules, 174 placeable + 899 appear-only sensors; r0.05 1364/12/29/1655 rules, 167 placeable + 871 appear-only sensors.

## Honest false alarms (decisions 64, 67): nested leave-one-cell-out unions on the no-fault cells

Union of the sensors' rules, each held-out no-fault cell scored at the values re-selected without it (its leave-one-cell-out fit), restarted after each alarm: count (/h [exact 95 % bound]); per family also the sum of its calibrated rules' honest counts (the reviewer's tally). The honest per-sensor rate is the sensor's false-alarm cost for CELF (JSON calibration.*.sensors.*.honestPerHour). Campaign B's fresh check can certify at best 20.0/h (0 alarms in 0.15 h per rate).

| setting | rate | T (h) | E | L | M | S | T | all placeable L, M, S, T |
|---|---|---|---|---|---|---|---|---|
| primary | r10 | 1.050 | 2 (1.9/h [6.0], 1.050 of 1.05 h) · sum 2 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [2.9], 1.050 of 1.05 h) · sum 0 · no evidence: 0 rules, 137 sensors | 11 (10.5/h [17.3], 1.050 of 1.05 h) · sum 18 · no evidence: 27 rules, 9 sensors | — | 9 (8.6/h [15.0], 1.050 of 1.05 h) · sum 10 · no evidence: 0 rules, 0 sensors | 21 (20.0/h [28.8], 1.05 of 1.05 h) |
| primary | r1 | 1.050 | 2 (1.9/h [6.0], 1.050 of 1.05 h) · sum 2 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [2.9], 1.050 of 1.05 h) · sum 0 · no evidence: 0 rules, 133 sensors | 20 (19.0/h [27.7], 1.050 of 1.05 h) · sum 16 · no evidence: 27 rules, 9 sensors | — | 13 (12.4/h [19.7], 1.050 of 1.05 h) · sum 19 · no evidence: 0 rules, 0 sensors | 33 (31.4/h [42.0], 1.05 of 1.05 h) |
| primary | r0.2 | 1.050 | 1 (1.0/h [4.5], 1.050 of 1.05 h) · sum 1 · no evidence: 0 rules, 1 sensors | 2 (1.9/h [6.0], 1.050 of 1.05 h) · sum 2 · no evidence: 0 rules, 161 sensors | 28 (26.7/h [36.6], 1.050 of 1.05 h) · sum 43 · no evidence: 30 rules, 10 sensors | — | 8 (7.6/h [13.7], 1.050 of 1.05 h) · sum 10 · no evidence: 0 rules, 0 sensors | 40 (38.1/h [49.6], 1.05 of 1.05 h) |
| primary | r0.05 | 1.050 | 0 (0.0/h [2.9], 1.050 of 1.05 h) · sum 0 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [2.9], 1.050 of 1.05 h) · sum 0 · no evidence: 0 rules, 132 sensors | 21 (20.0/h [28.8], 1.050 of 1.05 h) · sum 22 · no evidence: 21 rules, 7 sensors | — | 5 (4.8/h [10.0], 1.050 of 1.05 h) · sum 8 · no evidence: 0 rules, 0 sensors | 26 (24.8/h [34.4], 1.05 of 1.05 h) |
| atMostOne | r10 | 1.050 | 4 (3.8/h [8.7], 1.050 of 1.05 h) · sum 4 · no evidence: 0 rules, 1 sensors | 5 (4.8/h [10.0], 1.050 of 1.05 h) · sum 5 · no evidence: 0 rules, 137 sensors | 13 (12.4/h [19.7], 1.050 of 1.05 h) · sum 34 · no evidence: 24 rules, 8 sensors | — | 22 (21.0/h [29.9], 1.050 of 1.05 h) · sum 21 · no evidence: 0 rules, 0 sensors | 41 (39.0/h [50.7], 1.05 of 1.05 h) |
| atMostOne | r1 | 1.050 | 2 (1.9/h [6.0], 1.050 of 1.05 h) · sum 2 · no evidence: 0 rules, 1 sensors | 5 (4.8/h [10.0], 1.050 of 1.05 h) · sum 5 · no evidence: 0 rules, 133 sensors | 24 (22.9/h [32.1], 1.050 of 1.05 h) · sum 24 · no evidence: 24 rules, 8 sensors | — | 35 (33.3/h [44.2], 1.050 of 1.05 h) · sum 35 · no evidence: 0 rules, 0 sensors | 77 (73.3/h [88.6], 1.05 of 1.05 h) |
| atMostOne | r0.2 | 1.050 | 3 (2.9/h [7.4], 1.050 of 1.05 h) · sum 3 · no evidence: 0 rules, 1 sensors | 5 (4.8/h [10.0], 1.050 of 1.05 h) · sum 5 · no evidence: 0 rules, 161 sensors | 40 (38.1/h [49.6], 1.050 of 1.05 h) · sum 74 · no evidence: 27 rules, 9 sensors | — | 33 (31.4/h [42.0], 1.050 of 1.05 h) · sum 33 · no evidence: 0 rules, 0 sensors | 80 (76.2/h [91.8], 1.05 of 1.05 h) |
| atMostOne | r0.05 | 1.050 | 3 (2.9/h [7.4], 1.050 of 1.05 h) · sum 3 · no evidence: 0 rules, 1 sensors | 5 (4.8/h [10.0], 1.050 of 1.05 h) · sum 5 · no evidence: 0 rules, 132 sensors | 24 (22.9/h [32.1], 1.050 of 1.05 h) · sum 43 · no evidence: 18 rules, 6 sensors | — | 23 (21.9/h [31.0], 1.050 of 1.05 h) · sum 26 · no evidence: 0 rules, 0 sensors | 52 (49.5/h [62.4], 1.05 of 1.05 h) |

P4-selected sets (the sensors P4 selected over its folds, or with one episode the candidates judged a win), honest nested union, primary:

- P4a frontend-pause-effect r0.05: `span:frontendproxy:router_frontend_egress` -> 1 (1.0/h [4.5], 1.05 of 1.05 h) · sum over the sensors 1
- P4a frontend-pause-effect r0.2: `span:frontendproxy:router_frontend_egress` -> 2 (1.9/h [6.0], 1.05 of 1.05 h) · sum over the sensors 2
- P4a frontend-pause-effect r1: `metric:productcatalogservice:rpc.server.duration~rate` -> 0 (0.0/h [2.9], 1.05 of 1.05 h) · sum over the sensors 0
- P4a frontend-pause-effect r10: `metric:frontendproxy:calls` -> 0 (0.0/h [2.9], 1.05 of 1.05 h) · sum over the sensors 0
- P4a productcatalog-cpu-throttle-effect r0.05: `log:frontendproxy:5eaff2aaa577` -> 0 (0.0/h [2.9], 1.05 of 1.05 h) · sum over the sensors 0
- P4a productcatalog-cpu-throttle-effect r0.2: `span:frontend:GET` -> 1 (1.0/h [4.5], 1.05 of 1.05 h) · sum over the sensors 1
- P4a productcatalog-cpu-throttle-effect r1: `log:frontendproxy:5eaff2aaa577`, `span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct` -> 5 (4.8/h [10.0], 1.05 of 1.05 h) · sum over the sensors 5
- P4a productcatalog-cpu-throttle-effect r10: `log:frontendproxy:5eaff2aaa577`, `span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct` -> 2 (1.9/h [6.0], 1.05 of 1.05 h) · sum over the sensors 2
- P4b frontend-pause-effect r0.05: `metric:frontend:duration~mean` -> 1 (1.0/h [4.5], 1.05 of 1.05 h) · sum over the sensors 1
- P4b frontend-pause-effect r1: `metric:frontend:calls` -> 0 (0.0/h [2.9], 1.05 of 1.05 h) · sum over the sensors 0
- P4b frontend-pause-effect r10: `metric:frontend:calls` -> 0 (0.0/h [2.9], 1.05 of 1.05 h) · sum over the sensors 0
- P4b productcatalog-cpu-throttle-effect r0.05: `metric:productcatalogservice:process.runtime.go.gc.pause_ns~mean`, `span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct` -> 1 (1.0/h [4.5], 1.05 of 1.05 h) · sum over the sensors 1
- P4b productcatalog-cpu-throttle-effect r10: `span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct` -> 1 (1.0/h [4.5], 1.05 of 1.05 h) · sum over the sensors 1

## v2.4 reference row: family operating point (decision 53, 15/h, from v2.4's own code)

K per family: E 16, L 2.5, M 20, S —, T 100, system —.

| class | family | r10 | r1 | r0.2 | r0.05 |
|---|---|---|---|---|---|
| frontend-pause | E | no | ok (K 16) | ok (K 16) | ok (K 16) |
| frontend-pause | L | ok (K 2.5) | ok (K 2.5) | ok (K 2.5) | ok (K 2.5) |
| frontend-pause | M | no | no | ok (K 20) | no |
| frontend-pause | S | n/c | n/c | n/c | n/c |
| frontend-pause | T | no | no | no | ok (K 100) |
| productcatalog-cpu-throttle | E | no | ok (K 16) | ok (K 16) | ok (K 16) |
| productcatalog-cpu-throttle | L | no | no | no | no |
| productcatalog-cpu-throttle | M | no | no | ok (K 20) | no |
| productcatalog-cpu-throttle | S | n/c | n/c | n/c | n/c |
| productcatalog-cpu-throttle | T | no | no | no | ok (K 100) |

## Predictions (primary: calibrated arm, floor primary)

- **P1** (frontend-pause; decision 54's interval, observed = first `failed` catch): 27/28; per rate r10 7/7, r1 6/7, r0.2 7/7, r0.05 7/7; not evaluable 0; holds by branch: timeout interval 27; verdict **fails**.
- **P2** r10 (failed before the first `failed` catch <= 153.00): 7/7, counts [151, 151, 151, 151, 151, 151, 151], verdict — (n < 4).
- **P2** r1 (failed before the first `failed` catch <= 18.00): 7/7, counts [16, 16, 7, 16, 16, 16, 16], verdict — (n < 4).
- **P2** r0.2 (failed before the first `failed` catch <= 6.00): 7/7, counts [4, 4, 4, 4, 4, 4, 4], verdict — (n < 4).
- **P2** r0.05 (failed before the first `failed` catch <= 3.75): 7/7, counts [1, 1, 1, 1, 1, 1, 1], verdict — (n < 4).
- **P3** frontend-pause: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P3** productcatalog-cpu-throttle: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P4** compares against the ledger E as the OR of its calibrated rules, its `failed` rule exempt from calibration (decisions 63, 70; V3_P4_LEDGER_READING = `calibrated-ledger`): a dropped ledger rule is listed below, not a reason for `—`. Two arms (decision 67): calibrated (primary) and optimistic bound (dropped rules armed at K = 100 / m = 5, beside, not evidence).
- Dropped ledger rules per rate (decision 70: listed; the ledger compares by its calibrated rules): r10 none; r1 none; r0.2 none; r0.05 none.
- **P4a** frontend-pause (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 0/7 (ledger missed, sensor caught: 0); r1 0/7 (ledger missed, sensor caught: 0); r0.2 0/7 (ledger missed, sensor caught: 0); r0.05 5/7 (ledger missed, sensor caught: 0); highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/7 (ledger missed, sensor caught: 0); r1 0/7 (ledger missed, sensor caught: 0); r0.2 0/7 (ledger missed, sensor caught: 0); r0.05 5/7 (ledger missed, sensor caught: 0); highest rate — at {10, 1, 0.2, 0.05}.
- **P4a** productcatalog-cpu-throttle (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 0/7 (ledger missed, sensor caught: 0); r1 0/7 (ledger missed, sensor caught: 0); r0.2 0/7 (ledger missed, sensor caught: 3); r0.05 0/7 (ledger missed, sensor caught: 0); highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/7 (ledger missed, sensor caught: 0); r1 0/7 (ledger missed, sensor caught: 0); r0.2 0/7 (ledger missed, sensor caught: 3); r0.05 0/7 (ledger missed, sensor caught: 1); highest rate — at {10, 1, 0.2, 0.05}.
- **P4b** frontend-pause (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 0/7 (ledger missed, sensor caught: 0); r1 0/7 (ledger missed, sensor caught: 0); r0.2 0/7 (ledger missed, sensor caught: 0); r0.05 0/7 (ledger missed, sensor caught: 0); highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/7 (ledger missed, sensor caught: 0); r1 0/7 (ledger missed, sensor caught: 0); r0.2 0/7 (ledger missed, sensor caught: 0); r0.05 2/7 (ledger missed, sensor caught: 0); highest rate — at {10, 1, 0.2, 0.05}.
- **P4b** productcatalog-cpu-throttle (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 0/7 (ledger missed, sensor caught: 0); r1 0/7 (ledger missed, sensor caught: 0); r0.2 0/7 (ledger missed, sensor caught: 0); r0.05 0/7 (ledger missed, sensor caught: 0); highest rate **— at {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/7 (ledger missed, sensor caught: 6); r1 0/7 (ledger missed, sensor caught: 0); r0.2 0/7 (ledger missed, sensor caught: 0); r0.05 0/7 (ledger missed, sensor caught: 0); highest rate — at {10, 1, 0.2, 0.05}.

### P4 per class and rate: placeable sensors, dropped rules and non-placeable sensors on the affected path

- frontend-pause r10: placeable sensors 1110 (candidates with a catch: 14); dropped on the path: `metric:productcatalogservice:process.runtime.go.gc.count/spike`, `metric:productcatalogservice:process.runtime.go.gc.pause_ns~rate/spike`; not placeable on the path: `log:frontendproxy:1982b925695b`, `log:frontendproxy:a933fde0fa35`, `log:frontendproxy:d2080adea2c3`, `metric:frontend:http.client.duration~rate`, `metric:productcatalogservice:process.runtime.go.cgo.calls`, `metric:productcatalogservice:process.runtime.go.mem.lookups`, `metric:productcatalogservice:rpc.server.request.size~mean`, `metric:productcatalogservice:rpc.server.requests_per_rpc~mean`, `metric:productcatalogservice:rpc.server.response.size~mean`, `metric:productcatalogservice:rpc.server.responses_per_rpc~mean`; dropped ledger rules (listed, decision 70): none
- frontend-pause r1: placeable sensors 1138 (candidates with a catch: 14); dropped on the path: `span:frontend:GET/spike`; not placeable on the path: `log:frontendproxy:1982b925695b`, `log:frontendproxy:d2080adea2c3`, `metric:frontend:http.client.duration~rate`, `metric:productcatalogservice:process.runtime.go.cgo.calls`, `metric:productcatalogservice:process.runtime.go.mem.lookups`, `metric:productcatalogservice:rpc.server.request.size~mean`, `metric:productcatalogservice:rpc.server.requests_per_rpc~mean`, `metric:productcatalogservice:rpc.server.response.size~mean`, `metric:productcatalogservice:rpc.server.responses_per_rpc~mean`; dropped ledger rules (listed, decision 70): none
- frontend-pause r0.2: placeable sensors 1137 (candidates with a catch: 6); dropped on the path: none; not placeable on the path: `log:frontendproxy:1982b925695b`, `log:frontendproxy:d2080adea2c3`, `metric:frontend:http.client.duration~rate`, `metric:productcatalogservice:process.runtime.go.cgo.calls`, `metric:productcatalogservice:process.runtime.go.mem.lookups`, `metric:productcatalogservice:rpc.server.request.size~mean`, `metric:productcatalogservice:rpc.server.requests_per_rpc~mean`, `metric:productcatalogservice:rpc.server.response.size~mean`, `metric:productcatalogservice:rpc.server.responses_per_rpc~mean`; dropped ledger rules (listed, decision 70): none
- frontend-pause r0.05: placeable sensors 1110 (candidates with a catch: 15); dropped on the path: `metric:frontend:app.frontend.requests/spike`, `metric:frontend:calls/spike`, `metric:frontend:duration~rate/spike`, `metric:frontend:http.server.duration~rate/spike`, `metric:productcatalogservice:process.runtime.go.gc.pause_total_ns/spike`; not placeable on the path: `log:frontendproxy:1982b925695b`, `log:frontendproxy:d2080adea2c3`, `metric:frontend:http.client.duration~rate`, `metric:productcatalogservice:process.runtime.go.cgo.calls`, `metric:productcatalogservice:process.runtime.go.mem.lookups`, `metric:productcatalogservice:rpc.server.request.size~mean`, `metric:productcatalogservice:rpc.server.requests_per_rpc~mean`, `metric:productcatalogservice:rpc.server.response.size~mean`, `metric:productcatalogservice:rpc.server.responses_per_rpc~mean`; dropped ledger rules (listed, decision 70): none
- productcatalog-cpu-throttle r10: placeable sensors 1110 (candidates with a catch: 2); dropped on the path: `metric:productcatalogservice:process.runtime.go.gc.count/spike`, `metric:productcatalogservice:process.runtime.go.gc.pause_ns~rate/spike`; not placeable on the path: `log:frontendproxy:1982b925695b`, `log:frontendproxy:a933fde0fa35`, `log:frontendproxy:d2080adea2c3`, `metric:frontend:http.client.duration~rate`, `metric:productcatalogservice:process.runtime.go.cgo.calls`, `metric:productcatalogservice:process.runtime.go.mem.lookups`, `metric:productcatalogservice:rpc.server.request.size~mean`, `metric:productcatalogservice:rpc.server.requests_per_rpc~mean`, `metric:productcatalogservice:rpc.server.response.size~mean`, `metric:productcatalogservice:rpc.server.responses_per_rpc~mean`; dropped ledger rules (listed, decision 70): none
- productcatalog-cpu-throttle r1: placeable sensors 1138 (candidates with a catch: 4); dropped on the path: `span:frontend:GET/spike`; not placeable on the path: `log:frontendproxy:1982b925695b`, `log:frontendproxy:d2080adea2c3`, `metric:frontend:http.client.duration~rate`, `metric:productcatalogservice:process.runtime.go.cgo.calls`, `metric:productcatalogservice:process.runtime.go.mem.lookups`, `metric:productcatalogservice:rpc.server.request.size~mean`, `metric:productcatalogservice:rpc.server.requests_per_rpc~mean`, `metric:productcatalogservice:rpc.server.response.size~mean`, `metric:productcatalogservice:rpc.server.responses_per_rpc~mean`; dropped ledger rules (listed, decision 70): none
- productcatalog-cpu-throttle r0.2: placeable sensors 1137 (candidates with a catch: 3); dropped on the path: none; not placeable on the path: `log:frontendproxy:1982b925695b`, `log:frontendproxy:d2080adea2c3`, `metric:frontend:http.client.duration~rate`, `metric:productcatalogservice:process.runtime.go.cgo.calls`, `metric:productcatalogservice:process.runtime.go.mem.lookups`, `metric:productcatalogservice:rpc.server.request.size~mean`, `metric:productcatalogservice:rpc.server.requests_per_rpc~mean`, `metric:productcatalogservice:rpc.server.response.size~mean`, `metric:productcatalogservice:rpc.server.responses_per_rpc~mean`; dropped ledger rules (listed, decision 70): none
- productcatalog-cpu-throttle r0.05: placeable sensors 1110 (candidates with a catch: 3); dropped on the path: `metric:frontend:app.frontend.requests/spike`, `metric:frontend:calls/spike`, `metric:frontend:duration~rate/spike`, `metric:frontend:http.server.duration~rate/spike`, `metric:productcatalogservice:process.runtime.go.gc.pause_total_ns/spike`; not placeable on the path: `log:frontendproxy:1982b925695b`, `log:frontendproxy:d2080adea2c3`, `metric:frontend:http.client.duration~rate`, `metric:productcatalogservice:process.runtime.go.cgo.calls`, `metric:productcatalogservice:process.runtime.go.mem.lookups`, `metric:productcatalogservice:rpc.server.request.size~mean`, `metric:productcatalogservice:rpc.server.requests_per_rpc~mean`, `metric:productcatalogservice:rpc.server.response.size~mean`, `metric:productcatalogservice:rpc.server.responses_per_rpc~mean`; dropped ledger rules (listed, decision 70): none

### P4 folds (sensor rule vs ledger rule; lead, margin; category)

**Calibrated arm**

- P4a frontend-pause r10 (candidates 14; paired differences ledger - sensor: mean -8.889 [-9.209, -8.643] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:frontendproxy:calls `spike` 9.120 vs E `absent` 0.477; lead -8.643, margin 2e-05; tied 2 (win share 0/2); **not faster**
  - ep2 b1: metric:frontendproxy:calls `spike` 9.083 vs E `absent` 0.418; lead -8.666, margin 2e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b2: metric:frontendproxy:calls `spike` 9.344 vs E `absent` 0.471; lead -8.873, margin 2.5e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b3: metric:frontendproxy:calls `spike` 9.693 vs E `absent` 0.484; lead -9.209, margin 1.8e-05; tied 2 (win share 0/2); **not faster**
  - ep5 b1: metric:frontendproxy:calls `spike` 9.124 vs E `absent` 0.463; lead -8.661, margin 1e-05; tied 2 (win share 0/2); **not faster**
  - ep6 b2: metric:frontendproxy:calls `spike` 9.443 vs E `absent` 0.439; lead -9.004, margin 1.9e-05; tied 2 (win share 0/2); **not faster**
  - ep7 b3: metric:frontendproxy:calls `spike` 9.647 vs E `absent` 0.477; lead -9.170, margin 1.1e-05; tied 2 (win share 0/2); **not faster**
- P4a frontend-pause r1 (candidates 14; paired differences ledger - sensor: mean -8.471 [-9.161, -7.506] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:productcatalogservice:rpc.server.duration~rate `spike` 9.509 vs E `absent` 0.623; lead -8.885, margin 3.4e-06; tied 1 (win share 0/1); **not faster**
  - ep2 b1: metric:productcatalogservice:rpc.server.duration~rate `spike` 9.538 vs E `absent` 1.044; lead -8.494, margin 6.1e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:productcatalogservice:rpc.server.duration~rate `spike` 9.689 vs E `absent` 0.527; lead -9.161, margin 2.4e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:productcatalogservice:rpc.server.duration~rate `spike` 8.763 vs E `absent` 1.257; lead -7.506, margin 5.3e-06; tied 1 (win share 0/1); **not faster**
  - ep5 b1: metric:productcatalogservice:rpc.server.duration~rate `spike` 9.258 vs E `absent` 1.286; lead -7.972, margin 5.3e-06; tied 1 (win share 0/1); **not faster**
  - ep6 b2: metric:productcatalogservice:rpc.server.duration~rate `spike` 9.610 vs E `absent` 1.081; lead -8.529, margin 1.7e-05; tied 1 (win share 0/1); **not faster**
  - ep7 b3: metric:productcatalogservice:rpc.server.duration~rate `spike` 9.357 vs E `absent` 0.608; lead -8.749, margin 5.3e-06; tied 1 (win share 0/1); **not faster**
- P4a frontend-pause r0.2 (candidates 6; paired differences ledger - sensor: mean -12.332 [-12.382, -12.282] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontendproxy:router_frontend_egress `spike` 15.223 vs E `absent` 2.841; lead -12.382, margin 1.9e-06; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:frontendproxy:router_frontend_egress `spike` 16.376 vs E `absent` 4.032; lead -12.344, margin 7.9e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:frontendproxy:router_frontend_egress `spike` 17.334 vs E `absent` 4.985; lead -12.349, margin 5.7e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:frontendproxy:router_frontend_egress `spike` 19.707 vs E `absent` 7.381; lead -12.326, margin 5.7e-06; tied 1 (win share 0/1); **not faster**
  - ep5 b1: span:frontendproxy:router_frontend_egress `spike` 18.393 vs E `absent` 6.072; lead -12.321, margin 5e-06; tied 1 (win share 0/1); **not faster**
  - ep6 b2: span:frontendproxy:router_frontend_egress `spike` 17.512 vs E `absent` 5.231; lead -12.282, margin 4.8e-06; tied 1 (win share 0/1); **not faster**
  - ep7 b3: span:frontendproxy:router_frontend_egress `spike` 16.448 vs E `absent` 4.126; lead -12.323, margin 3.6e-06; tied 1 (win share 0/1); **not faster**
- P4a frontend-pause r0.05 (candidates 15; paired differences ledger - sensor: mean 2.106 [-4.880, 5.228] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontendproxy:router_frontend_egress `spike` 22.954 vs E `absent` 27.975; lead 5.021, margin 3.3e-06; tied 1 (win share 1/1); **win**
  - ep2 b1: span:frontendproxy:router_frontend_egress `spike` 20.707 vs E `absent` 25.935; lead 5.228, margin 6.2e-06; tied 1 (win share 1/1); **win**
  - ep3 b2: span:frontendproxy:router_frontend_egress `spike` 21.622 vs E `absent` 16.761; lead -4.861, margin 5.5e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:frontendproxy:router_frontend_egress `spike` 15.430 vs E `absent` 20.097; lead 4.668, margin 5.1e-05; tied 1 (win share 1/1); **win**
  - ep5 b1: span:frontendproxy:router_frontend_egress `spike` 19.504 vs E `absent` 24.176; lead 4.672, margin 3.6e-06; tied 1 (win share 1/1); **win**
  - ep6 b2: span:frontendproxy:router_frontend_egress `spike` 20.583 vs E `absent` 15.703; lead -4.880, margin 4.3e-06; tied 1 (win share 0/1); **not faster**
  - ep7 b3: span:frontendproxy:router_frontend_egress `spike` 16.232 vs E `absent` 21.123; lead 4.891, margin 3.6e-06; tied 1 (win share 1/1); **win**
- P4a productcatalog-cpu-throttle r10 (candidates 2; paired differences ledger - sensor: mean 0.000 [0.000, 0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b1: span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b2: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b3: span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep5 b1: span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep6 b2: span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep7 b3: span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4a productcatalog-cpu-throttle r1 (candidates 4; paired differences ledger - sensor: mean -0.154 [-1.079, 0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b1: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b2: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b3: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep5 b1: log:frontendproxy:5eaff2aaa577 `—` — vs E `spike` 58.979; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep6 b2: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep7 b3: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4a productcatalog-cpu-throttle r0.2 (candidates 3; paired differences ledger - sensor: mean 22.201 [0.000, 54.238] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:GET `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b1: span:frontend:GET `median` 5.822 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b2: span:frontend:GET `median` 10.242 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep4 b3: span:frontend:GET `median` 8.681 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep5 b1: span:frontend:GET `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep6 b2: span:frontend:GET `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep7 b3: span:frontend:GET `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4a productcatalog-cpu-throttle r0.05 (candidates 3; paired differences ledger - sensor: mean 0.000 [0.000, 0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b1: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b2: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b3: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep5 b1: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep6 b2: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep7 b3: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4b frontend-pause r10 (candidates 2; paired differences ledger - sensor: mean -8.889 [-9.209, -8.643] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:frontend:calls `spike` 9.120 vs E `absent` 0.477; lead -8.643, margin 2e-05; tied 2 (win share 0/2); **not faster**
  - ep2 b1: metric:frontend:calls `spike` 9.083 vs E `absent` 0.418; lead -8.666, margin 2e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b2: metric:frontend:calls `spike` 9.344 vs E `absent` 0.471; lead -8.873, margin 2.5e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b3: metric:frontend:calls `spike` 9.693 vs E `absent` 0.484; lead -9.209, margin 1.8e-05; tied 2 (win share 0/2); **not faster**
  - ep5 b1: metric:frontend:calls `spike` 9.124 vs E `absent` 0.463; lead -8.661, margin 1e-05; tied 2 (win share 0/2); **not faster**
  - ep6 b2: metric:frontend:calls `spike` 9.443 vs E `absent` 0.439; lead -9.004, margin 1.9e-05; tied 2 (win share 0/2); **not faster**
  - ep7 b3: metric:frontend:calls `spike` 9.647 vs E `absent` 0.477; lead -9.170, margin 1.1e-05; tied 2 (win share 0/2); **not faster**
- P4b frontend-pause r1 (candidates 2; paired differences ledger - sensor: mean -22.542 [-59.431, -7.186] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:frontend:calls `—` — vs E `absent` 0.623; lead —, margin —; tied 2 (win share 0/2); **sensor missed**
  - ep2 b1: metric:frontend:calls `spike` 8.987 vs E `absent` 1.044; lead -7.943, margin 6.1e-06; tied 2 (win share 0/2); **not faster**
  - ep3 b2: metric:frontend:calls `spike` 8.875 vs E `absent` 0.527; lead -8.347, margin 2.4e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b3: metric:frontend:calls `—` — vs E `absent` 1.257; lead —, margin —; tied 2 (win share 0/2); **sensor missed**
  - ep5 b1: metric:frontend:calls `spike` 8.472 vs E `absent` 1.286; lead -7.186, margin 5.3e-06; tied 2 (win share 0/2); **not faster**
  - ep6 b2: metric:frontend:calls `spike` 9.001 vs E `absent` 1.081; lead -7.920, margin 1.7e-05; tied 2 (win share 0/2); **not faster**
  - ep7 b3: metric:frontend:calls `spike` 8.822 vs E `absent` 0.608; lead -8.214, margin 5.3e-06; tied 2 (win share 0/2); **not faster**
- P4b frontend-pause r0.2 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `absent` 2.841; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b1: — `—` — vs E `absent` 4.032; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b2: — `—` — vs E `absent` 4.985; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b3: — `—` — vs E `absent` 7.381; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep5 b1: — `—` — vs E `absent` 6.072; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep6 b2: — `—` — vs E `absent` 5.231; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep7 b3: — `—` — vs E `absent` 4.126; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b frontend-pause r0.05 (candidates 1; paired differences ledger - sensor: mean -39.072 [-44.313, -32.043] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:frontend:duration~mean `—` — vs E `absent` 27.975; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b1: — `—` — vs E `absent` 25.935; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b2: metric:frontend:duration~mean `—` — vs E `absent` 16.761; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b3: metric:frontend:duration~mean `—` — vs E `absent` 20.097; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep5 b1: metric:frontend:duration~mean `—` — vs E `absent` 24.176; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep6 b2: metric:frontend:duration~mean `—` — vs E `absent` 15.703; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep7 b3: metric:frontend:duration~mean `—` — vs E `absent` 21.123; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4b productcatalog-cpu-throttle r10 (candidates 1; paired differences ledger - sensor: mean 0.000 [0.000, 0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b2: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b3: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep5 b1: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep6 b2: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep7 b3: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4b productcatalog-cpu-throttle r1 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b2: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b3: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep5 b1: — `—` — vs E `spike` 58.979; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep6 b2: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep7 b3: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b productcatalog-cpu-throttle r0.2 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b2: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b3: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep5 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep6 b2: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep7 b3: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b productcatalog-cpu-throttle r0.05 (candidates 9; paired differences ledger - sensor: mean 0.000 [0.000, 0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:productcatalogservice:process.runtime.go.gc.pause_ns~mean `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b1: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b2: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b3: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep5 b1: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep6 b2: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep7 b3: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**

**Optimistic bound (not evidence)**

- P4a frontend-pause r10 (candidates 16; paired differences ledger - sensor: mean -8.889 [-9.209, -8.643] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:frontendproxy:calls `spike` 9.120 vs E `absent` 0.477; lead -8.643, margin 2e-05; tied 2 (win share 0/2); **not faster**
  - ep2 b1: metric:frontendproxy:calls `spike` 9.083 vs E `absent` 0.418; lead -8.666, margin 2e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b2: metric:frontendproxy:calls `spike` 9.344 vs E `absent` 0.471; lead -8.873, margin 2.5e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b3: metric:frontendproxy:calls `spike` 9.693 vs E `absent` 0.484; lead -9.209, margin 1.8e-05; tied 2 (win share 0/2); **not faster**
  - ep5 b1: metric:frontendproxy:calls `spike` 9.124 vs E `absent` 0.463; lead -8.661, margin 1e-05; tied 2 (win share 0/2); **not faster**
  - ep6 b2: metric:frontendproxy:calls `spike` 9.443 vs E `absent` 0.439; lead -9.004, margin 1.9e-05; tied 2 (win share 0/2); **not faster**
  - ep7 b3: metric:frontendproxy:calls `spike` 9.647 vs E `absent` 0.477; lead -9.170, margin 1.1e-05; tied 2 (win share 0/2); **not faster**
- P4a frontend-pause r1 (candidates 14; paired differences ledger - sensor: mean -8.471 [-9.161, -7.506] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:productcatalogservice:rpc.server.duration~rate `spike` 9.509 vs E `absent` 0.623; lead -8.885, margin 3.4e-06; tied 1 (win share 0/1); **not faster**
  - ep2 b1: metric:productcatalogservice:rpc.server.duration~rate `spike` 9.538 vs E `absent` 1.044; lead -8.494, margin 6.1e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: metric:productcatalogservice:rpc.server.duration~rate `spike` 9.689 vs E `absent` 0.527; lead -9.161, margin 2.4e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b3: metric:productcatalogservice:rpc.server.duration~rate `spike` 8.763 vs E `absent` 1.257; lead -7.506, margin 5.3e-06; tied 1 (win share 0/1); **not faster**
  - ep5 b1: metric:productcatalogservice:rpc.server.duration~rate `spike` 9.258 vs E `absent` 1.286; lead -7.972, margin 5.3e-06; tied 1 (win share 0/1); **not faster**
  - ep6 b2: metric:productcatalogservice:rpc.server.duration~rate `spike` 9.610 vs E `absent` 1.081; lead -8.529, margin 1.7e-05; tied 1 (win share 0/1); **not faster**
  - ep7 b3: metric:productcatalogservice:rpc.server.duration~rate `spike` 9.357 vs E `absent` 0.608; lead -8.749, margin 5.3e-06; tied 1 (win share 0/1); **not faster**
- P4a frontend-pause r0.2 (candidates 6; paired differences ledger - sensor: mean -12.332 [-12.382, -12.282] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontendproxy:router_frontend_egress `spike` 15.223 vs E `absent` 2.841; lead -12.382, margin 1.9e-06; tied 1 (win share 0/1); **not faster**
  - ep2 b1: span:frontendproxy:router_frontend_egress `spike` 16.376 vs E `absent` 4.032; lead -12.344, margin 7.9e-06; tied 1 (win share 0/1); **not faster**
  - ep3 b2: span:frontendproxy:router_frontend_egress `spike` 17.334 vs E `absent` 4.985; lead -12.349, margin 5.7e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:frontendproxy:router_frontend_egress `spike` 19.707 vs E `absent` 7.381; lead -12.326, margin 5.7e-06; tied 1 (win share 0/1); **not faster**
  - ep5 b1: span:frontendproxy:router_frontend_egress `spike` 18.393 vs E `absent` 6.072; lead -12.321, margin 5e-06; tied 1 (win share 0/1); **not faster**
  - ep6 b2: span:frontendproxy:router_frontend_egress `spike` 17.512 vs E `absent` 5.231; lead -12.282, margin 4.8e-06; tied 1 (win share 0/1); **not faster**
  - ep7 b3: span:frontendproxy:router_frontend_egress `spike` 16.448 vs E `absent` 4.126; lead -12.323, margin 3.6e-06; tied 1 (win share 0/1); **not faster**
- P4a frontend-pause r0.05 (candidates 15; paired differences ledger - sensor: mean 2.106 [-4.880, 5.228] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontendproxy:router_frontend_egress `spike` 22.954 vs E `absent` 27.975; lead 5.021, margin 3.3e-06; tied 1 (win share 1/1); **win**
  - ep2 b1: span:frontendproxy:router_frontend_egress `spike` 20.707 vs E `absent` 25.935; lead 5.228, margin 6.2e-06; tied 1 (win share 1/1); **win**
  - ep3 b2: span:frontendproxy:router_frontend_egress `spike` 21.622 vs E `absent` 16.761; lead -4.861, margin 5.5e-06; tied 1 (win share 0/1); **not faster**
  - ep4 b3: span:frontendproxy:router_frontend_egress `spike` 15.430 vs E `absent` 20.097; lead 4.668, margin 5.1e-05; tied 1 (win share 1/1); **win**
  - ep5 b1: span:frontendproxy:router_frontend_egress `spike` 19.504 vs E `absent` 24.176; lead 4.672, margin 3.6e-06; tied 1 (win share 1/1); **win**
  - ep6 b2: span:frontendproxy:router_frontend_egress `spike` 20.583 vs E `absent` 15.703; lead -4.880, margin 4.3e-06; tied 1 (win share 0/1); **not faster**
  - ep7 b3: span:frontendproxy:router_frontend_egress `spike` 16.232 vs E `absent` 21.123; lead 4.891, margin 3.6e-06; tied 1 (win share 1/1); **win**
- P4a productcatalog-cpu-throttle r10 (candidates 2; paired differences ledger - sensor: mean 0.000 [0.000, 0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b1: span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b2: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b3: span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep5 b1: span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep6 b2: span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep7 b3: span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4a productcatalog-cpu-throttle r1 (candidates 5; paired differences ledger - sensor: mean -0.154 [-1.079, 0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:GET `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b1: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b2: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b3: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep5 b1: log:frontendproxy:5eaff2aaa577 `—` — vs E `spike` 58.979; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep6 b2: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep7 b3: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4a productcatalog-cpu-throttle r0.2 (candidates 3; paired differences ledger - sensor: mean 22.201 [0.000, 54.238] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:GET `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b1: span:frontend:GET `median` 5.822 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b2: span:frontend:GET `median` 10.242 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep4 b3: span:frontend:GET `median` 8.681 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep5 b1: span:frontend:GET `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep6 b2: span:frontend:GET `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep7 b3: span:frontend:GET `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4a productcatalog-cpu-throttle r0.05 (candidates 7; paired differences ledger - sensor: mean 0.792 [0.000, 5.543] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:frontend:calls `spike` 54.515 vs E `—` —; lead —, margin —; tied 2 (win share 0/2); **ledger missed (counted apart)**
  - ep2 b1: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b2: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b3: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep5 b1: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep6 b2: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep7 b3: log:frontendproxy:5eaff2aaa577 `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4b frontend-pause r10 (candidates 2; paired differences ledger - sensor: mean -8.889 [-9.209, -8.643] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:frontend:calls `spike` 9.120 vs E `absent` 0.477; lead -8.643, margin 2e-05; tied 2 (win share 0/2); **not faster**
  - ep2 b1: metric:frontend:calls `spike` 9.083 vs E `absent` 0.418; lead -8.666, margin 2e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b2: metric:frontend:calls `spike` 9.344 vs E `absent` 0.471; lead -8.873, margin 2.5e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b3: metric:frontend:calls `spike` 9.693 vs E `absent` 0.484; lead -9.209, margin 1.8e-05; tied 2 (win share 0/2); **not faster**
  - ep5 b1: metric:frontend:calls `spike` 9.124 vs E `absent` 0.463; lead -8.661, margin 1e-05; tied 2 (win share 0/2); **not faster**
  - ep6 b2: metric:frontend:calls `spike` 9.443 vs E `absent` 0.439; lead -9.004, margin 1.9e-05; tied 2 (win share 0/2); **not faster**
  - ep7 b3: metric:frontend:calls `spike` 9.647 vs E `absent` 0.477; lead -9.170, margin 1.1e-05; tied 2 (win share 0/2); **not faster**
- P4b frontend-pause r1 (candidates 2; paired differences ledger - sensor: mean -22.542 [-59.431, -7.186] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:frontend:calls `—` — vs E `absent` 0.623; lead —, margin —; tied 2 (win share 0/2); **sensor missed**
  - ep2 b1: metric:frontend:calls `spike` 8.987 vs E `absent` 1.044; lead -7.943, margin 6.1e-06; tied 2 (win share 0/2); **not faster**
  - ep3 b2: metric:frontend:calls `spike` 8.875 vs E `absent` 0.527; lead -8.347, margin 2.4e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b3: metric:frontend:calls `—` — vs E `absent` 1.257; lead —, margin —; tied 2 (win share 0/2); **sensor missed**
  - ep5 b1: metric:frontend:calls `spike` 8.472 vs E `absent` 1.286; lead -7.186, margin 5.3e-06; tied 2 (win share 0/2); **not faster**
  - ep6 b2: metric:frontend:calls `spike` 9.001 vs E `absent` 1.081; lead -7.920, margin 1.7e-05; tied 2 (win share 0/2); **not faster**
  - ep7 b3: metric:frontend:calls `spike` 8.822 vs E `absent` 0.608; lead -8.214, margin 5.3e-06; tied 2 (win share 0/2); **not faster**
- P4b frontend-pause r0.2 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `absent` 2.841; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b1: — `—` — vs E `absent` 4.032; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b2: — `—` — vs E `absent` 4.985; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b3: — `—` — vs E `absent` 7.381; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep5 b1: — `—` — vs E `absent` 6.072; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep6 b2: — `—` — vs E `absent` 5.231; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep7 b3: — `—` — vs E `absent` 4.126; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b frontend-pause r0.05 (candidates 3; paired differences ledger - sensor: mean -21.530 [-39.688, 21.259] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:frontend:calls `spike` 6.951 vs E `absent` 27.975; lead 21.024, margin 3.4e-06; tied 2 (win share 2/2); **win**
  - ep2 b1: metric:frontend:calls `spike` 4.676 vs E `absent` 25.935; lead 21.259, margin 6.3e-06; tied 2 (win share 2/2); **win**
  - ep3 b2: metric:frontend:calls `spike` 55.950 vs E `absent` 16.761; lead -39.189, margin 5.6e-06; tied 2 (win share 0/2); **not faster**
  - ep4 b3: metric:frontend:calls `spike` 59.402 vs E `absent` 20.097; lead -39.305, margin 5.1e-05; tied 2 (win share 0/2); **not faster**
  - ep5 b1: metric:frontend:calls `—` — vs E `absent` 24.176; lead —, margin —; tied 2 (win share 0/2); **sensor missed**
  - ep6 b2: metric:frontend:calls `spike` 55.392 vs E `absent` 15.703; lead -39.688, margin 4.4e-06; tied 2 (win share 0/2); **not faster**
  - ep7 b3: metric:frontend:calls `—` — vs E `absent` 21.123; lead —, margin —; tied 2 (win share 0/2); **sensor missed**
- P4b productcatalog-cpu-throttle r10 (candidates 3; paired differences ledger - sensor: mean 43.139 [0.000, 50.660] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:productcatalogservice:process.runtime.go.gc.count `spike` 9.986 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep2 b1: metric:productcatalogservice:process.runtime.go.gc.count `spike` 9.996 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b2: metric:productcatalogservice:process.runtime.go.gc.count `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b3: metric:productcatalogservice:process.runtime.go.gc.count `spike` 9.517 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep5 b1: metric:productcatalogservice:process.runtime.go.gc.count `spike` 9.614 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep6 b2: metric:productcatalogservice:process.runtime.go.gc.count `spike` 9.779 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep7 b3: metric:productcatalogservice:process.runtime.go.gc.count `spike` 9.400 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
- P4b productcatalog-cpu-throttle r1 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b2: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b3: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep5 b1: — `—` — vs E `spike` 58.979; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep6 b2: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep7 b3: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b productcatalog-cpu-throttle r0.2 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b2: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b3: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep5 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep6 b2: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep7 b3: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b productcatalog-cpu-throttle r0.05 (candidates 10; paired differences ledger - sensor: mean 0.000 [0.000, 0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:productcatalogservice:process.runtime.go.gc.pause_total_ns `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b1: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b2: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b3: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep5 b1: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep6 b2: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep7 b3: span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**

**Per harness** (decision 49 pools the sweep's episode with campaign B's three; V3_HARNESS_TAG_RULE; tags B, sweep). Episodes per class and rate: frontend-pause r0.05 B 6, sweep 1; frontend-pause r0.2 B 6, sweep 1; frontend-pause r1 B 6, sweep 1; frontend-pause r10 B 6, sweep 1; productcatalog-cpu-throttle r0.05 B 6, sweep 1; productcatalog-cpu-throttle r0.2 B 6, sweep 1; productcatalog-cpu-throttle r1 B 6, sweep 1; productcatalog-cpu-throttle r10 B 6, sweep 1.

- P1 holds per harness: B 23/24, sweep 4/4; P2 within the bound per harness: r10 B 6/6, sweep 1/1; r1 B 6/6, sweep 1/1; r0.2 B 6/6, sweep 1/1; r0.05 B 6/6, sweep 1/1.
- P4 optimistic P4a frontend-pause r0.05: wins / folds by the held-out episode's harness: B 4/6, sweep 1/1
- P4 optimistic P4a frontend-pause r0.2: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4a frontend-pause r1: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4a frontend-pause r10: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4a productcatalog-cpu-throttle r0.05: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4a productcatalog-cpu-throttle r0.2: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4a productcatalog-cpu-throttle r1: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4a productcatalog-cpu-throttle r10: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4b frontend-pause r0.05: wins / folds by the held-out episode's harness: B 1/6, sweep 1/1
- P4 optimistic P4b frontend-pause r0.2: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4b frontend-pause r1: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4b frontend-pause r10: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4b productcatalog-cpu-throttle r0.05: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4b productcatalog-cpu-throttle r0.2: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4b productcatalog-cpu-throttle r1: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 optimistic P4b productcatalog-cpu-throttle r10: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4a frontend-pause r0.05: wins / folds by the held-out episode's harness: B 4/6, sweep 1/1
- P4 primary P4a frontend-pause r0.2: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4a frontend-pause r1: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4a frontend-pause r10: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4a productcatalog-cpu-throttle r0.05: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4a productcatalog-cpu-throttle r0.2: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4a productcatalog-cpu-throttle r1: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4a productcatalog-cpu-throttle r10: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4b frontend-pause r0.05: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4b frontend-pause r0.2: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4b frontend-pause r1: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4b frontend-pause r10: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4b productcatalog-cpu-throttle r0.05: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4b productcatalog-cpu-throttle r0.2: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4b productcatalog-cpu-throttle r1: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1
- P4 primary P4b productcatalog-cpu-throttle r10: wins / folds by the held-out episode's harness: B 0/6, sweep 0/1

**Beside the primary** (highest rate where P4 holds):

| verdict | calibrated (primary) | floor arm | <= 1 held-out alarm | optimistic bound (not evidence) |
|---|---|---|---|---|
| P4a frontend-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a productcatalog-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b frontend-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b productcatalog-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC frontend-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC productcatalog-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC frontend-pause | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC productcatalog-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |

## Out-of-sample check (decision 65, 67): calibrated detectors on --validation no-fault cells, no refit

Validation campaigns: `tmp/otel-c-evidence/c1-fetch2/x` (input digest `87613b1ed652615f763bfb440b4dde03796b21ee29ab91618354405ebd0d4ad9`). Not used: `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/frontend-pause/r0p05-b01-11-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/frontend-pause/r0p05-b02-02-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/frontend-pause/r0p05-b03-10-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/frontend-pause/r0p2-b01-01-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/frontend-pause/r0p2-b02-08-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/frontend-pause/r0p2-b03-04-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/frontend-pause/r1-b01-06-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/frontend-pause/r1-b02-05-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/frontend-pause/r1-b03-12-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/frontend-pause/r10-b01-08-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/frontend-pause/r10-b02-04-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/frontend-pause/r10-b03-08-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/productcatalog-cpu-throttle/r0p05-b01-09-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/productcatalog-cpu-throttle/r0p05-b02-06-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/productcatalog-cpu-throttle/r0p05-b03-02-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/productcatalog-cpu-throttle/r0p2-b01-12-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/productcatalog-cpu-throttle/r0p2-b02-11-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/productcatalog-cpu-throttle/r0p2-b03-01-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/productcatalog-cpu-throttle/r1-b01-02-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/productcatalog-cpu-throttle/r1-b02-03-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/productcatalog-cpu-throttle/r1-b03-06-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/productcatalog-cpu-throttle/r10-b01-10-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/productcatalog-cpu-throttle/r10-b02-01-full` (a fault cell (validation uses no-fault cells only)); `tmp/otel-c-evidence/c1-fetch2/x/runs/effect/productcatalog-cpu-throttle/r10-b03-03-full` (a fault cell (validation uses no-fault cells only)).

- r10: 3 cells, 0.150 h (limit of this check: 20.0/h for 0 alarms); rules alarming 3 of 1578 calibrated: `metric:accountingservice:process.runtime.dotnet.jit.compilation_time/spike 1`, `metric:frauddetectionservice:kafka.consumer.join_time_avg/spike 1`, `metric:frauddetectionservice:kafka.consumer.join_time_max/spike 1`; sensors alarming 3 of 1110 placeable; all placeable sensors' union 2 (13.3/h [42.0], 0.15 of 0.15 h)
  - P4a frontend-pause-effect r10: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4a productcatalog-cpu-throttle-effect r10: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4b frontend-pause-effect r10: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4b productcatalog-cpu-throttle-effect r10: 0 (0.0/h [20.0], 0.15 of 0.15 h)
- r1: 3 cells, 0.150 h (limit of this check: 20.0/h for 0 alarms); rules alarming 15 of 1609 calibrated: `span:frontend:GET_//spike 2`, `ledger:frontendproxy:/api/products/66VCHSJNUP/failed 1`, `ledger:frontendproxy:/api/products/66VCHSJNUP/spike 1`, `log:frontendproxy:a933fde0fa35/appear 1`, `metric:accountingservice:dns.lookup.duration~mean/spike 1`, `metric:cartservice:process.runtime.dotnet.thread_pool.threads.count/spike 1`, `metric:cartservice:process.thread.count/spike 1`, `span:frontend:GET/absent 1`, `span:frontend:GET_/api/products/{productId}/absent 1`, `span:frontend:executing_api_route_(pages)_/api/products/[productId]/absent 1`, `span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct/absent 1`, `span:frontend:render_route_(pages)_//spike 1`, `span:frontendproxy:ingress/spike 1`, `span:frontendproxy:router_frontend_egress/spike 1`, `span:productcatalogservice:oteldemo.ProductCatalogService/GetProduct/absent 1`; sensors alarming 13 of 1138 placeable; all placeable sensors' union 14 (93.3/h [145.9], 0.15 of 0.15 h)
  - P4a frontend-pause-effect r1: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4a productcatalog-cpu-throttle-effect r1: 1 (6.7/h [31.6], 0.15 of 0.15 h)
  - P4b frontend-pause-effect r1: 0 (0.0/h [20.0], 0.15 of 0.15 h)
- r0.2: 3 cells, 0.150 h (limit of this check: 20.0/h for 0 alarms); rules alarming 2 of 1605 calibrated: `metric:frauddetectionservice:jvm.class.unloaded/spike 1`, `metric:frauddetectionservice:kafka.consumer.time_between_poll_max/median 1`; sensors alarming 2 of 1137 placeable; all placeable sensors' union 1 (6.7/h [31.6], 0.15 of 0.15 h)
  - P4a frontend-pause-effect r0.2: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4a productcatalog-cpu-throttle-effect r0.2: 0 (0.0/h [20.0], 0.15 of 0.15 h)
- r0.05: 3 cells, 0.150 h (limit of this check: 20.0/h for 0 alarms); rules alarming 6 of 1580 calibrated: `metric:frauddetectionservice:jvm.gc.duration~mean/spike 1`, `metric:frauddetectionservice:kafka.consumer.time_between_poll_max/median 1`, `metric:frontend:duration~mean/spike 1`, `metric:frontendproxy:duration~mean/spike 1`, `span:frontend:GET/spike 1`, `span:frontend:GET_//spike 1`; sensors alarming 6 of 1110 placeable; all placeable sensors' union 4 (26.7/h [61.0], 0.15 of 0.15 h)
  - P4a frontend-pause-effect r0.05: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4a productcatalog-cpu-throttle-effect r0.05: 0 (0.0/h [20.0], 0.15 of 0.15 h)
  - P4b frontend-pause-effect r0.05: 1 (6.7/h [31.6], 0.15 of 0.15 h)
  - P4b productcatalog-cpu-throttle-effect r0.05: 0 (0.0/h [20.0], 0.15 of 0.15 h)

## Primary outcome: time to detection at the calibrated values, misses charged at the hold end

Detected k/n · median [min-max] · **mean over all n** (with BC catches), then without BC. `—` = channel missing.

| class | rate | n | E | E no BC | L | L no BC | M | M no BC | S | S no BC | T | T no BC | L:own | L:own no BC | M:own | M:own no BC | S:own | S:own no BC | T:own | T:own no BC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| frontend-pause | 10 | 7 | 7/7 · 0.47 [0.42–0.48] · **0.46** | (= E) | 7/7 · 16.71 [11.61–16.82] · **16.00** | 7/7 · 21.70 [11.61–21.81] · **20.28** | 7/7 · 9.34 [9.08–9.69] · **9.35** | 7/7 · 9.34 [9.08–9.69] · **9.35** | — | — | 7/7 · 0.46 [0.41–0.47] · **0.45** | 7/7 · 15.25 [15.20–15.29] · **15.25** | 0/7 · **60.05** | 0/7 · **60.05** | 7/7 · 9.34 [9.08–9.69] · **9.35** | 7/7 · 9.34 [9.08–9.69] · **9.35** | — | — | 7/7 · 0.46 [0.41–0.48] · **0.46** | 0/7 · **60.05** |
| frontend-pause | 1 | 7 | 7/7 · 1.04 [0.53–1.29] · **0.92** | (= E) | 7/7 · 16.04 [11.24–16.65] · **14.85** | 7/7 · 21.04 [11.24–21.65] · **18.42** | 7/7 · 9.26 [8.76–9.61] · **9.19** | 7/7 · 9.26 [8.76–9.61] · **9.19** | — | — | 7/7 · 1.59 [1.07–1.83] · **1.46** | 7/7 · 15.93 [6.42–16.18] · **14.52** | 0/7 · **60.04** | 0/7 · **60.04** | 5/7 · 8.87 [8.47–9.00] · **23.46** | 5/7 · 8.87 [8.47–9.00] · **23.46** | — | — | 7/7 · 1.04 [0.52–1.28] · **0.92** | 0/7 · **60.04** |
| frontend-pause | 0.2 | 7 | 7/7 · 4.98 [2.84–7.38] · **4.95** | (= E) | 7/7 · 13.98 [6.79–16.19] · **13.21** | 7/7 · 18.98 [6.79–21.19] · **17.49** | 0/7 · **60.04** | 0/7 · **60.04** | — | — | 7/7 · 4.97 [2.83–7.37] · **4.94** | 7/7 · 17.33 [15.22–19.71] · **17.28** | 0/7 · **60.04** | 0/7 · **60.04** | 0/7 · **60.04** | 0/7 · **60.04** | — | — | 7/7 · 4.98 [2.83–7.37] · **4.95** | 0/7 · **60.04** |
| frontend-pause | 0.05 | 7 | 7/7 · 21.12 [15.70–27.98] · **21.68** | (= E) | 7/7 · 21.63 [9.43–27.01] · **20.28** | 7/7 · 25.75 [9.43–28.30] · **23.14** | 3/7 · 55.95 [55.34–59.40] · **58.69** | 3/7 · 55.95 [55.34–59.40] · **58.69** | — | — | 7/7 · 16.76 [15.43–22.95] · **18.18** | 7/7 · 20.58 [15.43–22.95] · **19.58** | 0/7 · **60.04** | 0/7 · **60.04** | 1/7 · 4.68 · **52.13** | 1/7 · 4.68 · **52.13** | — | — | 7/7 · 21.12 [15.70–27.97] · **21.68** | 0/7 · **60.04** |
| productcatalog-cpu-throttle | 10 | 7 | 0/7 · **60.04** | (= E) | 1/7 · 1.69 · **51.71** | 1/7 · 1.69 · **51.71** | 0/7 · **60.04** | 0/7 · **60.04** | — | — | 1/7 · 0.36 · **51.52** | 1/7 · 0.36 · **51.52** | 0/7 · **60.04** | 0/7 · **60.04** | 0/7 · **60.04** | 0/7 · **60.04** | — | — | 1/7 · 0.21 · **51.49** | 1/7 · 0.21 · **51.49** |
| productcatalog-cpu-throttle | 1 | 7 | 1/7 · 58.98 · **59.90** | (= E) | 1/7 · 1.51 · **51.69** | 1/7 · 1.51 · **51.69** | 0/7 · **60.05** | 0/7 · **60.05** | — | — | 1/7 · 58.98 · **59.90** | 1/7 · 58.98 · **59.90** | 0/7 · **60.05** | 0/7 · **60.05** | 0/7 · **60.05** | 0/7 · **60.05** | — | — | 0/7 · **60.05** | 0/7 · **60.05** |
| productcatalog-cpu-throttle | 0.2 | 7 | 0/7 · **60.06** | (= E) | 1/7 · 9.05 · **52.77** | 1/7 · 9.05 · **52.77** | 1/7 · 9.30 · **52.81** | 1/7 · 9.30 · **52.81** | — | — | 3/7 · 8.68 [5.82–10.24] · **37.85** | 3/7 · 8.68 [5.82–10.24] · **37.85** | 0/7 · **60.06** | 0/7 · **60.06** | 0/7 · **60.06** | 0/7 · **60.06** | — | — | 0/7 · **60.06** | 0/7 · **60.06** |
| productcatalog-cpu-throttle | 0.05 | 7 | 0/7 · **60.04** | (= E) | 1/7 · 7.03 · **52.47** | 1/7 · 7.03 · **52.47** | 1/7 · 54.52 · **59.25** | 1/7 · 54.52 · **59.25** | — | — | 0/7 · **60.04** | 0/7 · **60.04** | 0/7 · **60.04** | 0/7 · **60.04** | 2/7 · 56.74 [54.52–58.96] · **59.10** | 2/7 · 56.74 [54.52–58.96] · **59.10** | — | — | 1/7 · 45.48 · **57.96** | 1/7 · 45.48 · **57.96** |

## P1 detail (H4, decision 54)

- r10 b1: interval 0.244 s (intervention appliedMonotonic (after the command returned and docker inspect saw the state; the cell keeps no Docker events)); expected [15.089, 15.287] +- 0.008 s; observed 15.287; holds via **timeout interval**
- r10 b1: interval 0.203 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [15.008, 15.203] +- 0.008 s; observed 15.206; holds via **timeout interval**
- r10 b2: interval 0.181 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [15.049, 15.252] +- 0.008 s; observed 15.256; holds via **timeout interval**
- r10 b3: interval 0.220 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [15.084, 15.288] +- 0.008 s; observed 15.293; holds via **timeout interval**
- r10 b1: interval 0.227 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [15.048, 15.248] +- 0.008 s; observed 15.250; holds via **timeout interval**
- r10 b2: interval 0.209 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [15.009, 15.225] +- 0.008 s; observed 15.227; holds via **timeout interval**
- r10 b3: interval 0.190 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [15.061, 15.261] +- 0.008 s; observed 15.265; holds via **timeout interval**
- r1 b1: interval 0.240 s (intervention appliedMonotonic (after the command returned and docker inspect saw the state; the cell keeps no Docker events)); expected [15.509, 15.509] +- 0.009 s; observed 15.513; holds via **timeout interval**
- r1 b1: interval 0.188 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [15.930, 15.930] +- 0.009 s; observed 15.933; holds via **timeout interval**
- r1 b2: interval 0.222 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [15.441, 15.441] +- 0.009 s; observed 6.421; ✗
- r1 b3: interval 0.195 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [15.145, 16.146] +- 0.009 s; observed 16.150; holds via **timeout interval**
- r1 b1: interval 0.207 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [15.174, 16.175] +- 0.009 s; observed 16.179; holds via **timeout interval**
- r1 b2: interval 0.208 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [15.986, 15.986] +- 0.009 s; observed 15.993; holds via **timeout interval**
- r1 b3: interval 0.235 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [15.473, 15.473] +- 0.009 s; observed 15.475; holds via **timeout interval**
- r0.2 b1: interval 0.233 s (intervention appliedMonotonic (after the command returned and docker inspect saw the state; the cell keeps no Docker events)); expected [15.220, 15.220] +- 0.011 s; observed 15.224; holds via **timeout interval**
- r0.2 b1: interval 0.218 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [16.373, 16.373] +- 0.011 s; observed 16.378; holds via **timeout interval**
- r0.2 b2: interval 0.207 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [17.331, 17.331] +- 0.009 s; observed 17.335; holds via **timeout interval**
- r0.2 b3: interval 0.207 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [19.706, 19.706] +- 0.010 s; observed 19.709; holds via **timeout interval**
- r0.2 b1: interval 0.218 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [18.390, 18.390] +- 0.011 s; observed 18.395; holds via **timeout interval**
- r0.2 b2: interval 0.217 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [17.510, 17.510] +- 0.010 s; observed 17.514; holds via **timeout interval**
- r0.2 b3: interval 0.173 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [16.446, 16.446] +- 0.010 s; observed 16.449; holds via **timeout interval**
- r0.05 b1: interval 0.221 s (intervention appliedMonotonic (after the command returned and docker inspect saw the state; the cell keeps no Docker events)); expected [32.784, 32.784] +- 0.014 s; observed 32.789; holds via **timeout interval**
- r0.05 b1: interval 0.205 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [30.822, 30.822] +- 0.012 s; observed 30.823; holds via **timeout interval**
- r0.05 b2: interval 0.201 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [21.619, 21.619] +- 0.011 s; observed 21.623; holds via **timeout interval**
- r0.05 b3: interval 0.227 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [24.963, 24.963] +- 0.012 s; observed 24.964; holds via **timeout interval**
- r0.05 b1: interval 0.208 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [29.046, 29.046] +- 0.014 s; observed 29.051; holds via **timeout interval**
- r0.05 b2: interval 0.225 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [20.579, 20.579] +- 0.011 s; observed 20.584; holds via **timeout interval**
- r0.05 b3: interval 0.195 s (Docker `pause` event of frontend, docker-events.json (otel-demo-fault-docker-events-v1, the producer's mapping bm + (timeNano/1e9 - be))); expected [25.957, 25.957] +- 0.011 s; observed 25.960; holds via **timeout interval**

- The ledger's calibrated `absent` against the client timeout: r10 /api/products/66VCHSJNUP: calibrated m 1 g 0.308 s vs timeout 15 s; `absent` before the first `failed` in 7/7 pause episodes; r1 /api/products/66VCHSJNUP: calibrated m 1 g 1.102 s vs timeout 15 s; `absent` before the first `failed` in 7/7 pause episodes; r0.2 /api/products/66VCHSJNUP: calibrated m 1.5 g 7.670 s vs timeout 15 s; `absent` before the first `failed` in 7/7 pause episodes; r0.05 /api/products/66VCHSJNUP: calibrated m 1.5 g 30.122 s vs timeout 15 s; `absent` before the first `failed` in 7/7 pause episodes.

## Exposure (H5): recorded, the objective unchanged

Route call path: frontend, frontendproxy, productcatalogservice. Episodes with no request started in the fault window: 0 of 56. Never-exposed sensors: 1145.

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
