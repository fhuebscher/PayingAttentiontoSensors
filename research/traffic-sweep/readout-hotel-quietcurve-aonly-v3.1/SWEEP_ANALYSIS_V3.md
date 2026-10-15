# Traffic sweep, Hotel: analysis v3 (v3.1), exploratory, not frozen (every cell of this system was read under v2.4 before v3 was written) (x + x)

**Exploratory, not frozen.** Protocol rounds 15 and 17 (decisions 61-65 as amended by 67) on v2.4's readers and rules; every cell read here was read under v2.4 first. **Scope: instance** (one SUT, one host). `—` = absent or not evaluable, never 0. Each (sensor, rule) is calibrated per rate by the zero-held-out-alarm selection; **no false-alarm figure here is that selection's own zero**: every count of false alarms is the honest nested leave-one-cell-out count (V3_NESTED_RULE), with its exact 95 % bound.

Binding documents and inputs: research/PROTOCOL_DRAFT_20261002.md round 15 (decisions 61-65, 252cfcd); research/protocol/ANALYSIS_V3_DESIGN.md (252cfcd); research/traffic-sweep/SYNTHESIS_V2_4.md; research/protocol/parameters_v3.json (decision 37); research/traffic-sweep/DECLARATION.md (a795fc9); research/traffic-sweep/AMENDMENT_1.md (6aca1ff); research/traffic-sweep/AMENDMENT_2.md (ddf03df); research/traffic-sweep/AMENDMENT_3.md (a7d509d); research/protocol/METHODOLOGY_HARDENING.md (H1-H11); research/PROTOCOL_DRAFT_20261002.md rounds 7-14 (decisions 26-60; round 11 = aae8898, decision 57 = d126589, round 13 = 6162c37, round 14 = c17f6a6); research/traffic-sweep/readout-hotel-r3/REVIEW.md (a61801c, the v1 review); research/traffic-sweep/readout-hotel-r3-v2-fix1/REVIEW.md (cb795c5, the v2 review); research/protocol/parameters.json (decision 37).

Analysis: `research/detection-time/sweep_analysis_v3.py` v3 (sha256 `2e7ec5c387fa906a02026f0d1a5212b974f17751c24f76526a1d8418b2fd4fdd`) on v2.4 `sweep_analysis_v2.py` (sha256 `075c43e5870170c8b59cdbe1a970b56dc03920d67514027b9a95e5de38d962e9`), parameters.json `7447b492abf64f42ebaf547a640c84929ac15b59ebc1e495d5082f279373fc68`, parameters_v3.json `f6257b78fedfdcab9577f37cdba77a6fc6d785e4b0b34641cb18de6bb21ade9a`, HEAD `48829ff2ed17165a9586b1b84a55cfb8664d78a2`, Python 3.13.12.

## Outputs that are — by construction

- availability-clock P4 verdict for family T: no measured collector receive stamp (AVAILABILITY_SOURCES, decision 43).
- P3 (every fault): no family is traffic-independent by mechanism (H11).
- out-of-sample check (decision 65): no --validation cells given (campaign B's no-fault cells are the declared source).
- a false-alarm figure from the zero-alarm selection itself: never printed (decision 67): the selected value has 0 held-out alarms on the cells it was chosen on by construction; every false-alarm count below is the honest nested one.

## What was read

Campaigns pooled (H1; decision 68: quiet runs A and A2 pool with the sweep):

- `tmp/hotelsweep3-evidence/x`: 64 valid of 64 (cpu-throttle 16, net-delay 16, no-fault-calibration 16, search-pause 16)
- `tmp/hotelquiet1-evidence/x`: 40 valid of 40 (no-fault-calibration 40)

| class | r10 valid/found | r1 valid/found | r0.2 valid/found | r0.05 valid/found |
|---|---|---|---|---|
| no-fault-calibration | 14/14 | 14/14 | 14/14 | 14/14 |
| search-pause | 4/4 | 4/4 | 4/4 | 4/4 |
| cpu-throttle | 4/4 | 4/4 | 4/4 | 4/4 |
| net-delay | 4/4 | 4/4 | 4/4 | 4/4 |

Cells not scored: none.

Provenance: harness commit `ca58974785c97fe54afe351f928c65fa46f18403`; input digest `b4cb9ab9a1cb3fb4482f84fa0f9515b5e15f8c4bd36b61f0e3f873de4d6a16d6` over 1298 files (v2.4's file set plus docker-events.json[l]).

H4 freeze record per harness and status (V3_FREEZE_EVENTS_RULE; decision 69: a missing or contradictory record keeps the sweep's bound and is counted): sweep: Hotel: docker-events.jsonl (v2.4) 48; reasons: none.

## Calibration per (sensor, rule) on the no-fault cells (decisions 61-63, 67)

Each armed (sensor, rule) takes the smallest grid value with zero held-out alarms over the rate's no-fault cells, each scored leave-one-cell-out (v2.4's fit, H1; class-independent). Level rules: K_GRID (<= 100; K = 100 flagged at grid edge), then the range fallback (discrete in effect; up-only for spans and the ledger; may apply where MAD = 0, decision 52 kept for K); `absent`: m x G on m in {1, 1.5, 2, 3, 5}, G including the censored silences of cells with records; an `absent` whose gap exceeds the shortest hold (60.000 s) is **inert**; `appear` per stream; the ledger's `failed` exempt. **honest** = the nested count (each held-out cell at the value re-selected without it), the false-alarm figure; its rate per hour of no-fault time T.

| rate | no-fault cells | T (h) | rules calibrated / dropped / inert / unarmed | at grid edge | range (of them MAD = 0) | sensors placeable / appear-only / not (L, M, S, T) | dof | E `failed` in no-fault (exempt) | calibrated rules: median folds armed of the rate's cells · out of the detector in every nested fold · honest — (no nested evidence) | placeable sensors with CELF cost — |
|---|---|---|---|---|---|---|---|---|---|---|
| r10 | 14 | 0.700 | 391 / 4 / 1 / 313 | 2 | 13 (13) | 55 / 211 / 31 | 180 | hotel-search-v1 0 | 14 of 14 · 0 · 0 | 4 |
| r1 | 14 | 0.700 | 391 / 4 / 1 / 314 | 1 | 26 (26) | 55 / 211 / 31 | 180 | hotel-search-v1 0 | 14 of 14 · 0 · 0 | 3 |
| r0.2 | 14 | 0.700 | 392 / 2 / 1 / 313 | 1 | 34 (34) | 55 / 210 / 31 | 182 | hotel-search-v1 0 | 14 of 14 · 0 · 0 | 3 |
| r0.05 | 14 | 0.700 | 389 / 5 / 1 / 313 | 0 | 43 (43) | 55 / 210 / 31 | 179 | hotel-search-v1 0 | 14 of 14 · 0 · 0 | 3 |

Per family and rule (primary): calibrated / dropped / inert / unarmed.

| rate | family | appear | absent | spike | run3 | median |
|---|---|---|---|---|---|---|
| r10 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r10 | L | 207 / 0 / 0 / 1 | 0 / 0 / 1 / 207 | — | — | — |
| r10 | M | — | — | 10 / 0 / 0 / 0 | 10 / 0 / 0 / 0 | 10 / 0 / 0 / 0 |
| r10 | S | — | — | 28 / 2 / 0 / 30 | 30 / 0 / 0 / 30 | 30 / 0 / 0 / 30 |
| r10 | T | 4 / 0 / 0 / 15 | 15 / 0 / 0 / 0 | 13 / 2 / 0 / 0 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 |
| r1 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r1 | L | 208 / 0 / 0 / 1 | 0 / 0 / 1 / 208 | — | — | — |
| r1 | M | — | — | 10 / 0 / 0 / 0 | 10 / 0 / 0 / 0 | 10 / 0 / 0 / 0 |
| r1 | S | — | — | 26 / 4 / 0 / 30 | 30 / 0 / 0 / 30 | 30 / 0 / 0 / 30 |
| r1 | T | 3 / 0 / 0 / 15 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 |
| r0.2 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r0.2 | L | 207 / 0 / 0 / 1 | 0 / 0 / 1 / 207 | — | — | — |
| r0.2 | M | — | — | 8 / 2 / 0 / 0 | 10 / 0 / 0 / 0 | 10 / 0 / 0 / 0 |
| r0.2 | S | — | — | 30 / 0 / 0 / 30 | 30 / 0 / 0 / 30 | 30 / 0 / 0 / 30 |
| r0.2 | T | 3 / 0 / 0 / 15 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 |
| r0.05 | E | — | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 0 |
| r0.05 | L | 207 / 0 / 0 / 1 | 0 / 0 / 1 / 207 | — | — | — |
| r0.05 | M | — | — | 5 / 5 / 0 / 0 | 10 / 0 / 0 / 0 | 10 / 0 / 0 / 0 |
| r0.05 | S | — | — | 30 / 0 / 0 / 30 | 30 / 0 / 0 / 30 | 30 / 0 / 0 / 30 |
| r0.05 | T | 3 / 0 / 0 / 15 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 |

**The ledger E** per rate (route; `failed` **exempt**, decision 63: never calibrated, always compared; its no-fault count is reported):

- r10: `absent` calibrated (m 1.5, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 25, honest 0).
- r1: `absent` calibrated (m 1.5, honest 0); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 8, honest 1).
- r0.2: `absent` calibrated (m 1.5, honest 1); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 4, honest 1).
- r0.05: `absent` calibrated (m 1.5, honest 1); `failed` exempt (no-fault count 0); `median` calibrated (K 2.5, honest 0); `run3` calibrated (K 2.5, honest 0); `spike` calibrated (K 2.5, honest 0).
- E's catching rule in the episodes (primary): cpu-throttle r0.05: `—` 4; cpu-throttle r0.2: `spike` 1, `—` 3; cpu-throttle r1: `—` 4; cpu-throttle r10: `spike` 2, `—` 2; net-delay r0.05: `spike` 4; net-delay r0.2: `spike` 4; net-delay r1: `spike` 4; net-delay r10: `absent` 4; search-pause r0.05: `failed` 4; search-pause r0.2: `failed` 4; search-pause r1: `absent` 4; search-pause r10: `absent` 4.

**Dropped (sensor, rule) pairs** (held-out alarms at the last grid value; honest count beside), primary:

- r10 (4): `span:profile:memcached_get_profile/spike` 2 (honest —), `metric:geo:sys_psi_cpu/spike` 1 (honest 1), `metric:user:sys_psi_cpu/spike` 1 (honest 1), `span:rate:memcached_get_multi_rate/spike` 1 (honest 1)
- r1 (4): `metric:frontend:sys_psi_cpu/spike` 3 (honest 3), `metric:profile:sys_psi_cpu/spike` 1 (honest 1), `metric:rate:sys_psi_cpu/spike` 1 (honest —), `metric:reservation:sys_psi_cpu/spike` 1 (honest 1)
- r0.2 (2): `metric:attractions:cpu/spike` 1 (honest 1), `metric:review:cpu/spike` 1 (honest —)
- r0.05 (5): `metric:attractions:cpu/spike` 1 (honest 1), `metric:frontend:cpu/spike` 1 (honest —), `metric:recommendation:cpu/spike` 1 (honest —), `metric:review:cpu/spike` 1 (honest —), `metric:search:cpu/spike` 1 (honest —)

**Inert** (calibrated by the selection, but the gap exceeds the hold; not placeable), **at grid edge** (K = 100) and **appear-only** sensors (placeable through `appear` alone, listed apart), primary:

- r10: inert 1: `log:frontend:1c9632baa7b5/absent`; at grid edge 2: `span:geo:/geo.Geo/Nearby/spike`, `span:profile:/profile.Profile/GetProfiles/spike`; appear-only 211: `log:attractions:01e8eaa045e2`, `log:attractions:055dfa393986`, `log:attractions:276af8399ab1`, `log:attractions:2921b55e8c5d`, `log:attractions:35a7c43dcf3a`, `log:attractions:3d4eddfab798`, `log:attractions:40123bda2132`, `log:attractions:4110dcc48969`, `log:attractions:4ff7b7b4686d`, `log:attractions:54654c857d3a`, `log:attractions:5936d995d33c`, `log:attractions:6c24cb701e52`, `log:attractions:8c534c41c8a4`, `log:attractions:9056009088d7`, `log:attractions:9430a0f79158`, `log:attractions:9a746e6bda81`, `log:attractions:b73537dfcea0`, `log:attractions:bd7a3576df3d`, `log:attractions:cf8f513bcc77`, `log:attractions:dbfb07b81d0d`, `log:attractions:eb790194c36c`, `log:attractions:f23bf73a52ab`, `log:attractions:f598fad96168`, `log:attractions:fbcffe4122dc`, `log:frontend:01e8eaa045e2`, `log:frontend:4c991508b008`, `log:frontend:4ff7b7b4686d`, `log:frontend:54654c857d3a`, `log:frontend:58101b7e189c`, `log:frontend:6409fbc62d41`, `log:frontend:6afb7a2a9a8a`, `log:frontend:76ad34b88297`, `log:frontend:7a40a8b4a863`, `log:frontend:9056009088d7`, `log:frontend:905fd48af873`, `log:frontend:9430a0f79158`, `log:frontend:9545bd7940eb`, `log:frontend:9b2f7fc21c10`, `log:frontend:c2625d3f7b03`, `log:frontend:dc0a2b88d05c` (+171 more in the JSON).
- r1: inert 1: `log:frontend:1c9632baa7b5/absent`; at grid edge 1: `span:geo:/geo.Geo/Nearby/spike`; appear-only 211: `log:attractions:01e8eaa045e2`, `log:attractions:055dfa393986`, `log:attractions:276af8399ab1`, `log:attractions:2921b55e8c5d`, `log:attractions:35a7c43dcf3a`, `log:attractions:3d4eddfab798`, `log:attractions:40123bda2132`, `log:attractions:4110dcc48969`, `log:attractions:4ff7b7b4686d`, `log:attractions:54654c857d3a`, `log:attractions:5936d995d33c`, `log:attractions:6c24cb701e52`, `log:attractions:8c534c41c8a4`, `log:attractions:9056009088d7`, `log:attractions:9430a0f79158`, `log:attractions:9a746e6bda81`, `log:attractions:b73537dfcea0`, `log:attractions:bd7a3576df3d`, `log:attractions:cf8f513bcc77`, `log:attractions:dbfb07b81d0d`, `log:attractions:eb790194c36c`, `log:attractions:f23bf73a52ab`, `log:attractions:f598fad96168`, `log:attractions:fbcffe4122dc`, `log:frontend:01e8eaa045e2`, `log:frontend:4ae82b46d72e`, `log:frontend:4c991508b008`, `log:frontend:4ff7b7b4686d`, `log:frontend:54654c857d3a`, `log:frontend:58101b7e189c`, `log:frontend:6409fbc62d41`, `log:frontend:6afb7a2a9a8a`, `log:frontend:76ad34b88297`, `log:frontend:7a40a8b4a863`, `log:frontend:9056009088d7`, `log:frontend:905fd48af873`, `log:frontend:9430a0f79158`, `log:frontend:9545bd7940eb`, `log:frontend:9b2f7fc21c10`, `log:frontend:c2625d3f7b03` (+171 more in the JSON).
- r0.2: inert 1: `log:frontend:1c9632baa7b5/absent`; at grid edge 1: `metric:frontend:cpu/spike`; appear-only 210: `log:attractions:01e8eaa045e2`, `log:attractions:055dfa393986`, `log:attractions:276af8399ab1`, `log:attractions:2921b55e8c5d`, `log:attractions:35a7c43dcf3a`, `log:attractions:3d4eddfab798`, `log:attractions:40123bda2132`, `log:attractions:4110dcc48969`, `log:attractions:4ff7b7b4686d`, `log:attractions:54654c857d3a`, `log:attractions:5936d995d33c`, `log:attractions:6c24cb701e52`, `log:attractions:8c534c41c8a4`, `log:attractions:9056009088d7`, `log:attractions:9430a0f79158`, `log:attractions:9a746e6bda81`, `log:attractions:b73537dfcea0`, `log:attractions:bd7a3576df3d`, `log:attractions:cf8f513bcc77`, `log:attractions:dbfb07b81d0d`, `log:attractions:eb790194c36c`, `log:attractions:f23bf73a52ab`, `log:attractions:f598fad96168`, `log:attractions:fbcffe4122dc`, `log:frontend:01e8eaa045e2`, `log:frontend:4c991508b008`, `log:frontend:4ff7b7b4686d`, `log:frontend:54654c857d3a`, `log:frontend:58101b7e189c`, `log:frontend:6409fbc62d41`, `log:frontend:6afb7a2a9a8a`, `log:frontend:76ad34b88297`, `log:frontend:7a40a8b4a863`, `log:frontend:9056009088d7`, `log:frontend:905fd48af873`, `log:frontend:9430a0f79158`, `log:frontend:9545bd7940eb`, `log:frontend:9b2f7fc21c10`, `log:frontend:c2625d3f7b03`, `log:frontend:dc0a2b88d05c` (+170 more in the JSON).
- r0.05: inert 1: `log:frontend:1c9632baa7b5/absent`; at grid edge 0: none; appear-only 210: `log:attractions:01e8eaa045e2`, `log:attractions:055dfa393986`, `log:attractions:276af8399ab1`, `log:attractions:2921b55e8c5d`, `log:attractions:35a7c43dcf3a`, `log:attractions:3d4eddfab798`, `log:attractions:40123bda2132`, `log:attractions:4110dcc48969`, `log:attractions:4ff7b7b4686d`, `log:attractions:54654c857d3a`, `log:attractions:5936d995d33c`, `log:attractions:6c24cb701e52`, `log:attractions:8c534c41c8a4`, `log:attractions:9056009088d7`, `log:attractions:9430a0f79158`, `log:attractions:9a746e6bda81`, `log:attractions:b73537dfcea0`, `log:attractions:bd7a3576df3d`, `log:attractions:cf8f513bcc77`, `log:attractions:dbfb07b81d0d`, `log:attractions:eb790194c36c`, `log:attractions:f23bf73a52ab`, `log:attractions:f598fad96168`, `log:attractions:fbcffe4122dc`, `log:frontend:01e8eaa045e2`, `log:frontend:4c991508b008`, `log:frontend:4ff7b7b4686d`, `log:frontend:54654c857d3a`, `log:frontend:58101b7e189c`, `log:frontend:6409fbc62d41`, `log:frontend:6afb7a2a9a8a`, `log:frontend:76ad34b88297`, `log:frontend:7a40a8b4a863`, `log:frontend:9056009088d7`, `log:frontend:905fd48af873`, `log:frontend:9430a0f79158`, `log:frontend:9545bd7940eb`, `log:frontend:9b2f7fc21c10`, `log:frontend:c2625d3f7b03`, `log:frontend:dc0a2b88d05c` (+170 more in the JSON).

**Not placeable at this quiet time** (L, M, S, T sensors with no calibrated rule), by family (with a dropped rule / inert / unarmed only), then those with a dropped rule:

- r10: 31 sensors (L 0/1/0, S 0/0/30); with a dropped rule: none
- r1: 31 sensors (L 0/1/0, S 0/0/30); with a dropped rule: none
- r0.2: 31 sensors (L 0/1/0, S 0/0/30); with a dropped rule: none
- r0.05: 31 sensors (L 0/1/0, S 0/0/30); with a dropped rule: none

- `appear` (V3_APPEAR_RULE): new streams in no-fault cells per service, summed over the held-out cells (they enter the honest counts): r10 none; r1 none; r0.2 none; r0.05 none.
- **floor arm (share 0.05)**: r10 391/4/1/313 rules, 55 placeable + 211 appear-only sensors; r1 391/4/1/314 rules, 55 placeable + 211 appear-only sensors; r0.2 392/2/1/313 rules, 55 placeable + 210 appear-only sensors; r0.05 389/5/1/313 rules, 55 placeable + 210 appear-only sensors.
- **sensitivity, <= 1 held-out alarm (K_GRID only, no range fallback)**: r10 379/1/1/328 rules, 50 placeable + 211 appear-only sensors; r1 365/0/1/344 rules, 45 placeable + 211 appear-only sensors; r0.2 358/0/1/349 rules, 43 placeable + 210 appear-only sensors; r0.05 346/0/1/361 rules, 39 placeable + 210 appear-only sensors.

## Honest false alarms (decisions 64, 67): nested leave-one-cell-out unions on the no-fault cells

Union of the sensors' rules, each held-out no-fault cell scored at the values re-selected without it (its leave-one-cell-out fit), restarted after each alarm: count (/h [exact 95 % bound]); per family also the sum of its calibrated rules' honest counts (the reviewer's tally). The honest per-sensor rate is the sensor's false-alarm cost for CELF (JSON calibration.*.sensors.*.honestPerHour). Campaign B's fresh check can certify at best 20.0/h (0 alarms in 0.15 h per rate).

| setting | rate | T (h) | E | L | M | S | T | all placeable L, M, S, T |
|---|---|---|---|---|---|---|---|---|
| primary | r10 | 0.700 | 0 (0.0/h [4.3], 0.700 of 0.70 h) · sum 0 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [4.3], 0.700 of 0.70 h) · sum 0 · no evidence: 0 rules, 0 sensors | 9 (12.9/h [22.4], 0.700 of 0.70 h) · sum 9 · no evidence: 0 rules, 0 sensors | 118 (168.6/h [196.4], 0.700 of 0.70 h) · sum 293 · no evidence: 0 rules, 0 sensors | 40 (57.1/h [74.4], 0.700 of 0.70 h) · sum 28 · no evidence: 0 rules, 4 sensors | 211 (301.4/h [337.9], 0.70 of 0.70 h) |
| primary | r1 | 0.700 | 1 (1.4/h [6.8], 0.700 of 0.70 h) · sum 1 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [4.3], 0.700 of 0.70 h) · sum 0 · no evidence: 0 rules, 0 sensors | 14 (20.0/h [31.3], 0.700 of 0.70 h) · sum 8 · no evidence: 0 rules, 0 sensors | 8 (11.4/h [20.6], 0.700 of 0.70 h) · sum 3 · no evidence: 0 rules, 0 sensors | 24 (34.3/h [48.2], 0.700 of 0.70 h) · sum 22 · no evidence: 0 rules, 3 sensors | 66 (94.3/h [115.7], 0.70 of 0.70 h) |
| primary | r0.2 | 0.700 | 2 (2.9/h [9.0], 0.700 of 0.70 h) · sum 2 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [4.3], 0.700 of 0.70 h) · sum 0 · no evidence: 0 rules, 0 sensors | 10 (14.3/h [24.2], 0.700 of 0.70 h) · sum 8 · no evidence: 0 rules, 0 sensors | 77 (110.0/h [133.0], 0.700 of 0.70 h) · sum 303 · no evidence: 0 rules, 0 sensors | 31 (44.3/h [59.8], 0.700 of 0.70 h) · sum 25 · no evidence: 0 rules, 3 sensors | 133 (190.0/h [219.4], 0.70 of 0.70 h) |
| primary | r0.05 | 0.700 | 1 (1.4/h [6.8], 0.700 of 0.70 h) · sum 1 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [4.3], 0.700 of 0.70 h) · sum 0 · no evidence: 0 rules, 0 sensors | 6 (8.6/h [16.9], 0.700 of 0.70 h) · sum 5 · no evidence: 0 rules, 0 sensors | 119 (170.0/h [198.0], 0.700 of 0.70 h) · sum 194 · no evidence: 0 rules, 0 sensors | 23 (32.9/h [46.6], 0.700 of 0.70 h) · sum 21 · no evidence: 0 rules, 3 sensors | 147 (210.0/h [240.8], 0.70 of 0.70 h) |
| atMostOne | r10 | 0.700 | 1 (1.4/h [6.8], 0.700 of 0.70 h) · sum 1 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [4.3], 0.700 of 0.70 h) · sum 0 · no evidence: 0 rules, 0 sensors | 15 (21.4/h [33.0], 0.700 of 0.70 h) · sum 14 · no evidence: 0 rules, 0 sensors | 126 (180.0/h [208.7], 0.700 of 0.70 h) · sum 338 · no evidence: 0 rules, 0 sensors | 90 (128.6/h [153.2], 0.700 of 0.70 h) · sum 66 · no evidence: 0 rules, 4 sensors | 303 (432.9/h [476.1], 0.70 of 0.70 h) |
| atMostOne | r1 | 0.700 | 4 (5.7/h [13.1], 0.700 of 0.70 h) · sum 4 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [4.3], 0.700 of 0.70 h) · sum 0 · no evidence: 0 rules, 0 sensors | 57 (81.4/h [101.5], 0.700 of 0.70 h) · sum 24 · no evidence: 0 rules, 0 sensors | 9 (12.9/h [22.4], 0.700 of 0.70 h) · sum 9 · no evidence: 0 rules, 0 sensors | 46 (65.7/h [84.0], 0.700 of 0.70 h) · sum 39 · no evidence: 0 rules, 3 sensors | 152 (217.1/h [248.4], 0.70 of 0.70 h) |
| atMostOne | r0.2 | 0.700 | 3 (4.3/h [11.1], 0.700 of 0.70 h) · sum 3 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [4.3], 0.700 of 0.70 h) · sum 0 · no evidence: 0 rules, 0 sensors | 16 (22.9/h [34.7], 0.700 of 0.70 h) · sum 15 · no evidence: 0 rules, 0 sensors | 78 (111.4/h [134.5], 0.700 of 0.70 h) · sum 305 · no evidence: 0 rules, 0 sensors | 46 (65.7/h [84.0], 0.700 of 0.70 h) · sum 38 · no evidence: 0 rules, 3 sensors | 167 (238.6/h [271.2], 0.70 of 0.70 h) |
| atMostOne | r0.05 | 0.700 | 1 (1.4/h [6.8], 0.700 of 0.70 h) · sum 1 · no evidence: 0 rules, 1 sensors | 0 (0.0/h [4.3], 0.700 of 0.70 h) · sum 0 · no evidence: 0 rules, 0 sensors | 5 (7.1/h [15.0], 0.700 of 0.70 h) · sum 5 · no evidence: 0 rules, 0 sensors | 123 (175.7/h [204.1], 0.700 of 0.70 h) · sum 200 · no evidence: 0 rules, 0 sensors | 35 (50.0/h [66.3], 0.700 of 0.70 h) · sum 33 · no evidence: 0 rules, 3 sensors | 161 (230.0/h [262.1], 0.70 of 0.70 h) |

P4-selected sets (the sensors P4 selected over its folds, or with one episode the candidates judged a win), honest nested union, primary:

- P4a cpu-throttle-effect r0.05: `metric:frontend:sys_cpu` -> 2 (2.9/h [9.0], 0.70 of 0.70 h) · sum over the sensors 2
- P4a cpu-throttle-effect r0.2: `metric:frontend:cpu` -> 1 (1.4/h [6.8], 0.70 of 0.70 h) · sum over the sensors 1
- P4a cpu-throttle-effect r1: `metric:reservation:cpu` -> 5 (7.1/h [15.0], 0.70 of 0.70 h) · sum over the sensors 5
- P4a cpu-throttle-effect r10: `span:frontend:HTTP_GET_/hotels` -> 0 (0.0/h [4.3], 0.70 of 0.70 h) · sum over the sensors 0
- P4a net-delay-effect r0.05: `metric:frontend:sys_cpu`, `metric:search:sys_cpu`, `span:reservation:memcached_reserve_get_multi_number` -> 3 (4.3/h [11.1], 0.70 of 0.70 h) · sum over the sensors 3
- P4a net-delay-effect r0.2: `span:search:/search.Search/Nearby` -> 0 (0.0/h [4.3], 0.70 of 0.70 h) · sum over the sensors 0
- P4a net-delay-effect r1: `span:reservation:memcached_reserve_get_multi_number` -> 0 (0.0/h [4.3], 0.70 of 0.70 h) · sum over the sensors 0
- P4a net-delay-effect r10: `span:search:/search.Search/Nearby` -> 2 (2.9/h [9.0], 0.70 of 0.70 h) · sum over the sensors 2
- P4a search-pause-effect r0.05: `span:frontend:HTTP_GET_/hotels` -> 1 (1.4/h [6.8], 0.70 of 0.70 h) · sum over the sensors 1
- P4a search-pause-effect r0.2: `span:frontend:HTTP_GET_/hotels` -> 1 (1.4/h [6.8], 0.70 of 0.70 h) · sum over the sensors 1
- P4a search-pause-effect r1: `span:frontend:HTTP_GET_/hotels` -> 0 (0.0/h [4.3], 0.70 of 0.70 h) · sum over the sensors 0
- P4a search-pause-effect r10: `span:frontend:HTTP_GET_/hotels` -> 0 (0.0/h [4.3], 0.70 of 0.70 h) · sum over the sensors 0
- P4b cpu-throttle-effect r0.05: `metric:profile:cpu`, `metric:profile:sys_cpu` -> 2 (2.9/h [9.0], 0.70 of 0.70 h) · sum over the sensors 2
- P4b cpu-throttle-effect r0.2: `metric:profile:cpu` -> 0 (0.0/h [4.3], 0.70 of 0.70 h) · sum over the sensors 0
- P4b cpu-throttle-effect r10: `span:profile:/profile.Profile/GetProfiles` -> 3 (4.3/h [11.1], 0.70 of 0.70 h) · sum over the sensors 3
- P4b net-delay-effect r0.05: `metric:rate:sys_cpu`, `span:rate:memcached_get_multi_rate` -> 1 (1.4/h [6.8], 0.70 of 0.70 h) · sum over the sensors 1
- P4b net-delay-effect r0.2: `span:rate:/rate.Rate/GetRates` -> 1 (1.4/h [6.8], 0.70 of 0.70 h) · sum over the sensors 1
- P4b net-delay-effect r1: `span:rate:memcached_get_multi_rate` -> 1 (1.4/h [6.8], 0.70 of 0.70 h) · sum over the sensors 1
- P4b net-delay-effect r10: `span:rate:memcached_get_multi_rate` -> 3 (4.3/h [11.1], 0.70 of 0.70 h) · sum over the sensors 3
- P4b search-pause-effect r10: `metric:search:sys_psi_cpu` -> 1 (1.4/h [6.8], 0.70 of 0.70 h) · sum over the sensors 1

## v2.4 reference row: family operating point (decision 53, 15/h, from v2.4's own code)

K per family: E 20, L 2.5, M 100, S 63, T 50, system 100.

| class | family | r10 | r1 | r0.2 | r0.05 |
|---|---|---|---|---|---|
| search-pause | E | ok (K 20) | ok (K 20) | ok (K 20) | ok (K 20) |
| search-pause | L | ok (K 2.5) | ok (K 2.5) | ok (K 2.5) | ok (K 2.5) |
| search-pause | M | ok (K 100) | ok (K 100) | ok (K 100) | ok (K 100) |
| search-pause | S | ok (K 63) | ok (K 63) | ok (K 63) | ok (K 63) |
| search-pause | T | ok (K 50) | ok (K 50) | ok (K 50) | ok (K 50) |
| cpu-throttle | E | ok (K 20) | ok (K 20) | ok (K 20) | ok (K 20) |
| cpu-throttle | L | no | no | no | no |
| cpu-throttle | M | ok (K 100) | ok (K 100) | ok (K 100) | ok (K 100) |
| cpu-throttle | S | ok (K 63) | ok (K 63) | ok (K 63) | ok (K 63) |
| cpu-throttle | T | no | ok (K 50) | ok (K 50) | ok (K 50) |
| net-delay | E | ok (K 20) | ok (K 20) | ok (K 20) | ok (K 20) |
| net-delay | L | no | no | no | no |
| net-delay | M | ok (K 100) | ok (K 100) | ok (K 100) | ok (K 100) |
| net-delay | S | ok (K 63) | ok (K 63) | ok (K 63) | ok (K 63) |
| net-delay | T | ok (K 50) | ok (K 50) | ok (K 50) | ok (K 50) |

## Predictions (primary: calibrated arm, floor primary)

- **P1** (search-pause; decision 54's interval, observed = first `failed` catch): 16/16; per rate r10 4/4, r1 4/4, r0.2 4/4, r0.05 4/4; not evaluable 0; holds by branch: timeout interval 16; verdict **holds**.
- **P2** r10 (failed before the first `failed` catch <= 13.00): 4/4, counts [11, 11, 11, 11], verdict holds.
- **P2** r1 (failed before the first `failed` catch <= 4.00): 4/4, counts [2, 2, 2, 2], verdict holds.
- **P2** r0.2 (failed before the first `failed` catch <= 3.20): 4/4, counts [1, 1, 1, 1], verdict holds.
- **P2** r0.05 (failed before the first `failed` catch <= 3.05): 4/4, counts [1, 1, 1, 1], verdict holds.
- **P3** search-pause: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P3** cpu-throttle: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P3** net-delay: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P4** compares against the ledger E as the OR of its calibrated rules, its `failed` rule exempt from calibration (decisions 63, 70; V3_P4_LEDGER_READING = `calibrated-ledger`): a dropped ledger rule is listed below, not a reason for `—`. Two arms (decision 67): calibrated (primary) and optimistic bound (dropped rules armed at K = 100 / m = 5, beside, not evidence).
- Dropped ledger rules per rate (decision 70: listed; the ledger compares by its calibrated rules): r10 none; r1 none; r0.2 none; r0.05 none.
- **P4a** search-pause (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 0/4 (ledger missed, sensor caught: 0); r1 0/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 0); r0.05 0/4 (ledger missed, sensor caught: 0); highest rate **none in {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/4 (ledger missed, sensor caught: 0); r1 0/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 0); r0.05 0/4 (ledger missed, sensor caught: 0); highest rate none in {10, 1, 0.2, 0.05}.
- **P4a** cpu-throttle (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 1/4 (ledger missed, sensor caught: 1); r1 0/4 (ledger missed, sensor caught: 0); r0.2 1/4 (ledger missed, sensor caught: 3); r0.05 0/4 (ledger missed, sensor caught: 4); highest rate **none in {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 1/4 (ledger missed, sensor caught: 1); r1 0/4 (ledger missed, sensor caught: 0); r0.2 1/4 (ledger missed, sensor caught: 3); r0.05 0/4 (ledger missed, sensor caught: 4); highest rate none in {10, 1, 0.2, 0.05}.
- **P4a** net-delay (outside the target, without BC; wins under H3 a-c, >= 3 of 4): r10 0/4 (ledger missed, sensor caught: 0); r1 0/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 0); r0.05 1/4 (ledger missed, sensor caught: 0); highest rate **none in {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/4 (ledger missed, sensor caught: 0); r1 0/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 0); r0.05 1/4 (ledger missed, sensor caught: 0); highest rate none in {10, 1, 0.2, 0.05}.
- **P4b** search-pause (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 0/4 (ledger missed, sensor caught: 0); r1 0/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 0); r0.05 0/4 (ledger missed, sensor caught: 0); highest rate **none in {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/4 (ledger missed, sensor caught: 0); r1 0/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 0); r0.05 0/4 (ledger missed, sensor caught: 0); highest rate none in {10, 1, 0.2, 0.05}.
- **P4b** cpu-throttle (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 0/4 (ledger missed, sensor caught: 0); r1 0/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 2); r0.05 0/4 (ledger missed, sensor caught: 0); highest rate **none in {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/4 (ledger missed, sensor caught: 0); r1 0/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 2); r0.05 0/4 (ledger missed, sensor caught: 0); highest rate none in {10, 1, 0.2, 0.05}.
- **P4b** net-delay (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4): r10 0/4 (ledger missed, sensor caught: 0); r1 0/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 0); r0.05 0/4 (ledger missed, sensor caught: 0); highest rate **none in {10, 1, 0.2, 0.05}**.
  - optimistic bound (not evidence): r10 0/4 (ledger missed, sensor caught: 0); r1 0/4 (ledger missed, sensor caught: 0); r0.2 0/4 (ledger missed, sensor caught: 0); r0.05 0/4 (ledger missed, sensor caught: 0); highest rate none in {10, 1, 0.2, 0.05}.

### P4 per class and rate: placeable sensors, dropped rules and non-placeable sensors on the affected path

- search-pause r10: placeable sensors 266 (candidates with a catch: 4); dropped on the path: `metric:geo:sys_psi_cpu/spike`, `span:rate:memcached_get_multi_rate/spike`; not placeable on the path: `log:frontend:1c9632baa7b5`, `metric:frontend:sys_io`, `metric:frontend:sys_psi_io`, `metric:frontend:sys_psi_memory`, `metric:geo:sys_io`, `metric:geo:sys_psi_io`, `metric:geo:sys_psi_memory`, `metric:rate:sys_io`, `metric:rate:sys_psi_io`, `metric:rate:sys_psi_memory`, `metric:search:sys_io`, `metric:search:sys_psi_io`, `metric:search:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- search-pause r1: placeable sensors 266 (candidates with a catch: 3); dropped on the path: `metric:frontend:sys_psi_cpu/spike`, `metric:rate:sys_psi_cpu/spike`; not placeable on the path: `log:frontend:1c9632baa7b5`, `metric:frontend:sys_io`, `metric:frontend:sys_psi_io`, `metric:frontend:sys_psi_memory`, `metric:geo:sys_io`, `metric:geo:sys_psi_io`, `metric:geo:sys_psi_memory`, `metric:rate:sys_io`, `metric:rate:sys_psi_io`, `metric:rate:sys_psi_memory`, `metric:search:sys_io`, `metric:search:sys_psi_io`, `metric:search:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- search-pause r0.2: placeable sensors 265 (candidates with a catch: 3); dropped on the path: none; not placeable on the path: `log:frontend:1c9632baa7b5`, `metric:frontend:sys_io`, `metric:frontend:sys_psi_io`, `metric:frontend:sys_psi_memory`, `metric:geo:sys_io`, `metric:geo:sys_psi_io`, `metric:geo:sys_psi_memory`, `metric:rate:sys_io`, `metric:rate:sys_psi_io`, `metric:rate:sys_psi_memory`, `metric:search:sys_io`, `metric:search:sys_psi_io`, `metric:search:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- search-pause r0.05: placeable sensors 265 (candidates with a catch: 4); dropped on the path: `metric:frontend:cpu/spike`, `metric:search:cpu/spike`; not placeable on the path: `log:frontend:1c9632baa7b5`, `metric:frontend:sys_io`, `metric:frontend:sys_psi_io`, `metric:frontend:sys_psi_memory`, `metric:geo:sys_io`, `metric:geo:sys_psi_io`, `metric:geo:sys_psi_memory`, `metric:rate:sys_io`, `metric:rate:sys_psi_io`, `metric:rate:sys_psi_memory`, `metric:search:sys_io`, `metric:search:sys_psi_io`, `metric:search:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- cpu-throttle r10: placeable sensors 266 (candidates with a catch: 5); dropped on the path: `span:profile:memcached_get_profile/spike`; not placeable on the path: `log:frontend:1c9632baa7b5`, `metric:frontend:sys_io`, `metric:frontend:sys_psi_io`, `metric:frontend:sys_psi_memory`, `metric:profile:sys_io`, `metric:profile:sys_psi_io`, `metric:profile:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- cpu-throttle r1: placeable sensors 266 (candidates with a catch: 2); dropped on the path: `metric:frontend:sys_psi_cpu/spike`, `metric:profile:sys_psi_cpu/spike`; not placeable on the path: `log:frontend:1c9632baa7b5`, `metric:frontend:sys_io`, `metric:frontend:sys_psi_io`, `metric:frontend:sys_psi_memory`, `metric:profile:sys_io`, `metric:profile:sys_psi_io`, `metric:profile:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- cpu-throttle r0.2: placeable sensors 265 (candidates with a catch: 4); dropped on the path: none; not placeable on the path: `log:frontend:1c9632baa7b5`, `metric:frontend:sys_io`, `metric:frontend:sys_psi_io`, `metric:frontend:sys_psi_memory`, `metric:profile:sys_io`, `metric:profile:sys_psi_io`, `metric:profile:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- cpu-throttle r0.05: placeable sensors 265 (candidates with a catch: 10); dropped on the path: `metric:frontend:cpu/spike`; not placeable on the path: `log:frontend:1c9632baa7b5`, `metric:frontend:sys_io`, `metric:frontend:sys_psi_io`, `metric:frontend:sys_psi_memory`, `metric:profile:sys_io`, `metric:profile:sys_psi_io`, `metric:profile:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- net-delay r10: placeable sensors 266 (candidates with a catch: 10); dropped on the path: `span:rate:memcached_get_multi_rate/spike`; not placeable on the path: `log:frontend:1c9632baa7b5`, `metric:frontend:sys_io`, `metric:frontend:sys_psi_io`, `metric:frontend:sys_psi_memory`, `metric:rate:sys_io`, `metric:rate:sys_psi_io`, `metric:rate:sys_psi_memory`, `metric:search:sys_io`, `metric:search:sys_psi_io`, `metric:search:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- net-delay r1: placeable sensors 266 (candidates with a catch: 11); dropped on the path: `metric:frontend:sys_psi_cpu/spike`, `metric:rate:sys_psi_cpu/spike`; not placeable on the path: `log:frontend:1c9632baa7b5`, `metric:frontend:sys_io`, `metric:frontend:sys_psi_io`, `metric:frontend:sys_psi_memory`, `metric:rate:sys_io`, `metric:rate:sys_psi_io`, `metric:rate:sys_psi_memory`, `metric:search:sys_io`, `metric:search:sys_psi_io`, `metric:search:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- net-delay r0.2: placeable sensors 265 (candidates with a catch: 10); dropped on the path: none; not placeable on the path: `log:frontend:1c9632baa7b5`, `metric:frontend:sys_io`, `metric:frontend:sys_psi_io`, `metric:frontend:sys_psi_memory`, `metric:rate:sys_io`, `metric:rate:sys_psi_io`, `metric:rate:sys_psi_memory`, `metric:search:sys_io`, `metric:search:sys_psi_io`, `metric:search:sys_psi_memory`; dropped ledger rules (listed, decision 70): none
- net-delay r0.05: placeable sensors 265 (candidates with a catch: 15); dropped on the path: `metric:frontend:cpu/spike`, `metric:search:cpu/spike`; not placeable on the path: `log:frontend:1c9632baa7b5`, `metric:frontend:sys_io`, `metric:frontend:sys_psi_io`, `metric:frontend:sys_psi_memory`, `metric:rate:sys_io`, `metric:rate:sys_psi_io`, `metric:rate:sys_psi_memory`, `metric:search:sys_io`, `metric:search:sys_psi_io`, `metric:search:sys_psi_memory`; dropped ledger rules (listed, decision 70): none

### P4 folds (sensor rule vs ledger rule; lead, margin; category)

**Calibrated arm**

- P4a search-pause r10 (candidates 4; paired differences ledger - sensor: mean -0.917 [-0.918, -0.915] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:HTTP_GET_/hotels `spike` 1.170 vs E `absent` 0.255; lead -0.915, margin 0.00013; tied 2 (win share 0/2); **not faster**
  - ep2 b2: span:frontend:HTTP_GET_/hotels `spike` 1.201 vs E `absent` 0.285; lead -0.915, margin 8.1e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b3: span:frontend:HTTP_GET_/hotels `spike` 1.156 vs E `absent` 0.238; lead -0.918, margin 9.1e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b4: span:frontend:HTTP_GET_/hotels `spike` 1.134 vs E `absent` 0.216; lead -0.918, margin 9.7e-05; tied 2 (win share 0/2); **not faster**
- P4a search-pause r1 (candidates 3; paired differences ledger - sensor: mean -0.480 [-0.483, -0.478] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:HTTP_GET_/hotels `spike` 1.193 vs E `absent` 0.715; lead -0.478, margin 6.2e-05; tied 2 (win share 0/2); **not faster**
  - ep2 b2: span:frontend:HTTP_GET_/hotels `spike` 2.028 vs E `absent` 1.545; lead -0.483, margin 5.7e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b3: span:frontend:HTTP_GET_/hotels `spike` 1.548 vs E `absent` 1.070; lead -0.478, margin 6.9e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b4: span:frontend:HTTP_GET_/hotels `spike` 1.812 vs E `absent` 1.332; lead -0.479, margin 7.8e-05; tied 2 (win share 0/2); **not faster**
- P4a search-pause r0.2 (candidates 3; paired differences ledger - sensor: mean -0.000 [-0.000, -0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:HTTP_GET_/hotels `spike` 2.926 vs E `failed` 2.926; lead -0.000, margin 6.9e-05; tied 2 (win share 0/2); **not faster**
  - ep2 b2: span:frontend:HTTP_GET_/hotels `spike` 5.248 vs E `failed` 5.248; lead -0.000, margin 8.8e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b3: span:frontend:HTTP_GET_/hotels `spike` 6.005 vs E `failed` 6.005; lead -0.000, margin 9.2e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b4: span:frontend:HTTP_GET_/hotels `spike` 4.298 vs E `failed` 4.298; lead -0.000, margin 7.5e-05; tied 2 (win share 0/2); **not faster**
- P4a search-pause r0.05 (candidates 4; paired differences ledger - sensor: mean -0.000 [-0.000, -0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:HTTP_GET_/hotels `spike` 13.829 vs E `failed` 13.828; lead -0.000, margin 3.9e-05; tied 2 (win share 0/2); **not faster**
  - ep2 b2: span:frontend:HTTP_GET_/hotels `spike` 9.132 vs E `failed` 9.132; lead -0.000, margin 3.4e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b3: span:frontend:HTTP_GET_/hotels `spike` 2.588 vs E `failed` 2.587; lead -0.000, margin 3.9e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b4: span:frontend:HTTP_GET_/hotels `spike` 18.659 vs E `failed` 18.659; lead -0.000, margin 4.9e-05; tied 2 (win share 0/2); **not faster**
- P4a cpu-throttle r10 (candidates 5; paired differences ledger - sensor: mean 18.329 [0.000, 59.901] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:HTTP_GET_/hotels `spike` 16.891 vs E `spike` 30.305; lead 13.414, margin 8.9e-05; tied 1 (win share 1/1); **win**
  - ep2 b2: span:frontend:HTTP_GET_/hotels `spike` 7.911 vs E `spike` 7.912; lead 0.001, margin 9.4e-05; tied 1 (win share 0/1); **same request**
  - ep3 b3: span:frontend:HTTP_GET_/hotels `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b4: span:frontend:HTTP_GET_/hotels `spike` 0.151 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
- P4a cpu-throttle r1 (candidates 2; paired differences ledger - sensor: mean 0.000 [0.000, 0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b2: metric:reservation:cpu `—` — vs E `—` —; lead —, margin —; tied 2 (win share 0/2); **sensor missed**
  - ep3 b3: metric:reservation:cpu `—` — vs E `—` —; lead —, margin —; tied 2 (win share 0/2); **sensor missed**
  - ep4 b4: metric:reservation:cpu `—` — vs E `—` —; lead —, margin —; tied 2 (win share 0/2); **sensor missed**
- P4a cpu-throttle r0.2 (candidates 4; paired differences ledger - sensor: mean 45.546 [15.849, 59.838] s; availability-clock wins 1 of 1 evaluable):
  - ep1 b1: metric:frontend:cpu `median` 11.176 vs E `spike` 27.025; lead 15.849, margin 4e-05; tied 1 (win share 1/1); **win**
  - ep2 b2: metric:frontend:cpu `median` 6.918 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: metric:frontend:cpu `median` 6.689 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep4 b4: metric:frontend:cpu `spike` 0.214 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
- P4a cpu-throttle r0.05 (candidates 10; paired differences ledger - sensor: mean 45.203 [35.912, 49.980] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:frontend:sys_cpu `median` 12.902 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep2 b2: metric:frontend:sys_cpu `median` 10.071 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: metric:frontend:sys_cpu `median` 24.140 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep4 b4: metric:frontend:sys_cpu `median` 12.289 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
- P4a net-delay r10 (candidates 10; paired differences ledger - sensor: mean 0.003 [0.003, 0.004] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:search:/search.Search/Nearby `absent` 0.199 vs E `absent` 0.203; lead 0.003, margin 9.6e-05; tied 1 (win share 0/1); **same request** [lead = 0.0039 start + -0.00041 gap + 0]
  - ep2 b2: span:search:/search.Search/Nearby `absent` 0.185 vs E `absent` 0.188; lead 0.003, margin 7.8e-05; tied 1 (win share 0/1); **same request** [lead = 0.0031 start + -0.00041 gap + 0]
  - ep3 b3: span:search:/search.Search/Nearby `absent` 0.147 vs E `absent` 0.150; lead 0.004, margin 9.3e-05; tied 1 (win share 0/1); **same request** [lead = 0.0041 start + -0.00041 gap + 0]
  - ep4 b4: span:search:/search.Search/Nearby `absent` 0.140 vs E `absent` 0.143; lead 0.003, margin 0.00014; tied 1 (win share 0/1); **same request** [lead = 0.0039 start + -0.00041 gap + 0]
- P4a net-delay r1 (candidates 11; paired differences ledger - sensor: mean 0.271 [0.197, 0.298] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:reservation:memcached_reserve_get_multi_number `absent` 0.588 vs E `spike` 0.885; lead 0.298, margin 9.2e-05; tied 1 (win share 0/1); **same request**
  - ep2 b2: span:reservation:memcached_reserve_get_multi_number `absent` 0.087 vs E `spike` 0.380; lead 0.293, margin 8.1e-05; tied 1 (win share 0/1); **same request**
  - ep3 b3: span:reservation:memcached_reserve_get_multi_number `absent` 0.770 vs E `spike` 1.067; lead 0.297, margin 9.1e-05; tied 1 (win share 0/1); **same request**
  - ep4 b4: span:reservation:memcached_reserve_get_multi_number `absent` 0.199 vs E `spike` 0.397; lead 0.197, margin 9.6e-05; tied 1 (win share 0/1); **same request**
- P4a net-delay r0.2 (candidates 10; paired differences ledger - sensor: mean 0.275 [0.202, 0.301] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:search:/search.Search/Nearby `absent` 3.132 vs E `spike` 3.431; lead 0.299, margin 7e-05; tied 1 (win share 0/1); **same request**
  - ep2 b2: span:search:/search.Search/Nearby `absent` 4.774 vs E `spike` 5.073; lead 0.299, margin 8.4e-05; tied 1 (win share 0/1); **same request**
  - ep3 b3: span:search:/search.Search/Nearby `absent` 1.186 vs E `spike` 1.487; lead 0.301, margin 6.5e-05; tied 1 (win share 0/1); **same request**
  - ep4 b4: span:search:/search.Search/Nearby `absent` 0.414 vs E `spike` 0.616; lead 0.202, margin 6.6e-05; tied 1 (win share 0/1); **same request**
- P4a net-delay r0.05 (candidates 15; paired differences ledger - sensor: mean -3.432 [-9.668, 0.312] s; availability-clock wins 1 of 3 evaluable):
  - ep1 b1: metric:frontend:sys_cpu `median` 14.430 vs E `spike` 14.741; lead 0.312, margin 4.2e-05; tied 1 (win share 1/1); **win**
  - ep2 b2: metric:search:sys_cpu `median` 14.711 vs E `spike` 10.045; lead -4.666, margin 3.5e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b3: span:reservation:memcached_reserve_get_multi_number `absent` 19.311 vs E `spike` 19.607; lead 0.295, margin 3.2e-05; tied 1 (win share 0/1); **same request**
  - ep4 b4: metric:search:sys_cpu `median` 11.391 vs E `spike` 1.723; lead -9.668, margin 3.4e-05; tied 1 (win share 0/1); **not faster**
- P4b search-pause r10 (candidates 1; paired differences ledger - sensor: mean -19.566 [-19.617, -19.515] s; availability-clock wins 0 of 4 evaluable):
  - ep1 b1: metric:search:sys_psi_cpu `run3` 19.770 vs E `absent` 0.255; lead -19.515, margin 0.00013; tied 1 (win share 0/1); **not faster**
  - ep2 b2: metric:search:sys_psi_cpu `run3` 19.800 vs E `absent` 0.285; lead -19.515, margin 8.1e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b3: metric:search:sys_psi_cpu `run3` 19.855 vs E `absent` 0.238; lead -19.617, margin 9.1e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b4: metric:search:sys_psi_cpu `run3` 19.831 vs E `absent` 0.216; lead -19.615, margin 9.7e-05; tied 1 (win share 0/1); **not faster**
- P4b search-pause r1 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `absent` 0.715; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b2: — `—` — vs E `absent` 1.545; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b3: — `—` — vs E `absent` 1.070; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b4: — `—` — vs E `absent` 1.332; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b search-pause r0.2 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `failed` 2.926; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b2: — `—` — vs E `failed` 5.248; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b3: — `—` — vs E `failed` 6.005; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b4: — `—` — vs E `failed` 4.298; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b search-pause r0.05 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `failed` 13.828; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b2: — `—` — vs E `failed` 9.132; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b3: — `—` — vs E `failed` 2.587; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b4: — `—` — vs E `failed` 18.659; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b cpu-throttle r10 (candidates 1; paired differences ledger - sensor: mean 0.001 [0.000, 0.003] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:profile:/profile.Profile/GetProfiles `spike` 30.303 vs E `spike` 30.305; lead 0.002, margin 8.9e-05; tied 1 (win share 0/1); **same request**
  - ep2 b2: span:profile:/profile.Profile/GetProfiles `spike` 7.909 vs E `spike` 7.912; lead 0.003, margin 9.4e-05; tied 1 (win share 0/1); **same request**
  - ep3 b3: span:profile:/profile.Profile/GetProfiles `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b4: span:profile:/profile.Profile/GetProfiles `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4b cpu-throttle r1 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b2: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b3: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b4: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b cpu-throttle r0.2 (candidates 4; paired differences ledger - sensor: mean 18.367 [-33.027, 53.363] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:profile:cpu `—` — vs E `spike` 27.025; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b2: metric:profile:cpu `median` 6.918 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: metric:profile:cpu `median` 6.689 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep4 b4: metric:profile:cpu `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4b cpu-throttle r0.05 (candidates 2; paired differences ledger - sensor: mean 0.000 [0.000, 0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:profile:sys_cpu `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b2: metric:profile:sys_cpu `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b3: metric:profile:sys_cpu `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b4: metric:profile:cpu `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4b net-delay r10 (candidates 2; paired differences ledger - sensor: mean 0.007 [0.006, 0.008] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:rate:memcached_get_multi_rate `absent` 0.195 vs E `absent` 0.203; lead 0.007, margin 9.6e-05; tied 1 (win share 0/1); **same request** [lead = 0.0051 start + 0.0023 gap + 1.2e-07]
  - ep2 b2: span:rate:memcached_get_multi_rate `absent` 0.181 vs E `absent` 0.188; lead 0.006, margin 7.8e-05; tied 1 (win share 0/1); **same request** [lead = 0.0042 start + 0.0023 gap + -1.2e-07]
  - ep3 b3: span:rate:memcached_get_multi_rate `absent` 0.143 vs E `absent` 0.150; lead 0.008, margin 9.3e-05; tied 1 (win share 0/1); **same request** [lead = 0.0054 start + 0.0023 gap + 1.2e-07]
  - ep4 b4: span:rate:memcached_get_multi_rate `absent` 0.136 vs E `absent` 0.143; lead 0.008, margin 0.00014; tied 1 (win share 0/1); **same request** [lead = 0.0053 start + 0.0023 gap + -1.2e-07]
- P4b net-delay r1 (candidates 2; paired differences ledger - sensor: mean 0.107 [0.106, 0.109] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:rate:memcached_get_multi_rate `spike` 0.777 vs E `spike` 0.885; lead 0.109, margin 9.2e-05; tied 1 (win share 0/1); **same request**
  - ep2 b2: span:rate:memcached_get_multi_rate `spike` 0.274 vs E `spike` 0.380; lead 0.106, margin 8.1e-05; tied 1 (win share 0/1); **same request**
  - ep3 b3: span:rate:memcached_get_multi_rate `spike` 0.959 vs E `spike` 1.067; lead 0.108, margin 9.1e-05; tied 1 (win share 0/1); **same request**
  - ep4 b4: span:rate:memcached_get_multi_rate `spike` 0.289 vs E `spike` 0.397; lead 0.107, margin 9.6e-05; tied 1 (win share 0/1); **same request**
- P4b net-delay r0.2 (candidates 3; paired differences ledger - sensor: mean 0.276 [0.202, 0.301] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:rate:/rate.Rate/GetRates `absent` 3.132 vs E `spike` 3.431; lead 0.299, margin 7e-05; tied 1 (win share 0/1); **same request**
  - ep2 b2: span:rate:/rate.Rate/GetRates `absent` 4.773 vs E `spike` 5.073; lead 0.300, margin 8.4e-05; tied 1 (win share 0/1); **same request**
  - ep3 b3: span:rate:/rate.Rate/GetRates `absent` 1.186 vs E `spike` 1.487; lead 0.301, margin 6.5e-05; tied 1 (win share 0/1); **same request**
  - ep4 b4: span:rate:/rate.Rate/GetRates `absent` 0.413 vs E `spike` 0.616; lead 0.202, margin 6.6e-05; tied 1 (win share 0/1); **same request**
- P4b net-delay r0.05 (candidates 4; paired differences ledger - sensor: mean -12.424 [-50.022, 0.109] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:rate:memcached_get_multi_rate `spike` 14.633 vs E `spike` 14.741; lead 0.108, margin 4.2e-05; tied 1 (win share 0/1); **same request**
  - ep2 b2: metric:rate:sys_cpu `—` — vs E `spike` 10.045; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b3: span:rate:memcached_get_multi_rate `spike` 19.499 vs E `spike` 19.607; lead 0.108, margin 3.2e-05; tied 1 (win share 0/1); **same request**
  - ep4 b4: span:rate:memcached_get_multi_rate `spike` 1.614 vs E `spike` 1.723; lead 0.109, margin 3.4e-05; tied 1 (win share 0/1); **same request**

**Optimistic bound (not evidence)**

- P4a search-pause r10 (candidates 4; paired differences ledger - sensor: mean -0.917 [-0.918, -0.915] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:HTTP_GET_/hotels `spike` 1.170 vs E `absent` 0.255; lead -0.915, margin 0.00013; tied 2 (win share 0/2); **not faster**
  - ep2 b2: span:frontend:HTTP_GET_/hotels `spike` 1.201 vs E `absent` 0.285; lead -0.915, margin 8.1e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b3: span:frontend:HTTP_GET_/hotels `spike` 1.156 vs E `absent` 0.238; lead -0.918, margin 9.1e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b4: span:frontend:HTTP_GET_/hotels `spike` 1.134 vs E `absent` 0.216; lead -0.918, margin 9.7e-05; tied 2 (win share 0/2); **not faster**
- P4a search-pause r1 (candidates 3; paired differences ledger - sensor: mean -0.480 [-0.483, -0.478] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:HTTP_GET_/hotels `spike` 1.193 vs E `absent` 0.715; lead -0.478, margin 6.2e-05; tied 2 (win share 0/2); **not faster**
  - ep2 b2: span:frontend:HTTP_GET_/hotels `spike` 2.028 vs E `absent` 1.545; lead -0.483, margin 5.7e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b3: span:frontend:HTTP_GET_/hotels `spike` 1.548 vs E `absent` 1.070; lead -0.478, margin 6.9e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b4: span:frontend:HTTP_GET_/hotels `spike` 1.812 vs E `absent` 1.332; lead -0.479, margin 7.8e-05; tied 2 (win share 0/2); **not faster**
- P4a search-pause r0.2 (candidates 3; paired differences ledger - sensor: mean -0.000 [-0.000, -0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:HTTP_GET_/hotels `spike` 2.926 vs E `failed` 2.926; lead -0.000, margin 6.9e-05; tied 2 (win share 0/2); **not faster**
  - ep2 b2: span:frontend:HTTP_GET_/hotels `spike` 5.248 vs E `failed` 5.248; lead -0.000, margin 8.8e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b3: span:frontend:HTTP_GET_/hotels `spike` 6.005 vs E `failed` 6.005; lead -0.000, margin 9.2e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b4: span:frontend:HTTP_GET_/hotels `spike` 4.298 vs E `failed` 4.298; lead -0.000, margin 7.5e-05; tied 2 (win share 0/2); **not faster**
- P4a search-pause r0.05 (candidates 4; paired differences ledger - sensor: mean -0.000 [-0.000, -0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:HTTP_GET_/hotels `spike` 13.829 vs E `failed` 13.828; lead -0.000, margin 3.9e-05; tied 2 (win share 0/2); **not faster**
  - ep2 b2: span:frontend:HTTP_GET_/hotels `spike` 9.132 vs E `failed` 9.132; lead -0.000, margin 3.4e-05; tied 2 (win share 0/2); **not faster**
  - ep3 b3: span:frontend:HTTP_GET_/hotels `spike` 2.588 vs E `failed` 2.587; lead -0.000, margin 3.9e-05; tied 2 (win share 0/2); **not faster**
  - ep4 b4: span:frontend:HTTP_GET_/hotels `spike` 18.659 vs E `failed` 18.659; lead -0.000, margin 4.9e-05; tied 2 (win share 0/2); **not faster**
- P4a cpu-throttle r10 (candidates 5; paired differences ledger - sensor: mean 18.329 [0.000, 59.901] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:frontend:HTTP_GET_/hotels `spike` 16.891 vs E `spike` 30.305; lead 13.414, margin 8.9e-05; tied 1 (win share 1/1); **win**
  - ep2 b2: span:frontend:HTTP_GET_/hotels `spike` 7.911 vs E `spike` 7.912; lead 0.001, margin 9.4e-05; tied 1 (win share 0/1); **same request**
  - ep3 b3: span:frontend:HTTP_GET_/hotels `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b4: span:frontend:HTTP_GET_/hotels `spike` 0.151 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
- P4a cpu-throttle r1 (candidates 2; paired differences ledger - sensor: mean 0.000 [0.000, 0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b2: metric:reservation:cpu `—` — vs E `—` —; lead —, margin —; tied 2 (win share 0/2); **sensor missed**
  - ep3 b3: metric:reservation:cpu `—` — vs E `—` —; lead —, margin —; tied 2 (win share 0/2); **sensor missed**
  - ep4 b4: metric:reservation:cpu `—` — vs E `—` —; lead —, margin —; tied 2 (win share 0/2); **sensor missed**
- P4a cpu-throttle r0.2 (candidates 4; paired differences ledger - sensor: mean 45.546 [15.849, 59.838] s; availability-clock wins 1 of 1 evaluable):
  - ep1 b1: metric:frontend:cpu `median` 11.176 vs E `spike` 27.025; lead 15.849, margin 4e-05; tied 1 (win share 1/1); **win**
  - ep2 b2: metric:frontend:cpu `median` 6.918 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: metric:frontend:cpu `median` 6.689 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep4 b4: metric:frontend:cpu `spike` 0.214 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
- P4a cpu-throttle r0.05 (candidates 11; paired differences ledger - sensor: mean 45.203 [35.912, 49.980] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:frontend:sys_cpu `median` 12.902 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep2 b2: metric:frontend:sys_cpu `median` 10.071 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: metric:frontend:sys_cpu `median` 24.140 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep4 b4: metric:frontend:sys_cpu `median` 12.289 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
- P4a net-delay r10 (candidates 10; paired differences ledger - sensor: mean 0.003 [0.003, 0.004] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:search:/search.Search/Nearby `absent` 0.199 vs E `absent` 0.203; lead 0.003, margin 9.6e-05; tied 1 (win share 0/1); **same request** [lead = 0.0039 start + -0.00041 gap + 0]
  - ep2 b2: span:search:/search.Search/Nearby `absent` 0.185 vs E `absent` 0.188; lead 0.003, margin 7.8e-05; tied 1 (win share 0/1); **same request** [lead = 0.0031 start + -0.00041 gap + 0]
  - ep3 b3: span:search:/search.Search/Nearby `absent` 0.147 vs E `absent` 0.150; lead 0.004, margin 9.3e-05; tied 1 (win share 0/1); **same request** [lead = 0.0041 start + -0.00041 gap + 0]
  - ep4 b4: span:search:/search.Search/Nearby `absent` 0.140 vs E `absent` 0.143; lead 0.003, margin 0.00014; tied 1 (win share 0/1); **same request** [lead = 0.0039 start + -0.00041 gap + 0]
- P4a net-delay r1 (candidates 11; paired differences ledger - sensor: mean 0.271 [0.197, 0.298] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:reservation:memcached_reserve_get_multi_number `absent` 0.588 vs E `spike` 0.885; lead 0.298, margin 9.2e-05; tied 1 (win share 0/1); **same request**
  - ep2 b2: span:reservation:memcached_reserve_get_multi_number `absent` 0.087 vs E `spike` 0.380; lead 0.293, margin 8.1e-05; tied 1 (win share 0/1); **same request**
  - ep3 b3: span:reservation:memcached_reserve_get_multi_number `absent` 0.770 vs E `spike` 1.067; lead 0.297, margin 9.1e-05; tied 1 (win share 0/1); **same request**
  - ep4 b4: span:reservation:memcached_reserve_get_multi_number `absent` 0.199 vs E `spike` 0.397; lead 0.197, margin 9.6e-05; tied 1 (win share 0/1); **same request**
- P4a net-delay r0.2 (candidates 10; paired differences ledger - sensor: mean 0.275 [0.202, 0.301] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:search:/search.Search/Nearby `absent` 3.132 vs E `spike` 3.431; lead 0.299, margin 7e-05; tied 1 (win share 0/1); **same request**
  - ep2 b2: span:search:/search.Search/Nearby `absent` 4.774 vs E `spike` 5.073; lead 0.299, margin 8.4e-05; tied 1 (win share 0/1); **same request**
  - ep3 b3: span:search:/search.Search/Nearby `absent` 1.186 vs E `spike` 1.487; lead 0.301, margin 6.5e-05; tied 1 (win share 0/1); **same request**
  - ep4 b4: span:search:/search.Search/Nearby `absent` 0.414 vs E `spike` 0.616; lead 0.202, margin 6.6e-05; tied 1 (win share 0/1); **same request**
- P4a net-delay r0.05 (candidates 15; paired differences ledger - sensor: mean -3.432 [-9.668, 0.312] s; availability-clock wins 1 of 3 evaluable):
  - ep1 b1: metric:frontend:sys_cpu `median` 14.430 vs E `spike` 14.741; lead 0.312, margin 4.2e-05; tied 1 (win share 1/1); **win**
  - ep2 b2: metric:search:sys_cpu `median` 14.711 vs E `spike` 10.045; lead -4.666, margin 3.5e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b3: span:reservation:memcached_reserve_get_multi_number `absent` 19.311 vs E `spike` 19.607; lead 0.295, margin 3.2e-05; tied 1 (win share 0/1); **same request**
  - ep4 b4: metric:search:sys_cpu `median` 11.391 vs E `spike` 1.723; lead -9.668, margin 3.4e-05; tied 1 (win share 0/1); **not faster**
- P4b search-pause r10 (candidates 1; paired differences ledger - sensor: mean -19.566 [-19.617, -19.515] s; availability-clock wins 0 of 4 evaluable):
  - ep1 b1: metric:search:sys_psi_cpu `run3` 19.770 vs E `absent` 0.255; lead -19.515, margin 0.00013; tied 1 (win share 0/1); **not faster**
  - ep2 b2: metric:search:sys_psi_cpu `run3` 19.800 vs E `absent` 0.285; lead -19.515, margin 8.1e-05; tied 1 (win share 0/1); **not faster**
  - ep3 b3: metric:search:sys_psi_cpu `run3` 19.855 vs E `absent` 0.238; lead -19.617, margin 9.1e-05; tied 1 (win share 0/1); **not faster**
  - ep4 b4: metric:search:sys_psi_cpu `run3` 19.831 vs E `absent` 0.216; lead -19.615, margin 9.7e-05; tied 1 (win share 0/1); **not faster**
- P4b search-pause r1 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `absent` 0.715; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b2: — `—` — vs E `absent` 1.545; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b3: — `—` — vs E `absent` 1.070; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b4: — `—` — vs E `absent` 1.332; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b search-pause r0.2 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `failed` 2.926; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b2: — `—` — vs E `failed` 5.248; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b3: — `—` — vs E `failed` 6.005; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b4: — `—` — vs E `failed` 4.298; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b search-pause r0.05 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `failed` 13.828; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b2: — `—` — vs E `failed` 9.132; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b3: — `—` — vs E `failed` 2.587; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b4: — `—` — vs E `failed` 18.659; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b cpu-throttle r10 (candidates 2; paired differences ledger - sensor: mean -13.037 [-52.148, 0.002] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:profile:/profile.Profile/GetProfiles `spike` 30.303 vs E `spike` 30.305; lead 0.002, margin 8.9e-05; tied 1 (win share 0/1); **same request**
  - ep2 b2: span:profile:memcached_get_profile `—` — vs E `spike` 7.912; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b3: span:profile:/profile.Profile/GetProfiles `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b4: span:profile:/profile.Profile/GetProfiles `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4b cpu-throttle r1 (candidates 0; paired differences ledger - sensor: mean — [—, —] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep2 b2: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep3 b3: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
  - ep4 b4: — `—` — vs E `—` —; lead —, margin —; tied 0 (win share —); **sensor missed**
- P4b cpu-throttle r0.2 (candidates 4; paired differences ledger - sensor: mean 18.367 [-33.027, 53.363] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:profile:cpu `—` — vs E `spike` 27.025; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b2: metric:profile:cpu `median` 6.918 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep3 b3: metric:profile:cpu `median` 6.689 vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **ledger missed (counted apart)**
  - ep4 b4: metric:profile:cpu `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4b cpu-throttle r0.05 (candidates 2; paired differences ledger - sensor: mean 0.000 [0.000, 0.000] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: metric:profile:sys_cpu `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep2 b2: metric:profile:sys_cpu `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b3: metric:profile:sys_cpu `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep4 b4: metric:profile:cpu `—` — vs E `—` —; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
- P4b net-delay r10 (candidates 2; paired differences ledger - sensor: mean 0.007 [0.006, 0.008] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:rate:memcached_get_multi_rate `absent` 0.195 vs E `absent` 0.203; lead 0.007, margin 9.6e-05; tied 1 (win share 0/1); **same request** [lead = 0.0051 start + 0.0023 gap + 1.2e-07]
  - ep2 b2: span:rate:memcached_get_multi_rate `absent` 0.181 vs E `absent` 0.188; lead 0.006, margin 7.8e-05; tied 1 (win share 0/1); **same request** [lead = 0.0042 start + 0.0023 gap + -1.2e-07]
  - ep3 b3: span:rate:memcached_get_multi_rate `absent` 0.143 vs E `absent` 0.150; lead 0.008, margin 9.3e-05; tied 1 (win share 0/1); **same request** [lead = 0.0054 start + 0.0023 gap + 1.2e-07]
  - ep4 b4: span:rate:memcached_get_multi_rate `absent` 0.136 vs E `absent` 0.143; lead 0.008, margin 0.00014; tied 1 (win share 0/1); **same request** [lead = 0.0053 start + 0.0023 gap + -1.2e-07]
- P4b net-delay r1 (candidates 3; paired differences ledger - sensor: mean 0.107 [0.106, 0.109] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:rate:memcached_get_multi_rate `spike` 0.777 vs E `spike` 0.885; lead 0.109, margin 9.2e-05; tied 1 (win share 0/1); **same request**
  - ep2 b2: span:rate:memcached_get_multi_rate `spike` 0.274 vs E `spike` 0.380; lead 0.106, margin 8.1e-05; tied 1 (win share 0/1); **same request**
  - ep3 b3: span:rate:memcached_get_multi_rate `spike` 0.959 vs E `spike` 1.067; lead 0.108, margin 9.1e-05; tied 1 (win share 0/1); **same request**
  - ep4 b4: span:rate:memcached_get_multi_rate `spike` 0.289 vs E `spike` 0.397; lead 0.107, margin 9.6e-05; tied 1 (win share 0/1); **same request**
- P4b net-delay r0.2 (candidates 3; paired differences ledger - sensor: mean 0.276 [0.202, 0.301] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:rate:/rate.Rate/GetRates `absent` 3.132 vs E `spike` 3.431; lead 0.299, margin 7e-05; tied 1 (win share 0/1); **same request**
  - ep2 b2: span:rate:/rate.Rate/GetRates `absent` 4.773 vs E `spike` 5.073; lead 0.300, margin 8.4e-05; tied 1 (win share 0/1); **same request**
  - ep3 b3: span:rate:/rate.Rate/GetRates `absent` 1.186 vs E `spike` 1.487; lead 0.301, margin 6.5e-05; tied 1 (win share 0/1); **same request**
  - ep4 b4: span:rate:/rate.Rate/GetRates `absent` 0.413 vs E `spike` 0.616; lead 0.202, margin 6.6e-05; tied 1 (win share 0/1); **same request**
- P4b net-delay r0.05 (candidates 4; paired differences ledger - sensor: mean -12.424 [-50.022, 0.109] s; availability-clock wins 0 of 0 evaluable):
  - ep1 b1: span:rate:memcached_get_multi_rate `spike` 14.633 vs E `spike` 14.741; lead 0.108, margin 4.2e-05; tied 1 (win share 0/1); **same request**
  - ep2 b2: metric:rate:sys_cpu `—` — vs E `spike` 10.045; lead —, margin —; tied 1 (win share 0/1); **sensor missed**
  - ep3 b3: span:rate:memcached_get_multi_rate `spike` 19.499 vs E `spike` 19.607; lead 0.108, margin 3.2e-05; tied 1 (win share 0/1); **same request**
  - ep4 b4: span:rate:memcached_get_multi_rate `spike` 1.614 vs E `spike` 1.723; lead 0.109, margin 3.4e-05; tied 1 (win share 0/1); **same request**

**Per harness** (decision 49 pools the sweep's episode with campaign B's three; V3_HARNESS_TAG_RULE; tags sweep). Episodes per class and rate: cpu-throttle r0.05 sweep 4; cpu-throttle r0.2 sweep 4; cpu-throttle r1 sweep 4; cpu-throttle r10 sweep 4; net-delay r0.05 sweep 4; net-delay r0.2 sweep 4; net-delay r1 sweep 4; net-delay r10 sweep 4; search-pause r0.05 sweep 4; search-pause r0.2 sweep 4; search-pause r1 sweep 4; search-pause r10 sweep 4.

- P1 holds per harness: sweep 16/16; P2 within the bound per harness: r10 sweep 4/4; r1 sweep 4/4; r0.2 sweep 4/4; r0.05 sweep 4/4.
- P4 optimistic P4a cpu-throttle r0.05: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4a cpu-throttle r0.2: wins / folds by the held-out episode's harness: sweep 1/4
- P4 optimistic P4a cpu-throttle r1: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4a cpu-throttle r10: wins / folds by the held-out episode's harness: sweep 1/4
- P4 optimistic P4a net-delay r0.05: wins / folds by the held-out episode's harness: sweep 1/4
- P4 optimistic P4a net-delay r0.2: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4a net-delay r1: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4a net-delay r10: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4a search-pause r0.05: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4a search-pause r0.2: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4a search-pause r1: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4a search-pause r10: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4b cpu-throttle r0.05: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4b cpu-throttle r0.2: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4b cpu-throttle r1: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4b cpu-throttle r10: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4b net-delay r0.05: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4b net-delay r0.2: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4b net-delay r1: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4b net-delay r10: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4b search-pause r0.05: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4b search-pause r0.2: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4b search-pause r1: wins / folds by the held-out episode's harness: sweep 0/4
- P4 optimistic P4b search-pause r10: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4a cpu-throttle r0.05: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4a cpu-throttle r0.2: wins / folds by the held-out episode's harness: sweep 1/4
- P4 primary P4a cpu-throttle r1: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4a cpu-throttle r10: wins / folds by the held-out episode's harness: sweep 1/4
- P4 primary P4a net-delay r0.05: wins / folds by the held-out episode's harness: sweep 1/4
- P4 primary P4a net-delay r0.2: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4a net-delay r1: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4a net-delay r10: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4a search-pause r0.05: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4a search-pause r0.2: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4a search-pause r1: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4a search-pause r10: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4b cpu-throttle r0.05: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4b cpu-throttle r0.2: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4b cpu-throttle r1: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4b cpu-throttle r10: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4b net-delay r0.05: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4b net-delay r0.2: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4b net-delay r1: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4b net-delay r10: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4b search-pause r0.05: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4b search-pause r0.2: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4b search-pause r1: wins / folds by the held-out episode's harness: sweep 0/4
- P4 primary P4b search-pause r10: wins / folds by the held-out episode's harness: sweep 0/4

**Beside the primary** (highest rate where P4 holds):

| verdict | calibrated (primary) | floor arm | <= 1 held-out alarm | optimistic bound (not evidence) |
|---|---|---|---|---|
| P4a search-pause | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} |
| P4a cpu-throttle | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} |
| P4a net-delay | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} |
| P4b search-pause | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} |
| P4b cpu-throttle | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} |
| P4b net-delay | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} |
| P4a withBC search-pause | 0.2 | 0.2 | none in {10, 1, 0.2, 0.05} | 0.2 |
| P4a withBC cpu-throttle | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} |
| P4a withBC net-delay | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} |
| P4b withBC search-pause | 0.2 | 0.2 | none in {10, 1, 0.2, 0.05} | 0.2 |
| P4b withBC cpu-throttle | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} |
| P4b withBC net-delay | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} | none in {10, 1, 0.2, 0.05} |

## Out-of-sample check (decision 65, 67): calibrated detectors on --validation no-fault cells, no refit

Not computed (no --validation cells given; campaign B's no-fault cells are the declared source; at 0.15 h per rate they can certify at best 20.0/h).

## Primary outcome: time to detection at the calibrated values, misses charged at the hold end

Detected k/n · median [min-max] · **mean over all n** (with BC catches), then without BC. `—` = channel missing.

| class | rate | n | E | E no BC | L | L no BC | M | M no BC | S | S no BC | T | T no BC | L:own | L:own no BC | M:own | M:own no BC | S:own | S:own no BC | T:own | T:own no BC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| search-pause | 10 | 4 | 4/4 · 0.25 [0.22–0.29] · **0.25** | (= E) | 0/4 · **60.00** | 0/4 · **60.00** | 4/4 · 1.80 [1.73–1.83] · **1.79** | 0/4 · **60.00** | 4/4 · 4.82 [4.77–4.85] · **4.81** | 4/4 · 14.82 [14.77–14.85] · **14.81** | 4/4 · 0.24 [0.21–0.28] · **0.24** | 4/4 · 1.16 [1.13–1.20] · **1.17** | 0/4 · **60.00** | 0/4 · **60.00** | 4/4 · 14.08 [14.02–14.10] · **14.07** | 0/4 · **60.00** | 4/4 · 9.82 [9.77–9.85] · **9.81** | 4/4 · 19.82 [19.77–19.86] · **19.81** | 4/4 · 0.24 [0.21–0.28] · **0.24** | 0/4 · **60.00** |
| search-pause | 1 | 4 | 4/4 · 1.20 [0.72–1.54] · **1.17** | (= E) | 0/4 · **60.00** | 0/4 · **60.00** | 4/4 · 7.47 [7.15–7.90] · **7.50** | 0/4 · **60.00** | 4/4 · 4.37 [4.02–4.81] · **4.39** | 1/4 · 59.02 · **59.76** | 4/4 · 0.69 [0.21–1.04] · **0.66** | 4/4 · 1.68 [1.19–2.03] · **1.65** | 0/4 · **60.00** | 0/4 · **60.00** | 4/4 · 13.61 [13.29–14.03] · **13.64** | 0/4 · **60.00** | 4/4 · 9.37 [9.02–9.81] · **9.39** | 0/4 · **60.00** | 4/4 · 1.19 [0.70–1.54] · **1.15** | 0/4 · **60.00** |
| search-pause | 0.2 | 4 | 4/4 · 4.77 [2.93–6.00] · **4.62** | (= E) | 0/4 · **60.00** | 0/4 · **60.00** | 3/4 · 16.58 [9.26–20.39] · **26.56** | 3/4 · 16.58 [9.26–20.39] · **26.56** | 1/4 · 30.00 · **52.50** | 0/4 · **60.00** | 4/4 · 3.78 [1.93–5.01] · **3.63** | 4/4 · 4.77 [2.93–6.01] · **4.62** | 0/4 · **60.00** | 0/4 · **60.00** | 0/4 · **60.00** | 0/4 · **60.00** | 4/4 · 18.77 [16.91–20.00] · **18.61** | 0/4 · **60.00** | 4/4 · 3.78 [1.94–5.01] · **3.63** | 0/4 · **60.00** |
| search-pause | 0.05 | 4 | 4/4 · 11.48 [2.59–18.66] · **11.05** | (= E) | 0/4 · **60.00** | 0/4 · **60.00** | 0/4 · **60.00** | 0/4 · **60.00** | 2/4 · 10.37 [2.64–18.11] · **35.19** | 2/4 · 10.37 [2.64–18.11] · **35.19** | 4/4 · 10.51 [1.63–17.67] · **10.08** | 4/4 · 11.48 [2.59–18.66] · **11.05** | 0/4 · **60.00** | 0/4 · **60.00** | 4/4 · 12.55 [11.58–14.27] · **12.74** | 0/4 · **60.00** | 0/4 · **60.00** | 0/4 · **60.00** | 4/4 · 20.51 [11.63–27.67] · **20.08** | 0/4 · **60.00** |
| cpu-throttle | 10 | 4 | 2/4 · 19.11 [7.91–30.30] · **39.58** | (= E) | 0/4 · **60.05** | 0/4 · **60.05** | 0/4 · **60.05** | 0/4 · **60.05** | 2/4 · 17.25 [14.77–19.72] · **38.65** | 2/4 · 17.25 [14.77–19.72] · **38.65** | 3/4 · 0.28 [0.15–7.91] · **17.10** | 3/4 · 0.28 [0.15–7.91] · **17.10** | 0/4 · **60.05** | 0/4 · **60.05** | 0/4 · **60.05** | 0/4 · **60.05** | 4/4 · 4.76 [4.72–4.79] · **4.76** | 0/4 · **60.05** | 2/4 · 19.11 [7.91–30.30] · **39.58** | 2/4 · 19.11 [7.91–30.30] · **39.58** |
| cpu-throttle | 1 | 4 | 0/4 · **60.05** | (= E) | 0/4 · **60.05** | 0/4 · **60.05** | 1/4 · 7.28 · **46.86** | 1/4 · 7.28 · **46.86** | 0/4 · **60.05** | 0/4 · **60.05** | 0/4 · **60.05** | 0/4 · **60.05** | 0/4 · **60.05** | 0/4 · **60.05** | 0/4 · **60.05** | 0/4 · **60.05** | 2/4 · 14.59 [14.43–14.74] · **37.32** | 0/4 · **60.05** | 0/4 · **60.05** | 0/4 · **60.05** |
| cpu-throttle | 0.2 | 4 | 1/4 · 27.02 · **51.79** | (= E) | 0/4 · **60.05** | 0/4 · **60.05** | 4/4 · 6.80 [0.21–11.18] · **6.25** | 4/4 · 6.80 [0.21–11.18] · **6.25** | 2/4 · 11.98 [10.16–13.81] · **36.02** | 2/4 · 11.98 [10.16–13.81] · **36.02** | 1/4 · 27.02 · **51.79** | 1/4 · 27.02 · **51.79** | 0/4 · **60.05** | 0/4 · **60.05** | 2/4 · 6.80 [6.69–6.92] · **33.43** | 2/4 · 6.80 [6.69–6.92] · **33.43** | 4/4 · 2.74 [0.16–3.80] · **2.36** | 1/4 · 18.81 · **49.74** | 1/4 · 27.02 · **51.79** | 1/4 · 27.02 · **51.79** |
| cpu-throttle | 0.05 | 4 | 0/4 · **60.05** | (= E) | 0/4 · **60.05** | 0/4 · **60.05** | 3/4 · 13.28 [8.55–59.44] · **35.33** | 3/4 · 13.28 [8.55–59.44] · **35.33** | 4/4 · 12.60 [10.07–24.14] · **14.85** | 4/4 · 12.60 [10.07–24.14] · **14.85** | 1/4 · 52.93 · **58.27** | 1/4 · 52.93 · **58.27** | 0/4 · **60.05** | 0/4 · **60.05** | 1/4 · 13.28 · **48.36** | 1/4 · 13.28 · **48.36** | 4/4 · 2.60 [0.07–4.14] · **2.35** | 1/4 · 2.29 · **45.61** | 0/4 · **60.05** | 0/4 · **60.05** |
| net-delay | 10 | 4 | 4/4 · 0.17 [0.14–0.20] · **0.17** | (= E) | 0/4 · **60.06** | 0/4 · **60.06** | 0/4 · **60.06** | 0/4 · **60.06** | 0/4 · **60.06** | 0/4 · **60.06** | 4/4 · 0.17 [0.14–0.20] · **0.17** | 4/4 · 0.17 [0.14–0.20] · **0.17** | 0/4 · **60.06** | 0/4 · **60.06** | 0/4 · **60.06** | 0/4 · **60.06** | 0/4 · **60.06** | 0/4 · **60.06** | 4/4 · 0.16 [0.14–0.20] · **0.16** | 4/4 · 0.16 [0.14–0.20] · **0.16** |
| net-delay | 1 | 4 | 4/4 · 0.64 [0.38–1.07] · **0.68** | (= E) | 0/4 · **60.07** | 0/4 · **60.07** | 4/4 · 7.49 [7.17–7.87] · **7.50** | 4/4 · 7.49 [7.17–7.87] · **7.50** | 4/4 · 4.66 [4.18–19.07] · **8.14** | 4/4 · 4.66 [4.18–19.07] · **8.14** | 4/4 · 0.39 [0.09–0.77] · **0.41** | 4/4 · 0.39 [0.09–0.77] · **0.41** | 0/4 · **60.07** | 0/4 · **60.07** | 0/4 · **60.07** | 0/4 · **60.07** | 0/4 · **60.07** | 0/4 · **60.07** | 4/4 · 0.53 [0.27–0.96] · **0.57** | 4/4 · 0.53 [0.27–0.96] · **0.57** |
| net-delay | 0.2 | 4 | 4/4 · 2.46 [0.62–5.07] · **2.65** | (= E) | 0/4 · **60.06** | 0/4 · **60.06** | 4/4 · 6.98 [6.23–7.87] · **7.01** | 4/4 · 6.98 [6.23–7.87] · **7.01** | 4/4 · 12.14 [10.40–14.75] · **12.36** | 4/4 · 12.14 [10.40–14.75] · **12.36** | 4/4 · 2.16 [0.41–4.77] · **2.38** | 4/4 · 2.16 [0.41–4.77] · **2.38** | 0/4 · **60.06** | 0/4 · **60.06** | 1/4 · 10.93 · **47.78** | 1/4 · 10.93 · **47.78** | 0/4 · **60.06** | 0/4 · **60.06** | 4/4 · 2.16 [0.41–4.77] · **2.38** | 4/4 · 2.16 [0.41–4.77] · **2.38** |
| net-delay | 0.05 | 4 | 4/4 · 12.39 [1.72–19.61] · **11.53** | (= E) | 0/4 · **60.06** | 0/4 · **60.06** | 2/4 · 30.89 [7.04–54.74] · **45.48** | 2/4 · 30.89 [7.04–54.74] · **45.48** | 4/4 · 4.35 [1.39–14.71] · **6.20** | 4/4 · 4.35 [1.39–14.71] · **6.20** | 4/4 · 12.11 [1.44–19.31] · **11.24** | 4/4 · 12.11 [1.44–19.31] · **11.24** | 0/4 · **60.06** | 0/4 · **60.06** | 1/4 · 10.11 · **47.57** | 1/4 · 10.11 · **47.57** | 3/4 · 4.28 [1.39–4.43] · **17.54** | 3/4 · 4.28 [1.39–4.43] · **17.54** | 4/4 · 12.28 [1.61–19.50] · **11.42** | 4/4 · 12.28 [1.61–19.50] · **11.42** |

## P1 detail (H4, decision 54)

- r10 b1: interval 0.125 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.067, 1.166] +- 0.012 s; observed 1.170; holds via **timeout interval**
- r10 b2: interval 0.106 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [0.998, 1.198] +- 0.012 s; observed 1.201; holds via **timeout interval**
- r10 b3: interval 0.105 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.052, 1.152] +- 0.012 s; observed 1.155; holds via **timeout interval**
- r10 b4: interval 0.106 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.030, 1.130] +- 0.012 s; observed 1.134; holds via **timeout interval**
- r1 b1: interval 0.119 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.190, 1.190] +- 0.013 s; observed 1.193; holds via **timeout interval**
- r1 b2: interval 0.110 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.025, 2.025] +- 0.012 s; observed 2.028; holds via **timeout interval**
- r1 b3: interval 0.106 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.545, 1.545] +- 0.013 s; observed 1.548; holds via **timeout interval**
- r1 b4: interval 0.130 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [1.808, 1.808] +- 0.012 s; observed 1.812; holds via **timeout interval**
- r0.2 b1: interval 0.109 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [2.923, 2.923] +- 0.013 s; observed 2.926; holds via **timeout interval**
- r0.2 b2: interval 0.109 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [5.244, 5.244] +- 0.013 s; observed 5.248; holds via **timeout interval**
- r0.2 b3: interval 0.111 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [0.997, 6.001] +- 0.013 s; observed 6.005; holds via **timeout interval**
- r0.2 b4: interval 0.105 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [4.294, 4.294] +- 0.014 s; observed 4.298; holds via **timeout interval**
- r0.05 b1: interval 0.108 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [13.825, 13.825] +- 0.012 s; observed 13.828; holds via **timeout interval**
- r0.05 b2: interval 0.108 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [9.129, 9.129] +- 0.010 s; observed 9.132; holds via **timeout interval**
- r0.05 b3: interval 0.112 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [2.584, 2.584] +- 0.012 s; observed 2.587; holds via **timeout interval**
- r0.05 b4: interval 0.106 s (docker-events.jsonl `pause` of search (timeNano, wall -> monotonic by the cell's fit)); expected [18.657, 18.657] +- 0.009 s; observed 18.659; holds via **timeout interval**

- The ledger's calibrated `absent` against the client timeout: r10 hotel-search-v1: calibrated m 1.5 g 0.179 s vs timeout 1 s; `absent` before the first `failed` in 4/4 pause episodes; r1 hotel-search-v1: calibrated m 1.5 g 1.512 s vs timeout 1 s; `absent` before the first `failed` in 4/4 pause episodes; r0.2 hotel-search-v1: calibrated m 1.5 g 7.512 s vs timeout 1 s; `absent` before the first `failed` in 0/4 pause episodes; r0.05 hotel-search-v1: calibrated m 1.5 g 30.024 s vs timeout 1 s; `absent` before the first `failed` in 0/4 pause episodes.

## Exposure (H5): recorded, the objective unchanged

Route call path: frontend, geo, memcached-profile, memcached-rate, memcached-reserve, mongodb-geo, mongodb-profile, mongodb-rate, mongodb-reservation, profile, rate, reservation, search. Episodes with no request started in the fault window: 0 of 48. Never-exposed sensors: 114.

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
