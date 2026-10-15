"""The v3.5 wrappers (research/placement/celf_v3_5.py, research/placement/score_test_v3_5.py): thin layers that accept v3.5 readouts (the
OTel F ablation epoch otel-offpath-f-nolag-v1) over the frozen v3.2 / v3.3 placement and scorer. Synthetic ablation campaign of
tests/test_sweep_analysis_v3_5.py (no ablation cell was read); each pin of the wrappers is enforced, and each check has a planted defect that
it catches.
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
from test_sweep_analysis_v3_5 import (EPOCH_NL, _no_registry_split, f_world5, nl_world)  # noqa: E402,F401  (fixtures)

v33, v32 = v35.v33, v35.v32


def _chain_files(world, tmp_path, monkeypatch):
    import celf_v3_2 as c2
    import score_test_v3_2 as s2
    for mod in (v32, c2, s2):
        monkeypatch.setattr(mod, "E_SPLIT", {"train": [1, 2], "test": [3]})
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"train": [1, 2], "test": [3]}))
    tr, full = tmp_path / "train", tmp_path / "full"
    base = [str(world["camp"]), str(world["quiet"]), "--system", "otel", "--split", str(split)]
    assert v35.main(base + ["--out", str(tr), "--blocks", "1", "2"]) == 0
    assert v35.main(base + ["--out", str(full), "--test-blocks", "3"]) == 0
    tiers = tmp_path / "tiers.json"
    tiers.write_text(json.dumps({"schemaVersion": 1, "system": "otel", "postureCatalogs": {"v3": {}, "current": {}},
                                 "postureCostEvidence": {"steps": {k: {"share_of_none_level": s} for k, s in (
                                     ("none_to_selected", 0.17), ("selected_to_async", 0.058), ("async_to_full", 0.06))}},
                                 "sensors": [{"id": "span:frontend:x", "effortTier": 0,
                                              "postures": ["none", "selected", "async", "full"],
                                              "postureCurrentCatalog": ["none", "selected", "async", "full"]}]}))
    return split, tr / v35.OUT_JSON, full / v35.OUT_JSON, tiers


def test_reader_to_placement_to_scorer_chain_v35(nl_world, tmp_path, monkeypatch):
    """Reader v3.5 (--blocks train) -> celf_v3_5 -> reader (all blocks) -> score_test_v3_5 on the synthetic ablation campaign: every stage
    accepts the previous stage's file; the v3.2 and v3.3 wrappers refuse v3.5 files and the v3.5 ones refuse v3.3 files."""
    import celf_v3_2 as c2
    import celf_v3_3 as c3
    import celf_v3_5 as c5
    import score_test_v3_3 as s3
    import score_test_v3_5 as s5
    split, tr, full, tiers = _chain_files(nl_world, tmp_path, monkeypatch)
    Jt = json.loads(tr.read_text())
    assert Jt["version"] == "3.5" and EPOCH_NL in Jt["v32"]["blockSelection"]["applies"]
    args = [str(tr), "--tiers", str(tiers), "--tier-catalog", "postureCurrentCatalog", "--split", str(split), "--allow-unpinned"]
    with pytest.raises(SystemExit, match="not v3.2"):                       # the frozen v3.2 placement takes v3.2 files only
        c2.main(args + ["--out", str(tmp_path / "p32.json")])
    with pytest.raises(SystemExit, match="not v3.3"):                       # and the v3.3 one v3.3 files only
        c3.main(args + ["--out", str(tmp_path / "p33.json")])
    no_flag = [a for a in args if a != "--allow-unpinned"]
    assert c5.PINNED_V35_SHA256 and c5.PINNED_PARAMETERS_V35_SHA256         # frozen: the v3.5 layer needs no flag
    with monkeypatch.context() as mp:                                       # the unpinned branches, patched in on purpose
        mp.setattr(c5, "PINNED_V35_SHA256", None)
        with pytest.raises(SystemExit, match="reader is not frozen"):
            c5.main(no_flag + ["--out", str(tmp_path / "p0.json")])
        mp.setattr(c5, "PINNED_PARAMETERS_V35_SHA256", None)
        mp.setattr(c5, "PINNED_V35_SHA256", c5.sha256(c5.READER_V35))
        with pytest.raises(SystemExit, match="registry is not frozen"):
            c5.main(no_flag + ["--out", str(tmp_path / "p0b.json")])
    with pytest.raises(SystemExit, match="--tier-catalog"):                 # the ablation epoch calls for the current runtime catalog
        c5.main([str(tr), "--tiers", str(tiers), "--tier-catalog", "postures", "--split", str(split), "--out", str(tmp_path / "pc.json")])
    assert c5.expected_catalog(Jt) == "postureCurrentCatalog" and c3.expected_catalog(c5.v33_view(Jt)) == "postures"
    pl = tmp_path / "placement.json"
    assert c5.main(no_flag + ["--out", str(pl)]) == 0                       # pinned digests: accepted without a flag
    P = json.loads(pl.read_text())
    assert P["version"] == "placement-v3.5" and P["split"]["trainBlocks"] == [1, 2]
    assert P["inputs"]["parametersV35Sha256"] == v35._sha(v35.PARAMETERS_V35) and P["inputs"]["pinnedV35"] == c5.PINNED_V35_SHA256
    assert P["inputs"]["pinnedParametersV35"] == c5.PINNED_PARAMETERS_V35_SHA256
    assert P["inputs"]["parametersV33Sha256"] == v33._sha(v33.PARAMETERS_V33) and P["inputs"]["script"].endswith("celf_v3_5.py")
    with pytest.raises(SystemExit, match="every block"):                    # decision 95, through the v3.2 layer
        c5.main([str(full)] + args[1:] + ["--out", str(tmp_path / "p2.json")])
    old = json.loads(tr.read_text())
    old["version"] = "3.3"
    (tmp_path / "old.json").write_text(json.dumps(old))
    with pytest.raises(SystemExit, match="is not v3.5"):
        c5.main([str(tmp_path / "old.json")] + args[1:] + ["--out", str(tmp_path / "p3.json")])
    score = tmp_path / "score.json"
    sargs = [str(full), "--placement", str(pl), "--training-readout", str(tr), "--test-blocks", "3"]
    assert s5.PINNED_PLACEMENTS == {}
    with pytest.raises(SystemExit, match="no pinned placement"):            # reader and registry are pinned; the placement is not
        s5.main(sargs + ["--out", str(tmp_path / "s0.json")])
    with pytest.raises(SystemExit, match="is not v3.3"):                    # F's frozen scorer takes v3.3 readouts only
        s3.main(sargs + ["--out", str(tmp_path / "s3.json"), "--allow-unpinned"])
    assert s5.main(sargs + ["--out", str(score), "--allow-unpinned"]) == 0
    res = json.loads(score.read_text())
    assert res["version"] == "score-test-v3.5" and res["splitCheck"]["trainBlocks"] == [1, 2]
    assert res["splitCheck"]["testBlocks"] == [3] and res["inputs"]["scoreTestV32Sha256"]
    assert res["inputs"]["parametersV35Sha256"] == v35._sha(v35.PARAMETERS_V35)
    import score_test_v3_2 as s2
    assert s2.VERSION == "score-test-v3.2" and s2.check_readout is s5._ORIG_CHECK_READOUT       # restored after the call
    # the recorded-pin path (what score_nolag.py does): the pin replaces the missing one and a different digest is refused
    psha = c5.sha256(pl)
    with monkeypatch.context() as mp:
        mp.setattr(s5, "PINNED_PLACEMENTS", {"otel": psha})
        assert s5.main(sargs + ["--out", str(tmp_path / "s_pinned.json")]) == 0
        mp.setattr(s5, "PINNED_PLACEMENTS", {"otel": "0" * 64})
        with pytest.raises(SystemExit, match="is not the frozen"):
            s5.main(sargs + ["--out", str(tmp_path / "s_wrong.json")])


def chk_c5_pin(tmp_path, _world=None, monkeypatch=None):
    """A readout whose v3.5 reader digest is not the installed one is refused by the v3.5 layer."""
    import celf_v3_5 as c5
    J = json.loads((tmp_path / "ro.json").read_text())
    J["scriptSha256"] = "0" * 64
    try:
        c5.check_v35_layer(J, "the readout", allow_unpinned=True)
    except SystemExit:
        return True
    return False


def test_wrapper_pin_checks_fail_on_planted_defects(nl_world, tmp_path, monkeypatch):
    import celf_v3_5 as c5
    import score_test_v3_5 as s5
    split, tr, full, tiers = _chain_files(nl_world, tmp_path, monkeypatch)
    (tmp_path / "ro.json").write_text(tr.read_text())
    assert chk_c5_pin(tmp_path)
    monkeypatch.setattr(c5, "CHECK_PINS", False)                        # planted: the v3.5 layer is not checked
    assert not chk_c5_pin(tmp_path)
    monkeypatch.setattr(c5, "CHECK_PINS", True)
    P = {"system": "otel", "version": c5.VERSION, "inputs": {"celfSha256": "0" * 64}}
    with pytest.raises(SystemExit, match="frozen celf_v3"):
        s5.check_placement(P, "x", {"system": "otel"}, allow_unpinned=True)
    monkeypatch.setattr(s5, "ENFORCE_PINS", False)                      # planted: the placement checks are not made
    s5.check_placement(P, "x", {"system": "otel"}, allow_unpinned=True)
    monkeypatch.setattr(s5, "ENFORCE_PINS", True)
    good = {"celfSha256": c5.c2.PINNED_CELF_SHA256, "parametersV32Sha256": c5.c2.PINNED_PARAMETERS_V32_SHA256,
            "parametersV33Sha256": c5.c3.PINNED_PARAMETERS_V33_SHA256, "parametersV35Sha256": c5.PINNED_PARAMETERS_V35_SHA256}
    s5.check_placement(dict(P, inputs=good), "x", {"system": "otel"}, allow_unpinned=True)
    for k in ("parametersV32Sha256", "parametersV33Sha256", "parametersV35Sha256"):      # each registry digest is checked
        with pytest.raises(SystemExit, match="digest|frozen|recorded"):
            s5.check_placement(dict(P, inputs=dict(good, **{k: "0" * 64})), "x", {"system": "otel"}, allow_unpinned=True)
    with pytest.raises(SystemExit, match="not placement-v3.5"):         # a v3.3 placement is refused
        s5.check_placement(dict(P, version="placement-v3.3", inputs=good), "x", {"system": "otel"}, allow_unpinned=True)
    with pytest.raises(SystemExit, match="no pinned placement"):
        s5.check_placement(dict(P, inputs=good), "x", {"system": "otel"})
    with pytest.raises(SystemExit, match="placement system"):
        s5.check_placement(dict(P, inputs=good), "x", {"system": "teastore"}, allow_unpinned=True)


def test_the_frozen_pins_equal_the_files():
    """The reader and registry pins of celf_v3_5 (mirrored in score_test_v3_5) are the digests of the files; a changed file is refused by the
    v3.5 layer, a changed pin too; the scorer pins no placement."""
    import celf_v3_5 as c5
    import score_test_v3_5 as s5
    assert c5.PINNED_V35_SHA256 == hashlib.sha256(Path(v35.__file__).read_bytes()).hexdigest()
    assert c5.PINNED_PARAMETERS_V35_SHA256 == hashlib.sha256(v35.PARAMETERS_V35.read_bytes()).hexdigest()
    assert (s5.PINNED_V35_SHA256, s5.PINNED_PARAMETERS_V35_SHA256) == (c5.PINNED_V35_SHA256, c5.PINNED_PARAMETERS_V35_SHA256)
    assert c5.PINNED_V35_SHA256 == c5.sha256(c5.READER_V35) and c5.PINNED_PARAMETERS_V35_SHA256 == c5.sha256(c5.PARAMETERS_V35)
    assert s5.PINNED_PLACEMENTS == {}                                       # no placement of the ablation exists at the freeze
    assert set(s5.SAME_ACROSS_READOUTS) >= {"v35.parametersV35Sha256", "v33ScriptSha256", "v33.parametersV33Sha256", "v32ScriptSha256"}


def test_a_changed_pin_is_refused_and_the_planted_one_is_caught(monkeypatch):
    import celf_v3_5 as c5
    J = {"version": "3.5", "scriptSha256": c5.PINNED_V35_SHA256, "v35": {"parametersV35Sha256": c5.PINNED_PARAMETERS_V35_SHA256}}
    c5.check_v35_layer(J, "the readout")                                    # pinned digests: accepted without a flag
    monkeypatch.setattr(c5, "PINNED_PARAMETERS_V35_SHA256", "0" * 64)       # a registry edited after the freeze
    with pytest.raises(SystemExit, match="not the frozen"):
        c5.check_v35_layer(J, "the readout")
    monkeypatch.setattr(c5, "PINNED_PARAMETERS_V35_SHA256", c5.sha256(c5.PARAMETERS_V35))
    monkeypatch.setattr(c5, "PINNED_V35_SHA256", "0" * 64)                  # a reader edited after the freeze
    with pytest.raises(SystemExit, match="is not the frozen v3.5"):
        c5.check_v35_layer(J, "the readout")


def test_v33_and_v32_layers_are_checked_through_the_view(nl_world, tmp_path, monkeypatch):
    """A v3.5 readout whose recorded v3.3 reader digest is not the frozen one is refused by celf_v3_3's layer, one whose v3.2 digest is not by
    celf_v3_2's: the v3.5 wrapper does not skip the earlier layers."""
    import celf_v3_5 as c5
    split, tr, full, tiers = _chain_files(nl_world, tmp_path, monkeypatch)
    J = json.loads(tr.read_text())
    c5.check_readout(J, allow_unsplit=False)
    with pytest.raises(SystemExit, match="v3.3"):
        c5.check_readout(dict(J, v33ScriptSha256="0" * 64))
    with pytest.raises(SystemExit, match="v3.2"):
        c5.check_readout(dict(J, v32ScriptSha256="0" * 64))
    with pytest.raises(SystemExit, match="v3.1"):
        c5.check_readout(dict(J, v31ScriptSha256="0" * 64))
