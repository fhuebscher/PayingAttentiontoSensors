# FNL predictions scored (F no-lag ablation otel-offpath-f-nolag-v1; instance scope)

Rules: each prediction's own `rule` field in `research/protocol/PREDICTIONS_OVERNIGHT_20261014.json` (`8b89d43`); the ontology items by `research/ontology/compare.py`.
Inputs: committed outputs only (digests in the json). The ablation launched after `8b89d43` (01:53:28Z, 2026-10-15).

| id | verdict | basis |
|---|---|---|
| FNL-ONT-fraud | see items below | |
| FNL-ONT-accounting | see items below | |
| FNL-ONT-frontend | see items below | |
| FNL-L1 | hit | `{"k": 4, "n": 4, "ttd": [["fraud-pause-effect", 4, 0.550076961517334, "by-construction"], ["fraud-pause-effect", 5, 1.064805030822754, "by-construction"], ["accounting-pause-effect", 4, 0.6387114524841309, "by-construction"], ["accounting-pause-effect", 5, 0.8292624950408936, "by-construction"]]}` |
| FNL-L2 | hit | `{"countedTtd": [["fraud-pause-effect", 4, 43.07908034324646], ["fraud-pause-effect", 5, 43.12495970726013], ["accounting-pause-effect", 4, 43.87255644798279], ["accounting-pause-effect", 5, 43.627784729003906]], "frontendNoFireEitherField": true, "offpathInWindow": 4}` |
| FNL-L3 | - | `{"armed": 0, "lagIdsInCalibration": 0}` |
| FNL-M | hit | `{"placeableNonFlagdSdk": 231, "placeableNonFlagdSpanmetrics": 44}` |
| FNL-V1 | hit | `{"sensors": ["metric:kafka:kafka.request.count"], "set": "frontier (effort<=any, runtime<=any) @6/T_r", "size": 1}` |
| FNL-V2 | hit | `{"episodesInPool": 2, "gE": 51.143910240381956, "improved": 2, "verdict": "PASS"}` |
| FNL-V3 | hit | `{"episodesInPool": 2, "gE": 51.0597237162292, "improved": 2, "verdict": "PASS"}` |
| FNL-V4 | hit | `{"improved": 0, "of": 2}` |
| FNL-V5 | hit | `{"ablationOwnSet": [["metric:kafka:kafka.request.count", 0, 0.2, 15.812881727968593, 14.978661367769948]], "totalAlarms": 0}` |

### FNL-ONT-fraud

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | 2/2 (counted 0) 0.55-1.06 s | disagree |  |
| lane:coordinator | yes | 2/2 (counted 2) 43.08-43.12 s | agree |  |
| lane:lag | no | — | not comparable |  |
| CQ-C1 class | tracked | coordinator fired | agree | from the coordinator lane (no class table for this campaign) |
| CQ-L2 window | [45.0, 45.0] | [43.08, 43.12] | disagree | range is the any-field earliest per episode; counted-only range [43.08, 43.12] |
| CQ-B1 entry reached (proxy: ledger lane) | no | 1/2 (counted 1) 54.87-54.87 s | disagree |  |

### FNL-ONT-accounting

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | 2/2 (counted 0) 0.64-0.83 s | disagree |  |
| lane:coordinator | yes | 2/2 (counted 2) 43.63-43.87 s | agree |  |
| lane:lag | no | — | not comparable |  |
| CQ-C1 class | tracked | coordinator fired | agree | from the coordinator lane (no class table for this campaign) |
| CQ-L2 window | [45.0, 45.0] | [43.63, 43.87] | disagree | range is the any-field earliest per episode; counted-only range [43.63, 43.87] |
| CQ-B1 entry reached (proxy: ledger lane) | no | 0/2 (counted 0) | agree |  |

### FNL-ONT-frontend

| item | predicted | measured | verdict | note |
|---|---|---|---|---|
| lane:own | no | — | not comparable |  |
| lane:coordinator | no | 0/2 (counted 0) | agree |  |
| lane:lag | no | — | not comparable |  |
| CQ-C1 class | not-a-member | coordinator silent | agree | from the coordinator lane (no class table for this campaign) |
| CQ-L2 window | — | — | agree | no predicted window; coordinator silent |
| CQ-B1 entry reached (proxy: ledger lane) | yes | 2/2 (counted 2) 0.40-0.48 s | agree |  |
