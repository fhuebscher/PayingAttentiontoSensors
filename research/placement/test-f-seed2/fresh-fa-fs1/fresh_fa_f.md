# Fresh false alarms of F's frozen sets on F's held-out no-fault cells (POST HOC, instance scope)

Cells: r25-b04-16-full, r25-b04-17-full, r25-b05-21-full, r25-b05-22-full. 4 cells, 0.2000 h. Calibration byte-equal to the frozen training readout: True.

| set | sensor | rule (calibrated value) | alarms | h | alarms/h | 95 % Poisson upper /h | training honest upper /h |
|---|---|---|---|---|---|---|---|
| @6/T_r | kafka.consumer_group.lag | spike (range) | 0 | 0.2000 | 0.00 | 14.98 | 9.99 |
| @6/T_r | kafka.consumer_group.lag | run3 (range) | 0 | 0.2000 | 0.00 | 14.98 | 9.99 |
| @6/T_r | kafka.consumer_group.lag | median (range) | 0 | 0.2000 | 0.00 | 14.98 | 9.99 |
| @6/T_r | kafka.consumer_group.lag | union of the sensor's 3 rules  | 0 | 0.2000 | 0.00 | 14.98 | 9.99 |
| @3/T_r | kafka.request.count | spike (K 10) | 0 | 0.2000 | 0.00 | 14.98 | 15.81 |
| @3/T_r | kafka.request.count | run3 (K 2.5) | 0 | 0.2000 | 0.00 | 14.98 | 9.99 |
| @3/T_r | kafka.request.count | median (K 2.5) | 0 | 0.2000 | 0.00 | 14.98 | 9.99 |
| @3/T_r | kafka.request.count | union of the sensor's 3 rules  | 0 | 0.2000 | 0.00 | 14.98 | 15.81 |
