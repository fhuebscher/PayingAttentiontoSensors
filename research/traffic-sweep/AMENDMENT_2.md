# Traffic-sweep pilot, amendment 2 (FROZEN 2026-10-03, committed alone, before the relaunch)

Amends `research/traffic-sweep/DECLARATION.md` (a795fc9) as amended by `AMENDMENT_1.md` (6aca1ff). Design, descriptor
(`788ff28c…`) and plan (`766063c5…`) are **unchanged**; only the harness commit the declaration binds changes.

## What happened
- Relaunch 2 (`hotel-v1-20261003t111746z-cc971de7`, harness 7a1d97b): 15 of 64 cells attempted, 14 sealed, 14 valid.
  Cell 15 `net-delay-effect-r10-b01-full-a01` raised `native trace lacks a required same-trace service edge`
  (`STOP_ATTEMPT3.md`): 10 of 1,803 frontend-rooted traces lacked `search → rate`, all with a ledger start inside the
  fault window. `BUDGET.md` rule 4 (at most 2 relaunches) was reached.
- User decision 25 (`research/PROTOCOL_DRAFT_20261002.md:280-288`, 2026-10-03 ~13:00Z): one trace-completeness rule
  for all three sweeps, and the Hotel relaunch of all 64 cells approved.

## Amendment
**Harness binding: `7a1d97b` → `ca58974`** (worktree `../observability-placement-runtime-hotel-protocol`, branch
`hotel-protocol-20261002`). `4f8697d` implements the rule (`modules/hotel-reservation/witness/candidate_evidence.py`,
`modules/hotel-reservation/validation/candidate_terminal.py`, `tests/test_hotel_traffic_sweep.py`); `ca58974` adds
one test after review and pins 7a1d97b by full SHA (tests only; witness and terminal byte-identical to 4f8697d).

### The rule as implemented (`witness/candidate_evidence.py` at 4f8697d)
- **Scope** (`:733-735`): cells whose contract carries a compiled `timing` (the sweep epoch) and a tracing posture.
  `timing=None` (the frozen `hotel-reservation-selected-v1`) keeps every trace defect fatal; its output and its error
  messages match 7a1d97b exactly (test below).
- **Window (i), fault + drain** (`:750-761`, assignment `:781-788`): a request belongs to it when its ledger
  `actualStartMonotonic` lies in [`startedMonotonic`, `readyAtMonotonic` + `timing.requestTimeoutSeconds` +
  `TRACE_DRAIN_MARGIN_SECONDS`), half-open. The timeout is the plan's value (1.0 s for Hotel), the margin is the rule's
  2 s (`:60`), so the drain is 3.0 s after readiness, derived, not a literal. Everything before is `pre`, everything
  after is `post-drain`. A no-fault cell has one window, `measurement`.
- **Incomplete trace** (an absence): a missing required service edge (`:465`), a dangling parent (`:429`), a witnessed
  request with no trace at all (`trace-missing`, `:806`), and on pause cells the pause's own during-policy failures
  (attempted prefix missing `:581`, an edge the fault does not explain `:585`). The pause during-window policy stays the
  pause's structural ground truth: a truncation it permits is not incomplete (`faultPathTruth` is unchanged).
- **(i) never blocks** (`:822-829`): inside window (i) every per-trace defect, absence or malformed, is recorded with its
  token, trace ID and reason; the row becomes `unsupported`, `reconstructed: null`, reason `native-trace-incomplete`
  (cause `?`, see `STOP_ATTEMPT3.md`, so not a negative).
- **(ii) allowance** (`:871-897`): `pre` and `post-drain` pooled (a no-fault cell: `measurement`); the cell blocks when
  incomplete traces exceed max(`TRACE_INCOMPLETE_MINIMUM` = 1, floor(`TRACE_INCOMPLETE_PERCENT` = 1 % × successful
  requests there)), integer arithmetic. Successful = ledger `outcome == "completed"` and status 200, the terminal's own
  protocol-cell definition (`:790`).
- **(iii) report** (`:966`): `correlation.json` carries `traceCompleteness` on every sweep cell, zero counts included:
  per window `requests`, `successful`, `incomplete`, `incompleteByReason`, `incompleteTraces` (token, trace ID,
  reason), plus the window bounds, `drainAfterReadySeconds` and the allowance record. The cell terminal surfaces it
  (`validation/candidate_terminal.py:1074-1076`).
- Per-trace defects now raise `TraceDefect`, a `WitnessError` subclass with the old messages (`:38-50`).

### Engineering defaults (recorded, not preregistration choices)
- Malformed traces (duplicate span ID, second root, root with a parent service, parentService mismatch, cycle) outside
  window (i) still block at once, as before; they are not "incomplete".
- Still blocking everywhere, as before: an untagged native trace that is not the fault adapter's route probe, a trace
  carrying a token nobody witnessed, a token mapped to several traces, a token tag off the frontend root.
- A request that started before the receipt's start but was in flight at onset counts in (ii) (the rule keys on the
  ledger start).
- Phase floors (`minimumWitnessedStartsByPhase`) and the pause `during` phase ([start, readyAt + 1 s)) are unchanged.
- Rule constants live in the witness, not the descriptor, so plan and descriptor digests stay as frozen; the harness
  commit above binds the rule.

### Known residuals (from the review below; none occurred in the 40 replayed cells)
- **Lost frontend root inside (i) still blocks** (`:744-749`, `:612-641`, unchanged since 7a1d97b). If a request's
  frontend span batch is lost but its children are reported, the children form an untagged trace with no root, and
  `one native trace/root maps to zero or multiple opportunity tokens` stops the cell whatever the window. Read
  literally, rule (i) ("missing span", "nothing blocks") covers this case; the code does not, because an untagged
  fragment cannot be tied to a request or a window without a time heuristic. 0 of 40 cells; no sweep fault targets the
  frontend or its span export. **At freeze (engineering call, main session)**: launched with this residual. It is stricter
  than decision 25, never looser, so it cannot admit bad evidence; it can only stop the campaign (0 of 40 cells so far).
  The user may still choose to attribute such fragments to (i) by span time for a later run.
- In-flight at onset counts as (ii): a request started just before `startedMonotonic` is `pre`, as the rule keys on
  the start. At <= 1/s the allowance is 1, so two incomplete traces outside (i) stop the cell. 7a1d97b already
  stopped on one. G2 independently fails a cell with a failed pre-onset request.
- `fault-drain.incomplete` is not comparable across regimes. On pause cells, truncations the pause policy permits in
  `during` ([start, readyAt + 1 s)) are not counted, while the same shape in [readyAt + 1 s, readyAt + 3 s) is; on
  degradation cells every missing edge counts. Read it together with `faultPathTruth.duringTracesTruncated`. Inside
  (i), malformed traces are listed among `incompleteTraces` under their own reason code.
- Frozen epoch: messages and exit paths are unchanged, but the blocked-evidence manifest's `errorType`
  (`candidate_cell.py:638`) would read `TraceDefect` instead of `WitnessError` for a per-trace defect. No validator reads
  it, and the frozen epoch does not run from this tree. The frozen fault-cell path is identical by reading; only the
  no-fault path is byte-compared by a test.
- TeaStore receipts already use a `traceCompleteness` key with another shape (`tools/mlflow_import_v4.py:124`
  reads `.traces` with `.get`, so Hotel's block is harmless there). Same name, two schemas.

### Digests
Unchanged: descriptor `788ff28cc44248fec518fd04e3e0f91ab6d92229888a1412a52e50f9dd889dab`, plan
`766063c5a0f0b90ab1aba1ada29b86e152e8ec1e7f7bd048d4c802c10b7bbc72`. No timing key and no descriptor field changed, so
nothing was regenerated and `candidate_sweep.py:125-126` is untouched. Compiled at 4f8697d under `/usr/bin/python3 -I
-B -X pycache_prefix=<fresh>` (3.9.6) and `uv run python -I` (3.13): identical digests, 64 cells, 21,600 s. (No Apple
3.9 bytecode cache existed for this worktree, so there was nothing to clear.)

## Verification
### Tests
- 14 new tests in `tests/test_hotel_traffic_sweep.py` section 10 (13 in 4f8697d, plus the edge test in ca58974): the
  synthetic cell-15 incident (10 traces
  without the rate span inside window (i): valid, 10 recorded with tokens; the 7a1d97b witness raises the incident's
  message); the same cell sealed and terminal-validated; four defects inside window (i) never blocking (missing edge,
  dangling parent, trace missing, a malformed duplicate span), including requests after readiness; a pause cell keeping
  its permitted truncation while recording two prefix failures; the allowance boundary at 10/s and at 0.05/s (n = 5-6
  successful, allowance 1): exactly the allowance passes, one more blocks; a malformed trace outside (i) still fatal; a
  no-fault cell at 1/s and 0.05/s applying (ii) over its whole window, including its pseudo window; the frozen path
  byte-identical to 7a1d97b with the same three errors; window (i) half-open at both edges (a start exactly at the
  receipt's start is inside, one exactly at readyAt + 3 s is not). Flipping either `<` to `<=` fails that test
  (mutation run in scratch clones).
- Seen failing on the old code: in a clone at 7a1d97b with the new test file, 11 of the 13 fail (the incident test
  with `native trace lacks a required same-trace service edge`); the 2 that pass assert unchanged behaviour (malformed
  outside (i), frozen epoch).
- Worktree, whole suite (`uv run pytest -q --continue-on-collection-errors`): before 909 passed, 37 skipped, 14 failed,
  1 collection error; at ca58974 923 passed (+14), 37 skipped, and the same 14 failed + 1 error by name (12
  `test_online_boutique_lgtm_module.py`, `test_online_boutique_module.py::test_materialized_guards_cover_go_request_path`,
  `test_otel_materialize.py::test_materialized_guards_do_not_load_enabled_implementations_when_disabled`; collection
  error `test_mlflow_manifest.py`, mlflow not installed). Hotel files: 386 passed, 37 skipped. (The reviewer's
  isolated worktree also failed `test_reviewed_patch_applies_to_exact_pinned_hotel_source`; it passes here. The
  changed files are not involved.)
- Frozen epoch with the selector absent (clone at 4f8697d, `study-epoch.json` removed): 415 passed, 6 skipped, 1 failed
  (`test_every_hotel_extension_is_classified`: the extension ledger lists the removed selector). The same single failure
  occurs at 7a1d97b with the selector removed (402 passed there), so it comes from removing the file, not from 4f8697d.
- Measurement repo `uv run pytest -q`: 955 passed, 1 skipped, 3 xfailed. Delta vs the 918 in `CLAUDE.md`: +30
  `test_sweep_analysis.py` (da6c002, ca380a4), +5 `test_unbound_names.py` and +2 `test_protocol_gates.py` vendored-copy
  parameters, both from sibling worktrees.

### Offline replay (capture level; incomplete-trace counts only; no detection time, catch or sensor score computed)
Method: harness 4f8697d (witness and terminal identical at ca58974); `witness.correlate` on each retained cell's inputs, compared with its retained
`correlation.json` without the new block; then, in a scratch copy, the new `correlation.json`, a fresh content seal and
`candidate_terminal.validate_cell`, which is what `run_cell` does after `correlate`. Run under 3.13 and under 3.9 (`-I
-B`); the `traceCompleteness` blocks are identical. Baseline: the 7a1d97b harness replays all 39 sealed cells valid with
byte-identical terminals and reproduces cell 15's error. Script and stripped results:
`tmp/traffic-sweep-decision25-replay-20261003/` (gitignored).
- Relaunch 2 cell 15 now seals **valid**: pre 0, fault-drain **10** (`required-edge-missing` × 10), post-drain 0.
- The 14 relaunch-2 and 25 attempt-2 valid cells stay **valid**, with 0 incomplete traces in every window. Their
  correlation rows, phase counts and fault truth are identical to the retained ones (only the new block is added); their
  terminals differ only by the new block, the correlation digest and the manifest.

| run | # | run ID | pre | fault-drain | post-drain | measurement | replay |
|---|---|---|---|---|---|---|---|
| relaunch 2 | 1 | `search-pause-effect-r10-b01-full-a01` | 0 | 0 | 0 | — | valid |
| relaunch 2 | 2 | `search-pause-effect-r0p05-b01-full-a01` | 0 | 0 | 0 | — | valid |
| relaunch 2 | 3 | `search-pause-effect-r0p2-b01-full-a01` | 0 | 0 | 0 | — | valid |
| relaunch 2 | 4 | `no-fault-calibration-r0p2-b01-full-a01` | — | — | — | 0 | valid |
| relaunch 2 | 5 | `no-fault-calibration-r1-b01-full-a01` | — | — | — | 0 | valid |
| relaunch 2 | 6 | `no-fault-calibration-r0p05-b01-full-a01` | — | — | — | 0 | valid |
| relaunch 2 | 7 | `cpu-throttle-effect-r10-b01-full-a01` | 0 | 0 | 0 | — | valid |
| relaunch 2 | 8 | `net-delay-effect-r1-b01-full-a01` | 0 | 0 | 0 | — | valid |
| relaunch 2 | 9 | `cpu-throttle-effect-r0p05-b01-full-a01` | 0 | 0 | 0 | — | valid |
| relaunch 2 | 10 | `net-delay-effect-r0p05-b01-full-a01` | 0 | 0 | 0 | — | valid |
| relaunch 2 | 11 | `search-pause-effect-r1-b01-full-a01` | 0 | 0 | 0 | — | valid |
| relaunch 2 | 12 | `no-fault-calibration-r10-b01-full-a01` | — | — | — | 0 | valid |
| relaunch 2 | 13 | `net-delay-effect-r0p2-b01-full-a01` | 0 | 0 | 0 | — | valid |
| relaunch 2 | 14 | `cpu-throttle-effect-r0p2-b01-full-a01` | 0 | 0 | 0 | — | valid |
| relaunch 2 | 15 | `net-delay-effect-r10-b01-full-a01` | 0 | 10 | 0 | — | valid |
| attempt 2 | 1 | `search-pause-effect-r10-b01-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 2 | `search-pause-effect-r0p05-b01-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 3 | `search-pause-effect-r0p2-b01-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 4 | `no-fault-calibration-r0p2-b01-full-a01` | — | — | — | 0 | valid |
| attempt 2 | 5 | `no-fault-calibration-r1-b01-full-a01` | — | — | — | 0 | valid |
| attempt 2 | 6 | `no-fault-calibration-r0p05-b01-full-a01` | — | — | — | 0 | valid |
| attempt 2 | 7 | `cpu-throttle-effect-r10-b01-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 8 | `net-delay-effect-r1-b01-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 9 | `cpu-throttle-effect-r0p05-b01-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 10 | `net-delay-effect-r0p05-b01-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 11 | `search-pause-effect-r1-b01-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 12 | `no-fault-calibration-r10-b01-full-a01` | — | — | — | 0 | valid |
| attempt 2 | 13 | `net-delay-effect-r0p2-b01-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 14 | `cpu-throttle-effect-r0p2-b01-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 15 | `net-delay-effect-r10-b01-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 16 | `cpu-throttle-effect-r1-b01-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 17 | `cpu-throttle-effect-r0p2-b02-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 18 | `net-delay-effect-r10-b02-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 19 | `no-fault-calibration-r0p2-b02-full-a01` | — | — | — | 0 | valid |
| attempt 2 | 20 | `search-pause-effect-r0p05-b02-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 21 | `search-pause-effect-r10-b02-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 22 | `net-delay-effect-r0p2-b02-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 23 | `no-fault-calibration-r10-b02-full-a01` | — | — | — | 0 | valid |
| attempt 2 | 24 | `net-delay-effect-r0p05-b02-full-a01` | 0 | 0 | 0 | — | valid |
| attempt 2 | 25 | `search-pause-effect-r0p2-b02-full-a01` | 0 | 0 | 0 | — | valid |

`—` = the window does not exist for that cell kind. Attempt 2's cell 26 (stopped on the 0xbf log byte, amendment 1) is
out of scope here: its run root has no `application.log`.

### Dry run (2026-10-03 13:43Z, `DRY_RUN=1`, read-only guards against fb14srv4; first passed at 4f8697d, 13:23Z)
Log `scratchpad/gate-drivers/hotel-sweep1r3dry2-launch.log`:
```
13:43:05Z === hotel launcher sweep1r3dry2 (HEAD ca58974 on hotel-protocol-20261002, plan 766063c5…, 64 cells, dry=1) ===
13:43:14Z previous runs on host: 1 [hotel-v1-20261003t111746z-cc971de7 ]
13:43:22Z host preflight: containers=0 compose=[]  free GB=172
13:43:22Z setup-campaign status: HEAD ca589747… authorized 2026-10-03T04:54:39Z deadline 2026-10-10T04:54:39Z live=True invariants match=True
13:43:22Z DRY RUN: all guards passed; stopping before the first mutation
```
Relaunch 2's run directory is still on the host. Its local archive `tmp/hotel6-evidence/hotel-v1-20261003t111746z-cc971de7.tgz`
exists, so the guard passed. In non-dry mode the launcher itself moves that run's host paths aside (a move, never a
delete) before `auto`. Nothing was moved during this work.

## Relaunch
- **Hotel, all 64 cells: the 3rd relaunch**, beyond `BUDGET.md` rule 4, approved explicitly by the user (decision 25).
  Same plan, run IDs and seeded onsets as attempt 2 and relaunch 2. Kill date unchanged (2026-10-06 12:00Z).
- Proposed, as amendment 1 did for attempt 2: relaunch 2's cells (14 valid on the host, and cell 15 valid only in this
  offline replay) are **not pooled** with relaunch 3. They are same-plan repeats under an older harness, and any use of
  them is exploratory. (Scope and meaning are the user's to decide.)
- Command, from the measurement repo:
  ```
  HOTEL_ROOT=$PWD/../observability-placement-runtime-hotel-protocol COMPILER=candidate_sweep.py \
  EXPECTED_PLAN=766063c5a0f0b90ab1aba1ada29b86e152e8ec1e7f7bd048d4c802c10b7bbc72 RUN_COUNT=64 \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_hotel.sh sweep1r3 > scratchpad/gate-drivers/hotel-sweep1r3.out 2>&1 &
  nohup uv run python tools/wandb_campaign.py follow sweep1r3 scratchpad/gate-drivers/hotel-sweep1r3-launch.log \
    > scratchpad/gate-drivers/wandb-sweep1r3.out 2>&1 &
  ```
- The analysis stays blind: no detection result of attempt 2, relaunch 2 or this replay has been looked at.

## Review
Independent review: one read-only adversarial review of 4f8697d by a separate subagent (Fable, `adversarial-review`
agent), 2026-10-03. It found no blocker, 2 majors (both recorded above as known residuals: lost frontend root, in-flight
at onset) and 6 minors (edge tests and the short SHA, fixed in ca58974; the rest recorded above). This draft itself has
not been reviewed separately.
