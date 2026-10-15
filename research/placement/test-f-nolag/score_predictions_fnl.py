#!/usr/bin/env python3
"""Score the FNL-* predictions of research/protocol/PREDICTIONS_OVERNIGHT_20261014.json (8b89d43) against the F no-lag ablation's COMMITTED outputs.

Reads only committed files (no cell is opened):
  scorer output   research/placement/test-f-nolag/otel-nolag.json            (f31e5fb)
  post hoc lanes  research/lanes/out-f-nolag-posthoc/posthoc_lanes_v33_otel.json (8e52946)
  fresh FA        research/placement/test-f-nolag/fresh-fa-nolag/fresh_fa_f.json (0c794ec; the ablation's own frozen sets)
Each rule is the one the prediction record declares; nothing is edited after reading. The FNL-ONT-* items apply the rules of
research/ontology/compare.py (docstring and `item` logic, reproduced here because compare() reads hard-coded measured rows); the
ontology items are scored one by one. A prediction whose precondition is absent is `-` (not comparable), never a miss.

    uv run python research/placement/test-f-nolag/score_predictions_fnl.py --out research/placement/test-f-nolag/PREDICTIONS_SCORED
(writes <out>.json and <out>.md; refuses if either exists)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "research" / "ontology"))
import compare as cmp  # noqa: E402  imported, never edited

PRED = REPO / "research/protocol/PREDICTIONS_OVERNIGHT_20261014.json"
SCORED = REPO / "research/placement/test-f-nolag/otel-nolag.json"
LANES = REPO / "research/lanes/out-f-nolag-posthoc/posthoc_lanes_v33_otel.json"
FA_OWN = REPO / "research/placement/test-f-nolag/fresh-fa-nolag/fresh_fa_f.json"
SET6 = "frontier (effort<=any, runtime<=any) @6/T_r"
CLASS_OF = {"fraud-pause": "fraud-pause-effect", "accounting-pause": "accounting-pause-effect", "frontend-pause": "frontend-pause-effect"}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rng(xs):
    xs = [x for x in xs if x is not None]
    return [round(min(xs), 2), round(max(xs), 2)] if xs else None


def measured(scored, lanes):
    """Per-class lane rows {any, counted, episodes, range} from committed outputs (any field; counted beside it)."""
    ep = scored["rates"]["25"]["episodes"]
    by_pred = {p["id"]: p["numbers"] for p in lanes["predictions"]}
    out = {}
    for cls_short, cls in CLASS_OF.items():
        eps = [e for e in ep if e["class"] == cls]
        ledger = [e["ledger"]["ttd"] for e in eps]
        m = {"episodes": len(eps),
             "ledger": {"any": sum(1 for t in ledger if t is not None), "counted": sum(1 for t in ledger if t is not None),
                        "episodes": len(eps), "range": rng(ledger)}}
        if cls_short == "frontend-pause":
            m["own"] = None
            m["lag"] = None  # the post hoc output carries lag/own rows for the off-path episodes only
            fe = by_pred["F-L2"]
            assert fe["frontendNoFireEitherField"] is True or fe["frontendNoFireEitherField"] is False
            m["coordinator"] = ({"any": 0, "counted": 0, "episodes": len(eps), "range": None} if fe["frontendNoFireEitherField"] else None)
        else:
            own = [e for e in by_pred["F-L1"]["episodes"] if e["regime"] == cls]
            m["own"] = {"any": len(own), "counted": sum(1 for e in own if e["earliest"]["field"] == "counted"), "episodes": len(own),
                        "range": rng([e["earliest"]["ttd"] for e in own])}
            co = [e for e in by_pred["F-L2"]["episodes"] if e["regime"] == cls]
            anyt, cnt = [], []
            for e in co:
                c = e["countedEarliest"]["ttd"] if e["countedEarliest"] else None
                b = e["byConstructionEarliest"]["ttd"] if e["byConstructionEarliest"] else None
                cnt.append(c)
                anyt.append(min(x for x in (c, b) if x is not None) if (c is not None or b is not None) else None)
            m["coordinator"] = {"any": sum(1 for t in anyt if t is not None), "counted": sum(1 for t in cnt if t is not None),
                                "episodes": len(co), "range": rng(anyt), "rangeCounted": rng(cnt)}
            assert by_pred["F-L3"]["lagIdsInCalibration"] == 0  # the measured lag lane is not collected: not comparable, never a disagreement
            m["lag"] = None
        out[cls_short] = m
    return out


def score_ont(pred, m):
    """compare.py's per-row item logic applied to the prediction's answers and this run's measured row."""
    a = pred["answers"]
    items = []

    def item(name, p, me, verdict, note=""):
        items.append({"item": name, "predicted": p, "measured": me, "verdict": verdict, "note": note})

    for lane, pk in (("own", "ownLane"), ("coordinator", "coordinatorLane"), ("lag", "lagLane")):
        mv = m.get(lane)
        item("lane:" + lane, a[pk], mv, cmp.lane_cmp(a[pk], mv))
    pc1 = a["CQ-C1 class"]
    mc = m.get("coordinator")
    if mc is None:
        item("CQ-C1 class", pc1, None, "not comparable")
    else:
        saw = mc["any"] > 0
        item("CQ-C1 class", pc1, "coordinator %s" % ("fired" if saw else "silent"), "agree" if (pc1 == "tracked") == saw else "disagree",
             "from the coordinator lane (no class table for this campaign)")
    w = a["CQ-L2 window (s)"]
    if mc is None:
        item("CQ-L2 window", w, None, "not comparable")
    elif not w:
        item("CQ-L2 window", None, mc.get("range"), "not predicted" if mc["any"] else "agree",
             "no predicted window; coordinator %s" % ("fired" if mc["any"] else "silent"))
    else:
        lo, hi = (float(x) for x in w)
        r = mc.get("range")
        v = "disagree" if not r else ("agree" if lo <= r[0] and r[1] <= hi else ("partial" if r[0] <= hi and r[1] >= lo else "disagree"))
        item("CQ-L2 window", [lo, hi], r, v, "range is the any-field earliest per episode; counted-only range %s" % mc.get("rangeCounted"))
    item("CQ-B1 entry reached (proxy: ledger lane)", a["CQ-B1 entry service reached"], m["ledger"],
         cmp.lane_cmp(a["CQ-B1 entry service reached"], m["ledger"]))
    return items


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="output stem; writes <stem>.json and <stem>.md")
    args = ap.parse_args(argv)
    stem = Path(args.out)
    for suf in (".json", ".md"):
        if Path(str(stem) + suf).exists():
            raise SystemExit("refusing: exists (new evidence never overwrites old): %s%s" % (stem, suf))
    preds = {p["id"]: p for p in json.loads(PRED.read_text())["predictions"] if p["run"] == "FNL"}
    scored, lanes = json.loads(SCORED.read_text()), json.loads(LANES.read_text())
    fa_own = json.loads(FA_OWN.read_text())
    r = scored["rates"]["25"]
    by_lane = {p["id"]: p for p in lanes["predictions"]}
    M = measured(scored, lanes)
    res = []

    def put(pid, verdict, basis):
        res.append({"id": pid, "verdict": verdict, "rule": preds[pid]["rule"], "basis": basis})

    # ontology (items scored separately)
    for pid, cls in (("FNL-ONT-fraud", "fraud-pause"), ("FNL-ONT-accounting", "accounting-pause"), ("FNL-ONT-frontend", "frontend-pause")):
        items = score_ont(preds[pid], M[cls])
        res.append({"id": pid, "verdict": "items", "rule": preds[pid]["rule"], "items": items,
                    "basis": {"measuredRow": M[cls]}})
    # lanes
    l1 = by_lane["F-L1"]["numbers"]
    put("FNL-L1", "hit" if (l1["n"] == 4 and l1["k"] == 4) else "miss",
        {"k": l1["k"], "n": l1["n"], "ttd": [(e["regime"], e["block"], e["earliest"]["ttd"], e["earliest"]["field"]) for e in l1["episodes"]]})
    l2 = by_lane["F-L2"]["numbers"]
    ok2 = l2["offpathInWindow"] == 4 and l2["frontendNoFireEitherField"] is True
    put("FNL-L2", "hit" if ok2 else "miss",
        {"offpathInWindow": l2["offpathInWindow"], "frontendNoFireEitherField": l2["frontendNoFireEitherField"],
         "countedTtd": [(e["regime"], e["block"], e["countedEarliest"]["ttd"]) for e in l2["episodes"]]})
    l3 = by_lane["F-L3"]["numbers"]
    put("FNL-L3", "-" if (l3["armed"] == 0 and l3["lagIdsInCalibration"] == 0) else "miss",
        {"armed": l3["armed"], "lagIdsInCalibration": l3["lagIdsInCalibration"]})
    lm = by_lane["F-M"]["numbers"]
    put("FNL-M", "hit" if (lm["placeableNonFlagdSdk"] >= 1 or lm["placeableNonFlagdSpanmetrics"] >= 1) else "miss",
        {"placeableNonFlagdSdk": lm["placeableNonFlagdSdk"], "placeableNonFlagdSpanmetrics": lm["placeableNonFlagdSpanmetrics"]})
    # verdicts
    sensors = r["sets"][SET6]["sensors"]
    put("FNL-V1", "hit" if any(s.startswith("metric:kafka:") for s in sensors) else "miss",
        {"set": SET6, "sensors": sensors, "size": r["sets"][SET6]["size"]})
    vd = {v["rule"]["class"]: v for v in r["verdicts"]}
    for pid, cls in (("FNL-V2", "fraud-pause-effect"), ("FNL-V3", "accounting-pause-effect")):
        v = vd[cls]
        put(pid, ("hit" if v["verdict"] == "PASS" else "miss") if v["episodesInPool"] >= 2 else "-",
            {"verdict": v["verdict"], "gE": v["gE"], "improved": v["improved"], "episodesInPool": v["episodesInPool"]})
    fe = [e for e in r["episodes"] if e["class"] == "frontend-pause-effect"]
    impr = sum(1 for e in fe if e["sets"][SET6]["improvesOnLedger"])
    put("FNL-V4", "hit" if impr == 0 and len(fe) == 2 else "miss", {"improved": impr, "of": len(fe)})
    own6 = [x for x in fa_own["rows"] if x["set"] == "@6/T_r" and x["rule"].startswith("union of the sensor's 3 rules")]
    tot = sum(x["alarms"] for x in own6)
    put("FNL-V5", "hit" if (own6 and tot <= 4) else ("-" if not own6 else "miss"),
        {"ablationOwnSet": [(x["sensor"], x["alarms"], x["hours"], x["trainHonestUpperPerHour"], x["upperPerHour"]) for x in own6],
         "totalAlarms": tot})
    doc = {"label": "FNL predictions (8b89d43) scored against the ablation's committed outputs; the ablation launched 2026-10-15 01:53:28Z, after 8b89d43",
           "scope": "instance (fb14srv6, one SUT, one host, one pinned harness)",
           "inputs": {str(p.relative_to(REPO)): sha(p) for p in (PRED, SCORED, LANES, FA_OWN)},
           "script": str(Path(__file__).resolve().relative_to(REPO)), "scriptSha256": sha(__file__), "results": res}
    Path(str(stem) + ".json").write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")
    lines = ["# FNL predictions scored (F no-lag ablation otel-offpath-f-nolag-v1; instance scope)", "",
             "Rules: each prediction's own `rule` field in `research/protocol/PREDICTIONS_OVERNIGHT_20261014.json` (`8b89d43`); the ontology items by `research/ontology/compare.py`.",
             "Inputs: committed outputs only (digests in the json). The ablation launched after `8b89d43` (01:53:28Z, 2026-10-15).", "",
             "| id | verdict | basis |", "|---|---|---|"]
    for x in res:
        if x["verdict"] == "items":
            lines.append("| %s | see items below | |" % x["id"])
        else:
            lines.append("| %s | %s | `%s` |" % (x["id"], x["verdict"], json.dumps(x["basis"], sort_keys=True)))
    for x in res:
        if x["verdict"] == "items":
            lines += ["", "### %s" % x["id"], "", "| item | predicted | measured | verdict | note |", "|---|---|---|---|---|"]
            for it in x["items"]:
                lines.append("| %s | %s | %s | %s | %s |" % (it["item"], cmp._p(it["predicted"]), cmp._p(it["measured"]), it["verdict"], it["note"]))
    Path(str(stem) + ".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote %s.json %s.md" % (stem, stem))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
