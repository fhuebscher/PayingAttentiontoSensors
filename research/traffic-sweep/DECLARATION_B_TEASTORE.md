# TeaStore campaign B: declaration (FROZEN 2026-10-09, committed alone before launch)

Part B of `research/traffic-sweep/NEXT_CAMPAIGNS_PROPOSAL.md` on TeaStore, fb14srv5: three more blocks of the traffic
sweep's 12 cells, on a harness with **H10** and **H4** (`research/protocol/METHODOLOGY_HARDENING.md`). Authority:
protocol decision 49 (3 more blocks, after the H10/H4 harness change), decision 50 (fault doses inherited, a fixed
factor) and decision 69 (H4 is record, don't block), `research/PROTOCOL_DRAFT_20261002.md` round 10. Budget and stop rule: `research/traffic-sweep/BUDGET_B.md`
(`92ca1c7`, committed alone before the work; user's confirmation of the 2026-10-12 terminal deadline `ac4b992`). Cell
shape: the frozen TeaStore sweep (`DECLARATION_TEASTORE.md` `c9f072b`, `AMENDMENT_TEASTORE_1.md` `bbbd80b`,
`AMENDMENT_TEASTORE_2.md` `b840353`). Template: `DECLARATION_QUIET_TEASTORE.md`. Every **▶** is a choice of mine that the
user confirms or vetoes at freeze; values without ▶ are the sweep's frozen values, copied by construction (the compiler
reads them from the sweep's compiler). Scope of every number: instance (one SUT, one host).

**Status of this text:** written by the build session. No independent review has been run on it (neither the `judge`
skill nor a separate session); the numbers below were each taken from a command or a file named next to them.

## Binding (filled at freeze)
| item | value |
|---|---|
| harness | worktree `observability-placement-runtime-teastore-protocol`, branch `teastore-protocol-20261002`: epoch commit `c4669a1` (`c4669a1caf648efcab80e33b1094ec1dfd968452`), activation `5188852` (`518885241f03aa43f43f8bfdce42a17f101cf3fd`) and decision 69's commit **`bbb6b11` (`bbb6b1165410be5bd4eb304b56c4eac9490310d1`, the HEAD to launch)**, on `91c4967` (the quiet calibration's harness). Any further commit in the worktree changes `EXPECTED_HEAD` and needs a new DRY_RUN |
| epoch | `teastore-traffic-sweep-b-v1`, selected by the committed selector `modules/teastore/execution/study-epoch.json` (`study_epoch.py` accepts exactly three selector documents now: sweep, quiet, B) |
| compiler | `modules/teastore/execution/candidate_sweep_b.py`; it reads `candidate_sweep.py` and the sweep descriptor, both digest-bound (controllers `sweep-compiler`, `sweep-descriptor`, `sweep-b-descriptor`, `candidate-compiler`; 56 bound controllers, as the quiet run) |
| descriptor | `pipelines/campaigns/teastore-traffic-sweep-b-v1.json`, canonical sha256 `d4d846337263f57bfe2b9a0d8de8f0f9cde319157ad8e7611b62faecfe99b7c7`, file sha256 `e96492ce…3169` (generated from the pinned sweep descriptor `f90bd64c…160a`; regenerate, never hand-edit) |
| plan | canonical sha256 `aa3469708cc7f27f3262e12a6293a4a77bc6af1ec9e06cc4156f8bdd123101db`, 36 cells; identical under `/usr/bin/python3 -I` (3.9.6, fresh `-X pycache_prefix`) and `uv run python -I` (3.13.12). Plan directory `.local/candidate-v4/teastore/plan-e96492ce` (gitignored; the earlier `plan-19ffb637` is stale), campaign manifest sha256 `1c6f887d06a4191a2ad7963147a5e33e29f17f7ec141c158e39edbc244ce541b`, the same bytes under 3.9 and 3.13 (`campaign.json`, `compiled-plan.json`, `campaign-descriptor.json` compared with `cmp`) |
| sweep and quiet epochs | unchanged: sweep descriptor `f90bd64c…160a` / plan `88a3017a…9355`; quiet descriptor `338226d0…315b` / plan `879a81ab…8266`; under `modules/teastore` and `pipelines/campaigns` five files changed (`study_epoch.py`, `performance_campaign.py`, the validator `candidate_pilot.py`, the extension ledger, the selector) and two were added (`candidate_sweep_b.py`, the B descriptor); every other file is byte-identical to `91c4967` (tested, see "Checks done") |
| host | fb14srv5 only (TeaStore's lineage-bound host); GATE-RUN window 6 h (derived), minimum remaining at first mutation 19,200 s (derived), launcher watcher cap 7 h |
| analysis | none until analysis v3 is frozen and reviewed (`BUDGET_B.md` stop rule 4) |
| declaration file name | **the freeze must use `research/traffic-sweep/DECLARATION_B_TEASTORE.md`**: the pinned descriptor's `declaration` field names that path. Any other name, or any change to a design value, means a regenerated descriptor, new digests, a new commit and a new DRY_RUN |

## Purpose
One episode per (fault, rate) is descriptive only (`NEXT_CAMPAIGNS_PROPOSAL.md` section B). This campaign adds **3
episodes** of every (regime, rate) pair the sweep ran once, giving 4 in all, like Hotel. Each block's 4 no-fault cells
also add 3 × 180 s of fault-free time per rate (the pseudo window and cell shape are the sweep's). The run makes no
claim about detection; analysis v3 decides what is read from it and how it pools with the sweep's block.

## Design
- **36 cells = 3 blocks × 12 pairs**: 3 regimes (`no-fault-cost`, `auth-freeze-effect`,
  `persistence-cpu-throttle-effect`) × 4 rates (10, 1, 0.2, 0.05 login journeys/s) × 3 blocks. Posture `full` only; cold
  start per cell.
- **Every cell is the sweep's cell of the same regime and rate.** `candidate_sweep_b.cell_timing` takes
  `candidate_sweep.cell_timing(<the sweep's run ID of that regime and rate>, regime, rate)` and replaces only five keys
  (`OWN_TIMING_KEYS`): `faultOnsetPhaseOffsetSeconds`, `faultOnsetSeconds`, `scoredWindowSeconds` (this epoch's seeded
  onset), `minimumActualStartsByPhase` (the sweep's plan-derived floor rule, recomputed for the new onset; fault cells)
  and `faultHarness` (new, below). Tested key by key against the sweep's own function. From the sweep, unchanged:
  - route `POST /tools.descartes.teastore.webui/loginAction`, the 302 to `/` followed, one login per journey, workload
    `login-only-v1`; open loop from the shared barrier; offered = rate × 180 (1800, 180, 36, 9);
  - client timeout 15 s; concurrency 240; warm-up 30 s at 10/s untokenised; measurement 180 s;
  - **doses (decision 50, inherited, a fixed factor):** `docker compose pause auth` for 60 s; `docker update --cpus 0.1`
    on `persistence` for 60 s, reverted with `--cpus <docker info NCPU>` (`--cpus 0` is a no-op); net-delay still omitted;
  - the Q3 drain allowance (client timeout + 2 s = 17 s, fault cells), decision 25's journey-unit trace-completeness rule,
    the narrowed JVM-frame rule of the witness-log secret scan, the protocol gates (F1, G1, G2, G4 blocking in fault cells;
    G1, G2, G4 in no-fault cells), captures and the cgroup system sampler (5 s, 37 samples).
- ▶ **Onset.** Fault onset (and each no-fault cell's pseudo window) = 60 s + a seeded offset: the sweep's stratified rule,
  here with this epoch's name, seed and run IDs and **3 strata per (regime, rate) pair**: the 3 blocks of a pair take
  the 3 thirds of its inter-arrival once each, in a seeded order (tested). Given the sweep's seed, epoch and stratum
  count the function reproduces the sweep's own 12 offsets (tested).
- ▶ **Order.** Each block holds all 12 pairs once, in a Fisher-Yates order drawn by SHA-256 from **seed 20261009** (the
  sweep's draw encoding with schedule version `sweep-b-schedule-v1`; own seed, not the sweep's 20261003). **No lead
  cell:** the sweep's lead cell (pause at 10/s first) existed to show the first 10/s pause early, and that ran. The seed
  and the draw encoding are recorded in the descriptor (`schedule`), every block's run-ID order in the descriptor and in
  the compiled plan (`blocks[].order`, `orderSha256`); a test recomputes the order from the recorded encoding without the
  compiler. Run order (regime, rate, onset offset in s; throttle = persistence CPU throttle, pause = auth pause):

  | block | cells in execution order |
  |---|---|
  | 1 | throttle 10 (+0.079), pause 10 (+0.095), throttle 1 (+0.228), pause 1 (+0.401), nofault 0.05 (+16.355), nofault 1 (+0.604), pause 0.2 (+4.813), nofault 0.2 (+1.504), throttle 0.2 (+4.004), throttle 0.05 (+14.600), pause 0.05 (+18.715), nofault 10 (+0.073) |
  | 2 | throttle 0.2 (+2.523), throttle 0.05 (+12.342), throttle 10 (+0.005), throttle 1 (+0.894), nofault 1 (+0.195), nofault 0.05 (+4.993), pause 0.2 (+1.654), pause 10 (+0.048), pause 0.05 (+3.322), pause 1 (+0.983), nofault 10 (+0.029), nofault 0.2 (+2.863) |
  | 3 | nofault 0.05 (+9.444), throttle 0.2 (+1.639), pause 1 (+0.087), throttle 0.05 (+2.661), throttle 1 (+0.527), nofault 0.2 (+4.332), throttle 10 (+0.045), nofault 1 (+0.790), pause 10 (+0.017), pause 0.05 (+9.557), pause 0.2 (+2.927), nofault 10 (+0.045) |

  The first cell is a CPU throttle at 10/s, a first-position the sweep did not have (that was the pause); that is the
  seeded draw, not a rule. Block 2 runs the 4 throttle cells back to back and then the 4 pause cells back to back; also the draw.
- ▶ **A separate epoch**, not a new attempt of the sweep. Run IDs have the sweep's shape with this epoch's name,
  `teastore-traffic-sweep-b-v1/<regime>/r<rate>/b01…b03/full/a01`, so no run ID can equal a sweep or quiet run ID
  (tested). Campaign paths are `runs/<regime>/b<NN>-<ordinal>-full`. *Engineering default:* compiled artifact roots keep
  the sweep's form (`effect/auth-freeze/r<rate>/block-<NN>/full/attempt-01`, ...), so block 01's twelve roots are the same
  strings as the sweep's twelve; within one campaign they are unique (36 of 36), across epochs they are told apart by the
  campaign ID and the results root (a new setup ID per launch). Any pooling must key on the campaign ID.
- The sweep's and the quiet run's descriptors, plans, setup history and archived run state stay as they are.

## What changes in the harness (binding): H10 and H4
Both are carried by the plan cell's `timing.faultHarness`, present in the 24 fault cells and `null` in the 12 no-fault
cells, bound by the plan digest:

```
{"version": "h4-h10-v1", "noProbeDuringFault": true, "freezeStamps": true, "freezeFailure": "record-not-block",
 "freezeEventToleranceSeconds": 0.25}
```
A cell without it (every sweep and quiet cell) takes the old code path: the sweep's fault receipt is equal to the one
`91c4967` writes (tested: receipts and `docker`/`compose` call lists equal under a fake clock), and no `docker events`
query runs.

**Finding for H10 on TeaStore.** The sweep's controller already issues no SUT request between the onset command and the
revert. State checks are `docker inspect`; the only SUT requests in a fault cell are the stamped `GET /status`
readiness probes, which start after the revert command returned (`DECLARATION_TEASTORE.md`: "does not probe the login
route during the fault"; the validator already rejected a probe starting before `revertCommandReturned`). So the
Hotel-style 5 s probe handicap under a pause has no TeaStore counterpart, and H10 changes no probe schedule. What B adds
is the **contract**: the window is recorded, enforced and re-derived, and a violation is refuted by a test with a planted
defect. Hotel's and OTel's H10 may differ in this respect (not examined here).

**H10, as implemented** (`performance_campaign.inject_fault`, `wait_ready_stamped`; validator
`_fault_harness_problem`):
- window: from the onset command's issue to the later of the scored window's end (`faultOnsetSeconds +
  faultHoldSeconds`, plan values) and the revert command's return;
- the controller refuses to issue a readiness probe before the window's end (raises; the cell is invalid; it is not
  delayed), and records the window in `sweep.probePolicy`;
- the validator re-derives the window from the plan and the receipt's own stamps and rejects any probe that starts
  inside it, and any `probePolicy` that differs from the re-derivation.

**H4, as implemented.** No new artifact: the records live in `intervention.json` under `sweep` (already required,
hashed into the receipt and validated for fault cells), so the artifact lists, the content manifest and the terminal's
required files are unchanged. (`docker-events.json` of the proposal's example is not created; its content is
`sweep.freezeStamps.events`.)

Schema, `intervention.json` → `sweep` (B fault cells only; the other keys are the sweep's: `schemaVersion`,
`onsetSource`, `commandStamps`, `probes`, `throttle`):
```
sweep.probePolicy = {
  "version": "h4-h10-v1",
  "noProbeFromMonotonicOffsetSeconds":      <onset command issued>,
  "scoredWindowEndMonotonicOffsetSeconds":  <faultOnsetSeconds + faultHoldSeconds>,
  "noProbeUntilMonotonicOffsetSeconds":     <max(scored window end, revert command returned)> }
sweep.freezeStamps = {
  "schemaVersion": 1, "version": "h4-h10-v1",
  "scenario": "auth-freeze" | "persistence-cpu-throttle", "targetContainerId": <64 hex>,
  "toleranceSeconds": 0.25,
  "commands": {                      # equal to sweep.commandStamps, monotonic seconds from the shared barrier
    "onsetIssuedMonotonicOffsetSeconds", "onsetReturnedMonotonicOffsetSeconds",
    "revertIssuedMonotonicOffsetSeconds", "revertReturnedMonotonicOffsetSeconds" },
  "readbacks": [                     # one per duringStateSamples row: manifested, hold-midpoint, hold-end
    { "phase", "issuedMonotonicOffsetSeconds" (= the sample's observedAtMonotonicOffsetSeconds),
      "returnedMonotonicOffsetSeconds", "paused": bool, "nanoCpus": int | null } ],   # nanoCpus: throttle only
  "status": "recorded" | "missing",   # decision 69: "missing" iff failures is non-empty
  "failures": [ <reason text>, ... ],   # every producer-side failure of the H4 capture, e.g. "docker events query: ..."
  "failureCount": <len(failures)>,
  "clock":  null (throttle) | {
    "barrierWallEpochSeconds", "barrierMonotonicOffsetSeconds": 0.0,
    "collectedWallEpochSeconds", "collectedMonotonicOffsetSeconds", "mapping": <text> },
  "events": null (throttle) | {
    "command": <argv>, "returnCode": 0, "error": null,
    "rows": [ { "action": "pause", "type": "container", "containerId", "timeNano": <ns, host wall clock>,
                "monotonicOffsetSeconds" },
              { "action": "unpause", ... } ] } }
```
- Pause (`auth-freeze`): after the readiness, the controller replays the target's Docker `pause` and `unpause` events
  (`timeout 30 docker events --since <onset issued − 2 s> --until <now> --filter container=<id> --filter type=container
  --filter event=pause --filter event=unpause --format '{{json .}}'`, an already-past `--until` so it returns at once)
  and keeps only `Action`, `Type`, `Actor.ID` and `timeNano` of each row (no actor attributes). It is not one of the
  cell's commands: `operational.commandResults` keeps exactly the pause and the unpause.
- Event time → cell monotonic offset: linear between the barrier (offset 0, its wall time) and the collection instant
  (its wall time and monotonic offset, read together), i.e.
  `offset = (timeNano/1e9 − barrierWallEpochSeconds) × collectedMonotonicOffsetSeconds / (collectedWallEpochSeconds −
  barrierWallEpochSeconds)`. Over a cell this cancels wall-clock slew against the monotonic clock. The validator
  recomputes it (tolerance 1e-6 s).
- Throttle (`persistence-cpu-throttle`): no Docker event is asked for. The record is the four command stamps and the
  applied-state readback stamps: each `docker inspect` readback's issue and return, with the quota it showed.
- **Intervals the analysis may take (instance-level reading, not a mechanism):** pause onset ∈ [onsetIssued, pause
  event], pause end ∈ [revertIssued, unpause event] (decision 54's [command, Docker pause event + δ] ambiguity window
  starts here); throttle onset ∈ [onsetIssued, `readbacks[0].returned`] with the quota observed applied at
  `readbacks[0]`; the throttle revert is bounded by [revertIssued, revertReturned] only (the post-revert state is read
  once, after the readiness).
- **Which H4 status counts:** pooling and analysis use the reader's own re-derivation (equivalently the validator's `h4.status`), never the receipt's `freezeStamps.status`, which reflects producer-visible failures only. Known review notes, not blocking: two comments in `performance_campaign.py` (:1929, :1958) still say the validator blocks on H4 (stale; the code does not), and the campaign report's check text says "All 27 cells".
- **H4 is record, don't block (user decision 69, 2026-10-09).** A failed or contradictory Docker events query or
  freeze-stamp check leaves the cell **valid**. The producer sets `status: "missing"` and lists every reason in `failures`
  (events query non-zero return, timeout or exception; not exactly one `pause` then one `unpause`; an event naming
  another container or type; any exception while building the record), with their number in `failureCount`; the
  validator re-derives the reasons from the receipt's own stamps and reports them as `h4` = `{status, reasons,
  failureCount}` in the `sweep-fault-command-stamps` observation (and counts producer-reported ones too). A reader of a
  `missing` cell falls back to [onset command issued, onset command returned] (`commands` is always present). The
  validator's H4 re-derivation covers: header (version, scenario, target = the receipt's, tolerance = the plan's),
  `commands` = the command stamps, `readbacks` one per state sample with ordered stamps and the paused state or applied
  quota, `status`/`failures`/`failureCount` consistent, and for a pause: return code 0, exactly one `pause` then one
  `unpause` of this container, offsets equal to the recomputation, the pause offset inside [onsetIssued − 0.25,
  onsetReturned + 0.25] and the unpause offset inside [revertIssued − 0.25, revertReturned + 0.25], collected after the last
  readiness probe; throttle: `events` and `clock` are `null`.
- **What still blocks (inside the existing check `sweep-fault-command-stamps`):**
  - the `sweep` key set equals the sweep's plus `probePolicy` and `freezeStamps` exactly when the plan cell declares
    `faultHarness` (a B cell with the sweep's receipt shape, a missing `freezeStamps` key, and a sweep cell with the
    records are all rejected; `freezeStamps: null` is not a missing key and is recorded as missing);
  - **H10:** `probePolicy` equals its re-derivation and every probe starts at or after `noProbeUntil`; the plan's
    `faultHarness` must be the declared one.
  - ▶ **Tolerance 0.25 s** is an engineering default (a Docker pause event is emitted by the daemon between the
    command's issue and its return, so after the clock mapping it must fall inside the command interval; the slack covers
    rounding and clock-pair read-out). It is in the plan (`freezeEventToleranceSeconds`), so a change re-pins. A contradiction with it is now a `missing` record, not a block.

## Gates and stop rules
- **Blocking per cell, evaluated on the target before the next cell** (vendored `protocol_gates.py`, byte-identical to
  the measurement repo's): F1 (fault cells), G1, G2, G4; R2.recovery recorded; P0, R1, R2 not evaluated; G4 ledger-only.
  The frozen validator's own checks all run, with plan-derived numbers: zero failures in no-fault cells, zero before/after
  failures in fault cells outside the 17 s drain allowance, the plan-derived actual-start floor per phase
  (`max(1, ceil(0.5 × scheduled slots))`: 301/300/290 at 10/s, 31/30/29 at 1/s, 7/6/5 at 0.2/s, 2/2/1 at 0.05/s for
  before/during/after), witness and native-token correlation for every scored journey.
- **The campaign stops on the first invalid cell** (controller behaviour).
- **Budget and stop rule (`BUDGET_B.md`):**
  - harness ready by **2026-10-10 12:00Z** (this build: DRY_RUN passed 2026-10-09 12:42Z on `bbb6b11`);
  - terminal by **2026-10-12 12:00Z**;
  - at most **2 relaunches**; TeaStore on fb14srv5, one campaign per host;
  - 30 min per critical-path defect; **3 critical-path harness defects stop TeaStore's part of B** and go to the user
    (this build: **0**, see "Defects and time");
  - launch only from this declaration committed alone plus a passing DRY_RUN on the host, mirrored to wandb;
  - no B evidence is analysed until analysis v3 is frozen and reviewed.
- **Wall time.** Sweep relaunch 2 (fb14srv5, 2026-10-04) measured a cell period of 324.9-423.4 s (median 330.5, mean
  343.2; 11 consecutive runtime-journal gaps over its 12 cells, which include the two fault types; instance). That
  projects to 3.3 h (median) to 3.4 h (mean) for 36 cells, ≤ 4.2 h if every cell took the slowest period, plus ~11 min for
  install and authorization and ~6 min to the first journal row. The compiled estimate is the sweep's 525 s per cell,
  5.25 h. The events query adds one short daemon call per pause cell (not measured on a real cell).
- **GATE-RUN window and watcher cap.** The sweep's rule: minimum remaining at first mutation = 36 × 525 + 300 = 19,200 s;
  window = ceil((19,200 + 1,800) / 3,600) = **6 h**. The controller starts no cell once the deadline minus the 300 s
  cleanup reserve has passed; at the slowest measured period the last cell starts ~4.1 h (35 × 423.4 s) after the first.
  The launcher's watcher cap is window + 1 = **7 h**.

## Analysis
No analysis of this run's evidence until analysis v3 is frozen and reviewed (`BUDGET_B.md` stop rule 4; B is the first
data read under v3). Until then only the harness's validity record is read: the runtime journal, cell validity, the
terminal validation and the fetch manifest. Analysis v3 fixes before any look how B pools with the sweep's block (the
campaign ID is the key) and what the pause events and readback stamps are used for.

## Monitoring (not evidence)
High-level progress is mirrored to wandb (`tools/wandb_campaign.py follow`). The evidence of record is the fetched
campaign directory.

## Launch (after: this declaration frozen as `DECLARATION_B_TEASTORE.md` and committed alone; the DRY_RUN below already passed)
From the measurement repo:
```
W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
cd $M
DRY_RUN=1 TEASTORE_ROOT=$W EXPECTED_HEAD=bbb6b1165410be5bd4eb304b56c4eac9490310d1 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_sweep_b.py EXPECTED_PLAN=aa3469708cc7f27f3262e12a6293a4a77bc6af1ec9e06cc4156f8bdd123101db RUN_COUNT=36 \
  zsh scratchpad/gate-drivers/launch_teastore.sh bdry3        # repeat on the day of the launch (bdry2 passed on bbb6b11)
TEASTORE_ROOT=$W EXPECTED_HEAD=bbb6b1165410be5bd4eb304b56c4eac9490310d1 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_sweep_b.py EXPECTED_PLAN=aa3469708cc7f27f3262e12a6293a4a77bc6af1ec9e06cc4156f8bdd123101db RUN_COUNT=36 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh b1 > $M/scratchpad/gate-drivers/teastore-b1.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow teastore-b1 scratchpad/gate-drivers/teastore-b1-launch.log \
  > scratchpad/gate-drivers/teastore-b1-wandb.out 2>&1 &
```
What the non-dry launcher does before the first mutation (as for the quiet run): reads the previous campaign's status from
the worktree's live runtime package (now: the quiet run, `state=complete terminal=True journalRows=40`, rc 3); moves
that run state in `.local/candidate-v4/teastore/gates` (`run-authorization.json`, `runtime-package.json`,
`gate-run.json`, `campaign-terminal.json`) into `gates/run-state-before-b1-<stamp>` (move, never delete; the quiet run's
evidence is fetched at `tmp/teastorequiet1-evidence`, whose byte verification I did not re-run); `auto` re-derives
SETUP-CAMPAIGN onto plan `aa346970…` (today's authorization is bound to the quiet plan, `invariants match=False`),
recorded as auto-derived; `auto` mints a new setup ID, so the results root on srv5 is new. After terminal: fetch to a new
path under `tmp/`, byte-verify against the host, check cell validity only.

## Checks done (2026-10-09)
- **Worktree suite** (`uv run pytest -q -p no:cacheprovider --ignore tests/test_mlflow_manifest.py -rf`, the quiet
  declaration's invocation):

  | commit | selector | failed | passed | skipped | collected |
  |---|---|---|---|---|---|
  | baseline `91c4967` | quiet | 20 | 1858 | 180 | 2058 |
  | `c4669a1` + the two quiet-test edits, before commit (run before they were made: 22 failed, 1967 passed, 180 skipped) | quiet | 20 | 1969 (derived: 1967 + the 2 repaired) | 180 | 2169 |
  | `5188852` (activation) | B | 20 | 1987 | 162 | 2169 |
  | **`bbb6b11` (decision 69, HEAD)** | **B** | **20** | **1994** | **162** | **2176** |

  - The 20 failures are the same by name as the baseline's (`comm` of the sorted FAILED lines: 0 lines differ): Hotel
    materialize ×4, OB-LGTM ×12, OB ×1, openspec ×1, OTel materialize ×1, science-epoch router ×1. None is TeaStore.
  - Collected 2058 → 2176 = **+118 = `tests/test_teastore_sweep_b.py`** (111 at `5188852`, +7 for decision 69: 3 producer-side failure cases and 4 recorded-not-blocked plants, net of the rewritten failed-events test). Passed +136 = those 118 + **18 effect-cell
    tests** that the quiet selector skipped and the B selector (which has the sweep's fault regimes) runs again, all
    passing (skipped 180 → 162, the sweep baseline's count). Nothing unexplained.
  - The first full run after the epoch commit had 2 extra failures, both in `test_teastore_quiet_calibration.py`
    (`test_the_sweep_epoch_is_byte_identical…`, `test_under_the_sweep_selector_the_runtime_is_the_0588a41_runtime`): they
    asserted that `performance_campaign.py` and the validator are byte-identical to `0588a41` and that only two
    controller digests moved. B moves those two files on purpose, so the tests' allowed set now names them
    (`bounded-performance-runner`, `candidate-validator`); the sweep's and quiet's behaviour is pinned against `91c4967`
    in the new file instead (below).
- **Measurement repo** `tests/test_unbound_names.py`: 315 passed; its scan now includes
  `teastore-protocol/teastore/candidate_sweep_b.py` (+1) and finds nothing in `performance_campaign.py` or the two
  `candidate_pilot.py` files this build touched.
- **The new tests** (118): 36 cells, 3 blocks × 12 pairs, deterministic and pinned; the order recomputed from the recorded
  encoding; the shuffle and onset rules reproduce the sweep's with the sweep's values and the quiet copy of the rule; every
  cell equals the sweep's cell apart from the five keys; each pair's 3 onsets fall in the 3 thirds; the descriptor differs
  from the sweep's only in `id`, `declaration`, `design`, `timing`, `schedule`, `groundTruth` (two notes), `collection`,
  `outcomes`, `analysis`, `continuation`, `derivedFrom`; the budget and its coverage of the measured periods; the 3.9 digest;
  **the sweep and quiet files and digests byte-identical to `91c4967`** and, **under their own selectors, the `active()`
  epoch, controller set, campaign manifest, plan and every cell contract equal to `91c4967`'s** (12 and 40 cells; only the
  digests of the three moved controllers differ), **a sweep cell's fault receipt (both faults) and the validator's
  verdict on sealed sweep cells equal to `91c4967`'s**; the B selector activates the epoch in every runtime file; malformed
  selectors and a compiler naming another epoch refuse to load; materialize → inspect → 36 contracts → runtime package
  through the transport's own validator (35 cells refused) → producer contract check, with 9 planted contract defects
  refused; the real fault controller against a faked Docker for H10 and H4 (pause, throttle, failed events query, a cell
  without the declaration, an unknown declaration); sealed B cells validate at all 12 (regime, rate) pairs; **32 planted
  defects on a pause cell and 7 on a throttle cell: the H10 ones and a deleted `freezeStamps` key block the cell via `sweep-fault-command-stamps`, every H4 one leaves it valid with `h4.status` `missing` and a counted reason (decision 69)**, plus a B cell
  with the sweep's receipt shape and a sweep cell with the records; the 36-cell campaign replays its own allocation and a
  swapped order is rejected; the 3.9 floor, an unbound-name scan with its own planted defect, and the whole B runtime
  imports under `/usr/bin/python3 -I`.
- **Planted defects in the source** (worktree, one at a time, each restored with `git checkout` and the tree checked clean;
  plants that change the descriptor or plan were re-pinned and the descriptor regenerated, so a semantic test has to
  catch them; `__pycache__` cleared and `PYTHONDONTWRITEBYTECODE=1` each time): **24 of 24 caught** (re-run after decision 69; the original 20 plus: validator blocks on an H4 failure, producer raises on a collection failure, producer drops the query error, compiler declares block-on-failure). Script and result:
  `<session scratchpad>/plants/plants_b.py`, `plants_b_result.json`.

  | plant | first failing test (`tests/test_teastore_sweep_b.py::`) |
  |---|---|
  | H10 a probe inside the hold (hold-midpoint) | `test_no_probe_is_scheduled_inside_the_fault_window_on_a_pause` |
  | H10 runtime guard removed | `test_the_controller_refuses_to_probe_inside_the_window` |
  | H10 window ends at the scored window only | `test_no_probe_is_scheduled_inside_the_fault_window_on_a_pause` |
  | H4 no events collected for the pause | `test_a_pause_records_the_dockers_pause_and_unpause_events_beside_the_command_stamps` |
  | H4 events also asked for the throttle | `test_a_throttle_records_command_and_applied_state_readback_stamps_and_no_events` |
  | H4 event offset mapped one second late | `test_a_pause_records_…` (as above) |
  | H4 events not filtered to the target | `test_a_pause_records_…` |
  | H4 readback return stamp before its issue | `test_a_pause_records_…` |
  | sweep receipts also get the B records | `test_a_sweep_cells_fault_receipt_is_the_91c4967_receipt[auth-freeze-effect-auth-freeze]` |
  | validator ignores the harness problem | `test_planted_h4_defects_are_recorded_and_h10_defects_block_a_pause_cell[pause-event-late]` |
  | validator drops the event tolerance rule | `test_planted_h4_defects_are_recorded_and_h10_defects_block_a_pause_cell[pause-event-late]` |
  | validator accepts a failed events query as recorded | `test_planted_h4_defects_are_recorded_and_h10_defects_block_a_pause_cell[events-query-failed]` |
  | **D69: validator blocks the cell on an H4 failure** | `test_planted_h4_defects_are_recorded_and_h10_defects_block_a_pause_cell[pause-event-late]` (cell must stay valid) |
  | D69: producer raises on a collection failure | `test_every_producer_side_h4_failure_is_a_counted_reason_not_an_error[collection-raises]` |
  | D69: producer drops the events query error | `test_a_failed_events_query_is_recorded_as_a_missing_h4_record_and_does_not_block` |
  | D69: compiler declares block-on-failure (re-pinned) | `test_every_cell_is_the_sweeps_cell_but_for_the_onset_and_the_harness_declaration` |
  | validator accepts a probe inside the window | `test_the_window_rule_is_not_vacuous_when_the_scored_window_outlasts_the_revert` |
  | compiler: harness declares no probe rule (re-pinned) | `test_every_cell_is_the_sweeps_cell_but_for_the_onset_and_the_harness_declaration` |
  | compiler: 2 blocks (re-pinned) | `test_b_plan_is_36_cells_3_blocks_deterministic_and_pinned` |
  | compiler: other seed (re-pinned) | same |
  | compiler: onset strata collapsed (re-pinned) | `test_the_shuffle_and_onset_rules_reproduce_the_sweeps_with_the_sweeps_values` |
  | compiler: no shuffle, fixed order (re-pinned) | `test_the_order_is_recomputed_from_the_recorded_encoding` |
  | compiler: floors left at the sweep's (re-pinned) | `test_every_cell_is_the_sweeps_cell_but_for_the_onset_and_the_harness_declaration` |
  | selector accepts any `teastore-*` document | `test_a_malformed_b_selector_refuses_to_load[selector2]` |

- **What the tests cannot show.** A real `docker compose pause` and its event on fb14srv5, and the replay of that event
  through `docker events --since/--until`, have not run on TeaStore. Two read-only facts support them: (a) on fb14srv5
  (read-only `ssh`, idle host) the exact query, with the filters and format above, exits 0 in 0.03 s with an already-past
  `--until`, and `timeout` is `/usr/bin/timeout`; (b) a real pause/unpause pair retained from Hotel's evidence
  (`tmp/hotelsel1-evidence/x/runs/effect/search-pause/b02/p04-selected/attempt-01/docker-events.jsonl`) has the fields the
  controller reads (`Type`, `Action`, `Actor.ID`, `timeNano`). The first B fault cell is the first real execution.
- **Digests**, `/usr/bin/python3 -X pycache_prefix=<fresh> -I` (3.9.6) and `uv run python -I` (3.13.12): the same plan and
  descriptor digests as in the Binding table, and the same bytes of the materialized plan directory.
- **Launcher DRY_RUN** on `bbb6b11` (`scratchpad/gate-drivers/teastore-bdry2-launch.log`, rc 0, paths shortened; `bdry1` on
  `5188852` also passed):
  ```
  12:42:33Z === teastore launcher bdry2 (ROOT <worktree>, HEAD bbb6b11, dry=1) ===
  12:42:37Z previous campaign status (<worktree> live package): state=complete systemd=inactive/dead result=success journalRows=40 terminal=True abort=False lease=False
  12:42:37Z plan: descriptor d4d84633..., firstRunId teastore-traffic-sweep-b-v1/persistence-cpu-throttle-effect/r10/b01/full/a01, minimumFirstMutationRemainingSeconds 19200, plan aa346970..., runCount 36, runWindowHours 6
  12:42:37Z drivers read: ROOT=<worktree> STUDY=teastore-traffic-sweep-b-v1 CAMPAIGN_ID=teastore-traffic-sweep-b-v1 RUN_WINDOW_HOURS=6 PLAN_DIR=.../plan-e96492ce GATES=.../gates SWEEP=True
  12:42:42Z srv5 host facts (stdout only): ncpu=24 cgroup=systemd/2 candidate_containers=0 containers=0
  12:42:42Z authorization (auto will re-derive if not live): HEAD bbb6b1165410... / authorized 2026-10-04T10:56:00Z deadline 2026-10-11T10:56:00Z live=True / provenance derived by `auto` / invariants match=False
  12:42:47Z srv5 free GB (stdout only): 363
  12:42:47Z DRY RUN: all guards passed; stopping before the first mutation
  ```
  What the dry run cannot show: the SETUP-CAMPAIGN renewal, `auto` (upload, install, image build, readiness), `oneshot`, the
  controller loop over blocks 2 and 3 and the cell period. A 36-cell, 3-block plan has never executed on fb14srv5.
- **fb14srv5 idle** before the dry run (read-only): 0 containers, 0 `teastore-candidate` units, load 0.07, 363 GB free.

## Guards costed (CLAUDE.md "cost the guards, not the cells")
The sweep build (`9e75010`) had moved every shape literal behind `study_epoch.active()`; the quiet build used it for 40
cells and 10 blocks. A grep of the changed and controller files for count-shaped literals (`12`, `24`, `27`, `36`, `40`,
`3` against `!=`, `==`, `range(`) found only path-part, hash-length and schema-version comparisons. Each guard and what it
now reads:

| guard | where | B value |
|---|---|---|
| cell-count literals | adapter / transport / controller / terminal `RUN_COUNT`, installer `_installed_run_count()`, readiness `compiledRunCount` / `expectedRunRoots`, validator population | 36 (epoch), tested ("exactly 36 cells") |
| regime set | validator `REGIMES` / `SCENARIOS`, terminal `_required_for`, producer scenarios, witness `EFFECT_REGIMES` | the sweep's three regimes; `persistence-crash-effect` refused (tested) |
| run-ID formats and regexes | `candidate_sweep_b._run_id_parts`; campaign-ID regexes `^[a-z0-9][a-z0-9_-]{0,63}$` | `teastore-traffic-sweep-b-v1/<regime>/r…/bNN/full/a01`; campaign ID 27 characters |
| blocks / ordinal ranges (the Latin-square analogue) | producer and validator `1 <= block <= blocksPerRegime`, transport and producer ordinal `1..maximumOrdinal` | 3 blocks, ordinal 1-12 (plants: ordinal 13 and block 4 refused) |
| GATE-RUN window, minimum remaining, watcher cap | `teastore_driver_root.RUN_WINDOW_HOURS` → `gate_run.py`; adapter, transport and controller minimum; launcher cap = window + 1 | 6 h, 19,200 s, 7 h (derived) |
| descriptor equality | adapter `_frozen_timing`, `validate_descriptor` exact generator equality, producer `compiler.frozen_descriptor()` | B compiler exposes the same names; `minimumTimedSeconds` 7,560 |
| receipt key sets | validator `sweep` key set, `probePolicy`, `freezeStamps` | exact, gated on the plan cell's `faultHarness` |
| spent-attempt records | TeaStore keeps none (`ATTEMPT = 1`, per-process consumed guard; launches separated by setup ID) | nothing to record; B run IDs differ from the sweep's and quiet's |
| controller digest binding | adapter `CONTROLLER_PATHS` | `+sweep-compiler`, `+sweep-b-descriptor`; `sweep-descriptor` names the sweep's file; 56 bound |
| governance pins | `openspec/changes/*/governance.json` | pin historical `sourceCommit` blobs, not current files; nothing to re-pin (the pinned `performance_campaign.py` is the `b4a6e05` blob) |
| host binding (lineage-wide fb14srv5) | adapter target, machine-id, descriptor `targetHost` | unchanged, inherited |
| launcher sweep guard | `launch_teastore.sh` requires `SWEEP=True` from the drivers | B is a sweep-mode epoch: passes |

Cosmetic only, left unchanged: `gate_run.py` prints "LAUNCHING 27-CELL CAMPAIGN" (a literal the sweep and quiet runs
printed too).

## Defects and time
- **Critical-path harness defects: 0** (of the 3 that stop TeaStore's part of B).
- Findings in this build, none on the critical path: the H10 finding above (no probe schedule to change); two quiet tests
  that asserted the old moved-file set (repaired, ~5 min); my own first-run test errors corrected before the first green run
  of the new file (the hold-midpoint inspect is the third `docker inspect`, not the fourth; the "upgrade" test must use a
  sweep-timing cell because the validator takes `timing` from the plan, not the receipt), ~10 min.
- Not done, by instruction: no declaration freeze, no launch, no evidence read.

## Open questions for the user (▶ = preregistration class)
1. **Closed (user decision 69):** H4 is record, don't block; built and tested as described under "H4".
2. ▶ **Tolerance 0.25 s** and **seed 20261009**, **3 onset strata per pair**, **no lead cell**: engineering defaults, to be
   recorded in `research/protocol/parameters.json` at freeze (I did not edit that file).
3. ▶ **Throttle H4 scope:** the throttle's record is stamps and readbacks, as asked; Docker `update` events are not
   captured. Adding them would be the same query with `event=update` and one more validator rule.
4. **Closed (user, 2026-10-09):** H10 on TeaStore needs no probe change; the recorded policy, runtime refusal and validator re-derivation stay.
5. **The freeze must use the file name `DECLARATION_B_TEASTORE.md`** (see Binding).
6. Pooling with the sweep's block and with B's no-fault time is analysis v3's decision (`campaign ID` is the key).
7. A review: none has been run on the harness change. `adversarial-review` (read-only) on `c4669a1`, `5188852` and `bbb6b11` before
   the freeze is the quiet run's precedent.
