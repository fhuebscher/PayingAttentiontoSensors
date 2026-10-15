#!/usr/bin/env python3
"""POST HOC fresh false-alarm check of the F ablation (otel-offpath-f-nolag-v1): a thin wrapper over research/placement/test-f/fresh-fa/fresh_fa_f.py,
adapted from research/placement/test-f-rep1/fresh_fa_rep.py for the ablation epoch and the v3.5 reader.

fresh_fa_f.py cannot take the ablation's paths: its campaign, training readout, held-out cell names, the reader (v3.3) and the readout file name
(`sweep_analysis_v3_3.json`) are constants of F attempt 1, and its default sets are F's two sensors, one of which is the Kafka lag sensor the ablation
does not have. This wrapper edits nothing in it. It (1) selects the ablation's held-out cells FROM THE RECEIPTS (regime no-fault-calibration, block 4 or
5, state valid, runKey.attempt --attempt, studyEpoch otel-offpath-f-nolag-v1; exactly 4, else it refuses), (2) builds the symlink farm of exactly
those cells with fresh_fa_f.build_farm, (3) runs the frozen v3.5 reader's main() with the arguments fresh_fa_f uses (`--blocks 1 2 3 4 5 --test-blocks 4 5
--split ... --validation <farm>`), (4) presents the v3.5 readout to fresh_fa_f under the file name it reads: a directory holding the symlink
`sweep_analysis_v3_3.json -> <readout dir>/sweep_analysis_v3_5.json` (no copy, no rewrite: the bytes and the reader digest it records are the v3.5
reader's), (5) sets fresh_fa_f's module globals (TRAIN_READOUT, HELD_OUT_CELLS, TRAIN_BOUND, SETS) and calls fresh_fa_f.main(--readout-dir <view>) to do
the summary unchanged, (6) writes <out>/fresh_fa_nolag_provenance.json.

    uv run python research/placement/test-f-nolag/fresh_fa_nolag.py --campaign tmp/otel-f-evidence/nolag1-fetch/x \
        --train-readout research/traffic-sweep/readout-otel-f-nolag-train-v3.5/sweep_analysis_v3_5.json \
        --sets-from-placement research/placement/test-f-nolag/placement-nolag.json \
        --out research/placement/test-f-nolag/fresh-fa-nolag [--attempt 1]

SETS. There is no default: F's two sensors include the lag sensor, which the ablation does not collect (fresh_fa_f.summarise would stop on it). Give either
`--sets-from-placement <the ablation's frozen placement>` (the `@6/T_r` and `@3/T_r` sets of the unrestricted cell, rate 25, as frozen: every member
becomes a row group `@6/T_r[1]`, `@6/T_r[2]`, ..., one label when the set has one member; an empty set refuses) or `--set LABEL=ID[,ID...]` once per
label. Each sensor must be placeable with all three rules calibrated in the training calibration (fresh_fa_f.summarise asserts it). The rows of one
declared set are summed by label prefix by whoever scores FNL-V5 (rows[rule == 'union of the sensor's 3 rules']).
Wording in fresh_fa_f's own outputs ("after RESULT_F.md", file names fresh_fa_f.*) is F's; here `trainBoundQuoted` is {} (no bound is quoted; the
training honest bounds come from the ablation's own calibration).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "research" / "placement" / "test-f" / "fresh-fa"))
sys.path.insert(0, str(REPO / "research" / "detection-time"))
sys.path.insert(0, str(HERE))
import fresh_fa_f as ff  # noqa: E402  imported, never edited
import score_nolag as sn  # noqa: E402  (check_ablation_only; the ablation-epoch readout test)

EPOCH = "otel-offpath-f-nolag-v1"
RATE = "25"
BUDGET_LABELS = {"@6/T_r": "6/T_r", "@3/T_r": "3/T_r"}
FARM_DEFAULT = REPO / "tmp" / "fresh-fa-nolag" / "farm"
READOUT_DEFAULT = REPO / "tmp" / "fresh-fa-nolag" / "readout-v3.5-validation"
F_FETCH = re.compile(r"^f\d+-fetch2?$")


def select_cells(campaign, attempt=1):
    """Held-out no-fault cell names of the ablation, from receipts. Refuses unless exactly 4, all valid, of the ablation epoch and `attempt`."""
    campaign = Path(campaign)
    cells = []
    for rc in sorted(campaign.glob("runs/calibration/*/receipt.json")):
        r = json.loads(rc.read_text())
        k = r.get("runKey", {})
        if k.get("regime") != "no-fault-calibration" or k.get("block") not in (4, 5):
            continue
        if r.get("state") != "valid":
            raise SystemExit("refusing: held-out cell %s is %r, not valid" % (rc.parent.name, r.get("state")))
        if k.get("attempt") != attempt or k.get("studyEpoch") != EPOCH:
            raise SystemExit("refusing: cell %s is attempt %r of %r, not attempt %d of %s (not the ablation)"
                             % (rc.parent.name, k.get("attempt"), k.get("studyEpoch"), attempt, EPOCH))
        cells.append(rc.parent.name)
    if len(cells) != 4:
        raise SystemExit("refusing: %d held-out no-fault cells in %s, expected 4: %r" % (len(cells), campaign, cells))
    return cells


def parse_sets(items):
    """`LABEL=ID[,ID...]` once per label -> {row label: sensor id}; a label with several ids becomes LABEL[1], LABEL[2], ..."""
    sets = {}
    seen = set()
    for it in items:
        label, sep, ids = it.partition("=")
        members = [x for x in ids.split(",")] if sep else []
        if not sep or not label or not members or any(not m for m in members) or label in seen or len(set(members)) != len(members):
            raise SystemExit("refusing: --set wants LABEL=SENSOR_ID[,SENSOR_ID...], once per label, no empty or repeated id: %r" % it)
        seen.add(label)
        if len(members) == 1:
            sets[label] = members[0]
        else:
            sets.update({"%s[%d]" % (label, i): m for i, m in enumerate(members, 1)})
    return sets


def sets_from_placement(placement, rate=RATE):
    """`@6/T_r` and `@3/T_r`: the frozen sets of the unrestricted (maxEffort any, maxRuntime any) cell at `rate`, as `--set` items."""
    P = json.loads(Path(placement).read_text())
    R = (P.get("rates") or {}).get(rate)
    if not R or "grid" not in R:
        raise SystemExit("refusing: %s has no frozen grid at rate %s" % (placement, rate))
    cell = [c for c in R["grid"] if c["maxEffort"] == "any" and c["maxRuntime"] == "any"]
    if len(cell) != 1:
        raise SystemExit("refusing: %s has %d unrestricted cells, expected 1" % (placement, len(cell)))
    items = []
    for label, budget in BUDGET_LABELS.items():
        S = (cell[0]["points"].get(budget) or {}).get("set")
        if not S:
            raise SystemExit("refusing: the frozen %s set of %s is %r (empty or absent): nothing to check" % (budget, placement, S))
        items.append("%s=%s" % (label, ",".join(S)))
    return items


def main(argv=None, reader=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--campaign", required=True, help="the ablation's fetched campaign dir (.../nolag1-fetch/x)")
    ap.add_argument("--train-readout", required=True, help="the ablation's v3.5 training readout json")
    ap.add_argument("--out", required=True, help="NEW output dir")
    ap.add_argument("--attempt", type=int, default=1)
    ap.add_argument("--farm", default=str(FARM_DEFAULT))
    ap.add_argument("--readout-dir", default=str(READOUT_DEFAULT))
    ap.add_argument("--set", action="append", default=[], dest="sets")
    ap.add_argument("--sets-from-placement", default=None)
    a = ap.parse_args(argv)
    campaign, train, out = Path(a.campaign).resolve(), Path(a.train_readout).resolve(), Path(a.out)
    if any(F_FETCH.match(p) for p in campaign.parts):
        raise SystemExit("refusing: %s is a fetch of campaign F or its replicates, not the ablation's" % campaign)
    if hashlib.sha256(train.read_bytes()).hexdigest() in sn.F_READOUT_SHA256 or \
            hashlib.sha256(train.read_bytes()).hexdigest() == hashlib.sha256(ff.TRAIN_READOUT.read_bytes()).hexdigest():
        raise SystemExit("refusing: --train-readout is a byte copy of F's training readout")
    sn.check_ablation_only(train, "training readout")
    if bool(a.sets) == bool(a.sets_from_placement):
        raise SystemExit("refusing: give exactly one of --set (once per label) or --sets-from-placement: there is no default set "
                         "(F's lag sensor does not exist in the ablation)")
    for p in (out, Path(a.farm), Path(a.readout_dir)):
        if p.exists():
            raise SystemExit("refusing: output exists (new evidence never overwrites old): %s" % p)
    items = sets_from_placement(a.sets_from_placement) if a.sets_from_placement else a.sets
    sets = parse_sets(items)
    cells = select_cells(campaign, a.attempt)
    ff.build_farm(a.farm, campaign=campaign, cells=cells)
    ff.HELD_OUT_CELLS, ff.TRAIN_READOUT, ff.TRAIN_BOUND, ff.SETS = cells, train, {}, sets
    if reader is None:
        import sweep_analysis_v3_5 as v35
        reader = v35.main
    reader([str(campaign), "--system", "otel", "--out", a.readout_dir, "--blocks", "1", "2", "3", "4", "5", "--test-blocks", "4", "5",
            "--split", str(ff.SPLIT), "--validation", a.farm])
    real = Path(a.readout_dir) / "sweep_analysis_v3_5.json"
    view = Path(str(a.readout_dir) + ".fresh_fa_f_view")
    view.mkdir()
    os.symlink(real.resolve(), view / "sweep_analysis_v3_3.json")          # the name fresh_fa_f reads; the content is the v3.5 readout
    rc = ff.main(["--out", str(out), "--farm", a.farm, "--readout-dir", str(view)])
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731
    rec = {"label": "POST HOC fresh false alarms, F ablation otel-offpath-f-nolag-v1; instance scope", "campaign": str(campaign),
           "attempt": a.attempt, "heldOutCells": cells, "sets": sets,
           "setsAre": ("the ablation's frozen @6/T_r and @3/T_r sets from %s" % a.sets_from_placement) if a.sets_from_placement
           else "given by --set",
           "setsFromPlacementSha256": sha(a.sets_from_placement) if a.sets_from_placement else None,
           "trainReadout": str(train), "trainReadoutSha256": sha(train),
           "readoutDir": a.readout_dir, "readoutSha256": sha(real), "readoutViewForFreshFaF": str(view),
           "readoutViewNote": "a symlink named sweep_analysis_v3_3.json (the name fresh_fa_f reads) to the v3.5 readout; no copy",
           "split": str(ff.SPLIT), "splitSha256": sha(ff.SPLIT),
           "wrapper": str(Path(__file__).resolve().relative_to(REPO)), "wrapperSha256": sha(__file__),
           "freshFaF": "research/placement/test-f/fresh-fa/fresh_fa_f.py", "freshFaFSha256": sha(ff.__file__),
           "note": "fresh_fa_f's own output files say 'after RESULT_F.md' and name F (fresh_fa_f.json/.md); their rows are the ablation's"}
    with open(out / "fresh_fa_nolag_provenance.json", "x", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, indent=1, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
