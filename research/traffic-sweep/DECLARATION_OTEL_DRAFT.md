# Traffic-sweep initial test on the OpenTelemetry Demo: declaration DRAFT (2026-10-03; not frozen, nothing run)

Hotel's frozen declaration (`DECLARATION.md`, 2026-10-03) adapted to the OTel Demo on fb14srv6. Budget and stop rule:
`BUDGET_REPLICATION.md` (committed alone before this file). Harness report: `HARNESS_CHANGE_OTEL.md`. Every **▶** is a
mapping choice of mine that the user confirms or vetoes at freeze; values without ▶ are Hotel's approved values, copied.
This is an **initial test (shakedown), not confirmatory**: one block, one episode per (regime, rate). Scope of every number:
instance (one SUT, one host).

## Binding (filled at freeze)
| item | value |
|---|---|
| harness | worktree `observability-placement-runtime-otel-protocol`, branch `otel-protocol-20261002`; epoch commit and re-pin commit: see `HARNESS_CHANGE_OTEL.md` §1; M1 commit `275492f`, activation commit `6380cce` |
| epoch | `otel-traffic-sweep-v1`, activated by the committed selector `modules/otel-demo/execution/study-epoch.json` plus the tombstone edit (`ADMITTED_STUDY_EPOCHS = ("otel-traffic-sweep-v1",)` in `candidate_setup.py` and `candidate_remote.py`) |
| descriptor | `pipelines/campaigns/otel-traffic-sweep-v1.json`, canonical sha256 `78d2f0c43533d6371048498d3525b67166e9c1b6bdfbc84d61e2db0d9785aefa` (generated from the offpath descriptor; regenerate, never hand-edit) |
| plan | attempt 1: canonical sha256 `779b908d2fb5ba815f2477c6d470fe98ca853b354d690a1663ac05980a5d4100`, 12 cells, identical under `/usr/bin/python3 -I` (3.9.6) and `uv run` (3.13) |
| host | fb14srv6 only; GATE-RUN window 3 h (derived), minimum remaining at first mutation 5,472 s (derived) |
| analysis | `research/detection-time/` extended for OTel **before any result is looked at** (not done; see open question 9) |

## Question
Hotel's, unchanged: whether, and at which request rate, sensors that read a service's own state detect a fault sooner than
the request ledger (the root), and what that does to placement. Here: does the answer replicate on a second SUT whose
telemetry is OpenTelemetry-native (traces, metrics and logs through one collector)?

## Design
- ▶ **Route**: `GET /api/products/66VCHSJNUP` through the entry point `frontendproxy` (Envoy), reaching `frontend` (Next.js)
  and **one** backend, `productcatalogservice` (gRPC GetProduct). From upstream 2d4661e code: no currency call without a
  `currencyCode`; productcatalogservice asks flagd only for product `OLJCESPC7Z` (`main.go` checkProductFailure), so any other
  product keeps flagd off the route. 66VCHSJNUP is the catalog's second product. Alternative: `OLJCESPC7Z` (the product the
  harness has always used) puts flagd on the route as a second backend.
- Rates **10, 1, 0.2, 0.05 /s**, open loop, constant spacing from the shared barrier; offered = rate × 180 (1800, 180, 36, 9).
- ▶ **Client timeout 15 s**: the harness's own per-request timeout (the offpath journey's `stepTimeoutSeconds`; Hotel's is
  1 s). Consequence: during a frontend pause every request waits up to 15 s, and Envoy's default 15 s route timeout races
  it; the ledger's time to detection at any rate is ≥ ~15 s after the first post-onset request (Hotel P1's "+ 1 s" becomes
  "+ 15 s").
- ▶ **Concurrency 300** = ceil(2 × max rate × timeout), the open-loop rule "worker cap ≥ rate × timeout" (DESIGN.md L1, which
  Hotel's 16 ≥ 10 × 1 met with a 1.6× margin). The offpath harness used 32, which would stall the generator's starts at 10/s
  during a pause (32 / 15 s ≈ 2.1 starts/s against 10 scheduled).
- **Upstream loadgenerator OFF**: removed right after `docker compose up`, before readiness, warm-up and measurement
  (`docker compose rm --stop --force loadgenerator`; `frontendproxy` has a required `depends_on: loadgenerator`, so
  `up --scale loadgenerator=0` was dropped after review as Compose-version dependent). It runs only for the seconds between
  `up` and the removal. It is **on** in every earlier OTel cell:
  `LOCUST_HEADLESS true` overrides `LOCUST_AUTOSTART false` (retained `tmp/otel-v3a2-evidence/runs/no-fault-cost/b03-03-full/otelcol.log`:
  360 loadgenerator records, "Starting Locust 2.18.2", `GET http://frontend-proxy:18080/` failing), and it asks flagd on every
  task. Absence is proven per cell by the Docker engine (`upstream-generator.json`: no container with the project's
  `loadgenerator` service label, after the removal and after the window). ▶ C_HARNESS_INFRA #10 recommended "off"; it is an
  emission change, so OTel sweep cost numbers are not poolable with v3/offpath.
- Warm-up: **30 s at 10/s for every rate**, on the same route, untokenised for scoring. Before it, the harness's own stack
  readiness (one complete checkout journey) and one route 200 (both token `readiness-not-scored`).
- Fault: onset at 60 s **+ a seeded offset uniform in one inter-arrival** (Hotel's stratified rule with one stratum, keyed by
  regime, rate and block, not by attempt); hold **60 s**.
- Regimes:
  - no-fault calibration (pseudo window at the same seeded onset);
  - ▶ **frontend-pause** (`docker compose pause frontend`; on-path, the route must be unavailable during the fault): Hotel's
    search-pause analogue; it already exists in the harness;
  - ▶ **productcatalog-cpu-throttle** (`docker update --cpus 0.1` on productcatalogservice; docker group, no sudo): Hotel's
    profile-cpu-throttle analogue on the route's backend. ▶ Revert: to the original quota when one is set; productcatalog has
    none (NanoCpus 0), and `docker update --cpus 0` is a no-op (Hotel lmt_faults.py, measured on fb14srv4 2026-09-28), so the
    quota is lifted to every host CPU (24) instead. The container is removed at the end of the cell.
  - ▶ **net-delay omitted**: no no-sudo mechanism exists in this harness. fb14srv6 grants sudo only for tcpdump; the project's
    only netem mechanism is `sudo -n nsenter … tc` (Hotel); the docker-sidecar netem of decision round 4 item 6 is not built
    and would need an image with iproute2 pinned on srv6.
- Posture `full` only; placements by restriction of `full` cells (an approximation: a sensor can behave differently when
  other sensors are off).
- ▶ **1 block**: every (regime, rate) pair once, 3 × 4 = **12 cells**, order a Fisher-Yates shuffle with SHA-256 draws from
  seed 20261003, except that **frontend-pause at 10/s is first** (lead cell: the first 60 s pause at 10/s on OTel; check its
  capture while the campaign runs).
- ▶ **Metric export interval unchanged** (SDK default, 60 s observed): changing it is an emission change this initial test does
  not make. Declared limit: metric sensors have ≤ 3 samples per 180 s window and ~1 per 60 s hold, so a metric family cannot
  beat the ledger by more than its own cadence allows, and P3's "within one sampling cadence" is 60 s for OTLP metrics.
- Sampling, unchanged from the harness: docker-engine cumulative CPU before and after the window (diagnostic only), OTLP
  bytes by tcpdump/tshark, the collector's debug exporter as the trace/metric/log carrier (`otelcol.log`), the proxy access
  log as the request witness. New: `application.log` = `docker compose logs --timestamps` of every started application
  service except the collector (Docker's RFC3339Nano receive stamp on every line).

## Outcomes
Hotel's, unchanged: **primary** time to detection per sensor and for the ledger (first catch after onset; a miss charged at
the hold end; averaged over episodes, never over detected episodes only); **secondary** impact before detection (failed
requests started before the first catch, by scheduled time); exploratory D3/D4/D5. With one episode per pair, every
outcome is a single observation per (fault, rate): descriptive only.

## Predictions (testable sets declared now; one episode, so each is a single-case check)
- **P1 (positive control, frontend-pause)**: the ledger's time to detection = wait to the first scheduled request at or after
  onset + ▶ the 15 s client timeout (or Envoy's 15 s route timeout, whichever fires first), within ±1 s. A deviation flags a
  harness or onset defect, not a finding.
- **P2 (frontend-pause, `failed` rule)**: failed requests started before the ledger's first catch ≤ 1 + rate × 15 s + 2
  (Hotel's slope form with the OTel timeout; ≈ 153, 18, 6, 3.75).
- **P3 (request-independent families)**: a sensor's time at 0.05/s ≤ its time at 10/s + one sampling cadence (docker CPU ~3 s;
  OTLP metrics 60 s). Testable set from the 10/s cells; untestable cells listed, not failed.
- **P4 (decision criterion)**: with one episode per pair the "≥ 3 of 4 paired episodes" rule cannot be applied; ▶ report per
  (fault, rate) whether the sensor's time is lower than the ledger's in the one episode, labelled descriptive.

## Analysis definitions (Hotel's, unchanged unless marked)
- Probe windows excluded from sensor scoring: the fault receipt's `probes` (phase `during-fault` and every `post-revert`
  readiness probe, exact monotonic start/end on the ledger's clock) and `[revertedMonotonic, readyAtMonotonic]`. Probe requests
  carry token `readiness-not-scored`, are never in the ledger, and their traces are not correlated to ledger rows.
- Ledger rule, stamps, leave-one-episode-out (▶ not applicable with one episode), by-construction flags, false alarms on
  no-fault windows at the same onset phase, G2 own/outside: as Hotel.

## Gates and declared limits
- Blocking per cell, **evaluated on the target before the next cell** (vendored `protocol_gates.py`, byte-identical to
  d3fc741): **F1** (fault cells), **G1**, **G2**, **G4**; replayed byte-for-byte by the terminal validator. R2.recovery recorded,
  never blocking; with onsets ≥ 60 s the revert returns after 120 s (= measurement − 60) in every fault cell, so it is
  always `—` in this design.
- Not evaluated (inputs not written): **P0**, **R1**, **R2** (as Hotel). G4's channel scope is ledger-only.
- At 0.05/s there are 3–4 requests before onset: one pre-onset failure fails G2 and stops the campaign (stop and ask).
- The campaign stops on the first invalid cell.
- ▶ Posture-probe receipt: the GATE-SETUP precondition is satisfied by the existing receipt (2026-09-23, PROBE OK, disabled 0 /
  enabled 42), which binds the probe-script bytes and the upstream pin only; both are unchanged. It was not re-run for this
  epoch.

## Monitoring (not evidence)
As Hotel: high-level progress mirrored to wandb (`tools/wandb_campaign.py`); the evidence of record is the fetched campaign
directory.
