# R6 predictions scored (instance)

Counted: 5 hit, 0 miss, 0 undecided, of 5.

| id | result | counted | numbers |
|---|---|---|---|
| FR6-V1 | hit | yes | `{"accounting-pause-effect": "PASS", "fraud-pause-effect": "PASS"}` |
| FR6-V2 | hit | yes | `{"set": ["metric:kafka:kafka.consumer_group.lag"]}` |
| FR6-L1 | hit | yes | `{"ledgerDetected": 0, "offPathEpisodes": 4}` |
| FR6-C | hit | no (control check, not counted) | `{"frontendEpisodes": 2, "gFrontend": 0.0, "ledgerTtd": [0.4197833612561226, 0.34646791219711304], "setTtd": [0.4197833612561226, 0.34646791219711304]}` |
| TR6-LAG | hit | yes | `{"accounting-pause-effect": "PASS", "fraud-pause-effect": "PASS", "placementSha256": "ce6bfc1b9addbb1771b189c9330b1930f0d84c9890c1fd8d8e8cae0978d20a3d"}` |
| TR6-R2 | hit | no (reported, not counted (not independent of TR6-LAG)) | `{"accounting-pause-effect": "PASS", "fraud-pause-effect": "PASS", "placementSha256": "633b89f1beea3b6896488aa41de82983ac84c80d2230a768938190f0d181e560"}` |
| TR6-PUR | hit | yes | `{"accounting-pause-effect": "FAIL", "fraud-pause-effect": "FAIL", "placementSha256": "674580e08353e667ea32d587091fc38327db6d68e1d3f2142fdd94c9e433b606"}` |
