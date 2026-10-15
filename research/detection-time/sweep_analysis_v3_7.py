#!/usr/bin/env python3
"""Traffic-sweep analysis v3.7: v3.4's Hotel reader (sweep_analysis_v3_4.py, frozen, imported and never edited, itself over v3.3) with the
Hotel off-path epoch `hotel-offpath-v1` read as a campaign-E-role epoch (the Hotel arm of R1's analysis; research/traffic-sweep/
BUDGET_TS_PLACEMENT_20261015.md, 2501e86, scope extension by the user 2026-10-15 ~07:30Z). Admission only. TeaStore's counterpart is v3.6
(FREEZE_V36_20261015.md); v3.7 imports v3.6 for its system-agnostic pieces and changes nothing of it.

    uv run python research/detection-time/sweep_analysis_v3_7.py <campaign dir> --system hotel \
        --out <new dir> [--blocks 1 2 3] [--split research/protocol/split_hotel_offpath.json] [--test-blocks 4 5]

STATUS: FROZEN by digest (research/protocol/FREEZE_V37_20261015.md) before any cell of a Hotel run analysed with it exists. The only real
cells read while v3.7 was written are those of the Hotel off-path run off1 (tmp/hotel-offpath-evidence/off1-fetch), read and reported
before (RESULT_HOTEL_OFFPATH.md); its use here is a dry run of the wiring, post hoc, no verdict. Every claim below is scope **method**.

ENGINEERING CHOICE (recorded): a module of its own over v3.4 and v3.3. For the duration of one run it rebinds THREE names (a context manager
restores them), the Hotel counterparts of v3.6's three:
  (1) v3.3's `ADDED_PROFILES`: v3.3's table PLUS the one profile of parameters_v3_7.json, v3.4's `hotel-offpath-v1` entry with exactly one
      key changed, `role` (offpath-hotel -> campaign-E; asserted at import). v3.4 keeps its Hotel profile out of v3.3's table, so v3.2 never
      saw the epoch; with it in, v3.2's `profiles_for("hotel")` contains it and v3.2's block selection, held-out rule, split check against
      V32_E_SPLIT (1-3 / 4-5) and one-new-epoch refusal apply, as for E, F and v3.6's TeaStore epoch.
  (2) v3.2's `_read_block`: Hotel cells have no receipt.json; their (studyEpoch, block) are the cell-contract.json `runKey`'s (v3.4's
      `_contract_run`). v3.7 returns v3.2's answer whenever it is not (None, None), and the contract's (studyEpoch, block) only for an
      epoch of this registry.
  (3) v3.3's `_ORIG_CTX`: for system hotel, v3.2's eight decision-102 train-only hooks (v3.6's `TRAIN_ONLY_HOOKS`, v3.2's functions
      unchanged) are installed, as v3.2 installs them for otel and v3.6 for teastore.
  And one driver change: v3.4's `run34` refuses `--split` and `--test-blocks` for Hotel ("held-out status keys on receipt.json, which Hotel
  cells do not have, and no registry split is declared for the off-path epoch"). Both reasons are removed by (1)-(3) and this registry, so
  `run37` is `run34`'s body (v3.4's scan, `_v34_wrapped`, v3.3's `run33`, v3.4's path check, the `_v34ctx` record) without that refusal;
  every v3.4 Hotel check (shape, target, design, epoch, legacy-cells-alone, unique cells, pause pair, path) applies unchanged.
No v3.3 or v3.4 function is replaced, no rule changed. Any system but hotel is refused. A v3.7 readout carries scriptSha256 of THIS file,
v34ScriptSha256, v33ScriptSha256 (v3.3's, as v3.4's readouts do), keeps v3.3's `v32`/`v33` and v3.4's `v34` blocks, and adds `v37`.

Switches (planted defects, tests/test_sweep_analysis_v3_7.py): ADMIT_HOTEL_E (1), HOTEL_ONLY, HOTEL_BLOCK_FROM_CONTRACT (2),
HOTEL_TRAIN_ONLY (3). The pass rule (V37_PASS_RULE) is applied by score_test_v3_7.py, not here.
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
import sweep_analysis_v3_4 as v34  # noqa: E402  v3.4 (frozen), never edited
import sweep_analysis_v3_6 as v36  # noqa: E402  v3.6 (frozen), never edited; its TRAIN_ONLY_HOOKS table is read

v33 = v34.v33
v32, v31, v24 = v33.v32, v33.v31, v33.v24
DASH = v24.DASH

PARAMETERS_V37 = REPO / "research" / "protocol" / "parameters_v3_7.json"
VERSION = "3.7"
OUT_MD, OUT_JSON = "SWEEP_ANALYSIS_V3_7.md", "sweep_analysis_v3_7.json"
LABEL = "frozen v3.7 for the Hotel off-path epoch hotel-offpath-v1 as a campaign-E-role epoch (FREEZE_V37_20261015.md)"
EPOCH = "hotel-offpath-v1"


def load_registry(path=PARAMETERS_V37):
    doc = json.loads(Path(path).read_text())
    return {p["name"]: p for p in doc["parameters"]}


REGISTRY37 = load_registry()
PARAMS_USED37 = set()


def param37(name):
    PARAMS_USED37.add(name)
    return REGISTRY37[name]["value"]


HOTEL_E_PROFILES = param37("V37_EPOCH_PROFILES")
SPLIT37 = param37("V37_SPLIT")
V33_ADDED = dict(v33.ADDED_PROFILES)         # v3.3's table as frozen, captured before any rebinding
assert set(HOTEL_E_PROFILES) == {EPOCH} and EPOCH in v34.HOTEL_PROFILES and EPOCH not in V33_ADDED
assert {k: v for k, v in HOTEL_E_PROFILES[EPOCH].items() if k != "role"} == {
    k: v for k, v in v34.HOTEL_PROFILES[EPOCH].items() if k != "role"}, "v3.7 changes only the epoch's role"
assert HOTEL_E_PROFILES[EPOCH]["role"] == "campaign-E" and v34.HOTEL_PROFILES[EPOCH]["role"] != "campaign-E"
assert SPLIT37 == v32.E_SPLIT, "v3.7's split is V32_E_SPLIT"

ADMIT_HOTEL_E = True              # (1): the epoch is in v3.3's table as campaign-E (False: v3.2 never sees it, --blocks is refused)
HOTEL_ONLY = True                 # any system but hotel is refused (False: passed to v3.4's engine)
HOTEL_BLOCK_FROM_CONTRACT = True  # (2): a Hotel cell's block is its cell-contract runKey.block (False: v3.2's receipt-only reader)
HOTEL_TRAIN_ONLY = True           # (3): v3.2's train-only hooks are installed for hotel (False: held-out cells calibrate)
SWITCHES = ("ADMIT_HOTEL_E", "HOTEL_ONLY", "HOTEL_BLOCK_FROM_CONTRACT", "HOTEL_TRAIN_ONLY")


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def admitted_profiles():
    merged = dict(V33_ADDED)
    if ADMIT_HOTEL_E:
        merged.update(HOTEL_E_PROFILES)
    return merged


_ORIG_READ_BLOCK = v32._read_block
_ORIG_V33_CTX = v33._ORIG_CTX


def read_block37(d):
    """v3.2's (studyEpoch, block) of a cell's receipt; for a Hotel cell (no receipt) of this registry's epoch, its contract's (2)."""
    epoch, block = _ORIG_READ_BLOCK(d)
    if epoch is not None or not HOTEL_BLOCK_FROM_CONTRACT:
        return epoch, block
    c_epoch, _regime, _rate, c_block = v34._contract_run(d)[:4]
    if c_epoch in HOTEL_E_PROFILES and isinstance(c_block, int) and not isinstance(c_block, bool):
        return c_epoch, c_block
    return epoch, block


@contextlib.contextmanager
def v32_context37(system, rates=None, blocks=None, test_blocks=None):
    """v3.2's context; for system hotel, plus v3.2's train-only hooks (3), restored on exit."""
    saved = []
    try:
        with _ORIG_V33_CTX(system, rates, blocks, test_blocks) as st:
            if system == "hotel" and HOTEL_TRAIN_ONLY:
                for mod, name, fn in v36.TRAIN_ONLY_HOOKS:
                    saved.append((mod, name, getattr(mod, name)))
                    setattr(mod, name, fn)
            yield st
    finally:
        for mod, name, val in reversed(saved):
            setattr(mod, name, val)


@contextlib.contextmanager
def _v37_wrapped():
    prev, prev_rb, prev_ctx = v33.ADDED_PROFILES, v32._read_block, v33._ORIG_CTX
    v33.ADDED_PROFILES = admitted_profiles()
    v32._read_block = read_block37
    v33._ORIG_CTX = v32_context37
    try:
        yield
    finally:
        v33.ADDED_PROFILES, v32._read_block, v33._ORIG_CTX = prev, prev_rb, prev_ctx


def run37(campaign, system="hotel", validation_dirs=(), reference=True, blocks=None, split=None, test_blocks=None):
    """run34's body without its Hotel split refusal, inside the v3.7 rebinding."""
    if HOTEL_ONLY and system != "hotel":
        raise SystemExit("refusing: --system %s: v3.7 admits one Hotel epoch and reads Hotel only (TeaStore's off-path epoch is read "
                         "by v3.6, OTel's epochs by v3.3 and v3.5)" % system)
    campaigns = [campaign] if isinstance(campaign, (str, Path)) else list(campaign)
    scan = campaigns + ([validation_dirs] if isinstance(validation_dirs, (str, Path)) else list(validation_dirs))
    epochs, regimes = v34.hotel_scan(scan)
    active = v34.hotel_is_active(epochs, regimes)
    with _v37_wrapped(), v34._v34_wrapped(active):
        R = v33.run33(campaign, system=system, validation_dirs=validation_dirs, reference=reference, blocks=blocks,
                      split=split, test_blocks=test_blocks)
        if active:
            v34._check_paths(R)
    R["_v34ctx"] = {"system": system, "hotelActive": active, "hotelOffPath": v34.offpath_epochs_in(epochs) if active else []}
    R["_v37ctx"] = {"system": system}
    return R


def _v37_block(R):
    read = dict(R["v32"]["epochsRead"])
    return {"version": VERSION, "label": LABEL, "system": R["_v37ctx"]["system"],
            "epochsAdmittedAsCampaignEByV37": sorted(HOTEL_E_PROFILES) if ADMIT_HOTEL_E else [],
            "epochsRead": read, "campaignEEpochsRead": sorted(e for e in HOTEL_E_PROFILES if e in read and ADMIT_HOTEL_E),
            "switches": {k: globals()[k] for k in SWITCHES},
            "parametersV37Sha256": _sha(PARAMETERS_V37),
            "parametersV37": {n: REGISTRY37[n]["value"] for n in sorted(PARAMS_USED37)}}


def build_json37(R):
    with _v37_wrapped():
        J = v34.build_json34(R)
        blk = _v37_block(R)
    J["v34ScriptSha256"] = J["scriptSha256"]
    J["version"], J["label"] = VERSION, LABEL
    J["script"] = "research/detection-time/sweep_analysis_v3_7.py"
    J["scriptSha256"] = _sha(__file__)
    J["v37"] = blk
    return J


def render37(R, J):
    J34 = dict(J, version=v34.VERSION)
    with _v37_wrapped():
        md = v34.render34(R, J34)
    v = J["v37"]
    w = ["", "## v3.7 additions (Hotel off-path epoch read as campaign-E; admission only)", "",
         "Frozen v3.7 (FREEZE_V37_20261015.md). Scope: instance; a report, no mechanism claim.", "",
         "- Epoch admitted as campaign-E by v3.7: %s." % (", ".join("`%s`" % e for e in v["epochsAdmittedAsCampaignEByV37"]) or DASH),
         "- Campaign-E epoch read: %s." % (", ".join("`%s`" % e for e in v["campaignEEpochsRead"]) or DASH), ""]
    return md + "\n".join(w) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("campaign", nargs="+", help="fetched campaign directory/ies of one system (pooled, H1)")
    ap.add_argument("--system", default="hotel", choices=v24.SYSTEMS)
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
    R = run37(camp[0] if len(camp) == 1 else camp, system=a.system, validation_dirs=[Path(x) for x in a.validation],
              blocks=set(a.blocks) if a.blocks is not None else None, split=a.split,
              test_blocks=set(a.test_blocks) if a.test_blocks is not None else None)
    with v24.use_system(a.system):
        v31.finish(R)
    J = build_json37(R)
    out.mkdir(parents=True)
    v31.write_new(out / OUT_JSON, json.dumps(J, indent=1, sort_keys=True, default=sorted))
    v31.write_new(out / OUT_MD, render37(R, J))
    print("wrote", out / OUT_JSON, out / OUT_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
