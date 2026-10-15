# Pooled lane evidence, all three SUTs, 2026-10-14

**POST HOC, EXPLORATORY (not preregistered; computed after the readouts were seen).** Scope of every table: **instance** (one SUT, one host; pooled rows pool campaigns of one SUT, never SUTs). Produced by `research/lanes/pooled_lanes.py` from the committed readout JSON listed below; nothing under `tmp/` was read, no frozen file edited. Plan: user request 2026-10-14 (expand E's 10 off-path episodes to every relevant episode, show where the coordinator lane fails).

Cell format: `detected/episodes median (min-max)` in seconds after the pre-command onset stamp; `—` = not collected, none armed or no episode (never 0). A lane's *any* column uses fires with `counts` true; *counted* is the subset with no BC flag (the field the scorer counts); the difference is the by-construction-only hits (`byConstructionOnly` in pooled.json). Lanes: **own** = sensors of the fault's target service; **coord** = every log id of service `registry` (TeaStore) / `kafka` (OTel), Hotel `—` (consul writes no log, structural absence); **coord strict** = only the heartbeat-removal / group-member-failed ids reported in LANES.md; **lag** = OTel kafka consumer-lag metric ids armed at the rate (armed = placeable at the rate in the readout's calibration); **ledger** = family E. **These are detection times only: no lane here is priced or charged for false alarms** (a lane's time is the earliest fire of any of its sensors, so a lane with several sensors is not a single-sensor claim). Rate 25 exists only in campaign E (reader v3.2), rates 0.05-10 in the v3.1 readouts: Table 3 mixes the two readers for OTel frontend-pause.

## Readouts used (one per campaign) and not used

| system | readout | reader | episodes | covers | sha256 (first 12) |
|---|---|---|---|---|---|
| teastore | research/traffic-sweep/readout-teastore-c-v3.1/sweep_analysis_v3.json | v3.1 | 56 | TeaStore sweep r2 + campaign B + campaign C (auth-freeze, persistence-cpu-throttle; 4 + 12 + 12 each) | a29455b4d637 |
| otel | research/traffic-sweep/readout-otel-c-v3.1/sweep_analysis_v3.json | v3.1 | 56 | OTel sweep r1 + campaign B + campaign C (frontend-pause, productcatalog-cpu-throttle; 4 + 12 + 12 each) | 99a3299f46f6 |
| otel | research/traffic-sweep/readout-otel-e-score-v3.2/sweep_analysis_v3_2.json | v3.2 | 15 | OTel campaign E (accounting-pause, fraud-pause, frontend-pause, 5 each, rate 25; blocks 1-3 train, 4-5 test) | 09aa5382a08f |
| hotel | research/traffic-sweep/readout-hotel-primary-v3.1/sweep_analysis_v3.json | v3.1 | 48 | Hotel sweep relaunch 3 (search-pause, cpu-throttle on profile, net-delay on rate; 16 each) | 473cb649e858 |

Not used (every other `readout-*` directory under research/traffic-sweep):

| readout | reason |
|---|---|
| readout-hotel-quietcurve-a1to5-v3.1 | same sweep r3 fault cells as the primary readout, quiet-time ablation |
| readout-hotel-quietcurve-aonly-v3.1 | same sweep r3 fault cells as the primary readout, quiet-time ablation |
| readout-hotel-r3 | earlier reader version of Hotel sweep r3 (superseded by the v3.1 primary readout) |
| readout-hotel-r3-quiet-v2.4 | earlier reader version of Hotel sweep r3 (superseded by the v3.1 primary readout) |
| readout-hotel-r3-quiet-v3 | earlier reader version of Hotel sweep r3 (superseded by the v3.1 primary readout) |
| readout-hotel-r3-quiet-v3-fix1 | earlier reader version of Hotel sweep r3 (superseded by the v3.1 primary readout) |
| readout-hotel-r3-quiet-v3-fix2 | earlier reader version of Hotel sweep r3 (superseded by the v3.1 primary readout) |
| readout-hotel-r3-quiet-v3-fix3 | earlier reader version of Hotel sweep r3 (superseded by the v3.1 primary readout) |
| readout-hotel-r3-v2 | earlier reader version of Hotel sweep r3 (superseded by the v3.1 primary readout) |
| readout-hotel-r3-v2-fix1 | earlier reader version of Hotel sweep r3 (superseded by the v3.1 primary readout) |
| readout-hotel-r3-v2.1 | earlier reader version of Hotel sweep r3 (superseded by the v3.1 primary readout) |
| readout-hotel-r3-v2.2 | earlier reader version of Hotel sweep r3 (superseded by the v3.1 primary readout) |
| readout-hotel-r3-v2.3 | earlier reader version of Hotel sweep r3 (superseded by the v3.1 primary readout) |
| readout-hotel-r3-v2.4 | v2.4: no calibration (no prices); the same Hotel sweep r3 cells as the used v3.1 readout, read by an earlier detector |
| readout-otel-e-train-v3.2 | blocks 1-3 of E only; the score readout carries all 15 episodes with identical fires on blocks 1-3 (decision 102) |
| readout-otel-primary-v3.1 | pools sweep r1 + B (+ quiet cells) only: a subset of the C readout's fault cells |
| readout-otel-quietcurve-a1to5-v3.1 | pools sweep r1 + B (+ quiet cells) only: a subset of the C readout's fault cells |
| readout-otel-quietcurve-aonly-v3.1 | pools sweep r1 + B (+ quiet cells) only: a subset of the C readout's fault cells |
| readout-otel-r1-v2.4 | earlier reader version of sweep r1 (superseded by the C v3.1 readout, which also pools B and C) |
| readout-otel-r1-v3 | earlier reader version of sweep r1 (superseded by the C v3.1 readout, which also pools B and C) |
| readout-otel-r1-v3-fix1 | earlier reader version of sweep r1 (superseded by the C v3.1 readout, which also pools B and C) |
| readout-otel-r1-v3-fix2 | earlier reader version of sweep r1 (superseded by the C v3.1 readout, which also pools B and C) |
| readout-otel-r1-v3-fix3 | earlier reader version of sweep r1 (superseded by the C v3.1 readout, which also pools B and C) |
| readout-teastore-primary-v3.1 | pools sweep r2 + B (+ quiet cells) only: a subset of the C readout's fault cells |
| readout-teastore-quietcurve-a1to5-v3.1 | pools sweep r2 + B (+ quiet cells) only: a subset of the C readout's fault cells |
| readout-teastore-quietcurve-aonly-v3.1 | pools sweep r2 + B (+ quiet cells) only: a subset of the C readout's fault cells |
| readout-teastore-r2-v2.4 | earlier reader version of sweep r2 (superseded by the C v3.1 readout, which also pools B and C) |
| readout-teastore-r2-v3 | earlier reader version of sweep r2 (superseded by the C v3.1 readout, which also pools B and C) |
| readout-teastore-r2-v3-fix1 | earlier reader version of sweep r2 (superseded by the C v3.1 readout, which also pools B and C) |
| readout-teastore-r2-v3-fix2 | earlier reader version of sweep r2 (superseded by the C v3.1 readout, which also pools B and C) |
| readout-teastore-r2-v3-fix3 | earlier reader version of sweep r2 (superseded by the C v3.1 readout, which also pools B and C) |

OTel off-path pilot v2: — (no sweep readout: research/placement/pilot-offpath/manifestation-v2.json holds manifestation verdicts, no fires). Placement scorer outputs (`research/placement/test-c`, `test-e`) are derived from the used readouts and add no episodes.

## Cross-checks against research/lanes/out-20261013/LANES.md

| check | computed | ok |
|---|---|---|
| LANES.md: E own 10/10, 0.88-1.55 s (accounting + fraud pause, own lane, any rule) | 10/10, 0.88-1.55 s | True |
| LANES.md: TeaStore C readout registry 28/28, 9.07-11.75 s (auth-freeze, all campaigns of the readout) | 28/28, 9.07-11.75 s | True |
| own lane (any rule) equals LANES.md O1 'any own rule' detected and median, every row | 23 rows compared, 0 differ | True |

## Table 1: SUT x fault kind x rate (pooled over the SUT's campaigns)

| system | fault | kind | rate | episodes | own any | own counted | coord any | coord counted | coord strict any | coord strict counted | lag | ledger any | ledger counted |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hotel | cpu-throttle | degradation | 0.05 | 4 | 4/4 2.60 (0.07-4.14) | 1/4 | — | — | — | — | — | 0/4 | 0/4 |
| hotel | cpu-throttle | degradation | 0.2 | 4 | 3/4 6.92 (6.69-27.02) | 3/4 | — | — | — | — | — | 1/4 27.02 (27.02-27.02) | 1/4 |
| hotel | cpu-throttle | degradation | 1 | 4 | 1/4 14.74 (14.74-14.74) | 0/4 | — | — | — | — | — | 0/4 | 0/4 |
| hotel | cpu-throttle | degradation | 10 | 4 | 4/4 4.76 (4.72-4.79) | 2/4 | — | — | — | — | — | 2/4 19.11 (7.91-30.30) | 2/4 |
| hotel | net-delay | degradation | 0.05 | 4 | 4/4 4.35 (1.39-9.94) | 4/4 | — | — | — | — | — | 4/4 12.39 (1.72-19.61) | 4/4 |
| hotel | net-delay | degradation | 0.2 | 4 | 4/4 2.16 (0.41-4.77) | 4/4 | — | — | — | — | — | 4/4 2.46 (0.62-5.07) | 4/4 |
| hotel | net-delay | degradation | 1 | 4 | 4/4 0.53 (0.27-0.96) | 4/4 | — | — | — | — | — | 4/4 0.64 (0.38-1.07) | 4/4 |
| hotel | net-delay | degradation | 10 | 4 | 4/4 0.16 (0.14-0.20) | 4/4 | — | — | — | — | — | 4/4 0.17 (0.14-0.20) | 4/4 |
| hotel | search-pause | pause | 0.05 | 4 | 4/4 11.76 (11.58-13.21) | 0/4 | — | — | — | — | — | 4/4 11.48 (2.59-18.66) | 0/4 |
| hotel | search-pause | pause | 0.2 | 4 | 4/4 3.78 (1.94-5.01) | 0/4 | — | — | — | — | — | 4/4 4.77 (2.93-6.00) | 0/4 |
| hotel | search-pause | pause | 1 | 4 | 4/4 1.19 (0.70-1.54) | 0/4 | — | — | — | — | — | 4/4 1.20 (0.72-1.55) | 0/4 |
| hotel | search-pause | pause | 10 | 4 | 4/4 0.24 (0.21-0.28) | 4/4 | — | — | — | — | — | 4/4 0.25 (0.22-0.29) | 0/4 |
| otel | accounting-pause | pause | 25 | 5 | 5/5 1.34 (0.88-1.51) | 0/5 | 5/5 44.18 (43.71-44.32) | 5/5 | 5/5 44.18 (43.71-44.32) | 5/5 | — | 1/5 37.19 (37.19-37.19) | 1/5 |
| otel | fraud-pause | pause | 25 | 5 | 5/5 1.28 (1.15-1.55) | 0/5 | 5/5 43.85 (43.37-43.94) | 5/5 | 5/5 43.85 (43.37-43.94) | 5/5 | — | 2/5 32.92 (20.25-45.58) | 2/5 |
| otel | frontend-pause | pause | 0.05 | 7 | 7/7 20.10 (4.68-27.97) | 1/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 7/7 21.12 (15.70-27.98) | 0/7 |
| otel | frontend-pause | pause | 0.2 | 7 | 7/7 4.98 (2.83-7.37) | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 7/7 4.98 (2.84-7.38) | 0/7 |
| otel | frontend-pause | pause | 1 | 7 | 7/7 1.04 (0.52-1.28) | 5/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 7/7 1.04 (0.53-1.29) | 0/7 |
| otel | frontend-pause | pause | 10 | 7 | 7/7 0.46 (0.41-0.48) | 7/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 7/7 0.47 (0.42-0.48) | 0/7 |
| otel | frontend-pause | pause | 25 | 5 | 5/5 0.35 (0.29-0.41) | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | — | 5/5 0.35 (0.29-0.42) | 0/5 |
| otel | productcatalog-cpu-throttle | degradation | 0.05 | 7 | 2/7 52.22 (45.48-58.96) | 2/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 |
| otel | productcatalog-cpu-throttle | degradation | 0.2 | 7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 |
| otel | productcatalog-cpu-throttle | degradation | 1 | 7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 1/7 58.98 (58.98-58.98) | 1/7 |
| otel | productcatalog-cpu-throttle | degradation | 10 | 7 | 1/7 0.21 (0.21-0.21) | 1/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 |
| teastore | auth-freeze | pause | 0.05 | 7 | 7/7 6.86 (1.35-18.37) | 0/7 | 7/7 10.18 (9.07-11.72) | 0/7 | 7/7 10.18 (9.07-11.72) | 0/7 | — | 7/7 6.93 (1.43-18.44) | 0/7 |
| teastore | auth-freeze | pause | 0.2 | 7 | 7/7 4.65 (2.79-6.56) | 0/7 | 7/7 10.59 (9.89-11.67) | 0/7 | 7/7 10.59 (9.89-11.67) | 0/7 | — | 7/7 4.71 (2.83-6.61) | 0/7 |
| teastore | auth-freeze | pause | 1 | 7 | 7/7 1.49 (0.93-1.66) | 7/7 | 7/7 11.41 (9.66-11.75) | 0/7 | 7/7 11.41 (9.66-11.75) | 0/7 | — | 7/7 1.61 (1.04-1.78) | 0/7 |
| teastore | auth-freeze | pause | 10 | 7 | 7/7 0.47 (0.45-0.52) | 7/7 | 7/7 10.20 (9.79-11.73) | 0/7 | 7/7 10.20 (9.79-11.73) | 0/7 | — | 7/7 0.51 (0.48-0.55) | 0/7 |
| teastore | persistence-cpu-throttle | degradation | 0.05 | 7 | 7/7 2.61 (0.43-5.32) | 7/7 | 2/7 34.75 (21.52-47.98) | 2/7 | 2/7 34.75 (21.52-47.98) | 0/7 | — | 7/7 18.27 (0.58-57.41) | 7/7 |
| teastore | persistence-cpu-throttle | degradation | 0.2 | 7 | 7/7 3.30 (0.93-5.53) | 7/7 | 2/7 54.15 (53.14-55.16) | 2/7 | 2/7 54.15 (53.14-55.16) | 0/7 | — | 7/7 5.67 (2.55-21.92) | 7/7 |
| teastore | persistence-cpu-throttle | degradation | 1 | 7 | 7/7 1.15 (0.26-4.62) | 7/7 | 4/7 31.90 (19.50-44.66) | 4/7 | 4/7 31.90 (19.50-44.66) | 0/7 | — | 7/7 2.17 (0.52-5.03) | 7/7 |
| teastore | persistence-cpu-throttle | degradation | 10 | 7 | 7/7 0.92 (0.29-1.48) | 7/7 | 6/7 30.55 (17.56-59.05) | 4/7 | 6/7 30.55 (17.56-59.05) | 0/7 | — | 7/7 0.63 (0.23-1.30) | 7/7 |

## Table 1b: SUT x campaign x fault kind x rate

| system | campaign | fault | kind | rate | episodes | own any | own counted | coord any | coord counted | coord strict any | coord strict counted | lag | ledger any | ledger counted |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hotel | sweep r3 | cpu-throttle | degradation | 0.05 | 4 | 4/4 2.60 (0.07-4.14) | 1/4 | — | — | — | — | — | 0/4 | 0/4 |
| hotel | sweep r3 | cpu-throttle | degradation | 0.2 | 4 | 3/4 6.92 (6.69-27.02) | 3/4 | — | — | — | — | — | 1/4 27.02 (27.02-27.02) | 1/4 |
| hotel | sweep r3 | cpu-throttle | degradation | 1 | 4 | 1/4 14.74 (14.74-14.74) | 0/4 | — | — | — | — | — | 0/4 | 0/4 |
| hotel | sweep r3 | cpu-throttle | degradation | 10 | 4 | 4/4 4.76 (4.72-4.79) | 2/4 | — | — | — | — | — | 2/4 19.11 (7.91-30.30) | 2/4 |
| hotel | sweep r3 | net-delay | degradation | 0.05 | 4 | 4/4 4.35 (1.39-9.94) | 4/4 | — | — | — | — | — | 4/4 12.39 (1.72-19.61) | 4/4 |
| hotel | sweep r3 | net-delay | degradation | 0.2 | 4 | 4/4 2.16 (0.41-4.77) | 4/4 | — | — | — | — | — | 4/4 2.46 (0.62-5.07) | 4/4 |
| hotel | sweep r3 | net-delay | degradation | 1 | 4 | 4/4 0.53 (0.27-0.96) | 4/4 | — | — | — | — | — | 4/4 0.64 (0.38-1.07) | 4/4 |
| hotel | sweep r3 | net-delay | degradation | 10 | 4 | 4/4 0.16 (0.14-0.20) | 4/4 | — | — | — | — | — | 4/4 0.17 (0.14-0.20) | 4/4 |
| hotel | sweep r3 | search-pause | pause | 0.05 | 4 | 4/4 11.76 (11.58-13.21) | 0/4 | — | — | — | — | — | 4/4 11.48 (2.59-18.66) | 0/4 |
| hotel | sweep r3 | search-pause | pause | 0.2 | 4 | 4/4 3.78 (1.94-5.01) | 0/4 | — | — | — | — | — | 4/4 4.77 (2.93-6.00) | 0/4 |
| hotel | sweep r3 | search-pause | pause | 1 | 4 | 4/4 1.19 (0.70-1.54) | 0/4 | — | — | — | — | — | 4/4 1.20 (0.72-1.55) | 0/4 |
| hotel | sweep r3 | search-pause | pause | 10 | 4 | 4/4 0.24 (0.21-0.28) | 4/4 | — | — | — | — | — | 4/4 0.25 (0.22-0.29) | 0/4 |
| otel | B | frontend-pause | pause | 0.05 | 3 | 3/3 16.76 (4.68-20.10) | 1/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 20.10 (16.76-25.93) | 0/3 |
| otel | B | frontend-pause | pause | 0.2 | 3 | 3/3 4.98 (4.02-7.37) | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 4.98 (4.03-7.38) | 0/3 |
| otel | B | frontend-pause | pause | 1 | 3 | 3/3 1.04 (0.52-1.25) | 2/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 1.04 (0.53-1.26) | 0/3 |
| otel | B | frontend-pause | pause | 10 | 3 | 3/3 0.46 (0.41-0.48) | 3/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 0.47 (0.42-0.48) | 0/3 |
| otel | B | productcatalog-cpu-throttle | degradation | 0.05 | 3 | 1/3 58.96 (58.96-58.96) | 1/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| otel | B | productcatalog-cpu-throttle | degradation | 0.2 | 3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| otel | B | productcatalog-cpu-throttle | degradation | 1 | 3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| otel | B | productcatalog-cpu-throttle | degradation | 10 | 3 | 1/3 0.21 (0.21-0.21) | 1/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| otel | C | frontend-pause | pause | 0.05 | 3 | 3/3 21.12 (15.70-24.18) | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 21.12 (15.70-24.18) | 0/3 |
| otel | C | frontend-pause | pause | 0.2 | 3 | 3/3 5.22 (4.12-6.06) | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 5.23 (4.13-6.07) | 0/3 |
| otel | C | frontend-pause | pause | 1 | 3 | 3/3 1.08 (0.61-1.28) | 3/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 1.08 (0.61-1.29) | 0/3 |
| otel | C | frontend-pause | pause | 10 | 3 | 3/3 0.46 (0.43-0.47) | 3/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 0.46 (0.44-0.48) | 0/3 |
| otel | C | productcatalog-cpu-throttle | degradation | 0.05 | 3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| otel | C | productcatalog-cpu-throttle | degradation | 0.2 | 3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| otel | C | productcatalog-cpu-throttle | degradation | 1 | 3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 1/3 58.98 (58.98-58.98) | 1/3 |
| otel | C | productcatalog-cpu-throttle | degradation | 10 | 3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| otel | E | accounting-pause | pause | 25 | 5 | 5/5 1.34 (0.88-1.51) | 0/5 | 5/5 44.18 (43.71-44.32) | 5/5 | 5/5 44.18 (43.71-44.32) | 5/5 | — | 1/5 37.19 (37.19-37.19) | 1/5 |
| otel | E | fraud-pause | pause | 25 | 5 | 5/5 1.28 (1.15-1.55) | 0/5 | 5/5 43.85 (43.37-43.94) | 5/5 | 5/5 43.85 (43.37-43.94) | 5/5 | — | 2/5 32.92 (20.25-45.58) | 2/5 |
| otel | E | frontend-pause | pause | 25 | 5 | 5/5 0.35 (0.29-0.41) | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | — | 5/5 0.35 (0.29-0.42) | 0/5 |
| otel | sweep r1 | frontend-pause | pause | 0.05 | 1 | 1/1 27.97 (27.97-27.97) | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 1/1 27.98 (27.98-27.98) | 0/1 |
| otel | sweep r1 | frontend-pause | pause | 0.2 | 1 | 1/1 2.83 (2.83-2.83) | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 1/1 2.84 (2.84-2.84) | 0/1 |
| otel | sweep r1 | frontend-pause | pause | 1 | 1 | 1/1 0.62 (0.62-0.62) | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 1/1 0.62 (0.62-0.62) | 0/1 |
| otel | sweep r1 | frontend-pause | pause | 10 | 1 | 1/1 0.47 (0.47-0.47) | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 1/1 0.48 (0.48-0.48) | 0/1 |
| otel | sweep r1 | productcatalog-cpu-throttle | degradation | 0.05 | 1 | 1/1 45.48 (45.48-45.48) | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| otel | sweep r1 | productcatalog-cpu-throttle | degradation | 0.2 | 1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| otel | sweep r1 | productcatalog-cpu-throttle | degradation | 1 | 1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| otel | sweep r1 | productcatalog-cpu-throttle | degradation | 10 | 1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| teastore | B | auth-freeze | pause | 0.05 | 3 | 3/3 10.44 (1.35-16.68) | 0/3 | 3/3 10.18 (9.07-11.60) | 0/3 | 3/3 10.18 (9.07-11.60) | 0/3 | — | 3/3 10.53 (1.43-16.77) | 0/3 |
| teastore | B | auth-freeze | pause | 0.2 | 3 | 3/3 4.65 (2.79-5.92) | 0/3 | 3/3 10.20 (9.89-11.67) | 0/3 | 3/3 10.20 (9.89-11.67) | 0/3 | — | 3/3 4.71 (2.83-5.96) | 0/3 |
| teastore | B | auth-freeze | pause | 1 | 3 | 3/3 1.50 (1.16-1.59) | 3/3 | 3/3 11.60 (10.07-11.75) | 0/3 | 3/3 11.60 (10.07-11.75) | 0/3 | — | 3/3 1.62 (1.28-1.71) | 0/3 |
| teastore | B | auth-freeze | pause | 10 | 3 | 3/3 0.48 (0.47-0.52) | 3/3 | 3/3 10.10 (10.09-10.26) | 0/3 | 3/3 10.10 (10.09-10.26) | 0/3 | — | 3/3 0.51 (0.51-0.55) | 0/3 |
| teastore | B | persistence-cpu-throttle | degradation | 0.05 | 3 | 3/3 2.61 (2.28-5.32) | 3/3 | 0/3 | 0/3 | 0/3 | 0/3 | — | 3/3 7.75 (5.45-57.41) | 3/3 |
| teastore | B | persistence-cpu-throttle | degradation | 0.2 | 3 | 3/3 2.41 (0.93-3.30) | 3/3 | 1/3 55.16 (55.16-55.16) | 1/3 | 1/3 55.16 (55.16-55.16) | 0/3 | — | 3/3 3.47 (2.55-18.59) | 3/3 |
| teastore | B | persistence-cpu-throttle | degradation | 1 | 3 | 3/3 1.15 (0.88-4.48) | 3/3 | 1/3 30.44 (30.44-30.44) | 1/3 | 1/3 30.44 (30.44-30.44) | 0/3 | — | 3/3 2.17 (1.86-2.82) | 3/3 |
| teastore | B | persistence-cpu-throttle | degradation | 10 | 3 | 3/3 1.28 (0.46-1.48) | 3/3 | 2/3 30.55 (29.79-31.30) | 2/3 | 2/3 30.55 (29.79-31.30) | 0/3 | — | 3/3 0.41 (0.29-1.30) | 3/3 |
| teastore | C | auth-freeze | pause | 0.05 | 3 | 3/3 6.86 (2.23-18.37) | 0/3 | 3/3 10.86 (9.18-11.72) | 0/3 | 3/3 10.86 (9.18-11.72) | 0/3 | — | 3/3 6.93 (2.32-18.44) | 0/3 |
| teastore | C | auth-freeze | pause | 0.2 | 3 | 3/3 4.45 (3.70-6.46) | 0/3 | 3/3 11.27 (10.57-11.57) | 0/3 | 3/3 11.27 (10.57-11.57) | 0/3 | — | 3/3 4.48 (3.75-6.50) | 0/3 |
| teastore | C | auth-freeze | pause | 1 | 3 | 3/3 1.49 (0.93-1.66) | 3/3 | 3/3 10.51 (9.66-11.56) | 0/3 | 3/3 10.51 (9.66-11.56) | 0/3 | — | 3/3 1.61 (1.04-1.78) | 0/3 |
| teastore | C | auth-freeze | pause | 10 | 3 | 3/3 0.45 (0.45-0.45) | 3/3 | 3/3 11.43 (9.79-11.73) | 0/3 | 3/3 11.43 (9.79-11.73) | 0/3 | — | 3/3 0.48 (0.48-0.49) | 0/3 |
| teastore | C | persistence-cpu-throttle | degradation | 0.05 | 3 | 3/3 2.06 (0.43-3.12) | 3/3 | 1/3 21.52 (21.52-21.52) | 1/3 | 1/3 21.52 (21.52-21.52) | 0/3 | — | 3/3 18.27 (0.58-27.20) | 3/3 |
| teastore | C | persistence-cpu-throttle | degradation | 0.2 | 3 | 3/3 4.79 (1.78-5.53) | 3/3 | 1/3 53.14 (53.14-53.14) | 1/3 | 1/3 53.14 (53.14-53.14) | 0/3 | — | 3/3 5.67 (4.94-21.92) | 3/3 |
| teastore | C | persistence-cpu-throttle | degradation | 1 | 3 | 3/3 3.60 (0.26-4.62) | 3/3 | 2/3 26.43 (19.50-33.36) | 2/3 | 2/3 26.43 (19.50-33.36) | 0/3 | — | 3/3 1.48 (0.52-5.03) | 3/3 |
| teastore | C | persistence-cpu-throttle | degradation | 10 | 3 | 3/3 0.92 (0.48-1.06) | 3/3 | 3/3 29.61 (17.56-59.05) | 2/3 | 3/3 29.61 (17.56-59.05) | 0/3 | — | 3/3 0.93 (0.63-1.28) | 3/3 |
| teastore | sweep r2 | auth-freeze | pause | 0.05 | 1 | 1/1 6.74 (6.74-6.74) | 0/1 | 1/1 9.45 (9.45-9.45) | 0/1 | 1/1 9.45 (9.45-9.45) | 0/1 | — | 1/1 6.82 (6.82-6.82) | 0/1 |
| teastore | sweep r2 | auth-freeze | pause | 0.2 | 1 | 1/1 6.56 (6.56-6.56) | 0/1 | 1/1 10.59 (10.59-10.59) | 0/1 | 1/1 10.59 (10.59-10.59) | 0/1 | — | 1/1 6.61 (6.61-6.61) | 0/1 |
| teastore | sweep r2 | auth-freeze | pause | 1 | 1 | 1/1 0.94 (0.94-0.94) | 1/1 | 1/1 11.41 (11.41-11.41) | 0/1 | 1/1 11.41 (11.41-11.41) | 0/1 | — | 1/1 1.06 (1.06-1.06) | 0/1 |
| teastore | sweep r2 | auth-freeze | pause | 10 | 1 | 1/1 0.51 (0.51-0.51) | 1/1 | 1/1 10.20 (10.20-10.20) | 0/1 | 1/1 10.20 (10.20-10.20) | 0/1 | — | 1/1 0.54 (0.54-0.54) | 0/1 |
| teastore | sweep r2 | persistence-cpu-throttle | degradation | 0.05 | 1 | 1/1 3.88 (3.88-3.88) | 1/1 | 1/1 47.98 (47.98-47.98) | 1/1 | 1/1 47.98 (47.98-47.98) | 0/1 | — | 1/1 34.02 (34.02-34.02) | 1/1 |
| teastore | sweep r2 | persistence-cpu-throttle | degradation | 0.2 | 1 | 1/1 3.97 (3.97-3.97) | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 | — | 1/1 9.19 (9.19-9.19) | 1/1 |
| teastore | sweep r2 | persistence-cpu-throttle | degradation | 1 | 1 | 1/1 1.01 (1.01-1.01) | 1/1 | 1/1 44.66 (44.66-44.66) | 1/1 | 1/1 44.66 (44.66-44.66) | 0/1 | — | 1/1 2.93 (2.93-2.93) | 1/1 |
| teastore | sweep r2 | persistence-cpu-throttle | degradation | 10 | 1 | 1/1 0.29 (0.29-0.29) | 1/1 | 1/1 57.68 (57.68-57.68) | 0/1 | 1/1 57.68 (57.68-57.68) | 0/1 | — | 1/1 0.23 (0.23-0.23) | 1/1 |

## Table 2: coordinator failure, SUT x fault kind

Classes (first match): hit counted; (d) counted field miss but a by-construction hit; (a) no coordinator collected (Hotel); (c) fault target is not a member of the coordinator (OTel: not an accounting/frauddetection Kafka group member); (b) member, fault is a throttle/delay (no failure record in the window, hence heartbeats/session survived); (e) member, pause, no hit (unexplained). (a), (b), (c) are assigned from fault kind and membership (`MEMBERS` in the script), not measured heartbeat liveness; the *absence* of a failure record is the measurement.

| system | fault | kind | target | episodes | hit counted | (d) by-constr. only | (a) structural | (b) heartbeat alive | (c) not registered | (e) unexplained |
|---|---|---|---|---|---|---|---|---|---|---|
| hotel | cpu-throttle | degradation | profile | 16 | 0 | 0 | 16 | 0 | 0 | 0 |
| hotel | net-delay | degradation | rate | 16 | 0 | 0 | 16 | 0 | 0 | 0 |
| hotel | search-pause | pause | search | 16 | 0 | 0 | 16 | 0 | 0 | 0 |
| otel | accounting-pause | pause | accountingservice | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| otel | fraud-pause | pause | frauddetectionservice | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| otel | frontend-pause | pause | frontend | 33 | 0 | 0 | 0 | 0 | 33 | 0 |
| otel | productcatalog-cpu-throttle | degradation | productcatalogservice | 28 | 0 | 0 | 0 | 0 | 28 | 0 |
| teastore | auth-freeze | pause | auth | 28 | 0 | 28 | 0 | 0 | 0 | 0 |
| teastore | persistence-cpu-throttle | degradation | persistence | 28 | 12 | 2 | 0 | 14 | 0 | 0 |

## Table 3: traffic dependence (median ttdAny per rate; Spearman rho of log10 rate vs ttdAny over detected episodes)

| system | fault | lane | rate 0.05 | rate 0.2 | rate 1 | rate 10 | rate 25 | n detected | rho |
|---|---|---|---|---|---|---|---|---|---|
| hotel | cpu-throttle | own | 4/4 2.60 | 3/4 6.92 | 1/4 14.74 | 4/4 4.76 | — | 12 | 0.47 |
| hotel | cpu-throttle | ledger | 0/4 — | 1/4 27.02 | 0/4 — | 2/4 19.11 | — | 3 | — |
| hotel | net-delay | own | 4/4 4.35 | 4/4 2.16 | 4/4 0.53 | 4/4 0.16 | — | 16 | -0.90 |
| hotel | net-delay | ledger | 4/4 12.39 | 4/4 2.46 | 4/4 0.64 | 4/4 0.17 | — | 16 | -0.92 |
| hotel | search-pause | own | 4/4 11.76 | 4/4 3.78 | 4/4 1.19 | 4/4 0.24 | — | 16 | -0.97 |
| hotel | search-pause | ledger | 4/4 11.48 | 4/4 4.77 | 4/4 1.20 | 4/4 0.25 | — | 16 | -0.92 |
| otel | accounting-pause | own | — | — | — | — | 5/5 1.34 | 5 | — |
| otel | accounting-pause | coordinator | — | — | — | — | 5/5 44.18 | 5 | — |
| otel | accounting-pause | ledger | — | — | — | — | 1/5 37.19 | 1 | — |
| otel | fraud-pause | own | — | — | — | — | 5/5 1.28 | 5 | — |
| otel | fraud-pause | coordinator | — | — | — | — | 5/5 43.85 | 5 | — |
| otel | fraud-pause | ledger | — | — | — | — | 2/5 32.92 | 2 | — |
| otel | frontend-pause | own | 7/7 20.10 | 7/7 4.98 | 7/7 1.04 | 7/7 0.46 | 5/5 0.35 | 33 | -0.97 |
| otel | frontend-pause | coordinator | 0/7 — | 0/7 — | 0/7 — | 0/7 — | 0/5 — | 0 | — |
| otel | frontend-pause | ledger | 7/7 21.12 | 7/7 4.98 | 7/7 1.04 | 7/7 0.47 | 5/5 0.35 | 33 | -0.98 |
| otel | productcatalog-cpu-throttle | own | 2/7 52.22 | 0/7 — | 0/7 — | 1/7 0.21 | — | 3 | — |
| otel | productcatalog-cpu-throttle | coordinator | 0/7 — | 0/7 — | 0/7 — | 0/7 — | — | 0 | — |
| otel | productcatalog-cpu-throttle | ledger | 0/7 — | 0/7 — | 1/7 58.98 | 0/7 — | — | 1 | — |
| teastore | auth-freeze | own | 7/7 6.86 | 7/7 4.65 | 7/7 1.49 | 7/7 0.47 | — | 28 | -0.88 |
| teastore | auth-freeze | coordinator | 7/7 10.18 | 7/7 10.59 | 7/7 11.41 | 7/7 10.20 | — | 28 | 0.07 |
| teastore | auth-freeze | ledger | 7/7 6.93 | 7/7 4.71 | 7/7 1.61 | 7/7 0.51 | — | 28 | -0.88 |
| teastore | persistence-cpu-throttle | own | 7/7 2.61 | 7/7 3.30 | 7/7 1.15 | 7/7 0.92 | — | 28 | -0.47 |
| teastore | persistence-cpu-throttle | coordinator | 2/7 34.75 | 2/7 54.15 | 4/7 31.90 | 6/7 30.55 | — | 14 | -0.09 |
| teastore | persistence-cpu-throttle | ledger | 7/7 18.27 | 7/7 5.67 | 7/7 2.17 | 7/7 0.63 | — | 28 | -0.78 |

rho is `—` below 4 detected episodes or with one rate only. It is a descriptive rank correlation on one SUT's instance, not a test.
