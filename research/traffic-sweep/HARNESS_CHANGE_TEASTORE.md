# Traffic-sweep harness change: TeaStore epoch `teastore-traffic-sweep-v1` (2026-10-03; committed, not activated)

Status: **implemented and committed in the TeaStore worktree, not activated, not run on any host.** Worktree
`../observability-placement-runtime-teastore-protocol`, branch `teastore-protocol-20261002`, base `c1724b1`, commits
`9e75010` (epoch, selector mechanism, tests), `761c95a` (frozen-only test skip list) and `9181964` (review fix:
`application.log` kept as raw bytes). The selector file is **not**
created. The only host contact was the launcher's `DRY_RUN=1` (read-only) against fb14srv5 (§7). In this repo:
this file, `DECLARATION_TEASTORE_DRAFT.md`, the launcher/driver edits of §8, all uncommitted. Scope labels:
**instance** for every file:line (at `9181964`), **method** for the epoch design. Every value below is a proposal held
as a parameter in `modules/teastore/execution/candidate_sweep.py` ("parameters" block); changing one changes the
descriptor and plan digests.

## 1. What the change is

- **A second epoch beside the frozen one.** `execution/candidate_sweep.py` (new) compiles `teastore-traffic-sweep-v1`.
  `execution/candidate_pilot.py` and `pipelines/campaigns/teastore-candidate-pilot-sys-v1.json` are byte-identical to
  `c1724b1` (test against `git show`); the frozen plan digest `0fee53e5...` is unchanged.
- **Selector.** `execution/study_epoch.py` (new) is the single reader of `modules/teastore/execution/study-epoch.json`.
  Absent: every epoch constant equals its `c1724b1` literal (27 cells, 29,100 s, `schedule-v1`,
  `entire-27-cell-one-shot`, three frozen regimes, postures none/selected/full; the adapter's `CONTROLLER_PATHS` key
  set equals the base's, parsed from `git show`). Present with exactly `{"schemaVersion": 1, "studyEpoch":
  "teastore-traffic-sweep-v1"}`: the adapter, transport, remote controller, installer, orchestrator, producer
  (`performance_campaign.py`), cell validator, terminal, readiness checker and both witness extractors run the sweep.
  Any other content, a boolean schemaVersion, duplicate keys, a non-JSON file or a symlink refuses to load (tested).
  With the selector the adapter digest-binds five more inputs: `frozen-compiler`, `sweep-descriptor`, `protocol-gates`,
  `study-epoch-loader`, `study-epoch-selector`; `candidate-compiler` becomes `candidate_sweep.py`.
- **Plan schema.** The sweep plan keeps the frozen plan's top-level keys (`scheduleAllocation`, `runCount`,
  `descriptorSha256`, ...) so the orchestrator, adapter, transport and installer replay it with the same code, but holds
  its cells in `blocks` (execution order) instead of `regimeRoots` (regime-major). `scheduleAllocation[regime]` keeps the
  frozen shape (selector digest = canonical sha256 of the regime's run IDs in order; posture per block). Run IDs:
  `teastore-traffic-sweep-v1/<regime>/r<rate token>/b01/full/a01`; the 5-key run key is unchanged, so four cells share
  a run key and differ by run ID and timing (the terminal and the campaign validator bind the run ID for sweep cells).
- **Per-cell timing.** Every compiled cell carries `timing` (rate, inter-arrival, concurrency, timeout, journey kind and
  workload id, warm-up seconds/rate/offered, barrier lead, measurement, offered, fault and target, throttle quota,
  onset base/offset/effective, hold, scored window, phase floors, post-recovery allowance, system-sample interval and
  count, capture flags). The adapter copies it into the contract (`window.timing`); the producer refuses a contract
  whose timing, run key, ordinal, artifact root or fault differ from the compiled cell for its run ID
  (`performance_campaign.py:3068`); the producer copies it into the receipt; the validator re-derives it from the
  compiled plan and refuses a receipt that brings its own (`sweep-compiled-timing`). So no retained file can bring its
  own numbers.
- **Plan (proposal)**: rates 10, 1, 0.2, 0.05 login journeys/s; 3 regimes (`no-fault-cost` calibration,
  `auth-freeze-effect` pause, `persistence-cpu-throttle-effect`); 1 block ⇒ **12 cells**; offered 1800/180/36/9; posture
  full; seed 20261003; lead cell `auth-freeze-effect` r10. Descriptor `86c31476...`, plan `14d36efa...`, identical under
  `/usr/bin/python3 -I` (3.9.6, fresh `pycache_prefix`) and `uv run` (3.13) (test).
- **Wall budget, derived** (`candidate_sweep.py`): timed 30 + 15 + 180 = 225 s per cell, overhead 300 s (engineering
  default; frozen cells measured 130 s median / 192 s max, §6) ⇒ period 525 s; minimum remaining at first mutation =
  12 × 525 + 300 = **6,600 s** (the frozen rule: upper estimate + cleanup reserve, which gave 29,100); GATE-RUN window =
  ceil_hours(6,600 + 1,800 prepare) = **3 h** (frozen driver: 11 h).

## 2. Diff summary (`git diff --numstat c1724b1 9181964`)

| file | change |
|---|---|
| `execution/candidate_sweep.py` (new, 694) | compiler: parameters, seeded order with lead cell, Hotel's onset offset, plan-derived phase floors, derived budget, descriptor generator, pinned digests, `compiled_cell(run_id)` |
| `execution/study_epoch.py` (new, 171) | selector reader; frozen literals; sweep constants from the compiler; `flatten_plan_cells` |
| `pipelines/campaigns/teastore-traffic-sweep-v1.json` (new, 483) | written by `candidate_sweep.py --write-descriptor`; a test asserts byte equality with the generator |
| `validation/protocol_gates.py` (new, 696) | `cp` of the measurement repo's `src/obsplacement/protocol_gates.py` (sha256 `1b3c8a3b...6590`) |
| `execution/performance_campaign.py` | +277 / −45: epoch constants; contract validation against the compiled cell; `_candidate_args` from timing; warm-up/workload argv; `inject_fault` sweep path (pre-command and revert stamps, hold from the first sample, stamped readiness probes `wait_ready_stamped`, CPU throttle with `host_nanocpus`); `application.log` as raw bytes (`capture_bytes`); receipt window/warm-up from timing, `receipt.timing` |
| `validation/candidate_pilot.py` | +445 / −60: every literal from the compiled timing (`design`), sweep checks (`sweep-compiled-timing`, `sweep-fault-command-stamps`, `protocol-gates`, `application-log-timestamps`), throttle state predicates, campaign recomputation from the sweep plan, run-ID binding |
| `execution/candidate_runtime_adapter.py` | +102 / −36: epoch constants, sweep `CONTROLLER_PATHS`, `application.log`, blocks flattening, sweep timing in contracts |
| `validation/candidate_terminal.py` | +45 / −12: run count, regimes, `application.log`, receipt run-ID binding |
| `workload/fixed_load.py` | +45 / −24: `--journey-kind login-only` (workload id `login-only-v1`); default unchanged |
| transport / controller / installer / orchestrator / readiness / 2 extractors | +33/+23/+19/+39/+32/+19/+19: run count, minimum remaining, lease scope, schedule version, ordinal range, descriptor path, readiness facts, effect regimes from the epoch |
| `extension-ledger.yaml` | +15: the three new module files |
| `tests/test_teastore_traffic_sweep.py` (new, 1,558) | 97 tests, §5 |
| `tests/conftest.py` (new) | skips 77 frozen-only node ids **only when the selector exists** |

## 3. Every guard that pinned the frozen shape: old → new (sweep; frozen value unchanged)

Found with `/usr/bin/grep -nE` for 27, 26, 28, 90, 91, 600, 120, 121, 180, 150, 0.15, 2430, 19_440, 29_100, 20, 8,
`schedule-v1`, `regimeRoots`, the epoch string, `no-fault-cost`, `(1, 2, 3)`, `<= 3`, plus a read of the per-cell
runtime slice and `validate_run`. File:line at `9181964`.

| site | old | new (sweep) |
|---|---|---|
| adapter `RUN_COUNT` / `MINIMUM_FIRST_MUTATION_REMAINING_SECONDS` / messages | 27 / 29,100 | 12 / 6,600 (epoch) |
| adapter `inspect_campaign` flatten | `regimeRoots` | `blocks` (`study_epoch.flatten_plan_cells`) |
| adapter `scheduleVersion` check | `schedule-v1` | `sweep-schedule-v1` |
| adapter `_frozen_timing` | 120 / 600 / 180 / 150 / 19,440 | warm-up 30, measurement 180, minimum timed from the sweep compiler; onset/hold per cell |
| adapter `build_cell_contract` workload / window / fault | descriptor 0.15/s, 90, 120/600, 180/150 | cell timing; `window.timing` |
| adapter readiness / contract `outerLeaseScope` | `entire-27-cell-one-shot` | `entire-12-cell-one-shot` |
| adapter GATE-RUN deadline message | "29,100 seconds" literal | formatted from the constant (frozen text identical) |
| transport `RUN_COUNT`, minimum, 27-cell messages, lease scope ×4, epoch, schedule version | 27, 29,100, literals | epoch values |
| transport ordinal | `in (1, 2, 3)` | `1..12` |
| controller `RUN_COUNT`, minimum, journal cap | 27, 29,100 | 12, 6,600 |
| installer journal rows `> 27`, `== 27`; descriptor path; `len(run_ids) != 27`; readiness `runCount` 27; lease scope | literals | `_installed_run_count()` / installed adapter's epoch |
| orchestrator `DEFAULT_DESCRIPTOR`, compiler, flatten, `scheduleVersion` | sys-v1, `candidate_pilot.py`, `regimeRoots`, `schedule-v1` | epoch descriptor/compiler, `blocks`, `sweep-schedule-v1` |
| readiness `compiledRunCount` 27, regimes, postures, `expectedRunRoots` 27, descriptor path, `runCount != 27` | literals | epoch |
| terminal `!= 27` ×4, `_required_for` regimes | literals | `RUN_COUNT`, epoch regimes; `application.log` required |
| validator `STUDY_EPOCH`, `REGIMES`, `SCENARIOS`, `POSTURES`, `REQUIRED_FILES` | frozen | epoch (+ `application.log`) |
| validator block `<= 3` | 3 | `blocksPerRegime` (1) |
| validator window | warm-up 120, measurement 600 | 30, 180 |
| validator plan | 0.15/s, 600 s, 90, offsets `index / 0.15`, 90 opportunities | timing rate, 180, offered, `index / rate` |
| validator ledger | 91 / 90 rows, reconciliation 90 | offered + 1 / offered |
| validator journey shape | login, browse-home, ..., return-home | `["login"]` for `login-only` |
| validator denominator `offered == 90` | 90 | offered |
| validator resources `expected_duration_seconds=600.0` | 600 | 180 |
| validator system samples 600 s / 121 | literals | 180 s / 37 |
| validator intervention `scheduledOnsetSeconds == 180`, hold 150, `requestedHoldSeconds == 150` | literals | timing onset (float), 60 |
| validator service map | auth-freeze → auth else persistence | `FAULT_SERVICES` (throttle → persistence) |
| validator `actual-phase-start-floor >= 20` | 20 per phase | `max(1, ceil(0.5 × scheduled slots))` per phase |
| validator campaign recomputation / population `== 27` | frozen selector and schedules | recompiled sweep plan |
| producer contract `block <= 3`, `ordinal in (1, 2, 3)`, lease scope, compiler path | literals | epoch |
| producer `_candidate_args` | warm-up 120, 600, 0.15, 8, 180, 150 | timing (30, 180, rate, 240, onset, 60) |
| producer warm-up argv `--rate args.rate` | 0.15 | 10.0 (+ `--timeout 15.0 --journey-kind login-only`) |
| producer `_candidate_receipt` | 600, warm-up 0.15/120/18/8, `login-browse-v1`, 120, `+ 600.0` | timing |
| extractors effect regimes | auth-freeze, persistence-crash | epoch effect regimes |

Checked and left unchanged (the sweep's defaults do not trip them): collector duration `duration + 30`, collector join cap
600 s and no-progress 60 s, system-probe join `+ 90 s`, fault-thread join `duration + outage`, barrier lead 15 s,
`wait_ready` 240 s / 5 s cadence, queue-depth cap 25,000, exposure settle ≤ 30 s, broker heartbeat floor 300 s (2 ×
the frozen 150 s pause, above the sweep's 60 s), emergency cleanup 240 s, GATE-SETUP window 6 h (driver),
`MAX_GATE_RUN_AGE_SECONDS` 15 min, compose project derived from the campaign ID.

## 4. Compiled cells (execution order)

| # | regime | rate /s | offered | onset s (offset) | floors before/during/after |
|---|---|---|---|---|---|
| 1 | auth-freeze-effect | 10 | 1800 | 60.055 (0.055) | 301/300/290 |
| 2 | auth-freeze-effect | 0.2 | 36 | 61.005 (1.005) | 7/6/6 |
| 3 | auth-freeze-effect | 1 | 180 | 60.618 (0.618) | 31/30/29 |
| 4 | no-fault-cost | 0.05 | 9 | 79.505 (19.505) | — |
| 5 | no-fault-cost | 1 | 180 | 60.946 (0.946) | — |
| 6 | no-fault-cost | 10 | 1800 | 60.072 (0.072) | — |
| 7 | auth-freeze-effect | 0.05 | 9 | 73.251 (13.251) | 2/2/1 |
| 8 | no-fault-cost | 0.2 | 36 | 62.121 (2.121) | — |
| 9 | persistence-cpu-throttle-effect | 0.2 | 36 | 61.021 (1.021) | 7/6/6 |
| 10 | persistence-cpu-throttle-effect | 0.05 | 9 | 66.055 (6.055) | 2/2/1 |
| 11 | persistence-cpu-throttle-effect | 10 | 1800 | 60.000 (0.000) | 301/300/290 |
| 12 | persistence-cpu-throttle-effect | 1 | 180 | 60.116 (0.116) | 31/30/29 |

## 5. Tests (commands run 2026-10-03; counts from the pytest summary line)

| suite | before | after | delta accounted |
|---|---|---|---|
| worktree whole suite, `uv run pytest -q -p no:cacheprovider --ignore tests/test_mlflow_manifest.py` (mlflow not installed there) | 20 failed, 1808 passed | 20 failed, **1905 passed** (at `9181964`; 1904 at `761c95a`) | +97 = `test_teastore_traffic_sweep.py`; failures identical by name (`comm` on the sorted FAILED lines): Hotel materialize ×4, OB/OB-LGTM ×13, openspec, OTel materialize, science-epoch router. With submodules uninitialised the base had 26 (`research/teastore-sys/baseline-failures-f352f8d.txt`); initialising `upstream/teastore` fixed 6 TeaStore ones before any code change |
| same suite in a copy of `761c95a` with the selector committed (temporary, §7) | — | 20 failed (same names), 1772 passed, 137 skipped | 137 skips = the 77 frozen-only node ids of `tests/conftest.py` with their parameters; 1929 collected vs 1924: +5 parameters of the controller-digest drift test (five more digest-bound inputs) |
| measurement repo `uv run pytest -q` | 918 passed, 1 skipped, 3 xfailed (CLAUDE.md/brief) | **925 passed**, 1 skipped, 3 xfailed | +4 from this worktree (`test_unbound_names` for `candidate_sweep.py`, `study_epoch.py`, `protocol_gates.py`; `test_vendored_copy_is_byte_identical` for the TeaStore copy); +3 from the OTel worktree's concurrent vendoring (its copy, its `candidate_sweep.py`, `protocol_gates.py`), listed by `--co` |

`tests/test_teastore_traffic_sweep.py` (97): plan determinism, pins, seed, lead cell, offered, onset offsets, floors ≤
slots, derived budget, 3.9 digest; frozen files byte-identical to `c1724b1`, frozen constants and `CONTROLLER_PATHS`
keys, frozen `_candidate_args`; selector activation and six malformed selectors plus a symlink; materialize → inspect →
contracts (every cell's timing) → runtime package through the transport's own validator → producer contract check and
arguments; eight planted contract defects refused; **a fake-driven execution of `_execute_candidate_runtime_slice`**
(never executed by the suite before) for a frozen contract (every argv equals the base literal, no `application.log`)
and for three sweep contracts (warm-up 10/s × 30 s, workload rate × 180, `--timeout 15.0 --journey-kind login-only`,
collector 210 s, system probe 180 s, perf probe 180 s in no-fault cells, `inject_fault` gets the cell's onset/hold and
`sweep_timing`, one `docker compose logs --timestamps --no-color`); the fault controller with faked docker/time: the
frozen receipt key set unchanged, the onset stamp equal to the instant of the pause command at every rate, samples at
first + 30 / + 60 s exactly, one stamped probe inside [revert returned, readiness], hold within F1's bound, the throttle's
argv/quota/revert to NCPU, refusal of an already-throttled target; **a sealed sweep cell accepted by the validator for
all 12 (regime, rate) pairs** (real witness and native-token extractors, real Kieker spool replay), and rejected for: one
journey missing (each rate), a receipt carrying its own timing, a receipt of another rate under the same run key, six
command-stamp/probe plants, each blocking gate (F1 ×2, G1, G2) forced, a G2 pre-onset failure at 0.05/s, three
application-log plants, a stray non-UTF-8 byte (counted, not fatal), three frozen literals inside a sweep cell; the plan-derived floors; the 12-cell campaign replay
and a reordered campaign; terminal required artifacts; vendored gates byte identity; 3.9 grammar of the 15 changed
target files and their import under `/usr/bin/python3 -X pycache_prefix=<fresh> -I`; the login-only workload against a
local HTTP stub (10 POSTs, complete ledger) and the default journey unchanged.

**Planted defects, each seen failing** (one at a time in the worktree file, file restored after; script
`<session scratchpad>/plants.py`): onset stamp taken after the command; warm-up at the cell's rate; contract timing
trusted; frozen ≥ 20 floor kept; failed gates ignored; receipt timing trusted; frozen 600 s system window kept; hold
timed by the frozen sleeps (first missed; caught after the hold assertion was tightened to "samples at first + 30 / + 60
s"); throttle reverted with `--cpus 0`; `application.log` not required by the terminal; selector accepting any epoch;
onset offset dropped; login-only journey still browsing. **13 of 13 caught** (`-x`, first failing test recorded;
rerun on `761c95a`, 13/13; `9181964` changes none of the planted sites).

Offline bundle builds (TMPDIR in the session scratchpad): frozen epoch at `9e75010` — `inspect_campaign` on a plan dir
materialized in the scratchpad, `build_release_bundle` passed its own clean-HEAD and submodule checks (bundle
`21e53a1e...`, 102,686,720 B, submodule `34b37f7e...`); sweep epoch in the temporary activated copy (commit `2b305cc`,
selector on `9e75010`) under `/usr/bin/python3 -I`: inspect 12 cells, plan `14d36efa...`, 54 controller digests, bundle
`198a969e...` built.

Not tested: any real Docker, Kieker, TeaStore or srv5 path; the system probe on srv5 (never run, §9); a 60 s pause at
10/s; `docker update --cpus` on srv5; the detached controller with the selector committed; the readiness seams on the
target.

## 6. Cell duration, and how to check it

- Measured on the frozen epoch (srv5): journals of campaigns #12-#15 (`tmp/teastore1[2-5]-evidence/.../runtime-journal.jsonl`,
  `recordedAt` differences, 80 intervals): median 861-866 s, maximum 927 s per cell, against 735 s timed ⇒ overhead
  ~130 s median, ~192 s at most. Command: a `uv run python` loop over those files (session scratchpad `periods.py`).
- Sweep estimate: 225 s timed + 130-300 s ⇒ **355-525 s per cell**, 12 cells ⇒ **71-105 min** (`?` until the first
  cells run; a 10/s cell carries a larger spool to replay). The 3 h window and the 6,600 s minimum assume 525 s.
- A DRY_RUN cannot measure a cell. First observable: the gap between the first two `runtime-journal.jsonl` rows.

## 7. Dry run (2026-10-03 06:43Z) and the temporary activation

The launcher refuses a dirty tree and the adapter refuses an uncommitted framework, so the activation was tried in a
**detached copy**: `git worktree add --detach <session scratchpad>/activated 761c95a`, selector + its extension-ledger
entry committed there (`5c0a6be`, on no branch), submodule initialised, plan directory materialized
(`.local/candidate-v4/teastore/plan-e18a1256`, campaign sha256 `85e9bba0...`). Whole suite there: §5. Then:

```
TEASTORE_ROOT=<scratchpad>/activated EXPECTED_HEAD=5c0a6be5fd2acdb81dc3bcc6435f72dceca74585 \
TEASTORE_PREV_PACKAGE=$M/tmp/observability-placement-runtime-teastore-v4-reviewed2/.local/candidate-v4/teastore/gates/run-state-stopped-teastore20-20261002T134204Z/runtime-package.json \
COMPILER=candidate_sweep.py EXPECTED_PLAN=14d36efa85110c81c87ca6f97031f5cd4a8512e68cf248ce2c534ed8fe87e370 RUN_COUNT=12 \
DRY_RUN=1 zsh scratchpad/gate-drivers/launch_teastore.sh sweep1dry      # rc=0
```

Log (`scratchpad/gate-drivers/teastore-sweep1dry-launch.log`, paths shortened):

```
06:43:10Z === teastore launcher sweep1dry (ROOT .../activated, HEAD 5c0a6be, dry=1) ===
06:43:14Z previous campaign status (v4-reviewed2, run-state-stopped-teastore20/runtime-package.json): state=blocked systemd=?/? result=? journalRows=? terminal=False abort=False lease=?
06:43:15Z plan: descriptor 86c31476..., firstRunId .../auth-freeze-effect/r10/b01/full/a01, minimumFirstMutationRemainingSeconds 6600, plan 14d36efa..., runCount 12, runWindowHours 3
06:43:15Z drivers read: ROOT=.../activated STUDY=teastore-traffic-sweep-v1 CAMPAIGN_ID=teastore-traffic-sweep-v1 RUN_WINDOW_HOURS=3 PLAN_DIR=.../plan-e18a1256 GATES=.../gates SWEEP=True
06:43:19Z srv5 host facts (stdout only): ncpu=24 cgroup=systemd/2 candidate_containers=0 containers=0
06:43:19Z authorization (auto will re-derive if not live): HEAD 5c0a6be... / no SETUP-CAMPAIGN authorization recorded
06:43:23Z srv5 free GB (stdout only): 366
06:43:23Z DRY RUN: all guards passed; stopping before the first mutation
```

Reading: the previous-campaign status endpoint answered `state=blocked` for #20's archived package (the launcher counts
any non-running state as terminal, rc 3); the host check is the stronger one: **0 containers** on srv5. Docker reports
the systemd cgroup driver on cgroup v2 and 24 CPUs (the throttle's revert value). No SETUP-CAMPAIGN exists for the new
tree; `auto` derives one (recorded as auto-derived). Then the copy was removed (`git worktree remove --force`, 43 MB;
`git worktree prune`); the branch never held the selector. The dry run predates `9181964` (log capture only, no guard
or plan change); the activation commit needs its own DRY_RUN (§8 step 4).

## 8. Activation (for the main session; nothing below is done)

1. In the TeaStore worktree, one commit with exactly two changes:
   - `modules/teastore/execution/study-epoch.json` = `{"schemaVersion": 1, "studyEpoch": "teastore-traffic-sweep-v1"}` + newline;
   - `modules/teastore/extension-ledger.yaml`: before `  - path: execution/candidate_sweep.py`, add
     ```
       - path: execution/study-epoch.json
         class: deployment-overlay
         purpose: Committed study-epoch selector; its presence activates teastore-traffic-sweep-v1 (read by execution/study_epoch.py).
         origin: framework-owned
         upstream_patch: false
     ```
     (without it `tests/test_readiness.py::test_five_module_readiness_is_curated_and_auditable` fails: unclassified file).
   If the frozen declaration changes the descriptor's `declaration` field first, regenerate the descriptor
   (`candidate_sweep.py --print-digests`, move the old file aside, `--write-descriptor`), re-pin
   `EXPECTED_DESCRIPTOR_SHA256` / `EXPECTED_PLAN_SHA256`, commit, then activate.
2. Materialize the plan directory (local, gitignored): `cd <worktree> && /usr/bin/python3 -I -c "import importlib.util,
   sys; from pathlib import Path; s=importlib.util.spec_from_file_location('o','modules/teastore/execution/candidate_orchestrator.py');
   m=importlib.util.module_from_spec(s); sys.modules['o']=m; s.loader.exec_module(m);
   print(m.materialize_campaign(Path('.local/candidate-v4/teastore/plan-e18a1256'))['campaignSha256'])"`
   (directory name = `plan-` + first 8 hex of the descriptor file's sha256; `teastore_driver_root.py` prints it).
3. ROOT: the drivers now read `TEASTORE_ROOT` (default unchanged). Either launch with the environment below, or, to
   rebind permanently, change `DEFAULT_ROOT` in `scratchpad/gate-drivers/teastore_driver_root.py:22-25` to the
   worktree path (the only ROOT literal left; `gate_run.py`, `campaign_setup.py`, `gate_setup.py` import it).
4. Launch (after the frozen declaration is committed alone and wandb is mirrored per CLAUDE.md):
   ```
   W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
   M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
   TEASTORE_ROOT=$W EXPECTED_HEAD=$(git -C $W rev-parse HEAD) \
   TEASTORE_PREV_PACKAGE=$M/tmp/observability-placement-runtime-teastore-v4-reviewed2/.local/candidate-v4/teastore/gates/run-state-stopped-teastore20-20261002T134204Z/runtime-package.json \
   COMPILER=candidate_sweep.py EXPECTED_PLAN=<pinned plan> RUN_COUNT=12 \
   nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh sweep1 > $M/scratchpad/gate-drivers/teastore-sweep1.out 2>&1 &
   ```
   Run it with `DRY_RUN=1` first. A relaunch from the same tree uses `TEASTORE_PREV_ROOT=$W` and no
   `TEASTORE_PREV_PACKAGE`. The launcher archives stranded run state before `auto` and after a failed `oneshot`, as
   before; the watcher cap is the run window + 1 = 4 h.

Launcher and driver edits (measurement repo, uncommitted; defaults byte-for-byte the old values, checked by importing
each driver and printing ROOT / PLAN_DIR / STUDY / CAMPAIGN_ID / RUN_WINDOW_HOURS): `launch_teastore.sh` (TEASTORE_ROOT,
EXPECTED_HEAD, TEASTORE_PREV_ROOT, TEASTORE_PREV_PACKAGE, COMPILER/EXPECTED_PLAN/RUN_COUNT; with COMPILER also the
drivers' view, the materialized plan dir and read-only srv5 facts that abort if a `teastore_candidate` container runs;
watcher cap = window + 1), `teastore_driver_root.py` (new), `gate_run.py`, `campaign_setup.py`, `gate_setup.py`,
`campaign_status.py` (TEASTORE_STATUS_PACKAGE).

## 9. Open questions (preregistration-class unless marked)

1. All ▶ of `DECLARATION_TEASTORE_DRAFT.md`: route `POST /loginAction` (+ followed redirect) as "one request"; unit login
   journeys/s; timeout 15 s; concurrency 240; pause on auth; throttle on persistence 0.1 CPU reverted to NCPU; net delay
   omitted (no sudo on srv5); no-fault cells via the frozen cost path (perf probe only there); every service's log
   retained; lead cell.
2. **The cgroup system probe has never run on srv5** (sys lineage, `research/teastore-sys/PORT_LOG.md` step 0). The dry
   run shows systemd/cgroup v2, a necessary condition only; if `stig` cannot read the scopes, every cell blocks and the
   runtime stops at cell 1. A host smoke of `collectors/system_probe.py` needs approval.
3. **Zero tolerance carried from the frozen validator**: any failed journey in a no-fault cell, or before onset / after
   readiness in a fault cell, blocks the cell and stops the campaign (stricter than G2's 5 %). At 10/s that is 1 in
   1,800. The readiness edge has no allowance (review, §10): readiness is the first `GET /status` that reports 5 × OK,
   instant after an unpause or a throttle lift, so "after" journeys start while up to 150 released requests drain; one
   of them timing out (15 s) invalidates the cell. Keep, or relax to G2 / add a drain allowance for sweep cells?
4. G2 at the lowest rate (Hotel m6): ~3-4 journeys before onset at 0.05/s, so one pre-onset failure fails G2.
5. P0 / R1 / R2 not evaluated, G4 ledger-only, G1 dispatch condition inherited (Hotel Q6/Q7).
6. *(engineering default)* overhead 300 s, prepare reserve 1,800 s, post-recovery allowance 2 s (frozen auth-freeze
   receipts: readiness 0.44-0.60 s after the last hold sample, n = 28), system-sample count 37.
7. A 60 s auth pause at 10/s releases up to 150 blocked logins at once; never run on TeaStore; the lead cell shows it.
   Kieker capture at 10/s is also untested: across the 71 retained cells of #13-#15 (all regimes and postures; the maxima are full-posture no-fault cells) a cell carried at most
   3,875 AMQP messages / 102,353 records per cell (~6 messages/s at ~2 HTTP requests/s) with a maximum queue depth of
   15; a 10/s login cell (~20 HTTP requests/s with the followed redirect) is roughly 10x that message rate and ~3x the
   records per cell. The spool is fsynced per delivery; the queue cap is 50,000 with reject-publish, the depth guard
   25,000. `?` until the lead cell runs.
8. The analysis code (`research/detection-time/`) is not extended: it must read `timing` from the receipt, the
   `sweep.commandStamps` / `sweep.probes` of `intervention.json`, and `application.log`'s Compose prefix.
9. *(engineering default)* The previous-campaign check reads #20's archived package and gets `state=blocked`; the srv5
   zero-container check is what actually guards "one campaign per host".
10. **Drivers read ROOT** (review, process risk): `teastore_driver_root.py` keeps the v4 tree as its default, so running
    a driver by hand without `TEASTORE_ROOT` drives the frozen v1 tree. The launcher always exports it; rebinding
    `DEFAULT_ROOT` (§8 step 3) removes the risk and is the activation edit.

## 10. Independent review (2026-10-03)

One `adversarial-review` subagent on **Fable**, read-only, neutral prompt (question, scope, three report categories), on
`9e75010`. It ran: the 3.9 replay of the frozen literals and of the compiler (digests equal to the pins), a 3.9
`compile()` + AST scan of the 16 changed files (0 issues), the measurement repo's unbound-name scanner under 3.9 on 15
files (0 offenders), the sweep tests (96 passed) and seven frozen test files (456 passed), the vendored-gates sha256, a
grep for CPU quotas in the compose files (none, so the throttle's pre-state check holds), and a retained #10
auth-freeze receipt (~0.1 s per `docker inspect` on srv5). It found **no key-set mismatch, shape literal, 3.9
incompatibility or laptop-only path on the candidate path, and no frozen-epoch behaviour change**.

| finding | rating | action |
|---|---|---|
| strict UTF-8 decoding of the all-service `docker compose logs` capture raises on a stray byte and loses the cell | major, low likelihood | **fixed** in `9181964` (raw bytes; validator counts replacements) |
| drivers default to the v4 tree without `TEASTORE_ROOT` | major, process | open: Q10 (activation edit in §8) |
| zero-failure effect context at the readiness edge, no drain allowance | major, design | open: Q3 |
| descriptor `declaration` field is draft text; freezing it re-pins the digests | minor | recorded (§8 step 1) |
| `ALLOWED_FAULTS` / CLI `--fault` exclude the throttle (diagnostic CLI only) | minor | recorded |
| `scheduledOnsetWall` compared within 1 µs (both paths round; passes at exactly 1 µs) | minor | recorded |
| F1 hold margin ~0.8 s after two `docker inspect` latencies | minor | recorded (the sweep hold is timed from the first sample) |
| `application.log` check needs one stamped line per service; a truncated capture passes | minor | recorded |
| `issued >= onset − 0.05` is a literal | minor | recorded |
| frozen-receipt test checks key set and two values, not a base fixture | minor | recorded |

Not established by the review either: host behaviour at 10/s, the Compose log prefix on srv5, the cgroup probe on srv5,
and backlog drain after the readiness edge.


## 11. Addendum 2026-10-03 ~11:40Z: user decisions, Q3, re-pin, activation, dry run on the activation commit

User (via the coordinator, verbatim): "accept all, Q3 17 s". Every ▶ of `DECLARATION_TEASTORE_DRAFT.md` accepted as
proposed; Q3 = a drain allowance of client timeout + 2 s for sweep fault cells. Worktree commits:

- `59634c5` Q3 + declaration path. `drainAllowanceSeconds` = `REQUEST_TIMEOUT_SECONDS + DRAIN_ALLOWANCE_MARGIN_SECONDS`
  (15 + 2 = 17 s) in every fault cell's compiled timing, `None` in no-fault cells. A journey that STARTS in
  [readiness, readiness + 17 s) and does not succeed is excluded from the zero-failure rule (`effect-context`) and from
  the scored population (no witness, no native bridge required); it is recorded in `candidate-validation.json`
  (`drainAllowance.excusedFailures`, `excusedJourneyIds`, and on the `effect-context` row). One implementation,
  `study_epoch.drain_excused`, used by the validator and both witness extractors; the frozen epoch has no allowance;
  G2 unchanged (strict at 0.05/s). Descriptor `declaration` = "research/traffic-sweep/DECLARATION_TEASTORE.md
  (measurement repo; frozen 2026-10-03)". Re-pinned: **descriptor `e808c2bb8db1c8456a11aadbb63a36dfaacda482ff563ea4e23c997d1be920b6`,
  plan `5212f18c8159e6ed400362a8ffaef517db6246598881ce85a7faa3aa7e185601`**, identical under `/usr/bin/python3 -I`
  (3.9.6; no Apple bytecode-cache entries for this tree remained) and `uv run` (3.13). Tests +7: inside the
  allowance seals valid (with and without the journey's witness lines) and is recorded; the first start past the edge
  still invalidates; a pre-onset failure is never excused; a no-fault cell has none; the frozen validator never
  excuses. The inside test fails on `9181964` (run in a detached copy, since removed). Planted defects: 16/16 caught
  (13 earlier + allowance excusing successes, allowance without the +2 s, allowance not applied to the scored set).
- `396009a` skip list + the one new frozen-only test (probed in a detached copy of `59634c5` with the selector).
- **`9a4ea56` activation**: `modules/teastore/execution/study-epoch.json` + its extension-ledger entry (§8 step 1).

Suites: worktree before activation (`59634c5`) 20 failed / 1912 passed; on `9a4ea56` 20 failed / 1779 passed /
138 skipped (failures identical by name; 138 = the 78 skip-listed ids with parameters; +5 collected = the
controller-digest drift test's new parameters). Measurement repo `uv run pytest -q`: 925 passed, 1 skipped, 3 xfailed.

Plan directory materialized (gitignored): `.local/candidate-v4/teastore/plan-e79d5cb7`, campaign sha256
`392a2bc85902e9148dd8db225bf5a56a0a0771ea4d9185724200a63c00dbf323`. Dry run on `9a4ea56`
(`scratchpad/gate-drivers/teastore-sweep1dry2-launch.log`), rc 0:

```
11:37:51Z === teastore launcher sweep1dry2 (ROOT .../observability-placement-runtime-teastore-protocol, HEAD 9a4ea56, dry=1) ===
11:37:56Z previous campaign status (v4-reviewed2, #20 archived package): state=blocked ... terminal=False abort=False
11:37:56Z plan: descriptor e808c2bb..., plan 5212f18c..., runCount 12, runWindowHours 3, minimumFirstMutationRemainingSeconds 6600
11:37:56Z drivers read: ROOT=<worktree> STUDY=teastore-traffic-sweep-v1 RUN_WINDOW_HOURS=3 PLAN_DIR=.../plan-e79d5cb7 SWEEP=True
11:38:01Z srv5 host facts (stdout only): ncpu=24 cgroup=systemd/2 candidate_containers=0 containers=0
11:38:01Z authorization (auto will re-derive if not live): HEAD 9a4ea56... / no SETUP-CAMPAIGN authorization recorded
11:38:05Z srv5 free GB (stdout only): 366
11:38:05Z DRY RUN: all guards passed; stopping before the first mutation
```

Launch command (not run; the frozen declaration is committed by the coordinator first):

```
W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
TEASTORE_ROOT=$W EXPECTED_HEAD=9a4ea56f86dccdc1855d0e08fa0b04d857ef62dd \
TEASTORE_PREV_PACKAGE=$M/tmp/observability-placement-runtime-teastore-v4-reviewed2/.local/candidate-v4/teastore/gates/run-state-stopped-teastore20-20261002T134204Z/runtime-package.json \
COMPILER=candidate_sweep.py EXPECTED_PLAN=5212f18c8159e6ed400362a8ffaef517db6246598881ce85a7faa3aa7e185601 RUN_COUNT=12 \
nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh sweep1 > $M/scratchpad/gate-drivers/teastore-sweep1.out 2>&1 &
```

## 12. Addendum 2026-10-03 ~13:40Z: attempt 1 stopped at cell 11; decision 25 implemented (`e6d6600`)

Attempt 1 (activation `9a4ea56`) sealed 10 of 11 attempted cells; cell 11 (throttle r10) was blocked on 498
unattributable `conflicting-native-identity` persistence records logged 3-72 ms after readiness. The shared
trace-completeness rule (protocol decision 25) is implemented in the journey unit (commit `e6d6600`; descriptor
`f2e35292…`, plan `c7df47ab…`; cell timing unchanged). Diagnosis, rule with file:line, tests, offline replay (cell 11
seals valid because its defects fall in window (i); the 10 valid cells stay valid), archive
(`tmp/teastore-sweep-evidence/teastore-traffic-sweep-v1-attempt1.tgz`), the relaunch DRY_RUN and command:
`AMENDMENT_TEASTORE_1_DRAFT.md`.
