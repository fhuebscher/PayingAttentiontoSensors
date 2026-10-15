# S4 replication on Hotel r7: result (2026-09-27, scored once)

**Rules.** `REPLICATION_DECLARATION_20260927.md` (978cbf4, Amendment A 582066b, Amendment B bff5bba).
**Run.** Hotel `r7`, fb14srv4, `hotel-v1-20260927t114506z-9a428b0c`, unchanged Hotel #6 lineage (HEAD 31d69af). Terminal
14:30Z: `candidateCampaignValid: true`, 54/54 cells valid. The host has 3,266 files, and all 3,266 matched the host
sha256 manifest after fetch (`tmp/hotel7-evidence/verify-full.txt`).
**Computation.** Symptom bags: `symptoms.py` (sha `7f332036…`, unchanged) → `tmp/s4-symptoms-r7/20260927T143700Z`.
Scoring: `relevance.py --replication` → `tmp/s4-relevance-r7/20260927T144032Z` (`tables.md`, `relevance.json`); stdout in
`tmp/s4-relevance-r7-stdout-B.txt`.
**Denominators.** Per regime: 18 episodes pooled over three postures, 6 of them on `full`; false alarms over 18 no-fault pseudo rows (6 on `full`).
**Scope.** Instance: one host, one run, same workload and fault catalogue as the baseline.

| # | Criterion | Baseline | r7 | Verdict |
|---|---|---|---|---|
| R1 | `log:frontend:4ae82b46d72e` fires in every reservation-pause episode, no search-pause episode, FA 0 | 72/72, 0/72, FA 0/72 | 18/18, 0/18, FA 0/18 | **replicated** |
| R2 | no log template fires in any search-pause episode | 0/72 for all 162 templates | `log:frontend:dff1c3922d14` 2/18 (both on `full`: 2/6; none and sample-zero 0/6) | **not replicated**, not blind (Amendment B) |
| R3 | `metric:rate:cpu` on `full`: every search-pause, no reservation-pause episode | 24/24, 0/24, FA 0/24 | 6/6, 0/6, FA 0/6 (pooled 18/18, 0/18, FA 0/18) | **replicated** |
| R4 | `metric:cpu:plateau_down` fires in every episode of both regimes, FA 0 | 72/72 both, FA 0/72 | 18/18 both, FA 0/18 | **replicated** |
| R5 | target `missing_expected` stays silent (reported, not scored: true by construction of W) | 0/24, 0/24 | 0/6, 0/6 | — |

**R2 in plain words.** The new template is the frontend's `services/frontend/server.go:285 > SearchHandler GetProfiles failed`
(ERR, zerolog). It appears in `search-pause/b01/p03-full` and `search-pause/b04/p02-full`. In those two cells a request's
profile call failed while search was paused, and the frontend logged it on a different line from the reservation path's
`server.go:271`. The span table agrees: `span:/profile.Profile/GetProfiles:error` fires 2/6 in search-pause on `full`. So "search-pause
leaves no log trace" is a property of most runs, not of the fault. The log family catches search-pause rarely, through a
downstream call, and in this run only under `full`. Two cells cannot tell whether that is posture-related.

**What this says for the multi-modal direction** (instance scope, one fresh run). The reservation-pause log sensor and both
metric findings recur exactly on unseen data. The claim that failed is the absolute one ("never"). The trace-derived
R(p) on `full` again gives distinct sets per episode with none shared across the two regimes (D-P4 held: 8 distinct sets, 12
episodes).

## TeaStore 17 (fb14srv5): aborted, partial

The campaign aborted at 14:53Z on its first blocked cell (`auth-freeze-effect/b02/full`, `RuntimeError: TeaStore readiness failed`,
the known readiness class: 2/291 srv5 cells and 1/9 srv6 before this, mechanism unestablished). It kept 12 cells: 3 complete
no-fault-cost blocks and auth-freeze b01. It reached no persistence-crash cell, so **R6 is `—`**. Evidence: `tmp/teastore17-evidence/x`,
278/278 files byte-verified against the host manifest.

The no-fault blocks were run through `research/host-rotation/evaluate_amendment3.py`, unchanged; output in
`tmp/teastore17-evidence/amendment3-rules.txt`:
- rule 1 holds: none→selected is +54,900 records in 3/3 blocks, and selected→full is +47,423, +47,387 and +47,348;
- rule 2 holds: p50 none→selected is +73.27, +65.14 and +63.78 ms;
- rule 3 holds: peak memory none→selected is +1.399, +3.270 and +2.145 GB.

Scope: instance, srv5, one more campaign of the same lineage. This is not a host replication.
A rerun is campaign 18 on the same lineage. The classifier blocked Claude's launch, so it was handed to the user.

## Hotel r8 (fb14srv4): scored once under Addendum C (e4920ad)

**Run.** `hotel-v1-20260928t062728z-28ce4896`, same lineage as r7 (HEAD 31d69af). Terminal 09:12:55Z: `candidateCampaignValid: true`,
54/54 valid, verdict pass. 3,266/3,266 files match the host sha256 manifest (`tmp/hotel8-evidence/verify-full.txt`).
**Computation.** `symptoms.py` (sha `7f332036…`) → `tmp/s4-symptoms-r8/20260928T092121Z`; `relevance.py --replication` →
`tmp/s4-relevance-r8/20260928T092123Z` (`tables.md`); stdout `tmp/s4-relevance-r8-stdout.txt`. 18 episodes per regime, 6 on `full`.

| # | r8 | Verdict |
|---|---|---|
| R1 | `log:frontend:4ae82b46d72e` 18/18 reservation-pause, 0/18 search-pause, FA 0/18 (6/6 per posture) | **replicated** |
| R2 | `log:*` 0/18 in search-pause (every template) | **replicated** (blind for r8; r7's miss was known) |
| R3 | `metric:rate:cpu` on `full` 6/6 search-pause, 0/6 reservation-pause, FA 0/6 (pooled 18/18, 0/18) | **replicated** |
| R4 | `metric:cpu:plateau_down` 18/18 both regimes, FA 0/18 | **replicated** |
| R5 | target `missing_expected` 0/6, 0/6 (reported, not scored) | — |

The profile-call line from r7's R2 miss (`log:frontend:dff1c3922d14`, `server.go:285`) fired once in r8, in a **reservation-pause** episode
on `full` (1/6), and in no search-pause episode. Search-pause episodes with any template, per generation, never pooled: H-B 0/72, H-Bp
1/18, r7 2/18, r8 0/18. Scope: instance.
