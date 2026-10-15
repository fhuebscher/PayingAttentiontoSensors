# Predictions for the overnight runs, 2026-10-14/15 (committed before any new-run cell is read)

**PREDICTIONS made before any new-run cell is read. Written under BUDGET_OVERNIGHT_20261014.md item 5 and stop rule 4. None of the new runs' evidence was read to write it: tmp/otel-f-evidence/f2-fetch, any f3 / nolag / teastore-rep2 / hotel-offpath fetch were not opened; inputs are committed files only.** Scope: instance (each run: one SUT, one host, one pinned harness; F-rep1/F-rep2/F-nolag fb14srv6, TeaStore fb14srv5, Hotel fb14srv4; host is confounded with SUT). Budget item: `research/traffic-sweep/BUDGET_OVERNIGHT_20261014.md` item 5.

Generated from `PREDICTIONS_OVERNIGHT_20261014.json` (same directory; a throwaway script rendered both, the JSON is authoritative). `—` = not collected or precondition absent, never 0. Rules are hit / miss statements, not tests; a miss is reported as a miss and no prediction changes a verdict. Thresholds are stated with their justification in the `rule` field.

## Runs

- **FR1**: F-rep1 (attempt 2, plan 373a1ece, fb14srv6)
- **FR2**: F-rep2 (attempt 3, fb14srv6)
- **FNL**: F-nolag ablation (epoch otel-offpath-f-nolag-v1: F without the kafkametrics receiver, fb14srv6)
- **TSR**: TeaStore off-path replication on the fixed harness (Kieker barrier fix; same plan; fb14srv5); no declaration committed at this commit
- **HO**: Hotel off-path (consul-pause and search-pause; fb14srv4); no declaration or build committed at this commit, so its rates and durations are not known here

## Ontology predictions (first made before the data)

Rows for F-rep1, F-rep2, TeaStore and Hotel search-pause are copied exactly from `research/ontology/runs/run2-20261014/PREDICTIONS.json`; F-nolag and Hotel consul-pause were run through `research/ontology/query.py cq` on run2's committed `.ttl` (commands and outputs in the JSON, `queryRuns`). Scoring rules: `research/ontology/compare.py` docstring. The ABox was already compared on earlier campaigns of the same SUT and fault (post hoc), so for the F rows a repeat of the known disagreements (own lane, lag lane, a 45.0 s point window) is not new information about the ontology; the coordinator lane, class and entry-service answers are the ones this data can still test.

| id | system / fault / target | own | coord | coord emits | lag | CQ-C1 | CQ-L2 window (s) | entry reached | blast radius |
|---|---|---|---|---|---|---|---|---|---|
| FR1-ONT-fraud | otel / fraud-pause / frauddetectionservice | no | yes | no | no | tracked | [45.0, 45.0] | no | backlog group-frauddetectionservice |
| FR1-ONT-accounting | otel / accounting-pause / accountingservice | no | yes | no | no | tracked | [45.0, 45.0] | no | backlog group-accountingservice |
| FR1-ONT-frontend | otel / frontend-pause / frontend | no | no | no | no | not-a-member | — | yes | sync-caller svc-frontendproxy; sync-caller svc-grafana; sync-caller svc-jaeger; sync-caller svc-loadgenerator; sync-caller svc-otelcol; sync-caller svc-prometheus |
| FR2-ONT-fraud | otel / fraud-pause / frauddetectionservice | no | yes | no | no | tracked | [45.0, 45.0] | no | backlog group-frauddetectionservice |
| FR2-ONT-accounting | otel / accounting-pause / accountingservice | no | yes | no | no | tracked | [45.0, 45.0] | no | backlog group-accountingservice |
| FR2-ONT-frontend | otel / frontend-pause / frontend | no | no | no | no | not-a-member | — | yes | sync-caller svc-frontendproxy; sync-caller svc-grafana; sync-caller svc-jaeger; sync-caller svc-loadgenerator; sync-caller svc-otelcol; sync-caller svc-prometheus |
| FNL-ONT-fraud | otel / fraud-pause / frauddetectionservice | no | yes | no | no | tracked | [45.0, 45.0] | no | backlog group-frauddetectionservice |
| FNL-ONT-accounting | otel / accounting-pause / accountingservice | no | yes | no | no | tracked | [45.0, 45.0] | no | backlog group-accountingservice |
| FNL-ONT-frontend | otel / frontend-pause / frontend | no | no | no | no | not-a-member | — | yes | sync-caller svc-frontendproxy; sync-caller svc-grafana; sync-caller svc-jaeger; sync-caller svc-loadgenerator; sync-caller svc-otelcol; sync-caller svc-prometheus |
| TSR-ONT-recommender | teastore / recommender-pause / recommender | no | no | no | no | no-liveness-check | — | yes | sync-caller svc-recommender; sync-caller svc-webui |
| TSR-ONT-auth | teastore / auth-freeze / auth | no | no | no | no | no-liveness-check | — | yes | sync-caller svc-webui |
| HO-ONT-search | hotel / search-pause / search | no | no | no | no | no-liveness-check | — | yes | sync-caller svc-frontend |
| HO-ONT-consul | hotel / consul-pause / consul | no | no | no | no | not-a-member | — | yes | sync-caller svc-frontend; sync-caller svc-reservation; sync-caller svc-review |

Query runs for the rows not in run2 (verbatim):

`FNL-ONT-fraud` (answers equal run2's row, asserted at generation):

```
$ uv run python research/ontology/query.py cq C1 research/ontology/runs/run2-20261014/otel.ttl --target frauddetectionservice --kind pause
arch	target	kind	class
arch-otel	svc-frauddetectionservice	pause	tracked
1 rows
$ uv run python research/ontology/query.py cq L1 research/ontology/runs/run2-20261014/otel.ttl --target frauddetectionservice --kind pause
arch	target	kind	ownLane	coordinatorLane	coordinatorEmits	lagLane
arch-otel	svc-frauddetectionservice	pause	False	True	False	False
1 rows
$ uv run python research/ontology/query.py cq L2 research/ontology/runs/run2-20261014/otel.ttl --target frauddetectionservice --kind pause
arch	target	kind	coordinator	liveness	failureTimeout	cleanup	heartbeat	low	high	phaseLow
arch-otel	svc-frauddetectionservice	pause	coord-kafka_consumer-group-session	live-kafka_consumer-group-session-0	45.0	0.0	3.0	45.0	45.0	42.0
1 rows
$ uv run python research/ontology/query.py cq B1 research/ontology/runs/run2-20261014/otel.ttl --target frauddetectionservice --kind pause
arch	target	effect	affected	via
arch-otel	svc-frauddetectionservice	backlog	group-frauddetectionservice	topic-orders
1 rows
```

`FNL-ONT-accounting` (answers equal run2's row, asserted at generation):

```
$ uv run python research/ontology/query.py cq C1 research/ontology/runs/run2-20261014/otel.ttl --target accountingservice --kind pause
arch	target	kind	class
arch-otel	svc-accountingservice	pause	tracked
1 rows
$ uv run python research/ontology/query.py cq L1 research/ontology/runs/run2-20261014/otel.ttl --target accountingservice --kind pause
arch	target	kind	ownLane	coordinatorLane	coordinatorEmits	lagLane
arch-otel	svc-accountingservice	pause	False	True	False	False
1 rows
$ uv run python research/ontology/query.py cq L2 research/ontology/runs/run2-20261014/otel.ttl --target accountingservice --kind pause
arch	target	kind	coordinator	liveness	failureTimeout	cleanup	heartbeat	low	high	phaseLow
arch-otel	svc-accountingservice	pause	coord-kafka_consumer-group-session	live-kafka_consumer-group-session-0	45.0	0.0	3.0	45.0	45.0	42.0
1 rows
$ uv run python research/ontology/query.py cq B1 research/ontology/runs/run2-20261014/otel.ttl --target accountingservice --kind pause
arch	target	effect	affected	via
arch-otel	svc-accountingservice	backlog	group-accountingservice	topic-orders
1 rows
```

`FNL-ONT-frontend` (answers equal run2's row, asserted at generation):

```
$ uv run python research/ontology/query.py cq C1 research/ontology/runs/run2-20261014/otel.ttl --target frontend --kind pause
arch	target	kind	class
arch-otel	svc-frontend	pause	not-a-member
1 rows
$ uv run python research/ontology/query.py cq L1 research/ontology/runs/run2-20261014/otel.ttl --target frontend --kind pause
arch	target	kind	ownLane	coordinatorLane	coordinatorEmits	lagLane
arch-otel	svc-frontend	pause	False	False	False	False
1 rows
$ uv run python research/ontology/query.py cq L2 research/ontology/runs/run2-20261014/otel.ttl --target frontend --kind pause
0 rows
$ uv run python research/ontology/query.py cq B1 research/ontology/runs/run2-20261014/otel.ttl --target frontend --kind pause
arch	target	effect	affected	via
arch-otel	svc-frontend	sync-caller	svc-frontendproxy	svc-frontend
arch-otel	svc-frontend	sync-caller	svc-grafana	svc-frontend
arch-otel	svc-frontend	sync-caller	svc-jaeger	svc-frontend
arch-otel	svc-frontend	sync-caller	svc-loadgenerator	svc-frontend
arch-otel	svc-frontend	sync-caller	svc-otelcol	svc-frontend
arch-otel	svc-frontend	sync-caller	svc-prometheus	svc-frontend
6 rows
```

`HO-ONT-consul`:

```
$ uv run python research/ontology/query.py cq C1 research/ontology/runs/run2-20261014/hotel.ttl --target consul --kind pause
arch	target	kind	class
arch-hotel	svc-consul	pause	not-a-member
1 rows
$ uv run python research/ontology/query.py cq L1 research/ontology/runs/run2-20261014/hotel.ttl --target consul --kind pause
arch	target	kind	ownLane	coordinatorLane	coordinatorEmits	lagLane
arch-hotel	svc-consul	pause	False	False	False	False
1 rows
$ uv run python research/ontology/query.py cq L2 research/ontology/runs/run2-20261014/hotel.ttl --target consul --kind pause
0 rows
$ uv run python research/ontology/query.py cq B1 research/ontology/runs/run2-20261014/hotel.ttl --target consul --kind pause
arch	target	effect	affected	via
arch-hotel	svc-consul	sync-caller	svc-frontend	svc-consul
arch-hotel	svc-consul	sync-caller	svc-reservation	svc-consul
arch-hotel	svc-consul	sync-caller	svc-review	svc-consul
3 rows
```

## All predictions

Columns: id; claim; rule (hit/miss); basis (file:line); scoring (committed output and field). Ontology rows: see the table above and the `rule` field in the JSON.

### Lane timing bands

**FR1-L1** (FR1; fraud-pause, accounting-pause)
- Claim: Own silence: the target's own sensors fire (by-construction field) < 2.0 s after the pause command in 4/4 off-path test episodes (blocks 4-5). Restated unchanged from DECLARATION_F_OTEL.md F-L1.
- Rule: hit iff 4/4 off-path test episodes have an own-lane earliest fire < 2.0 s; miss otherwise; — if an episode has no own sensors collected
- Basis: research/traffic-sweep/DECLARATION_F_OTEL.md:50 (F-L1); research/placement/test-f/RESULT_F.md:42 (F attempt 1: 0.84-1.52 s, 4/4); research/lanes/out-pooled-20261014/POOLED.md:78-79 (E: 10/10 at 0.88-1.55 s)
- Scoring: posthoc_lanes_v33.py otel output of the replicate (new out dir, recorded in its commit); field `predictions[id=F-L1].result and numbers.episodes[].earliest.ttd`

**FR1-L2** (FR1; fraud-pause, accounting-pause, frontend-pause)
- Claim: Coordinator lane: the earliest counted fire among the log ids of service kafka is 42-47 s after the pause command in 4/4 off-path test episodes, and no fire in either field in the 2 frontend test episodes. Restated unchanged from F-L2.
- Rule: hit iff 4/4 off-path test episodes have a counted coordinator fire in [42, 47] s and both frontend episodes have no coordinator fire in either field
- Basis: research/traffic-sweep/DECLARATION_F_OTEL.md:51 (F-L2); research/placement/test-f/RESULT_F.md:43 (F: 43.3-44.0 s, 4/4); research/lanes/out-pooled-20261014/POOLED.md:78-79 (E: 5/5 43.71-44.32 and 5/5 43.37-43.94, counted 5/5 each); research/lanes/out-pooled-20261014/POOLED.md:84 (frontend 0/5)
- Scoring: posthoc_lanes_v33.py otel output of the replicate (new out dir, recorded in its commit); field `predictions[id=F-L2].result, numbers.offpathInWindow, numbers.frontendNoFireEitherField`

**FR1-L3** (FR1; fraud-pause, accounting-pause)
- Claim: Lag lane: the consumer-group lag metric ids of service kafka are armed (>= 20 pooled training points) and the lag lane's earliest fire precedes the coordinator lane's fire in >= 3/4 off-path test episodes. Restated from F-L3 with F's measured band attached.
- Rule: hit iff armed and lag fire < coordinator fire in >= 3/4 episodes; additionally stated: lag earliest fire in [3.0, 15.0] s in >= 3/4 episodes (F: 4.5-9.3 s, 4/4)
- Basis: research/traffic-sweep/DECLARATION_F_OTEL.md:52 (F-L3); research/placement/test-f/RESULT_F.md:44 (4.5-9.3 s, 4/4); research/placement/test-f/RESULT_F.md:50-53 (4.5 vs 9.3 s follows the 5 s scrape, threshold-marginal)
- Scoring: posthoc_lanes_v33.py otel output of the replicate (new out dir, recorded in its commit); field `predictions[id=F-L3].result, numbers.k, numbers.episodes`

**FR1-M** (FR1; all)
- Claim: Metric arming: >= 1 non-flagd metric id is placeable at 25 req/s, counted separately for SDK metrics and spanmetrics-derived ids. Restated from F-M.
- Rule: hit iff numbers.placeableNonFlagdSdk >= 1 or numbers.placeableNonFlagdSpanmetrics >= 1
- Basis: research/traffic-sweep/DECLARATION_F_OTEL.md:53 (F-M); research/placement/test-f/RESULT_F.md:45 (F: 236 SDK + 44 spanmetrics-derived)
- Scoring: posthoc_lanes_v33.py otel output of the replicate (new out dir, recorded in its commit); field `predictions[id=F-M].result, numbers.placeableNonFlagdSdk, numbers.placeableNonFlagdSpanmetrics`

**FR2-L1** (FR2; fraud-pause, accounting-pause)
- Claim: Own silence: the target's own sensors fire (by-construction field) < 2.0 s after the pause command in 4/4 off-path test episodes (blocks 4-5). Restated unchanged from DECLARATION_F_OTEL.md F-L1.
- Rule: hit iff 4/4 off-path test episodes have an own-lane earliest fire < 2.0 s; miss otherwise; — if an episode has no own sensors collected
- Basis: research/traffic-sweep/DECLARATION_F_OTEL.md:50 (F-L1); research/placement/test-f/RESULT_F.md:42 (F attempt 1: 0.84-1.52 s, 4/4); research/lanes/out-pooled-20261014/POOLED.md:78-79 (E: 10/10 at 0.88-1.55 s)
- Scoring: posthoc_lanes_v33.py otel output of the replicate (new out dir, recorded in its commit); field `predictions[id=F-L1].result and numbers.episodes[].earliest.ttd`

**FR2-L2** (FR2; fraud-pause, accounting-pause, frontend-pause)
- Claim: Coordinator lane: the earliest counted fire among the log ids of service kafka is 42-47 s after the pause command in 4/4 off-path test episodes, and no fire in either field in the 2 frontend test episodes. Restated unchanged from F-L2.
- Rule: hit iff 4/4 off-path test episodes have a counted coordinator fire in [42, 47] s and both frontend episodes have no coordinator fire in either field
- Basis: research/traffic-sweep/DECLARATION_F_OTEL.md:51 (F-L2); research/placement/test-f/RESULT_F.md:43 (F: 43.3-44.0 s, 4/4); research/lanes/out-pooled-20261014/POOLED.md:78-79 (E: 5/5 43.71-44.32 and 5/5 43.37-43.94, counted 5/5 each); research/lanes/out-pooled-20261014/POOLED.md:84 (frontend 0/5)
- Scoring: posthoc_lanes_v33.py otel output of the replicate (new out dir, recorded in its commit); field `predictions[id=F-L2].result, numbers.offpathInWindow, numbers.frontendNoFireEitherField`

**FR2-L3** (FR2; fraud-pause, accounting-pause)
- Claim: Lag lane: the consumer-group lag metric ids of service kafka are armed (>= 20 pooled training points) and the lag lane's earliest fire precedes the coordinator lane's fire in >= 3/4 off-path test episodes. Restated from F-L3 with F's measured band attached.
- Rule: hit iff armed and lag fire < coordinator fire in >= 3/4 episodes; additionally stated: lag earliest fire in [3.0, 15.0] s in >= 3/4 episodes (F: 4.5-9.3 s, 4/4)
- Basis: research/traffic-sweep/DECLARATION_F_OTEL.md:52 (F-L3); research/placement/test-f/RESULT_F.md:44 (4.5-9.3 s, 4/4); research/placement/test-f/RESULT_F.md:50-53 (4.5 vs 9.3 s follows the 5 s scrape, threshold-marginal)
- Scoring: posthoc_lanes_v33.py otel output of the replicate (new out dir, recorded in its commit); field `predictions[id=F-L3].result, numbers.k, numbers.episodes`

**FR2-M** (FR2; all)
- Claim: Metric arming: >= 1 non-flagd metric id is placeable at 25 req/s, counted separately for SDK metrics and spanmetrics-derived ids. Restated from F-M.
- Rule: hit iff numbers.placeableNonFlagdSdk >= 1 or numbers.placeableNonFlagdSpanmetrics >= 1
- Basis: research/traffic-sweep/DECLARATION_F_OTEL.md:53 (F-M); research/placement/test-f/RESULT_F.md:45 (F: 236 SDK + 44 spanmetrics-derived)
- Scoring: posthoc_lanes_v33.py otel output of the replicate (new out dir, recorded in its commit); field `predictions[id=F-M].result, numbers.placeableNonFlagdSdk, numbers.placeableNonFlagdSpanmetrics`

**FNL-L1** (FNL; fraud-pause, accounting-pause)
- Claim: Own silence < 2.0 s in 4/4 off-path test episodes (by-construction field); unaffected by removing the metrics receiver.
- Rule: as F-L1
- Basis: research/placement/test-f/RESULT_F.md:42; research/lanes/out-pooled-20261014/POOLED.md:78-79
- Scoring: posthoc_lanes_v33.py otel output of the F-nolag run (new out dir, recorded in its commit); field `predictions[id=F-L1].result`

**FNL-L2** (FNL; fraud-pause, accounting-pause, frontend-pause)
- Claim: Coordinator lane: counted fire 42-47 s in 4/4 off-path test episodes, none in the 2 frontend episodes; unaffected by removing the metrics receiver (the coordinator ids are kafka broker log lines).
- Rule: as F-L2
- Basis: research/placement/test-f/RESULT_F.md:43; research/lanes/out-pooled-20261014/POOLED.md:78-79,84
- Scoring: posthoc_lanes_v33.py otel output of the F-nolag run (new out dir, recorded in its commit); field `predictions[id=F-L2].result`

**FNL-L3** (FNL; fraud-pause, accounting-pause)
- Claim: Lag lane: not applicable. The kafkametrics receiver is removed, so no `metric:kafka:kafka.consumer_group.*` id is collected (state `—`, never a miss).
- Rule: `—` iff numbers.armed is false / lagIdsInCalibration == 0; a miss would be a lag id present in the F-nolag calibration (which would mean the ablation did not remove the receiver)
- Basis: research/traffic-sweep/BUDGET_OVERNIGHT_20261014.md (item 2: F without the kafkametrics receiver); research/traffic-sweep/DECLARATION_F_OTEL.md:25 (the receiver is F's change 3); research/placement/test-f/placement-f.json rates.25.costs (the four `kafka.consumer_group.*` ids)
- Scoring: posthoc_lanes_v33.py otel output of the F-nolag run (new out dir, recorded in its commit); field `predictions[id=F-L3].numbers.armed, .lagIdsInCalibration`

**FNL-M** (FNL; all)
- Claim: Metric arming: >= 1 non-flagd metric id is placeable (5 s export and spanmetrics flush are kept); F had 236 SDK + 44 spanmetrics-derived.
- Rule: as F-M
- Basis: research/placement/test-f/RESULT_F.md:45
- Scoring: posthoc_lanes_v33.py otel output of the F-nolag run (new out dir, recorded in its commit); field `predictions[id=F-M].result`

**TSR-L2** (TSR; recommender-pause)
- Claim: Coordinator: the registry's heartbeat-removal line for the recommender fires 7.5-12.5 s after the pause command in >= 9/10 episodes, at both rates, in the by-construction field (`BC-caller-log`; 0 counted). Restated unchanged from T-L2 (field named).
- Rule: hit iff >= 9/10 episodes have the removal fire in [7.5, 12.5] s in either field; the field is reported (expected: by-construction, counted 0/10)
- Basis: research/traffic-sweep/DECLARATION_TEASTORE_OFFPATH.md:27 (T-L2); research/placement/test-ts-offpath/RESULT_TS_OFFPATH.md:18 (r1: 10/10 at 8.37-12.03 s)
- Scoring: the post hoc lane script's TeaStore output for this run (research/lanes/posthoc_lanes_v33.py teastore, new out dir) and its single-fetch v3.3 readout; field `predictions[id=T-L2].result, numbers.byRate, numbers.episodes[].inWindowFire.{ttd,field}`

**TSR-L2a** (TSR; auth-freeze)
- Claim: Coordinator on the on-path control: the registry removal line for auth fires 7.5-12.5 s after the freeze command in >= 9/10 episodes, both rates, by-construction field.
- Rule: hit iff >= 9/10 auth-freeze episodes have a coordinator fire in [7.5, 12.5] s in either field
- Basis: research/lanes/out-pooled-20261014/POOLED.md:89-92,179 (28/28 at 9.07-11.75 s, all by-construction only)
- Scoring: the post hoc lane script's TeaStore output for this run (research/lanes/posthoc_lanes_v33.py teastore, new out dir) and its single-fetch v3.3 readout; field `per-episode coordinator lane ttdAny of the auth-freeze-effect episodes (readout lanes block)`

**TSR-L1** (TSR; recommender-pause)
- Claim: Own silence, declared form T-L1 (recommender cgroup CPU down-fire < 5 s in >= 9/10) is expected to MISS again: <= 1 of 10 episodes with an own earliest fire < 5 s (r1: 0/10).
- Rule: hit (of this prediction) iff the count of episodes with own earliest fire < 5 s is <= 1 of 10
- Basis: research/placement/test-ts-offpath/RESULT_TS_OFFPATH.md:19,27-31 (miss: cpuUsageUsec flat, calibrated sys_cpu rules did not fire; earliest own fires 14.86-14.92 s)
- Scoring: the post hoc lane script's TeaStore output for this run (research/lanes/posthoc_lanes_v33.py teastore, new out dir) and its single-fetch v3.3 readout; field `predictions[id=T-L1].numbers.k (T-L1 itself reads miss iff k < 9)`

**TSR-L1b** (TSR; recommender-pause)
- Claim: Own lane by rate: at rate 10 an own fire (counted `median`/`run3` of sys_io / sys_psi_cpu) in [12, 18] s in >= 3/5 episodes; at rate 1 own fires in <= 1/5 episodes.
- Rule: hit iff both clauses hold (any field)
- Basis: research/placement/test-ts-offpath/RESULT_TS_OFFPATH.md:19 (r1: 5/5 at 14.86-14.92 s at rate 10; none at rate 1)
- Scoring: the post hoc lane script's TeaStore output for this run (research/lanes/posthoc_lanes_v33.py teastore, new out dir) and its single-fetch v3.3 readout; field `per-episode own lane ttdAny by rate (recommender-pause-effect episodes)`

**TSR-L1c** (TSR; auth-freeze)
- Claim: Own silence of the on-path control: the auth own lane detects 10/10 episodes, all < 1.0 s at rate 10 and all < 2.5 s at rate 1.
- Rule: hit iff 10/10 detected, max(rate 10) < 1.0 s and max(rate 1) < 2.5 s (any field). Thresholds: pooled maxima 0.52 s (rate 10, n 7) and 1.66 s (rate 1, n 7); rate 10 = about 2x the pooled maximum, rate 1 adds one 1 s inter-arrival to it.
- Basis: research/lanes/out-pooled-20261014/POOLED.md:91-92
- Scoring: the post hoc lane script's TeaStore output for this run (research/lanes/posthoc_lanes_v33.py teastore, new out dir) and its single-fetch v3.3 readout; field `per-episode own lane ttdAny, auth-freeze-effect episodes, by rate`

**TSR-OFF** (TSR; recommender-pause)
- Claim: The pause stays off the login route: ok share >= 95 % in >= 9/10 episodes (r1: 10/10, share 1.0) and at most 2 of 10 episodes with a counted ledger fire (r1: 1/10, a spike at 5.07 s). The declared T-OFF clause 'no counted ledger fire' is not predicted to hold in every episode.
- Rule: hit iff both clauses hold; the declared T-OFF itself is scored by the post hoc script as before. Threshold justification: r1 spike rule honest count 1 in 0.25 h at rate 10 gives about 0.07 expected per 60 s hold, 0.33 over 5 rate-10 episodes; P(>= 3 in 10) is below 1 % on that rate, so 2 is the stated ceiling.
- Basis: research/placement/test-ts-offpath/RESULT_TS_OFFPATH.md:20,36
- Scoring: the post hoc lane script's TeaStore output for this run (research/lanes/posthoc_lanes_v33.py teastore, new out dir) and its single-fetch v3.3 readout; field `predictions[id=T-OFF].numbers.okShareClause, .noCountedLedgerFireClause, per-episode ledgerFiresCounted`

**TSR-W** (TSR; recommender-pause)
- Claim: Webui discovery line: the counted fire of `log:webui:d4d75ec135e6` (Ribbon 'current list of Servers=[]') occurs in >= 9/10 recommender-pause episodes, 9.0-15.0 s after onset, 0.5-2.5 s after the registry removal. Not predicted for r1; found in review, so this is its first prediction before data.
- Rule: hit iff >= 9/10 episodes have that sensor id as a counted fire in [9.0, 15.0] s; `—` if the id is absent from this run's ground set (template hash differs)
- Basis: research/placement/test-ts-offpath/RESULT_TS_OFFPATH.md:32-35 (r1: 10/10; 9.52-14.12 s at rate 10, 10.20-12.53 s at rate 1; 0.75-2.08 s after the removal)
- Scoring: the post hoc lane script's TeaStore output for this run (research/lanes/posthoc_lanes_v33.py teastore, new out dir) and its single-fetch v3.3 readout; field `readout episodes[recommender-pause-effect].fires[sensor == log:webui:d4d75ec135e6].ttd`

**HO-C** (HO; consul-pause, search-pause)
- Claim: No coordinator lane and no queue/lag lane for either fault: the lanes block reports the coordinator and lag lanes as not collected (`—`) and no coordinator or lag fire in any episode. consul-pause is the declared negative control for both.
- Rule: hit iff no coordinator-lane and no lag-lane fire in any episode of either fault in either field; a fire is a miss (the lane exists after all). `—` entries are consistent with the prediction.
- Basis: research/lanes/out-pooled-20261014/POOLED.md:74-77,174 (Hotel search-pause: coordinator `—` structural, 16/16 class (a)); research/ontology/runs/run2-20261014/hotel.ttl:415; research/traffic-sweep/BUDGET_OVERNIGHT_20261014.md item 4 (consul pause as negative control: no coordinator, no queue)
- Scoring: the Hotel off-path run's lane output (readout lanes block via research/lanes/pooled_lanes.py or its successor; file recorded in the run's commit); field `lanes.coordinator, lanes.lag per episode`

**HO-L1** (HO; search-pause)
- Claim: Own lane of search: detected in every episode (any field), and for each rate in {0.05, 0.2, 1, 10} req/s the median earliest own fire lies inside the pooled sweep r3 min-max band: 0.05: 11.58-13.21 s; 0.2: 1.94-5.01 s; 1: 0.70-1.54 s; 10: 0.21-0.28 s. Other rates: `—`.
- Rule: hit iff 100 % detected and every present-rate median is inside its band. Applies only if the off-path run uses the sweep's workload and pause form; if its declaration differs the band rows are `—` and the detection clause alone is scored.
- Basis: research/lanes/out-pooled-20261014/POOLED.md:74-77
- Scoring: the Hotel off-path run's lane output (readout lanes block via research/lanes/pooled_lanes.py or its successor; file recorded in the run's commit); field `per-episode own lane ttdAny by rate (search-pause episodes)`

**HO-L2** (HO; consul-pause)
- Claim: Own silence of consul: `—`. consul is not among the 10 Jaeger-traced services, writes no log in the harness, and the ABox holds no `ops:emits` for it (own lane `no`), so no consul sensor is expected in the lanes block.
- Rule: `—` iff the lanes block has no armed consul own sensor; MISS iff an own-lane fire of a consul sensor is reported (then this build collects telemetry for consul and the `—` was wrong)
- Basis: research/ontology/runs/run2-20261014/PREDICTIONS.md CQ-S1 (Collector svc-jaeger: 10 members, consul absent); research/lanes/out-pooled-20261014/POOLED.md:5 (coordinator `—`: consul writes no log, structural absence)
- Scoring: the Hotel off-path run's lane output (readout lanes block via research/lanes/pooled_lanes.py or its successor; file recorded in the run's commit); field `lanes.own for target consul`

### Verdict expectations (stated, not tests)

**FR1-V1** (FR1; all)
- Claim: The frozen set `frontier (effort<=any, runtime<=any) @6/T_r` of this replicate contains >= 1 `metric:kafka:*` id (F: exactly one, kafka.consumer_group.lag, price 15.81/h; the 6/T_r budget is about 20/h).
- Rule: hit iff the set's sensors include >= 1 id starting `metric:kafka:`; the set's members are reported either way (not a pass criterion)
- Basis: research/placement/test-f/RESULT_F.md:21,23; research/placement/test-f/placement-f.json rates.25.costs (28 `metric:kafka:*` ids priced 9.99-20.99/h)
- Scoring: score_rep.py output of the replicate (research/placement/test-f-rep1/, `rates.25.verdicts[]`, `rates.25.sets[<set>].sensors`); field `rates.25.sets["frontier (effort<=any, runtime<=any) @6/T_r"].sensors`

**FR1-V2** (FR1; fraud-pause)
- Claim: fraud-pause-effect PASS under the frozen rule (g = D(ledger alone) - D(S) > 0 and >= 2 of the class's test episodes strictly improved; F: g = 42.05 s, 2 of 2 improved). Implied by F: the frozen set again holds a broker metric that fires 4.5-9.3 s after onset while the ledger alone fires in 1-2 of 4 off-path episodes.
- Rule: hit iff the scorer's verdict for class fraud-pause-effect is PASS; miss if FAIL; — if fewer than 2 valid test episodes. Weakest link: the strict-improvement count (a lag fire that is threshold-marginal, or a ledger fire first in an episode, gives < 2 of 2).
- Basis: research/placement/test-f/RESULT_F.md:18-19,29-34 (F verdicts and episodes); research/traffic-sweep/DECLARATION_F_OTEL.md:36-45 (pass rule)
- Scoring: score_rep.py output of the replicate (research/placement/test-f-rep1/, `rates.25.verdicts[]`, `rates.25.sets[<set>].sensors`); field `rates.25.verdicts[rule.class == fraud-pause-effect].verdict, .gE, .improved`

**FR1-V3** (FR1; accounting-pause)
- Claim: accounting-pause-effect PASS under the frozen rule (g = D(ledger alone) - D(S) > 0 and >= 2 of the class's test episodes strictly improved; F: g = 53.23 s, 2 of 2 improved). Implied by F: the frozen set again holds a broker metric that fires 4.5-9.3 s after onset while the ledger alone fires in 1-2 of 4 off-path episodes.
- Rule: hit iff the scorer's verdict for class accounting-pause-effect is PASS; miss if FAIL; — if fewer than 2 valid test episodes. Weakest link: the strict-improvement count (a lag fire that is threshold-marginal, or a ledger fire first in an episode, gives < 2 of 2).
- Basis: research/placement/test-f/RESULT_F.md:18-19,29-34 (F verdicts and episodes); research/traffic-sweep/DECLARATION_F_OTEL.md:36-45 (pass rule)
- Scoring: score_rep.py output of the replicate (research/placement/test-f-rep1/, `rates.25.verdicts[]`, `rates.25.sets[<set>].sensors`); field `rates.25.verdicts[rule.class == accounting-pause-effect].verdict, .gE, .improved`

**FR1-V4** (FR1; frontend-pause)
- Claim: On-path control: the frozen @6/T_r set improves 0 of 2 frontend test episodes (ledger first at about 0.3-0.4 s; F: g = 0). The frontend class has no pass rule; reported only.
- Rule: hit iff improved == 0 of 2 for class frontend-pause-effect in the scorer's per-episode rows; miss otherwise
- Basis: research/placement/test-f/RESULT_F.md:33-36; research/lanes/out-pooled-20261014/POOLED.md:84 (ledger 5/5 at 0.35 s)
- Scoring: score_rep.py output of the replicate (research/placement/test-f-rep1/, `rates.25.verdicts[]`, `rates.25.sets[<set>].sensors`); field `rates.25.episodes[class == frontend-pause-effect].sets[<@6/T_r set>].improvesOnLedger`

**FR1-V5** (FR1; no-fault)
- Claim: Fresh false alarms of the replicate's frozen @6/T_r set on its 4 held-out no-fault cells (0.20 h) do not exceed the rule's own budget: <= 4 alarms in total (20/h x 0.2 h). F: lag 0 alarms.
- Rule: hit iff the sum of `union of the sensor's 3 rules` alarms over the set's sensors <= 4; reported with the training honest bound
- Basis: research/placement/test-f/RESULT_F.md:76-80 (F: 0 alarms, bound 14.98/h); research/placement/test-f/fresh-fa/out/fresh_fa_f.json rows[]
- Scoring: fresh_fa_rep.py output (research/placement/test-f-rep1/fresh-fa-f2/, rows[] = {set, sensor, rule, alarms}); field `rows[rule == 'union of the sensor's 3 rules' and set == '@6/T_r'].alarms`

**FR2-V1** (FR2; all)
- Claim: The frozen set `frontier (effort<=any, runtime<=any) @6/T_r` of this replicate contains >= 1 `metric:kafka:*` id (F: exactly one, kafka.consumer_group.lag, price 15.81/h; the 6/T_r budget is about 20/h).
- Rule: hit iff the set's sensors include >= 1 id starting `metric:kafka:`; the set's members are reported either way (not a pass criterion)
- Basis: research/placement/test-f/RESULT_F.md:21,23; research/placement/test-f/placement-f.json rates.25.costs (28 `metric:kafka:*` ids priced 9.99-20.99/h)
- Scoring: the replicate's scorer output (`rates.25.verdicts[]`, `rates.25.sets[<set>].sensors`); field `rates.25.sets["frontier (effort<=any, runtime<=any) @6/T_r"].sensors`

**FR2-V2** (FR2; fraud-pause)
- Claim: fraud-pause-effect PASS under the frozen rule (g = D(ledger alone) - D(S) > 0 and >= 2 of the class's test episodes strictly improved; F: g = 42.05 s, 2 of 2 improved). Implied by F: the frozen set again holds a broker metric that fires 4.5-9.3 s after onset while the ledger alone fires in 1-2 of 4 off-path episodes.
- Rule: hit iff the scorer's verdict for class fraud-pause-effect is PASS; miss if FAIL; — if fewer than 2 valid test episodes. Weakest link: the strict-improvement count (a lag fire that is threshold-marginal, or a ledger fire first in an episode, gives < 2 of 2).
- Basis: research/placement/test-f/RESULT_F.md:18-19,29-34 (F verdicts and episodes); research/traffic-sweep/DECLARATION_F_OTEL.md:36-45 (pass rule)
- Scoring: the replicate's scorer output (`rates.25.verdicts[]`, `rates.25.sets[<set>].sensors`); field `rates.25.verdicts[rule.class == fraud-pause-effect].verdict, .gE, .improved`

**FR2-V3** (FR2; accounting-pause)
- Claim: accounting-pause-effect PASS under the frozen rule (g = D(ledger alone) - D(S) > 0 and >= 2 of the class's test episodes strictly improved; F: g = 53.23 s, 2 of 2 improved). Implied by F: the frozen set again holds a broker metric that fires 4.5-9.3 s after onset while the ledger alone fires in 1-2 of 4 off-path episodes.
- Rule: hit iff the scorer's verdict for class accounting-pause-effect is PASS; miss if FAIL; — if fewer than 2 valid test episodes. Weakest link: the strict-improvement count (a lag fire that is threshold-marginal, or a ledger fire first in an episode, gives < 2 of 2).
- Basis: research/placement/test-f/RESULT_F.md:18-19,29-34 (F verdicts and episodes); research/traffic-sweep/DECLARATION_F_OTEL.md:36-45 (pass rule)
- Scoring: the replicate's scorer output (`rates.25.verdicts[]`, `rates.25.sets[<set>].sensors`); field `rates.25.verdicts[rule.class == accounting-pause-effect].verdict, .gE, .improved`

**FR2-V4** (FR2; frontend-pause)
- Claim: On-path control: the frozen @6/T_r set improves 0 of 2 frontend test episodes (ledger first at about 0.3-0.4 s; F: g = 0). The frontend class has no pass rule; reported only.
- Rule: hit iff improved == 0 of 2 for class frontend-pause-effect in the scorer's per-episode rows; miss otherwise
- Basis: research/placement/test-f/RESULT_F.md:33-36; research/lanes/out-pooled-20261014/POOLED.md:84 (ledger 5/5 at 0.35 s)
- Scoring: the replicate's scorer output (`rates.25.verdicts[]`, `rates.25.sets[<set>].sensors`); field `rates.25.episodes[class == frontend-pause-effect].sets[<@6/T_r set>].improvesOnLedger`

**FR2-V5** (FR2; no-fault)
- Claim: Fresh false alarms of the replicate's frozen @6/T_r set on its 4 held-out no-fault cells (0.20 h) do not exceed the rule's own budget: <= 4 alarms in total (20/h x 0.2 h). F: lag 0 alarms.
- Rule: hit iff the sum of `union of the sensor's 3 rules` alarms over the set's sensors <= 4; reported with the training honest bound
- Basis: research/placement/test-f/RESULT_F.md:76-80 (F: 0 alarms, bound 14.98/h); research/placement/test-f/fresh-fa/out/fresh_fa_f.json rows[]
- Scoring: the replicate's fresh-FA output (rows[] = {set, sensor, rule, alarms}); field `rows[rule == 'union of the sensor's 3 rules' and set == '@6/T_r'].alarms`

**FNL-V1** (FNL; all)
- Claim: The frozen @6/T_r set contains `metric:kafka:kafka.request.count` (a non-lag broker metric). Reason: in F its price was 9.99/h (zero training alarms, i.e. the 2.996/T_r zero-alarm price at T_r = 0.30 h), it was the @3/T_r set in every effort tier, and without the lag sensor (15.81/h) the 20/h budget holds two 9.99/h sensors (2 x 9.986 = 19.97 <= 20.0).
- Rule: hit iff `metric:kafka:kafka.request.count` is in the set; the other members (up to two) are reported; miss if absent
- Basis: research/placement/test-f/RESULT_F.md:54-57; research/placement/test-f/placement-f.json rates.25.costs[metric:kafka:kafka.request.count] = 9.985774245179966, lag = 15.812881727968593; research/placement/test-f/RESULT_F.md:76-80 (fresh false alarms: request.count 2 in 0.2 h, upper bound 31.48/h vs training bound 9.99/h)
- Scoring: the F-nolag scorer output (`rates.25.verdicts[]`, `rates.25.sets[<set>].sensors`); field `rates.25.sets["frontier (effort<=any, runtime<=any) @6/T_r"].sensors`

**FNL-V2** (FNL; fraud-pause)
- Claim: fraud-pause-effect PASS under the frozen rule without the lag receiver (reviewer's post hoc on F: g 42.38, 2/2). Conditional on FNL-V1: if the set lacks a sensor that fires before the ledger, FAIL is the expectation.
- Rule: hit iff the scorer's verdict for fraud-pause-effect is PASS; miss if FAIL; — if < 2 valid episodes
- Basis: research/placement/test-f/RESULT_F.md:54-57 (request.count detects 6/6 test episodes, g 31.89; post hoc passes both classes)
- Scoring: the F-nolag scorer output (`rates.25.verdicts[]`, `rates.25.sets[<set>].sensors`); field `rates.25.verdicts[rule.class == fraud-pause-effect].verdict, .gE, .improved`

**FNL-V3** (FNL; accounting-pause)
- Claim: accounting-pause-effect PASS under the frozen rule without the lag receiver (reviewer's post hoc on F: g 53.28, 2/2). Conditional on FNL-V1: if the set lacks a sensor that fires before the ledger, FAIL is the expectation.
- Rule: hit iff the scorer's verdict for accounting-pause-effect is PASS; miss if FAIL; — if < 2 valid episodes
- Basis: research/placement/test-f/RESULT_F.md:54-57 (request.count detects 6/6 test episodes, g 31.89; post hoc passes both classes)
- Scoring: the F-nolag scorer output (`rates.25.verdicts[]`, `rates.25.sets[<set>].sensors`); field `rates.25.verdicts[rule.class == accounting-pause-effect].verdict, .gE, .improved`

**FNL-V4** (FNL; frontend-pause)
- Claim: On-path control: the frozen @6/T_r set improves 0 of 2 frontend test episodes (ledger first). Reported only.
- Rule: as FR1-V4
- Basis: research/placement/test-f/RESULT_F.md:33-36,54-57 (request.count g 31.89 over 6 episodes = 0 for the 2 frontend ones)
- Scoring: the F-nolag scorer output (`rates.25.verdicts[]`, `rates.25.sets[<set>].sensors`); field `rates.25.episodes[class == frontend-pause-effect].sets[<@6/T_r set>].improvesOnLedger`

**FNL-V5** (FNL; no-fault)
- Claim: Fresh false alarms of the F-nolag frozen @6/T_r set on its 4 held-out no-fault cells (0.20 h) are <= 4 in total (the 20/h budget x 0.2 h). The tier-0 broker metric exceeded its training price in F (2 alarms = 10/h vs 9.99/h), so a miss here is plausible and would be a finding about the price, not about the set's detection.
- Rule: hit iff summed union-of-rules alarms <= 4
- Basis: research/placement/test-f/RESULT_F.md:76-80
- Scoring: the F-nolag fresh-FA output (rows[] = {set, sensor, rule, alarms}); field `rows[rule == 'union of the sensor's 3 rules' and set == '@6/T_r'].alarms`

**TSR-C** (TSR; auth-freeze)
- Claim: On-path control: auth-freeze P1 holds in >= 9/10 episodes (r1: 10/10).
- Rule: hit iff predictions.P1 holds with k >= 9 of n = 10
- Basis: research/placement/test-ts-offpath/RESULT_TS_OFFPATH.md:21
- Scoring: the post hoc lane script's TeaStore output for this run (research/lanes/posthoc_lanes_v33.py teastore, new out dir) and its single-fetch v3.3 readout; field `predictions[id=T-C].numbers.{holds,k,n}`

### Traffic dependence

**TSR-D1** (TSR; auth-freeze)
- Claim: Own-silence traffic dependence: median own earliest fire at rate 10 <= 0.5 x median at rate 1, and max(rate 10) < min(rate 1) over the 5 + 5 auth-freeze episodes.
- Rule: hit iff both hold. Threshold 0.5: pooled ratio 0.32 (0.47/1.49 = 0.32, POOLED.md:204; per campaign B 0.48/1.50 = 0.32 at :143-144, C 0.45/1.49 = 0.30 at :151-152); ranges disjoint in the pool (0.45-0.52 vs 0.93-1.66).
- Basis: research/lanes/out-pooled-20261014/POOLED.md:91-92,204 (rho -0.88)
- Scoring: the post hoc lane script's TeaStore output for this run (research/lanes/posthoc_lanes_v33.py teastore, new out dir) and its single-fetch v3.3 readout; field `per-episode own lane ttdAny by rate`

**TSR-D2** (TSR; auth-freeze, recommender-pause)
- Claim: Coordinator times do not depend on rate: |median(rate 10) - median(rate 1)| <= 2.5 s and the two ranges overlap, separately for auth-freeze and recommender-pause (registry removal, either field).
- Rule: hit iff both clauses hold for both regimes. Threshold 2.5 s = one registry heartbeat / cleanup period (declaration basis); observed differences: auth pooled 1.21 s (10.20 vs 11.41, rho 0.07), recommender r1 0.54 s (9.70 vs 10.24).
- Basis: research/lanes/out-pooled-20261014/POOLED.md:92,205; research/lanes/out-ts-offpath-posthoc/posthoc_lanes_v33_teastore.json predictions[T-L2].numbers.episodes (r1 per-episode values); research/traffic-sweep/DECLARATION_TEASTORE_OFFPATH.md:27 (heartbeat 2.5 s, cleanup 2.5 s)
- Scoring: the post hoc lane script's TeaStore output for this run (research/lanes/posthoc_lanes_v33.py teastore, new out dir) and its single-fetch v3.3 readout; field `per-episode coordinator ttd by rate`

**TSR-D3** (TSR; auth-freeze)
- Claim: Ledger traffic dependence on the on-path control: median ledger earliest fire at rate 10 <= 0.5 x median at rate 1 (pooled 0.51 / 1.61 = 0.32).
- Rule: hit iff ratio <= 0.5
- Basis: research/lanes/out-pooled-20261014/POOLED.md:206
- Scoring: the post hoc lane script's TeaStore output for this run (research/lanes/posthoc_lanes_v33.py teastore, new out dir) and its single-fetch v3.3 readout; field `per-episode ledger lane ttdAny by rate`

**HO-D1** (HO; search-pause)
- Claim: Traffic dependence of search-pause, own and ledger lanes: for any two rates in the run with a gap >= 4x, median(higher rate) <= 0.5 x median(lower rate).
- Rule: hit iff every such pair satisfies the ratio, separately for own and ledger (any field). Threshold justification: pooled ratios 0.31-0.32 for 4-5x gaps (0.05 -> 0.2 -> 1) and 0.20 for 10x (own 11.76 -> 3.78 -> 1.19 -> 0.24; ledger 11.48 -> 4.77 -> 1.20 -> 0.25).
- Basis: research/lanes/out-pooled-20261014/POOLED.md:190-191 (rho -0.97 own, -0.92 ledger)
- Scoring: the Hotel off-path run's lane output (readout lanes block via research/lanes/pooled_lanes.py or its successor; file recorded in the run's commit); field `per-episode own and ledger ttdAny by rate`

**HO-D2** (HO; consul-pause)
- Claim: No traffic-dependence prediction for consul-pause: no own lane (HO-L2) and no coordinator (HO-C); the ledger effect of a consul pause is not predicted (`—`).
- Rule: `—`
- Basis: see HO-C, HO-L2
- Scoring: the Hotel off-path run's lane output (readout lanes block via research/lanes/pooled_lanes.py or its successor; file recorded in the run's commit); field `—`

