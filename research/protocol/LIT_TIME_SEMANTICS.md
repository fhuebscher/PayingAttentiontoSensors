# Time semantics: detection delay and fault onset in the literature (decisions m, n)

Status: written 2026-10-04 by a subagent for protocol decision 28 (`research/PROTOCOL_DRAFT_20261002.md`, round 7,
items m and n). 39 of the 40 sources in §3 were opened and read in the sections named there; L5 (Lorden 1971) was read
in its abstract only and is not used as support. Quotes were copied from the text layer of each PDF or page and checked
by string search against those texts. Review: one independent adversarial review (a Fable subagent, read-only); its
findings are applied, see the end of this file.

Conventions. `L<n>` = source id in §3. Scope labels: **general practice** (several independent sources agree),
**one paper**, **one research group**, **tool-specific** (one tool's documented or coded behaviour), **this thesis**
(my reasoning about this repo, no source). "Says" is what a source states; "I conclude" is mine. `—` = not reported or
not found. In quotes, inner double quotes are rendered as single quotes, math glyphs as plain letters, and words split
by a hyphen at a line break are joined.

Terms used below:

- **Event time**: when the anomalous data point happened. Examples: a span's end stamp, a log line's stamp, a metric
  sample's stamp, a request's end in the ledger.
- **Availability time** (stream processing calls it *processing time*): when a detector could first see that data
  point, after export, ingestion and evaluation.
- **Onset**: the moment the fault starts acting on the system under test. Not the same as the moment the injection
  command is issued.
- **Positive control**: a run with a known fault where the expected detector response is stated in advance, with a
  tolerance, and checked.

---

## 1. Summary

**Where decision 28's premise holds.** Decision 28 says "Use the field's standard rather than inventing one". For
*observation time* and for *onset stamping* the field has a de-facto practice (event time; a point stamp at the
injection command). For the *margin* before calling one detector faster, for *in-flight requests at onset*, and for a
*positive-control tolerance*, no field standard was found. There the thesis has to declare its own rule, and the
premise does not hold.

### 1.1 Question m: which clock times a detection?

**What the sources say.** The sensor-placement papers read (L1, L2, L3; one research group and a challenge it
co-authored) time detection when the event *reaches* the sensor, in simulation time. An ideal sensor that alarms at
once is explicit in L1 ("As soon as the event reaches a selected node, an alarm is triggered") and L3; L2 defines
T(s, i) as the sensor's own detection time and does not discuss a reporting delay. Change-detection theory counts the
delay in observations after the change, and compares detectors at a fixed false-alarm rate (L4). Anomaly-detection
benchmarks score *which data point* was flagged, by its position in a labelled window (L6, L7, L8, L9). All of these
use event time. Operations practice uses a later clock: the SRE workbook's "detection time" is the time to send a
notification (L11), and an incident's "detection" is when the operator becomes aware (L12). AIOps agent benchmarks
time the agent: L25 states it in seconds of agent time; for L24 the definition is "from the occurrence of a fault to
its detection", and that it is agent time is my reading of its results table. DORA defines no detection metric (L13).
The six microservice RCA and anomaly papers read from 2023–2026 report no detection delay; they score windows, samples
or cases (L19, L20, L21, L22, L23, L26). BARO comes closest: it estimates an "anomaly detection time" to feed RCA and
tests RCA's sensitivity to errors in it, but reports no delay metric (L20). Oxn, the closest prior work, reports
whether a fault was *visible*, not when, and lists MTTD as future work (L15, L16, L17, L18). Stream processing treats
event time and processing time as two separate clocks with a changing gap between them (L10).

**Is "event time plus pipeline latency as a separate part" established?** Not as such. One paper reports both clocks
for the same detectors: alarm time including the export window, with pipeline processing time reported separately
(L27, NOMS 2026). Sensor placement keeps detection at event time and can add a *response* delay after detection to the
penalty, as a fixed parameter (L2: "the response is delayed by a fixed amount of time"; L3 Derivative Case C: 3 h).
That keeps two delays apart, but it is a post-detection response delay, not a pipeline delay: an analogy, not a
precedent (I conclude). No microservice observability paper read reports both.

**Resolution margin.** No source read states a minimum margin before calling one detector faster. Three related
practices exist. Detection times are computed on the sampling grid (L1, L2, L3: 5-minute steps; L4: sample indices);
I conclude that differences below one step are therefore ties by construction, though no source discusses ties.
Detectors are compared at a matched false-alarm rate (L4). Where labels may be misaligned, a buffer zone is added at
label boundaries (L9); separately, SR-CNN credits a detection up to k samples after a segment starts (L8), and NAB
scores earliness inside a window (L6). L27 reports medians without a test and calls 0.70 s vs 0.80 s "slightly faster".

**What the recent work adds (2023–2026, weighted more).** The newest papers move in three directions, none of them a
timing convention: they verify that an injected fault had a user-visible effect before keeping a case (L22, FSE 2026);
they switch the fault on before traffic so that onset never cuts through requests (L23, MSR 2026); and one
telemetry-design paper reports alarm time and pipeline time side by side (L27, NOMS 2026). The Oxn line (2024–2025)
still measures visibility only (L15, L16, L18). BARO (2024) measured the injection-to-symptom gap only by eye, at 1–3 s
(L20).

**Recommendation for this thesis (m).**

1. Keep **event-time detection delay** as the primary metric (span end, request end, log stamp, metric sample stamp).
   This is what placement (L1–L3), change detection (L4) and anomaly benchmarks (L6, L8) use. Engineering default.
2. Report **availability delay** beside it, as a separate component per sensor class and per SUT: span export, metric
   scrape or evaluation interval, log shipping. For Hotel the span export is a 1 s Jaeger reporter flush
   (`research/traffic-sweep/readout-hotel-r3/SWEEP_ANALYSIS.md`, "Resolution"; `REVIEW.md` cites `tracer.go:36`).
   TeaStore (Kieker) and the OTel demo export differently; the OTel SDK's default batch delay is 5000 ms (L38). The
   per-SUT values were not checked here. Re-rank the sensors once more under "event time + availability bound".
   Precedent: L27 (alarm time plus pipeline time); L2, L3 only as an analogy. Engineering default.
3. **Margin**: there is no standard to adopt. Declare one: a lead smaller than the combined timestamp resolution of the
   two sensors (plus any clock offset; plus the availability bound in the second view) counts as a tie. Report the full
   distribution of leads and the share above the margin. Compare sensors at a matched no-fault firing rate (L4).
   Whether ties change how P4 wins are counted is a **preregistration decision for the user**.

### 1.2 Question n: how is fault onset fixed as ground truth?

**What the sources say.** The common practice is one timestamp taken when the injection is issued; the effect is
assumed to follow at once. Oxn stamps the treatment start just before it calls the injection (L17). RCAEval ships one
Unix timestamp per case, `inject_time.txt` (L21). BARO uses the injection time "as a proxy" for the true onset, after
seeing by eye that symptoms lag by 1–3 s (L20); it is also the only paper read that treats onset error at all, by
shifting the assumed onset from −40 to +40 around the injection time and measuring RCA accuracy (L20, §4.8.1). Eadro
labels a whole observation window abnormal if a fault was injected in it (L19). The AIOps Challenge 2022 data give
start times only; one paper using them set the end times by hand, "with a maximum interval of two minutes" (L26). Fang
et al. verify that the fault had an effect, but per case, through user-facing SLIs; 84.4 % of their first injections
had none (L22). AnoMod avoids the question: the fault is switched on before traffic starts (L23).

The chaos tools whose code or status docs were read record that the *injection action* finished, not that the
*effect* began (L28, L29, L30). Their stamps range from whole seconds (Chaos Mesh record events and Litmus Kubernetes
events use second-precision timestamps) to nanoseconds (ChaosBlade). Two of them use a fixed sleep where they would
need a check, each marked with a TODO in the code: ChaosBlade waits 100 ms before checking that the fault process
exists, for long-running fault processes outside pods, containers and nodes (L29); Litmus waits 700 ms before resuming
the stress process (L30). Gremlin documents separate "Initializing" and "Running" stages, and Chaos Monkey records
terminations through trackers; neither page read says what their timestamps mean (L31, L32). For `docker pause` the
effect can probably be confirmed: on cgroup v2 the kernel reports "frozen 1" when freezing is complete (L34), runc's
freeze call polls for that report every 10 ms (L35), and Docker emits its `pause` event only after the runtime's pause
call returns (L33). The containerd/shim path between Docker and runc was not traced, so the link is inferred. The
three measurement hosts run cgroup v2 (`research/host-topology.json`, `"cgroupVersion": "v2"`, lines 24, 199, 437),
which makes the v2 path the relevant one. No benchmark read bounds onset as an interval, or uses such an event.

No benchmark read states an explicit rule for requests in flight at onset. One implicit span-level rule exists: Oxn
labels spans by their start time, so a span that starts before the treatment and ends under it counts as "no
treatment" (L17). Others label windows or whole cases (L19, L20, L22). Positive controls with an explicit tolerance
exist in chaos and alerting tools: steady-state probes with an exact value or an inclusive range (L37), probe verdicts
as a conjunction (L30), and alert unit tests that check the expected alerts at a given evaluation time, with exact
value matching by default (L39). The control-versus-experiment comparison is the core of chaos engineering (L36). None
of the RCA or anomaly benchmarks read runs a positive control on a detector's timing.

**What this repo already has (this thesis; repo files, not literature).** `src/obsplacement/protocol_gates.py` records
`onsetCommandIssued` and `onsetCommandReturned` around the onset command (lines 40–43). Gate F1 passes only an onset
stamp whose source is `"pre-command"` and fails a post-command probe (lines 72–74, `COMMAND_BOUNDED_ONSET`, line 137).
G2 uses "Onset = onsetCommandIssued (a lower bound, F-ADH-085)" (line 89). The Hotel readout review proposes the
Docker `pause` event as a freeze stamp and says it "is retained in `docker-events.json`"
(`research/traffic-sweep/readout-hotel-r3/REVIEW.md`, item n); where that file is produced was not checked here. So
the command-bounded half of an onset interval exists already; what is new below is an upper bound from a confirmed
effect.

**Recommendation for this thesis (n).**

1. Stamp onset as an **interval**: [injection command issued, effect confirmed]. Keep the pre-command stamp as the
   lower bound, as F1 requires. For pause, take the upper bound from the Docker `pause` event (nanosecond stamp; the
   freeze is very probably complete by then, L33, L34, L35, with the containerd path untraced). For CPU throttle and
   netem no source was read on when the effect starts; use a readback after the command (e.g. the container's
   `cpu.max`, or `tc qdisc show`) as the upper bound. The stamping is an engineering default; letting F1 or G2 use the
   upper bound changes a frozen gate and is a **preregistration decision for the user**.
2. Classify each ledger request by its [issue, end] time against the onset interval: **before**, **straddling**,
   **after**. Straddling requests are "ambiguous": excluded from the positive-control check and counted separately.
   The closest precedent is a buffer zone at label boundaries for label misalignment (L9). The only span rule found
   (L17, start time, implicit) would put straddling spans in "no fault". Note that G2 today attributes rows "by
   schedule even when they end after onset" (`protocol_gates.py`, G2 text). Which rule to use is an analysis
   definition; if it changes P1–P4 verdicts it is the **user's decision**.
3. **Positive control**: write its tolerance down before the run, as L37 and L39 do. Example form: "the ledger's first
   failed request falls no later than the onset upper bound plus the client timeout". The value is the user's call; no
   published tolerance for detection timing was found.
4. In a paired lead (sensor vs ledger, same episode) the onset cancels, because both delays are measured from the same
   onset. The onset interval still matters for three things: which observations count as post-onset, the absolute time
   to detection, and impact before detection. (**this thesis**, my reasoning, no source)

### 1.3 Conclusions with scope

| id | conclusion (I conclude) | scope | basis |
|---|---|---|---|
| C-m1 | Research that defines detection delay (placement, change detection, anomaly benchmarks) uses event time on a sampling grid. Operations and agent benchmarks use notification or agent time. | general practice (placement part: one research group, L1–L3) | L1–L4, L6–L9; L11, L12, L24, L25 |
| C-m2 | None of the 6 microservice RCA/anomaly papers read (2023–2026) defines or reports a detection delay. Four older ones were not opened (§3.12), so "no convention" holds for what was read. | general practice (by absence; denominator 6) | L19–L23, L26. String search of their text layers for "detection delay", "time to detect", "detection latency": 0 hits; for "detection time": 30 hits, all in L20 (BARO), where it is an estimated onset fed to RCA, not a delay metric. Evaluation sections read. |
| C-m3 | Reporting event-time detection and a pipeline delay separately appears in one telemetry-design paper. Sensor placement keeps a post-detection response delay apart from detection time: an analogy, not the same quantity. | one paper (L27); L2, L3 analogy only | L2, L3, L27 |
| C-m4 | No source sets a minimum margin before calling one detector faster. | general practice (by absence; denominator 12: the sources that score or compare detection timing, L1–L4, L6–L9, L11, L24, L25, L27; the other 28 are not sources where such a margin could appear) | §3 |
| C-m5 | Oxn (closest prior work) measures visibility, not time; its labelling uses event stamps (metric sample time, span start time). | tool-specific | L15–L18 |
| C-n1 | Onset ground truth is a point stamp from the injection record; the effect is assumed. | general practice | L17, L19, L20, L21, L26 |
| C-n2 | Verifying that a fault had an effect is done per case, by user-facing impact, not per timestamp. | one paper | L22 |
| C-n3 | For `docker pause`, Docker's `pause` event is very probably a post-freeze stamp, so [command, event] bounds onset. Probable, not proven: the containerd/shim path was not traced. | tool-specific | L33, L34, L35 |
| C-n4 | No explicit rule for in-flight requests at onset exists in what was read; one implicit span-level rule exists (Oxn, span start time). | general practice (by absence; denominator 7: L17, L19, L20, L21, L22, L23, L26) | as listed |
| C-n5 | Positive controls with explicit tolerances exist in chaos/alerting tools, not in the RCA/anomaly benchmarks read. | tool-specific | L30, L36, L37, L39 |
| C-n6 | In paired sensor-vs-ledger leads the onset error cancels; it matters for eligibility, absolute delay and impact. | this thesis | reasoning |

---

## 2. Tables

### 2.1 Question m: event time vs availability time

| approach | who uses it | how they handle the gap / resolution | fit for this thesis |
|---|---|---|---|
| Event time with an ideal sensor, on a simulation grid | L1, L2, L3 (one research group) | T(i, s) = time the contaminant (or cascade) reaches sensor s. Instant alarm explicit in L1 and L3. A post-detection response delay can be added to the penalty (L2 relaxation; L3 Case C, 3 h). Grid: 5-minute steps. | **High.** Same T(s, i) as the thesis objective (CELF on Leskovec's form). Supports event time as primary. Their separate delay is a response delay, not a pipeline delay (analogy only). |
| Delay in samples, at a fixed false-alarm rate | L4 (Lorden criterion; L5 abstract only) | Delay = alarm index minus change index (+1). Criterion: smallest delay for a fixed mean time between false alarms. Resolution: one sample. | **High** for the comparison rule: compare sensors at a matched no-fault firing rate. Also suggests reporting low-rate sensors' delay in "observations after onset". |
| Flagged data point's position in a labelled window | L6 (NAB), L7, L8 (SR-CNN), L9 (VUS); L40 criticises NAB's data | Detectors replay recorded streams; no pipeline delay exists. Earliness = relative position in a window (L6, L7). SR-CNN credits a detection up to k samples late (L8: k = 7 for minutely data). VUS adds a buffer at label boundaries for label misalignment (L9). | **Medium.** Confirms event time. L9 is a precedent for a transition zone at onset; their windows are minutes, not 0.1–0.3 s. |
| Two clocks: event time and processing time | L10 (Dataflow) | Event time never changes; processing time changes as data moves; the gap between them ("skew") varies over time. No clock synchronisation assumed. | **Vocabulary.** Supports keeping both clocks and naming them. |
| Notification / awareness time | L11 (SRE workbook), L12 (Incident Metrics in SRE), L13 (DORA) | Detection time = time to send the notification; depends on the alert window (L11). Detection = operator becomes aware (L12). MTTx called statistically weak (L12). DORA has no detection metric (L13). | **Low** as primary. Supports a secondary "operational" view only. L11's low-traffic section supports traffic rate as a parameter. |
| Detection time at the monitor (failure detectors) | L14 | T_D runs from the crash to when the *monitoring* process starts suspecting permanently; it therefore contains the heartbeat and transport path (my reading of the definition). | **Medium.** A well-defined availability-time metric; useful as the model for the second view. |
| Visibility only, no time | L15, L16, L17, L18 (Oxn line) | A fault is "visible" if a classifier separates [t0, t1] from [t-1, t0). Labels: metric samples by their timestamp, spans by their start time, against the treatment interval. MTTD listed as future work (L15). | **Closest prior work, no timing standard.** The thesis adds what Oxn left out: time to detection. |
| Window, sample or case classification | L19, L20, L21, L22, L23, L26 | No detection delay. Windows or samples during injection are "abnormal" (L19, L20). RCA given the injection time (L20, L21); BARO also estimates an onset ("anomaly detection time") and tests RCA's sensitivity to it (L20). | **None to adopt** (C-m2). |
| Agent time | L24 (AIOpsLab), L25 (ITBench) | TTD = time from fault occurrence to detection (L24); its results table reports agent "Time (s)" (agent time is my reading). In L25, "MTTD" means mean time to *diagnosis*, in seconds of agent time. | **Low.** Different question (agent speed). Note the acronym clash. |
| Alarm time including export window, plus pipeline time separately | L27 (Kestrel, NOMS 2026) | TTFD = median delay from onset to first alarm. Postcards export at once; sketches wait for the 1 s window end, so they alarm later. Pipeline processing (ingestion, features, ML) reported separately, in ms. No significance test. | **High as precedent** for reporting both. One paper, 5G user planes, not microservices. |
| Pipeline mechanics (what the availability delay is made of) | L38 (OTel batch span processor), L39 (Prometheus) | Spans are exported in batches, default at most 5000 ms apart (L38). An alert with a `for` clause waits that long; without it, it fires on the first evaluation (L39). | **High** for listing the per-sensor availability components. |

### 2.2 Question n: fault onset ground truth, in-flight requests, positive controls

| approach | who uses it | how they handle the gap / resolution | fit for this thesis |
|---|---|---|---|
| Point stamp from the injection record; effect assumed | L17 (Oxn code), L19 (Eadro), L20 (BARO), L21 (RCAEval), L26 (AIOps Challenge 2022 via TGAD) | No bound on the effect time. L20 notes a 1–3 s lag by eye, uses the injection time anyway, and is the only one to test sensitivity to onset error (shift −40 to +40, §4.8.1). L26: no end time given; set by hand with a two-minute maximum. | **Matches the current stamp.** Shows the field accepts seconds-level onset error, which is too coarse for 0.1–0.3 s leads. |
| Effect verified per case, by user-facing impact | L22 (Fang et al., FSE 2026) | Keep a case only if entry SLIs show a significant change (z-tests, thresholds). 84.4 % of first injections showed none. | **Good gate** for "did the fault act at all". Gives no timestamp. |
| Fault on before traffic starts | L23 (AnoMod); simulated onsets in L1–L3 | No in-flight requests at onset by design (L23). Onset known exactly in simulation (L1–L3). | **Not usable**: removes the time-to-detection question. |
| Tool records "injection action done" | L28 (Chaos Mesh), L29 (ChaosBlade), L30 (LitmusChaos); L31 (Gremlin), L32 (Chaos Monkey) without documented stamp semantics | Chaos Mesh: `Apply` record events and `AllInjected`, second-precision stamps. ChaosBlade: `Success` after the command returns; only for long-running fault processes outside pod/container/node scope (and not over ssh) after a 100 ms sleep and a check that the process exists; nanosecond stamps. Litmus: `ChaosInject` event after the stressor is started (fixed 700 ms sleep before resuming it), second-precision stamps. Gremlin: separate `Initializing` ("creating the desired impact") and `Running` stages. Chaos Monkey: trackers, no-op by default. | **Medium.** None confirms the effect. Useful only as an upper bound on the *command*, and only at the stated resolution. |
| Runtime/kernel-confirmed effect | L33 (Docker docs + moby code), L34 (kernel cgroup docs), L35 (runc freezer code) | cgroup v2 signals "frozen 1" when freezing completes (L34). runc's v2 freezer polls for it every 10 ms (L35). Docker emits `pause` after the runtime's pause call returns (L33), with a nanosecond stamp. The containerd/shim link between them was not traced. | **High for pause** (hosts are cgroup v2). Gives [command, event] as a probable onset interval with about 10 ms granularity. Not used by any benchmark read. |
| Tolerance zone at label boundaries | L9 (label misalignment); L8, L6 (detection credit, not label uncertainty) | Buffer of length ℓ at boundaries "to accommodate the false tolerance of labeling" (L9). Credit up to k samples late (L8); window around the label (L6). | **Medium.** L9 is the precedent for marking straddling requests "ambiguous" instead of forcing a label. |
| In-flight requests / spans at onset | L17 (implicit span start-time rule); L19, L20, L22 (window/case labels); L23 (avoided) | No explicit request-level rule. Oxn assigns a span by its start time only. | **Thesis must declare its own rule** (before / straddling / after). |
| Positive control with declared tolerance | L36 (Principles of Chaos), L37 (Chaos Toolkit), L30 (Litmus probes), L39 (promtool rule tests); L6 (NAB artificial files) | Steady-state probe must match an exact value or fall in an inclusive range (L37). Fault verdict = conjunction of probes (L30). Expected alerts checked at a given evaluation time, exact match by default (L39). NAB adds artificial files with known anomalies (L6). | **High as a form**: state the expected response and its tolerance in advance. No published tolerance value for detection timing. |

---

## 3. Sources

All accessed 2026-10-04. DOIs were checked against Crossref metadata (title, authors, year match the paper read);
arXiv DOIs were checked to resolve at doi.org. "OA PDF" is the copy that was read unless stated. BibTeX keys follow
`firstauthorYEARword`.

**Zotero import (DOIs, one per line):** 10.1145/1281192.1281239, 10.1061/(ASCE)0733-9496(2008)134:6(516),
10.1061/(ASCE)0733-9496(2008)134:6(556), 10.1214/aoms/1177693055, 10.1109/ICMLA.2015.141, 10.48550/arXiv.1803.03639,
10.1145/3292500.3330680, 10.14778/3551793.3551830, 10.1109/TKDE.2021.3112126, 10.14778/2824032.2824076, 10.1109/12.980014,
10.1109/ICSA59870.2024.00015, 10.1109/ICSA-C63560.2024.00035, 10.1109/ICSA-C65153.2025.00036,
10.1109/ICSE48619.2023.00150, 10.1145/3660805, 10.1145/3701716.3715290, 10.1145/3797100, 10.1145/3793302.3793324,
10.48550/arXiv.2501.06706, 10.48550/arXiv.2502.05352, 10.1109/ASE56229.2023.00138, 10.1109/NOMS69089.2026.11668159.

### 3.1 Sensor placement

**L1** · `leskovec2007costeffective`
Leskovec, Krause, Guestrin, Faloutsos, VanBriesen, Glance. *Cost-effective outbreak detection in networks.* KDD 2007,
pp. 420–429. DOI 10.1145/1281192.1281239. OA PDF https://www.cs.cmu.edu/~jure/pubs/detect-kdd07.pdf.
Read: §2.1–2.2 problem statement and placement objectives (PDF p. 2), §6.2 Objective functions (PDF p. 8).
Says:
- "As soon as the event reaches a selected node, an alarm is triggered"
- "In the water network, T (i, s) is the time it takes for contaminated water to reach node s in scenario i (depending
  on outbreak location and time)."
- "Detection time (DT) measures the time passed from outbreak till detection by one of the selected nodes."
- "We consider simulations of 48 hours length, with 5 minute simulation timesteps."

**L2** · `krause2008efficient`
Krause, Leskovec, Guestrin, VanBriesen, Faloutsos. *Efficient Sensor Placement Optimization for Securing Large Water
Distribution Networks.* J. Water Resour. Plann. Manage. 134(6):516–526, 2008.
DOI 10.1061/(ASCE)0733-9496(2008)134:6(516). OA PDF (author manuscript) https://las.inf.ethz.ch/files/krause08efficient.pdf.
Read: "Sensor placement objectives" (manuscript pp. 5–7), "System Implementation" (p. 16).
Says:
- "we define the detection time T (s, i) as the time it takes for sensor s to detect the intrusion defined by scenario
  i."
- "Our notion of penalties implies that upon detection, immediate action is taken and no more contaminated water is
  consumed. This notion can be easily relaxed, e.g., handling the case where the response is delayed by a fixed amount
  of time."
- "we perform water quality simulations using the EPANET 2.0 software (Rossman, 1999), with a temporal resolution of 5
  minutes."

**L3** · `ostfeld2008battle`
Ostfeld, Uber, Salomons, Berry, Hart, Phillips, et al. *The Battle of the Water Sensor Networks (BWSN): A Design
Challenge for Engineers and Algorithms.* J. Water Resour. Plann. Manage. 134(6):556–568, 2008.
DOI 10.1061/(ASCE)0733-9496(2008)134:6(556). OA PDF https://cs.stanford.edu/people/jure/pubs/bwsn-jwrpm09.pdf.
Read: design objectives Z1 (p. 557), Base Case A and Derivative Cases (p. 558), nondetections (p. 563).
Says:
- "For a particular contamination scenario, the time of detection by a sensor is the elapsed time from the start of the
  contamination event, to the first identified presence of a nonzero contaminant concentration." (the text layer
  splits this sentence across a column break; the words are in the original order)
- "Sensors instantly detected any nonzero contaminant concentration and action was taken to eliminate further exposure
  without delay."
- "Identical to Base Case A except that the response delay was 3 h, i.e., it took 3 h after detection for emergency
  response to limit contaminant exposure."

### 3.2 Change-point and sequential detection

**L4** · `basseville1993detection`
Basseville, Nikiforov. *Detection of Abrupt Changes: Theory and Application.* Prentice-Hall, 1993. No DOI.
OA PDF (authors' copy) https://people.irisa.fr/Michele.Basseville/kniga/kniga.pdf.
Read: §1.1 (pp. 1–4), §1.4.2.1 (p. 30 region), §4.4 Formal Definition of Criteria (pp. 151–152).
Says:
- "We call abrupt change any change in the parameters of the system that occurs either instantaneously or at least
  very fast with respect to the sampling period of the measurements."
- "Usually the overall criterion consists in minimizing the delay for detection for a fixed mean time between false
  alarms."
- "This criteria was introduced in [Lorden, 1971]." (said of the worst mean delay, Definition 4.4.3, which conditions on
  the alarm time ta and the change time t0 as sample indices)

**L5** · `lorden1971procedures`
Lorden. *Procedures for Reacting to a Change in Distribution.* Ann. Math. Statist. 42(6):1897–1908, 1971.
DOI 10.1214/aoms/1177693055. OA status not verified (PDF download was refused). Page:
https://projecteuclid.org/journals/annals-of-mathematical-statistics/volume-42/issue-6/Procedures-for-Reacting-to-a-Change-in-Distribution/10.1214/aoms/1177693055.full
Read: abstract only, through a fetch tool. **Not used as support**; the criterion is cited through L4.

### 3.3 Anomaly-detection benchmarks and metrics

**L6** · `lavin2015nab`
Lavin, Ahmad. *Evaluating Real-Time Anomaly Detection Algorithms – the Numenta Anomaly Benchmark.* ICMLA 2015,
pp. 38–44. DOI 10.1109/ICMLA.2015.141. OA PDF https://arxiv.org/pdf/1510.03336.
Read: §II.B Scoring Real-Time Anomaly Detectors (pp. 3–5), dataset paragraph (p. 3).
Says:
- "works with real time data (no look ahead)" (requirement iv of the ideal detector)
- "If there are multiple detections within a window, the earliest detection is given credit and counted as a true
  positive."
- "In Eq. (1), y is the relative position of the detection within the anomaly window."
- "We also include some artificially-generated data files that test anomalous behaviors not yet represented in the
  corpus's real data"

**L7** · `tatbul2018precision`
Tatbul, Lee, Zdonik, Alam, Gottschlich. *Precision and Recall for Time Series.* NeurIPS 2018. No publisher DOI;
arXiv DOI 10.48550/arXiv.1803.03639. OA PDF https://arxiv.org/pdf/1803.03639.
Read: §3 positional bias (p. 5).
Says:
- "δ() signifies the urgency of when an anomaly is detected and reacted to."

**L8** · `ren2019timeseries`
Ren, Xu, Wang, Yi, Huang, Kou, Xing, Yang, Tong, Zhang. *Time-Series Anomaly Detection Service at Microsoft.* KDD
2019, pp. 3009–3017. DOI 10.1145/3292500.3330680. OA PDF https://arxiv.org/pdf/1906.03821.
Read: §4 Experiments, "Metrics" (p. 6).
Says:
- "If any point in an anomaly segment can be detected by the algorithm, and the delay of this point is no more than k
  from the start point of the anomaly segment, we say this segment is detected correctly."
- "In our experiments, we set k = 7 for minutely time-series, k = 3 for hourly time-series and k = 1 for daily
  time-series following the requirement of real application."

**L9** · `paparrizos2022volume`
Paparrizos, Boniol, Palpanas, Tsay, Elmore, Franklin. *Volume Under the Surface: A New Accuracy Evaluation Measure for
Time-Series Anomaly Detection.* PVLDB 15(11):2774–2787, 2022. DOI 10.14778/3551793.3551830.
OA PDF https://www.vldb.org/pvldb/vol15/p2774-paparrizos.pdf.
Read: §3.2 limitations due to lag (p. 5), §4 buffer region (p. 6).
Says:
- "Overall such a lag may also exist by the approximation made during the labeling phase."
- "there should be a transition region between the normal and abnormal subsequences to accommodate the false
  tolerance of labeling in the ground truth"

**L40** · `wu2021current`
Wu, Keogh. *Current Time Series Anomaly Detection Benchmarks are Flawed and are Creating the Illusion of Progress.*
IEEE TKDE, 2021 (early access). DOI 10.1109/TKDE.2021.3112126. OA PDF https://arxiv.org/pdf/2009.13807 (arXiv version
read). Read: end of §2.2 Triviality (p. 3), opening of §2.4 Mislabeled Ground Truth.
Says:
- "The Numenta archive is commendably diverse, however most of the examples, like the one shown in Fig. 2, readily
  yield to a single line of code."
- "All of the benchmark datasets appear to have mislabeled data, both false positives and false negatives."
I conclude: this qualifies NAB's *data* (L6), not its scoring rule, which is what this note cites.

### 3.4 Stream processing

**L10** · `akidau2015dataflow`
Akidau, Bradshaw, Chambers, Chernyak, Fernández-Moctezuma, Lax, McVeety, Mills, Perry, Schmidt, Whittle. *The
Dataflow Model.* PVLDB 8(12):1792–1803, 2015. DOI 10.14778/2824032.2824076.
OA PDF https://www.vldb.org/pvldb/vol8/p1792-Akidau.pdf.
Read: §1.3 Time Domains (p. 1794).
Says:
- "Event Time, which is the time at which the event itself actually occurred, i.e. a record of system clock time (for
  whatever system generated the event) at the time of occurrence."
- "Processing Time, which is the time at which an event is observed at any given point during processing within the
  pipeline, i.e. the current time according to the system clock. Note that we make no assumptions about clock
  synchronization within a distributed system."
- "Event time for a given event essentially never changes, but processing time changes constantly for each event as it
  flows through the pipeline and time marches ever forward."

### 3.5 SRE practice

**L11** · `thurgood2018alerting`
Thurgood, with Frame, Lenton, Quinito, Tolchanov, Trdin. *Alerting on SLOs.* Chapter 5 in *The Site Reliability
Workbook*, O'Reilly/Google, 2018. No DOI. HTML https://sre.google/workbook/alerting-on-slos/.
Read: "Alerting Considerations", approaches 1–2, "Low-Traffic Services and Error Budget Alerting".
Says:
- "Detection time" — "How long it takes to send notifications in various conditions. Long detection times can
  negatively impact the error budget."
- "Detection time is good: 0.6 seconds for a total outage." (approach 1, 10-minute window)
- "If a system has either a low number of users or natural low-traffic periods (such as nights and weekends), you may
  need to alter your approach."

**L12** · `davidovic2021incident`
Davidovič. *Incident Metrics in SRE: Critically Evaluating MTTR and Friends.* O'Reilly, 2021 (ISBN
978-1-098-10313-2). No DOI. OA PDF https://static.googleusercontent.com/media/sre.google/en//static/pdf/IncidentMeticsInSre.pdf.
Read: "Incident Life Cycle and Timing" (pp. 2–3), conclusion of the MTTx analysis.
Says:
- "Detection" — "When the system's operator becomes aware of the ongoing problem"
- "Many other incident metrics, such as the time to detection, suffer from the same problem."

**L13** · `dora2026fourkeys`
DORA. *DORA's software delivery performance metrics* (guide, last updated 2026-01-05). No DOI.
HTML https://dora.dev/guides/dora-metrics-four-keys/. Read: whole page.
Says:
- "shifting from the original four keys to the current five-metric model"
- "Failed deployment recovery time: The time it takes to recover from a deployment that fails and requires immediate
  intervention."
I conclude: none of the five metrics is a detection time (page read in full).

### 3.6 Distributed failure detectors

**L14** · `chen2000qos`
Chen. *On the Quality of Service of Failure Detectors.* PhD dissertation, Cornell University, 2000. No DOI.
OA PDF http://disi.unitn.it/~montreso/ds/papers/fd-qos.pdf. Read: §2.2.2 Primary Metrics (pp. 19–21).
Journal version: Chen, Toueg, Aguilera, IEEE Trans. Computers 51(1):13–32, 2002, DOI 10.1109/12.980014 — **not read**.
Says:
- "Detection time (TD ): Informally, TD is the time that elapses from p's crash to the time when q starts suspecting p
  permanently."

### 3.7 Observability experiments (Oxn line, closest prior work)

**L15** · `borges2024informed`
Borges, Bauer, Werner, Gebauer, Tai. *Informed and Assessable Observability Design Decisions in Cloud-Native
Microservice Applications.* ICSA 2024, pp. 69–78. DOI 10.1109/ICSA59870.2024.00015. OA PDF https://arxiv.org/pdf/2403.00633.
Read: §4 Approach to quantify observability effectiveness (p. 4), §5 Oxn (p. 6), §6.1–6.2 (pp. 6–7), §7 (p. 9).
Says:
- "A fault f can be considered visible in metric m if the data recorded during the occurrence of the fault, represented
  by the time interval [t0 − t1 ], is significantly different from the data recorded under normal conditions, in time
  interval [t-1 − t0 [, and thus detected by detection mechanism d."
- "They serve to track the long-term effect of reliability measures and of reliability teams but are too coarse and can
  be influenced by many different overlapping factors." (about MTTD/MTTR)
- "we aim to enhance our tool by incorporating support for alerting systems and Mean Time To Detect (MTTD)."
Setup facts read: base metrics at a 5 s sampling rate, a custom metric at 60 s, 1 % trace sampling; detection = a
logistic-regression classifier with accuracy threshold 0.7; 10 runs of 10 min per fault.

**L16** · `borges2024oxn`
Borges, Bauer, Werner. *OXN – Automated Observability Assessments for Cloud-Native Applications.* ICSA-C 2024 (poster
track), pp. 167–170. DOI 10.1109/ICSA-C63560.2024.00035. OA PDF https://arxiv.org/pdf/2407.09644.
Read: whole paper (4 pages).
Says:
- "we feed the observability data generated during the experiment through a fault detection mechanism and report if the
  faults were detected in any of the observed metrics."
- "The observer module provides methods that allow the runner to pass experiment information, e.g. execution start and
  end timestamps, to the response variables for labelling purposes." (the PDF text layer interleaves two columns here;
  the words are in the original order)

**L17** · `oxn2024code`
Oxn source code, https://github.com/nymphbox/oxn, HEAD commit 4b3fde9e (2024-10-14). No DOI.
Read: `oxn/runner.py` (runtime treatments), `oxn/responses.py` (labelling), `oxn/treatments.py` (`PauseTreatment`).
Says (code, verbatim):
- `treatment.start = utc_timestamp()` / `treatment.inject()` / `treatment.clean()` / `treatment.end = utc_timestamp()`
- `"""Label a dataframe containing Jaeger spans depending on the span start timestamp"""`
- Metric rows (line breaks removed): `predicate = (treatment_start <= self.data["timestamp"]) & ( self.data["timestamp"] <= treatment_end )`
I conclude: the treatment start is stamped *before* the Docker pause call; `PauseTreatment.inject()` calls
`container.pause()` and then sleeps for the duration. There is no effect check. `treatment.end` is stamped after
`clean()` (the unpause) returns, so the labelled interval includes the unpause call.

**L18** · `borges2025continuous`
Borges, Werner. *Continuous Observability Assurance in Cloud-Native Applications.* ICSA-C 2025, pp. 182–185.
DOI 10.1109/ICSA-C65153.2025.00036. OA PDF https://arxiv.org/pdf/2503.08552.
Read: §3 Background (Oxn), §5 Preliminary Instantiation, conclusion.
Says:
- "With OXN, we can evaluate the observability system's effectiveness by injecting faults into the microservice system
  under experimentation (SUE) and monitoring the configured detection mechanisms, such as alerting thresholds, while
  also measuring the costs produced by the observability systems."
I conclude: as of this 2025 paper the Oxn line still reports detected/not detected and cost, not detection time.

### 3.8 Microservice AIOps / RCA benchmarks (2023–2026)

**L19** · `lee2023eadro` (project S1)
Lee, Yang, Chen, Su, Lyu. *Eadro: An End-to-End Troubleshooting Framework for Microservices on Multi-source Data.*
ICSE 2023, pp. 1750–1762. DOI 10.1109/ICSE48619.2023.00150. OA PDF https://arxiv.org/pdf/2302.05092.
Read: §V.A Data Collection (p. 7), §V.E RQ1 (p. 8).
Says:
- "Ground truths are based on the known injection operations, i.e., if a fault is injected, then the current
  observation window is abnormal; otherwise, it is normal."
- "We generate 0.2∼0.5 and 2∼3 requests per second for TT and SN at a uniform rate, respectively."

**L20** · `pham2024baro`
Pham, Ha, Zhang. *BARO: Robust Root Cause Analysis for Microservices via Multivariate Bayesian Online Change Point
Detection.* Proc. ACM Softw. Eng. 1(FSE), Article 98, 2024. DOI 10.1145/3660805. OA PDF https://arxiv.org/pdf/2405.09330.
Read: §4.1 (p. 12), §4.2.1 (p. 13), §4.6 (p. 15), §4.8.1 (p. 18).
Says:
- "Upon visual inspections, we observed that the deviations between the fault injection time and the onset of failure
  symptoms in the metrics data are usually around 1-3 seconds."
- "we use the fault injection time 𝑡 inject as a proxy for the true anomaly occurence time since we have observed that
  in our benchmark microservice systems, the anomaly occurence time closely aligns with the fault injection time."
- "We determine metrics data collected during a fault injection period as abnormal, while metrics data before that
  period is considered normal."
Also read: §4.8.1 shifts the assumed onset by −40 to +40 around the injection time to test RCA robustness.

**L21** · `pham2025rcaeval` (project S3)
Pham, Zhang, Ha, Salim, Zhang. *RCAEval: A Benchmark for Root Cause Analysis of Microservice Systems with Telemetry
Data.* WWW Companion 2025, pp. 777–780. DOI 10.1145/3701716.3715290. OA PDF https://arxiv.org/pdf/2412.17015.
Also read: repository README, https://github.com/phamquiluan/RCAEval (commit 259ea41, 2026-09-29), "File Structure".
Read: §3.3–3.4 (p. 3), README.
Says:
- "We allow the microservice systems to run normally to collect normal telemetry data. Then, we inject a fault into a
  randomly selected running service and collect the abnormal telemetry data."
- README: "`inject_time.txt`: Fault injection timestamp (Unix timestamp)"

**L22** · `fang2026rethinking` (project S2)
Fang, Zhang, Yang, Wu, Xu, Wang, et al. *Rethinking the Evaluation of Microservice RCA with a Fault
Propagation-Aware Benchmark.* Proc. ACM Softw. Eng. (FSE 2026), pp. 1605–1627. DOI 10.1145/3797100.
OA PDF https://arxiv.org/pdf/2510.04711 (arXiv version read).
Read: §4.1 framework, §4.7 Impact-Driven Selection (p. 10), §5.3 setup (p. 12), §6.1.1 (p. 13).
Says:
- "we implement a strict, impact-driven selection process where a fault is included if and only if it produces a
  discernible anomaly at the system's entry points, as measured by user-facing Service Level Indicators (SLIs)."
- "Our analysis reveals that a vast majority of initial fault injections (84.4%) were classified as 'No Anomaly',
  failing to produce any user-perceivable impact."
- "each data collection cycle consists of 4 minutes of normal operation data followed by 4 minutes of failure data."

**L23** · `ping2026anomod` (project S4)
Ping, Mazhar, Wang, Song, Mäntylä. *AnoMod: A Dataset for Anomaly Detection and Root Cause Analysis in Microservice
Systems.* MSR 2026, pp. 677–681. DOI 10.1145/3793302.3793324. OA PDF https://arxiv.org/pdf/2601.22881.
Read: §2.4 Data Collection Pipeline (pp. 3–4).
Says:
- "Importantly, the pipeline logic ensures the anomaly case is activated precisely before the workload starts and is
  terminated immediately upon workload completion."

**L24** · `chen2025aiopslab`
Chen, Shetty, Somashekar, Ma, Simmhan, Mace, Bansal, Wang, Rajmohan. *AIOpsLab: A Holistic Framework to Evaluate AI
Agents for Enabling Autonomous Clouds.* MLSys 2025 (Proceedings of Machine Learning and Systems 7). No publisher DOI;
arXiv DOI 10.48550/arXiv.2501.06706. OA PDF https://arxiv.org/pdf/2501.06706. Proceedings page:
https://proceedings.mlsys.org/paper_files/paper/2025/hash/d1f9e4a9f109b6e8b75ed362736f22ec-Abstract-Conference.html.
Read: §3 problem formulation (p. 3), evaluation metrics (p. 7), Tables 3–4 captions.
Says:
- "the detection task employs Time-to-Detect (TTD) to measure the time taken to detect a fault."
- "Time-to-Detect (TTD) is the time elapsed from the occurrence of a fault to its detection, and Time-to-Mitigate (TTM)
  is the time taken from detection to complete mitigation of the fault."
Not found in the sections read: when the TTD clock starts (injection command or effect).

**L25** · `jha2025itbench`
Jha, Arora, Watanabe, et al. *ITBench: Evaluating AI Agents across Diverse Real-World IT Automation Tasks.* arXiv
2502.05352, 2025 (venue not verified). arXiv DOI 10.48550/arXiv.2502.05352. OA PDF https://arxiv.org/pdf/2502.05352.
Read: SRE evaluation metrics (PDF p. 30), Table caption with MTTD.
Says:
- "we calculate MTTD, which measures how soon (in seconds) an agent performs diagnosis. Otherwise, MTTD is set to
  infinite."

**L26** · `huang2023twin`
Huang, Yang, Yu, Li, Zheng. *Twin Graph-Based Anomaly Detection via Attentive Multi-Modal Learning for Microservice
System.* ASE 2023, pp. 66–78. DOI 10.1109/ASE56229.2023.00138. OA PDF https://arxiv.org/pdf/2310.04701.
Read: §V.A Datasets (p. 9).
Says:
- "It is crucial to note that the end time of an injected anomaly is not provided. To address this limitation, we
  manually set the end time with a maximum interval of two minutes." (about the AIOps Challenge 2022 dataset)

**L27** · `saha2026rethinking`
Saha, Limam, Xiao, Boutaba. *Rethinking Telemetry Design for Fine-Grained Anomaly Detection in 5G User Planes.* NOMS
2026. DOI 10.1109/NOMS69089.2026.11668159. OA PDF https://arxiv.org/pdf/2510.27664 (arXiv version read).
Read: §VI setup (telemetry export), §VI.C Responsiveness, §VI.D pipeline latency (p. 7).
Says:
- "measured as the time-to-first-detection (TTFD): the median delay between anomaly onset and the first alarm."
- "This is because postcards are exported immediately upon threshold crossings, while Kestrel waits for the end of each
  window to query sketches."
- "We measure end-to-end processing per 1s window, broken down into ingestion (I), feature extraction (F), and ML
  detection (ML)."

### 3.9 Chaos and fault-injection tools (primary for tool behaviour)

**L28** · `chaosmesh2026docs`
Chaos Mesh. *Inspect Results of Chaos Experiments* (docs v2.8.4), https://chaos-mesh.org/docs/inspect-chaos-experiments/;
source `api/v1alpha1/common_types.go`, https://github.com/chaos-mesh/chaos-mesh (last change 6545614, 2025-07-03);
Kubernetes `apimachinery/pkg/apis/meta/v1/time.go`. No DOI.
Says:
- "AllInjected: indicates the faults have been successfully injected to all target pods."
- Code: `// Apply means this event is recorded, when we inject the chaos` / `// typically, when we call impl.Apply()`;
  and `// Timestamp is time when we create this event`, typed `*metav1.Time`.
- Kubernetes code: `metav1.Time` JSON uses `t.UTC().AppendFormat(buf, time.RFC3339)`; `// Rfc3339Copy returns a copy of the Time at second-level precision.`
I conclude: Chaos Mesh's per-target record stamps have one-second resolution on the wire. (tool-specific)

**L29** · `chaosblade2026docs`
ChaosBlade. *blade status* (docs v1.7.1), https://chaosblade.io/en/docs/1.7.1/getting-started/chaosblade-tool-quick-start/cli-mode-user-guide/blade-status/;
source `cli/cmd/create.go`, `data/experiment.go`, https://github.com/chaosblade-io/chaosblade (master, read 2026-10-04). No DOI.
Says:
- Docs (Chinese, verbatim): "--status string 实验状态，create 类型支持 Created|Success|Error|Destroyed 状态" (my
  translation: experiment status; the create type supports the states Created, Success, Error, Destroyed). Example
  stamp: `"CreateTime": "2020-01-14T14:09:49.152708+08:00"`.
- Code: `// todo -> need to find a better way to query the status` followed by `time.Sleep(time.Millisecond * 100)`,
  inside the branch `if expModel.ActionProcessHang && scope != "pod" && scope != "container" && scope != "node" && expModel.ActionFlags["channel"] != "ssh" {`;
  in both branches the status is set to `Success` after the executor returns (in the branch, only if the process
  exists); `UpdateTime` written with `time.Now().Format(time.RFC3339Nano)`.

**L30** · `litmus2026probes`
LitmusChaos. *Resilience Probes* (docs v3.32.0), https://docs.litmuschaos.io/docs/concepts/probes; source
`chaoslib/litmus/stress-chaos/helper/stress-helper.go` and `pkg/events/event.go`, https://github.com/litmuschaos/litmus-go
(HEAD a299355, 2026-09-16). No DOI.
Says:
- "Continuous: The probe is executed continuously, with a specified polling interval during the chaos injection."
- "The pass criteria for a fault is the logical conjunction of all probes defined in the ChaosEngine and an inbuilt
  entry/exit criteria."
- Code: `// TODO: need a dynamic way to check the start of the process` followed by `time.Sleep(700 * time.Millisecond)`;
  the `ChaosInject` event (message `"Injecting " + experimentsDetails.ExperimentName + " chaos on application pod"`) is generated after the stress processes are
  started; event stamps are `FirstTimestamp: metav1.Time{Time: time.Now()}`.

**L31** · `gremlin2026experiments`
Gremlin. *Fault Injection > Experiments*, https://www.gremlin.com/docs/infrastructure-layer/attacks/. No DOI.
Read: "Experiment stages" table.
Says:
- Stage "Initializing", description "Experiment is creating the desired impact"
- Stage "Running", description "Experiment running on the host"

**L32** · `netflix2026chaosmonkey`
Netflix. *Chaos Monkey* docs: Tracker, https://netflix.github.io/chaosmonkey/Tracker/; Configuration file format,
https://netflix.github.io/chaosmonkey/Configuration-file-format/. No DOI.
Says:
- "A tracker is used to record termination events in some sort of external system."
- "Note that many of these configuration parameters (decryptor, trackers, error_counter, outage_checker) currently only
  have no-op implementations."

**L33** · `docker2026pause`
Docker. *docker container pause*, https://docs.docker.com/reference/cli/docker/container/pause/; *docker system events*,
https://docs.docker.com/reference/cli/docker/system/events/; moby source `daemon/pause.go`,
https://github.com/moby/moby (last change 9941082, 2025-10-25). No DOI.
Says:
- "The docker pause command suspends all processes in the specified containers. On Linux, this uses the freezer
  cgroup."
- Events docs list `pause`, `unpause` and `update` among container events; example line (truncated)
  "2017-01-05T00:35:58.859401177+08:00 container create".
- Code order in `containerPause`: `tsk.Pause(context.Background())`, then `container.State.Paused = true`, then
  `daemon.LogContainerEvent(container, events.ActionPause)`.
The pause docs link to the cgroup v1 freezer documentation; the measurement hosts run cgroup v2
(`research/host-topology.json`, lines 24, 199, 437), so L34's v2 text and L35's `fs2` code are the relevant path.
Not traced: the containerd/shim call path between `tsk.Pause` and runc. When Docker emits `update` for `docker update`
(CPU throttle) relative to the cgroup write: **not read**.

**L34** · `kernel2026cgroupv2`
Linux kernel documentation. *Control Group v2*, https://docs.kernel.org/admin-guide/cgroup-v2.html (`cgroup.freeze`);
*Freezer Subsystem* (v1), https://docs.kernel.org/admin-guide/cgroup-v1/freezer-subsystem.html. No DOI.
Says:
- "Freezing of the cgroup may take some time; when this action is completed, the 'frozen' value in the cgroup.events
  control file will be updated to '1' and the corresponding notification will be issued."
- v1: "FREEZING cgroup transitions into FROZEN state when all tasks belonging to the cgroup and its descendants become
  frozen."

**L35** · `opencontainers2025cgroups`
opencontainers/cgroups (used by runc), `fs2/freezer.go` (last change 6df7bae, 2025-07-09) and `fs/freezer.go`,
https://github.com/opencontainers/cgroups. No DOI.
Says:
- `// waitFrozen polls cgroup.events until it sees "frozen 1" in it.`
- `waitTime = 10 * time.Millisecond`, `maxIter = 1000`; `setFreezer` writes `cgroup.freeze` and then calls
  `readFreezer`, which calls `waitFrozen` when the file reads "1".

### 3.10 Steady state, tolerances, positive controls

**L36** · `principles2019chaos` (project S5)
*Principles of Chaos Engineering* (last update March 2019), https://principlesofchaos.org/. No DOI. Read: whole page.
Says:
- "Hypothesize that this steady state will continue in both the control group and the experimental group."
- "Try to disprove the hypothesis by looking for a difference in steady state between the control group and the
  experimental group."

**L37** · `chaostoolkit2026spec`
Chaos Toolkit. *Experiment API specification*, https://chaostoolkit.org/reference/api/experiment/. No DOI.
Read: "Steady State Probe Tolerance".
Says:
- "Each Probe MUST define a tolerance property that acting as a gate mechanism for the experiment to carry on or bail."
- "If it has only two values, those two values represent a lower and upper bound within which the Probe returned value
  must fall (inclusive)."

### 3.11 Telemetry pipeline mechanics

**L38** · `otel2026sdktrace`
OpenTelemetry Specification. *Tracing SDK*, "Batching processor",
https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/sdk.md. No DOI.
Says:
- "`scheduledDelayMillis` - the maximum delay interval in milliseconds between two consecutive exports. The default
  value is `5000`."

**L39** · `prometheus2026rules`
Prometheus docs. *Alerting rules*, https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/; *Unit
testing for rules*, https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/ (read from
`docs/configuration/*.md` in https://github.com/prometheus/prometheus, main). No DOI.
Says:
- "Alerting rules without the `for` clause will become active on the first evaluation."
- Unit tests: `# List of expected alerts which are firing under the given alertname at` / `# given evaluation time.`
- Unit tests: `# Setting fuzzy_compare true will very slightly weaken floating point comparisons.` (the only tolerance
  offered; by default values must match exactly)

### 3.12 Not read (never used as support)

- Lorden 1971 full text (L5, abstract only); Page 1954 (CUSUM).
- Chen, Toueg, Aguilera, IEEE TC 2002 (journal version of L14).
- Nezha (FSE 2023), MicroRCA (NOMS 2020), TraceRCA (IWQoS 2021), DiagFusion (TSC 2023): not opened. The 2023–2026
  set read instead is L19–L27.
- TSB-UAD (VLDB 2022): not opened; the same group's VUS (L9) was read.
- Classic dependability fault injection (e.g. Arlat et al., IEEE TSE 1990, on fault activation and error-detection
  latency): no open copy found. This is the gap most likely to hold an onset-vs-activation convention.
- `tc netem` and `docker update` semantics for when the effect starts.
- Google SRE book (2016) chapters other than the workbook chapter in L11.
- Fetched and searched, not used as separate support: Q. L. Pham, *Anomaly Detection and Root Cause Analysis for
  Microservice Systems*, PhD thesis, RMIT, arXiv 2606.09942 (2026); it repeats L20's injection-time convention and
  1–3 s observation. DeepTraLog (Zhang et al., ICSE 2022, DOI 10.1145/3510003.3510180), §4.1.1 only: faults are built
  into code branches, so there is no runtime onset. The slide version of L14 (dependability.org). A Rutgers PDF that
  turned out to be an unrelated paper.
- Fetches that failed (not read): Lorden 1971 full text (blocked), Avizienis et al. 2004 taxonomy (no PDF reached),
  Hsueh, Tsai, Iyer 1997 fault-injection survey (404), a CMU copy of L2 (404; the ETH copy was read).

### Independent review

One independent adversarial review, run 2026-10-04 by a separate subagent (model Fable, read-only, `adversarial-review`
type). It checked all 100 quotes in §3 against the text layers (93 exact; 7 differ only by column interleave,
hyphenation, inner-quote rendering or a math glyph; none wrong), about 40 attributions, all 11 scope labels, 6 tool
claims against the code, and 7 recommendations. Findings: 0 blockers, 4 major, 17 minor. All were applied: the
placement "precedent" for reporting both clocks was downgraded to an analogy (M1); the C-m4 denominator was narrowed
to 12 (M2); L1–L3 are labelled one research group (M3); the repo's onset contract (`protocol_gates.py` F1/G2) is now
stated beside recommendation n.1 (M4); the minors are reflected in wording, qualifiers and §3.12. The text after these
corrections was not re-reviewed.
