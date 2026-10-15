# TeaStore campaign C, relaunch 1: declaration (frozen 2026-10-11)

**Status: frozen** by committing this file alone, before the launch below. `DECLARATION_C_TEASTORE.md` (frozen `cd747c7`)
stays binding for everything not changed here. Budget `BUDGET_C.md` (`d5b9af0`): terminal by **2026-10-12 12:00Z**; at
most 2 relaunches (**this is relaunch 1 of 2**); 3 critical-path harness defects stop TeaStore (**0 of 3 used**). Scope of
every number: instance (one SUT, one host, fb14srv5).

## Why
The launch of 2026-10-11 00:47Z (setup ID `d8cac67e766ce920d8edb1c17650df8a`) stopped at its 2nd cell
(`no-fault-cost/r10/b01`, journal sequence 1): `ControllerError: candidate cell executor failed: RuntimeError: TeaStore
readiness failed`; supervisor `abstained`, rc 2; 1 cell valid (`auth-freeze-effect/r0p05/b01`). Blocked evidence:
`runs/no-fault-cost/b01-02-full.blocked-evidence/.operational/` (fetched: `tmp/teastorec1-evidence`, 60/60 byte-verified).
Signature: every service registered with the registry (registry.log: auth, image, persistence, recommender, webui, once
each), but webui's `ServiceLoadBalancer` logged "No Server registered" for image (3) and persistence (2) until readiness
timed out: the same signature as quiet run A2's stop at cell 18 (`DECLARATION_QUIET_A2_TEASTORE_RELAUNCH1.md`).
**Classification (coordinator):** a TeaStore startup race in its registry client, a SUT flake, not a harness defect;
not counted toward the 3-defect rule. It is now **a recurring class** (2 occurrences in about 95 TeaStore cells since
2026-10-09): recorded as a ledger row (registry-client load-balancer refresh at startup), not fixed under this budget.

## What differs from the stopped attempt
Nothing in the harness, plan or descriptor: harness `3b4a513ff3c4b00b65131dbc82ba1b472d1c0548` (tracked tree clean), plan
`e55b4f59e3ff8895b3f7d44d89114436fae89b6096fc7d6204d9e0579872eb29` (36 cells), the same run IDs; the gate chain mints a
new setup ID, so every host path is new and no path collides (as for A2 relaunch 1). SETUP-CAMPAIGN live, `invariants
match=True`. Launcher label `c1r1`; DRY_RUN `c1r1dry1` passed 02:03:09Z (`scratchpad/gate-drivers/teastore-c1r1dry1-launch.log`).

## Which cells the test scores (declared before any C cell is read)
The placement test scores **relaunch 1's cells**. The stopped attempt's one valid cell is preserved and flagged but not
scored, because relaunch 1 re-measures the same plan cell (same run ID); scoring both would count one episode twice.
Pooling, where any, keys on the campaign directory (V3_POOL_KEY_RULE).

## Launch
```
W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
cd $M
TEASTORE_ROOT=$W EXPECTED_HEAD=3b4a513ff3c4b00b65131dbc82ba1b472d1c0548 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_sweep_c.py EXPECTED_PLAN=e55b4f59e3ff8895b3f7d44d89114436fae89b6096fc7d6204d9e0579872eb29 RUN_COUNT=36 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh c1r1 > $M/scratchpad/gate-drivers/teastore-c1r1.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow teastore-c1r1 scratchpad/gate-drivers/teastore-c1r1-launch.log \
  > scratchpad/gate-drivers/teastore-c1r1-wandb.out 2>&1 &
```
After terminal: fetch to a new path (`tmp/teastorec1r1-evidence`), byte-verify, read cell validity only (BUDGET_C rule 4).
