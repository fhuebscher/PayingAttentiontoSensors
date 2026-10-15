#!/usr/bin/env python3
"""Score R3's predictions HO2-V, HO2-L, HO2-C (DECLARATION_HOTEL_OFFPATH_PLACEMENT.md) against the committed scorer output hotel-off2.json.

    uv run python research/placement/test-hotel-offpath-placement/score_predictions_ho2.py <new out stem>   # writes <stem>.json and <stem>.md

Rules, fixed before any value of hotel-off2.json is read (committed before it runs):
- HO2-V hit iff no verdict of a consul-pause-effect rule, at rate 10 or rate 1, is "PASS" (FAIL or dash both hit).
- HO2-L hit iff the ledger alone (episode field `ledger.ttd` not null) detects at most 1 of the consul-pause test episodes (both rates pooled).
- HO2-C hit iff the ledger detects every search-pause test episode (both rates pooled); the declaration expects 4 of 4.
A count of episodes other than the declared 4 is reported beside the hit. Scope: instance.
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = json.loads((HERE / "hotel-off2.json").read_text())
stem = Path(sys.argv[1])
assert not stem.with_suffix(".json").exists() and not stem.with_suffix(".md").exists(), "new evidence never overwrites old"
CONSUL, SEARCH = "consul-pause-effect", "search-pause-effect"
verdicts, consul, search = [], [], []
for rate, R in sorted(OUT["rates"].items()):
    for v in R.get("verdicts", []):
        if v["rule"]["class"] == CONSUL:
            verdicts.append({"rate": rate, "verdict": v["verdict"], "gE": v.get("gE"), "improved": v.get("improved")})
    for e in R["episodes"]:
        row = {"rate": rate, "block": e["block"], "ledgerTtd": e["ledger"]["ttd"]}
        (consul if e["class"] == CONSUL else search if e["class"] == SEARCH else []).append(row)
led_c = sum(r["ledgerTtd"] is not None for r in consul)
led_s = sum(r["ledgerTtd"] is not None for r in search)
res = {
    "HO2-V": {"hit": bool(verdicts) and all(v["verdict"] != "PASS" for v in verdicts), "verdicts": verdicts},
    "HO2-L": {"hit": led_c <= 1, "ledgerDetected": led_c, "episodes": len(consul), "rows": consul},
    "HO2-C": {"hit": len(search) > 0 and led_s == len(search), "ledgerDetected": led_s, "episodes": len(search), "rows": search},
}
stem.with_suffix(".json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
md = ["| id | hit | detail |", "|---|---|---|"]
md.append("| HO2-V | %s | %s |" % (res["HO2-V"]["hit"], "; ".join("rate %s %s" % (v["rate"], v["verdict"]) for v in verdicts)))
md.append("| HO2-L | %s | ledger %d of %d consul-pause test episodes |" % (res["HO2-L"]["hit"], led_c, len(consul)))
md.append("| HO2-C | %s | ledger %d of %d search-pause test episodes |" % (res["HO2-C"]["hit"], led_s, len(search)))
stem.with_suffix(".md").write_text("\n".join(md) + "\n")
print("\n".join(md))
