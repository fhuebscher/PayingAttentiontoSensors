#!/usr/bin/env python3
"""Episode detection per signal family, as frozen in DETECTION_DEFINITIONS.md (99e6c0e).

    python3 research/sprint-draft2/detection.py hotel <run-dir>...   # Hotel #6 runs (each has runs/cost, runs/effect)
    python3 research/sprint-draft2/detection.py teastore <campaign-dir>
    python3 research/sprint-draft2/detection.py --self-check

Parsers follow the logging frameworks' own layouts (zerolog JSON + ConsoleWriter; log4j pattern
"[thread] LEVEL logger - msg"), never patterns over message text. The one regex strips ECMA-48 SGR
colour codes, which ConsoleWriter adds.
"""
import datetime as dt
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

SGR = re.compile(r"\x1b\[[0-9;]*m")
ZL_CONSOLE = {"TRC": "trace", "DBG": "debug", "INF": "info", "WRN": "warn", "ERR": "error", "FTL": "fatal", "PNC": "panic"}
ALERT = {"warn", "error", "fatal", "panic", "WARN", "ERROR", "FATAL"}
L4J = {"TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"}
K, FLOOR, PSEUDO_AT, PSEUDO_LEN = 4.0, 1.0, 45.0, 15.0
A1 = "--a1" in sys.argv  # amendment A1 (post hoc): Go stdlib log layout + gRPC severity prefix
GRPC_SEV = {"INFO:": "info", "WARNING:": "warn", "ERROR:": "error", "FATAL:": "fatal"}


def epoch(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def parse_zerolog(raw):
    """-> (service, level, template_key, epoch) or (service|None, None, None, None) if unparsed."""
    if " | " not in raw:
        return None, None, None, None
    prefix, payload = raw.split(" | ", 1)
    service = prefix.strip().rsplit("-", 1)[0]
    payload = SGR.sub("", payload).strip()
    try:
        if payload.startswith("{"):
            o = json.loads(payload)
            return service, o["level"], o.get("caller") or o.get("message"), epoch(o["time"])
        t = payload.split(None, 3)
        if len(t) >= 3 and t[1] in ZL_CONSOLE:
            caller = None if t[2] == ">" else t[2]
            if caller is None or (len(t) == 4 and t[3].startswith(">")) or t[3:] == []:
                return service, ZL_CONSOLE[t[1]], caller, epoch(t[0])
        if A1 and payload.startswith("OBSPLACEMENT_EMISSION "):
            return service, "harness", None, None
        if A1 and len(t) >= 2:  # Go log.LstdFlags: "2006/01/02 15:04:05 msg", UTC in these containers
            ts = dt.datetime.strptime(t[0] + " " + t[1], "%Y/%m/%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
            sev = GRPC_SEV.get(t[2] if len(t) > 2 else "", "info")
            return service, sev, "go-log", ts.timestamp()
    except (ValueError, KeyError):
        pass
    return service, None, None, None


def parse_log4j(line):
    """-> (level, logger) or None. Harness witness lines return 'harness'."""
    if not line.startswith("[") or "] " not in line:
        return None
    t = line.split("] ", 1)[1].split(None, 2)
    if len(t) == 3 and t[0] in L4J and t[2].startswith("- "):
        return "harness" if t[2][2:].startswith("OBSERVABILITY_") else (t[0], t[1])
    return None


def robust_events(pre, inside, k=K, floor=FLOOR):
    """Samples in the window that leave the pre-window baseline by >= k robust sigma and >= floor pp."""
    if len(pre) < 3:
        return None
    m = statistics.median(v for _, v in pre)
    s = 1.4826 * statistics.median(abs(v - m) for _, v in pre)
    return [t for t, v in inside if abs(v - m) >= max(k * s, floor)]


def span_error(e):
    tags = e.get("tags") or {}
    code = tags.get("http.status_code")
    return tags.get("error") in (True, "true") or (isinstance(code, int) and code >= 500)


# ---------------------------------------------------------------- Hotel

def hotel_cell(d: Path):
    ct = json.loads((d / "cell-contract.json").read_text())
    term = json.loads((d / "cell-terminal.json").read_text())
    cpu = json.loads((d / "cpu.json").read_text())["samples"]
    fr = d / "fault-receipt.json"
    f = json.loads(fr.read_text()) if fr.exists() else None
    if f:
        w0, w1 = epoch(f["startedAt"]), epoch(f["endedAt"])
    else:
        w0 = cpu[0]["capturedAtEpoch"] + PSEUDO_AT
        w1 = w0 + PSEUDO_LEN
    lines, unparsed = [], 0
    for raw in (d / "application.log").read_text(errors="replace").splitlines():
        svc, lvl, key, t = parse_zerolog(raw)
        if lvl == "harness":
            continue
        if lvl is None:
            unparsed += 1
            continue
        lines.append((svc, lvl, key, t))
    series = defaultdict(list)
    for smp in cpu:
        for c in smp["containers"]:
            series[c["service"]].append((smp["capturedAtEpoch"], c["cpuPercent"]))
    tr = json.loads((d / "traces-normalized.json").read_text())["events"]
    return {"valid": term.get("candidateCellValid") is True, "posture": ct["runKey"]["posture"],
            "block": ct["runKey"]["block"], "regime": ct["runKey"]["regime"],
            "target": f["targetService"] if f else None, "w": (w0, w1), "lines": lines,
            "unparsed": unparsed, "series": series,
            "spans": [(e["startTimeUs"] / 1e6, e["service"]) for e in tr if span_error(e)]}


def in_w(t, w, whole_seconds=False):
    return (int(w[0]) if whole_seconds else w[0]) <= t <= w[1]


def hotel_detect(c, target, known):
    """Per detector: first event epoch in the window, or None. `known` = templates seen in the calibration cells."""
    w, out = c["w"], {}
    win = [x for x in c["lines"] if in_w(x[3], w, True)]
    out["log-level"] = min((x[3] for x in win if x[1] in ALERT), default=None)
    out["log-novel"] = min((x[3] for x in win if (x[0], x[1], x[2]) not in known), default=None)
    for part, svcs in (("metric-target", [target]), ("metric-other", [s for s in c["series"] if s != target])):
        ts = []
        for s in svcs:
            ev = robust_events([p for p in c["series"].get(s, []) if p[0] < w[0]],
                               [p for p in c["series"].get(s, []) if in_w(p[0], w)])
            ts += ev or []
        out[part] = min(ts, default=None)
    out["trace-error"] = min((t for t, _ in c["spans"] if in_w(t, w)), default=None)
    out["log"] = min((v for k, v in out.items() if k.startswith("log-") and v), default=None)
    out["metric"] = min((out[k] for k in ("metric-target", "metric-other") if out[k]), default=None)
    return out


DETECTORS = ("log-level", "log-novel", "log", "metric-target", "metric-other", "metric", "trace-error")


def fmt_lat(xs):
    return "—" if not xs else f"{statistics.median(xs):.1f} [{min(xs):.1f}, {max(xs):.1f}] s"


def hotel(run_dirs):
    rows = defaultdict(list)  # (regime, posture, detector) -> latencies of detected
    n = Counter()             # (regime, posture) -> episodes
    fa = Counter()            # (target, posture, detector) -> false alarms
    nf = Counter()            # posture -> no-fault cells
    combos = defaultdict(Counter)
    unparsed = Counter()
    for rd in map(Path, run_dirs):
        root = next(rd.glob("**/runs"))
        cost = [hotel_cell(a) for a in sorted(root.glob("cost/*/*/attempt-*"))]
        eff = [hotel_cell(a) for a in sorted(root.glob("effect/*/*/*/attempt-*"))]
        cost, eff = [c for c in cost if c["valid"]], [c for c in eff if c["valid"]]
        tmpl = [{(x[0], x[1], x[2]) for x in c["lines"]} for c in cost]
        known = set().union(*tmpl)
        targets = sorted({c["target"] for c in eff})
        for c in cost + eff:
            unparsed[c["regime"]] += c["unparsed"]
        for c in eff:
            r = c["regime"]
            n[r, c["posture"]] += 1
            det = hotel_detect(c, c["target"], known)
            for k in DETECTORS:
                if det[k] is not None:
                    rows[r, c["posture"], k].append(det[k] - c["w"][0])
            combos[r][tuple(f for f in ("log", "metric-other", "metric-target", "trace-error") if det[f])] += 1
        for i, c in enumerate(cost):
            nf[c["posture"]] += 1
            loo = set().union(*(t for j, t in enumerate(tmpl) if j != i))  # leave-one-out, else novelty is 0 by construction
            for tgt in targets:
                det = hotel_detect(c, tgt, loo)
                for k in DETECTORS:
                    fa[tgt, c["posture"], k] += det[k] is not None
    regimes = sorted({r for r, _ in n})
    postures = sorted({p for _, p in n})
    print(f"amendment A1 (post hoc): {A1}")
    print(f"Hotel: runs {len(run_dirs)}; episodes {dict(sorted(n.items()))}; no-fault cells {dict(nf)}")
    print(f"unparsed lines (kept, not windowed): {dict(unparsed)}")
    for r in regimes:
        tgt = r.split("-")[0]
        print(f"\n{r} (target {tgt})\n  {'detector':14} " + "  ".join(f"{p:>34}" for p in postures))
        for k in DETECTORS:
            cells = [f"{len(rows[r, p, k])}/{n[r, p]} FA {fa[tgt, p, k]}/{nf[p]} lat {fmt_lat(rows[r, p, k])}" for p in postures]
            print(f"  {k:14} " + "  ".join(f"{s:>34}" for s in cells))
        print("  overlap (log, metric-other, metric-target, trace-error):",
              ", ".join(f"{'+'.join(k) or 'none'} {v}" for k, v in combos[r].most_common()))


# ---------------------------------------------------------------- sweep (SWEEP_PLAN.md, 82b9cd4)

GRID = [(k, f) for k in (3.0, 4.0, 5.0, 6.0) for f in (0.5, 1.0, 2.0)]
LEVELS = {"warn+": ALERT, "error+": ALERT - {"warn", "WARN"}}


def sweep_cell(c):
    w = c["w"]
    win = [x for x in c["lines"] if in_w(x[3], w, True)]
    metric = {}
    for s, ser in c["series"].items():
        pre, ins = [p for p in ser if p[0] < w[0]], [p for p in ser if in_w(p[0], w)]
        for k, f in GRID:
            metric[k, f, s] = bool(robust_events(pre, ins, k, f))
    return {"metric": metric, "services": sorted(c["series"]),
            "log": {lv: {x[0] for x in win if x[1] in S} for lv, S in LEVELS.items()},
            "trace": {sv for t, sv in c["spans"] if in_w(t, w)}}


def hotel_sweep(run_dirs):
    ep, nf = [], []  # (run, block, regime, posture, target, sweep_cell)
    for rd in map(Path, run_dirs):
        root = next(rd.glob("**/runs"))
        for pat, sink in (("effect/*/*/*/attempt-*", ep), ("cost/*/*/attempt-*", nf)):
            for a in sorted(root.glob(pat)):
                c = hotel_cell(a)
                if c["valid"]:
                    sink.append((rd.name[-8:], c["block"], c["regime"], c["posture"], c["target"], sweep_cell(c)))
    regimes = sorted({e[2] for e in ep})
    svcs = ep[0][5]["services"]
    print(f"sweep: episodes {len(ep)}, no-fault {len(nf)}, services {svcs}")
    for r in regimes:
        E = [e for e in ep if e[2] == r]
        tgt = E[0][4]
        other = [s for s in svcs if s != tgt]
        print(f"\n== {r} (target {tgt}), episodes {len(E)}, no-fault {len(nf)}")
        print("  metric grid (k, floor pp): target det FA | other-union det FA")
        for k, f in GRID:
            td = sum(e[5]["metric"][k, f, tgt] for e in E); tf = sum(c[5]["metric"][k, f, tgt] for c in nf)
            od = sum(any(e[5]["metric"][k, f, s] for s in other) for e in E)
            of = sum(any(c[5]["metric"][k, f, s] for s in other) for c in nf)
            print(f"    k={k:g} floor={f:<3g}  target {td}/{len(E)} FA {tf}/{len(nf)} | other {od}/{len(E)} FA {of}/{len(nf)}")
        print("  metric per service, det/FA over the 12 configs in grid order:")
        for s in svcs:
            cells = " ".join(f"{sum(e[5]['metric'][k, f, s] for e in E)}/{sum(c[5]['metric'][k, f, s] for c in nf)}" for k, f in GRID)
            print(f"    {s:15}{'*' if s == tgt else ' '} {cells}")
        for lv in LEVELS:
            d = sum(bool(e[5]["log"][lv]) for e in E); fa = sum(bool(c[5]["log"][lv]) for c in nf)
            by = Counter(s for e in E for s in e[5]["log"][lv])
            print(f"  log {lv:7} {d}/{len(E)} FA {fa}/{len(nf)}  emitting services (episodes): {dict(by)}")
        full = [e for e in E if e[3] == "full"]
        print(f"  trace (full) error spans by service (episodes of {len(full)}): {dict(Counter(s for e in full for s in e[5]['trace']))}")
        groups = defaultdict(dict)
        for e in E:
            groups[e[0], e[1]][e[3]] = e[5]
        dets = {"log warn+": lambda x: bool(x["log"]["warn+"]), "log error+": lambda x: bool(x["log"]["error+"])}
        for k, f in GRID:
            dets[f"metric-target k{k:g} f{f:g}"] = lambda x, k=k, f=f: x["metric"][k, f, tgt]
            dets[f"metric-other k{k:g} f{f:g}"] = lambda x, k=k, f=f: any(x["metric"][k, f, s] for s in other)
        full3 = [g for g in groups.values() if len(g) == 3]
        print(f"  posture agreement per (run, block), all 3 postures agree, of {len(full3)} groups:")
        for name, fn in dets.items():
            print(f"    {name:26} {sum(len({fn(x) for x in g.values()}) == 1 for g in full3)}/{len(full3)}")


def teastore_levels(camp):
    for lv, S in LEVELS.items():
        S4 = {x.upper() for x in S}
        res = Counter(); n = Counter()
        for d in sorted(Path(camp).glob("runs/*/*")):
            if d.name.endswith(".blocked-evidence") or not (d / "candidate-validation.json").exists():
                continue
            v = json.loads((d / "candidate-validation.json").read_text())
            if v["cellStatus"] != "valid":
                continue
            r = v["runKey"]["regime"]; n[r] += 1
            hit = any(isinstance(x, tuple) and x[0] in S4 for name in ("auth.log", "persistence.log")
                      for x in map(parse_log4j, (d / name).read_text(errors="replace").splitlines()))
            res[r] += hit
        print(f"TeaStore log {lv}: " + ", ".join(f"{r} {res[r]}/{n[r]}" for r in sorted(n)))


# ---------------------------------------------------------------- TeaStore (cell-level)

def teastore_cell(d: Path):
    if not (d / "candidate-validation.json").exists():  # blocked cell: no validation, not in the population
        return None
    v = json.loads((d / "candidate-validation.json").read_text())
    tmpl, alert, unparsed = set(), False, 0
    for name in ("auth.log", "persistence.log"):
        p = d / name
        if not p.exists():
            return None
        for line in p.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            r = parse_log4j(line)
            if r == "harness":
                continue
            if r is None:
                unparsed += 1
                r = ("UNPARSED", line.split(None, 1)[0])  # ponytail: first token as the template of an unlayouted line; a real template miner (Drain) if this is noisy
            tmpl.add((name,) + r)
            alert |= r[0] in ALERT
    return {"valid": v["cellStatus"] == "valid", "regime": v["runKey"]["regime"],
            "posture": v["runKey"]["posture"], "tmpl": tmpl, "alert": alert, "unparsed": unparsed}


def teastore(camp):
    cells = [c for d in sorted(Path(camp).glob("runs/*/*"))
             if d.is_dir() and not d.name.endswith(".blocked-evidence") and (c := teastore_cell(d)) and c["valid"]]
    base = [c for c in cells if c["regime"] == "no-fault-cost"]
    known = set().union(*(c["tmpl"] for c in base))
    print(f"TeaStore (cell-level, no window: native lines carry no timestamp); valid cells {Counter(c['regime'] for c in cells)}")
    print(f"unparsed lines: {sum(c['unparsed'] for c in cells)}")
    fa_lvl = sum(c["alert"] for c in base)
    fa_nov = sum(bool(c["tmpl"] - set().union(*(o["tmpl"] for o in base if o is not c))) for c in base)
    for r in sorted({c["regime"] for c in cells} - {"no-fault-cost"}):
        for p in sorted({c["posture"] for c in cells}):
            cs = [c for c in cells if c["regime"] == r and c["posture"] == p]
            lvl = sum(c["alert"] for c in cs)
            nov = sum(bool(c["tmpl"] - known) for c in cs)
            print(f"  {r:26} {p:28} level {lvl}/{len(cs)}  novel {nov}/{len(cs)}")
        novel = Counter(t for c in cells if c["regime"] == r for t in c["tmpl"] - known)
        print(f"  {r} novel templates: {novel.most_common(8)}")
    print(f"  false alarms on no-fault (leave-one-out): level {fa_lvl}/{len(base)}  novel {fa_nov}/{len(base)}")


def self_check():
    s, lvl, key, t = parse_zerolog('frontend-1        | \x1b[90m2026-09-24T03:30:42Z\x1b[0m \x1b[31mERR\x1b[0m '
                                   '\x1b[1mservices/frontend/server.go:271\x1b[0m\x1b[36m >\x1b[0m SearchHandler failed')
    assert (s, lvl, key, t) == ("frontend", "error", "services/frontend/server.go:271", epoch("2026-09-24T03:30:42Z"))
    assert parse_zerolog('user-1  | {"level":"info","time":"2026-09-24T03:29:07Z","message":"TLS disabled."}')[1:3] == ("info", "TLS disabled.")
    assert parse_zerolog('time="x" level=warning msg="compose"')[1] is None
    assert parse_zerolog("geo-1 | plain text from a non-zerolog writer")[1] is None
    assert parse_log4j("[http-nio-8080-exec-3] INFO a.b.C - OBSERVABILITY_APP_WITNESS {}") == "harness"
    assert parse_log4j("[main] ERROR a.b.C - boom") == ("ERROR", "a.b.C")
    assert parse_log4j("WriterController: x") is None
    pre = [(i, 3.0 + 0.1 * (i % 3)) for i in range(15)]
    assert robust_events(pre, [(20, 0.0), (21, 3.1)]) == [20]
    assert robust_events(pre[:2], [(20, 0.0)]) is None
    global A1
    A1 = True
    r = parse_zerolog('search-1 | 2026/09/24 01:22:07 ERROR: [Consul resolver] bad state')
    assert r == ("search", "error", "go-log", epoch("2026-09-24T01:22:07Z")), r
    assert parse_zerolog('geo-1 | OBSPLACEMENT_EMISSION {"a":1}')[1] == "harness"
    assert parse_zerolog("geo-1 | plain text from a non-zerolog writer")[1] is None
    print("self-check ok")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x != "--a1"]
    {"--self-check": lambda: self_check(), "hotel": lambda: hotel(a[1:]), "teastore": lambda: teastore(a[1]),
     "hotel-sweep": lambda: hotel_sweep(a[1:]), "teastore-levels": lambda: teastore_levels(a[1])}[a[0]]()
