# Quiet calibration run A2 on TeaStore: declaration (FROZEN 2026-10-09, committed alone before launch)

**Status: draft.** Written to be frozen by the coordinator (renamed, committed alone) after review. Nothing was launched,
no gate was derived, no setup ID was minted. Authority: protocol decision 68 (`research/PROTOCOL_DRAFT_20261002.md`).
Budget and stop rule: `BUDGET_QUIET_A2.md` (`0bf4cf8`, committed alone): TeaStore on fb14srv5 after campaign B is
terminal and fetched; terminal by **2026-10-12 12:00Z**; at most 2 relaunches; 3 critical-path harness defects stop
TeaStore's part of A2. Scope of every number: **instance** (one SUT, one host).

## What A2 is
A second run of quiet run A (`DECLARATION_QUIET_TEASTORE.md`, frozen `fc64a6d`): **the same 40 no-fault cells** (10 blocks
x rates 10, 1, 0.2, 0.05 /s, posture `full`, 180 s measurement, pseudo window, G1/G2/G4, decision 25), the same compiler,
descriptor and plan, **a new campaign launch** (new setup ID, new results root on srv5), on a **later harness tree**
(below). Pooled with A for calibration under analysis v3.1 (decisions 67, 68).

## What differs from A, and what does not
| item | A | A2 |
|---|---|---|
| harness commit | `91c4967f2d9c12a25eeeaf097f998856c377ca7f` | **`bb3717e8adeeaa05a45fd8e587cee481da206ac7`** (worktree `observability-placement-runtime-teastore-protocol`, branch `teastore-protocol-20261002`), one commit on `bbb6b11` (campaign B's harness) |
| epoch / selector | `teastore-quiet-calibration-v1`, `modules/teastore/execution/study-epoch.json` | **same epoch, same selector bytes** (`bb3717e` restores `d0a5953`'s selector; B's selector `5188852` is reverted) |
| descriptor canonical sha256 | `338226d05f8e9d3557918ef9120727094bd71532f4eba72cc9191070f102315b` | **same** |
| plan canonical sha256 | `879a81ab0c3f2e960ee11a282c8200e58b98e97bc8a541cbcc5704654f858266`, 40 cells | **same** |
| campaign manifest sha256 | `faf4e52392db870c9dfbd00d6f960830eabba9f519f7d1857cdc69a9733c0e0c` | **same bytes** (plan dir `plan-ce87db3c`; `materialize_campaign` replayed it at `bb3717e`, existing bytes matched; a fresh materialization under `/usr/bin/python3 -I` and `uv run python -I` is byte-equal to it for `campaign.json`, `compiled-plan.json`, `campaign-descriptor.json`) |
| run IDs, artifact roots, `attempt` | `teastore-quiet-calibration-v1/no-fault-cost/r<rate>/b01..b10/full/a01`; 40 in A's runtime journal | **same 40 strings** (the compiler has no attempt input: `attempt` is the literal 1 and the run-ID rule ends in `a01`, `candidate_quiet.py:166,173,434`) |
| schedule seed, cell order, pseudo-window onset offsets | seed 20261004, per-block Fisher-Yates | **same** (module constants) |
| campaign ID (`campaignId` in the contract) | `teastore-quiet-calibration-v1` | **same string** (the drivers' `CAMPAIGN_ID`), so the Compose project, `teastore_candidate_` + sha256(campaign id)[:16] (`candidate_remote_controller.py:387`), is A's; srv5 has 0 containers now |
| setup ID, results root, release dir | `cedad730e9b5c219d53dabd22cd1f6c1` | **new**, `secrets.token_hex(16)` at `auto` (`campaign_setup.py:369`); the controller refuses an existing output root (`candidate_remote_controller.py:657`), so a collision with A's `results/cedad730…/teastore-quiet-calibration-v1` is impossible |
| SETUP-CAMPAIGN, GATE-PLAN, GATE-SETUP, GATE-RUN, preflight | A's records (SETUP derived 2026-10-04T10:56:00Z) | **new records, same plan**; today's SETUP-CAMPAIGN is B's (derived 2026-10-09T15:23:41Z, live to 2026-10-16, `invariants match=False` against this plan, as for A) and `auto` re-derives it, recorded `approvedBy: "auto-derived"` |
| 3 of the 56 bound controller digests | A's | **differ**: `candidate-validator` (`validation/candidate_pilot.py`), `bounded-performance-runner` (`execution/performance_campaign.py`), `study-epoch-loader` (`execution/study_epoch.py`). They carry campaign B's H10/H4 code (decisions 49, 69); every other bound controller is byte-identical to A's |
| host / lease | fb14srv5 | same; one campaign at a time (the host is idle, see below) |
| launcher label / logs | `quiet1`, `teastore-quiet1-launch.log` | `quietA2`, `teastore-quietA2-launch.log` (dry run: `quietA2dry1`) |
| GATE-RUN window, watcher cap, 40 x 525 s estimate | 7 h, 8 h, 21,300 s | **same** |

**Nothing else differs.** Cell shape, rates, warm-up, posture, pseudo window, gates, captures and the analysis rule (no read
until v3.1 is frozen and reviewed, `BUDGET_QUIET_A2.md` rule 4) are A's.

## Why the plan is reused (engineering default, recorded)
The quiet compiler has no attempt, campaign or seed input (same finding as Hotel's A2, `DECLARATION_QUIET_A2_HOTEL.md`),
so any distinct plan needs a new epoch or compiler and a framework commit that re-pins the descriptor, plan and tests.
Decision 68 asks for "the same cell shape", not a new plan. TeaStore itself already launched the same run-ID shape three
times (sweep attempt 1, relaunch 1, relaunch 2: each plan's first run ID is `…/auth-freeze-effect/r10/b01/full/a01`; the three
plans differ in digest) with a new setup ID each time, each to its own results root. So A2 reuses the plan.

## What the activation changed in the worktree (`bb3717e`, tested)
- `modules/teastore/execution/study-epoch.json` -> the quiet selector (bytes of `d0a5953`'s).
- `modules/teastore/extension-ledger.yaml`: purpose text of the selector, nothing else.
- `tests/conftest.py`: docstring only (the 18 effect-cell skips under the quiet selector already existed).
- `tests/test_teastore_quiet_a2.py` (+5): the selector and `study_epoch.active` (40 cells, 7 h, 21,300 s, no fault regime);
  the quiet plan and descriptor digests are A's and compile here; B's descriptor/plan (`d4d84633…`, `aa346970…`) and the
  sweep's plan (`88a3017a…`) are unchanged; since `bbb6b11` only the selector and the ledger differ under
  `modules/teastore` and `pipelines/campaigns`, and quiet's, sweep's and B's compiler and descriptor files, plus
  `performance_campaign.py` and `candidate_pilot.py`, are the bytes of `bbb6b11`; relative to A's `91c4967`, exactly six files
  differ (the B compiler and descriptor, the two shared files, `study_epoch.py`, the ledger) and quiet's own compiler,
  descriptor and the sweep's are byte-identical. **Planted: 2 of 2 caught** (B selector restored: 3 tests fail; one byte
  appended to `performance_campaign.py`: 1 test fails; both restored, tree clean).
- **Behaviour of the quiet epoch on this tree equals A's tree.** Not new in this commit: `tests/test_teastore_sweep_b.py`
  runs the quiet selector on a copy of this tree and of `91c4967` and compares the epoch dict, adapter constants, campaign
  manifest, plan, run IDs, the 40 cell contracts (with the 3 moved controller digests masked), a sealed quiet cell's
  validator verdict and its gate table. They pass. The H4 and H10 code runs only for a cell whose plan declares
  `timing.faultHarness`; quiet cells declare none.

## Verification (2026-10-10)
- Worktree suite (`uv run pytest -q -p no:cacheprovider --ignore tests/test_mlflow_manifest.py -rf`):

  | tree | selector | failed | passed | skipped |
  |---|---|---|---|---|
  | `bbb6b11` | B | 20 | 1994 | 162 |
  | `bb3717e` | quiet | 20 | 1981 | 180 |

  The 20 failures are the same by name (sorted `FAILED` lines diffed empty): Hotel materialize x4, Online Boutique LGTM x12,
  Online Boutique x1, openspec x1, OTel materialize x1, science-epoch router x1. None is TeaStore. 1994 - 18 (effect-cell tests
  skipped under the quiet selector again) + 5 (new) = 1981.
- Digests: `candidate_quiet.py` output (descriptor `338226d0…315b`, plan `879a81ab…8266`, 40 runs, window 7 h, minimum
  remaining 21,300 s) is byte-identical under `/usr/bin/python3 -I -X pycache_prefix=<fresh dir>` (3.9.6) and `uv run
  python -I` (3.13.12).
- Plan directory: `.local/candidate-v4/teastore/plan-ce87db3c` (gitignored), the three files equal A's (manifest
  `faf4e523…0e0c`); nothing regenerated, A's plan directory was not changed.
- A's evidence (`tmp/teastorequiet1-evidence`) has the same descriptor and plan digests and 40 run IDs of the same shape in its
  runtime journal; untouched. **A2 must fetch to its own new `tmp/` path.**
- fb14srv5, read-only (dry run 19:28Z and `ps` after): 0 containers, 0 `teastore_candidate` containers, no campaign or tar
  process after the dry run, 361 GB free (the launcher guard is 40 GB). The 6 `teastore-candidate-v4-*` systemd units listed
  as failed/inactive are earlier campaigns'; none is active. Campaign B is terminal (journalRows 36, `terminal=True`) and its
  fetch is at `tmp/teastoreb1-evidence` (`verify-full.txt`: 799 lines, none other than `OK`; not re-verified by me against
  the host).
- **Not shown by the DRY_RUN:** the SETUP-CAMPAIGN re-derivation, `auto` (release bundle, upload, install, readiness),
  `oneshot` (GATE-RUN), the 40-cell controller loop, the cell period. A's launch passed all of them on `91c4967`, but this
  tree's release bundle, the three moved controllers and the first 40-cell run on `bb3717e` are untested on the host.

### Dry run (`DRY_RUN=1`, 2026-10-10 19:28Z, read-only against fb14srv5)
Log `scratchpad/gate-drivers/teastore-quietA2dry1-launch.log` (rc 0):
```
19:28:20Z === teastore launcher quietA2dry1 (ROOT …/observability-placement-runtime-teastore-protocol, HEAD bb3717e, dry=1) ===
19:28:24Z previous campaign status (… live package): state=complete systemd=inactive/dead result=success journalRows=36 terminal=True abort=False lease=False
19:28:25Z plan: descriptorCanonicalSha256 338226d0…315b, firstRunId teastore-quiet-calibration-v1/no-fault-cost/r0p05/b01/full/a01, minimumFirstMutationRemainingSeconds 21300, planCanonicalSha256 879a81ab…8266, runCount 40, runWindowHours 7, studyEpoch teastore-quiet-calibration-v1
19:28:25Z drivers read: ROOT=<worktree> STUDY=teastore-quiet-calibration-v1 CAMPAIGN_ID=teastore-quiet-calibration-v1 RUN_WINDOW_HOURS=7 PLAN_DIR=<worktree>/.local/candidate-v4/teastore/plan-ce87db3c GATES=<worktree>/.local/candidate-v4/teastore/gates SWEEP=True
19:28:29Z srv5 host facts (stdout only): ncpu=24 cgroup=systemd/2 candidate_containers=0 containers=0
19:28:29Z authorization (auto will re-derive if not live): HEAD bb3717e8… authorized 2026-10-09T15:23:41Z deadline 2026-10-16T15:23:41Z live=True; provenance derived by `auto` (no human typed it); invariants match=False
19:28:34Z srv5 free GB (stdout only): 361
19:28:34Z DRY RUN: all guards passed; stopping before the first mutation
```

## Consequences of reusing the plan (stated, not hidden)
- **All 40 run IDs, artifact roots and campaign paths equal A's**, and so does the contract's `campaignId`. Pooling must key
  on the results ID (setup ID) of each fetch; any reader keyed on `(campaign ID, run ID)` alone cannot tell A from A2.
  `tools/evidence_inventory.py` reads `plan["blocks"]` and needs a check before it touches quiet evidence.
- **Cell order and onset offsets repeat A's.** A2 is a replicate of A's schedule, not an independent draw. Position in the
  campaign (host drift) repeats too, and cell order stays confounded with rate as in A. Recorded as a limitation.
- **The harness tree is not A's.** Three bound controllers moved (B's H10/H4 code); behaviour for quiet cells is pinned equal by
  tests, not shown on a host. If A2 and A differ systematically, "different harness commit" is one explanation to rule out
  before any other; the release bundle also contains `candidate_sweep_b.py` and B's descriptor (unused by this epoch).
- **A's evidence is untouched.**

## Launch (only after this draft is frozen as the real declaration and committed alone)
From the measurement repo. Launch only after B's fetch is complete and verified (done as of this draft) and no other campaign
runs on fb14srv5 (re-check `docker ps` and `ps` first):
```
W=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement-runtime-teastore-protocol
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
cd $M
TEASTORE_ROOT=$W EXPECTED_HEAD=bb3717e8adeeaa05a45fd8e587cee481da206ac7 TEASTORE_PREV_ROOT=$W \
  COMPILER=candidate_quiet.py EXPECTED_PLAN=879a81ab0c3f2e960ee11a282c8200e58b98e97bc8a541cbcc5704654f858266 RUN_COUNT=40 \
  nohup caffeinate -i zsh $M/scratchpad/gate-drivers/launch_teastore.sh quietA2 > $M/scratchpad/gate-drivers/teastore-quietA2.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow teastore-quietA2 scratchpad/gate-drivers/teastore-quietA2-launch.log \
  > scratchpad/gate-drivers/teastore-quietA2-wandb.out 2>&1 &
```
The launcher moves B's run state (`run-authorization.json`, `runtime-package.json`, `gate-run.json`,
`campaign-terminal.json`, `campaign-result`) into `gates/run-state-before-quietA2-<stamp>` (move, never delete) before `auto`,
and archives a failed `oneshot`'s stranded state the same way. Expected: 40 x ~325-425 s (A's measured periods), about
3.7-4.7 h plus ~11 min setup; watcher cap 8 h. A launch before about 2026-10-12 06:00Z leaves the 12:00Z deadline met even at
the slowest measured period.

After terminal: fetch to a **new** path (for example `tmp/teastorequiet2-evidence`), byte-verify against the host, check cell
validity only (A's procedure, `tmp/teastorequiet1-evidence`). Then `uv run python tools/wandb_campaign.py cells
teastore-quietA2 tmp/teastorequiet2-evidence/x`.

## Analysis
None until analysis v3.1 is frozen and reviewed (`BUDGET_QUIET_A2.md` rule 4). Allowed reads: cell validity, the runtime
journal, and the counts needed to fetch and verify.

## Coordinator's resolution of the open items
1. Frozen as `DECLARATION_QUIET_A2_TEASTORE.md`; the reused descriptor still names A's declaration, which stays binding for everything A2 does not change.
2. The harness-tree difference is accepted as an engineering default: quiet cells carry no `timing.faultHarness`, so B's H10/H4 code never runs for them, and `tests/test_teastore_sweep_b.py` pins quiet-selector behaviour to `91c4967`. The 3 moved controller digests are recorded; this is shown by tests, not on the host.
