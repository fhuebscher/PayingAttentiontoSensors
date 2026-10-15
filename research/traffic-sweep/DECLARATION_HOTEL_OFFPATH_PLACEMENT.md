# Hotel off-path placement test (R3, second run of `hotel-offpath-v1`, the declared negative control): declaration (2026-10-15)

**Status: committed alone, before the launch below.** Budget amendment `BUDGET_TS_PLACEMENT_20261015_AMENDMENT1.md` (`369b18c`, item R3).
`DECLARATION_HOTEL_OFFPATH.md` (`4945293`) stays binding for the design. Analysis frozen before launch: `research/protocol/FREEZE_V37_20261015.md` (`0cede5c`;
code `779959e`). Scope: instance (fb14srv4).
## What it is
A fresh run of the unchanged epoch: harness `9ad0b98`, plan `90b7b621c8a1e54a92a78f813bb9c73ee829eddf4ef615e8806edd50d1df2f2a` (same seed, order and onsets as the
first run; new cells, a new timestamped campaign ID), 30 cells: 5 blocks x rates 10 and 1 req/s x {no-fault, consul pause (off path), search pause (on-path
control)}. DRY_RUN `off2dry` passed 2026-10-15 07:50:29Z (srv4 0 containers, 172 GB free, invariants match). Only this run's fetch is read.
## Question and rule (V37_PASS_RULE in `parameters_v3_7.json`, digest in FREEZE_V37)
As R1, for `consul-pause-effect` at rate 10 and at rate 1 separately: trained on blocks 1-3, scored on 4-5; frontier any/any @6/T_r passes iff g > 0 and >= 2 of
2 test episodes strictly improved; dash rules as F; decision 73 unchanged; consul's own sensors excluded for its class. Search pause carries no verdict.
## Predictions (committed here, before launch). INFORMED BY SEEN DATA:
the v3.7 dry run on the first run (already read; post hoc, no verdict) failed both rates (rate 1: empty set, g = 0; rate 10: `span:rate:/rate.Rate/GetRates`, 1 of 2).
No coordinator observes consul and there is no queue, so a PASS would suggest a false pass of the rule, not a detection lane.
| id | prediction |
|---|---|
| HO2-V | not PASS at either rate (FAIL or dash) |
| HO2-L | the ledger alone detects at most 1 of the 4 off-path test episodes |
| HO2-C | search pause: the ledger detects 4 of 4 test episodes |
## Notes
- The budget amendment's "v3.6 layer (Hotel admission)" is the v3.7 layer: v3.6 was frozen for TeaStore alone and v3.7 adds Hotel on v3.4 (FREEZE_V37).
- The epoch descriptor carries `analysis.placementVerdict: null`; the authority for R3's verdict is the budget amendment (`369b18c`), this declaration and
  `V37_PASS_RULE` (registry digest in FREEZE_V37).
- Power: T_r = 0.15 h per rate, so the zero-alarm floor is about 19.97/h and 6/T_r = 40/h buys at most about two sensors; a FAIL is weak evidence.
- Same plan as the first run (same seed, order and onsets): before any value is read, check that `campaignsRead` is this run's fetch only and that the
  readout's `provenance.input.sha256` is not the first run's (`5c8e5013…`). Readouts are made at a HEAD at or after `0cede5c`. Do not quote the readout's
  `v32.edgesDeclaredNotObserved` / `offPathClasses` / `v33.epochsAddedByV33` fields (inherited OTel or v3.3 bookkeeping, review N2).
## Review
v3.7 same-provider adversarial review: **GO** (2026-10-15 ~08:05Z; dry run reproduced byte-identically; dropped v3.4 refusal justified for this
epoch only, review N1). Fetch named `off2-fetch`.
## Launch
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
HOTEL_ROOT=$PWD/../observability-placement-runtime-hotel-protocol COMPILER=candidate_offpath.py \
  EXPECTED_PLAN=90b7b621c8a1e54a92a78f813bb9c73ee829eddf4ef615e8806edd50d1df2f2a RUN_COUNT=30 \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_hotel.sh off2 > scratchpad/gate-drivers/hotel-off2.out 2>&1 &
```
At most 1 relaunch, harness or infrastructure defects only, starting no later than 13:00Z. Fetch case added after launch, keyed by the new campaign ID.
