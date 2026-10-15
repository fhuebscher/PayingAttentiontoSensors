# Campaign C test result (2026-10-12; numbers from ac3845a)

Review: Fable adversarial-review subagent, same-provider (the cross-provider judge server is down); nothing blocking,
should-fix items S1-S5 and notes N1-N2 applied in this revision. Scope: instance (OTel on fb14srv6, TeaStore on fb14srv5).
Inputs: frozen placements 378e598, frozen scorer 1a8d924, C readouts 720957c (decision 92, freeze record be3a7f1).
D = mean penalised time to detection over C's 6 episodes per rate (3 blocks x 2 fault classes), a miss charged the hold
(~60 s). g_C = D_C(ledger alone) - D_C(S).

Comparators: `full` = the frozen training ground set V_r (trace, log and metric sensors placeable at that rate in
training), scored by restriction of full-posture cells; it is not every sensor C's readout has (1079 vs 1137 at OTel
r0.2). `none` (782) and `selected` (927) are restriction estimates (decision 78), their sensors outside training V_r
dropped; `none` is not an empty set.

## Decision 89 verdict (OTel r0.2, frozen 6/h set `span:frontend:GET`): FAIL, and it stands
- g_C = 0.000 s (D_C 32.601 for the set and for the ledger); the set improves 0 of 3 CPU-throttle episodes (rule: >= 2).
- Decisions 90/91 do not apply: the member is placeable in C's readout (calibration entry identical to training's) and
  all 3 throttle episodes are valid. No decision gives `—` for "no set detects the class"; treating it so would be post hoc.
- Training prediction: 19.4 s, the mean of B folds 27.1 / 24.9 / 25.7 and the sweep fold 0; every fold chose the same
  set, so held-out equals in-sample here. In training the set caught 3 of 4 throttle episodes, all in B, the ledger none.
- At r0.2 every scored set, `full` included, misses all 3 throttle episodes (each 60.06 s = the hold). In C's readout two
  of the three episodes have no fire from any sensor; the third has one off-path, uncounted fire (a Kafka JVM metric at
  58.4 s). Pause episodes are caught by the ledger (4.1-6.1 s) and no set is earlier.

## What is checked, what is open (exploratory, under no protocol decision)
- Pooling C did not change this detector on B: `span:frontend:GET`'s fires on B's three r0.2 throttle episodes are
  identical in the training and C readouts (5.822 / 10.242 / 8.681 s), and its calibration entry is identical.
- The throttle was applied: every C throttle cell's `intervention.json` records `manifested` and `recovered`; at r0.2 the
  applied limit is 0.1 core, as in B.
- Counted on-path fires on throttle episodes, B vs C: r0.05 0/3 vs 0/3; r0.2 3/3 vs 0/3; r1 0/3 vs 1/3 (at 58.98 s of a
  60.06 s hold, shared by the ledger and every set); r10 1/3 vs 0/3. Within B the pattern the prediction rested on
  appeared at r0.2 only, so C is a failure to replicate a single-rate pattern.
- Open: why the same throttle gave no on-path fire in C. C differs from B in harness commit (8018a19 vs c4aa313), onsets
  and block orders; these are differences, not an explanation.

## Everywhere else (reported, no verdict: decision 89 adopted the sign rule only at OTel r0.2)
| SUT | rate | g_C frozen 6/h set (s) | g_C `full` (s) | training prediction, fold mean [fold range] |
|---|---|---|---|---|
| OTel | r10 | 0.000 | 0.000 | 0.0 |
| OTel | r1 | 0.000 | 0.000 (0.0004) | 0.0 |
| OTel | r0.2 | 0.000 | 0.000 | 19.4 |
| OTel | r0.05 | 0.000 | 1.594 | 0.6 |
| TeaStore | r10 | 0.053 | 0.053 | 0.019 [0, 0.063] |
| TeaStore | r1 | 0.083 | 0.083 | 0.030 [0, 0.100] |
| TeaStore | r0.2 | 1.691 (`metric:rabbitmq:sys_cpu`) | 1.692 | 0.0002 [0, 0.00075] |
| TeaStore | r0.05 | 1.796 | 1.961 | 0.018 [0, 0.039] |
- TeaStore: the ledger detects 6/6 at every rate; the frozen 6/h set (1-2 sensors) is within 0.17 s of `full` at every
  rate. At r10 and r1 the C gains sit inside the training fold range; at r0.2 and r0.05 they are far above it. The
  scoring draft said a no-gain prediction is contradicted "only by a large g_C" without quantifying "large", and
  decision 89 defines no verdict here, so these are reported, not judged. The gains are concentrated: r0.2's 1.691 is
  one throttle episode (b03, 21.922 -> 11.778 s); at r0.05 one auth-freeze and one throttle episode carry most of it.
  `none` gains the same (1.691 at r0.2, 1.933 at r0.05), so the gain is not attributable to traces.
- OTel r0.05: `full`, `selected`, the unlimited set and the modality-T 6/h set (`span:frontendproxy:router_frontend_egress`)
  gain 1.594 s from 2 of 3 pause episodes; the frozen 6/h set (a frontendproxy log template) gains 0. The 0.6 prediction
  came entirely from the sweep fold, which chose that span; the log template's B folds were 0 / 0 / 0, as in C.
- Fresh false alarms of the frozen sets on C's no-fault cells: `—` (decision 88, no validated path).

## Limitations to carry
- n = 3 episodes per class and rate; one host per SUT; host confounded with SUT.
- C's fault cells contribute pre-onset segments to the pooled fit (decision 88, declared; N5 in be3a7f1).
- Scored by restriction of `full` cells (decision 80), not a live run of the chosen placement.
