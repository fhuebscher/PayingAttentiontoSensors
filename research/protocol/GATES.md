# Generic gates: keep / fold / drop, wiring, vendoring

Status 2026-10-02: **draft, unreviewed, nothing wired.** No harness has been edited. The keep/fold/drop rows below
need the user's approval before any harness commit (PLAN_FABLE part 4, gate G2 of its schedule). Scope label:
**method** for the gate set, **instance** for every file:line (pinned commits below).

- Module: `src/obsplacement/protocol_gates.py`. Its docstring holds the normalised cell schema, the gate rules and the
  engineering defaults.
- Tests: `tests/test_protocol_gates.py`. It holds the planted defects, G1 on scheduled opportunities, the 3.9 floor,
  the vendored sha256 check, and an xfail inventory of the count literals.
- Spec: `research/PROTOCOL_DRAFT_20261002.md` §4. Source map: `research/protocol-review-20261002/PLAN_FABLE.md` part 4.
  The gates are lifted from `research/visibility-map/traffic_gate.py:56-169`.

## What was checked, and how

- Self-check, run as `/usr/bin/python3 -I -B src/obsplacement/protocol_gates.py --self-check` (CPython 3.9.6) and under
  `uv run` (3.13). The healthy campaign passes every gate. Each of the 8 planted defects fails exactly its own gate, and
  every blocking defect stops the campaign at the planted cell. `--break <gate>` forces a gate to pass; the self-check
  then reports MISSED for every one of the eight gates. That last check is the one that shows the guard can fail.
- `uv run pytest -q tests/test_protocol_gates.py`: 76 passed, 1 skipped (no vendored copy exists yet), 3 xfailed
  (literal inventory). Whole suite: 906 passed, 2 skipped, 3 xfailed; without this file, 830 passed, 1 skipped. The
  CLAUDE.md baseline of 565 predates the three `-protocol` worktrees, which `test_unbound_names.py` also scans.
- Independent review: an `adversarial-review` subagent on Opus, read-only, 2026-10-02 (the Fable run hit its rate
  limit). It confirmed the four corrected/moved rows and every TeaStore literal line. It found one blocker, five majors
  and nine minors; all are fixed in this version except where **Open** says otherwise:
  - **Blocker:** G1 on scheduled opportunities alone is true by construction. Every harness ledger pre-allocates one
    row per plan slot (OTel: `scheduledAtEpoch` = start + i / rate in all 66 retained ledgers), so given G4 it cannot
    fail, and the draft 3 §5 challenge "no traffic in the window" would pass.
  - **Majors:** P0 passed on an empty proof map; G2 hid pre-onset timeouts that ended after onset; G4 treated missing
    channel counts and a missing profile rate as pass; F1 accepted a copied scheduled onset; the literal scan covered
    the validators only.
- Every file:line in PLAN part 4 was re-read at the pinned commits. Results are in the tables (✓ = as cited; **moved**
  or **corrected** = PLAN's citation was wrong or out of date).

Worktrees and commits (checked with `git -C <wt> log -1`; all four `status` clean apart from untracked notes in
`tmp/otel-v2-admission`):

| tag | worktree | commit | role |
|---|---|---|---|
| RT-H | `../observability-placement-runtime-hotel-srv4` = `../observability-placement-runtime-hotel-protocol` | e4fd4c7 | Hotel; the `-protocol` copy is the wiring target |
| RT-T | `../observability-placement-runtime-teastore-sys` = `../observability-placement-runtime-teastore-protocol` | c1724b1 | TeaStore; same |
| RT-O | `tmp/otel-v2-admission` | 64ba7c9 | OTel v2/v3 (the lineage PLAN cites) |
| RT-OP | `tmp/otel-offpath` = `../observability-placement-runtime-otel-protocol` | 92be2b7 | OTel off-path; **the OTel wiring target** |

All paths below are relative to `modules/<sut>/` in that worktree. The OTel wiring target is RT-OP, not RT-O, so the
OTel table cites RT-OP wherever the two differ.

## The generic gate set (draft 3 §4)

| gate | blocking | rule (exact thresholds in the module docstring) |
|---|---|---|
| P0 provenance | yes | namespace empty; every measured service's image pinned by `sha256:` digest; posture proved by connection count or emitted bytes: an observation for every expected emitter, at least one nonzero, none outside the posture's expected set (one silent expected emitter is reported, not blocking) |
| R1 ready | yes | `—` if the profile declares no services or routes; every measured service running; 200 on every declared route; ledger receiving rows; every collected channel ≥ 1 record after warm-up; `readiness_action`: restart once, then stop and ask |
| R2 base state | yes | fresh project and `down -v` |
| R2.recovery | **no** (carry-over record) | last 60 s of a fault cell: G2's bound, and p50 ≤ 1.5 × the pre-onset p50 |
| F1 fault truth | yes, fault cells | manifested, reverted; onset stamped immediately before the command (`pre-command` only: a post-command probe is F-ADH-085, and a copied scheduled onset would make the schedule check trivially true); onset within 1 s of schedule; hold bounded by the two commands; inside the measurement |
| G1 traffic | yes | **scheduled** opportunities in the window ≥ max(1, ⌈0.5 × rate × s⌉) **and** ≥ `G1_MIN_DISPATCHED` (= 1) of them started in the window. The second condition is **not in draft 3's wording**; see Open |
| G2 healthy before | yes | rows scheduled in [m0, onset), attributed by schedule even if they end after onset: successes ≥ ⌈0.5 × rate × s⌉ and failure share ≤ 0.05 (dropped = failure) |
| G3 false-alarm rate | analysis side, population | k/n_eff per sensor family over valid no-fault windows (valid implies G1, G2) that pass the can-fire check; n_eff = 0 fails |
| G4 provenance | yes | ledger (not a proxy), fault timing, validity recorded; offered == plan.offered; plan.offered == rate × duration (± 1); plan rate == profile rate (no profile rate fails); ≥ 95 % of ledger rows and of every collected channel's records inside the cell (a collected channel without counts fails) |
| stop | — | `stop_decision`: stop and ask on the first invalid cell. A cell is invalid if any blocking gate is not `pass` (`—` blocks), its kind is neither `fault` nor `nofault`, or the harness's own verdict is invalid |

## Keep / fold / drop

"Fold" means the per-SUT check is replaced by the generic gate named. "Keep" means it stays harness-specific; it is
recorded as a P0 or C1 (collector integrity) record where noted. Each row was re-verified at the commits above.

### Hotel (RT-H, e4fd4c7)

| existing gate | where (verified) | PLAN cite | decision |
|---|---|---|---|
| host condition / foreign project | `execution/candidate_cell.py:679-692` | — | keep → P0 `namespaceEmpty` |
| boundary clean before mutation | `execution/candidate_cell.py:278`, used at `:723-727` | — | keep (P0) |
| rendered-compose image/port/env check | `execution/candidate_cell.py:354-415` (def at 354) | :354-415 ✓ | fold → P0 `imagesByDigest`; the env-per-posture part is driven by profile L4 |
| readiness `/hotels` 200 | `execution/smoke.py:167-182` (`request_ok`, `wait_ready`), called from the cell driver at `execution/candidate_cell.py:752` | smoke.py:174-181 ✓ (the call site was not cited) | fold → R1 route 200 per declared route |
| posture proof | `execution/candidate_cell.py:516` (`_posture_receipt`), written at `:757` | — | keep, recorded as P0 `postureProof` (must be an observed count, not a config read) |
| warm-up must succeed | `execution/candidate_cell.py:759-767` (`--rate 10 --duration 30` literals) | — | fold → R1 + G2; rate and duration from the profile |
| reset per cell | cell driver | — | keep (R2) |
| fault pre/recovery | `faults/compose_pause.py:108` (`inject`); `startedMonotonic` stamped before pause at `:157`; `wait_recovered` `:65`, `:183` | — | keep as F1 inputs |
| ledger/witness denominator | `validation/candidate_terminal.py:489-506` (`_reconciliation`) | — | fold → G4 |
| `NORMAL_EDGES` full-trace check | defined `execution/candidate_pilot.py:107`; enforced in `witness/candidate_evidence.py:452` (fault policy) and `:700` (`_validate_native_trace`) | **corrected**: PLAN cites `candidate_evidence.py:649`, which is the token↔trace bijection check (`:645-656`) | drop as a blocker; record as a profile L2 observed-path comparison |
| `offered != 1200` (×4) | `validation/candidate_terminal.py:498-500`, `:750` | :490-506 ✓, plus `:750` (not cited) | fold → G4 `offeredEqualsPlan` from the plan |
| system samples `len(rows) < 24` | `validation/candidate_terminal.py:667` | not cited | fold → G4: count derived from plan duration / sampler cadence |
| sampler-off retains no `cpu.json` | `validation/candidate_terminal.py:834-835` | — | keep (P0) |
| stop on first invalid cell | `execution/candidate_runtime.py:2654` (`stopped-invalid-cell`), stop condition declared at `:1980` | **moved**: PLAN cites `:2602-2607`, which is the deadline-reserve stop | fold → `stop_decision` (stop and ask) |
| deadline reserve | `execution/candidate_runtime.py:2602-2607` | (cited as the invalid-cell stop) | keep (operational) |
| quarantine of blocked cells | `execution/candidate_cell.py:576` (suffix), `preserve_blocked_evidence` `:590-657`, `_quarantine_blocked_cell` `:660`, called `:899`, `:936` | — | keep |
| cell count | `execution/candidate_runtime.py:497` `CELL_COUNT = _load_compiler().TOTAL_RUNS` | — | keep: derived from the compiled plan, not a literal |

### TeaStore (RT-T, c1724b1)

| existing gate | where (verified) | PLAN cite | decision |
|---|---|---|---|
| namespace empty | `execution/performance_campaign.py:2184` | — | keep → P0 |
| broker first + `wait_broker` | `execution/performance_campaign.py:614-634` | :614-633 ✓ | fold → R1 "trace channel ready" |
| `wait_ready` ≥ 5 OK | `execution/performance_campaign.py:603-612` (`>= 5` at `:608`) | :603-611 ✓ | fold → R1 one 200 per declared route; the `>= 5` literal goes |
| image digests | `execution/performance_campaign.py:59` (`RepoDigests` inspect format) | — | keep → P0 `imagesByDigest` |
| AOP sha | `execution/performance_campaign.py:693`, `:714`, `:2513-2514` | — | keep (P0 posture identity) |
| AMQP writer alive / consumer | `wait_consumer` `:636`, `collector_barrier_acknowledgement` `:863` | — | fold → R1 channel delivering |
| queue purge + exclusive consumer | `purge_queue` `:880`, `validate_queue_proof` `:896` | — | keep (C1) |
| queue non-empty at barrier | `execution/performance_campaign.py:3099-3101` | ✓ | **warning**, not a blocker: a zero-tolerance literal (F-ADH-073..084 class) |
| queue depth cap 25,000 | `:925`, constant `:1227` | — | keep as the only blocking C1 depth rule |
| broker heartbeat proof | `:757-858` | — | keep (C1; the Kieker `heartbeat=0` trap) |
| fault command / controller lateness | `:1938-1946` (refuses > 1 s late at `:1940`) | :1942-1946 ✓ | fold → F1 `onsetOnSchedule` (ONSET_TOLERANCE_S = 1.0 is taken from here) |
| `no-fault-workload-context` (zero failures) | `validation/candidate_pilot.py:1562-1568` | ✓ | fold → G2 at 5 % |
| `independent-fault-ground-truth` | `validation/candidate_pilot.py:1740-1744` | — | keep → F1 |
| `actual-phase-start-floor` ≥ 20 | `validation/candidate_pilot.py:1751-1756` | :1750-1756 ✓ | fold → G1, derived from the rate. Caveat: this guard exists because "nominal scheduling does not prove exposure" (`:1754`). G1's scheduled count is nominal by construction, and its dispatch condition (≥ 1 start) is much weaker than ≥ 20 starts per phase. See Open |
| `effect-context` | `validation/candidate_pilot.py:1757-1767` | ✓ | fold → G2 (before) + R2.recovery (after) |
| `offered-ledger-denominator` `offered == 90` | `validation/candidate_pilot.py:1268`; also `90` at `:1153`, `:1199`, `:1215` (with `91`), `:1224-1225`, `:1231` | **not in PLAN** | fold → G4 `offeredEqualsPlan` |
| ledger / witness / token checks | `:1254` chain, `:1371`, `:2356`, `:2498` | — | keep (G4 provenance records) |
| posture ↔ telemetry | `posture-capture-domain` `:1906` | — | keep (P0) |
| literal 27 / frozen allocation | `validate_campaign` `:2552`, `:2589` (frozen schedule recomputation), `:2605`, `:2619-2622` | :2551-2660 ✓ | **drop** the literal; the population comes from the descriptor |
| abort rule | launcher breaker (`blockedCells >= 3 and validCells == 0`, CLAUDE.md) | — | fold → `stop_decision` |

### OTel (RT-OP, 92be2b7; RT-O, 64ba7c9, where it differs)

| existing gate | where (verified) | PLAN cite | decision |
|---|---|---|---|
| readiness body > 1000 B | RT-O `execution/candidate_remote.py:446-457` (`> 1000` at `:452`) | ✓ (RT-O) | gone in RT-OP; fold → R1 route 200 |
| journey readiness (2 steps 200) | RT-OP `execution/candidate_remote.py:526-539` | ✓ | keep: this is the R1 shape |
| 15 s collector settle | RT-OP `execution/candidate_remote.py:81`, used at `:1233` | **corrected**: PLAN calls it readiness (R1). It runs **after** the workload and the fault join, before the logs are captured, so it is a drain settle. Not present in RT-O | keep as a drain step; R1 channel delivery needs its own after-warm-up count |
| fault manifest / recovery | RT-OP `execution/candidate_remote.py:759-835` (`inject_fault`); RT-O `:658-706` | RT-O ✓ | keep as F1 inputs; target parameterised in RT-OP |
| carrier coverage | `execution/candidate_remote.py:897`; validator `validation/candidate_terminal.py:133`, `:716` | — | fold → G4 scope |
| denominator | `validation/candidate_terminal.py:667` checks `ledger["offered"] != contract["workload"]["offeredRequests"]` (RT-O `:563`) | **corrected**: PLAN says "600 literal". The validator already compares against the contract. 600 is the descriptor value: RT-OP `execution/candidate_pilot.py:732` (`offeredJourneys`), RT-O `execution/candidate_runtime.py:3371` | G4 already holds; the descriptor value is a plan parameter, not a guard literal |
| measurement 600 s | RT-OP `execution/candidate_runtime.py:3425`, RT-O `:3378` | — | plan parameter; G4 `planConsistent` checks it against offered/rate |
| `TARGET_PATH` correlation clip | RT-OP remote `:52`, `:932`, `:1311`; validator `:44`, `:446`, `:464`, `:479`, `:587`. RT-O remote `:49`, `:800-801`; validator `:42` | RT-O ✓ | **drop the clip**; the observed services are compared against the profile's L2 observed path |
| `EXPECTED_RUNS` | RT-OP `validation/candidate_terminal.py:39` = **36** (`:874-882`); RT-O `:39` = 24 | 24 ✓ (RT-O only) | drop; the population comes from the descriptor |
| campaign abort | RT-OP `execution/candidate_remote.py:1388-1460` | — | fold → `stop_decision` |
| preflight, deadline reserve, image identity, workload identity, witness, fault ground truth, CPU replay, posture proof, lattice, connection probe | as PLAN | not re-cited | keep; connection probe recorded as P0 `postureProof` |

### Count literals still present (xfail inventory)

From `count_literals()` in `tests/test_protocol_gates.py`. It scans every `.py` file under `execution/`,
`validation/`, `workload/`, `witness/`, `faults/` and `collectors/` of each `-protocol` worktree's module, and finds:

- comparisons against 1200 / 600 / 90 / 20 / 24 / 27, and every `>= 5`;
- `EXPECTED_* / *_RUNS / *_CELLS = int` (constants ending in `*_SECONDS` excluded);
- dict entries whose key names a count (cells, offered, runs, journeys, requests) and that hold one of those literals.

String literals are not scanned, so Hotel's warm-up `"--rate", "10", "--duration", "30"` at
`execution/candidate_cell.py:761` is missed. **An XPASS means these patterns are gone, not that every literal is.**
Totals: Hotel 6, TeaStore 21, OTel 8. `90` was added to PLAN's list.

| SUT | file: lines | what |
|---|---|---|
| Hotel | `validation/candidate_terminal.py`: 498, 499, 500, 750 | `!= 1200` |
| Hotel | `validation/candidate_terminal.py`: 667 | system samples `len(rows) < 24` |
| Hotel | `workload/candidate_search.py`: 169 | `offered != 1200` |
| TeaStore | `validation/candidate_pilot.py`: 1153, 1199, 1215, 1224, 1225, 1231, 1268 | `90` (offered journeys) |
| TeaStore | `validation/candidate_pilot.py`: 1143 | descriptor literal `"durationSeconds": 600, "offered": 90` |
| TeaStore | `validation/candidate_pilot.py`: 1751 | `>= 20` per phase |
| TeaStore | `validation/candidate_pilot.py`: 2605, 2619 | `== 27`, `"expectedCells": 27` |
| TeaStore | `validation/candidate_terminal.py`: 303, 309, 313, 358 | `!= 27` |
| TeaStore | `validation/candidate_readiness.py`: 486 | `!= 27` |
| TeaStore | `execution/candidate_pilot.py`: 88 | `TOTAL_RUNS = 27` (descriptor source) |
| TeaStore | `execution/candidate_release_installer.py`: 2485, 2579, 2664 | `> 27` journal rows, and others |
| TeaStore | `execution/performance_campaign.py`: 608 | readiness `>= 5` |
| OTel | `validation/candidate_terminal.py`: 39 | `EXPECTED_RUNS = 36` |
| OTel | `validation/candidate_unsupported.py`: 26 | `EXPECTED_CELLS = 18` |
| OTel | `execution/candidate_pilot.py`: 119, 693, 732 | `OFFPATH_DECLARED_RUNS = 36`; window fit `> 600`; descriptor `"offeredJourneys": 600` |
| OTel | `execution/candidate_remote.py`: 1167 | `< 20`: a diagnostic cap on retained mismatches, not a count guard (scanner false positive) |

Descriptor values (TeaStore `execution/candidate_pilot.py:88`, OTel `:732`) are where the plan is defined. They are
plan parameters, not guard literals. They stay, and they move into the descriptor or profile when the workload rule
lands. The test is `xfail(strict=False)`.

## Wiring per harness (proposed; one commit per `-protocol` worktree)

Each harness builds the normalised cell from artefacts it already writes, then calls
`protocol_gates.evaluate_cell(cell, profile)` after the cell's own terminal validation. It calls `stop_decision` before
the next cell. R1 is evaluated inside the cell driver after warm-up; `readiness_action` decides restart or
stop-and-ask. Field mapping:

| normalised field | Hotel | TeaStore | OTel (RT-OP) |
|---|---|---|---|
| `ledger[].scheduled` | `scheduledMonotonicOffsetSeconds` (`opportunity-ledger.jsonl`) | `scheduledMonotonicOffsetSeconds` (`journey-ledger.jsonl`, `recordType` terminal) | `scheduledAtEpoch - startedAtEpoch(ledger)` (`request-ledger.json`) |
| `started` / `ended` | `actualStartMonotonic/actualEndMonotonic - barrierMonotonic` (`opportunity-plan.json`) | `actualStartMonotonic` / `actualEndMonotonic` (already barrier-relative) | `startedAtEpoch` / `endedAtEpoch` minus base |
| `status` ok | `outcome == "completed" and statusCode == 200` | `outcome == "succeeded"` | `status == 200 and error is None` (journey: both steps) |
| `plan` | `opportunity-plan.json` `offered`, `rate`, `durationSeconds` | `journey-ledger.plan.json` `schedule.offered`, `journeysPerSecond`, `durationSeconds` | contract `workload.offeredRequests`, `requestsPerSecond`, `window.measurementSeconds` |
| `fault.*` (all four) | each stamp minus `barrierMonotonic` | barrier-relative offsets | barrier-relative offsets |
| `fault.onsetCommandIssued` | `startedMonotonic` (pre-command, `compose_pause.py:157`) | **missing**: `actualOnsetMonotonicOffsetSeconds` is post-command (F-ADH-085), and F1 no longer accepts a copied scheduled onset. A pre-command stamp must be added | `actualOnsetMonotonicOffsetSeconds` (pre-command, `candidate_remote.py:798`) |
| `fault.onsetCommandReturned` | `appliedMonotonic` (`:165`, an upper bound) | **missing**: add | `appliedMonotonicOffsetSeconds` (post-observation, an upper bound) |
| `fault.revertCommandIssued` / `Returned` | `revertingMonotonic` (`:176`) / `unpausedAtMonotonic` (`:181`; not `endedMonotonic`, which follows readiness) | **missing**: add | `revertingMonotonicOffsetSeconds` / `actualOffsetMonotonicOffsetSeconds` |
| `provenance.postureProof` | `posture-proof.json` (must carry observed counts) | `posture-capture-domain` evidence | connection probe (`tmp/otel-v2-admission/.../posture_connection_probe.sh`) |
| `channels[].recordsAfterWarmup` | **missing** | **missing** | **missing** |
| `channels[].recordsInCell` / `recordsTotal` | **missing** | **missing** | **missing** (carrier coverage has the first record only) |

None of the three harnesses records per-channel counts (`recordsAfterWarmup`, `recordsInCell`, `recordsTotal`) or a
per-route readiness map today. R1 therefore returns `—` and G4 fails `scope`; both block until the drivers write
them. That is intended: it is the R1 "ledger receiving rows / every
channel ≥ 1 record" requirement.

Every wiring commit invalidates the approved GATE-PLAN (CLAUDE.md, Gates). It must land in the worktree each driver
pins (`drivers-read-ROOT-not-your-worktree`), together with part 6's controller and workload changes.

## Vendoring rule

1. The source of truth is `src/obsplacement/protocol_gates.py` in this repo. Never edit a vendored copy.
2. Copy it byte-identically to `modules/<sut>/validation/protocol_gates.py` in each runtime worktree (`cp`, no
   reformatting). Target-side code runs as `python3 -I` on 3.9, which drops the script's own directory from `sys.path`,
   so the importing driver must insert its own `validation/` directory explicitly (CLAUDE.md trap).
3. `test_vendored_copy_is_byte_identical` compares the sha256 of every
   `../observability-placement-runtime-*/modules/*/validation/protocol_gates.py` against the source. Today no copy
   exists, so the test skips. Skipped means unverified, not passing.
4. The module is stdlib-only, has no package-relative import, no PEP 604 annotation, no f-string and no dataclass.
   Tests enforce all of this: the `feature_version=(3, 9)` parse, the AST scans, and an execution of the self-check
   under `/usr/bin/python3 -I -B`, which skips when no 3.9 is present. The self-check runs the file as `__main__`, so
   the Apple bytecode cache cannot serve a stale copy.
5. Once vendored, a copy ships in the release bundle and is covered by `tests/test_target_py39_compile.py` after it is
   committed. Today the source file is untracked, so that test does not yet see it.

## Proposed change to `research/visibility-map/traffic_gate.py` (not applied)

traffic_gate.py has its own cell shape: `rows: [(t_start, ok)]`, `m`, `w`. Proposal:

1. Import, don't copy. Add `sys.path.insert(0, str(REPO / "src"))` and `from obsplacement import protocol_gates as pg`.
   The package `__init__` holds only a version string and is 3.9-safe. Set `FLOOR, PRE_FAIL_MAX, SCOPE_MIN = pg.FLOOR,
   pg.PRE_FAIL_MAX, pg.SCOPE_MIN`, and replace `need` with `pg.need`.
2. Each adapter emits a normalised cell. The ledger rows gain `scheduled` from the fields in the mapping table, which
   all three harness ledgers carry. The window comes from the receipt as today. For trace-only proxies, `scheduled =
   started = trace start` and `ledgerKind = "proxy"`, so G4 fails for them by construction, as today.
3. `evaluate()` calls `pg.g1`, `pg.g2` and `pg.entry_rule_can_fire` per cell, and `pg.g3` for the population.
   traffic_gate's population-level G4 (invalid scored cells, ledger share) stays local, because `pg.g4` is per cell;
   it can call `pg.g4` per cell for the presence checks.
4. `--self-check` delegates to `pg.self_check(broken=...)`, which replaces the module-global `BROKEN`. traffic_gate's
   own synthetic population can stay as an adapter test.
5. Expected effect, checked on OTel only. The scheduled count changes no verdict on the 33 retained OTel fault cells
   (12 in `tmp/otel-v3-evidence`, 12 in `tmp/otel-v3a2-evidence`, 9 in `tmp/otel-run3-evidence`; windows as
   traffic_gate reads them). **That is true by construction, not evidence**: the scheduled count is the plan's slot
   count (155 per ~155 s window at 1/s). The informative number is the start count, 85-86 against a floor of 78. A
   pause about 1.4× longer would fail a start-based G1. The dispatch condition (≥ 1 start) passes all 33. Hotel and
   TeaStore: not run (`?`). The script below was run with `uv run python <script> <evidence roots>`:

   ```python
   import json, sys, pathlib
   sys.path.insert(0, "src")
   from obsplacement.protocol_gates import need
   for root in sys.argv[1:]:
       for d in sorted(pathlib.Path(root, "runs").glob("*/*")):
           iv = d / "intervention.json"
           if not (d / "request-ledger.json").exists() or not iv.exists():
               continue
           led = json.loads((d / "request-ledger.json").read_text()); v = json.loads(iv.read_text())
           a, b = v["actualOnsetMonotonicOffsetSeconds"], v["actualOffsetMonotonicOffsetSeconds"]
           base, rate = led["startedAtEpoch"], float(led["ratePerSecond"])
           sch = sum(1 for q in led["requests"] if a <= q["scheduledAtEpoch"] - base <= b)
           st = sum(1 for q in led["requests"] if a <= q["startedAtEpoch"] - base <= b)
           print(d.name, round(b - a, 1), need(rate, b - a), sch, st)
   ```

## Open (`?`)

- **G1's dispatch condition (user decision).** Draft 3 §4 says G1 counts scheduled opportunities. Read literally, that
  cannot fail given G4 (see the review blocker). The module adds "≥ 1 dispatched start in the window"
  (`G1_MIN_DISPATCHED = 1`), which rejects the §5 "no traffic in the window" challenge and still passes a
  concurrency-capped stall. Setting it to 0 restores the literal rule. A stronger floor, such as starts ≥ a fraction
  of the scheduled count, would also catch a near-total stall. It would also fail OTel's frontend-pause cells only if
  the fraction were above ~0.55 (85/155). This changes what a valid cell is, so it is the user's choice.
- TeaStore's per-phase start floor (≥ 20 before, during and after) has no generic equivalent in this module. Folding
  it into G1 drops the "during" and "after" exposure floors. Either keep it as a TeaStore record, or make G1's dispatch
  floor rate-derived per phase.
- R2.recovery's p50 ratio (1.5) and its 60 s window go beyond §4, since G2 has no latency bound. They are engineering
  defaults and are not blocking. TAU = 0.05 is provisional until the scope mapping (draft 3, decision 5).
- A zero-rate (idle) rung fails G1, G2 and G4 by construction, so it would stop a campaign. Such a rung needs its own
  gate set.
- The vendoring test passes when only some harnesses carry a copy. Partial vendoring is legitimate while wiring is
  under way, so completeness is checked by reading this file, not by the test.
- `test_stdlib_only` compares against 3.13's `sys.stdlib_module_names`. A module added after 3.9 is caught only by the
  3.9 execution test, and that test skips when no 3.9 interpreter is present.
- Whether OTel's `TARGET_PATH` drop needs the profile L2 observed path first (PLAN part 1). Until then the comparison
  has no reference.
