#!/usr/bin/env python3
"""Score every TSR-* prediction of PREDICTIONS_OVERNIGHT_20261014.json against the committed rep2 outputs, by each prediction's own rule.

    uv run python research/placement/test-ts-rep2/score_predictions.py <new out stem>   # writes <stem>.json and <stem>.md

Inputs (committed, read-only): the v3.3 readout of rep2 and the post hoc lane script's TeaStore output of rep2. Per-episode lane times come from
research/lanes/pooled_lanes.episode_lanes (the same function the scoring fields name: ttdAny = earlier of counted / by-construction), cross-checked here
against the readout's own v33.lanes block. Ontology rows use research/ontology/compare.py's rules (lane_cmp, CLASS_MAP). Nothing in a rule is changed after
reading; a miss is a miss. Scope: instance (TeaStore at 34b37f7, fb14srv5, harness 04254228).
"""
import json, statistics, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for p in (REPO / "research" / "placement", REPO / "research", REPO / "research" / "lanes", REPO / "research" / "ontology"):
    sys.path.insert(0, str(p))
import pooled_lanes as pl  # noqa: E402
import compare as cmp_  # noqa: E402
import celf_v3 as cv  # noqa: E402

DASH = "—"
READOUT = REPO / "research/traffic-sweep/readout-teastore-offpath-rep2-v3.3/sweep_analysis_v3_3.json"
POSTHOC = REPO / "research/lanes/out-ts-rep2-posthoc/posthoc_lanes_v33_teastore.json"
PRED = REPO / "research/protocol/PREDICTIONS_OVERNIGHT_20261014.json"
out_stem = Path(sys.argv[1])
assert not out_stem.with_suffix(".json").exists() and not out_stem.with_suffix(".md").exists(), "new evidence never overwrites old"
J = json.loads(READOUT.read_text()); H = json.loads(POSTHOC.read_text())
P = {p["id"]: p for p in json.loads(PRED.read_text())["predictions"] if p["id"].startswith("TSR")}
HP = {p["id"]: p for p in H["predictions"]}
FIRE = cv.FIRE
assert len(J["campaignsRead"]) == 1 and J["campaignsRead"][0]["valid"] == 30


def eps(regime):
    out = []
    for e in J["episodes"]:
        if e["regime"] != regime:
            continue
        L = pl.episode_lanes(e, "teastore", set(), set())
        out.append({"cell": e["cell"].split(" :: ")[1], "rate": e["rate"], "block": e["block"], "e": e, "L": L})
    return sorted(out, key=lambda x: (-x["rate"], x["block"]))


REC, AUTH = eps("recommender-pause-effect"), eps("auth-freeze-effect")
assert len(REC) == 10 and len(AUTH) == 10
# cross-check against the readout's own lanes block (counted and by-construction earliest, own and coordinator)
for regime, rows in (("recommender-pause-effect", REC), ("auth-freeze-effect", AUTH)):
    blk = {(float(x["rate"]), x["block"]): x for x in J["v33"]["lanes"]["regimes"][regime]["episodes"]}
    for r in rows:
        b = blk[(float(r["rate"]), r["block"])]["lanes"]
        for lane in ("own", "coordinator"):
            c = (b[lane]["earliest"] or {}).get("ttd"); bc = (b[lane]["earliestByConstruction"] or {}).get("ttd")
            assert c == r["L"][lane]["ttdCounted"] and bc == r["L"][lane]["ttdByConstruction"], (regime, r["cell"], lane)


def t(r, lane, which="ttdAny"):
    return r["L"][lane][which]


def rng(xs):
    xs = [x for x in xs if x is not None]
    return [min(xs), max(xs)] if xs else None


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def by_rate(rows, lane, which="ttdAny"):
    return {"%g" % rate: [t(r, lane, which) for r in rows if r["rate"] == rate] for rate in (10.0, 1.0)}


S = []


def add(pid, result, numbers, reason=""):
    S.append({"id": pid, "claim": P[pid]["claim"], "rule": P[pid]["rule"], "result": result, "numbers": numbers, "note": reason})


# ---- TSR-L2 (recommender coordinator)
k = HP["T-L2"]["numbers"]["k"]
fields = [e["inWindowFire"]["field"] if e["inWindowFire"] else None for e in HP["T-L2"]["numbers"]["episodes"]]
tt = [e["inWindowFire"]["ttd"] if e["inWindowFire"] else None for e in HP["T-L2"]["numbers"]["episodes"]]
add("TSR-L2", "hit" if k >= 9 else "miss",
    {"k": k, "n": 10, "need": 9, "window": [7.5, 12.5], "byRate": HP["T-L2"]["numbers"]["byRate"], "ttdRange": rng(tt),
     "fieldCounts": {f: fields.count(f) for f in sorted(set(x for x in fields if x))},
     "countedFires": sum(1 for r in REC if t(r, "coordinator", "ttdCounted") is not None),
     "perRate": {r_: rng(v) for r_, v in {"%g" % rate: [x for x, e in zip(tt, HP["T-L2"]["numbers"]["episodes"]) if e["rate"] == rate] for rate in (10.0, 1.0)}.items()}},
    "source: posthoc_lanes_v33_teastore.json predictions[T-L2]")
# ---- TSR-L2a (auth coordinator)
ta = [t(r, "coordinator") for r in AUTH]
inw = [x is not None and 7.5 <= x <= 12.5 for x in ta]
add("TSR-L2a", "hit" if sum(inw) >= 9 else "miss",
    {"k": sum(inw), "n": 10, "need": 9, "ttdRange": rng(ta), "byRate": {r_: rng(v) for r_, v in by_rate(AUTH, "coordinator").items()},
     "countedFires": sum(1 for r in AUTH if t(r, "coordinator", "ttdCounted") is not None),
     "byConstructionFires": sum(1 for r in AUTH if t(r, "coordinator", "ttdByConstruction") is not None)})
# ---- TSR-L1
k1 = HP["T-L1"]["numbers"]["k"]
own_lt5 = sum(1 for r in REC if t(r, "own") is not None and t(r, "own") < 5.0)
add("TSR-L1", "hit" if k1 <= 1 else "miss",
    {"episodesCpuDownBelow5s_T-L1_k": k1, "n": 10, "ceiling": 1, "ownLaneEarliestBelow5s_crossCheck": own_lt5})
# ---- TSR-L1b
own10 = by_rate(REC, "own")["10"]; own1 = by_rate(REC, "own")["1"]
in_band = [x is not None and 12.0 <= x <= 18.0 for x in own10]
fires1 = [x is not None for x in own1]
own_sensors = sorted({f[FIRE["sensorId"] + 0] + "/" + f[FIRE["rule"]] for r in REC for f in r["e"]["fires"]
                      if f[FIRE["own"]] and f[FIRE["family"]] != "E" and f[FIRE["counts"]]})
add("TSR-L1b", "hit" if (sum(in_band) >= 3 and sum(fires1) <= 1) else "miss",
    {"rate10": {"inBand12to18s": sum(in_band), "n": 5, "need": 3, "ownTtdAny": own10},
     "rate1": {"episodesWithOwnFire": sum(fires1), "n": 5, "ceiling": 1, "ownTtdAny": own1},
     "ownFiringSensorRulePairs(all rates, counted fires)": own_sensors})
# ---- TSR-L1c
a10 = by_rate(AUTH, "own")["10"]; a1 = by_rate(AUTH, "own")["1"]
det = sum(1 for r in AUTH if t(r, "own") is not None)
okc = det == 10 and max(a10) < 1.0 and max(a1) < 2.5
add("TSR-L1c", "hit" if okc else "miss",
    {"detected": det, "n": 10, "rate10": {"max": max(x for x in a10 if x is not None), "limit": 1.0, "ttdAny": a10},
     "rate1": {"max": max(x for x in a1 if x is not None), "limit": 2.5, "ttdAny": a1},
     "counted": {"rate10": by_rate(AUTH, "own", "ttdCounted")["10"], "rate1": by_rate(AUTH, "own", "ttdCounted")["1"]}})
# ---- TSR-OFF
off = HP["T-OFF"]["numbers"]
led_ep = sum(1 for e in off["episodes"] if e["ledgerFiresCounted"] > 0)
okk = off["okShareClause"]["k"]
add("TSR-OFF", "hit" if (okk >= 9 and led_ep <= 2) else "miss",
    {"okShareEpisodes": {"k": okk, "n": 10, "need": 9, "minShare": 0.95}, "episodesWithCountedLedgerFire": {"k": led_ep, "n": 10, "ceiling": 2},
     "declaredT-OFF_noCountedLedgerFireClause": off["noCountedLedgerFireClause"], "declaredT-OFF_result": HP["T-OFF"]["result"],
     "episodesWithCountedLedgerFire_detail": [{"cell": e["cell"].split(" :: ")[-1], "rate": e["rate"], "block": e["block"], "fires": [f for f in e["ledgerFires"] if f["counts"]]}
                                               for e in off["episodes"] if e["ledgerFiresCounted"] > 0]})
# ---- TSR-W
WID = "log:webui:d4d75ec135e6"
present = any(f[FIRE["sensorId"]] == WID for r in REC for f in r["e"]["fires"])
ground = WID in json.dumps(J.get("perSensor", {})) or present
wrows = []
for r in REC:
    fs = [f for f in r["e"]["fires"] if f[FIRE["sensorId"]] == WID and f[FIRE["counts"]] and not f[FIRE["bc"]]]
    rem = t(r, "coordinator")
    ttd = min((f[FIRE["ttd"]] for f in fs), default=None)
    wrows.append({"cell": r["cell"], "rate": r["rate"], "block": r["block"], "counted": bool(fs), "ttd": ttd,
                  "afterRemovalS": None if (ttd is None or rem is None) else ttd - rem})
kw = sum(1 for w in wrows if w["ttd"] is not None and 9.0 <= w["ttd"] <= 15.0)
add("TSR-W", (DASH if not ground else ("hit" if kw >= 9 else "miss")),
    {"k": kw, "n": 10, "need": 9, "window": [9.0, 15.0], "idInReadout": ground, "ttdRange": rng([w["ttd"] for w in wrows]),
     "afterRemovalRange": rng([w["afterRemovalS"] for w in wrows]), "episodes": wrows})
# ---- TSR-C
c = HP["T-C"]["numbers"]
add("TSR-C", "hit" if (c["holds"] and c["k"] >= 9 and c["n"] == 10) else "miss", {"holds": c["holds"], "k": c["k"], "n": c["n"], "perRate": c.get("perRate")})
# ---- TSR-D1
o10 = [x for x in by_rate(AUTH, "own")["10"]]; o1 = [x for x in by_rate(AUTH, "own")["1"]]
m10, m1 = med(o10), med(o1)
add("TSR-D1", "hit" if (m10 <= 0.5 * m1 and max(o10) < min(o1)) else "miss",
    {"median10": m10, "median1": m1, "ratio": m10 / m1, "max10": max(o10), "min1": min(o1), "ttd10": o10, "ttd1": o1})
# ---- TSR-D2
d2 = {}
for name, rows in (("auth-freeze", AUTH), ("recommender-pause", REC)):
    c10 = by_rate(rows, "coordinator")["10"]; c1 = by_rate(rows, "coordinator")["1"]
    a, b = med(c10), med(c1)
    r10, r1 = rng(c10), rng(c1)
    d2[name] = {"median10": a, "median1": b, "absDiff": abs(a - b), "range10": r10, "range1": r1,
                "rangesOverlap": r10[0] <= r1[1] and r1[0] <= r10[1], "ok": abs(a - b) <= 2.5 and (r10[0] <= r1[1] and r1[0] <= r10[1])}
add("TSR-D2", "hit" if all(v["ok"] for v in d2.values()) else "miss", d2)
# ---- TSR-D3
l10 = by_rate(AUTH, "ledger")["10"]; l1 = by_rate(AUTH, "ledger")["1"]
lm10, lm1 = med(l10), med(l1)
if lm10 is None or lm1 is None:
    add("TSR-D3", DASH, {"ledgerTtdAny10": l10, "ledgerTtdAny1": l1}, "no ledger fire at one rate: median undefined")
else:
    add("TSR-D3", "hit" if lm10 <= 0.5 * lm1 else "miss",
        {"median10": lm10, "median1": lm1, "ratio": lm10 / lm1, "ttd10": l10, "ttd1": l1,
         "episodesDetected": {"rate10": sum(x is not None for x in l10), "rate1": sum(x is not None for x in l1)},
         "note": "median over detected episodes" if None in l10 + l1 else "all 10 episodes detected"})


# ---- ontology rows (compare.py rules, post hoc label as in the prediction)
def meas(rows, lane):
    xs = [t(r, lane) for r in rows]
    cs = [t(r, lane, "ttdCounted") for r in rows]
    return {"any": sum(x is not None for x in xs), "counted": sum(x is not None for x in cs), "episodes": len(rows), "range": rng(xs)}


for pid, rows, target, kind in (("TSR-ONT-recommender", REC, "recommender", "pause"), ("TSR-ONT-auth", AUTH, "auth", "pause")):
    pr = P[pid]; ans = pr["answers"]
    m = {"own": meas(rows, "own"), "coordinator": meas(rows, "coordinator"), "lag": None, "ledger": meas(rows, "ledger")}
    classes = {}
    for r in rows:
        cc = pl.classify_coordinator("teastore", target, kind, r["L"]["coordinator"])
        classes[cc] = classes.get(cc, 0) + 1
    items = []
    for lane, key in (("own", "ownLane"), ("coordinator", "coordinatorLane"), ("lag", "lagLane")):
        items.append({"item": "lane:" + lane, "predicted": ans[key], "measured": m[lane], "verdict": cmp_.lane_cmp(ans[key], m[lane])})
    mapped = {}
    for cc, n in classes.items():
        mc = cmp_.CLASS_MAP.get(cc); mapped[mc] = mapped.get(mc, 0) + n
    okn = mapped.get(ans["CQ-C1 class"], 0); tot = sum(n for kk, n in mapped.items() if kk is not None)
    items.append({"item": "CQ-C1 class", "predicted": ans["CQ-C1 class"], "measured": {"classes": classes, "mapped": mapped},
                  "verdict": "not comparable" if tot == 0 else ("agree" if okn == tot else ("partial" if okn else "disagree"))})
    items.append({"item": "CQ-L2 window", "predicted": ans["CQ-L2 window (s)"], "measured": m["coordinator"]["range"],
                  "verdict": "not predicted" if (ans["CQ-L2 window (s)"] is None and m["coordinator"]["any"]) else "see rule"})
    items.append({"item": "CQ-B1 entry reached (proxy: ledger lane)", "predicted": ans["CQ-B1 entry service reached"], "measured": m["ledger"],
                  "verdict": cmp_.lane_cmp(ans["CQ-B1 entry service reached"], m["ledger"])})
    S.append({"id": pid, "claim": pr["claim"], "rule": pr["rule"], "result": "verdicts (ontology rows are agree/disagree items, not hit/miss)",
              "numbers": {"items": items, "priorComparisonVerdicts": pr["priorComparison"]["verdicts"], "expected": pr["expected"]}, "note": "POST HOC label as in the prediction"})

assert {s["id"] for s in S} == set(P), set(P) ^ {s["id"] for s in S}
doc = {"kind": "teastore-offpath-rep2-predictions-scored", "scope": "instance", "predictions": "research/protocol/PREDICTIONS_OVERNIGHT_20261014.json (8b89d43)",
       "inputs": {"readout": str(READOUT.relative_to(REPO)), "posthoc": str(POSTHOC.relative_to(REPO))},
       "counts": {r: sum(1 for s in S if s["result"] == r) for r in ("hit", "miss", DASH)}, "scored": S}
out_stem.with_suffix(".json").write_text(json.dumps(doc, indent=2, sort_keys=True, default=str) + "\n")


def f(x):
    return json.dumps(x, sort_keys=True, default=lambda o: o)


L = ["# TeaStore off-path replication 2: TSR-* predictions scored", "",
     "Scope: instance. Rules and thresholds exactly as committed in `PREDICTIONS_OVERNIGHT_20261014.json` (`8b89d43`); scored by `score_predictions.py` from the committed readout and post hoc output. Hit / miss / `—`; ontology rows are verdict items, not hit/miss.", "",
     "| id | result | numbers |", "|---|---|---|"]
for s in S:
    n = s["numbers"]
    if s["id"].startswith("TSR-ONT"):
        txt = "; ".join("%s: pred %s, meas %s -> %s" % (i["item"], f(i["predicted"]), f(i["measured"]), i["verdict"]) for i in n["items"])
    else:
        txt = f({k: v for k, v in n.items() if k not in ("episodes",)})
    L.append("| %s | **%s** | %s |" % (s["id"], s["result"], txt.replace("|", "/")))
out_stem.with_suffix(".md").write_text("\n".join(L) + "\n")
print(doc["counts"])
for s in S:
    print(s["id"], s["result"])
