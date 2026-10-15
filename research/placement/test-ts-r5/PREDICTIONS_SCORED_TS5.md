# R5 predictions scored (instance)

Counted: 6 hit, 0 miss, 0 undecided, of 6.

| id | result | counted | numbers |
|---|---|---|---|
| TS5-V1 | hit | yes | `{"gE": 48.5420863814652, "improved": 2, "rate": "1", "verdict": "PASS"}` |
| TS5-V10 | hit | yes | `{"gE": 48.81357361096889, "improved": 2, "rate": "10", "verdict": "PASS"}` |
| TS5-S | hit | yes | `{"sets": {"1": ["log:webui:d4d75ec135e6"], "10": ["log:webui:d4d75ec135e6"]}}` |
| TS5-T1 | hit | yes | `{"absentFromScoringGroundSet": {}, "episodesInPool": 2, "improved": 2, "members": ["log:webui:d4d75ec135e6"], "rate": "1", "verdict": "PASS"}` |
| TS5-T10 | hit | yes | `{"absentFromScoringGroundSet": {}, "episodesInPool": 2, "improved": 1, "members": ["span:auth:BCryptProvider.checkPassword"], "rate": "10", "verdict": "FAIL"}` |
| TS5-L | hit | no (check, not counted (true by construction if no request in the window touches recommender)) | `{"ledgerMissed": 4, "recEpisodes": 4}` |
| TS5-C | hit | yes | `{"authEpisodes": 4, "ledgerDetected": 4}` |
