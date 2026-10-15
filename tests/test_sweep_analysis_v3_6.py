"""Analysis v3.6 (research/detection-time/sweep_analysis_v3_6.py, research/protocol/parameters_v3_6.json): TeaStore's off-path epoch
`teastore-offpath-v1` read as a campaign-E-role epoch (block selection by the receipt's run.block, held-out test blocks, decision 102's
train-only calibration for TeaStore).

Layer: reader + synthetic end-to-end. Synthetic cells only, the TeaStore off-path fixture of tests/test_sweep_analysis_v3_3.py, with cells
copied into further blocks. Every v3.6 change has a planted defect (its switch off) under which its check fails
(test_check_passes_and_fails_with_its_switch_off); the frozen files are untouched (digests); a v3.6 read without a block selection equals
v3.3's in every key but identity keys and the admission lists (test_an_unselected_v36_read_equals_v33s).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "detection-time"))
sys.path.insert(0, str(ROOT / "research" / "placement"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sweep_analysis_v3_6 as v36  # noqa: E402
import test_sweep_analysis_v22_systems as t22  # noqa: E402
import test_sweep_analysis_v3_2 as t32  # noqa: E402
from test_sweep_analysis_v3_3 import AUTH, REC, TS_EPOCH, f_campaign, ts_campaign  # noqa: E402
from test_sweep_analysis_v3_5 import FROZEN as FROZEN35, _diff  # noqa: E402

v33, v32, v31, v24 = v36.v33, v36.v32, v36.v31, v36.v24
SPLIT3 = {"train": [1, 2], "test": [3]}


@pytest.fixture(autouse=True)
def _small_split(monkeypatch):
    """The synthetic campaign has blocks 1-3, so the registry split is 1-2 / 3 here (as the v3.5 wrapper tests do)."""
    monkeypatch.setattr(v32, "E_SPLIT", SPLIT3)


def _clone(src, block, name):
    """A copy of cell `src` as a cell of `block` (receipt run.block edited)."""
    d = src.parent / name
    shutil.copytree(src, d)
    t22._edit_json(d / "receipt.json", lambda rc: rc["run"].update(block=block))
    return d


def ts3_campaign(dest):
    """The v3.3 TeaStore off-path fixture (block 1: no-fault, auth; block 2: recommender) plus a block-2 no-fault cell and a block-3
    copy of the no-fault, auth and recommender cells (the test block)."""
    camp = ts_campaign(dest)
    nf, auth, rec = (t22._cell_dir(camp, r) for r in (t22.TS_NF, AUTH, REC))
    _clone(nf, 2, "b02-91-full")
    _clone(nf, 3, "b03-92-full")
    _clone(auth, 3, "b03-93-full")
    _clone(rec, 3, "b03-94-full")
    return camp


def cells36(camps, blocks=None, test_blocks=None):
    camps = list(camps)
    with v24.use_system("teastore"), v36._v36_wrapped(), v33._v33_wrapped(bool(v33.epochs_present(camps, "teastore"))), \
            v32.v32_context("teastore", None, blocks, test_blocks):
        return v31.find_and_load3(camps)[1]


def run(camps, **kw):
    R = v36.run36(camps, system="teastore", reference=False, **kw)
    with v24.use_system("teastore"):
        v31.finish(R)
    return R


# ----------------------------------------------------------------------------- 8.8 / 8.9: campaign-E role and the block of a cell

def chk_ts_e_admitted(tmp_path, _world=None):
    """`--blocks 1 2` reads the TeaStore off-path cells of blocks 1-2 only; block 3's three cells are excluded by the split."""
    camp = ts3_campaign(tmp_path / "c")
    R = run([camp], blocks={1, 2})
    sel = R["v32"]["blockSelection"]
    return (sel["applies"] == [TS_EPOCH] and sel["excludedCount"] == 3
            and {c["block"] for c in R["cells"]} == {1, 2} and all(c["valid"] for c in R["cells"]))


def chk_teastore_only(tmp_path, _world=None):
    camp = f_campaign(tmp_path / "f")
    try:
        v36.run36(camp, system="otel", reference=False)
    except SystemExit as exc:
        return "reads TeaStore only" in str(exc)
    except Exception:                                # noqa: BLE001  (the unplanted engine failing differently is not a refusal)
        return False
    return False


def chk_block_from_run(tmp_path, _world=None):
    """The block of a TeaStore receipt is its run.block: the selection sees all 9 cells and the reader records their blocks."""
    camp = ts3_campaign(tmp_path / "c")
    seen = []
    with v36._v36_wrapped():
        for rp in sorted((camp / "runs").rglob("receipt.json")):
            seen.append(v32._read_block(rp.parent))
    return sorted(b for _, b in seen if b is not None) == [1, 1, 2, 2, 3, 3, 3] and {e for e, _ in seen} == {TS_EPOCH}


def chk_train_only(tmp_path, _world=None):
    """With --test-blocks 3 the block-3 cells are heldOut and the no-fault calibration has the training blocks' cells only."""
    camp = ts3_campaign(tmp_path / "c")
    R = run([camp], test_blocks={3})
    held = sorted(c["block"] for c in R["cells"] if c.get("heldOut"))
    cal = R["cal"]["primary"]["perRate"]
    return held == [3, 3, 3] and all(r["cells"] == 2 for r in cal.values())


def test_the_epoch_is_read_as_campaign_e_with_a_block_selection(tmp_path):
    assert chk_ts_e_admitted(tmp_path / "a")
    camp = ts3_campaign(tmp_path / "v33")                  # under v3.3 alone the epoch is lanes-only: --blocks is refused
    with pytest.raises(SystemExit, match="no cell of a campaign-E epoch"):
        v33.run33(camp, system="teastore", reference=False, blocks={1, 2})


def test_other_systems_are_refused(tmp_path):
    assert chk_teastore_only(tmp_path)
    with pytest.raises(SystemExit, match="reads TeaStore only"):
        v36.main([str(t22.TS_CAMP), "--system", "otel", "--out", str(tmp_path / "o")])
    assert not (tmp_path / "o").exists()


def test_receipt_blocks_and_otel_receipts(tmp_path):
    assert chk_block_from_run(tmp_path)
    camp = f_campaign(tmp_path / "f")                     # an OTel receipt (runKey) keeps v3.2's answer
    rp = next((camp / "runs").rglob("receipt.json"))
    with v36._v36_wrapped():
        assert v32._read_block(rp.parent) == v36._ORIG_READ_BLOCK(rp.parent)
    legacy = next(Path(t22.TS_CAMP).rglob("receipt.json"))  # a legacy TeaStore receipt (another epoch) gets (None, None)
    with v36._v36_wrapped():
        assert v32._read_block(legacy.parent) == (None, None)


def test_a_test_block_read_without_test_blocks_is_refused(tmp_path):
    """v3.2's held-out rule applies to the epoch: a registry test block read without --test-blocks stops the run (decision 102)."""
    camp = ts3_campaign(tmp_path / "c")
    with pytest.raises(SystemExit, match="decision 102"):
        run([camp])


def test_held_out_cells_never_calibrate(tmp_path):
    assert chk_train_only(tmp_path / "a")
    camp = ts3_campaign(tmp_path / "b")
    R = run([camp], test_blocks={3})
    tr = run([camp], blocks={1, 2})
    js = lambda r: json.loads(json.dumps(v36.build_json36(r)["calibration"], default=sorted))   # noqa: E731
    assert js(R) == js(tr)                         # what score_test_v3_2 checks (decision 102)


def test_the_epoch_is_never_read_with_another_one(tmp_path):
    other = t32.offpath_campaign(tmp_path / "e")
    with pytest.raises(SystemExit):
        cells36([ts3_campaign(tmp_path / "c"), other])


# ----------------------------------------------------------------------------- v3.6 equals v3.3 where nothing is selected

IDENTITY = {"version", "label", "script", "scriptSha256", "generatedAt", "frameworkCommit", "v33ScriptSha256", "v36"}
ADMISSION_LISTS = {"v32.blockSelection.applies"}


def test_an_unselected_v36_read_equals_v33s(tmp_path, monkeypatch):
    """The v3.3 fixture (blocks 1-2, no registry test block) through v3.3 and v3.6, no --blocks: every key equal but identity keys,
    the v36 block and the list of campaign-E epochs the selection rule applies to."""
    monkeypatch.setattr(v32, "E_SPLIT", {"train": None, "test": None})
    camp = ts_campaign(tmp_path / "t")
    R3 = v33.run33([camp], system="teastore", reference=False)
    with v24.use_system("teastore"):
        v31.finish(R3)
    J3 = json.loads(json.dumps(v33.build_json33(R3), default=sorted))
    J6 = json.loads(json.dumps(v36.build_json36(run([camp])), default=sorted))
    got = set(_diff(J3, J6))
    assert {"version", "label", "script", "scriptSha256", "v33ScriptSha256", "v36"} <= got <= IDENTITY | ADMISSION_LISTS, got
    for k in ("episodes", "calibration", "perSensor", "predictions", "secondary", "validation"):
        assert J3[k] == J6[k], k


def test_rebinding_is_restored_on_exit():
    before = (v33.ADDED_PROFILES, v32._read_block, v33._ORIG_CTX, v31.calibrate, v31.fits_for3, v24.make_ctx)
    with v36._v36_wrapped():
        assert v33.ADDED_PROFILES[TS_EPOCH]["role"] == "campaign-E" and v32._read_block is v36.read_block36
    with pytest.raises(RuntimeError):
        with v36._v36_wrapped():
            raise RuntimeError("x")
    after = (v33.ADDED_PROFILES, v32._read_block, v33._ORIG_CTX, v31.calibrate, v31.fits_for3, v24.make_ctx)
    assert all(a is b for a, b in zip(before, after)) and v33.ADDED_PROFILES[TS_EPOCH]["role"] == "offpath-teastore"


def test_json_and_markdown_carry_the_v36_block(tmp_path):
    camp = ts3_campaign(tmp_path / "c")
    out = tmp_path / "ro"
    assert v36.main([str(camp), "--system", "teastore", "--blocks", "1", "2", "--out", str(out)]) == 0
    J = json.loads((out / v36.OUT_JSON).read_text())
    md = (out / v36.OUT_MD).read_text()
    assert J["version"] == "3.6" and J["scriptSha256"] == v36._sha(v36.__file__)
    assert J["v33ScriptSha256"] == v33._sha(v33.__file__) and J["v36"]["parametersV36Sha256"] == v36._sha(v36.PARAMETERS_V36)
    assert J["v36"]["campaignEEpochsRead"] == [TS_EPOCH] and "## v3.6 additions" in md
    assert set(J["v36"]["parametersV36"]) == {"V36_EPOCH_PROFILES", "V36_SPLIT"}
    with pytest.raises(SystemExit):
        v36.main([str(camp), "--system", "teastore", "--out", str(out)])


# ----------------------------------------------------------------------------- registry and frozen files

def _exec_with_registry(tmp_path, edit):
    doc = json.loads(v36.PARAMETERS_V36.read_text())
    edit(doc)
    reg = tmp_path / "parameters_v3_6.json"
    reg.write_text(json.dumps(doc))
    src = Path(v36.__file__).read_text().replace('REPO / "research" / "protocol" / "parameters_v3_6.json"', repr(str(reg)))
    assert str(reg) in src
    ns = {"__name__": "v36_planted", "__file__": v36.__file__}
    exec(compile(src, v36.__file__, "exec"), ns)          # noqa: S102
    return ns


def _param(doc, name):
    return next(p for p in doc["parameters"] if p["name"] == name)["value"]


def test_planted_registry_defects_are_refused_at_import(tmp_path, monkeypatch):
    """The profile may differ from v3.3's in `role` only, re-admit exactly TeaStore's off-path epoch, and keep V32_E_SPLIT."""
    monkeypatch.setattr(v32, "E_SPLIT", {"train": [1, 2, 3], "test": [4, 5]})
    (tmp_path / "ok").mkdir()
    assert _exec_with_registry(tmp_path / "ok", lambda d: None)["LABEL"] == v36.LABEL
    for name, edit in (("rate", lambda d: _param(d, "V36_EPOCH_PROFILES")[TS_EPOCH]["design"].__setitem__("journeysPerSecond", [5.0])),
                       ("regime", lambda d: _param(d, "V36_EPOCH_PROFILES")[TS_EPOCH]["faultRegimes"].pop(AUTH)),
                       ("role", lambda d: _param(d, "V36_EPOCH_PROFILES")[TS_EPOCH].__setitem__("role", "offpath-teastore")),
                       ("second", lambda d: _param(d, "V36_EPOCH_PROFILES").__setitem__("teastore-offpath-v2", {})),
                       ("split", lambda d: _param(d, "V36_SPLIT").__setitem__("test", [5]))):
        (tmp_path / name).mkdir()
        with pytest.raises(AssertionError):
            _exec_with_registry(tmp_path / name, edit)


def test_registry_entries_and_the_pass_rule():
    for n, p in v36.REGISTRY36.items():
        assert p["origin_ref"] and p["origin_type"] in ("decision", "literature", "measured", "upstream", "engineering default",
                                                        "unknown") and p["status"] == "active", n
    rule = v36.REGISTRY36["V36_PASS_RULE"]["value"]
    assert [(r["class"], r["rate"]) for r in rule] == [(REC, 10), (REC, 1)]
    assert all(r["set"] == "frontier (effort<=any, runtime<=any) @6/T_r" and r["minGain"] is None and r["minImprovedEpisodes"] == 2
               and r["minEpisodes"] == 2 for r in rule)
    assert json.loads((ROOT / "research/protocol/split_ts_offpath.json").read_text()) == v36.SPLIT36


FROZEN = dict(FROZEN35, **{   # FREEZE_V35_20261015.md
    "research/detection-time/sweep_analysis_v3_5.py": "69ec63b3e099a664ad4b75f59ece4a28b5d8ebaeeb159ef94250d2219e61509b",
    "research/protocol/parameters_v3_5.json": "d3b72bf9a255bbb5cac091c6e319485e25ea7e3759ed9e792c45f7702216977b",
})


def test_the_frozen_chain_is_byte_identical():
    for rel, sha in FROZEN.items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == sha, rel


# ----------------------------------------------------------------------------- planted defects: each switch has a check

CHECKS = {"ADMIT_TS_E": chk_ts_e_admitted, "TEASTORE_ONLY": chk_teastore_only, "TS_BLOCK_FROM_RUN": chk_block_from_run,
          "TS_TRAIN_ONLY": chk_train_only}


def _passes(chk, tmp_path):
    try:
        return bool(chk(tmp_path, None))
    except (v24.UnknownSchema, SystemExit, AssertionError, StopIteration, KeyError):
        return False


@pytest.mark.parametrize("flag", sorted(CHECKS))
def test_check_passes_and_fails_with_its_switch_off(flag, tmp_path, monkeypatch):
    assert _passes(CHECKS[flag], tmp_path / "on"), flag
    monkeypatch.setattr(v36, flag, False)
    assert not _passes(CHECKS[flag], tmp_path / "off"), flag


def test_every_switch_has_a_check():
    switches = {k for k, v in vars(v36).items() if k.isupper() and isinstance(v, bool)}
    assert switches == set(CHECKS) == set(v36.SWITCHES), switches ^ set(CHECKS)
