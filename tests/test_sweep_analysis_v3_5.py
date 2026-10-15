"""Analysis v3.5 (research/detection-time/sweep_analysis_v3_5.py, research/protocol/parameters_v3_5.json): admission of the OTel
campaign-F ablation epoch `otel-offpath-f-nolag-v1` (F without the kafkametrics receiver) on top of v3.3's admission, and the lag-lane
integrity record.

Layer: reader + synthetic end-to-end. Synthetic cells only, built by the helpers of tests/test_sweep_analysis_v3_3.py (the F fixture) and
tests/test_sweep_analysis_v3_2.py, restamped to the ablation epoch's study epoch and left without Kafka lag gauges (the epoch has no
kafkametrics receiver). No cell of the ablation was read. Every v3.5 change has a planted defect (its switch off) under which one of its
checks fails (test_check_passes_and_fails_with_its_switch_off); the frozen v3.2, v3.3 and v3.4 files are untouched (digests); and a v3.5
read of F's fixture equals v3.3's in every key but identity keys and the three admission lists (test_a_v35_read_of_f_equals_v33s; the real
regression, on F's committed training inputs, is recorded in FREEZE_V35_20261015.md).
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

import sweep_analysis_v3_5 as v35  # noqa: E402
import test_sweep_analysis_v22_systems as t22  # noqa: E402
import test_sweep_analysis_v3_2 as t32  # noqa: E402
from test_sweep_analysis_v3_3 import (ACCT, EPOCH_E, EPOCH_F, FRAUD, FRONT, _zap, add_kafka, f_campaign)  # noqa: E402,F401

v33, v32, v31, v24 = v35.v33, v35.v32, v35.v31, v35.v24
EPOCH_NL = "otel-offpath-f-nolag-v1"
NO_SPLIT = {"train": None, "test": None}


@pytest.fixture(autouse=True)
def _no_registry_split(monkeypatch):
    """The synthetic campaigns use blocks 1-3, so the registry's 3+2 split is switched off here (as in the v3.2 and v3.3 tests)."""
    monkeypatch.setattr(v32, "E_SPLIT", NO_SPLIT)


# ----------------------------------------------------------------------------- synthetic campaigns

def nolag_campaign(dest, epoch=EPOCH_NL, lag_in=()):
    """The v3.2 off-path fixture (E's shape, no throttle) restamped to `epoch`, with NO Kafka lag gauge anywhere (the receiver is not
    rendered) and, as in F's fixture, one Kafka broker log line inside the fraud cell's fault window (the coordinator lane, which the
    ablation leaves alone). `lag_in`: regimes whose cell gets a lag gauge anyway (a planted ablation that did not hold)."""
    camp = t32.offpath_campaign(dest)
    t32._set_epoch(camp, epoch, multi=False)
    fr = t22._cell_dir(camp, FRAUD)
    barrier = json.loads((fr / "request-ledger.json").read_text())["barrierEpoch"]
    with (fr / "application.log").open("a") as fh:
        fh.write("kafka-1  | %s [GroupCoordinator 1]: Member consumer-fraud-detection-1 in group fraud-detection has "
                 "failed\n" % _zap(barrier + 80))
    for regime in lag_in:
        add_kafka(t22._cell_dir(camp, regime))
    return camp


def cells35(camps, system="otel", blocks=None):
    """The cells as the v3.5 reader loads them (v3.5's table rebinding, then v3.3's context, then v3.2's)."""
    camps = list(camps)
    with v24.use_system(system), v35._v35_wrapped(), v33._v33_wrapped(bool(v33.epochs_present(camps, system))), \
            v32.v32_context(system, None, blocks):
        return v31.find_and_load3(camps)[1]


def run(camps, **kw):
    R = v35.run35(camps, system="otel", reference=False, **kw)
    with v24.use_system("otel"):
        v31.finish(R)
    return R


@pytest.fixture(scope="module")
def nl_world(tmp_path_factory):
    base = tmp_path_factory.mktemp("v35nl")
    camp = nolag_campaign(base / "nl")
    return {"base": base, "camp": camp, "quiet": t32.quiet(camp, base / "q")}


@pytest.fixture(scope="module")
def nl_result(nl_world):
    with pytest.MonkeyPatch.context() as mp:           # module-scoped: the autouse per-test patch is not yet in force
        mp.setattr(v32, "E_SPLIT", NO_SPLIT)
        return run([nl_world["camp"], nl_world["quiet"]])


@pytest.fixture(scope="module")
def f_world5(tmp_path_factory):
    base = tmp_path_factory.mktemp("v35f")
    camp = f_campaign(base / "f")
    return {"base": base, "camp": camp, "quiet": t32.quiet(camp, base / "q")}


# ----------------------------------------------------------------------------- 8.7: the ablation epoch is admitted like F

def chk_nolag_admitted(tmp_path, _world=None):
    camp = nolag_campaign(tmp_path / "c")
    cells = cells35([camp])
    f = next(c for c in cells if c["valid"] and c["regime"] == FRAUD)
    return (all(c["valid"] for c in cells) and {c["studyEpoch"] for c in cells} == {EPOCH_NL}
            and {c["harness"] for c in cells} == {"B"} and {c["regime"] for c in cells} == {FRAUD, ACCT, FRONT, t22.OT_NF}
            and f["target"] == "frauddetectionservice" and f["h4"]["status"] == "used")


def test_nolag_epoch_is_driven_through_the_loader(tmp_path):
    """Decision-92 lesson: a synthetic cell of the new epoch goes through find_and_load3 (the v3.5 context) and is a valid
    campaign-B-shaped cell with F's regimes; the same cells under v3.3's own context are an unknown epoch."""
    assert chk_nolag_admitted(tmp_path / "v35")
    camp = nolag_campaign(tmp_path / "v33")
    with pytest.raises(v24.UnknownSchema):
        with v24.use_system("otel"), v33._v33_wrapped(False), v32.v32_context("otel", None, None):
            v31.find_and_load3([camp])


def test_the_profile_is_fs_byte_for_byte_and_the_role_is_campaign_e(tmp_path):
    f = v33.ADDED_PROFILES[EPOCH_F]
    assert v35.NOLAG_PROFILES[EPOCH_NL] == f and f["role"] == "campaign-E"
    with v35._v35_wrapped():
        assert set(v33.profiles_for("otel")) >= {EPOCH_E, EPOCH_F, EPOCH_NL}
        assert v33.profiles_for("otel")[EPOCH_NL]["faultRegimes"] == v33.profiles_for("otel")[EPOCH_F]["faultRegimes"]
        assert v33.profiles_for("teastore").keys() == {"teastore-offpath-v1"}
    camp = nolag_campaign(tmp_path / "c")
    cells = cells35([camp], blocks={1, 2})                       # `--blocks` selects a campaign-E-role epoch's cells by receipt
    assert {c["block"] for c in cells} == {1, 2} and ACCT not in {c["regime"] for c in cells}


def test_the_ablation_is_never_read_with_f_or_e_in_one_run(tmp_path):
    """v3.2's one-new-epoch refusal covers the added epoch (its block numbers would collide with F's in the fold key)."""
    nl = nolag_campaign(tmp_path / "nl")
    for epoch, other in ((EPOCH_F, f_campaign(tmp_path / "of")), (EPOCH_E, t32.offpath_campaign(tmp_path / "oe", epoch=EPOCH_E))):
        with pytest.raises(SystemExit, match="different v3.2 epochs"):
            cells35([nl, other])


def test_any_other_epoch_is_still_refused(tmp_path):
    """Nothing else is admitted in addition: a study epoch outside v3.2's, v3.3's and v3.5's tables stops the run."""
    camp = nolag_campaign(tmp_path / "g", epoch="otel-offpath-g-v1")
    with pytest.raises(v24.UnknownSchema):
        cells35([camp])
    camp = nolag_campaign(tmp_path / "typo", epoch="otel-offpath-f-nolag-v2")
    with pytest.raises(v24.UnknownSchema):
        cells35([camp])


def test_a_regime_outside_the_epoch_stops_the_run(tmp_path):
    """The off-path regimes are F's: the throttle regime of the older epochs is refused here as it is for F."""
    camp = t32.t3._ot_b_campaign(tmp_path / "c")
    t32._set_epoch(camp, EPOCH_NL)
    with pytest.raises(v24.UnknownSchema, match="productcatalog-cpu-throttle-effect"):
        cells35([camp])


def chk_otel_only(_tmp=None, _world=None):
    """A system other than otel is refused (TeaStore would otherwise be read by v3.3's engine, Hotel stops with a KeyError)."""
    refused = 0
    for system, camp in (("teastore", t22.TS_CAMP), ("hotel", t22.TS_CAMP)):
        try:
            v35.run35(camp, system=system, reference=False)
        except SystemExit as exc:
            refused += "reads OTel only" in str(exc)
        except Exception:                            # noqa: BLE001  (the unplanted engine failing differently is not a refusal)
            pass
    return refused == 2


def test_other_systems_are_refused(tmp_path):
    assert chk_otel_only()
    with pytest.raises(SystemExit, match="reads OTel only"):
        v35.main([str(t22.TS_CAMP), "--system", "teastore", "--out", str(tmp_path / "o")])
    assert not (tmp_path / "o").exists()


def test_two_no_fault_cells_of_a_block_stay_two_calibration_cells(tmp_path):
    """As F's (v3.3 test of the same name): runKey.replicate 1 and 2 are two cells, two calibration cells, doubled hours."""
    import shutil
    camp = nolag_campaign(tmp_path / "c")
    nf = t22._cell_dir(camp, t22.OT_NF)
    t22._edit_json(nf / "receipt.json", lambda rc: rc["runKey"].__setitem__("replicate", 1))
    twin = nf.parent / "r1-b01-99-full"
    shutil.copytree(nf, twin)
    t22._edit_json(twin / "receipt.json", lambda rc: rc["runKey"].__setitem__("replicate", 2))
    cells = [c for c in cells35([camp]) if c["regime"] == t22.OT_NF]
    assert len(cells) == 2 and all(c["valid"] for c in cells) and len({c["cellKey"] for c in cells}) == 2
    R = run([camp])
    one = run([nolag_campaign(tmp_path / "one")])
    cal = lambda r: r["cal"]["primary"]["perRate"][1.0]          # noqa: E731
    assert cal(one)["cells"] == 1 and cal(R)["cells"] == 2
    assert abs(cal(R)["hours"] - 2 * cal(one)["hours"]) < 1e-9


# ----------------------------------------------------------------------------- 9: the lag-lane integrity record

def chk_ablation_check(tmp_path, _world=None):
    """A lag gauge in one ablation cell is reported: ablationHolds false, the cell counted, the sensor named."""
    camp = nolag_campaign(tmp_path / "c", lag_in=(FRONT,))
    R = run([camp])
    rec = v35.ablation_record(R, EPOCH_NL)
    return (rec["ablationHolds"] is False and rec["cellsWithLagLaneSensor"] == 1
            and rec["lagLaneSensors"] == ["metric:kafka:kafka.consumer_group.lag"] and "not ablation cells" in rec["note"])


def test_a_clean_ablation_holds_and_keeps_the_coordinator_lane(nl_result):
    rec = v35.ablation_record(nl_result, EPOCH_NL)
    assert rec["ablationHolds"] is True and rec["cellsWithLagLaneSensor"] == 0 and rec["lagLaneSensors"] == []
    assert rec["validCellsOfEpoch"] == 13 and rec["cellsWithCoordinatorLaneSensor"] >= 1 and "note" not in rec
    J = v35.build_json35(nl_result)
    lanes = J["v33"]["lanes"]["regimes"][FRAUD]["episodes"][0]["lanes"]
    assert lanes["lag"]["collectedSensors"] == 0 and lanes["lag"]["earliest"] is None        # `—` by v3.3's own rule
    assert lanes["coordinator"]["earliest"]["sensor"].startswith("log:kafka:")
    assert J["v33"]["lanes"]["regimes"][FRAUD]["byRate"]["1"]["lag"]["withCollectedSensors"] == 0


def test_a_lag_sensor_in_an_ablation_cell_is_reported_not_refused(tmp_path):
    assert chk_ablation_check(tmp_path / "x")
    camp = nolag_campaign(tmp_path / "y", lag_in=(FRONT, FRAUD))
    rec = v35.build_json35(run([camp]))["v35"]["ablation"][EPOCH_NL]
    assert rec["cellsWithLagLaneSensor"] == 2 and rec["ablationHolds"] is False


def test_the_record_is_only_for_the_ablation_epoch(f_world5):
    """F itself is not an ablation epoch: its (lag) sensors are not an integrity failure and no record is made."""
    R = run([f_world5["camp"], f_world5["quiet"]])
    J = v35.build_json35(R)
    assert J["v35"]["ablationEpochsRead"] == [] and J["v35"]["ablation"] == {}
    assert J["v32"]["epochsRead"] == {EPOCH_F: 13}


def test_json_and_markdown_carry_the_v35_block(nl_world, tmp_path):
    out = tmp_path / "ro"
    assert v35.main([str(nl_world["camp"]), str(nl_world["quiet"]), "--system", "otel", "--out", str(out)]) == 0
    J = json.loads((out / v35.OUT_JSON).read_text())
    md = (out / v35.OUT_MD).read_text()
    assert J["version"] == "3.5" and J["scriptSha256"] == v35._sha(v35.__file__)
    assert J["v33ScriptSha256"] == v33._sha(v33.__file__) and J["v32ScriptSha256"] == v32._sha(v32.__file__)
    assert J["v31ScriptSha256"] == v31._sha(v31.__file__)
    assert J["v35"]["parametersV35Sha256"] == v35._sha(v35.PARAMETERS_V35)
    assert J["v33"]["parametersV33Sha256"] == v33._sha(v33.PARAMETERS_V33)
    assert J["v32"]["parametersV32Sha256"] == v32._sha(v32.PARAMETERS_V32)
    assert J["v32"]["epochsRead"] == {EPOCH_NL: 13} and all(e["studyEpoch"] == EPOCH_NL for e in J["episodes"])
    assert J["v35"]["ablationEpochsRead"] == [EPOCH_NL] and J["v35"]["ablation"][EPOCH_NL]["ablationHolds"] is True
    assert "## v3.3 additions" in md and "## v3.5 additions" in md and "### Lag-lane integrity, `%s`" % EPOCH_NL in md
    assert set(J["v35"]["parametersV35"]) == {"V35_EPOCH_PROFILES", "V35_ABLATION", "V35_REPORT_RULE"}
    with pytest.raises(SystemExit):
        v35.main([str(nl_world["camp"]), "--system", "otel", "--out", str(out)])


# ----------------------------------------------------------------------------- v3.5 on F equals v3.3

def _diff(a, b, path=""):
    """Dotted paths at which two JSON documents differ (lists compared whole at the first differing element's parent)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append((path + "." + k).lstrip("."))
            else:
                out += _diff(a[k], b[k], path + "." + k)
        return out
    return [] if a == b else [path.lstrip(".")]


IDENTITY = {"version", "label", "script", "scriptSha256", "generatedAt", "frameworkCommit", "v33ScriptSha256", "v35"}
ADMISSION_LISTS = {"v32.epochsAdmittedExplicitly", "v32.blockSelection.applies", "v33.epochsAddedByV33"}


def test_a_v35_read_of_f_equals_v33s(f_world5):
    """The same F fixture through v3.3 and through v3.5: every key equal but the identity keys, v3.5's new keys, and the three lists
    that name what a reader admits (v3.3 gained F in the same three over v3.2)."""
    camps = [f_world5["camp"], f_world5["quiet"]]
    R3 = v33.run33(camps, system="otel", reference=False)
    with v24.use_system("otel"):
        v31.finish(R3)
    J3 = json.loads(json.dumps(v33.build_json33(R3), default=sorted))
    J5 = json.loads(json.dumps(v35.build_json35(run(camps)), default=sorted))
    got = set(_diff(J3, J5))
    required = {"version", "label", "script", "scriptSha256", "v33ScriptSha256", "v35"} | ADMISSION_LISTS
    assert required <= got <= IDENTITY | ADMISSION_LISTS, got ^ required
    assert J3["v33"]["epochsAddedByV33"] == [EPOCH_F] and J5["v33"]["epochsAddedByV33"] == sorted([EPOCH_F, EPOCH_NL])
    assert J3["v32"]["epochsAdmittedExplicitly"] == sorted(set(J5["v32"]["epochsAdmittedExplicitly"]) - {EPOCH_NL})
    assert EPOCH_NL in J5["v32"]["blockSelection"]["applies"] and EPOCH_NL not in J3["v32"]["blockSelection"]["applies"]
    for k in ("episodes", "calibration", "perSensor", "predictions", "secondary", "validation"):
        assert J3[k] == J5[k], k


def test_rebinding_is_restored_on_exit():
    before = (v33.ADDED_PROFILES, v32.EPOCH_PROFILES, v32.v32_context, v33.LANE_RULES, v31.find_and_load3, v24.FAULT_REGIMES)
    with v35._v35_wrapped():
        assert EPOCH_NL in v33.ADDED_PROFILES and v33.ADDED_PROFILES is not before[0]
    with pytest.raises(RuntimeError):
        with v35._v35_wrapped():
            raise RuntimeError("x")
    after = (v33.ADDED_PROFILES, v32.EPOCH_PROFILES, v32.v32_context, v33.LANE_RULES, v31.find_and_load3, v24.FAULT_REGIMES)
    assert all(a is b for a, b in zip(before, after)) and EPOCH_NL not in v33.ADDED_PROFILES
    assert v33.ADDED_PROFILES == v35.V33_ADDED


def _exec_with_registry(tmp_path, edit):
    """Execute the reader's source with its registry path pointed at an edited copy (the import-time assertions run on it)."""
    doc = json.loads(v35.PARAMETERS_V35.read_text())
    edit(doc)
    reg = tmp_path / "parameters_v3_5.json"
    reg.write_text(json.dumps(doc))
    src = Path(v35.__file__).read_text().replace('REPO / "research" / "protocol" / "parameters_v3_5.json"', repr(str(reg)))
    assert str(reg) in src
    ns = {"__name__": "v35_planted", "__file__": v35.__file__}
    exec(compile(src, v35.__file__, "exec"), ns)          # noqa: S102
    return ns


def _profile(doc):
    return next(p for p in doc["parameters"] if p["name"] == "V35_EPOCH_PROFILES")["value"]


def test_planted_registry_defects_are_refused_at_import(tmp_path):
    """The registry's profile must be F's byte for byte and the registry must add exactly one epoch: a profile that differs
    from F's (rate 50 here), a second epoch, or an epoch v3.3 already admits stops the import."""
    (tmp_path / "ok").mkdir()
    assert _exec_with_registry(tmp_path / "ok", lambda d: None)["LABEL"] == v35.LABEL        # the unedited copy imports
    for name, edit in (("rate", lambda d: _profile(d)[EPOCH_NL]["design"].__setitem__("requestsPerSecond", 50.0)),
                       ("regime", lambda d: _profile(d)[EPOCH_NL]["faultRegimes"].pop("frontend-pause-effect")),
                       ("second", lambda d: _profile(d).__setitem__("otel-offpath-g-v1", dict(_profile(d)[EPOCH_NL]))),
                       ("redefine", lambda d: _profile(d).__setitem__(EPOCH_F, _profile(d).pop(EPOCH_NL)))):
        (tmp_path / name).mkdir()
        with pytest.raises(AssertionError):
            _exec_with_registry(tmp_path / name, edit)


# ----------------------------------------------------------------------------- the frozen files are untouched

FROZEN = {   # FREEZE_V33_20261014.md / FREEZE_V34_20261015.md digest tables
    "research/detection-time/sweep_analysis_v3_3.py": "c8cd5072ed4b22cae9360e6446f969c75b4e66b900a08d3cfe0efbdadcd36e18",
    "research/protocol/parameters_v3_3.json": "a85daa482b487e4600d11c91dbdecac9a98b01fcd542b9ef051c06cf1268f4b7",
    "research/placement/celf_v3_3.py": "5d801f634d4d359a0b49c51faf390244eee99c09241c99bc778f0e20929d1ead",
    "research/placement/score_test_v3_3.py": "704cf341ae23e09a123915e14b4546dc1e3b02b3cf7bf2fa4808059acbd2e442",
    "research/detection-time/sweep_analysis_v3_4.py": "caad8672867b165910bbd0dc15090aee1e67ddaded0f2daffee7410cb2b3410d",
    "research/protocol/parameters_v3_4.json": "7b8b921fe341df1895a6c6d1d1dd97a553e6c0bfdd6677522ba25d65905da7e6",
    "research/detection-time/sweep_analysis_v3_2.py": "97eb0a1d4f3f7e0daecee447113fdd14bd14b84812f420ddb3903bfe16759465",
    "research/protocol/parameters_v3_2.json": "ab4a5af7243e776f536b09a39e649b1be968d23f1767ef2f5a166ac08e340a67",
    "research/placement/celf_v3_2.py": "cc7157d858ce3a92fd236e0ce982a7421b4f2a69ad81b06a5ea59b7fb8b88e12",
    "research/placement/score_test_v3_2.py": "f9942b9138f1d1216ed3d3466949c727f6388980e24fff4ce40af994fbf64a07",
    "research/detection-time/sweep_analysis_v3.py": "2e7ec5c387fa906a02026f0d1a5212b974f17751c24f76526a1d8418b2fd4fdd",
    "research/detection-time/sweep_analysis_v2.py": "075c43e5870170c8b59cdbe1a970b56dc03920d67514027b9a95e5de38d962e9",
    "research/protocol/parameters_v3.json": "212830bec3e6669bc211d5cffa48d61fa3bf0f6d4dd5ceaf79d3e2bcc7c4d000",
    "research/otel-offpath/adapter.py": "22f627dcd1bffdf3f92a151e0d9935f9e2b284a07c905737594d1e95f40bc0b9",
    "research/protocol/split_f_otel.json": "107cb13aeb52e009754744b136f33b63af69c67d9a2b50e8d9bce14a0e719844",
}


def test_the_frozen_chain_and_the_adapter_are_byte_identical():
    for rel, sha in FROZEN.items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == sha, rel


def test_status_label_and_registry():
    assert v35.LABEL == "frozen v3.5 for the OTel F ablation epoch otel-offpath-f-nolag-v1 (FREEZE_V35_20261015.md)"
    assert "STATUS: FROZEN by digest (research/protocol/FREEZE_V35_20261015.md)" in v35.__doc__
    for n, p in v35.REGISTRY35.items():
        assert p["origin_ref"] and p["origin_type"] in ("decision", "literature", "measured", "upstream", "engineering default",
                                                        "unknown")
        assert p["status"] == "active", n
    assert v35.PARAMS_USED35 == set(v35.REGISTRY35) == {"V35_EPOCH_PROFILES", "V35_ABLATION", "V35_REPORT_RULE"}


def test_v35_adds_one_epoch_and_never_redefines():
    assert set(v35.NOLAG_PROFILES) == {EPOCH_NL} and not set(v35.NOLAG_PROFILES) & (set(v33.ADDED_PROFILES) | set(v33.V32_PROFILES))
    assert v33.ADDED_PROFILES == v35.V33_ADDED and EPOCH_NL not in v33.ADDED_PROFILES
    assert v35.ABLATION[EPOCH_NL]["designEpoch"] == EPOCH_F


def test_the_registry_pins_the_ablation_harness_commit():
    doc = json.loads(v35.PARAMETERS_V35.read_text())
    assert "4ab4433352e17818d19851434b8ffe73a1b26700" in doc["provenanceRule"]
    assert "a65f4e33ae7698cfc6bd43829857bfda02030af546e712a471687031f1ca4dd8" in doc["provenanceRule"]


# ----------------------------------------------------------------------------- planted defects: each switch has a check

CHECKS = {"ADMIT_NOLAG": chk_nolag_admitted, "OTEL_ONLY": chk_otel_only, "ABLATION_CHECK": chk_ablation_check}


def _passes(chk, tmp_path):
    try:
        return bool(chk(tmp_path, None))
    except (v24.UnknownSchema, SystemExit, AssertionError, StopIteration, KeyError):
        return False


@pytest.mark.parametrize("flag", sorted(CHECKS))
def test_check_passes_and_fails_with_its_switch_off(flag, tmp_path, monkeypatch):
    """Each v3.5 switch has a check that passes, and fails (or stops) once the switch is planted off."""
    assert _passes(CHECKS[flag], tmp_path / "on"), flag
    monkeypatch.setattr(v35, flag, False)
    assert not _passes(CHECKS[flag], tmp_path / "off"), flag


def test_every_switch_has_a_check():
    switches = {k for k, v in vars(v35).items() if k.isupper() and isinstance(v, bool)}
    assert switches == set(CHECKS) == set(v35.SWITCHES), switches ^ set(CHECKS)
