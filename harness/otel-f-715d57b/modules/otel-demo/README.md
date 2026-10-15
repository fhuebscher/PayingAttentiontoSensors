# OpenTelemetry Demo adapter

Pinned to the 1.12.0 experiment version. Activation groups span agents,
libraries, SDKs, services, routers, and manual source spans.

Materialize a clean working copy (the pinned submodule is never edited):

```bash
uv run python modules/otel-demo/materialize.py
```

The generated `.local/otel-demo` copy contains explicit Node/browser guards
and both Envoy tracing configurations. Run Compose from that directory with
`OTEL_PLACEMENT_ENABLED=true` for full source instrumentation or
`OTEL_PLACEMENT_ENABLED=false OTEL_PLACEMENT_DISABLED=true` for the posture
whose legacy identifier is `source-off`. Set `DEMO_VERSION=1.12.0`; never
inherit upstream `latest`.

That identifier currently means **SDK-and-proxy disabled on the target path**,
not zero instrumentation work. The frontend may still invoke no-op OTel APIs
and non-target services remain enabled (the recommendation process now starts
through a posture-conditional entrypoint and no longer loads
`opentelemetry-instrument` when disabled). Receipts therefore label these runs
`noncanonical-control-smoke`; they cannot support request-path cost claims.
They can be imported into MLflow without promotion.

## Per-service instrumentation controls (candidate postures)

`postures/catalog.json` (schema 2) classifies every application service by the
mechanism that loads its instrumentation and by the load state the disabled
posture reaches (`not-loaded`, `loaded-silenced`, `loaded-exporting`), each with
the upstream load site and the SDK source that was read to decide it.
`materialize.py` is the single render source for every disabled control
(`ENTRYPOINT_GUARDS`, `AGENT_ENVIRONMENT`, `FLAGD_*_ENVIRONMENT`,
`render_imageprovider_no_otel_template`, `SOURCE_PLACEMENT_GUARDS`);
`deployment/compose.candidate-postures.yml` wires them per posture, and
`execution/candidate_runtime.py` declares the expected values independently,
executes every guarded launch under `/bin/sh` against stubbed programs, and
checks the pinned upstream Dockerfiles, `.env`, and nginx template before a
plan is accepted. The runtime posture proof (schema 2) records, per service,
the expected and observed control (`docker inspect` env, `/proc/1/environ`,
`docker top` argv, or a rendered config file), a posture-config digest shared
with the terminal validator, and the loaded-service set that the terminal
checks for strict nesting none < selected < full.

| disabled load state | services | blocks the posture? |
|---|---|---|
| `not-loaded` | accountingservice, adservice, cartservice, checkoutservice, currencyservice, frauddetectionservice, frontend, frontendproxy, imageprovider, kafka, paymentservice, productcatalogservice, quoteservice, recommendationservice, shippingservice | no |
| `loaded-silenced` | emailservice (OTEL_TRACES_EXPORTER=none), flagd (empty collector URI / metrics exporter), flagd-ui and loadgenerator (SDK honours OTEL_SDK_DISABLED) | no — emits nothing; carried as the named `claimBoundary` (D13) |
| `loaded-exporting` | (none) | yes — the only blocking state |

`loaded-silenced` is **not** a claim that the instrumentation is absent. Those
four services still load and still cost; see "What `none` means here" below.

cartservice (.NET), checkoutservice and productcatalogservice (Go),
currencyservice (C++), and shippingservice (Rust) construct their OTel SDK
pipeline directly in application code, whose pinned versions honour neither
`OTEL_SDK_DISABLED` nor `OTEL_*_EXPORTER=none`; `SOURCE_PLACEMENT_GUARDS`
patches the exact call site (never the pinned checkout in place) so the
disabled branch never constructs the exporter/provider at all, and
`candidate_setup.install` now builds a local image for each of the five so the
patched source, not the pulled ghcr image, is what runs. The proof for these
five is text-only against the pinned upstream checkout
(`prove_materialized_source_guards`) -- unlike the entrypoint guards, there is
no `/bin/sh` indirection to execute a compiled-language conditional, so
whether the patched source still compiles is unverified until a local image
is actually built.

### What `none` means here (decision D13, user, 2026-09-06)

`none` means **no telemetry emitted**, not **no instrumentation loaded**. Those
are different measurements and the choice between them was a governance
decision, not a mechanical catalog edit; the user took the "emitted" reading.

The proof rule encodes it: `proofRule.disabledLoadStateRequired` is
`not-exporting` (both `not-loaded` and `loaded-silenced` satisfy it),
`proofRule.noneSemantics` is `no-telemetry-emitted`, and
`proofRule.loadedButSilencedIsClaimBoundaryNotBlocker` is `true`. With the five
`loaded-exporting` blockers closed by the source guards,
`postureRealization.none` and `.selected` therefore read `implemented`:
`blockingServices` is empty, and `blockingServices` is the only list that gates
the status. `zeroStartupApplicationSignalsRequiredForNone` stays `true` — the
`none` posture must still be observed emitting nothing.

**The claim boundary is named, not hidden.** emailservice, flagd, flagd-ui and
loadgenerator are still `loaded-silenced`: their instrumentation is compiled or
imported into the process and still costs, it just exports nothing. Every
realization row therefore carries `disabledSetSemantics:
"no-telemetry-emitted"` plus `claimBoundary:
"loaded-but-silenced-instrumentation-still-runs-and-still-costs"`, and lists
those four under `silencedButLoadedServices` — a list kept strictly separate
from `notLoadedServices`, so a reader of the proof cannot mistake this posture
for "not loaded". A cost claim from these postures is a claim about *emitted*
telemetry, and the residual instrumentation work of those four services sits
inside the baseline. Removing that boundary needs four more source guards, in
Ruby, Go and Python, each run through the connection probe.

The refusal has **not** lifted, and D13 did not lift it.
`candidate_runtime.refuse_unsupported` derives it from the frozen v1
descriptor, whose `postureRealization` is byte-pinned at
`daffe1ca…`(`candidate_pilot.EXPECTED_DESCRIPTOR_SHA256`) and still says
`unsupported` for none and selected. Admitting them is a **new study epoch** —
a new descriptor, a new control schema parent `changeId`, and a governed edit
of `ADMITTED_STUDY_EPOCHS` in `candidate_setup.py` and `candidate_remote.py`,
which are both still `()`. The catalog realization is *necessary* for a
descriptor to claim a posture, so a descriptor that claimed one the per-service
table cannot realize is still a gate failure; the reverse — catalog realizes,
descriptor does not — is exactly today's state and means "awaiting an epoch".

Run resumable, randomized source-off/full blocks from the materialized tree:

```bash
uv run python modules/otel-demo/execution/campaign.py \
  --output .local/evidence/otel-campaign-srv6 --blocks 3
```

Set a fresh, run-scoped Compose project before every invocation, for example
`OBSPLACEMENT_COMPOSE_PROJECT=obsplacement-otel-20260809a`. The runner refuses
to start without a safe project name and refuses to tear down a project that
already contained resources at its ownership preflight.

Each run pauses and restores the frontend during the measurement window. The
receipt retains the runtime source-posture proof, per-request timings, fault
manifestation and recovery, collector output volume, and trace-export lines.

Retained pre-hardening artifacts are immutable and still contain embedded
`candidate-evidence` labels (and one directory name containing `canonical`).
Those strings describe the old runner's self-assessment, not the reviewed
scientific status. `research/five-module-readiness.json` is the controlling
curated ceiling: every retained OTel campaign is currently smoke validation
only, and MLflow schema 4 records that digest-bound ceiling separately.

## Candidate v4 disposition: UNSUPPORTED

The 18-cell design remains frozen exactly as reviewed: `none/selected/full` in
randomized repeated blocks, separate no-fault cost and frontend-pause effect
windows, and explicit fault/path ground truth.  The srv6 allocation file is
also retained byte-for-byte as provenance.  Neither document grants runtime
authority.

The frozen descriptor says that `none` is not structurally realized by the
legacy source-off control and that no audited `selected` closure exists.  Its
comparative unit is a complete `(regime, block)` containing all three
postures.  Consequently every block—and therefore all 18 empirical slots—is
`UNSUPPORTED`.  The six individually implementable `full` cells may not be
run or reinterpreted as a different experiment.

[`execution/candidate-unsupported.json`](execution/candidate-unsupported.json)
is the machine-readable disposition and exact cell ledger.  It binds the
frozen descriptor and reviewed target-allocation bytes, records zero external
attempts and null numeric results for all 18 run identities, sets all gates to
`not-requested`, and denies setup, readiness, launch, status/fetch, cell
mutation, and external mutation.  The runtime derives that denial from the
descriptor's `postureRealization` cross-checked against the catalog's
per-service realization; the target setup and target controllers admit no
study epoch (`ADMITTED_STUDY_EPOCHS = ()`) and refuse before staging files or
invoking an external command.  The disposition validator is
[`validation/candidate_unsupported.py`](validation/candidate_unsupported.py)
(`CONTROLLER_PATHS["unsupported-disposition"]`), which emits the same 18-row
`UNSUPPORTED` result.  The route-bound terminal validator is
[`validation/candidate_terminal.py`](validation/candidate_terminal.py): it
refuses through the same descriptor-driven check today, and once a study
epoch realizes all three postures it replays every retained cell (workload
identity, per-phase correlation, posture proof v2, nested lattice, host
release) and can emit at most `candidate-evidence`.

The v4 root registry must therefore project this child as
`executionDisposition: unsupported`, `empiricalResultState: UNSUPPORTED`, all
three gates unavailable and `not-requested`, and the standard unavailable
target contract (`host: null`, no users, paths, ports, lease, or projection
bindings).  That root-level authority projection is intentionally different
from retaining the historical srv6 allocation bytes inside this payload for
audit provenance.
