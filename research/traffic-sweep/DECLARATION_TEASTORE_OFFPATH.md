# TeaStore off-path pause (recommender) campaign: declaration (2026-10-14)

**Status: declaration, committed alone before launch** (BUDGET_TEASTORE_OFFPATH stop rule 3), after an independent review (GO on the code at `9eef736`,
see "Review"). Scope of every number: **instance** (TeaStore at upstream 34b37f7, fb14srv5). *Generator* numbers come from the compiler, not the host;
unknown values are `?`. Authority: user, 2026-10-13 ("Yes" to the TeaStore off-path pause on `research/PLAN_LANES_20261014.md`, `c2914de`; budget
`BUDGET_TEASTORE_OFFPATH.md`, `ebf345a`). No cell of this epoch is read (validity fields only) before reader v3.3 is frozen by digest.

## What it is
Epoch `teastore-offpath-v1` in the TeaStore harness worktree (`observability-placement-runtime-teastore-protocol`, branch `teastore-protocol-20261002`; commits
`9b0086f`, `bc3dc2a`, `20f555b`, `9eef736` on `3b4a513`; activation `f74b29b`). Compiler `modules/teastore/execution/candidate_offpath_ts.py` (modelled on
campaign C), descriptor `pipelines/campaigns/teastore-offpath-v1.json`.
- **Regimes:** `no-fault-cost`; `recommender-pause-effect` (60 s pause of `recommender`, which the login journey never calls: `workload/fixed_load.py` ~803-807 is a
  single `POST /loginAction` redirecting to `/`; `IndexServlet` calls persistence, auth and image; the servlets that call the recommender are Cart, Product,
  DataBaseAction and Status); `auth-freeze-effect` (the on-path control, the B/C mechanism).
- **Pause target:** an allow-list {auth, recommender} (`performance_campaign.py` `PAUSE_FAULT_SERVICES` ~73, `fault_service()` ~80); a plan whose `faultTarget`
  differs is refused before any container is touched; the validator requires the onset/recovery commands to end in `pause <service>` / `unpause <service>`.
- **Design:** rates 10 and 1 req/s, 5 blocks, 3 regimes per rate: **30 cells**, order shuffled per block. Descriptor
  `127e8263947c13799128c6ff4ff787d648ce967c54d09bfc3703a7409ffe2b76`, plan `5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a` (*generator*,
  identical under 3.9 and 3.13). Window 5 h (`RUN_WINDOW_HOURS`), expected about 3.0 h from campaign C's runtime journal (mean 348.6 s per cell; a recommender
  cell is assumed to take an auth cell's time). `application.log` is kept in every cell (registry lines).
- **Analysis:** reader v3.3 (`sweep_analysis_v3_3.py`, `parameters_v3_3.json`), campaign-B shaped. There is **no placement verdict** for this epoch: it measures
  lanes, reported per regime and rate.

## Lane predictions (stated before launch; scored hit/miss over the 10 recommender-pause episodes, 5 per rate)
| id | lane | prediction | basis |
|---|---|---|---|
| T-L2 | coordinator: registry log ids (service `registry`) | a "Removed …recommender… since it failed the heartbeat!" fire 7.5-12.5 s after the pause command in >= 9/10, at both rates | client heartbeat 2.5 s (`RegistryClient.java:65`), alive window 10 s (`HeartbeatInfo.java:32`), cleanup every 2.5 s (`RegistryStartup.java:40,68-73`); campaign C: the auth line fired in 28/28 auth-freeze episodes at 9.1-11.7 s |
| T-L1 | own silence: the recommender's cgroup CPU (family S) | a downward fire < 5 s after the pause command in >= 9/10, independent of the rate | no-fault recommender CPU median 0.070 cores, minimum 0.038 (one B cell); a paused container uses ~0 |
| T-OFF | the fault stays off the login route | ledger: >= 95 % of login journeys ok during the hold in >= 9/10 recommender-pause episodes; no ledger fire attributable to the pause | the login route does not call the recommender (above) |
| T-C | on-path control | auth-freeze is detected by the ledger as in C (C: P1 4/4) | C |
- **Counting status, stated before launch.** The reader drops a fire flagged by construction (`BC-*`) from the counted field and reports it in the lanes block's
  by-construction field (`LANES_BC_SEPARATE`, `f8412c5`). In campaign C's readout the auth removal line carries `BC-caller-log` in 28/28 episodes, although the
  project map's call graph for TeaStore has no registry edge (`detection_time.call_graph("teastore")` lists `(webui, recommender)` only); why it is flagged was
  not resolved before this declaration. A down-going CPU fire of the target is flagged `BC-idle-cpu` by rule. **Both fields are reported; a prediction is a hit if
  the fire is in either field, and the field is named.**
- **Pricing.** The registry removal line appears in 0 of 12 campaign C no-fault cells: an appear-only sensor, which decision 73 prices at the fill cost. Both the
  charged price and the zero-alarm price (2.996/T_r) are reported, without a verdict.
- If the recommender pause turns on-path (webui's status or login calls fail), that is reported as observed (budget stop rule 4), not hidden.

## Evidence handling
Fetch read-only after the terminal into a new directory (`tmp/teastore-offpath-evidence/o1-fetch`), byte-verified against the host manifest, with a new case in
`scratchpad/gate-drivers/fetch_overnight.sh` once the setup id is known (as `teastorec1r1`). Offline terminal replay before any reading. Evidence stays out of git.

## Launch (worktree HEAD = the activation commit; DRY_RUN first; one campaign per host, check fb14srv5 itself)
```
W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
cd $M
git -C $W rev-parse HEAD        # must equal f74b29b92de283878ca50ea4ab2a5e1beb74eef7 (activation)
DRY_RUN=1 TEASTORE_ROOT=$W EXPECTED_HEAD=f74b29b92de283878ca50ea4ab2a5e1beb74eef7 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_offpath_ts.py EXPECTED_PLAN=5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a RUN_COUNT=30 \
  zsh scratchpad/gate-drivers/launch_teastore.sh odry1
TEASTORE_ROOT=$W EXPECTED_HEAD=f74b29b92de283878ca50ea4ab2a5e1beb74eef7 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_offpath_ts.py EXPECTED_PLAN=5a8e385e7a82ab4ee5166dfdbc9a98df478e0cd8c9c77282bba15d7fa82fd06a RUN_COUNT=30 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh o1 > $M/scratchpad/gate-drivers/teastore-o1.out 2>&1 &
```
At most 1 relaunch, harness or infrastructure defects only.

## Risks the build cannot settle without running
1. Readiness after unpausing the recommender is untested: webui `/status` needs it re-registered and "OK and trained" (`StatusServlet` `isRecommenderFinished`);
   at 1 req/s the after-phase floor needs readiness within about 28 s of the revert (review). C's auth cells reached readiness 0.3 s or 5.4 s after the revert.
2. The recommender's AMQP (Kieker) heartbeat is 900 s, so a 60 s pause should not drop its monitoring connection (not observed).
3. TeaStore's registry-client startup race recurred twice in earlier campaigns (ledger row); a readiness block is preserved and flagged, not fatal.
4. The shared runtime files `performance_campaign.py` and `validation/candidate_pilot.py` moved, so every epoch's controller digests moved and gate sentences
   re-derive (expected).

## Review
Independent same-provider review (Fable `adversarial-review`, 2026-10-13 ~14:20Z on `9eef736`): **GO on the code**; one blocker outside the code (untracked
files in the worktree's `tmp/` make the launcher refuse a dirty tree), resolved by moving them to the measurement repo's `tmp/teastore-offpath-build-logs/`.
The reviewer's claim that the registry line is not BC-flagged is contradicted by campaign C's readout (above). Cross-provider judge: not run (server not connected).
