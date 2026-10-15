"""research/lanes/sensitivity_curves.py: POST HOC sensitivity curves (detection versus false-alarm budget).

Layers, stated per test:
  * REAL (committed readouts, ~6 s): the curve at E's declared budgets reproduces research/placement/test-e/otel-e.json (g and detected
    episodes of the frozen frontier any/any), the zero-alarm row reproduces the post hoc lanes result (6/T_r: g 5.292, 5 of 6 detected),
    TeaStore reproduces teastore-c.json at the named budgets, Hotel's fold sets equal the frozen heldOut folds.
  * SYNTHETIC: the strict rule (every episode of a class) and the budget grid, on hand-built tables.
One planted defect: STRICT_EVERY_EPISODE flipped makes the synthetic strict assertion fail, so the check exists, ran, and was seen
failing on a planted defect.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "research" / "placement", ROOT / "research" / "detection-time", ROOT / "research" / "lanes"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
_spec = importlib.util.spec_from_file_location("sensitivity_curves", ROOT / "research" / "lanes" / "sensitivity_curves.py")
sc = importlib.util.module_from_spec(_spec)
sys.modules["sensitivity_curves"] = sc
_spec.loader.exec_module(sc)
cv = sc.cv

OTEL_E = ROOT / "research" / "placement" / "test-e" / "otel-e.json"
INF = float("inf")


@pytest.fixture(scope="module")
def curves():
    return sc.run_all()


def _frozen(lab):
    return json.loads(OTEL_E.read_text())["rates"]["25"]["sets"][lab]


# =========================================================================== REAL

def test_e_curve_reproduces_the_frozen_scoring_at_the_declared_budgets(curves):
    res = curves["systems"]["otel-e"]["rates"]["25"]["decision73"]
    for nm in sc.DECLARED:
        p = sc._point(res, nm)
        fz = _frozen("frontier (effort<=any, runtime<=any) @%s" % nm)
        a = p["groups"]["all"]
        assert a["g"] == pytest.approx(fz["g"], abs=1e-9)
        assert [a["detected"], a["episodes"]] == fz["detectedEpisodes"]


def test_e_zero_alarm_row_reproduces_the_posthoc_lanes_result(curves):
    z = sc._point(curves["systems"]["otel-e"]["rates"]["25"]["zeroAlarm"], "6/T_r")["groups"]["all"]
    assert z["g"] == pytest.approx(5.292, abs=5e-4) and [z["detected"], z["episodes"]] == [5, 6]
    d = sc._point(curves["systems"]["otel-e"]["rates"]["25"]["decision73"], "6/T_r")["groups"]["all"]
    assert d["g"] == pytest.approx(0.0, abs=1e-12) and [d["detected"], d["episodes"]] == [3, 6]


def test_all_builtin_cross_checks_pass(curves):
    bad = [r["check"] for r in curves["crossChecks"]["rows"] if not r["ok"]]
    assert bad == []
    assert len(curves["crossChecks"]["rows"]) == 16


def test_e_groups_split_offpath_from_onpath(curves):
    res = curves["systems"]["otel-e"]["rates"]["25"]["decision73"]
    p0 = res["points"][0]["groups"]
    assert (p0["offpath"]["episodes"], p0["onpath"]["episodes"], p0["all"]["episodes"]) == (4, 2, 6)
    assert p0["offpath"]["partial"] == 0.25 and p0["offpath"]["strict"] == 0.0     # ledger alone: fraud block 5 only
    assert p0["onpath"]["partial"] == 1.0 and p0["onpath"]["strict"] == 1.0


# =========================================================================== SYNTHETIC

def _table(per_episode):
    """per_episode: [(class, hold, ledger ttd or inf, {sensor: ttd})] -> a frozen celf_v3.Table."""
    eps = [{"regime": c, "holdSeconds": h, "rate": 1.0, "block": i, "fires": []} for i, (c, h, _, _) in enumerate(per_episode)]
    te = [t for _, _, t, _ in per_episode]
    sensors = sorted({s for _, _, _, d in per_episode for s in d})
    times = {s: [d.get(s, INF) for _, _, _, d in per_episode] for s in sensors}
    return cv.Table(eps, te, times)


def _metrics(table, S, classes=None):
    idx = list(range(len(table.episodes)))
    obj = cv.Objective(table, idx, "ttd")
    m, raw = sc.eval_set(table, obj, idx, S)
    return sc.group_metrics(table, idx, obj.pe, m, raw, classes)


def test_strict_needs_every_episode_of_a_class_and_the_planted_defect_is_seen():
    # class A: 2 episodes, the set catches one of them; class B: 1 episode, the ledger catches it
    t = _table([("A", 60.0, INF, {"s": 5.0}), ("A", 60.0, INF, {}), ("B", 60.0, 1.0, {})])
    m = _metrics(t, ["s"])
    assert m["partial"] == pytest.approx(2 / 3)
    assert m["strict"] == 0.5                                   # class B yes, class A no
    assert m["classes"] == {"A": {"detected": 1, "episodes": 2}, "B": {"detected": 1, "episodes": 1}}
    # penalised: A1 5, A2 60, B 1; class weights 1/2 each: g = D(ledger) - D(set), ledger penalised 60, 60, 1
    assert m["g"] == pytest.approx(0.5 * 0.5 * (60 - 5) + 0.0)
    assert m["medianPenalised"] == 5.0
    sc.STRICT_EVERY_EPISODE = False
    try:
        bad = _metrics(t, ["s"])
        assert bad["strict"] == 1.0 and bad["strict"] != 0.5        # the planted defect is visible: class A counted as detected
    finally:
        sc.STRICT_EVERY_EPISODE = True


def test_a_miss_is_charged_the_hold_and_a_late_fire_is_not_a_detection():
    t = _table([("A", 60.0, INF, {}), ("A", 60.0, INF, {"s": 70.0})])
    m = _metrics(t, ["s"])
    assert m["detected"] == 0 and m["partial"] == 0.0 and m["medianPenalised"] == 60.0 and m["g"] == 0.0


def test_grid_declares_the_frozen_named_budgets_exactly_and_merges_ties():
    import celf_v3_2 as c2
    hours = 0.15000000000000002
    grid = sc.budget_grid(hours)
    named = c2.named_budgets(hours)
    for nm in sc.DECLARED:
        pts = [g for g in grid if nm in g["names"]]
        assert len(pts) == 1
        assert pts[0]["value"] == named[nm] or (nm == "inf" and pts[0]["value"] == INF)
    vals = [g["value"] for g in grid]
    assert vals == sorted(vals) and vals[0] == 0.0 and vals[-1] == INF
    # 20/h and 3/T_r = 19.999999999999996/h are one point at T_r = 0.15 h; at T_r = 1.25 h they are two
    assert sum(1 for v in vals if 19.9 < v < 20.1) == 1
    assert sum(1 for g in sc.budget_grid(1.25) if 19 < g["value"] < 20.5) == 2          # 19.2 (8 x 3/T_r) and 20/h
