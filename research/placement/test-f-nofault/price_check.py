#!/usr/bin/env python3
"""R4 (BUDGET_TS_PLACEMENT_20261015_AMENDMENT2.md, a0e50a3): price check of F's frozen sensors on fresh no-fault time. POST HOC to every
placement it checks; scope instance (OTel Demo, fb14srv6, 25 req/s).

R4 runs F's unchanged plan (harness 715d57b) at attempt 6; only its 10 no-fault cells are read (its fault cells are not read). For each
entry of sets.json the frozen v3.3 reader is run on the entry's CALIBRATION campaign exactly as fresh_fa_f.py runs it
(`--blocks 1 2 3 4 5 --test-blocks 4 5 --split split_f_otel.json --validation <farm>`), where the farm holds symlinks to R4's 10 no-fault
cells only. The readout's `calibration` must be byte-equal to the entry's committed training readout (the sensor is never refitted; else
refuse). Per sensor and rule: alarms k on the farm, hours T, k/T, the reader's 95 % Poisson upper bound, an exact 95 % lower bound, and the
training honest upper bound (the price). Verdict per sensor (union of its rules): "contradicted" iff the fresh 95 % lower bound exceeds the
training price; "bounded below the price" iff the fresh 95 % upper bound is below it; else "consistent, not bounded". Not an equivalence test. The ledger is reported without a price (it is never priced).

    uv run python research/placement/test-f-nofault/price_check.py --campaign tmp/otel-f-evidence/nf1-fetch/x --out research/placement/test-f-nofault/out
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "research" / "placement" / "test-f" / "fresh-fa"))
sys.path.insert(0, str(REPO / "research" / "detection-time"))
import fresh_fa_f as ff  # noqa: E402  imported, never edited
import hand_check as hc  # noqa: E402  imported, never edited (its own raw otelcol.log parser, not the adapter's)

EPOCH = "otel-offpath-f-v1"
ATTEMPTS = (6, 7)  # 6 = R4; 7 = its one declared relaunch (only that attempt's cells are then read)
CELLS = 10
RATE = "25"
SPLIT = REPO / "research" / "protocol" / "split_f_otel.json"
SETS = HERE / "sets.json"


def select_cells(campaign, attempt):
    """R4's no-fault cells from the receipts: regime no-fault-calibration, state valid, the attempt, the F epoch; exactly CELLS."""
    out = []
    for rc in sorted(Path(campaign).glob("runs/calibration/*/receipt.json")):
        r = json.loads(rc.read_text())
        k = r.get("runKey", {})
        if k.get("regime") != "no-fault-calibration":
            continue
        if r.get("state") != "valid" or k.get("attempt") != attempt or k.get("studyEpoch") != EPOCH:
            raise SystemExit("refusing: %s is not a valid attempt-%d %s no-fault cell (%r)" % (rc.parent.name, attempt, EPOCH, k))
        out.append(rc.parent.name)
    if len(out) != CELLS:
        raise SystemExit("refusing: %d no-fault cells, expected %d" % (len(out), CELLS))
    return out


def raw_samples(cell_dir, sensor):
    """Samples of a metric sensor in a cell's raw otelcol.log (hc.raw_series; 0 when the metric never appears). Whole log, not the
    reader's window: a coarse presence check that catches a sensor absent from a cell, not one that stopped part-way."""
    _, svc, metric = sensor.split(":", 2)
    try:
        return len(hc.raw_series(Path(cell_dir) / "otelcol.log", metric, svc))
    except KeyError:  # raw_series pops its meta entry, absent when the metric never appeared
        return 0


def presence(campaign, cells, sensors):
    """{sensor: {cell: samples}} for the metric sensors; a sensor with 0 samples in any cell gets its rows reported as —."""
    return {s: {c: raw_samples(Path(campaign) / "runs" / "calibration" / c, s) for c in cells} for s in sensors if s.startswith("metric:")}


def lower95(k, hours):
    """Exact one-sided 95 % lower bound of a Poisson rate: the lambda*T with P(X >= k) = 0.05 (0 for k = 0), by bisection."""
    if k == 0:
        return 0.0
    def tail(mu):  # P(X >= k)
        return 1.0 - sum(math.exp(-mu) * mu ** i / math.factorial(i) for i in range(k))
    lo, hi = 0.0, float(k) + 10.0 * math.sqrt(k) + 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if tail(mid) < 0.05 else (lo, mid)
    return lo / hours


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run_reader(cal_campaign, farm, out_dir):
    import sweep_analysis_v3_3 as v33
    v33.main([str(REPO / cal_campaign), "--system", "otel", "--out", str(out_dir), "--blocks", "1", "2", "3", "4", "5",
              "--test-blocks", "4", "5", "--split", str(SPLIT), "--validation", str(farm)])
    return json.loads((Path(out_dir) / "sweep_analysis_v3_3.json").read_text())


def rows_for(entry, J, present=None):
    T = json.loads((REPO / entry["trainingReadout"]).read_text())
    if json.dumps(J["calibration"], sort_keys=True) != json.dumps(T["calibration"], sort_keys=True):
        raise SystemExit("refusing: the readout's calibration is not byte-equal to %s (a refit)" % entry["trainingReadout"])
    x = J["validation"]["perRate"][RATE]
    if x["cells"] != CELLS:
        raise SystemExit("refusing: the validation block read %r cells, expected %d" % (x["cells"], CELLS))
    cal = J["calibration"]["primary"]["perRate"][RATE]
    hours = x["hours"]
    sensors = ([s for s in cal["sensors"] if s.startswith("ledger:frontendproxy:")] if entry["sensor"].endswith(":*")
               else [entry["sensor"]])
    rows = []
    for sid in sensors:
        s = cal["sensors"][sid]
        if not s["placeable"] or sorted(s["calibrated"]) != sorted(entry["rules"]):
            raise SystemExit("refusing: %s is not placeable with rules %r in the training calibration" % (sid, entry["rules"]))
        for rule in entry["rules"]:
            rr = cal["rules"]["%s/%s" % (sid, rule)]
            n = ff.rule_count(x["rulesAlarming"], sid, rule)
            rows.append({"label": entry["label"], "sensor": sid, "rule": rule, "alarms": n, "hours": hours,
                         "price": rr.get("honestUpperPerHour")})
        # the reader's sensorsAlarming covers placeable NON-ledger sensors only (sweep_analysis_v3.validation): a ledger union is —, not 0
        n = None if sid.startswith("ledger:") else int(x["sensorsAlarming"].get(sid, 0))
        rows.append({"label": entry["label"], "sensor": sid, "rule": "union", "alarms": n, "hours": hours,
                     "price": s.get("honestUpperPerHour")})
    for r in rows:
        if present is not None and r["sensor"] in present and min(present[r["sensor"]].values()) == 0:
            r["alarms"], r["absentFrom"] = None, sorted(c for c, n in present[r["sensor"]].items() if n == 0)
        if r["alarms"] is None:
            r.update(perHour=None, upper95=None, lower95=None, verdict="—")
            continue
        r["perHour"] = r["alarms"] / r["hours"]
        r["upper95"] = ff.poisson_bound_text(r["alarms"], r["hours"])
        r["lower95"] = lower95(r["alarms"], r["hours"])
        r["verdict"] = ("—" if r["price"] is None or r["rule"] != "union" or r["sensor"].startswith("ledger:")
                        else "contradicted" if r["lower95"] > r["price"]
                        else "bounded below the price" if r["upper95"] < r["price"] else "consistent, not bounded")
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True, help="R4's fetched campaign dir (.../x)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--attempt", type=int, default=ATTEMPTS[0])
    ap.add_argument("--dry-run", action="store_true", help="wiring check on other cells: any --attempt, outputs marked DRY, under tmp/ only")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists():
        raise SystemExit("refusing: output exists (new evidence never overwrites old): %s" % out)
    if a.attempt not in ATTEMPTS and not a.dry_run:
        raise SystemExit("refusing: attempt %d is not R4's %r (use --dry-run for a wiring check)" % (a.attempt, ATTEMPTS))
    if a.dry_run and REPO / "tmp" not in out.resolve().parents:
        raise SystemExit("refusing: a dry run writes under tmp/ only")
    cfg = json.loads(SETS.read_text())
    cells = select_cells(a.campaign, a.attempt)
    work = REPO / "tmp" / ("price-check-dry" if a.dry_run else "price-check-nf") / out.name
    if work.exists():
        raise SystemExit("refusing: work dir exists: %s" % work)
    farm = ff.build_farm(work / "farm", campaign=Path(a.campaign), cells=cells)
    present = presence(a.campaign, cells, [e["sensor"] for e in cfg["sets"]])
    readouts, rows = {}, []
    for entry in cfg["sets"]:
        c = entry["calibrationCampaign"]
        if c not in readouts:
            rd = work / ("readout-%d" % len(readouts))
            readouts[c] = (rd, run_reader(c, farm, rd))
        rows += rows_for(entry, readouts[c][1], present)
    out.mkdir(parents=True)
    res = {"label": ("DRY RUN (wiring check, not evidence); " if a.dry_run else "") + "R4 price check, POST HOC; instance scope",
           "campaign": a.campaign, "attempt": a.attempt, "cells": cells, "setsSha256": sha(SETS), "scriptSha256": sha(__file__),
           "readouts": {c: {"path": str(rd), "sha256": sha(rd / "sweep_analysis_v3_3.json")} for c, (rd, _) in readouts.items()},
           "rawSamplesPerCell": present, "rows": rows}
    (out / "price_check.json").write_text(json.dumps(res, indent=1, sort_keys=True))
    w = ["# R4 price check%s (POST HOC, instance)" % (" — DRY RUN" if a.dry_run else ""), "",
         "%d no-fault cells, %.4f h. Contradicted iff the fresh one-sided 95 %% lower bound exceeds the training price; bounded below iff the one-sided 95 %% upper bound is under it. A metric sensor with 0 raw samples in any cell is —." % (len(cells), rows[0]["hours"]), "",
         "Raw samples per cell (min / max): " + "; ".join("%s %d / %d" % (s.split(":", 2)[-1], min(v.values()), max(v.values())) for s, v in present.items()), "",
         "| set | sensor | rule | k | h | k/h | 95 % lower /h | 95 % upper /h | training price /h | verdict |", "|---|---|---|---|---|---|---|---|---|---|"]
    f2 = lambda v: "—" if v is None else "%.2f" % v
    for r in rows:
        w.append("| %s | %s | %s | %s | %.4f | %s | %s | %s | %s | %s |" % (
            r["label"], r["sensor"].split(":", 2)[-1], r["rule"], "—" if r["alarms"] is None else r["alarms"], r["hours"],
            f2(r["perHour"]), f2(r["lower95"]), f2(r["upper95"]), f2(r["price"]), r["verdict"]))
    (out / "price_check.md").write_text("\n".join(w) + "\n")
    print("\n".join(w))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
