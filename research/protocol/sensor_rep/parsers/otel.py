"""OTel Demo parser: one candidate cell `runs/<regime>/<bNN-OO-posture>/` -> events. Per-SUT code lives only here.

Reused, unchanged, by path from `research/otel-offpath/adapter.py`: `parse_otelcol` (debug-exporter spans and metric
data points, `metric_series` rules), `_payload`, `_nanos`, `_attr_value`, `_severity`, `catalog_service`, `APP_SERVICES`;
`symptoms.template_id` / `mask` / `op_token`; the request-ledger reading of `visibility.otel_ledger_rows`.

The masking defect (research/sensor-validity/VALIDITY.md §7) is fixed HERE, not in symptoms.py:
`symptoms.mask` leaves alphanumeric product ids in recommendationservice bodies (`Receive ListRecommendations for
product ids:['66VCHSJNUP', ...]`), so every request became its own template (~1,700 over 12 tiles). The fix is typed and
parameter-aware, not a narrower regex (VALIDITY.md: "typed, parameter-aware templating"; memory: no narrow regex):
1. call-site templating: an OTLP log record that carries the semantic-convention attributes `code.filepath` and
   `code.lineno` (+ `code.function`) gets the template key `<scope>|<filepath>:<function>:<lineno>`; the body is not
   part of the key, because one call site has one format string and its parameters are values, whatever their shape;
2. otherwise, language-literal parameterisation: every balanced bracketed span or quoted string in the body that
   Python's own literal parser (`ast.literal_eval`) accepts is replaced by its type (`<list>`, `<dict>`, `<tuple>`,
   `<set>`, `<str>`); then `symptoms.mask` (numbers, hex, UUID, IPv4) as before. A quote opens a literal only at a token
   boundary (start, whitespace or one of `[({,:=`), so an apostrophe inside a word is text.
`templating="symptoms"` reproduces the adapter's own templating (template_id over the raw body) for the replay
against `research/otel-offpath/out/adapter-otel-v3-evidence-20261002.json`.

Engineering defaults (recorded):
- cells: `runs/*/*` with `receipt.json`; valid = receipt state "valid"; target = intervention.json `service`.
- clocks: spans, logs, metrics wall (OTLP timestamps); the ledger on the barrier-relative clock (row startedAtEpoch -
  ledger startedAtEpoch, visibility.otel_ledger_rows). Wall base and old-rule t0 = ledger startedAtEpoch (adapter
  default); fault window = appliedMonotonicOffsetSeconds..revertingMonotonicOffsetSeconds when present, else
  actualOnset/OffsetMonotonicOffsetSeconds (adapter default), on both clocks (wall = base + offset).
- ledger token `<url path>:ok|failed` (request-ledger `url`), ok = status 200 and error None; entry service `frontend`
  (visibility.ENTRY). The ledger is scored apart from G2.
- metric source: `runtime` for OTel semantic-convention runtime/process/system namespaces (`process.`, `runtime.`,
  `jvm.`, `dotnet.`, `go.`, `nodejs.`, `v8js.`, `system.`), else `application`; resolution = median export gap (s).
- Hotel's periodic GoAway template has no counterpart here; OTel loadgenerator span errors in 6/6 no-fault windows
  under `full` (VALIDITY.md §7) are an ordinary token that G3 removes.
"""
import ast
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

from . import common
from ..events import Event, level_class, stream_meta

SUT = "otel"
ENTRY = "frontend"
COLLECTS = {"L": ("selected", "async", "full"), "M": ("selected", "async", "full"), "T": ("selected", "async", "full")}
RUNTIME_NS = ("process.", "runtime.", "jvm.", "dotnet.", "go.", "nodejs.", "v8js.", "system.")
OPEN = {"[": "]", "{": "}", "(": ")"}
QUOTE_BOUNDARY = set(" \t[({,:=")


def adapter():
    return common.load("sensor_rep_otel_adapter", common.RESEARCH / "otel-offpath" / "adapter.py")


def cell_dirs(x):
    return [d for d in sorted(Path(x).glob("runs/*/*")) if d.is_dir() and (d / "receipt.json").exists()]


# --------------------------------------------------------------------------- typed templating

def _quoted_end(s, i):
    q = s[i]
    j = i + 1
    while j < len(s):
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == q:
            return j
        j += 1
    return -1


def _bracket_end(s, i):
    stack = [OPEN[s[i]]]
    j = i + 1
    while j < len(s):
        ch = s[j]
        if ch in "'\"":
            k = _quoted_end(s, j)
            if k < 0:
                return -1
            j = k + 1
            continue
        if ch in OPEN:
            stack.append(OPEN[ch])
        elif ch in ")]}":
            if not stack or ch != stack[-1]:
                return -1
            stack.pop()
            if not stack:
                return j
        j += 1
    return -1


def literal_params(msg):
    """Replace language literals in a message by their type (see module docstring, rule 2)."""
    out, i = [], 0
    while i < len(msg):
        ch = msg[i]
        end = -1
        if ch in OPEN:
            end = _bracket_end(msg, i)
        elif ch in "'\"" and (i == 0 or msg[i - 1] in QUOTE_BOUNDARY):
            end = _quoted_end(msg, i)
        if end > i:
            frag = msg[i:end + 1]
            try:
                val = ast.literal_eval(frag)
            except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
                val = frag
            if frag is not val and isinstance(val, (list, dict, tuple, set, str)):
                out.append("<%s>" % type(val).__name__)
                i = end + 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def template(rec, templating="callsite"):
    S = common.symptoms()
    if templating == "symptoms":
        return S.template_id("otlp-log", rec["level"], rec["scope"], rec["body"]), "body"
    a = rec["attrs"]
    if "code.filepath" in a and "code.lineno" in a:
        key = "%s|%s:%s:%s" % (rec["scope"], a["code.filepath"], a.get("code.function", "?"), a["code.lineno"])
        return S.template_id("otlp-log", rec["level"], key, "<callsite>"), "callsite"
    return S.template_id("otlp-log", rec["level"], rec["scope"], literal_params(rec["body"])), "literal"


# --------------------------------------------------------------------------- log records with attributes

def parse_log_records(lines):
    """Debug-exporter LogRecords with their attributes -> {service: [rec]}; rec = {t, level, scope, body, attrs}.
    Same resource/scope resolution as adapter.parse_otelcol (which drops the record attributes)."""
    A = adapter()
    logs, stats = defaultdict(list), Counter()
    kind, res, in_res, scope, svc = None, {}, False, None, None
    cur, in_attrs = None, False

    def flush():
        nonlocal cur
        if cur is not None and svc is not None:
            ns = cur.get("ts") or cur.get("observed")
            logs[svc].append({"t": None if ns is None else ns / 1e9,
                              "level": A._severity(cur.get("sevnum", ""), cur.get("sevtext", "")),
                              "scope": scope, "body": cur.get("body", ""), "attrs": cur["attrs"]})
            stats["logRecords"] += 1
        cur = None

    for raw in lines:
        s = A._payload(raw.rstrip("\r\n")).strip()
        if not s:
            continue
        last = s.rsplit("\t", 1)[-1]
        if last.startswith(("ResourceSpans #", "ResourceMetrics #", "ResourceLog #")):
            flush()
            kind = "logs" if last.startswith("ResourceLog") else "other"
            res, in_res, scope, svc, in_attrs = {}, False, None, None, False
            continue
        if "\tinfo\t" in s or "\twarn\t" in s or "\terror\t" in s:
            flush()
            continue
        if kind != "logs":
            continue
        if s == "Resource attributes:":
            in_res = True
            continue
        if s.startswith("ScopeLogs #"):
            flush()
            if in_res:
                in_res = False
                name = res.get("service.name")
                svc = A.catalog_service(name)[0] if name is not None else None
            continue
        if in_res:
            if s.startswith("-> "):
                k, _, v = s[3:].partition(": ")
                res[k] = A._attr_value(v)
            continue
        if s.startswith("InstrumentationScope"):
            bits = s.split()
            scope = bits[1] if len(bits) > 1 else ""
            continue
        if s.startswith("LogRecord #"):
            flush()
            cur, in_attrs = {"attrs": {}}, False
            continue
        if cur is None:
            continue
        if s == "Attributes:":
            in_attrs = True
            continue
        if in_attrs and s.startswith("-> "):
            k, _, v = s[3:].partition(": ")
            cur["attrs"][k] = A._attr_value(v)
            continue
        in_attrs = False
        k, _, v = s.partition(": ")
        if k == "ObservedTimestamp":
            cur["observed"] = A._nanos(v)
        elif k == "Timestamp":
            cur["ts"] = A._nanos(v)
        elif k == "SeverityText":
            cur["sevtext"] = v
        elif k == "SeverityNumber":
            cur["sevnum"] = v
        elif k == "Body":
            cur["body"] = A._attr_value(v) if v.startswith("Str(") else v
    flush()
    return dict(logs), stats


# --------------------------------------------------------------------------- cell

def parse_cell(d, population, templating="callsite"):
    S = common.symptoms()
    A = adapter()
    d = Path(d)
    rc = json.loads((d / "receipt.json").read_text())
    rk = rc["runKey"]
    posture = rk["posture"]
    ivp = d / "intervention.json"
    iv = json.loads(ivp.read_text()) if ivp.exists() else None
    target = iv.get("service") if iv else None
    kind = ("pause" if str(iv.get("scenario", "")).endswith("pause") else None) if iv else None
    cell = common.new_cell(SUT, population, d, posture, rk["regime"], rk["block"], rc.get("state") == "valid",
                           target, kind)
    ev, stats = cell["events"], cell["stats"]
    lp = d / "request-ledger.json"
    cell["channels"]["ledger"] = {"present": lp.exists(), "collectors": ["request-ledger"], "resolution": "per-record",
                                  "file": "request-ledger.json"}
    base = None
    if lp.exists():
        led = json.loads(lp.read_text())
        base = led["startedAtEpoch"]
        cell["duration"] = led.get("endedAtEpoch", base) - base
        route = urlparse(led.get("url", "")).path or "?"
        m = stream_meta(SUT, posture, "ledger", ENTRY, "harness", "request-ledger", "mono", "per-record")
        for q in led["requests"]:
            ok = q["status"] == 200 and q["error"] is None
            ev.append(Event("ledger", ENTRY, route + (":ok" if ok else ":failed"), q["startedAtEpoch"] - base,
                            (q["endedAtEpoch"] - q["startedAtEpoch"]) * 1000.0, m))
    cell["base"] = {"wall": base, "mono": 0.0} if base is not None else {}
    cell["t0"] = {"wall": base, "mono": None}
    if iv and base is not None:
        if iv.get("appliedMonotonicOffsetSeconds") is not None and iv.get("revertingMonotonicOffsetSeconds") is not None:
            a, b = iv["appliedMonotonicOffsetSeconds"], iv["revertingMonotonicOffsetSeconds"]
        else:
            a, b = iv.get("actualOnsetMonotonicOffsetSeconds"), iv.get("actualOffsetMonotonicOffsetSeconds")
        if a is not None and b is not None:
            cell["fault"] = {"wall": (base + a, base + b), "mono": (float(a), float(b))}
    op = d / "otelcol.log"
    present = op.exists()
    for ch in ("log", "span", "metric"):
        cell["channels"][ch] = {"present": present, "collectors": ["otelcol-debug-exporter"], "file": "otelcol.log",
                                "resolution": "per-record" if ch != "metric" else None}
    if not present:
        return cell
    with open(op, encoding="utf-8", errors="replace") as fh:
        parsed = A.parse_otelcol(fh)
    with open(op, encoding="utf-8", errors="replace") as fh:
        logs, lstats = parse_log_records(fh)
    stats.update({"otelcol:" + k: v for k, v in parsed["stats"].items() if isinstance(v, int)})
    # cross-check: the attribute-aware pass sees exactly the adapter's log records (count and timestamps per service)
    mism = [s for s in set(logs) | set(parsed["logs"])
            if [r["t"] for r in logs.get(s, [])] != [r["t"] for r in parsed["logs"].get(s, [])]]
    stats["log:recordsMatchAdapter"] = not mism
    basis = Counter()
    for svc, recs in logs.items():
        for r in recs:
            tid, how = template(r, templating)
            basis[how] += 1
            lv = level_class("otlp-log", r["level"])
            m = stream_meta(SUT, posture, "log", svc, "application", "otelcol-debug-exporter", "wall", "per-record", lv)
            ev.append(Event("log", svc, tid, r["t"], 1.0, m))
    stats.update({"log:template:" + k: v for k, v in basis.items()})
    for svc, spans in parsed["spans"].items():
        m = stream_meta(SUT, posture, "span", svc, "application", "otelcol-debug-exporter", "wall", "per-record")
        for t, name, dur, err in spans:
            tok = S.op_token(name)
            ev.append(Event("span", svc, tok, t, dur, m))
            if err:
                ev.append(Event("span", svc, tok + ":error", t, dur, m))
    gaps = []
    for svc, ex in parsed.get("exports", {}).items():
        for ts in ex.values():
            gaps += [b - a for a, b in zip(ts, ts[1:])]
    res = statistics.median(gaps) if gaps else None
    cell["channels"]["metric"]["resolution"] = res
    for svc, series in parsed["metrics"].items():
        for tok, xs in series.items():
            src = "runtime" if tok.startswith(RUNTIME_NS) else "application"
            m = stream_meta(SUT, posture, "metric", svc, src, "otelcol-debug-exporter", "wall", res)
            for t, x in xs:
                ev.append(Event("metric", svc, tok, t, x, m))
    return cell


def pseudo_offsets(cells):
    """adapter.process_cells: median offsets of the VALID fault cells (one fault regime per population here)."""
    out = {}
    offs = [(c["fault"]["mono"][0], c["fault"]["mono"][1]) for c in cells if c["valid"] and c["fault"]]
    if offs:
        a, b = statistics.median(o[0] for o in offs), statistics.median(o[1] for o in offs)
        out = {"wall": (a, b), "mono": (a, b)}
    return out


def family(channel, collector, posture):
    return {"log": "L", "metric": "M", "span": "T"}.get(channel)
