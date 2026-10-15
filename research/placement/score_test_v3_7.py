#!/usr/bin/env python3
"""Hotel off-path block-split scorer: score_test_v3_2's frozen-set scoring on the TEST blocks, over a v3.7 readout. A thin wrapper,
score_test_v3_6's twin for Hotel.

    uv run python research/placement/score_test_v3_7.py <v3.7 readout covering the test blocks> \
        --placement <frozen celf_v3_7 output> --training-readout <the placement's input readout> \
        --test-blocks 4 5 --out <NEW file.json> [--allow-unpinned]

STATUS: FROZEN with the v3.7 reader, registry and celf_v3_7.py (research/protocol/FREEZE_V37_20261015.md, step 1); the reader and
registry pins are celf_v3_7's (mirrored below). PINNED_PLACEMENTS stays EMPTY until a Hotel training placement exists: it is pinned by a
one-line commit recorded as step 2 of the freeze record, before any test-block cell of that run is read. Scope: **instance**.

Nothing of the scoring is changed: `score_test_v3_2` is imported and its `score`, `score_rate`, `check_split` and markdown are used as
they are. Two things differ. (1) The INPUT checks accept a v3.7 readout and a celf_v3_7 placement. (2) The PASS RULE passed to
`score_test_v3_2.score` is the v3.7 registry's V37_PASS_RULE (class consul-pause-effect, at rate 10 and at rate 1 separately, set
`frontier (effort<=any, runtime<=any) @6/T_r`, minGain null, minImprovedEpisodes 2, minEpisodes 2), not v3.2's, whose classes are OTel's
(RULE_FROM_V37; the registry digest is recorded in the output inputs). search-pause-effect carries no verdict.
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
import celf_v3_7 as c7  # noqa: E402
import score_test_v3_2 as s2  # noqa: E402  frozen with the v3.2 chain; imported, never edited

VERSION = "score-test-v3.7"
PINNED_V37_SHA256 = c7.PINNED_V37_SHA256                      # mirrors of celf_v3_7's pins (one source; a test asserts equality)
PINNED_PARAMETERS_V37_SHA256 = c7.PINNED_PARAMETERS_V37_SHA256
PINNED_PLACEMENTS = {"hotel": "625d2b8bff3b90cfa8a57aefd001a5f1345be812eee0fcf9e1fbbf2149c1854d"}   # R3 training placement (step 2 of FREEZE_V37_20261015.md)
ENFORCE_PINS = True                      # False planted by tests: the v3.7 placement checks are not made
RULE_FROM_V37 = True                     # False planted by tests: v3.2's OTel-class rule is used (no Hotel class, no verdict)

refuse, sha256 = s2.refuse, s2.sha256


def check_readout(J, allow_unpinned=False):
    """A v3.7 scoring readout: the v3.7 layer (celf_v3_7), the v3.3 layer (celf_v3_3), then the v3.2 layer and the reader digests."""
    c7.check_v37_layer(J, "the scoring readout", allow_unpinned)
    c3.check_v33_layer(c7.v33_view(J), "the scoring readout", allow_unpinned)
    return _ORIG_CHECK_READOUT(c3.v32_view(c7.v33_view(J)), allow_unpinned)


def check_placement(P, psha, J, allow_unpinned=False):
    system = P.get("system")
    if ENFORCE_PINS:
        inp = P.get("inputs") or {}
        if inp.get("celfSha256") != c2.PINNED_CELF_SHA256:
            refuse("the placement was not produced with the frozen celf_v3")
        if P.get("version") != c7.VERSION:
            refuse("the placement is %r, not %s" % (P.get("version"), c7.VERSION))
        c2.check_parameters_digest(inp.get("parametersV32Sha256"), "the placement", allow_unpinned)
        c3.check_parameters_digest33(inp.get("parametersV33Sha256"), "the placement", allow_unpinned)
        c7.check_parameters_digest37(inp.get("parametersV37Sha256"), "the placement", allow_unpinned)
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
                                                         "v37.parametersV37Sha256")


@contextlib.contextmanager
def v37_inputs():
    saved = [(s2, n, getattr(s2, n)) for n in ("check_readout", "check_placement", "VERSION", "SAME_ACROSS_READOUTS")]
    s2.check_readout, s2.check_placement = check_readout, check_placement
    s2.VERSION, s2.SAME_ACROSS_READOUTS = VERSION, SAME_ACROSS_READOUTS
    try:
        yield
    finally:
        for mod, n, v in saved:
            setattr(mod, n, v)


def score(J, P, psha, test_blocks, training=None, rule=None, allow_unpinned=False):
    with v37_inputs():
        return s2.score(J, P, psha, test_blocks, training, rule, allow_unpinned)


def pass_rule():
    """V37_PASS_RULE from the v3.7 registry (RULE_FROM_V37); the planted defect returns v3.2's rule."""
    if not RULE_FROM_V37:
        return s2.pass_rule_registry()
    return json.loads(json.dumps(c7._registry37()["V37_PASS_RULE"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("readout", help="v3.7 readout whose episodes include the test blocks")
    ap.add_argument("--placement", required=True, help="frozen celf_v3_7 output")
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
                     "passRuleSource": ("V37_PASS_RULE, research/protocol/parameters_v3_7.json (the output's passRuleNote is "
                                        "score_test_v3_2's inherited label)") if RULE_FROM_V37 else "V32_PASS_RULE (planted)",
                     "parametersV37Sha256": sha256(c7.PARAMETERS_V37), "pinnedParametersV37": c7.PINNED_PARAMETERS_V37_SHA256,
                     "pinnedV37": c7.PINNED_V37_SHA256, "scoreTestV32Sha256": sha256(s2.__file__),
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
