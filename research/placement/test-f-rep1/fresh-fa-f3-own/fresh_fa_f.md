# Fresh false alarms of F's frozen sets on F's held-out no-fault cells (POST HOC, instance scope)

Cells: r25-b04-16-full, r25-b04-17-full, r25-b05-21-full, r25-b05-22-full. 4 cells, 0.2000 h. Calibration byte-equal to the frozen training readout: True.

| set | sensor | rule (calibrated value) | alarms | h | alarms/h | 95 % Poisson upper /h | training honest upper /h |
|---|---|---|---|---|---|---|---|
| @6/T_r | kafka.purgatory.size | spike (range) | 1 | 0.2000 | 5.00 | 23.72 | 9.99 |
| @6/T_r | kafka.purgatory.size | run3 (range) | 0 | 0.2000 | 0.00 | 14.98 | 9.99 |
| @6/T_r | kafka.purgatory.size | median (range) | 0 | 0.2000 | 0.00 | 14.98 | 9.99 |
| @6/T_r | kafka.purgatory.size | union of the sensor's 3 rules  | 1 | 0.2000 | 5.00 | 23.72 | 9.99 |
| @3/T_r | kafka.purgatory.size | spike (range) | 1 | 0.2000 | 5.00 | 23.72 | 9.99 |
| @3/T_r | kafka.purgatory.size | run3 (range) | 0 | 0.2000 | 0.00 | 14.98 | 9.99 |
| @3/T_r | kafka.purgatory.size | median (range) | 0 | 0.2000 | 0.00 | 14.98 | 9.99 |
| @3/T_r | kafka.purgatory.size | union of the sensor's 3 rules  | 1 | 0.2000 | 5.00 | 23.72 | 9.99 |
