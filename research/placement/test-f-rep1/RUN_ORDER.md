# Campaign F replication 1 (attempt 2): analysis run order (written 2026-10-15, before the replicate is fetched)

Declared in `research/traffic-sweep/DECLARATION_F_OTEL_REP1.md` (`d0ef902`): the frozen v3.3 chain exactly as for F (`research/protocol/FREEZE_V33_20261014.md`
"Run order from here"), on the replicate alone. Scope: instance. No frozen file is edited (`sweep_analysis_v3*.py`, `parameters_v3*.json`, `celf_v3*.py`,
`score_test_v3*.py`, `adapter.py`). F's pin `score_test_v3_3.PINNED_PLACEMENTS["otel"]` = `ce6bfc1b9addbb1771b189c9330b1930f0d84c9890c1fd8d8e8cae0978d20a3d` stays F's;
the replicate is scored through `research/placement/test-f-rep1/score_rep.py`, which sets the pin to the replicate placement's digest for its one process and records it.

Rules for every step: run from the repo root with `uv run python` (3.13, as F); commit each output **unedited before reading it** (separate commit per output,
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`); a new run goes to a new path (never overwrite); `--allow-unpinned` is never used.
Pass **only** `tmp/otel-f-evidence/f2-fetch/x` to a reader. `tmp/otel-f-evidence/f1-fetch` (attempt 1) must never be passed:
the reader's duplicate guard keys on (campaign root, run path) and would not stop a pooled read. The replicate is not pooled with F; the result note reports both.

## 0. Frozen digests, before the fetch is opened

```
/usr/bin/awk -F'|' '/^\| `research/ {gsub(/[` ]/,"",$2); gsub(/[` ]/,"",$3); print $3"  "$2}' research/protocol/FREEZE_V33_20261014.md | shasum -a 256 -c - | /usr/bin/grep -v ': OK'
```
Expected (checked 2026-10-15): exactly one line, `research/placement/score_test_v3_3.py: FAILED`: the table holds the pre-pin digest `a0d3c6af...`; the installed file is the post-pin
`704cf341ae23e09a123915e14b4546dc1e3b02b3cf7bf2fa4808059acbd2e442` (freeze record, "Step 2"). Any other line is a deviation to record before going on.

## 1. Fetch and byte-verify

```
bash scratchpad/gate-drivers/fetch_overnight.sh otelF2          # case otelF2: host fb14srv6, ID otel-offpath-f-v1, O=tmp/otel-f-evidence/f2-fetch; read-only on the host
```
(`fetch_overnight.sh` carries the uncommitted `otelF2` case at this writing; commit it before the fetch or record that it was not.) Byte-verified against the host manifest,
as for F (437/437 there); record the count. Check the host is not still running a campaign before the fetch, not from a log.

## 2. Offline terminal replay at harness `715d57b`

As F's `research/placement/test-f/terminal-replay-f1.json` (`28ce767`: pass, 25 of 25 valid). **F's exact replay command is not recorded** (RESULT_F.md: "arguments reconstructed from the CLI
and F's gate working set"), so there is no command to list here. The replay is `replay_fetched_campaign` of the `715d57b` harness (`candidate_transport.py`) over the replicate's gate-plan,
gate-setup, install-staging setup receipt, fetched readiness and gate-run, under the interpreter F's replay used; **record the exact command and interpreter beside the output**:
`research/placement/test-f-rep1/terminal-replay-f2.json`. Replay before spend: do it before step 3 reads any cell content for analysis. Expected: `pass`, 25 of 25 valid
(attempt 2, plan `373a1ece8c5ff5bca99ecb25491399d0379bd9df044d8a94f6bf577125963a6f`). A blocked cell is preserved and flagged, not fatal (launcher rule: stop only at >= 3 blocked with 0 valid).

## 3. Training readout (blocks 1-3), twice

```
uv run python research/detection-time/sweep_analysis_v3_3.py tmp/otel-f-evidence/f2-fetch/x --system otel --blocks 1 2 3 \
  --split research/protocol/split_f_otel.json --out research/traffic-sweep/readout-otel-f2-train-v3.3
uv run python research/detection-time/sweep_analysis_v3_3.py tmp/otel-f-evidence/f2-fetch/x --system otel --blocks 1 2 3 \
  --split research/protocol/split_f_otel.json --out tmp/otel-f-evidence/f2-train-second          # determinism pre-check; outside git
```
No `--validation`, as F. Compare the two `calibration` blocks byte for byte (F's were equal). Check `campaignsRead` lists exactly one entry, `tmp/otel-f-evidence/f2-fetch/x`, and
15 of 15 valid (3 blocks x 5 cells) before opening anything else. Commit `research/traffic-sweep/readout-otel-f2-train-v3.3/` unedited; record `sweep_analysis_v3_3.json` sha256.

## 4. Placement (CELF, frozen v3.3)

```
uv run python research/placement/celf_v3_3.py research/traffic-sweep/readout-otel-f2-train-v3.3/sweep_analysis_v3_3.json \
  --tiers research/placement/declared/otel.effort.json --tier-catalog postureCurrentCatalog \
  --split research/protocol/split_f_otel.json --out research/placement/test-f-rep1/placement-f2.json
```
No `--declared` (as F). `shasum -a 256 research/placement/test-f-rep1/placement-f2.json` = the replicate pin. If it equals `ce6bfc1b...` (F's), `score_rep.py` refuses; that would mean the
two training readouts select the same set, which is a result to report and to take back to the user before scoring, not a defect. Commit the placement unedited.

## 5. Freeze record entry (appended; before any test-block cell is read)

Append to `research/protocol/FREEZE_V33_20261014.md`, at the end, a section `## Replicate F2 pin (2026-10-NN, after the replicate's training placement, before any test-block cell is read)` with:
the fetch (path, byte-verified count), the terminal replay (path, sha256, commit), the training readout (path, sha256, commit, determinism pre-check result), the placement (path, **sha256**,
commit), the pin mechanism and its digests: `score_rep.py` sha256 (this file's committing commit), `score_test_v3_3.py` still `704cf341ae23e09a123915e14b4546dc1e3b02b3cf7bf2fa4808059acbd2e442`
(unedited, F's pin `ce6bfc1b...` unchanged), and the sentence: "the scorer for this replicate runs with `PINNED_PLACEMENTS = {'otel': <that sha256>}` set for that process only by
`research/placement/test-f-rep1/score_rep.py` (`--replicate-placement-sha256`); the scorer's output records it in `<out stem>.override.json`." Commit the freeze entry alone,
**before step 6**. Nothing else in the freeze record is edited.

## 6. Scoring readout (blocks 4-5 held out) and scorer

```
uv run python research/detection-time/sweep_analysis_v3_3.py tmp/otel-f-evidence/f2-fetch/x --system otel \
  --split research/protocol/split_f_otel.json --test-blocks 4 5 --out research/traffic-sweep/readout-otel-f2-score-v3.3
```
(Reads blocks 1-5; 4-5 are held out of every fit and calibration. As F's `044b210`.) Check `campaignsRead` (one entry, f2-fetch/x, 25 of 25 valid). Commit unedited. Then:

```
uv run python research/placement/test-f-rep1/score_rep.py research/traffic-sweep/readout-otel-f2-score-v3.3/sweep_analysis_v3_3.json \
  --replicate-placement-sha256 <sha256 of placement-f2.json, as recorded in step 5> \
  --placement research/placement/test-f-rep1/placement-f2.json \
  --training-readout research/traffic-sweep/readout-otel-f2-train-v3.3/sweep_analysis_v3_3.json \
  --test-blocks 4 5 --out research/placement/test-f-rep1/otel-f2.json
```
Writes `otel-f2.json`, `otel-f2.md` (the scorer's, unedited) and `otel-f2.override.json` (the override, F's untouched pin, reader and registry pins, file digests). Refused if any of the three exists.
Commit all three unedited, before reading. The pass rule is F's (`V32_PASS_RULE`: fraud and accounting classes at 6/T_r); the lanes block is a report.

## 7. Post hoc lanes (not a verdict)

```
uv run python research/lanes/posthoc_lanes_v33.py otel \
  --training-readout research/traffic-sweep/readout-otel-f2-train-v3.3/sweep_analysis_v3_3.json \
  --scoring-readout research/traffic-sweep/readout-otel-f2-score-v3.3/sweep_analysis_v3_3.json \
  --placement research/placement/test-f-rep1/placement-f2.json --out-dir research/lanes/out-f2-posthoc
```
The script empties `score_test_v3_3.PINNED_PLACEMENTS` for its own scoring calls (a post hoc placement is by definition not the pinned one), so it needs no override; its decision-73 rerun must equal
`placement-f2.json`. (`research/lanes/out-f-posthoc/` is F's failed partial run, uncommitted and unused; `out-f2-posthoc` is a new path.) Commit unedited before reading.

## 8. Fresh held-out false-alarm check (post hoc)

`research/placement/test-f/fresh-fa/fresh_fa_f.py` does **not** accept the replicate's paths (campaign, training readout, held-out cell names and `build_farm`'s defaults are F attempt 1's constants),
so the thin wrapper `research/placement/test-f-rep1/fresh_fa_rep.py` is used. It selects the 4 held-out no-fault cells from the receipts (attempt 2, epoch `otel-offpath-f-v1`, blocks 4-5, valid; else it
refuses), builds the farm, runs the frozen reader's own `--validation` path and calls `fresh_fa_f.main` for the summary (~5 min, 78 MB of reader output kept in `tmp/`).

```
uv run python research/placement/test-f-rep1/fresh_fa_rep.py --campaign tmp/otel-f-evidence/f2-fetch/x \
  --train-readout research/traffic-sweep/readout-otel-f2-train-v3.3/sweep_analysis_v3_3.json \
  --out research/placement/test-f-rep1/fresh-fa-f2
```
Without `--set` the sets are F's two (`@6/T_r` `metric:kafka:kafka.consumer_group.lag`, `@3/T_r` `metric:kafka:kafka.request.count`): a like-for-like check of F's sets on the replicate's cells. To check the replicate's
own frozen sets instead, add `--set '@6/T_r=<sensor id>' --set '@3/T_r=<sensor id>'` into a different `--out` (a new path; each sensor must be placeable with all three rules calibrated in the replicate's
training calibration, else `summarise` asserts). Outputs `fresh_fa_f.json`, `fresh_fa_f.md` (wording names F and "RESULT_F.md"; rows are the replicate's) and `fresh_fa_rep_provenance.json`. Commit unedited before reading.

## What this record does not cover
- Both wrappers are tested with planted defects (`tests/test_score_rep.py`, `tests/test_fresh_fa_rep.py`) on synthetic inputs; neither has run on replicate data. `score_rep.py`'s only real-scorer check is
  `check_placement` on F's committed placement; the full `score_test_v3_3.main` path under the override is first exercised on the replicate.
- No independent review (no judge call, no adversarial-review subagent) of these two wrappers at this writing; say so wherever they are cited.
- The replay command (step 2) is not recorded for F and is not invented here.
