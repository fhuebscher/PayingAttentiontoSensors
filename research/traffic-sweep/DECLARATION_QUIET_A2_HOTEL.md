# Quiet calibration run A2 on HotelReservation: declaration (FROZEN 2026-10-09, committed alone before launch)

**Status: frozen.** Committed alone before launch; no cell had run. Authority: protocol decision 68 (round 17, `research/PROTOCOL_DRAFT_20261002.md`). Budget and stop rule:
`BUDGET_QUIET_A2.md` (0bf4cf8, committed alone): Hotel launch-ready by 2026-10-10 06:00Z, terminal by 2026-10-10
18:00Z, at most 2 relaunches, 3 critical-path defects stop Hotel's part of A2. Scope of every number: **instance**
(one SUT, one host).

## What A2 is
A second run of quiet run A (`DECLARATION_QUIET_HOTEL.md`, frozen 2bf2e76) **on the same frozen harness and plan, with
nothing changed**. It adds 40 no-fault cells (10 blocks x rates 10, 1, 0.2, 0.05 /s, 180 s measurement, posture `full`)
to be pooled with A for calibration under analysis v3.1 (decision 67, decision 68).

## What differs from A, and what does not
| item | A | A2 |
|---|---|---|
| harness commit | `e9d35f7` (worktree `observability-placement-runtime-hotel-protocol`) | **same**, no framework commit, tree clean |
| epoch / descriptor | `hotel-quiet-calibration-v1`, `fa42391d…` | **same** |
| plan canonical sha256 | `554a7a1e753a7f3535a7ae1c796cceee986bf0b1ae4b629858de2a547d79b127`, 40 cells | **same** |
| run IDs, artifact roots, `attempt` | `no-fault-calibration-r<rate>-b<NN>-full-a01`, `attempt-01` | **same strings** |
| schedule seed, cell order, onset offsets | seed 20261004, one shuffle over 40 cells | **same** (they are literals in the compiler) |
| campaign ID | `hotel-v1-20261004t082015z-b71377d4` | **new**, minted at launch (`hotel-v1-<UTC stamp>-<8 hex>`); not known before launch |
| SETUP-CAMPAIGN, GATE-PLAN, GATE-SETUP, GATE-RUN, preflight | the A records | **new records, same plan**; SETUP-CAMPAIGN was renewed 2026-10-04T08:19:01Z and is live to 2026-10-11T08:19:01Z (`status`: live=True, invariants match=True); the launcher renews it if it has expired |
| launcher label / logs | `quiet1`, `hotel-quiet1-launch.log` | `quietA2`, `hotel-quietA2-launch.log` |
| host, ports, lease | fb14srv4, 35005 / 36685 | same host; A's host paths are moved aside by the launcher before `auto` |

**Nothing else differs.** Cell shape, rates, warm-up, posture, pseudo window, gates (G1, G2, G4, decision 25), capture,
budget (14,400 s wall, 4 h; watcher cap 5 h), and the analysis rule (no read until v3.1 is frozen and reviewed;
`BUDGET_QUIET_A2.md` rule 4) are A's.

**Why the plan is not distinct.** The compiler has no attempt, campaign or seed input: `attempt` is the literal 1, the
run-ID regexes in `candidate_quiet.py:87`, `candidate_sweep.py:155` and `workload/candidate_search.py:37,45` end in
`-a01`, and the seed, epoch name and run IDs are module constants. The plan digest is a pure function of them, so any
distinct plan needs a framework commit (a new compiler, epoch, descriptor, selector, runtime policy, driver config and
tests, then a re-typed GATE-PLAN). Decision 68 asks for "same cell shape", not a new plan, and the launcher has
replicated the same plan on the same commit before without a framework change (`sel1`, `rep1`, `rep2`, plan
`189604cc…`, HEAD `e4fd4c7`, each ran to terminal). So A2 reuses the plan, and this is an **engineering default, recorded**.

## Consequences of reusing the plan (stated, not hidden)
- **All 40 run IDs and artifact roots equal A's.** Within a campaign directory they are unique; across A and A2 they are
  told apart only by the campaign ID (A's `m1` minor, now 40 of 40 instead of 4 of 40 plus the sweep). Any pooling must key on
  `(campaign ID, run ID)`. `tools/evidence_inventory.py:236` reads `plan["blocks"]` and needs a check before it touches
  quiet evidence. Fetch A2 to its own `tmp/` path; never into `tmp/hotelquiet1-evidence`.
- **The cell order and the pseudo-window onset offsets repeat A's.** A2 is therefore a replicate of A's schedule, not an
  independent draw of order or onset phase. For the quiet-time use (the whole 180 s measurement counts as quiet, decision
  48), the phase is not a quantity of interest, but position in the campaign (host drift) repeats too. The coordinator kept the
  replicate as an engineering default (each cell is a fresh deployment, so the cells are independent draws of system
  behaviour; a new seed would cost a framework commit and a re-typed GATE-PLAN). Cell order stays confounded with rate
  exactly as in A; recorded as a limitation.
- **A's evidence is untouched.** A's campaign is fetched at `tmp/hotelquiet1-evidence` and archived for the launcher
  guard at `tmp/hotel6-evidence/hotel-v1-20261004t082015z-b71377d4.tgz` (68 MB, present).

## Verification (2026-10-09, no commit made)
- Worktree clean, HEAD `e9d35f7fffcab4134b53a864cd36613cc628cb4d`.
- `candidate_quiet.py` gives descriptor `fa42391d…` and plan `554a7a1e…`, 40 runs, **identical under `/usr/bin/python3 -I -B`
  (3.9.6, fresh pycache prefix) and `/opt/homebrew/bin/python3.13 -I`**.
- fb14srv4 read-only: uptime 640 d, **0 containers, empty compose listing**, no hotel, candidate or campaign process,
  172 GB free, lease `.hotel-candidate-v1.lock` is A's (campaign `…b71377d4`, deadline 2026-10-04T12:20:15Z, expired),
  one run dir on the host (`hotel-v1-20261004t082015z-b71377d4`).
- **Not shown by the DRY_RUN:** the SETUP-CAMPAIGN renewal (not needed now), `auto` (upload, install, readiness),
  `oneshot`, the cell period. The A1 run passed all of them on this commit and plan.

### Dry run (2026-10-09 10:59Z, `DRY_RUN=1`, read-only against fb14srv4)
Log `scratchpad/gate-drivers/hotel-quietA2dry1-launch.log`:
```
10:59:12Z === hotel launcher quietA2dry1 (HEAD e9d35f7 on hotel-protocol-20261002, plan 554a7a1e753a7f3535a7ae1c796cceee986bf0b1ae4b629858de2a547d79b127, 40 cells, dry=1) ===
10:59:20Z previous runs on host: 1 [hotel-v1-20261004t082015z-b71377d4 ]
10:59:29Z host preflight: containers=0 compose=[]  free GB=172
10:59:29Z setup-campaign status: HEAD e9d35f7fffcab4134b53a864cd36613cc628cb4d authorized 2026-10-04T08:19:01Z deadline 2026-10-11T08:19:01Z live=True invariants match=True
10:59:29Z DRY RUN: all guards passed; stopping before the first mutation
```

## Launch (only after this declaration is frozen and committed alone)
From the measurement repo:
```
HOTEL_ROOT=$PWD/../observability-placement-runtime-hotel-protocol COMPILER=candidate_quiet.py \
EXPECTED_PLAN=554a7a1e753a7f3535a7ae1c796cceee986bf0b1ae4b629858de2a547d79b127 RUN_COUNT=40 \
nohup caffeinate -i zsh scratchpad/gate-drivers/launch_hotel.sh quietA2 > scratchpad/gate-drivers/hotel-quietA2.out 2>&1 &
```
Monitoring only (the fetched campaign directory is the evidence of record):
```
nohup uv run python tools/wandb_campaign.py follow hotel-quietA2 scratchpad/gate-drivers/hotel-quietA2-launch.log \
  > scratchpad/gate-drivers/wandb-hotel-quietA2.out 2>&1 &
```
Expected: 40 x 246-262 s, about 2.7-2.9 h plus setup. If the launch is after 2026-10-11T08:19:01Z the launcher renews
SETUP-CAMPAIGN itself. After terminal: fetch to a new `tmp/` path, archive to
`tmp/hotel6-evidence/<campaign-id>.tgz`, byte-verify, check cell validity only. The runtime stops on the first invalid
cell; at 0.2 and 0.05 /s one failed pre-onset request fails G2 (A's rule).

## Analysis
None until analysis v3.1 is frozen and reviewed (`BUDGET_QUIET_A2.md` rule 4). Allowed reads: cell validity, the runtime
journal, and the counts needed to fetch and verify.
