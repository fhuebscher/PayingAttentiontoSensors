# TeaStore quiet calibration run (A): declaration (FROZEN 2026-10-04, committed alone before the first cell)

Part A of `research/traffic-sweep/NEXT_CAMPAIGNS_PROPOSAL.md` on TeaStore, fb14srv5. Authority: protocol decision 48
(`research/PROTOCOL_DRAFT_20261002.md` round 10, `b6baf76`). Budget and stop rule:
`research/traffic-sweep/BUDGET_CALIBRATION.md` (`98e07bf`, committed alone before the work). Cell shape: the frozen
TeaStore sweep (`DECLARATION_TEASTORE.md` `c9f072b`, `AMENDMENT_TEASTORE_1.md` `bbbd80b`, `AMENDMENT_TEASTORE_2.md`
`b840353`), whose no-fault cell this run repeats 40 times. Templates: `DECLARATION_QUIET_HOTEL.md` and
`DECLARATION_QUIET_OTEL.md`. Every **▶** is a choice of mine that the user confirms or vetoes at freeze. Values without
▶ are the sweep's frozen values, copied by construction (the compiler reads them from the sweep's compiler). Scope of
every number: instance (one SUT, one host).

## Binding (filled at freeze)
| item | value |
|---|---|
| harness | worktree `observability-placement-runtime-teastore-protocol`, branch `teastore-protocol-20261002`: epoch commit `3c8cc03` (`3c8cc034093e862901162a8e77b6132d6f4db8c5`), activation `d0a5953` (`d0a59535169305f24628ed6fe5272b30a121e8e6`) and the review's test-only commit **`91c4967` (`91c4967f2d9c12a25eeeaf097f998856c377ca7f`, the HEAD to launch)**, all committed in the worktree, on `0588a41` (the harness of sweep relaunch 2) |
| epoch | `teastore-quiet-calibration-v1`, selected by the committed selector `modules/teastore/execution/study-epoch.json`. TeaStore has no separate tombstone or admission list: `study_epoch.py` accepts exactly two selector documents (sweep, quiet) and refuses anything else, so the selector is the activation |
| compiler | `modules/teastore/execution/candidate_quiet.py`; it reads `candidate_sweep.py` and the sweep descriptor, both digest-bound (controllers `sweep-compiler` and `sweep-descriptor`, beside `quiet-descriptor` and `candidate-compiler`; 56 bound controllers, the sweep had 54) |
| descriptor | `pipelines/campaigns/teastore-quiet-calibration-v1.json`, canonical sha256 `338226d05f8e9d3557918ef9120727094bd71532f4eba72cc9191070f102315b`, file sha256 `ce87db3c…65e1` (generated from the pinned sweep descriptor `f90bd64c…160a`; regenerate, never hand-edit) |
| plan | canonical sha256 `879a81ab0c3f2e960ee11a282c8200e58b98e97bc8a541cbcc5704654f858266`, 40 cells; identical under `/usr/bin/python3 -I` (3.9.6, fresh `-X pycache_prefix`) and `uv run python -I` (3.13.12). Plan directory `.local/candidate-v4/teastore/plan-ce87db3c` (gitignored), campaign manifest sha256 `faf4e523…0e0c`, the same bytes under 3.9 and 3.13 |
| sweep epoch | unchanged: descriptor `f90bd64c…160a`, plan `88a3017a…9355`; `candidate_sweep.py`, its descriptor and every other harness file but three byte-identical to `0588a41` (tested; see "Checks done") |
| host | fb14srv5 only (TeaStore's lineage-bound host); GATE-RUN window 7 h (derived), minimum remaining at first mutation 21,300 s (derived), launcher watcher cap 8 h |
| analysis | none until analysis v2 is frozen (see "Analysis") |

## Purpose
False-alarm calibration (decision 48). With 0 alarms in T hours of quiet time, the one-sided 95 % upper bound on a
Poisson alarm rate is −ln(0.05) / T ≈ 3 / T per hour. Today a rate has about 12 min of no-fault time, so ≤ 15/h is the
tightest bound available (decision 33). This run adds 10 no-fault cells per rate, 10 × 180 s = **30 min of quiet time
per rate**, so a detector with 0 alarms on it is certified at **≤ 6/h at that rate**. The bound is per detector and per
rate. With k > 0 alarms the bound is wider (Poisson upper limit for k). The run measures no fault effect and makes no
claim about detection.

## Design
- **No fault in any cell.** 40 cells = **10 blocks × 4 rates** (10, 1, 0.2, 0.05 login journeys/s). The regime is the
  sweep's no-fault regime `no-fault-cost` only, so every regime-keyed reader stays unchanged: the frozen no-fault code
  path with the docker-stats performance probe (`resources.json`), the terminal's required artifacts.
- **Every cell is the sweep's no-fault cell.** `candidate_quiet.cell_timing` takes
  `candidate_sweep.cell_timing(<the sweep's no-fault run ID at that rate>, "no-fault-cost", rate)` and replaces only
  three keys: `faultOnsetPhaseOffsetSeconds`, `faultOnsetSeconds`, `scoredWindowSeconds` (tested key by key against the
  sweep's own function). From the sweep, unchanged:
  - route `POST /tools.descartes.teastore.webui/loginAction`, the 302 to `/` followed, one login per journey, workload
    `login-only-v1`;
  - open loop from the shared barrier; offered = rate × 180 (1800, 180, 36, 9);
  - client timeout 15 s; concurrency 240;
  - warm-up 30 s at 10/s on the same route, untokenised; then 180 s of measurement;
  - posture `full` only; cold start per cell;
  - the captures (see "Measures"), the system sampler (5 s, 37 samples);
  - no drain allowance (Q3 applies to fault cells only), decision 25's journey-unit trace-completeness rule, and the
    narrowed JVM-frame rule of the witness-log secret scan (`0588a41`).
- ▶ **Pseudo window.** Every cell carries the window [onset, onset + 60 s], onset = 60 s + a seeded offset. This is
  the sweep's stratified rule (`onset_phase_offset`), here with this epoch's name, seed and run IDs and **10 strata per
  rate**: each rate's 10 onsets fall one in each tenth of its inter-arrival (offsets 10/s: 0.003-0.095 s; 1/s:
  0.030-0.974 s; 0.2/s: 0.443-4.583 s; 0.05/s: 0.369-18.541 s). Given the sweep's seed, epoch and stratum count the
  function reproduces the sweep's own 12 offsets (tested). No fault command runs, so there is no `intervention.json`
  and no readiness probe.
- ▶ **Order.** Each block holds every rate once, in a Fisher-Yates order drawn by SHA-256 from **seed 20261004** (the
  sweep's draw encoding with schedule version `quiet-schedule-v1`; no lead cell). The same seed keys the onsets. The
  seed and the draw encoding are recorded in the descriptor (`schedule`), every block's run-ID order in the descriptor
  (`schedule.blocks`) and in the compiled plan (`blocks[].order`, `orderSha256`); a test recomputes the order from the
  recorded encoding without the compiler. Blocking spreads every rate evenly over the ~3.8 h run, so slow host drift
  falls on all rates alike. Run order (rate, onset offset in s):

  | block | 1 | 2 | 3 | 4 |
  |---|---|---|---|---|
  | 1 | 0.05 (+0.369) | 10 (+0.069) | 0.2 (+4.583) | 1 (+0.777) |
  | 2 | 0.05 (+2.568) | 10 (+0.021) | 0.2 (+0.817) | 1 (+0.162) |
  | 3 | 0.05 (+9.880) | 10 (+0.039) | 1 (+0.512) | 0.2 (+3.562) |
  | 4 | 0.05 (+15.441) | 10 (+0.041) | 1 (+0.373) | 0.2 (+3.092) |
  | 5 | 1 (+0.823) | 0.05 (+11.414) | 0.2 (+2.127) | 10 (+0.057) |
  | 6 | 1 (+0.229) | 0.2 (+0.443) | 0.05 (+6.418) | 10 (+0.090) |
  | 7 | 0.05 (+5.528) | 10 (+0.095) | 1 (+0.477) | 0.2 (+1.744) |
  | 8 | 0.2 (+2.842) | 10 (+0.019) | 1 (+0.030) | 0.05 (+12.514) |
  | 9 | 0.05 (+18.541) | 0.2 (+4.259) | 10 (+0.080) | 1 (+0.643) |
  | 10 | 10 (+0.003) | 0.2 (+1.182) | 1 (+0.974) | 0.05 (+16.015) |

  The 0.05/s cell is first in 6 of the 10 blocks. That is the seeded draw, not a rule.
- ▶ **A separate epoch**, not a new attempt of the sweep. Run IDs have the sweep's shape with this epoch's name,
  `teastore-quiet-calibration-v1/no-fault-cost/r<rate>/b01…b10/full/a01`, so no run ID can equal a sweep run ID (tested).
  Campaign paths are `runs/no-fault-cost/b<NN>-<ordinal>-full`. *Engineering default:* compiled artifact roots keep the
  sweep's form, `cost/r<rate>/block-<NN>/full/attempt-01`, so block 01's four roots are the same strings as the sweep's
  four no-fault roots. Within one campaign they are unique (40 of 40); across epochs they are told apart by the
  campaign ID and the results root (a new setup ID per launch). Any pooling must key on the campaign ID.
- The sweep's descriptor, plans, setup history and archived run state stay as they are.

## Measures (per cell, as the sweep's no-fault cells)
- `journey-ledger.plan.json` and `journey-ledger.jsonl`: one row per scheduled login, with planned offset, start and end
  on the barrier's monotonic clock, outcome and status; hash-chained, with a reconciliation row.
- `application.log`: `docker compose logs --timestamps --no-color` of every service, kept as raw bytes.
- `auth.log` and `persistence.log` (the bounded witness logs), `app-witness.jsonl`, the native-token correlation.
- Kieker: the AMQP spool (`kieker-amqp.spool`) and `traces.json`; `queue-proof.json`, `capture-terminal.json`.
- `system-samples.json` (cgroup v2, every 5 s, 37 samples) and `resources.json` (the docker-stats performance probe of
  the no-fault path).
- `posture-proof.json`, `runtime-images.json`, `service-log-capture.json`, `candidate-validation.json` (with
  `traceCompleteness` and `protocolGates`), `content-manifest.json`, `cell-cleanup.json`.
- Quiet time per rate: 10 × 180 s of measurement window. ▶ What counts as quiet time is analysis v2's choice (open
  question 1).

## Gates and stop rules
- **Blocking per cell, evaluated on the target before the next cell** (vendored `protocol_gates.py`, byte-identical to
  the measurement repo's): **G1, G2, G4**. F1 applies to fault cells only, and this run has none. P0, R1 and R2 are not
  evaluated, as in the sweep. The terminal validator replays every cell.
- **G2 at the two lowest rates stays strict** (decision 21): 4 logins precede the pseudo onset in every 0.05/s cell and
  13 in every 0.2/s cell, so one failure among them fails the cell.
- **Zero failures in a no-fault cell** (the frozen TeaStore validator's `no-fault-workload-context` rule, stricter than
  G2's 5 %): one failed or timed-out login anywhere in the 180 s blocks the cell, at 10/s 1 of 1,800. There is no drain
  allowance in no-fault cells. Across the sweep's three launches (attempt 1, relaunch 1, relaunch 2), all 12 no-fault
  cells were valid (instance; 12 is too few to bound the per-cell rate tightly).
- **Trace completeness (decision 25), no-fault cells:** one window, `whole-measurement`. The cell blocks if more than
  max(1, floor(0.01 × successful journeys)) journeys have an incomplete trace: 18 of 1,800 at 10/s, 1 at the other rates.
  Unattributable defective traces count one journey each. Every incomplete journey is recorded in
  `candidate-validation.json`.
- **Witness-log secret scan:** fail-closed, with the sweep's narrowed JVM-frame rule (`0588a41`); a non-frame line whose
  key embeds a secret name still blocks (amendment 2's residual risk; seen in 0 of 312 retained logs).
- The validator's integrity checks run first, as in the sweep: ledger chain and plan replay, witness and native-token
  correlation, posture, queue and capture reconciliation, system samples, `application.log` timestamps per service.
- **The campaign stops on the first invalid cell** (controller behaviour).
- Budget (`BUDGET_CALIBRATION.md`):
  - launch-ready by 2026-10-05 12:00Z;
  - terminal by 2026-10-06 12:00Z;
  - at most 2 relaunches;
  - 30 min per critical-path defect;
  - 3 critical-path harness defects stop TeaStore's part A and go to the user.
- **Wall time.** Sweep relaunch 2 (fb14srv5, 2026-10-04) measured a cell period of 324.9-423.4 s (median 330.5, mean
  343.2; 11 consecutive runtime-journal `recordedAt` gaps, read from the host's journal, timestamps only; instance). That
  projects to ≈ 3.7 h (median) to 3.8 h (mean) for 40 cells, ≤ 4.7 h if every cell took the slowest period, plus ~11 min
  for install and authorization (relaunch 2: `auto` 07:36:12Z, `oneshot` 07:47:38Z) and ~6 min to the first journal row.
  The compiled estimate is the sweep's 525 s per cell (225 s timed + 300 s overhead), 5.8 h.
- **GATE-RUN window and watcher cap.** The sweep's rule: minimum remaining at first mutation = 40 × 525 + 300 = 21,300 s;
  window = ceil((21,300 + 1,800) / 3,600) = **7 h**. The controller starts no cell once the deadline minus the 300 s
  cleanup reserve has passed; at the slowest measured period the last cell starts ~4.6 h (39 × 423.4 s) after the first. The launcher's watcher cap
  is window + 1 = **8 h**.

## Analysis
- **No analysis of this run's evidence until analysis v2 is frozen** (`BUDGET_CALIBRATION.md` stop rule 4;
  `research/protocol/METHODOLOGY_HARDENING.md` §4). Until then only the harness's validity record is read: the runtime
  journal, cell validity, the terminal validation and the fetch manifest.
- Analysis v2 fixes before any look:
  - the detectors and their common operating point (H7);
  - what counts as quiet time;
  - whether quiet cells from other runs are pooled (open question 2).

## Monitoring (not evidence)
High-level progress is mirrored to wandb (`tools/wandb_campaign.py follow`). The evidence of record is the fetched
campaign directory.

## Activation (done in the worktree; nothing else to apply)
The activation commit `d0a5953` is in the worktree (no edit was refused by the permission classifier), followed by
the test-only commit `91c4967` (review A1). The plan directory `.local/candidate-v4/teastore/plan-ce87db3c` was
materialized under `/usr/bin/python3 -I` (gitignored). The activation changes:
- the selector → `{"schemaVersion": 1, "studyEpoch": "teastore-quiet-calibration-v1"}`;
- the extension ledger text for the selector;
- `tests/conftest.py`: the skip reason names the selected epoch, and with the quiet selector 14 effect-cell tests
  (18 node ids) are skipped (see "Checks done").

Any later replay or relaunch of the sweep must run at `0588a41` or `3c8cc03` (or with the selector set back), because
the worktree's selector now names the quiet epoch.

## Launch (after: this declaration frozen as `DECLARATION_QUIET_TEASTORE.md` and committed alone, and a passing DRY_RUN)
From the measurement repo:
```
W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
cd $M
DRY_RUN=1 TEASTORE_ROOT=$W EXPECTED_HEAD=91c4967f2d9c12a25eeeaf097f998856c377ca7f TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_quiet.py EXPECTED_PLAN=879a81ab0c3f2e960ee11a282c8200e58b98e97bc8a541cbcc5704654f858266 RUN_COUNT=40 \
  zsh scratchpad/gate-drivers/launch_teastore.sh quietdry3
TEASTORE_ROOT=$W EXPECTED_HEAD=91c4967f2d9c12a25eeeaf097f998856c377ca7f TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_quiet.py EXPECTED_PLAN=879a81ab0c3f2e960ee11a282c8200e58b98e97bc8a541cbcc5704654f858266 RUN_COUNT=40 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh quiet1 > $M/scratchpad/gate-drivers/teastore-quiet1.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow teastore-quiet1 scratchpad/gate-drivers/teastore-quiet1-launch.log \
  > scratchpad/gate-drivers/teastore-quiet1-wandb.out 2>&1 &
```
What the non-dry launcher does before the first mutation:
- reads the previous campaign's status from the worktree's live runtime package (sweep relaunch 2: `state=complete
  terminal=True`, rc 3);
- moves relaunch 2's run state in `.local/candidate-v4/teastore/gates` (`run-authorization.json`,
  `runtime-package.json`, `gate-run.json`, `campaign-terminal.json`) into `gates/run-state-before-quiet1-<stamp>`
  (move, never delete; relaunch 2 is already fetched and byte-verified, `70fe0df`);
- `auto` re-derives SETUP-CAMPAIGN onto plan `879a81ab…` (today's authorization is bound to the sweep's plan
  `88a3017a…`, so its invariants do not match), recorded as auto-derived; it archives the previous setup documents into
  `gates/attempt-<stamp>-91c4967f`;
- `auto` mints a new setup ID, so the results root on srv5 is new.

After terminal: fetch to a new path under `tmp/`, byte-verify against the host, check cell validity only (the
procedure used for relaunch 2, `70fe0df`).

Host paths (checked read-only on fb14srv5, 2026-10-04 ~09:42Z; nothing was moved):
- The quiet epoch uses `…/candidate-v4/teastore/results/<new setup ID>/teastore-quiet-calibration-v1`, a new
  `…/releases/<setup ID>-…`, the lease `…/leases/host-exclusive.lock` and the Compose project
  `teastore_candidate_46a023456d95cf24`.
- No `teastore-quiet-calibration-v1` directory exists under any of the 96 results roots. The sweep's 3 campaign
  directories (attempt 1, relaunch 1, relaunch 2) stay in their own results roots and need no moving.
- The lease file exists and no process holds it. The quiet and the sweep Compose projects have 0 containers, 0 volumes
  and 0 networks; there are 0 `teastore_candidate` containers in any state and 0 active `teastore-candidate-v4-*` units
  (6 inactive). 364 GB free.

## Checks done (2026-10-04)
- **Worktree suite** (`uv run pytest -q -p no:cacheprovider --ignore tests/test_mlflow_manifest.py -rf`):

  | commit | selector | failed | passed | skipped |
  |---|---|---|---|---|
  | baseline `0588a41` | sweep | 20 | 1822 | 162 |
  | `3c8cc03` (epoch) | sweep | 20 | 1868 | 162 |
  | `d0a5953` (activation) | quiet | 20 | 1852 | 180 |
  | `91c4967` (review twins) | quiet | 20 | 1858 | 180 |

  - The 20 failures are the same by name in all three runs (`comm` of the sorted FAILED lines): Hotel materialize ×4,
    OB-LGTM ×12, OB ×1, openspec ×1, OTel materialize ×1, science-epoch router ×1. None is TeaStore.
  - +46 passed = `tests/test_teastore_quiet_calibration.py`.
  - At `d0a5953`: 18 node ids (14 tests in `test_candidate_pilot_evidence.py`, `test_teastore_app_witness.py`,
    `test_native_token_correlation.py`) are skipped. They build `auth-freeze-effect` cells against the tree's active
    epoch, which under the quiet selector has no fault regime (`KeyError: 'auth-freeze-effect'`, "run receipt has an
    unknown regime"). The skip list is the exact set that failed with the quiet selector written in before the
    activation commit; each passes at `3c8cc03` under the sweep selector. The sweep's effect cells stay covered in sweep
    tree copies (`test_teastore_traffic_sweep.py`, 126 passed with the quiet selector committed).
  - +2 collected at `d0a5953`: the controller-digest drift test's parameters for `sweep-compiler` and
    `quiet-descriptor`, both passing. 1868 − 18 + 2 = 1852.
  - +6 at `91c4967`: the quiet-cell twins of two skipped generic-rule tests (review finding A1, below).
- **Measurement repo** `uv run pytest -q`: 983 → 984 passed, 1 skipped, 3 xfailed. The +1 is
  `test_unbound_names[…teastore-protocol/teastore/candidate_quiet.py]`. A later rerun (10:10Z) gave 1014 passed: the
  +30 are in `tests/test_sweep_analysis_v2.py`, which another session modified (uncommitted, 12 → 21 test functions);
  not this build.
- **The new tests** (46): 40 no-fault cells, 10 per rate, blocks 1-10 each holding every rate once; the order recomputed
  from the recorded encoding; the shuffle and onset rules reproduce the sweep's with the sweep's values; every cell equal
  to the sweep's no-fault timing apart from the three onset keys, each tenth stratum once per rate; the descriptor
  differs from the sweep's only in `id`, `declaration`, `design`, `timing`, `schedule`, `outcomes`, `analysis`,
  `continuation`, `protocolGates` (`blocking`, `blockingNote`) and `derivedFrom`; the budget; **the sweep's files
  byte-identical to `0588a41` and its digests `f90bd64c` / `88a3017a` unchanged**; **under the sweep selector the
  `d0a5953` tree gives the same `active()` epoch, controller set, campaign manifest, plan and 12 cell contracts as the
  `0588a41` tree** (only the digests of the two changed controllers differ); the sweep-mode compiler follows the
  selector; the quiet selector activates the epoch in the adapter, transport, controller, producer, validator, terminal,
  readiness checker, orchestrator and both witness extractors; malformed quiet selectors and a compiler naming another
  epoch refuse to load; materialize → inspect → 40 contracts → runtime package through the transport's own validator
  (39 cells refused) → producer contract check, with 7 planted contract defects refused; a fake-driven runtime slice of
  a quiet cell issues the same commands as the sweep's no-fault cell at every rate (run root and barrier ID masked); a
  sealed quiet cell validates at every rate (G1, G2, G4; completeness window `whole-measurement`); a missing journey, the
  sweep's onset in a quiet receipt and a pre-onset failure at 0.05/s are rejected; the 40-cell campaign replays its own
  allocation and a swapped order is rejected; the 3.9 floor and the 3.9 digest; the whole quiet runtime imports under
  `/usr/bin/python3 -I`. At `91c4967` (+6, 52 in all): a ledger row drifting 1 s from its planned offset blocks
  `pre-outcome-plan-and-ledger-chain` on a sealed quiet cell (0 s drift, rechained, passes), and each system-samples
  shape plant (kind, count, grid, start) blocks `system-samples`.
- **Planted defects** (in the worktree, one at a time, each restored with `git checkout` and checked byte-equal to HEAD;
  plants that change the descriptor or plan were re-pinned and the descriptor regenerated, so a semantic test has to
  catch them): **13 of 13 caught**. Script: `<session scratchpad>/tq/plants.py`.

  | plant | first failing test |
  |---|---|
  | blocks 10 → 9 | `test_quiet_plan_is_40_no_fault_cells_10_per_rate_deterministic_and_pinned` |
  | seed 20261005 | same |
  | onset strata collapsed (every block in stratum 0) | `test_every_cell_is_the_sweeps_no_fault_cell_but_for_the_pseudo_window_onset` |
  | no shuffle | `test_the_order_is_recomputed_from_the_recorded_encoding` |
  | a 10/s lead order in block 1 | same |
  | concurrency 32 in the cell shape | `test_every_cell_is_the_sweeps_no_fault_cell…` |
  | onset not re-drawn (the sweep's onset kept) | same |
  | GATE-RUN window hand-set to 4 h | `test_budget_is_the_sweeps_rule_over_40_cells_and_covers_the_measured_periods` |
  | one byte in `candidate_sweep.py` | `test_the_sweep_epoch_is_byte_identical_and_its_digests_unchanged` |
  | selector accepts any `teastore-quiet*` document | `test_a_malformed_quiet_selector_refuses_to_load` |
  | adapter drops the sweep compiler and descriptor bindings | `test_the_selector_activates_the_quiet_calibration` |
  | sweep-mode compiler always `candidate_sweep.py` | `test_the_sweep_mode_compiler_follows_the_selector[…quiet]` |
  | the sweep epoch also gets additional controller paths | `test_under_the_sweep_selector_the_runtime_is_the_0588a41_runtime` |

- **Digests after the plants:** the same plan and descriptor digests under `/usr/bin/python3 -I` with the default Apple
  bytecode cache, with a fresh `pycache_prefix`, and under `uv run python -B -I`.
- **Launcher DRY_RUN** on `91c4967` (`scratchpad/gate-drivers/teastore-quietdry2-launch.log`, rc 0, paths shortened;
  `quietdry1` on `d0a5953` at 09:39Z also passed, identical apart from HEAD and times):
  ```
  10:05:32Z === teastore launcher quietdry2 (ROOT <worktree>, HEAD 91c4967, dry=1) ===
  10:05:36Z previous campaign status (<worktree> live package): state=complete systemd=inactive/dead result=success journalRows=12 terminal=True abort=False lease=False
  10:05:36Z plan: descriptor 338226d0..., firstRunId teastore-quiet-calibration-v1/no-fault-cost/r0p05/b01/full/a01, minimumFirstMutationRemainingSeconds 21300, plan 879a81ab..., runCount 40, runWindowHours 7
  10:05:36Z drivers read: ROOT=<worktree> STUDY=teastore-quiet-calibration-v1 CAMPAIGN_ID=teastore-quiet-calibration-v1 RUN_WINDOW_HOURS=7 PLAN_DIR=.../plan-ce87db3c GATES=.../gates SWEEP=True
  10:05:40Z srv5 host facts (stdout only): ncpu=24 cgroup=systemd/2 candidate_containers=0 containers=0
  10:05:41Z authorization (auto will re-derive if not live): HEAD 91c4967f... / authorized 2026-10-04T07:36:12Z deadline 2026-10-11T07:36:12Z live=True / provenance derived by `auto` / invariants match=False
  10:05:45Z srv5 free GB (stdout only): 364
  10:05:45Z DRY RUN: all guards passed; stopping before the first mutation
  ```
  What the dry run cannot show: the SETUP-CAMPAIGN renewal, `auto` (upload, install, image build, readiness), `oneshot`
  and the cell period.

## Guards costed (CLAUDE.md "cost the guards, not the cells")
The sweep build (`9e75010`) had already moved every shape literal behind `study_epoch.active()`, so no guard literal
had to change. Each guard and what it now reads:

| guard | where | quiet value |
|---|---|---|
| cell-count literals | adapter / transport / controller / terminal `RUN_COUNT`, installer `_installed_run_count()`, readiness `compiledRunCount` / `expectedRunRoots`, validator population | 40 (epoch), tested ("exactly 40 cells") |
| regime set | validator `REGIMES` / `SCENARIOS`, terminal `_required_for`, producer scenarios, witness `EFFECT_REGIMES` | `("no-fault-cost",)`; the sweep's fault regimes are refused (tested) |
| run-ID formats and regexes | `candidate_quiet._run_id_parts`; campaign-ID regexes `^[a-z0-9][a-z0-9_-]{0,63}$` | `teastore-quiet-calibration-v1/no-fault-cost/r…/bNN/full/a01`; campaign ID 29 characters; Compose project `teastore_candidate_46a023456d95cf24` |
| blocks / ordinal ranges (the Latin-square analogue) | producer and validator `1 <= block <= blocksPerRegime`, transport and producer ordinal `1..maximumOrdinal` | 10 blocks, ordinal 1-4 |
| GATE-RUN window, minimum remaining, watcher cap | `teastore_driver_root.RUN_WINDOW_HOURS` → `gate_run.py`; adapter, transport and controller minimum; launcher cap = window + 1 | 7 h, 21,300 s, 8 h (derived) |
| descriptor equality | adapter `_frozen_timing` (warm-up, measurement, `minimumTimedSeconds` against the compiler), `validate_descriptor` exact generator equality, producer `compiler.frozen_descriptor()` | quiet compiler exposes the same names; `minimumTimedSeconds` 8,400 |
| spent-attempt records | TeaStore keeps none (`ATTEMPT = 1`, per-process consumed guard; launches separated by setup ID) | nothing to record; quiet run IDs differ from the sweep's |
| controller digest binding | adapter `CONTROLLER_PATHS` | +`sweep-compiler`, +`quiet-descriptor`; `sweep-descriptor` names the sweep's file; 56 bound |
| host binding (lineage-wide fb14srv5) | adapter target, machine-id, descriptor `targetHost` | unchanged, inherited |
| launcher sweep guard | `launch_teastore.sh` requires `SWEEP=True` from the drivers | the quiet epoch is a sweep-mode epoch: passes |

Cosmetic only, left unchanged: `gate_run.py` prints "LAUNCHING 27-CELL CAMPAIGN" (a literal the sweep runs printed too).

## Defects and time
- **Critical-path harness defects: 0** (of the 3 that stop TeaStore's part A).
- Test-scope findings, fixed in this build: 18 effect-cell node ids cannot run under the quiet selector (skip list,
  ~10 min); three of my own test assertions corrected on first run (barrier IDs differ by run ID; the slice receipt has
  no `timing`; the no-fault completeness window is named `whole-measurement`), ~10 min; the review's A1 (quiet twins of
  two skipped generic-rule tests, `91c4967`), ~15 min.

## Open questions for the user (▶ = preregistration class), with the resolutions the OTel freeze used
1. ▶ What counts as quiet time T. *Proposed resolution, as OTel:* decided by H2 (decision 33, round 9 item 42): the
   whole 180 s measurement window of every held-out no-fault cell, slid over, warm-up and probe windows excluded
   (TeaStore no-fault cells have no readiness probe in the measurement).
2. ▶ Pooling. *Proposed resolution, as OTel:* decided by H1 (decision 31): all fault-free time per system × rate, which
   includes the sweep's no-fault cells and B's.
3. ▶ Order. *Proposed resolution, as OTel:* an engineering default, kept per-block (randomised complete blocks, which
   balance drift over the run). Hotel's quiet run uses one shuffle over all 40 (`DECLARATION_QUIET_HOTEL.md`). Both are
   seeded and recorded; the difference is noted, not harmonised.
4. ▶ Seed 20261004 and 10 onset strata per rate. *Proposed resolution, as OTel:* engineering defaults, to be recorded in
   `research/protocol/parameters.json`.
5. **The freeze must use the file name `research/traffic-sweep/DECLARATION_QUIET_TEASTORE.md`.** The pinned descriptor's
   `declaration` field names that path. Any other name, or any change to a design value, means a regenerated
   descriptor, new digests, a new commit and a new DRY_RUN.
6. Engineering defaults recorded: cell period estimate 525 s (the sweep's; above every measured relaunch-2 period);
   prepare reserve 1,800 s; cleanup reserve 300 s; window 7 h; watcher cap 8 h; artifact-root strings as the sweep's;
   the inherited fault vocabulary (`groundTruth.fault.scenarioContracts`, `faultParameters`) left in the descriptor,
   unused (no quiet cell has a fault); the 18 effect-cell test skips under the quiet selector.

## Review
One independent read-only review of `3c8cc03` and `d0a5953` was run by a separate subagent (Fable,
`adversarial-review`, neutral prompt: seven requirements to falsify, three report categories) on 2026-10-04. It edited
nothing, made no host contact and opened nothing under `tmp/`. It falsified one requirement (minor) and found no
blocker in the harness.

| finding | rating | action |
|---|---|---|
| A1: 5 of the 18 skipped node ids (2 tests) check generic rules (ledger row drift, system-samples shape) and fail under the quiet selector only because their fixture builds an auth-freeze cell; the other 13 are effect-only, and the 18 fail exactly as stated and pass under the sweep selector | minor (coverage) | **fixed** in `91c4967`: twins on sealed quiet cells (+6 tests); the skips stay |
| B1: the declaration is not frozen; the descriptor names `DECLARATION_QUIET_TEASTORE.md` | blocker (process) | the freeze is the coordinator's step (open question 5) |
| B2: a 40-cell, 10-block plan has never executed on fb14srv5 (blocks 2-10, a 40-row journal, the 40-cell lease scope, a 7 h deadline); the dry run does not reach `auto`, `oneshot` or the controller loop | major (first-run risk) | recorded; no shape literal found (C6), block 5 and 10 slices checked (C8) |
| B3: a sustained cell period of ≥ ~600 s would hit the deadline's cleanup reserve and abort | major (sensitivity) | recorded; measured maximum 423.4 s; the periods were not re-verified by the reviewer (read from the host journal, timestamps only) |
| B4: inherited inconsistencies: every cell's `timing.protocolGates` lists F1 while the descriptor's blocking list is G1, G2, G4; `collection.witnessLogSecretScan` says "sweep only"; the fault vocabulary is unused | minor | recorded; the validator derives the blocking list from `faultApplied` |
| B5: the plan records the order, not the seed (the seed is in the descriptor, bound by `descriptorSha256`) | minor | recorded: the sweep plan's schema is kept on purpose, so every runtime reader replays it unchanged |
| B6: SETUP-CAMPAIGN is live but bound to the sweep's plan; `auto` re-derives it | minor (audit trail) | as expected; recorded as auto-derived |
| B7: `gate_run.py` prints "27-CELL" | minor (cosmetic) | left |
| B8: the measurement repo's tree is dirty; no fetch entry for the quiet campaign yet | minor | the launcher checks the worktree only; fetch as for relaunch 2 |
| B9: the wandb follower is a separate command | minor | in the launch block above |

The review's checks that held include: the sweep's files byte-identical to `0588a41` (`git diff` empty for every sweep,
validator, witness, workload and runtime file but the three changed ones); the digests under 3.9 and 3.13; every
attribute the runtime reads from the compiler present in `candidate_quiet.py`; no remaining count, block, ordinal or
regime literal; block 5 and block 10 quiet slices issuing the sweep's no-fault commands; the materialized plan
directory and the launcher's static path with the launch environment.

## Note at freeze (coordinator, 2026-10-04)
Launched at harness `91c4967`, plan `879a81ab…`. This run keeps TeaStore's blocking trace-completeness rule (decision 25,
journey unit). The OTel quiet run switched to record-not-block after its attempt 1 (decision 56). If this run stops on
trace loss in a quiet cell, the same amendment is the proposed remedy, and it goes to the user first.
