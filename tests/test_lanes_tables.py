"""research/lanes/lanes_tables.py: POST HOC exploratory lane tables (plan research/PLAN_LANES_20261014.md, O1-O5).

Layer: unit, SYNTHETIC readouts only (no cell, no readout file). Each check that guards a rule has a planted defect: the module switch
is flipped and the same assertion is shown to fail (`COUNTED_ONLY`, `STRICT_GAP`). The silence-sensor and price helpers are checked
against hand-derived values; `set_times` is checked against the placement's own `celf_v3.build_table` on a synthetic readout.
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "research" / "placement", ROOT / "research" / "detection-time", ROOT / "research"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
_spec = importlib.util.spec_from_file_location("lanes_tables", ROOT / "research" / "lanes" / "lanes_tables.py")
lt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lt)
import celf_v3 as cv  # noqa: E402


def fire(fam, sid, rule, ttd, own=False, counts=True, bc=(), on_path=False):
    return [fam, sid, rule, ttd, None, own, on_path, counts, list(bc), 0.0]


def sensor(family, honest, folds, placeable=True):
    return {"family": family, "placeable": placeable, "honestUpperPerHour": honest, "foldsEvaluated": folds,
            "calibrated": ["absent"], "unarmed": [], "dropped": [], "inert": [], "exempt": [], "appearOnly": False}


def synthetic_readout():
    """One rate (1), one class, three episodes. Own sensor `span:tgt:op` fires `absent` (BC-flagged, own); an UNCOUNTED own fire is
    earlier in episode 0 (counts False); `log:coord:aaa` is the coordinator id (evaluated in 0 folds)."""
    sens = {"span:tgt:op": sensor("T", None, 0), "log:coord:aaa": sensor("L", None, 0), "log:other:bbb": sensor("L", 5.0, 3),
            "ledger:fe:r": dict(sensor("E", 1.0, 3))}
    eps = []
    for i, (own_t, coord_t, ledger_t) in enumerate([(1.0, 44.0, None), (1.5, 43.5, 20.0), (None, 44.5, None)]):
        fires = []
        if i == 0:
            fires.append(fire("T", "span:tgt:op", "absent", 0.2, own=True, counts=False, bc=["BC-downstream-absent"]))
        if own_t is not None:
            fires.append(fire("T", "span:tgt:op", "absent", own_t, own=True, bc=["BC-downstream-absent"]))
        fires.append(fire("L", "log:coord:aaa", "appear", coord_t))
        if ledger_t is not None:
            fires.append(fire("E", "ledger:fe:r", "spike", ledger_t))
        eps.append({"regime": "tgt-pause-effect", "rate": 1.0, "block": i + 1, "campaignIndex": 0, "harness": "sweep",
                    "holdSeconds": 60.0, "target": "tgt", "cell": "c%d" % i, "fires": sorted(fires, key=lambda f: f[3])})
    return {"episodes": eps, "calibration": {"primary": {"perRate": {"1": {"hours": 0.15, "sensors": sens}}}}}


# ---------------------------------------------------------------------------- the planted-defect check (lane-1 counting)

def test_lane1_counts_only_counted_fires_and_defect_is_seen():
    J = synthetic_readout()
    rows = lt.lane1_rows(J, "syn")
    assert len(rows) == 1
    r = rows[0]
    assert (r["episodes"], r["detected"]) == (3, 2)             # episode 2 has no own fire
    assert r["ttds"] == [1.0, 1.5, None]                         # the earlier, uncounted 0.2 s fire is not used
    assert r["min"] == 1.0 and r["max"] == 1.5 and r["median"] == 1.25
    ch = r["cheapest"]
    assert ch["id"] == "span:tgt:op" and ch["coverage"] == 2 and ch["honest"] is None
    # planted defect: the `counts` flag is not consulted -> the 0.2 s uncounted fire becomes the detection time
    lt.COUNTED_ONLY = False
    try:
        bad = lt.lane1_rows(J, "syn")[0]
        assert bad["ttds"][0] == 0.2                              # the same assertion above (== 1.0) would fail
        assert bad["ttds"] != r["ttds"]
    finally:
        lt.COUNTED_ONLY = True
    assert lt.lane1_rows(J, "syn")[0]["ttds"] == [1.0, 1.5, None]


def test_silence_alarm_strictness_and_calibration():
    recs = [0.5, 1.0, 5.0]
    g = lt.build_gaps(recs, 0.0, 6.0)
    assert g == [(0.0, 0.5), (0.5, 0.5), (1.0, 4.0), (5.0, 1.0)]
    w = lt.calibrate_w([g])
    assert w == 4.0
    assert lt.alarm_times(g, w) == []                            # a calibration cell cannot alarm at its own maximum
    assert lt.alarm_times(g, 3.0) == [4.0]                       # alarm at last record + w
    lt.STRICT_GAP = False                                         # planted defect: >= instead of >
    try:
        assert lt.alarm_times(g, w) == [5.0]                      # the calibration cell now alarms: the check above fails
    finally:
        lt.STRICT_GAP = True
    # a service silent for the whole window has the window as its gap (virtual edges)
    assert lt.max_gap(lt.build_gaps([], 10.0, 190.0)) == 180.0
    assert lt.calibrate_w([[]]) is None


def test_prices_charge_fill_and_zero_alarm():
    J = synthetic_readout()
    pr = lt.Prices(J, 1.0)
    assert pr.fill == 5.0                                         # the largest evidenced bound over V_r
    i = pr.info("log:coord:aaa")
    assert i["honest"] is None and i["charged"] == 5.0
    assert i["zeroAlarm"] == pytest.approx(-math.log(0.05) / 0.15) and i["zeroAlarm"] == pytest.approx(19.9715, abs=1e-3)
    assert pr.info("log:other:bbb")["zeroAlarm"] == 5.0           # an evaluated sensor keeps its bound
    tot = pr.total(["log:coord:aaa", "log:other:bbb"])
    assert tot["charged"] == 10.0 and tot["unevaluated"] == 1
    assert lt.poisson_upper(0) == pytest.approx(2.995732, abs=1e-5)


def test_set_times_equals_celf_build_table():
    J = synthetic_readout()
    V = ["log:coord:aaa", "log:other:bbb"]
    table = cv.build_table(J, 1.0, V)                             # the placement's own table (e-only, exclude)
    mine = lt.set_times(J["episodes"], V)
    ref = [min(table.te[i], *(table.times[s][i] for s in V if s in table.times)) for i in range(3)]
    assert mine == ref == [44.0, 20.0, 44.5]
    # the own sensor is excluded in the scorer's reading and counted only in the lane reading
    assert lt.set_times(J["episodes"], ["span:tgt:op"]) == [math.inf, 20.0, math.inf]
    assert lt.set_times(J["episodes"], ["span:tgt:op"], "count-all", "only") == [1.0, 1.5, math.inf]


def test_lane2_select_by_service_and_template():
    texts = {("kafka", "a"): "[<n>] INFO [GroupCoordinator <n>]: Member x in group accountingservice has failed, removing it from the group (k)",
             ("kafka", "b"): "[<n>] INFO [GroupCoordinator <n>]: Group accountingservice with generation <n> is now empty (k)",
             ("kafka", "c"): "[<n>] INFO [GroupCoordinator <n>]: Stabilized group accountingservice generation <n>",
             ("kafka", "f"): "[<n>] INFO [GroupCoordinator <n>]: Preparing to rebalance group x in state PreparingRebalance with old generation <n> (reason: remo",
             ("kafka", "g"): "[<n>] INFO [GroupCoordinator <n>]: Preparing to rebalance group x in state PreparingRebalance with old generation <n> (reason: Adding n",
             ("registry", "d"): "WARN Removed tools.auth@auth:8080 since it failed the heartbeat!",
             ("webui", "e"): "since it failed the heartbeat"}
    o = lt.lane2_select(texts, "otel")
    assert {k: v["lane2"] for k, v in o.items()} == {("kafka", "a"): True, ("kafka", "b"): True, ("kafka", "c"): False,
                                                       ("kafka", "f"): True, ("kafka", "g"): False}
    assert o[("kafka", "a")]["group"] == "accountingservice"
    t = lt.lane2_select(texts, "teastore")
    assert list(t) == [("registry", "d")]
