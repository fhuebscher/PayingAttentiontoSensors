# OTel campaign C (clean placement test run): declaration (frozen 2026-10-10)

**Status: frozen 2026-10-10** by committing this file alone (coordinator). The placement design was frozen by digest before this launch (d9638e1, BUDGET_PLACEMENT.md step 1), as decision 82 requires. The new seed 20261011, the schedule version and the run-ID keying are the coordinator's engineering defaults (recorded here; they change no measured quantity's definition). No independent review of the harness build was made (judge server unavailable); its checks are the preparing agent's tests with planted defects, the suite comparison and the DRY_RUN. Online Boutique is not part of the test (decision 83).

Draft only. Freezing means committing it alone under the file name `research/traffic-sweep/DECLARATION_C_OTEL.md`, the path the
pinned descriptor's `declaration` entry names (any other name regenerates the descriptor, the digests and the DRY_RUN). Nothing has been
launched, no declaration frozen, no C cell exists. Scope of every number here: **instance** (one SUT, one host, fb14srv6).

Authority: `research/PROTOCOL_DRAFT_20261002.md` **decision 82** (round 22, user 2026-10-10: clean placement test runs; campaign C on TeaStore and
OTel, the same 36-cell shape as campaign B with new blocks, after the placement design is frozen by digest; fault cells scored only by the frozen
placement). B's decisions carry over unchanged: 49, 50, 56, 66 (collector log sampler off), 69 (H4 recorded, never blocking).
Budget and stop rule: `research/traffic-sweep/BUDGET_C.md` (`d5b9af0`, committed alone before any C work): harness ready by **2026-10-11 12:00Z**,
terminal and fetched by **2026-10-12 12:00Z**, at most 2 relaunches, 3 critical-path harness defects stop OTel's part of C (**0 of 3 used**).
Placement design: `research/protocol/BUDGET_PLACEMENT.md` (frozen `d9638e1`); C's fault cells are read only through it (step 6).

## What C is
Campaign B (`DECLARATION_B_OTEL.md`, harness `c4aa313`) again, **exactly**: 36 cells = 3 blocks x 3 regimes (no fault, frontend pause,
productcatalogservice CPU throttle to 0.1 core) x 4 rates (10, 1, 0.2, 0.05 /s), posture `full`, H10, H4 recorded and never blocking, collector log
sampler off, decision 25 in fault cells and decision 56 in no-fault cells. New study epoch, new block orders, new onsets, new run IDs. Its no-fault cells
are a second fresh false-alarm check, **never pooled into a calibration**; its fault cells are a held-out test of the frozen placement, never used to tune it.

## Binding changes (against campaign B)
| item | campaign B (attempt 1) | campaign C |
|---|---|---|
| study epoch | `otel-repeat-episodes-v1` | **`otel-repeat-episodes-c-v1`** (new; B and every earlier epoch unchanged) |
| harness commit | `c4aa313fdfe89c330513146e6098ddf723213ffb` | **`8018a194892a901222b2b4e0655eef131bc776ae`** (branch `otel-protocol-20261002`) |
| compiler | `candidate_repeat.py` | **`candidate_repeat_c.py`**, which reads B's compiler and B's pinned descriptor and edits neither |
| seed | 20261009 | **20261011** (engineering default: the build date, as 20261003 / 20261004 / 20261009 before; recorded here) |
| block orders (first 12 hex of `orderSha256`) | b1 `a6f521c01240`, b2 `6fac3bab1afa`, b3 `6d2fed2b949d` | **b1 `035346f10af9`, b2 `30c81cc24ab2`, b3 `b564bcc373fb`** |
| fault onsets | B's draws | **new draws** (same function, 3 strata per (regime, rate) over the blocks; all 36 onsets differ from B's for the same cell, tested) |
| run IDs | B's 36 | **36 new**; none equals a run ID of sweep attempts 1-2, quiet A / A2 (attempts 1-3) or B attempt 1 (tested) |
| descriptor | `6e5d0f34...81a4ce` | **`6dd3cb7215db438cdf2f0618dd62eed583b86004f5f0254c565eabe93cc13721`** |
| plan, attempt 1 | `3aaf5923...2b142` | **`ece8caa0552fc0bc03ef2cd51f7560e7a8c6f54e96c29755a75d37168609b744`** |
| declaration path in the descriptor | `DECLARATION_B_OTEL.md` | **`DECLARATION_C_OTEL.md`** |
| host paths | `...-runs/otel-repeat-episodes-v1`, `.setup-...`, `...-otel-srv6/otel-repeat-episodes-v1-c4aa313fdfe8` | `...-runs/otel-repeat-episodes-c-v1`, `.setup-otel-repeat-episodes-c-v1`, `...-otel-srv6/otel-repeat-episodes-c-v1-8018a194892a` (absent on the host now) |
| Compose project | `otel_candidate_v4_otel_repeat_episodes_v1` | `otel_candidate_v4_otel_repeat_episodes_c_v1` |

**Unchanged from B, by construction and tested.** `candidate_repeat_c.cell_timing(regime, rate, block)` starts from B's own
`candidate_repeat.cell_timing(regime, rate, block)` and replaces only the four keys that follow from the onset draw (`faultOnsetPhaseOffsetSeconds`,
`faultOnsetSeconds`, `scoredWindowSeconds`, `scheduledSlotsByPhase`, by B's formulas); every other timing key equals B's for the same cell (tested for all
36). That covers route, rates, client timeout 15 s, concurrency 300, warm-up 30 s, measurement 180 s, hold 60 s, `duringFaultProbe: false` (H10),
`freezeStamps: true` (H4), the trace rule per cell kind, `planRunCount` 36, `planMinimumRemainingSeconds` **13,416 s**, frontendproxy memory 256 MiB, the
container-health guard and the protocol gates (F1, G1, G2, G4 blocking). GATE-RUN window **5 h**. The descriptor is generated from B's pinned descriptor and
differs from it in exactly `id`, `declaration`, `schedule`, `derivedFrom` (B's record, with B's own `derivedFrom` nested) and `design.purpose`,
`outcomes.primary`, `analysis.comparativeUnit`, `analysis.analysisFreeze` (tested: no other key differs; a planted drift in `timing` or `faultDesign` is found).
`amendments` is `[]` as in B.

- Both digests are identical under `/usr/bin/python3 -I` (3.9.6, fresh `-X pycache_prefix`) and `uv run python -I` (3.13): command
  `candidate_repeat_c.py --print-digests --attempt 1`, run 2026-10-10 at the epoch commit, and pinned by
  `tests/test_otel_repeat_episodes_c.py::test_the_digests_are_identical_under_python39_isolated_and_this_interpreter` (passes at HEAD).
- Spent attempts for the epoch: none; its first launch is attempt 1. **B attempt 1 is now recorded spent** (`8d41a95`, the open row from
  `DECLARATION_QUIET_A2_OTEL.md`): a B relaunch would be attempt 2.
- Materialized-source digest the GATE-PLAN will carry (local projection, `candidate_transport._projected_materialized_source_sha256`, run 2026-10-10 at HEAD):
  `18fe429c0bcc64a26f641b95223e01688c4f5f2e8451de4c4268cf7f5c55d860`, equal to B's (C renders the materialized tree byte for byte as B, collector log sampler
  off included; tested file by file).

### Commits in the OTel worktree (all on top of `0b67ee2`, tracked tree clean at HEAD)
| commit | what | governed file moved? |
|---|---|---|
| `8d41a95b358456f36e5e264ab2f1845ba9c52f58` | `SPENT_ATTEMPTS_BY_EPOCH["otel-repeat-episodes-v1"][1]` (B attempt 1, plan `3aaf5923`, harness `c4aa313`, fetch terminal-valid, 619/619); 2 new tests + B's adapter test updated; source plant (row removed) fails 2 tests | `candidate_runtime_adapter.py` |
| `b78b40fc7706dc132d4a738a04f407f04ecdd252` | campaign C epoch, not activated: `candidate_repeat_c.py`, descriptor `otel-repeat-episodes-c-v1.json`, `REPEAT_STUDY_EPOCHS = (B, C)` in `candidate_remote.py`, C's controller set and timing keys in `candidate_runtime.py` / `candidate_setup.py`, `SPENT[C] = {}`, C in `materialize.COLLECTOR_LOG_SAMPLING_OFF_EPOCHS`, ledger +1, `tests/test_otel_repeat_episodes_c.py` (26) | `candidate_runtime.py`, `candidate_runtime_adapter.py` |
| `999cfc95a65947b0b360bc9593a5521df3a2eb0d` | governance re-pin of both (bytes at `b78b40f` == working tree; every other sourceBinding checked unchanged) | re-pin |
| `8018a194892a901222b2b4e0655eef131bc776ae` | activation: selector names C; tombstone `ADMITTED_STUDY_EPOCHS = ("otel-repeat-episodes-c-v1",)` in `candidate_setup.py` and `candidate_remote.py`; ledger text | no |

`candidate_terminal.py` did not move: it reads the H10/H4 and trace-rule predicates from `candidate_remote.py`, which now key on the repeat family (B, C).

## The 36 cells (attempt 1; onset = seconds after the barrier at which the fault command is issued)
Every block holds all 12 (regime, rate) pairs once.

| block | pos | regime | rate /s | onset s | run id |
|---|---|---|---|---|---|
| 1 | 1 | frontend-pause | 0.2 | 61.647 | ea093f2654e58f16f64f7c2e |
| 1 | 2 | productcatalog-throttle | 1 | 60.064 | b00a1824526bc765a9ca0d71 |
| 1 | 3 | no-fault | 1 | 60.051 | faa32e693401c40ecd7cff7d |
| 1 | 4 | no-fault | 0.2 | 63.275 | cb370ce37adb7488bb68c37d |
| 1 | 5 | no-fault | 0.05 | 69.726 | 99581713fde15689a3d1a719 |
| 1 | 6 | frontend-pause | 1 | 60.884 | 6a7dcc65b4d0a935f634a884 |
| 1 | 7 | no-fault | 10 | 60.095 | 1b6d9e75191016f9739da87a |
| 1 | 8 | frontend-pause | 10 | 60.078 | fc2038e95ddec25ed19e6267 |
| 1 | 9 | productcatalog-throttle | 0.05 | 75.959 | 07f432411b259c1cb39dd2d9 |
| 1 | 10 | productcatalog-throttle | 10 | 60.012 | d10867ef598855539142e14f |
| 1 | 11 | frontend-pause | 0.05 | 65.981 | 8ee9e57aa8c18549e7162472 |
| 1 | 12 | productcatalog-throttle | 0.2 | 64.055 | fa171ebf44b245bd5cb5dcaa |
| 2 | 1 | productcatalog-throttle | 10 | 60.067 | e36aaf402f44a1474ed4c13a |
| 2 | 2 | frontend-pause | 0.05 | 74.483 | 0a20f151330ed8ee4a8a4adb |
| 2 | 3 | productcatalog-throttle | 1 | 60.406 | 096bb4af592c03b1d80284d4 |
| 2 | 4 | frontend-pause | 10 | 60.001 | 28d3c558479fb8e6b7ee4602 |
| 2 | 5 | frontend-pause | 1 | 60.072 | 74f7b176a8d72bae8ca709f1 |
| 2 | 6 | productcatalog-throttle | 0.05 | 60.988 | ee45c6fbcf639e6fc260b398 |
| 2 | 7 | no-fault | 0.2 | 63.653 | 09ca2a146428ec448e85032f |
| 2 | 8 | frontend-pause | 0.2 | 62.491 | 790d901f27e498c34d1d04cd |
| 2 | 9 | no-fault | 1 | 60.601 | 33899c277b9863834756b328 |
| 2 | 10 | no-fault | 0.05 | 64.527 | e0bccdadf40f07a0aabd9c91 |
| 2 | 11 | productcatalog-throttle | 0.2 | 61.624 | 3aadfc26f163bb519ed2c6a2 |
| 2 | 12 | no-fault | 10 | 60.032 | f796bd0cbdc69174cc19f5e2 |
| 3 | 1 | productcatalog-throttle | 0.2 | 62.938 | 44fa2cb77817e33088135868 |
| 3 | 2 | productcatalog-throttle | 0.05 | 69.303 | 0df0af54091b4248c685673e |
| 3 | 3 | productcatalog-throttle | 10 | 60.067 | fdbfe5ba4efd346639dda4d0 |
| 3 | 4 | frontend-pause | 0.2 | 63.610 | 14c85a9dad0c5a515869a89c |
| 3 | 5 | no-fault | 1 | 60.677 | bb982d6cc35bfc30df5e7f63 |
| 3 | 6 | productcatalog-throttle | 1 | 60.975 | 2495699fc71e39b2f2c68541 |
| 3 | 7 | no-fault | 10 | 60.044 | eff0c84cb2cc6b46e9d5773e |
| 3 | 8 | frontend-pause | 10 | 60.066 | c1c24169285f377c52ab0e23 |
| 3 | 9 | no-fault | 0.2 | 61.569 | eb42c7cd9766a9505d711719 |
| 3 | 10 | frontend-pause | 0.05 | 69.060 | dae73bd9ec257a0a69b52385 |
| 3 | 11 | no-fault | 0.05 | 74.677 | 038247de445f9c967b2cfed6 |
| 3 | 12 | frontend-pause | 1 | 60.557 | 27aa89850dcf504f2b9bb86a |

(Generated from the compiled plan at HEAD. Onsets are the plan's; the fault command may be issued up to 0.05 s early and F1 allows 1 s late. No-fault cells
carry the same seeded window as a pseudo window for G1/G2 and false alarms.) No lead cell, as in B: the first pause cell is block 1 position 1 (0.2 /s) and
must be checked by hand when it seals.

## Rules that apply to each cell (B's, unchanged; see `DECLARATION_B_OTEL.md` for the full text)
- **Trace completeness.** Fault cells (24): decision 25, no timing key, blocking above max(1, 1 %) outside the fault-and-drain window. No-fault cells (12):
  decision 56, timing key `traceCompletenessRule = "protocol-decision-56"`, recorded, never blocking. Enforced per cell kind
  (`candidate_remote.names_trace_rule`, now true for the no-fault cells of B **and C**, and the runtime's per-epoch key sets, C's equal to B's).
- **H10.** No readiness probe from the onset command's issue to the end of the hold; `duringRouteAvailable` is `null`; manifestation rests on the read-back
  container state (and, for a pause, the Docker `pause` event recorded beside it).
- **H4, recorded and never blocking (decision 69).** Freeze stamps in every fault receipt; pause cells retain `docker-events.json`; a `missing` or
  `contradictory` record leaves the cell valid; a record that does not replay from its own raw lines, clock and receipt is refused (integrity).
- **Decision 66.** The collector config renders `service::telemetry::logs::sampling::enabled: false` when the committed selector names B or C
  (`materialize.COLLECTOR_LOG_SAMPLING_OFF_EPOCHS = ("otel-repeat-episodes-v1", "otel-repeat-episodes-c-v1")`). C's rendered tree equals B's file for file;
  the quiet and sweep epochs keep the default sampler (tested).
- Blocking in every cell: G1, G2, G4 (F1 in fault cells), the container-health guard, the H10/H4 flag/contract guard, and the terminal's ledger, witness,
  generator-absence, posture, application-log and integrity replays. Campaign stop rule: first invalid cell.

## Tests and suites (OTel worktree, `uv run pytest -q -p no:cacheprovider -rf --ignore=tests/test_mlflow_manifest.py`)
| tree | result |
|---|---|
| baseline `0b67ee2` (the worktree itself, before any change, clean) | 29 failed, 2166 passed, 145 skipped (550 s) |
| HEAD `8018a19` (clean) | **29 failed, 2194 passed, 145 skipped** (574 s) |

The sorted `FAILED` name lists are **identical** (`diff`, no output): Hotel materialize 4, Kieker fixture 1, Online Boutique 13, phase-1 control universe 6,
science router 1, TeaStore 4. None is OTel. Delta +28 passed, fully attributed: +26 in the new `tests/test_otel_repeat_episodes_c.py`, +2 new tests in
`tests/test_otel_repeat_episodes.py` (B attempt 1 recorded spent; planted missing/wrong row); skipped unchanged. Logs and name lists:
`tmp/otel-c-prep/` (gitignored) `suite-baseline-0b67ee2.txt`, `suite-head-8018a19.txt`, `failed-*.txt`.

Planted defects, each run and restored (diff checked):
- **plan pin**: descriptor edits (B's seed, H10 off, a 6 h window, B's declaration path) refused and move the digest; plan edits (onset, a dropped cell,
  H4 off, a cell or plan re-labelled with B's epoch) refused; a wrong reviewed pin refused. Source plant: C's epoch id set to B's -> 9 failed + 6 errors.
- **no run-ID reuse**: C's compiler with B's epoch (with B's seed, or with C's) plans exactly B attempt 1's 36 run IDs and the check reports them.
- **B-shape identity**: a descriptor drift in `timing.budget` and `faultDesign.scenarios` is reported outside the declared keys.
- **membership**: C dropped from `REPEAT_STUDY_EPOCHS` -> 5 failed (the runner refuses C's H10/H4 keys, the trace rule flips); C dropped from the
  sampling-off tuple -> 2 failed (the config keeps the sampler).
- **spent row**: B's row removed from the adapter source -> 2 failed.

Measurement repo `tests/test_unbound_names.py`: 317 passed, one parametrisation is `candidate_repeat_c.py` (+1 from this change; B's record said 315, the
other +1 comes from another session's module and is not attributed here).

Not verified: the per-cell runner has run only against the fake target (as for every epoch); C's code paths on the host are B's, which ran 36/36 on
fb14srv6 on 2026-10-09 (`c4aa313`), but the harness commit differs, so the first live evidence is the first sealed C cell.

## Verification before launch (2026-10-10, read-only)
- **B's evidence is safe locally**: `tmp/otel-b-evidence/b1-fetch` (36 cell directories), `b1-fetch.host.sha256` and `b1-fetch.local.sha256` identical
  (`cmp`, 619 lines each), fetch receipt `terminal-valid`. No cell content opened.
- **fb14srv6 idle** (read-only ssh, stdout only, about 18:20Z and again in the DRY_RUN at 18:27Z): 0 units, 0 containers, no lease holder, 243 GB free, 0 C paths. The host paths of
  A (archived `...quiet-a1...`), A2 (`otel-quiet-calibration-v1`, `.setup-otel-quiet-calibration-v1`, `otel-quiet-calibration-v1-0b67ee2c0904`) and B
  (`otel-repeat-episodes-v1`, `.setup-otel-repeat-episodes-v1`, `otel-repeat-episodes-v1-c4aa313fdfe8`) are present and untouched. **No move-aside was needed**:
  C's paths carry its own epoch id, and no guard asked for one.
- **Posture-probe receipt** `.local/candidate-v4/otel-demo/gates/posture-probe-receipt.json`: `PROBE OK`, 0 disabled / 42 enabled OTLP connections
  (connection-count probe, recorded 2026-09-23); `probeScriptSha256` equals `shasum -a 256` of `modules/otel-demo/tools/posture_connection_probe.sh` now
  and `upstreamCommit` equals the worktree's `upstream/opentelemetry-demo` gitlink (`2d4661e4`). Not re-run (no posture changed; the collector config
  differs from the receipt's time only in its own log sampler, as in B).
- **DRY_RUN** (`scratchpad/gate-drivers/otel-repeat-c-cdry1-launch.log`, HEAD `8018a19`, tracked tree clean):
```
18:27:20Z === otel offpath launcher cdry1 (HEAD 8018a194892a901222b2b4e0655eef131bc776ae on otel-protocol-20261002, compiler candidate_repeat_c.py, plan ece8caa0552fc0bc03ef2cd51f7560e7a8c6f54e96c29755a75d37168609b744, 36 cells, attempt 1, dry=1) ===
18:27:20Z untracked files (tolerated, as in runs 1-3): 0
18:27:20Z compiled: otel-repeat-episodes-c-v1 36 ece8caa0552fc0bc03ef2cd51f7560e7a8c6f54e96c29755a75d37168609b744
18:27:20Z drivers: otel-repeat-episodes-c-v1 otel-repeat-episodes-c-v1 5 <worktree>
probe receipt 2026-09-23T10:03:11Z 23dd90bb20f5 0 42
18:27:47Z host fb14srv6: running units=0 containers=0 lease holders=[] free GB=243 otel-repeat-episodes-c-v1 paths=0
18:27:47Z DRY: would archive run-phase state and the plan dir, read SETUP-CAMPAIGN status, and renew it onto ece8caa0... if expired/drifted
18:27:47Z DRY RUN: all guards passed; stopping before the first mutation
```
- **Not shown by the DRY_RUN:** the SETUP-CAMPAIGN renewal, `auto` (upload, install, readiness), `oneshot`, the cell period.

## Launch (only after: this draft frozen as `DECLARATION_C_OTEL.md` and committed alone; the placement frozen by digest (decision 82); worktree HEAD still `8018a19...`)
From the measurement repo (re-run `git -C ../observability-placement-runtime-otel-protocol rev-parse HEAD` first):
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_repeat_c.py EXPECTED_PLAN=ece8caa0552fc0bc03ef2cd51f7560e7a8c6f54e96c29755a75d37168609b744 \
  RUN_COUNT=36 CAMPAIGN=otel-repeat-episodes-c-v1 LOG_PREFIX=otel-repeat-c \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh c1 8018a194892a901222b2b4e0655eef131bc776ae \
  > scratchpad/gate-drivers/otel-repeat-c1.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow otel-repeat-c1 scratchpad/gate-drivers/otel-repeat-c-c1-launch.log \
  > scratchpad/gate-drivers/otel-repeat-c1-wandb.out 2>&1 &
```
Re-run the DRY_RUN immediately before launching (host state moves): same command with `DRY_RUN=1`, label `cdry2`, no `LAUNCH_APPROVED`.
Expected: B attempt 1, the same shape, ran from launch 15:23Z to terminal 18:38Z on 2026-10-09 (3 h 15 min, `otel-repeat-repeat1-launch.log`); GATE-RUN
window 5 h, watcher cap 6 h (run window + 1). Check the first pause cell's `docker-events.json` (`verdict.status`) and the first no-fault cell's `trace-completeness.json` (`rule:
protocol-decision-56`) as soon as each seals (validity fields only). After terminal: fetch to a **new** path (for example `tmp/otel-c-evidence/c1-fetch`),
byte-verify the host and local sha256 lists, read cell validity only (`BUDGET_C.md` stop rule 4).

## Open (for the user or the review)
- **The placement must be frozen by digest before launch** (decision 82, `BUDGET_PLACEMENT.md`); this draft does not check that.
- Seed 20261011 is an engineering default chosen here (recorded above); any other new seed would do, the epoch id already changes every draw.
- The `docker events` tolerance (0.25 s) and the ledgered B review notes (terminal re-derives H10 from receipt stamps only; argv and H10 window line pinned by
  self-consistency) carry over unchanged.
- C and B share the harness code paths but not the commit; C's first live cell is the first evidence on `8018a19`.
- An independent review (Fable `adversarial-review` or the judge panel) of this build has **not** been run; the judge MCP server failed to connect in this
  session. The checks above are my own tests and read-only host checks.
- The TeaStore half of campaign C (fb14srv5) is not covered here.
