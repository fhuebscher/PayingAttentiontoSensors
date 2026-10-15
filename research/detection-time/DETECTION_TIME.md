# Time to detection: ledger vs every sensor, on retained evidence

Protocol draft 3, decisions 14 and 15 (spatio-temporal objective: per fault, detected or not, time to detection, impact before detection; traffic per route as a parameter; primary outcome = time to detection with misses charged at the window end, averaged over episodes), with decisions 9-11 and OFFLINE_RESULTS round 4 (ledger spread per request; a single-sample spike counts only on the affected call path inside the fault window, here approximated at service level; BC-caller-log).

**Scope: instance.** Retained evidence, one host and one campaign per population, populations never pooled. The online rules below are engineering defaults chosen for this analysis, not a preregistered rule: K, the floors, the run length, the silence multiplier and the no-fault window placement are recorded in the script's docstring. Unknown is `?` or `—`; a share with denominator 0 is never printed. Status: built 2026-10-02 by a subagent; one independent adversarial review (Opus; Fable was rate-limited) applied, see the end.

## Commands

    rm -rf ~/Library/Caches/com.apple.python/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/research
    /usr/bin/python3 -B research/detection-time/detection_time.py --self-check
    /usr/bin/python3 -B research/detection-time/detection_time.py      # ~215 s; writes out/detection_time.json and this file

Run: framework commit `0949f2b702ff` (HEAD at run time; this script uncommitted, sha256 `2ca61dd7ac2a17cf`), Python 3.9.6, 200 seeds per (cell, thinning fraction).

## What was measured, per population

| population | evidence | valid fault episodes | no-fault windows per posture (cells) | onset bound | onset offset / hold (s) | command duration (s) | ledger rate | metric cadence, measured | log stamps |
|---|---|---|---|---|---|---|---|---|---|
| hotel-lmt2 | `tmp/hotellmt2-evidence/x` | 64 | full 20 (4), logs 20 (4), metrics 20 (4), none 20 (4) | fault-receipt startedMonotonic | 45.15 / 15.03 | 0.05–0.27 | 10 request/s (10 req/s) | cgroup-sampler 5.00 s, docker-stats 3.07 s | whole seconds |
| hotel-sel1 | `tmp/hotelsel1-evidence/x` | 64 | full 20 (4), metrics 20 (4), none 20 (4), selected 20 (4) | fault-receipt startedMonotonic | 45.15 / 15.03 | 0.05–0.28 | 10 request/s (10 req/s) | cgroup-sampler 5.00 s, docker-stats 3.07 s | whole seconds |
| hotel-int1 | `tmp/hotelint1-evidence/x` | 64 | full 20 (4), metrics 20 (4), none 20 (4), selected 20 (4) | fault-receipt startedMonotonic | 45.16 / 15.06 | 0.05–0.26 | 10 request/s (10 req/s) | cgroup-sampler 5.00 s, docker-stats 3.07 s | whole seconds |
| teastore-T16 | `tmp/teastore16-evidence/x/teastore-candidate-pilot-v1` | 18 | full 6 (3), none 6 (3), selected 6 (3) | intervention measurementBarrier.scheduledOnset* | 180.00 / 155.72 | 0.18–10.94 | 0.152 journey/s (1.94 req/s) | — | sub-second |
| otel-v3 | `tmp/otel-v3-evidence/runs` | 12 | async 6 (3), full 6 (3), none 6 (3), selected 6 (3) | intervention actualOnsetMonotonicOffsetSeconds (pre-command stamp) | 180.31 / 155.51 | — | 1 request/s (1 req/s) | — | — |

Onset check (F-ADH-085): hotel-lmt2 64/64 episodes with the bound at or before the post-command stamp; hotel-sel1 64/64 episodes with the bound at or before the post-command stamp; hotel-int1 64/64 episodes with the bound at or before the post-command stamp; teastore-T16 18/18 episodes with the bound at or before the post-command stamp; otel-v3 — (no post-command stamp retained; the bound is the pre-command stamp by the code order). Hotel's bound is pre-command by statement order (lmt_faults.py / compose_pause.py), so its check only confirms the order was kept; TeaStore's scheduled onset is computed (barrier + 180 s), not stamped.

Resolution per channel: spans and ledger requests are per record (observation = end of the span / request); logs are per record at the stamp resolution above; docker stats (M) and the cgroup sampler (S) at the measured cadence (Hotel only; TeaStore T16 retained no metric channel, OTel v3 is read for its ledger only). docker stats' declared `intervalSeconds` is 1.0 but the measured gap is the one printed (`docker stats --no-stream` takes ~3 s per round). A time to detection below a channel's cadence is not resolvable on that channel.

## 0. Primary outcome (decision 15): time to detection, misses charged at the hold end, averaged over episodes

Seconds from the command bound; a family that misses an episode is charged that episode's hold. Each cell: with BC / without BC catches. Outside the target (G2), except `E:own` (OTel: the target is the entry). n per cell as in table 1. These means inherit every limit of the rules and of n (4 per Hotel cell, 3 per TeaStore and OTel cell); read them with the false-alarm columns of table 1, which this mean does not charge.

**hotel-lmt2** (hold 15.0 s)

| class | posture | n | E | L | M | S | T |
|---|---|---|---|---|---|---|---|
| cpu-throttle | none | 4 | 15.05 / 15.05 | — | — | 14.99 / 14.99 | — |
| cpu-throttle | logs | 4 | 15.05 / 15.05 | 15.05 / 15.05 | — | 15.05 / 15.05 | — |
| cpu-throttle | metrics | 4 | 15.06 / 15.06 | 15.06 / 15.06 | 13.19 / 13.19 | 13.74 / 13.74 | — |
| cpu-throttle | full | 4 | 15.05 / 15.05 | 15.05 / 15.05 | 15.05 / 15.05 | 14.99 / 14.99 | 15.05 / 15.05 |
| net-delay | none | 4 | 0.51 / 0.51 | — | — | 14.95 / 14.95 | — |
| net-delay | logs | 4 | 0.56 / 0.56 | 15.06 / 15.06 | — | 15.01 / 15.01 | — |
| net-delay | metrics | 4 | 0.55 / 0.55 | 15.07 / 15.07 | 13.19 / 13.19 | 12.51 / 12.51 | — |
| net-delay | full | 4 | 0.54 / 0.54 | 15.06 / 15.06 | 15.06 / 15.06 | 15.06 / 15.06 | 0.39 / 0.39 |
| reservation-pause | none | 4 | 1.17 / 15.00 | — | — | 14.97 / 14.97 | — |
| reservation-pause | logs | 4 | 1.16 / 15.00 | 1.64 / 15.00 | — | 14.97 / 14.97 | — |
| reservation-pause | metrics | 4 | 1.16 / 15.00 | 1.54 / 15.00 | 3.02 / 15.00 | 13.71 / 13.71 | — |
| reservation-pause | full | 4 | 1.16 / 15.00 | 1.75 / 15.00 | 7.63 / 15.00 | 13.68 / 13.68 | 1.16 / 1.16 |
| search-pause | none | 4 | 1.15 / 15.00 | — | — | 15.00 / 15.00 | — |
| search-pause | logs | 4 | 1.16 / 15.00 | 15.00 / 15.00 | — | 9.93 / 9.93 | — |
| search-pause | metrics | 4 | 1.16 / 15.00 | 15.00 / 15.00 | 1.49 / 15.00 | 14.96 / 14.96 | — |
| search-pause | full | 4 | 1.16 / 15.00 | 15.00 / 15.00 | 1.49 / 15.00 | 7.39 / 7.39 | 1.16 / 1.16 |

**hotel-sel1** (hold 15.0 s)

| class | posture | n | E | L | M | S | Tsel | T |
|---|---|---|---|---|---|---|---|---|
| cpu-throttle | none | 4 | 15.05 / 15.05 | — | — | 14.87 / 14.87 | — | — |
| cpu-throttle | metrics | 4 | 15.06 / 15.06 | 15.06 / 15.06 | 15.06 / 15.06 | 14.99 / 14.99 | — | — |
| cpu-throttle | selected | 4 | 15.05 / 15.05 | 15.05 / 15.05 | 15.05 / 15.05 | 14.93 / 14.93 | 15.05 / 15.05 | — |
| cpu-throttle | full | 4 | 15.05 / 15.05 | 15.05 / 15.05 | 15.05 / 15.05 | 15.05 / 15.05 | — | 15.05 / 15.05 |
| net-delay | none | 4 | 0.56 / 0.56 | — | — | 13.65 / 13.65 | — | — |
| net-delay | metrics | 4 | 0.54 / 0.54 | 15.06 / 15.06 | 11.34 / 11.34 | 14.96 / 14.96 | — | — |
| net-delay | selected | 4 | 0.54 / 0.54 | 15.07 / 15.07 | 11.34 / 11.34 | 12.46 / 12.46 | 0.41 / 0.41 | — |
| net-delay | full | 4 | 0.51 / 0.51 | 15.07 / 15.07 | 13.21 / 13.21 | 15.07 / 15.07 | — | 0.40 / 0.40 |
| reservation-pause | none | 4 | 1.15 / 15.00 | — | — | 14.92 / 14.92 | — | — |
| reservation-pause | metrics | 4 | 1.16 / 15.00 | 1.61 / 15.00 | 3.02 / 15.00 | 13.68 / 13.68 | — | — |
| reservation-pause | selected | 4 | 1.17 / 15.00 | 1.95 / 15.00 | 1.49 / 15.00 | 13.72 / 13.72 | 1.17 / 1.17 | — |
| reservation-pause | full | 4 | 1.17 / 15.00 | 1.64 / 15.00 | 1.49 / 15.00 | 13.65 / 13.65 | — | 1.17 / 1.17 |
| search-pause | none | 4 | 1.17 / 15.00 | — | — | 15.00 / 15.00 | — | — |
| search-pause | metrics | 4 | 1.16 / 15.00 | 15.00 / 15.00 | 1.49 / 15.00 | 12.47 / 12.47 | — | — |
| search-pause | selected | 4 | 1.17 / 15.00 | 15.00 / 15.00 | 1.48 / 15.00 | 9.90 / 9.90 | 1.17 / 1.17 | — |
| search-pause | full | 4 | 1.16 / 15.00 | 15.00 / 15.00 | 1.48 / 15.00 | 12.43 / 12.43 | — | 1.16 / 1.16 |

**hotel-int1** (hold 15.1 s)

| class | posture | n | E | L | M | S | Tsel | T |
|---|---|---|---|---|---|---|---|---|
| cpu-throttle | none | 4 | 15.06 / 15.06 | — | — | 14.87 / 14.87 | — | — |
| cpu-throttle | metrics | 4 | 15.05 / 15.05 | 15.05 / 15.05 | 15.05 / 15.05 | 15.05 / 15.05 | — | — |
| cpu-throttle | selected | 4 | 15.06 / 15.06 | 15.06 / 15.06 | 15.06 / 15.06 | 11.12 / 11.12 | 15.06 / 15.06 | — |
| cpu-throttle | full | 4 | 15.05 / 15.05 | 15.05 / 15.05 | 15.05 / 15.05 | 15.05 / 15.05 | — | 15.05 / 15.05 |
| geo-delay | none | 4 | 1.08 / 1.08 | — | — | 13.76 / 13.76 | — | — |
| geo-delay | metrics | 4 | 1.36 / 1.36 | 15.07 / 15.07 | 15.07 / 15.07 | 11.21 / 11.21 | — | — |
| geo-delay | selected | 4 | 7.73 / 7.73 | 15.06 / 15.06 | 15.06 / 15.06 | 15.06 / 15.06 | 0.30 / 0.30 | — |
| geo-delay | full | 4 | 15.06 / 15.06 | 15.06 / 15.06 | 15.06 / 15.06 | 15.06 / 15.06 | — | 0.06 / 0.06 |
| rate-delay | none | 4 | 0.49 / 0.49 | — | — | 13.76 / 13.76 | — | — |
| rate-delay | metrics | 4 | 1.16 / 1.16 | 15.08 / 15.08 | 13.98 / 13.98 | 13.70 / 13.70 | — | — |
| rate-delay | selected | 4 | 10.86 / 10.86 | 15.06 / 15.06 | 15.06 / 15.06 | 15.06 / 15.06 | 0.26 / 0.26 | — |
| rate-delay | full | 4 | 14.74 / 14.74 | 15.06 / 15.06 | 13.20 / 13.20 | 15.06 / 15.06 | — | 0.20 / 0.20 |
| search-pause | none | 4 | 1.16 / 15.00 | — | — | 12.43 / 12.43 | — | — |
| search-pause | metrics | 4 | 1.17 / 15.00 | 15.00 / 15.00 | 1.49 / 15.00 | 15.00 / 15.00 | — | — |
| search-pause | selected | 4 | 1.17 / 15.00 | 15.00 / 15.00 | 7.63 / 15.00 | 9.90 / 9.90 | 1.17 / 1.17 | — |
| search-pause | full | 4 | 1.16 / 15.00 | 15.00 / 15.00 | 1.49 / 15.00 | 8.61 / 8.61 | — | 1.16 / 1.16 |

**teastore-T16** (hold 155.7 s)

| class | posture | n | E | L | Tsel | T |
|---|---|---|---|---|---|---|
| auth-freeze | none | 3 | 15.24 / 150.42 | 150.42 / 150.42 | — | — |
| auth-freeze | selected | 3 | 15.25 / 150.40 | 150.40 / 150.40 | 12.58 / 150.40 | — |
| auth-freeze | full | 3 | 15.26 / 150.44 | 150.44 / 150.44 | — | 12.42 / 23.88 |
| persistence-crash | none | 3 | 16.79 / 161.02 | 13.39 / 161.02 | — | — |
| persistence-crash | selected | 3 | 17.26 / 161.08 | 13.40 / 161.08 | 19.65 / 149.61 | — |
| persistence-crash | full | 3 | 17.82 / 161.05 | 13.39 / 161.05 | — | 13.42 / 13.42 |

**otel-v3** (hold 155.5 s)

| class | posture | n | E:own | E |
|---|---|---|---|---|
| frontend-pause | none | 3 | 15.69 / 155.54 | 155.54 / 155.54 |
| frontend-pause | selected | 3 | 12.71 / 155.51 | 155.51 / 155.51 |
| frontend-pause | async | 3 | 15.73 / 155.51 | 155.51 / 155.51 |
| frontend-pause | full | 3 | 15.68 / 155.54 | 155.54 / 155.54 |

## 1. Time to detection per (fault class, posture, family), by-construction catches included

Each cell: detected k/n episodes · time to detection in seconds from the command bound, median [min–max] over the detected ones · **mean over all n episodes with misses charged at the hold end** (decision 15's primary outcome, bold; the same number as table 0). Hotel log stamps are whole seconds, so a log record stamped s is timed at s + 1 (the instant it certainly existed); the lower end s is in the JSON (`fires[i][4]`). Family false-alarm rate in no-fault windows of the same posture, leave-one-cell-out, same filters: k/n windows (median time to the first false alarm). Outside the target only (G2); the ledger family E counts its rules failed / spike / run3 / median. `—`: the posture does not collect the family.

**hotel-lmt2**

| class (target, kind) | posture | n | E | FA E | L | FA L | M | FA M | S | FA S | T | FA T |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cpu-throttle (profile, degradation) | none | 4 | 0/4 · **15.05** | 0/20 | — | — | — | — | 1/4 · 14.82 · **14.99** | 5/20 (14.8 s) | — | — |
| cpu-throttle (profile, degradation) | logs | 4 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | — | — | 0/4 · **15.05** | 2/20 (14.9 s) | — | — |
| cpu-throttle (profile, degradation) | metrics | 4 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 1/4 · 7.58 · **13.19** | 1/20 (2.1 s) | 1/4 · 9.81 · **13.74** | 2/20 (14.8 s) | — | — |
| cpu-throttle (profile, degradation) | full | 4 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 1/4 · 14.81 · **14.99** | 0/20 | 0/4 · **15.05** | 0/20 |
| net-delay (rate, degradation) | none | 4 | 4/4 · 0.52 [0.46–0.56] · **0.51** | 0/20 | — | — | — | — | 2/4 · 14.85 [14.84–14.85] · **14.95** | 5/20 (14.8 s) | — | — |
| net-delay (rate, degradation) | logs | 4 | 4/4 · 0.56 [0.56–0.57] · **0.56** | 0/20 | 0/4 · **15.06** | 0/20 | — | — | 1/4 · 14.86 · **15.01** | 2/20 (14.9 s) | — | — |
| net-delay (rate, degradation) | metrics | 4 | 4/4 · 0.56 [0.50–0.57] · **0.55** | 0/20 | 0/4 · **15.07** | 0/20 | 1/4 · 7.57 · **13.19** | 1/20 (2.1 s) | 1/4 · 4.86 · **12.51** | 2/20 (14.8 s) | — | — |
| net-delay (rate, degradation) | full | 4 | 4/4 · 0.56 [0.47–0.57] · **0.54** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 4/4 · 0.37 [0.37–0.46] · **0.39** | 0/20 |
| reservation-pause (reservation, pause) | none | 4 | 4/4 · 1.17 [1.16–1.17] · **1.17** | 0/20 | — | — | — | — | 1/4 · 14.86 · **14.97** | 5/20 (14.8 s) | — | — |
| reservation-pause (reservation, pause) | logs | 4 | 4/4 · 1.16 [1.16–1.17] · **1.16** | 0/20 | 4/4 · 1.60 [1.22–2.13] · **1.64** | 0/20 | — | — | 1/4 · 14.87 · **14.97** | 2/20 (14.9 s) | — | — |
| reservation-pause (reservation, pause) | metrics | 4 | 4/4 · 1.16 [1.16–1.17] · **1.16** | 0/20 | 4/4 · 1.49 [1.25–1.92] · **1.54** | 0/20 | 4/4 · 1.49 [1.48–7.63] · **3.02** | 1/20 (2.1 s) | 1/4 · 9.86 · **13.71** | 2/20 (14.8 s) | — | — |
| reservation-pause (reservation, pause) | full | 4 | 4/4 · 1.16 [1.13–1.17] · **1.16** | 0/20 | 4/4 · 1.74 [1.54–1.98] · **1.75** | 0/20 | 4/4 · 7.64 [7.59–7.65] · **7.63** | 0/20 | 2/4 · 12.36 [9.86–14.86] · **13.68** | 0/20 | 4/4 · 1.16 [1.13–1.17] · **1.16** | 0/20 |
| search-pause (search, pause) | none | 4 | 4/4 · 1.16 [1.13–1.17] · **1.15** | 0/20 | — | — | — | — | 0/4 · **15.00** | 5/20 (14.8 s) | — | — |
| search-pause (search, pause) | logs | 4 | 4/4 · 1.17 [1.15–1.17] · **1.16** | 0/20 | 0/4 · **15.00** | 0/20 | — | — | 2/4 · 4.86 [4.86–4.86] · **9.93** | 3/20 (9.9 s) | — | — |
| search-pause (search, pause) | metrics | 4 | 4/4 · 1.17 [1.16–1.17] · **1.16** | 0/20 | 0/4 · **15.00** | 0/20 | 4/4 · 1.49 [1.48–1.49] · **1.49** | 2/20 (4.9 s) | 1/4 · 14.86 · **14.96** | 2/20 (14.8 s) | — | — |
| search-pause (search, pause) | full | 4 | 4/4 · 1.16 [1.16–1.17] · **1.16** | 0/20 | 0/4 · **15.00** | 0/20 | 4/4 · 1.50 [1.47–1.51] · **1.49** | 0/20 | 3/4 · 4.86 [4.85–4.87] · **7.39** | 1/20 (9.8 s) | 4/4 · 1.16 [1.16–1.17] · **1.16** | 0/20 |

Own sensors of the target (G2, reported apart): cpu-throttle none S:own 4/4 · 4.81 [4.79–9.78] · **6.05**; cpu-throttle logs S:own 3/4 · 4.81 [4.80–4.82] · **7.37**; cpu-throttle metrics S:own 4/4 · 4.80 [4.79–4.82] · **4.80**; cpu-throttle full S:own 4/4 · 4.81 [4.81–4.82] · **4.81**; net-delay logs S:own 1/4 · 14.86 · **15.01**; net-delay metrics M:own 1/4 · 7.57 · **13.19**; net-delay full T:own 4/4 · 0.15 [0.15–0.16] · **0.16**; reservation-pause metrics M:own 4/4 · 1.49 [1.48–1.49] · **1.49**; reservation-pause full M:own 4/4 · 1.50 [1.45–1.50] · **1.49**; search-pause metrics M:own 4/4 · 1.49 [1.48–4.56] · **2.26**; search-pause full M:own 4/4 · 1.50 [1.47–1.51] · **1.49**.

**hotel-sel1**

| class (target, kind) | posture | n | E | FA E | L | FA L | M | FA M | S | FA S | Tsel | FA Tsel | T | FA T |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cpu-throttle (profile, degradation) | none | 4 | 0/4 · **15.05** | 0/20 | — | — | — | — | 3/4 · 14.81 [14.79–14.81] · **14.87** | 7/20 (14.7 s) | — | — | — | — |
| cpu-throttle (profile, degradation) | metrics | 4 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 1/20 (7.6 s) | 1/4 · 14.79 · **14.99** | 3/20 (14.8 s) | — | — | — | — |
| cpu-throttle (profile, degradation) | selected | 4 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 2/4 · 14.81 [14.81–14.81] · **14.93** | 2/20 (14.8 s) | 0/4 · **15.05** | 0/20 | — | — |
| cpu-throttle (profile, degradation) | full | 4 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 1/20 (14.8 s) | — | — | 0/4 · **15.05** | 0/20 |
| net-delay (rate, degradation) | none | 4 | 4/4 · 0.56 [0.55–0.57] · **0.56** | 0/20 | — | — | — | — | 3/4 · 14.84 [9.85–14.85] · **13.65** | 7/20 (14.7 s) | — | — | — | — |
| net-delay (rate, degradation) | metrics | 4 | 4/4 · 0.56 [0.47–0.57] · **0.54** | 0/20 | 0/4 · **15.06** | 0/20 | 2/4 · 7.62 [7.61–7.62] · **11.34** | 1/20 (7.6 s) | 2/4 · 14.85 [14.84–14.86] · **14.96** | 4/20 (12.3 s) | — | — | — | — |
| net-delay (rate, degradation) | selected | 4 | 4/4 · 0.57 [0.47–0.57] · **0.54** | 0/20 | 0/4 · **15.07** | 0/20 | 2/4 · 7.62 [7.62–7.63] · **11.34** | 0/20 | 2/4 · 9.85 [4.85–14.86] · **12.46** | 3/20 (14.8 s) | 4/4 · 0.41 [0.36–0.46] · **0.41** | 0/20 | — | — |
| net-delay (rate, degradation) | full | 4 | 4/4 · 0.51 [0.43–0.56] · **0.51** | 0/20 | 0/4 · **15.07** | 0/20 | 1/4 · 7.63 · **13.21** | 0/20 | 0/4 · **15.07** | 1/20 (14.8 s) | — | — | 4/4 · 0.40 [0.37–0.46] · **0.40** | 0/20 |
| reservation-pause (reservation, pause) | none | 4 | 4/4 · 1.16 [1.13–1.17] · **1.15** | 0/20 | — | — | — | — | 2/4 · 14.84 [14.83–14.86] · **14.92** | 3/20 (9.8 s) | — | — | — | — |
| reservation-pause (reservation, pause) | metrics | 4 | 4/4 · 1.16 [1.16–1.17] · **1.16** | 0/20 | 4/4 · 1.60 [1.48–1.78] · **1.61** | 0/20 | 4/4 · 1.49 [1.46–7.62] · **3.02** | 1/20 (7.6 s) | 2/4 · 12.36 [9.86–14.85] · **13.68** | 2/20 (9.8 s) | — | — | — | — |
| reservation-pause (reservation, pause) | selected | 4 | 4/4 · 1.17 [1.15–1.18] · **1.17** | 0/20 | 4/4 · 1.94 [1.82–2.12] · **1.95** | 0/20 | 4/4 · 1.49 [1.48–1.50] · **1.49** | 0/20 | 1/4 · 9.87 · **13.72** | 2/20 (14.8 s) | 4/4 · 1.17 [1.15–1.18] · **1.17** | 0/20 | — | — |
| reservation-pause (reservation, pause) | full | 4 | 4/4 · 1.17 [1.17–1.17] · **1.17** | 0/20 | 4/4 · 1.51 [1.37–2.16] · **1.64** | 0/20 | 4/4 · 1.49 [1.49–1.50] · **1.49** | 0/20 | 3/4 · 14.87 [9.86–14.87] · **13.65** | 1/20 (14.8 s) | — | — | 4/4 · 1.17 [1.17–1.17] · **1.17** | 0/20 |
| search-pause (search, pause) | none | 4 | 4/4 · 1.17 [1.16–1.17] · **1.17** | 0/20 | — | — | — | — | 0/4 · **15.00** | 9/20 (14.8 s) | — | — | — | — |
| search-pause (search, pause) | metrics | 4 | 4/4 · 1.16 [1.16–1.17] · **1.16** | 0/20 | 0/4 · **15.00** | 0/20 | 4/4 · 1.49 [1.48–1.51] · **1.49** | 1/20 (7.6 s) | 1/4 · 4.86 · **12.47** | 3/20 (4.9 s) | — | — | — | — |
| search-pause (search, pause) | selected | 4 | 4/4 · 1.17 [1.16–1.17] · **1.17** | 0/20 | 0/4 · **15.00** | 0/20 | 4/4 · 1.48 [1.47–1.49] · **1.48** | 1/20 (7.6 s) | 3/4 · 4.87 [4.87–14.86] · **9.90** | 3/20 (4.9 s) | 4/4 · 1.17 [1.16–1.17] · **1.17** | 0/20 | — | — |
| search-pause (search, pause) | full | 4 | 4/4 · 1.16 [1.15–1.17] · **1.16** | 0/20 | 0/4 · **15.00** | 0/20 | 4/4 · 1.48 [1.47–1.50] · **1.48** | 0/20 | 2/4 · 9.85 [9.85–9.85] · **12.43** | 1/20 (14.9 s) | — | — | 4/4 · 1.16 [1.15–1.17] · **1.16** | 0/20 |

Own sensors of the target (G2, reported apart): cpu-throttle none S:own 3/4 · 4.81 [4.79–4.81] · **7.36**; cpu-throttle metrics S:own 4/4 · 4.81 [4.79–9.80] · **6.05**; cpu-throttle selected S:own 4/4 · 4.81 [4.79–9.81] · **6.05**; cpu-throttle full S:own 4/4 · 4.81 [4.81–4.81] · **4.81**; net-delay metrics M:own 1/4 · 7.61 · **13.20**; net-delay selected S:own 1/4 · 14.86 · **15.01**; net-delay full M:own 1/4 · 7.63 · **13.21**; net-delay full T:own 4/4 · 0.16 [0.15–0.17] · **0.16**; reservation-pause metrics M:own 4/4 · 1.48 [1.46–1.50] · **1.48**; reservation-pause selected M:own 4/4 · 1.50 [1.49–4.56] · **2.26**; reservation-pause full M:own 4/4 · 1.49 [1.49–4.56] · **2.26**; search-pause metrics M:own 4/4 · 1.49 [1.48–4.58] · **2.26**; search-pause selected M:own 4/4 · 1.48 [1.47–1.49] · **1.48**; search-pause full M:own 4/4 · 1.48 [1.47–1.50] · **1.48**.

**hotel-int1**

| class (target, kind) | posture | n | E | FA E | L | FA L | M | FA M | S | FA S | Tsel | FA Tsel | T | FA T |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cpu-throttle (profile, degradation) | none | 4 | 0/4 · **15.06** | 0/20 | — | — | — | — | 3/4 · 14.81 [14.79–14.82] · **14.87** | 1/20 (14.8 s) | — | — | — | — |
| cpu-throttle (profile, degradation) | metrics | 4 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 4/20 (14.7 s) | — | — | — | — |
| cpu-throttle (profile, degradation) | selected | 4 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 3/4 · 9.81 [4.82–14.81] · **11.12** | 0/20 | 0/4 · **15.06** | 0/20 | — | — |
| cpu-throttle (profile, degradation) | full | 4 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 1/20 (14.7 s) | — | — | 0/4 · **15.05** | 1/20 (0.3 s) |
| geo-delay (geo, degradation) | none | 4 | 4/4 · 0.36 [0.26–3.36] · **1.08** | 0/20 | — | — | — | — | 1/4 · 9.84 · **13.76** | 2/20 (9.8 s) | — | — | — | — |
| geo-delay (geo, degradation) | metrics | 4 | 4/4 · 0.95 [0.26–3.27] · **1.36** | 0/20 | 0/4 · **15.07** | 0/20 | 0/4 · **15.07** | 0/20 | 2/4 · 7.35 [4.83–9.86] · **11.21** | 3/20 (14.7 s) | — | — | — | — |
| geo-delay (geo, degradation) | selected | 4 | 2/4 · 0.40 [0.26–0.54] · **7.73** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 4/4 · 0.31 [0.14–0.47] · **0.30** | 0/20 | — | — |
| geo-delay (geo, degradation) | full | 4 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 1/20 (7.6 s) | 0/4 · **15.06** | 2/20 (14.8 s) | — | — | 4/4 · 0.06 [0.06–0.06] · **0.06** | 2/20 (1.0 s) |
| rate-delay (rate, degradation) | none | 4 | 4/4 · 0.37 [0.27–0.95] · **0.49** | 0/20 | — | — | — | — | 1/4 · 9.85 · **13.76** | 2/20 (9.8 s) | — | — | — | — |
| rate-delay (rate, degradation) | metrics | 4 | 4/4 · 0.51 [0.35–3.27] · **1.16** | 0/20 | 0/4 · **15.08** | 0/20 | 1/4 · 10.67 · **13.98** | 0/20 | 2/4 · 12.34 [9.84–14.85] · **13.70** | 4/20 (14.7 s) | — | — | — | — |
| rate-delay (rate, degradation) | selected | 4 | 2/4 · 6.67 [1.67–11.66] · **10.86** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 4/4 · 0.26 [0.16–0.36] · **0.26** | 0/20 | — | — |
| rate-delay (rate, degradation) | full | 4 | 1/4 · 13.76 · **14.74** | 0/20 | 0/4 · **15.06** | 0/20 | 1/4 · 7.61 · **13.20** | 1/20 (7.6 s) | 0/4 · **15.06** | 2/20 (14.8 s) | — | — | 4/4 · 0.20 [0.15–0.26] · **0.20** | 2/20 (1.0 s) |
| search-pause (search, pause) | none | 4 | 4/4 · 1.17 [1.14–1.17] · **1.16** | 0/20 | — | — | — | — | 2/4 · 9.85 [4.87–14.84] · **12.43** | 1/20 (14.8 s) | — | — | — | — |
| search-pause (search, pause) | metrics | 4 | 4/4 · 1.17 [1.16–1.17] · **1.17** | 0/20 | 0/4 · **15.00** | 0/20 | 4/4 · 1.49 [1.48–1.50] · **1.49** | 1/20 (14.9 s) | 0/4 · **15.00** | 4/20 (14.7 s) | — | — | — | — |
| search-pause (search, pause) | selected | 4 | 4/4 · 1.17 [1.17–1.17] · **1.17** | 0/20 | 0/4 · **15.00** | 0/20 | 4/4 · 7.63 [7.61–7.65] · **7.63** | 0/20 | 3/4 · 4.87 [4.86–14.86] · **9.90** | 0/20 | 4/4 · 1.17 [1.17–1.17] · **1.17** | 0/20 | — | — |
| search-pause (search, pause) | full | 4 | 4/4 · 1.17 [1.14–1.17] · **1.16** | 0/20 | 0/4 · **15.00** | 0/20 | 4/4 · 1.49 [1.46–1.50] · **1.49** | 1/20 (7.6 s) | 4/4 · 7.36 [4.86–14.84] · **8.61** | 3/20 (14.7 s) | — | — | 4/4 · 1.17 [1.14–1.17] · **1.16** | 0/20 |

Own sensors of the target (G2, reported apart): cpu-throttle none S:own 3/4 · 4.79 [4.67–4.81] · **7.33**; cpu-throttle metrics S:own 2/4 · 4.82 [4.82–4.82] · **9.94**; cpu-throttle selected S:own 3/4 · 4.81 [4.81–4.82] · **7.37**; cpu-throttle full S:own 3/4 · 4.81 [4.81–4.81] · **7.37**; cpu-throttle full T:own 1/4 · 2.72 · **11.97**; geo-delay metrics S:own 1/4 · 14.84 · **15.01**; geo-delay selected S:own 1/4 · 4.83 · **12.50**; rate-delay full T:own 4/4 · 0.20 [0.14–0.45] · **0.25**; search-pause metrics M:own 4/4 · 1.50 [1.49–4.55] · **2.26**; search-pause selected M:own 4/4 · 1.49 [1.47–1.50] · **1.49**; search-pause full M:own 4/4 · 1.50 [1.46–4.56] · **2.25**.

**teastore-T16**

| class (target, kind) | posture | n | E | FA E | L | FA L | Tsel | FA Tsel | T | FA T |
|---|---|---|---|---|---|---|---|---|---|---|
| auth-freeze (auth, pause) | none | 3 | 3/3 · 15.26 [15.17–15.29] · **15.24** | 1/6 (18.1 s) | 0/3 · **150.42** | ? (no records) | — | — | — | — |
| auth-freeze (auth, pause) | selected | 3 | 3/3 · 15.25 [15.22–15.30] · **15.25** | 0/6 | 0/3 · **150.40** | ? (no records) | 3/3 · 12.58 [12.55–12.61] · **12.58** | 2/6 (78.8 s) | — | — |
| auth-freeze (auth, pause) | full | 3 | 3/3 · 15.28 [15.21–15.29] · **15.26** | 0/6 | 0/3 · **150.44** | ? (no records) | — | — | 3/3 · 12.41 [12.41–12.44] · **12.42** | 5/6 (33.4 s) |
| persistence-crash (persistence, stop) | none | 3 | 3/3 · 17.04 [16.30–17.04] · **16.79** | 1/6 (18.1 s) | 3/3 · 13.39 [13.39–13.39] · **13.39** † | ? (no records) | — | — | — | — |
| persistence-crash (persistence, stop) | selected | 3 | 3/3 · 17.46 [16.70–17.64] · **17.26** | 0/6 | 3/3 · 13.39 [13.39–13.41] · **13.40** † | ? (no records) | 3/3 · 19.66 [19.56–19.71] · **19.65** | 0/6 | — | — |
| persistence-crash (persistence, stop) | full | 3 | 3/3 · 17.91 [17.55–18.00] · **17.82** | 0/6 | 3/3 · 13.39 [13.38–13.39] · **13.39** † | ? (no records) | — | — | 3/3 · 13.42 [13.41–13.43] · **13.42** | 1/6 (24.5 s) |

Own sensors of the target (G2, reported apart): auth-freeze selected Tsel:own 3/3 · 12.49 [12.49–12.50] · **12.49**; auth-freeze full T:own 3/3 · 12.50 [12.45–12.51] · **12.49**; persistence-crash selected Tsel:own 3/3 · 19.69 [19.59–19.74] · **19.68**; persistence-crash full T:own 3/3 · 19.62 [19.60–19.66] · **19.62**.

**otel-v3**

| class (target, kind) | posture | n | E:own | FA E:own | E | FA E |
|---|---|---|---|---|---|---|
| frontend-pause (frontend, pause) | none | 3 | 3/3 · 15.69 [15.67–15.71] · **15.69** | 0/6 | 0/3 · **155.54** | 0/6 |
| frontend-pause (frontend, pause) | selected | 3 | 3/3 · 15.70 [6.70–15.73] · **12.71** | 0/6 | 0/3 · **155.51** | 0/6 |
| frontend-pause (frontend, pause) | async | 3 | 3/3 · 15.72 [15.72–15.74] · **15.73** | 0/6 | 0/3 · **155.51** | 0/6 |
| frontend-pause (frontend, pause) | full | 3 | 3/3 · 15.68 [15.67–15.70] · **15.68** | 2/6 (75.0 s) | 0/3 · **155.54** | 0/6 |

Own sensors of the target (G2, reported apart): frontend-pause none E:own 3/3 · 15.69 [15.67–15.71] · **15.69**; frontend-pause selected E:own 3/3 · 15.70 [6.70–15.73] · **12.71**; frontend-pause async E:own 3/3 · 15.72 [15.72–15.74] · **15.73**; frontend-pause full E:own 3/3 · 15.68 [15.67–15.70] · **15.68**.

## 2. The same without by-construction catches

Every sensor-rule carrying a BC flag (BC-ledger-stopped-on-path, BC-caller-span, BC-idle-cpu, BC-downstream-absent, BC-caller-log) is dropped, in the fault windows and in the false-alarm count.

**hotel-lmt2**

| class (target, kind) | posture | n | E | FA E | L | FA L | M | FA M | S | FA S | T | FA T |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cpu-throttle (profile, degradation) | none | 4 | 0/4 · **15.05** | 0/20 | — | — | — | — | 1/4 · 14.82 · **14.99** | 5/20 (14.8 s) | — | — |
| cpu-throttle (profile, degradation) | logs | 4 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | — | — | 0/4 · **15.05** | 2/20 (14.9 s) | — | — |
| cpu-throttle (profile, degradation) | metrics | 4 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 1/4 · 7.58 · **13.19** | 1/20 (2.1 s) | 1/4 · 9.81 · **13.74** | 2/20 (14.8 s) | — | — |
| cpu-throttle (profile, degradation) | full | 4 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 1/4 · 14.81 · **14.99** | 0/20 | 0/4 · **15.05** | 0/20 |
| net-delay (rate, degradation) | none | 4 | 4/4 · 0.52 [0.46–0.56] · **0.51** | 0/20 | — | — | — | — | 2/4 · 14.85 [14.84–14.85] · **14.95** | 5/20 (14.8 s) | — | — |
| net-delay (rate, degradation) | logs | 4 | 4/4 · 0.56 [0.56–0.57] · **0.56** | 0/20 | 0/4 · **15.06** | 0/20 | — | — | 1/4 · 14.86 · **15.01** | 2/20 (14.9 s) | — | — |
| net-delay (rate, degradation) | metrics | 4 | 4/4 · 0.56 [0.50–0.57] · **0.55** | 0/20 | 0/4 · **15.07** | 0/20 | 1/4 · 7.57 · **13.19** | 1/20 (2.1 s) | 1/4 · 4.86 · **12.51** | 2/20 (14.8 s) | — | — |
| net-delay (rate, degradation) | full | 4 | 4/4 · 0.56 [0.47–0.57] · **0.54** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 4/4 · 0.37 [0.37–0.46] · **0.39** | 0/20 |
| reservation-pause (reservation, pause) | none | 4 | 0/4 · **15.00** | 0/20 | — | — | — | — | 1/4 · 14.86 · **14.97** | 5/20 (14.8 s) | — | — |
| reservation-pause (reservation, pause) | logs | 4 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | — | — | 1/4 · 14.87 · **14.97** | 2/20 (14.9 s) | — | — |
| reservation-pause (reservation, pause) | metrics | 4 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 1/20 (2.1 s) | 1/4 · 9.86 · **13.71** | 2/20 (14.8 s) | — | — |
| reservation-pause (reservation, pause) | full | 4 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 2/4 · 12.36 [9.86–14.86] · **13.68** | 0/20 | 4/4 · 1.16 [1.13–1.17] · **1.16** | 0/20 |
| search-pause (search, pause) | none | 4 | 0/4 · **15.00** | 0/20 | — | — | — | — | 0/4 · **15.00** | 5/20 (14.8 s) | — | — |
| search-pause (search, pause) | logs | 4 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | — | — | 2/4 · 4.86 [4.86–4.86] · **9.93** | 3/20 (9.9 s) | — | — |
| search-pause (search, pause) | metrics | 4 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 1/20 (2.1 s) | 1/4 · 14.86 · **14.96** | 2/20 (14.8 s) | — | — |
| search-pause (search, pause) | full | 4 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 3/4 · 4.86 [4.85–4.87] · **7.39** | 1/20 (9.8 s) | 4/4 · 1.16 [1.16–1.17] · **1.16** | 0/20 |

Own sensors of the target (G2, reported apart): cpu-throttle none S:own 4/4 · 4.81 [4.79–9.78] · **6.05**; cpu-throttle logs S:own 3/4 · 4.81 [4.80–4.82] · **7.37**; cpu-throttle metrics S:own 4/4 · 4.80 [4.79–4.82] · **4.80**; cpu-throttle full S:own 4/4 · 4.81 [4.81–4.82] · **4.81**; net-delay logs S:own 1/4 · 14.86 · **15.01**; net-delay metrics M:own 1/4 · 7.57 · **13.19**; net-delay full T:own 4/4 · 0.15 [0.15–0.16] · **0.16**.

**hotel-sel1**

| class (target, kind) | posture | n | E | FA E | L | FA L | M | FA M | S | FA S | Tsel | FA Tsel | T | FA T |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cpu-throttle (profile, degradation) | none | 4 | 0/4 · **15.05** | 0/20 | — | — | — | — | 3/4 · 14.81 [14.79–14.81] · **14.87** | 7/20 (14.7 s) | — | — | — | — |
| cpu-throttle (profile, degradation) | metrics | 4 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 1/20 (7.6 s) | 1/4 · 14.79 · **14.99** | 3/20 (14.8 s) | — | — | — | — |
| cpu-throttle (profile, degradation) | selected | 4 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 2/4 · 14.81 [14.81–14.81] · **14.93** | 2/20 (14.8 s) | 0/4 · **15.05** | 0/20 | — | — |
| cpu-throttle (profile, degradation) | full | 4 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 1/20 (14.8 s) | — | — | 0/4 · **15.05** | 0/20 |
| net-delay (rate, degradation) | none | 4 | 4/4 · 0.56 [0.55–0.57] · **0.56** | 0/20 | — | — | — | — | 3/4 · 14.84 [9.85–14.85] · **13.65** | 7/20 (14.7 s) | — | — | — | — |
| net-delay (rate, degradation) | metrics | 4 | 4/4 · 0.56 [0.47–0.57] · **0.54** | 0/20 | 0/4 · **15.06** | 0/20 | 2/4 · 7.62 [7.61–7.62] · **11.34** | 1/20 (7.6 s) | 2/4 · 14.85 [14.84–14.86] · **14.96** | 4/20 (12.3 s) | — | — | — | — |
| net-delay (rate, degradation) | selected | 4 | 4/4 · 0.57 [0.47–0.57] · **0.54** | 0/20 | 0/4 · **15.07** | 0/20 | 2/4 · 7.62 [7.62–7.63] · **11.34** | 0/20 | 2/4 · 9.85 [4.85–14.86] · **12.46** | 3/20 (14.8 s) | 4/4 · 0.41 [0.36–0.46] · **0.41** | 0/20 | — | — |
| net-delay (rate, degradation) | full | 4 | 4/4 · 0.51 [0.43–0.56] · **0.51** | 0/20 | 0/4 · **15.07** | 0/20 | 1/4 · 7.63 · **13.21** | 0/20 | 0/4 · **15.07** | 1/20 (14.8 s) | — | — | 4/4 · 0.40 [0.37–0.46] · **0.40** | 0/20 |
| reservation-pause (reservation, pause) | none | 4 | 0/4 · **15.00** | 0/20 | — | — | — | — | 2/4 · 14.84 [14.83–14.86] · **14.92** | 3/20 (9.8 s) | — | — | — | — |
| reservation-pause (reservation, pause) | metrics | 4 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 2/4 · 12.36 [9.86–14.85] · **13.68** | 2/20 (9.8 s) | — | — | — | — |
| reservation-pause (reservation, pause) | selected | 4 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 1/4 · 9.87 · **13.72** | 2/20 (14.8 s) | 4/4 · 1.17 [1.15–1.18] · **1.17** | 0/20 | — | — |
| reservation-pause (reservation, pause) | full | 4 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 3/4 · 14.87 [9.86–14.87] · **13.65** | 1/20 (14.8 s) | — | — | 4/4 · 1.17 [1.17–1.17] · **1.17** | 0/20 |
| search-pause (search, pause) | none | 4 | 0/4 · **15.00** | 0/20 | — | — | — | — | 0/4 · **15.00** | 9/20 (14.8 s) | — | — | — | — |
| search-pause (search, pause) | metrics | 4 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 1/4 · 4.86 · **12.47** | 3/20 (4.9 s) | — | — | — | — |
| search-pause (search, pause) | selected | 4 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 3/4 · 4.87 [4.87–14.86] · **9.90** | 3/20 (4.9 s) | 4/4 · 1.17 [1.16–1.17] · **1.17** | 0/20 | — | — |
| search-pause (search, pause) | full | 4 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 2/4 · 9.85 [9.85–9.85] · **12.43** | 1/20 (14.9 s) | — | — | 4/4 · 1.16 [1.15–1.17] · **1.16** | 0/20 |

Own sensors of the target (G2, reported apart): cpu-throttle none S:own 3/4 · 4.81 [4.79–4.81] · **7.36**; cpu-throttle metrics S:own 4/4 · 4.81 [4.79–9.80] · **6.05**; cpu-throttle selected S:own 4/4 · 4.81 [4.79–9.81] · **6.05**; cpu-throttle full S:own 4/4 · 4.81 [4.81–4.81] · **4.81**; net-delay metrics M:own 1/4 · 7.61 · **13.20**; net-delay selected S:own 1/4 · 14.86 · **15.01**; net-delay full M:own 1/4 · 7.63 · **13.21**; net-delay full T:own 4/4 · 0.16 [0.15–0.17] · **0.16**.

**hotel-int1**

| class (target, kind) | posture | n | E | FA E | L | FA L | M | FA M | S | FA S | Tsel | FA Tsel | T | FA T |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cpu-throttle (profile, degradation) | none | 4 | 0/4 · **15.06** | 0/20 | — | — | — | — | 3/4 · 14.81 [14.79–14.82] · **14.87** | 1/20 (14.8 s) | — | — | — | — |
| cpu-throttle (profile, degradation) | metrics | 4 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 4/20 (14.7 s) | — | — | — | — |
| cpu-throttle (profile, degradation) | selected | 4 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 3/4 · 9.81 [4.82–14.81] · **11.12** | 0/20 | 0/4 · **15.06** | 0/20 | — | — |
| cpu-throttle (profile, degradation) | full | 4 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 0/20 | 0/4 · **15.05** | 1/20 (14.7 s) | — | — | 0/4 · **15.05** | 1/20 (0.3 s) |
| geo-delay (geo, degradation) | none | 4 | 4/4 · 0.36 [0.26–3.36] · **1.08** | 0/20 | — | — | — | — | 1/4 · 9.84 · **13.76** | 2/20 (9.8 s) | — | — | — | — |
| geo-delay (geo, degradation) | metrics | 4 | 4/4 · 0.95 [0.26–3.27] · **1.36** | 0/20 | 0/4 · **15.07** | 0/20 | 0/4 · **15.07** | 0/20 | 2/4 · 7.35 [4.83–9.86] · **11.21** | 3/20 (14.7 s) | — | — | — | — |
| geo-delay (geo, degradation) | selected | 4 | 2/4 · 0.40 [0.26–0.54] · **7.73** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 4/4 · 0.31 [0.14–0.47] · **0.30** | 0/20 | — | — |
| geo-delay (geo, degradation) | full | 4 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 1/20 (7.6 s) | 0/4 · **15.06** | 2/20 (14.8 s) | — | — | 4/4 · 0.06 [0.06–0.06] · **0.06** | 2/20 (1.0 s) |
| rate-delay (rate, degradation) | none | 4 | 4/4 · 0.37 [0.27–0.95] · **0.49** | 0/20 | — | — | — | — | 1/4 · 9.85 · **13.76** | 2/20 (9.8 s) | — | — | — | — |
| rate-delay (rate, degradation) | metrics | 4 | 4/4 · 0.51 [0.35–3.27] · **1.16** | 0/20 | 0/4 · **15.08** | 0/20 | 1/4 · 10.67 · **13.98** | 0/20 | 2/4 · 12.34 [9.84–14.85] · **13.70** | 4/20 (14.7 s) | — | — | — | — |
| rate-delay (rate, degradation) | selected | 4 | 2/4 · 6.67 [1.67–11.66] · **10.86** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 0/4 · **15.06** | 0/20 | 4/4 · 0.26 [0.16–0.36] · **0.26** | 0/20 | — | — |
| rate-delay (rate, degradation) | full | 4 | 1/4 · 13.76 · **14.74** | 0/20 | 0/4 · **15.06** | 0/20 | 1/4 · 7.61 · **13.20** | 1/20 (7.6 s) | 0/4 · **15.06** | 2/20 (14.8 s) | — | — | 4/4 · 0.20 [0.15–0.26] · **0.20** | 2/20 (1.0 s) |
| search-pause (search, pause) | none | 4 | 0/4 · **15.00** | 0/20 | — | — | — | — | 2/4 · 9.85 [4.87–14.84] · **12.43** | 1/20 (14.8 s) | — | — | — | — |
| search-pause (search, pause) | metrics | 4 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 4/20 (14.7 s) | — | — | — | — |
| search-pause (search, pause) | selected | 4 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 3/4 · 4.87 [4.86–14.86] · **9.90** | 0/20 | 4/4 · 1.17 [1.17–1.17] · **1.17** | 0/20 | — | — |
| search-pause (search, pause) | full | 4 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 0/4 · **15.00** | 0/20 | 4/4 · 7.36 [4.86–14.84] · **8.61** | 3/20 (14.7 s) | — | — | 4/4 · 1.17 [1.14–1.17] · **1.16** | 0/20 |

Own sensors of the target (G2, reported apart): cpu-throttle none S:own 3/4 · 4.79 [4.67–4.81] · **7.33**; cpu-throttle metrics S:own 2/4 · 4.82 [4.82–4.82] · **9.94**; cpu-throttle selected S:own 3/4 · 4.81 [4.81–4.82] · **7.37**; cpu-throttle full S:own 3/4 · 4.81 [4.81–4.81] · **7.37**; cpu-throttle full T:own 1/4 · 2.72 · **11.97**; geo-delay metrics S:own 1/4 · 14.84 · **15.01**; geo-delay selected S:own 1/4 · 4.83 · **12.50**; rate-delay full T:own 4/4 · 0.20 [0.14–0.45] · **0.25**.

**teastore-T16**

| class (target, kind) | posture | n | E | FA E | L | FA L | Tsel | FA Tsel | T | FA T |
|---|---|---|---|---|---|---|---|---|---|---|
| auth-freeze (auth, pause) | none | 3 | 0/3 · **150.42** | 0/6 | 0/3 · **150.42** | ? (no records) | — | — | — | — |
| auth-freeze (auth, pause) | selected | 3 | 0/3 · **150.40** | 0/6 | 0/3 · **150.40** | ? (no records) | 0/3 · **150.40** | 2/6 (78.8 s) | — | — |
| auth-freeze (auth, pause) | full | 3 | 0/3 · **150.44** | 0/6 | 0/3 · **150.44** | ? (no records) | — | — | 3/3 · 25.76 [19.70–26.18] · **23.88** | 5/6 (33.4 s) |
| persistence-crash (persistence, stop) | none | 3 | 0/3 · **161.02** | 0/6 | 0/3 · **161.02** | ? (no records) | — | — | — | — |
| persistence-crash (persistence, stop) | selected | 3 | 0/3 · **161.08** | 0/6 | 0/3 · **161.08** | ? (no records) | 1/3 · 126.73 · **149.61** | 0/6 | — | — |
| persistence-crash (persistence, stop) | full | 3 | 0/3 · **161.05** | 0/6 | 0/3 · **161.05** | ? (no records) | — | — | 3/3 · 13.42 [13.41–13.43] · **13.42** | 1/6 (24.5 s) |

**otel-v3**

| class (target, kind) | posture | n | E:own | FA E:own | E | FA E |
|---|---|---|---|---|---|---|
| frontend-pause (frontend, pause) | none | 3 | 0/3 · **155.54** | 0/6 | 0/3 · **155.54** | 0/6 |
| frontend-pause (frontend, pause) | selected | 3 | 0/3 · **155.51** | 0/6 | 0/3 · **155.51** | 0/6 |
| frontend-pause (frontend, pause) | async | 3 | 0/3 · **155.51** | 0/6 | 0/3 · **155.51** | 0/6 |
| frontend-pause (frontend, pause) | full | 3 | 0/3 · **155.54** | 0/6 | 0/3 · **155.54** | 0/6 |

Admissible single-sample spikes excluded because their service is off the affected call path (round 4): hotel-lmt2 M 27, S 22; hotel-sel1 M 42, S 29, T 1; hotel-int1 M 21, S 11, T 3; teastore-T16 0; otel-v3 0 (fires, summed over episodes).

## 3. The ledger's rules one by one

Ledger sensor = one per route at the entry. Per rule: detected k/n by the rule on an admissible route · time to detection; then `adm a/b routes` and the G3 k/n_eff of the inadmissible routes (τ = 0.05); `any route: k` = the rule on any route, admissible or not. `watchdog` is not part of E.

**hotel-lmt2**

| class | posture | n | failed | spike | run3 | median | watchdog |
|---|---|---|---|---|---|---|---|
| cpu-throttle | none | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 17/20 · any route: 4 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 17/20 · any route: 4 |
| cpu-throttle | logs | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 · any route: 3 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 · any route: 3 |
| cpu-throttle | metrics | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 · any route: 4 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 · any route: 4 |
| cpu-throttle | full | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 9/20 · any route: 2 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 9/20 · any route: 2 |
| net-delay | none | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 17/20 · any route: 4 | 4/4 · 0.52 [0.46–0.56] · adm 1/1 routes | 4/4 · 0.52 [0.46–0.56] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 17/20 · any route: 4 |
| net-delay | logs | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 · any route: 4 | 4/4 · 0.56 [0.56–0.57] · adm 1/1 routes | 4/4 · 0.56 [0.56–0.57] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 · any route: 4 |
| net-delay | metrics | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 · any route: 4 | 4/4 · 0.56 [0.50–0.57] · adm 1/1 routes | 4/4 · 0.56 [0.50–0.57] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 · any route: 4 |
| net-delay | full | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 9/20 · any route: 4 | 4/4 · 0.56 [0.47–0.57] · adm 1/1 routes | 4/4 · 0.56 [0.47–0.57] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 9/20 · any route: 4 |
| reservation-pause | none | 4 | 4/4 · 1.17 [1.16–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 17/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 17/20 · any route: 4 |
| reservation-pause | logs | 4 | 4/4 · 1.16 [1.16–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 · any route: 4 |
| reservation-pause | metrics | 4 | 4/4 · 1.16 [1.16–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 · any route: 4 |
| reservation-pause | full | 4 | 4/4 · 1.16 [1.13–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 9/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 9/20 · any route: 4 |
| search-pause | none | 4 | 4/4 · 1.16 [1.13–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 17/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 17/20 · any route: 4 |
| search-pause | logs | 4 | 4/4 · 1.17 [1.15–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 · any route: 4 |
| search-pause | metrics | 4 | 4/4 · 1.17 [1.16–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 · any route: 4 |
| search-pause | full | 4 | 4/4 · 1.16 [1.16–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 9/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 9/20 · any route: 4 |

**hotel-sel1**

| class | posture | n | failed | spike | run3 | median | watchdog |
|---|---|---|---|---|---|---|---|
| cpu-throttle | none | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 19/20 · any route: 4 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 19/20 · any route: 4 |
| cpu-throttle | metrics | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 15/20 · any route: 3 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 15/20 · any route: 3 |
| cpu-throttle | selected | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 10/20 · any route: 4 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 10/20 · any route: 4 |
| cpu-throttle | full | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 8/20 · any route: 2 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 8/20 · any route: 3 |
| net-delay | none | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 19/20 · any route: 4 | 4/4 · 0.56 [0.55–0.57] · adm 1/1 routes | 4/4 · 0.56 [0.55–0.57] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 19/20 · any route: 4 |
| net-delay | metrics | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 15/20 · any route: 4 | 4/4 · 0.56 [0.47–0.57] · adm 1/1 routes | 4/4 · 0.56 [0.47–0.57] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 15/20 · any route: 4 |
| net-delay | selected | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 10/20 · any route: 4 | 4/4 · 0.57 [0.47–0.57] · adm 1/1 routes | 4/4 · 0.57 [0.47–0.57] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 10/20 · any route: 4 |
| net-delay | full | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 8/20 · any route: 4 | 4/4 · 0.54 [0.47–0.56] · adm 1/1 routes | 4/4 · 0.51 [0.43–0.56] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 8/20 · any route: 4 |
| reservation-pause | none | 4 | 4/4 · 1.16 [1.13–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 19/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 19/20 · any route: 4 |
| reservation-pause | metrics | 4 | 4/4 · 1.16 [1.16–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 15/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 15/20 · any route: 4 |
| reservation-pause | selected | 4 | 4/4 · 1.17 [1.15–1.18] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 10/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 10/20 · any route: 4 |
| reservation-pause | full | 4 | 4/4 · 1.17 [1.17–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 8/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 8/20 · any route: 4 |
| search-pause | none | 4 | 4/4 · 1.17 [1.16–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 19/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 19/20 · any route: 4 |
| search-pause | metrics | 4 | 4/4 · 1.16 [1.16–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 15/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 15/20 · any route: 4 |
| search-pause | selected | 4 | 4/4 · 1.17 [1.16–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 10/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 10/20 · any route: 4 |
| search-pause | full | 4 | 4/4 · 1.16 [1.15–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 8/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 8/20 · any route: 4 |

**hotel-int1**

| class | posture | n | failed | spike | run3 | median | watchdog |
|---|---|---|---|---|---|---|---|
| cpu-throttle | none | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 · any route: 4 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 · any route: 4 |
| cpu-throttle | metrics | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 · any route: 3 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 · any route: 3 |
| cpu-throttle | selected | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 11/20 · any route: 1 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 11/20 · any route: 1 |
| cpu-throttle | full | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 7/20 · any route: 3 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 7/20 · any route: 3 |
| geo-delay | none | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 · any route: 4 | 4/4 · 0.41 [0.36–3.36] · adm 1/1 routes | 3/4 · 0.26 [0.26–0.46] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 · any route: 4 |
| geo-delay | metrics | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 · any route: 4 | 4/4 · 1.41 [0.54–3.27] · adm 1/1 routes | 3/4 · 1.36 [0.26–3.14] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 · any route: 4 |
| geo-delay | selected | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 11/20 · any route: 4 | 1/4 · 12.16 · adm 1/1 routes | 2/4 · 0.40 [0.26–0.54] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 11/20 · any route: 4 |
| geo-delay | full | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 7/20 · any route: 4 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 7/20 · any route: 4 |
| rate-delay | none | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 · any route: 4 | 4/4 · 0.42 [0.37–0.95] · adm 1/1 routes | 4/4 · 0.37 [0.27–1.05] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 · any route: 4 |
| rate-delay | metrics | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 · any route: 4 | 4/4 · 0.56 [0.55–3.27] · adm 1/1 routes | 3/4 · 0.46 [0.35–0.65] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 · any route: 4 |
| rate-delay | selected | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 11/20 · any route: 4 | 2/4 · 6.67 [1.67–11.66] · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 11/20 · any route: 4 |
| rate-delay | full | 4 | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 7/20 · any route: 4 | 1/4 · 13.76 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 7/20 · any route: 4 |
| search-pause | none | 4 | 4/4 · 1.17 [1.14–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 20/20 · any route: 4 |
| search-pause | metrics | 4 | 4/4 · 1.17 [1.16–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 18/20 · any route: 4 |
| search-pause | selected | 4 | 4/4 · 1.17 [1.17–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 11/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 11/20 · any route: 4 |
| search-pause | full | 4 | 4/4 · 1.17 [1.14–1.17] · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 7/20 | 0/4 · adm 1/1 routes | 0/4 · adm 1/1 routes | 0/4 · adm 0/1 routes; G3 hotel-search-v1 7/20 · any route: 4 |

**teastore-T16**

| class | posture | n | failed | spike | run3 | median | watchdog |
|---|---|---|---|---|---|---|---|
| auth-freeze | none | 3 | 3/3 · 15.26 [15.17–15.29] · adm 4/4 routes | 0/3 · adm 1/4 routes; G3 category 2/6, home 1/6, product 6/6 | 0/3 · adm 4/4 routes | 0/3 · adm 4/4 routes | 3/3 · 6.77 [6.75–6.78] · adm 1/4 routes; G3 category 2/6, home 1/6, product 6/6 |
| auth-freeze | selected | 3 | 3/3 · 15.25 [15.22–15.30] · adm 4/4 routes | 0/3 · adm 2/4 routes; G3 category 3/6, product 6/6 | 0/3 · adm 4/4 routes | 0/3 · adm 4/4 routes | 3/3 · 6.77 [6.76–6.78] · adm 2/4 routes; G3 category 3/6, product 6/6 |
| auth-freeze | full | 3 | 3/3 · 15.28 [15.21–15.29] · adm 4/4 routes | 0/3 · adm 2/4 routes; G3 category 3/6, product 5/6 | 0/3 · adm 4/4 routes | 0/3 · adm 4/4 routes | 3/3 · 6.79 [6.77–6.80] · adm 2/4 routes; G3 category 3/6, product 5/6 |
| persistence-crash | none | 3 | 3/3 · 17.04 [16.30–17.04] · adm 4/4 routes | 3/3 · 26.89 [26.88–26.96] · adm 1/4 routes; G3 category 2/6, home 1/6, product 6/6 | 2/3 · 73.45 [40.12–106.78] · adm 4/4 routes | 0/3 · adm 4/4 routes | 3/3 · 13.44 [13.43–13.44] · adm 1/4 routes; G3 category 2/6, home 1/6, product 6/6 |
| persistence-crash | selected | 3 | 3/3 · 17.46 [16.70–17.64] · adm 4/4 routes | 3/3 · 20.85 [20.78–27.42] · adm 2/4 routes; G3 category 3/6, product 6/6 | 3/3 · 86.77 [46.78–153.47] · adm 4/4 routes | 0/3 · adm 4/4 routes | 3/3 · 13.45 [13.45–13.46] · adm 2/4 routes; G3 category 3/6, product 6/6 |
| persistence-crash | full | 3 | 3/3 · 17.91 [17.55–18.00] · adm 4/4 routes | 3/3 · 27.92 [27.81–28.10] · adm 2/4 routes; G3 category 3/6, product 5/6 | 2/3 · 70.12 [53.45–86.79] · adm 4/4 routes | 0/3 · adm 4/4 routes | 3/3 · 13.44 [13.43–13.44] · adm 2/4 routes; G3 category 3/6, product 5/6 |

**otel-v3**

| class | posture | n | failed | spike | run3 | median | watchdog |
|---|---|---|---|---|---|---|---|
| frontend-pause | none | 3 | 3/3 · 15.69 [15.67–15.71] · adm 1/1 routes | 0/3 · adm 0/1 routes; G3 recommendations 2/6 | 0/3 · adm 1/1 routes | 0/3 · adm 1/1 routes | 0/3 · adm 0/1 routes; G3 recommendations 2/6 · any route: 3 |
| frontend-pause | selected | 3 | 3/3 · 15.70 [6.70–15.73] · adm 1/1 routes | 0/3 · adm 0/1 routes; G3 recommendations 3/6 | 0/3 · adm 1/1 routes | 0/3 · adm 1/1 routes | 0/3 · adm 0/1 routes; G3 recommendations 3/6 · any route: 3 |
| frontend-pause | async | 3 | 3/3 · 15.72 [15.72–15.74] · adm 1/1 routes | 0/3 · adm 0/1 routes; G3 recommendations 3/6 | 0/3 · adm 1/1 routes | 0/3 · adm 1/1 routes | 0/3 · adm 0/1 routes; G3 recommendations 3/6 · any route: 3 |
| frontend-pause | full | 3 | 3/3 · 15.68 [15.67–15.70] · adm 1/1 routes | 0/3 · adm 0/1 routes; G3 recommendations 2/6 | 0/3 · adm 1/1 routes | 0/3 · adm 1/1 routes | 0/3 · adm 0/1 routes; G3 recommendations 2/6 · any route: 3 |

## 4. Impact before detection

Ledger requests started between the command bound and the family's first catch that failed or crossed their route's per-request threshold: median [min–max] over the detected episodes (all postures that collect the family pooled), with detected/collected episodes. `hold` = the same count over the whole hold, for scale.

**hotel-lmt2**

| class | hold: bad / started | E | E:noBC | E:own | L | L:noBC | L:own | M | M:noBC | M:own | S | S:noBC | S:own | T | T:noBC | T:own |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cpu-throttle | 2 [0–6] / 151 [150–151] | 0/16 | 0/16 | 0/16 | 0/12 | 0/12 | 0/12 | 1 (1/8) | 1 (1/8) | 0/8 | 1 [0–2] (3/16) | 1 [0–2] (3/16) | 0 [0–2] (15/16) | 0/4 | 0/4 | 0/4 |
| net-delay | 151 [150–151] / 151 [150–151] | 6 [5–6] (16/16) | 6 [5–6] (16/16) | 0/16 | 0/12 | 0/12 | 0/12 | 75 (1/8) | 75 (1/8) | 75 (1/8) | 148 [48–149] (4/16) | 148 [48–149] (4/16) | 149 (1/16) | 4 [4–5] (4/4) | 4 [4–5] (4/4) | 2 [2–2] (4/4) |
| reservation-pause | 149 [149–149] / 150 [150–150] | 11 [11–11] (16/16) | 0/16 | 0/16 | 15 [11–20] (12/12) | 0/12 | 0/12 | 75 [14–75] (8/8) | 0/8 | 14 [14–14] (8/8) | 147 [97–148] (5/16) | 147 [97–148] (5/16) | 0/16 | 11 [11–11] (4/4) | 11 [11–11] (4/4) | 0/4 |
| search-pause | 149 [149–149] / 150 [150–150] | 11 [11–11] (16/16) | 0/16 | 0/16 | 0/12 | 0/12 | 0/12 | 14 [14–14] (8/8) | 0/8 | 14 [14–44] (8/8) | 47 [47–147] (6/16) | 47 [47–147] (6/16) | 0/16 | 11 [11–11] (4/4) | 11 [11–11] (4/4) | 0/4 |

**hotel-sel1**

| class | hold: bad / started | E | E:noBC | E:own | L | L:noBC | L:own | M | M:noBC | M:own | S | S:noBC | S:own | T | T:noBC | T:own | Tsel | Tsel:noBC | Tsel:own |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cpu-throttle | 2 [0–6] / 151 [150–151] | 0/16 | 0/16 | 0/16 | 0/12 | 0/12 | 0/12 | 0/12 | 0/12 | 0/12 | 3 [0–6] (6/16) | 3 [0–6] (6/16) | 1 [0–5] (15/16) | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 |
| net-delay | 151 [150–151] / 151 [151–151] | 6 [4–6] (16/16) | 6 [4–6] (16/16) | 0/16 | 0/12 | 0/12 | 0/12 | 76 [76–76] (5/12) | 76 [76–76] (5/12) | 76 [76–76] (2/12) | 148 [48–148] (7/16) | 148 [48–148] (7/16) | 148 (1/16) | 4 [4–5] (4/4) | 4 [4–5] (4/4) | 2 [1–2] (4/4) | 4.50 [4–5] (4/4) | 4.50 [4–5] (4/4) | 0/4 |
| reservation-pause | 149 [149–149] / 150 [150–150] | 11 [11–11] (16/16) | 0/16 | 0/16 | 16 [12–20] (12/12) | 0/12 | 0/12 | 14 [14–75] (12/12) | 0/12 | 14 [14–44] (12/12) | 147 [97–148] (8/16) | 147 [97–148] (8/16) | 0/16 | 11 [11–11] (4/4) | 11 [11–11] (4/4) | 0/4 | 11 [11–11] (4/4) | 11 [11–11] (4/4) | 0/4 |
| search-pause | 149 [149–149] / 150 [150–150] | 11 [11–11] (16/16) | 0/16 | 0/16 | 0/12 | 0/12 | 0/12 | 14 [14–14] (12/12) | 0/12 | 14 [14–45] (12/12) | 72.50 [47–147] (6/16) | 72.50 [47–147] (6/16) | 0/16 | 11 [11–11] (4/4) | 11 [11–11] (4/4) | 0/4 | 11 [11–11] (4/4) | 11 [11–11] (4/4) | 0/4 |

**hotel-int1**

| class | hold: bad / started | E | E:noBC | E:own | L | L:noBC | L:own | M | M:noBC | M:own | S | S:noBC | S:own | T | T:noBC | T:own | Tsel | Tsel:noBC | Tsel:own |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cpu-throttle | 1.50 [0–4] / 151 [150–151] | 0/16 | 0/16 | 0/16 | 0/12 | 0/12 | 0/12 | 0/12 | 0/12 | 0/12 | 0.50 [0–3] (6/16) | 0.50 [0–3] (6/16) | 1 [0–3] (11/16) | 0/4 | 0/4 | 0 (1/4) | 0/4 | 0/4 | 0/4 |
| geo-delay | 38 [8–137] / 151 [150–151] | 3 [2–13] (10/16) | 3 [2–13] (10/16) | 0/16 | 0/12 | 0/12 | 0/12 | 0/12 | 0/12 | 0/12 | 24 [23–87] (3/16) | 24 [23–87] (3/16) | 36.50 [7–66] (2/16) | 0 [0–0] (4/4) | 0 [0–0] (4/4) | 0/4 | 1.50 [0–2] (4/4) | 1.50 [0–2] (4/4) | 0/4 |
| rate-delay | 53.50 [8–139] / 151 [151–151] | 3 [2–23] (11/16) | 3 [2–23] (11/16) | 0/16 | 0/12 | 0/12 | 0/12 | 30 [9–51] (2/12) | 30 [9–51] (2/12) | 0/12 | 59 [49–74] (3/16) | 59 [49–74] (3/16) | 0/16 | 0 [0–1] (4/4) | 0 [0–1] (4/4) | 0.50 [0–1] (4/4) | 0 [0–1] (4/4) | 0 [0–1] (4/4) | 0/4 |
| search-pause | 149 [149–149] / 150 [150–150] | 11 [11–11] (16/16) | 0/16 | 0/16 | 0/12 | 0/12 | 0/12 | 14 [14–75] (12/12) | 0/12 | 14 [14–44] (12/12) | 48 [47–147] (9/16) | 48 [47–147] (9/16) | 0/16 | 11 [11–11] (4/4) | 11 [11–11] (4/4) | 0/4 | 11 [11–11] (4/4) | 11 [11–11] (4/4) | 0/4 |

**teastore-T16**

| class | hold: bad / started | E | E:noBC | E:own | L | L:noBC | L:own | T | T:noBC | T:own | Tsel | Tsel:noBC | Tsel:own |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| auth-freeze | 70 [69–71] / 75 [75–75] | 3 [3–3] (9/9) | 0/9 | 0/9 | 0/9 | 0/9 | 0/9 | 2 [2–2] (3/3) | 6 [4–6] (3/3) | 2 [2–2] (3/3) | 2 [2–2] (3/3) | 0/3 | 2 [2–2] (3/3) |
| persistence-crash | 26 [10–29] / 99 [99–99] | 2 [1–2] (9/9) | 0/9 | 0/9 | 2 [1–2] (9/9) | 0/9 | 0/9 | 1 [1–2] (3/3) | 1 [1–2] (3/3) | 3 [3–4] (3/3) | 4 [4–4] (3/3) | 20 (1/3) | 4 [4–4] (3/3) |

**otel-v3**

| class | hold: bad / started | E | E:noBC | E:own |
|---|---|---|---|---|
| frontend-pause | 85 [85–155] / 85 [85–155] | 0/12 | 0/12 | 8 [7–8] (12/12) |

## 5. Traffic dependence: the ledger thinned

**Thinning the ledger does not reproduce what the SUT would do at lower load.** The SUT's state, its queueing, and every sensor's noise change with load, and sensors whose signal is load-driven (e.g. BC-idle-cpu: callers idle because requests stopped) would weaken. The numbers below bound the **ledger side only**: what the same fault, seen through fewer requests, would leave the ledger to see. The sensors' times are the ones measured at the campaign's load.

Per class: share of (episode × seed) trials with no ledger catch inside the hold (miss), with no catch and a route without a latency baseline (`?`), median time to detection over the detected trials, and the no-fault false-alarm share of the thinned ledger. Bernoulli thinning (Poisson-like arrivals); periodic thinning in the JSON. Analytic Poisson prediction from the full-rate bad-request share q and observation lag l in the last column.

**hotel-lmt2** (base 10 request/s, 10 requests/s; 200 seeds)

| class | model: m · q · delay · lag · hold (s) | p | requests/s | miss | ? | miss periodic | median TTD all trials · detected (s) | mean TTD, miss = hold (s) | FA no-fault | failed rule only: miss · mean · FA | analytic miss · median |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cpu-throttle | 3 · 0.01 · 2.01 · 0.01 · 15.1 | 1 | 10 | 1.00 | 0.00 | 1.00 | > hold · — | 15.05 | 0/80 | 1.00 · 15.05 · 0/80 | n/a |
| cpu-throttle | 3 · 0.01 · 2.01 · 0.01 · 15.1 | 0.2 | 2 | 1.00 | 0.00 | 1.00 | > hold · 1.93 [0.33–2.23] | 15.03 | 35/16000 | 1.00 · 15.05 · 0/16000 | n/a |
| cpu-throttle | 3 · 0.01 · 2.01 · 0.01 · 15.1 | 0.1 | 1 | 1.00 | 0.00 | 1.00 | > hold · 2.43 [0.82–11.63] | 15.00 | 72/16000 | 1.00 · 15.05 · 0/16000 | n/a |
| cpu-throttle | 3 · 0.01 · 2.01 · 0.01 · 15.1 | 0.02 | 0.2 | 0.96 | 0.00 | 0.96 | > hold · 6.13 [0.33–14.92] | 14.79 | 299/16000 | 1.00 · 15.05 · 0/16000 | n/a |
| cpu-throttle | 3 · 0.01 · 2.01 · 0.01 · 15.1 | 0.01 | 0.1 | 0.85 | 0.13 | 1.00 | > hold · 5.83 [0.32–14.93] | 14.91 | 253/16000 | 1.00 · 15.05 · 0/16000 | n/a |
| cpu-throttle | 3 · 0.01 · 2.01 · 0.01 · 15.1 | 0.001 | 0.01 | 0.86 | 0.14 | 0.85 | > hold · — | 15.05 | 7/16000 | 1.00 · 15.05 · 0/16000 | n/a |
| net-delay | 3 · 1.00 · 0.05 · 0.21 · 15.1 | 1 | 10 | 0.00 | 0.00 | 0.00 | 0.56 · 0.56 [0.46–0.57] | 0.54 | 0/80 | 1.00 · 15.06 · 0/80 | 0.00 · 0.53 |
| net-delay | 3 · 1.00 · 0.05 · 0.21 · 15.1 | 0.2 | 2 | 0.00 | 0.00 | 0.00 | 1.50 · 1.50 [0.47–6.26] | 1.66 | 35/16000 | 1.00 · 15.06 · 0/16000 | 0.00 · 1.60 |
| net-delay | 3 · 1.00 · 0.05 · 0.21 · 15.1 | 0.1 | 1 | 0.00 | 0.00 | 0.00 | 2.76 · 2.76 [0.50–11.57] | 3.10 | 72/16000 | 1.00 · 15.06 · 0/16000 | 0.00 · 2.94 |
| net-delay | 3 · 1.00 · 0.05 · 0.21 · 15.1 | 0.02 | 0.2 | 0.33 | 0.00 | 0.03 | 11.27 · 7.66 [0.26–15.06] | 10.14 | 299/16000 | 1.00 · 15.06 · 0/16000 | 0.43 · 13.63 |
| net-delay | 3 · 1.00 · 0.05 · 0.21 · 15.1 | 0.01 | 0.1 | 0.60 | 0.12 | 1.00 | > hold · 7.97 [0.26–15.06] | 13.07 | 253/16000 | 1.00 · 15.06 · 0/16000 | 0.81 · > hold |
| net-delay | 3 · 1.00 · 0.05 · 0.21 · 15.1 | 0.001 | 0.01 | 0.86 | 0.13 | 0.84 | > hold · 11.36 [0.66–13.16] | 15.05 | 7/16000 | 1.00 · 15.06 · 0/16000 | 1.00 · > hold |
| reservation-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 1 | 10 | 0.00 | 0.00 | 0.00 | 1.16 · 1.16 [1.13–1.17] | 1.16 | 0/80 | 0.00 · 1.16 · 0/80 | 0.00 · 1.24 |
| reservation-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.2 | 2 | 0.00 | 0.00 | 0.00 | 1.46 · 1.46 [1.13–5.36] | 1.56 | 35/16000 | 0.00 · 1.56 · 0/16000 | 0.00 · 1.54 |
| reservation-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.1 | 1 | 0.00 | 0.00 | 0.00 | 1.76 · 1.76 [1.13–7.77] | 2.06 | 72/16000 | 0.00 · 2.06 · 0/16000 | 0.00 · 1.91 |
| reservation-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.02 | 0.2 | 0.05 | 0.00 | 0.00 | 4.47 · 4.17 [1.13–14.97] | 5.68 | 299/16000 | 0.05 · 5.68 · 0/16000 | 0.08 · 4.88 |
| reservation-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.01 | 0.1 | 0.24 | 0.00 | 0.00 | 8.11 · 5.96 [1.13–14.97] | 8.61 | 253/16000 | 0.24 · 8.61 · 0/16000 | 0.27 · 8.59 |
| reservation-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.001 | 0.01 | 0.87 | 0.00 | 0.87 | > hold · 8.16 [1.16–14.97] | 14.10 | 7/16000 | 0.87 · 14.10 · 0/16000 | 0.88 · > hold |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 1 | 10 | 0.00 | 0.00 | 0.00 | 1.16 · 1.16 [1.13–1.17] | 1.16 | 0/80 | 0.00 · 1.16 · 0/80 | 0.00 · 1.24 |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.2 | 2 | 0.00 | 0.00 | 0.00 | 1.43 · 1.43 [1.13–4.97] | 1.56 | 35/16000 | 0.00 · 1.56 · 0/16000 | 0.00 · 1.54 |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.1 | 1 | 0.00 | 0.00 | 0.00 | 1.76 · 1.76 [1.13–7.26] | 2.04 | 72/16000 | 0.00 · 2.04 · 0/16000 | 0.00 · 1.91 |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.02 | 0.2 | 0.06 | 0.00 | 0.00 | 4.34 · 4.06 [1.13–14.97] | 5.66 | 299/16000 | 0.06 · 5.66 · 0/16000 | 0.08 · 4.88 |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.01 | 0.1 | 0.25 | 0.00 | 0.00 | 8.26 · 5.97 [1.13–14.97] | 8.71 | 253/16000 | 0.25 · 8.71 · 0/16000 | 0.27 · 8.59 |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.001 | 0.01 | 0.86 | 0.00 | 0.86 | > hold · 7.27 [1.15–14.97] | 13.97 | 7/16000 | 0.86 · 13.97 · 0/16000 | 0.88 · > hold |

**hotel-sel1** (base 10 request/s, 10 requests/s; 200 seeds)

| class | model: m · q · delay · lag · hold (s) | p | requests/s | miss | ? | miss periodic | median TTD all trials · detected (s) | mean TTD, miss = hold (s) | FA no-fault | failed rule only: miss · mean · FA | analytic miss · median |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cpu-throttle | 3 · 0.01 · 1.81 · 0.01 · 15.1 | 1 | 10 | 1.00 | 0.00 | 1.00 | > hold · — | 15.05 | 0/80 | 1.00 · 15.05 · 0/80 | n/a |
| cpu-throttle | 3 · 0.01 · 1.81 · 0.01 · 15.1 | 0.2 | 2 | 0.99 | 0.00 | 1.00 | > hold · 1.52 [0.84–9.62] | 14.98 | 15/16000 | 1.00 · 15.05 · 0/16000 | n/a |
| cpu-throttle | 3 · 0.01 · 1.81 · 0.01 · 15.1 | 0.1 | 1 | 1.00 | 0.00 | 1.00 | > hold · 3.22 [1.12–8.22] | 15.00 | 32/16000 | 1.00 · 15.05 · 0/16000 | n/a |
| cpu-throttle | 3 · 0.01 · 1.81 · 0.01 · 15.1 | 0.02 | 0.2 | 0.97 | 0.01 | 0.97 | > hold · 7.22 [0.22–14.93] | 14.84 | 255/16000 | 1.00 · 15.05 · 0/16000 | n/a |
| cpu-throttle | 3 · 0.01 · 1.81 · 0.01 · 15.1 | 0.01 | 0.1 | 0.86 | 0.13 | 1.00 | > hold · 11.32 [2.10–14.52] | 15.04 | 49/16000 | 1.00 · 15.05 · 0/16000 | n/a |
| cpu-throttle | 3 · 0.01 · 1.81 · 0.01 · 15.1 | 0.001 | 0.01 | 0.86 | 0.14 | 0.84 | > hold · — | 15.05 | 15/16000 | 1.00 · 15.05 · 0/16000 | n/a |
| net-delay | 3 · 1.00 · 0.05 · 0.21 · 15.1 | 1 | 10 | 0.00 | 0.00 | 0.00 | 0.56 · 0.56 [0.43–0.57] | 0.54 | 0/80 | 1.00 · 15.06 · 0/80 | 0.00 · 0.53 |
| net-delay | 3 · 1.00 · 0.05 · 0.21 · 15.1 | 0.2 | 2 | 0.00 | 0.00 | 0.00 | 1.56 · 1.56 [0.47–6.16] | 1.69 | 15/16000 | 1.00 · 15.06 · 0/16000 | 0.00 · 1.60 |
| net-delay | 3 · 1.00 · 0.05 · 0.21 · 15.1 | 0.1 | 1 | 0.00 | 0.00 | 0.00 | 2.86 · 2.86 [0.47–12.53] | 3.16 | 32/16000 | 1.00 · 15.06 · 0/16000 | 0.00 · 2.94 |
| net-delay | 3 · 1.00 · 0.05 · 0.21 · 15.1 | 0.02 | 0.2 | 0.33 | 0.01 | 0.02 | 11.05 · 7.66 [0.26–15.07] | 10.11 | 255/16000 | 1.00 · 15.06 · 0/16000 | 0.43 · 13.63 |
| net-delay | 3 · 1.00 · 0.05 · 0.21 · 15.1 | 0.01 | 0.1 | 0.71 | 0.13 | 1.00 | > hold · 10.67 [1.06–15.06] | 14.29 | 49/16000 | 1.00 · 15.06 · 0/16000 | 0.81 · > hold |
| net-delay | 3 · 1.00 · 0.05 · 0.21 · 15.1 | 0.001 | 0.01 | 0.85 | 0.15 | 0.86 | > hold · 6.16 [3.97–8.35] | 15.06 | 15/16000 | 1.00 · 15.06 · 0/16000 | 1.00 · > hold |
| reservation-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 1 | 10 | 0.00 | 0.00 | 0.00 | 1.17 · 1.17 [1.13–1.18] | 1.16 | 0/80 | 0.00 · 1.16 · 0/80 | 0.00 · 1.24 |
| reservation-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.2 | 2 | 0.00 | 0.00 | 0.00 | 1.46 · 1.46 [1.13–6.06] | 1.56 | 15/16000 | 0.00 · 1.56 · 0/16000 | 0.00 · 1.54 |
| reservation-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.1 | 1 | 0.00 | 0.00 | 0.00 | 1.76 · 1.76 [1.13–7.75] | 2.05 | 32/16000 | 0.00 · 2.05 · 0/16000 | 0.00 · 1.91 |
| reservation-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.02 | 0.2 | 0.05 | 0.00 | 0.00 | 4.47 · 4.25 [1.13–14.98] | 5.69 | 255/16000 | 0.05 · 5.69 · 0/16000 | 0.08 · 4.88 |
| reservation-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.01 | 0.1 | 0.25 | 0.00 | 0.00 | 7.97 · 5.77 [1.13–14.97] | 8.56 | 49/16000 | 0.25 · 8.56 · 0/16000 | 0.27 · 8.59 |
| reservation-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.001 | 0.01 | 0.87 | 0.00 | 0.85 | > hold · 7.77 [1.17–14.97] | 14.07 | 15/16000 | 0.87 · 14.07 · 0/16000 | 0.88 · > hold |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 1 | 10 | 0.00 | 0.00 | 0.00 | 1.17 · 1.17 [1.15–1.17] | 1.17 | 0/80 | 0.00 · 1.17 · 0/80 | 0.00 · 1.24 |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.2 | 2 | 0.00 | 0.00 | 0.00 | 1.46 · 1.46 [1.15–5.97] | 1.57 | 15/16000 | 0.00 · 1.57 · 0/16000 | 0.00 · 1.54 |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.1 | 1 | 0.00 | 0.00 | 0.00 | 1.77 · 1.77 [1.15–8.76] | 2.06 | 32/16000 | 0.00 · 2.06 · 0/16000 | 0.00 · 1.91 |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.02 | 0.2 | 0.05 | 0.00 | 0.00 | 4.56 · 4.27 [1.15–14.98] | 5.74 | 255/16000 | 0.05 · 5.74 · 0/16000 | 0.08 · 4.88 |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.01 | 0.1 | 0.25 | 0.00 | 0.00 | 8.27 · 5.96 [1.15–14.97] | 8.75 | 49/16000 | 0.25 · 8.75 · 0/16000 | 0.27 · 8.59 |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.001 | 0.01 | 0.86 | 0.00 | 0.87 | > hold · 8.06 [1.15–14.97] | 14.06 | 15/16000 | 0.86 · 14.06 · 0/16000 | 0.88 · > hold |

**hotel-int1** (base 10 request/s, 10 requests/s; 200 seeds)

| class | model: m · q · delay · lag · hold (s) | p | requests/s | miss | ? | miss periodic | median TTD all trials · detected (s) | mean TTD, miss = hold (s) | FA no-fault | failed rule only: miss · mean · FA | analytic miss · median |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cpu-throttle | 3 · 0.01 · 1.40 · 0.01 · 15.1 | 1 | 10 | 1.00 | 0.00 | 1.00 | > hold · — | 15.05 | 0/80 | 1.00 · 15.05 · 0/80 | n/a |
| cpu-throttle | 3 · 0.01 · 1.40 · 0.01 · 15.1 | 0.2 | 2 | 1.00 | 0.00 | 1.00 | > hold · 1.71 [0.53–3.83] | 15.03 | 29/16000 | 1.00 · 15.05 · 0/16000 | n/a |
| cpu-throttle | 3 · 0.01 · 1.40 · 0.01 · 15.1 | 0.1 | 1 | 1.00 | 0.00 | 1.00 | > hold · 1.52 [0.83–5.52] | 15.04 | 53/16000 | 1.00 · 15.05 · 0/16000 | n/a |
| cpu-throttle | 3 · 0.01 · 1.40 · 0.01 · 15.1 | 0.02 | 0.2 | 0.97 | 0.00 | 0.99 | > hold · 5.52 [0.16–14.81] | 14.84 | 268/16000 | 1.00 · 15.05 · 0/16000 | n/a |
| cpu-throttle | 3 · 0.01 · 1.40 · 0.01 · 15.1 | 0.01 | 0.1 | 0.86 | 0.12 | 1.00 | > hold · 8.17 [0.16–15.02] | 14.93 | 239/16000 | 1.00 · 15.05 · 0/16000 | n/a |
| cpu-throttle | 3 · 0.01 · 1.40 · 0.01 · 15.1 | 0.001 | 0.01 | 0.86 | 0.14 | 0.85 | > hold · 6.52 | 15.05 | 5/16000 | 1.00 · 15.05 · 0/16000 | n/a |
| geo-delay | 3 · 0.25 · 0.29 · 0.01 · 15.1 | 1 | 10 | 0.38 | 0.00 | 0.38 | 2.32 · 0.50 [0.26–3.36] | 6.31 | 0/80 | 1.00 · 15.06 · 0/80 | n/a |
| geo-delay | 3 · 0.25 · 0.29 · 0.01 · 15.1 | 0.2 | 2 | 0.49 | 0.00 | 0.45 | 13.31 · 1.74 [0.26–15.06] | 8.79 | 29/16000 | 1.00 · 15.06 · 0/16000 | n/a |
| geo-delay | 3 · 0.25 · 0.29 · 0.01 · 15.1 | 0.1 | 1 | 0.54 | 0.00 | 0.41 | > hold · 3.14 [0.26–15.06] | 9.97 | 53/16000 | 1.00 · 15.06 · 0/16000 | n/a |
| geo-delay | 3 · 0.25 · 0.29 · 0.01 · 15.1 | 0.02 | 0.2 | 0.67 | 0.01 | 0.46 | > hold · 8.41 [0.17–15.06] | 12.85 | 268/16000 | 1.00 · 15.06 · 0/16000 | n/a |
| geo-delay | 3 · 0.25 · 0.29 · 0.01 · 15.1 | 0.01 | 0.1 | 0.74 | 0.13 | 1.00 | > hold · 8.67 [0.17–15.06] | 14.12 | 239/16000 | 1.00 · 15.06 · 0/16000 | n/a |
| geo-delay | 3 · 0.25 · 0.29 · 0.01 · 15.1 | 0.001 | 0.01 | 0.86 | 0.14 | 0.85 | > hold · 1.72 [1.27–2.17] | 15.06 | 5/16000 | 1.00 · 15.06 · 0/16000 | n/a |
| rate-delay | 3 · 0.35 · 0.25 · 0.01 · 15.1 | 1 | 10 | 0.31 | 0.00 | 0.31 | 2.47 · 0.55 [0.27–13.76] | 6.81 | 0/80 | 1.00 · 15.07 · 0/80 | n/a |
| rate-delay | 3 · 0.35 · 0.25 · 0.01 · 15.1 | 0.2 | 2 | 0.43 | 0.00 | 0.46 | 3.76 · 1.57 [0.25–15.06] | 7.91 | 29/16000 | 1.00 · 15.07 · 0/16000 | n/a |
| rate-delay | 3 · 0.35 · 0.25 · 0.01 · 15.1 | 0.1 | 1 | 0.49 | 0.00 | 0.35 | 12.67 · 2.87 [0.36–15.06] | 9.25 | 53/16000 | 1.00 · 15.07 · 0/16000 | n/a |
| rate-delay | 3 · 0.35 · 0.25 · 0.01 · 15.1 | 0.02 | 0.2 | 0.66 | 0.01 | 0.46 | > hold · 8.65 [0.25–15.06] | 12.82 | 268/16000 | 1.00 · 15.07 · 0/16000 | n/a |
| rate-delay | 3 · 0.35 · 0.25 · 0.01 · 15.1 | 0.01 | 0.1 | 0.74 | 0.13 | 1.00 | > hold · 8.51 [0.15–14.95] | 14.15 | 239/16000 | 1.00 · 15.07 · 0/16000 | n/a |
| rate-delay | 3 · 0.35 · 0.25 · 0.01 · 15.1 | 0.001 | 0.01 | 0.87 | 0.13 | 0.84 | > hold · 6.06 [5.56–8.95] | 15.06 | 5/16000 | 1.00 · 15.07 · 0/16000 | n/a |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 1 | 10 | 0.00 | 0.00 | 0.00 | 1.17 · 1.17 [1.14–1.17] | 1.16 | 0/80 | 0.00 · 1.16 · 0/80 | 0.00 · 1.24 |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.2 | 2 | 0.00 | 0.00 | 0.00 | 1.37 · 1.37 [1.14–4.87] | 1.55 | 29/16000 | 0.00 · 1.55 · 0/16000 | 0.00 · 1.54 |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.1 | 1 | 0.00 | 0.00 | 0.00 | 1.77 · 1.77 [1.14–9.67] | 2.08 | 53/16000 | 0.00 · 2.08 · 0/16000 | 0.00 · 1.91 |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.02 | 0.2 | 0.06 | 0.00 | 0.00 | 4.57 · 4.27 [1.14–14.98] | 5.82 | 268/16000 | 0.06 · 5.82 · 0/16000 | 0.08 · 4.88 |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.01 | 0.1 | 0.24 | 0.00 | 0.00 | 8.17 · 5.97 [1.14–14.98] | 8.69 | 239/16000 | 0.24 · 8.69 · 0/16000 | 0.27 · 8.59 |
| search-pause | 1 · 0.93 · 0.16 · 1.00 · 15.0 | 0.001 | 0.01 | 0.87 | 0.00 | 0.85 | > hold · 7.26 [1.14–14.97] | 14.08 | 5/16000 | 0.87 · 14.08 · 0/16000 | 0.88 · > hold |

**teastore-T16** (base 0.152 journey/s, 1.94 requests/s; 200 seeds)

| class | model: m · q · delay · lag · hold (s) | p | requests/s | miss | ? | miss periodic | median TTD all trials · detected (s) | mean TTD, miss = hold (s) | FA no-fault | failed rule only: miss · mean · FA | analytic miss · median |
|---|---|---|---|---|---|---|---|---|---|---|---|
| auth-freeze | 1 · 0.93 · 0.25 · 0.03 · 150.4 | 1 | 1.94 | 0.00 | 0.00 | 0.00 | 15.26 · 15.26 [15.17–15.30] | 15.25 | 0/18 | 0.00 · 15.25 · 0/18 | n/a |
| auth-freeze | 1 · 0.93 · 0.25 · 0.03 · 150.4 | 0.2 | 0.388 | 0.01 | 0.00 | 0.00 | 26.20 · 26.20 [0.07–146.71] | 34.87 | 224/3600 | 0.01 · 34.94 · 0/3600 | n/a |
| auth-freeze | 1 · 0.93 · 0.25 · 0.03 · 150.4 | 0.1 | 0.194 | 0.09 | 0.00 | 0.00 | 40.06 · 40.04 [0.09–146.71] | 59.59 | 239/3600 | 0.09 · 59.62 · 0/3600 | n/a |
| auth-freeze | 1 · 0.93 · 0.25 · 0.03 · 150.4 | 0.02 | 0.0388 | 0.60 | 0.00 | 0.55 | > hold · 66.69 [0.11–146.71] | 118.55 | 153/3600 | 0.60 · 118.61 · 0/3600 | n/a |
| auth-freeze | 1 · 0.93 · 0.25 · 0.03 · 150.4 | 0.01 | 0.0194 | 0.80 | 0.00 | 0.78 | > hold · 66.70 [0.20–146.71] | 134.68 | 129/3600 | 0.80 · 134.71 · 0/3600 | n/a |
| auth-freeze | 1 · 0.93 · 0.25 · 0.03 · 150.4 | 0.001 | 0.00194 | 0.97 | 0.00 | 0.98 | > hold · 80.03 [15.17–146.70] | 148.42 | 2/3600 | 0.97 · 148.42 · 0/3600 | n/a |
| persistence-crash | 1 · 0.06 · 6.78 · 0.03 · 161.0 | 1 | 1.94 | 0.00 | 0.00 | 0.00 | 17.46 · 17.46 [16.30–18.00] | 17.29 | 0/18 | 0.00 · 17.29 · 0/18 | n/a |
| persistence-crash | 1 · 0.06 · 6.78 · 0.03 · 161.0 | 0.2 | 0.388 | 0.08 | 0.02 | 0.14 | 33.43 · 27.81 [0.08–160.10] | 54.28 | 224/3600 | 0.68 · 115.32 · 0/3600 | n/a |
| persistence-crash | 1 · 0.06 · 6.78 · 0.03 · 161.0 | 0.1 | 0.194 | 0.16 | 0.21 | 0.16 | 100.11 · 40.12 [0.07–160.15] | 96.40 | 239/3600 | 0.83 · 136.80 · 0/3600 | n/a |
| persistence-crash | 1 · 0.06 · 6.78 · 0.03 · 161.0 | 0.02 | 0.0388 | 0.61 | 0.33 | 0.49 | > hold · 20.06 [0.12–160.11] | 154.29 | 153/3600 | 0.96 · 155.97 · 0/3600 | n/a |
| persistence-crash | 1 · 0.06 · 6.78 · 0.03 · 161.0 | 0.01 | 0.0194 | 0.79 | 0.19 | 0.75 | > hold · 17.91 [0.17–160.12] | 158.11 | 129/3600 | 0.98 · 158.67 · 0/3600 | n/a |
| persistence-crash | 1 · 0.06 · 6.78 · 0.03 · 161.0 | 0.001 | 0.00194 | 0.98 | 0.02 | 0.98 | > hold · — | 161.05 | 2/3600 | 1.00 · 161.05 · 0/3600 | n/a |

**otel-v3** (base 1 request/s, 1 requests/s; 200 seeds)

| class | model: m · q · delay · lag · hold (s) | p | requests/s | miss | ? | miss periodic | median TTD all trials · detected (s) | mean TTD, miss = hold (s) | FA no-fault | failed rule only: miss · mean · FA | analytic miss · median |
|---|---|---|---|---|---|---|---|---|---|---|---|
| frontend-pause | 1 · 0.92 · 0.70 · 15.00 · 155.5 | 1 | 1 | 0.00 | 0.00 | 0.00 | 15.70 · 15.70 [6.70–15.74] | 14.95 | 0/24 | 0.00 · 14.95 · 0/24 | n/a |
| frontend-pause | 1 · 0.92 · 0.70 · 15.00 · 155.5 | 0.2 | 0.2 | 0.00 | 0.00 | 0.00 | 17.74 · 17.74 [6.70–75.70] | 20.24 | 1/4800 | 0.00 · 20.24 · 0/4800 | n/a |
| frontend-pause | 1 · 0.92 · 0.70 · 15.00 · 155.5 | 0.1 | 0.1 | 0.00 | 0.00 | 0.00 | 20.74 · 20.74 [6.70–138.73] | 28.50 | 5/4800 | 0.00 · 28.50 · 0/4800 | n/a |
| frontend-pause | 1 · 0.92 · 0.70 · 15.00 · 155.5 | 0.02 | 0.02 | 0.20 | 0.00 | 0.00 | 75.74 · 52.72 [6.70–154.76] | 82.45 | 148/4800 | 0.20 · 82.45 · 0/4800 | n/a |
| frontend-pause | 1 · 0.92 · 0.70 · 15.00 · 155.5 | 0.01 | 0.01 | 0.44 | 0.00 | 0.22 | 136.75 · 66.72 [6.70–154.76] | 109.53 | 114/4800 | 0.44 · 109.53 · 0/4800 | n/a |
| frontend-pause | 1 · 0.92 · 0.70 · 15.00 · 155.5 | 0.001 | 0.001 | 0.93 | 0.00 | 0.92 | > hold · 77.69 [15.67–154.72] | 150.05 | 0/4800 | 0.93 · 150.05 · 0/4800 | n/a |

### Where a sampled or per-record sensor first beats the thinned ledger (its signal's own load dependence not measured)

For each class and family: the sensor's measured time to detection (full load; a miss counts as never) against the thinned ledger's, per (episode × seed); `first rate` = the highest request rate on the grid at which the sensor is faster in more than half the trials (`—`: at no rate down to p = 0.001). Analytic = λ_m / (q·(t − d − l)) with t the sensor's median over all its episodes (`—` if it misses in half or more), d the effect delay, l the ledger's observation lag, λ_1 = ln 2; ∞ = the sensor is faster than d + l, so faster at any rate; n/a = the Poisson model does not apply (scattered crossings, or TeaStore's journey-clustered requests). M and S sample at a fixed cadence whatever the traffic; L is per record and its coupling to requests is unknown here (`?`), so its row is not a request-independent comparison. Spans thin with requests and are not compared.

M and S sample at a fixed cadence, so their times are set by where the first sample after the effect falls (docker stats every 3.07 s, cgroup every 5 s): M catches fall only at 1.45-1.51, 4.55-4.58 and 7.57-7.65 s, S at 4.8, 9.8 and 14.8 s. With a random sampling phase the same sensor would take [effect, effect + cadence]; the rates below hold for this campaign's phase only. Hotel log rows (whole-second stamps) are timed at the stamp's end and coincide with the ledger failure they report (same request), so their crossover is a stamp artefact; they are kept only for completeness.

| population | class | family | detected | sensor TTD (s) | faster at full rate | first rate faster (req/s) | first rate, mean TTD miss = hold (req/s) | analytic (req/s) | without BC: detected · first rate |
|---|---|---|---|---|---|---|---|---|---|
| hotel-lmt2 | cpu-throttle | M | 1/8 | 7.58 | 0.12 | — | 10 | n/a | 1/8 · — |
| hotel-lmt2 | cpu-throttle | S | 3/16 | 14.81 [9.81–14.82] | 0.19 | — | 10 | n/a | 3/16 · — |
| hotel-lmt2 | cpu-throttle | S:own | 15/16 | 4.81 [4.79–9.78] | 0.94 | 10 | 10 | n/a | 15/16 · 10 |
| hotel-lmt2 | net-delay | M | 1/8 | 7.57 | 0.00 | — | 0.02 | — | 1/8 · — |
| hotel-lmt2 | net-delay | S | 4/16 | 14.85 [4.86–14.86] | 0.00 | — | 0.02 | — | 4/16 · — |
| hotel-lmt2 | net-delay | M:own | 1/8 | 7.57 | 0.00 | — | 0.02 | — | 1/8 · — |
| hotel-lmt2 | net-delay | S:own | 1/16 | 14.86 | 0.00 | — | 0.01 | — | 1/16 · — |
| hotel-lmt2 | reservation-pause | M | 8/8 | 7.61 [1.48–7.65] | 0.00 | 0.2 | 0.2 | 0.115 | 0/8 |
| hotel-lmt2 | reservation-pause | S | 5/16 | 14.86 [9.86–14.87] | 0.00 | — | — | — | 5/16 · — |
| hotel-lmt2 | reservation-pause | L | 12/12 | 1.60 [1.22–2.13] | 0.00 | 1 | 1 | 1.71 | 0/12 |
| hotel-lmt2 | reservation-pause | M:own | 8/8 | 1.49 [1.45–1.50] | 0.00 | 1 | 2 | 2.26 | 0/8 |
| hotel-lmt2 | search-pause | M | 8/8 | 1.49 [1.47–1.51] | 0.00 | 1 | 2 | 2.28 | 0/8 |
| hotel-lmt2 | search-pause | S | 6/16 | 4.86 [4.85–14.86] | 0.00 | — | 0.02 | — | 6/16 · — |
| hotel-lmt2 | search-pause | M:own | 8/8 | 1.49 [1.47–4.56] | 0.00 | 1 | 1 | 2.26 | 0/8 |
| hotel-sel1 | cpu-throttle | S | 6/16 | 14.81 [14.79–14.81] | 0.38 | — | 10 | n/a | 6/16 · — |
| hotel-sel1 | cpu-throttle | S:own | 15/16 | 4.81 [4.79–9.81] | 0.94 | 10 | 10 | n/a | 15/16 · 10 |
| hotel-sel1 | net-delay | M | 5/12 | 7.62 [7.61–7.63] | 0.00 | — | 0.1 | — | 5/12 · — |
| hotel-sel1 | net-delay | S | 7/16 | 14.84 [4.85–14.86] | 0.00 | — | 0.1 | — | 7/16 · — |
| hotel-sel1 | net-delay | M:own | 2/12 | 7.62 [7.61–7.63] | 0.00 | — | 0.1 | — | 2/12 · — |
| hotel-sel1 | net-delay | S:own | 1/16 | 14.86 | 0.00 | — | 0.01 | — | 1/16 · — |
| hotel-sel1 | reservation-pause | M | 12/12 | 1.49 [1.46–7.62] | 0.00 | 1 | 1 | 2.28 | 0/12 |
| hotel-sel1 | reservation-pause | S | 8/16 | 14.84 [9.86–14.87] | 0.00 | — | 0.01 | — | 8/16 · — |
| hotel-sel1 | reservation-pause | L | 12/12 | 1.71 [1.37–2.16] | 0.00 | 1 | 1 | 1.38 | 0/12 |
| hotel-sel1 | reservation-pause | M:own | 12/12 | 1.49 [1.46–4.56] | 0.00 | 1 | 1 | 2.27 | 0/12 |
| hotel-sel1 | search-pause | M | 12/12 | 1.49 [1.47–1.51] | 0.00 | 1 | 2 | 2.32 | 0/12 |
| hotel-sel1 | search-pause | S | 6/16 | 7.36 [4.86–14.86] | 0.00 | — | 0.02 | — | 6/16 · — |
| hotel-sel1 | search-pause | M:own | 12/12 | 1.49 [1.47–4.58] | 0.00 | 1 | 1 | 2.32 | 0/12 |
| hotel-int1 | cpu-throttle | S | 6/16 | 14.80 [4.82–14.82] | 0.38 | — | 10 | n/a | 6/16 · — |
| hotel-int1 | cpu-throttle | S:own | 11/16 | 4.81 [4.67–4.82] | 0.69 | 10 | 10 | n/a | 11/16 · 10 |
| hotel-int1 | geo-delay | S | 3/16 | 9.84 [4.83–9.86] | 0.00 | — | 0.1 | n/a | 3/16 · — |
| hotel-int1 | geo-delay | S:own | 2/16 | 9.84 [4.83–14.84] | 0.00 | — | 0.02 | n/a | 2/16 · — |
| hotel-int1 | rate-delay | M | 2/12 | 9.14 [7.61–10.67] | 0.08 | — | 0.05 | n/a | 2/12 · — |
| hotel-int1 | rate-delay | S | 3/16 | 9.85 [9.84–14.85] | 0.00 | — | 0.02 | n/a | 3/16 · — |
| hotel-int1 | search-pause | M | 12/12 | 1.50 [1.46–7.65] | 0.00 | 0.5 | 0.2 | 2.26 | 0/12 |
| hotel-int1 | search-pause | S | 9/16 | 4.87 [4.86–14.86] | 0.00 | 0.01 | 0.02 | 0.0543 | 9/16 · 0.01 |
| hotel-int1 | search-pause | M:own | 12/12 | 1.49 [1.46–4.56] | 0.00 | 1 | 1 | 2.27 | 0/12 |
| teastore-T16 | persistence-crash | L | 9/9 | 13.39 [13.38–13.41] | 1.00 | 1.94 | 1.94 | n/a | 0/9 |

Never detecting (with or without BC), so no crossover: hotel-int1 L: cpu-throttle, geo-delay, rate-delay, search-pause; hotel-int1 L:own: cpu-throttle, geo-delay, rate-delay, search-pause; hotel-int1 M: cpu-throttle, geo-delay; hotel-int1 M:own: cpu-throttle, geo-delay, rate-delay; hotel-int1 S:own: rate-delay, search-pause; hotel-lmt2 L: cpu-throttle, net-delay, search-pause; hotel-lmt2 L:own: cpu-throttle, net-delay, reservation-pause, search-pause; hotel-lmt2 M:own: cpu-throttle; hotel-lmt2 S:own: reservation-pause, search-pause; hotel-sel1 L: cpu-throttle, net-delay, search-pause; hotel-sel1 L:own: cpu-throttle, net-delay, reservation-pause, search-pause; hotel-sel1 M: cpu-throttle; hotel-sel1 M:own: cpu-throttle; hotel-sel1 S:own: reservation-pause, search-pause; teastore-T16 L: auth-freeze; teastore-T16 L:own: auth-freeze, persistence-crash.

## BC-caller-log: the templates it flags

Structural rule (warn/error/other-level template of a direct caller of the target, firing by appear). Listed so a reader can check each one is a caller's log about its failed call; admissible fires per episode count:

- hotel-lmt2: reservation-pause-effect log:frontend:4ae82b46d72e (target reservation) × 12 episodes: `error SearchHandler CheckAvailability failed`
- hotel-sel1: reservation-pause-effect log:frontend:4ae82b46d72e (target reservation) × 12 episodes: `error SearchHandler CheckAvailability failed`
- teastore-T16: persistence-crash-effect log:auth:6c19cf62298a (target persistence) × 9 episodes: `warn An exception mapping did not successfully produce and processed a response. Logging the exception propagated to the default exception mapper`

## Findings (instance scope; contrasts, not mechanisms)

- **The ledger's time to detection, per class, as a measured decomposition** (bound to first observed failure; `failed` rule; every catch BC-ledger-stopped-on-path). Hotel pauses: E 16/16 in every population, 1.13-1.18 s: the first affected request starts 0.16 s after the bound (median) and the client reports `transport-error` at its 1.00 s timeout. TeaStore auth-freeze 9/9, 15.17-15.30 s: the first affected request starts 0.15-0.28 s after the bound and ends in the client's 15 s `timeout`. TeaStore persistence-crash 9/9, 16.30-18.00 s: the first failure is a login-action request that starts with the journey at about +13.3 s and returns HTTP 500 after 3.0-4.7 s; the `stop` command itself takes ~11 s (command duration 10.9 s), so neither a timeout nor the command bound sets this time. OTel 11/12 at 15.67-15.74 s (frontendproxy returns 504 at its 15 s upstream timeout) and 1/12 at 6.70 s (a 503 after 5.0 s); the target is the entry, so the ledger is the target's own sensor there, and the 5xx come from frontendproxy, a caller of the target.
- **At K = 4, 1 ms floor, the single-request latency rules are G3-inadmissible on Hotel and OTel, and admissible on 2 of 4 TeaStore routes.** `spike` and `watchdog` (an in-flight request's age crossing the per-request threshold) fire in 7-20 of 20 Hotel no-fault windows per posture and 2-3 of 6 OTel: inadmissible in 15 of 15 (population, posture) cells there. On TeaStore they are admissible on `login-action` (0/6 in 3 of 3 postures) and `home` (0/6 in 2 of 3), inadmissible on `product` (5-6/6) and `category` (2-3/6). `failed`, `run3` and `median` have 0 no-fault firings in all 19 (population, posture) cells. Where it is admissible, the watchdog (not part of E) catches TeaStore auth-freeze at 6.77-6.79 s (median per posture) against E's 15.25-15.28 s, and persistence-crash at 13.44-13.45 s against 17.04-17.91 s. On Hotel the watchdog would sit at 0.14-0.19 s but is inadmissible at this setting; the setting is this analysis's engineering default, not a preregistered rule, and no other was run.
- **On stopping faults, the sensors faster than the ledger at full load are by-construction catches or a tracer copy of it; on the delays they are spans that are not flagged.** Hotel pauses, M: CPU of callers (frontend) and of the stopped path's callees (rate, geo) dropping, BC-idle-cpu in every case, per-(class, posture) medians 1.48-1.50 s in 11 of 13 cells and 7.63-7.64 s in 2; 0/8-0/12 without BC. Without BC, the remaining span catch of every Hotel pause is the entry's own root span erroring (`span:frontend:HTTP_GET_/hotels:error`, 1.16 s, the ledger's failure seen by the tracer); the MAP taxonomy does not flag it, and whether it should is the user's call. TeaStore persistence-crash: auth's exception-mapper warning (BC-caller-log; sub-second stamps) 9/9 at 13.38-13.41 s vs E 16.30-18.00 s; without BC, `full`'s webui LoginActionServlet latency spike (3/3, 13.41-13.43 s) and one `selected` span catch (1/3, 126.73 s) remain. Non-stopping faults: see the delay finding below.
- **Hotel's logs coincide with the ledger; the stamp cannot order them.** frontend's `SearchHandler CheckAvailability failed` (BC-caller-log) catches reservation-pause 12/12 in lmt2 and sel1 (int1 has no reservation fault). The handler logs and writes the 500 in the same branch (services/frontend/server.go:270-272), and the reviewer found all 24 stamps equal floor(onset + E's failure time): it is the same failed request the ledger reports, at its 1 s client timeout. Its whole-second stamp makes each catch an interval [s, s + 1) − onset that contains the ledger's time in 24 of 26 Hotel log catches and lies wholly after it in 2; the tables use the end s + 1 (per-posture medians 1.49-1.94 s vs E 1.16-1.17 s), which is a stamp artefact in the slow direction, as timing at s (0.49-0.94 s, the first version of this document) was one in the fast direction. Read the L rows of tables 0-1, the L impact and the L crossover rows as 'coincides with the ledger', not as faster or slower. Two further Hotel log records are stamped in the hold's last second and are not counted (`logStraddlesHoldEnd`).
- **BC-caller-log is structural here and over-reaches in 3 of 36 flagged (template, episode) pairs.** It flags a warn/error template of a direct caller of the target. 33 pairs carry a message about the call to the target (`CheckAvailability failed` during reservation-pause, 24; auth's warning during persistence-crash, 9; listing below). The other 3 are frontend logs about a different callee: `GetProfiles failed` (sel1 reservation-pause metrics, int1 search-pause full) and `CheckAvailability failed` (sel1 search-pause full). All three are stamped in the hold's last second and so no longer count as catches; a content rule would change no episode-level outcome now.
- **The delays are where spans catch while the ledger misses.** Configured netem delay 1 ms on int1, 100 ms on lmt2/sel1 (lmt_faults.py:37); the shifts seen at the entry are about 2 ms and 200 ms. hotel-int1 geo-delay: E 4/4, 4/4, 2/4, 0/4 under none, metrics, selected, full; spans 4/4 under selected (frontend's `/search.Search/Nearby`, Tsel, 0.31 s median) and full (search's client span to geo, `spike`, 0.06 s; T family false alarms 2/20, first at ~1.0 s). rate-delay: E 4/4, 4/4, 2/4, 1/4; spans 4/4 at 0.26 s (selected) and 0.20 s (full; FA 2/20). The ledger's per-request threshold K·1.4826·MAD rises from 1.7-2.1 ms (none) to 3.2-3.9 ms (full) (reviewer's recomputation), the posture effect of decision 9; under this analysis's online rules E catches 10/16 and 11/16 of the int1 delays, not decision 9's 4/16 and 5/16. lmt2/sel1 net-delay: E 16/16 at 0.43-0.57 s (run3/median), T/Tsel 4/4 at 0.36-0.46 s. Span times are span ends; Hotel's Jaeger reporter flushes every 1 s, so span-vs-ledger differences under 1 s are not resolvable. The span catches are not BC-flagged because the taxonomy flags caller spans only for stopping faults; they time the target's RPC. Every ranking here is at one setting (K = 4, 1 ms floor); protocol §3 requires the K × floor grid, which was not run, and H4 found this int1 ranking in 4 of 9 settings.
- **The cgroup sampler (S, 5 s) in a 15 s hold: catch counts in the range of its false-alarm counts.** All 66 first outside S catches are `sys_memory` and fall on the sample instants (4.8, 9.8, 14.8 s). Detection k/16 per (population, class) sits beside family false-alarm counts of 0-9/20 per posture (e.g. sel1 search-pause S 6/16 vs FA 9/20, 3/20, 3/20, 1/20); no interval was computed, so no statement of 'above' or 'at' the false-alarm rate is made. The one recurring pattern is frontend's memory rising while search is paused (first no-BC S catch in 4/16 lmt2, 6/16 sel1, 7/16 int1 search-pause episodes; at the first sample, 4.86-4.87 s, in most of them; not BC-flagged). cpu-throttle: E 0/16 in every population; outside S 3/16, 6/16, 6/16; the throttled service's own sensors catch 15/16, 15/16, 11/16 (G2: own), by PSI in 14, 14 and 11 of them, at 4.67-9.81 s.
- **Impact before detection** (ledger requests started between the bound and the first catch, clipped to the hold, that failed or crossed their route's per-request threshold; detected episodes): Hotel pauses E 11 in every episode (149 of 150 hold requests are bad, so the count is the rate times the time to detection), docker CPU M 14-75; Hotel L 11-20 at the stamp's end (it coincides with the ledger, see above); TeaStore auth-freeze E 3, persistence-crash E 1-2 of 26 bad in the hold; OTel E:own 7-8.
- **Thinning the ledger (a bound on the ledger side only; G3 re-derived at each rate).** Hotel pauses, Bernoulli, 200 seeds × 16 episodes per class: miss within the 15 s hold 0.00 down to 1 req/s, 0.05-0.06 at 0.2, 0.24-0.25 at 0.1, 0.86-0.87 at 0.01 req/s; the Poisson model gives 0.08, 0.27, 0.88. Mean time to detection with misses charged at the hold end (decision 15): 1.16-1.17 s at 10 req/s, about 2.0 at 1, 5.7-5.8 at 0.2, 8.6-8.8 at 0.1, 14.0-14.1 at 0.01. A periodic schedule never misses down to 0.1 req/s (one request every 10 s always lands in a 15 s hold). Thinned no-fault false alarms of E with the re-derived rules (in-sample, so a lower value): Hotel 5-520 per 16,000 trials (p < 1, three populations), TeaStore 224/3600 at p = 0.2, OTel ≤ 114/4800; the failure rule alone has 0 at every rate in every population. TeaStore persistence-crash at p = 0.2: miss 0.08 with all rules vs 0.68 with the failure rule alone, so most thinned catches there come from latency rules whose false-alarm rate is 6 %. OTel: the generator caps concurrency at 8 with a 15 s timeout, so only 85 of ~155 scheduled requests start during the pause; thinning that record is not a lower offered rate, and its rows (miss 0.44 at 0.01 req/s) are not a bound.
- **Crossover (sampled sensors at this campaign's sampling phase, against the thinned ledger).** On Hotel pauses, docker CPU (M, BC-idle-cpu) is faster than the thinned ledger in more than half the trials from 1 req/s down in 3 of 5 (population, pause class) cells and from 0.5 and 0.2 req/s in the other two (analytic 2.26-2.32 req/s; 0.115 for lmt2 reservation-pause, whose M median is 7.6 s); without BC there is no M catch (0/8, 0/12). The S family on int1 search-pause (9/16, mostly frontend memory) is faster from 0.01 req/s. M's times are its first, second or third sample after the effect (3.07 s cadence), so these rates hold for this phase only; with a random phase the same sensor takes anywhere in [effect, effect + cadence]. The signals behind every crossover plausibly need load (callers idling behind a stopped peer, blocked requests holding memory); whether they weaken at lower load is not measured here and is what decision 15's traffic sweep tests on the host.
- Scope of every line above: **instance** (one host and one campaign per population; n = 4 episodes per Hotel (class, posture), 3 per TeaStore and OTel; no-fault windows are sub-windows of 4 or 3 cells; TeaStore's no-fault cells hold no timed log record, so its log G3 and false-alarm rates are untestable, `?`, and its log catches carry †). The rules are this analysis's engineering defaults at one setting; the affected-path rule is a service-level approximation of round 4's decision 7; under the window rule of `research/protocol/sensor_rep/` the detection counts differ (e.g. its ledger 16/16 on the int1 delays).

## Engineering defaults and limits

- Baselines are each cell's own pre-window, per sample / per request (decision round 4: ledger spread per request); the sensor_rep window rule (no-fault tiles, window medians) is not used for timing because a window median has no time.
- K = 4, scale 1.4826, floors from sensor_rep/catch.py (span latency 1 ms, ledger 1 ms, metric floors from symptoms.py / lmt_detect.py, else 2 % of the median); comparator `>=`; >= 3 pre-window samples for a level threshold.
- run3 = 3 consecutive samples; median = online median of >= 3 in-window samples; absent = silence > 2 x the longest pre-window gap after >= 5 pre-window records. One rule pool for every channel; no detector selection (§2b not run).
- No-fault windows: hold-length windows at onset_med + i·hold inside every valid no-fault cell of the posture, each with its own pre-window; windows of one cell are not independent (n_eff is stated with its cells). Later windows have longer pre-windows than the fault cells.
- G3 per (posture, sensor, rule) at τ = 0.05. Hotel n_eff = 20 per posture (k <= 1 admissible); TeaStore and OTel 6 (k = 0). TeaStore no-fault cells hold no application log records, so log rules there cannot be removed by G3.
- The affected call path for spikes is service-level (target, transitive callers, transitive callees in the project map's call graph); per-request trace attribution was not done.
- Observation time = when a record becomes available (span end, request end, log stamp, metric stamp). docker stats and cgroup rates are stamped at the end of their interval.
- Detection is counted only inside the hold [command bound, hold end]; a catch after the revert is not a detection.
- Ledger readers: visibility.hotel_ledger_rows / teastore_ledger_rows (checked equal, journey index kept) / otel_ledger_rows. Ledger latency baselines are per route; TeaStore has four routes.
- OTel: barrier-relative fault offsets against the ledger's own start stamp (taken after the barrier), skew not measured.
- Thinning keeps the full-rate admissible ledger rules; E only (failed, spike, run3, median).

## Review

- One independent read-only adversarial review, Opus subagent (`adversarial-review`), 2026-10-02/03; the Fable attempt hit its rate limit. It reviewed the outputs written at 13:58Z and found 4 blockers, 11 major and 11 minor issues. The main session separately reported that Hotel log catches are artefacts of the whole-second stamp.
- Applied in code:
-   - B1: whole-second log records count only if s + 1 <= hold end, and impact is clipped to the hold (with a planted check and a mutant).
-   - B2: per-route ledger G3 in table 3, denominator 19.
-   - M3: TeaStore log G3 is printed `?`, with † on its catches.
-   - M7: G3 is re-derived at each thinning rate, with the failure rule alone reported beside it.
-   - M8: the OTel analytic model is n/a and its thinning is not a bound.
-   - M9: the path rule is labelled service-level.
-   - m1/m2/m3/m4: docstring, analytic formula with d, the OTel onset check and the citation.
-   - New self-checks: a planted two-clock eval_window cell, plus log-stamp and hold-cap mutants. The self-check has 36 checks, and 5/5 mutants are caught.
- Applied in the findings:
-   - B3: E as a per-class decomposition.
-   - B4: the headline is restricted to stopping faults; M is counted in 13 cells.
-   - M1: Hotel logs coincide with the ledger.
-   - M2: the sampling phase is noted.
-   - M4: the section is renamed and the throttle sentence dropped.
-   - M5: configured delays, the selected-posture sensor, the full false alarms, decision 9's counts and the single setting.
-   - M6: the span flush.
-   - M10: this record.
-   - M11: wording and counts.
-   - m6-m10.
- Not done: the K × floor grid (protocol §3); request-level path attribution (decision 7); hashing the evidence directories (m11; the JSON records paths, the script sha and HEAD only).
