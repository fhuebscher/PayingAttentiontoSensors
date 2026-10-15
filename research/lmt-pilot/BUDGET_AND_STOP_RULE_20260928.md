# Hotel LMT+S pilot for rc4: budget and stop rule (committed alone, 2026-09-28 10:40Z, before any engineering)

**User decisions (2026-09-28):** rush a pilot into rc4 (not after submission); add faults that are not an absence (network delay, CPU stress)
beside the two pause faults. Purpose: measure the collection cost of logs, metrics and system information per step, and score which signal
types catch each fault class with the by-construction parts designed out where possible.

**Scope:** HotelReservation on fb14srv4 only, a new epoch of the Hotel lineage (not pooled with Hotel #6 runs 1-8). TeaStore untouched.

**Design defaults (engineering, recorded in the descriptor; the user may overrule before launch):**
- Postures, nested ladder, one signal type per step: `none` (tracer off, logging driver `none`, no metric sampler, no system collector) ->
  `logs` -> `logs+metrics` -> `logs+metrics+traces` (= today's `full`) -> `all` (+ system collector).
- Cost reading identical in every posture and outside every switch: per-container cumulative cgroup CPU read once at window start and once
  at window end, and workload p50 latency.
- System information: `docker events` lifecycle stream, per-container cgroup counters, one TCP connection snapshot per window.
- Fault window set from `docker events` pause/unpause (and injector start/stop) timestamps, so it covers the fault interval only.
- Regimes: cost, reservation-pause, search-pause, delay (netem on one service), cpu-stress (one service). Blocks: 3. Cells = 5 x 5 x 3 = 75,
  about 3.8 h at the Hotel #6 rate (183 s/cell).

**Budget and stop rules:**
- Engineering budget 14 h, hard stop 21 h (150 %).
- **Launch-ready by Tue 29 Sep 20:00Z** (tests green, the Hotel AST guards green, offline replay of retained Hotel #6 cells through the new
  validators, `DRY_RUN=1` launcher green). If not, the pilot is dropped from rc4 in writing that day, rc4 is submitted as tagged
  (`asoca-rc4-20260928`), and the work continues as the Hotel part of Epoch U.
- **Launch by Wed 30 Sep 06:00Z** (the launch is the user's). A campaign not terminal by Wed 30 12:00Z is not used in the paper.
- The rc4 edit from pilot results gets one Fable review before the tag; if that review is not done by Wed 30 18:00Z, rc4 is submitted as tagged.
- Per-defect rule: 30 minutes on the critical path, else a ledger row.
- Blocked cells are preserved and flagged; the launcher stops only on >= 3 blocked with 0 valid.

## Decisions after the harness map (2026-09-28 11:05Z, before any code)

- **User:** 4 postures + both new faults; application logging off = a level above error (zerolog `Disabled`).
- **Postures (nested by what is switched on):** `none` (tracer off, `LOG_LEVEL=disabled`, no docker-stats sampler) -> `logs` (+ info logging)
  -> `metrics` (+ 1-s docker-stats sampler) -> `full` (+ tracer, sample ratio 1). The claim ceiling keeps `placement-lattice-nesting`
  prohibited: steps are reported as adjacent-pair contrasts, not as a lattice.
- **Always on, every posture (not a step, its cost not measured):** request witness (stdout), per-cell `docker events` stream, a system
  sampler every 5 s (per-container cgroup `cpu.stat`, `memory.current`, `io.stat`, PSI `cpu/memory/io.pressure`), and cumulative cgroup CPU
  of the ten app containers plus `docker.service` and `containerd.service` read at window start and end (the cost axis).
- **Faults:** reservation-pause, search-pause (unchanged); `cpu-throttle` (`docker update --cpus 0.1` on one service, restored after
  the hold); `net-delay` (`sudo nsenter -t <pid> -n tc qdisc add dev eth0 root netem delay 100ms` on one service, removed after the hold).
  Targets are engineering defaults recorded in the descriptor. Delay is dropped first if it is not working by Tue 29 12:00Z.
- **Blocks:** 4 per regime, 4x4 Latin square (each posture in each position once). 4 x 5 x 4 = 80 cells, about 4.1 h.
- **SUT patch:** one added `case "DISABLED","disabled": zerolog.SetGlobalLevel(zerolog.Disabled)` in `tune/setting.go`.
- **Lineage:** the pilot lives on branch `lmt-pilot-20260928` of the Hotel runtime worktree as its own epoch. Hotel #6 cells keep replaying
  on 31d69af; the pilot's validators accept only the pilot's shape. The launch-ready criterion "offline replay of retained Hotel #6
  cells through the new validators" is replaced by: the suite green on the branch, the unchanged 31d69af replaying r8 as before, and
  planted-defect checks for each new validator. This is an engineering default.
- **Stop semantics:** Hotel's stop-on-first-invalid-cell is kept (no engineering); if the campaign aborts, the valid cells of complete
  (regime, block)s are evaluated, preregistered here.
