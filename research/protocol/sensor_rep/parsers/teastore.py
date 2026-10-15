"""TeaStore parser: one candidate cell `runs/<regime>/<bNN-OO-posture>/` -> events. Per-SUT code lives only here.

Reused, unchanged, by path: `symptoms.parse_stream` + `JVM_LAYOUTS` (log4j/slf4j-simple, Tomcat JUL, MariaDB,
JVM throwable header), `symptoms.template_id`, `symptoms.op_token`, `symptoms.epoch`; the cell selection, window and
span reading of `symptoms.teastore_cell` / `teastore_cells` (`:511-561`); the journey-ledger reading of
`visibility.teastore_ledger_rows` (`:126-136`).

Engineering defaults (recorded):
- cells: `runs/*/*` directories with `candidate-validation.json`, `.blocked-evidence` excluded (symptoms.teastore_cells);
  valid = cellStatus "valid". The `.operational/` docker-log dumps are NOT read (as the frozen bags: retained in 8 of 40
  run dirs of a5 only; CLAUDE.md "Modality scope").
- clocks: logs and spans wall (epoch); the journey ledger on the barrier-relative monotonic clock (base 0). Wall base and
  old-rule t0 = receipt `measurementStartedAt` (symptoms.teastore_cell's t0); fault window = intervention
  actualOnsetWall..actualOffsetWall (wall) and actualOnset/OffsetMonotonicOffsetSeconds (mono).
- log4j lines carry no timestamp, so they never fall in a window (symptoms: "cell level only"); counted in stats.
- span error = status_code not in (None, 200, 0) (symptoms.teastore_cell). Span service = traces.json `service`.
- ledger: one event per request of every journey-terminal record; token `<routeId>:ok|failed`, ok = outcome
  succeeded and status 200; entry service `webui`.
- no metric channel is retained in these cells (`metric` present False -> `—`).
"""
import json
import statistics
from pathlib import Path

from . import common
from ..events import Event, level_class, stream_meta

SUT = "teastore"
ENTRY = "webui"
COLLECTS = {"L": ("none", "selected", "full", "async", "auth-persistence-webui"), "Tsel": ("selected",),
            "T": ("full", "kieker-native")}


def cell_dirs(x):
    return [d for d in sorted(Path(x).glob("runs/*/*"))
            if d.is_dir() and not d.name.endswith(".blocked-evidence") and (d / "candidate-validation.json").exists()]


def parse_cell(d, population):
    S = common.symptoms()
    d = Path(d)
    v = json.loads((d / "candidate-validation.json").read_text())
    rc = json.loads((d / "receipt.json").read_text())
    rk = v["runKey"]
    posture = rk["posture"]
    ivp = d / "intervention.json"
    iv = json.loads(ivp.read_text()) if ivp.exists() else None
    target = iv.get("service") if iv else None
    kind = None
    if iv and iv.get("commandVector"):
        kind = iv["commandVector"][-2]
    cell = common.new_cell(SUT, population, d, posture, rk["regime"], rk["block"], v["cellStatus"] == "valid",
                           target, kind)
    w = rc["window"]
    ms, me = S.epoch(w["measurementStartedAt"]), S.epoch(w["measurementEndedAt"])
    cell["base"] = {"wall": ms, "mono": 0.0}
    cell["t0"] = {"wall": ms, "mono": None}
    cell["duration"] = me - ms
    if iv and iv.get("actualOnsetWall") and iv.get("actualOffsetWall"):
        cell["fault"] = {"wall": (S.epoch(iv["actualOnsetWall"]), S.epoch(iv["actualOffsetWall"])),
                         "mono": (float(iv["actualOnsetMonotonicOffsetSeconds"]),
                                  float(iv["actualOffsetMonotonicOffsetSeconds"]))}
    ev, stats = cell["events"], cell["stats"]
    logs = sorted(d.glob("*.log"))
    cell["channels"]["log"] = {"present": bool(logs), "collectors": ["docker-container-stdout"],
                               "resolution": "per-record", "services": [p.stem for p in logs],
                               "file": logs[0].name if logs else None}
    untimed = 0
    for p in logs:
        svc = p.stem
        records, st = S.parse_stream(p.read_text(errors="replace").splitlines(), S.JVM_LAYOUTS)
        for k, val in st.items():
            stats["log:" + k] = stats.get("log:" + k, 0) + val
        for r in records:
            if r["framework"] == "jvm-throwable":
                continue
            tid = S.template_id(r["framework"], r["level"], r["key"], r["msg"])
            lv = level_class(r["framework"], r["level"])
            m = stream_meta(SUT, posture, "log", svc, "application", "docker-container-stdout", "wall", "per-record", lv)
            if r["t"] is None:
                untimed += 1
            ev.append(Event("log", svc, tid, r["t"], 1.0, m))
    stats["log:untimedRecords"] = untimed
    cell["channels"]["metric"] = {"present": False, "collectors": [], "file": None}
    tr = d / "traces.json"
    cell["channels"]["span"] = {"present": tr.exists(), "collectors": ["kieker-amqp"], "resolution": "per-record",
                                "file": "traces.json"}
    if tr.exists():
        n = 0
        for r in json.loads(tr.read_text()):
            tok = S.op_token(r["operation"])
            m = stream_meta(SUT, posture, "span", r["service"], "application", "kieker-amqp", "wall", "per-record")
            ev.append(Event("span", r["service"], tok, r["timestamp"], r["duration_s"], m))
            if r.get("status_code") not in (None, 200, 0):
                ev.append(Event("span", r["service"], tok + ":error", r["timestamp"], r["duration_s"], m))
            n += 1
        stats["spans"] = n
    lp = d / "journey-ledger.jsonl"
    cell["channels"]["ledger"] = {"present": lp.exists(), "collectors": ["journey-ledger"], "resolution": "per-record",
                                  "file": "journey-ledger.jsonl"}
    if lp.exists():
        m = stream_meta(SUT, posture, "ledger", ENTRY, "harness", "journey-ledger", "mono", "per-record")
        for line in lp.open():
            r = json.loads(line)
            for q in r.get("requests") or []:
                s = q["actualStartMonotonic"]
                ok = q["outcome"] == "succeeded" and q["statusCode"] == 200
                ev.append(Event("ledger", ENTRY, "%s:%s" % (q.get("routeId", "?"), "ok" if ok else "failed"), s,
                                (q["actualEndMonotonic"] - s) * 1000.0, m))
    return cell


def pseudo_offsets(cells):
    """symptoms.teastore_cells: onset = median (fault start - t0) over EVERY parsed cell with a fault window (invalid ones
    included), length = median hold; per clock (mono: the intervention's own offsets, base 0)."""
    out = {}
    for clock in ("wall", "mono"):
        on = [c["fault"][clock][0] - c["base"][clock] for c in cells if c["fault"]]
        ln = [c["fault"][clock][1] - c["fault"][clock][0] for c in cells if c["fault"]]
        if on:
            a, b = statistics.median(on), statistics.median(ln)
            out[clock] = (a, a + b)
    return out


def family(channel, collector, posture):
    if channel == "log":
        return "L"
    if channel == "span":
        return "Tsel" if posture == "selected" else "T" if posture in ("full", "kieker-native") else None
    return None


def old_extra_fire(cells, wins, fired):
    """The frozen bags' `log:rate:<tid>:high` (symptoms.calibrate, relevance R2): a template count in the window at or
    above the median + max(K·1.4826·MAD, 2) of the other no-fault cells' pseudo windows. Adds kind `rate_high`."""
    from ..catch import old_rate_high
    from ..vectors import select

    def counts(c):
        out = {}
        for (ch, svc, tok), s in c["streams"].items():
            if ch == "log":
                n = len(select(s, wins[c["cell"]][0]))
                if n:
                    out[(svc, tok)] = n
        return out
    nf = {}
    for c in cells:
        if c["valid"] and c["target"] is None:
            per = {svc: {} for svc in c["channels"]["log"].get("services", [])}
            for (svc, tok), n in counts(c).items():
                per.setdefault(svc, {})[tok] = n
            nf[c["cell"]] = per
    for c in cells:
        if c["cell"] not in fired:
            continue
        for sensor in old_rate_high(counts(c), nf, c["cell"]):
            fired[c["cell"]].setdefault(sensor, set()).add("rate_high")
