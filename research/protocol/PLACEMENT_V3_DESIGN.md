# Placement v3: CELF on per-episode detection times (design proposal, rev. 2, 2026-10-10, not adopted, not computed)

This is the placement step deferred by decision 29. Nothing in it is adopted until the user says so. **No placement has
been computed on any readout.** This design, its digest, the D-p answers, and a budget and stop rule for the placement
work are frozen first, each committed alone, before the first placement number exists on any SUT.

The inputs are the frozen v3.1 readouts: Hotel 3d6bf3b and OTel 0a8517a. TeaStore's does not exist yet (`—`).

**Rev. 2** follows an independent Fable `adversarial-review` of rev. 1 (eec5f0d). Its scripts and outputs are in
`tmp/placement-review/`. The review found the §2 mathematics holds, verified on 300 synthetic instances. It found the
decision framing NO-GO. The counts below are structural only (sensor, cost and fire tallies; no placement, no score). I
re-ran them with `uv run python -I tmp/placement-review/data_pass{3,4}.py`, plus `jq` for the fold keys. They are
instance scope.

## Inputs: JSON paths the placement step reads (schema checked on both readouts)
- **Episodes:** `episodes[].{cell, regime, rate, block, campaignIndex, harness, target, holdSeconds, onset.mono,
  affectedPath[]}`.
  - Hotel: 48 episodes, all `sweep`, blocks 1-4.
  - OTel: 32 episodes, keyed by (harness, block, campaignIndex) as (sweep,1,0): 8, (B,1,1): 8, (B,2,1): 8, (B,3,1): 8.
- **Traffic:** `exposure.episodes["<cell>"].{requestsStartedInWindow, exposedServices[]}`, `exposure.routePath[]` and
  `exposure.neverExposedSensors[]`.
- **Detection times:** `episodes[].fires[]` holds positional arrays, sorted by ttd:
  `[family, sensorId, rule, ttd_s, dir, own, onPath, counts, bcFlags[], movedBy]`.
  - The serialiser is `episode_detail`, `sweep_analysis_v2.py:3611-3613`, reused by v3.
  - Fires come only from calibrated or exempt rules: `cr["score"]` is built at `sweep_analysis_v3.py:786-787` and used
    at `:955`.
  - T(i,s) = min `ttd_s` over the fires of `sensorId` s with `counts` = true. Whether `bcFlags` ≠ [] counts is D-p7.
  - The ledger's fires have family `E` and sensorId `ledger:<entry>:<route>`.
- **Cross-check:** `perSensor[].{regime, rate, sensor, own (bool), exposed[] (bool per episode),
  noBC.perEpisode[] (null = miss), noBC.penalisedMeanTtd}`.
  - `penalisedMeanTtd` = mean(min(t, H_i)) for A = {s} without E. The re-run confirmed this in 173/173 Hotel rows and
    95/95 OTel rows.
- **Ground set and costs:** `calibration.primary.perRate["<r>"].sensors["<sensorId>"].{family, placeable, appearOnly,
  calibrated[], dropped[], unarmed[], inert[], celfCost, honest, honestHours, honestPerHour, honestUpperPerHour,
  foldsEvaluated}`.
  - `celfCost` = `honestPerHour`. It is `null` without evidence, and for the ledger.
  - Per rate: `calibration.primary.perRate["<r>"].{hours (T_r), cells}`.
  - Per-rate summary: `.summary.{placeableWithoutCost [sensorId], appearOnly [sensorId], inert [sensorId],
    gridEdge [], sensors {family: {status: count}}, rules {}, degreesOfFreedom, foldsArmedMedian, hold}`.
  - The ≤ 1-alarm arm is `calibration.atMostOne.*`.
- **Impact:** `predictions.P2["<r>"].perEpisode[]` counts failures before E's first `failed` catch.
  `secondary[].columns["E"|…|"T:own"].perEpisode[].failedBefore` counts them before a family's first catch.
  - **Neither gives impact at an arbitrary T(i,A).** That needs each episode's failed-request schedule
    (`e["_c"]["ledger"]`), which is not serialised.
  - Gap: a read-only emitter on the frozen v3.1 loaders that writes, per episode, the sorted scheduled offsets of the
    failed requests. It computes no placement.
- **False alarms:** the reference sets are in `placementFalseAlarms.primary.{allPlaceable["<r>"], families["<r>"]["<F>"],
  sets["P4a <class> r<r>"]}.{union, sumOverSensors, perHour, upperPerHour, hours, foldsEvaluated}`.
  - A chosen set needs `placement_far(sids, cr, share, "nested")` (`sweep_analysis_v3.py:1074`) run on the cells.
  - Fresh check: `validation.perRate["<r>"].{allPlaceable, sets, hours, freshLimitZeroPerHour}` and `bFreshCheckLimit`.

## 1. Scenarios
- **Unit:** an episode i = (SUT, fault class, rate, campaign, block). Its hold is H_i = `holdSeconds` (declared 60 s,
  `traffic-sweep/DECLARATION.md:30`).
  - Every fault cell counts, even ones nothing caught. Dropping them would truncate the sample, which is BWSN's bias
    (`DIMENSIONS.md` §1.1).
- **P(i):** equal weight per class within a rate, and per episode within a class. This is an engineering default; an
  incident prior is `—`.
- **Rates (D-p1):** one placement per rate, S*(r), for three reasons.
  - Detectors and `celfCost` exist per rate only (decision 61).
  - Traffic is the parameter (decision 14), so the result is the map r → S*(r).
  - Pooling across rates would need a traffic profile.
  - Pooled arm: w_r uniform, the sensors placeable at every rate, and cost max_r c_r(s).
- **Traffic per route:** each sweep drives one route (`exposure.routePath`). `requestsStartedInWindow` is printed per
  episode. Scores are averaged over episodes, the realisations ω, never computed from mean times, because
  E[min] ≤ min E (`DIMENSIONS.md` §0).
- **No pooling across SUTs.** Sensor ids are SUT-specific. Every placement number is scope **instance**.

## 2. Objective (Leskovec et al., KDD 2007, §2)
- **Definitions:** T(i,A) = min_{s∈A∪{E}} T(i,s). The ledger is in every placement (decision 1), so CELF maximises
  g(A) = R(A∪{E}) − R({E}), where R(A) = Σ_i P(i)[π_i(∞) − π_i(T(i,A))].
- **Primary objective, TTD (decision 15):** π_i(t) = min(t, H_i). The penalised mean TTD is
  D(A) = Σ_i P(i) π_i(T(i,A∪E)) = D(∅) − g(A).
- **Submodularity.** This is an instance of Leskovec Theorem 1, and the review verified it.
  - Because π_i is nondecreasing, R_i(A) = max_{s∈A}[π_i(∞) − π_i(T(i,s))], with R_i(∅) = 0. That is a facility-location
    term, so it is monotone submodular.
  - Nonnegative sums and the contraction by E preserve this. No independence is needed.
  - Sufficient conditions, all kept here:
    - (a) T(i,s) does not depend on A. That rules out per-placement recalibration.
    - (b) Detectors are fixed per sensor: the OR of the calibrated rules, with no fusion and no k-of-n.
    - (c) A miss carries a finite charge, π_i(∞) = H_i.
    - (d) Scores are taken per episode, then averaged.
  - Any BC choice under D-p7 only changes which fires define T(i,s), so the form survives all three options.
- **The Heavey et al. (AAAI 2022) contrast is unverified.** No copy of the paper is in the repo; the characterisation
  comes from `DIMENSIONS.md` §1.1's quotation.
  - Reading of that quote: the expected delay, minimised with a multiplicative ratio, is not submodular.
  - Independent of their paper: D = D(∅) − g is supermodular. So (1−1/e) on g gives only
    D(Â) ≤ D(∅)/e + (1−1/e)·D(OPT). That is an affine bound.
  - The online bound (§5) is therefore reported as an **additive** certificate on mean TTD. (1−1/e) is never quoted for
    TTD.
- **Tie-margin arm (decision 35)** is a transform per (i,s), not a gain threshold.
  - The transform: T′(i,s) = T(i,E) whenever T(i,E) − m_i ≤ T(i,s) < T(i,E). Here m_i is the per-cell margin from
    `parameters.MARGIN_RULE`.
  - This keeps the facility-location form.
  - Thresholding marginal gains instead depends on insertion order, so it is not a set function
    (`tmp/placement-review/margin_demo.py`).
- **Second penalty, impact:** π_i(t) = the failed requests scheduled in [onset, onset+t]. This is P2's count:
  `failed_before`, with `COUNT_BY_SCHEDULED = True` verified at `sweep_analysis.py:156`, and client timeouts per
  decision 59.
  - A miss is charged the whole hold.
  - The penalty is nondecreasing in t, so the form is submodular.
  - The denominator is the episodes with ≥ 1 failed request. Counting slowed requests is `—` (D-p5).
- **Third penalty, detection:** π_i(t) = 1[t = ∞], Leskovec's DL. With E fixed, it gains only where the ledger misses.
- **TTD is primary.** Impact and detection are reported for the TTD placement, and each is also optimised once as a
  secondary row. No scalarisation.
- **Synthetic toy (not data).** H = 60 s.
  - E catches ep1 at 40 s and misses ep2 and ep3.
  - Sensor a catches ep2 at 5 s. Sensor b catches ep2 at 10 s and ep3 at 20 s.
  - Then D({E}) = 53.3, D(a) = 35.0, D(b) = 23.3 and D(a,b) = 21.7.
  - So g(a) = 18.3, g(b) = 30.0, and g(a | b) = 1.7 ≤ 18.3. The review reproduced these values.

## 3. Ground set and costs
**Placeable sensors per rate** (min-max over the 4 rates; the null counts include the ledger):

| system | placeable | cost 0 | cost null | cost > 0 | T_r | 3/T_r |
|---|---|---|---|---|---|---|
| Hotel | 266-267 | 230-242 | 4-5 | 20-32 | 1.20 h | 2.50/h |
| OTel | 1052-1107 | 927-967 | 88-114 | 27-39 | 1.05 h | 2.857/h |

**Sensors with ≥ 1 counted, BC-free fire**, non-E. Cells read r0.05 / r0.2 / r1 / r10, as zero/null/pos cost:

| system | sensors | zero/null/pos per rate |
|---|---|---|
| Hotel | 15 / 16 / 8 / 15 | 8/1/6 · 4/1/11 · 2/1/5 · 2/1/12 |
| OTel | 18 / 9 / 16 / 19 | 12/3/3 · 2/4/3 · 9/5/2 · 11/4/4 |

- Only these sensors can have a positive gain under the BC-free reading. So greedy picks at most 19 sensors per rate,
  and the budget grid in §4 has at most that many distinct points.
- No never-exposed sensor has a counted fire, on either system.
- **V_r = {s : `placeable` at r, family ≠ E}** (decision 67 pt 3).
  - Sensors whose rules are only `dropped`, `unarmed` or `inert` are excluded, and listed with the reason.
  - `appearOnly` sensors are included but listed apart, and one arm runs without them.
  - Own sensors: D-p8. BC catches: D-p7.
- **Cost:** c_r(s) = `celfCost`, the honest nested-LOCO alarms/h (decision 67). A `null` cost becomes 3/T_r, labelled
  "bound, no evidence" (decision 71). Which rule applies to zero-alarm and no-evidence sensors is D-p3.
- **Cost 0 is the norm, not an edge case.** It covers 230-242 of 266-267 placeable Hotel sensors and 927-967 of
  1052-1107 on OTel.
  - Gain/0 must never be computed.
  - Under the literal decision-67 rule, every cost-0 sensor with positive gain is **pre-admitted**. CELF then runs on
    the residual problem, and every guarantee and the online bound apply to that residual only.
- **The inversion:** decision 71's 3/T_r is the *floor* of any `honestUpperPerHour`.
  - An evidenced zero-alarm sensor with fewer folds has a larger bound. On OTel those bounds range over 2.85-59.9/h
    (59.91/h at 1 fold).
  - So under an upper-bound arm, a sensor with no evidence (3/T_r) would be cheaper than one with some evidence. D-p3
    must not leave this in place.
- **Additivity:** CELF charges Σ c(s). The measured union is **not** reliably smaller than the per-sensor sum.
  - On `allPlaceable` (re-run), Hotel's union exceeds the sum at 3 of 4 rates: 64 > 61 at r0.05, 194 > 183 at r0.2,
    149 > 122 at r10.
  - OTel's union is below the sum at 4 of 4 rates.
  - The readout prints both. The review note said 2 of 4 for Hotel; the re-run gives 3 of 4.
- **Instrumentation cost** (CPU-s, bytes) per sensor is `—`, because it exists per posture only.
- **Ledger E** is outside V_r, uncharged, and fixed in every placement. It is the baseline ({E}, g = 0). The view
  without the ledger is secondary (decision 1).

## 4. Budget (D-p2)
A knapsack budget B on Σ c(s) is a constraint, not a term in g. So all three options below satisfy decision 64 ("no FAR
constraint inside the objective") literally, and all three report the placement FAR beside the score.
- **(a) A FAR budget B = 6/h.** The number comes from decision 48, where it was the quiet runs' certification target.
  Here it would serve a new role, as a placement FAR budget.
  - 3/T_r is 2.5/h on Hotel and 2.857/h on OTel, so 6/h admits two null-cost sensors.
  - Under the literal D-p3 rule, cost-0 sensors do not count against B.
- **(b) Cardinality k = 1..19,** with the FAR printed per k. The decision-67 cost is then unused inside the optimiser.
- **(c) A Pareto sweep over B.** Each point prints g, D, detection, impact, the honest union and the online bound.
  - The grid is the cumulative costs along the CB order, at most about 19 points per rate.
  - Named points: 3/T_r, 6/h (decision 48's number, in the new role) and ∞.
- **Recommendation:** (c), with 6/h stated plainly as a FAR budget borrowed from decision 48. (b) is a secondary row.

## 5. Algorithm (Leskovec et al. 2007, §3)
- **Procedure:**
  - Pre-admit the cost-0 sensors with positive gain (under the literal D-p3 rule).
  - Run lazy greedy over the rest, once at unit cost (UC) and once cost-benefit (CB: gain/cost over the affordable
    sensors), and keep the run with the larger g.
  - This gives ≥ ½(1−1/e) of the residual optimum under B, and (1−1/e) under cardinality.
  - Ties go to the canonical id (`placement.py`). Greedy stops at zero gain.
- **Online bound:** g(OPT) ≤ g(Â) + the fractional-knapsack sum of the gains δ_s, ordered by δ_s/c_s, up to B. This also
  bounds D(Â) − D(OPT). Check the theorem numbers against the KDD PDF before citing them.
- **Code gaps:** `src/obsplacement/placement.py` optimises path coverage, not detection times. Its `greedy_cost_budget`
  is not lazy, has neither the UC/CB best-of nor the online bound, rejects cost 0, and supports no fixed member.
  - A commit there is a framework commit, which invalidates GATE-PLAN. The code therefore lives under `research/`.

## 6. Evaluation
- **Held-out episodes: leave one (campaignIndex, block) out**, not one block.
  - OTel's block 1 exists in both the sweep and B, so a block-only key would merge two episodes per stratum. TeaStore is
    expected to have the same shape; verify once its readout exists.
  - Each fold carries `harness`, because harness is confounded with campaign.
  - The fold mean is the headline, with the in-sample g beside it.
- **What the folds protect:** leave-one-out guards only the *selection*. Detectors, baselines and costs are fitted on
  all no-fault cells of the rate, and never on fault cells, so there is no outcome leakage. The no-fault fit is shared
  across folds, so the folds are not independent replications of the whole pipeline.
- **SUT roles** (user, 2026-09-15): TeaStore + Hotel train, OTel test, Online Boutique hold-out (`—`). See D-p4 for
  OTel's status.
- **Comparators,** each with D, detection, impact and FAR at the same rate:
  - E alone.
  - `full` = E ∪ V_r. Its FAR is in `allPlaceable`.
  - `selected` and `none` (Hotel: `sample-zero`, `none`), using per-SUT sensor sets. These are `—` until declared (D-p6).
  - The top-k individually best sensors, which tests §8's prediction "greedy ≠ degree at some k".
  - Every comparator is a restriction of `-full` cells (D-p9).
- **Placement FAR** (decisions 64 and 67):
  - The honest nested union over the chosen sensors ∪ E, with its bound, and the same without E.
  - `failed` stays exempt; its count is printed beside it (decision 63).
  - Fresh check: campaign B's no-fault cells, with the ≤ 20/h limit printed. Hotel has no B cells: `—`.
- **Isolability** (decision 2) is reported as a matrix, not optimised. Max-min over rates (decision 36) is not
  submodular, so it is a later row.

## 7. Hyperparameters and their origin (decision 37)
| parameter | value | origin |
|---|---|---|
| episode unit, rates | (SUT, class, rate, campaign, block); {0.05, 0.2, 1, 10}/s | decisions 14, 16 |
| miss charge | H_i = `holdSeconds` (declared 60 s) | decision 15; measured |
| P(i) | uniform over classes, then over episodes | engineering default |
| rate handling | per rate; pooled arm secondary | D-p1 |
| T(i,s) | v3.1 primary arm as frozen (`parametersV3Sha256`) | decisions 61-70 |
| BC catches | D-p7 | user; protocol :104-105, decision 11 |
| own sensors | D-p8 | user; protocol :101, decisions 11, 14 |
| cost | D-p3 (literal: `celfCost`, null → 3/T_r) | decisions 67, 71; LIT D21 |
| budget | D-p2 | user; decision 48's number |
| solver | pre-admit cost 0; lazy greedy, best of UC/CB; canonical-id ties | Leskovec 2007 §3 |
| tie-margin arm | per-(i,s) transform, m_i = `MARGIN_RULE` | decision 35 |
| impact | failed requests by scheduled time; miss = whole hold | decisions 15, 59; P2 |
| folds | leave one (campaignIndex, block) out | engineering default |
| comparators | restriction of `full` cells | D-p9; `DECLARATION.md:32-33` |
| FAR arms | honest nested union; `atMostOne`; B fresh | decisions 64, 65, 67 |

## What this does not fix
- Each (class, rate) has 4 episodes, so every number is instance scope, and any ranking needs the K × floor band.
- Detection stays binary. Decisions 38 and 44 are outside this design.
- `DIMENSIONS.md` §1.2's k/q derivation (impact flat with E fixed) is untested and stays a prediction.
- D-p7 and D-p3 are being decided after the E/BC and cost tallies above were seen. That is a forking path, stated here
  rather than hidden.

## Decisions for the user
- **D-p1 Rates:** one placement per rate, or pooled under a declared traffic profile. *Recommend: per rate.*
- **D-p2 Budget:** (a) Σ c ≤ 6/h; (b) cardinality k; (c) a Pareto sweep over B. *Recommend: (c), with 6/h named as a FAR
  budget borrowed from decision 48.*
- **D-p3 Costs for zero-alarm and no-evidence sensors:**
  - (i) Decision 67/71 literal: an evidenced 0 costs 0 and is pre-admitted (most sensors); null costs 3/T_r.
  - (ii) Every sensor at its `honestUpperPerHour`, null at 3/T_r. This inverts: no evidence costs less than thin
    evidence.
  - (iii) Upper bounds throughout, null at the rate's largest evidenced `honestUpperPerHour`. This is monotone in
    evidence and never free, but it amends decisions 67/71.
  - Variant of (iii): every zero-count sensor, evidenced or not, at bound(0, T_r) = 3/T_r.
  - *Recommend: (iii) primary, with (i) reported as the literal arm.*
- **D-p4 OTel's role.**
  - Both readouts carry the frozen renderer's fixed label "exploratory, not frozen (every cell of this system was read
    under v2.4 before v3 was written)". That string is inaccurate for B cells, which were first read in 0a8517a.
  - The coordinator read `readout-otel-primary-v3.1/SWEEP_ANALYSIS_V3.md` in full on 2026-10-10, after committing it.
    That read included the P4 folds (per-episode sensor-vs-ledger times of the P4 candidates) and the primary-outcome
    table per family.
  - OTel as a placement test is therefore already compromised to that extent, and D-p7 is being chosen with OTel's
    E/BC counts known.
  - Options:
    - (a) Keep OTel as the test and state the compromise.
    - (b) Relabel OTel as training; the clean test then becomes a campaign run after the freeze (OTel or Online
      Boutique).
  - *Recommend: (b).*
- **D-p5 Impact:** failed requests only, or failed + slowed (which needs a new threshold). *Recommend: failed only.*
- **D-p6 Posture comparators:** declare the `selected`/`none` sensor sets from the posture definitions, or compare only
  with E and `full`. *Recommend: declare them, labelled as restriction estimates.*
- **D-p7 By-construction catches** (protocol :104-105 reports detection with and without BC; decision 11, :217, reports
  BC apart). Clean E (BC-free) catches:
  - OTel: 0/32 episodes. All 32 E fires are `BC-ledger-stopped-on-path` in frontend-pause; productcatalog-cpu-throttle
    has no E fire at all.
  - Hotel: 19/48 episodes (net-delay 16/16, cpu-throttle 3/16, search-pause 0/16).
  - Options:
    - (a) BC = miss for all. The fixed ledger is then vacuous on OTel.
    - (b) BC counts for E only, since the ledger's stop is the user-visible symptom.
    - (c) BC counts for all, with a BC-free secondary view.
  - *Recommend: (b), with (a) and (c) as reported arms.*
- **D-p8 Own sensors** (the sensor is on the fault target). Fire-bearing sensors that fire as own: Hotel 5/15, 7/16, 2/8,
  4/15; OTel 9/18, 0/9, 2/16, 3/19.
  - Options:
    - (a) Own sensors in the primary objective, reading decision 14.
    - (b) Own sensors excluded from the primary, with the `X:own` columns secondary. This follows protocol :101 (G2,
      "outside the target") and decision 11, :217.
  - *Recommend: (b), as the protocol is written, with (a) as an arm.*
- **D-p9 Restriction of `full` cells.**
  - Protocol :102 allows restriction only where a posture-leak check passes. That check cannot run on all-`full` cells.
  - `DECLARATION.md:32-33` already calls restriction an approximation.
  - Options:
    - (a) Declare restriction as a deviation, with decision 46.3's live run of the chosen placement as the later check.
    - (b) Wait for posture runs that allow the check.
  - *Recommend: (a).*
- **Before any placement work:** after these answers, a budget and stop rule for the placement step is committed alone,
  using `research/OTEL_STOPPING_RULE.md` as the template.
