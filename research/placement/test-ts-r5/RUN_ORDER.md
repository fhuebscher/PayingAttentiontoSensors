# R5 (TeaStore same-plan repeat of R1, relaunch r5r1): analysis run order (written 2026-10-15 UTC, before the fetch; no R5 cell fetched or read)

Declared in `research/traffic-sweep/DECLARATION_TEASTORE_R5.md` (`c61cde6`), budget `BUDGET_OVERNIGHT_20261015.md` (`bfc9417`, amendment `b43a5dd`). Modelled on
`research/placement/test-f-r6/RUN_ORDER.md` and on R1's chain (`research/placement/test-ts-placement/`, `research/protocol/FREEZE_V36_20261015.md`; commits `684284f`..`4da3d99`).
Each output is committed unedited before it is read; new paths only; `--allow-unpinned` never used; scope instance (TeaStore, fb14srv5, rates 10 and 1 req/s). R1's cells, replication 2's and
the stopped attempt's are never pooled with R5's and never passed to a reader.

## The attempt and the setup ID (read this first)

R5's first launch (setup ID `b4bdd8e0df7bfc1eb7562462df181b64`) **stopped at cell 5** (2026-10-15 14:53Z; stop note
`research/traffic-sweep/STOP_TEASTORE_R5_ATTEMPT1.md`, `7c36497`). Its cells are never read. The analysed run is the **relaunch, label `r5r1`** (launched 14:57Z; log
`scratchpad/gate-drivers/teastore-r5r1-launch.log`, uncommitted; cite it by sha256 in the result note).

**Placeholder.** `9e9443fb6252e0ac7e1c6d374be15b24` below is the relaunch's setup ID, the 32-hex `releases/<ID>` of the last
`APPROVE GATE-RUN ... release=` line (not the GATE-PLAN `setupId` printed under `auto`). It is not printed yet at this writing. **The main session fills it in, in a separate commit
that changes only these placeholders, before the fetch**; until then no command below is runnable on purpose. `fetch_r5.sh` derives the same ID from the log itself and refuses any other
value, and refuses `b4bdd8e0…` and the seven earlier IDs (`b6c165a`).

## 0. Frozen digests and tests, before the fetch is opened

```
shasum -a 256 research/detection-time/sweep_analysis_v3_6.py research/protocol/parameters_v3_6.json research/protocol/split_ts_offpath.json \
  research/placement/celf_v3_6.py research/placement/score_test_v3_6.py research/placement/transfer/transfer_score.py tests/test_wrappers_v3_6.py
```
Expected (FREEZE_V36 step 1/2 and amendment; checked 2026-10-15): `98d7832c…`, `68f417c5…`, `107cb13a…`, `05c5c58a…`, `c2ab6de8…` (scorer after R1's pin, unedited), `b438fcaf…` (`4c66582`), `aceccb66…`.
```
uv run pytest -q tests/test_transfer_score.py tests/test_score_rep_ts5.py tests/test_score_predictions_ts5.py tests/test_sweep_analysis_v3_6.py tests/test_wrappers_v3_6.py
```
114 passed at this writing (2026-10-15).

## 1. Fetch and byte-verify

Only after R5r1 is terminal **by the host** (srv5: 0 containers, no `candidate-v4` unit), not from a log:
```
bash scratchpad/gate-drivers/fetch_r5.sh teastorer5 9e9443fb6252e0ac7e1c6d374be15b24     # -> tmp/teastore-offpath-evidence/r5-fetch; read-only on the host
```
Refuses (nothing created) a non-32-hex ID, any of the eight earlier IDs, an ID that is not the last GATE-RUN line's, a host result dir without `.packages/teastore-offpath-v1.json`, and an existing
`r5-fetch`. Byte-verified means the printed `shasum rc=0` and `OK` equal to `host files` (R1's complete run: 667); record the three numbers. Binding check, before any reader:
```
uv run python -I -c 'import json,sys; P=json.load(open(sys.argv[1])); print(P["setupId"], P["frameworkCommit"], len(P["cells"])); sys.exit(0 if P["setupId"]==sys.argv[2] and P["frameworkCommit"]==sys.argv[3] and len(P["cells"])==30 else 1)' \
  tmp/teastore-offpath-evidence/r5-fetch/x/.packages/teastore-offpath-v1.json 9e9443fb6252e0ac7e1c6d374be15b24 04254228aba90566dfeca603dfcc7b05b7d8d2e3
```
Must exit 0; `tmp/teastore-offpath-evidence/r5-fetch/source.txt` must end in `/<that setup ID>`.

## 2. Offline terminal replay at harness `04254228`

W = `../observability-placement-runtime-teastore-protocol` (clean, HEAD `04254228aba90566dfeca603dfcc7b05b7d8d2e3`). The driver `research/placement/test-ts-r5/replay_ts_r5.py` (sha256
`ba0e13e9251b535ce28be9a2e8f695514326c9bcd3033ddf57bdb8add0bf2956`) is a copy of `test-ts-placement/replay_ts_rep3r1.py` with labels changed and the setup ID taken as an argument; it asserts the package
`setupId` == that argument (and `source.txt` ends in it), the argument is not one of the eight earlier IDs, and `frameworkCommit` == `04254228…`. Committed with this record, before it runs.
```
PYTHONPYCACHEPREFIX=$PWD/tmp/pycache-r5.$(date -u +%H%M%S) PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 research/placement/test-ts-r5/replay_ts_r5.py \
  $PWD/../observability-placement-runtime-teastore-protocol tmp/teastore-offpath-evidence/r5-fetch 9e9443fb6252e0ac7e1c6d374be15b24 \
  research/placement/test-ts-r5/terminal-replay-r5.json
```
Save the command line as `research/placement/test-ts-r5/terminal-replay-r5.cmd.txt` (with `python3 --version`), as R1 did. Expected as R1: 30 of 30 cells replay to pass, 10 byte-equal to
the retained validation and the rest differing only in the observation path, `hostTerminalValidation` 30/30 pass; the campaign-level replay `blocked` by host-path embedding (a recorded deviation, not
an evidence defect). A cell that fails is preserved and flagged. Commit unedited.

## 3. Training readout (blocks 1-3)

```
uv run python research/detection-time/sweep_analysis_v3_6.py tmp/teastore-offpath-evidence/r5-fetch/x/teastore-offpath-v1 --system teastore --blocks 1 2 3 \
  --split research/protocol/split_ts_offpath.json --out research/traffic-sweep/readout-teastore-offpath-r5-train-v3.6
```
Pass **only** this path. `campaignsRead` exactly `[{"campaign": "tmp/teastore-offpath-evidence/r5-fetch/x/teastore-offpath-v1", …}]` (1 entry; 18 of 18 valid at R1's shape). Not a byte copy of R1's training
readout (`b00bafd0…`). Commit unedited; record the sha256.

## 4. Placement (frozen `celf_v3_6`)

```
uv run python research/placement/celf_v3_6.py research/traffic-sweep/readout-teastore-offpath-r5-train-v3.6/sweep_analysis_v3_6.json \
  --tier-catalog postureCurrentCatalog --split research/protocol/split_ts_offpath.json --out research/placement/test-ts-r5/placement-r5.json
```
No `--declared`, no `--allow-unpinned`. Commit unedited **before the scoring readout exists**; its sha256 goes into the commit message and is R5's pin. If it equals R1's `f7f5c04a…`,
`score_rep_ts5.py` refuses: a result to report to the user before scoring, not a defect.

## 5. Scoring readout (blocks 4-5 held out)

```
uv run python research/detection-time/sweep_analysis_v3_6.py tmp/teastore-offpath-evidence/r5-fetch/x/teastore-offpath-v1 --system teastore \
  --split research/protocol/split_ts_offpath.json --test-blocks 4 5 --out research/traffic-sweep/readout-teastore-offpath-r5-score-v3.6
```
`campaignsRead` exactly the same single path (30 of 30 valid at R1's shape); not a byte copy of R1's scoring readout (`b53521c9…`). Commit unedited.

## 6. Scorer (recorded pin override)

```
uv run python research/placement/test-ts-r5/score_rep_ts5.py research/traffic-sweep/readout-teastore-offpath-r5-score-v3.6/sweep_analysis_v3_6.json \
  --replicate-placement-sha256 <sha256 of placement-r5.json, as recorded in step 4> \
  --setup-id 9e9443fb6252e0ac7e1c6d374be15b24 \
  --placement research/placement/test-ts-r5/placement-r5.json \
  --training-readout research/traffic-sweep/readout-teastore-offpath-r5-train-v3.6/sweep_analysis_v3_6.json \
  --test-blocks 4 5 --out research/placement/test-ts-r5/ts-r5.json
```
Writes `ts-r5.json`, `ts-r5.md` and `ts-r5.override.json`; refuses if the sidecar exists. Commit all three unedited, before reading. Rule V36_PASS_RULE per rate (declaration, analysis item 1).
`score_rep_ts5.py` (sha256 `dc22b6a3…`) lists seven earlier setup IDs in its own refuse list, not the stopped attempt's `b4bdd8e0…`: a recorded gap, covered by `fetch_r5.sh` and `replay_ts_r5.py`
refusing it and by the wrapper's own `source.txt` / package `setupId` == `--setup-id` check.

## 7. Transfer of R1's frozen sets and its consistency check

`transfer_score.py` at `4c66582` (sha256 `b438fcaf4a07c2d674c6278cc1d073a1e0b3ceabacaff60e1163e17735372742`); `tests/test_transfer_score.py` passing first (step 0). The readout argument is **the same string** as the
scorer's `inputs.readout` (check `ts-r5.json` `inputs.readout` / `readoutSha256` and record the check in the result note):
```
uv run python research/placement/transfer/transfer_score.py research/traffic-sweep/readout-teastore-offpath-r5-score-v3.6/sweep_analysis_v3_6.json --test-blocks 4 5 \
  --placement research/placement/test-ts-placement/placement-rep3r1.json --out research/placement/test-ts-r5/transfer-r5
uv run python research/placement/transfer/transfer_score.py research/traffic-sweep/readout-teastore-offpath-r5-score-v3.6/sweep_analysis_v3_6.json --test-blocks 4 5 \
  --placement research/placement/test-ts-r5/placement-r5.json --out research/placement/test-ts-r5/transfer-r5-own
```
R1's set: rate 1 `{log:webui:d4d75ec135e6}`, rate 10 `{span:auth:BCryptProvider.checkPassword}` (placement sha256 `f7f5c04a…`). The own-placement run must reproduce `ts-r5.json`'s per-episode outcomes and
@6/T_r verdicts, otherwise TS5-T1 and TS5-T10 are `—` (`score_predictions_ts5.py` checks it). Commit both directories unedited before reading.

## 8. Predictions

```
uv run python research/placement/test-ts-r5/score_predictions_ts5.py --scored research/placement/test-ts-r5/ts-r5.json --placement research/placement/test-ts-r5/placement-r5.json \
  --transfer research/placement/test-ts-r5/transfer-r5/transfer.json --transfer-own research/placement/test-ts-r5/transfer-r5-own/transfer.json \
  --out research/placement/test-ts-r5/PREDICTIONS_SCORED_TS5
```
Reads only those four files. If the relaunch stopped too (a second stop ends R5 with a stop note): `uv run python research/placement/test-ts-r5/score_predictions_ts5.py --run-stopped --out research/placement/test-ts-r5/PREDICTIONS_SCORED_TS5`
(every row `—`). Commit unedited. `—` decides a prediction as undecided, neither hit nor miss.

## What this record does not cover
- `score_rep_ts5.py`, `score_predictions_ts5.py` and `replay_ts_r5.py` have not run on R5 data. `replay_ts_r5.py` was run only to its first guards (a bad and an earlier setup ID are refused, offline);
  its body is R1's driver, unchanged except as stated.
- No independent review of this record or of `replay_ts_r5.py` at this writing; say so wherever they are cited.
- `fetch_r5.sh` was checked offline only (ssh stub, 20 cases); it has not run against srv5.
- The relaunch's setup ID, its launch-log sha256 and its terminal state are not recorded here: they do not exist at this writing.

- 2026-10-15 ~15:10Z (main session): setup ID filled in: `9e9443fb6252e0ac7e1c6d374be15b24`, the last `APPROVE GATE-RUN … release=…/releases/<32hex>` of `scratchpad/gate-drivers/teastore-r5r1-launch.log` (same expression as `fetch_r5.sh`).
