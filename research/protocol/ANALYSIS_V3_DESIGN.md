# Analysis v3: per-rule calibration on quiet data (design proposal, 2026-10-09, not adopted)

Answers the seven options at the end of `research/traffic-sweep/SYNTHESIS_V2_4.md`. Nothing here is adopted until the
user says so; adopted parts become protocol decisions and analysis v3, frozen and reviewed before campaign B
(`research/traffic-sweep/BUDGET_B.md`) is read. The v2.4 readouts stay the record of the first round; under v3 all
three systems' existing cells are exploratory.

## The problem in one line
v2.4 calibrates one K per family against the union of every rule of every sensor in it (decision 53), so one rule that
cannot be calibrated removes the family, and B1 (decision 55) then removes P4. The binding rules were few, and most did
not respond to K (`SYNTHESIS_V2_4.md`, reviewed).

## Proposal

**1. Unit: one threshold per (sensor, rule), chosen on quiet data.** This is the literature note's own recommendation
("calibrate each sensor's combined rule", `LIT_DETECTION_RULES.md` Q3), refined to the rule, because the review showed
that within one sensor one rule can be uncalibratable while the others are fine. A sensor's detector is the OR of its
calibrated rules.

**2. Criterion: zero held-out alarms.** For each (sensor, rule) take the smallest value on its grid such that, fitted
leave-one-cell-out on the no-fault cells of that rate, it raises **no** alarm in any held-out cell. Its rate bound is
then the exact 95 % bound for 0 events, 3/T per hour: 5.45/h with 0.55 h (TeaStore, OTel), 4.28/h with 0.70 h (Hotel).
This removes the free target parameter (15/h vs 6/h, option 6): every calibrated rule meets ≤ 6/h, the size the quiet
runs were built for (decision 48), by construction. The criterion is generic: no system-specific value.

**3. Grids per rule kind** (the generic part, identical on all systems):
- Level rules (`spike`, `run3`, `median`): K on the existing grid (≤ 100, decision 55 unchanged). If no K gives zero
  held-out alarms, a **range fallback**: the fit cells' empirical minimum and maximum, widened by one resolution step,
  two-sided. This is decision 52's quantile threshold at its extreme quantile, and it handles the two-state, quantised
  and bimodal series the review found (`sys_io` 0 vs 3,275 B/s; GC rates; `resolve_page_components`), with no special
  case for any shape.
- `absent`: the gap g = m × (the largest inter-arrival gap in the fit cells, **including** the censored silences from
  window start to the first record and from the last record to window end). m on a grid {1, 1.5, 2, 3, 5}. Counting
  the censored silences is what makes deployment-locked one-shot bursts (kafka at +4-5 s and +125 s, Hotel's GoAway pair
  at +76-77 s) normal: their long silence is in the fit data. No template list, no regex.
- `appear`: unchanged (a template or operation never seen in the fit cells); it is calibrated by the same zero-alarm
  criterion, and dropped for a sensor where it still fires.
- `MIN_BASELINE_POOLED` = 20 stays for estimating a scale; below it the rule is not armed and is listed.

**4. What cannot be calibrated is listed, not hidden.** A (sensor, rule) with no grid value meeting zero alarms is
dropped from that sensor's detector and listed with its held-out count. A sensor with no calibrated rule is **not
placeable at this quiet time**, which is a statement about the data, not about the sensor ("cannot detect" is never
claimed).

**5. The ledger.** E's `spike` and `absent` are calibrated like any sensor. E's `failed` is the client's definition of
failure and the positive control of P1/P2, so it is exempt; its count in the no-fault cells is reported (OTel r10 had
one failed request in a no-fault cell).

**6. Placement-level false alarms: reported, not constrained.** Beside every placement score, report the held-out
**union** alarm count of the chosen sensors on the no-fault cells and its exact bound. Measuring the union directly
avoids assuming independent sensors, which the note warns against (Q6) and D29's Σ f_i ≤ ρ assumes. A FAR budget inside
the CELF objective (a knapsack-type constraint) stays a later comparison (note row 7: a user decision).

**7. P4 over calibrated sensors (replaces B1).** P4 compares the ledger with the placeable sensors; the readout names
every dropped rule and non-placeable sensor of the class. P4 is `—` only where the ledger's own compared rule is not
calibrated, or where fewer episodes than declared exist (as now).

## What it costs and what it does not fix
- **Selection on the same data.** Choosing the smallest zero-alarm value and certifying it on the same held-out cells is
  optimistic. Campaign B's no-fault cells (3 per rate per system, 0.15 h) are fresh data: v3 reports the calibrated
  detectors' alarm count on them as an out-of-sample check, and Hotel's existing cells cannot provide one.
- **Zero alarms favours late detection.** A larger K or m delays catches. That is the declared trade-off, and the delay
  vs false-alarm curve (decision 47, W2) shows it; v3 adds one sensitivity row at "≤ 1 held-out alarm".
- **Per-rule calibration adds degrees of freedom** (one value per rule instead of per family). Their number is reported
  per system; cross-system claims cover only the generic part (grids, criterion, rules), per the note's recommendation 5.
- Unchanged: decisions 51, 54, 57, 58, 60 (same-request and onset rules), event time primary, the exposure record, the
  operating-point inputs (no-fault cells only, no post-onset data).

## Decisions for the user
- **D-a** Unit = (sensor, rule) with zero held-out alarms (points 1-2).
- **D-b** Range fallback for level rules and censored-silence gap for `absent` (point 3).
- **D-c** Ledger `failed` exempt (point 5).
- **D-d** Placement FAR reported as the measured union, not constrained (point 6).
- **D-e** P4 over calibrated sensors, replacing B1 (point 7).

## Review and amendment v3.1 (2026-10-09, proposed, not adopted)
Independent read-only review with a feasibility run on the existing cells (Fable `adversarial-review`; scripts and
outputs kept in `tmp/v3review/`; scope instance, exploratory). The mechanics work (each system runs in about a minute
on the frozen loaders; the binding rules stop blocking families). Three claims above do not hold:
- **"≤ 6/h by construction" is false after selection.** The smallest zero-alarm value is the empirical maximum of the
  10-14 held-out cells, so a fresh cell exceeds it with probability about 1/(n+1) per rule. Scored honestly (each
  held-out cell at the value re-selected without it), the union of a family's calibrated rules alarms 20-340/h
  (Hotel S 340/h, TeaStore S 91/h, TeaStore T 52/h, OTel M 50/h, OTel T 23/h, Hotel T 34/h).
- **The union report (point 6) is 0 by construction** on the cells it is computed from. Campaign B adds 0.15 h of
  no-fault time per rate, which certifies ≤ 20/h at best; Hotel gets no fresh cells.
- **The range fallback and the censored gap are generic in form, shape-specific in effect.** The fallback rescues only
  discrete series (a continuous one always leaves exactly 1 held-out alarm). The censored gap makes one-shot `absent`
  rules "calibrated" with gaps of 90-264 s, longer than the 60 s hold, so they can never fire. And `appear` alone makes
  almost every sensor placeable, so "not placeable" never discriminates.
- **Survivorship (point 7):** on OTel, in 4 of 8 episodes a dropped rule (at K = 100) catches where every calibrated
  rule misses (productcatalogservice GC count, frontendproxy egress, frontend GET, frontend calls).

Proposed amendment (v3.1):
1. Selection stays as in points 1-3, but **no false-alarm claim uses the naive 0.** Every (sensor, rule) and every
   sensor carries its **honest nested-LOCO count** and rate; a sensor's honest rate is its cost for CELF (this restores
   a real per-sensor cost, which zero-alarm selection had removed).
2. Placement-level false alarms = the **honest nested union** of the chosen sensors on the no-fault cells, with campaign
   B's no-fault cells as a fresh check whose limit (≤ 20/h certifiable) is printed.
3. A rule whose calibrated value cannot fire inside the hold (e.g. `absent` gap > hold) is **inert**: neither
   calibrated nor a reason to call the sensor placeable. Placeability is reported per (sensor, rule); `appear`-only
   sensors are listed apart.
4. The range fallback is declared **discrete-only in effect** and labelled; no "≤ 1 alarm" sensitivity row for it.
   Range is up-only for latency channels (spans, ledger) and two-sided for metrics. A cell with no records contributes
   no silence.
5. Decision 52 kept: MAD = 0 → no K rule; the range fallback may apply (labelled). K = 100 selections are flagged "at
   grid edge". Calibration is class-independent (one value per rule and rate).
6. P4 reports two arms: **calibrated** (primary) and **optimistic** (dropped rules at the largest grid value), as H6's
   pessimistic/optimistic bounds. The ledger's `failed` stays exempt and P4 says so; E's rule mix per rate is printed
   (at r0.05 its `absent` now precedes `failed` on TeaStore).
