# Traffic-sweep pilot on HotelReservation: declaration (FROZEN 2026-10-03, committed alone, before any cell)

Decisions by the user on 2026-10-03 (`research/READING_20261003.md` §2-§3, all pilot decisions approved; §2b items as
noted). Budget and stop rule: `research/traffic-sweep/BUDGET.md` (6a06818, committed alone before this file).
Draft history: `research/traffic-sweep/DECLARATION_DRAFT.md`. Decision briefs: `research/decisions-20261003/`.

## Binding
| item | value |
|---|---|
| harness | worktree `observability-placement-runtime-hotel-protocol`, branch `hotel-protocol-20261002`, commit `9ed8863` (epoch commit `b70f81e`) |
| epoch | `hotel-traffic-sweep-v1`, activated by the committed selector `modules/hotel-reservation/execution/study-epoch.json` |
| descriptor | `pipelines/campaigns/hotel-traffic-sweep-v1.json`, canonical sha256 `788ff28cc44248fec518fd04e3e0f91ab6d92229888a1412a52e50f9dd889dab` |
| plan | canonical sha256 `766063c5a0f0b90ab1aba1ada29b86e152e8ec1e7f7bd048d4c802c10b7bbc72`, 64 cells, identical under Python 3.9 `-I` and 3.13 |
| host | fb14srv4 only; wall budget 21,600 s |
| analysis | `research/detection-time/detection_time.py` as committed in `dbebcbb`, plus a sweep extension committed **before any result is looked at** (blind until then; the departure from "fixed before the first cell" is the user's decision, row 13) |

## Question
Whether, and at which request rate, sensors that read a service's own state detect a fault sooner than the request ledger
(the root), and what that does to placement. The guarantee CELF carries covers time saved (Leskovec et al. 2007), not mean
delay itself, which is hard to approximate (Heavey et al., AAAI 2022). The question here is empirical: does selecting
sensors on time pick different sensors than selecting on detection probability, how far is CELF from the enumerated
optimum, and how do both move with rate (`research/decisions-20261003/B_OBJECTIVE_MEASUREMENT.md` §1.3). Scope of every
number: instance (one SUT, one host).

## Design (approved values)
- Workload: `GET /hotels`, open loop, rates **10, 1, 0.2, 0.05 /s**; concurrency 16; per-request timeout 1 s; measurement
  180 s; offered = rate × 180 (1800, 180, 36, 9).
- Warm-up: **30 s at 10/s for every rate**, untokenised.
- Fault: onset at 60 s **+ a stratified offset**: the four episodes of each (regime, rate) pair take the four quarters of
  one inter-arrival in a seeded order, uniform inside the quarter; hold **60 s**.
- Regimes: no-fault calibration (pseudo window at the same seeded onset), **search-pause**, **profile-cpu-throttle**
  (`--cpus 0.1`), **rate-net-delay 100 ms**.
- Posture: `full` only; placements are evaluated by restriction of `full` cells (an approximation; a sensor can behave
  differently when other sensors are off, D3).
- Episodes: 4 per (regime, rate); 4 blocks, each holding every pair once, order shuffled with seed 20261003, except that
  **block 1 starts with `search-pause-effect-r10-b01-full-a01`** (lead cell; capture checked while the campaign runs).
- Netem: the existing `sudo -n nsenter … tc` on srv4 (**deviation** from round-4 decision 6, sidecar netem, which is not
  built yet; recorded).
- Sampling: cgroup sampler 5 s, docker stats as before; every time is reported with its channel's resolution.
- Logs captured with `docker compose logs --timestamps`; traces of all services retained.

## Outcomes
1. **Primary: time to detection** per sensor and for the ledger: first catch after onset; a miss is charged at the hold
   end; averaged over episodes, never over detected episodes only.
2. **Secondary: impact before detection**: failed requests (started before the first catch) per episode; requests counted
   by scheduled time.
3. Exploratory (collected, not tested): D3 probabilistic detection, D4 robustness across rates (max-min by exact
   enumeration), D5 labels per catch.

## Predictions (testable sets and tolerances declared now)
- **P1 (positive control, search-pause)**: per episode, the ledger's time to detection equals the wait to the first
  scheduled request at or after onset plus the 1 s client timeout, within ±0.5 s. A deviation flags a harness or onset
  defect, not a finding.
- **P2 (search-pause, `failed` rule)**: in ≥ 3 of 4 episodes per rate, failed requests started before the ledger's first
  catch ≤ 1 + rate × 1 s + 2 (D2's model, slope form; predicted ≈ 11, 2, 1.2, 1.05). Per-episode counts are reported.
- **P3 (request-independent families: docker CPU M, cgroup S)**: a sensor's time to detection at 0.05/s ≤ its time at
  10/s + one sampling cadence (M ~3 s, S 5 s). Testable set (from the 10/s evidence): search-pause S outside the target;
  cpu-throttle S of the target (reported separately). Cells where no such family detects at 10/s are listed as untestable,
  not as failures.
- **P4 (decision criterion)**: per fault class and rate, a sensor beats the ledger if its time is lower in ≥ 3 of 4
  paired episodes. **P4a**: sensors outside the target, primary without by-construction catches; **P4b**: the target's own
  sensors. Reported: the highest rate where the criterion holds, or "none in {10, 1, 0.2, 0.05}".

## Analysis definitions
- **Probe windows excluded from sensor scoring** (user, §2b): the fault adapter's readiness probes are SUT requests inside
  the measurement. Their windows come from the receipt (`probes`: pre and during probes, exact start/end) and from
  `[revert, readyAtMonotonic]` (recovery polling). Every sensor sample or record inside a probe window is not scored; a
  catch that would fall inside is moved to the window end. The ledger holds no probe requests and is unaffected; spans of
  probe requests carry no token and are excluded by token.
- Ledger rule: per-request spread (decision round 4, item 3), scored on the same K × floor grid as the sensors.
- Stamps: a whole-second log stamp is timed at s + 1 s (conservative end); with `--timestamps` the Docker receive time is
  used.
- Selection vs evaluation: leave-one-episode-out (sensors chosen on three episodes, scored on the fourth).
- By-construction: flagged by content (the record names the callee), incl. BC-caller-log; claims rest on numbers without
  BC catches; BC filters candidate sensors, never the ledger baseline.
- False alarms: per rate, on no-fault windows at the same onset phase; placement-level false alarms are reported beside the
  score, not inside it.
- G2 own/outside: the target's own sensors are a separate column, never in a placement's catch set for P4a.

## Gates and declared limits
- Blocking per cell (shared module, vendored): **F1** fault truth (manifested, reverted, onset and hold bounded by the
  scheduled command), **G1** traffic (scheduled opportunities, plus ≥ 1 request started in the window), **G2** healthy
  before onset (successes ≥ 0.5 × rate × seconds and failure share ≤ 5 %), **G4** bookkeeping (offered == plan, ledger
  complete). At 0.05/s there are ~3 requests before onset, so one pre-onset failure fails G2 (stop and ask).
- Not evaluated by the shared module (the harness writes none of their inputs; its own checks still run): **P0**
  provenance, **R1** readiness, **R2** base state. G4's in-cell check covers the ledger only. **R2.recovery** is `—` in every
  fault cell: only 40-60 s are observed after the hold, shorter than its 60 s window. Fresh project and `down -v` per cell
  remain the base-state control.
- The runtime stops on the first invalid cell (`BUDGET.md` rule 3).

## Monitoring (not evidence)
Campaign progress and per-cell summaries are logged at a high level to Weights & Biases (user, 2026-10-03). The evidence
of record stays the fetched campaign directory; wandb holds no number that is not also in the evidence.
