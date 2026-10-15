# Amendment 1 to the S4 definitions: hierarchical sensors and a symptom alphabet (FROZEN 2026-09-27)

**Frozen 2026-09-27, before any S4 relevance, detection or MI value is computed.** Committed on its own. Reviewed independently by a Fable 5.1 `adversarial-review` subagent: first verdict 'not fit', then 15 fixes applied (1395999). The user's standing direction of 2026-09-27 decides A13–A15: T-16 in, H-A dropped, a-p-w excluded. Script sha256 7f332036… (committed `symptoms.py`); bags `tmp/s4-symptoms/20260927T100543Z/`. Any later change is a dated amendment committed on its own.

**Status: DRAFT, not an amendment yet.** It amends `research/s4-conjunction/DEFINITIONS.md` (frozen
2026-09-26, commit 962bf4f). Under that document's rule S-A it becomes Amendment 1 only when it is
committed on its own, dated, before any value in §4 is computed. This draft was written by a subagent on
2026-09-27 (8abee07) and revised the same day after an independent review found it not fit to freeze
(window-identity collapse on G-old, text/code mismatches, population changes undeclared); the main
session commits it. The user's own choices are listed in §10; A13–A15 carry the user's standing direction
of 2026-09-27, everything else there is open.

**What it amends (every frozen part that changes; nothing here is "unchanged").**

1. **U2** (families in U) and **U4** (log-sensor granularity: one `log:<svc>` sensor per service at ≥ WARN)
   are replaced by the hierarchical universe of §2.
2. **DEFINITIONS §3 population.** Adds **T-16** = `teastore-candidate-pilot-v1`, campaign #16, fb14srv5,
   27 runs (`tmp/teastore16-evidence/x`), as its own generation (A13). Removes **H-A** (#2 `fb8dcd9e`, #5
   `658f9b6a`): no adapter was tested on that plan's layout (A14). TeaStore's fourth posture
   `auth-persistence-webui` (a-p-w) is excluded from R(p) and from every §4 table; its rows stay in the bags
   labelled `a-p-w` (A15). H-B, H-B′, T-new and G-old are as frozen; the a-p-w rule also applies to T-new.
3. **DEFINITIONS §5 "T-new: cell-level".** Windowed rows now exist for T-new/T-16 (JUL, MariaDB records and
   spans have timestamps); log4j lines still enter the `cell` row only. Whether the `cell` row takes part in
   R(p) is A11 (draft default: no; it serves the C1 bridge).
4. **DEFINITIONS §7 "JVM stack traces … inherit their parent's level and never fire on their own".** A
   `Throwable.printStackTrace()` header (`<fqcn>[: message]`, never indented) now starts its own record with
   no level and emits `log:exception:<Class>` (plus every `Caused by:` class). Frames and `... N more` lines
   remain continuations. The MariaDB docker-entrypoint line is a second MariaDB layout.

Kept as frozen: the episode windows of §5 apart from item 3, the validity gate G1–G6 (§6, applied when
R(p) is built), the other parsers and the multi-line rule (§7), the objective (§8), the comparison C1–C5
(§9, with P1 narrowed as in §4 below), and the stop rules (§12).

**Why (user, 2026-09-27; memory `sensor-model-hierarchical`).** A service is not a sensor. A service switch
is an actuator. The sensors are control points inside a service: spans per operation, log event templates,
native metrics; the subsensors are derived signals (a count or rate of a template per window, like a
CloudWatch metric filter; a spike; a threshold). The ASOCA framing made HotelReservation look like one
switch. Every sensor's output is normalised into one **symptom alphabet**, so that a later encoder with
attention across services can learn relevance, and so that the relevance of each sensor, alone and in
combination, can first be counted deterministically.

**Scope label for everything below: instance.** One host, one workload and one fault catalogue per generation.

## 1. Disclosed prior look (beyond DEFINITIONS §1)

While building the parsers, the following fault-cell content was seen. It is disclosed so that the
predictions in §8 are read as consistency predictions where they touch it.

- Hotel #6 run `7fd8717d`, reservation-pause b05 `full`: the list of distinct (service, layout, level,
  caller, message-prefix) tuples of the whole `application.log` (209 distinct; the top row was 142 lines
  of `frontend ERR services/frontend/server.go:271 SearchHandler CheckAvailability failed`; the
  Consul-resolver `ERROR` and gRPC `GoAway ENHANCE_YOUR_CALM` lines from frontend and search). Search-pause
  b02 `full`: the alert-level lines are the same two Go-log messages, 0 zerolog warn/error lines.
- TeaStore e3-a5 (T-new) persistence-crash b01-02 `full`: the WARN/WARNING lines of `auth.log` and
  `persistence.log` (`ServiceLoadBalancer - No Server registered for Service: …persistence` ×22, two JUL
  `ServerRuntime$Responder.process An exception mapping did not …`, one `WadlFeature.configure`); the first
  30 lines of `auth.log` (a `ClientException` stack trace); the un-layouted lines of both files (Kieker's
  `WriterController:` banner). Also, from the trial run of the script: the symbol bag of the `auth` service
  in persistence-crash b01-01 `none` (cell window) and the span symbols of `persistence` in a
  persistence-crash `full` fault window. No count per regime was formed from any of this.
- `vocab.json`: the trial run's `noFaultWindowsPerService` (window counts per service) was read; the
  `symbolNoFaultWindows` block (the false-alarm column per symbol) and `templatesNoFaultCells` were **not**
  read by the author. The independent review of 8abee07 quoted one value from it (G-old `persistence/window`
  maximum 297 against n0 = 30, the window-identity defect fixed in this revision), so that one number is known.
- G-old `fault_persistence_crash_20260712_065031` (a July-12 run, **not** in the G-old population) and
  `fault_recommender_exception_20260717_…`: per-service layout mix of `logs.json`; the first two records of
  each layout; one `docker_events.json` record. `fault_db_crash_20260717_…`: the `db` lines that match no
  layout (MariaDB docker-entrypoint lines).

## 2. Sensor universe (replaces U2/U4)

Per generation, per service s, the universe is the disjoint union of

| modality | sensor | id | exists in |
|---|---|---|---|
| trace | one per **operation** (span name) observed for s in the generation's `full` cells | `span:<svc>:<op>` | Hotel (10 operations in the catalogued path set; the six catalogue sensors are a subset), T-new/T-16 (Kieker operation signatures), G-old (same) |
| log | one per **event template** t of s (§3.2) | `log:<svc>:<tid>` | every generation with a retained log stream for s |
| metric | one per **resource** r of s that the generation recorded | `metric:<svc>:cpu` (Hotel `cpu.json`, G-old `docker stats`); `metric:<svc>:mem` (G-old only); JVM MXBean later, via S5 | Hotel: cpu; G-old: cpu, mem; T-new/T-16: `—` (fault cells are `diagnostic-only`) |

Subsensors are not new sensor ids. They are the **symbols** a sensor can emit (§3). A sensor is "in S"
or not; its symbols are what the requirement set and the relevance baseline are written in.

- A service switch (`none` / `selected` / `full`, Hotel `none` / `sample-zero` / `full`) is an actuator over
  the trace sensors of that service. Log and metric sensors have no activation choice in any retained
  generation (U3 stays: "hypothetical activation choice at unit cost", both readings reported).
- Activation dependencies among log or metric sensors: none assumed (engineering default, as before).
- **What operation-level trace sensors do not give.** `research/CONDITIONAL_VOCABULARY_FEASIBILITY.md`
  found 19 level sets at every trace granularity. Operation-level ids are kept for the alphabet, not
  because they add level sets on their own.

## 3. Symptom alphabet v0

### 3.1 Grammar

A symbol is a string `<modality>:<sensor-part>:<symptom>` in the bag of one (generation, cell, service,
window). The service is the bag's key, so it is not repeated inside the symbol.

```
symbol   := log-sym | metric-sym | span-sym
log-sym  := "log:level:" level                    ; level ∈ {warn, error, fatal}
          | "log:template:" tid                    ; tid = 12 hex chars, §3.2
          | "log:template:novel"                   ; derived, §3.5
          | "log:rate:" tid ":high"                ; derived, §3.5
          | "log:exception:" class                 ; JVM Throwable simple class name
metric-sym := "metric:" res ":" msym               ; res ∈ {cpu, mem}
          ; msym ∈ {spike_up, spike_down, plateau_up, plateau_down, missing, ?}
span-sym := "span:" op ":" ssym                    ; op = operation name, ':'→'%3A', ' '→'_'
          ; ssym ∈ {present, error, latency_high, missing_expected}
```

The level vocabulary is one for all frameworks: zerolog `warn`/`error`/`fatal`+`panic`; gRPC
`WARNING`/`ERROR`/`FATAL`; log4j `WARN`/`ERROR`/`FATAL`; JUL `WARNING`→warn, `SEVERE`→error; MariaDB
`[Warning]`/`[Warn]`→warn, `[ERROR]`→error. Levels come from the layout's level field only (§7 of DEFINITIONS).

### 3.2 Log templates (typed parser output, no codebase-specific regex)

- Record-start layouts: the six in DEFINITIONS §7, plus two that the evidence forced and that are
  published formats, not codebase patterns: the **JVM `Throwable.printStackTrace()` header**
  (`<fully.qualified.ClassName>[: message]`, never indented, class segment capitalised), and the
  **MariaDB docker-entrypoint** line (`<date> <time>+00:00 [Note|Warn|ERROR] [Entrypoint]: …`).
- Template key = (framework, level, template-field, masked message), `tid` = the first 12 hex digits of its
  SHA-256. The template field is what the layout provides: zerolog `caller` (file:line) when present,
  else nothing; log4j logger; JUL logger.method; MariaDB `mariadb`; Go `log` nothing (it has no field).
- **Masking is language-level only**, applied in this order: UUIDs → `<uuid>`; IPv4 with an optional
  `:port` → `<ip>`; `0x`-prefixed hex of any length and bare hex runs of ≥ 8 characters (word-bounded) →
  `<hex>`; decimal numbers (optional sign, optional fraction) not preceded by a letter, digit or underscore
  → `<n>`, so `x8080` stays `x8080` and `exec-3` becomes `exec-<n>`; whitespace is collapsed. Nothing else
  is rewritten. A template miner (Drain) is a later option; v0 is exact modulo these masks.
- A throwable record has no template and no timestamp of its own. It emits `log:exception:<Class>` for its
  header class and for every `Caused by:` class in its continuation lines. On T-new/T-16 it therefore
  enters the `cell` row only; on G-old it carries the docker receive stamp and is windowed like every other
  record. Frames (`\tat …`, `... N more`) and any other line that starts no record are continuations of the
  previous record of the same container (unchanged rule). An orphan continuation is unparsed (G6).
- Harness lines are excluded before parsing (G5): `OBSPLACEMENT_*`, `OBSERVABILITY_*`, and compose CLI
  lines without a `<service>-<n> |` prefix. G-old's old `level` field is ignored.
- Timestamps: Hotel and T-new/T-16 from the layout (container clock, UTC); G-old the docker receive stamp
  for every record, as DEFINITIONS §7 says, even when the layout carries its own.

### 3.3 Metric symbols (the sprint's frozen rule, U11 unchanged)

Per (service, resource, window), with baseline = that cell's samples in `[t0, W.start)`:

- m = median, σ = 1.4826·MAD of the baseline; thr = max(4σ, floor). cpu floor = 1 pp (sprint). mem floor
  = 2 % of m (engineering default; there was no memory family in the sprint).
- `spike_up` / `spike_down`: some in-window sample x with x − m ≥ thr / m − x ≥ thr.
- `plateau_up` / `plateau_down`: ≥ 3 in-window samples and their median deviates by ≥ thr (a sustained
  shift; a pause gives `spike_down` and `plateau_down` together).
- `missing`: the service has a baseline but no sample in W. `?`: fewer than 3 baseline samples
  (unknown, never zero).
- The sprint's admissibility calibration (G3, false alarms over no-fault pseudo-windows) is carried in the
  vocabulary file, not as a symbol.

### 3.4 Span symbols

Per (service, operation, window), from `traces-normalized.json` (Hotel) or Kieker `traces.json`:

- `present`: ≥ 1 span of the operation starts in W (the live `f(S)` semantics, U8 primary).
- `error`: a span in W carries an error mark (Hotel: `tags.error` or `http.status_code ≥ 500`, the sprint's
  rule; Kieker: a `status_code` that is not null, 200 or 0; F14 still says all Kieker marks are null, so
  this is `—` for TeaStore).
- `latency_high`: the in-window median duration exceeds the baseline (same cell, `[t0, W.start)`, ≥ 3 spans)
  by the robust rule with a 1 ms floor.
- `missing_expected`: the operation had ≥ 1 span in the baseline and none in W.
- All four are silent under `none` / `sample-zero` by construction (DEFINITIONS §11).

### 3.5 Derived log symbols and the calibration population

Calibrated **inside one generation only** (S-G) on the **valid no-fault cells** of that generation:

- `log:template:novel`, **per service**: some template in the row occurs in no no-fault cell of the
  generation **for the same service** (any window kind; leave-one-cell-out when the cell is itself a
  no-fault cell, else novelty is 0 by construction). The same template in another service does not make it known.
- `log:rate:<tid>:high`, per service: the template's count in the row exceeds its counts over the no-fault
  windows that calibrate the row (one value per window, absent = 0) by the robust rule with floor 2. The
  calibrating windows are: for a `cell` row, the no-fault `cell` rows; for a `fault` or `pseudo` row, the
  no-fault `pseudo` rows, and on G-old only those pseudo-windows whose length D_f is the fault family's
  (each baseline run carries one pseudo-window per distinct D_f, so n0 = 30 baseline runs for every
  family). This is the CloudWatch-metric-filter subsensor.
- The vocabulary file records, per generation and service: the number of no-fault cells that contain each
  template (`templatesNoFaultCells`); the number of calibrating no-fault windows per class
  (`noFaultWindows`, keys `<svc>/cell`, `<svc>/window`, G-old `<svc>/window:<families sharing D_f>`); and
  the number of those windows in which each raw symbol fired (`symbolNoFaultWindows`, the false-alarm
  column, always ≤ `noFaultWindows`). G3's τ = 5 % rule (U6) is applied from these numbers when R(p) is
  built, exactly as DEFINITIONS §6 says. `pseudoDurations` (D_f per family) is written to `summary.json`
  and `manifest.json`.

### 3.6 Windows and rows

Every cell produces one row per (window, service). Window kinds:

| kind | Hotel | T-new / T-16 | G-old |
|---|---|---|---|
| `fault` | `[startedAt, endedAt]` of `fault-receipt.json` | `[actualOnsetWall, actualOffsetWall]` of `intervention.json` | `[fault_started_at, fault_finished_at]` |
| `pseudo` (no-fault cells) | `[t0+45, t0+60]`, t0 = first `cpu.json` sample | `[start + a, start + a + b]`, a = median onset offset and b = median hold over **all** fault cells of the generation, **both regimes pooled and invalid cells included** (timing metadata only) | `[start+75, start+75+D_f]`, one row per distinct D_f, labelled with the families that share it (`window.pseudoFor`) |
| `cell` | the retained stream (logs only, no G1) | the measurement window of `receipt.json` | the retained (pre-buffered) stream |

Log records enter a `fault` or `pseudo` row iff ⌊W.start⌋ ≤ t ≤ W.end (the sprint's 1-second floor,
applied on **every** generation); metric samples and spans use W.start unfloored. Log4j lines carry no
timestamp, so on TeaStore they enter the `cell` row only; so do throwable records on T-new/T-16 (§3.2).
JUL and MariaDB records and all spans are windowed. The `cell` row exists so that TeaStore stays comparable
with the sprint's cell-level detection and so that novelty is calibrated on whole cells, as the sprint did.
Metric and span symbols are computed for `fault` and `pseudo` rows only. A service with no stream in a
cell has no row (absence, not zero); a service with a stream and no symbol has an empty row. Rows of the
a-p-w posture carry `label: "a-p-w"` (A15).

### 3.7 Validity gate

G1–G6 of DEFINITIONS §6 are kept unchanged and are applied when R(p) is built from the bags, not when the
bags are written. The bags are pre-gate: they carry everything the parsers produced, so that C2 ("every
change is traced to the gate that caused it") can be computed from one file.

## 4. Relevance baseline (step 2; computed only after this amendment is committed)

All of this is instance scope, per generation, never pooled, and every table names its denominator.

**Populations and denominators.**
- *Episodes.* For span symbols and for R(p): the generation's valid **`full`** fault cells (the only
  posture that exports spans). For log and metric symbols: every valid posture **except a-p-w** (A15),
  reported per posture and pooled over postures; the a-p-w rows are in the bags and in no table.
- *No-fault denominator.* One `pseudo` row per valid no-fault cell per posture (Hotel 24 per posture, 72
  pooled; T-new 12 minus a-p-w = 9, T-16 9); G-old one per baseline run per D_f (30 per family class).
- *Rows.* The `fault` row of the episode and the service (A11: the `cell` row does not take part).
- *Missing rows.* A service with no row in an episode (no stream of any kind) is excluded from that
  symbol's denominator for that service, and the exclusion count is printed beside the table.
- *Zero.* A symbol with count 0 over n episodes is reported as `0/n`, never dropped.

**Sensor firing.** A sensor fires in a row iff at least one of its symbols **other than**
`span:<op>:present`, `metric:<res>:?` and `metric:<res>:missing` is in the row. `present` is the U8
requirement event, not a symptom; `?` is unknown and `missing` is absence of the stream. G3
admissibility (τ, from `vocab.json`) is applied to log templates and metric symbols; it is **not** applied
to span symbols (there is no no-fault span calibration in the sprint and none is added here).

**Tables (per generation, per service and pooled over services).**
- **Per symbol × fault class, alone.** For each symbol σ and regime c: episodes of c whose row contains
  σ / episodes of c; and the false-alarm count over the no-fault `pseudo` rows / their number. This is the
  sprint's detection table generalised from 7 detectors to the alphabet.
- **Per sensor.** The same with the firing rule above.
- **Combinations.** For pairs of sensors, and for triples only when the number of sensors that fire in
  ≥ 1 episode of the generation is ≤ 200: the conjunction count (episodes in which both fire) and the
  union count, against the single-sensor counts. A pair whose conjunction equals the smaller single count
  is redundant; one whose union exceeds the larger single count is complementary. This is the "alone vs in
  combination" question of the memory note, answered by counting.
- **Mutual information.** I(σ; C) in bits, plug-in estimate on the generation's rows, with 0·log 0 = 0;
  the class support is the generation's fault regimes plus **one no-fault class** made of the `pseudo`
  rows; computed per service and pooled. No test, no interval: at 24 episodes per regime it is a ranking
  aid, not a result.
- **Objective.** `f_all`/`f_any` of DEFINITIONS §8 over R(p) built from the bags with G1–G6 applied, where
  a sensor enters R(p) iff it fires (rule above) with an admissible symbol in the episode's `fault` row of
  its service.
- **C1 bridge, narrowed (P1).** With U4's `log:<svc>` reconstructed as "any template of s at level ≥ warn",
  the bridge must reproduce the **level, metric-target, metric-other and trace-error rows** of
  DETECTION_RESULT (H-B tables; sweep row "warn+"; T-new level 11/11, 0/9, no-fault 0/12). Novelty and the
  latency figures are **not** part of P1: novelty here is per service and per template, and latencies
  are not computed from the bags.

## 5. What is preregistered here and what is an engineering default

**Preregistered (changes what counts as a sensor or a requirement; frozen by committing this file):**
the three-modality universe of §2 with template-level log sensors and operation-level trace sensors; the
grammar of §3.1; the level vocabulary; the metric rule parameters (k = 4, cpu floor 1 pp); the four span
symptoms; the derived symbols and their calibration population (§3.5); the window kinds (§3.6); the
relevance baseline of §4; the gate G1–G6.

**Engineering defaults (recorded, changeable without an amendment as long as the bags are regenerated
and the manifest says so):** the mask set of §3.2; the 12-hex template id; mem floor 2 %; the 1 ms latency
floor; the burst floor 2; the plateau minimum of 3 samples; `MIN_BASELINE = 3`; the G-old population rule
(runs listed by a complete `fault_campaign_*.json` manifest dated 2026-07-17/18, kieker_native, all
sidecars present; a partial campaign is excluded and counted); the `.operational` dumps off by default;
output paths; `/usr/bin/python3 -B` with `~/Library/Caches/com.apple.python/` cleared before a replay.

## 6. Script, self-check and manifest

`research/s4-conjunction/symptoms.py` (`--self-check`; `hotel|teastore|gold <generation> <path>` triples;
`--out tmp/s4-symptoms`). It reuses the sprint's `detection.py` (SGR strip, ConsoleWriter levels, gRPC
prefix, log4j parser, robust rule, span error mark) by import. It writes, under a new UTC-stamped
directory, `bags.jsonl` (one row per window × service), `vocab.json` (calibration counts of §3.5),
`summary.json` (cells, layouts, unparsed share per generation and service, vocabulary sizes; never by
regime) and `manifest.json` (every input file with size and SHA-256, the script's and `detection.py`'s
SHA-256, the framework commit, argv, interpreter). A generation label bound to two adapters is refused.

The self-check builds a Hotel and a JVM fixture and asserts the exact symbol sets, then plants defects:
a message containing the word `ERROR` at level info must not yield `log:level:error`; mutating the level
field must change the symbol set (the check is not vacuous); a flat CPU series must not spike and a
planted spike must; a two-sample baseline must yield `?`, not nothing. `tests/test_symptoms.py` (21 tests,
fixtures only) covers each layout, the multi-line rule, the mask, the three adapters on synthetic cells,
the same-generation leave-one-out calibration, the window-class rule, the G-old per-family pseudo-window
rule (≥ 2 pseudo-windows per baseline run, `symbolNoFaultWindows ≤ noFaultWindows`), the declared-broker
S-P case (an Erlang-layout `rabbitmq.log` trips the 5 % rule), the a-p-w label, and the S-G refusal.

## 7. Vocabulary sizes and coverage (allowed before commit: not outcome values)

**Provenance.** Regenerated under the final script after the review: `tmp/s4-symptoms/20260927T100543Z/`
(H-B, H-B′, T-new, T-16, G-old; 9,832 bag rows, 2,441 hashed inputs) and `tmp/s4-symptoms/20260927T100648Z/`
(T-new-op, the `.operational` variant). `manifest.json` records the script SHA-256
`7f33203647ce7ed6aedec53be996f0a4ee543b952474d9265b1094ccf65a6fb8`, which is the content hash of
`research/s4-conjunction/symptoms.py` as committed with this revision; `/usr/bin/python3` 3.9.6. The
earlier stamps (`…T091658Z`, `…T091853Z`, `…T092057Z`, `…T092200Z`, `…T092410Z`, `trial/`) were produced by
superseded script states and are kept, not overwritten. The numbers below are identical to the
`…T092057Z` run, as the review's fixes changed calibration keys and labels, not parsing. Cells and valid
cells; excluded runs with reasons; application lines = total − harness; unparsed share (S-P stops a
generation's log family above 5 %); layout mix; distinct templates, exception classes, operations and
symbols per modality. **Not** by regime, posture or service-with-regime.

**T-new and T-16 no-fault cells contain 0 application records (all lines are harness witnesses), so
their template calibration set is empty** (`templatesNoFaultCells` has no entry for any TeaStore service;
see §9). G-old `pseudoDurations`: the 11 families have 11 distinct D_f (45.2–55.6 s), so every baseline run
carries 11 pseudo rows and `noFaultWindows` is 30 for every `<svc>/window:<family>` key; the
`symbolNoFaultWindows ≤ noFaultWindows` invariant holds for all keys of all generations (checked on the
regenerated `vocab.json`, 0 violations). 48 bag rows carry `label: "a-p-w"` (T-new).

| generation | cells (valid) | excluded | application lines (harness) | unparsed | share | layouts | templates | exception classes | span ops | symbols log / metric / span |
|---|---|---|---|---|---|---|---|---|---|---|
| H-B (#6 runs 3–6) | 216 (216) | — | 62,727 (1,828,438) | 0 | 0.0 % | zerolog-console 49,688; go-log 6,558; zerolog-json 6,480 | 162 | — (no JVM) | 10 | 165 / 3 / 23 |
| H-B′ (#6 run 1) | 54 (54) | — | 15,643 (457,101) | 0 | 0.0 % | 12,423; 1,600; 1,620 | 161 | — | 10 | 164 / 3 / 22 |
| T-new (e3-a5) | 35 (32) | blocked dirs skipped | 5,498 (7,772) | 27 | 0.49 % | jul 497; log4j 370; jvm-throwable 24 | 58 | 4 | 37 | 68 / — / 70 |
| T-16 (pilot-v1, 27 runs) | 27 (27) | — | 4,534 (5,822) | 21 | 0.46 % | jul 407; log4j 302; jvm-throwable 20 | 58 | 4 | 37 | 68 / — / 70 |
| G-old (fb14srv6, 2026-07-17/18) | 140 (140) | 112 missing sidecar (empty dirs of eight later campaigns), 7 partial campaign | 234,410 (0) | 1 | 0.0004 % | log4j 12,249; jul 4,454; jvm-throwable 2,610; mariadb 1,572 | 171 | 9 | 32 | 221 / 7 / 55 |
| T-new-op (T-new + `.operational` service dumps; A8) | 35 (32) | — | 8,968 (8,829) | 762 | **8.5 %, S-P fires** | + mariadb 286 | 104 | 5 | 37 | 115 / — / 70 |

- Hotel compose CLI lines: 216 and 54 (one per cell), excluded by G5. Continuation lines: 1 and 0.
- The T-new/T-16 unparsed lines are all in `persistence.log`: Kieker's `WriterController:` start-up banner
  (orphan continuations, G6). Every other line parses.
- G-old: the one unparsed line is in `recommender`. The 140 runs are 110 fault + 30 baseline, F2's
  population, reached by the complete-campaign rule (A7).
- T-new-op: 669 of the 762 unparsed lines are `rabbitmq.log` (Erlang report layout, not covered; rabbitmq
  is a declared compose service). Without rabbitmq the share is 93 / 8,299 = 1.1 %. Under S-P no pattern is
  added; the variant's log family is stopped unless A8 excludes the broker.
- Hotel `metric` symbols: 3 = `metric:cpu:{spike_down, plateau_down, spike_up}` seen somewhere; G-old 7.
  These are vocabulary sizes, not counts.
- P7 holds on every generation (58–171 templates).

## 8. Predictions (written before any relevance value is read)

Consistency predictions restate sprint counts (marked "(sprint)").

- **P1** (hard gate): the C1 bridge with U4 reconstructed from templates reproduces DETECTION_RESULT
  exactly. (sprint)
- **P2** H-B: in reservation-pause, `log:level:error` fires in frontend's `fault` row in ≥ 20/24 `full`
  episodes and the template of `services/frontend/server.go:271` is the one that carries it; in
  search-pause no `log:level:*` symbol fires in any service in ≥ 20/24. (sprint, now at template level)
- **P3** H-B: `span:<op>:missing_expected` fires for the paused service's own operation in ≥ 20/24 `full`
  episodes of each regime, and `span:<op>:error` for a frontend operation in ≥ 20/24 (sprint's error-span
  count, now per operation). Both are close to true by construction and are listed in §9.
- **P4** H-B: at least one `log:rate:<tid>:high` symbol fires outside the target service in ≥ 12/24
  reservation-pause episodes; the direction for search-pause is not predicted.
- **P5** T-new: `log:exception:ClientException` fires in auth's `cell` row in ≥ 8/11 persistence-crash
  cells and in 0/9 auth-freeze cells (disclosed look; consistency only).
- **P6** G-old: at least two fault families whose `fault` rows carry a `metric:*:spike_*` symbol in some
  non-target service in ≥ 5/10 runs and no `log:level:*` symbol in the same rows (the G4 count of
  DEFINITIONS, now with memory as a second resource).
- **P7 (withdrawn: observed in §7, not a prediction.)** The template counts per generation (58–171) were
  already in §7 when this line was written; they bound how many log sensors the placement domain gets and
  are not predicted by anything.

## 9. True by construction (not results)

- A paused service's `metric:cpu:spike_down`/`plateau_down` and its `span:<op>:missing_expected`.
- A crashed service's restart lines are novel templates and its exception classes appear in its callers.
- Span symbols are silent under `none` / `sample-zero`.
- Any template that occurs in every no-fault cell is admissible-inadmissible by G3 regardless of the fault.
- More templates means more distinct R sets, mechanically (DEFINITIONS §11).
- The count of `log:level:warn` on TeaStore crash cells is the sprint's `ServiceLoadBalancer` count.
- On T-new/T-16, `log:template:novel`, `log:rate:*:high` and every log false-alarm count of 0 are true by
  construction: the no-fault cells contain 0 application log records (every retained line is a harness
  witness), so the template calibration set is empty and every template in a fault cell is novel.

## 10. The user's decisions

Each changes what counts as a sensor, a requirement, or the population. The draft default is what the
script implements now.

| # | Decision | Draft default | Alternatives |
|---|---|---|---|
| A1 | Sensor granularity for logs | one sensor per event template (§3.2) | per (template, level); per logger; per service (U4 as frozen) |
| A2 | Sensor granularity for traces | one per operation | per service (U12, catalogue ids); per (operation, kind) |
| A3 | Metric resources | cpu (Hotel, G-old) + mem (G-old) | add G-old network; add proc/JVM families (S5) |
| A4 | Which derived symbols enter R(p) | all of §3.5 | presence only (`log:template:<tid>`); level only (the sprint) |
| A5 | Template identity | exact modulo language-level masks | Drain-mined templates; include the level in the id (current) or not |
| A6 | Calibration population for novelty and rate | valid no-fault cells of the same generation, leave-one-out | no-fault cells of the same run only (the sprint's Hotel rule) |
| A7 | G-old population | complete campaigns only (140 runs); partial first campaign excluded | all 147 runs with sidecars; the F2 list by date |
| A8 | `.operational` TeaStore dumps | off (blocked cells and re-runs only) | on, as a separate generation label |
| A9 | Relevance baseline scope | per generation, per symbol and per sensor, pairs and small triples | symbols only; sensors only; add a greedy set-cover ranking |
| A10 | Mutual-information estimator | plug-in on episode counts, no correction | Miller–Madow; none (counts only) |
| A11 | Whether the `cell` row participates in R(p) | no (TeaStore log4j lines enter via the cell row for C1 only) | yes, for TeaStore only |
| A12 | Metric floors | cpu 1 pp (U11), mem 2 % of median | cpu 2 pp (0/72 false alarms in the sweep); mem absolute bytes |
| A13 | T-16 in the population | **decided (user, 2026-09-27): yes**, as its own generation (campaign #16, `teastore-candidate-pilot-v1`, fb14srv5, 27 runs) | — |
| A14 | H-A (#2, #5, plan `98773760`) | **decided (user, 2026-09-27): dropped**; no adapter was tested on that layout | re-admit after an adapter test |
| A15 | a-p-w posture rows | **decided (user, 2026-09-27): excluded from R(p) and from every §4 table; kept in the bags labelled `a-p-w`** | — |

## 11. Stop rules and budget

- **Budget: 1 day** for the alphabet and the relevance baseline together (NEXT_STEPS S4). At 50 % over,
  stop and write a ledger row.
- **S-P** (unchanged): an unparsed share above 5 % of a generation's application lines stops that
  generation's log family; no pattern is added to close it.
- **S-B** (unchanged): if P1 fails, no relevance or conjunction number is reported.
- **S-G** (unchanged): generations are compared, never pooled; the script refuses a label bound to two adapters.
- **S-V**: if a generation's template vocabulary exceeds 1,000, template-level sensors are replaced by
  logger-level sensors for that generation (A1 alternative) and the change is recorded as post hoc.
- **S-Z** (unchanged): a family that never fires is `0/n`; no data is `—`; unknown is `?`.
- **S-J** (unchanged): one judge call per claim before it enters a document.
- **S-O** (unchanged): every run writes to a new `tmp/s4-symptoms/<utc-stamp>/`; nothing is overwritten.

## 12. Open questions (append-only log)

- F14 stays open: do any Kieker records carry a status code? Until then `span:<op>:error` is `—` on TeaStore.
- Hotel memory: `cpu.json` carries CPU only. Is a memory sample retained anywhere for Hotel #6 (`—` if not)?
- Whether the two MariaDB layouts (server log and docker entrypoint) should be one sensor family or two.
- The G-old first campaign `fault_campaign_20260717_162748` (7 runs) is excluded by the completeness
  rule; DEFINITIONS F2 said 140 runs, and this rule reproduces that number by a rule, not by a date list.
