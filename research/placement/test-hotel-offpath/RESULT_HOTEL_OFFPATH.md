# Result: Hotel off-path epoch `hotel-offpath-v1` (campaign `hotel-v1-20261014t225950z-36b91d24`)

**Scope of every statement: instance** (one SUT, Hotel; one host, fb14srv4; one campaign; 5 episodes per (regime, rate)). Nothing here is cross-SUT or a mechanism claim. `—` = absent or
not evaluable, never 0. **Review status: none independent.** The chain (v3.4 reader and scorer) had one same-provider review before any cell was read
(`research/protocol/FREEZE_V34_20261015.md`); no cross-provider `judge` panel ran (the judge MCP server failed to connect in this session); this document has had no review.

## Chain and commits (each output committed unedited, in its own commit, before its values were read)

| step | what | commit | sha256 |
|---|---|---|---|
| declaration | `research/traffic-sweep/DECLARATION_HOTEL_OFFPATH.md` | `4945293` | — |
| predictions | `research/protocol/PREDICTIONS_OVERNIGHT_20261014.json`, ids HO-* | `8b89d43` | `57529300012ea7d52848f10c574e8089596010c5705d01a7f9b13c8d0d743a0d` |
| frozen reader | `research/protocol/FREEZE_V34_20261015.md` (46 of 46 digest rows re-checked equal before the readout, `shasum -a 256 -c`) | `380b5b6` | — |
| fetch | `bash scratchpad/gate-drivers/fetch_overnight.sh hoteloff1` -> `tmp/hotel-offpath-evidence/off1-fetch` (gitignored): host files 2878, OK 2878, shasum rc=0 | not committed (evidence stays out of git) | `source.txt` names `fb14srv4:/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1/hotel-v1-20261014t225950z-36b91d24` |
| replay driver | `research/placement/test-hotel-offpath/replay_hotel_off1.py` | `e655452` | — |
| offline terminal replay | `research/placement/test-hotel-offpath/terminal-replay-off1.json` | `0c8da6f` | `7cb87acb9448deec02b785906fc7fe795e58f1d6bdf209579013abf6d6e7facf` |
| readout (v3.4, this fetch only, no legacy cells, no `--validation`/`--split`) | `research/traffic-sweep/readout-hotel-offpath-off1-v3.4/` | `3ac90e8` | `sweep_analysis_v3_4.json` `7cdb4caaac73f5c611f364cbfc69dd530f8ae39e92cb34ae0fb952204890b81c`; `SWEEP_ANALYSIS_V3_4.md` `22588abfb9e466eb71989eae061cc18b38f95c4adf6c7fcc0e7c54714f7beb01` |
| scoring | `research/lanes/out-hotel-offpath-off1/` (`HO_SCORE.json`, `HO_SCORE.md`) | `03a5f44` | `HO_SCORE.json` `3fb8c247c8fe46bd9571ace5d58d0c587b92a1fda6f0e8d1363a451eb518cfae`; `HO_SCORE.md` `04574046c8b14d67da0eacf0a4d8944b71503e290a5f44ea72d50db8f6d500f1` |

Harness `9ad0b98194f715b921aba187df5ed511082f1f7b`, plan `90b7b621c8a1e54a92a78f813bb9c73ee829eddf4ef615e8806edd50d1df2f2a`, 30 cells.

## Validity

- Host terminal (`campaign-terminal.json`, sha256 `3c3a8b1fd41524b541456dbd3e36aed97747b675dcedaf12d1203e35c0289ca6`): `candidateCampaignValid` true, `cellCount` 30, `validCellCount` 30, manifest `fileCount` 2876,
  verdict `pass`.
- Offline replay at 9ad0b98 under `/usr/bin/python3` 3.9.6 (`-I -B`; the Apple bytecode cache had no entry for the main repo or the Hotel worktree before the run): 30 of 30 cells replay valid and
  the replayed cell terminal is canonical-byte-equal to the retained one in 30 of 30; the campaign-level `validate_campaign` over the retained contracts and `runtime-admission.json` returns
  `candidateCampaignValid` true, 30 valid, byte-equal to the host terminal (canonicalSha256 `bd37777f...926f1`). The replay remaps the host path to the fetch directory (the harness's own
  `configure_path_remap`), which is how the earlier Hotel replays ran. `replay_hotel_off1.py` is a thin adaptation of `tmp/traffic-sweep-decision25-replay-20261003/replay.py` (mode `old`),
  which takes the remote root from the directory name and so cannot be used on a directory called `x`.
- Readout: `campaignsRead` lists exactly `tmp/hotel-offpath-evidence/off1-fetch/x`, found 30, valid 30; `v34.hotelOffPathEpochsRead` = `["hotel-offpath-v1"]`; `v34.designCounts`: declared 5, found 5,
  valid 5 in each of consul-pause-effect r1 and r10, search-pause-effect r1 and r10, no-fault-calibration r1 and r10. "Cells not scored: none". Off-path manifestation record (consul-pause, 10 of 10):
  manifested by rule 10 of 10 (container read back paused; 1 docker pause and 1 unpause event each); route outage observed (recorded, not required): 0 of 10.

## The consul log-layout gap (as declared in FREEZE_V34 finding 1)

The Hotel parser keeps records of three layouts (zerolog JSON, zerolog console, Go log); `FREEZE_V34_20261015.md` finding 1, written before any cell was read, said consul's documented default lines match
none and that consul would have docker-stats and cgroup sensors (metric channel) but no log sensor, although the declaration lists logs among consul's collected channels. The readout's
`v34.extraCollectedServices["hotel-offpath-v1:consul"]`: 30 cells with a sensor of the service (metric 30), 7 distinct sensors, **6363 consul lines in `application.log` over 30 cells, 0 log sensors**.
The readout's own note: "no Hotel log layout ... parsed one: the service has no log sensor, its log channel is a dead channel for this reader". Adding a layout would change what may be measured (a
preregistration decision, the user's); none was added. Every consul number below is therefore a metric-channel number; there is no consul log lane in this readout.

## HO-* scored (`HO_SCORE.json`; 20 fault episodes, 5 per (regime, rate), shortfall none)

| id | verdict (scorer's words) | numbers (source: `HO_SCORE.json` rows) |
|---|---|---|
| HO-ONT-search | per item: lane:own `disagree`; lane:coordinator, lane:lag, CQ-C1 class, CQ-L2 window `not comparable`; CQ-B1 entry reached (ledger-lane proxy) `agree` | measuredOwn: any-field 10 of 10 episodes, counted 5 of 10, range 0.2-1.09 s; measuredLedger: any 10 of 10, counted 0 of 10, range 0.21-1.11 s |
| HO-ONT-consul | per item: lane:own `disagree`; coordinator, lag, CQ-C1, CQ-L2 `not comparable`; CQ-B1 entry reached `agree` | measuredOwn: any 10 of 10, counted 5 of 10, range 1.81-4.75 s; measuredLedger: any 1 of 10, counted 1 of 10, 1.77 s |
| HO-C | `hit (by construction)` | coordinator/lag fires in any episode: none, of 20 episodes. **True by construction of the lane rules** (`V34_LANE_RULES` declares no coordinator or lag lane for Hotel); a `hit` is the rule's, not a measurement that no service observes consul |
| HO-L1 | `hit` | search-pause, own lane, any field, detected 5 of 5 at r1 and 5 of 5 at r10; median earliest fire r1 0.7851 s (band 0.70-1.54), r10 0.2322 s (band 0.21-0.28); both inside. **Every one of those 10 fires is in the by-construction field** (flag `BC-downstream-absent`, sensor `span:search:/geo.Geo/Nearby`, 0.197-1.094 s); see the counted field below |
| HO-L2 | `miss (counted field)` | consul-pause, 10 episodes, 7 own sensors collected in each; own fire in any field 10 of 10, in the counted field 5 of 10; earliest own fire 1.8140 s; firing ids `metric:consul:cpu`, `metric:consul:sys_cpu`, `metric:consul:sys_psi_cpu`; armed own sensors `metric:consul:cpu`, `sys_cpu`, `sys_io`, `sys_memory`, `sys_psi_cpu`. The prediction's `—` was wrong for this build: a consul own-lane fire is reported |
| HO-D1 | `hit` | search-pause r1 -> r10 (the only pair with gap >= 4x): own medians 0.7851 -> 0.2322 s, ratio 0.2958; ledger medians 0.7975 -> 0.2427 s, ratio 0.3044; threshold 0.5. Both medians are the scorer's any-field values (by-construction field for own) |
| HO-D2 | `—` | the rule is `—` (no prediction) |

Rates 0.05 and 0.2 are not in this epoch (rates 1 and 10 only): the HO-L1 bands for them are `—`.

## Lanes, as the readout reports them (`v33.lanes`; counted field beside the by-construction field)

Own lane = the episode target's sensors; coordinator and lag lanes `—` for every row ("no coordinator lane is declared for this system", "no lag lane is declared for this system").

| regime | rate | episodes with collected own sensors | with a counted own fire | earliest counted own fire, median [min, max] | with a by-construction own fire | earliest by-construction own fire, median [min, max] |
|---|---|---|---|---|---|---|
| consul-pause-effect (own via metrics) | 10 | 5 of 5 | 0 of 5 | — | 5 of 5 | 1.8736 s [1.8140, 1.9094] (`metric:consul:cpu`, flag `BC-idle-cpu`) |
| consul-pause-effect (own via metrics) | 1 | 5 of 5 | 5 of 5 | 4.7502 s [4.3305, 9.1588] (`metric:consul:sys_psi_cpu`, rule spike) | 5 of 5 | 4.3305 s [4.0274, 4.7502] (`metric:consul:sys_cpu`, flag `BC-idle-cpu`) |
| search-pause-effect | 10 | 5 of 5 | 5 of 5 | 19.8166 s [19.7725, 19.8521] (`metric:search:sys_psi_cpu`) | 5 of 5 | 0.2322 s [0.1970, 0.2699] (`span:search:/geo.Geo/Nearby`, flag `BC-downstream-absent`) |
| search-pause-effect | 1 | 5 of 5 | 0 of 5 | — | 5 of 5 | 0.7851 s [0.2916, 1.0941] (`span:search:/geo.Geo/Nearby`, flag `BC-downstream-absent`) |

consul: coordinator `—`, lag `—`, own through the metric channel only (see the log-layout gap). consul's ledger lane: 1 of 10 episodes (r1, 1.77 s) in the primary-outcome table (E, 1/5 at r1, 0/5 at r10).

## Search-pause control (the epoch's P1/P2 regime)

- **P1** (decision 54's interval; observed = first `failed` catch): 10 of 10 hold, r10 5 of 5, r1 5 of 5, not evaluable 0; every cell holds via the timeout interval; verdict `holds`.
- **P2**: r10 5 of 5 episodes, counts [11, 11, 11, 11, 11]; r1 5 of 5, counts [2, 2, 2, 2, 2]; verdict `—` at both (n < 4, `EPISODES_HOTEL` 4 not rebound; finding 3 of the freeze record). Rates 0.2 and 0.05: `—`.
- P4a search-pause: r10 0/5, r1 0/5 (ledger missed, sensor caught: 0 in both). P4b search-pause: r10 0/5, r1 0/5 (0 in both). P4a consul-pause: r10 0/5, r1 0/5 (ledger missed, sensor caught: 3 in both).
  P4b consul-pause: r10 0/5 (sensor caught 0), r1 0/5 (sensor caught 4). Highest-rate verdicts `—`. P3: `—` for every fault.
- Primary-outcome table, search-pause (E = ledger rule family): r10 E 5/5, median 0.24 s [0.21-0.28]; r1 E 5/5, median 0.80 s [0.30-1.11]. consul-pause: r10 E 0/5; r1 E 1/5 (1.77 s).
- No placement verdict and no test scoring exist for this epoch (descriptor `analysis.placementVerdict` null).

## What the numbers do not carry (stated, not resolved)

- The HO-L1 `hit` and the HO-D1 `hit` rest on by-construction-field own fires (`BC-downstream-absent`); the counted own lane at search-pause is 0 of 5 at r1 and, at r10, 5 of 5 at a median of 19.8166 s (outside HO-L1's r10 band
  0.21-0.28 s). The prediction rule scores "any field", so the verdicts stand as scored; the counted-field numbers are in the lane table above.
- HO-C is true by construction (above).
- The readout's lane block reports the search-pause ledger lane (scorer evidence `measuredLedger`) as counted 0 of 10, while the primary-outcome table reports E 5/5 at both rates with "E no BC (= E)". The two are computed by different readers
  (the lanes block uses `pooled_lanes`' E-family fires with own fires dropped; the table uses v2.4's E rule family); this document does not reconcile them.
- n = 5 episodes per (regime, rate), two rates; the calibration is the epoch's own no-fault cells (5 per rate), per finding 6 of the freeze record.
