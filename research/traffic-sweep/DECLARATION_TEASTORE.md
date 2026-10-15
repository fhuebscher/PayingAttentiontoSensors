# Traffic-sweep initial test on TeaStore: declaration (FROZEN 2026-10-03, committed alone, before any cell)

Adapted from the frozen Hotel declaration (`DECLARATION.md`, campaign `hotel-v1-20261003t050738z-29661565`). Budget and
stop rule: `BUDGET_REPLICATION.md` (d655feb, committed alone). Harness change: `HARNESS_CHANGE_TEASTORE.md`. Every mapping
choice (marked with a triangle in `DECLARATION_TEASTORE_DRAFT.md`) was accepted by the user on 2026-10-03 ("accept all,
Q3 17 s"; `research/PROTOCOL_DRAFT_20261002.md` decision 23). Scope of every number: **instance** (one
SUT, one host, one episode per cell).

## Binding
| item | value |
|---|---|
| harness | worktree `observability-placement-runtime-teastore-protocol`, branch `teastore-protocol-20261002`, commits `9e75010` (epoch), `761c95a` (frozen-only test skips), `9181964` (raw-bytes log capture), `59634c5` (Q3 drain allowance, declaration path), `396009a` (skip list), **activation `9a4ea56`** (selector `modules/teastore/execution/study-epoch.json`) on base `c1724b1` |
| epoch | `teastore-traffic-sweep-v1` |
| descriptor | `pipelines/campaigns/teastore-traffic-sweep-v1.json`, canonical sha256 `e808c2bb8db1c8456a11aadbb63a36dfaacda482ff563ea4e23c997d1be920b6` |
| plan | canonical sha256 `5212f18c8159e6ed400362a8ffaef517db6246598881ce85a7faa3aa7e185601`, 12 cells, identical under `/usr/bin/python3 -I` (3.9.6) and `uv run` (3.13) |
| host | fb14srv5 only (TeaStore's lineage-bound host); run window 3 h (derived) |
| analysis | `research/detection-time/` extended for TeaStore before the first cell is looked at (Hotel's rule) |

## Question
As Hotel: whether, and at which request rate, sensors that read a service's own state detect a fault sooner than the
request ledger (the root), and what that does to placement. This is an **initial test** of the replication (shakedown,
not confirmatory, 1 episode per cell): it establishes that the sweep runs on TeaStore and what a cell looks like.

## Design
- **Route and unit.** `POST /tools.descartes.teastore.webui/loginAction` (urllib follows the 302 to `/`, exactly as
  the frozen journey's login step), one request per **login journey**. The TeaStore harness drives journeys, so the
  unit is *login journeys per second*; with a one-step journey that equals requests per second, but each request is
  the login plus the redirected home page (webui → auth → persistence; the home page also reads persistence and the
  image service). Workload id `login-only-v1` (the frozen login-browse journey is unchanged).
- Rates **10, 1, 0.2, 0.05 /s** (Hotel's); measurement **180 s**; offered = rate × 180 (1800, 180, 36, 9).
- Client timeout **15 s** per request: `workload/fixed_load.py`'s `--timeout` default; the frozen cell runner passes
  none. Hotel's is 1 s. With 15 s, a full outage at 10/s keeps up to 150 requests in flight.
- Concurrency **240** = ceil(1.6 × 10/s × 15 s), Hotel's margin ratio (16 workers for 10/s × 1 s). TeaStore's frozen
  value is 8, which would stall the open loop at ~0.5 starts/s during a pause (8 workers × 1/15 s) and fail the
  plan-derived "during" floor by construction at 10/s.
- Warm-up **30 s at 10/s for every rate** (Hotel decision), same route and timeout, untokenised; ledger validated, not
  scored.
- Fault onset **60 s + a seeded offset** inside one inter-arrival (Hotel's `onset_phase_offset`, copied; with one episode
  the stratum is the whole inter-arrival); hold **60 s**. Compiled onsets: see `HARNESS_CHANGE_TEASTORE.md` §4.
- Regimes:
  - no-fault calibration (pseudo window at the same seeded onset). It reuses the frozen harness's **no-fault-cost**
    code path, so the docker-stats performance probe (`resources.json`) runs in these cells and not in fault cells
    (the frozen asymmetry; the cgroup system probe runs in every cell).
  - **pause**: `auth-freeze-effect` = `docker compose pause auth` (the frozen auth-freeze fault; Hotel paused
    `search`). Auth is on the login path.
  - **CPU throttle**: `persistence-cpu-throttle-effect` = `docker update --cpus 0.1 <persistence>` (Hotel: `profile`
    at 0.1). Persistence is on the login path and is not the pause target. Reverted with `docker update --cpus <docker
    info NCPU>`: `--cpus 0` is a no-op (Hotel LMT finding), so "revert to the original value" is implemented as
    "original unset (0) → quota lifted to every host CPU"; the pre-state must be 0 or that value.
  - **network delay: omitted.** netem needs root in the target's network namespace; fb14srv5 gives the execution user
    (stig, docker group) no passwordless sudo, and a docker sidecar sharing the namespace needs an image with `tc`
    that is not provisioned or digest-pinned on srv5. Recorded in the descriptor (`design.omittedRegimes`).
- Posture `full` only.
- **1 block**: one cell per (regime, rate) = **12 cells**. Lead cell `auth-freeze-effect` at 10/s first; the other 11
  in a seeded Fisher-Yates order (seed 20261003, Hotel's draw encoding).
- Stamps: onset stamped **immediately before** the fault command (F1), revert issued/returned stamped; the hold is timed
  from the first post-command state sample. Readiness after the revert is the frozen `GET /webui/status` loop; every
  one of those requests is **stamped in the receipt** (`sweep.probes`) so the analysis can exclude it. The adapter does
  not probe the login route during the fault (state checks are `docker inspect`).
- Logs: `docker compose logs --timestamps --no-color` of **every** service retained as `application.log` (the frozen
  design kept only the bounded auth/persistence logs, which stay unchanged). A secret scan of it is recorded, not
  blocking.
- Sampling: cgroup-v2 system samples every 5 s (37 per cell) as in the sys lineage; Kieker spool and traces as frozen.

## Outcomes
As Hotel (primary: time to detection per sensor and for the ledger; secondary: impact before detection; exploratory D3-D5),
with one episode per (fault, rate) every number is a single observation (instance), never averaged.

## Predictions
Hotel's P1-P4 are stated for 4 episodes; with 1 episode they are **descriptive checks**, not tests. P1 needs TeaStore's
timeout: the ledger's time to detection under the pause ≈ wait to the first scheduled login at or after onset + 15 s
(the client timeout), unless webui answers earlier with an error.

## Gates and declared limits
- Blocking per cell (vendored `protocol_gates.py`): **F1** (fault cells), **G1**, **G2**, **G4**; R2.recovery recorded;
  P0, R1, R2 not evaluated (no harness inputs), G4 ledger-only, as Hotel.
- The frozen validator's own checks all still run, with plan-derived numbers: e.g. **zero failures in no-fault cells**
  and **zero before/after failures in fault cells** (TeaStore's frozen effect-context rule, stricter than G2's 5 %), the
  plan-derived actual-start floor per phase (`max(1, ceil(0.5 × scheduled slots))`, replacing the frozen ≥ 20), witness
  and native-token correlation for every scored journey.
- **Drain allowance (user decision Q3, 2026-10-03)**: in fault cells, a journey that starts in [readiness, readiness +
  client timeout + 2 s) = 17 s and fails is excluded from the zero-failure rule and from the scored set, and is recorded
  (`candidate-validation.json`). No-fault cells have no allowance; a pre-onset failure is never excused. The post-hold
  window left for scoring shrinks by up to 17 s.
- The runtime stops on the first invalid cell (frozen controller behaviour).

## Resolved at freeze, and declared limits
1. All mapping choices above accepted (route/unit, timeout 15 s, concurrency 240, pause on auth, throttle on persistence
   at 0.1 reverted to NCPU, net delay omitted, no-fault-cost path reused, all-service log retention, lead cell).
2. The sys lineage's cgroup probe (c1724b1) has **never run on srv5** (`research/teastore-sys/PORT_LOG.md`, step 0
   open); if srv5's container scopes are not where it looks, every cell blocks. The launcher's sweep guard logs
   `docker info` cgroup driver/version (dry-run result in `HARNESS_CHANGE_TEASTORE.md` §7).
3. A 60 s auth pause at 10/s with 150 requests in flight has never run on TeaStore (frozen: 0.15 journeys/s, 150 s); the
   lead cell exists to show it early. Kieker at 10/s (~10x the frozen message rate) is untested too.
4. Q3 resolved: the 17 s drain allowance above (implemented in `59634c5`, 7 tests, one failing on `9181964`). Items 2
   and 3 stay declared limits: the lead cell shows them first.
