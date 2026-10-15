"""POST HOC fresh false-alarm check of campaign F's frozen sets (research/placement/test-f/fresh-fa/fresh_fa_f.py).

Layer: script helpers on synthetic readout dicts, plus (skipped when the gitignored F evidence is absent) the farm builder on the real
held-out cells and the committed output. Planted defects, each seen failing: a farm that also holds a training no-fault cell
(`check_farm`), a substring key match that mixes `consumer_group.lag` with `consumer_group.lag_sum` (`rule_count`), and a bound
computed on the wrong hours (`summarise`).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FA = ROOT / "research/placement/test-f/fresh-fa"
spec = importlib.util.spec_from_file_location("fresh_fa_f", FA / "fresh_fa_f.py")
fa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fa)

LAG, REQ = fa.SETS["@6/T_r"], fa.SETS["@3/T_r"]


def synthetic(alarming, sensors_alarming, hours=0.2):
    rules = {}
    for sid in (LAG, REQ):
        for rule in fa.RULES:
            rules["%s/%s" % (sid, rule)] = {"value": "K 5", "honest": 0, "honestUpperPerHour": 9.99}
    cal = {"sensors": {sid: {"placeable": True, "calibrated": list(fa.RULES), "honest": 0, "honestUpperPerHour": 9.99}
                       for sid in (LAG, REQ)}, "rules": rules}
    return {"validation": {"perRate": {fa.RATE: {"hours": hours, "cells": 4, "rulesCalibrated": 6, "rulesAlarming": alarming,
                                                 "sensorsAlarming": sensors_alarming}}},
            "calibration": {"primary": {"perRate": {fa.RATE: cal}}}}


def row(rows, sid, rule):
    return next(r for r in rows if r["sensor"] == sid and r["rule"] == rule)


def test_summarise_counts_rates_and_the_readers_bound():
    J = synthetic({REQ + "/spike": 2, LAG + "_sum/spike": 3}, {REQ: 2, LAG + "_sum": 3})
    rows, meta = fa.summarise(J)
    assert meta == {"cells": 4, "hours": 0.2, "rulesCalibrated": 6}
    r = row(rows, REQ, "spike")
    assert r["alarms"] == 2 and r["perHour"] == pytest.approx(10.0)
    assert r["upperPerHour"] == pytest.approx(fa.poisson_bound_text(2, 0.2))
    assert r["upperPerHour"] == pytest.approx(31.48, abs=0.01)
    assert row(rows, REQ, "union of the sensor's 3 rules")["alarms"] == 2
    z = row(rows, LAG, "spike")        # lag has no alarm of its own: the lag_sum alarms must not leak into it
    assert z["alarms"] == 0 and z["upperPerHour"] == pytest.approx(14.98, abs=0.01)
    assert row(rows, LAG, "union of the sensor's 3 rules")["alarms"] == 0


def test_planted_defect_substring_match_mixes_lag_and_lag_sum():
    alarming = {LAG + "_sum/spike": 3}

    def sloppy(rules_alarming, sid, rule):     # the defect: prefix/substring match
        return sum(v for k, v in rules_alarming.items() if k.startswith(sid) and k.endswith(rule))

    assert sloppy(alarming, LAG, "spike") == 3          # the defect is wrong ...
    assert fa.rule_count(alarming, LAG, "spike") == 0   # ... and the shipped matcher is right


def test_planted_defect_wrong_hours_changes_the_bound():
    J = synthetic({REQ + "/spike": 2}, {REQ: 2}, hours=0.3)   # 6 cells' hours instead of the 4 held-out cells' 0.2 h
    rows, _ = fa.summarise(J)
    assert row(rows, REQ, "spike")["upperPerHour"] != pytest.approx(31.48, abs=0.01)


def make_receipts(root, cells):
    for name, block in cells:
        d = root / "runs" / "calibration" / name
        d.mkdir(parents=True)
        (d / "receipt.json").write_text(json.dumps(
            {"state": "valid", "runKey": {"regime": "no-fault-calibration", "block": block}}))


HELD = [("r25-b04-16-full", 4), ("r25-b04-17-full", 4), ("r25-b05-21-full", 5), ("r25-b05-22-full", 5)]


def test_check_farm_accepts_exactly_the_four_held_out_cells(tmp_path):
    make_receipts(tmp_path, HELD)
    assert fa.check_farm(tmp_path) == sorted(n for n, _ in HELD)


def test_planted_defect_farm_with_a_training_cell_is_refused(tmp_path):
    make_receipts(tmp_path, HELD + [("r25-b01-01-full", 1)])
    with pytest.raises(AssertionError):
        fa.check_farm(tmp_path)


def test_planted_defect_farm_missing_a_cell_is_refused(tmp_path):
    make_receipts(tmp_path, HELD[:3])
    with pytest.raises(AssertionError):
        fa.check_farm(tmp_path)


@pytest.mark.skipif(not (fa.CAMPAIGN / "runs/calibration").is_dir(), reason="gitignored F evidence absent")
def test_real_farm_matches_the_held_out_cells(tmp_path):
    farm = fa.build_farm(tmp_path / "farm")
    assert fa.check_farm(farm) == sorted(fa.HELD_OUT_CELLS)


def test_committed_output_is_consistent():
    p = FA / "out/fresh_fa_f.json"
    if not p.is_file():
        pytest.skip("output not generated")
    d = json.loads(p.read_text())
    assert d["calibrationByteEqualToTrainingReadout"] is True
    assert d["farmCells"] == sorted(fa.HELD_OUT_CELLS) and d["meta"]["cells"] == 4
    again, _ = fa.summarise({"validation": d["validation"], "calibration": _cal_from_rows(d)})
    assert [(r["set"], r["rule"], r["alarms"]) for r in again] == [(r["set"], r["rule"], r["alarms"]) for r in d["rows"]]


def _cal_from_rows(d):
    rules, sensors = {}, {}
    for r in d["rows"]:
        if r["value"]:
            rules["%s/%s" % (r["sensor"], r["rule"])] = {"value": r["value"], "honest": r["trainHonest"],
                                                         "honestUpperPerHour": r["trainHonestUpperPerHour"]}
        else:
            sensors[r["sensor"]] = {"placeable": True, "calibrated": list(fa.RULES), "honest": r["trainHonest"],
                                    "honestUpperPerHour": r["trainHonestUpperPerHour"]}
    return {"primary": {"perRate": {fa.RATE: {"sensors": sensors, "rules": rules}}}}
