# Campaign F (OTel off-path faults, detection lanes): result (2026-10-14)

Scope: **instance** (OTel Demo 1.12.0, fb14srv6, 25 req/s of the upstream mix, 5 blocks, n = 2 test episodes per class).

- Declaration `research/traffic-sweep/DECLARATION_F_OTEL.md` (`8845721`); budget `BUDGET_F.md` (`db3be09`, amendment 1 `0214c07`); pass rule decisions
  99-102, 110-112 (unchanged from E); decision 73 kept. Harness `715d57b`, plan `30aa2484`.
- Run: launched 2026-10-14 00:21:23Z, terminal 02:48:57Z (result success), 25/25 cells valid; fetched 437/437 byte-verified
  (`tmp/otel-f-evidence/f1-fetch`); offline terminal replay pass 25/25 (`research/placement/test-f/terminal-replay-f1.json`, `28ce767`; the replay
  arguments were reconstructed from the CLI and F's gate working set, E's exact replay command is not recorded).
- Analysis v3.3 frozen before any F cell was read (`6efd378`, addendum `4be01dc`, `acdfe9b`); training readout `49d0265`, placement `198acc9`,
  placement pin `bf8e24c` (freeze step 2), scoring readout `044b210`, scorer output `a6a4dbb`, each committed unedited before reading. Post hoc lanes
  `f1768f5` after a recorded deviation in the post-hoc script (`6a42206`: placement-pin waiver; no computation changed).

## Verdicts (the preregistered rule)

| class | set | verdict |
|---|---|---|
| frauddetectionservice pause | `frontier (effort<=any, runtime<=any) @6/T_r` | **PASS** (g = 42.05 s, 2 of 2 test episodes improved) |
| accountingservice pause | same | **PASS** (g = 53.23 s, 2 of 2 improved) |

The frozen set has one sensor, `metric:kafka:kafka.consumer_group.lag` (the collector's `kafkametrics` receiver, F's change 3). T_r = 0.30 h (6 training
no-fault cells); 6/T_r = 20.0/h. The sensor was evaluated in 6 of 6 training folds; its `spike` rule alarmed once (honest bound 15.81/h), its `median`
and `run3` rules not (9.99/h); its price 15.81/h fits the budget.

## Test episodes (`otel-f.json`, `rates.25.episodes`; seconds after the pause command's pre-command stamp; "miss" = no counted fire in the 60 s hold)

| test episode | ledger alone | frozen set (lag) |
|---|---|---|
| accounting, block 4 | miss | 4.5 |
| accounting, block 5 | miss | 9.2 |
| fraud, block 4 | 38.1 | 4.8 |
| fraud, block 5 | miss | 9.3 |
| frontend, block 4 | 0.4 | 0.4 |
| frontend, block 5 | 0.3 | 0.3 |

The frontend pause (on-path control) is caught by the ledger first in both episodes (0.3-0.4 s); the lag sensor fires later, at 14.6 s (`run3`/`median`, down), so g = 0 for that class.

## Lane predictions (declared before launch; scored on the 4 off-path test episodes; `research/lanes/out-f-posthoc2`, post hoc script)

| id | prediction | result |
|---|---|---|
| F-L1 own silence | < 2.0 s in 4/4 (by-construction field) | **hit**: 0.84-1.52 s, 4/4 (`orders_receive` `absent`, BC-downstream-absent) |
| F-L2 coordinator | counted fire 42-47 s in 4/4; none in the 2 frontend episodes | **hit**: 43.3-44.0 s, 4/4; frontend none in either field |
| F-L3 lag | armed, fires before F-L2 in >= 3/4 | **hit**: 2 lag ids armed; 4.5-9.3 s, 4/4 |
| F-M metric arming | >= 1 non-flagd metric placeable | **hit**: 236 SDK + 44 spanmetrics-derived non-flagd ids placeable (E: 0); spanmetrics ids can arm by construction from traces |

The post-hoc zero-alarm pricing row gives the same @6/T_r set and g as decision 73 (the lag sensor is evaluated, so the fill price does not bind).

## What this does and does not say
- The summed consumer-group lag metric has a counted `spike` fire in 4/4 off-path test episodes at 4.5-9.3 s (instance), at a training false-alarm bound
  of 15.81/h, and the preregistered rule passes for both off-path classes. The fires count because `kafka` is on the declared affected path of both
  off-path classes. The 4.5 s vs 9.3 s split follows the 5 s scrape and is threshold-marginal (first post-onset summed sample about 14-16 against a
  threshold of about 14.4, reviewer's estimate).
- **The pass does not depend on the lag receiver.** The 3/T_r set is `metric:kafka:kafka.request.count` (the broker's JVM-agent metric, effort tier 0,
  9.99/h), which detects 6/6 test episodes (g 31.89) and is chosen in every effort tier; post hoc it would pass both classes (reviewer: g 42.38 / 53.28,
  2/2 each). The lag sensor has no declared effort/runtime tier (`tiersMissingForGroundSet`) and enters only the effort<=any cell, where CELF prefers it at
  6/T_r by training gain. What changed between E and F for this result is that broker metrics are exported every 5 s (change 1) and so arm.
- In E (60 s export, no lag receiver) the same rule failed both classes. E and F differ in the four declared changes (export interval, spanmetrics flush,
  lag receiver, second no-fault cell) plus rebuilt images (8 of 18 service image IDs differ: cart, checkout, currency, frontend, frontendproxy,
  productcatalog, recommendation, shipping; kafka, accounting, fraud and flagd identical; collector 0.108.1 in both), otelcol's start ordering
  (`depends_on` kafka healthy, `resource/kafka`), reader v3.3 instead of v3.2 (regression-checked on E's training blocks), seed, run order and day, and
  9 harness commits (`6a5c2a9..715d57b`, `git rev-list --count`; an earlier version of this note said 8). The design does not separate their effects.
- The lag metric is one id per (kafka, metric name), summed over both consumer groups (declared risk (e)), so it cannot tell which consumer stopped.
- n = 2 test episodes per class, one host, one rate, one SUT; the two no-fault cells per block are siblings in leave-one-cell-out calibration (fold
  false-alarm estimates optimistic). Fresh false alarms of the frozen set on F's 4 held-out no-fault cells: **not computed** (the reader's `--validation`
  path was not used; the reviewer's approximation finds no lag sample beyond the spike threshold in 4/4, `run3`/`median` down-fires unsettled).
- Cadence observed in cell `r25-b01-01` (reviewer): 5 s for ad, fraud, kafka, quote, checkout, productcatalog, recommendation, cart and accountingservice
  (declared unverified); flagd 2 s; frontend, payment, currency 60 s; spanmetrics 5 s; kafkametrics 5.0 s (4.86-5.14 s); flagd-ui sent no metrics;
  loadgenerator one batch (not observed).
- The scorer's generated `otel-f.md` is headed "Campaign E test scoring" and says "E's no-fault cells" (labels inherited from v3.2; not edited).
  Analysis ran under Python 3.13 (hosts run 3.9). The launcher logged "not under caffeinate" although the declared command used it.
- Reviews: one same-provider adversarial review (Fable subagent, 2026-10-14): every number supported, the order claim supported, four sentences
  refuted and replaced here (lag "detects both consumers", "adds nothing", the four-changes sentence, "no validated path"). A cross-provider check is
  owed (judge server not connected).

## Fresh false alarms on the held-out no-fault cells (POST HOC, `0790f24`, research/placement/test-f/fresh-fa/)
The frozen v3.3 reader's own `--validation` path on F's 4 held-out no-fault cells (blocks 4-5, 0.20 h), training calibration byte-equal to the frozen
readout's: the frozen @6/T_r sensor `kafka.consumer_group.lag` raised **0 alarms** in 0.20 h (95 % Poisson upper bound 14.98/h, the zero-alarm floor of
0.2 h; training bound 15.81/h); the @3/T_r sensor `kafka.request.count` raised **2** (two downward `spike` crossings, 0.027 below the line; 10.0/h, upper
bound 31.48/h, against its training bound 9.99/h). So the frozen set's training price is not contradicted on fresh no-fault time, while the tier-0 broker
metric that would also have passed does not keep its training price. A raw re-parse of two cells' `otelcol.log` matches the reader's counts. Not an
equivalence test; n = 4 cells, 0.2 h.
