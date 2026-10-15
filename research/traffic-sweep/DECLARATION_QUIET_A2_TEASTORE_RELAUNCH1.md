# TeaStore quiet calibration run A2, relaunch 1: declaration (frozen 2026-10-10)

**Status: frozen** by committing this file alone, before the launch below (prepared by a subagent; frozen by the coordinator). Authority: protocol decision 68;
the A2 declaration `DECLARATION_QUIET_A2_TEASTORE.md` (frozen `b53c063`) stays binding for everything this draft does not change.
Budget and stop rule `BUDGET_QUIET_A2.md` (`0bf4cf8`): TeaStore terminal by **2026-10-12 12:00Z**; at most 2 relaunches
(**this is relaunch 1 of 2**); 3 critical-path harness defects stop TeaStore's part of A2 (**0 of 3 used**, see "Defect count").
Scope of every number: **instance** (one SUT, one host, fb14srv5).

## What relaunch 1 is
The A2 launch of 2026-10-09 23:32Z (setup ID `dc4e26ada1250e9c42037d88bfeebf43`) stopped at its 18th cell. Relaunch 1 runs the
**same 40-cell plan on the same harness commit** as a new campaign launch: new setup ID (minted by the gate chain), new results
root on srv5. **No framework commit, no plan change, no host move.**

## What differs from the stopped A2 attempt, and what does not
| item | A2 attempt (stopped) | A2 relaunch 1 |
|---|---|---|
| harness commit | `bb3717e8adeeaa05a45fd8e587cee481da206ac7` | **same** (worktree HEAD re-checked 2026-10-10 02:08Z; tracked and untracked tree clean, the launcher's `git status --porcelain -uall` guard passed) |
| epoch / selector / compiler | `teastore-quiet-calibration-v1`, `candidate_quiet.py` | **same bytes** (no commit) |
| descriptor canonical sha256 | `338226d05f8e9d3557918ef9120727094bd71532f4eba72cc9191070f102315b` | **same** |
| plan canonical sha256 | `879a81ab0c3f2e960ee11a282c8200e58b98e97bc8a541cbcc5704654f858266`, 40 cells | **same** (compiled by the launcher under `/usr/bin/python3 -I` in the dry run) |
| plan directory / campaign manifest | `.local/candidate-v4/teastore/plan-ce87db3c`, `faf4e523…0e0c` | **same directory, not regenerated** |
| run IDs, artifact paths, `attempt` | the 40 strings `…/no-fault-cost/r<rate>/b01..b10/full/a01` (A's strings) | **same 40 strings** (the quiet compiler has no attempt input; see "Run IDs") |
| schedule seed, cell order, onset offsets | seed 20261004 | **same** |
| campaign ID | `teastore-quiet-calibration-v1` | **same** |
| setup ID / results root | `dc4e26ada1250e9c42037d88bfeebf43` | **new**, `secrets.token_hex(16)` (`scratchpad/gate-drivers/campaign_setup.py:369`, `gate_setup.py:139`); the controller refuses an existing output root (`candidate_remote_controller.py:657-658`) |
| transient unit name | `teastore-candidate-v4-4b8e2c3b…` (left `loaded failed` on srv5) | **new**: derived from campaign ID + setup ID + package digest (`candidate_release_installer.py:1016`), so the failed unit cannot block `systemd-run` |
| SETUP-CAMPAIGN | re-derived by `auto` 2026-10-09T23:32:28Z (`approvedBy: "auto-derived"`) | **reused as is**: live to 2026-10-16T23:32:28Z, `invariants match=True` against this plan (dry run), so `auto` will not re-derive it |
| GATE-PLAN, GATE-SETUP, readiness, preflight, GATE-RUN | A2's records | **new records** (minted by `auto` and `oneshot`, the GATE-RUN sentence harness-derived as on every `oneshot`) |
| local run state | A2's `run-authorization.json`, `runtime-package.json`, `gate-run.json`, `campaign-terminal.json` in `gates/` | moved by the launcher (move, never delete) to `gates/run-state-before-quietA2r1-<stamp>` before `auto`; `gate_run.py oneshot` keys "prior authorization current" on (commit, setupId), so A2's record cannot be mistaken for current |
| launcher label / logs | `quietA2`, `teastore-quietA2-launch.log`; dry runs `quietA2dry1`, `quietA2dry2` | **`quietA2r1`**, `teastore-quietA2r1-launch.log`; dry run **`quietA2r1dry1`** |
| GATE-RUN window, watcher cap | 7 h, 8 h | **same** |

**Nothing else differs.** Cell shape, rates, warm-up, posture, pseudo window, gates, captures and the analysis rule are A's (via the
A2 declaration).

## Why A2 stopped (SUT flake, not a harness defect)
- Launcher log `scratchpad/gate-drivers/teastore-quietA2-launch.log`: `oneshot rc=0` 23:44:06Z; journal rows 0 -> 17 by 01:25:46Z;
  `02:00:51Z TEASTORE quietA2 TERMINAL: state=stopped systemd=failed/failed result=exit-code journalRows=18 terminal=False abort=True lease=False`.
- Fetched evidence `tmp/teastorequiet2-evidence/x/teastore-quiet-calibration-v1/` (source
  `fb14srv5:…/teastore/results/dc4e26ada1250e9c42037d88bfeebf43`; `verify-full.txt` 412 lines, 0 not `OK`; the host campaign
  directory holds 408 files, as locally):
  - `campaign-abort.json`: `ControllerError: candidate cell executor failed: RuntimeError: TeaStore readiness failed`,
    stage `cell-execution`, `experimentalState: ABSTAINED`, `journalRows 18`, `validCells 17`, recorded 2026-10-10T01:26:22Z.
  - `runtime-journal.jsonl`: sequences 0-16 `valid` (b01-b04 all four rates, b05 r1), sequence 17
    `teastore-quiet-calibration-v1/no-fault-cost/r0p05/b05/full/a01` `stopped` with the same reason (counted: 17 valid, 1 stopped).
  - Blocked cell: `runs/no-fault-cost/b05-02-full.blocked-evidence/blocked-evidence-manifest.json` (15 preserved operational files,
    preserved 01:26:21Z) and `runs/no-fault-cost/b05-02-full/.operational/` (`webui.log`, `registry.log`, `persistence.log`,
    `image.log`, `up.log`, `teardown.json`, …).
- Coordinator's read of those operational logs, recorded as the classification: all containers started, the registry had all 5
  services registered by 01:22:34Z, but webui's `ServiceLoadBalancer` kept logging `No Server registered for Service: persistence /
  image` until readiness timed out about 01:26Z: a **TeaStore startup race, classified as a SUT flake, not a harness defect**; it does
  not count toward the 3-defect rule. My only check of it: `webui.log` has 6 such lines (image and persistence), and `teardown.json`
  reports 0 containers and 0 networks left for project `teastore_candidate_46a023456d95cf24`. Not independently reviewed.
- The stop rule fired as designed (one-shot, no retry, blocked cell preserved, controller abstained).

## Harness commit and plan digest
- Harness: **`bb3717e8adeeaa05a45fd8e587cee481da206ac7`** (no new commit; governance pins, GATE-PLAN binding and suite state are those
  recorded in the A2 declaration; the full worktree suite was not re-run because nothing changed).
- Plan: **`879a81ab0c3f2e960ee11a282c8200e58b98e97bc8a541cbcc5704654f858266`**, 40 cells, descriptor `338226d0…315b`,
  minimum remaining at first mutation 21,300 s, run window 7 h (dry-run compile below).

## Run IDs: strings repeat, paths do not collide
- **The 40 run-ID strings are A's and the stopped A2 attempt's** (third use). The quiet compiler has no attempt, campaign or seed input
  (`candidate_quiet.py:434` writes `"attempt": 1`; `candidate_runtime_adapter.py:85` `ATTEMPT = 1`), and TeaStore's adapter has no
  spent-attempt registry (searched: no `SPENT_ATTEMPTS` in the worktree's `modules/teastore`). The A2 declaration accepted the same
  repetition between A and A2 ("Why the plan is reused"); a distinct set would need a new epoch or compiler, a framework commit,
  re-pinned governance and a new GATE-PLAN. Not done (least change).
- **No path collision.** Every host path is keyed on the setup ID: results `…/teastore/results/<setupId>/teastore-quiet-calibration-v1`,
  release `…/releases/<setupId>-<commit12>-<bundle16>`, readiness `/var/lib/…/readiness/<setupId>/`. On srv5 now (read-only,
  2026-10-10 ~02:12Z) exactly two results roots hold this campaign: `cedad730e9b5c219d53dabd22cd1f6c1` (A, 883 files) and
  `dc4e26ada1250e9c42037d88bfeebf43` (A2 attempt, 408 files). The new setup ID is a fresh 128-bit random token, and the controller
  refuses an existing output root, so neither can be written into. In-process, the adapter refuses a cell whose artifact root exists
  (`candidate_runtime_adapter.py:2520-2521`).
- **Neither old results root is moved, renamed or deleted.** No host move is needed: unlike OTel (whose `install` counts
  campaign-keyed host paths, hence `tmp/otel_quiet_a2_archive.sh`), TeaStore keys nothing on the campaign ID alone except the Compose
  project name, and the A2 attempt's teardown left 0 containers.

## Verification before launch (2026-10-10, read-only)
- **fb14srv5 idle** (02:09-02:12Z, `ssh -n -o BatchMode=yes -o IdentitiesOnly=yes fb14srv5`, stdout only): running/activating
  candidate|teastore|hotel|otel|boutique units 0; containers 0 (`docker ps -q`); `teastore_candidate` containers incl. stopped 0;
  candidate/supervise processes 0; lease `…/teastore/leases/host-exclusive.lock` exists (0 bytes, Sep 1), `fuser` rc 1, no holder;
  360 GB free (guard 40 GB). Seven `teastore-candidate-v4-*` units are `loaded failed` (six earlier campaigns' plus A2's
  `4b8e2c3b…`); none is active, and unit names are per setup ID.
- **Stopped attempt's evidence is safe locally**: `tmp/teastorequiet2-evidence` (412/412 `OK`, fetched and verified by the coordinator;
  not re-hashed on the host by me). A's evidence `tmp/teastorequiet1-evidence` untouched.
- **DRY_RUN** `scratchpad/gate-drivers/teastore-quietA2r1dry1-launch.log` (rc 0; `teastore-quietA2r1dry1.out` empty):
```
02:11:07Z === teastore launcher quietA2r1dry1 (ROOT …/observability-placement-runtime-teastore-protocol, HEAD bb3717e, dry=1) ===
02:11:12Z previous campaign status (… live package): 02:11:11Z state=stopped systemd=failed/failed result=exit-code journalRows=18 terminal=False abort=True lease=False
02:11:12Z plan: { "descriptorCanonicalSha256": "338226d05f8e9d3557918ef9120727094bd71532f4eba72cc9191070f102315b", "firstRunId": "teastore-quiet-calibration-v1/no-fault-cost/r0p05/b01/full/a01", "minimumFirstMutationRemainingSeconds": 21300, "planCanonicalSha256": "879a81ab0c3f2e960ee11a282c8200e58b98e97bc8a541cbcc5704654f858266", "runCount": 40, "runWindowHours": 7, "studyEpoch": "teastore-quiet-calibration-v1" }
02:11:12Z drivers read: ROOT=<worktree> STUDY=teastore-quiet-calibration-v1 CAMPAIGN_ID=teastore-quiet-calibration-v1 RUN_WINDOW_HOURS=7 PLAN_DIR=<worktree>/.local/candidate-v4/teastore/plan-ce87db3c GATES=<worktree>/.local/candidate-v4/teastore/gates SWEEP=True
02:11:17Z srv5 host facts (stdout only): ncpu=24 cgroup=systemd/2 candidate_containers=0 containers=0
02:11:17Z authorization (auto will re-derive if not live): HEAD bb3717e8adeeaa05a45fd8e587cee481da206ac7
authorized 2026-10-09T23:32:28Z deadline 2026-10-16T23:32:28Z live=True
provenance derived by `auto` at 2026-10-09T23:32:28Z (no human typed it)
invariants match=True
02:11:22Z srv5 free GB (stdout only): 360
02:11:22Z DRY RUN: all guards passed; stopping before the first mutation
```
- **Not shown by the DRY_RUN:** the run-state move, `auto` (GATE-PLAN, release bundle, install, readiness), `oneshot` (fresh preflight,
  GATE-RUN), the 40-cell loop. The A2 attempt passed all of them on this exact commit and plan about 2.6 h earlier (2026-10-09 23:32Z), so the difference is
  the starting state (A2's aborted run state instead of B's completed one), which the launcher moves aside before `auto`.

## Defect count
**0 of 3** critical-path harness defects for TeaStore's part of A2. The A2 stop is a SUT flake (above), not counted. This prep found no
harness defect: no guard refused, no commit was needed.

## Launch (only after this draft is frozen as the real declaration and committed alone)
From the measurement repo. Re-check first: worktree HEAD still `bb3717e8…`, fb14srv5 idle (`docker ps`, `ps`, lease holder), no other
campaign on srv5.
```
W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
cd $M
TEASTORE_ROOT=$W EXPECTED_HEAD=bb3717e8adeeaa05a45fd8e587cee481da206ac7 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_quiet.py EXPECTED_PLAN=879a81ab0c3f2e960ee11a282c8200e58b98e97bc8a541cbcc5704654f858266 RUN_COUNT=40 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh quietA2r1 > $M/scratchpad/gate-drivers/teastore-quietA2r1.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow teastore-quietA2r1 scratchpad/gate-drivers/teastore-quietA2r1-launch.log \
  > scratchpad/gate-drivers/teastore-quietA2r1-wandb.out 2>&1 &
```
Expected: the A2 attempt's measured pace was 17 cells in about 101 min (23:44:06Z start to 01:25:46Z, about 357 s per cell, a
5-minute-poll resolution), so 40 cells take about 4.0 h plus about 12 min setup (A2: 23:32:14Z to 23:44:06Z); window 7 h, watcher cap
8 h. A launch before about **2026-10-12 03:45Z** leaves the 12:00Z deadline met even if the run uses the full 8 h watcher cap plus setup.

After terminal: fetch to a **new** path (for example `tmp/teastorequiet2r1-evidence`, never into `tmp/teastorequiet2-evidence`),
byte-verify host against local, read cell validity only. Then `uv run python tools/wandb_campaign.py cells teastore-quietA2r1
tmp/teastorequiet2r1-evidence/x`.

## Pooling and consequences (stated, not hidden)
- **The 17 valid cells of the stopped attempt remain evidence** to be pooled with A and with relaunch 1 under analysis v3.1. Pooling must
  key on the setup ID / fetch directory (`cedad730…` = A, `dc4e26ad…` = A2 attempt, the new one = A2 relaunch 1), never on
  `(campaign ID, run ID)`: all three share the campaign ID and every run-ID string. `tools/evidence_inventory.py` needs that check before
  it touches quiet evidence (open since the A2 declaration).
- Relaunch 1 runs all 40 cells, so the 17 run IDs already valid in the stopped attempt (b01-b04 x 4 rates, b05 r1) are measured a second
  time within A2. **Resolved by the frozen analysis, not a new decision:** v3.1 identifies a cell by (campaign directory, run path)
  (`sweep_analysis_v3.py` `pool_key`, rule V3_POOL_KEY_RULE, decisions 68 and 69, with a planted-defect test), so A, the A2 attempt and
  relaunch 1 are distinct cells even where run IDs repeat, and every valid cell is pooled (decision 68: more quiet time). Each fetch
  directory is given to v3.1 once; the analysis refuses a cell given twice.
- Cell order, onset offsets and position-in-campaign repeat A's schedule a third time (limitation as in the A2 declaration).
- The A2 attempt's blocked cell (b05 r0.05) is preserved, flagged, and not re-used as a valid cell.

## Open items
1. Pooling rule for repeated run IDs: resolved above by the frozen v3.1 pool key (all valid cells pooled).
2. `scratchpad/gate-drivers/teastore-quietA2.out` holds 6 lines `log: operation not permitted: …/teastore-quietA2-launch.log`: the
   launcher's `log()` could not append to its log for six watcher polls (the log has no lines between 01:25:46Z and 02:00:51Z). Cause not
   established (laptop-side; the campaign itself ran on the host). It does not affect the campaign but blinds the wandb follower for that
   span; check the relaunch's `.out` for the same symptom.
3. No independent review (judge or Fable subagent) of this draft; the checks above are my own read-only host checks and the launcher's dry run.
