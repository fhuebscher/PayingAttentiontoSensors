"""Stage 6 comparison: committed PREDICTIONS.json vs measured lanes. POST HOC for every row (all campaigns were read).

Usage:  uv run python research/ontology/compare.py RUN_DIR      (writes RUN_DIR/COMPARISON.json and COMPARISON.md)

Measured values: pooled rows from research/lanes/out-pooled-20261014/pooled.json (`pooled` lanes summed over rates,
`coordinatorFailure` classes); campaign F and the TeaStore off-path epoch from their RESULT files (MEASURED_EXTRA below,
each value with the file:line it is copied from). Comparison rules (fixed here, applied to every row):
* lane (own / coordinator / lag): predicted yes/no (CQ-L1) against "detected in >= 1 episode, any field" (counted
  field reported beside it). Measured lane not collected (`—`) -> not comparable.
* CQ-C1 class against the measured class: hit counted or (d) by-construction hit -> the coordinator saw the fault
  (`tracked`); (b) -> heartbeat-stays-alive; (c) -> not-a-member; (a) -> not collected (not comparable). agree if every
  episode's measured class equals the prediction, partial if some, disagree if none.
* CQ-L2 window: predicted [low, high] against the measured coordinator detection-time range: agree if the range lies
  inside the window, partial if they overlap, disagree if they do not overlap or the coordinator never fired; no
  predicted window while the coordinator fired -> `not predicted`; neither -> agree.
* CQ-B1 against the request-ledger lane as a proxy for "the entry service is affected": predicted yes when the blast
  radius contains the system's entry service (ENTRY) or the target is one. A proxy, labelled so.
* CQ-S1: no campaign measures shared fate -> not comparable.
Disagreements are listed, not fixed: no prediction or ABox is edited after this comparison.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
POOLED = ROOT / "research/lanes/out-pooled-20261014/pooled.json"
ENTRY = {"hotel": {"frontend"}, "teastore": {"webui"}, "otel": {"frontendproxy", "frontend"}}
CLASS_MAP = {"hit-counted": "tracked", "d": "tracked", "b": "heartbeat-stays-alive", "c": "not-a-member", "a": None,
             "e": "unexplained"}
F = "research/placement/test-f/RESULT_F.md"
TS = "research/placement/test-ts-offpath/RESULT_TS_OFFPATH.md"
# (system, regime, source prefix) -> measured lanes; n = episodes; detected any / counted; times in s
MEASURED_EXTRA = {
    ("otel", "fraud-pause", "campaign F"): {
        "episodes": 2, "own": {"any": 2, "counted": 0, "range": [0.84, 1.52], "cite": F + ":42 (F-L1, 4/4 over both classes, BC field)"},
        "coordinator": {"any": 2, "counted": 2, "range": [43.3, 44.0], "cite": F + ":43 (F-L2, 4/4 over both classes, counted)"},
        "lag": {"any": 2, "counted": 2, "range": [4.8, 9.3], "cite": F + ":31-32 (fraud blocks 4, 5)"},
        "ledger": {"any": 1, "counted": 1, "range": [38.1, 38.1], "cite": F + ":31-32"}},
    ("otel", "accounting-pause", "campaign F"): {
        "episodes": 2, "own": {"any": 2, "counted": 0, "range": [0.84, 1.52], "cite": F + ":42 (F-L1, 4/4 over both classes, BC field)"},
        "coordinator": {"any": 2, "counted": 2, "range": [43.3, 44.0], "cite": F + ":43 (F-L2, 4/4 over both classes, counted)"},
        "lag": {"any": 2, "counted": 2, "range": [4.5, 9.2], "cite": F + ":29-30 (accounting blocks 4, 5)"},
        "ledger": {"any": 0, "counted": 0, "range": None, "cite": F + ":29-30"}},
    ("otel", "frontend-pause", "campaign F"): {
        "episodes": 2, "own": None,
        "coordinator": {"any": 0, "counted": 0, "range": None, "cite": F + ":43 (frontend none in either field)"},
        "lag": {"any": 2, "counted": 2, "range": [14.6, 14.6], "cite": F + ":36 (lag fires at 14.6 s)"},
        "ledger": {"any": 2, "counted": 2, "range": [0.3, 0.4], "cite": F + ":33-34"}},
    ("teastore", "recommender-pause", "TeaStore off-path"): {
        "episodes": 10, "own": {"any": 5, "counted": 5, "range": [14.86, 14.92], "cite": TS + ":19 (5/5 rate 10, none at rate 1)"},
        "coordinator": {"any": 10, "counted": 0, "range": [8.37, 12.03], "cite": TS + ":18 (T-L2, BC field)"},
        "lag": None,
        "ledger": {"any": 1, "counted": 1, "range": [5.07, 5.07], "cite": TS + ":20 (one counted spike, login ok share 1.0)"}},
    ("teastore", "auth-freeze", "TeaStore off-path"): {
        "episodes": 10, "own": None, "coordinator": None, "lag": None,
        "ledger": {"any": 10, "counted": None, "range": None, "cite": TS + ":21 (T-C: auth-freeze P1 holds 10/10)"}},
}


def pooled_measured():
    d = json.loads(POOLED.read_text())
    agg = {}
    for r in d["pooled"]:
        s, regime = r["key"][0], r["key"][1]
        a = agg.setdefault((s, regime), {"episodes": 0, "lanes": {}})
        a["episodes"] += r["episodes"]
        for lane in ("own", "coordinator", "lag", "ledger"):
            v = r["lanes"].get(lane)
            if v is None:
                a["lanes"].setdefault(lane, None)
                continue
            x = a["lanes"].get(lane) or {"any": 0, "counted": 0, "episodes": 0, "min": None, "max": None}
            x["any"] += v["any"]
            x["counted"] += v["counted"]
            x["episodes"] += v["episodes"]
            t = v["ttdAny"]
            if t["n"]:
                x["min"] = t["min"] if x["min"] is None else min(x["min"], t["min"])
                x["max"] = t["max"] if x["max"] is None else max(x["max"], t["max"])
            a["lanes"][lane] = x
    cf = {(r["system"], r["regime"]): r for r in d["coordinatorFailure"]}
    out = {}
    for k, a in agg.items():
        m = {"episodes": a["episodes"], "cite": "pooled.json `pooled` rows %s/%s summed over rates" % k}
        for lane, x in a["lanes"].items():
            m[lane] = None if x is None else {"any": x["any"], "counted": x["counted"], "episodes": x["episodes"],
                                              "range": None if x["min"] is None else [round(x["min"], 2), round(x["max"], 2)]}
        if k in cf:
            m["classes"] = cf[k]["classes"]
        out[k] = m
    return out


def lane_cmp(pred, meas):
    if meas is None or pred is None:
        return "not comparable"
    return "agree" if bool(pred) == (meas["any"] > 0) else "disagree"


def fmt_m(m):
    if m is None:
        return "—"
    n = m.get("episodes")
    s = "%s/%s" % (m["any"], n) if n is not None else "%s" % m["any"]
    if m.get("counted") is not None:
        s += " (counted %s)" % m["counted"]
    if m.get("range"):
        s += " %.2f-%.2f s" % tuple(m["range"])
    return s


def compare(run_dir):
    run_dir = Path(run_dir)
    pred = json.loads((run_dir / "PREDICTIONS.json").read_text())
    pm = pooled_measured()
    rows = []
    for i, r in enumerate(pred["rows"], 1):
        src = r["source"].split(" (")[0]
        key = (r["system"], r["regime"])
        if src == "pooled":
            m = pm.get(key)
        else:
            m = MEASURED_EXTRA[(r["system"], r["regime"], src)]
            for lane in ("own", "coordinator", "lag", "ledger"):
                if m.get(lane) is not None:
                    m[lane].setdefault("episodes", m["episodes"])
        ln = r["lanes"][0] if r.get("lanes") else {}
        row = {"n": i, "system": r["system"], "regime": r["regime"], "target": r["target"], "source": src,
               "label": "POST HOC", "measuredCite": m.get("cite") if m else None, "items": []}

        def item(name, p, me, verdict, note=""):
            row["items"].append({"item": name, "predicted": p, "measured": me, "verdict": verdict, "note": note})

        for lane, pk in (("own", "ownLane"), ("coordinator", "coordinatorLane"), ("lag", "lagLane")):
            mv = m.get(lane) if m else None
            item("lane:" + lane, ln.get(pk), mv, lane_cmp(ln.get(pk), mv),
                 (mv or {}).get("cite", ""))
        # CQ-C1
        pc = r.get("coordinatorClass", [])
        pc1 = pc[0] if pc else None
        if m and m.get("classes"):
            mapped = {}
            for c, n in m["classes"].items():
                mc = CLASS_MAP.get(c)
                mapped[mc] = mapped.get(mc, 0) + n
            if None in mapped and len(mapped) == 1:
                v = "not comparable"
            else:
                ok = mapped.get(pc1, 0)
                tot = sum(n for c, n in mapped.items() if c is not None)
                v = "agree" if ok == tot else ("partial" if ok else "disagree")
            item("CQ-C1 class", pc1, m["classes"], v, "measured class map: %s" % json.dumps(mapped))
        else:
            mc = m.get("coordinator") if m else None
            if mc is None:
                item("CQ-C1 class", pc1, None, "not comparable")
            else:
                saw = mc["any"] > 0
                v = ("agree" if (pc1 == "tracked") == saw else "disagree") if pc1 else "not comparable"
                item("CQ-C1 class", pc1, "coordinator %s" % ("fired" if saw else "silent"), v,
                     "from the coordinator lane (no class table for this campaign)")
        # CQ-L2
        w = r.get("coordinatorWindow", [])
        mc = m.get("coordinator") if m else None
        if mc is None:
            item("CQ-L2 window", [x["predictedWindowSeconds"] for x in w] or None, None, "not comparable")
        elif not w:
            item("CQ-L2 window", None, mc.get("range"), "not predicted" if mc["any"] else "agree",
                 "no predicted window; coordinator %s" % ("fired" if mc["any"] else "silent"))
        else:
            lo, hi = (float(x) for x in w[0]["predictedWindowSeconds"])
            rg = mc.get("range")
            if not rg:
                v = "disagree"
            elif lo <= rg[0] and rg[1] <= hi:
                v = "agree"
            else:
                v = "partial" if rg[0] <= hi and rg[1] >= lo else "disagree"
            item("CQ-L2 window", [lo, hi], rg, v)
        # CQ-B1 vs ledger proxy
        aff = {x["affected"].replace("svc-", "") for x in r.get("blastRadius", [])}
        entry = bool((aff | {r["target"]}) & ENTRY[r["system"]])
        ml = m.get("ledger") if m else None
        item("CQ-B1 entry reached (proxy: ledger lane)", entry, ml, lane_cmp(entry, ml),
             "blast radius %s" % (", ".join(sorted(aff)) or "—"))
        row["items"].append({"item": "CQ-S1 shared fate", "predicted": "see PREDICTIONS.md", "measured": None,
                             "verdict": "not comparable", "note": "no campaign measures shared fate"})
        rows.append(row)
    counts = {}
    for r in rows:
        for it in r["items"]:
            k = it["item"].split(" (")[0]
            counts.setdefault(k, {})
            counts[k][it["verdict"]] = counts[k].get(it["verdict"], 0) + 1
    return {"run": run_dir.name, "label": "POST HOC: every compared campaign was read before these predictions were made",
            "scope": "instance", "predictions": "PREDICTIONS.json (committed before this comparison)",
            "rules": "compare.py docstring", "rows": rows, "counts": counts}


def _p(x):
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, dict) and "any" in x:
        return fmt_m(x)
    if isinstance(x, list):
        return json.dumps(x)
    if isinstance(x, dict):
        return ", ".join("%s %s" % kv for kv in x.items())
    return str(x)


# What each run's ABoxes contain, read from the run's own files (final_spec.json rebuild logs, SHACL reports); no
# reading of cause beyond those files.
ABOX_NOTES = {
    "run1b-20261014": (
        "What the ABoxes contain, from the run's own files (no reading of cause is offered): no `ops:emits` fact was "
        "accepted for any row target except Hotel profile (emits were accepted for 7 non-target services; the fixed "
        "prompt does not ask for sensors) and no `ops:measuresLagOf` fact at all, so the own and lag lanes are "
        "predicted `no` almost everywhere; no accepted liveness record carries `failureTimeoutSeconds` (the SHACL "
        "violations of TeaStore and Hotel); the TeaStore registry record and one of the two Hotel consul records carry "
        "`healthCheckConfigured false`; OTel has no accepted Kafka coordinator (`final_spec.json` rebuild log: "
        "coordinator kafka missing name and type), so no OTel CQ-L2 row exists."),
    "run2-20261014": (
        "What the ABoxes contain, from the run's own files (no reading of cause is offered): as in run1b, no `ops:emits` "
        "fact for any row target except Hotel profile and no `ops:measuresLagOf` fact, so the own and lag lanes are "
        "predicted `no` almost everywhere. OTel now has the coordinator `kafka/consumer-group-session` with a "
        "consumer-group-session liveness record monitoring accountingservice and frauddetectionservice, "
        "`failureTimeoutSeconds` 45 and no `cleanupIntervalSeconds` (acceptance `library`: librdkafka / kafka-clients "
        "defaults attached through the uses-facts). The TeaStore registry liveness record now carries "
        "`failureTimeoutSeconds` 10 (judge-supported, `HeartbeatInfo.java:32`) and still `healthCheckConfigured "
        "false` (agreed; every instance cites the absence of a compose/Docker healthcheck), so CQ-C1 gives "
        "`no-liveness-check` and CQ-L2 has no TeaStore row. The Hotel consul liveness record is not emitted (rebuild "
        "log: no accepted `monitors`). SHACL conforms for all three systems."),
}


def to_md(c):
    L = ["# Ontology predictions vs measurements, %s" % c["run"], "",
         "**%s.** Scope: %s. Predictions: %s. Rules: `research/ontology/compare.py` docstring (lane = detected in >= 1 "
         "episode, any field; CQ-B1 compared with the request-ledger lane as a proxy for entry-service impact). "
         "Disagreements are listed and not fixed." % (c["label"], c["scope"], c["predictions"]), "",
         ABOX_NOTES.get(c["run"], "What the ABoxes contain: see the run's final_spec.json rebuild logs."),
         "",
         "## Summary (items over the 14 rows)", "", "| item | agree | partial | disagree | not predicted | not comparable |",
         "|---|---|---|---|---|---|"]
    for k, v in c["counts"].items():
        L.append("| %s | %s |" % (k, " | ".join(str(v.get(x, 0)) for x in
                                              ("agree", "partial", "disagree", "not predicted", "not comparable"))))
    L += ["", "## Per row", ""]
    for r in c["rows"]:
        L.append("### %d. %s %s on %s (%s), POST HOC" % (r["n"], r["system"], r["regime"], r["target"], r["source"]))
        L.append("")
        L.append("Measured from: %s" % (r["measuredCite"] or "per item"))
        L.append("")
        L.append("| item | predicted | measured | verdict | note |")
        L.append("|---|---|---|---|---|")
        for it in r["items"]:
            L.append("| %s | %s | %s | %s | %s |" % (it["item"], _p(it["predicted"]), _p(it["measured"]), it["verdict"],
                                                    it["note"].replace("|", "/")))
        L.append("")
    L += ["## Disagreements and non-predictions", ""]
    for r in c["rows"]:
        for it in r["items"]:
            if it["verdict"] in ("disagree", "partial", "not predicted"):
                L.append("- row %d %s %s, %s: predicted %s, measured %s (%s)" % (
                    r["n"], r["system"], r["regime"], it["item"], _p(it["predicted"]), _p(it["measured"]), it["verdict"]))
    return "\n".join(L) + "\n"


def diff_runs(a_json, b_json):
    """Markdown table: per row and item, the verdict in run A and in run B, and the predicted values where they differ."""
    A, B = json.loads(Path(a_json).read_text()), json.loads(Path(b_json).read_text())
    L = ["# %s vs %s: what changed per row" % (A["run"] if "run" in A else "run1b-20261014", B["run"]), "",
         "POST HOC (all campaigns read). One line per (row, item) whose prediction or verdict changed; generated by "
         "`compare.py diff` from the two COMPARISON.json files.", "",
         "| row | system | regime | item | %s predicted | %s verdict | %s predicted | %s verdict |" % (
             A.get("run", "run1b"), A.get("run", "run1b"), B["run"], B["run"]), "|---|---|---|---|---|---|---|---|"]
    n = 0
    for ra, rb in zip(A["rows"], B["rows"]):
        for ia, ib in zip(ra["items"], rb["items"]):
            if ia["predicted"] != ib["predicted"] or ia["verdict"] != ib["verdict"]:
                n += 1
                L.append("| %d | %s | %s | %s | %s | %s | %s | %s |" % (
                    ra["n"], ra["system"], ra["regime"], ia["item"], _p(ia["predicted"]), ia["verdict"],
                    _p(ib["predicted"]), ib["verdict"]))
    L += ["", "%d (row, item) pairs changed; all others are identical in both runs." % n, "",
          "## Summary side by side", "", "| item | %s agree/disagree/not predicted/not comparable | %s |" % (
              A.get("run", "run1b"), B["run"]), "|---|---|---|"]
    for k in B["counts"]:
        f = lambda c: "/".join(str(c.get(k, {}).get(x, 0)) for x in ("agree", "disagree", "not predicted", "not comparable"))
        L.append("| %s | %s | %s |" % (k, f(A["counts"]), f(B["counts"])))
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir")
    ap.add_argument("--diff-against", help="another run's COMPARISON.json; writes RUN_DIR/<other>_VS_<run>.md")
    a = ap.parse_args(argv)
    d = Path(a.run_dir)
    if a.diff_against:
        other = Path(a.diff_against)
        out = d / ("%s_VS_%s.md" % (other.parent.name.split("-")[0].upper(), d.name.split("-")[0].upper()))
        if out.exists():
            sys.exit("refusing to overwrite %s" % out)
        out.write_text(diff_runs(other, d / "COMPARISON.json"))
        print(out.read_text())
        return
    for n in ("COMPARISON.json", "COMPARISON.md"):
        if (d / n).exists():
            sys.exit("refusing to overwrite %s" % (d / n))
    c = compare(d)
    (d / "COMPARISON.json").write_text(json.dumps(c, indent=1, default=str) + "\n")
    (d / "COMPARISON.md").write_text(to_md(c))
    print(json.dumps(c["counts"], indent=1))


if __name__ == "__main__":
    main()
