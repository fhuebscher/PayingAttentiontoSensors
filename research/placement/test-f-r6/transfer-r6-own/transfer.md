# Transfer of frozen sets (POST HOC to the sets; instance)

Readout `research/traffic-sweep/readout-otel-r6-score-v3.3/sweep_analysis_v3_3.json` (sha256 `13d7d5d5468e93b62b88e0c8e9c3789039cf088fdd38fd0f9af76fdf9f4b4fdf`); test blocks [4, 5]; point 6/T_r; rule registry `research/protocol/parameters_v3_2.json` sha256 `ab4a5af7243e776f536b09a39e649b1be968d23f1767ef2f5a166ac08e340a67` (pin `ab4a5af7243e776f536b09a39e649b1be968d23f1767ef2f5a166ac08e340a67`).

| placement | rate | members | class | improved | g (s) | verdict | reason | absent members |
|---|---|---|---|---|---|---|---|---|
| research/placement/test-f-r6/placement-r6.json | 25 | metric:kafka:kafka.consumer_group.lag | fraud-pause-effect | 2/2 | 55.813 | PASS | g_E = 55.8128; improves 2 of 2 episodes | none |
| research/placement/test-f-r6/placement-r6.json | 25 | metric:kafka:kafka.consumer_group.lag | accounting-pause-effect | 2/2 | 55.721 | PASS | g_E = 55.721; improves 2 of 2 episodes | none |
