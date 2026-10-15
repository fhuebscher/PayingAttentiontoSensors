# Hotel Reservation adapter

This module binds the pinned DeathStarBench `hotelReservation` subtree to the
executor-neutral lifecycle without copying application source into the
framework. `materialize.py` exports the exact clean Git object, retains its
original Compose file, and generates a separately hashed smoke deployment with
global container names removed and only configurable loopback ports. Its proof
records the upstream tree, untouched source-content hash, transformation list,
generated Compose hash, and final materialization hash.

The first qualified scenario is `GET /hotels`. Its audited call path is:

```text
frontend -> search -> geo
                   -> rate
frontend -> reservation (CheckAvailability)
frontend -> profile
```

The stock control is deliberately named `sample-zero`, not `none` or
`source-off`. `JAEGER_SAMPLE_RATIO=0` suppresses root trace sampling while the
application still constructs HTTP middleware, gRPC client/server interceptors,
and manual spans. All logical observations on the path are therefore coupled by
one root sampling decision. A request-path cost claim requires a subsequent
audited service-level source guard; it cannot be inferred from this scaffold.

Local qualification starts with:

```bash
uv run python modules/hotel-reservation/materialize.py
uv run python modules/hotel-reservation/execution/campaign.py \
  --source-proof .local/hotel-reservation/.obsplacement-materialized \
  --framework-commit "$(git rev-parse HEAD)" \
  --output .local/evidence/hotel-reservation-plan/schedule.json
```

`execution/campaign.py` only validates and freezes a schedule. The separate
`execution/smoke.py` runner executes the isolated Compose lifecycle and now
recomputes the materialized source proof, builds one source-bound application
image, verifies image/posture identity, makes fault recovery exception-safe,
joins intervention work before teardown, and records a final project-hygiene
receipt.

The retained `hotel-smoke-srv4-20260808` run is a smoke validation only: both
20-request postures completed, full retained the declared search path and
proved pause/recovery, and `sample-zero` retained no spans. It predates the
hardened runner, lacks an immutable schedule, used a shared host with foreign
workloads, and therefore remains generically quarantined and scientifically
smoke-only.

Current blockers before a candidate campaign:

- rerun the hardened runner from a clean framework checkout and retain its
  complete schedule/evidence manifest;
- resolve every remaining third-party Compose image to an immutable digest;
- add a service-level source guard before treating `sample-zero` as a cost
  baseline;
- run randomized independent blocks and campaign-level paired diagnostics;
- keep actual Jaeger operation names bound to retained raw responses before
  promoting any new ground truth.
