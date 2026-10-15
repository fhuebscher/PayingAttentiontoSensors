# OTel load pilot p1: result (2026-10-12; criterion 983c8c3, output 174ed52; wording not independently reviewed)

Scope: instance (OTel on fb14srv6). Declaration `b76dbe7`, harness `7b20ec4`, plan `aea94eb9`. Launched 03:52Z, host
terminal 04:33Z (attempted 6, valid 6, not stopped); fetched `tmp/otel-load-pilot-evidence/p1-fetch` (107/107
byte-verified); offline terminal replay `pass`, 6/6 (`terminal-replay-p1.json`), so every cell is valid under S1.

## Verdict (declared criterion): does not manifest at 50 req/s, does not manifest at 100 req/s
| rate | cell | server ratio (pre -> hold median) | client ratio (pre -> hold median) |
|---|---|---|---|
| 50 | throttle b01 | 1.02 (0.13 -> 0.13 ms) | 0.85 (2.04 -> 1.74 ms) |
| 50 | throttle b02 | 1.01 (0.13 -> 0.14 ms) | 0.91 (2.04 -> 1.86 ms) |
| 50 | no-fault | 0.99 | 0.88 |
| 100 | throttle b01 | 0.99 (0.12 -> 0.11 ms) | 0.99 (1.59 -> 1.58 ms) |
| 100 | throttle b02 | 0.99 (0.12 -> 0.11 ms) | 0.95 (1.66 -> 1.58 ms) |
| 100 | no-fault | 1.00 | 0.96 |
About 3000 (r50) and 6000 (r100) spans per segment. Per amendment 1, campaign D is not launched.

## Context (exploratory, `resources.json`, whole cell, ~186 s)
- productcatalogservice CPU: 8.4-8.6 CPU-s at r50, 15.3-15.5 CPU-s at r100, about 0.08 core on average at 100 req/s,
  below the 0.1-core cap (about 0.85 ms CPU per request here, against the 1.07 ms extrapolated from 0.05-10 req/s).
  So the cap still does not bind at 100 req/s; by this rate it would near 120 req/s and clearly by 200.
- frontend CPU: 61-62 CPU-s at r50, 97-98 CPU-s at r100 (about 0.53 core), 0-1 failed requests of 18,000: the
  frontend was not saturated at 100 req/s; the 10 ms/request estimate from r10 overstated its cost (about 5.4 ms here).
