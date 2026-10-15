# posthoc-lanes-v33: TeaStore lane rows (POST HOC (not a preregistered verdict; written under FREEZE_V33_20261014.md addendum, condition 2), scope instance)

Readout `research/traffic-sweep/readout-teastore-offpath-rep2-v3.3/sweep_analysis_v3_3.json`; regime `recommender-pause-effect`. Condition 1: campaignsRead ['tmp/teastore-offpath-evidence/rep2-fetch/x/teastore-offpath-v1'], setup ID(s) ['cbe9920a4b95f47d60054186641e754c'].

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

- `runs/recommender-pause-effect/b01-06-full` rate 10 block 1: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 12.471067667007446, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 12.471067667007446}}
- `runs/recommender-pause-effect/b02-03-full` rate 10 block 2: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 9.278493642807007, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 9.278493642807007}}
- `runs/recommender-pause-effect/b03-06-full` rate 10 block 3: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 9.480126857757568, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 9.480126857757568}}
- `runs/recommender-pause-effect/b04-06-full` rate 10 block 4: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 9.09001111984253, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 9.09001111984253}}
- `runs/recommender-pause-effect/b05-05-full` rate 10 block 5: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 10.399309396743774, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 10.399309396743774}}
- `runs/recommender-pause-effect/b01-02-full` rate 1 block 1: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 11.759441137313843, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 11.759441137313843}}
- `runs/recommender-pause-effect/b02-02-full` rate 1 block 2: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 9.268453359603882, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 9.268453359603882}}
- `runs/recommender-pause-effect/b03-03-full` rate 1 block 3: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 9.118203401565552, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 9.118203401565552}}
- `runs/recommender-pause-effect/b04-02-full` rate 1 block 4: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 11.808310270309448, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 11.808310270309448}}
- `runs/recommender-pause-effect/b05-03-full` rate 1 block 5: {"allCoordinatorFires": 1, "applicationLogRemovalLine": {"lagSeconds": 10.336305141448975, "present": true}, "inWindow": true, "inWindowFire": {"bcFlags": ["BC-caller-log"], "field": "by-construction", "rule": "appear", "sensor": "log:registry:c2797874a226", "ttd": 10.336305141448975}}

### T-OFF per episode

- `runs/recommender-pause-effect/b01-06-full` rate 10 block 1: {"hold": 60.20585365220904, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 602, "okAtLeast95": true, "onset": 60.133664190769196, "share": 1.0, "started": 602}
- `runs/recommender-pause-effect/b02-03-full` rate 10 block 2: {"hold": 60.23261050879955, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 603, "okAtLeast95": true, "onset": 60.17310709506273, "share": 1.0, "started": 603}
- `runs/recommender-pause-effect/b03-06-full` rate 10 block 3: {"hold": 60.24593281559646, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 603, "okAtLeast95": true, "onset": 60.08761664107442, "share": 1.0, "started": 603}
- `runs/recommender-pause-effect/b04-06-full` rate 10 block 4: {"hold": 60.2145434319973, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 603, "okAtLeast95": true, "onset": 60.094609601423144, "share": 1.0, "started": 603}
- `runs/recommender-pause-effect/b05-05-full` rate 10 block 5: {"hold": 60.25415066629648, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 603, "okAtLeast95": true, "onset": 60.09515977837145, "share": 1.0, "started": 603}
- `runs/recommender-pause-effect/b01-02-full` rate 1 block 1: {"hold": 60.233772434294224, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 60, "okAtLeast95": true, "onset": 60.54117574170232, "share": 1.0, "started": 60}
- `runs/recommender-pause-effect/b02-02-full` rate 1 block 2: {"hold": 60.24665980786085, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 61, "okAtLeast95": true, "onset": 60.886578591540456, "share": 1.0, "started": 61}
- `runs/recommender-pause-effect/b03-03-full` rate 1 block 3: {"hold": 60.21420170366764, "ledgerFiresAny": 1, "ledgerFiresCounted": 1, "ok": 60, "okAtLeast95": true, "onset": 60.293958868831396, "share": 1.0, "started": 60}
- `runs/recommender-pause-effect/b04-02-full` rate 1 block 4: {"hold": 60.24268068931997, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 61, "okAtLeast95": true, "onset": 60.861975986510515, "share": 1.0, "started": 61}
- `runs/recommender-pause-effect/b05-03-full` rate 1 block 5: {"hold": 60.22290027141571, "ledgerFiresAny": 0, "ledgerFiresCounted": 0, "ok": 60, "okAtLeast95": true, "onset": 60.04780251905322, "share": 1.0, "started": 60}

