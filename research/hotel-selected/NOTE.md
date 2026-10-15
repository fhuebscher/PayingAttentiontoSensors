# Hotel `selected`: offline evidence on lmt2 (2026-09-29), before any code

Scope: instance (lmt2, fb14srv4, 4 blocks). In-sample: everything here is read from the campaign a `selected` would be tested against,
so it is a candidate, not a result.

1. **Journey-services selected = full** at the GET /hotels workload (`journey_equals_full.py`, output `journey_equals_full.lmt2.txt`):
   attractions, recommendation, review, user emit 0 spans in 20/20 `full` cells; their metrics->full CPU delta is -0.012..-0.005 CPU-s
   per block against +8.61..+8.75 for the six journey services. A campaign contrasting the two would measure an empty step.
2. **Frontend-only candidate** (from `out/post_hoc.lmt2.json`, T family, non-target, before G3): frontend spans catch search-pause 4/4,
   reservation-pause 4/4, net-delay 4/4, cpu-throttle 0/4, the same as all spans; 0 no-fault firings. Frontend is 94,499 of 351,325
   spans (26.9 %). Cost: `—` (not measured; downstream tracers would be NoopTracer, frontend's client spans stay).

Open (user, preregistration): what `selected` is (frontend-only goal-derived, another set, or a wider workload so full > journey).
Harness work either way: per-service `HR_JAEGER_DISABLED`/`HR_JAEGER_SAMPLE_RATIO` (`candidate_cell.py:335-338`, check at `:404-405`),
a fifth posture, and the 4-posture guards (80 cells, Latin square rung count).
