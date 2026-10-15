# Plan: three detection lanes per system, 2026-10-14 (written 2026-10-13 ~13:30Z)

Question (user, 2026-10-13): not whether the request ledger misses an off-path fault, but which lane of our monitoring
catches it, with which sensor set, at what false-alarm price, per system. Deadline BenchSOC 2026-10-16 11:59Z.
Everything below is post hoc unless a campaign is declared for it. Scope: instance per row.

## What the existing evidence already says (checked 2026-10-13)

| lane | OTel (E, 25 req/s) | TeaStore (C) | Hotel (sweep r3) |
|---|---|---|---|
| 1 own silence (`absent` on the paused target) | 10/10 off-path episodes, 0.88-1.55 s; price 19.97/h (fraud log id), 31.6/h (accounting) | auth-freeze 28/28, median 6.9 / 4.7 / 1.5 / 0.5 s at 0.05 / 0.2 / 1 / 10 req/s | search-pause 16/16, median 30.5 / 8.8 / 1.7 / 0.3 s at the same rates |
| 2 coordinator side | Kafka group-coordinator logs, 4/4 test at 43.4-44.3 s; client default session timeout 45 s (not overridden in either consumer; library default, jar not checked) | registry heartbeat removal `log:registry:1b6e1f5f63fc` 28/28 auth-freeze at 9.1-11.7 s (alive window 10 s, `HeartbeatInfo.java:32`) | none: consul registers without health checks |
| 3 backlog / lag | collected but unarmed: 379 metric ids in E, incl. `kafka.consumer.records_lag`; 60 s export cadence gives pooled n = 3-18 < `MIN_BASELINE_POOLED` = 20. Client-side lag of a paused JVM is silent; group lag needs the collector's `kafkametrics` receiver | n/a (only queue is Kieker's) | n/a (no queue) |

- Lane 1 is excluded from the frozen rules by decisions 84/111 (measures the injection). Its speed scales with traffic for on-path
  targets (above); for E's consumers it does not depend on the request rate in the same way (poll loop), unverified.
- All faults run so far on TeaStore and Hotel are on the request path. Neither has an application queue.
- Ids per service, E ground set: 4,417 placeable ids over 19 services (recommendationservice 2,193, checkoutservice 1,680).

## Shared-fate groups (design note)

A generalisation drawn from a private, de-identified incident review is omitted from this copy.

- Dimensionality: place over shared-fate units first (host -> container -> broker/registry -> signal), then refine inside a unit.
  Ours: one host per SUT, one replica per service, shared units = host, Docker daemon, collector (all telemetry lanes share it; only the
  witness/ledger is independent), broker (OTel), registry (TeaStore). A per-container silence sensor is 19 sensors on OTel, not 4,417.
- Our SUTs run no replicas; replica experiments are future work (OTel compose pins `container_name`, so `--scale` is blocked).

## Directions

Offline, no server (engineering defaults; new output paths, labelled post hoc):
- O1 lane-1 rows per system from existing readouts (done above; write as a table generator).
- O2 lane-2 rows (E Kafka, TeaStore registry) with price if evaluated.
- O3 lane-3 sensitivity: E reader with `MIN_BASELINE_POOLED` lowered, exploratory dir, to see whether lag/fetch metrics move at all.
- O4 shared-fate aggregation: per-container "any telemetry absent" sensor on E/C/Hotel, with its no-fault alarm count.
- O5 price-vs-detection curve per lane (the FP/FN sensitivity curve), all three systems.

Server (each needs budget + stop rule committed alone, declaration, DRY_RUN; user decision):
- S1 OTel srv6, campaign F: E's design + `OTEL_METRIC_EXPORT_INTERVAL` 5 s + spanmetrics flush 5 s + `kafkametrics` consumer-group lag
  (service.name upsert) + more no-fault cells. New epoch (~1,350 lines, mostly a copy of `candidate_offpath_e.py`), reader registry
  amendment + new freeze. Unverified: `kafkametrics` in contrib 0.108; non-Java SDKs honouring the interval.
- S2 TeaStore srv5: pause `recommender` (off the login path). Lanes 2 (registry removal, expected ~10-12.5 s) and 1 (cgroup CPU).
  Harness: parameterise the pause target (~100-150 lines + epoch module); reader: second pause regime trips `pause_regime()` assert.
- S3 Hotel srv4: pause `consul` as a negative control (expected invisible to every lane). Needs a new manifestation rule (current pause
  validity requires a route outage), collector scope change; medium-large. Recommended: defer.

Order if S1 and S2 are approved: O1-O5 and both harness builds today (parallel subworkers), reviews, budgets committed alone,
DRY_RUNs 2026-10-14 morning, runs 2026-10-14, read under a frozen reader 2026-10-14 evening, paper 2026-10-15.
