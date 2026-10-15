# LMT+S Hotel pilot: what is measured and how it is read (committed before any pilot cell exists)

Budget, stop rule and design decisions: `BUDGET_AND_STOP_RULE_20260928.md` (a3fb947, 5e01ecc). Harness: branch `lmt-pilot-20260928` of
`../observability-placement-runtime-hotel-srv4`, epoch `hotel-reservation-lmt-pilot-v1`, 80 cells (5 regimes x 4 blocks x 4 postures, a
4x4 Latin square per regime), fb14srv4. Nothing here is pooled with Hotel #6 (runs 1-8) or the S4 baseline.

## Postures and what each collects

| posture | application logs | docker-stats metric sampler (1 s) | tracer | always on in every posture |
|---|---|---|---|---|
| `none` | off (`LOG_LEVEL=disabled`) | off | disabled (NoopTracer) | request witness line, docker events, system sampler (5 s), TCP snapshots, cost cgroup edges |
| `logs` | info | off | disabled | same |
| `metrics` | info | on | disabled | same |
| `full` | info | on | full sampling | same |

The always-on collectors are the same in every posture, so they cancel in every step and their own cost is **not** measured.

## Cost (no-fault-cost regime, 4 blocks): `cost_steps.py`

Per step (`none->logs`, `logs->metrics`, `metrics->full`, `none->full`) and per complete block: the paired difference in
- app CPU: cgroup `usage_usec` delta of the ten application containers over the 120 s window;
- daemon CPU: the same for `docker.service` + `containerd.service` (where json-file logging and docker-stats sampling are paid);
- total = app + daemon;
- p50 latency of completed requests (ledger rule of `hotel_cost_axes.py`).

Reported: block mean, [min, max] of the 4 block deltas, positive count. No interval, no test. A step whose block deltas have both signs is
reported as "sign undetermined". Scope: instance, one host, n = 4 blocks.

## Detection (four fault regimes): `lmt_detect.py`

- Families: L (log templates; postures logs, metrics, full), M (docker-stats CPU; metrics, full), T (spans; full), S (system sampler: cgroup
  CPU rate, memory, io rate, PSI cpu/memory/io rates; all four postures). Each family is scored only over the postures that collect it, so
  per regime n = 12 (L), 8 (M), 4 (T), 16 (S).
- Window: inside the fault (receipt `appliedMonotonic` .. `revertingMonotonic`); no-fault cells get a pseudo window at the median offsets.
- Gates: G2 (target service excluded) and G3 (sensor inadmissible if it fires in more than 5 % of its family's no-fault windows) on every
  family, spans included. This changes the S4 frozen rule, which left spans uncalibrated (review finding: FA 28/30 spans entered R(p)).
- Symptom rules: the symptom alphabet v0 of `research/s4-conjunction/symptoms.py`, imported unchanged; S floors in `lmt_detect.SYS_FLOORS`.
- Reported per regime x family: caught / n, the top non-target sensors, and per family the no-fault windows with any admissible firing.

## Carried findings, read as yes / no / `—` (not new predictions; the pause regimes repeat Hotel #6)

| # | Finding carried from the S4 baseline | Reads "yes" iff, in the pilot |
|---|---|---|
| C1 | the frontend availability template (`4ae82b46d72e`) fires in reservation pause, not in search pause | L top sensor in reservation-pause is `L:frontend:4ae82b46d72e` in every L episode, 0 search-pause L episodes |
| C2 | rate CPU separates search pause from reservation pause | `M:rate:cpu` fires in every M search-pause episode and in no M reservation-pause episode |
| C3 | the inside-fault window changes nothing for C1/C2 | both C1 and C2 read yes |

For `cpu-throttle-effect` and `net-delay-effect` nothing is predicted: this is the first time they run on any system here.

## What this cannot say

n = 4 blocks per cost step and 4-16 episodes per family and regime. The pilot shows whether collecting logs and metrics has a measurable
cost on this host and which families react to a degradation that is not an absence; it does not establish a rate, a ranking or a
cross-system property.

## Amendment 1 (2026-09-28, before any valid pilot cell; lmt1 has 0 valid cells)

- `none` logs at zerolog **FatalLevel** (`LOG_LEVEL=fatal`), not `Disabled`. Under `Disabled` all ten services exit 1 at start
  (`log.Fatal().Msg(srv.Run().Error())` in every `cmd/*/main.go`; zerolog 1.31 runs Fatal's exit inside `Fatal()` when the level is
  off, before `Run()` is evaluated). Measured: `scratchpad/gate-drivers/lmt_readiness_diag.sh`, disabled 10/10 services restarting
  (12 restarts in 180 s), info ready in 10 s. FatalLevel is the level directly above error, as the user decided; a normal cell emits no
  application log line at it. PanicLevel would disable Fatal the same way.
- The CPU throttle is lifted by `docker update --cpus <NCPU>`, because `--cpus 0` is a no-op on this daemon (host smoke, 2026-09-28).
- Harness `lmt-pilot-20260928` at 40682b7: descriptor `9df5b462...`, plan `e1e617469f48dc9df973ee4016a4415f4eac7ead5b533bacfb3a5a5afadd5d46`,
  80 cells. lmt1 (`hotel-v1-20260928t114413z-a49116ba`, plan `a0f21b56...`) is retained as a blocked run and enters no analysis.
