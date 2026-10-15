#!/usr/bin/env python3
"""Traffic, health, non-vacuity and provenance gates over every scored population (offline, read-only).

Defect class (2026-10-01, research/visibility-map/MAP.md): a fault corpus whose scored windows held no workload, or whose
system was already failing before the fault, makes every "reacts / does not react" count and every false-alarm rate
vacuous. These four gates make that class fail loudly instead of scoring:

  G1 traffic   requests (or traces, for trace-only corpora) started inside each scored window >= FLOOR x rate x seconds;
               the rate is the plan's declared rate where a plan exists, else an external or baseline reference (named).
  G2 healthy   in the pre-window [measurement start, onset): successes >= FLOOR x rate x seconds and failure share
               <= PRE_FAIL_MAX. No-fault cells: the same over [start, pseudo onset).
  G3 FA        a false-alarm rate k/n is reportable only over no-fault windows that pass G1 and G2 and in which a
               planted failure makes the entry-point rule fire; n_eff < n is PARTIAL, n_eff = 0 is FAIL (the rate cannot fail).
  G4 prov      every scored cell carries a start-stamped request ledger, fault cells carry fault timing, cells carry a
               validity verdict, the scored set holds no invalid cell, and the records lie inside the scored measurement.

Engineering defaults (recorded, not preregistered): FLOOR 0.5, PRE_FAIL_MAX 0.05, scope share 0.95. A trace-only
population has no ledger: its rows are trace starts (ok = no error span, or unknown) and its windows are inferred from
the runner's timing constants; every such row is labelled `proxy`, and its G4 fails by construction.

    /usr/bin/python3 -B research/visibility-map/traffic_gate.py               # ledger + load-generator populations
    /usr/bin/python3 -B research/visibility-map/traffic_gate.py --legacy      # adds the trace-only legacy corpora (slow)
    /usr/bin/python3 -B research/visibility-map/traffic_gate.py --only hotel-rep1,teastore-Gold
    /usr/bin/python3 -B research/visibility-map/traffic_gate.py --by-family   # adds one line per fault family / lane
    /usr/bin/python3 -B research/visibility-map/traffic_gate.py --self-check  # planted defects; exit 1 if a gate misses one
    /usr/bin/python3 -B research/visibility-map/traffic_gate.py --self-check --break G1   # shows the self-check failing

Writes nothing. Python 3.9 (no PEP 604 annotations).
"""
import datetime as dt
import glob
import importlib.util
import json
import math
import os
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
TS = (REPO / ".." / "test-repos" / "TeaStore" / "data" / "experiments").resolve()
FLOOR = 0.5
PRE_FAIL_MAX = 0.05
SCOPE_MIN = 0.95
BROKEN = set()          # --break: disable a gate so the self-check can be seen failing


# --------------------------------------------------------------------------- gates (operate on normalised cells)
#
# cell = {"cell", "kind": "fault"|"nofault", "valid": True|False|None, "rows": [(t, ok)] | None, "rowsKind",
#         "m": (m0, m1), "w": (a, b) | None, "rate": per-second | None, "rateSource", "faultTiming": bool | None}
# t is seconds on the cell's own clock (barrier-relative where a barrier exists); ok is True/False/None (unknown).

def need(rate, seconds):
    if "G1" in BROKEN or rate is None:
        return 0 if "G1" in BROKEN else None
    return max(1, math.ceil(FLOOR * rate * max(seconds, 0.0)))


def g1(cell, w):
    """Traffic in window w: count of rows started in [a, b] against the rate floor."""
    if cell["rows"] is None or w is None:
        return {"n": None, "floor": None, "pass": None}
    a, b = w
    n = sum(1 for t, _ in cell["rows"] if a <= t <= b)
    fl = need(cell["rate"], b - a)
    return {"n": n, "floor": fl, "pass": None if fl is None else n >= fl}


def g2(cell, onset):
    """Healthy before onset: successes in [m0, onset) against the rate floor, and the failure share."""
    if cell["rows"] is None or onset is None:
        return {"ok": None, "failed": None, "floor": None, "pass": None}
    m0 = cell["m"][0]
    pre = [ok for t, ok in cell["rows"] if m0 <= t < onset]
    if pre and all(ok is None for ok in pre):          # trace-only, no success signal: traffic only
        fl = need(cell["rate"], onset - m0)
        return {"ok": None, "failed": None, "n": len(pre), "floor": fl, "pass": None if fl is None else len(pre) >= fl,
                "proxy": "traffic only"}
    good = sum(1 for ok in pre if ok)
    bad = sum(1 for ok in pre if ok is False)
    fl = need(cell["rate"], onset - m0)
    if "G2" in BROKEN:
        return {"ok": good, "failed": bad, "floor": fl, "pass": True}
    share = bad / len(pre) if pre else None
    ok = fl is not None and good >= fl and share is not None and share <= PRE_FAIL_MAX
    return {"ok": good, "failed": bad, "floor": fl, "pass": None if fl is None else ok}


def entry_rule_can_fire(cell, w):
    """Plant one failed request in the window; does the entry-point rule (any in-window failure, given a defined
    pre-window) fire? Needs >= 1 in-window request and >= 1 successful pre-window request (ledger_check.cell's
    preconditions). Without them the rate is a zero that cannot become anything else."""
    if "G3" in BROKEN:
        return True
    if cell["rows"] is None or w is None:
        return False
    a, b = w
    inside = [ok for t, ok in cell["rows"] if a <= t <= b]
    pre = [ok for t, ok in cell["rows"] if cell["m"][0] <= t < a]
    if not inside or not pre:
        return False
    if not all(ok is None for ok in pre) and not any(ok for ok in pre):
        return False
    # For the any-failure rule the plant always fires once a window has a request and a defined pre-window, so this
    # reduces to those preconditions; a detector with a latency or rate half needs its own planted positive (MITIGATION §3.1).
    planted = [False] + inside[1:]
    return any(ok is False for ok in planted)


def pseudo_window(cells):
    offs = [(c["w"][0] - c["m"][0], c["w"][1] - c["m"][0]) for c in cells if c["kind"] == "fault" and c["w"]]
    if not offs:
        return None
    return statistics.median(o[0] for o in offs), statistics.median(o[1] for o in offs)


def evaluate(pop):
    """Population verdicts. Only cells the consumer scores enter (valid ones, or all when validity is unknown or the
    consumer does not filter)."""
    cells = pop["cells"]
    scored = [c for c in cells if c["valid"] is not False] if pop.get("filtersValidity", True) else list(cells)
    pw = pseudo_window(scored)
    out = {"fault": [], "nofault": []}
    for c in scored:
        if c["kind"] == "fault":
            w, onset = c["w"], (c["w"][0] if c["w"] else None)
        elif pw is not None:
            w = (c["m"][0] + pw[0], c["m"][0] + pw[1])
            onset = w[0]
        else:                        # cost-only population: the whole measurement is the scored window
            w, onset = c["m"], None
        r = {"cell": c["cell"], "g1": g1(c, w), "g2": g2(c, onset) if onset is not None else {"pass": None},
             "canFire": entry_rule_can_fire(c, w) if c["kind"] == "nofault" and onset is not None else None}
        if c["kind"] == "nofault" and onset is None:          # cost cells: success share over the whole measurement
            rows = [ok for t, ok in (c["rows"] or []) if c["m"][0] <= t <= c["m"][1]]
            known = [ok for ok in rows if ok is not None]
            r["g2"] = {"ok": sum(known), "failed": len(known) - sum(known),
                       "pass": (bool(known) and (len(known) - sum(known)) / len(known) <= PRE_FAIL_MAX) or "G2" in BROKEN}
        out[c["kind"]].append(r)
    # G3: only no-fault cells with a pseudo window are false-alarm windows
    fa = [r for r in out["nofault"] if r["canFire"] is not None]
    n_eff = sum(1 for r in fa if r["g1"]["pass"] and r["g2"]["pass"] and r["canFire"])
    g3 = "—" if not fa else ("PASS" if n_eff == len(fa) else "FAIL" if n_eff == 0 else "PARTIAL")
    if "G3" in BROKEN:
        g3 = "PASS"
    # G4
    prov = {
        "ledger": (sum(1 for c in scored if c["rowsKind"] == "ledger"), len(scored)),
        "faultTiming": (sum(1 for c in scored if c["kind"] == "fault" and c["faultTiming"]),
                        sum(1 for c in scored if c["kind"] == "fault")),
        "validity": (sum(1 for c in scored if c["valid"] is not None), len(scored)),
        "invalidScored": sum(1 for c in scored if c["valid"] is False),
    }
    for c in scored:              # ledger rows: share of records inside the cell's own measurement (+-5 s)
        if c.get("scopeShare") is None and c["rows"] and c["m"][1] > c["m"][0]:
            c["scopeShare"] = sum(1 for t, _ in c["rows"] if c["m"][0] - 5 <= t <= c["m"][1] + 5) / len(c["rows"])
    inscope = [c.get("scopeShare") for c in scored if c.get("scopeShare") is not None]
    prov["scopeMin"] = min(inscope) if inscope else None
    g4 = all(k == n for k, n in (prov["ledger"], prov["faultTiming"], prov["validity"])) and prov["invalidScored"] == 0 \
        and (prov["scopeMin"] is None or prov["scopeMin"] >= SCOPE_MIN)
    if "G4" in BROKEN:
        g4 = True
    return {"name": pop["name"], "unit": pop["unit"], "rateSource": pop["rateSource"], "proxy": pop.get("proxy", False),
            "cells": len(cells), "scored": len(scored), "invalidExcluded": len(cells) - len(scored),
            "pseudoWindow": pw, "fault": out["fault"], "nofault": out["nofault"],
            "g3": {"verdict": g3, "nEff": n_eff, "n": len(fa)}, "g4": {"pass": g4, **prov}, "note": pop.get("note", "")}


# --------------------------------------------------------------------------- adapters: harness ledgers

def jload(p):
    return json.loads(Path(p).read_text())


def hotel(name, x, note=""):
    x = REPO / x
    cells = []
    for a in sorted((x / "runs").glob("**/attempt-01")):
        plan = jload(a / "opportunity-plan.json")
        b0 = plan["barrierMonotonic"]
        rows = None
        if (a / "opportunity-ledger.jsonl").exists():
            rows = []
            for line in (a / "opportunity-ledger.jsonl").open():
                r = json.loads(line)
                rows.append((r["actualStartMonotonic"] - b0, r["outcome"] == "completed" and r.get("statusCode") == 200))
        fr = a / "fault-receipt.json"
        w = None
        if fr.exists():
            f = jload(fr)
            # v4 receipts: applied..reverting (ledger_check.cell); older ones: started..ended (symptoms.py:470)
            w = (f.get("appliedMonotonic", f.get("startedMonotonic")) - b0,
                 f.get("revertingMonotonic", f.get("endedMonotonic")) - b0)
        ct = a / "cell-terminal.json"
        valid = bool(jload(ct).get("candidateCellValid")) if ct.exists() else False
        fault = a.relative_to(x).parts[1] == "effect"     # kind from the path, timing from the file (never both)
        cells.append({"cell": str(a.relative_to(x)), "kind": "fault" if fault else "nofault", "valid": valid,
                      "rows": rows, "rowsKind": "ledger", "m": (0.0, float(plan["durationSeconds"])), "w": w,
                      "rate": float(plan["rate"]), "faultTiming": fr.exists() if fault else None})
    return {"name": name, "unit": "requests", "rateSource": "plan rate (opportunity-plan.json)", "cells": cells,
            "note": note}


def teastore(name, campaign, only_full=False, filters_validity=True, note=""):
    root = REPO / campaign
    cells = []
    for d in sorted((root / "runs").glob("*/*")):
        if not d.is_dir() or d.name.endswith(".blocked-evidence") or (only_full and not d.name.endswith("-full")):
            continue
        cv = d / "candidate-validation.json"
        valid = (jload(cv).get("cellStatus") == "valid") if cv.exists() else None
        if not (d / "journey-ledger.plan.json").exists():      # a cell that died before its plan: no ledger
            cells.append({"cell": "%s/%s" % (d.parent.name, d.name), "kind": "fault" if "effect" in d.parent.name
                          else "nofault", "valid": valid if valid is not None else False, "rows": None,
                          "rowsKind": "none", "m": (0.0, 0.0), "w": None, "rate": None, "faultTiming": False})
            continue
        plan = jload(d / "journey-ledger.plan.json")
        rows = []
        for line in (d / "journey-ledger.jsonl").open():
            r = json.loads(line)
            if r.get("recordType", "journey-terminal") == "journey-terminal":
                rows.append((r["actualStartMonotonic"], r["outcome"] == "succeeded"))
        iv = d / "intervention.json"
        w = None
        if iv.exists():
            v = jload(iv)
            w = (v["actualOnsetMonotonicOffsetSeconds"], v["actualOffsetMonotonicOffsetSeconds"])
        sch = plan["schedule"]
        fault = "effect" in d.parent.name
        cells.append({"cell": "%s/%s" % (d.parent.name, d.name), "kind": "fault" if fault else "nofault",
                      "valid": valid, "rows": rows, "rowsKind": "ledger", "m": (0.0, float(sch["durationSeconds"])),
                      "w": w, "rate": float(sch["journeysPerSecond"]), "faultTiming": iv.exists() if fault else None})
    return {"name": name, "unit": "journeys", "rateSource": "plan journeysPerSecond (journey-ledger.plan.json)",
            "cells": cells, "filtersValidity": filters_validity, "note": note}


def otel(name, root, note=""):
    root = REPO / root
    cells = []
    for d in sorted((root / "runs").glob("*/*")):
        if not d.is_dir() or not (d / "request-ledger.json").exists():
            continue
        led = jload(d / "request-ledger.json")
        base = led["startedAtEpoch"]
        rows = [(q["startedAtEpoch"] - base, q["status"] == 200 and q["error"] is None) for q in led["requests"]]
        iv = d / "intervention.json"
        w = None
        if iv.exists():
            v = jload(iv)
            w = (v["actualOnsetMonotonicOffsetSeconds"], v["actualOffsetMonotonicOffsetSeconds"])
        rc = jload(d / "receipt.json") if (d / "receipt.json").exists() else {}
        rate = float(led["ratePerSecond"])
        fault = "effect" in d.parent.name
        cells.append({"cell": "%s/%s" % (d.parent.name, d.name), "kind": "fault" if fault else "nofault",
                      "valid": rc.get("state") == "valid" if rc else None, "rows": rows, "rowsKind": "ledger",
                      "m": (0.0, led["offered"] / rate), "w": w, "rate": rate, "faultTiming": iv.exists() if fault else None})
    return {"name": name, "unit": "requests", "rateSource": "ledger ratePerSecond (request-ledger.json)", "cells": cells,
            "note": note}


# --------------------------------------------------------------------------- adapter: the earlier TeaStore corpus

def _stamp(line):
    return dt.datetime.strptime(line[1:line.index("]")], "%Y-%m-%dT%H:%M:%S%z").timestamp()


def loadgen_rows(run):
    """load_gen.log: one `[HTTP nnn]` line per request, stamped at whole seconds AFTER it returned (no start)."""
    p = run / "load_gen.log"
    if not p.exists():
        return None
    return [(_stamp(l), l.split("[HTTP ", 1)[1].startswith("200")) for l in p.read_text(errors="replace").splitlines()
            if l.startswith("[") and "[HTTP " in l]


def gold(name="teastore-Gold"):
    """The scored corpus: exactly symptoms.py's gold_select (S4 F2), 110 fault runs + 30 baselines. Rate reference:
    the same host's 7-run smoke campaign two hours earlier (fault_campaign_20260717_162748, 5/5 healthy), external
    to the corpus, so a corpus-wide starvation cannot lower its own floor."""
    root = TS / "by_server" / "fb14srv6"
    spec = importlib.util.spec_from_file_location("tg_symptoms", REPO / "research" / "s4-conjunction" / "symptoms.py")
    sym = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sym)
    keep, excluded = sym.gold_select(root)
    ref = []
    for r in jload(root / "fault_campaign_20260717_162748.json")["runs"]:
        d = root / Path(r["output_dir"]).name
        md = jload(d / "metadata.json")
        rows = loadgen_rows(d) or []
        ref.append(sum(1 for t, _ in rows if md["start_time"] <= t <= md["end_time"]) / md["duration"])
    rate = statistics.median(ref)
    cells = []
    for r in keep:
        md = jload(r / "metadata.json")
        t0 = md["start_time"]
        rows = loadgen_rows(r)
        rows = None if rows is None else [(t - t0, ok) for t, ok in rows]
        f = md.get("fault") or {}
        fault = r.name.startswith("fault_")
        w = (f["fault_started_at"] - t0, f["fault_finished_at"] - t0) if fault else None
        cells.append({"cell": r.name, "kind": "fault" if fault else "nofault", "valid": None, "rows": rows,
                      "rowsKind": "loadgen-completion-stamps", "m": (0.0, md["duration"]), "w": w, "rate": rate,
                      "faultTiming": bool(f.get("fault_started_at")) if fault else None})
    return {"name": name, "unit": "requests (completion stamps)",
            "rateSource": "external: median HTTP lines/s of the 7 healthy runs of fault_campaign_20260717_162748 (%.2f/s)" % rate,
            "cells": cells, "note": "selection excluded %s" % dict(excluded)}


# --------------------------------------------------------------------------- adapters: trace-only legacy corpora

def trace_rows(spans, err=lambda s: s.get("status_code") == 2):
    starts, bad = {}, set()
    for s in spans:
        tid = s.get("trace_id")
        if not tid:
            continue
        starts[tid] = min(starts.get(tid, s["timestamp"]), s["timestamp"])
        if err(s):
            bad.add(tid)
    return sorted((t, tid not in bad) for tid, t in starts.items())


def hr10():
    """Figure 3 panel (b): hr_campaign_20260717_* on fb14srv5 (tools/make_final_figures.py:63-64). No metadata, no
    ledger: the runner (tools/run_hr_faults.sh:49-54) starts the load, faults at WARMUP=70 s for OUTAGE=90 s, load
    lasts DURATION=240 s. A scenario's own measurement is inferred as [last trace start - 240, last trace start].
    Rate: the file's own trace density (the Jaeger fetch is capped, so density is per file, not per campaign)."""
    cells = []
    for mf in sorted((TS / "by_server" / "fb14srv5").glob("hr_campaign_20260717_*.json")):
        for r in jload(mf)["runs"]:
            d = TS / "by_server" / "fb14srv5" / Path(r["output_dir"]).name
            rows = trace_rows(jload(d / "traces.json"))
            t_end = rows[-1][0]
            m0 = t_end - 240.0
            span = rows[-1][0] - rows[0][0]
            own = sum(1 for t, _ in rows if m0 - 5 <= t <= t_end)
            fault = r["fault_class"] != "baseline"
            cells.append({"cell": "%s:%s" % (mf.stem, r["scenario"]), "kind": "fault" if fault else "nofault",
                          "valid": None, "rows": [(t - m0, ok) for t, ok in rows], "rowsKind": "traces",
                          "m": (0.0, 240.0), "w": (70.0, 160.0) if fault else None,
                          "rate": len(rows) / span if span > 0 else None, "faultTiming": False if fault else None,
                          "scopeShare": own / len(rows), "fileSpanSeconds": span})
    return {"name": "fig3b-hr10", "unit": "traces (proxy)", "proxy": True, "cells": cells,
            "rateSource": "per-file trace density (Jaeger fetch capped; window inferred from run_hr_faults.sh constants)"}


def otel_lab():
    """Figure 3 panel (a): otel_campaign_20260712_124211 (tools/rebuild_gt_pertrace.py:50). Each traces.json is cut to
    its scenario (--since-ts/--until-ts, tools/run_otel_faults.sh:104-106); fault at WARMUP=90 s for OUTAGE=90 s
    (run_otel_faults.sh:38-39, as committed 2026-07-20, after this campaign ran). Measurement anchored at the first span.
    Rate: median trace density of the campaign's three baselines."""
    root = TS
    m = jload(root / "otel_campaign_20260712_124211.json")
    cells, dens = [], []
    for r in m["runs"]:
        d = root / Path(r["output_dir"]).name
        rows = trace_rows(jload(d / "traces.json"))
        m0 = rows[0][0]
        fault = r["scenario"].startswith("fault_")
        if not fault:
            dens.append(len(rows) / 300.0)
        cells.append({"cell": r["scenario"], "kind": "fault" if fault else "nofault", "valid": None,
                      "rows": [(t - m0, ok) for t, ok in rows], "rowsKind": "traces", "m": (0.0, 300.0),
                      "w": (90.0, 180.0) if fault else None, "rate": None, "faultTiming": False if fault else None})
    rate = statistics.median(dens)
    for c in cells:
        c["rate"] = rate
    return {"name": "fig3a-otel-lab", "unit": "traces (proxy)", "proxy": True, "cells": cells,
            "rateSource": "median baseline trace density %.1f/s (window inferred)" % rate}


def gold_postfix():
    """The SECOND 10x TeaStore attempt on fb14srv6 (2026-07-18 14:32 to 07-19 02:10, after the starvation postmortem
    in tools/run_nightly_replication.sh:30-36). Only ground_truth__trace.json was fetched (112 of its 140 dirs fall
    on 07-18 and are symptoms.py's `missing sidecar` exclusions). Rows: transaction_flow path starts; Kieker carries
    no status, so ok is unknown. Window assumed [75 s, 75 s + D_f], D_f the starved attempt's median per family.
    Rate: median trace density of its own 30 baselines."""
    root = TS / "by_server" / "fb14srv6"
    tz = dt.timezone(dt.timedelta(hours=2))
    D = defaultdict(list)
    for p in glob.glob(str(root / "fault_*_2026071[78]_*" / "metadata.json")):
        f = (jload(p).get("fault") or {})
        if f.get("fault_started_at"):
            D[Path(p).parent.name[6:].rsplit("_", 2)[0]].append(f["fault_finished_at"] - f["fault_started_at"])
    Dm = {k: statistics.median(v) for k, v in D.items()}
    cells, dens = [], []
    mfs = [mf for mf in sorted(root.glob("fault_campaign_2026071[89]_*.json")) if mf.stem >= "fault_campaign_20260718_143215"]
    for mf in mfs:
        for r in jload(mf)["runs"]:
            d = root / Path(r["output_dir"]).name
            p = d / "ground_truth__trace.json"
            if not p.exists():
                continue
            g = jload(p)
            t0 = dt.datetime.strptime(d.name[-15:], "%Y%m%d_%H%M%S").replace(tzinfo=tz).timestamp()
            rows = sorted((min(e["timestamp"] for e in q["events"]) - t0, None) for q in g["paths"]
                          if q.get("type") == "transaction_flow" and q.get("events"))
            fam = d.name[6:].rsplit("_", 2)[0] if d.name.startswith("fault_") else None
            if fam is None:
                dens.append(len(rows) / 300.0)
            cells.append({"cell": d.name, "kind": "fault" if fam else "nofault", "valid": None, "rows": rows,
                          "rowsKind": "traces", "m": (0.0, 300.0),
                          "w": (75.0, 75.0 + Dm.get(fam, 45.0)) if fam else None, "rate": None,
                          "faultTiming": False if fam else None})
    rate = statistics.median(dens) if dens else None
    for c in cells:
        c["rate"] = rate
    return {"name": "teastore-Gold-postfix", "unit": "traces (proxy)", "proxy": True, "cells": cells,
            "rateSource": "median baseline trace density %.1f/s (window assumed 75 s + D_f)" % (rate or float("nan"))}


def single_file(name, path, err, note):
    rows = trace_rows(jload(path), err)
    m0 = rows[0][0]
    span = rows[-1][0] - m0
    return {"name": name, "unit": "traces (proxy)", "proxy": True, "rateSource": "— (no reference)", "note": note,
            "cells": [{"cell": Path(path).parent.name or Path(path).name, "kind": "nofault", "valid": None,
                       "rows": [(t - m0, ok) for t, ok in rows], "rowsKind": "traces", "m": (0.0, span), "w": None,
                       "rate": None, "faultTiming": None}]}


# --------------------------------------------------------------------------- registry

def populations(legacy):
    """(name, builder) pairs; --only filters by name before anything is read."""
    H = "tmp/sprint-hotel6-x/%s/%s"
    T5 = "tmp/teastore-e3-user-a5-evidence/teastore-candidate-pilot-v3-user"
    P = [("hotel-run%d" % i, (lambda i=i, r=r: hotel("hotel-run%d" % i, H % (r, r)))) for i, r in (
            (1, "hotel-v1-20260921t152751z-210a480a"), (3, "hotel-v1-20260922t002056z-969a1362"),
            (4, "hotel-v1-20260923t021034z-a8e7e72e"), (5, "hotel-v1-20260923t061605z-88b7bf7c"),
            (6, "hotel-v1-20260924t012134z-7fd8717d"))]
    P += [("hotel-%s" % k, (lambda k=k: hotel("hotel-%s" % k, "tmp/hotel%s-evidence/x" % k)))
          for k in ("lmt2", "sel1", "int1", "rep1")]
    L = {9: "research/campaign9-evidence", 10: "tmp/teastore10-evidence/x", 11: "tmp/teastore11-evidence",
         12: "tmp/teastore12-evidence", 13: "tmp/teastore13-evidence", 14: "tmp/teastore14-evidence",
         15: "tmp/teastore15-evidence", 17: "tmp/teastore17-evidence/x", 18: "tmp/teastore18-evidence/x"}
    P += [("teastore-T%d" % i, (lambda i=i: teastore("teastore-T%d" % i, L[i] + "/teastore-candidate-pilot-v1")))
          for i in sorted(L)]          # the ladder and replication campaigns whose evidence is extracted locally
    P += [
        ("teastore-T16", lambda: teastore("teastore-T16", "tmp/teastore16-evidence/x/teastore-candidate-pilot-v1")),
        ("teastore-Tnew", lambda: teastore("teastore-Tnew", T5)),
        ("teastore-Tnew-sec3", lambda: teastore("teastore-Tnew-sec3", T5, only_full=True, filters_validity=False,
                                                note="the 9 *-full cells research/observed_requirements.py:33 reads, "
                                                     "unfiltered by validity")),
        ("otel-run2", lambda: otel("otel-run2", "tmp/otel-run2-evidence")),
        ("otel-run3", lambda: otel("otel-run3", "tmp/otel-run3-evidence")),
        ("otel-v3", lambda: otel("otel-v3", "tmp/otel-v3-evidence")),
        ("teastore-Gold", gold),
    ]
    if legacy:
        P += [
            ("fig3a-otel-lab", otel_lab),
            ("fig3b-hr10", hr10),
            ("fig3c-teastore-native", lambda: single_file("fig3c-teastore-native", TS / "teastore_native_traces_raw.json",
                                                          lambda s: False, "one lab-mix fault run; no fault timing retained")),
            ("fig3d-hr-construct", lambda: single_file("fig3d-hr-construct",
                                                       TS / "icsoc_pertrace_rescore" / "hr_construct_place" / "traces.json",
                                                       lambda s: s.get("status_code") == 2, "construct row, no fault")),
            ("teastore-Gold-postfix", gold_postfix),
        ]
    return P


# --------------------------------------------------------------------------- report

def frac(k, n):
    return "%d/%d" % (k, n) if n else "—"


def summarise(E):
    f, nf = E["fault"], E["nofault"]

    def cnt(rs, key):
        known = [r for r in rs if r[key].get("pass") is not None]
        return sum(1 for r in known if r[key]["pass"]), len(known)
    g1f, g2f = cnt(f, "g1"), cnt(f, "g2")
    g1n, g2n = cnt(nf, "g1"), cnt(nf, "g2")
    ins = [r["g1"]["n"] for r in f if r["g1"]["n"] is not None]
    fls = [r["g1"]["floor"] for r in f if r["g1"]["floor"] is not None]
    g4 = E["g4"]
    prov = "PASS" if g4["pass"] else "FAIL (ledger %s, faultTiming %s, validity %s, invalidScored %d%s)" % (
        frac(*g4["ledger"]), frac(*g4["faultTiming"]), frac(*g4["validity"]), g4["invalidScored"],
        "" if g4["scopeMin"] is None else ", scope min %.2f" % g4["scopeMin"])
    return {"population": E["name"] + (" [proxy]" if E["proxy"] else ""), "cells": "%d (%d scored, %d invalid excluded)" % (
        E["cells"], E["scored"], E["invalidExcluded"]),
        "G1 fault windows": frac(*g1f), "in-window median [min] / floor": "%s [%s] / %s" % (
            statistics.median(ins) if ins else "—", min(ins) if ins else "—", statistics.median(fls) if fls else "—"),
        "G2 pre-fault healthy": frac(*g2f), "G1 no-fault windows": frac(*g1n), "G2 no-fault healthy": frac(*g2n),
        "G3 FA n_eff/n": "%s %s" % (frac(E["g3"]["nEff"], E["g3"]["n"]), E["g3"]["verdict"]), "G4 provenance": prov}


def failing(E, k=6):
    bad = [r["cell"] for r in E["fault"] if r["g1"].get("pass") is False or r["g2"].get("pass") is False]
    return bad[:k], len(bad)


def family(cell):
    """Grouping key for --by-family: the fault family / regime / scenario lane a cell belongs to."""
    if ":" in cell:                                   # fig3b-hr10  campaign:scenario_rN
        return cell.split(":", 1)[1].rsplit("_r", 1)[0]
    if cell.startswith("fault_") and cell[-15:-7].isdigit():        # the earlier corpus: fault_<family>_<date>_<time>
        return cell[len("fault_"):-16]
    if cell.startswith("baseline"):
        return "baseline"
    parts = cell.split("/")
    if parts[0] == "runs":                            # Hotel: runs/<kind>[/<regime>]/b../p..-posture/attempt-01
        return parts[2] if parts[1] == "effect" else parts[1]
    return parts[0]                                   # TeaStore / OTel: <regime>/<cell>; legacy single scenarios


def by_family(pop, E):
    cells = {c["cell"]: c for c in pop["cells"]}
    groups = defaultdict(list)
    for r in E["fault"] + E["nofault"]:
        groups[family(r["cell"])].append(r)
    for f, rs in sorted(groups.items()):
        ins = [r["g1"]["n"] for r in rs if r["g1"]["n"] is not None]
        fl = [r["g1"]["floor"] for r in rs if r["g1"]["floor"] is not None]
        pre = []
        for r in rs:
            c = cells[r["cell"]]
            w = c["w"] if c["w"] else ((c["m"][0] + E["pseudoWindow"][0], 0) if E["pseudoWindow"] else None)
            if c["rows"] is not None and w is not None:
                pre.append(sum(1 for t, _ in c["rows"] if c["m"][0] <= t < w[0]))
        okf = [(r["g2"].get("ok"), r["g2"].get("failed")) for r in rs if r["g2"].get("ok") is not None]
        print("   %-28s n %3d | G1 %s, in-window median %s [min %s] vs floor %s | G2 %s, pre-window rows median %s%s" % (
            f, len(rs), frac(sum(1 for r in rs if r["g1"].get("pass")), sum(1 for r in rs if r["g1"].get("pass") is not None)),
            statistics.median(ins) if ins else "—", min(ins) if ins else "—", statistics.median(fl) if fl else "—",
            frac(sum(1 for r in rs if r["g2"].get("pass")), sum(1 for r in rs if r["g2"].get("pass") is not None)),
            statistics.median(pre) if pre else "—",
            ", pre ok/failed median %s/%s" % (statistics.median(o for o, _ in okf), statistics.median(b for _, b in okf))
            if okf else ""))


def main(argv):
    legacy = "--legacy" in argv
    only = None
    if "--only" in argv:
        only = set(argv[argv.index("--only") + 1].split(","))
    print("traffic_gate: FLOOR %.2f x rate x seconds, PRE_FAIL_MAX %.2f, SCOPE_MIN %.2f; python %s" % (
        FLOOR, PRE_FAIL_MAX, SCOPE_MIN, sys.version.split()[0]))
    rows = []
    for name, make in populations(legacy):
        if only and name not in only:
            continue
        try:
            pop = make()
        except FileNotFoundError as e:
            print("SKIP %s (evidence not local): %s" % (name, e))
            rows.append({"population": name, "cells": "— (not local)"})
            continue
        E = evaluate(pop)
        s = summarise(E)
        rows.append(s)
        bad, nbad = failing(E)
        print("\n== %s  unit=%s  rate=%s%s" % (E["name"], E["unit"], E["rateSource"], ("  note: " + E["note"]) if E["note"] else ""))
        for k, v in s.items():
            if k != "population":
                print("   %-34s %s" % (k, v))
        if nbad:
            print("   failing fault cells (%d): %s%s" % (nbad, ", ".join(bad), " ..." if nbad > len(bad) else ""))
        if "--by-family" in argv:
            by_family(pop, E)
        sc = [c for c in pop["cells"] if c.get("fileSpanSeconds") is not None]
        if sc:                     # records outside the scored scenario (trace files not cut to their scenario)
            fc = [c for c in sc if c["kind"] == "fault"]
            tot = sum(len(c["rows"]) for c in fc)
            own = sum(c["scopeShare"] * len(c["rows"]) for c in fc)
            inw = sum(sum(1 for t, _ in c["rows"] if c["w"][0] <= t <= c["w"][1]) for c in fc)
            print("   scope (fault files): rows %d; in own scenario %.0f (%.1f%%); in own fault window %d (%.1f%%); "
                  "per-file own share median %.2f min %.2f; file span median %.0f s" % (
                      tot, own, 100.0 * own / tot, inw, 100.0 * inw / tot,
                      statistics.median(c["scopeShare"] for c in fc), min(c["scopeShare"] for c in fc),
                      statistics.median(c["fileSpanSeconds"] for c in fc)))
    print("\n| population | cells | G1 fault windows | in-window median [min] / floor | G2 pre-fault healthy | "
          "G1 no-fault windows | G2 no-fault healthy | G3 FA n_eff/n | G4 provenance |")
    print("|---|---|---|---|---|---|---|---|---|")
    for s in rows:
        print("| " + " | ".join(str(s.get(k, "—")) for k in ("population", "cells", "G1 fault windows",
              "in-window median [min] / floor", "G2 pre-fault healthy", "G1 no-fault windows", "G2 no-fault healthy", "G3 FA n_eff/n",
              "G4 provenance")) + " |")
    return 0


# --------------------------------------------------------------------------- self-check (in memory, writes nothing)

def synthetic(defect=None):
    """One population: 4 fault cells and 4 no-fault cells, open loop at 10/s over 120 s, fault window [60, 75]."""
    def cell(i, kind):
        rows = [(k / 10.0, True) for k in range(1200)]
        w = (60.0, 75.0) if kind == "fault" else None
        if kind == "fault":
            rows = [(t, ok if not (60 <= t <= 75) else (k % 3 != 0)) for k, (t, ok) in enumerate(rows)]
        c = {"cell": "%s-%d" % (kind, i), "kind": kind, "valid": True, "rows": rows, "rowsKind": "ledger",
             "m": (0.0, 120.0), "w": w, "rate": 10.0, "faultTiming": True if kind == "fault" else None}
        if defect == "no-traffic-in-window" and kind == "fault" and i == 0:
            c["rows"] = [(t, ok) for t, ok in rows if not (60 <= t <= 75)]
        if defect == "failing-before-fault" and kind == "fault" and i == 0:
            c["rows"] = [(t, False if t < 60 else ok) for t, ok in rows]
        if defect == "idle-no-fault-windows" and kind == "nofault":
            c["rows"] = [(t, ok) for t, ok in rows if t < 50]
        if defect == "no-ledger" and i == 0:
            c["rows"], c["rowsKind"] = None, "none"
        if defect == "invalid-scored" and i == 0 and kind == "fault":
            c["valid"] = False
        return c
    pop = {"name": "synthetic:%s" % defect, "unit": "requests", "rateSource": "plan", "cells":
           [cell(i, "fault") for i in range(4)] + [cell(i, "nofault") for i in range(4)]}
    if defect == "invalid-scored":
        pop["filtersValidity"] = False
    return pop


def self_check():
    """Each planted defect must flip exactly its gate; the healthy population must pass every gate."""
    def verdicts(E):
        f = E["fault"]
        return {"G1": all(r["g1"]["pass"] for r in f), "G2": all(r["g2"]["pass"] for r in f),
                "G3": E["g3"]["verdict"] == "PASS", "G4": E["g4"]["pass"]}
    expect = {None: {"G1": True, "G2": True, "G3": True, "G4": True},
              "no-traffic-in-window": {"G1": False},
              "failing-before-fault": {"G2": False},
              "idle-no-fault-windows": {"G3": False},
              "no-ledger": {"G4": False},
              "invalid-scored": {"G4": False}}
    bad = 0
    for defect, want in expect.items():
        got = verdicts(evaluate(synthetic(defect)))
        for g, v in want.items():
            ok = got[g] == v
            bad += not ok
            print("%-24s %s expected %-5s got %-5s %s" % (defect or "healthy", g, v, got[g], "ok" if ok else "MISSED"))
    print("self-check: %s (%d mismatches)%s" % ("PASS" if not bad else "FAIL", bad,
                                                  "; broken gates: %s" % sorted(BROKEN) if BROKEN else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    if "--break" in sys.argv:
        BROKEN.update(sys.argv[sys.argv.index("--break") + 1].split(","))
    sys.exit(self_check() if "--self-check" in sys.argv else main(sys.argv[1:]))
