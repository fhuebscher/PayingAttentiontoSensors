# Detector sweep: plan and stop rules (frozen 2026-09-24, before the sweep runs)

User decision 2026-09-24: "strengthen first". This answers the judge's surviving objection that one
configuration per detector is a detector result, not a family property (`DETECTION_RESULT.md`,
`eval_74d0a1b8…`). Committed alone. Population, windows and parsers are exactly as in
`DETECTION_DEFINITIONS.md` plus A1.

## Grid (every cell of it is reported; nothing is selected after the fact)

- **Metric:** k ∈ {3, 4, 5, 6} × absolute floor ∈ {0.5, 1, 2} percentage points = 12 configurations.
  Each is reported per regime and per service (all 10 Hotel services separately, target included),
  with detections / 72 and false alarms / 72. The union of the 9 non-target services is also reported, as before.
- **Log level threshold:** {warn and above, error and above}, on Hotel and TeaStore.
- **Log, per emitting service:** for every detection, the service whose line fired, per regime.
  This answers which service reported the fault, with no attribution claim.
- **Episode-level agreement across postures:** for each (run, block), the none / sample-zero / full
  cells of one regime are three episodes under matched conditions. Per detector: the number of
  (run, block) groups, of 24, in which all three postures agree (all detect or none does).
- **Traces (full only):** per service, error spans in the window.

## Stop rules

- The full grid is the result. No "best" configuration is named. A sentence may only describe
  the whole grid (for example "in all 12 configurations" or "in n of 12").
- Nothing new is added after the sweep has been seen. A defect in the sweep code gets fixed and
  disclosed; a new detector does not.
- Budget: 3 h including the re-judge. At 4.5 h, stop and ship the discussion-paragraph option.
- One re-judge per sentence, with the grid as the evidence and full counts included (the missing
  evidence in `eval_097bf4e8…` and `eval_2e2ebc72…` was my omission). If a sentence is refuted again,
  it is dropped, and the fallback is the discussion paragraph with the counts.
- The go/no-go at Sun 27 18:00Z is unchanged.
