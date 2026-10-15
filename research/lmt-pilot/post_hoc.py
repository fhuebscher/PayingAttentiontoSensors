#!/usr/bin/env python3
"""POST HOC, not declared: the reviewer's questions on lmt2 (2026-09-29), computed from the same bags as lmt_detect.py,
which is imported unchanged.  Per regime x family: raw firings (G2 only, no G3), firings on the target itself (what G2
removes), the full tie set at the top count, and failed requests per cell.  Usage: post_hoc.py <x dir>"""
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

spec = importlib.util.spec_from_file_location("lmt_detect", Path(__file__).resolve().parent / "lmt_detect.py")
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)

x = Path(sys.argv[1])
attempts = sorted((x / "runs").glob("**/attempt-01"))
cells = [d.load_cell(a) for a in attempts]
d.score(cells)                                     # fills pseudo windows in place
fired = {id(c): {tuple(s) for r in d.bag(c) for s in r["sensors"]} for c in cells if c["valid"]}
out = {"failedRequests": Counter(), "classes": {}}
for a, c in zip(attempts, cells):
    failed = sum(json.loads(line)["outcome"] != "completed" for line in (a / "opportunity-ledger.jsonl").open())
    out["failedRequests"]["%s:%d" % (c["regime"], failed)] += 1
for fam, postures in d.FAMILY_POSTURES.items():
    for regime in sorted({c["regime"] for c in cells}):
        eps = [c for c in cells if c["regime"] == regime and c["posture"] in postures and c["valid"]]
        raw, target = Counter(), Counter()
        for c in eps:
            for s in fired[id(c)]:
                if s[0] == fam:
                    (target if s[1] == c["target"] else raw)[s] += 1
        top = max(raw.values(), default=0)
        out["classes"].setdefault(regime, {})[fam] = {
            "n": len(eps),
            "rawNonTargetTop": sorted("%s:%s:%s" % s for s, k in raw.items() if k == top) if top else [],
            "rawNonTargetTopCount": top,
            "rawNonTarget": {"%s:%s:%s" % s: k for s, k in sorted(raw.items())},
            "target": {"%s:%s:%s" % s: k for s, k in sorted(target.items())}}
out["failedRequests"] = dict(sorted(out["failedRequests"].items()))
print(json.dumps(out, indent=1))
