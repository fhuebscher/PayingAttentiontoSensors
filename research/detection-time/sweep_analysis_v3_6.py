#!/usr/bin/env python3
"""Traffic-sweep analysis v3.6: v3.3's reader and rules (sweep_analysis_v3_3.py, frozen, imported and never edited) with the TeaStore
off-path epoch `teastore-offpath-v1` admitted as a campaign-E-role epoch (R1, research/traffic-sweep/BUDGET_TS_PLACEMENT_20261015.md).
Admission only.

    uv run python research/detection-time/sweep_analysis_v3_6.py <campaign dir> --system teastore \
        --out <new dir> [--blocks 1 2 3] [--split research/protocol/split_ts_offpath.json] [--test-blocks 4 5]

STATUS: FROZEN by digest (research/protocol/FREEZE_V36_20261015.md) before any cell of the R1 run exists. The only real cells read while
v3.6 was written are those of TeaStore off-path replication 2 (tmp/teastore-offpath-evidence/rep2-fetch), which was read and reported
before (RESULT_TS_OFFPATH_REP2.md); its use here is a dry run of the wiring, post hoc, no verdict. Every claim below is scope
**method**; no number is produced by this file.

ENGINEERING CHOICE (recorded): like v3.5 over v3.3, v3.6 is a module of its own. It imports v3.3 (`import sweep_analysis_v3_3 as v33`)
and, for the duration of one run, rebinds THREE names (a context manager restores them). (1) v3.3's `ADDED_PROFILES`, to v3.3's table with its `teastore-offpath-v1` entry
replaced by the one profile of parameters_v3_6.json, which differs from v3.3's entry in exactly one key, `role` (offpath-teastore ->
campaign-E; asserted at import). v3.2 selects campaign-E epochs by that key alone (`e_epochs`), so the epoch then gets v3.2's block
selection (V32_BLOCK_SELECT_RULE), held-out test blocks with train-only calibration (decision 102), the one-new-epoch refusal and the
split check against V32_E_SPLIT (1-3 / 4-5), exactly as E and F. (2) v3.2's `_read_block`, the receipt reader behind block selection
and the held-out flag: v3.2 reads (studyEpoch, block) from the receipt's `runKey`, which OTel receipts carry and TeaStore receipts do not
(a TeaStore receipt has a top-level `studyEpoch` and `run.block`). The v3.6 version returns v3.2's answer whenever the receipt has a
`runKey`, and for a receipt without one whose top-level studyEpoch is `teastore-offpath-v1` it returns (studyEpoch, run.block); every
other receipt gets v3.2's (None, None) as before. Without (2) the selection never sees a TeaStore cell and v3.2 refuses `--blocks`
(observed on replication 2). (3) v3.3's `_ORIG_CTX` (its handle on v3.2's `v32_context`), so that for system teastore v3.2's
decision-102 train-only hooks are installed as they are for otel: v3.2 installs its eight `_train(cells)` wrappers (fits_for3,
loco_fits3, the v2.4 reference loco_fits and operating_point, pair_fits, calibrate, validation, make_ctx) only under `system == "otel"`,
so a TeaStore read with `--test-blocks` would flag the test cells heldOut and still calibrate on them (observed on replication 2: the
scoring readout's calibration had 5 no-fault cells per rate, the training readout's 3, and score_test_v3_2 refused it, decision 102).
The wrappers are v3.2's own functions, unchanged and system-agnostic (make_ctx32 adds OTel edges only under v24.SYSTEM == "otel"); none
of v3.2's OTel-only rebindings (ledger kind, OTel ledger and loader, path_of, pause regime, eval_episode3, exposure, P1/P2) is
installed. No v3.3 function is replaced, no rule changed: decision 102 now applies to this epoch as it does to E and F. A v3.6 readout carries
scriptSha256 of THIS file, v33ScriptSha256 of v3.3, v32ScriptSha256 of v3.2 and v31ScriptSha256 of v3.1, keeps v3.3's `v32` and `v33`
blocks, and adds a `v36` block.

DEVIATIONS FROM v3.3. A group not listed did not change (calibration, level rules, `absent`/`appear`, cost model, lane rules, the
TeaStore shape, target and pause-pair checks of v3.3's 8.4).
  Group 8 epoch admission (V36_EPOCH_PROFILES; switches ADMIT_TS_E, TEASTORE_ONLY, TS_BLOCK_FROM_RUN, TS_TRAIN_ONLY):
     8.8 TeaStore `teastore-offpath-v1` is read as a campaign-E-role epoch (regimes no-fault-cost, recommender-pause-effect,
         auth-freeze-effect; rates 10 and 1 req/s; one no-fault cell per block and rate). Any system but teastore is refused
         (TEASTORE_ONLY: OTel's epochs are v3.3's and v3.5's, Hotel's v3.4's).
     8.9 the block of a TeaStore off-path cell is its receipt's run.block (TS_BLOCK_FROM_RUN; see (2) above).
     8.10 decision 102's train-only calibration is installed for TeaStore (TS_TRAIN_ONLY; see (3) above).
The pass rule this epoch is scored under (V36_PASS_RULE) lives in the same registry and is applied by score_test_v3_6.py, not here.
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

PARAMETERS_V36 = REPO / "research" / "protocol" / "parameters_v3_6.json"
VERSION = "3.6"
OUT_MD, OUT_JSON = "SWEEP_ANALYSIS_V3_6.md", "sweep_analysis_v3_6.json"
LABEL = "frozen v3.6 for the TeaStore off-path epoch teastore-offpath-v1 as a campaign-E-role epoch (FREEZE_V36_20261015.md)"
EPOCH = "teastore-offpath-v1"


# =========================================================================== the v3.6 registry (decision 37)

def load_registry(path=PARAMETERS_V36):
    doc = json.loads(Path(path).read_text())
    return {p["name"]: p for p in doc["parameters"]}


REGISTRY36 = load_registry()
PARAMS_USED36 = set()


def param36(name):
    PARAMS_USED36.add(name)
    return REGISTRY36[name]["value"]


TS_E_PROFILES = param36("V36_EPOCH_PROFILES")
SPLIT36 = param36("V36_SPLIT")
V33_ADDED = dict(v33.ADDED_PROFILES)         # v3.3's table as frozen, captured before any rebinding
assert set(TS_E_PROFILES) == {EPOCH} and EPOCH in V33_ADDED, "v3.6 re-admits exactly v3.3's TeaStore off-path epoch"
assert {k: v for k, v in TS_E_PROFILES[EPOCH].items() if k != "role"} == {
    k: v for k, v in V33_ADDED[EPOCH].items() if k != "role"}, "v3.6 changes only the epoch's role"
assert TS_E_PROFILES[EPOCH]["role"] == "campaign-E" and V33_ADDED[EPOCH]["role"] != "campaign-E"
assert SPLIT36 == v32.E_SPLIT, "v3.6's split is V32_E_SPLIT"

# Switches flipped only by tests/test_sweep_analysis_v3_6.py (planted defects); the analysis never changes them.
ADMIT_TS_E = True         # 8.8: the epoch is read as campaign-E (False: v3.3's lanes-only role, so --blocks is refused)
TEASTORE_ONLY = True      # 8.8: any system but teastore is refused (False: passed to v3.3's engine)
TS_BLOCK_FROM_RUN = True  # 8.9: a TeaStore off-path receipt's block is run.block (False: v3.2's runKey-only reader, no block seen)
TS_TRAIN_ONLY = True      # 8.10: v3.2's train-only hooks are installed for teastore (False: held-out cells calibrate, as in v3.2)
SWITCHES = ("ADMIT_TS_E", "TEASTORE_ONLY", "TS_BLOCK_FROM_RUN", "TS_TRAIN_ONLY")


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def admitted_profiles():
    """v3.3's added-epoch table with the TeaStore off-path entry's role set to campaign-E (a new dict; v3.3's is never edited)."""
    merged = dict(V33_ADDED)
    if ADMIT_TS_E:
        merged.update(TS_E_PROFILES)
    return merged


_ORIG_READ_BLOCK = v32._read_block


def read_block36(d):
    """v3.2's (studyEpoch, block) of a cell's receipt, with the TeaStore off-path receipt's run.block (8.9)."""
    epoch, block = _ORIG_READ_BLOCK(d)
    if epoch is not None or not TS_BLOCK_FROM_RUN:
        return epoch, block
    try:
        rc = v32._ORIG["read_json"](Path(d) / "receipt.json")
    except (OSError, ValueError):
        return None, None
    if not isinstance(rc, dict) or rc.get("runKey") is not None or rc.get("studyEpoch") not in TS_E_PROFILES:
        return epoch, block
    blk = (rc.get("run") or {}).get("block")
    return (rc["studyEpoch"], blk) if isinstance(blk, int) and not isinstance(blk, bool) else (None, None)


# v3.2's decision-102 wrappers: (module, name, wrapper). Exactly the eight `_train(cells)` hooks v3.2 installs for otel.
TRAIN_ONLY_HOOKS = ((v31, "fits_for3", v32.fits_for3_32), (v31, "loco_fits3", v32.loco_fits3_32),
                    (v24, "loco_fits", v32.loco_fits_reference_32), (v24, "operating_point", v32.operating_point_32),
                    (v31, "pair_fits", v32.pair_fits_32), (v31, "calibrate", v32.calibrate32),
                    (v31, "validation", v32.validation32), (v24, "make_ctx", v32.make_ctx32))
_ORIG_V33_CTX = v33._ORIG_CTX


@contextlib.contextmanager
def v32_context36(system, rates=None, blocks=None, test_blocks=None):
    """v3.2's context; for system teastore, plus v3.2's train-only hooks (8.10), restored on exit."""
    saved = []
    try:
        with _ORIG_V33_CTX(system, rates, blocks, test_blocks) as st:
            if system == "teastore" and TS_TRAIN_ONLY:
                for mod, name, fn in TRAIN_ONLY_HOOKS:
                    saved.append((mod, name, getattr(mod, name)))
                    setattr(mod, name, fn)
            yield st
    finally:
        for mod, name, val in reversed(saved):
            setattr(mod, name, val)


@contextlib.contextmanager
def _v36_wrapped():
    """v3.3's `ADDED_PROFILES` and `_ORIG_CTX` and v3.2's `_read_block` are the three names rebound; all are read by module name
    at call time."""
    prev, prev_rb, prev_ctx = v33.ADDED_PROFILES, v32._read_block, v33._ORIG_CTX
    v33.ADDED_PROFILES = admitted_profiles()
    v32._read_block = read_block36
    v33._ORIG_CTX = v32_context36
    try:
        yield
    finally:
        v33.ADDED_PROFILES, v32._read_block, v33._ORIG_CTX = prev, prev_rb, prev_ctx


# =========================================================================== whole run

def run36(campaign, system="teastore", validation_dirs=(), reference=True, blocks=None, split=None, test_blocks=None):
    """v3.3's run33 with the TeaStore off-path epoch read as campaign-E. Returns v3.3's result dict plus R["_v36ctx"]."""
    if TEASTORE_ONLY and system != "teastore":
        raise SystemExit("refusing: --system %s: v3.6 admits one TeaStore epoch and reads TeaStore only (OTel's epochs are read by "
                         "v3.3 and v3.5, Hotel's by v3.4)" % system)
    with _v36_wrapped():
        R = v33.run33(campaign, system=system, validation_dirs=validation_dirs, reference=reference, blocks=blocks,
                      split=split, test_blocks=test_blocks)
    R["_v36ctx"] = {"system": system}
    return R


def _v36_block(R):
    read = dict(R["v32"]["epochsRead"])
    return {"version": VERSION, "label": LABEL, "system": R["_v36ctx"]["system"],
            "epochsReadmittedByV36": sorted(TS_E_PROFILES) if ADMIT_TS_E else [],
            "epochsRead": read, "campaignEEpochsRead": sorted(e for e in TS_E_PROFILES if e in read and ADMIT_TS_E),
            "switches": {k: globals()[k] for k in SWITCHES},
            "parametersV36Sha256": _sha(PARAMETERS_V36),
            "parametersV36": {n: REGISTRY36[n]["value"] for n in sorted(PARAMS_USED36)}}


def build_json36(R):
    with _v36_wrapped():
        J = v33.build_json33(R)
        blk = _v36_block(R)
    J["v33ScriptSha256"] = J["scriptSha256"]
    J["version"], J["label"] = VERSION, LABEL
    J["script"] = "research/detection-time/sweep_analysis_v3_6.py"
    J["scriptSha256"] = _sha(__file__)
    J["v36"] = blk
    return J


def render36(R, J):
    with _v36_wrapped():
        md = v33.render33(R, J)
    v = J["v36"]
    w = ["", "## v3.6 additions (TeaStore off-path epoch read as campaign-E; admission only)", "",
         "Frozen v3.6 (FREEZE_V36_20261015.md). Scope: instance; a report, no mechanism claim.", "",
         "- Epoch re-admitted as campaign-E by v3.6: %s." % (", ".join("`%s`" % e for e in v["epochsReadmittedByV36"]) or DASH),
         "- Campaign-E epoch read: %s." % (", ".join("`%s`" % e for e in v["campaignEEpochsRead"]) or DASH), ""]
    return md + "\n".join(w) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("campaign", nargs="+", help="fetched campaign directory/ies of one system (pooled, H1)")
    ap.add_argument("--system", default="teastore", choices=v24.SYSTEMS)
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
    R = run36(camp[0] if len(camp) == 1 else camp, system=a.system, validation_dirs=[Path(x) for x in a.validation],
              blocks=set(a.blocks) if a.blocks is not None else None, split=a.split,
              test_blocks=set(a.test_blocks) if a.test_blocks is not None else None)
    with v24.use_system(a.system):
        v31.finish(R)
    J = build_json36(R)
    out.mkdir(parents=True)
    v31.write_new(out / OUT_JSON, json.dumps(J, indent=1, sort_keys=True, default=sorted))
    v31.write_new(out / OUT_MD, render36(R, J))
    print("wrote", out / OUT_JSON, out / OUT_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
