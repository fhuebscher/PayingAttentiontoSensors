# Hotel `selected`: result (sel1, 2026-09-29)

Scope of every number: **instance** (HotelReservation, fb14srv4, one campaign, n = 4 blocks per regime). Not pooled with lmt2 or
Hotel #1-#8. Declaration and predictions: `DECLARATION.md` (f120805), committed before any code or cell.

## Run

- Campaign `hotel-v1-20260929t072735z-065bb893`, harness `selected-20260929` e4fd4c7, plan `189604cc...`, 80 cells.
  Launcher started 07:26Z by Claude under the user's instruction of 2026-09-29 ("run the experiments yourself"); the SETUP-CAMPAIGN
  sentence was typed by Claude and GATE-RUN was harness-derived (`scratchpad/gate-drivers/hotel-sel1-launch.log`). Terminal 11:40Z:
  80/80 valid, `candidateCampaignValid: true`; a post-terminal `docker ps -aq` returned 0 (session output, not in the retained log).
- Fault receipts 64/64 `successful`. Fetched `fetch_overnight.sh hotelsel1`: 4272/4272 files OK (`tmp/hotelsel1-evidence`, not in git).
- Posture check (host, cost b01): `selected` posture proof traces `["frontend"]`, the only ratio-1 service; 4,800 spans, all frontend.
  Cost regime, all blocks: `selected` 19,200 spans, `full` 72,000 (26.7 %).
- Analysis: `analyse.py` (bf67e10, which imports the LMT pilot's `cost_steps.py`/`lmt_detect.py` unchanged; `git diff bf67e10 HEAD`
  on all three is empty), run once. Output `out.sel1.json`.

## Predictions

| # | reads | evidence |
|---|---|---|
| P1 `selected` catches what its derivation says | **yes** | `Tsel` 4/4 in search-pause, reservation-pause, net-delay |
| P2 `selected` loses nothing `full` catches | **yes** | `Tsel` = `T` in every regime: 4/4, 4/4, 4/4, and cpu-throttle 0/4 = 0/4 |
| P3 `selected` costs less than `full` | **yes** | `selected->full` total CPU-s > 0 in 4/4 blocks |
| P4 `selected` costs more than no tracing | **yes** | `metrics->selected` total CPU-s > 0 in 4/4 blocks |

P2 at n = 4 is not an equivalence test; it says no regime's catch count dropped in these four blocks.

## Cost (no-fault regime, 4 complete blocks, 120 s window): mean [min, max], positive of 4

| step | total CPU-s | app CPU-s | daemon CPU-s | p50 ms |
|---|---|---|---|---|
| none -> metrics | +3.31 [3.26, 3.37] 4/4 | -0.07 [-0.13, -0.01] 0/4 | +3.37 [3.34, 3.40] 4/4 | +0.08 [0.03, 0.13] 4/4 |
| metrics -> selected | +4.49 [4.39, 4.62] 4/4 | +3.40 [3.35, 3.43] 4/4 | +1.09 [0.99, 1.18] 4/4 | +0.52 [0.47, 0.56] 4/4 |
| selected -> full | +8.28 [8.12, 8.42] 4/4 | +5.35 [5.29, 5.44] 4/4 | +2.93 [2.84, 3.02] 4/4 | +0.90 [0.87, 0.94] 4/4 |
| metrics -> full | +12.77 [12.59, 12.87] 4/4 | +8.76 [8.64, 8.84] 4/4 | +4.02 [3.95, 4.10] 4/4 | +1.42 [1.40, 1.45] 4/4 |

Derived (ratios of the block means above, not a new measurement): `selected` pays 35 % of tracing's total CPU step
(4.493 / 12.774) and 37 % of its p50 step (0.520 / 1.425), for 26.7 % of its spans. Carried contrast from lmt2, `metrics->full`:
positive in 4/4 blocks again (lmt2: +12.69 CPU-s, +1.38 ms). `none->metrics` here moves the log level and the sampler together;
its app delta is negative in 4/4 blocks (lmt2's sampler step alone: sign undetermined) and its CPU sits in dockerd/containerd,
where lmt2's sampler step also sat.
Same cost coverage as lmt2: ten Go services plus host-wide dockerd/containerd; jaeger, consul, data stores, load generator not costed.

## Detection (caught / n; non-target sensors, G3 per family on its own no-fault windows)

| regime (target) | L (n 12) | M (n 12) | Tsel (n 4) | T (n 4) | S (n 16) |
|---|---|---|---|---|---|
| search-pause (search) | 1 | 11 | 4 | 4 | 1 |
| reservation-pause (reservation) | 12 | 12 | 4 | 4 | 0 |
| cpu-throttle (profile) | 0 | 0 | 0 | 0 | 1 |
| net-delay (rate) | 0 | 2 | 4 | 4 | 2 |

G3 inadmissible: M frontend/rate/reservation cpu; S sys_memory of 6 services. "No admissible firing in a no-fault window" holds by
construction (one firing exceeds 5 % at 4-16 windows), as in lmt2.

## What this does and does not show (after the Fable review, 2026-09-29)

- A preregistered out-of-sample contrast of a hand-derived one-service placement: `selected` was read off lmt2's post-hoc span table
  at service granularity (no objective or algorithm ran), and measured on a fresh campaign with the same host, SUT commit, workload
  and fault parameters. Every prediction held. It is not an iteration of an adaptive loop: nothing was re-placed.
- **The detection half holds by construction.** All 12 `Tsel` and all 12 `T` catches are reproduced by the workload's own request
  ledger in the `none` posture (no tracer): `ledger_check.py` (post hoc, output `ledger_check.sel1.json`) shows the pauses in 4/4
  cells per posture (138-140 failed in-window requests, median ~1002 ms), the delay in 4/4 (0 failed, median ~210 ms vs ~10 ms
  before), the throttle in 0/4, identically in none, metrics, selected and full.
  `full` is caught by the same frontend sensors. The frontend is the request-path root and these three faults change what the root
  sees, so P1/P2 cannot tell "the derivation works" from "the root sees failed requests". The four faults do not discriminate
  placements; a fault catalogue that does needs faults the root does not see.
- The cost half stands: tracing the frontend alone costs 35 % of tracing's CPU step and 37 % of its p50 step. Jaeger is not costed,
  and it receives 26.7 % vs 100 % of spans, so the ratio excludes a component that scales with the contrast. `selected` is
  tracer-disabled on nine services, not source-off (their nethttp/otgrpc wrappers stay installed).
- `full` switches all ten tracers on, but only six services emit spans at this workload (0 from attractions, recommendation, review,
  user in 20/20 full cells).
- Not replicated here: the pilot's C1 (frontend availability template 12/12 reservation-pause, 0/12 search-pause) reads 12/12 and
  **1/12** in sel1.
- n = 4 blocks; no rate, interval or equivalence claim. The cost ratios are of block means.

## Ledger

- `runtime-policy.json` still lists `placement-lattice-nesting` as a prohibited claim with a rationale that `selected` is unsupported;
  this epoch ran `selected`. The ladder is nested by traced-service set (40/40 posture proofs); the policy text is stale. Paper wording:
  "nested by traced-service set", never "lattice".
