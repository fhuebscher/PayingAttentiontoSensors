# OTel quiet calibration run (A), attempt 1: stop record (2026-10-04)

Campaign `otel-quiet-calibration-v1`, harness `6e37ec2`, plan `5cec5a69…`, fb14srv6, 09:12-09:58Z. Scope: instance.

## What happened
- `remote-terminal.json`: attemptedCells 8, validCells 7, stopped true (the declared rule: the campaign stops on the
  first invalid cell).
- The invalid cell is `calibration/r10-b02-04-full` (no fault, 10/s). Error: `trace completeness: 50 incomplete of 1800
  successful requests outside the fault-and-drain window exceeds the allowance 18` (decision 25, rule ii).
- The other 7 cells are valid, with 0 incomplete traces each: r10 b01, r1 b01/b02, r0.2 b01/b02, r0.05 b01/b02.

## Diagnosis (read-only on srv6, ~25 min, within the 30-minute rule)
- **The 50 incomplete requests are one contiguous block,** scheduled 134.9-139.8 s into the measurement: exactly 5 s
  at 10/s. All of them succeeded.
- **Only one service's spans are missing.** Each of the 50 traces has frontend and frontendproxy spans but no
  productcatalogservice span. Complete traces have all three.
- **No error in any log.** productcatalogservice logs nothing about export failure; `otelcol.log` shows no exporter or
  queue error, only a `httpcheck` DNS error metric.
- **The capture shows no gap.** In `telemetry.pcap` (OTLP to :4317), every source sending at ≤ 5 s cadence has bytes
  in every 5 s bin of the cell.
- **Conclusion (probable, not proven):** productcatalogservice exported, and one 5 s batch of its spans was lost
  between the collector receiving it and the trace carrier we parse (the collector's debug exporter, written to stdout
  and captured as `otelcol.log`). The other reading, an SDK batch drop with a retry inside the same bin, was not ruled
  out. Proving which one needs decoding the OTLP payloads in the pcap; not done.

## Why it matters beyond this cell
- A quiet run exists to calibrate false alarms. A lost batch of one service's spans is exactly what makes an `absent`
  rule fire on a healthy system.
- Blocking such cells removes the data the run is meant to measure.
- At 10/s, 1 of 2 quiet cells hit it so far (0 of 4 r10 cells in the sweep's relaunch 1).

## Budget
- This is OTel A's **1st** critical-path stop (`BUDGET_CALIBRATION.md`: 3 → stop). 2 relaunches remain.
- The 7 valid cells are kept, not pooled with a relaunch.
- Evidence: still on srv6, not yet fetched.
