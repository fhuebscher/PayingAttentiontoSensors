# OTel quiet calibration run A2: declaration (frozen 2026-10-10)

**Status: frozen** by committing this file alone, before the launch below. Collector log sampler ON as in A is the coordinator's engineering choice (A2 keeps A's carrier). Authority: protocol decision 68
(`research/PROTOCOL_DRAFT_20261002.md` round 17); budget and stop rule `research/traffic-sweep/BUDGET_QUIET_A2.md`: OTel terminal by
**2026-10-12 12:00Z**, at most 2 relaunches, 3 critical-path harness defects stop OTel's part of A2 (**1 of 3 used**, see "Defect 1").
Scope of every number: **instance** (one SUT, one host, fb14srv6).

## What A2 is
A second run of quiet run A (`DECLARATION_QUIET_OTEL.md` frozen `593d4ee`, `AMENDMENT_QUIET_OTEL_1.md` frozen `bf27aef`: decision 56,
trace loss recorded, never blocking): the same 40 no-fault cells (10 blocks x rates 10, 1, 0.2, 0.05 /s, 180 s measurement, posture
`full`), new run IDs, pooled with A for calibration under analysis v3.1. Epoch `otel-quiet-calibration-v1`, attempts 1 (spent, stopped
at cell 8) and 2 (A's relaunch 1, ran 40/40) are recorded spent; **A2 is attempt 3**.

## What differs from A (relaunch 1, attempt 2), and what does not
| item | A (relaunch 1) | A2 |
|---|---|---|
| harness commit | `6a47d0b37edb1f4a5c6d9b23bcb7dc184bfe9365` | **`0b67ee2c0904063579f7b2629641b3be711dcab1`** (branch `otel-protocol-20261002`) |
| attempt (`OTEL_CANDIDATE_ATTEMPT`) | 2 | **3** |
| plan canonical sha256 | `bb1eb1fc6bb4047b83c69d4d216d70b18f49dd7689c1245e4d0b7d0e18ffe8d6` | **`d82dcb2f0fed57ae450ed80cd1d708776fe9affced678fea1ab6fc70e91dfbcb`**, 40 cells |
| run IDs | attempt-2 IDs | **40 new IDs**; none of A's 80 (attempts 1 and 2) is reused (tested) |
| descriptor | `36a7fd173a9995e6b0c0e9897d98ff76995ca375e045b90804fe92221dfd2286` | **same** |
| compiler | `candidate_quiet.py` | **same bytes** (pinned against `6a47d0b` by test) |
| seed, block order, onset offsets, all timings | seed 20261004 | **same** (keyed by regime, rate and block, never by attempt; tested) |
| epoch name, campaign id, host paths | `otel-quiet-calibration-v1` | **same strings**; A's paths were moved aside first (below) |
| trace rule | decision 56 (recorded, never blocking) | **same** |
| collector log sampler | on (collector default) | **on, unchanged** (see "Choice for the coordinator") |
| GATE-RUN window, minimum remaining | 6 h, 14,740 s | **same** |
| SETUP-CAMPAIGN, GATE-PLAN, GATE-SETUP, GATE-RUN | A's records | new records on the new plan (the launcher renews SETUP-CAMPAIGN onto `d82dcb2f…`, archives stranded run-phase state, moves the old plan dir aside) |

Both plan digests are identical under `/usr/bin/python3 -I` (3.9.6, fresh `-X pycache_prefix`) and `uv run python -I` (3.13.12):
`candidate_quiet.py --print-digests --attempt {1,2,3}` (attempt 1 `f2e7158f…9fc6`, attempt 2 `bb1eb1fc…e8d6`, attempt 3 `d82dcb2f…dfbcb`), run at
`c4aa313` before the commits below, and pinned in `tests/test_otel_quiet_calibration.py` (the 3.9/3.13 identity test passes at HEAD).

**Behaviour between A's harness and A2's.** `6a47d0b` to `0b67ee2` also contains campaign B's changes (`candidate_repeat.py`, H10, H4
record-only, decision 66 for B only; `candidate_remote.py`, `candidate_runtime.py`, `candidate_setup.py`, `candidate_terminal.py`,
`materialize.py`). The quiet epoch's behaviour is pinned to `6a47d0b` by `tests/test_otel_repeat_episodes.py` (quiet/sweep files byte-identical;
the quiet trace record byte-identical to `6a47d0b`'s; the target runner and terminal treat a quiet cell as at `6a47d0b`; the materialized
source of the quiet epoch equals the base commit's). Those tests passed in the full-suite runs below. That is a test result, not a measurement
on the host: the first live check is the first sealed r10 cell (below).

## Choice for the coordinator: collector log sampler stays ON
Decision 66 (collector `service::telemetry::logs::sampling::enabled: false`) is written for campaign B's epoch only. A2 is pooled with A, which ran
with the default sampler on, so **A2 keeps A's carrier**: the quiet epoch is not in `materialize.COLLECTOR_LOG_SAMPLING_OFF_EPOCHS` (tested). The
consequence is that otelcol.log is the same lossy carrier as in A: a span missing from it is not evidence that the system lost it
(`OTEL_LOST_BATCH_DIAGNOSIS.md`), and decision 56 records such loss without blocking. If A2 should instead run sampling off, that needs the quiet epoch
added to that tuple, a new materialized-source digest, a new GATE-PLAN and a new DRY_RUN, and it makes A2's carrier differ from A's. Not done.

## Worktree commits (OTel worktree, all on top of `c4aa313`, tracked tree clean at HEAD)
| commit | what | governed file moved? |
|---|---|---|
| `0d2a146` | selector `study-epoch.json` -> `otel-quiet-calibration-v1`; tombstone `ADMITTED_STUDY_EPOCHS` in `candidate_setup.py` and `candidate_remote.py`; ledger text | no |
| `d219d6b` | `SPENT_ATTEMPTS_BY_EPOCH["otel-quiet-calibration-v1"][2]` (A relaunch 1, plan `bb1eb1fc`, 40/40); 5 new tests, planted defects | `candidate_runtime_adapter.py` |
| `d039908` | governance re-pin of `candidate_runtime_adapter.py` (sha256 `6e8c77d8…39b2`, sourceCommit `d219d6b`), rule of d101fda / fb02804 / 6a47d0b / 095ebab / c4aa313 | re-pin |
| `5d7db7d` | `tests/test_otel_gate_driver_shims.py` drives the first unspent attempt of the selected epoch (a literal attempt 2 is spent now) | `tests/test_otel_gate_driver_shims.py` (governance-bound) |
| `0b67ee2` | governance re-pin of `tests/test_otel_gate_driver_shims.py` (sha256 `0db6106b…0ee4`, sourceCommit `5d7db7d`) | re-pin |

Tests added in `tests/test_otel_quiet_calibration.py` (36 pass): attempt 3 plan pin; A2 = same descriptor, timings, schedule, new run IDs;
the adapter refuses attempts 1 and 2 and takes 3; every attempt that ran is recorded spent with its plan prefix (read from the adapter source);
**planted defects**: a missing or wrong spent row is found; with row 2 deleted the adapter plans A's relaunch-1 run IDs again (shown); and a
**source plant** (row 2 removed from the adapter) made 3 tests fail; the file was restored (diff checked). The quiet carrier keeps the default sampler.

## Defect 1 of 3 (critical path, this prep)
My activation commit `0d2a146` made attempts 1 and 2 spent for the selected epoch. The full suite then showed 1 failure + 1 error in
`tests/test_otel_gate_driver_shims.py` (a fixture hard-coded attempt 2): fixed in `5d7db7d`. That commit moved a governance-bound file without a
re-pin, which `tests/test_otel_v2_epoch.py::test_every_source_binding_names_bytes_that_exist_at_its_commit_and_now` caught (the coordinator
spotted it in the second full run): re-pinned in `0b67ee2`. Cause class: activation changes which attempts are spent, and the shim tests and
governance pins track that. Time on it: well inside 30 minutes of work.

## Suite comparison (full suite, `uv run pytest -q -p no:cacheprovider -rf --ignore=tests/test_mlflow_manifest.py`)
| tree | result |
|---|---|
| worktree HEAD `0b67ee2` | **29 failed, 2166 passed, 145 skipped** (539 s) |
| baseline `c4aa313`, scratch clone (symlinked `upstream/opentelemetry-demo`; the other four submodule dirs are empty, as in the worktree) | 30 failed, 2160 passed, 145 skipped (541 s) |

The 29 FAILED names at HEAD are a **subset** of the baseline's 30 (`diff` of the sorted name lists): the one extra baseline failure is
`tests/test_teastore_native_bridge_patch.py::test_v2_patch_applies_to_the_exact_pinned_source_without_mutating_it`, which asserts `git status` is
empty and found ` T upstream/opentelemetry-demo`, i.e. an artifact of my symlink in the clone, not of the code. So the failing set at HEAD equals the
baseline's set apart from that clone artifact; these 29 are Hotel materialize, Kieker fixture, Online Boutique, phase-1 control universe (bound to
`materialize.py` / `compose.otel-placement.yml`, which B moved), science router and TeaStore tests. None is OTel and none is new. Earlier HEAD runs: 30 failed
+ 1 error after `0d2a146` + `d219d6b` (shim regression), 30 failed after `5d7db7d` (governance drift). Scope: these are suite results, not evidence a campaign
will run (CLAUDE.md).

## Verification before launch (2026-10-09/10, read-only except where stated)
- **Fetch gate.** Campaign B's `candidate_runtime.py fetch` had exited; `tmp/otel-b-evidence/b1-fetch.{host,local}.sha256` exist; receipt `terminal-valid`.
  No cell content opened.
- **A's evidence is safe locally.** `tmp/otel-quiet-evidence/relaunch1-fetch` has 647 files, equal to the host's file count at the move; the host and local
  sha256 lists are identical (`cmp`; written 2026-10-05; not re-hashed on the host now); fetch receipt `terminal-valid`.
- **Host move (done 19:59:30Z).** `tmp/otel_quiet_a2_archive.sh` (move, never delete; refuses unless idle), report-only first, then `--archive`:
  `…-runs/otel-quiet-calibration-v1`, `…-runs/.setup-otel-quiet-calibration-v1`, `…-otel-srv6/otel-quiet-calibration-v1-6a47d0b37edb` renamed to
  `.archived-…-quiet-a2-20261009T195930Z`; the archived artifact root holds 647 files; B's paths (`otel-repeat-episodes-v1`, its `.setup-`) untouched.
- **fb14srv6 idle, re-checked 23:32Z and in both DRY_RUNs:** 0 units, 0 containers, no lease holder, 244 GB free, 0 quiet-epoch paths.
- **Posture-probe receipt** `.local/candidate-v4/otel-demo/gates/posture-probe-receipt.json`: `PROBE OK`, 0 disabled / 42 enabled OTLP connections (a
  connection-count probe, recorded 2026-09-23); `probeScriptSha256` equals `shasum -a 256` of `modules/otel-demo/tools/posture_connection_probe.sh` now
  and `upstreamCommit` equals the worktree's `upstream/opentelemetry-demo` gitlink. I did not re-run the probe.
- **DRY_RUN** (`scratchpad/gate-drivers/otel-quiet-quietA2dry2-launch.log`, 23:41Z, HEAD `0b67ee2`, tracked tree clean; an earlier `quietA2dry1` at 23:32Z agrees):
```
23:41:17Z === otel offpath launcher quietA2dry2 (HEAD 0b67ee2c0904063579f7b2629641b3be711dcab1 on otel-protocol-20261002, compiler candidate_quiet.py, plan d82dcb2f0fed57ae450ed80cd1d708776fe9affced678fea1ab6fc70e91dfbcb, 40 cells, attempt 3, dry=1) ===
23:41:17Z untracked files (tolerated, as in runs 1-3): 0
23:41:17Z compiled: otel-quiet-calibration-v1 40 d82dcb2f0fed57ae450ed80cd1d708776fe9affced678fea1ab6fc70e91dfbcb
23:41:17Z drivers: otel-quiet-calibration-v1 otel-quiet-calibration-v1 6 <worktree>
probe receipt 2026-09-23T10:03:11Z 23dd90bb20f5 0 42
23:41:45Z host fb14srv6: running units=0 containers=0 lease holders=[] free GB=244 otel-quiet-calibration-v1 paths=0
23:41:45Z DRY: would archive run-phase state and the plan dir, read SETUP-CAMPAIGN status, and renew it onto d82dcb2f… if expired/drifted
23:41:45Z DRY RUN: all guards passed; stopping before the first mutation
```
- **Not shown by the DRY_RUN:** the SETUP-CAMPAIGN renewal, `auto` (upload, install, readiness), `oneshot`, the cell period. A passed all of them on the
  same compiler and plan shape; the harness commit differs, so the first live evidence is the first sealed r10 cell.

## Launch (only after this declaration is frozen and committed alone, and HEAD of the worktree is still `0b67ee2…`)
From the measurement repo (`<frozen>` = the full 40-hex HEAD; re-run `git -C ../observability-placement-runtime-otel-protocol rev-parse HEAD`):
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=3 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_quiet.py EXPECTED_PLAN=d82dcb2f0fed57ae450ed80cd1d708776fe9affced678fea1ab6fc70e91dfbcb \
  RUN_COUNT=40 CAMPAIGN=otel-quiet-calibration-v1 LOG_PREFIX=otel-quiet \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh quietA2 0b67ee2c0904063579f7b2629641b3be711dcab1 \
  > scratchpad/gate-drivers/otel-quietA2.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow otel-quietA2 scratchpad/gate-drivers/otel-quiet-quietA2-launch.log \
  > scratchpad/gate-drivers/otel-quietA2-wandb.out 2>&1 &
```
Expected: 40 cells at about 303-315 s each (A's relaunch 1 cell period), roughly 3.4-3.7 h plus about 5 min setup; GATE-RUN window 6 h, watcher cap 7 h.
Check the first r10 cell as soon as it seals: `trace-completeness.json` schema 3, `rule: protocol-decision-56`; `container-health.json` valid.
After terminal: fetch to a **new** path (for example `tmp/otel-quiet-evidence/a2-fetch`, never into `relaunch1-fetch`), byte-verify the host and local sha256 lists, read cell
validity only (`BUDGET_QUIET_A2.md` rule 4: cells are read only through the frozen, reviewed analysis v3.1).

## Consequences and open items (stated, not hidden)
- A and A2 share the campaign id `otel-quiet-calibration-v1` and the artifact-root names (the campaign id does not change with the attempt); their run IDs differ.
  Any pooling must key on the fetch directory (campaign + attempt), and `tools/evidence_inventory.py` needs a check before it touches the pooled evidence.
- A2 repeats A's cell order and onset phases (same schedule keyed by regime, rate, block); position in the campaign (host drift) is not an independent draw.
- Campaign B cannot be re-fetched or replayed from the worktree at HEAD (the selector now names the quiet epoch); that needs `c4aa313` checked out.
- `SPENT_ATTEMPTS_BY_EPOCH["otel-repeat-episodes-v1"]` is still `{}` although B attempt 1 ran; mark it spent before any B relaunch (outside this prep).
- The reviewer's M3 from `AMENDMENT_QUIET_OTEL_1.md` still holds (the terminal does not re-derive the correlation from `otelcol.log`).
- No independent review (judge or Fable subagent) of this prep has been made; the checks above are my own tests and read-only host checks.
