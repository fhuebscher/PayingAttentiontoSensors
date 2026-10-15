# TeaStore off-path placement test (R1, replication 3 of `teastore-offpath-v1`): declaration (2026-10-15)

**Status: committed alone, before the launch below.** Budget `BUDGET_TS_PLACEMENT_20261015.md` (`2501e86`). `DECLARATION_TEASTORE_OFFPATH.md` (`f40e786`) and
`_REP2.md` (`5b9236f`) stay binding for the design. Analysis frozen before launch: `research/protocol/FREEZE_V36_20261015.md` (`975b7a1`; code `6698351`).
Scope: instance (fb14srv5).
## What it is
A fresh run of the unchanged epoch: harness `04254228` (barrier-fixed), plan `5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a` and descriptor
`127e8263…` as replication 2 (same seed, order and onsets; new cells), 30 cells: 5 blocks x rates 10 and 1 req/s x {no-fault, recommender pause (off path),
auth freeze (on-path control)}. DRY_RUN `rep3dry` passed 2026-10-15 07:14:30Z (srv5 0 containers, 352 GB free, invariants match). Only this run's fetch is read.
## Question and rule (V36_PASS_RULE in `parameters_v3_6.json`, digest in FREEZE_V36)
Trained on blocks 1-3 of this run, scored on blocks 4-5: for the recommender pause at rate 10 and at rate 1 separately, the frontier (effort<=any, runtime<=any)
set @6/T_r passes iff g > 0 and it strictly improves on the ledger in >= 2 of 2 test episodes; dash if fewer than 2 valid test episodes or a member is absent;
decision 73 unchanged; the recommender's own sensors excluded for its class; by-construction fires count for the ledger only. Auth freeze carries no verdict.
TeaStore has no declared tier file, so every candidate is tier-missing and only the any/any cell is defined (engineering default, FREEZE_V36).
## Predictions (committed here, before launch). They are INFORMED BY SEEN DATA:
the v3.6 dry run on replication 2 (already read; post hoc, no verdict) chose `log:webui:d4d75ec135e6` (webui's Ribbon "current list of Servers=[]" line, itself
found post hoc in the review of relaunch 1) at both rates, priced 19.97/h under 6/T_r = 40/h, and passed both rates. This run therefore tests whether a placement
frozen on fresh training blocks repeats that on fresh test blocks; it is not a blind test of the sensor.
| id | prediction |
|---|---|
| TS3-V | PASS at rate 10 and at rate 1 |
| TS3-S | the frozen @6/T_r set at both rates is `log:webui:d4d75ec135e6` alone |
| TS3-T | the set's first counted fire (scorer field `ttd`, seconds after the fault onset stamp) is 9-15 s in 4 of 4 off-path test episodes |
| TS3-L | the ledger alone misses 4 of 4 off-path test episodes |
| TS3-C | auth freeze: the ledger detects 4 of 4 test episodes |
## Reading a PASS
The dry run's sensor also fires in auth-freeze episodes (16-31 s): it is a service-discovery signal on the login route. By decision 111's reading
a PASS says which lane sees this fault and when, not that the method generalises. The effort/runtime axes carry no information here (all candidates
tier-missing); cite the scorer output's `inputs.passRuleSource` (its header text says V32_PASS_RULE, inherited).
## Review
v3.6 same-provider adversarial review: **GO** (2026-10-15 ~07:55Z); its N1 (step-2 pin breaks two tests) fixed in `0c706cb`, recorded in FREEZE_V36
(`fbcabc4`). Fetch named `rep3-fetch` (not `r1-fetch`, which is relaunch 1); `campaignsRead` must list one campaign.
## Launch
```
W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
cd $M
TEASTORE_ROOT=$W EXPECTED_HEAD=04254228aba90566dfeca603dfcc7b05b7d8d2e3 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_offpath_ts.py EXPECTED_PLAN=5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a RUN_COUNT=30 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh rep3 > $M/scratchpad/gate-drivers/teastore-rep3.out 2>&1 &
```
At most 1 relaunch, harness or infrastructure defects only, starting no later than 12:30Z. Fetch case added after launch, keyed by the new setup ID.
