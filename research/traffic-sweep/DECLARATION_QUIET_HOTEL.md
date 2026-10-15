# Quiet calibration run (A) on HotelReservation: declaration (FROZEN 2026-10-04, committed alone before the first cell)

**Status: frozen.** Committed alone under the path the descriptor names, before the first cell; harness e9d35f7, plan
`554a7a1e…`. Decisions: user round 10, items 48 and 50
(`research/PROTOCOL_DRAFT_20261002.md`); proposal `NEXT_CAMPAIGNS_PROPOSAL.md` §A. Budget and stop rule:
`BUDGET_CALIBRATION.md` (98e07bf, committed alone before this work). Derived from the Hotel traffic sweep:
`DECLARATION.md` (a795fc9) as amended by `AMENDMENT_1.md`, `AMENDMENT_2.md` and `AMENDMENT_3.md`. Scope of every
number: **instance** (one SUT, one host).

## Binding
| item | value |
|---|---|
| harness | worktree `observability-placement-runtime-hotel-protocol`, branch `hotel-protocol-20261002`, commit **`e9d35f7`** (`e9d35f7fffcab4134b53a864cd36613cc628cb4d`) on `ca58974` (the harness of sweep relaunch 3) |
| epoch | `hotel-quiet-calibration-v1`, activated by the committed selector `modules/hotel-reservation/execution/study-epoch.json` |
| compiler | `modules/hotel-reservation/execution/candidate_quiet.py`; it reads `candidate_sweep.py` as a library, and that file is digest-bound as `sweep-compiler` |
| descriptor | `pipelines/campaigns/hotel-quiet-calibration-v1.json`, canonical sha256 `fa42391ddb766e03bfbbf0eb212bff0b5409ed8def238a754199c17a4301efea` |
| plan | canonical sha256 `554a7a1e753a7f3535a7ae1c796cceee986bf0b1ae4b629858de2a547d79b127`, 40 cells. The same value under `/usr/bin/python3 -I` (3.9.6, fresh `-X pycache_prefix`) and `uv run` (3.13.12) |
| derived from | `hotel-traffic-sweep-v1`: descriptor `788ff28c…`, plan `766063c5…`, both unchanged at `e9d35f7` (tested) |
| host | fb14srv4 only; wall budget 14,400 s (4 h), first-mutation minimum 14,100 s, watcher cap 5 h |
| analysis | none until analysis v2 is frozen (`METHODOLOGY_HARDENING.md` §4; `BUDGET_CALIBRATION.md` rule 4) |

## Purpose
False-alarm calibration. With 0 false alarms in T quiet hours, the one-sided 95 % upper bound on the false-alarm rate
is −ln(0.05)/T ≈ 3/T per hour. The sweep's no-fault cells give each rate about 12 min of no-fault time, so the best
it can certify is about 15/h. This run gives each rate **30 min** of quiet measurement (10 cells × 180 s). That
certifies **≤ 6/h per rate** for a detector with no alarm in it (decision 48). If a detector does alarm, its rate is
estimated, not certified.

## Design
- **Cells.** 40 = 10 blocks × 4 rates (**10, 1, 0.2, 0.05 /s**). Every cell is the sweep's `no-fault-calibration`
  cell. No fault is applied in any cell, and the plan holds no fault regime.
- **Cell shape (unchanged from the sweep).** `GET /hotels`, open loop, concurrency 16, per-request timeout 1 s.
  Warm-up 30 s at 10/s for every rate, untokenised. Measurement 180 s. Offered = rate × 180 (1800, 180, 36, 9).
  Posture `full` only. The compiler reads every one of these values from `candidate_sweep.py`; none is restated.
- **Pseudo window.** As in the sweep's no-fault cells: onset 60 s plus a seeded offset inside one inter-arrival, hold
  60 s. It is carried for G1/G2 and for comparison with the sweep's no-fault cells. The rule is the sweep's
  (`onset_phase_offset`: stratified, seeded draws), with this epoch's name and seed. Each rate has 10 cells, so it
  has **10 strata**: the 10 blocks of a rate cover each tenth of one inter-arrival exactly once.
- **Order.** One Fisher-Yates shuffle over all 40 cells, with SHA-256 draws from seed **20261004**. The starting order
  is block-major, with rates in declaration order. Draw i is SHA-256 of UTF-8(seed ‖ NUL ‖ epoch ‖ NUL ‖ `all-cells` ‖
  NUL ‖ `draw-i` ‖ NUL ‖ `quiet-schedule-v1`), modulo i + 1. The order is recorded in the descriptor
  (`schedule.order`) and in the plan (`sequence.order`). There is no block-wise order and no lead cell.
- **Run IDs** `no-fault-calibration-r<rate>-b<NN>-full-a01`, NN = 01–10. Artifact roots are
  `calibration/r<rate>/b<NN>/p<position>-full/attempt-01`, where the position is the cell's place in the 40-cell order.
  *Engineering default:* the sweep's regime id is kept, so every regime-keyed reader stays unchanged. As a result, the
  IDs of blocks 01–04 are the same strings as the sweep's no-fault run IDs. Within one campaign directory they are
  unique. Across the two epochs they are told apart only by `studyEpoch` and the campaign ID.
- **Budget (derived, the sweep's rule).** ceil-to-hours(40 × 275 s + 600 + 300) = **4 h**. The measured cell period
  in sweep relaunch 3 (`runtime-journal.jsonl` `recordedAt` gaps, 63 intervals, srv4) had a median of 246.5 s and a
  maximum of 261.6 s. For no-fault cells alone (16 intervals): median 246.3 s, maximum 261.1 s. Expected run time:
  40 × 246–262 s ≈ **2.7–2.9 h**, plus a few minutes of setup.
- **Netem, CPU throttle.** These are not used: no fault. The fault doses are a fixed factor inherited from Hotel's
  catalogue (decision 50) and concern the sweep, not this run.

## What is measured (per cell; the sweep's no-fault capture, unchanged)
- The opportunity ledger: per request, scheduled, started and ended times, outcome and status. The warm-up ledger is
  validated but not scored.
- Application logs of every service, via `docker compose logs --timestamps`, kept as raw bytes and parsed with U+FFFD
  replacement.
- Traces: the frontend Jaeger query, plus the de-duplicated remainder of the other nine application services.
- The cgroup sampler every 5 s (`system-samples.json`), docker-stats CPU (`cpu.json`) and the cgroup cost edges.
- TCP snapshots at pseudo-onset −15 s and +7 s, docker events, and the image, posture and source proofs.
- Every time is reported with its channel's resolution. Event time is primary (decision 43).

## Gates (unchanged from the sweep at ca58974; `validation/protocol_gates.py` byte-identical)
- Blocking per cell:
  - **G1**: traffic, meaning scheduled opportunities and at least 1 request started in the window.
  - **G2**: healthy before the pseudo onset, meaning successes ≥ 0.5 × rate × seconds and a failure share ≤ 5 %.
  - **G4**: bookkeeping, meaning offered == plan and a complete ledger.
- **F1** applies to fault cells only, so it is not evaluated here. **R2.recovery** is `—`. **P0, R1 and R2** are not
  evaluated, as in the sweep (the harness writes none of their inputs).
- **Decision 25, trace completeness.** A no-fault cell has one window, `measurement`. The cell blocks when incomplete
  traces exceed max(1, floor(1 % × successful requests)). Malformed traces block at once.
- **Known residual (AMENDMENT_2).** A lost frontend root still blocks, because an untagged fragment cannot be tied to
  a request.
- **At 0.2 and 0.05 /s, one failed pre-onset request fails G2.** In this plan, every 0.2 /s cell has 13 scheduled
  requests before the pseudo onset, and every 0.05 /s cell has 4. A single failure stops the campaign under the
  first-invalid rule.
- **Integrity checks run first, as before:** hash-chained ledger replay, plan replay, witness bijection, manifest,
  provenance, posture, cleanup, nuisance and docker events.
- **The runtime stops on the first invalid cell.** At most 2 relaunches (`BUDGET_CALIBRATION.md`). Three
  critical-path harness defects stop Hotel's part of A, and the user is asked.

## Analysis
**No analysis runs until analysis v2 is frozen** (`METHODOLOGY_HARDENING.md` §4, `BUDGET_CALIBRATION.md` rule 4).
Until then:
- no detection, false-alarm, sensor or placement number is computed from these cells;
- the only reads allowed are cell validity, the runtime journal, and the counts needed to fetch and verify the
  evidence.

The following are fixed by analysis v2 before any quiet cell is read, not here:
- the false-alarm definition per sensor and per placement (K, floor, operating point; H7);
- which seconds count as quiet time (decision 48 sizes it as the whole 180 s measurement);
- whether the sweep's 16 no-fault cells are pooled with these.

## Verification at e9d35f7 (2026-10-04)
- **Tests.** In the worktree, the whole suite (`uv run pytest -q --continue-on-collection-errors`):
  - **before** (ca58974): 923 passed, 37 skipped, 14 failed, 1 collection error;
  - **after**: 957 passed (+34, the new `tests/test_hotel_quiet_calibration.py`), 37 skipped, and the same 14 failures
    and 1 error, diffed by name;
  - the failures: 12 in `test_online_boutique_lgtm_module.py`, plus
    `test_online_boutique_module.py::test_materialized_guards_cover_go_request_path` and
    `test_otel_materialize.py::test_materialized_guards_do_not_load_enabled_implementations_when_disabled`. The error
    is in `test_mlflow_manifest.py` (mlflow is not installed).

  In the measurement repo (`uv run pytest -q`), 955 → 957 passed, 1 skipped, 3 xfailed. The +2 by name:
  - `test_unbound_names[…hotel-protocol/…/candidate_quiet.py]`, from this build;
  - `test_unbound_names[…otel-protocol/…/candidate_quiet.py]`, from the OTel quiet build in its own worktree, not this
    one.
- **The new tests:**
  - exactly 40 no-fault cells, 10 per rate, and no fault regime;
  - the order recomputed independently from the recorded encoding;
  - every cell equal to the sweep's no-fault timing apart from the four onset-derived keys, with each tenth stratum
    once per rate;
  - the descriptor differs from the sweep's in exactly `id`, `declaration`, `design`, `timing`, `schedule`,
    `analysis` and `derivedFrom`;
  - **the sweep's descriptor and plan digests unchanged**. Ten sweep or shared files are byte-identical to ca58974.
    Under the sweep selector, the e9d35f7 runtime emits the same 64 contracts, policy, budget, controller set and
    embedded launcher as the ca58974 runtime;
  - the selector activates quiet: 40 contracts, a planted timing is refused, the launcher is re-budgeted to
    `!=14400` and `14100..14405`, and the GATE-RUN text carries `cells=40 wallSeconds=14400`;
  - the driver config gives quiet and 4 h;
  - b10 run IDs pass the workload;
  - a sealed quiet cell validates at every rate (G1, G2, G4 pass; trace-completeness window `measurement`), and one
    request missing is rejected;
  - a fake-driven `run_cell` of a quiet cell issues the same commands as a sweep no-fault cell;
  - the 3.9 run under `-I` with a fresh pycache prefix.
- **Seen failing on planted defects** (scratch clone, re-pinned where a digest would otherwise catch it first):
  **9 of 9 caught**. The plants: doubled concurrency, one cell carrying a fault, 4 onset strata, seed 20261005, no
  shuffle, the runtime dropping the `sequence` reader, the runtime adding a contract key under the sweep, the sweep
  overhead 60 → 61 s, and a hand-set 3 h budget.
- **Replay before spend.** The e9d35f7 terminal, under the sweep selector, replayed all 64 retained relaunch-3 cells
  (`tmp/hotelsweep3-evidence/x`, read-only). All 64 are valid, with terminals byte-identical to the retained ones
  (3.13). The 16 no-fault cells gave the same result under `/usr/bin/python3 -I -B` (3.9.6). No quiet cell exists to
  replay.
- **Offline, no remote action.** `inspect_bindings` at e9d35f7 gives plan `554a7a1e…`, descriptor `fa42391d…`, 40
  runs and 27 controllers, including `sweep-compiler`. The release bundle builds: 33,249,280 bytes, 2,433 entries,
  sha256 `7039d2fa…`; the quiet compiler, descriptor, policy, selector and sweep compiler are inside it.

### Dry run (2026-10-04 08:00Z, `DRY_RUN=1`, read-only against fb14srv4)
Log `scratchpad/gate-drivers/hotel-quietdry1-launch.log`:
```
08:00:49Z === hotel launcher quietdry1 (HEAD e9d35f7 on hotel-protocol-20261002, plan 554a7a1e753a7f3535a7ae1c796cceee986bf0b1ae4b629858de2a547d79b127, 40 cells, dry=1) ===
08:00:57Z previous runs on host: 1 [hotel-v1-20261003t134611z-db51eb9e ]
08:01:06Z host preflight: containers=0 compose=[]  free GB=172
08:01:06Z setup-campaign status: HEAD e9d35f7fffcab4134b53a864cd36613cc628cb4d authorized 2026-10-03T04:54:39Z deadline 2026-10-10T04:54:39Z live=True invariants match=False
08:01:06Z DRY: would renew SETUP-CAMPAIGN onto 554a7a1e753a7f3535a7ae1c796cceee986bf0b1ae4b629858de2a547d79b127
08:01:06Z DRY RUN: all guards passed; stopping before the first mutation
```
- **Previous run on the host.** It is relaunch 3, `hotel-v1-20261003t134611z-db51eb9e`. Its local archive
  `tmp/hotel6-evidence/hotel-v1-20261003t134611z-db51eb9e.tgz` exists (102 MB). In a real launch the launcher moves
  that run's host paths aside before `auto`. The destination names carry a fresh stamp, so nothing collides, and the
  launcher only moves, never deletes. Nothing was moved during this work.
- **SETUP-CAMPAIGN.** Its invariants differ, because the plan is new. A real launch therefore runs
  `propose-campaign` and `authorize-campaign` onto `554a7a1e…` before `auto`.
- **What the dry run cannot show:** that renewal; `auto` (upload, install, readiness); `oneshot`; and the cell period.

## Launch (after this declaration is frozen and committed alone)
From the measurement repo:
```
HOTEL_ROOT=$PWD/../observability-placement-runtime-hotel-protocol COMPILER=candidate_quiet.py \
EXPECTED_PLAN=554a7a1e753a7f3535a7ae1c796cceee986bf0b1ae4b629858de2a547d79b127 RUN_COUNT=40 \
nohup caffeinate -i zsh scratchpad/gate-drivers/launch_hotel.sh quiet1 > scratchpad/gate-drivers/hotel-quiet1.out 2>&1 &
```
The wandb follower (monitoring only; the evidence of record is the fetched campaign directory):
```
nohup uv run python tools/wandb_campaign.py follow hotel-quiet1 scratchpad/gate-drivers/hotel-quiet1-launch.log \
  > scratchpad/gate-drivers/wandb-hotel-quiet1.out 2>&1 &
```
After terminal:
1. fetch to a new path under `tmp/` and archive to `tmp/hotel6-evidence/<campaign-id>.tgz` (the next Hotel launch
   requires that archive);
2. byte-verify;
3. check cell validity only.

## Review
One independent read-only review of `e9d35f7` was run by a separate subagent (Fable, `adversarial-review` agent) on
2026-10-04. It found **no blocker** and could not refute any of the seven build requirements. It reproduced the
digests under 3.9 `-I` and 3.13, the suite counts, the sweep-unchanged tests and the extension-ledger audit (pass, 0
unclassified). It also checked that the copied onset rule equals the sweep's own function with this epoch's
parameters (0 of 40 mismatches).
- **Majors.** Both are launch preconditions, not code defects:
  - M1: this declaration must be renamed and committed alone first. The descriptor already names
    `DECLARATION_QUIET_HOTEL.md`.
  - M2: SETUP-CAMPAIGN is stale and the gates directory still holds relaunch 3's run-phase files. The launcher renews
    the first and archives the second before `auto`, so launch only through `launch_hotel.sh` with all four env
    overrides.
- **Minors**, recorded and not fixed:
  - m1: run IDs of blocks 01–04 equal the sweep's no-fault IDs, and 2 artifact roots coincide. Any pooling must key on
    the campaign ID. `tools/evidence_inventory.py:236` reads `plan["blocks"]` and needs a check before it touches
    quiet evidence.
  - m2: `candidate_quiet.py` restates the onset-rule body and the timing dict; it reads only their constants from the
    sweep. Its docstring says "never restated".
  - m3: inherited fault vocabulary (`groundTruth.fault.scenarioContracts`, `faultParameters`) stays in the
    descriptor. No runtime reader applies it.
  - m4: `fetch_overnight.sh` has no quiet mode yet.
- **Not checked by the review:** host behaviour (`auto`, `oneshot`, host Python 3.9.2), the planted-defect claim
  (clone kept in the session scratchpad), and the 64-cell replay.

## Monitoring (not evidence)
Campaign progress is mirrored at a high level to Weights & Biases (`tools/wandb_campaign.py`). wandb holds no number
that is not also in the evidence.
