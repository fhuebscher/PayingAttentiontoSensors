# LMT+S Hotel pilot: result (lmt2, 2026-09-28)

Scope of every number here: **instance** (Hotel, fb14srv4, one campaign, n = 4 blocks per regime). Not pooled with Hotel #1-#8 or S4.

## Run

- Campaign `hotel-v1-20260928t133750z-e6a3bc45`, plan `e1e617469f48...` (harness `lmt-pilot-20260928` at 40682b7, DECLARATION Amendment 1).
  Launcher started 13:36Z by the user (the human authorization; SETUP-CAMPAIGN was renewed and GATE-RUN derived by the harness, see
  `scratchpad/gate-drivers/hotel-lmt2-launch.log`), terminal 17:50Z. `campaign-terminal.json`: 80 cells, 80 valid,
  `candidateCampaignValid: true`. `docker ps -aq` on fb14srv4 after terminal: 0 containers.
- Fault receipts: 64 of 64 `successful` (16 per regime). Throttle (`profile`, `--cpus 0.1`) and net delay (`rate`, netem 100 ms): held 15 s.
  Failed requests of 1200 per cell: 0 in 32/32 throttle and delay cells and 16/16 no-fault cells; 140-141 in 32/32 pause cells
  (`post_hoc.py`, post hoc). The receipt's `routeAvailableDuring` is one probe right after apply, not a watch over the hold.
- Fetched with `fetch_overnight.sh hotellmt2`: 4252 of 4252 host files, `shasum -c` rc 0, into `tmp/hotellmt2-evidence/x` (not in git).
- lmt1 (`hotel-v1-20260928t114413z-a49116ba`) stopped at cell 1 with 0 valid cells and enters no analysis (Amendment 1).
- Analysis: `cost_steps.py` and `lmt_detect.py`, byte-identical to their declaration commit a6711f0 (`git diff a6711f0 -- research/lmt-pilot/*.py`
  is empty), each run once on `tmp/hotellmt2-evidence/x`. Raw output: `out/cost_steps.lmt2.json`, `out/lmt_detect.lmt2.json`.
- Post hoc, after the Fable review (not declared): `post_hoc.py` imports `lmt_detect.py` unchanged; output `out/post_hoc.lmt2.json`.

## Cost (no-fault regime, 4 complete blocks, 120 s window)

Paired block deltas: mean [min, max], positive count of 4. Both signs among the 4 give "sign undetermined", as declared.

| step | app CPU-s (10 Go services) | daemon CPU-s (dockerd + containerd) | total CPU-s | p50 ms |
|---|---|---|---|---|
| none -> logs | +0.08 [-0.07, +0.27] 3/4, undetermined | +0.00 [-0.08, +0.07] 2/4, undetermined | +0.09 [-0.00, +0.29] 3/4, undetermined | +0.01 [-0.04, +0.06] 2/4, undetermined |
| logs -> metrics | -0.11 [-0.26, +0.08] 1/4, undetermined | +3.35 [+3.33, +3.40] 4/4 | +3.25 [+3.07, +3.43] 4/4 | +0.02 [-0.05, +0.07] 2/4, undetermined |
| metrics -> full | +8.64 [+8.61, +8.74] 4/4 | +4.05 [+4.01, +4.10] 4/4 | +12.69 [+12.62, +12.84] 4/4 | +1.38 [+1.33, +1.50] 4/4 |
| none -> full | +8.62 [+8.50, +8.76] 4/4 | +7.41 [+7.36, +7.45] 4/4 | +16.03 [+15.89, +16.11] 4/4 | +1.41 [+1.34, +1.54] 4/4 |

What the columns cover, and what they do not:
- "app" is the ten Go service containers (attractions, frontend, geo, profile, rate, recommendation, reservation, review, search, user).
  **Not costed:** `jaeger`, `consul`, the 12 mongodb/memcached containers and the load generator. `jaeger` runs in every posture, so the cost
  of receiving and storing spans in `full` is outside every column.
- "daemon" is the host-wide `docker.service` and `containerd.service` cgroups: it covers dockerd/containerd work for all 24 containers
  (jaeger's included), the docker-events stream (every posture) and anything else on the host (`nuisance.json`: no foreign Compose project).
  The harness's own docker-stats client, system sampler and TCP snapshots are outside every column.
- The always-on collectors (witness line, system sampler, docker events, TCP snapshots) run in every posture and cancel; their own cost is not measured.
- "logs" is the application logger going from zerolog FatalLevel to info. `none` is not zero log output: in the checked cell (cost b01 p01-none)
  36 lines are not witness lines (10 "TLS disabled." before the level is set, 25 gRPC-library lines, 1 `docker compose logs` CLI warning).
  The Fable review counted all 20 `none` cells: 32-50 non-witness lines each, 2-4 gRPC GoAway lines inside the 120 s window.
- The step is a posture contrast. Which process inside dockerd/containerd pays the daemon delta is not measured here.

## Detection (four fault regimes)

caught / n episodes per family. n is the postures that collect the family x 4 blocks. Top sensors exclude the target (G2) and inadmissible sensors (G3).

| regime (target) | L (n 12) | M (n 8) | T (n 4) | S (n 16) |
|---|---|---|---|---|
| search-pause (search) | 0 | 8, `M:profile:cpu` 8 | 4, 12 spans of frontend, geo, profile, rate, reservation 4 each | 1, `S:recommendation:sys_memory` 1 |
| reservation-pause (reservation) | 12, `L:frontend:4ae82b46d72e` 12 | 7, `M:profile:cpu` 7 | 4, profile/frontend spans 4 each | 0 |
| cpu-throttle (profile) | 0 | 1, `M:search:cpu` 1 | 0 | 0 |
| net-delay (rate) | 0 | 1, `M:profile:cpu` 1 | 4, `T:search:/rate.Rate/GetRates`, search/frontend spans 4 each | 0 |

G3 made inadmissible: M `frontend` (2/8 no-fault windows), `rate` (1/8), `reservation` (1/8) cpu; S `sys_memory` of 7 services (frontend,
geo, profile, rate, reservation, review, search). No-fault windows per family are 12 (L), 8 (M), 4 (T), 16 (S); in every family one firing
is above the 5 % bar, so G3 removes any sensor that fires even once, and "no admissible firing in a no-fault window" holds by construction.

M catches are CPU drops of non-target services, not rises (Fable review count over all M symbols: 76 `spike_down` + 61 `plateau_down`, 2 `spike_up`).
T catches in the pause regimes include `missing_expected` spans (callers' downstream spans that stop while the target is paused).

Post hoc, on the target itself (what G2 removes; `out/post_hoc.lmt2.json`):

| regime (target) | target sensors that fire |
|---|---|
| search-pause | `M:search:cpu` 8/8; 3 `T:search:*` spans 4/4 |
| reservation-pause | `M:reservation:cpu` 8/8; 3 `T:reservation:*` spans 4/4 |
| cpu-throttle | `S:profile:sys_psi_cpu` 15/16 (0/16 in no-fault windows) |
| net-delay | `T:rate:*` 2 spans 4/4; `M:rate:cpu` 1/8 |

### Carried findings

| # | reads | from |
|---|---|---|
| C1 | **yes** | `L:frontend:4ae82b46d72e` in 12/12 reservation-pause L episodes, 0/12 search-pause L episodes |
| C2 | **no** | `M:rate:cpu` is inadmissible (G3: 1 of 8 no-fault M windows), so it fires in 0 scored episodes |
| C3 | **no** | C2 is no |

Post hoc: before G3, `M:rate:cpu` fires in 8/8 search-pause and 1/8 reservation-pause M episodes, so C2's rule ("in no reservation-pause
episode") fails even without G3. `M:profile:cpu` is one of four sensors that fire 8/8 in search-pause before G3 (frontend, profile, rate,
reservation cpu), and the only one of the four that never fires in a no-fault window. C3 reads no only because of G3 and the one
reservation-pause firing; it does not test whether the inside-fault window changes C1 or C2.

## What this cannot say

- n = 4 blocks and 4-16 episodes per cell of the detection table: no rate, ranking or interval.
- cpu-throttle is caught by 1 of 40 family-episodes on non-target services. On the target, `S:profile:sys_psi_cpu` fires in 15/16 throttle
  episodes and 0/16 no-fault windows (post hoc), so the throttle raised profile's own CPU stall; what the families did not see is a
  change on another service. Whether no such change occurred at this load, or the families missed it, is not separated.
- S is caught in 1 of 64 fault episodes. The pilot does not tell apart floors that are too high (`SYS_FLOORS`) from system signals
  that do not move under these faults.
- One host, one SUT, one campaign.

## Ledger (not fixed; the declared scripts stay as run)

- `cost_steps.py` / `lmt_detect.py` exit 0 with empty output when given a directory without `runs/` (first invocation here pointed at a
  wrong path and printed all-null steps with rc 0). An absent input should fail. Add a guard in a later version; this result used the correct path.
- `lmt_detect.py` `topSensors` truncates ties with `most_common(5)` over a set's iteration order, so which tied sensors are listed depends on
  `PYTHONHASHSEED` (Fable review: three seeds, three lists; every count identical). The tables here list the full tie set from `post_hoc.py`.
