"""research/placement/test-f-rep1/fresh_fa_rep.py: the replicate's wrapper over fresh_fa_f. Synthetic receipts only; no replicate evidence is read.
The reader and fresh_fa_f.main are stubbed; what is tested is which cells it picks, what it refuses, and what it hands to fresh_fa_f.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "placement" / "test-f-rep1"))
import fresh_fa_rep as fr  # noqa: E402

ff = fr.ff


def _cell(camp, name, block, regime="no-fault-calibration", attempt=2, state="valid", epoch="otel-offpath-f-v1"):
    d = camp / "runs" / "calibration" / name
    d.mkdir(parents=True)
    (d / "receipt.json").write_text(json.dumps({"state": state, "runKey": {"attempt": attempt, "block": block, "regime": regime, "studyEpoch": epoch}}))
    (d / "resources.json").write_text("{}")


@pytest.fixture
def camp(tmp_path):
    c = tmp_path / "f2-fetch" / "x"
    for i, b in enumerate((1, 2, 3)):
        _cell(c, "r25-b0%d-nf" % b, b)                       # training no-fault cells are not held out
    for n, b in (("zz-a", 4), ("zz-b", 4), ("zz-c", 5), ("zz-d", 5)):
        _cell(c, n, b)
    _cell(c, "zz-fault", 4, regime="fraud-pause-effect")      # a block-4 fault cell is not a no-fault cell
    return c


def test_selects_the_four_held_out_no_fault_cells_by_receipt(camp):
    assert fr.select_cells(camp) == ["zz-a", "zz-b", "zz-c", "zz-d"]


def test_attempt_1_cell_refused(camp):
    _cell(camp, "zz-old", 5, attempt=1)
    with pytest.raises(SystemExit, match="not attempt 2"):
        fr.select_cells(camp)


def test_wrong_epoch_refused(tmp_path):
    c = tmp_path / "x"
    _cell(c, "a", 4, epoch="otel-offpath-e-v1")
    with pytest.raises(SystemExit, match="not attempt 2"):
        fr.select_cells(c)


def test_not_four_refused(camp):
    _cell(camp, "zz-e", 5)
    with pytest.raises(SystemExit, match="expected 4"):
        fr.select_cells(camp)


def test_invalid_held_out_cell_refused(tmp_path):
    c = tmp_path / "x"
    _cell(c, "a", 4, state="blocked")
    with pytest.raises(SystemExit, match="not valid"):
        fr.select_cells(c)


def test_parse_sets():
    assert fr.parse_sets([]) == dict(ff.SETS)
    assert fr.parse_sets(["@6/T_r=metric:a:b", "@3/T_r=metric:c:d"]) == {"@6/T_r": "metric:a:b", "@3/T_r": "metric:c:d"}
    for bad in (["nolabel"], ["=x"], ["a="], ["a=1", "a=2"]):
        with pytest.raises(SystemExit, match="LABEL=SENSOR_ID"):
            fr.parse_sets(bad)


def _run(camp, tmp_path, monkeypatch, extra=()):
    for n in ("HELD_OUT_CELLS", "TRAIN_READOUT", "TRAIN_BOUND", "SETS"):
        monkeypatch.setattr(ff, n, getattr(ff, n))           # so that the wrapper's rebinding is undone at teardown
    seen = {}
    train = tmp_path / "train.json"
    train.write_text('{"r": "f2 training"}')
    rd = tmp_path / "rd"

    def reader(argv):
        seen["reader"] = list(argv)
        rd.mkdir()
        (rd / "sweep_analysis_v3_3.json").write_text("{}")

    def fake_ff_main(argv):
        seen["ff"] = list(argv)
        seen["globals"] = (list(ff.HELD_OUT_CELLS), ff.TRAIN_READOUT, dict(ff.TRAIN_BOUND), dict(ff.SETS))
        Path(argv[argv.index("--out") + 1]).mkdir(parents=True)
        return 0
    monkeypatch.setattr(ff, "main", fake_ff_main)
    out = tmp_path / "out"
    rc = fr.main(["--campaign", str(camp), "--train-readout", str(train), "--out", str(out), "--farm", str(tmp_path / "farm"),
                  "--readout-dir", str(rd), *extra], reader=reader)
    return rc, seen, out, train


def test_hands_the_replicate_to_fresh_fa_f_and_records_provenance(camp, tmp_path, monkeypatch):
    rc, seen, out, train = _run(camp, tmp_path, monkeypatch)
    assert rc == 0
    assert seen["globals"][0] == ["zz-a", "zz-b", "zz-c", "zz-d"]
    assert seen["globals"][1] == train.resolve() and seen["globals"][2] == {} and seen["globals"][3] == dict(ff.SETS)
    assert "--validation" in seen["reader"] and seen["reader"][seen["reader"].index("--test-blocks") + 1:][:2] == ["4", "5"]
    assert seen["reader"][0] == str(camp.resolve())
    farm_cells = sorted(p.parent.name for p in (tmp_path / "farm").glob("**/receipt.json"))
    assert farm_cells == ["zz-a", "zz-b", "zz-c", "zz-d"]       # the 4 held-out cells and nothing else
    prov = json.loads((out / "fresh_fa_rep_provenance.json").read_text())
    assert prov["heldOutCells"] == farm_cells and prov["setsAre"] == "F's frozen sets"


def test_given_sets_replace_f_sets(camp, tmp_path, monkeypatch):
    _, seen, out, _ = _run(camp, tmp_path, monkeypatch, ["--set", "@6/T_r=metric:x:y"])
    assert seen["globals"][3] == {"@6/T_r": "metric:x:y"}
    assert json.loads((out / "fresh_fa_rep_provenance.json").read_text())["setsAre"] == "given by --set"


def test_f_attempt_1_fetch_refused(tmp_path):
    c = tmp_path / "f1-fetch" / "x"
    for n, b in (("a", 4), ("b", 4), ("c", 5), ("d", 5)):
        _cell(c, n, b)
    with pytest.raises(SystemExit, match="attempt 1's fetch"):
        fr.main(["--campaign", str(c), "--train-readout", str(tmp_path / "t.json"), "--out", str(tmp_path / "o")])


def test_f_training_readout_refused(camp, tmp_path):
    with pytest.raises(SystemExit, match="byte copy of F's training readout"):
        fr.main(["--campaign", str(camp), "--train-readout", str(ff.TRAIN_READOUT), "--out", str(tmp_path / "o")])


def test_existing_output_refused(camp, tmp_path):
    train = tmp_path / "t.json"
    train.write_text("{}")
    (tmp_path / "o").mkdir()
    with pytest.raises(SystemExit, match="output exists"):
        fr.main(["--campaign", str(camp), "--train-readout", str(train), "--out", str(tmp_path / "o")])
