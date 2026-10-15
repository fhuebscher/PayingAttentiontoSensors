"""The v3.3 wrappers (research/placement/celf_v3_3.py, research/placement/score_test_v3_3.py): thin layers over the frozen v3.2
placement and scorer that accept v3.3 readouts. Synthetic F campaign of tests/test_sweep_analysis_v3_3.py; every pin of the
wrappers is None (the coordinator sets them at the freeze), and each check has a planted defect that it catches.
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

import sweep_analysis_v3_3 as v33  # noqa: E402
from test_sweep_analysis_v3_3 import (EPOCH_E, EPOCH_F, _no_registry_split, f_world)  # noqa: E402,F401  (fixtures)

v32 = v33.v32


def _chain_files(f_world, tmp_path, monkeypatch):
    import celf_v3_2 as c2
    import score_test_v3_2 as s2
    for mod in (v32, c2, s2):
        monkeypatch.setattr(mod, "E_SPLIT", {"train": [1, 2], "test": [3]})
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"train": [1, 2], "test": [3]}))
    tr, full = tmp_path / "train", tmp_path / "full"
    base = [str(f_world["camp"]), str(f_world["quiet"]), "--system", "otel", "--split", str(split)]
    assert v33.main(base + ["--out", str(tr), "--blocks", "1", "2"]) == 0
    assert v33.main(base + ["--out", str(full), "--test-blocks", "3"]) == 0
    tiers = tmp_path / "tiers.json"
    tiers.write_text(json.dumps({"schemaVersion": 1, "system": "otel", "postureCatalogs": {"v3": {}, "current": {}},
                                 "postureCostEvidence": {"steps": {k: {"share_of_none_level": s} for k, s in (
                                     ("none_to_selected", 0.17), ("selected_to_async", 0.058), ("async_to_full", 0.06))}},
                                 "sensors": [{"id": "span:frontend:x", "effortTier": 0,
                                              "postures": ["none", "selected", "async", "full"],
                                              "postureCurrentCatalog": ["none", "selected", "async", "full"]}]}))
    return split, tr / v33.OUT_JSON, full / v33.OUT_JSON, tiers


def test_reader_to_placement_to_scorer_chain_v33(f_world, tmp_path, monkeypatch):
    """Reader v3.3 (--blocks train) -> celf_v3_3 -> reader (all blocks) -> score_test_v3_3 on the synthetic F campaign: every
    stage accepts the previous stage's file; the v3.2 wrappers refuse v3.3 files and the v3.3 ones refuse v3.2 files."""
    import celf_v3_2 as c2
    import celf_v3_3 as c3
    import score_test_v3_3 as s3
    split, tr, full, tiers = _chain_files(f_world, tmp_path, monkeypatch)
    Jt = json.loads(tr.read_text())
    assert Jt["version"] == "3.3" and Jt["v32"]["blockSelection"]["applies"] == [EPOCH_E, EPOCH_F, ]
    args = [str(tr), "--tiers", str(tiers), "--tier-catalog", "postureCurrentCatalog", "--split", str(split),
            "--allow-unpinned"]
    with pytest.raises(SystemExit, match="not v3.2"):                       # the frozen v3.2 placement takes v3.2 files only
        c2.main(args + ["--out", str(tmp_path / "p32.json")])
    no_flag = [a for a in args if a != "--allow-unpinned"]
    assert c3.PINNED_V33_SHA256 and c3.PINNED_PARAMETERS_V33_SHA256               # frozen: the v3.3 layer needs no flag
    with monkeypatch.context() as mp:                                       # the unpinned branch, patched in on purpose
        mp.setattr(c3, "PINNED_V33_SHA256", None)
        with pytest.raises(SystemExit, match="reader is not frozen"):
            c3.main(no_flag + ["--out", str(tmp_path / "p0.json")])
        mp.setattr(c3, "PINNED_PARAMETERS_V33_SHA256", None)
        mp.setattr(c3, "PINNED_V33_SHA256", c3.sha256(c3.READER_V33))
        with pytest.raises(SystemExit, match="registry is not frozen"):
            c3.main(no_flag + ["--out", str(tmp_path / "p0b.json")])
    pl = tmp_path / "placement.json"
    assert c3.main(args + ["--out", str(pl)]) == 0
    P = json.loads(pl.read_text())
    assert P["version"] == "placement-v3.3" and P["split"]["trainBlocks"] == [1, 2]
    assert P["inputs"]["parametersV33Sha256"] == v33._sha(v33.PARAMETERS_V33) and P["inputs"]["pinnedV33"] == c3.PINNED_V33_SHA256
    assert P["inputs"]["celfV32Sha256"] == hashlib.sha256((ROOT / "research/placement/celf_v3_2.py").read_bytes()).hexdigest()
    with pytest.raises(SystemExit, match="every block"):                    # decision 95, through the v3.2 layer
        c3.main([str(full)] + args[1:] + ["--out", str(tmp_path / "p2.json")])
    old = json.loads(tr.read_text())
    old["version"] = "3.2"
    (tmp_path / "old.json").write_text(json.dumps(old))
    with pytest.raises(SystemExit, match="is not v3.3"):
        c3.main([str(tmp_path / "old.json")] + args[1:] + ["--out", str(tmp_path / "p3.json")])
    score = tmp_path / "score.json"
    sargs = [str(full), "--placement", str(pl), "--training-readout", str(tr), "--test-blocks", "3"]
    monkeypatch.setattr(s3, "PINNED_PLACEMENTS", {})                        # the unpinned branch, as before freeze step 2 (bf8e24c)
    with pytest.raises(SystemExit, match="no pinned placement"):            # reader and registry are pinned; the placement is not yet
        s3.main(sargs + ["--out", str(tmp_path / "s0.json")])
    assert s3.main(sargs + ["--out", str(score), "--allow-unpinned"]) == 0
    res = json.loads(score.read_text())
    assert res["version"] == "score-test-v3.3" and res["splitCheck"]["trainBlocks"] == [1, 2]
    assert res["splitCheck"]["testBlocks"] == [3] and res["inputs"]["scoreTestV32Sha256"]
    import score_test_v3_2 as s2
    assert s2.VERSION == "score-test-v3.2" and s2.check_readout is s3._ORIG_CHECK_READOUT       # restored after the call


def chk_c3_pin(tmp_path, _world=None, monkeypatch=None):
    """A readout whose v3.3 reader digest is not the installed one is refused by the v3.3 layer."""
    import celf_v3_3 as c3
    J = json.loads((tmp_path / "ro.json").read_text())
    J["scriptSha256"] = "0" * 64
    try:
        c3.check_v33_layer(J, "the readout", allow_unpinned=True)
    except SystemExit:
        return True
    return False


def test_wrapper_pin_checks_fail_on_planted_defects(f_world, tmp_path, monkeypatch):
    import celf_v3_3 as c3
    import score_test_v3_3 as s3
    split, tr, full, tiers = _chain_files(f_world, tmp_path, monkeypatch)
    (tmp_path / "ro.json").write_text(tr.read_text())
    assert chk_c3_pin(tmp_path)
    monkeypatch.setattr(c3, "CHECK_PINS", False)                        # planted: the v3.3 layer is not checked
    assert not chk_c3_pin(tmp_path)
    monkeypatch.setattr(c3, "CHECK_PINS", True)
    P = {"system": "otel", "version": c3.VERSION, "inputs": {"celfSha256": "0" * 64}}
    with pytest.raises(SystemExit, match="frozen celf_v3"):
        s3.check_placement(P, "x", {"system": "otel"}, allow_unpinned=True)
    monkeypatch.setattr(s3, "ENFORCE_PINS", False)                      # planted: the placement checks are not made
    s3.check_placement(P, "x", {"system": "otel"}, allow_unpinned=True)
    with pytest.raises(SystemExit, match="calibrat|digest|pin|frozen"):
        monkeypatch.setattr(s3, "ENFORCE_PINS", True)
        s3.check_placement(dict(P, inputs={"celfSha256": c3.c2.PINNED_CELF_SHA256, "parametersV32Sha256": "0" * 64,
                                           "parametersV33Sha256": "0" * 64}), "x", {"system": "otel"}, allow_unpinned=True)


def test_the_frozen_pins_equal_the_files():
    """The reader and registry pins of celf_v3_3 (mirrored in score_test_v3_3) are the digests of the files; a changed file is
    refused by the v3.3 layer, a changed pin too."""
    import celf_v3_3 as c3
    import score_test_v3_3 as s3
    assert c3.PINNED_V33_SHA256 == hashlib.sha256(Path(v33.__file__).read_bytes()).hexdigest()
    assert c3.PINNED_PARAMETERS_V33_SHA256 == hashlib.sha256(v33.PARAMETERS_V33.read_bytes()).hexdigest()
    assert (s3.PINNED_V33_SHA256, s3.PINNED_PARAMETERS_V33_SHA256) == (c3.PINNED_V33_SHA256, c3.PINNED_PARAMETERS_V33_SHA256)
    assert c3.PINNED_V33_SHA256 == c3.sha256(c3.READER_V33)
    assert c3.PINNED_PARAMETERS_V33_SHA256 == c3.sha256(c3.PARAMETERS_V33)
    assert set(s3.PINNED_PLACEMENTS) == {"otel"}                             # freeze step 2: F's training placement (bf8e24c)
    assert s3.PINNED_PLACEMENTS["otel"] == c3.sha256(Path(__file__).resolve().parents[1] / "research/placement/test-f/placement-f.json")


def test_a_changed_pin_is_refused_and_the_planted_one_is_caught(monkeypatch):
    import celf_v3_3 as c3
    J = {"version": "3.3", "scriptSha256": c3.PINNED_V33_SHA256,
         "v33": {"parametersV33Sha256": c3.PINNED_PARAMETERS_V33_SHA256}}
    c3.check_v33_layer(J, "the readout")                                    # pinned digests: accepted without a flag
    monkeypatch.setattr(c3, "PINNED_PARAMETERS_V33_SHA256", "0" * 64)       # a registry edited after the freeze
    with pytest.raises(SystemExit, match="not the frozen"):
        c3.check_v33_layer(J, "the readout")
    monkeypatch.setattr(c3, "PINNED_PARAMETERS_V33_SHA256", c3.sha256(c3.PARAMETERS_V33))
    monkeypatch.setattr(c3, "PINNED_V33_SHA256", "0" * 64)                  # a reader edited after the freeze
    with pytest.raises(SystemExit, match="is not the frozen v3.3"):
        c3.check_v33_layer(J, "the readout")
