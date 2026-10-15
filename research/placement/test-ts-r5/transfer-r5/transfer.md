# Transfer of frozen sets (POST HOC to the sets; instance)

Readout `research/traffic-sweep/readout-teastore-offpath-r5-score-v3.6/sweep_analysis_v3_6.json` (sha256 `41bf1c39471e12f7347f2626bf0e42e0c8540d4726c903c298e5d768385f2c4a`); test blocks [4, 5]; point 6/T_r; rule registry `research/protocol/parameters_v3_6.json` sha256 `68f417c53599b52401e6a33d30d0d45215bf8a349182f84171b2691cf9424428` (pin `68f417c53599b52401e6a33d30d0d45215bf8a349182f84171b2691cf9424428`).

| placement | rate | members | class | improved | g (s) | verdict | reason | absent members |
|---|---|---|---|---|---|---|---|---|
| research/placement/test-ts-placement/placement-rep3r1.json | 1 | log:webui:d4d75ec135e6 | recommender-pause-effect | 2/2 | 48.542 | PASS | g_E = 48.5421; improves 2 of 2 episodes | none |
| research/placement/test-ts-placement/placement-rep3r1.json | 10 | span:auth:BCryptProvider.checkPassword | recommender-pause-effect | 1/2 | 29.787 | FAIL | improves 1 of 2 episodes (< 2) | none |
