#!/usr/bin/env python3
"""LMT+S pilot: which signal family catches each fault class (frozen before the run; see DECLARATION.md).

Bags reuse the symptom alphabet of research/s4-conjunction/symptoms.py (imported, unchanged) with three
pilot rules:
- windows: a fault cell's window is the detection window inside the fault (fault-receipt appliedMonotonic ..
  revertingMonotonic, mapped to wall time through the plan's barrier); a no-fault cell gets a pseudo window at
  the median offsets of the generation's fault windows (same length, same place in the cell);
- families: L = application log templates (logs/metrics/full postures), M = docker-stats CPU (metrics/full),
  T = spans (full), S = system sampler (every posture: cgroup CPU rate, memory, io rate, PSI cpu/memory/io
  rates), each scored only over the postures that collect it;
- gates: G2 (sensors of the faulted service excluded) and G3 (a sensor whose symbol fires in more than
  5 % of the no-fault windows of its own posture set is inadmissible) on EVERY family, spans included.
A sensor is (family, service, name): L name = template id, M name = cpu, S name = resource, T name = operation.
An episode is caught by a family when at least one admissible, non-target sensor of it fires.

    /usr/bin/python3 -B research/lmt-pilot/lmt_detect.py <campaign x/ dir> [--out DIR]
    /usr/bin/python3 -B research/lmt-pilot/lmt_detect.py --self-check
"""
import importlib.util
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("s4sym", HERE.parent / "s4-conjunction" / "symptoms.py")
sym = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sym)

FAMILY_POSTURES = {"L": ("logs", "metrics", "full"), "M": ("metrics", "full"), "T": ("full",),
                   "S": ("none", "logs", "metrics", "full")}
SYS_FLOORS = {"sys_cpu": 0.05, "sys_io": 65536.0, "sys_psi_cpu": 1000.0, "sys_psi_memory": 1000.0,
              "sys_psi_io": 1000.0}      # cores, bytes/s, stall usec/s; memory uses the 2 % relative floor
TAU = 0.05


def _wall(plan, mono):
    return sym.epoch(plan["barrierAt"]) + (float(mono) - float(plan["barrierMonotonic"]))


def _rates(samples, service, key, scale=1.0):
    rows = samples["samples"]
    out = []
    for a, b in zip(rows, rows[1:]):
        dt = b["monotonic"] - a["monotonic"]
        va, vb = a["services"][service].get(key), b["services"][service].get(key)
        if dt > 0 and va is not None and vb is not None:
            out.append((sym.epoch(b["at"]), (vb - va) / dt * scale))
    return out


def load_cell(attempt: Path):
    ct = json.loads((attempt / "cell-contract.json").read_text())
    term = json.loads((attempt / "cell-terminal.json").read_text())
    plan = json.loads((attempt / "opportunity-plan.json").read_text())
    fr = attempt / "fault-receipt.json"
    f = json.loads(fr.read_text()) if fr.exists() else None
    rk = ct["runKey"]
    t0 = sym.epoch(plan["barrierAt"])
    window = None
    if f is not None:
        window = (_wall(plan, f["appliedMonotonic"]), _wall(plan, f["revertingMonotonic"]))
    cell = sym.new_cell("H-L", "hotel", str(attempt), attempt.parts[-5], rk["block"], rk["posture"], rk["regime"],
                        term.get("candidateCellValid") is True, f["targetService"] if f else None, t0, [])
    cell["windowWall"] = window
    posture = rk["posture"]
    if posture in FAMILY_POSTURES["L"]:
        streams = defaultdict(list)
        for raw in (attempt / "application.log").read_text(errors="replace").splitlines():
            if " | " in raw:
                prefix, payload = raw.split(" | ", 1)
                streams[prefix.strip().rsplit("-", 1)[0]].append(payload)
        for s, lines in streams.items():
            cell["logs"][s], cell["stats"][s] = sym.parse_stream(lines, sym.HOTEL_LAYOUTS)
    if posture in FAMILY_POSTURES["M"]:
        cpu = json.loads((attempt / "cpu.json").read_text())
        for smp in cpu["samples"]:
            for c in smp["containers"]:
                cell["metrics"].setdefault(c["service"], {}).setdefault("cpu", []).append(
                    (smp["capturedAtEpoch"], c["cpuPercent"]))
    samples = json.loads((attempt / "system-samples.json").read_text())
    for s in samples["samples"][0]["services"]:
        m = cell["metrics"].setdefault(s, {})
        m["sys_cpu"] = _rates(samples, s, "cpuUsageUsec", 1e-6)
        m["sys_memory"] = [(sym.epoch(r["at"]), r["services"][s]["memoryCurrent"]) for r in samples["samples"]]
        io = [(sym.epoch(r["at"]), r["services"][s]["rbytes"] + r["services"][s]["wbytes"]) for r in samples["samples"]]
        m["sys_io"] = [(t1, (v1 - v0) / max(t1 - t0_, 1e-9)) for (t0_, v0), (t1, v1) in zip(io, io[1:])]
        for r in ("cpu", "memory", "io"):
            m["sys_psi_" + r] = _rates(samples, s, "psi%sSomeTotalUsec" % r.capitalize())
    if posture in FAMILY_POSTURES["T"]:
        for e in json.loads((attempt / "traces-normalized.json").read_text())["events"]:
            cell["spans"].setdefault(e["service"], []).append(
                (e["startTimeUs"] / 1e6, e["operation"], e["durationUs"] / 1e6, bool(sym.span_error(e))))
    return cell


def family(symbol):
    if symbol.startswith("log:template:"):
        return "L", symbol.split(":", 2)[2]
    if symbol.startswith("metric:sys_"):
        return "S", symbol.split(":")[1]
    if symbol.startswith("metric:cpu:"):
        return "M", "cpu"
    if symbol.startswith("span:") and not symbol.endswith(":present"):
        return "T", symbol.rsplit(":", 1)[0].split(":", 1)[1]
    return None


def bag(cell):
    """One row per service for the cell's single window (fault or pseudo)."""
    w0, w1 = cell["windowWall"]
    rows = []
    for s in sorted(set(cell["logs"]) | set(cell["metrics"]) | set(cell["spans"])):
        c = Counter()
        if s in cell["logs"]:
            c.update(sym.log_symbols(cell["logs"][s], (w0, w1)))
        for resource, series in cell["metrics"].get(s, {}).items():
            floor = SYS_FLOORS.get(resource)
            saved = sym.FLOOR.get(resource)
            if floor is not None:
                sym.FLOOR[resource] = floor
            c.update(sym.metric_symbols(series, resource, cell["t0"], (w0, w1)))
            if floor is not None:
                if saved is None:
                    del sym.FLOOR[resource]
                else:
                    sym.FLOOR[resource] = saved
        if s in cell["spans"]:
            c.update(sym.span_symbols(cell["spans"][s], cell["t0"], (w0, w1)))
        sensors = sorted({(f[0], s, f[1]) for f in map(family, c) if f})
        rows.append({"service": s, "sensors": sensors})
    return rows


def score(cells):
    fault = [c for c in cells if c["valid"] and c["windowWall"] and c["target"]]
    offsets = [(c["windowWall"][0] - c["t0"], c["windowWall"][1] - c["t0"]) for c in fault]
    a = statistics.median(o[0] for o in offsets) if offsets else 45.0
    b = statistics.median(o[1] for o in offsets) if offsets else 60.0
    for c in cells:
        if c["windowWall"] is None:
            c["windowWall"] = (c["t0"] + a, c["t0"] + b)
    fired = {id(c): {tuple(x) for r in bag(c) for x in r["sensors"]} for c in cells if c["valid"]}
    nofault = [c for c in cells if c["valid"] and c["target"] is None]
    out = {"pseudoWindowOffsets": [a, b], "classes": {}, "falseAlarms": {}}
    for fam, postures in FAMILY_POSTURES.items():
        nf = [c for c in nofault if c["posture"] in postures]
        fa_counts = Counter(x for c in nf for x in fired[id(c)] if x[0] == fam)
        inadmissible = {x for x, n in fa_counts.items() if nf and n > TAU * len(nf)}
        out["falseAlarms"][fam] = {"noFaultWindows": len(nf), "inadmissible": sorted("%s:%s:%s" % x for x in inadmissible),
                                   "anyAdmissibleFiring": sum(1 for c in nf if any(
                                       x[0] == fam and x not in inadmissible for x in fired[id(c)]))}
        for regime in sorted({c["regime"] for c in fault}):
            eps = [c for c in fault if c["regime"] == regime and c["posture"] in postures]
            caught, sensors = 0, Counter()
            for c in eps:
                hit = {x for x in fired[id(c)] if x[0] == fam and x[1] != c["target"] and x not in inadmissible}
                caught += bool(hit)
                sensors.update(hit)
            out["classes"].setdefault(regime, {})[fam] = {
                "n": len(eps), "caught": caught,
                "topSensors": [["%s:%s:%s" % x, k] for x, k in sensors.most_common(5)]}
    return out


def self_check():
    t0 = 1_790_000_000.0
    def c(regime, posture, target, sensors_by_service, valid=True):
        cell = {"valid": valid, "regime": regime, "posture": posture, "target": target, "t0": t0,
                "windowWall": (t0 + 45.2, t0 + 60.1) if target else None}
        cell["_fixture"] = sensors_by_service
        return cell
    global bag
    real = bag
    bag = lambda cell: [{"service": s, "sensors": v} for s, v in cell["_fixture"].items()]
    try:
        cells = [c("no-fault-cost", "logs", None, {"frontend": []}) for _ in range(4)] + \
                [c("no-fault-cost", "logs", None, {"frontend": [("L", "frontend", "noisy")]})] * 0 + \
                [c("x-effect", "logs", "rate", {"frontend": [("L", "frontend", "t1")], "rate": [("L", "rate", "own")]}),
                 c("x-effect", "logs", "rate", {"rate": [("L", "rate", "own")]})]
        s = score(cells)
        assert s["classes"]["x-effect"]["L"] == {"n": 2, "caught": 1, "topSensors": [["L:frontend:t1", 1]]}, s
        # planted defect: a sensor firing in every no-fault window must be inadmissible
        cells[0]["_fixture"] = cells[1]["_fixture"] = {"frontend": [("L", "frontend", "t1")]}
        s = score(cells)
        assert s["classes"]["x-effect"]["L"]["caught"] == 0, s
        # planted defect: the metric family must not score a logs-only posture
        assert s["classes"]["x-effect"]["M"]["n"] == 0, s
    finally:
        bag = real
    print("self-check: pass")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-check"]:
        self_check(); sys.exit(0)
    x = Path(sys.argv[1])
    cells = [load_cell(a) for a in sorted((x / "runs").glob("**/attempt-01"))]
    result = score(cells)
    result["cells"] = len(cells)
    result["validCells"] = sum(1 for c in cells if c["valid"])
    print(json.dumps(result, indent=2))
