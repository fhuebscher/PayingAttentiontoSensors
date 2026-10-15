"""R4 price-check wrapper (research/placement/test-f-nofault/price_check.py): planted defects on synthetic readouts."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research" / "placement" / "test-f-nofault"))
import price_check as pc  # noqa: E402

LAG, LED = "metric:kafka:kafka.consumer_group.lag", "ledger:frontendproxy:index"


def _cal(lag_price=15.81):
    rules = {"%s/%s" % (LAG, r): {"honestUpperPerHour": 9.99} for r in ("spike", "run3", "median")}
    rules.update({"%s/%s" % (LED, r): {"honestUpperPerHour": 9.99} for r in ("spike", "run3", "median", "absent")})
    sensors = {LAG: {"placeable": True, "calibrated": ["spike", "run3", "median"], "honestUpperPerHour": lag_price},
               LED: {"placeable": True, "calibrated": ["spike", "run3", "median", "absent"], "honestUpperPerHour": None}}
    return {"primary": {"perRate": {"25": {"sensors": sensors, "rules": rules}}}}


def _J(cal, lag_alarms=0, led_rule_alarms=4):
    ra = {"%s/median" % LED: led_rule_alarms}
    if lag_alarms:
        ra["%s/spike" % LAG] = lag_alarms
    sa = {LAG: lag_alarms} if lag_alarms else {}
    return {"calibration": cal, "validation": {"perRate": {"25": {"cells": pc.CELLS, "hours": 0.5, "rulesAlarming": ra,
                                                                 "sensorsAlarming": sa}}}}


def _entry(tmp_path, cal, sensor=LAG, rules=("spike", "run3", "median")):
    tr = tmp_path / "train.json"
    tr.write_text(json.dumps({"calibration": cal}))
    pc.REPO = Path("/")  # entries carry absolute paths in these tests
    return {"label": "x", "sensor": sensor, "rules": list(rules), "calibrationCampaign": "c", "trainingReadout": str(tr)}


def test_refit_calibration_is_refused(tmp_path):            # planted defect: the readout's calibration differs from training
    e = _entry(tmp_path, _cal(15.81))
    with pytest.raises(SystemExit, match="not byte-equal"):
        pc.rows_for(e, _J(_cal(9.99)))


def test_ledger_union_is_dash_not_zero(tmp_path):
    cal = _cal()
    e = _entry(tmp_path, cal, sensor="ledger:frontendproxy:*", rules=("spike", "run3", "median", "absent"))
    rows = pc.rows_for(e, _J(cal))
    union = [r for r in rows if r["rule"] == "union"]
    assert union and all(r["alarms"] is None and r["verdict"] == "—" for r in union)
    assert [r["alarms"] for r in rows if r["rule"] == "median"] == [4]


def test_verdicts(tmp_path):
    cal = _cal(15.81)
    e = _entry(tmp_path, cal)
    v = lambda k: [r for r in pc.rows_for(e, _J(cal, lag_alarms=k)) if r["rule"] == "union"][0]["verdict"]
    assert v(0) == "bounded below the price"          # upper 5.99 < 15.81
    assert v(4) == "consistent, not bounded"          # lower 2.73, upper 18.31
    assert v(14) == "contradicted"                    # lower > 15.81


def test_wrong_cell_count_is_refused(tmp_path):
    cal = _cal()
    J = _J(cal)
    J["validation"]["perRate"]["25"]["cells"] = 4
    with pytest.raises(SystemExit, match="expected"):
        pc.rows_for(_entry(tmp_path, cal), J)


def test_lower_bound():
    assert pc.lower95(0, 0.5) == 0.0
    assert abs(pc.lower95(1, 0.5) - 0.10259) < 1e-3 and abs(pc.lower95(3, 1.0) - 0.8177) < 1e-3


def test_absent_stream_is_dash_not_zero(tmp_path):          # planted defect: a metric with no samples in one cell must not read as silent
    cal = _cal(15.81)
    e = _entry(tmp_path, cal)
    present = {LAG: {"c1": 120, "c2": 0}}
    rows = pc.rows_for(e, _J(cal), present)
    assert rows and all(r["alarms"] is None and r["verdict"] == "—" and r["absentFrom"] == ["c2"] for r in rows)
    assert [r for r in pc.rows_for(e, _J(cal), {LAG: {"c1": 1, "c2": 1}}) if r["rule"] == "union"][0]["verdict"] == "bounded below the price"


def test_raw_samples_zero_when_metric_never_appears(tmp_path):
    (tmp_path / "otelcol.log").write_text("otelcol-1  | ResourceMetrics #0\n")
    assert pc.raw_samples(tmp_path, LAG) == 0


def test_attempts_are_r4_and_its_relaunch():
    assert pc.ATTEMPTS == (6, 7)
    with pytest.raises(SystemExit, match="not R4's"):
        pc.main(["--campaign", "x", "--out", "/nonexistent-r4-out", "--attempt", "5"])
