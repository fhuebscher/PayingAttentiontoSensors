# Campaign E test scoring (score-test-v3.6, scope instance)

System `teastore`; test blocks [4, 5]; training blocks [1, 2, 3]. Penalty `ttd` (a miss charged the hold); D and g_E in seconds; g_E = D_E(ledger alone) - D_E(S). Pass rule: decision 99 (V32_PASS_RULE in the registry, digest recorded).
Fresh false alarms of every frozen set: — (decision 88 analogue: fresh false alarms of the frozen sets on E's no-fault cells need a validated path; none exists).
Deviation: scored by restriction of `full` cells: a declared deviation from protocol §3 (:102), decision 80; decision 46.3's live run of the chosen placement is the later check.
Limitation: the scoring readout calibrates its detectors on the training blocks only (decision 102); exposure and the P1-P4 tables of the scoring readout still read every valid cell (report-only).

## r1

Test episodes: 4 (auth-freeze-effect 2, recommender-pause-effect 2). Ground set of the scoring readout: 461 sensors.

| set | size | absent from V_r | D_E(S) | D_E(ledger) | g_E | detected |
|---|---|---|---|---|---|---|
| frontier (effort<=0, runtime<=<1%) @0 | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=<1%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=<1%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=<1%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=<1%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=1-10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=1-10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=1-10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=1-10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=1-10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=>10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=>10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=>10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=>10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=>10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=any) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=any) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=any) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=any) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=any) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=<1%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=<1%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=<1%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=<1%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=<1%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=1-10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=1-10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=1-10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=1-10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=1-10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=>10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=>10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=>10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=>10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=>10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=any) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=any) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=any) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=any) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=any) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=<1%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=<1%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=<1%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=<1%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=<1%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=1-10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=1-10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=1-10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=1-10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=1-10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=>10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=>10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=>10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=>10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=>10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=any) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=any) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=any) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=any) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=any) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=<1%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=<1%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=<1%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=<1%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=<1%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=1-10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=1-10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=1-10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=1-10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=1-10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=>10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=>10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=>10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=>10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=>10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=any) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=any) @3/T_r | 1 | 0 | 6.309 | 30.580 | 24.271 | 4/4 |
| frontier (effort<=any, runtime<=any) @6/T_r (= frontier (effort<=any, runtime<=any) @3/T_r) | 1 | 0 | 6.309 | 30.580 | 24.271 | 4/4 |
| frontier (effort<=any, runtime<=any) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=any) @inf (= frontier (effort<=any, runtime<=any) @3/T_r) | 1 | 0 | 6.309 | 30.580 | 24.271 | 4/4 |
| ledger alone (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |
| full | 461 | 0 | 6.309 | 30.580 | 24.271 | 4/4 |
| out of the box (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.580 | 30.580 | 0.000 | 2/4 |

Verdicts (decision 99, per class; on-path classes carry none):

- `recommender-pause-effect` on `frontier (effort<=any, runtime<=any) @6/T_r`: **PASS** (g_E = 48.5421; improves 2 of 2 episodes); g over the class's 2 test episode(s) = 48.542.

## r10

Test episodes: 4 (auth-freeze-effect 2, recommender-pause-effect 2). Ground set of the scoring readout: 461 sensors.

| set | size | absent from V_r | D_E(S) | D_E(ledger) | g_E | detected |
|---|---|---|---|---|---|---|
| frontier (effort<=0, runtime<=<1%) @0 | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=<1%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=<1%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=<1%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=<1%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=1-10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=1-10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=1-10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=1-10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=1-10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=>10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=>10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=>10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=>10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=>10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=any) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=any) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=any) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=any) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=0, runtime<=any) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=<1%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=<1%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=<1%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=<1%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=<1%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=1-10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=1-10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=1-10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=1-10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=1-10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=>10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=>10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=>10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=>10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=>10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=any) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=any) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=any) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=any) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=1, runtime<=any) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=<1%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=<1%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=<1%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=<1%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=<1%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=1-10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=1-10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=1-10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=1-10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=1-10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=>10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=>10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=>10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=>10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=>10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=any) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=any) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=any) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=any) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=2, runtime<=any) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=<1%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=<1%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=<1%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=<1%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=<1%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=1-10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=1-10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=1-10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=1-10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=1-10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=>10%) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=>10%) @3/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=>10%) @6/T_r (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=>10%) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=>10%) @inf (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=any) @0 (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=any) @3/T_r | 1 | 0 | 5.894 | 30.301 | 24.407 | 4/4 |
| frontier (effort<=any, runtime<=any) @6/T_r (= frontier (effort<=any, runtime<=any) @3/T_r) | 1 | 0 | 5.894 | 30.301 | 24.407 | 4/4 |
| frontier (effort<=any, runtime<=any) @6/h (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| frontier (effort<=any, runtime<=any) @inf (= frontier (effort<=any, runtime<=any) @3/T_r) | 1 | 0 | 5.894 | 30.301 | 24.407 | 4/4 |
| ledger alone (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |
| full | 461 | 0 | 3.127 | 30.301 | 27.174 | 4/4 |
| out of the box (= frontier (effort<=0, runtime<=<1%) @0) | 0 | 0 | 30.301 | 30.301 | 0.000 | 2/4 |

Verdicts (decision 99, per class; on-path classes carry none):

- `recommender-pause-effect` on `frontier (effort<=any, runtime<=any) @6/T_r`: **PASS** (g_E = 48.8136; improves 2 of 2 episodes); g over the class's 2 test episode(s) = 48.814.

