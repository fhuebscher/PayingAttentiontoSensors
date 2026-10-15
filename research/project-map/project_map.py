#!/usr/bin/env python3
"""Project map (planning artefact, not for the paper): projected vs observed emission per service x channel x posture
for HotelReservation, TeaStore and OTel Demo (research/PROTOCOL_DRAFT_20261002.md section 1b).

    rm -rf ~/Library/Caches/com.apple.python/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/research
    /usr/bin/python3 -B research/project-map/project_map.py               # writes project_map.json + PROJECT_MAP.md here
    /usr/bin/python3 -B research/project-map/project_map.py --self-check  # planted case per state; exit 1 if wrong
    /usr/bin/python3 -B research/project-map/project_map.py --no-callsites  # skip the Go/Java scanners

Read-only over the evidence; writes only into research/project-map/. Python 3.9 compatible (no `X | None`).

What a cell is
--------------
(SUT, service, channel, posture). Channels: metric:runtime, metric:app, log:info, log:warn, log:error, log:other,
log:undefined, trace, ledger (ledger cells exist for the entry service only). Each cell carries a projection
(possible / not-possible / unknown, from configuration and source only), an observation (count in the measurement
window and over the whole retained capture, or null when the evidence cannot show it), and a state:
  possible-observed       projection possible, observed count > 0
  possible-not-observed   projection possible, observed count == 0 on a channel whose capture is complete
  not-possible            projection not-possible, observed count == 0 or not observable (then `unconfirmed`)
  observed-not-projected  observed count > 0 while the projection said not-possible or unknown
  unknown (`?`)           the evidence cannot show the channel (not collected, or a partial capture holding 0),
                          or the projection is unknown and nothing was observed
`state` uses the measurement window; `stateCapture` the whole retained capture.

Role rule (code: assign_roles)
------------------------------
1. data store / broker / telemetry from tokens of the compose image reference and the service name, matched against
   fixed vocabularies of well-known server products (ROLE_TOKENS; precedence telemetry > broker > data store).
2. entry: among the remaining services, the one(s) publishing a fixed host port ("H:C" or a long-form `published`);
   if several, the one whose published port equals the workload URL's port; if still ambiguous, the service that
   is the local root of most base-run traces.
3. driven traces = base-run traces whose local root span (no parent, or a parent not retained in the trace) belongs
   to the entry. On-route services = services with a span in a driven trace.
4. interior = on route with a cross-service parent->child edge to another on-route service in a driven trace;
   leaf = on route without one; helper = everything else (off the driven route).

Engineering defaults (recorded; scope and meaning stay with the user)
---------------------------------------------------------------------
- Evidence: observed cells are block b01 no-fault cells, one per posture. The base run (call graph for roles and for
  the `expected` flag of trace cells) is a *different* no-fault `full` cell from block b02, so the trace projection
  is not computed from the cell it is compared with. Hotel tmp/hotelrep1-evidence/x (cost/b01/*, base cost/b02 full);
  TeaStore tmp/teastore16-evidence/x/teastore-candidate-pilot-v1 (no-fault-cost/b01-*, base b02-*-full); OTel
  tmp/otel-v3-evidence/runs (no-fault-cost/b01-*, base b02-*-full).
- Measurement window: Hotel opportunity-plan barrierAt + durationSeconds; TeaStore receipt window; OTel request-ledger
  startedAtEpoch..endedAtEpoch. Capture = everything retained in the cell.
- "possible" for traces means instrumented under the posture (structural); whether the driven workload reaches the
  service is recorded as `expected` and used as the likely reason of a gap ("no traffic"), as section 1b lists it.
- Log level classes: info; warn; error; other = trace, debug, fatal, panic (and JUL FINE/CONFIG, MariaDB none);
  undefined = a record whose layout carries no level (Go stdlib `log` without a gRPC severity prefix, JVM throwable
  headers, OTLP SeverityNumber 0 without SeverityText) plus unparsed lines. Harness lines (OBSPLACEMENT_*,
  OBSERVABILITY_*) are excluded from every class: they are the harness's channel, not the service's.
- Log projection: a class is possible iff one of its member levels is available in the logging framework and >= the
  configured threshold. undefined is always possible (any process can write unlevelled stdout). Threshold unknown ->
  projection unknown. MariaDB `Note` is mapped to info. Go `log` lines without a gRPC severity prefix: symptoms.py
  maps them to info; here they are undefined (the layout carries no level).
- Configured level sources: Hotel = compose env LOG_LEVEL per posture fed through the switch in tune/setting.go of the
  *materialized* (witness-patched) source, read with go/ast (callsites/callsites.go); TeaStore = slf4j-simple default
  INFO (no simplelogger.properties / defaultLogLevel in the upstream tree, checked by file walk) and Tomcat JUL default
  INFO (assumed: no logging.properties override in the tree); available levels exclude fatal/panic (slf4j and JUL
  have none). OTel = a static level the Go source sets (logrus `.Level =` / `SetLevel`), else unknown. Third-party
  images: unknown.
- Call sites per level: counted language-aware only where a parser exists here: Go via go/ast (Hotel, OTel checkout and
  productcatalog), Java via the javac Tree API (TeaStore services + their in-repo Maven dependencies, OTel adservice).
  Vendor/library code is not counted, so app call sites == 0 at a passing level does NOT make the class not-possible
  (gRPC, Tomcat, runtimes log too); it is recorded (`appCallSites`) and used in the gap reason. Without a parser the
  cell says projectionSource `configured-level-only`.
- metric:runtime is possible for every container (cgroup / docker stats). metric:app: Hotel/TeaStore app services from
  metric-library imports (go/ast, javac); OTel app services = SDK enabled under the posture (catalog closure, imported
  from research/otel-offpath/adapter.py LAYOUTS v3); otelcol = its config's prometheus self-scrape receiver;
  third-party images unknown.
- trace projection: Hotel compose env JAEGER_DISABLED == false and JAEGER_SAMPLE_RATIO > 0; TeaStore Kieker enabled
  (RABBITMQ_HOST set and != "unset", upstream dockerbase start.sh) and the service's aspectj group in the posture's
  closure (posture-proof.json closureGroups, the harness's declared posture); OTel posture closure. Containers outside
  the posture's instrumentation config: not-possible (no trace exporter configured).
- Observation completeness: Hotel logs complete for services built from the application source (compose `build`);
  Hotel traces complete only for the service Jaeger was queried for (jaeger-raw.json url `service=`), else a zero is
  unknown; Hotel runtime metrics complete for services in cpu.json / system-samples.json. TeaStore logs complete for
  services with a retained `<service>.log` (measurement-window scope, so window == capture); traces complete for all
  (Kieker AMQP consumer); runtime metrics for resources.json containers. OTel: traces and app metrics complete for every
  service (collector debug exporter sees all OTLP); OTLP logs complete for a service only if it is SDK-enabled under the
  posture AND emitted >= 1 OTLP log record in any parsed OTel cell (evidence of a log bridge), and never for undefined
  (stdout is not retained); otelcol self-metrics carry no timestamp in the parser, so their window count is unknown.
- OTel compose model: upstream docker-compose.yml with .env interpolation (compose spec ${VAR}, ${VAR:-d}, ${VAR:?m})
  plus the harness overlays; the materialized compose (rewritten ports) is not retained locally.
- Compose models: Hotel = the compose-rendered.yml (JSON from `docker compose config`) retained in each cell, so the
  per-posture env (LOG_LEVEL, JAEGER_*) is what ran; TeaStore = the runtime worktree's docker-compose_kieker.yaml +
  docker-compose_rabbitmq.yaml + isolation.override.yaml + the posture override (none.override.yaml /
  compiled-<posture>.override.yaml); `environment` lists and mappings are both accepted.
- Role vocabulary (ROLE_TOKENS) is a fixed table of server-product names matched as whole tokens of the image reference
  and the service name (no substring regex); bare `otel` and `telemetry` are deliberately absent, because OTel Demo's own
  application images carry them.
- Ledger observed count: Hotel opportunity-ledger rows; TeaStore request rows inside journey-ledger terminal rows; OTel
  request-ledger rows. Ledger cells exist for the entry only.
- `unconfirmed`: a not-possible cell whose channel the evidence cannot show; counted under not-possible and reported
  separately in the counts table.
- Likely reasons are heuristics computed from the cell's own fields (the `expected` flag, window vs capture counts,
  app call-site count, record frameworks); they are leads to check, not verified causes.
- The OTel base-run call graph needs span/parent ids, which adapter.parse_otelcol drops; otel_span_edges reads them
  from the same debug-exporter layout using the adapter's own _payload/_attr_value/catalog_service.
"""
import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
REPO = RESEARCH.parent
SIBLINGS = REPO.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SYM = _load("pm_symptoms", RESEARCH / "s4-conjunction" / "symptoms.py")
ADP = _load("pm_otel_adapter", RESEARCH / "otel-offpath" / "adapter.py")
try:
    import yaml  # PyYAML 6 is present in /usr/bin/python3 and the uv env
except ImportError:  # pragma: no cover
    yaml = None

# --------------------------------------------------------------------------- raw levels from the reused parsers
# symptoms.py maps info/debug/trace to None (it only needs alert levels). The project map needs every level, so this
# module's private copy of symptoms.py gets identity level maps. The functions read these module globals at call time.
SYM.ZL_LEVEL = {k: k for k in SYM.ZL_LEVEL}
SYM.L4J_LEVEL = {k: k.lower() for k in SYM.L4J_LEVEL}
SYM.JUL_LEVEL = {"FINEST": "trace", "FINER": "trace", "FINE": "debug", "CONFIG": "debug", "INFO": "info",
                 "WARNING": "warn", "SEVERE": "error"}
SYM.MARIADB_LEVEL = {"Note": "info", "Warning": "warn", "Warn": "warn", "ERROR": "error"}
SYM.GRPC_LEVEL = {k: k for k in SYM.GRPC_LEVEL}


def go_log_raw(payload):
    """symptoms.parse_go_log, but a line without a gRPC severity prefix keeps level None (undefined)."""
    r = SYM.parse_go_log(payload)
    if r is not None:
        first = payload[20:].split(None, 1)
        if not first or first[0] not in SYM.GRPC_SEV:
            r["level"] = None
    return r


HOTEL_LAYOUTS = (SYM.parse_zerolog_json, SYM.parse_zerolog_console, go_log_raw)
JVM_LAYOUTS = SYM.JVM_LAYOUTS


def otlp_severity(number_text, severity_text):
    """OTLP SeverityNumber ranges (1-4 trace, 5-8 debug, 9-12 info, 13-16 warn, 17-20 error, 21-24 fatal); the text
    only when the number is 0 or absent. Replaces the adapter's alert-only _severity in this module's copy."""
    n = 0
    if "(" in number_text and ")" in number_text:
        try:
            n = int(number_text[number_text.index("(") + 1:number_text.index(")")])
        except ValueError:
            n = 0
    if n:
        return ("trace", "debug", "info", "warn", "error", "fatal")[min((n - 1) // 4, 5)]
    t = severity_text.strip().upper()
    return {"TRACE": "trace", "DEBUG": "debug", "INFO": "info", "INFORMATION": "info", "WARN": "warn",
            "WARNING": "warn", "ERROR": "error", "FATAL": "fatal", "CRITICAL": "fatal"}.get(t)


ADP._severity = otlp_severity

# --------------------------------------------------------------------------- vocabulary

CHANNELS = ("metric:runtime", "metric:app", "log:info", "log:warn", "log:error", "log:other", "log:undefined",
            "trace", "ledger")
CLASSES = ("info", "warn", "error", "other", "undefined")
SEVERITY = {"trace": 1, "debug": 2, "info": 3, "warn": 4, "error": 5, "fatal": 6, "panic": 6}
CLASS_MEMBERS = {"info": ("info",), "warn": ("warn",), "error": ("error",), "other": ("trace", "debug", "fatal", "panic")}
ALL_LEVELS = tuple(SEVERITY)
STATES = ("possible-observed", "possible-not-observed", "not-possible", "observed-not-projected")
UNKNOWN = "unknown"
SYMBOL = {"possible-observed": "+", "possible-not-observed": "o", "not-possible": "x", "observed-not-projected": "!",
          UNKNOWN: "?", None: "—"}
ROLES = ("entry", "interior", "leaf", "helper", "data store", "broker", "telemetry")
ROLE_TOKENS = (
    ("telemetry", {"jaeger", "otelcol", "collector", "prometheus", "grafana", "opensearch", "elasticsearch", "kibana",
                   "loki", "tempo", "zipkin", "fluentd", "fluentbit"}),
    ("broker", {"rabbitmq", "kafka", "nats", "activemq", "pulsar", "mosquitto"}),
    ("data store", {"mongo", "mongodb", "memcached", "mariadb", "mysql", "postgres", "postgresql", "redis", "valkey",
                    "cassandra", "couchdb", "db"}),
)


def level_class(raw):
    if raw is None:
        return "undefined"
    raw = raw.lower()
    if raw in ("info",):
        return "info"
    if raw in ("warn", "warning"):
        return "warn"
    if raw in ("error", "severe"):
        return "error"
    return "other"


def tokens(*texts):
    out = set()
    for t in texts:
        t = (t or "").split("@", 1)[0].lower()
        for ch in "/:-_.":
            t = t.replace(ch, " ")
        out.update(x for x in t.split() if x)
    return out


def epoch(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def rel(p):
    try:
        return str(Path(p).resolve().relative_to(REPO))
    except ValueError:
        return str(Path(p).resolve())


# --------------------------------------------------------------------------- classifier

def classify(projection, observed):
    """projection in {possible, not-possible, unknown}; observed int or None (not observable)."""
    if observed is None:
        return "not-possible" if projection == "not-possible" else UNKNOWN
    if observed > 0:
        return "possible-observed" if projection == "possible" else "observed-not-projected"
    if projection == "possible":
        return "possible-not-observed"
    if projection == "not-possible":
        return "not-possible"
    return UNKNOWN


def observed_value(entry, scope):
    """entry = {window, capture, complete, completeWindow?, note}; returns int or None (unknown)."""
    if entry is None:
        return None
    n = entry.get(scope)
    if n is None:
        return None
    complete = entry.get("complete" + scope.capitalize(), entry.get("complete", False))
    if n == 0 and not complete:
        return None
    return n


# --------------------------------------------------------------------------- roles

def image_role(image, service):
    toks = tokens(image, service)
    for role, vocab in ROLE_TOKENS:
        hit = toks & vocab
        if hit:
            return role, sorted(hit)
    return None, []


def call_graph(spans, entry):
    """spans: [(trace, span, parent, service)] -> (roots Counter by service, driven on-route set, edges Counter)."""
    by_trace = defaultdict(list)
    for t, s, p, svc in spans:
        by_trace[t].append((s, p, svc))
    roots, on_route, edges = Counter(), set(), Counter()
    driven = 0
    for t, rows in by_trace.items():
        ids = {s: svc for s, p, svc in rows}
        local_roots = [svc for s, p, svc in rows if not p or p not in ids]
        for svc in set(local_roots):
            roots[svc] += 1
        if entry is None or not local_roots or entry not in local_roots:
            continue
        driven += 1
        for s, p, svc in rows:
            on_route.add(svc)
            if p and p in ids and ids[p] != svc:
                edges[(ids[p], svc)] += 1
    return roots, on_route, edges, driven, len(by_trace)


def assign_roles(services, spans, workload_port=None):
    """services: {name: {image, fixedPorts}} -> ({name: {role, rule, evidence}}, entry, graph summary)."""
    out = {}
    for s, d in services.items():
        role, hit = image_role(d.get("image"), s)
        if role:
            out[s] = {"role": role, "rule": "image/name token %s" % ",".join(hit)}
    cands = sorted(s for s, d in services.items() if s not in out and d.get("fixedPorts"))
    entry, entry_rule = None, None
    if len(cands) == 1:
        entry, entry_rule = cands[0], "only non-infrastructure service publishing a fixed host port %s" % services[cands[0]]["fixedPorts"]
    elif len(cands) > 1 and workload_port is not None:
        m = [s for s in cands if str(workload_port) in [str(p) for p in services[s]["fixedPorts"]]]
        if len(m) == 1:
            entry, entry_rule = m[0], "publishes the workload URL port %s" % workload_port
    roots0, _, _, _, _ = call_graph(spans, None)
    if entry is None and roots0:
        c = [(n, s) for s, n in roots0.items() if s in services and s not in out]
        if c:
            entry = max(c)[1]
            entry_rule = "local root of most base-run traces (%d)" % max(c)[0]
    roots, on_route, edges, driven, ntraces = call_graph(spans, entry)
    if entry:
        out[entry] = {"role": "entry", "rule": entry_rule}
    for s in services:
        if s in out:
            continue
        if s in on_route:
            outs = sorted({c for (p, c) in edges if p == s and c in on_route and c != s})
            if outs:
                out[s] = {"role": "interior", "rule": "on driven route; calls %s" % ",".join(outs)}
            else:
                out[s] = {"role": "leaf", "rule": "on driven route; no outgoing cross-service edge"}
        else:
            out[s] = {"role": "helper", "rule": "off the driven route (no span in an entry-rooted base-run trace)"}
    top_root = roots0.most_common(1)[0][0] if roots0 else None
    graph = {"tracesInBaseRun": ntraces, "drivenTraces": driven, "onRoute": sorted(on_route),
             "edges": {"%s->%s" % k: v for k, v in sorted(edges.items())},
             "mostCommonLocalRoot": top_root,
             "entryAgreesWithRootSpans": (top_root == entry) if top_root else None,
             "spanServicesNotInCompose": sorted({x[3] for x in spans} - set(services))}
    return out, entry, graph


# --------------------------------------------------------------------------- call-site scanners

def run_go_scanner(module_root):
    if shutil.which("go") is None or not Path(module_root).is_dir():
        return None
    try:
        p = subprocess.run(["go", "run", str(HERE / "callsites" / "callsites.go"), str(module_root)],
                           capture_output=True, text=True, timeout=600, cwd=str(HERE / "callsites"))
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        sys.stderr.write("go scanner failed on %s: %s\n" % (module_root, p.stderr[-400:]))
        return None
    return json.loads(p.stdout)


def run_java_scanner(roots):
    """roots: {name: [src dirs]} -> {name: {calls, logApis, metricImports, files}} (summed over dirs)."""
    if shutil.which("java") is None or not roots:
        return None
    args, owners = [], []
    for name, dirs in roots.items():
        for i, d in enumerate(dirs):
            if Path(d).is_dir():
                args.append("%s#%d=%s" % (name, i, d))
                owners.append(name)
    try:
        p = subprocess.run(["java", str(HERE / "callsites" / "CallSites.java")] + args, capture_output=True, text=True,
                           timeout=600)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        sys.stderr.write("java scanner failed: %s\n" % p.stderr[-400:])
        return None
    raw = json.loads(p.stdout)
    out = {}
    for key, v in raw.items():
        name = key.split("#", 1)[0]
        o = out.setdefault(name, {"calls": Counter(), "logApis": set(), "metricImports": set(), "files": 0})
        o["calls"].update(v["calls"])
        o["logApis"].update(v["logApis"])
        o["metricImports"].update(v["metricImports"])
        o["files"] += v["files"]
    return {k: {"calls": dict(v["calls"]), "logApis": sorted(v["logApis"]), "metricImports": sorted(v["metricImports"]),
                "files": v["files"]} for k, v in out.items()}


def class_callsites(calls):
    """{raw level: n} -> {class: n}; 'none' -> undefined."""
    if calls is None:
        return None
    out = {c: 0 for c in CLASSES}
    for lvl, n in calls.items():
        out["undefined" if lvl == "none" else level_class(lvl)] += n
    return out


# --------------------------------------------------------------------------- observation helpers

def log_counts(records, stats, window, timed=True, whole_seconds=False):
    """records -> per class {window, capture, frameworks}; unparsed lines -> undefined (capture only when timed)."""
    w, c, fw = Counter(), Counter(), defaultdict(Counter)
    for r in records:
        cls = level_class(r["level"])
        c[cls] += 1
        fw[cls][r["framework"]] += 1
        if not timed or (r["t"] is not None and SYM.in_window(r["t"], window, whole_seconds)):
            w[cls] += 1
    un = stats.get("unparsed", 0) if stats else 0
    c["undefined"] += un
    if not timed:
        w["undefined"] += un
    if un:
        fw["undefined"]["unparsed"] += un
    return {cls: {"window": w[cls], "capture": c[cls], "frameworks": dict(fw[cls])} for cls in CLASSES}


def new_obs():
    return defaultdict(dict)   # service -> channel -> entry


def put(obs, svc, ch, window, capture, complete, note, path, **extra):
    e = {"window": window, "capture": capture, "complete": complete, "note": note, "evidence": rel(path) if path else None}
    e.update(extra)
    obs[svc][ch] = e


# --------------------------------------------------------------------------- HotelReservation

HOTEL_EV = REPO / "tmp" / "hotelrep1-evidence" / "x"


def _cell(root, pattern):
    hits = sorted(root.glob(pattern))
    return hits[0] if hits else None


def hotel(scan=True):
    runs = HOTEL_EV / "runs" / "cost"
    postures = ("none", "metrics", "selected", "full")
    cells = {p: _cell(runs, "b01/*-%s/attempt-01" % p) for p in postures}
    base = _cell(runs, "b02/*-full/attempt-01")
    missing = [p for p, c in cells.items() if c is None] + ([] if base else ["base"])
    if missing:
        return {"sut": "hotel", "blocked": "missing Hotel cells: %s" % missing}
    composes = {p: json.loads((c / "compose-rendered.yml").read_text()) for p, c in cells.items()}
    services = {}
    for s, d in composes["full"]["services"].items():
        fixed = [x.get("published") for x in (d.get("ports") or []) if isinstance(x, dict) and x.get("published")]
        services[s] = {"image": d.get("image"), "fixedPorts": fixed, "built": "build" in d,
                       "entrypoint": (d.get("entrypoint") or [None])[0]}
    wl = json.loads((cells["full"] / "warmup.json").read_text()).get("baseUrl", "")
    wport = wl.rsplit(":", 1)[-1].split("/", 1)[0] if ":" in wl else None
    spans = [(e["traceId"], e["spanId"], e.get("parentSpanId"), e["service"])
             for e in json.loads((base / "traces-normalized.json").read_text())["events"]]
    # source scan (materialized = witness-patched source the image was built from)
    src = HOTEL_EV / "materialized-source"
    go = run_go_scanner(src) if scan else None
    switch = None
    if go and go.get("levelSwitches"):
        switch = go["levelSwitches"][0]
    log_cfg, trace_cfg, metric_cfg, callsites = {}, {}, {}, {}
    for s, d in services.items():
        b = go["binaries"].get(d["entrypoint"]) if (go and d["built"]) else None
        callsites[s] = dict(b["calls"]) if b else None
        for p in postures:
            env = composes[p]["services"].get(s, {}).get("environment") or {}
            if d["built"]:
                if switch:
                    var = switch["envVars"][0] if switch["envVars"] else "LOG_LEVEL"
                    val = env.get(var, switch.get("defaultString"))
                    thr = switch["cases"].get(val, switch.get("default"))
                    src_txt = "compose env %s=%r -> %s:%s switch (go/ast)" % (var, val, switch["file"], switch["func"])
                else:
                    val = env.get("LOG_LEVEL")
                    thr = val.lower() if val and val.lower() in SEVERITY else None
                    src_txt = "compose env LOG_LEVEL=%r (no source switch read)" % val
                log_cfg[(s, p)] = {"threshold": thr, "available": ALL_LEVELS, "source": src_txt,
                                   "framework": "zerolog (+ Go stdlib log / grpclog, not level-governed)"}
                on = env.get("JAEGER_DISABLED") == "false" and float(env.get("JAEGER_SAMPLE_RATIO", "0") or 0) > 0
                trace_cfg[(s, p)] = (on, "compose env JAEGER_DISABLED=%s JAEGER_SAMPLE_RATIO=%s" % (
                    env.get("JAEGER_DISABLED"), env.get("JAEGER_SAMPLE_RATIO")))
                if b is not None:
                    metric_cfg[(s, p)] = (bool(b["metricImports"]), "go/ast imports: %s" % (b["metricImports"] or "no metric library"))
                else:
                    metric_cfg[(s, p)] = (None, "source not scanned")
            else:
                log_cfg[(s, p)] = {"threshold": None, "available": ALL_LEVELS,
                                   "source": "third-party image; no level configured in compose", "framework": "?"}
                trace_cfg[(s, p)] = (False, "no trace exporter configured for this container")
                metric_cfg[(s, p)] = (None, "third-party image; metrics endpoint not determined from config")
    # observations
    obs_by_posture, windows = {}, {}
    for p, c in cells.items():
        plan = json.loads((c / "opportunity-plan.json").read_text())
        ws = epoch(plan["barrierAt"])
        win = (ws, ws + float(plan["durationSeconds"]))
        windows[p] = win
        obs = new_obs()
        streams = defaultdict(list)
        for raw in (c / "application.log").read_text(errors="replace").splitlines():
            if " | " in raw:
                prefix, payload = raw.split(" | ", 1)
                streams[prefix.strip().rsplit("-", 1)[0]].append(payload)
        for s, d in services.items():
            if d["built"]:
                recs, st = SYM.parse_stream(streams.get(s, []), HOTEL_LAYOUTS)
                lc = log_counts(recs, st, win, timed=True, whole_seconds=True)
                for cls in CLASSES:
                    put(obs, s, "log:" + cls, lc[cls]["window"], lc[cls]["capture"], True,
                        "docker compose logs of the application services", c / "application.log",
                        frameworks=lc[cls]["frameworks"])
            else:
                for cls in CLASSES:
                    put(obs, s, "log:" + cls, None, None, False, "container log not captured by the Hotel harness", None)
        # traces: Jaeger queried for one service; complete only for that one
        jr = c / "jaeger-raw.json"
        queried = sorted({q.get("service") for q in json.loads(jr.read_text()).get("queries", [])}) if jr.exists() else []
        tr = c / "traces-normalized.json"
        tw, tc = Counter(), Counter()
        if tr.exists():
            for e in json.loads(tr.read_text())["events"]:
                tc[e["service"]] += 1
                if win[0] <= e["startTimeUs"] / 1e6 <= win[1]:
                    tw[e["service"]] += 1
        for s in services:
            if tr.exists():
                put(obs, s, "trace", tw[s], tc[s], s in queried,
                    "Jaeger queried for service=%s only: a zero is evidence only for that service" % ",".join(queried), tr)
            else:
                put(obs, s, "trace", None, None, False, "no traces-normalized.json", None)
        # runtime metrics: docker stats (cpu.json, not in `none`) + cgroup sampler (system-samples.json)
        mw, mc, covered = Counter(), Counter(), set()
        paths = []
        cpu = c / "cpu.json"
        if cpu.exists():
            paths.append(cpu)
            for smp in json.loads(cpu.read_text())["samples"]:
                for k in smp["containers"]:
                    covered.add(k["service"])
                    mc[k["service"]] += 1
                    if win[0] <= smp["capturedAtEpoch"] <= win[1]:
                        mw[k["service"]] += 1
        ss = c / "system-samples.json"
        if ss.exists():
            paths.append(ss)
            for smp in json.loads(ss.read_text())["samples"]:
                t = epoch(smp["at"])
                for svc in smp["services"]:
                    covered.add(svc)
                    mc[svc] += 1
                    if win[0] <= t <= win[1]:
                        mw[svc] += 1
        for s in services:
            if s in covered:
                put(obs, s, "metric:runtime", mw[s], mc[s], True, "docker stats + cgroup sampler samples",
                    paths[-1] if paths else None)
            else:
                put(obs, s, "metric:runtime", None, None, False, "container not sampled by docker stats or the cgroup sampler", None)
            put(obs, s, "metric:app", None, None, False, "no application-metric collector in the Hotel harness", None)
        led = c / "opportunity-ledger.jsonl"
        n = sum(1 for line in led.read_text().splitlines() if line.strip())
        obs["__entry__"]["ledger"] = {"window": n, "capture": n, "complete": True, "note": "opportunity ledger rows",
                                      "evidence": rel(led)}
        obs_by_posture[p] = {"cell": rel(c), "obs": obs}
    return {"sut": "hotel", "postures": postures, "services": services, "workloadPort": wport, "spans": spans,
            "base": rel(base), "logCfg": log_cfg, "traceCfg": trace_cfg, "metricCfg": metric_cfg,
            "callsites": callsites, "observed": obs_by_posture, "windows": windows,
            "scanner": {"go": rel(src) if go else None, "levelSwitch": switch}}


# --------------------------------------------------------------------------- TeaStore

TEA_EV = REPO / "tmp" / "teastore16-evidence" / "x" / "teastore-candidate-pilot-v1" / "runs" / "no-fault-cost"
TEA_RT = SIBLINGS / "observability-placement-runtime-teastore-sys" / "modules" / "teastore"
TEA_UP = REPO / "upstream" / "teastore"


def _env_dict(env):
    """Compose `environment` as a mapping or a list of KEY=VALUE (compose spec) -> dict."""
    if isinstance(env, dict):
        return {k: ("" if v is None else str(v)) for k, v in env.items()}
    out = {}
    for item in env or []:
        k, _, v = str(item).partition("=")
        out[k] = v
    return out


def _merge_service(a, b):
    out = dict(a)
    for k, v in (b or {}).items():
        if k == "environment":
            env = _env_dict(out.get("environment"))
            env.update(_env_dict(v))
            out["environment"] = env
        else:
            out[k] = v
    return out


def compose_services(files):
    svc = {}
    for f in files:
        d = yaml.safe_load(Path(f).read_text()) or {}
        for s, v in (d.get("services") or {}).items():
            svc[s] = _merge_service(svc.get(s, {}), v or {})
    return svc


def fixed_ports(ports):
    out = []
    for x in ports or []:
        if isinstance(x, dict):
            if x.get("published"):
                out.append(str(x["published"]))
        else:
            x = str(x)
            if ":" in x:
                out.append(x.rsplit(":", 1)[0].split(":")[-1])
    return out


def maven_modules(root):
    """artifactId -> (dir, [in-repo dependency artifactIds]) from every pom.xml under root (xml.etree)."""
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    mods = {}
    for pom in root.rglob("pom.xml"):
        try:
            t = ET.parse(str(pom)).getroot()
        except ET.ParseError:
            continue
        aid = t.find("m:artifactId", ns)
        gid = t.find("m:groupId", ns)
        if gid is None:
            gid = t.find("m:parent/m:groupId", ns)
        if aid is None:
            continue
        deps = []
        for d in t.findall("m:dependencies/m:dependency", ns):
            dg, da = d.find("m:groupId", ns), d.find("m:artifactId", ns)
            if dg is not None and da is not None and gid is not None and dg.text == gid.text:
                deps.append(da.text)
        mods[aid.text] = (pom.parent, deps)
    return mods


def teastore(scan=True):
    postures = ("none", "selected", "full")
    cells = {p: _cell(TEA_EV, "b01-*-%s" % p) for p in postures}
    base = _cell(TEA_EV, "b02-*-full")
    if any(c is None for c in cells.values()) or base is None:
        return {"sut": "teastore", "blocked": "missing TeaStore cells"}
    if not TEA_RT.is_dir() or yaml is None:
        return {"sut": "teastore", "blocked": "runtime worktree %s or PyYAML missing" % TEA_RT}
    cdir = TEA_RT / "deployment" / "compose"
    basefiles = [cdir / "docker-compose_kieker.yaml", cdir / "docker-compose_rabbitmq.yaml", cdir / "isolation.override.yaml"]
    overrides = {"none": TEA_RT / "postures" / "none.override.yaml", "selected": cdir / "compiled-selected.override.yaml",
                 "full": cdir / "compiled-full.override.yaml"}
    comp = {p: compose_services(basefiles + [overrides[p]]) for p in postures}
    services = {s: {"image": d.get("image"), "fixedPorts": fixed_ports(d.get("ports"))} for s, d in comp["full"].items()}
    spans = [(r["trace_id"], r["span_id"], r.get("parent_span_id"), r["service"])
             for r in json.loads((base / "traces.json").read_text())]
    # configured level: slf4j-simple default unless the tree overrides it
    override = [rel(p) for p in TEA_UP.rglob("simplelogger.properties")] + [rel(p) for p in TEA_UP.rglob("logging.properties")]
    java_svcs = {s for s, d in services.items() if (d["image"] or "").startswith("descartesresearch/teastore-")
                 and image_role(d["image"], s)[0] is None}
    mods = maven_modules(TEA_UP)
    roots = {}
    for s in java_svcs:
        if s not in mods:
            continue
        seen, todo = set(), [s]
        while todo:
            a = todo.pop()
            if a in seen or a not in mods:
                continue
            seen.add(a)
            todo.extend(mods[a][1])
        roots[s] = [str(mods[a][0] / "src") for a in sorted(seen)]
    java = run_java_scanner(roots) if scan else None
    log_cfg, trace_cfg, metric_cfg, callsites = {}, {}, {}, {}
    closures = {p: set(json.loads((c / "posture-proof.json").read_text()).get("closureGroups") or []) for p, c in cells.items()}
    for s, d in services.items():
        j = (java or {}).get(s)
        callsites[s] = dict(j["calls"]) if j else None
        for p in postures:
            env = comp[p].get(s, {}).get("environment") or {}
            if s in java_svcs:
                log_cfg[(s, p)] = {"threshold": None if override else "info",
                                   "available": ("trace", "debug", "info", "warn", "error"),
                                   "source": ("level override files present: %s" % override) if override else
                                   "slf4j-simple default INFO (no simplelogger.properties in upstream tree); Tomcat JUL default INFO (assumed)",
                                   "framework": "slf4j-simple + Tomcat JUL"}
                kieker = bool(env.get("RABBITMQ_HOST")) and env.get("RABBITMQ_HOST") != "unset"
                grp = "aspectj:%s" % s
                trace_cfg[(s, p)] = (kieker and grp in closures[p],
                                     "Kieker %s (RABBITMQ_HOST=%s, dockerbase start.sh); %s %s posture closure" % (
                                         "enabled" if kieker else "disabled", env.get("RABBITMQ_HOST"), grp,
                                         "in" if grp in closures[p] else "not in"))
                if j is not None:
                    metric_cfg[(s, p)] = (bool(j["metricImports"]), "javac imports: %s" % (j["metricImports"] or "no metric library"))
                else:
                    metric_cfg[(s, p)] = (None, "source not scanned")
            else:
                log_cfg[(s, p)] = {"threshold": None, "available": ALL_LEVELS,
                                   "source": "third-party server image; level not configured in compose", "framework": "?"}
                trace_cfg[(s, p)] = (False, "no trace exporter configured for this container")
                metric_cfg[(s, p)] = (None, "third-party image; metrics endpoint not determined from config")
    obs_by_posture, windows = {}, {}
    for p, c in cells.items():
        rc = json.loads((c / "receipt.json").read_text())
        win = (epoch(rc["window"]["measurementStartedAt"]), epoch(rc["window"]["measurementEndedAt"]))
        windows[p] = win
        obs = new_obs()
        for s in services:
            lf = c / ("%s.log" % s)
            if lf.exists():
                recs, st = SYM.parse_stream(lf.read_text(errors="replace").splitlines(), JVM_LAYOUTS)
                lc = log_counts(recs, st, win, timed=False)
                for cls in CLASSES:
                    put(obs, s, "log:" + cls, lc[cls]["window"], lc[cls]["capture"], True,
                        "measurement-window capture of docker stdout/stderr", lf, frameworks=lc[cls]["frameworks"])
            else:
                for cls in CLASSES:
                    put(obs, s, "log:" + cls, None, None, False,
                        "service log not captured (harness captures auth and persistence only)", None)
        tw, tc = Counter(), Counter()
        tr = c / "traces.json"
        for r in json.loads(tr.read_text()):
            tc[r["service"]] += 1
            if win[0] <= r["timestamp"] <= win[1]:
                tw[r["service"]] += 1
        for s in services:
            put(obs, s, "trace", tw[s], tc[s], True, "Kieker AMQP consumer (all Kieker-emitting services)", tr)
        res = c / "resources.json"
        mw, mc, covered = Counter(), Counter(), set()
        if res.exists():
            for smp in json.loads(res.read_text())["samples"]:
                for k in smp["containers"]:
                    covered.add(k["service"])
                    mc[k["service"]] += 1
                    if win[0] <= smp["completedAtEpoch"] <= win[1]:
                        mw[k["service"]] += 1
        for s in services:
            if s in covered:
                put(obs, s, "metric:runtime", mw[s], mc[s], True, "docker stats cost probe (no-fault cells)", res)
            else:
                put(obs, s, "metric:runtime", None, None, False,
                    "excluded from the cost probe; cgroup samples not in this lineage", None)
            put(obs, s, "metric:app", None, None, False, "no application-metric collector in the TeaStore harness", None)
        led = c / "journey-ledger.jsonl"
        n = 0
        for line in led.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                n += len(row.get("requests") or [])
        obs["__entry__"]["ledger"] = {"window": n, "capture": n, "complete": True, "note": "journey-ledger request rows",
                                      "evidence": rel(led)}
        obs_by_posture[p] = {"cell": rel(c), "obs": obs}
    return {"sut": "teastore", "postures": postures, "services": services, "workloadPort": None, "spans": spans,
            "base": rel(base), "logCfg": log_cfg, "traceCfg": trace_cfg, "metricCfg": metric_cfg,
            "callsites": callsites, "observed": obs_by_posture, "windows": windows,
            "scanner": {"java": sorted(roots) if java else None, "levelOverrides": override}}


# --------------------------------------------------------------------------- OTel Demo

OTEL_EV = REPO / "tmp" / "otel-v3-evidence" / "runs" / "no-fault-cost"
OTEL_UP = REPO / "upstream" / "opentelemetry-demo"
OTEL_H = REPO / "tmp" / "otel-v2-admission" / "modules" / "otel-demo"
INTERP = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:?[-?])([^}]*))?\}")   # compose-spec interpolation


def dotenv(path):
    env = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def interpolate(obj, env):
    if isinstance(obj, str):
        def sub(m):
            v = env.get(m.group(1))
            if m.group(2) in (":-", "-") and not v:
                return interpolate(m.group(3), env)
            return v if v is not None else ""
        for _ in range(3):
            obj = INTERP.sub(sub, obj)
        return obj
    if isinstance(obj, list):
        return [interpolate(x, env) for x in obj]
    if isinstance(obj, dict):
        return {k: interpolate(v, env) for k, v in obj.items()}
    return obj


def otel_span_edges(path):
    """Base-run span ids from the debug exporter: [(trace, span, parent, service)] (service = adapter catalog name)."""
    spans, kind, in_res, res, svc, cur = [], None, False, {}, None, None

    def flush():
        if cur and svc and cur.get("trace") and cur.get("id"):
            spans.append((cur["trace"], cur["id"], cur.get("parent"), svc))

    with open(path, errors="replace") as fh:
        for raw in fh:
            s = ADP._payload(raw.rstrip("\r\n")).strip()
            if not s:
                continue
            last = s.rsplit("\t", 1)[-1]
            if last.startswith(("ResourceSpans #", "ResourceMetrics #", "ResourceLog #")):
                flush()
                cur = None
                kind = "spans" if last.startswith("ResourceSpans") else None
                in_res, res, svc = False, {}, None
                continue
            if "\tinfo\t" in s or "\twarn\t" in s or "\terror\t" in s:
                flush()
                cur = None
                continue
            if kind != "spans":
                continue
            if s == "Resource attributes:":
                in_res = True
                continue
            if s.startswith("ScopeSpans #"):
                flush()
                cur = None
                if in_res:
                    in_res = False
                    svc = ADP.catalog_service(res["service.name"])[0] if "service.name" in res else None
                continue
            if in_res:
                if s.startswith("-> "):
                    k, _, v = s[3:].partition(": ")
                    res[k] = ADP._attr_value(v)
                continue
            if s.startswith("Span #"):
                flush()
                cur = {}
                continue
            if cur is not None and ":" in s:
                k, _, v = s.partition(":")
                k, v = k.strip(), v.strip()
                if k == "Trace ID":
                    cur["trace"] = v
                elif k == "Parent ID":
                    cur["parent"] = v or None
                elif k == "ID":
                    cur["id"] = v
    flush()
    return spans


def otel(scan=True, log=lambda *a: None):
    postures = ("none", "selected", "async", "full")
    cells = {p: _cell(OTEL_EV, "b01-*-%s" % p) for p in postures}
    base = _cell(OTEL_EV, "b02-*-full")
    if any(c is None for c in cells.values()) or base is None:
        return {"sut": "otel", "blocked": "missing OTel cells"}
    if yaml is None:
        return {"sut": "otel", "blocked": "PyYAML missing"}
    env = dotenv(OTEL_UP / ".env")
    files = [OTEL_UP / "docker-compose.yml"]
    overlays = []
    if OTEL_H.is_dir():
        overlays = [OTEL_H / "deployment" / "compose.otel-placement.yml", OTEL_H / "deployment" / "compose.candidate-postures.yml"]
        files += [f for f in overlays if f.exists()]
    comp = interpolate(compose_services(files), env)
    services = {s: {"image": d.get("image"), "fixedPorts": fixed_ports(d.get("ports"))} for s, d in comp.items()}
    lay = ADP.LAYOUTS["otel-demo-candidate-pilot-v3"]
    closures = {p: set(lay["closures"][p]) for p in postures}
    app = set(ADP.APP_SERVICES)
    led0 = json.loads((cells["full"] / "request-ledger.json").read_text())
    url = led0.get("url", "")
    wport = url.split("://", 1)[-1].split("/", 1)[0].rsplit(":", 1)[-1] if url else None
    log("otel: base-run span edges %s" % rel(base))
    spans = otel_span_edges(base / "otelcol.log")
    # source scans: Go modules + Java (adservice)
    go_res, java = {}, None
    if scan:
        for s in sorted(app):
            d = OTEL_UP / "src" / s
            if (d / "go.mod").exists():
                g = run_go_scanner(d)
                if g:
                    go_res[s] = g
        jr = {s: [str(OTEL_UP / "src" / s / "src")] for s in sorted(app) if (OTEL_UP / "src" / s / "src" / "main" / "java").is_dir()}
        java = run_java_scanner(jr) if jr else None
    otelcfg = yaml.safe_load((OTEL_UP / "src" / "otelcollector" / "otelcol-config.yml").read_text())
    selfscrape = any(k.startswith("prometheus") for k in (otelcfg.get("receivers") or {})) and any(
        r.startswith("prometheus") for r in ((otelcfg.get("service") or {}).get("pipelines") or {}).get("metrics", {}).get("receivers", []))
    log_cfg, trace_cfg, metric_cfg, callsites = {}, {}, {}, {}
    for s in services:
        g = go_res.get(s)
        cs = None
        static = None
        if g:
            bins = list(g["binaries"].values())
            calls = Counter()
            for b in bins:
                calls.update(b["calls"])
            cs = dict(calls)
            if g.get("staticLevels"):
                static = g["staticLevels"][0]
        elif java and s in java:
            cs = dict(java[s]["calls"])
        callsites[s] = cs
        for p in postures:
            if s in app:
                if static:
                    log_cfg[(s, p)] = {"threshold": static["level"], "available": ALL_LEVELS,
                                       "source": "level set in source %s:%s (go/ast)" % (static["file"], static["func"]),
                                       "framework": static["api"]}
                else:
                    log_cfg[(s, p)] = {"threshold": None, "available": ALL_LEVELS,
                                       "source": "no configured level found in compose or scanned source", "framework": "?"}
                trace_cfg[(s, p)] = (s in closures[p], "posture closure (%s)" % lay["source"])
                metric_cfg[(s, p)] = (s in closures[p], "SDK %s under posture closure" % ("enabled" if s in closures[p] else "disabled"))
            else:
                log_cfg[(s, p)] = {"threshold": None, "available": ALL_LEVELS,
                                   "source": "third-party image; level not configured in compose", "framework": "?"}
                trace_cfg[(s, p)] = (False, "not in the posture catalog: no trace exporter configured")
                if s == "otelcol":
                    metric_cfg[(s, p)] = (bool(selfscrape), "otelcol-config.yml prometheus self-scrape receiver %s" % (
                        "in the metrics pipeline" if selfscrape else "absent"))
                else:
                    metric_cfg[(s, p)] = (None, "third-party image; metrics endpoint not determined from config")
    parsed, obs_by_posture, windows = {}, {}, {}
    for p, c in cells.items():
        log("otel: parsing %s" % rel(c / "otelcol.log"))
        with open(c / "otelcol.log", errors="replace") as fh:
            parsed[p] = ADP.parse_otelcol(fh)
    bridged = {s for p in parsed for s, recs in parsed[p]["logs"].items() if recs}
    for p, c in cells.items():
        pr = parsed[p]
        led = json.loads((c / "request-ledger.json").read_text())
        win = (float(led["startedAtEpoch"]), float(led["endedAtEpoch"]))
        windows[p] = win
        obs = new_obs()
        ol = c / "otelcol.log"
        for s in services:
            sp = pr["spans"].get(s, [])
            put(obs, s, "trace", sum(1 for x in sp if win[0] <= x[0] <= win[1]), len(sp), True,
                "collector debug exporter (every OTLP export)", ol)
            ex = pr["exports"].get(s, {})
            nw = sum(1 for ts in ex.values() for t in ts if win[0] <= t <= win[1])
            nc = sum(len(ts) for ts in ex.values())
            if s == "otelcol":
                k = pr["stats"].get("collectorResources", 0)
                put(obs, s, "metric:app", None, k, False, "collector self-metric resources (no timestamp parsed)", ol,
                    completeCapture=True)
            elif s in app:
                put(obs, s, "metric:app", nw, nc, True, "OTLP metric exports (metric x export timestamp)", ol)
            else:
                put(obs, s, "metric:app", None, None, False,
                    "receiver-scraped metrics carry no service.name; not attributed by the parser", None)
            recs = pr["logs"].get(s, [])
            lc = log_counts(recs, {}, win, timed=True)
            complete = s in closures[p] and s in bridged
            for cls in CLASSES:
                put(obs, s, "log:" + cls, lc[cls]["window"], lc[cls]["capture"], complete and cls != "undefined",
                    "OTLP log records only (container stdout not retained); complete iff SDK on and a log bridge seen",
                    ol, frameworks=lc[cls]["frameworks"])
        res = json.loads((c / "resources.json").read_text())
        covered = set(res.get("before", {}).get("services", {})) & set(res.get("after", {}).get("services", {}))
        for s in services:
            if s in covered:
                put(obs, s, "metric:runtime", 2, 2, True, "Docker cumulative CPU counter at both window edges",
                    c / "resources.json")
            else:
                put(obs, s, "metric:runtime", None, None, False, "not counted by the harness CPU counters", None)
        obs["__entry__"]["ledger"] = {"window": len(led["requests"]), "capture": len(led["requests"]), "complete": True,
                                      "note": "request-ledger rows", "evidence": rel(c / "request-ledger.json")}
        obs_by_posture[p] = {"cell": rel(c), "obs": obs}
    return {"sut": "otel", "postures": postures, "services": services, "workloadPort": wport, "spans": spans,
            "base": rel(base), "logCfg": log_cfg, "traceCfg": trace_cfg, "metricCfg": metric_cfg,
            "callsites": callsites, "observed": obs_by_posture, "windows": windows,
            "scanner": {"go": sorted(go_res), "java": sorted(java) if java else None,
                        "overlays": [rel(f) for f in overlays if f.exists()],
                        "otlpLogBridgeSeen": sorted(bridged), "parseStats": {p: parsed[p]["stats"] for p in parsed}}}


# --------------------------------------------------------------------------- generic projection + cells

def project(sut, s, ch, p, entry, on_route):
    cs = sut["callsites"].get(s)
    if ch == "metric:runtime":
        return {"projection": "possible", "projectionSource": "container-runtime",
                "projectionReason": "cgroup/docker metrics exist for every container"}
    if ch == "metric:app":
        v, why = sut["metricCfg"][(s, p)]
        return {"projection": {True: "possible", False: "not-possible", None: "unknown"}[v],
                "projectionSource": "configuration+source", "projectionReason": why}
    if ch == "trace":
        v, why = sut["traceCfg"][(s, p)]
        return {"projection": {True: "possible", False: "not-possible", None: "unknown"}[v],
                "projectionSource": "posture-configuration", "projectionReason": why,
                "expected": (s in on_route) if v else None}
    if ch == "ledger":
        return {"projection": "possible", "projectionSource": "harness", "projectionReason": "one row per offered request at the entry"}
    cls = ch.split(":", 1)[1]
    cfg = sut["logCfg"][(s, p)]
    src = "configured-level+app-callsites" if cs is not None else "configured-level-only"
    out = {"projectionSource": src, "appCallSites": None, "configuredLevel": cfg["threshold"], "levelSource": cfg["source"]}
    if cls == "undefined":
        out["appCallSites"] = None if cs is None else cs.get("none", 0)
        out.update(projection="possible", projectionReason="unlevelled stdout is possible for any process")
        return out
    if cs is not None:   # call sites of the class's member levels (all members; refined to passing members below)
        out["appCallSites"] = sum(cs.get(m, 0) for m in CLASS_MEMBERS[cls])
    thr = cfg["threshold"]
    if thr is None:
        out.update(projection="unknown", projectionReason="configured level unknown: " + cfg["source"])
        return out
    if thr == "off":
        out.update(projection="not-possible", projectionReason="logging disabled")
        return out
    members = [m for m in CLASS_MEMBERS[cls] if m in cfg["available"]]
    passing = [m for m in members if SEVERITY[m] >= SEVERITY[thr]]
    if cs is not None:
        out["appCallSites"] = sum(cs.get(m, 0) for m in passing)
    if passing:
        out.update(projection="possible", projectionReason="level %s passes threshold %s" % ("/".join(passing), thr))
    else:
        out.update(projection="not-possible",
                   projectionReason="threshold %s filters %s" % (thr, "/".join(members) or "(no member level in framework)"))
    return out


def gap_reason(c):
    ch = c["channel"]
    if ch == "trace":
        if c.get("expected") is False:
            return "no traffic: not on the driven route in the base run"
        return "on the driven route in the base run, but no span in this cell"
    if ch.startswith("log:"):
        if (c.get("observedCountCapture") or 0) > 0:
            return "emitted only outside the measurement window (start-up / teardown)"
        if c.get("appCallSites") == 0:
            return "no app call site at this level; only library/runtime code could emit"
        if ch == "log:undefined":
            return "no unlevelled output in this cell"
        return "call sites exist but none fired (error/edge paths not exercised by a no-fault run)"
    if ch == "metric:app":
        return "instrumented under this posture, but no data point from this service (no metric instrument, or export silenced)"
    if ch == "metric:runtime":
        return "collector sampled no point in the window"
    return "nothing recorded"


def surprise_reason(c):
    ch = c["channel"]
    fw = c.get("frameworks") or {}
    if c["projection"] == "unknown":
        return "projection unknown (%s); the observation shows it is possible" % c["projectionReason"]
    if ch.startswith("log:"):
        return ("emitted although the configured level filters it (records from %s): a logger the level setting does "
                "not govern, or lines written before the setting takes effect" % (
                    ", ".join("%s %d" % kv for kv in sorted(fw.items())) or "?"))
    if ch == "trace":
        return "spans from a service the posture configuration does not instrument"
    return "observed while the projection said not possible: " + c["projectionReason"]


def build_cells(sut):
    roles, entry, graph = assign_roles(sut["services"], sut["spans"], sut.get("workloadPort"))
    on_route = set(graph["onRoute"])
    cells = []
    for s in sorted(sut["services"]):
        for ch in CHANNELS:
            if ch == "ledger" and s != entry:
                continue
            for p in sut["postures"]:
                pr = project(sut, s, ch, p, entry, on_route)
                ob = sut["observed"][p]["obs"]
                e = ob["__entry__"].get("ledger") if ch == "ledger" else ob.get(s, {}).get(ch)
                w, cap = observed_value(e, "window"), observed_value(e, "capture")
                c = {"sut": sut["sut"], "service": s, "role": roles[s]["role"], "channel": ch, "posture": p}
                c.update(pr)
                c.update({"observedCount": w, "observedCountCapture": cap,
                          "rawCount": None if e is None else e.get("window"),
                          "observationNote": None if e is None else e.get("note"),
                          "evidencePath": None if e is None else e.get("evidence"),
                          "cell": sut["observed"][p]["cell"]})
                if e is not None and e.get("frameworks"):
                    c["frameworks"] = e["frameworks"]
                c["state"] = classify(c["projection"], w)
                c["stateCapture"] = classify(c["projection"], cap)
                if c["state"] == "not-possible" and w is None:
                    c["unconfirmed"] = True
                if c["state"] == "possible-not-observed":
                    c["reason"] = gap_reason(c)
                elif c["state"] == "observed-not-projected":
                    c["reason"] = surprise_reason(c)
                elif c["state"] == UNKNOWN:
                    c["reason"] = (c["observationNote"] or "not collected") if w is None else c["projectionReason"]
                if c["stateCapture"] == "observed-not-projected" and c["state"] != "observed-not-projected":
                    c["reasonCapture"] = "only outside the measurement window; " + surprise_reason(c)
                cells.append(c)
    return cells, roles, entry, graph


def tally(cells, key="state"):
    out = {"all": Counter()}
    for c in cells:
        out["all"][c[key]] += 1
        out.setdefault(c["role"], Counter())[c[key]] += 1
    return {k: {s: v.get(s, 0) for s in STATES + (UNKNOWN,)} for k, v in out.items()}


# --------------------------------------------------------------------------- rendering

def render(result):
    L = ["# Project map (planning artefact; not for the paper)", "",
         "Generated by `research/project-map/project_map.py` from `project_map.json` (%s, commit `%s`). Do not edit by hand: "
         "re-run the script. Not independently reviewed. Scope: **instance** (one retained campaign per SUT, one no-fault "
         "cell per posture; base run = a different no-fault `full` cell)." % (result["generatedAt"], result["gitCommit"]), "",
         "Cell symbols: `+` possible and observed · `o` possible, not observed · `x` not possible · `!` observed but not "
         "projected · `?` unknown (the evidence cannot show it, or projection unknown and nothing observed) · `—` no cell "
         "(ledger exists at the entry only). Each table cell lists one symbol per posture, in the posture order given "
         "above the table. States use the measurement window; the capture-scope counts are reported beside them.", ""]
    for name in ("hotel", "teastore", "otel"):
        r = result["suts"].get(name)
        if r is None:
            continue
        L.append("## %s" % {"hotel": "HotelReservation", "teastore": "TeaStore", "otel": "OTel Demo"}[name])
        L.append("")
        if r.get("blocked"):
            L += ["**Blocked:** %s" % r["blocked"], ""]
            continue
        L.append("Postures (symbol order): **%s**. Base run: `%s`. Observed cells: %s." % (
            " / ".join(r["postures"]), r["baseRun"], ", ".join("`%s`" % v for v in r["observedCells"].values())))
        L.append("")
        g = r["callGraph"]
        L.append("Role rule output (entry `%s`; %d of %d base-run traces are entry-rooted; most common local root `%s`; "
                 "entry agrees with root spans: %s). Cross-service edges on driven traces: %s." % (
                     r["entry"], g["drivenTraces"], g["tracesInBaseRun"], g["mostCommonLocalRoot"],
                     g["entryAgreesWithRootSpans"], ", ".join("%s ×%d" % kv for kv in g["edges"].items()) or "none"))
        if g["spanServicesNotInCompose"]:
            L.append("Span services absent from the compose model: %s." % ", ".join(g["spanServicesNotInCompose"]))
        L.append("")
        L.append("| service | role | rule | " + " | ".join(CHANNELS) + " |")
        L.append("|---|---|---|" + "---|" * len(CHANNELS))
        by = defaultdict(dict)
        for c in r["cells"]:
            by[c["service"]].setdefault(c["channel"], {})[c["posture"]] = c["state"]
        order = sorted(by, key=lambda s: (ROLES.index(r["roles"][s]["role"]), s))
        for s in order:
            row = []
            for ch in CHANNELS:
                if ch not in by[s]:
                    row.append("—")
                else:
                    row.append("`%s`" % "".join(SYMBOL[by[s][ch][p]] for p in r["postures"]))
            L.append("| %s | %s | %s | %s |" % (s, r["roles"][s]["role"], r["roles"][s]["rule"], " | ".join(row)))
        L.append("")
        L.append("Four-state counts (cells = service × channel × posture; denominator %d cells):" % len(r["cells"]))
        L.append("")
        L.append("| scope | group | possible+observed | possible, not observed | not possible (unconfirmed) | observed, not projected | ? | n |")
        L.append("|---|---|---|---|---|---|---|---|")
        for scope, key in (("window", "counts"), ("capture", "countsCapture")):
            for grp in ["all"] + [x for x in ROLES if x in r[key]]:
                t = r[key][grp]
                unc = r["unconfirmed"][grp] if scope == "window" else None
                n = sum(t.values())
                L.append("| %s | %s | %d | %d | %d%s | %d | %d | %d |" % (
                    scope, grp, t["possible-observed"], t["possible-not-observed"], t["not-possible"],
                    " (%d)" % unc if unc is not None else "", t["observed-not-projected"], t[UNKNOWN], n))
        L.append("")
        for st, title in (("possible-not-observed", "Possible, not observed"), ("observed-not-projected", "Observed but not projected")):
            per = defaultdict(list)
            for c in r["cells"]:
                if c["state"] == st:
                    per[(c["service"], c["role"], c["channel"], c["reason"])].append(c["posture"])
            groups = defaultdict(list)
            for (s, role, ch, why), ps in per.items():
                groups[(ch, why, "/".join(ps))].append("%s (%s)" % (s, role))
            L.append("**%s** (%d cells; grouped by channel, reason and postures):" % (title, sum(len(v) for v in per.values())))
            L.append("")
            if not groups:
                L.append("- none")
            for (ch, why, ps), svcs in sorted(groups.items()):
                L.append("- `%s` [%s] %s: %s" % (ch, ps, why, ", ".join(sorted(svcs))))
            L.append("")
        cap = defaultdict(list)
        for c in r["cells"]:
            if c.get("reasonCapture"):
                cap[(c["channel"], c["reasonCapture"], c["posture"])].append("%s (%s)" % (c["service"], c["role"]))
        L.append("**Observed but not projected in the capture scope only** (%d cells; outside the measurement window):"
                 % sum(len(v) for v in cap.values()))
        L.append("")
        if not cap:
            L.append("- none")
        for (ch, why, p), svcs in sorted(cap.items()):
            L.append("- `%s` [%s] %s: %s" % (ch, p, why, ", ".join(sorted(svcs))))
        L.append("")
        unk = Counter()
        for c in r["cells"]:
            if c["state"] == UNKNOWN:
                unk[(c["channel"].split(":")[0], c["reason"])] += 1
        L.append("**Unknown (`?`) cells by reason** (%d):" % sum(unk.values()))
        L.append("")
        for (ch, why), n in sorted(unk.items(), key=lambda kv: -kv[1]):
            L.append("- %s: %s — %d" % (ch, why, n))
        L.append("")
    L.append("## Defaults and limits")
    L.append("")
    L.append("Every engineering default is in the docstring of `project_map.py` and in `project_map.json` → `defaults`. "
             "Main limits: one cell per posture (n = 1, so `o` is a single-run absence, not a property); call-site counts "
             "are lower bounds (no vendor/library code; Go struct-field loggers unresolved); Kotlin, Python, Node, .NET, "
             "C++, Ruby, PHP, Rust sources are not parsed (`configured-level-only`); the role vocabulary is a fixed table "
             "of server products; TeaStore's registry has no spans, so 'off route' there means 'not on a traced route'.")
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------- self-check

def self_check():
    fails, n = [], [0]

    def check(name, got, want):
        n[0] += 1
        if got != want:
            fails.append("%s: got %r want %r" % (name, got, want))

    # 1. classifier truth table, one planted case per state (+ unknown and unconfirmed not-possible)
    check("possible+observed", classify("possible", 5), "possible-observed")
    check("possible, not observed", classify("possible", 0), "possible-not-observed")
    check("not possible", classify("not-possible", 0), "not-possible")
    check("observed, not projected", classify("not-possible", 3), "observed-not-projected")
    check("observed, projection unknown", classify("unknown", 2), "observed-not-projected")
    check("unknown: not observable", classify("possible", None), UNKNOWN)
    check("not possible, unconfirmed", classify("not-possible", None), "not-possible")
    check("partial capture zero", observed_value({"window": 0, "capture": 0, "complete": False}, "window"), None)
    check("complete zero", observed_value({"window": 0, "capture": 0, "complete": True}, "window"), 0)
    # 2. a planted SUT through roles, projection and cells
    services = {"gw": {"image": "acme/gateway:1", "fixedPorts": ["8080"]}, "svc": {"image": "acme/app:1", "fixedPorts": []},
                "leaf": {"image": "acme/app:1", "fixedPorts": []}, "db": {"image": "docker.io/library/mongo:5.0", "fixedPorts": ["27017"]},
                "helper": {"image": "acme/app:1", "fixedPorts": []}, "mq": {"image": "rabbitmq:3-management", "fixedPorts": ["5672"]},
                "jaeger": {"image": "jaegertracing/all-in-one:1.60", "fixedPorts": ["16686"]}}
    spans = [("t1", "a", None, "gw"), ("t1", "b", "a", "svc"), ("t1", "c", "b", "leaf"),
             ("t2", "x", None, "helper")]
    postures = ("p",)
    full = {"window": 0, "capture": 0, "complete": True, "note": "fixture", "evidence": None}

    def ob(n, complete=True):
        return dict(full, window=n, capture=n, complete=complete)
    obs = new_obs()
    for s in services:
        for ch in CHANNELS[:-1]:
            obs[s][ch] = ob(0)
    obs["gw"]["trace"] = ob(7)            # planted: possible and observed
    obs["leaf"]["trace"] = ob(0)          # planted: possible, not observed
    obs["db"]["trace"] = ob(0)            # planted: not possible
    obs["svc"]["log:info"] = ob(3)        # planted: observed but not projected (threshold fatal)
    obs["helper"]["trace"] = ob(0, complete=False)   # planted: unknown (partial capture)
    obs["__entry__"]["ledger"] = ob(10)
    sut = {"sut": "fixture", "postures": postures, "services": services, "spans": spans, "workloadPort": None,
           "callsites": {s: None for s in services},
           "logCfg": {(s, "p"): {"threshold": "fatal" if s == "svc" else "info", "available": ALL_LEVELS, "source": "fixture"}
                      for s in services},
           "traceCfg": {(s, "p"): (s in ("gw", "leaf", "helper"), "fixture") for s in services},
           "metricCfg": {(s, "p"): (False, "fixture") for s in services},
           "observed": {"p": {"cell": "fixture", "obs": obs}}}
    cells, roles, entry, graph = build_cells(sut)
    want_roles = {"gw": "entry", "svc": "interior", "leaf": "leaf", "db": "data store", "helper": "helper",
                  "mq": "broker", "jaeger": "telemetry"}
    for s, r in want_roles.items():
        check("role %s" % s, roles.get(s, {}).get("role"), r)
    st = defaultdict(dict, {(c["service"], c["channel"]): c for c in cells})
    check("cell gw trace", st[("gw", "trace")].get("state"), "possible-observed")
    check("cell leaf trace", st[("leaf", "trace")].get("state"), "possible-not-observed")
    check("cell leaf trace expected", st[("leaf", "trace")].get("expected"), True)
    check("cell db trace", st[("db", "trace")].get("state"), "not-possible")
    check("cell svc log:info", st[("svc", "log:info")].get("state"), "observed-not-projected")
    check("cell helper trace", st[("helper", "trace")].get("state"), UNKNOWN)
    check("cell helper trace expected", st[("helper", "trace")].get("expected"), False)
    check("ledger only at entry", sorted(c["service"] for c in cells if c["channel"] == "ledger"), ["gw"])
    check("cell gw ledger", st[("gw", "ledger")].get("state"), "possible-observed")
    # 3. raw levels survive the reused parsers
    recs, _ = SYM.parse_stream(["2026-10-01T08:33:58Z INF services/x.go:1 > hello",
                                "2026-10-01T08:33:58Z WRN services/x.go:2 > careful",
                                "2026/10/01 08:33:58 plain go log line",
                                "2026/10/01 08:33:58 ERROR: [transport] boom"], HOTEL_LAYOUTS)
    check("zerolog/go-log classes", [level_class(r["level"]) for r in recs], ["info", "warn", "undefined", "error"])
    recs, _ = SYM.parse_stream(["[main] INFO a.b.C - started", "[main] DEBUG a.b.C - detail",
                                "01-Oct-2026 08:33:58.123 WARNING [main] org.x.Y msg"], JVM_LAYOUTS)
    check("slf4j/JUL classes", [level_class(r["level"]) for r in recs], ["info", "other", "warn"])
    check("otlp severity 9", level_class(otlp_severity("Info(9)", "INFO")), "info")
    check("otlp severity 0 no text", level_class(otlp_severity("Unspecified(0)", "")), "undefined")
    check("otlp severity 17", level_class(otlp_severity("Error(17)", "")), "error")
    # 4. projection threshold logic
    cfg = {(("s", "p")): {"threshold": "info", "available": ("trace", "debug", "info", "warn", "error"), "source": "t"}}
    fx = {"callsites": {"s": {"info": 1, "trace": 4}}, "logCfg": cfg}
    check("other filtered without fatal", project(fx, "s", "log:other", "p", None, set())["projection"], "not-possible")
    check("warn passes info", project(fx, "s", "log:warn", "p", None, set())["projection"], "possible")
    check("undefined always", project(fx, "s", "log:undefined", "p", None, set())["projection"], "possible")
    check("other call sites count passing members only", project(dict(fx, logCfg={("s", "p"): dict(cfg[("s", "p")], available=ALL_LEVELS)}), "s", "log:other", "p", None, set())["appCallSites"], 0)
    if fails:
        print("SELF-CHECK FAILED (%d):" % len(fails))
        for f in fails:
            print("  " + f)
        return 1
    print("self-check ok: %d assertions (planted case per state + unknown + unconfirmed; 7 roles; level parsing; thresholds)" % n[0])
    return 0


# --------------------------------------------------------------------------- main

def git_commit():
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return "?"


def defaults_from_doc():
    doc = __doc__.split("Engineering defaults", 1)[1].split("\n", 3)[3]
    items, cur = [], []
    for line in doc.splitlines():
        if line.startswith("- "):
            if cur:
                items.append(" ".join(cur))
            cur = [line[2:].strip()]
        elif line.strip() and cur:
            cur.append(line.strip())
    if cur:
        items.append(" ".join(cur))
    return items


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--no-callsites", action="store_true")
    ap.add_argument("--only", choices=("hotel", "teastore", "otel"), action="append")
    ap.add_argument("--out-dir", default=str(HERE))
    a = ap.parse_args(argv)
    if a.self_check:
        return self_check()
    if self_check() != 0:
        return 1
    log = lambda m: sys.stderr.write(m + "\n")
    scan = not a.no_callsites
    builders = {"hotel": lambda: hotel(scan), "teastore": lambda: teastore(scan), "otel": lambda: otel(scan, log)}
    result = {"generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "gitCommit": git_commit(),
              "script": rel(__file__), "states": list(STATES) + [UNKNOWN], "channels": list(CHANNELS),
              "defaults": defaults_from_doc(), "suts": {}}
    for name in a.only or ("hotel", "teastore", "otel"):
        log("building %s" % name)
        sut = builders[name]()
        if sut.get("blocked"):
            result["suts"][name] = {"blocked": sut["blocked"]}
            log("  BLOCKED: %s" % sut["blocked"])
            continue
        cells, roles, entry, graph = build_cells(sut)
        unconf = {"all": 0}
        for c in cells:
            if c.get("unconfirmed"):
                unconf["all"] += 1
                unconf[c["role"]] = unconf.get(c["role"], 0) + 1
        for r in ROLES:
            unconf.setdefault(r, 0)
        result["suts"][name] = {
            "postures": list(sut["postures"]), "entry": entry, "roles": roles, "callGraph": graph,
            "baseRun": sut["base"], "observedCells": {p: v["cell"] for p, v in sut["observed"].items()},
            "windows": {p: list(w) for p, w in sut["windows"].items()},
            "scanner": sut["scanner"],
            "callsites": {s: (None if v is None else {"raw": v, "byClass": class_callsites(v)}) for s, v in sut["callsites"].items()},
            "counts": tally(cells), "countsCapture": tally(cells, "stateCapture"), "unconfirmed": unconf,
            "cells": cells}
        print("== %s: entry %s" % (name, entry))
        for s in sorted(roles, key=lambda x: (ROLES.index(roles[x]["role"]), x)):
            print("  %-24s %-10s %s" % (s, roles[s]["role"], roles[s]["rule"]))
        t = result["suts"][name]["counts"]["all"]
        print("  cells %d: %s" % (len(cells), ", ".join("%s %d" % (k, v) for k, v in t.items())))
    out = Path(a.out_dir)
    (out / "project_map.json").write_text(json.dumps(result, indent=1, sort_keys=False, default=str) + "\n")
    (out / "PROJECT_MAP.md").write_text(render(result))
    log("wrote %s and %s" % (rel(out / "project_map.json"), rel(out / "PROJECT_MAP.md")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
