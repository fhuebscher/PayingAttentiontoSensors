# Traffic-sweep pilot on HotelReservation: declaration DRAFT (2026-10-02; not frozen, nothing run)

Every ▶ value is a proposal for the user to set on 2026-10-03, hands-on. The declaration is frozen (committed alone, before
any cell) only after that. Protocol: `research/PROTOCOL_DRAFT_20261002.md` decision 14; literature premise
`research/literature-20261002/DIMENSIONS.md`.

## Question and gap
Placement is optimised with CELF on a submodular surrogate. Detection probability is submodular, detection *time* is not
(Heavey et al., AAAI 2022, per DIMENSIONS.md), so the (1 − 1/e) guarantee covers the surrogate only; we found no paper that
uses time to detection as a placement objective for microservice telemetry ("none found", not "none exists"). This pilot
measures the quantity the surrogate stands in for, on one SUT, across request rates.

## Predictions (from DIMENSIONS.md §6, the agent's reasoning, untested)
- **P1** The ledger's time to detection grows roughly as 1/rate on the faulted path.
- **P2** The number of bad (failed or slowed) requests before the ledger's first catch stays roughly constant across rates.
- **P3** The number of bad requests before an own-state sensor's first catch grows with rate.
- **P4** For each fault class, either some own-state sensor's time to detection drops below the ledger's at some rate in the
  sweep (report the rate), or none does (report that). Both outcomes are results.
Risk named in advance: at low rate a paused or throttled service is idle anyway, so its own CPU sensors may lose the contrast
they have at 10/s; P3/P4 can fail for that reason, and that is part of what the pilot measures.

## Design (▶ = proposal)
- SUT: HotelReservation on fb14srv4 (stable; per-request ledger; pause, throttle and netem already implemented).
- ▶ Rates: 10, 1, 0.2, 0.05 requests/s on `/hotels` (inter-arrival 0.1 s, 1 s, 5 s, 20 s; the last two are at or above the
  cgroup sampler's 5 s and docker stats' ~3 s).
- ▶ Faults: search-pause (stop, on path), profile-cpu-throttle (degradation), rate-net-delay 100 ms (degradation, on path),
  plus no-fault cells for calibration.
- ▶ Cell timing: warm-up 30 s at the cell's rate; measurement 180 s; onset 60 s; hold 60 s (≥ 3 inter-arrivals at 0.05/s);
  60 s recovery observed.
- ▶ Posture: `full` (every channel collected; placements evaluated by restriction with the posture-leak check). The ledger is
  in every placement (decision 1).
- ▶ Episodes: 4 per (fault, rate) and 4 no-fault per rate: 4 × 4 × 4 = 64 cells, randomised order within blocks, seed
  recorded. Estimate ~5 min per cell ⇒ ~5.5 h (`?` until the dry run).
- Netem: sidecar container in the target's network namespace (decision round 4, item 6) or the existing `sudo -n nsenter` on
  srv4; ▶ which one for this pilot.

## Outcomes, per episode (primary first)
1. **Time to detection** per sensor and for the ledger: first catch after onset; a miss is charged at the window end (hold
   end); averaged over episodes (never over detected episodes only). Each sensor's sampling resolution reported beside it.
2. Optional, collected now: bad requests before detection; detection probability per (sensor, rate) over the K × floor grid;
   labels per catch (symptom kind, service, route); by-construction flags incl. BC-caller-log.
Analysis code fixed before the first cell: `research/detection-time/` (retained-evidence version) extended to the sweep.

## Gates and stop rule
Shared gates (`src/obsplacement/protocol_gates.py`): P0, R1, F1, G1 counting actual starts, G2, G4 from the plan (no
literals). Stop and ask the user on the first invalid cell. ▶ Kill date: not terminal by 2026-10-05 12:00Z ⇒ stop.

## Harness change needed (Hotel protocol worktree, branch hotel-protocol-20261002; for review before any dry run)
Rate, hold and offered count become per-cell plan values: today `candidate_search.py:155` rejects any rate ≠ 10.0, `:169`
any offered ≠ 1200, and `candidate_terminal.py:498-500,750` check 1200 literally; `MINIMUM_PHASE_STARTS = 100` and the
descriptor/plan digests are fixed for 10/s. A new epoch name, not an edit of the frozen one.
