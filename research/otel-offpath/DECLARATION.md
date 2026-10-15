# OTel Demo off-path fault (direction c): declaration, predictions, stop rule (2026-10-01 ~13:30Z, before any code or cell)

Authority: user 2026-10-01 (direction (c); "happy for improving base postures and loosening stop rules as suggested in c,d"; overnight:
"Yes, my defaults"). This is the **fifth override** of `research/OTEL_RUN2_STOPPING_RULE.md`, made by the user and recorded here.
OTel Demo is a training system. **No launch until the user approves the built harness and this declaration.**
Question: does a fault the entry point cannot see let placements rank by what they see, without a threshold artefact
(`research/visibility-map/MAP.md`: no such row exists in any population so far)?

## Why this fault (code reading, upstream 2d4661e; method, unmeasured)
checkout publishes the order to Kafka and waits only for the broker's acknowledgement (`src/checkoutservice/main.go:492-545`);
frauddetectionservice and accountingservice consume the topic asynchronously. A **broker** fault is entry-visible by that wait;
a **consumer** pause is not: the order completes before consumption.

## Design (engineering defaults, recorded)
- Successor of `otel-postures-20260930` 64ba7c9; new epoch `otel-demo-offpath-v1`, fb14srv6, never pooled.
- Workload: the harness's own offered-request producer, switched from `/api/recommendations` to a checkout journey (add to cart, then
  place order) with W3C trace context; one ledger row per offered journey (start, end, status), as the Hotel ledger.
- Faults (15 s, onset 45 s, as Hotel): `fraud-pause` = `docker pause` frauddetectionservice (target); `frontend-pause` control (as v3).
- Postures (instrumentation only; every service runs): `none`; `selected` = the synchronous order path (frontendproxy, frontend, cart,
  checkout, currency, payment, productcatalog, shipping, quote, email as traversed); `async` = `selected` + kafka + frauddetection +
  accounting; `full` = all 19. The exact sets are derived from the traced `full` paths of a no-fault cell, written into the descriptor
  before the first fault cell.
- Regimes: no-fault (calibration windows and cost), fraud-pause, frontend-pause; 3 blocks x 4 postures (3x4 Latin rectangle) = 36 cells.
- Detection adapter (new): the collector's debug-exporter log -> per-service span / metric / log symbol bags in the Hotel symptom
  alphabet (`research/s4-conjunction/symptoms.py` rules, unchanged); G2 (faulted service's sensors excluded) and G3 (5 % no-fault rule) as in the paper.

## Predictions (read yes / no / `—`; n = 3 episodes per posture)
- K1 ledger blind: the untraced ledger rule (`research/hotel-selected/ledger_check.py`'s rule) shows fraud-pause in <= 1 of 3 cells per posture.
- K2 `selected` blind: no sensor of `selected` outside the target catches fraud-pause in >= 2 of 3.
- K3 `async` sees it outside the target: a sensor of `async` outside frauddetection (kafka broker or accounting) catches >= 2 of 3.
  Both outcomes are reported; "no" is itself the finding that the fault is visible only at its own service.
- K4 by construction (reported, not a result): the target's own spans/metrics change in >= 2 of 3 under `async` and `full`.
- Control C1: frontend-pause is ledger-visible in 3 of 3 per posture.
Scope: instance, one host, n = 3. No magnitude claim; OTel stays a training system.

## Stop rule (dates Z)
- 2026-10-06 18:00: workload, postures, adapter built and the adapter replays v3r1's frontend-pause cells as ledger-visible 12/12; else (c) is dropped.
- 2026-10-08 18:00: first cells valid on srv6; a second distinct smoke failure kills (c).
- 2026-10-11 12:00: terminal-valid, else not in the ASOCA paper. One relaunch after a fix, no second.
- Paper text only after a Fable review; a refuted paper sentence keeps OTel out.

## Erratum 1 (2026-10-01 ~13:55Z, before any (c) cell; the rules above are unchanged)
After `research/hypotheses-20261001/H4_threshold_ranking.md` (cd0403a: the int1 ranking held in 4 of 9 (K, floor) settings), the
adapter additionally reports, beside the frozen reading (K=4, floor 1 ms) and without changing K1-K4: K1-K4 and C1 over K in {3,4,5} x
floor in {0.5,1,2} ms; the symbol kind behind each catch (error / missing / latency / metric / log); the maximum in-window shift/threshold
ratio of `selected`'s sensors outside the target per fraud-pause cell; and the G3 cliff (3 no-fault windows: one firing is inadmissible).
A K2 "blind" that flips within the grid is reported as threshold-dependent, not as blindness.

## Erratum 2 (2026-10-01 ~14:30Z, before any (c) cell): findings, design decision deferred to the user
From `research/hypotheses-20261001/H1_root_invisible_rank.md` and `H5_async_offpath.md`:
- The "Why this fault" premise is wrong: checkout's producer uses `RequiredAcks = sarama.NoResponse` (`producer.go:24`), so checkout does
  not wait for a broker acknowledgement. A broker fault may also be root-invisible.
- K1 and K2 are by construction (a consumer pause cannot reach the order response; `selected` has no consumer sensor). K3 via
  accountingservice is "no" by construction (separate consumer group). K3's only empirical channel is broker-side Kafka metrics or a
  missing-export symbol, both at the collector's 60 s metric cadence, which a 15 s pause rarely spans; the consumer session timeout
  (client default 45 s, unverified at the pin) exceeds the hold, so no rebalance registers.
- Candidate redesigns, **for the user to choose before any cell** (they change fault parameters or what the harness emits):
  (a) hold >= 60 s and > the session timeout; (b) a shorter metric export interval (harness emission change); (c) the
  `kafkaQueueProblems` flag (sustained lag, consumer alive) instead of or beside the pause; (d) an `emailservice` stop regime, whose
  error checkout logs and swallows, as the one design that can falsify H5 rather than confirm K1 by construction.
The builder parameterises hold, fault scenario and export interval; the declared defaults stay until the user decides.
