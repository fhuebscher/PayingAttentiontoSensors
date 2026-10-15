# Budget and stop rule: overnight runs R5 (TeaStore) and R6 (OTel F design), 2026-10-15 (committed alone, before either declaration)

Asked by the author 2026-10-15 ~13:50Z ("any last set of campaigns to run overnight"; chose TeaStore on srv5 and OTel F design on srv6; srv4 stays idle).
Paper deadline 2026-10-16 11:59Z. Scope of every result: instance.

## Runs
- **R5, TeaStore, fb14srv5:** R1's plan (`5a8e385e…`, harness `04254228`, `DECLARATION_TEASTORE_OFFPATH_PLACEMENT.md` binding for design and pass rule) on new cells, at a
  fresh attempt whose run IDs collide with no earlier attempt (checked before the declaration is committed).
- **R6, OTel, fb14srv6:** F's plan (harness `715d57b`, `DECLARATION_F_OTEL.md` binding) on new cells, at a fresh attempt with no run-ID collision (attempt 7 stays
  reserved for R4's relaunch), launched only after R4 is terminal and fetched byte-verified.

## Analysis (each run alone, nothing pooled)
1. **Replicate of the rule:** the run's own frozen chain exactly as its original (R5: v3.6, as R1; R6: v3.3, as F, its rerun and R2): train blocks 1-3, CELF,
   placement pinned by a recorded override (the `score_rep` pattern, no frozen file edited), score blocks 4-5, the original pass rule.
2. **Transfer of the frozen sets (declared here, post hoc to the sets themselves):** on the run's own scoring readout, per test episode the earliest counted fire of
   each earlier frozen set's members versus the ledger alone (improved iff strictly earlier; a ledger miss charged the hold), in the pass rule's form (>= 2 of 2
   per class). R5: R1's sets (1 req/s, 10 req/s). R6: F's {lag}, F rerun's {purgatory.size}, R2's {lag, flagd impression}. The selection is frozen; thresholds come
   from the new run's own training calibration. One script for both, committed with a test before either fetch is read; the test must reproduce the scorer's own
   episode outcomes for the run's own placement.

## Gates and stop rules
- Each launch needs: this budget and its declaration (with predictions) each committed alone, one same-provider review GO of the declaration, a passed DRY_RUN on the
  host, and the host idle by the host. R5 launches by 16:00Z, R6 by 18:00Z; otherwise that run does not happen (a stop note records it).
- At most 1 relaunch per run, for harness or infrastructure defects only, within 1 h of the stop; a second stop ends that run with a stop note.
- Earlier evidence on a host is moved (never deleted) to a dated archive only after its fetch is byte-verified.
- A result enters the paper only after its result note has one same-provider review, by 2026-10-16 06:00Z; after that, one sentence without numbers or nothing.
  A result that needs more than 3 net lines replaces text rather than overflowing p.12.
