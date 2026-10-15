"""Analysis v3.7 (research/detection-time/sweep_analysis_v3_7.py, research/protocol/parameters_v3_7.json): Hotel's off-path epoch
`hotel-offpath-v1` read as a campaign-E-role epoch over v3.4 (block selection by the cell contract's runKey.block, held-out test blocks,
decision 102's train-only calibration for Hotel, v3.4's split refusal lifted).

Layer: reader + synthetic end-to-end. Synthetic cells only, the Hotel off-path fixture of tests/test_sweep_analysis_v3_4.py (blocks 1-3,
rate 1). Every v3.7 switch has a planted defect under which its check fails; the frozen files are untouched (digests); a v3.7 read without
a block selection equals v3.4's in every key but identity keys and the admission lists.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "detection-time"))
sys.path.insert(0, str(ROOT / "research" / "placement"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sweep_analysis_v3_7 as v37  # noqa: E402
import test_sweep_analysis_v22_systems as t22  # noqa: E402
from test_sweep_analysis_v3_4 import CP, EPOCH, offpath_campaign  # noqa: E402
from test_sweep_analysis_v3_5 import _diff  # noqa: E402
from test_sweep_analysis_v3_6 import FROZEN as FROZEN36  # noqa: E402
from test_sweep_analysis_v3_3 import ts_campaign  # noqa: E402

v34, v33, v32, v31, v24 = v37.v34, v37.v33, v37.v32, v37.v31, v37.v24
SPLIT3 = {"train": [1, 2], "test": [3]}


@pytest.fixture(autouse=True)
def _small_split(monkeypatch):
    monkeypatch.setattr(v32, "E_SPLIT", SPLIT3)


def run(camps, **kw):
    R = v37.run37(camps, system="hotel", reference=False, **kw)
    with v24.use_system("hotel"):
        v31.finish(R)
    return R


def chk_hotel_e_admitted(tmp_path, _world=None):
    camp = offpath_campaign(tmp_path / "c")
    R = run([camp], blocks={1, 2})
    sel = R["v32"]["blockSelection"]
    return (sel["applies"] == [EPOCH] and sel["excludedCount"] == 3 and {c["block"] for c in R["cells"]} == {1, 2}
            and all(c["valid"] for c in R["cells"]))


def chk_hotel_only(tmp_path, _world=None):
    try:
        v37.run37(ts_campaign(tmp_path / "t"), system="teastore", reference=False)
    except SystemExit as exc:
        return "reads Hotel only" in str(exc)
    except Exception:                                # noqa: BLE001
        return False
    return False


def chk_block_from_contract(tmp_path, _world=None):
    camp = offpath_campaign(tmp_path / "c")
    seen = []
    with v37._v37_wrapped():
        for cp in sorted((camp / "runs").rglob("cell-contract.json")):
            seen.append(v32._read_block(cp.parent))
    return sorted(b for _, b in seen if b is not None) == [1, 1, 1, 2, 2, 2, 3, 3, 3] and {e for e, _ in seen} == {EPOCH}


def chk_train_only(tmp_path, _world=None):
    camp = offpath_campaign(tmp_path / "c")
    R = run([camp], test_blocks={3})
    held = sorted(c["block"] for c in R["cells"] if c.get("heldOut"))
    return held == [3, 3, 3] and all(r["cells"] == 2 for r in R["cal"]["primary"]["perRate"].values())


def test_the_epoch_is_read_as_campaign_e_with_a_block_selection(tmp_path):
    assert chk_hotel_e_admitted(tmp_path / "a")
    camp = offpath_campaign(tmp_path / "v34")
    with pytest.raises(SystemExit, match="not applied to Hotel"):          # v3.4 alone refuses a split for Hotel
        v34.run34(camp, system="hotel", reference=False, test_blocks={3})


def test_other_systems_are_refused(tmp_path):
    assert chk_hotel_only(tmp_path)
    with pytest.raises(SystemExit, match="reads Hotel only"):
        v37.main([str(t22.TS_CAMP), "--system", "teastore", "--out", str(tmp_path / "o")])
    assert not (tmp_path / "o").exists()


def test_contract_blocks(tmp_path):
    assert chk_block_from_contract(tmp_path)


def test_a_test_block_read_without_test_blocks_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="decision 102"):
        run([offpath_campaign(tmp_path / "c")])


def test_held_out_cells_never_calibrate(tmp_path):
    assert chk_train_only(tmp_path / "a")
    camp = offpath_campaign(tmp_path / "b")
    js = lambda r: json.loads(json.dumps(v37.build_json37(r)["calibration"], default=sorted))   # noqa: E731
    assert js(run([camp], test_blocks={3})) == js(run([camp], blocks={1, 2}))


IDENTITY = {"version", "label", "script", "scriptSha256", "generatedAt", "frameworkCommit", "v34ScriptSha256", "v37"}
ADMISSION_LISTS = {"v32.blockSelection.applies", "v32.epochsAdmittedExplicitly", "v33.epochsAddedByV33"}


def test_an_unselected_v37_read_equals_v34s(tmp_path, monkeypatch):
    monkeypatch.setattr(v32, "E_SPLIT", {"train": None, "test": None})
    camp = offpath_campaign(tmp_path / "o")
    R4 = v34.run34([camp], system="hotel", reference=False)
    with v24.use_system("hotel"):
        v31.finish(R4)
    J4 = json.loads(json.dumps(v34.build_json34(R4), default=sorted))
    J7 = json.loads(json.dumps(v37.build_json37(run([camp])), default=sorted))
    got = set(_diff(J4, J7))
    assert {"version", "label", "script", "scriptSha256", "v34ScriptSha256", "v37"} <= got <= IDENTITY | ADMISSION_LISTS, got
    for k in ("episodes", "calibration", "perSensor", "predictions", "secondary", "validation", "v34"):
        assert J4[k] == J7[k], k


def test_rebinding_is_restored_on_exit():
    before = (v33.ADDED_PROFILES, v32._read_block, v33._ORIG_CTX, v31.calibrate, v24.make_ctx)
    with v37._v37_wrapped():
        assert v33.ADDED_PROFILES[EPOCH]["role"] == "campaign-E" and v32._read_block is v37.read_block37
    with pytest.raises(RuntimeError):
        with v37._v37_wrapped():
            raise RuntimeError("x")
    after = (v33.ADDED_PROFILES, v32._read_block, v33._ORIG_CTX, v31.calibrate, v24.make_ctx)
    assert all(a is b for a, b in zip(before, after)) and EPOCH not in v33.ADDED_PROFILES


def test_json_and_markdown_carry_the_v37_block(tmp_path):
    camp = offpath_campaign(tmp_path / "c")
    out = tmp_path / "ro"
    assert v37.main([str(camp), "--system", "hotel", "--blocks", "1", "2", "--out", str(out)]) == 0
    J = json.loads((out / v37.OUT_JSON).read_text())
    md = (out / v37.OUT_MD).read_text()
    assert J["version"] == "3.7" and J["scriptSha256"] == v37._sha(v37.__file__) and J["v34ScriptSha256"] == v34._sha(v34.__file__)
    assert J["v33ScriptSha256"] == v33._sha(v33.__file__) and J["v37"]["parametersV37Sha256"] == v37._sha(v37.PARAMETERS_V37)
    assert J["v37"]["campaignEEpochsRead"] == [EPOCH] and "## v3.7 additions" in md and "v3.4" in md


def _exec_with_registry(tmp_path, edit):
    doc = json.loads(v37.PARAMETERS_V37.read_text())
    edit(doc)
    reg = tmp_path / "parameters_v3_7.json"
    reg.write_text(json.dumps(doc))
    src = Path(v37.__file__).read_text().replace('REPO / "research" / "protocol" / "parameters_v3_7.json"', repr(str(reg)))
    assert str(reg) in src
    ns = {"__name__": "v37_planted", "__file__": v37.__file__}
    exec(compile(src, v37.__file__, "exec"), ns)          # noqa: S102
    return ns


def _param(doc, name):
    return next(p for p in doc["parameters"] if p["name"] == name)["value"]


def test_planted_registry_defects_are_refused_at_import(tmp_path, monkeypatch):
    monkeypatch.setattr(v32, "E_SPLIT", {"train": [1, 2, 3], "test": [4, 5]})
    (tmp_path / "ok").mkdir()
    assert _exec_with_registry(tmp_path / "ok", lambda d: None)["LABEL"] == v37.LABEL
    for name, edit in (("rate", lambda d: _param(d, "V37_EPOCH_PROFILES")[EPOCH].__setitem__("rates", [5.0])),
                       ("regime", lambda d: _param(d, "V37_EPOCH_PROFILES")[EPOCH]["faultRegimes"].pop(CP)),
                       ("role", lambda d: _param(d, "V37_EPOCH_PROFILES")[EPOCH].__setitem__("role", "offpath-hotel")),
                       ("second", lambda d: _param(d, "V37_EPOCH_PROFILES").__setitem__("hotel-offpath-v2", {})),
                       ("split", lambda d: _param(d, "V37_SPLIT").__setitem__("test", [5]))):
        (tmp_path / name).mkdir()
        with pytest.raises(AssertionError):
            _exec_with_registry(tmp_path / name, edit)


def test_registry_entries_and_the_pass_rule():
    for n, p in v37.REGISTRY37.items():
        assert p["origin_ref"] and p["status"] == "active", n
    rule = v37.REGISTRY37["V37_PASS_RULE"]["value"]
    assert [(r["class"], r["rate"]) for r in rule] == [(CP, 10), (CP, 1)]
    assert all(r["set"] == "frontier (effort<=any, runtime<=any) @6/T_r" and r["minGain"] is None and r["minImprovedEpisodes"] == 2
               and r["minEpisodes"] == 2 for r in rule)
    assert json.loads((ROOT / "research/protocol/split_hotel_offpath.json").read_text()) == v37.SPLIT37


FROZEN = dict(FROZEN36, **{   # FREEZE_V36_20261015.md
    "research/detection-time/sweep_analysis_v3_6.py": "98d7832c4dad50149b53bebf191682dce991877a136e6db548b9c152131df83a",
    "research/protocol/parameters_v3_6.json": "68f417c53599b52401e6a33d30d0d45215bf8a349182f84171b2691cf9424428",
    "research/placement/celf_v3_6.py": "05c5c58af42e8d303681517101e042b44e5eeca9907bc2a8dac67cda8be1b6cf",
})


def test_the_frozen_chain_is_byte_identical():
    for rel, sha in FROZEN.items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == sha, rel


CHECKS = {"ADMIT_HOTEL_E": chk_hotel_e_admitted, "HOTEL_ONLY": chk_hotel_only, "HOTEL_BLOCK_FROM_CONTRACT": chk_block_from_contract,
          "HOTEL_TRAIN_ONLY": chk_train_only}


def _passes(chk, tmp_path):
    try:
        return bool(chk(tmp_path, None))
    except (v24.UnknownSchema, SystemExit, AssertionError, StopIteration, KeyError):
        return False


@pytest.mark.parametrize("flag", sorted(CHECKS))
def test_check_passes_and_fails_with_its_switch_off(flag, tmp_path, monkeypatch):
    assert _passes(CHECKS[flag], tmp_path / "on"), flag
    monkeypatch.setattr(v37, flag, False)
    assert not _passes(CHECKS[flag], tmp_path / "off"), flag


def test_every_switch_has_a_check():
    switches = {k for k, v in vars(v37).items() if k.isupper() and isinstance(v, bool)}
    assert switches == set(CHECKS) == set(v37.SWITCHES), switches ^ set(CHECKS)
