# OTel quiet calibration run (A), amendment 1: trace loss recorded, never blocking; relaunch 1 (FROZEN 2026-10-04, committed alone before launch)

Amends `research/traffic-sweep/DECLARATION_QUIET_OTEL.md` (frozen `593d4ee`). Authority: `research/PROTOCOL_DRAFT_20261002.md`
round 12, **decision 56** (user, 2026-10-04 ~10:45Z). Stop record: `research/traffic-sweep/STOP_QUIET_OTEL_A1.md`
(`a0e74b4`). Budget: `research/traffic-sweep/BUDGET_CALIBRATION.md`. This is OTel A's **1st** critical-path stop (3 stop
the system), and this is **relaunch 1 of 2**. The launch-ready deadline is 2026-10-05 12:00Z; this draft was ready on
2026-10-04 at ~13:01Z. Scope of every number: **instance** (one SUT, one host, fb14srv6).

**Frozen under the file name `research/traffic-sweep/AMENDMENT_QUIET_OTEL_1.md`**, the path the pinned descriptor's
`amendments` entry names. Any other name would mean a regenerated descriptor, new digests and a new DRY_RUN.

## Binding change
| item | attempt 1 | relaunch 1 (attempt 2) |
|---|---|---|
| harness commit | `6e37ec2` (activation) | **`6a47d0b37edb1f4a5c6d9b23bcb7dc184bfe9365`** = `c80fe88` (decision 56, attempt 1 spent, re-pin) + `6a47d0b` (governance re-pin), on `6e37ec2` |
| descriptor | `02c2d90e…777d` | **`36a7fd173a9995e6b0c0e9897d98ff76995ca375e045b90804fe92221dfd2286`** |
| plan | `5cec5a69…7b58` (ran) | **attempt 2 `bb1eb1fc6bb4047b83c69d4d216d70b18f49dd7689c1245e4d0b7d0e18ffe8d6`** |
| trace rule in quiet cells | decision 25 (blocking above max(1, 1 %)) | **decision 56 (recorded, never blocking)** |
| sweep epoch | decision 25 | unchanged: decision 25, byte for byte |

- Both digests are identical under `/usr/bin/python3 -I` (3.9.6, a fresh `-X pycache_prefix` directory each time) and
  `uv run python -I` (3.13.12). Command: `candidate_quiet.py --print-digests --attempt {1,2}`.
- Attempt 1 under the new descriptor has plan `f2e7158f…9fc6`. Its run IDs are attempt 1's run IDs, because the run ID
  hashes the runKey, which carries the attempt but not the descriptor. Attempt 1 is therefore recorded as spent
  (`candidate_runtime_adapter.SPENT_ATTEMPTS_BY_EPOCH["otel-quiet-calibration-v1"][1]`), and the adapter refuses it.
- All other design values are unchanged:
  - 40 no-fault cells, 10 blocks × 4 rates;
  - seed 20261004 and the same block orders and onsets (timing is keyed by regime, rate and block, never by attempt);
  - route, timeout 15 s, concurrency 300, warm-up, measurement, proxy memory 256 MiB, container-health guard;
  - G1, G2, G4; GATE-RUN window 6 h; minimum remaining 14,740 s.
- In the descriptor, the `amendments` entry is added, and `analysis.traceCompleteness` replaces the decision-25 block.
  `drainRule`, `drainSeconds` and the decision-25 `authority` and `rule` are gone; `allowanceShare` and `allowanceMinimum`
  stay, for the counterfactual. Nothing else changes.

## What happened (attempt 1; from the stop record)
- Campaign `otel-quiet-calibration-v1`, harness `6e37ec2`, plan `5cec5a69…`, fb14srv6, 09:12-09:58Z.
- `remote-terminal.json`: attemptedCells 8, validCells 7, stopped true.
- The invalid cell is `calibration/r10-b02-04-full` (no fault, 10/s): `trace completeness: 50 incomplete of 1800 successful
  requests outside the fault-and-drain window exceeds the allowance 18` (decision 25, rule ii).
- Diagnosis (stop record, read-only, not repeated here): the 50 requests are one contiguous block, scheduled
  134.9-139.8 s. All of them succeeded. Each has frontendproxy and frontend spans, and none has a productcatalogservice
  span. The probable reading is one lost 5 s batch of one service's spans between collector receipt and the
  debug-exporter carrier. That is not proven: an SDK-side drop was not ruled out.
- Decision 56 keeps attempt 1's 7 valid cells but does not pool them with the relaunch.

## 1. The rule change (decision 56; commit `c80fe88`)
**Mechanism.**
- Every quiet cell's compiled timing gains one key, `traceCompletenessRule = "protocol-decision-56"`
  (`candidate_quiet.cell_timing`). It is the only key the sweep's timing does not have.
- `candidate_remote.trace_completeness` dispatches on that key:
  - with the key, `trace_loss_record` writes the record below;
  - without the key, the decision-25 body runs unchanged. A test checks that its output equals `c532853`'s on the same
    inputs.
- Only a quiet-epoch cell may carry the key. A sweep cell that carries it, or a quiet cell that lacks it, fails closed.
  Unknown rule values and fault cells are refused too.
- `candidate_runtime`: the timed-cell timing key set is the sweep's, plus the rule key for the quiet epoch only. A
  contract cannot drop the key or change its value (tested).

**The record** (`trace-completeness.json`, schema 3, `otel-demo-quiet-trace-completeness-v3`) has one
`whole-measurement` window. "Complete" keeps decision 25's meaning: the request's own trace id was observed, with exactly
the route's services. The window holds:
- decision 25's counts: requests, successful, complete, incomplete with tokens; unsuccessful requests counted separately;
- per successful incomplete request: its scheduled offset, whether its own trace id was observed, and the required path
  services missing from it (plus any unexpected ones);
- `incompleteByMissingService`: the number of incomplete requests missing each required service;
- `incompleteRuns`: the contiguous runs of consecutively scheduled requests that are each successful and incomplete,
  with first and last scheduled offset, request count and missing services. A complete request or an unsuccessful one
  ends a run. A lost batch shows as one run only if every request in it succeeded; a timeout inside it splits the run.

"Incomplete" means the observed path services differ from the route's set in either direction. A trace that has every
required service plus an extra one from the path catalogue (for example currencyservice) is incomplete with
`missingServices: []`. It is named only in that request's `unexpectedServices`, and its run may show
`missingServices: []`. Such a trace is not counted in `incompleteByMissingService` (review finding M1).

Beside the window:
- `decision25Counterfactual` records the allowance decision 25 would have applied and whether the cell exceeds it, with
  `applied: false`;
- `blocking: false`, `blockingWindows: []`, `allowance: null`, `valid: true` by rule.

**What stays blocking.** G1, G2 and G4 (target), the container-health guard, and the terminal's ledger, application
witness, generator-absence, posture and application-log checks. The campaign still stops on the first invalid cell.

"Never blocking" has one bound. The posture proof derives the observed signal services from the collector log, so a
loss that covers one service for a whole cell would still fail the posture check. That is intended.

**Terminal.** `candidate_terminal.py` is unchanged (byte-identical to `c532853`, tested). It replays
`trace-completeness.json` byte for byte through the remote's function, which reads the contract's compiled timing. The
runtime first checks that timing against the active compiled plan, so a retained record cannot choose its own rule.

**Governance.** `6a47d0b` re-pins the two governance-bound files that moved (`candidate_runtime.py`,
`candidate_runtime_adapter.py`), by the rule of `d101fda`/`fb02804`. `candidate_pilot.py` and `candidate_terminal.py`
did not move.

## 2. Tests
New and changed tests (`tests/test_otel_quiet_calibration.py`, 22 → 32; `tests/test_otel_traffic_sweep.py` +1; the
FakeTarget gains `lose_spans`, which drops only a request's productcatalogservice span):
- **Attempt 1's pattern seals valid with the loss recorded.** On the cell it hit (r10, block 2, position 4), 50
  consecutive requests (sequences 1349-1398) lack productcatalogservice. The cell seals valid, and the record shows:
  - 1750/1800 complete;
  - `incompleteByMissingService` = {frontend 0, frontendproxy 0, productcatalogservice 50};
  - one run, 134.9-139.8 s, 50 requests;
  - the counterfactual {allowance 18, wouldHaveBlocked true}.

  The terminal accepts the cell. **This test fails at `6e37ec2`**: in a scratch clone with the harness restored to
  `6e37ec2` and the new tests kept, the cell sealed invalid with
  `RuntimeFailure: trace completeness: 50 incomplete of 1800 successful requests outside the fault-and-drain window
  exceeds the allowance 18`, which is attempt 1's error.
- **The same pattern in a sweep cell still blocks:** decision-25 record, schema 2, 50 > 18, invalid.
- G2 (a pre-onset failure at 0.05/s) and an OOM kill still invalidate a quiet cell, and the loss is recorded either way.
- Run and missing-service bookkeeping on a synthetic ledger:
  - three runs, ended by a complete request and by an unsuccessful one;
  - per-service counts;
  - the record does not depend on ledger order.
- Fail-closed cases: the rule key is bound to the quiet epoch; unknown rule values and fault cells are refused; a
  contract cannot drop or change its rule.
- The sweep's decision-25 record is byte-identical to `c532853`'s for the lost batch in a no-fault cell and for a fault
  cell.
- Four planted record defects are rejected by the terminal replay ("trace completeness record does not replay"): a run
  erased, the missing service relabelled, the loss relabelled as blocking, and the loss hidden in the correlation.
- Re-pinned: descriptor and plan digests, the 3.9/3.13 identity (now with attempt 2), and the adapter refusing attempt 1
  and taking attempt 2 (plan `bb1eb1fc…`).

**Planted defects in the source** (scratch clone at `6a47d0b`, one at a time, clone restored and its digest re-checked
after each; `scratchpad/…/quiet-a1/plant.py`): **12 of 12 caught.** Each made at least one named test in `test_otel_quiet_calibration.py` fail:
- the quiet loss record blocks like decision 25 (7 tests, including the attempt-1 test);
- decision 56 leaks into the sweep, so the decision-25 record is always valid (the byte-identity test against `c532853`);
- a complete request does not end a run (the run test);
- an unsuccessful request does not end a run (the run test);
- observed services are recorded as missing (3 tests);
- the rule key is not bound to the quiet epoch (the fail-closed test);
- an unknown rule value is accepted (the fail-closed test);
- rule 56 is accepted in a fault cell (the fail-closed test);
- the decision-25 counterfactual is relabelled (2 tests);
- the quiet timing drops the rule key (11 tests);
- the runtime refuses the quiet rule key (5 failed, 5 errors);
- attempt 1 is no longer recorded as spent (the adapter test).

**Suites.**
- Worktree (`uv run pytest -q -p no:cacheprovider -rA --ignore=tests/test_mlflow_manifest.py`): 29 failed / 2060 passed / 145 skipped at `6e37ec2`, and
  **29 failed / 2071 passed / 145 skipped** at `6a47d0b`.
  - The +11 passed are the new tests (10 quiet, 1 sweep).
  - The 29 failures are the same by name in both runs (sorted `FAILED` lists compared with `diff`): Hotel materialize,
    Kieker fixture, Online Boutique, phase-1 control universe, science router, TeaStore. None is OTel.
- Measurement repo `uv run pytest -q`: **1019 passed, 1 skipped, 3 xfailed, 0 failed** at measurement-repo HEAD `bc8e738`.
  - Other sessions moved HEAD from `fc64a6d` while this work ran.
  - This change touched no tracked file there and added no module file to the OTel worktree, which `test_unbound_names`
    scans.
  - This draft claims only that the suite is green. It does not compare the count with any earlier count, so no delta is
    quoted.

## 3. Attempt 1 evidence: fetch and byte check
- **Fetched read-only before any host move**, from the OTel worktree at `6e37ec2` with `PYTHONPATH=src`:
  `uv run python modules/otel-demo/execution/candidate_runtime.py fetch .local/candidate-v4/otel-demo/plan
  --gate-plan G/gate-plan.json --gate-setup G/gate-setup.json --setup-receipt G/install-staging/setup-receipt.json
  --readiness G/fetched-readiness/readiness.json --gate-run G/gate-run.json --staging
  <measurement repo>/tmp/otel-quiet-evidence/attempt1-fetch` (G = `.local/candidate-v4/otel-demo/gates`).
- **Result.** The scp completed: the terminal validator runs only after a zero scp return code and a present
  `remote-terminal.json`. The terminal validation then raised
  `ValidationError: cell artifact population differs: missing=['content-manifest.json'], extra=[]`, so there is no
  `terminal-validation.json` and no fetch receipt (stdout empty, traceback in `attempt1-fetch.stderr`). The missing
  manifest belongs to the invalid cell `r10-b02-04-full` (receipt `invalid`): the runner writes a content manifest only
  for valid cells. The other 7 receipts are `valid`. This failure is expected for a campaign that stopped.
- **Byte check.** 134 files, no symlinks or special files. The sorted `sha256sum` list of the host's
  `…-runs/otel-quiet-calibration-v1` equals the local list of `attempt1-fetch/retained`; both lists hash to
  **`c501c5c8d5ccbacc29e5479724e4fcac184ea6f31a131e6d8e49fec1714d98e1`**. The lists are kept as
  `tmp/otel-quiet-evidence/attempt1-fetch.{host,local}.sha256`.
- No cell was analysed. Attempt 1 was not replayed under decision 56: none of its cells is pooled, so the launch does not
  need it.

## 4. Host move (done 2026-10-04 12:43:17Z, after the byte check)
- Script `tmp/otel_quiet_a1_archive.sh`, adapted from `tmp/otel_sweep_a1_archive.sh` (moves, never deletes; refuses
  unless the host is idle), run report-only first and then with `--archive`. Command:
  `ssh root@fb14srv6 'bash -s' -- --archive < tmp/otel_quiet_a1_archive.sh`.
- Idle at the move: 0 units, 0 containers, no lease holder, no candidate process (also checked separately at 12:42Z).
- Moves:
  - `/home/stig/observability-placement-candidate-v4-runs/otel-quiet-calibration-v1` → `.archived-otel-quiet-calibration-v1-quiet-a1-20261004T124317Z` (221 MB, 134 files)
  - `/home/stig/observability-placement-candidate-v4-runs/.setup-otel-quiet-calibration-v1` → `.archived-.setup-otel-quiet-calibration-v1-quiet-a1-20261004T124317Z` (46 MB, 8 files)
  - `/home/stig/observability-placement-candidate-v4-otel-srv6/otel-quiet-calibration-v1-6e37ec248a5a` → `.archived-otel-quiet-calibration-v1-6e37ec248a5a-quiet-a1-20261004T124317Z` (70 MB, 1,515 files)
- After the move, the archived artifact root still hashes to `c501c5c8…98e1`, and 0 quiet-epoch paths remain.

## 5. DRY_RUN (passed; `scratchpad/gate-drivers/otel-quiet-quietdry3-launch.log`)
```
13:00:25Z === otel offpath launcher quietdry3 (HEAD 6a47d0b37edb1f4a5c6d9b23bcb7dc184bfe9365 on otel-protocol-20261002, compiler candidate_quiet.py, plan bb1eb1fc6bb4047b83c69d4d216d70b18f49dd7689c1245e4d0b7d0e18ffe8d6, 40 cells, attempt 2, dry=1) ===
13:00:25Z compiled: otel-quiet-calibration-v1 40 bb1eb1fc6bb4047b83c69d4d216d70b18f49dd7689c1245e4d0b7d0e18ffe8d6
13:00:25Z drivers: otel-quiet-calibration-v1 otel-quiet-calibration-v1 6 /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-otel-protocol
probe receipt 2026-09-23T10:03:11Z 23dd90bb20f5 0 42
13:00:50Z host fb14srv6: running units=0 containers=0 lease holders=[] free GB=248 otel-quiet-calibration-v1 paths=0
13:00:50Z DRY RUN: all guards passed; stopping before the first mutation
```
Before the first mutation, the non-dry launcher:
- archives attempt 1's run-phase state left in the worktree's `.local/…/gates` (`gate_run.py archive-run`);
- moves attempt 1's plan dir aside;
- renews SETUP-CAMPAIGN onto `bb1eb1fc…`. Today's authorization is bound to attempt 1's `5cec5a69…`.

## 6. Launch (after: this amendment frozen as `AMENDMENT_QUIET_OTEL_1.md` and committed alone)
From the measurement repo:
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=2 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_quiet.py EXPECTED_PLAN=bb1eb1fc6bb4047b83c69d4d216d70b18f49dd7689c1245e4d0b7d0e18ffe8d6 \
  RUN_COUNT=40 CAMPAIGN=otel-quiet-calibration-v1 LOG_PREFIX=otel-quiet \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh quiet2 6a47d0b37edb1f4a5c6d9b23bcb7dc184bfe9365 \
  > scratchpad/gate-drivers/otel-quiet2.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow otel-quiet2 scratchpad/gate-drivers/otel-quiet-quiet2-launch.log \
  > scratchpad/gate-drivers/otel-quiet2-wandb.out 2>&1 &
```
Check the first r10 cell as soon as it seals. Its `trace-completeness.json` must be schema 3 with
`rule: protocol-decision-56`, and its `container-health.json` must be valid.

## Independent review (Fable `adversarial-review` subagent, read-only, 2026-10-04 ~13:20Z)
**Verdict: no blocker and no major defect.** What the reviewer did:
- ran 15 targeted tests;
- planted 7 defects of its own; all were caught;
- confirmed that the attempt-1 test fails at `6e37ec2`;
- found the new record byte-identical between CPython 3.9.6 `-I` and 3.13.12;
- confirmed that the sweep is unchanged against `c532853`;
- confirmed that a quiet cell cannot be blocked by trace completeness on the target or in the terminal;
- found the governance re-pin and the spent-attempt record consistent.

The reviewer did not verify the full-suite counts or the host-side state.

Minor findings and their disposition:
- **M1:** an extra-service trace counts as incomplete with no missing service. Documented in §1; the code is unchanged.
- **M2:** an unsuccessful request splits a run. Documented in §1.
- **M3, M4, M5:** open below.
- **M6:** wording fixed (the descriptor *replaces* the trace block), and the measurement-suite count is no longer quoted as
  a delta.

## Open
- **M3 (pre-existing, not a regression).** The terminal replays `trace-completeness.json` from the retained correlation
  but never re-derives the correlation from the retained `otelcol.log`. A consistent tamper of both files would pass.
  Under decision 56 the record is calibration data, so this matters more than before. Fix: re-parse `otelcol.log` with
  `parse_trace_correlation` in the terminal and byte-compare. That is a governed terminal change, so it needs a re-pin
  and a new DRY_RUN.
- **M4.** The worktree has no 3.9 syntax gate of its own. The changed target files carry
  `from __future__ import annotations`, and the reviewer ran `py_compile` on them and executed the record under 3.9.6.
- **M5.** The new guards raise `RuntimeFailure`, not `ValidationError`, if reached from the terminal. They are
  unreachable with package-built contracts, and they fail closed either way.
- The cause of the lost batch (collector side vs SDK side) is still unproven. Decoding the OTLP payloads in attempt 1's
  `telemetry.pcap` would settle it. This is not needed for the launch.
