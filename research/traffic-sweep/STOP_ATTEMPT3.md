# Hotel traffic sweep: relaunch 2 stopped, stop rule reached (2026-10-03, ~12:40Z)

`BUDGET.md` rule 4 (at most 2 relaunches) is reached; no further relaunch without the user.

## What happened
- Campaign `hotel-v1-20261003t111746z-cc971de7` (harness 7a1d97b, plan 766063c5, amendment 1): 11:17-12:20Z, **15 of 64
  cells attempted, 14 sealed, 14 valid**. Cell 15 `rate-net-delay-effect-r10-b01-full-a01` raised in run-cell
  `native trace lacks a required same-trace service edge`; the controller aborted (ABSTAINED).
- Diagnosis (read-only, capture level, counts only; no detection result computed): 1,803 traces with a frontend root;
  **10 lack the `search → rate` edge, all with a ledger start inside the fault window**; their other spans (frontend,
  search, geo, profile, reservation) are present. The rate span of those requests was never reported.
- Rule that fired: `witness/candidate_evidence.py:686-691` — "Degradations are not an absence: during-fault traces keep
  the normal path ground truth, and no truncation is excused" (only pauses get a during-window policy).
- Not deterministic: attempt 2 sealed the identical cell (same run ID, plan, onset) valid
  (`tmp/hotel6-evidence/hotel-v1-20261003t050738z-29661565.tgz`).
- Cause of the missing rate spans: `?` (not established). Candidates: search's call to rate cancelled before rate
  starts its span; rate's span report (UDP to the Jaeger agent, through the delayed interface) lost.

## Evidence on hand (all plan 766063c5, valid)
- Attempt 2: cells 1-25 (harness 9ed8863). Relaunch 2: cells 1-14 (harness 7a1d97b), a same-plan repeat of attempt 2's
  first 14. The two harness commits differ only in how `application.log` is decoded.
- Archive of relaunch 2: to be fetched into `tmp/hotel6-evidence/` before anything moves on srv4.
