# Budget amendment 1 to `BUDGET_OVERNIGHT_20261015.md` (`bfc9417`): evidence identity for R5 (TeaStore), 2026-10-15 ~14:05Z (committed alone)

**Why.** The budget asks R5 to run "at a fresh attempt whose run IDs collide with no earlier attempt". TeaStore's off-path compiler
(`modules/teastore/execution/candidate_offpath_ts.py` at `04254228`) has no attempt or seed parameter: every run of plan `5a8e385e…` has the same 30 run IDs
(`teastore-offpath-v1/<regime>/r<rate>/b0N/full/a01`, `runKey.attempt` 1). Replication 2, R1 and R1's relaunch already reused them. Making them distinct needs a
harness commit, which would invalidate the plan and the frozen chain's binding to it. Found by the cross-provider pre-launch review of the R5 declaration
(`eval_5a2ea355…`, gpt-6.1-sol, refuted on this point alone).

**Change (R5 only; R6 keeps the run-ID rule).** R5's evidence is identified by **(setup ID, run ID)**, not by run ID alone, as for R1's relaunch and the Hotel
runs: the setup ID is new at launch (the launcher archives the previous run state first), the fetch reads only `<results>/<new setup ID>/`, the fetch path is new
(`tmp/teastore-offpath-evidence/r5-fetch`), and the offline replay asserts the campaign ID. Both readouts must list exactly that one fetch in `campaignsRead`, and
neither may be a byte copy of an earlier run's readout. Everything else in the budget is unchanged.
