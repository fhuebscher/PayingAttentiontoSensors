#!/usr/bin/env python3
"""Symptom alphabet v0: typed parsers -> per (generation, cell, service, window) symbol bags.

Implements research/s4-conjunction/AMENDMENT_1_SYMPTOM_ALPHABET_DRAFT.md. It emits symbols; it computes
no relevance, detection or objective value. Vocabulary sizes and parse coverage are its only summary.

    /usr/bin/python3 research/s4-conjunction/symptoms.py --self-check
    /usr/bin/python3 research/s4-conjunction/symptoms.py --out tmp/s4-symptoms \\
        hotel    H-B   <run-dir>...            # Hotel #6 runs (each has runs/cost, runs/effect)
        hotel    H-Bp  <run-dir>               # run 1, reported beside H-B, never pooled
        teastore T-new <campaign-dir>          # tmp/teastore-e3-user-a5-evidence/teastore-candidate-pilot-v3-user
        teastore T-16  <campaign-dir>          # tmp/teastore16-evidence/x/teastore-candidate-pilot-v1
        gold     G-old <by_server/fb14srv6>    # old corpus, read-only, one run at a time

Parsers follow the logging frameworks' published layouts (zerolog JSON + ConsoleWriter, Go `log` with the
gRPC severity prefix, log4j/slf4j-simple, Tomcat JUL OneLineFormatter, MariaDB error log, JVM
Throwable.printStackTrace). Levels come from the layout's level field only. The only regexes are the
ECMA-48 SGR strip and the language-level masks (numbers, hex, UUID, IPv4) of the template step.
Runs under /usr/bin/python3 (3.9) and the uv 3.13 environment; no `X | None` annotations.
"""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALPHABET_VERSION = "v0"


def _load_detection():
    """The sprint's parsers and robust rule, reused, not rewritten."""
    spec = importlib.util.spec_from_file_location("sprint_detection", HERE.parent / "sprint-draft2" / "detection.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DET = _load_detection()
SGR, ZL_CONSOLE, GRPC_SEV, epoch, robust_events, span_error = (
    DET.SGR, DET.ZL_CONSOLE, DET.GRPC_SEV, DET.epoch, DET.robust_events, DET.span_error)

# --------------------------------------------------------------------------- levels (layout field only)

ALERT = ("warn", "error", "fatal")
ZL_LEVEL = {"trace": None, "debug": None, "info": None, "warn": "warn", "error": "error", "fatal": "fatal", "panic": "fatal"}
L4J_LEVEL = {"TRACE": None, "DEBUG": None, "INFO": None, "WARN": "warn", "ERROR": "error", "FATAL": "fatal"}
JUL_LEVEL = {"FINEST": None, "FINER": None, "FINE": None, "CONFIG": None, "INFO": None, "WARNING": "warn", "SEVERE": "error"}
MARIADB_LEVEL = {"Note": None, "Warning": "warn", "Warn": "warn", "ERROR": "error"}   # server log and docker entrypoint
GRPC_LEVEL = {"info": None, "warn": "warn", "error": "error", "fatal": "fatal"}

# Metric rule: the sprint's frozen robust rule (k = 4, floor) on the same cell's pre-window baseline.
K = DET.K
FLOOR = {"cpu": DET.FLOOR}          # percentage points
MEM_REL_FLOOR = 0.02                # memory: 2 % of the baseline median (engineering default, see draft)
MIN_BASELINE = 3
PSEUDO_AT, PSEUDO_LEN = DET.PSEUDO_AT, DET.PSEUDO_LEN
LAT_FLOOR_S = 0.001                 # span latency floor: 1 ms
BURST_FLOOR = 2                     # template count floor above the calibrated median
TAU = 0.05                          # G3 admissibility share (U6), carried into the vocabulary, not a symbol

# --------------------------------------------------------------------------- template masking (language level)

MASKS = [
    (re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"), "<uuid>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"), "<ip>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b|\b[0-9a-fA-F]{8,}\b"), "<hex>"),
    (re.compile(r"(?<![A-Za-z_0-9])[-+]?\d+(?:\.\d+)?"), "<n>"),
    (re.compile(r"\s+"), " "),
]


def mask(msg):
    for rx, rep in MASKS:
        msg = rx.sub(rep, msg)
    return msg.strip()


def template_id(framework, level, key, msg):
    h = hashlib.sha256("|".join([framework, level or "-", key or "-", mask(msg)]).encode()).hexdigest()
    return h[:12]


# --------------------------------------------------------------------------- record-start layouts

FQCN = re.compile(r"^([A-Za-z_$][\w$]*\.)+[A-Z][\w$]*(: |$)")   # Throwable.toString(): class name [": " message]
MARIADB_TS = re.compile(r"^\d{4}-\d\d-\d\d +\d{1,2}:\d\d:\d\d(?:[+-]\d\d:?\d\d)? ")
JUL_TS = re.compile(r"^\d\d-[A-Z][a-z]{2}-\d{4} \d\d:\d\d:\d\d\.\d{3} ")
GO_TS = re.compile(r"^\d{4}/\d\d/\d\d \d\d:\d\d:\d\d ")
HARNESS_PREFIXES = ("OBSPLACEMENT_", "OBSERVABILITY_")


def rec(framework, level, t, key, msg, exc=None):
    return {"framework": framework, "level": level, "t": t, "key": key, "msg": msg, "exc": exc or []}


def parse_zerolog_json(payload):
    if not payload.startswith("{"):
        return None
    try:
        o = json.loads(payload)
        level = o["level"]
        return rec("zerolog-json", ZL_LEVEL.get(level, None), epoch(o["time"]), o.get("caller"), o.get("message", ""))
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def parse_zerolog_console(payload):
    t = payload.split(None, 3)
    if len(t) < 3 or t[1] not in ZL_CONSOLE:
        return None
    try:
        ts = epoch(t[0])
    except ValueError:
        return None
    if t[2] == ">":
        return rec("zerolog-console", ZL_LEVEL[ZL_CONSOLE[t[1]]], ts, None, t[3] if len(t) > 3 else "")
    if len(t) > 3 and t[3].startswith(">"):
        return rec("zerolog-console", ZL_LEVEL[ZL_CONSOLE[t[1]]], ts, t[2], t[3][1:].strip())
    return None


def parse_go_log(payload):
    if not GO_TS.match(payload):
        return None
    ts = dt.datetime.strptime(payload[:19], "%Y/%m/%d %H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp()
    rest = payload[20:]
    first = rest.split(None, 1)
    sev = GRPC_SEV.get(first[0] if first else "")
    if sev:
        rest = first[1] if len(first) > 1 else ""
    return rec("go-log", GRPC_LEVEL[sev or "info"], ts, None, rest)


def parse_log4j(line):
    r = DET.parse_log4j(line)
    if r is None:
        return None
    if r == "harness":
        return "harness"
    level, logger = r
    msg = line.split("] ", 1)[1].split(None, 2)[2][2:]
    return rec("log4j", L4J_LEVEL.get(level), None, logger, msg)


def parse_jul(line):
    if not JUL_TS.match(line):
        return None
    t = line.split(None, 4)
    if len(t) < 4 or t[2] not in JUL_LEVEL or not t[3].startswith("["):
        return None
    ts = dt.datetime.strptime(t[0] + " " + t[1], "%d-%b-%Y %H:%M:%S.%f").replace(tzinfo=dt.timezone.utc).timestamp()
    rest = (t[4] if len(t) > 4 else "").split(None, 1)
    logger = rest[0] if rest else None
    msg = rest[1] if len(rest) > 1 else ""
    return rec("jul", JUL_LEVEL[t[2]], ts, logger, msg)


def parse_mariadb(line):
    """MariaDB error log `<date> <time> <thread-id> [<Level>] <msg>` and the docker-entrypoint variant
    `<date> <time><tz> [<Level>] [Entrypoint]: <msg>` (no thread id)."""
    if not MARIADB_TS.match(line):
        return None
    t = line.split(None, 4)
    if len(t) < 3:
        return None
    if t[2].startswith("[") and t[2].endswith("]") and t[2][1:-1] in MARIADB_LEVEL:
        level, msg = t[2][1:-1], " ".join(t[3:])
    elif len(t) >= 4 and t[3].startswith("[") and t[3].endswith("]") and t[3][1:-1] in MARIADB_LEVEL:
        level, msg = t[3][1:-1], t[4] if len(t) > 4 else ""
    else:
        return None
    stamp = t[0] + " " + t[1]
    fmt = "%Y-%m-%d %H:%M:%S%z" if ("+" in t[1] or "-" in t[1]) else "%Y-%m-%d %H:%M:%S"
    ts = dt.datetime.strptime(stamp, fmt)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return rec("mariadb", MARIADB_LEVEL[level], ts.timestamp(), "mariadb", msg)


def parse_throwable(line):
    """JVM Throwable.printStackTrace() header: `<fqcn>[: message]`, never indented."""
    if line[:1].isspace() or not FQCN.match(line):
        return None
    cls = line.split(":", 1)[0].strip()
    return rec("jvm-throwable", None, None, None, line, [cls.rsplit(".", 1)[-1]])


def continuation_exception(line):
    s = line.strip()
    if s.startswith("Caused by: "):
        m = FQCN.match(s[len("Caused by: "):])
        if m:
            return s[len("Caused by: "):].split(":", 1)[0].strip().rsplit(".", 1)[-1]
    return None


HOTEL_LAYOUTS = (parse_zerolog_json, parse_zerolog_console, parse_go_log)
JVM_LAYOUTS = (parse_log4j, parse_jul, parse_mariadb, parse_throwable)


def parse_stream(lines, layouts, stamp=None):
    """Lines of one container -> (records, stats). Multi-line rule: a line that starts no record is a
    continuation of the previous record (Fluent Bit / Logstash "negate, match after"). `stamp(i)` gives an
    external timestamp for line i (G-old docker receive stamps, DEFINITIONS §7); when given it is the record's time."""
    records, stats, cur = [], Counter(), None
    for i, raw in enumerate(lines):
        line = SGR.sub("", raw.rstrip("\r\n"))
        if not line.strip():
            continue
        stats["lines"] += 1
        payload = line.strip()
        if payload.startswith(HARNESS_PREFIXES):
            stats["harness"] += 1
            continue
        r = None
        for layout in layouts:
            r = layout(line)
            if r is not None:
                break
        if r == "harness":
            stats["harness"] += 1
            continue
        if r is not None:
            if stamp is not None:
                r["t"] = stamp(i)
            records.append(r)
            cur = r
            stats["record:" + r["framework"]] += 1
            continue
        if cur is None:
            stats["unparsed"] += 1
            continue
        cause = continuation_exception(line)
        if cause:
            cur["exc"].append(cause)
        stats["continuation"] += 1
    return records, stats


# --------------------------------------------------------------------------- symbols

def op_token(op):
    return op.replace(":", "%3A").replace(" ", "_")


def in_window(t, w, whole_seconds=False):
    return t is not None and (int(w[0]) if whole_seconds else w[0]) <= t <= w[1]


def log_symbols(records, w, cell_level=False):
    """Records of one service -> Counter of raw log symbols inside w (or all timestamped-or-not at cell level)."""
    c = Counter()
    for r in records:
        if cell_level:
            if r["t"] is not None and not in_window(r["t"], w):
                continue
        elif not in_window(r["t"], w, True):
            continue
        if r["level"] in ALERT:
            c["log:level:" + r["level"]] += 1
        if r["framework"] != "jvm-throwable":
            c["log:template:" + template_id(r["framework"], r["level"], r["key"], r["msg"])] += 1
        for e in r["exc"]:
            c["log:exception:" + e] += 1
    return c


def robust_threshold(pre, floor):
    m = statistics.median(pre)
    s = 1.4826 * statistics.median(abs(v - m) for v in pre)
    return m, max(K * s, floor)


def metric_symbols(series, resource, t0, w):
    """One service's (t, x) series -> Counter of metric symbols. Baseline = samples in [t0, w0)."""
    pre = [x for t, x in series if t0 <= t < w[0]]
    ins = [x for t, x in series if in_window(t, w)]
    c = Counter()
    if len(pre) < MIN_BASELINE:
        c["metric:%s:?" % resource] += 1     # insufficient baseline: unknown, not zero
        return c
    if not ins:
        c["metric:%s:missing" % resource] += 1
        return c
    m, thr = robust_threshold(pre, FLOOR.get(resource, MEM_REL_FLOOR * abs(statistics.median(pre))))
    if any(x - m >= thr for x in ins):
        c["metric:%s:spike_up" % resource] += 1
    if any(m - x >= thr for x in ins):
        c["metric:%s:spike_down" % resource] += 1
    if len(ins) >= MIN_BASELINE:
        mi = statistics.median(ins)
        if mi - m >= thr:
            c["metric:%s:plateau_up" % resource] += 1
        if m - mi >= thr:
            c["metric:%s:plateau_down" % resource] += 1
    return c


def span_symbols(spans, t0, w):
    """One service's spans [(t, op, duration_s, error)] -> Counter of span symbols."""
    c = Counter()
    by_op = defaultdict(list)
    for t, op, d, err in spans:
        by_op[op].append((t, d, err))
    for op, xs in by_op.items():
        tok = op_token(op)
        pre = [d for t, d, _ in xs if t0 <= t < w[0]]
        ins = [(d, err) for t, d, err in xs if in_window(t, w)]
        if ins:
            c["span:%s:present" % tok] += len(ins)
            if any(err for _, err in ins):
                c["span:%s:error" % tok] += sum(1 for _, err in ins if err)
            if len(pre) >= MIN_BASELINE:
                m, thr = robust_threshold(pre, LAT_FLOOR_S)
                if statistics.median(d for d, _ in ins) - m >= thr:
                    c["span:%s:latency_high" % tok] += 1
        elif pre:
            c["span:%s:missing_expected" % tok] += 1
    return c


# --------------------------------------------------------------------------- cells

def new_cell(generation, system, cell, run, block, posture, regime, valid, target, t0, windows):
    """windows: list of (kind, start, end[, pseudoFor]); kind in {fault, pseudo, cell}; pseudoFor = the fault
    families a G-old pseudo-window of that length stands in for. Streams are filled by the adapter."""
    return {"generation": generation, "system": system, "cell": cell, "run": run, "block": block,
            "posture": posture, "regime": regime, "valid": valid, "target": target, "t0": t0,
            "windows": windows, "logs": {}, "stats": {}, "metrics": {}, "spans": {}, "inputs": []}


def bag_cell(cell):
    """One cell -> list of bag rows, one per (window, service). Every service seen in the cell gets a row,
    so an empty bag is explicit (absence is not zero: a service with no stream at all has no row)."""
    rows = []
    services = sorted(set(cell["logs"]) | set(cell["metrics"]) | set(cell["spans"]))
    for w in cell["windows"]:
        kind, w0, w1 = w[:3]
        pseudo_for = list(w[3]) if len(w) > 3 else None
        for s in services:
            c = Counter()
            if s in cell["logs"]:
                c.update(log_symbols(cell["logs"][s], (w0, w1), cell_level=(kind == "cell")))
            for resource, series in cell["metrics"].get(s, {}).items():
                if kind != "cell":
                    c.update(metric_symbols(series, resource, cell["t0"], (w0, w1)))
            if s in cell["spans"] and kind != "cell":
                c.update(span_symbols(cell["spans"][s], cell["t0"], (w0, w1)))
            rows.append({"generation": cell["generation"], "system": cell["system"], "cell": cell["cell"],
                         "run": cell["run"], "block": cell["block"], "posture": cell["posture"],
                         "regime": cell["regime"], "valid": cell["valid"], "target": cell["target"],
                         "window": {"kind": kind, "start": w0, "end": w1, "pseudoFor": pseudo_for}, "service": s,
                         "label": "a-p-w" if cell["posture"] == "auth-persistence-webui" else None,   # A15: kept, excluded from R(p)
                         "symbols": sorted(c), "counts": dict(sorted(c.items()))})
    return rows


NO_FAULT = ("no-fault-cost", "baseline")


def is_no_fault(row):
    return row["regime"].startswith(NO_FAULT)


def window_class(w):
    """Calibration class of a window: whole-cell rows calibrate whole-cell rows; fault and pseudo windows
    calibrate against pseudo-windows; a G-old pseudo-window of length D_f serves only the families with that D_f."""
    if w["kind"] == "cell":
        return "cell"
    pf = w.get("pseudoFor")
    return "window:" + "+".join(pf) if pf else "window"


def calibrates(q, r):
    """Does no-fault row q belong to the calibration set of row r (same service assumed)?"""
    qk, rk = q["window"]["kind"], r["window"]["kind"]
    if rk == "cell":
        return qk == "cell"
    if qk != "pseudo":
        return False
    pf = q["window"].get("pseudoFor")
    if not pf:
        return True
    if rk == "pseudo":
        return pf == r["window"].get("pseudoFor")
    return r["regime"] in pf


def window_id(r):
    w = r["window"]
    return (r["cell"], w["kind"], w["start"], w["end"])


def calibrate(rows):
    """Derived symbols from the no-fault rows of the SAME generation (never across generations), per service:
    `log:template:novel` (template in no no-fault cell of the generation for that service, any window kind,
    leave-one-cell-out) and `log:rate:<tid>:high` (count vs the no-fault windows that calibrate the row
    (`calibrates`), one value per window, absent = 0, robust rule, floor 2). G3 admissibility counts go into
    the vocab, not into a symbol. Every no-fault row is exactly one window, so symbolNoFaultWindows <=
    noFaultWindows for every key."""
    vocab = {}
    for g in sorted({r["generation"] for r in rows}):
        G = [r for r in rows if r["generation"] == g and r["valid"]]
        nf_by_svc = defaultdict(list)
        seen = defaultdict(lambda: defaultdict(set))          # service -> template -> no-fault cells
        for r in G:
            if is_no_fault(r):
                nf_by_svc[r["service"]].append(r)
                for sym in r["counts"]:
                    if sym.startswith("log:template:"):
                        seen[r["service"]][sym].add(r["cell"])
        for r in G:
            s, own = r["service"], r["cell"]
            hist_rows = [q for q in nf_by_svc.get(s, []) if q["cell"] != own and calibrates(q, r)]
            n0 = len({window_id(q) for q in hist_rows})
            derived = Counter()
            for sym, n in r["counts"].items():
                if not sym.startswith("log:template:"):
                    continue
                if not (seen.get(s, {}).get(sym, set()) - {own}):
                    derived["log:template:novel"] += 1
                hist = [q["counts"].get(sym, 0) for q in hist_rows]
                if len(hist) >= MIN_BASELINE and len(hist) == n0:
                    m, thr = robust_threshold(hist, BURST_FLOOR)
                    if n - m >= thr:
                        derived["log:rate:%s:high" % sym.split(":", 2)[2]] += 1
            r["derived"] = sorted(derived)
            r["counts"].update(derived)
            r["symbols"] = sorted(set(r["symbols"]) | set(derived))
        nf_windows, firing = defaultdict(set), defaultdict(Counter)
        for s, qs in nf_by_svc.items():
            for q in qs:
                k = "%s/%s" % (s, window_class(q["window"]))
                nf_windows[k].add(window_id(q))
                for sym, n in q["counts"].items():
                    if n and not sym.startswith(("log:template:novel", "log:rate:")):
                        firing[k][sym] += 1
        vocab[g] = {"noFaultWindows": {k: len(v) for k, v in sorted(nf_windows.items())},
                    "admissibilityShare": TAU,
                    "templatesNoFaultCells": {s: {sym: len(c) for sym, c in v.items()} for s, v in seen.items()},
                    "symbolNoFaultWindows": {k: dict(v) for k, v in sorted(firing.items())}}
    return rows, vocab


# --------------------------------------------------------------------------- adapters

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hotel_cell(d, generation, run):
    ct = json.loads((d / "cell-contract.json").read_text())
    term = json.loads((d / "cell-terminal.json").read_text())
    cpu = json.loads((d / "cpu.json").read_text())
    fr = d / "fault-receipt.json"
    f = json.loads(fr.read_text()) if fr.exists() else None
    t0 = cpu["samples"][0]["capturedAtEpoch"]
    if f:
        windows = [("fault", epoch(f["startedAt"]), epoch(f["endedAt"]))]
    else:
        windows = [("pseudo", t0 + PSEUDO_AT, t0 + PSEUDO_AT + PSEUDO_LEN)]
    rk = ct["runKey"]
    cell = new_cell(generation, "hotel", run + "/" + d.relative_to(d.parents[3]).as_posix(), run, rk["block"], rk["posture"],
                    rk["regime"], term.get("candidateCellValid") is True, f["targetService"] if f else None, t0, windows)
    streams = defaultdict(list)
    compose_cli = 0
    for raw in (d / "application.log").read_text(errors="replace").splitlines():
        if " | " not in raw:
            compose_cli += 1               # G5: compose CLI lines without a `<service>-<n> |` prefix
            continue
        prefix, payload = raw.split(" | ", 1)
        streams[prefix.strip().rsplit("-", 1)[0]].append(payload)
    for s, lines in streams.items():
        cell["logs"][s], cell["stats"][s] = parse_stream(lines, HOTEL_LAYOUTS)
    cell["stats"]["_compose_cli"] = compose_cli
    ts = [r["t"] for rs in cell["logs"].values() for r in rs if r["t"] is not None]
    if ts:
        cell["windows"].append(("cell", min(ts), max(ts)))       # the retained stream (no G1); logs only
    for smp in cpu["samples"]:
        for c in smp["containers"]:
            cell["metrics"].setdefault(c["service"], {}).setdefault("cpu", []).append((smp["capturedAtEpoch"], c["cpuPercent"]))
    tr = d / "traces-normalized.json"
    if tr.exists():
        for e in json.loads(tr.read_text())["events"]:
            cell["spans"].setdefault(e["service"], []).append((e["startTimeUs"] / 1e6, e["operation"], e["durationUs"] / 1e6, bool(span_error(e))))
    cell["inputs"] = [d / n for n in ("cell-contract.json", "cell-terminal.json", "cpu.json", "application.log")] + \
                     ([fr] if f else []) + ([tr] if tr.exists() else [])
    return cell


def hotel_cells(run_dir, generation):
    rd = Path(run_dir)
    root = next(rd.glob("**/runs"))
    run = rd.name[-8:]
    for pat in ("cost/*/*/attempt-*", "effect/*/*/*/attempt-*"):
        for a in sorted(root.glob(pat)):
            yield hotel_cell(a, generation, run)


def teastore_cell(d, generation, operational=False):
    cv = d / "candidate-validation.json"
    if not cv.exists():
        return None
    v = json.loads(cv.read_text())
    rc = json.loads((d / "receipt.json").read_text())
    w = rc["window"]
    ms, me = epoch(w["measurementStartedAt"]), epoch(w["measurementEndedAt"])
    rk = v["runKey"]
    iv = d / "intervention.json"
    target, windows = None, [("cell", ms, me)]
    if iv.exists():
        i = json.loads(iv.read_text())
        target = i.get("service")
        if i.get("actualOnsetWall") and i.get("actualOffsetWall"):
            windows.append(("fault", epoch(i["actualOnsetWall"]), epoch(i["actualOffsetWall"])))
    cell = new_cell(generation, "teastore", d.relative_to(d.parents[2]).as_posix(), rk["studyEpoch"], rk["block"],
                    rk["posture"], rk["regime"], v["cellStatus"] == "valid", target, ms, windows)
    logs = sorted(d.glob("*.log"))
    if operational and (d / ".operational").is_dir():
        ri = d / "runtime-images.json"          # typed compose-service list (rabbitmq included); harness files (up, warmup, workload, ...) are not services
        declared = set(json.loads(ri.read_text()).get("services", {})) if ri.exists() else set()
        logs += sorted(x for x in (d / ".operational").glob("*.log") if x.stem in declared)
    for p in logs:
        s = p.stem if p.parent == d else "operational/" + p.stem
        cell["logs"][s], cell["stats"][s] = parse_stream(p.read_text(errors="replace").splitlines(), JVM_LAYOUTS)
    tr = d / "traces.json"
    if tr.exists():
        for r in json.loads(tr.read_text()):
            cell["spans"].setdefault(r["service"], []).append((r["timestamp"], r["operation"], r["duration_s"], r.get("status_code") not in (None, 200, 0)))
    cell["inputs"] = [cv, d / "receipt.json"] + ([iv] if iv.exists() else []) + logs + ([tr] if tr.exists() else [])
    return cell


def teastore_cells(campaign_dir, generation, operational=False):
    cells = []
    for d in sorted(Path(campaign_dir).glob("runs/*/*")):
        if not d.is_dir() or d.name.endswith(".blocked-evidence"):
            continue
        c = teastore_cell(d, generation, operational)
        if c:
            cells.append(c)
    # no-fault pseudo-window from timing metadata only: median onset offset and hold of the generation's fault cells
    on = [w[1] - c["t0"] for c in cells for w in c["windows"] if w[0] == "fault"]
    ln = [w[2] - w[1] for c in cells for w in c["windows"] if w[0] == "fault"]
    if on:
        a, b = statistics.median(on), statistics.median(ln)
        for c in cells:
            if not any(w[0] == "fault" for w in c["windows"]):
                c["windows"].append(("pseudo", c["t0"] + a, c["t0"] + a + b))
    return cells


GOLD_TARGET = {"auth_freeze": "auth", "orderitems_timeout": "auth", "db_crash": "db", "image_crash": "image",
               "image_loss": "image", "persistence_crash": "persistence", "persistence_latency": "persistence",
               "recommender_crash": "recommender", "recommender_exception": "recommender",
               "recommender_latency": "recommender", "registry_restart": "registry"}
GOLD_DATES = ("20260717", "20260718")


def gold_family(name):
    if name.startswith("baseline_ref_"):
        return "baseline", name.split("_")[2]
    if name.startswith("fault_"):
        return name[len("fault_"):].rsplit("_", 2)[0], None
    return None, None


def gold_run(r, generation, pseudo_by_family=None):
    md = json.loads((r / "metadata.json").read_text())
    fam, ref = gold_family(r.name)
    t0, t1 = md["start_time"], md["end_time"]
    post = (md.get("log_filter_stats") or {}).get("log_post_buffer_seconds", 30.0)
    if fam == "baseline":
        by_d = defaultdict(list)
        for fam_, D in (pseudo_by_family or {}).items():
            by_d[D].append(fam_)
        windows = [("pseudo", t0 + 75.0, t0 + 75.0 + D, tuple(sorted(fams))) for D, fams in sorted(by_d.items())]
    else:
        f = md["fault"]
        windows = [("fault", f["fault_started_at"], f["fault_finished_at"])]
    lfs = md.get("log_filter_stats") or {}
    windows.append(("cell", lfs.get("filter_window_start", t0), lfs.get("filter_window_end", t1 + post)))
    cell = new_cell(generation, "teastore", r.name, getattr(gold_select, "campaign_of", {}).get(r.name, r.name),
                    ref, "kieker-native", fam, True, GOLD_TARGET.get(fam), t0, windows)
    by_svc, stamps, fallback = defaultdict(list), defaultdict(list), 0
    for x in json.loads((r / "logs.json").read_text()):
        if x["timestamp"] > t1 + post:
            fallback += 1                                   # collector-fallback stamp (F6), excluded
            continue
        by_svc[x["service"]].append(x["message"])           # the old `level` field is ignored (G5)
        stamps[x["service"]].append(x["timestamp"])
    for s, lines in by_svc.items():
        st = stamps[s]
        cell["logs"][s], cell["stats"][s] = parse_stream(lines, JVM_LAYOUTS, stamp=lambda i, st=st: st[i])
    cell["stats"]["_fallback_stamps"] = fallback
    for x in json.loads((r / "metrics.json").read_text()):
        m = cell["metrics"].setdefault(x["service"], {})
        m.setdefault("cpu", []).append((x["timestamp"], x["cpu_percent"]))
        if x.get("memory_bytes") is not None:
            m.setdefault("mem", []).append((x["timestamp"], x["memory_bytes"]))
    tr = r / "traces.json"
    if tr.exists():
        for x in json.loads(tr.read_text()):
            cell["spans"].setdefault(x["service"], []).append((x["timestamp"], x["operation"], x["duration_s"], x.get("status_code") not in (None, 200, 0)))
    cell["inputs"] = [r / "metadata.json", r / "logs.json", r / "metrics.json"] + ([tr] if tr.exists() else [])
    return cell


def gold_select(root):
    """G-old population: by_server/fb14srv6 runs listed by a `fault_campaign_*.json` manifest dated 2026-07-17/18,
    kieker_native, all sidecars present, and only runs of COMPLETE campaigns (a campaign with fewer runs than the
    largest one is partial and excluded, counted)."""
    root = Path(root)
    campaign_of, size = {}, Counter()
    for mf in sorted(root.glob("fault_campaign_*.json")):
        if not any(("_%s_" % d) in mf.name for d in GOLD_DATES):
            continue
        m = json.loads(mf.read_text())
        for x in m.get("runs", []):
            campaign_of[Path(x["output_dir"]).name] = m["campaign_id"]
            size[m["campaign_id"]] += 1
    full = max(size.values()) if size else 0
    keep, excluded = [], Counter()
    for r in sorted(root.iterdir()):
        if not r.is_dir() or r.name not in campaign_of:
            continue
        fam, _ = gold_family(r.name)
        if fam is None:
            continue
        if size[campaign_of[r.name]] < full:
            excluded["partial campaign"] += 1
            continue
        if not all((r / n).exists() for n in ("metadata.json", "logs.json", "metrics.json")):
            excluded["missing sidecar"] += 1
            continue
        md = json.loads((r / "metadata.json").read_text())
        if (md.get("trace_collection") or {}).get("collector") != "kieker_native":
            excluded["collector not kieker_native"] += 1
            continue
        if fam != "baseline" and not (md.get("fault") or {}).get("fault_started_at"):
            excluded["no fault timing"] += 1
            continue
        keep.append(r)
    gold_select.campaign_of = campaign_of
    return keep, excluded


def gold_runs(root, generation):
    runs, excluded = gold_select(root)
    durations = defaultdict(list)
    for r in runs:
        fam, _ = gold_family(r.name)
        if fam != "baseline":
            f = json.loads((r / "metadata.json").read_text())["fault"]
            durations[fam].append(f["fault_finished_at"] - f["fault_started_at"])
    pseudo = {fam: statistics.median(v) for fam, v in durations.items()}
    for r in runs:                       # one run at a time: the 60 GB corpus is streamed, never held
        yield gold_run(r, generation, pseudo)
    gold_runs.excluded = excluded
    gold_runs.pseudo = pseudo


# --------------------------------------------------------------------------- summary (vocabulary and coverage only)

def summarise(rows, cells_meta):
    """Per generation: cells, services, layout mix, unparsed share (G6), vocabulary sizes. Never by regime."""
    out = {}
    for g in sorted({r["generation"] for r in rows}):
        R = [r for r in rows if r["generation"] == g]
        meta = cells_meta[g]
        lines = Counter()
        per_service = defaultdict(Counter)
        for st in meta["stats"]:
            for s, c in st.items():
                if s.startswith("_"):
                    lines[s] += c
                    continue
                for k, v in c.items():
                    lines[k] += v
                    per_service[s][k] += v
        vocab = defaultdict(set)
        for r in R:
            for sym in r["symbols"]:
                fam = sym.split(":", 1)[0]
                vocab[fam].add(sym)
                if sym.startswith("log:template:") and sym != "log:template:novel":
                    vocab["template-ids"].add(sym)
                if sym.startswith("log:exception:"):
                    vocab["exception-classes"].add(sym)
                if sym.startswith("span:"):
                    vocab["span-ops"].add(sym.rsplit(":", 1)[0])
        app_lines = lines["lines"] - lines["harness"]
        unparsed_share = (lines["unparsed"] / app_lines) if app_lines else None
        out[g] = {
            "cells": meta["cells"], "validCells": meta["valid"], "excluded": meta.get("excluded", {}),
            "pseudoDurations": meta.get("pseudoDurations"),
            "windows": Counter(k for _, k in {(r["cell"], r["window"]["kind"]) for r in R}),
            "services": sorted({r["service"] for r in R}),
            "lines": {"total": lines["lines"], "harness": lines["harness"], "application": app_lines,
                      "unparsed": lines["unparsed"], "continuation": lines["continuation"],
                      "composeCli": lines["_compose_cli"], "fallbackStamps": lines["_fallback_stamps"]},
            "unparsedShare": unparsed_share,
            "stopRuleSP": (unparsed_share is not None and unparsed_share > 0.05),
            "layouts": {k[len("record:"):]: v for k, v in lines.items() if k.startswith("record:")},
            "unparsedPerService": {s: {"lines": c["lines"] - c["harness"], "unparsed": c["unparsed"]}
                                   for s, c in sorted(per_service.items())},
            "vocabulary": {k: len(v) for k, v in sorted(vocab.items())},
            "symbolsPerModality": {k: len(v) for k, v in vocab.items() if k in ("log", "metric", "span")},
        }
    return out


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(HERE), check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def run(args):
    if args.out is None:
        sys.exit("--out is required (evidence stays out of git; default is tmp/s4-symptoms/<utc-stamp>/)")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) / stamp
    if out.exists():
        sys.exit("refusing to overwrite %s" % out)
    out.mkdir(parents=True)
    rows, inputs, meta = [], [], {}
    seen_gen = {}
    for kind, gen, path in args.sources:
        if gen in seen_gen and seen_gen[gen] != kind:
            sys.exit("generation %s bound to two adapters" % gen)
        seen_gen[gen] = kind
        m = meta.setdefault(gen, {"cells": 0, "valid": 0, "stats": [], "kind": kind, "paths": []})
        m["paths"].append(str(path))
        if kind == "hotel":
            it = hotel_cells(path, gen)
        elif kind == "teastore":
            it = teastore_cells(path, gen, operational=args.operational)
        elif kind == "gold":
            it = gold_runs(path, gen)
        else:
            sys.exit("unknown adapter %s" % kind)
        for cell in it:
            m["cells"] += 1
            m["valid"] += bool(cell["valid"])
            m["stats"].append(cell["stats"])
            inputs += [(gen, p) for p in cell["inputs"]]
            rows += bag_cell(cell)
            print("  %s %s windows=%d services=%d" % (gen, cell["cell"], len(cell["windows"]), len(cell["logs"]) or len(cell["metrics"])), file=sys.stderr)
        if kind == "gold":
            m["excluded"] = dict(getattr(gold_runs, "excluded", {}))
            m["pseudoDurations"] = getattr(gold_runs, "pseudo", {})
    rows, vocab = calibrate(rows)
    with open(out / "bags.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    summary = summarise(rows, meta)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=list))
    (out / "vocab.json").write_text(json.dumps(vocab, indent=2, sort_keys=True))
    manifest = {"alphabet": ALPHABET_VERSION, "script": sha256_file(Path(__file__)),
                "detection.py": sha256_file(HERE.parent / "sprint-draft2" / "detection.py"),
                "frameworkCommit": git_commit(), "generatedAt": stamp, "argv": sys.argv[1:],
                "python": sys.version.split()[0],
                "generations": {g: {"adapter": m["kind"], "paths": m["paths"], "pseudoDurations": m.get("pseudoDurations")}
                                for g, m in meta.items()},
                "inputs": [{"generation": g, "path": str(p), "bytes": p.stat().st_size, "sha256": sha256_file(p)}
                           for g, p in inputs]}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({g: {k: v for k, v in s.items() if k not in ("unparsedPerService", "services")} for g, s in summary.items()},
                     indent=2, default=list))
    print("wrote", out)


# --------------------------------------------------------------------------- self-check (fixtures; planted defects)

def _fixture_hotel():
    t0 = 1_790_000_000.0
    iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    golog = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y/%m/%d %H:%M:%S")
    w = (t0 + 45.0, t0 + 60.0)
    cell = new_cell("FX-H", "hotel", "fx/hotel", "fx", 1, "full", "reservation-pause-effect", True, "reservation", t0, [("fault",) + w])
    lines = {
        "frontend": [
            '{"level":"info","time":"%s","message":"TLS disabled."}' % iso(t0 + 1),
            '{"level":"info","time":"%s","message":"Set global log level: info ERROR is in the text"}' % iso(t0 + 50),
            "\x1b[90m%s\x1b[0m \x1b[31mERR\x1b[0m \x1b[1mservices/frontend/server.go:271\x1b[0m\x1b[36m >\x1b[0m SearchHandler failed id=42" % iso(t0 + 47),
            "\x1b[90m%s\x1b[0m \x1b[31mERR\x1b[0m \x1b[1mservices/frontend/server.go:271\x1b[0m\x1b[36m >\x1b[0m SearchHandler failed id=43" % iso(t0 + 48),
            "%s ERROR: [Consul resolver] bad state" % golog(t0 + 49),
            "%s plain grpc line" % golog(t0 + 49),
            'OBSPLACEMENT_WITNESS {"opaqueToken":"x"}',
            "goroutine 7 [running]:",                       # continuation of the previous record
        ],
        "geo": ["no layout at all, before any record",            # orphan continuation: unparsed (G6)
                "\x1b[90m%s\x1b[0m \x1b[32mINF\x1b[0m \x1b[1mcmd/geo/main.go:23\x1b[0m\x1b[36m >\x1b[0m Reading config..." % iso(t0 + 2)],
    }
    for s, ls in lines.items():
        cell["logs"][s], cell["stats"][s] = parse_stream(ls, HOTEL_LAYOUTS)
    cell["metrics"]["reservation"] = {"cpu": [(t0 + i, 3.0 + 0.1 * (i % 3)) for i in range(40)] + [(t0 + 46, 0.0), (t0 + 50, 0.0), (t0 + 55, 0.0)]}
    cell["metrics"]["frontend"] = {"cpu": [(t0 + i, 3.0 + 0.1 * (i % 3)) for i in range(40)] + [(t0 + 46, 3.1), (t0 + 50, 3.0)]}
    cell["metrics"]["rate"] = {"cpu": [(t0 + 46, 3.1)]}
    cell["spans"]["frontend"] = [(t0 + i, "HTTP GET /hotels", 0.010, False) for i in range(40)] + [(t0 + 47, "HTTP GET /hotels", 0.500, True)]
    cell["spans"]["reservation"] = [(t0 + i, "/reservation.Reservation/CheckAvailability", 0.002, False) for i in range(40)]
    return cell


def _fixture_jvm():
    ms = 1_789_000_000.0
    jul = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%d-%b-%Y %H:%M:%S.%f")[:-3]
    cell = new_cell("FX-T", "teastore", "fx/teastore", "fx", 1, "full", "persistence-crash-effect", True, "persistence", ms,
                    [("cell", ms, ms + 600), ("fault", ms + 190, ms + 340)])
    auth = [
        "[http-nio-8080-exec-3] INFO tools.descartes.teastore.auth.rest.AuthUserActionsRest - OBSERVABILITY_APP_WITNESS {}",
        "com.netflix.client.ClientException: Number of retries on next server exceeded max 2 retries, while making a call for: persistence:8080",
        "\tat com.netflix.loadbalancer.reactive.LoadBalancerCommand$4.call(LoadBalancerCommand.java:352)",
        "Caused by: java.net.UnknownHostException: persistence",
        "\t... 85 more",
        "[http-nio-8080-exec-5] WARN tools.descartes.teastore.registryclient.loadbalancers.ServiceLoadBalancer - No Server registered for Service: tools.descartes.teastore.persistence",
        "[http-nio-8080-exec-6] INFO tools.descartes.teastore.auth.X - message saying ERROR but at INFO",
    ]
    pers = [
        "WriterController: WriterClassName: kieker.monitoring.writer.filesystem.FileWriter",   # orphan, unparsed
        "%s INFO [main] org.apache.catalina.startup.VersionLoggerListener.log Server version name:   Apache Tomcat/10.0.7" % jul(ms + 100),
        "\tkieker.monitoring.writer.collector",                                                  # continuation (indented)
        "%s WARNING [http-nio-8080-exec-8] org.glassfish.jersey.server.ServerRuntime$Responder.process An exception mapping did not succeed" % jul(ms + 200),
        "%s 8 [Warning] Aborted connection 8 to db: 'teadb' user: 'teauser' host: '10.151.2.7' (Got an error reading communication packets)"
        % dt.datetime.fromtimestamp(ms + 400, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S").replace(" 0", "  "),   # MariaDB pads the hour with a space
    ]
    cell["logs"]["auth"], cell["stats"]["auth"] = parse_stream(auth, JVM_LAYOUTS)
    cell["logs"]["persistence"], cell["stats"]["persistence"] = parse_stream(pers, JVM_LAYOUTS)
    return cell


def self_check():
    # --- Hotel layouts, windows, metric and span symbols
    h = _fixture_hotel()
    st = h["stats"]["frontend"]
    assert st["harness"] == 1 and st["continuation"] == 1 and st["unparsed"] == 0, st
    assert h["stats"]["geo"]["unparsed"] == 1, h["stats"]["geo"]
    rows = {(r["service"]): r for r in bag_cell(h)}
    fe = rows["frontend"]["counts"]
    tid = template_id("zerolog-console", "error", "services/frontend/server.go:271", "SearchHandler failed id=42")
    assert fe["log:level:error"] == 3, fe                  # 2 console ERR + 1 gRPC ERROR
    assert fe["log:template:" + tid] == 2, fe              # id=42 / id=43 mask to one template
    assert "log:level:info" not in fe and not any(k.startswith("log:level:") and "warn" in k for k in fe)
    assert fe["span:HTTP_GET_/hotels:present"] == 1 and fe["span:HTTP_GET_/hotels:error"] == 1 and fe["span:HTTP_GET_/hotels:latency_high"] == 1, fe
    assert "metric:cpu:spike_up" not in fe and "metric:cpu:spike_down" not in fe, fe
    rs = rows["reservation"]["counts"]
    assert rs["metric:cpu:spike_down"] == 1 and rs["metric:cpu:plateau_down"] == 1 and "metric:cpu:spike_up" not in rs, rs
    assert rs["span:/reservation.Reservation/CheckAvailability:missing_expected"] == 1, rs
    assert rows["rate"]["counts"] == {"metric:cpu:?": 1}, rows["rate"]
    assert rows["geo"]["counts"] == {}, rows["geo"]         # its only record is outside the window
    # planted defect 1: a message containing "ERROR" at level info must not become an error symbol
    assert "log:level:error" not in log_symbols([parse_zerolog_json('{"level":"info","time":"2026-09-24T03:29:07Z","message":"ERROR here"}')],
                                                (0, 4e9)), "level read from message text"
    # planted defect 2: mutate the level field and the symbol set must change (the check is not vacuous)
    mutated = [dict(r, level="warn" if r["level"] == "error" else r["level"]) for r in h["logs"]["frontend"]]
    assert log_symbols(mutated, h["windows"][0][1:], False)["log:level:warn"] == 3
    assert log_symbols(mutated, h["windows"][0][1:], False)["log:level:error"] == 0
    # planted defect 3: a flat series must not spike, and the planted spike must
    flat = [(i, 3.0 + 0.1 * (i % 3)) for i in range(40)] + [(46, 3.1)]
    assert metric_symbols(flat, "cpu", 0, (45, 60)) == Counter(), "false spike"
    assert metric_symbols(flat + [(50, 9.0)], "cpu", 0, (45, 60)) == Counter({"metric:cpu:spike_up": 1}), "missed planted spike"
    assert metric_symbols([(1, 5.0), (2, 5.0)], "cpu", 0, (45, 60)) == Counter({"metric:cpu:?": 1}), "insufficient baseline is not zero"
    # --- JVM layouts: log4j, JUL, MariaDB, throwable header + cause, Kieker banner
    t = _fixture_jvm()
    sa, sp = t["stats"]["auth"], t["stats"]["persistence"]
    assert sa["harness"] == 1 and sa["record:log4j"] == 2 and sa["record:jvm-throwable"] == 1 and sa["continuation"] == 3 and sa["unparsed"] == 0, sa
    assert sp["unparsed"] == 1 and sp["record:jul"] == 2 and sp["record:mariadb"] == 1 and sp["continuation"] == 1, sp
    rows = {(r["window"]["kind"], r["service"]): r["counts"] for r in bag_cell(t)}
    ca = rows[("cell", "auth")]
    assert ca["log:level:warn"] == 1 and "log:level:error" not in ca, ca
    assert ca["log:exception:ClientException"] == 1 and ca["log:exception:UnknownHostException"] == 1, ca
    assert sum(1 for k in ca if k.startswith("log:template:")) == 2, ca      # two log4j records; the throwable has no template
    cp = rows[("cell", "persistence")]
    assert cp["log:level:warn"] == 2, cp                                     # JUL WARNING + MariaDB [Warning]
    fp = rows[("fault", "persistence")]
    assert fp["log:level:warn"] == 1, fp                                     # only the JUL line (ms+200) is inside the fault window
    assert rows[("fault", "auth")] == {}, rows[("fault", "auth")]            # log4j lines have no timestamp: cell level only
    # --- calibration: novelty and burst against no-fault windows of the same generation, leave-one-out
    base = [{"generation": "FX", "cell": "nf%d" % i, "regime": "no-fault-cost", "valid": True, "service": "s",
             "window": {"kind": "pseudo", "start": 0, "end": 1}, "symbols": ["log:template:aaa"], "counts": {"log:template:aaa": 1}} for i in range(4)]
    fault = {"generation": "FX", "cell": "f1", "regime": "x-effect", "valid": True, "service": "s",
             "window": {"kind": "fault", "start": 0, "end": 1}, "symbols": ["log:template:aaa", "log:template:bbb"],
             "counts": {"log:template:aaa": 9, "log:template:bbb": 1}}
    rows, vocab = calibrate(base + [fault])
    assert rows[-1]["derived"] == ["log:rate:aaa:high", "log:template:novel"], rows[-1]["derived"]
    assert all(r["derived"] == [] for r in rows[:-1]), [r["derived"] for r in rows[:-1]]
    assert vocab["FX"]["templatesNoFaultCells"]["s"]["log:template:aaa"] == 4
    assert vocab["FX"]["noFaultWindows"] == {"s/window": 4}
    # --- template masking is language-level only
    assert mask("Removed x@auth:8080 id 3fa85f64-5717-4562-b3fc-2c963f66afa6 at 10.1.2.3:80 0xdeadbeef 42") == "Removed x@auth:<n> id <uuid> at <ip> <hex> <n>"
    assert parse_throwable("kieker.monitoring.writer.collector") is None and parse_throwable("\tjava.lang.Foo: x") is None
    assert parse_throwable("java.lang.StackOverflowError")["exc"] == ["StackOverflowError"]
    print("self-check ok")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--out", default=None, help="output root; a new <utc-stamp>/ dir is created under it")
    ap.add_argument("--operational", action="store_true",
                    help="TeaStore: also read .operational/<service>.log dumps for services declared in runtime-images.json (blocked cells and re-runs)")
    ap.add_argument("sources", nargs="*", help="triples: <hotel|teastore|gold> <generation> <path> ...")
    a = ap.parse_args(argv)
    if a.self_check:
        self_check()
        return
    if len(a.sources) % 3 or not a.sources:
        ap.error("sources come in triples: <adapter> <generation> <path>")
    a.sources = [(a.sources[i], a.sources[i + 1], Path(a.sources[i + 2])) for i in range(0, len(a.sources), 3)]
    run(a)


if __name__ == "__main__":
    main()
