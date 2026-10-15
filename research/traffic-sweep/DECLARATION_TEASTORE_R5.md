# R5: TeaStore off-path placement, same-plan repeat of R1 (identical seed, order, onsets and host; run-to-run variation only) + transfer of R1's frozen sets: declaration (2026-10-15)

**Status: to be committed alone, before the launch below, after one same-provider review GO (Claude adversarial subagent, 2026-10-15 ~14:12Z: GO after text fixes T1-T10, applied here).** Pre-launch cross-provider reviews
(gpt-6.1-sol via the llm_as_judge CLI): `eval_5a2ea355…` refuted readiness on run-ID identity alone (resolved by budget amendment 1, `b43a5dd`); `eval_1953d9e3…`
raised no point beyond the missing same-provider GO. Budget `BUDGET_OVERNIGHT_20261015.md` (`bfc9417`) and amendment 1 (`b43a5dd`, evidence identity).
`DECLARATION_TEASTORE_OFFPATH_PLACEMENT.md` (`42c04f3`, R1) stays binding for design, rule and the frozen v3.6 chain (`research/protocol/FREEZE_V36_20261015.md`,
`975b7a1`, amendment `fbcabc4`; reader/placement/scorer digests as recorded there). Scope: instance (TeaStore, fb14srv5, rates 10 and 1 req/s).
## What it is
A fresh run of the unchanged epoch `teastore-offpath-v1`: harness `04254228` (worktree `observability-placement-runtime-teastore-protocol`, clean, HEAD
`04254228aba90566dfeca603dfcc7b05b7d8d2e3`), plan `5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a`, descriptor `127e8263…`, 30 cells: 5 blocks x rates
10 and 1 req/s x {no-fault, recommender pause (off path), auth freeze (on-path control)}. Same seed, order and onsets as every earlier launch of this plan on srv5 (the
compiler has no attempt or seed parameter: run IDs are fixed, `teastore-offpath-v1/<regime>/r<rate>/b0N/full/a01`). Seven srv5 result directories already carry these 30 run IDs: `c88ed29d…` (off-path attempt 1, stopped), `def272fd…` (its relaunch 1, local `r1-fetch`, which is not R1), `887a7838…`, `d61bfea7…` (replication 1 and its relaunch, both stopped), `cbe9920a…` (replication 2), `416ea06f…` (R1 stopped attempt), `dcc8b664…` (R1). New cells under a new setup ID: R5's setup ID is the one in the GATE-RUN `release=…/releases/<setup ID>-04254228aba9-…` line of `teastore-r5-launch.log` (the second `setupId` the log prints, after `readiness re-admitted`), not the GATE-PLAN `setupId` printed under `auto` (R1: `c1521ee4…` under auto; result directory `dcc8b664…`). Per budget amendment 1 the evidence is identified by **(setup ID, run ID)**: the fetch reads only `<results>/<new setup ID>/`,
the fetch path is new, the replay asserts `x/.packages/teastore-offpath-v1.json` `setupId` == R5's setup ID and `frameworkCommit` == `04254228` (as `replay_ts_rep3r1.py:25-26` does for R1; the campaign ID is `teastore-offpath-v1` for every run of this epoch and identifies nothing), both readouts' `campaignsRead[*].campaign` is exactly `["tmp/teastore-offpath-evidence/r5-fetch/x/teastore-offpath-v1"]` (`campaignsRead` records the path, not the setup ID; `r5-fetch/source.txt` and the package's `setupId` bind the path to the setup ID), and neither is a byte copy of an earlier readout. No host path needs moving: each campaign has its own
setup-ID result directory on srv5 (checked 13:59Z: 0 containers, no active campaign unit, 349 GB free; R1's relaunch terminal `complete` 12:48:02Z).
DRY_RUN `r5dry` passed 2026-10-15 13:59:43Z (all guards; srv5 ncpu 24, candidate containers 0, invariants match, authorization live).
Only this run's fetch (`tmp/teastore-offpath-evidence/r5-fetch`) is read; `campaignsRead[*].campaign` must be exactly its path, as above.
## Analysis (budget items 1 and 2; each output committed unedited before it is read)
1. **Replicate of the rule** (as R1): byte-verified fetch; offline terminal replay; v3.6 training readout on blocks 1-3; `celf_v3_6` placement; the placement pinned by
   a **recorded pin override** in the `score_rep` pattern (`research/placement/test-ts-r5/score_rep_ts5.py`: imports `score_test_v3_6` unchanged, replaces its
   `PINNED_PLACEMENTS` for one call, writes an `.override.json` sidecar; refuses: R1's placement digest `f7f5c04a…`; any byte copy of R1's readouts; a readout whose `campaignsRead` is not exactly the r5-fetch path; an r5-fetch whose `source.txt` or package `setupId` is not R5's setup ID; and `score_test_v3_6.PINNED_PLACEMENTS` other than R1's `{"teastore": "f7f5c04a…"}` at import; it records the setup ID and the placement's commit in the `.override.json`; no frozen file edited),
   committed with a planted-defect test (each check seen failing) before the fetch is read. R5's placement JSON is committed unedited before the scoring readout is generated, and the wrapper is called with that committed file's sha256; scorer. Rule V36_PASS_RULE per rate:
   the frontier (effort<=any, runtime<=any) set @6/T_r passes iff g > 0 and it strictly improves on the ledger in >= 2 of 2 test episodes of the recommender pause;
   dash if fewer than 2 valid test episodes or a member absent; decision 73 unchanged; the recommender's own sensors excluded for its class; by-construction fires
   count for the ledger only. Auth freeze carries no verdict.
2. **Transfer of R1's frozen sets** (post hoc to the sets, declared here): `research/placement/transfer/transfer_score.py` (shared with R6; committed at `47abf3c` with `tests/test_transfer_score.py`, which reproduces R1's `ts-rep3r1.json`; review fixes committed before this fetch is read; its readout argument is the same file (path and sha256) as the R5 scorer output's `inputs.readout` / `readoutSha256`, checked and recorded in the result note) on this run's v3.6 scoring readout: per recommender-pause test episode, the earliest counted fire of
   the set's members vs the ledger alone (improved iff strictly earlier; a ledger miss charged the hold), in the pass rule's form (>= 2 of 2 per rate). Sets: rate 1
   `{log:webui:d4d75ec135e6}`, rate 10 `{span:auth:BCryptProvider.checkPassword}` (R1's `placement-rep3r1.json`). The selection is frozen; thresholds come
   from this run's own training calibration; a set's price there is reported, not a condition of the verdict. A member absent from this run's scoring-readout ground set makes that verdict `—` (decision 90, `absentFromScoringGroundSet`). Consistency check (budget item 2): `transfer_score.py` run with R5's own placement must reproduce the R5 scorer's per-episode outcomes; otherwise the transfer rows are `—`.
## Predictions (committed here, before launch; INFORMED BY SEEN DATA: R1 and its review, replication 2 and its v3.6 dry run, off-path relaunch 1 (`def272fd…`))
R1: rate 1 PASS through the webui line (fires 11.4 / 12.1 s); rate 10 FAIL (CELF chose the auth span, 1 of 2; the webui line fired 2 of 2 but added no training gain
after it). The webui line fired in 10 of 10 recommender-pause episodes of off-path relaunch 1 and 5 of 5 per rate in R1, 9-15 s after onset; the auth span's training
no-fault price differed between runs (R1: 19.97/h at rate 10, 41.97/h at rate 1; replication 2 dry run: 41.97 and 51.69/h, not recurring).
| id | prediction | decided from |
|---|---|---|
| TS5-V1 | replicate: PASS at rate 1 | scorer verdict |
| TS5-V10 | replicate: PASS at rate 10 (low confidence) | scorer verdict |
| TS5-S | replicate: the frozen @6/T_r set contains `log:webui:d4d75ec135e6` at both rates; `—` if the @6/T_r point is absent at a rate; an empty set is a miss | placement |
| TS5-T1 | transfer: R1's rate-1 set `{webui line}` improves on the ledger in 2 of 2 rate-1 test episodes | transfer script |
| TS5-T10 | transfer: R1's rate-10 set `{auth span}` improves in at most 1 of 2 rate-10 test episodes (low confidence) | transfer script |
| TS5-L | the ledger alone misses 4 of 4 off-path test episodes (true by construction if no request in the window touches recommender); a check, not counted as a hit or a miss | scorer episodes |
| TS5-C | auth freeze: the ledger detects 4 of 4 test episodes | scorer episodes |
`—` (no verdict, a member absent, fewer than 2 valid test episodes, or the run stopped) decides a prediction as **undecided**, neither hit nor miss. Predictions are scored by a script committed before the scorer and transfer outputs are read (as `score_predictions_ts3.py`, `493732b`).
## Launch (srv5 idle by the host; by 16:00Z, else a stop note and no run)
```
W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
cd $M
TEASTORE_ROOT=$W EXPECTED_HEAD=04254228aba90566dfeca603dfcc7b05b7d8d2e3 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_offpath_ts.py EXPECTED_PLAN=5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a RUN_COUNT=30 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh r5 > $M/scratchpad/gate-drivers/teastore-r5.out 2>&1 &
```
Logged with `uv run python tools/wandb_campaign.py follow r5 scratchpad/gate-drivers/teastore-r5-launch.log`. Fetch: case `teastorer5` in a one-case copy
`scratchpad/gate-drivers/fetch_r5.sh teastorer5 <new setup ID>` (refuses a non-32-hex ID and all seven earlier setup IDs above, and checks the result directory exists before creating `r5-fetch`; script fix committed before the fetch), to `tmp/teastore-offpath-evidence/r5-fetch`, byte-verified (every host file OK,
shasum rc 0) before anything is read. **Relaunch:** at most 1, harness or infrastructure defects only, starting within 1 h of the stop and by 17:00Z (stricter than the budget), on the same
commit and plan; the stopped attempt's cells are kept and never read. A stop note naming the stopped attempt's setup ID is committed alone, and DRY_RUN is run, before the relaunch; the fetch then reads only the relaunch's setup ID, and `fetch_r5.sh`'s refuse list gains the stopped one. A second stop ends R5 with a stop note.
