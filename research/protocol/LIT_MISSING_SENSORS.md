# Missing sensors: survivorship bias in the placement ground set (literature note)

Written 2026-10-04 by a Claude subagent (Opus) for the question below. This is a literature note, not a protocol change, and it decides nothing.
Quotes were checked by script against the downloaded texts (§5). **Independent review: one Fable adversarial pass,
findings applied, revised text not re-reviewed** (see §5).

> The user's question, verbatim: "how does this account for non survivorship bias for parts that are missing (-inf
> probability that are mapped in the optimal full graph vs what is observed)"

Every conclusion carries one of these **scope labels**:
- **general practice**: a textbook or field-wide standard;
- **one paper**: what a single source shows;
- **tool-specific**: one tool or specification;
- **mine**: my own derivation or synthesis.

"No standard" means I found none. It does not mean none exists. The search was web search plus reading, and it was not
systematic.

---

## 1. Summary in plain language

### 1.1 What the bias is here

- **Sensor.** A signal we could keep: a span per operation, a log template, a metric.
- **Full graph.** Every sensor the system could have: every service, operation, log template and metric, under the
  posture with everything instrumented.
- **Ground set.** The list of sensors the optimiser (CELF, lazy greedy) may choose from. In this repo it is truncated
  in two ways:
  - **The live TeaStore f(S).** The universe is the activation catalog (`research/submodularity.py:56–59`), which is
    trace-only. A catalog sensor that no observed journey requires stays in the ground set, but with marginal gain 0.
    Logs, metrics and operations that are not in the catalog are not in the ground set at all.
  - **The protocol §2 representation.** The vocabulary is built from observed no-fault windows. A token that never
    emitted is absent from it.

Either way, a sensor that never emitted gets detection probability 0, which is log-probability −∞. It never gets an
uncertain value, and CELF can never pick it for a positive reason. That is **survivorship bias**: we optimise only over
what survived into the data, or into the catalog. The placement is then optimal *for that ground set*, not for the
system.

A sensor can show nothing for a fault for four different reasons. Testing theory names the steps with the **RIPR**
model (M24): Reachability, Infection, Propagation, Revealability. Rows 1 and 3 can also keep a sensor out of the ground
set entirely; rows 2 and 4 leave it in the ground set but without a catch. Mapped to this project (the mapping is
**mine**):

| why the sensor shows nothing | RIPR step | what the absence tells us |
|---|---|---|
| no request or job went through its code path (route not driven, too little traffic, fault not in the catalogue) | reachability | nothing about the sensor. It had **no opportunity** |
| the path ran, but the fault did not change anything the sensor reads | infection | the sensor does not see this fault: a genuine non-detection for placement |
| the state changed, but nothing was emitted or kept (posture does not collect it, log level filters it, the trace was sampled away, the collector was down) | propagation (into the telemetry output) | something about the **instrumentation**, nothing about the fault |
| it emitted, but the detector (our oracle) did not flag it: below threshold | revealability | a miss that depends on the detector as well as the sensor |

Rows 2 and 4 bear on the sensor. Rows 1 and 3 do not. In the first row, the absence is **absence of opportunity**. The
project has already been caught by this. In the earlier TeaStore corpus, **8** fault families (of 11) are flagged
`NO-WORKLOAD`: no span of any service fell in the fault window, in 10 of 10 runs each (`research/visibility-map/MAP.md`;
count from `/usr/bin/grep -c "NO-WORKLOAD: in 10 of 10"`, which gives 8). The catches recorded on those families are
artefacts of the trace stream ending, not evidence about the fault (MAP.md: "A catch here is the trace stream ending,
not the fault").

The project also has a first **bias report**: the projection map (`research/project-map/PROJECT_MAP.md`; protocol
§1b). It has four states: possible and observed, possible but not observed, not possible, observed but not projected.
Scope **instance**: one no-fault cell per posture, generated 2026-10-02 from commit `0446f9b`, not independently
reviewed. The unit is service × channel × posture **cells, not sensors**. Measurement-window counts:

| SUT | possible, observed | possible, **not** observed | not possible (of which unconfirmed) | observed, not projected | `?` (unknown) | n cells |
|---|---|---|---|---|---|---|
| HotelReservation | 54 | 167 | 154 (123) | 1 | 396 | 772 |
| TeaStore | 25 | 24 | 53 (30) | 0 | 93 | 195 |
| OTel demo | 112 | 22 | 118 (0) | 6 | 546 | 804 |

So in Hotel, three times as many possible cells were not observed as were observed (167 vs 54). Not all 167 are
"never emitted". 33 emitted only outside the measurement window (start-up or teardown), and 40 are `log:undefined`
cells that only library code could fill (PROJECT_MAP.md, Hotel list). That leaves 94 cells whose call sites exist but
never fired. The `?` column (396/772, 93/195, 546/804) is unknown, not zero.

### 1.2 How the field handles it

1. **In the two reference placement papers, unobserved locations are modelled, not dropped.** In the GP placement work,
   the objective is the information the chosen sensors give about the locations *not* chosen. That includes places
   where no sensor can go (M2, **one paper**). In Leskovec et al.'s water network, every node and every scenario comes from a
   simulator: 3.6 million scenarios, any node, any time (M1). The ground set is complete *by construction*. In their
   blog case the ground set came from data. There, CELF overfitted to small blogs that "just by chance" took part in
   cascades. The fix was an **exposure floor**: only blogs with at least one post per day (M1, **one paper**). This
   project is in the blog case, not the water case.
2. **Missing-data theory says when ignoring the gaps is safe.** Rubin's classes (M5, M6; **general practice**):
   - **MCAR** (missing completely at random): the gap is unrelated to anything. Ignoring it is safe.
   - **MAR** (missing at random): the gap depends only on things we do observe. Ignoring it is safe if we condition on
     those things.
   - **MNAR** (missing not at random): the gap depends on the missing value itself.

   Analysing only the units that were observed is called **complete-case analysis**. It is safe under MCAR. Under
   MNAR, some quantities cannot be recovered "regardless of how large the sample or how clever the imputation" (M5).

   How this maps here (**mine**) depends on which gap is meant:
   - **Dropping sensors that never fired** from the ground set is selection on the outcome. That is survivorship bias
     proper, and it sits outside Rubin's three classes.
   - **Sensor × fault cells for faults that were never run** are missing by design. The gap depends on the fault
     catalogue, not on the value, so it is MAR given the catalogue.
   - **Traces dropped by content-dependent sampling** are self-masking MNAR: the rare, faulty requests are the ones
     lost (M9).

   Neither the first nor the last can be fixed by more of the same data. New experiments, or an explicit assumption,
   can.
3. **Ecology separates "absent" from "present but not detected".** It has done this for decades with **occupancy
   models**. Each site has a hidden state, occupied or not. Repeated visits estimate a **detection probability**
   separately from **occupancy** (M18, M22; **general practice in ecology**). Multi-species versions draw every
   species' parameters from a shared community distribution. That gives rare species usable estimates (M18). A further
   step, **data augmentation**, adds species that were **never detected**: each gets a latent "available" flag with a
   posterior probability, not a zero (M19, **tool-specific** write-up of Dorazio et al. 2006, which I did not read).
   The time-to-detection variant links the detection rate to survey length, p = 1 − e^(−λt) (M22). That is the same
   form as the project's traffic model for the root (`research/literature-20261002/DIMENSIONS.md` §0).
4. **Software testing estimates the unseen part.** It borrows ecology's species estimators (Good–Turing, Chao, jackknife)
   to estimate how much code or behaviour is still unseen (M16, M15, M17). Two warnings carry over:
   - a static upper bound (the call graph) both over- and under-counts (M15);
   - every estimator predicted "false peaks" when the truth was unknown (M15). Extrapolation is provably limited to
     about log n times the sample (M17).
5. **Microservice observability names the problem but does not treat the candidate set as a population.**
   - Missing modalities are handled in RCA models. ARMOR shows that zero-filling a dropped channel looks like "a
     healthy idle service" (M8).
   - Unmonitored root causes are modelled as latent variables (M11). Partial identification gives bounds (M12).
   - Sampling hides traces: a 27.17 % query miss rate at Alibaba (M10). Head sampling cannot know in advance which
     request matters (M9).
   - Monitoring gaps are a known cause of late detection (M14).
   - The closest evaluation framework computes fault coverage over the **collected** metrics only (M13).

   M14 proposes missing monitors from similar services, but it does not score how well they would detect. I found no
   paper that estimates which telemetry signals a system *could* emit but did not *and then scores their detection*.
   I also found none that separates "no opportunity" from "missed" (**no standard**).
6. **Across systems, names are shared but detection behaviour is not.** OpenTelemetry semantic conventions give a
   common naming scheme. Optional attributes may legitimately be absent (M28, **tool-specific**). Cross-system log
   detectors report "semantic mismatch" and "distribution drift" (M27, **one paper**). The hierarchical beta process
   is the formal device for sharing an unknown number of features across groups (M26). I found no placement transfer
   study (**no standard**).

### 1.3 Recommendation

Each item is marked **engineering default** (Claude may pick and record it) or **▶ user** (it changes what the objective
counts or what is reported as primary, so it is a preregistration decision; see `CLAUDE.md`, "Decisions").

**For this paper (trace-only evidence, CELF kept):**

- **R1. State what the optimum is over** (engineering default). Write "optimal over this ground set (the catalog, or the
  observed vocabulary) under this workload and posture". Print how many of its sensors had nonzero gain, beside the
  projection map's four-state counts. Keep `?` as `?`.
- **R2. Account for exposure** (engineering default to report it; ▶ user to change the primary metric, and ▶ user for
  the exposure threshold: any request, or at least k). For every (sensor, fault, episode), record one of three states:
  - **exposed**: the posture collects the sensor and traffic reached it during the fault window. The ledger observes
    traffic per route at the entry only. Whether a route reaches an interior sensor is projected from the call graph
    (§1b), not observed;
  - **not exposed**;
  - **unknown**.

  If the user takes decision (b) in §4, detection is estimated only on exposed episodes, and non-exposed ones are `—`,
  not misses. Decision 15 charges a miss at the window end. That is Leskovec's bounded penalty π(∞), and it is right
  for exposed episodes (M1).
  - Charging it to a never-exposed sensor puts a unit that was never at risk into the risk set.
  - Where the fault itself ends exposure (for example, by stopping traffic upstream), the censoring is informative,
    and standard methods are not valid then (M25).

  Both cases need exposure to be recorded. The planted positives of protocol §2 test the later RIPR steps: whether a
  channel can emit and fire at all.
- **R3. Bound the placement instead of pretending to know** (▶ user). Run CELF twice:
  - pessimistic: unobserved sensors score 0, as now;
  - optimistic: every possible-but-not-observed sensor gets the best detection rate measured in its channel × role
    class.

  If the chosen set or its score changes, report that the placement depends on the unobserved part. Bounds are the
  honest output when the unobserved part cannot be identified (M5, M12). Recommended as a robustness row, not as the
  primary result.
- **R4. Use an exposure floor as a robustness row** (engineering default). Rerun with only sensors that had at least k
  exposed episodes. Leskovec's fix for lucky rare picks was exactly this (M1).
- **R5. Put one number on how much is missing** (engineering default, diagnostic only). Treat each episode as the set
  of sensors that fired; that is the Bernoulli-product, or incidence, model (M17). Report the Chao2 lower bound and the
  discovery probability (the chance that the next episode shows a new sensor; M16) per SUT × posture × channel. Add
  Liyanage et al.'s caveat that these estimators under-estimate (M15).
- **R6. Wording.** Never write "sensor X cannot detect fault F" from a run where X had no opportunity. Write "not
  exposed in this run". This is the "snapshot as a property" trap in `CLAUDE.md`.

**Future work (the probabilistic dimension; round 7 decision 26, D3):**

- **F1. An occupancy-style model of detection.** Give each sensor a detection rate λ_s, with random effects by channel ×
  role × SUT, drawn from a shared community distribution (M18). Use a time-to-detection likelihood censored at the
  window end, with traffic as the exposure (M22, M25). Every *projected* sensor gets a posterior predictive detection
  probability, including never-exposed ones. Those are wide, but they are not −∞. This is one reading of the "filter
  that assigns variance to activations" the user asked for. Decision 26 names a Kalman or state-space filter on
  activations; that is a different model, of the signal over time rather than of detection rates.
- **F2. Data augmentation for sensors never seen at all.** Size the super-population from the projection map and
  static call sites (M19, M15).
- **F3. Keep CELF.** The expected penalty reduction R under the posterior is still submodular (M1, M2 §6.2, M4;
  derivation and its premises in M1's conclusion). CELF runs unchanged on R. This holds for the penalty-reduction
  surrogate only. The primary outcome of decision 15, the mean charged detection time, is not submodular, with or
  without a prior (`DIMENSIONS.md` §1.1, Heavey et al. 2022).
- **F4. The prior's shape enters the placement; its variance also steers the next run.** A risk-neutral expectation
  ignores prior variance only when the objective is linear in the uncertain detection probabilities and the sensors
  are independent a posteriori. Under F1 neither holds:
  - rates enter through p = 1 − e^(−λt), and E[e^(−λt)] ≠ e^(−E[λ]t);
  - the shared community prior correlates sensors.

  So prior shape does change E[R]. The variance is also what experiment design (M2's footnote) and adaptive placement
  (M3) use to choose the next run. It certifies nothing about a placement.
- **F5. Cross-system.** A hierarchical model over systems → channel × role → sensor, typed by OpenTelemetry names
  and service roles (M26, M28, M14). Test it on the hold-out SUT. Expect semantic mismatch (M27).
- **F6. Retroactive collection** (M9; ▶ user, because it changes what the harness emits). It removes "was not
  exported" as a cause of absence, at the cost of changing the harness.

---

## 2. Approaches at a glance

| approach | sources | what it fixes | cost | fit here |
|---|---|---|---|---|
| State the scope and denominators (projection map, four states, `?` kept) | M13, M15, project `PROJECT_MAP.md` | makes the bias visible; estimates nothing | low; the map exists | **now** (R1) |
| Exposure accounting; non-exposed episodes are `—`, not misses | M24, M25, M22, M1, M23 | separates "no chance" from "missed" | entry-route traffic exists in the ledger; interior exposure is projected, not observed; analysis code | **now** (R2) |
| Exposure floor | M1 §5.7 | stops CELF picking sensors that were lucky once | loses genuinely rare sensors | **now**, robustness row (R4) |
| Pessimistic / optimistic bounds on the placement | M5, M12 | honest when the unseen part cannot be identified; shows whether the result depends on it | two CELF runs plus a class rule | **now** if the user agrees (R3) |
| Unseen-count estimators (Chao2, Good–Toulmin, discovery probability) | M15, M16, M17 | a number for how much is missing | low; under-estimates; false peaks | **now**, diagnostic (R5) |
| GP prediction of unobserved locations (mutual information) | M2 | values places with no sensor through correlation | needs a kernel over sensors; there is no geometry here | weak; future |
| Occupancy / time-to-detection hierarchical model | M18, M19, M22 (M20, M21 not read) | separates absence from non-detection; every sensor gets a posterior | replicated episodes; MCMC; n_eff is tens | **future, best fit** (F1, F2) |
| Hierarchical beta process / Indian buffet | M26 | an unknown number of sensors; sharing across systems; no 0/1 estimates | heavy; needs a typing | future (F5) |
| Expected objective over the posterior, fed to CELF | M1, M2 §6.2, M4 | keeps submodularity; CELF unchanged | needs F1 | future (F3) |
| Adaptive placement / experiment design | M3, M2 | uses the variance to pick the next run | an online loop | future (F4) |
| Missing-modality-robust RCA models | M8, M11, M12 | diagnosis when a channel drops | deep models, training data | context only; not placement |
| Retroactive or always-on collection | M9, M10 | removes sampling and export as causes of absence | harness and infrastructure change | future (F6) |
| Shared typing across systems | M28, M14, M27 | makes sensors comparable across SUTs | mapping effort; semantic mismatch | future (F5) |

---

## 3. Sources

Fields per source: authors · title · venue/year · URL · DOI (how verified) · open-access PDF · BibTeX key · read ·
quotes · **says** · **I conclude** (with scope label).

Notes on quotes. They are verbatim, with only these normalisations:
- ligatures and line-break hyphens are joined;
- typographic hyphens and quote marks are unified;
- the HTML math markup in M19 is stripped.

Page numbers are pages of the downloaded PDF ("PDF p."), unless the journal's own page is given.

### M1 · Leskovec, Krause, Guestrin, Faloutsos, VanBriesen, Glance
- **Title.** Cost-effective outbreak detection in networks. **Venue.** KDD 2007, pp. 420–429.
- **URL / OA PDF.** https://www.cs.cmu.edu/~jure/pubs/detect-kdd07.pdf (tech report CMU-ML-07-111:
  http://www.cs.cmu.edu/~jure/pubs/detect-techRept.pdf)
- **DOI.** 10.1145/1281192.1281239 (Crossref title matches, 2026-10-04) · **BibTeX key.** `leskovec2007costeffective`
- **Read.** §2.1–2.2 (PDF p. 3), §3 sparsity paragraph (p. 4), §5.1, §5.5, §5.7 (pp. 6–7), §6.2–6.3 (p. 8).
- **Quotes.**
  - "We also set T(i, ∅) = ∞, and set πi(∞) to some maximum penalty incurred for not detecting event i." (PDF p. 3)
  - "most outbreaks are sparse, i.e., affect only a small area of the network (c.f., [12, 16]), and hence are only
    detected by a small number of nodes. Hence, most nodes s do not reduce the penalty incurred by an outbreak (i.e.,
    Ri({s}) = 0)." (PDF p. 4)
  - "CELF overfits when evaluated on the future data, i.e., it selects small blogs with very few posts that just by
    chance participate in cascades, and then these blogs do not generalize well for the second half of the year."
    (PDF p. 7)
- **Says.**
  - Undetected events are charged the maximum penalty, not dropped.
  - "any objective function that can be viewed as an expected penalty reduction is submodular" (PDF p. 3).
  - Water: 3.6 M simulated scenarios; contamination "can happen at any node". Blogs: the data set was "biased …
    towards the active part of the blogosphere" (at least 3 in-links; cascades of at least 10 nodes).
  - Restricting CELF to blogs with at least one post per day nearly closed the generalisation gap: "the gap between
    the curves is very small" (§5.7).
- **I conclude.**
  - (a) Leskovec handles *undetected events* (π(∞)) but not *missing candidates*. The water ground set is complete
    because a simulator enumerates it. The blog ground set is filtered on activity, which is a selection on the
    outcome (**one paper**).
  - (b) The exposure floor is a published, cheap guard against sensors that were lucky once (**one paper**).
  - (c) Derivation (**mine**): for a posterior draw θ and an episode realisation ω, R_{θ,ω}(A) has the Leskovec form.
    E_θ E_ω R is a nonnegative mixture of such functions, so it is submodular, and CELF applies to the prior-based
    penalty reduction R. Two premises:
    - π is nondecreasing in t;
    - the distribution of episode realisations does not depend on the placement A. Postures perturb the SUT
      (TeaStore campaign #11: +60 ms p50 at none→selected, project memory `teastore-campaign11-complete`), so this is
      an assumption, not a fact.

    The result is for R only. The primary outcome of decision 15, the mean charged delay, is not submodular
    (`DIMENSIONS.md` §1.1).

### M2 · Krause, Singh, Guestrin
- **Title.** Near-optimal sensor placements in Gaussian processes: theory, efficient algorithms and empirical studies.
  **Venue.** JMLR 9:235–284, 2008.
- **URL / OA PDF.** https://www.jmlr.org/papers/volume9/krause08a/krause08a.pdf
- **DOI.** none; JMLR does not issue DOIs. 10.1145/1102351.1102385 is the different ICML 2005 paper.
- **BibTeX key.** `krause2008nearoptimal`
- **Read.** Abstract, §1 with footnote 1 (pp. 235–236), §3.1–3.2 (pp. 241–243), §6.2 (p. 254).
- **Quotes.**
  - "we tackle the combinatorial optimization problem of maximizing the mutual information between the chosen
    locations and the locations which are not selected." (p. 235)
  - "a set S of possible positions where we can place sensors, and another set U of positions of interest, where no
    sensor placements are possible. The goal is to place a set of k sensors that will give us good predictions at all
    uninstrumented locations V \ A." (p. 243)
  - "Since the class of submodular functions is closed under expectations, MIM is still a submodular function." (p. 254)
- **Says.**
  - The GP is learned from a pilot deployment or expert knowledge.
  - The objective values predictions at unsensed locations.
  - A prior over the GP's parameters keeps submodularity.
  - Footnote 1: placement "can be viewed as an inner-loop step for an active learning algorithm".
- **I conclude.**
  - In this reference paper and M1, the unobserved part is **modelled**, not omitted (**one paper** each; I did not
    survey the placement literature as a whole).
  - Transfer here is weak. Mutual information needs a covariance between sensors, and telemetry has no spatial
    geometry. A call-graph or role-based kernel would have to be built (**mine**).

### M3 · Golovin, Krause
- **Title.** Adaptive submodularity: theory and applications in active learning and stochastic optimization.
  **Venue.** JAIR 42:427–486, 2011.
- **URL / OA PDF.** https://arxiv.org/pdf/1003.3967
- **DOI.** 10.1613/jair.3278 does **not** resolve (doi.org 404, 2026-10-04). arXiv DOI 10.48550/arXiv.1003.3967
  (DataCite title matches).
- **BibTeX key.** `golovin2011adaptive`
- **Read.** Abstract, §1, §2.1 (PDF pp. 1–4).
- **Quotes.**
  - "we introduce the concept of adaptive submodularity, generalizing submodular set functions to adaptive policies. We
    prove that if a problem satisfies this property, a simple adaptive greedy algorithm is guaranteed to be competitive
    with the optimal policy." (PDF p. 1)
  - "We will consider problems where we sequentially pick an item e ∈ E, get to see its state Φ(e), pick the next item,
    get to see its state, and so on (e.g., place a sensor, see whether it fails, and so on)." (PDF p. 4)
- **Says.** It uses a prior over item states. Greedy is near-optimal for adaptive policies when the objective is
  adaptive submodular.
- **I conclude.** This is the formal home for "place, observe whether the sensor fires, update, place again". It
  belongs to the online follow-on, not this paper (**one paper**).

### M4 · Kim, Sarker, Kim, Stilwell, Jimenez
- **Title.** Robust sensor placement for Poisson arrivals with false-alarm-aware spatiotemporal sensing.
  **Venue.** arXiv preprint 2510.05343v3, 2025.
- **URL / OA PDF.** https://arxiv.org/pdf/2510.05343
- **DOI.** 10.48550/arXiv.2510.05343 (DataCite title matches) · **BibTeX key.** `kim2025robust`
- **Read.** Abstract, §I, §II.B, §III.B–C (PDF pp. 1–4).
- **Quotes.**
  - "This paper studies sensor placement when detection performance varies stochastically due to environmental factors
    over space and time and false alarms are present, but a filter is used to attenuate the effect." (PDF p. 1)
  - "Furthermore, we prove robustness guarantees showing that performance remains stable when detection probabilities
    are learned from limited data." (PDF p. 1)
  - "This theorem certifies that even when detection rates are estimated from finite samples, the greedy algorithm
    continues to provide strong guarantees." (PDF p. 4)
- **Says.**
  - Arrivals are Poisson, with a log-Gaussian Cox intensity. Each sensor's detection probability is p ∈ [0, 1].
  - Expected detected targets, C(a), is monotone submodular.
  - Estimation error enters through a Hoeffding term that shrinks as N^−1/2.
- **I conclude.**
  - The closest recent analogue to "traffic per route as a parameter plus a filtered, probabilistic detector" (**one
    paper**).
  - Its guarantee needs N samples per sensor. A never-exposed sensor has N = 0, so its value comes from the prior
    alone and must be labelled so (**mine**).

### M5 · Mohan, Pearl
- **Title.** Graphical models for processing missing data. **Venue.** JASA 116(534):1023–1037, 2021.
- **URL / OA PDF.** https://arxiv.org/pdf/1801.03583
- **DOI.** 10.1080/01621459.2021.1874961 (Crossref) · **BibTeX key.** `mohan2021graphical`
- **Read.** Abstract, §1, §2.2, §3 (first example) (PDF pp. 1–3, 7–8, 11–13).
- **Quotes.**
  - "Failing this assumption, there is no guarantee that estimates produced by current software will be less biased
    than those produced by complete case analysis." (PDF p. 3)
  - "Data that are not MAR or MCAR fall under the MNAR category." (PDF p. 8)
  - "That is, regardless of how large the sample or how clever the imputation, no algorithm exists that produces
    consistent estimate of P(G,O,A)." (PDF p. 12)
- **Says.** It defines MCAR, MAR and MNAR graphically. When a variable causes its own missingness (O → R_O), the joint
  distribution can be non-recoverable.
- **I conclude.**
  - The mapping to this project (**mine**) is in §1.2 item 2:
    - dropping never-firing sensors is selection on the outcome, outside Rubin's classes;
    - cells for unrun faults are missing by design (MAR given the catalogue);
    - content-dependent trace sampling is the self-masking MNAR case.
  - Missingness from entry *traffic* is closer to MAR, because the ledger observes it at the entry. Interior exposure
    is projected, not observed (**mine**).
  - Where a quantity is non-recoverable, the remedy is design or an explicit assumption, not more data (**general
    practice**).

### M6 · Seaman, Galati, Jackson, Carlin
- **Title.** What is meant by "missing at random"? **Venue.** Statistical Science 28(2):257–268, 2013.
- **URL / OA PDF.** https://arxiv.org/pdf/1306.2812
- **DOI.** 10.1214/13-STS415 (Crossref) · **BibTeX key.** `seaman2013missing`
- **Read.** Abstract, §1, §5.1 (PDF pp. 1, 7).
- **Quotes.**
  - "it is often said that if data are missing at random, valid inference using likelihood approaches (including
    Bayesian) can be obtained ignoring the missingness mechanism. Unfortunately, the term "missing at random" has been
    used inconsistently and not always clearly" (PDF p. 1)
  - Rubin (1976), as quoted there: "When making direct-likelihood or Bayesian inferences about θ, it is appropriate to
    ignore the process that causes missing data if the missing data are missing at random and the parameter of the
    missing data process is "distinct" from θ" (PDF p. 7)
- **I conclude.** "Ignorable" has two conditions: MAR, and distinct parameters. In this project the process that
  hides a sensor (traffic, fault) shares parameters with what we estimate (detection), so the second condition is
  doubtful as well (**mine**).

### M7 · Rubin · **not read**
- **Title.** Inference and missing data. **Venue.** Biometrika 63(3):581–592, 1976.
- **DOI.** 10.1093/biomet/63.3.581 (Crossref) · **BibTeX key.** `rubin1976inference`
- The OUP PDF was blocked. It is cited only through M5 and M6.

### M8 · Qian, Zhao, Wang, Gao, Chen, Ling, Deng
- **Title.** ARMOR: a robust self-supervised framework for root cause analysis in microservices under missing modality.
  **Venue.** ASE 2026 (per arXiv v3 header; ACM DOI still a placeholder); arXiv 2603.25538.
- **URL / OA PDF.** https://arxiv.org/pdf/2603.25538
- **DOI.** 10.48550/arXiv.2603.25538 (DataCite) · **BibTeX key.** `qian2026armor`
- **Read.** Abstract, §1, §3 (training), §5.3, §6.1 (PDF pp. 1–2, 5, 8–10).
- **Quotes.**
  - "While recent unified frameworks leverage multimodal data for joint optimization, they unrealistically assume
    perfect data completeness. In practice, network fluctuations and agent failures frequently cause missing
    modalities." (PDF p. 1)
  - "When a Prometheus agent goes offline, filling its missing channels with zero tells the model that every monitored
    resource sits at exactly zero consumption [44, 53]. That is precisely the signature of a healthy idle service, not
    a failing one." (PDF p. 2)
  - "In the rare case where a modality has been persistently absent from the archive to an extent beyond the stochastic
    dropout simulated during training, the missing-aware fusion module loses its explicit training signal." (PDF p. 10)
- **Says.** Missingness is simulated as random dropout of whole modalities or channels during training and testing.
- **I conclude.**
  - The microservice field's handling of missing telemetry is model-side robustness. It assumes MCAR-like dropout,
    and its authors say it fails when a modality is persistently absent (**one paper**).
  - "Zero looks healthy" is the same error as scoring an unobserved sensor 0 (**mine**).

### M9 · Zhang, Xie, Anand, Vigfusson, Mace
- **Title.** The benefit of hindsight: tracing edge-cases in distributed systems. **Venue.** NSDI 2023, pp. 321–339.
- **URL / OA PDF.** https://www.usenix.org/system/files/nsdi23-zhang-lei.pdf
- **DOI.** none; USENIX does not issue DOIs. **BibTeX key.** `zhang2023hindsight`
- **Read.** Abstract, §1, §2.2 (PDF pp. 2–3).
- **Quotes.**
  - "frameworks can indiscriminately select requests to trace when they enter the system (head sampling), but this is
    unlikely to capture a relevant edge-case trace because the framework cannot know which requests will be
    problematic until after-the-fact." (PDF p. 2)
  - "Retroactive sampling ultimately reports the same volume of trace data as other sampling methods, but ensures that
    edge-case traces are not missed." (PDF p. 2)
- **I conclude.** Sampling makes absence depend on the outcome: rare and faulty requests are the ones lost. That is
  MNAR by design. Retroactive collection removes it at the source (**one paper**).

### M10 · Huang, Chen, Chen, Chen, Yu, He, Wang, Zhang, Zhou
- **Title.** Mint: cost-efficient tracing with all requests collection via commonality and variability analysis.
  **Venue.** ASPLOS 2025, pp. 683–697.
- **URL / OA PDF.** https://arxiv.org/pdf/2411.04605
- **DOI.** 10.1145/3669940.3707287 (Crossref; resolves to ACM DL) · **BibTeX key.** `huang2025mint`
- **Read.** Abstract, §1, §2.2 (PDF pp. 1–4).
- **Quotes.**
  - "previous approaches typically used a '1 or 0' sampling strategy: retaining sampled traces while completely
    discarding unsampled ones." (PDF p. 1)
  - "some traces that need to be analyzed cannot be determined until the analysis is performed." (PDF p. 4)
  - "the average miss rate for trace queries at Alibaba over the past 30 days was 27.17%, indicating that a
    significant number of traces that need to be analyzed were filtered out due to sampling." (PDF p. 4)
- **I conclude.** Scope **one paper** (Alibaba, 30 days): a production measurement that sampling-induced absence is
  large.

### M11 · Xie, Zhang, Geng, Zhang, Ma, Nie, Yao, Xu, Sun, Li, Pei
- **Title.** Microservice root cause analysis with limited observability through intervention recognition in the
  latent space. **Venue.** KDD 2024, pp. 6049–6060.
- **URL / OA PDF.** https://netman.aiops.org/wp-content/uploads/2024/07/LatentScope_CameraReady_final.pdf (CC-BY)
- **DOI.** 10.1145/3637528.3671530 (Crossref) · **BibTeX key.** `xie2024latentscope`
- **Read.** Abstract, §1, §2.3 with Table 1 (PDF pp. 1–2).
- **Quotes.**
  - "However, many heterogeneous RCCs exist with limited observability in real-world microservices systems. Further,
    we find that the limited observability may result in inaccurate RCA through real-world failures in eBay." (PDF p. 1)
  - "Another reason for the limited observability is the absence of direct monitoring metrics for non-observable
    services (such as third-party services, see 2.3)." (PDF p. 2)
  - "The main idea is that latent variables are not required to be observed." (PDF p. 2)
- **Says.** In Table 1 (eBay, 6 months), 63.59 % of faults had a third-party-service root cause, and those services lack
  direct metrics.
- **I conclude.** In RCA, an unmonitored component is a latent node to infer, not a node to delete. The same move
  applies to a placement's ground set (**one paper** for RCA; **mine** for placement).

### M12 · Caetano, Arone, Maciel
- **Title.** Root cause analysis with latent confounders using partial ancestral graphs. **Venue.** arXiv preprint
  2606.20912, 2026.
- **URL / OA PDF.** https://arxiv.org/pdf/2606.20912
- **DOI.** 10.48550/arXiv.2606.20912 (DataCite) · **BibTeX key.** `caetano2026pagrca`
- **Read.** Abstract, §1 (PDF p. 1).
- **Quotes.**
  - "existing frameworks assume causal sufficiency, failing to account for the unobserved latent variables prevalent
    in real-world environments." (PDF p. 1)
  - "When effects are structurally unidentifiable, our framework (for the first time in the RCA literature) integrates
    partial identification to evaluate and score candidates using analytical causal bounds." (PDF p. 1)
- **I conclude.** When the unobserved part cannot be identified, report bounds (R3). This is the general idea; the
  RCA method itself does not transfer (**one paper**).

### M13 · Borges, Bauer, Werner, Gebauer, Tai
- **Title.** Informed and assessable observability design decisions in cloud-native microservice applications.
  **Venue.** ICSA 2024, pp. 69–78.
- **URL / OA PDF.** https://arxiv.org/pdf/2403.00633
- **DOI.** 10.1109/ICSA59870.2024.00015 (Crossref; resolves to IEEE Xplore) · **BibTeX key.** `borges2024informed`
- **Read.** Abstract, §1, §4.1 (PDF pp. 1, 4).
- **Quotes.**
  - "these architectural design decisions are not supported by systematic methods and typically just rely on
    "professional intuition"." (PDF p. 1)
  - "If the detection mechanism is not able to detect the fault, it suggests that either (i) metric m is unsuitable to
    detect f (ii) the parameters of metric m are not set appropriately or (iii) the function parameters of the
    detection mechanism d are not tuned correctly." (PDF p. 4)
  - "If a fault is not visible in any metric of the system, it implies that this fault is not covered by the system's
    observability, and thus the fault coverage for fault f is 0." (PDF p. 4)
- **Says.** Fault coverage FC is averaged over the *collected* metrics M.
- **I conclude.**
  - The closest related work. Its non-detection reasons list has no "no opportunity" entry. Its denominator is the
    observed set.
  - So this note's gap applies to it too (**one paper**). That is a positioning point for the paper.

### M14 · Srinivas, Husain, Parayil, Choure, Bansal, Rajmohan
- **Title.** Intelligent monitoring framework for cloud services: a data-driven approach. **Venue.** ICSE-SEIP 2024,
  pp. 381–391.
- **URL / OA PDF.** https://arxiv.org/pdf/2403.07927
- **DOI.** 10.1145/3639477.3639753 (Crossref; resolves to ACM DL) · **BibTeX key.** `srinivas2024intelligent`
- **Read.** Abstract, §1, §2 (definitions), §3.4 (Insight 3), §3.5, §4.1 (PDF pp. 1–2, 6–8).
- **Quotes.**
  - "Gaps in monitoring can lead to delay in incident detection and significant negative customer impact." (PDF p. 1)
  - "As a result, monitors often have incomplete coverage which leads to production issues, or, redundancy which
    results in noise and wasted effort." (PDF p. 1)
  - "If the presence of a resource class within a service probabilistically implies the existence of another resource
    class, this signal can be utilized to suggest missing monitors for an existing service." (PDF p. 6)
- **Says.**
  - 30,000+ monitors from 791 Microsoft services, organised in an ontology.
  - Recommendations for a new service come from similar services, by cosine similarity on dependencies.
- **I conclude.** Borrowing strength across services to propose *missing* monitors is industrial practice at one
  company. It is the closest thing to a prior over unobserved sensors in this field (**one paper**).

### M15 · Liyanage, Böhme, Tantithamthavorn, Lipp
- **Title.** Reachable coverage: estimating saturation in fuzzing. **Venue.** ICSE 2023, pp. 371–383.
- **URL / OA PDF.** https://mboehme.github.io/paper/ICSE23-effectiveness.pdf
- **DOI.** 10.1109/ICSE48619.2023.00042 (Crossref) · **BibTeX key.** `liyanage2023reachable`
- **Read.** Abstract, §I, §III (Chao-type estimators) (PDF pp. 1–4).
- **Quotes.**
  - "Using static program analysis, we can compute an upper bound on the number of reachable coverage elements, e.g.,
    by extracting the call graph. However, we cannot decide whether a coverage element is reachable in general."
    (PDF p. 1)
  - "For static analysis tools, we find that they over- and under-count reachable coverage." (PDF p. 2)
  - "in the context where the reachable coverage is empirically unknown, we find that all estimators predict false
    peaks: More coverage can be achieved upon reaching the predicted reachable coverage." (PDF p. 2)
- **I conclude.**
  - Protocol §1b's projection (from source and call graph) is the static side, and it will over- and under-count.
  - The statistical side under-estimates. Both are needed, and neither is ground truth (**one paper**).

### M16 · Böhme
- **Title.** STADS: software testing as species discovery. **Venue.** ACM TOSEM 27(2), Art. 7, 2018.
- **URL / OA PDF.** https://mboehme.github.io/paper/TOSEM18.pdf
- **DOI.** 10.1145/3210309 (Crossref) · **BibTeX key.** `bohme2018stads`
- **Read.** Abstract, §2.1 (PDF pp. 1, 9).
- **Quotes.**
  - "Failing to discover a vulnerability, does not mean that none exists—even if the fuzzer was run for a week (or a
    year)." (PDF p. 1)
  - "In ecology, the discovery probability U gives the proportion of individuals in the assemblage whose species are
    not represented in the sample." (PDF p. 9)
  - "The sample coverage C = 1 −U is the complement of the discovery probability" (PDF p. 9)
- **I conclude.** The discovery probability is the right single number for "how much sensor behaviour is unseen" (R5).
  It describes the sampled process, here the workload and fault catalogue, not the whole system (**one paper**).

### M17 · Orlitsky, Suresh, Wu
- **Title.** Optimal prediction of the number of unseen species. **Venue.** PNAS 113(47):13283–13288, 2016.
- **URL / OA PDF.** https://arxiv.org/pdf/1511.07428. The preprint title differs: "Estimating the number of unseen
  species: A bird in the hand is worth log n in the bush". The PNAS PDF was blocked, so I read the preprint.
- **DOI.** 10.1073/pnas.1607774113 (Crossref) · **BibTeX key.** `orlitsky2016optimal`
- **Read.** Abstract, §1, §3 (statistical models) (arXiv PDF pp. 1–3, 7).
- **Quotes.**
  - "This shows that the number of species can be estimated for a population log n times larger than that observed,
    a factor that grows arbitrarily large as n increases. We also show that this range is the best possible"
    (PDF p. 1)
  - "This question seems impossible to answer, since it refers to a column of Corbet's table that doesn't exist, the
    "0" column." (PDF p. 3)
  - "Each sample Xi is a subset of X where symbol x ∈ X appears with probability px and is absent with probability
    1 − px , independently of all other symbols." (PDF p. 7, Bernoulli-product model)
- **I conclude.**
  - "Episode = set of sensors that fired" is exactly the Bernoulli-product model, so incidence estimators apply.
  - Extrapolation beyond about log n times the observed episodes is provably unreliable (**one paper**; the
    estimator family is **general practice** in ecology).

### M18 · Doser, Finley, Kéry, Zipkin
- **Title.** spOccupancy: an R package for single-species, multi-species, and integrated spatial occupancy models.
  **Venue.** Methods in Ecology and Evolution 13(8):1670–1678, 2022.
- **URL / OA PDF.** https://arxiv.org/pdf/2111.12163 (preprint v2)
- **DOI.** 10.1111/2041-210X.13897 (Crossref) · **BibTeX key.** `doser2022spoccupancy`
- **Read.** Abstract, §1, §2.1, §2.3 (PDF pp. 1–3, 6, 8).
- **Quotes.**
  - "Imperfect detection, or the failure to observe a species during sampling where it is in fact present, is a
    ubiquitous complication that must be addressed when modeling species distributions" (PDF p. 3)
  - "We model the observed detection (1) or nondetection (0) of a study species during replicate visit k at site j,
    denoted yj,k , conditional on the true occupancy process, zj" (PDF p. 6)
  - "Species-specific regression coefficients for occupancy (βi ) and detection (αi ) are treated as random effects
    arising from community-level normal distributions, which leads to greater precision of species-specific effects
    (particularly for rare species)" (PDF p. 8)
- **Says.**
  - z_j ~ Bernoulli(ψ_j) and y_jk ~ Bernoulli(p_jk z_j). Spatial correlation is a nearest-neighbour GP.
- **I conclude.**
  - In this mapping, a site is a (sensor, fault) pair and a visit is an episode:
    - ψ = "does this sensor carry this fault's signal at all";
    - p = "does it show in a given episode", which depends on traffic and threshold.
  - Community-level random effects by channel × role give rarely exposed sensors a usable posterior. This is the
    concrete form of the user's "variance instead of a binary catch" (**general practice in ecology**; the mapping is
    **mine**, and I found no telemetry precedent).

### M19 · Carpenter (Stan case study of Dorazio et al. 2006)
- **Title.** Multiple species-site occupancy model. Stan case study, 2015, revised 2017.
- **URL.** https://mc-stan.org/learn-stan/case-studies/dorazio-royle-occupancy.html · **DOI.** none
- **BibTeX key.** `carpenter2017occupancy`
- **Read.** Data, model and likelihood sections (HTML).
- **Quotes.**
  - On the super-community size S: "is just required to be large enough to encompass all possible species that might
    be present; it will affect the estimation of various model parameters, but not the derived quantities of interest
    such as the estimated total number of species available at a site"
  - On w_i, the availability of species i: "because a species must be available if it was detected, whereas" for the
    never-detected species it "is a latent parameter".
  - Pr_available is "the posterior expectation of" w_i "for species never detected for the parameter values being
    used."
- **I conclude.**
  - This is a worked recipe for giving never-observed members of a population a probability instead of −∞
    (**tool-specific** write-up).
  - The super-population here would come from the projection map plus static call sites (**mine**).

### M20 · Dorazio, Royle, Söderström, Glimskär · **not read**
- **Title.** Estimating species richness and accumulation by modeling species occurrence and detectability.
  **Venue.** Ecology 87(4):842–854, 2006.
- **DOI.** 10.1890/0012-9658(2006)87[842:ESRAAB]2.0.CO;2 (Crossref) · **BibTeX key.** `dorazio2006estimating`
- The Wiley PDF was blocked. Used only through M19.

### M21 · MacKenzie, Nichols, Lachman, Droege, Royle, Langtimm · **not read**
- **Title.** Estimating site occupancy rates when detection probabilities are less than one. **Venue.** Ecology
  83(8):2248–2255, 2002.
- **DOI.** 10.1890/0012-9658(2002)083[2248:ESORWD]2.0.CO;2 (Crossref) · **BibTeX key.** `mackenzie2002estimating`
- The Wiley PDF was blocked. It is the original occupancy model, cited by M18 and M22. Not used as support.

### M22 · Halstead, Rose, Kleeman
- **Title.** Time-to-detection occupancy methods: performance and utility for improving efficiency of surveys.
  **Venue.** Ecological Applications 31(3):e2267, 2021.
- **URL / OA.** https://pmc.ncbi.nlm.nih.gov/articles/PMC8047884/
- **DOI.** 10.1002/eap.2267 (Crossref) · **BibTeX key.** `halstead2021time`
- **Read.** Abstract, Introduction, Methods (model definitions) (HTML).
- **Quotes.**
  - "Occupancy methods propelled the quantitative study of species distributions forward by separating the observation
    process, or the imperfect detectability of species, from the ecological processes of interest governing species
    distributions."
  - "Mean time to detection is related to the detection rate, λ, as λ = 1/μ" (the same sentence then gives detection
    probability as p = 1 − exp(−λt), with t the survey duration; the HTML flattens the superscript, so it is
    paraphrased here)
  - "an empirical test of time-to-detection methods against known occurrence found overestimates of detection
    probability and underestimates of occupancy when heterogeneity in detection probability was not accounted for"
- **I conclude.**
  - Time-to-detection with imperfect detection is an established design. Its detection probability has the same form
    as the project's traffic model for the root, with survey duration in place of the fault window.
  - Heterogeneity between sensors must be modelled, or detection is over-estimated (**general practice in ecology**;
    the transfer is **mine**).

### M23 · Christakis, Fowler
- **Title.** Social network sensors for early detection of contagious outbreaks. **Venue.** PLoS ONE 5(9):e12948, 2010.
- **URL / OA PDF.** https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0012948
- **DOI.** 10.1371/journal.pone.0012948 (Crossref) · **BibTeX key.** `christakis2010social`
- **Read.** Abstract, Fig. 2 caption, Methods, Results (PDF pp. 1–3).
- **Quotes.**
  - "The amount of lead time will depend on features of the outbreak and the network at hand." (PDF p. 1)
  - "Central individuals lie on more paths in a network compared to the average person in a population and are
    therefore more likely to be infected early" (PDF p. 2)
  - "By December 31, 2009, the cumulative incidence of flu in our sample was 8% based on diagnoses by medical staff,
    and it was 32% based on self-reports" (PDF p. 3)
- **I conclude.**
  - Sensors were chosen by **structural position** (being on more paths), not by past catches. That is a selection
    rule that does not depend on what happened to be observed.
  - The 8 % vs 32 % gap shows that a channel's ascertainment must be measured, not assumed (**one paper**).

### M24 · Li, Offutt
- **Title.** Test oracle strategies for model-based testing. **Venue.** IEEE TSE 43(4):372–395, 2017.
- **URL / OA PDF.** https://www.albany.edu/faculty/offutt/research/papers/testOracle.pdf
- **DOI.** 10.1109/TSE.2016.2597136 (Crossref) · **BibTeX key.** `li2017test`
- **Read.** Abstract, §1, §2.2 (PDF pp. 1, 3).
- **Quotes.**
  - "When tests are executed, a fault may be triggered to produce an error state, which then propagates to an external
    failure. This is known as the Reachability, Infection, and Propagation (RIP) model" (PDF p. 1)
  - "But even if a fault propagates to a failure, it is only useful if the failing part of the output state is
    revealed to the tester." (PDF p. 1)
  - "if the oracle does not check the particular portion of the state that contains an erroneous value, the oracle
    will not see the failure." (PDF p. 3)
- **I conclude.** RIPR is the standard four-step vocabulary for "why did nothing show". It maps onto the table in §1.1.
  It lets the paper say *which* step failed instead of "not detected" (**general practice** in software testing).

### M25 · Clark, Bradburn, Love, Altman
- **Title.** Survival analysis part I: basic concepts and first analyses. **Venue.** British Journal of Cancer
  89(2):232–238, 2003.
- **URL / OA.** https://pmc.ncbi.nlm.nih.gov/articles/PMC2394262/
- **DOI.** 10.1038/sj.bjc.6601118 (Crossref) · **BibTeX key.** `clark2003survival`
- **Read.** Sections "Censoring makes survival analysis different" and "Uninformative censoring" (HTML).
- **Quotes.**
  - "Such censored survival times underestimate the true (but unknown) time to event."
  - "Standard methods used to analyse survival data with censored observations are valid only if the censoring is
    'noninformative'."
  - "Informative censoring may occur when patients withdraw from a clinical trial because of drug toxicity or worsening
    clinical condition."
- **I conclude.**
  - Charging a miss at the window end is right censoring, which is standard. It is valid only if censoring is
    non-informative.
  - A fault that stops traffic, and so also ends the sensor's chance to fire, makes the censoring informative
    (**general practice**, applied here by me).
  - A sensor that was never exposed is a different error: it was never at risk, so it does not belong in the risk set
    at all (**mine**). In both cases exposure must be recorded, not assumed.

### M26 · Thibaux, Jordan
- **Title.** Hierarchical beta processes and the Indian buffet process. **Venue.** AISTATS 2007, PMLR 2:564–571.
- **URL / OA PDF.** http://proceedings.mlr.press/v2/thibaux07a/thibaux07a.pdf
- **DOI.** none; PMLR does not issue DOIs. **BibTeX key.** `thibaux2007hierarchical`
- **Read.** Abstract, §1, §6, §7 (PDF pp. 1, 5, 7).
- **Quotes.**
  - "For categories to share words, B must be discrete. On the other hand, B is unknown a priori, so it must be random.
    This suggests that B should itself be generated as a realization of a beta process." (PDF p. 5)
  - "Estimating pj,ω as its maximum likelihood mj,ω /nj,ω leads to many features having probability 0 or 1, making
    inference impossible." (PDF p. 7)
  - "allows the number of known features to grow with data, and the number of unknown features to serve as evidence
    for belonging to a poorly known category, one for which we have little training data." (PDF p. 7)
- **I conclude.**
  - This is the user's −∞ point, stated in 2007: maximum-likelihood rates give 0 for anything unseen.
  - A hierarchical beta process shares a base measure across groups. Groups could be systems, and features could be
    sensors, so a sensor unseen in one SUT borrows from the others (**one paper**; the mapping is **mine**).

### M27 · Zhao, Jia, He, Li, Huang
- **Title.** ZeroLog: zero-label generalizable cross-system log-based anomaly detection. **Venue.** arXiv preprint
  2511.05862, 2025.
- **URL / OA PDF.** https://arxiv.org/pdf/2511.05862
- **DOI.** 10.48550/arXiv.2511.05862 (DataCite) · **BibTeX key.** `zhao2025zerolog`
- **Read.** Abstract, §I, §II (PDF pp. 1–3).
- **Quotes.**
  - "features learned on the source system may suffer from semantic mismatch, where identical log patterns carry
    different meanings across systems, and distribution drift, where the source feature manifold fails to cover the
    target's data space" (PDF p. 2)
  - "They exhibit significant differences in terms of field formats (e.g., timestamp precision), log template
    granularity (operation-level vs. system-level), semantic space (storage operations vs. computational tasks vs.
    cloud services), and data scale." (PDF p. 3)
- **I conclude.** Transfer of detectors across systems is an active topic. Even with a shared embedding, the source
  may not cover the target's space. A placement learned on one SUT carries the same risk (**one paper**; HDFS, BGL
  and OpenStack, not microservices).

### M28 · OpenTelemetry semantic conventions 1.44.0 (specification)
- **Pages.** Index; "Attribute requirement levels"; "HTTP metrics".
- **URLs.** https://opentelemetry.io/docs/specs/semconv/ ,
  https://opentelemetry.io/docs/specs/semconv/general/attribute-requirement-level/ ,
  https://opentelemetry.io/docs/specs/semconv/http/http-metrics/ (accessed 2026-10-04)
- **DOI.** none · **BibTeX key.** `otel2026semconv`
- **Quotes.**
  - "The Semantic Conventions define a common set of (semantic) attributes which provide meaning to data when
    collecting, producing and consuming it."
  - "The benefit to using Semantic Conventions is in following a common naming scheme that can be standardized across
    a codebase, libraries, and platforms."
  - "Instrumentations MAY offer a configuration option to disable Recommended attributes."
- **Says.** `http.server.request.duration` is a histogram with `http.request.method` Required and `error.type`
  Conditionally Required. Other attributes are Recommended or Opt-In.
- **I conclude.**
  - The shared vocabulary exists for names and types. It does not cover detection behaviour.
  - Under it, the absence of a Recommended or Opt-In attribute can be a configuration choice. So "absent" must be
    read against the instrumentation's configuration (**tool-specific**).

### Not read (named for completeness; not used as support)
- Zhang, Jia, Shen, Zhu, Li. *MetaLog: generalizable cross-system anomaly detection from logs with meta-learning.*
  ICSE 2024. DOI 10.1145/3597503.3639205 (Crossref). The ACM PDF was blocked; M27 cites it.
- Ganatra, Parayil, Ghosh, Kang, Ma, Bansal, Nath, Mace. *Detection is better than cure: a cloud incidents
  perspective.* ESEC/FSE 2023, pp. 1891–1902. DOI 10.1145/3611643.3613898 (Crossref). Not retrieved.
- El-Arini, Veda, Shahaf, Guestrin. *Turning down the noise in the blogosphere.* KDD 2009 (noisy-OR coverage). Not
  retrieved. `research/literature-20261002/DIMENSIONS.md` §1.4 records it as read in full.
- Mangel, Samaniego. *Abraham Wald's work on aircraft survivability.* JASA 1984. This is the usual origin story for
  "survivorship bias". Not retrieved.

### Project files read (read-only)
- `CLAUDE.md`, "Modality scope". Catalogues are trace-only. Logs scored in the previous version. Multi-modality is
  framing and future work for this paper.
- `research/PROTOCOL_DRAFT_20261002.md`: §1b projection map; §2 planted positives and "disappear only if the posture
  collects"; decisions 14–15 (objective; misses charged at the window end); round 7, decisions 26–29.
- `research/traffic-sweep/readout-hotel-r3/REVIEW.md` (instance). CPU throttle: the ledger detects 1/16 and the
  target's PSI 16/16, now excluded as actuator readback. At 0.05/s, each cell has 4 pre-onset requests, so the
  baseline "rests on 4 samples".
- `research/project-map/PROJECT_MAP.md` (four-state counts, §1.1). `research/visibility-map/MAP.md` (8 `NO-WORKLOAD`
  families).
- `research/literature-20261002/DIMENSIONS.md` §0, §1.1, §1.3, §1.4 (cross-reference only).

---

## 4. Decisions this note raises (classified, not taken)

| # | question | class | recommendation |
|---|---|---|---|
| a | Ground set of f(S): as now (catalog universe with gain 0 for unobserved sensors; observed vocabulary in §2), or projected sensors with an explicit unknown state? | ▶ user (changes what the objective counts) | as now stays primary for this paper; projected is reported as the optimistic bound (R3) |
| b | Are misses charged only for exposed episodes, with non-exposed ones `—`? | ▶ user (changes the primary outcome's definition) | yes for the primary metric; always report the exposure columns |
| b′ | Exposure threshold: any request on the route in the window, or at least k? And is interior exposure taken from the call-graph projection? | ▶ user (fixes the primary denominator under b) | state it before any rescoring; report the k grid beside it |
| c | Exposure columns, exposure-floor row, Chao2 / discovery-probability diagnostic | engineering default | add; record the defaults in the analysis descriptor |
| d | Hierarchical occupancy model as the probabilistic dimension (D3) | ▶ user (new analysis family) | future work. A small offline pilot on retained Hotel episodes is possible, but n_eff is tens |
| e | Retroactive or always-on collection (F6) | ▶ user (changes what the harness emits) | future work only |

---

## 5. Verification log
- **Quotes.** `checkdoc.py` (session scratchpad, `lit_missing/`) parses every quoted segment out of this file and
  searches for it in the source's `pdftotext` extract or HTML text. Result: **73 segments, 0 misses**.
  - 67 match after whitespace and line-break normalisation alone.
  - 6 match only when spaces and hyphens are also ignored:
    - M1 ×2 and M2 ×2 contain formula symbols;
    - M11 ×1 has a hyphenated word split across a line;
    - one is the second Borges (M13) quote. It had to be checked against the page-4 right column extracted
      separately, because the page is two-column.
  - The checker was seen failing on a planted defect. One word changed in an ARMOR quote ("idle" → "busy") gave
    `MISS`; the true quote gave a match.
- **DOIs.** Crossref `api.crossref.org/works/{doi}` titles match for every DOI listed (2026-10-04). arXiv DOIs were
  checked on DataCite. `10.1613/jair.3278` returned 404 at doi.org and is marked so. No DOI was guessed.
- **What was not checked.** Every quote, number and DOI above was checked by the script. Nothing else was:
  - the mappings to this project (marked **mine**);
  - the derivation in M1;
  - whether R3's optimistic class rule is well defined.
- **Independent review: one round, applied.**
  - **Who.** A Fable `adversarial-review` subagent, read-only, 2026-10-04. One reviewer, same provider family, so not
    a cross-provider panel.
  - **What it checked.** The note against the source extracts, `PROJECT_MAP.md`, `MAP.md`, `REVIEW.md`, the protocol
    draft, `DIMENSIONS.md`, `research/submodularity.py` and `research/observed_requirements.py`.
  - **Result.** Every project count and source figure it checked matched. It found 5 major and 9 minor problems in
    the sentences, and all 14 were applied in this version. The major ones:
    - the ground set was misdescribed. The live f(S) universe is the activation catalog, with gain 0 for unobserved
      sensors;
    - the M1/F3 submodularity result holds for the surrogate R only, under two premises;
    - F4's "variance does not matter" holds only for linear, independent cases;
    - the MNAR mapping was wrong for unrun faults;
    - "informative censoring" had been applied to never-exposed sensors, which were never at risk.
  - **Not done.** No second round on the revised text. The **mine** conclusions still need a claim-by-claim review
    before any of them enters the paper.
