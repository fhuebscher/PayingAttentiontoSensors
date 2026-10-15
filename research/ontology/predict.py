"""Stage 6 predictions: competency-question answers per (system, fault kind, target) row, from a run's Turtle ABoxes.

Usage:  uv run python research/ontology/predict.py RUN_DIR      (writes RUN_DIR/PREDICTIONS.json and PREDICTIONS.md)

Rows: every (system, regime, faultKind, target) of research/lanes/out-pooled-20261014/pooled.json `coordinatorFailure`
(keys only; no measured value is read here), plus the rows of campaign F (OTel fraud/accounting/frontend pause,
DECLARATION_F_OTEL.md) and of the TeaStore off-path epoch (recommender pause, auth freeze). Fault kind -> ops kind:
a regime named *cpu-throttle* -> ops:cpuThrottle, *net-delay* -> ops:netDelay, faultKind `pause` (incl. auth freeze)
-> ops:pause. Per row: CQ-L1 lanes, CQ-L2 coordinator window (the predicted window is [failureTimeout,
failureTimeout + cleanup] only; phaseLow is reported and labelled post hoc), CQ-C1 coordinator-failure class, CQ-B1
blast radius; CQ-S1 shared-fate groups per system. The ABoxes are used as built, SHACL violations included (they are
reported in <system>.shacl.txt, not repaired); a CQ that returns no row is `—`, never a negative.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import query  # noqa: E402

POOLED = ROOT / "research/lanes/out-pooled-20261014/pooled.json"
EXTRA_ROWS = [
    {"source": "campaign F (DECLARATION_F_OTEL.md, RESULT_F.md)", "system": "otel", "regime": "fraud-pause",
     "faultKind": "pause", "target": "frauddetectionservice"},
    {"source": "campaign F (DECLARATION_F_OTEL.md, RESULT_F.md)", "system": "otel", "regime": "accounting-pause",
     "faultKind": "pause", "target": "accountingservice"},
    {"source": "campaign F (DECLARATION_F_OTEL.md, RESULT_F.md)", "system": "otel", "regime": "frontend-pause",
     "faultKind": "pause", "target": "frontend"},
    {"source": "TeaStore off-path (DECLARATION_TEASTORE_OFFPATH.md, RESULT_TS_OFFPATH.md)", "system": "teastore",
     "regime": "recommender-pause", "faultKind": "pause", "target": "recommender"},
    {"source": "TeaStore off-path (DECLARATION_TEASTORE_OFFPATH.md, RESULT_TS_OFFPATH.md)", "system": "teastore",
     "regime": "auth-freeze", "faultKind": "pause", "target": "auth"},
]


def ops_kind(row):
    r = row["regime"]
    if "cpu-throttle" in r:
        return "cpuThrottle"
    if "net-delay" in r:
        return "netDelay"
    if row["faultKind"] == "pause":
        return "pause"
    raise SystemExit("no ops fault kind for %r" % row)


def rows():
    d = json.loads(POOLED.read_text())
    out = [{"source": "pooled (research/lanes/out-pooled-20261014/pooled.json)",
            **{k: r[k] for k in ("system", "regime", "faultKind", "target")}} for r in d["coordinatorFailure"]]
    return out + EXTRA_ROWS


def predict(run_dir):
    run_dir = Path(run_dir)
    graphs, inputs = {}, {}
    out = {"label": "PREDICTIONS from the run's ABoxes, committed before any comparison. Every campaign compared "
                    "later has already been read: the comparison is POST HOC for all rows.",
           "scope": "instance (one system at one pinned commit; the ABox as built, SHACL violations included)",
           "run": run_dir.name, "inputs": inputs, "rows": [], "sharedFate": {}}
    for i, r in enumerate(rows()):
        s = r["system"]
        if s not in graphs:
            p = run_dir / ("%s.ttl" % s)
            inputs["%s.ttl" % s] = hashlib.sha256(p.read_bytes()).hexdigest()
            graphs[s] = query.load(p)
            out["sharedFate"][s] = query.run_cq("S1", graphs[s])
        g, kind = graphs[s], ops_kind(r)
        tgt = query.resolve_target(g, r["target"])
        row = dict(r, opsKind=kind, targetInAbox=bool(tgt))
        if tgt:
            l1 = query.run_cq("L1", g, r["target"], kind)
            c1 = query.run_cq("C1", g, r["target"], kind)
            l2 = query.run_cq("L2", g, r["target"], kind)
            b1 = query.run_cq("B1", g, r["target"])
            row["lanes"] = [{k: x[k] for k in ("ownLane", "coordinatorLane", "coordinatorEmits", "lagLane")} for x in l1]
            row["coordinatorClass"] = [x["class"] for x in c1]
            row["coordinatorWindow"] = [{"coordinator": x["coordinator"], "liveness": x["liveness"],
                                         "predictedWindowSeconds": [x["low"], x["high"]],
                                         "failureTimeout": x["failureTimeout"], "cleanup": x["cleanup"],
                                         "heartbeat": x["heartbeat"],
                                         "phaseLowSeconds_POST_HOC": x["phaseLow"]} for x in l2]
            row["blastRadius"] = [{k: x[k] for k in ("effect", "affected", "via")} for x in b1]
        out["rows"].append(row)
    out["inputs"]["pooled.json (row keys only)"] = hashlib.sha256(POOLED.read_bytes()).hexdigest()
    return out


def _b(v):
    return "—" if v is None else ("yes" if v else "no")


def to_md(p):
    L = ["# Ontology predictions, run %s" % p["run"], "",
         "**%s** Scope: %s. Generated by `research/ontology/predict.py` from `<system>.ttl` (sha256 in "
         "PREDICTIONS.json); `—` = the competency question returned no row (not a negative)." % (p["label"], p["scope"]),
         "", "CQ-L2: the predicted coordinator window is `[failureTimeout, failureTimeout + cleanup]` only; "
         "`phaseLow` is reported in PREDICTIONS.json and labelled post hoc.", "",
         "A lane `no` means the ABox holds no fact that would open the lane (CQ-L1 is an EXISTS test): own lane = no "
         "`ops:emits` for the target (the fixed prompt does not ask for sensors, so this is `no` unless an extractor "
         "reported one); coordinator lane = no tracking liveness mechanism with `stopsHeartbeat`; lag lane = no "
         "emitted lag metric of the target's group. It is a statement about the extracted ABox, not a measured absence.",
         "",
         "| # | system | regime | target | kind | own lane | coord lane | coord emits | lag lane | CQ-C1 class | "
         "CQ-L2 window (s) | CQ-B1 blast radius | source |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(p["rows"], 1):
        if not r["targetInAbox"]:
            L.append("| %d | %s | %s | %s | %s | — | — | — | — | — | — | — | %s (target not in the ABox) |" % (
                i, r["system"], r["regime"], r["target"], r["opsKind"], r["source"]))
            continue
        ln = r["lanes"][0] if r["lanes"] else {}
        win = "; ".join("%s [%s, %s]" % (w["coordinator"], w["predictedWindowSeconds"][0], w["predictedWindowSeconds"][1])
                        for w in r["coordinatorWindow"]) or "—"
        br = "; ".join("%s %s" % (x["effect"], x["affected"]) for x in r["blastRadius"]) or "—"
        L.append("| %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            i, r["system"], r["regime"], r["target"], r["opsKind"], _b(ln.get("ownLane")), _b(ln.get("coordinatorLane")),
            _b(ln.get("coordinatorEmits")), _b(ln.get("lagLane")), ", ".join(r["coordinatorClass"]) or "—", win, br,
            r["source"].split(" (")[0]))
    L += ["", "## CQ-S1 shared-fate groups", ""]
    for s, rs in p["sharedFate"].items():
        groups = {}
        for x in rs:
            groups.setdefault((x["anchorType"], x["anchor"]), []).append(x["member"])
        L.append("**%s**" % s)
        L.append("")
        for (t, a), ms in sorted(groups.items()):
            L.append("- %s `%s`: %d members: %s" % (t, a, len(ms), ", ".join(sorted(ms))))
        L.append("")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir")
    a = ap.parse_args(argv)
    d = Path(a.run_dir)
    for n in ("PREDICTIONS.json", "PREDICTIONS.md"):
        if (d / n).exists():
            sys.exit("refusing to overwrite %s" % (d / n))
    p = predict(d)
    (d / "PREDICTIONS.json").write_text(json.dumps(p, indent=1, default=str) + "\n")
    (d / "PREDICTIONS.md").write_text(to_md(p))
    print(to_md(p))


if __name__ == "__main__":
    main()
