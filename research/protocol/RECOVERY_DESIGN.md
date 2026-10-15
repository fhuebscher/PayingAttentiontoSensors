# Recovery and carry-over: what others do, what we do, a middle ground (2026-10-03; unreviewed)

User request 2026-10-03: put what we do and why beside recent papers, find a middle ground, track the sources. Sources are
`research/literature-20261002/SOURCES.md` (S1-S6); every number below comes from a verbatim quote there. Scope: method.
The traffic-sweep pilot is frozen (`research/traffic-sweep/DECLARATION.md`); nothing here changes it.

## 1. Comparison

| | Eadro, ICSE 2023 (S1) | Fault-propagation benchmark, 2025 (S2) | RCAEval, WWW 2025 (S3) | AnoMod, MSR 2026 (S4) | Chaos engineering (S5) | **Ours: traffic-sweep pilot** |
|---|---|---|---|---|---|---|
| request rate | 0.2-0.5 /s (TT), 2-3 /s (SN), uniform | not read | 10-200 /s, random | EvoMaster test suites | — | 10, 1, 0.2, 0.05 /s, open loop, a factor |
| before the fault | 7 h (TT) / 1.2 h (SN) fault-free, once | 4 min warm-up + 4 min normal, per case | "run normally" (duration not stated in §3.3) | wait until "fully initialized and stable" | steady state defined first | 30 s warm-up at 10/s + 60 s pre-onset (+ offset) |
| fault duration | 10 min (TT), 2 min (SN) | 4 min | not stated in §3.3 | the whole workload | experiment-specific | 60 s |
| after the fault | 2 min (TT) / 30 s (SN) gap, then next fault | none: redeploy | not stated | none: terminated "upon workload completion" | compare steady state, experiment vs control | 40-60 s of traffic, then `down -v` |
| isolation between cases | none (same deployment) | full redeploy | not stated | fresh redeploy per case | — | fresh project + `down -v` per cell |
| recovery checked? | no, assumed by the gap | no | no | no | **yes**: steady state must hold | partly: route answers HTTP 200 within 120 s (F1); return to pre-fault latency/error level `—` (declared limit) |
| carry-over / multi-fault | possible (no redeploy), not measured | excluded by redeploy | — | excluded by redeploy | — | excluded by redeploy; recorded, never scored (protocol §7) |

## 2. Why we do what we do now
- **Fresh deployment per cell**: each cell is one episode of one fault at one rate, scored against its own pre-window.
  Carry-over would add a second unknown (the previous cell's residue) to a detection-time measurement. Two of the four
  benchmarks (S2, S4) make the same choice.
- **Short hold (60 s) and short post-window (40-60 s)**: time to detection is the primary outcome, and the slowest
  catch we expect is bounded by the hold. 64 cells fit the 6 h window only at ~4.5 min per cell.
- **What this misses** (user, round 6): "route answers 200" is only part of recovery, because not every failure shows as
  a status code; and redeploying hides carry-over and multi-failure, which real systems do not get to skip.

## 3. Middle ground (proposal, after the pilot)
Between "redeploy and never look at recovery" (S2, S4) and "fixed gap, recovery assumed" (S1):

1. **Keep the redeployed cell as the primary arm.** Isolation stays the default for every placement claim.
2. **Measure recovery instead of assuming it** (S5's steady-state check): extend measurement 180 → 210 s so every fault
   cell has ≥ 60 s after the hold, and compare that window with the cell's pre-fault window *and* with the no-fault cell
   at the same rate and phase (the control group). Steady-state outputs: error share, p50/p95 latency of the ledger.
   New outcome: **time to recover** (first time after revert the output re-enters the pre-fault band and stays), beside
   time to detect. Cost: +30 s per cell, about +32 min per 64 cells (estimate).
3. **Carry-over arm (ablation)**: the same faults without redeploy between cells, the next fault starting after a fixed gap
   (S1-style), with the order of predecessors randomised by the existing seeded block shuffle so the effect of the
   previous fault can be estimated. The steady-state check from (2) labels each start as clean or polluted; nothing is
   discarded. Answers: does residue change detection time, false alarms, or recovery time, and is a check-then-start
   gate (start only when steady state holds) enough to mitigate it.
4. **Multi-fault arm (later)**: overlapping faults on two services, only after (3) shows what residue alone does.

Order: (2) needs one parameter change and a new analysis column; (3) needs a "no redeploy" switch in the harness; (4) needs
a second fault adapter in the same window. Each is a new epoch with its own declaration.

## 4. Open
- S6 (Oxn) is not read; it is the related work most likely to have a recovery or steady-state step for observability
  experiments.
- Whether the post-window compares against the pre-window (within cell) or the same-phase no-fault cell (control) as the
  primary is a preregistration decision.
