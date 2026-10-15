# Budget and stop rule: overnight runs addressing the paper's weakest points, 2026-10-14/15

Committed alone, before any of this work. Authority: user, 2026-10-14 ~14:45Z: "address some of the weakest parts like F replication over night on the
other servers and potentially fix the kieker queue race" (with the list of weaknesses). Scope of every number: instance. Paper deadline 2026-10-16 11:59Z.

## Work items (priority order)
1. **F replicates on fb14srv6** (same epoch, harness `715d57b`, frozen v3.3 chain per replicate, each analysed alone): F-rep1 (attempt 2, running,
   `d0ef902`), F-rep2 (attempt 3, after attempt 2's one-shot host paths are archived by move, as for attempt 1). OTel is bound to srv6 in 38 harness
   files, so a cross-host OTel run is out of scope; host stays confounded with SUT (stated).
2. **F ablation on fb14srv6:** a new epoch `otel-offpath-f-nolag-v1` = F without the `kafkametrics` receiver (5 s export, spanmetrics flush and two
   no-fault cells per block kept), same rule, same analysis chain; declared before launch. Question: does F's pass hold without the lag receiver.
3. **Kieker-queue barrier race (TeaStore):** a harness fix at `modules/teastore/execution/performance_campaign.py:3490` (bounded wait for the queue to
   drain before the barrier decision; refuse after the bound, recorded), tests with a planted defect, independent review; then the TeaStore off-path
   replication on fb14srv5 with the fixed harness (same plan, new framework commit).
4. **Hotel off-path on fb14srv4** (consul pause as the declared negative control: no coordinator, no queue), only if its harness build and review are done
   by 2026-10-15 03:00Z.
5. **Predictions from post hoc findings, committed before any new cell is read:** ontology run2's competency-question answers (coordinator lane, class,
   window) for the new runs' rows; lane timing bands from the pooled tables; the own-silence traffic dependence where rates vary.

## Deadlines (UTC)
Launches as hosts free up; all new campaigns terminal and fetched by 2026-10-15 08:00Z; readouts, scores, result notes by 12:00Z; paper final by
2026-10-16 06:00Z.
## Stop rules
1. A missed deadline stops that item; the paper reports what finished. No extension without the user.
2. Per campaign: declaration committed alone, DRY_RUN passed, one campaign per host, at most 1 relaunch (harness/infrastructure defects only).
3. 30 minutes per critical-path defect; 2 defects stop that item.
4. No new cell is read (validity only) before its analysis and predictions are committed; frozen v3.3 unchanged (separate recorded pins per replicate).
5. Any permission denial on a harness edit stops that item and is reported; no workaround.
