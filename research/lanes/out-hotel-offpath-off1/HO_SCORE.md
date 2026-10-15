# Hotel off-path predictions HO-*, scored by score_ho_v34.py

**POST-READING SCORE of preregistered predictions (committed 8b89d43 before any hotel-offpath cell was read); rules applied by code (score_ho_v34.py), rule pins checked.** Scope: instance.

Episodes: 20 (consul-pause-effect r1 5, consul-pause-effect r10 5, search-pause-effect r1 5, search-pause-effect r10 5). Declared 5 per (regime, rate); shortfall: none.

| id | verdict | evidence |
|---|---|---|
| HO-ONT-search | per item | lane:own: disagree; lane:coordinator: not comparable; lane:lag: not comparable; CQ-C1 class: not comparable; CQ-L2 window: not comparable; CQ-B1 entry reached (proxy: ledger lane): agree |
| | | label: compare.py's rules (a lane is detected if any episode fires in any field); Hotel has no coordinator, so the coordinator-based items are not comparable; a lane:own `disagree` whose measuredOwn.counted is 0 rests on by-construction fires only (the paused target's own idle signal), not on a counted detection |
| HO-ONT-consul | per item | lane:own: disagree; lane:coordinator: not comparable; lane:lag: not comparable; CQ-C1 class: not comparable; CQ-L2 window: not comparable; CQ-B1 entry reached (proxy: ledger lane): agree |
| | | label: compare.py's rules (a lane is detected if any episode fires in any field); Hotel has no coordinator, so the coordinator-based items are not comparable; a lane:own `disagree` whose measuredOwn.counted is 0 rests on by-construction fires only (the paused target's own idle signal), not on a counted detection |
| HO-C | hit (by construction) | `{"coordinatorLaneInPooledLanes": "none (Hotel: structural)", "coordinatorOrLagFiresInAnyEpisode": [], "episodes": 20, "lagLane": "none"}` |
| | | label: true by construction of the lane rules (V34_LANE_RULES declares no coordinator or lag lane for Hotel); a hit is the rule's, not a measurement that no service observes consul |
| HO-L1 | hit | `{"detectedInEveryEpisode": true, "perRate": {"1": {"band": [0.7, 1.54], "detected": 5, "episodes": 5, "inside": true, "median": 0.7851135730743408}, "10": {"band": [0.21, 0.28], "detected": 5, "episodes": 5, "inside": true, "median": 0.23223280906677246}}, "ratesWithoutBand": []}` |
| | | label: bands apply because candidate_offpath.py reads the sweep's workload and pause form (judgement recorded in the docstring) |
| HO-L2 | miss (counted field) | `{"armedOwnSensors": ["metric:consul:cpu", "metric:consul:sys_cpu", "metric:consul:sys_io", "metric:consul:sys_memory", "metric:consul:sys_psi_cpu"], "earliestOwnFire": 1.8139829635620117, "episodes": 10, "episodesWithCountedOwnFire": 5, "episodesWithOwnFire": 10, "ownCollectedSensorsPerEpisode": [7, 7, 7, 7, 7, 7, 7, 7, 7, 7], "ownFiringIds": ["metric:consul:cpu", "metric:consul:sys_cpu", "metric:consul:sys_psi_cpu"]}` |
| HO-D1 | hit | `{"ledger": [{"holds": true, "medians": {"1.0": 0.7974880784749985, "10.0": 0.24273593723773956}, "pair": [1.0, 10.0], "ratio": 0.30437563117170713}], "own": [{"holds": true, "medians": {"1.0": 0.7851135730743408, "10.0": 0.23223280906677246}, "pair": [1.0, 10.0], "ratio": 0.29579517796055577}]}` |
| HO-D2 | — | `{"reason": "the rule is `\u2014`: no prediction"}` |
