# OTel off-path manifestation pilot v2: result (2026-10-13)

Scope: **instance** (OTel demo 1.12.0 on fb14srv6, one cell per (fault, rate), n = 1 per pair). A verdict is about that cell,
not about a rate or a mechanism.

- Declaration: `research/traffic-sweep/DECLARATION_PILOT_OFFPATH_V2_OTEL.md` (`36b0813`), budget `BUDGET_E.md` amendment 1
  (`d4e8e52`), criteria script `research/placement/manifestation_offpath_pilot.py` (`ef94c6d`).
- Run: harness `ff29b93`, plan `a929b4d9…`, launched 2026-10-12 11:52:54Z, terminal 12:42:08Z (host `remote-terminal.json`
  mtime, host clock CEST), 8 attempted / 8 valid, not stopped.
- Fetch: `tmp/otel-offpath-pilot-v2-evidence/p1-fetch`, 147/147 files byte-verified against the host sha256 manifest.
- Offline terminal replay at `ff29b93` against the pilot's own gates and plan: verdict `pass`, 8/8 valid
  (`terminal-replay-v2.json`). Criteria applied once with `--terminal-valid`; output `manifestation-v2.json`, committed
  unedited before it was read (`537a406`).

## Verdicts

| fault | 25 req/s | 50 req/s |
|---|---|---|
| frontend pause (on-path control) | manifests | manifests |
| frauddetectionservice pause (off-path) | manifests | manifests |
| accountingservice pause (off-path) | manifests | manifests |
| productcatalog throttle | — (no cell: dropped by decision 108) | — |

Kept for E: frontend pause, fraud pause, accounting pause. E rate by the declared rule (lowest rate at which every kept
fault manifests): **25 req/s**.

## The numbers behind them (from `manifestation-v2.json`)

Consumer spans (`Kind=Consumer`, target service) started in pre-onset 60 s → hold 60 s, and `route=checkout` ledger rows
scheduled in the hold (ok / rows):

| cell | accountingservice | frauddetectionservice | checkout ok |
|---|---|---|---|
| no-fault 25 | 88 → 90 | 176 → 179 | 89 / 89 |
| accounting pause 25 | **87 → 0** | 174 → 178 | 89 / 89 |
| fraud pause 25 | 89 → 88 | **178 → 0** | 88 / 88 |
| frontend pause 25 | 88 → 1 | 176 → 2 | 9 / 89 |
| no-fault 50 | 176 → 176 | 352 → 352 | 176 / 176 |
| fraud pause 50 | 176 → 177 | **352 → 2** | 177 / 177 |
| accounting pause 50 | **176 → 0** | 352 → 354 | 177 / 177 |
| frontend pause 50 | 178 → 1 | 356 → 2 | 7 / 176 |

Frontend pause, first 45 s of the hold: all routes 4 / 1125 ok (25 req/s) and 9 / 2250 (50); checkout by send time 1 / 65
and 0 / 129. No-fault preconditions pass at both rates (every row ok).

What this says: pausing either Kafka consumer stops that consumer's spans while every checkout in the hold still succeeds,
so the request ledger alone does not see these two faults in these cells. The consumer collapse is near-true by construction
(a frozen process emits nothing, as the declaration says); the informative parts are that each consumer produced spans
before the pause, the other consumer kept going, and checkout stayed at 100 % ok. What it does not say: anything about
detection time, other rates, or a second host.

Witness cross-check (declaration N3, reported, not part of any verdict): 0 ledger rows without a witness row in every cell;
status disagreements and non-`-` response flags occur only in the frontend-pause cells (e.g. 25 req/s: add-to-cart 4
disagreements, 256 flagged rows), consistent with requests cut by the pause.

## Deadline note

BUDGET_E amendment 1 set "terminal and fetched 2026-10-12 15:30Z". Terminal was met (12:42Z); the fetch was not (done
2026-10-13 ~01:25Z) because the coordinator's VPN was down from ~12:57Z. Stop rule 1 (no extension without the user)
applies to that step: whether these verdicts may set E is the user's decision, recorded in the protocol when made.
