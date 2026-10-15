# OTel campaign B (repeat episodes): declaration FROZEN 2026-10-09 (revised for decision 69), committed alone before launch

Draft only. Freezing means committing it alone under the file name `research/traffic-sweep/DECLARATION_B_OTEL.md`, the path the
pinned descriptor's `declaration` entry names (any other name regenerates the descriptor, the digests and the DRY_RUN). Nothing has been
launched, no declaration frozen and no evidence analysed. Scope of every number here: **instance** (one SUT, one host, fb14srv6).

Authority: `research/PROTOCOL_DRAFT_20261002.md` decision 49 (B: 3 more blocks on TeaStore and OTel after the H10/H4 harness change), 50 (fault
doses inherited from Hotel, a fixed factor), 56 (OTel quiet cells: record trace loss, never block), 66 (collector log sampler off),
**69 (H4 is record, don't block; H10 covers the throttle too, confirmed)**.
Budget and stop rule: `research/traffic-sweep/BUDGET_B.md` (92ca1c7). Design: `NEXT_CAMPAIGNS_PROPOSAL.md` section B. Harness changes:
`research/protocol/METHODOLOGY_HARDENING.md` H10 and H4.

## Binding changes (against the sweep, `DECLARATION_OTEL.md` + `AMENDMENT_OTEL_1.md`)
| item | sweep (relaunch 1) | campaign B |
|---|---|---|
| study epoch | `otel-traffic-sweep-v1` | **`otel-repeat-episodes-v1`** (new; sweep and quiet epochs unchanged) |
| harness commit | `c532853` | **`c4aa313fdfe89c330513146e6098ddf723213ffb`** (branch `otel-protocol-20261002`) |
| cells | 12 (1 block) | **36** = 3 blocks x 3 regimes x 4 rates |
| order | seed 20261003, lead cell pause @ 10/s | **seed 20261009**, Fisher-Yates per block, **no lead cell** |
| fault onset | 1 stratum | **3 strata** over the blocks, per (regime, rate), seeded |
| H10 | a probe right after the fault command (`during-fault`) | **no readiness probe from the onset to the end of the hold**; probes outside it unchanged |
| H4 | `startedMonotonic`, `appliedMonotonic` only | **freeze stamps** in every fault receipt; pause cells also retain `docker-events.json`; **recorded, never blocking (decision 69)**: a failed, dead or contradictory stream or stamp leaves the cell valid, marked `missing` or `contradictory` with reasons and a per-cell failure count |
| trace rule | decision 25 everywhere | **fault cells: decision 25 (as the sweep); no-fault cells: decision 56 (as the quiet epoch)** |
| collector log sampler | collector default (on) | **`service::telemetry::logs::sampling::enabled: false`** (decision 66) |
| descriptor | `be5b0b4d...c86d` | **`6e5d0f3460d28142428221c259994011a3a02973392aca4ffe6a4eb47a81a4ce`** |
| plan, attempt 1 | `09b2563a...4865` | **`3aaf5923a051270f715aab822dafb7d63bbe0c8d6475f984afa2e2317cb2b142`** |
| budget | 12 cells, 3 h window | minimum remaining **13,416 s**, GATE-RUN window **5 h** (36 x 331 s + 900 + 600, + 3,600 s slack, rounded up) |

Unchanged from the sweep, by construction (`candidate_repeat.cell_timing` starts from `candidate_sweep.cell_timing(regime, rate, 1)`; tested key by key):
route `GET /api/products/66VCHSJNUP`, rates 10, 1, 0.2, 0.05 /s, client timeout 15 s, concurrency 300, warm-up 30 s at 10/s, measurement 180 s,
hold 60 s, upstream generator removed after `up`, frontendproxy memory 256 MiB, container-health guard, posture `full` only, protocol gates
(F1, G1, G2, G4 blocking), the faults and doses (decision 50: CPU throttle to 0.1 core, `docker compose pause frontend`).

- Both digests are identical under `/usr/bin/python3 -I` (3.9.6, a fresh `-X pycache_prefix`) and `uv run python -I` (3.13): command
  `candidate_repeat.py --print-digests --attempt 1`, run 2026-10-09 (re-run after decision 69). Run IDs hash the run key (epoch included), so none equals a sweep or quiet ID.
- Spent attempts for the epoch: none. Its first launch is attempt 1.
- Materialized-source digest the GATE-PLAN will carry (local projection, `candidate_transport._projected_materialized_source_sha256`):
  `18fe429c0bcc64a26f641b95223e01688c4f5f2e8451de4c4268cf7f5c55d860` (moves with decision 66; the quiet and sweep values are as before).
- Governance: `095ebab` re-pins the three governed files that moved (`candidate_runtime.py`, `candidate_runtime_adapter.py`,
  `candidate_terminal.py`), by the rule of d101fda / fb02804 / 6a47d0b; `c4aa313` re-pins `candidate_terminal.py` again after decision 69 (the only governed file that
  moved). Activation (selector + tombstone) is `03b60df`; it moved no governed file.

### Commits in the OTel worktree
`dd4b8d7` epoch + H10 + H4 + decision 66 + tests (not activated) -> `095ebab` governance re-pin -> `03b60df` activation (selector and tombstone name the
repeat epoch) -> `0ad9a2c` H4 recorded, never blocking (decision 69; re-pins descriptor and plan) -> `c4aa313` governance re-pin (the frozen HEAD). Same order as the quiet epoch
(36d2e15, fb02804, 6e37ec2, c80fe88, 6a47d0b).

## The 36 cells (attempt 1; onset = seconds after the barrier at which the fault command is issued)
Block order hashes: b1 `a6f521c01240`, b2 `6fac3bab1afa`, b3 `6d2fed2b949d` (first 12 hex of `orderSha256`). Every block holds all 12 (regime, rate) pairs once.

| block | pos | regime | rate /s | onset s | run id |
|---|---|---|---|---|---|
| 1 | 1 | frontend-pause | 0.05 | 64.255 | 6d985fbb9e7f4660dfee0e9b |
| 1 | 2 | frontend-pause | 0.2 | 63.688 | be67e00e6994fa15f7d3c685 |
| 1 | 3 | frontend-pause | 10 | 60.023 | cd307cae929a22f623bbbc7d |
| 1 | 4 | no-fault | 0.2 | 60.847 | 177e0350dd15ee90d6d101f7 |
| 1 | 5 | frontend-pause | 1 | 60.126 | 49e8e7780cbdc205f00226a2 |
| 1 | 6 | productcatalog-throttle | 10 | 60.014 | f9cec92729824b339922ad0a |
| 1 | 7 | productcatalog-throttle | 0.2 | 64.474 | 0124051b9c4698d993ea2b3b |
| 1 | 8 | productcatalog-throttle | 0.05 | 71.173 | caad0cf7368ca512f4dee00f |
| 1 | 9 | no-fault | 0.05 | 74.078 | 8bcea499622dd80866c53021 |
| 1 | 10 | no-fault | 10 | 60.006 | 8a21d52b2d936fee4d15ce55 |
| 1 | 11 | no-fault | 1 | 60.235 | 75177498379979de4c487a6c |
| 1 | 12 | productcatalog-throttle | 1 | 60.731 | b5079278b214f57a69340327 |
| 2 | 1 | no-fault | 0.05 | 64.999 | e669eee9baac60a002c32cc5 |
| 2 | 2 | frontend-pause | 0.05 | 73.428 | f4eb276cd9a4498d296c28e3 |
| 2 | 3 | frontend-pause | 0.2 | 62.722 | 6faae9e5e4aac5a04346eba2 |
| 2 | 4 | frontend-pause | 1 | 60.617 | 4a21aa27cdb5dff6a87d684b |
| 2 | 5 | productcatalog-throttle | 10 | 60.072 | 22857404e4a5b713be9a8757 |
| 2 | 6 | no-fault | 1 | 60.507 | 4ecb47446d3a262707d36f35 |
| 2 | 7 | frontend-pause | 10 | 60.075 | d21ba7fb081c015685858133 |
| 2 | 8 | productcatalog-throttle | 1 | 60.127 | 0dbf22d3c8d49279f781d821 |
| 2 | 9 | no-fault | 0.2 | 63.585 | db0bd325de155392bc700b26 |
| 2 | 10 | productcatalog-throttle | 0.05 | 79.755 | b658fbd63c02ba40e6efa083 |
| 2 | 11 | productcatalog-throttle | 0.2 | 60.325 | 9b7143038297ea85959c33fb |
| 2 | 12 | no-fault | 10 | 60.039 | 173aa5c225b06a79fa5968cd |
| 3 | 1 | productcatalog-throttle | 10 | 60.040 | b05d634489f5b1c37353e2cb |
| 3 | 2 | no-fault | 0.05 | 73.237 | 10ac44fdd55a051b14286250 |
| 3 | 3 | productcatalog-throttle | 1 | 60.448 | fbed41b9a50f9fc78fe91afa |
| 3 | 4 | no-fault | 1 | 60.954 | 3f69b752d7b1f5728f0f2fc4 |
| 3 | 5 | frontend-pause | 10 | 60.038 | 5e0891ddaace1f6a7ab92d7d |
| 3 | 6 | frontend-pause | 0.2 | 60.356 | f0f02b06c0de1cfde5579535 |
| 3 | 7 | productcatalog-throttle | 0.05 | 64.972 | 1780419bc84f3952f0730009 |
| 3 | 8 | productcatalog-throttle | 0.2 | 62.233 | f3a0a9d83a9a522badf026a7 |
| 3 | 9 | frontend-pause | 1 | 60.916 | 7807d2055ae6768998913f98 |
| 3 | 10 | no-fault | 0.2 | 62.092 | 482b999c3f15b7b1b5ad6ebb |
| 3 | 11 | no-fault | 10 | 60.070 | 30cad1e8776b51c8d9b33475 |
| 3 | 12 | frontend-pause | 0.05 | 70.077 | 19461fb491b39768eb492c22 |

(Onsets are the ones in the plan; the fault command may be issued up to 0.05 s early and F1 allows 1 s late. No-fault cells carry the same seeded
window as a pseudo window for G1/G2 and false alarms.) With the sweep's own block that makes 4 episodes per (regime, rate) pair, like Hotel; the
sweep's episode ran on a harness without H10/H4, so the pooled four are not one design: a pooling question for analysis v3, not decided here.

## Which trace-completeness rule applies to which cell
- **Fault cells (24: frontend-pause 12, productcatalog-throttle 12): decision 25**, exactly as the sweep. No timing key. Windows by request start
  (pre-onset, fault-and-drain = onset command issued to route ready + 17 s, after-drain); incomplete traces in fault-and-drain are recorded and
  never block; the cell is blocked if the successful requests of the other windows with an incomplete trace exceed max(1, floor(1 % of them)).
  This block still stops a campaign (the sweep's attempt 1 stopped on it).
- **No-fault cells (12): decision 56**, exactly as the quiet epoch. Timing key `traceCompletenessRule = "protocol-decision-56"`: one
  whole-measurement window, incomplete traces counted and recorded (per missing service, with contiguous runs), never blocking; decision 25's
  allowance recorded as a counterfactual only.
- Enforced, not conventional: a fault cell that carries the key, or a no-fault cell that lacks it, is refused (`candidate_remote.names_trace_rule`,
  the runtime's per-cell-kind timing key sets). The sweep's and quiet epochs' records are byte-identical to `6a47d0b`'s (tested).
- What stays blocking in every cell: G1, G2, G4 (F1 in fault cells), the container-health guard, and the terminal's ledger, witness,
  generator-absence, posture and application-log checks. The campaign stops on the first invalid cell.

## H10: no readiness probe during the fault
- Compiled timing `duringFaultProbe: false`; scenario `entryRouteDuringFault: "not-probed-h10"` for both faults (the sweep's pause was
  `must-be-unavailable`, its throttle `recorded-not-required`). Applies to **both** fault types: the throttle's during-fault route observation is dropped too.
- `intervention.json`: `duringRouteAvailable` is `null`, `probes` holds the post-revert readiness probes only (phase `post-revert`).
  Window: from the onset command's issue to the end of the hold (the revert command's issue); the first post-revert probe starts after the revert
  command returns. Probes outside it (stack readiness and route readiness before the warm-up) are unchanged.
- Manifestation is therefore proven by the paused container state (pause) or the applied NanoCpus (throttle) read back, and for a pause by the
  Docker `pause` event. The route's unavailability is no longer observed; a claim that needs it must say so.
- Proof: the fake target logs every readiness-token request with its monotonic start; the test asserts none lies in [barrier + onset, barrier + onset + hold],
  that probes exist before the barrier and after the window, and that the terminal rejects a probe stamped in the window. Planted defect: reinstating
  the probe is caught by the runner's flag/contract guard, and, with that guard removed, by the test's checker and by the terminal.

## H4: stamp the freeze, recorded and never blocking (decision 69)
**Rule.** H4 never invalidates a cell. A failed, dead or contradictory event stream or freeze stamp leaves the cell valid and the freeze record marked
`missing` (an absence: the stream could not start or had died, no pause or unpause event) or `contradictory` (stamps or events that disagree: duplicate
events, an event outside its command's interval, an unparseable line, stamps out of order), with the reasons and a failure count per cell. The
terminal replays and byte-compares whatever was retained: a record that does not replay from its own raw lines, clock and receipt, a differing identity or clock, or
offsets that do not derive from the barrier is **refused** (integrity, not H4 availability); a record that replays and says `missing` or `contradictory` is accepted and
reported (`status`, `failures`) in the cell's report. A cell is still invalid if the fault itself failed to manifest or recover (unchanged; that is not H4).
H4 is therefore not a stop condition of the campaign.

Receipt (`intervention.json`), every fault cell, new key `freeze` (schema 1, kind `otel-demo-fault-freeze-stamps-v1`):

| field | meaning |
|---|---|
| `action` | `pause` or `cpu-throttle` |
| `commandIssuedMonotonic` | monotonic clock, immediately before the fault command; equals `startedMonotonic` |
| `commandReturnedMonotonic` | taken when the fault command returns, before the state readback (new) |
| `stateReadbackMonotonic` | after `docker inspect` showed the state; equals `appliedMonotonic` (kept) |
| `commandIssuedOffsetSeconds`, `commandReturnedOffsetSeconds`, `stateReadbackOffsetSeconds` | the three above minus `barrierMonotonic` |
| `dockerEventsFile` | `"docker-events.json"` for a pause, `null` for a throttle |
| `stampCheck` | record `{status: ok \| missing \| contradictory, failures: n, reasons: [{kind, reason}]}`: expected issued <= returned <= readback, issued = `startedMonotonic`, readback = `appliedMonotonic`, returned <= `revertingMonotonic` |

Pause cells also retain **`docker-events.json`** (kind `otel-demo-fault-docker-events-v1`, schema 1), written for every pause cell even when the stream failed. A live `docker events` stream
(`--since <epoch - 1 s> --filter type=container --filter event=pause --filter event=unpause --filter label=com.docker.compose.project=<project> --format '{{json .}}'`)
is started before the barrier and stopped after the fault worker has settled (a stream, because the daemon's replay buffer is bounded and a 25-container
stack's health checks can roll it over inside a cell). A stream that cannot start or stop is recorded (`stream.error`), not fatal.

| key | content |
|---|---|
| `schemaVersion`, `kind`, `runId`, `service`, `containerId` | identity; `containerId` is the receipt's `targetContainerId` |
| `clock` | `barrierMonotonic`, `barrierEpoch` (the ledger's), `mapping` (text), `stopPair` {`epoch`, `monotonic`} read when the stream stopped, for drift checks |
| `stream` | `argv`, `sinceEpoch`, `exitedBeforeStop`, `returnCode`, `stderr` (first 2,000 chars), `error` (null or why the stream could not be used) |
| `raw` | the stream's JSON lines, verbatim |
| `events[]` | per parsed line: `action`, `containerId`, `service`, **`timeNano`** (event time, ns), `offsetSeconds` = `timeNano / 1e9 - barrierEpoch`, `monotonic` = `barrierMonotonic + offsetSeconds` |
| `parseProblems[]` | lines that could not be parsed (skipped, and a `contradictory` reason) |
| `verdict` | `status` (`ok` \| `missing` \| `contradictory`), `failures` (= number of reasons), `reasons[{kind, reason}]`, `pauseEvents`, `unpauseEvents`, `pauseOffsetSeconds`, `unpauseOffsetSeconds`, `onsetIntervalSeconds` = [`commandIssuedOffsetSeconds`, pause event offset], `otherContainerEvents` |

`status` is `ok` iff the stream was alive when stopped, there is exactly one `pause` and one `unpause` event of the target container, the pause event lies in
[commandIssued, commandReturned] and the unpause event in [revertCommandIssued, revertCommandReturned], each widened by **0.25 s** (an engineering default: the mapping reads
two clocks at the barrier; to be checked on the first pause cell), and the unpause follows the pause. `missing` if every reason is an absence, `contradictory` otherwise. Events of other
containers are recorded and do not count. For a throttle there are no events: its onset interval is [commandIssued, commandReturned] plus the applied quota read back.
Per decision 69, analysis falls back on a `missing` or `contradictory` record to the sweep's own onset bound (OTel: `appliedMonotonic`; the `freeze` block's command-issued and command-returned offsets are recorded beside it); a `contradictory` record's `onsetIntervalSeconds` is not used. Known review notes, not blocking: the terminal re-derives H10 from the receipt's probe stamps only, not from the raw carrier; the `docker events` argv and the terminal's H10 window line are pinned by self-consistency only (ledgered).

Tests (all in `tests/test_otel_repeat_episodes.py`): the stream defects that invalidated a cell in the first draft (pause or unpause dropped, both dropped, duplicated pause, 10 s late, stream dead,
unparseable line, stream that cannot start) leave it valid with the expected status and failure count, and the terminal accepts the record; contradictory producer stamps leave a throttle cell valid
(`contradictory`, 1 failure); a consistently recorded contradiction (event moved 4 s late with its verdict recomputed) is accepted, and the same raw edit with the verdict left `ok` is refused; tampering
refused: events edited without their raw lines, a hidden parse problem, a failed stream relabelled alive, a relabelled verdict or stamp check, a moved clock, a swapped container, an undeclared action,
broken freeze offsets or identity, a missing or extra events file. A harness that drops H4 altogether (`freeze_enabled` patched off) still yields an invalid cell (the events file is part of the cell's declared population).

## Decision 66: collector log sampler off
`modules/otel-demo/materialize.py` renders `service:\n  telemetry:\n    logs:\n      sampling:\n        enabled: false` into
`src/otelcollector/otelcol-placement.yml` **when the committed selector of its own tree names `otel-repeat-episodes-v1`**; no other epoch renders it
(the materialized source of the frozen, sweep and quiet epochs is byte-identical to the base commit's materializer, tested). The key was checked
against the pinned collector (`otel/opentelemetry-collector-contrib:0.108.0`, `.env`): `LogsSamplingConfig.Enabled` with tag `enabled` in
`service/telemetry/config.go` at tag v0.108.0 (read online 2026-10-09), and the pinned image's `otelcol-contrib` (from `docker save` on fb14srv6, read-only)
carries the type `telemetry.LogsSamplingConfig`. **Not confirmed offline:** the stripped binary does not show the `Enabled` field of that type, so the key itself rests on the
source at the tag. The test pins the collector version, so a bump forces a re-check. Not run: the collector with this config (that needs a container on a host).
Effect to expect: more `otelcol.log` lines than the quiet run's cells for the same traffic; whether the lost-batch pattern disappears is data, not claimed here.

## Stop rules (from BUDGET_B.md; none added)
1. Harness ready by 2026-10-10 12:00Z, terminal 2026-10-12 12:00Z; a system not launch-ready by its deadline is dropped, no extension without the user.
2. A critical-path defect gets 30 minutes; 3 critical-path harness defects in one system stop it. **Defects so far in this build: 0** (own test defects and the
   intended failures of two byte-identity tests, which were replaced by behavioural pins, are not harness defects).
3. Launch only from a declaration committed alone plus a passing DRY_RUN on the host, mirrored to wandb. At most 2 relaunches.
4. No B evidence is analysed until analysis v3 is frozen and reviewed.
Campaign stop rule: first invalid cell. H4 is not among the checks that can invalidate a cell (decision 69). New blocking checks of this epoch that can: the flag/contract guard and the terminal's
integrity replays. Review the first pause cell's `docker-events.json` (`verdict.status`) as soon as it seals.

## Tests and suites (OTel worktree, `uv run pytest -q -p no:cacheprovider -rA --ignore=tests/test_mlflow_manifest.py`)
- Before (`6a47d0b`): 29 failed / 2071 passed / 145 skipped. After (`c4aa313`, clean tree): **29 failed / 2161 passed / 145 skipped.** The 29 failures are the same by name
  (sorted `FAILED` lists compared with `diff`): Hotel materialize 4, Kieker fixture 1, Online Boutique 13, phase-1 control universe 6, science router 1, TeaStore 4. None is OTel.
- Delta +90 passed, fully attributed: +92 new tests in `tests/test_otel_repeat_episodes.py`, -2 parametrisations removed (the terminal from the quiet test's byte-identity list,
  `materialize.py` from the sweep test's); no skipped test changed. A run with the changes still uncommitted showed one extra failure
  (`test_teastore_native_bridge_patch::test_v2_patch_applies...`): it asserts a clean `git status` of the enclosing repo and passes once committed.
- Measurement repo `tests/test_unbound_names.py`: 315 passed; one of its parametrisations is the new `candidate_repeat.py` (+1 from this change; the rest of the count moves with other sessions' modules).
- The new file also runs an AST unbound-name scan over every touched target file, with a planted defect, and parses them with `feature_version=(3, 9)`.
- Not verified: the per-cell runner has run only against the fake target (as for every epoch); `docker events` has not run against a real pause; the posture connection probe
  receipt in the worktree (2026-09-23, PROBE OK) predates this change and was not re-run (no postures changed; the collector config differs only in its own log sampler).

## DRY_RUN (passed, 2026-10-09 12:34Z, on the final HEAD; `scratchpad/gate-drivers/otel-repeat-repeatdry2-launch.log`; the first, `repeatdry1`, was on `03b60df` before decision 69)
```
12:33:59Z === otel offpath launcher repeatdry2 (HEAD c4aa313fdfe89c330513146e6098ddf723213ffb on otel-protocol-20261002, compiler candidate_repeat.py, plan 3aaf5923a051270f715aab822dafb7d63bbe0c8d6475f984afa2e2317cb2b142, 36 cells, attempt 1, dry=1) ===
12:33:59Z compiled: otel-repeat-episodes-v1 36 3aaf5923a051270f715aab822dafb7d63bbe0c8d6475f984afa2e2317cb2b142
12:34:00Z drivers: otel-repeat-episodes-v1 otel-repeat-episodes-v1 5 /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-otel-protocol
probe receipt 2026-09-23T10:03:11Z 23dd90bb20f5 0 42
12:34:24Z host fb14srv6: running units=0 containers=0 lease holders=[] free GB=246 otel-repeat-episodes-v1 paths=0
12:34:24Z DRY RUN: all guards passed; stopping before the first mutation
```
Before the first mutation, the non-dry launcher archives stranded run-phase state, moves any plan dir aside and renews SETUP-CAMPAIGN onto `3aaf5923...`.

## Launch (only after: this draft frozen as `DECLARATION_B_OTEL.md` and committed alone; the harness commit is `c4aa313fdfe89c330513146e6098ddf723213ffb`)
From the measurement repo:
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_repeat.py EXPECTED_PLAN=3aaf5923a051270f715aab822dafb7d63bbe0c8d6475f984afa2e2317cb2b142 \
  RUN_COUNT=36 CAMPAIGN=otel-repeat-episodes-v1 LOG_PREFIX=otel-repeat \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh repeat1 c4aa313fdfe89c330513146e6098ddf723213ffb \
  > scratchpad/gate-drivers/otel-repeat1.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow otel-repeat1 scratchpad/gate-drivers/otel-repeat-repeat1-launch.log \
  > scratchpad/gate-drivers/otel-repeat1-wandb.out 2>&1 &
```
Re-run the DRY_RUN immediately before launching (host state moves): same command with `DRY_RUN=1`, label `repeatdry2`, no `LAUNCH_APPROVED`.

## Open (for the user or the review)
- The 0.25 s event tolerance is an engineering default chosen here; it only decides `ok` vs `contradictory` now, never validity.
- (Closed by decision 69: H4 is record-only; H10 covers the throttle too.)
- No lead cell: the sweep put the pause at 10/s first so its capture could be checked early; here the first pause cell must be checked by hand when it seals.
- Pooling the sweep's episode (no H10/H4) with these 3 is an analysis v3 question.
- An independent review (Fable `adversarial-review`, as for the quiet epoch) has not been run on this build.
