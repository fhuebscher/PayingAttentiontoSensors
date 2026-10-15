#!/usr/bin/env python3
"""TeaStore off-path (R1) block-split scorer: score_test_v3_2's frozen-set scoring on the TEST blocks, over a v3.6 readout. A thin wrapper.

    uv run python research/placement/score_test_v3_6.py <v3.6 readout covering the test blocks> \
        --placement <frozen celf_v3_6 output> --training-readout <the placement's input readout> \
        --test-blocks 4 5 --out <NEW file.json> [--allow-unpinned]

STATUS: FROZEN with the v3.6 reader, registry and celf_v3_6.py (research/protocol/FREEZE_V36_20261015.md, step 1); the reader and
registry pins are celf_v3_6's (mirrored below). PINNED_PLACEMENTS stays EMPTY until R1's training placement exists: the coordinator pins
its digest by a one-line commit recorded as step 2 of the freeze record, before any test-block cell of R1 is read (as F, FREEZE_V33 step
2). Scope: **instance**.

Nothing of the scoring is changed: `score_test_v3_2` is imported and its `score`, `score_rate`, `check_split` and markdown are used as
they are, exactly as score_test_v3_3 and score_test_v3_5 do. Two things differ. (1) The INPUT checks accept a v3.6 readout and a
celf_v3_6 placement (v3.6, v3.3 and v3.2 layers, as score_test_v3_5 for v3.5). (2) The PASS RULE passed to `score_test_v3_2.score` is
the v3.6 registry's V36_PASS_RULE (F's V32_PASS_RULE mapped to this epoch: class recommender-pause-effect, at rate 10 and at rate 1
separately, set `frontier (effort<=any, runtime<=any) @6/T_r`, minGain null, minImprovedEpisodes 2, minEpisodes 2), not v3.2's, whose
classes are OTel's and would give no verdict here (RULE_FROM_V36; the rule's digest is the registry's, recorded in the output inputs).
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
import celf_v3_6 as c6  # noqa: E402
import score_test_v3_2 as s2  # noqa: E402  frozen with the v3.2 chain; imported, never edited

VERSION = "score-test-v3.6"
PINNED_V36_SHA256 = c6.PINNED_V36_SHA256                      # mirrors of celf_v3_6's pins (one source; a test asserts equality)
PINNED_PARAMETERS_V36_SHA256 = c6.PINNED_PARAMETERS_V36_SHA256
PINNED_PLACEMENTS = {"teastore": "f7f5c04a6422394d2fab11b97d8ef974643afec69b37688dc359f42e7a64e8de"}                   # empty until R1's training placement exists (step 2 of FREEZE_V36_20261015.md)
ENFORCE_PINS = True                      # False planted by tests: the v3.6 placement checks are not made
RULE_FROM_V36 = True                     # False planted by tests: v3.2's OTel-class rule is used (no TeaStore class, no verdict)

refuse, sha256 = s2.refuse, s2.sha256


def check_readout(J, allow_unpinned=False):
    """A v3.6 scoring readout: the v3.6 layer (celf_v3_6), the v3.3 layer (celf_v3_3), then the v3.2 layer and the reader digests."""
    c6.check_v36_layer(J, "the scoring readout", allow_unpinned)
    c3.check_v33_layer(c6.v33_view(J), "the scoring readout", allow_unpinned)
    return _ORIG_CHECK_READOUT(c3.v32_view(c6.v33_view(J)), allow_unpinned)


def check_placement(P, psha, J, allow_unpinned=False):
    system = P.get("system")
    if ENFORCE_PINS:
        inp = P.get("inputs") or {}
        if inp.get("celfSha256") != c2.PINNED_CELF_SHA256:
            refuse("the placement was not produced with the frozen celf_v3")
        if P.get("version") != c6.VERSION:
            refuse("the placement is %r, not %s" % (P.get("version"), c6.VERSION))
        c2.check_parameters_digest(inp.get("parametersV32Sha256"), "the placement", allow_unpinned)
        c3.check_parameters_digest33(inp.get("parametersV33Sha256"), "the placement", allow_unpinned)
        c6.check_parameters_digest36(inp.get("parametersV36Sha256"), "the placement", allow_unpinned)
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
                                                         "v36.parametersV36Sha256")


@contextlib.contextmanager
def v36_inputs():
    saved = [(s2, n, getattr(s2, n)) for n in ("check_readout", "check_placement", "VERSION", "SAME_ACROSS_READOUTS")]
    s2.check_readout, s2.check_placement = check_readout, check_placement
    s2.VERSION, s2.SAME_ACROSS_READOUTS = VERSION, SAME_ACROSS_READOUTS
    try:
        yield
    finally:
        for mod, n, v in saved:
            setattr(mod, n, v)


def score(J, P, psha, test_blocks, training=None, rule=None, allow_unpinned=False):
    with v36_inputs():
        return s2.score(J, P, psha, test_blocks, training, rule, allow_unpinned)


def pass_rule():
    """V36_PASS_RULE from the v3.6 registry (RULE_FROM_V36); the planted defect returns v3.2's rule."""
    if not RULE_FROM_V36:
        return s2.pass_rule_registry()
    return json.loads(json.dumps(c6._registry36()["V36_PASS_RULE"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("readout", help="v3.6 readout whose episodes include the test blocks")
    ap.add_argument("--placement", required=True, help="frozen celf_v3_6 output")
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
    rule = pass_rule()
    res = score(J, P, sha256(a.placement), a.test_blocks, (T, sha256(a.training_readout)), rule, a.allow_unpinned)
    res["inputs"] = {"readout": str(a.readout), "readoutSha256": sha256(a.readout), "placement": str(a.placement),
                     "placementSha256": sha256(a.placement), "trainingReadout": a.training_readout,
                     "trainingReadoutSha256": sha256(a.training_readout),
                     "parametersV32Sha256": sha256(c2.PARAMETERS_V32), "pinnedParametersV32": c2.PINNED_PARAMETERS_V32_SHA256,
                     "parametersV33Sha256": sha256(c3.PARAMETERS_V33), "pinnedParametersV33": c3.PINNED_PARAMETERS_V33_SHA256,
                     "passRuleSource": ("V36_PASS_RULE, research/protocol/parameters_v3_6.json (the output's passRuleNote is "
                                        "score_test_v3_2's inherited label)") if RULE_FROM_V36 else "V32_PASS_RULE (planted)",
                     "parametersV36Sha256": sha256(c6.PARAMETERS_V36), "pinnedParametersV36": c6.PINNED_PARAMETERS_V36_SHA256,
                     "pinnedV36": c6.PINNED_V36_SHA256, "scoreTestV32Sha256": sha256(s2.__file__),
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
