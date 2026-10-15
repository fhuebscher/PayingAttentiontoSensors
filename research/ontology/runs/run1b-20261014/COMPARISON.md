# Ontology predictions vs measurements, run1b-20261014

**POST HOC: every compared campaign was read before these predictions were made.** Scope: instance. Predictions: PREDICTIONS.json (committed before this comparison). Rules: `research/ontology/compare.py` docstring (lane = detected in >= 1 episode, any field; CQ-B1 compared with the request-ledger lane as a proxy for entry-service impact). Disagreements are listed and not fixed.

What the ABoxes contain, from the run's own files (no reading of cause is offered): no `ops:emits` fact was accepted for any row target except Hotel profile (emits were accepted for 7 non-target services; the fixed prompt does not ask for sensors) and no `ops:measuresLagOf` fact at all, so the own and lag lanes are predicted `no` almost everywhere; no accepted liveness record carries `failureTimeoutSeconds` (the SHACL violations of TeaStore and Hotel); the TeaStore registry record and one of the two Hotel consul records carry `healthCheckConfigured false`; OTel has no accepted Kafka coordinator (`final_spec.json` rebuild log: coordinator kafka missing name and type), so no OTel CQ-L2 row exists.

## Summary (items over the 14 rows)

| item | agree | partial | disagree | not predicted | not comparable |
|---|---|---|---|---|---|
| lane:own | 1 | 0 | 11 | 0 | 2 |
| lane:coordinator | 3 | 0 | 7 | 0 | 4 |
| lane:lag | 2 | 0 | 3 | 0 | 9 |
| CQ-C1 class | 1 | 0 | 9 | 0 | 4 |
| CQ-L2 window | 3 | 0 | 0 | 7 | 4 |
| CQ-B1 entry reached | 11 | 0 | 3 | 0 | 0 |
| CQ-S1 shared fate | 0 | 0 | 0 | 0 | 14 |

## Per row

### 1. hotel cpu-throttle on profile (pooled), POST HOC

Measured from: pooled.json `pooled` rows hotel/cpu-throttle summed over rates

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | yes | 12/16 (counted 6) 0.07-27.02 s | agree |  |
| lane:coordinator | no | — | not comparable |  |
| lane:lag | no | — | not comparable |  |
| CQ-C1 class | no-liveness-check | a 16 | not comparable | measured class map: {"null": 16} |
| CQ-L2 window | — | — | not comparable |  |
| CQ-B1 entry reached (proxy: ledger lane) | yes | 3/16 (counted 3) 7.91-30.30 s | agree | blast radius frontend |
| CQ-S1 shared fate | see PREDICTIONS.md | — | not comparable | no campaign measures shared fate |

### 2. hotel net-delay on rate (pooled), POST HOC

Measured from: pooled.json `pooled` rows hotel/net-delay summed over rates

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | 16/16 (counted 16) 0.14-9.94 s | disagree |  |
| lane:coordinator | no | — | not comparable |  |
| lane:lag | no | — | not comparable |  |
| CQ-C1 class | no-liveness-check | a 16 | not comparable | measured class map: {"null": 16} |
| CQ-L2 window | — | — | not comparable |  |
| CQ-B1 entry reached (proxy: ledger lane) | yes | 16/16 (counted 16) 0.14-19.61 s | agree | blast radius frontend, search |
| CQ-S1 shared fate | see PREDICTIONS.md | — | not comparable | no campaign measures shared fate |

### 3. hotel search-pause on search (pooled), POST HOC

Measured from: pooled.json `pooled` rows hotel/search-pause summed over rates

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | 16/16 (counted 4) 0.21-13.21 s | disagree |  |
| lane:coordinator | no | — | not comparable |  |
| lane:lag | no | — | not comparable |  |
| CQ-C1 class | no-liveness-check | a 16 | not comparable | measured class map: {"null": 16} |
| CQ-L2 window | — | — | not comparable |  |
| CQ-B1 entry reached (proxy: ledger lane) | yes | 16/16 (counted 0) 0.22-18.66 s | agree | blast radius frontend |
| CQ-S1 shared fate | see PREDICTIONS.md | — | not comparable | no campaign measures shared fate |

### 4. otel accounting-pause on accountingservice (pooled), POST HOC

Measured from: pooled.json `pooled` rows otel/accounting-pause summed over rates

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | 5/5 (counted 0) 0.88-1.51 s | disagree |  |
| lane:coordinator | no | 5/5 (counted 5) 43.71-44.32 s | disagree |  |
| lane:lag | no | — | not comparable |  |
| CQ-C1 class | no-coordinator | hit-counted 5 | disagree | measured class map: {"tracked": 5} |
| CQ-L2 window | — | [43.71, 44.32] | not predicted | no predicted window; coordinator fired |
| CQ-B1 entry reached (proxy: ledger lane) | no | 1/5 (counted 1) 37.19-37.19 s | disagree | blast radius group-accountingservice |
| CQ-S1 shared fate | see PREDICTIONS.md | — | not comparable | no campaign measures shared fate |

### 5. otel fraud-pause on frauddetectionservice (pooled), POST HOC

Measured from: pooled.json `pooled` rows otel/fraud-pause summed over rates

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | 5/5 (counted 0) 1.15-1.55 s | disagree |  |
| lane:coordinator | no | 5/5 (counted 5) 43.37-43.94 s | disagree |  |
| lane:lag | no | — | not comparable |  |
| CQ-C1 class | no-coordinator | hit-counted 5 | disagree | measured class map: {"tracked": 5} |
| CQ-L2 window | — | [43.37, 43.94] | not predicted | no predicted window; coordinator fired |
| CQ-B1 entry reached (proxy: ledger lane) | no | 2/5 (counted 2) 20.25-45.58 s | disagree | blast radius group-frauddetectionservice |
| CQ-S1 shared fate | see PREDICTIONS.md | — | not comparable | no campaign measures shared fate |

### 6. otel frontend-pause on frontend (pooled), POST HOC

Measured from: pooled.json `pooled` rows otel/frontend-pause summed over rates

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | 33/33 (counted 13) 0.29-27.97 s | disagree |  |
| lane:coordinator | no | 0/33 (counted 0) | agree |  |
| lane:lag | no | 0/28 (counted 0) | agree |  |
| CQ-C1 class | no-coordinator | c 33 | disagree | measured class map: {"not-a-member": 33} |
| CQ-L2 window | — | — | agree | no predicted window; coordinator silent |
| CQ-B1 entry reached (proxy: ledger lane) | yes | 33/33 (counted 0) 0.29-27.98 s | agree | blast radius frontendproxy, grafana, jaeger, loadgenerator, otelcol, prometheus |
| CQ-S1 shared fate | see PREDICTIONS.md | — | not comparable | no campaign measures shared fate |

### 7. otel productcatalog-cpu-throttle on productcatalogservice (pooled), POST HOC

Measured from: pooled.json `pooled` rows otel/productcatalog-cpu-throttle summed over rates

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | 3/28 (counted 3) 0.21-58.96 s | disagree |  |
| lane:coordinator | no | 0/28 (counted 0) | agree |  |
| lane:lag | no | 0/28 (counted 0) | agree |  |
| CQ-C1 class | no-coordinator | c 28 | disagree | measured class map: {"not-a-member": 28} |
| CQ-L2 window | — | — | agree | no predicted window; coordinator silent |
| CQ-B1 entry reached (proxy: ledger lane) | yes | 1/28 (counted 1) 58.98-58.98 s | agree | blast radius accountingservice, checkoutservice, frauddetectionservice, frontend, frontendproxy, grafana, jaeger, loadgenerator, otelcol, prometheus, recommendationservice |
| CQ-S1 shared fate | see PREDICTIONS.md | — | not comparable | no campaign measures shared fate |

### 8. teastore auth-freeze on auth (pooled), POST HOC

Measured from: pooled.json `pooled` rows teastore/auth-freeze summed over rates

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | 28/28 (counted 14) 0.45-18.37 s | disagree |  |
| lane:coordinator | no | 28/28 (counted 0) 9.07-11.75 s | disagree |  |
| lane:lag | no | — | not comparable |  |
| CQ-C1 class | no-liveness-check | d 28 | disagree | measured class map: {"tracked": 28} |
| CQ-L2 window | — | [9.07, 11.75] | not predicted | no predicted window; coordinator fired |
| CQ-B1 entry reached (proxy: ledger lane) | yes | 28/28 (counted 0) 0.48-18.44 s | agree | blast radius webui |
| CQ-S1 shared fate | see PREDICTIONS.md | — | not comparable | no campaign measures shared fate |

### 9. teastore persistence-cpu-throttle on persistence (pooled), POST HOC

Measured from: pooled.json `pooled` rows teastore/persistence-cpu-throttle summed over rates

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | 28/28 (counted 28) 0.26-5.53 s | disagree |  |
| lane:coordinator | no | 14/28 (counted 12) 17.56-59.05 s | disagree |  |
| lane:lag | no | — | not comparable |  |
| CQ-C1 class | no-liveness-check | d 2, hit-counted 12, b 14 | disagree | measured class map: {"tracked": 14, "heartbeat-stays-alive": 14} |
| CQ-L2 window | — | [17.56, 59.05] | not predicted | no predicted window; coordinator fired |
| CQ-B1 entry reached (proxy: ledger lane) | yes | 28/28 (counted 28) 0.23-57.41 s | agree | blast radius auth, image, persistence, recommender, webui |
| CQ-S1 shared fate | see PREDICTIONS.md | — | not comparable | no campaign measures shared fate |

### 10. otel fraud-pause on frauddetectionservice (campaign F), POST HOC

Measured from: per item

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | 2/2 (counted 0) 0.84-1.52 s | disagree | research/placement/test-f/RESULT_F.md:42 (F-L1, 4/4 over both classes, BC field) |
| lane:coordinator | no | 2/2 (counted 2) 43.30-44.00 s | disagree | research/placement/test-f/RESULT_F.md:43 (F-L2, 4/4 over both classes, counted) |
| lane:lag | no | 2/2 (counted 2) 4.80-9.30 s | disagree | research/placement/test-f/RESULT_F.md:31-32 (fraud blocks 4, 5) |
| CQ-C1 class | no-coordinator | coordinator fired | disagree | from the coordinator lane (no class table for this campaign) |
| CQ-L2 window | — | [43.3, 44.0] | not predicted | no predicted window; coordinator fired |
| CQ-B1 entry reached (proxy: ledger lane) | no | 1/2 (counted 1) 38.10-38.10 s | disagree | blast radius group-frauddetectionservice |
| CQ-S1 shared fate | see PREDICTIONS.md | — | not comparable | no campaign measures shared fate |

### 11. otel accounting-pause on accountingservice (campaign F), POST HOC

Measured from: per item

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | 2/2 (counted 0) 0.84-1.52 s | disagree | research/placement/test-f/RESULT_F.md:42 (F-L1, 4/4 over both classes, BC field) |
| lane:coordinator | no | 2/2 (counted 2) 43.30-44.00 s | disagree | research/placement/test-f/RESULT_F.md:43 (F-L2, 4/4 over both classes, counted) |
| lane:lag | no | 2/2 (counted 2) 4.50-9.20 s | disagree | research/placement/test-f/RESULT_F.md:29-30 (accounting blocks 4, 5) |
| CQ-C1 class | no-coordinator | coordinator fired | disagree | from the coordinator lane (no class table for this campaign) |
| CQ-L2 window | — | [43.3, 44.0] | not predicted | no predicted window; coordinator fired |
| CQ-B1 entry reached (proxy: ledger lane) | no | 0/2 (counted 0) | agree | blast radius group-accountingservice |
| CQ-S1 shared fate | see PREDICTIONS.md | — | not comparable | no campaign measures shared fate |

### 12. otel frontend-pause on frontend (campaign F), POST HOC

Measured from: per item

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | — | not comparable |  |
| lane:coordinator | no | 0/2 (counted 0) | agree | research/placement/test-f/RESULT_F.md:43 (frontend none in either field) |
| lane:lag | no | 2/2 (counted 2) 14.60-14.60 s | disagree | research/placement/test-f/RESULT_F.md:36 (lag fires at 14.6 s) |
| CQ-C1 class | no-coordinator | coordinator silent | agree | from the coordinator lane (no class table for this campaign) |
| CQ-L2 window | — | — | agree | no predicted window; coordinator silent |
| CQ-B1 entry reached (proxy: ledger lane) | yes | 2/2 (counted 2) 0.30-0.40 s | agree | blast radius frontendproxy, grafana, jaeger, loadgenerator, otelcol, prometheus |
| CQ-S1 shared fate | see PREDICTIONS.md | — | not comparable | no campaign measures shared fate |

### 13. teastore recommender-pause on recommender (TeaStore off-path), POST HOC

Measured from: per item

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | 5/10 (counted 5) 14.86-14.92 s | disagree | research/placement/test-ts-offpath/RESULT_TS_OFFPATH.md:19 (5/5 rate 10, none at rate 1) |
| lane:coordinator | no | 10/10 (counted 0) 8.37-12.03 s | disagree | research/placement/test-ts-offpath/RESULT_TS_OFFPATH.md:18 (T-L2, BC field) |
| lane:lag | no | — | not comparable |  |
| CQ-C1 class | no-liveness-check | coordinator fired | disagree | from the coordinator lane (no class table for this campaign) |
| CQ-L2 window | — | [8.37, 12.03] | not predicted | no predicted window; coordinator fired |
| CQ-B1 entry reached (proxy: ledger lane) | yes | 1/10 (counted 1) 5.07-5.07 s | agree | blast radius recommender, webui |
| CQ-S1 shared fate | see PREDICTIONS.md | — | not comparable | no campaign measures shared fate |

### 14. teastore auth-freeze on auth (TeaStore off-path), POST HOC

Measured from: per item

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | — | not comparable |  |
| lane:coordinator | no | — | not comparable |  |
| lane:lag | no | — | not comparable |  |
| CQ-C1 class | no-liveness-check | — | not comparable |  |
| CQ-L2 window | — | — | not comparable |  |
| CQ-B1 entry reached (proxy: ledger lane) | yes | 10/10 | agree | blast radius webui |
| CQ-S1 shared fate | see PREDICTIONS.md | — | not comparable | no campaign measures shared fate |

## Disagreements and non-predictions

- row 2 hotel net-delay, lane:own: predicted no, measured 16/16 (counted 16) 0.14-9.94 s (disagree)
- row 3 hotel search-pause, lane:own: predicted no, measured 16/16 (counted 4) 0.21-13.21 s (disagree)
- row 4 otel accounting-pause, lane:own: predicted no, measured 5/5 (counted 0) 0.88-1.51 s (disagree)
- row 4 otel accounting-pause, lane:coordinator: predicted no, measured 5/5 (counted 5) 43.71-44.32 s (disagree)
- row 4 otel accounting-pause, CQ-C1 class: predicted no-coordinator, measured hit-counted 5 (disagree)
- row 4 otel accounting-pause, CQ-L2 window: predicted —, measured [43.71, 44.32] (not predicted)
- row 4 otel accounting-pause, CQ-B1 entry reached (proxy: ledger lane): predicted no, measured 1/5 (counted 1) 37.19-37.19 s (disagree)
- row 5 otel fraud-pause, lane:own: predicted no, measured 5/5 (counted 0) 1.15-1.55 s (disagree)
- row 5 otel fraud-pause, lane:coordinator: predicted no, measured 5/5 (counted 5) 43.37-43.94 s (disagree)
- row 5 otel fraud-pause, CQ-C1 class: predicted no-coordinator, measured hit-counted 5 (disagree)
- row 5 otel fraud-pause, CQ-L2 window: predicted —, measured [43.37, 43.94] (not predicted)
- row 5 otel fraud-pause, CQ-B1 entry reached (proxy: ledger lane): predicted no, measured 2/5 (counted 2) 20.25-45.58 s (disagree)
- row 6 otel frontend-pause, lane:own: predicted no, measured 33/33 (counted 13) 0.29-27.97 s (disagree)
- row 6 otel frontend-pause, CQ-C1 class: predicted no-coordinator, measured c 33 (disagree)
- row 7 otel productcatalog-cpu-throttle, lane:own: predicted no, measured 3/28 (counted 3) 0.21-58.96 s (disagree)
- row 7 otel productcatalog-cpu-throttle, CQ-C1 class: predicted no-coordinator, measured c 28 (disagree)
- row 8 teastore auth-freeze, lane:own: predicted no, measured 28/28 (counted 14) 0.45-18.37 s (disagree)
- row 8 teastore auth-freeze, lane:coordinator: predicted no, measured 28/28 (counted 0) 9.07-11.75 s (disagree)
- row 8 teastore auth-freeze, CQ-C1 class: predicted no-liveness-check, measured d 28 (disagree)
- row 8 teastore auth-freeze, CQ-L2 window: predicted —, measured [9.07, 11.75] (not predicted)
- row 9 teastore persistence-cpu-throttle, lane:own: predicted no, measured 28/28 (counted 28) 0.26-5.53 s (disagree)
- row 9 teastore persistence-cpu-throttle, lane:coordinator: predicted no, measured 14/28 (counted 12) 17.56-59.05 s (disagree)
- row 9 teastore persistence-cpu-throttle, CQ-C1 class: predicted no-liveness-check, measured d 2, hit-counted 12, b 14 (disagree)
- row 9 teastore persistence-cpu-throttle, CQ-L2 window: predicted —, measured [17.56, 59.05] (not predicted)
- row 10 otel fraud-pause, lane:own: predicted no, measured 2/2 (counted 0) 0.84-1.52 s (disagree)
- row 10 otel fraud-pause, lane:coordinator: predicted no, measured 2/2 (counted 2) 43.30-44.00 s (disagree)
- row 10 otel fraud-pause, lane:lag: predicted no, measured 2/2 (counted 2) 4.80-9.30 s (disagree)
- row 10 otel fraud-pause, CQ-C1 class: predicted no-coordinator, measured coordinator fired (disagree)
- row 10 otel fraud-pause, CQ-L2 window: predicted —, measured [43.3, 44.0] (not predicted)
- row 10 otel fraud-pause, CQ-B1 entry reached (proxy: ledger lane): predicted no, measured 1/2 (counted 1) 38.10-38.10 s (disagree)
- row 11 otel accounting-pause, lane:own: predicted no, measured 2/2 (counted 0) 0.84-1.52 s (disagree)
- row 11 otel accounting-pause, lane:coordinator: predicted no, measured 2/2 (counted 2) 43.30-44.00 s (disagree)
- row 11 otel accounting-pause, lane:lag: predicted no, measured 2/2 (counted 2) 4.50-9.20 s (disagree)
- row 11 otel accounting-pause, CQ-C1 class: predicted no-coordinator, measured coordinator fired (disagree)
- row 11 otel accounting-pause, CQ-L2 window: predicted —, measured [43.3, 44.0] (not predicted)
- row 12 otel frontend-pause, lane:lag: predicted no, measured 2/2 (counted 2) 14.60-14.60 s (disagree)
- row 13 teastore recommender-pause, lane:own: predicted no, measured 5/10 (counted 5) 14.86-14.92 s (disagree)
- row 13 teastore recommender-pause, lane:coordinator: predicted no, measured 10/10 (counted 0) 8.37-12.03 s (disagree)
- row 13 teastore recommender-pause, CQ-C1 class: predicted no-liveness-check, measured coordinator fired (disagree)
- row 13 teastore recommender-pause, CQ-L2 window: predicted —, measured [8.37, 12.03] (not predicted)
