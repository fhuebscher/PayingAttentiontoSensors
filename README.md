# BenchSOC 2026 artifact v2: results, analysis code, protocol records and harness code at the launch commits

This bundle belongs to the BenchSOC 2026 paper on observability sensor placement (`papers/current/benchsoc/paper.tex`).
It is a snapshot of selected files, not repository history. v2 replaces v1: it adds the harness code at nine launch commits,
the launch and fetch scripts, and the results of the placement tests of 2026-10-15 and 2026-10-16.

Source commit of the analysis repository: `03bc89b0ed18a2558d34275bb99ebe35065a9b7d` (branch `phase2-method-contracts-20260817`). Every file was exported from git with `git archive`
at that commit, except the five launch scripts (below). Every file is byte-identical to its committed blob except the files in
`REDACTIONS.md` (before and after SHA-256 for each). `MANIFEST.sha256` has the SHA-256 of every file. Check it from this directory
with `shasum -a 256 -c MANIFEST.sha256` (macOS) or `sha256sum -c MANIFEST.sha256` (Linux).

## What is in it

- `papers/current/benchsoc/`: paper sources and built PDF.
- `research/PROTOCOL_DRAFT_20261002.md`: the decision log. `research/protocol/`: freeze records (`FREEZE_V3x_*.md`), parameter
  files, review records (`REVIEW_JUDGE_20261015.md`, `REVIEWS_LAST_RUNS_20261015.md`), `TIMELINE.md`, split files.
- `research/traffic-sweep/`: budgets (`BUDGET_*.md`), declarations (`DECLARATION_*.md`), amendments, stop and harness-change
  records, and the derived readouts (`readout-*`). Superseded reader iterations (group C2 of v1) are not included.
- `research/placement/`: placements, scorer outputs and result notes per test. New in v2: `test-ts-placement/` (TeaStore off-path,
  placement by v3.6), `test-f-seed2/` (campaign F with a new seed), `test-hotel-offpath-placement/` (Hotel off-path, v3.7),
  `test-f-nofault/` (price check on fresh no-fault time).
- `research/detection-time/` (readers `sweep_analysis_v3_*.py`), `research/lanes/`, `research/ontology/`, and the smaller pilot
  directories that the tests import.
- `src/obsplacement/` and `tests/` (the test files for the paper pipelines, including the v3.4 to v3.7 readers and wrappers, plus
  `tests/fixtures/`).
- `harness/<sut>-<label>-<sha>/`: the harness code at nine launch commits, one directory each. See `harness/PROVENANCE.md`.
- `scratchpad/gate-drivers/`: the launch scripts `launch_teastore.sh`, `launch_hotel.sh`, `launch_otel_offpath.sh` and the fetch
  scripts `fetch_overnight.sh`, `fetch_r1relaunch.sh`.
- `SCAN_REPORT.md`: what the secret and identifier scan found (file, line, pattern name; never values).
- `LICENSES.md` and the two licence texts. `README_REPOSITORY.md` is the original repository README, kept under another name.

## How the repositories fit

There is one analysis repository (this snapshot) and one harness per system under test (SUT). The harness runs the campaigns on
the lab hosts. The analysis repository reads what a campaign produced and never changes the harness.
In the source, each harness is a git worktree of the same repository, checked out at a launch commit. The per-cell drivers
(`candidate_*.py`) exist only in those trees, so they are exported here, one directory per launch commit:

| Directory | SUT | Used for |
|---|---|---|
| `harness/otel-c-8018a19/` | otel | c |
| `harness/otel-e-6a5c2a9/` | otel | e |
| `harness/otel-f-715d57b/` | otel | f |
| `harness/otel-ablation-4ab4433/` | otel | ablation |
| `harness/otel-seed2-f08ba1d/` | otel | seed2 |
| `harness/teastore-c-3b4a513/` | teastore | c |
| `harness/teastore-offpath-f74b29b/` | teastore | offpath |
| `harness/teastore-offpath-placement-04254228/` | teastore | offpath-placement |
| `harness/hotel-offpath-9ad0b98/` | hotel | offpath |

A harness directory holds `src/obsplacement/`, `modules/<sut>/`, `pipelines/campaigns/`, `tools/`, `contracts/`, `tests/`,
`pyproject.toml`, `uv.lock`, `pytest.ini` and `.python-version`. Papers, notes, other SUTs' modules and `deployment/` are left out.
The harness tests need lab hosts or the withheld evidence and were not run from this bundle.

## How a run is repeated

Each step is committed before the next one starts, and each output is committed before anyone reads it.

1. Budget and stop rule, committed alone (`research/traffic-sweep/BUDGET_*.md`).
2. Declaration with predictions, committed alone (`research/traffic-sweep/DECLARATION_*.md`).
3. `DRY_RUN=1` of the launch script on the host.
4. Launch script (`scratchpad/gate-drivers/launch_*.sh`) at the harness launch commit.
5. Fetch with byte verification (`fetch_*.sh`; host file list and `shasum` check).
6. Offline terminal replay of every cell under the host's Python 3.9 (`research/placement/test-*/terminal-replay-*.json`).
7. Training readout (`research/detection-time/sweep_analysis_v3_*.py`, blocks 1 to 3).
8. Placement (`research/placement/celf_v3_*.py`).
9. Freeze pin: a one-line commit that pins the placement digest in the scorer (`research/protocol/FREEZE_V3*_*.md`).
10. Scoring readout (blocks 4 and 5), then the scorer (`research/placement/score_test_v3_*.py`).

A new run takes a new output path. Nothing is overwritten.

## How to recompute the verdicts

You need [uv](https://docs.astral.sh/uv/) and network access once (CPython 3.13 and the locked dependencies from `uv.lock`).
From this directory:

```
mkdir -p tmp
uv run pytest -q
```

The tests rebuild the readers, wrappers, CELF placement, scorers and lanes on the included fixtures and derived readouts.
Some tests skip because an input is withheld (raw evidence, sibling harness worktrees, git history). A skip is not a pass.
The tests of the harness trees are not part of this run.

To recompute a verdict from the committed readouts, run the placement and the scorer. These are the commands quoted in the
freeze records (`research/protocol/FREEZE_V36_20261015.md` steps 3 and 6; `FREEZE_V37_20261015.md` is the same for Hotel). Run
them with a new `--out` path. The first command output is compared with the committed placement by SHA-256.

TeaStore off-path (R1):

```
uv run python research/placement/celf_v3_6.py research/traffic-sweep/readout-teastore-offpath-rep3r1-train-v3.6/sweep_analysis_v3_6.json \
  --tier-catalog postureCurrentCatalog --split research/protocol/split_ts_offpath.json --out <new>/placement.json
uv run python research/placement/score_test_v3_6.py research/traffic-sweep/readout-teastore-offpath-rep3r1-score-v3.6/sweep_analysis_v3_6.json \
  --placement research/placement/test-ts-placement/placement-rep3r1.json \
  --training-readout research/traffic-sweep/readout-teastore-offpath-rep3r1-train-v3.6/sweep_analysis_v3_6.json --test-blocks 4 5 --out <new>/ts.json
```

Hotel off-path (v3.7), same shape:

```
uv run python research/placement/celf_v3_7.py research/traffic-sweep/readout-hotel-offpath-off2-train-v3.7/sweep_analysis_v3_7.json \
  --tier-catalog postureCurrentCatalog --split research/protocol/split_hotel_offpath.json --out <new>/placement.json
uv run python research/placement/score_test_v3_7.py research/traffic-sweep/readout-hotel-offpath-off2-score-v3.7/sweep_analysis_v3_7.json \
  --placement research/placement/test-hotel-offpath-placement/placement-off2.json \
  --training-readout research/traffic-sweep/readout-hotel-offpath-off2-train-v3.7/sweep_analysis_v3_7.json --test-blocks 4 5 --out <new>/hotel.json
```

Campaign F with a new seed (usage line of `research/placement/test-f-seed2/score_rep_fs1.py`):

```
uv run python research/placement/test-f-seed2/score_rep_fs1.py research/traffic-sweep/readout-otel-fs1-score-v3.3/sweep_analysis_v3_3.json \
  --replicate-placement-sha256 <sha256 of placement-fs1.json> --placement research/placement/test-f-seed2/placement-fs1.json \
  --training-readout research/traffic-sweep/readout-otel-fs1-train-v3.3/sweep_analysis_v3_3.json --test-blocks 4 5 --out <new>/otel-fs1.json
```

These commands were taken from the result and freeze notes. They were not all re-run for this README. Each scorer pins the
placement digest, so a changed placement is refused unless `--allow-unpinned` is given. The scorer files were pinned at the pin
commit, and the `PINNED_PLACEMENTS` line in the committed scorer is the pin.

## What is withheld

Raw cell evidence is withheld: collector logs, packet captures, container logs and request ledgers, about 130 GB across the
`tmp/*-evidence/` directories of the working repository. It is not in git. The logs record lab-host identifiers. Without it,
the readers (`sweep_analysis_v3_*.py` run on fetched cells) and the terminal replays cannot be re-run. The scorers and placements read
only the derived readouts, which are included. Also left out: `.local/`, `scratchpad/` except the five scripts, `wb.env`,
upstream submodules, the C2 readout iterations, the third-party sources vendored for the ontology run (only their `PROVENANCE.json`
is kept), and files with a cloud account identifier (`SCAN_REPORT.md`).

Host names `fb14srv4/5/6` and the user names `stig` and `fhuebscher` are kept, as in v1. They are lab labels and are pinned by digests
in the freeze records.

## Licences

Code under Apache-2.0, data, derived results and documents under CC BY 4.0. Third-party carve-outs are in `LICENSES.md`.
