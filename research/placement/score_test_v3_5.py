#!/usr/bin/env python3
"""F-ablation block-split scorer: score_test_v3_2's frozen-set scoring on the TEST blocks, over a v3.5 readout. A thin wrapper.

    uv run python research/placement/score_test_v3_5.py <v3.5 readout covering the test blocks> \
        --placement <frozen celf_v3_5 output> --training-readout <the placement's input readout> \
        --test-blocks 4 5 --out <NEW file.json> [--allow-unpinned]

STATUS: FROZEN with the v3.5 reader, registry and celf_v3_5.py (research/protocol/FREEZE_V35_20261015.md); the reader and registry pins
are celf_v3_5's (PINNED_V35_SHA256, PINNED_PARAMETERS_V35_SHA256, mirrored below). PINNED_PLACEMENTS is EMPTY: the ablation's training
placement does not exist yet. The ablation is scored through research/placement/test-f-nolag/score_nolag.py, which sets the pin to that
placement's digest for its one process and records it (as research/placement/test-f-rep1/score_rep.py does for F's replicate); nothing
here is edited for it. Scope: **instance**.

Nothing of the scoring is changed: `score_test_v3_2` is imported and its `score`, `score_rate`, `check_split`, the pass rule
(V32_PASS_RULE, per off-path class: decisions 99, 110, 112 unchanged; the ablation's classes are F's) and the markdown are used as they
are, exactly as score_test_v3_3 does for v3.3. What v3.5 changes is what the INPUT checks accept: a v3.5 readout and a celf_v3_5
placement. `score_test_v3_2.score` is run with its `check_readout`, `check_placement`, `VERSION` and `SAME_ACROSS_READOUTS` replaced for
the duration of the call (a context manager restores them): the readout is checked in its v3.5 layer (celf_v3_5), its v3.3 layer
(celf_v3_3.check_v33_layer on the v3.3 view) and its v3.2 layer plus the v24 / detection-time / v1 reader digests (the frozen v3.2 checks on
the v3.2 view); the placement must be a celf_v3_5 output of the frozen celf_v3 with the v3.2, v3.3 and v3.5 registry digests; and training
and scoring readouts must also agree on the v3.5 registry digest, the v3.3 reader digest and the v3.2 reader digest.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import celf_v3_2 as c2  # noqa: E402  frozen with the v3.2 chain
import celf_v3_3 as c3  # noqa: E402  frozen with the v3.3 chain
import celf_v3_5 as c5  # noqa: E402
import score_test_v3_2 as s2  # noqa: E402  frozen with the v3.2 chain; imported, never edited

VERSION = "score-test-v3.5"
PINNED_V35_SHA256 = c5.PINNED_V35_SHA256                      # mirrors of celf_v3_5's pins (one source; a test asserts equality)
PINNED_PARAMETERS_V35_SHA256 = c5.PINNED_PARAMETERS_V35_SHA256
PINNED_PLACEMENTS = {}                   # empty until the ablation's training placement exists (score_nolag.py's recorded override)
ENFORCE_PINS = True                      # False planted by tests: the v3.5 placement checks are not made

refuse, sha256 = s2.refuse, s2.sha256


def check_readout(J, allow_unpinned=False):
    """A v3.5 scoring readout: the v3.5 layer (celf_v3_5), the v3.3 layer (celf_v3_3), then the v3.2 layer and the reader digests."""
    c5.check_v35_layer(J, "the scoring readout", allow_unpinned)
    c3.check_v33_layer(c5.v33_view(J), "the scoring readout", allow_unpinned)
    return _ORIG_CHECK_READOUT(c3.v32_view(c5.v33_view(J)), allow_unpinned)


def check_placement(P, psha, J, allow_unpinned=False):
    system = P.get("system")
    if ENFORCE_PINS:
        inp = P.get("inputs") or {}
        if inp.get("celfSha256") != c2.PINNED_CELF_SHA256:
            refuse("the placement was not produced with the frozen celf_v3")
        if P.get("version") != c5.VERSION:
            refuse("the placement is %r, not %s" % (P.get("version"), c5.VERSION))
        c2.check_parameters_digest(inp.get("parametersV32Sha256"), "the placement", allow_unpinned)
        c3.check_parameters_digest33(inp.get("parametersV33Sha256"), "the placement", allow_unpinned)
        c5.check_parameters_digest35(inp.get("parametersV35Sha256"), "the placement", allow_unpinned)
        pin = PINNED_PLACEMENTS.get(system)
        if pin is None and not allow_unpinned:
            refuse("no pinned placement digest for %r (PINNED_PLACEMENTS): --allow-unpinned for exploration" % system)
        if pin is not None and pin != psha:
            refuse("placement sha256 %s is not the frozen %s" % (psha, pin))
    if system != J.get("system"):
        refuse("placement system %r, readout system %r" % (system, J.get("system")))


_ORIG_CHECK_READOUT = s2.check_readout
_ORIG_CHECK_PLACEMENT = s2.check_placement
SAME_ACROSS_READOUTS = tuple(s2.SAME_ACROSS_READOUTS) + ("v32ScriptSha256", "v33.parametersV33Sha256", "v33ScriptSha256",
                                                         "v35.parametersV35Sha256")


@contextlib.contextmanager
def v35_inputs():
    saved = [(s2, n, getattr(s2, n)) for n in ("check_readout", "check_placement", "VERSION", "SAME_ACROSS_READOUTS")]
    s2.check_readout, s2.check_placement = check_readout, check_placement
    s2.VERSION, s2.SAME_ACROSS_READOUTS = VERSION, SAME_ACROSS_READOUTS
    try:
        yield
    finally:
        for mod, n, v in saved:
            setattr(mod, n, v)


def score(J, P, psha, test_blocks, training=None, rule=None, allow_unpinned=False):
    with v35_inputs():
        return s2.score(J, P, psha, test_blocks, training, rule, allow_unpinned)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("readout", help="v3.5 readout whose episodes include the test blocks")
    ap.add_argument("--placement", required=True, help="frozen celf_v3_5 output")
    ap.add_argument("--training-readout", required=True, help="the placement's input readout (checked)")
    ap.add_argument("--test-blocks", nargs="+", type=int, required=True)
    ap.add_argument("--allow-unpinned", action="store_true")
    ap.add_argument("--out", required=True, help="NEW <file>.json; <file>.md beside it; refused if either exists")
    a = ap.parse_args(argv)
    out = Path(a.out)
    md = out.with_suffix(".md")
    if out.suffix != ".json":
        refuse("--out must end in .json")
    for p in (out, md):
        if p.exists() or p.is_symlink():
            refuse("to write into an existing path: %s" % p)
    J = json.loads(Path(a.readout).read_text())
    P = json.loads(Path(a.placement).read_text())
    T = json.loads(Path(a.training_readout).read_text())
    rule = s2.pass_rule_registry()                       # v3.2's registry entry, unchanged (decision 99)
    res = score(J, P, sha256(a.placement), a.test_blocks, (T, sha256(a.training_readout)), rule, a.allow_unpinned)
    res["inputs"] = {"readout": str(a.readout), "readoutSha256": sha256(a.readout), "placement": str(a.placement),
                     "placementSha256": sha256(a.placement), "trainingReadout": a.training_readout,
                     "trainingReadoutSha256": sha256(a.training_readout),
                     "parametersV32Sha256": sha256(c2.PARAMETERS_V32), "pinnedParametersV32": c2.PINNED_PARAMETERS_V32_SHA256,
                     "parametersV33Sha256": sha256(c3.PARAMETERS_V33), "pinnedParametersV33": c3.PINNED_PARAMETERS_V33_SHA256,
                     "parametersV35Sha256": sha256(c5.PARAMETERS_V35), "pinnedParametersV35": c5.PINNED_PARAMETERS_V35_SHA256,
                     "pinnedV35": c5.PINNED_V35_SHA256, "scoreTestV32Sha256": sha256(s2.__file__),
                     "script": str(Path(__file__).resolve().relative_to(REPO)), "scriptSha256": sha256(__file__),
                     "python": sys.version}
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as fh:
        fh.write(json.dumps(res, indent=1, sort_keys=True, allow_nan=False))
    with open(md, "x", encoding="utf-8") as fh:
        fh.write(s2.markdown(res))
    print("wrote", out)
    print("wrote", md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
