#!/usr/bin/env python3
"""Score R1's predictions TS3-V, TS3-S, TS3-T, TS3-L, TS3-C (DECLARATION_TEASTORE_OFFPATH_PLACEMENT.md, 42c04f3) against the committed scorer output ts-rep3r1.json.

    uv run python research/placement/test-ts-placement/score_predictions_ts3.py <new out stem>   # writes <stem>.json and <stem>.md

Rules, committed before this script runs (the scorer output was committed, unread, in 4da3d99):
- TS3-V hit iff the recommender-pause-effect verdict is "PASS" at rate 10 AND at rate 1.
- TS3-S hit iff at both rates the frozen set named by that rule (`rule.set`, the @6/T_r frontier cell) is exactly ["log:webui:d4d75ec135e6"].
- TS3-T hit iff in every recommender-pause test episode (both rates) the frozen set's `ttd` (scorer field, seconds after the onset stamp) is in [9, 15];
  the declaration expects 4 episodes.
- TS3-L hit iff the ledger alone (`ledger.ttd` null) misses every recommender-pause test episode.
- TS3-C hit iff the ledger detects every auth-freeze test episode; the declaration expects 4 of 4.
Episode counts other than 4 are reported beside the hit. Scope: instance.
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = json.loads((HERE / "ts-rep3r1.json").read_text())
stem = Path(sys.argv[1])
assert not stem.with_suffix(".json").exists() and not stem.with_suffix(".md").exists(), "new evidence never overwrites old"
REC, AUTH, SENSOR = "recommender-pause-effect", "auth-freeze-effect", "log:webui:d4d75ec135e6"
verdicts, sets_, rec, auth = [], [], [], []
for rate, R in sorted(OUT["rates"].items()):
    for v in R.get("verdicts", []):
        if v["rule"]["class"] != REC:
            continue
        lab = v["rule"]["set"]
        verdicts.append({"rate": rate, "verdict": v["verdict"], "gE": v.get("gE"), "improved": v.get("improved"), "set": lab})
        sets_.append({"rate": rate, "set": lab, "sensors": R["sets"][lab]["sensors"]})
        for e in R["episodes"]:
            if e["class"] == REC:
                rec.append({"rate": rate, "block": e["block"], "ledgerTtd": e["ledger"]["ttd"], "setTtd": e["sets"][lab]["ttd"]})
    for e in R["episodes"]:
        if e["class"] == AUTH:
            auth.append({"rate": rate, "block": e["block"], "ledgerTtd": e["ledger"]["ttd"]})
res = {
    "TS3-V": {"hit": len(verdicts) == 2 and all(v["verdict"] == "PASS" for v in verdicts), "verdicts": verdicts},
    "TS3-S": {"hit": len(sets_) == 2 and all(s["sensors"] == [SENSOR] for s in sets_), "sets": sets_},
    "TS3-T": {"hit": bool(rec) and all(r["setTtd"] is not None and 9 <= r["setTtd"] <= 15 for r in rec), "episodes": len(rec), "rows": rec},
    "TS3-L": {"hit": bool(rec) and all(r["ledgerTtd"] is None for r in rec), "ledgerMissed": sum(r["ledgerTtd"] is None for r in rec), "episodes": len(rec)},
    "TS3-C": {"hit": bool(auth) and all(r["ledgerTtd"] is not None for r in auth), "ledgerDetected": sum(r["ledgerTtd"] is not None for r in auth), "episodes": len(auth), "rows": auth},
}
stem.with_suffix(".json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
md = ["| id | hit | detail |", "|---|---|---|",
      "| TS3-V | %s | %s |" % (res["TS3-V"]["hit"], "; ".join("rate %s %s (g %s, improved %s)" % (v["rate"], v["verdict"], v["gE"], v["improved"]) for v in verdicts)),
      "| TS3-S | %s | %s |" % (res["TS3-S"]["hit"], "; ".join("rate %s %s" % (s["rate"], s["sensors"]) for s in sets_)),
      "| TS3-T | %s | %s |" % (res["TS3-T"]["hit"], "; ".join("r%s b%s %s" % (r["rate"], r["block"], r["setTtd"]) for r in rec)),
      "| TS3-L | %s | ledger missed %d of %d |" % (res["TS3-L"]["hit"], res["TS3-L"]["ledgerMissed"], len(rec)),
      "| TS3-C | %s | ledger %d of %d auth-freeze test episodes |" % (res["TS3-C"]["hit"], res["TS3-C"]["ledgerDetected"], len(auth))]
stem.with_suffix(".md").write_text("\n".join(md) + "\n")
print("\n".join(md))
