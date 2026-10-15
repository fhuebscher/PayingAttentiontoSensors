# TeaStore campaign C: declaration (frozen 2026-10-10)

**Status: frozen 2026-10-10** by committing this file alone (coordinator). The placement design was frozen by digest before this launch (d9638e1, BUDGET_PLACEMENT.md step 1), as decision 82 requires. The new seed 20261011, the schedule version and the run-ID keying are the coordinator's engineering defaults (recorded here; they change no measured quantity's definition). No independent review of the harness build was made (judge server unavailable); its checks are the preparing agent's tests with planted defects, the suite comparison and the DRY_RUN. Online Boutique is not part of the test (decision 83).

Campaign C on TeaStore, fb14srv5: a placement test run with **campaign B's shape exactly** (36 cells = 3 blocks x 3
regimes x 4 rates, H10 and H4 as in B), new blocks and run IDs, a new study epoch. Authority: protocol decision 82
(round 22) and D-p4 / decision 74; budget and stop rule `research/traffic-sweep/BUDGET_C.md` (`d5b9af0`, committed alone
before the work): "campaign B's shape ..., new blocks and run IDs, a new study epoch; nothing else changes. Its no-fault
cells are a second fresh false-alarm check (never pooled into a calibration)." Template: `DECLARATION_B_TEASTORE.md`
(frozen `66c83e6`), which stays binding for everything this draft does not change. Every **▶** is a choice of mine that
the user confirms or vetoes at freeze. Scope of every number: **instance** (one SUT, one host).

**Status of this text:** written by the build subagent (Opus). No independent review has been run on it (neither the
`judge` skill nor a separate session); each number below comes from a command or a file named next to it. To freeze:
copy it to **`research/traffic-sweep/DECLARATION_C_TEASTORE.md`** (the name the pinned descriptor's `declaration` field
names) and commit that file alone.

## Binding (filled at freeze)
| item | value |
|---|---|
| harness | worktree `observability-placement-runtime-teastore-protocol`, branch `teastore-protocol-20261002`: epoch commit `9fcc2ab` (`9fcc2ab36e934ede78e8a653b54f81d40668ba47`) and activation **`3b4a513` (`3b4a513ff3c4b00b65131dbc82ba1b472d1c0548`, the HEAD to launch)**, on `bb3717e` (quiet run A2's harness, which is campaign B's `bbb6b11` plus the quiet selector). Any further commit in the worktree changes `EXPECTED_HEAD` and needs a new DRY_RUN |
| epoch | `teastore-traffic-sweep-c-v1`, selected by the committed selector `modules/teastore/execution/study-epoch.json` (`{"schemaVersion": 1, "studyEpoch": "teastore-traffic-sweep-c-v1"}`). TeaStore has no tombstone or admission list: `study_epoch.py` accepts exactly the selector documents it names (now sweep, quiet, B, C) and refuses anything else, so the selector is the activation (as for B and A2) |
| compiler | `modules/teastore/execution/candidate_sweep_c.py` (file sha256 `9967ba14…f27a`); it reads campaign B's compiler `candidate_sweep_b.py` (which reads the sweep compiler) and B's descriptor, all digest-bound (controllers `candidate-compiler`, `sweep-compiler`, `sweep-descriptor`, `sweep-b-compiler`, `sweep-b-descriptor`, `sweep-c-descriptor`) |
| descriptor | `pipelines/campaigns/teastore-traffic-sweep-c-v1.json`, canonical sha256 `ee01552936cfcef21b0826480a1c844e30aa67b418a99555e9f163a270c49711`, file sha256 `919819ae…a287` (generated from B's pinned descriptor `d4d84633…99b7c7`; regenerate, never hand-edit) |
| plan | canonical sha256 **`e55b4f59e3ff8895b3f7d44d89114436fae89b6096fc7d6204d9e0579872eb29`**, 36 cells; identical under `/usr/bin/python3 -B -X pycache_prefix=<fresh> -I` (3.9.6) and `uv run python -I` (3.13.12), after clearing the stale `study_epoch.cpython-39.pyc` from `~/Library/Caches/com.apple.python` (the only cached file of the two touched modules). Plan directory `.local/candidate-v4/teastore/plan-919819ae` (gitignored), materialized under `/usr/bin/python3 -I`; campaign manifest sha256 `2a89f3e19eaea46cdc77efdbb9e2b6b9ddd832efb5e9e45e457a87ef7670e52f`, the same bytes under 3.13 (`campaign.json`, `compiled-plan.json`, `campaign-descriptor.json` compared with `cmp`) |
| earlier epochs | unchanged: sweep plan `88a3017a…9355`, quiet plan `879a81ab…8266`, B descriptor `d4d84633…b7c7` / plan `aa346970…01db`. Since `bb3717e`, under `modules/teastore` and `pipelines/campaigns` three files changed (`study_epoch.py`, the extension ledger, the selector) and two were added (the C compiler and descriptor); `candidate_sweep_b.py`, B's descriptor, `performance_campaign.py`, the validator `candidate_pilot.py`, the runtime adapter and the sweep and quiet files are byte-identical to `bb3717e` **and** to `bbb6b11` (tested) |
| host | fb14srv5 only (TeaStore's lineage-bound host); GATE-RUN window 6 h, minimum remaining at first mutation 19,200 s (both derived, B's values); launcher watcher cap 7 h |
| analysis | none beyond cell validity until the placement is frozen (`BUDGET_C.md` stop rule 4); fault cells are read only through the frozen placement (`research/protocol/BUDGET_PLACEMENT.md` step 6), never to tune it; no-fault cells are a second fresh false-alarm check, never pooled into a calibration |
| declaration file name | **the freeze must use `research/traffic-sweep/DECLARATION_C_TEASTORE.md`** (the descriptor's `declaration` field). Any other name, or any design change, means a regenerated descriptor, new digests, a new commit and a new DRY_RUN |

## Differences from campaign B
| item | campaign B (`DECLARATION_B_TEASTORE.md`) | campaign C |
|---|---|---|
| study epoch / campaign ID | `teastore-traffic-sweep-b-v1` | **`teastore-traffic-sweep-c-v1`** (27 characters, passes the `^[a-z0-9][a-z0-9_-]{0,63}$` campaign-ID guard) |
| compiler | `candidate_sweep_b.py`, built on the sweep compiler | **`candidate_sweep_c.py`, built on B's compiler**: `cell_timing` takes B's own `cell_timing` of the same (regime, rate) and replaces only `ONSET_TIMING_KEYS` (`faultOnsetPhaseOffsetSeconds`, `faultOnsetSeconds`, `scoredWindowSeconds`, `minimumActualStartsByPhase`); the shuffle and onset draws are B's functions called with C's arguments |
| ▶ schedule seed | 20261009 | **20261011** (new draws; distinct from the sweep's 20261003 and quiet's seed, tested) |
| ▶ schedule version (draw context) | `sweep-b-schedule-v1` | **`sweep-c-schedule-v1`** |
| cell order and onset offsets | B's draws | new draws (table below); **all 36 onset offsets differ from B's for the same (regime, rate, block)** (tested); each (regime, rate) pair's 3 blocks still take the 3 thirds of its inter-arrival once each |
| ▶ run IDs | `teastore-traffic-sweep-b-v1/<regime>/r<rate>/b01…b03/full/a01` | **`teastore-traffic-sweep-c-v1/<regime>/r<rate>/b01…b03/full/a01`**: blocks keyed by the epoch name, **not renumbered 4-6** (choice recorded below) |
| descriptor | generated from the sweep's | generated from **B's** pinned descriptor; differs from B's only in `id`, `declaration`, `design.purpose`, `schedule` (`version`, `seed`, `blocks`), `analysis`, `continuation` (+`repeatOfEpoch`) and `derivedFrom` (B's derivation kept as `sweepDerivation`) (tested key by key) |
| plan | `aa346970…01db` | `e55b4f59…eb29`; differs from B's plan only in `studyEpoch`, `descriptorId`, `descriptorSha256`, `scheduleVersion`, `scheduleAllocation`, `blocks`, `analysisBoundary` (tested); `runCount`, budget, window and missingness boundary equal |
| controller set | 56 bound, `+sweep-compiler`, `+sweep-b-descriptor` | B's set `+sweep-b-compiler` (B's compiler is now an input) and `+sweep-c-descriptor` (the epoch descriptor); each is drift-tested by `tests/test_candidate_runtime_adapter.py::test_each_digest_bound_runtime_input_drift_rejects_during_binding_inspection` (+4 parametrisations under the C selector, -2 quiet ones) |
| analysis boundary | analysis v3 before any B cell is read | the frozen placement (see Binding) |
| launcher label / logs | `b1`, `teastore-b1-launch.log`; dry runs `bdry1-3` | **`c1`**, `teastore-c1-launch.log`; dry run **`cdry1`** (passed) |

**Unchanged, by construction and tested:** route, login-only journey, rates (10, 1, 0.2, 0.05 /s), offered counts, client
timeout 15 s, concurrency 240, warm-up 30 s at 10/s, measurement 180 s, hold 60 s, onset base 60 s + seeded offset, the
17 s Q3 drain allowance, doses (decision 50: `docker compose pause auth`; `docker update --cpus 0.1` on persistence,
reverted to `--cpus <NCPU>`), posture `full`, cold start per cell, protocol gates (F1, G1, G2, G4 blocking in fault
cells; G1, G2, G4 in no-fault cells), captures and the system sampler, the **H10/H4 declaration**
`{"version": "h4-h10-v1", "noProbeDuringFault": true, "freezeStamps": true, "freezeFailure": "record-not-block",
"freezeEventToleranceSeconds": 0.25}` on every fault cell (`null` on no-fault cells), producer and validator code (the
files B ran), budget (36 x 525 + 300 = 19,200 s; window 6 h), host.

## ▶ Run-ID choice: keyed by the epoch name, not blocks 4-6
Every C run ID carries `teastore-traffic-sweep-c-v1/` as its first segment, so it cannot equal a sweep (12), quiet A/A2
(40) or B (36) run ID; the test also shows the C strings are B's strings with the epoch segment replaced one for one,
and each compiler's run-ID parser refuses the other's. Blocks 4-6 were not used because the producer's and validator's
`1 <= block <= blocksPerRegime` and the transport's ordinal range are epoch-derived guards (`blocksPerRegime` = 3);
renumbering would need a harness change and new guards (CLAUDE.md "cost the guards"). *Engineering default carried from
B:* compiled artifact roots keep the sweep's form (`effect/auth-freeze/r<rate>/block-<NN>/full/attempt-01`, ...), so
they repeat B's strings; within one campaign they are unique (36 of 36) and across campaigns they are told apart by the
campaign ID and the results root (new setup ID per launch). Any pooling keys on the campaign directory (v3.1's
`pool_key`), never on the run path alone.

## Cell schedule (execution order; regime, rate in journeys/s, onset offset in s)
Throttle = persistence CPU throttle, pause = auth pause, nofault = no-fault cell (its offset places the pseudo window).
From the compiled plan (`uv run python -I`, `candidate_sweep_c.compile_plan`), first run ID
`teastore-traffic-sweep-c-v1/auth-freeze-effect/r0p05/b01/full/a01`:

| block | cells in execution order |
|---|---|
| 1 | pause 0.05 (+13.190), nofault 10 (+0.076), throttle 10 (+0.097), pause 0.2 (+3.091), nofault 1 (+0.294), throttle 0.2 (+0.198), throttle 1 (+0.315), nofault 0.05 (+0.644), pause 1 (+0.912), pause 10 (+0.041), throttle 0.05 (+12.869), nofault 0.2 (+1.701) |
| 2 | pause 1 (+0.645), pause 0.2 (+1.145), nofault 1 (+0.607), nofault 10 (+0.062), nofault 0.2 (+3.908), throttle 1 (+0.750), pause 0.05 (+1.646), throttle 10 (+0.065), pause 10 (+0.012), nofault 0.05 (+12.601), throttle 0.05 (+19.494), throttle 0.2 (+4.434) |
| 3 | throttle 0.05 (+1.891), nofault 1 (+0.841), nofault 0.05 (+16.417), throttle 1 (+0.627), throttle 10 (+0.015), pause 10 (+0.072), pause 0.05 (+17.761), nofault 0.2 (+0.837), pause 0.2 (+3.846), pause 1 (+0.076), nofault 10 (+0.031), throttle 0.2 (+3.158) |

The first cell is an auth pause at 0.05/s; that is the seeded draw, not a rule (no lead cell, as in B).

## Gates and stop rules
- Per cell, as in B: vendored `protocol_gates.py`, the validator's own checks with plan-derived numbers (zero failures in
  no-fault cells; zero before/after failures in fault cells outside the 17 s drain allowance; actual-start floors per
  phase; witness and native-token correlation), H10 blocking inside `sweep-fault-command-stamps`, H4 record-not-block.
- The campaign stops on the first invalid cell (controller behaviour); blocked cells are preserved and flagged.
- `BUDGET_C.md`: harness ready by **2026-10-11 12:00Z** (this build: DRY_RUN passed 2026-10-10 18:20:37Z on `3b4a513`);
  terminal and fetched by **2026-10-12 12:00Z**; at most **2 relaunches**; 30 min per critical-path defect, **3
  critical-path harness defects stop TeaStore's part of C** (this build: **0**); launch only from this declaration
  committed alone plus a passing DRY_RUN, mirrored to wandb; one campaign per host; **no C cell is read (validity fields
  only) before the placement is frozen**.
- **Wall time.** B on this host and harness shape (`teastore-b1-launch.log`, launcher lines only): `auto` 15:23:41Z,
  `oneshot rc=0` 15:35:31Z, journal row 1 by 15:45:45Z, 36 rows by 19:08:55Z, terminal 19:13:59Z: about 3 h 50 min
  from `auto` to terminal (5-minute poll resolution; instance). The compiled estimate is 525 s per cell (5.25 h); window
  6 h, watcher cap 7 h. A launch before about **2026-10-12 04:45Z** meets the 12:00Z terminal deadline even if the run
  uses the full 7 h cap plus about 12 min of setup; fetch time comes on top.

## Checks done (2026-10-10)
- **Worktree suite** (`uv run pytest -q -p no:cacheprovider --ignore tests/test_mlflow_manifest.py -rf`, B's invocation):

  | commit | selector | failed | passed | skipped | collected | wall |
  |---|---|---|---|---|---|---|
  | baseline `bb3717e` | quiet | 20 | 1981 | 180 | 2181 | 347 s |
  | **`3b4a513` (activation, HEAD)** | **C** | **20** | **2056** | **162** | **2238** | 401 s |

  - **FAILED name sets identical** (`diff` of the sorted FAILED lines: 0 lines differ): Hotel materialize x4, OB-LGTM x12,
    OB x1, openspec x1, OTel materialize x1, science-epoch router x1. None is TeaStore. (Same 20 as recorded for B and A2.)
  - Collected 2181 -> 2238 = **+57, fully attributed** (`comm` of the collected node-id lists at both commits):
    `tests/test_teastore_sweep_c.py` +55 (54 at `9fcc2ab` + 1 activation test at `3b4a513`); `tests/test_candidate_runtime_adapter.py`
    `test_each_digest_bound_runtime_input_drift_rejects_during_binding_inspection` +2 (parametrised over the active
    epoch's controller paths: +4 under C (`candidate-compiler`=C's compiler, `sweep-b-compiler`, `sweep-b-descriptor`,
    `sweep-c-descriptor`), -2 quiet ones (`candidate-compiler`=quiet's, `quiet-descriptor`)). Passed +75 = those 57 + the
    **18 effect-cell tests** that the quiet selector skipped and the C selector (fault regimes) runs again (skipped
    180 -> 162).
  - Between the commits, the targeted TeaStore files (`test_teastore_sweep_c`, `_sweep_b`, `_quiet_a2`, `_quiet_calibration`,
    `_traffic_sweep`, `test_readiness`) passed at `9fcc2ab` before commit: 359 passed, 3 skipped.
- **Measurement repo** `tests/test_unbound_names.py`: 317 passed; its module list (315) now includes
  `observability-placement-runtime-teastore-protocol/modules/teastore/execution/candidate_sweep_c.py`.
- **Governance re-pins (the defect class B and A2 preps hit).** TeaStore's `openspec/changes/*/governance.json` pin
  historical `sourceCommit` blobs (as B recorded), so nothing there moves. The equivalent guards are the tests that pin
  the set of harness files changed since a base commit; each one C trips was re-pinned **in the epoch commit, before it
  was committed** (no red commit):
  - `tests/test_teastore_sweep_b.py` `ADDED_FILES` (since `91c4967`) and `tests/test_teastore_quiet_calibration.py`
    `added` (since `0588a41`) now name C's compiler and descriptor; nothing else is allowed to move.
  - `tests/test_teastore_quiet_a2.py`: its three statements about A2's tree (selector names quiet; since `bbb6b11` only the
    selector and the ledger differ; since `91c4967` exactly B's six files differ) now read A2's commit `bb3717e` from git
    objects instead of the working tree, and the quiet `active()` check runs in a tree copy with the quiet selector. Same
    assertions, pinned on the commit they describe, so C's (and later) commits do not falsify them.
  - The C test `test_since_a2_only_c_files_moved_and_the_earlier_epochs_are_byte_identical` is the new guard: since
    `bb3717e` only `study_epoch.py`, the ledger, the selector and C's two files may differ, and B's compiler and
    descriptor, `performance_campaign.py`, both `candidate_pilot.py`, the adapter and the sweep and quiet files equal both
    `bb3717e` and `bbb6b11`.
- **The new tests** (55, `tests/test_teastore_sweep_c.py`): 36 cells / 3 blocks pinned and deterministic, seed 20261011
  distinct from B's, the sweep's and quiet's; **no run-ID collision with sweep, quiet A/A2 or B**, with an in-test
  planted collision; order recomputed from the recorded encoding; with B's seed, epoch and version C's draw functions
  reproduce B's order and onsets; **every cell equals B's cell of the same (regime, rate, block) except the four onset
  keys, and all 36 onsets moved**; the plan and the descriptor differ from B's only in the listed keys; budget = B's; C
  exposes every module-level name of B's compiler (the runtime calls the compiler by name); 3.9 digest; **under B's
  selector the runtime equals `bb3717e`'s** (`active()`, controller paths, campaign manifest, plan, 36 contracts equal
  apart from the moved `study-epoch-loader` digest); the selector activates C in every runtime file (adapter,
  transport, controller, terminal, producer, validator, readiness, witness, native token, orchestrator); malformed C
  selectors and a compiler naming another epoch refuse to load; materialize -> inspect -> 36 contracts -> runtime package
  through the transport (35 cells refused); the producer accepts every C contract and refuses one carrying B's timing;
  the real fault controller against a faked Docker writes the H10 window and the H4 pause events for a C pause cell;
  sealed C cells pass at all 12 (regime, rate) pairs; planted H10 defects block a C pause cell and an H4 defect is
  recorded, not blocking; a C cell validated against B's run key fails; the 36-cell campaign replays its allocation and a
  swapped order is rejected; 3.9 parse floor, unbound-name scan, and the C runtime imports under `/usr/bin/python3 -I`;
  the committed selector names C.
- **Planted defects in the source** (worktree, one at a time, `PYTHONDONTWRITEBYTECODE=1`, `__pycache__` cleared, each
  restored with `git checkout` and the tree checked clean; plants that change the descriptor or plan were re-pinned and
  the descriptor regenerated, so a semantic test has to catch them): **17 of 17 caught** (16 at `9fcc2ab`, the selector
  plant at `3b4a513`; at `9fcc2ab` the selector plant was a no-op, since the selector was still quiet, and is not
  counted). Script and results: session scratchpad `c/plants_c.py`, `plants_c_result_9fcc2ab.json`,
  `plants_c_result_3b4a513.json` (ephemeral; the table is the record).

  | change | plant | first failing test (`tests/test_teastore_sweep_c.py::`) |
  |---|---|---|
  | plan pin | plan digest pin wrong | `test_c_plan_is_36_cells_3_blocks_deterministic_and_pinned` |
  | plan pin | seed = B's 20261009 (re-pinned) | same |
  | plan pin | schedule version = B's (re-pinned) | same |
  | no collision | run IDs under B's epoch name (re-pinned) | `test_no_c_run_id_equals_a_sweep_quiet_or_b_run_id` |
  | no collision | run IDs under the sweep's epoch name (re-pinned) | same |
  | no collision | run IDs under the quiet epoch name (re-pinned) | same |
  | B-shape identity | drain allowance moved to 18 s in fault cells (re-pinned) | `test_every_cell_is_bs_cell_but_for_the_onset` |
  | B-shape identity | onset not re-drawn, B's offsets kept (re-pinned) | same |
  | B-shape identity | descriptor `collection` changed (re-pinned) | `test_the_descriptor_differs_from_bs_only_where_the_epoch_differs` |
  | B-shape identity | harness declares `freezeFailure: block` | `test_c_plan_is_36_cells_3_blocks_deterministic_and_pinned` (compiler refuses: "campaign B's cell shape changed") |
  | selector | C mapped to B's compiler | `test_the_sweep_mode_compiler_follows_the_selector[selector4-teastore-traffic-sweep-c-v1]` |
  | selector | C document removed from the accepted set | same |
  | controller binding | `sweep-b-compiler` not digest-bound | `test_the_selector_activates_campaign_c` |
  | governance | one byte appended to `candidate_sweep_b.py` | `test_since_a2_only_c_files_moved_and_the_earlier_epochs_are_byte_identical` |
  | governance | one byte appended to `performance_campaign.py` | same |
  | governance | one byte appended to the validator `candidate_pilot.py` | same |
  | activation | selector set back to quiet | `test_the_committed_selector_names_campaign_c_and_the_tree_runs_it` |

- **What the tests cannot show.** Nothing new runs on the host that B did not run: same producer, validator and H10/H4
  code (byte-identical files), same doses. B's run (`teastore-b1`) completed 36 journal rows on this host; its cell
  validity was not re-read by me.
- **fb14srv5 idle** (read-only, `ssh -n -o BatchMode=yes -o IdentitiesOnly=yes fb14srv5`, stdout only, 17:48Z):
  0 containers running, 0 `teastore_candidate` containers incl. stopped, 0 running/activating candidate|teastore|hotel|otel|
  boutique units, load 0.12, 359 GB free (guard 40 GB); the dry run's own host facts at 18:20Z agree (0 containers, 359 GB). No TeaStore launcher running locally; the previous campaign (A2
  relaunch 1, `teastore-quietA2r1`) is terminal (`state=complete ... journalRows=40 terminal=True`, 06:25:28Z) and fetched
  (`tmp/teastorequiet2r1-evidence` exists; its byte verification not re-run by me).
- **B's host paths** (report only; nothing moved, renamed or deleted, and no guard asked for it): the results roots on
  srv5 are keyed by setup ID: B `9184b8ef…/teastore-traffic-sweep-b-v1`, A2 relaunch 1 `69abdc89…`, A2 attempt `dc4e26ad…`,
  quiet A `cedad730…`, three sweep roots. C's launch mints a new setup ID; the controller refuses an existing output root.
- **Launcher DRY_RUN** on `3b4a513` (`scratchpad/gate-drivers/teastore-cdry1-launch.log`, rc 0; `teastore-cdry1.out` empty;
  paths shortened):
  ```
  18:20:21Z === teastore launcher cdry1 (ROOT <worktree>, HEAD 3b4a513, dry=1) ===
  18:20:26Z previous campaign status (<worktree> live package): 18:20:26Z state=complete systemd=inactive/dead result=success journalRows=40 terminal=True abort=False lease=False
  18:20:26Z plan: { "descriptorCanonicalSha256": "ee01552936cfcef21b0826480a1c844e30aa67b418a99555e9f163a270c49711", "firstRunId": "teastore-traffic-sweep-c-v1/auth-freeze-effect/r0p05/b01/full/a01", "minimumFirstMutationRemainingSeconds": 19200, "planCanonicalSha256": "e55b4f59e3ff8895b3f7d44d89114436fae89b6096fc7d6204d9e0579872eb29", "runCount": 36, "runWindowHours": 6, "studyEpoch": "teastore-traffic-sweep-c-v1" }
  18:20:26Z drivers read: ROOT=<worktree> STUDY=teastore-traffic-sweep-c-v1 CAMPAIGN_ID=teastore-traffic-sweep-c-v1 RUN_WINDOW_HOURS=6 PLAN_DIR=<worktree>/.local/candidate-v4/teastore/plan-919819ae GATES=<worktree>/.local/candidate-v4/teastore/gates SWEEP=True
  18:20:31Z srv5 host facts (stdout only): ncpu=24 cgroup=systemd/2 candidate_containers=0 containers=0
  18:20:31Z authorization (auto will re-derive if not live): HEAD 3b4a513ff3c4b00b65131dbc82ba1b472d1c0548
  authorized 2026-10-09T23:32:28Z deadline 2026-10-16T23:32:28Z live=True
  provenance derived by `auto` at 2026-10-09T23:32:28Z (no human typed it)
  invariants match=False
  18:20:37Z srv5 free GB (stdout only): 359
  18:20:37Z DRY RUN: all guards passed; stopping before the first mutation
  ```
  `invariants match=False`: today's SETUP-CAMPAIGN is bound to the quiet plan, so `auto` re-derives it onto plan
  `e55b4f59…` (recorded as auto-derived), exactly as for B. **Not shown by the DRY_RUN:** the run-state move, `auto`
  (GATE-PLAN, release bundle, install, readiness), `oneshot` (fresh preflight, GATE-RUN), the 36-cell loop.

## Launch (only after this draft is frozen as `DECLARATION_C_TEASTORE.md` and committed alone)
From the measurement repo. Re-check first: worktree HEAD still `3b4a513f…`, fb14srv5 idle (`docker ps`, `ps`, lease
holder), no other campaign on srv5; repeat the dry run on the day of the launch:
```
W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
cd $M
DRY_RUN=1 TEASTORE_ROOT=$W EXPECTED_HEAD=3b4a513ff3c4b00b65131dbc82ba1b472d1c0548 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_sweep_c.py EXPECTED_PLAN=e55b4f59e3ff8895b3f7d44d89114436fae89b6096fc7d6204d9e0579872eb29 RUN_COUNT=36 \
  zsh scratchpad/gate-drivers/launch_teastore.sh cdry2        # cdry1 passed on 3b4a513
TEASTORE_ROOT=$W EXPECTED_HEAD=3b4a513ff3c4b00b65131dbc82ba1b472d1c0548 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_sweep_c.py EXPECTED_PLAN=e55b4f59e3ff8895b3f7d44d89114436fae89b6096fc7d6204d9e0579872eb29 RUN_COUNT=36 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh c1 > $M/scratchpad/gate-drivers/teastore-c1.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow teastore-c1 scratchpad/gate-drivers/teastore-c1-launch.log \
  > scratchpad/gate-drivers/teastore-c1-wandb.out 2>&1 &
```
What the non-dry launcher does before the first mutation (as for B and A2 relaunch 1): moves A2 relaunch 1's run state in
`.local/candidate-v4/teastore/gates` (`run-authorization.json`, `runtime-package.json`, `gate-run.json`,
`campaign-terminal.json`, `campaign-result/`) into `gates/run-state-before-c1-<stamp>` (move, never delete); `auto`
re-derives SETUP-CAMPAIGN onto plan `e55b4f59…` and mints a new setup ID, so the results root on srv5 is new. After
terminal: fetch to a **new** path (for example `tmp/teastorec1-evidence`), byte-verify host against local, read cell
validity only (`BUDGET_C.md` stop rule 4), then `uv run python tools/wandb_campaign.py cells teastore-c1 tmp/teastorec1-evidence/x`.

## Guards costed (CLAUDE.md "cost the guards, not the cells")
Same shape as B, so every count-shaped guard reads B's values through `study_epoch.active()`: 36 cells, 3 regimes,
blocks 1..3, ordinal 1..12, window 6 h, minimum 19,200 s, watcher cap 7 h, outer lease scope `entire-36-cell-one-shot`
(tested in `test_the_selector_activates_campaign_c`). Campaign-ID regex: 27 characters, passes. Descriptor equality:
the C compiler exposes every name of B's (tested). Receipt key sets: gated on the plan cell's `faultHarness`, which is
B's. Spent-attempt records: TeaStore keeps none (`ATTEMPT = 1`; launches separated by setup ID; C run IDs differ from
every earlier epoch's). Host binding: unchanged. Launcher sweep guard: C is a sweep-mode epoch (`SWEEP=True`, passed).

## Defect count
**0 of 3** critical-path harness defects for TeaStore's part of C. No guard refused; the DRY_RUN passed first time. Not
defects: the changed-file guards in three earlier test files that C's new files trip by design (re-pinned in the epoch
commit before it was committed, about 10 minutes), and the A2 working-tree assertions re-pinned onto A2's commit.

## Open items
1. **Freeze**: the user confirms the ▶ choices (seed 20261011, schedule version `sweep-c-schedule-v1`, run IDs keyed by
   the epoch name rather than blocks 4-6) and the coordinator freezes this text as `DECLARATION_C_TEASTORE.md`, committed
   alone. The ▶ values are not yet in `research/protocol/parameters.json` (I did not edit it).
2. **No independent review** (judge or `adversarial-review`) of `9fcc2ab`, `3b4a513` or this draft. The judge MCP server
   failed to connect in this session.
3. Artifact roots repeat B's strings (engineering default carried from B); pooling must key on the campaign directory.
4. Cosmetic, unchanged: `gate_run.py` prints "LAUNCHING 27-CELL CAMPAIGN".
5. The C launch moves A2 relaunch 1's local run state aside (not deleted); A2 relaunch 1 is fetched at
   `tmp/teastorequiet2r1-evidence` (not re-verified by me).
