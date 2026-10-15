# R4 price check (POST HOC, instance)

10 no-fault cells, 0.5000 h. Contradicted iff the fresh one-sided 95 % lower bound exceeds the training price; bounded below iff the one-sided 95 % upper bound is under it. A metric sensor with 0 raw samples in any cell is —.

Raw samples per cell (min / max): kafka.consumer_group.lag 49 / 49; kafka.request.count 47 / 48; kafka.purgatory.size 48 / 49

| set | sensor | rule | k | h | k/h | 95 % lower /h | 95 % upper /h | training price /h | verdict |
|---|---|---|---|---|---|---|---|---|---|
| F @6/T_r (frozen) | kafka.consumer_group.lag | spike | 0 | 0.5000 | 0.00 | 0.00 | 5.99 | 15.81 | — |
| F @6/T_r (frozen) | kafka.consumer_group.lag | run3 | 0 | 0.5000 | 0.00 | 0.00 | 5.99 | 9.99 | — |
| F @6/T_r (frozen) | kafka.consumer_group.lag | median | 0 | 0.5000 | 0.00 | 0.00 | 5.99 | 9.99 | — |
| F @6/T_r (frozen) | kafka.consumer_group.lag | union | 0 | 0.5000 | 0.00 | 0.00 | 5.99 | 15.81 | bounded below the price |
| F @3/T_r; ablation @6/T_r (frozen there, priced here with F's calibration) | kafka.request.count | spike | 4 | 0.5000 | 8.00 | 2.73 | 18.31 | 9.99 | — |
| F @3/T_r; ablation @6/T_r (frozen there, priced here with F's calibration) | kafka.request.count | run3 | 0 | 0.5000 | 0.00 | 0.00 | 5.99 | 9.99 | — |
| F @3/T_r; ablation @6/T_r (frozen there, priced here with F's calibration) | kafka.request.count | median | 0 | 0.5000 | 0.00 | 0.00 | 5.99 | 9.99 | — |
| F @3/T_r; ablation @6/T_r (frozen there, priced here with F's calibration) | kafka.request.count | union | 4 | 0.5000 | 8.00 | 2.73 | 18.31 | 9.99 | consistent, not bounded |
| F rerun @6/T_r (frozen) | kafka.purgatory.size | spike | 5 | 0.5000 | 10.00 | 3.94 | 21.03 | 9.99 | — |
| F rerun @6/T_r (frozen) | kafka.purgatory.size | run3 | 0 | 0.5000 | 0.00 | 0.00 | 5.99 | 9.99 | — |
| F rerun @6/T_r (frozen) | kafka.purgatory.size | median | 0 | 0.5000 | 0.00 | 0.00 | 5.99 | 9.99 | — |
| F rerun @6/T_r (frozen) | kafka.purgatory.size | union | 5 | 0.5000 | 10.00 | 3.94 | 21.03 | 9.99 | consistent, not bounded |
| ledger (baseline, unpriced) | add-to-cart | spike | 7 | 0.5000 | 14.00 | 6.57 | 26.30 | 9.99 | — |
| ledger (baseline, unpriced) | add-to-cart | run3 | 0 | 0.5000 | 0.00 | 0.00 | 5.99 | 20.99 | — |
| ledger (baseline, unpriced) | add-to-cart | median | 2 | 0.5000 | 4.00 | 0.71 | 12.59 | 15.81 | — |
| ledger (baseline, unpriced) | add-to-cart | absent | 0 | 0.5000 | 0.00 | 0.00 | 5.99 | 9.99 | — |
| ledger (baseline, unpriced) | add-to-cart | union | — | 0.5000 | — | — | — | — | — |
| ledger (baseline, unpriced) | ads | spike | 1 | 0.5000 | 2.00 | 0.10 | 9.49 | 20.99 | — |
| ledger (baseline, unpriced) | ads | run3 | 4 | 0.5000 | 8.00 | 2.73 | 18.31 | 9.99 | — |
| ledger (baseline, unpriced) | ads | median | 6 | 0.5000 | 12.00 | 5.23 | 23.68 | 15.81 | — |
| ledger (baseline, unpriced) | ads | absent | 0 | 0.5000 | 0.00 | 0.00 | 5.99 | 9.99 | — |
| ledger (baseline, unpriced) | ads | union | — | 0.5000 | — | — | — | — | — |
| ledger (baseline, unpriced) | checkout | spike | 1 | 0.5000 | 2.00 | 0.10 | 9.49 | 15.81 | — |
| ledger (baseline, unpriced) | checkout | run3 | 0 | 0.5000 | 0.00 | 0.00 | 5.99 | 9.99 | — |
| ledger (baseline, unpriced) | checkout | median | 2 | 0.5000 | 4.00 | 0.71 | 12.59 | 9.99 | — |
| ledger (baseline, unpriced) | checkout | absent | 0 | 0.5000 | 0.00 | 0.00 | 5.99 | 15.81 | — |
| ledger (baseline, unpriced) | checkout | union | — | 0.5000 | — | — | — | — | — |
| ledger (baseline, unpriced) | index | spike | 1 | 0.5000 | 2.00 | 0.10 | 9.49 | 15.81 | — |
| ledger (baseline, unpriced) | index | run3 | 1 | 0.5000 | 2.00 | 0.10 | 9.49 | 9.99 | — |
| ledger (baseline, unpriced) | index | median | 3 | 0.5000 | 6.00 | 1.64 | 15.51 | 9.99 | — |
| ledger (baseline, unpriced) | index | absent | 0 | 0.5000 | 0.00 | 0.00 | 5.99 | 9.99 | — |
| ledger (baseline, unpriced) | index | union | — | 0.5000 | — | — | — | — | — |
| ledger (baseline, unpriced) | product | spike | 1 | 0.5000 | 2.00 | 0.10 | 9.49 | 15.81 | — |
| ledger (baseline, unpriced) | product | run3 | 6 | 0.5000 | 12.00 | 5.23 | 23.68 | 15.81 | — |
| ledger (baseline, unpriced) | product | median | 2 | 0.5000 | 4.00 | 0.71 | 12.59 | 15.81 | — |
| ledger (baseline, unpriced) | product | absent | 1 | 0.5000 | 2.00 | 0.10 | 9.49 | 9.99 | — |
| ledger (baseline, unpriced) | product | union | — | 0.5000 | — | — | — | — | — |
| ledger (baseline, unpriced) | recommendations | spike | 1 | 0.5000 | 2.00 | 0.10 | 9.49 | 15.81 | — |
| ledger (baseline, unpriced) | recommendations | run3 | 3 | 0.5000 | 6.00 | 1.64 | 15.51 | 15.81 | — |
| ledger (baseline, unpriced) | recommendations | median | 6 | 0.5000 | 12.00 | 5.23 | 23.68 | 15.81 | — |
| ledger (baseline, unpriced) | recommendations | absent | 0 | 0.5000 | 0.00 | 0.00 | 5.99 | 9.99 | — |
| ledger (baseline, unpriced) | recommendations | union | — | 0.5000 | — | — | — | — | — |
| ledger (baseline, unpriced) | view-cart | spike | 2 | 0.5000 | 4.00 | 0.71 | 12.59 | 9.99 | — |
| ledger (baseline, unpriced) | view-cart | run3 | 1 | 0.5000 | 2.00 | 0.10 | 9.49 | 20.99 | — |
| ledger (baseline, unpriced) | view-cart | median | 5 | 0.5000 | 10.00 | 3.94 | 21.03 | 15.81 | — |
| ledger (baseline, unpriced) | view-cart | absent | 2 | 0.5000 | 4.00 | 0.71 | 12.59 | 9.99 | — |
| ledger (baseline, unpriced) | view-cart | union | — | 0.5000 | — | — | — | — | — |
