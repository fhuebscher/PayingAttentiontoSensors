"""research/lanes/posthoc_lanes_v35.py: posthoc_lanes_v33's `otel` command over v3.5 readouts (the F ablation). The synthetic ablation chain of
tests/test_wrappers_v3_5.py is run end to end through the wrapper; the rebinding, its restoration and each refusal have a planted defect. No ablation
evidence is read.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "research" / "lanes", ROOT / "research" / "placement", ROOT / "research" / "detection-time"):
    sys.path.insert(0, str(_p))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import posthoc_lanes_v35 as p5  # noqa: E402
from test_sweep_analysis_v3_5 import _no_registry_split, nl_world  # noqa: E402,F401  (fixtures)
from test_wrappers_v3_5 import _chain_files  # noqa: E402

pl, c5, s5 = p5.pl, p5.c5, p5.s5


def test_v33s_own_checks_refuse_a_v35_readout_so_the_wrapper_is_needed(nl_world, tmp_path, monkeypatch):
    split, tr, full, tiers = _chain_files(nl_world, tmp_path, monkeypatch)
    J = json.loads(tr.read_text())
    with pytest.raises(SystemExit, match="not v3.3"):
        pl.check_readout_pins(J, "the readout")


def test_the_rebinding_applies_inside_and_is_restored_outside(monkeypatch):
    before = (pl.c3, pl.s3, pl.check_readout_pins)
    seen = {}

    def fake(argv):
        seen["in"] = (pl.c3, pl.s3, pl.check_readout_pins)
        return 0
    monkeypatch.setattr(pl, "main", fake)
    with p5.v35_chain():
        assert (pl.c3, pl.s3, pl.check_readout_pins) == (c5, s5, p5.check_readout_pins35)
    assert (pl.c3, pl.s3, pl.check_readout_pins) == before
    with pytest.raises(RuntimeError):
        with p5.v35_chain():
            raise RuntimeError("x")
    assert (pl.c3, pl.s3, pl.check_readout_pins) == before and before[0].__name__ == "celf_v3_3"
    assert s5.PINNED_PLACEMENTS == {}


def test_pins_are_checked_in_the_v35_and_the_v33_layers(nl_world, tmp_path, monkeypatch):
    split, tr, full, tiers = _chain_files(nl_world, tmp_path, monkeypatch)
    J = json.loads(tr.read_text())
    p5.check_readout_pins35(J, "the readout")
    with pytest.raises(SystemExit, match="not the frozen v3.5"):
        p5.check_readout_pins35(dict(J, scriptSha256="0" * 64), "the readout")
    with pytest.raises(SystemExit, match="frozen v3.3"):
        p5.check_readout_pins35(dict(J, v33ScriptSha256="0" * 64), "the readout")
    with pytest.raises(SystemExit, match="is not v3.5"):
        p5.check_readout_pins35(dict(J, version="3.3"), "the readout")


def test_end_to_end_on_the_synthetic_ablation_chain(nl_world, tmp_path, monkeypatch):
    """reader -> celf_v3_5 -> reader (test blocks held out) -> posthoc_lanes_v35: the decision-73 rerun equals the frozen placement, the scoring runs
    through score_test_v3_5 with its placement pin waived for the post hoc placement only, and the module bindings are back afterwards."""
    split, tr, full, tiers = _chain_files(nl_world, tmp_path, monkeypatch)
    placement = tmp_path / "placement.json"
    assert c5.main([str(tr), "--tiers", str(tiers), "--tier-catalog", "postureCurrentCatalog", "--split", str(split), "--out", str(placement)]) == 0
    out = tmp_path / "posthoc"
    before = (pl.c3, pl.s3, pl.check_readout_pins)
    assert p5.main(["otel", "--training-readout", str(tr), "--scoring-readout", str(full), "--placement", str(placement),
                    "--split", str(split), "--test-blocks", "3", "--rate", "1", "--out-dir", str(out)]) == 0
    assert (pl.c3, pl.s3, pl.check_readout_pins) == before and s5.PINNED_PLACEMENTS == {}
    R = json.loads((out / "posthoc_lanes_v33_otel.json").read_text())
    assert R["zeroAlarm"]["baselineCheck"]["ratesEqualFrozen"] is True                    # the rerun through celf_v3_5 equals the frozen one
    assert {p["id"] for p in R["predictions"]} == {"F-L1", "F-L2", "F-L3", "F-M"}
    l3 = next(p for p in R["predictions"] if p["id"] == "F-L3")
    assert l3["result"] == "—" and l3["numbers"]["lagIdsInCalibration"] == 0              # no lag id: not applicable, never a miss (FNL-L3)
    prov = json.loads((out / "posthoc_lanes_v35_provenance.json").read_text())
    assert prov["rebound"]["c3"] == "celf_v3_5" and prov["inputs"]["placementSha256"] and prov["pins"]["scorerPinnedPlacements"] == {}
    assert prov["fileDigests"]["scriptSha256"]
    with pytest.raises(SystemExit, match="existing path"):                                # a second run never overwrites
        p5.main(["otel", "--training-readout", str(tr), "--scoring-readout", str(full), "--placement", str(placement),
                 "--split", str(split), "--test-blocks", "3", "--rate", "1", "--out-dir", str(out)])


def test_planted_the_unwrapped_script_cannot_run_the_chain(nl_world, tmp_path, monkeypatch):
    """Without the rebinding the same inputs stop in posthoc_lanes_v33's own v3.3 check (what the wrapper exists for)."""
    split, tr, full, tiers = _chain_files(nl_world, tmp_path, monkeypatch)
    placement = tmp_path / "placement.json"
    assert c5.main([str(tr), "--tiers", str(tiers), "--tier-catalog", "postureCurrentCatalog", "--split", str(split), "--out", str(placement)]) == 0
    with pytest.raises(SystemExit, match="not v3.3"):
        pl.main(["otel", "--training-readout", str(tr), "--scoring-readout", str(full), "--placement", str(placement), "--split", str(split),
                 "--test-blocks", "3", "--rate", "1", "--out-dir", str(tmp_path / "plain")])


def test_teastore_command_refused(tmp_path):
    with pytest.raises(SystemExit, match="only the `otel` command"):
        p5.main(["teastore", "--readout", "x", "--out-dir", str(tmp_path / "o")])
    with pytest.raises(SystemExit, match="only the `otel` command"):
        p5.main([])


def test_readouts_of_f_or_a_pooled_epoch_are_refused(nl_world, tmp_path, monkeypatch):
    split, tr, full, tiers = _chain_files(nl_world, tmp_path, monkeypatch)
    f_train = ROOT / "research/traffic-sweep/readout-otel-f-train-v3.3/sweep_analysis_v3_3.json"
    with pytest.raises(SystemExit, match="byte copy of a committed F readout"):
        p5.main(["otel", "--training-readout", str(f_train), "--scoring-readout", str(full), "--placement", "x", "--out-dir", str(tmp_path / "o")])
    pooled = tmp_path / "pooled.json"
    J = json.loads(full.read_text())
    J["v32"]["epochsRead"] = {"otel-offpath-f-nolag-v1": 20, "otel-offpath-f-v1": 5}
    pooled.write_text(json.dumps(J))
    with pytest.raises(SystemExit, match="not otel-offpath-f-nolag-v1 alone"):
        p5.main(["otel", "--training-readout", str(tr), "--scoring-readout", str(pooled), "--placement", "x", "--out-dir", str(tmp_path / "o2")])
    assert not (tmp_path / "o").exists() and not (tmp_path / "o2").exists()
