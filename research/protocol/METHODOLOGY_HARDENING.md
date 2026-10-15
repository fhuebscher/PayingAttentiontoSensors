# Methodology hardening (2026-10-03): what we keep, what changes, what you decide

**Goal (user, round 7):**
- the method is correct;
- it generalises across Hotel, TeaStore and the OTel Demo;
- it uses the field's standards where they exist instead of new ones.

**Inputs:**
- the Hotel readout review `research/traffic-sweep/readout-hotel-r3/REVIEW.md`;
- three literature notes in this folder, each with verbatim quotes and verified DOIs. Source ids carry the note's letter:
  - `L` = `LIT_TIME_SEMANTICS.md` (40 sources);
  - `D` = `LIT_DETECTION_RULES.md` (64);
  - `M` = `LIT_MISSING_SENSORS.md` (28).

  `D3` here is a source id. The repo's "D3" (probabilistic detection) is written as "dimension D3".

Already decided:
- **k (decision 26):** actuator readback is not a detection.
- **l (decision 27):** relative floor.

## 1. Your challenge, answered in one place
| your question | what the field does | what we do |
|---|---|---|
| **Filter out noise from default system load** | Learn the background from fault-free data, and set the alarm level by a false-alarm rate per hour, not per window [D17, D46, D55]. | Pool all fault-free time per rate as the baseline. A cell's post-onset (scored) data never fits anything. Measure false alarms per hour of the combined rules on held-out quiet time (H1, H2). |
| **Sensors differ in sensitivity per system** | There is no standard [D52-D64]. Three patterns: (a) one generic rule with the scale fitted per system from fault-free data; (b) calibration on known faults per system, where claims then hold for that system only; (c) a held-out tuning split. | Pattern (a), with a common **operating point**. Frozen once and shared by all three systems: the target false-alarm rate per hour, the relative-floor fraction and the rule families. Fitted per system, only from its fault-free data: each sensor's scale (median, spread, gaps) and the threshold multiplier K needed to meet the target rate. A frozen K would not give comparable false-alarm behaviour across different sensor populations (H7). |
| **Tune generic parameters from a baseline run plus a guided/chaos run** | Allowed, but a run used for tuning is calibration, never evidence. Tuning on the same faults you test on inflates results [D52-D64]. | A guided/chaos run may set the generic parameters on the train systems (Hotel, TeaStore) only. OTel stays untouched as the test system. Nothing is tuned on OTel fault cells (H7). |
| **Survivorship: sensors in the full graph that never show up (−∞)** | Placement papers model the unobserved part instead of dropping it [M1, M2]. Ecology separates "absent" from "present but not detected" (occupancy models) [M18, M22]. Microservice work names the gap but does not solve it for placement [M8-M14]. | Now: record **exposure** per sensor, fault and episode, for wording and to find never-exposed sensors. The objective still charges misses as Leskovec does. Report a pessimistic and an optimistic placement, and give one number for how much is unseen (H5, H6). Later: a hierarchical detection model gives every sensor a probability instead of −∞ (H9). |

## 2. Each analysis default: keep, change, or your decision
"Engineering" means I make the change and record it. "▶ you" means it changes what is measured or what counts as a
result.

| # | default today | verdict | why, with sources |
|---|---|---|---|
| 1 | Onset = when the fault command is issued | **▶ you (H4)** | The field uses one stamp at the command and assumes the effect [L17, L19-L21, L26]. That is too coarse for 0.1-0.3 s leads. For `docker pause`, the Docker `pause` event comes after the kernel confirms the freeze, so [command, event] very probably bounds onset [L33-L35]. We already keep `docker-events.json` in every cell. |
| 2 | Threshold = baseline median + 4 × robust spread | **keep the form; K becomes fitted (H7)** | Textbooks give K = 2.5-3.5; 4 is stricter [D1-D4]. With a common false-alarm operating point, K is fitted per system to meet it and is reported; K = 4 stays as the reference row. |
| 3 | Baseline = the cell's own pre-onset requests (4 at 0.05/s) | **▶ you (H1)**: pooled and cross-fitted | With 3-4 points, the K = 4 rule fires on 6-16 % of quiet points instead of 0.003 % (two simulations, `LIT_DETECTION_RULES.md` appendix). Tools use ≥ 6-12 points; process control uses 50-100 [D2, D5, D6, D10, D13]. |
| 4 | False-alarm gate: ≤ 5 % of 4 quiet windows (= 0 of 4) | **▶ you (H2)** | 0 of 4 only shows the rate is below 53 %; showing below 5 % needs 59 windows. The standard is a rate per hour (ARL0/FAR) over all quiet time, for the combined rule set [D17, D18, D21]. |
| 5 | Floor = fixed 1 ms | **changed (l)** | Engineering value: the larger of K × spread, **10 % of the baseline median** and the clock resolution, with a 5 % arm. Regression tools use 2-10 % [D7-D14]. |
| 6 | Readiness-probe windows excluded from scoring | **keep**, **▶ you for later runs** | The exclusion is right. The 5 s hang under a pause is caused by our own probe, so later runs should not probe during the fault (H10). |
| 7 | Log time = Docker receive stamp | **keep, labelled as receipt time** | It is the time Docker read the line from the container's output, a receipt stamp that approximates the write time. The receipt delay is **measured per line**: the line was written at or after the app's own stamp, so delay ≤ receive stamp − app stamp. The per-cell maximum of that difference is the log receipt-delay bound in the margin (H3 b). Where an app writes no stamp, log leads are not counted. |
| 8 | Observation time = event time (span end, request end, sample stamp) | **▶ you (m, H8): both clocks; a win needs both** | Papers that define detection delay for placement use event time [L1-L4, L6-L9]; operations and the judge argue for availability, since a detector cannot alarm before it has the data [L11, L14]. Both are computed. Event time is the stamp. Availability is the time the observation **reached the collector**, taken from the collector's own receive stamp where one is recorded. Where none is recorded it is `—`, never estimated from a configured interval (Jaeger flush 1 s, OTel batch ≤ 5 s [L38]), because queues and retries can exceed it. The placement objective uses event time (Leskovec), with availability as a sensitivity row. A P4 win must hold in both clocks. Reporting both has one precedent [L27]. |
| 9 | Misses charged at the 60 s hold | **keep** | This is Leskovec's min{t, T_max}, which equals the restricted mean survival time at 60 s [D30-D35, M1]. Print k/n beside it, and a Kaplan-Meier curve when misses are common. It applies to **every** episode, exposed or not: in Leskovec's objective, a sensor the outbreak never reaches simply does not detect it (H5). |
| 10 | P1 (ledger catches a pause at the expected time, ±0.5 s) | **▶ you (H4)** | The model ignores requests in flight at the freeze, and ±0.5 s is shorter than the gap between requests at ≤ 1/s. Positive controls state the expected response and tolerance in advance [L30, L36, L37, L39]. No published timing tolerance exists. |
| 11 | P2 | **keep** | Recomputed, holds. |
| 12 | P3 (traffic-independent signals catch equally at all rates) | **▶ you (H11)** | It picked frontend memory, which depends on traffic. Restrict it to signals that are traffic-independent by mechanism, or drop it. |
| 13 | P4 win = strictly faster than the ledger in ≥ 3 of 4 episodes | **▶ you (H3)** | 3 of 4 has p = 0.31, and even 4 of 4 is only 0.06. The field compares detectors at a **matched false-alarm rate**, with a paired comparison and a trivial baseline [D17, D18, D24, D50, D51]. No paper sets a time margin [L, C-m4], so we declare one: the timing uncertainty between the two sources (H3 b). |
| 14 | Leave-one-episode-out selection | **keep for Hotel (4 episodes)**, report ties; **none for TeaStore and OTel** | Selection inside the loop is almost unbiased but noisy [D36-D39]; report the win share across tied sensors. With 1 episode per condition (TeaStore, OTel) no selection or win verdict is possible: per-sensor times only, descriptive, as their declarations already say. |
| 15 | By-construction flags | **extend (k) and add same-request** | Add actuator readback for degradation faults: PSI and CPU-throttle counters of the throttled container, and qdisc stats of the delayed interface. Add **same-request lead**: when a sensor's catching observation belongs to the same request (token) as the ledger's catching row, the lead is the observation's position inside that request, not earlier information. The review found this behind the net-delay wins at 1 and 0.2/s. At 10/s the win came from the `absent` rule, which the ledger does not have (H3 e). |
| 16 | Impact = failed requests by scheduled time | **keep** | Requests in flight at onset go into a "straddling" class (H4) [L9]. |
| 17 | Candidate sensors = those that showed up | **▶ you (H6)**; exposure is reported (H5) | Selection on the outcome is survivorship bias proper [M5, M6]. Leskovec's fix for picks that were lucky once is a minimum-activity floor [M1 §5.7]. |
| 18 | Probabilistic detection not computed | **keep binary as primary**; exploratory later (H9) | A posterior detector still needs a threshold to give a time. CELF stays valid on the expected objective; fusing sensors into one posterior can break submodularity [D41-D49, M1-M4]. |
| 19 | Stale readout text; rules not printed on P4 lines | **engineering** | Fix, regenerate into a new directory, and show that only text changed. |

Engineering additions, reports only, no verdict changes:
- false-alarm rate of the combined rule set;
- the scope of every optimum ("over this ground set, this workload, this posture") with the four-state projection counts;
- an exposure-floor robustness row;
- a Chao2 / discovery-probability estimate of how much is unseen, which under-estimates [M15-M17];
- the wording rule "not exposed in this run", never "cannot detect" [M, R6].

## 3. Your decisions, with my recommendation
- **H1 Baseline and the calibration boundary.** One rule: **no post-onset data of an evidence episode is ever used to
  fit anything that scores evidence.** Three declared exceptions:
  - designated calibration runs (H7), on the train systems only, never reported as evidence;
  - the exploratory H9 model. It is **not** kept apart: it is fitted on the same evidence it describes. So its output
    is descriptive only, never a verdict and never a rule parameter. Any claim made from it needs held-out scoring:
    leave-one-episode-out on Hotel, or the test system.
  - P4's leave-one-episode-out **selection** (Hotel), which picks the sensor from the other 3 episodes' post-onset
    results. The held-out episode never enters its own selection, and selection never fits rule parameters.
  - **Generic parameters** (target false-alarm rate, relative-floor fraction, rule families) are frozen before any
    evidence is scored, and shared by all systems.
  - **Per-system fitted values.** Each sensor's scale (median, spread, largest gap) and the K that meets the target rate
    come from fault-free data only:
    - the no-fault cells;
    - all pre-onset time of fault cells, unscreened. It is fault-free by design: fresh deployment per cell, onset at
      ≥ 60 s. Only the declared warm-up and probe windows are excluded.

    A fault episode's own pre-onset may enter its baseline, because a real detector has it at onset. Its post-onset data
    never does.
  - **False alarms** are counted on a quiet cell scored with values fitted without that cell (leave-one-cell-out).
  - Require n ≥ 20 baseline points, else `—`. *Recommend yes.*
- **H2 False alarms, held out:**
  - Count false alarms per hour of the combined rules (OR), sliding over each held-out quiet cell, with an exact bound.
  - Arithmetic: per rate, 4 no-fault cells × 180 s = 12 min; with 12 pre-onset minutes, about 24 min. With 0 alarms,
    the best certifiable is about 15/h (12 min) or 7.5/h (24 min) at 95 %.
  - *Recommend:* fix the target operating point (H7) and compare detectors at it. ≤ 15/h is the most this data can
    certify.
- **H3 P4 (Hotel only; TeaStore and OTel descriptive, 1 episode):** a sensor beats the ledger only if:
  - (a) it is faster at the common false-alarm operating point;
  - (b) the lead exceeds the **timing uncertainty between the two sources**, in **both** clocks (H8). The uncertainty
    is the sum of:
    - both stamps' granularity;
    - the clock-alignment error between the ledger's monotonic clock and the wall-clock stamps of spans, logs and
      metrics. It is measured directly: every ledger row has both a wall-clock and a monotonic stamp, so a per-cell fit
      of wall = monotonic + offset gives the residual. Same-request pairs are **not** used for this, because they
      include the real response path, which row 15 flags instead;
    - for logs, the measured receipt-delay bound (row 7);
    - in the availability clock, only the uncertainty of the measured receive stamp (its granularity). The export
      delay itself is already inside the availability time (H8), so it is not counted twice;
  - (c) it is not a same-request lead or actuator readback (row 15);
  - (d) "the ledger missed it" counts separately from "faster";
  - (e) the ledger gets the same rule families where they apply, including `absent` on request completions.

  Paired differences with intervals, descriptive at n = 4. P4 selection (which sensor) uses the other 3 episodes'
  results only. *Recommend yes.*
- **H4 Onset and P1:**
  - **Onset as an interval.** [command, Docker `pause` event] for pauses. For throttle and netem, [command issued,
    command returned] plus a check that the effect happened.
  - **Requests classed** as before, straddling or after.
  - **P1's expected catch becomes an interval.** For every possible freeze instant inside the onset interval, compute
    when the first request outstanding at the freeze would time out. Requests that complete inside the interval are
    ambiguous and do not fix the expectation alone. P1 holds if the observed catch falls in [earliest, latest] expected
    ± a tolerance declared before the run.
  - **F1/G2** keep the lower bound, as the gate requires.

  *Recommend yes, for the analysis now and the harness in later runs.*
- **H5 Exposure, recorded but the objective unchanged:** record per (sensor, fault, episode) whether traffic reached
  the sensor during the fault (interior exposure is projected from the call graph, not observed; say so). Exposure is
  used for three things:
  - wording: "not exposed in this run", never "cannot detect";
  - a capability estimate conditioned on exposure (exploratory, the H9 model);
  - finding sensors never exposed in any run, which go to the bounds (H6).

  The placement objective keeps Leskovec's scenario penalty: a miss is charged in every episode, because in that traffic
  scenario the sensor would not have seen the fault. Dropping non-exposed episodes from the objective would favour
  rarely exposed sensors. *Recommend yes.*
- **H6 Placement bounds:** run CELF pessimistic (unseen = 0, as now) and optimistic (unseen = the best rate of its
  channel × role class). If the chosen set changes, the placement depends on the unseen part. *Recommend as a robustness
  row, not the primary result.*
- **H7 Per-system calibration:** pattern (a) with a common operating point. Frozen and shared: the target false-alarm
  rate, the floor fraction and the rule families. Fitted per system from fault-free data: scales and K. *Recommend.* Spending runs on a guided/chaos calibration set for
  Hotel and TeaStore is your call; OTel never.
- **H8 Two clocks (decision m):** compute both. Availability uses measured collector receive times only (`—` where
  none is recorded). The placement objective uses event time, as Leskovec does, with an
  availability sensitivity row. A P4 "faster" verdict must hold in both clocks. *Recommend.* The literature splits by
  purpose (placement uses event time, operations use alarm time), so the primary clock for the thesis's headline claim
  is your call.
- **H9 Probabilistic dimension:** later, an occupancy-style hierarchical model:
  - each sensor gets a detection rate;
  - random effects by channel × role × system;
  - a time-to-detection likelihood censored at the hold;
  - traffic as the exposure.

  Every projected sensor gets a posterior, not −∞, and CELF runs on the expected penalty reduction [M18, M22, M1-M4].
  Your Kalman/state-space idea models the signal over time, which is a different layer: it would feed the detector, and
  this model would feed the placement. *Recommend as the next paper's core, exploratory here.*
- **H10 Later runs:** no readiness probe during the fault; stamp the freeze.
- **H11 P3:** restrict to traffic-independent signals by mechanism, or drop. *Recommend restrict.*

## 4. Order of work after your decisions
1. Analysis v2 implements the decisions (H1-H5, H8, rows 15 and 19, the reports).
   - Hotel's v1 results have been seen, so **v2 on Hotel is a re-analysis, labelled exploratory**. Its rules come from
     the decisions above, not from which verdicts they move.
   - It is regenerated into a new directory, and every verdict that moves is listed against v1.
2. v2 is frozen and committed **before** any TeaStore or OTel cell is read. For those systems it is the first analysis,
   and descriptive (1 episode).
3. The placement graph comes next: sensors × episodes with detection times feeding CELF per rate, pessimistic and
   optimistic (H6), and a service call graph with sensors coloured by detection time.
4. The harness changes for later runs (H4, H10) go into the next campaign's declaration.

## Review
Judge, single helper (gpt-6.1-sol, `panel_n: 1`), session `methodology-hardening-20261003`.
- **v1** (`eval_94201a5086cd4982bf5c9d7f021bb720`): 4/11 criteria passed (C3 cross-system calibration, C7 onset
  interval, C9 CELF on the expected objective, C10 no false "standard"). The failures, each checked and accepted:
  - **C6/C8:** event time primary vs an availability-based tie margin. Fixed: one clock for verdicts, plus the
    same-request flag.
  - **C2:** baseline and false alarms fitted and counted on the same data. Fixed: cross-fitted, held out.
  - **C5:** dropping non-exposed episodes changes Leskovec's objective and favours rarely exposed sensors. Fixed:
    misses are charged everywhere, and exposure is used only for wording and bounds.
  - **C1/C4:** leave-one-out and P4 verdicts are impossible with 1 episode (TeaStore, OTel). Fixed: descriptive there.
  - **C11:** the unspecified "clean" screening biases the baseline. Fixed: unscreened pre-onset time.
- **v2** (`eval_c8aa4744ee3e4f069481dee75de2d714`): 4/11 passed (C5 exposure, C9 CELF, C10 standards, C11 unscreened
  baseline). C3 and C7 flipped from pass to fail on unchanged or near-unchanged text, which shows this single judge
  varies between runs. The failures were still substantive, and each was accepted:
  - **C3:** a frozen K does not give comparable false-alarm behaviour across systems. Fixed: a common operating point,
    with K fitted per system.
  - **C4/C6:** stamp granularity ignores cross-source timing uncertainty and log receipt delay. Fixed: margin = summed
    timing uncertainty, with alignment measured from same-request pairs.
  - **C2/C8:** the calibration boundary was stated inconsistently. Fixed: one rule, no post-onset data fits anything.
  - **C7:** P1 must not count requests that completed inside the onset interval. Fixed: the expected catch is an
    interval.
  - **C1:** event time can predate data availability. Answered: both clocks are computed and a win needs both; the
    primary clock stays decision m.
- **v3** (`eval_620c8a0be247477daf0ad16d37bbfaca`): **8/11 passed, overall pass**. The 3 remaining failures were
  accepted and fixed in v4:
  - **C1:** the log receipt delay was unbounded. Fixed: logs need a > 1 s lead until it is measured.
  - **C4:** same-request pairs include the real response path, so they cannot measure clock alignment. Fixed: alignment
    from the ledger's own wall/monotonic pairs.
  - **C8:** the blanket calibration rule contradicted H7 and H9. Fixed: two declared exceptions.
- **v4** (`eval_fa941cdccf2141f9b34d107ad505a5b7`): 8/11 passed, overall pass. Accepted and fixed in v5:
  - **C1/C4:** the app's stamp resolution does not bound pipe delay. Fixed: the bound is measured per line (receive −
    app stamp). Availability is measured per observation where possible, and the export interval is used otherwise.
  - **C8:** leave-one-out selection uses other episodes' post-onset results. Fixed: a third declared exception.
- **v5** (`eval_5e8bf3748b5343c387c7d9d58a00f4cb`): 8/11 passed, overall pass. C1 now passes. Accepted and fixed in
  v6:
  - **C4/C6/C8:** the export delay was added to availability time and again to the margin, and a configured interval is
    not a bound. Fixed: availability is measured receive time only (`—` otherwise), and the margin carries only that
    measurement's own uncertainty.
- **v6** (`eval_b9a1b3e49672472db8adeefe254f4bbb`): **10/11 passed, overall pass.** The one failure was C8: H1 said all
  three exceptions are kept apart from what they score, but H9 is fitted on evidence. Fixed by wording: H9 is declared
  not separated, so its output is descriptive and held-out scoring is required for any claim. Not re-judged.

Judge limits:
- **Single judge.** One model, `panel_n: 1`.
- **It varies between runs.** C3 and C7 flipped on unchanged text between v1 and v2.
- **It judged a condensed restatement of this note.** It did not see the note itself, the literature notes, or any
  evidence.
- **What its passes mean:** the reasoning holds on its own terms. They do not establish that the cited sources say what
  the note says. The literature notes' own reviews cover that: verbatim quotes are checked by script, and one Fable
  review was run per note.
