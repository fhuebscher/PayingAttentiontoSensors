#!/usr/bin/env python3
"""Placement v3.5: celf_v3_2's tiered-budget frontier over a v3.5 readout (the OTel F ablation epoch otel-offpath-f-nolag-v1). A thin wrapper.

    uv run python research/placement/celf_v3_5.py <v3.5 readout sweep_analysis_v3_5.json> \
        --tiers research/placement/declared/otel.effort.json --tier-catalog postureCurrentCatalog --out <NEW file.json> \
        --split research/protocol/split_f_otel.json [--declared <comparator sets json>] [--allow-unpinned] [--allow-unsplit]

STATUS: FROZEN with the v3.5 reader and registry (research/protocol/FREEZE_V35_20261015.md); its own digest is recorded there.
PINNED_V35_SHA256 and PINNED_PARAMETERS_V35_SHA256 are the digests of sweep_analysis_v3_5.py and parameters_v3_5.json at that
freeze (the scorer reads them from here). Scope of every number: **instance**.

Nothing of the objective, the tiers, the recurrence rule or the frontier is changed: `celf_v3_2` is imported and its `run`,
`load_tiers`, `check_frozen_celf`, `check_split_registry` are used as they are, and `celf_v3_3`'s input layers are reused as they are.
What v3.5 changes is what the INPUT checks accept: a v3.5 readout (sweep_analysis_v3_5.py) instead of a v3.3 one. A v3.5 readout is
checked in three layers: its v3.5 layer here (version "3.5", the reader's digest, the v3.5 registry digest; pinned, a pin set to None
would need --allow-unpinned and the installed files), its v3.3 layer by celf_v3_3.check_v33_layer on a view that presents its v3.3
identity (version "3.3", scriptSha256 = the v33ScriptSha256 it records), and its v3.2 layer by celf_v3_2.check_readout (through
celf_v3_3.check_readout), so every v3.1, v3.2 and v3.3 pin applies unchanged. `main` below is celf_v3_3.main's body with those input
checks, the placement version label (`placement-v3.5`) and the v3.5 digests recorded in `inputs`; the epoch registries consulted for the
posture catalog are v3.2's, v3.3's and v3.5's (the ablation is a campaign-E-role epoch with F's current runtime catalog).
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

VERSION = "placement-v3.5"
PINNED_V35_SHA256 = "69ec63b3e099a664ad4b75f59ece4a28b5d8ebaeeb159ef94250d2219e61509b"   # the frozen v3.5 reader (FREEZE_V35_20261015.md)
PINNED_PARAMETERS_V35_SHA256 = "d3b72bf9a255bbb5cac091c6e319485e25ea7e3759ed9e792c45f7702216977b"   # the frozen v3.5 registry (FREEZE_V35_20261015.md)
PARAMETERS_V35 = REPO / "research" / "protocol" / "parameters_v3_5.json"
READER_V35 = REPO / "research" / "detection-time" / "sweep_analysis_v3_5.py"
CHECK_PINS = True                        # False planted by tests: the v3.5 layer is not checked

refuse, sha256 = c2.refuse, c2.sha256


def _registry35():
    return {p["name"]: p["value"] for p in json.loads(PARAMETERS_V35.read_text())["parameters"]}


def check_parameters_digest35(recorded, what, allow_unpinned=False):
    """c3.check_parameters_digest33 for the v3.5 registry (parameters_v3_5.json)."""
    live = sha256(PARAMETERS_V35)
    pin = PINNED_PARAMETERS_V35_SHA256
    if pin is not None and live != pin:
        refuse("the live registry %s has sha256 %s, not the frozen %s" % (PARAMETERS_V35.name, live, pin))
    if pin is None and not allow_unpinned:
        refuse("the v3.5 registry is not frozen (PINNED_PARAMETERS_V35_SHA256 is None): --allow-unpinned for exploration")
    want = pin or live
    if recorded != want:
        refuse("%s recorded parametersV35Sha256 %r is not %s %s" % (what, recorded, "the frozen" if pin else "the live", want))


def check_v35_layer(J, what, allow_unpinned=False):
    """The v3.5 layer of a v3.5 readout: version, the reader's digest, the registry digest."""
    if J.get("version") != "3.5":
        refuse("%s is not v3.5 (version %r); celf_v3_3.py takes v3.3 readouts" % (what, J.get("version")))
    if not CHECK_PINS:
        return
    want = PINNED_V35_SHA256 or sha256(READER_V35)
    if J.get("scriptSha256") != want:
        refuse("%s scriptSha256 %r is not %s %s" % (what, J.get("scriptSha256"), "the frozen v3.5" if PINNED_V35_SHA256
                                                    else "the installed reader", want))
    if PINNED_V35_SHA256 is None and not allow_unpinned:
        refuse("the v3.5 reader is not frozen (PINNED_V35_SHA256 is None): --allow-unpinned for exploration")
    check_parameters_digest35((J.get("v35") or {}).get("parametersV35Sha256"), what, allow_unpinned)


def v33_view(J):
    """The readout as a v3.3 readout (its v3.3 identity), for celf_v3_3's own checks (which take the v3.2 view of it in turn)."""
    return dict(J, version="3.3", scriptSha256=J.get("v33ScriptSha256"))


def check_readout(J, allow_unpinned=False, allow_unsplit=False):
    """A v3.5 readout: its v3.5 layer here, its v3.3 layer and v3.2 layer by celf_v3_3.check_readout (every earlier pin applies)."""
    check_v35_layer(J, "the readout", allow_unpinned)
    return c3.check_readout(v33_view(J), allow_unpinned, allow_unsplit)


def expected_catalog(J):
    """The off-path epochs (v3.2's, v3.3's and v3.5's registries) call for the current runtime catalog, others for the v3 one."""
    if c3.expected_catalog(v33_view(J)) == "postureCurrentCatalog":
        return "postureCurrentCatalog"
    epochs = ((J.get("v32") or {}).get("epochsRead") or {})
    return "postureCurrentCatalog" if any(e in _registry35()["V35_EPOCH_PROFILES"] for e in epochs) else "postures"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("readout", help="v3.5 readout JSON (sweep_analysis_v3_5.json), read with --blocks <training>")
    ap.add_argument("--tiers", required=True, help="the declared effort/runtime tier file (celf_v3_2's schema)")
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
    tiers, meta = c2.load_tiers(a.tiers, a.tier_catalog)
    dec = json.loads(Path(a.declared).read_text()) if a.declared else None
    res = {"version": VERSION, "scope": c2.SCOPE, "system": J.get("system"),
           "split": {"trainBlocks": sorted(blocks) if blocks is not None else None,
                     "test": (split or {}).get("test"), "unsplit": blocks is None},
           "recurrenceRule": dict(c2.RECURRENCE_RULE, switch=c2.RECURRENCE_FILTER),
           "tiers": meta, "caps": {"effort": list(c2.EFFORT_CAPS), "runtime": list(c2.RUNTIME_CAPS)},
           "switches": {k: getattr(c2, k) for k in c2.SWITCHES}, "celfSwitches": {k: getattr(cv, k) for k in cv.SWITCHES},
           "rates": c2.run(J, tiers, dec),
           "inputs": {"readout": str(a.readout), "readoutSha256": sha256(a.readout), "tiers": a.tiers,
                      "tiersSha256": meta["sha256"], "declared": a.declared,
                      "declaredSha256": sha256(a.declared) if a.declared else None, "celfSha256": celf_sha,
                      "parametersV32Sha256": sha256(c2.PARAMETERS_V32), "pinnedV32": c2.PINNED_V32_SHA256,
                      "pinnedParametersV32": c2.PINNED_PARAMETERS_V32_SHA256,
                      "parametersV33Sha256": sha256(c3.PARAMETERS_V33), "pinnedV33": c3.PINNED_V33_SHA256,
                      "pinnedParametersV33": c3.PINNED_PARAMETERS_V33_SHA256, "celfV32Sha256": sha256(c2.__file__),
                      "celfV33Sha256": sha256(c3.__file__),
                      "parametersV35Sha256": sha256(PARAMETERS_V35), "pinnedV35": PINNED_V35_SHA256,
                      "pinnedParametersV35": PINNED_PARAMETERS_V35_SHA256,
                      "script": str(Path(__file__).resolve().relative_to(REPO)), "scriptSha256": sha256(__file__),
                      "python": sys.version}}
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as fh:
        fh.write(json.dumps(res, indent=1, sort_keys=True, allow_nan=False))
    print("wrote", out)                                    # no number printed: committed unedited before reading
    return 0


if __name__ == "__main__":
    sys.exit(main())
