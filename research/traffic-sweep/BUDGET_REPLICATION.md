# Traffic-sweep replication on TeaStore and OTel: budget and stop rule (committed alone, before the work; 2026-10-03)

User, 2026-10-03 ~05:20Z: "replicate now for the other 2 repos as an initial test while this one runs". Hotel's sweep
(`DECLARATION.md`, campaign `hotel-v1-20261003t050738z-29661565`, srv4) keeps running; its worktree
`observability-placement-runtime-hotel-protocol` is ROOT for a live campaign and is **not touched**.

## Scope (initial test = shakedown, not confirmatory)
| | TeaStore | OTel demo |
|---|---|---|
| host | fb14srv5 (lineage-bound) | fb14srv6 |
| worktree | `observability-placement-runtime-teastore-protocol` | `observability-placement-runtime-otel-protocol` |
| design | Hotel's values: rates 10, 1, 0.2, 0.05 /s on one route through the entry; warm-up 30 s at 10/s; measurement 180 s; onset 60 s + stratified offset; hold 60 s; posture full; lead cell = pause at 10/s | same |
| regimes | no-fault + the SUT's analogues of Hotel's pause / CPU throttle / net delay; a regime whose mechanism needs sudo on the host (netem on srv5/srv6) is omitted and recorded | same |
| size | **1 block** (one cell per regime × rate, ≤ 16 cells) | same |
Each SUT gets its own declaration, committed alone before its first cell; the user vetoes mapping choices at freeze.

## Budget
- Build (harness epoch, tests, offline replay, DRY_RUN): **launch-ready by 2026-10-04 12:00Z** per SUT.
- Campaign: terminal by the Hotel kill date, **2026-10-06 12:00Z**; at most 2 relaunches per SUT.

## Stop rules
1. A SUT not launch-ready by 2026-10-04 12:00Z is dropped from the initial test; the reason is recorded
   (`research/OTEL_STOPPING_RULE.md` is the template). No extension without the user.
2. A defect on the critical path gets 30 minutes; **3 critical-path harness defects in one SUT → stop that SUT and ask.**
3. Nothing here may change the running Hotel campaign, its worktree, or srv4.
4. Launches follow `CLAUDE.md`: frozen declaration + passing DRY_RUN; every campaign mirrored to wandb.
