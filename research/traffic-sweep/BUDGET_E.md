# Budget and stop rule: OTel off-path campaign E (multi-path workload, off-path faults, effort-tiered cost), 2026-10-12

Committed alone, before any E work. Authority: user, 2026-10-12, after the load pilot (`e131856`): off-path faults
"would significantly improve our results and are worth going for", OTel only, with Sonnet 5.5 and Haiku 5.5 workers.
Roadmap origin: direction (c) of 2026-10-01 (`research/NEXT_STEPS_20260925.md:482-484`; fraud-pause built, never run,
`research/system-profiles/otel.md:109`). Campaign C's FAIL and the pilot result stay reported as they are. Scope of every
number: instance (OTel on fb14srv6). Paper deadline: BenchSOC / ASOCA, 2026-10-15 23:59 AoE = **2026-10-16 11:59Z**.

## User decisions (2026-10-12)
1. **Workload:** the upstream Locust task mix as an open loop with one ledger row per request
   (`research/load-generator/DESIGN.md`: products, cart, recommendations, ads, view-cart, checkout, checkout_multi), so
   checkout reaches Kafka and its consumers accountingservice and frauddetectionservice (protocol §9).
2. **Faults:** frauddetectionservice pause and accountingservice pause (off-path, asynchronous Kafka consumers),
   frontend pause (on-path control), productcatalogservice 0.1-core CPU throttle at a rate where it binds.
3. **Cost model:** implementation-effort tiers per sensor (0 = emitted by the upstream system as shipped; 1 =
   configuration only; 2 = code change), plus runtime-cost tiers (CPU overhead < 1 %, 1-10 %, > 10 %); the starting
   point is the out-of-the-box (upstream default) posture.

## Sequence and deadlines (UTC)
1. Harness epoch (workload + faults, tests with a planted defect per change, activation) and the effort/runtime-tier
   inventory: **2026-10-13 06:00Z**. Independent review GO, declaration of the manifestation pilot committed alone,
   DRY_RUN passed: **2026-10-13 10:00Z**.
2. **Manifestation pilot** (two total rates, one cell per fault per rate plus a no-fault cell, criteria per fault declared
   before launch; off-path: consumer-side activity collapses during the hold while checkout requests keep succeeding):
   terminal and fetched **2026-10-13 16:00Z**. A fault that does not manifest is dropped from E.
3. **Analysis v3.2** (reader admits the new epochs and the multi-route ledger; placement budget axes for effort tier and
   runtime tier), tests with planted defects, review, digest freeze **before any E cell is read**: **2026-10-14 06:00Z**.
4. **Campaign E** at the rate(s) chosen from the pilot, training blocks and test blocks in one declaration (split fixed
   before launch), committed alone with a DRY_RUN: launch by **2026-10-13 22:00Z**; terminal and fetched
   **2026-10-14 12:00Z**. At most 1 relaunch, harness or infrastructure defects only.
5. Placement solved on the training blocks, frozen with the pass rule; test blocks scored once; readouts and scores
   committed unedited before reading: **2026-10-14 20:00Z**. Paper text from then; submission by 2026-10-16 11:59Z.

## Stop rules
1. A missed deadline stops that step; the paper then reports C's FAIL, both manifestation results and the cost frontier
   from existing data (option A). No extension without the user.
2. 30 minutes per critical-path defect; 3 critical-path harness defects stop E.
3. Launch only from a declaration committed alone plus a passing DRY_RUN, mirrored to wandb; one campaign per host.
4. No E cell is read (validity fields only) before v3.2, the training placement and the pass rule are frozen.
5. If no off-path fault manifests in the pilot, E is not launched.

## Amendment 1 (user, 2026-10-12 ~11:00Z, committed alone before the second pilot's work)
The off-path pilot (declaration `64854c2`, harness `8c53cb2`, 100/150 req/s) stopped at cell 2 of 10: cell 1 (no-fault,
100 req/s) valid; cell 2 (frauddetectionservice pause, 100 req/s) invalid because productcatalogservice was OOM-killed at
its upstream 20 MiB limit (kernel memcg OOM, 2026-10-12 09:50:16Z; Docker restarted it; the health guard invalidated the
cell). Fetched `tmp/otel-offpath-pilot-evidence/p1-fetch` (40/40 byte-verified). Both off-path faults undecided (`—`).
- **Second pilot:** a new epoch (`otel-offpath-pilot-v2`, so no host path collides), the upstream mix at **25 and 50 req/s**,
  SUT memory limits upstream (otelcol and jaeger 1G as decision 103), regimes: no-fault, frauddetectionservice pause,
  accountingservice pause, frontend pause (on-path control). **The productcatalog throttle is dropped from the pilot and
  from E** (it does not take effect below ~120 req/s, and at 100 req/s of the mix productcatalogservice already exceeds its
  20 MiB limit). Criteria as in `64854c2` with its review fixes, minus the throttle row.
- Deadlines: harness ready, review, declaration committed alone, DRY_RUN: **2026-10-12 13:30Z**; terminal and fetched
  **15:30Z**. E's deadlines (step 4 launch by 22:00Z, terminal 2026-10-14 12:00Z) are unchanged. At most 1 relaunch,
  harness or infrastructure defects only.

## Amendment 2 (user, 2026-10-13 ~02:00Z, committed alone before E's declaration)
Pilot v2 (declaration `36b0813`, harness `ff29b93`, plan `a929b4d9`) reached terminal on time (2026-10-12 12:42Z, 8 attempted /
8 valid) but missed amendment 1's "fetched by 15:30Z": the coordinator's VPN was down from ~12:57Z; fetched 2026-10-13 ~01:25Z,
147/147 byte-verified, offline replay pass 8/8 (`537a406`). **The user extended that step (stop rule 1) and accepted the pilot's
verdicts for E** (`research/placement/pilot-offpath/RESULT_V2.md`): every pause manifests at 25 and 50 req/s, so E keeps
fraud-pause, accounting-pause and frontend-pause at **25 req/s** (the declared E-rate rule, not vetoed). E's deadlines are
unchanged: launch by **2026-10-13 22:00Z**, terminal and fetched **2026-10-14 12:00Z**; at most 1 relaunch, harness or
infrastructure defects only.
