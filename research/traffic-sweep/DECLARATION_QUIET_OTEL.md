# OTel quiet calibration run (A): declaration (FROZEN 2026-10-04, committed alone before the first cell)

Part A of `research/traffic-sweep/NEXT_CAMPAIGNS_PROPOSAL.md` on the OpenTelemetry Demo, fb14srv6. Authority: protocol
decision 48 (`research/PROTOCOL_DRAFT_20261002.md` round 10, `b6baf76`). Budget and stop rule:
`research/traffic-sweep/BUDGET_CALIBRATION.md` (`98e07bf`, committed alone before the work). Cell shape: the frozen OTel
sweep (`DECLARATION_OTEL.md` and `AMENDMENT_OTEL_1.md`, `16ae373`), whose no-fault cell this run repeats 40 times.
Every **▶** is a choice of mine that the user confirms or vetoes at freeze. Values without ▶ are the sweep's frozen
values, copied by construction (the compiler reads them from the sweep's compiler). Scope of every number: instance (one
SUT, one host).

## Binding (filled at freeze)
| item | value |
|---|---|
| harness | worktree `observability-placement-runtime-otel-protocol`, branch `otel-protocol-20261002`: epoch commit `36d2e15`, governance re-pin `fb02804` (both committed); activation commit `6e37ec248a5a68db7db14e15c1e1ce995b9d8ca2`, **built and dry-run in a scratch clone only**, not yet in the worktree (see "Activation") |
| epoch | `otel-quiet-calibration-v1`, selected by the committed selector `modules/otel-demo/execution/study-epoch.json` plus the tombstone edit (`ADMITTED_STUDY_EPOCHS = ("otel-quiet-calibration-v1",)` in `candidate_setup.py` and `candidate_remote.py`) |
| compiler | `modules/otel-demo/execution/candidate_quiet.py`; reads `candidate_sweep.py` and the sweep descriptor, both digest-bound as controllers `sweep-compiler` and `sweep-descriptor` (19 bound controllers) |
| descriptor | `pipelines/campaigns/otel-quiet-calibration-v1.json`, canonical sha256 `02c2d90e39e448f77025de55a0377cb2a65aafc4d2a42c5177a5ec7ce3e6777d` (generated from the sweep descriptor `be5b0b4d…c86d`; regenerate, never hand-edit) |
| plan | attempt 1: canonical sha256 `5cec5a6966fb7f5998b34ca3ab2c6ac5223ec8ecb52a6425697f9a3f8cd87b58`, 40 cells; identical under `/usr/bin/python3 -I` (3.9.6, fresh `-X pycache_prefix`) and `uv run python -I` (3.13.12) |
| sweep epoch | unchanged: descriptor `be5b0b4d…c86d`, attempt-1 plan `09b2563a…4865`, attempt-2 plan `fa770ccf…9498`; `candidate_sweep.py` and its descriptor byte-identical to `c532853` (tested) |
| host | fb14srv6 only; GATE-RUN window 6 h (derived), minimum remaining at first mutation 14,740 s (derived), launcher watcher cap 7 h |
| analysis | none until analysis v2 is frozen (see "Analysis") |

## Purpose
False-alarm calibration (decision 48). With 0 alarms in T hours of quiet time, the one-sided 95 % upper bound on a
Poisson alarm rate is −ln(0.05) / T ≈ 3 / T per hour. Today a rate has about 12 min of no-fault time, so ≤ 15/h is the
tightest bound available (decision 33). This run adds 10 no-fault cells per rate, 10 × 180 s = **30 min of quiet time per
rate**, so a detector with 0 alarms on it is certified at **≤ 6/h at that rate**. The bound is per detector and per rate.
With k > 0 alarms the bound is wider (Poisson upper limit for k). The run measures no fault effect and makes no claim about
detection.

## Design
- **No fault in any cell.** 40 cells = **10 blocks × 4 rates** (10, 1, 0.2, 0.05 /s). Regime `no-fault-calibration`
  only. Every cell is the sweep's no-fault cell: `candidate_quiet.cell_timing` takes `candidate_sweep.cell_timing(
  "no-fault-calibration", rate, 1)` and replaces only five keys: the pseudo window's onset offset, onset and scored window,
  and the plan-level run count and minimum remaining time (tested key by key).
- From the sweep, unchanged:
  - route `GET /api/products/66VCHSJNUP` through `frontendproxy` → `frontend` → `productcatalogservice`;
  - open loop, constant spacing from the shared barrier; offered = rate × 180 (1800, 180, 36, 9);
  - client timeout 15 s; concurrency 300;
  - upstream `loadgenerator` removed right after `compose up`, before readiness (absence proven per cell by the engine);
  - stack readiness (one checkout journey) and one route 200, then a 30 s warm-up at 10/s on the route, then 180 s of
    measurement;
  - posture `full` only; cold start per cell (`down -v`);
  - frontendproxy memory limit 256 MiB (declared deviation from upstream's 50M, `AMENDMENT_OTEL_1.md`);
  - the same captures (see "Measures").
- ▶ **Pseudo window.** Every cell carries the window [onset, onset + 60 s], onset = 60 s + a seeded offset. This is the
  sweep's stratified rule, here with **10 strata per rate**: each rate's 10 onsets fall one in each tenth of its
  inter-arrival (10/s: 0.001-0.096 s; 1/s: 0.075-0.928 s; 0.2/s: 0.03-4.53 s; 0.05/s: 1.7-18.9 s). It keys G1/G2 and
  false alarms at the same onset phase. No fault command runs, so there are no probes and no `intervention.json`.
- ▶ **Order.** Each block holds every rate once, in a Fisher-Yates order drawn by SHA-256 from **seed 20261004** (the
  sweep's draw encoding; no lead cell). The same seed keys the onsets. Seed and orders are recorded in the descriptor
  (`schedule`) and in the compiled plan (`schedule.blockOrders`). Blocking spreads every rate evenly over the ~3.5 h run,
  so slow host drift falls on all rates alike. The alternative, one shuffle over all 40 cells, does not guarantee that.
  Run order (rate, onset offset in s):

  | block | 1 | 2 | 3 | 4 |
  |---|---|---|---|---|
  | 1 | 0.2 (+0.974) | 1 (+0.540) | 10 (+0.065) | 0.05 (+15.866) |
  | 2 | 0.2 (+3.750) | 1 (+0.324) | 0.05 (+8.278) | 10 (+0.053) |
  | 3 | 1 (+0.630) | 0.2 (+1.609) | 0.05 (+16.955) | 10 (+0.044) |
  | 4 | 10 (+0.023) | 0.2 (+2.427) | 0.05 (+11.794) | 1 (+0.483) |
  | 5 | 1 (+0.075) | 0.05 (+12.556) | 10 (+0.001) | 0.2 (+3.070) |
  | 6 | 1 (+0.738) | 0.05 (+18.891) | 10 (+0.096) | 0.2 (+4.406) |
  | 7 | 0.05 (+7.804) | 10 (+0.087) | 0.2 (+1.063) | 1 (+0.824) |
  | 8 | 1 (+0.195) | 0.2 (+4.529) | 0.05 (+3.876) | 10 (+0.075) |
  | 9 | 0.2 (+0.027) | 0.05 (+1.674) | 1 (+0.928) | 10 (+0.039) |
  | 10 | 0.2 (+2.781) | 10 (+0.010) | 0.05 (+4.272) | 1 (+0.235) |
- ▶ **A separate epoch**, not a new attempt of the sweep. Run identity is unchanged in form (first 24 hex of the runKey's
  sha256; the runKey carries `studyEpoch`), so no run ID can collide with the sweep's. The sweep's descriptor, plans,
  admission history and spent attempts stay as they are.
- Metric export interval unchanged (SDK default, 60 s observed), as in the sweep.

## Measures (per cell, as the sweep's no-fault cells)
- `request-ledger.json`: one row per scheduled request, with planned offset, start and end on the barrier's monotonic
  clock, status and outcome (ok / timeout / failed).
- `otelcol.log`: the collector's debug exporter, carrying traces, metrics and logs; unrotated, raw bytes.
- `application.log`: `docker compose logs --timestamps` of every started application service except the collector.
- Proxy access log: the application witness.
- OTLP bytes by tcpdump/tshark.
- Docker-engine CPU before and after the window (diagnostic).
- `trace-completeness.json`, `container-health.json`, `protocol-gates.json`, `upstream-generator.json`,
  `posture-proof.json`, `resources.json`, `cell-cleanup.json`, `content-manifest.json`.
- Quiet time per rate: 10 × 180 s of measurement window. ▶ Whether the analysis counts the whole 180 s, or only part of
  it (for example after the warm-up's tail, or outside the pseudo window), is analysis v2's choice. It changes T and
  so the certified bound (open question 1).

## Gates and stop rules
- **Blocking per cell, evaluated on the target before the next cell** (vendored `protocol_gates.py`, byte-identical to
  `d3fc741`): **G1, G2, G4**. F1 applies to fault cells only, and this run has none. The terminal validator replays the
  gates byte for byte. P0, R1 and R2 are not evaluated, as in the sweep.
- G2 at 0.05/s stays strict: 3-4 requests precede the pseudo onset, and one failure among them fails the cell (decision
  21).
- **Trace completeness (decision 25), no-fault cells:** one window, whole measurement. The cell is blocked if more than
  max(1, floor(0.01 × successful requests)) successful requests lack the complete 3-service trace: 18 of 1,800 at 10/s,
  1 at the other rates. Every incomplete trace is counted in `trace-completeness.json`.
- **Container-health guard** (`AMENDMENT_OTEL_1.md`): the cell is invalid if any container was OOM-killed, an application
  container restarted, was replaced or disappeared, or the 256 MiB proxy limit is not in effect.
- The terminal validator also checks the ledger, the witness, the generator's absence, the posture and the application
  log.
- **The campaign stops on the first invalid cell.**
- Budget (`BUDGET_CALIBRATION.md`):
  - launch-ready by 2026-10-05 12:00Z;
  - terminal by 2026-10-06 12:00Z;
  - at most 2 relaunches;
  - 30 min per critical-path defect;
  - 3 critical-path harness defects stop OTel's part A and go to the user.
- **Wall time.** Relaunch 1 measured a cell period of 302.7-314.9 s (mean 309.6 s, 11 consecutive barrier gaps;
  instance). That projects to ≈ 3.4 h for 40 cells, plus ~5 min for install and authorization before the first cell. The
  compiled estimate is 331 s per cell, 3.7 h.
- **GATE-RUN window and watcher cap.** The window is 6 h = ceil((40 × 331 + 900 + 600 + 3,600) / 3,600). The controller
  refuses a cell within 900 s of the deadline, so the last cell must start by ~5.75 h after approval, which leaves ≥ 2 h
  of slack. The watcher cap is 7 h.

## Analysis
- **No analysis of this run's evidence until analysis v2 is frozen** (`BUDGET_CALIBRATION.md` stop rule 4;
  `research/protocol/METHODOLOGY_HARDENING.md` §4). Until then only the harness's validity record is read: receipts,
  gates, the terminal validation and the fetch manifest.
- Analysis v2 fixes before any look:
  - the detectors and their common operating point (H7);
  - what counts as quiet time;
  - whether quiet cells from other runs are pooled (open question 2).

## Monitoring (not evidence)
High-level progress is mirrored to wandb (`tools/wandb_campaign.py`). The evidence of record is the fetched campaign
directory.

## Activation (to do before the launch; this draft did not do it)
The activation edit is ready but **not in the worktree**. The permission classifier refused editing the selector and
tombstone in the shared OTel worktree ("Modify Shared Resources"), so it was made in a private scratch clone instead.
- Commit `6e37ec248a5a68db7db14e15c1e1ce995b9d8ca2`; parent `fb02804`, the worktree's HEAD.
- It changes:
  - selector → `otel-quiet-calibration-v1`;
  - tombstone `("otel-quiet-calibration-v1",)` in `candidate_setup.py` and `candidate_remote.py`;
  - the ledger text;
  - two test adjustments.
- No governance-bound file moves.

It needs the user's go. Then, from the measurement repo:

```
S=/private/tmp/claude-502/-Users-fhuebscher-Desktop-ma-thesis-oltp-submodularity-evaluation-observability-placement/70ef7069-de5b-4b65-a510-310d1fa1a1a1/scratchpad/quiet
git -C ../observability-placement-runtime-otel-protocol fetch $S/otel-clone otel-quiet-activation-scratch
git -C ../observability-placement-runtime-otel-protocol merge --ff-only 6e37ec248a5a68db7db14e15c1e1ce995b9d8ca2
```

Use `git am $S/activation.patch` instead if the clone is gone. That gives a different commit hash, so use the new hash
below.

## Launch (after: the activation above, this declaration frozen and committed alone, and a passing DRY_RUN in the worktree)
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
DRY_RUN=1 OTEL_CANDIDATE_ATTEMPT=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_quiet.py EXPECTED_PLAN=5cec5a6966fb7f5998b34ca3ab2c6ac5223ec8ecb52a6425697f9a3f8cd87b58 \
  RUN_COUNT=40 CAMPAIGN=otel-quiet-calibration-v1 LOG_PREFIX=otel-quiet \
  zsh scratchpad/gate-drivers/launch_otel_offpath.sh quietdry2 6e37ec248a5a68db7db14e15c1e1ce995b9d8ca2
LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_quiet.py EXPECTED_PLAN=5cec5a6966fb7f5998b34ca3ab2c6ac5223ec8ecb52a6425697f9a3f8cd87b58 \
  RUN_COUNT=40 CAMPAIGN=otel-quiet-calibration-v1 LOG_PREFIX=otel-quiet \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh quiet1 6e37ec248a5a68db7db14e15c1e1ce995b9d8ca2 \
  > scratchpad/gate-drivers/otel-quiet1.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow otel-quiet1 scratchpad/gate-drivers/otel-quiet-quiet1-launch.log \
  > scratchpad/gate-drivers/otel-quiet1-wandb.out 2>&1 &
```
What the non-dry launcher does before the first mutation:
- archives the sweep's run-phase state left in the worktree's `.local/…/gates` (`gate_run.py archive-run`; archive,
  never delete) and moves the sweep's plan dir aside;
- renews SETUP-CAMPAIGN onto `5cec5a69…` (today's authorization is bound to the sweep's `fa770ccf…`).

The sweep's relaunch 1 is already terminal-validated locally (`tmp/otel-sweep-evidence/relaunch1-fetch/terminal-validation.json`).
Any later replay of the sweep must run at `c532853`, because after activation the worktree's selector names the quiet
epoch.

Host paths (checked read-only on fb14srv6, 2026-10-04 08:04Z):
- The quiet epoch uses `…-runs/otel-quiet-calibration-v1`, `…-runs/.setup-otel-quiet-calibration-v1`,
  `…-otel-srv6/otel-quiet-calibration-v1-<commit12>` and Compose project `otel_candidate_v4_otel_quiet_calibration_v1`.
- None of these exists on srv6. None collides with the sweep's relaunch-1 paths, which are still in place and do not
  need moving for this launch: `…-runs/otel-traffic-sweep-v1`, `…-runs/.setup-otel-traffic-sweep-v1`,
  `…-otel-srv6/otel-traffic-sweep-v1-c5328531b94e`.
- The materialized-source digest is the sweep's (`b5f3fc41…`), so the install builds the same image tags the sweep
  used.

## Checks done (2026-10-04; commands in the build report)
- **Worktree suite** (`uv run pytest -q -p no:cacheprovider -rA --ignore=tests/test_mlflow_manifest.py`):

  | commit | failed | passed | skipped |
  |---|---|---|---|
  | baseline `c532853` | 29 | 2038 | 145 |
  | `fb02804` (worktree HEAD) | 29 | 2060 | 145 |
  | activation `6e37ec2` (scratch clone) | 29 | 2060 | 145 |

  - The 29 failures are the same by name in all three runs: Hotel materialize, Kieker fixture, Online Boutique,
    phase-1 control universe, science router, TeaStore. None is OTel.
  - The +22 passed are `tests/test_otel_quiet_calibration.py`.
- **Measurement repo** `uv run pytest -q`: 956 → 957 passed, 1 skipped, 3 xfailed. The +1 is `test_unbound_names` for
  `otel-demo/candidate_quiet.py`.
- **Planted defects** (scratch clone, one at a time, file restored and sha256 re-checked): 10 of 10 made their named test
  fail. The plants were:
  - blocks 10 → 9;
  - order seed + 1;
  - onset strata collapsed;
  - concurrency 32 in the cell shape;
  - one byte in `candidate_sweep.py`;
  - the sweep's seed;
  - the quiet epoch dropped from the remote's timed epochs;
  - `sweep-descriptor` dropped from the setup controller set;
  - a planted spent attempt;
  - the approval slack dropped from the window.
- **Launcher DRY_RUN** against the scratch clone at `6e37ec2`
  (`scratchpad/gate-drivers/otel-quiet-quietclonedry1-launch.log`):
  - compiled `otel-quiet-calibration-v1 40 5cec5a69…`;
  - drivers `otel-quiet-calibration-v1 otel-quiet-calibration-v1 6`;
  - probe receipt PROBE OK;
  - `host fb14srv6: running units=0 containers=0 lease holders=[] free GB=248 otel-quiet-calibration-v1 paths=0`;
  - `08:08:56Z DRY RUN: all guards passed`, exit 0.

  It must be repeated in the worktree after the activation.
- **Offline GATE-PLAN derivation** on the clone (no remote action): 40 runs, 19 bound controllers, materialized source
  `b5f3fc41…`, sentence `… runs=40 attempt=1 one-shot …`.

## Open questions for the user (▶ = preregistration class)
1. ▶ What counts as quiet time T: the whole 180 s window of every cell (30 min per rate), or less. This is analysis v2's
   choice, and the certified bound is 3 / T.
2. ▶ Pooling: the proposal says quiet cells from B (and the sweep's 4 no-fault cells) "add to these totals". Pool them for
   the bound, or certify on this run alone? Pooled cells differ in harness (B: H10/H4) and in schedule position.
3. ▶ Per-block order (as drafted) vs one shuffle over all 40.
4. ▶ Seed 20261004 for order and onsets; 10 onset strata per rate.
5. **The freeze must use the file name `research/traffic-sweep/DECLARATION_QUIET_OTEL.md`.** The pinned descriptor's
   `declaration` field and the ledger text name that path. Any other name, or any change to a design value, means a
   regenerated descriptor, new digests and a new DRY_RUN.
6. Not done here, so that nothing of the sweep epoch changed: the sweep's relaunch 1 (attempt 2, terminal-valid
   12/12) is **not** in `SPENT_ATTEMPTS_BY_EPOCH["otel-traffic-sweep-v1"]` (`candidate_runtime_adapter.py`). That dict's
   own rule asks for it. Today the launcher's host-path guard is the only barrier to a colliding sweep re-run. Adding it
   is a governed edit plus a re-pin; the coordinator decides.
7. Engineering defaults recorded:
   - cell period estimate 331 s (the sweep's, above every measured period);
   - approval slack 3,600 s;
   - window 6 h; watcher cap 7 h;
   - per-cell deadline reserve 900 s; cleanup reserve 600 s.

## Resolutions at freeze (coordinator, 2026-10-04)
Activation: the user approved fast-forwarding the OTel worktree to `6e37ec2` after the classifier refused the agent's edit.
1. **Quiet time T** is decided by H2 (decision 33, round 9 item 42): the whole 180 s measurement window of every held-out
   no-fault cell, slid over, warm-up and probe windows excluded.
2. **Pooling** is decided by H1 (decision 31): all fault-free time per system × rate, which includes the sweep's no-fault
   cells and B's.
3. **Order** is an engineering default, kept per-block (randomised complete blocks, which balance drift over the run).
   Hotel's quiet run uses one shuffle over all 40 (`DECLARATION_QUIET_HOTEL.md`). Both are seeded and recorded; the
   difference is noted, not harmonised.
4. **Seed 20261004 and 10 onset strata per rate** are engineering defaults, to be recorded in `research/protocol/parameters.json`.
5. The sweep's spent-attempt record (review finding 1) is left unchanged here; it is a governed edit for a later sweep
   relaunch.
