# Budget and stop rule: placement test runs (campaign C on TeaStore and OTel; Online Boutique), 2026-10-10

Committed alone, before any C or Online Boutique work. Authority: protocol decision 82 (round 22) and D-p4 / decision 74.
These runs exist to test the frozen placement: their fault cells are read only through the frozen placement
(`research/protocol/BUDGET_PLACEMENT.md` step 6), never to tune it.

## Campaign C (TeaStore on fb14srv5, OTel on fb14srv6)
- Shape: campaign B's (3 blocks x 3 regimes x 4 rates = 36 cells per system, H10 and H4 as in B; OTel collector log
  sampling off, decision 66), new blocks and run IDs, a new study epoch; nothing else changes. Its no-fault cells are a
  second fresh false-alarm check (never pooled into a calibration).
- Harness ready (epoch commit, tests incl. a planted defect per change, re-pin, DRY_RUN): **2026-10-11 12:00Z**.
- Terminal and fetched: **2026-10-12 12:00Z**. At most 2 relaunches per system.

## Online Boutique (held-out system; fb14srv4 unless its harness binds another host)
- A held-out test of the frozen **procedure** (calibration v3.1, placement design, budgets), never tuned on Online
  Boutique: its own sweep (fault and no-fault cells) and quiet calibration cells, placement chosen and scored held-out by
  block within Online Boutique. Shape follows the traffic sweep and quiet runs (DECLARATION.md, DECLARATION_QUIET_*.md);
  the exact cells go in its declaration.
- Harness admitted (existing worktree `observability-placement-ob-successor`, ledger `research/OB_HARNESS_LEDGER_20260923.md`)
  and launch-ready: **2026-10-11 18:00Z**. Terminal and fetched: **2026-10-12 12:00Z**.

## Stop rules
1. A system not launch-ready by its deadline stops; the reason is recorded and the user is asked. No extension without
   the user.
2. A critical-path defect gets 30 minutes; 3 critical-path harness defects in one system: stop that system and ask.
3. Launch only from a declaration committed alone plus a passing DRY_RUN on the host, mirrored to wandb. One campaign per
   host.
4. No C or Online Boutique cell is read (validity fields only) before the placement is frozen.
