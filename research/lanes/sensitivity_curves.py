#!/usr/bin/env python3
"""POST HOC sensitivity curves: detection versus false-alarm budget, per system, on the frozen method.

    uv run python research/lanes/sensitivity_curves.py --out research/lanes/out-sensitivity-20261014

NOTHING HERE IS PREREGISTERED AND NO FIELD DECIDES ANYTHING. Scope of every number: **instance** (one SUT, one host, one rate,
one readout pair per system; n = 2 to 12 test episodes). The frozen chain is imported and never edited: `celf_v3` (arm_setup,
solve, folds, Objective, build_table, ground_set), `celf_v3_2` (recurrence rule, tier file, input checks), `score_test_v3_2` (readout
checks, pins), `score_test_v3` (readout checks), and `posthoc_lanes_v33.zero_alarm_costs` (the post hoc zero-alarm price wrapper).
Only the budget axis is new: instead of the five named budgets, the same solver runs on a dense grid.

DEFINITION (also in CURVES.md and the figure caption).
  x     false-alarm budget per hour (decision 76's knapsack budget B on sum c(s)); 0 = the ledger alone (plus cost-0 sensors),
        multiples m x 3/T_r (m in 0.5 .. 64; T_r = the rate's training no-fault hours; 3/T_r = celf_v3.LITERAL_NULL_EVENTS / T_r,
        the frozen named unit, 0.14 % above the zero-alarm bound 2.9957/T_r), 6/h, 20/h, 60/h, 200/h, 600/h, 2000/h, inf.
  set   the CELF frontier set (effort<=any, runtime<=any) solved on the TRAINING readout at that budget: celf_v3.solve over the
        ground set (OTel E: after the decision-112 recurrence rule, as celf_v3_2.frontier_rate; TeaStore and Hotel: celf_v3's
        primary arm, which has no tiers and no recurrence rule). Two prices: decision 73 as frozen, and the post hoc zero-alarm
        price (posthoc_lanes_v33.zero_alarm_costs: appear-only ids evaluated in 0 folds cost 2.9957/T_r instead of the fill).
  test  OTel E: the scoring readout's held-out episodes (blocks 4-5), frozen sets scored as frozen. TeaStore: campaign C's episodes
        (campaignIndex 5 of the C readout), the placement solved on the training readout. Hotel: no held-out campaign exists, so
        LEAVE-ONE-BLOCK-OUT on the training readout (celf_v3's own fold key, (harness, block)): each block's episodes are scored with
        the set solved on the other three blocks, then pooled. A member absent from the scoring readout's ground set never fires.
  y_partial  share of test episodes detected (a counted fire of the ledger or of a set member, at or before the hold).
  y_strict   share of fault classes in which EVERY test episode is detected.
  also  median over the test episodes of the penalised time (a miss is charged the hold); g = D(ledger) - D(set), the frozen
        class-weighted mean penalised time (weights recomputed on the group's episodes, as the frozen scorer does).
  groups  OTel E is reported as `offpath` (fraud, accounting), `onpath` (frontend) and `all`; TeaStore and Hotel as `all`.

Switches (flipped only by tests/test_sensitivity_curves.py, a planted defect each): STRICT_EVERY_EPISODE, DEDUP_BUDGETS.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (REPO / "research" / "placement", REPO / "research" / "detection-time", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import celf_v3 as cv  # noqa: E402  frozen; imported, never edited
import celf_v3_2 as c2  # noqa: E402  frozen
import score_test_v3 as st1  # noqa: E402  frozen
import score_test_v3_2 as st2  # noqa: E402  frozen
import posthoc_lanes_v33 as ph  # noqa: E402  post hoc (committed); only its zero-alarm price wrapper is used

POST_HOC = "POST HOC (not preregistered; computed after the readouts were seen)"
SCOPE = "instance"
DASH = "—"
INF = math.inf
VERSION = "sensitivity-curves-20261014"
SWEEP = REPO / "research" / "traffic-sweep"
PLACEMENT = REPO / "research" / "placement"

# ---------------------------------------------------------------------------- switches (the test flips them)
STRICT_EVERY_EPISODE = True   # a class is strictly detected only if EVERY test episode is (False: planted: ANY episode)
DEDUP_BUDGETS = True          # budgets tied within celf_v3.KEY_REL_TOL merge their names (False: planted: both kept, last name wins)
SWITCHES = ("STRICT_EVERY_EPISODE", "DEDUP_BUDGETS")

MULTIPLES = (0.5, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64)
FIXED_PER_HOUR = (6.0, 20.0, 60.0, 200.0, 600.0, 2000.0)
DECLARED = ("0", "3/T_r", "6/T_r", "6/h", "inf")      # 6/T_r is a v3.2 name; the grid carries it for every system

SYSTEMS = {
    "otel-e": {
        "label": "OTel Demo, campaign E (off-path pauses)", "kind": "split",
        "train": SWEEP / "readout-otel-e-train-v3.2" / "sweep_analysis_v3_2.json",
        "score": SWEEP / "readout-otel-e-score-v3.2" / "sweep_analysis_v3_2.json",
        "tiers": PLACEMENT / "declared" / "otel.effort.json", "catalog": "postureCurrentCatalog",
        "frozenScoring": PLACEMENT / "test-e" / "otel-e.json", "frozenPlacement": PLACEMENT / "test-e" / "placement-e.json",
        "rates": (25.0,), "plotRate": 25.0,
        "groups": {"offpath": tuple(ph.OFFPATH_REGIMES_OTEL), "onpath": (ph.CONTROL_REGIME_OTEL,), "all": None},
    },
    "teastore": {
        "label": "TeaStore, campaign C (test)", "kind": "campaign",
        "train": SWEEP / "readout-teastore-primary-v3.1" / "sweep_analysis_v3.json",
        "score": SWEEP / "readout-teastore-c-v3.1" / "sweep_analysis_v3.json",
        "declared": PLACEMENT / "declared" / "teastore.declared.json",
        "frozenScoring": PLACEMENT / "test-c" / "teastore-c.json",
        "frozenPlacement": PLACEMENT / "out" / "teastore-primary" / "placement.json",
        "rates": (0.05, 0.2, 1.0, 10.0), "plotRate": 0.2, "groups": {"all": None},
    },
    "hotel": {
        "label": "Hotel Reservation, leave-one-block-out", "kind": "lobo",
        "train": SWEEP / "readout-hotel-primary-v3.1" / "sweep_analysis_v3.json",
        "declared": PLACEMENT / "declared" / "hotel.declared.json",
        "frozenPlacement": PLACEMENT / "out" / "hotel-primary" / "placement.json",
        "rates": (0.05, 0.2, 1.0, 10.0), "plotRate": 0.2, "groups": {"all": None},
    },
}


class Refused(SystemExit):
    pass


def refuse(msg):
    raise Refused("refusing: " + msg)


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and (math.isinf(o) or math.isnan(o)):
        return None
    return o


# =========================================================================== the budget grid

def budget_grid(hours):
    """[{label, value, names}] ascending; `names` holds the declared names (0, 3/T_r, 6/T_r, 6/h, inf) the point carries.
    Budgets tied within celf_v3.KEY_REL_TOL merge (DEDUP_BUDGETS)."""
    unit = cv.LITERAL_NULL_EVENTS / hours
    raw = [(0.0, "0", ["0"])]
    for m in MULTIPLES:
        names = {1: ["3/T_r"], 2: ["6/T_r"]}.get(m, [])
        raw.append((m * unit, "%gx3/T_r" % m, names))
    for b in FIXED_PER_HOUR:
        raw.append((b, "%g/h" % b, ["6/h"] if b == cv.FAR_BUDGET_PER_HOUR else []))
    raw.append((INF, "inf", ["inf"]))
    raw.sort(key=lambda r: r[0])
    out = []
    for v, label, names in raw:
        if DEDUP_BUDGETS and out and (out[-1]["value"] == v or (v not in (0.0, INF) and out[-1]["value"] not in (0.0, INF)
                                                                 and cv.tied(out[-1]["value"], v))):
            out[-1]["names"] = sorted(set(out[-1]["names"]) | set(names))
            if names and not out[-1]["declared"]:
                out[-1]["label"] = label
            out[-1]["declared"] = bool(out[-1]["names"])
            continue
        out.append({"label": label, "value": v, "names": list(names), "declared": bool(names)})
    return out


# =========================================================================== scoring of one set on one episode list

def eval_set(table, obj_all, idx, S):
    """Per test episode (in idx order): the penalised time with the set (ledger in) and the raw detection time (inf = miss)."""
    m = list(obj_all.pe)
    for s in S:
        m = [min(a, b) for a, b in zip(m, obj_all.pen(s))]
    raw = [min([table.te[i]] + [table.T(s)[i] for s in S]) for i in idx]
    return m, raw


def group_metrics(table, idx, pe, m, raw, classes):
    """The curve's four numbers on the episodes of `classes` (None = every class). Weights are the frozen Objective's, recomputed
    on the group's episodes (the frozen scorer does the same on its test subset)."""
    sel = [k for k, i in enumerate(idx) if classes is None or table.episodes[i]["regime"] in classes]
    if not sel:
        return {"episodes": 0, "detected": None, "partial": None, "strict": None, "medianPenalised": None, "g": None,
                "classes": {}}
    sub = cv.Objective(table, [idx[k] for k in sel], "ttd")
    D_led = math.fsum(w * pe[k] for w, k in zip(sub.w, sel))
    D = math.fsum(w * m[k] for w, k in zip(sub.w, sel))
    per = {}
    for k in sel:
        e = table.episodes[idx[k]]
        det = raw[k] < INF and raw[k] <= e["holdSeconds"]
        c = per.setdefault(e["regime"], [0, 0])
        c[0] += 1 if det else 0
        c[1] += 1
    n_det = sum(c[0] for c in per.values())
    n = sum(c[1] for c in per.values())
    strict_pred = (lambda c: c[0] == c[1]) if STRICT_EVERY_EPISODE else (lambda c: c[0] > 0)
    return {"episodes": n, "detected": n_det, "partial": n_det / n,
            "strict": sum(1 for c in per.values() if strict_pred(c)) / len(per),
            "medianPenalised": statistics.median(m[k] for k in sel), "g": D_led - D,
            "classes": {r: {"detected": c[0], "episodes": c[1]} for r, c in sorted(per.items())}}


def all_groups(table, idx, pe, m, raw, groups):
    return {name: group_metrics(table, idx, pe, m, raw, cls) for name, cls in groups.items()}


# =========================================================================== one (system, rate, pricing)

def comparator_sets(cfg, J, V, tiers):
    """{label: member list} of the comparators, from the training readout: ledger alone, full (the ground set V_r), and either
    out of the box (E: every ground-set sensor of effort tier 0) or the declared postures (TeaStore, Hotel; decision 78)."""
    comps = {"ledger alone": [], "full": list(V)}
    if tiers is not None:
        comps["out of the box"] = [s for s in V if (tiers.get(s) or {}).get("effort") == 0]
    else:
        dec = json.loads(Path(cfg["declared"]).read_text())
        for name in sorted(dec):
            if dec[name] is not None:
                comps["posture " + name] = sorted(dec[name])
    return comps


def solve_budget(obj, V_cap, costs, b):
    sol = cv.solve(obj, V_cap, {s: costs[s] for s in V_cap}, b)
    return sol["preAdmitted"] + sol["chosen"], sol


def training_setup(cfg, J, rate, tiers):
    """(V, V_cap, costs, table, obj, recurrence record or None) of the training readout, under the cost wrapper in force."""
    a, V, excluded, costs, labels, table, obj = cv.arm_setup(J, rate, None, None)
    rec = None
    V_cap = list(V)
    if tiers is not None:
        V_rec, rec = c2.recurrence(table, V)
        V_rec = set(V_rec)
        by_caps = c2.admitted(V, tiers, c2.ANY, c2.ANY)
        V_cap = [s for s in by_caps if s in V_rec]
    return V, V_cap, costs, table, obj, rec


def pricing_ctx(pricing):
    return ph.zero_alarm_costs() if pricing == "zeroAlarm" else contextlib.nullcontext()


def run_fixed(cfg, Jtr, Jsc, rate, pricing, tiers, test_selector):
    """OTel E and TeaStore: one set per budget solved on the training readout, scored once on the test episodes."""
    rk = cv.rate_key(rate)
    with pricing_ctx(pricing):
        V, V_cap, costs, ttab, tobj, rec = training_setup(cfg, Jtr, rate, tiers)
    hours = Jtr["calibration"]["primary"]["perRate"][rk]["hours"]
    grid = budget_grid(hours)
    Vs, excl = cv.ground_set(Jsc, rate)
    stab = cv.build_table(Jsc, rate, Vs, "e-only", "exclude")
    idx = test_selector(stab)
    if not idx:
        return {"note": "— (no test episode at this rate)"}
    sobj = cv.Objective(stab, idx, "ttd")
    pe = sobj.pe
    cache = {}

    def score(S):
        key = tuple(sorted(S))
        if key not in cache:
            m, raw = eval_set(stab, sobj, idx, S)
            cache[key] = all_groups(stab, idx, pe, m, raw, cfg["groups"])
            cache[key]["_ttd"] = [None if r == INF else r for r in raw]
        return cache[key]

    points = []
    for g in grid:
        S, sol = solve_budget(tobj, V_cap, costs, g["value"])
        sc = score(S)
        points.append({"label": g["label"], "budget": g["value"], "names": g["names"], "set": sorted(S), "size": len(S),
                       "mode": sol["mode"], "charged": sol["charged"], "trainG": sol["g"], "trainD": sol["D"],
                       "groups": {k: v for k, v in sc.items() if k != "_ttd"}, "ttd": sc["_ttd"]})
    comps = {}
    for lab, S in comparator_sets(cfg, Jtr, V, tiers).items():
        inV = [s for s in S if s in set(V)]
        sc = score(S)
        comps[lab] = {"members": len(S), "membersInTrainingGroundSet": len(inV),
                      "charged": math.fsum(costs[s] for s in inV), "groups": {k: v for k, v in sc.items() if k != "_ttd"},
                      "ttd": sc["_ttd"]}
    episodes = [{"cell": stab.episodes[i].get("cell"), "class": stab.episodes[i]["regime"], "block": stab.episodes[i]["block"],
                 "holdSeconds": stab.episodes[i]["holdSeconds"]} for i in idx]
    return {"rate": rate, "hours": hours, "trainingGroundSet": len(V), "candidates": len(V_cap),
            "zeroAlarmRepricedIds": len(ph.zero_alarm_ids(Jtr["calibration"]["primary"]["perRate"][rk])),
            "recurrence": ({k: rec[k] for k in ("groundSet", "withCountedFire", "recurring")} if rec else None),
            "testEpisodes": episodes, "points": points, "comparators": comps,
            "pricing": pricing, "testGroundSet": len(Vs)}


def run_lobo(cfg, J, rate, pricing):
    """Hotel: leave one (harness, block) fold out. The set of each budget is solved on the other folds (celf_v3.held_out's
    selection: the full-readout cost table, the training objective of the other folds) and scored on the held-out fold; the
    held-out episodes are pooled."""
    rk = cv.rate_key(rate)
    with pricing_ctx(pricing):
        V, V_cap, costs, table, obj, _ = training_setup(cfg, J, rate, None)
    hours = J["calibration"]["primary"]["perRate"][rk]["hours"]
    grid = budget_grid(hours)
    fl = cv.folds(table)
    idx = list(range(len(table.episodes)))
    allobj = cv.Objective(table, idx, "ttd")
    pe = allobj.pe
    pos = {i: k for k, i in enumerate(idx)}
    cache = {}

    def fold_set(key, b):
        ck = (key, b)
        if ck not in cache:
            train = [i for f, ii in fl.items() if f != key for i in ii]
            tr = cv.Objective(table, train, "ttd")
            cache[ck] = solve_budget(tr, V_cap, costs, b)
        return cache[ck]

    points = []
    for g in grid:
        m, raw = list(pe), [INF] * len(idx)
        sets, charged = {}, []
        for key, test in fl.items():
            S, sol = fold_set(key, g["value"])
            sets[json.dumps(list(key))] = sorted(S)
            charged.append(sol["charged"])
            for i in test:                       # the held-out episode is scored with ITS fold's set only
                k = pos[i]
                m[k] = min([pe[k]] + [allobj.pen(s)[k] for s in S])
                raw[k] = min([table.te[i]] + [table.T(s)[i] for s in S])
        points.append({"label": g["label"], "budget": g["value"], "names": g["names"], "foldSets": sets,
                       "sizeMean": statistics.mean(len(s) for s in sets.values()), "chargedMean": statistics.mean(charged),
                       "groups": all_groups(table, idx, pe, m, raw, cfg["groups"]),
                       "ttd": [None if r == INF else r for r in raw]})
    comps = {}
    for lab, S in comparator_sets(cfg, J, V, None).items():
        inV = [s for s in S if s in set(V)]
        m, raw = eval_set(table, allobj, idx, S)
        comps[lab] = {"members": len(S), "membersInTrainingGroundSet": len(inV),
                      "charged": math.fsum(costs[s] for s in inV),
                      "groups": all_groups(table, idx, pe, m, raw, cfg["groups"]),
                      "note": "scored on every episode of the readout (a fixed set has no fold to leave out)"}
    episodes = [{"cell": table.episodes[i].get("cell"), "class": table.episodes[i]["regime"],
                 "block": table.episodes[i]["block"], "holdSeconds": table.episodes[i]["holdSeconds"]} for i in idx]
    return {"rate": rate, "hours": hours, "trainingGroundSet": len(V), "candidates": len(V_cap), "folds": [list(k) for k in fl],
            "zeroAlarmRepricedIds": len(ph.zero_alarm_ids(J["calibration"]["primary"]["perRate"][rk])),
            "testEpisodes": episodes, "points": points, "comparators": comps, "pricing": pricing,
            "testBasis": "leave-one-block-out on the training readout (no held-out campaign exists)"}


# =========================================================================== inputs and checks

def load(path):
    return json.loads(Path(path).read_text())


def e_selector(Jsc):
    test_blocks = set(c2.E_SPLIT["test"])
    applies = set(((Jsc.get("v32") or {}).get("blockSelection") or {}).get("applies") or [])

    def sel(table):
        idx = [i for i, e in enumerate(table.episodes) if e["block"] in test_blocks and e.get("studyEpoch") in applies]
        if not all(table.episodes[i].get("heldOut") for i in idx):
            refuse("a test episode of the E scoring readout is not flagged heldOut")
        return idx
    return sel


def campaign_selector(ci):
    def sel(table):
        return [i for i, e in enumerate(table.episodes) if e.get("campaignIndex", 0) == ci]
    return sel


def check_inputs(name, cfg, Jtr, Jsc):
    """The frozen scorers' own input checks, called, not re-implemented."""
    c2.check_frozen_celf()
    if cfg["kind"] == "split":
        c2.check_readout(Jtr)
        st2.check_readout(Jsc)
    else:
        if Jtr.get("scriptSha256") != st1.PINNED_V3_SHA256:
            refuse("%s training readout is not the frozen v3.1" % name)
        if Jsc is not None:
            st1.check_readout(Jsc)


# =========================================================================== driver

def run_all():
    out = {"label": POST_HOC, "scope": SCOPE, "version": VERSION, "systems": {}, "inputs": {}}
    tiers_e, meta_e = c2.load_tiers(SYSTEMS["otel-e"]["tiers"], SYSTEMS["otel-e"]["catalog"])
    for name, cfg in SYSTEMS.items():
        Jtr = load(cfg["train"])
        Jsc = load(cfg["score"]) if cfg.get("score") else None
        check_inputs(name, cfg, Jtr, Jsc)
        out["inputs"][name] = {"train": str(cfg["train"].relative_to(REPO)), "trainSha256": sha256(cfg["train"]),
                               "score": str(cfg["score"].relative_to(REPO)) if cfg.get("score") else None,
                               "scoreSha256": sha256(cfg["score"]) if cfg.get("score") else None}
        sysout = {"label": cfg["label"], "kind": cfg["kind"], "plotRate": cfg["plotRate"], "rates": {}}
        if cfg["kind"] == "split":
            sel, tiers = e_selector(Jsc), tiers_e
            out["inputs"][name]["tiers"] = meta_e["sha256"]
        elif cfg["kind"] == "campaign":
            ci = st1.campaign_index(Jsc, path=load(cfg["frozenScoring"])["campaign"]["path"])
            sel, tiers = campaign_selector(ci), None
            out["inputs"][name]["campaignIndex"] = ci
        else:
            sel, tiers = None, None
        for rate in cfg["rates"]:
            rk = cv.rate_key(rate)
            sysout["rates"][rk] = {}
            for pricing in ("decision73", "zeroAlarm"):
                if cfg["kind"] == "lobo":
                    r = run_lobo(cfg, Jtr, rate, pricing)
                else:
                    r = run_fixed(cfg, Jtr, Jsc, rate, pricing, tiers, sel)
                sysout["rates"][rk][pricing] = r
        out["systems"][name] = sysout
    out["crossChecks"] = cross_checks(out)
    return out


# =========================================================================== cross-checks against the frozen outputs

def _point(res, name):
    for p in res["points"]:
        if name in p["names"]:
            return p
    return None


def _approx(a, b, tol=1e-9):
    return a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def cross_checks(out):
    """Every check is `ok` True/False with the two numbers; none is hidden."""
    rows = []
    # --- OTel E at the declared points, decision 73: sets, g and detected episodes vs research/placement/test-e/otel-e.json
    cfg = SYSTEMS["otel-e"]
    frozen = load(cfg["frozenScoring"])["rates"]["25"]["sets"]
    placement = load(cfg["frozenPlacement"])["rates"]["25"]
    cell = [c for c in placement["grid"] if c["maxEffort"] == "any" and c["maxRuntime"] == "any"][0]["points"]
    res = out["systems"]["otel-e"]["rates"]["25"]["decision73"]
    for nm in DECLARED:
        p = _point(res, nm)
        fz = frozen["frontier (effort<=any, runtime<=any) @%s" % nm]
        want_set = sorted(cell[nm]["set"])
        rows.append({"check": "E decision 73 @%s: set equals placement-e.json" % nm, "ok": p["set"] == want_set,
                     "mine": p["set"], "frozen": want_set})
        a = p["groups"]["all"]
        rows.append({"check": "E decision 73 @%s: g and detected episodes equal otel-e.json" % nm,
                     "ok": _approx(a["g"], fz["g"]) and [a["detected"], a["episodes"]] == fz["detectedEpisodes"],
                     "mine": [a["g"], a["detected"], a["episodes"]], "frozen": [fz["g"], fz["detectedEpisodes"]]})
    for lab in ("full", "out of the box", "ledger alone"):
        c = res["comparators"][lab]["groups"]["all"]
        fz = frozen[lab]
        rows.append({"check": "E comparator %s: g and detected equal otel-e.json" % lab,
                     "ok": _approx(c["g"], fz["g"]) and [c["detected"], c["episodes"]] == fz["detectedEpisodes"],
                     "mine": [c["g"], c["detected"], c["episodes"]], "frozen": [fz["g"], fz["detectedEpisodes"]]})
    # --- OTel E, zero-alarm pricing @6/T_r vs the committed post hoc lanes result (tests/test_posthoc_lanes_v33.py:163-166)
    z = _point(out["systems"]["otel-e"]["rates"]["25"]["zeroAlarm"], "6/T_r")["groups"]["all"]
    rows.append({"check": "E zero-alarm @6/T_r: g = 5.292 and 5 of 6 detected (posthoc_lanes_v33 on E)",
                 "ok": abs(z["g"] - 5.292) <= 5e-4 and [z["detected"], z["episodes"]] == [5, 6],
                 "mine": [z["g"], z["detected"], z["episodes"]], "frozen": [5.292, [5, 6]]})
    # --- TeaStore at the named points: set and g, detected vs teastore-c.json and the frozen placement
    cfg = SYSTEMS["teastore"]
    frz = load(cfg["frozenScoring"])["rates"]
    pl = load(cfg["frozenPlacement"])["arms"]["primary"]
    ok_all, n = True, 0
    detail = []
    for rk in ("0.05", "0.2", "1", "10"):
        res = out["systems"]["teastore"]["rates"][rk]["decision73"]
        named = {nm: p for p in pl[rk]["pareto"] for nm in p["names"] if nm in st1.NAMED}
        for nm in st1.NAMED:
            p = _point(res, nm)
            fz = frz[rk]["sets"]["primary %s" % nm]
            a = p["groups"]["all"]
            same_set = p["set"] == sorted(named[nm]["set"])
            same_num = _approx(a["g"], fz["g"]) and [a["detected"], a["episodes"]] == fz["detectedEpisodes"]
            n += 1
            ok_all = ok_all and same_set and same_num
            detail.append({"rate": rk, "budget": nm, "setEqual": same_set, "numbersEqual": same_num,
                           "mine": [a["g"], a["detected"], a["episodes"]], "frozen": [fz["g"], fz["detectedEpisodes"]]})
    rows.append({"check": "TeaStore decision 73 at the 4 named budgets x 4 rates (%d points): set equals the frozen placement, "
                          "g and detected equal teastore-c.json" % n, "ok": ok_all, "detail": detail})
    # --- Hotel: the fold sets at the named budgets equal the frozen placement's held-out folds
    pl = load(SYSTEMS["hotel"]["frozenPlacement"])["arms"]["primary"]
    ok_all, n, detail = True, 0, []
    for rk in ("0.05", "0.2", "1", "10"):
        res = out["systems"]["hotel"]["rates"][rk]["decision73"]
        named = {nm: p for p in pl[rk]["pareto"] for nm in p["names"] if nm in st1.NAMED}
        for nm in st1.NAMED:
            p = _point(res, nm)
            for f in named[nm]["heldOut"]["folds"]:
                n += 1
                mine = p["foldSets"].get(json.dumps(f["fold"]))
                same = f.get("chosen") is not None and mine == sorted(f["chosen"])
                ok_all = ok_all and same
                if not same:
                    detail.append({"rate": rk, "budget": nm, "fold": f["fold"], "mine": mine, "frozen": f.get("chosen")})
    rows.append({"check": "Hotel decision 73: the leave-one-block-out set of every fold at the named budgets equals the frozen "
                          "placement's heldOut fold (%d folds)" % n, "ok": ok_all, "mismatches": detail})
    return {"allOk": all(r["ok"] for r in rows), "rows": rows}


# =========================================================================== markdown

def f3(x, d=3):
    return DASH if x is None else ("%.*f" % (d, x))


def fb(b):
    return "inf" if b == INF else ("%.4g" % b)


def fbh(b):
    """A budget as text with its unit: `0` and `inf` carry none."""
    return fb(b) if b in (0, INF) else fb(b) + "/h"


def md_table(res, group, title):
    lines = ["**%s**" % title, "",
             "| budget /h | grid label | declared point | set size | charged /h | partial | strict | median penalised s | g s |",
             "|---|---|---|---|---|---|---|---|---|"]
    for p in res["points"]:
        g = p["groups"][group]
        size = p.get("size") if "size" in p else "%.2f" % p["sizeMean"]
        charged = p.get("charged") if "charged" in p else p["chargedMean"]
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            fb(p["budget"]), p["label"], ", ".join(p["names"]) or "", size, f3(charged, 2),
            f3(g["partial"]), f3(g["strict"]), f3(g["medianPenalised"], 2), f3(g["g"], 3)))
    return lines


def where_reaches(res, group, field, target=1.0):
    for p in res["points"]:
        v = p["groups"][group][field]
        if v is not None and v >= target - 1e-12:
            return p
    return None


def first_gain_and_knee(res, group, share=0.9):
    """(first grid budget with g > 0, first grid budget with g >= share x the grid's largest g); None where g never rises.
    Grid resolution only: the true step is somewhere between a budget and the one before it."""
    gs = [(p["budget"], p["groups"][group]["g"]) for p in res["points"] if p["groups"][group]["g"] is not None]
    top = max((g for _, g in gs), default=None)
    if top is None or top <= 1e-12:
        return None, None, top
    first = next(b for b, g in gs if g > 1e-12)
    knee = next(b for b, g in gs if g >= share * top)
    return first, knee, top


def write_markdown(curves, path):
    L = ["# Sensitivity curves: detection versus false-alarm budget (2026-10-14)", "",
         "**%s.** Scope of every number: **instance** (one SUT, one host, one rate, one readout pair per system; test episodes: "
         "OTel E 6 (4 off-path, 2 on-path), TeaStore C 6 per rate, Hotel 12 per rate). Produced by "
         "`research/lanes/sensitivity_curves.py` from the committed readouts; nothing here is a pass rule and no frozen file was "
         "edited. Unknown is `—`, never 0." % POST_HOC, "",
         "## Definition", "",
         "- **x**: false-alarm budget per hour, the knapsack budget B of decision 76. `0` = the ledger alone (plus any cost-0 "
         "sensor); then m x 3/T_r for m in 0.5, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64 (T_r = the rate's training no-fault "
         "hours; the unit is the frozen named 3/T_r = 3.0/T_r, not the exact zero-alarm bound 2.9957/T_r, so the points m = 1 and "
         "m = 2 are exactly the declared 3/T_r and 6/T_r); then 6, 20, 60, 200, 600, 2000 per hour; then `inf`. Budgets tied "
         "within 1e-9 merge. Declared points: 0, 3/T_r, 6/T_r, 6/h, inf (6/T_r is a v3.2 name; the grid carries it for every system).",
         "- **set**: the CELF frontier set (effort<=any, runtime<=any) solved on the TRAINING readout at that budget with the frozen "
         "`celf_v3.solve` (OTel E: over the candidates that pass decision 112's recurrence rule, as `celf_v3_2.frontier_rate`; "
         "TeaStore and Hotel: `celf_v3`'s primary arm, which has neither tiers nor the recurrence rule). Two prices: **decision 73** "
         "as frozen, and the **post hoc zero-alarm** price (`posthoc_lanes_v33.zero_alarm_costs`: an appear-only id evaluated in "
         "0 folds costs 2.9957/T_r instead of the rate's largest evidenced bound).",
         "- **test episodes**: OTel E, the scoring readout's held-out blocks 4-5 (frozen sets scored as frozen); TeaStore, campaign C "
         "(campaignIndex 5 of the C readout) with the set solved on the training readout; **Hotel has no held-out campaign, so "
         "the curve is leave-one-block-out on its training readout** (celf_v3's fold key (harness, block); each block scored with the "
         "set solved on the other three blocks, the 12 held-out episodes pooled). A set member absent from the scoring readout's "
         "ground set never fires.",
         "- **partial**: share of test episodes detected (a counted fire of the ledger or of a set member within the hold). "
         "**strict**: share of fault classes in which every test episode is detected. **median penalised s**: median over test "
         "episodes of the time to detection, a miss charged the hold (~60 s). **g**: D(ledger alone) - D(set), the frozen "
         "class-weighted mean penalised time, weights recomputed on the group's episodes (as the frozen scorer does).",
         "- **groups**: OTel E is split into `offpath` (fraud and accounting pauses, 2 + 2 episodes) and `onpath` (frontend pause, 2 "
         "episodes); TeaStore and Hotel use `all` classes. With 2 classes strict takes the values 0, 0.5, 1; with 1 class 0 or 1.",
         "- **comparators** are drawn at their charged price: `full` (the training ground set), `out of the box` (E: every "
         "ground-set sensor of effort tier 0; there is no effort file for TeaStore or Hotel, so there the declared postures `none` "
         "and `selected` stand in, restriction estimates of decision 78 and not the shipped system).",
         "- **plotted rate**: OTel E has one rate (25 req/s). TeaStore and Hotel have four; the figure shows r0.2 (an engineering "
         "default: the rate decision 89 used; not a preregistered choice). All four rates are in `curves.json` and below.", ""]
    ck = curves["crossChecks"]
    L += ["## Cross-checks", "",
          "All %d checks %s." % (len(ck["rows"]), "PASS" if ck["allOk"] else "DID NOT ALL PASS (see rows)"), "",
          "| check | ok |", "|---|---|"]
    for r in ck["rows"]:
        L.append("| %s | %s |" % (r["check"], "PASS" if r["ok"] else "FAIL"))
    L.append("")
    for name, sysd in curves["systems"].items():
        L += ["## %s" % sysd["label"], ""]
        for rk, byp in sysd["rates"].items():
            for pricing in ("decision73", "zeroAlarm"):
                res = byp[pricing]
                if "points" not in res:
                    L += ["rate %s, %s: %s" % (rk, pricing, res.get("note")), ""]
                    continue
                if float(rk) != sysd["plotRate"]:
                    # compact for the other rates: where each curve reaches 1 and the ledger value
                    g0 = res["points"][0]["groups"]["all"] if "all" in res["points"][0]["groups"] else None
                    p1 = where_reaches(res, "all", "partial")
                    s1 = where_reaches(res, "all", "strict")
                    L.append("- rate %s, %s (T_r = %.3g h): partial at budget 0 = %s, reaches 1 at %s; strict at 0 = %s, reaches 1 at %s; "
                             "g at inf = %s" % (rk, pricing, res["hours"], f3(g0["partial"]),
                                                fbh(p1["budget"]) if p1 else DASH, f3(g0["strict"]),
                                                fbh(s1["budget"]) if s1 else DASH,
                                                f3(res["points"][-1]["groups"]["all"]["g"])))
                    continue
                for group in sysd_groups(name):
                    L += md_table(res, group, "rate %s, %s pricing, group `%s` (T_r = %.3g h; %d test episodes in the group)" % (
                        rk, pricing, group, res["hours"], res["points"][0]["groups"][group]["episodes"]))
                    L.append("")
                L.append("Comparators (%s pricing, rate %s):" % (pricing, rk))
                L.append("")
                L += ["| comparator | members (in training ground set) | charged /h | " + " | ".join(
                    "%s partial / strict / g" % g for g in sysd_groups(name)) + " |", "|---|---|---|" + "---|" * len(sysd_groups(name))]
                for lab, c in res["comparators"].items():
                    L.append("| %s | %d (%d) | %s | %s |" % (lab, c["members"], c["membersInTrainingGroundSet"], f3(c["charged"], 1),
                                                         " | ".join("%s / %s / %s" % (f3(c["groups"][g]["partial"]),
                                                                                    f3(c["groups"][g]["strict"]),
                                                                                    f3(c["groups"][g]["g"])) for g in sysd_groups(name))))
                L.append("")
            if float(rk) == sysd["plotRate"]:
                pass
        L.append("")
    L += ["## Reading (grid values, post hoc)", "", curves["reading"], "", "## Caveats and what could not be computed", ""]
    L += ["- " + c for c in curves["caveats"]] + [""]
    Path(path).write_text("\n".join(L), encoding="utf-8")


def sysd_groups(name):
    return tuple(SYSTEMS[name]["groups"])


def sets_differ(a, b):
    """Do two pricings give a different set (or fold sets) at any grid budget?"""
    key = lambda p: json.dumps(p.get("set") if "set" in p else p.get("foldSets"), sort_keys=True)
    return [x["label"] for x, y in zip(a["points"], b["points"]) if key(x) != key(y)]


def dips(curves):
    """Every (system, rate, pricing, group, field) where a larger budget gives a LOWER value (greedy sets are not nested)."""
    out = []
    for name, sysd in curves["systems"].items():
        for rk, byp in sysd["rates"].items():
            for pricing, res in byp.items():
                for group in sysd_groups(name):
                    for field in ("partial", "strict", "g"):
                        v = [p["groups"][group][field] for p in res["points"]]
                        if any(b < a - 1e-9 for a, b in zip(v, v[1:])):
                            out.append("%s r%s %s %s %s" % (name, rk, pricing, group, field))
    return out


def never_full(curves):
    """(system, rate) whose decision-73 `all`/`offpath` partial curve never reaches 1 on the grid."""
    out = []
    for name, sysd in curves["systems"].items():
        for rk, byp in sysd["rates"].items():
            grp = "offpath" if name == "otel-e" else "all"
            top = max(p["groups"][grp]["partial"] for p in byp["decision73"]["points"])
            if top < 1 - 1e-12:
                out.append("%s r%s (maximum %.3f)" % (name, rk, top))
    return out


def ledger_full(curves):
    """TeaStore rates at which the ledger alone detects every episode."""
    return [rk for rk, byp in curves["systems"]["teastore"]["rates"].items()
            if byp["decision73"]["points"][0]["groups"]["all"]["partial"] == 1.0]


def caveats(curves):
    c = ["**x is a charged budget, not a measured false-alarm rate.** The price of a set is the sum of its members' training upper "
         "bounds (decision 73 or the zero-alarm row); the frozen sets' fresh false alarms on the test no-fault cells have no "
         "validated path (decision 88 analogue), so no curve here has a realised false-alarm axis.",
         "**Granularity.** Test episodes: OTel E off-path 4 (strict takes 0, 0.5, 1 over 2 classes), on-path 2; TeaStore C 6 per "
         "rate; Hotel 12 per rate (3 classes x 4 blocks, strict takes multiples of 1/3). `reaches 1 at` and the knee are grid "
         "values: the true step lies between that budget and the one before it. Greedy sets are not nested in the budget, so the "
         "curves are not forced monotone; curves that dip (a larger budget, a lower value): %s." % (", ".join(dips(curves)) or "none"),
         "**TeaStore.** The ledger alone detects every campaign-C episode at rates %s (of 0.05, 0.2, 1, 10), so there partial and "
         "strict are 1 at every budget and only the penalised time and g move." % (", ".join(ledger_full(curves)) or "none"),
         "**Hotel is leave-one-block-out, not a held-out campaign.** Each fold's set is solved on the other three blocks with the "
         "price table of the full readout (the same as the frozen `celf_v3.held_out`), so prices are in-sample for the fold; the 12 "
         "held-out episodes are pooled. The fixed comparators are scored on all 12 episodes (they have no fold).",
         "**Comparators.** `out of the box` exists for OTel E only (the effort file `otel.effort.json`); TeaStore and Hotel have no "
         "effort file, so the declared postures `none` and `selected` (restriction estimates, decision 78) stand in and are not "
         "the shipped system. Hotel `sample-zero` is in the JSON and the table, not drawn.",
         "**Zero-alarm price.** It reprices only ids the reader flags (appearOnly, foldsEvaluated 0, no honest bound): E %d, "
         "TeaStore r0.2 %d, Hotel r0.2 %d ids. For TeaStore and Hotel the sets differ between the two prices at: TeaStore %s; "
         "Hotel %s (grid labels, rate 0.2)." % (
             curves["systems"]["otel-e"]["rates"]["25"]["zeroAlarm"]["zeroAlarmRepricedIds"],
             curves["systems"]["teastore"]["rates"]["0.2"]["zeroAlarm"]["zeroAlarmRepricedIds"],
             curves["systems"]["hotel"]["rates"]["0.2"]["zeroAlarm"]["zeroAlarmRepricedIds"],
             sets_differ(curves["systems"]["teastore"]["rates"]["0.2"]["decision73"],
                         curves["systems"]["teastore"]["rates"]["0.2"]["zeroAlarm"]) or "no budget",
             sets_differ(curves["systems"]["hotel"]["rates"]["0.2"]["decision73"],
                         curves["systems"]["hotel"]["rates"]["0.2"]["zeroAlarm"]) or "no budget"),
         "**Other rates.** TeaStore and Hotel have rates 0.05, 0.2, 1, 10 req/s; only r0.2 is drawn (engineering default). The "
         "others are in `curves.json` and summarised in one line each above. OTel E has one rate. Rates where the partial curve "
         "(decision-73 price; E off-path, others all classes) never reaches 1 on the grid: %s; no mechanism is claimed." % (
             ", ".join(never_full(curves)) or "none")]
    return c


def reading(curves):
    lines = []
    for name, sysd in curves["systems"].items():
        rk = "%g" % sysd["plotRate"]
        for pricing in ("decision73", "zeroAlarm"):
            res = sysd["rates"][rk][pricing]
            for group in sysd_groups(name):
                p0 = res["points"][0]["groups"][group]
                p1 = where_reaches(res, group, "partial")
                s1 = where_reaches(res, group, "strict")
                first, knee, gmax = first_gain_and_knee(res, group)
                lines.append("- %s, %s, `%s` (rate %s, %d episodes): ledger alone partial %s, strict %s; partial reaches 1 at %s, "
                             "strict at %s; g first above 0 at %s, reaches 90%% of its grid maximum (%s s) at %s." % (
                                 name, pricing, group, rk, p0["episodes"], f3(p0["partial"]), f3(p0["strict"]),
                                 fbh(p1["budget"]) if p1 else "never on this grid",
                                 fbh(s1["budget"]) if s1 else "never on this grid", fbh(first) if first is not None else "never (g = 0 at every grid budget)",
                                 f3(gmax, 2), fbh(knee) if knee is not None else DASH))
    return "\n".join(lines)


# =========================================================================== figure

def make_figure(curves, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    plt.rcParams.update({"font.size": 6.5, "axes.linewidth": 0.5, "lines.linewidth": 0.9, "pdf.fonttype": 42,
                         "xtick.major.width": 0.5, "ytick.major.width": 0.5, "xtick.major.size": 2.2, "ytick.major.size": 2.2})
    panels = []
    for name in ("otel-e", "teastore", "hotel"):
        s = curves["systems"][name]
        rk = "%g" % s["plotRate"]
        short = {"otel-e": "OTel E (25 req/s, test blocks 4-5)", "teastore": "TeaStore (r0.2, campaign C)",
                 "hotel": "Hotel (r0.2, leave-one-block-out)"}[name]
        for group in sysd_groups(name):
            if name == "otel-e" and group == "all":
                continue
            title = short + ({"offpath": ", off-path", "onpath": ", on-path"}.get(group, ""))
            panels.append((name, rk, group, title))

    def xpos(res_all):
        fin = [p["budget"] for res in res_all for p in res["points"] if 0 < p["budget"] < INF]
        comp = [c["charged"] for res in res_all for c in res["comparators"].values() if c["charged"] and c["charged"] > 0]
        lo, hi = min(fin) / 2.5, max(fin + comp) * 2.5
        return lo, hi

    def pos(b, lo, hi):
        return lo if b == 0 else (hi if b == INF else b)

    def draw(page_field, ylabel, fname):
        fig, axes = plt.subplots(2, 2, figsize=(6.2, 4.9))
        for ax, (name, rk, group, title) in zip(axes.flat, panels):
            byp = curves["systems"][name]["rates"][rk]
            lo, hi = xpos([byp["decision73"], byp["zeroAlarm"]])
            styles = {"zeroAlarm": ("0.6", "s", "zero-alarm price"), "decision73": ("black", "o", "decision 73")}
            for pricing, (col, mk, lab) in styles.items():       # gray first, thick, so equal black curves stay visible on top
                lw = 1.8 if pricing == "zeroAlarm" else 0.9
                res = byp[pricing]
                xs = [pos(p["budget"], lo, hi) for p in res["points"]]
                if page_field == "frac":
                    for field, ls, fill, nm in (("partial", "-", True, "partial"), ("strict", "--", False, "strict")):
                        ys = [p["groups"][group][field] for p in res["points"]]
                        ax.step(xs, ys, where="post", color=col, linestyle=ls, linewidth=lw, zorder=2)
                        dx = [x for x, p in zip(xs, res["points"]) if p["names"]]
                        dy = [y for y, p in zip(ys, res["points"]) if p["names"]]
                        ax.plot(dx, dy, linestyle="none", marker=mk, markersize=3.2, markerfacecolor=col if fill else "white",
                                markeredgecolor=col, markeredgewidth=0.6, zorder=3)
                else:
                    ys = [p["groups"][group]["medianPenalised"] for p in res["points"]]
                    ax.step(xs, ys, where="post", color=col, linestyle="-", linewidth=lw)
                    gs = [p["groups"][group]["g"] for p in res["points"]]
                    ax.step(xs, gs, where="post", color=col, linestyle=":", linewidth=lw + 0.2)
                    dx = [x for x, p in zip(xs, res["points"]) if p["names"]]
                    dy = [y for y, p in zip(ys, res["points"]) if p["names"]]
                    ax.plot(dx, dy, linestyle="none", marker=mk, markersize=3.2, markerfacecolor=col, markeredgecolor=col,
                            zorder=3)
            # comparators at their charged price (decision-73 price in black, zero-alarm price in gray when it differs)
            cm = {"full": "D", "out of the box": "^", "posture none": "v", "posture selected": "p"}
            for pricing, (col, mk, lab) in styles.items():
                for cl, c in byp[pricing]["comparators"].items():
                    if cl == "ledger alone" or cl not in cm or not c["charged"]:
                        continue
                    if pricing == "zeroAlarm" and abs(c["charged"] - byp["decision73"]["comparators"][cl]["charged"]) < 1e-9:
                        continue
                    g = c["groups"][group]
                    if page_field == "frac":
                        ax.plot([c["charged"]], [g["partial"]], marker=cm[cl], markersize=3.6, color=col, markerfacecolor=col,
                                linestyle="none", zorder=4)
                        ax.plot([c["charged"]], [g["strict"]], marker=cm[cl], markersize=3.6, color=col, markerfacecolor="white",
                                linestyle="none", zorder=4)
                    else:
                        ax.plot([c["charged"]], [g["medianPenalised"]], marker=cm[cl], markersize=3.6, color=col,
                                linestyle="none", zorder=4)
            ax.set_xscale("log")
            ax.set_xlim(lo / 1.3, hi * 1.3)
            decs = [10 ** k for k in range(int(math.floor(math.log10(lo))), int(math.ceil(math.log10(hi))) + 1)
                    if 0.4 < math.log10(10 ** k / lo) and 0.4 < math.log10(hi / 10 ** k)]
            ax.set_xticks(decs + [lo, hi])
            ax.set_xticklabels(["$10^{%d}$" % round(math.log10(d)) for d in decs] + ["0", "$\\infty$"])
            ax.minorticks_off()
            if page_field == "frac":
                ax.set_ylim(-0.04, 1.06)
                ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
            ax.set_title(title, fontsize=6.3, pad=22)
            ax.grid(axis="y", linewidth=0.3, color="0.85")
            # declared points: top axis, labels merged where they collide (within 0.15 decade)
            pts = byp["decision73"]["points"]
            dec_pts = sorted((pos(p["budget"], lo, hi), n) for p in pts for n in p["names"])
            merged = []
            for x, n in dec_pts:
                if merged and abs(math.log10(x) - math.log10(merged[-1][0])) < 0.15:
                    merged[-1][1].append(n)
                else:
                    merged.append([x, [n]])
            top = ax.secondary_xaxis("top")
            top.set_xscale("log")
            top.set_xticks([m[0] for m in merged])
            top.set_xticklabels([",".join(m[1]) for m in merged], rotation=90, fontsize=4.8)
            top.minorticks_off()
            top.tick_params(which="both", length=2, width=0.4, pad=1)
            for m in merged:
                ax.axvline(m[0], color="0.8", linewidth=0.4, linestyle=(0, (1, 2)), zorder=0)
        for ax in axes[1]:
            ax.set_xlabel("false-alarm budget per hour (0 = ledger alone)", fontsize=6)
        for ax in axes[:, 0]:
            ax.set_ylabel(ylabel, fontsize=6)
        from matplotlib.lines import Line2D
        if page_field == "frac":
            h = [Line2D([], [], color="black", linestyle="-"), Line2D([], [], color="black", linestyle="--"),
                 Line2D([], [], color="0.6", linestyle="-", linewidth=1.8), Line2D([], [], color="0.6", linestyle="--", linewidth=1.8)]
            l = ["partial, decision-73 price", "strict, decision-73 price", "partial, zero-alarm price", "strict, zero-alarm price"]
        else:
            h = [Line2D([], [], color="black", linestyle="-"), Line2D([], [], color="black", linestyle=":", linewidth=1.1),
                 Line2D([], [], color="0.6", linestyle="-", linewidth=1.8), Line2D([], [], color="0.6", linestyle=":", linewidth=2.0)]
            l = ["median penalised, decision-73 price", "g, decision-73 price", "median penalised, zero-alarm price",
                 "g, zero-alarm price"]
        for mk, nm in (("D", "full"), ("^", "out of the box (E)"), ("v", "posture none"), ("p", "posture selected")):
            h.append(Line2D([], [], color="black", marker=mk, markersize=3.6, linestyle="none"))
            l.append(nm + " (charged price)")
        fig.legend(h, l, loc="lower center", ncol=3, fontsize=5.4, frameon=False, bbox_to_anchor=(0.5, -0.005),
                   handlelength=2.4, columnspacing=1.0)
        fig.tight_layout(rect=(0, 0.095, 1, 1), h_pad=1.6, w_pad=0.8)
        return fig

    with PdfPages(path, metadata={"Title": "Sensitivity curves (post hoc)", "CreationDate": None}) as pdf:
        f1 = draw("frac", "share of test episodes / classes", "frac")
        pdf.savefig(f1)
        f2 = draw("seconds", "seconds (penalised at the hold)", "sec")
        pdf.savefig(f2)
    import matplotlib.pyplot as plt2
    plt2.close("all")


CAPTION = ("Detection versus false-alarm budget (post hoc, instance scope). x: budget per hour, log axis; 0 = ledger alone, right "
           "edge = unbounded. Solid: share of test episodes detected (partial); dashed: share of fault classes with every test "
           "episode detected (strict). Black circles: decision-73 price; gray squares: post hoc zero-alarm price; markers sit on "
           "the declared budgets 0, 3/T_r, 6/T_r, 6/h, inf (top axis). Diamond: full, triangle: out of the box (E) or posture none / "
           "selected (TeaStore, Hotel), at their charged price; filled = partial, open = strict. Sets are solved on the training "
           "readout; test = held-out blocks 4-5 (E), campaign C (TeaStore), leave-one-block-out (Hotel). n = 2 to 12 test episodes.")


# =========================================================================== main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="NEW output directory (refused if it exists)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists():
        refuse("to write into an existing path: %s" % out)
    curves = run_all()
    curves["reading"] = reading(curves)
    curves["caveats"] = caveats(curves)
    curves["caption"] = CAPTION
    curves["switches"] = {k: globals()[k] for k in SWITCHES}
    curves["grid"] = {"multiplesOf3OverTr": list(MULTIPLES), "fixedPerHour": list(FIXED_PER_HOUR), "declared": list(DECLARED)}
    curves["script"] = {"path": "research/lanes/sensitivity_curves.py", "sha256": sha256(__file__), "python": sys.version}
    out.mkdir(parents=True)
    (out / "curves.json").write_text(json.dumps(_clean(curves), indent=1, sort_keys=True, allow_nan=False), encoding="utf-8")
    write_markdown(curves, out / "CURVES.md")
    make_figure(curves, out / "fig_sensitivity.pdf")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
