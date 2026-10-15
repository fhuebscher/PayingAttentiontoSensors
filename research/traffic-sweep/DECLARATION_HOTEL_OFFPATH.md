# Hotel Reservation off-path pause (consul): declaration (2026-10-14)

**Status: committed alone, before the launch below.** Budget `BUDGET_OVERNIGHT_20261014.md` (`cf50078`, item 4). Predictions committed before launch:
`research/protocol/PREDICTIONS_OVERNIGHT_20261014.md` (`8b89d43`, ids HO-*). Scope: instance (fb14srv4).
## What it is
Epoch `hotel-offpath-v1` in the Hotel worktree (`observability-placement-runtime-hotel-protocol`, commits `e7c6cf1`, `34b4fd4`, `8b4ec01`, activation
`3303c57`, review fix `9ad0b98` = the launch commit). Compiler `candidate_offpath.py`, descriptor digest `d9bf052e…`, plan
`90b7b621c8a1e54a92a78f813bb9c73ee829eddf4ef615e8806edd50d1df2f2a`, 30 cells: regimes `no-fault-calibration`, `consul-pause-effect` (60 s pause of consul,
which is off the request path: services register without health checks, `registry.go:77-92`; the frontend's resolver watch keeps existing connections)
and `search-pause-effect` (on-path control), rates 10 and 1 req/s, 5 blocks, shuffled per block (seed 20261015), no lead cell.
- Consul manifestation: container paused (read back) plus the Docker pause/unpause events on consul's own container; the route outage is recorded
  (`outageObserved`), not required. The on-path rule (`paused and outageObserved`) is unchanged for search-pause.
- Collection scope adds consul (logs, docker stats, cgroup, system samples, TCP snapshots, image receipt, cleanup) for this epoch only; application CPU
  sums stay over the ten application containers, consul reported separately.
- Independent same-provider review of the build: one launch blocker (consul's own image id refused by `_images`), fixed in `9ad0b98` with a test on the
  real image receipt. Known limits from the review: `outageObserved` is one probe after the pause; probe traces not listed for off-path cells.
- **This is the declared negative control:** no coordinator observes consul, and there is no queue. Expected (HO-*): no coordinator or lag lane for either
  fault; consul own silence `—` unless consul telemetry is collected and fires; search-pause detected by the ledger as before.
- DRY_RUN `offdry1` passed 2026-10-14 22:57:53Z (srv4 0 containers, 172 GB free; SETUP-CAMPAIGN expired, renewed by `auto`).
## Analysis
Reader v3.3 is frozen and has no Hotel off-path epoch profile; the Hotel readout of this epoch therefore needs a registry admission entry, written and
committed **before** any cell is read, and reviewed; until then only validity fields are read. Predictions HO-* are scored on that readout.
## Launch
```
cd /Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
HOTEL_ROOT=$PWD/../observability-placement-runtime-hotel-protocol COMPILER=candidate_offpath.py \
  EXPECTED_PLAN=90b7b621c8a1e54a92a78f813bb9c73ee829eddf4ef615e8806edd50d1df2f2a RUN_COUNT=30 \
  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_hotel.sh off1 > scratchpad/gate-drivers/hotel-off1.out 2>&1 &
```
At most 1 relaunch, harness or infrastructure defects only.
