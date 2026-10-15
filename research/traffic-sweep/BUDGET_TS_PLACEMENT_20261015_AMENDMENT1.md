# Budget amendment 1 to BUDGET_TS_PLACEMENT_20261015 (2501e86): the last set of runs on all three hosts (2026-10-15 ~07:35Z, committed alone)

Authority: user, 2026-10-15 ~07:30Z ("strengthen it via the last set of runs"). The R1 budget, gate and stop rules stay binding for R1 (srv5). Added, one campaign
per host, each analysed alone, each with the same pass-rule form as F (per off-path class and rate: frontier (effort<=any, runtime<=any) @6/T_r, g > 0 and
strict improvement on >= 2 of 2 test episodes; dash if < 2 valid test episodes or a member absent; decision 73 unchanged):

- **R2, fb14srv6, F with a new seed.** F's design byte for byte (lag receiver on, 25 cells, 25 req/s, split 1-3 / 4-5) in a separate worktree branched from
  `715d57b`, whose only change is the compiler's schedule seed (a new draw of block orders and onset strata). Analysed alone with the frozen v3.3 chain by
  F's rerun pattern (separate recorded pin), or, if the epoch id must change, by a reader admission frozen by digest before any cell is read. Answers the
  review point that the no-lag ablation's new seed is not an independent-seed replicate of F itself.
- **R3, fb14srv4, Hotel off-path placement test.** A fresh run of `hotel-offpath-v1` on the unchanged harness `9ad0b98` (plan `90b7b621…`), trained on
  blocks 1-3 and scored on 4-5 by the v3.6 layer (Hotel admission). The consul pause is the declared negative control (no coordinator, no queue), so the
  expected verdict is not PASS; a PASS would be reported as a possible false pass of the rule.

Gates (UTC, 2026-10-15): R2 launches only if its worktree tests are green, a DRY_RUN passed and its declaration is committed alone by 11:00Z; R3 only if its
v3.6 admission is frozen with a review GO, its declaration is committed alone and a DRY_RUN passed by 12:00Z. A missed gate means that run is not made,
recorded in a stop note. Relaunch: at most 1 per run, harness or infrastructure defects only, starting no later than 13:00Z. Analysis committed by 19:00Z,
paper text by 22:00Z; a run not analysed by then is mentioned in one sentence without numbers. No run blocks the submission (deadline 2026-10-16 11:59Z).
