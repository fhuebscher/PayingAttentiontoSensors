# Detection by signal family: result (2026-09-24)

Definitions: `DETECTION_DEFINITIONS.md` (frozen 99e6c0e; amendment A1 0ab0c50, post hoc).
Script: `research/sprint-draft2/detection.py` (`--self-check` passes). Evidence stays in `tmp/`.
Scope: **instance**. One host per SUT, one workload, pause and crash faults only. No intervals, no p-values.

```sh
X=tmp/sprint-hotel6-x   # the five Hotel #6 snapshots from tmp/hotel6-evidence/*.tgz, extracted
/usr/bin/python3 research/sprint-draft2/detection.py hotel $X/hotel-v1-20260922t002056z-969a1362 \
  $X/hotel-v1-20260923t021034z-a8e7e72e $X/hotel-v1-20260923t061605z-88b7bf7c $X/hotel-v1-20260924t012134z-7fd8717d [--a1]
/usr/bin/python3 research/sprint-draft2/detection.py teastore tmp/teastore-e3-user-a5-evidence/teastore-candidate-pilot-v3-user
```

## HotelReservation (fb14srv4, campaign #6 runs 3–6, 216 valid cells of 216)

The episode window is the pause itself: 15 s, from `fault-receipt.json`. Each posture has 24 episodes
per regime. False alarms (FA) are counted over 24 no-fault cells per posture, each with a 15 s
pseudo-window at the same offset.

| regime | family | none | sample-zero | full | FA (72 no-fault) |
|---|---|---|---|---|---|
| reservation-pause | log (level ∪ novelty) | 24/24 | 24/24 | 24/24 | 0 |
| | metric, target's CPU | 23/24 | 24/24 | 24/24 | 0 |
| | metric, other services' CPU | 24/24 | 24/24 | 24/24 | 10 |
| | trace, error span | 0/24 † | 0/24 † | 24/24 | 0 |
| search-pause | log (level ∪ novelty) | **0/24** | **0/24** | **0/24** | 0 |
| | metric, target's CPU | 24/24 | 23/24 | 24/24 | 4 |
| | metric, other services' CPU | 24/24 | 24/24 | 24/24 | 6 |
| | trace, error span | 0/24 † | 0/24 † | 24/24 | 0 |

† True by construction: no spans are exported under `none` or `sample-zero`.

- Metric union FA: 10/72 for either target set. Log FA: 0/72.
- Latency from window start (median, [min, max] over detected episodes):
  - log: 0.6–0.7 s [0.2, 1.1];
  - metric: 1.5 s [0.5, 4.6], limited by the sampler's ~3 s effective spacing;
  - trace: 0.2 s [0.1, 0.2].
- Log detection on reservation-pause comes from the level detector, via frontend's
  `ERR services/frontend/server.go:271` lines. Novelty fired in 18 of 24 episodes per posture.
- **Search-pause produces no log event in any of 72 episodes.** Every application line parses: under
  A1, the only unparsed lines are the harness's request-witness lines and one compose warning.
  So this zero is not a parser gap. The frozen parser and A1 give identical counts.
- Family overlap per regime (72 episodes):
  - reservation-pause: log + both metric parts 47; the same plus trace 24; log + metric-other 1.
  - search-pause: both metric parts 47; the same plus trace 24; metric-other 1.

## TeaStore (fb14srv5, epoch 3 user rung a5; cell level)

TeaStore's native log lines have no timestamp, so detection is per cell: any alert-level line, or a
template absent from the no-fault cells. No metric family is available: fault cells are
`diagnostic-only`, so the metric result is `—`. Valid cells: 32 of 36 (4 blocked, excluded).

| regime | log level | log novelty | FA over 12 no-fault cells (leave-one-out) |
|---|---|---|---|
| persistence-crash | 11/11 | 11/11 | level 0, novelty 0 |
| auth-freeze | **0/9** | **0/9** | |

- The level detector is auth's `registryclient.loadbalancers.ServiceLoadBalancer` WARN: 241 lines in
  11 cells, emitted by a neighbour of the crashed service.
- Novelty is mostly the restarted service's startup lines, which is close to true by construction for
  a crash-restart fault.

## What this supports (for the judge, then the paper)

- The log family's detection depends on which service is faulted, not on the fault type. Both Hotel
  faults are 15 s pauses, yet logs detected reservation-pause in 72/72 and search-pause in 0/72, with
  0 false alarms. On TeaStore, logs detected persistence-crash in 11/11 and auth-freeze in 0/9.
  "Crash vs freeze" does **not** describe this: reservation-pause is a freeze.
- On Hotel, a harness-observed CPU metric detected every pause episode. It did so through other
  services' CPU as well as the target's, at 10/72 false alarms.
- Log and metric detection counts differed by at most one episode across the three trace postures.
  The trace family's own detection is zero under `none` / `sample-zero` by construction.

## What it does not support

- Not a multi-modal *placement* result: metrics have no activation choice and logs no measured cost.
- Not a cross-SUT claim about metrics (TeaStore `—`), nor about which fault types logs miss. It covers
  two SUTs, four fault targets and one host each.
- The target-CPU detector for pause, and TeaStore novelty for crash-restart, are close to true by
  construction. The other-service metric and the neighbour log lines are the non-trivial parts.
- Detection means an event inside the window. It does not mean the event was *attributed* to the right service.

## Judge (2026-09-24; 2-member panels, the third provider returned 403)

All four proposed sentences were refuted. No detection sentence enters the paper as written.

| claim | refuted | eval | surviving objection |
|---|---|---|---|
| log detection depended on the faulted service | 1/2 (split) | `eval_aada6b94…` | service identity is not isolated from call-graph position or timeouts; say "differed between the two pause regimes" |
| CPU metric detected all 144 | 2/2 | `eval_097bf4e8…` | the target hit is a tautology; the 9-service union inflates chance; the other-services counts were missing from my evidence (they are 72/72) |
| trace posture did not change log/metric detection | 2/2 | `eval_2e2ebc72…` | equal totals are not episode-level agreement; it is a weak robustness check |
| no family detected all at 0 FA except full-posture spans | 2/2 | `eval_74d0a1b8…` | one configuration per detector is a detector result, not a family property; "full was necessary" does not follow |

What survives: the counts in the tables above, stated as results of **the evaluated detector
configurations** (one each, parameters fixed before counting), at instance scope. The significance
lens refuted every framing as too thin for a results section.

## Sweep (SWEEP_PLAN.md, 82b9cd4; full output in `out/sweep-hotel.txt`, `out/sweep-teastore.txt`)

```sh
/usr/bin/python3 research/sprint-draft2/detection.py hotel-sweep <the four run dirs> --a1
/usr/bin/python3 research/sprint-draft2/detection.py teastore-levels tmp/teastore-e3-user-a5-evidence/teastore-candidate-pilot-v3-user
```

The whole grid is the result: k ∈ {3, 4, 5, 6} × floor ∈ {0.5, 1, 2} pp, which is 12 configurations.

**Metric, other services' CPU (union of the 9 non-paused services).** Detections and false alarms
are each out of 72.

| floor | reservation-pause: detected | false alarms | search-pause: detected | false alarms |
|---|---|---|---|---|
| 0.5 pp | 71–72 | 22–56 | 72 | 20–52 |
| 1 pp | 71–72 | 4–10 | 71–72 | 3–6 |
| 2 pp | 69–70 | **0** | 71–72 | **0** |

- With a 2 pp floor there are 0/72 false alarms in all four k values.
- The false alarms follow the floor, not k.
- Services that carry the signal, at floor ≥ 1 pp and every k:
  - reservation-pause: frontend (53–72) and profile (30–72);
  - search-pause: frontend (71–72), rate (71–72), reservation (52–72), profile (31–72) and geo (0–23).
- rate and geo sit downstream of search, so the signal appears in services the paused service calls,
  as well as in its callers.
- attractions, recommendation, review and user: 0 detections in every configuration. They are not
  on the workload's path.

**Metric, target's own CPU:** reservation 56–72/72, search 70–72/72. The target's false alarms are 0/72
at floor ≥ 2 and at most 14/72 otherwise. As before, this is close to true by construction.

**Logs (Hotel).**
- warn+ and error+ give identical results: reservation-pause 72/72, search-pause 0/72, 0/72 false alarms.
- Every detection is from **frontend**.

**Logs (TeaStore, cell level).**
- warn+: persistence-crash 11/11, auth-freeze 0/9, no-fault 0/12.
- error+: 0/11, 0/9, 0/12. The crash detection therefore rests on WARN lines only.

**Traces (full only):** error spans came from frontend in reservation-pause (24/24), and from search
and frontend in search-pause (24/24 each).

**Posture agreement.** Of the 24 (run, block) groups per regime, all three postures agree in:
- log: 24/24 in both regimes and at both thresholds;
- other-services CPU: 21–24/24 over the 12 configurations;
- target CPU: 8–24/24 (the low end is k = 6, where the target detector itself drops to 56/72).

## Re-judge and decision (2026-09-24 13:40Z)

| sentence | refuted | eval | objection |
|---|---|---|---|
| logs, Hotel + TeaStore | 2/2 | `eval_b7f2724f…` | correctness: TeaStore per-cell distribution not given, and only 2 of 5 services captured; significance: too thin |
| other-services CPU over the grid | 1/2 (split) | `eval_1bd0162f…` | correctness **accepted** (with "rate, a service that search calls"); significance: too thin |
| posture agreement | 1/2 (split) | `eval_4d097a37…` | correctness **accepted**; significance: logs are posture-independent by construction, and the outcomes are saturated |
| fallback discussion paragraph | 2/2 | `eval_e254ca06…` | correctness: "left its pre-window range" misstates the threshold event; significance: moving it doesn't make it significant |

Tally: significance refuted 8 of 8. Under the SWEEP_PLAN stop rule, the sentences are dropped, and so is
the fallback paragraph. **No detection text enters the ASOCA paper.** Draft 1's existing TeaStore log
sentence and its "future work" sentence stay unchanged. The counts are thesis material.

## Correction: TeaStore lines are not all untimestamped

TeaStore writes two layouts, not one: log4j `[thread] LEVEL logger - msg`, which has no timestamp, and
Tomcat/JUL `dd-MMM-yyyy HH:mm:ss.SSS LEVEL [thread] logger msg`, which **has** one. The parser here
read log4j only. JUL lines were counted as unparsed, and their `WARNING` level was not read. Per crash
cell that is 21–23 log4j WARN lines plus 2–3 JUL WARNING lines. The broader count is the paper's
"25 or 26" (`TEASTORE_LOG_FEASIBILITY_20260922.md`), which stands.

The detection counts are unchanged: crash 11/11, freeze 0/9, no-fault 0/12. But the statement
"TeaStore detection must be cell-level" is too strong. Window-level detection is possible for the
JUL lines. Thesis backlog: add the JUL layout, and try window-level TeaStore detection.
