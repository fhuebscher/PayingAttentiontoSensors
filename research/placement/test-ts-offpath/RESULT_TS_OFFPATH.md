# TeaStore off-path pause (recommender), relaunch 1: result (2026-10-14)

Scope: **instance** (TeaStore at 34b37f7, fb14srv5, login-only workload at 10 and 1 req/s, 5 blocks; 10 recommender-pause episodes, 10 auth-freeze, 10
no-fault). No placement verdict was declared for this epoch; it measures lanes against predictions stated before launch.

- Declarations `DECLARATION_TEASTORE_OFFPATH.md` (`f40e786`) and `_RELAUNCH1.md` (`3dd0221`); budget `BUDGET_TEASTORE_OFFPATH.md` (`ebf345a`, amendment 1
  `b7f6bf5`). Harness `f74b29b`, plan `5a8e385e`. Attempt 1 stopped at cell 3 (registry-client readiness race); only relaunch 1 is read.
- Run: relaunched 2026-10-14 00:25:27Z (the launch log's first line; the relaunch declaration `3dd0221` was committed in the same second), terminal 03:48:20Z (complete), 30/30 valid; fetched 667/667 byte-verified (`tmp/teastore-offpath-evidence/r1-fetch`,
  setup ID `def272fd…`). Host terminal validation pass 30/30. Offline replay (`e6253a5`): 30/30 cells replay to pass, 10 byte-equal, 20 differ only in the
  embedded host path of `intervention.json`; the campaign-level byte-exact replay is blocked by that path (deviation recorded, `3270e49`).
- Reader v3.3 frozen before any cell was read (`6efd378`); readout `b6d8690` and post hoc `74c84f4` committed unedited before reading; `campaignsRead` lists
  exactly the relaunch-1 campaign (setup ID checked first).

## Predictions (declared before launch; 10 recommender-pause episodes, 5 per rate)

| id | prediction | result |
|---|---|---|
| T-L2 coordinator | registry removal line 7.5-12.5 s after the pause command in >= 9/10, both rates, field named | **hit**: 10/10 at 8.37-12.03 s (rate 10: 8.37-12.03; rate 1: 9.45-11.31); all in the by-construction field (`BC-caller-log`), 0 counted |
| T-L1 own silence | recommender cgroup CPU down-fire < 5 s in >= 9/10 | **miss**: 0/10 under 5 s; the own lane's earliest fires are counted `median`/`run3` fires of `sys_io` and `sys_psi_cpu` at 14.86-14.92 s in 5/5 rate-10 episodes; none at rate 1 |
| T-OFF stays off the login route | ok share >= 95 % during the hold in >= 9/10, and no counted ledger fire | **miss** under the post-hoc script's pre-committed operationalisation of "no ledger fire attributable to the pause" (any counted ledger fire): ok share 1.0 in 10/10 (603/603 per episode at rate 10; 60/60 or 61/61 per episode at rate 1); one counted ledger `spike` at 5.07 s in rate 10, block 5 (one succeeded login-action request of 603, 164.6 ms against a pre-onset median of 51.4 ms; the spike rule's honest no-fault count at rate 10 is 1 in 0.25 h) |
| T-C on-path control | auth-freeze P1 holds | **hit**: 10/10 (5 per rate) |

## What this does and does not say
- The registry's heartbeat-removal line marks the paused off-path recommender in 10/10 episodes at 8.4-12.0 s, inside the window derived before launch
  from the client heartbeat (2.5 s), alive window (10 s) and cleanup interval (2.5 s). The reader drops it from the counted field by its content rule (the
  line names the target, `sweep_analysis.py:293-318`); it is reported in the by-construction field, as the declaration said it would be.
- The recommender's CPU counter (`cpuUsageUsec`) was flat for the whole pause in 10/10 episodes, and no no-fault cell has a single zero interval; the
  calibrated `sys_cpu` rules (K 2.5-8) did not fire in either field, probably because their downward threshold sits at or below zero at that K (reviewer's
  per-cell estimate from raw samples, not the reader's pooled fit). I/O and CPU-pressure rules fired at about 14.9 s at 10 req/s (3-sample rules on a 5 s
  sampler, which strains "< 5 s", as the freeze addendum noted); nothing fired at 1 req/s. So T-L1 is a miss of the detector, not evidence that the pause
  left nothing to see.
- **Not predicted, found in review:** webui (a login-route service) logs Ribbon's "current list of Servers=[]" load-balancer line
  (`log:webui:d4d75ec135e6`) as a counted, non-BC fire in 10/10 recommender-pause episodes, at 9.52-14.12 s (rate 10) and 10.20-12.53 s (rate 1),
  0.75-2.08 s after the registry removal; the line does not name the recommender and also appears at startup. It is a client-side discovery signal on
  the login route, while the login route itself stayed fully available.
- The login route stayed fully available during every recommender pause. The one counted ledger spike (5.07 s, one episode) is not separated here from
  ledger noise at n = 1.
- The post-hoc script ran at its post-deviation digest `b203c2c3…` (changed for F at 04:00Z, recorded, before TeaStore was read). The readout flags all 30
  cells F5 (harness `f74b29b` is not in the reader's HARNESS_PROVENANCE table) and its header text ("not frozen", harness 91c4967) is stale boilerplate.
- n = 5 episodes per rate, one host, one SUT. One same-provider adversarial review (Fable, 2026-10-14): numbers supported apart from three corrected
  here, the T-L1 sentence refuted and replaced, the webui finding added. A cross-provider check is owed.
- Correction (review of the paper, 2026-10-14): the declaration's T-L2 basis "campaign C: the auth line fired in 28/28 auth-freeze episodes at
  9.1-11.7 s" pools the TeaStore readouts committed before F (sweep r2, B, C), not campaign C alone, and spans 9.07-11.75 s (`research/lanes/out-20261013/LANES.md`). The
  declaration is frozen and not edited; this note records the correction.
