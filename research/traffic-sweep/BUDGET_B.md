# Budget and stop rule: campaign B (repeat episodes on TeaStore and OTel), 2026-10-09

Committed alone, before any B work. Design from `NEXT_CAMPAIGNS_PROPOSAL.md` §B and protocol decision 49: 3 more blocks
per system (3 regimes × 4 rates × 3 = 36 cells), on a harness with **H10** (no readiness probe during the fault) and
**H4** (record the freeze: Docker events for `pause`, command-return stamps for throttle).

## Why a new budget
`BUDGET_CALIBRATION.md` set B's harness deadline to 2026-10-06 12:00Z and its terminal deadline to 2026-10-08 12:00Z.
Both passed with no B work started: the session stopped on 2026-10-05 waiting for the v3 calibration decision
(`SYNTHESIS_V2_4.md`). Under its stop rule 1 that drops B unless the user extends. The user did on 2026-10-09 ("continue
with the progress of today and catch up with all tasks from this week ... the 3 servers free").

## Budget
- Harness ready per system (epoch commit, tests incl. a planted defect per change, offline replay, re-pin, DRY_RUN on
  the host): **2026-10-10 12:00Z**.
- Campaign terminal per system: **2026-10-12 12:00Z**.
- At most **2 relaunches** per system. TeaStore on fb14srv5, OTel on fb14srv6, one campaign per host.

## Stop rules
1. A system not launch-ready by its deadline is dropped from B; the reason is recorded. No extension without the user.
2. A critical-path defect gets 30 minutes; **3 critical-path harness defects in one system: stop that system and ask.**
3. Launch only from a declaration committed alone plus a passing DRY_RUN on the host, mirrored to wandb.
4. **No B evidence is analysed until analysis v3 is frozen and reviewed.** B is the first data read under v3.

## Confirmation (user, 2026-10-09 ~10:45Z)
"ignore the expired deadline and extend it to 12th and continue with all tasks within the deadline". The deadlines above
stand as written; nothing else changes.
