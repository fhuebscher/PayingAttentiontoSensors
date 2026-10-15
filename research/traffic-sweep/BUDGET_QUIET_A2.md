# Budget and stop rule: second quiet calibration run A2 (decision 68), 2026-10-09

Committed alone, before any A2 work. 40 no-fault cells per system, the same cell shape, rates and posture as quiet run
A (`DECLARATION_QUIET_{HOTEL,TEASTORE,OTEL}.md`); new run IDs; pooled with A for calibration under analysis v3.1.

## Budget
- **Hotel** (fb14srv4, free now): launch-ready by 2026-10-10 06:00Z, terminal by 2026-10-10 18:00Z.
- **TeaStore** (fb14srv5) and **OTel** (fb14srv6): start only after that host's campaign B is terminal and fetched;
  terminal by **2026-10-12 12:00Z** (the user's deadline, `BUDGET_B.md`). B has priority on those hosts.
- At most 2 relaunches per system. One campaign per host.

## Stop rules
1. A system that cannot be terminal by its deadline is dropped from A2; recorded. No extension without the user.
2. A critical-path defect gets 30 minutes; 3 critical-path harness defects in one system: stop that system and ask.
3. Launch only from a declaration committed alone plus a passing DRY_RUN, mirrored to wandb.
4. A2 cells are read only through the frozen, reviewed v3.1.
