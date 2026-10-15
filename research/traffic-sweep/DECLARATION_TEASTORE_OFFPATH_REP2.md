# TeaStore off-path pause (recommender), replication 2 on the barrier-fixed harness: declaration (2026-10-14)

**Status: committed alone, before the launch below.** `DECLARATION_TEASTORE_OFFPATH.md` (`f40e786`) stays binding for everything not changed here (design,
regimes, predictions T-L1, T-L2, T-OFF, T-C). Budget `BUDGET_OVERNIGHT_20261014.md` (`cf50078`, item 3). Predictions for this run, committed before
launch: `research/protocol/PREDICTIONS_OVERNIGHT_20261014.md` (`8b89d43`, ids TSR-*). Scope: instance (fb14srv5).
## What changed
Harness `04254228aba90566dfeca603dfcc7b05b7d8d2e3` = `f74b29b` + the Kieker-queue barrier fix (`7596980`, tests `04254228`): the barrier
**acknowledgement** re-queries the Kieker queue every 1 s until it reads empty, starting no probe that would complete later than 5 s after the barrier
(the frozen srv5 acknowledgement deadline); every probe is recorded in `queue-proof.json` (`measurement.barrierProbes`); a queue still non-empty at
the bound stops the campaign as before. This is a bounded wait **after** the barrier, not a drain before it: the blocked cells show the queue empty
before the barrier and the workload's first record in flight at the acknowledgement (+0.015 s query, read 1 message; a depth read at +1.3 s read 0).
Records are assigned to the window by their own timestamps, so the window, barrier lead and collector duration are unchanged. Independent same-provider
review: GO (non-blocking: the probe validator checks consumers on the final probe only; `queueMessagesAtBarrier` now means "at the acknowledging probe",
up to ~4 s after the barrier; residual stop risk estimated ~3 % per 30-cell campaign, an estimate). Plan `5a8e385e…` and descriptor `127e8263…` unchanged.
DRY_RUN `rep2dry` passed 2026-10-14 15:05:36Z (all guards, invariants match=True, srv5 353 GB free).
## Which cells are read
This run's cells only (one readout of its own fetch, setup ID checked first). The two stopped replication attempts stay unread. At most 1 relaunch.
## Launch
```
W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
cd $M
TEASTORE_ROOT=$W EXPECTED_HEAD=04254228aba90566dfeca603dfcc7b05b7d8d2e3 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_offpath_ts.py EXPECTED_PLAN=5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a RUN_COUNT=30 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh rep2 > $M/scratchpad/gate-drivers/teastore-rep2.out 2>&1 &
```
