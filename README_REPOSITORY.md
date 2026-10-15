# Goal-Conditioned Observability Placement

This repository discovers heterogeneous upstream instrumentation, reconciles
logical telemetry with realizable activation units, compiles operational goals
into evidence requirements, and validates deployable telemetry configurations
under measured constraints.

The systems under test are pinned Git submodules under `upstream/`. Research
integration belongs in `modules/`; upstream source is not copied or silently
modified.

## Current maturity

- Repository separation, pinned submodules, activation contracts, lifecycle
  receipts, evidence hashing, module ledgers, and local MLflow indexing are
  implemented and tested.
- TeaStore has two five-block none/selected/full performance campaigns. They
  are candidate evidence for same-host trace-record count, serialized
  trace-artifact size, and successful-request mean-latency ordering, not a
  cross-SUT cost result; p95 ordering did not replicate consistently.
- OpenTelemetry Demo has an older three-block lifecycle campaign and a newer
  source-bound srv5 control smoke. The latter proves images, target SDK/Envoy
  posture, fault/recovery, and teardown, but not complete source-work removal
  or cost.
- Hotel Reservation has a corrected five-block full/sample-zero functional
  smoke with bound fault/recovery, path evidence, and teardown. Sampling zero
  suppresses emission; it is not source-off or cost evidence.
- Online Boutique Compose has a one-block, three-posture functional smoke for
  the product-catalog fault subpath. It proves source/image binding, required
  subpath retention in selected/full, outage/recovery, and clean project
  teardown from a clean framework identity. Its single block, bounded claim
  projection, and causal exporter self-telemetry prohibit volume, latency,
  cost, candidate, or canonical claims. The LGTM/kind module is a deployment-channel variant of
  the same application family; its source-bound v9 run completed full,
  selected, and target-off postures at functional-smoke level. Background
  telemetry remains explicitly allowed in target-off, and no cost effect is
  claimed.

These are five modules across four application families. A module being
runnable does not make its evidence canonical; see
`docs/UPDATED_RESEARCH_SCOPE.md` and the readiness ledger for claim boundaries.

## Repository principles

1. Validation precedes empirical claims.
2. Logical signals and physical activation units are separate objects.
3. Implementation cost, runtime cost, and goal loss are separate dimensions.
4. Every experiment pins source commits, images, configuration, workload, and
   artifact windows.
5. Missing evidence yields an explicit abstention.

## Local validation and comparison

The project uses Python 3.13 through `uv`:

```bash
uv sync --group dev --group tracking
uv run pytest -q
```

Every SUT-specific line is classified in its module extension ledger. Audit a
module with:

```bash
uv run python -m obsplacement.module_audit modules/teastore
```

MLflow is an optional local index; filesystem evidence remains authoritative.
See `docs/LOCAL_MLFLOW.md`. The common objective adapter preserves missing
values and does not equate collector log size with emitted bytes or sampled CPU
percentages with application CPU-seconds.

## Repository learning tour

The dependency-free local quest starts with a short repository map, the
goal-to-evidence flow, a review of the parallel implementation/adversarial-eval
strategy, TeaStore-to-framework migration status, and the current outstanding
work. It then offers 125 source-linked multiple-choice questions, including an
eight-section science re-entry curriculum and a 30-question ordered migration
and retrospective tour.

From this repository root:

```bash
python3 -m http.server 8000 --bind 127.0.0.1
```

Open
`http://127.0.0.1:8000/learning/observability-placement-quest/` and choose
**Start context tour**. The longer study guide and Mermaid diagrams are in
`learning/observability-placement-quest/REPOSITORY_GUIDE.md`; the ensemble's
ported/rewritten/retained/open matrix is in
`research/TEASTORE_MIGRATION_AND_SHIFT_AUDIT_20260812.md`.
