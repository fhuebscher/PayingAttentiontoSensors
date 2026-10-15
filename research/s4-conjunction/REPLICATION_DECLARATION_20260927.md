# S4 baseline replication on fresh runs: declaration (2026-09-27, before any new run launched)

Committed alone, before the Hotel run on fb14srv4 (label `r7`) and the TeaStore v1 run on fb14srv5 (label `17`) launch.
The user asked for these to run overnight on 2026-09-27; this file only fixes how their results are read. It changes neither
script, no reading and no threshold. The user can amend it before `symptoms.py` touches the new data, and not after.

## What runs

- **Hotel `r7`** on fb14srv4: `scratchpad/gate-drivers/launch_hotel.sh r7`, the unchanged Hotel #6 lineage (HEAD 31d69af,
  plan `ac60dbbc…`), postures none / sample-zero / full, regimes cost, reservation-pause, search-pause.
- **TeaStore `17`** on fb14srv5: `scratchpad/gate-drivers/launch_teastore.sh 17`, the unchanged v1 lineage (f352f8d,
  descriptor `76fb72a6`, 27 cells). v1 retains only `auth.log` and `persistence.log` and no metrics, so this run can
  replicate the TeaStore log finding only.

## How the results are computed (once each)

The scripts are `symptoms.py` (sha256 `7f33203647ce7ed6aedec53be996f0a4ee543b952474d9265b1094ccf65a6fb8`) and
`relevance.py` as committed in df1bcc3, both unchanged. The new data forms its **own bag directory**, and the two runs
are never pooled with the baseline bags or with each other.

- **Hotel:** `symptoms.py --out tmp/s4-symptoms-r7 hotel H-B <r7 run dir>`. Then `relevance.py <that bag>
  --out tmp/s4-relevance-r7`. The label `H-B` is reused only so that the unchanged code paths keyed on it run. The ledger calls this
  generation **H-B-r7**.
- **TeaStore:** `symptoms.py --out tmp/s4-symptoms-t17 teastore T-16 <#17 campaign dir>`, then `relevance.py` likewise. This is
  generation **T-17**.

## What counts as replicated (each line is read as yes / no / `—` if the run did not produce the population)

Denominators are the new run's own episode counts. The baseline (`RESULT_BASELINE.md` §1–§3) is 72 episodes per Hotel regime
pooled over three postures (24 on `full`).

| # | Baseline finding | Replicates iff, in the new run |
|---|---|---|
| R1 | `log:frontend:4ae82b46d72e` fires in every reservation-pause and no search-pause episode, FA 0 | same template id: k = n in reservation-pause, 0 in search-pause, 0 false alarms |
| R2 | No log template fires in any search-pause episode | 0 of n for every template |
| R3 | `metric:rate:cpu` separates the regimes on `full` (24/24 vs 0/24) | k = n in search-pause and 0 in reservation-pause on `full` |
| R4 | `metric:cpu:plateau_down` fires in every episode of both regimes, FA 0 | k = n in both, FA 0 |
| R5 | The paused service's own span stays `present` (`missing_expected` 0/24 for the target) | **reported, not scored**: true by construction of the window W (see amendment below) |
| R6 | TeaStore: `log:auth:6c19cf62298a` fires 9/9 persistence-crash and 0/9 auth-freeze on T-16 (FA 0 is true by construction, TBC5, so it is not a criterion) | same template id: k = n in persistence-crash. The auth-freeze 0 is reported, not scored (by construction, see amendment) |

A near miss (for example 17/18) is reported as its count, and is **not** a replication. Nothing is re-thresholded after a count is
seen. A run that aborts early is scored on the complete blocks it has; a regime with no complete block is `—`.

## Amendment A (2026-09-27, after the Fable review of df1bcc3, before `symptoms.py` read any new data)

The independent review (Fable 5.1 adversarial-review subagent, report in `REVIEW_RESULT_BASELINE_20260927.md`) showed that two
criteria are partly true by construction, so a "replication" of them would say nothing about a sensor:
- R5: W = [`startedAt`, `endedAt`] starts before the pause command and ends after recovery (`compose_pause.py:108`, `:143`), so the
  target operation keeps spans inside W and `missing_expected` cannot fire. R5 is reported, not scored.
- R6, second half: auth is the paused target in auth-freeze and emits nothing, so its template's 0 there is guaranteed. Only the
  persistence-crash half is scored.
R1–R4 stand as written. Their by-construction component is disclosed: the frontend's own error line (R1), and the paused
target's CPU (R4, which G2 already removes from the target).
Scored criteria are now R1, R2, R3, R4 and R6 (first half).

## Amendment B (2026-09-27 14:45Z, after the first r7 scoring attempt, before any R1–R4 count was computed)

**What happened.** `relevance.py` run unchanged on the r7 bags (`tmp/s4-symptoms-r7/20260927T143700Z`) stopped at its frozen
stop rule S-B. P1 compares the bags against the sprint's exact `DETECTION_RESULT` counts, which describe the baseline population:
72 episodes per regime, 24 per posture. A fresh run has 18 and 6, so P1 cannot pass on any new run. This declaration missed that.
The stopped output is kept at `tmp/s4-relevance-r7/20260927T143708Z`.

**Values seen before this amendment**, all from that P1 report and all at the aggregate level (level / metric-target /
metric-other / trace-error per posture, and the warn+ sweep):
- reservation-pause: level 6/6 per posture, warn+ 18/18;
- search-pause: level 0/6 none, 0/6 sample-zero, **2/6 full**; warn+ **2/18** (baseline 0/72); FA metric-other 2/18 in each regime.

The search-pause warn+ 2/18 bears on R2, so R2 is **no longer a blind test** and is reported with that disclosure. No
per-template, per-sensor or per-symptom count (R1, R3, R4, R6) had been computed.

**Change.** `relevance.py --replication` reports P1 without gating on it. Every other line of the script is unchanged. The
default run still stops on S-B, and a new test (`test_replication_flag_reports_p1_but_does_not_stop`) is shown failing against
the unpatched script. The r7 and T-17 scoring uses `--replication`.

## Scope

Instance. Same host, workload and fault catalogue as the baseline. A replication here says the finding recurs on a fresh run of
the same system. It does not say the finding holds on another host or another system, or under the Epoch U postures.

## Addendum C (2026-09-28 09:20Z, after r8 terminal, before `symptoms.py` read any r8 file)

**Hotel `r8`** (fb14srv4, `hotel-v1-20260928t062728z-28ce4896`, same lineage and plan as r7; terminal 09:12:55Z, `candidateCampaignValid: true`,
54/54 valid, 3,266/3,266 files byte-verified in `tmp/hotel8-evidence/`) is scored as generation **H-B-r8**, exactly as r7: R1–R4 as written,
R5 reported not scored (Amendment A), same scripts (`symptoms.py` sha `7f332036…`, `relevance.py` at bff5bba), same flags
(`symptoms.py --out tmp/s4-symptoms-r8 hotel H-B tmp/hotel8-evidence/x`; `relevance.py <bags> --replication --out tmp/s4-relevance-r8`),
never pooled with the baseline, r7, or each other. What is already known and so not blind for r8: r7's result, including R2's miss
(`dff1c3922d14`, 2/18, `full` only). No r8 value has been seen; this was written before the run was opened beyond the terminal and
cleanup verdict files.
