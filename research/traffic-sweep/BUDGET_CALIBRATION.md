# Quiet calibration run (A) and repeat episodes (B): budget and stop rule (committed alone, before the work; 2026-10-04)

User decisions 48-50 (`research/PROTOCOL_DRAFT_20261002.md` round 10). Template: `BUDGET_REPLICATION.md`.

## Scope
| | A: quiet calibration | B: repeat episodes |
|---|---|---|
| systems | Hotel (fb14srv4), TeaStore (fb14srv5), OTel (fb14srv6) | TeaStore, OTel |
| cells | 40 no-fault cells per system (10 per rate × 4 rates), sweep cell shape | 3 blocks × 3 regimes × 4 rates = 36 per system |
| harness | the system's sweep epoch, no-fault regime only; no change to cell shape | H10 (no readiness probe during the fault) + H4 (stamp when the fault command returns) |
| declaration | one per system, committed alone before its first cell | one per system, committed alone before its first cell |

## Budget
- **A:** launch-ready by **2026-10-05 12:00Z** per system; campaign terminal by **2026-10-06 12:00Z**.
- **B:** harness ready (tests, replay, DRY_RUN) by **2026-10-06 12:00Z**; campaign terminal by **2026-10-08 12:00Z**.
- At most **2 relaunches** per campaign.
- One campaign per host at a time. TeaStore's A and B start only after TeaStore sweep relaunch 2 is terminal; its
  worktree is the live ROOT until then.

## Stop rules
1. A system not launch-ready by its deadline is dropped from that part; the reason is recorded. No extension without
   the user.
2. A defect on the critical path gets 30 minutes. **3 critical-path harness defects in one system for A or B: stop that
   system and ask.**
3. Launches follow `CLAUDE.md`: frozen declaration, passing DRY_RUN, wandb mirror.
4. No analysis of A or B evidence until analysis v2 is frozen (`METHODOLOGY_HARDENING.md` §4).
