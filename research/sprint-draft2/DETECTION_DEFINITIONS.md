# Detection definitions for draft 2 (frozen 2026-09-24, before any detection count)

Addendum to `research/SPRINT_DRAFT2_20260924.md` (D-S2, D-S3), committed alone before the script runs.
The inventory (`INVENTORY.md`) changed one premise: **metrics inside a fault window exist only for
Hotel**. TeaStore's fault cells are `resourceUse: diagnostic-only` (no samples), and Online Boutique
has no fault regime. So the two-family go/no-go can only be met on Hotel; TeaStore contributes a log
family only.

**Disclosed prior look.** Before these definitions were written, one Hotel fault cell was inspected by
hand (run 7fd8717d, reservation-pause b03 full): reservation CPU read 0.0 in all 5 in-window samples,
and frontend logged `ERR services/frontend/server.go:271` lines throughout the window. One TeaStore
`auth.log` and one `persistence.log` were read for their layout only. No other fault-cell value was read.

## Population

- **Hotel.** Campaign #6, runs 3–6 (`969a1362`, `a8e7e72e`, `88b7bf7c`, `7fd8717d`): the paper's
  population for the Hotel cost result. Plan `ac60dbbc…`; cells with `candidateCellValid: true`
  (all 216). Episodes: `reservation-pause` and `search-pause`, 4 runs × 6 blocks × 3 postures = 72
  each. False-alarm set: the 72 `no-fault-cost` cells. Run `210a480a` is left out, as in the paper.
- **TeaStore.** `teastore-e3-user-a5` (the only campaign whose fault cells retain log content, with
  its own no-fault cells): the cells in `campaign-terminal-validation.json` `validCells`, expected 12
  `auth-freeze-effect`, 12 `persistence-crash-effect`, 12 `no-fault-cost`. Only each cell's own top-level
  `auth.log`/`persistence.log` is read, never the `.operational` dumps (blocked cells and re-runs only).
  The inventory's "receipt only" for no-fault cells is wrong: all 12 retain both files.

## Windows

- Hotel episode window W = [`startedAt`, `endedAt`] from `fault-receipt.json`. Log lines carry
  1-second timestamps; a line at second t is in W if floor(start) ≤ t ≤ end.
- Hotel false-alarm pseudo-window, per no-fault cell: [t0 + 45 s, t0 + 60 s], where t0 is the
  first `cpu.json` sample and 45 s / 15 s are the fault's `scheduledAtSeconds` / `requestedOutageSeconds`.
- TeaStore: native log lines carry no timestamp, so **TeaStore log detection is cell-level**
  (one episode per fault cell), not window-level. It is labelled that way wherever it appears.

## Families

**Log (Hotel).** `application.log` is the docker compose stream: `<service>-<n> | <payload>`. The
payload is parsed by zerolog's two output layouts, not by patterns over message text: a JSON object
(`level`, `time`, `message`, optional `caller`), or the ConsoleWriter layout, which after stripping
ECMA-48 SGR sequences is `<RFC3339 time> <LVL> <caller> > <message>`. A line matching neither layout
is kept and counted as *unparsed*. It cannot be placed in a window, so its count is reported and it
takes no part in window detection. Template = (service, level, caller), or (service, level, message)
for a JSON line with no caller. Two detectors, reported separately and as their union:
- *level*: a line in W at zerolog level warn, error, fatal or panic;
- *novelty*: a line in W whose template occurs in no no-fault cell of the same run (unmatched
  scores higher; nothing is dropped).

**Log (TeaStore).** `auth.log` and `persistence.log`, log4j pattern layout `[<thread>] <LEVEL> <logger> - <message>`.
Harness witness lines (`OBSERVABILITY_*` messages) are harness output, not application logs, and are
excluded. Template = (file, level, logger). A line matching no layout is *unparsed* and, because
there is no window, counts toward novelty. The same two detectors apply at cell level, with novelty
measured against the 12 no-fault cells.

**Metric (Hotel only).** `cpu.json`, per-service CPU percent. Per cell and service s: baseline
median m_s and robust scale σ_s = 1.4826 · MAD over the samples before W (or before the
pseudo-window). An event is a sample in W with |x − m_s| ≥ 4 σ_s and |x − m_s| ≥ 1 percentage point.
The parameters (k = 4, 1 pp floor) are fixed here, not fitted. No-fault cells give the false-alarm
rate. The family is reported in three parts: *target* (the faulted service's own CPU), *other*
(any other service) and their union.

**Trace (Hotel).** A span in `traces-normalized.json` that starts in W and carries an error mark. It
is reported next to the other families only as a reference. Under `none` and `sample-zero` no spans
are exported, so the trace family's zero there is **true by construction**, not a result.

## What is reported

Per SUT, regime, posture and family: episodes detected / episodes, the false alarms / no-fault cells
for the same detector, detection latency (first event − window start: median [min, max]), and the
per-episode family overlap (which combinations detected). Instance scope. No intervals, no p-values.

## Caveats fixed in advance

- A paused container reports 0 % CPU, so the *target* metric detector is close to true by
  construction for pause faults. The *other* part (the load on other services changes) is the
  non-trivial metric signal.
- TeaStore has no metric family in fault windows (`—`, by harness design), and its log detection is
  cell-level.
- Hotel runs are not independent of posture order, host (fb14srv4 only) or workload. Instance scope.

## Amendment A1 (2026-09-24, after the first Hotel run; post hoc, disclosed)

The frozen parser left about 8.5k of about 24k lines per Hotel cell unparsed. By structure, not by
content, they are (a) harness span-witness lines (`OBSPLACEMENT_EMISSION {…}`, the harness's own
output) and (b) Go's standard `log` package layout, `2006/01/02 15:04:05 <msg>` (container clock UTC,
checked against the same cell's `cpu.json` epochs), which gRPC's default logger writes with a
severity prefix `INFO: ` / `WARNING: ` / `ERROR: ` / `FATAL: `. The frozen result is the primary
result. A1 is reported beside it as a **post-hoc sensitivity**, because it was written after the
frozen counts were seen (search-pause: log 0/72).
- Harness span-witness lines are excluded from the unparsed count; they were never windowed.
- Go `log` lines are parsed by that layout. Level = the gRPC severity prefix if present, else `info`
  (the package has no levels). Template = (service, level, `go-log`), because the layout has no
  caller field. Their novelty detector is therefore coarse, and the level detector carries them.
- Nothing else changes: windows, k, the population and the metric and trace families are as frozen.
