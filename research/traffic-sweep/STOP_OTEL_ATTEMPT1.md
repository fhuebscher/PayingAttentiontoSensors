# OTel traffic sweep: attempt 1 stopped (2026-10-03 12:30Z)

Campaign `otel-traffic-sweep-v1` on fb14srv6 (activation 6380cce, plan 779b908d, `DECLARATION_OTEL.md`): **8 of 12 cells
sealed, 7 valid**. Cell 8 `frontend-pause` r0.2 b01 sealed invalid: `trace completeness 20/21 is below 0.99 (needs 21)`;
pre-onset 12/12, post-recovery 8/9. F1/G1/G2/G4 passed. The campaign stopped (first invalid cell). Relaunch 1 of 2 not
used yet.

This is the low-rate behaviour of the M1 rule recorded at freeze (`DECLARATION_OTEL.md`, "Trace completeness"): below 100
successful requests the 99 % rule is all-or-nothing. Same class as Hotel relaunch 2's stop (`STOP_ATTEMPT3.md`): an
all-or-nothing trace-completeness rule around a fault. Which request lost its trace, and why: `?` (not examined).

## Addendum (2026-10-03 ~13:30Z): third critical-path defect, OTel on hold (BUDGET_REPLICATION.md rule 2)
- Decision 25 implemented (worktree f9f480f + re-pin ecb0f8e; plan attempt 2 `34308536…`); offline replay: cell 8 now
  valid (its one incomplete trace started 9.8 s into the drain window); 6 of the 7 previously valid cells stay valid.
- **The lead cell (frontend-pause r10) fails terminal replay**: "application witness does not establish the offered
  denominator"; 124 of 1,800 requests got RemoteDisconnected and have no proxy access-log line. The target sealed it valid
  because the witness check runs only in the terminal at fetch.
- **Cause verified** (srv6 kernel log, read-only): `Memory cgroup out of memory: Killed process … (envoy)` at
  2026-10-03 11:46:59Z and again at 11:59:31Z (anon-rss ~46 MB + file-rss ~41 MB; upstream caps frontendproxy at 50M).
  With 15 s timeouts at 10/s up to 150-300 requests wait in the proxy during a pause.
- Third critical-path harness defect in OTel (after the loadgenerator Compose dependency and the UTF-8 class), so the SUT
  stops and the user decides. No relaunch, no host move. Archive: `tmp/otel-sweep-evidence/otel-traffic-sweep-v1-attempt1.tgz`.
