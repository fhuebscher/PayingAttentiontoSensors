# OTel campaign F (detection lanes: own silence, coordinator, consumer-group lag; 5 blocks, 1-3 training / 4-5 test): declaration (2026-10-14)

**Status: declaration, committed alone before launch** (BUDGET_F stop rule 3), after an independent review (see "Review"). Scope of every number:
**instance** (OTel Demo 1.12.0 at 2d4661e, fb14srv6). *Generator* numbers come from the compiler, not the host; unknown values are `?`.
Authority: user, 2026-10-13: "Yes, full F" (plan `research/PLAN_LANES_20261014.md`, `c2914de`; budget `BUDGET_F.md`, `db3be09`); pass rule "E's rule + lane
predictions"; decision 73 "keep fill; zero-alarm row post hoc". Stop rule 4 holds: no F cell is read (validity fields only) before reader v3.3, the
training placement and the pass rule are frozen by digest.

## What F is
Campaign E's design (`DECLARATION_E_OTEL.md`, `49e47a1` with amendments `c785354`, `ef64d3b`): upstream Locust mix as an open loop, one ledger row per
request, 25 req/s, 60 s pauses of frauddetectionservice and accountingservice (off-path Kafka consumers) and of the frontend (on-path control), posture
`full`, collector log sampler off, split blocks 1-3 training / 4-5 test, train-only calibration (decision 102). Epoch `otel-offpath-f-v1`, compiler
`modules/otel-demo/execution/candidate_offpath_f.py`, descriptor `pipelines/campaigns/otel-offpath-f-v1.json` in the harness worktree
(`observability-placement-runtime-otel-protocol`; commits `936aedd`, `a5f1a36`, `9fc8fef`, `26aa624`, `94a9fd1` on E's launch commit `6a5c2a9`;
E recorded spent `e58580a`; activated `48d44d5` (run by the user from a coordinator-written script after the permission system denied the builder),
governance re-pin `e17d34f`, test fix `715d57b` = the launch commit). Changes from E, nothing else:
1. **Metric export 5 s:** `OTEL_METRIC_EXPORT_INTERVAL=5000` rendered into the materialized posture overlay for F only (18 services). Honoured, from
   SDK source and demo code (not observed): Java agent (adservice, frauddetectionservice, kafka), PHP (quoteservice), Go (checkoutservice,
   productcatalogservice), Python (recommendationservice, loadgenerator), .NET (cartservice). Not honoured: flagd (2 s, hard-coded), frontend and
   paymentservice (Node, 60 s), currencyservice (C++, 60 s). Unverified: accountingservice (.NET auto-instrumentation), flagd-ui. No metrics SDK:
   shippingservice, emailservice, imageprovider, frontendproxy. The launcher's DRY_RUN exits before any mutation (no stack, no collector), so the observed
   cadence is first read from cell 1's `otelcol.log` timestamps after the fetch, before any reading of results; F's cost and telemetry bytes are not
   pooled with E's (the cadence is partial).
2. **spanmetrics** `metrics_flush_interval: 5s`.
3. **Consumer-group lag:** the collector's `kafkametrics` receiver (brokers `kafka:9092`, scrapers `[consumers]`, 5 s; in contrib 0.108.0 per the
   release manifest `distributions/otelcol-contrib/manifest.yaml` at tag v0.108.0), a `resource/kafka` processor upserting `service.name=kafka`
   (the adapter drops resources without it), a `metrics/kafka` pipeline to the debug exporter; otelcol waits for kafka `service_healthy`.
4. **Two no-fault cells per block** (regime `no-fault-calibration`, run-key field `replicate`), so 25 cells: per block 2 no-fault (seeded order), the
   off-path pauses (seeded), the frontend pause last. Seed 20261014. Training no-fault time doubles to about 0.30 h (T_r), so the zero-alarm price is
   2.996/T_r ~ 10/h and the 6/T_r budget ~ 20/h (computed by the reader; these are expectations).
- Descriptor `6164052dc62c323be37c286afd0f41a90808bbd251f62d56eb959eec01233b7e`, plan (attempt 1) `30aa2484fa1aa42c0f9bedbc3b98123dd8a3290a417237d0bb07fb93ae28b5bd`,
  25 cells (*generator*, identical under 3.9 and 3.13). Expected about 2 h 20 min of cells from E's 336 s/cell plus install; harness budget 511 s/cell,
  GATE-RUN window 5 h.

## The pass rule (unchanged from E: decisions 99-102, 110-112)
- **Verdict:** for each off-path class (fraud-pause-effect, accounting-pause-effect) separately, the frozen set `frontier (effort<=any, runtime<=any) @6/T_r`
  (registry `V32_PASS_RULE`, inherited by v3.3) passes iff g = D(ledger alone) - D(S) > 0 over that class's test episodes and it improves at least 2 of them
  (strictly); `—` with fewer than 2 valid test episodes or a set member absent from the scoring ground set. Own-sensor exclusion (decisions 84/111) and the
  recurrence rule (decision 112) stay.
- **Decision 73 stays as frozen** (user, 2026-10-13): a sensor never evaluated in a training no-fault fold pays the rate's largest evidenced upper bound.
  Reported beside it, **post hoc and without a verdict:** the same frontier with every id that has zero records in every training no-fault cell priced at
  the zero-alarm bound 2.996/T_r.
- **Stated before launch, from E:** the Kafka group-coordinator log ids never occur in no-fault time, so under decision 73 they again pay the fill price
  and are not expected in the @6/T_r set; in E, fraud block 5's ledger fired at 20.2 s, before the coordinator lane, so a class can fail on strict improvement
  even with a coordinator sensor. Lag metrics that are present in no-fault time are evaluated normally and can be priced near 2.996/T_r if quiet.

## Lane predictions (stated before launch; scored hit/miss on the 4 off-path test episodes, blocks 4-5; reader v3.3 `lanes` block)
| id | lane | prediction | basis |
|---|---|---|---|
| F-L1 | own silence (target's own sensors; reported in the by-construction field, excluded from placement) | fires < 2.0 s after the pause command in 4/4 | E: 10/10 at 0.88-1.55 s |
| F-L2 | coordinator (log ids of service `kafka`) | earliest counted fire 42-47 s in 4/4; no fire in the 2 frontend test episodes | E: 43.4-44.3 s in 10/10; clients' default 45 s session timeout, not overridden (`Consumer.cs:75-82`, `main.kt:38-47`); library defaults read from docs, jars not checked |
| F-L3 | lag (`kafka.consumer_group.lag*` of service `kafka`) | armed (>= 20 pooled training points) and fires before F-L2's fire in >= 3/4 | none measured; expectation from the receiver's 5 s scrape of the paused group's committed offsets; `—` if not armed or not collected |
| F-M | metric arming | >= 1 non-flagd metric id is placeable at 25 req/s, counted separately for SDK metrics and spanmetrics-derived metrics (the latter can arm by construction from traces) | E: 0 (pooled n 3-18 < 20 at 60 s export) |
A miss of a prediction is reported as a miss. No prediction changes the verdict.

## The analysis chain (measurement repo; frozen by digest before any F cell is read)
1. Reader `research/detection-time/sweep_analysis_v3_3.py` + registry `research/protocol/parameters_v3_3.json` (layers on the frozen v3.2; admits F with E's
   regimes; lanes block with counted and by-construction fields). Training readout `--blocks 1 2 3`; scoring readout `--test-blocks 4 5`; `--split
   research/protocol/split_f_otel.json` (`{train: [1, 2, 3], test: [4, 5]}`).
2. Placement `research/placement/celf_v3_3.py <training readout> --tiers research/placement/declared/otel.effort.json --tier-catalog postureCurrentCatalog --split <split> --out <new file>`.
3. Scorer `research/placement/score_test_v3_3.py <scoring readout> --placement <frozen placement> --training-readout <training readout> --test-blocks 4 5 --out <new file>`.
Pins (`PINNED_V33_SHA256`, `PINNED_PARAMETERS_V33_SHA256`, then `PINNED_PLACEMENTS["otel"]` for F) are set at the freeze, recorded in a freeze record.

## Evidence handling
Fetch read-only after the terminal into a new directory, byte-verified against the host manifest: case `otelF1` in `scratchpad/gate-drivers/fetch_overnight.sh`
(`H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs; ID=otel-offpath-f-v1; O=tmp/otel-f-evidence/f1-fetch`). Offline terminal replay before any
scoring. Evidence stays out of git.

## Launch (worktree HEAD = the activation commit; DRY_RUN first; one campaign per host, check fb14srv6 itself)
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
git -C ../observability-placement-runtime-otel-protocol rev-parse HEAD        # must equal 715d57b5f06ea32d47466acccae927da8e350a2c
DRY_RUN=1 OTEL_CANDIDATE_ATTEMPT=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_offpath_f.py EXPECTED_PLAN=30aa2484fa1aa42c0f9bedbc3b98123dd8a3290a417237d0bb07fb93ae28b5bd \
  RUN_COUNT=25 CAMPAIGN=otel-offpath-f-v1 LOG_PREFIX=otel-offpath-f-v1 \
  zsh scratchpad/gate-drivers/launch_otel_offpath.sh f1dry 715d57b5f06ea32d47466acccae927da8e350a2c > scratchpad/gate-drivers/otel-offpath-f-v1-f1dry.out 2>&1
LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_offpath_f.py EXPECTED_PLAN=30aa2484fa1aa42c0f9bedbc3b98123dd8a3290a417237d0bb07fb93ae28b5bd \
  RUN_COUNT=25 CAMPAIGN=otel-offpath-f-v1 LOG_PREFIX=otel-offpath-f-v1 \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh f1 715d57b5f06ea32d47466acccae927da8e350a2c > scratchpad/gate-drivers/otel-offpath-f-v1-f1.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow otel-offpath-f-v1-f1 scratchpad/gate-drivers/otel-offpath-f-v1-f1-launch.log \
  > scratchpad/gate-drivers/otel-offpath-f-v1-f1-wandb.out 2>&1 &
```
At most 1 relaunch (attempt 2), harness or infrastructure defects only.

Worktree suite at `715d57b`: 29 failed / 2441 passed / 145 skipped / 1 collection error (mlflow), the failure set identical to `6a5c2a9`'s. DRY_RUN `f1dry` passed 2026-10-14 00:03:20Z at `715d57b` (all guards; srv6: 0 units, 0 containers, no lease, 234 GB free, 0 F paths).

## Risks the build cannot settle without running
E's risks 1-8 apply unchanged. New: (a) collector log volume: E's cell `r25-b01-01-full` wrote 87.3 MB of `otelcol.log` (metrics 13.6 MB, mostly hostmetrics and
flagd, unchanged in F) and 62.9 MB of pcap, E 2.9 GB over 20 cells; the SDK and spanmetrics share is under ~2 MB per cell, so F is estimated at 100-130 MB per cell,
~4 GB in total (estimate, not measured; disk guard 40 GB, srv6 had 234 GB free on 2026-10-13). **Deviation from BUDGET_F stop rule 5's wording:** the launcher's
DRY_RUN cannot report per-cell bytes (it starts no stack); the estimate above replaces it and the disk guard stays. (b) The kafkametrics receiver's start with the
broker not yet healthy (mitigated by `depends_on`, not observed). (c) The rendered collector config (`otelcol-placement.yml` of the F materialization) passes
`otelcol-contrib validate` of the official 0.108.0 darwin build (release checksum verified; Linux-only `root_path` removed for the darwin check; upstream's own
config passes the same way). `validate` catches structural errors (a planted unknown key fails) but not value errors (a planted bad scraper name and bad
processor action pass). The same darwin build was then started with the config (local ports, no broker): it reached "Everything is ready" with the
kafkametrics receiver built and reporting its self-metrics (2026-10-13 23:13Z); scraping a real broker and the `resource/kafka` upsert are first observed in cell 1. An empty `protocol_version` is skipped, not rejected, in 0.108.0 (`receiver.go`).
(d) A changed materialized source rebuilds the frontend, frontendproxy and recommendationservice layers during `auto` (outside the GATE-RUN window).
(e) The lag sensor is one id per (kafka, metric name), summed over both consumer groups, so it cannot tell the fraud pause from the accounting pause. (f) The two
no-fault cells of a block are siblings in leave-one-cell-out calibration, not independent blocks.

## Review
Independent same-provider review (Fable `adversarial-review`, 2026-10-13 ~23:00Z, on `94a9fd1`): **GO on the harness code**; launch blockers B1 (not activated:
closed by `48d44d5`/`e17d34f`/`715d57b`), B2 (the DRY_RUN starts no stack: the byte and cadence claims were replaced, above), B3 (no collector had loaded
the config: closed by `validate` and a local start of the official 0.108.0 build, above). Checked and held: 3.9 compile and digests, 25 unique run ids and
roots, the two no-fault replicates collide nowhere (runtime, validator, drivers, reader), posture-proof exactness with the kafka resource, compose environment
and `depends_on`, rebuild outside the window, 2.3 h expected against a 5 h window. Cross-provider judge: not run (server not connected).
