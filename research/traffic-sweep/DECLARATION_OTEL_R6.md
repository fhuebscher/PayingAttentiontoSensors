# R6: campaign F's design on new cells (attempt 8): declaration (2026-10-15)

**Status: to be committed alone, before the launch below, after one same-provider review GO (Claude adversarial subagent, 2026-10-15 ~14:15Z: NO-GO on text points T1-T13, applied here).** Budget `BUDGET_OVERNIGHT_20261015.md` (`bfc9417`, run R6); amendment 1 (`b43a5dd`) changes R5 only; R6 keeps the run-ID rule.
`DECLARATION_F_OTEL.md` (`8845721`) stays binding for the design, pass rule (V32_PASS_RULE) and decision 73. Scope: instance (OTel Demo 1.12.0, fb14srv6, 25 req/s).
**INFORMED BY SEEN DATA:** F, rerun, R2 verdicts, episodes and sets, and the post hoc counts in `RESULT_F_SEED2.md:84-86` (purgatory passed 2/2 per class on its own run); the ablation also passed (a variant, not in "3 of 3"); no R4 cell read.
## Run
F's unchanged descriptor on F's harness `715d57b` (worktree `observability-placement-runtime-otel-protocol`, clean), F's seed, order and onsets, at **attempt 8**:
descriptor `6164052d…` (F's), plan `38ff4d32d6060f7f73dd29d57718ef0d9c6234ed74214bb60d22888903e41b3c`, 25 cells. Its 25 run IDs collide with none of the
compiled attempts 1-7 and 9-12 of F's worktree, none of attempts 1-7 and 9-12 of the new-seed worktree (`f08ba1d`), and none of the executed packages under
`tmp/otel-f-evidence/` (execution packages and cell receipts of `f1-fetch`, `f2-fetch2`, `f3-fetch2`, `fs1-fetch2`, `nolag1-fetch`; the interrupted `f2-fetch`, `f3-fetch`, `fs1-fetch` hold no package), nor any of the 24 OTel execution packages under `tmp/` (427 cell receipts); host archive directories not checked. Sorted run-ID sha256 (newline-joined, R4's encoding): attempt 8 `ed0d0764ed158209a57f2a11062561ccca0cce8b2c38b568e0a497c98b4ed45f`, attempt 9 `d9629ad285e4798f57ec7817547664b6a64c2537fd022a0b0dc5effa1d6a5de8`; R4 attempt 6 `f2040a38…`, attempt 7 `12076078…`.
They equal the new-seed worktree's attempt 8 (run IDs do not depend on the seed), which was never executed and must never be. Attempts 6 and 7 stay R4's.
The package carries no plan digest; before any reader runs, every cell of `r6-fetch/x/.controller/execution-package.json` must have `runKey.attempt` 8 and `frameworkCommit` `715d57b5f06ea32d47466acccae927da8e350a2c`, and its sorted run-ID sha256 must be `ed0d0764…` (the commit separates it from the fseed attempt 8, whose IDs are equal); the uncommitted launch log is cited by sha256 in the result note. R6 is a same-descriptor, same-schedule rerun (order and onsets equal to attempts 1 and 3 at every cell, checked by compiling), like F's rerun (attempt 3), not a new draw of the randomisation.
Harness-test record: worktree suite at `715d57b`: 29 failed / 2441 passed / 145 skipped / 1 collection error (mlflow), the failure set identical to `6a5c2a9`'s, accepted for F (`DECLARATION_F_OTEL.md:86`); R6 runs the same commit.
## Analysis (declared before launch; each output committed unedited before it is read)
1. **Replicate of the rule:** F's rerun run order (`research/placement/test-f-rep1/RUN_ORDER.md`) on this run alone: offline terminal replay at `715d57b`
   (expected plan `38ff4d32…`); frozen v3.3 reader, training readout on blocks 1-3 (`campaignsRead` = R6's fetch only, exactly 1 entry: the reader cannot tell F
   and R6 apart by epoch), `celf_v3_3`, a recorded pin override (`research/placement/test-f-r6/score_rep_r6.py`: a copy of `test-f-seed2/score_rep_fs1.py` changed only in PLACEMENT_DIR `test-f-r6`, VERSION `score-rep-f-r6-v1`, and refusal lists extended by R2's placement `633b89f1…` and readouts `bcc4cd34…` (training), `6c5f6bc1…` (scoring); each refusal seen failing once on a planted input, recorded; committed together with `research/placement/test-f-r6/RUN_ORDER.md` (the rerun run order with fetch `r6-fetch/x`, replay plan `38ff4d32…`, outputs `-r6-`, freeze-record section 'Replicate R6 pin') before the fetch is opened; F's pin stays F's),
   scoring readout, scorer on blocks 4-5, V32_PASS_RULE per off-path class. Both readouts: `campaignsRead` exactly `[tmp/otel-f-evidence/r6-fetch/x]`; the scoring readout's `calibration` byte-equal to the training readout's.
   Never pooled with F, its rerun, the ablation, R2 or R4; R4's 15 fault cells stay unread (its declaration).
2. **Transfer of the frozen sets** (post hoc to the sets, declared here; `research/placement/transfer/transfer_score.py` at `4c66582` (transfer-score-v2, sha256 `b438fcaf4a07c2d674c6278cc1d073a1e0b3ceabacaff60e1163e17735372742`), with `tests/test_transfer_score.py` passing, 13 tests):
   on R6's scoring readout, test blocks 4-5, F's `placement-f.json` {lag}, the rerun's `placement-f3.json` {purgatory.size} and R2's `placement-fs1.json`
   {lag, flagd impression}, each at its frozen @6/T_r point, under V32_PASS_RULE's form. The selection is frozen; thresholds come from R6's own training
   calibration.
   ```
   uv run python research/placement/transfer/transfer_score.py research/traffic-sweep/readout-otel-r6-score-v3.3/sweep_analysis_v3_3.json --test-blocks 4 5 \
     --placement research/placement/test-f/placement-f.json --placement research/placement/test-f-rep1/placement-f3.json \
     --placement research/placement/test-f-seed2/placement-fs1.json --out research/placement/test-f-r6/transfer-r6
   ```
   (placement sha256 `ce6bfc1b…`, `674580e0…`, `633b89f1…`). Consistency check (budget item 2): the same script with `--placement research/placement/test-f-r6/placement-r6.json --out research/placement/test-f-r6/transfer-r6-own` must reproduce `otel-r6.json` `rates.25` episodes and @6/T_r verdicts; otherwise every transfer row is `—`.
   `—` is the scorer's or transfer script's dash: a member absent from R6's scoring ground set (decision 90), fewer than 2 valid test episodes of a class (decision 91), or no set or calibration at the rate; a run that stops with no read relaunch makes every prediction `—`. A `—` decides its prediction as undecided, neither hit nor miss.
3. No fresh-false-alarm analysis (R4 prices lag, request.count and purgatory.size on fresh no-fault time; flagd impression and R6's own set are not priced there); R6's own @6/T_r set's price is reported as the placement gives it.
## Predictions (committed here, before launch; informed by F, its rerun and R2)
| id | prediction | decided from |
|---|---|---|
| FR6-V1 | replicate: PASS for both off-path classes (3 of 3 earlier runs of this design passed) | `otel-r6.json` `rates.25.verdicts`; both PASS hit; any FAIL miss |
| FR6-V2 | replicate: the frozen @6/T_r set contains `kafka.consumer_group.lag` (chosen in 2 of 3) | `placement-r6.json` (any, any) `points["6/T_r"].set` contains `metric:kafka:kafka.consumer_group.lag`; an empty set is a miss |
| FR6-L1 | the ledger alone detects at most 1 of the 4 off-path test episodes (F 1/4, rerun 0/4, R2 0/4) | off-path `episodes` with `ledger.ttd` not null is at most 1; undecided if fewer than 4 valid off-path episodes |
| FR6-C | frontend control: the ledger is first (< 1 s) in 2 of 2 test episodes, g = 0 for that class | as R2's FS-C (ledger ttd < 1 s, set ttd >= ledger, mean penalised difference 0); a control check, not counted in the hit tally |
| TR6-LAG | transfer of F's {lag}: PASS for both off-path classes (lag had a counted fire in 12 of 12 off-path test episodes across F, rerun, R2) | `transfer.json`, both class verdicts PASS |
| TR6-R2 | transfer of R2's {lag, flagd impression}: PASS for both off-path classes | `transfer.json`, both class verdicts PASS; not independent of TR6-LAG (superset; a lag PASS implies it unless flagd is `—`); reported, not counted as a separate hit |
| TR6-PUR | transfer of the rerun's {purgatory.size}: not PASS for at least one class (0 of 8 counted off-path fires in F and R2) | `transfer.json`: hit iff at least one class verdict is FAIL; miss iff both PASS; otherwise undecided |

Scored by `research/placement/test-f-r6/score_predictions_r6.py`, committed before scorer and transfer outputs are read.
A `—` verdict decides its prediction as undecided, neither hit nor miss.
Author-side defaults (engineering, recorded): (i) no budget amendment for archive-before-fetch: the relaunch sequence below stands, so a late stop means no relaunch; (ii) TR6-R2 is kept as reported, not counted as a separate hit (non-independent of TR6-LAG).
## Host preparation (only after R4 (its last attempt: 6, or 7 if relaunched; name D accordingly) is terminal by the host and its fetch is byte-verified (shasum rc 0, every host file OK, host-file count recorded; 437 for a complete run))
R4's one-shot paths on srv6 are moved, not deleted, so that the launcher's guard (`ls -d $ARUNS/$CAMPAIGN $ARUNS/.setup-$CAMPAIGN $RELS/$CAMPAIGN-*`
must be 0) passes. The commands, run once from the repo root, output pasted into `research/placement/test-f-r6/RUN_ORDER.md`:
```
E=$(shasum -a 256 tmp/otel-f-evidence/nf1-fetch/x/.controller/execution-package.json | cut -d' ' -f1)
ssh -o BatchMode=yes -o IdentitiesOnly=yes root@fb14srv6 "E=$E"'; set -eu; A=/home/stig/observability-placement-candidate-v4-runs; R=/home/stig/observability-placement-candidate-v4-otel-srv6
test "$(docker ps -q | wc -l)" = 0
test "$(systemctl list-units --state=running,activating --no-legend --plain | grep -ciE "otel_candidate|candidate-v4" || true)" = 0
test "$(sha256sum $A/otel-offpath-f-v1/.controller/execution-package.json | cut -d" " -f1)" = "$E"
D=$A/archive-f-attempt6-20261015; test ! -e $D; install -d -m 700 -o stig -g stig $D
ls -d $A/otel-offpath-f-v1 $A/.setup-otel-offpath-f-v1 $R/otel-offpath-f-v1-*; du -sh $A/otel-offpath-f-v1 $A/.setup-otel-offpath-f-v1 $R/otel-offpath-f-v1-*
mv $A/otel-offpath-f-v1 $A/.setup-otel-offpath-f-v1 $D/; mv $R/otel-offpath-f-v1-* $D/; ls -la $D'
```
Then DRY_RUN (label `r6dry`) with the launch environment below; it must log `paths=0` and `DRY RUN: all guards passed`:
```
DRY_RUN=1 OTEL_CANDIDATE_ATTEMPT=8 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol COMPILER=candidate_offpath_f.py EXPECTED_PLAN=38ff4d32d6060f7f73dd29d57718ef0d9c6234ed74214bb60d22888903e41b3c RUN_COUNT=25 CAMPAIGN=otel-offpath-f-v1 LOG_PREFIX=otel-offpath-f-v1 zsh scratchpad/gate-drivers/launch_otel_offpath.sh r6dry 715d57b5f06ea32d47466acccae927da8e350a2c
```
## Launch (after the review GO, the archive step and a passed DRY_RUN; srv6 idle by the host; by 18:00Z)
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=8 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_offpath_f.py EXPECTED_PLAN=38ff4d32d6060f7f73dd29d57718ef0d9c6234ed74214bb60d22888903e41b3c \
  RUN_COUNT=25 CAMPAIGN=otel-offpath-f-v1 LOG_PREFIX=otel-offpath-f-v1 \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh r6 715d57b5f06ea32d47466acccae927da8e350a2c > scratchpad/gate-drivers/otel-offpath-f-v1-r6.out 2>&1 &
```
Logged to wandb:
```
nohup uv run python tools/wandb_campaign.py follow r6 scratchpad/gate-drivers/otel-offpath-f-v1-r6-launch.log > scratchpad/gate-drivers/wandb-r6.out 2>&1 &
```
The launcher's "not under caffeinate" WARN is expected (present in all six F-epoch logs).
Fetch: case `otelR6` -> `tmp/otel-f-evidence/r6-fetch`, committed alone (added to `fetch_overnight.sh` only when no fetch is running), run only after R6 is terminal by the host; byte-verified and the binding check above passed before any reader runs.
At most 1 relaunch, for infrastructure defects or a harness defect needing no commit (a commit changes `715d57b` and ends R6 with a stop note), starting within 1 h of the stop: attempt 9, plan `563d289eadd42069cc3a06d620cd5753e237c95c4351afabfda4c2b731f9b07f`
(sorted-ID sha256 `d9629ad2…`, no collision). Before it, in order: a stop note committed alone; attempt 8's package fetched to `tmp/otel-f-evidence/r6-stopped-fetch` (own case) and byte-verified; the archive step with `archive-f-attempt8-<UTC date>` and that package's digest; DRY_RUN `r6rdry`; launch label `r6r1`. If this cannot start within 1 h, there is no relaunch. A stop is the campaign ending before its 25th cell; a terminal run with blocked cells is read (cells flagged; decision 91 gives `—`). Attempt 8's cells are never read after a relaunch. A second stop ends R6 with a stop note.
