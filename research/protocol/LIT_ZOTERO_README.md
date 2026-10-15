# Zotero import: literature notes 2026-10-03/04

Built from three literature notes in `research/protocol/`: `LIT_TIME_SEMANTICS.md` (L1-L40, section 3),
`LIT_DETECTION_RULES.md` (D1-D64, section 3), `LIT_MISSING_SENSORS.md` (M1-M28, section 3). Scope is exactly the
numbered sources in each note's own section 3 — items named only in a "not read, never used as support" list (no
L/D/M id) are out of scope.

## Counts

| note | sources (section 3) |
|---|---|
| LIT_TIME_SEMANTICS.md | 40 (L1-L40) |
| LIT_DETECTION_RULES.md | 64 (D1-D64) |
| LIT_MISSING_SENSORS.md | 28 (M1-M28) |
| **raw total** | **132** |
| **unique sources after dedup** | **112** |

20 raw citations collapse into 18 duplicate sources (cited from more than one note). Found by matching DOI, and
where no DOI exists, by matching title/venue/URL:

1. Leskovec, Krause, Guestrin, Faloutsos, VanBriesen, Glance 2007, *Cost-effective outbreak detection in networks* (KDD) — **L1, D30, M1**
2. Krause, Leskovec, Guestrin, VanBriesen, Faloutsos 2008, water-network sensor placement (JWRPM) — **L2, D31**
3. Ostfeld et al. 2008, *The Battle of the Water Sensor Networks (BWSN)* (JWRPM) — **L3, D32**
4. Basseville, Nikiforov 1993, *Detection of Abrupt Changes* (book) — **L4, D17**
5. Lavin, Ahmad 2015, Numenta Anomaly Benchmark (NAB) (ICMLA) — **L6, D19**
6. Tatbul, Lee, Zdonik, Alam, Gottschlich 2018, *Precision and Recall for Time Series* (NeurIPS) — **L7, D20**
7. Thurgood et al. / Google, *Alerting on SLOs* (SRE Workbook ch. 5) — **L11, D11**
8. Borges, Bauer, Werner, Gebauer, Tai 2024, *Informed and Assessable Observability Design Decisions* (ICSA) — **L15, D52, M13**
9. Borges, Bauer, Werner 2024, OXN poster (ICSA-C) — **L16, D53**
10. Lee, Yang, Chen, Su, Lyu 2023, *Eadro* (ICSE) — **L19, D56**
11. Pham, Ha, Zhang 2024, *BARO* (FSE) — **L20, D46**
12. Pham, Zhang, Ha, Salim, Zhang 2025, *RCAEval* (WWW Companion) — **L21, D54**
13. Fang et al. 2026, *Rethinking the Evaluation of Microservice RCA* (FSE) — **L22, D55**
14. Ping, Mazhar, Wang, Song, Mäntylä 2026, *AnoMod* (MSR) — **L23, D58**
15. Chen et al. 2025, *AIOpsLab* (MLSys/arXiv) — **L24, D35**
16. Wu, Keogh 2021, *Current Time Series Anomaly Detection Benchmarks are Flawed* (TKDE) — **L40, D51**
17. Clark, Bradburn, Love, Altman 2003, *Survival Analysis Part I* (Br. J. Cancer) — **D33, M25**
18. Krause, Singh, Guestrin 2008, *Near-Optimal Sensor Placements in Gaussian Processes* (JMLR) — **D48, M2**

Of the 112 unique sources:
- **79** have a working DOI (including arXiv-issued `10.48550/arXiv.*` DOIs) and are read: these are the 79 lines in
  `LIT_ZOTERO_IDENTIFIERS.txt`.
- **30** have no DOI or arXiv identifier at all (tool/vendor docs, source code, specs, two O'Reilly books, one PhD
  dissertation, two no-DOI JMLR/PMLR articles, one NSDI paper, one Stan case study, one OpenTelemetry spec page):
  written by hand into the `.bib` with `url` + `urldate`, excluded from the identifiers file.
- **3** are explicitly marked "not read" in their own note (`M7` Rubin 1976, `M20` Dorazio et al. 2006, `M21`
  MacKenzie et al. 2002 — all paywalled originals, cited only through other sources in `LIT_MISSING_SENSORS.md`):
  they have working DOIs and get a full `.bib` entry with `note = {...; not read}`, but are excluded from the
  identifiers file per the task's instruction to exclude "not read" sources.

  79 + 30 + 3 = 112.

## How to import

- **By identifier (fastest, 79 of 112 sources):** in Zotero, select a collection, then *File -> Add Item by
  Identifier* (or the magic-wand icon in the toolbar), paste the entire contents of `LIT_ZOTERO_IDENTIFIERS.txt`,
  and go. Zotero resolves each DOI (including the `10.48550/arXiv.*` ones) and attaches metadata; it will usually
  also attach an open-access PDF where one is indexed.
- **By .bib (all 112 sources, including the 30 hand-written and the 3 not-read):** *File -> Import...* ->
  select `LIT_HARDENING_20261003.bib` -> import into a new or existing collection. This is the only path that
  brings in the 33 sources that have no DOI/arXiv or are marked not-read, and it also carries the `note` field
  (which note(s) cite the source, and "not read" where it applies) and the `url` field (the OA PDF the note used).
- The two are not additive without de-duplication: importing both will create duplicate items for the 79 DOI-backed
  sources (Zotero's own duplicate-item merge handles this if wanted). For a single clean pass, use the `.bib` file
  alone — it is the complete set.

## Checks performed

- All 82 DOI-bearing sources (79 read + 3 not-read) were fetched from `https://doi.org/<doi>` with
  `Accept: application/x-bibtex`, 2026-10-04, ~0.3 s apart. **82/82 returned HTTP 200 with a BibTeX record on the
  first attempt** (log: fetch run during this task; no retries were needed).
- `LIT_ZOTERO_IDENTIFIERS.txt` has **79** lines, equal to the 79 rows below marked `read` that carry a DOI.
- A Python check parsed `LIT_HARDENING_20261003.bib` as 112 blank-line-separated blocks: every block starts with
  `@`, every block's braces balance to zero, and all 112 keys are unique.

## Identifiers that failed to resolve

None. All 79 identifiers in `LIT_ZOTERO_IDENTIFIERS.txt` (and the 3 additional not-read DOIs used only in the
`.bib`) returned HTTP 200 with a parseable BibTeX record on the first request.

## All sources

Sorted by first citing id (L, then D, then M). "note ids" lists every note that cites the source. "DOI / arXiv /
URL" is the DOI used for the `.bib`/identifiers entry, or (for the 30 no-identifier sources) the URL used instead.

| note ids | short title | year | DOI / arXiv / URL | OA PDF | status |
|---|---|---|---|---|---|
| L1, D30, M1 | Leskovec -- Cost-effective outbreak detection in networks | 2007 | 10.1145/1281192.1281239 | https://www.cs.cmu.edu/~jure/pubs/detect-kdd07.pdf | read |
| L2, D31 | Krause -- Efficient Sensor Placement Optimization for Securing Large Water Di... | 2008 | 10.1061/(ASCE)0733-9496(2008)134:6(516) | https://las.inf.ethz.ch/files/krause08efficient.pdf | read |
| L3, D32 | Ostfeld -- The Battle of the Water Sensor Networks (BWSN): A Design Challenge ... | 2008 | 10.1061/(ASCE)0733-9496(2008)134:6(556) | https://cs.stanford.edu/people/jure/pubs/bwsn-jwrpm09.pdf | read |
| L4, D17 | Basseville -- Detection of Abrupt Changes: Theory and Application | 1993 | https://people.irisa.fr/Michele.Basseville/kniga/kniga.pdf | https://people.irisa.fr/Michele.Basseville/kniga/kniga.pdf | read |
| L5 | Lorden -- Procedures for Reacting to a Change in Distribution | 1971 | 10.1214/aoms/1177693055 | - | read |
| L6, D19 | Lavin -- Evaluating Real-Time Anomaly Detection Algorithms - the Numenta Ano... | 2015 | 10.1109/ICMLA.2015.141 | https://arxiv.org/pdf/1510.03336 | read |
| L7, D20 | Tatbul -- Precision and Recall for Time Series | 2018 | 10.48550/arXiv.1803.03639 | https://arxiv.org/pdf/1803.03639 | read |
| L8 | Ren -- Time-Series Anomaly Detection Service at Microsoft | 2019 | 10.1145/3292500.3330680 | https://arxiv.org/pdf/1906.03821 | read |
| L9 | Paparrizos -- Volume Under the Surface: A New Accuracy Evaluation Measure for Tim... | 2022 | 10.14778/3551793.3551830 | https://www.vldb.org/pvldb/vol15/p2774-paparrizos.pdf | read |
| L10 | Akidau -- The Dataflow Model | 2015 | 10.14778/2824032.2824076 | https://www.vldb.org/pvldb/vol8/p1792-Akidau.pdf | read |
| L11, D11 | Thurgood -- Alerting on SLOs (ch. 5, The Site Reliability Workbook) | 2018 | https://sre.google/workbook/alerting-on-slos/ | https://sre.google/workbook/alerting-on-slos/ | read |
| L12 | Davidovic -- Incident Metrics in SRE: Critically Evaluating MTTR and Friends | 2021 | https://static.googleusercontent.com/media/sre.google/en//static/pdf/IncidentMeticsInSre.pdf | https://static.googleusercontent.com/media/sre.google/en//static/pdf/IncidentMeticsInSre.pdf | read |
| L13 | DORA -- DORA's software delivery performance metrics | 2026 | https://dora.dev/guides/dora-metrics-four-keys/ | https://dora.dev/guides/dora-metrics-four-keys/ | read |
| L14 | Chen -- On the Quality of Service of Failure Detectors | 2000 | http://disi.unitn.it/~montreso/ds/papers/fd-qos.pdf | http://disi.unitn.it/~montreso/ds/papers/fd-qos.pdf | read |
| L15, D52, M13 | Borges -- Informed and Assessable Observability Design Decisions in Cloud-Nat... | 2024 | 10.1109/ICSA59870.2024.00015 | https://arxiv.org/pdf/2403.00633 | read |
| L16, D53 | Borges -- OXN - Automated Observability Assessments for Cloud-Native Applicat... | 2024 | 10.1109/ICSA-C63560.2024.00035 | https://arxiv.org/pdf/2407.09644 | read |
| L17 | nymphbox -- Oxn (source code) | 2024 | https://github.com/nymphbox/oxn | https://github.com/nymphbox/oxn | read |
| L18 | Borges -- Continuous Observability Assurance in Cloud-Native Applications | 2025 | 10.1109/ICSA-C65153.2025.00036 | https://arxiv.org/pdf/2503.08552 | read |
| L19, D56 | Lee -- Eadro: An End-to-End Troubleshooting Framework for Microservices on... | 2023 | 10.1109/ICSE48619.2023.00150 | https://arxiv.org/pdf/2302.05092 | read |
| L20, D46 | Pham -- BARO: Robust Root Cause Analysis for Microservices via Multivariate... | 2024 | 10.1145/3660805 | https://arxiv.org/pdf/2405.09330 | read |
| L21, D54 | Pham -- RCAEval: A Benchmark for Root Cause Analysis of Microservice System... | 2025 | 10.1145/3701716.3715290 | https://arxiv.org/pdf/2412.17015 | read |
| L22, D55 | Fang -- Rethinking the Evaluation of Microservice RCA with a Fault Propagat... | 2026 | 10.1145/3797100 | https://arxiv.org/pdf/2510.04711 | read |
| L23, D58 | Ping -- AnoMod: A Dataset for Anomaly Detection and Root Cause Analysis in ... | 2026 | 10.1145/3793302.3793324 | https://arxiv.org/pdf/2601.22881 | read |
| L24, D35 | Chen -- AIOpsLab: A Holistic Framework to Evaluate AI Agents for Enabling A... | 2025 | 10.48550/arXiv.2501.06706 | https://arxiv.org/pdf/2501.06706 | read |
| L25 | Jha -- ITBench: Evaluating AI Agents across Diverse Real-World IT Automati... | 2025 | 10.48550/arXiv.2502.05352 | https://arxiv.org/pdf/2502.05352 | read |
| L26 | Huang -- Twin Graph-Based Anomaly Detection via Attentive Multi-Modal Learni... | 2023 | 10.1109/ASE56229.2023.00138 | https://arxiv.org/pdf/2310.04701 | read |
| L27 | Saha -- Rethinking Telemetry Design for Fine-Grained Anomaly Detection in 5... | 2026 | 10.1109/NOMS69089.2026.11668159 | https://arxiv.org/pdf/2510.27664 | read |
| L28 | Chaos Mesh -- Inspect Results of Chaos Experiments (docs v2.8.4); api/v1alpha1/co... | 2026 | https://chaos-mesh.org/docs/inspect-chaos-experiments/ | https://chaos-mesh.org/docs/inspect-chaos-experiments/ | read |
| L29 | ChaosBlade -- blade status (docs v1.7.1); cli/cmd/create.go, data/experiment.go | 2026 | https://chaosblade.io/en/docs/1.7.1/getting-started/chaosblade-tool-quick-start/cli-mode-user-guide/blade-status/ | https://chaosblade.io/en/docs/1.7.1/getting-started/chaosblade-tool-quick-start/cli-mode-user-guide/blade-status/ | read |
| L30 | LitmusChaos -- Resilience Probes (docs v3.32.0); stress-helper.go, event.go | 2026 | https://docs.litmuschaos.io/docs/concepts/probes | https://docs.litmuschaos.io/docs/concepts/probes | read |
| L31 | Gremlin -- Fault Injection > Experiments | 2026 | https://www.gremlin.com/docs/infrastructure-layer/attacks/ | https://www.gremlin.com/docs/infrastructure-layer/attacks/ | read |
| L32 | Netflix -- Chaos Monkey docs (Tracker; Configuration file format) | 2026 | https://netflix.github.io/chaosmonkey/Tracker/ | https://netflix.github.io/chaosmonkey/Tracker/ | read |
| L33 | Docker -- docker container pause / docker system events (docs); moby daemon/p... | 2026 | https://docs.docker.com/reference/cli/docker/container/pause/ | https://docs.docker.com/reference/cli/docker/container/pause/ | read |
| L34 | Linux kernel documentation -- Control Group v2 (cgroup.freeze); Freezer Subsystem (v1) | 2026 | https://docs.kernel.org/admin-guide/cgroup-v2.html | https://docs.kernel.org/admin-guide/cgroup-v2.html | read |
| L35 | opencontainers/cgroups -- fs2/freezer.go; fs/freezer.go (runc cgroups) | 2025 | https://github.com/opencontainers/cgroups | https://github.com/opencontainers/cgroups | read |
| L36 | Principles of Chaos Engineering -- Principles of Chaos Engineering | 2019 | https://principlesofchaos.org/ | https://principlesofchaos.org/ | read |
| L37 | Chaos Toolkit -- Experiment API specification (Steady State Probe Tolerance) | 2026 | https://chaostoolkit.org/reference/api/experiment/ | https://chaostoolkit.org/reference/api/experiment/ | read |
| L38 | OpenTelemetry Specification -- Tracing SDK, Batching processor | 2026 | https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/sdk.md | https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/sdk.md | read |
| L39 | Prometheus -- Alerting rules; Unit testing for rules | 2026 | https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/ | https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/ | read |
| L40, D51 | Wu -- Current Time Series Anomaly Detection Benchmarks are Flawed and are... | 2021 | 10.1109/TKDE.2021.3112126 | https://arxiv.org/pdf/2009.13807 | read |
| D1 | Leys -- Detecting outliers: Do not use standard deviation around the mean, ... | 2013 | 10.1016/j.jesp.2013.03.013 | https://dipot.ulb.ac.be/dspace/bitstream/2013/139499/1/Leys_MAD_final-libre.pdf | read |
| D2 | Rousseeuw -- Alternatives to the Median Absolute Deviation | 1993 | 10.1080/01621459.1993.10476408 | https://wis.kuleuven.be/stat/robust/papers/publications-1993/rousseeuwcroux-alternativestomedianad-jasa-1993.pdf | read |
| D3 | NIST/SEMATECH -- e-Handbook of Statistical Methods (NIST Handbook 151) | 2012 | 10.18434/M32189 | https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h.htm | read |
| D4 | Wicklin -- The Hampel identifier: Robust outlier detection in a time series | 2021 | https://blogs.sas.com/content/iml/2021/06/01/hampel-filter-robust-outliers.html | https://blogs.sas.com/content/iml/2021/06/01/hampel-filter-robust-outliers.html | read |
| D5 | Akinshin -- Finite-sample bias-correction factors for the median absolute devia... | 2022 | 10.48550/arXiv.2207.12005 | https://arxiv.org/pdf/2207.12005 | read |
| D6 | Knoth -- Controlling the EWMA S^2 control chart false alarm behavior when th... | 2021 | 10.48550/arXiv.2101.04011 | https://arxiv.org/pdf/2101.04011 | read |
| D7 | Daly -- The Use of Change Point Detection to Identify Software Performance ... | 2020 | 10.1145/3358960.3375791 | https://arxiv.org/pdf/2003.00584 | read |
| D8 | Fleming -- Hunter: Using Change Point Detection to Hunt for Performance Regres... | 2023 | 10.1145/3578244.3583719 | https://arxiv.org/pdf/2301.03034 | read |
| D9 | Mozilla -- Performance Sheriffing | 2026 | https://firefox-source-docs.mozilla.org/testing/perfdocs/perf-sheriffing.html | https://firefox-source-docs.mozilla.org/testing/perfdocs/perf-sheriffing.html | read |
| D10 | Besbes -- A Dataset of Performance Measurements and Alerts from Mozilla (Data... | 2025 | 10.1145/3680256.3721973 | https://arxiv.org/pdf/2503.16332 | read |
| D12 | Spinnaker/Kayenta -- Kayenta canary analysis docs (canary-config.md; canary judge) | 2026 | https://spinnaker.io/docs/guides/user/canary/judge/ | https://spinnaker.io/docs/guides/user/canary/judge/ | read |
| D13 | Chromium -- catapult perf dashboard defaults.py | 2026 | https://chromium.googlesource.com/catapult/+/HEAD/dashboard/dashboard/common/defaults.py | https://chromium.googlesource.com/catapult/+/HEAD/dashboard/dashboard/common/defaults.py | read |
| D14 | Lakens -- Equivalence Testing for Psychological Research: A Tutorial | 2018 | 10.1177/2515245918770963 | https://osf.io/download/v3zkt/ | read |
| D15 | Muller -- Open Challenges in Time Series Anomaly Detection: An Industry Persp... | 2025 | 10.48550/arXiv.2502.05392 | https://arxiv.org/pdf/2502.05392 | read |
| D16 | Liu -- The Elephant in the Room: Towards A Reliable Time-Series Anomaly De... | 2024 | 10.52202/079017-3437 | https://proceedings.neurips.cc/paper_files/paper/2024/file/c3f3c690b7a99fba16d0efd35cb83b2c-Paper-Datasets_and_Benchmarks_Track.pdf | read |
| D18 | Veeravalli -- Quickest Change Detection | 2014 | 10.48550/arXiv.1210.5552 | https://arxiv.org/pdf/1210.5552 | read |
| D21 | Hanley -- If Nothing Goes Wrong, Is Everything All Right? Interpreting Zero N... | 1983 | 10.1001/jama.1983.03330370053031 | https://jhanley.biostat.mcgill.ca/c607/ch08/zero_numerator.pdf | read |
| D22 | Angelopoulos -- A Gentle Introduction to Conformal Prediction and Distribution-Free... | 2023 | 10.48550/arXiv.2107.07511 | https://arxiv.org/pdf/2107.07511 | read |
| D23 | Hardle -- Bootstrap Methods for Time Series | 2003 | 10.1111/j.1751-5823.2003.tb00485.x | https://users.ssc.wisc.edu/~behansen/718/HardleHorowitzKreiss.pdf | read |
| D24 | Kim -- Towards a Rigorous Evaluation of Time-Series Anomaly Detection | 2022 | 10.1609/aaai.v36i7.20680 | https://arxiv.org/pdf/2109.05257 | read |
| D25 | Sorbo -- Navigating the metric maze: a taxonomy of evaluation metrics for an... | 2023 | 10.1007/s10618-023-00988-8 | https://arxiv.org/pdf/2303.01272 | read |
| D26 | Goncalves -- A Model-Based Approach to Anomaly Detection Trading Detection Time ... | 2020 | 10.48550/arXiv.2006.08811 | https://arxiv.org/pdf/2006.08811 | read |
| D27 | Sun -- A Scenario-Oriented Benchmark for Assessing AIOps Algorithms in Mic... | 2024 | 10.48550/arXiv.2407.14532 | https://arxiv.org/pdf/2407.14532 | read |
| D28 | Islam -- Anomaly Detection in Large-Scale Cloud Systems: An Industry Case an... | 2025 | 10.1109/ICSE-SEIP66354.2025.00039 | https://arxiv.org/pdf/2411.09047 | read |
| D29 | Berry -- On the Placement of Imperfect Sensors in Municipal Water Networks | 2006 | 10.1061/40941(247)129 | https://www.osti.gov/servlets/purl/1264620 | read |
| D33, M25 | Clark -- Survival Analysis Part I: Basic concepts and first analyses | 2003 | 10.1038/sj.bjc.6601118 | https://pmc.ncbi.nlm.nih.gov/articles/PMC2394262/ | read |
| D34 | Royston -- Restricted mean survival time: an alternative to the hazard ratio f... | 2013 | 10.1186/1471-2288-13-152 | https://pmc.ncbi.nlm.nih.gov/articles/PMC3922847/ | read |
| D36 | Cawley -- On Over-fitting in Model Selection and Subsequent Selection Bias in... | 2010 | https://jmlr.org/papers/volume11/cawley10a/cawley10a.pdf | https://jmlr.org/papers/volume11/cawley10a/cawley10a.pdf | read |
| D37 | Varma -- Bias in error estimation when using cross-validation for model sele... | 2006 | 10.1186/1471-2105-7-91 | https://pmc.ncbi.nlm.nih.gov/articles/PMC1397873/ | read |
| D38 | Goswami -- Unsupervised Model Selection for Time-series Anomaly Detection | 2023 | 10.48550/arXiv.2210.01078 | https://arxiv.org/pdf/2210.01078 | read |
| D39 | Sharma -- Less is More: Optimizing Probe Selection Using Shared Latency Anoma... | 2026 | 10.48550/arXiv.2602.03965 | https://arxiv.org/pdf/2602.03965 | read |
| D40 | Demsar -- Statistical Comparisons of Classifiers over Multiple Data Sets | 2006 | https://www.jmlr.org/papers/volume7/demsar06a/demsar06a.pdf | https://www.jmlr.org/papers/volume7/demsar06a/demsar06a.pdf | read |
| D41 | Adams -- Bayesian Online Changepoint Detection | 2007 | 10.48550/arXiv.0710.3742 | https://arxiv.org/pdf/0710.3742 | read |
| D42 | Saatci -- Gaussian Process Change Point Models | 2010 | https://icml.cc/Conferences/2010/papers/170.pdf | https://icml.cc/Conferences/2010/papers/170.pdf | read |
| D43 | Roberts -- Gaussian processes for time-series modelling | 2013 | 10.1098/rsta.2011.0550 | https://www.robots.ox.ac.uk/~sjrob/Pubs/philTransA_2012.pdf | read |
| D44 | Fox -- Bayesian Nonparametric Inference of Switching Dynamic Linear Models | 2011 | 10.1109/TSP.2010.2102756 | https://arxiv.org/pdf/1003.3829 | read |
| D45 | Altamirano -- Robust and Scalable Bayesian Online Changepoint Detection | 2023 | 10.48550/arXiv.2302.04759 | https://proceedings.mlr.press/v202/altamirano23a/altamirano23a.pdf | read |
| D47 | Krause -- Near-optimal Nonmyopic Value of Information in Graphical Models | 2005 | 10.48550/arXiv.1207.1394 | https://arxiv.org/pdf/1207.1394 | read |
| D48, M2 | Krause -- Near-Optimal Sensor Placements in Gaussian Processes: Theory, Effic... | 2008 | https://www.jmlr.org/papers/volume9/krause08a/krause08a.pdf | https://www.jmlr.org/papers/volume9/krause08a/krause08a.pdf | read |
| D49 | Krause -- Submodular Function Maximization | 2014 | 10.1017/CBO9781139177801.004 | https://las.inf.ethz.ch/files/krause12survey.pdf | read |
| D50 | van den Burg -- An Evaluation of Change Point Detection Algorithms | 2020 | 10.48550/arXiv.2003.06222 | https://arxiv.org/pdf/2003.06222 | read |
| D57 | Zhang -- Robust Failure Diagnosis of Microservice System through Multimodal ... | 2023 | 10.1109/TSC.2023.3290018 | https://arxiv.org/pdf/2302.10512 | read |
| D59 | Kapoor -- Leakage and the reproducibility crisis in machine-learning-based sc... | 2023 | 10.48550/arXiv.2207.07048 | https://arxiv.org/pdf/2207.07048 | read |
| D60 | Siffer -- Anomaly Detection in Streams with Extreme Value Theory (SPOT) | 2017 | 10.1145/3097983.3098144 | https://hal.science/hal-01640325/document | read |
| D61 | Basiri -- Chaos Engineering | 2016 | 10.1109/MS.2016.60 | https://arxiv.org/pdf/1702.05843 | read |
| D62 | Pham -- Anomaly Detection and Root Cause Analysis for Microservice Systems | 2026 | 10.48550/arXiv.2606.09942 | https://arxiv.org/pdf/2606.09942 | read |
| D63 | Wang -- Cross-System Categorization of Abnormal Traces in Microservice-Base... | 2025 | 10.1145/3715742 | https://arxiv.org/pdf/2403.18998 | read |
| D64 | Chen -- Adaptively diagnosing system faults in microservice architecture: A... | 2026 | 10.1016/j.future.2025.108256 | - | read |
| M3 | Golovin -- Adaptive submodularity: theory and applications in active learning ... | 2011 | 10.48550/arXiv.1003.3967 | https://arxiv.org/pdf/1003.3967 | read |
| M4 | Kim -- Robust sensor placement for Poisson arrivals with false-alarm-aware... | 2025 | 10.48550/arXiv.2510.05343 | https://arxiv.org/pdf/2510.05343 | read |
| M5 | Mohan -- Graphical models for processing missing data | 2021 | 10.1080/01621459.2021.1874961 | https://arxiv.org/pdf/1801.03583 | read |
| M6 | Seaman -- What is meant by "missing at random"? | 2013 | 10.1214/13-STS415 | https://arxiv.org/pdf/1306.2812 | read |
| M7 | Rubin -- Inference and missing data | 1976 | 10.1093/biomet/63.3.581 | - | not read |
| M8 | Qian -- ARMOR: a robust self-supervised framework for root cause analysis i... | 2026 | 10.48550/arXiv.2603.25538 | https://arxiv.org/pdf/2603.25538 | read |
| M9 | Zhang -- The benefit of hindsight: tracing edge-cases in distributed systems | 2023 | https://www.usenix.org/system/files/nsdi23-zhang-lei.pdf | https://www.usenix.org/system/files/nsdi23-zhang-lei.pdf | read |
| M10 | Huang -- Mint: cost-efficient tracing with all requests collection via commo... | 2025 | 10.1145/3669940.3707287 | https://arxiv.org/pdf/2411.04605 | read |
| M11 | Xie -- Microservice root cause analysis with limited observability through... | 2024 | 10.1145/3637528.3671530 | https://netman.aiops.org/wp-content/uploads/2024/07/LatentScope_CameraReady_final.pdf | read |
| M12 | Caetano -- Root cause analysis with latent confounders using partial ancestral... | 2026 | 10.48550/arXiv.2606.20912 | https://arxiv.org/pdf/2606.20912 | read |
| M14 | Srinivas -- Intelligent monitoring framework for cloud services: a data-driven ... | 2024 | 10.1145/3639477.3639753 | https://arxiv.org/pdf/2403.07927 | read |
| M15 | Liyanage -- Reachable coverage: estimating saturation in fuzzing | 2023 | 10.1109/ICSE48619.2023.00042 | https://mboehme.github.io/paper/ICSE23-effectiveness.pdf | read |
| M16 | Bohme -- STADS: software testing as species discovery | 2018 | 10.1145/3210309 | https://mboehme.github.io/paper/TOSEM18.pdf | read |
| M17 | Orlitsky -- Optimal prediction of the number of unseen species | 2016 | 10.1073/pnas.1607774113 | https://arxiv.org/pdf/1511.07428 | read |
| M18 | Doser -- spOccupancy: an R package for single-species, multi-species, and in... | 2022 | 10.1111/2041-210X.13897 | https://arxiv.org/pdf/2111.12163 | read |
| M19 | Carpenter -- Multiple species-site occupancy model (Stan case study of Dorazio e... | 2017 | https://mc-stan.org/learn-stan/case-studies/dorazio-royle-occupancy.html | https://mc-stan.org/learn-stan/case-studies/dorazio-royle-occupancy.html | read |
| M20 | Dorazio -- Estimating species richness and accumulation by modeling species oc... | 2006 | 10.1890/0012-9658(2006)87[842:ESRAAB]2.0.CO;2 | - | not read |
| M21 | MacKenzie -- Estimating site occupancy rates when detection probabilities are le... | 2002 | 10.1890/0012-9658(2002)083[2248:ESORWD]2.0.CO;2 | - | not read |
| M22 | Halstead -- Time-to-detection occupancy methods: performance and utility for im... | 2021 | 10.1002/eap.2267 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8047884/ | read |
| M23 | Christakis -- Social network sensors for early detection of contagious outbreaks | 2010 | 10.1371/journal.pone.0012948 | https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0012948 | read |
| M24 | Li -- Test oracle strategies for model-based testing | 2017 | 10.1109/TSE.2016.2597136 | https://www.albany.edu/faculty/offutt/research/papers/testOracle.pdf | read |
| M26 | Thibaux -- Hierarchical beta processes and the Indian buffet process | 2007 | http://proceedings.mlr.press/v2/thibaux07a/thibaux07a.pdf | http://proceedings.mlr.press/v2/thibaux07a/thibaux07a.pdf | read |
| M27 | Zhao -- ZeroLog: zero-label generalizable cross-system log-based anomaly de... | 2025 | 10.48550/arXiv.2511.05862 | https://arxiv.org/pdf/2511.05862 | read |
| M28 | OpenTelemetry -- OpenTelemetry semantic conventions 1.44.0 (specification) | 2026 | https://opentelemetry.io/docs/specs/semconv/ | https://opentelemetry.io/docs/specs/semconv/ | read |
