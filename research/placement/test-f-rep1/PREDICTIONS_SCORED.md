# FR1 predictions scored (F replication 1, attempt 3; instance scope)

Rules: each prediction's own `rule` field in `research/protocol/PREDICTIONS_OVERNIGHT_20261014.json` (`8b89d43`); the ontology items by `research/ontology/compare.py`.
Inputs: committed outputs only (digests in the json). Attempt 3 launched after `8b89d43`; attempt 2 launched before it and is not read.

| id | verdict | basis |
|---|---|---|
| FR1-ONT-fraud | see items below | |
| FR1-ONT-accounting | see items below | |
| FR1-ONT-frontend | see items below | |
| FR1-L1 | hit | `{"k": 4, "n": 4, "ttd": [["fraud-pause-effect", 4, 1.1542789936065674, "by-construction"], ["fraud-pause-effect", 5, 1.1767044067382812, "by-construction"], ["accounting-pause-effect", 4, 0.9527275562286377, "by-construction"], ["accounting-pause-effect", 5, 1.0007774829864502, "by-construction"]]}` |
| FR1-L2 | hit | `{"countedTtd": [["fraud-pause-effect", 4, 42.93950295448303], ["fraud-pause-effect", 5, 43.325910568237305], ["accounting-pause-effect", 4, 43.77522873878479], ["accounting-pause-effect", 5, 43.79254627227783]], "frontendNoFireEitherField": true, "offpathInWindow": 4}` |
| FR1-L3 | hit | `{"additionallyStated_lagInBand_3_15": "4/4", "armed": 2, "armedIds": ["metric:kafka:kafka.consumer_group.lag", "metric:kafka:kafka.consumer_group.lag_sum"], "lagBeforeCoordinator": 4, "lagFireSeconds": [8.902467727661133, 9.39865779876709, 4.377531051635742, 9.287614583969116], "n": 4}` |
| FR1-M | hit | `{"placeableNonFlagdSdk": 236, "placeableNonFlagdSpanmetrics": 44}` |
| FR1-V1 | hit | `{"sensors": ["metric:kafka:kafka.purgatory.size"], "set": "frontier (effort<=any, runtime<=any) @6/T_r", "size": 1}` |
| FR1-V2 | hit | `{"episodesInPool": 2, "gE": 53.654993411153555, "improved": 2, "verdict": "PASS"}` |
| FR1-V3 | hit | `{"episodesInPool": 2, "gE": 58.546938721090555, "improved": 2, "verdict": "PASS"}` |
| FR1-V4 | hit | `{"improved": 0, "of": 2}` |
| FR1-V5 | hit | `{"fSetOnReplicateCells": [["metric:kafka:kafka.consumer_group.lag", 0, 0.2, 35.04344969580511, 14.978661367769948]], "replicateOwnSet": [["metric:kafka:kafka.purgatory.size", 1, 0.2, 9.985774245179966, 23.71932259195289]], "totalAlarms": 1}` |

### FR1-ONT-fraud

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | 2/2 (counted 0) 1.15-1.18 s | disagree |  |
| lane:coordinator | yes | 2/2 (counted 2) 42.94-43.33 s | agree |  |
| lane:lag | no | 2/2 (counted 2) 8.90-9.40 s | disagree |  |
| CQ-C1 class | tracked | coordinator fired | agree | from the coordinator lane (no class table for this campaign) |
| CQ-L2 window | [45.0, 45.0] | [42.94, 43.33] | disagree | range is the any-field earliest per episode; counted-only range [42.94, 43.33] |
| CQ-B1 entry reached (proxy: ledger lane) | no | 0/2 (counted 0) | agree |  |

### FR1-ONT-accounting

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | 2/2 (counted 0) 0.95-1.00 s | disagree |  |
| lane:coordinator | yes | 2/2 (counted 2) 26.00-43.78 s | agree |  |
| lane:lag | no | 2/2 (counted 2) 4.38-9.29 s | disagree |  |
| CQ-C1 class | tracked | coordinator fired | agree | from the coordinator lane (no class table for this campaign) |
| CQ-L2 window | [45.0, 45.0] | [26.0, 43.78] | disagree | range is the any-field earliest per episode; counted-only range [43.78, 43.79] |
| CQ-B1 entry reached (proxy: ledger lane) | no | 0/2 (counted 0) | agree |  |

### FR1-ONT-frontend

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | — | not comparable |  |
| lane:coordinator | no | 0/2 (counted 0) | agree |  |
| lane:lag | no | — | not comparable |  |
| CQ-C1 class | not-a-member | coordinator silent | agree | from the coordinator lane (no class table for this campaign) |
| CQ-L2 window | — | — | agree | no predicted window; coordinator silent |
| CQ-B1 entry reached (proxy: ledger lane) | yes | 2/2 (counted 2) 0.37-0.40 s | agree |  |
