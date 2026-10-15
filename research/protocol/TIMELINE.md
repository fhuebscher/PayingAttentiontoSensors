# Commit-time timeline of the preregistration chain (C, E, F, TeaStore off-path, ontology)

Written 2026-10-14 for the BenchSOC draft (`papers/current/benchsoc/paper.tex`, artifact pointer). Every time is UTC. Commit times
come from `TZ=UTC git log --format='%h %ad' --date=format-local:'%Y-%m-%d %H:%M:%SZ' -- <file>` (first commit of the file, or the
commit that added the named decision, found with `git log -S'<decision heading>' -- research/PROTOCOL_DRAFT_20261002.md`). Launch
times come from the first line of the launcher log `scratchpad/gate-drivers/<label>-launch.log`, which prints the time of day
only; its date is taken from the surrounding commits and the declarations' own text (marked *log*). Nothing here was read from raw
cell evidence. A row's order is what matters: a rule committed after launch is marked **after launch**.

## Campaign C (OTel and TeaStore, placement test)

| step | commit / source | time (UTC) |
|---|---|---|
| budget and stop rule `BUDGET_C.md` | `d5b9af0` | 2026-10-10 17:41:52Z |
| declarations `DECLARATION_C_OTEL.md`, `DECLARATION_C_TEASTORE.md` | `56006b9`, `cd747c7` | 2026-10-11 00:46:25Z |
| launch, OTel and TeaStore (labels `c1`) | *log* `otel-repeat-c-c1-launch.log`, `teastore-c1-launch.log` | 2026-10-11 00:47:36Z |
| TeaStore relaunch 1 declaration `DECLARATION_C_TEASTORE_RELAUNCH1.md` | `6d2ecc8` | 2026-10-11 02:03:37Z |
| TeaStore relaunch 1 launch (`c1r1`) | *log* `teastore-c1r1-launch.log` | 2026-10-11 02:03:37Z (same second as its declaration) |
| decision 89 (C pass rule, sign rule) | `73a32d0` | 2026-10-11 04:14:56Z **after launch** |
| test scorer frozen (decision 88) | `1a8d924` | 2026-10-11 05:44:49Z |
| decision 92 (C epochs admitted to the frozen reader) | `fdbdb16` | 2026-10-12 00:44:18Z |
| C readouts committed unedited before reading | `720957c` | 2026-10-12 00:54:40Z |
| result `RESULT_C.md` | `ae6608f` | 2026-10-12 00:57:19Z |

## Campaign E (OTel off-path)

| step | commit / source | time (UTC) |
|---|---|---|
| budget `BUDGET_E.md` | `ec4b9fa` | 2026-10-12 05:42:01Z |
| decision 99 (E pass rule) | `80152db` | 2026-10-12 06:47:32Z |
| decision 110 (verdict set at 3/T_r) | `f60e7fb` | 2026-10-13 03:35:48Z |
| declaration `DECLARATION_E_OTEL.md` | `49e47a1` | 2026-10-13 03:36:56Z |
| launch (`e1`) | *log* `otel-offpath-e-v1-e1-launch.log` | 2026-10-13 03:37:40Z |
| decision 112 (verdict set at 6/T_r, recurrence rule) | `eebcbf2` | 2026-10-13 05:14:48Z **after launch** |
| declaration amendment 1 (decision 112) | `c785354` | 2026-10-13 05:32:47Z |
| freeze v3.2, step 1 | `05f70d4` | 2026-10-13 05:50:55Z |
| training readout | `a4ce818` | 2026-10-13 05:53:42Z |
| freeze v3.2, step 2 (placement pinned) | `40209da` | 2026-10-13 05:54:02Z |
| scoring readout and scorer output, unedited before reading | `e2cbc74` | 2026-10-13 05:56:53Z |
| result `RESULT_E.md` | `115abdc` | 2026-10-13 05:59:01Z |

## Campaign F (OTel off-path, detection lanes)

| step | commit / source | time (UTC) |
|---|---|---|
| budget `BUDGET_F.md` | `db3be09` | 2026-10-13 13:28:20Z |
| declaration `DECLARATION_F_OTEL.md` | `8845721` | 2026-10-14 00:21:08Z |
| launch (`f1`) | *log* `otel-offpath-f-v1-f1-launch.log` | 2026-10-14 00:21:21Z |
| freeze v3.3, step 1 | `6efd378` | 2026-10-14 00:33:05Z |
| post hoc script digest recorded (`posthoc_lanes_v33.py`, `55b00eb`) | `acdfe9b` | 2026-10-14 01:04:46Z |
| training readout | `49d0265` | 2026-10-14 03:48:05Z |
| freeze step 2 (placement pinned) | `bf8e24c` | 2026-10-14 03:52:28Z |
| scorer output, unedited before reading | `a6a4dbb` | 2026-10-14 03:57:34Z |
| post hoc script changed once (recorded deviation, placement-pin waiver) | `6a42206` | 2026-10-14 04:00:16Z **after the scorer output was read and after TeaStore launched** |
| result `RESULT_F.md` | `a54e1ef` | 2026-10-14 04:03:19Z |

## TeaStore off-path (recommender pause; no placement verdict)

| step | commit / source | time (UTC) |
|---|---|---|
| budget `BUDGET_TEASTORE_OFFPATH.md` | `ebf345a` | 2026-10-13 13:28:20Z |
| declaration `DECLARATION_TEASTORE_OFFPATH.md` | `f40e786` | 2026-10-13 23:07:02Z |
| attempt 1 launch (`o1`; stopped at cell 3) | *log* `teastore-o1-launch.log` | 2026-10-13 23:50:57Z |
| relaunch 1 declaration `DECLARATION_TEASTORE_OFFPATH_RELAUNCH1.md` | `3dd0221` | 2026-10-14 00:25:27Z |
| relaunch 1 launch (`o1r1`) | *log* `teastore-o1r1-launch.log` | 2026-10-14 00:25:27Z (same second as its declaration) |
| freeze v3.3 (same record as F) | `6efd378` | 2026-10-14 00:33:05Z |
| readout committed unedited before reading | `b6d8690` | 2026-10-14 04:30:48Z |
| result `RESULT_TS_OFFPATH.md` | `a9fbf13` | 2026-10-14 04:32:35Z |

## Ontology extraction (every comparison post hoc)

| step | commit | time (UTC) |
|---|---|---|
| `EXTRACTION_PROTOCOL.md` first in git (inside a concurrent commit), then recorded alone | `14a72c7`, `3b8c20f` | 2026-10-14 03:54:54Z, 03:55:25Z |
| amendment 1 (builder defaults, before stage 2) | `0cc4e7e` | 2026-10-14 04:34:43Z |
| amendment 2 (rule-derived facts, after run1's stage 4 was refused) | `21f2830` | 2026-10-14 06:23:48Z |
| run1b predictions, then comparison | `0523282`, `d943c02` | 2026-10-14 06:31:31Z, 06:34:04Z |
| amendment 3 (library module, identifier keys; after run1b's comparison) | `5d5028e` | 2026-10-14 06:51:25Z |
| run2 predictions, then comparison | `f8cfd23`, `d451530` | 2026-10-14 07:20:05Z, 07:21:30Z |

Every campaign above was read (F scorer output 03:57Z, TeaStore readout 04:30Z) before the ontology's stage 2 ran.

## Overnight runs (added 2026-10-15; same sources and method)

Launch and terminal times are the first line and the `TERMINAL` line of `scratchpad/gate-drivers/<label>-launch.log` (time of day; dates from the log
file's mtime and the surrounding commits). Predictions `research/protocol/PREDICTIONS_OVERNIGHT_20261014.md/.json` (`8b89d43`, 2026-10-14 14:49:53Z).

### TeaStore off-path replication 1 and its relaunch (stopped; 25 valid cells preserved, not read)

| step | commit / source | time (UTC) |
|---|---|---|
| budget `BUDGET_REPLICATION_20261014.md` | `0b70303` | 2026-10-14 06:52:51Z |
| declaration `DECLARATION_TEASTORE_OFFPATH_REP1.md` | `256ae13` | 2026-10-14 06:54:20Z |
| launch (`rep1`) | *log* `teastore-rep1-launch.log` | 2026-10-14 06:54:20Z (same second as its declaration) |
| terminal: stopped (9 journal rows) | *log* | 2026-10-14 08:17:15Z |
| relaunch declaration `DECLARATION_TEASTORE_OFFPATH_REP1_RELAUNCH1.md` | `3760a6c` | 2026-10-14 08:21:14Z |
| relaunch launch (`rep1r1`) | *log* `teastore-rep1r1-launch.log` | 2026-10-14 08:21:16Z |
| terminal: stopped (18 journal rows) | *log* | 2026-10-14 10:25:15Z |
| stop record `STOP_TEASTORE_OFFPATH_REP1.md` | `03e7cd6` | 2026-10-14 10:30:45Z |

### TeaStore off-path replication 2 (barrier-fixed harness 04254228)

| step | commit / source | time (UTC) |
|---|---|---|
| budget `BUDGET_OVERNIGHT_20261014.md` | `cf50078` | 2026-10-14 14:40:58Z |
| predictions TSR-* | `8b89d43` | 2026-10-14 14:49:53Z |
| declaration `DECLARATION_TEASTORE_OFFPATH_REP2.md` | `5b9236f` | 2026-10-14 15:05:58Z |
| launch (`rep2`) | *log* `teastore-rep2-launch.log` | 2026-10-14 15:06:00Z |
| reader: frozen v3.3 (`6efd378`, unchanged) | `6efd378` | 2026-10-14 00:33:05Z |
| terminal: complete, 30 rows | *log* | 2026-10-14 18:31:31Z |
| readout committed unedited before reading | `cde33b9` | 2026-10-14 23:12:09Z |
| predictions scored | `75326e3` | 2026-10-14 23:14:14Z |

### Hotel off-path (consul pause, declared negative control)

| step | commit / source | time (UTC) |
|---|---|---|
| budget `BUDGET_OVERNIGHT_20261014.md` (item 4) | `cf50078` | 2026-10-14 14:40:58Z |
| predictions HO-* | `8b89d43` | 2026-10-14 14:49:53Z |
| declaration `DECLARATION_HOTEL_OFFPATH.md` | `4945293` | 2026-10-14 22:58:15Z |
| launch (`off1`) | *log* `hotel-off1-launch.log` | 2026-10-14 22:58:17Z |
| freeze v3.4 | `380b5b6` | 2026-10-14 23:52:17Z (after launch, before any cell was read) |
| terminal | *log* | 2026-10-15 01:09:33Z |
| readout committed unedited before reading | `3ac90e8` | 2026-10-15 01:24:27Z |
| HO-* scored | `03a5f44` | 2026-10-15 01:24:34Z |

### OTel F replication (attempts 2 and 3; frozen v3.3)

| step | commit / source | time (UTC) |
|---|---|---|
| budget `BUDGET_REPLICATION_20261014.md`, amendment 1 | `0b70303`, `208f076` | 2026-10-14 06:52:51Z, 14:27:57Z |
| declaration `DECLARATION_F_OTEL_REP1.md` (attempt 2) | `d0ef902` | 2026-10-14 14:28:46Z |
| attempt 2 launch (`f2`) | *log* `otel-offpath-f-v1-f2-launch.log` | 2026-10-14 14:28:48Z |
| attempt 2 terminal: stopped (at cell 13, per the relaunch declaration) | *log* | 2026-10-14 15:45:21Z |
| predictions for F replicates | `8b89d43` | 2026-10-14 14:49:53Z (after attempt 2 launched, before attempt 3) |
| relaunch declaration `DECLARATION_F_OTEL_REP1_RELAUNCH1.md` (attempt 3) | `7f4382e` | 2026-10-14 23:18:56Z |
| attempt 3 launch (`f3`) | *log* `otel-offpath-f-v1-f3-launch.log` | 2026-10-14 23:18:58Z |
| attempt 3 terminal | *log* | 2026-10-15 01:51:25Z |

### OTel F no-lag ablation (`otel-offpath-f-nolag-v1`)

| step | commit / source | time (UTC) |
|---|---|---|
| budget `BUDGET_OVERNIGHT_20261014.md` (item 2) | `cf50078` | 2026-10-14 14:40:58Z |
| prediction rows for the ablation | `8b89d43` | 2026-10-14 14:49:53Z |
| freeze v3.5 | `0be6dc2` | 2026-10-15 01:50:36Z |
| declaration `DECLARATION_F_NOLAG_OTEL.md` | `14af489` | 2026-10-15 01:53:25Z |
| launch (`nl1`) | *log* `otel-offpath-f-nolag-nl1-launch.log` | 2026-10-15 01:53:27Z |
| terminal | — (running at the time of writing; the last log line, 02:22:08Z, reads not terminal) | — |
