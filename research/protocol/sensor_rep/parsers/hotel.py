"""Hotel Reservation parser: one `runs/**/attempt-01` cell -> events. Per-SUT code lives only here.

Reused, unchanged, by path: `symptoms.parse_stream` + `HOTEL_LAYOUTS` (zerolog JSON/console, Go log with gRPC
severity), `symptoms.template_id`, `symptoms.op_token`, `symptoms.span_error`, `symptoms.epoch`;
`lmt_detect._rates` and lmt_detect's sys_io / sys_memory derivation for the cgroup sampler; the ledger row reading of
`research/visibility-map/visibility.py:116-123` (ok = outcome completed and status 200).

Engineering defaults (recorded):
- every channel present on disk is read, whatever the posture; which channels a posture *collects* is the
  population's posture table (`COLLECTS` below, = the oracle's FAMILY_POSTURES), applied downstream. A channel file
  that is missing gives `present: False` and no events (absence is not zero: `—`).
- clocks: logs, spans, metrics on the wall clock (epoch seconds); the ledger on the harness monotonic clock. The base
  of both is the barrier (plan `barrierAt` / `barrierMonotonic`); the fault window is the receipt's
  appliedMonotonic..revertingMonotonic, mapped to wall time through the barrier (lmt_detect._wall).
- old-rule pre-window lower bound t0 = barrier (wall) for sensors; unbounded for the ledger (ledger_check.py: every
  request started before the window).
- ledger route token = the plan's `workloadId` (Hotel drives one route); entry service = `frontend`.
- service of a log line = the compose prefix `<service>-<n> | ` (symptoms.hotel_cell); lines without it are compose CLI.
- metric `cpu` = docker stats cpuPercent per container (resolution = cpu.json intervalSeconds); `sys_*` = cgroup sampler
  (system-samples.json intervalSeconds): sys_cpu cores, sys_memory bytes, sys_io bytes/s, sys_psi_{cpu,memory,io} stall
  usec/s, exactly as lmt_detect.load_cell derives them.
- Hotel frontend emits a periodic (79-80 s, phase-locked to start-up) ERROR-level gRPC `GoAway ENHANCE_YOUR_CALM`
  template (VALIDITY.md §1b/§7). It is NOT filtered: it is an ordinary log token. Under the old rule it never falls in
  the 45-60 s window; under the new rule's tiles it enters the vocabulary (so it can neither appear nor, with a
  per-window median of 0, disappear). Its token is listed in the manifest as `knownPeriodic` so a reader can find it.
"""
import json
from collections import defaultdict
from pathlib import Path

from . import common
from ..events import Event, level_class, stream_meta

SUT = "hotel"
ENTRY = "frontend"
GOAWAY_TEXT = "GoAway"
COLLECTS = {      # posture -> channels (families) the posture collects, per population (oracle FAMILY_POSTURES)
    "lmt2": {"L": ("logs", "metrics", "full"), "M": ("metrics", "full"), "T": ("full",),
             "S": ("none", "logs", "metrics", "full")},
    "sel1": {"L": ("metrics", "selected", "full"), "M": ("metrics", "selected", "full"), "T": ("full",),
             "Tsel": ("selected",), "S": ("none", "metrics", "selected", "full")},
}
COLLECTS["int1"] = COLLECTS["sel1"]


def cell_dirs(x):
    return sorted(Path(x).joinpath("runs").glob("**/attempt-01"))


def parse_cell(attempt, population):
    S = common.symptoms()
    L = common.lmt()
    attempt = Path(attempt)
    ct = json.loads((attempt / "cell-contract.json").read_text())
    term = json.loads((attempt / "cell-terminal.json").read_text())
    plan = json.loads((attempt / "opportunity-plan.json").read_text())
    fr = attempt / "fault-receipt.json"
    f = json.loads(fr.read_text()) if fr.exists() else None
    rk = ct["runKey"]
    posture = rk["posture"]
    cell = common.new_cell(SUT, population, attempt, posture, rk["regime"], rk["block"],
                           term.get("candidateCellValid") is True, f["targetService"] if f else None,
                           f.get("faultKind") if f else None)
    bw, bm = S.epoch(plan["barrierAt"]), float(plan["barrierMonotonic"])
    cell["base"] = {"wall": bw, "mono": bm}
    cell["t0"] = {"wall": bw, "mono": None}
    cell["duration"] = float(plan["durationSeconds"])
    if f is not None:
        a, b = float(f["appliedMonotonic"]), float(f["revertingMonotonic"])
        cell["fault"] = {"wall": (L._wall(plan, a), L._wall(plan, b)), "mono": (a, b)}
    ev = cell["events"]
    stats = cell["stats"]
    # ---- logs
    p = attempt / "application.log"
    cell["channels"]["log"] = {"present": p.exists(), "collectors": ["compose-logs"], "resolution": "per-record",
                               "file": "application.log"}
    known = set()
    if p.exists():
        streams = defaultdict(list)
        cli = 0
        for raw in p.read_text(errors="replace").splitlines():
            if " | " not in raw:
                cli += 1
                continue
            prefix, payload = raw.split(" | ", 1)
            streams[prefix.strip().rsplit("-", 1)[0]].append(payload)
        stats["composeCliLines"] = cli
        untimed = 0
        for svc, lines in sorted(streams.items()):
            records, st = S.parse_stream(lines, S.HOTEL_LAYOUTS)
            for k, v in st.items():
                stats["log:" + k] = stats.get("log:" + k, 0) + v
            for r in records:
                if r["framework"] == "jvm-throwable":
                    continue                     # no template (symptoms.log_symbols)
                tid = S.template_id(r["framework"], r["level"], r["key"], r["msg"])
                if GOAWAY_TEXT in r["msg"]:
                    known.add("log:%s:%s" % (svc, tid))
                lv = level_class(r["framework"], r["level"])
                m = stream_meta(SUT, posture, "log", svc, "application", "compose-logs", "wall", "per-record", lv)
                if r["t"] is None:
                    untimed += 1
                ev.append(Event("log", svc, tid, r["t"], 1.0, m))
        stats["log:untimedRecords"] = untimed
    stats["knownPeriodic"] = sorted(known)
    # ---- docker stats CPU
    p = attempt / "cpu.json"
    cell["channels"]["metric:docker-stats"] = {"present": p.exists(), "collectors": ["docker-stats"], "file": "cpu.json"}
    if p.exists():
        cpu = json.loads(p.read_text())
        res = cpu.get("intervalSeconds")
        cell["channels"]["metric:docker-stats"]["resolution"] = res
        for smp in cpu["samples"]:
            for c in smp["containers"]:
                m = stream_meta(SUT, posture, "metric", c["service"], "runtime", "docker-stats", "wall", res)
                ev.append(Event("metric", c["service"], "cpu", smp["capturedAtEpoch"], c["cpuPercent"], m))
    # ---- cgroup sampler
    p = attempt / "system-samples.json"
    cell["channels"]["metric:cgroup-sampler"] = {"present": p.exists(), "collectors": ["cgroup-sampler"],
                                                 "file": "system-samples.json"}
    if p.exists():
        samples = json.loads(p.read_text())
        res = samples.get("intervalSeconds")
        cell["channels"]["metric:cgroup-sampler"]["resolution"] = res
        for s in samples["samples"][0]["services"]:
            series = {"sys_cpu": L._rates(samples, s, "cpuUsageUsec", 1e-6),
                      "sys_memory": [(S.epoch(r["at"]), r["services"][s]["memoryCurrent"]) for r in samples["samples"]]}
            io = [(S.epoch(r["at"]), r["services"][s]["rbytes"] + r["services"][s]["wbytes"]) for r in samples["samples"]]
            series["sys_io"] = [(t1, (v1 - v0) / max(t1 - t0_, 1e-9)) for (t0_, v0), (t1, v1) in zip(io, io[1:])]
            for r in ("cpu", "memory", "io"):
                series["sys_psi_" + r] = L._rates(samples, s, "psi%sSomeTotalUsec" % r.capitalize())
            m = stream_meta(SUT, posture, "metric", s, "runtime", "cgroup-sampler", "wall", res)
            for tok, xs in series.items():
                for t, x in xs:
                    ev.append(Event("metric", s, tok, t, x, m))
    # ---- spans
    p = attempt / "traces-normalized.json"
    cell["channels"]["span"] = {"present": p.exists(), "collectors": ["jaeger"], "resolution": "per-record",
                                "file": "traces-normalized.json"}
    if p.exists():
        n = 0
        for e in json.loads(p.read_text())["events"]:
            tok = S.op_token(e["operation"])
            m = stream_meta(SUT, posture, "span", e["service"], "application", "jaeger", "wall", "per-record")
            t, d = e["startTimeUs"] / 1e6, e["durationUs"] / 1e6
            ev.append(Event("span", e["service"], tok, t, d, m))
            if S.span_error(e):
                ev.append(Event("span", e["service"], tok + ":error", t, d, m))
            n += 1
        stats["spans"] = n
    # ---- ledger
    p = attempt / "opportunity-ledger.jsonl"
    cell["channels"]["ledger"] = {"present": p.exists(), "collectors": ["workload-ledger"], "resolution": "per-record",
                                  "file": "opportunity-ledger.jsonl"}
    if p.exists():
        route = plan.get("workloadId", "?")
        m = stream_meta(SUT, posture, "ledger", ENTRY, "harness", "workload-ledger", "mono", "per-record")
        for line in p.open():
            row = json.loads(line)
            start = row["actualStartMonotonic"]
            ok = row["outcome"] == "completed" and row.get("statusCode") == 200
            ev.append(Event("ledger", ENTRY, route + (":ok" if ok else ":failed"), start,
                            (row["actualEndMonotonic"] - start) * 1000.0, m))
    return cell


def pseudo_offsets(cells):
    """The oracle's no-fault window placement (lmt_detect.score): median offsets of the VALID fault cells' windows from
    the barrier, per clock (wall for sensors; mono for the ledger, as visibility.hotel_population)."""
    import statistics
    out = {}
    for clock in ("wall", "mono"):
        offs = [(c["fault"][clock][0] - c["base"][clock], c["fault"][clock][1] - c["base"][clock])
                for c in cells if c["valid"] and c["fault"] and c["target"]]
        out[clock] = (statistics.median(o[0] for o in offs), statistics.median(o[1] for o in offs)) if offs else (45.0, 60.0)
    return out


def family(channel, collector, posture):
    """MAP_TABLE family of a sensor in this SUT (L logs, M docker CPU, S cgroup sampler, Tsel/T spans)."""
    if channel == "log":
        return "L"
    if channel == "metric":
        return "M" if collector == "docker-stats" else "S"
    if channel == "span":
        return "Tsel" if posture == "selected" else "T"
    return None
