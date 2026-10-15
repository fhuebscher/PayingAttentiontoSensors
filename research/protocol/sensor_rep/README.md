# Sensor representation (protocol draft 3 §2, PLAN part 2)

One event model for every channel, a vocabulary and thresholds per (population, posture) from no-fault windows, one catch
rule (appear / disappear / move) with G3 on every channel, and a replay of the old rules against
`research/visibility-map/MAP_TABLE.md`. Offline only: it reads retained evidence and launches nothing.

Scope: **method** for the representation and the rule. Every number below is **instance** (one host, one campaign per
population, populations never pooled). Status: built 2026-10-02 by a subagent and not yet reviewed by the user. Gate
(PLAN part 2): the user accepts the rule (K, τ, floors, baseline statistic, fallback) from the delta tables below. Any
change of K, τ or a floor is preregistration class.

## Commands

Clear the Apple bytecode cache before any `/usr/bin/python3` run (CLAUDE.md, "Bytecode caches lie"):

    rm -rf ~/Library/Caches/com.apple.python/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/research
    /usr/bin/python3 -B research/protocol/sensor_rep/replay.py                 # old rules vs MAP_TABLE.md, all five populations (~2 min)
    /usr/bin/python3 -B research/protocol/sensor_rep/replay.py hotel-sel1      # one population
    /usr/bin/python3 -B research/protocol/sensor_rep/run.py --replay           # new rule, writes tmp/protocol/<UTC stamp>/ (~4 min)
    /usr/bin/python3 -B research/protocol/sensor_rep/run.py --k 3 hotel-int1   # one point of a K grid (preregistration class)
    uv run pytest -q tests/test_sensor_rep.py                                  # 8 tests, fixtures only

`run.py` writes `vocab.json`, `vectors.jsonl`, `catches.jsonl`, `manifest.json`, plus `summary.md`, and with `--replay`
also `replay.json` and `replay.md`, to a new `tmp/protocol/<stamp>/`. It refuses to overwrite an existing directory.

## Layout

| file | what |
|---|---|
| `events.py` | `Event(channel, service, token, t, value, meta)`, the stream metadata (role, channel, source, level class, resolution, posture, onPath, projected state from `research/project-map/project_map.json`, collector, clock), `Stream`, `group` |
| `parsers/{hotel,teastore,otel}.py` | the only SUT-specific code. They reuse `symptoms.py`, `lmt_detect.py`, `adapter.py` and visibility's ledger readers by path and never edit them |
| `vectors.py` | windows (fault, pseudo, tile, pre), window membership, vector rows, `channel_counts` (`—` for a channel not retained) |
| `catch.py` | the NEW rule (`new_fire`, `Baseline`, `g3_loo`) and the OLD rule (`old_fire`, `old_ledger`, `old_rate_high`, `g3_inadmissible`) |
| `population.py` | the five populations, their posture tables (which posture collects which family), and which families the oracle G3-gated |
| `replay.py` | the old rules vs MAP_TABLE.md, plus episode-level checks against `visibility.json` and the OTel adapter's committed output |
| `run.py` | the new rule end to end, and the output files |

Engineering defaults are recorded in each module's docstring (catch: rule and floors; vectors: window edges and tiles;
events: tokens and level classes; parsers: clocks, tokens and file readings; population: posture tables).

## Replay at the old rules (oracle): result

At the old rules (sensors K = 4 against the cell's own pre-window, ledger max(3·raw MAD, 1 ms), G3 τ = 0.05 per family
over the pseudo windows), the event pipeline reproduces MAP_TABLE.md:

Run `tmp/protocol/20261002T115708Z` (HEAD f8110bc at run time, module uncommitted; Python 3.9.6, `run.py --replay`; `replay.md`
and `replay.json` there). `replay.py` alone gives the same agreement.

| population | evidence | cells (valid) | MAP_TABLE cells agreeing (n, ledger, L, M, S, Tsel, T) | episodes identical to the episode oracle |
|---|---|---|---|---|
| hotel-lmt2 | `tmp/hotellmt2-evidence/x` | 80 (80) | 28/28 | 64/64 vs visibility.json |
| hotel-sel1 | `tmp/hotelsel1-evidence/x` | 80 (80) | 28/28 | 64/64 vs visibility.json |
| hotel-int1 | `tmp/hotelint1-evidence/x` | 80 (80) | 28/28 | 64/64 vs visibility.json |
| teastore-T16 | `tmp/teastore16-evidence/x/teastore-candidate-pilot-v1` | 27 (27) | 14/14 | 18/18 vs visibility.json |
| otel-v3 | `tmp/otel-v3-evidence` | 24 (24) | 4/7 (3 deltas, below) | 12/12 vs the adapter output (visibility.json: — , ledger only) |
| **total** | | 291 | **102/105** (77/77 substantive) | **222/222** |

Of the 102 agreeing cells, 15 are the `n` column and 10 are `—` equal to `—`, so 77 of 77 substantive cells agree.

How informative the checks are. An independent review perturbed the old rule:
- on hotel-int1, K = 6 drops the table to 22/28 and the episodes to 39/64;
- on hotel-int1, τ = 0.2 gives 20/28 and 28/64;
- on teastore-T16, K = 6 with τ = 0.2 still gives 14/14 and 18/18; a 50 ms latency floor gives 17/18 episodes.

So the Hotel replay discriminates, but the T16 replay is nearly insensitive to K and τ (spans are not G3-gated there,
and logs carry no no-fault records). For OTel the table carries no information: its 3 deltas and their cause would read
the same whatever the replayed values were. The OTel evidence is the 12/12 adapter match, which drops to 3/12 under the
same perturbation.

Planted-defect check of the tests (2026-10-02, copies in the session scratchpad):
- making `appear` fire on every present token fails 5 of 8 tests;
- G3 `k ≤ n` in place of `k ≤ τ·n` fails the G3 test;
- dropping the status-200 condition from the Hotel ledger fails the round-trip test.

The episode-level checks are stronger than the table. For every valid fault cell, the admissible outside and own sensor
sets per family, and the ledger verdict with its in-window and failed counts, equal those in
`research/visibility-map/visibility.json`. For OTel they equal `research/otel-offpath/out/adapter-otel-v3-evidence-20261002.json`
(adapter ids carry an `=<kind>` suffix, which is stripped before comparing).

### Per-row delta table

| population | fault | column | MAP_TABLE | replay | cause |
|---|---|---|---|---|---|
| otel-v3 | frontend-pause | L | — | 6/9 | MAP_TABLE has no OTel detection (visibility.py: "— (no detection adapter for OTel Demo)"). This cause explains why the cell cannot match; it says nothing about whether 6/9 is right. That evidence is the separate 12/12 episode match against `research/otel-offpath/adapter.py`'s committed output, run with the adapter's own templating |
| otel-v3 | frontend-pause | M | — | 9/9 (own 9) | as L |
| otel-v3 | frontend-pause | T | — | 9/9 (own 9) | as L |

Every other cell of the five populations agrees: 102 of 105. The comparison also checks the reverse direction: a
MAP_TABLE row of a replayed population that the replay does not produce counts as a delta.

Not replayed, and why: MAP_TABLE's `class` and `caught by construction` columns are derived from the replayed columns
plus flags outside this module. The rows `teastore-Tnew`, `teastore-Gold` and `otel-run3` use evidence outside this
task's list (see "What remains").

## The OTel masking defect (VALIDITY.md §7): fixed in `parsers/otel.py`

`symptoms.mask` leaves product ids unmasked in recommendationservice bodies. The fix is typed rather than a narrower
regex:
1. A record that carries the OTLP semantic-convention attributes `code.filepath` and `code.lineno` is keyed by its call
   site.
2. Any other record has every Python-literal span (as `ast.literal_eval` accepts it) replaced by its type before
   `symptoms.mask`.

The attribute-aware pass sees exactly the adapter's log records: same per-service timestamps in 24/24 cells
(`log:recordsMatchAdapter`).

Distinct log templates per service in `tmp/otel-v3-evidence`, whole otelcol.log, all postures. The command that
produced these counts is below the table.

| service | `symptoms.mask` (adapter), 24 cells | same, 12 no-fault cells | fixed (call site or literal), 24 cells | basis of the fixed key (records) |
|---|---|---|---|---|
| recommendationservice | 8,665 | 5,284 | 2 | call site (12,818) |
| loadgenerator | 27 | 27 | 7 | call site (49,336) |
| kafka | 17 | 17 | 17 | literal (5,964) |
| cartservice | 6 | 6 | 6 | literal (36) |
| accountingservice | 2 | 2 | 2 | literal (24) |
| adservice | 2 | 2 | 2 | literal (12) |
| currencyservice | 1 | 1 | 1 | literal (6) |

VALIDITY.md's "about 1700 over 12 tiles" uses a different denominator: tiles of the no-fault cells, per posture set.
The 5,284 here counts whole no-fault cells. Both measure the same defect. loadgenerator's 27 → 7 merges the rows of
Locust's statistics table, which one call site prints. Command: `/usr/bin/python3 -B research/protocol/sensor_rep/otel_templates.py`.

The whole reduction comes from rule 1, which keys a record by its call site and drops the body. That is call-site
identity, not parameter-aware templating of the body. It merges distinct messages from one call site (Locust's
table rows), and it makes OTel log tokens a different unit from Hotel's and TeaStore's body templates. Rule 2
(literal parameterisation) changes no count on this evidence (kafka, cart, accounting, ad and currency are unchanged);
it is exercised only by the unit fixture. Its quote-boundary character set is a hand-picked default.

Hotel's periodic GoAway template (79–80 s, ERROR, phase-locked to start-up) is not filtered. It is an ordinary token,
listed per population under `knownPeriodic` in the manifest. Under the old rule it never falls in the 45–60 s window.
Under the new rule it enters the vocabulary through the 75–90 s tile, so it can neither appear nor (median 0 per tile)
disappear.

## The new rule on the same evidence

The rule is in `catch.py`. Its baseline is the no-fault tiles (hold length) of the same (population, posture), scored
leave-one-cell-out for G3. Counts are normalised to the tile length. The table lists admissible catches only, outside
the target (G2). The ledger column counts any admissible ledger catch. n_eff = tiles per posture, with the number of
cells; tiles of one cell are not independent.

Run `tmp/protocol/20261002T115708Z` (`summary.md` there). K = 4, τ = 0.05, floors as in `catch.py`.

| population | fault | n | ledger | L | M | S | Tsel | T | old rule (MAP_TABLE), where it differs |
|---|---|---|---|---|---|---|---|---|---|
| hotel-lmt2 | cpu-throttle | 16 | 0/16 | 0/12 | 0/8 | 4/16 (own 4) | — | 0/4 | M 1/8; S 0/16 (own 15) |
| hotel-lmt2 | net-delay | 16 | 16/16 | 0/12 | 0/8 | 3/16 (own 2) | — | 4/4 (own 4) | M 1/8; S 0/16 |
| hotel-lmt2 | reservation-pause | 16 | 16/16 | 12/12 | 8/8 (own 8) | 2/16 (own 2) | — | 4/4 (own 4) | M 7/8 (no own); S 0/16 |
| hotel-lmt2 | search-pause | 16 | 16/16 | 0/12 | 8/8 (own 8) | 5/16 | — | 4/4 (own 4) | S 1/16 |
| hotel-sel1 | cpu-throttle | 16 | 0/16 | 0/12 | 0/12 | 2/16 (own 7) | 0/4 | 0/4 | S 1/16 (own 15) |
| hotel-sel1 | net-delay | 16 | 16/16 | 0/12 | 0/12 | 1/16 (own 1) | 4/4 | 4/4 (own 4) | M 2/12; S 2/16 |
| hotel-sel1 | reservation-pause | 16 | 16/16 | 12/12 | 12/12 (own 12) | 3/16 | 4/4 | 4/4 (own 4) | M 12/12 (no own); S 0/16 |
| hotel-sel1 | search-pause | 16 | 16/16 | 1/12 | 12/12 (own 12) | 4/16 (own 1) | 4/4 | 4/4 (own 4) | M 11/12; S 1/16 |
| hotel-int1 | cpu-throttle | 16 | 0/16 | 0/12 | 0/12 | 1/16 (own 4) | 0/4 | 0/4 | S 1/16 (own 11) |
| hotel-int1 | geo-delay | 16 | 16/16 | 0/12 | 0/12 | 4/16 | 4/4 | 4/4 | same |
| hotel-int1 | rate-delay | 16 | 16/16 | 0/12 | 0/12 | 0/16 | 4/4 | 4/4 (own 4) | ledger 15/16; S 3/16; T own 3 |
| hotel-int1 | search-pause | 16 | 16/16 | 1/12 | 12/12 (own 12) | 2/16 | 4/4 | 4/4 (own 4) | M 12/12 (no own); S 3/16 |
| teastore-T16 | auth-freeze | 9 | 9/9 | 0/9 | — | — | 3/3 (own 3) | 3/3 (own 3) | same |
| teastore-T16 | persistence-crash | 9 | 9/9 | 9/9 | — | — | 3/3 (own 3) | 3/3 (own 3) | same |
| otel-v3 | frontend-pause | 12 | 12/12 | 9/9 | 9/9 (own 6) | — | — | 9/9 (own 9) | L/M/T — in MAP_TABLE; adapter at the old rule: L 6/9, M 9/9 (own 9), T 9/9 (own 9) |

n_eff per (population, posture), as tiles / cells: Hotel lmt2, sel1 and int1 have 32 tiles from 4 cells in every
posture. A channel the posture does not collect has 0 tiles: logs under `none`, spans outside `selected`/`full`.
TeaStore T16 and OTel v3 have 9 tiles from 3 cells, so at τ = 0.05 any single no-fault firing makes a sensor
inadmissible (⌊0.05·9⌋ = 0). The protocol's ≥ 20 no-fault windows are met only by Hotel, and there only by tiling 4
cells. Every catch carries G3 k/n_eff: a token absent from every no-fault tile gets k = 0 of the channel's n_eff, so
`g3: null` cannot occur by construction. The own-pre-window fallback was used by 0 catches.

What the new rule changes, with the mechanism where it is visible in the catches. These are not results to quote: the
rule is not accepted yet.

1. **The ledger becomes more sensitive, not less, under the sensors' K.** On int1, geo-delay is 16/16 and
   rate-delay 16/16 (old rule: 16/16 and 15/16). Decision 9 recorded 4/16 and 5/16 for the "4·1.4826·MAD rule", and
   that figure used the spread of individual request latencies in the cell's own pre-window. The new rule's statistic
   is the window median, and its spread is the tile-to-tile spread of medians: MAD 0.03–0.08 ms per posture
   (`vocab.json`, `ledger:frontend:hotel-search-v1:ok`). So the 1 ms floor binds, and the 2 ms delay moves the
   in-window median by about +2 ms, past it. Which spread the ledger is held to (per request or per window) is a rule
   choice for the user, not an engineering default. Scope: instance (int1, one host).
2. **Slow level metrics compared across cells pick up a per-cell offset.** Most of the extra S catches
   (lmt2 cpu-throttle 4/16, search-pause 5/16) are `sys_memory` level_up/level_down on non-target services. In 16 of
   19 lmt2 cases, the cell's own pre-window is already past the threshold in the same direction, so this is a
   per-cell level, not a fault effect. G3 does not remove them (k = 0 for 13 of 19, 1 for 6). Leave-one-cell-out
   would remove between-cell differences if the 4 no-fault cells showed that spread. They do not: the no-fault
   cells undersample it. (int1 geo-delay S 4/16 equals MAP_TABLE; it is not extra.) Candidates, both
   preregistration class: an own-pre-window baseline for slow level metrics, or levels centred per cell. Scope:
   instance.
3. **The cpu-throttle target's own S catches drop** (own 15 → 4 on lmt2, 15 → 7 on sel1, 11 → 4 on int1) because the
   new rule has no spike detector: `move` uses the window median only. On lmt2, the old own catches were
   `sys_psi_cpu spike_up` in 15 of 16 cells and `plateau_up` in 4, and the new rule catches exactly those 4 plateau
   cells. Whether a single-sample spike counts as a catch is a rule decision owed to the user. (Whether this removes
   the `BC-own-actuator` catches cannot be read here, because BC flags are not attached to catches.) Scope:
   instance.
4. **M on search-pause/reservation-pause** reaches 12/12 and 8/8 (old 11/12 and 7/8). The catches are callers' CPU
   `level_down`, services idling behind a stopped peer (MAP's `BC-idle-cpu`).
5. **OTel (no MAP oracle).**
   - L 9/9: recommendationservice's call-site template drops or disappears while the frontend is paused. It is a
     downstream service starved of requests, the `BC-downstream-absent` pattern, and becomes visible only because
     the fix makes the template a stable token.
   - M 9/9: frontendproxy `duration~mean` level_up.
   - T 9/9: recommendationservice operations disappear.
   n_eff is 9 here, below the protocol's 20.
6. TeaStore T16 is unchanged in aggregate (n_eff 9).

## What remains

Budget used: about one working day. Hotel, TeaStore and OTel were all built, in that order. Not done:
- **Rows not replayed:** `teastore-Tnew` (a5: blocked cells, a-p-w exclusion A15, the rate rule against its own
  vocab), `teastore-Gold` (60 GB old corpus, kieker-native, failure-half ledger, LOW/NO-WORKLOAD flags) and
  `otel-run3`. Each needs a population entry; Gold needs a parser. Estimate 3–4 h.
- **MAP_TABLE `class` and `caught by construction` columns:** derive them from the replayed columns
  (`visibility.classify` / `by_construction` could be called on the replay rows). About 1 h.
- **Planted positives on retained evidence** (draft 3 §2: one template line, one metric step, one span error, one
  failed request per SUT). The plants exist only as unit fixtures so far. Without them a silent channel cannot be told
  apart from a blind one. About 2 h.
- **Detector pool and selection rule** (§2b): repeated resampling of no-fault windows plus plants, runner-up detector,
  stability across resamples. Not started.
- **K × floor robustness grid:** `run.py --k` exists. Floors are module constants (`catch.py`) and are not yet CLI
  flags.
- **Metadata gaps:**
  - level class `info` means info-or-below, because the reused parsers collapse debug/trace;
  - the `by-construction` flag is not attached to catches;
  - the projected state is `?` for postures absent from the project map (Hotel lmt2 `logs`; all of TeaStore T16 and
    OTel v3 where the map's observed cells come from other campaigns);
  - OTel metric `source` is split by semantic-convention namespace.
- **Rule decisions owed** (preregistration class): ledger spread per request or per window (note 1); the baseline
  for slow level metrics (note 2); counts normalised to the tile length (adopted here because the open-loop schedule
  has MAD 0, so the floor of 2 would fire on window length alone: 151 vs 149 requests).
- **Housekeeping:** three superseded runs were kept, not deleted (deleting needs a yes):
  - `tmp/protocol/20261002T113639Z`, before the tile-overrun default (int1 had 28 tiles);
  - `20261002T114053Z`, aborted, with no manifest;
  - `20261002T114140Z`, before the review fixes (same numbers; its code hashes predate the docstring and compare edits).

  The definitive run is `20261002T115708Z`.
- **Review:** one independent read-only adversarial review (Opus subagent, 2026-10-02; the Fable attempt hit a rate
  limit). It confirmed the replay numbers and notes 1, 4 and 5, and found no blocker. It refuted the earlier wording of
  notes 2 and 3 and of the OTel delta cause, which are corrected above. Its other points are recorded here: the
  fallback condition (now documented in `catch.py` and tested); appear and disappear firing with 1–2 baseline windows;
  log counts widened by up to 1 s against their normalisation (`vectors.py` docstring); the PLAN schema differences
  (no `vocab.py`; vector fields `count`/`level` instead of `latencyMedianMs`/`failed`; no per-offered-request
  normalisation).
- **Provenance:** the manifest's `frameworkCommit` is HEAD. None of this module's code is committed (the user owns
  commits); the script sha256 values in the manifest pin the code that ran.
- **Write scope:** a pytest run under uv 3.13 created gitignored `__pycache__/` directories in four reused-module
  folders (`research/lmt-pilot`, `otel-offpath`, `visibility-map`, `hotel-selected`). No reused module was edited
  (the hashes match).
