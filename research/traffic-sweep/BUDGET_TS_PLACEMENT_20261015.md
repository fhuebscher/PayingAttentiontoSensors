# TeaStore off-path placement test (R1): budget and stop rule (2026-10-15, committed alone, before any of the work)

Authority: user, 2026-10-15 ~07:00Z ("R1, gated"), after a cross-provider review of the BenchSOC draft (`research/protocol/REVIEW_JUDGE_20261015.md`,
`eval_845c2629…`, `eval_c64868fa…`). Scope of any result: instance (TeaStore at 34b37f7, fb14srv5).

## What
One fresh run of the TeaStore off-path epoch `teastore-offpath-v1` on the unchanged barrier-fixed harness (`04254228`, plan `5a8e385e…`, 30 cells, 5 blocks
x 2 rates (10, 1 req/s) x {no-fault, recommender pause, auth freeze}), analysed **alone**, like F's rerun: the frozen chain trains on blocks 1-3 and is
scored on blocks 4-5 under F's pass rule mapped to this epoch (per off-path class and rate: the frontier (effort<=any, runtime<=any) set @6/T_r passes
iff g > 0 and it strictly improves on the ledger in >= 2 of 2 test episodes; dash if fewer than 2 valid test episodes or a member is absent; decision 73
unchanged). The v3.3 chain admits this epoch for lanes only, so a v3.6 admission layer (reader, CELF and scorer wrappers, v3.5's pattern: one rebinding,
no rule changed) is needed. The two finished TeaStore off-path runs were read; they are used only for a dry run of the wiring, which is post hoc and
carries no verdict.

## Budget (UTC, 2026-10-15)
- **Gate, 10:30Z:** v3.6 built with its tests green, a dry scoring of replication 2 (`rep2-fetch`, train 1-3 / test 4-5) runs end to end and returns
  a verdict object (any verdict), v3.6 frozen by digest in a freeze record, one same-provider review GO, declaration and predictions committed alone,
  DRY_RUN passed on srv5. Any item missing at 10:30Z: **no run** (R4), recorded in a stop note; the time goes to the artifact and the text.
- **Run:** at most 1 relaunch, harness or infrastructure defects only, and only if it can start by 12:30Z. Stop as usual on the first invalid cell for a
  decision; a launcher stop on >= 3 blocked with 0 valid. Not terminal by 16:00Z: stopped, reported as not analysed.
- **Analysis:** fetch byte-verified, offline replay, training readout, placement, placement pin (two-step freeze), scoring readout, scorer, each committed
  unedited before reading, by 18:00Z; else the paper says the run is not analysed.
- **Paper:** the verdict, whatever it is, enters the paper by 21:00Z with the same-provider and cross-provider review of the new paragraph; else a
  one-sentence mention without numbers.
