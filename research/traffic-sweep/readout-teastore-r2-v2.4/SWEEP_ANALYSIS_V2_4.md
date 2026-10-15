# Traffic sweep, TeaStore: analysis v2.4, analysis frozen before any TeaStore cell was read (teastore-traffic-sweep-v1 + teastore-quiet-calibration-v1)

**Analysis frozen before any TeaStore cell was read.** v2.4 (decisions 57, 58 and 60) and this system's reader were written from the harness code that writes the cells (91c4967) and tested on synthetic cells only; no TeaStore cell was read before the freeze. **Scope: instance** (one SUT, one host; 2 campaign(s) pooled). `—` = absent or not evaluable, never 0; every output that is `—` by construction is listed under "Outputs that are — by construction".

Binding documents and inputs: research/traffic-sweep/DECLARATION_TEASTORE.md (c9f072b); research/traffic-sweep/AMENDMENT_TEASTORE_1.md (bbbd80b); research/traffic-sweep/AMENDMENT_TEASTORE_2.md (b840353); research/traffic-sweep/DECLARATION_QUIET_TEASTORE.md (fc64a6d); research/protocol/METHODOLOGY_HARDENING.md (H1-H11); research/PROTOCOL_DRAFT_20261002.md rounds 7-14 (decisions 26-60; decision 57 = d126589, round 13 = 6162c37, round 14 = c17f6a6); harness observability-placement-runtime-teastore-protocol 91c4967 (the cell writer and validator); research/protocol/parameters.json (decision 37).

Analysis: `research/detection-time/sweep_analysis_v2.py` v2.4 (sha256 `075c43e5870170c8b59cdbe1a970b56dc03920d67514027b9a95e5de38d962e9`), parameters.json sha256 `7447b492abf64f42ebaf547a640c84929ac15b59ebc1e495d5082f279373fc68`, on v1 `sweep_analysis.py` (sha256 `e4ad9ddf9239de4cda6d07e6570145333d02f894bd4bc6527c378a175d4f0760`) and `detection_time.py` (sha256 `2ca61dd7ac2a17cf82948cfd2b5ed632c9f74d360ea639ea39cfaf3e6a530c27`), HEAD `891a4c331b8f4d6233c6528be0324083707f0254`, Python 3.13.12. v1 verdicts: —. v2 verdicts: —. v2.1 verdicts: —. v2.2 verdicts: —. v2.3 verdicts: —.

## Outputs that are — by construction

- family M (primary and secondary columns, operating point, P4 candidates): docker-stats samples (resources.json) are written in no-fault cells only (the frozen no-fault-cost path, DECLARATION_TEASTORE.md Regimes): no fault episode has M, so it is not read (FAMILY_CHANNELS).
- availability-clock P4 verdict for family T: no measured collector receive stamp (AVAILABILITY_SOURCES, decision 43).
- P3 (every fault): no family is traffic-independent by mechanism (H11).
- Docker pause event as the onset interval's upper bound (H4): the cells keep no Docker events: the interval is [command issued, command returned].
- v1 / v2 / v2.1 comparisons: Hotel only (no earlier analysis of this system).
- P2 and P4 verdicts ('k of 4') at auth-freeze r0.05 (n = 1), auth-freeze r0.2 (n = 1), auth-freeze r1 (n = 1), auth-freeze r10 (n = 1), persistence-cpu-throttle r0.05 (n = 1), persistence-cpu-throttle r0.2 (n = 1), persistence-cpu-throttle r1 (n = 1), persistence-cpu-throttle r10 (n = 1): fewer episodes than declared (EPISODES); P4's single-episode comparison is reported where n = 1, descriptive.

## What was read

| class | r10 valid/found | r1 valid/found | r0.2 valid/found | r0.05 valid/found |
|---|---|---|---|---|
| no-fault-cost | 11/11 | 11/11 | 11/11 | 11/11 |
| auth-freeze | 1/1 | 1/1 | 1/1 | 1/1 |
| persistence-cpu-throttle | 1/1 | 1/1 | 1/1 | 1/1 |

Cells not scored: none.

Provenance: harness commit `0588a412ea7355f0aaa143b5468e8c4b9b7f0943, 91c4967f2d9c12a25eeeaf097f998856c377ca7f`; plan sha256 —; input digest `d48b7a47e09a6680781b69e4fda0e5bd7eebda3335c1c9b7a9be4eb0487fa594` over 424 files.

Harness provenance (registry HARNESS_PROVENANCE, F5): reader built from `91c4967`; sweep cells produced by 0588a41 (relaunch 2, AMENDMENT_TEASTORE_2.md b840353); quiet cells produced by 91c4967 (DECLARATION_QUIET_TEASTORE.md fc64a6d); files read: 0588a41..91c4967 changes modules/teastore/execution/candidate_quiet.py (new), study_epoch.py, candidate_runtime_adapter.py, study-epoch.json and extension-ledger.yaml only: none writes a file the reader reads; the cells' own commit: receipt.json source.frameworkCommit (printed per readout; a commit not in knownCommits is flagged).

Reader statistics over the valid cells (F11; a drop is counted, never silent): bridgeMappings 25745; bridgeTokensWithSeveralTraces 0; bridgeTracesWithSeveralTokens 0; bridgeRowsDropped 0; tracesWithoutToken 26023; probeTracesExcluded 179; probeSpansExcluded 2873; spansIncomplete 0; spansUnusable 0; duplicateSpans 5648; journeysWithoutStart 0; samplePairsSkipped 0; logRecordsUntimed 0; composeCliLines 0.

## Decision 57, 58 and 60: a sensor's `absent` and the requests that start and end its silence (P4, primary)

A sensor's `absent` carries the token of the observation that ends its silence (decision 57) and of the one that starts it (decision 58; own token, else the trace's entry-root token). A pair with the ledger's catch is same-request when the ending observation is the ledger's catching request (57) or, for an `absent`-vs-`absent` pair, when the silence-starting records are one request (58); with a token missing it is unclassifiable (no win). An `absent`-vs-`absent` pair of different requests wins only if its start term exceeds the margin; the gap term never counts (60). Folds whose selected sensor caught by `absent`: 0; same-request by the ending observation (57): 0; `absent`-vs-`absent` pairs: 0, same-request by the starting records (58): 0 (of them by the start only: 0); start term within the margin (60): 0; **unclassifiable pairs: 0** (decisive for the category: 0).

## Clocks and timing uncertainty (H3 b, H8)

- Clock alignment, per cell wall = monotonic + offset over the ledger's paired stamps: residual median 2.5e-06 s, max 4.3e-05 s over 52 cells.
- Log receipt-delay bound per cell (max Docker stamp - app second): median 0.976 s, range 0.753-1.000 s over 52 cells; services with no app stamp: rabbitmq.
- Availability (H8, decision 43): log lines carry a Docker receive stamp in 52 of 52 valid cells; availability per family (decision 43, measured receive stamps only): E: the client's own end stamp (fixed_load writes the ledger), L: Docker daemon receive stamp (docker compose logs --timestamps), M: —, S: cgroup sampler stamp `monotonic` (taken after the read), mapped through the producer barrier, T: —. Span event keys read: `args`, `collector_timestamp`, `correlation_errors`, `correlation_warnings`, `duration_s`, `eoi`, `ess`, `full_signature`, `hostname`, `kieker_trace_id`, `message_sha1`, `native_identity_message_bodies`, `native_identity_occurrences`, `native_record_class`, `operation`, `parent_resolution`, `parent_span_id`, `runtime_host_service`, `service`, `service_attribution_errors`, `service_attribution_status`, `session_id`, `signature_ordinal`, `signature_package`, `signature_service`, `signature_sha1`, `source`, `span_id`, `status_code`, `timestamp`, `tin`, `tout`, `trace_id`.
- The ledger's `absent` gap against the client timeout, per rate (it fires before a timeout only where the gap is shorter): r10 login-only-v1: gap 0.658 s < timeout 15 s (can fire before a timeout); `absent` before the first `failed` in 1/1 pause episodes; r1 login-only-v1: gap 2.156 s < timeout 15 s (can fire before a timeout); `absent` before the first `failed` in 1/1 pause episodes; r0.2 login-only-v1: gap 10.077 s < timeout 15 s (can fire before a timeout); `absent` before the first `failed` in 1/1 pause episodes; r0.05 login-only-v1: gap 40.097 s >= timeout 15 s (cannot fire before a timeout); `absent` before the first `failed` in 0/1 pause episodes.

## Scale not estimable (M2, decision 52): fault-free MAD = 0 at the baseline

These sensors' level rules (spike, run3, median) are `—`: no catch, no false alarm; `appear` and `absent` are kept. Pooled per rate (the scoring baseline):

- r0.05: 20 of 69 sensors with >= 20 points: `metric:auth:sys_psi_io` (median 0, n 412), `metric:auth:sys_psi_memory` (median 0, n 412), `metric:db:sys_io` (median 0, n 412), `metric:db:sys_psi_cpu` (median 0, n 412), `metric:db:sys_psi_io` (median 0, n 412), `metric:db:sys_psi_memory` (median 0, n 412), `metric:image:sys_io` (median 0, n 412), `metric:image:sys_psi_io` (median 0, n 412), `metric:image:sys_psi_memory` (median 0, n 412), `metric:persistence:sys_psi_io` (median 0, n 412), `metric:persistence:sys_psi_memory` (median 0, n 412), `metric:rabbitmq:sys_io` (median 0, n 412), `metric:rabbitmq:sys_psi_io` (median 0, n 412), `metric:rabbitmq:sys_psi_memory` (median 0, n 412), `metric:recommender:sys_psi_io` (median 0, n 412), `metric:recommender:sys_psi_memory` (median 0, n 412), `metric:registry:sys_psi_io` (median 0, n 412), `metric:registry:sys_psi_memory` (median 0, n 412), `metric:webui:sys_psi_io` (median 0, n 412), `metric:webui:sys_psi_memory` (median 0, n 412)
- r0.2: 20 of 69 sensors with >= 20 points: `metric:auth:sys_psi_io` (median 0, n 409), `metric:auth:sys_psi_memory` (median 0, n 409), `metric:db:sys_io` (median 0, n 409), `metric:db:sys_psi_cpu` (median 0, n 409), `metric:db:sys_psi_io` (median 0, n 409), `metric:db:sys_psi_memory` (median 0, n 409), `metric:image:sys_io` (median 0, n 409), `metric:image:sys_psi_io` (median 0, n 409), `metric:image:sys_psi_memory` (median 0, n 409), `metric:persistence:sys_psi_io` (median 0, n 409), `metric:persistence:sys_psi_memory` (median 0, n 409), `metric:rabbitmq:sys_io` (median 0, n 409), `metric:rabbitmq:sys_psi_io` (median 0, n 409), `metric:rabbitmq:sys_psi_memory` (median 0, n 409), `metric:recommender:sys_psi_io` (median 0, n 409), `metric:recommender:sys_psi_memory` (median 0, n 409), `metric:registry:sys_psi_io` (median 0, n 409), `metric:registry:sys_psi_memory` (median 0, n 409), `metric:webui:sys_psi_io` (median 0, n 409), `metric:webui:sys_psi_memory` (median 0, n 409)
- r1: 20 of 69 sensors with >= 20 points: `metric:auth:sys_psi_io` (median 0, n 409), `metric:auth:sys_psi_memory` (median 0, n 409), `metric:db:sys_io` (median 0, n 409), `metric:db:sys_psi_cpu` (median 0, n 409), `metric:db:sys_psi_io` (median 0, n 409), `metric:db:sys_psi_memory` (median 0, n 409), `metric:image:sys_io` (median 0, n 409), `metric:image:sys_psi_io` (median 0, n 409), `metric:image:sys_psi_memory` (median 0, n 409), `metric:persistence:sys_psi_io` (median 0, n 409), `metric:persistence:sys_psi_memory` (median 0, n 409), `metric:rabbitmq:sys_io` (median 0, n 409), `metric:rabbitmq:sys_psi_io` (median 0, n 409), `metric:rabbitmq:sys_psi_memory` (median 0, n 409), `metric:recommender:sys_psi_io` (median 0, n 409), `metric:recommender:sys_psi_memory` (median 0, n 409), `metric:registry:sys_psi_io` (median 0, n 409), `metric:registry:sys_psi_memory` (median 0, n 409), `metric:webui:sys_psi_io` (median 0, n 409), `metric:webui:sys_psi_memory` (median 0, n 409)
- r10: 20 of 69 sensors with >= 20 points: `metric:auth:sys_psi_io` (median 0, n 409), `metric:auth:sys_psi_memory` (median 0, n 409), `metric:db:sys_io` (median 0, n 409), `metric:db:sys_psi_cpu` (median 0, n 409), `metric:db:sys_psi_io` (median 0, n 409), `metric:db:sys_psi_memory` (median 0, n 409), `metric:image:sys_io` (median 0, n 409), `metric:image:sys_psi_io` (median 0, n 409), `metric:image:sys_psi_memory` (median 0, n 409), `metric:persistence:sys_psi_io` (median 0, n 409), `metric:persistence:sys_psi_memory` (median 0, n 409), `metric:rabbitmq:sys_io` (median 0, n 409), `metric:rabbitmq:sys_psi_io` (median 0, n 409), `metric:rabbitmq:sys_psi_memory` (median 0, n 409), `metric:recommender:sys_psi_io` (median 0, n 409), `metric:recommender:sys_psi_memory` (median 0, n 409), `metric:registry:sys_psi_io` (median 0, n 409), `metric:registry:sys_psi_memory` (median 0, n 409), `metric:webui:sys_psi_io` (median 0, n 409), `metric:webui:sys_psi_memory` (median 0, n 409)
- In a leave-one-cell-out fit only (the operating point), additionally: none.
- Resolution of ledger latency: a float-difference granularity of (end - start), not an instrument resolution (RESOLUTION_RULE; never binding).

## Operating point (H2, H7; M3, M4): held-out false alarms per hour on the scored sensor set

Target 15/h, met when the exact one-sided 0.95 upper bound is <= the target (`FAR_MEETS_CRITERION` = upper). The scored set of a class is the detector its episodes are scored with: the spike path filter and the by-construction flags (no-BC view, as P4) applied exactly as in scoring, the detector restarted after each counted alarm (CALIBRATION_SET_RULE, decision 55). K per channel family within the system (`K_FIT_UNIT` = family, decision 53): one K per family, the smallest grid K that meets the target at every (class, rate) where some grid K does; the per-system K (L, M, S, T together) is the `system` row. Quiet time per rate: the valid no-fault cells, each scored leave-one-cell-out. Cell: min K (cert / point) · alarms at the fitted K · /h [bound] · at K = 4.

**Floor primary (share 0.1 of the baseline median)**: K per family E 12.5, L 2.5, M —, S —, T —; per-system K —.

| class | family | r10 | r1 | r0.2 | r0.05 |
|---|---|---|---|---|---|
| auth-freeze | E | 12.5 / 10 · 2 · 3.64 [11.45] · 32 (58.2/h) | 6.3 / 3 · 0 · 0.00 [5.45] · 4 (7.3/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) |
| auth-freeze | L | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) |
| auth-freeze | M | — (not collected) | — (not collected) | — (not collected) | — (not collected) |
| auth-freeze | S | — / — · — · — [—] · 211 (383.6/h) | — / — · — · — [—] · 180 (327.3/h) | — / — · — · — [—] · 267 (485.5/h) | — / — · — · — [—] · 225 (409.1/h) |
| auth-freeze | T | — / — · — · — [—] · 25843 (46987.3/h) | — / — · — · — [—] · 2762 (5021.8/h) | — / 100 · — · — [—] · 665 (1209.1/h) | — / 63 · — · — [—] · 161 (292.7/h) |
| auth-freeze | system | — / — · — · — [—] · 26041 (47347.3/h) | — / — · — · — [—] · 2939 (5343.6/h) | — / — · — · — [—] · 926 (1683.6/h) | — / — · — · — [—] · 382 (694.5/h) |
| persistence-cpu-throttle | E | 12.5 / 10 · 2 · 3.64 [11.45] · 32 (58.2/h) | 6.3 / 3 · 0 · 0.00 [5.45] · 4 (7.3/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) |
| persistence-cpu-throttle | L | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) |
| persistence-cpu-throttle | M | — (not collected) | — (not collected) | — (not collected) | — (not collected) |
| persistence-cpu-throttle | S | — / — · — · — [—] · 208 (378.2/h) | — / — · — · — [—] · 178 (323.6/h) | — / — · — · — [—] · 267 (485.5/h) | — / — · — · — [—] · 222 (403.6/h) |
| persistence-cpu-throttle | T | — / — · — · — [—] · 25843 (46987.3/h) | — / — · — · — [—] · 2762 (5021.8/h) | — / 100 · — · — [—] · 665 (1209.1/h) | — / 63 · — · — [—] · 161 (292.7/h) |
| persistence-cpu-throttle | system | — / — · — · — [—] · 26038 (47341.8/h) | — / — · — · — [—] · 2937 (5340.0/h) | — / — · — · — [—] · 926 (1683.6/h) | — / — · — · — [—] · 379 (689.1/h) |

*All sensors of the family, no class filter (v2's calibration set; not used for K in v2.1)*, beside it (counted as v2 did; M2 applies): K E 12.5, L 2.5, M —, S —, T —; per-system K —.

| family (all sensors) | r10 | r1 | r0.2 | r0.05 |
|---|---|---|---|---|
| E | 12.5 / 10 · 2 · 3.64 [11.45] · 32 (58.2/h) | 6.3 / 3 · 0 · 0.00 [5.45] · 4 (7.3/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) |
| L | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) |
| M | — (not collected) | — (not collected) | — (not collected) | — (not collected) |
| S | — / — · — · — [—] · 298 (541.8/h) | — / — · — · — [—] · 264 (480.0/h) | — / — · — · — [—] · 318 (578.2/h) | — / — · — · — [—] · 288 (523.6/h) |
| T | — / — · — · — [—] · 27212 (49476.4/h) | — / — · — · — [—] · 2954 (5370.9/h) | — / 100 · — · — [—] · 742 (1349.1/h) | — / 63 · — · — [—] · 190 (345.5/h) |
| system | — / — · — · — [—] · 27510 (50018.2/h) | — / — · — · — [—] · 3218 (5850.9/h) | — / — · — · — [—] · 1060 (1927.3/h) | — / — · — · — [—] · 478 (869.1/h) |

Alarms left at the largest grid K (K = 100) on the scored set, by sensor and rule:

- auth-freeze S r10: `metric:webui:sys_io/spike` 83, `metric:auth:sys_io/spike` 62, `metric:persistence:sys_io/spike` 46, `metric:recommender:sys_io/median` 6, `metric:recommender:sys_io/run3` 6
- auth-freeze S r1: `metric:webui:sys_io/spike` 65, `metric:auth:sys_io/spike` 61, `metric:persistence:sys_io/spike` 26
- auth-freeze S r0.2: `metric:auth:sys_io/spike` 105, `metric:webui:sys_io/spike` 69, `metric:persistence:sys_io/spike` 63, `metric:recommender:sys_io/median` 4, `metric:recommender:sys_io/run3` 3
- auth-freeze S r0.05: `metric:auth:sys_io/spike` 76, `metric:webui:sys_io/spike` 73, `metric:persistence:sys_io/spike` 33
- auth-freeze T r10: `span:persistence:PersistenceCategory.getId/spike` 158, `span:auth:RandomSessionIdGenerator.getSessionId/spike` 8, `span:auth:ShaSecurityProvider.getSha512/spike` 3, `span:auth:ShaSecurityProvider.getKeyProvider/spike` 2, `span:persistence:PersistenceUser.getId/spike` 2, `span:auth:ShaSecurityProvider.blobToString/spike` 1 (+1 more)
- auth-freeze T r1: `span:persistence:PersistenceCategory.getId/spike` 8, `span:auth:RandomSessionIdGenerator.getSessionId/spike` 1
- auth-freeze T r0.2: `span:persistence:PersistenceCategory.getId/spike` 4, `span:auth:ShaSecurityProvider.getKeyProvider/spike` 1
- auth-freeze T r0.05: `span:persistence:PersistenceCategory.getId/spike` 4
- persistence-cpu-throttle S r10: `metric:webui:sys_io/spike` 83, `metric:auth:sys_io/spike` 62, `metric:persistence:sys_io/spike` 46, `metric:recommender:sys_io/median` 6, `metric:recommender:sys_io/run3` 6
- persistence-cpu-throttle S r1: `metric:webui:sys_io/spike` 65, `metric:auth:sys_io/spike` 61, `metric:persistence:sys_io/spike` 26
- persistence-cpu-throttle S r0.2: `metric:auth:sys_io/spike` 105, `metric:webui:sys_io/spike` 69, `metric:persistence:sys_io/spike` 63, `metric:recommender:sys_io/median` 4, `metric:recommender:sys_io/run3` 3
- persistence-cpu-throttle S r0.05: `metric:auth:sys_io/spike` 76, `metric:webui:sys_io/spike` 73, `metric:persistence:sys_io/spike` 33
- persistence-cpu-throttle T r10: `span:persistence:PersistenceCategory.getId/spike` 158, `span:auth:RandomSessionIdGenerator.getSessionId/spike` 8, `span:auth:ShaSecurityProvider.getSha512/spike` 3, `span:auth:ShaSecurityProvider.getKeyProvider/spike` 2, `span:persistence:PersistenceUser.getId/spike` 2, `span:auth:ShaSecurityProvider.blobToString/spike` 1 (+1 more)
- persistence-cpu-throttle T r1: `span:persistence:PersistenceCategory.getId/spike` 8, `span:auth:RandomSessionIdGenerator.getSessionId/spike` 1
- persistence-cpu-throttle T r0.2: `span:persistence:PersistenceCategory.getId/spike` 4, `span:auth:ShaSecurityProvider.getKeyProvider/spike` 1
- persistence-cpu-throttle T r0.05: `span:persistence:PersistenceCategory.getId/spike` 4

**Floor arm (share 0.05 of the baseline median)**: K per family E 12.5, L 2.5, M —, S —, T —; per-system K —.

| class | family | r10 | r1 | r0.2 | r0.05 |
|---|---|---|---|---|---|
| auth-freeze | E | 12.5 / 10 · 2 · 3.64 [11.45] · 32 (58.2/h) | 6.3 / 3 · 0 · 0.00 [5.45] · 4 (7.3/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) |
| auth-freeze | L | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) |
| auth-freeze | M | — (not collected) | — (not collected) | — (not collected) | — (not collected) |
| auth-freeze | S | — / — · — · — [—] · 211 (383.6/h) | — / — · — · — [—] · 180 (327.3/h) | — / — · — · — [—] · 267 (485.5/h) | — / — · — · — [—] · 225 (409.1/h) |
| auth-freeze | T | — / — · — · — [—] · 25843 (46987.3/h) | — / — · — · — [—] · 2762 (5021.8/h) | — / 100 · — · — [—] · 665 (1209.1/h) | — / 63 · — · — [—] · 161 (292.7/h) |
| auth-freeze | system | — / — · — · — [—] · 26041 (47347.3/h) | — / — · — · — [—] · 2939 (5343.6/h) | — / — · — · — [—] · 926 (1683.6/h) | — / — · — · — [—] · 382 (694.5/h) |
| persistence-cpu-throttle | E | 12.5 / 10 · 2 · 3.64 [11.45] · 32 (58.2/h) | 6.3 / 3 · 0 · 0.00 [5.45] · 4 (7.3/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) |
| persistence-cpu-throttle | L | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) |
| persistence-cpu-throttle | M | — (not collected) | — (not collected) | — (not collected) | — (not collected) |
| persistence-cpu-throttle | S | — / — · — · — [—] · 208 (378.2/h) | — / — · — · — [—] · 178 (323.6/h) | — / — · — · — [—] · 267 (485.5/h) | — / — · — · — [—] · 222 (403.6/h) |
| persistence-cpu-throttle | T | — / — · — · — [—] · 25843 (46987.3/h) | — / — · — · — [—] · 2762 (5021.8/h) | — / 100 · — · — [—] · 665 (1209.1/h) | — / 63 · — · — [—] · 161 (292.7/h) |
| persistence-cpu-throttle | system | — / — · — · — [—] · 26038 (47341.8/h) | — / — · — · — [—] · 2937 (5340.0/h) | — / — · — · — [—] · 926 (1683.6/h) | — / — · — · — [—] · 379 (689.1/h) |

*All sensors of the family, no class filter (v2's calibration set; not used for K in v2.1)*, beside it (counted as v2 did; M2 applies): K E 12.5, L 2.5, M —, S —, T —; per-system K —.

| family (all sensors) | r10 | r1 | r0.2 | r0.05 |
|---|---|---|---|---|
| E | 12.5 / 10 · 2 · 3.64 [11.45] · 32 (58.2/h) | 6.3 / 3 · 0 · 0.00 [5.45] · 4 (7.3/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) |
| L | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) | 2.5 / 2.5 · 0 · 0.00 [5.45] · 0 (0.0/h) |
| M | — (not collected) | — (not collected) | — (not collected) | — (not collected) |
| S | — / — · — · — [—] · 298 (541.8/h) | — / — · — · — [—] · 264 (480.0/h) | — / — · — · — [—] · 318 (578.2/h) | — / — · — · — [—] · 289 (525.5/h) |
| T | — / — · — · — [—] · 27212 (49476.4/h) | — / — · — · — [—] · 2954 (5370.9/h) | — / 100 · — · — [—] · 742 (1349.1/h) | — / 63 · — · — [—] · 190 (345.5/h) |
| system | — / — · — · — [—] · 27510 (50018.2/h) | — / — · — · — [—] · 3218 (5850.9/h) | — / — · — · — [—] · 1060 (1927.3/h) | — / — · — · — [—] · 479 (870.9/h) |

Alarms left at the largest grid K (K = 100) on the scored set, by sensor and rule:

- auth-freeze S r10: `metric:webui:sys_io/spike` 83, `metric:auth:sys_io/spike` 62, `metric:persistence:sys_io/spike` 46, `metric:recommender:sys_io/median` 6, `metric:recommender:sys_io/run3` 6
- auth-freeze S r1: `metric:webui:sys_io/spike` 65, `metric:auth:sys_io/spike` 61, `metric:persistence:sys_io/spike` 26
- auth-freeze S r0.2: `metric:auth:sys_io/spike` 105, `metric:webui:sys_io/spike` 69, `metric:persistence:sys_io/spike` 63, `metric:recommender:sys_io/median` 4, `metric:recommender:sys_io/run3` 3
- auth-freeze S r0.05: `metric:auth:sys_io/spike` 76, `metric:webui:sys_io/spike` 73, `metric:persistence:sys_io/spike` 33
- auth-freeze T r10: `span:persistence:PersistenceCategory.getId/spike` 158, `span:auth:RandomSessionIdGenerator.getSessionId/spike` 8, `span:auth:ShaSecurityProvider.getSha512/spike` 3, `span:auth:ShaSecurityProvider.getKeyProvider/spike` 2, `span:persistence:PersistenceUser.getId/spike` 2, `span:auth:ShaSecurityProvider.blobToString/spike` 1 (+1 more)
- auth-freeze T r1: `span:persistence:PersistenceCategory.getId/spike` 8, `span:auth:RandomSessionIdGenerator.getSessionId/spike` 1
- auth-freeze T r0.2: `span:persistence:PersistenceCategory.getId/spike` 4, `span:auth:ShaSecurityProvider.getKeyProvider/spike` 1
- auth-freeze T r0.05: `span:persistence:PersistenceCategory.getId/spike` 4
- persistence-cpu-throttle S r10: `metric:webui:sys_io/spike` 83, `metric:auth:sys_io/spike` 62, `metric:persistence:sys_io/spike` 46, `metric:recommender:sys_io/median` 6, `metric:recommender:sys_io/run3` 6
- persistence-cpu-throttle S r1: `metric:webui:sys_io/spike` 65, `metric:auth:sys_io/spike` 61, `metric:persistence:sys_io/spike` 26
- persistence-cpu-throttle S r0.2: `metric:auth:sys_io/spike` 105, `metric:webui:sys_io/spike` 69, `metric:persistence:sys_io/spike` 63, `metric:recommender:sys_io/median` 4, `metric:recommender:sys_io/run3` 3
- persistence-cpu-throttle S r0.05: `metric:auth:sys_io/spike` 76, `metric:webui:sys_io/spike` 73, `metric:persistence:sys_io/spike` 33
- persistence-cpu-throttle T r10: `span:persistence:PersistenceCategory.getId/spike` 158, `span:auth:RandomSessionIdGenerator.getSessionId/spike` 8, `span:auth:ShaSecurityProvider.getSha512/spike` 3, `span:auth:ShaSecurityProvider.getKeyProvider/spike` 2, `span:persistence:PersistenceUser.getId/spike` 2, `span:auth:ShaSecurityProvider.blobToString/spike` 1 (+1 more)
- persistence-cpu-throttle T r1: `span:persistence:PersistenceCategory.getId/spike` 8, `span:auth:RandomSessionIdGenerator.getSessionId/spike` 1
- persistence-cpu-throttle T r0.2: `span:persistence:PersistenceCategory.getId/spike` 4, `span:auth:ShaSecurityProvider.getKeyProvider/spike` 1
- persistence-cpu-throttle T r0.05: `span:persistence:PersistenceCategory.getId/spike` 4

## Predictions (primary: K per family on the scored set, floor primary)

- **P1 under v2.4's definition** (auth-freeze; H4 interval, ambiguity window [onset command, command returned (no Docker events) + delta] and tolerance as decided in decision 54, observed = first `failed` catch; or an error answer before the timeout, the declared alternative): 4/4; per rate r10 1/1, r1 1/1, r0.2 1/1, r0.05 1/1; not evaluable 0; holds by branch: error answer before the timeout (declared alternative) 1, timeout interval 3; verdict **holds**.
- **P2** r10 (failed before the first `failed` catch <= 153.00): 1/1, counts [116], verdict — (n < 4).
- **P2** r1 (failed before the first `failed` catch <= 18.00): 1/1, counts [16], verdict — (n < 4).
- **P2** r0.2 (failed before the first `failed` catch <= 6.00): 1/1, counts [4], verdict — (n < 4).
- **P2** r0.05 (failed before the first `failed` catch <= 3.75): 1/1, counts [1], verdict — (n < 4).
- **P3** auth-freeze: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P3** persistence-cpu-throttle: **—** (no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; actuator readback excluded, decision 26)).
- **P4a** auth-freeze (outside the target, without BC; wins under H3 a-c, >= 3 of 4, descriptive): r10 — (S, T not at the operating point), r1 — (S, T not at the operating point), r0.2 — (S, T not at the operating point), r0.05 — (S, T not at the operating point); highest rate **— at {10, 1, 0.2, 0.05}**.
- **P4a** persistence-cpu-throttle (outside the target, without BC; wins under H3 a-c, >= 3 of 4, descriptive): r10 — (S, T not at the operating point), r1 — (S, T not at the operating point), r0.2 — (S, T not at the operating point), r0.05 — (S, T not at the operating point); highest rate **— at {10, 1, 0.2, 0.05}**.
- **P4b** auth-freeze (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4, descriptive): r10 — (S, T not at the operating point), r1 — (S, T not at the operating point), r0.2 — (S, T not at the operating point), r0.05 — (S, T not at the operating point); highest rate **— at {10, 1, 0.2, 0.05}**.
- **P4b** persistence-cpu-throttle (the target's own sensors, without BC; wins under H3 a-c, >= 3 of 4, descriptive): r10 — (S, T not at the operating point), r1 — (S, T not at the operating point), r0.2 — (S, T not at the operating point), r0.05 — (S, T not at the operating point); highest rate **— at {10, 1, 0.2, 0.05}**.

### P4 folds (sensor rule vs ledger rule; lead, margin; category)

- P4a auth-freeze r10: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)
- P4a auth-freeze r1: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)
- P4a auth-freeze r0.2: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)
- P4a auth-freeze r0.05: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)
- P4a persistence-cpu-throttle r10: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)
- P4a persistence-cpu-throttle r1: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)
- P4a persistence-cpu-throttle r0.2: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)
- P4a persistence-cpu-throttle r0.05: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)
- P4b auth-freeze r10: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)
- P4b auth-freeze r1: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)
- P4b auth-freeze r0.2: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)
- P4b auth-freeze r0.05: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)
- P4b persistence-cpu-throttle r10: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)
- P4b persistence-cpu-throttle r1: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)
- P4b persistence-cpu-throttle r0.2: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)
- P4b persistence-cpu-throttle r0.05: — (not evaluable): family S, T not at the operating point for this class at this rate (B1, decision 55)

### P4 folds under the reference K = 4 where the primary is `—` (descriptive, not an operating point)


**Beside the primary** (highest rate where P4 holds): floor arm (refitted K), K = 4 reference (not an operating point), and the per-system K (decision 53's `beside`):

| verdict | primary | floor arm (refitted K) | reference K = 4 | per-system K |
|---|---|---|---|---|
| P4a auth-freeze | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a persistence-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b auth-freeze | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b persistence-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC auth-freeze | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4a withBC persistence-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC auth-freeze | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |
| P4b withBC persistence-cpu-throttle | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} | — at {10, 1, 0.2, 0.05} |

## Primary outcome: time to detection at the operating point, misses charged at the hold end

Detected k/n · median [min-max] · **mean over all n** (with BC catches), then without BC; FA = held-out false alarms on the class's scored set at the family's K: alarms (/h, [bound]). `—` = channel missing or family not at the operating point for this class at this rate.

| class | rate | n | E | E no BC | L | L no BC | M | M no BC | S | S no BC | T | T no BC | L:own | L:own no BC | M:own | M:own no BC | S:own | S:own no BC | T:own | T:own no BC | FA E | FA L | FA M | FA S | FA T |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| auth-freeze | 10 | 1 | 1/1 · 0.83 · **0.83** | (= E) | 1/1 · 10.20 · **10.20** | 1/1 · 16.64 · **16.64** | — | — | — | — | — | — | 0/1 · **60.26** | 0/1 · **60.26** | — | — | — | — | — | — | 2 (3.6 [11.4]) | 0 (0.0 [5.4]) | — | — | — |
| auth-freeze | 1 | 1 | 1/1 · 1.52 · **1.52** | (= E) | 1/1 · 11.41 · **11.41** | 1/1 · 30.75 · **30.75** | — | — | — | — | — | — | 0/1 · **60.24** | 0/1 · **60.24** | — | — | — | — | — | — | 0 (0.0 [5.4]) | 0 (0.0 [5.4]) | — | — | — |
| auth-freeze | 0.2 | 1 | 1/1 · 9.09 · **9.09** | (= E) | 1/1 · 10.59 · **10.59** | 1/1 · 28.34 · **28.34** | — | — | — | — | — | — | 0/1 · **60.24** | 0/1 · **60.24** | — | — | — | — | — | — | 0 (0.0 [5.4]) | 0 (0.0 [5.4]) | — | — | — |
| auth-freeze | 0.05 | 1 | 1/1 · 21.70 · **21.70** | (= E) | 1/1 · 9.45 · **9.45** | 1/1 · 25.90 · **25.90** | — | — | — | — | — | — | 0/1 · **60.24** | 0/1 · **60.24** | — | — | — | — | — | — | 0 (0.0 [5.4]) | 0 (0.0 [5.4]) | — | — | — |
| persistence-cpu-throttle | 10 | 1 | 1/1 · 0.61 · **0.61** | (= E) | 1/1 · 13.09 · **13.09** | 1/1 · 13.09 · **13.09** | — | — | — | — | — | — | 0/1 · **60.12** | 0/1 · **60.12** | — | — | — | — | — | — | 2 (3.6 [11.4]) | 0 (0.0 [5.4]) | — | — | — |
| persistence-cpu-throttle | 1 | 1 | 1/1 · 1.03 · **1.03** | (= E) | 1/1 · 42.92 · **42.92** | 1/1 · 42.92 · **42.92** | — | — | — | — | — | — | 0/1 · **60.11** | 0/1 · **60.11** | — | — | — | — | — | — | 0 (0.0 [5.4]) | 0 (0.0 [5.4]) | — | — | — |
| persistence-cpu-throttle | 0.2 | 1 | 1/1 · 9.19 · **9.19** | (= E) | 0/1 · **60.13** | 0/1 · **60.13** | — | — | — | — | — | — | 0/1 · **60.13** | 0/1 · **60.13** | — | — | — | — | — | — | 0 (0.0 [5.4]) | 0 (0.0 [5.4]) | — | — | — |
| persistence-cpu-throttle | 0.05 | 1 | 1/1 · 34.61 · **34.61** | (= E) | 1/1 · 47.98 · **47.98** | 1/1 · 48.21 · **48.21** | — | — | — | — | — | — | 0/1 · **60.11** | 0/1 · **60.11** | — | — | — | — | — | — | 0 (0.0 [5.4]) | 0 (0.0 [5.4]) | — | — | — |

## Secondary: failed requests scheduled before the first catch, with their H4 class

Cell: failed requests per episode, median [min-max] (detected/n) · H4 class totals over the episodes straddling / after the onset interval (before: none can be, they are scheduled after the onset).

| class | rate | n | E | L | M | S | T | L:own | M:own | S:own | T:own |
|---|---|---|---|---|---|---|---|---|---|---|---|
| auth-freeze | 10 | 1 | 6 (1/1) · 0/6 | 165 (1/1) · 0/165 | — | — | — | 601 (0/1) · 0/601 | — | — | — |
| auth-freeze | 1 | 1 | 2 (1/1) · 0/2 | 31 (1/1) · 0/31 | — | — | — | 60 (0/1) · 0/60 | — | — | — |
| auth-freeze | 0.2 | 1 | 2 (1/1) · 0/2 | 5 (1/1) · 0/5 | — | — | — | 12 (0/1) · 0/12 | — | — | — |
| auth-freeze | 0.05 | 1 | 1 (1/1) · 0/1 | 1 (1/1) · 0/1 | — | — | — | 3 (0/1) · 0/3 | — | — | — |
| persistence-cpu-throttle | 10 | 1 | 0 (1/1) · 0/0 | 64 (1/1) · 0/64 | — | — | — | 369 (0/1) · 0/369 | — | — | — |
| persistence-cpu-throttle | 1 | 1 | 0 (1/1) · 0/0 | 0 (1/1) · 0/0 | — | — | — | 0 (0/1) · 0/0 | — | — | — |
| persistence-cpu-throttle | 0.2 | 1 | 0 (1/1) · 0/0 | 0 (0/1) · 0/0 | — | — | — | 0 (0/1) · 0/0 | — | — | — |
| persistence-cpu-throttle | 0.05 | 1 | 0 (1/1) · 0/0 | 0 (1/1) · 0/0 | — | — | — | 0 (0/1) · 0/0 | — | — | — |

## P1 detail (H4, M5)

- r10 b1: interval 0.201 s (intervention sweep.commandStamps onsetCommandReturnedMonotonicOffsetSeconds (the cell keeps no Docker events: [command issued, command returned])); delta 0.023 s (from 600 requests); ambiguity window [0, 0.225] s with 3 requests completing in it; expected [14.933, 15.233] +- 0.051 s (ledgerGranularity 1e-17, receiptGranularity 1e-15, sendToWait 0.051, receiptAlignmentResidual 7.7e-05); observed 11.804; classes {'before': 600, 'straddling': 3, 'after': 1197}; max dispatch lag 0.063 s holds via **error answer before the timeout (declared alternative)** (first failed: {"errorAnswer": true, "errors": ["HTTPError"], "outcome": "failed", "status": 500})
- r1 b1: interval 0.180 s (intervention sweep.commandStamps onsetCommandReturnedMonotonicOffsetSeconds (the cell keeps no Docker events: [command issued, command returned])); delta 0.029 s (from 61 requests); ambiguity window [0, 0.210] s with 0 requests completing in it; expected [15.310, 15.310] +- 0.062 s (ledgerGranularity 1e-19, receiptGranularity 1e-15, sendToWait 0.062, receiptAlignmentResidual 8.1e-05); observed 15.327; classes {'before': 61, 'after': 119}; max dispatch lag 0.005 s holds via **timeout interval**
- r0.2 b1: interval 0.182 s (intervention sweep.commandStamps onsetCommandReturnedMonotonicOffsetSeconds (the cell keeps no Docker events: [command issued, command returned])); delta 0.037 s (from 13 requests); ambiguity window [0, 0.219] s with 0 requests completing in it; expected [18.932, 18.932] +- 0.075 s (ledgerGranularity 1e-18, receiptGranularity 1e-15, sendToWait 0.075, receiptAlignmentResidual 7.8e-05); observed 18.950; classes {'before': 13, 'after': 23}; max dispatch lag 0.010 s holds via **timeout interval**
- r0.05 b1: interval 0.177 s (intervention sweep.commandStamps onsetCommandReturnedMonotonicOffsetSeconds (the cell keeps no Docker events: [command issued, command returned])); delta 0.038 s (from 4 requests); ambiguity window [0, 0.215] s with 0 requests completing in it; expected [21.686, 21.686] +- 0.083 s (ledgerGranularity 1e-18, receiptGranularity 1e-14, sendToWait 0.083, receiptAlignmentResidual 8e-05); observed 21.702; classes {'before': 4, 'after': 5}; max dispatch lag 0.020 s holds via **timeout interval**

## Exposure (H5): recorded, the objective unchanged

Route call path (projected from the no-fault traces, plus data stores by depends_on): auth, persistence, webui. Trace edges: auth->persistence, webui->auth. Episodes with no request started in the fault window: 0 of 8. Never-exposed sensors: 265, on services db, image, rabbitmq, recommender, registry; a miss of such a sensor reads "not exposed in this run", never "cannot detect".

## Defaults and declared limits

- Every tunable value is in research/protocol/parameters.json; the rule texts there (RESOLUTION_RULE, MARGIN_RULE, LOG_RECEIPT_RULE, P1_TOLERANCE_RULE, P1_AMBIGUITY_WINDOW_RULE, LEDGER_ABSENT_TOKEN_RULE, SCALE_NOT_ESTIMABLE_RULE, CALIBRATION_SET_RULE, P4_NOT_EVALUABLE_RULE, EXPOSURE_RULE) are what this script implements.
- Baseline (H1): per rate, every valid cell's fault-free time (no-fault cells whole, fault cells before startedMonotonic), scope probe rule, unscreened; n >= MIN_BASELINE_POOLED or —; MAD = 0 -> scale not estimable (M2), level rules —. Episodes at one rate share it (it is the other cells plus the episode's own pre-onset).
- Operating point (H2/H7, M3): no-fault cells only (decision 33; the quiet time per rate is in the table above, every campaign given pooled, H1); pre-onset time of fault cells is not added to the held-out quiet time. The calibrated detector of a class is its scored set: the family's no-BC column detector (own and outside sensors together, the path filter and BC flags as in scoring); P4a/P4b select single sensors from it, whose false-alarm count is at most the family's (engineering default, recorded). The with-BC column uses the same K. The ledger E keeps its BC catches (as in scoring) and is the same for every class.
- K (decision 53): one K per channel family within the system, over every (class, rate) where some grid K meets the target; where none does, the family is `—` there. The K grid is not extended after the fact (decision 55).
- Clock mapping: every monotonic <-> wall conversion uses the per-cell offset fitted on the ledger's own stamps (v1 used the barrier pair).
- M1 (decision 51) ties the ledger's `absent` to the completion that ends its silence; decision 57 ties a sensor's `absent` to the observation that ends its silence (its own token, else its trace's entry-root token); with neither, the pair is unclassifiable (no win) and counted.
- P4 in the availability clock is a sensitivity row (decision 43): spans have no receive stamp, so their availability verdict is —.
- Probe and caller-span variants are not recomputed: v2.1 implements the AMENDMENT_3 primaries (scope, content); v1's readout showed all six variant columns identical.
- Not implemented here: the H6 placement bounds and CELF (next step, METHODOLOGY_HARDENING.md §4), the H9 model, Chao2 and the quantile threshold for MAD = 0 sensors (W2, decision 52). v2.2+ reads Hotel, TeaStore (harness 91c4967) and OTel (harness 6e37ec2) cells into one model; the rules are the same for all three, the system values are the registry's (SYSTEM_<SUT>, CLIENT_TIMEOUT_S_<SUT>, ROUTE_SERVICES_<SUT>, ACTUATOR_READBACK_<SUT>, ...).
- TeaStore and OTel (v2.2+): spans carry no token; a span's request is its trace's (TOKEN_SOURCES: TeaStore's auth bridge, OTel's originalTraceId); untokened probe traces are not read (PROBE_TRACE_RULE); the onset interval's upper bound is the command's return (no Docker events in the cells); several campaigns of one system are pooled (H1, decision 31); with fewer episodes than declared, P2 and P4 are — and P4's single episode is reported, descriptive. OTLP log records in otelcol.log are not read (L is application.log).
- Known limitation F7 (v2.2 review, registry KNOWN_LIMITATIONS): TeaStore fixture cells are written by the harness's test writer (tests/test_teastore_traffic_sweep.py make_sweep_run), which writes resources.json in every cell; the producer writes it in no-fault cells only (modules/teastore/execution/performance_campaign.py:1690-1693). The reader never reads M on TeaStore (FAMILY_CHANNELS), so the fixture difference is untested, not a reader path.
- Known limitation F9 (v2.2 review, registry KNOWN_LIMITATIONS): TeaStore S samples are placed on the wall clock through the producer's barrier pair (CLOCK_RULE_TEASTORE), not the ledger fit; the P4 margin of an S-vs-ledger lead omits that mapping term, which P1's tolerance includes (receipt-alignment residual). Immaterial at a 5 s cadence; recorded.
- Known limitation F10 (v2.2 review, registry KNOWN_LIMITATIONS): OTel cell validity is the target-side receipt.json state (it folds in F1/G1/G2/G4, trace completeness and container health); the coordinator-side terminal replay (candidate_terminal.validate_campaign, remote-terminal.json) is not read. TeaStore reads the validator's candidate-validation.json.
- Known limitation F11 (v2.2 review, registry KNOWN_LIMITATIONS): The harness refuses a cell when one token maps to several Kieker traces, and (woven entry point) when one trace maps to several tokens (modules/teastore/witness/extract_native_token_correlation.py:449-467); the reader drops such bridge rows instead and counts them (readout: reader statistics, bridgeTokensWithSeveralTraces / bridgeTracesWithSeveralTokens). On harness-validated cells both counts are expected 0.
- Known limitation G4 (v2.3 review, registry KNOWN_LIMITATIONS): OTel: productcatalogservice logs through logrus's default TextFormatter (upstream src/productcatalogservice/main.go:57, not JSON) and frontend writes plain console output, so neither carries an app stamp the reader parses (JSON_LOG_STAMP_RULE notParsed): their L leads read "log lead not counted (no app stamp)" and their lines do not enter LOG_RECEIPT_RULE's bound. Recorded, not fixed (a logfmt reader would be a new layout).
- v2.3 fixes from the v2.2 review (registry V23_FIXES): F2: P1's branch (timeout interval, or TeaStore's declared error-answer alternative) is printed in the P1 summary and detail, and holds are counted by branch; F3: json-line records keep their own stamp (JSON_LOG_STAMP_RULE); F4: the v2.3 freeze record states every difference of the Hotel re-run, not only campaignIndex; F5: the readout states harness provenance from HARNESS_PROVENANCE; TeaStore cells' frameworkCommit is checked against it (flagged, not refused); F8: the TeaStore/OTel end-to-end tests pool perturbed quiet copies (one carries a template the others lack), so leave-one-cell-out is tested on those paths and its planted defect is caught; F12: the moved-verdict sections count changed P4 folds in every setting and BC view, each with its rule, and the number not explained by an expected rule; F11: the reader's bridge drops are printed (reader statistics); paths: registry and comment citations of harness files use their module paths (modules/teastore/witness/..., modules/otel-demo/validation/...).
- v2.4 fixes from the v2.3 review (registry V24_FIXES): G3: the unclassifiable label names both ends of the silence ('no silence-ending or silence-starting token'), since a missing start token (decision 58) also makes a pair unclassifiable; comparisons map the v2.2/v2.3 label onto it (CATEGORY_ALIASES); G4: recorded as a known limitation (KNOWN_LIMITATIONS G4) and in JSON_LOG_STAMP_RULE notParsed; v2.3 comparison: --v23-readout adds the v2.3 -> v2.4 moved-verdict table and the changed P4 folds in every setting and view.
- P1 (v2.4): observed = the ledger's first `failed` catch, the rule the timeout model predicts. E also has `absent` (H3 e); it can fire before a timeout only where its gap is shorter than the timeout: r10 login-only-v1: gap 0.658 s < timeout 15 s (can fire before a timeout); `absent` before the first `failed` in 1/1 pause episodes; r1 login-only-v1: gap 2.156 s < timeout 15 s (can fire before a timeout); `absent` before the first `failed` in 1/1 pause episodes; r0.2 login-only-v1: gap 10.077 s < timeout 15 s (can fire before a timeout); `absent` before the first `failed` in 1/1 pause episodes; r0.05 login-only-v1: gap 40.097 s >= timeout 15 s (cannot fire before a timeout); `absent` before the first `failed` in 0/1 pause episodes. P2 uses the same `failed` catch, as v1.
