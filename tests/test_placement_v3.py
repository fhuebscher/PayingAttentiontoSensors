"""Placement v3 (research/placement/celf_v3.py, research/placement/cells_v3.py): lazy CELF on per-episode detection
times, the decision 72/73/75/76/77/79 rules, held-out folds, and the read-only companion on the frozen v3.1 loaders.

Layer: unit + synthetic end-to-end. SYNTHETIC instances only: hand-built tables and readout dicts, seeded random
instances checked against brute force, and v2.4's own synthetic Hotel cell generator (test_sweep_analysis_v3.make_v3)
run through the frozen v3.1 for the end-to-end checks. No readout of any SUT is read and no placement is computed on
evidence. Every rule has a check that passes and a planted defect (MUTANTS: a module-level switch flipped) under which
one of its checks fails (the pattern of tests/test_sweep_analysis_v3.py).
"""
from __future__ import annotations

import copy
import hashlib
from fractions import Fraction
import itertools
import json
import math
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "research" / "placement", ROOT / "research" / "detection-time", Path(__file__).resolve().parent):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import celf_v3 as cv  # noqa: E402
import cells_v3 as cells  # noqa: E402

INF = math.inf
TOL = 1e-9
LOWER = 0.5 * (1 - 1 / math.e)          # best of UC / CB under a knapsack (Leskovec et al. 2007 §3)
V3_SHA = "2e7ec5c387fa906a02026f0d1a5212b974f17751c24f76526a1d8418b2fd4fdd"


# ----------------------------------------------------------------------------- synthetic builders

def ep(regime="c1", rate=1.0, block=1, fires=(), hold=60.0, harness="sweep", ci=0, onset=100.0):
    return {"cell": "%s/%s/b%d/%s" % (harness, regime, block, rate), "regime": regime, "rate": rate, "block": block,
            "campaignIndex": ci, "harness": harness, "holdSeconds": hold, "onset": {"mono": onset},
            "fires": [list(f) for f in fires]}


def fire(fam, sid, ttd, own=False, counts=True, bc=(), rule="spike"):
    return [fam, sid, rule, ttd, "up", own, True, counts, list(bc), None]


def sensor(fam="T", placeable=True, upper=None, celf=None, appear_only=False, dropped=()):
    return {"family": fam, "placeable": placeable, "appearOnly": appear_only, "calibrated": ["spike"] if placeable
            else [], "dropped": list(dropped), "unarmed": [], "inert": [], "exempt": [], "celfCost": celf,
            "honestUpperPerHour": upper}


def readout(episodes, sensors, hours=1.0, rates=None):
    rates = rates or sorted({e["rate"] for e in episodes})
    per = {cv.rate_key(r): {"hours": hours, "cells": 4, "sensors": copy.deepcopy(sensors)} for r in rates}
    for x in per.values():
        x["sensors"].setdefault("ledger:frontend:r", sensor("E"))
    return {"system": "synthetic", "episodes": episodes, "calibration": {"primary": {"perRate": per}}}


def table(te, times, hold=60.0, regimes=None, failed=None):
    n = len(te)
    regimes = regimes or ["c"] * n
    eps = [{"regime": regimes[i], "rate": 1.0, "block": i + 1, "harness": "sweep", "campaignIndex": 0,
            "holdSeconds": hold} for i in range(n)]
    return cv.Table(eps, list(te), {k: list(v) for k, v in times.items()}, failed)


def toy():
    """Design §2's synthetic toy: H = 60; E catches ep1 at 40; a catches ep2 at 5; b ep2 at 10 and ep3 at 20."""
    return table([40, INF, INF], {"a": [INF, 5, INF], "b": [INF, 10, 20]})


def random_table(rng, n_s=5, n_e=5, penalty="ttd"):
    regimes = [rng.choice(["c1", "c2"]) for _ in range(n_e)]
    te = [rng.uniform(0, 60) if rng.random() < 0.4 else INF for _ in range(n_e)]
    times = {"s%d" % j: [rng.uniform(0, 60) if rng.random() < 0.45 else INF for _ in range(n_e)] for j in range(n_s)}
    failed = None
    if penalty == "impact":
        failed = [(100.0, sorted(rng.uniform(100.0, 160.0) for _ in range(rng.randint(0, 6)))) for _ in range(n_e)]
    return table(te, times, regimes=regimes, failed=failed)


def additive(gains, costs):
    """One episode per sensor, one class: sensor s alone catches its episode, gain_s = (H - t_s) / n."""
    n = len(gains)
    names = sorted(gains)
    te = [INF] * n
    times = {s: [INF] * n for s in names}
    for i, s in enumerate(names):
        times[s][i] = 60.0 - gains[s] * n
    return table(te, times), dict(costs)


def subsets(V):
    for k in range(len(V) + 1):
        yield from itertools.combinations(V, k)


def brute_opt(obj, V, costs, B):
    best = 0.0
    for S in subsets(V):
        if B == INF or math.fsum(costs[s] for s in S) <= B:
            best = max(best, obj.value(list(S)))
    return best


def naive(obj, cands, costs, B, mode, base=()):
    """Plain (non-lazy) greedy with canonical ties, stop at zero gain."""
    S, order, spent = list(base), [], []
    while True:
        cur, best = obj.value(S), None
        for s in sorted(cands):
            if s in S or not (B == INF or math.fsum(spent + [costs[s]]) <= B):
                continue
            g = obj.value(S + [s]) - cur
            k = g if mode == "UC" else g / costs[s]
            if best is None or (k > best[0] and not cv.tied(k, best[0])):
                best = (k, s, g)                          # sorted(cands): a tied later id never replaces
        if best is None or not cv.positive(best[2]):
            return order
        S.append(best[1])
        order.append(best[1])
        spent.append(costs[best[1]])


# ----------------------------------------------------------------------------- checks (True = holds)

def check_toy(ctx):
    o = cv.Objective(toy())
    D = {k: o.D(S) for k, S in {"E": [], "a": ["a"], "b": ["b"], "ab": ["a", "b"]}.items()}
    want = {"E": 160 / 3, "a": 105 / 3, "b": 70 / 3, "ab": 65 / 3}
    g = {"a": o.value(["a"]), "b": o.value(["b"]), "a|b": o.value(["a", "b"]) - o.value(["b"])}
    return (all(abs(D[k] - want[k]) < TOL for k in want) and abs(g["a"] - 55 / 3) < TOL and abs(g["b"] - 30) < TOL
            and abs(g["a|b"] - 5 / 3) < TOL and g["a|b"] <= g["a"])


def check_submodular(ctx):
    rng = random.Random(7)
    for _ in range(60):
        for pen in cv.PENALTIES:
            t = random_table(rng, penalty=pen)
            o = cv.Objective(t, penalty=pen)
            V = sorted(t.times)
            val = {S: o.value(list(S)) for S in subsets(V)}
            if abs(val[()]) > TOL:
                return False
            for S in val:
                for s in V:
                    if s in S:
                        continue
                    Ss = tuple(sorted(S + (s,)))
                    if val[Ss] < val[S] - TOL:                       # monotone
                        return False
                    for x in V:                                     # S ⊂ S + x: diminishing returns
                        if x in S or x == s:
                            continue
                        T = tuple(sorted(S + (x,)))
                        Ts = tuple(sorted(T + (s,)))
                        if val[Ss] - val[S] < val[Ts] - val[T] - TOL:
                            return False
    return True


def check_weights(ctx):
    t = table([INF] * 4, {}, regimes=["a", "b", "b", "b"])
    w = cv.Objective(t).w
    return all(abs(x - y) < TOL for x, y in zip(w, [0.5, 1 / 6, 1 / 6, 1 / 6]))


def check_lazy_equals_naive(ctx):
    rng = random.Random(11)
    for _ in range(150):
        t = random_table(rng, n_s=6, n_e=6)
        o = cv.Objective(t)
        V = sorted(t.times)
        costs = {s: rng.uniform(0.5, 3.0) for s in V}
        for B in (rng.uniform(1.0, 6.0), INF):
            for mode in ("UC", "CB"):
                if cv.greedy(o, V, costs, B, mode)["order"] != naive(o, V, costs, B, mode):
                    return False
    return True


def check_best_of(ctx):
    t1, c1 = additive({"big": 1.0, "small": 0.02}, {"big": 1.0, "small": 0.01})          # UC wins
    t2, c2 = additive({"one": 1.0, "p": 0.8, "q": 0.8}, {"one": 1.0, "p": 0.5, "q": 0.5})  # CB wins
    s1 = cv.solve(cv.Objective(t1), sorted(c1), c1, 1.0)
    s2 = cv.solve(cv.Objective(t2), sorted(c2), c2, 1.0)
    return (s1["mode"] == "UC" and s1["chosen"] == ["big"] and abs(s1["g"] - max(s1["gUC"], s1["gCB"])) < TOL
            and s2["mode"] == "CB" and sorted(s2["chosen"]) == ["p", "q"] and s1["gUC"] > s1["gCB"]
            and s2["gCB"] > s2["gUC"])


def check_guarantee(ctx):
    rng = random.Random(5)
    for _ in range(150):
        t = random_table(rng, n_s=6, n_e=6)
        o = cv.Objective(t)
        V = sorted(t.times)
        costs = {s: rng.uniform(0.5, 3.0) for s in V}
        B = rng.uniform(1.0, 6.0)
        sol = cv.solve(o, V, costs, B)
        if sol["g"] < LOWER * brute_opt(o, V, costs, B) - TOL or sol["charged"] > B + TOL:
            return False
    return True


def check_online_bound(ctx):
    rng = random.Random(3)
    for _ in range(300):
        t = random_table(rng, n_s=6, n_e=6)
        o = cv.Objective(t)
        V = sorted(t.times)
        costs = {s: rng.uniform(0.5, 3.0) for s in V}
        B = rng.choice([rng.uniform(1.0, 6.0), INF])
        opt = brute_opt(o, V, costs, B)
        sol = cv.solve(o, V, costs, B)
        A = sol["preAdmitted"] + sol["chosen"]
        if not (sol["g"] - TOL <= opt <= sol["g"] + sol["onlineBound"] + TOL):
            return False
        if sol["DOptLowerBound"] > sol["D"] + TOL or sol["DOptLowerBound"] > o.D(A) - opt + sol["g"] + TOL:
            return False
        if opt > o.value([]) + cv.online_bound(o, [], V, costs, B) + TOL:          # the bound holds for any A
            return False
    return True


def check_zero_cost(ctx):
    # a: cost 0, gain; c: cost 0, dominated by a; z: cost 0, never better than E; d: cost 2, gain
    t = table([30, INF, INF], {"a": [INF, 5, INF], "c": [INF, 9, INF], "z": [35, INF, INF], "d": [INF, INF, 10]})
    costs = {"a": 0.0, "c": 0.0, "z": 0.0, "d": 2.0}
    o = cv.Objective(t)
    V = sorted(costs)
    s1 = cv.solve(o, V, costs, 1.0)
    s2 = cv.solve(o, V, costs, 2.0)
    grid = [b for b, _ in cv.budget_grid(o, V, costs, 1.0)]
    return (s1["preAdmitted"] == ["a"] and s1["chosen"] == [] and s1["charged"] == 0.0
            and math.isfinite(s1["onlineBound"]) and s2["preAdmitted"] == ["a"] and s2["chosen"] == ["d"]
            and abs(s2["g"] - o.value(["a", "c", "z", "d"])) < TOL and 0.0 in grid and 2.0 in grid)


def check_stop_at_zero(ctx):
    t = table([30, INF], {"s1": [INF, 5], "s2": [INF, 10], "s3": [35, INF]})
    costs = {s: 1.0 for s in t.times}
    sol = cv.solve(cv.Objective(t), sorted(costs), costs, INF)
    return sol["chosen"] == ["s1"]


def check_ties(ctx):
    t = table([INF, INF], {"b": [10, INF], "a": [10, INF], "c": [INF, 30]})
    costs = {s: 1.0 for s in t.times}
    sol = cv.solve(cv.Objective(t), sorted(costs), costs, 1.0)
    return sol["chosen"] == ["a"] and cv.top_k(cv.Objective(t), sorted(costs), 1) == ["a"]


def _bc_readout():
    e1 = ep(block=1, fires=[fire("T", "span:x:op", 10, bc=["BC-caller-span"]),
                            fire("E", "ledger:frontend:r", 30, bc=["BC-ledger-stopped-on-path"], rule="absent")])
    e2 = ep(block=2, fires=[fire("T", "span:x:op", 20), fire("E", "ledger:frontend:r", 50, rule="failed")])
    return readout([e1, e2], {"span:x:op": sensor("T", upper=3.0)})


def check_bc_rules(ctx):
    J = _bc_readout()
    V = ["span:x:op"]
    got = {bc: cv.build_table(J, 1.0, V, bc) for bc in cv.BC_RULES}
    return (got["e-only"].te == [30, 50] and got["e-only"].T("span:x:op") == [INF, 20]
            and got["miss-all"].te == [INF, 50] and got["miss-all"].T("span:x:op") == [INF, 20]
            and got["count-all"].te == [30, 50] and got["count-all"].T("span:x:op") == [10, 20])


def check_own(ctx):
    J = readout([ep(block=1, fires=[fire("M", "metric:t:cpu", 5, own=True)]),
                 ep(block=2, fires=[fire("M", "metric:t:cpu", 8)]),
                 ep(block=3, fires=[fire("M", "metric:t:cpu", 2, own=True, counts=False)])],
                {"metric:t:cpu": sensor("M", upper=3.0)})
    V = ["metric:t:cpu"]
    got = {own: cv.build_table(J, 1.0, V, own=own).T("metric:t:cpu") for own in cv.OWN_RULES}
    return got == {"exclude": [INF, 8, INF], "include": [5, 8, INF], "only": [5, INF, INF]}


def check_ground_set(ctx):
    J = readout([ep()], {"span:a": sensor("T", upper=3.0), "log:b": sensor("L", upper=3.0, appear_only=True),
                         "metric:c": sensor("M", placeable=False, dropped=["spike"])})
    V, ex = cv.ground_set(J, 1.0)
    Vt, ext = cv.ground_set(J, 1.0, families=("T",))
    Va, _ = cv.ground_set(J, 1.0, appear_only=False)
    return (V == ["log:b", "span:a"] and "ledger:frontend:r" not in V and "dropped spike" in ex["metric:c"]
            and Vt == ["span:a"] and "family L" in ext["log:b"] and Va == ["span:a"])


def check_costs(ctx):
    sens = {"s:full": sensor(upper=2.9957, celf=0.0), "s:thin": sensor(upper=12.0, celf=4.0),
            "s:none": sensor(upper=None, celf=None), "s:np": sensor(placeable=False, upper=99.0)}
    J = readout([ep()], sens, hours=1.0)
    up, lab = cv.costs_of(J, 1.0, "upper")
    lit, llab = cv.costs_of(J, 1.0, "literal")
    evid = [up[s] for s in up if sens[s]["honestUpperPerHour"] is not None]
    never_dearer = all(up[s] >= max(evid) for s in up if sens[s]["honestUpperPerHour"] is None)
    return (never_dearer and up["s:none"] == 12.0 and up["s:full"] == 2.9957 and "s:np" not in up
            and lit == {"s:full": 0.0, "s:thin": 4.0, "s:none": 3.0} and "pre-admitted" in llab["s:full"]
            and "3/T_r" in llab["s:none"] and all(c > 0 for c in up.values()))


def check_per_rate(ctx):
    J = readout([ep(rate=1.0, block=1), ep(rate=10.0, block=1), ep(rate=1.0, block=2)], {"span:a": sensor(upper=3.0)})
    t = cv.build_table(J, 1.0, ["span:a"])
    return [e["rate"] for e in t.episodes] == [1.0, 1.0]


def _otel_shaped():
    eps = []
    for h, b, ci in (("sweep", 1, 0), ("B", 1, 1), ("B", 2, 1), ("B", 3, 1)):
        for reg in ("pause", "cpu"):
            eps.append(ep(regime=reg, block=b, harness=h, ci=ci))
    return readout(eps, {"span:a": sensor(upper=3.0)})


def check_fold_key(ctx):
    t = cv.build_table(_otel_shaped(), 1.0, ["span:a"])
    f = cv.folds(t)
    return (sorted(f) == [("B", 1), ("B", 2), ("B", 3), ("sweep", 1)] and all(len(v) == 2 for v in f.values())
            and cv.fold_merges(t) == {})


def check_held_out(ctx):
    # x catches only in fold (sweep, 1) and beats y there; held out, the training selection cannot see it
    fires_by_block = {1: [fire("T", "span:x", 5)], 2: [fire("T", "span:y", 20)], 3: [], 4: []}
    eps = [ep(regime="c", block=b, fires=fires_by_block[b]) for b in (1, 2, 3, 4)]
    J = readout(eps, {"span:x": sensor(upper=1.0), "span:y": sensor(upper=1.0)})
    V = ["span:x", "span:y"]
    t = cv.build_table(J, 1.0, V)
    costs = {s: 1.0 for s in V}
    h = cv.held_out(t, V, costs, 1.0, "ttd")
    row = next(r for r in h["folds"] if r["fold"] == ["sweep", 1])
    return row["chosen"] == ["span:y"] and abs(row["D"] - 60.0) < TOL and h["foldsScored"] == [4, 4]


def check_impact(ctx):
    sched = {"episodes": [
        {"regime": "c1", "rate": 1.0, "block": 1, "campaignIndex": 0, "harness": "sweep", "onsetMono": 100.0,
         "holdSeconds": 60.0, "failedScheduled": [100.0, 110.0, 130.0, 160.0]},
        {"regime": "c1", "rate": 1.0, "block": 2, "campaignIndex": 0, "harness": "sweep", "onsetMono": 100.0,
         "holdSeconds": 60.0, "failedScheduled": []}]}
    J = readout([ep(block=1, fires=[fire("E", "ledger:frontend:r", 10, rule="failed"), fire("T", "span:a", 30)]),
                 ep(block=2, fires=[fire("T", "span:a", 1)])], {"span:a": sensor(upper=3.0)})
    t = cv.build_table(J, 1.0, ["span:a"], schedule=sched)
    o = cv.Objective(t, penalty="impact")
    counts = [o._pi(0, 10), o._pi(0, 30), o._pi(0, INF), o._pi(0, 75)]
    bad = copy.deepcopy(sched)
    bad["episodes"][0]["onsetMono"] = 100.5
    try:
        cv.build_table(J, 1.0, ["span:a"], schedule=bad)
        joined = False
    except ValueError:
        joined = True
    return counts == [2.0, 3.0, 4.0, 4.0] and o.idx == [0] and o.D([]) == 2.0 and joined


def check_pareto_grid(ctx):
    t, c = additive({"p": 1.0, "q": 0.5, "r": 0.1}, {"p": 2.0, "q": 1.5, "r": 4.0})
    o = cv.Objective(t)
    grid = dict(cv.budget_grid(o, sorted(c), c, 1.2))
    cum = [2.0, 3.5, 7.5]                                    # CB order p (0.5/h), q (0.33), r (0.025)
    return (all(x in grid for x in cum) and grid[0.0] == ["0"] and grid[3 / 1.2] == ["3/T_r"] and grid[6.0] == ["6/h"]
            and grid[INF] == ["inf"])


def check_tie_margin(ctx):
    t = table([10, INF], {"s": [9.5, 4], "u": [8, 3]})
    m = cv.tie_margin(t, [1.0, 1.0])
    return m.T("s") == [10, 4] and m.T("u") == [8, 3]


def check_pin(ctx):
    v3 = cells.load_v3()
    return hasattr(v3, "placement_far") and hashlib.sha256(cells.V3_PATH.read_bytes()).hexdigest() == V3_SHA


# --- end to end on the synthetic Hotel campaign (v2.4's generator, the frozen v3.1)

def check_e2e_per_sensor(ctx):
    J = ctx["J"]
    sens = J["calibration"]["primary"]["perRate"]["1"]["sensors"]
    V = sorted(s for s, x in sens.items() if x["family"] != "E")
    t = cv.build_table(J, 1.0, V, bc="miss-all", own="include")
    compared = finite = 0
    for row in J["perSensor"]:
        if row["rate"] != 1.0:
            continue
        idx = [i for i, e in enumerate(t.episodes) if e["regime"] == row["regime"]]
        mine = [t.T(row["sensor"])[i] for i in idx]
        theirs = [INF if x is None else x for x in row["noBC"]["perEpisode"]]
        if mine != theirs:
            return False
        compared += 1
        finite += any(x < INF for x in mine)
    return compared >= 5 and finite >= 3


def check_e2e_ledger_impact(ctx):
    J = ctx["J"]
    sch = cells.schedule([ctx["camp"]], "hotel", readout=J)
    t = cv.build_table(J, 1.0, [], schedule=sch)
    o = cv.Objective(t, penalty="impact")
    compared = nonzero = 0
    for row in J["secondary"]:
        col = row["columns"].get("E")
        if row["rate"] != 1.0 or not col:
            continue
        idx = [i for i, e in enumerate(t.episodes) if e["regime"] == row["regime"]]
        for i, p in zip(idx, col["perEpisode"]):
            if o._pi(i, t.te[i]) != p["failedBefore"]:
                return False
            compared += 1
            nonzero += p["failedBefore"] > 0
    rows_ok = all(r["failedBeforeAtHold"] == len(r["failedScheduled"]) for r in sch["episodes"])
    return compared == len(t.episodes) == 12 and nonzero >= 1 and rows_ok


def check_e2e_far(ctx):
    J = ctx["J"]
    sens = J["calibration"]["primary"]["perRate"]["1"]["sensors"]
    allp = sorted(s for s, x in sens.items() if x["family"] != "E" and x["placeable"])
    one = next(s for s in allp if sens[s]["honest"] is not None)
    res = cells.far([ctx["camp"]], "hotel", {"1": [allp, [one]]}, readout=J)
    wrong = copy.deepcopy(J)
    wrong["provenance"]["input"]["sha256"] = "0" * 64
    try:
        cells.schedule([ctx["camp"]], "hotel", readout=wrong)
        return False
    except SystemExit:
        pass
    rows = {(r["setting"], tuple(r["sensors"])): r for r in res["rows"]}
    ref = J["placementFalseAlarms"]["primary"]["allPlaceable"]["1"]
    return (rows[("primary", tuple(allp))]["withoutLedger"]["union"] == ref["union"]
            and rows[("primary", (one,))]["withoutLedger"]["alarms"] == sens[one]["honest"]
            and rows[("primary", (one,))]["ledger"] and ("atMostOne", (one,)) in rows
            and res["readoutInputChecked"] == J["provenance"]["input"]["sha256"])


def check_e2e_run(ctx):
    J, out = ctx["J"], ctx["tmp"] / ("celf-%d.json" % len(list(ctx["tmp"].iterdir())))
    sch = cells.schedule([ctx["camp"]], "hotel", readout=J)
    jpath = ctx["tmp"] / "readout.json"
    if not jpath.exists():
        jpath.write_text(json.dumps(J, sort_keys=True))
    spath = out.with_suffix(".schedule.json")
    spath.write_text(json.dumps(sch, sort_keys=True))
    dpath = out.with_suffix(".declared.json")
    dpath.write_text(json.dumps({"selected": ["span:frontend:HTTP_GET_/hotels", "not:a:sensor"], "none": None}))
    cv.main([str(jpath), "--out", str(out), "--schedule", str(spath), "--declared", str(dpath), "--k-max", "2"])
    res = json.loads(out.read_text())
    try:
        cv.main([str(jpath), "--out", str(out)])
        refused = False
    except SystemExit:
        refused = True
    prim = res["arms"]["primary"]["1"]
    sets = cells.sets_of(res)
    return (refused and set(res["arms"]) == set(cv.ARMS) and prim["pareto"] and prim["scope"] == "instance"
            and prim["comparators"]["selected"]["outsideGroundSet"] == ["not:a:sensor"]
            and prim["comparators"]["none"]["describe"] is None and len(prim["cardinality"]) == 2
            and "impact" in prim["pareto"][0]["describe"] and sets.get("1") and res["inputs"]["python"]
            and all("pointKind" in p and "shortfall" in p["topK"] for p in prim["pareto"]))


def tie_table(rng, n_s=6, n_e=6):
    """Integer detection times, two classes: exact mathematical ties are common (review probe3)."""
    regimes = [rng.choice(["c1", "c2"]) for _ in range(n_e)]
    te = [rng.choice([30, INF, INF]) for _ in range(n_e)]
    times = {"s%d" % j: [rng.choice([5, 10, 20, INF, INF]) for _ in range(n_e)] for j in range(n_s)}
    return table(te, times, regimes=regimes)


def exact_naive(t, cands, costs, B, mode):
    """Plain greedy in exact rational arithmetic (ttd penalty, ledger fixed): the canonical-tie reference."""
    H = Fraction(60)
    per = {}
    for e in t.episodes:
        per[e["regime"]] = per.get(e["regime"], 0) + 1
    w = [Fraction(1, len(per) * per[e["regime"]]) for e in t.episodes]
    pi = (lambda x: H if x == INF else min(Fraction(x), H))
    pe = [pi(x) for x in t.te]

    def g(S):
        m = list(pe)
        for s in S:
            m = [min(a, pi(b)) for a, b in zip(m, t.T(s))]
        return sum(wi * (a - b) for wi, a, b in zip(w, pe, m))
    S, spent = [], Fraction(0)
    while True:
        best = None
        for s in sorted(cands):
            c = Fraction(costs[s])
            if s in S or (B != INF and spent + c > Fraction(B)):
                continue
            d = g(S + [s]) - g(S)
            k = d if mode == "UC" else d / c
            if best is None or k > best[0]:
                best = (k, s, d)
        if best is None or best[2] <= 0:
            return S
        S.append(best[1])
        spent += Fraction(costs[best[1]])


def check_lazy_ties_exact(ctx):
    rng = random.Random(1)
    for _ in range(400):
        t = tie_table(rng)
        o = cv.Objective(t)
        V = sorted(t.times)
        costs = {s: rng.choice([1.0, 1.0, 2.0]) for s in V}
        for B in (rng.choice([1.0, 2.0, 3.0, 4.0]), INF):
            for mode in ("UC", "CB"):
                ref = exact_naive(t, V, costs, B, mode)
                if cv.greedy(o, V, costs, B, mode)["order"] != ref or naive(o, V, costs, B, mode) != ref:
                    return False
    return True


def _modality_readout():
    """Review probe1's instance: T sensors a, b and L sensor l with distinct costs."""
    eps = [ep(block=1, fires=[fire("T", "span:a", 5), fire("L", "log:l", 7)]),
           ep(block=2, fires=[fire("T", "span:b", 10), fire("L", "log:l", 4)]),
           ep(block=3, fires=[fire("T", "span:b", 20)]),
           ep(block=4, fires=[fire("T", "span:a", 30)])]
    return readout(eps, {"span:a": sensor("T", upper=1.0, celf=0.0), "span:b": sensor("T", upper=2.0, celf=1.0),
                         "log:l": sensor("L", upper=0.5, celf=0.0)})


def check_grid_shared(ctx):
    res = cv.run(_modality_readout())
    arms = ("primary", "modality-T (81a)", "modality-T+L (81a)")
    grids = [[p["budget"] for p in res["arms"][a]["1"]["pareto"]] for a in arms]
    kinds = {p["pointKind"] for a in arms for p in res["arms"][a]["1"]["pareto"]}
    first = res["arms"]["primary"]["1"]["pareto"][0]
    return (grids[0] == grids[1] == grids[2] and kinds == {"named", "data-derived"} and first["names"] == ["0"]
            and first["pointKind"] == "named" and res["budgetGrid"]["perRate"]["1"])


def check_arm_costs(ctx):
    res = cv.run(_modality_readout())
    prim = res["arms"]["primary"]["1"]["costs"]
    same = all(res["arms"][a]["1"]["costs"] == {s: prim[s] for s in res["arms"][a]["1"]["costs"]}
               for a in cv.ARMS if a != "cost-literal (73)" and "costs" in res["arms"][a]["1"])
    lit = res["arms"]["cost-literal (73)"]["1"]["costs"]
    return same and prim == {"log:l": 0.5, "span:a": 1.0, "span:b": 2.0} and lit["span:a"] == 0.0


def check_fold_means(ctx):
    J = _modality_readout()
    V = sorted(s for s, x in J["calibration"]["primary"]["perRate"]["1"]["sensors"].items() if x["family"] != "E")
    t = cv.build_table(J, 1.0, V)
    h = cv.held_out(t, V, {s: 1.0 for s in V}, 1.0, "ttd")
    rows = [r for r in h["folds"] if r.get("D") is not None]
    mean = lambda k: sum(r[k] for r in rows) / len(rows)
    return (h["foldsScored"] == [4, 4] and abs(h["foldMeanD"] - mean("D")) < TOL
            and abs(h["foldMeanG"] - mean("g")) < TOL and abs(h["foldMeanDLedger"] - mean("DLedger")) < TOL
            and abs(h["foldMeanDTopK"] - mean("DTopK")) < TOL and all("topKShortfall" in r for r in rows))


def check_top_k_shortfall(ctx):
    t = table([INF, INF], {"a": [10, INF], "z": [INF, INF], "y": [70, INF]})
    o = cv.Objective(t)
    row = cv.top_k_row(o, t, ["a", "y", "z"], 3, {"a": 1.0, "y": 1.0, "z": 1.0})
    return cv.top_k(o, ["a", "y", "z"], 3) == ["a"] and row["shortfall"] == 2 and row["requested"] == 3


def check_fold_merges(ctx):
    J = readout([ep(block=1, ci=0), ep(block=1, ci=1), ep(block=2, ci=1)], {"span:a": sensor(upper=1.0)})
    t = cv.build_table(J, 1.0, ["span:a"])
    return cv.fold_merges(t) == {str(("sweep", 1)): [0, 1]} and len(cv.folds(t)) == 2


def check_main_refusals(ctx):
    J, d = ctx["J"], ctx["tmp"]
    sch = cells.schedule([ctx["camp"]], "hotel", readout=J)
    bad_j = copy.deepcopy(J)
    bad_j["scriptSha256"] = "0" * 64
    unchecked = dict(sch, readoutInputChecked=None)
    out = []
    for name, jj, ss in (("badj", bad_j, None), ("unchecked", J, unchecked)):
        jp, sp = d / ("ref-%s.json" % name), d / ("ref-%s.schedule.json" % name)
        jp.write_text(json.dumps(jj))
        sp.write_text(json.dumps(ss))
        args = [str(jp), "--out", str(d / ("ref-%s.out.json" % name))] + (["--schedule", str(sp)] if ss else [])
        try:
            cv.main(args)
            out.append(False)
        except SystemExit as exc:
            out.append("refusing" in str(exc) and not (d / ("ref-%s.out.json" % name)).exists())
    return all(out) and J["scriptSha256"] == V3_SHA


def check_sets_of(ctx):
    """Review probe6's instance: the k = 2 cardinality set (span:x, span:z) is in no Pareto, top-k or comparator set
    (z costs 6 > 6/h); sets_of must hand it, and every held-out fold's chosen and top-k set, to `far`."""
    eps = [ep(block=1, fires=[fire("T", "span:x", 0), fire("T", "span:y", 0)]),
           ep(block=2, fires=[fire("T", "span:x", 0)]),
           ep(block=3, fires=[fire("T", "span:y", 0)]),
           ep(block=4, fires=[fire("T", "span:z", 0)]),
           ep(block=5, fires=[fire("T", "span:z", 30)])]
    J = readout(eps, {"span:x": sensor("T", upper=1.0), "span:y": sensor("T", upper=1.0),
                      "span:z": sensor("T", upper=6.0)})
    res = cv.run(J, arms={"primary": {}}, k_max=3)
    pr = res["arms"]["primary"]["1"]
    card = {tuple(sorted(c["preAdmitted"] + c["chosen"])) for c in pr["cardinality"]}
    other = {tuple(sorted(p["set"])) for p in pr["pareto"]} | {tuple(sorted(p["topK"]["sensors"])) for p in pr["pareto"]}
    folds = {tuple(sorted(f[k])) for p in pr["pareto"] for f in p["heldOut"]["folds"] if f.get("chosen") is not None
             for k in ("chosen", "topK")}
    k2 = next(tuple(sorted(c["preAdmitted"] + c["chosen"])) for c in pr["cardinality"] if c["k"] == 2)
    # each source alone, the other stripped, so one cannot mask the other's omission
    only_card = copy.deepcopy(res)
    for p in only_card["arms"]["primary"]["1"]["pareto"]:
        p["heldOut"]["folds"] = []
    only_folds = copy.deepcopy(res)
    only_folds["arms"]["primary"]["1"]["cardinality"] = None
    got_c = set(map(tuple, cells.sets_of(only_card)["1"]))
    got_f = set(map(tuple, cells.sets_of(only_folds)["1"]))
    got = set(map(tuple, cells.sets_of(res)["1"]))
    return (k2 == ("span:x", "span:z") and k2 not in other and card <= got_c and folds <= got_f
            and bool(folds - other) and (card | folds | other) == got)


CHECKS = {
    "toy": check_toy, "submodular": check_submodular, "weights": check_weights,
    "lazy-equals-naive": check_lazy_equals_naive, "best-of": check_best_of, "guarantee": check_guarantee,
    "online-bound": check_online_bound, "zero-cost": check_zero_cost, "stop-at-zero": check_stop_at_zero,
    "ties": check_ties, "bc-rules": check_bc_rules, "own": check_own, "ground-set": check_ground_set,
    "costs": check_costs, "per-rate": check_per_rate, "fold-key": check_fold_key, "held-out": check_held_out,
    "impact": check_impact, "pareto-grid": check_pareto_grid, "tie-margin": check_tie_margin, "pin": check_pin,
    "e2e-per-sensor": check_e2e_per_sensor, "e2e-ledger-impact": check_e2e_ledger_impact, "e2e-far": check_e2e_far,
    "e2e-run": check_e2e_run, "lazy-ties-exact": check_lazy_ties_exact, "grid-shared": check_grid_shared,
    "arm-costs": check_arm_costs, "fold-means": check_fold_means, "top-k-shortfall": check_top_k_shortfall,
    "fold-merges": check_fold_merges, "main-refusals": check_main_refusals, "sets-of": check_sets_of,
}

MUTANTS = {   # label: (module, switch, planted value, checks of which at least one must fail[, expected failure])
    "a miss charged 0 (condition c)": (cv, "MISS_AT_HOLD", False, ["toy"]),
    "min over sensors of mean penalties (condition d)": (cv, "PER_EPISODE", False, ["toy"]),
    "P(i) uniform over episodes": (cv, "CLASS_WEIGHTS", False, ["weights"]),
    "ledger not in the placement (decision 1)": (cv, "LEDGER_FIXED", False, ["toy"]),
    "a sensor's BC catch counts (72)": (cv, "BC_SENSOR_MISS", False, ["bc-rules"]),
    "the ledger's BC catch a miss (72)": (cv, "BC_LEDGER_COUNTS", False, ["bc-rules"]),
    "own fires count in the primary (79)": (cv, "OWN_OUT", False, ["own"]),
    "no evidence at 3/T in the upper arm (73)": (cv, "COST_NULL_RULE", "3/T", ["costs"]),
    "rates pooled (75)": (cv, "PER_RATE", False, ["per-rate"]),
    "cost 0 enters the cost-benefit queue": (cv, "PRE_ADMIT_ZERO", False, ["zero-cost"], (ZeroDivisionError, "")),
    "stale CELF gain accepted": (cv, "LAZY_REEVALUATE", False, ["lazy-equals-naive"]),
    "cost-benefit greedy only": (cv, "BEST_OF_UC_CB", False, ["best-of"]),
    "zero-gain sensors added": (cv, "STOP_AT_ZERO", False, ["stop-at-zero"]),
    "ties to the largest id": (cv, "CANONICAL_TIES", False, ["ties"]),
    "online bound without the fractional item": (cv, "ONLINE_FRACTIONAL", False, ["online-bound"]),
    "fold key = block only": (cv, "FOLD_KEY", ("block",), ["fold-key"]),
    "fold selection sees the held-out fold": (cv, "FOLD_SELECT_TRAIN_ONLY", False, ["held-out"]),
    "exact float ties (lazy picks non-canonical)": (cv, "TIE_TOLERANCE", False, ["lazy-ties-exact"]),
    "each arm on its own knots (81)": (cv, "GRID_UNION", False, ["grid-shared"]),
    "impact counts every request (77)": (cells, "FAILED_ONLY", False, ["e2e-ledger-impact"],
                                         (SystemExit, "schedule disagrees with v1.failed_before")),
    "v3.1 digest not enforced": (cells, "PINNED_V3_SHA256", "0" * 64, ["pin"], (SystemExit, "refusing")),
    "cardinality sets not handed to far (87)": (cells, "SETS_CARDINALITY", False, ["sets-of"]),
    "fold sets not handed to far": (cells, "SETS_FOLDS", False, ["sets-of"]),
}


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    import test_sweep_analysis_v3 as t3       # v2.4's synthetic Hotel generator, as planted for v3's own tests
    base = tmp_path_factory.mktemp("placement_v3")
    camp = t3.make_v3(base / "main")
    v3 = cells.load_v3()
    R = v3.finish(v3.run(camp, reference=False))
    J = json.loads(json.dumps(v3.build_json(R), indent=1, sort_keys=True, default=sorted))
    out = base / "out"
    out.mkdir()
    return {"camp": camp, "J": J, "tmp": out}


def _outcome(name, ctx):
    """True / False, or the exception the check raised."""
    try:
        return bool(CHECKS[name](ctx))
    except (Exception, SystemExit) as exc:
        return exc


def _run_check(name, ctx):
    return _outcome(name, ctx) is True


def test_checks_pass(ctx):
    res = {n: _outcome(n, ctx) for n in CHECKS}
    assert all(v is True for v in res.values()), {k: v for k, v in res.items() if v is not True}


@pytest.mark.parametrize("label", sorted(MUTANTS))
def test_planted_defect_is_caught(label, ctx, monkeypatch):
    mod, attr, val, names, *expect = MUTANTS[label]
    assert hasattr(mod, attr)
    monkeypatch.setattr(mod, attr, val)
    got = [_outcome(n, ctx) for n in names]
    if expect:            # the intended failure is this exception, not any crash
        etype, text = expect[0]
        assert any(isinstance(g, etype) and text in str(g) for g in got), (label, got)
    else:                 # the intended failure is a check returning False, not a crash
        assert any(g is False for g in got), (label, got)


def test_every_switch_has_a_mutant():
    planted = {m[1] for m in MUTANTS.values() if m[0] is cv}
    assert planted == set(cv.SWITCHES)


def test_v3_unchanged_and_not_imported_from_framework():
    assert hashlib.sha256(cells.V3_PATH.read_bytes()).hexdigest() == V3_SHA
    for p in (ROOT / "research" / "placement").glob("*.py"):
        text = p.read_text()
        assert "import obsplacement" not in text and "from obsplacement" not in text, p
