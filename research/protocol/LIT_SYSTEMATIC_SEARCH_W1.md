# Systematic search W1: detection delay and sensor placement in microservice monitoring

Status: protocol (Section 1) written 2026-10-09 before any query was run; results (Sections 2-6) appended the same day.
The protocol text is not edited afterwards; every deviation is in "Deviations" with a date. Revised 2026-10-09 after an
independent review (findings F1-F9, logged as R1-R9 under "Revisions after independent review"); the revision changed
counts (Sections 2.3, 2.4, 3, 4), so numbers in this file are the revised ones. Single screener; the independent review
was of this note, not a second screening pass (no kappa). The `judge` server failed to connect in the original session.
Todo: `papers/notes/WRITING_TODOS.md` W1. Prior reading, not re-listed as new: `LIT_TIME_SEMANTICS.md` (C-m2; L19-L27),
`LIT_DETECTION_RULES.md`, `LIT_MISSING_SENSORS.md`, `LIT_HARDENING_20261003.bib`, `LIT_ZOTERO_IDENTIFIERS.txt`.

## 1. Protocol

### 1.1 Research question

RQ-main. Of the peer-reviewed or preprint literature 2015-2026 on microservice or cloud-service monitoring, which papers
(a) report a detection delay (time to detect, MTTD, detection latency) as a measured outcome, and (b) place or select
sensors, traces, logs, metrics or instrumentation points?

The claim under test (wording to be supported or weakened, not assumed): "no microservice paper reports detection delay
(time to detection) for observability / monitoring placement". It is a conjunction. The search is built so that each
half can fail separately:

- C-a: papers that report a detection delay for microservice / cloud-service fault or anomaly detection (any purpose).
- C-b: papers that place or select monitoring sensors / instrumentation in microservice / cloud systems (any outcome).
- C-ab: papers in both sets. Only C-ab refutes the claim as worded.

### 1.2 Sources

The shell has network access through `curl`; WebSearch and WebFetch are also available. Bibliographic databases that
publish a query API with hit counts are used as the primary, reproducible sources, because a count can then be quoted:

| id | source | what it covers | access | known limits |
|---|---|---|---|---|
| S1 | OpenAlex (`api.openalex.org/works`, `title_and_abstract.search`) | indexes Crossref, ACM, IEEE, USENIX, Springer, Elsevier, arXiv, DBLP-listed venues (ICSE, FSE, ASE, ICSOC, ICPE, Middleware, SoCC, NSDI, EuroSys, DSN, ISSRE, TSE, TOSEM, TPDS, ...) | API, no key | abstract coverage incomplete (some publishers withhold abstracts); sort is relevance; stemming on |
| S2 | arXiv API (`export.arxiv.org/api/query`, `all:` field) | cs.SE, cs.DC, cs.NI, cs.LG, cs.PF, cs.DB preprints | API | preprints; no peer-review filter |
| S3 | WebSearch, venue-targeted (site filters: dl.acm.org, ieeexplore.ieee.org, usenix.org, arxiv.org, link.springer.com) | catches items S1/S2 index without abstract; operator-written queries | tool | no hit count is returned; "screened" means the result blocks returned |
| S4 | Backward and forward citations of the papers that come closest (OpenAlex `referenced_works`, `cited_by`) | snowballing | API | only run from the final close set |

Not available: Google Scholar (no API), IEEE Xplore and ACM DL search UIs (bot walls), DBLP search API (bot challenge
returned by the shell on 2026-10-09; Semantic Scholar rate-limited, HTTP 429). These are listed so the absence is
visible. Venues named in the task (ICSE, FSE, ASE, ICSOC, ICPE, Middleware, SoCC, NSDI, EuroSys, DSN, ISSRE, TSE,
TOSEM, TPDS) are covered through S1 only to the extent OpenAlex indexes them; the venue of every hit is recorded, and
the S3 queries name venues explicitly.

Years: 2015-01-01 to 2026-10-09 (publication year 2015 to 2026). Languages: English.

### 1.3 Query strings

Booleans are as written. OpenAlex applies stemming, so `microservice` also matches `microservices`.
arXiv queries use the same term lists, `all:` for each phrase, restricted to the date range, and the category filter
`cat:cs.SE OR cat:cs.DC OR cat:cs.NI OR cat:cs.LG OR cat:cs.PF OR cat:cs.DB OR cat:cs.PL`.

Let DOM = `microservice OR "cloud-native" OR "cloud service" OR "cloud services" OR "service mesh" OR "distributed tracing"`.

| id | targets | OpenAlex `title_and_abstract.search` |
|---|---|---|
| A1 | C-a | `("detection delay" OR "time to detect" OR "time to detection" OR "time-to-detect" OR "time-to-detection" OR "detection latency" OR "mean time to detect" OR "MTTD") AND (DOM)` |
| A2 | C-b | `("sensor placement" OR "monitor placement" OR "monitoring placement" OR "placement of monitors" OR "probe placement" OR "observability placement" OR "instrumentation placement" OR "telemetry placement") AND (DOM OR "distributed system")` |
| A3 | C-b | `(instrumentation OR observability OR telemetry OR monitoring) AND (selection OR selective OR "where to" OR "what to" OR placement OR optimal) AND (microservice) AND (metric OR trace OR log OR span)` |
| A4 | C-b | `submodular AND (monitoring OR observability OR microservice OR "distributed tracing" OR telemetry OR instrumentation)` |
| A5 | C-b | `("trace sampling" OR "tail-based sampling" OR "adaptive sampling" OR "selective tracing" OR "adaptive instrumentation" OR "dynamic instrumentation" OR "adaptive monitoring" OR "tracing overhead") AND (DOM)` |
| A6 | C-a | `("anomaly detection" OR "failure detection" OR "fault detection" OR "incident detection") AND ("detection time" OR "detection delay" OR "detection latency" OR "time to detect" OR MTTD) AND (microservice OR "cloud service" OR "cloud services")` |
| A7 | C-a | `("quickest change detection" OR "sequential change detection" OR "sequential detection" OR CUSUM) AND (DOM)` |
| A8 | C-a, C-b | `("false alarm" OR "false positive") AND ("detection delay" OR "time to detection" OR "detection latency" OR "time to detect") AND (DOM)` |
| A9 | C-b | `("which metrics" OR "metric selection" OR "log selection" OR "what to log" OR "log placement" OR "logging placement" OR "where to log") AND (DOM)` |

`DOM` is expanded in place when run. The exact strings as sent are stored by the script and reproduced in Section 2.

S3 (WebSearch, venue-targeted), run after S1/S2, each recorded with the number of result blocks returned:
W1 `microservices "detection delay" OR "time to detection" monitoring placement` (no site filter);
W2 `sensor placement microservices observability trace instrumentation` (no filter);
W3 `"time to detection" microservices fault detection evaluation` with each of dl.acm.org, ieeexplore.ieee.org,
usenix.org, arxiv.org;
W4 `observability placement microservices submodular` (no filter);
W5 `where to instrument microservices optimal instrumentation points monitoring cost` (no filter);
W6 `microservice monitoring "MTTD" evaluation fault injection detection time` (no filter).

### 1.4 Screening

Every hit is recorded with id, title, year, venue, DOI, source query. Duplicates are merged by DOI, else by normalised
title. Screening runs in three stages on the deduplicated union:

1. Title and abstract screen against the criteria below (one screener, the author-agent; a limitation, no kappa).
2. Mechanical cross-check, independent of the screener: every hit whose abstract matches
   `detection (delay|latency|time)|time[- ]to[- ]detect|MTTD|mean time to detect` is listed, and the screener must
   record an explicit decision for each, so a title-based exclusion cannot hide a delay report. Likewise every hit
   whose abstract matches `placement|select(ion)? of (sensors|metrics|logs|traces|probes|monitors)|instrumentation
   point|what to (monitor|instrument|log)`.
3. Full-text coding of the included set (PDF text layer through `pdftotext`, or the publisher/arXiv HTML). A paper that
   could not be opened is marked NOT READ and is not coded from its abstract.

### 1.5 Inclusion and exclusion criteria

Include if all of I1-I3 hold:

- I1 Domain: the system under study is a microservice application, a cloud-native or cloud service system, or a
  distributed service system with request tracing (service mesh, serverless included).
- I2 Topic, at least one of: (a) reports a detection delay (time to detect / MTTD / detection latency) as a quantity
  the paper measures or evaluates; (b) places or selects monitoring sensors, traces, logs, metrics, spans or
  instrumentation points, or decides what to observe or keep, with an explicit selection or optimisation step.
- I3 Type and access: peer-reviewed paper or arXiv preprint, 2015-2026, English, with an abstract.

Exclude with a recorded reason: E1 domain (network-only SDN/NFV, wireless sensor network, water, IoT, hardware,
HPC-only, non-service software); E2 topic (root-cause analysis, log parsing, or anomaly detection with binary or
point-wise metrics and no delay; benchmark papers that only cite delay in motivation; surveys and tutorials, which are
recorded and used for reference chasing but never counted as a primary report); E3 type (thesis, patent, tool
manual, blog; vendor documents are noted separately); E4 duplicate or superseded version; E5 not accessible.

### 1.6 Full-text coding questions (answered per included paper, each with a quote or section/page)

- Q-A: is time to detection a measured outcome? Values: YES (a delay quantity is reported, with the definition of its
  start and end), PARTIAL (reported only as a secondary figure, or as a delay of something other than a detector, e.g.
  the sampling or reporting delay), NO (full text searched, no such figure), NOT READ.
- Q-B: under what false-alarm control? Values: threshold or rate stated (give it), calibrated on fault-free data,
  none stated, not applicable, NOT READ.
- Q-C: does it place or select sensors / instrumentation? YES (explicit selection or optimisation over which
  signals, spans, services or probes are observed), PARTIAL (selection of what to keep, e.g. trace sampling),
  NO, NOT READ.

For text-layer papers, the term search is reported with the exact pattern and hit count, so that "NO" is a measured
absence over a stated pattern, not an impression. Pattern: `detection (delay|latency|time)|time[- ]to[- ]detect|MTTD|
mean time to detect|detection lag|time to alarm|alert(ing)? (delay|latency)`.

### 1.7 Outputs and denominators

Reported as: N_hits per query and per source; N_unique after dedup; N_screened (titles/abstracts read); N_included;
N_read in full; N_not_read; K_a (Q-A YES or PARTIAL), K_b (Q-C YES or PARTIAL), K_ab. Scope label for the
conclusion: method / general-literature, by absence over the named sources and years; it is not a claim about the
literature outside those indexes.

### 1.8 Stop rules and budget (set before running)

- Per query, screen at most the 200 highest-relevance OpenAlex hits and at most 200 arXiv hits (when a query returns
  more, the count is reported and the rest are not screened; the cap is stated in the result).
- Snowball only from the final close set (at most 5 papers, one level backward and forward).
- Full-text reading budget: at most 40 papers. If the included set exceeds 40, the ones with an I2(a) and I2(b) match
  in the abstract are read first, then the rest by rank, and the remainder is reported as NOT READ.
- The search is closed when the S1/S2/S3 list is exhausted within these caps. No further queries are added after the
  first screening pass except through a logged deviation.

## Deviations

All dated 2026-10-09. D1 was decided after the first query run and before any screening; D2-D6 during or after the
first screening pass; R1-R9 (below the D-list) after the independent review. None changed a query string in 1.3.

- D1 (before screening): the OpenAlex hits ranked beyond the 200 cap for A1 (606 hits), A3 (327) and A4 (207) were
  fetched too, for a mechanical regex check only (Section 2.4). The screened set stays top 200 per query.
- D2 (during screening): E1 clarified. Intrusion, DDoS, malware, fraud, SIEM and other security-threat detection in
  cloud systems is out of domain even when it reports a detection delay (these are not fault or performance
  monitoring of a service). Revised 2026-10-09 (R3): the original sentence said "68 abstracts ... were excluded on this
  basis". That was a regex label, not 68 individual decisions: 68 delay-term records matched the SEC pattern (which
  includes generic words such as "security" and "threat"). After the review, 6 of those 68 were moved or included (#330
  included; #267, #479, #615, #128 moved to E2; #784 moved to E1), leaving 62; with the new abstracts and a stricter
  term list the delay-term records excluded under a security label are 66 (Section 2.4), of which 64 contain a strict
  security term (attack, intrusion, fraud, DDoS, malware, phishing, zero-day, cyber, breach, insider, SIEM, zero-trust,
  vulnerab-, ransom, botnet, malicious, adversar-) and 2 (#209, #450) have "security" in the title. They are counted,
  not hidden (Section 2.3). Without D2 the delay half of the claim would be refuted by security papers that say
  nothing about observability.
- D3 (after the first pass): four extra web queries X1-X4 (Section 2.2) because the first pass found delay papers and
  placement papers but almost no paper in both; and snowballing from 6 seeds, not at most 5 (1.8): the 3 close
  papers plus Borges 2024, Saha 2026 and Roberts 2025.
- D4 (reading budget): "opened" in Section 3 means the PDF text layer (or, for TraceForge, the repository README)
  was obtained and the pattern in 1.6 was searched. I did not read every opened paper in full. For each opened paper
  with pattern hits I read the hit contexts; for the 9 with a defined delay, the method and evaluation passages as
  well. Where this note is silent, assume "pattern search plus contexts".
- D5: three papers found only by S3 (Roberts 2025, UniSage 2025, SampleHST 2022) were added to the included set;
  they are not in the 849.
- D6: the included list was revised before coding: three theses or dissertation chapters were moved to E3, one
  autoscaling paper to E2 (Section 2.3). Revised 2026-10-09 (R6): the same revision also ADDED three records to group A
  that the first-pass list (86 = 50 A + 27 B + 9 C, `data/included_ids.json`) did not hold: #698 (Scalable Cloud-Native
  Architectures for Real-Time Payment Processing Systems; abstract: "Federated AIOps reduced Mean Time to Detect
  (MTTD) by 60%"), #431 (Intelligent API Automation Framework for Enterprise Microservices; abstract: "decreases mean
  time to detect (MTTD) by 61%") and #289 (Developing Incident Management Systems Using Proactive Alerting ...;
  abstract names MTTD as an evaluation metric, no figure). All three were added after the mechanical delay-regex
  cross-check (1.4 step 2), on abstract-level delay claims. 86 + 3 - 3 theses - 1 autoscaling = 85, the figure in the
  original Section 2.3.
- D7 (after screening): two OpenAlex full-text probes, F1 and F2, run to address the main limit of A1-A9 (title and
  abstract only; a delay result that appears only in the evaluation section is invisible to them). F1: (delay terms)
  AND (placement terms) AND (microservice OR cloud-native OR distributed tracing), 2015-2026, `fulltext.search`: 54 hits,
  top 50 read by title: none on topic (IoT, water networks, security, thesis index volumes). F2: (delay terms) AND
  (which metrics to / what to instrument / where to instrument / instrumentation points / observability configuration /
  observability posture) AND microservice: 63 hits, top 50 read by title. One new on-topic title, Grabher, Machida,
  Ropars, UCC 2025 (DOI 10.1145/3773274.3774269): a stochastic-reward-net model of a cloud service with a performance
  anomaly detector, studying precision, recall and inspection frequency against service latency and resource cost;
  abstract read, PDF not obtained (the HAL link returned an HTML page). It has no sensor placement and its outcome
  is service latency, not delay to detect. The probes are not a second screening pass: OpenAlex full-text matching is
  loose (the AND terms are not required to co-occur), so their silence is weak evidence.
- Process note: one line of text patching of a helper script used the system `python3`; all searching, screening and
  statistics ran under `uv run --no-project python -I`. The `judge` MCP server failed to connect in the original
  session; the independent review that followed (not the `judge` panel) produced R1-R9 below.

### Revisions after independent review (all dated 2026-10-09)

Section 1 (the protocol) is unchanged. Each entry names the review finding it answers and what changed in the counts.

- R1 (F1, Awartani). Record #305, Awartani, "Do Multimodal Fusion Architectures Actually Improve Early Degradation
  Detection?", SSRN 2026, DOI 10.2139/ssrn.7583047, had been excluded on its title only (no abstract in OpenAlex). Its
  Crossref abstract reports a detection delay ("35-second median detection delay", RE2-OB, logistic regression with
  metrics and traces) and compares four telemetry configurations (metrics-only, metrics-plus-logs, metrics-plus-traces,
  full) on Online Boutique and Train Ticket, 90 injected-failure cases per dataset, 60-second windows, thresholds from
  development repetitions. Included in groups A and B (configuration comparison; counted once). **Not opened** (SSRN
  returned HTTP 403, also with the Delivery.cfm URL). It is coded from the abstract only, so Q-A, Q-B and Q-C are not
  assessed from the text: the abstract does not say how the detection delay was defined, nor what false-alarm rate it
  was measured at. See 3.1a.
- R2 (F2, title-only exclusions). The 71 records recorded as "excluded on title only" had not been content-screened.
  Abstracts were sought for all 71 through Crossref, OpenAlex (`abstract_inverted_index`, re-queried) and Semantic
  Scholar (rate-limited with HTTP 429 in the first session; re-queried with back-off), then by web
  search for the two most relevant titles. Recovered for **28** (26 by API; FUSE #349 and MiMoQ #497 by web search of
  their repository records). Re-screened on content: **3 included** (#305, #143, #173), **25 excluded on content**
  (10 E1 domain, 7 security, 8 E2 topic; Section 2.3). The remaining **43** are relabelled "unscreened on content"
  (not "excluded"): no abstract could be recovered (Springer, Elsevier and IEEE withhold abstracts from the three
  APIs). Included: #143 (SSRN 2025, logging and monitoring architecture for containerised microservices; the abstract
  claims "reduced detection latency", a qualitative, abstract-level claim with no figure; group A); #173 (Research
  Square 2026, change-point detection of CPU workload patterns on Kubernetes and Online Boutique; "mean detection
  latency of 2.1 +/- 0.4 minutes"; group C, adjacent: the delay is the localisation error |estimated change point - true
  change point| for workload transitions, not a fault detector's delay, and the PDF was opened, Section 3.5). FUSE (#349,
  LNCS 2023, ICSOC) was opened through the accepted manuscript at QUT eprints (0 pattern hits; kernel-level digest per
  invocation; 53 detected faults; no delay, no placement step): excluded E2 on content. eBPF-shield (#842, SOCA 2026) is
  closed access and no abstract is available from any source tried: it stays "unscreened on content" and is on the
  download list. The recovered abstracts are in `tmp/lit-w1/data/rev_abs.json`.
- R3 (F3, labels). The exclusion-reason counts in Section 2.3 are regex labels (`final_stats.py`: pattern MS for
  "no microservice/cloud term", pattern SEC for security, remainder = E2), apart from the records listed under R2 and
  here. Stated for every bucket: E1 domain (237), E1 security (175 + 45 generic-word-only), E2 topic (255). Moved:
  #267 (observability maturity model, MTTD is a keyword), #479 (proposal, detection latency is a planned metric),
  #615 (breach MTTD cited from an IBM report), #128 (qualitative literature review), #645 (review of observability
  tools) and #773 (payments event-mesh architecture) from "security" to E2; #784 (weather and wildfire hazard
  detection) from "security" to E1. Added: #330 (ERP incident management in cloud-native ecosystems; abstract: "incident
  detection latency reduced by ~40-50%", prototype and simulated ERP environments) to the abstract-claim list, which
  makes it an included group-A record, not opened. The SEC pattern also matched 45 further records only on generic
  words ("security", "threat"); they are now a separate bucket "security, generic word only" because many are not
  security papers (e.g. #576 OpenTelemetry tracing overhead, #135 microservice anomaly detection, #8 monitoring
  architecture comparison). Their exclusion rests on the screening pass and the two mechanical cross-checks (2.4: none
  has a sensor-placement term (#288 matches inside "replacement", #527 on "energy-aware workload placement"); two, #209 and
  #450, have a delay term and "security" in the title), not on the label. Qualitative-only delay claims were included for some
  records (#289, #143) and not for others that carry the same kind of claim without a figure and a weaker domain
  fit: #166 (RCA in distributed platforms), #433 (cloud infrastructure management), #617 (event-driven workflow
  integrity), #69 (test automation). That is a judgement call and is flagged; none selects or places sensors, so the
  C-ab conclusion does not depend on it. D2's sentence is corrected above.
- R4 (F4, Outage-Watch). The clock start IS defined in the paper (Figure 1): B is "the time when it started affecting
  the performance metrics", C is when "an outage [is] declared" after alerts, and Table 6 reports the MTTD reduction as
  a percentage of (C - time of prediction) / (C - B). It is therefore a prediction lead measured against a human
  declaration, not a detector's delay from fault onset (A). Row corrected in 3.1.
- R5 (F5, Section 3.1 rows). Köse and Ng: a controlled fault-injection simulation, n = 12 trials, MTTD quantised by the
  60 s synthetic-agent cadence (limitations section). NetMon: the delay tables (3-5) span 0-58 s in the cells read
  (58 s at 50% packet loss), not only the conclusion's "2-10 seconds"; the one non-firing cell (1/9 runs at 50% loss) is
  in the correlation-latency row of Table 5. UniAIOps: its three evaluation sets are synthetic proxy generators
  patterned on LogHub, AIOps 2018 and AIOps 2020, so the microservice domain is doubtful. Pappula: the definition of
  MTTD is generic (no start or end event tied to an injection or incident) and the setup is not established; counted in
  the nine as a definition only. Q-C is coded consistently as follows: PARTIAL for studies that compare detection delay
  across fixed set-ups that differ in which signal or probe class is available (Köse and Ng: synthetic user-journey
  agents versus infrastructure alerts; TraceForge; Awartani), which is wider than the wording in 1.6; NO for studies
  that change only how the same signal is detected or transported (Roberts et al.: polling versus signalling of
  container health). The coding is a judgement.
- R6 (F6): the three additions to group A are logged in D6 above.
- R7 (F7, .bib). `LIT_SYSTEMATIC_SEARCH_W1.bib` is now regenerated from `research/protocol/make_bib_w1.py`; no hand
  edits remain. Before this revision three entries (gias2022samplehst, zhu2025unisage, grabher2025modeling) had been
  added by hand and the key `jacob2025signalling` renamed to `roberts2025signalling` (OpenAlex returned the first author
  as "Roberts, Jacob"); the script now produces all of these, unescapes HTML entities (`O&#39;Brien` had leaked into
  one entry) and takes the output path as a parameter. New entries: `awartani2026do`, `devarakonda2025integrated`,
  `amirullah2026automated`, `wang2024fine`. The script reads working data in `tmp/lit-w1/` (gitignored), so it
  documents the build and cannot be re-run from a clean clone.
- R8 (F8). Sifter (#732, `las-casas2019sifter`) was opened from the author PDF
  (https://jonathanmace.github.io/papers/lascasas2019sifter.pdf): 0 hits of the 1.6 pattern in 117.8k characters;
  Q-A NO, Q-C PARTIAL (trace sampling), opened count 49 on that change alone. Wang's SSRN 2024 version
  (10.2139/ssrn.4829698, #356, recorded as a duplicate E4 of #357) is cited in 3.4. STEAM and TracePicker are open
  access at the ACM DL only, which returned HTTP 403 to the shell, so a browser is needed; TraStrainer and Wang
  et al. 2026 are closed access. Final opened count after R1-R9: 50 (3.x and 4.1).
- R9 (F9). The wording in 4.3 is replaced by the reviewer's; its counts are the revised ones (849 screened, 94
  included) and the bracketed clause is kept conditional on Awartani being opened.
- Counts that moved because of R1-R9 (old -> new): unique records screened 849 (unchanged); included at abstract level
  85 -> 89 (A 53 -> 56, B 24 -> 24, C 8 -> 9; #305 coded in A and B, counted once); included in total 90 -> 94; opened
  48 -> 50 (+ Sifter, + #173); not opened 42 -> 44 (+ #305, #143, #330; - Sifter); excluded on title only 71 ->
  "unscreened on content" 43 (28 recovered, 3 of them included); abstract-claim list not opened 22 -> 25; Q-C PARTIAL 20
  -> 21 (Awartani); studies comparing detection delay across fixed telemetry configurations 2 -> 3.

## 2. Search log (run 2026-10-09)

Raw data, scripts and every downloaded text are in `tmp/lit-w1/` (gitignored): `run_search.py` (exact query strings as
sent), `data/oa_A*.json` and `data/ax_A*.json` (per-query hit lists with the abstracts), `data/unique.json` (849
deduplicated records), `data/counts.tsv`, `pdf/<n>/paper.txt` (text layers), `final_stats.py`.
Added in the 2026-10-09 revision: `data/rev_abs.json` (abstracts recovered for the title-only records, per source),
`data/rev_abs_chosen.json` (the one used), `data/included_final_rev.json`, `pdf_rev/` (FUSE, Sifter, #173 as downloaded;
Sifter and #173 are also copied to `pdf/732` and `pdf/173`), `add_meta.py`, `final_stats.py` (revised; the original is
`final_stats.orig-20261009.py`), and `research/protocol/make_bib_w1.py` (tracked).

### 2.1 Database queries (S1 OpenAlex, S2 arXiv)

"Hits" is the count the API reported for the query; "screened" is the number of records of that query that entered
screening (cap 200, 1.8). arXiv queries: same phrase lists, 2015-01-01 to 2026-10-09, categories as in 1.3.

| query | targets | OpenAlex hits | OpenAlex screened | arXiv hits | arXiv screened |
|---|---|---|---|---|---|
| A1 delay terms AND domain | C-a | 606 | 200 | 12 | 12 |
| A2 placement terms AND domain | C-b | 11 | 11 | 1 | 1 |
| A3 instrumentation/monitoring AND selection AND microservice AND signal | C-b | 327 | 200 | 28 | 28 |
| A4 submodular AND monitoring terms | C-b | 207 | 200 | 84 | 84 |
| A5 trace sampling / adaptive instrumentation AND domain | C-b | 58 | 58 | 8 | 8 |
| A6 anomaly/fault detection AND delay terms AND microservice/cloud | C-a | 102 | 102 | 6 | 6 |
| A7 quickest/sequential change detection AND domain | C-a | 9 | 9 | 0 | 0 |
| A8 false alarm AND delay terms AND domain | C-a, C-b | 124 | 124 | 1 | 1 |
| A9 metric/log selection AND domain | C-b | 29 | 29 | 1 | 1 |
| total (overlapping) | | 1473 | 933 | 141 | 141 |

Raw records screened: 933 + 141 = 1074. After deduplication by normalised title: **849 unique records** (717
OpenAlex only, 98 arXiv only, 34 both). The A4 hits are mostly submodular optimisation in robotics, crowdsensing and
learning; A1 and A3 hits are dominated by non-peer-reviewed "AI-driven observability" articles (Zenodo, SSRN and
low-circulation journals).

### 2.2 Web queries (S3) and snowballing (S4)

"Blocks" = result blocks returned by WebSearch (no hit count exists). Domain filters were passed where listed; the tool
did not enforce them strictly (the usenix.org run returned no usenix.org result).

| id | query (abridged) | filter | blocks |
|---|---|---|---|
| W1 | microservices "detection delay" OR "time to detection" monitoring placement | none | 9 |
| W2 | sensor placement microservices observability trace instrumentation | none | 9 |
| W3a-d | "time to detection" microservices fault detection evaluation | dl.acm.org / ieeexplore.ieee.org / usenix.org / arxiv.org | 9 / 10 / 10 / 10 |
| W4 | observability placement microservices submodular | none | 9 |
| W5 | where to instrument microservices optimal instrumentation points monitoring cost | none | 9 |
| W6 | microservice monitoring "MTTD" evaluation fault injection detection time | none | 9 |
| X1 (D3) | "sensor placement" OR "monitor placement" fault diagnosis microservices cloud detectability | none | 9 |
| X2 (D3) | observability configuration comparison metrics logs traces effect on time to detect, Kubernetes | none | 9 |
| X3 (D3) | trace sampling impact on anomaly "detection delay" OR "time to detect" tail-based sampling | none | 10 |
| X4 (D3) | optimal placement of monitoring probes microservice applications maximize detection probability | none | 9 |

Of the 121 blocks, most were vendor blogs, patents and non-microservice sensor-placement papers (recorded as E3 or E1).
Academic items that entered screening: Roberts 2025 (included), UniSage 2025 and SampleHST 2022 (included),
Borges 2024 (known, L15), ICDCS 2016 service placement (E1, telecom), "Sensor Placement for Online Fault Diagnosis"
arXiv 2211.11741 (E1, not opened), Tampere thesis "Observability Design in Microservice Systems" and Polytechnique
Montreal thesis on instrumentation placement as a knapsack (both E3, snippets only), Guo et al. industrial survey
"Enjoy your observability" (E2 survey, abstract snippet only).

Snowballing (S4, OpenAlex citations and references of 6 seeds, D3): 22 forward records (cited-by, 2015-2026) and about
75 backward records (reference lists), read by title and abstract. Two entered the included set (abstract only, not opened):
Stylos 2025 (hierarchical multi-agent RL for adaptive telemetry collection) and Li 2022 (Microsoft incident
detection "timely, accurate, comprehensive"). The rest were off-topic, surveys, or already in the 849.

### 2.3 Screening counts

Revised 2026-10-09 (R1-R3). **The exclusion-reason rows are regex labels** (`tmp/lit-w1/final_stats.py`: pattern MS
= no microservice/cloud-service term in title and abstract; pattern SEC = a security word; remainder = E2), not a manual
classification, except for the records named in R2 and R3. A regex label says which pattern a record matched, not why a
reader would exclude it. Before the review the table described the E1/E2 rows as "rule-labelled after a manual title
pass"; that manual pass covered the delay and placement candidates only (2.4).

| stage | n | note |
|---|---|---|
| records reported by the databases | 1614 | 1473 OpenAlex + 141 arXiv, overlapping |
| screened after cap | 1074 | |
| unique after dedup (**N_screened**) | **849** | 49 have no abstract (title screen only): 43 unscreened on content, 4 included, 2 E3/E4 |
| excluded E1 domain (regex MS: no microservice/cloud-service term; plus 10 content-screened, 1 moved by hand) | 237 | regex label |
| excluded E1 security, fraud, intrusion, DDoS (D2): a strict security term matched (7 of them content-screened) | 175 | regex label |
| excluded, SEC matched only generic words ("security", "threat"); many are not security papers (R3) | 45 | regex label, reason not assigned |
| excluded E2 topic (other): remainder, plus 8 content-screened and 6 moved by hand | 255 | regex label; includes service placement/orchestration, trace analysis without delay, RCA |
| excluded E3 thesis/dissertation chapter | 3 | Harvard 2020 instrumentation placement; Carleton 2023; Springer chapter "Robust Monitor Placement" |
| excluded E4 duplicate | 2 | #371, #356 (Wang SSRN 2024, version of #357) |
| **unscreened on content** (no abstract recoverable; was "excluded on title only", 71) | **43** | never judged beyond the title; 8 titles are plausible for C-a/C-b (R2) |
| **included at abstract level (N_included, S1+S2)** | **89** | 56 delay (A), 24 selection (B), 9 other (C); #305 is coded in A and B, counted once |
| included from S3 | 3 | Roberts, UniSage, SampleHST |
| included from S4 | 2 | abstract only |
| **included in total** | **94** | |
| PDF text layer or README opened (N_opened) | 50 | 47 of the 89 (45 + Sifter + #173), plus the 3 from S3 |
| not opened (NOT READ) | 44 | 42 of the 89 (25 A, 13 B, 4 C), plus the 2 from S4 |

Check: 237 + 175 + 45 + 255 + 3 + 2 + 43 + 89 = 849. Of the 71 title-only records of the first pass, 28 gained an
abstract (3 included, 25 excluded on content) and 43 did not. The 43 are #22, 36, 38, 47, 48, 91, 113, 142, 144, 149,
176, 220, 222, 247, 250, 263, 265, 324, 331, 348, 406, 420, 423, 443, 480, 490, 507, 585, 625, 629, 646, 666, 679,
684, 725, 734, 751, 778, 809, 820, 821, 825, 842. Eight have titles that are plausible for C-a or C-b and need an
abstract: #48 (log anomaly detection), #144 (message-level failure detection), #176 (GenAI observability control
plane), #247 (DAIMS, anomaly detection in web services), #348 (FL-AD-MSA, microservice anomaly detection), #725
(service demand estimation for microservices), #825 (software monitoring on Stack Overflow), #842 (eBPF-shield).
Their absence from the included set is therefore "not screened", not "not relevant".

Group A = abstract reports or uses a delay (MTTD, detection time/latency) in a microservice/cloud service context;
B = abstract concerns selecting, placing or sampling observability data; C = adjacent (anomaly anticipation, change
point detection, monitoring systems).

### 2.4 Mechanical cross-checks (independent of the screener)

- Delay regex (`detection (delay|latency|time)|time[- ]to[- ]detect|MTTD|mean time to detect`) in title or abstract:
  165 of 849 (158 before the review; the recovered abstracts of R2 added 7); with a microservice/cloud term, 163.
  59 of the 163 are included (55 before; + #305, #143, #173, #330). 104 were excluded: 66 under a security label (D2;
  64 with a strict security term, 2 with "security" in the title), 36 E2, 1 E1 (#784, hazard detection) and 1 E4
  duplicate. Before the review the split was 68 security / 33 other of 101. Reasons for the non-security ones:
  detector or ingestion run time reported as "latency" (ms-scale), IoT or data-pipeline domain, benchmark or diagram
  records, duplicates, a qualitative claim without a figure (R3 lists four that are not included), or the abstract
  only names MTTD as a motivation, a keyword or a planned metric. One of them (record 12, an observability review)
  states that the study "did not report quantitative measures of prediction accuracy, mean time to detect (MTTD)
  ...", a statement about one reviewed study, not evidence about the field. The 36 E2 and the labels are regex
  output. For R3 I re-read the sentence containing the delay term of every excluded record in the pre-review list
  that had no strict security term (36 of the 101, 2026-10-09); the other 65 were not re-read individually.
- Placement regex (`placement|selection of (sensors|metrics|logs|traces|probes|monitors)|instrumentation point|what to
  (monitor|instrument|log)`) with a microservice/cloud term: 28 (26 before the review; + #255 data placement in a
  payments pipeline, #457 service placement, both E2); 2 included (357, 439); the other 26 are service
  placement/orchestration, scheduling or security papers, plus regex artefacts (the pattern is unanchored: #288 matches
  inside "replacement").
- Beyond the cap (D1): of the 606 / 327 / 207 hits of A1 / A3 / A4, 272 / 121 / 8 were not screened. Regex on these
  abstracts: 48 delay-plus-microservice non-security records, none with a placement term in title or abstract
  (titles are observability frameworks, AIOps platforms, data-pipeline monitoring, RCA); 15 placement-plus-microservice
  records, all service placement, autoscaling or security. They stay unscreened and are not counted as excluded
  on merit.

## 3. Included papers and coding

Coding follows 1.6. "Opened" is defined in D4. Quotes are from the text layers in `tmp/lit-w1/pdf/<n>/paper.txt`
(record number n in `data/unique.json`); locations are section, table or "abstract" because the layouts are
two-column and page numbers were not recorded. Venue type is given because the delay-reporting set is mostly not from
the target venues of 1.2: a "gray" venue is a journal or repository outside ICSE/FSE/ASE/ICSOC/ICPE/Middleware/SoCC/
NSDI/EuroSys/DSN/ISSRE/TSE/TOSEM/TPDS and the like, with no peer-review status checked by me.

### 3.1 Papers that define and report a detection delay (opened) - Q-A = YES

K_a(defined) = 9 (8 from S1/S2, 1 from S3). Bib keys refer to `LIT_SYSTEMATIC_SEARCH_W1.bib`. Rows corrected 2026-10-09 (R4,
R5). Of the nine, the clock is tied to a fault or incident event in rows 1 (injection), 2, 4 (injection), 5 (incident
start), 9 (fault onset) and, against a human declaration, row 3; rows 6-8 give a definition and a figure only.

| # | paper (key) | venue, year, id | Q-A time to detection measured? | Q-B false-alarm control | Q-C places/selects sensors? |
|---|---|---|---|---|---|
| 1 | Köse, Ng, *Vitality assurance in microservice architectures* (`kose2026vitality`) | Front. Comput. Sci. 8:1811944, 2026, DOI 10.3389/fcomp.2026.1811944 | YES. Controlled fault-injection simulation, n = 12 trials (Table 2), MTTD "quantised by the 60 s synthetic-agent cadence" (limitations). "MTTD was computed as T_detection - T_fault"; HBT median 70 s (IQR 48.5-86.8) vs baseline 397 s, baseline detected 7 of 12 injected trials (abstract; Table 2). Right-censoring of non-detections is stated in the method. | Fixed rules: baseline alerts "p99 request latency above 1 s sustained for 60 s, or ..." (Methods). No false-alarm rate measured; limitations: "Synthetic journeys can be subject to flakiness ... which may increase false positives without careful baselining". | PARTIAL (configuration comparison): synthetic user-journey agents vs Prometheus/Grafana alerts. No selection or optimisation step in the passages read. |
| 2 | Roberts, Archibald, Trinder, *Signalling Health for Improved Kubernetes Microservice Availability* (`roberts2025signalling`) | arXiv 2507.02158 (cs.DC), 2025; venue not verified | YES. Model "T_l,p ~ (N_l - 1/2) I_l + L_l" (Eq. 2) for poll-based detection, validated on SockShop (Sec. IV, Tables III-IV); abstract: signal-based monitoring "detects container failure 86% faster than PCM". | "PCM can erroneously detect failures, and this reduces service availability by 4%" (abstract). No false-alarm target. | NO. Compares a monitoring mechanism (poll vs signal), not which signals. |
| 3 | Agarwal et al., *Outage-Watch* (`agarwal2023outage`) | ESEC/FSE 2023, DOI 10.1145/3611643.3616316 | YES. "reduces the Mean Time To Detection (MTTD) of outages by up to 88%" (abstract); Table 6 gives the MTTD reduction for 3 production outages; "flagged the outage 67 minutes before the outage was actually launched". The clock start IS defined (Figure 1, R4): B = "the time when it started affecting the performance metrics", C = the outage "declared" after alerts fired; Table 6 reports the MTTD reduction as a percentage of (C - time of prediction) / (C - B). So the quantity is a prediction lead against a human declaration, not a detector's delay from fault onset (A); 3 production outages. | Precision and recall reported ("recall is 100%, while precision is 30-40%"); threshold "generated based on the 9 weeks of training data". No false-alarm budget. | NO. |
| 4 | Andersson et al., *Hybrid Monitoring for Early Fault Detection in Cloud-Native 5G Systems* (NetMon) (`andersson2026hybrid`) | arXiv 2609.12649, 2026; venue not verified | YES. "Detection latency: Time from fault injection to the first relevant anomaly observed at the central server"; faults of "10ms latency or 5% packet loss" detected "within 2-10 seconds" (conclusion); the detection-latency tables (3-5) span 0-58 s (58 s at 50% packet loss), and one cell did not fire (1/9 runs at 50% loss, Table 5, correlation row). Kubernetes AMF cluster, tc netem injection. | "zero false positives for high-confidence correlations across 18 hours"; "Reducing anomaly volume would require raising detection thresholds and increasing detection latency, a deliberate trade-off favoring sensitivity". No fixed budget. | NO. Fixed all-pairs probing, "N(N-1) probes ... per cycle"; no selection step found. |
| 5 | Zhang, *Unified AIOps pipeline for joint log-KPI anomaly detection* (UniAIOps) (`zhang2024unified`) | J. Adv. Comput. Syst., 2024, DOI 10.69987/jacs.2024.40305; gray | YES, on benchmark proxies; the microservice domain is doubtful (the three sets are synthetic proxy generators patterned on LogHub, AIOps 2018 and AIOps 2020, R5). "Detection delay is measured per incident interval as the elapsed time between incident start and the first ..." (Sec. 5/6.4); mean delay 10.9 s (LogHub-proxy), 0.5 min (AIOps2018-proxy, 5-min aggregation), 5.5 min (AIOps2020-proxy, 10-min windows). | "Thresholds reflect the tradeoff between paging cost (false positives) and missed incidents"; thresholds tuned on training data. No budget. | NO. |
| 6 | Remella, *End-to-End Visibility in Cloud Deployments* (RTPH) (`remella2025end`) | IJAIBDCMS 6(4), 2025, DOI 10.63282/3050-9416.ijaibdcms-v6i4p117; gray | YES (definition). "Detection Latency: Time from anomaly occurrence to ..." (Sec. 4); "reduces anomaly detection latency by 32-45%" (abstract). Method (simulated vs live) not established in the passages read. | False-positive rate reported ("decreased false positives by 28-40%"). | NO. |
| 7 | Konda et al., *Streaming Telemetry Analytics ... Microservices* (`konda2026streaming`) | J. Comput. Sci. Technol. Stud. 8(8), 2026, DOI 10.32996/jcsts.2026.8.8.6; gray | YES (definition and value). MTTD = "Total Detection Time for All Events / Number of Detected Events" (Eq. 12), so misses are not charged; table value MTTD 5.8 min, FPR 0.07. | FPR defined and reported (0.07). | NO. |
| 8 | Pappula et al., *Building Observability into Full-Stack Systems* (`pappula2021building`) | IJERET 2(4), 2021, DOI 10.63282/3050-922x.ijeret-v2i4p106; gray | YES (definition only; generous: no start or end event is tied to an injection or incident, R5). "MTTD means the mean amount of time required to identify a system deficiency or anomalous behaviour, upon its occurrence"; Table 1: MTTD 18 -> 4 min. Case-study type; setup not established. | None found (1 pattern hit for false positives). | NO. |
| 9 | "mhmdevan" (Eslamnia in the registry), *TraceForge* (`eslamnia2026traceforge`) | Zenodo + GitHub repository, 2026, DOI 10.5281/zenodo.20561280; **not peer reviewed**; README opened, `docs/mttd-report.md` not opened | YES. "MTTD is measured as the time from fault onset to Prometheus alert firing"; with metrics the alert fires at 70 s (payment errors, 12% errors) and 72 s (slow payment, p95 ~1007 ms); without metrics both are marked "undetected". | Not described in the README ("pending 9s" before firing is shown; thresholds not shown). | PARTIAL (configuration comparison): five modes `none`, `metrics`, `metrics_logs`, `metrics_logs_traces`, `otel_full`. A fixed ladder; no selection step. |

### 3.1a Not opened: abstract reports a delay across fixed telemetry configurations (R1)

Coded from the Crossref abstract only; the full text was not obtained (SSRN HTTP 403), so none of Q-A, Q-B, Q-C is
assessed from the text.

| paper (key) | venue, year, id | what the abstract says | coding from the abstract |
|---|---|---|---|
| Awartani, *Do Multimodal Fusion Architectures Actually Improve Early Degradation Detection?* (`awartani2026do`), #305 | SSRN 2026, DOI 10.2139/ssrn.7583047; **not opened** | Online Boutique (RE2-OB) and Train Ticket (RE2-TT), 90 injected-failure cases each (five services, six fault types, three repetitions), 60-second windows, "thresholds use only development repetitions"; logistic regression, random forest and XGBoost on "metrics-only, metrics-plus-logs, metrics-plus-traces, and full multimodal configurations"; RE2-OB logistic regression with metrics and traces: ROC-AUC 0.9755, F1 0.9073, 97.78% case-level coverage, "35-second median detection delay"; plus observational validation on production NGINX/Elastic telemetry | Q-A: YES at the abstract level (a median detection delay is reported; its definition is not in the abstract). Q-B: thresholds from development repetitions; no false-alarm rate matched across configurations is visible in the abstract. Q-C: PARTIAL (R5), a configuration comparison, no selection or optimisation step visible. Group A and B |

### 3.2 Papers that state a delay figure but where the definition or the method is not established (opened)

These 12 give a number or percentage for MTTD or detection latency; I could not find the start and end of the clock
or the evaluation set-up in the passages read. All are gray venues. Three contain a number that disagrees with its own
abstract, which is why I do not use them as support:
`devalla2025ai` (abstract: MTTD -35% and false positives -40%; Sec. 4.5: MTTD -38%, false positives -42%),
`kalyanasundaram2026autonomous` (abstract: -83%; Table 1: 20 min -> 3 min, labelled 85%), `sethupathy2023zero`
(abstract: "45% improvement in Mean Time to Detection"; Sec. 5.2: 14 hours -> 3 hours).

| key | id | figure |
|---|---|---|
| `vytla2026auto` (AUTO-OPS) | DOI 10.48084/etasr.20360 | median time to detect 18.0 -> 6.1 min over 46 incidents in a 30-day blind window; false-positive alert groups 34.0% -> 12.0% |
| `vanama2025ai` | DOI 10.63282/3050-9416.ijaibdcms-v6i2p111 | Table 2: MTTD 42 -> 14 min; false positives 18% -> 5.8%; "simulated" appears in the text |
| `devalla2025ai` | DOI 10.63282/3050-9262.ijaidsml-v6i2p114 | see above |
| `kalyanasundaram2026autonomous` | DOI 10.63282/3050-9262.ijaidsml-v7i1p162 | see above |
| `sivakumaran2026cortex` | Zenodo 10.5281/zenodo.21875642 | "five-to-eight times faster" MTTD vs threshold monitoring |
| `sethupathy2023zero` | DOI 10.30574/wjaets.2023.8.2.0119 | see above |
| `garnimitta2025federated` | DOI 10.37745/ijeats.13/vol13n32031 | "anomaly detection latency was reduced by 25%" in an illustrative e-commerce case |
| `pentaparthi2025observability` | DOI 10.32628/cseit25112811 | MTTD -79% attributed to cited work ([4], [5]) in the text, not measured there |
| `mohammed2025ai` | DOI 10.36948/ijfmr.2025.v07i05.57943 | "MTTD reduction levels of up to 45%" in "controlled experiments"; "simulated microservices" |
| `kalivoshko2025explainable` | DOI 10.70315/uloap.ulbec.2025.0204015 | MTTD -74% vs "legacy black-box methods"; its case table is "compiled by the author ... [from] case analysis [2, 6, 9, 11, 17]" (literature) |
| `holigi2026continuous` | DOI 10.70917/ijcisim-2026-5327 | regression-detection time -60 to -75% vs post-production discovery |
| `jakkaraju2025graph` | DOI 10.4236/jcc.2025.1310006 | "detection latency by 63% compared to GraphSAGE" (model comparison; whether it is run time is not established) |

### 3.3 Opened, delay term present only as a concept, a motivation or run time (12)

- Run time, not delay from onset: `raeiszadeh2023real` (TDAD; "detection time ... time required for processing a single
  trace", 0.131 ms) and `xiong2025deepcontainer` (Table 4, average latency in ms per mechanism).
- Concept or motivation, no figure from a measurement in the text read: `73` Pentyala (`pentyala2025ai`), `93` Weing
  (`weing2018ai`; MTTD is a planned metric), `87` Jain (`jain2026ai`), `96` Thallam (`thallam2025ai`), `103` Yeluri
  (`yeluri2022aiops`), `145` Yazhini (`yazhini2026intelligent`), `148` Deshmukh (`deshmukh2025open`),
  `172` Harikrishnan (`harikrishnan2026automated`), `338` Rahmonov (no DOI, not in the .bib) and `6` Ramachandran
  (no DOI; "Conceptual analysis indicates ...").

### 3.4 Papers with an explicit selection or placement step, or a selection of what data to keep (Q-C)

Q-C = YES means an explicit selection or optimisation over which signals, spans, services or probes are observed,
in a microservice or cloud-service system. Q-A for these is the pattern search of 1.6 (text layer) unless "not opened".

| paper (key) | venue, year, id | Q-C | Q-A | Q-B |
|---|---|---|---|---|
| Srinivas et al., *Intelligent Monitoring Framework for Cloud Services* (`srinivas2024intelligent`, **known**, in LIT_HARDENING bib) | ICSE-SEIP 2024, DOI 10.1145/3639477.3639753; arXiv version opened | YES. "We focus on two crucial dimensions: what to monitor (resources) and which metrics to monitor." | NO: 0 pattern hits in 72.6k characters | 1 hit for false positive; not a design constraint |
| Boppudi et al., *Information-Theoretic Limits of Observability* (`boppudi2022information`) | Zenodo, DOI 10.5281/zenodo.20792159; self-published, no review evidence; opened | YES. "We give a greedy algorithm that selects a minimum sufficient metric set ... we argue from its submodular structure that the returned set is near-optimal" | NO: 0 hits | none |
| Wang et al., *Fine-grained Tracing for Performance Anomaly Diagnosis of Serverless Functions* (`wang2026fine`); earlier SSRN version *Fine-Grained Tracing for Anomaly Diagnosis Of Serverless Functions* (`wang2024fine`, DOI 10.2139/ssrn.4829698, record #356, counted as duplicate E4) | ACM TAAS 2026, DOI 10.1145/3785005 (closed access); SSRN 2024 (HTTP 403); **neither opened** | YES (abstract): "tracing probe placement based on the control flow graph ... an enhanced global search algorithm that automatically computes a probe placement with optimal fault localization" under a cost constraint | **NOT READ** | **NOT READ** |
| Alves et al., RADAR (`alves2026dynamic`) | arXiv 2609.31292, 2026; opened | PARTIAL: RL chooses trace-sampling rules | NO: 0 hits | none |
| Toslali et al. (`toslali2024online`), IC2E version (`toslali2024unleashing`, not opened; identity of the two not verified) | arXiv 2405.15645; DOI 10.1109/ic2e61754.2024.00015 | PARTIAL: online probabilistic trace sampling | arXiv: NO, 0 hits | none |
| Ertl (`ertl2021estimation`); Gias et al. (`gias2022samplehst`, `gias2024samplehst`); Toshniwal TAS (`toshniwal2026tas`); Wu et al. (`wu2025trace`); Chen et al. TraceMesh (`chen2024tracemesh`); Zhu et al. UniSage (`zhu2025unisage`) | arXiv or Zenodo or IEEE CLOUD 2024; opened | PARTIAL: trace sampling | NO: 0 hits each | not assessed (no delay reported) |
| Chen et al., Tracezip (`chen2025tracezip`) | PACMSE 2025, DOI 10.1145/3728888; opened | NO (compression, not selection) | NO: 0 hits | |
| Las-Casas et al. Sifter (`las-casas2019sifter`) | SoCC 2019, DOI 10.1145/3357223.3362736; **opened** from the author PDF https://jonathanmace.github.io/papers/lascasas2019sifter.pdf (R8) | PARTIAL: trace sampling (biased sampling of unusual traces; no sensor placement) | NO: 0 hits of the 1.6 pattern in 117.8k characters | not assessed (no delay reported) |
| He et al. STEAM (`he2023steam`), Huang et al. TraStrainer (`huang2024trastrainer`), Xie et al. TracePicker (`xie2025tracepicker`) | FSE 2023, PACMSE 2024, PACMSE 2025; **not opened** (ACM DL returned HTTP 403). STEAM and TracePicker are open access at the ACM DL only (a browser is needed); TraStrainer is closed access | PARTIAL (abstract): trace sampling | **NOT READ** | **NOT READ** |
| Fodor et al., AdaMC (`fodor2025adaptive`); Pathak et al. (`pathak2024self`, `pathak2025demonstration`) | NOMS 2025; IEEE CLOUD 2024; COMSNETS 2025; **not opened** | PARTIAL (abstract): scrape-frequency adaptation; log verbosity; "when, where, and at what granularity to collect log data" | **NOT READ** | **NOT READ** |
| Pina et al. (`pina2018nonintrusive`); Filipe et al. (`filipe2018black`); Fadda et al. (`fadda2019monitoring`); Wang et al. HSACMA (`wang2020hsacma`); Song et al. ASTracer (`song2019astracer`) | NCA 2018 (x2), IEEE TSC 2019, Softw. Qual. J. 2020, LNCS 2019; **not opened** | NO or not coded on the abstract (gateway logging; black-box inference from response time; monitoring-aware microservice *deployment*; no abstract for the last two) | **NOT READ** | **NOT READ** |
| Stylos et al. (`stylos2025hierarchical`) | NFV-SDN 2025, DOI 10.1109/nfv-sdn66355.2025.11349644; S4; **not opened** | PARTIAL (abstract): adaptive telemetry collection, cloud-native | **NOT READ** | **NOT READ** |

Summary of Q-C: YES = 3 (Srinivas, Boppudi, Wang). PARTIAL = 21: 15 trace-sampling, adaptive-scrape or logging papers
plus UniSage, SampleHST (S3), Stylos (S4), and the three configuration comparisons (Köse and Ng and TraceForge in 3.1;
Awartani in 3.1a, abstract only). Of the 3 with YES: 2 opened and report no delay; 1 not opened.

### 3.5 Adjacent papers (group C) opened

| paper | id | Q-A | note |
|---|---|---|---|
| Lee et al., Maat (`lee2023maat`) | ASE 2023, DOI 10.1109/ase56229.2023.00082 | NO: 1 hit, "such an alert delay" in the problem statement | anomaly anticipation (forecast then detect); evaluates detection quality, not delay |
| Amirullah et al., *Automated Workload Pattern Recognition in Kubernetes* (`amirullah2026automated`), #173 (R2) | Research Square 2026, DOI 10.21203/rs.3.rs-9189120/v1; PDF opened | PARTIAL, not a fault detector: "mean detection latency of 2.1 +/- 0.4 minutes" (abstract; Table 5 reports 1.7, 2.0, 2.7 min per repetition) is the "Detection Latency (DL): \|tau-hat - tau\| in minutes for correctly detected" workload-pattern transitions, i.e. the localisation error of a change point in CPU workload, on a single-service pod baseline (n = 21); Online Boutique is a cross-environment accuracy test (57.1%), with no delay figure | adjacent (binary-segmentation change-point detection plus a shape classifier for autoscaling); no sensor selection |
| Ni et al., MELODY (`ni2024melody`) | arXiv 2401.10338 | NO: 0 hits | |
| Zaki et al., OrEdge (`zaki2026oredge`) | arXiv 2608.00309 | NO: 0 hits | |
| Tan et al., MAAD (`tan2024maad`); Ojanen et al. (`ojanen2025efficient`); Kande (`kande2025real`); Kandi (`kandi2025real`) | IPDPS 2024; IEEE CLOUD 2025; two 2025 papers | **NOT READ** | abstract of MAAD: "saves approximately 92% detection time" vs DeepLog (a run-time claim in the abstract; not opened) |

### 3.6 Group A, abstract claims a delay figure, not opened (25)

NOT READ, so not coded. The abstract (not the text) states a measured or claimed MTTD / detection-time / detection-delay
result: `bhansali2026multi`, `vankayala2023ai`, `verma2025ai`, `du2025anomaly` ("reducing detection latency by over 70%"),
no key for `163` (no DOI), `muller2026causal`, `yang2020design` (Sensors 2020, fault detection time of a fast fault
detection mechanism for containerised IoT services, "more than three times" faster), `erigha2023developing`,
`lakshmanasamy2026enhancing`, `fu2026graphrca`, `sychev2026implementing`, `gurramula2026intelligent`,
`thalary2023monitoring`, `amgothu2025observability`, no key for `557` and `846` (no DOI), `hareram2025resilient`,
`nelavala2026scalable`, `tariq2026service`, `li2026service`, `devarakonda2025integrated` (#143, R2: "reduced detection
latency", qualitative, no figure), `awartani2026do` (#305, R1; see 3.1a), no key for `330` (R3: no DOI; "incident detection
latency reduced by ~40-50%" in prototype and simulated ERP environments), `chavali2026stochastic` (preprint; per-run MTTD over 960
runs described in a data note; the Preprints.org page returned HTTP 403), `mistry2025future`. Three of these are in
peer-reviewed-looking venues (IEEE conference proceedings, Sensors, Springer); I did not check review status.

### 3.7 Already known to the project (not new; listed so the denominator is complete)

From `LIT_TIME_SEMANTICS.md`: AIOpsLab (L24, MLSys 2025: "Time-to-Detect (TTD) is the time elapsed from the occurrence of
a fault to its detection"), ITBench (L25: its "MTTD" is "how soon (in seconds) an agent performs diagnosis", i.e. time to diagnosis, so not counted as a detection delay), Saha et al. NOMS 2026 (L27: "time-to-first-detection (TTFD): the
median delay between anomaly onset and the first alarm"; telemetry design, 5G user plane), and the Oxn line (L15, L16, L18:
detected or not; MTTD announced as future work). Quotes are copied from that note, which reports them checked against
the PDFs; I did not re-open these papers. They are not counted in this search's denominators. They are the reason
C-m2's wording ("the 6 RCA/anomaly papers read") must not be generalised.

### 3.8 Excluded papers that matter for the claim (adjacent, outside the domain or type)

| paper | why excluded | what it says (abstract only unless noted) |
|---|---|---|
| He et al., *Service Placement for Detecting and Localizing Failures Using End-to-End Observations*, ICDCS 2016, DOI 10.1109/icdcs.2016.21 (`he2016service`) | E1 telecommunication networks | placement for monitoring performance: coverage, identifiability, distinguishability; greedy, constant-factor; no delay objective |
| Heavey et al., *Provable Sensor Sets for Epidemic Detection over Networks with Minimum Delay*, AAAI 2022, DOI 10.1609/aaai.v36i9.21260 (`heavey2022provable`) | E1 contact networks | selects a sensor set that minimises detection delay; shows greedy submodular can be worse; bicriteria algorithm. The same objective family as Leskovec 2007 (known), outside services |
| Harvard 2020 thesis on instrumentation placement from performance variation; Polytechnique Montreal 2026 thesis (instrumentation placement as a knapsack, evaluated on Redis, Apache, SPEC) | E3 thesis; not opened | placement of instrumentation, not microservices, no delay |
| Guo et al., "Enjoy your observability" industrial survey | E2 survey, snippet only | tracing and analysis practice in 10 companies |

Also surfaced by D7 (not counted in the 90): Grabher, Machida, Ropars, UCC 2025 (`grabher2025modeling`), abstract only,
Q-A NOT READ; it models detector precision, recall and inspection frequency against service latency and cost.

## 4. Conclusion

Scope label for everything below: **general (literature), by absence, over the named indexes and queries**, 2015-01-01
to 2026-10-09, English, title/abstract matching plus the web and citation routes of 1.2. It describes what this search
found, not the whole literature. Single screener (me); no second screener, no inter-rater figure. The note was
independently reviewed once (R1-R9); the review was not a second screening pass and did not re-run the queries. All
counts are the revised ones (R1-R9).

### 4.1 Denominators

- Screened: 1074 raw records, **849 unique** (S1 OpenAlex, S2 arXiv). 89 included at abstract level; 3 more from web
  queries (S3) and 2 from snowballing (S4): **94 included**. 50 opened (47 of the 89, plus 3 from S3); **44 not opened**.
  43 further records have no abstract and were never judged on content ("unscreened on content", 2.3).
- C-a (reports a detection delay): of the 94 included, 56 are group A (all from S1/S2). Among all included:
  - **9** define and report a delay (3.1; Roberts counted, NetMon counted). The clock is tied to a fault or incident event in
    6 of them (Outage-Watch against a human declaration, R4); 3 give a definition and a figure only (Remella, Konda,
    Pappula), and UniAIOps' microservice domain is doubtful (R5);
  - **12** state a figure whose definition or method I could not establish (3.2), three with numbers that contradict
    their own abstract;
  - **12** opened papers use the term only as a concept or as run time (3.3);
  - **25** claim a delay result in the abstract and were not opened (3.6; 22 before R1-R3), among them Awartani (3.1a).
  Two further delay-defining papers (AIOpsLab TTD, Saha 2026 TTFD) are already in the project notes.
- C-b (selects or places observability data): **3** with an explicit selection or placement step (Srinivas 2024 (known),
  Boppudi 2026 (self-published), Wang 2026 (serverless probe placement)); **21** partial (trace sampling, adaptive
  scrape or logging, three configuration comparisons).
- C-ab: of the 3 with an explicit placement step, **0** report a delay in the 2 opened (0 pattern hits in each); the
  third (Wang 2026) was **not opened**. Of the 9 opened papers with a defined delay, **2** compare fixed
  observability configurations (Köse and Ng 2026, peer reviewed, controlled simulation, 12 trials; TraceForge 2026, an
  unreviewed repository, 2 faults); a third, Awartani 2026 (SSRN; four telemetry configurations, 90 injected cases per
  system, "35-second median detection delay"), was found at abstract level only and **not opened**: **3** compare
  detection delay across fixed telemetry configurations. **0** of the 9 optimise or select a sensor set, and **0** hold a
  stated false-alarm budget fixed while comparing delay (in the passages read; false-positive counts, rates or
  precision appear beside delay in at least 5 of them, as separate outcomes). For Awartani neither point can be read
  from the abstract.
- Open risk by construction: 13 group-B papers were not opened: 4 trace-sampling papers (STEAM, TraStrainer,
  TracePicker, and the IC2E version of Toslali; ACM DL returned HTTP 403; Sifter was opened in R8), 3
  adaptive-monitoring or logging papers (NOMS 2025, CLOUD 2024, COMSNETS 2025), 3 older monitoring papers (NCA 2018 x2,
  IEEE TSC 2019), 2 with no abstract, and Wang 2026. Any of them could report a delay that the abstract does not mention.

### 4.2 What cannot be claimed

- "No microservice paper reports detection delay (time to detection)". Refuted for the delay half alone: 9 papers in
  this search define and report one (e.g. Köse and Ng 2026 from injection timestamps; Roberts et al. 2025 on
  SockShop; NetMon 2026 from fault injection; Outage-Watch, FSE 2023, as a prediction lead against the declaration of
  production outages), plus AIOpsLab (TTD) and Saha 2026 (TTFD) from earlier reading.
- C-m2 ("none of the 6 microservice RCA/anomaly papers read defines a detection delay") remains true for those 6 and
  must keep the "of the 6 read" denominator; it is not evidence about the field.
- "No paper compares observability configurations by detection delay": three do (Köse and Ng 2026; TraceForge 2026;
  Awartani 2026, abstract only).
- "No paper selects sensors by a delay objective" as a statement about all domains: it is established outside services
  (Leskovec 2007 known; Heavey et al. AAAI 2022, abstract only: "selecting a sensor set that minimizes the delay in
  detection").
- Anything about full text of the 44 papers not opened, about the 43 records unscreened on content, and nothing about
  venues OpenAlex does not index.

### 4.3 What can be claimed

Claim wording, replaced 2026-10-09 (R9) by the independent reviewer's abstract-length wording, with the counts of this
revision (849 screened, 94 included; the reviewer's draft had 90 before the re-screen):

> To our knowledge (systematic search of OpenAlex and arXiv, 2015 to October 2026, 849 records screened, 94 included),
> no prior microservice work selects or places observability sensors by optimising detection delay[, and the three
> studies that compare detection delay across fixed telemetry configurations neither optimise the sensor set nor
> report delay at a matched false-alarm rate].

The bracketed clause is conditional on Awartani 2026 being opened: two of the three studies (Köse and Ng, TraceForge)
were read, the third (Awartani) only through its abstract. Use the clause only after the Awartani PDF has been
obtained and confirms both halves; until then it is an abstract-level statement and the sentence should end at
"detection delay". "Included" counts records, not a quality judgement, and 44 of the 94 were not opened.

Facts that sit behind the wording, kept apart from it: nine opened papers define and report a detection delay in
microservice or cloud monitoring (Köse and Ng 2026, Roberts et al. 2025, Agarwal et al. 2023 among them); placement
under a delay objective is established for water, contact and social networks (Leskovec et al. 2007; Heavey et al.
2022). Claim-level cautions, per the project rules: this is a contrast of absence ("not found in 849"), not a
mechanism; the interval is the denominator; "none optimises" is a snapshot over 94 included papers, 44 of which were
not opened, plus 43 records never read beyond a title.

### 4.4 Closest papers (3-5)

1. Köse and Ng 2026 (`kose2026vitality`): MTTD from injection timestamps, right-censored, vs a Prometheus baseline,
   controlled fault-injection simulation, 12 trials, MTTD quantised by the 60 s agent cadence. Compares monitoring
   approaches (synthetic journeys vs infrastructure alerts); no selection step; no false-alarm rate.
   1b. Awartani 2026 (`awartani2026do`, R1, **not opened**): detection delay across metrics-only / +logs / +traces / full
   configurations on Online Boutique and Train Ticket, 90 injected cases each; the closest paper by abstract and the first
   to obtain after Wang 2026.
2. TraceForge 2026 (`eslamnia2026traceforge`): MTTD per observability mode, none to full OpenTelemetry, onset to alert
   firing. Unreviewed; a ladder of postures like none/selected/full; README only.
3. Saha et al. NOMS 2026 (known, L27): telemetry design for fine-grained anomaly detection with TTFD; 5G user plane,
   not microservices.
4. Srinivas et al. ICSE-SEIP 2024 (known): "what to monitor ... which metrics to monitor", no delay in the text
   searched; and Boppudi 2026 (`boppudi2022information`): greedy submodular minimum sufficient metric set, no delay,
   self-published.
5. Wang et al. TAAS 2026 (`wang2026fine`): tracing probe placement with a cost bound for serverless; **not opened**,
   so its relation to delay is unknown. First paper to obtain.

## 5. Limitations

- One screener; the E1/E2/security labels for the 760 excluded records are regex labels (2.3, R3), apart from the
  records named there; a manual pass covered the delay and placement candidates and, in the review, 36 delay-term
  records. A second screener on a sample would be needed for a kappa.
- 49 of 849 records have no abstract (title only); 4 of them are included, 2 are E3/E4 and 43 are "unscreened on
  content" (R2; the first version called 71 of them "excluded on the title").
- The qualitative-only abstract-claim rule was not applied uniformly (R3): #289 and #143 are included, #166, #433, #617
  and #69 are not.
- Title and abstract matching misses delay results that are only in an evaluation section; D7 probes are weak.
- OpenAlex coverage of ACM/IEEE abstracts is partial; ACM DL, IEEE Xplore, SSRN, Springer (client challenge) and DBLP
  were not available to the shell (bot wall, HTTP 403); Semantic Scholar answered HTTP 429 in the first session and
  worked with back-off in the review, but returned no abstract for Springer, Elsevier and IEEE records. Venue coverage (ICSE, FSE, ASE, ICSOC, ICPE, Middleware, SoCC,
  NSDI, EuroSys, DSN, ISSRE, TSE, TOSEM, TPDS) is whatever OpenAlex and the web search return; it was not enumerated
  venue by venue.
- The delay-reporting set is dominated by gray venues (Zenodo, SSRN, low-circulation journals). I did not check
  their review status, and three contradict their own abstracts. They show that the phrase is common, not that the
  measurement is sound.
- A group-A abstract that says "MTTD" may mean time to diagnosis (ITBench, Outage-Watch variants) or run time; this was
  separated only for the opened papers.
- Quotes come from `pdftotext -layout` output and were not compared with the PDFs page by page; two-column
  interleaving can reorder words (this affects Section 3.1 quotes of Köse and Ng and NetMon most).
- The numbers in Section 2 were produced by the scripts in `tmp/lit-w1/`; `final_stats.py` (revised 2026-10-09, the
  pre-review version is `final_stats.orig-20261009.py`) reproduces the counts in 2.3 and 2.4 from `data/*.json` plus
  `data/rev_abs_chosen.json`. The scripts were run once each (final_stats several times during the revision); no
  planted-defect check of the regexes was done (the check "exists and ran", not "seen failing on a defect"), and the
  review found one regex artefact by reading (the placement pattern matches inside "replacement").

## 6. Not in the .bib, and why

`LIT_SYSTEMATIC_SEARCH_W1.bib` has 91 entries (87 before R7), generated by `make_bib_w1.py` in this directory (R7), each
with a DOI that resolves at doi.org (handle API) and whose title matches Crossref or DataCite, or an arXiv page that was
fetched. Left out:

- Records with no DOI and no arXiv id: Ramachandran 2024 (record 6), Rahmonov 2026 (338), record 163 (Alicante
  repository), record 557 (CloudWatch), record 846 (Russian-language article).
- Theses and chapters (E3): Harvard 2020 (817), Carleton 2023 (785), Springer chapter (676).
- Papers already in `LIT_HARDENING_20261003.bib`: Srinivas 2024, Borges 2024, Saha 2026, AIOpsLab, ITBench.
- Papers named only through a web snippet and never opened or DOI-checked: Tampere thesis, Polytechnique Montreal
  thesis, Guo et al. survey, arXiv 2211.11741.

Entries marked "abstract only" in the `note` field were not read in full; the DOI check proves the record exists, not
its content.
