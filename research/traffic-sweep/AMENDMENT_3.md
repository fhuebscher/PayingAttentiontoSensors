# Traffic-sweep pilot, amendment 3 (FROZEN 2026-10-03, committed alone, before any result is looked at)

Amends `research/traffic-sweep/DECLARATION.md` (a795fc9) as amended by `AMENDMENT_1.md` and `AMENDMENT_2.md`. Analysis
only; harness, descriptor and plan unchanged. No sweep result has been computed or looked at.

User decision (2026-10-03, "go for recommended scope and content"), on the two open points of
`ANALYSIS_EXTENSION_NOTES.md` after the Fable review of the analysis extension (da6c002 → ca380a4):

1. **Probe-window exclusion, primary = `scope`.** The declared rule ("every sensor sample or record inside a probe window
   is not scored", DECLARATION.md "Analysis definitions") is narrowed in scope to the channels the fault adapter's probe
   request can touch while it hangs: logs and metrics of `frontend` and of the fault target; spans of probe requests are
   excluded by token as before. Records of every other service inside the window are scored. Reason: under search-pause
   the during-probe window spans ≈ [applied + 0.25, applied + 5.3] s at every rate, so the declared rule decides P4a at
   10 and 1/s and P3 by construction (review M1, from `faults/compose_pause.py:54-62, 173-187`). The declared rule
   (`declared`) and no exclusion (`none`) are reported beside it; a verdict that differs from `none` is printed "decided
   by the probe rule".
2. **Caller-span by-construction flag, primary = `content`.** "Flagged by content (the record names the callee)"
   (DECLARATION.md) is applied to caller spans under every fault class, not only pauses (dbebcbb's kind rule). The `kind`
   variant is reported beside it (round-4 item 2 asks for both).

Implementation: `PRIMARY_PROBE = "scope"`, `PRIMARY_CALLER_SPAN = "content"` in `research/detection-time/sweep_analysis.py`
(next commit; tests unchanged, every variant is computed regardless).
