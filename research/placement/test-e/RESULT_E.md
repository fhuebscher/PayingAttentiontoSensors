# Campaign E (OTel off-path faults): result (2026-10-13)

Scope: **instance** (OTel Demo 1.12.0, fb14srv6, 25 req/s of the upstream mix, 5 blocks, n = 2 test episodes per class).

- Declaration `research/traffic-sweep/DECLARATION_E_OTEL.md` (`49e47a1`, amendments `c785354`, `ef64d3b`); budget `BUDGET_E.md`
  (amendments 1-2); decisions 99-102, 110-112. Harness `6a5c2a9`, plan `503bf014`.
- Run: launcher started 2026-10-13 03:37:40Z, host unit started 03:43:15Z, terminal 05:35:08Z, 20/20 valid; fetched 357/357 byte-verified; offline replay pass 20/20 (`61131be`).
- Analysis v3.2 frozen before any E cell was read (`05f70d4`, record `research/protocol/FREEZE_V32_20261013.md`); training readout twice with
  identical calibration (only the first run's output is kept), placement pinned (`40209da`); scoring readout and scorer output committed unedited before reading (`e2cbc74`).

## Verdicts (the preregistered rule)

| class | set | verdict |
|---|---|---|
| frauddetectionservice pause | `frontier (effort<=any, runtime<=any) @6/T_r` | **FAIL** (g = 0, 0 of 2 test episodes improved) |
| accountingservice pause | same | **FAIL** (g = 0, 0 of 2 improved) |

The frozen set has one sensor, `metric:flagd:http.server.duration~rate` (19.97/h = 2.996/T_r, T_r = 0.15 h from 3 training no-fault cells).
Its training gain (14.25 s per episode over 9 training episodes) came from two fraud episodes and one accounting episode; in the frontend class
the ledger fires first (0.3-0.4 s). The three sibling flagd metrics fire at the same instant and add nothing, so the second 6/T_r slot stayed
empty. On the test blocks the sensor has no counted fire in any off-path episode (a `spike` at 15.3 s in fraud block 4 is discarded by the
spike path rule).

## What the test blocks show (post hoc, reported without a verdict)

Detection time in seconds after the pause command's pre-command stamp (`otel-e.json`, `rates.25.episodes`; "miss" = no counted fire in the 60 s hold):

| test episode | ledger alone | frozen set @6/T_r | set @inf (4 sensors) | `full` (4,417) |
|---|---|---|---|---|
| accounting, block 4 | miss | miss | 44.3 | 3.8 |
| accounting, block 5 | miss | miss | 44.1 | 3.4 |
| fraud, block 4 | miss | miss | 43.9 | 2.3 |
| fraud, block 5 | 20.2 | 20.2 | 20.2 | 0.3 |
| frontend, block 4 | 0.4 | 0.4 | 0.4 | 0.4 |
| frontend, block 5 | 0.3 | 0.3 | 0.3 | 0.3 |

- The request ledger misses 3 of the 4 off-path test episodes; it catches every frontend pause within 0.5 s.
- The `inf` set (`metric:flagd:http.server.duration~rate`, `log:kafka:28ec81d9cba3`, `log:kafka:8f9d8866e174`,
  `log:recommendationservice:271a57397c88`) catches 3 of the 4 off-path test episodes through its Kafka ids (43.9-44.3 s); in fraud block 5 the
  ledger catches first (20.2 s) and the Kafka ids fire at 43.4 s. Decision 111 predicted "about 43-44 s" before launch from pilot v2. The Kafka
  ids are three group-coordinator log templates per consumer (member failed, rebalance, group empty) firing within ~2 ms of each other, at
  43.4-44.3 s in 4/4 off-path test episodes. This is about which lane sees the fault and when; `inf` has no budget and no verdict.
- `full` (every placeable sensor of the training ground set: 4,417 of 8,935 calibrated ids; ledger included) detects within 4 s: in three
  off-path episodes through per-line recommendationservice `appear` ids with no honest bound (fill-priced), in fraud block 5 through a
  cartservice span `median` bounded at 31.6/h. It is a comparator, not a placement.
- Own-exclusion (decision 84/111) applies to every row, `inf` and `full` included. Without it the target's own `orders_receive` span `absent`
  fires at 1.0-1.5 s in all four off-path test episodes.
- Episodes: 6 test (2 per class, incl. the on-path frontend control), 9 training; 5 no-fault cells, of which the 3 training ones calibrate.

## Why the rule could not use the Kafka lane (mechanism in the code, checked post hoc)

The recurrence filter (decision 112) kept 19 sensors, including all six Kafka group-coordinator ids (3 templates per off-path class, the same
ids as in pilot v2). Those ids never occur in a no-fault cell, so the reader evaluates them in **0** leave-one-out folds (`foldsEvaluated 0`, no honest bound;
`readout-otel-e-train-v3.2`, `calibration.primary.perRate.25.sensors`). Decision 73 then charges them the rate's largest evidenced upper bound, **183.07/h** (the largest bound among the 669
evidenced sensors of V_r, set by one sensor with 4 alarms in one 0.05 h fold; `celf_v3.py:231`), which does not fit in the 20.03/h left beside a 19.97/h sensor under 6/T_r = 40/h. 3,748 of the 4,417 candidates
(85 %) carry that fill price. Decision 112 sized the two slots for zero-alarm sensors evaluated in every training fold; Amendment 1 (F6) named
the risk that a sensor evaluated in fewer folds costs more, but nobody checked the Kafka ids against it, although both pilot v2 shakedown
readouts already showed `foldsEvaluated 0` for them. The rule was frozen as written and the result above is its result.

Other causes, each sufficient for at least one verdict on its own:
- **Fraud would FAIL with a Kafka sensor in the set:** in fraud block 5 the ledger fires at 20.2 s, before the Kafka ids (43.4 s); improvement is
  strict, so that episode cannot improve and 1 of 2 < 2 (stated before the freeze in Amendment 2). Only the accounting class could have passed
  through the Kafka lane.
- **Two slots hold at most one Kafka id here:** the flagd sensor takes the first slot (gain 14.25); one Kafka id would fit beside it at 19.97/h,
  and the two classes' ids are disjoint.
- **The pick did not reproduce:** the flagd sensor had counted fires in 3 of 6 off-path training episodes and 0 of 4 off-path test episodes.
- The ledger fired in 1 of 4 off-path test and 2 of 6 off-path training episodes (route spikes at 20-46 s); fault effect or ledger noise
  cannot be told apart at n = 1 each, and the strict improvement over the ledger makes a 44 s lane depend on there being no earlier ledger spike.

## What this does and does not say
- It does **not** say off-path faults are invisible to a placed sensor: a broker-side log line detects them at about 44 s in 4/4 test episodes.
- Under decision 73 a sensor that never produces a record in a no-fault cell is unevaluated and priced at the rate's largest evidenced bound
  (183.07/h); the six Kafka ids are among the 3,748 such candidates, so none fits in the 20.03/h left at 6/T_r. More no-fault time of this
  kind would not change that: the reader arms an `appear` rule only in cells where the id has a record. Separately, the fraud class would
  have failed with a Kafka sensor in the set, and two slots could hold one Kafka id at most.
- n = 2 test episodes per class (6 in total), 0.15 h of training no-fault time, one host, one rate, one SUT.

Reviewed by a same-provider adversarial subagent (Fable 5.1, 2026-10-13): every number re-derived and supported; three sentences refuted and
replaced here (the flagd sensor's training gain, the launch time, the binding constraint). A cross-provider check is still owed (judge server
not connected).
