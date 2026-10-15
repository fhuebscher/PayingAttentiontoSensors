# R1 (TeaStore off-path placement test), relaunch 1: stop note and declaration (2026-10-15 ~09:30Z)

**Status: committed alone, before the relaunch below.** `DECLARATION_TEASTORE_OFFPATH_PLACEMENT.md` (`42c04f3`) stays binding for everything (design, rule,
predictions TS3-*, frozen v3.6 chain). Budget `BUDGET_TS_PLACEMENT_20261015.md` (`2501e86`): at most 1 relaunch, harness or infrastructure defects only, starting
by 12:30Z; **this is it**. Scope: instance (fb14srv5).
## Why (stop)
Attempt (setup `416ea06f6b87f7ba0291fd2823c83d53`, launched 08:13:47Z) stopped at 08:49:05Z after 5 valid cells: cell 6,
`teastore-offpath-v1/recommender-pause-effect/r10/b01/full/a01`, raised `ControllerError: candidate cell executor failed: WitnessError: journey is outside
measurement window: journey-e87b795d…` (`campaign-abort.json`: stage cell-execution, validCells 5, retryAllowed false). The check is
`modules/teastore/witness/extract_app_witness.py:318-319` (every journey's startedAt..endedAt must lie inside the receipt's measurement wall-clock bounds).
**Classification:** a harness/timing defect of the witness (one journey of a 10 req/s recommender-pause cell crossed a window bound), not a fault of the SUT
or a design change; its exact cause is **not established** (time-boxed; the cell's evidence is kept on the host and is not read). The same check passed in
60 of 60 cells of relaunch 1 and replication 2 (both 30/30 valid). No harness change: relaunch on `04254228`, plan `5a8e385e…` unchanged. The stopped
attempt's 5 valid cells are preserved and not read; only the relaunch's fetch is read.
## Relaunch
New setup ID (the launcher archives the stopped run state first). DRY_RUN `rep3r1dry` before launch. Fetch case `teastorerep3r1`, path
`tmp/teastore-offpath-evidence/rep3r1-fetch`. If the relaunch also stops, R1 is reported as not run to completion (no further relaunch).
```
W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
cd $M
TEASTORE_ROOT=$W EXPECTED_HEAD=04254228aba90566dfeca603dfcc7b05b7d8d2e3 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_offpath_ts.py EXPECTED_PLAN=5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a RUN_COUNT=30 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh rep3r1 > $M/scratchpad/gate-drivers/teastore-rep3r1.out 2>&1 &
```
