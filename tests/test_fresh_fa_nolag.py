"""research/placement/test-f-nolag/fresh_fa_nolag.py: the ablation's wrapper over fresh_fa_f. Synthetic receipts only; no ablation evidence is read.
The reader and fresh_fa_f.main are stubbed; what is tested is which cells it picks, what it refuses, how sets are given, the readout view fresh_fa_f is
shown, and what it hands to fresh_fa_f.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "placement" / "test-f-nolag"))
import fresh_fa_nolag as fn  # noqa: E402

ff, sn = fn.ff, fn.sn
EPOCH = fn.EPOCH


def _cell(camp, name, block, regime="no-fault-calibration", attempt=1, state="valid", epoch=EPOCH):
    d = camp / "runs" / "calibration" / name
    d.mkdir(parents=True)
    (d / "receipt.json").write_text(json.dumps({"state": state, "runKey": {"attempt": attempt, "block": block, "regime": regime, "studyEpoch": epoch}}))
    (d / "resources.json").write_text("{}")


def _readout(path, epochs):
    path.write_text(json.dumps({"version": "3.5", "v32": {"epochsRead": epochs}}))
    return path


@pytest.fixture
def camp(tmp_path):
    c = tmp_path / "nolag1-fetch" / "x"
    for b in (1, 2, 3):
        _cell(c, "r25-b0%d-nf" % b, b)                       # training no-fault cells are not held out
    for n, b in (("zz-a", 4), ("zz-b", 4), ("zz-c", 5), ("zz-d", 5)):
        _cell(c, n, b)
    _cell(c, "zz-fault", 4, regime="fraud-pause-effect")      # a block-4 fault cell is not a no-fault cell
    return c


def test_selects_the_four_held_out_no_fault_cells_by_receipt(camp):
    assert fn.select_cells(camp) == ["zz-a", "zz-b", "zz-c", "zz-d"]


def test_other_attempt_refused(camp):
    _cell(camp, "zz-old", 5, attempt=2)
    with pytest.raises(SystemExit, match="not attempt 1"):
        fn.select_cells(camp)


def test_the_attempt_is_a_parameter(tmp_path):
    c = tmp_path / "x"
    for n, b in (("a", 4), ("b", 4), ("c", 5), ("d", 5)):
        _cell(c, n, b, attempt=2)
    assert fn.select_cells(c, attempt=2) == ["a", "b", "c", "d"]
    with pytest.raises(SystemExit, match="not attempt 1"):
        fn.select_cells(c)


@pytest.mark.parametrize("epoch", ["otel-offpath-f-v1", "otel-offpath-e-v1", None])
def test_wrong_epoch_refused(tmp_path, epoch):
    c = tmp_path / "x"
    _cell(c, "a", 4, epoch=epoch)
    with pytest.raises(SystemExit, match="not the ablation"):
        fn.select_cells(c)


def test_not_four_refused(camp):
    _cell(camp, "zz-e", 5)
    with pytest.raises(SystemExit, match="expected 4"):
        fn.select_cells(camp)


def test_invalid_held_out_cell_refused(tmp_path):
    c = tmp_path / "x"
    _cell(c, "a", 4, state="blocked")
    with pytest.raises(SystemExit, match="not valid"):
        fn.select_cells(c)


def test_parse_sets():
    assert fn.parse_sets(["@6/T_r=metric:a:b", "@3/T_r=metric:c:d"]) == {"@6/T_r": "metric:a:b", "@3/T_r": "metric:c:d"}
    assert fn.parse_sets(["@6/T_r=metric:a:b,metric:e:f"]) == {"@6/T_r[1]": "metric:a:b", "@6/T_r[2]": "metric:e:f"}
    for bad in (["nolabel"], ["=x"], ["a="], ["a=1", "a=2"], ["a=1,"], ["a=,1"], ["a=1,1"]):
        with pytest.raises(SystemExit, match="LABEL=SENSOR_ID"):
            fn.parse_sets(bad)


def _placement(tmp_path, s6=("metric:kafka:kafka.request.count", "span:x"), s3=("metric:kafka:kafka.request.count",)):
    def pts(six, three):
        return {"0": {"set": []}, "3/T_r": {"set": list(three)}, "6/T_r": {"set": list(six)}}
    grid = [{"maxEffort": 0, "maxRuntime": "<1%", "points": pts(("zz:other",), ("zz:other",))},
            {"maxEffort": "any", "maxRuntime": "any", "points": pts(s6, s3)}]
    p = tmp_path / "placement.json"
    p.write_text(json.dumps({"rates": {"25": {"grid": grid}}}))
    return p


def test_sets_from_placement_take_the_unrestricted_cell(tmp_path):
    items = fn.sets_from_placement(_placement(tmp_path))
    assert items == ["@6/T_r=metric:kafka:kafka.request.count,span:x", "@3/T_r=metric:kafka:kafka.request.count"]
    assert fn.parse_sets(items) == {"@6/T_r[1]": "metric:kafka:kafka.request.count", "@6/T_r[2]": "span:x",
                                    "@3/T_r": "metric:kafka:kafka.request.count"}


def test_sets_from_placement_refuse_an_empty_set_or_a_missing_grid(tmp_path):
    with pytest.raises(SystemExit, match="empty or absent"):
        fn.sets_from_placement(_placement(tmp_path, s6=()))
    p = tmp_path / "np.json"
    p.write_text(json.dumps({"rates": {"25": {"note": "no grid"}}}))
    with pytest.raises(SystemExit, match="no frozen grid"):
        fn.sets_from_placement(p)


def _run(camp, tmp_path, monkeypatch, extra=("--set", "@6/T_r=metric:x:y"), epochs=None):
    for n in ("HELD_OUT_CELLS", "TRAIN_READOUT", "TRAIN_BOUND", "SETS"):
        monkeypatch.setattr(ff, n, getattr(ff, n))           # so that the wrapper's rebinding is undone at teardown
    seen = {}
    train = _readout(tmp_path / "train.json", epochs or {EPOCH: 15})
    rd = tmp_path / "rd"

    def reader(argv):
        seen["reader"] = list(argv)
        rd.mkdir()
        (rd / "sweep_analysis_v3_5.json").write_text('{"v35": true}')

    def fake_ff_main(argv):
        seen["ff"] = list(argv)
        seen["globals"] = (list(ff.HELD_OUT_CELLS), ff.TRAIN_READOUT, dict(ff.TRAIN_BOUND), dict(ff.SETS))
        view = Path(argv[argv.index("--readout-dir") + 1])
        seen["view"] = (view, (view / "sweep_analysis_v3_3.json").is_symlink(), (view / "sweep_analysis_v3_3.json").read_text())
        Path(argv[argv.index("--out") + 1]).mkdir(parents=True)
        return 0
    monkeypatch.setattr(ff, "main", fake_ff_main)
    out = tmp_path / "out"
    rc = fn.main(["--campaign", str(camp), "--train-readout", str(train), "--out", str(out), "--farm", str(tmp_path / "farm"),
                  "--readout-dir", str(rd), *extra], reader=reader)
    return rc, seen, out, train


def test_hands_the_ablation_to_fresh_fa_f_and_records_provenance(camp, tmp_path, monkeypatch):
    rc, seen, out, train = _run(camp, tmp_path, monkeypatch)
    assert rc == 0
    assert seen["globals"][0] == ["zz-a", "zz-b", "zz-c", "zz-d"]
    assert seen["globals"][1] == train.resolve() and seen["globals"][2] == {} and seen["globals"][3] == {"@6/T_r": "metric:x:y"}
    assert "--validation" in seen["reader"] and seen["reader"][seen["reader"].index("--test-blocks") + 1:][:2] == ["4", "5"]
    assert seen["reader"][0] == str(camp.resolve())
    farm_cells = sorted(p.parent.name for p in (tmp_path / "farm").glob("**/receipt.json"))
    assert farm_cells == ["zz-a", "zz-b", "zz-c", "zz-d"]       # the 4 held-out cells and nothing else
    view, is_link, text = seen["view"]                           # fresh_fa_f reads the v3.5 readout through a symlink, not a copy
    assert is_link and text == '{"v35": true}' and view.name == "rd.fresh_fa_f_view"
    prov = json.loads((out / "fresh_fa_nolag_provenance.json").read_text())
    assert prov["heldOutCells"] == farm_cells and prov["setsAre"] == "given by --set" and prov["attempt"] == 1
    assert prov["readoutSha256"] and prov["readoutViewForFreshFaF"] == str(view)


def test_sets_from_placement_are_handed_over_and_recorded(camp, tmp_path, monkeypatch):
    pl = _placement(tmp_path)
    _, seen, out, _ = _run(camp, tmp_path, monkeypatch, ["--sets-from-placement", str(pl)])
    assert seen["globals"][3] == {"@6/T_r[1]": "metric:kafka:kafka.request.count", "@6/T_r[2]": "span:x",
                                  "@3/T_r": "metric:kafka:kafka.request.count"}
    prov = json.loads((out / "fresh_fa_nolag_provenance.json").read_text())
    assert prov["setsFromPlacementSha256"] and "from %s" % pl in prov["setsAre"]


def test_no_default_sets_and_not_both(camp, tmp_path, monkeypatch):
    train = _readout(tmp_path / "t.json", {EPOCH: 1})
    base = ["--campaign", str(camp), "--train-readout", str(train), "--out", str(tmp_path / "o")]
    with pytest.raises(SystemExit, match="exactly one of"):
        fn.main(base)
    with pytest.raises(SystemExit, match="exactly one of"):
        fn.main(base + ["--set", "a=b", "--sets-from-placement", str(_placement(tmp_path))])


@pytest.mark.parametrize("part", ["f1-fetch", "f2-fetch", "f3-fetch", "f2-fetch2"])
def test_f_and_replicate_fetches_refused(tmp_path, part):
    c = tmp_path / part / "x"
    for n, b in (("a", 4), ("b", 4), ("c", 5), ("d", 5)):
        _cell(c, n, b)
    train = _readout(tmp_path / "t.json", {EPOCH: 1})
    with pytest.raises(SystemExit, match="fetch of campaign F"):
        fn.main(["--campaign", str(c), "--train-readout", str(train), "--out", str(tmp_path / "o"), "--set", "a=b"])


def test_f_training_readout_refused(camp, tmp_path):
    with pytest.raises(SystemExit, match="byte copy of F's training readout"):
        fn.main(["--campaign", str(camp), "--train-readout", str(ff.TRAIN_READOUT), "--out", str(tmp_path / "o"), "--set", "a=b"])


@pytest.mark.parametrize("epochs", [{"otel-offpath-f-v1": 15}, {EPOCH: 10, "otel-offpath-f-v1": 5}, {}])
def test_a_training_readout_of_another_epoch_or_a_pooled_one_is_refused(camp, tmp_path, epochs):
    train = _readout(tmp_path / "t.json", epochs)
    with pytest.raises(SystemExit, match="not %s alone" % EPOCH):
        fn.main(["--campaign", str(camp), "--train-readout", str(train), "--out", str(tmp_path / "o"), "--set", "a=b"])


def test_existing_output_refused(camp, tmp_path):
    train = _readout(tmp_path / "t.json", {EPOCH: 1})
    (tmp_path / "o").mkdir()
    with pytest.raises(SystemExit, match="output exists"):
        fn.main(["--campaign", str(camp), "--train-readout", str(train), "--out", str(tmp_path / "o"), "--set", "a=b"])
