#!/usr/bin/env python3
"""OTel Demo detection adapter (direction (c), research/otel-offpath/DECLARATION.md), offline only.

Reads retained cells of an OTel Demo candidate campaign and reads the declaration's predictions mechanically.

    /usr/bin/python3 -B research/otel-offpath/adapter.py <evidence-root> [--out PATH]
    /usr/bin/python3 -B research/otel-offpath/adapter.py --self-check

<evidence-root> holds runs/<regime>/bNN-OO-<posture>/ (v3r1: tmp/otel-v3-evidence; the offpath epoch: same layout with
three regime directories). Clear ~/Library/Caches/com.apple.python/<repo>/research before a /usr/bin/python3 replay.

Everything scored is imported, unchanged, by path:
- symbol alphabet and rules: research/s4-conjunction/symptoms.py (log_symbols, metric_symbols, span_symbols, mask,
  template_id, rec; K and LAT_FLOOR_S read from the module at call time);
- entry point: research/visibility-map/visibility.py's `ledger_rule`, `split` and `otel_ledger_rows` (the transcription of
  research/hotel-selected/ledger_check.py that visibility.py checks equal to `ledger_check.cell` on every Hotel cell);
- G3 share TAU from research/lmt-pilot/lmt_detect.py (0.05); its arithmetic (`n > TAU * len(nf)`, lmt_detect.py:151) and
  G2 (`x[1] != c["target"]`, lmt_detect.py:159) are restated here because lmt_detect.score is bound to Hotel files.

What is new here (engineering defaults, recorded in the output under `defaults`):
- the debug-exporter parser (otelcol.log -> per-service spans, metric samples, log records), described in parse_otelcol;
- metric samples per (service, metric name): Gauge and non-monotonic Sum = the value summed over data-point attribute
  sets at one export timestamp; monotonic cumulative Sum = per-attribute-set delta / dt, summed; Histogram = per-set
  delta count / dt (`<name>~rate`) and delta sum / delta count (`<name>~mean`);
- families L (log templates), M (OTLP metrics), T (spans); collected in every posture except `none`.

Absence is not zero: a prediction with no episode is `—`, a family not collected is `—`.
Runs under /usr/bin/python3 (3.9) and the uv 3.13 environment; no `X | None` annotations evaluated at runtime.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import importlib.util
import json
import math
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
REPO = RESEARCH.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SYMPTOMS_PATH = RESEARCH / "s4-conjunction" / "symptoms.py"
VISIBILITY_PATH = RESEARCH / "visibility-map" / "visibility.py"
LMT_PATH = RESEARCH / "lmt-pilot" / "lmt_detect.py"
SYM = _load("offpath_symptoms", SYMPTOMS_PATH)
VIS = _load("offpath_visibility", VISIBILITY_PATH)
LMT = _load("offpath_lmt_detect", LMT_PATH)
TAU = LMT.TAU
NON_SYMPTOMS = ("present", "?", "missing")          # research/s4-conjunction/relevance.py:36, never fire a sensor
FROZEN = (SYM.K, SYM.LAT_FLOOR_S)                   # (4.0, 0.001) as committed
GRID_K = (3.0, 4.0, 5.0)
GRID_FLOOR_S = (0.0005, 0.001, 0.002)
LEDGER_FROZEN = (3.0, 1.0)                          # ledger_check.py: max(3 x MAD, 1 ms)

APP_SERVICES = (
    "accountingservice", "adservice", "cartservice", "checkoutservice", "currencyservice", "emailservice", "flagd",
    "flagd-ui", "frauddetectionservice", "frontend", "frontendproxy", "imageprovider", "kafka", "loadgenerator",
    "paymentservice", "productcatalogservice", "quoteservice", "recommendationservice", "shippingservice",
)
SPAN_SERVICE_ALIASES = {"frontend-proxy": "frontendproxy"}   # candidate_remote.SPAN_SERVICE_ALIASES
COLLECTOR_SELF = ("otelcol", "otelcol-contrib")
POSTURES = ("none", "selected", "async", "full")
FAMILIES = ("L", "M", "T")
FAMILY_POSTURES = {f: ("selected", "async", "full") for f in FAMILIES}   # `none` emits no application telemetry

_V3_SELECTED = ("frontend", "frontendproxy", "recommendationservice")
_OFF_SELECTED = ("cartservice", "checkoutservice", "currencyservice", "emailservice", "flagd", "frontend",
                 "frontendproxy", "paymentservice", "productcatalogservice", "quoteservice", "shippingservice")
LAYOUTS = {
    "otel-demo-candidate-pilot-v3": {
        "regimes": ("frontend-pause-effect", "no-fault-cost"),
        "closures": {"none": (), "selected": _V3_SELECTED,
                     "async": tuple(sorted(_V3_SELECTED + ("accountingservice", "checkoutservice",
                                                           "frauddetectionservice", "kafka"))),
                     "full": APP_SERVICES},
        "source": "tmp/otel-v2-admission 64ba7c9 candidate_runtime.SELECTED_CLOSURE / ASYNC_CLOSURE",
    },
    "otel-demo-offpath-v1": {
        "regimes": ("fraud-pause-effect", "frontend-pause-effect", "no-fault-cost"),
        "closures": {"none": (), "selected": _OFF_SELECTED,
                     "async": tuple(sorted(_OFF_SELECTED + ("accountingservice", "frauddetectionservice", "kafka"))),
                     "full": APP_SERVICES},
        "source": "offpath harness literal (selected = synchronous order path incl. flagd; async = + kafka, "
                  "frauddetectionservice, accountingservice)",
    },
}
FRAUD = "fraud-pause-effect"
FRONTEND = "frontend-pause-effect"
NO_FAULT = "no-fault-cost"
FRAUD_TARGET = "frauddetectionservice"
K3_RESTRICTED = ("kafka", "accountingservice")

DEFAULTS = [
    "window: fault cells use [appliedMonotonicOffsetSeconds, revertingMonotonicOffsetSeconds] when the receipt has them, "
    "else [actualOnsetMonotonicOffsetSeconds, actualOffsetMonotonicOffsetSeconds]; barrier-relative, mapped to wall time "
    "as ledger startedAtEpoch + offset (visibility.py's OTel mapping)",
    "baseline start t0 = ledger startedAtEpoch (measurement start); the pre-window is [t0, window start)",
    "no-fault cells: one pseudo window per fault regime at that regime's median fault offsets (visibility.py / "
    "lmt_detect.py rule, applied per regime so G3 calibrates each regime on its own window placement)",
    "G3 per (family, regime): no-fault cells of every posture that collects the family (selected, async, full), pooled as "
    "lmt_detect.score pools a family's posture set; inadmissible iff fired in > TAU x n0 of them",
    "a sensor is (family, service, name): L name = template id (symptoms.template_id over framework `otlp-log`, level, "
    "instrumentation scope, body), M name = metric name (+ `~rate` / `~mean` for histograms), T name = span name",
    "a sensor fires on a symptom symbol: L any template occurrence in the window; M spike/plateau up/down (present, ?, "
    "missing never fire, relevance.py:36); T error, latency_high, missing_expected",
    "log level from SeverityNumber (13-16 warn, 17-20 error, 21-24 fatal); SeverityText only when the number is 0",
    "ledger ok = status 200 and error None, journey latency = endedAtEpoch - startedAtEpoch (visibility.otel_ledger_rows)",
    "K2/K3 'a sensor catches >= 2 of 3' read literally per sensor (perSensor); the union reading (any sensor, per episode) "
    "is reported beside it (anySensorPerEpisode)",
    "the threshold grid varies symptoms.K and symptoms.LAT_FLOOR_S only (h4_sweep.py approach), restoring them after each "
    "setting; the ledger rule is not a function of either, so K1/C1 are constant over that grid; a separate ledgerGrid "
    "varies the ledger rule's own constants (3 x MAD, 1 ms) for information only",
]


# --------------------------------------------------------------------------- debug-exporter parser

def _payload(line):
    """Strip the compose prefix `otelcol-1  | `; keep the payload."""
    head = line[:40]
    i = head.find("| ")
    return line[i + 2:] if i >= 0 and head[:i].strip().startswith("otelcol") else line


def _nanos(stamp):
    """`2026-09-30 06:30:14.399601831 +0000 UTC` -> integer epoch nanoseconds, None when unset (epoch 0)."""
    parts = stamp.strip().split()
    if len(parts) < 2:
        return None
    whole, _, frac = parts[1].partition(".")
    try:
        base = dt.datetime.strptime(parts[0] + " " + whole, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None
    if frac and not frac.isdigit():
        return None
    ns = int(base.timestamp()) * 1_000_000_000 + (int(frac[:9].ljust(9, "0")) if frac else 0)
    return None if ns == 0 else ns


def _attr_value(text):
    """`Str(x)` / `Int(3)` -> the inner text."""
    if "(" in text and text.endswith(")"):
        return text[text.index("(") + 1:-1]
    return text


def _severity(number_text, severity_text):
    level = None
    if "(" in number_text:
        try:
            n = int(number_text[number_text.index("(") + 1:number_text.index(")")])
        except ValueError:
            n = 0
        level = "warn" if 13 <= n <= 16 else "error" if 17 <= n <= 20 else "fatal" if 21 <= n <= 24 else None
        if n:
            return level
    return {"WARN": "warn", "WARNING": "warn", "ERROR": "error", "FATAL": "fatal", "CRITICAL": "fatal"}.get(
        severity_text.strip().upper())


def catalog_service(name):
    name = SPAN_SERVICE_ALIASES.get(name, name)
    if name in COLLECTOR_SELF:
        return None, "collector"
    if name not in APP_SERVICES:
        return None, "unknown"
    return name, None


def parse_otelcol(lines):
    """Debug exporter (detailed verbosity) -> {spans, points, logs, stats}.

    Layout (collector v0.108): `Resource{Spans,Metrics,Log} #n` opens a resource; `Resource attributes:` lists
    `-> key: Type(value)` until the first `Scope...` line; `InstrumentationScope <name> <version>`; then `Span #n`
    (fields `Name`, `Start time`, `End time`, `Status code`), `Metric #n` (a `Descriptor:` with `-> Name`, `-> DataType`,
    `-> IsMonotonic`, `-> AggregationTemporality`, then `<Type>DataPoints #n` with `Data point attributes:`,
    `StartTimestamp`, `Timestamp`, `Value` | `Count`/`Sum`), or `LogRecord #n` (`ObservedTimestamp`, `Timestamp`,
    `SeverityText`, `SeverityNumber`, `Body`). A record is flushed when the next header starts."""
    spans, points, logs = defaultdict(list), [], defaultdict(list)
    stats = Counter()
    kind = None          # "spans" | "metrics" | "logs"
    res_attrs, in_res, scope = {}, False, None
    svc = None
    desc, in_desc = {}, False
    cur = None           # pending record (dict with "_t" type)
    in_dp_attrs = False

    def resolve():
        nonlocal svc
        name = res_attrs.get("service.name")
        if name is None:
            svc = None
            stats["nonServiceResources"] += 1        # collector receivers (redis, hostmetrics processes): infrastructure
            return
        svc, why = catalog_service(name)
        if why:
            stats["%sResources" % why] += 1
            if why == "unknown":
                stats["unknown:" + name] += 1

    def flush():
        nonlocal cur
        if cur is None:
            return
        t = cur.pop("_t")
        if svc is not None:
            if t == "span" and cur.get("start") is not None and cur.get("end") is not None and cur.get("name") is not None:
                spans[svc].append((cur["start"] / 1e9, cur["name"], (cur["end"] - cur["start"]) / 1e9,
                                   cur.get("status") == "Error"))
                stats["spans"] += 1
            elif t == "dp" and cur.get("ts") is not None:
                cur["service"] = svc
                cur["desc"] = dict(desc)
                points.append(cur)
                stats["dataPoints"] += 1
            elif t == "log":
                ns = cur.get("ts") or cur.get("observed")
                logs[svc].append(SYM.rec("otlp-log", _severity(cur.get("sevnum", ""), cur.get("sevtext", "")),
                                         None if ns is None else ns / 1e9, scope, cur.get("body", "")))
                stats["logRecords"] += 1
        cur = None

    for raw in lines:
        p = _payload(raw.rstrip("\r\n"))
        s = p.strip()
        if not s:
            continue
        # headers (may follow `<ts>\tinfo\t`)
        last = s.rsplit("\t", 1)[-1]
        if last.startswith(("ResourceSpans #", "ResourceMetrics #", "ResourceLog #")):
            flush()
            kind = "spans" if last.startswith("ResourceSpans") else "metrics" if last.startswith("ResourceMetrics") else "logs"
            res_attrs, in_res, scope, svc, desc, in_desc = {}, False, None, None, {}, False
            continue
        if "\tinfo\t" in s or "\twarn\t" in s or "\terror\t" in s:
            flush()                                  # collector's own log line: ends any pending record
            continue
        if kind is None:
            continue
        if s == "Resource attributes:":
            in_res = True
            continue
        if s.startswith(("ScopeSpans #", "ScopeMetrics #", "ScopeLogs #")):
            flush()
            if in_res:
                in_res = False
                resolve()
            continue
        if in_res:
            if s.startswith("-> "):
                k, _, v = s[3:].partition(": ")
                res_attrs[k] = _attr_value(v)
            continue
        if s.startswith("InstrumentationScope"):
            bits = s.split()
            scope = bits[1] if len(bits) > 1 else ""
            continue
        if kind == "spans":
            if s.startswith("Span #"):
                flush()
                cur = {"_t": "span"}
            elif cur is not None and ":" in s:
                k, _, v = s.partition(":")
                k = k.strip()
                v = v.strip()
                if k == "Name":
                    cur["name"] = v
                elif k == "Start time":
                    cur["start"] = _nanos(v)
                elif k == "End time":
                    cur["end"] = _nanos(v)
                elif k == "Status code":
                    cur["status"] = v
            continue
        if kind == "metrics":
            if s.startswith("Metric #"):
                flush()
                desc, in_desc = {}, False
            elif s == "Descriptor:":
                in_desc = True
            elif in_desc and s.startswith("-> "):
                k, _, v = s[3:].partition(": ")
                desc[k] = v
            elif "DataPoints #" in s:
                flush()
                in_desc = False
                cur = {"_t": "dp", "attrs": [], "type": s.split("DataPoints", 1)[0] or "Number"}
                in_dp_attrs = False
            elif cur is not None:
                if s == "Data point attributes:":
                    in_dp_attrs = True
                elif s.startswith("-> ") and in_dp_attrs:
                    cur["attrs"].append(s[3:])
                else:
                    in_dp_attrs = False
                    k, _, v = s.partition(": ")
                    if k == "StartTimestamp":
                        cur["start"] = _nanos(v)
                    elif k == "Timestamp":
                        cur["ts"] = _nanos(v)
                    elif k == "Value":
                        try:
                            cur["value"] = float(v)
                        except ValueError:
                            stats["unparsedValue"] += 1
                    elif k == "Count":
                        try:
                            cur["count"] = float(v)
                        except ValueError:
                            pass
                    elif k == "Sum":
                        try:
                            cur["sum"] = float(v)
                        except ValueError:
                            pass
            continue
        if kind == "logs":
            if s.startswith("LogRecord #"):
                flush()
                cur = {"_t": "log"}
            elif cur is not None:
                k, _, v = s.partition(": ")
                if k == "ObservedTimestamp":
                    cur["observed"] = _nanos(v)
                elif k == "Timestamp":
                    cur["ts"] = _nanos(v)
                elif k == "SeverityText":
                    cur["sevtext"] = v
                elif k == "SeverityNumber":
                    cur["sevnum"] = v
                elif k == "Body":
                    cur["body"] = _attr_value(v) if v.startswith("Str(") else v
            continue
    flush()
    metrics, exports = metric_series(points)
    return {"spans": dict(spans), "metrics": metrics, "exports": exports, "logs": dict(logs), "stats": dict(stats)}


def _token(name):
    return name.replace(":", "%3A").replace(" ", "_")


def metric_series(points):
    """Data points -> ({service: {resource: [(t_seconds, x)]}}, {service: {metric: [export t_seconds]}}).
    Rules in the module docstring; the export times feed the adapter's absent-export readout only."""
    by = defaultdict(list)
    for q in points:
        by[(q["service"], q["desc"].get("Name", "?"))].append(q)
    out = defaultdict(dict)
    exports = defaultdict(dict)
    for (svc, name), qs in by.items():
        d = qs[0]["desc"]
        dtype = d.get("DataType", "")
        tok = _token(name)
        exports[svc][tok] = sorted({q["ts"] / 1e9 for q in qs})
        if dtype == "Histogram" or dtype == "ExponentialHistogram" or dtype == "Summary" or "count" in qs[0]:
            series = defaultdict(list)
            for q in qs:
                series["|".join(q["attrs"])].append(q)
            cnt, sm, dts = defaultdict(float), defaultdict(float), {}
            delta = d.get("AggregationTemporality") == "Delta"
            for rows in series.values():
                rows.sort(key=lambda q: q["ts"])
                prev = None
                for q in rows:
                    if "count" not in q:
                        continue
                    if delta:
                        if q.get("start") and q["ts"] > q["start"]:
                            cnt[q["ts"]] += q["count"]
                            sm[q["ts"]] += q.get("sum", 0.0)
                            dts[q["ts"]] = (q["ts"] - q["start"]) / 1e9
                    elif prev is not None and q.get("start") == prev.get("start") and q["count"] >= prev["count"] \
                            and q["ts"] > prev["ts"]:
                        cnt[q["ts"]] += q["count"] - prev["count"]
                        sm[q["ts"]] += q.get("sum", 0.0) - prev.get("sum", 0.0)
                        dts[q["ts"]] = (q["ts"] - prev["ts"]) / 1e9
                    prev = q
            out[svc][tok + "~rate"] = sorted((t / 1e9, cnt[t] / dts[t]) for t in cnt if dts.get(t))
            out[svc][tok + "~mean"] = sorted((t / 1e9, sm[t] / cnt[t]) for t in cnt if cnt[t] > 0)
            continue
        monotonic_cum = dtype == "Sum" and d.get("IsMonotonic") == "true" and d.get("AggregationTemporality") != "Delta"
        delta_sum = dtype == "Sum" and d.get("AggregationTemporality") == "Delta"
        acc = defaultdict(float)
        if monotonic_cum:
            series = defaultdict(list)
            for q in qs:
                if "value" in q:
                    series["|".join(q["attrs"])].append(q)
            for rows in series.values():
                rows.sort(key=lambda q: q["ts"])
                for a, b in zip(rows, rows[1:]):
                    if b["ts"] > a["ts"] and b.get("start") == a.get("start") and b["value"] >= a["value"]:
                        acc[b["ts"]] += (b["value"] - a["value"]) / ((b["ts"] - a["ts"]) / 1e9)
        elif delta_sum:
            for q in qs:
                if "value" in q and q.get("start") and q["ts"] > q["start"]:
                    acc[q["ts"]] += q["value"] / ((q["ts"] - q["start"]) / 1e9)
        else:
            for q in qs:
                if "value" in q:
                    acc[q["ts"]] += q["value"]
        out[svc][tok] = sorted((t / 1e9, x) for t, x in acc.items())
    return {s: v for s, v in out.items()}, {s: v for s, v in exports.items()}


def absent_exports(exports, t0, w):
    """Adapter-defined readout (NOT a symptoms.py symbol and not part of the frozen firing rule): a metric's export is
    absent when, with >= MIN_BASELINE exports in [t0, w0) and cadence c = their median gap, an export slot expected at
    t_i + j*c (j >= 1, before the next retained export, or up to w1 after the last one) falls inside the window."""
    out = set()
    for tok, ts in exports.items():
        pre = [t for t in ts if t0 <= t < w[0]]
        if len(pre) < SYM.MIN_BASELINE:
            continue
        c = statistics.median(b - a for a, b in zip(pre, pre[1:]))
        if c <= 0:
            continue
        nxt = ts[1:] + [None]
        for a, b in zip(ts, nxt):
            end = (b - 0.5 * c) if b is not None else w[1]
            j = 1
            while a + j * c <= end and a + j * c <= w[1]:
                if w[0] <= a + j * c:
                    out.add(tok)
                    break
                j += 1
            if tok in out:
                break
    return out


# --------------------------------------------------------------------------- symbols -> sensors

def sensors_of(counter, service):
    """Symbol Counter of one service -> {(family, service, name): kind}."""
    out = {}
    for sym in counter:
        p = sym.split(":")
        if p[0] == "log" and len(p) >= 3 and p[1] == "template" and p[2] != "novel":
            out[("L", service, p[2])] = "log"
        elif p[0] == "metric" and p[-1] not in NON_SYMPTOMS:
            out[("M", service, sym[len("metric:"):].rsplit(":", 1)[0])] = "metric"
        elif p[0] == "span":
            op, ssym = sym[len("span:"):].rsplit(":", 1)
            if ssym in NON_SYMPTOMS:
                continue
            kind = {"error": "error", "latency_high": "latency", "missing_expected": "missing_expected"}.get(ssym, ssym)
            prev = out.get(("T", service, op))
            out[("T", service, op)] = kind if prev is None else "+".join(sorted(set(prev.split("+")) | {kind}))
    return out


@contextlib.contextmanager
def setting(k, floor):
    saved = (SYM.K, SYM.LAT_FLOOR_S)
    SYM.K, SYM.LAT_FLOOR_S = k, floor
    try:
        yield
    finally:
        SYM.K, SYM.LAT_FLOOR_S = saved


def window_bag(parsed, t0, w):
    """{service: Counter} for one window under the current symptoms.K / LAT_FLOOR_S."""
    bag = {}
    for s in sorted(set(parsed["logs"]) | set(parsed["metrics"]) | set(parsed["spans"])):
        c = Counter()
        if s in parsed["logs"]:
            c.update(SYM.log_symbols(parsed["logs"][s], w))
        for resource, series in parsed["metrics"].get(s, {}).items():
            c.update(SYM.metric_symbols(series, resource, t0, w))
        if s in parsed["spans"]:
            c.update(SYM.span_symbols(parsed["spans"][s], t0, w))
        bag[s] = c
    return bag


def fired(parsed, t0, w):
    out = {}
    for s, c in window_bag(parsed, t0, w).items():
        out.update(sensors_of(c, s))
    return out


def margins(parsed, t0, w, target):
    """At the current setting: max shift/threshold over services other than `target`, per family (T latency, M)."""
    best = {"T": None, "M": None}
    for s, spans in parsed["spans"].items():
        if s == target:
            continue
        by = defaultdict(list)
        for t, op, d, _ in spans:
            by[op].append((t, d))
        for op, xs in by.items():
            pre = [d for t, d in xs if t0 <= t < w[0]]
            ins = [d for t, d in xs if SYM.in_window(t, w)]
            if len(pre) >= SYM.MIN_BASELINE and ins:
                m, thr = SYM.robust_threshold(pre, SYM.LAT_FLOOR_S)
                r = (statistics.median(ins) - m) / thr if thr > 0 else math.inf
                if best["T"] is None or r > best["T"][0]:
                    best["T"] = [r, "T:%s:%s" % (s, SYM.op_token(op))]
    for s, res in parsed["metrics"].items():
        if s == target:
            continue
        for name, series in res.items():
            pre = [x for t, x in series if t0 <= t < w[0]]
            ins = [x for t, x in series if SYM.in_window(t, w)]
            if len(pre) >= SYM.MIN_BASELINE and ins:
                m, thr = SYM.robust_threshold(pre, SYM.FLOOR.get(name, SYM.MEM_REL_FLOOR * abs(statistics.median(pre))))
                dev = max(abs(x - m) for x in ins)
                r = dev / thr if thr > 0 else (math.inf if dev > 0 else 0.0)
                if best["M"] is None or r > best["M"][0]:
                    best["M"] = [r, "M:%s:%s" % (s, name)]
    return best


# --------------------------------------------------------------------------- cells

def _json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fault_offsets(iv):
    """(a, b, source) barrier-relative seconds."""
    if iv.get("appliedMonotonicOffsetSeconds") is not None and iv.get("revertingMonotonicOffsetSeconds") is not None:
        return iv["appliedMonotonicOffsetSeconds"], iv["revertingMonotonicOffsetSeconds"], "applied..reverting"
    return iv["actualOnsetMonotonicOffsetSeconds"], iv["actualOffsetMonotonicOffsetSeconds"], "actualOnset..actualOffset"


def load_meta(d):
    """Cheap pass: identity, validity, ledger, fault offsets. Missing inputs are listed, never defaulted."""
    d = Path(d)
    meta = {"dir": d, "cell": "%s/%s" % (d.parent.name, d.name), "regime": d.parent.name, "missing": []}
    try:
        _, _, posture = d.name.split("-", 2)
        meta["block"] = int(d.name[1:3])
    except ValueError:
        posture, meta["block"] = None, None
    meta["posture"] = posture
    rc = _json(d / "receipt.json")
    if rc is None:
        meta["missing"].append("receipt.json")
    meta["valid"] = bool(rc) and rc.get("state") == "valid"
    if rc and rc.get("runKey"):
        meta["posture"] = rc["runKey"].get("posture", posture)
        meta["block"] = rc["runKey"].get("block", meta["block"])
        meta["studyEpoch"] = rc["runKey"].get("studyEpoch")
    try:
        meta["base"], meta["ledgerRows"] = VIS.otel_ledger_rows(d)
    except (OSError, ValueError, KeyError):
        meta["missing"].append("request-ledger.json")
        meta["base"], meta["ledgerRows"] = None, None
    meta["target"], meta["offsets"] = None, None
    if meta["regime"] != NO_FAULT:
        iv = _json(d / "intervention.json")
        if iv is None:
            meta["missing"].append("intervention.json")
        else:
            meta["target"] = iv.get("service")
            meta["scenario"] = iv.get("scenario")
            try:
                meta["offsets"] = fault_offsets(iv)
            except KeyError:
                meta["missing"].append("intervention.json:offsets")
    pp = _json(d / "posture-proof.json")
    meta["proofActive"] = None if pp is None else pp.get("expectedActiveApplicationServices")
    if not (d / "otelcol.log").exists():
        meta["missing"].append("otelcol.log")
    return meta


def ledger_custom(pre, inside, mult, floor_ms):
    """visibility.ledger_rule with its constants (3, 1 ms) as parameters, for the informational ledgerGrid only."""
    pre_ms = [m for m, ok in pre if ok]
    if not pre_ms or not inside:
        return None
    med = statistics.median(pre_ms)
    mad = statistics.median(abs(m - med) for m in pre_ms)
    in_med = statistics.median(m for m, _ in inside)
    failed = sum(1 for _, ok in inside if not ok)
    return failed > 0 or in_med > med + max(mult * mad, floor_ms)


def grid():
    return [(k, f) for k in GRID_K for f in GRID_FLOOR_S]


def skey(k, f):
    return "K=%g,floor=%gms" % (k, f * 1000)


def process_cells(metas, log=lambda *a: None, parse=None):
    """Second pass: per valid cell, parse otelcol.log once and compute fired sensors for every grid setting and
    window. `parse(meta)` returns the parsed telemetry (or None when the carrier is missing)."""
    parse = parse or (lambda m: parse_otelcol(open(m["dir"] / "otelcol.log", encoding="utf-8", errors="replace")))
    fault_regimes = sorted({m["regime"] for m in metas if m["regime"] != NO_FAULT})
    pseudo = {}
    for r in fault_regimes:
        offs = [m["offsets"] for m in metas if m["regime"] == r and m["valid"] and m["offsets"]]
        if offs:
            pseudo[r] = (statistics.median(o[0] for o in offs), statistics.median(o[1] for o in offs))
    for m in metas:
        m["windows"] = {}
        if not m["valid"] or m["base"] is None:
            continue
        if m["regime"] == NO_FAULT:
            for r, (a, b) in pseudo.items():
                m["windows"][r] = (a, b)
        elif m["offsets"]:
            m["windows"][m["regime"]] = m["offsets"][:2]
        m["ledger"] = {}
        m["ledgerGrid"] = {}
        for r, (a, b) in m["windows"].items():
            pre, ins = VIS.split(m["ledgerRows"], a, b)
            m["ledger"][r] = VIS.ledger_rule(pre, ins)
            m["ledgerGrid"][r] = {skey(k, f): ledger_custom(pre, ins, k, f * 1000) for k, f in grid()}
        m["fired"], m["margins"], m["appServicesSeen"], m["absent"] = None, None, None, None
        if "otelcol.log" in m["missing"]:
            continue
        log("  parse %s" % m["cell"])
        parsed = parse(m)
        if parsed is None:
            continue
        m["parseStats"] = parsed.get("stats", {})
        m["appServicesSeen"] = sorted(set(parsed["logs"]) | set(parsed["metrics"]) | set(parsed["spans"]))
        t0 = m["base"]
        m["absent"] = {r: {("M", s, tok) for s, ex in parsed.get("exports", {}).items()
                           for tok in absent_exports(ex, t0, (t0 + a, t0 + b))}
                       for r, (a, b) in m["windows"].items()}
        m["fired"] = {}
        for k, f in grid():
            with setting(k, f):
                m["fired"][skey(k, f)] = {r: fired(parsed, t0, (t0 + a, t0 + b)) for r, (a, b) in m["windows"].items()}
        if m["regime"] != NO_FAULT:
            with setting(*FROZEN):
                a, b = m["windows"][m["regime"]]
                m["margins"] = margins(parsed, t0, (t0 + a, t0 + b), m["target"])
    return pseudo


# --------------------------------------------------------------------------- scoring

def collects(fam, posture):
    return posture in FAMILY_POSTURES[fam]


def inadmissible(metas, key, regime):
    """G3 (lmt_detect.py:151): per family, sensors firing in > TAU x n0 of the regime's no-fault pseudo windows."""
    out = {}
    for fam in FAMILIES:
        nf = [m for m in metas if m["regime"] == NO_FAULT and m.get("fired") is not None and collects(fam, m["posture"])
              and regime in m["fired"][key]]
        counts = Counter(x for m in nf for x in m["fired"][key][regime] if x[0] == fam)
        out[fam] = {"n0": len(nf), "gateCount": TAU * len(nf),
                    "inadmissible": {x for x, n in counts.items() if nf and n > TAU * len(nf)},
                    "noFaultFirings": counts}
    return out


def inadmissible_absent(metas, regime):
    """The same G3 arithmetic on the absent-export readout's no-fault firings (M postures)."""
    nf = [m for m in metas if m["regime"] == NO_FAULT and m.get("absent") is not None and collects("M", m["posture"])
          and regime in m["absent"]]
    counts = Counter(x for m in nf for x in m["absent"][regime])
    return {"n0": len(nf), "inadmissible": {x for x, n in counts.items() if nf and n > TAU * len(nf)},
            "noFaultFirings": counts}


def score(metas, key):
    """Per fault regime: episodes with outside/own catches per family (G2 + G3), per-sensor counts."""
    res = {}
    for regime in sorted({m["regime"] for m in metas if m["regime"] != NO_FAULT}):
        gate = inadmissible(metas, key, regime)
        gate_abs = inadmissible_absent(metas, regime)
        eps = []
        for m in metas:
            if m["regime"] != regime or not m["valid"] or m.get("ledger") is None:
                continue
            e = {"cell": m["cell"], "posture": m["posture"], "block": m["block"], "target": m["target"],
                 "ledger": m["ledger"].get(regime), "families": {}}
            f = None if m.get("fired") is None else m["fired"][key].get(regime)
            for fam in FAMILIES:
                if not collects(fam, m["posture"]) or f is None:
                    e["families"][fam] = None              # not collected / carrier missing: unknown, not zero
                    continue
                bad = gate[fam]["inadmissible"]
                out = {x: k for x, k in f.items() if x[0] == fam and x[1] != m["target"] and x not in bad}
                own = {x: k for x, k in f.items() if x[0] == fam and x[1] == m["target"] and x not in bad}
                own_raw = {x: k for x, k in f.items() if x[0] == fam and x[1] == m["target"]}
                e["families"][fam] = {"outside": out, "own": own, "ownNoG3": own_raw,
                                      "droppedByG3Outside": sorted(":".join(x) for x in f if x[0] == fam and
                                                                   x[1] != m["target"] and x in bad)}
                if fam == "M":
                    ab = (m.get("absent") or {}).get(regime, set())
                    e["families"][fam]["absentOutside"] = {x: "absent" for x in ab if x[1] != m["target"]
                                                           and x not in gate_abs["inadmissible"]}
                    e["families"][fam]["absentOwn"] = {x: "absent" for x in ab if x[1] == m["target"]
                                                       and x not in gate_abs["inadmissible"]}
                    e["families"][fam]["absentOwnNoG3"] = {x: "absent" for x in ab if x[1] == m["target"]}
            e["margins"] = m.get("margins")
            eps.append(e)
        res[regime] = {"episodes": eps, "g3": gate, "g3Absent": gate_abs}
    return res


def _fmt(x):
    return ":".join(x)


def posture_summary(regime_res):
    """Per posture: ledger k/n, per family outside/own k/n, per-sensor outside counts, symbol kinds behind catches."""
    out = {}
    for p in POSTURES:
        eps = [e for e in regime_res["episodes"] if e["posture"] == p]
        if not eps:
            continue
        known = [e for e in eps if e["ledger"] is not None]
        row = {"episodes": len(eps),
               "ledger": {"shows": sum(1 for e in known if e["ledger"]["shows"]), "n": len(known),
                          "unknown": len(eps) - len(known)},
               "families": {}, "outsideSensors": {}, "outsideKinds": {}, "anyOutside": None}
        any_k, any_n = 0, 0
        sens = Counter()
        kinds = Counter()
        for fam in FAMILIES:
            scored = [e for e in eps if e["families"][fam] is not None]
            if not scored:
                row["families"][fam] = "—"
                continue
            row["families"][fam] = {
                "n": len(scored),
                "outside": sum(1 for e in scored if e["families"][fam]["outside"]),
                "own": sum(1 for e in scored if e["families"][fam]["own"]),
                "ownNoG3": sum(1 for e in scored if e["families"][fam]["ownNoG3"]),
            }
            for e in scored:
                for x, k in e["families"][fam]["outside"].items():
                    sens[_fmt(x)] += 1
                    for kk in k.split("+"):
                        kinds["%s:%s" % (fam, kk)] += 1
        scored_any = [e for e in eps if any(e["families"][f] is not None for f in FAMILIES)]
        if scored_any:
            any_n = len(scored_any)
            any_k = sum(1 for e in scored_any if any(e["families"][f] and e["families"][f]["outside"] for f in FAMILIES))
            row["anyOutside"] = {"k": any_k, "n": any_n}
        row["outsideSensors"] = dict(sens.most_common())
        row["outsideKinds"] = dict(sorted(kinds.items()))
        out[p] = row
    return out


def yn(flag):
    return "—" if flag is None else ("yes" if flag else "no")


def per_sensor_counts(eps, fams, service_ok, own=False, absent=False):
    c = Counter()
    for e in eps:
        hits = set()
        for fam in fams:
            v = e["families"].get(fam)
            if v is None:
                continue
            for x in (v["own"] if own else v["outside"]):
                if service_ok(x[1]):
                    hits.add(x)
            if absent and fam == "M":
                for x in (v["absentOwn"] if own else v["absentOutside"]):
                    if service_ok(x[1]):
                        hits.add(x)
        c.update(hits)
    return c


def _any_outside(e, absent=False):
    return any(e["families"][f] and (e["families"][f]["outside"] or (absent and f == "M" and e["families"][f]["absentOutside"]))
               for f in FAMILIES)


def k_readings(rr, regime):
    """K1-K4 for one off-path fault regime; the target is read from the episodes' intervention.json `service`."""
    targets = Counter(e["target"] for e in rr["episodes"])
    target = targets.most_common(1)[0][0] if targets else None
    fraud = regime == FRAUD
    P = {"target": target, "targets": dict(targets)}
    per = {}
    for p in POSTURES:
        eps = [e for e in rr["episodes"] if e["posture"] == p and e["ledger"] is not None]
        k = sum(1 for e in eps if e["ledger"]["shows"])
        per[p] = {"shows": k, "n": len(eps), "reading": "—" if not eps else yn(k <= 1)}
    reads = [v["reading"] for v in per.values()]
    P["K1"] = {"perPosture": per, "reading": "no" if "no" in reads else "—" if "—" in reads else "yes",
               "byConstruction": fraud,
               "rule": "ledger rule shows the fault in <= 1 of 3 cells, every posture"}

    def scored(posture):
        return [e for e in rr["episodes"] if e["posture"] == posture
                and any(e["families"][f] is not None for f in FAMILIES)]
    eps = scored("selected")
    if not eps:
        P["K2"] = {"reading": "—", "why": "no scored selected episode", "byConstruction": fraud}
    else:
        c = per_sensor_counts(eps, FAMILIES, lambda s: True)
        ca = per_sensor_counts(eps, FAMILIES, lambda s: True, absent=True)
        anyk = sum(1 for e in eps if _any_outside(e))
        P["K2"] = {"n": len(eps), "byConstruction": fraud,
                   "perSensor": {"reading": yn(not any(k >= 2 for k in c.values())),
                                 "topSensors": [[_fmt(x), k] for x, k in c.most_common(5)]},
                   "anySensorPerEpisode": {"k": anyk, "n": len(eps), "reading": yn(anyk < 2)},
                   "withAbsentExports": {"reading": yn(not any(k >= 2 for k in ca.values())),
                                         "topSensors": [[_fmt(x), k] for x, k in ca.most_common(5)]},
                   "reading": yn(not any(k >= 2 for k in c.values())),
                   "maxShiftOverThreshold": [{"cell": e["cell"], "T": (e["margins"] or {}).get("T"),
                                              "M": (e["margins"] or {}).get("M")} for e in eps],
                   "rule": "no outside sensor of selected fires in >= 2 of the n episodes (n = 3 declared)"}
    eps = scored("async")
    if not eps:
        P["K3"] = {"reading": "—", "why": "no scored async episode"}
    else:
        lit = per_sensor_counts(eps, FAMILIES, lambda s: s != target)
        rst = per_sensor_counts(eps, FAMILIES, lambda s: s in K3_RESTRICTED and s != target)
        kaf = per_sensor_counts(eps, FAMILIES, lambda s: s == "kafka" and s != target)
        acc = per_sensor_counts(eps, FAMILIES, lambda s: s == "accountingservice" and s != target)
        lit_a = per_sensor_counts(eps, FAMILIES, lambda s: s != target, absent=True)
        anyk = sum(1 for e in eps if _any_outside(e))
        P["K3"] = {"n": len(eps),
                   "literal": {"reading": yn(any(k >= 2 for k in lit.values())),
                               "topSensors": [[_fmt(x), k] for x, k in lit.most_common(5)],
                               "rule": "a sensor of async on any service other than the target"},
                   "restricted": {"reading": yn(any(k >= 2 for k in rst.values())),
                                  "topSensors": [[_fmt(x), k] for x, k in rst.most_common(5)],
                                  "rule": "a sensor of kafka or accountingservice"},
                   "kafka": {"reading": yn(any(k >= 2 for k in kaf.values())),
                             "topSensors": [[_fmt(x), k] for x, k in kaf.most_common(5)]},
                   "accountingservice": {"measured": yn(any(k >= 2 for k in acc.values())),
                                         "topSensors": [[_fmt(x), k] for x, k in acc.most_common(5)],
                                         "byConstruction": "no (erratum 2: separate consumer group)" if fraud else None},
                   "withAbsentExports": {"reading": yn(any(k >= 2 for k in lit_a.values())),
                                         "topSensors": [[_fmt(x), k] for x, k in lit_a.most_common(5)]},
                   "anySensorPerEpisode": {"k": anyk, "n": len(eps), "reading": yn(anyk >= 2)},
                   "reading": yn(any(k >= 2 for k in lit.values()))}
    per = {}
    for p in ("async", "full"):
        eps = scored(p)
        if not eps:
            per[p] = {"reading": "—", "n": 0}
            continue
        k = sum(1 for e in eps if any(e["families"][f] and e["families"][f]["own"] for f in ("T", "M")))
        kr = sum(1 for e in eps if any(e["families"][f] and e["families"][f]["ownNoG3"] for f in ("T", "M")))
        ka = sum(1 for e in eps if any(e["families"][f] and (e["families"][f]["own"] or (f == "M" and e["families"][f]["absentOwn"]))
                                       for f in ("T", "M")))
        per[p] = {"k": k, "n": len(eps), "kWithoutG3": kr, "kWithAbsentExports": ka, "reading": yn(k >= 2)}
    reads = [v["reading"] for v in per.values()]
    P["K4"] = {"perPosture": per, "byConstruction": True,
               "reading": "no" if "no" in reads else "—" if "—" in reads else "yes"}
    return P


def predictions(res, _unused=()):
    """C1 on frontend-pause; K1-K4 per off-path regime (every fault regime but frontend-pause, targets read from
    intervention.json). Top-level K1-K4 = fraud-pause when present, else the single off-path regime, else `—`."""
    P = {}
    fe = res.get(FRONTEND)
    if fe is None:
        P["C1"] = {"reading": "—", "why": "no %s episodes" % FRONTEND}
    else:
        per = {}
        for p in POSTURES:
            eps = [e for e in fe["episodes"] if e["posture"] == p and e["ledger"] is not None]
            k = sum(1 for e in eps if e["ledger"]["shows"])
            per[p] = {"shows": k, "n": len(eps), "reading": "—" if not eps else yn(len(eps) == 3 and k == 3)}
        reads = [v["reading"] for v in per.values()]
        tot = sum(v["shows"] for v in per.values()), sum(v["n"] for v in per.values())
        P["C1"] = {"perPosture": per, "total": {"shows": tot[0], "n": tot[1]},
                   "reading": "no" if "no" in reads else "—" if "—" in reads else "yes"}
    offs = sorted(r for r in res if r != FRONTEND)
    P["offPath"] = {r: k_readings(res[r], r) for r in offs}
    primary = FRAUD if FRAUD in res else (offs[0] if len(offs) == 1 else None)
    P["primaryRegime"] = primary
    for k in ("K1", "K2", "K3", "K4"):
        P[k] = P["offPath"][primary][k] if primary else {
            "reading": "—", "why": "no off-path fault regime in this evidence" if not offs else
            "several off-path regimes %s: read offPath" % offs}
    return P


def ledger_grid(metas):
    """K1/C1-style ledger counts with the ledger rule's own constants varied (informational, not frozen)."""
    out = {}
    for k, f in grid():
        key = skey(k, f)
        row = {}
        for regime in (FRAUD, FRONTEND):
            per = {}
            for p in POSTURES:
                vals = [m["ledgerGrid"][regime][key] for m in metas if m["regime"] == regime and m["posture"] == p
                        and m.get("ledgerGrid") and m["ledgerGrid"].get(regime, {}).get(key) is not None]
                if vals:
                    per[p] = [sum(1 for v in vals if v), len(vals)]
            if per:
                row[regime] = per
        out[key.replace("K=", "mult=")] = row
    return out


G3_CLIFF = ("G3 inadmissibility is `fired in > TAU x n0 no-fault windows` with TAU = 0.05 (lmt_detect.py:151): for any "
            "n0 < 20 the gate TAU x n0 is below 1, so a single no-fault firing makes a sensor inadmissible. With 3 no-fault "
            "windows per posture (n0 = 3 for a posture-specific reading, n0 = 9 pooled over selected/async/full as here), "
            "one firing in one window removes the sensor from every episode of the regime.")


def run(root, out_path=None, log=lambda *a: None):
    root = Path(root).resolve()
    runs = root / "runs"
    regimes = tuple(sorted(p.name for p in runs.iterdir() if p.is_dir())) if runs.is_dir() else ()
    if NO_FAULT not in regimes:
        raise SystemExit("no %s regime under %s" % (NO_FAULT, runs))
    metas = [load_meta(d) for r in regimes for d in sorted((runs / r).iterdir()) if d.is_dir()]
    # layout = the receipts' study epoch (any number of fault regimes is accepted); fallback: the regime set
    epochs = {m.get("studyEpoch") for m in metas if m.get("studyEpoch")}
    layout = next(iter(epochs)) if len(epochs) == 1 and next(iter(epochs)) in LAYOUTS else None
    how = "receipt runKey.studyEpoch"
    if layout is None:
        layout = next((k for k, v in LAYOUTS.items() if v["regimes"] == regimes), None)
        how = "regime directory set"
    if layout is None:
        raise SystemExit("unknown layout: epochs %s, regimes %s match no table (%s)" % (sorted(epochs), regimes, sorted(LAYOUTS)))
    closures = LAYOUTS[layout]["closures"]
    # integrity: the closure table must equal what the harness recorded; the carrier must equal its manifest digest
    closure_check, digest_check = [], []
    for m in metas:
        if m["proofActive"] is not None and list(m["proofActive"]) != sorted(closures[m["posture"]]):
            closure_check.append(m["cell"])
        man = _json(m["dir"] / "content-manifest.json")
        if man and (m["dir"] / "otelcol.log").exists():
            want = {r["path"]: r["sha256"] for r in man.get("files", [])}.get("otelcol.log")
            digest_check.append((m["cell"], want is not None and want == _sha256(m["dir"] / "otelcol.log")))
    if closure_check:
        raise SystemExit("closure table %s differs from posture-proof.json in %s" % (layout, closure_check[:3]))
    pseudo = process_cells(metas, log=log)
    frozen_key = skey(*FROZEN)
    results = {}
    for k, f in grid():
        key = skey(k, f)
        res = score(metas, key)
        results[key] = {"predictions": predictions(res),
                        "perRegime": {r: posture_summary(v) for r, v in res.items()}}
        if key == frozen_key:
            frozen_res = res
    # cross-check against visibility.json (v3 layout only: the committed map has otel-v3 ledger episodes)
    xcheck = None
    vis = _json(VISIBILITY_PATH.parent / "visibility.json")
    if vis and layout == "otel-demo-candidate-pilot-v3":
        theirs = {Path(e["cell"]).parent.name + "/" + Path(e["cell"]).name: e["ledger"]
                  for e in vis["populations"]["otel-v3"]["episodes"]}
        mine = {m["cell"]: m["ledger"].get(m["regime"]) for m in metas if m["regime"] != NO_FAULT and m.get("ledger")}
        agree = sum(1 for c in mine if c in theirs and theirs[c] == mine[c])
        nf_mine = [m["ledger"][FRONTEND] for m in metas if m["regime"] == NO_FAULT and m.get("ledger")]
        xcheck = {"against": "research/visibility-map/visibility.json populations.otel-v3",
                  "episodesEqual": [agree, len(mine)], "visibilityEpisodes": len(theirs),
                  "noFaultLedgerFalseAlarms": {"mine": [sum(1 for r in nf_mine if r and r["shows"]), len(nf_mine)],
                                               "visibility": vis["populations"]["otel-v3"]["ledgerFalseAlarms"]}}
    fe = [m for m in metas if m["regime"] == FRONTEND and m.get("ledger")]
    stop = {"rule": "DECLARATION.md stop rule 2026-10-06: the adapter replays v3r1's frontend-pause cells as "
                    "ledger-visible 12/12",
            "frontendPauseLedgerVisible": [sum(1 for m in fe if m["ledger"][FRONTEND] and m["ledger"][FRONTEND]["shows"]),
                                           len(fe)]}
    g3_frozen = {r: dict({fam: {"n0": v["n0"], "gate": v["gateCount"],
                                "inadmissible": sorted(_fmt(x) for x in v["inadmissible"])}
                          for fam, v in res["g3"].items()},
                         absentExports={"n0": res["g3Absent"]["n0"],
                                        "inadmissible": sorted(_fmt(x) for x in res["g3Absent"]["inadmissible"])})
                 for r, res in frozen_res.items()}
    assertions = replay_assertions(layout, frozen_res)
    out = {
        "adapter": "research/otel-offpath/adapter.py", "adapterSha256": _sha256(__file__),
        "imports": {str(p.relative_to(REPO)): _sha256(p) for p in (SYMPTOMS_PATH, VISIBILITY_PATH, LMT_PATH)},
        "frameworkCommit": _git(), "python": sys.version.split()[0],
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "evidence": str(root), "layout": layout, "layoutDetectedBy": how, "layoutSource": LAYOUTS[layout]["source"],
        "regimes": list(regimes),
        "faultScenarios": {r: sorted({"%s -> %s" % (m.get("scenario"), m["target"]) for m in metas if m["regime"] == r})
                           for r in regimes if r != NO_FAULT},
        "closures": {p: list(v) for p, v in closures.items()},
        "frozenSetting": {"K": FROZEN[0], "latFloorS": FROZEN[1], "tau": TAU, "ledger": "max(3 x MAD, 1 ms)"},
        "defaults": DEFAULTS, "g3Cliff": G3_CLIFF,
        "g3Definition": "research/lmt-pilot/lmt_detect.py:151 `inadmissible = {x for x, n in fa_counts.items() if nf and n > "
                        "TAU * len(nf)}` (TAU = 0.05, :36); paper: papers/current/lncs/paper.tex:411-413",
        "g2Definition": "research/lmt-pilot/lmt_detect.py:159 `x[1] != c[\"target\"]`; paper.tex:410",
        "cells": {"total": len(metas), "valid": sum(1 for m in metas if m["valid"]),
                  "missingInputs": {m["cell"]: m["missing"] for m in metas if m["missing"]},
                  "carrierDigestEqualsManifest": [sum(1 for _, ok in digest_check if ok), len(digest_check)],
                  "noneCellsWithApplicationTelemetry": sorted(m["cell"] for m in metas if m["posture"] == "none"
                                                              and m.get("appServicesSeen"))},
        "pseudoWindows": {r: list(v) for r, v in pseudo.items()},
        "stopRule": stop,
        "replayAssertions": assertions,
        "visibilityCrossCheck": xcheck,
        "frozen": results[frozen_key],
        "g3Frozen": g3_frozen,
        "grid": {k: {"predictions": {pk: v["predictions"][pk].get("reading") for pk in ("K1", "K2", "K3", "K4", "C1")},
                     "offPath": {r: {pk: pv[pk].get("reading") for pk in ("K1", "K2", "K3", "K4")}
                                 for r, pv in v["predictions"]["offPath"].items()},
                     "K2perSensor": v["predictions"].get("K2", {}).get("perSensor", {}).get("reading"),
                     "K2anySensor": v["predictions"].get("K2", {}).get("anySensorPerEpisode", {}).get("reading"),
                     "K3restricted": v["predictions"].get("K3", {}).get("restricted", {}).get("reading"),
                     "perRegimeAnyOutside": {r: {p: row["anyOutside"] for p, row in pr.items()}
                                             for r, pr in v["perRegime"].items()}}
                 for k, v in results.items()},
        "ledgerGrid": ledger_grid(metas),
        "episodes": [{"cell": e["cell"], "regime": r, "posture": e["posture"], "block": e["block"], "target": e["target"],
                      "ledger": e["ledger"], "margins": e["margins"],
                      "families": {f: (None if v is None else {"outside": sorted(_fmt(x) + "=" + k for x, k in v["outside"].items()),
                                                               "own": sorted(_fmt(x) + "=" + k for x, k in v["own"].items()),
                                                               "ownNoG3": sorted(_fmt(x) for x in v["ownNoG3"]),
                                                               "droppedByG3Outside": v["droppedByG3Outside"],
                                                               "absentOutside": sorted(_fmt(x) for x in v.get("absentOutside", {})),
                                                               "absentOwn": sorted(_fmt(x) for x in v.get("absentOwn", {})),
                                                               "absentOwnNoG3": sorted(_fmt(x) for x in v.get("absentOwnNoG3", {}))})
                                   for f, v in e["families"].items()}}
                     for r, res in frozen_res.items() for e in res["episodes"]],
    }
    if out_path is None:
        out_path = HERE / "out" / ("adapter-%s-%s.json" % (root.name, out["generatedAt"]))
    out_path = Path(out_path)
    if out_path.exists():
        raise SystemExit("refusing to overwrite %s" % out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")
    return out, out_path


REPLAY_ASSERTIONS = {
    # erratum 2: frontend's http.server.duration exports are absent at 06:09:33 and 06:10:33, inside the pause
    # 06:08:43..06:11:19 of this v3r1 cell; the adapter must report an absent-export symbol for frontend there.
    "otel-demo-candidate-pilot-v3": [
        ("frontend http.server.duration export gap in %s/b01-01-async" % FRONTEND, FRONTEND,
         "%s/b01-01-async" % FRONTEND, ("M", "frontend", "http.server.duration")),
    ],
}


def replay_assertions(layout, frozen_res):
    out = {}
    for name, regime, cell, sensor in REPLAY_ASSERTIONS.get(layout, []):
        e = next((x for x in frozen_res.get(regime, {}).get("episodes", []) if x["cell"] == cell), None)
        m = None if e is None else e["families"].get("M")
        ok = m is not None and sensor in m.get("absentOwnNoG3", {})
        out[name] = {"sensor": _fmt(sensor), "kind": "absent", "pass": ok,
                     "absentOwnAfterG3": None if m is None else sensor in m.get("absentOwn", {})}
        if not ok:
            raise SystemExit("replay assertion failed: %s" % name)
    return out


def _git():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO), capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def headline(out):
    f = out["frozen"]["predictions"]
    lines = ["layout %s; cells %d valid %d; stop rule frontend-pause ledger-visible %d/%d" % (
        out["layout"], out["cells"]["total"], out["cells"]["valid"], *out["stopRule"]["frontendPauseLedgerVisible"])]
    for k in ("K1", "K2", "K3", "K4", "C1"):
        lines.append("  %s: %s" % (k, f[k].get("reading")))
    for r, pr in out["frozen"]["perRegime"].items():
        for p, row in pr.items():
            fam = " ".join("%s %s" % (x, "—" if row["families"][x] == "—" else "%d/%d out, %d/%d own" % (
                row["families"][x]["outside"], row["families"][x]["n"], row["families"][x]["own"], row["families"][x]["n"]))
                for x in FAMILIES)
            lines.append("  %s %-8s ledger %d/%d | %s" % (r, p, row["ledger"]["shows"], row["ledger"]["n"], fam))
    if out.get("visibilityCrossCheck"):
        lines.append("  visibility.json cross-check: %s" % json.dumps(out["visibilityCrossCheck"]))
    return "\n".join(lines)


# --------------------------------------------------------------------------- self-check (planted defects)

FIXTURE_LOG = """otelcol-1  | 2026-09-30T06:30:12.632Z\tinfo\tservice@v0.108.1/service.go:178\tSetting up own telemetry...
otelcol-1  | 2026-09-30T06:30:19.453Z\tinfo\tResourceSpans #0
otelcol-1  | Resource SchemaURL:
otelcol-1  | Resource attributes:
otelcol-1  |      -> service.name: Str(frontend-proxy)
otelcol-1  | ScopeSpans #0
otelcol-1  | InstrumentationScope envoy 1.0
otelcol-1  | Span #0
otelcol-1  |     Trace ID       : 727b1130d212612be46d708837ca2a03
otelcol-1  |     Name           : ingress
otelcol-1  |     Start time     : 2026-09-30 06:30:14.399 +0000 UTC
otelcol-1  |     End time       : 2026-09-30 06:30:14.401500000 +0000 UTC
otelcol-1  |     Status code    : Error
otelcol-1  | Attributes:
otelcol-1  |      -> peer.ipv4: Str(0.0.0.0)
otelcol-1  | 2026-09-30T06:30:19.500Z\tinfo\tResourceSpans #0
otelcol-1  | Resource attributes:
otelcol-1  |      -> service.name: Str(otelcol)
otelcol-1  | ScopeSpans #0
otelcol-1  | Span #0
otelcol-1  |     Name           : self
otelcol-1  |     Start time     : 2026-09-30 06:30:14.399 +0000 UTC
otelcol-1  |     End time       : 2026-09-30 06:30:14.401 +0000 UTC
otelcol-1  |     Status code    : Unset
otelcol-1  | 2026-09-30T06:31:15.928Z\tinfo\tResourceMetrics #0
otelcol-1  | Resource attributes:
otelcol-1  |      -> telemetry.sdk.language: Str(nodejs)
otelcol-1  |      -> service.name: Str(frontend)
otelcol-1  | ScopeMetrics #0
otelcol-1  | InstrumentationScope @opentelemetry/instrumentation-http 0.52.1
otelcol-1  | Metric #0
otelcol-1  | Descriptor:
otelcol-1  |      -> Name: http.server.requests
otelcol-1  |      -> DataType: Sum
otelcol-1  |      -> IsMonotonic: true
otelcol-1  |      -> AggregationTemporality: Cumulative
otelcol-1  | NumberDataPoints #0
otelcol-1  | Data point attributes:
otelcol-1  |      -> code: Int(200)
otelcol-1  | StartTimestamp: 2026-09-30 06:30:00 +0000 UTC
otelcol-1  | Timestamp: 2026-09-30 06:31:00 +0000 UTC
otelcol-1  | Value: 60
otelcol-1  | NumberDataPoints #1
otelcol-1  | Data point attributes:
otelcol-1  |      -> code: Int(200)
otelcol-1  | StartTimestamp: 2026-09-30 06:30:00 +0000 UTC
otelcol-1  | Timestamp: 2026-09-30 06:32:00 +0000 UTC
otelcol-1  | Value: 180
otelcol-1  | Metric #1
otelcol-1  | Descriptor:
otelcol-1  |      -> Name: http.server.duration
otelcol-1  |      -> DataType: Histogram
otelcol-1  |      -> AggregationTemporality: Cumulative
otelcol-1  | HistogramDataPoints #0
otelcol-1  | Data point attributes:
otelcol-1  |      -> http.method: Str(GET)
otelcol-1  | StartTimestamp: 2026-09-30 06:30:00 +0000 UTC
otelcol-1  | Timestamp: 2026-09-30 06:31:00 +0000 UTC
otelcol-1  | Count: 10
otelcol-1  | Sum: 100.0
otelcol-1  | HistogramDataPoints #1
otelcol-1  | Data point attributes:
otelcol-1  |      -> http.method: Str(GET)
otelcol-1  | StartTimestamp: 2026-09-30 06:30:00 +0000 UTC
otelcol-1  | Timestamp: 2026-09-30 06:32:00 +0000 UTC
otelcol-1  | Count: 30
otelcol-1  | Sum: 500.0
otelcol-1  | Buckets #0, Count: 0
otelcol-1  | 2026-09-30T06:31:07.030Z\tinfo\tResourceLog #0
otelcol-1  | Resource attributes:
otelcol-1  |      -> telemetry.sdk.language: Str(python)
otelcol-1  |      -> service.name: Str(loadgenerator)
otelcol-1  | ScopeLogs #0
otelcol-1  | InstrumentationScope opentelemetry.sdk._logs._internal
otelcol-1  | LogRecord #0
otelcol-1  | ObservedTimestamp: 2026-09-30 06:31:02.992472407 +0000 UTC
otelcol-1  | Timestamp: 2026-09-30 06:31:02.992372992 +0000 UTC
otelcol-1  | SeverityText: INFO
otelcol-1  | SeverityNumber: Error(17)
otelcol-1  | Body: Str(GET / 5 failed id 42 | ERROR in text)
otelcol-1  | Trace ID:
otelcol-1  | LogRecord #1
otelcol-1  | ObservedTimestamp: 2026-09-30 06:31:03.000000000 +0000 UTC
otelcol-1  | Timestamp: 1970-01-01 00:00:00 +0000 UTC
otelcol-1  | SeverityText: ERROR
otelcol-1  | SeverityNumber: Info(9)
otelcol-1  | Body: Str(ERROR in body at info)
otelcol-1  | 2026-09-30T06:31:08.000Z\tinfo\tResourceSpans #0
otelcol-1  | Resource attributes:
otelcol-1  |      -> service.name: Str(mystery)
otelcol-1  | ScopeSpans #0
otelcol-1  | Span #0
otelcol-1  |     Name           : x
otelcol-1  |     Start time     : 2026-09-30 06:30:14 +0000 UTC
otelcol-1  |     End time       : 2026-09-30 06:30:15 +0000 UTC
otelcol-1  |     Status code    : Unset
"""


def _fx_parsed(t0, spans_by_svc):
    return {"spans": spans_by_svc, "metrics": {}, "logs": {}, "stats": {}}


def _fx_meta(cell, regime, posture, block, target, offsets, rows, base=1_790_000_000.0, missing=()):
    return {"dir": Path("/nonexistent") / cell, "cell": cell, "regime": regime, "posture": posture, "block": block,
            "valid": True, "base": base, "ledgerRows": rows, "target": target,
            "offsets": None if offsets is None else (offsets[0], offsets[1], "applied..reverting"),
            "missing": list(missing), "proofActive": None}


def self_check():
    failures = []

    def check(name, cond):
        print("  %-72s %s" % (name, "ok" if cond else "FAILED"))
        if not cond:
            failures.append(name)

    # 1 parser: alias, collector exclusion, unknown service, span error/duration, monotonic sum rate, histogram, severity
    p = parse_otelcol(FIXTURE_LOG.splitlines())
    check("parser: frontend-proxy -> frontendproxy, otelcol and unknown excluded",
          set(p["spans"]) == {"frontendproxy"} and p["stats"].get("collectorResources") == 1
          and p["stats"].get("unknown:mystery") == 1)
    sp = p["spans"]["frontendproxy"][0]
    check("parser: span name, error status, duration from integer nanoseconds",
          sp[1] == "ingress" and sp[3] is True and abs(sp[2] - 0.0025) < 1e-9)
    m = p["metrics"]["frontend"]
    check("parser: monotonic cumulative sum -> rate 2.0/s at the second export",
          m["http.server.requests"] == [(1790749920.0, 2.0)])
    check("parser: histogram -> ~rate (20/60 s) and ~mean (400/20)",
          m["http.server.duration~rate"] == [(1790749920.0, 20 / 60)] and m["http.server.duration~mean"] == [(1790749920.0, 20.0)])
    lg = p["logs"]["loadgenerator"]
    check("parser: level from SeverityNumber, not body text; SeverityText ignored when the number is set",
          lg[0]["level"] == "error" and lg[1]["level"] is None and lg[1]["t"] == 1790749863.0)
    # 2 ledger rule: failed in-window request must show; a shuffled (moved) window must not
    rows = [(float(i), 20.0 + (i % 3), True) for i in range(600)]
    rows_f = [(s, ms, ok and not (50 <= s <= 60)) for s, ms, ok in rows]
    check("ledger: failed in-window requests show", VIS.ledger_rule(*VIS.split(rows_f, 45, 60))["shows"] is True)
    check("ledger: the same cell with the window moved to a quiet period does not show",
          VIS.ledger_rule(*VIS.split(rows_f, 300, 315))["shows"] is False)
    # 3-6 scoring over planted cells: fraud-pause, 3 posture x 3 blocks + no-fault calibration
    t0 = 1_790_000_000.0

    def spans(svc_ops, slow=None, missing_in=None, noisy_nf=False):
        out = {}
        for svc, op in svc_ops:
            xs = []
            for i in range(120):
                d = 0.010 + 0.001 * (i % 5)          # pre median 12 ms, MAD 1 ms, s = 1.4826 ms
                if slow and (svc, op) == slow and 45 <= i <= 60:
                    d = 0.0185                          # shift 6.5 ms: >= 3s (4.45) and 4s (5.93), < 5s (7.41)
                if missing_in and (svc, op) == missing_in and 45 <= i <= 60:
                    continue
                xs.append((t0 + i + 0.5, op, d, False))
            out.setdefault(svc, []).extend(xs)
        return out

    ops = [("checkoutservice", "PlaceOrder"), ("frauddetectionservice", "orders process"),
           ("accountingservice", "orders process"), ("cartservice", "GetCart")]
    metas, parsed = [], {}
    for b in (1, 2, 3):
        for post in ("selected", "async", "full"):
            c = "%s/b%02d-%s" % (FRAUD, b, post)
            mt = _fx_meta(c, FRAUD, post, b, FRAUD_TARGET, (45.0, 60.0), rows)
            metas.append(mt)
            # target's own op goes missing (G2 must keep it out of `outside`); a K-sensitive slow-down on checkout
            parsed[c] = _fx_parsed(t0, spans(ops, slow=("checkoutservice", "PlaceOrder"),
                                             missing_in=("frauddetectionservice", "orders process")))
            cn = "%s/b%02d-%s" % (NO_FAULT, b, post)
            metas.append(_fx_meta(cn, NO_FAULT, post, b, None, None, rows))
            # planted G3 noise: cartservice GetCart is slow inside the pseudo window of one no-fault cell
            parsed[cn] = _fx_parsed(t0, spans(ops, slow=("cartservice", "GetCart") if (b, post) == (1, "full") else None))
    for mt in metas:      # cartservice also slow in every fault cell: only G3 can remove it
        if mt["regime"] == FRAUD:
            parsed[mt["cell"]] = _fx_parsed(t0, spans(ops, slow=("cartservice", "GetCart"),
                                                      missing_in=("frauddetectionservice", "orders process")))
            for svc, xs in spans([("checkoutservice", "PlaceOrder")], slow=("checkoutservice", "PlaceOrder")).items():
                parsed[mt["cell"]]["spans"][svc] = xs
    # a no-fault none cell and a fault cell whose carrier is missing
    metas.append(_fx_meta("%s/b01-none" % FRAUD, FRAUD, "none", 1, FRAUD_TARGET, (45.0, 60.0), rows, missing=("otelcol.log",)))
    process_cells(metas, parse=lambda mt: parsed.get(mt["cell"]))
    res = score(metas, skey(*FROZEN))
    ep = {e["cell"]: e for e in res[FRAUD]["episodes"]}
    e = ep["%s/b01-async" % FRAUD]
    check("G2: the target's own missing span is own, never outside",
          ("T", FRAUD_TARGET, "orders_process") in e["families"]["T"]["ownNoG3"]
          and all(x[1] != FRAUD_TARGET for x in e["families"]["T"]["outside"]))
    check("G3: cartservice GetCart (slow in 1 of 9 no-fault windows) is inadmissible and dropped",
          ("T", "cartservice", "GetCart") in res[FRAUD]["g3"]["T"]["inadmissible"]
          and ("T", "cartservice", "GetCart") not in e["families"]["T"]["outside"]
          and "T:cartservice:GetCart" in e["families"]["T"]["droppedByG3Outside"])
    check("missing carrier: families of that cell are unknown (None), not zero",
          ep["%s/b01-none" % FRAUD]["families"]["T"] is None)
    # 7 grid: the planted checkout shift (median +6.5 ms over s = 1.4826 ms) fires at K=3 and K=4, not K=5
    r3, r5 = score(metas, skey(3.0, 0.001)), score(metas, skey(5.0, 0.001))
    k3 = ("T", "checkoutservice", "PlaceOrder") in {x for x in
                                                    next(x for x in r3[FRAUD]["episodes"] if x["posture"] == "selected")["families"]["T"]["outside"]}
    k5 = ("T", "checkoutservice", "PlaceOrder") in {x for x in
                                                    next(x for x in r5[FRAUD]["episodes"] if x["posture"] == "selected")["families"]["T"]["outside"]}
    check("grid: a planted shift fires at K=3 and not at K=5", k3 and not k5)
    P3, P5 = predictions(r3, ()), predictions(r5, ())
    check("grid: K2 reads no at K=3 (sensor in 3/3) and yes at K=5", P3["K2"]["reading"] == "no" and P5["K2"]["reading"] == "yes")
    check("symbol kind: the K=3 catch is a latency symbol",
          P3["K2"]["perSensor"]["topSensors"][0][0] == "T:checkoutservice:PlaceOrder"
          and next(x for x in r3[FRAUD]["episodes"] if x["posture"] == "selected")["families"]["T"]["outside"][
              ("T", "checkoutservice", "PlaceOrder")] == "latency")
    P = predictions(res, ())
    check("K4 by construction: target's own span missing in 3/3 under async and full (G3 kept)",
          P["K4"]["reading"] == "yes" and P["K4"]["perPosture"]["async"]["k"] == 3)
    check("absent regime reads `—`, never no: C1 without frontend-pause episodes", P["C1"]["reading"] == "—")
    check("K1 with a ledger that fails in-window in every cell reads no",
          predictions({FRAUD: {"episodes": [dict(x, ledger={"shows": True}) for x in res[FRAUD]["episodes"]]}}, ())["K1"]["reading"] == "no")
    mg = ep["%s/b01-selected" % FRAUD]["margins"]
    check("margins: max shift/threshold over selected's outside sensors is reported (checkout, 6.5/5.93 at K=4)",
          mg["T"] is not None and mg["T"][1] == "T:checkoutservice:PlaceOrder" and 1.05 < mg["T"][0] < 1.15)
    # the check is not vacuous: break G2 and the target must leak into `outside`
    global sensors_of
    real = sensors_of
    try:
        sensors_of = lambda c, s: {(k[0], "elsewhere", k[2]): v for k, v in real(c, s).items()} if s == FRAUD_TARGET else real(c, s)
        process_cells(metas, parse=lambda mt: parsed.get(mt["cell"]))
        leaked = score(metas, skey(*FROZEN))[FRAUD]["episodes"]
        check("planted G2 defect (target relabelled) is caught: target sensors appear outside",
              any(("T", "elsewhere", "orders_process") in x["families"]["T"]["outside"] for x in leaked if x["families"]["T"]))
    finally:
        sensors_of = real
    check("grid restores symptoms.K and LAT_FLOOR_S", (SYM.K, SYM.LAT_FLOOR_S) == FROZEN == (4.0, 0.001))
    # absent-export readout (erratum 2): exports every 60 s, two slots missing inside the window; none missing outside
    ex = {"http.server.duration": [t0 + 3 + 60 * i for i in range(4)] + [t0 + 3 + 60 * 3 + 166 + 60 * i for i in range(3)]}
    check("absent export: two missed 60 s slots inside the window are reported",
          absent_exports(ex, t0, (t0 + 190, t0 + 349)) == {"http.server.duration"})
    check("absent export: the same series with the window before the gap reports nothing",
          absent_exports(ex, t0, (t0 + 130, t0 + 180)) == set())
    check("absent export: fewer than 3 pre-window exports is unknown, not absent",
          absent_exports(ex, t0, (t0 + 100, t0 + 349)) == set())
    check("absent export is not a frozen firing: metric:<x>:missing never fires a sensor",
          sensors_of(Counter({"metric:http.server.duration~rate:missing": 1}), "frontend") == {})
    # extensible scenarios: a fourth regime with its own target, read from the episodes, needs no code change
    alt = {"emailservice-stop-effect": {"episodes": [dict(x, target="emailservice") for x in res[FRAUD]["episodes"]]}}
    Pa = predictions(alt)
    check("a non-fraud regime is read with its own target and no by-construction labels",
          Pa["primaryRegime"] == "emailservice-stop-effect" and Pa["K3"]["n"] == 3
          and Pa["offPath"]["emailservice-stop-effect"]["target"] == "emailservice" and Pa["K1"]["byConstruction"] is False)
    both = dict(alt, **{FRAUD: res[FRAUD]})
    Pb = predictions(both)
    check("two off-path regimes: top level reads fraud-pause, both under offPath",
          Pb["primaryRegime"] == FRAUD and set(Pb["offPath"]) == {FRAUD, "emailservice-stop-effect"}
          and Pb["K1"]["byConstruction"] is True and Pb["K3"]["accountingservice"]["byConstruction"].startswith("no"))
    if failures:
        print("self-check: FAILED %d: %s" % (len(failures), failures))
        sys.exit(1)
    print("self-check: pass")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?")
    ap.add_argument("--out", default=None, help="output JSON (new file; default research/otel-offpath/out/...)")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args(argv)
    if a.self_check:
        self_check()
        return
    if not a.root:
        ap.error("evidence root required")
    out, path = run(a.root, a.out, log=lambda s: print(s, file=sys.stderr))
    print(headline(out))
    print("wrote", path)


if __name__ == "__main__":
    main()
