# OTel campaign F, replication 1, relaunch 1 (attempt 3): declaration (2026-10-14)

**Status: committed alone, before the launch below.** `DECLARATION_F_OTEL_REP1.md` (`d0ef902`) and `DECLARATION_F_OTEL.md` (`8845721`) stay binding for
everything not changed here (analysis on the replicate alone with a separate recorded pin, `research/placement/test-f-rep1/RUN_ORDER.md` and
`score_rep.py`, `c08b2d5`). Budgets `BUDGET_REPLICATION_20261014.md` (amendment 1 `208f076`) and `BUDGET_OVERNIGHT_20261014.md` (`cf50078`): at most 1
relaunch, harness or infrastructure defects only (**this is it**). Predictions committed before launch: `PREDICTIONS_OVERNIGHT_20261014.md` (`8b89d43`,
ids FR1-*), which apply to this relaunch. Scope: instance (fb14srv6).
## Why
Attempt 2 (launched 14:28:49Z) stopped after 13 cells (12 valid) at 15:45:21Z: cell 13 (`effect/fraud-pause/r25-b03-13-full`) invalid with
`RuntimeFailure: command docker failed (1) … dependency failed to start: container …-opensearch-1 is unhealthy` at stack start, before any fault.
**Classification:** an infrastructure flake (the telemetry backend did not become healthy), not a harness defect. Attempt 2's host paths were moved to
`archive-f-attempt2-20261014/` on srv6 (no deletion); its evidence is being re-fetched from there to `tmp/otel-f-evidence/f2-fetch2` (a first fetch,
`f2-fetch`, was interrupted before verification and is kept, unverified, unused). Attempt 2's 12 valid cells are preserved and not read.
## What differs
Only the attempt: plan `56bdaa62c41555957004a6264026282afad16272b92abe5377b51a5e7f345c94` (attempt 3, 25 cells), harness `715d57b` unchanged.
DRY_RUN `f3dry` passed 2026-10-14 23:18:35Z (0 guarded paths, 0 containers, 226 GB free). Fetch case `otelF3` (`tmp/otel-f-evidence/f3-fetch`).
The run order of `test-f-rep1/RUN_ORDER.md` applies with the fetch dir `f3-fetch` and output names `-f3-` in place of `-f2-`.
## Launch
```
LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=3 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_offpath_f.py EXPECTED_PLAN=56bdaa62c41555957004a6264026282afad16272b92abe5377b51a5e7f345c94 \
  RUN_COUNT=25 CAMPAIGN=otel-offpath-f-v1 LOG_PREFIX=otel-offpath-f-v1 \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh f3 715d57b5f06ea32d47466acccae927da8e350a2c > scratchpad/gate-drivers/otel-offpath-f-v1-f3.out 2>&1 &
```
