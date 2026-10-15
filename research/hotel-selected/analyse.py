#!/usr/bin/env python3
"""Hotel `selected` analysis (DECLARATION.md), committed before the run.

Runs the LMT pilot's `cost_steps.py` and `lmt_detect.py` unchanged, imported by path, with only the posture names
changed: postures none/metrics/selected/full; cost steps none->metrics, metrics->selected, selected->full,
metrics->full; spans of a `selected` cell are family `Tsel`, spans of a `full` cell family `T`, each gated by G3 on
its own no-fault windows. Then reads P1-P4 mechanically.

    /usr/bin/python3 -B research/hotel-selected/analyse.py <campaign x/ dir>     # the dir holding runs/
    /usr/bin/python3 -B research/hotel-selected/analyse.py --self-check
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PILOT = HERE.parent / "lmt-pilot"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, PILOT / ("%s.py" % name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cost = _load("cost_steps")
detect = _load("lmt_detect")

cost.POSTURES = ("none", "metrics", "selected", "full")
cost.STEPS = (("none", "metrics"), ("metrics", "selected"), ("selected", "full"), ("metrics", "full"))
detect.FAMILY_POSTURES = {"L": ("metrics", "selected", "full"), "M": ("metrics", "selected", "full"),
                          "T": ("full",), "Tsel": ("selected",), "S": ("none", "metrics", "selected", "full")}
_load_cell, _bag = detect.load_cell, detect.bag


def load_cell(attempt):
    """Spans are loaded for `selected` as well as `full` (the pilot loads them where family T is collected)."""
    saved = detect.FAMILY_POSTURES["T"]
    detect.FAMILY_POSTURES["T"] = ("selected", "full")
    try:
        return _load_cell(attempt)
    finally:
        detect.FAMILY_POSTURES["T"] = saved


def bag(cell):
    rows = _bag(cell)
    if cell["posture"] == "selected":
        for row in rows:
            row["sensors"] = [("Tsel",) + tuple(s[1:]) if s[0] == "T" else s for s in row["sensors"]]
    return rows


detect.load_cell, detect.bag = load_cell, bag
FAULTS = ("search-pause-effect", "reservation-pause-effect", "cpu-throttle-effect", "net-delay-effect")


def predictions(cost_out, detect_out):
    cls = detect_out["classes"]

    def caught(regime, fam):
        row = cls.get(regime, {}).get(fam)
        return None if row is None or row["n"] == 0 else (row["caught"], row["n"])   # no episodes: —, not 0

    def step_positive(step):
        axis = cost_out["steps"][step]["totalCpuSeconds"]
        return None if axis is None else (axis["positive"], axis["n"])

    def read(ok):
        return "—" if ok is None else ("yes" if ok else "no")

    p1 = [caught(r, "Tsel") for r in ("search-pause-effect", "reservation-pause-effect", "net-delay-effect")]
    p2 = [(caught(r, "Tsel"), caught(r, "T")) for r in FAULTS]
    p3, p4 = step_positive("selected->full"), step_positive("metrics->selected")
    return {
        "P1": {"reads": read(None if None in p1 else all(c == n == 4 for c, n in p1)), "Tsel": p1},
        "P2": {"reads": read(None if any(None in pair for pair in p2) else all(s[0] >= t[0] for s, t in p2)),
               "TselVsT": dict(zip(FAULTS, p2))},
        "P3": {"reads": read(None if p3 is None else p3 == (4, 4)), "positiveOfN": p3},
        "P4": {"reads": read(None if p4 is None else p4 == (4, 4)), "positiveOfN": p4},
    }


def self_check():
    cell = {"posture": "selected"}
    detect_bag = detect.bag
    global _bag
    saved, _bag = _bag, lambda c: [{"service": "frontend", "sensors": [("T", "frontend", "HTTP GET"), ("S", "frontend", "sys_cpu")]}]
    try:
        assert detect_bag(cell)[0]["sensors"] == [("Tsel", "frontend", "HTTP GET"), ("S", "frontend", "sys_cpu")]
        assert detect_bag({"posture": "full"})[0]["sensors"][0][0] == "T"
    finally:
        _bag = saved
    four = {"caught": 4, "n": 4}
    d = {"classes": {r: {"Tsel": dict(four), "T": dict(four)} for r in FAULTS}}
    d["classes"]["cpu-throttle-effect"] = {"Tsel": {"caught": 0, "n": 4}, "T": {"caught": 1, "n": 4}}
    c = {"steps": {"selected->full": {"totalCpuSeconds": {"positive": 4, "n": 4}},
                   "metrics->selected": {"totalCpuSeconds": {"positive": 3, "n": 4}}}}
    p = predictions(c, d)
    assert (p["P1"]["reads"], p["P2"]["reads"], p["P3"]["reads"], p["P4"]["reads"]) == ("yes", "no", "yes", "no")
    c["steps"]["metrics->selected"]["totalCpuSeconds"] = None
    assert predictions(c, d)["P4"]["reads"] == "—"
    d["classes"]["net-delay-effect"]["Tsel"] = {"caught": 0, "n": 0}     # a posture that never ran
    assert predictions(c, d)["P1"]["reads"] == "—"
    print("self-check: pass")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-check"]:
        self_check(); sys.exit(0)
    x = Path(sys.argv[1])
    attempts = sorted((x / "runs").glob("**/attempt-01"))
    if not attempts:   # the pilot scripts exit 0 on an empty path (RESULT.md ledger); this one does not
        sys.exit("no runs/**/attempt-01 under %s" % x)
    blocks = cost.collect(x)
    cost_out = {"completeBlocks": sorted(blocks), "cells": blocks, "steps": cost.steps(blocks)}
    cells = [detect.load_cell(a) for a in attempts]
    detect_out = detect.score(cells)
    detect_out["cells"], detect_out["validCells"] = len(cells), sum(1 for c in cells if c["valid"])
    print(json.dumps({"cost": cost_out, "detect": detect_out, "predictions": predictions(cost_out, detect_out)},
                     indent=1, sort_keys=True))
