#!/usr/bin/env python3
"""Fault visibility map (user question, 2026-10-01): for every fault class we have run, which observers see it?

Offline only. Reads retained evidence and the frozen symptom bags; launches nothing. Every detector is imported from the
script that scored its population, unchanged, by path:

- entry point: `research/hotel-selected/ledger_check.py`'s rule (failed in-window request, or in-window median latency above the
  pre-window median by max(3 x MAD, 1 ms)). Hotel calls `ledger_check.cell` itself; TeaStore (journey ledger), OTel (request
  ledger) and the earlier corpus (load-generator log, failure half only) apply `ledger_rule`, a transcription of the same lines,
  checked equal to `ledger_check.cell` on every Hotel fault cell before any other number is computed.
- Hotel sensors: `research/lmt-pilot/lmt_detect.py` as configured by each population's own analysis script (lmt2: as-is;
  sel1: `research/hotel-selected/analyse.py`; int1: `research/hotel-interior/analyse.py`). G3 on every family, spans included.
- TeaStore and the earlier corpus: `research/s4-conjunction/relevance.py`'s `Generation.firing` over the frozen bags
  `tmp/s4-symptoms/20260927T100543Z` (the paper's Table 1 run). G3 on log templates and metrics; spans not calibrated.
- "outside" = a sensor of a service other than the faulted one (G2, the paper's rule); "own" = the faulted service's own
  sensors under the same detector, G3 still applied (`ownNoG3` in the JSON drops G3 too).

    /usr/bin/python3 -B research/visibility-map/visibility.py            # writes visibility.json and MAP.md beside this file
    /usr/bin/python3 -B research/visibility-map/visibility.py --self-check

Engineering defaults (recorded, not preregistered): a column "catches" a row when it catches a strict majority of the row's
episodes that collect it (2k > n); `visibilityClassAnyEpisode` repeats the derivation with k >= 1. Unknown is `None` / `—`.
The LOW-WORKLOAD flag (earlier corpus) fires below 1 span per second, any service, inside the fault window.
"""
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
BAGS = REPO / "tmp" / "s4-symptoms" / "20260927T100543Z"
RELEVANCE_OUT = REPO / "tmp" / "s4-relevance" / "20260927T102324Z" / "relevance.json"
GOLD_ROOT = (REPO / ".." / "test-repos" / "TeaStore" / "data" / "experiments" / "by_server" / "fb14srv6").resolve()

HOTEL = {
    "hotel-lmt2": {"x": "tmp/hotellmt2-evidence/x", "analysis": "lmt-pilot/lmt_detect.py", "attr": None,
                   "committed": ("lmt-pilot/out/lmt_detect.lmt2.json", ()), "ledgerCommitted": None,
                   "postures": ("none", "logs", "metrics", "full")},
    "hotel-sel1": {"x": "tmp/hotelsel1-evidence/x", "analysis": "hotel-selected/analyse.py", "attr": "detect",
                   "committed": ("hotel-selected/out.sel1.json", ("detect",)),
                   "ledgerCommitted": "hotel-selected/ledger_check.sel1.json",
                   "postures": ("none", "metrics", "selected", "full")},
    "hotel-int1": {"x": "tmp/hotelint1-evidence/x", "analysis": "hotel-interior/analyse.py", "attr": "detect",
                   "committed": ("hotel-interior/out.int1.json", ("detect",)),
                   "ledgerCommitted": "hotel-interior/ledger_check.int1.json",
                   "postures": ("none", "metrics", "selected", "full")},
}
TEASTORE = {
    "teastore-T16": {"gen": "T-16", "campaign": "tmp/teastore16-evidence/x/teastore-candidate-pilot-v1",
                     "note": "campaign #16, 27 cells: the paper's Table 1 TeaStore population (9 per class, 3 under full)"},
    "teastore-Tnew": {"gen": "T-new", "campaign": "tmp/teastore-e3-user-a5-evidence/teastore-candidate-pilot-v3-user",
                      "note": "epoch-3 user rung a5 (e3-user); a-p-w posture excluded (A15) as in relevance.py; blocked cells invalid"},
}
OTEL = {"otel-run3": "tmp/otel-run3-evidence", "otel-v3": "tmp/otel-v3-evidence"}
POSTURE_ORDER = ("none", "logs", "metrics", "sample-zero", "selected", "async", "full", "kieker-native")
ENTRY = {"hotel": "frontend", "teastore": "webui", "otel": "frontend"}   # the service the workload's requests enter
FAMILIES = ("L", "M", "Mm", "S", "Tsel", "T", "Csel", "C")
LOW_WORKLOAD_SPANS_PER_S = 1.0     # engineering default for the LOW-WORKLOAD flag (any service, inside the fault window)
ACTUATED = {"cpu-throttle-effect": ("sys_cpu", "sys_psi_cpu", "cpu")}   # fault class -> the target resource it sets
STOPPING = ("pause", "stop")          # fault kinds that stop the target (a container verb, read from the recorded command)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rel(p):
    p = Path(p).resolve()
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return Path("..", p.relative_to(REPO.parent)).as_posix()


# --------------------------------------------------------------------------- the entry-point rule

LEDGER = _load("vm_ledger_check", RESEARCH / "hotel-selected" / "ledger_check.py")


def ledger_rule(pre, inside):
    """ledger_check.cell's rule on (ms, ok) pairs, line for line. Returns None (unknown) where ledger_check would raise:
    no successful pre-window request, or no request started in the window."""
    pre_ms = [m for m, ok in pre if ok]
    if not pre_ms or not inside:
        return None
    med = statistics.median(pre_ms)
    mad = statistics.median(abs(m - med) for m in pre_ms)
    in_med = statistics.median(m for m, _ in inside)
    failed = sum(1 for _, ok in inside if not ok)
    return {"inWindow": len(inside), "failedInWindow": failed, "preMedianMs": med, "inMedianMs": in_med,
            "shows": failed > 0 or in_med > med + max(3 * mad, 1.0)}


def split(rows, a, b):
    """rows: (start, ms, ok). The ledger_check split: start < a pre; a <= start <= b inside."""
    pre = [(ms, ok) for s, ms, ok in rows if s < a]
    inside = [(ms, ok) for s, ms, ok in rows if a <= s <= b]
    return pre, inside


def hotel_ledger_rows(attempt):
    out = []
    for line in (attempt / "opportunity-ledger.jsonl").open():
        row = json.loads(line)
        start = row["actualStartMonotonic"]
        out.append((start, (row["actualEndMonotonic"] - start) * 1000.0,
                    row["outcome"] == "completed" and row.get("statusCode") == 200))
    return out


def teastore_ledger_rows(cell_dir):
    """Journey ledger: one row per request of every journey-terminal record (barrier-relative monotonic seconds).
    ok = outcome succeeded and status 200 (the journey ledger's word for Hotel's `completed`)."""
    out, outcomes = [], Counter()
    for line in (cell_dir / "journey-ledger.jsonl").open():
        r = json.loads(line)
        for q in r.get("requests") or []:
            s = q["actualStartMonotonic"]
            outcomes["%s/%s" % (q["outcome"], q["statusCode"])] += 1
            out.append((s, (q["actualEndMonotonic"] - s) * 1000.0, q["outcome"] == "succeeded" and q["statusCode"] == 200))
    return out, outcomes


def otel_ledger_rows(cell_dir):
    led = json.loads((cell_dir / "request-ledger.json").read_text())
    base = led["startedAtEpoch"]       # taken by run_workload right after `barrier = time.monotonic()` (candidate_remote.py)
    return base, [(q["startedAtEpoch"] - base, (q["endedAtEpoch"] - q["startedAtEpoch"]) * 1000.0,
                   q["status"] == 200 and q["error"] is None) for q in led["requests"]]


def gold_ledger_rows(run_dir):
    """Earlier corpus: the load generator's own log, one `[HTTP nnn]` line per request, stamped at whole seconds after the
    request returned. No start time, no latency: only the failure half of the rule can be applied."""
    out = []
    p = run_dir / "load_gen.log"
    if not p.exists():
        return None
    for line in p.read_text(errors="replace").splitlines():
        if not line.startswith("[") or "[HTTP " not in line:
            continue
        stamp = line[1:line.index("]")]
        code = line.split("[HTTP ", 1)[1].split("]", 1)[0]
        t = dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S%z").timestamp()
        out.append((t, code == "200"))
    return out


_TRACE_TIMES = {}


def gold_workload(run_dir, t0, w0, w1):
    """Was there traffic? Spans (any service, Kieker records in traces.json) before and inside the window, and the load
    generator's own cycle count (its `Finished after N cycles` line)."""
    if run_dir not in _TRACE_TIMES:
        tr = run_dir / "traces.json"
        _TRACE_TIMES[run_dir] = [(x["timestamp"], x["service"]) for x in json.loads(tr.read_text())] if tr.exists() else None
    ts = _TRACE_TIMES[run_dir]
    cycles, ok, req = None, 0, 0
    lg = run_dir / "load_gen.log"
    if lg.exists():
        for line in lg.read_text(errors="replace").splitlines():
            if "Finished after " in line:
                cycles = int(line.split("Finished after ", 1)[1].split()[0])
            if "[HTTP " in line:
                req += 1
                ok += line.split("[HTTP ", 1)[1].split("]", 1)[0] == "200"
    if ts is None:
        return {"spansTotal": None, "spansPreWindow": None, "spansInWindow": None, "loadGenCycles": cycles,
                "loadGenRequests": req, "loadGenOk": ok, "spanServices": None}
    return {"spansTotal": len(ts), "spansPreWindow": sum(1 for t, _ in ts if t0 <= t < w0),
            "spansInWindow": sum(1 for t, _ in ts if w0 <= t <= w1), "loadGenCycles": cycles, "windowSeconds": w1 - w0,
            "loadGenRequests": req, "loadGenOk": ok, "spanServices": sorted({sv for _, sv in ts})}


def gold_failure_half(rows, w0, w1):
    pre = [ok for t, ok in rows if t < int(w0)]
    inside = [ok for t, ok in rows if int(w0) <= t <= w1]
    return {"inWindow": len(inside), "failedInWindow": sum(1 for ok in inside if not ok),
            "preWindow": len(pre), "failedPreWindow": sum(1 for ok in pre if not ok),
            "shows": (sum(1 for ok in inside if not ok) > 0) if inside else None}


# --------------------------------------------------------------------------- classification

def hit(k, n, rule):
    if not n or k is None:
        return False
    return 2 * k > n if rule == "majority" else k >= 1


def classify(ledger, fams, rule="majority"):
    """ledger: (k, n) over known episodes or None; fams: {fam: {"n", "outside", "own"}} for collected families only.
    Returns (visibilityClass, classIfEntryMisses)."""
    scored = {f: v for f, v in fams.items() if v["n"]}
    out = any(hit(v["outside"], v["n"], rule) for v in scored.values())
    own = any(hit(v["own"], v["n"], rule) for v in scored.values())
    interior = None if not scored else ("interior-only-outside" if out else "own-service-only" if own else "unseen")
    if ledger is None or not ledger[1]:
        return "—", interior or "—"
    if hit(ledger[0], ledger[1], rule):
        return "entry-visible", interior or "—"
    return (interior or "—"), interior or "—"


def frac(k, n):
    return None if not n else [k, n]


# --------------------------------------------------------------------------- Hotel

def hotel_population(name, cfg, checks):
    x = REPO / cfg["x"]
    mod = _load("vm_" + name.replace("-", "_"), RESEARCH / cfg["analysis"])
    D = mod if cfg["attr"] is None else getattr(mod, cfg["attr"])
    attempts = sorted((x / "runs").glob("**/attempt-01"))
    if not attempts:
        sys.exit("no runs/**/attempt-01 under %s" % x)
    orig, memo = D.bag, {}

    def memo_bag(cell):
        if id(cell) not in memo:
            memo[id(cell)] = orig(cell)
        return memo[id(cell)]
    D.bag = memo_bag
    cells = [D.load_cell(a) for a in attempts]
    scored = D.score(cells)
    inadm = {fam: {tuple(s.split(":", 2)) for s in v["inadmissible"]} for fam, v in scored["falseAlarms"].items()}
    fam_postures = dict(D.FAMILY_POSTURES)
    # target ops (for the caller-client-span flag): every span operation token each service emits in this population
    ops = defaultdict(set)              # server-span operation tokens per service, from the span.kind tag of full cells
    for a, c in zip(attempts, cells):
        if c["posture"] == "full" and (a / "traces-normalized.json").exists():
            for e in json.loads((a / "traces-normalized.json").read_text())["events"]:
                if (e.get("tags") or {}).get("span.kind") == "server":
                    ops[e["service"]].add(D.sym.op_token(e["operation"]))
    request_path = sorted(s for c in cells if c["posture"] == "full" for s in c["spans"])
    request_path = sorted(set(request_path))
    # ledger pseudo window for no-fault cells: median offsets of the fault cells (same rule as lmt_detect's pseudo window)
    offs = []
    for a in attempts:
        fr = a / "fault-receipt.json"
        if fr.exists():
            f = json.loads(fr.read_text())
            b0 = json.loads((a / "opportunity-plan.json").read_text())["barrierMonotonic"]
            offs.append((f["appliedMonotonic"] - b0, f["revertingMonotonic"] - b0))
    pa, pb = statistics.median(o[0] for o in offs), statistics.median(o[1] for o in offs)
    episodes, nf_ledger = [], []
    mism = []
    for a, c in zip(attempts, cells):
        if not c["valid"]:
            continue
        rows = hotel_ledger_rows(a)
        if c["target"] is None:
            b0 = json.loads((a / "opportunity-plan.json").read_text())["barrierMonotonic"]
            nf_ledger.append(ledger_rule(*split(rows, b0 + pa, b0 + pb)))
            continue
        receipt = json.loads((a / "fault-receipt.json").read_text())
        mine = ledger_rule(*split(rows, receipt["appliedMonotonic"], receipt["revertingMonotonic"]))
        theirs = LEDGER.cell(a)
        if mine != theirs:
            mism.append(rel(a))
        fired = {tuple(s) for r in D.bag(c) for s in r["sensors"]}
        fams = {}
        for fam, postures in fam_postures.items():
            if c["posture"] not in postures:
                continue
            mine_f = {s for s in fired if s[0] == fam}
            fams[fam] = {"outside": sorted("%s:%s:%s" % s for s in mine_f if s[1] != c["target"] and s not in inadm[fam]),
                         "own": sorted("%s:%s:%s" % s for s in mine_f if s[1] == c["target"] and s not in inadm[fam]),
                         "ownNoG3": sorted("%s:%s:%s" % s for s in mine_f if s[1] == c["target"])}
        # symptom kinds behind outside T*/C* and M catches (the library's own symbol functions on the same window)
        kinds = Counter()
        w = c["windowWall"]
        span_sym = {s: D.sym.span_symbols(sp, c["t0"], w) for s, sp in c["spans"].items()}
        for fam, v in fams.items():
            for sensor in v["outside"]:
                _, s, nm = sensor.split(":", 2)
                if fam in ("T", "Tsel", "C", "Csel"):
                    for k in span_sym.get(s, {}):
                        if k.startswith("span:%s:" % nm) and not k.endswith(":present"):
                            kinds["%s:%s" % (fam, k.rsplit(":", 1)[1])] += 1
                elif fam == "M":
                    for k in D.sym.metric_symbols(c["metrics"][s]["cpu"], "cpu", c["t0"], w):
                        kinds["M:%s" % k.rsplit(":", 1)[1]] += 1
        episodes.append({"cell": rel(a), "posture": c["posture"], "block": c["block"], "regime": c["regime"],
                         "target": c["target"], "faultKind": receipt.get("faultKind"), "ledger": mine,
                         "families": fams, "outsideSymptomKinds": dict(sorted(kinds.items())),
                         "callerSpansToTarget": sorted({x for v in fams.values() for x in v["outside"]
                                                        if x.split(":")[0] in ("T", "Tsel", "C", "Csel")
                                                        and x.split(":", 2)[2] in ops.get(c["target"], set())})})
    if mism:
        raise SystemExit("ledger_rule != ledger_check.cell on %d Hotel cells: %s" % (len(mism), mism[:3]))
    # reproduction checks: my outside counts == the population's own score(), == its committed output
    repro, committed_ok = [], []
    cpath, keys = cfg["committed"]
    committed = json.loads((RESEARCH / cpath).read_text())
    for k in keys:
        committed = committed[k]
    for regime, fams in scored["classes"].items():
        for fam, v in fams.items():
            eps = [e for e in episodes if e["regime"] == regime and fam in e["families"]]
            caught = sum(1 for e in eps if e["families"][fam]["outside"])
            repro.append((regime, fam, (caught, len(eps)) == (v["caught"], v["n"])))
            cv = committed["classes"].get(regime, {}).get(fam, {})
            committed_ok.append((regime, fam, (cv.get("caught"), cv.get("n")) == (v["caught"], v["n"])))
    if not all(ok for *_, ok in repro):
        raise SystemExit("%s: outside counts do not reproduce score(): %s" % (name, [r for r in repro if not r[2]]))
    ledger_committed = None
    if cfg["ledgerCommitted"]:
        mine_agg = LEDGER.main(x)
        ledger_committed = json.loads((RESEARCH / cfg["ledgerCommitted"]).read_text()) == json.loads(json.dumps(mine_agg))
    checks[name] = {
        "ledgerRuleEqualsLedgerCheckCell": "%d/%d fault cells" % (len(episodes), len(episodes)),
        "outsideCountsReproduceScore": "%d/%d (regime, family) cells" % (sum(ok for *_, ok in repro), len(repro)),
        "scoreEqualsCommittedOutput": "%d/%d (regime, family) cells vs research/%s" % (
            sum(ok for *_, ok in committed_ok), len(committed_ok), cpath),
        "ledgerCheckMainEqualsCommitted": ledger_committed if ledger_committed is not None else "— (no committed ledger_check output)",
    }
    fa = {fam: {"noFaultWindows": v["noFaultWindows"], "inadmissible": v["inadmissible"]}
          for fam, v in scored["falseAlarms"].items()}
    nf_known = [r for r in nf_ledger if r is not None]
    return {
        "system": "hotel", "evidence": cfg["x"], "postures": list(cfg["postures"]), "familyPostures": fam_postures,
        "detector": ("research/lmt-pilot/lmt_detect.py as-is" if cfg["attr"] is None else
                     "research/lmt-pilot/lmt_detect.py as configured by research/%s" % cfg["analysis"]) +
                    " (G2 outside, G3 on every family, spans included)",
        "commands": ["/usr/bin/python3 -B research/%s %s" % (cfg["analysis"], cfg["x"]),
                     "/usr/bin/python3 -B research/hotel-selected/ledger_check.py %s" % cfg["x"]],
        "familyFalseAlarms": fa, "requestPath": request_path,
        "ledgerFalseAlarms": {"shows": sum(1 for r in nf_known if r["shows"]), "n0": len(nf_known),
                              "unknown": len(nf_ledger) - len(nf_known),
                              "pseudoWindowBarrierOffsets": [pa, pb]},
        "episodes": episodes, "cells": len(cells), "validCells": sum(1 for c in cells if c["valid"]),
    }


# --------------------------------------------------------------------------- TeaStore and the earlier corpus (frozen bags)

def bag_family(sensor, posture):
    kind, rest = sensor.split(":", 1)
    if kind == "log":
        return "L"
    if kind == "metric":
        return "M" if sensor.endswith(":cpu") else "Mm" if sensor.endswith(":mem") else "M?"
    if kind == "span":
        return "T" if posture in ("full", "kieker-native") else "Tsel" if posture == "selected" else "T?"
    return None


def fam_id(sensor, fam):
    _, s, nm = sensor.split(":", 2)
    return "%s:%s:%s" % (fam, s, nm)


def bags_population(name, gen, G, REL, campaign, relevance_out, checks, gold=False):
    """Episodes = valid fault cells of the generation (a-p-w excluded, A15). Family collected per posture: a family is
    collected in a posture if any row of that posture (fault or pseudo window) carries one of its symbols."""
    collected = defaultdict(set)
    for unit_rows in list(G.fault.values()) + list(G.pseudo.values()):
        for r in unit_rows.values():
            for sym in r["symbols"]:
                sensor, _ = REL.sensor_of(sym, r["service"])
                if sensor:
                    collected[bag_family(sensor, r["posture"])].add(r["posture"])
    if gen.startswith("T-"):
        collected["L"] |= set(G.postures)    # auth.log and persistence.log are retained in every cell, symbols or not
    fam_postures = {f: tuple(p for p in POSTURE_ORDER if p in v) for f, v in collected.items() if f}
    ops = defaultdict(set)
    for unit_rows in G.fault.values():
        for r in unit_rows.values():
            for sym in r["symbols"]:
                if sym.startswith("span:"):
                    ops[r["service"]].add(sym[len("span:"):].rsplit(":", 1)[0])
    episodes = []
    span_fa = {}

    def span_false_alarms(regime, posture):
        """Spans are not calibrated by relevance.py; their no-fault firing rate is computed here (same G3 arithmetic as
        Generation.admissible: inadmissible iff fired in more than floor(tau * n0) calibrating pseudo windows)."""
        key = (regime, posture)
        if key not in span_fa:
            units = G.pseudo_units(regime, (posture,))
            fired = Counter()
            for u in units:
                fired.update({x for r in G.pseudo[u].values() for x in G.firing(r, True) if x.startswith("span:")})
            span_fa[key] = (fired, len(units))
        return span_fa[key]
    by_cell_R = {}
    if relevance_out is not None:
        by_cell_R = {e["cell"]: e for e in relevance_out["generations"][gen]["R"]["episodes"]}
    gold_rows = {}
    on_off = []
    for c in sorted(G.fault):
        m = G.meta[c]
        tgt, posture = m["target"], m["posture"]
        fired_out, fired_own, fired_own_raw = defaultdict(set), defaultdict(set), defaultdict(set)
        kinds = Counter()
        for s, row in G.fault[c].items():
            adm = G.firing(row, True)
            raw = G.firing(row, False)
            for sensor in raw:
                fam = bag_family(sensor, posture)
                if REL.sensor_service(sensor) == tgt:
                    fired_own_raw[fam].add(fam_id(sensor, fam))
                    if sensor in adm:
                        fired_own[fam].add(fam_id(sensor, fam))
                elif sensor in adm:
                    fired_out[fam].add(fam_id(sensor, fam))
            pf = row["window"].get("pseudoFor")
            for sym in row["symbols"]:
                sensor, symptom = REL.sensor_of(sym, s)
                if sensor and symptom and REL.sensor_service(sensor) != tgt and sensor in adm \
                        and G.admissible(sym, s, row["regime"], pf):
                    fam = bag_family(sensor, posture)
                    k = ("template" if sym.startswith("log:template:") else "rate") if fam == "L" else sym.rsplit(":", 1)[1]
                    kinds["%s:%s" % (fam, k)] += 1
        fams = {}
        fired_fa, n0 = span_false_alarms(m["regime"], posture)
        for fam, postures in fam_postures.items():
            if posture in postures:
                fams[fam] = {"outside": sorted(fired_out[fam]), "own": sorted(fired_own[fam]), "ownNoG3": sorted(fired_own_raw[fam])}
                if fam in ("T", "Tsel"):
                    gate = math.floor(G.tau * n0)
                    fa = {x: fired_fa.get("span:" + x.split(":", 1)[1], 0) for x in fired_out[fam]}
                    fams[fam]["outsideSpanFalseAlarms"] = {x: [k, n0] for x, k in sorted(fa.items())}
                    fams[fam]["outsideIfSpansGated"] = sorted(x for x, k in fa.items() if k <= gate)
        if c in by_cell_R:      # the Table 1 run's R(p) (outside) and R+ (outside + own), span-exporting episodes
            R = {fam_id(x, bag_family(x, posture)) for x in by_cell_R[c]["R"]}
            Rp = {fam_id(x, bag_family(x, posture)) for x in by_cell_R[c]["Rplus"]}
            mine_R = {x for v in fams.values() for x in v["outside"]}
            mine_Rp = mine_R | {x for v in fams.values() for x in v["own"]}
            checks.setdefault(name, {}).setdefault("_R", []).append((c, R == mine_R and Rp == mine_Rp))
        ep = {"cell": c, "posture": posture, "block": m["block"], "regime": m["regime"], "target": tgt,
              "families": fams, "outsideSymptomKinds": dict(sorted(kinds.items())),
              "callerSpansToTarget": sorted({x for v in fams.values() for x in v["outside"]
                                             if x.split(":")[0] in ("T", "Tsel") and x.split(":", 2)[2] in ops.get(tgt, set())})}
        if gold:
            run = GOLD_ROOT / c
            md = json.loads((run / "metadata.json").read_text())
            toks = md["fault"]["fault_command"].split()
            ep["faultKind"] = "pause" if "pause" in toks else "stop" if "stop" in toks else "degradation"
            rows = gold_ledger_rows(run)
            gold_rows[c] = rows
            w0, w1 = m["window"]["start"], m["window"]["end"]
            ep["ledger"] = None
            ep["ledgerFailureHalf"] = gold_failure_half(rows, w0, w1) if rows is not None else None
            ep["workload"] = gold_workload(run, md["start_time"], w0, w1)
        else:
            d = REPO / campaign / c
            iv = json.loads((d / "intervention.json").read_text())
            ep["faultKind"] = iv["commandVector"][-2] if iv.get("commandVector") else None
            rows, outcomes = teastore_ledger_rows(d)
            a, b = iv["actualOnsetMonotonicOffsetSeconds"], iv["actualOffsetMonotonicOffsetSeconds"]
            on_off.append((a, b))
            plan = json.loads((d / "journey-ledger.plan.json").read_text())
            skew = (REL_epoch(iv["actualOnsetWall"]) - REL_epoch(plan["barrierAt"])) - a
            ep["ledger"] = ledger_rule(*split(rows, a, b))
            ep["ledgerOutcomes"] = dict(outcomes)
            ep["clockSkewSeconds"] = skew
            ep["journeyPath"] = sorted(x.split(":", 1)[1] for x in plan["expectedPath"]["requiredLogicalSensors"])
        episodes.append(ep)
    # no-fault ledger windows
    nf = []
    if gold:
        for u, unit_rows in G.pseudo.items():
            r0 = next(iter(unit_rows.values()))
            rows = gold_rows.get(u[0]) or gold_ledger_rows(GOLD_ROOT / u[0])
            if rows is None:
                continue
            gold_rows[u[0]] = rows
            md = json.loads((GOLD_ROOT / u[0] / "metadata.json").read_text())
            nf.append({"pseudoFor": r0["window"].get("pseudoFor"), "res": gold_failure_half(rows, u[1], u[2]),
                       "workload": gold_workload(GOLD_ROOT / u[0], md["start_time"], u[1], u[2])})
    else:
        pa, pb = statistics.median(o[0] for o in on_off), statistics.median(o[1] for o in on_off)
        for cell in sorted({u[0] for u in G.pseudo}):
            rows, _ = teastore_ledger_rows(REPO / campaign / cell)
            nf.append({"pseudoFor": None, "res": ledger_rule(*split(rows, pa, pb))})
    if name in checks and "_R" in checks[name]:
        rr = checks[name].pop("_R")
        checks[name]["outsideAndOwnEqualTable1RunRandRplus"] = "%d/%d span-exporting episodes vs %s" % (
            sum(ok for _, ok in rr), len(rr), rel(RELEVANCE_OUT))
        if not all(ok for _, ok in rr):
            raise SystemExit("%s: R / R+ mismatch against the Table 1 run: %s" % (name, [c for c, ok in rr if not ok][:3]))
    if not gold:
        skews = [abs(e["clockSkewSeconds"]) for e in episodes]
        checks.setdefault(name, {})["ledgerAndInterventionShareBarrierClock"] = "max |wall-derived - monotonic| onset offset %.4f s over %d episodes" % (max(skews), len(skews))
    known = [x for x in nf if x["res"] is not None]
    return {
        "system": "teastore", "evidence": rel(GOLD_ROOT) if gold else campaign,
        "postures": [p for p in POSTURE_ORDER if p in G.postures], "familyPostures": fam_postures,
        "detector": "research/s4-conjunction/relevance.py Generation.firing over %s (G2 outside; G3 on log templates and metrics; spans not calibrated)" % rel(BAGS),
        "commands": ["/usr/bin/python3 -B research/s4-conjunction/relevance.py %s --out tmp/s4-relevance" % rel(BAGS)] +
                    ([] if gold else ["(journey ledger) /usr/bin/python3 -B research/visibility-map/visibility.py"]),
        "ledgerFalseAlarms": ({"rule": "failure half only", "byFamily": {}} if gold else
                              {"shows": sum(1 for x in known if x["res"]["shows"]), "n0": len(known), "unknown": len(nf) - len(known)}),
        "_nf": nf,
        "episodes": episodes,
    }


def REL_epoch(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


# --------------------------------------------------------------------------- OTel (ledger only)

def otel_population(name, root, checks):
    root = REPO / root
    cells = []
    for d in sorted((root / "runs").glob("*/*")):
        if not d.is_dir():
            continue
        rc = json.loads((d / "receipt.json").read_text())
        cells.append((d, rc))
    offs = []
    for d, rc in cells:
        if (d / "intervention.json").exists():
            iv = json.loads((d / "intervention.json").read_text())
            offs.append((iv["actualOnsetMonotonicOffsetSeconds"], iv["actualOffsetMonotonicOffsetSeconds"]))
    pa, pb = statistics.median(o[0] for o in offs), statistics.median(o[1] for o in offs)
    episodes, nf = [], []
    for d, rc in cells:
        if rc.get("state") != "valid":
            continue
        rk = rc["runKey"]
        _, rows = otel_ledger_rows(d)
        ivp = d / "intervention.json"
        if not ivp.exists():
            nf.append(ledger_rule(*split(rows, pa, pb)))
            continue
        iv = json.loads(ivp.read_text())
        episodes.append({"cell": rel(d), "posture": rk["posture"], "block": rk["block"], "regime": rk["regime"],
                         "target": iv["service"], "faultKind": "pause" if iv["scenario"].endswith("pause") else None,
                         "ledger": ledger_rule(*split(rows, iv["actualOnsetMonotonicOffsetSeconds"],
                                                       iv["actualOffsetMonotonicOffsetSeconds"])),
                         "families": {}, "outsideSymptomKinds": {}, "callerSpansToTarget": []})
    known = [r for r in nf if r is not None]
    checks[name] = {"cells": len(cells), "validCells": sum(1 for _, rc in cells if rc.get("state") == "valid"),
                    "clockMapping": "intervention offsets are relative to `barrier = time.monotonic()`, taken immediately before "
                                    "run_workload's `started = time.time()` (.controller/candidate_remote.py); mapped as ledger startedAtEpoch + offset"}
    return {"system": "otel", "evidence": rel(root), "postures": sorted({e["posture"] for e in episodes}, key=POSTURE_ORDER.index),
            "familyPostures": {}, "detector": "— (no detection adapter for OTel Demo)",
            "commands": ["/usr/bin/python3 -B research/visibility-map/visibility.py"],
            "ledgerFalseAlarms": {"shows": sum(1 for r in known if r["shows"]), "n0": len(known), "unknown": len(nf) - len(known),
                                  "pseudoWindowBarrierOffsets": [pa, pb]},
            "episodes": episodes}


# --------------------------------------------------------------------------- rows

def build_rows(pops):
    rows = []
    for pname, P in pops.items():
        order = P["postures"]
        for regime in sorted({e["regime"] for e in P["episodes"]}):
            eps = [e for e in P["episodes"] if e["regime"] == regime]
            tgt = eps[0]["target"]
            kind = eps[0].get("faultKind")
            led_known = [e for e in eps if e.get("ledger") is not None]
            ledger = None if (not led_known or P["system"] == "teastore" and P["evidence"].startswith("..")) else \
                (sum(1 for e in led_known if e["ledger"]["shows"]), len(led_known))
            fams = {}
            for fam in FAMILIES:
                fe = [e for e in eps if fam in e["families"]]
                if not fe:
                    continue
                out_c, own_c = Counter(), Counter()
                for e in fe:
                    out_c.update(e["families"][fam]["outside"])
                    own_c.update(e["families"][fam]["own"])
                fams[fam] = {"n": len(fe),
                             "outside": sum(1 for e in fe if e["families"][fam]["outside"]),
                             "own": sum(1 for e in fe if e["families"][fam]["own"]),
                             "ownNoG3": sum(1 for e in fe if e["families"][fam]["ownNoG3"]),
                             "outsideSensors": sorted(out_c.items(), key=lambda kv: (-kv[1], kv[0])),
                             "ownSensors": sorted(own_c.items(), key=lambda kv: (-kv[1], kv[0]))}
                if any("outsideIfSpansGated" in e["families"][fam] for e in fe):
                    fa = {}
                    for e in fe:
                        for x, v in e["families"][fam]["outsideSpanFalseAlarms"].items():
                            fa.setdefault(x, v)
                    fams[fam]["outsideIfSpansGated"] = sum(1 for e in fe if e["families"][fam]["outsideIfSpansGated"])
                    fams[fam]["outsideSpanFalseAlarms"] = {x: fa[x] for x, _ in fams[fam]["outsideSensors"]}
            # C/Csel are catalogue subsets of T/Tsel: they never change the derivation, reported only
            derive = {f: v for f, v in fams.items() if f not in ("C", "Csel")}
            cls, if_miss = classify(ledger, derive, "majority")
            gated = {f: dict(v, outside=v.get("outsideIfSpansGated", v["outside"])) for f, v in derive.items()}
            _, if_miss_gated = classify(None, gated, "majority")
            cls_any, _ = classify(ledger, derive, "any")
            postures = {}
            for p in order:
                pe = [e for e in eps if e["posture"] == p]
                if not pe:
                    continue
                lk = [e for e in pe if e.get("ledger") is not None]
                sens = Counter()
                for e in pe:
                    sens.update({x for f, v in e["families"].items() if f not in ("C", "Csel") for x in v["outside"]})
                postures[p] = {
                    "n": len(pe),
                    "ledger": frac(sum(1 for e in lk if e["ledger"]["shows"]), len(lk)) if ledger is not None else None,
                    "familiesCollected": sorted({f for e in pe for f in e["families"] if f not in ("C", "Csel")}),
                    "outside": frac(sum(1 for e in pe if any(v["outside"] for f, v in e["families"].items() if f not in ("C", "Csel"))), len(pe))
                    if any(e["families"] for e in pe) else None,
                    "anyInclOwn": frac(sum(1 for e in pe if any(v["outside"] or v["own"] for f, v in e["families"].items() if f not in ("C", "Csel"))), len(pe))
                    if any(e["families"] for e in pe) else None,
                    "outsideSensors": sorted(sens.items(), key=lambda kv: (-kv[1], kv[0]))[:8],
                }
            minimal = next((p for p, v in postures.items() if v["outside"] and hit(v["outside"][0], v["outside"][1], "majority")), None)
            minimal_own = next((p for p, v in postures.items() if v["anyInclOwn"] and hit(v["anyInclOwn"][0], v["anyInclOwn"][1], "majority")), None)
            kinds = Counter()
            for e in eps:
                kinds.update(e["outsideSymptomKinds"])
            caller = Counter(x for e in eps for x in e["callerSpansToTarget"])
            row = {"population": pname, "faultClass": regime, "target": tgt, "faultKind": kind, "n": len(eps),
                   "postureEpisodes": {p: v["n"] for p, v in postures.items()},
                   "entryPoint": None if ledger is None else list(ledger),
                   "entryPointUnknown": len(eps) - len(led_known) if ledger is not None else None,
                   "families": fams, "postures": postures,
                   "minimalPostureOutside": minimal, "minimalPostureInclOwn": minimal_own,
                   "visibilityClass": cls, "visibilityClassAnyEpisode": cls_any, "classIfEntryMisses": if_miss,
                   "classIfEntryMissesSpansGated": if_miss_gated if any("outsideIfSpansGated" in v for v in derive.values()) else None,
                   "outsideSymptomKinds": dict(sorted(kinds.items())), "callerSpansToTarget": sorted(caller.items()),
                   "source": {"evidence": P["evidence"], "detector": P["detector"], "commands": P["commands"]}}
            if P["system"] == "teastore" and P["evidence"].startswith(".."):
                fh = [e["ledgerFailureHalf"] for e in eps if e.get("ledgerFailureHalf")]
                known = [r for r in fh if r["shows"] is not None]
                nf = [x["res"] for x in P["_nf"] if regime in (x["pseudoFor"] or [])]
                nf_known = [r for r in nf if r["shows"] is not None]
                row["entryPointFailureHalfOnly"] = {
                    "shows": sum(1 for r in known if r["shows"]), "known": len(known), "n": len(eps),
                    "runsWithNoRequestInWindow": len(fh) - len(known),
                    "runsWithNoRequestInLog": sum(1 for r in fh if r["inWindow"] == 0 and r["preWindow"] == 0),
                    "falseAlarms": [sum(1 for r in nf_known if r["shows"]), len(nf_known)],
                    "baselineWindowsWithNoRequest": len(nf) - len(nf_known),
                    "failedInWindow": [r["failedInWindow"] for r in fh], "inWindowRequests": [r["inWindow"] for r in fh]}
            if any(e.get("workload") for e in eps):
                wl = [e["workload"] for e in eps]
                nfw = [x["workload"] for x in P["_nf"] if regime in (x["pseudoFor"] or []) and x.get("workload")]
                row["workload"] = {
                    "runsWithASpanInWindow": [sum(1 for w in wl if w["spansInWindow"]), len(wl)],
                    "spansInWindowPerRun": [w["spansInWindow"] for w in wl],
                    "spansTotalPerRun": [w["spansTotal"] for w in wl],
                    "loadGenCyclesPerRun": [w["loadGenCycles"] for w in wl],
                    "baselineWindowsWithASpan": [sum(1 for w in nfw if w["spansInWindow"]), len(nfw)],
                    "baselineSpansInWindow": sorted(w["spansInWindow"] for w in nfw),
                    "loadGenOkOfRequestsPerRun": [[w["loadGenOk"], w["loadGenRequests"]] for w in wl],
                    "baselineRunsWithSpansOf": {sv: [sum(1 for w in nfw if sv in (w["spanServices"] or [])), len(nfw)]
                                                for sv in sorted({x.split(":")[1] for f, v in fams.items()
                                                                  if f in ("T", "Tsel") for x, _ in v["outsideSensors"]})},
                    "medianSpansPerSecondInWindow": statistics.median(w["spansInWindow"] / w["windowSeconds"] for w in wl
                                                                      if w.get("windowSeconds"))}
            row["byConstruction"] = by_construction(P, row, eps)
            rows.append(row)
    return rows


def by_construction(P, row, eps):
    """Mechanical flags. Each names the rule; none is a judgement about the fault."""
    flags = []
    wl = row.get("workload")
    if wl and not hit(*wl["runsWithASpanInWindow"], "majority"):
        flags.append("NO-WORKLOAD: in %d of %d runs no span of any service falls in the fault window (spans per run in the "
                     "window %s, in the whole run %s; load generator cycles %s). A catch here is the trace stream ending, "
                     "not the fault" % (wl["runsWithASpanInWindow"][1] - wl["runsWithASpanInWindow"][0],
                                        wl["runsWithASpanInWindow"][1], wl["spansInWindowPerRun"], wl["spansTotalPerRun"],
                                        wl["loadGenCyclesPerRun"]))
    elif wl and wl["medianSpansPerSecondInWindow"] < LOW_WORKLOAD_SPANS_PER_S:
        flags.append("LOW-WORKLOAD: median %.2f spans per second (any service) in the fault window, spans per run in the window "
                     "%s, load generator cycles %s; image_crash in the same corpus has ~17,000 per window"
                     % (wl["medianSpansPerSecondInWindow"], wl["spansInWindowPerRun"], wl["loadGenCyclesPerRun"]))
    if wl:
        logged = [x for x in wl["loadGenOkOfRequestsPerRun"] if x[1]]
        if logged and hit(sum(1 for k, _ in logged if k == 0), len(logged), "majority"):
            flags.append("NO-SUCCESSFUL-REQUEST: in %d of %d runs whose load_gen.log has a request, not one request in the whole "
                         "run returned HTTP 200 (ok/requests per run %s): the system was failing before the fault, so a catch "
                         "here is not separable from that breakage" % (sum(1 for k, _ in logged if k == 0), len(logged),
                                                                        wl["loadGenOkOfRequestsPerRun"]))
        blind = [sv for sv, (k, n) in wl["baselineRunsWithSpansOf"].items() if n and k == 0]
        if blind:
            flags.append("BC-FA-unfailable: outside span sensors of %s catch, but none of the calibrating baseline windows' runs "
                         "holds a span of that service, so their 0 false alarms cannot be otherwise" % ", ".join(blind))
    stop = row["faultKind"] in STOPPING
    entry = ENTRY[P["system"]]
    if row["target"] == entry and row["entryPoint"] and hit(*row["entryPoint"], "majority"):
        flags.append("BC-entry-target: the faulted service is the one the workload's requests enter (%s); the ledger sees "
                     "its own server stop" % entry)
    path = set(P.get("requestPath") or []) | {x for e in eps for x in e.get("journeyPath", [])}
    if stop and row["target"] != entry and row["target"] in path and row["entryPoint"] and hit(*row["entryPoint"], "majority"):
        flags.append("BC-ledger-stopped-on-path: a %s of %s, %s; requests through a stopped service fail or hang" % (
            row["faultKind"], row["target"],
            "a service that emits spans for the workload under full (all of %s)" % ", ".join(P["requestPath"])
            if P.get("requestPath") else "on the login journey's planned path (journey-ledger.plan.json requiredLogicalSensors)"))
    if stop and any(v["own"] for v in row["families"].values()):
        own = sorted({f for f, v in row["families"].items() if v["own"]})
        flags.append("BC-own-stopped: the stopped target's own sensors (%s) fire because it stopped (TBC1/TBC2/TBC7)" % "+".join(own))
    acted = ACTUATED.get(row["faultClass"])
    if acted:
        own = sorted({x for f, v in row["families"].items() if hit(v["own"], v["n"], "majority")
                      for x, _ in v["ownSensors"] if x.split(":", 2)[2] in acted})
        if own:
            flags.append("BC-own-actuator: the catching own sensor reads the resource the fault manipulates on the target "
                         "(%s; the fault sets a CPU quota on that cgroup)" % ", ".join(own))
    if stop and row["callerSpansToTarget"]:
        flags.append("BC-caller-span: outside span catches include callers' client spans to the stopped target (%s)"
                     % ", ".join("%s %d" % kv for kv in row["callerSpansToTarget"][:4]))
    if stop:
        k = row["outsideSymptomKinds"]
        miss = sum(v for x, v in k.items() if x.endswith(":missing_expected"))
        other_t = sum(v for x, v in k.items() if x.split(":")[0] in ("T", "Tsel") and not x.endswith(":missing_expected"))
        if miss and not other_t:
            flags.append("BC-downstream-absent: every outside span firing is `missing_expected` (operations that stop while "
                         "the target is stopped), %d firings" % miss)
        down = sum(v for x, v in k.items() if x in ("M:spike_down", "M:plateau_down"))
        up = sum(v for x, v in k.items() if x in ("M:spike_up", "M:plateau_up"))
        if down and not up:
            flags.append("BC-idle-cpu: every outside CPU firing is a drop (%d), services idling behind a stopped peer" % down)
    if P["system"] == "teastore" and not P["evidence"].startswith("..") and "L" in row["families"]:
        flags.append("TBC5: TeaStore log false alarms are 0 by construction (no-fault cells hold 0 application records), so "
                     "G3 cannot remove a log sensor; logs retained for auth and persistence only")
    return flags


# --------------------------------------------------------------------------- markdown

def kn(x):
    return "—" if x is None else "%d/%d" % tuple(x)


def fam_cell(row, fam):
    v = row["families"].get(fam)
    return "—" if v is None else "%d / %d (n %d)" % (v["outside"], v["own"], v["n"])


NOTES = {
    ("hotel-int1", "geo-delay-effect"): "designed threshold contrast: the 2 ms was chosen between two sensors' thresholds (research/hotel-interior/RESULT.md)",
    ("hotel-int1", "rate-delay-effect"): "designed threshold contrast, as geo-delay; the ledger catches 15/16 under its 3-MAD rule",
}


def gold_entry(fh):
    return "load_gen.log: no request in the window in %d/%d runs; failures in %d/%d of the rest, FA %d/%d" % (
        fh["runsWithNoRequestInWindow"], fh["n"], fh["shows"], fh["known"], fh["falseAlarms"][0], fh["falseAlarms"][1])


def render(out):
    rows = out["rows"]
    L = []
    L.append("# Fault visibility map (offline, 2026-10-01)\n")
    L.append("Generated by `research/visibility-map/visibility.py` (do not hand-edit; rerun it). Output `visibility.json` beside it.")
    L.append("Command: `/usr/bin/python3 -B research/visibility-map/visibility.py` after clearing "
             "`~/Library/Caches/com.apple.python/<repo>/research`. Framework commit at generation: `%s`; python %s. "
             "Scope of every number: **instance** (one host, one campaign or corpus per population; populations never pooled).\n"
             % (out["frameworkCommit"], out["python"]))
    L.append("Question (user, 2026-10-01): for every fault class we have run, which observers see it? Detection is a catch inside "
             "the fault window, not root-cause analysis.\n")
    L.append("## Rules\n")
    for r in out["rules"]:
        L.append("- " + r)
    L.append("")
    L.append("## Map\n")
    L.append("Cells: `outside / own (n)`, episodes caught by a sensor outside the faulted service / by the faulted service's own "
             "sensors, over the n episodes whose posture collects the family. `—` = family not collected or not scored. "
             "Entry point = the untraced workload ledger, k/n episodes. Postures: episodes caught outside the target, per posture.\n")
    L.append("| population | fault class (target, kind) | n | entry point | L | M | S | Tsel | T | outside catch per posture | class (majority) | class (any) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        mcol = fam_cell(r, "M") if "Mm" not in r["families"] else "%s; mem %s" % (fam_cell(r, "M"), fam_cell(r, "Mm"))
        entry = kn(r["entryPoint"])
        if r.get("entryPointFailureHalfOnly"):
            entry = "— (%s)" % gold_entry(r["entryPointFailureHalfOnly"])
        post = " · ".join("%s %s" % (p, kn(v["outside"])) for p, v in r["postures"].items()) if any(
            v["outside"] for v in r["postures"].values()) else "—"
        L.append("| %s | %s (%s, %s) | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["population"], r["faultClass"].replace("-effect", ""), r["target"], r["faultKind"], r["n"], entry,
            fam_cell(r, "L"), mcol, fam_cell(r, "S"), fam_cell(r, "Tsel"), fam_cell(r, "T"), post,
            "**%s**" % r["visibilityClass"] if r["visibilityClass"] not in ("entry-visible",) else r["visibilityClass"],
            r["visibilityClassAnyEpisode"]))
    L.append("")
    L.append("Entry-point false alarms (same rule, pseudo windows of the no-fault cells at the fault cells' median offsets): " +
             "; ".join("%s %s" % (p, ("%d/%d" % (v["ledgerFalseAlarms"]["shows"], v["ledgerFalseAlarms"]["n0"]))
                                  if "n0" in v["ledgerFalseAlarms"] else "failure half per family, in the row")
                       for p, v in out["populations"].items()) + ".\n")
    L.append("## Per row: catching sensors and sources\n")
    for r in rows:
        L.append("### %s / %s\n" % (r["population"], r["faultClass"]))
        L.append("- n %d episodes (%s); target `%s`, fault kind `%s`." % (
            r["n"], ", ".join("%s %d" % kv for kv in r["postureEpisodes"].items()), r["target"], r["faultKind"]))
        L.append("- entry point: %s%s." % (kn(r["entryPoint"]), "" if not r.get("entryPointUnknown") else
                                          " (%d episodes unknown: no request started in the window)" % r["entryPointUnknown"]))
        if r.get("entryPointFailureHalfOnly"):
            fh = r["entryPointFailureHalfOnly"]
            L.append("- earlier corpus, no request ledger. `load_gen.log` has status codes at 1-s completion stamps, no start time "
                     "or latency, so only the failure half (any non-200 in the window) can be read: %d of the %d runs whose log "
                     "has a request in the window; %d of %d runs have none in the window (%d record no request at all). Baseline "
                     "pseudo windows of this family's length: %d/%d show a failure (%d have no request). In-window requests per "
                     "run %s, failed %s. Not used for the class." % (
                         fh["shows"], fh["known"], fh["runsWithNoRequestInWindow"], fh["n"], fh["runsWithNoRequestInLog"],
                         fh["falseAlarms"][0], fh["falseAlarms"][1], fh["baselineWindowsWithNoRequest"],
                         fh["inWindowRequests"], fh["failedInWindow"]))
        if r.get("workload"):
            w = r["workload"]
            L.append("- workload: %d/%d runs have a span (any service) in the fault window; spans in the window per run %s; "
                     "spans in the whole run %s; load-generator cycles %s. Baseline pseudo windows of this length with a span: "
                     "%d/%d (spans %s)." % (w["runsWithASpanInWindow"][0], w["runsWithASpanInWindow"][1],
                                            w["spansInWindowPerRun"], w["spansTotalPerRun"], w["loadGenCyclesPerRun"],
                                            w["baselineWindowsWithASpan"][0], w["baselineWindowsWithASpan"][1],
                                            w["baselineSpansInWindow"]))
        for fam, v in r["families"].items():
            L.append("- %s: outside %d/%d, own %d/%d (own without G3 %d/%d). Outside sensors: %s. Own: %s." % (
                fam, v["outside"], v["n"], v["own"], v["n"], v["ownNoG3"], v["n"],
                ", ".join("`%s` %d" % kv for kv in v["outsideSensors"][:6]) or "none",
                ", ".join("`%s` %d" % kv for kv in v["ownSensors"][:4]) or "none"))
            if "outsideIfSpansGated" in v:
                L.append("  - spans are not calibrated under this population's rule; post hoc, with G3 applied to spans "
                         "(no-fault firing k/n0 per sensor: %s), outside would be %d/%d." % (
                             ", ".join("`%s` %d/%d" % (x, k[0], k[1]) for x, k in list(v["outsideSpanFalseAlarms"].items())[:4]) or "no outside span fires",
                             v["outsideIfSpansGated"], v["n"]))
        L.append("- per posture (outside / incl. own / ledger): %s." % "; ".join(
            "%s %s / %s / %s" % (p, kn(v["outside"]), kn(v["anyInclOwn"]), kn(v["ledger"])) for p, v in r["postures"].items()))
        L.append("- lowest posture catching a majority outside: %s; including own sensors: %s." % (
            r["minimalPostureOutside"] or "—", r["minimalPostureInclOwn"] or "—"))
        if r["outsideSymptomKinds"]:
            L.append("- symptom kinds behind outside firings: %s." % ", ".join("%s %d" % kv for kv in r["outsideSymptomKinds"].items()))
        for f in r["byConstruction"]:
            L.append("- " + f)
        if (r["population"], r["faultClass"]) in NOTES:
            L.append("- note: " + NOTES[(r["population"], r["faultClass"])])
        L.append("- source: `%s`; detector %s; commands: %s." % (
            r["source"]["evidence"], r["source"]["detector"], "; ".join("`%s`" % c for c in r["source"]["commands"])))
        L.append("")
    L.append("## Candidates that rank placements\n")
    L.append("Rows whose class is not `entry-visible` (majority rule), with the lowest posture whose sensor set catches a majority "
             "and the sensors responsible. A row whose entry point is `—` is listed with the class it would have if the "
             "entry point missed it (`classIfEntryMisses`).\n")
    cand = [r for r in rows if r["visibilityClass"] != "entry-visible"]
    L.append("| population | fault class | class | entry point | lowest posture, outside | lowest posture, incl. own | responsible sensors (count / n) |")
    L.append("|---|---|---|---|---|---|---|")
    for r in cand:
        sens = []
        c_eff = r["visibilityClass"] if r["visibilityClass"] != "—" else r["classIfEntryMisses"]
        side = "outside" if c_eff == "interior-only-outside" else "own" if c_eff == "own-service-only" else None
        for fam, v in r["families"].items():
            if fam in ("C", "Csel") or side is None or not hit(v[side], v["n"], "majority"):
                continue
            sens += ["`%s` %d/%d" % (s, k, v["n"]) for s, k in v[side + "Sensors"][:3]]
        cls = r["visibilityClass"] if r["visibilityClass"] != "—" else "— (if entry misses: %s)" % r["classIfEntryMisses"]
        if any(f.startswith("NO-WORKLOAD") for f in r["byConstruction"]):
            cls += "; **NO-WORKLOAD** (%d/%d runs have a span in the window)" % tuple(r["workload"]["runsWithASpanInWindow"])
        elif any(f.startswith("NO-SUCCESSFUL-REQUEST") for f in r["byConstruction"]):
            cls += "; **NO-SUCCESSFUL-REQUEST** (0 HTTP 200 in the whole run; median %.2f spans/s in the window)" % \
                r["workload"]["medianSpansPerSecondInWindow"]
        if r.get("classIfEntryMissesSpansGated") and r["classIfEntryMissesSpansGated"] != r["classIfEntryMisses"]:
            cls += "; spans gated post hoc: %s" % r["classIfEntryMissesSpansGated"]
        entry = kn(r["entryPoint"])
        if r.get("entryPointFailureHalfOnly"):
            entry = "— (%s)" % gold_entry(r["entryPointFailureHalfOnly"])
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (r["population"], r["faultClass"].replace("-effect", ""), cls, entry,
                                                      r["minimalPostureOutside"] or "—", r["minimalPostureInclOwn"] or "—",
                                                      ", ".join(sens) or "none"))
    L.append("")
    L.append("## Rows caught by construction\n")
    for r in rows:
        if r["byConstruction"]:
            L.append("- %s / %s: %s" % (r["population"], r["faultClass"], " | ".join(f.split(":", 1)[0] for f in r["byConstruction"])))
    L.append("")
    L.append("## Checks\n")
    for p, v in out["checks"].items():
        L.append("- %s: %s" % (p, "; ".join("%s %s" % kv for kv in v.items())))
    L.append("")
    L.append("## Gaps and blockers\n")
    for g in out["gaps"]:
        L.append("- " + g)
    L.append("")
    if out.get("reading"):
        L.append("## Reading (hand-written against this output; regenerate the tables, revise this text)\n")
        L.append(out["reading"])
    return "\n".join(L) + "\n"


READING = """Written 2026-10-01 against this output. Scope: instance per population. Counts are rows of the map above unless
an episode count is named.

- 29 rows (population x fault class) over 8 populations. With an entry point recorded (18 rows): 15 `entry-visible`, 3
  `own-service-only`, 0 `interior-only-outside`, 0 `unseen`. Without one (11 rows, the earlier TeaStore corpus): `—`.
- 11 of the 15 entry-visible rows stop a service on the workload's request path (Hotel pauses, TeaStore freeze and crash) or stop
  the entry service itself (OTel frontend pause): the ledger sees them because requests through a stopped service fail or hang
  (flags BC-ledger-stopped-on-path, BC-entry-target). The other 4 are network delays on Hotel: 100 ms on rate (lmt2, sel1;
  16/16 each) and 2 ms on geo or rate (int1; 16/16, 15/16), the 2 ms sized in advance between two sensors' thresholds.
- The only fault class the entry point misses where it was recorded is the profile CPU throttle (`--cpus 0.1` for 15 s per
  research/lmt-pilot/RESULT.md and DECLARATION.md; the receipts record the hold, not the quota value): 0/16 episodes
  in each of the three Hotel campaigns, all on fb14srv4. No family outside profile catches it in a majority of episodes (at
  most 1 episode per family). Its own cgroup CPU pressure `S:profile:sys_psi_cpu` does, in 15/16, 15/16 and 11/16, and that
  sensor reads the resource the fault sets (BC-own-actuator). The system sampler S runs in every posture, `none` included, so
  this row separates no two postures of the ladder: it would rank a placement only by whether the target's own pressure sensor
  is in it, which the paper's rule (G2) excludes.
- So on the populations with an entry point, no row ranks the ladder's placements under G2: every fault that a sensor outside
  the target catches, the entry point catches too.
- The earlier corpus cannot supply candidates as it stands. Its entry point is not recorded (no request ledger; the load
  generator's log has no latency, and its failure half fires in 27/27 baseline windows that hold a request, so it is
  uninformative). In 8 of its 11 families no span of any service falls inside the fault window in 10/10 runs; in 7 of them a run
  holds at most 5 spans, all image spans within 0.1 s of its start, and the load generator reports 0 cycles in 9/10 runs (1/10
  has no cycle line). Their catches are the streams of an idle or down system, not the fault (flag NO-WORKLOAD). In auth freeze
  and db crash not one load-generator request returned HTTP 200 in the whole run in 9/9 logged runs, the fault window
  included, so the system was failing before the fault (flag NO-SUCCESSFUL-REQUEST; 12 and 6-8 spans per window). Only image
  crash carries traffic (about 17,000 spans per window in 9/10 runs). Baseline windows hold 0-113 spans (21/30 at most 21,
  9/30 between 63 and 113), and none of the 30 baseline runs holds an image span, so the image span sensors' 0/30 false alarms
  cannot be otherwise (flag BC-FA-unfailable).
- This bears on the paper's Table 1 rows for the earlier TeaStore corpus, computed on the same 110 runs (checked here: 110/110
  R and R+ sets equal the Table 1 run), on the sentence that image spans reach the four latency, timeout and exception families
  in 9 of 10 runs with 0 of 30 false alarms (four image operations going `missing_expected` after five start-up spans, against
  baselines with no image span), and on every count over those episodes (f_any / f_all over 110 episodes include 80 with no
  span in the window). Not corrected here; flagged for the paper's owner.
- Rows caught by construction are listed above. Beyond the request-path flags: a stopped target's own sensors fire because it
  stopped (BC-own-stopped), callers' client spans to a paused Hotel callee fail (BC-caller-span), and outside CPU firings in the
  Hotel pauses are all drops (BC-idle-cpu). TeaStore's log false alarms are 0 by construction (TBC5).
- TeaStore's journey ledger pools four routes (login, home, category, product) into one pre-window median and MAD, unlike
  Hotel's single route; it does not matter for the two classes mapped (every in-window request fails), but a route-mix shift
  could move its latency half elsewhere.
- Not shown: anything across hosts (each population is one host), any rate (n is 2 to 16 episodes per family), and any
  population outside the brief (Hotel #3-#6 are not mapped).
"""


RULES = [
    "Entry point: `research/hotel-selected/ledger_check.py` rule, unchanged. Requests started in [fault applied, fault reverting] vs "
    "before; shows = any failed in-window request, or in-window median > pre-window median + max(3 x MAD, 1 ms). Hotel calls "
    "`ledger_check.cell`; TeaStore applies the same lines to every request of `journey-ledger.jsonl` (window = intervention "
    "actualOnset/OffsetMonotonicOffsetSeconds, barrier-relative like the ledger; ok = `succeeded` and 200); OTel to "
    "`request-ledger.json` (window = intervention offsets + ledger startedAtEpoch; ok = 200 and no error).",
    "Sensors outside the target: each population's own detector, G2 (the faulted service's sensors excluded) and G3. Own: the "
    "same detector with G2 inverted (only the target's sensors), G3 kept. Families: L log templates (and their rate subsensors on "
    "TeaStore/earlier corpus), M container CPU (docker stats), Mm container memory (earlier corpus only), S cgroup system sampler "
    "(Hotel lmt2/sel1/int1 only), Tsel spans under `selected`, T spans under `full` (`kieker-native` on the earlier corpus).",
    "A family's n is the row's episodes whose posture collects it. Per-posture columns count an episode as caught when any "
    "family collected in that posture catches it outside the target.",
    "visibilityClass (majority: a column catches when 2k > n): entry-visible if the entry point catches; else "
    "interior-only-outside if any family catches outside the target; else own-service-only if any family catches on the target's "
    "own sensors; else unseen. `—` where the entry point was not recorded. visibilityClassAnyEpisode repeats it with k >= 1.",
    "C/Csel (int1 catalogue spans) are subsets of T/Tsel; reported in the JSON, never used in the derivation.",
]


def main():
    started = dt.datetime.now(dt.timezone.utc)
    checks = {}
    pops = {}
    for name, cfg in HOTEL.items():
        pops[name] = hotel_population(name, cfg, checks)
    REL = _load("vm_relevance", RESEARCH / "s4-conjunction" / "relevance.py")
    bag_rows, vocab, _, manifest, prov = REL.load_bags(BAGS)
    rel_out = json.loads(RELEVANCE_OUT.read_text())
    for name, cfg in TEASTORE.items():
        G = REL.Generation(cfg["gen"], bag_rows, vocab.get(cfg["gen"], {}))
        pops[name] = bags_population(name, cfg["gen"], G, REL, cfg["campaign"], rel_out, checks)
    G = REL.Generation("G-old", bag_rows, vocab.get("G-old", {}))
    pops["teastore-Gold"] = bags_population("teastore-Gold", "G-old", G, REL, None, rel_out, checks, gold=True)
    checks["bags"] = {"manifestScriptSha": manifest["script"], "equalsSymptomsPyOnDiskAndCommitted": prov["scriptSha"] == manifest["script"]}
    for name, root in OTEL.items():
        pops[name] = otel_population(name, root, checks)
    rows = build_rows(pops)
    gaps = [
        "Earlier TeaStore corpus: no request ledger. `load_gen.log` gives status codes at whole-second completion stamps with no "
        "start time and no latency, so the ledger rule's latency half cannot be applied and the entry-point column is `—`; the "
        "failure half (any non-200 in the window) is shown beside it with its false alarms on the baseline pseudo windows. "
        "`proc_metrics.json` (per-process /proc samples) is retained in the corpus but no adapter scores it, so S is `—` there.",
        "TeaStore T16/Tnew: no metric is recorded (M, S `—`); logs are retained for auth and persistence only, so in auth-freeze the "
        "only outside log stream is persistence (the paper's footnote a).",
        "OTel run3/v3: ledger only; no detection adapter exists, every sensor column is `—`.",
        "Hotel's request path (for the BC-ledger-stopped-on-path flag) is read from the full posture's own spans, so it holds only "
        "what that instrument sees.",
        "The user's brief names `TeaStore e3-user` and `the 27-cell campaign behind Table 1` as one population; they are two: "
        "Table 1 is campaign #16 (T-16, `tmp/teastore16-evidence`, 27 cells, all valid); e3-user is T-new "
        "(`tmp/teastore-e3-user-a5-evidence`, 36 cells + 4 blocked-evidence copies). Both are mapped, never pooled.",
        "Hotel #3-#6 (the paper's H-B rows) are not in the brief and are not mapped here.",
    ]
    out = {
        "generatedAt": started.strftime("%Y%m%dT%H%M%SZ"),
        "frameworkCommit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip(),
        "python": sys.version.split()[0], "script": rel(__file__), "scriptSha256": sha256_file(__file__),
        "rules": RULES, "checks": checks, "gaps": gaps, "rows": rows,
        "populations": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in pops.items()},
    }
    out["reading"] = READING
    (HERE / "visibility.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=list) + "\n")
    (HERE / "MAP.md").write_text(render(out))
    for r in rows:
        print("%-14s %-26s n=%-3d entry=%-7s class=%-22s any=%-22s min=%s" % (
            r["population"], r["faultClass"], r["n"], kn(r["entryPoint"]), r["visibilityClass"], r["visibilityClassAnyEpisode"],
            r["minimalPostureOutside"]))
    print(json.dumps(checks, indent=1))


def self_check():
    # ledger rule: planted failure, planted slowdown, flat window, and unknowns
    pre = [(10.0, True)] * 20 + [(11.0, True)] * 20
    assert ledger_rule(pre, [(10.0, True)] * 10)["shows"] is False
    assert ledger_rule(pre, [(10.0, True)] * 9 + [(10.0, False)])["shows"] is True
    assert ledger_rule(pre, [(12.6, True)] * 10)["shows"] is True          # > 10.5 + max(3 * 0.5, 1)
    assert ledger_rule(pre, [(11.9, True)] * 10)["shows"] is False
    assert ledger_rule([], [(1.0, True)]) is None and ledger_rule(pre, []) is None
    assert split([(0.5, 1.0, True), (1.0, 1.0, True), (2.0, 1.0, True), (2.5, 1.0, True)], 1.0, 2.0) == ([(1.0, True)], [(1.0, True), (1.0, True)])
    f = lambda o, w, n=4: {"n": n, "outside": o, "own": w}
    assert classify((4, 4), {"T": f(4, 4)}) == ("entry-visible", "interior-only-outside")
    assert classify((0, 4), {"T": f(3, 0), "S": f(0, 4)}) == ("interior-only-outside", "interior-only-outside")
    assert classify((0, 4), {"T": f(2, 0), "S": f(0, 3)}) == ("own-service-only", "own-service-only")   # 2/4 is not a majority
    assert classify((0, 4), {"T": f(2, 0), "S": f(0, 3)}, "any") == ("interior-only-outside", "interior-only-outside")
    assert classify((1, 4), {"T": f(0, 0)}) == ("unseen", "unseen")
    assert classify(None, {"T": f(4, 0)}) == ("—", "interior-only-outside")                         # absence is not zero
    assert classify((0, 4), {}) == ("—", "—")                                                          # no sensor scored
    assert classify((3, 4), {}) == ("entry-visible", "—")
    print("self-check: pass")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-check"]:
        self_check()
        sys.exit(0)
    main()
