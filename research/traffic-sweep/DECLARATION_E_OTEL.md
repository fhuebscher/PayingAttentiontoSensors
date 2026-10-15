# OTel campaign E (off-path faults, 5 blocks, blocks 1-3 training and 4-5 test): declaration (2026-10-13)

**Status: declaration, committed alone before launch** (BUDGET_E stop rule 3), after an independent review (see "Review"). Drafted by the
harness-building agent (Sonnet 5.5, 2026-10-12); parameters set and placeholders filled by the coordinator (2026-10-13) after the off-path pilot v2
verdict (criteria output `537a406`, `research/placement/pilot-offpath/RESULT_V2.md` `4ddd451`) and the user's decision 109 (BUDGET_E amendment 2, `34dc151`). Scope of every
number: **instance** (one SUT, OTel Demo 1.12.0 at 2d4661e, one host, fb14srv6). Numbers marked *generator* come from the compiler's derivation, not
from the host; unknown values are `?`. The analysis chain (v3.2) is NOT yet frozen: stop rule 4 holds (no E cell is read, validity fields only,
before v3.2, the training placement and the pass rule are frozen by digest; deadline 2026-10-14 06:00Z).

## What E is
Campaign E (BUDGET_E.md, protocol decisions 95-102 and 108) is the off-path pilot v2's cell (`candidate_offpath_pilot_v2.py`, plan `a929b4d9...`;
the upstream Locust task mix as an open loop with one ledger row per request, a 60 s pause of frauddetectionservice, accountingservice or
the frontend, and a no-fault cell) run in **5 blocks at one rate with a kept set of faults**: epoch `otel-offpath-e-v1`, compiler
`modules/otel-demo/execution/candidate_offpath_e.py` and descriptor `pipelines/campaigns/otel-offpath-e-v1.json` in the harness worktree
(`observability-placement-runtime-otel-protocol`, branch `otel-protocol-20261002`; epoch commit `d1358bb`, governance re-pin `0d6578a`; pilot v2
attempt 1 recorded spent `c547ebb`; parameters `0788151`; **activated** `94641f5`, governance re-pin `6a5c2a9` = the launch commit). The mix, the pause scenarios, the criteria fields,
H10/H4, the collector log sampler off, the trace rules (decisions 25/56 per route), posture `full` and the sizing rules are the pilot v2's, tested
for identity (`tests/test_otel_offpath_e.py`). The pause hold is 60 s (decision 104); the throttle is not in E (decision 108).

## The two parameters: **RATE = 25.0, KEPT_FAULTS = ("fraud-pause", "accounting-pause", "frontend-pause")** (variant row 1)

Set from pilot v2 (`537a406`): every pause manifests at 25 and at 50 req/s, so every fault is kept and the rate rule gives 25 req/s (the lowest rate at
which every kept fault manifests; not vetoed, decision 109). Commit `0788151`; `--print-digests` at `6a5c2a9`: descriptor `a17ac3d6…4398`, plan (attempt 1)
`503bf014…7661`, 20 cells, minimum remaining 11,720 s, window 5 h, equal to row 1 of the table below. How the parameters were allowed to move:
| parameter | module constant | allowed | set from |
|---|---|---|---|
| rate | `RATE` | `25.0` or `50.0` req/s of the whole mix | pilot v2 and E's rate rule (lowest rate at which every kept fault manifests, else the highest at which any does; the user may veto) |
| kept faults | `KEPT_FAULTS` | one of 6 tuples, canonical order: `("fraud-pause","accounting-pause","frontend-pause")`, `("fraud-pause","frontend-pause")`, `("accounting-pause","frontend-pause")`, `("fraud-pause","accounting-pause")`, `("fraud-pause",)`, `("accounting-pause",)` | pilot v2's criteria: a fault is kept iff it manifests at >= 1 rate; at least one off-path pause (BUDGET_E stop rule 5) |

Anything else is refused at import. The 12 pairs are the table below; the descriptor digest of each is pinned in
`EXPECTED_DESCRIPTOR_SHA256_BY_VARIANT`, so **setting the parameters needs no pin edit**. Procedure (executed in the tests on tree copies for 3 variants,
including the gate chain): edit the two lines `RATE = ...` and `KEPT_FAULTS = ...` of `candidate_offpath_e.py`; `rm pipelines/campaigns/otel-offpath-e-v1.json`;
`/usr/bin/python3 -I modules/otel-demo/execution/candidate_offpath_e.py --emit-descriptor pipelines/campaigns/otel-offpath-e-v1.json`; run
`--print-digests` and compare with the table (descriptor and plan, attempt 1); commit; then the activation commit (below). Row 1 is the chosen variant.

## Design
- **Blocks and split (decision 100):** 5 blocks; blocks 1, 2, 3 are *training* (the placement is solved on them and frozen), blocks 4, 5 are *test* (scored
  once). The split is in the descriptor (`design.split`, `schedule.split`, `analysis.split`) and in the compiled plan (`split`, and `split` per block), and a plan
  with another split is refused by the rule, not only by the pin (tested, planted). The analysis registry's `V32_E_SPLIT` has the same 1-3 / 4-5.
- **Per block:** one no-fault cell and one cell per kept fault. Order inside a block: the no-fault cell first, the kept off-path pauses in a seeded
  Fisher-Yates order (one draw per block, SHA-256 draws keyed by seed, epoch, block and context `offpath-e-schedule-v1-group1`; with one kept off-path
  pause there is no draw), the frontend pause last (when kept). Blocks run in order 1..5.
- **Onsets:** campaign C's strata rule over the 5 blocks: for each (regime, rate) the 5 blocks take the 5 strata of one inter-arrival (1/rate) in a seeded order,
  uniform inside the stratum (`quiet.stratified_onset_offset` with 5 episodes); the no-fault cell's pseudo onset (`timing.scoredWindowSeconds[0]`) is drawn the same
  way. Tested: the 5 onsets of a (regime, rate) are a permutation of the 5 strata; v2's one-stratum rule and C's 3 strata are refused.
- **Seed 20261012** (the build date; an engineering default recorded in the descriptor). No reason to change it: the epoch id alone gives every draw a new value.
- **Run IDs** are `sha256` of the run key (epoch, regime, rate, block, posture, attempt), so they cannot equal any earlier epoch's; tested against the sweep, quiet, B, C,
  the load pilot, v1 attempt 1 and v2 attempts 1-3, for all 12 variants and attempts 1-2 (and E's attempts 1-3 for the default; planted reuse found).
- **Sizing (the pilot v2's rules at RATE):** concurrency ceil(2 x RATE x 15) (750 at 25, 1500 at 50), open files concurrency + 1024 (1774, 2524), frontendproxy memory by the sweep's
  0.3 MB per waiting request at RATE x 15 waiting requests (112.5 MB at 25, 225 MB at 50) rounded up to a power of two **with a floor at C's own 256 MiB**: the literal rule gives
  128 MiB at 25 req/s, below the 256 MiB the sweep ran at 10 req/s (90 MB at its 300-request cap) and below what the pilot v2's 25 req/s frontend pause runs at; so every variant has 256 MiB
  (*engineering default, recorded in the descriptor `sutDeviations`; the user may veto*). otelcol and jaeger 1 GiB (decision 103). **Every SUT service limit stays upstream's.**
  Overhead 300 s per cell (v2's), 211 timed seconds, 900 s cell-deadline reserve, 600 s cleanup reserve, 3,600 s approval-to-first-mutation slack (the frozen epoch's).
- **Posture** `full` only; collector log sampler off; frontendproxy log retention 4g x 1 (the pilots' rendering, so the materialized source is the pilots' and the host's images
  are probably reusable: `?`).

### The 12 prepared variants (*generator*; identical under `/usr/bin/python3 -I` (3.9) and `uv run python` (3.13); tested)
| # | rate (req/s) | KEPT_FAULTS | RUN_COUNT | cells | min remaining s | GATE-RUN window | watcher cap | concurrency | open files | frontendproxy | descriptor digest | plan digest (attempt 1) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 25 | fraud, accounting, frontend | 20 | 5 x 4 | 11720 (3.26 h) | 5 h | 6 h | 750 | 1774 | 256 MiB | `a17ac3d676a85dd9b488bd100a925679322ff93ec6c4257e8f102acd700e4398` | `503bf014cfb51cc85c96010b2dc4632fe24bba644c804c21fbd405b7bb517661` |
| 2 | 25 | fraud, frontend | 15 | 5 x 3 | 9165 (2.55 h) | 4 h | 5 h | 750 | 1774 | 256 MiB | `79671d364d5e52b97f44a3853a57c6fae1d44684cbaf3c501d9d7c3875d63d21` | `1c955f296cefd8d15b59a02d2f6d796b6e166836856085a5c64fb8a2aa0c47ce` |
| 3 | 25 | accounting, frontend | 15 | 5 x 3 | 9165 (2.55 h) | 4 h | 5 h | 750 | 1774 | 256 MiB | `a95d810721c07feed889bd1f243058c619afab665dd9983ea49f003c9fafd6df` | `5ce44991a28e6a13f677b3b2c7df941cbcb42a31c24b548797ad3a13d50cf642` |
| 4 | 25 | fraud, accounting | 15 | 5 x 3 | 9165 (2.55 h) | 4 h | 5 h | 750 | 1774 | 256 MiB | `9380b7394683d7cc94158914c8f147181060aab7a74146e078fa71e10fc5fbe7` | `b90cacdb423de0ee266e1b9fb10ab95b037768b8c0b95d6d4bb4a41891c9f138` |
| 5 | 25 | fraud | 10 | 5 x 2 | 6610 (1.84 h) | 3 h | 4 h | 750 | 1774 | 256 MiB | `cf3725de6f5733e935125015bd5c0d140cc305d322aa132625df1d73dec6a7c7` | `e05333d615aa48ed66bcff231f8d1e54cab9bcd5c7bdaa28ccb7cf3eeae888da` |
| 6 | 25 | accounting | 10 | 5 x 2 | 6610 (1.84 h) | 3 h | 4 h | 750 | 1774 | 256 MiB | `54cf4757a9167d662f4da3dd5bc4d23e9f9d41441fa97a36d569a92f107bd5e9` | `73653dc9e21e644e61b65c2e28c5e726cd35b3a13606c9d19ed1497de169ca8c` |
| 7 | 50 | fraud, accounting, frontend | 20 | 5 x 4 | 11720 (3.26 h) | 5 h | 6 h | 1500 | 2524 | 256 MiB | `7ab00ab2d677653aad7dc509ca09dbf4b7521a11e2a58da119cfc3b83d844e0d` | `edcb2f0e300adca19cfba5f52130d6cae9531a19f1a97d45329dbabd91ea8946` |
| 8 | 50 | fraud, frontend | 15 | 5 x 3 | 9165 (2.55 h) | 4 h | 5 h | 1500 | 2524 | 256 MiB | `96ba7532fd1fb99c9cb5f81d7b5bd191b4486884ea505c78af588f490594e798` | `9dda74a66cae709f0f48cb612ee706c96aa4a06d8b01f0af55d53cf6c912bb69` |
| 9 | 50 | accounting, frontend | 15 | 5 x 3 | 9165 (2.55 h) | 4 h | 5 h | 1500 | 2524 | 256 MiB | `c6a49b6a22a142db453a1a706da7abdda7c2965888c72bd5cb32a5ae97a064b2` | `6774eff729b90e7368ea561b11e47a5d7fb9cd71b23669a219aa952ea5d77f2f` |
| 10 | 50 | fraud, accounting | 15 | 5 x 3 | 9165 (2.55 h) | 4 h | 5 h | 1500 | 2524 | 256 MiB | `d13c44401f5cae426f820346c3802e56d05ad5bcf30c3ec45c665ca77d51a691` | `ebc097bc1721eecca0d4e93db56bd0e10b53cd689542f35ccf1cac1feb1b4181` |
| 11 | 50 | fraud | 10 | 5 x 2 | 6610 (1.84 h) | 3 h | 4 h | 1500 | 2524 | 256 MiB | `863e910a87e6a6287814d35f1811a898bf137a94cf19b3410b5bc186f0725653` | `850d0f1bf6669e06bfe9cd0db1c750006d33a87f74701ee7219ffe6645e2b15a` |
| 12 | 50 | accounting | 10 | 5 x 2 | 6610 (1.84 h) | 3 h | 4 h | 1500 | 2524 | 256 MiB | `4e08d93532239624b02c4635f68b19843369d834f789af2d5162f8f4445b0f54` | `36ac5f9de2183d781642d0334f66d58decf6028cb86e17cb6d9ac2f72eb52e3d` |
RUN_COUNT = 5 x (1 + number of kept faults). Minimum remaining = RUN_COUNT x (211 + 300) + 900 + 600 s. GATE-RUN window = ceil((minimum remaining + 3,600) / 3,600) h; the
watcher cap is the window + 1 h (the launcher's rule). Plan digests are for attempt 1; they are the launcher's `EXPECTED_PLAN`. **Fit:** the largest variant (20 cells) needs 11,720 s = 3.26 h of cells
and a 5 h GATE-RUN window, inside the 4-5 h a campaign may take; every variant's minimum remaining is below 4 h. Time to terminal from a launch: 20 cells x (211 s + a tail of 142-150 s,
the load pilot's measurement at 50 req/s of one route; the mix's tail is for the pilot v2 to measure, `?`) is about 2.0 h, and 2.8 h at the budgeted 511 s per cell, plus setup: inside the window. The budget wants E terminal by
**2026-10-14 12:00Z** and launch by **2026-10-13 22:00Z**: a 20-cell launch at 22:00Z ends by 03:00Z at the latest even on the full 5 h window, and one relaunch (at most 1, harness or infrastructure
defects only) still fits. The 300 s overhead is the pilot v2's engineering default; if the pilot's measured tails are lower, changing it is an engineering decision with its own descriptor pin (it moves all 12 digests); it is not one of the two parameters.

### The chosen variant's 20 cells (row 1; attempt 1; onset = seconds after the barrier at which the fault command is issued, or the no-fault cell's pseudo onset; *generator*, compiled at `6a5c2a9`)
| pos | block | split | regime | onset s | run id | artifact root |
|---|---|---|---|---|---|---|
| 1 | 1 | training | no-fault | 60.038980 | 228c02a78532d290528c5772 | runs/calibration/r25-b01-01-full |
| 2 | 1 | training | fraud-pause | 60.013437 | 53fffae8935f25f7882d7bf8 | runs/effect/fraud-pause/r25-b01-02-full |
| 3 | 1 | training | accounting-pause | 60.034211 | 32d2e7db8ac2e7c24c84dd07 | runs/effect/accounting-pause/r25-b01-03-full |
| 4 | 1 | training | frontend-pause | 60.027007 | beef5e77e6d80dd87c93d22f | runs/effect/frontend-pause/r25-b01-04-full |
| 5 | 2 | training | no-fault | 60.007572 | a558009b3aea7c1db0e4c5d0 | runs/calibration/r25-b02-05-full |
| 6 | 2 | training | fraud-pause | 60.028378 | 661e38eca11e8cd714b057c0 | runs/effect/fraud-pause/r25-b02-06-full |
| 7 | 2 | training | accounting-pause | 60.002932 | 878d02a5ec7ccb964d928e60 | runs/effect/accounting-pause/r25-b02-07-full |
| 8 | 2 | training | frontend-pause | 60.037601 | 79344f5b56f18926f6eecbe4 | runs/effect/frontend-pause/r25-b02-08-full |
| 9 | 3 | training | no-fault | 60.028099 | 28ef8be55432e69d27326284 | runs/calibration/r25-b03-09-full |
| 10 | 3 | training | accounting-pause | 60.008511 | 8c450bfc644457440bdfedb7 | runs/effect/accounting-pause/r25-b03-10-full |
| 11 | 3 | training | fraud-pause | 60.002060 | c21f4cf72a0ce5bcad89dd96 | runs/effect/fraud-pause/r25-b03-11-full |
| 12 | 3 | training | frontend-pause | 60.004368 | 674e8a554be38b18b7a0ee8d | runs/effect/frontend-pause/r25-b03-12-full |
| 13 | 4 | test | no-fault | 60.020381 | 24e64e73e596ff1f3a38d845 | runs/calibration/r25-b04-13-full |
| 14 | 4 | test | fraud-pause | 60.019505 | 2723fc2e4d519bfcf4f0b754 | runs/effect/fraud-pause/r25-b04-14-full |
| 15 | 4 | test | accounting-pause | 60.021305 | a44cd6b8d7fcebb05787f7c9 | runs/effect/accounting-pause/r25-b04-15-full |
| 16 | 4 | test | frontend-pause | 60.012583 | e8015e480473539bf037ab0c | runs/effect/frontend-pause/r25-b04-16-full |
| 17 | 5 | test | no-fault | 60.010172 | 33d75886c508b74b2da298d2 | runs/calibration/r25-b05-17-full |
| 18 | 5 | test | fraud-pause | 60.032006 | 1a037fc5e340665579f1a066 | runs/effect/fraud-pause/r25-b05-18-full |
| 19 | 5 | test | accounting-pause | 60.027953 | 1f00ed7f4f28b30cd28aae8f | runs/effect/accounting-pause/r25-b05-19-full |
| 20 | 5 | test | frontend-pause | 60.016600 | 6c3b8d871f75d34b855eb88f | runs/effect/frontend-pause/r25-b05-20-full |

## The pass rule (decisions 99-102, with 110-111 of 2026-10-13)
- **Decision 99 (E pass rule, off-path sign rule):** for each off-path class (frauddetectionservice pause, accountingservice pause) **separately**, at E's rate, the **frozen set** passes if
  g = D(ledger alone) - D(S) > 0 over that class's test episodes **and** it improves at least 2 of them; on-path classes and other cells are reported without a verdict; `—` if a set member is
  absent from the scoring ground set or fewer than 2 valid test episodes exist (decisions 90-91 carried over). In the analysis registry (`research/protocol/parameters_v3_2.json`,
  `V32_PASS_RULE`) the frozen set is the **unrestricted frontier cell's** set at the zero-alarm knot, `frontier (effort<=any, runtime<=any) @3/T_r` (decision 110), per class `fraud-pause-effect` and
  `accounting-pause-effect`, `minGain` null (strictly positive), `minImprovedEpisodes` 2, `minEpisodes` 2.
- **Decision 110 (user, 2026-10-13, on this declaration's review): the set is read at 3/T_r, not 6/h.** A sensor costs its 95 % Poisson upper false-alarm rate over the rate's
  no-fault hours (decision 73). E's training blocks hold 3 no-fault cells (~0.15-0.18 h; the test blocks' 2 are held out by decision 102), so the cheapest sensor costs >= ~17/h
  (2.996 / T_r) and the declared 6/h set would be **empty: both verdicts FAIL by construction** (review finding 1; 6/h needs >= 0.4993 h, about 10 no-fault cells). At
  3/T_r (T_r = the training no-fault hours) exactly one zero-alarm sensor is affordable. The 6/h point is still computed and reported, without a verdict. The descriptor's
  `analysis.passRule` text predates this and still says 6/h; it does not gate the analysis (the registry does, its digest recorded), and changing it would move every pinned digest.
- **Decision 111 (user, 2026-10-13): decision 84's own-sensor exclusion stays for the off-path classes.** Every sensor of frauddetectionservice is a miss in the fraud-pause class,
  every accountingservice sensor in the accounting-pause class, so the signal pilot v2's criterion used (the target's own consumer spans) cannot pass the rule. **Prediction,
  stated before launch from pilot v2 (not from E):** the Kafka group coordinator logs "Member … has failed, removing it from the group" about 43-44 s after the pause command
  (+43.3 to +44.2 s; present in 4/4 pilot off-path cells, absent in 2/2 no-fault and 2/2 frontend-pause cells, counted with `/usr/bin/grep` over the cells' logs), which follows the
  consumers' 45 s session timeout. A Kafka-side sensor is therefore the likely pick, and its detection time is set by that timeout, so a pass would say which lane sees the fault and
  when, not how strong the placement method is. Broker metrics (`metric:kafka:*`, 34 ids in the OTel vocabulary) have unmeasured responses to a consumer pause.
- **Decision 100 (split):** 5 blocks; placement solved on blocks 1-3, frozen, scored once on blocks 4-5.
- **Decision 101:** the runtime tier is cumulative (a set costs the cumulative posture steps needed to emit all its members; an async sensor also pays the selected step).
- **Decision 102:** the detectors that score E's test blocks are calibrated on the training blocks only and applied unchanged to the test blocks.
- **What the design implies for the rule (stated, not changed):** a class has **2 test episodes** (one cell per block 4 and 5), so passing needs *both* to improve and *a single invalid test
  cell of the class makes its verdict `—`* (fewer than 2 valid test episodes). A fault that is not kept contributes no episodes and no verdict. No pass-rule number has been computed. With one sensor at 3/T_r and 2 test episodes per class, the verdict is close to a yes/no on whether the chosen sensor fires in both test cells.

The descriptor carries the rule text (`analysis.passRule`, `analysis.calibration`, `analysis.split`); the descriptor is not the registry and does not gate the analysis.

## The analysis chain (measurement repo; all still DRAFT, to be frozen by digest before any E cell is read)
1. **Reader:** `research/detection-time/sweep_analysis_v3_2.py` (imports the frozen v3.1 and v2.4; header `STATUS: DRAFT, NOT FROZEN, not reviewed`). Train-only calibration (decision 102): the
   test blocks are passed as `--test-blocks 4 5`, the cells of those blocks are flagged `heldOut`, excluded from every fit, and still scored as episodes with the training-calibrated detectors.
   `--blocks 1 2 3` makes the training readout; `--split <split.json>` records the declared split's sha256 (`{train: [1, 2, 3], test: [4, 5]}`).
2. **Placement:** `research/placement/celf_v3_2.py <training readout> --tiers research/placement/declared/otel.effort.json --tier-catalog postureCurrentCatalog --split <split.json> --out <new file>`:
   the tiered-budget frontier ((max effort x max runtime) x budgets 0, 3/T_r, 6/h, inf) on blocks 1-3 only; it refuses a readout of every block unless `--allow-unsplit`.
3. **Scorer:** `research/placement/score_test_v3_2.py <readout covering blocks 4-5> --placement <frozen celf_v3_2 output> --training-readout <its input readout> --test-blocks 4 5 --out <new file>`; sets are never re-solved; the pass rule is read from the registry.

Digest freeze (to do): the three scripts, `research/protocol/parameters_v3_2.json`, the effort file, the split file; pinned digests recorded; independent review. **Items found while drafting, settled in `085b715`:** (a) the registry's `otel-offpath-e-v1` epoch entry (the placeholder name equals this epoch's) still lists the `productcatalog-cpu-throttle-effect`
regime and `shape: campaign-B`, and its origin text says it is a placeholder to re-pin at the harness commit: E has no throttle regime (decision 108) — removed, origin names `d1358bb`, a planted
throttle cell under E is refused (UnknownSchema), `shape: campaign-B` kept (it is how decision 92 admits C-shaped epochs); (b) `score_test_v3_2.py`'s usage example showed `--test-blocks 4 5 6` — now `4 5`;
(c) the effort/runtime tier file and the cost frontier are the coordinator's (BUDGET_E decision 98); open: the tier file was generated by an inline
script and lists the 1,705 ids of the v3.1 OTel readout, so ids that only E emits get unknown tiers (admitted only under `any`). The pass rule reads the
unrestricted frontier cell (`effort<=any, runtime<=any`), so the tier file cannot change a verdict; it changes the tiered cost report only. Its committed generator is `research/placement/declared/build_otel_effort.py` (`a3522eb`; regenerates the committed file byte-identically
apart from `generatedAt`). Split file: `research/protocol/split_e_otel.json` (`931d53d`, sha256 `107cb13a…9844`). **Open before the freeze (review findings 4, 6):** add pilot v2
to `V32_EPOCH_PROFILES` and run the v3.2 reader on its 8 fetched cells (the reader has never read a real mix-ledger cell); re-pin the provisional registry entries' text at `6a5c2a9`.

## Evidence handling
Fetch and byte-verify (read-only on the host) after the terminal. Case `otelE1` in `scratchpad/gate-drivers/fetch_overnight.sh` (added 2026-10-13; the script is a scratchpad file with uncommitted changes of its own):
```
  otelE1) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-offpath-e-v1; O=tmp/otel-e-evidence/e1-fetch ;;   # OTel campaign E (DECLARATION_E_OTEL.md, plan 503bf014, 25 req/s, fraud+accounting+frontend pause)
```
Evidence stays out of git (`tmp/` is gitignored); a relaunch gets a new fetch directory (`e2-fetch`), never overwriting `e1-fetch`. The retained cells are replayed with `validate_cell` and the criteria script before any scoring.

## Launch (worktree HEAD must be the activation commit; DRY_RUN first)
A relaunch (attempt 2; at most 1, harness or infrastructure defects only) uses plan `c2f0928b96539956c262fc62d1a93fce4cb5297a247baad7c79a1b7060679eb9` (`--attempt 2 --print-digests` at `6a5c2a9`)
and `OTEL_CANDIDATE_ATTEMPT=2`; whether a consumer restart or OOM counts as such a defect is the user's call at that time. Filled: activation commit `6a5c2a997fd56e72b886043a50e151ef16c13ba3` (worktree HEAD; `94641f5` activates, `6a5c2a9` re-pins governance on top), plan `503bf014cfb51cc85c96010b2dc4632fe24bba644c804c21fbd405b7bb517661`, RUN_COUNT 20.
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
git -C ../observability-placement-runtime-otel-protocol rev-parse HEAD        # must equal 6a5c2a997fd56e72b886043a50e151ef16c13ba3
DRY_RUN=1 OTEL_CANDIDATE_ATTEMPT=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_offpath_e.py EXPECTED_PLAN=503bf014cfb51cc85c96010b2dc4632fe24bba644c804c21fbd405b7bb517661 \
  RUN_COUNT=20 CAMPAIGN=otel-offpath-e-v1 LOG_PREFIX=otel-offpath-e-v1 \
  zsh scratchpad/gate-drivers/launch_otel_offpath.sh e1dry 6a5c2a997fd56e72b886043a50e151ef16c13ba3 \
  > scratchpad/gate-drivers/otel-offpath-e-v1-e1dry.out 2>&1
# after a passing DRY_RUN and the committed-alone declaration (same variables, no DRY_RUN):
LAUNCH_APPROVED=1 OTEL_CANDIDATE_ATTEMPT=1 OTEL_WORKTREE=$PWD/../observability-placement-runtime-otel-protocol \
  COMPILER=candidate_offpath_e.py EXPECTED_PLAN=503bf014cfb51cc85c96010b2dc4632fe24bba644c804c21fbd405b7bb517661 \
  RUN_COUNT=20 CAMPAIGN=otel-offpath-e-v1 LOG_PREFIX=otel-offpath-e-v1 \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh e1 6a5c2a997fd56e72b886043a50e151ef16c13ba3 \
  > scratchpad/gate-drivers/otel-offpath-e-v1-e1.out 2>&1 &
nohup uv run python tools/wandb_campaign.py follow otel-offpath-e-v1-e1 scratchpad/gate-drivers/otel-offpath-e-v1-e1-launch.log \
  > scratchpad/gate-drivers/otel-offpath-e-v1-e1-wandb.out 2>&1 &
```
The launcher's watcher cap is the window + 1 h, read from the drivers' `CONFIG.run_window_hours` (derived from the compiler's `RUN_WINDOW_HOURS`: 3, 4 or 5 h by variant, see the table).
Before a launch: one campaign per host (check fb14srv6, not a log); the pilot v2 is terminal (12:42Z 2026-10-12) and fetched (147/147); a failed earlier `oneshot` strands `gates/gate-run.json` and the lease lock (archive both before a retry).

### Activation checklist (done: `c547ebb`, `0788151`, `94641f5`, `6a5c2a9`; mirrors `12b626a`, `a045b9c` and `ff29b93`)
1. Set `RATE` and `KEPT_FAULTS`, regenerate the descriptor, compare both digests with the table, run `tests/test_otel_offpath_e.py`.
2. `execution/study-epoch.json` names `otel-offpath-e-v1`; `ADMITTED_STUDY_EPOCHS = ("otel-offpath-e-v1",)` in `candidate_setup.py` and `candidate_remote.py`; the extension ledger's selector purpose.
3. Tests that pin the selected epoch: flip `test_e_is_not_activated_the_selector_and_the_tombstone_still_name_the_running_pilot`; add `"otel-offpath-e-v1": <window>` to the `windows` table of
   `tests/test_otel_traffic_sweep.py` (`test_driver_config_and_adapter_follow_the_selector_of_the_tree_they_read`; 5, 4 or 3 by variant). The tombstone-equals-selector test needs nothing.
4. No governed file moves at activation (the epoch commit moved `candidate_runtime.py` and `candidate_runtime_adapter.py`, re-pinned in the commit after it); re-check with `tests/test_otel_v2_epoch.py`.
5. The launcher's local plan check and drivers check print `otel-offpath-e-v1 20 503bf014cfb51cc85c96010b2dc4632fe24bba644c804c21fbd405b7bb517661` and `otel-offpath-e-v1 otel-offpath-e-v1 <window>`; then DRY_RUN.

## Risks the build cannot settle without running
1. **productcatalogservice at its upstream 20 MiB limit** was memcg-OOM-killed at 100 req/s of the mix in pilot v1 (cell 2, 09:50:16Z, about 14.7 s before its pause command) and Docker's restart invalidated the cell. E repeats the same load in 10 to 20 cells;
   whether that many repetitions are safe at the chosen rate is unknown. An OOM-restart of an application service blocks the cell (the container-health restart guard; `oomKilled` reads false after the restart, so the restart is what is caught).
   The campaign stops on its first invalid cell (as the pilot's); an early stop leaves the training blocks incomplete. **Pilot v2 at 25 and 50 req/s:** 8/8 cells valid, no restart
   caught (instance, 8 cells, ~45 min); E runs 20 cells at 25 req/s, about 2.5x the pilot's exposure at the lower of its two rates.
2. **Frontend saturation:** the single-process Node frontend uses about 10 ms CPU per request (the pilot v1 review), about 0.5 core at 50 req/s and saturation near 100 req/s. E runs at 25 req/s, about a quarter of that; frontend CPU in the pilot was not measured (`?`), but the no-fault cells at 25 and 50 req/s had every ledger row ok (1500/1500, 3000/3000 in the hold).
3. **Consumer restart after a pause:** after 60 s paused a Kafka consumer's session (45 s default) has expired and it rejoins on unpause; if either consumer exits or Docker restarts it, the container-health guard invalidates that cell (decision 104 accepts the rebalance, not a restart). Each off-path class has 2 test cells, so one such cell turns that class's verdict into `—`.
4. **The 256 MiB frontendproxy under a frontend pause at 50 req/s:** a paused frontend holds RATE x 15 = 750 requests in Envoy at 50 req/s (375 at 25). The pilot v2 review's arithmetic (about 294 MB at 750 waiting requests, from the attempt-1 baseline) is above 268 MB (256 MiB).
   Pilot v2's frontend pause at 50 req/s was valid (no restart caught); E runs at 25 req/s, 375 waiting requests, below the 50 req/s cell that passed.
5. **Otelcol and jaeger are not in `APP_SERVICES`:** an OOM-restart of either (1 GiB each) does not by itself invalidate a cell (the pilot v2's risk 10, unchanged).
6. **Disk and volume:** a cell writes up to a few hundred MB of collector log and about as much pcap (`?`); 20 cells plausibly 4-10 GB (`?`); the launcher refuses below 40 GB free (srv6 had 239 GB at the pilot's DRY_RUN).
7. **Host and time:** fb14srv6 only (hosts are not exchangeable; E is a within-host campaign); the pilot v2 must have ended; a VPN drop blinds the coordinator, not the campaign.
8. **Guards calibrated to the pilot:** descriptor equality to Python literals, pinned digests and cell counts are literals of this epoch's compiler; reshaping E (another block count, rate or fault) surfaces them one at a time, which is why the two parameters are limited to the 12 prepared pairs.

## What is not decided here
- The two parameters (the coordinator, after the pilot verdict; the user may veto E's rate rule).
- The 256 MiB floor of the frontendproxy at 25 req/s (an engineering default, recorded).
- Whether 2 test episodes per off-path class are enough for the pass rule (decisions 99-100 are the user's; stated above as a design property, no change made).
- The registry and tier-file items listed under the analysis chain.

## Tests (OTel worktree)
- At the launch commit `6a5c2a9` (worker report, 2026-10-13; the coordinator re-ran `--print-digests` under `/usr/bin/python3 -I` with the Apple bytecode cache cleared: row 1's
  digests): `tests/test_otel_offpath_e.py` and `tests/test_otel_offpath_pilot_v2.py` 80 passed; `tests/test_otel_v2_epoch.py` 10 passed. Full worktree suite
  (`--ignore=tests/test_mlflow_manifest.py`, mlflow not installed): **29 failed, 2401 passed, 145 skipped**, run twice with the same 29. They are the same 29 modules as at `0d6578a`
  and on a clean `ff29b93` export (below): none is an OTel Demo test (4 Hotel materializer, 1 Kieker, 12 + 1 Online Boutique, 6 phase-1 control universe, 1 science router,
  1 TeaStore witness, 1 native bridge, 2 patched images; four submodules uninitialised in that worktree; the 6 phase-1 failures include a stale `materialize.py` binding in its
  matrix, a ledger row, present when pilot v2 ran). One load-sensitive flake seen once (`test_run_cell_executes_a_sweep_cell...[productcatalog-cpu-throttle-effect-10.0]`, F1
  gate), passed alone 5/5 and in the next full run.
- Measurement repo, v3.2 files at `085b715`: 108 passed (planted: a throttle cell stamped E is refused).

### At the epoch commit (the build agent's record, 2026-10-12)
- `tests/test_otel_offpath_e.py` at `d1358bb` (unchanged at HEAD `0d6578a`): **52 passed** (about 85 s). Planted defects, each caught: the split (blocks 1-2 / 3-5, a split that leaves a block out or lists one twice), the block order
  (frontend first, no-fault last, frontend before the off-path pauses, an off-path pause before the no-fault cell, a lost or repeated cell; all refused by the rule, with the pin bypassed), the strata (v2's one stratum, C's 3, another seed), the two
  parameters (RATE 100, 37.5 and an int; a fault set without an off-path pause, in a non-canonical order, a list, empty; the rate edited without regenerating the descriptor; a stale or missing table pin), run-ID reuse (E under pilot v2's epoch id: 4 reused
  IDs found), the sizing (a C-sized generator, a smuggled SUT limit, the 50 req/s sizing kept at 25), the wiring (E out of the family tuple, the controller set, the sampler and retention tuples). The 12 variants' digests, run counts and budgets are pinned in the file
  and re-derived under `/usr/bin/python3 -I` (3.9); 3 variants run the coordinator's switching procedure on tree copies, through the gate chain; a fraud cell at 25 req/s and four cells at 50 req/s (no-fault, fraud, accounting, frontend pause; a training and a
  test block each) run end to end on v1's fake target with the terminal's replay.
- **Source plants** (a source edit, the file run with `-x`, the edit restored): 12 of 12 caught: split 1-2/3-5, block-group order reversed, the order rule removed from `validate_plan`, `check_parameters` a no-op, concurrency fixed at the 50 req/s value, EPOCH = pilot v2's,
  onset strata 3, kept faults ignored, E dropped from `REPEAT_STUDY_EPOCHS`, the default variant's pin edited, the frontendproxy floor removed, the seed changed. (A thirteenth plant did not apply: its search string no longer matched; not counted.)
- Full worktree suite (`uv run pytest -q -p no:cacheprovider -rf --ignore=tests/test_mlflow_manifest.py`) at HEAD `0d6578a`: **29 failed, 2401 passed, 145 skipped** (940 s). The 29 `FAILED` names are identical (`diff`, no output) to the 29 that fail when the same ids run on a clean export of `ff29b93`
  (`git archive`, run in isolation with this worktree's environment: 29 failed, the 30th id passed there); none is an OTel Demo test (4 Hotel materializer, 1 Kieker, 12 + 1 Online Boutique, 6 phase-1 control universe, 1 science router, 1 TeaStore witness, 1 native bridge, 2 patched images).
  Delta against the pilot v2's 2349 passed: +52 = the E file. Two earlier runs of the same suite are not the result: the first (48 failed) had a stale bytecode cache of my own plant harness (a same-size, same-second restore left a seed-changed `.pyc` of `candidate_offpath_e.py`, deleted; the repo's known
  bytecode-cache trap) plus one load-sensitive `test_srv5_harness` deadline test; the second (30 failed, 33 errors) had load-sensitive F1 gate failures in the pilot v1 fixtures and one repeat-tree test, with background load on the laptop. Neither has anything of E in it.
- Measurement repo `tests/test_unbound_names.py`: 321 collected (320 before; +1, environmental, the sibling worktree's new compiler module `candidate_offpath_e.py`, which passes); `CLAUDE.md`'s count is not edited here.
- Governance: `tests/test_otel_v2_epoch.py` 10 passed after the re-pin commit (`candidate_runtime.py`, `candidate_runtime_adapter.py` bound to `d1358bb`).

## Review
Reviewer: Fable 5.1 adversarial read-only review subagent (same provider; the cross-provider judge server did not connect), 2026-10-13 ~02:30Z, on this file at harness `6a5c2a9`.
Verdict: **NO-GO as written; GO at `6a5c2a9` after (1) and (2).** The plan, the 20-row table, the digests (3.9 and 3.13), the sizing, the guards, the spent-attempt bookkeeping,
the run IDs and the launch command were re-derived by the reviewer and match. Findings and what was done:
1. BLOCKER: the 6/h set is empty by construction (3 training no-fault cells), so both verdicts FAIL. **User decision 110: the rule reads 3/T_r** (registry `f60e7fb`).
2. Own-exclusion removes the directly manifesting signal; a pass rests on Kafka-side sensors. **User decision 111: exclusion kept, prediction stated** (above).
3. The split file did not exist: **added** (`931d53d`).
4. The v3.2 reader has never read a real mix-ledger cell; pilot v2 is not in `V32_EPOCH_PROFILES`: **open, before the freeze.**
5. Tier file provenance: **generator committed** (`a3522eb`).
6. Registry entries still provisional: **open, at the freeze.**
7. The remote stops at the first invalid cell; attempt 2's plan digest: **added** (launch section).
8. Citation of `RESULT_V2.md` corrected (`4ddd451`); the fetch case `otelE1` sits in an uncommitted scratchpad script; the DRY_RUN is re-run after this file is committed.


## Amendment 1 (2026-10-13 ~05:35Z, committed alone; E terminal-pending, no E cell read beyond receipt states)
Decision 112 (user, on the v3.2 chain review's blocker; protocol `eebcbf2`, code `de6d21a`, registry `V32_RECURRENCE_RULE` and `V32_PASS_RULE`).
It supersedes the wording above where they differ (the text above is kept as committed):
- **The pass-rule set is read at 6/T_r** (`frontier (effort<=any, runtime<=any) @6/T_r`, both off-path classes): two zero-alarm sensors evaluated in
  every training fold (2 x 2.996/T_r <= 6/T_r). The 3/T_r and 6/h points stay computed and reported without a verdict.
- **Recurrence rule:** a sensor is a candidate for every frontier set only if it has a counted fire (after the per-class own exclusion) in >= 2
  training episodes of at least one class. Why (review B1, counted on the pilot v2 shakedown readout, not on E): per-line log hashing gives 17-34
  non-own `appear` ids in the first 5 s of each off-path pilot episode, 0 shared with any other episode, so at 3/T_r the single slot went to a line
  that cannot fire in the test blocks (a synthetic run of the frozen solver confirmed it). The filter's removals are recorded per rate.
- **Cost wording (review F6):** "a zero-alarm sensor costs 2.996/T_r" above means a zero-alarm sensor **evaluated in every training fold**; one
  evaluated in fewer folds costs more and may not fit.
- **Stated before freezing:** the Kafka member-failed ids are appear-only, recur within a class (the same 3 ids at both pilot rates) and are
  disjoint between fraud and accounting, so each off-path class needs its own slot; a recurring sensor of the frontend class may take one of the two
  slots, and then one off-path class FAILs by construction. With two slots and 2 test episodes per class the verdict is close to a yes/no on whether
  that class's sensor fires in both test cells. The descriptor's `analysis.passRule` text (6/h) predates decisions 110-112 and does not gate.
- **Closed since the declaration:** pilot v2 in `V32_EPOCH_PROFILES` and the reader read its 8 cells (`ab7fc5e`); the provisional registry entries
  re-pinned at `6a5c2a9` and set active (`675df55`); the v2.4 reference fit is train-only (`4d88108`); the registry digest gets a pin
  (`PINNED_PARAMETERS_V32_SHA256`, `4121c1f`). Open until the freeze: the reader's draft label strings, the digest pins, a fresh review of the changed chain.

## Amendment 2 (2026-10-13 ~06:15Z, committed alone before the v3.2 freeze; E terminal 05:35Z, fetched 357/357, no E cell read beyond receipt states)
From the third review (Fable subagent, same provider; GO for the freeze with text and pin fixes). Statements made before any E cell is read, from
pilot v2 data and the code:
- **The ledger can fire first.** In pilot v2 at 25 req/s the request ledger fired inside both off-path episodes before the Kafka ids (fraud 10.68 s,
  `ledger:frontendproxy:product` `run3`; accounting 42.87 s, `ledger:frontendproxy:index` `absent`; calibrated on 1 no-fault cell, E calibrates on 3).
  Under decision 99 a ledger catch counts and improvement is strict, so a ledger fire before the set's sensors in either test episode of a class makes that
  class FAIL whatever the placement. The scorer's per-episode ledger detection time is reported next to each verdict.
- **Training-side validity.** With the recurrence rule a class with fewer than 2 valid training episodes has no recurring class-specific candidate and would
  FAIL rather than `—`. All 20 E receipts read `valid`, so every class has 3 training episodes; if the offline replay invalidates a training cell, the
  verdict rule for that class goes to the user before scoring.
- **Two-step freeze of the scorer.** `PINNED_PLACEMENTS` sits inside `score_test_v3_2.py`, so its digest is recorded at the freeze and once more after the
  one-line placement pin (after the training placement exists, before any test-block cell is read). No production run uses `--allow-unpinned` (the flag
  is not recorded in the outputs).
- **Budget list:** the analysis chain step 2 above lists budgets 0, 3/T_r, 6/h, inf; the frozen code also has 6/T_r (Amendment 1).
- **Determinism pre-check:** the training read (`--blocks 1 2 3`) runs twice and the two `calibration` blocks are compared before the placement, since the
  scorer refuses a scoring readout whose calibration differs from the training one.
