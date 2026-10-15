# Budget and stop rule: TeaStore off-path pause (recommender), 2026-10-13

Committed alone, before any work on it. Authority: user, 2026-10-13 ~13:40Z, choosing "Yes" for the TeaStore off-path pause on
the plan `research/PLAN_LANES_20261014.md` (`c2914de`). Hotel's consul control is deferred (same decision). Scope of every number:
instance (TeaStore on fb14srv5). Paper deadline 2026-10-16 11:59Z.

## What it is
A new epoch (`teastore-offpath-v1`): pause `recommender`, which is not on the login route (route services webui, auth,
persistence, image). Regimes: no-fault, recommender pause, auth freeze as the on-path control. Lanes measured: coordinator side
(registry heartbeat removal; alive window 10 s, `HeartbeatInfo.java:32`) and own silence (cgroup CPU of the paused container).
Rate(s), blocks and cell count are engineering defaults set in the declaration, sized so the run ends by its deadline.

## Sequence and deadlines (UTC)
1. Harness: pause target parameterised, epoch module, tests with a planted defect per change: **2026-10-14 00:00Z**.
2. Independent review GO; per-lane predictions in a declaration committed alone; DRY_RUN passed: **2026-10-14 03:00Z**.
3. Launch by **2026-10-14 03:30Z**; terminal and fetched (byte-verified) **2026-10-14 12:00Z**. At most 1 relaunch, harness or
   infrastructure defects only.
4. Read only under reader v3.3 frozen before any cell of this epoch is read (`BUDGET_F.md` step 4): **2026-10-14 08:00Z**.
5. Readout committed unedited before reading: **2026-10-14 16:00Z**.

## Stop rules
1. A missed deadline stops that step; TeaStore then stays on-path only in the paper. No extension without the user.
2. 30 minutes per critical-path defect; 3 critical-path harness defects stop it.
3. Launch only from a declaration committed alone plus a passing DRY_RUN, mirrored to wandb; one campaign per host (srv5).
4. If the recommender pause turns on-path (the registry drops it and webui calls fail), that is reported as observed, not hidden.

## Amendment 1 (user, 2026-10-13 ~23:45Z, committed alone)
The coordinator's VPN dropped (~23:00Z) before this epoch's DRY_RUN. The user reconnected the VPN and **extended every deadline above by one day** (harness
2026-10-15 00:00Z; review, declaration, DRY_RUN 03:00Z; launch by 03:30Z; terminal and fetched 12:00Z; reader v3.3 frozen 08:00Z; readout 16:00Z, all
2026-10-15), and asked to rerun. Stop rules unchanged. The paper deadline (2026-10-16 11:59Z) is unchanged.
