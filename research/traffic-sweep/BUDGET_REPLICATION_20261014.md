# Budget and stop rule: replications of campaign F (OTel) and the TeaStore off-path epoch, 2026-10-14

Committed alone, before any replication work. Authority: user, 2026-10-14 ~06:50Z: "continue the run throughs autonomously on the servers over the next
2 hours". Scope of every number: instance. Paper deadline 2026-10-16 11:59Z.

## What runs
1. **F-rep1** on fb14srv6: epoch `otel-offpath-f-v1`, harness `715d57b` unchanged, **attempt 2** (plan `373a1ece…`, 25 cells, same descriptor
   `6164052d…`); only the attempt number differs, so run IDs differ. Analysis: the frozen v3.3 chain exactly as for F (training readout blocks 1-3,
   placement solved on the replicate's own training blocks, pinned, scoring readout --test-blocks 4 5, scorer, post hoc lanes), giving an independent
   second verdict per off-path class and 4 more off-path test episodes for F-L1..F-M. F's own verdicts and placement are not changed or pooled.
2. **TS-rep1** on fb14srv5: epoch `teastore-offpath-v1`, harness `f74b29b` unchanged, plan `5a8e385e…` (30 cells); the gate chain mints a new setup ID.
   Analysis: one v3.3 readout on the replicate's fetch only, post hoc lanes (T-L1, T-L2, T-OFF, T-C) on 10 new recommender-pause episodes.
## Deadlines (UTC)
Launch both by 2026-10-14 09:00Z; terminal and fetched by 2026-10-14 14:00Z; readouts, scores and result notes committed by 18:00Z.
## Stop rules
1. A missed deadline stops that step; the paper reports F and TeaStore off-path without replication. No extension without the user.
2. 30 minutes per critical-path defect; 2 defects stop that replication. At most 1 relaunch each, harness or infrastructure defects only.
3. Launch only from a declaration committed alone plus a passing DRY_RUN; one campaign per host.
4. No replicate cell is read (validity only) before its run order is committed; the frozen v3.3 chain is used unchanged.
5. If a guard refuses attempt 2 or a host path collides, that replication stops and is reported; no harness change under this budget.

## Amendment 1 (user, 2026-10-14 ~14:25Z, committed alone)
F-rep1's DRY_RUN (`f2dry`, 06:53Z) refused attempt 2 because F attempt 1's one-shot host paths existed (stop rule 5). The user said "archive F's
attempt-1 paths on srv6 and launch the F replication" and "finalise the experiments and the respective paper". Done ~14:28Z: the three guarded paths
(`otel-offpath-f-v1` 4.6 GB, `.setup-otel-offpath-f-v1` 47 MB, release `otel-offpath-f-v1-715d57b5f06e` 72 MB) were **moved, not deleted**, into
`archive-f-attempt1-20261014/` beside them on srv6 (same filesystem); attempt 1 was fetched and byte-verified before (437/437). New deadlines for
F-rep1: launch by 2026-10-14 15:30Z; terminal and fetched 19:30Z; readouts, scores, result note 23:00Z. TeaStore replication ended by its stop rules
(`STOP_TEASTORE_OFFPATH_REP1.md`). Other rules unchanged.
