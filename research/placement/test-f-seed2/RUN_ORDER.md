# R2 (campaign F with a new seed, attempt 4): analysis run order (written 2026-10-15 ~08:30Z, while the run executes; no cell fetched or read)

Declared in `research/traffic-sweep/DECLARATION_F_OTEL_SEED2.md`. F's rerun run order (`research/placement/test-f-rep1/RUN_ORDER.md`) with these substitutions; each
output committed unedited before it is read; new paths only; `--allow-unpinned` never used; scope instance.
0. Frozen digests as in that run order, step 0 (expected: exactly the one `score_test_v3_3.py: FAILED` line, the post-pin digest `704cf341…`).
1. Fetch `bash scratchpad/gate-drivers/fetch_overnight.sh otelFS1` -> `tmp/otel-f-evidence/fs1-fetch` (srv6 checked idle first, by the host), byte-verified.
2. Offline terminal replay at harness **`f08ba1d`** (the fseed worktree; expected plan `6bc8c84a…`, 25 valid) -> `research/placement/test-f-seed2/terminal-replay-fs1.json`, with
   the exact command and interpreter recorded beside it. This is the only commit-provenance check for OTel (the reader has none).
3. Training readout: `sweep_analysis_v3_3.py tmp/otel-f-evidence/fs1-fetch/x --system otel --blocks 1 2 3 --split research/protocol/split_f_otel.json --out research/traffic-sweep/readout-otel-fs1-train-v3.3`.
   Pass **only** `fs1-fetch/x`; check `campaignsRead` has exactly 1 entry and its run IDs are attempt 4 (the reader cannot tell F and R2 apart by epoch).
4. Placement: `celf_v3_3.py` on that readout (as F) -> `research/placement/test-f-seed2/placement-fs1.json`; its sha256 recorded in a commit before step 5.
5. Scoring readout `--test-blocks 4 5 --split research/protocol/split_f_otel.json` -> `research/traffic-sweep/readout-otel-fs1-score-v3.3`.
6. Scorer `research/placement/test-f-seed2/score_rep_fs1.py <scoring readout> --replicate-placement-sha256 <sha> --placement research/placement/test-f-seed2/placement-fs1.json --training-readout <training readout> --test-blocks 4 5 --out research/placement/test-f-seed2/otel-fs1.json`.
7. Post hoc: `posthoc_lanes_v33.py otel` on the fetch (lanes; FS-L2), and `research/placement/test-f-seed2/fresh_fa_fs1.py` (fresh false alarms; FS-FA).
Wrapper checks run 2026-10-15 (planted, then removed): the rerun's placement is refused as a placement, the rerun's training readout as a byte copy.

## Deviation (2026-10-15 ~13:00Z, before the fetch is opened for analysis)
The fetch read is `tmp/otel-f-evidence/fs1-fetch2` (case `otelFS1b`, `e401199`; 437/437 byte-verified), not `fs1-fetch`: a VPN drop at ~11:30Z interrupted the first
fetch at 3.85 GB; `fs1-fetch` is kept, unverified and unused. Every step below reads `fs1-fetch2/x` where it says `fs1-fetch/x`. Nothing else changes.
