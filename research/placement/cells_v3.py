#!/usr/bin/env python3
"""Read-only companion of celf_v3.py on the frozen v3.1 loaders: (a) each fault episode's failed-request schedule
(decision 77; the design's gap "a read-only emitter ... It computes no placement"), (b) the honest nested union
false-alarm count of given sensor sets (decisions 64, 67; design §6 "Placement FAR").

    uv run python research/placement/cells_v3.py schedule <campaign dir> [...] --system S --out <NEW file.json>
    uv run python research/placement/cells_v3.py far <campaign dir> [...] --system S --sets <celf_v3 output> \
        --out <NEW file.json>

It imports research/detection-time/sweep_analysis_v3.py (v3.1) and never edits it; the import is refused unless the
file's sha256 is the frozen one (PINNED_V3_SHA256). The campaign directories must be the ones the readout was made
from, in the same order (campaignIndex is the position).

(a) schedule: per valid fault cell, as v3's analyse3 keys its episode (regime, rate, block, campaignIndex, harness,
    cell), the onset A (`cmd.A.mono`), the hold B - A, and the sorted scheduled times of the failed ledger requests
    scheduled in [A, A + hold]: exactly the requests v1.failed_before(ledger, A, A + hold) counts (COUNT_BY_SCHEDULED,
    sweep_analysis.py:156), checked per episode. Times are absolute on the ledger's monotonic clock, so celf_v3 counts
    A <= s <= A + t with v2.4's own arithmetic.
(b) far: v3.run on the campaigns (calibration recomputed as the readout did), then v3.placement_far(sids, cr, share,
    "nested") per (setting, rate, set), with and without the ledger (its exempt `failed` never counts).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DETECTION_TIME = REPO / "research" / "detection-time"
V3_PATH = DETECTION_TIME / "sweep_analysis_v3.py"
PINNED_V3_SHA256 = "2e7ec5c387fa906a02026f0d1a5212b974f17751c24f76526a1d8418b2fd4fdd"   # v3.1 as frozen

FAILED_ONLY = True        # decision 77: failed requests only (False: every request scheduled in the hold)
FAR_SETTINGS = ("primary", "atMostOne")
SETS_CARDINALITY = True   # sets_of collects the cardinality rows' sets (decision 87: their FAR per k; False: dropped)
SETS_FOLDS = True         # sets_of collects every held-out fold's chosen and top-k sets (False: dropped)


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_v3():
    got = sha256(V3_PATH)
    if got != PINNED_V3_SHA256:
        raise SystemExit("refusing: %s has sha256 %s, not the frozen v3.1 %s" % (V3_PATH, got, PINNED_V3_SHA256))
    if str(DETECTION_TIME) not in sys.path:
        sys.path.insert(0, str(DETECTION_TIME))
    import sweep_analysis_v3 as v3  # noqa: E402  frozen v3.1, read only
    return v3


def schedule_row(c, v1):
    """One fault cell's row (keys as v3.analyse3 builds its episode)."""
    a = c["cmd"]["A"]["mono"]
    hold = c["cmd"]["B"]["mono"] - c["cmd"]["A"]["mono"]
    t_end = a + hold
    i = 5 if v1.COUNT_BY_SCHEDULED else 0
    sched = sorted(r[i] for r in c["ledger"] if (not r[2] or not FAILED_ONLY) and a <= r[i] <= t_end)
    return {"cell": c.get("cellKey", c["cell"]), "regime": c["regime"], "rate": c["rate"], "block": c["block"],
            "campaignIndex": c.get("campaignIndex", 0), "harness": c.get("harness", "sweep"),
            "onsetMono": a, "holdSeconds": hold, "failedScheduled": sched,
            "failedBeforeAtHold": v1.failed_before(c["ledger"], a, t_end)}


def check_input(digest, readout):
    """Refuse campaign directories that are not the readout's: v3's own input digest (file list and sizes) must
    equal the readout's provenance.input.sha256. readout None: no check (stated in the output)."""
    if readout is None:
        return None
    want = readout["provenance"]["input"]["sha256"]
    if digest["sha256"] != want:
        raise SystemExit("refusing: the campaigns' input digest %s is not the readout's %s (same directories, same "
                         "order as the readout's run)" % (digest["sha256"], want))
    return want


def schedule(campaigns, system, readout=None):
    v3 = load_v3()
    with v3.v24.use_system(system):
        located, cells = v3.find_and_load3([Path(x) for x in campaigns])
        digest = v3.input_digest3(*located[0]) if len(located) == 1 else v3.input_digest_multi3(located)
        checked = check_input(digest, readout)
        rows = [schedule_row(c, v3.v1) for c in cells if c["valid"] and c["target"] is not None]
    bad = [r["cell"] for r in rows if len(r["failedScheduled"]) != r["failedBeforeAtHold"]]
    if bad:
        raise SystemExit("schedule disagrees with v1.failed_before on %d episode(s): %s" % (len(bad), bad[:3]))
    return {"kind": "placement-v3-failed-schedule", "system": system, "campaigns": [str(r) for r, _ in located],
            "v3Sha256": PINNED_V3_SHA256, "input": digest, "readoutInputChecked": checked,
            "rule": "failed ledger requests scheduled in [onset, onset + hold] (v1.failed_before, COUNT_BY_SCHEDULED); "
                    "absolute monotonic seconds", "episodes": rows}


def sets_of(celf_out):
    """{rate key: sorted distinct sensor sets} from a celf_v3 output: every Pareto point's set and top-k set, every
    held-out fold's chosen and top-k set, every cardinality row's set (pre-admitted + chosen), every comparator's
    explicit set."""
    out = {}
    for per in celf_out["arms"].values():
        for rk, x in per.items():
            acc = out.setdefault(rk, set())
            for p in x.get("pareto") or []:
                acc.add(tuple(sorted(p["set"])))
                acc.add(tuple(sorted(p["topK"]["sensors"])))
                for f in (p.get("heldOut") or {}).get("folds") or []:
                    if SETS_FOLDS and f.get("chosen") is not None:
                        acc.add(tuple(sorted(f["chosen"])))
                        acc.add(tuple(sorted(f["topK"])))
            for c in (x.get("cardinality") or []) if SETS_CARDINALITY else []:
                acc.add(tuple(sorted(c["preAdmitted"] + c["chosen"])))
            for c in (x.get("comparators") or {}).values():
                if isinstance(c.get("sensors"), list):
                    acc.add(tuple(sorted(c["sensors"])))
    return {rk: sorted(v) for rk, v in out.items()}


def far(campaigns, system, sets, readout=None):
    """sets: {rate key: [[sensor id, ...], ...]}. Per setting and rate, each set's honest nested union with and
    without the rate's ledger sensor."""
    v3 = load_v3()
    camp = [Path(x) for x in campaigns]
    R = v3.finish(v3.run(camp[0] if len(camp) == 1 else camp, system=system, reference=False))
    checked = check_input(R["provenance"]["input"], readout)
    rows = []
    with v3.v24.use_system(system):
        share = v3.v24.ARMS["primary"]
        for setting in FAR_SETTINGS:
            for rk, ss in sorted(sets.items()):
                cr = R["cal"][setting]["perRate"].get(float(rk))
                if cr is None:
                    rows.append({"setting": setting, "rate": rk, "note": "— (no calibration at this rate)"})
                    continue
                ledger = sorted(s for s, k in cr["keys"].items() if k[0] == "ledger")
                for sids in ss:
                    sids = list(sids)
                    rows.append({"setting": setting, "rate": rk, "sensors": sids,
                                 "withoutLedger": _far_json(v3.placement_far(sids, cr, share, "nested")) if sids
                                 else None,
                                 "withLedger": _far_json(v3.placement_far(sids + ledger, cr, share, "nested")),
                                 "ledger": ledger})
    return {"kind": "placement-v3-far", "system": system, "campaigns": [str(x) for x in camp],
            "v3Sha256": PINNED_V3_SHA256, "input": R["provenance"]["input"], "readoutInputChecked": checked,
            "rows": rows}


def _far_json(f):
    return {k: f[k] for k in ("alarms", "union", "sumOverSensors", "hours", "totalHours", "perHour", "upperPerHour",
                              "foldsEvaluated", "cells", "rules")}


def _write_new(path, obj):
    out = Path(path)
    if out.exists() or out.is_symlink():
        raise SystemExit("refusing to write into an existing path: %s" % out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, indent=1, sort_keys=True, allow_nan=False))
    print("wrote", out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("schedule", "far"):
        p = sub.add_parser(name)
        p.add_argument("campaign", nargs="+")
        p.add_argument("--system", default="hotel", choices=("hotel", "teastore", "otel"))
        p.add_argument("--out", required=True)
        p.add_argument("--readout", help="the readout JSON these campaigns made: its input digest is checked")
        if name == "far":
            p.add_argument("--sets", required=True, help="celf_v3.py output")
    a = ap.parse_args(argv)
    if Path(a.out).exists() or Path(a.out).is_symlink():
        raise SystemExit("refusing to write into an existing path: %s" % a.out)
    ro = json.loads(Path(a.readout).read_text()) if a.readout else None
    if a.cmd == "schedule":
        res = schedule(a.campaign, a.system, ro)
    else:
        celf = json.loads(Path(a.sets).read_text())
        res = far(a.campaign, a.system, sets_of(celf), ro)
        res["sets"] = {"path": a.sets, "sha256": sha256(a.sets)}
    res["script"] = {"path": str(Path(__file__).resolve().relative_to(REPO)), "sha256": sha256(__file__)}
    res["python"] = sys.version
    _write_new(a.out, res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
