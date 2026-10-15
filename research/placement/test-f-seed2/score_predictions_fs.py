#!/usr/bin/env python3
"""Score R2's predictions FS-* (DECLARATION_F_OTEL_SEED2.md, committed alone before launch) against R2's COMMITTED outputs only.
Rules, as declared:
  FS-V1 PASS for both off-path classes under F's rule (scorer verdicts).
  FS-V2 the frozen @6/T_r set is ONE metric:kafka:* id (size 1 and that prefix).
  FS-L1 the ledger alone detects at most 1 of the 4 off-path test episodes.
  FS-L2 the Kafka coordinator log lane has a counted fire at 42-47 s in 4 of 4 off-path test episodes (post hoc lanes, F-L2's window).
  FS-C  frontend control: the ledger is first (< 1 s) in 2 of 2 test episodes, and g = 0 for that class.
  FS-FA post hoc, the frozen set raises at most 2 alarms in the held-out no-fault time (union per member, summed).
    uv run python research/placement/test-f-seed2/score_predictions_fs.py --out research/placement/test-f-seed2/PREDICTIONS_SCORED_FS
"""
import argparse
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
D = REPO / "research/placement/test-f-seed2"
SCORED, LANES = D / "otel-fs1.json", REPO / "research/lanes/out-fs1-posthoc/posthoc_lanes_v33_otel.json"
FA_F, FA_FLAGD = D / "fresh-fa-fs1/fresh_fa_f.json", D / "fresh-fa-fs1-flagd.json"
SET6 = "frontier (effort<=any, runtime<=any) @6/T_r"
OFF = ("fraud-pause-effect", "accounting-pause-effect")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    oj, om = Path(a.out + ".json"), Path(a.out + ".md")
    if oj.exists() or om.exists():
        raise SystemExit("refusing: output exists")
    S, L = json.loads(SCORED.read_text()), json.loads(LANES.read_text())
    R = S["rates"]["25"]
    ver = {v["rule"]["class"]: v for v in R["verdicts"]}
    eps = R["episodes"]
    off = [e for e in eps if e["class"] in OFF]
    fe = [e for e in eps if e["class"] == "frontend-pause-effect"]
    members = R["sets"][SET6]["sensors"]
    lanes = {p["id"]: p for p in L["predictions"]}
    l2 = [e["countedEarliest"]["ttd"] for e in lanes["F-L2"]["numbers"]["episodes"] if e.get("countedEarliest")]
    faf = json.loads(FA_F.read_text())
    union = {r["sensor"]: r["alarms"] for r in faf["rows"] if r["rule"].startswith("union")}
    fl = json.loads(FA_FLAGD.read_text())
    fresh = {}
    for m in members:
        if m in union:                     # correction (after the first output): rows carry the full sensor id
            fresh[m] = union[m]
        elif m == fl["sensor"]:
            fresh[m] = [r for r in fl["rows"] if r["rule"].startswith("union")][0]["alarms"]
        else:
            fresh[m] = None
    res = []
    res.append(("FS-V1", all(ver[c]["verdict"] == "PASS" for c in OFF), {c: ver[c]["verdict"] for c in OFF}))
    res.append(("FS-V2", len(members) == 1 and members[0].startswith("metric:kafka:"), {"members": members}))
    led = sum(1 for e in off if e["ledger"]["ttd"] is not None)
    res.append(("FS-L1", led <= 1, {"ledgerDetected": led, "of": len(off)}))
    res.append(("FS-L2", len(l2) == 4 and all(42 <= t <= 47 for t in l2), {"countedTtd": [round(t, 2) for t in l2]}))
    fc = [e["ledger"]["ttd"] for e in fe]
    fg = [v for v in R.get("classG", {}).items()] if R.get("classG") else None
    first = all(t is not None and t < 1 and e["sets"][SET6]["ttd"] is not None and e["sets"][SET6]["ttd"] >= t for t, e in zip(fc, fe))
    gfront = sum(e["ledger"]["penalised"] - e["sets"][SET6]["penalised"] for e in fe) / len(fe)
    res.append(("FS-C", first and abs(gfront) < 1e-9, {"ledgerTtd": [round(t, 3) for t in fc], "gFrontend": gfront}))
    tot = None if any(v is None for v in fresh.values()) else sum(fresh.values())
    res.append(("FS-FA", (tot is not None and tot <= 2) if tot is not None else None, {"perMember": fresh, "total": tot, "hours": faf.get("meta", {}).get("hours", 0.2)}))
    rows = [{"id": i, "result": ("hit" if ok else "miss") if ok is not None else "-", "numbers": n} for i, ok, n in res]
    rec = {"scope": "instance", "rows": rows,
           "inputs": {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (SCORED, LANES, FA_F, FA_FLAGD)},
           "scriptSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    oj.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    om.write_text("# R2 predictions scored (instance)\n\n| id | result | numbers |\n|---|---|---|\n" +
                  "".join("| %s | %s | `%s` |\n" % (r["id"], r["result"], json.dumps(r["numbers"], sort_keys=True)) for r in rows))
    print("wrote", oj, om)


if __name__ == "__main__":
    main()
