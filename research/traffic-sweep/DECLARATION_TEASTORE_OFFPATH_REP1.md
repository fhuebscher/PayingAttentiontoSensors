# TeaStore off-path pause (recommender), replication 1: declaration (2026-10-14)

**Status: committed alone, before the launch below.** `DECLARATION_TEASTORE_OFFPATH.md` (`f40e786`) stays binding for everything not changed here (design,
regimes, predictions T-L1, T-L2, T-OFF, T-C with their thresholds, evidence handling). Budget `BUDGET_REPLICATION_20261014.md` (`0b70303`). Scope:
instance (fb14srv5).
- Same harness `f74b29b92de283878ca50ea4ab2a5e1beb74eef7` (tracked tree clean), same plan `5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a`
  (30 cells), same run IDs; the gate chain mints a new setup ID, so every host path is new. Launcher label `rep1`; DRY_RUN `rep1dry` passed 2026-10-14
  06:53:53Z (all guards, SETUP-CAMPAIGN live, invariants match=True, srv5 0 containers, 355 GB free).
- **Which cells are read:** this replicate's cells only, in one readout of its own fetch (its setup ID checked first, FREEZE_V33 addendum condition 1);
  relaunch 1's readout and verdicts are not changed and not pooled with it. Predictions are scored on its 10 recommender-pause episodes with the same
  post hoc script (`posthoc_lanes_v33.py`, digest `b203c2c3…`). T-L2 is expected in the by-construction field (`BC-caller-log`, content rule).
- Fetch to `tmp/teastore-offpath-evidence/rep1-fetch` (new case in `fetch_overnight.sh` once the setup ID is known), byte-verified; per-cell offline replay
  as for relaunch 1 (`replay_ts_r1.py`; the campaign-level byte-exact replay is blocked by host-path embedding, as recorded).
## Launch
```
W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
cd $M
TEASTORE_ROOT=$W EXPECTED_HEAD=f74b29b92de283878ca50ea4ab2a5e1beb74eef7 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_offpath_ts.py EXPECTED_PLAN=5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a RUN_COUNT=30 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh rep1 > $M/scratchpad/gate-drivers/teastore-rep1.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow teastore-offpath-v1-rep1 scratchpad/gate-drivers/teastore-rep1-launch.log \
  > scratchpad/gate-drivers/teastore-rep1-wandb.out 2>&1 &
```
At most 1 relaunch, harness or infrastructure defects only (the registry-client readiness race counts as infrastructure, as in relaunch 1).
