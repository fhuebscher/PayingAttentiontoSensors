# Campaign F no-lag ablation (`otel-offpath-f-nolag-v1`, OTel off-path faults): result (2026-10-15)

Scope: **instance** (OTel Demo 1.12.0, fb14srv6, 25 req/s of the upstream mix, 5 blocks, n = 2 test episodes per class). One run, analysed alone; it is not pooled with F or with F's replicate.
The ablation is F's design with the collector's `kafkametrics` receiver (and its `resource/kafka` processor, `metrics/kafka` pipeline and otelcol's `depends_on kafka`) not rendered. Seed 20261015 (F: 20261014), so block orders and onset strata are **new draws**.
Numbers for the ablation are copied from the files named below; F's and F's replicate's from `research/placement/test-f/otel-f.json`, `research/placement/test-f-rep1/otel-f3.json` and `RESULT_F_REP1.md` (which copied F's from `RESULT_F.md`; F's lane and fresh-false-alarm rows were not re-read from F's own files here).
Every ablation output was committed unedited **before it was read**; the one exception is stated in deviation 2.

- Declaration `DECLARATION_F_NOLAG_OTEL.md` (`14af489`); predictions FNL-* `PREDICTIONS_OVERNIGHT_20261014.json` (`8b89d43`), committed before launch (launched 2026-10-15 01:53:28Z). Harness `4ab4433`, plan `858bbcd3634a48c30af55546308d181ebed6daf9af29161f1b5cf760e263026e` (attempt 1, 25 cells).
- Run: terminal `attempted 25, valid 25` on fb14srv6. Fetched to `tmp/otel-f-evidence/nolag1-fetch/x` with `fetch_overnight.sh otelNL1`; verify line `otel-offpath-f-nolag-v1: host files 437, OK 437, shasum rc=0`.
  Offline terminal replay at `4ab4433`: `terminal-replay-nl1.json` (`07342a6`, command in the commit message), `verdict` `pass`, `validCells` 25.
- Chain (frozen v3.5, `FREEZE_V35_20261015.md`, run order `RUN_ORDER.md`): training readout `bf8ec4d` (15 of 15 valid; `campaignsRead` one entry; `v32.epochsRead` `{otel-offpath-f-nolag-v1: 15}`; determinism pre-check: `calibration` blocks byte-equal, whole readout equal except `generatedAt` and `label`;
  `v35.ablation[...].ablationHolds` **true**, `cellsWithLagLaneSensor` 0, `cellsWithCoordinatorLaneSensor` 15), placement `bbfe72c` (sha256 `8263bfd0b16659e82c8d43f9835772c4f279918262b84a37f1c0e5d3e5425085`; F's is `ce6bfc1b...`), freeze entry `5ff756d`,
  scoring readout `97404b6` (25 of 25 valid, one `campaignsRead` entry), `score_nolag.py` output `f31e5fb` (`otel-nolag.json`, `.md`, `.override.json`), post hoc lanes `8e52946` (`research/lanes/out-f-nolag-posthoc`; decision-73 rerun `ratesEqualFrozen` true),
  fresh false alarms `0c794ec`, `score_predictions_fnl.py` `c7823ef`, predictions scored `06f60ca`. Python 3.13 (`uv run python`).

## Verdicts (the preregistered rule, F's `V32_PASS_RULE`; `otel-nolag.json`, `rates.25.verdicts`)

| class | set | F | F replicate (attempt 3) | ablation (no lag receiver) |
|---|---|---|---|---|
| frauddetectionservice pause | `frontier (effort<=any, runtime<=any) @6/T_r` | PASS (g = 42.05 s, 2 of 2 improved) | PASS (g = 53.655 s, 2 of 2 improved) | PASS (g_E = 51.1439 s, 2 of 2 improved) |
| accountingservice pause | same | PASS (g = 53.23 s, 2 of 2 improved) | PASS (g = 58.5469 s, 2 of 2 improved) | PASS (g_E = 51.0597 s, 2 of 2 improved) |

Unrounded g, ablation: fraud 51.143910240381956, accounting 51.0597237162292 (F: 42.04993839934468, 53.227133959531784; replicate: 53.654993411153555, 58.546938721090555).

## Frozen set and its price (`placement-nolag.json`, `rates.25.costs`; T_r = 0.30 h)

| | F | F replicate | ablation |
|---|---|---|---|
| `@6/T_r` set | `metric:kafka:kafka.consumer_group.lag` (1 sensor) | `metric:kafka:kafka.purgatory.size` (1) | `metric:kafka:kafka.request.count` (1) |
| `@3/T_r` set | `metric:kafka:kafka.request.count` (1) | `metric:kafka:kafka.purgatory.size` (same as `@6/T_r`) | `metric:cartservice:calls` (1; not the `@6/T_r` set) |
| training price of the `@6/T_r` sensor (budget 20.0 /h) | 15.81 /h | 9.99 /h | 15.812881727968593 /h |
| training price of `kafka.consumer_group.lag` / `kafka.request.count` / `kafka.purgatory.size` | 15.81 / 9.99 / 9.99 | 35.04 / 15.81 / 9.99 | no lag id in the ground set (the key list has none) / 15.81 / 9.99 |
| training price of the ablation's `@3/T_r` sensor `metric:cartservice:calls` | — | — | 9.985774245179966 /h |
| set-level D(S), D(ledger), g over all 6 test episodes (`@6/T_r`) | 4.73, 36.49, 31.76 | 2.77, 40.17, 37.40 | 5.242, 39.310, 34.068 |
| `@3/T_r`: D(S), g (6 episodes) | 4.61, 31.89 | 2.77, 37.40 | 8.964, 30.346 |
| episodes detected by the `@6/T_r` set | 6 of 6 | 6 of 6 | 6 of 6 |

The three placements differ. The ablation's `@6/T_r` set holds one non-lag Kafka broker metric (`kafka.request.count`, F's `@3/T_r` sensor) at 15.81 /h; one such sensor fits the 20 /h budget, a second does not. The ablation calibration holds 4756 ground-set sensors and 389 metric ids; 0 of them are `kafka.consumer_group.lag*`.

## Test episodes (`otel-f.json` / `otel-f3.json` / `otel-nolag.json`, `rates.25.episodes`; seconds after the pause command's pre-command stamp; "miss" = no counted fire in the 60 s hold)

| test episode | F: ledger | F: set | replicate: ledger | replicate: set | ablation: ledger | ablation: `@6/T_r` set |
|---|---|---|---|---|---|---|
| accounting, block 4 | miss | 4.51 | miss | 1.59 | miss | 6.34 |
| accounting, block 5 | miss | 9.16 | miss | 1.44 | miss | 11.60 |
| fraud, block 4 | 38.12 | 4.77 | miss | 1.15 | miss | 6.08 |
| fraud, block 5 | miss | 9.31 | miss | 11.65 | 54.87 | 6.56 |
| frontend, block 4 | 0.35 | 0.35 | 0.40 | 0.40 | 0.48 | 0.48 |
| frontend, block 5 | 0.31 | 0.31 | 0.37 | 0.37 | 0.40 | 0.40 |

Unrounded, ablation set: 6.339001893997192, 11.601020574569702, 6.082672119140625, 6.559065341949463, 0.47594452649354935, 0.396851509809494; ledger: fraud block 5 54.86976258456707, frontend 0.47594452649354935 and 0.396851509809494.
The ledger alone has a counted fire in 1 of 4 off-path test episodes (F: 1 of 4; replicate: 0 of 4). In the frontend (on-path control) episodes the set's time equals the ledger's, so 0 of 2 improve (class has no pass rule; same in F and the replicate).

## Lane predictions (post hoc script, not a verdict; `research/lanes/out-f-nolag-posthoc/posthoc_lanes_v33_otel.json`)

| id | F | F replicate | ablation |
|---|---|---|---|
| F-L1 own silence (by-construction field) < 2.0 s | hit, 0.84-1.52 s, 4/4 | hit, 0.95-1.18 s, 4/4 | 4/4, 0.550-1.065 s (0.5501, 1.0648, 0.6387, 0.8293) |
| F-L2 coordinator counted fire 42-47 s in 4/4; none in the 2 frontend episodes | hit, 43.3-44.0 s | hit, 42.94-43.79 s; frontend none | 4/4 counted 43.08-43.87 s; frontend none in either field; one episode (accounting, block 5) also has a by-construction fire at 45.31 s |
| F-L3 lag lane | hit, 4.5-9.3 s | hit, 4.38-9.40 s | `—`: `armed` 0, `lagIdsInCalibration` 0 (no lag id collected) |
| F-M placeable non-flagd metric ids | 236 SDK + 44 spanmetrics-derived | 236 + 44 | 231 SDK + 44 spanmetrics-derived (389 metric ids in the calibration) |

## Fresh false alarms on the held-out no-fault cells (POST HOC; frozen v3.5 reader's `--validation` path; `fresh-fa-nolag/`)

4 cells (`r25-b04-16-full`, `r25-b04-17-full`, `r25-b05-21-full`, `r25-b05-22-full`), 0.2000 h. Union of the sensor's 3 rules (`spike`, `run3`, `median`); 95 % Poisson upper bound per hour; "training" = the sensor's honest training bound.

| set checked | sensor | alarms | upper /h | training /h |
|---|---|---|---|---|
| ablation `@6/T_r` | `metric:kafka:kafka.request.count` | 0 (`spike` 0, `run3` 0, `median` 0) | 14.98 | 15.81 |
| ablation `@3/T_r` | `metric:cartservice:calls` | 0 (all three rules 0) | 14.98 | 9.99 |
| F (`0790f24`, F's cells) `@6/T_r` / `@3/T_r` | lag / `request.count` | 0 / 2 | 14.98 / 31.48 | 15.81 / 9.99 |
| replicate's own set | `kafka.purgatory.size` | 1 | 23.72 | 9.99 |

Not an equivalence test; n = 4 cells, 0.2 h.

## FNL predictions (`PREDICTIONS_SCORED.md/.json`, by each prediction's declared rule)

FNL-L1 hit, FNL-L2 hit, FNL-L3 `-` (not applicable, as declared), FNL-M hit (231 SDK + 44 spanmetrics-derived), FNL-V1 hit (the `@6/T_r` set is `metric:kafka:kafka.request.count`), FNL-V2 hit (PASS), FNL-V3 hit (PASS), FNL-V4 hit (0 of 2 frontend episodes improved),
FNL-V5 hit (0 alarms in 0.2 h for the ablation's own `@6/T_r` set, <= 4).
Ontology items (`research/ontology/compare.py` rules, scored one by one): fraud row: own disagree, coordinator agree, lag not comparable, class agree, window disagree (predicted [45, 45] s, measured 43.08-43.12 s), entry-reached **disagree** (predicted no; the ledger fired in 1 of 2 fraud episodes, at 54.87 s).
Accounting row: own disagree, coordinator agree, lag not comparable, class agree, window disagree (measured 43.63-43.87 s), entry-reached agree. Frontend row: coordinator agree, class agree, window agree, entry-reached agree; own and lag not comparable.
Where the prediction text and the measurement differ: FNL-V1's stated reason (request.count priced 9.99 /h, so two such sensors fit 20 /h) did not hold; its price here is 15.81 /h and the set holds one sensor. FNL-V2/V3 are hits by their rule; the "reviewer's post hoc on F" g values quoted in them (42.38, 53.28) are not the ones measured (51.14, 51.06).

## What this does and does not say
- Scope: instance. n = 2 test episodes per class, one host, one rate, one SUT, one ablation run. Under the preregistered rule both off-path classes pass with no `kafka.consumer_group.lag*` sensor collected (`ablationHolds` true).
- **Confound: the ablation's block orders and onset strata are new draws (new epoch id and seed), so a difference from F or from the replicate mixes the removed receiver with the draw; one run cannot separate them.** The F-versus-replicate differences (different frozen sensor, different ledger outcomes) show that run-to-run variation exists at this n.
- The frozen `@6/T_r` set differs across F, the replicate and the ablation (one `metric:kafka:*` id each, three different ids); the PASS rests on a different sensor in each. The design does not say why the sets differ.
- Per off-path episode, the ablation set's time (6.08-11.60 s) is later than F's set in 3 of 4 episodes (accounting 4 and 5, fraud 4) and earlier in 1 (fraud 5: 6.56 s against 9.31 s); the same 3 of 4 against the replicate's set (fraud 5: 6.56 against 11.65 s). The sets are different sensors in different runs.
- `kafka.request.count` also fires in 5 of 5 frontend episodes (2 of 2 test), after the ledger (spike fires at ~6.0-6.6 s are not counted by the path filter; the counted median/run3 fires come at ~11 s and ~16 s). The FNL-V4 hit reflects the ledger firing first, not specificity of the sensor. It raised 0 alarms in the 4 held-out no-fault cells. (Corrected after review; an earlier line said this was not checked.)
- The two no-fault cells per block are siblings in leave-one-cell-out calibration (fold false-alarm estimates optimistic), as in F.
- Fresh false alarms of the ablation's own sets: 0 in 0.2 h for each; the 95 % upper bound (14.98 /h) is below the `@6/T_r` sensor's training bound (15.81 /h) and above the `@3/T_r` sensor's (9.99 /h). 0.2 h is too short to say more.
- The scorer's generated `otel-nolag.md` is headed "Campaign E test scoring" and names E's no-fault cells (labels inherited from v3.2; not edited). `fresh_fa_f.md` names F and `RESULT_F.md`; its rows are the ablation's.

## Deviations (recorded; none changed a computation)
1. **Digest table (RUN_ORDER step 0)** was run after all outputs were committed, not before the fetch: all 60 rows of `FREEZE_V35_20261015.md`'s table matched (`shasum -c`, 0 non-OK lines); `git status` shows no frozen file modified.
2. **Replay verdict read after its commit:** the replay output and the training readout, scoring readout, scorer output, lanes output, fresh-false-alarm output and predictions-scored output were each committed before being read; the commit messages say so. Only exit codes, file lists and, for the readouts, `campaignsRead` / `v32.epochsRead` counts were looked at between a run and its commit. The `ablationHolds` flag was read right after the training readout's commit and before the placement ran. The stdout logs of the scripts (`tmp/otel-f-evidence/nolag1-*.log`) were not opened.
3. **Replay command** reconstructed from `ce71bb8`'s message (F's replicate), harness `4ab4433` worktree, `uv run python -I`, 3.13, fresh `PYTHONPYCACHEPREFIX`; the Apple bytecode cache subtree of the ablation worktree (6 files) was removed first; the main repo had no subtree there. No 3.9 comparison run.
4. **Host state before the fetch** was taken from the brief (terminal on fb14srv6, attempted 25, valid 25) and from the fetch itself (read-only); no separate host check was made. The fetch took 31 min (3.7-4.8 GB tar).
5. **`score_predictions_fnl.py`** is new (RUN_ORDER step 7 names no script), adapted from `score_predictions_fr1.py` (`c7823ef`): lag lane `—` instead of a measured row, FNL-L3 `-`, one fresh-false-alarm file. Committed before it ran; no planted-defect test; no independent review. `fetch_overnight.sh` was not edited (the `otelNL1` case was already in the working copy, uncommitted).
6. **No independent review of this note or the v3.5 chain** (no judge call; the judge MCP server was not connected; no adversarial-review subagent was run). The commits carry `Co-Authored-By: Claude Sonnet 5.5` (the run order text names Opus 5.5).

## Review corrections and caveats (same-provider adversarial review, 2026-10-15; every number confirmed)
- **What this supports (instance scope):** in one ablation run with new draws, both off-path classes PASS under F's rule with no
  `kafka.consumer_group.lag*` id collected and no lag-named metric placeable. The frozen sensor is `kafka.request.count`, which also fires in every
  frontend-pause episode. This note does not say that lag is unnecessary or that a broker metric carries detection in general.
- **Not ablated:** the 5 s SDK metric export (change 1) was kept, as declared; spanmetrics flush and the second no-fault cell per block were kept too.
- **Lag metrics still collected:** three consumer-side lag metrics of frauddetectionservice (`kafka.consumer.records_lag`, `_avg`, `_max`) and the
  broker's `kafka.lag.max` are collected (as in F) but never armed ("range degenerate"), so none could be placed. The removed receiver's
  `kafka.consumer_group.*` ids appear in none of the 25 cells' `otelcol.log` (checked by string search).
- **Small gaps:** RUN_ORDER names the replay file `terminal-replay-nolag1.json`; it was written as `terminal-replay-nl1.json`. The pin entry says "no
  deviation" although the digest-table check (deviation 1) had not yet run; it later passed 60/60, and `git diff 0be6dc2 HEAD` is empty for the 60 frozen
  files. Line 38's ground-set count (4,756 sensors) and the calibration's metric-id count (389) are different populations.
- FNL-L1 is a hit by its rule while the ontology's "own lane" item disagrees for the same data (the own lane fired in the by-construction field only);
  both follow their own declared rules.

