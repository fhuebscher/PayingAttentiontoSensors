# OTel load pilot (50 and 100 req/s): declaration (frozen 2026-10-12)

**Status: frozen** by committing this file alone, before launch. It is the draft written by the harness-building agent
plus the GO review's fixes (section "Review fixes", below), which bind where they differ from the draft's text. The
descriptor's `declaration` entry names this path. Scope of every number here: **instance** (one SUT, one host, fb14srv6).
**DRY_RUN `pdry1` passed** 2026-10-12 03:33Z at HEAD `7b20ec48cf66…` ("DRY RUN: all guards passed; stopping before the
first mutation"; srv6: running units 0, containers 0, lease holders none, free 242 GB, pilot paths 0;
`scratchpad/gate-drivers/otel-load-pilot-pdry1-launch.log`).

Authority: `research/traffic-sweep/BUDGET_D.md` **amendment 1** (`86d9172`, user 2026-10-12, committed alone before
the pilot work). The user chose higher traffic with no new fault code, and a load pilot before campaign D. Diagnosis:
`research/placement/test-c/DIAGNOSIS_OTEL_THROTTLE.md` (`aa461f8`). The 0.1-core productcatalogservice throttle never
took effect at 0.05-10 req/s. At about 1.07 ms of CPU per request it should start to bind near 93 req/s.

**User decisions, 2026-10-12** (relayed by the coordinator, after the first build at 100/200 req/s):
1. **Pilot rates are 50 and 100 req/s**, not 100 and 200. Reason: in C the frontend used about 10 ms of CPU per
   request, which puts 200 req/s near two cores of a one-process frontend.
2. **SUT memory limits stay as in C**: productcatalogservice 20 MiB, frontend 250 MiB (upstream).

Deadlines (amendment 1): harness ready and DRY_RUN passed by **2026-10-12 18:00Z**; terminal and fetched by
**2026-10-12 22:00Z**; at most 1 relaunch. If no rate shows the declared effect, D is not launched and the paper reports
C's FAIL together with the diagnosis.

## Manifestation criterion (declared before launch)
Amendment 1's wording, verbatim:
> The throttle manifests at a rate if, in both throttle cells, the median productcatalogservice GetProduct server-span
> duration over the hold is >= 2x its median over the pre-onset segment, and the frontend->productcatalog gRPC client
> span median rises too; the no-fault cell at that rate shows neither (same statistic at the same window position).

**Engineering defaults that close its open wording** (coordinator, 2026-10-12). The descriptor binds them by digest as
`analysis.manifestationCriterionDefaults`:
- **Span selection:** by span start time; all spans, regardless of status.
- **Onset:** in a fault cell, the onset command issued (`intervention.json`). In the no-fault cell, its pseudo onset:
  the seeded window position, `timing.scoredWindowSeconds[0]`.
- **Pre-onset segment:** [onset - 60 s, onset). **Hold:** [onset, onset + hold) with hold = 60 s.
- **Server-span ratio:** median productcatalogservice GetProduct server-span duration, hold / pre-onset >= **2.0**.
- **"Rises" for the client span:** median frontend->productcatalog gRPC client-span duration, hold / pre-onset
  >= **1.25**.
- **No-fault cell:** the same statistics at its pseudo onset must show neither the >= 2x server-span ratio nor the
  >= 1.25x client-span ratio.
- **Verdict per rate:** *manifests*, *does not manifest*, or `—` (fewer than 2 valid throttle cells, or an invalid
  no-fault cell, at that rate).

## What differs from campaign C
| item | campaign C (attempt 1) | load pilot |
|---|---|---|
| study epoch | `otel-repeat-episodes-c-v1` | **`otel-load-pilot-v1`** (new; C and every earlier epoch unchanged) |
| compiler | `candidate_repeat_c.py` | **`candidate_load_pilot.py`**: reads C's compiler and C's pinned descriptor, edits neither |
| rates | 10, 1, 0.2, 0.05 /s | **50, 100 /s** (offered 9,000 / 18,000 per 180 s measurement) |
| regimes | no fault, frontend pause, productcatalog throttle | **no fault, productcatalog throttle** (same scenario: `docker update --cpus 0.1`, onset 60 s + seeded offset, hold 60 s) |
| cells | 36 = 3 blocks x 12 | **6** = per rate 2 throttle episodes (runKey `block` 1, 2) + 1 no-fault cell (`block` 1) |
| run order | seeded Fisher-Yates per block | **rate-ascending segments** (all 50 /s cells, then all 100 /s cells), seeded Fisher-Yates inside each segment |
| onset strata | 3 | 2 (the two throttle episodes take the two halves of one inter-arrival) |
| seed | 20261011 | **20261012** (engineering default: the build date) |
| concurrency | 300 | **3000** = ceil(2 x 100 x 15), the sweep's own rule at the pilot's top rate |
| generator open files | not set | **soft RLIMIT_NOFILE >= 4024** (= concurrency + 1024), raised before `compose up`, or the cell is refused |
| frontendproxy memory | 256 MiB | **512 MiB** (the sweep's rule: 0.3 MB x rate x timeout = 0.3 MB x 1500 = 450 MB, rounded up) |
| productcatalogservice / frontend memory | 20 MiB / 250 MiB | **unchanged** (user decision 2) |
| frontendproxy log rotation | upstream 5m x 2 | **4g x 1** (the collector carrier's rule), rendered by `materialize.py` for this epoch only |
| collector | log sampler off (decision 66) | same |
| H10 / H4 | as B | same (H4 recorded, never blocking, decision 69) |
| trace rule | decision 25 in fault cells, 56 in no-fault cells | same |
| cell overhead / min. remaining / GATE-RUN window | 120 s / 13,416 s / 5 h | **450 s / 5,466 s / 3 h** (watcher cap 4 h) |
| descriptor | `6dd3cb72...3721` | **`45b79b0cf552b12a111ed047803ee535aabdb6d0400d05ce108e5a119a65ac46`** |
| plan, attempt 1 | `ece8caa0...b744` | **`aea94eb91d90d18fd41165da3af88771ea1964434c922375196478ef269d25d6`** |
| run count | 36 | **6** |
| materialized source (local projection) | `18fe429c...d860` | **`031fcc1e83e1ebff9672b7036793b23e040517cad1bf4850271d3f839f5c79b0`**: differs from C's only through the frontendproxy logging block, so the install rebuilds the locally built images |
| host paths | `...-runs/otel-repeat-episodes-c-v1` etc. | `...-runs/otel-load-pilot-v1`, `.setup-otel-load-pilot-v1`, `...-otel-srv6/otel-load-pilot-v1-7b20ec48cf66`; Compose project `otel_candidate_v4_otel_load_pilot_v1` |

Every other timing key of a cell equals C's for the same (regime, rate). That covers the route, timeout 15 s, warm-up
30 s at 10 /s, measurement 180 s, hold 60 s, the H10/H4 flags, the trace rule per kind, the container-health guard and
the protocol gates (F1, G1, G2, G4 blocking). Tested key by key. The descriptor equals C's except for the declared keys
(`candidate_load_pilot.REPLACED_DESCRIPTOR_KEYS` and `_SUBKEYS`, tested). Both digests are identical under
`/usr/bin/python3 -I` (3.9) and `uv run python -I` (3.13).

### Why these sizes (engineering defaults, recorded in the descriptor)
- **Concurrency 3000.** At 100 /s a binding throttle can keep rate x timeout = 1500 requests in flight. The thread pool
  starts a request on time only while in-flight requests stay below the cap, so the sweep's 2x margin gives 3000.
- **Open files 4024.** Every in-flight request holds a socket in the controller. A systemd unit's default soft limit is
  1024, and an EMFILE would be recorded as a failed request of the target.
- **frontendproxy 512 MiB.** C's 256 MiB rule applied at rate x timeout = 1500 waiting requests.
- **frontendproxy log 4g x 1, kept.** Upstream's json-file rotation loses lines once a container has written 10 MB. A
  100 /s cell writes about 18,300 lines. At an estimated 0.4 kB per line on disk (C's lines are 260-330 bytes before
  json-file framing) that is about 7.3 MB, a margin of only about 27 %. At 0.55 kB per line it would exceed 10 MB. The
  terminal requires every offered token to be witnessed exactly once.
- **450 s overhead per cell.** C's tail after the window was 122-134 s and rose about 4 s from r0.05 to r10 (about
  2.2 ms per offered request). That projects to about 162 s at r100 if linear; 450 s (about 2.8x) covers a superlinear
  tshark and collector-log pass.

### Host limits (checked read-only on fb14srv6 by the coordinator, 2026-10-12)
| quantity | value on srv6 | pilot need at 100 /s |
|---|---|---|
| CPUs (`nproc`) | 24 | — (the frontend is one Node process; see risk 1) |
| `kernel.threads-max` | 2,062,359 | 3000 generator threads + controller threads |
| systemd `DefaultTasksMax` | 309,353 | same |
| `ulimit -u` | 1,031,179 | same |
| `ulimit -n` (login shell) | 1,048,576 | — |
| systemd `DefaultLimitNOFILE` | 524,288 (user manager: 1,048,576) | soft >= 4024: the hard limit allows the raise the cell makes |
| `nf_conntrack_max` | 262,144 | ~24k entries (100 conn/s x 2 hops x 120 s TIME_WAIT) |
| `ip_local_port_range` | 32768-60999 (28,232 ports) | ~6k sockets in TIME_WAIT (100 conn/s x 60 s) |

The thread, conntrack and port needs are estimates (the hop count and TIME_WAIT durations are kernel defaults, not
measured on srv6). Whether the transient unit's *soft* NOFILE is 1024 is not settled. The cell raises it either way, and
refuses itself if the hard limit is below 4024.

### Expected volumes per cell (linear extrapolation from C's r1 and r10 cells; not measured at these rates)
| artifact | C r10 | r50 (est.) | r100 (est.) |
|---|---|---|---|
| otelcol.log | 31 MB | ~90 MB | ~160 MB |
| telemetry.pcap | 16 MB | ~70 MB | ~135 MB |
| request-ledger.json | 1.0 MB | ~5 MB | ~10 MB |
| all artifacts | ~52 MB | ~180 MB | ~330 MB |
The pilot total is about 1.5 GB on fb14srv6, against the launcher's 40 GB free-space guard, and the same fetched to the
laptop.

### Expected duration
6 cells x (211 s timed + ~135-165 s tail) is about 35-40 min of cells. Add setup with an image rebuild (the materialized
source is new), about 15-30 min. **Expected about 1 h from launch to terminal (up to about 1.25 h)**, within the 3 h
GATE-RUN window and the 4 h watcher cap. To meet 22:00Z terminal-and-fetched, launch by about 20:00Z.

## Commits in the OTel worktree (branch `otel-protocol-20261002`, on top of `8018a19`, tracked tree clean at HEAD)
| commit | what | governed file moved? |
|---|---|---|
| `243628bfcda172685b52cc04586018d368e940fa` | C attempt 1 recorded spent (2026-10-11, harness 8018a19, plan ece8caa0, 36/36 valid, 619/619); +2 tests, 2 updated | `candidate_runtime_adapter.py` |
| `af40d63ab19420f545e9a49e5a666152064bda70` | load-pilot epoch (first at 100/200), not activated: compiler, descriptor, pilot in `REPEAT_STUDY_EPOCHS`, `ensure_generator_open_files`, controller sets and timing keys, `SPENT[pilot] = {}`, collector sampler and frontendproxy retention in `materialize.py`, ledger +1, `tests/test_otel_load_pilot.py` | `candidate_runtime.py`, `candidate_runtime_adapter.py` |
| `f0814e0e5e2a11ccac9ad91b05e81e53fb0bf167` | governance re-pin of both | re-pin |
| `394ec4735731099211f6aec02c319dfd9916642a` | activation: selector names the pilot; tombstone `("otel-load-pilot-v1",)` in `candidate_setup.py` and `candidate_remote.py` | no |
| `c113946` | **rates 50 and 100** (user decision), sizing re-derived (3000 / 4024 / 512 MiB / 450 s / 5,466 s / 3 h), criterion defaults bound in the descriptor | no (no re-pin needed; every sourceBinding checked) |
| `7b20ec48cf66ae2eae5d36fc5437aae251ad8d85` | activation confirmed on the re-derived plan (selector and tombstone unchanged; ledger names the rates) | no |

**Launcher values:** `EXPECTED_PLAN=aea94eb91d90d18fd41165da3af88771ea1964434c922375196478ef269d25d6`, `RUN_COUNT=6`,
`COMPILER=candidate_load_pilot.py`, `CAMPAIGN=otel-load-pilot-v1`. The launcher's local plan check and drivers check
were reproduced locally (no host contact) and print `otel-load-pilot-v1 6 aea94eb9...25d6` and
`otel-load-pilot-v1 otel-load-pilot-v1 3`.

## The 6 cells (attempt 1; run order; onset = seconds after the barrier at which the fault command is issued)
| pos | rate /s | regime | episode | onset s | run id | artifact root |
|---|---|---|---|---|---|---|
| 1 | 50 | productcatalog-throttle | 1 | 60.018811 | 008d8350117501e8e35b8210 | runs/effect/productcatalog-cpu-throttle/r50-b01-01-full |
| 2 | 50 | no-fault (pseudo onset) | 1 | 60.006104 | 439ae180b4d7272e0e80e062 | runs/calibration/r50-b01-02-full |
| 3 | 50 | productcatalog-throttle | 2 | 60.004382 | 0d773d51279c48103b7aaed9 | runs/effect/productcatalog-cpu-throttle/r50-b02-03-full |
| 4 | 100 | productcatalog-throttle | 1 | 60.005588 | 59d84e9497cc604c35b14f9d | runs/effect/productcatalog-cpu-throttle/r100-b01-04-full |
| 5 | 100 | no-fault (pseudo onset) | 1 | 60.002331 | 3d3478a6c2ec896bf7bf0cb3 | runs/calibration/r100-b01-05-full |
| 6 | 100 | productcatalog-throttle | 2 | 60.000341 | c21a646ed08dd6537199a487 | runs/effect/productcatalog-cpu-throttle/r100-b02-06-full |

No run ID equals one from sweep attempts 1-2, quiet attempts 1-3, B attempt 1 or C attempt 1 (tested). The 100 /s run
IDs are the ones the 100/200 plan had (same run keys); that plan never ran. The campaign stops on its first invalid cell.

## Risks the build cannot settle without running the pilot
1. **The frontend may saturate at 100 /s without any fault.** In C's r10 cells the frontend used 19.2-19.7 CPU-s per
   180 s window against 1.2-1.4 s at r0.05: about **10.2 ms CPU per request** (13 ms at r1). It is one Node process
   (`node server.js`), so its JavaScript runs on one core. That is about 0.5 core at 50 /s and about 1 core at 100 /s.
   At 100 /s, G2 (pre-onset failure share > 5 %) or pre-onset trace loss in a fault cell (decision 25) may invalidate a
   cell, which stops the campaign. The rate-ascending order runs all 50 /s cells first. Scope: instance; per-request
   cost above 10 /s is not measured.
2. **SUT memory limits unchanged (user decision 2):** productcatalogservice 20 MiB, frontend 250 MiB. The frontend's
   gRPC client sets no deadline. At 100 /s a binding throttle (demand about 107 ms per 100 ms quota period) accumulates
   only about 7 req/s of backlog, about 420 pending calls by the end of the hold. That is a smaller pile-up than at
   200 /s, but any OOM kill still invalidates the cell.
3. **Decision 25 still blocks fault cells** outside the fault-and-drain window. SDK span queues (JS and Go
   BatchSpanProcessor, 2048 spans) at 5-10x C's span rate may drop spans. The draft keeps C's rule.
4. **Witness check.** Every offered token must appear exactly once in frontendproxy's access log. A connection refused
   before Envoy (listen backlog, docker-proxy) would leave a token unwitnessed and fail the terminal.

## Launch (worktree HEAD must still be `7b20ec48...`)
From the measurement repo (re-run `git -C ../observability-placement-runtime-otel-protocol rev-parse HEAD` first):
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
DRY_RUN=1 OTEL_CANDIDATE_ATTEMPT=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_load_pilot.py EXPECTED_PLAN=aea94eb91d90d18fd41165da3af88771ea1964434c922375196478ef269d25d6 \
  RUN_COUNT=6 CAMPAIGN=otel-load-pilot-v1 LOG_PREFIX=otel-load-pilot \
  zsh scratchpad/gate-drivers/launch_otel_offpath.sh pdry1 7b20ec48cf66ae2eae5d36fc5437aae251ad8d85 \
  > scratchpad/gate-drivers/otel-load-pilot-pdry1.out 2>&1
```
Launch (after a passing DRY_RUN; same variables, no `DRY_RUN`):
```
LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_load_pilot.py EXPECTED_PLAN=aea94eb91d90d18fd41165da3af88771ea1964434c922375196478ef269d25d6 \
  RUN_COUNT=6 CAMPAIGN=otel-load-pilot-v1 LOG_PREFIX=otel-load-pilot \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh p1 7b20ec48cf66ae2eae5d36fc5437aae251ad8d85 \
  > scratchpad/gate-drivers/otel-load-pilot-p1.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow otel-load-pilot-p1 scratchpad/gate-drivers/otel-load-pilot-p1-launch.log \
  > scratchpad/gate-drivers/otel-load-pilot-p1-wandb.out 2>&1 &
```
After the first cell seals, check the validity fields only: `receipt.json` state, `protocol-gates.json` failedGates,
`container-health.json` reasons, `trace-completeness.json` valid. After terminal, fetch to a **new** path (for example
`tmp/otel-load-pilot-evidence/p1-fetch`) and byte-verify the host and local sha256 lists. Then apply the criterion
once, with the defaults above.

## Tests (OTel worktree)
- `tests/test_otel_load_pilot.py` at `7b20ec4`: 36 passed. Source plants, each restored, all caught:
  - pilot dropped from `REPEAT_STUDY_EPOCHS`: 6 failed;
  - open-file call removed from the cell runner: 4 failed;
  - pilot dropped from the sampling tuple: 1 failed;
  - pilot dropped from the retention tuple: 2 failed;
  - open-file key dropped from the runtime key set: 8 failed;
  - old rates (100, 200) restored in the compiler: 14 failed + 7 errors;
  - epoch id set to C's: collection error (the active selector's compiler no longer names its epoch).
- In-test plants: C-sized generator (300), descending rate order, edited descriptor or plan, C-epoch run-ID reuse, a
  hard limit of 2048 (cell sealed invalid before `compose up`).
- The fake-target end-to-end cells (throttle r50, no-fault r50, throttle r100) cap the thread pool at 256 on macOS. The
  3000 the controller asks for is asserted, not exercised. **The per-cell runner has run only against the fake target.**
- Measurement repo `tests/test_unbound_names.py`: 318 passed (one parametrisation is `candidate_load_pilot.py`, +1
  against the 317 in CLAUDE.md).
- Full worktree suite at `7b20ec4`: Full worktree suite (`uv run pytest -q -p no:cacheprovider -rf --ignore=tests/test_mlflow_manifest.py`) at `7b20ec4`, clean: **29 failed, 2232 passed, 145 skipped** (606 s). At `8018a19` (C's record): 29 failed, 2194 passed, 145 skipped. The sorted `FAILED` name lists are identical to C's and to `394ec47`'s (`diff`, no output; none is OTel). The delta of +38 passed is fully attributed: +36 from `tests/test_otel_load_pilot.py` and +2 new C tests (C attempt 1 spent). Logs: `tmp/otel-load-pilot-prep/` (gitignored).

## Open at freeze
- Risk 1: 100 /s may exceed the frontend's single-process capacity. The pilot will show it.
- Risks 2-3 (SUT memory limits as in C, decision 25 in fault cells) are preregistration-class. The memory limits are
  the user's decision 2; decision 25 is unchanged.
- Reviewed: Fable adversarial-review (same-provider), GO with fixes; the judge MCP server fails to connect.

## Review fixes (GO with fixes; Fable adversarial-review, same-provider, 2026-10-12; bind over the text above)
- **S1, valid cell.** For the per-rate verdict a cell is valid iff its host receipt says valid **and** an offline
  `validate_cell` replay of that cell passes (the witness check runs only in the terminal). This applies per cell, so the
  50 /s verdict stands even if the campaign stops in the 100 /s segment and never becomes terminal-valid.
- **S2, span predicates.** Server: `service.name=productcatalogservice`, `Name=oteldemo.ProductCatalogService/GetProduct`,
  `Kind=Server`. Client: `service.name=frontend`, `Name=grpc.oteldemo.ProductCatalogService/GetProduct`, `Kind=Client`.
  Spans from `otelcol.log` (Start/End time, ns). Onset: `intervention.json` `freeze.commandIssuedOffsetSeconds`
  (= `actualOnsetMonotonicOffsetSeconds`, pre-command), mapped to wall clock with `request-ledger.json` `barrierEpoch`;
  the no-fault pseudo onset is `timing.scoredWindowSeconds[0]`. A segment with fewer than 20 spans gives `—` for that
  ratio (engineering default).
- **S3, relaunch.** At most one, and only for a harness or infrastructure defect; frontend saturation or an OOM kill at
  100 /s is a result, not a defect, and is not relaunched. A relaunch needs: the adapter `SPENT` row for attempt 1
  (`candidate_runtime_adapter.py:334`) with a governance re-pin, the attempt-2 plan
  `04c894d52aed6a4a774821c54bbfa93013c6b0f5b3cc0d349a8f2789fb3ac4b6`, the host run dir
  `…/observability-placement-candidate-v4-runs/otel-load-pilot-v1` archived (the launcher refuses while it exists), a
  relaunch declaration committed alone, and a fresh DRY_RUN.
- **S4, fetch.** `scratchpad/gate-drivers/fetch_overnight.sh otelpilot1` (host-side sha256 manifest, tar stream over
  ssh, local extract, `shasum -c`) to the new path `tmp/otel-load-pilot-evidence/p1-fetch`. If the stream dies, the same
  command re-runs into another new path (`p1-fetch2`); nothing is overwritten.
- **S5.** Host-limit readings: coordinator's read-only ssh to fb14srv6, 2026-10-12 ~03:05Z, output preserved here:
  `nproc 24; threads-max 2062359; nf_conntrack_max 262144; ip_local_port_range 32768 60999; ulimit -n 1048576;
  ulimit -u 1031179; DefaultLimitNOFILE=524288 (user 1048576); DefaultTasksMax=309353`.
- **N1.** Comments naming "100/200 req/s" remain at `candidate_remote.py:264,1440` and `materialize.py:24-25,33`; line 33
  is rendered into the compose overlay (materialized source `031fcc1e`). Harmless; not edited, so the source digest holds.
- **N2.** `ensure_generator_open_files` returns the before/after limits but nothing stores them; an EMFILE still shows as
  a ledger error. A hard limit below 4024 would seal cell 1 invalid (attempt spent, no data); not verified on the host.
- The criterion is applied by a small script written after the fetch, which implements exactly the rules above and is
  committed before it is run on the cells.
