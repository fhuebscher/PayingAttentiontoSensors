# Hotel `selected`: one place-measure-check iteration (declared 2026-09-29 07:30Z, before any code or cell)

Authority: user 2026-09-29 ("run the experiments yourself that would clear the reviewers' doubt"), which delegates the design
choices below; they are recorded here as mine. Purpose: the prior reviews (ACSOS, `papers/reviews/ACSOS_official_reviews_20260712.md`)
found self-improvement only as future work (R2, R3) and Hotel has no intermediate placement. This runs one loop iteration:
a placement derived from one campaign (lmt2) is measured on a fresh one, with predictions fixed here.

## Placement (derived in-sample from lmt2, `NOTE.md`)

Goal: catch every fault class that any span sensor catches outside the target, with the fewest traced services. On lmt2, service
granularity, k = 1: `frontend` alone (its spans catch search-pause, reservation-pause and net-delay 4/4 each, cpu-throttle 0/4 as all
spans do; 0 no-fault firings; 94,499 of 351,325 spans).

## Design

- Harness: successor of `lmt-pilot-20260928` (40682b7), epoch `hotel-reservation-selected-v1`, fb14srv4. Not pooled with lmt2 or #1-#8.
- 80 cells = 5 regimes (no-fault cost, search-pause, reservation-pause, cpu-throttle, net-delay; same fault parameters as lmt2)
  x 4 blocks x 4 postures, a 4x4 Latin square per regime.
- Postures (logs at info and the 1-s docker-stats sampler in all but `none`, so each step below changes one thing):

| posture | app log level | docker-stats sampler | tracer |
|---|---|---|---|
| `none` | fatal | off | disabled on all 10 |
| `metrics` | info | on | disabled on all 10 |
| `selected` | info | on | `frontend` only (ratio 1); NoopTracer on the other 9 |
| `full` | info | on | all 10 (ratio 1) |

- Analysis: `cost_steps.py` and `lmt_detect.py` of the LMT pilot with the posture names changed only (committed before the run):
  steps `none->metrics`, `metrics->selected`, `selected->full`, `metrics->full`; span family scored separately per posture,
  `Tsel` (selected, n 4 per regime) and `T` (full, n 4), each gated by G3 on its own 4 no-fault windows.

## Predictions (read yes / no / `—`)

| # | prediction | reads yes iff |
|---|---|---|
| P1 | `selected` catches what its derivation says | `Tsel` caught 4/4 in search-pause, reservation-pause and net-delay |
| P2 | `selected` loses nothing that `full` catches | in every regime, `Tsel` caught >= `T` caught |
| P3 | `selected` costs less than `full` | `selected->full` total CPU-s delta > 0 in 4/4 blocks |
| P4 | `selected` costs more than no tracing | `metrics->selected` total CPU-s delta > 0 in 4/4 blocks |

Reported without a pass rule: the span count of `selected` as a share of `full`; the p50 latency of each step; the lmt2 carried
contrast `metrics->full` (sign in 4/4 blocks). Scope: instance, one host, n = 4 blocks. P2 at n = 4 is not an equivalence test.

## Stop rule

- Launch by 2026-09-29 15:00Z or not at all for the ASOCA paper. Not terminal by 2026-09-30 06:00Z: not used in the paper.
- The launcher's own rule (>= 3 blocked cells, 0 valid) stops it; one relaunch after a fix, no second.
- Paper text only after a Fable adversarial review of the result.

## Erratum (2026-09-29, after the run; the declaration above is unchanged)

The header says "declared 2026-09-29 07:30Z"; the commit f120805 is 07:10:44Z, before the harness commit (07:23:46Z), the launcher
(07:26:13Z) and the first cell (07:28:07Z). 07:30Z was a typo; git is the record.
