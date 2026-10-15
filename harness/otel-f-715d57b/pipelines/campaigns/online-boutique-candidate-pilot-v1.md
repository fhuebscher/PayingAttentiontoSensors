# Online Boutique candidate pilot v1 — construction protocol

This local construction protocol freezes an 18-cell design: three randomized complete
`none/selected/full` blocks in a strictly no-fault cost regime and three
independently allocated complete blocks in a `productcatalogservice`
pause-effect regime. Each run has one immutable attempt identity. Cost and
effect artifacts have disjoint roots and may not be pooled.

Every run offers 150 requests over 150 seconds at 1 request/second. The effect
regime plans fault onset at 50 seconds and release after another 50 seconds,
giving exact nominal `pre/during/post-readiness` start counts of `50/50/50`.
The retained floor is 40 actual starts per phase, so each nominal phase has ten
starts of predeclared slack. Phase intervals are half-open. Controller
ground-truth probes are retained separately and count toward neither the
offered ledger nor phase minima or outcomes. Requests between fault release and
observed homepage readiness are an unscored `recovery-gap`; that delay consumes
post-readiness slack and invalidates the cell if the actual-start floor is lost.

Offered-request truth comes from a future append-only ledger planned before
telemetry. Fault truth requires container state plus functional manifestation
and recovery. Path truth requires a one-to-one pre-outcome request token and
one original trace. The predecessor workload lacks that token, so correlation
is explicitly `unsupported`, not zero or failure. The held-out currency effect
remains an explicit null abstention.

The construction API only compiles, validates, materializes, and hash-chain
replays deterministic fixture digests. It accepts no executor or callback,
creates no compiler-owned artifact root, and cannot invoke Compose, Docker,
SSH, workload, fault, or acquisition code. The compiler's `artifactRoot` is the
one physical identity; a pre-existing root stops simulation before any fixture.
A clean local validation is therefore labelled
`construction-pass-runtime-blocked`; it is not runtime readiness, candidate
evidence, or canonical evidence.

Repository routing and adoption are external to this protocol. Its neutral
`integrationBoundary: local-construction-only` label states only that these
bytes construct and validate a local plan. It neither predicts nor blocks a
repository-level route. A separate human runtime-plan decision and fresh
runtime gate remain mandatory. Runtime also requires request/trace correlation
and runtime readiness; neither is implemented here.
