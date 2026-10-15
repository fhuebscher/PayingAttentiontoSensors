# Deviation record: analysis v2.4 to v3.1 (and decision 92)

Written 2026-10-12 (committed 4742cfb). **Not independently reviewed**: the cross-provider `judge` server failed to connect
in this session (CONNECTION_CLOSED), and no same-provider reviewer has read this file. Every "foreseeable" verdict below
is the writer's judgement from the cited documents and commits, not a measurement. Scope label: **method** (the analysis
chain), evidence read from three SUT instances; nothing here is a cross-SUT claim.

## 0. What is compared

| | v2.4 (the earlier freeze) | v3.1 (the later freeze) | decision 92 amendment |
|---|---|---|---|
| reader | `research/detection-time/sweep_analysis_v2.py`, sha256 `075c43e5870170c8b59cdbe1a970b56dc03920d67514027b9a95e5de38d962e9` | `research/detection-time/sweep_analysis_v3.py`, sha256 `2e7ec5c387fa906a02026f0d1a5212b974f17751c24f76526a1d8418b2fd4fdd` | script unchanged |
| registry | `research/protocol/parameters.json`, sha256 `7447b492abf64f42ebaf547a640c84929ac15b59ebc1e495d5082f279373fc68`, 77 entries (73 active, 2 superseded, 2 not-used-by-v2) | `research/protocol/parameters_v3.json`, 32 entries, sha256 `f6257b78fedfdcab9577f37cdba77a6fc6d785e4b0b34641cb18de6bb21ade9a` | now `212830bec3e6669bc211d5cffa48d61fa3bf0f6d4dd5ceaf79d3e2bcc7c4d000` |
| code commit | `098f3e0` 2026-10-05T12:06:16+11:00 | `7ec9f28` 2026-10-10T02:31:41+11:00 | `fdbdb16` 2026-10-12T11:44:18+11:00 |
| freeze record | `891a4c3` 2026-10-05T12:07:34+11:00 | `990d501` 2026-10-10T06:04:37+11:00 | `be3a7f1` 2026-10-12T11:56:34+11:00 |
| decisions | 31-60 (rounds 8-14) | 61-65 (`252cfcd`, 2026-10-09T21:35), 66 (`e12e98f`), 67-68 (`d8df15d`, 21:57), 69 (`f6aea2d`), 70 (`147c910`, 2026-10-10T00:28) | 92 (`fdbdb16`) |

Digest checks run for this record (command: `shasum -a 256` on the working-tree files, and `git show 7ec9f28:research/protocol/parameters_v3.json | shasum -a 256`):
v2.4 script and registry digests equal the freeze record `891a4c3`; v3 script digest equals `990d501` and `git diff --stat 7ec9f28 HEAD`
on it is empty; the 7ec9f28 registry is `f6257b78`; the working-tree registry is `212830be`, which `be3a7f1` states
(`research/protocol/FREEZE_DECISION92_20261012.md:S1`). `git show fdbdb16 -- research/protocol/parameters_v3.json` shows only the
`STUDY_EPOCHS_B` hunk.

Decisions 71-91 (placement step and campaign C test scoring) are not registry entries and change nothing in the frozen
reader; they are listed in group 10 because the request named the placement objective and costs "if it is in the v3 chain".

Abbreviations: PD = `research/PROTOCOL_DRAFT_20261002.md`; SYN = `research/traffic-sweep/SYNTHESIS_V2_4.md`;
DES = `research/protocol/ANALYSIS_V3_DESIGN.md`; P24 = `research/protocol/parameters.json`; P3 = `research/protocol/parameters_v3.json`
(line = the entry's `"name"` line); LIT = `research/protocol/LIT_DETECTION_RULES.md`; MH = `research/protocol/METHODOLOGY_HARDENING.md`;
REV = `research/traffic-sweep/readout-hotel-r3-v2-fix1/REVIEW.md` (`cb795c5`, 2026-10-04T20:27); NS = `research/NEXT_STEPS_20260925.md`;
S2 / S3 = the v2.4 / v3 reader scripts; FR92 = `research/protocol/FREEZE_DECISION92_20261012.md`.

## 1. Summary

**Unit of count: a deviation row.** One row is one separable change (one v2.4 value or rule that v3 replaces, narrows or
adds to). Rows are not registry entries: 30 registry entries map to 34 rows and 2 entries are bookkeeping (some entries carry
several rows; rows 8.1 and 8.4 share the entry `STUDY_EPOCHS_B`). Coverage of all 32 `parameters_v3.json` names is checked by script (section 8).

Foreseeable = could the change, or the information that triggered it, have been known before the v2.4 freeze `891a4c3`
(2026-10-05T12:07+11:00)? **yes**: a document or data dated before the freeze implied the change itself. **partly**: it
implied the need or the mechanism, but the value, shape or instance came from data or artefacts first read or written after the
freeze. **no**: it arises from new code, a new campaign, or a review of v3's own code, none of which existed at the freeze.

| group | registry entries | rows | yes | partly | no |
|---|---|---|---|---|---|
| 1 Calibration unit, criterion, honest counts | 6 | 6 | 3 | 2 | 1 |
| 2 Level-rule thresholds (K grid, range fallback) | 3 | 5 | 3 | 1 | 1 |
| 3 `absent` and `appear` rules | 4 | 4 | 2 | 2 | 0 |
| 4 Ledger, status taxonomy, P4 | 5 | 5 | 1 | 3 | 1 |
| 5 False-alarm reporting and fresh check | 3 | 3 | 3 | 0 | 0 |
| 6 Pooling, campaign keys, quiet time | 2 | 3 | 2 | 0 | 1 |
| 7 Onset (H4) timing and carrier | 4 | 4 | 0 | 3 | 1 |
| 8 Schema and epoch admission | 3 | 4 | 2 | 2 | 0 |
| 9 Bookkeeping and display (not deviations) | 2 | 0 | n/a | n/a | n/a |
| **groups 1-8** | **30 (+2 in group 9 = 32)** | **34** | **16** | **13** | **5** |
| 10 Placement step and C test scoring (outside the registry) | 0 | 7 | 3 | 2 | 2 |

Denominator for the 16 / 13 / 5: the 34 rows of groups 1-8. Group 10 is a different population and is not added in.
These counts are mine and are conservative toward admitting foreseeability: where a pre-freeze document named the problem
and the freeze did not act on it, the row says **yes**, not **partly**.

**What the record says about foreseeability overall.** The expensive part of v3 (per-rule unit, zero-alarm criterion,
censored-silence gap, B1 removal, placement-level FAR, fresh check) was documented as an option or a risk before the v2.4
freeze in 16 of 34 rows. The mechanism that took three families (M, S, T) off the operating point was observed on Hotel at 10/s on
2026-10-04 (REV:24-28, `cb795c5`), one day before the freeze, and was answered by "the K grid is not extended; the quiet runs add
calibration time" (PD:379, decision 55). Decision 92 (row 8.4) is foreseeable: **yes**; the same failure class was named in the v3.1
freeze record for campaign B (`990d501`, open item R2) and the C declarations list the analogous harness-side allowlist edits.

**Exposure (forking paths), by what each row responded to** (column "Informed by"):

| tag | meaning | rows | count |
|---|---|---|---|
| T | responded to existing cells read under v2.4 (fault outcomes and/or no-fault cells of Hotel sweep r3 + quiet A, TeaStore sweep r2 + quiet A, OTel sweep r1 + quiet A r1), directly or through the v3 design review's feasibility run | 1.1 1.2 1.5 1.6 2.1 2.2 2.3 2.5 3.1 3.2 3.3 3.4 4.1 4.3 4.4 4.5 6.3 | 17 |
| H | responded to design reasoning, literature or harness documents only (no outcome data named as the trigger) | 1.3 1.4 2.4 4.2 5.1 5.2 5.3 6.1 6.2 7.1 7.2 7.3 7.4 8.1 8.2 8.3 | 16 |
| OB | outcome-blind: made before any campaign C cell was read | 8.4 | 1 |

All 34 rows were decided after the v2.4 readouts of all three systems had been read (TeaStore `6d8f095` 2026-10-05T12:12,
Hotel `0274c54` 12:15, OTel `b5f3a1f` 13:20; synthesis `aaef8cc` 13:38) and four days before v3 was adopted (`252cfcd`
2026-10-09T21:35). Tag H means the record names no outcome as the trigger, not that the decider was blind. v3.1 was frozen
(`990d501`) before any campaign B or A2 cell was read (first B and A2 read under it: `0a8517a`, `3d6bf3b`, 2026-10-10T15:23), so for
B, A2 and C the groups 1-8 rows except 8.4 are pre-specified; for the cells that shaped them they are not (section 6).

Rows I could not fully source are in section 7.

## 2. Group 1: calibration unit, criterion, honest counts

| # | parameter (v3 registry name) | v2.4 | v3.x | decision, commit | triggering observation | foreseeable before 891a4c3? | informed by |
|---|---|---|---|---|---|---|---|
| 1.1 | `V3_CALIBRATION_UNIT` (P3:15) | `K_FIT_UNIT` = "family" (P24:36); one K per (system, family); the ledger E is its own family (S2:268, S2:2351) | "sensor-rule": one threshold per (sensor, rule) and rate; a sensor's detector is the OR of its calibrated rules | 61 (PD:425), `252cfcd` | SYN:86-93 (one uncalibratable rule removes a family, B1 then removes P4); SYN:36-44 (family table); SYN:105-108 (option 1); DES:9-11, DES:15-19 | **partly.** Mechanism: yes. REV:23-31 and REV:89 (Hotel, 2026-10-04T20:27): at 10/s only L reaches 15/h, T is kept out by one span sensor (`memcached_get_profile`, 4 alarms at K = 100), P4 is `—`. LIT:134 (`d34907c`, 2026-10-04T14:29): "calibrate each sensor's combined rule". Decision 53 (PD:370) chose the family after the v2 review asked (M4). Instance: no. Which few rules bind on TeaStore and OTel was first visible in readouts of 2026-10-05T12:12-13:20; Hotel's binding L rule was unarmed at 4 cells (8 < 20 records, SYN:56-58) and appeared only with the 40 quiet cells, which existed unread (Hotel run A complete ~2026-10-04T11:10Z, NS:575-577). Recorded response to the Hotel symptom was more quiet time, not a unit change (PD:379). | T |
| 1.2 | `V3_MAX_HELD_OUT_ALARMS` = 0 (P3:23) | `FAR_TARGET_PER_HOUR` = 15.0 (P24:30), `FAR_MEETS_CRITERION` = "upper" (P24:34): smallest grid K whose exact 95 % bound is <= 15/h | smallest grid value with zero held-out alarms (leave-one-cell-out); 3/T printed as a bound, never as a claim after 67 | 61 (PD:425), amended 67 (PD:452); `252cfcd`, `d8df15d` | SYN:116-118 (option 6: 15/h vs 6/h; 3 certifiable alarms at 0.55 h, 4 at 0.70 h); SYN:92-93; DES:20-25 | **yes.** The arithmetic and both targets were written down before the freeze: MH:84-88 (`cf83a0d`, 2026-10-04T14:51: "<= 15/h is the most this data can certify"), decision 33 (PD:319), decision 48 (PD:359, a 6/h quiet run). NS:599-601 (post-freeze) records the same tension: "frozen at 15/h (decision 33) although decision 48 sized the quiet runs for <= 6/h". Why not acted on: no recorded reason; the v2.4 freeze changed none of the decision-33 values. | T |
| 1.3 | `V3_SENSITIVITY_MAX_HELD_OUT_ALARMS` = 1 (P3:31) | not present (v2.4 sensitivity rows: floor arm 5 %, P24:22; per-system K) | one extra setting "<= 1 held-out alarm"; not tried for the range fallback | 65 (PD:437), `252cfcd`; 67 pt 4 | DES:62-63 ("zero alarms favours late detection") | **yes.** A consequence of the zero criterion's own arithmetic; no data trigger. | H |
| 1.4 | `V3_CALIBRATION_SCOPE_RULE` (P3:101) | `CALIBRATION_SET_RULE` (P24:109): false alarms counted per fault class on that class's scored set (decision 55, M3: "the detector calibrated must equal the detector scored") | calibration per rate, independent of fault class; one value per rule and rate; M3 not applied | 61; 67 pt 5 (PD:452) | DES:105-106 states it without an observation | **partly.** Inherits 1.1: class-independence follows from any rule-level unit. The M3 trade-off was on record on 2026-10-04 (PD:377-378) but no document weighed it against a rule-level unit before the freeze. | H |
| 1.5 | `V3_NESTED_RULE` (P3:149) | not present: K chosen as the smallest value meeting the target on the held-out counts it is then certified by (P24:36) | honest nested leave-one-cell-out count: each held-out cell scored at the value re-selected without it, inner fits excluding both cells; per-sensor honest rate is the CELF cost; evaluated-fold denominators (F2) | 67 (PD:452), `d8df15d`; F2 in `0b23efe` | DES:79-83: the reviewer's feasibility run (`tmp/v3review/`, gitignored) found the union of a family's calibrated rules alarms 20-340/h honestly (Hotel S 340, TeaStore S 91, TeaStore T 52, OTel M 50) while the zero-alarm bound says <= 6/h | **yes.** Selecting on the same cells that certify is the leakage pattern LIT:255-257 (`d34907c`) calls "the textbook case"; v2.4's own K selection had the same optimism and nothing nested it. The size (20-340/h) is data-dependent and was first measured 2026-10-09. | T |
| 1.6 | `V3_TESTABLE_RULE` (P3:157) | not present | a held-out fold whose fit cannot arm a rule is no evidence (no alarm, no test); a rule with no nested evidence has count `—`, never 0 | engineering default, `908302b` 2026-10-09T22:29; accepted by the coordinator 2026-10-09 (P3:251) | P3:157 origin_ref: found while building v3.1; OTel MAD = 0 metrics were re-selected at the range in every nested fold by vacuity, about 1,200 honest alarms per rate (OTel: 411-460 calibrated rules per rate armed with one cell left out, not with two) | **no.** An artefact of nested fits (n - 2 cells) that exist only in v3.1, found on OTel data. | T |

## 3. Group 2: level-rule thresholds

| # | parameter | v2.4 | v3.x | decision, commit | triggering observation | foreseeable? | informed by |
|---|---|---|---|---|---|---|---|
| 2.1 | `V3_LEVEL_GRID_RULE` (P3:39); `K_GRID` itself unchanged | K grid of 19 values 2.5 to 100 (P24:13), "above it a family is reported as not certifiable by K"; one K per family | each level rule (spike, run3, median; the ledger's on ok latency) tries K_GRID ascending (cap K <= 100, decision 55 kept), then the range fallback; each rule on its own, so run3 and median can fire before spike | 62 (PD:428), `252cfcd` | SYN:36-44, SYN:112-114 | **yes.** The cap was known to bind before the freeze: REV:27 and PD:379 (decision 55, 2026-10-04): T "would certify at K = 200", the grid "is not extended after the fact". P24:13 itself says the upper end "has no source". | T |
| 2.2 | `V3_RANGE_FALLBACK_RULE` (P3:55), `V3_RANGE_WIDEN_STEPS` = 1 (P3:47) | no quantile or range threshold: `SCALE_NOT_ESTIMABLE_RULE` (P24:106) "no quantile threshold"; decision 52 (PD:368-369) names an empirical-quantile threshold as a later sensitivity row (W2) | lower = fit min - 1 resolution step, upper = fit max + 1 step, over the pooled fault-free values; fires beyond (inclusive) | 62 (PD:428), `252cfcd` | SYN:71-77: two-state series (TeaStore `sys_io` 3,275 B/s or exactly 0), quantised OTel GC rates (two values, MAD 7e-7), bimodal `resolve_page_components`, heavy tails; SYN:112-114 option 4; DES:26-31 | **partly.** Need: yes (decision 52, PD:368-369; REV:80, Hotel r0.05 "not evaluable (MAD = 0, threshold = resolution)"; PD:379 K = 200). Shapes: no, TeaStore and OTel series first read 2026-10-05T12:12-13:20. The widening of one resolution step and the extreme-quantile choice have no source beyond DES:28-29; no sensitivity row exists for them (`—`). | T |
| 2.3 | range fallback direction, label and scope (inside P3:55; V3 amendment) | not present | up-only for latency channels (spans, ledger), two-sided for metrics; labelled "discrete in effect"; no "<= 1" row for it | 67 pt 4 (PD:452), `d8df15d` | DES:86-88: a continuous series always leaves exactly one held-out alarm (reviewer's run, 2026-10-09) | **yes.** An order-statistics fact (a fresh cell exceeds the maximum of n cells with probability 1/(n+1), DES:81-82 states it) derivable without data. | T |
| 2.4 | MAD = 0 handling (inside P3:55); v2.4 `SCALE_NOT_ESTIMABLE_RULE` (P24:106) | MAD = 0 with >= 20 pooled points: level rules `—`, no catch, no false alarm | decision 52 kept for K rules; the range fallback may apply where MAD = 0 (labelled) | 67 pt 5 | DES:105-106 | **yes.** Decision 52 (PD:368-369, 2026-10-04) already named the quantile alternative. | H |
| 2.5 | degenerate-range guard (inside P3:55) | not present (no range rule existed) | a range with no instrument resolution in the fit, or a threshold <= 0, is unarmed ("range degenerate"), never dropped and never re-armed in the optimistic arm | independent v3.1 review finding F1 (Fable, 2026-10-10), `0b23efe` | P3:55: inclusive >= on a {0, 0} threshold fired on every sample (Hotel `sys_io`, `sys_psi_io`, `sys_psi_memory` are 0.0 everywhere) | **no.** A defect in new code found by an independent review of that code. | T |

## 4. Group 3: `absent` and `appear` rules

| # | parameter | v2.4 | v3.x | decision, commit | triggering observation | foreseeable? | informed by |
|---|---|---|---|---|---|---|---|
| 3.1 | `V3_ABSENT_M_GRID` = [1, 1.5, 2, 3, 5] (P3:63) | `ABSENT_GAP_MULT` = 2.0 (P24:42), an engineering default from `detection_time.py:113` (`dbebcbb`) | g = m x G; smallest m on the grid meeting the criterion (so v3 may select a multiplier below v2.4's 2.0 as well as above) | 62 (PD:428), `252cfcd` | SYN:53-58 (Hotel `log:frontend:1c9632baa7b5/absent`, 14 alarms, 20/h at every rate); SYN:67-68 (13 OTel kafka templates); SYN:78-80; SYN:109-111 option 3 ("a gap multiplier ... fitted to the budget") | **partly.** The multiplier was an unsourced default from the start (P24:42) so fitting it was always a candidate; pre-freeze evidence that `absent` on one-shot bursts is a calibration risk is row 3.2. The grid values {1, 1.5, 2, 3, 5} have no source beyond DES:32-33 (no literature, no measurement). | T |
| 3.2 | `V3_ABSENT_CENSORED_RULE` (P3:77) | gap G pooled from fault-free data (H1), inter-arrival gaps only (P24:42; DES:32-33 contrasts v3 with "including" the censored silences) | G = largest of the fit cells' inter-arrival gaps plus the censored silences from segment start to first record and last record to segment end; a cell with no record contributes none | 62 (PD:428), amended 67 pt 4 | SYN:56-58 (Hotel GoAway pair at +76-77 s in every cell; with 4 cells pooled count 8 < 20 so never armed, with 14 cells armed at gap 0.79 s and fires after the pair in every cell); SYN:78-80 (kafka bursts at +4-5 s and +125 s) | **yes.** LIT:262 (`d34907c`, 2026-10-04T14:29) names this exact template: "Hotel's gRPC GoAway template recurs every 79-80 s (`research/sensor-validity/VALIDITY.md:209`) ... a short window also underestimates the largest gap that `absent` relies on". VALIDITY.md:205-212: present in 120/120 cells, phase-aligned to start-up, at -4.8 to -2.5 s and 75.2 to 77.5 s. Hotel's 40 quiet cells existed unread (NS:575-577). Why missed (recorded, SYN:56-58): the rule was unarmed at the 4 sweep cells, so Hotel's v2.4 sweep readout showed no problem. Writer's reading, not recorded: pooling the baseline (H1, decision 31) was taken as the remedy LIT:262 asked for, and the window-edge silences were not considered. | T |
| 3.3 | `V3_APPEAR_RULE` (P3:85) | `appear` fires on a stream with no record in the fit; not calibrated | `appear` calibrated by the same criterion; a stream with a record in the pooled fit is unarmed for `appear`; vocabulary-level held-out `appear` rate reported beside; `appear`-only sensors listed apart | 62 (PD:428); 67 pt 3 (PD:452) | DES:88-89: `appear` alone makes almost every sensor placeable, so "not placeable" never discriminates | **yes.** A stream that can fire `appear` in an episode has no no-fault record, so its held-out count is 0 by construction (P3:85 says so); derivable from the rule definition. Decision 62 adopted calibrating it anyway (2026-10-09) and the review found it vacuous the same day. | T |
| 3.4 | `V3_INERT_RULE` (P3:165) | not present | an `absent` whose calibrated gap exceeds the shortest fault hold (60.0002 s in the primary readouts, `calibration.primary.hold`) is inert: not in the detector, not a reason for placeability | 67 pt 3 (PD:452) | DES:86-88: censored-gap rules calibrate at 90-264 s gaps, longer than the 60 s hold, so they can never fire | **partly.** The 60 s hold was declared (MH row 9, "Misses charged at the 60 s hold"); a 90-264 s gap exists only through the new censored-gap rule (3.2), whose need was foreseeable. | T |

## 5. Group 4: ledger, status taxonomy, P4

| # | parameter | v2.4 | v3.x | decision, commit | triggering observation | foreseeable? | informed by |
|---|---|---|---|---|---|---|---|
| 4.1 | `V3_LEDGER_RULE` (P3:93) | E is a family with its own K (S2:2351); ledger `absent` on completions (`LEDGER_ABSENT`, P24:82); `failed` is an armed rule | `failed` exempt from calibration (client's definition of failure, the positive control of P1/P2), always armed, its no-fault count reported; E's spike, run3, median and absent calibrated per rule | 63 (PD:433), `252cfcd`; 67 pt 6 | SYN:64: OTel E at 10/s, 404 alarms at K = 4 and 17 at K = 100 (16 spike + 1 `failed`, a failed request in a no-fault cell); SYN:115 (option 5); DES:45-47 | **partly.** Hotel's E was already off K = 4 before the freeze (REV:24: "E is at K = 20"). That a `failed` request inside a no-fault cell is a false alarm was first seen in OTel quiet data (2026-10-05). Exempting `failed` is a definitional choice available any time. | T |
| 4.2 | `V3_P4_LEDGER_READING` = "calibrated-ledger" (P3:350) | not present (E at the operating point or P4 is `—`, S2:2662) | the ledger in P4 is the OR of its calibrated rules (`failed` exempt); a dropped ledger rule is listed, not a reason for `—`. Replaces the default accepted 2026-10-09: "P4 is `—` where an armed ledger rule is dropped" (P3:251) | 70 (PD:469), `147c910`; code `7ec9f28` | independent v3.1 review finding F4 (the review text is not committed; see section 7); DES:108-109 (TeaStore r0.05: E's `absent` precedes `failed`) | **no.** Arises from per-rule ledger calibration (4.1) as a reading ambiguity found by review of new code. Whether F4 was informed by P4 outcomes: `—` (not established from the committed record). | H |
| 4.3 | `V3_P4_RULE` (P3:125) | `P4_NOT_EVALUABLE_RULE` / B1 (P24:112; decision 55, PD:376): P4 is `—` when the ledger or any collected family is not at the operating point | P4 over the placeable sensors; dropped rules and non-placeable sensors named per (class, rate); calibrated (primary) and optimistic arms; `—` only where fewer episodes than declared exist | 65 (PD:437), amended 67 pt 6, 70; `252cfcd`, `d8df15d`, `147c910` | SYN:23, SYN:29-31 (P4 `—` everywhere on TeaStore and OTel; Hotel search-pause 0/4); SYN:119 (option 7); DES:54-56 | **yes.** B1 was written on 2026-10-04 as the fix for REV:23-31, and REV:89 already reported the consequence on Hotel: "At 10/s, P4 is `—`: no family except logs reaches <= 15/h within the K grid". SYN:86-88 itself calls the removal "by construction, not a finding". Caveat for attribution: TeaStore and OTel had one episode per (fault, rate) at v2.4, so P4 and P2 were `—` by rule independent of B1 (SYN:13-14; P24:129-130); the share of `—` due to B1 alone is not separable from the record (`—`). | T |
| 4.4 | `V3_OPTIMISTIC_ARM_RULE` (P3:173) | not present for P4 (the optimistic/pessimistic bound idea is H6, MH:128-130, decision 42, PD:342, a placement robustness row) | optimistic arm: dropped rules also armed at the largest grid value (K = 100, m = 5), inert and unarmed excluded; printed as "optimistic bound (not evidence)", never primary | 67 pt 6 (PD:452) | DES:90-91: on OTel, in 4 of 8 episodes a dropped rule at K = 100 catches where every calibrated rule misses (productcatalogservice GC count, frontendproxy egress, frontend GET, frontend calls) | **partly.** H6 and the bound idea predate the freeze. Applying it to dropped rules follows from per-rule dropping (1.1). The trigger is a fault-outcome observation (survivorship), the one place a fault-cell result directly shaped a v3 arm. | T |
| 4.5 | `V3_STATUS_RULE` (P3:109) | "at operating point" vs `—`; K = 100 is the edge (P24:13) | statuses calibrated / dropped / inert / unarmed / exempt; placeability per (sensor, rule); "not placeable at this quiet time"; K = 100 flagged "at grid edge" | 62 (DES pt 4), 67 pts 3 and 5 | DES:40-45, DES:99-101, DES:88-89 | **partly.** The grid-edge flag is yes (P24:13 origin text). The inert and appear-only distinctions came from the feasibility run (rows 3.3, 3.4). | T |

## 6. Group 5: false-alarm reporting and the fresh check

| # | parameter | v2.4 | v3.x | decision, commit | triggering observation | foreseeable? | informed by |
|---|---|---|---|---|---|---|---|
| 5.1 | `V3_PLACEMENT_FAR_RULE` (P3:117) | per-family held-out false-alarm counts only; no placement-level figure | honest nested union of a sensor set's rules on the rate's no-fault cells, with exact bound; sum of members beside; no constraint inside the objective | 64 (PD:435), amended 67 pts 1-2; `252cfcd`, `d8df15d` | SYN:94-98 (option 2); DES:49-52; DES:84-85 (the first formulation, the naive union, is 0 by construction) | **yes.** LIT:131-135 (`d34907c`): "Report the placement-level FAR beside every placement score", with the Q6 independence warning; the placement step was deferred, not unknown (PD:302, decision 29). | H |
| 5.2 | `V3_VALIDATION_RULE` (P3:133) | not present | no-fault cells given as `--validation` are never pooled or refitted; the calibrated detectors are run on them; fault cells given there are listed and unused | 65 (PD:437), 67 pt 2 | DES:59-61 and DES:84-86 (selection on the certifying cells; Hotel gets no fresh cells) | **yes.** Leakage: LIT:255-257. Campaign B and its no-fault cell per rate and block were declared on 2026-10-04 (decision 49, PD:361). | H |
| 5.3 | `V3_B_FRESH_HOURS` = 0.15 (P3:181) | not present | 0.15 h of fresh no-fault time per rate per system from B; zero-alarm bound printed as about 20/h (`bFreshCheckLimit.boundZeroPerHour` = 19.97 in `readout-hotel-primary-v3.1/sweep_analysis_v3.json`) | 49 (PD:361), 67 pt 2 | DES:84-86 | **yes.** The arithmetic 3 / 0.15 h follows from decision 49's cell design (one 180 s no-fault cell per rate and block). | H |

## 7. Group 6: pooling, campaign keys, quiet time

| # | parameter | v2.4 | v3.x | decision, commit | triggering observation | foreseeable? | informed by |
|---|---|---|---|---|---|---|---|
| 6.1 | `V3_HARNESS_TAG_RULE` (P3:235) | `EPISODES_TEASTORE` = `EPISODES_OTEL` = 4 declared (P24:129-130) as "k of 4" with no harness tag | every cell and episode tagged `B` or `sweep`; P2 and P4 pool the sweep episode with B's three; per-harness breakdown printed beside every pooled verdict (P4 folds, P2, P1, H4 status) | 49 (PD:361) plus the coordinator's instruction of 2026-10-09 | P3:189 (L-H10, L-H4): the sweep and B differ in harness (readiness probe after the fault command; H4 record) | **yes.** H10 and "stamp the freeze" were agreed on 2026-10-04 (decision 42, PD:342) and B was declared "after the H10/H4 harness change" (PD:361) the same day, so a pooled "k of 4" across two harnesses was declared with the difference already known. No recorded reason the v2.4 registry carried no tag; v2.4 had only sweep cells. | H |
| 6.2 | `V3_POOL_KEY_RULE` (P3:243) | a cell identified by its run ID / run path (P3:243 text); duplicates not stopped | identity = (campaign directory, path inside it); a cell given twice stops the run | 68 (PD:458), 69; `5d018ab` 2026-10-09T22:00 | A2 repeats A's plan and run IDs under a new campaign ID (`DECLARATION_QUIET_A2_HOTEL.md`) | **no.** A2 was decided on 2026-10-09 (round 17); before it a repeated run ID could not occur. | H |
| 6.3 | no-fault time T per rate (no registry entry; decision 68 and the pooled campaigns) | Hotel 0.70 h, TeaStore and OTel 0.55 h per rate (SYN:34) | rate 1, primary v3.1 readouts: Hotel 24 cells = 1.20 h, TeaStore 26 cells = 1.30 h, OTel 21 cells = 1.05 h (`calibration.primary.perRate["1"].cells` and `.hours` in each `readout-*-primary-v3.1/sweep_analysis_v3.json`); other rates not read here (`—`) | 68 (PD:458), `d8df15d` | DES:84-85; PD:458 ("more quiet time") | **yes.** LIT:121 (`d34907c`): "Showing <= 1 per hour needs >= 3 alarm-free hours per rate"; decision 48 bought quiet time on 2026-10-04. The extra run A2 itself was decided after the freeze. | T |

## 8. Group 7: onset (H4) timing and carrier

| # | parameter | v2.4 | v3.x | decision, commit | triggering observation | foreseeable? | informed by |
|---|---|---|---|---|---|---|---|
| 7.1 | `V3_FREEZE_EVENTS_RULE` (P3:141) | TeaStore sweep onset interval [command issued, command returned]; OTel [startedMonotonic, appliedMonotonic]; Hotel uses the Docker pause event (`P1_AMBIGUITY_WINDOW_RULE`, P24:96, decision 54) | B-campaign fault cell with exactly one usable Docker `pause` event of its target gets it as the upper bound; otherwise H4 is `missing` with reasons, the cell stays valid, keeps the sweep bound and is counted per harness; throttle cells keep v2.4's bound | 49, 54, 69 (PD:463), `f6aea2d` 2026-10-09T23:25; reader `9ac8ead`, rewritten to the harness record schemas in `0b23efe` after review findings F3, F6, F7, F11 | B harness drafts `DECLARATION_B_TEASTORE_DRAFT.md` ("H4, as implemented") and `DECLARATION_B_OTEL_DRAFT.md` ("H4: stamp the freeze"), read 2026-10-09; harness commits `bbb6b11` (23:29), `0ad9a2c` / `c4aa313` (23:33) | **partly.** Intent: yes (decision 42, PD:342; decision 54, PD:372, both 2026-10-04). Record formats and the block-vs-record policy: no, they did not exist before the drafts of 2026-10-09; precedent for "record, don't block" is decision 56 (PD:383, 2026-10-04) for OTel trace loss. | H |
| 7.2 | `V3_FREEZE_EVENT_TOLERANCE_S` = 0.25 (P3:205) | not present (v2.4's P1 tolerance adds Docker-event granularity, P24:92) | the pause event must fall within [command issued - 0.25 s, upper bound + 0.25 s] | engineering default | both B harness drafts' `freezeEventToleranceSeconds` | **partly.** A mapping tolerance was implied by decision 54; the value is the harness's. | H |
| 7.3 | `V3_FREEZE_REPLAY_TOLERANCE_S` = 1e-06 (P3:213) | not present | the reader's replay check of event offsets and command stamps uses the validators' 1e-6 s | engineering default | `DECLARATION_B_TEASTORE_DRAFT.md` 'The validator recomputes it (tolerance 1e-6 s)' | **no.** A cross-check of the new reader against a new validator. | H |
| 7.4 | `V3_KNOWN_LIMITATIONS` (P3:189): L66, L-H10, L-H4 | `KNOWN_LIMITATIONS` F7, F9, F10, F11, G4 (P24:150); nothing on the carrier | L66: `otelcol.log` is a lossy carrier in the OTel sweep and quiet cells (collector log sampler on), so a missing span there may be a carrier drop; B's OTel collector disables the sampler (decision 66), so B fault cells are read through a different carrier than the calibration cells; L-H10 and L-H4: the harness difference of 6.1 | 66 (PD:447), `e12e98f` 2026-10-09T21:51; L-H10, L-H4 at the coordinator's request 2026-10-09 | `research/traffic-sweep/OTEL_LOST_BATCH_DIAGNOSIS.md` (not independently reviewed, P3:189) | **partly.** The loss was observed and recorded on 2026-10-04: `a0e74b4` ("r10 b02 lost one 5 s batch of productcatalog spans (probably carrier-side)", 21:04) and decision 56 (PD:383-385: a lost batch "is what makes an `absent` rule fire on a healthy system"). The cause (default log sampler, `materialize.py:650-653` at `6a47d0b`) was diagnosed 2026-10-09. L-H10 and L-H4: yes (6.1). The direction claim ("conservative for `absent` and the level rules", P3:189) is unreviewed. | H |

## 9. Group 8: schema and epoch admission

| # | parameter | v2.4 | v3.x | decision, commit | triggering observation | foreseeable? | informed by |
|---|---|---|---|---|---|---|---|
| 8.1 | `STUDY_EPOCHS_B` (P3:366), B part | only `SYSTEM_<SUT>.studyEpochs` (sweep and quiet) pass `check_schema` (S2:1189-1190, S2:1492; P24:122-123) | adds `teastore-traffic-sweep-b-v1` and `otel-repeat-episodes-v1`; any other epoch name stops the run (`UnknownSchema`, S3:1178 `admit_b_epochs`) | 49 (PD:361); `26f16ff`, `9ac8ead` | the B harness drafts name the epochs (P3:366: draft read 2026-10-09) | **yes.** B was declared on 2026-10-04 (3 more blocks, EPISODES = 4, P24:129-130) and v2.4's reader refuses an unknown epoch by design (P24:145 origin: "A file that differs is refused loudly (the run stops)"), so some registry edit for B was certain. The names are from 2026-10-09. | H |
| 8.2 | `V3_B_RECORD_KEYS` (P3:266) | not present | exact key sets of the TeaStore `freezeStamps` and OTel `dockerEvents` / `freeze` records, pinned from the harness writers at `bbb6b11`, `0ad9a2c` (re-pinned `c4aa313`); another key set stops the run | independent v3.1 review finding F3, `0b23efe` 2026-10-10T00:12 | writer commits of 2026-10-09T23:29-23:33 | **partly.** That the freeze stamp needs some record is decision 42; the key sets did not exist before the harness drafts, and the first reader (`9ac8ead`) was written to drafts the harnesses then changed (decision 69). | H |
| 8.3 | `V3_B_SCHEMA_ADDITIONS` (P3:221) | OTel `intervention.json` key set pinned by equality (P24:145, `SCHEMAS.otel.intervention.json.keys`) | key `freeze` admitted for B-epoch OTel cells only; sweep cells keep the exact set | 69; `9ac8ead` | `DECLARATION_B_OTEL_DRAFT.md` 'H4: stamp the freeze' (new key `freeze`) | **partly.** Same as 8.2: the need follows from decision 42, the key name from the 2026-10-09 draft. | H |
| 8.4 | `STUDY_EPOCHS_B` (P3:366), C part | the v3.1 freeze admits only the two B epochs | adds `teastore-traffic-sweep-c-v1` and `otel-repeat-episodes-c-v1` as campaign-B-shaped; `V3_B_RECORD_KEYS` unchanged, so a C record of another shape still stops the run; `sweep_analysis_v3.py` unchanged; `parametersV3Sha256` becomes `212830be` | 92 (PD:548-557), `fdbdb16` 2026-10-12T11:44:18; freeze record `be3a7f1` | PD:548-550: the frozen v3.1 reader refused both C campaigns at the schema check (`UnknownSchema`, studyEpoch not in the admitted list), so decision 88 could not run; no C declaration named the reader change (FR92 N2: the cited `DECLARATION_C_OTEL.md:159` is the wrong line; the claim holds by absence) | **yes.** (i) The allowlist is fail-closed by design (P3:366: "Any other epoch name stops the run"). (ii) Decision 82 (PD:506-508, 2026-10-10) declared C with "a new study epoch"; `DECLARATION_C_TEASTORE.md:5-8, 34` and `DECLARATION_C_OTEL.md:25` say so. (iii) The C declarations list the harness-side allowlist edits for the new epoch (`DECLARATION_C_OTEL.md:61-63`: `REPEAT_STUDY_EPOCHS = (B, C)`, `ADMITTED_STUDY_EPOCHS`), so the analogous reader edit was foreseeable. (iv) The v3.1 freeze record `990d501` already flagged the same class for B (open item R2: "a real B receipt's key set may need a one-line reader re-pin (fail-closed UnknownSchema)"). (v) `/usr/bin/grep -n -e STUDY_EPOCHS_B -e reader research/traffic-sweep/BUDGET_C.md` returns nothing. (vi) FR92 N3: no test drives a C-epoch cell through `find_and_load3`. Why missed: no recorded reason; the C declarations enumerated harness guards and not the analysis reader. | OB |

**Decision 92 is outcome-blind, by commit order.** `fdbdb16` 2026-10-12T11:44:18 precedes the C readouts `720957c` (11:54:40,
"committed unedited before reading") and the C test scores `ac3845a` (11:56:44); the digest was checked on both C readouts'
input fields before scoring (FR92 S1: both carry `parametersV3Sha256 = 212830be...`, their `parametersV3` dump differs from the
training readout's only in `STUDY_EPOCHS_B`, `scriptSha256` and `v24Sha256` equal the training readout's). What the refusal exposed
is only the `studyEpoch` string of each campaign's receipt. Not verified by me: that no one viewed C's harness-side summaries
(for example `campaign-terminal.json` or the wandb log) before `fdbdb16`; the record asserts it (PD:555) and I have no
evidence either way (`—`). Limitations the amendment created, from FR92 S2: pooling C as an extra campaign gives 7 episodes per (fault, rate)
against `EPISODES` = 4, so P2/P3/P4 render `—` with a wrong "(n < 4)" reason; `harness_breakdown` counts B and C together under "B";
the readout's "exploratory, not frozen" label is wrong; `celf_v3`'s held-out folds must not be run on a C readout (FOLD_KEY merges
B and C blocks). FR92 N5 (decision 88, declared): C's fault cells contribute their pre-onset segments to the pooled fit, so the
detectors that score C are partly fitted on C's pre-onset data.

## 10. Group 9: bookkeeping and display (registry entries that are not deviations)

| parameter | content | why not a deviation |
|---|---|---|
| `V3_ACCEPTED_DEFAULTS` (P3:251) | the six engineering defaults the coordinator accepted on 2026-10-09: full nesting; unarmed fold is no evidence; inert = gap > shortest hold (60 s); P4 `—` on a dropped armed ledger rule (superseded by decision 70); throttle onset bound stays v2.4's; `appear` unarmed on a stream with records, class-independent calibration | a list that points at rows 1.4, 1.5, 1.6, 3.3, 3.4, 4.2 and 7.1; each is counted there |
| `V3_REPORT_LIST_MAX` = 40 (P3:358) | the markdown readout prints at most 40 items of a long list; the JSON keeps every item | display only |

## 11. Group 10: placement step and campaign C test scoring (decisions 71-91; outside the registry)

These are not parameters of the frozen reader. They are listed because the placement objective and its costs are downstream of
v3.1 and were decided after campaign B and A2 cells had been read under the frozen reader (`readouts: OTel `0a8517a`,
Hotel `3d6bf3b`, 2026-10-10T15:23; TeaStore `19bd343`, 2026-10-11T04:40). v2.4 has no placement step in its registry; the
placement was deferred by decision 29 (PD:302). Sources for these rows are the protocol draft and `PLACEMENT_V3_DESIGN.md`; I did not
re-verify the placement code or its numbers.

| # | item | v2.4 | after v3.1 | decision, commit | triggering observation | foreseeable? | informed by |
|---|---|---|---|---|---|---|---|
| 10.1 | CELF sensor cost | not present | the honest nested per-sensor rate is the cost (67 pt 1; DES:95-96); a sensor with no held-out evidence at 3/T (71, PD:473); amended to every sensor at its honest 95 % upper bound and no-evidence sensors at the rate's largest evidenced bound (73, PD:482) | 67, 71 (round 20), 73 (round 21, 2026-10-10) | v3.1 readouts show cost `—` for sensors with no evaluated fold once A2 is pooled (PD:473); `PLACEMENT_V3_DESIGN.md:235-242`: literal costing makes "no evidence cost less than thin evidence" | **partly.** A per-sensor false-alarm cost was in the literature note before the freeze (LIT:128-129, D29: sum of per-sensor rates <= rho); the `—` and the inversion come from the v3.1 evaluated-fold rule (1.5, F2). | T |
| 10.2 | false-alarm budget in the placement | not present | a Pareto sweep over the cost budget, with 6/h named as the false-alarm budget (the number of decision 48); a knapsack budget is a constraint, not a term in the objective, so decision 64 holds | 76 (PD:489), 85 (PD:522) | `PLACEMENT_V3_DESIGN.md:231-234` (D-p2) | **yes.** 6/h is decision 48 (PD:359, 2026-10-04); the constraint form is D29 (LIT:128) and SYN:95-98 kept it a user decision. | H |
| 10.3 | by-construction catches in the objective | BC flags reported apart (decision 11, PD:214; protocol :104-105) | BC counts for the ledger E only; a sensor's BC catch is a miss; BC-for-all and BC-miss-for-all as arms (72, 84) | 72 (PD:480), 84 (PD:520), 2026-10-10 and 2026-10-11 | `PLACEMENT_V3_DESIGN.md:259-268`: clean E catches OTel 0/32 episodes, Hotel 19/48; PD:478-479: "D-p7 was decided after its counts were seen" | **partly.** The BC flags and the choice to report with and without BC predate the freeze; that the fixed ledger is vacuous on OTel was first visible after B was read. Outcome-informed by the record's own statement, not outcome-blind. | T |
| 10.4 | OTel's role | OTel was the test system (train TeaStore + Hotel, test OTel, hold-out Online Boutique, user 2026-09-15; LIT:268 item 4) | OTel relabelled a training system for the placement step; the clean test is campaign C (74, 82) | 74 (PD:485), 82 (PD:506) | `PLACEMENT_V3_DESIGN.md:243-253`: the coordinator read the OTel primary readout in full on 2026-10-10, including P4 folds with per-episode sensor-vs-ledger times | **yes.** SYN:99-101 (2026-10-05): "a setting changed after OTel's fault cells were read ends OTel's role as a test ... any change now makes this round exploratory on all three systems"; LIT:268 says the same. v3's design of 2026-10-09 was such a change. | T |
| 10.5 | scoring placements by restriction of `full` cells | not present | declared deviation from protocol section 3 (:102); decision 46.3's live run of the placement is the later check | 80 (PD:495) | `PLACEMENT_V3_DESIGN.md:276-281`: the posture-leak check cannot run on all-`full` cells | **yes.** `DECLARATION.md:32-33` already calls restriction an approximation and every sweep cell is `full` by design (decision 16, PD:259). | H |
| 10.6 | reporting and ablation choices | not present | ablations by modality and quiet-time curve (81, PD:500); held-out headline only at named budgets (85); tie-margin arm deferred (86); cardinality view k = 1..19 (87); tolerant tie comparison and shared budget-knot grid (`346482a`) | 81 (round 22), 85-87 (round 24) | Fable review of the placement code `ed25107` (PD:519) and the ablation proposals | **no.** Findings on new code and new proposals after the freeze. | T |
| 10.7 | campaign C test scoring | not present | frozen v3.1 on the training campaigns plus a fault-only view of C, C's full campaign as `--validation`; scorer `score_test_v3.py`; pass rule: at OTel r0.2 the frozen 6/h set `span:frontend:GET` passes if g_C > 0 and it improves at least 2 of C's 3 CPU-throttle episodes; elsewhere no verdict; `—` if the set member is absent or fewer than 3 episodes (88-91) | 88-89 (`bffb3a0` 2026-10-11T14:01), 90-91 (round 26), scorer frozen `1a8d924` 16:44 | `research/protocol/TEST_SCORING_C_DRAFT.md`: predictions frozen from the training held-out results (`378e598`) | **no.** A new procedure created after the freeze for a campaign that did not yet exist. Outcome-blind with respect to C by commit order (all before `720957c`); informed by training results (the OTel r0.2 prediction of 19.4 s comes from them). | T |

Group 10 tally (7 rows): yes 3 (10.2, 10.4, 10.5), partly 2 (10.1, 10.3), no 2 (10.6, 10.7).
Decisions 75, 77, 78, 79 (rates, impact, comparators, own sensors) restore or implement protocol text (protocol :101, decisions
11, 14, 15) and are not counted as deviations; I did not audit that reading.

## 12. What did not change

Of the 77 v2.4 registry entries (P24, counted with `uv run python`): 6 are replaced as v3's primary by rows above (`K_FIT_UNIT`,
`FAR_TARGET_PER_HOUR`, `FAR_MEETS_CRITERION`, `ABSENT_GAP_MULT`, `CALIBRATION_SET_RULE`, `P4_NOT_EVALUABLE_RULE`; S3's docstring says v2.4's
family table is still printed beside v3's, computed in process); 1 is narrowed (`SCALE_NOT_ESTIMABLE_RULE`, row 2.4); 4 were already inactive
(`TAU`, `SYS_FLOORS` superseded; `FAULT_DOSE_CPU_THROTTLE`, `FAULT_DOSE_NET_DELAY` not-used-by-v2). The other 66 are not
replaced or narrowed by any v3 registry entry or decision text I found. S3's docstring lists them as UNCHANGED in kind: the readers,
pooled baselines (H1), `K_REFERENCE`, `K_GRID`, `MAD_SCALE`, `FLOOR_REL_PRIMARY` / `FLOOR_REL_ARM`, `RESOLUTION_RULE`, `MIN_BASELINE_POOLED`
= 20, `FAR_CONFIDENCE`, the episode window and probe rules, decisions 51, 54, 57, 58, 60 (same-request and onset rules), event time as
primary, P1, P2, P3, exposure. I did not re-verify that v3 reads each of the 66 unchanged.

## 13. Forking-paths exposure, stated plainly

1. **All of v3 followed the v2.4 readouts.** The synthesis that triggered it (SYN, `aaef8cc`, 2026-10-05T13:38) was written from
   fault-outcome tables (P1 to P4) and no-fault alarm counts of all three systems. The v3 design (`252cfcd`) is dated 2026-10-09, four days later.
   The v3 script's own docstring labels every existing cell "EXPLORATORY and NOT FROZEN. Every existing cell of Hotel, TeaStore and
   OTel was read under v2.4 before v3 was written" (S3 docstring, line 18).
2. **Motivation by an unevaluable verdict.** The change was driven by P4 being `—` on 2026-10-05 (SYN:23, SYN:29-31). Changing the
   analysis until a declared prediction becomes evaluable is a forking path even when the changes do not target its direction. Part of
   the `—` was independent (one episode per (fault, rate), SYN:13-14), which row 4.3 notes.
3. **v3 itself was iterated four times on the same exploratory cells before freeze.** Each system has readouts at v3 (`26f16ff`), fix1 (`908302b`),
   fix2 and fix3 (`0b23efe`, `7ec9f28`): directories `readout-{hotel-r3-quiet,teastore-r2,otel-r1}-v3`, `-v3-fix1`, `-v3-fix2`, `-v3-fix3`; each
   committed unedited before reading, each informing the next build (for example row 1.6 was found on OTel data between the first and second).
4. **A fault-outcome observation shaped one v3 arm** (row 4.4: OTel, 4 of 8 episodes caught only by a dropped rule). It is reported as
   "optimistic bound (not evidence)" and is never primary (P3:173).
5. **Pre-specification holds for later data only.** `990d501` froze v3.1 "before any campaign B or A2 cell is read"; B and A2 were first read
   under it on 2026-10-10T15:23. After that, decisions 71-87 were taken with B and A2 results visible, and the record says so for D-p7
   (`PLACEMENT_V3_DESIGN.md:259-268`) and for OTel's role (10.3, 10.4). Campaign C is the first data of which the frozen
   reader's row 8.4 and the frozen placements and scorer (`378e598`, `1a8d924`) were fixed before any cell was read; decision 92 is the only
   change to the frozen reader's inputs after `990d501`, and it is outcome-blind by commit order (row 8.4, with the unverified residual stated there).
6. **Not tried.** The unit left at "family" with only a quantile fallback (SYN option 1 and 4 combined), and a K grid extended past 100,
   were not run; no result exists for them (`—`). The v2.4 family table is printed beside v3's, so the unit change has a printed
   comparison on the existing cells.

## 14. Rows I could not fully source, and other caveats

- **Row 4.2 and rows 1.5, 2.5:** the independent v3.1 review reports (findings F1 to F4, and the earlier feasibility review of 2026-10-09) are not
  committed as files. Their content reaches this record only through DES:76-109, PD round 19, the freeze message of `990d501`, and the registry
  `origin_ref` texts (P3:55, P3:149, P3:157, P3:350). Whether F4 was informed by P4 outcomes is `—`. The feasibility scripts and outputs are in
  gitignored `tmp/v3review/` (`v3_feasibility.py`, `*.json`); I did not re-run them.
- **Row 6.3:** only rate 1 was read from the primary readouts; the other three rates and the exact v2.4 hours per system (SYN:34 gives 0.55 / 0.70)
  were not recomputed. The TeaStore 26-cell figure includes the stopped A2 attempt's valid cells (readout `campaignsRead`), not a clean 4 + 10 + 10.
- **Timing of quiet run A against the freeze:** Hotel's 40 cells were complete about 2026-10-04T11:10Z, 14 hours before `891a4c3` (NS:575-577). For TeaStore and OTel
  NS:585-586 records completion at about 2026-10-05T01:20Z against a freeze at 01:07Z; the order is not established (`—`).
- **Rows citing documents I did not open in full:** `DECLARATION_B_TEASTORE_DRAFT.md`, `DECLARATION_B_OTEL_DRAFT.md` (cited through P3:141 and P3:221),
  `OTEL_LOST_BATCH_DIAGNOSIS.md`, `PLACEMENT_V3_DESIGN.md` beyond lines 205-290, `TEST_SCORING_C_DRAFT.md` beyond its first 60 lines.
- **Foreseeable verdicts are judgements.** Where I wrote why a change was missed, I marked it "recorded" (a cited sentence says so) or "writer's reading"
  (inference). No row has an independent review.
- **Out of scope:** the campaign C result itself (decision 89 outcome) and what any v3 number means. This record says what changed and what could have been
  known, not whether v3 is better.

## 15. Commands run for this record

- `uv run python` over `research/protocol/parameters.json` (77 entries; status counts 73 / 2 / 2) and `parameters_v3.json` (32 entries; names, values, origin refs).
- `shasum -a 256` on the four working-tree files above; `git show 7ec9f28:research/protocol/parameters_v3.json | shasum -a 256`;
  `git log --format='%h %ad %s' --date=iso-strict` on `research/protocol`, `research/traffic-sweep` and the two scripts;
  `git show fdbdb16 -- research/protocol/parameters_v3.json`; `git diff --stat 7ec9f28 HEAD -- research/detection-time/sweep_analysis_v3.py`.
- `/usr/bin/grep -n` on the protocol draft, LIT, MH, SYN, DES, NS, the two C declarations and `BUDGET_C.md` for the cited lines.
- `uv run python` reading `research/traffic-sweep/readout-{hotel,teastore,otel}-primary-v3.1/sweep_analysis_v3.json` for `calibration.primary.perRate["1"]` cells and hours, `bFreshCheckLimit`, `campaignsRead`.
- Row counts and registry coverage in section 1 are checked by a script over this file (section 16 states its result).

## 16. Self-check result

Run after the last edit (`uv run python`, a script over this file's table rows and over `parameters_v3.json`): all 32 registry names occur in this file; 34 rows in groups 1-8 with verdicts yes 16, partly 13, no 5 (per group as in section 1); Informed-by tags T 17, H 16, OB 1; group 10 has 7 rows, yes 3, partly 2, no 2; every markdown table has a constant cell count. This checks internal consistency only. It does not check that a cited line says what the row says; line cites were taken from `grep -n` / `sed -n` output during writing and the ones that were off by one were corrected, but no second pass was made on every cite.
