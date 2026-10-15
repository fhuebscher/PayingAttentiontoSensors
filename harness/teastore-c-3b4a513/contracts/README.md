# Contracts

Versioned schemas for logical sensors, activation groups, goals, scenarios,
campaigns, evidence, and validation reports belong here. Contracts must remain
independent of Docker Compose, Kubernetes, Dagger, and telemetry backends.

`signal-channel.schema.json` separates a semantic signal from its transport
and acquisition carrier. `signal-target.schema.json` defines the independent
posture-specific target state. Adapters must not relabel collector stdout as
application logs or infer a missing semantic channel from a filename. Shared
schemas leave transport names, collector details, and posture keys project-owned;
each adapter supplies and hashes its stricter supported contract and evaluator.

`control-universe.schema.json` freezes a family-specific activation catalogue and
its Phase 1 microtests in backend-neutral terms. `control-observation.schema.json`
records terminal evidence across the declared, enabled, emitted, transported,
and retained stages. Goal sufficiency remains outside Phase 1. Unsupported controls require explicit
abstentions. The generic evaluator in `obsplacement.control_universe` can establish
only a structural control map (Phi); missing evidence falls back to descriptive
claims. Empirical promotion requires a module adapter's semantic validator and
the curated readiness gate, and even that cannot imply optimization or
cross-family equivalence. Callers must provide an `evidence_verifier(item)` that
resolves each locator and checks its SHA-256 digest; omitting it, or returning
anything other than `True`, keeps the result descriptive-only.
Every stage binds its semantic unit, identity namespace and policy, denominator,
target population, and measurement point. A transition across incompatible
bindings is `not-comparable`, never a numeric reduction or amplification.

The next-phase design contracts deliberately keep four additional objects
separate:

- `probe-design.schema.json` binds placement locus, native signal semantics,
  mechanism/version, setting domain, dependencies, lifecycle, and control
  purity. Similar logical evidence produced by different mechanisms is not the
  same probe design.
- `context-regime.schema.json` distinguishes deployment/acquisition context
  from workload, fault, load, interference, and held-out regime. Contexts are
  pooled only after their compatibility and matching gates pass.
- `knowledge-policy.schema.json` defines what K0--K4 may know, when information
  is revealed, and which policies may select candidates. A method contract with
  unresolved budget or implementation digests is not a preregistration.
- `optimization-goal.schema.json` freezes required evidence and objective
  semantics without claiming that structural selection yields retained evidence
  or diagnostic utility.

`finite-configuration-space.schema.json` binds the small Boolean catalogs used
by `obsplacement.configuration_oracle`. Its exactness is exhaustive structural
enumeration only. The diminishing-returns diagnostics search the complete
enumerated catalog-admissible domain for finite counterexamples; they are classification
hooks, not a theorem about noisy runtime outcomes or an approximation guarantee.
The compatibility field `feasibleConfigurationCount` retains its legacy name,
but means only the count of catalog-admissible structural assignments. Neither
the field nor the oracle proves operational deployability.

`science-change-control.schema.json` is the machine-readable science-control
supplement for the canonical OpenSpec lifecycle. Its version 1 governance
manifest binds a full base commit, exact authority paths and SHA-256 digests,
path ownership, human checkpoints, and registered typed checks. It
structurally forbids runtime, external mutation, held-out outcome access, AI
selection, evidence promotion, approval bindings, and passed verification.
These permissions cannot be granted by changing prose, marking OpenSpec tasks
complete, or archiving a change; a future operation needs a different,
separately reviewed and human-bound authorization contract.

The trusted registry contains exactly `openspec-config`, `openspec-tool-pin`,
`change-artifacts`, `governance-schema`, `authority-bindings`,
`path-ownership`, `findings-ledger`, and `runtime-boundary`. Agent-authored
Markdown and free-form shell commands are not executable claims. Authority
digest drift fails closed and requires semantic review; a validator must never
refresh it mechanically.

Run the supplement with:

```bash
command -p python3 -I tools/run_openspec.py science-validate
```

The overall result and every check use `pass`, `fail`, or `cannot_run`. Process
exit codes are 0, 2, and 3 respectively. `cannot_run` means a fixed external
verifier such as OpenSpec or Git could not execute; a missing or malformed
declaration is `fail`. Green establishes repository-local governance
consistency only. `runtimeAuthorized` and `promotionEligible` remain false, and
no empirical claim is promoted.

The former `aidlc-work-unit.schema.json`, `aidlc/units/` packages, validator,
and focused tests belonged to the historical bootstrap and are retired in this
change. Git history preserves them for audit. Their useful planning and
science-safety semantics have moved into the OpenSpec `scientific-change`
schema and this science-control supplement; they must not be restored as a
parallel live lifecycle.
