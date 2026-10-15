#!/usr/bin/env python3
"""POST HOC (2026-10-14, after RESULT_F.md): fresh false-alarm rate of campaign F's frozen sets on F's held-out no-fault cells.

Question: how often do the training-calibrated detectors of the frozen @6/T_r set {metric:kafka:kafka.consumer_group.lag} and the
@3/T_r set {metric:kafka:kafka.request.count} alarm on F's 4 held-out no-fault cells (blocks 4-5, regime no-fault-calibration)?

Path used: the READER'S OWN validation path (V3_VALIDATION_RULE, sweep_analysis_v3.validation(), `--validation`), by calling the frozen
v3.3 reader's main() unchanged. Nothing is re-implemented. Two arguments make it apply to cells of the same campaign:
  * `--blocks 1 2 3 4 5 --test-blocks 4 5 --split split_f_otel.json`: blocks 4-5 are held out of every fit and calibration
    (decision 102), so the calibration is the training one (checked below: byte-equal to the frozen training readout's `calibration`);
  * `--validation <farm>`: a directory of symlinks to ONLY the four held-out no-fault cells. Pointing --validation at the whole
    campaign would also count the 6 training no-fault cells as "fresh" (the validation fit excludes held-out cells only).
Scope: instance (one SUT, one host, one rate, 4 cells, 0.2 h). A bound is an upper bound, not an equivalence test.

    uv run python research/placement/test-f/fresh-fa/fresh_fa_f.py [--out research/placement/test-f/fresh-fa/out]
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
CAMPAIGN = REPO / "tmp/otel-f-evidence/f1-fetch/x"
TRAIN_READOUT = REPO / "research/traffic-sweep/readout-otel-f-train-v3.3/sweep_analysis_v3_3.json"
SPLIT = REPO / "research/protocol/split_f_otel.json"
PLACEMENT = REPO / "research/placement/test-f/placement-f.json"
FARM_DEFAULT = REPO / "tmp/fresh-fa-f/farm"
READOUT_DEFAULT = REPO / "tmp/fresh-fa-f/readout-v3.3-validation"
HELD_OUT_CELLS = ["r25-b04-16-full", "r25-b04-17-full", "r25-b05-21-full", "r25-b05-22-full"]
SETS = {"@6/T_r": "metric:kafka:kafka.consumer_group.lag", "@3/T_r": "metric:kafka:kafka.request.count"}
TRAIN_BOUND = {"@6/T_r": 15.81, "@3/T_r": 9.99}   # the training honest upper bounds quoted in RESULT_F.md
RATE = "25"
RULES = ("spike", "run3", "median")


def build_farm(farm, campaign=CAMPAIGN, cells=HELD_OUT_CELLS):
    """A campaign-shaped directory holding symlinks to the files of exactly `cells` (real directories, so that pathlib's `**` glob
    in the reader's otel_find_cells finds them; it does not follow directory symlinks)."""
    farm = Path(farm)
    if farm.exists():
        raise SystemExit("refusing: farm exists: %s" % farm)
    for name in cells:
        src = campaign / "runs" / "calibration" / name
        if not (src / "receipt.json").is_file():
            raise SystemExit("missing cell: %s" % src)
        dst = farm / "runs" / "calibration" / name
        dst.mkdir(parents=True)
        for f in sorted(src.iterdir()):
            os.symlink(f.resolve(), dst / f.name)
    for f in ("runtime-admission.json",):
        if (campaign / f).is_file():
            os.symlink((campaign / f).resolve(), farm / f)
    return farm


def farm_cells(farm):
    return sorted(p.parent.name for p in Path(farm).glob("**/receipt.json"))


def check_farm(farm, campaign=CAMPAIGN):
    """Every cell of the farm is a no-fault calibration cell of block 4 or 5, valid, and the list is exactly the 4 held-out ones."""
    names = farm_cells(farm)
    for n in names:
        rc = json.loads((Path(farm) / "runs" / "calibration" / n / "receipt.json").read_text())
        rk = rc["runKey"]
        assert rk["regime"] == "no-fault-calibration" and rk["block"] in (4, 5) and rc["state"] == "valid", (n, rk)
    assert names == sorted(HELD_OUT_CELLS), names
    return names


def poisson_bound_text(n, hours, conf=None):
    sys.path.insert(0, str(REPO / "research/detection-time"))
    import sweep_analysis_v3 as v3  # the reader's own formula: poisson_upper(n, conf) / hours
    return v3.bound(n, hours, conf)


def rule_count(rules_alarming, sid, rule):
    """Alarms of one (sensor, rule): the reader's key is exactly `<sensor id>/<rule>` (alarming rules only; absent = 0 alarms).
    Exact match: `...consumer_group.lag` is a prefix of `...consumer_group.lag_sum`, a substring match would mix them."""
    return int(rules_alarming.get("%s/%s" % (sid, rule), 0))


def summarise(J, train=None):
    """From the reader's JSON (validation block + calibration) to rows per sensor and rule. Counts come from the reader's
    `rulesAlarming` / `sensorsAlarming` (alarming only, so a rule absent there is 0 alarms: it is calibrated, see rulesCalibrated)."""
    v = J["validation"]
    x = v["perRate"][RATE]
    cal = J["calibration"]["primary"]["perRate"][RATE]
    hours = x["hours"]
    rows = []
    for label, sid in SETS.items():
        sensor = cal["sensors"][sid]
        assert sensor["placeable"] and sorted(sensor["calibrated"]) == sorted(RULES), sensor
        for rule in RULES:
            rr = cal["rules"]["%s/%s" % (sid, rule)]
            n = rule_count(x["rulesAlarming"], sid, rule)
            rows.append({"set": label, "sensor": sid, "rule": rule, "value": rr["value"], "alarms": n,
                         "hours": hours, "perHour": n / hours, "upperPerHour": None,
                         "trainHonest": rr["honest"], "trainHonestUpperPerHour": rr["honestUpperPerHour"]})
        n = x["sensorsAlarming"].get(sid, 0)
        rows.append({"set": label, "sensor": sid, "rule": "union of the sensor's 3 rules", "value": None, "alarms": n,
                     "hours": hours, "perHour": n / hours, "upperPerHour": None,
                     "trainHonest": sensor["honest"], "trainHonestUpperPerHour": sensor["honestUpperPerHour"]})
    for r in rows:
        r["upperPerHour"] = poisson_bound_text(r["alarms"], r["hours"])
    return rows, {"cells": x["cells"], "hours": hours, "rulesCalibrated": x["rulesCalibrated"]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "out"))
    ap.add_argument("--farm", default=str(FARM_DEFAULT))
    ap.add_argument("--readout-dir", default=None, help="summarise an existing readout dir written by this script's reader run "
                    "(the reader takes ~5 min); the farm must still exist")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if (out / "fresh_fa_f.json").exists() or (a.readout_dir is None and (out.exists() or READOUT_DEFAULT.exists())):
        raise SystemExit("refusing: output exists (new evidence never overwrites old): %s" % out)
    if a.readout_dir is None:
        farm = build_farm(a.farm)
    else:
        farm = Path(a.farm)
    check_farm(farm)
    rd = Path(a.readout_dir) if a.readout_dir else READOUT_DEFAULT   # 78 MB: kept out of git (tmp/), its sha256 is recorded
    if a.readout_dir is None:
        sys.path.insert(0, str(REPO / "research/detection-time"))
        import sweep_analysis_v3_3 as v33
        v33.main([str(CAMPAIGN), "--system", "otel", "--out", str(rd), "--blocks", "1", "2", "3", "4", "5", "--test-blocks", "4",
                  "5", "--split", str(SPLIT), "--validation", str(farm)])
    out.mkdir(parents=True, exist_ok=True)
    J = json.loads((rd / "sweep_analysis_v3_3.json").read_text())
    T = json.loads(TRAIN_READOUT.read_text())
    cal_equal = json.dumps(J["calibration"], sort_keys=True) == json.dumps(T["calibration"], sort_keys=True)
    rows, meta = summarise(J, T)
    res = {"label": "POST HOC (after RESULT_F.md); instance scope", "path": "reader's own --validation path, v3.3 frozen, unchanged",
           "readoutScriptSha256": J["scriptSha256"], "validation": J["validation"],
           "calibrationByteEqualToTrainingReadout": cal_equal,
           "readoutPath": str(rd.relative_to(REPO)) if rd.is_relative_to(REPO) else str(rd),
           "readoutSha256": hashlib.sha256((rd / "sweep_analysis_v3_3.json").read_bytes()).hexdigest(),
           "trainingReadoutSha256": hashlib.sha256(TRAIN_READOUT.read_bytes()).hexdigest(),
           "farmCells": farm_cells(farm), "meta": meta, "rows": rows,
           "trainBoundQuoted": TRAIN_BOUND}
    (out / "fresh_fa_f.json").write_text(json.dumps(res, indent=1, sort_keys=True))
    w = ["# Fresh false alarms of F's frozen sets on F's held-out no-fault cells (POST HOC, instance scope)", "",
         "Cells: %s. %d cells, %.4f h. Calibration byte-equal to the frozen training readout: %s." % (
             ", ".join(farm_cells(farm)), meta["cells"], meta["hours"], cal_equal), "",
         "| set | sensor | rule (calibrated value) | alarms | h | alarms/h | 95 % Poisson upper /h | training honest upper /h |",
         "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        w.append("| %s | %s | %s %s | %d | %.4f | %.2f | %.2f | %.2f |" % (
            r["set"], r["sensor"].split(":", 2)[-1], r["rule"], ("(%s)" % r["value"]) if r["value"] else "", r["alarms"],
            r["hours"], r["perHour"], r["upperPerHour"], r["trainHonestUpperPerHour"]))
    (out / "fresh_fa_f.md").write_text("\n".join(w) + "\n")
    print("\n".join(w))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
