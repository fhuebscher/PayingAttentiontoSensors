# TeaStore off-path replication 1, relaunch 1: declaration (2026-10-14)

**Status: committed alone, before the launch below.** `DECLARATION_TEASTORE_OFFPATH_REP1.md` (`256ae13`) and `DECLARATION_TEASTORE_OFFPATH.md` (`f40e786`)
stay binding for everything not changed here. Budget `BUDGET_REPLICATION_20261014.md` (`0b70303`): at most 1 relaunch, harness or infrastructure defects
only (**this is it**); terminal and fetched by 14:00Z. Scope: instance (fb14srv5).
## Why
Replication 1 (launcher `rep1`, setup ID `887a7838e73019806ed39607be69992f`, launched 06:54:22Z) stopped at its 9th cell (`recommender-pause-effect/r10/b02`)
at 08:15:06Z: `ControllerError: candidate cell executor failed: RuntimeError: candidate queue was non-empty at the measurement barrier`; 8 cells valid.
Fetched read-only to `tmp/teastore-offpath-evidence/rep1-fetch`, 298/298 byte-verified. The blocked cell's `queue-proof.json` shows the Kieker queue with
1 message and 1 consumer at the barrier. **Classification (coordinator):** the recurring Kieker-queue race at the measurement barrier (one record in flight),
an infrastructure flake, not a harness defect; 2nd occurrence (1st: TeaStore #19, auth-freeze b01, `research/NEXT_STEPS_20260925.md:486`). Ledger row
stands; not fixed under this budget.
## What differs
Nothing: harness `f74b29b92de283878ca50ea4ab2a5e1beb74eef7`, plan `5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a` (30 cells), same run
IDs, new setup ID. Launcher label `rep1r1`; DRY_RUN `rep1r1dry` passed 08:20:49Z (all guards, invariants match=True, srv5 354 GB free).
## Which cells are read
This relaunch's cells only (one readout of its own fetch, setup ID checked first). Replication 1's 8 valid cells are preserved and flagged, not read.
If this relaunch stops again, there is no further relaunch; TeaStore keeps relaunch 1's result without replication.
## Launch
```
W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
cd $M
TEASTORE_ROOT=$W EXPECTED_HEAD=f74b29b92de283878ca50ea4ab2a5e1beb74eef7 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_offpath_ts.py EXPECTED_PLAN=5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a RUN_COUNT=30 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh rep1r1 > $M/scratchpad/gate-drivers/teastore-rep1r1.out 2>&1 &
```
