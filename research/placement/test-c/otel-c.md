# Campaign C test scoring (score-test-v3.1, scope instance)

System `otel`; campaign index 4 (`tmp/c-fault-copy/otel`), C's episodes only. Penalty `ttd` (a miss charged the hold); D and g_C in seconds; g_C = D_C(ledger alone) - D_C(S).
Fresh false alarms of every frozen set on C's no-fault cells: — (decision 88: fresh false alarms of the frozen sets on C's no-fault cells need a validated path; the frozen v3.1 --validation accepts P4-shaped sets only, so none exists).
Deviation: scored by restriction of `full` cells: a declared deviation from protocol §3 (:102), decision 80; decision 46.3's live run of the chosen placement is the later check.

## r0.05

C episodes: 6 (frontend-pause-effect 3, productcatalog-cpu-throttle-effect 3). Ground set of the C readout: 1110 sensors.

| set | sensors | absent from C's V_r | D_C(S) | D_C(ledger) | g_C | detected | verdict (decision 89) |
|---|---|---|---|---|---|---|---|
| primary 0 | (none) | 0 | 40.185 | 40.185 | 0.000 | 3/6 | — |
| primary 3/T_r | log:frontendproxy:5eaff2aaa577 | 0 | 40.185 | 40.185 | 0.000 | 3/6 | — |
| primary 6/h | log:frontendproxy:5eaff2aaa577 | 0 | 40.185 | 40.185 | 0.000 | 3/6 | — |
| primary inf | log:frontendproxy:5da27c0ea977, log:frontendproxy:5eaff2aaa577, span:frontendproxy:router_frontend_egress | 0 | 38.591 | 40.185 | 1.594 | 3/6 | — |
| ledger alone | (none) | 0 | 40.185 | 40.185 | 0.000 | 3/6 | — |
| full | V_r frozen (1077) | 0 | 38.591 | 40.185 | 1.594 | 3/6 | — |
| none | 780 sensors | 0 | 40.185 | 40.185 | 0.000 | 3/6 | — |
| selected | 925 sensors | 0 | 38.591 | 40.185 | 1.594 | 3/6 | — |
| modality T 6/h | span:frontendproxy:router_frontend_egress | 0 | 38.591 | 40.185 | 1.594 | 3/6 | — |
| modality T+L 6/h | log:frontendproxy:5eaff2aaa577 | 0 | 40.185 | 40.185 | 0.000 | 3/6 | — |

Per episode, penalised seconds (`*` = strictly earlier than the ledger):

| episode | class | block | ledger | primary 0 | primary 3/T_r | primary 6/h | primary inf | full | none | selected | modality T 6/h | modality T+L 6/h |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/frontend-pause/r0p05-b01-11-full | frontend-pause-effect | 1 | 24.176 | 24.176 | 24.176 | 24.176 | 19.504* | 19.504* | 24.176 | 19.504* | 19.504* | 24.176 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/frontend-pause/r0p05-b02-02-full | frontend-pause-effect | 2 | 15.703 | 15.703 | 15.703 | 15.703 | 15.703 | 15.703 | 15.703 | 15.703 | 15.703 | 15.703 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/frontend-pause/r0p05-b03-10-full | frontend-pause-effect | 3 | 21.123 | 21.123 | 21.123 | 21.123 | 16.232* | 16.232* | 21.123 | 16.232* | 16.232* | 21.123 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/productcatalog-cpu-throttle/r0p05-b01-09-full | productcatalog-cpu-throttle-effect | 1 | 60.030 | 60.030 | 60.030 | 60.030 | 60.030 | 60.030 | 60.030 | 60.030 | 60.030 | 60.030 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/productcatalog-cpu-throttle/r0p05-b02-06-full | productcatalog-cpu-throttle-effect | 2 | 60.022 | 60.022 | 60.022 | 60.022 | 60.022 | 60.022 | 60.022 | 60.022 | 60.022 | 60.022 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/productcatalog-cpu-throttle/r0p05-b03-02-full | productcatalog-cpu-throttle-effect | 3 | 60.054 | 60.054 | 60.054 | 60.054 | 60.054 | 60.054 | 60.054 | 60.054 | 60.054 | 60.054 |

## r0.2

C episodes: 6 (frontend-pause-effect 3, productcatalog-cpu-throttle-effect 3). Ground set of the C readout: 1137 sensors.

| set | sensors | absent from C's V_r | D_C(S) | D_C(ledger) | g_C | detected | verdict (decision 89) |
|---|---|---|---|---|---|---|---|
| primary 0 | (none) | 0 | 32.601 | 32.601 | 0.000 | 3/6 | — |
| primary 3/T_r | log:frontendproxy:5eaff2aaa577 | 0 | 32.601 | 32.601 | 0.000 | 3/6 | — |
| primary 6/h | span:frontend:GET | 0 | 32.601 | 32.601 | 0.000 | 3/6 | **FAIL**: g_C = 0 <= 0; improves 0 of 3 throttle episodes (< 2) |
| primary inf | log:frontendproxy:5eaff2aaa577, span:frontend:GET | 0 | 32.601 | 32.601 | 0.000 | 3/6 | — |
| ledger alone | (none) | 0 | 32.601 | 32.601 | 0.000 | 3/6 | — |
| full | V_r frozen (1079) | 0 | 32.601 | 32.601 | 0.000 | 3/6 | — |
| none | 782 sensors | 0 | 32.601 | 32.601 | 0.000 | 3/6 | — |
| selected | 927 sensors | 0 | 32.601 | 32.601 | 0.000 | 3/6 | — |
| modality T 6/h | span:frontend:GET | 0 | 32.601 | 32.601 | 0.000 | 3/6 | — |
| modality T+L 6/h | span:frontend:GET | 0 | 32.601 | 32.601 | 0.000 | 3/6 | — |

Per episode, penalised seconds (`*` = strictly earlier than the ledger):

| episode | class | block | ledger | primary 0 | primary 3/T_r | primary 6/h | primary inf | full | none | selected | modality T 6/h | modality T+L 6/h |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/frontend-pause/r0p2-b01-01-full | frontend-pause-effect | 1 | 6.072 | 6.072 | 6.072 | 6.072 | 6.072 | 6.072 | 6.072 | 6.072 | 6.072 | 6.072 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/frontend-pause/r0p2-b02-08-full | frontend-pause-effect | 2 | 5.231 | 5.231 | 5.231 | 5.231 | 5.231 | 5.231 | 5.231 | 5.231 | 5.231 | 5.231 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/frontend-pause/r0p2-b03-04-full | frontend-pause-effect | 3 | 4.126 | 4.126 | 4.126 | 4.126 | 4.126 | 4.126 | 4.126 | 4.126 | 4.126 | 4.126 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/productcatalog-cpu-throttle/r0p2-b01-12-full | productcatalog-cpu-throttle-effect | 1 | 60.060 | 60.060 | 60.060 | 60.060 | 60.060 | 60.060 | 60.060 | 60.060 | 60.060 | 60.060 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/productcatalog-cpu-throttle/r0p2-b02-11-full | productcatalog-cpu-throttle-effect | 2 | 60.060 | 60.060 | 60.060 | 60.060 | 60.060 | 60.060 | 60.060 | 60.060 | 60.060 | 60.060 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/productcatalog-cpu-throttle/r0p2-b03-01-full | productcatalog-cpu-throttle-effect | 3 | 60.059 | 60.059 | 60.059 | 60.059 | 60.059 | 60.059 | 60.059 | 60.059 | 60.059 | 60.059 |

## r1

C episodes: 6 (frontend-pause-effect 3, productcatalog-cpu-throttle-effect 3). Ground set of the C readout: 1138 sensors.

| set | sensors | absent from C's V_r | D_C(S) | D_C(ledger) | g_C | detected | verdict (decision 89) |
|---|---|---|---|---|---|---|---|
| primary 0 | (none) | 0 | 30.343 | 30.343 | 0.000 | 4/6 | — |
| primary 3/T_r | log:frontendproxy:5eaff2aaa577 | 0 | 30.343 | 30.343 | 0.000 | 4/6 | — |
| primary 6/h | log:frontendproxy:5eaff2aaa577 | 0 | 30.343 | 30.343 | 0.000 | 4/6 | — |
| primary inf | log:frontendproxy:5eaff2aaa577 | 0 | 30.343 | 30.343 | 0.000 | 4/6 | — |
| ledger alone | (none) | 0 | 30.343 | 30.343 | 0.000 | 4/6 | — |
| full | V_r frozen (1106) | 0 | 30.342 | 30.343 | 0.000 | 4/6 | — |
| none | 809 sensors | 0 | 30.343 | 30.343 | 0.000 | 4/6 | — |
| selected | 954 sensors | 0 | 30.342 | 30.343 | 0.000 | 4/6 | — |
| modality T 6/h | (none) | 0 | 30.343 | 30.343 | 0.000 | 4/6 | — |
| modality T+L 6/h | log:frontendproxy:5eaff2aaa577 | 0 | 30.343 | 30.343 | 0.000 | 4/6 | — |

Per episode, penalised seconds (`*` = strictly earlier than the ledger):

| episode | class | block | ledger | primary 0 | primary 3/T_r | primary 6/h | primary inf | full | none | selected | modality T 6/h | modality T+L 6/h |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/frontend-pause/r1-b01-06-full | frontend-pause-effect | 1 | 1.286 | 1.286 | 1.286 | 1.286 | 1.286 | 1.286 | 1.286 | 1.286 | 1.286 | 1.286 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/frontend-pause/r1-b02-05-full | frontend-pause-effect | 2 | 1.081 | 1.081 | 1.081 | 1.081 | 1.081 | 1.081 | 1.081 | 1.081 | 1.081 | 1.081 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/frontend-pause/r1-b03-12-full | frontend-pause-effect | 3 | 0.608 | 0.608 | 0.608 | 0.608 | 0.608 | 0.608 | 0.608 | 0.608 | 0.608 | 0.608 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/productcatalog-cpu-throttle/r1-b01-02-full | productcatalog-cpu-throttle-effect | 1 | 58.979 | 58.979 | 58.979 | 58.979 | 58.979 | 58.977* | 58.979 | 58.977* | 58.979 | 58.979 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/productcatalog-cpu-throttle/r1-b02-03-full | productcatalog-cpu-throttle-effect | 2 | 60.046 | 60.046 | 60.046 | 60.046 | 60.046 | 60.046 | 60.046 | 60.046 | 60.046 | 60.046 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/productcatalog-cpu-throttle/r1-b03-06-full | productcatalog-cpu-throttle-effect | 3 | 60.057 | 60.057 | 60.057 | 60.057 | 60.057 | 60.057 | 60.057 | 60.057 | 60.057 | 60.057 |

## r10

C episodes: 6 (frontend-pause-effect 3, productcatalog-cpu-throttle-effect 3). Ground set of the C readout: 1110 sensors.

| set | sensors | absent from C's V_r | D_C(S) | D_C(ledger) | g_C | detected | verdict (decision 89) |
|---|---|---|---|---|---|---|---|
| primary 0 | (none) | 0 | 30.246 | 30.246 | 0.000 | 3/6 | — |
| primary 3/T_r | log:frontendproxy:5eaff2aaa577 | 0 | 30.246 | 30.246 | 0.000 | 3/6 | — |
| primary 6/h | span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct | 0 | 30.246 | 30.246 | 0.000 | 3/6 | — |
| primary inf | log:frontendproxy:5eaff2aaa577, span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct | 0 | 30.246 | 30.246 | 0.000 | 3/6 | — |
| ledger alone | (none) | 0 | 30.246 | 30.246 | 0.000 | 3/6 | — |
| full | V_r frozen (1051) | 0 | 30.246 | 30.246 | 0.000 | 3/6 | — |
| none | 754 sensors | 0 | 30.246 | 30.246 | 0.000 | 3/6 | — |
| selected | 899 sensors | 0 | 30.246 | 30.246 | 0.000 | 3/6 | — |
| modality T 6/h | span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct | 0 | 30.246 | 30.246 | 0.000 | 3/6 | — |
| modality T+L 6/h | span:frontend:grpc.oteldemo.ProductCatalogService/GetProduct | 0 | 30.246 | 30.246 | 0.000 | 3/6 | — |

Per episode, penalised seconds (`*` = strictly earlier than the ledger):

| episode | class | block | ledger | primary 0 | primary 3/T_r | primary 6/h | primary inf | full | none | selected | modality T 6/h | modality T+L 6/h |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/frontend-pause/r10-b01-08-full | frontend-pause-effect | 1 | 0.463 | 0.463 | 0.463 | 0.463 | 0.463 | 0.463 | 0.463 | 0.463 | 0.463 | 0.463 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/frontend-pause/r10-b02-04-full | frontend-pause-effect | 2 | 0.439 | 0.439 | 0.439 | 0.439 | 0.439 | 0.439 | 0.439 | 0.439 | 0.439 | 0.439 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/frontend-pause/r10-b03-08-full | frontend-pause-effect | 3 | 0.477 | 0.477 | 0.477 | 0.477 | 0.477 | 0.477 | 0.477 | 0.477 | 0.477 | 0.477 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/productcatalog-cpu-throttle/r10-b01-10-full | productcatalog-cpu-throttle-effect | 1 | 60.022 | 60.022 | 60.022 | 60.022 | 60.022 | 60.022 | 60.022 | 60.022 | 60.022 | 60.022 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/productcatalog-cpu-throttle/r10-b02-01-full | productcatalog-cpu-throttle-effect | 2 | 60.017 | 60.017 | 60.017 | 60.017 | 60.017 | 60.017 | 60.017 | 60.017 | 60.017 | 60.017 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/otel :: runs/effect/productcatalog-cpu-throttle/r10-b03-03-full | productcatalog-cpu-throttle-effect | 3 | 60.059 | 60.059 | 60.059 | 60.059 | 60.059 | 60.059 | 60.059 | 60.059 | 60.059 | 60.059 |

