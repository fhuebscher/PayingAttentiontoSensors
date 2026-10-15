# Campaign C test scoring (score-test-v3.1, scope instance)

System `teastore`; campaign index 5 (`tmp/c-fault-copy/teastore`), C's episodes only. Penalty `ttd` (a miss charged the hold); D and g_C in seconds; g_C = D_C(ledger alone) - D_C(S).
Fresh false alarms of every frozen set on C's no-fault cells: — (decision 88: fresh false alarms of the frozen sets on C's no-fault cells need a validated path; the frozen v3.1 --validation accepts P4-shaped sets only, so none exists).
Deviation: scored by restriction of `full` cells: a declared deviation from protocol §3 (:102), decision 80; decision 46.3's live run of the chosen placement is the later check.

## r0.05

C episodes: 6 (auth-freeze-effect 3, persistence-cpu-throttle-effect 3). Ground set of the C readout: 461 sensors.

| set | sensors | absent from C's V_r | D_C(S) | D_C(ledger) | g_C | detected | verdict (decision 89) |
|---|---|---|---|---|---|---|---|
| primary 0 | (none) | 0 | 12.290 | 12.290 | 0.000 | 6/6 | — |
| primary 3/T_r | log:webui:d4d75ec135e6 | 0 | 10.522 | 12.290 | 1.768 | 6/6 | — |
| primary 6/h | log:webui:d4d75ec135e6, span:auth:BCryptProvider.checkPassword | 0 | 10.495 | 12.290 | 1.796 | 6/6 | — |
| primary inf | log:webui:d4d75ec135e6, span:auth:BCryptProvider.checkPassword, span:image:AbstractCache.getEntries | 0 | 10.495 | 12.290 | 1.796 | 6/6 | — |
| ledger alone | (none) | 0 | 12.290 | 12.290 | 0.000 | 6/6 | — |
| full | V_r frozen (461) | 0 | 10.329 | 12.290 | 1.961 | 6/6 | — |
| none | 438 sensors | 0 | 10.357 | 12.290 | 1.933 | 6/6 | — |
| selected | 452 sensors | 0 | 10.329 | 12.290 | 1.961 | 6/6 | — |
| modality T 6/h | span:auth:BCryptProvider.checkPassword | 0 | 12.252 | 12.290 | 0.038 | 6/6 | — |
| modality T+L 6/h | log:webui:d4d75ec135e6, span:auth:BCryptProvider.checkPassword | 0 | 10.495 | 12.290 | 1.796 | 6/6 | — |

Per episode, penalised seconds (`*` = strictly earlier than the ledger):

| episode | class | block | ledger | primary 0 | primary 3/T_r | primary 6/h | primary inf | full | none | selected | modality T 6/h | modality T+L 6/h |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/auth-freeze-effect/b01-01-full | auth-freeze-effect | 1 | 6.932 | 6.932 | 6.932 | 6.932 | 6.932 | 6.932 | 6.932 | 6.932 | 6.932 | 6.932 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/auth-freeze-effect/b02-07-full | auth-freeze-effect | 2 | 18.440 | 18.440 | 11.977* | 11.977* | 11.977* | 11.977* | 11.977* | 11.977* | 18.440 | 11.977* |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/auth-freeze-effect/b03-07-full | auth-freeze-effect | 3 | 2.324 | 2.324 | 2.324 | 2.324 | 2.324 | 2.324 | 2.324 | 2.324 | 2.324 | 2.324 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/persistence-cpu-throttle-effect/b01-11-full | persistence-cpu-throttle-effect | 1 | 27.196 | 27.196 | 23.050* | 23.050* | 23.050* | 22.058* | 22.058* | 22.058* | 27.133* | 23.050* |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/persistence-cpu-throttle-effect/b02-11-full | persistence-cpu-throttle-effect | 2 | 0.577 | 0.577 | 0.577 | 0.494* | 0.494* | 0.494* | 0.577 | 0.494* | 0.494* | 0.494* |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/persistence-cpu-throttle-effect/b03-01-full | persistence-cpu-throttle-effect | 3 | 18.272 | 18.272 | 18.272 | 18.190* | 18.190* | 18.190* | 18.272 | 18.190* | 18.190* | 18.190* |

## r0.2

C episodes: 6 (auth-freeze-effect 3, persistence-cpu-throttle-effect 3). Ground set of the C readout: 464 sensors.

| set | sensors | absent from C's V_r | D_C(S) | D_C(ledger) | g_C | detected | verdict (decision 89) |
|---|---|---|---|---|---|---|---|
| primary 0 | (none) | 0 | 7.876 | 7.876 | 0.000 | 6/6 | — |
| primary 3/T_r | metric:rabbitmq:sys_cpu | 0 | 6.186 | 7.876 | 1.691 | 6/6 | — |
| primary 6/h | metric:rabbitmq:sys_cpu | 0 | 6.186 | 7.876 | 1.691 | 6/6 | — |
| primary inf | metric:rabbitmq:sys_cpu, span:webui:IndexServlet.handleGETRequest | 0 | 6.185 | 7.876 | 1.692 | 6/6 | — |
| ledger alone | (none) | 0 | 7.876 | 7.876 | 0.000 | 6/6 | — |
| full | V_r frozen (462) | 0 | 6.185 | 7.876 | 1.692 | 6/6 | — |
| none | 439 sensors | 0 | 6.186 | 7.876 | 1.691 | 6/6 | — |
| selected | 453 sensors | 0 | 6.186 | 7.876 | 1.691 | 6/6 | — |
| modality T 6/h | span:auth:BCryptProvider.checkPassword | 0 | 7.876 | 7.876 | 0.000 | 6/6 | — |
| modality T+L 6/h | span:auth:BCryptProvider.checkPassword | 0 | 7.876 | 7.876 | 0.000 | 6/6 | — |

Per episode, penalised seconds (`*` = strictly earlier than the ledger):

| episode | class | block | ledger | primary 0 | primary 3/T_r | primary 6/h | primary inf | full | none | selected | modality T 6/h | modality T+L 6/h |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/auth-freeze-effect/b01-04-full | auth-freeze-effect | 1 | 4.482 | 4.482 | 4.482 | 4.482 | 4.482 | 4.482 | 4.482 | 4.482 | 4.482 | 4.482 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/auth-freeze-effect/b02-02-full | auth-freeze-effect | 2 | 6.498 | 6.498 | 6.498 | 6.498 | 6.498 | 6.498 | 6.498 | 6.498 | 6.498 | 6.498 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/auth-freeze-effect/b03-09-full | auth-freeze-effect | 3 | 3.750 | 3.750 | 3.750 | 3.750 | 3.750 | 3.750 | 3.750 | 3.750 | 3.750 | 3.750 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/persistence-cpu-throttle-effect/b01-06-full | persistence-cpu-throttle-effect | 1 | 4.938 | 4.938 | 4.938 | 4.938 | 4.936* | 4.936* | 4.938 | 4.938 | 4.938 | 4.938 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/persistence-cpu-throttle-effect/b02-12-full | persistence-cpu-throttle-effect | 2 | 5.667 | 5.667 | 5.667 | 5.667 | 5.664* | 5.664* | 5.667 | 5.667 | 5.667 | 5.667 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/persistence-cpu-throttle-effect/b03-12-full | persistence-cpu-throttle-effect | 3 | 21.922 | 21.922 | 11.778* | 11.778* | 11.778* | 11.778* | 11.778* | 11.778* | 21.922 | 21.922 |

## r1

C episodes: 6 (auth-freeze-effect 3, persistence-cpu-throttle-effect 3). Ground set of the C readout: 463 sensors.

| set | sensors | absent from C's V_r | D_C(S) | D_C(ledger) | g_C | detected | verdict (decision 89) |
|---|---|---|---|---|---|---|---|
| primary 0 | (none) | 0 | 1.911 | 1.911 | 0.000 | 6/6 | — |
| primary 3/T_r | (none) | 0 | 1.911 | 1.911 | 0.000 | 6/6 | — |
| primary 6/h | span:auth:AuthUserActionsRest.login | 0 | 1.828 | 1.911 | 0.083 | 6/6 | — |
| primary inf | span:auth:AuthUserActionsRest.login, span:webui:IndexServlet.handleGETRequest | 0 | 1.828 | 1.911 | 0.083 | 6/6 | — |
| ledger alone | (none) | 0 | 1.911 | 1.911 | 0.000 | 6/6 | — |
| full | V_r frozen (463) | 0 | 1.828 | 1.911 | 0.083 | 6/6 | — |
| none | 439 sensors | 0 | 1.911 | 1.911 | 0.000 | 6/6 | — |
| selected | 453 sensors | 0 | 1.828 | 1.911 | 0.083 | 6/6 | — |
| modality T 6/h | span:auth:AuthUserActionsRest.login | 0 | 1.828 | 1.911 | 0.083 | 6/6 | — |
| modality T+L 6/h | span:auth:AuthUserActionsRest.login | 0 | 1.828 | 1.911 | 0.083 | 6/6 | — |

Per episode, penalised seconds (`*` = strictly earlier than the ledger):

| episode | class | block | ledger | primary 0 | primary 3/T_r | primary 6/h | primary inf | full | none | selected | modality T 6/h | modality T+L 6/h |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/auth-freeze-effect/b01-09-full | auth-freeze-effect | 1 | 1.781 | 1.781 | 1.781 | 1.781 | 1.781 | 1.781 | 1.781 | 1.781 | 1.781 | 1.781 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/auth-freeze-effect/b02-01-full | auth-freeze-effect | 2 | 1.042 | 1.042 | 1.042 | 1.042 | 1.042 | 1.042 | 1.042 | 1.042 | 1.042 | 1.042 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/auth-freeze-effect/b03-10-full | auth-freeze-effect | 3 | 1.614 | 1.614 | 1.614 | 1.614 | 1.614 | 1.614 | 1.614 | 1.614 | 1.614 | 1.614 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/persistence-cpu-throttle-effect/b01-07-full | persistence-cpu-throttle-effect | 1 | 5.031 | 5.031 | 5.031 | 4.730* | 4.730* | 4.730* | 5.031 | 4.730* | 4.730* | 4.730* |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/persistence-cpu-throttle-effect/b02-06-full | persistence-cpu-throttle-effect | 2 | 1.482 | 1.482 | 1.482 | 1.381* | 1.381* | 1.381* | 1.482 | 1.381* | 1.381* | 1.381* |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/persistence-cpu-throttle-effect/b03-04-full | persistence-cpu-throttle-effect | 3 | 0.516 | 0.516 | 0.516 | 0.418* | 0.418* | 0.418* | 0.516 | 0.418* | 0.418* | 0.418* |

## r10

C episodes: 6 (auth-freeze-effect 3, persistence-cpu-throttle-effect 3). Ground set of the C readout: 464 sensors.

| set | sensors | absent from C's V_r | D_C(S) | D_C(ledger) | g_C | detected | verdict (decision 89) |
|---|---|---|---|---|---|---|---|
| primary 0 | (none) | 0 | 0.716 | 0.716 | 0.000 | 6/6 | — |
| primary 3/T_r | span:auth:AuthUserActionsRest.login | 0 | 0.663 | 0.716 | 0.053 | 6/6 | — |
| primary 6/h | span:auth:AuthUserActionsRest.login | 0 | 0.663 | 0.716 | 0.053 | 6/6 | — |
| primary inf | span:auth:AuthUserActionsRest.login, span:webui:IndexServlet.handleGETRequest | 0 | 0.663 | 0.716 | 0.053 | 6/6 | — |
| ledger alone | (none) | 0 | 0.716 | 0.716 | 0.000 | 6/6 | — |
| full | V_r frozen (464) | 0 | 0.663 | 0.716 | 0.053 | 6/6 | — |
| none | 440 sensors | 0 | 0.716 | 0.716 | 0.000 | 6/6 | — |
| selected | 454 sensors | 0 | 0.663 | 0.716 | 0.053 | 6/6 | — |
| modality T 6/h | span:auth:AuthUserActionsRest.login | 0 | 0.663 | 0.716 | 0.053 | 6/6 | — |
| modality T+L 6/h | span:auth:AuthUserActionsRest.login | 0 | 0.663 | 0.716 | 0.053 | 6/6 | — |

Per episode, penalised seconds (`*` = strictly earlier than the ledger):

| episode | class | block | ledger | primary 0 | primary 3/T_r | primary 6/h | primary inf | full | none | selected | modality T 6/h | modality T+L 6/h |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/auth-freeze-effect/b01-10-full | auth-freeze-effect | 1 | 0.485 | 0.485 | 0.485 | 0.485 | 0.485 | 0.485 | 0.485 | 0.485 | 0.485 | 0.485 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/auth-freeze-effect/b02-09-full | auth-freeze-effect | 2 | 0.493 | 0.493 | 0.493 | 0.493 | 0.493 | 0.493 | 0.493 | 0.493 | 0.493 | 0.493 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/auth-freeze-effect/b03-06-full | auth-freeze-effect | 3 | 0.482 | 0.482 | 0.482 | 0.482 | 0.482 | 0.482 | 0.482 | 0.482 | 0.482 | 0.482 |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/persistence-cpu-throttle-effect/b01-03-full | persistence-cpu-throttle-effect | 1 | 0.629 | 0.629 | 0.600* | 0.600* | 0.600* | 0.600* | 0.629 | 0.600* | 0.600* | 0.600* |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/persistence-cpu-throttle-effect/b02-08-full | persistence-cpu-throttle-effect | 2 | 1.277 | 1.277 | 1.082* | 1.082* | 1.082* | 1.082* | 1.277 | 1.082* | 1.082* | 1.082* |
| /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/tmp/c-fault-copy/teastore :: runs/persistence-cpu-throttle-effect/b03-05-full | persistence-cpu-throttle-effect | 3 | 0.933 | 0.933 | 0.838* | 0.838* | 0.838* | 0.838* | 0.933 | 0.838* | 0.838* | 0.838* |

