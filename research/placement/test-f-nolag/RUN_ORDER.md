# F ablation `otel-offpath-f-nolag-v1`: analysis run order (written 2026-10-15, before the ablation is fetched)

The ablation is campaign F without the collector's `kafkametrics` receiver (`research/traffic-sweep/BUDGET_OVERNIGHT_20261014.md` item 2; harness worktree
`../observability-placement-runtime-otel-ablation`, branch `otel-ablation-20261014`, activated at `4ab4433`; descriptor `pipelines/campaigns/otel-offpath-f-nolag-v1.json`).
It is analysed by the frozen **v3.5** chain (`research/protocol/FREEZE_V35_20261015.md`), which is v3.3's reader plus one admitted epoch, on the ablation alone. Scope: instance.
Its declaration (`DECLARATION_F_NOLAG_OTEL.md`) is not committed at this writing; the pass rule the scorer applies is the frozen `V32_PASS_RULE` (fraud and accounting classes at 6/T_r),
which is F's. No frozen file is edited (`sweep_analysis_v3*.py`, `parameters_v3*.json`, `celf_v3*.py`, `score_test_v3*.py`, `adapter.py`, `posthoc_lanes_v33.py`, `fresh_fa_f.py`).
F's pin `score_test_v3_3.PINNED_PLACEMENTS["otel"]` = `ce6bfc1b9addbb1771b189c9330b1930f0d84c9890c1fd8d8e8cae0978d20a3d` stays F's and is never consulted; `score_test_v3_5.PINNED_PLACEMENTS`
is empty; the ablation is scored through `research/placement/test-f-nolag/score_nolag.py`, which sets the pin to the ablation placement's digest for its one process and records it.

Rules for every step: run from the repo root with `uv run python` (3.13, as F); commit each output **unedited before reading it** (separate commit per output,
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`); a new run goes to a new path (never overwrite); `--allow-unpinned` is never used.
Pass **only** `tmp/otel-f-evidence/nolag1-fetch/x` to a reader. No `f1-fetch`, `f2-fetch`, `f2-fetch2`, `f3-fetch` path may be passed to any v3.5 command (v3.2's
one-epoch refusal stops a pooled read of the epochs, but the duplicate guard keys on (campaign root, run path) and does not see a copy of the wrong epoch's cells under another name).
The ablation is not pooled with F; the result note reports both side by side.

## 0. Frozen digests, before the fetch is opened

```
/usr/bin/awk -F'|' '/^\| `(research|tests)/ {gsub(/[` ]/,"",$2); gsub(/[` ]/,"",$3); print $3"  "$2}' research/protocol/FREEZE_V35_20261015.md | shasum -a 256 -c - | /usr/bin/grep -v ': OK'
```
Expected: no line (the V35 digest table is complete and current at its commit). Any line is a deviation to record before going on. The v3.3 table's one known difference
(`score_test_v3_3.py`: pre-pin `a0d3c6af...` in the table, post-pin `704cf341...` installed, `FREEZE_V33_20261014.md` step 2) is the reason the v3.5 table lists the v3.3 files itself with their installed digests.

## 1. Fetch and byte-verify

`scratchpad/gate-drivers/fetch_overnight.sh` has no case for the ablation at this writing (it is another worker's file, uncommitted; not edited here). The case to add, by the pattern of `otelF1`/`otelF2`:
```
  otelNL1) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-offpath-f-nolag-v1; O=tmp/otel-f-evidence/nolag1-fetch ;;   # F ablation (kafkametrics removed); fill in the declaration and plan digests
```
then `bash scratchpad/gate-drivers/fetch_overnight.sh otelNL1` (read-only on the host). Check first that the host is not still running a campaign (the host, not a log); byte-verify against the host manifest as F's was
(437/437 for F) and record the count. Do not open any cell until step 2.

## 2. Offline terminal replay at the ablation's harness commit

As F's `research/placement/test-f/terminal-replay-f1.json` and F-rep1's step 2: `replay_fetched_campaign` of the harness commit the campaign ran at (record it; `4ab4433` unless the launch commit differs)
over the fetched gate-plan, gate-setup, install-staging setup receipt, fetched readiness and gate-run. F's exact replay command is not recorded; **record the exact command and interpreter beside the
output**: `research/placement/test-f-nolag/terminal-replay-nolag1.json`. Expected: `pass`, 25 of 25 valid. A blocked cell is preserved and flagged, not fatal (launcher rule: stop only at >= 3 blocked with 0 valid).

## 3. Training readout (blocks 1-3), twice

```
uv run python research/detection-time/sweep_analysis_v3_5.py tmp/otel-f-evidence/nolag1-fetch/x --system otel --blocks 1 2 3 \
  --split research/protocol/split_f_otel.json --out research/traffic-sweep/readout-otel-f-nolag-train-v3.5
uv run python research/detection-time/sweep_analysis_v3_5.py tmp/otel-f-evidence/nolag1-fetch/x --system otel --blocks 1 2 3 \
  --split research/protocol/split_f_otel.json --out tmp/otel-f-evidence/nolag1-train-second          # determinism pre-check; outside git
```
No `--validation`, as F. Compare the two `calibration` blocks byte for byte (F's were equal). Check `campaignsRead` lists exactly one entry, `tmp/otel-f-evidence/nolag1-fetch/x`, and 15 of 15 valid
(3 blocks x 5 cells), `v32.epochsRead` = `{otel-offpath-f-nolag-v1: 15}`, and `v35.ablation[otel-offpath-f-nolag-v1].ablationHolds` = `true` before opening anything else. **If `ablationHolds` is false** (a cell
collected a `kafka.consumer_group.lag*` sensor) the cells are not ablation cells: stop and take it to the user; nothing downstream is run. Commit `research/traffic-sweep/readout-otel-f-nolag-train-v3.5/` unedited;
record `sweep_analysis_v3_5.json` sha256.

## 4. Placement (CELF, frozen v3.5)

```
uv run python research/placement/celf_v3_5.py research/traffic-sweep/readout-otel-f-nolag-train-v3.5/sweep_analysis_v3_5.json \
  --tiers research/placement/declared/otel.effort.json --tier-catalog postureCurrentCatalog \
  --split research/protocol/split_f_otel.json --out research/placement/test-f-nolag/placement-nolag.json
```
No `--declared` (as F). `shasum -a 256 research/placement/test-f-nolag/placement-nolag.json` = the ablation pin. If it equals `ce6bfc1b...` (F's), `score_nolag.py` refuses; that would mean the two training readouts select the
same set, a result to report and to take back to the user before scoring, not a defect. Commit the placement unedited.

## 5. Freeze record entry (appended; before any test-block cell is read)

Append to `research/protocol/FREEZE_V35_20261015.md`, at the end, a section `## Ablation pin (2026-10-NN, after the ablation's training placement, before any test-block cell is read)` with: the fetch (path,
byte-verified count), the terminal replay (path, sha256, commit), the training readout (path, sha256, commit, determinism pre-check result, `ablationHolds`), the placement (path, **sha256**, commit), the pin mechanism
and its digests (`score_nolag.py` sha256, `score_test_v3_5.py` still `447219bc4832cb7fdb446721033715e33da0efdfa30efe8eca7fcc94b7bea72e` with an empty `PINNED_PLACEMENTS`, F's pin `ce6bfc1b...` unchanged), and the sentence:
"the scorer for this ablation runs with `PINNED_PLACEMENTS = {'otel': <that sha256>}` set for that process only by `research/placement/test-f-nolag/score_nolag.py` (`--ablation-placement-sha256`); the scorer's output
records it in `<out stem>.override.json`." Commit the entry alone, **before step 6**. Nothing else in the freeze record is edited.

## 6. Scoring readout (blocks 4-5 held out) and scorer

```
uv run python research/detection-time/sweep_analysis_v3_5.py tmp/otel-f-evidence/nolag1-fetch/x --system otel \
  --split research/protocol/split_f_otel.json --test-blocks 4 5 --out research/traffic-sweep/readout-otel-f-nolag-score-v3.5
```
(Reads blocks 1-5; 4-5 are held out of every fit and calibration. As F's `044b210`.) Check `campaignsRead` (one entry, nolag1-fetch/x, 25 of 25 valid). Commit unedited. Then:

```
uv run python research/placement/test-f-nolag/score_nolag.py research/traffic-sweep/readout-otel-f-nolag-score-v3.5/sweep_analysis_v3_5.json \
  --ablation-placement-sha256 <sha256 of placement-nolag.json, as recorded in step 5> \
  --placement research/placement/test-f-nolag/placement-nolag.json \
  --training-readout research/traffic-sweep/readout-otel-f-nolag-train-v3.5/sweep_analysis_v3_5.json \
  --test-blocks 4 5 --out research/placement/test-f-nolag/otel-nolag.json
```
Writes `otel-nolag.json`, `otel-nolag.md` (the scorer's, unedited) and `otel-nolag.override.json` (the override, the scorer's untouched empty pin, F's untouched pin, reader and registry pins, file digests).
Refused if any of the three exists, if a readout is not of the ablation epoch alone, or if the placement is F's or was solved on an F readout. Commit all three unedited, before reading.
The pass rule is F's (`V32_PASS_RULE`: fraud and accounting classes at 6/T_r); the lanes block is a report.

## 7. Post hoc lanes (not a verdict)

`research/lanes/posthoc_lanes_v33.py otel` binds `celf_v3_3` / `score_test_v3_3` and its readout check is `celf_v3_3.check_v33_layer`, which refuses a v3.5 readout ("is not v3.3"), so it **does not accept** the
ablation's readouts as is. `research/lanes/posthoc_lanes_v35.py` runs the same code with its chain rebound to v3.5 for one call (tested end to end on the synthetic ablation chain):
```
uv run python research/lanes/posthoc_lanes_v35.py otel \
  --training-readout research/traffic-sweep/readout-otel-f-nolag-train-v3.5/sweep_analysis_v3_5.json \
  --scoring-readout research/traffic-sweep/readout-otel-f-nolag-score-v3.5/sweep_analysis_v3_5.json \
  --placement research/placement/test-f-nolag/placement-nolag.json --out-dir research/lanes/out-f-nolag-posthoc
```
Its scoring calls empty the pin of the scorer it uses (a post hoc placement is by definition not the pinned one), so it needs no override; its decision-73 rerun must equal `placement-nolag.json`
(`zeroAlarm.baselineCheck.ratesEqualFrozen`). Output `posthoc_lanes_v33_otel.json` / `.md` (posthoc_lanes_v33's names) and `posthoc_lanes_v35_provenance.json`. F-L1, F-L2, F-L3, F-M are the declared `FNL-L1`, `FNL-L2`,
`FNL-L3`, `FNL-M` (`PREDICTIONS_OVERNIGHT_20261014.json`: "as F-L1" etc.); F-L3 reads `—` when no lag id is in the calibration, as FNL-L3 declares. `FNL-V1`..`FNL-V4` are read from the scorer's output, `FNL-V5` from step 8.
Commit unedited before reading. (`research/lanes/out-f-posthoc/` is F's failed partial run; `out-f-nolag-posthoc` is a new path.)

## 8. Fresh held-out false-alarm check (post hoc)

`research/placement/test-f/fresh-fa/fresh_fa_f.py` does **not** accept the ablation's paths (campaign, training readout, held-out cell names, reader and readout file name are F attempt 1's constants, and its default sets
include F's Kafka lag sensor, which the ablation does not collect). `research/placement/test-f-nolag/fresh_fa_nolag.py` is the adaptation of `research/placement/test-f-rep1/fresh_fa_rep.py`: it selects the 4 held-out
no-fault cells from the receipts (epoch `otel-offpath-f-nolag-v1`, `--attempt`, blocks 4-5, valid; else it refuses), builds the farm, runs the frozen **v3.5** reader's `--validation` path, shows the v3.5 readout to
`fresh_fa_f.main` through a symlink named as it expects, and records provenance (~5 min, ~78 MB of reader output kept in `tmp/`).
```
uv run python research/placement/test-f-nolag/fresh_fa_nolag.py --campaign tmp/otel-f-evidence/nolag1-fetch/x \
  --train-readout research/traffic-sweep/readout-otel-f-nolag-train-v3.5/sweep_analysis_v3_5.json \
  --sets-from-placement research/placement/test-f-nolag/placement-nolag.json \
  --out research/placement/test-f-nolag/fresh-fa-nolag
```
`--sets-from-placement` takes the ablation's own frozen `@6/T_r` and `@3/T_r` sets (unrestricted cell, rate 25): a set of two members becomes rows `@6/T_r[1]`, `@6/T_r[2]`, one label per member (FNL-V5 sums the
union rows of a set). There is no default set. Each sensor must be placeable with all three rules calibrated in the training calibration, else `summarise` asserts. Outputs `fresh_fa_f.json`, `fresh_fa_f.md` (wording
names F and "RESULT_F.md"; rows are the ablation's) and `fresh_fa_nolag_provenance.json`. Commit unedited before reading.

## What this record does not cover
- The five wrapper scripts (`celf_v3_5.py`, `score_test_v3_5.py`, `score_nolag.py`, `fresh_fa_nolag.py`, `posthoc_lanes_v35.py`) are tested with planted defects on synthetic inputs (`tests/test_wrappers_v3_5.py`,
  `tests/test_score_nolag.py`, `tests/test_fresh_fa_nolag.py`, `tests/test_posthoc_lanes_v35.py`); none has run on ablation data. `score_nolag.py`, like `score_rep.py`, is first exercised on real data in step 6;
  its real-chain test runs the whole `score_test_v3_5.main` path on a synthetic campaign.
- No independent review (no judge call, no adversarial-review subagent) of the v3.5 chain or of these wrappers at this writing; say so wherever they are cited.
- The replay command (step 2) is not recorded for F and is not invented here. `fetch_overnight.sh` has no ablation case yet (step 1). `DECLARATION_F_NOLAG_OTEL.md` is not committed at this writing; if it fixes anything
  that differs from F's frozen pass rule or sets, that is a deviation to record before step 6, not an edit of a frozen file.
- Which `runKey.attempt` the ablation's cells carry is not known here (`fresh_fa_nolag.py --attempt`, default 1, refuses on a mismatch).
