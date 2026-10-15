# Budget amendment 2 to BUDGET_TS_PLACEMENT_20261015 (2501e86): R4, a long no-fault price check of F's frozen sensors (2026-10-15 ~12:45Z, committed alone)

Authority: user, 2026-10-15 ~12:40Z ("one more run through ... Long no-fault price check"). Not part of the original set of runs; reported as a validation of
prices, post hoc to every placement it checks. Scope of any result: instance (OTel Demo, fb14srv6).
## What
F's design (`DECLARATION_F_OTEL.md`, harness `715d57b`, lag receiver on, 25 req/s, 5 s export) with fault-free cells only, to price on fresh time the sets that
F's three runs and the ablation froze: `metric:kafka:kafka.consumer_group.lag` (F), `metric:kafka:kafka.purgatory.size` (F's rerun),
`metric:kafka:kafka.request.count` (the ablation; F's @3/T_r set), the R2 set once frozen, and the ledger. Each sensor is scored with its frozen training
calibration by the reader's `--validation` path (as `research/placement/test-f/fresh-fa/`), never refitted; the count k and its 95 % Poisson upper bound per
hour are reported against the sensor's training price. Preferred shape: 25 no-fault cells (about 1.25 h of fault-free measurement; zero-alarm floor about
2.4/h) in a separate worktree branched from `715d57b`, whose only change is the regime list. Fallback if the preferred shape trips guards that cannot be fixed
and reviewed by 14:30Z: F's unchanged plan at a fresh attempt number (no run ID shared with F's attempts 1-3 or R2's attempt 4), reading all 10 of its no-fault
cells (about 0.5 h; floor about 6/h). The fault cells of the fallback are not read.
## Gates and stop
Worktree tests green, one same-provider review GO, declaration with predictions committed alone, DRY_RUN passed on srv6 (R2's fetch verified first), by
15:00Z; else no run, recorded in a stop note. At most 1 relaunch (harness or infrastructure only), starting by 16:00Z. Analysis committed by 21:00Z; paper text
by 23:00Z, else one sentence without numbers. No run blocks the submission (deadline 2026-10-16 11:59Z).
