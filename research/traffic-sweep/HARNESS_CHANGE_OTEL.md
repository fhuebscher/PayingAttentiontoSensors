# Traffic-sweep harness change: OTel epoch `otel-traffic-sweep-v1` (2026-10-03; committed, NOT activated)

Status: **implemented and committed in the OTel worktree, not activated, not launched.** Worktree
`../observability-placement-runtime-otel-protocol`, branch `otel-protocol-20261002`, base `92be2b7`:

- `2184ef0` OTel traffic-sweep epoch otel-traffic-sweep-v1, not activated (13 files)
- `d101fda` Re-pin OTel v2 governance source bindings to 2184ef0 (the repository's rule since cc777bb)
- `cfc2261` review fixes (§9: B1 generator removal, M2 target resolved at the barrier); descriptor and plan re-pinned
- `c78216f` Re-pin governance source bindings to cfc2261 (candidate_terminal.py moved)
- `902ec99` UTF-8 defect class (§4b): target command output decoded with replacement, sweep container logs kept as raw bytes
- `3d9b7fe` Re-pin governance source bindings to 902ec99 — **HEAD, the commit the dry run ran on**

The only host contact was the launcher's `DRY_RUN=1` read-only guards against fb14srv6, twice (07:07Z at c78216f, 07:35Z
at 3d9b7fe; §7). Hotel's worktree, srv4 and the
TeaStore worktree were not touched. Scope labels: **instance** for every file:line (at the commits above), **method** for
the epoch design. Declaration draft: `DECLARATION_OTEL_DRAFT.md` (every mapping choice marked ▶). Budget:
`BUDGET_REPLICATION.md` (launch-ready by 2026-10-04 12:00Z: the harness side is, as of the 07:35Z dry run; the declaration
freeze, the activation commit and a dry run on it remain). Critical-path harness
defects against the stop rule's 3: none surfaced on a host. Before any host contact, the review's B1 (Compose `--scale 0`
against a required dependency, unverified) and the coordinator's UTF-8 class (§4b) were each fixed in under 30 minutes; if
the user counts them, the count is 2 of 3.

## 0. Addendum 2026-10-03 (after the user's decisions: "accept all, M1 99 %") — supersedes the digests below

- `275492f` **M1**: a sweep cell is blocked only if fewer than 99 % of its successful pre-onset and post-recovery
  requests (no-fault cells: every successful request) carry the complete route trace (own trace id + exactly
  frontendproxy/frontend/productcatalogservice). Pooled over the two windows (my reading of "fewer than 99 % of successful
  pre-onset and post-recovery requests"); pass iff complete ≥ ceil(0.99 × successful); zero successful blocks.
  `candidate_remote.trace_completeness` evaluates it **on the target** before the next cell and writes
  `trace-completeness.json` (per window and pooled: complete, successful, share, required count, minimum); the terminal
  replays it byte-for-byte and puts it in the cell report. The minimum (0.99) and the edge slack (5 s) are compiled
  timing, not literals. Frozen cells keep the old per-request rule. Descriptor gains `declaration` =
  `research/traffic-sweep/DECLARATION_OTEL.md (measurement repo; frozen 2026-10-03)`; construction blockers drop the
  declaration/selector items. **Descriptor `78d2f0c43533d6371048498d3525b67166e9c1b6bdfbc84d61e2db0d9785aefa`, attempt-1
  plan `779b908d2fb5ba815f2477c6d470fe98ca853b354d690a1663ac05980a5d4100`**, identical under `/usr/bin/python3 -I` (3.9.6)
  and 3.13. The 3.9 run used a fresh `-X pycache_prefix` directory, so no cached bytecode could be read; I did not delete
  `~/Library/Caches/com.apple.python` (20 MB; 0 `.pyc` entries under the OTel worktree's path) — deleting needs a yes.
  `ec043ec` re-pins governance (candidate_runtime.py, candidate_terminal.py moved).
- Tests (M1): one dropped trace in 1,800 seals valid with 1799/1800 recorded — fails on 3d9b7fe's terminal ("pre-fault
  request … completed successfully without the full … correlation", observed); 20 dropped pre-onset traces at 10/s block
  on the target; at 0.05/s one incomplete trace of 5 (3 pre-onset + 2 post-recovery) blocks; two planted record defects
  rejected by the terminal.
- **Low-rate consequence of the 99 % rule (reported, not changed):** misses tolerated per cell = successful − ceil(0.99 ×
  successful), assuming every request succeeds (plan arithmetic, revert ≈ onset + 60.3 s): 10/s fault cells ~10 of ~1,097,
  no-fault 10/s 18 of 1,800; 1/s 1 of 110 (fault) / 180 (no-fault); **0.2/s and 0.05/s tolerate no miss** (denominators
  21, 22, 36 and 5, 6, 9). Below 100 successful requests the 99 % rule is identical to the old "every request" rule. If
  the user wants low-rate cells to tolerate one miss, the rule needs a minimum count (e.g. apply the share only when
  successful ≥ 100, else allow ≤ 1 miss) — a preregistration decision, not made here.
- `6380cce` **activation**: `execution/study-epoch.json`, `ADMITTED_STUDY_EPOCHS = ("otel-traffic-sweep-v1",)` in
  `candidate_setup.py` and `candidate_remote.py`, ledger entry. No governance-bound file moved.
- Suites (failures by name, `-rA`): before activation (ec043ec) 29 failed / 2173 passed; after (6380cce) 29 failed /
  2029 passed / 144 skipped (the conftest's frozen-only set); the same 29 failures as the 92be2b7 baseline in both, none
  new. Measurement repo `uv run pytest -q`: 925 passed, 1 skipped, 3 xfailed.
- Dry run on 6380cce (`scratchpad/gate-drivers/otel-sweep-sweepdry3-launch.log`): compiled `otel-traffic-sweep-v1 12
  779b908d…`; drivers `otel-traffic-sweep-v1 otel-traffic-sweep-v1 3 <worktree>`; probe receipt PROBE OK; host fb14srv6:
  0 units, 0 containers, lease free, 250 GB free, 0 campaign paths; "DRY RUN: all guards passed" at 11:36:00Z, exit 0;
  0 untracked files.
- Launch (not done): `cd <measurement repo>; LAUNCH_APPROVED=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol
  COMPILER=candidate_sweep.py EXPECTED_PLAN=779b908d2fb5ba815f2477c6d470fe98ca853b354d690a1663ac05980a5d4100 RUN_COUNT=12
  CAMPAIGN=otel-traffic-sweep-v1 LOG_PREFIX=otel-sweep nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh
  sweep1 6380cceffa7b2970e18c364e23c97780e5c2683a > scratchpad/gate-drivers/otel-sweep1.out 2>&1 &`; follower:
  `nohup uv run python tools/wandb_campaign.py follow otel-sweep1 scratchpad/gate-drivers/otel-sweep-sweep1-launch.log >
  scratchpad/gate-drivers/otel-sweep1-wandb.out 2>&1 &`.

## 1. What the change is

- **Submodule first.** `upstream/opentelemetry-demo` was uninitialised (`git submodule status` showed `-`), the state that
  killed Hotel's first sweep launch in `auto`. Initialised at the pinned `2d4661e` from the main repo's module store
  (`git submodule update --init --reference <main>/.git/modules/upstream/opentelemetry-demo`), then `git repack -a -d`
  and `objects/info/alternates` removed; `git fsck --connectivity-only` clean. The harness's own bundle-source check
  (`candidate_transport.build_release_bundle`: upstream HEAD == the allocation's `upstreamCommit`, both bundles verify)
  passed offline (§7).
- **A second epoch, not an edit of the frozen one.** `execution/candidate_sweep.py` (new) compiles
  `otel-traffic-sweep-v1`; its descriptor is **generated** from the byte-pinned offpath descriptor
  (`derive_sweep_descriptor`; a test compares the file's bytes). `candidate_pilot.py`, the offpath/v1/v2/v3 descriptors, the
  catalog, the overlays, the target allocation, `materialize.py` and `workload.py` are byte-identical to `92be2b7`
  (parametrised test against `git show 92be2b7:<path>`).
- **Selector.** Active only when the committed file `modules/otel-demo/execution/study-epoch.json` holds
  `{"schemaVersion": 1, "studyEpoch": "otel-traffic-sweep-v1"}`. Without it: `STUDY_EPOCH` offpath, `RUN_COUNT 36`,
  `MINIMUM_REMAINING_SECONDS 36000`, run window 11 h, the same 12 `CONTROLLER_PATHS` keys (tested). With it,
  `candidate_runtime.py:671-720` swaps the compiler to `candidate_sweep.py`, the descriptor, and derives `RUN_COUNT 12`,
  `MINIMUM_REMAINING_SECONDS 5472`, `RUN_WINDOW_HOURS 3` from the compiler; `CONTROLLER_PATHS` gains five digest-bound
  entries (`candidate-descriptor`, `frozen-compiler`, `frozen-descriptor`, `protocol-gates`, `study-epoch-selector`). A
  selector naming anything else refuses to load (tested). **The selector is not created** and the tombstone is unchanged.
- **Plan (defaults).** Rates 10, 1, 0.2, 0.05 /s on `GET /api/products/66VCHSJNUP` (frontendproxy → frontend →
  productcatalogservice). Warm-up 30 s at 10/s. Measurement 180 s. Onset 60 s + seeded offset in [0, 1/rate) (Hotel's
  `onset_phase_offset`, one stratum, keyed by regime, rate and block, never by attempt). Hold 60 s. Regimes no-fault
  calibration, frontend-pause, productcatalog-cpu-throttle (0.1 CPU). Posture `full`. One block = 3 × 4 = **12 cells**;
  Fisher-Yates with SHA-256 draws from seed 20261003, lead cell frontend-pause at 10/s. Offered 1800 / 180 / 36 / 9.
  Client timeout 15 s (the harness's). Concurrency 300 = ceil(2 × 10/s × 15 s). Upstream loadgenerator removed right after
  `up`, before readiness (`docker compose rm --stop --force loadgenerator`).
  Digests: descriptor `bd698569…1d5f`, attempt-1 plan `c60a04d4…94e2`, identical under `/usr/bin/python3 -I` (3.9.6,
  fresh `-X pycache_prefix`) and `uv run python -I` (3.13.12) (command in §6).
- **Run IDs** keep the frozen rule (first 24 hex of sha256 of the canonical runKey; runKey gains `requestsPerSecond`).
- **Wall budget, derived** (`candidate_sweep.py`, "derived"): cell period = 30 warm-up + 1 barrier lead + 180 measurement
  + 120 overhead = 331 s; minimum remaining at first mutation = 12 × 331 + 900 (the controller's per-cell deadline
  reserve) + 600 (cleanup) = **5,472 s**; GATE-RUN window = ceil((5,472 + 3,600 approval slack) / 3,600) = **3 h**. The 120 s
  overhead is an engineering default over the measured 80–84 s of run 3 and v3r1 (13.4 / 13.3 min per 720 s-timed cell).

## 2. Diff per file (`git diff --numstat 92be2b7 3d9b7fe`, governance.json omitted)

| file | +/− | change |
|---|---|---|
| `execution/candidate_sweep.py` (new) | 797 | compiler: parameters, seeded schedule and onset, phase-slot check, derived budget, descriptor generator (`--emit-descriptor`), `--print-digests`, the frozen compiler's API (`load_descriptor`, `compile_plan`, `validate_plan`, `plan_attempt`, `materialize`) |
| `pipelines/campaigns/otel-traffic-sweep-v1.json` (new) | 539 | generated; byte-compared with the generator by a test |
| `validation/protocol_gates.py` (new) | 696 | `cp` of `src/obsplacement/protocol_gates.py` (sha256 `1b3c8a3b…6590`, source commit d3fc741) |
| `execution/candidate_remote.py` (target) | +598 / −13 | timed-package run count and minimum remaining from compiled timing (`:252-266`); timed dispatch in `run_cell` (`:1767`); `run_sweep_cell` (`:1605`): `compose up`, then `compose rm --stop --force loadgenerator` and an engine-label proof of absence (after the review; 2184ef0 had `up --scale loadgenerator=0`), stack readiness, 10/s route warm-up, route workload with per-request ledger on the fault receipt's monotonic clock and padded to the window end (`:1299`), `inject_sweep_fault` (`:1390`: target container resolved at the barrier and its pre-state inspected 3 s before onset, pre-command stamp, pause or `docker update --cpus`, stamped route probes, revert to the original quota or every host CPU), `--timestamps` application log, F1/G1/G2/G4 on the target (`protocol_gate_record`, `:1571`); `command` (`:212`) decodes UTF-8 with replacement and has a `binary` mode (§4b), posture proof without the generator; zero path-check cells for a timed package (`:1881`); ordinal range = run count (`:1937`). The frozen `run_cell`, `inject_fault`, `run_workload`, `wait_ready`, `workload_path_check` are AST-identical to 92be2b7 apart from the dispatch (test) |
| `execution/candidate_runtime.py` | +242 / −6 | selector (`:652-720`), `_frozen_pilot_module` for the v1 ledger and the offpath readiness fixture, block flattening (`:1854`), `sweep_cell_timing` (`:3560`: a contract's timing must equal the active plan's), `_sweep_cell_contract` (`:3576`); `_target_command` decodes with replacement (§4b) |
| `validation/candidate_terminal.py` | +358 / −13 | `validate_sweep_cell` (`:1002`) and its ledger, intervention, application-log, generator and gate-replay checks; route path as the required correlation (`:429`); posture proof without the generator (`:597`); `validate_single_posture`; run count from the runtime (`:1211`); the collector carrier decoded with replacement (§4b) |
| `execution/candidate_setup.py` (target) | +29 / −3 | `EPOCH_CONTROLLER_PATHS` / `controller_paths(epoch)` (`:98-111`): the installer binds exactly the runtime's controller set per epoch (tested both ways); tombstone comment; `command` decodes with replacement (§4b) |
| `execution/candidate_runtime_adapter.py` | +8 / −1 | compiler from `CONTROLLER_PATHS`; `CAMPAIGN_ID = STUDY_EPOCH` under the selector (`:216`); sweep has no spent attempts |
| `drivers/gate_driver_config.py` | +25 / −3 | `study`, `campaign_id`, `run_window_hours` from ROOT's selector via ROOT's own runtime (`:121-140`); **ROOT not rebound** (it is already `Path(__file__).parents[3]`, the worktree itself) |
| `extension-ledger.yaml` | +10 | classifies the two new module files |
| `tests/test_otel_traffic_sweep.py` (new) | 1122 | 73 tests, §5 |
| `tests/conftest.py` (new) | 83 | with the selector present, skips the 58 frozen-epoch-only tests (the exact set that failed under a trial activation); no effect without it |
| `tests/test_otel_materialize.py` | +6 / −2 | pinned ledger count 25 → 27 (+1 once the selector exists) |

Not edited: Hotel's and TeaStore's worktrees, any frozen OTel descriptor, `candidate_pilot.py`, `materialize.py`, the
overlays, the catalog. Measurement repo: only this file, the declaration draft (both untracked) and the uncommitted launcher overrides (§8).

## 3. Every guard that pins the current shape: old → new

Found by reading every literal that the offpath run path, its package validation and its terminal compare against (36, 600,
120, 1, 32, 15, 45, 4 postures, TARGET_PATH, 36000, 11 h, `candidate_pilot.py`), plus GATES.md's OTel inventory.

| site | old (offpath) | new (sweep, from the plan) | frozen epoch |
|---|---|---|---|
| remote `validate_package` / `_run_campaign` | `RUN_COUNT = 36` (count, cells, ids, terminal) | `expected_run_count`: every cell's `timing.planRunCount` (one value) = 12 | 36; a frozen package with a timed cell is refused |
| remote `validate_package` | `EXPECTED_MINIMUM_REMAINING_SECONDS = 36_000` | `timing.planMinimumRemainingSeconds` = 5,472 | 36,000 |
| remote `_run_campaign` | ordinal ∈ 1..4 (postures) | 1..run count | 1..4 |
| remote `require_path_check_before_faults` | exactly one no-fault full gating cell before every fault | zero gating cells (the lead cell is a fault by design; the route path is checked per cell) | unchanged |
| remote warm-up | `window.warmupSeconds` 120 s of journeys at 1/s | `timing.warmupSeconds` 30 s at `warmupRequestsPerSecond` 10 on the route | unchanged |
| remote workload | journeys, rate 1, offered = duration × rate (600), concurrency 32, 15 s step | route GET, `timing` rate / offered / concurrency 300 / timeout 15 s; returns ≥ barrier + measurement | unchanged |
| remote fault | onset 45 / hold 15 from the contract's fault | `timing.faultOnsetSeconds` (60 + offset) / `faultHoldSeconds` 60; probes stamped; throttle action | unchanged |
| remote post-revert readiness | a checkout journey inside the window | route probes (stamped) | unchanged |
| remote posture proof | all 19 services | 18 (loadgenerator removed after `up`), `notStartedServices` | unchanged (byte-equal to 92be2b7's output, test) |
| runtime `RUN_COUNT`, `MINIMUM_REMAINING_SECONDS` | 36, 36,000 | compiler `TOTAL_RUNS` 12, `MINIMUM_REMAINING_SECONDS` 5,472 | 36, 36,000 |
| driver `run_window_hours` | 11 | compiler `RUN_WINDOW_HOURS` 3 | 11 |
| runtime `build_cell_contract` | window 120 / 600, descriptor workload (1/s, 600, 32, 15) | `_sweep_cell_contract`: every number from `timing` | unchanged (package byte-equal modulo controller digests, test) |
| runtime `inspect_compiled_plan` | flattens `regimeRoots` | also `blocks` | identical |
| runtime readiness seams / v1 ledger | `_pilot_module().OFFPATH_SYNC_PATH`, `.EPOCHS` | `_frozen_pilot_module()` (same file whatever is active) | identical |
| terminal `EXPECTED_RUNS = 36` | 36 | `runtime.RUN_COUNT` | 36 |
| terminal workload identity | checkout URL, int rate, 2 steps | `_validate_sweep_ledger`: route URL, float rate == timing, concurrency, timeout, duration, offered, per-slot identity and offset, start ≥ slot − 0.05 s, outcome replay | unchanged |
| terminal correlation | `TARGET_PATH` (11 checkout services) required | the route's 3 services required (must lie inside the producer's clip) | unchanged |
| terminal posture | `TARGET_PATH` ⊆ signals; 19 services; 4-posture lattice | route ⊆ signals; 18 services; `validate_single_posture` | unchanged |
| terminal intervention | pause/stop predicates, onset ≥ 45, hold ≥ 15 | `_validate_sweep_intervention`: pause / cpu-throttle predicates, same barrier as the ledger, onset ∈ [schedule − 0.05 s, …], hold ≥ 60, stamps ordered, probes inside their phase | unchanged |
| setup `FIXED_CONTROLLER_PATHS` | 12 keys | `controller_paths(epoch)`: 17 for the sweep | 12 |
| adapter `pilot`, `CAMPAIGN_ID` | `candidate_pilot.py`, `otel-demo-offpath-v1` | active compiler; the epoch id | unchanged |
| launcher | compiler path literal, log name, approval var | `COMPILER`, `LOG_PREFIX`, `LAUNCH_APPROVED`; new driver-identity check | defaults unchanged |

Checked and left unchanged (each still caps a future reshape): remote `SAFE_NAME` (62 chars) and the campaign id ≤ 40
chars (`otel-traffic-sweep-v1` is 21; Compose project `otel_candidate_v4_otel_traffic_sweep_v1`); per-cell deadline
reserve 900 s (`run_cell`); `COLLECTOR_SETTLE_SECONDS` 15; cleanup reserve 600; `MAX_GATE_AGE_SECONDS` 900 (15-min
preflight); the readiness seam pins `dockerVersion == "29.6.1"` (a target observation: if srv6's Docker moved since
2026-10-01, readiness refuses — `?`, not checked here); `TimeoutStartSec=15000` (start timeout of a `Type=exec` unit, not
a run limit); the catalog's four postures; v1 ledger `EXPECTED_CELLS = 18`.

## 4. Protocol gates and evidence integrity

- Vendored byte-identically; the measurement repo's `test_vendored_copy_is_byte_identical` now runs for the OTel copy and
  passes; `test_otel_traffic_sweep.py` repeats the check.
- **Evaluated on the target, per cell, before the next cell** (unlike Hotel, where the cell runner calls the terminal): the
  remote controller is a lone copy in `.controller/`, so it loads the gates from the installed release
  (`<releaseRoot>/repository/modules/otel-demo/validation/protocol_gates.py`, repository mode 0755) only after their sha256
  equals the installed `protocol-gates` controller digest. A non-pass of F1 (fault cells), G1, G2 or G4 writes
  `protocol-gates.json` and invalidates the cell; the campaign stops. The terminal validator replays the record with the
  local copy and requires byte equality.
- Mapping (GATES.md table, one clock): scheduled = `i / rate` (the plan slot); started / ended = the request's
  `startedMonotonic` / `endedMonotonic` − the ledger's `barrierMonotonic`, which is the fault receipt's barrier (checked);
  status = `outcome` (ok iff HTTP 200; timeout iff the client error says "timed out"; else failed). Fault: onset issued =
  `actualOnsetMonotonicOffsetSeconds` (pre-command), onset returned = `appliedMonotonicOffsetSeconds` (after the change is
  observed; an upper bound), revert issued / returned = `revertingMonotonicOffsetSeconds` / `actualOffsetMonotonicOffsetSeconds`.
  Plan offered, rate, window from the compiled timing; profile rate = the ledger's rate.
- Not evaluated: P0, R1, R2 (inputs not written); G4 channel scope ledger-only; as Hotel. G4 cannot fail inside a cell that
  already passed the ledger checks (as Hotel's review m1); F1's `onsetCommandBounded` is a constant.
- F-ADH-085: the stamp is taken immediately before the command; the target container is resolved at the barrier (one
  Compose round trip, a minute early) and only a direct `docker inspect` runs 3 s before the onset, so the stamp sits on
  the schedule. In the fake-driven runs the onset was 0.003–0.52 s (simulated) after schedule.
- Probe windows: every route probe inside the measurement is in the receipt's `probes` (phase `during-fault` once,
  `post-revert` until ready), with start/end on the ledger's clock; the terminal checks each lies inside its phase.

## 4b. Non-UTF-8 container output (the class that aborted Hotel's sweep1 attempt 2)

Coordinator note, 2026-10-03: Hotel's sweep1 attempt 2 aborted after 25 valid cells because `docker compose logs` output
was decoded as strict UTF-8 (`subprocess.run(text=True)`) and one container emitted byte 0xbf; TeaStore hit the same class
in review (9181964); Hotel's fix is 7a1d97b. Every place this harness decodes subprocess or container output, checked by
`/usr/bin/grep -n "text=True\|read_text\|.decode("` over `modules/otel-demo`:

| site | before | after (`902ec99`) |
|---|---|---|
| `candidate_remote.command` (target controller: compose logs, docker inspect/exec/top, tshark, …) | `text=True` (strict, locale) | UTF-8 with `errors="replace"`; `binary=True` returns bytes |
| `run_sweep_cell` collector, proxy and application logs | text, written with `write_text` | fetched as bytes; `otelcol.log` and `application.log` written raw; parsed after `decode("utf-8", "replace")` |
| frozen `run_cell` logs | strict text | replacement text through the fixed wrapper (byte-identical output for valid UTF-8; its code is unchanged, AST test) |
| `candidate_setup.command` (install: git, compose pull/build, inspect) | `text=True` | UTF-8 with replacement |
| `candidate_runtime._target_command` (readiness producer on the target) | `text=True` | UTF-8 with replacement |
| `candidate_terminal._validate_carrier_coverage` (`otelcol.log`) | `decode(errors="strict")` | `errors="replace"` |
| `candidate_terminal` `application.log` | already `errors="replace"` | unchanged |
| local ssh/status/fetch decoding in `candidate_runtime` (`:3920`ff), `drivers/gate_run.py` | already `errors="replace"` | unchanged |
| `candidate_runtime.resolve_entrypoint_launch` (`:796`, plan-time stub execution on the laptop, output written by the stubs) | `text=True` | unchanged (controlled output; not container output) |
| JSON artefacts the harness writes itself (`read_json`, `_json`) | strict | unchanged (ASCII by `json.dumps`; strictness is a tamper check) |

Regression: the fake target's container logs carry a stray 0xbf and its text mode decodes strictly, as the old wrapper did;
`test_target_command_wrappers_survive_a_non_utf8_byte` runs the real wrappers on `/usr/bin/printf 'x\277y'`. Against
cfc2261's four modules the five fake-driven `run_cell` tests and the wrapper test fail (6 failed, observed); at `902ec99`
they pass.

## 5. Tests (commands run 2026-10-03; counts from the pytest summary lines)

| suite | before (92be2b7 + submodule) | after (d101fda) | delta accounted |
|---|---|---|---|
| worktree whole suite, `TMPDIR=<scratch> uv run pytest -q -p no:cacheprovider -rA --ignore=tests/test_mlflow_manifest.py` | 29 failed, 2095 passed | 29 failed, **2168 passed** (at 3d9b7fe) | +73 = `test_otel_traffic_sweep.py`; the same 29 failures by name (Hotel materialize with deathstarbench uninitialised, Online Boutique, TeaStore, phase-1 control universe, science router: none OTel) |
| same, under a trial activation (selector + tombstone + ledger entry, uncommitted, reverted after) | — | 30 failed, 2023 passed, 144 skipped (at 3d9b7fe) | skipped = the conftest's 58 frozen-only tests (144 with parameters); 1 new failure by name, `test_teastore_native_bridge_patch::test_v2_patch_applies…`, which asserts a clean tree (the trial edits were uncommitted; it passes on a committed activation as on every clean tree). The governance test passes: the activation touches no bound file |
| measurement repo `uv run pytest -q` | 918 passed, 1 skipped, 3 xfailed (task baseline) | **925 passed, 1 skipped, 3 xfailed** (at 3d9b7fe) | +3 mine by name: `test_unbound_names` for `otel-demo/candidate_sweep.py` and `otel-demo/protocol_gates.py`, `test_vendored_copy_is_byte_identical[…otel-protocol…]`; +4 inferred from the TeaStore-protocol worktree that another agent is changing (61 vs teastore-sys's 58 unbound-name modules, and its vendored copy), not checked against a by-name baseline |

`tests/test_otel_traffic_sweep.py` (73): plan pinned, deterministic, seed recorded, lead cell first; offered = rate × 180;
onset offsets in range, distinct, attempt-independent; no-offset counterfactual; budget arithmetic; planted descriptor/plan
edits refused; the route's upstream code; frozen files byte-identical to 92be2b7 (11); frozen digests and runtime shape;
frozen functions AST-identical to 92be2b7 apart from the dispatch (13); the frozen execution package and posture proof equal
the base code's output (git-archived 92be2b7 tree); the selector activates every reader (runtime, setup, adapter, driver
config) and a bad selector refuses; the full GATE chain on the selected tree (sentences say `runs=12`, the 1 h window is
refused, the target controller accepts the package only once admitted, planted package defects refused); **fake-driven
executions of the target's `run_cell`** (compressed clock 30×, fake Docker/Compose CLI, fake Envoy route that blocks while
the frontend is paused, fault commands taking 1.5 s simulated) for frontend-pause at 10 and 0.05/s, throttle at 10 and
0.05/s and no-fault at 0.2/s, each accepted by the terminal validator; G2 failing on the target at 0.05/s and stopping the
cell; a generator container invalidating the cell before any traffic; 17 planted artifact defects each rejected with its
own message; vendoring; 3.9 grammar and deferred annotations of the six target files; the plan digest under
`/usr/bin/python3 -I` (3.9.6) equals 3.13's.

**Planted code defects (each seen failing): 14 of 14 caught**, at 2184ef0, again at cfc2261 and again at 3d9b7fe, one
at a time in the worktree, file restored and its sha256 re-checked after each (session scratchpad `otel-sweep/mutations.py`): generator left running (no removal after `up`; at 2184ef0: no `--scale`); onset stamped after the
command (F-ADH-085); probes not stamped; throttle reverted with `--cpus 0`; workload returning before the window end; a
failed gate not invalidating the cell; logs without `--timestamps`; terminal not replaying the gates; runtime trusting a
contract's own timing; lead cell not first; offpath concurrency 32 kept; frozen contracts routed to the sweep builder;
terminal accepting an unrestored throttle; remote using the frozen 36 for a timed package.

Not tested: any real Docker, Compose, Envoy or collector behaviour (no Docker daemon was started for this work). The
generator removal now uses `up` then `compose rm --stop --force loadgenerator`, plain commands whose semantics do not
depend on the Compose version; the first version (`up --scale loadgenerator=0` with `frontendproxy`'s required
`depends_on: loadgenerator`) was replaced after the review (§9, B1) because that semantics was unverified. Also not tested: a 60 s pause at 10/s on OTel (never run; offpath held 15 s), the real cell period, the remote
gate-module load from the installed release.

## 6. Cell duration estimate

Timed 211 s per cell (30 + 1 + 180) plus the measured offpath overhead of 80–84 s ⇒ **≈ 290–300 s per cell, 12 cells ≈
58–60 min** (`?` until the first cells run; instance, srv6). The budget assumes 331 s per cell (66 min) and the window
leaves 3 h. Not included: `auto` (bundle, upload, one-shot install with 8 local image builds) before GATE-RUN. A DRY_RUN
stops before the first mutation, so it cannot measure a cell; the first observable is the gap between the first two cell
receipts' `completedAt` on the host. Digest command: `/usr/bin/python3 -X pycache_prefix=<fresh> -I digest.py
<worktree>/modules/otel-demo/execution/candidate_sweep.py` and the same under `uv run python -I` → both print
`bd698569… c60a04d4… 12 5472 3`.

## 7. Offline bundle build and dry run

Both at HEAD `3d9b7fe`, with a **temporary local activation**: the selector file only (untracked, so the launcher's
tracked-clean check holds; ROOT needs no edit because the drivers resolve ROOT to the worktree they live in), written before
and deleted right after; `git status` clean before and after (checked). The tombstone tuple is not read by a dry run. The
posture-probe receipt was copied first into the worktree's gitignored `.local/candidate-v4/otel-demo/gates/` from
`tmp/otel-v2-admission` (sha256 `722acb30…99aa`; the driver's `require_probe_receipt` accepted it offline). The same pair
also passed at `c78216f` (07:07Z) before the UTF-8 fix.

Offline release bundle (session scratchpad `otel-sweep/offline_bundle.py`: `adapter.inspect_campaign` +
`candidate_transport.build_release_bundle`, output and `TMPDIR` in the scratchpad, no remote action):

```
config otel-traffic-sweep-v1 otel-traffic-sweep-v1 3
study otel-traffic-sweep-v1 campaign otel-traffic-sweep-v1 runs 12 plan c60a04d4aa0f647340538da6976ed18eb3e6e0f747af114a6e0b087bc75a94e2
framework 3d9b7feb0e3ed7dbb63d1ce8d7026236f221eac4 upstream 2d4661e4897aa7b2d2ddbb5ef8c4824ca8a1b88d
bundle 2a78d987b92e34e7 4423932 upstream bundle 6182d9785dd77b70 43303146
materialized source b5f3fc41c60c544d611d592eff9a3a7ff05c5a0345b01da7047910a9f1919911
controllers 17 [base-compose-overlay, candidate-compiler, candidate-descriptor, candidate-posture-overlay, candidate-terminal,
  frozen-compiler, frozen-descriptor, materializer, posture-catalog, protocol-gates, remote-compose-controller,
  remote-setup-controller, runtime-admission, study-epoch-selector, target-contract, unsupported-disposition, workload]
APPROVE GATE-PLAN study=otel-traffic-sweep-v1 change=admit-otel-demo-candidate-pilot-v2 campaign=otel-traffic-sweep-v1
  transport=root@fb14srv6 execution=stig:1016:1016+998 source=/home/stig/observability-placement-candidate-v4-otel-srv6/
  otel-traffic-sweep-v1-3d9b7feb0e3e/source artifacts=/home/stig/observability-placement-candidate-v4-runs/otel-traffic-sweep-v1
  framework=3d9b7feb… plan=c60a04d4… … runs=12 attempt=1 one-shot no-retry no-substitution no-rerandomization …
```

The upstream checkout passed the transport's pinned-commit check and both bundles verified (`git bundle verify`). The
materialized-source digest is the same as at `c78216f` (the materializer did not change). The bundle is of a commit without
the selector; the activation commit's bundle will carry it, and its digest is among the 17 the installer checks.

Launcher dry run (`scratchpad/gate-drivers/otel-sweep-sweepdry2-launch.log`, verbatim except the long fault-design line):

```
07:35:11Z === otel offpath launcher sweepdry2 (HEAD 3d9b7feb0e3ed7dbb63d1ce8d7026236f221eac4 on otel-protocol-20261002, compiler candidate_sweep.py, plan c60a04d4aa0f647340538da6976ed18eb3e6e0f747af114a6e0b087bc75a94e2, 12 cells, attempt 1, dry=1) ===
07:35:11Z untracked files (tolerated, as in runs 1-3): 1
fault design {... frontend-pause, productcatalog-cpu-throttle, omitted net-delay ...}
07:35:11Z compiled: otel-traffic-sweep-v1 12 c60a04d4aa0f647340538da6976ed18eb3e6e0f747af114a6e0b087bc75a94e2
07:35:11Z drivers: otel-traffic-sweep-v1 otel-traffic-sweep-v1 3 /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-otel-protocol
probe receipt 2026-09-23T10:03:11Z 23dd90bb20f5 0 42
07:35:37Z host fb14srv6: running units=0 containers=0 lease holders=[] free GB=250 otel-traffic-sweep-v1 paths=0
07:35:37Z DRY: would archive run-phase state and the plan dir, read SETUP-CAMPAIGN status, and renew it onto c60a04d4… if expired/drifted (worktree …/observability-placement-runtime-otel-protocol)
07:35:37Z DRY RUN: all guards passed; stopping before the first mutation
```

Exit 0. The one untracked file was the temporary selector. Not exercised by a dry run (by the launcher's design): SETUP-
CAMPAIGN status (it materialises the plan dir), `auto` (bundle upload, install, readiness), GATE-RUN, any cell. srv6 was
idle (0 units, 0 containers, lease free, 250 GB free) at 07:35Z.

## 8. Activation (the main session's step; nothing below is done)

One framework commit in `../observability-placement-runtime-otel-protocol` (it re-derives every gate sentence; SETUP-CAMPAIGN
is auto-derived by `campaign_setup.py auto`):

1. New file `modules/otel-demo/execution/study-epoch.json`, exactly
   `{"schemaVersion": 1, "studyEpoch": "otel-traffic-sweep-v1"}` + newline.
2. `modules/otel-demo/execution/candidate_setup.py` and `modules/otel-demo/execution/candidate_remote.py`: replace
   `ADMITTED_STUDY_EPOCHS: tuple[str, ...] = ("otel-demo-offpath-v1",)` with
   `ADMITTED_STUDY_EPOCHS: tuple[str, ...] = ("otel-traffic-sweep-v1",)` (the tombstone names only the current epoch, as
   v3 → offpath did; `test_repository_tombstones_agree…` asserts it and is in the conftest skip list).
3. `modules/otel-demo/extension-ledger.yaml`: before `classes:` add
   `  - path: execution/study-epoch.json` / `class: validator` / `purpose: Study-epoch selector; names otel-traffic-sweep-v1,
   which candidate_runtime then compiles, binds and admits.` / `origin: framework-owned` / `upstream_patch: false`
   (the module audit refuses an unclassified file; `test_otel_materialize` then expects 28).
4. Nothing to re-pin: none of the three edited files is a governance source binding (checked against `sourceBindings`).
   ROOT is not edited: `drivers/gate_driver_config.py` already resolves ROOT to the worktree it lives in; the launcher's
   `OTEL_WORKTREE` selects that worktree.
5. Expect, after the commit: `uv run pytest -q` = the 29 baseline failures, 58 frozen-only tests skipped (with parameters
   144), everything else passing (the trial activation in §5 showed exactly this apart from two uncommitted-tree effects).

Launch (after the declaration is frozen and committed alone, and after the dry run passes on the activation commit; the
launcher reads `HEAD` and refuses any other):

```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
DRY_RUN=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol COMPILER=candidate_sweep.py \
  EXPECTED_PLAN=c60a04d4aa0f647340538da6976ed18eb3e6e0f747af114a6e0b087bc75a94e2 RUN_COUNT=12 \
  CAMPAIGN=otel-traffic-sweep-v1 LOG_PREFIX=otel-sweep \
  zsh scratchpad/gate-drivers/launch_otel_offpath.sh sweepdry2 <activation-commit>
LAUNCH_APPROVED=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol COMPILER=candidate_sweep.py \
  EXPECTED_PLAN=c60a04d4aa0f647340538da6976ed18eb3e6e0f747af114a6e0b087bc75a94e2 RUN_COUNT=12 \
  CAMPAIGN=otel-traffic-sweep-v1 LOG_PREFIX=otel-sweep \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh sweep1 <activation-commit> \
  > scratchpad/gate-drivers/otel-sweep1.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow otel-sweep1 scratchpad/gate-drivers/otel-sweep-sweep1-launch.log \
  > scratchpad/gate-drivers/otel-sweep1-wandb.out 2>&1 &
```

`EXPECTED_PLAN` is attempt 1 (`OTEL_CANDIDATE_ATTEMPT` unset); a relaunch under attempt 2 needs that plan's digest
(`uv run python modules/otel-demo/execution/candidate_sweep.py --print-digests --attempt 2`). The watcher cap is
`run_window_hours + 1` = 4 h. Check the lead cell (frontend-pause at 10/s) on the host as soon as its receipt exists:
`upstream-generator.json` empty, `protocol-gates.json` valid, `intervention.json` probes and onset lateness.

Launcher edit (`scratchpad/gate-drivers/launch_otel_offpath.sh`, tracked in the measurement repo, left uncommitted; sha256 before
`db50739358f19689a7674dd32d2bbbd3f64554b6756074357415766e3dfc1a9a`): `COMPILER` (default `candidate_pilot.py`),
`LOG_PREFIX` (default `otel-offpath`), `LAUNCH_APPROVED` (alias of `OFFPATH_APPROVED`), and a new guard: the drivers'
`CONFIG.study` and `campaign_id` must equal `$CAMPAIGN` and `CONFIG.root` the worktree, before any host contact. Defaults
unchanged; `OTEL_WORKTREE`, `EXPECTED_PLAN`, `RUN_COUNT`, `CAMPAIGN` already existed.

The re-pin rule used for `d101fda` (and earlier cc777bb, 92be2b7), for any later commit that moves a bound file:

```python
# for each governance.json sourceBinding whose file sha256 now differs: assert bytes at <commit> == working tree,
# then set "sha256" = now and "sourceCommit" = <commit>; same for protocolBindings.compiler.sha256.
```

## 9. Independent review

One `adversarial-review` subagent (model fable), read-only, neutral prompt, on `2184ef0` + `d101fda`; it re-ran
`tests/test_otel_traffic_sweep.py` (72 passed at the time) and checked the governance re-pin, the vendored bytes, the selector and
derived guards (no 36 / 36000 / 11 literal left on the sweep path), the route against upstream 2d4661e, the frozen-epoch
tests, producer/validator symmetry, the 3.9 floor. Its answer: (c) frozen epoch unchanged — yes; (b) terminal accepts
exactly valid cells — yes as far as code shows; (a) executes as declared — not shown.

| finding | action |
|---|---|
| **B1** `up --scale loadgenerator=0` while frontendproxy has a required `depends_on: loadgenerator`: Compose-version semantics, untested (the fake made `up` a no-op); would kill every cell | **fixed in cfc2261**: `up`, then `compose rm --stop --force loadgenerator` before readiness; absence still proven by engine label; fake asserts the order; planted removal-skip caught |
| **M1** every successful pre/post request at 10/s must carry the full 3-service trace (`candidate_terminal.py` correlation rule, the offpath rule); one dropped span at 1,800 requests invalidates the cell and stops the campaign; never run on OTel at 10/s or with a 60 s pause | **open, preregistration-class** (Q14); the lead cell is the test |
| **M2** the target was resolved by `docker compose ps` 3 s before onset; a CLI slower than 3 s makes the stamp late (F1 1 s) | **fixed in cfc2261**: resolved at the barrier; only `docker inspect` 3 s before onset |
| m G4 `rateEqualsProfile` compares the ledger with itself and `validityRecorded` is constant (as Hotel) | recorded (§4); the terminal checks the ledger rate against the compiled timing |
| m R2.recovery is always `—` (revert ≥ 120 s = window − 60) | corrected in the draft ("always") |
| m the warm-up leaves no validated artifact (ledger discarded, as offpath) | recorded |
| "activation moves candidate_setup.py / candidate_remote.py and needs another re-pin" | not so: neither is a governance source binding (checked against `sourceBindings`, §8 step 4) |

Not reviewed: the uncommitted launcher edits (read only), anything on a host. Fable was used; no judge MCP call.

## 10. Open questions for the user (▶ = preregistration class)

1. ▶ Route `GET /api/products/66VCHSJNUP` (flagd off the route) vs `OLJCESPC7Z` (flagd on it).
2. ▶ Client timeout 15 s (the harness's) vs Hotel's 1 s: P1/P2 constants become +15 s and 1 + 15 × rate + 2.
3. ▶ Concurrency 300 (rule: cap ≥ 2 × rate × timeout) vs offpath's 32 (which stalls starts during a pause at 10/s).
4. ▶ Throttle target productcatalogservice at 0.1 CPU; revert = original quota, else every host CPU (24): the unset
   original is not restorable through `docker update`.
5. ▶ Net delay omitted: no no-sudo mechanism (srv6 sudo = tcpdump only; sidecar netem not built).
6. ▶ Metric export interval left at the SDK default (60 s): a declared limit on every OTLP-metric sensor.
7. ▶ Loadgenerator off: removed after `up` and before readiness (it runs for the seconds in between; an emission change;
   OTel sweep cost numbers are not poolable with v3/offpath).
8. ▶ One block: P4's "≥ 3 of 4 episodes" cannot apply; descriptive per-pair comparison proposed.
9. The OTel analysis extension of `research/detection-time/` (carrier `otelcol.log`, `application.log` prefix, probe
   windows, the 1-episode design) does not exist; the declaration requires it fixed before results are looked at.
10. ▶ Stack readiness = one checkout journey before the warm-up (unchanged harness rule; it reaches Kafka and the
    consumers before the window), then one route 200.
11. ▶ Posture-probe receipt reused from 2026-09-23 (bound to the probe-script bytes and the upstream pin only, both
    unchanged); it was not re-run for this epoch. Copied into the worktree's gitignored `.local/…/gates/`.
12. G2 at 0.05/s: one pre-onset failure blocks and stops the campaign (Hotel Q14).
14. ▶ (review M1) Per-request trace completeness at 10/s: every successful pre-fault / post-readiness request must carry
    the full frontendproxy + frontend + productcatalogservice trace, else the cell is invalid and the campaign stops. Keep
    (the offpath rule, now at 1,800 requests per cell), or allow a declared share?
13. Engineering defaults recorded: overhead 120 s, approval slack 3,600 s, pre-onset resolve 3 s, probe timeout 5 s,
    readiness poll 1 s / 300 s, start tolerance 0.05 s, onset-early tolerance 0.05 s, seed 20261003.
