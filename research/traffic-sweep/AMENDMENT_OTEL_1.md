# OTel traffic sweep, Amendment 1: shared trace rule, proxy memory, container-health guard, relaunch 1 (FROZEN 2026-10-03 ~14:45Z)

Amends `DECLARATION_OTEL.md` (frozen 2026-10-03). Authorities: `research/PROTOCOL_DRAFT_20261002.md` decision 25 (user,
2026-10-03 ~13:00Z, all three sweeps) and the user's OTel decision of 2026-10-03 (option A: raise frontendproxy's memory
limit for this epoch; option B, a shorter client timeout, only if the relaunch fails on the same class). Stop record:
`STOP_OTEL_ATTEMPT1.md`. Scope of every number: instance (one SUT, one host, fb14srv6). Frozen by the coordinator after reading commits 82a6269 and c532853, committed alone before relaunch 1.

## Binding change
| item | attempt 1 | relaunch 1 (attempt 2) |
|---|---|---|
| harness commit | `6380cce` (activation) | **`c5328531b94e6321fbf27ab1d263448754dda76e`** = `f9f480f` (decision 25) + `ecb0f8e` (re-pin) + `82a6269` (memory limit, guard) + `c532853` (re-pin), on 6380cce |
| descriptor | `78d2f0c4…aefa` | **`be5b0b4dcd212aaa47908a6dd533e5cb73a104ab22b1b9e04a147e21ccb2c86d`** |
| plan | attempt 1 `779b908d…4100` | **attempt 2 `fa770ccf62f3eca24081d0c9ca004c05104250da69ee3422bcf8a172b5349498`** (attempt 1 under this descriptor, `09b2563a…4865`, is spent: its run IDs exist on the host) |
| trace rule | M1 (≥ 99 % complete) | decision 25 |
| frontendproxy memory | upstream 50M | **256 MiB (268,435,456 bytes)**, a declared deviation |
| container-health guard | — | per cell, blocking |
Both digests are identical under `/usr/bin/python3 -I` (3.9.6) and `uv run python -I` (3.13.12). The 3.9 runs used a fresh
`-X pycache_prefix` directory each time, so no cached bytecode could be read; `~/Library/Caches/com.apple.python` was not
deleted. All other design values are unchanged: rates, route, timeout 15 s, concurrency 300, onsets, hold, regimes, 12 cells,
order, lead cell, 3 h window, 5,472 s minimum remaining. The descriptor's `amendments` names
`research/traffic-sweep/AMENDMENT_OTEL_1.md`. Attempt 1 is recorded as spent in `candidate_runtime_adapter.py:305-308`.

## 1. Trace completeness: decision 25 (`f9f480f`)
Windows by request **start**, measured from the barrier on the fault receipt's monotonic clock
(`modules/otel-demo/execution/candidate_remote.py` `trace_completeness`):
- fault cells have three windows: **pre-onset** (before the onset command was issued), **fault-and-drain** (from the onset
  command to the route being ready again plus 17 s, i.e. client timeout + 2 s) and **after-drain**;
- no-fault cells have one window, **whole-measurement**.

The rule:
- (i) Incomplete traces in fault-and-drain are counted and recorded with their tokens. They never block.
- (ii) In every other window, a cell is blocked only if more than max(1, floor(0.01 × successful requests)) successful
  requests lack a complete trace.
- (iii) Every incomplete trace is counted per window in `trace-completeness.json`: successful and unsuccessful requests,
  separately.
- The rule is evaluated on the target before the next cell, and the terminal replays it byte for byte.
- Drain, share and minimum come from the compiled timing (`candidate_sweep.py` `TRACE_*`), not from code literals.

Reading used by this relaunch: (ii) rules only on successful requests, as M1 did; G2 already rules on failures before onset. Open for the user as decision c in `research/REVIEW_LIST_20261004.md`.

## 2. frontendproxy memory 50M → 256 MiB (`82a6269`)
**Evidence.** srv6's kernel log records `Memory cgroup out of memory: Killed process … (envoy)` twice:
- at 11:46:59Z, 12.0 s after the lead cell's frontend-pause onset at 10/s (barrier 11:45:47.80Z, onset +60.04 s), with
  anon-rss ~46 MB and file-rss ~41 MB against upstream's 50M (`docker-compose.yml:319-320` at 2d4661e);
- again at 11:59:31Z, 31 s after cell 3's window ended (throttle at 10/s). That kill came after that cell's captures, so its
  evidence is intact. Its timing points to the post-window posture probes (a `docker exec` into the proxy), but that is
  inferred.

**Mechanism.**
- Compiled timing `serviceMemoryLimitBytes: {"frontendproxy": 268435456}`. The descriptor records it under `sutDeviations`
  (upstream value, sweep value, mechanism, reason, scope: this epoch only).
- `candidate_remote.apply_memory_limits` runs `docker update --memory 268435456 --memory-swap <same swap ratio>` on the
  running proxy right after `compose up`, before readiness, and checks the result by inspect.
- The overlays and every frozen epoch keep 50M.

**Size check (arithmetic, one observation).**
- At the kill, about 120 requests were waiting: 12 s × 10/s, none yet at its 15 s timeout. The cgroup charge was then at the
  50 MiB limit.
- Cost per waiting request: at most 50/120 ≈ 0.42 MiB even if Envoy's idle footprint were zero; about 0.17–0.25 MiB if the
  idle footprint is 20–30 MiB.
- In steady state at 10/s, at most rate × timeout = 150 requests wait, because Envoy's 15 s route timeout and the client's
  15 s timeout both cap them. That gives about 30 + 150 × 0.25 ≈ 68 MiB.
- Worst case, all 300 workers waiting at the upper cost: 30 + 300 × 0.42 ≈ 156 MiB.
- So 256 MiB covers the worst case with about 1.6× margin, and I propose no other number.
- Not measured: Envoy's idle footprint, and its memory during a 10/s pause. The guard below catches a miss.

## 3. Per-cell container-health guard (`82a6269`)
**What is recorded.** `candidate_remote.project_containers` lists every container with the project's Compose label. It
records each container's `State.OOMKilled`, `RestartCount`, status and `HostConfig.Memory`:
- **baseline**: after readiness, before the warm-up;
- **final**: after the captures, before cleanup.

**When a cell is invalid.** `container_health_verdict` invalidates the cell, and the campaign stops, if:
- any container has OOMKilled true;
- an application container restarted or was replaced between baseline and final;
- an application container disappeared;
- a declared memory limit is not in effect.

**Where it goes.**
- The record goes to `container-health.json`, which is a required artifact.
- The terminal replays the verdict from the two inspections and checks the applied limit.
- Infrastructure restarts (for example otelcol) are recorded but do not block.
- The frozen epoch's runner, overlays and contracts are unchanged; the AST test against 92be2b7 passes.

**Tests** (`tests/test_otel_traffic_sweep.py`):
- Planted OOMKilled on frontendproxy or otelcol, and a restarted frontend, each invalidate the cell. These fail on `ecb0f8e`.
- An otelcol restart is recorded and the cell stays valid.
- The run tests check the exact `docker update` argv and that the guard passed.
- Two planted record defects are rejected: an OOM hidden in the record, and a limit that was not applied.
- The decision-25 tests from `f9f480f` still pass. The attempt-1 incident (one incomplete trace in the drain after a pause
  at 0.2/s) fails on 6380cce with `trace completeness 20/21 is below 0.99 (needs 21)` and seals valid now. 300 incomplete
  traces inside fault-and-drain never block. No-fault at 10/s passes with 18 and blocks with 19. At 0.05/s, 1 passes and
  2 block.

**Suites.**
- Worktree, ecb0f8e → c532853: 29 failed / 2032 passed / 145 skipped → 29 failed / 2038 passed / 145 skipped. The +6 are the
  new tests. The 29 failures are the same by name as the pre-change baseline (92be2b7), and none is new.
- Measurement repo `uv run pytest -q`: 955 passed, 1 skipped, 3 xfailed.

## 4. Offline replay of attempt 1 (capture level only; no detection time, catch or score computed)
**Archive.** `tmp/otel-sweep-evidence/otel-traffic-sweep-v1-attempt1.tgz` (17.1 MB, sha256 `10fef8be…f191`, 146 entries).
The sorted sha256 list of its files equals the host's (`226df0e1…dadd`), checked again at 14:38Z before the host move.

**Method.** Session-scratchpad `otel-sweep/replay_attempt1.py`, run against the decision-25 code (`ecb0f8e`):
- the retained content manifest is verified first;
- the cell's timing is replaced by the current compiled timing (only the trace-rule keys differ; asserted);
- `trace-completeness.json` is recomputed;
- for cell 8 only, the receipt is set to valid;
- the terminal's `validate_sweep_cell` then runs.

Attempt 1 retained no container inspections, so the new guard cannot be replayed on it.

| cell | sealed | new trace rule (incomplete/successful per window) | replay |
|---|---|---|---|
| 01 frontend-pause r10 | valid | pre 0/601, fault+drain 0/280, after 0/412 | **invalid: application witness does not establish the offered denominator** |
| 02 no-fault r0.05 | valid | whole 0/9 | valid |
| 03 throttle r10 | valid | pre 0/601, fault+drain 0/771, after 0/428 | valid (the guard would have flagged the 11:59:31Z restart; inferred) |
| 04 no-fault r0.2 | valid | whole 0/36 | valid |
| 05 frontend-pause r1 | valid | pre 0/61, fault+drain 0/33, after 0/41 | valid |
| 06 no-fault r1 | valid | whole 0/180 | valid |
| 07 throttle r0.2 | valid | pre 0/13, fault+drain 0/15, after 0/8 | valid |
| 08 frontend-pause r0.2 | invalid (M1) | pre 0/13, **fault+drain 1/6** (recorded), after 0/7 | **valid** |

**Cell 8 now validates.** Its one incomplete trace started 9.8 s into the drain, so it is recorded as the fault's effect.

**Cell 01 still fails, and the cause is the OOM kill.**
- 124 of 1,800 requests (scheduled 60.3–72.6 s) ended at 72.0–72.6 s with RemoteDisconnected, connection refused or reset,
  and have no access-log line.
- `application.log` shows `frontendproxy … Killed` at 11:46:59.856Z and an Envoy restart at 11:47:00.38Z.
- The kernel log names the memory cgroup.
- The target sealed the cell valid because only the terminal checks the witness. Attempt 1 would therefore have failed
  terminal validation even without the stop at cell 8.

## 5. Relaunch 1 of 2: all 12 cells, attempt 2 (approved by decision 25 and the user's option-A decision)
1. **Host (done).** Attempt 1's one-shot paths were moved aside, nothing deleted, 2026-10-03 14:38:08Z, after the archive
   check above. Command: `ssh root@fb14srv6 'bash -s' -- --archive < tmp/otel_sweep_a1_archive.sh`. The host was idle
   (0 units, 0 containers, lease free).
   - `/home/stig/observability-placement-candidate-v4-runs/otel-traffic-sweep-v1` → `.archived-otel-traffic-sweep-v1-sweep-a1-20261003T143808Z` (219 MB, 131 files)
   - `/home/stig/observability-placement-candidate-v4-runs/.setup-otel-traffic-sweep-v1` → `.archived-.setup-otel-traffic-sweep-v1-sweep-a1-20261003T143808Z` (46 MB, 8 files)
   - `/home/stig/observability-placement-candidate-v4-otel-srv6/otel-traffic-sweep-v1-6380cceffa7b` → `.archived-otel-traffic-sweep-v1-6380cceffa7b-sweep-a1-20261003T143808Z` (70 MB, 1,511 files)
2. **Local state.** The non-dry launcher archives the previous run's local gate files itself (`gate_run.py archive-run`),
   moves the plan dir aside, and renews SETUP-CAMPAIGN onto the new plan.
3. **DRY_RUN at `c532853`, attempt 2 (passed; `scratchpad/gate-drivers/otel-sweep-sweepdry5-launch.log`):** compiled
   `otel-traffic-sweep-v1 12 fa770ccf…`; drivers `otel-traffic-sweep-v1 otel-traffic-sweep-v1 3 <worktree>`; probe receipt
   PROBE OK; `host fb14srv6: running units=0 containers=0 lease holders=[] free GB=248 otel-traffic-sweep-v1 paths=0`;
   `14:38:56Z DRY RUN: all guards passed; stopping before the first mutation`.
4. **Launch** from the measurement repo:
   `LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=2 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol
   COMPILER=candidate_sweep.py EXPECTED_PLAN=fa770ccf62f3eca24081d0c9ca004c05104250da69ee3422bcf8a172b5349498 RUN_COUNT=12
   CAMPAIGN=otel-traffic-sweep-v1 LOG_PREFIX=otel-sweep nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh
   sweep2 c5328531b94e6321fbf27ab1d263448754dda76e > scratchpad/gate-drivers/otel-sweep2.out 2>&1 &`
   and `nohup uv run python tools/wandb_campaign.py follow otel-sweep2 scratchpad/gate-drivers/otel-sweep-sweep2-launch.log
   > scratchpad/gate-drivers/otel-sweep2-wandb.out 2>&1 &`.
5. **Check the lead cell (frontend-pause r10) as soon as it seals.** In `container-health.json`: valid, frontendproxy memory
   268435456, restartCount 0. In the access log: 1800/1800 tokens. If the proxy is OOM-killed again, the cell is invalid
   and the campaign stops; option B (a shorter client timeout) is next, per the user.

Attempt 1's cells are not pooled with the relaunch's; they are retained as evidence of the stop.
