# posthoc-lanes-v33: TeaStore lane rows (POST HOC (not a preregistered verdict; written under FREEZE_V33_20261014.md addendum, condition 2), scope instance)

Readout `research/traffic-sweep/readout-teastore-offpath-r1-v3.3/sweep_analysis_v3_3.json`; regime `recommender-pause-effect`. Condition 1: campaignsRead ['tmp/teastore-offpath-evidence/r1-fetch/x/teastore-offpath-v1'], setup ID(s) ['def272fd4c9050f8226b88d756115e79'].

No pass or fail rule is applied; hit / miss / `—` is a report.

| id | result | reason | key numbers |
|---|---|---|---|
| T-L1 | **miss** | 10 episodes of recommender-pause-effect (declared 10) | {"k": 0, "n": 10, "need": 9} |
| T-L2 | **hit** | 10 episodes of recommender-pause-effect (declared 10) | {"k": 10, "n": 10, "need": 9} |
| T-OFF | **miss** | 10 episodes of recommender-pause-effect (declared 10) | {"noCountedLedgerFireClause": false, "okShareClause": {"k": 10, "minShare": 0.95, "n": 10, "need": 9}} |
| T-C | **hit** | predictions.P1 over the readout's auth-freeze episodes | {"holds": true, "k": 10, "n": 10} |

### T-L1 per episode

- `runs/recommender-pause-effect/b01-06-full` rate 10 block 1: {"below5s": false, "earliest": null}
- `runs/recommender-pause-effect/b02-03-full` rate 10 block 2: {"below5s": false, "earliest": null}
- `runs/recommender-pause-effect/b03-06-full` rate 10 block 3: {"below5s": false, "earliest": null}
- `runs/recommender-pause-effect/b04-06-full` rate 10 block 4: {"below5s": false, "earliest": null}
- `runs/recommender-pause-effect/b05-05-full` rate 10 block 5: {"below5s": false, "earliest": null}
- `runs/recommender-pause-effect/b01-02-full` rate 1 block 1: {"below5s": false, "earliest": null}
- `runs/recommender-pause-effect/b02-02-full` rate 1 block 2: {"below5s": false, "earliest": null}
- `runs/recommender-pause-effect/b03-03-full` rate 1 block 3: {"below5s": false, "earliest": null}
- `runs/recommender-pause-effect/b04-02-full` rate 1 block 4: {"below5s": false, "earliest": null}
- `runs/recommender-pause-effect/b05-03-full` rate 1 block 5: {"below5s": false, "earliest": null}

Sampler caveat: system-samples.json is a cgroup v2 sampler every 5 s (teastore_samples): a fire is stamped at a sample time, 0-5 s after the command, so '< 5 s' can fail on sampling phase alone; the actual times are listed, none is rounded to the sampler period

### T-L2 per episode

- `runs/recommender-pause-effect/b01-06-full` rate 10 block 1: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 9.075531482696533, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 9.075531482696533}}
- `runs/recommender-pause-effect/b02-03-full` rate 10 block 2: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 12.033676624298096, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 12.033676624298096}}
- `runs/recommender-pause-effect/b03-06-full` rate 10 block 3: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 9.695236206054688, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 9.695236206054688}}
- `runs/recommender-pause-effect/b04-06-full` rate 10 block 4: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 9.833694458007812, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 9.833694458007812}}
- `runs/recommender-pause-effect/b05-05-full` rate 10 block 5: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 8.37147331237793, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 8.37147331237793}}
- `runs/recommender-pause-effect/b01-02-full` rate 1 block 1: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 10.531571865081787, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 10.531571865081787}}
- `runs/recommender-pause-effect/b02-02-full` rate 1 block 2: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 11.3147451877594, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 11.3147451877594}}
- `runs/recommender-pause-effect/b03-03-full` rate 1 block 3: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 10.218829870223999, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 10.218829870223999}}
- `runs/recommender-pause-effect/b04-02-full` rate 1 block 4: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 10.235307931900024, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 10.235307931900024}}
- `runs/recommender-pause-effect/b05-03-full` rate 1 block 5: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 9.45079779624939, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 9.45079779624939}}

### T-OFF per episode

- `runs/recommender-pause-effect/b01-06-full` rate 10 block 1: {"hold": 60.244275748729706, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 603, "okAtLeast95": true, "onset": 60.095990646630526, "share": 1.0, "started": 603}
- `runs/recommender-pause-effect/b02-03-full` rate 10 block 2: {"hold": 60.261658541858196, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 603, "okAtLeast95": true, "onset": 60.159168023616076, "share": 1.0, "started": 603}
- `runs/recommender-pause-effect/b03-06-full` rate 10 block 3: {"hold": 60.253619000315666, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 603, "okAtLeast95": true, "onset": 60.096531042829156, "share": 1.0, "started": 603}
- `runs/recommender-pause-effect/b04-06-full` rate 10 block 4: {"hold": 60.24582777917385, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 603, "okAtLeast95": true, "onset": 60.09462065808475, "share": 1.0, "started": 603}
- `runs/recommender-pause-effect/b05-05-full` rate 10 block 5: {"hold": 60.23428736999631, "ledgerFiresAny": 1, "ledgerFiresCounted": 1, "ok": 603, "okAtLeast95": true, "onset": 60.09766282513738, "share": 1.0, "started": 603}
- `runs/recommender-pause-effect/b01-02-full` rate 1 block 1: {"hold": 60.22537409886718, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 60, "okAtLeast95": true, "onset": 60.54121242277324, "share": 1.0, "started": 60}
- `runs/recommender-pause-effect/b02-02-full` rate 1 block 2: {"hold": 60.24664454907179, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 61, "okAtLeast95": true, "onset": 60.81711121276021, "share": 1.0, "started": 61}
- `runs/recommender-pause-effect/b03-03-full` rate 1 block 3: {"hold": 60.24481004849076, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 60, "okAtLeast95": true, "onset": 60.24701574072242, "share": 1.0, "started": 60}
- `runs/recommender-pause-effect/b04-02-full` rate 1 block 4: {"hold": 60.22141055762768, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 61, "okAtLeast95": true, "onset": 60.861927431076765, "share": 1.0, "started": 61}
- `runs/recommender-pause-effect/b05-03-full` rate 1 block 5: {"hold": 60.212895501405, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 60, "okAtLeast95": true, "onset": 60.063556587323546, "share": 1.0, "started": 60}

