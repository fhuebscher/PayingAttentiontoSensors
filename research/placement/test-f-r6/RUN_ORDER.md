# R6 (campaign F's design on new cells, attempt 8): analysis run order (written 2026-10-16, before the fetch; no R6 cell fetched or read)

Declared in `research/traffic-sweep/DECLARATION_OTEL_R6.md` (`0ee8d62`). F's rerun run order (`research/placement/test-f-rep1/RUN_ORDER.md`) with the
substitutions below; each output committed unedited before it is read; new paths only; `--allow-unpinned` never used; scope instance. Never pooled with F, its
rerun, the ablation, R2 or R4; R4's 15 fault cells stay unread. No post hoc lanes and no fresh-false-alarm analysis (declaration, analysis item 3).

## Host preparation output (archive step, pasted unedited; before the DRY_RUN)

The declaration's "Host preparation" commands (R4's one-shot paths on srv6 moved, not deleted, into `archive-f-attempt6-20261015`, or `-attempt7-` if R4 was relaunched).
Paste the terminal output here, unedited, when it has run:

```
(not yet run)
```

## 0. Frozen digests, before the fetch is opened

As the rerun's step 0. Expected: exactly one line, `research/placement/score_test_v3_3.py: FAILED` (the table holds the pre-pin digest; installed is F's post-pin `704cf341…`).

## 1. Fetch and byte-verify

Only after R6 is terminal **by the host** (srv6: 0 containers, no `otel_candidate`/`candidate-v4` unit), not from a log:
```
bash scratchpad/gate-drivers/fetch_r6.sh otelR6     # -> tmp/otel-f-evidence/r6-fetch; refuses if it exists; read-only on the host
```
`fetch_r6.sh` committed alone in `a8fe322` (sha256 `b2d1c2495dabfbb7cc1bb9beb169b4cd0755a73e605e2828e8274e8014761f1c`; a one-case copy of `fetch_overnight.sh`'s `otelNF1`
logic, which is not edited). Byte-verified means the printed `shasum rc=0` and `OK` equal to `host files` (437 for a complete run); record the three numbers.

## 1b. Binding check on the execution package (before any reader runs)

The package carries no plan digest, and its run IDs equal the fseed worktree's attempt 8 (never executed); the commit separates them.
```
uv run python -I -c 'import json,hashlib,sys; P=json.load(open(sys.argv[1])); C=P["cells"]; ids=sorted(c["runId"] for c in C); h=hashlib.sha256("\n".join(ids).encode()).hexdigest(); bad=[c["runId"] for c in C if c["runKey"]["attempt"]!=int(sys.argv[2]) or c["frameworkCommit"]!=sys.argv[3]]; print("cells", len(C), "sortedRunIdSha256", h, "badCells", bad); sys.exit(0 if len(C)==25 and not bad and h==sys.argv[4] else 1)' \
  tmp/otel-f-evidence/r6-fetch/x/.controller/execution-package.json 8 715d57b5f06ea32d47466acccae927da8e350a2c ed0d0764ed158209a57f2a11062561ccca0cce8b2c38b568e0a497c98b4ed45f
```
Must exit 0: every cell `runKey.attempt` 8 and `frameworkCommit` `715d57b5f06ea32d47466acccae927da8e350a2c`, 25 cells, sorted run-ID sha256 (newline-joined, no trailing
newline, R4's encoding) `ed0d0764…`. Checked on R2's package (2026-10-16): with R2's values (attempt 4, `f08ba1d`, `b3206544…`) rc 0; with R6's values rc 1 (25 bad cells).
Cite the uncommitted launch log `scratchpad/gate-drivers/otel-offpath-f-v1-r6-launch.log` by sha256 in the result note.

## 2. Offline terminal replay at harness `715d57b`

As R2's (`8171b16` commit message), in the F worktree: W = `../observability-placement-runtime-otel-protocol` (clean, HEAD `715d57b5f06ea32d47466acccae927da8e350a2c`),
G = `$W/.local/candidate-v4/otel-demo/gates` (first check that `G/gate-run.json` is R6's: its `frameworkCommit` and the GATE-RUN line of the launch log), `uv run python`
3.13, a fresh `PYTHONPYCACHEPREFIX`, Apple bytecode cache (`~/Library/Caches/com.apple.python/`) cleared:
```
uv run python -I $W/modules/otel-demo/validation/candidate_terminal.py $W/.local/candidate-v4/otel-demo/plan tmp/otel-f-evidence/r6-fetch/x --gate-plan $G/gate-plan.json \
  --gate-setup $G/gate-setup.json --setup-receipt $G/install-staging/setup-receipt.json --readiness $G/fetched-readiness/readiness.json --gate-run $G/gate-run.json \
  > research/placement/test-f-r6/terminal-replay-r6.json
```
Expected: `pass`, 25 of 25 valid, all attempt 8, plan `38ff4d32d6060f7f73dd29d57718ef0d9c6234ed74214bb60d22888903e41b3c`. Record the command, input sha256s and output sha256 in the
commit message; re-run under `/usr/bin/python3` 3.9 `-I` (scratch) and record byte-equality. A blocked cell is preserved and flagged, not fatal.

## 3. Training readout (blocks 1-3), twice

```
uv run python research/detection-time/sweep_analysis_v3_3.py tmp/otel-f-evidence/r6-fetch/x --system otel --blocks 1 2 3 \
  --split research/protocol/split_f_otel.json --out research/traffic-sweep/readout-otel-r6-train-v3.3
uv run python research/detection-time/sweep_analysis_v3_3.py tmp/otel-f-evidence/r6-fetch/x --system otel --blocks 1 2 3 \
  --split research/protocol/split_f_otel.json --out tmp/otel-f-evidence/r6-train-second          # determinism pre-check; outside git
```
Pass **only** `r6-fetch/x`. `campaignsRead` exactly `[{"campaign": "tmp/otel-f-evidence/r6-fetch/x", …}]` (1 entry, 15 of 15 valid); the reader cannot tell F and R6
apart by epoch, so the binding check of step 1b is what makes it R6. Compare the two `calibration` blocks as sorted-key JSON text. Commit unedited; record the sha256.

## 4. Placement (CELF, frozen v3.3)

```
uv run python research/placement/celf_v3_3.py research/traffic-sweep/readout-otel-r6-train-v3.3/sweep_analysis_v3_3.json \
  --tiers research/placement/declared/otel.effort.json --tier-catalog postureCurrentCatalog \
  --split research/protocol/split_f_otel.json --out research/placement/test-f-r6/placement-r6.json
```
No `--declared`. Commit unedited; its sha256 is R6's pin. If it equals F's `ce6bfc1b…`, the rerun's `674580e0…`, the ablation's `8263bfd0…` or R2's `633b89f1…`,
`score_rep_r6.py` refuses: a result to report to the user before scoring, not a defect.

## 5. Freeze record entry (appended; before any test-block cell is read)

Append to `research/protocol/FREEZE_V33_20261014.md`, at the end, `## Replicate R6 pin (2026-10-NN, after R6's training placement, before any test-block cell is read)`,
in the form of the "Replicate FS1 pin" section: fetch (path, host-file count, OK count, rc), binding check (step 1b output), terminal replay (path, sha256, commit), training
readout (path, sha256, commit, determinism result), placement (path, **sha256**, commit), the pin mechanism (`research/placement/test-f-r6/score_rep_r6.py` sha256 and its
committing commit; `score_test_v3_3.py` still `704cf341ae23e09a123915e14b4546dc1e3b02b3cf7bf2fa4808059acbd2e442`, F's pin unchanged) and the sentence: "the scorer for R6 runs
with `PINNED_PLACEMENTS = {'otel': <that sha256>}` set for that process only by `research/placement/test-f-r6/score_rep_r6.py` (`--replicate-placement-sha256`); the
scorer's output records it in `<out stem>.override.json`." Commit alone, **before step 6**. Nothing else in the freeze record is edited.

## 6. Scoring readout (blocks 4-5 held out) and scorer

```
uv run python research/detection-time/sweep_analysis_v3_3.py tmp/otel-f-evidence/r6-fetch/x --system otel \
  --split research/protocol/split_f_otel.json --test-blocks 4 5 --out research/traffic-sweep/readout-otel-r6-score-v3.3
```
`campaignsRead` exactly `[tmp/otel-f-evidence/r6-fetch/x]` (25 of 25 valid); commit unedited. Then:
```
uv run python research/placement/test-f-r6/score_rep_r6.py research/traffic-sweep/readout-otel-r6-score-v3.3/sweep_analysis_v3_3.json \
  --replicate-placement-sha256 <sha256 of placement-r6.json, as recorded in step 5> \
  --placement research/placement/test-f-r6/placement-r6.json \
  --training-readout research/traffic-sweep/readout-otel-r6-train-v3.3/sweep_analysis_v3_3.json \
  --test-blocks 4 5 --out research/placement/test-f-r6/otel-r6.json
```
The wrapper refuses, before the scorer runs, if either readout's `campaignsRead` is not exactly `[tmp/otel-f-evidence/r6-fetch/x]`, if the scoring readout's `calibration`
is not byte-equal (sorted-key JSON) to the training readout's, or if either readout is a byte copy of F's, the rerun's, the ablation's or R2's. Writes `otel-r6.json`, `otel-r6.md`
and `otel-r6.override.json`; refused if the sidecar exists. Commit all three unedited, before reading. Pass rule V32_PASS_RULE per off-path class at 6/T_r.

## 7. Transfer of the frozen sets (post hoc to the sets) and its consistency check

`transfer_score.py` at `4c66582` (sha256 `b438fcaf4a07c2d674c6278cc1d073a1e0b3ceabacaff60e1163e17735372742`); `tests/test_transfer_score.py` passing (13) first.
```
uv run python research/placement/transfer/transfer_score.py research/traffic-sweep/readout-otel-r6-score-v3.3/sweep_analysis_v3_3.json --test-blocks 4 5 \
  --placement research/placement/test-f/placement-f.json --placement research/placement/test-f-rep1/placement-f3.json \
  --placement research/placement/test-f-seed2/placement-fs1.json --out research/placement/test-f-r6/transfer-r6
uv run python research/placement/transfer/transfer_score.py research/traffic-sweep/readout-otel-r6-score-v3.3/sweep_analysis_v3_3.json --test-blocks 4 5 \
  --placement research/placement/test-f-r6/placement-r6.json --out research/placement/test-f-r6/transfer-r6-own
```
Placement sha256s `ce6bfc1b…`, `674580e0…`, `633b89f1…`. The second must reproduce `otel-r6.json` `rates.25` episodes and @6/T_r verdicts, otherwise every transfer row is `—`
(`score_predictions_r6.py` checks it). Commit both directories unedited before reading.

## 8. Predictions

```
uv run python research/placement/test-f-r6/score_predictions_r6.py --out research/placement/test-f-r6/PREDICTIONS_SCORED_R6
```
Reads only `otel-r6.json`, `placement-r6.json`, `transfer-r6/transfer.json`, `transfer-r6-own/transfer.json`. If R6 stopped with no read relaunch:
`… score_predictions_r6.py --run-stopped --out research/placement/test-f-r6/PREDICTIONS_SCORED_R6` (every row `—`). Commit unedited.

## If R6 is relaunched (attempt 9; at most once, per the declaration)

Attempt 8's package goes to `tmp/otel-f-evidence/r6-stopped-fetch` through its own fetch case, committed alone (not in `fetch_r6.sh` at this writing). The relaunch is
then fetched with `fetch_r6.sh otelR6` to `r6-fetch` as above, and step 1b runs with `9 715d57b5f06ea32d47466acccae927da8e350a2c d9629ad285e4798f57ec7817547664b6a64c2537fd022a0b0dc5effa1d6a5de8`,
step 2 expects plan `563d289eadd42069cc3a06d620cd5753e237c95c4351afabfda4c2b731f9b07f` and attempt 9. Attempt 8's cells are never read.

## What this record does not cover
- `score_rep_r6.py` (`tests/test_score_rep_r6.py`) and `score_predictions_r6.py` (`tests/test_score_predictions_r6.py`) are tested on synthetic inputs and on R2's committed
  files; neither has run on R6 data. The full `score_test_v3_3.main` path under the override is stubbed in the tests.
- No independent review of these scripts at this writing; say so wherever they are cited.
- `fetch_r6.sh` was checked offline only (syntax; refusal on a planted existing `r6-fetch`); it has not run against srv6.

## Addendum 2026-10-15 UTC (after a same-provider review, before the fetch is opened; no R6 cell fetched or read; all dates in this record are UTC)

Appended; nothing above is edited. Where this addendum and the text above differ, this addendum governs.

1. **`fetch_r6.sh` replaced.** Step 1 now runs `fetch_r6.sh` committed alone in `26223b5`, sha256
   `906e517340ee0c6ad687776f8a943414de03ceb078d1b5e2daf052e692b47b90`, replacing `b2d1c249…` (`a8fe322`). Changes: before anything local is created it checks
   on the host that there are 0 running containers (a failing `docker ps` is a refusal, not a "0") and that `.controller/execution-package.json` exists
   (exit 2, "nothing created"), then runs a host-side `python3 -I` check that every cell's `runKey.attempt` equals the expected attempt (second argument,
   default 8) and `frameworkCommit` is `715d57b5f06ea32d47466acccae927da8e350a2c`; ssh errors of that check are shown. Step 1's command is
   `bash scratchpad/gate-drivers/fetch_r6.sh otelR6` (attempt 8; `… otelR6 9` for a relaunch). Step 1b still runs locally on the fetched copy (25 cells, sorted run-ID
   sha256). Tested offline only, with an ssh stub (`scratchpad/gate-drivers/test_fetch_r6.sh`, 12 cases; three planted defects each fail it); not run against srv6.
2. **Recorded deviation: a separate script.** The declaration (`DECLARATION_OTEL_R6.md`, "Fetch" line, about line 76) says the fetch case is "added to `fetch_overnight.sh`".
   It is a separate script, `fetch_r6.sh`, because `fetch_overnight.sh` is not edited while a fetch may run. The host paths and the tar/sha256 method are
   the `otelNF1` case's.
3. **Re-fetch contingency, pre-declared.** If `r6-fetch` is ever found to be a bad fetch (a refusal after `mkdir`, a failed or partial copy, `shasum` rc not 0 or OK not equal to host files),
   the re-fetch is a new case `otelR6b` in a committed script, written to `tmp/otel-f-evidence/r6-fetch2`, committed alone before it runs. `r6-fetch` is then kept
   **unverified and unused**: no reader, replay or binding check is run on it, and nothing in it is read. The same applies to the stopped-attempt case under "If R6 is relaunched".
4. **Reading of the predictions' dashes.** FR6-V1 is decided from `rates.25.verdicts` by the column text, "both PASS hit; any FAIL miss". A verdict of FAIL is a miss; a `—`
   verdict for a class, with the other PASS, has no column rule and is undecided. TR6-LAG and TR6-R2 have no miss text in their column, only "both class verdicts PASS": for these
   a FAIL with `—` in the other class is **undecided**, not a miss, until the scorer's rule is read; if `score_predictions_r6.py` decides it otherwise, that
   is reported as a deviation and the column text is quoted next to it. `—` is never `0` and never a miss by itself.
5. **Recorded addition in `score_rep_r6.py`.** The declaration says the wrapper is a copy "changed only in" PLACEMENT_DIR, VERSION and the refusal lists. It also
   carries the `campaignsRead` and `calibration` refusals (and writes `campaignsRead`/`calibrationSha256` into its sidecar). They implement checks the declaration's
   analysis item 1 names for both readouts (`campaignsRead` exactly `[tmp/otel-f-evidence/r6-fetch/x]`; the scoring readout's `calibration` byte-equal to the
   training readout's), so they are an addition beyond "changed only in", recorded here, not a change to what is measured. (The review's label for them, T4, is not a
   label in the declaration; it was not resolved here.)
6. **Analysis item 3, as declared.** Report R6's own @6/T_r set's price as the placement gives it (`placement-r6.json`, `points["6/T_r"]`), with the placement's own denominator and
   scope label (instance, OTel, one run). No fresh-false-alarm analysis, and no price for flagd impression from R4.

## Host archive output (main session, 2026-10-15 16:42Z UTC; R4 terminal 16:03:01Z, nf1-fetch 437/437 OK, shasum rc 0; package sha256 cdfb9114…)
```
/home/stig/observability-placement-candidate-v4-otel-srv6/otel-offpath-f-v1-715d57b5f06e
/home/stig/observability-placement-candidate-v4-runs/.setup-otel-offpath-f-v1
/home/stig/observability-placement-candidate-v4-runs/otel-offpath-f-v1
4.6G	/home/stig/observability-placement-candidate-v4-runs/otel-offpath-f-v1
47M	/home/stig/observability-placement-candidate-v4-runs/.setup-otel-offpath-f-v1
72M	/home/stig/observability-placement-candidate-v4-otel-srv6/otel-offpath-f-v1-715d57b5f06e
total 0
drwx------ 1 stig stig  142 Oct 15 18:42 .
drwxr-xr-x 1 root root 5670 Oct 15 18:42 ..
drwxr-xr-x 1 root root  348 Oct 15 15:32 .setup-otel-offpath-f-v1
drwxr-x--- 1 stig stig  136 Oct 15 17:57 otel-offpath-f-v1
drwxr-xr-x 1 root root   32 Oct 15 15:32 otel-offpath-f-v1-715d57b5f06e
```
