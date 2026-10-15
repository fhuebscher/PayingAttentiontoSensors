# OTel campaign F, replication 1 (attempt 2): declaration (2026-10-14)

**Status: committed alone, before the launch below.** `DECLARATION_F_OTEL.md` (`8845721`) stays binding for everything not changed here (design, pass
rule, decision 73, lane predictions F-L1..F-M and their thresholds, evidence handling). Budget `BUDGET_REPLICATION_20261014.md` (`0b70303`, amendment 1
`208f076`). Scope: instance (fb14srv6).
- Same epoch `otel-offpath-f-v1`, harness `715d57b5f06ea32d47466acccae927da8e350a2c` (clean), descriptor `6164052d…`; **attempt 2**, plan
  `373a1ece8c5ff5bca99ecb25491399d0379bd9df044d8a94f6bf577125963a6f` (25 cells; only the attempt number, hence the run IDs, differ from F). F attempt 1's
  host paths were archived (moved) before this launch (budget amendment 1). DRY_RUN `f2dry2` passed 2026-10-14 14:28:23Z (all guards, 0 paths, 228 GB).
- **Analysis, declared before launch:** the frozen v3.3 chain exactly as for F (`FREEZE_V33_20261014.md` run order), on this replicate alone: training
  readout `--blocks 1 2 3 --split research/protocol/split_f_otel.json` on its fetch only; `celf_v3_3.py` placement on that readout; the placement digest
  recorded in a freeze-record entry and passed to the scorer by a pin override recorded in that entry (F's pin `PINNED_PLACEMENTS["otel"]` stays F's;
  the scorer run for this replicate uses a recorded, separate pin); scoring readout `--test-blocks 4 5`; `score_test_v3_3.py`; `posthoc_lanes_v33.py otel`;
  the fresh held-out false-alarm check of `research/placement/test-f/fresh-fa/` on its 4 held-out no-fault cells (post hoc). Each output committed
  unedited before reading. F's verdicts, placement and readouts are not changed and not pooled with this replicate; the result note reports both.
- Fetch: case `otelF2` in `fetch_overnight.sh` (`O=tmp/otel-f-evidence/f2-fetch`), byte-verified; offline per-cell replay as for F.
## Launch
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=2 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_offpath_f.py EXPECTED_PLAN=373a1ece8c5ff5bca99ecb25491399d0379bd9df044d8a94f6bf577125963a6f \
  RUN_COUNT=25 CAMPAIGN=otel-offpath-f-v1 LOG_PREFIX=otel-offpath-f-v1 \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh f2 715d57b5f06ea32d47466acccae927da8e350a2c > scratchpad/gate-drivers/otel-offpath-f-v1-f2.out 2>&1 &
```
At most 1 relaunch, harness or infrastructure defects only.
