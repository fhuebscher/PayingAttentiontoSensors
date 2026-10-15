#!/usr/bin/env python3
"""Attempt-3 copy of fresh_fa_rep.py (c08b2d5), made 2026-10-15 because the original hard-codes ATTEMPT = 2 and refuses attempt 3 cells; differs only by the constants below (diff in the commit). POST HOC fresh false-alarm check of campaign F's replicate (attempt 3): a thin wrapper over research/placement/test-f/fresh-fa/fresh_fa_f.py.

fresh_fa_f.py cannot take the replicate's paths: its campaign, training readout, held-out cell names and the defaults of build_farm are
constants of F's attempt 1 (run IDs carry the attempt). This wrapper edits nothing in it. It (1) selects the replicate's held-out cells FROM
THE RECEIPTS (regime no-fault-calibration, block 4 or 5, state valid, runKey.attempt 3, studyEpoch otel-offpath-f-v1; exactly 4, else it
refuses), (2) builds the symlink farm of exactly those cells with fresh_fa_f.build_farm, (3) runs the frozen v3.3 reader's main() with the
same arguments fresh_fa_f uses (`--blocks 1 2 3 4 5 --test-blocks 4 5 --split ... --validation <farm>`), (4) sets fresh_fa_f's module
globals (TRAIN_READOUT, HELD_OUT_CELLS, TRAIN_BOUND, SETS) and calls fresh_fa_f.main(--readout-dir ...) to do the summary unchanged,
(5) writes <out>/fresh_fa_rep_provenance.json.

    uv run python research/placement/test-f-rep1/fresh_fa_rep_f3.py --campaign tmp/otel-f-evidence/f3-fetch2/x \
        --train-readout research/traffic-sweep/readout-otel-f3-train-v3.3/sweep_analysis_v3_3.json \
        --out research/placement/test-f-rep1/fresh-fa-f3 [--set LABEL=SENSOR_ID ...]

SETS. Without --set the sensors are F's two frozen sets (`@6/T_r` lag, `@3/T_r` request.count): a like-for-like check of F's sets on the
replicate's held-out cells. Pass --set once per set (replacing both) to check the replicate's own frozen sets instead; each must be a
placeable sensor of the replicate's training calibration with all three rules calibrated (fresh_fa_f.summarise asserts it).
Wording in fresh_fa_f's own outputs ("after RESULT_F.md", `trainBoundQuoted`) is F's; here `trainBoundQuoted` is {} (no bound is quoted
for the replicate; the training honest bounds come from the replicate's own calibration).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "research" / "placement" / "test-f" / "fresh-fa"))
sys.path.insert(0, str(REPO / "research" / "detection-time"))
import fresh_fa_f as ff  # noqa: E402  imported, never edited

EPOCH = "otel-offpath-f-v1"
ATTEMPT = 3
FARM_DEFAULT = REPO / "tmp" / "fresh-fa-f3" / "farm"
READOUT_DEFAULT = REPO / "tmp" / "fresh-fa-f3" / "readout-v3.3-validation"


def select_cells(campaign):
    """Held-out no-fault cell names of the replicate, from receipts. Refuses unless exactly 4, all attempt 3 of the F epoch."""
    campaign = Path(campaign)
    cells = []
    for rc in sorted(campaign.glob("runs/calibration/*/receipt.json")):
        r = json.loads(rc.read_text())
        k = r.get("runKey", {})
        if k.get("regime") != "no-fault-calibration" or k.get("block") not in (4, 5):
            continue
        if r.get("state") != "valid":
            raise SystemExit("refusing: held-out cell %s is %r, not valid" % (rc.parent.name, r.get("state")))
        if k.get("attempt") != ATTEMPT or k.get("studyEpoch") != EPOCH:
            raise SystemExit("refusing: cell %s is attempt %r of %r, not attempt %d of %s (not the replicate)"
                             % (rc.parent.name, k.get("attempt"), k.get("studyEpoch"), ATTEMPT, EPOCH))
        cells.append(rc.parent.name)
    if len(cells) != 4:
        raise SystemExit("refusing: %d held-out no-fault cells in %s, expected 4: %r" % (len(cells), campaign, cells))
    return cells


def parse_sets(items):
    sets = {}
    for it in items:
        label, sep, sid = it.partition("=")
        if not sep or not label or not sid or label in sets:
            raise SystemExit("refusing: --set wants LABEL=SENSOR_ID, once per label: %r" % it)
        sets[label] = sid
    return sets or dict(ff.SETS)


def main(argv=None, reader=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--campaign", required=True, help="the replicate's fetched campaign dir (.../f3-fetch2/x)")
    ap.add_argument("--train-readout", required=True, help="the replicate's v3.3 training readout json")
    ap.add_argument("--out", required=True, help="NEW output dir")
    ap.add_argument("--farm", default=str(FARM_DEFAULT))
    ap.add_argument("--readout-dir", default=str(READOUT_DEFAULT))
    ap.add_argument("--set", action="append", default=[], dest="sets")
    a = ap.parse_args(argv)
    campaign, train, out = Path(a.campaign).resolve(), Path(a.train_readout).resolve(), Path(a.out)
    if "f1-fetch" in campaign.parts:
        raise SystemExit("refusing: %s is F attempt 1's fetch, not the replicate's" % campaign)
    if hashlib.sha256(train.read_bytes()).hexdigest() == hashlib.sha256(ff.TRAIN_READOUT.read_bytes()).hexdigest():
        raise SystemExit("refusing: --train-readout is a byte copy of F's training readout")
    for p in (out, Path(a.farm), Path(a.readout_dir)):
        if p.exists():
            raise SystemExit("refusing: output exists (new evidence never overwrites old): %s" % p)
    sets = parse_sets(a.sets)
    cells = select_cells(campaign)
    ff.build_farm(a.farm, campaign=campaign, cells=cells)
    ff.HELD_OUT_CELLS, ff.TRAIN_READOUT, ff.TRAIN_BOUND, ff.SETS = cells, train, {}, sets
    if reader is None:
        import sweep_analysis_v3_3 as v33
        reader = v33.main
    reader([str(campaign), "--system", "otel", "--out", a.readout_dir, "--blocks", "1", "2", "3", "4", "5", "--test-blocks", "4", "5",
            "--split", str(ff.SPLIT), "--validation", a.farm])
    rc = ff.main(["--out", str(out), "--farm", a.farm, "--readout-dir", a.readout_dir])
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731
    rec = {"label": "POST HOC fresh false alarms, campaign F replicate (attempt 3); instance scope", "campaign": str(campaign),
           "heldOutCells": cells, "sets": sets, "setsAre": "F's frozen sets" if not a.sets else "given by --set",
           "trainReadout": str(train), "trainReadoutSha256": sha(train),
           "readoutDir": a.readout_dir, "readoutSha256": sha(Path(a.readout_dir) / "sweep_analysis_v3_3.json"),
           "split": str(ff.SPLIT), "splitSha256": sha(ff.SPLIT),
           "wrapper": str(Path(__file__).resolve().relative_to(REPO)), "wrapperSha256": sha(__file__),
           "freshFaF": "research/placement/test-f/fresh-fa/fresh_fa_f.py", "freshFaFSha256": sha(ff.__file__),
           "note": "fresh_fa_f's own output files say 'after RESULT_F.md' and name F; their rows are the replicate's"}
    with open(out / "fresh_fa_rep_provenance.json", "x", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, indent=1, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
