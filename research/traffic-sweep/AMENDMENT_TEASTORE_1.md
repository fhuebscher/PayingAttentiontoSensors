# TeaStore traffic-sweep initial test, amendment 1 (FROZEN 2026-10-03, committed alone, before the relaunch)

Amends `research/traffic-sweep/DECLARATION_TEASTORE.md` (c9f072b). Approved by the user as protocol decision 25
(`research/PROTOCOL_DRAFT_20261002.md`, a301903): a shared trace-completeness rule for all three sweeps, and a TeaStore
relaunch of all 12 cells (relaunch 1 of 2 under `BUDGET_REPLICATION.md`). Scope of every number: **instance**.

## What happened
- Attempt 1 (activation `9a4ea56`, plan `5212f18c…`, setup `21791ab37cab152a5d932c335c2f2a0d`, 11:52-12:55Z on
  fb14srv5): **11 cells attempted, 10 valid**. Cell 11 (`persistence-cpu-throttle-effect/r10/b01/full/a01`) was blocked
  by the producer: `collector native parent correlation errors: 498 events (7177 tolerated inside the exposure window)`;
  the controller aborted the campaign (`campaign-abort.json`, `ABSTAINED`, `validCells: 10`). Cell 12 did not run.
- Diagnosis, capture-level only (no detection time, catch or score was computed), from the retained blocked evidence
  `runs/persistence-cpu-throttle-effect/b01-11-full.blocked-evidence/.operational`:
  - fault: onset command issued 60.042 s after the barrier, hold end 120.130 s, revert issued 120.160 s, readiness
    121.598 s; the frozen tolerance window was [60.000, 121.598] s;
  - the 498 untolerated records were all `persistence` records with `conflicting-native-identity`, logged
    **121.601-121.670 s, i.e. 3-72 ms after readiness**, inside the 17 s drain window;
  - they belong to 63 native traces that **no journey's auth bridge names** (unattributable);
  - 7,675 records in the cell carry a correlation error; the other 7,177 were inside the frozen window.
  The block was the all-or-nothing completeness rule (zero residual correlation errors outside [onset, readiness]), not
  the fault or the design. Same class as Hotel relaunch 2 (cell 15) and OTel attempt 1 (cell 8): decision 25.

## Amendment
- **Rule** (decision 25, TeaStore's journey unit; sweep cells only, the frozen epoch keeps its zero tolerance):
  - A journey is **incomplete** if a record of its native trace(s) has a correlation error, an unresolved parent or a
    repeated native identity; if the trace repeats a (message, trace, eoi/ess) identity or has an execution-order-index
    gap; or if it lacks the required auth→persistence edge. Traces are attributed to journeys by the auth native-trace
    bridge (`auth.log`).
  - **(i)** Journeys starting in [onset command issued, readiness + `drainAllowanceSeconds`) (= client timeout + 2 s =
    17 s, from the compiled timing, the Q3 window): incomplete traces are **recorded as fault effect, never blocking**.
  - **(ii)** Pre-onset, after the drain window, and every no-fault cell: the cell blocks only if incomplete journeys >
    **max(1, floor(0.01 × successful journeys in those windows))**.
  - **Unattributable** defective traces (no bridge names them): each native trace is one cluster; if the logging time
    of every defective record of the cluster lies in window (i), it is recorded; otherwise it counts as **one
    incomplete journey** in (ii).
  - **(iii)** Every window's journeys, successful journeys, incomplete journeys (all ids), reasons, unattributable
    clusters (all trace ids) and defective records (by logging time) are written to `candidate-validation.json`
    (`traceCompleteness`), per cell.
- **Where** (worktree `observability-placement-runtime-teastore-protocol`, commit `e6d6600`):
  - rule: `modules/teastore/validation/candidate_pilot.py:975` (`sweep_trace_completeness`); window (i) `:999`;
    allowance `:1093`; check `trace-completeness` `:2675`;
  - defects handed to the rule instead of blocking: integrity `:2573`, duplicate keys `:2391`, tolerance residuals
    `:2634` (container parse failures, attribution, token smuggling, warnings and redelivery stay strict);
  - producer: `modules/teastore/execution/performance_campaign.py:1468` (`trace_completeness_deferred`), set for sweep
    cells at `:2673`;
  - parameters: `modules/teastore/execution/candidate_sweep.py:120` (`DRAIN_ALLOWANCE_MARGIN_SECONDS`), `:125`
    (`TRACE_INCOMPLETE_FRACTION = 0.01`); the descriptor records the rule (`timing.traceCompleteness`).
- **Binding**: harness `9a4ea56` → **`e6d6600`** (the selector stays committed; activation unchanged). Descriptor
  `e808c2bb…` → **`f2e35292257ff60d5ec677f0b804c07cd227a07cd89111c2b003adfe2749fe94`**, plan `5212f18c…` →
  **`c7df47ab30088c072456e3af8ab6a37e3720db0a96a5c8660051f307e4e03265`** (identical under `/usr/bin/python3 -I` 3.9, Apple
  bytecode cache cleared, and 3.13). **Cell timing is unchanged** (same 12 run IDs, order, onsets, floors, 17 s drain);
  only the descriptor's rule record changed. Plan directory `plan-b1bbfe28`, campaign sha256 `921b1af5…`.
- **Tests**: 12 decision-25 tests (all fail on `9a4ea56`): the cell-11 incident reproduced synthetically (unattributable
  repeated identities 3 and 70 ms after readiness) seals valid and is recorded in window (i); window (i) never blocks (1
  and 40 clusters); the (ii) boundary at 10/s (allowance passes, allowance + 1 blocks); a 0.05/s cell (about 5
  successful journeys, allowance 1: one missing edge passes, two block); no-fault cells use (ii) everywhere; a cluster
  is placed by its logging time; the producer defers only for sweep cells; the frozen epoch keeps its zero tolerance.
  Planted defects 20/20 caught (4 new). Worktree suite (activated): 20 failed (the same tests as before, by name), 1767
  passed, 162 skipped (frozen-only, each passing without the selector). Measurement repo: 955 passed, 1 skipped, 3
  xfailed (+30 = `tests/test_sweep_analysis.py`, da6c002/ca380a4, not this change).

## Replay of attempt 1 (offline, read-only copies, current code)
- Archive: `tmp/teastore-sweep-evidence/teastore-traffic-sweep-v1-attempt1.tgz` (sha256 `3792f2eb…ddf87dd`, 20.6 MB,
  291 MB on the host); `teastore-traffic-sweep-v1-attempt1.host.sha256` (303 files) equals the extracted copy byte for
  byte. Nothing on the host was moved or deleted.
- **Cell 11**: the producer's collector blockers recomputed by `e6d6600` are empty; the post-slice producer steps and the
  cell validator then **seal it valid**. Its 7,675 defective records, **439 incomplete journeys and 146 unattributable
  clusters all fall in window (i)** ([60.042, 138.598] s); window (ii): 0 incomplete of an allowance of 10 (1,015
  successful journeys). So cell 11 validates **because its errors fall in (i)**, not by (ii)'s allowance.
- **The 10 valid cells stay valid** (`validate_run` on copies: pass, no failed gate; (ii) incomplete 0 in each; window (i)
  recorded 1, 2, 13 and 20 incomplete journeys in the four auth-freeze cells, 0 in the throttle cells). Their retained
  `candidate-validation.json` predates the `traceCompleteness` field, so a byte-for-byte terminal replay of attempt 1
  would differ; attempt 1 is not pooled, so this does not arise.

## Relaunch
- **All 12 cells**, relaunch **1 of 2** (approved, decision 25). Attempt 1's 11 cells are archived above and **not
  pooled**; they remain a same-plan repeat (same run IDs and onsets) usable later as an exploratory test-retest check.
- DRY_RUN on `e6d6600` passed (13:39Z, `scratchpad/gate-drivers/teastore-sweep1r1dry-launch.log`): previous campaign
  `state=stopped … abort=True lease=False`; srv5 `ncpu=24 cgroup=systemd/2 candidate_containers=0 containers=0`, 366 GB
  free. SETUP-CAMPAIGN invariants no longer match (new digests); `auto` re-derives it (recorded as auto-derived).
- The launcher archives attempt 1's local run state (`run-authorization.json`, `runtime-package.json`, `gate-run.json`,
  `campaign-terminal.json`) into `gates/run-state-before-<label>-<stamp>` before `auto`; the new setup gets a new
  results root on srv5, so attempt 1's host directory stays untouched.
- Command (after this amendment is committed alone):
  ```
  W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
  M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
  TEASTORE_ROOT=$W EXPECTED_HEAD=e6d66009b5e7787183350fb56f6dc96c097b858a TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_sweep.py EXPECTED_PLAN=c7df47ab30088c072456e3af8ab6a37e3720db0a96a5c8660051f307e4e03265 RUN_COUNT=12 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh sweep1r1 > $M/scratchpad/gate-drivers/teastore-sweep1r1.out 2>&1 &
  ```
- Analysis stays blind: no detection result of attempt 1 has been looked at.
