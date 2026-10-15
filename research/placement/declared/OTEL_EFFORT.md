# OTel sensor effort inventory (instance)

Scope: **instance** (one SUT, one harness epoch, one readout vocabulary). Machine-readable record: `research/placement/declared/otel.effort.json`. Generated 2026-10-12 by an inline `uv run python -I -` script (nothing saved to disk). Not committed. Not independently reviewed.

## Denominator

- Ids: **1705** = union of `calibration.primary.perRate[*].sensors` keys (1705) and placement `arms.primary[*].groundSet` ids (1554). 151 are in calibration keys only; 0 in ground sets only.
- span/log/metric ids: **1704** (spans 74, logs 1286, metrics 344). Ledger ids: **1** (`ledger:frontendproxy:/api/products/66VCHSJNUP`, a harness client-side field, not an emitter; tier `—`).
- Sources: `research/traffic-sweep/readout-otel-primary-v3.1/sweep_analysis_v3.json`, `research/placement/out/otel-primary/placement.json`.

## Counts

effortTier, denominator 1705: tier 0 = **1587**; tier 1 = **117**; tier 2 = **0**; `—` = **1** (ledger).

| family | ids | tier 0 | tier 1 | tier 2 | `—` |
|---|---|---|---|---|---|
| span | 74 | 74 | 0 | 0 | 0 |
| metric | 344 | 344 | 0 | 0 | 0 |
| log | 1286 | 1169 | 117 | 0 | 0 |
| ledger | 1 | 0 | 0 | 0 | 1 |

ootb, denominator 1705: true **1587** (all tier-0 ids); false **1** (ledger); null **117** (frontendproxy logs, R-WITNESS, unknown whether upstream or harness).

Observation channel (separate from emission): **418** span and metric ids (of 418) are read from the collector debug exporter, which the harness sets to `verbosity: detailed` (`materialize.py:697`, runtime worktree). Upstream sets no verbosity (`upstream/opentelemetry-demo/src/otelcollector/otelcol-config.yml:92`). Emission tier is unchanged by this.

runtimeCostShare: **null for all 1705 ids**. Only posture-step CPU exists (see Cost).

## Rules applied (per family and service)

Instrumentation rows: `../observability-placement-runtime-otel-protocol/modules/otel-demo/postures/catalog.json` `serviceInstrumentation` (identical in the v3 catalog; checked by script). Each sensor's `sourceLine` in the JSON gives its service's row.

- **R-SPAN-UP** (tier 0, ootb true, 74 ids). Span from one of the 19 application services. Each has an upstream load site with no harness code change: catalog rows (e.g. frontend at catalog.json:323) and `research/system-profiles/otel.md:55` ("Every app service is instrumented with no code change"). Harness source guards only disable existing registrations (`materialize.py:369`).
- **R-METRIC-OTLP** (tier 0, ootb true, 313 ids). Same evidence for OTLP metric points.
- **R-SPANMETRICS** (tier 0, ootb true, 31 ids). Metric names `calls` and `duration~*`. Upstream spanmetrics connector: `upstream/opentelemetry-demo/src/otelcollector/otelcol-config.yml:120`, in the traces pipeline exporters at `:127`.
- **R-LOG-STDOUT** (tier 0, ootb true, 1169 ids). Log ids are hashes of upstream stdout lines (`research/placement/declared/README.md:30`). Not controlled by `OTEL_*_EXPORTER`; services run in every posture.
- **R-WITNESS** (tier 1, ootb null, 117 ids). frontendproxy log lines that may come from the harness-added Envoy stdout access log (`materialize.py:652`). Upstream `upstream/opentelemetry-demo/src/frontendproxy/envoy.tmpl.yaml` has no `access_log` (checked by the script; tracing block at `:18`). A template config change, not service code. Upper bound: the hash cannot separate witness lines from upstream Envoy lines.
- **L-LEDGER** (tier `—`, 1 id). Harness client ledger field.
- **R-CODE-PATCH** (tier 2, 0 ids). No id needs a harness patch that adds telemetry. The source guards (`materialize.py:369` onward) wrap existing registrations: `OTEL_PLACEMENT_ENABLED` gates in the cart, checkout, currency, product catalog and shipping sources. The recommendation logging block replacement (`materialize.py`, around lines 619-640) keeps the upstream LoggerProvider when enabled. Checked by reading the replacement text, not by a source diff.

Collector changes: `docker_stats` is removed by the harness (`materialize.py:691`), and collector-internal metrics (hostmetrics, httpcheck, redis, prometheus self-scrape) are not in the union, so none are classified.

## Posture membership (catalog conflict)

- **v3 catalog** (`tmp/otel-v2-admission/modules/otel-demo/postures/catalog.json`, postures at lines 46/51/64/85): selected = frontend, frontendproxy, recommendationservice; async = 7 services. Matches the v3 cells and `research/system-profiles/otel.md:§5`. Used for `postures`.
- **Current runtime catalog** (`../observability-placement-runtime-otel-protocol/.../catalog.json`, postures at lines 45-140): selected = 11 services; async = 14. Used for `postureCurrentCatalog`. The existing `research/placement/declared/otel.json` (commit 8db0f00) is built from this one.

183 ids differ between the two. By service: checkoutservice 41, cartservice 39, productcatalogservice 29, recommendationservice 21, flagd 14, paymentservice 13, quoteservice 12, emailservice 5, shippingservice 5, currencyservice 4. Which catalog the comparator should use is the user's decision; this file does not choose.

Log ids are listed in all four postures, since stdout survives every posture (`declared/README.md:30`; `otel.json` families.log). Instrumentation-originated log lines may vanish under none and selected (undetermined below).

## Cost (posture level only)

Source: `research/otel-postures/RESULT.md:22-27` (paired steps, mean of 3 blocks; instance, one host, n=3). Share = step delta / none-level CPU (about 90.4 ms per offered request, RESULT.md:27). The denominator is my derivation.

| step | CPU delta, ms | share of none-level | bin |
|---|---|---|---|
| none -> selected | +15.40 | 17.0 % | >10 % |
| selected -> async | +5.27 | 5.8 % | 1-10 % |
| async -> full | +5.41 | 6.0 % | 1-10 % |
| none -> full | +26.08 | 28.9 % | >10 % |

These are step totals over service groups, not per-sensor costs. The research tree has no per-sensor CPU measurement that I found. Per-sensor `runtimeCostShare` stays `null`. Bins apply to a step, not to one sensor.

## Could not be determined (`—`)

1. Per-sensor runtime cost: all 1705 ids.
2. Split of the 117 frontendproxy log ids into upstream Envoy lines and harness witness lines (hash only).
3. Instrumentation-originated log lines (javaagent banners, .NET shim, SDK startup) under none and selected: not separable from the id (`otel.json` undetermined list).
4. Observation channel for log ids: not traced to a config in this pass.
5. Per-service split of the async step beyond RESULT.md:38 (cited, not re-derived).
6. Collector-internal metric names (hostmetrics, httpcheck, otelcol self-scrape): not in the union, so not counted (`?`).
7. Loadgenerator: the harness runs it headless in every cell (`research/system-profiles/otel.md:§9`); upstream starts it with the UI (`upstream/opentelemetry-demo/.env:96-97`). Emission capability is the same; its runtime footprint is not in tier terms.

## Commands run

- `uv run python -I -c` inspections of the readout JSON (`calibration`, `perSensor`, `provenance`, `frameworkCommit`) and `placement.json` (`arms.primary`, `groundSet`, `costs`, `costLabels`).
- `/usr/bin/grep` on `research/system-profiles/otel.md`, `research/placement/declared/README.md`, `research/otel-postures/RESULT.md`, the upstream `otelcol-config.yml`, and the runtime `materialize.py`.
- `git -C <repo> show 6936347:modules/otel-demo/postures/catalog.json`: not an OTel commit (TeaStore), so not used. `8f9ab09` (v3 epoch): selected = 3 services.
- `uv run python -I -` (heredoc, nothing on disk): union, rules, line lookups, exclusive write of `otel.effort.json` (refuses if it exists).
- `uv run python -I -` (heredoc): this file, exclusive create.
