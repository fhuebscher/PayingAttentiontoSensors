#!/usr/bin/env python3
"""POST HOC fresh false alarms of R2's second frozen member, metric:flagd:feature_flag.flagd.impression, whose spike rule was dropped in
calibration, so fresh_fa_fs1.py's summarise() (which asserts all three rules calibrated) refuses it. Reads the validation readout that
fresh_fa_fs1.py's own reader run wrote before it refused (tmp/fresh-fa-fs1-own/readout-v3.3-validation, frozen v3.3 reader), checks its
calibration of this sensor equals the R2 training readout's, and counts alarms of the CALIBRATED rules only (an uncalibrated rule is not
part of the sensor and cannot alarm), with fresh_fa_f's own rule_count and Poisson bound. Scope instance; written before it ran.

    uv run python research/placement/test-f-seed2/fresh_fa_partial_fs1.py --out research/placement/test-f-seed2/fresh-fa-fs1-flagd.json
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "research/placement/test-f/fresh-fa"))
import fresh_fa_f as ff  # noqa: E402  imported, never edited

SID = "metric:flagd:feature_flag.flagd.impression"
VAL = REPO / "tmp/fresh-fa-fs1-own/readout-v3.3-validation/sweep_analysis_v3_3.json"
TRAIN = REPO / "research/traffic-sweep/readout-otel-fs1-train-v3.3/sweep_analysis_v3_3.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        raise SystemExit("refusing: output exists")
    J, T = json.loads(VAL.read_text()), json.loads(TRAIN.read_text())
    cal = J["calibration"]["primary"]["perRate"][ff.RATE]
    tcal = T["calibration"]["primary"]["perRate"][ff.RATE]
    s, ts = cal["sensors"][SID], tcal["sensors"][SID]
    if json.dumps(s, sort_keys=True) != json.dumps(ts, sort_keys=True):
        raise SystemExit("refusing: the validation readout's calibration of %s differs from the training readout's" % SID)
    x = J["validation"]["perRate"][ff.RATE]
    hours = x["hours"]
    rows = []
    for rule in sorted(s["calibrated"]):
        rr = cal["rules"]["%s/%s" % (SID, rule)]
        if json.dumps(rr, sort_keys=True) != json.dumps(tcal["rules"]["%s/%s" % (SID, rule)], sort_keys=True):
            raise SystemExit("refusing: rule %s calibration differs" % rule)
        n = ff.rule_count(x["rulesAlarming"], SID, rule)
        rows.append({"rule": rule, "value": rr["value"], "alarms": n, "hours": hours, "upperPerHour": ff.poisson_bound_text(n, hours),
                     "trainHonestUpperPerHour": rr["honestUpperPerHour"]})
    n = x["sensorsAlarming"].get(SID, 0)
    rows.append({"rule": "union of calibrated rules", "alarms": n, "hours": hours, "upperPerHour": ff.poisson_bound_text(n, hours),
                 "trainHonestUpperPerHour": s["honestUpperPerHour"]})
    rec = {"label": "POST HOC fresh false alarms, R2 second frozen member (calibrated rules only); instance", "sensor": SID,
           "dropped": s.get("dropped"), "cells": x["cells"], "rows": rows,
           "inputs": {"validationReadout": str(VAL.relative_to(REPO)), "validationReadoutSha256": hashlib.sha256(VAL.read_bytes()).hexdigest(),
                      "trainingReadoutSha256": hashlib.sha256(TRAIN.read_bytes()).hexdigest(),
                      "scriptSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    out.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
