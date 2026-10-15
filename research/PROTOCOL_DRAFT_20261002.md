# Campaign protocol, draft 3 (2026-10-02; not yet reviewed as a whole)

Draft 2 (commit 6925491) was attacked by a judge panel (`research/protocol-review-20261002/JUDGE.md`, J1-J3 refuted, 2 of 3
members), a Fable soundness review (`SOUNDNESS_FABLE.md`: 5 blockers, 8 major), a Fable implementation plan (`PLAN_FABLE.md`)
and a Fable directions survey (`DIRECTIONS_FABLE.md`). This draft keeps what they found sound and replaces what they refuted.
Every change is traced to its source in brackets. ▶ = decision owed by the user (preregistration class).

## Decisions already made (user, 2026-10-02)
- ASOCA does not rest on rc11's campaigns (too inconsistent across SUTs).
- Consistency across SUTs before any campaign.
- The user is hands-on at every stage gate; no autonomous launches or reruns. TeaStore #20 stopped.

## What changed from draft 2, in one table
| draft 2 | draft 3 | source |
|---|---|---|
| per-fault recall/precision against a "wide set" | detection per (fault, placement) in the placement's own run, plus an **isolability matrix** over fault pairs relative to the ledger-only baseline | B1, J3, D1 |
| one base run defines the vocabulary | vocabulary per (SUT, posture) from ≥ 20 no-fault windows; "disappear" only for tokens the posture collects; each channel's resolution printed beside its counts | B2, J1 |
| G3 absent | G3 restored, plus a planted positive per channel per SUT | B2, M6 |
| ledger membership unstated | ▶ decided before any cell; results reported both ways | B3 |
| "a few episodes" | a design block: n, order, seeds, predictions, dated stop rules | B4 |
| no cost | cost per posture always measured; selection rule for a placement; selection and evaluation evidence disjoint | B5 |
| harness differences recorded | aligned: window, timeout rule, hold ≥ slowest channel cadence, metrics on fault cells | M2 |
| workload recorded | ▶ upstream mix as the base workload; "≥ 2 distinct request paths" gates the SUT | M8, D2 |
| LLM report is the evidence | a script is the evidence; the LLM report is checked claim by claim against it; a planted-invalid challenge set measures the gate | M4, J2 |
| same faults at the same locations | same kind × path role where the role exists; structurally empty cells marked; magnitudes dosed against measured demand | M1, M3 |
| host not mentioned | host per SUT recorded; cross-SUT statements qualitative | M5 |

## 1. System profile (kept; becomes generated)
Six layers per SUT, as in `research/system-profiles/`. Next: a schema and `build_profile.py` so every number is produced by a
command in the repo, not hand-written [PLAN part 1]. L0 records the host. The three findings made while profiling stay ledger
rows until fixed (OTel TARGET_PATH clip, OTel loadgenerator in every cell, TeaStore `selected` trace-id collapse).

## 1b. Projection map: what each service can emit in principle (user, 2026-10-02; new)
A map computed **before any run**, from source, configuration and the call graph only, beside the measured outcome. It says
what every service *could* show on each channel; the measured map says what it *did* show. Uses: planning a new SUT (Online
Boutique, the hold-out) before spending host time; making the gaps between possible and observed explicit, which is where
bias hides (a channel that is empty because nothing was collected reads like a channel that is empty because nothing happened).

| channel | projected per service, before any run | source of the projection |
|---|---|---|
| metrics | runtime metrics exist for **every** container: CPU, memory, IO, PSI (cgroup), whatever the app does | container runtime; always "possible" |
| logs | the levels the service can emit: info / warn / error / other (fatal, debug, framework lines) / undefined (unparsed, no level); which of them the configured level lets through | configured level per posture + log call sites per level in source |
| traces | instrumented or not per posture, and whether the driven workload's path reaches the service | posture catalogue + call graph + workload routes |
| ledger | one row per request at the entry, independent of any posture | harness |

Each cell of the map is then one of: **possible and observed**, **possible, not observed** (a gap to explain: no traffic,
level filtered, below threshold), **not possible** (structural: a db has no app traces), or **observed but not projected** (the
projection is wrong; fix the projection, not the data). The counts of the four states per SUT are the bias report.

**Service roles.** Yes: segment services into roles assigned by a written rule, not by judgement: entry (receives the
workload's requests), interior (called on a driven route), leaf (calls nothing further on the route), helper (support service
off the driven route: registry, flags, email), data store (db, cache), broker, telemetry (collector, backends). Roles come from
the compose image and the call graph of the base run. Cross-SUT statements are made per role, not per service name, which is
also what the fault catalogue's "path role" needs (§6).

Log call sites per level are counted with language-aware parsing (Go, Java, .NET, Node, Python, ...), not regexes frozen from
one codebase; until that parser exists, the log column uses the configured level plus the base run's observed levels, marked
as such.

## 2. One sensor representation, with its limits stated
- Events `(channel, service, token, t, value, meta)` for log, span, metric, ledger; per-SUT code only in parsers; existing
  parsers reused, existing three detectors kept only as test oracles [PLAN part 2].
- **Metadata on every event and sensor** (user, 2026-10-02), so later analysis can stratify without re-parsing: service role
  (§1b); channel; source (runtime / application / harness); log level (info / warn / error / other / undefined); collection
  resolution (sampling period or records per window); posture that collects it; on the driven path or not; projected state
  from §1b; by-construction flag once scored.
- Vocabulary and thresholds per **(SUT, posture)**, from ≥ 20 no-fault windows (τ = 0.05 means nothing with fewer). A token
  "disappears" only if the posture collects it. Catch = appear / disappear / move past median ± max(K·1.4826·MAD, floor).
  Windows may be non-overlapping sub-windows of no-fault cells, of the fault hold's length. Retained evidence is thin per
  posture (Hotel: 4 no-fault cells per posture per campaign), so every retro result states its n_eff; sub-windows of one cell
  are not independent, and that is said beside the number.
- **G3 on every channel** (spans and ledger included), reported as k/n_eff; n_eff = 0 is not reported.
- **Planted positive per channel per SUT** (one template line, one metric step, one span error, one failed request) before any
  fault cell: a channel that cannot fire on a plant is reported as blind, not as "no catch".
- Every count is printed beside its channel's resolution in that window (samples per window, records per window). Counts are
  normalised per offered request and per second. Cross-SUT comparison is qualitative unless a channel's resolution matches.

## 2b. Differentiated detectors, one selection rule (user, 2026-10-02; new)
A single global rule (K = 4 everywhere) is what let a threshold create the only ranking (H4), and robustness is the critique
reviewers raise most. Chen, Song, Xia, *Adaptively diagnosing system faults in microservice architecture*, FGCS 177 (2026)
108256 (AMFF), handle the same problem by differentiating: they select a detector per fault type from a candidate pool by
repeated random sampling (5 rounds), keep the best and a sub-optimal model together for diversity, separate fault-type
identification from root-cause localisation, and report stability across services; random sampling was stable where
cross-validation collapsed on sparse services (frontend F1 0.063). What transfers, at our level of strictness:
- **Differentiate per (channel × role), not per fault.** A small, declared candidate pool per channel: token appearance;
  count shift; median latency shift (MAD rule); rate change; for metrics a step/plateau test. The pool is fixed before any data.
- **One selection rule everywhere.** A detector is chosen per (channel × role × SUT) by repeated random resampling of no-fault
  windows plus the **planted positives** of §2: maximise detection of the plants subject to G3 (≤ 5 % no-fault firing). Never
  selected on the faults being evaluated (that is AMFF's few-shot labels, and circular here) [B5: selection and evaluation
  evidence disjoint].
- **Diversity as a check, not a vote**: the runner-up detector is run too; a catch that only one of the two makes is reported
  as detector-dependent, beside the K × floor grid of §3.
- **Stability as a reported quantity**: across resamples, how often the selected detector and each placement's verdict change;
  a ranking that flips across resamples is not reported as a ranking.
- **Separate tasks**: detection (did anything outside the target fire), isolability (§3), and localisation (does the earliest or
  strongest catch point at the target) are scored separately; localisation is out of scope for ASOCA.
What does not transfer: deep models and learned ensembles need far more windows than a campaign gives (n_eff of tens, not
thousands); the candidate pool stays at threshold and count tests.

## 3. Outcome measures (replaces recall/precision)
- **Detection** per (fault, placement): caught / not under G2 (outside the target) and G3, in the placement's **own** run
  (restriction of `full` cells is allowed only where a posture-leak check against the placement's own cells passes). Reported
  with the symptom kind (error, missing, latency, metric, log) and the shift/threshold ratio.
- **By-construction column**: MAP's taxonomy (BC-ledger-stopped-on-path, BC-caller-span, BC-own-stopped, BC-idle-cpu, ...)
  applied to every catch; detection is reported with and without by-construction catches.
- **Robustness grid**: every catch over K ∈ {3, 4, 5} × floor ∈ {0.5, 1, 2} ms; a ranking counts only if it holds across the
  grid (`otel-offpath/DECLARATION.md` erratum 1; H4).
- **Isolability**: for each pair of faults, whether some sensor in the placement separates them (a sensor that fires for one and
  not the other). Reported as a matrix with the ledger alone as the baseline row. A by-construction catch still separates, so
  this survives the flags that detection does not [D1: Krysander & Frisk 2008; EC², Golovin et al. 2010].
- **Cost** per posture: CPU-s, p50, emitted bytes, as in the existing ladders. A placement is evaluated as (detection,
  isolability, cost); cost is a set function, not a sum over sensors [H3; D3: Iyer & Bilmes 2013].
- ▶ **The ledger**: member of every placement or not. Both are reported; the user chooses which is primary.

## 4. Gates, generic and parameterised by the profile
| gate | rule |
|---|---|
| P0 provenance | namespace empty, images by digest, posture proof by observed behaviour (connection count / emitted bytes) |
| R1 ready | every measured service running; one 200 per declared route; ledger receiving rows; every channel the posture collects delivers ≥ 1 record after warm-up; on failure restart once, then stop and ask |
| R2 base state | fresh project + `down -v` per cell; at the end of a fault cell, success share and p50 in the last 60 s within G2's bound, written to the carry-over record |
| F1 fault truth | manifested, reverted, onset and hold bounded by the scheduled command, never a probe (F-ADH-085) |
| G1 traffic | **scheduled** request opportunities in the window ≥ 0.5 × rate × seconds (not completed starts: OTel's concurrency cap stalls starts during a pause) |
| G2 healthy before | successes before onset ≥ 0.5 × rate × seconds and failure share ≤ 5 % |
| G3 false-alarm rate | k/n_eff per sensor family, analysis side |
| G4 provenance | ledger, fault timing, validity present; offered == plan (no literals); ≥ 95 % of records inside the cell |
Campaign stop: stop and ask the user on the first invalid cell (replaces three different abort rules). Every existing per-SUT
gate is mapped keep / fold / drop in `PLAN_FABLE.md` part 4 (e.g. TeaStore's "queue non-empty at barrier" becomes a warning;
OTel's TARGET_PATH clip is dropped; the literals 1200 / 600 / 20 / 24 / 27 go). One shared module, vendored byte-identically into
the three harnesses, with a test that the copies match.

## 5. Fault qualification
- Per scenario: fresh base state, `full`, 1 no-fault + 3 fault cells; the deterministic pipeline runs first (gates, vectors,
  catches, carry-over). A cell failing G1 or G2 is listed, not scored.
- A pass condition is declared per scenario **before** its run: which channel, service and symptom kind the label predicts.
- The LLM (Fable subagent; prompt, model and output hashes recorded) writes a report in a fixed schema; every number carries a
  reference into the evidence pack, and `check_report.py` re-derives every claim. A report with a contradicted or unreferenced
  claim never reaches the user. "Did what its label says" with G2 failing is rejected by rule (the image_crash inversion).
- **The gate is itself tested**: a challenge set of planted-invalid scenarios (a no-op fault whose receipt says manifested; a
  scenario with no traffic in the window; a scenario that turns traffic on) must all be rejected; the false-admission rate on
  that set is reported [J2].
- The user types admit / revise / drop into an append-only `DECISION.md`; only admitted scenarios enter a campaign.
- First product, no host: retro-qualification of the seven existing scenarios from retained `full` cells [PLAN part 5].

## 6. Fault catalogue
- Same kind × path role where the role exists on that SUT; a role that does not exist is marked **structurally empty**, not `—`.
  Roles: entry, interior on every route, interior leaf, off-path/async, infrastructure, host (table in `PLAN_FABLE.md` part 6).
- Magnitudes dosed against measured demand (a fraction of the target's CPU, a multiple of the ledger's pre-window MAD), two
  magnitudes per degradation fault; hold ≥ the slowest collected channel's cadence on that SUT (OTel metrics: 60 s).
- Kinds: pause, delay (netem; sudo on srv5/srv6 `?`), throttle, error (OTel flagd flags need a flag-file overlay; TeaStore
  byteman not ported; Hotel has none). Industrial fault kinds from Zhou et al. (TSE 2021) as the source list.
- Scope limit, stated: fresh starts exclude faults that act through accumulated state (pool exhaustion, cache poisoning,
  carried-over wedges), which is where root-invisible faults are most likely.

## 7. Carry-over
Recorded per cell (order, previous scenario, recovery, drift of the pre-window from the first base vector), never scored.

## 8. Design block (new) [B4]
▶ episodes per (fault, posture) (proposal: 4); randomised posture order per block with a recorded seed; one prediction per
campaign, including the SUT-level one: "≥ 2 distinct request paths under the base workload, and greedy ≠ degree at some k"
(otherwise no placement problem exists on that SUT and its campaign is a cost-only run); a stop rule with a date per stage,
committed before the stage starts.

## 9. Workload [M8, D2]
▶ Proposal: each SUT drives its upstream project's default mix (Hotel wrk2 60/39/0.5/0.5; TeaStore LIMBO browse incl. cart,
profile, logout; OTel locust minus flood and browser traffic), open loop, one ledger row per request, rate at a declared fraction
of capacity measured in the base run, 600 s window, timeout = 2 × base p99 (floor 1 s), concurrency cap ≥ rate × timeout.
**Offline check first** (c2, 0.5 day, no host): count distinct request paths under the upstream mix from source and existing
traces; if it predicts one path, the workload change is not worth a harness commit for that SUT.

## 10. Related work the paper must position against [DIRECTIONS §0]
Borges et al., ICSA 2024 (Oxn), runs fault visibility and coverage per observability configuration **on the OTel demo**, our
SUT; it is not cited in rc11 although `docs/UPDATED_RESEARCH_SCOPE.md:261` calls it "materially closer than this matrix
admitted". Also missing: VAIF (SoCC 2021), Log20 (SOSP 2017), and for detector robustness AMFF (Chen, Song, Xia, FGCS 2026; §2b). What we add over Oxn: the untraced-ledger baseline, the
own-sensor exclusion, the by-construction taxonomy, the threshold robustness band, paired cost ladders, isolability.

## 11. Implementation and schedule
Build order and hours from `PLAN_FABLE.md` (~121 h in total; 70-80 h fit before 2026-10-15), revised for this draft:
| dates | work | host | gate |
|---|---|---|---|
| 10-02 | this draft; decisions below | — | ▶ decisions |
| 10-03 – 10-04 | representation (§2) + replay against MAP_TABLE as oracle; planted positives on retained evidence; profile schema | none | catch rule accepted from the replay delta table |
| 10-05 | gate module + keep/fold/drop record; carry-over record | none | keep/fold/drop approved |
| 10-06 – 10-07 | detection, isolability, robustness grid on retained evidence (Hotel lmt2/sel1/int1/rep1, TeaStore #16, OTel v3); qualification pipeline + challenge set; retro-qualify 7 scenarios; workload check c2 | none | 7 decisions; workload decision |
| 10-08 – 10-10 | only if the workload and catalogue decisions are made: harness commits (gates + fault controller + workload), DRY_RUN per host | dry runs | each commit and dry run |
| 10-11 – 10-13 | base runs, then one new scenario per SUT qualified | ~1-1.5 h per SUT | each run started by the user |
| 10-14 | paper, Fable whole-paper review | — | text |
Cut line: through 10-07 the paper is the protocol, the replayed representation, isolability over the ledger baseline with its
robustness band, and seven retro-qualified scenarios, all on retained evidence (scope: method for the protocol, instance for
every number). Host work adds base runs and new qualified scenarios; no posture campaign fits.

## Decisions (user, 2026-10-02, second round)
1. **Ledger**: reported both ways. **Primary: the ledger is a member of every placement.** Reason (recommended by Claude,
   accepted): it is always present at the entry and costs no instrumentation, so the research question becomes what a placement
   adds beyond it (marginal detection and isolability over the ledger-only baseline); the without-ledger view is the secondary
   table, so the 14-of-16 vs 3-of-16 contrast (H1) stays visible.
2. **Primary outcome**: detection + isolability over the ledger baseline, unless a better way to establish the prerequisite
   without fault reconstruction turns up (open).
3. **Workload**: the upstream mix, accepted in principle; validating the paths and defining what a significant shift is for a
   sensor to count as valid will take longer, easier for logs than metrics (`research/sensor-validity/`, running).
4. **Scope**: plan base runs and new scenarios; research comes before the paper (the current paper is not strong enough and the
   work feeds the thesis). Working assumption: about one full day of thesis work per day.
5. **Defaults** (episodes, K, τ, windows, challenge set): set after the scope mapping (`research/scope-20261002/`, running).
6. **Load generator**: one generator for all SUTs: Locust for API calls, Playwright for UI journeys
   (`research/load-generator/`, running).
7. **Project map** (§1b, four states): a research planning artefact, not for the paper (`research/project-map/`, running).
8. **Detector pool** (§2b): replaceable whenever a better alternative is found.

## Decisions (user, 2026-10-02, third round)
9. **Ledger on the same grid**: the ledger is scored on the same K × floor grid as the sensors (under the sensors' 4×1.4826×MAD
   rule it misses the two int1 delay rows: 16/16 → 4/16, 15/16 → 5/16). Less open to critique; accepted.
10. **Catalogue rebalanced (amends §5/§6/§11)**: one on-path outage per SUT stays as a positive control; the freed cells go to
    faults where only a sensor can show the effect: off-path/async, an error masked by its caller, below the ledger's threshold
    (two magnitudes around it), and pairs of faults the ledger cannot tell apart. Plus a planted positive only a sensor can see.
11. **Redundancy is expected, not ruled out**: a fault may show in several sensors (callers' spans, several services' CPU). Per
    fault the analysis lists every minimal sensor set that catches it, and per fault pair every minimal set that separates them;
    "only a sensor can see" means the ledger misses and at least one set catches. Several minimal sets is what makes placement a
    choice (cheapest cover of all faults); by-construction catches (BC flags) and the target's own sensors (G2) are reported apart.
12. **Project map: what is tracked** (`research/project-map/DECIDABILITY.md`, `decidability.png`): undecided cells split by fix
    type. Rule: (a) **retain** everything the runtime already produces (all container stdout, the full trace store, collector
    output) and **query** it completely: no SUT change, so it is done by default once its capture overhead is measured;
    (b) **sample** every container with the existing collectors (harness change, host overhead measured); (c) **instrument** only
    as a declared posture, because it changes the SUT and its cost is part of the result. "Offline" means the analysis runs on
    retained evidence after the run with no further access to the system; collecting more on the server keeps it offline. What
    breaks it is a live query at the end of a cell (Hotel's Jaeger query for the frontend only is why 83 trace cells are `?`).
    Every change is one row in an append-only change ledger: change, fix type, repo and commit, cells resolved before/after.
13. **Load generator runtime**: not the hosts' Python 3.9. The 3.9 constraint binds harness code run as `python3 -I` on the
    host, not the generator. The generator ships as a container image pinned by digest, built from a `uv.lock` (Python 3.13,
    Locust, Playwright with its browsers), on reserved cores; the open-loop scheduler and the shared ledger schema of
    `research/load-generator/DESIGN.md` stay. Playwright is usable on all three SUTs, TeaStore included. Candidate for the UI
    layer: chaosbringer (github.com/mizchi/chaosbringer: MIT, TypeScript on Playwright, browser-side network/page/JS-runtime
    faults, seeded reproductions, W3C traceparent correlation; 47 stars, 304 commits, so young). Its UI exploration (`scan`)
    helps discover UI paths; its faults act in the browser, so server-side sensors see them only as missing or altered requests
    (a client/edge row in the catalogue, not a substitute for server faults).

## Decisions (user, 2026-10-02, round 5): the reframing
14. **Spatio-temporal objective, CELF kept.** The objective so far is request-driven: a fault exists for f(S) only when a
    request flows through it, so the root (frontend/ledger), where every flow ends, wins whenever the driven route is busy.
    That is the simplification. The objective goes back to the outbreak-detection form CELF was built for (Leskovec et al.,
    *Cost-effective outbreak detection in networks*, KDD 2007; the water-network sensor-placement setting): per fault,
    (a) **detected or not**, (b) **time to detection**, (c) **impact before detection** (e.g. failed or slowed requests
    before the first catch). **Traffic per route is a parameter, not a constant**: the root's chance of catching a fault
    within t depends on the request rate on the faulted path; a sensor reading the service's own state does not. Placement
    therefore matters where traffic is thin: rare routes, low load, background and async work. CELF stays the optimiser;
    modifications only when an improvement or generalisation is found. Further dimensions (e.g. multi-label or partial
    detection) are researched before any is adopted.
    First step, offline: time from fault onset to the first catch, ledger vs every sensor, on retained evidence
    (`research/detection-time/`), plus a literature search for objective dimensions added since 2007
    (`research/literature-20261002/`).
15. **Primary dimension and the gap (user, 2026-10-02).** Primary outcome: **time to detection, misses charged at the window
    end, averaged over episodes**. Collected as optional benchmark columns in every run: bad requests before detection,
    detection probability over the K × floor grid, labels per catch, by-construction flags. The gap the work addresses:
    CELF's guarantee covers the submodular surrogate (detection probability), not detection time, which is not submodular
    (Heavey et al., AAAI 2022, via `research/literature-20261002/DIMENSIONS.md`), and no paper was found that uses time to
    detection as a placement objective for microservice telemetry. First test: a traffic sweep on Hotel
    (`research/traffic-sweep/DECLARATION_DRAFT.md`, not frozen), hands-on on 2026-10-03.

## Decisions (user, 2026-10-03, round 6): traffic-sweep pilot
Pilot frozen in `research/traffic-sweep/DECLARATION.md` (a795fc9), budget `research/traffic-sweep/BUDGET.md` (6a06818).
16. **All pilot values approved** as recommended in `research/READING_20261003.md` §3 (rates, timing, stratified onset,
    episodes, faults, posture, netem via `sudo nsenter` on srv4, sampling, P1-P4 wording, analysis definitions).
17. **Budget**: 3 days, kill 2026-10-06 12:00Z, then readjust.
18. **Probe windows** excluded from every sensor's scoring; **lead cell** search-pause r10 first in the 64.
19. **Recovery inside the cell**: the 60 s hold and the resulting 40-60 s post-hold window are accepted; R2.recovery is `—`
    in fault cells (declared limit). The fault adapter's "route answers 200 again" is only part of recovery: not every
    failure shows as a status code. A **post-fault steady-state check** (latency and error share back to the pre-fault
    level, e.g. a 30 s window) is added at a later step, not in this pilot.
20. **Base state**: every cell starts from a fresh deployment (`down -v`), as in recent RCA benchmarks that redeploy after
    each injection. **Planned ablation** (later): carry-over on purpose (no redeploy, randomised predecessor, residual
    pollution from the previous fault) to measure its effect on detection and on multi-failure cases, and how to mitigate
    it. Feeds §7 (carry-over), which so far only records it.
21. **G2 stays strict** for the pilot (one pre-onset failure at 0.05/s fails the cell and stops the campaign for a decision).
22. **Campaign starts**: Claude may launch from a frozen declaration and a passing DRY_RUN; every campaign is logged at a
    high level to wandb (`tools/wandb_campaign.py`). Recorded in `CLAUDE.md`.
23. **Replication choices (user, 2026-10-03)**: every proposed TeaStore and OTel sweep choice accepted
    (`research/traffic-sweep/DECLARATION_TEASTORE_DRAFT.md`, `DECLARATION_OTEL_DRAFT.md`). **Q3**: TeaStore sweep cells get a
    drain allowance of client timeout + 2 s = 17 s after readiness (failures recorded, not invalidating). **M1**: OTel sweep
    cells block only if < 99 % of successful pre/post requests carry the complete trace; the share is always recorded.
24. **Thesis note** requested: why the objective diverted and returned to Leskovec et al. 2007
    (`papers/notes/THESIS_DESIGN_HISTORY.md`, in progress).
25. **Shared trace-completeness rule, all three sweeps (user, 2026-10-03 ~13:00Z)**, after Hotel relaunch 2 (cell 15, 10/1803
    traces lacked search→rate under net-delay r10), OTel attempt 1 (cell 8, 20/21 complete after a frontend pause at 0.2/s)
    and TeaStore attempt 1 (cell 11, 498 native-parent correlation errors outside the exposure window under the persistence
    throttle) stopped on all-or-nothing completeness rules. (i) Requests starting during the fault or in the drain window
    after recovery (client timeout + 2 s, as TeaStore's Q3) may have incomplete traces: recorded as part of the fault's
    effect, never blocking. (ii) Everywhere else (pre-onset, after the drain window, every no-fault cell): block only if more
    than max(1, 1 % of successful requests) traces are incomplete. Every incomplete trace is counted and reported per cell.
    **Relaunches approved**: Hotel all 64 cells (a 3rd relaunch, beyond `BUDGET.md` rule 4, by the user's explicit OK) and
    OTel all 12 (relaunch 1 of 2); TeaStore all 12 (relaunch 1 of 2) under the same rule since it stopped in the same class.

## Round 7 (user, 2026-10-03 ~19:45Z, after the Hotel readout review `research/traffic-sweep/readout-hotel-r3/REVIEW.md`)
26. **(k) Actuator readback is not a detection.**
    - The throttled container's own CPU pressure (PSI) is a high-value metric, not a detection. It is classed with the
      paused target's idle CPU as by-construction: the fault read back, now for degradation faults too. It is excluded
      from P4 wins and reported beside them.
    - User's direction: the missing dimension is probabilistic. A filter (e.g. Kalman / state-space) would see an
      activation and assign it a variance or probability, instead of a binary catch. This links to D3 (probabilistic
      detection), which is still not computed. It is a research item.
27. **(l) Relative floor, for now.** The latency floor becomes relative to the baseline rather than a fixed 1 ms. The
    value is an engineering default, recorded with its sources in the methodology hardening note.
28. **(m, n) Use the field's standard rather than inventing one.** This covers observation time (event time vs
    availability) and fault-onset stamping / in-flight requests. Literature research was commissioned.
29. **Focus: harden the methodology before going deeper.** The analysis defaults (`SWEEP_ANALYSIS.md` "Engineering
    defaults") are audited for validity first. The placement step (the detection graph and CELF) comes after.
30. **The high-level challenge behind k-n (user, 2026-10-03 ~20:00Z, verbatim):** "Challenging questions when optimising
    opentelemetry: baseline performance; filter out noise from default system load / activities; sensors have
    sensitivity different per microservice system; can we have generic parameters that get tuned based on our baseline
    run and follow up (e.g. guided + chaos test) to see initial outliers and correlation; how does this account for non
    survivorship bias for parts that are missing (-inf probability that are mapped in the optimal full graph vs what is
    observed)".
    - Research has been commissioned: `research/protocol/LIT_TIME_SEMANTICS.md`, `LIT_DETECTION_RULES.md`,
      `LIT_MISSING_SENSORS.md`. Recent papers (2023-2026) are weighted, with DOIs for Zotero.
    - The hardening decisions are then validated with the judge as a single helper (gpt-6.1-sol), for methodological
      correctness and generalisation across Hotel, TeaStore and OTel.

## Round 8 (user, 2026-10-04 ~08:30Z, on `research/protocol/METHODOLOGY_HARDENING.md`)
31. **H1 baseline pooled** across same-rate quiet cells (overrides the declaration's "not adopted"). K = 4 is kept as the
    reference.
32. **Floor:** max(statistical threshold, 10 % of the baseline median), with a 5 % sensitivity arm.
33. **H2 false alarms:** as recommended. Report the rate per hour on held-out quiet time and compare detectors at a
    common operating point. ≤ 15/h is the most the current quiet time certifies.
34. **H8 / m:** event time primary; pipeline (export) delay reported separately per sensor type.
35. **Tie margin:** an initial margin is set, derived from measured timing uncertainty (H3 b), not chosen freely.
36. **Faults / onset:** agreed (onset interval, H4). The user notes that robustness to sensor loss ("dropout") breaks
    submodularity, and wants the thesis to **compare the two** (expected objective vs a robust/dropout variant; the
    repo's dimension D4 max-min).
37. **Provenance rule (user):** every hyperparameter and sensitivity setting is traced to its origin and tracked:
    decision, literature source, or measurement with its command. Nothing in the analysis is "random".
38. **Probabilistic detection as part of the initial method (user):** the prior for an unseen sensor starts at the miss
    penalty and is reduced by evidence from neighbouring edges of the graph. Rationale: generating our own data
    (controlled injection, known onset, paired episodes) is much stronger than working on prerendered traces.
39. **Expected vocabulary (user):** log/span vocabulary recorded over the default (no-fault) run and over fault and chaos
    runs.
40. **In-flight requests:** the user suggested tagging them with a small embedding/LLM. Open; see the reply of the same
    date.
41. **User sketch** (`journey_tracking_pathways`, 2026-10-04): services × faults × user journeys. Observations per
    journey go to logs/traces per service (keywords, spikes) and to metrics, then against a baseline, then encoded into
    a tensor. Optimisation: submodular (properties cleanly mapped) vs a softmax / gradient-descent relaxation.

## Round 9 (user, 2026-10-04 ~09:00Z)
42. **All recommendations agreed:** H3 (P4 redefined), H5 (exposure recorded, objective unchanged), H6 (placement
    bounds as a robustness row), H7 (common operating point; K and scales fitted per system from fault-free data;
    guided/chaos runs as calibration on Hotel/TeaStore only), H10 (later runs: no readiness probe during the fault,
    stamp the freeze), and **decision j**: TeaStore relaunch 2 with the narrowed JVM-frame scanner (0588a41); relaunch 1's
    10 valid cells are not pooled.
43. **Clocks:** event time is primary for now. Availability is optional, from measured collector receive time only, and
    kept available for offline runs.
44. **H9** (the probabilistic / occupancy model) is tracked outside, as next steps for the paper and thesis. Decision
    38's graph-neighbour prior belongs to it.
45. **H11 / P3:** restricted to signals that are traffic-independent by mechanism.
46. **Additions agreed:**
    - (1) a long no-fault calibration run per system, to certify a lower false-alarm rate (≈ 3/r hours for r per hour);
    - (2) repeat episodes on TeaStore and OTel, for cross-system claims;
    - (3) close the loop: run the chosen placement as a real posture and compare predicted vs measured detection.
    - (4) Later, in the writing todos: a systematic search before any "no paper reports detection delay" claim.
47. **Later, high value:** sensitivity curves for the hyperparameters (true/false positive trade-off across K, floor and
    operating point; for detection-time work the delay-vs-false-alarm-rate curve).

## Round 10 (user, 2026-10-04 ~09:30Z, on `research/traffic-sweep/NEXT_CAMPAIGNS_PROPOSAL.md`)
48. **A: quiet calibration run at ≤ 6/h.** 40 no-fault cells per system (10 per rate × 4 rates, 30 min of quiet time per
    rate), same cell shape as the sweep, on all three systems.
49. **B: 3 more blocks on TeaStore and OTel** (4 in total, like Hotel), after the H10/H4 harness change.
50. **Fault doses** (CPU throttle to 0.1 cores, 100 ms netem delay) are recorded as inherited from Hotel's earlier fault
    catalogue, as a fixed factor. Dose-response is a writing todo for later.

## Round 11 (user, 2026-10-04 ~10:30Z, on the v2 review `research/traffic-sweep/readout-hotel-r3-v2-fix1/REVIEW.md`)
51. **M1 same silence:** the ledger's `absent` catch is tied to the first completion that ends the silence. A sensor
    catch on that request is same-request (no win), consistent with H3(c).
52. **M2 scale not estimable (MAD = 0):** such sensors are `—`, with no detection claim. A quantile-based threshold
    (empirical upper quantile + resolution) is a later sensitivity row (writing todo W2).
53. **M4 K unit:** K is fitted per channel family within each system as the primary; the system-wide K is reported
    beside it.
54. **M5 P1 model:** an ambiguity window of [command, Docker pause event + δ], with δ = the pre-onset median of
    (request end − paused-service span end). The tolerance comes from measured timing terms. Both are declared now,
    before any TeaStore or OTel cell is read.
55. **Engineering (coordinator):**
    - B1: P4 = `—` when a family is not at the operating point.
    - M3: false alarms are calibrated on the scored sensor set (path-filtered, by-construction excluded).
    - The review's minors.
    - The K grid is **not** extended after the fact (T would certify at K = 200); the quiet runs add calibration time
      instead.

## Round 12 (user, 2026-10-04 ~10:45Z, on `research/traffic-sweep/STOP_QUIET_OTEL_A1.md`)
56. **OTel quiet cells: record trace loss, don't block.** Incomplete traces in quiet (no-fault) cells are counted per
    window and service and reported as telemetry loss, never blocking. The other gates stay strict (G1/G2/G4,
    container health). Reason: a lost batch of one service's spans is what makes an `absent` rule fire on a healthy
    system, so it is calibration data. Relaunch 1 of 2, all 40 cells. Attempt 1's 7 valid cells are kept, not pooled.
57. **Mirror of decision 51 (user, 2026-10-04 ~11:00Z):** a sensor's `absent` catch is tied to the token of the span
    that ends its silence. If that is the same request as the ledger's catching row, it is same-request (no win). This
    goes in as analysis v2.2, frozen before any TeaStore or OTel cell is read. v2.1 (22e0d12) stays as the record of
    the Hotel re-analysis; P1's revised model (decision 54) is first tested cleanly on TeaStore and OTel.

## Round 13 (user, 2026-10-04 ~14:00Z, on the v2.2 review before any TeaStore or OTel cell was read)
Source: read-only Fable `adversarial-review` of v2.2 (421a6d2, freeze 5c98726), with an independent stdlib recompute on
Hotel. For an `absent`-vs-`absent` pair, the two catches fire at (last observation before the silence) + (the channel's
fitted gap), so the silence-**starting** records set the lead, not the ending ones. Hotel net-delay 10/s: in 4/4
episodes the sensor's and the ledger's starting records are the same request. The leads are 5.0-7.3 ms = that request's
response path (3.1-5.1 ms) + the gap-threshold difference (1.8-2.2 ms). Decision 57 caught 3 of the 4 only because
their ending requests also coincided. Judge, single helper (gpt-6.1-sol, `panel_n: 1`), `eval_51f6e70d873b4479b7047deea0f69342`:
5/5 criteria passed for option B (instance scope of the finding: Hotel; the rule is declared for all three systems).
58. **Silence-vs-silence pairs, either end:** an `absent`-vs-`absent` pair is same-request (no win) if the
    silence-starting records **or** the silence-ending records share a request token. Decision 57 stays as it is; the
    start test is added. Mixed pairs keep decision 57. Each such lead is reported with its decomposition (response path
    + gap difference). A missing token is "unclassifiable" (no win, counted), as in decision 57. Goes in as analysis
    v2.3, frozen and reviewed before any TeaStore or OTel cell is read; the Hotel re-run is exploratory.
59. **P2 on TeaStore uses TeaStore's own client timeout, 15 s** (`candidate_sweep.py:82`), as OTel's declaration states
    explicitly. TeaStore's declaration adopts Hotel's P2 by reference, and Hotel's 1 s is Hotel's own timeout. Recorded
    as a reading of the declaration, not a change of its model.

## Round 14 (user, 2026-10-04 ~16:00Z, on the v2.3 follow-up review, before any TeaStore or OTel cell was read)
Source: the same read-only Fable reviewer, finding G2 on v2.3 (af6f223, freeze 830f309): an `absent`-vs-`absent` pair
whose starting and ending records are different requests keeps lead = start term + gap term. The gap term
(g_ledger − g_sensor; 1.8-2.2 ms on ~235 ms thresholds in Hotel) is a difference between two fitted thresholds, and its
estimation uncertainty is not in the tie margin. Judge, single helper (gpt-6.1-sol, `panel_n: 1`),
`eval_4b3103b0d8c04a359320c4163880aef2`: 4/4 criteria passed for option A.
60. **Silence-vs-silence pairs with different requests: the start term only.** Such a pair is a win only if the start
    term (ledger's last completion before its silence − sensor's last observation before its silence) exceeds the tie
    margin. The gap term never counts toward a lead; it stays printed in the decomposition. Decisions 57 and 58 still
    apply first (same request at either end = no win; missing token = unclassifiable). Goes in as analysis v2.4, frozen
    and reviewed before any TeaStore or OTel cell is read; the Hotel re-run is exploratory.

## Round 15 (user, 2026-10-09 ~11:00Z, "yes to v3 design", on `research/protocol/ANALYSIS_V3_DESIGN.md`)
Source: the v2.4 synthesis `research/traffic-sweep/SYNTHESIS_V2_4.md` (reviewed). Adopted as analysis v3, frozen and
reviewed before campaign B is read. All existing cells of the three systems are exploratory under v3. An independent
review of the design was running when it was adopted; any material change it requires returns to the user.
61. **D-a Calibration unit:** one threshold per (sensor, rule), the smallest grid value with zero held-out alarms on the
    no-fault cells of the rate (leave-one-cell-out); bound 3/T per hour. Replaces decision 53 (K per family) and the
    15/h target of decision 33 for v3; a sensor's detector is the OR of its calibrated rules.
62. **D-b Grids:** level rules use the K grid (≤ 100, decision 55), then a two-sided range fallback (fit cells' min/max
    widened by one resolution step); `absent` uses g = m × the largest inter-arrival gap in the fit cells including the
    censored silences at window start and end, m ∈ {1, 1.5, 2, 3, 5}; `appear` unchanged, calibrated by the same
    criterion. Uncalibratable (sensor, rule) pairs are dropped and listed; a sensor with none is "not placeable at this
    quiet time".
63. **D-c** The ledger's `failed` rule is exempt (positive control of P1/P2); its no-fault count is reported. E's
    `spike` and `absent` are calibrated like any sensor.
64. **D-d** Placement-level false alarms are reported as the measured held-out union of the chosen sensors with its exact
    bound; no FAR constraint inside the objective.
65. **D-e** P4 compares the ledger with the placeable sensors and names dropped rules and non-placeable sensors;
    replaces B1 (decision 55). `—` only where the ledger's compared rule is uncalibrated or episodes are fewer than
    declared. Campaign B's no-fault cells serve as the out-of-sample check of the calibrated detectors; one sensitivity
    row at "≤ 1 held-out alarm".

## Round 16 (user, 2026-10-09, on `research/traffic-sweep/OTEL_LOST_BATCH_DIAGNOSIS.md`)
Source: read-only diagnosis of quiet attempt 1's r10-b02-04 (Sonnet subagent, not yet independently reviewed): the 50
productcatalogservice spans were exported (pcap frames 12583-12588) and forwarded by the collector (12599/12600); only
their debug-exporter record in otelcol.log is missing, consistent with the collector's default log sampler, which the
harness never disables (`materialize.py:650-653` at 6a47d0b sets no `service.telemetry.logs.sampling`).
66. **Campaign B's OTel collector disables log sampling** (`service.telemetry.logs.sampling.enabled: false`). It changes
    the measurement carrier only, not the SUT. Existing OTel sweep and quiet cells keep the recorded caveat that
    otelcol.log is a lossy carrier: a missing span there is not evidence that the system lost it.

## Round 17 (user, 2026-10-09, "Adopt, plus more quiet time", on `ANALYSIS_V3_DESIGN.md` § Review and amendment v3.1)
67. **Analysis v3.1 adopted:** the six amendments in that section (honest nested-LOCO false-alarm counts for every
    rule, sensor and placement, never the naive 0; the honest per-sensor rate as CELF cost; B's no-fault cells as a
    fresh check with its ≤ 20/h limit printed; `inert` status and per-rule placeability with `appear`-only sensors
    listed; range fallback labelled discrete-only, up-only for latency channels, no "≤ 1 alarm" row for it; decision 52
    kept, K = 100 flagged at grid edge, class-independent calibration; P4 with a calibrated and an optimistic arm,
    `failed` exempt and labelled). Amends decisions 61-65.
68. **More quiet time:** a second quiet calibration run (A2, 40 no-fault cells per system, same cell shape as A) on each
    system, pooled with A for calibration. Hotel now on fb14srv4; TeaStore and OTel after their campaign B is terminal.
    Budget `research/traffic-sweep/BUDGET_QUIET_A2.md`.

## Round 18 (user, 2026-10-09, on the campaign B harness drafts)
69. **H4 freeze record: record, don't block.** In campaign B (TeaStore and OTel), a failed or contradictory Docker
    events query or freeze stamp leaves the cell valid; its H4 record is marked missing with the reason, the onset
    interval falls back to [command issued, command returned] as in the sweep, and the failures are counted per cell.
    H10 applies to both fault types (no route readiness probe from onset to the end of the hold).

## Round 19 (user, 2026-10-09, on the v3.1 review finding F4)
70. **The ledger in P4 is the OR of its calibrated rules** (`failed` exempt), symmetric with sensors; a dropped ledger
    rule is listed, not a reason for `—`. Registry `V3_P4_LEDGER_READING` = (b) calibrated-ledger.

## Round 20 (user, 2026-10-09, on the v3.1 re-review note R1)
71. **CELF cost of a sensor with no held-out evidence** (cost `—` in v3.1 after A2 is pooled): use the zero-alarm upper
    bound 3/T of its rate as a conservative cost, labelled "bound, no evidence"; such sensors stay placeable but are never
    free. Applies to the placement step; the frozen v3.1 readouts are unchanged.

## Round 21 (user, 2026-10-10, on `research/protocol/PLACEMENT_V3_DESIGN.md` rev. 2, 9bd881e, after an independent Fable adversarial review of eec5f0d)
The recommended option was chosen on every item. D-p7 was decided after its counts were seen (OTel ledger clean catches
0/32 episodes, Hotel 19/48); the design says so. Scope of the placement step: CELF over the frozen v3.1 readouts.
72. **D-p7 By-construction catches:** count for the ledger E only (its path stopping is the user-visible symptom); a
    sensor's by-construction catch is a miss. Arms beside: BC = miss for all; BC counts for all.
73. **D-p3 Costs:** every sensor at its honest 95 % upper bound (`honestUpperPerHour`); a sensor with no held-out evidence
    at the rate's largest evidenced upper bound, so evidence never makes a sensor dearer and no sensor is free. Amends
    decisions 67 and 71 for the placement step; decisions 67/71 as written are reported beside as the literal arm.
74. **D-p4 OTel's role:** OTel becomes a training system for the placement step (its primary readout, 0a8517a, was read in
    full on 2026-10-10, including per-sensor detection times). The clean placement test is a campaign run after this
    design is frozen (or Online Boutique; no cells yet).
75. **D-p1** One placement per traffic rate.
76. **D-p2** Budget: a Pareto sweep over the cost budget, with 6/h named as the false-alarm budget (number from decision
    48, new role). A knapsack budget is a constraint, not a term in the objective, so decision 64 holds.
77. **D-p5** Impact before detection = failed requests only.
78. **D-p6** Comparators: declared `selected` / `none` sensor sets per SUT from the posture definitions, labelled as
    restriction estimates from `full` cells, beside the ledger alone and `full`.
79. **D-p8** Sensors on the fault target (own) are out of the primary objective; the `X:own` view is secondary.
80. **D-p9** Scoring placements by restriction of `full` cells is a declared deviation from protocol §3 (:102); decision
    46.3's live run of the chosen placement is the later check.
A budget and stop rule for the placement step is committed alone before any placement is computed.

## Round 22 (user, 2026-10-10 ~17:30Z, on the ablation and test-run proposals)
81. **Ablations of the placement step, declared before any placement is computed:** (a) **modality**: the same CELF
    objective, costs and budget grid on ground sets restricted to traces (T) only, T + logs (L), and every collected
    family (T, L, M, S where collected); the ledger E as in decision 72 in every arm. (b) **quiet-time curve**: the frozen
    v3.1 recalibrated on the sweep's no-fault cells plus the first 10 quiet cells per rate (quiet run A, blocks 1-10 in
    plan order... per rate, A's first half), plus quiet A only, plus A + A2 (decision 68), each a new readout, then the
    same placement; reported: placeable sensors, costs, chosen sets, mean time to detection.
82. **Clean placement test runs (D-p4), all three:** campaign C on TeaStore (fb14srv5) and OTel (fb14srv6), the same
    36-cell shape as campaign B with new blocks, and Online Boutique as the held-out system. All run after the placement
    design is frozen by digest; their fault cells are scored only by the frozen placement.
- Correction to 81(b) (coordinator, same day; the sentence above is garbled): quiet run A has 10 cells per rate (10 blocks x
  4 rates), so the curve's steps are the sweep's no-fault cells plus (i) quiet A blocks 1-5 (5 cells per rate), (ii) all of
  quiet A (10 per rate), (iii) A + A2 (Hotel and OTel 20 per rate; TeaStore 10 + the stopped attempt's valid cells + relaunch
  1's 10, as pooled by decision 68 and V3_POOL_KEY_RULE). Subsets are selected by block number from the plan, never by outcome.

## Round 23 (user, 2026-10-10 ~19:00Z, on `research/traffic-sweep/OB_READINESS_20261010.md`, 48829ff)
83. **Online Boutique stops under BUDGET_C (stop rule 1) and stays an unspent held-out system.** Not launch-ready by
    2026-10-11 18:00Z (estimate 25-49 h against ~24 h; srv4 needs host mutations M1/M5; the frozen v2.4/v3.1 reader has no
    Online Boutique support). Campaign C on TeaStore and OTel is the clean placement test (decisions 74, 82).

## Round 24 (user, 2026-10-11, on the Fable review of the placement code ed25107)
84. **Decision 79 reading:** an on-target ("own") sensor is excluded per fault class (the fires where its service is the
    class's target), the v2.4 `X` / `X:own` column semantics; it stays a candidate for the other classes.
85. **Held-out headline at the named budgets only** (0 = ledger alone, 3/T_r, 6/h, unlimited); rows at data-derived budget
    knots are labelled in-sample-indexed and kept as context (`pointKind`).
86. **The decision-35 tie-margin arm is deferred** (future work; the per-episode margin is not in the readout JSON).
87. **Cardinality view produced as a secondary:** k = 1..19 (the largest count of sensors with a clean counted fire at any
    rate on the training readouts), its placement-level false alarms reported.
Engineering defaults recorded with the fixes (346482a): tolerant tie comparison (relative 1e-9, ties to the smallest id);
every modality arm of a rate on the union of all arms' budget knots (decision 81 "same grid"); top-k without zero-gain padding.

## Round 25 (user, 2026-10-11, on `research/protocol/TEST_SCORING_C_DRAFT.md`, bffb3a0; before any campaign C cell is read)
88. **Campaign C test procedure adopted as drafted:** frozen v3.1 on each SUT's training campaigns plus a fault-only view
    of C, C's full campaign as `--validation` (second fresh false-alarm check, never pooled); a new scorer
    (`research/placement/score_test_v3.py`, reusing the frozen celf_v3 objective) computes each frozen set's D on C's
    episodes only; synthetic tests, a planted defect, independent review and a digest freeze before any C cell is read;
    fresh false alarms of the frozen sets are `—` until a validated path exists.
89. **Pass rule (sign rule):** at OTel r0.2 the frozen 6/h set (`span:frontend:GET`) passes if g_C = D_C(ledger alone) -
    D_C(S_6/h) > 0 and it improves at least 2 of C's 3 CPU-throttle episodes; elsewhere g_C and per-episode values are
    reported without a verdict.

## Round 26 (user, 2026-10-11, on the Fable review of the test scorer 2f037cb; before any campaign C cell is read)
90. **Decision 89 with no detector:** if a member of the frozen OTel r0.2 6/h set is absent from C's readout ground set
    at that rate (not placeable under the C readout's calibration, or missing from its sensor table), the verdict is `—`
    (not testable as declared), with the absence reported; never FAIL.
91. **Decision 89 with too few episodes:** fewer than 3 valid CPU-throttle episodes at OTel r0.2 gives `—`, with the count
    reported.

## Round 27 (user, 2026-10-12, before any campaign C cell is read)
92. **Campaign C epochs admitted to the frozen reader.** The frozen v3.1 reader refused both C campaigns at the
    schema check (`UnknownSchema`: studyEpoch `otel-repeat-episodes-c-v1` / `teastore-traffic-sweep-c-v1` not in the
    admitted list), so decision 88 could not run. Neither C declaration named the reader change (DECLARATION_C_OTEL.md
    :159 "no guard asked for one"). Amendment: `STUDY_EPOCHS_B` in `research/protocol/parameters_v3.json` admits the two
    C epochs as campaign-B-shaped, as both declarations state; `V3_B_RECORD_KEYS` is unchanged, so a C record of
    another shape still stops the run. `sweep_analysis_v3.py` is unchanged (scriptSha256 still the frozen v3.1 pin the
    scorer checks); the readout's `parametersV3Sha256` changes. C cells carry the `B` harness tag; the scorer selects
    C by campaign index, never by tag (score_test_v3.py:20). Outcome-blind: made before any C readout exists. Also
    (engineering default): C's fault-only views are real copies (`tmp/c-fault-copy/{otel,teastore}`, every file checked
    against the host sha256 manifest), as B's were; the symlink views failed the reader's path check (`relative_to`).

## Round 28 (user, 2026-10-12, after campaign C's FAIL and the throttle diagnosis aa461f8)
93. **C's FAIL stands; a fresh test follows.** Analysis v3.2 plus a fresh campaign D (`BUDGET_D.md`, 607a712). C is
    never re-scored or relabelled; v3.2 on C's cells would be exploratory only.
94. **Load, not a new fault.** OTel's 0.1-core productcatalog throttle never binds at 0.05-10 req/s (~1.07 ms CPU per
    request). Traffic is raised instead of writing a new fault ("higher user load would catch it"): a pilot at
    **50 and 100 req/s** (100/200 was replaced because the single-process Node frontend uses ~10 ms CPU per request and
    saturates near 100 req/s), the same throttle, the SUT memory limits as in C (productcatalog 20 MiB, frontend
    250 MiB; an OOM kill is preserved as blocked evidence). A manifestation criterion is declared before launch
    (amendment 1, 86d9172).
95. **D's shape:** training and test blocks in one declaration at the rate(s) where the pilot manifests (r10 as an
    anchor), the split fixed before launch; the placement is solved on the training blocks and frozen with the pass
    rule before any test block is read.

## Round 29 (user, 2026-10-12, after the load pilot e131856: throttle does not manifest at 50 or 100 req/s)
96. **Off-path faults, OTel only, campaign E** (`BUDGET_E.md`, ec4b9fa): restores direction (c) of 2026-10-01 (fraud-pause
    built, never run), dropped in the 2026-10-02 reset. Reason (user): with only request-path faults the ledger detects
    first and the optimal configuration is the ledger alone; off-path faults make a placement problem exist.
97. **Workload:** the upstream Locust task mix as an open loop with a request ledger (protocol §9), so checkout reaches
    Kafka and its consumers. **Faults:** frauddetectionservice pause, accountingservice pause (off-path), frontend pause
    (on-path control), productcatalog 0.1-core throttle at a rate where it binds. Each passes a manifestation pilot first.
98. **Cost model:** effort tiers per sensor (0 out of the box, 1 configuration, 2 code) and runtime-cost tiers (< 1 %,
    1-10 %, > 10 % CPU); the out-of-the-box (upstream default) posture is the starting point and a named comparator.
    The placement frontier is reported per (effort tier, runtime tier).

## Round 30 (user, 2026-10-12, on the v3.2 draft 7b518a2; before any campaign E cell exists)
99. **E pass rule (off-path sign rule):** for each off-path class (frauddetectionservice pause, accountingservice
    pause) separately, at E's rate, the frozen 6/h set passes if g = D(ledger alone) - D(S_6/h) > 0 over that class's
    test episodes and it improves at least 2 of them; on-path classes and other cells are reported without a verdict.
    `—` if a set member is absent from the scoring ground set or fewer than 2 valid test episodes exist (decisions 90-91
    carried over).
100. **Split:** 5 blocks; placement solved on blocks 1-3, frozen, scored once on blocks 4-5.
101. **Runtime tier is cumulative:** a set costs the cumulative posture steps needed to emit all its members (an async
    sensor also pays the selected step), so the runtime cap is a set-level deployment cost.
102. **Train-only calibration:** detectors for scoring E's test blocks are calibrated on training blocks only and
    applied unchanged to the test blocks (a reader change before the v3.2 freeze).
Engineering defaults (coordinator): off-path affected path = consumer + Kafka; E epoch name from the harness commit;
checkout rows that wait on a predecessor (`dependsOn`) are excluded from P1/P2 only, kept for detection.

## Round 31 (user, 2026-10-12, on the off-path pilot harness bff9fca; before launch)
103. **Telemetry-backend memory raised** for the off-path epochs: otelcol and jaeger to 1G each (upstream 200M / 400M;
     otelcol has no memory_limiter). Every SUT service keeps its upstream limit.
104. **Off-path pause hold 60 s**, as every other fault (a Kafka consumer-group rebalance after the 45 s session timeout
     is accepted as realistic behaviour; a container restart still invalidates the cell).
105. **Trace completeness per route** (decisions 25/56 read per route: each route must reach its declared services;
     async consumers neither required nor unexpected; allowance and windows unchanged).
106. **Envoy circuit breakers stay upstream defaults** (collateral 503s on untouched routes during a pause or binding
     throttle are part of the evidence).
Engineering default (coordinator): within each rate the no-fault cell runs first.
107. **Off-path pilot rates: 100 and 150 req/s** of the whole mix (user, 2026-10-12, on the GO review). The build's 100/200
     was the coordinator's prompt, not a user decision (corrected): the review put the frontend at >= ~0.94 core at
     200 req/s of the mix. Coordinator defaults recorded with it: off-path cells run right after the no-fault cell in each
     rate; at most 1 relaunch (harness or infrastructure defects only); E's rate = the lowest rate at which every kept fault
     manifests, else the highest rate at which any does (the user may veto before E).
108. **Off-path pilot v2 at 25 and 50 req/s, SUT limits upstream, throttle dropped from the pilot and from E** (user,
     2026-10-12, after productcatalogservice was OOM-killed at its 20 MiB limit at 100 req/s of the mix; BUDGET_E
     amendment 1). The off-path question needs Kafka traffic, not high load (checkout is 5.9 % of the mix: ~1.5-3 orders/s).
     Reportable as is: under upstream limits, productcatalogservice hits its memory limit at 100 req/s of the mix before
     its 0.1-core CPU throttle would take effect (~120 req/s by the load pilot's CPU per call). Ledger row: Docker's
     `oomKilled` read false after the restart; the restart guard caught it.

## Round 32 (user, 2026-10-13, after the off-path pilot v2 verdict 537a406; before campaign E)
109. **Pilot v2's verdicts set campaign E** although its fetch missed BUDGET_E amendment 1's 15:30Z deadline (VPN outage on
     the coordinator's side; the campaign itself was terminal at 12:42Z). BUDGET_E amendment 2. Result (instance, n = 1 per
     pair): frontend, frauddetectionservice and accountingservice pauses each manifest at 25 and 50 req/s; during either
     consumer pause every checkout in the hold succeeded (88/88, 89/89, 177/177, 177/177) while that consumer's spans
     stopped. E: 25 req/s (the declared rule, not vetoed), all three pauses, 20 cells. Coordinator defaults carried
     unchanged: frontendproxy 256 MiB floor at 25 req/s; 2 test episodes per off-path class (one invalid test cell makes
     that class `—`).
110. **E's pass rule reads the zero-alarm knot 3/T_r, not 6/h** (user, 2026-10-13, before launch, on the adversarial
     review's blocker). Under decision 73 a sensor costs its 95 % Poisson upper false-alarm rate over the rate's no-fault
     hours; E's training blocks hold 3 no-fault cells (~0.15-0.18 h), so the cheapest sensor costs >= ~17/h and the 6/h set
     is empty: both off-path verdicts would FAIL by construction. The rule's set is now the unrestricted frontier cell at
     3/T_r (T_r = training no-fault hours): exactly one zero-alarm sensor is affordable (2.996/T_r <= 3/T_r). Everything
     else in decision 99 stands (per off-path class, g > 0 over the 2 test episodes and both improved). The 6/h point is
     computed and reported without a verdict. Registry `V32_PASS_RULE` amended.
111. **Decision 84 (own-sensor exclusion) stays for the off-path classes** (user, 2026-10-13). The paused consumer's own
     signals do not count for its class, so a pass needs another lane. Prediction stated before launch from pilot v2 (not
     from E): the Kafka group coordinator logs a member failure about 43-44 s after the pause command (4/4 pilot off-path
     cells, 0/2 no-fault cells; it follows the consumers' 45 s session timeout), so a Kafka-side sensor is the likely pick
     and its detection time is set by that timeout. If E confirms it, the result is about which lane sees the fault and when,
     not a measure of the placement method's power.
112. **E's frozen set: recurrence rule plus two zero-alarm slots** (user, 2026-10-13, before the v3.2 freeze, on the v3.2
     review's blocker; E running, no E cell read). The review showed that at 3/T_r the single slot goes to a log id seen
     in one training episode: per-line log hashing makes 17-34 non-own `appear` ids per off-path pilot episode, 0 of them
     shared with any other episode (counted on the pilot v2 v3.2 shakedown readout), so the pick cannot fire in the test
     blocks; and the fraud and accounting Kafka member-failed ids are disjoint, so one slot serves at most one class.
     Rule: a sensor is a candidate for the frozen set only if it has a counted fire in >= 2 of the training episodes of at
     least one class; the pass-rule set is read at 6/T_r (two zero-alarm sensors evaluated in every training fold:
     2 x 2.996/T_r <= 6/T_r). Stated before freezing: a recurring sensor of the frontend class may take a slot, leaving an
     off-path class without one (then that class FAILs); the Kafka ids are appear-only and recur within a class (same 3 ids
     at both pilot rates). Decision 110's 3/T_r and the 6/h points stay reported without a verdict.
