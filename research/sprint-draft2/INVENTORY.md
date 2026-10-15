# Retained log/metric inventory for SPRINT_DRAFT2_20260924 (2026-09-24)

Read-only inventory. Nothing was modified, moved, deleted or extracted beyond directories that were
already extracted on disk. No host was contacted. `otel-run2-evidence` / `otel-run3` staging was not
opened (embargoed); OTel is out of scope for this inventory anyway (dropped as test SUT, D-S4 is
"offline only" and the sprint's per-SUT list is TeaStore/Hotel/Online Boutique).

Counts below use `/usr/bin/find`, `/usr/bin/grep`, `tar -tzf` and `/usr/bin/python3 -I` reading JSON
keys only (no interpretation of values beyond schema/shape). Every count names its denominator.
Absence is `—`, never 0.

---

## 1. TeaStore

Harness contract in every cell: `receipt.json` has `resourceUse` = `"cost-proxy"` (no-fault-cost
regime, `resources.json` present, a real time series) or `"diagnostic-only"` (fault regimes,
`resources` is `null`, **no metric samples retained for any TeaStore fault-regime cell inspected**).
This held in every campaign checked (#10–#15, epoch-3 idle/user/stress, per-sensor S4) with no
exception found.

Log retention is per-cell `auth.log` + `persistence.log` (auth/persistence services only) written by
the app-witness bridge, gated by a `service-log-capture.json` receipt (`capturedLog.complete`,
`sha256`, `measurementWindow`). Whether the log **files themselves** (not just the receipt) are
present on this laptop varies by which fetch script pulled the campaign off the host — see table.
Additionally, 8-of-40 `a5-user` run dirs (blocked cells / their re-runs) carry a full `.operational/`
dump with **all 8 services'** `docker logs` (auth, persistence, image, recommender, registry, webui,
db, rabbitmq).

Exposure-window fields (fault regimes only): `receipt.json.intervention.actualOnsetWall` /
`actualOffsetWall` (+ monotonic offsets), and `receipt.json.exposureTolerance.window.{startEpoch,endEpoch}`
(a tolerance-scoped sub-window). Present in every fault-regime cell inspected.

| Campaign (dir) | Regime | Cells valid/total | Log files retained per cell | Metric form | Exposure window |
|---|---|---|---|---|---|
| `tmp/teastore-e3-user-a5-evidence/…/teastore-candidate-pilot-v3-user` | auth-freeze-effect | 12/12 (part of 32/36 campaign, `verdict: pass-with-flags`) | `auth.log` + `persistence.log` **files present**, plus 8-service `.operational/*.log` dump in 3 of these 12 (blocked/rerun cells only) | none (`resourceUse: diagnostic-only`) | y — `intervention.actualOnsetWall/actualOffsetWall`, `exposureTolerance.window` |
| same | persistence-crash-effect | 12/12 | same pattern; 1 of 12 has `.operational` dump | none | y |
| same | no-fault-cost | 12/12 | receipt only, no log content needed | **time series**: `resources.json`, 120 samples @ 5 s (`fixed-rate-slots-v1`), 600 s window, per-container `cpuPercent`+`memoryBytes` (5 services: auth/image/persistence/recommender/webui) + aggregate `applicationCpuSeconds`/`applicationMemoryPeakBytes` | n/a (no fault) |
| `tmp/teastore-e3-user-a1-evidence` (`v3-user`) | auth-freeze-effect + no-fault-cost | 22 valid (`campaign-abort.json`, aborted before persistence-crash-effect at "13 events, 30 tolerated" collector rejector) | 0 log files (`auth.log`/`persistence.log` count = 0 across this dir) — receipts only | resources.json present for no-fault-cost cells only | y (same fields) |
| `tmp/teastore10-evidence` (`x/teastore-candidate-pilot-v1`) | all 3 regimes | 18 valid (`campaign-abort.json`, aborted on "collector container parse failures") | 0 log files (receipts only) | resources.json, no-fault-cost only, 9 cells | y |
| `tmp/teastore11-evidence` | all 3 regimes | 27/27 (`verdict: pass`, `runCount: 27`) | 0 log files | resources.json, no-fault-cost only, 9 cells | y |
| `tmp/teastore12-evidence` | auth-freeze-effect + no-fault-cost | 11 valid (`campaign-abort.json`, aborted before persistence-crash-effect) | 0 log files | resources.json, no-fault-cost only | y |
| `tmp/teastore13-evidence` | all 3 regimes | 27/27 (`verdict: pass`) | 0 log files | resources.json, no-fault-cost only, 9 cells | y |
| `tmp/teastore14-evidence` | all 3 regimes | 27/27 (`verdict: pass`) | 0 log files | resources.json, no-fault-cost only, 9 cells | y |
| `tmp/teastore15-evidence` | auth-freeze-effect + no-fault-cost | 17 valid (`campaign-abort.json`, aborted before persistence-crash-effect; AspectJ parent-aspect defect per CLAUDE.md) | **19 auth.log + 19 persistence.log files present** (this fetch DID retain log content) | resources.json, no-fault-cost only, 9 cells | y |
| `tmp/teastore-e3-idle-evidence` (`v3-idle`) | no-fault-cost only | 12/12 (`verdict: pass`) | 0 log files | resources.json, all 12 cells (idle load, 0 j/s) | n/a |
| `tmp/teastore-e3-stress-evidence` (`v3-stress`, att-1) | no-fault-cost only | — (no terminal-validation/abort file found at this path; `runtime-journal.jsonl` present, not parsed) | **12 auth.log + 12 persistence.log present** | resources.json, all 12 cells | n/a |
| `tmp/teastore-e3-stress2-evidence` (`v3-stress`, att-2) | no-fault-cost only | 12/12 (`verdict: pass`, `blockedCells: 0`) | **12 auth.log + 12 persistence.log present** | resources.json, all 12 cells | n/a |
| `tmp/per-sensor-v1-evidence` / `per-sensor-attempt3-evidence` (`teastore-per-sensor-v1`) | no-fault-cost only (per-sensor placements, S4) | 21/24 (`verdict: pass-with-flags`, `blockedCells: 3`) | auth.log/persistence.log present in both fetches | resources.json, all cells (schedule = per-sensor-v1) | n/a (no fault regime in this study) |

**Denominators for "detected by logs / detected by metrics" on TeaStore, as retained on this
laptop:** fault episodes with both a retained exposure window AND retained log/metric content exist
only where the "log files retained" column says "present" — i.e. `a5-user` (24 fault cells: 12
auth-freeze + 12 persistence-crash) and `#15` (up to 19, but #15 never reached persistence-crash-effect,
so its fault cells are auth-freeze-effect only). **Metric-based detection inside a fault window has
denominator 0 for every TeaStore campaign inspected** — no campaign retains `resources.json` (or any
per-sample metric) for a fault-regime cell; `resourceUse` is explicitly `"diagnostic-only"` there.
This is a harness property (cost sampling is switched off during fault regimes), not a laptop-fetch
gap — confirmed structurally via `receipt.json`, not inferred.

---

## 2. HotelReservation

Harness contract in every cell: a combined `application.log` (docker-compose multiplexed stdout,
one line per container prefixed `service-N |`, **all services in one file**, not split) and a
`cpu.json` metric time series. Fault cells additionally carry `fault-receipt.json`.

`cpu.json` schema: `samples[]` of `{applicationCpuPercent, capturedAtEpoch, capturedAtMonotonic,
containers:[{containerId, cpuPercent, service}]}`, `intervalSeconds: 1.0`, all 10 Hotel services
(`frontend, search, geo, rate, reservation, profile, user, recommendation, review, attractions`).
**No memory field anywhere in `cpu.json`** (confirms `MEMORY.md`'s "memory lost" note) — CPU-percent
only, per service, 1 Hz, sample count varies by cell length (40 samples seen in one 200 s-class
cell — a ~20% duty-cycle sampler per existing memory note, not resolved further here).

`fault-receipt.json` exposure-window fields: `startedAt` / `endedAt` (wall clock),
`startedMonotonic`/`endedMonotonic`/`unpausedAtMonotonic`, `actualOutageSeconds`,
`requestedOutageSeconds`, `scenario`, `targetService`. Present in every effect-regime cell found.

| Campaign (dir) | Cells (`cell-terminal.json` count = total cells with a terminal record) | `application.log` retained | `cpu.json` retained | `fault-receipt.json` (= effect-regime cells) |
|---|---|---|---|---|
| `tmp/hotel-campaign1-evidence` (#1) | 8 (memory: "8 valid cells", aborted at first fault cell) | 10 | 10 | 2 |
| `tmp/hotel-campaign2-evidence` (#2) | 24 (24/24 per memory) | 24 | 24 | 16 |
| `tmp/hotel3-evidence` (#3) | 23 (23/24 per memory) | **0 — absent, not zero** | 25 | 17 |
| `tmp/hotel4-evidence` (#4) | 24 (24/24 per memory) | **0 — absent, not zero** | 24 | 16 |
| `tmp/hotel5-evidence` (#5) | 24 (24/24 per memory) | 24 | 24 | 16 |
| `tmp/hotel6-evidence` (#6, 5 timestamped `.tgz` snapshots, `tar -tzf` counted, not extracted) | 54 attempt dirs per snapshot (not yet resolved to valid/total; campaign known "runs 3–6 pooled, 24 blocks" per memory — this dir may span more than the pooled subset) | 54 (per snapshot) | 54 (per snapshot) | 36 (per snapshot) |

**Container logs are NOT retained at all for campaigns #3 and #4** (0 of 23 and 0 of 24 cells) —
confirmed by `/usr/bin/find … -name application.log` returning 0 in both trees, at every depth. This
answers the CLAUDE.md prompt's question directly for those two campaigns: no, none. Campaigns #1,
#2, #5 and #6 do retain it, one file per cell (see below).

**Denominator for Hotel log detection**: fault episodes with both `application.log` and
`fault-receipt.json` present = campaigns #1 (2), #2 (16), #5 (16), #6 (36 per snapshot, valid/total
not resolved here) = the union of instrumented-posture effect-regime cells in those campaigns.
Campaigns #3 and #4's fault episodes (17 + 16 = 33) have `fault-receipt.json` (metric + exposure
window) but **no log** — usable for metric-only detection, not log detection.

**Denominator for Hotel metric detection**: every effect-regime cell across #1–#6 has `cpu.json`
(CPU-percent time series, no memory) — 2+16+17+16+16+36(#6 snapshot) — union across campaigns, not
summed as independent replicates without checking for pooling rules (`MEMORY.md`: "#9 cells can't
pool with #10" is a TeaStore-specific note; no equivalent Hotel pooling rule was checked here).

`tmp/hotel-fadh085-audit`, `tmp/hotel-c1-cell9`, `tmp/hotel-campaign1-evidence/observability-placement-candidate-v4-runs`
exist as single-cell/audit sidecars; not separately inventoried (out of the 90-minute budget; each
looked like a subset of the campaign directories above by spot-check of top-level names).

---

## 3. Online Boutique

**No fault regime exists anywhere in retained Online Boutique evidence.** Both evidence generations
found are single-block (`b01`) `{none, selected, full}` posture smoke runs with no pause/kill/fault
step. `MODALITY_SCOPE_PLAN`'s "hold-out, zero cells" is confirmed structurally: 0 fault-shaped
directories under any `online-boutique*` evidence tree (`/usr/bin/find . -path "*online-boutique*"
-iname "*pause*"` → 0 hits outside `.git`).

**Consequence for the sprint's detection objective: Online Boutique's fault-episode denominator is
`—` (not 0 — no fault was ever run, so there is nothing to detect or fail to detect).** Both retained
generations are documented below for completeness (they inform the log/metric *form*, not detection).

| Evidence dir | Stack | Log retained | Log form | Metric retained | Metric form |
|---|---|---|---|---|---|
| `.local/evidence/online-boutique-lgtm-srv6-v9-20260809-pristine/b01-{none,selected,full}` | kind + LGTM (Loki/Tempo) | y — `logs-normalized.json`, produced by `modules/online-boutique-lgtm/normalizers/loki.py` (`{timestampNs, line, labels}`) | 1767 / 1754 / 1766 rows (none/selected/full); 5 services with any rows: `currencyservice` (1011), `frontend` (529), `cartservice` (123), `adservice` (99), `productcatalogservice` (5) — **not** all 11 OB services | y — `resources.json` | **node-aggregate only**: `scope: "aggregate-kind-control-plane; not application-attributed"`, one container (`kind` control-plane), ~3 s interval, `CPUPerc`/`MemUsage` — **not per-service**, cannot support per-service metric detection |
| `.local/evidence/online-boutique-compose-p0c-20260817-authoritative/campaign/b01-{none,selected,full}` (+ `acquisition-canary`) | docker compose + otelcol | **— absent**, no `logs-normalized.json` or any log file in this tree | n/a | y — `resources.json` | **per-service** time series: `intervalSeconds: 2.0`, samples `{capturedAt, cpuPercent, memoryUsage, service}` per OB service (frontend, productcatalogservice, currencyservice, cartservice, … ) |

No `Mimir`/metrics backend was ever built for OB (`MIGRATION_LOSS.md` §3b, confirmed here by absence
of any metrics-service reference in either evidence tree).

---

## 4. Commands run (re-runnable)

```sh
# Discovery
find tmp -maxdepth 1 -type d
find .local -maxdepth 2 -type d

# TeaStore structure and cell counts
find tmp/teastore-e3-user-a5-evidence -maxdepth 3
find "tmp/teastore-e3-user-a5-evidence/teastore-candidate-pilot-v3-user/runs/<regime>" -maxdepth 1 -type d | wc -l
/usr/bin/python3 -c "import json; d=json.load(open('.../campaign-terminal-validation.json')); print(d['runCount'], len(d['validCells']), d['blockedCells'], d['verdict'])"
/usr/bin/python3 -c "import json; d=json.load(open('.../campaign-abort.json')); print(d['validCells'], d['stage'])"

# TeaStore log/metric presence per campaign (repeat <dir> for each teastoreNN-evidence / e3-*-evidence)
find "<dir>" -name "auth.log" | wc -l
find "<dir>" -name "persistence.log" | wc -l
find "<dir>" -name "resources.json" | wc -l
find "<dir>" -type d -name ".operational" | wc -l

# TeaStore receipt schema (exposure window, resourceUse)
/usr/bin/python3 -c "import json; d=json.load(open('<cell>/receipt.json')); print(d['intervention']['actualOnsetWall'], d['intervention']['actualOffsetWall'], d['resourceUse'])"

# Hotel: count without extracting further (tgz already-extracted 'x' dirs read directly)
find "<hotel-dir>" -name "application.log" | wc -l
find "<hotel-dir>" -name "cpu.json" | wc -l
find "<hotel-dir>" -name "fault-receipt.json" | wc -l
find "<hotel-dir>" -name "cell-terminal.json" | wc -l
tar -tzf tmp/hotel6-evidence/<snapshot>.tgz | grep -c "application.log$"   # for un-extracted snapshots

# Hotel fault-receipt schema
/usr/bin/python3 -c "import json; d=json.load(open('<cell>/fault-receipt.json')); print(d['startedAt'], d['endedAt'], d['actualOutageSeconds'])"

# Online Boutique
find .local/evidence -maxdepth 1 -iname "*online-boutique*"
/usr/bin/python3 -c "import json; d=json.load(open('.../logs-normalized.json')); print(len(d))"
/usr/bin/find . -path "*/online-boutique*" -iname "*pause*"   # fault search, 0 hits
cat modules/online-boutique-lgtm/normalizers/loki.py
```

---

## 5. Gaps (`—`, not 0)

- TeaStore: no campaign retains `resources.json` for a fault-regime cell — metric-in-window
  denominator is `—` for every TeaStore campaign, structurally (not a fetch omission).
- TeaStore: `#9` evidence not found anywhere on this laptop (`find tmp -iname "*teastore9*"` → 0
  hits outside worktree/log-name false positives). Cannot be inventoried; `—`.
- TeaStore campaigns #10–#14 and `e3-user-a1`: `auth.log`/`persistence.log` content is `—` (receipts
  present, files not fetched to this laptop) — a fetch-completeness gap, distinct from the TeaStore
  metric gap above, which is structural.
- Hotel campaigns #3 and #4: `application.log` is `—` for all cells (0 of 23, 0 of 24) — logs were
  either not captured or not fetched; not determined which, from this laptop alone.
  `tmp/hotel-fadh085-audit`, `hotel-c1-cell9` and the `observability-placement-candidate-v4-runs`
  sidecar were not resolved to distinct cell/valid counts inside the 90-minute budget.
- Hotel #6: valid/total cell split not resolved (5 raw `.tgz` snapshots, likely sequential retries of
  the same in-flight campaign; `—` until parsed against `MEMORY.md`'s "runs 3–6 pooled, 24 blocks").
- Online Boutique: fault-episode denominator is `—` everywhere (no fault was ever run against OB in
  retained evidence) — this blocks the go/no-go's per-family, per-regime table for OB entirely; OB
  cannot contribute a log-vs-metric detection comparison this sprint.
- Online Boutique LGTM smoke: log rows exist for only 5 of OB's ~11 services (the rest emitted 0
  matching Loki rows in that window) — `—` per service, not 0, for the other services, since the
  Loki query itself was not re-run to confirm true silence vs a label mismatch.
