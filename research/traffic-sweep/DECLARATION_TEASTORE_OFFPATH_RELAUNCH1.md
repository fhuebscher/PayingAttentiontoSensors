# TeaStore off-path pause (recommender), relaunch 1: declaration (2026-10-14)

**Status: committed alone, before the launch below.** `DECLARATION_TEASTORE_OFFPATH.md` (`f40e786`) stays binding for everything not changed here.
Budget `BUDGET_TEASTORE_OFFPATH.md` (`ebf345a`, amendment 1 `b7f6bf5`): at most 1 relaunch, harness or infrastructure defects only (**this is it**); terminal
and fetched by 2026-10-15 12:00Z. Scope of every number: instance (fb14srv5).

## Why
Attempt 1 (launcher `o1`, setup ID `c88ed29d91c6e8e889c0dd0f54157089`, launched 2026-10-13 23:50:58Z, host unit 00:01:34Z) stopped at its 3rd cell
(`no-fault-cost/r10/b01`, journal row 3) at 00:17:32Z: `ControllerError: candidate cell executor failed: RuntimeError: TeaStore readiness failed`;
`campaign-abort.json` stage cell-execution, `experimentalState` ABSTAINED, 2 cells valid (`auth-freeze-effect/r1/b01`, `recommender-pause-effect/r1/b01`).
Fetched read-only: `tmp/teastore-offpath-evidence/o1-fetch2`, 82/82 byte-verified (an earlier empty `o1-fetch` directory from a wrong-shell invocation is
kept, not reused). Signature, from the blocked cell's `.operational/` logs only: the stack was freshly brought up for the cell (`up.log`), every service
registered with the registry once (auth, image, persistence, recommender, webui), the recommender finished training, and webui's `ServiceLoadBalancer`
logged "No Server registered" for image (3) and persistence (2) until readiness timed out. This is the signature of campaign C's first stop (also
`no-fault-cost/r10/b01`, `DECLARATION_C_TEASTORE_RELAUNCH1.md`) and of quiet run A2's stop at cell 18.
**Classification (coordinator):** the recurring TeaStore registry-client startup race, a SUT flake, not a harness defect and not an after-effect of the
previous cell's recommender pause (the stack is rebuilt per cell); 3 occurrences in about 125 TeaStore cells since 2026-10-09. Not counted toward the
3-defect rule. The ledger row stands; not fixed under this budget.

## What differs from attempt 1
Nothing in the harness, plan or descriptor: harness `f74b29b92de283878ca50ea4ab2a5e1beb74eef7` (tracked tree clean), plan
`5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a` (30 cells), the same run IDs; the gate chain mints a new setup ID, so every host path is
new. Launcher label `o1r1`; DRY_RUN `o1r1dry1` passed 2026-10-14 00:25:15Z (all guards, SETUP-CAMPAIGN live, invariants match=True, srv5 0 containers, 357 GB free).

## Which cells are read (declared before any cell of this epoch is read)
The readout reads **relaunch 1's cells only**. Attempt 1's two valid cells are preserved and flagged but not read: relaunch 1 re-measures the same plan
cells (same run IDs), and reading both would count one episode twice.

## Launch
```
W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
cd $M
DRY_RUN=1 TEASTORE_ROOT=$W EXPECTED_HEAD=f74b29b92de283878ca50ea4ab2a5e1beb74eef7 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_offpath_ts.py EXPECTED_PLAN=5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a RUN_COUNT=30 \
  zsh scratchpad/gate-drivers/launch_teastore.sh o1r1dry1
TEASTORE_ROOT=$W EXPECTED_HEAD=f74b29b92de283878ca50ea4ab2a5e1beb74eef7 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_offpath_ts.py EXPECTED_PLAN=5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a RUN_COUNT=30 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh o1r1 > $M/scratchpad/gate-drivers/teastore-o1r1.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow teastore-offpath-v1-o1r1 scratchpad/gate-drivers/teastore-o1r1-launch.log \
  > scratchpad/gate-drivers/teastore-o1r1-wandb.out 2>&1 &
```
If relaunch 1 stops again, there is no further relaunch: TeaStore then contributes the cells it completed, reported as such, or stays on-path only
(budget stop rule 1).
