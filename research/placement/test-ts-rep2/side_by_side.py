"""Side-by-side numbers of relaunch 1 and replication 2 (both from committed readouts; read-only). Usage: uv run python side_by_side.py <new out json>"""
import json, statistics, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
for p in (REPO / "research" / "placement", REPO / "research", REPO / "research" / "lanes"):
    sys.path.insert(0, str(p))
import pooled_lanes as pl  # noqa: E402
import celf_v3 as cv  # noqa: E402
FIRE = cv.FIRE
out = Path(sys.argv[1]); assert not out.exists()
SRC = {"r1": ("research/traffic-sweep/readout-teastore-offpath-r1-v3.3/sweep_analysis_v3_3.json", "research/lanes/out-ts-offpath-posthoc/posthoc_lanes_v33_teastore.json"),
       "rep2": ("research/traffic-sweep/readout-teastore-offpath-rep2-v3.3/sweep_analysis_v3_3.json", "research/lanes/out-ts-rep2-posthoc/posthoc_lanes_v33_teastore.json")}
WID = "log:webui:d4d75ec135e6"


def rng(xs):
    xs = [x for x in xs if x is not None]
    return [min(xs), max(xs)] if xs else None


res = {}
for name, (rp, pp) in SRC.items():
    J = json.loads((REPO / rp).read_text()); H = {p["id"]: p for p in json.loads((REPO / pp).read_text())["predictions"]}
    d = {"sources": [rp, pp], "campaignsRead": [c["campaign"] for c in J["campaignsRead"]]}
    for regime, key in (("recommender-pause-effect", "rec"), ("auth-freeze-effect", "auth")):
        rows = []
        for e in J["episodes"]:
            if e["regime"] == regime:
                rows.append((e, pl.episode_lanes(e, "teastore", set(), set())))
        r = {}
        for lane in ("own", "coordinator", "ledger"):
            for rate in (10.0, 1.0):
                v = [L[lane]["ttdAny"] for e, L in rows if e["rate"] == rate]
                r["%s_rate%g" % (lane, rate)] = {"ttdAny": sorted(x for x in v if x is not None), "detected": sum(x is not None for x in v), "n": len(v),
                                                  "median": statistics.median([x for x in v if x is not None]) if any(x is not None for x in v) else None}
        r["ownSensors(counted fires, all)"] = sorted({f[1] + "/" + f[2] for e, L in rows for f in e["fires"] if f[FIRE["own"]] and f[0] != "E" and f[FIRE["counts"]]})
        r["ownEpisodesWithAnyFireByRate"] = {"%g" % rate: sum(L["own"]["ttdAny"] is not None for e, L in rows if e["rate"] == rate) for rate in (10.0, 1.0)}
        if key == "rec":
            r["webui_ribbon_counted_ttd"] = sorted(min(f[FIRE["ttd"]] for f in e["fires"] if f[1] == WID and f[FIRE["counts"]] and not f[FIRE["bc"]]) for e, L in rows
                                                   if any(f[1] == WID and f[FIRE["counts"]] and not f[FIRE["bc"]] for f in e["fires"]))
        d[key] = r
    o = H["T-OFF"]["numbers"]
    d["T-L1_k"] = H["T-L1"]["numbers"]["k"]; d["T-L2_k"] = H["T-L2"]["numbers"]["k"]
    d["T-OFF"] = {"okShareK": o["okShareClause"]["k"], "episodesWithCountedLedgerFire": sum(e["ledgerFiresCounted"] > 0 for e in o["episodes"]),
                  "countedLedgerFires": [{"rate": e["rate"], "block": e["block"], "fires": [f for f in e["ledgerFires"] if f["counts"]]} for e in o["episodes"] if e["ledgerFiresCounted"] > 0],
                  "okTotals": sorted({(e["ok"], e["started"]) for e in o["episodes"]})}
    d["T-C"] = {k: H["T-C"]["numbers"][k] for k in ("holds", "k", "n")}
    res[name] = d
out.write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
print(json.dumps(res, indent=1, sort_keys=True)[:100])
