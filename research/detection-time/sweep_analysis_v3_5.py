#!/usr/bin/env python3
"""Traffic-sweep analysis v3.5: v3.3's reader and rules (sweep_analysis_v3_3.py, frozen, imported and never edited) extended for
the OTel campaign-F ablation epoch `otel-offpath-f-nolag-v1` (F without the collector's kafkametrics receiver;
research/traffic-sweep/BUDGET_OVERNIGHT_20261014.md item 2). Admission and reporting only.

    uv run python research/detection-time/sweep_analysis_v3_5.py <campaign dir> [<campaign dir> ...] --system otel \
        --out <new dir> [--blocks 1 2 3] [--split <split.json>] [--test-blocks 4 5] [--validation <no-fault campaign dir> ...]

STATUS: FROZEN by digest (research/protocol/FREEZE_V35_20261015.md) before any cell of otel-offpath-f-nolag-v1 was fetched or read
(the epoch is built and activated in the ablation worktree at 4ab4433 and not yet run; the only real cells read while v3.5 was
written are campaign F's committed TRAINING inputs, blocks 1-3 of tmp/otel-f-evidence/f1-fetch, as a regression, and synthetic
fixtures; no F replicate and no ablation cell was opened). The registry's epoch entry is pinned at the ablation harness commit 4ab4433
and active. Every claim below is scope **method**; no number is produced by this file.

ENGINEERING CHOICE (recorded): like v3.4 over v3.3 and v3.3 over v3.2, v3.5 is a module of its own. It imports v3.3 (`import
sweep_analysis_v3_3 as v33`) and, for the duration of one run, rebinds ONE v3.3 name, `ADDED_PROFILES` (the table of epochs v3.3
adds to v3.2's), to the union of v3.3's table and the one profile of parameters_v3_5.json (a context manager restores it); every
function of v3.3 that consults the table (`profiles_for`, `epochs_present`, the `v33` block's epoch list) then sees the ablation epoch
exactly as it sees F. No v3.3 function is replaced, no rule changed. A v3.5 readout carries scriptSha256 of THIS file, v33ScriptSha256
of v3.3, v32ScriptSha256 of v3.2 and v31ScriptSha256 of v3.1, keeps v3.3's `v32` and `v33` blocks, and adds a `v35` block.

DEVIATIONS FROM v3.3. A group not listed did not change (calibration, level rules, `absent`/`appear`, pass rule, cost model, lane
rules, placement and scorer logic are v3.1's, v3.2's and v3.3's). Each row names its switch (flipped only by
tests/test_sweep_analysis_v3_5.py, a planted defect each) and its registry entry (parameters_v3_5.json).
  Group 8 epoch admission (V35_EPOCH_PROFILES; switches ADMIT_NOLAG, OTEL_ONLY):
     8.7 OTel `otel-offpath-f-nolag-v1` is admitted as a campaign-E-role epoch with F's profile, byte for byte (asserted at import
         against v3.3's `otel-offpath-f-v1` entry): regimes no-fault-calibration, fraud-pause-effect, accounting-pause-effect,
         frontend-pause-effect, rate 25 req/s, two no-fault cells per block, the 1-3 / 4-5 split of split_f_otel.json. v3.2's block
         selection, held-out rule, ledger-kind check, regime check and one-new-epoch refusal apply to it unchanged, so it is never
         pooled with F, E or any other epoch. Nothing else is admitted in addition: an epoch outside v3.2's, v3.3's and this registry
         stops the run as before (UnknownSchema), and a system other than otel is refused (OTEL_ONLY: Hotel's off-path epoch is
         v3.4's, TeaStore's v3.3's; this layer reads neither).
  Group 9 bookkeeping and display (V35_ABLATION, V35_REPORT_RULE; switch ABLATION_CHECK): the readout's `v35` block carries, per
     ablation epoch read, the lag-lane integrity record: how many valid cells of the epoch collected a sensor of v3.3's `lag` lane
     (service kafka, channel metric, metric-name prefix kafka.consumer_group.lag; the lane the removed receiver fed), their keys, and
     `ablationHolds` (true iff none did); and, beside it, the number of cells that collected a coordinator-lane sensor (kafka log ids,
     which the ablation does not touch). Reporting only: a lag sensor in an ablation cell is reported loudly, not refused (the cell
     would not be an ablation cell; whether that stops the analysis is the user's decision, not this reader's).
  No other change: the lag lane of v3.3's `v33.lanes` block is `—` (no collected sensor) in every ablation episode by v3.3's own rule.
"""
import argparse
import contextlib
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import sweep_analysis_v3_3 as v33  # noqa: E402  v3.3 (frozen), never edited

v32, v31, v24 = v33.v32, v33.v31, v33.v24
DASH = v24.DASH

PARAMETERS_V35 = REPO / "research" / "protocol" / "parameters_v3_5.json"
VERSION = "3.5"
OUT_MD, OUT_JSON = "SWEEP_ANALYSIS_V3_5.md", "sweep_analysis_v3_5.json"
LABEL = "frozen v3.5 for the OTel F ablation epoch otel-offpath-f-nolag-v1 (FREEZE_V35_20261015.md)"


# =========================================================================== the v3.5 registry (decision 37)

def load_registry(path=PARAMETERS_V35):
    doc = json.loads(Path(path).read_text())
    return {p["name"]: p for p in doc["parameters"]}


REGISTRY35 = load_registry()
PARAMS_USED35 = set()


def param35(name):
    PARAMS_USED35.add(name)
    return REGISTRY35[name]["value"]


NOLAG_PROFILES = param35("V35_EPOCH_PROFILES")
ABLATION = param35("V35_ABLATION")
REPORT_RULE = param35("V35_REPORT_RULE")
V33_ADDED = dict(v33.ADDED_PROFILES)         # v3.3's table as frozen, captured before any rebinding
assert set(NOLAG_PROFILES) == {"otel-offpath-f-nolag-v1"} == set(ABLATION), "v3.5 admits exactly one epoch"
assert not set(NOLAG_PROFILES) & (set(V33_ADDED) | set(v33.V32_PROFILES)), "v3.5 adds an epoch; it does not redefine v3.2's or v3.3's"
assert all(p == V33_ADDED["otel-offpath-f-v1"] for p in NOLAG_PROFILES.values()), \
    "the ablation epoch is admitted with F's profile, byte for byte (parameters_v3_3.json otel-offpath-f-v1)"
assert all(a["designEpoch"] in V33_ADDED for a in ABLATION.values())

# Switches flipped only by tests/test_sweep_analysis_v3_5.py (planted defects); the analysis never changes them.
ADMIT_NOLAG = True        # 8.7: the ablation epoch is admitted (False: an unknown epoch, the run stops)
OTEL_ONLY = True          # 8.7: any system but otel is refused (False: passed to v3.3's engine, which reads TeaStore, stops on Hotel)
ABLATION_CHECK = True     # 9: the lag-lane integrity record is computed (False: not computed, every ablation reads as holding)
SWITCHES = ("ADMIT_NOLAG", "OTEL_ONLY", "ABLATION_CHECK")


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def admitted_profiles():
    """v3.3's added-epoch table plus the one profile of this registry (a new dict; v3.3's is never edited)."""
    merged = dict(V33_ADDED)
    if ADMIT_NOLAG:
        merged.update(NOLAG_PROFILES)
    return merged


@contextlib.contextmanager
def _v35_wrapped():
    """v3.3's `ADDED_PROFILES` is the only name rebound; every v3.3 function reads it by module name at call time."""
    prev = v33.ADDED_PROFILES
    v33.ADDED_PROFILES = admitted_profiles()
    try:
        yield
    finally:
        v33.ADDED_PROFILES = prev


# =========================================================================== whole run

def run35(campaign, system="otel", validation_dirs=(), reference=True, blocks=None, split=None, test_blocks=None):
    """v3.3's run33 with the ablation epoch admitted. Returns v3.3's result dict plus R["_v35ctx"]."""
    if OTEL_ONLY and system != "otel":
        raise SystemExit("refusing: --system %s: v3.5 admits one OTel epoch and reads OTel only (Hotel's off-path epoch is read by "
                         "v3.4, TeaStore's by v3.3)" % system)
    with _v35_wrapped():
        R = v33.run33(campaign, system=system, validation_dirs=validation_dirs, reference=reference, blocks=blocks,
                      split=split, test_blocks=test_blocks)
    R["_v35ctx"] = {"system": system}
    return R


def lane_keys(c, lane):
    """The collected sensor keys (ch, svc, tok) of a cell that belong to a v3.3 lane (the `prep` keys, v3.3's own lane engine)."""
    rules = v33.LANE_RULES["otel"]
    target = c.get("target")
    return sorted(k for k in c.get("prep", {})
                  if v33.lane_of({"ch": k[0], "svc": k[1], "tok": k[2], "own": k[1] == target}, target, rules) == lane)


def ablation_record(R, epoch):
    """The lag-lane integrity record of one ablation epoch (V35_ABLATION): valid cells, cells with a lag-lane sensor and their keys."""
    cells = [c for c in R["cells"] if c["valid"] and c.get("studyEpoch") == epoch]
    spec = ABLATION[epoch]
    lag_cells, lag_keys, coord_cells = [], set(), 0
    if ABLATION_CHECK:
        for c in cells:
            ks = lane_keys(c, "lag")
            if ks:
                lag_cells.append(c.get("cellKey", c["cell"]))
                lag_keys |= set(ks)
            coord_cells += bool(lane_keys(c, "coordinator"))
    holds = not lag_cells
    rec = {"designEpoch": spec["designEpoch"], "removed": spec["removed"], "validCellsOfEpoch": len(cells),
           "cellsWithLagLaneSensor": len(lag_cells), "lagLaneSensors": sorted("%s:%s:%s" % k for k in lag_keys),
           "cellsWithLagLaneSensorNames": sorted(lag_cells),
           "cellsWithCoordinatorLaneSensor": coord_cells, "ablationHolds": holds, "checkComputed": ABLATION_CHECK,
           "integrityCheck": spec["integrityCheck"]}
    if not holds:
        rec["note"] = ("%d of %d valid cells collected a sensor of the lag lane (%s): the removed kafkametrics receiver (or another "
                       "source of kafka.consumer_group.lag*) was present, so those cells are not ablation cells; reported, not "
                       "refused" % (len(lag_cells), len(cells), ", ".join(rec["lagLaneSensors"])))
    return rec


def _v35_block(R):
    system = R["_v35ctx"]["system"]
    read = dict(R["v32"]["epochsRead"])
    present = sorted(e for e in NOLAG_PROFILES if e in read and ADMIT_NOLAG)
    return {"version": VERSION, "label": LABEL, "system": system,
            "epochsAddedByV35": sorted(NOLAG_PROFILES) if ADMIT_NOLAG else [],
            "epochsRead": read, "ablationEpochsRead": present,
            "ablation": {e: ablation_record(R, e) for e in present},
            "rule": REPORT_RULE,
            "switches": {k: globals()[k] for k in SWITCHES},
            "parametersV35Sha256": _sha(PARAMETERS_V35),
            "parametersV35": {n: REGISTRY35[n]["value"] for n in sorted(PARAMS_USED35)}}


def build_json35(R):
    with _v35_wrapped():
        J = v33.build_json33(R)
        blk = _v35_block(R)
    J["v33ScriptSha256"] = J["scriptSha256"]
    J["version"], J["label"] = VERSION, LABEL
    J["script"] = "research/detection-time/sweep_analysis_v3_5.py"
    J["scriptSha256"] = _sha(__file__)
    J["v35"] = blk
    return J


def render35(R, J):
    with _v35_wrapped():
        md = v33.render33(R, J)
    v = J["v35"]
    w = ["", "## v3.5 additions (OTel F ablation epoch; admission and lag-lane integrity)", "",
         "Frozen v3.5 (FREEZE_V35_20261015.md); harness pinned at the ablation worktree commit 4ab4433. Scope: instance; a report, no "
         "mechanism claim.", "",
         "- Epoch added by v3.5: %s." % (", ".join("`%s`" % e for e in v["epochsAddedByV35"]) or DASH),
         "- Ablation epoch read: %s." % (", ".join("`%s`" % e for e in v["ablationEpochsRead"]) or DASH),
         "- Rule: " + v["rule"], ""]
    for e, a in v["ablation"].items():
        w += ["### Lag-lane integrity, `%s` (design epoch `%s`)" % (e, a["designEpoch"]), "",
              "- valid cells of the epoch: %d; with a collected lag-lane sensor: %d; with a collected coordinator-lane sensor: %d." % (
                  a["validCellsOfEpoch"], a["cellsWithLagLaneSensor"], a["cellsWithCoordinatorLaneSensor"]),
              "- ablation holds (no lag-lane sensor in any cell): **%s**%s." % (
                  a["ablationHolds"], "" if a["checkComputed"] else " (CHECK NOT COMPUTED: planted switch)")]
        if a.get("note"):
            w.append("- **" + a["note"] + "**")
        w.append("")
    return md + "\n".join(w) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("campaign", nargs="+", help="fetched campaign directory/ies of one system (pooled, H1)")
    ap.add_argument("--system", default="otel", choices=v24.SYSTEMS)
    ap.add_argument("--out", required=True, help="NEW output directory; refused if it exists")
    ap.add_argument("--validation", nargs="+", default=[], help="no-fault campaign directory/ies, never pooled")
    ap.add_argument("--blocks", nargs="+", type=int, default=None,
                    help="block numbers of a campaign-E-role epoch to read (V32_BLOCK_SELECT_RULE); default all")
    ap.add_argument("--test-blocks", nargs="+", type=int, default=None,
                    help="blocks held out of every fit and calibration (decision 102); the registry's test blocks")
    ap.add_argument("--split", default=None, help="the declared split file (its sha256 is recorded)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists() or out.is_symlink():
        raise SystemExit("refusing to write into an existing path: %s" % out)
    camp = [Path(x) for x in a.campaign]
    R = run35(camp[0] if len(camp) == 1 else camp, system=a.system, validation_dirs=[Path(x) for x in a.validation],
              blocks=set(a.blocks) if a.blocks is not None else None, split=a.split,
              test_blocks=set(a.test_blocks) if a.test_blocks is not None else None)
    with v24.use_system(a.system):
        v31.finish(R)
    J = build_json35(R)
    out.mkdir(parents=True)
    v31.write_new(out / OUT_JSON, json.dumps(J, indent=1, sort_keys=True, default=sorted))
    v31.write_new(out / OUT_MD, render35(R, J))
    print("wrote", out / OUT_JSON, out / OUT_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
