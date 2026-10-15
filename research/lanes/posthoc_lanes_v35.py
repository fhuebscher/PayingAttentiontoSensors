#!/usr/bin/env python3
"""POST HOC lane rows for the F ablation otel-offpath-f-nolag-v1: research/lanes/posthoc_lanes_v33.py's `otel` command over v3.5 readouts. A thin wrapper.

    uv run python research/lanes/posthoc_lanes_v35.py otel --training-readout <v3.5 training readout.json> \
        --scoring-readout <v3.5 scoring readout.json> --placement <frozen celf_v3_5 placement.json> --out-dir <NEW dir>

WHY A WRAPPER. posthoc_lanes_v33.py binds celf_v3_3 and score_test_v3_3 (module names `c3`, `s3`) and checks readouts with celf_v3_3.check_v33_layer, which
accept v3.3 readouts only: it refuses a v3.5 readout (version "3.5"), and its decision-73 rerun and scoring calls would refuse one too. This wrapper edits
nothing in it. For the duration of one `main` call (a context manager restores everything, also on an error) it rebinds, inside posthoc_lanes_v33, `c3` to
celf_v3_5, `s3` to score_test_v3_5 (same attribute surface: `main`, `sha256`, `cv`, `c2`, `PINNED_PLACEMENTS`, `score`, `s2`) and `check_readout_pins` to the
v3.5 version below (v3.5 layer by celf_v3_5, v3.3 layer by celf_v3_3 on the v3.3 view; the v3.2 layer is checked inside both celf_v3_5.main and
score_test_v3_5.score). Every number is therefore produced by posthoc_lanes_v33's own code, unchanged: the decision-73 rerun (which must equal the frozen
placement's `rates`), the zero-alarm repricing, the scoring with no pass rule, and the lane predictions F-L1, F-L2, F-L3, F-M (the declared FNL-L1..FNL-M are
`as F-L1` ... `as F-M`, PREDICTIONS_OVERNIGHT_20261014.json; F-L3 reads `—` when no lag id is in the calibration, as FNL-L3 declares). Only the `otel`
command is available; the `teastore` command is refused. Both readouts must be readouts of the ablation epoch alone (v32.epochsRead names
otel-offpath-f-nolag-v1 and nothing else); the placement must be a celf_v3_5 output (its version is checked by score_test_v3_5.check_placement).

OUTPUT. posthoc_lanes_v33 writes <out-dir>/posthoc_lanes_v33_otel.json and .md (its names; its `inputs.script` says posthoc_lanes_v33.py). Beside them this
wrapper writes <out-dir>/posthoc_lanes_v35_provenance.json: the wrapper, the rebinding, the digests of the files that carry the chain, and the readouts' epochs.
Scope: instance; POST HOC, not a preregistered verdict.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (REPO / "research" / "placement", REPO / "research" / "detection-time", REPO / "research" / "placement" / "test-f-nolag", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import celf_v3_3 as c3  # noqa: E402  frozen; only its v3.3 layer check is called
import celf_v3_5 as c5  # noqa: E402
import posthoc_lanes_v33 as pl  # noqa: E402  imported, never edited
import score_nolag as sn  # noqa: E402  (check_ablation_only: the ablation-epoch-alone readout test)
import score_test_v3_5 as s5  # noqa: E402

VERSION = "posthoc-lanes-v35-wrapper-v1"
SCRIPT = "research/lanes/posthoc_lanes_v35.py"


def refuse(msg):
    raise SystemExit("refusing: " + msg)


def check_readout_pins35(J, what):
    """The frozen v3.5 reader and registry digests (v3.5 layer), then the v3.3 layer on the v3.3 view; pins enforced, no --allow-unpinned."""
    c5.check_v35_layer(J, what, False)
    c3.check_v33_layer(c5.v33_view(J), what, False)


@contextlib.contextmanager
def v35_chain():
    """posthoc_lanes_v33's c3, s3 and check_readout_pins rebound to the v3.5 chain for the duration of the block."""
    saved = (pl.c3, pl.s3, pl.check_readout_pins)
    pl.c3, pl.s3, pl.check_readout_pins = c5, s5, check_readout_pins35
    try:
        yield
    finally:
        pl.c3, pl.s3, pl.check_readout_pins = saved


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != "otel":
        refuse("only the `otel` command is available (the TeaStore command is posthoc_lanes_v33's and reads v3.3 readouts)")
    pre = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    for opt in ("--training-readout", "--scoring-readout", "--placement", "--out-dir"):
        pre.add_argument(opt)
    known, _ = pre.parse_known_args(argv[1:])
    for opt, v in (("--training-readout", known.training_readout), ("--scoring-readout", known.scoring_readout)):
        if v is None or not Path(v).is_file():
            refuse("%s %s is not a file" % (opt, v))
        if hashlib.sha256(Path(v).read_bytes()).hexdigest() in sn.F_READOUT_SHA256:
            refuse("%s %s is a byte copy of a committed F readout" % (opt, v))
        sn.check_ablation_only(v, opt.lstrip("-").replace("-", " "))
    with v35_chain():
        rc = pl.main(argv)
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731
    rec = {"version": VERSION, "scope": "instance", "label": "POST HOC (not a preregistered verdict); posthoc_lanes_v33 otel over v3.5 readouts",
           "rebound": {"module": "posthoc_lanes_v33", "c3": "celf_v3_5", "s3": "score_test_v3_5", "check_readout_pins": "posthoc_lanes_v35.check_readout_pins35"},
           "inputs": {"trainingReadoutSha256": sha(known.training_readout), "scoringReadoutSha256": sha(known.scoring_readout),
                      "placementSha256": sha(known.placement)},
           "fileDigests": {"research/lanes/posthoc_lanes_v33.py": sha(pl.__file__), "research/placement/celf_v3_5.py": sha(c5.__file__),
                           "research/placement/score_test_v3_5.py": sha(s5.__file__), "research/detection-time/sweep_analysis_v3_5.py": sha(c5.READER_V35),
                           "research/protocol/parameters_v3_5.json": sha(c5.PARAMETERS_V35),
                           "script": SCRIPT, "scriptSha256": sha(__file__)},
           "pins": {"pinnedV35": c5.PINNED_V35_SHA256, "pinnedParametersV35": c5.PINNED_PARAMETERS_V35_SHA256,
                    "pinnedV33": c5.c3.PINNED_V33_SHA256, "scorerPinnedPlacements": dict(s5.PINNED_PLACEMENTS)},
           "argv": argv, "python": sys.version}
    with open(Path(known.out_dir) / "posthoc_lanes_v35_provenance.json", "x", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, indent=1, sort_keys=True))
    print("wrote", Path(known.out_dir) / "posthoc_lanes_v35_provenance.json")
    return rc


if __name__ == "__main__":
    sys.exit(main())
