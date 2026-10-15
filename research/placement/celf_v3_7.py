#!/usr/bin/env python3
"""Placement v3.7: celf_v3_2's tiered-budget frontier over a v3.7 readout (the Hotel off-path epoch hotel-offpath-v1 read as a
campaign-E-role epoch; the Hotel arm of R1's analysis). A thin wrapper, celf_v3_6's twin for Hotel.

    uv run python research/placement/celf_v3_7.py <v3.7 readout sweep_analysis_v3_7.json> \
        --tier-catalog postureCurrentCatalog --out <NEW file.json> \
        --split research/protocol/split_hotel_offpath.json [--declared <comparator sets json>] [--allow-unpinned] [--allow-unsplit]

STATUS: FROZEN with the v3.7 reader and registry (research/protocol/FREEZE_V37_20261015.md); its own digest is recorded there.
PINNED_V37_SHA256 and PINNED_PARAMETERS_V37_SHA256 are the digests of sweep_analysis_v3_7.py and parameters_v3_7.json at that freeze;
PINNED_V34_SHA256 is the frozen v3.4 reader's (FREEZE_V34_20261015.md), which a v3.7 readout records as v34ScriptSha256. Scope of every
number: **instance**.

Nothing of the objective, the recurrence rule or the frontier is changed: `celf_v3_2` is imported and its `run`, `check_frozen_celf`,
`check_split_registry` are used as they are, and `celf_v3_3`'s input layers are reused as they are. What v3.7 changes is what the INPUT
checks accept: a v3.7 readout of system hotel, checked in its v3.7 layer here (version "3.7", the reader's digest, the v3.4 reader's
digest, the v3.7 registry digest; pinned), its v3.3 layer by celf_v3_3.check_v33_layer on a view that presents its v3.3 identity (v3.4
readouts record v3.3's digest as v33ScriptSha256 and keep v3.3's `v33` block), and its v3.2 layer by celf_v3_2.check_readout.

ENGINEERING DEFAULT, TIERS (recorded; registry V37_TIERS_RULE): as celf_v3_6 for Hotel. Hotel has no tier file in celf_v3_2's schema
and none is invented: `--tiers` is not taken, every candidate is tiersMissingForGroundSet, only the (effort<=any, runtime<=any) cell
admits it; the pass rule (V37_PASS_RULE) names that cell.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import celf_v3 as cv  # noqa: E402  frozen
import celf_v3_2 as c2  # noqa: E402  frozen with the v3.2 chain; imported, never edited
import celf_v3_3 as c3  # noqa: E402  frozen with the v3.3 chain; imported, never edited

VERSION = "placement-v3.7"
PINNED_V37_SHA256 = "c657d976332c29900c09ea885be73c7351d3a716ed171333d28906a756eaa97b"   # the frozen v3.7 reader (FREEZE_V37_20261015.md)
PINNED_PARAMETERS_V37_SHA256 = "44b489575b7637270edb31405d9fe941b000ba09e6e0c35cd1bd7b68407a1a4f"   # the frozen v3.7 registry (FREEZE_V37_20261015.md)
PINNED_V34_SHA256 = "caad8672867b165910bbd0dc15090aee1e67ddaded0f2daffee7410cb2b3410d"   # the frozen v3.4 reader (FREEZE_V34_20261015.md)
PARAMETERS_V37 = REPO / "research" / "protocol" / "parameters_v3_7.json"
READER_V37 = REPO / "research" / "detection-time" / "sweep_analysis_v3_7.py"
CHECK_PINS = True                        # False planted by tests: the v3.7 layer is not checked
HOTEL_ONLY = True                     # False planted by tests: a readout of another system is placed
NO_TIER_FILE = True                      # False planted by tests: the empty tier table is replaced by a fake effort-0 tier for every sensor

refuse, sha256 = c2.refuse, c2.sha256


def _registry37():
    return {p["name"]: p["value"] for p in json.loads(PARAMETERS_V37.read_text())["parameters"]}


def check_parameters_digest37(recorded, what, allow_unpinned=False):
    """c3.check_parameters_digest33 for the v3.7 registry (parameters_v3_7.json)."""
    live = sha256(PARAMETERS_V37)
    pin = PINNED_PARAMETERS_V37_SHA256
    if pin is not None and live != pin:
        refuse("the live registry %s has sha256 %s, not the frozen %s" % (PARAMETERS_V37.name, live, pin))
    if pin is None and not allow_unpinned:
        refuse("the v3.7 registry is not frozen (PINNED_PARAMETERS_V37_SHA256 is None): --allow-unpinned for exploration")
    want = pin or live
    if recorded != want:
        refuse("%s recorded parametersV37Sha256 %r is not %s %s" % (what, recorded, "the frozen" if pin else "the live", want))


def check_v37_layer(J, what, allow_unpinned=False):
    """The v3.7 layer of a v3.7 readout: version, the reader's digest, the registry digest."""
    if J.get("version") != "3.7":
        refuse("%s is not v3.7 (version %r); celf_v3_3.py takes v3.3 readouts" % (what, J.get("version")))
    if not CHECK_PINS:
        return
    want = PINNED_V37_SHA256 or sha256(READER_V37)
    if J.get("scriptSha256") != want:
        refuse("%s scriptSha256 %r is not %s %s" % (what, J.get("scriptSha256"), "the frozen v3.7" if PINNED_V37_SHA256
                                                    else "the installed reader", want))
    if PINNED_V37_SHA256 is None and not allow_unpinned:
        refuse("the v3.7 reader is not frozen (PINNED_V37_SHA256 is None): --allow-unpinned for exploration")
    if J.get("v34ScriptSha256") != PINNED_V34_SHA256:
        refuse("%s v34ScriptSha256 %r is not the frozen v3.4 reader %s" % (what, J.get("v34ScriptSha256"), PINNED_V34_SHA256))
    check_parameters_digest37((J.get("v37") or {}).get("parametersV37Sha256"), what, allow_unpinned)


def v33_view(J):
    """The readout as a v3.3 readout (its v3.3 identity), for celf_v3_3's own checks (which take the v3.2 view of it in turn)."""
    return dict(J, version="3.3", scriptSha256=J.get("v33ScriptSha256"))


def check_readout(J, allow_unpinned=False, allow_unsplit=False):
    """A v3.7 readout: its v3.7 layer here, its v3.3 layer and v3.2 layer by celf_v3_3.check_readout (every earlier pin applies)."""
    check_v37_layer(J, "the readout", allow_unpinned)
    return c3.check_readout(v33_view(J), allow_unpinned, allow_unsplit)


def expected_catalog(J):
    """The off-path epochs (v3.2's, v3.3's and v3.7's registries) call for the current runtime catalog, others for the v3 one."""
    if c3.expected_catalog(v33_view(J)) == "postureCurrentCatalog":
        return "postureCurrentCatalog"
    epochs = ((J.get("v32") or {}).get("epochsRead") or {})
    return "postureCurrentCatalog" if any(e in _registry37()["V37_EPOCH_PROFILES"] for e in epochs) else "postures"


def no_tiers(J, catalog):
    """The empty tier table (V37_TIERS_RULE) and its meta; NO_TIER_FILE False (planted) gives every ground-set sensor effort 0."""
    meta = {"path": None, "sha256": None, "system": J.get("system"), "sensors": 0, "catalog": catalog,
            "rule": _registry37()["V37_TIERS_RULE"]}
    if NO_TIER_FILE:
        return {}, meta
    ids = {s for r in sorted({e["rate"] for e in J["episodes"]}) for s in cv.ground_set(J, r)[0]}
    return {s: {"effort": 0, "runtime": "<1%", "runtimeBasis": "planted", "firstPosture": None, "cumulativeShare": None}
            for s in ids}, dict(meta, planted=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("readout", help="v3.7 readout JSON (sweep_analysis_v3_7.json), read with --blocks <training>")
    ap.add_argument("--tier-catalog", required=True, choices=c2.TIERS["postureCatalogs"])
    ap.add_argument("--out", required=True, help="NEW output file; refused if it exists")
    ap.add_argument("--declared", help="JSON {comparator name: [sensor ids] | null} (decision 78)")
    ap.add_argument("--split", help="the declared split file {train: [...], test: [...]} (checked against the readout)")
    ap.add_argument("--allow-unpinned", action="store_true")
    ap.add_argument("--allow-unsplit", action="store_true")
    ap.add_argument("--allow-catalog-mismatch", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists() or out.is_symlink():
        refuse("to write into an existing path: %s" % out)
    celf_sha = c2.check_frozen_celf()
    J = json.loads(Path(a.readout).read_text())
    blocks = check_readout(J, a.allow_unpinned, a.allow_unsplit)
    if HOTEL_ONLY and J.get("system") != "hotel":
        refuse("the readout's system is %r: celf_v3_7 places the Hotel off-path epoch only" % J.get("system"))
    if c2.CHECK_PINS and expected_catalog(J) != a.tier_catalog and not a.allow_catalog_mismatch:
        refuse("--tier-catalog %s, but the readout's epochs call for %s (the two catalogs disagree on 183 ids): "
               "--allow-catalog-mismatch to override" % (a.tier_catalog, expected_catalog(J)))
    if c2.REQUIRE_SPLIT and not a.split and not a.allow_unsplit:
        refuse("--split is required: decision 95 fixes the training and test blocks before launch and the scorer "
               "checks its test blocks against the placement's recorded split")
    split = None
    if a.split:
        split = json.loads(Path(a.split).read_text())
        if set(split.get("train") or []) & set(split.get("test") or []):
            refuse("the split's train and test blocks overlap")
        c2.check_split_registry(split)
        if blocks is not None and sorted(blocks) != sorted(split.get("train") or []):
            refuse("the readout's blocks %s are not the split's training blocks %s" % (sorted(blocks), split.get("train")))
        sha = ((J.get("v32") or {}).get("blockSelection") or {}).get("splitSha256")
        if sha is not None and sha != sha256(a.split):
            refuse("the split file's sha256 is not the one the readout recorded")
    tiers, meta = no_tiers(J, a.tier_catalog)
    dec = json.loads(Path(a.declared).read_text()) if a.declared else None
    res = {"version": VERSION, "scope": c2.SCOPE, "system": J.get("system"),
           "split": {"trainBlocks": sorted(blocks) if blocks is not None else None,
                     "test": (split or {}).get("test"), "unsplit": blocks is None},
           "recurrenceRule": dict(c2.RECURRENCE_RULE, switch=c2.RECURRENCE_FILTER),
           "tiers": meta, "caps": {"effort": list(c2.EFFORT_CAPS), "runtime": list(c2.RUNTIME_CAPS)},
           "switches": {k: getattr(c2, k) for k in c2.SWITCHES}, "celfSwitches": {k: getattr(cv, k) for k in cv.SWITCHES},
           "rates": c2.run(J, tiers, dec),
           "inputs": {"readout": str(a.readout), "readoutSha256": sha256(a.readout), "tiers": None,
                      "tiersSha256": None, "declared": a.declared,
                      "declaredSha256": sha256(a.declared) if a.declared else None, "celfSha256": celf_sha,
                      "parametersV32Sha256": sha256(c2.PARAMETERS_V32), "pinnedV32": c2.PINNED_V32_SHA256,
                      "pinnedParametersV32": c2.PINNED_PARAMETERS_V32_SHA256,
                      "parametersV33Sha256": sha256(c3.PARAMETERS_V33), "pinnedV33": c3.PINNED_V33_SHA256,
                      "pinnedParametersV33": c3.PINNED_PARAMETERS_V33_SHA256, "celfV32Sha256": sha256(c2.__file__),
                      "celfV33Sha256": sha256(c3.__file__),
                      "parametersV37Sha256": sha256(PARAMETERS_V37), "pinnedV37": PINNED_V37_SHA256,
                      "pinnedParametersV37": PINNED_PARAMETERS_V37_SHA256,
                      "script": str(Path(__file__).resolve().relative_to(REPO)), "scriptSha256": sha256(__file__),
                      "python": sys.version}}
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as fh:
        fh.write(json.dumps(res, indent=1, sort_keys=True, allow_nan=False))
    print("wrote", out)                                    # no number printed: committed unedited before reading
    return 0


if __name__ == "__main__":
    sys.exit(main())
