"""The v3.6 wrappers (research/placement/celf_v3_6.py, research/placement/score_test_v3_6.py): thin layers that accept v3.6 readouts (the
TeaStore off-path epoch read as campaign-E) over the frozen v3.2 / v3.3 placement and scorer, without a tier file, under the v3.6
registry's pass rule. Synthetic TeaStore campaign of tests/test_sweep_analysis_v3_6.py (blocks 1-2 train, 3 test); each new switch has a
planted defect that its check catches.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "detection-time"))
sys.path.insert(0, str(ROOT / "research" / "placement"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sweep_analysis_v3_6 as v36  # noqa: E402
from test_sweep_analysis_v3_3 import REC  # noqa: E402
from test_sweep_analysis_v3_6 import ts3_campaign  # noqa: E402

v33, v32 = v36.v33, v36.v32
SPLIT3 = {"train": [1, 2], "test": [3]}


@pytest.fixture(autouse=True)
def _pre_pin(monkeypatch):
    """These tests model the scorer before freeze step 2 (no pinned placement), whatever the installed file pins; the step-2
    test sets its own pin. Added for review note N1 (FREEZE_V36_20261015.md, step-1 amendment)."""
    import score_test_v3_6 as s
    monkeypatch.setattr(s, "PINNED_PLACEMENTS", {})


@pytest.fixture
def chain(tmp_path, monkeypatch):
    import celf_v3_2 as c2
    import score_test_v3_2 as s2
    for mod in (v32, c2, s2):
        monkeypatch.setattr(mod, "E_SPLIT", SPLIT3)
    import celf_v3_6 as c6
    reg = c6._registry36()                                  # the fixture's rate is 0.2: the registry rule's rates, moved to it
    reg = dict(reg, V36_PASS_RULE=[dict(r, rate=0.2) for r in reg["V36_PASS_RULE"]][:1])
    monkeypatch.setattr(c6, "_registry36", lambda: json.loads(json.dumps(reg)))
    camp = ts3_campaign(tmp_path / "c")
    split = tmp_path / "split.json"
    split.write_text(json.dumps(SPLIT3))
    tr, full = tmp_path / "train", tmp_path / "full"
    base = [str(camp), "--system", "teastore", "--split", str(split)]
    assert v36.main(base + ["--out", str(tr), "--blocks", "1", "2"]) == 0
    assert v36.main(base + ["--out", str(full), "--test-blocks", "3"]) == 0
    return {"tmp": tmp_path, "split": split, "tr": tr / v36.OUT_JSON, "full": full / v36.OUT_JSON}


def _place(ch, name, extra=()):
    import celf_v3_6 as c6
    out = ch["tmp"] / name
    c6.main([str(ch["tr"]), "--tier-catalog", "postureCurrentCatalog", "--split", str(ch["split"]), "--out", str(out)] + list(extra))
    return out


def _score(ch, pl, name, extra=()):
    import score_test_v3_6 as s6
    out = ch["tmp"] / name
    s6.main([str(ch["full"]), "--placement", str(pl), "--training-readout", str(ch["tr"]), "--test-blocks", "3", "--out", str(out)]
            + list(extra))
    return json.loads(out.read_text())


def test_reader_to_placement_to_scorer_chain_v36(chain, monkeypatch):
    import celf_v3_3 as c3
    import celf_v3_6 as c6
    import score_test_v3_2 as s2
    import score_test_v3_6 as s6
    args = [str(chain["tr"]), "--tiers", "x", "--tier-catalog", "postureCurrentCatalog", "--split", str(chain["split"])]
    with pytest.raises(SystemExit, match="not v3.3"):                       # the frozen v3.3 placement takes v3.3 files only
        c3.main(args + ["--allow-unpinned", "--out", str(chain["tmp"] / "p33.json")])
    pl = _place(chain, "placement.json")
    P = json.loads(pl.read_text())
    assert P["version"] == "placement-v3.6" and P["split"]["trainBlocks"] == [1, 2] and P["system"] == "teastore"
    assert P["tiers"]["sensors"] == 0 and P["tiers"]["path"] is None and P["inputs"]["tiers"] is None
    for rk, R in P["rates"].items():
        if "groundSet" in R:
            assert sorted(R["tiersMissingForGroundSet"]) == sorted(R["groundSet"]), rk
    assert P["inputs"]["parametersV36Sha256"] == v36._sha(v36.PARAMETERS_V36) and P["inputs"]["script"].endswith("celf_v3_6.py")
    assert s6.PINNED_PLACEMENTS == {}
    with pytest.raises(SystemExit, match="no pinned placement"):
        _score(chain, pl, "s0.json")
    res = _score(chain, pl, "s.json", ["--allow-unpinned"])
    assert res["version"] == "score-test-v3.6" and res["splitCheck"]["testBlocks"] == [3]
    assert res["passRule"] == [dict(r, rate="0.2") for r in v36.REGISTRY36["V36_PASS_RULE"]["value"]][:1]
    assert res["inputs"]["passRuleSource"].startswith("V36_PASS_RULE")
    classes = {v["rule"]["class"] for R in res["rates"].values() for v in R.get("verdicts", [])}
    assert classes <= {REC}
    assert s2.VERSION == "score-test-v3.2" and s2.check_readout is s6._ORIG_CHECK_READOUT       # restored after the call
    psha = c6.sha256(pl)
    with monkeypatch.context() as mp:                                         # step 2 of the freeze: the pinned placement
        mp.setattr(s6, "PINNED_PLACEMENTS", {"teastore": psha})
        assert _score(chain, pl, "s_pinned.json")["version"] == "score-test-v3.6"
        mp.setattr(s6, "PINNED_PLACEMENTS", {"teastore": "0" * 64})
        with pytest.raises(SystemExit, match="is not the frozen"):
            _score(chain, pl, "s_wrong.json")


def chk_teastore_only(chain):
    """celf_v3_6 places a TeaStore readout only."""
    J = json.loads(chain["tr"].read_text())
    J["system"] = "otel"
    bad = chain["tmp"] / "otel.json"
    bad.write_text(json.dumps(J))
    import celf_v3_6 as c6
    try:
        c6.main([str(bad), "--tier-catalog", "postureCurrentCatalog", "--split", str(chain["split"]), "--allow-unpinned",
                 "--allow-catalog-mismatch", "--out", str(chain["tmp"] / "po.json")])
    except SystemExit as exc:
        return "TeaStore off-path epoch only" in str(exc)
    return False


def chk_no_tier_file(chain):
    """Without a tier file every ground-set sensor is tier-missing, so only the any/any cell admits it."""
    P = json.loads(_place(chain, "pt-%d.json" % id(chain), ["--allow-unpinned"]).read_text())
    rates = [R for R in P["rates"].values() if "groundSet" in R]
    return bool(rates) and all(R["groundSet"] and sorted(R["tiersMissingForGroundSet"]) == sorted(R["groundSet"]) for R in rates)


def chk_rule_from_v36(chain):
    """The scorer's verdicts are the v3.6 rule's (recommender class), not v3.2's OTel classes."""
    pl = _place(chain, "pr-%d.json" % id(chain), ["--allow-unpinned"])
    res = _score(chain, pl, "sr-%d.json" % id(chain), ["--allow-unpinned"])
    classes = {v["rule"]["class"] for R in res["rates"].values() for v in R.get("verdicts", [])}
    return classes == {REC}


def chk_c6_pin(chain):
    """A readout whose v3.6 reader digest is not the installed one is refused by the v3.6 layer."""
    import celf_v3_6 as c6
    J = json.loads(chain["tr"].read_text())
    J["scriptSha256"] = "0" * 64
    try:
        c6.check_v36_layer(J, "the readout", allow_unpinned=True)
    except SystemExit:
        return True
    return False


CHECKS = {("celf_v3_6", "TEASTORE_ONLY"): chk_teastore_only, ("celf_v3_6", "NO_TIER_FILE"): chk_no_tier_file,
          ("celf_v3_6", "CHECK_PINS"): chk_c6_pin, ("score_test_v3_6", "RULE_FROM_V36"): chk_rule_from_v36}


@pytest.mark.parametrize("mod,flag", sorted(CHECKS))
def test_check_passes_and_fails_with_its_switch_off(mod, flag, chain, monkeypatch):
    import importlib
    m = importlib.import_module(mod)
    assert CHECKS[(mod, flag)](chain), flag
    monkeypatch.setattr(m, flag, False)
    try:
        ok = CHECKS[(mod, flag)](chain)
    except (SystemExit, AssertionError, KeyError):
        ok = False
    assert not ok, flag


def test_mirrored_pins_are_celf_v3_6s():
    import celf_v3_6 as c6
    import score_test_v3_6 as s6
    assert s6.PINNED_V36_SHA256 == c6.PINNED_V36_SHA256 and s6.PINNED_PARAMETERS_V36_SHA256 == c6.PINNED_PARAMETERS_V36_SHA256
