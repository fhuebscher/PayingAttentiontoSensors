# Detection rules: what the field does, question by question

Written 2026-10-04 for decisions (l) relative floor and (m, n) "use the field's standard"
(`research/PROTOCOL_DRAFT_20261002.md`, round 7). Literature only. The only new numbers are a few small
computations, labelled **computation**, with the method stated in the appendix.

Review status: one independent read-only review (a separate Fable session, adversarial-review agent), 20 findings,
all applied; not re-reviewed. See "Review" at the end.

## How to read this

- **Source ids** D1 … D64 point to §3. Every quote in §3 is verbatim. A script checked each one against the text
  of the downloaded PDF or HTML, after normalising whitespace. Nothing was quoted from a search snippet or a
  tool summary.
- **Recent work (2023–2026) weighs more**, as the user asked. 23 of the 64 sources were published 2023–2026
  (D8, D10, D15, D16, D25, D27, D28, D35, D38, D39, D45, D46, D52–D59, D62–D64), most of them microservice
  anomaly-detection, RCA and performance-regression papers. Where recent work departs from the classics,
  the summary says so. The main departure: recent ML benchmarks score without a threshold (Q3, Q7).
- **DOIs** were checked one by one. Each DOI's registry record (Crossref, or DataCite for arXiv) has to carry
  the title of the paper that was read, and `https://doi.org/<doi>` has to redirect. "None" means no DOI was
  found. Nothing was guessed. One guessed arXiv DOI failed this check and was dropped.
- **Scope labels** on conclusions:
  - *general practice*: several independent sources, or a textbook standard.
  - *one paper*: a single source.
  - *tool-specific*: one tool's default.
  - *my inference*: my own reasoning, not taken from a source.
  - *no standard*: none found.
- **"Says" vs "I conclude"**: §3 states what each source says. §1 and §2 state what I conclude, with a scope label.

### Terms used below

| term | meaning |
|---|---|
| MAD | median absolute deviation: median of \|x − median(x)\|. For normal data, 1.4826·MAD estimates the standard deviation σ. |
| K | how many scaled MADs above the baseline median a value must lie to count as a catch. K = 4 means 4·1.4826·MAD, about 4σ. |
| floor | the smallest change that counts, whatever K·MAD says |
| baseline | the no-fault data the median and MAD come from |
| false alarm | a catch where no fault was injected |
| ARL0, FAR | ARL0 (average run length to false alarm) is the mean time between false alarms on no-fault data. FAR is its inverse, false alarms per unit time. |
| detection delay | time from fault onset to the first catch |
| censoring | the episode ended (60 s hold) before any catch, so the true detection time is only known to be later |
| RMST | restricted mean survival time: the mean of min(T, τ), with every miss counted as τ |
| Kaplan–Meier (KM) curve | here, the share of episodes still undetected at each time t |
| leave-one-out (LOO) | select on all episodes but one, score on the one left out, and rotate |
| BOCPD | Bayesian online change-point detection: a posterior probability, at each step, of how long ago the data last changed |
| innovation | a Kalman filter's one-step prediction error, with a known variance when nothing has changed |
| SESOI | smallest effect size of interest |
| G3 | the analysis's false-alarm gate: a rule is admissible only if it fires in ≤ 5 % of no-fault windows |
| P4 | the pilot's prediction that some sensor beats the ledger (`research/traffic-sweep/DECLARATION.md:60-62`); P4a = sensors outside the target, P4b = the target's own |
| ledger | the load driver's own record of every request (the untraced baseline detector) |
| SPC | statistical process control (control charts) |
| IQR | interquartile range |
| MDE80 | the smallest planted shift a sensor detects in ≥ 80 % of trials |

---

## 1. Summary, per question

**Q1. Robust thresholds (median ± K·MAD).**
- The references disagree on K:
  - Leys et al. recommend K = 2.5 as the default and call K = 3 "very conservative" (D1).
  - Rousseeuw & Croux name cut-offs of 2.5 or 3.0 (D2).
  - The modified z-score rule flags values beyond 3.5 (D3). The Hampel identifier is usually run with 3 (D4).
  - Microservice RCA papers use the 3σ "N-Sigma" rule, where the multiplier is "an empirical parameter" (D46, D56).
  - Our reference K = 4 is stricter than every recommendation found. The grid {3, 4, 5} brackets them.
  - *general practice, for flagging outliers in one sample.*
- None of these sources sets K from a false-alarm rate over time. D4's h = 3 is a per-point rule in a moving window. For a
  detector that watches a stream, the quantity that matters is false alarms per hour (Q3). Recent benchmarks call thresholding a separate, unsolved problem (D16, D15).
  *No standard K for online detection.*
- The baseline size matters more than K:
  - At n = 4 points, 1.4826·MAD underestimates σ by about 27 % on average (correction factor 1.363, D5).
  - The MAD has only 37 % of the standard deviation's efficiency on normal data (D2), so it needs about 2.7× as many points for the same precision.
  - **Computation.** Two independent simulations agree. With the median and MAD taken from 4 baseline points, the K = 4 rule fires on about 5.7 % of new no-fault points (normal data) or about 10 % (latency-like lognormal data). With 3 points, the usual count at 0.05/s (`DECLARATION.md:83`, `detection_time.py` `MIN_BASELINE = 3`), the rates are 12 % and 16 %. The nominal rate is 0.003 %. At 20 points the normal-data rate is 0.25 %.
  - Control charts need 50–100 baseline samples before estimated limits behave like the true ones (D6, *one paper*).
  - Regression tools require at least 6 points (Chromium, D13) or 12 (Firefox's Perfherder, D10) on each side of a change. *tool-specific.*
- **Recommendation:**
  - Keep median/MAD and the K grid (D1, D2 support it).
  - **Change the baseline.** A MAD from 3–4 requests is too unstable to set a threshold (see the computation). Either pool no-fault time and pre-onset time per rate, posture and sensor, or set a minimum baseline (≥ 20 points) and score `—` below it.
  - The cost of the minimum: with onset at 60 s, a route sees about 600 / 60 / 12 / 3 pre-onset requests at 10 / 1 / 0.2 / 0.05 per s. A ≥ 20 minimum would therefore remove per-cell latency scoring at 0.2/s and 0.05/s, the two rates the sweep is about. Pooling avoids this.
  - Pooling changes the declaration. `research/traffic-sweep/readout-hotel-r3/SWEEP_ANALYSIS.md:176` records the pooled baseline as "not adopted (not in the declaration)". So this is a **user decision**.

**Q2. Floors: absolute or relative.**
- Four performance-regression tools combine a statistical gate with a relative-change gate, and a change must pass both.
  Three of them test first (Perfherder, Hunter, Kayenta). Chromium applies all its gates jointly: a change ≥ 2.5 SD, a
  steppiness ≥ 0.5 and a relative change ≥ 10 %. *tool-specific, but four tools agree.* The relative values:
  - 2 % is the Perfherder default, 5 % for a noisy suite and 0.25 % for memory (D9, D10).
  - 5 % in Hunter (D8).
  - 10 % in Chromium's perf dashboard (D13) and in Kayenta's documented example. Kayenta's default is no floor (D12).
- MongoDB dropped a static 10 % rule used on its own. It raised too many alerts on noisy tests and missed or
  delayed smaller changes (D7).
- Reported noise without any real change:
  - Run-to-run variation in MongoDB's performance tests is "less than 10%", with sensitive tests at "20% or more" (D7).
  - Hunter saw ±10 % in median latency on untuned hardware (D8).
  - *one paper each.*
- The SRE workbook's 2 %/5 %/10 % are shares of an error budget, not of baseline latency. Its latency SLOs are
  absolute (D11).
- The statistics standard: fix the smallest effect of interest before seeing the data, from an objective basis or a
  cost-benefit argument (D14). *general practice.*
- No source gives a relative floor for microservice latency detection. *No standard value.*
- **Recommendation (engineering default, per decision (l)):** floor = max(K·1.4826·MAD, r × baseline median, resolution floor).
  - r = 10 % as the reference, 5 % as a sensitivity arm.
  - Keep a small absolute floor on the value scale for measurement resolution. An example is the ledger's millisecond latency stamps; today's floor grid is {0.5, 1, 2} ms (`sweep_analysis.py:122`).
  - Hotel's Jaeger reporter flushes every 1 s. That limits the resolution of *observation time*, not of latency values, so it belongs to Q7 as a timing tolerance, not here.
  - 10 % matches the Chromium gate and the size of reported latency noise.
  - Write r into the descriptor before the next run.

**Q3. False-alarm calibration with few no-fault windows.**
- The field's measure is a rate in time: ARL0, or FAR per hour. The detector restarts after each alarm (D17, D18, D3).
  *general practice.*
- The standard design rule: fix the false-alarm rate first, then minimise the delay (D17, D18).
- "0 of 4 windows" cannot certify "≤ 5 %":
  - 0 of 4 has a 95 % upper bound of **52.7 %**.
  - Certifying 5 % needs **59** independent alarm-free windows (D21; **computation**). An earlier repo note gives "~24-58 no-fault cells" (`research/READING_20261003.md:81`). That range counts cells holding several windows each. 59 is the exact count of independent windows.
  - So G3 today is a screen, not a calibration.
- An OR of several rules fires more often than any one of them. Adding run rules to a 3σ chart cuts ARL0 from 371
  to about 92 points (D3). *general practice; the numbers are this chart's.* Our catch is an OR of a threshold, a run of 3, a
  median shift, `appear` and `absent`. Its false-alarm rate must be measured for the combination, not rule by rule.
- Sliding the detector over all no-fault time is what ARL0 means, so it is defensible for the point estimate.
  - The uncertainty has to respect dependence. Overlapping windows are not independent trials. Use a block bootstrap over whole cells (D23).
  - With 0 alarms in T hours, the exact 95 % upper bound is 3/T per hour (D21).
  - **Computation:** 4 no-fault cells × 180 s = 0.2 h gives a bound of 15 alarms per hour. Showing ≤ 1 per hour needs ≥ 3 alarm-free hours per rate.
- Adding the pre-onset parts of fault cells to the no-fault time is *my inference*. It holds only if pre-onset behaviour matches no-fault behaviour, which should be the case at the same posture and rate. Check this before pooling.
- Recent anomaly-detection benchmarks do not calibrate false alarms at all:
  - They score over all thresholds, or at the best threshold chosen on the test data (D16, D24).
  - Microservice benchmarks report F1 or NAB scores (D27, D28).
  - None of these yields a detection time under a false-alarm budget. *general practice in ML benchmarks, and not usable here.*
- Two exceptions do calibrate to a false-alarm budget:
  - A water-network placement paper sets each sensor's threshold from a false-alarm budget per unit time: "false positive events are not tolerated more than once every few months". It caps the whole placement with Σ f_i ≤ ρ, the sum of the per-sensor false-alarm rates of the chosen sensors (D29).
  - A software-performance paper sizes its detector to a false-alarm bound (D26).
  - *one paper each.*
- **Recommendation (user decision on the target value):** replace "0 of 4 windows" with a declared FAR per hour.
  - Estimate it over all no-fault time, plus pre-onset time, per rate and posture.
  - Report it with the exact upper bound.
  - Calibrate each sensor's combined rule to that FAR.
  - Report the placement-level FAR beside every placement score.

**Q4. Censoring: charging misses at the horizon.**
- This is exactly Leskovec et al. A miss has T = ∞ and costs π(∞). For detection time the penalty is min{t, Tmax},
  "the time horizon we consider (end of simulation / data set)" (D30). The water follow-up does the same (D31). *one
  paper plus its follow-up.*
- It equals the **restricted mean survival time** (RMST) at τ = 60 s, a standard survival measure (D34). Two
  conditions: τ is fixed in advance, and τ is the same for the ledger and for every sensor. *general practice in
  biostatistics.*
- D33 says censoring methods are valid only if the censoring is non-informative. A fixed hold set before the run, the same
  for every episode, should meet that condition, because the end of observation does not depend on the episode's outcome.
  *my inference.*
- The other convention exists:
  - The Battle of the Water Sensor Networks (BWSN) left misses out of its expected detection time and reported detection likelihood separately.
  - Its authors admit this biases the mean downward (D32).
  - They also note that charging misses makes a time objective chase detection likelihood (D32).
- A 2025 microservice benchmark reports time-to-detect without stating how misses enter (D35). *No single standard.*
- **Recommendation: keep.**
  - Name it "restricted mean time to detection at τ = 60 s".
  - Always print the detection fraction k/n beside it.
  - When misses are common, add the KM curve and the median.

**Q5. Selection with small n (leave-one-episode-out).**
- Select on 3 episodes and score on the 4th: the selection happens inside the cross-validation loop. That is the
  condition D37 names for an almost unbiased estimate of the selection procedure (D36, D37). It is not nested CV, which
  would need an inner tuning loop that is absent here. *general practice in ML evaluation.*
- The cost is variance:
  - Over-fitting in selection is worst with little data and many candidates (D36).
  - Leskovec et al. saw it in placement: greedy picked blogs that "just by chance" caught cascades. They fixed it by shrinking the candidate pool (D30). *one paper.*
- Recent work:
  - Probe selection holds out by time (D39).
  - D38 calls a labelled 20 % selection split "current practice" and uses it as its supervised baseline. Its own unsupervised surrogates use no labels. Among those surrogates, synthetic anomaly injection ranked best.
  - *one paper each.*
- Ties: none of the placement sources read gives a tie rule. ML comparisons split ties evenly between the two sides
  and give tied ranks the average rank (D40, D50). *no standard in placement.*
  - Today, selection breaks ties by sensor name (`SWEEP_ANALYSIS.md:180`). That is deterministic but arbitrary.
  - A win must be "strictly lower" than the ledger, so a tie with the ledger is already no win.
- **Computation:** with 4 paired episodes, no sign test or Wilcoxon test can reach p < 0.05. The smallest
  two-sided p is 0.125. P4's "≥ 3 of 4" majority has a one-sided sign-test p of 5/16 = 0.31. A "win" over 4
  episodes is descriptive.
- **Recommendation: keep LOO.**
  - Report only held-out scores.
  - Restrict the candidate pool before seeing the data (Leskovec's fix, D30). This changes P4a/P4b as declared (`DECLARATION.md:60-62`), so it is a **user decision**.
  - On a tie in selection, report the share of tied sensors that win, and how often selection tied, beside the recorded name-order result. For the Hotel pilot this is a variant, not a replacement. *my inference, by analogy with averaged ranks.*

**Q6. Probabilistic detection (Kalman, BOCPD, GP, DP).**
- Every probabilistic detector read gives a probability or a predictive density, not a time. Each paper that reports
  a detection adds a threshold:
  - Shiryaev: stop when the posterior probability of a change passes A. A = 1 − α bounds the false-alarm probability by α (D18).
  - A GP change-point model raises an alert when the change probability since the last alert exceeds 0.95 (D42).
  - BARO, on microservices, flags the step where the most probable run length drops (D46). BARO says it "does not require any user-defined thresholds". The hazard rate and the priors then do the threshold's job. *my inference.*
  - The sticky HDP model, a Dirichlet-process-based switching model, is scored by sweeping the threshold into a ROC curve (D44).
  - A Kalman filter turns data into innovations with a known variance, then runs CUSUM, GLR or χ² on them against a threshold h (D17).
  - Adams & MacKay's BOCPD itself defines no decision rule (D41).
  - *general practice.*
- So the user's "variance or probability instead of a binary catch" moves the threshold from the value scale to the
  probability scale. It does not remove it. It still has to be calibrated on no-fault data (Q3). *my inference, from the sources above.*
- Known costs:
  - BOCPD is "highly sensitive to hyper-parameter settings" (D42).
  - The standard version "mistakenly labels outliers as CPs" (change points) (D45).
  - GP change-point work mainly targets prediction; detection is "a natural byproduct" (D43).
  - The sticky HDP model is fitted offline with a Gibbs sampler (D44).
  - With 3–4 pre-onset requests, any model's prior will dominate its posterior. *my inference.*
- How it plugs into the Leskovec objective, which needs T(s, i):
  - (a) **Threshold the posterior.** This gives one T(s, i) per sensor and episode. The objective is unchanged. *my inference, consistent with D17, D18.*
  - (b) **Keep detection random.** Treat each sensor's detection as a probability or a random time. Maximise the expected penalty reduction.
    - Leskovec's co-authors already did this for water networks. A sensor's minimum detectable concentration is a random variable F_s, and the objective is the expected penalty reduction over the scenarios (D31).
    - Berry et al. add a detection probability per location and the probability that each sensor is the first to detect (D29).
    - The expectation of submodular functions is submodular, so greedy and CELF (cost-effective lazy forward selection, Leskovec et al.'s fast greedy) keep their guarantee (D31, D48, D49).
    - *general practice in this placement family.*
  - (c) **Fuse several sensors into one posterior.** A fused detector can fire before any single sensor, and then submodularity is not guaranteed. Information gain is not submodular in general (the XOR example). It is submodular when the sensors are conditionally independent given the hidden state (D47). *one paper, plus my inference for the detection objective.*
- **What the analysis already has, and what route (b) would add.** *my inference.*
  - Averaging over episodes is Leskovec's expectation over scenarios (D30, D31). Each episode is one scenario.
  - In Leskovec's objective, a set's time within an episode is the earliest of its sensors' times. That keeps the correlation between sensors that see the same fault. Set-level times and placements are not computed yet (`SWEEP_ANALYSIS.md:184`).
  - Berry's form (D29) states "We assume that sensor failures are independent". Applied to our data, it would throw that correlation away.
  - Route (b)'s extra ingredient is a per-sensor detection distribution P(T(s, i) ≤ t). The analysis does not compute one. It adds something only if a model gives it beyond the observed episodes, for example a calibrated posterior from route (a) or a curve of detection against fault size.
- **Recommendation:**
  - Keep the binary catch as primary.
  - Add a posterior-based detector (route a) as an exploratory arm. Calibrate it to the same FAR as the binary rules (Q3) and score it with the same objective.
  - Do not treat sensors as independent.
  - Route (c) is a separate objective (information), not detection time.
  - With 4 episodes, any estimated detection probability takes only the values 0, ¼, ½, ¾ or 1.

**Q7. When is detector A "faster" than detector B?**
- In change detection, delays are compared at the same false-alarm rate, or as delay-versus-ARL0 curves (D17, D18).
  Raw delays at different false-alarm rates are not comparable, because a lower threshold always buys speed.
  *general practice.*
- A recent result shows the trap: under lenient scoring, "even a random anomaly score can easily turn into a
  state-of-the-art" detector (D24).
- Over paired units:
  - Wilcoxon signed-rank for two detectors, with zero differences split evenly (D40).
  - Friedman then post-hoc tests for several (D50, D16).
  - *general practice in ML benchmarking.*
- A threshold picked from a grid after the fact is an "Oracle" result, reported apart from the pre-declared default
  (D50). Trivial baselines belong in every comparison: the "zero method" (D50), one-line detectors (D51), random
  scores (D24). *one paper each.*
- Time tolerances are benchmark-specific: 5 samples (D50), NAB windows (D19), the first k = 2 points (D25). *No
  standard margin for "faster".*
- **Recommendation (user decision, it changes P4's meaning):** "faster" = lower restricted mean at a matched FAR.
  - Both sides are calibrated to the same FAR on no-fault data.
  - Use a paired test over episodes × faults. It needs ≥ 6 paired units to reach p < 0.05 even with all wins (**computation**).
  - A tie is not a win, as today.
  - Report the reference K and the grid separately.
  - Add a random-score baseline.

**Q8. Calibration per system: generic parameters, a baseline run, or a calibration run.**
The user's question, in their words: "baseline performance: filter out noise from default system load / activities;
sensors have sensitivity different per microservice system; can we have generic parameters that get tuned based on
our baseline run and follow up (e.g. guided + chaos test) to see initial outliers and correlation".
- **There is no standard.** Microservice papers from 2023 to 2026 use three patterns. *no standard.*
  - (a) **A generic rule whose scale is learned from fault-free data of each system or run.** Examples: N-Sigma/3σ, P95, median and IQR, and SPOT, which fixes one risk level q for every stream and calibrates each stream on about 1000 initial points (D46, D55, D57, D60). Benchmarks run every method with its own paper's default hyperparameters (D54, D46).
  - (b) **Calibration with known faults, per system.**
    - Oxn, on our own OTel Demo, trains a classifier per fault on fault and non-fault data. It calls a fault "visible" at ≥ 0.7 test accuracy (D52).
    - Eadro and DiagFusion train supervised models per system, split by time, with the same fault types on both sides (D56, D57).
    - Transfer to another system is claimed only after 10 labelled examples per fault category in the target (D63).
  - (c) **Tuning per benchmark.** Fang et al. tune every model on their new benchmark (D55). TSB-AD holds out 15 % of each data set for tuning (D16).
- **Evidence on carrying parameters across systems:**
  - Default parameters are "not consistent across different datasets" (D62, a 2026 thesis).
  - Simple rules with a per-system scale match state-of-the-art RCA on four public benchmarks (D55).
  - No paper read shows a K or threshold carried unchanged to a new system and validated there.
- **Leakage.** Tuning on the same episodes that are scored is the textbook case (D59, categories L1.1 and L1.3).
  Tuning and testing on one system and one fault family limits the claim to that distribution (D59, L3.2). *general
  practice.*
- Chaos engineering's baseline is a control group running **at the same time**, judged on a steady-state output, not an
  earlier calibration run (D61). *one paper.*
- "Noise from default system load":
  - Background activity belongs in the fault-free baseline, so a fault-free run calibrates it away.
  - That only works if the baseline is long enough to contain it. Example: Hotel's gRPC GoAway template recurs every 79–80 s (`research/sensor-validity/VALIDITY.md:209`). A per-cell pre-onset window shorter than that makes it look like `appear`, and a short window also underestimates the largest gap that `absent` relies on. *my inference.*
  - Correlation between sensors can be learned from the same baseline (BARO's multivariate BOCPD, D46). A fused rule, though, leaves the submodular objective (Q6 c).
- **Recommendation** (engineering defaults, except where marked):
  1. Freeze the generic part before any fault cell, identical on all three systems: rule set, K, relative floor r, run length, `appear`/`absent` definitions, target FAR.
  2. Per system, fit only the scale (median, MAD, the per-sensor FAR calibration, the baseline vocabulary of templates and operations), and only from fault-free data. BARO reports that N-Sigma's root-cause ranking drops when the detected time is late, and attributes this, hedged as "might stem from", to anomalous points entering the normal period (D46).
  3. A guided or chaos run with known faults may calibrate sensitivity (planted shifts, MDE80). Its fault types, sizes or episodes must not be scored later, and it is reported as calibration, never as evidence. Whether to spend runs on it is a **user decision** (budget).
  4. Keep one system untouched. The project's earlier split (user, 2026-09-15) was TeaStore + Hotel to tune, OTel to test, and Online Boutique held out. Any setting changed after looking at OTel fault cells ends OTel's role as a test.
  5. For each system, report which parameters were fitted (scale) and which were generic. Cross-system claims cover only the generic part.
- Oxn's "visible" builds in per-fault tuning, so compare its contrasts with ours, not its labels. *one paper.*

---

## 2. Table: current choice vs literature

"keep": no change. "change": my recommendation, which I can make as an engineering default or as an added report. "user decision": it changes a frozen definition from the declaration, or spends runs.

| # | current choice | literature standard | change? | sources |
|---|---|---|---|---|
| 1 | K = 4 (4·1.4826·MAD), grid {3, 4, 5} | 2.5 default, 3 "very conservative", 3.5 modified z; for online detection no K, calibrate to ARL0 | **keep** as engineering default; K stops being the deciding knob once Q3 is done | D1–D4, D16, D17 |
| 2 | baseline = the cell's own pre-onset window (~3 requests at 0.05/s; `MIN_BASELINE = 3`) | ≥ 6 to 12 points per side (tools); 50–100 baseline samples (SPC); MAD needs ~2.7× the SD's sample size | **user decision**: pool no-fault + pre-onset time per rate × posture × sensor, or a minimum n ≥ 20 with `—` below | D2, D5, D6, D10, D13 |
| 3 | catch = threshold OR run of 3 OR median shift OR `appear` OR `absent` | run rules raise false alarms (ARL0 371 → 92); calibrate the combined rule | **change** (report now): FAR of the OR, not of each rule; using it as the gate is part of row 5 (**user decision**) | D3, D17 |
| 4 | absolute floor grid {0.5, 1, 2} ms, reference 1 ms (latency); per resource (metrics) | statistical gate + relative gate: 2 %, 5 %, 10 %; set SESOI in advance | **change** (decision l): max(K·MAD, 10 % of baseline median, resolution floor); 5 % arm | D7–D14 |
| 5 | G3: fires in ≤ 5 % of 4 windows, so 0/4 | ARL0 / FAR per time; 0/n has upper bound 1 − 0.05^(1/n); 59 windows for 5 % | **user decision** (target FAR value); method: rate per hour + exact bound | D17, D18, D21 |
| 6 | one pseudo window per no-fault cell | slide over all in-control time; dependence-aware interval (block bootstrap by cell) | **change** (report now); as the gate, part of row 5 (**user decision**); pre-onset time added only after a check | D17, D21, D23 |
| 7 | placement-level false alarms declared as reported beside the score (`DECLARATION.md:76-77`); P4 rows carry the pool's false alarms; no bound; placements not yet computed | Σ f_i s_i ≤ ρ over the placement | **keep** reporting; a Σ bound inside the objective would be a **user decision** | D29 |
| 8 | misses charged at the 60 s hold | Leskovec: min{t, Tmax}; = RMST at τ; BWSN excluded misses (biased) | **keep**; rename to RMST at 60 s; print k/n; KM curve when misses are common | D30–D35 |
| 9 | LOO over 4 episodes, lowest mean over 3 | selection inside the CV loop is almost unbiased but high-variance; shrink the pool | **keep** LOO and held-out scores; **user decision**: restrict the candidate pool (changes P4a/P4b) | D30, D36–D39 |
| 10 | selection ties broken by sensor name; a win must be strictly lower | tied ranks averaged, tied matches split evenly | **change** (added report): the win share across tied sensors and the tie count, beside the recorded result; "strictly" already makes a tie no win | D40, D50 |
| 11 | per fold, win = strictly lower than the ledger; P4 holds if a sensor wins in ≥ 3 of 4 paired episodes (`DECLARATION.md:60`) | compare at matched FAR; paired test; Oracle vs default; trivial baselines | **user decision** (redefines P4) | D17, D18, D24, D40, D50, D51 |
| 12 | probabilistic detection (the repo's dimension "D3", not source D3 here) not computed (`SWEEP_ANALYSIS.md:184`) | posterior → time by a threshold; expected objective over scenarios stays submodular; fusion can break it | **keep** binary as primary; add a posterior detector at matched FAR as exploratory (route a); the episode mean is Leskovec's scenario expectation, the per-sensor distribution of route (b) is not computed | D17, D18, D29, D31, D41–D49 |
| 13 | scale from each cell's pre-onset window; K and floors generic; no declared rule for what may be tuned on which system | no standard; (a) generic rule + per-system scale from fault-free data, (b) known-fault calibration (claims then hold for that system only), (c) a held-out tuning split | **change**: declare generic vs fitted; fit only on fault-free data; nothing tuned on OTel fault cells. **user decision**: spend runs on a guided/chaos calibration set | D16, D46, D52–D64 |
| 14 | `appear` / `absent` against the cell's own short pre-window | background activity is calibrated on fault-free data (pattern a) | **user decision** (with row 2): baseline vocabulary and largest gap from pooled fault-free time (*my inference*) | D46, D55, D60 |

---

## 3. Sources

Accessed 2026-10-04 unless stated. "OA" = an open-access copy, which is the one that was read unless noted.
Quotes are verbatim. Local text copies sit in the session scratchpad and are not kept.

### Q1 Robust thresholds

**D1** Leys, Ley, Klein, Bernard, Licata (2013). *Detecting outliers: Do not use standard deviation around the mean,
use absolute deviation around the median.* J. Experimental Social Psychology 49(4), 764–766.
DOI 10.1016/j.jesp.2013.03.013 (verified). OA: https://dipot.ulb.ac.be/dspace/bitstream/2013/139499/1/Leys_MAD_final-libre.pdf.
BibTeX `leys2013detecting`. Read: all 3 pages.
- "we strongly recommend the median plus or minus 2.5 times the MAD method for outlier detection."
- "Miller (1991) proposes the values of 3 (very conservative), 2.5 (moderately conservative) or even 2 (poorly conservative)."
- "Usually, b = 1.4826, a constant linked to the assumption of normality of the data, disregarding the abnormality induced by outliers"
- Says: K = 2.5 by default, chosen and justified in advance. It also says "the MAD is totally immune to the sample
  size". D2 and D5 contradict that for bias and precision at small n.

**D2** Rousseeuw, Croux (1993). *Alternatives to the Median Absolute Deviation.* J. American Statistical Association
88(424), 1273–1283. DOI 10.1080/01621459.1993.10476408 (verified).
OA: https://wis.kuleuven.be/stat/robust/papers/publications-1993/rousseeuwcroux-alternativestomedianad-jasa-1993.pdf (scan, read via OCR).
BibTeX `rousseeuw1993alternatives`. Read: §1, §2, Tables 1–2.
- "we need to set b = 1.4826"
- "statistic exceeds a certain cutoff (say, 2.5 or 3.0)"
- "the MAD is only 37% efficient"
- Says: the MAD has a 50 % breakdown point. It is biased low in small samples (Table 1: mean MAD 0.911 at n = 10,
  0.959 at n = 20, for σ = 1).

**D3** NIST/SEMATECH *e-Handbook of Statistical Methods*: §1.3.5.17 "Detection of Outliers" (reports Iglewicz &
Hoaglin), §6.3.2 and §6.3.2.3.1 (control charts, WECO rules). DOI 10.18434/M32189 (verified, DataCite: "NIST/SEMATECH
e-Handbook of Statistical Methods (NIST Handbook 151)"). OA: https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h.htm,
https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc32.htm, …/pmc3231.htm. BibTeX `nist2012handbook`.
- "These authors recommend that modified Z-scores with an absolute value of greater than 3.5 be labeled as potential outliers."
- "you will have "false alarms" every 371 points on the average"
- "Adding the WECO rules increases the frequency of false alarms to about once in every 91.75 points, on the average"
- Says: the modified z-score is 0.6745·(x − median)/MAD, which is K = 3.5 in our units. CUSUM charts are designed
  from a target in-control ARL0.

**D4** Wicklin (2021). *The Hampel identifier: Robust outlier detection in a time series.* SAS blog "The DO Loop",
2021-06-01. Practitioner source. DOI none. URL: https://blogs.sas.com/content/iml/2021/06/01/hampel-filter-robust-outliers.html.
BibTeX `wicklin2021hampel`. Read: whole post.
- "Most practitioners use h=3, but you can use higher values to identify more extreme outliers."
- Not read: Hampel 1974 and 1985, Davies & Gather 1993, Pearson 2002 (all paywalled). The Hampel identifier rests
  on this practitioner source only.

**D5** Akinshin (2022). *Finite-sample bias-correction factors for the median absolute deviation based on the
Harrell-Davis quantile estimator and its trimmed modification.* arXiv 2207.12005. DOI 10.48550/arXiv.2207.12005
(verified). OA: https://arxiv.org/pdf/2207.12005. BibTeX `akinshin2022finite`. Read: §1, §2.2.
- "However, when the sample size is small, the usage of C∞ produces a biased estimator."
- "For n ≤ 9, the approximated values of bn were defined as presented in Table 1."
- Says: it reproduces the Croux–Rousseeuw factors b_n (n = 4: 1.363; n = 5: 1.206), with b_n ≈ n/(n − 0.8) above n = 9.

**D6** Knoth (2021). *Controlling the EWMA S² control chart false alarm behavior when the in-control variance level
must be estimated.* arXiv 2101.04011. DOI 10.48550/arXiv.2101.04011 (verified). OA: https://arxiv.org/pdf/2101.04011.
BibTeX `knoth2021controlling`. Read: §1, results around Figs. 5–8.
- "Based on the profiles in Figure 7, we would recommend phase I sizes of at least 100."
- "the smaller the phase size m, the more likely the very early false alarms."
- "From sizes m = 50 on, the resulting limits on the control chart device in use would not really differ from the ideal case"
- Says: m counts baseline subgroups of size 5. The paper points to Jensen et al. 2006 for a survey (not read).

### Q2 Floors

**D7** Daly, Brown, Ingo, O'Leary, Bradford (2020). *The Use of Change Point Detection to Identify Software
Performance Regressions in a Continuous Integration System.* ICPE 2020, 67–75. DOI 10.1145/3358960.3375791 (verified).
OA: https://arxiv.org/pdf/2003.00584. BibTeX `daly2020use`. Read: §1, §1.1, §2, §3.
- "Using a static threshold (e.g., 10%) led to a lot of alerts for changes on noisy tests."
- "At the same time it would either miss real changes that were less than the threshold, or detect the smaller changes at some later time (when the change plus the noise crossed the threshold)."
- "In most of our tests the worst case run to run variation level is currently less than 10%, but some sensitive tests can fluctuate as much as 20% or more over the course of a small numbers of runs."
- Says: MongoDB replaced the static % rule with E-divisive change points plus a significance cut. Magnitude is used
  only to rank alerts.

**D8** Fleming, Kołaczkowski, Kumar, Das, McCarthy, Pattabhiraman, Ingo (2023). *Hunter: Using Change Point
Detection to Hunt for Performance Regressions.* ICPE 2023, 199–206. DOI 10.1145/3578244.3583719 (verified; the PDF
itself prints a template placeholder DOI). OA: https://arxiv.org/pdf/2301.03034 (arXiv DOI 10.48550/arXiv.2301.03034,
verified). BibTeX `fleming2023hunter`. Read: §3, §5.3.
- "we filter out change points that show a small relative change, e.g. change points where the difference in metric value is below 5%."
- "This relative threshold acts as a filter to discard change points that are not actionable"
- "Changes of +- 10% for the median latency were typical."
- Says: a t-test (usually p < 0.05) comes first, then the 5 % filter. The ±10 % is noise on untuned hardware with no real change.

**D9** Mozilla. *Performance Sheriffing* (Firefox Source Docs). Tool-specific. DOI none.
URL: https://firefox-source-docs.mozilla.org/testing/perfdocs/perf-sheriffing.html. BibTeX `mozilla2026perfsheriffing`.
- "Talos, Browsertime, Build Metrics >= 2%"
- "We also adjust the threshold per test, the default is 2%, but for Dromaeo it is 5%."
- Says: memory tests (AWSY) alert at ≥ 0.25 %. An alert needs 12 future data points.

**D10** Besbes, Costa, Mujahid, Mierzwinski, Castelluccio (2025). *A Dataset of Performance Measurements and Alerts
from Mozilla (Data Artifact).* ICPE 2025 Companion, 16–20. DOI 10.1145/3680256.3721973 (verified).
OA: https://arxiv.org/pdf/2503.16332. BibTeX `besbes2025dataset`. Read: §2.
- "In case the T-test shows a significant change detected by comparing it to a fixed threshold, Perfherder proceeds with measuring the change magnitude between both measurement groups, and if it surpasses a certain threshold, an alert is triggered"
- Says: the t-test compares at least 12 earlier revisions with the new one plus up to 11 later ones.

**D11** Google. *The Site Reliability Workbook*, ch. 5 "Alerting on SLOs". DOI none.
URL: https://sre.google/workbook/alerting-on-slos/. BibTeX `google2018alerting`. Read: whole chapter.
- "We recommend 2% budget consumption in one hour and 5% budget consumption in six hours as reasonable starting numbers for paging, and 10% budget consumption in three days as a good baseline for ticket alerts."
- "For example, if a system receives 10 requests per hour, then a single failed request results in an hourly error rate of 10%."
- Says: the percentages are shares of an error budget. Latency SLOs are absolute (100 ms at p90, 200 ms at p99 in
  its example). At low traffic it suggests synthetic traffic or grouping services.

**D12** Spinnaker / Kayenta canary analysis docs. Tool-specific. DOI none.
URLs: https://raw.githubusercontent.com/spinnaker/kayenta/master/docs/canary-config.md and
https://spinnaker.io/docs/guides/user/canary/judge/. BibTeX `spinnaker2026kayenta`.
- "Defaults to 1. The multiplier increase that must be met for the metric to fail. This example makes the metric fail when the metric has increased 10% from the baseline." (`allowedIncrease`, example 1.1)
- "Important: Effect size thresholds are secondary gates. A metric must first show statistical significance before the effect size is checked."

**D13** Chromium catapult perf dashboard, `dashboard/dashboard/common/defaults.py`. Tool-specific. DOI none.
URL: https://chromium.googlesource.com/catapult/+/HEAD/dashboard/dashboard/common/defaults.py. BibTeX `chromium2026catapult`.
- "MIN_RELATIVE_CHANGE = 0.1", "MULTIPLE_OF_STD_DEV = 2.5", "MIN_SEGMENT_SIZE = 6"
- Says: a change point must pass every gate. The gates are ≥ 6 points per side, a relative median change ≥ 10 %, a change ≥ 2.5 SD, and an absolute change ≥ 0, which is no absolute floor.

**D14** Lakens, Scheel, Isager (2018). *Equivalence Testing for Psychological Research: A Tutorial.* Advances in
Methods and Practices in Psychological Science 1(2), 259–269. DOI 10.1177/2515245918770963 (verified).
OA: https://osf.io/download/v3zkt/ (PsyArXiv preprint). BibTeX `lakens2018equivalence`. Read: the section on justifying the SESOI.
- "In lieu of objective justifications, the SESOI should ideally be based on a cost-benefit analysis."
- "The SESOI is thus independent of the outcome of the study, and should be determined before looking at the data."

**D15** Müller (2025). *Open Challenges in Time Series Anomaly Detection: An Industry Perspective.* arXiv 2502.05392.
DOI 10.48550/arXiv.2502.05392 (verified). OA: https://arxiv.org/pdf/2502.05392. BibTeX `muller2025open`. Read: §1, §5.3.
- "Given the usual unsupervised nature of the problem, even with human intervention, it’s unclear how to set a threshold effectively."
- "evaluation in benchmarks often uses an ideal threshold that not only requires knowledge of the full time series, but also of the ground truth"

**D16** Liu, Paparrizos (2024). *The Elephant in the Room: Towards A Reliable Time-Series Anomaly Detection Benchmark*
(TSB-AD). NeurIPS 37 Datasets & Benchmarks, 108231–108261. DOI 10.52202/079017-3437 (verified).
OA: https://proceedings.neurips.cc/paper_files/paper/2024/file/c3f3c690b7a99fba16d0efd35cb83b2c-Paper-Datasets_and_Benchmarks_Track.pdf.
BibTeX `liu2024elephant`. Read: §2 (point-adjust critique), §4.3, §5.2.1.
- "we treat the threshold setting on the anomaly score as an orthogonal problem to our primary focus of model performance evaluation."
- "Our approach either utilizes measures that summarize performance across all possible thresholds or iterates over these thresholds to identify the optimal setting."
- "the random score achieves a ranking of 26 under the PA-F1 measure."
- "For both TSB-AD-U and TSB-AD-M, we allocate 15% of the data from each dataset to construct a hyperparameter tuning set." (Q8)
- "In addition, comparing methods with optimized hyperparameters on a single synthetic dataset could lead to misleading conclusions." (Q8)
- Says: models are compared by Friedman and Nemenyi tests on ranks.

### Q3 False alarms

**D17** Basseville, Nikiforov (1993). *Detection of Abrupt Changes: Theory and Application.* Prentice-Hall. DOI none
(the free reprint prints none). OA: https://people.irisa.fr/Michele.Basseville/kniga/kniga.pdf.
BibTeX `basseville1993detection`. Read: §1.1, §1.4.2.1, §4.4.1 (pp. 151–153), §5.1.1 (pp. 159–160), the Fig. 5.3
comparison, §7.2.4 (pp. 234–241).
- "Usually the overall criterion consists in minimizing the delay for detection for a fixed mean time between false alarms."
- "Let ta be the alarm time at which a detection occurs; ta is a stopping time"
- "we solve the additive change detection problem by first using the transformation from observations to innovations, which can be achieved with the aid of a Kalman filter, and then solving the relevant corresponding basic problem."
- Says:
  - Mean time between false alarms = E(t_a) under no change, with a restart after each alarm.
  - For a comparison, each detector's parameters are tuned for a given false-alarm time and change size, and "the resulting mean delays for detection are compared".
  - Kalman innovations are N(0, Σ_k) before a change. CUSUM or GLR on them stops at the first k with g_k ≥ h.

**D18** Veeravalli, Banerjee (2012/2014). *Quickest Change Detection.* Read: arXiv 1210.5552 v1,
DOI 10.48550/arXiv.1210.5552 (verified). Published: Academic Press Library in Signal Processing vol. 3, 209–255,
DOI 10.1016/B978-0-12-411597-2.00006-0 (verified, not read). OA: https://arxiv.org/pdf/1210.5552.
BibTeX `veeravalli2014quickest`. Read: §I, §III (Shiryaev, Thm 3.1, PFA bound), §IV (FAR, Lorden, Pollak).
- "Without a prior on the change point, a reasonable measure of false alarms is the mean time to false alarm, or its reciprocal, which is the false alarm rate (FAR)"
- "the value of the Shiryaev statistic stays close to zero before the change point, and grows up to one after the change point. The change is detected by using a threshold of 0.8."
- "the formulations of Lorden and Pollak are equivalent for low FAR constraints"
- Says: the Shiryaev stopping time is τ = inf{n : p_n ≥ A}, where p_n is the posterior probability that the change has
  happened. A = 1 − α gives PFA ≤ α ("would ensure PFA(τS ) ≤ α."). Lorden and Pollak minimise the delay subject to
  FAR ≤ α.

**D19** Lavin, Ahmad (2015). *Evaluating Real-Time Anomaly Detection Algorithms – the Numenta Anomaly Benchmark.*
IEEE ICMLA 2015, 38–44. DOI 10.1109/ICMLA.2015.141 (verified). OA: https://arxiv.org/pdf/1510.03336.
BibTeX `lavin2015evaluating`. Read: scoring sections, Figs. 2–3. The weights come from the repository file
`config/profiles.json` (tool-specific).
- "If there are multiple detections within a window, the earliest detection is given credit and counted as a true positive."
- "The standard profile assigns TPs, FPs, and FNs with relative weights (tied to the window size) such that random detections made 10% of the time would get a zero final score on average."
- "These two profiles are somewhat arbitrary but designed to be illustrative of algorithm behavior."
- Says: false-positive weight 0.11 (standard) or 0.22 (low-FP profile). Window = 10 % of the file / number of anomalies.

**D20** Tatbul, Lee, Zdonik, Alam, Gottschlich (2018). *Precision and Recall for Time Series.* NeurIPS 2018.
arXiv DOI 10.48550/arXiv.1803.03639 (verified). OA: https://arxiv.org/pdf/1803.03639. BibTeX `tatbul2018precision`.
Read: §2, §3.
- "the NAB scoring model remains point-based in nature and has a fixed bias (early detection)"
- "front-end bias is preferable in scenarios where early response is critical, such as cancer detection or real-time systems."

**D21** Hanley, Lippman-Hand (1983). *If Nothing Goes Wrong, Is Everything All Right? Interpreting Zero Numerators.*
JAMA 249(13), 1743–1745. DOI 10.1001/jama.1983.03330370053031 (verified).
OA: https://jhanley.biostat.mcgill.ca/c607/ch08/zero_numerator.pdf. BibTeX `hanley1983nothing`. Read: whole paper.
- "we can be 95% confident that the chance of this event is at most three in n (ie, 3/n)."
- "below 30, it slightly overestimates the risk"
- Says: the exact bound is 1 − 0.05^(1/n). The Poisson form exp(−n·risk) = 0.05 gives the same 3/n, so the rule
  also covers a rate per unit time.

**D22** Angelopoulos, Bates. *A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty
Quantification.* arXiv 2107.07511 v6 (2022). DOI 10.48550/arXiv.2107.07511 (verified). Published as *Conformal
Prediction: A Gentle Introduction*, Foundations and Trends in ML 16(4), 2023, DOI 10.1561/2200000101 (verified, not
read). OA: https://arxiv.org/pdf/2107.07511. BibTeX `angelopoulos2023conformal`. Read: §1, §3.2, §4.4, the
time-series example.
- "In particular, we will guarantee that it does not return too many false positives."
- "Note that these data points are not exchangeable or i.i.d.; adjacent data points will be correlated."
- "hence our rough guideline of choosing about 1000 calibration points."
- Says: the threshold is the ⌈(n+1)(1 − α)⌉-th smallest calibration score, which is infinite unless α ≥ 1/(n+1).
  So n = 4 cannot go below α = 0.2, and α = 0.05 needs n ≥ 19.

**D23** Härdle, Horowitz, Kreiss (2003). *Bootstrap Methods for Time Series.* International Statistical Review 71(2),
435–459. DOI 10.1111/j.1751-5823.2003.tb00485.x (verified; the 2001 working paper was read).
OA: https://users.ssc.wisc.edu/~behansen/718/HardleHorowitzKreiss.pdf. BibTeX `hardle2003bootstrap`. Read: abstract, §3.
- "The blocks may be non-overlapping (Hall 1985, Carlstein 1986) or overlapping (Hall 1985, Künsch 1989, Politis and Romano 1993)."
- "the performance of the bootstrap as measured by the rate of convergence of estimation errors tends to be poorer with time series than with random samples."

**D24** Kim, Choi, Choi, Lee, Yoon (2022). *Towards a Rigorous Evaluation of Time-Series Anomaly Detection.* AAAI 36(7),
7194–7201. DOI 10.1609/aaai.v36i7.20680 (verified). OA: https://arxiv.org/pdf/2109.05257. BibTeX `kim2022towards`.
Read: abstract, §3, §4.1–4.2, conclusion.
- "even a random anomaly score can easily turn into a state-of-the-art TAD method."
- "existing TAD methods set the threshold after investigating the test dataset or simply use the optimal threshold that yields the best F1."
- "If the performance of the new TAD model does not exceed this baseline, the effectiveness of the model should be reexamined."

**D25** Sørbø, Ruocco (2023). *Navigating the metric maze: a taxonomy of evaluation metrics for anomaly detection in
time series.* Data Mining and Knowledge Discovery 38(3), 1027–1068. DOI 10.1007/s10618-023-00988-8 (verified).
OA: https://arxiv.org/pdf/2303.01272. BibTeX `sorbo2023navigating`. Read: §4, the delay-thresholded metrics.
- "In these cases, detecting the anomaly at a late stage is of no value since it is too late to rectify the problem."
- "a GT anomaly is only considered detected if an anomaly is predicted within the first k time steps of the anomaly."

**D26** Gonçalves, Menasché, Avritzer, Antunes, Vieira (2020). *A Model-Based Approach to Anomaly Detection Trading
Detection Time and False Alarm Rate.* arXiv 2006.08811. DOI 10.48550/arXiv.2006.08811 (verified).
OA: https://arxiv.org/pdf/2006.08811. BibTeX `goncalves2020model`. Read: abstract, §III, §VI.
- "what is the smallest bucket depth to produce a false alarm probability upper bounded by a given threshold?"
- "The number of samples collected until absorption accounts for a tradeoff between the mean time until (a) a false alarm, in the absence of anomalies, and (b) detection, in the presence of an anomaly."

**D27** Sun et al. (2024). *A Scenario-Oriented Benchmark for Assessing AIOps Algorithms in Microservice Management*
(MicroServo). arXiv 2407.14532. DOI 10.48550/arXiv.2407.14532 (verified). OA: https://arxiv.org/pdf/2407.14532.
BibTeX `sun2024scenario`. Read: §II-A, evaluation metrics.
- "We provide three common evaluation metrics for anomaly detection algorithms: Point-based [9], Range-based [9], Eventbased [9]"

**D28** Islam, Rakha, Pourmajidi, Sivaloganathan, Steinbacher, Miranskyy (2025). *Anomaly Detection in Large-Scale
Cloud Systems: An Industry Case and Dataset.* ICSE-SEIP 2025, 377–388. DOI 10.1109/ICSE-SEIP66354.2025.00039 (verified).
OA: https://arxiv.org/pdf/2411.09047. BibTeX `islam2025anomaly`. Read: evaluation metrics, anomaly timing.
- "relying solely on these point-based metrics is not ideal because detecting just one instance within an anomaly window is often sufficient in practice [23]."
- "The start time was set 20 minutes before the issue was reported"

**D29** Berry, Carr, Hart, Leung, Phillips, Watson (2006). *On the Placement of Imperfect Sensors in Municipal Water
Networks.* Water Distribution Systems Analysis Symposium 2006 (Sandia SAND2006-3463C). DOI 10.1061/40941(247)129
(verified). OA: https://www.osti.gov/servlets/purl/1264620. BibTeX `berry2006placement`. Read: all 13 pages.
- "A point on the ROC curve is determined only after an event detection threshold has been set."
- "Let xaj be the probability that a sensor placed at junction j is the first to detect the contamination scenario."
- "Finally, let q denote a “dummy” location that corresponds to failed detection of contamination scenario a. The impact daq is defined as the total impact of contamination scenario a if it is not detected before t∗ ."
- "We can enforce a global limit on the false positive rate."
- Says:
  - "That is, we assume that false positive events are not tolerated more than once every few months." At such thresholds the paper accepts sensitivities "in the 50% range or even lower".
  - Impact becomes an expected impact over which sensor detects first.
  - The placement-level constraint is Σ f_i s_i ≤ ρ.

### Q4 Censoring

**D30** Leskovec, Krause, Guestrin, Faloutsos, VanBriesen, Glance (2007). *Cost-effective Outbreak Detection in
Networks.* KDD 2007, 420–429. DOI 10.1145/1281192.1281239 (verified).
OA: http://reports-archive.adm.cs.cmu.edu/anon/ml2007/CMU-ML-07-111.pdf (tech report version, read).
BibTeX `leskovec2007cost`. Read: §2.2–2.3 (pp. 4–5), §5.7 (p. 16), §7.1 (p. 21).
- "We also set T (i, ∅) = ∞, and set πi (∞) to some maximum penalty incurred for not detecting event i."
- "Hence, πi (t) = min{t, Tmax }, where Tmax is the time horizon we consider (end of simulation / data set)."
- "As Fig. 8(a) shows, CELF overfits when evaluated on the future data, i.e., it selects small blogs with very few posts that just by chance participate in cascades, and then these blogs do not generalize well for the second half of the year."
- Says: selection was validated on the next 6 months of data. The fix for the overfitting was to admit only blogs with
  at least one post per day.

**D31** Krause, Leskovec, Guestrin, VanBriesen, Faloutsos (2008). *Efficient Sensor Placement Optimization for
Securing Large Water Distribution Networks.* J. Water Resources Planning and Management 134(6), 516–526.
DOI 10.1061/(ASCE)0733-9496(2008)134:6(516) (verified). OA: https://las.inf.ethz.ch/files/krause08efficient.pdf (author
manuscript). BibTeX `krause2008efficient`. Read: problem statement, robustness section, implementation.
- "If sensor s never detects intrusion i, we set T (s, i) = ∞."
- "if we want to minimize the time to detection, we would choose πi (t) = t, and πi (∞) = tmax , where tmax is a large number, e.g., the number of time steps until the end of the simulation."
- "Similarly, we could use a continuous random variable Fs which models the minimum contaminant concentration required for detecting a contamination at location [s]" (p. 15; a page break splits the sentence)
- "is an expectation of the penalty reduction achieved for placement A where all possible failure scenarios are considered. Since the class of submodular functions is closed under non-negative linear combinations, we can see that R(A) is again a nondecreasing submodular function."
- Says: a sensor that fails, or one whose detection threshold is random, enters Leskovec's objective as an expectation
  over scenarios. Each scenario scores only the working (or triggered) sensors.

**D32** Ostfeld, Uber, Salomons, Berry, Hart, Phillips, Watson, … Krause, Leskovec, … (2008). *The Battle of the
Water Sensor Networks (BWSN): A Design Challenge for Engineers and Algorithms.* J. Water Resources Planning and
Management 134(6), 556–568. DOI 10.1061/(ASCE)0733-9496(2008)134:6(556) (verified).
OA: https://cs.stanford.edu/people/jure/pubs/bwsn-jwrpm09.pdf. BibTeX `ostfeld2008battle`. Read: pp. 557–558, 563–566.
- "Since undetected events had no detection times, they were not included in the analysis."
- "As such, the random variables were in fact truncated (rather than censored), introducing an even greater downward bias in the computed values of their expectations." (The text extraction garbles the parentheses; the passage was checked in two parts.)
- "Optimizing for minimum time to detection in the presence of nondetections means avoiding nondetections at all costs, and results in sensor placements that are directly correlated with those optimizing the number of failed detections"
- Also on p. 566: "In reality, the correct functioning of sensors is not guaranteed; both false positive and false negative rates need to be considered."

**D33** Clark, Bradburn, Love, Altman (2003). *Survival Analysis Part I: Basic concepts and first analyses.* British J.
Cancer 89(2), 232–238. DOI 10.1038/sj.bjc.6601118 (verified). OA: https://pmc.ncbi.nlm.nih.gov/articles/PMC2394262/.
BibTeX `clark2003survival`. Read: censoring, Kaplan–Meier, uninformative censoring.
- "Such censored survival times underestimate the true (but unknown) time to event."
- "The survival probability can be estimated nonparametrically from observed survival times, both censored and uncensored, using the KM (or product-limit) method"
- "Standard methods used to analyse survival data with censored observations are valid only if the censoring is ‘noninformative’."

**D34** Royston, Parmar (2013). *Restricted mean survival time: an alternative to the hazard ratio for the design and
analysis of randomized trials with a time-to-event outcome.* BMC Medical Research Methodology 13, 152.
DOI 10.1186/1471-2288-13-152 (verified). OA: https://pmc.ncbi.nlm.nih.gov/articles/PMC3922847/.
BibTeX `royston2013restricted`. Read: abstract, background, methods (RMST, choice of t*).
- "of a random variable T is the mean of the survival time X = min( T , t ∗ ) limited to some horizon t ∗ > 0."
- "The restricted mean is a measure of average survival from time 0 to a specified time point, and may be estimated as the area under the survival curve up to that point."
- "The primary estimate of the RMST is specifically aligned to a chosen t ∗ and this must be made explicit."

**D35** Chen, Shetty, Somashekar, Ma, Simmhan, Mace, Bansal, Wang, Rajmohan (2025). *AIOpsLab: A Holistic Framework to
Evaluate AI Agents for Enabling Autonomous Clouds.* arXiv 2501.06706. DOI 10.48550/arXiv.2501.06706 (verified).
OA: https://arxiv.org/pdf/2501.06706. BibTeX `chen2025aiopslab`. Read: §3.2, §3.4, Table 4.
- "is the time elapsed from the occurrence of a fault to its detection" (on Time-to-Detect, TTD)
- Says: accuracy and mean time are reported side by side. How undetected faults enter the TTD mean is not stated.

### Q5 Selection with small n

**D36** Cawley, Talbot (2010). *On Over-fitting in Model Selection and Subsequent Selection Bias in Performance
Evaluation.* JMLR 11, 2079–2107. DOI none (JMLR assigns none). OA: https://jmlr.org/papers/volume11/cawley10a/cawley10a.pdf.
BibTeX `cawley2010over`. Read: abstract, §4.1, §4.4, §5.1.
- "over-fitting in model selection is likely to be most severe when the sample of data is small and the number of hyper-parameters to be tuned is relatively large."
- "For very small data sets, where the problem of over-fitting in both learning and model selection is greatest, the preferred approach would be to eliminate model selection altogether and opt for a fully Bayesian approach, where the hyper-parameters are integrated out rather than optimised"

**D37** Varma, Simon (2006). *Bias in error estimation when using cross-validation for model selection.* BMC
Bioinformatics 7, 91. DOI 10.1186/1471-2105-7-91 (verified). OA: https://pmc.ncbi.nlm.nih.gov/articles/PMC1397873/.
BibTeX `varma2006bias`. Read: abstract, background, results.
- "We show that using CV to compute an error estimate for a classifier that has itself been tuned using CV gives a significantly biased estimate of the true error."
- "A nested CV procedure provides an almost unbiased estimate of the true error."
- "However, CV methods are proven to be unbiased only if all the various aspects of classifier training takes place inside the CV loop."

**D38** Goswami, Challu, Callot, Minorics, Kan (2023). *Unsupervised Model Selection for Time-series Anomaly Detection.*
arXiv 2210.01078 v3 (ICLR 2023). DOI 10.48550/arXiv.2210.01078 (verified). OA: https://arxiv.org/pdf/2210.01078.
BibTeX `goswami2023unsupervised`. Read: abstract, §1, baselines, results.
- "partition each dataset into selection (20%) and evaluation (80%) sets."
- "We found synthetic anomaly injection to perform better than prediction error and centrality metrics"

**D39** Sharma, Chu, Schmitt, Bronzino, Feamster, Marwell (2026). *Less is More: Optimizing Probe Selection Using
Shared Latency Anomalies.* arXiv 2602.03965. DOI 10.48550/arXiv.2602.03965 (verified). OA: https://arxiv.org/pdf/2602.03965.
BibTeX `sharma2026less`. Read: abstract, predictive evaluation.
- "Specifically, we use the first 𝑇 days to select probes via our greedy heuristic, and evaluate the fraction of anomalies covered by these probes in the remaining days."
- "Our approach covers 95% of aggregate anomaly impact with less than half the total probes used in our deployment."

**D40** Demšar (2006). *Statistical Comparisons of Classifiers over Multiple Data Sets.* JMLR 7, 1–30. DOI none (JMLR).
OA: https://www.jmlr.org/papers/volume7/demsar06a/demsar06a.pdf. BibTeX `demsar2006statistical`. Read: §3.1.3, §3.1.4.
- "Ranks of di = 0 are split evenly among the sums; if there is an odd number of them, one is ignored"
- "Since tied matches support the null-hypothesis we should not discount them but split them evenly between the two classifiers"
- "the sign test will not reject the null-hypothesis unless one algorithm almost always outperforms the other."

### Q6 Probabilistic detection

**D41** Adams, MacKay (2007). *Bayesian Online Changepoint Detection.* arXiv 0710.3742. DOI 10.48550/arXiv.0710.3742
(verified). OA: https://arxiv.org/pdf/0710.3742. BibTeX `adams2007bayesian`. Read: all 7 pages.
- "We compute the probability distribution of the length of the current “run,” or time since the last changepoint, using a simple message-passing algorithm." (p. 1)
- "Notice that the drops to zero run-length correspond well with the abrupt changes in the mean of the data." (p. 4)
- "Immediately after a changepoint, the predictive variance increases, as would be expected for a sudden reduction in data." (p. 4)
- Says: the output is the run-length posterior P(r_t | x_1:t), with a constant hazard 1/λ (λ = 250 in two examples). No
  alarm rule is defined, and detection delay is not evaluated.

**D42** Saatçi, Turner, Rasmussen (2010). *Gaussian Process Change Point Models.* ICML 2010. DOI none found.
OA: https://icml.cc/Conferences/2010/papers/170.pdf. BibTeX `saatci2010gaussian`. Read: §1–2, §5, Fig. 1 caption (pp. 1–2, 5–6).
- "It is clear empirically that the performance of the algorithm is highly sensitive to hyper-parameter settings." (p. 2)
- "The small red crosses mark alert locations where the probability of a change point under the run length posterior since the last alert exceeds 0.95." (p. 6)
- "To quantify the performance of each of these models we evaluate them on test data using the onestep-ahead negative log predictive likelihood (NLL) in nats/observation and mean-square-error (MSE)." (p. 5)
- Says: BOCPD with a GP inside each regime. The CUSUM shown for comparison has its threshold "set to attain a false
  positive rate of 5%". Models are scored on prediction, not on delay.

**D43** Roberts, Osborne, Ebden, Reece, Gibson, Aigrain (2013). *Gaussian processes for time-series modelling.* Phil.
Trans. R. Soc. A 371, 20110550. DOI 10.1098/rsta.2011.0550 (verified). OA: https://www.robots.ox.ac.uk/~sjrob/Pubs/philTransA_2012.pdf
(preprint, read). BibTeX `roberts2013gaussian`. Read: §4 changepoint covariances and observation models (p. 14), §5.3 (p. 21).
- "For example, a sensor fault implies that the relationship between the underlying process model and the observed values is temporarily corrupted." (p. 14)
- "If desired, the algorithm additionally performs changepoint and fault detection as a natural byproduct of the prediction process." (p. 21)

**D44** Fox, Sudderth, Jordan, Willsky (2011). *Bayesian Nonparametric Inference of Switching Dynamic Linear Models.*
IEEE Trans. Signal Processing 59(4), 1569–1585. DOI 10.1109/TSP.2010.2102756 (verified). Read the arXiv version,
*… of Switching Linear Dynamical Systems*, arXiv 1003.3829, DOI 10.48550/arXiv.1003.3829 (verified).
OA: https://arxiv.org/pdf/1003.3829. BibTeX `fox2011bayesian`. Read: abstract, §I, §III-B (Gibbs sampler), IBOVESPA
section (p. 17).
- "Our Bayesian nonparametric approach utilizes a hierarchical Dirichlet process prior to learn an unknown number of persistent, smooth dynamical modes." (p. 1)
- "The ROC curves shown are calculated by windowing the time axis and taking the maximum probability of a change point in each window. These probabilities are then used as the confidence of a change point in that window." (p. 17)

**D45** Altamirano, Briol, Knoblauch (2023). *Robust and Scalable Bayesian Online Changepoint Detection.* ICML 2023,
PMLR 202. DOI: the arXiv version 10.48550/arXiv.2302.04759 (verified); PMLR assigns none.
OA: https://proceedings.mlr.press/v202/altamirano23a/altamirano23a.pdf. BibTeX `altamirano2023robust`. Read: §1, Fig. 3,
App. C.3.
- "However, it also has a significant flaw inherited from Bayesian inference: it is not robust under outliers or model misspecification." (p. 1)
- "Standard BOCD mistakenly labels outliers as CPs, while both Dm -BOCD and β-BOCD are robust and identify lasting changes." (p. 7)
- Says: delay is measured as the distance between the detected and the true change point, among detections "in a
  small neighbourhood of the true CP" (App. C.3).

**D46** Pham, Ha, Zhang (2024). *BARO: Robust Root Cause Analysis for Microservices via Multivariate Bayesian Online
Change Point Detection.* Proc. ACM Softw. Eng. 1(FSE), 2214–2237. DOI 10.1145/3660805 (verified).
OA: https://arxiv.org/pdf/2405.09330. BibTeX `pham2024baro`. Read: §1–3, Algorithm 1, §5 anomaly-detection results
(pp. 7, 13–14).
- "At each time step 𝑡, the most probable run length is computed as the value with the highest probability" (p. 7)
- "Finally, the change points are identified as the data points at the time steps whose run lengths decrease." (p. 7; the text extraction interleaves a formula subscript, which is dropped here)
- "it does not require any user-defined thresholds making it to be highly adaptive to different types of metrics data." (p. 14)
- Also (Q1): "MicroScope [46] and Ms-Rank [50] use a basic three-sigma rule of thumb as their anomaly detection method, known as N-Sigma."
- Also (Q8): "These approaches either rely on users or historical data to obtain thresholds to detect anomalies." (p. 4); "For all methods, we use the hyperparameter settings as in previous works and in their public source code." (p. 13); "In contrast, the performance of N-Sigma and CIRCA drops significantly when the anomaly is detected late." (p. 18); "In this paper, we employ a single deployment setting for each microservice system and a single data collection strategy, which potentially limits the generality of our work." (p. 20)
- Says:
  - Anomaly detection is scored per case by precision, recall and F1, not by delay.
  - BARO's own root-cause scorer takes the median and IQR from the normal period before the detected time.

**D47** Krause, Guestrin (2005). *Near-optimal Nonmyopic Value of Information in Graphical Models.* UAI 2005. Read
the arXiv version 1207.1394, DOI 10.48550/arXiv.1207.1394 (verified). OA: https://arxiv.org/pdf/1207.1394.
BibTeX `krause2005near`. Read: §3–4 (pp. 3–4).
- "Unfortunately, the following counter-example shows that information gain is not submodular in general:" (p. 3; the XOR example follows)
- "Let S, U be disjoint subsets of V, such that the variables in S are independent given U." (p. 3, the condition of Proposition 2 under which information gain is submodular)
- "A convenient property of submodular functions is that they are closed under positive linear combinations." (p. 4)

**D48** Krause, Singh, Guestrin (2008). *Near-Optimal Sensor Placements in Gaussian Processes: Theory, Efficient
Algorithms and Empirical Studies.* JMLR 9, 235–284. DOI none (JMLR). OA: https://www.jmlr.org/papers/volume9/krause08a/krause08a.pdf.
BibTeX `krause2008near`. Read: abstract, §5 (approximate monotonicity, p. 246), §6.1 (robustness to failures, p. 253).
- "is an expectation of the mutual information for placement A where all possible failure scenarios are considered." (p. 253)
- "This is a straightforward consequence of the fact that the class of submodular functions are closed under taking expectations." (p. 253)
- Says: GP-based placement maximises mutual information, which is submodular and approximately monotone, so greedy
  gets about 1 − 1/e of the optimum.

**D49** Krause, Golovin (2014). *Submodular Function Maximization.* In: Tractability: Practical Approaches to Hard
Problems, Cambridge University Press, 71–104. DOI 10.1017/CBO9781139177801.004 (verified).
OA: https://las.inf.ethz.ch/files/krause12survey.pdf (preprint). BibTeX `krause2014submodular`. Read: §1.2.
- "Submodular functions have many useful properties. For example, submodularity is preserved under taking nonnegative linear combinations."
- "in general, the minimum and maximum of two submodular functions are not submodular"

### Q7 Detector comparison

**D50** van den Burg, Williams (2020). *An Evaluation of Change Point Detection Algorithms.* arXiv 2003.06222 v3.
DOI 10.48550/arXiv.2003.06222 (verified). OA: https://arxiv.org/pdf/2003.06222. BibTeX `vandenburg2020evaluation`.
Read: §3 metrics, experimental setup, results.
- "In the experiments we use a margin of error of M = 5."
- "It should be emphasized that while the Oracle experiment is important from a theoretical point of view, it is not necessarily a realistic measure of practical algorithm performance."
- "We also see that in our experiments no method performs significantly better than the zero method on the Default experiment"
- Says: ranks per data set (ties get fractional ranks), then Friedman, then Wilcoxon with Holm correction.

**D51** Wu, Keogh (2021). *Current Time Series Anomaly Detection Benchmarks are Flawed and are Creating the Illusion of
Progress.* IEEE TKDE (early access 2021). DOI 10.1109/TKDE.2021.3112126 (verified). Read the arXiv version 2009.13807,
DOI 10.48550/arXiv.2009.13807 (verified). OA: https://arxiv.org/pdf/2009.13807. BibTeX `wu2021current`. Read:
introduction, §2.2, §2.5, §4.
- "Because of these four flaws, we believe that most published comparisons of anomaly detection algorithms may be unreliable."
- "A time series anomaly detection problem is trivial if it can be solved with a single line of standard library MATLAB code."

### Q8 Per-system calibration

**D52** Borges, Bauer, Werner, Gebauer, Tai (2024). *Informed and Assessable Observability Design Decisions in
Cloud-native Microservice Applications.* ICSA 2024, 69–78. DOI 10.1109/ICSA59870.2024.00015 (verified). Read the
arXiv preprint 2403.00633, DOI 10.48550/arXiv.2403.00633 (verified). OA: https://arxiv.org/pdf/2403.00633.
BibTeX `borges2024informed`. Read: §4 fault visibility (p. 4), §6.1–6.2 (p. 7).
- "A fault f can be considered visible in metric m if the data recorded during the occurrence of the fault, represented by the time interval [t0 − t1 ], is significantly different from the data recorded under normal conditions, in time interval [t-1 − t0 [, and thus detected by detection mechanism d." (p. 4)
- "For training, we split the experiment data into training and test sets and ensure an equal class balance of fault and non-fault labels via an oversampling technique." (p. 7)
- "evaluate the classifier’s detection function (DF(mt ) ) on the test data and compute classification accuracy with a threshold of 0.7 as our implementation of α for fault visibility." (p. 7)
- Says:
  - Runs on the OpenTelemetry Demo. The setup is 10 runs of 10 min with 50 users. The detector is logistic regression per fault and metric.
  - A miss may mean "(ii) the parameters of metric m are not set appropriately or (iii) the function parameters" of the detector are wrong.
  - The passage read does not say whether the train/test split is by time or by run.

**D53** Borges, Bauer, Werner (2024). *OXN – Automated Observability Assessments for Cloud-Native Applications.*
arXiv 2407.09644 (two-page poster paper). DOI 10.48550/arXiv.2407.09644 (verified). OA: https://arxiv.org/pdf/2407.09644.
BibTeX `borges2024oxn`. Read: whole paper.
- "seamlessly add their own fault detection mechanisms, which could range from threshold-based alerting techniques to more advanced anomaly detection models."

**D54** Pham, Zhang, Ha, Salim, Zhang (2025). *RCAEval: A Benchmark for Root Cause Analysis of Microservice Systems with
Telemetry Data.* WWW 2025 Companion, 777–780. DOI 10.1145/3701716.3715290 (verified). OA: https://arxiv.org/pdf/2412.17015.
BibTeX `pham2025rcaeval`. Read: §3.3–4.1 (p. 3).
- "We allow the microservice systems to run normally to collect normal telemetry data. Then, we inject a fault into a randomly selected running service and collect the abnormal telemetry data."
- "we adapt their available implementations and use the default hyperparameter settings recommended in their respective papers."

**D55** Fang, Zhang, Yang, Wu, Xu, Wang, Wang, Wang, Lu, He (2025). *Rethinking the Evaluation of Microservice RCA with
a Fault Propagation-Aware Benchmark.* arXiv 2510.04711 v2. DOI 10.48550/arXiv.2510.04711 (verified).
OA: https://arxiv.org/pdf/2510.04711. BibTeX `fang2025rethinking`. Read: abstract, §3.1–3.2 (pp. 1, 4), §4.2–4.7
(p. 10), §5.1 (p. 11).
- "Our preliminary study reveals that simple rule-based methods can achieve performance comparable to or even surpassing state-of-the-art (SOTA) models on four widely used public benchmarks." (p. 1)
- "The threshold is dynamically determined using robust statistical methods, such as the 3-sigma rule or the 95th percentile (P95) of its historical data." (p. 4, their simple baseline)
- "To ensure a fair comparison, we conducted a systematic, best-effort hyperparameter tuning for each model to adapt it to the unique characteristics of our new," (p. 11; the sentence continues "… dataset")
- Says: a case is kept only if it passes "hard thresholds (e.g., 10 seconds) with adaptive statistical thresholds based on
  historical performance patterns" (p. 10). No separate tuning split is mentioned in the part read.

**D56** Lee, Yang, Chen, Su, Lyu (2023). *Eadro: An End-to-End Troubleshooting Framework for Microservices on
Multi-source Data.* ICSE 2023, 1750–1762. DOI 10.1109/ICSE48619.2023.00150 (verified). OA: https://arxiv.org/pdf/2302.05092
(arXiv DOI 10.48550/arXiv.2302.05092, verified). BibTeX `lee2023eadro`. Read: §III and Table I (p. 4), §V.A (p. 7).
- "N-sigma used in [20], [21] computes the mean (µ) and the standard deviation (σ) of historical fault-free data." … "where n is an empirical parameter." (p. 4)
- "Even worse, these machine learning-based approaches require extra hyperparameter tuning, making the entire troubleshooting approach less practical." (p. 4)
- "Data produced in different periods are divided into training (60%) data and testing (40%) data, respectively. The data divisions share similar distributions in abnormal/normal ratios and root causes." (p. 7)
- Says: in Table I, N-sigma misses 63.2 % of anomalies and SPOT misses 20.7 %.

**D57** Zhang, Jin, Lin, Sun, Zhang, Xia, Li, Zhong, … Pei (2023). *Robust Failure Diagnosis of Microservice System
through Multimodal Data* (DiagFusion). IEEE Trans. Services Computing 16(6), 3851–3864. DOI 10.1109/TSC.2023.3290018
(verified). Read: arXiv 2302.10512 v2, DOI 10.48550/arXiv.2302.10512 (verified). OA: https://arxiv.org/pdf/2302.10512.
BibTeX `zhang2023robust`. Read: §4.1 (p. 5), §5.1 (p. 7).
- "We perform 3-sigma to detect anomalous metrics." (p. 5)
- "To prevent data leakage, we split the data of D1 and D2 into training and testing sets according to their start time, i.e., we use data from the earlier time as the training set and data from the later time as the test set." (p. 7)

**D58** Ping, Bin Mazhar, Wang, Song, Mäntylä (2026). *AnoMod: A Dataset for Anomaly Detection and Root Cause Analysis
in Microservice Systems.* MSR 2026, 677–681. DOI 10.1145/3793302.3793324 (verified). OA: https://arxiv.org/pdf/2601.22881.
BibTeX `ping2026anomod`. Read: §2.3–2.4 (p. 3).
- "the script redeploys a fresh instance of the MSS for each anomaly case run and waits until all components are fully initialized and stable."
- Says: normal and anomaly runs are separate fresh deployments, as with our no-fault cells. There is no detector
  calibration protocol.

**D59** Kapoor, Narayanan (2023). *Leakage and the reproducibility crisis in machine-learning-based science.* Patterns
4(9), 100804. DOI 10.1016/j.patter.2023.100804 (verified, not read). Read: arXiv 2207.07048 v1 (2022), *Leakage and the
Reproducibility Crisis in ML-based Science*, DOI 10.48550/arXiv.2207.07048 (verified); the published taxonomy may
differ. OA: https://arxiv.org/pdf/2207.07048. BibTeX `kapoor2023leakage`. Read: §3, the taxonomy (p. 5).
- "Using the same dataset for training as well as testing the model is a text-book example of overfitting, which leads to overoptimisic performance estimates" (L1.1)
- "Feature selection on the entire dataset results in using information about which feature performs well on the test set to make a decision about which features should be included in the model." (L1.3)
- "Nonindependence between train and test samples constitutes leakage, unless the scientific claim is about a distribution that has the same dependence structure." (L3.2)

**D60** Siffer, Fouque, Termier, Largouët (2017). *Anomaly Detection in Streams with Extreme Value Theory* (SPOT).
KDD 2017, 1067–1075. DOI 10.1145/3097983.3098144 (verified). OA: https://hal.science/hal-01640325/document.
BibTeX `siffer2017anomaly`. Read: abstract (p. 2), §4.3 (p. 5), experiments.
- "the main parameter is only the risk, controlling the number of false positives." (p. 2)
- "Firstly, we perform a POT estimate on the n first values (n ∼ 1000) and we get an initial threshold zq (initialization)." (p. 5)
- Says: one risk level q (1e-3 or 1e-4 in the experiments) for every stream, and each stream's threshold calibrated
  on its own initial batch.

**D61** Basiri, Behnam, de Rooij, Hochstein, Kosewski, Reynolds, Rosenthal (2016). *Chaos Engineering.* IEEE Software
33(3), 35–41. DOI 10.1109/MS.2016.60 (verified). OA: https://arxiv.org/pdf/1702.05843. BibTeX `basiri2016chaos`. Read: pp. 3–9.
- "Start by defining ‘steady state’ as some measurable output of a system that indicates normal behavior." (p. 9)
- "Hypothesize that this steady state will continue in both the control group and the experimental group." (p. 9)
- "Try to disprove the hypothesis by looking for a difference in steady state between the control group and the experimental group." (p. 9)

**D62** Pham (2026). *Anomaly Detection and Root Cause Analysis for Microservice Systems.* PhD thesis, RMIT; arXiv
2606.09942 v3. DOI 10.48550/arXiv.2606.09942 (verified). OA: https://arxiv.org/pdf/2606.09942. BibTeX `pham2026anomaly`.
Read: the EFP section (p. 82), §7.5 (pp. 137–145).
- "With default hyperparameter settings, their performance is not consistent across different datasets;" (p. 137)
- "Previous works usually choose these hyperparameters empirically, and these chosen values might not be the most optimal choice to achieve the maximal performance." (p. 139)
- "they require periodic retraining or recalibration." (p. 145, on BARO and EventADL under drift)

**D63** Wang, Mäntylä, Demeyer, Beyazıt, Kisaakye, Nyyssölä (2025). *Cross-System Categorization of Abnormal Traces in
Microservice-Based Systems via Meta-Learning* (TraFaultDia). Proc. ACM Softw. Eng. 2(FSE), 576–598.
DOI 10.1145/3715742 (verified). OA: https://arxiv.org/pdf/2403.18998. BibTeX `wang2025cross`. Read: abstract, §1 (pp. 1–2).
- "In the cross-system context, when TraFaultDia is applied to a MSS different from the one it is trained on, TraFaultDia gets an average accuracy of 92.19% and 84.77% for the same set of 50 new, unseen abnormal trace classification tasks of the respective systems, also with 10 labeled instances provided for each fault category per task in each system."

**D64** Chen, Song, Xia (2026). *Adaptively diagnosing system faults in microservice architecture: An autonomous
predictive model construction framework* (AMFF). Future Generation Computer Systems 177, 108256.
DOI 10.1016/j.future.2025.108256 (verified). OA: none found; read from a local copy made in an earlier session.
BibTeX `chen2026adaptively`. Read: only one fragment could be extracted cleanly. **Weak support.**
- "a certain fault type with normal data and a few abnormal samples"

### Not read, never used as support

- Hampel 1974 and 1985; Davies & Gather 1993; Pearson 2002: paywalled.
- Jensen et al. 2006: cited only through D6.
- Künsch 1989; Thiébaux & Zwiers 1984; Jovanovic & Levy 1997.
- Page 1954, Lorden 1971, Shiryaev 1963: known only through D17 and D18.
- Kaplan & Meier 1958.
- Ahmed, Kanhere & Jha 2005 ("probabilistic coverage").
- Berry et al. 2009 (journal version of D29).
- Lindon et al. 2022 (Netflix sequential testing, arXiv 2205.14762): found, not read.
- Garnett et al. 2009/2010 (GP prediction with changepoints): read in part, superseded by D43, not cited.
- Paparrizos et al. 2022 (VUS): only the abstract read, not cited.
- Georges et al. 2007: read, low relevance, not cited.

---

## Appendix: computations

All four were run by me. The scripts lived in the session scratchpad, which macOS reaps, so the method is given here
in full.

1. **MAD threshold with a small baseline.** Simulation, run twice independently: 20,000 and 100,000 repetitions, seed
   20261004. Draw n baseline points from N(0, 1), or from lognormal(0, 0.5) for latency-like data. Set the threshold
   at median + K·1.4826·MAD. Compute the exact probability that one new point from the same distribution exceeds it,
   then average over repetitions. One-sided. The values below come from the 20,000-repetition run. The other run,
   written separately, agrees within about 0.2 percentage points in every cell. The n = 3 rows come from a third run
   (200,000 repetitions, seed 3). The reviewer re-derived four cells independently: normal n = 4, K = 4 gave 5.69 %, and
   lognormal n = 4, K = 4 gave 10.3 %.

   | data | n | K = 3 | K = 4 | K = 5 |
   |---|---|---|---|---|
   | normal | 3 | 15 % | 12 % | 9.9 % |
   | normal | 4 | 8.7 % | 5.7 % | 3.9 % |
   | normal | 10 | 2.6 % | 1.05 % | 0.5 % |
   | normal | 20 | 1.1 % | 0.25 % | 0.06 % |
   | normal | 100 | 0.26 % | 0.02 % | 0.00 % |
   | normal | ∞ (nominal) | 0.13 % | 0.003 % | 0.00003 % |
   | lognormal(0, 0.5) | 3 | 20 % | 16 % | 14 % |
   | lognormal(0, 0.5) | 4 | 14 % | 10 % | 7.9 % |
   | lognormal(0, 0.5) | 20 | 5.4 % | 2.8 % | 1.5 % |
   | lognormal(0, 0.5) | ∞ (nominal) | 3.6 % | 1.5 % | 0.7 % |

   Each row is per new point. A window with m post-onset points fires more often. The lognormal rows show that a
   symmetric MAD rule on skewed latency data is not at its nominal rate even with infinite data.
2. **Zero alarms.**
   - The one-sided 95 % upper bound for 0 of n is 1 − 0.05^(1/n): 52.7 % at n = 4, 13.9 % at n = 20, 4.95 % at n = 59.
   - For a rate, 0 alarms in T hours gives a bound of 2.996/T per hour (χ² with 2 df).
3. **Paired tests.** The smallest two-sided p for a sign test, or an exact Wilcoxon test, with all n paired units
   favouring one side is 2·0.5^n: 0.125 at n = 4, 0.0625 at n = 5, 0.031 at n = 6.
4. **Time windows.** 4 no-fault cells × 180 s = 0.2 h of no-fault time per rate.

---

## Review

- **What was checked.** One independent read-only review was run on 2026-10-04: a separate Fable session using the
  adversarial-review agent, not the judge panel.
  - It re-derived the arithmetic and four simulation cells.
  - It spot-checked over 40 quotes against the source texts.
  - It read the declaration and analysis code it needed.
  - It did not check DOIs, because it had no network access.
- **Its verdict on the numbers.** All numbers and quotes held.
- **Its 20 findings were about wording and decision classes. All 20 were applied:**
  - Two §2 rows were reclassified: the candidate pool (row 9) and placement false alarms (row 7).
  - The Q6 claim that route (b) is "already computed" was narrowed.
  - Source-to-claim fixes: Chromium's gates, Goswami's split, BARO's hedged mechanism, the censoring inference, and the stream-K sentence.
  - The Jaeger example was moved from floors to timing.
  - A tie rule now handles win shares.
  - Added: the n = 3 baseline rows, the cost of a minimum baseline, P4's 3-of-4 criterion, term definitions, and pointers to repo evidence.
  - A contradictory "not read" line on SPOT was removed.
- **Not re-reviewed after the fixes.**

