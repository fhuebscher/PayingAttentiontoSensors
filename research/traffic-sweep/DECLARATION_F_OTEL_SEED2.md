# OTel campaign F with a new seed (R2, attempt 4): declaration (2026-10-15)

**Status: committed alone, before the launch below.** Budget `BUDGET_TS_PLACEMENT_20261015_AMENDMENT1.md` (`369b18c`, item R2). `DECLARATION_F_OTEL.md` (`8845721`)
stays binding for everything not changed here (design, pass rule, decision 73, evidence handling). Scope: instance (fb14srv6).
## What differs from F
Only the compiler's schedule seed: 20261016 (F: 20261014). Worktree `observability-placement-runtime-otel-fseed`, branch `otel-fseed-20261015` from `715d57b`:
`52333a7` (seed + regenerated descriptor; its diff against F's is `schedule.seed` and 4 of the 5 per-block orders with their `orderSha256`; block 2's order is unchanged. The `52333a7` message
says "the 5 per-block orders", an erratum recorded here), `f08ba1d` (test pins;
one planted defect made seed-independent) = the launch commit. Epoch id `otel-offpath-f-v1` kept: the frozen v3.3 reader admits by epoch id, system and regime
profile, not by seed or descriptor digest. Descriptor `74669810…`, plan (attempt 4) `6bc8c84a2e0707d3d43a10123fe39d9831dfb3739db41915fb7f272df87229d6` (attempt 4
so no run ID repeats F's attempts 1-3). Against F attempt 1, all 25 `faultOnsetSeconds` differ (by 0.06-31.5 ms: every onset is 60 s plus a phase inside one 0.04 s inter-arrival) and the cell
order differs at 10 of 25 positions. R2 is an independent-seed draw of the same randomisation, not a test of sensitivity to onset timing. F attempt 3's
host paths were moved (not deleted) to `archive-f-attempt3-20261015/` on srv6 after confirming its fetch `f3-fetch2` verifies 437/437. DRY_RUN `fsdry2` passed
2026-10-15 07:39:44Z (srv6 0 units, 0 containers, 216 GB free, 0 F paths). Launch review (same-provider adversarial subagent, 2026-10-15 ~08:20Z): **GO**; the declaration text corrected per its N1 and N5. Analysis notes from it
(N2-N4): the `test-f-seed2` copies of `score_rep.py` and `fresh_fa_rep.py` set their own placement dir, ATTEMPT 4 and refuse F's, the rerun's and the
ablation's readouts; the terminal replay runs at `f08ba1d` (expected plan `6bc8c84a…`), the only commit-provenance check for OTel; only `fs1-fetch/x` is
passed to a reader and `campaignsRead` has exactly 1 entry (the reader cannot tell F and R2 apart by epoch). F must never use attempt 4.
## Analysis (declared before launch)
F's rerun run order (`research/placement/test-f-rep1/RUN_ORDER.md`) on this run alone, with fetch case `otelFS1` (`tmp/otel-f-evidence/fs1-fetch`) and output
names `-fs1-` in a new directory `research/placement/test-f-seed2/` (a copy of `score_rep.py` with its own recorded pin, written before the fetch is opened;
F's pin stays F's). Never pooled with F, its rerun or the ablation. Fresh held-out false alarms post hoc, as for F.
## Predictions (from F, its rerun and the ablation; committed here, before launch)
| id | prediction |
|---|---|
| FS-V1 | PASS for both off-path classes under F's rule (3 of 3 earlier runs of this design passed) |
| FS-V2 | the frozen @6/T_r set is one `metric:kafka:*` id; which id is not predicted (three runs chose three different ids) |
| FS-L1 | the ledger alone detects at most 1 of the 4 off-path test episodes (F 1/4, rerun 0/4, ablation 1/4) |
| FS-L2 | the Kafka coordinator log lane has a counted fire at 42-47 s in 4 of 4 off-path test episodes (F-L2) |
| FS-C | on the frontend-pause control the ledger is first (< 1 s) in 2 of 2 test episodes, g = 0 for that class |
| FS-FA | post hoc, the frozen set raises at most 2 alarms in the 0.2 h of held-out no-fault time |
## Launch (after the review GO)
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=4 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-fseed \
  COMPILER=candidate_offpath_f.py EXPECTED_PLAN=6bc8c84a2e0707d3d43a10123fe39d9831dfb3739db41915fb7f272df87229d6 \
  RUN_COUNT=25 CAMPAIGN=otel-offpath-f-v1 LOG_PREFIX=otel-offpath-f-v1 \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh fs1 f08ba1d5313bef128ec88d73e1b4cdd1fe2cafe5 > scratchpad/gate-drivers/otel-offpath-f-v1-fs1.out 2>&1 &
```
At most 1 relaunch, harness or infrastructure defects only, starting no later than 13:00Z: attempt 5, plan
`c55312d7dbd53e6b55a93b09ba77cbf4bb3495ff648c7c9a184b583da7ca2dc5`. Logged with `tools/wandb_campaign.py follow fs1 <launch log>`.
