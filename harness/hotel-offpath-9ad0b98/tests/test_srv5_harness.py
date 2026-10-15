import importlib.util
import json
from pathlib import Path

import pytest


MODULE = Path(__file__).parents[1] / "modules/teastore/execution/srv5_harness.py"
SPEC = importlib.util.spec_from_file_location("srv5_harness", MODULE)
srv5_harness = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(srv5_harness)


def test_rejects_unsafe_campaign_identifier():
    for value in ("../../other", ".", "..", "a.b"):
        with pytest.raises(ValueError):
            srv5_harness.checked_name(value)


def test_rejects_ssh_option_and_shell_targets():
    for value in ("-oProxyCommand=bad", "host;touch-bad", "../host", "."):
        with pytest.raises(ValueError):
            srv5_harness.checked_target(value)
    assert srv5_harness.checked_target("fb14srv5.example.org") == "fb14srv5.example.org"


def test_rejects_unsafe_or_duplicate_campaign_parameters():
    base = dict(blocks=5, warmup=120, duration=600, rate=0.15, concurrency=8,
                postures="none,selected,full", fault="none", fault_at=240,
                outage=30, selection="auth")
    assert srv5_harness.validate_campaign_parameters(**base) == ("none", "selected", "full")
    with pytest.raises(ValueError):
        srv5_harness.validate_campaign_parameters(**{**base, "postures": "none,$(touch bad)"})
    with pytest.raises(ValueError):
        srv5_harness.validate_campaign_parameters(**{**base, "postures": "none,none"})
    with pytest.raises(ValueError):
        srv5_harness.validate_campaign_parameters(**{**base, "rate": float("nan")})
    with pytest.raises(ValueError):
        srv5_harness.validate_campaign_parameters(**{**base, "selection": "../../goal.json"})
    with pytest.raises(ValueError):
        srv5_harness.validate_campaign_parameters(**{**base, "fault": "$(touch bad)"})
    with pytest.raises(ValueError):
        srv5_harness.validate_campaign_parameters(**{**base, "fault": "auth-freeze", "fault_at": 590})


def test_bundle_validation_requires_balanced_complete_blocks(tmp_path: Path):
    for posture in ("none", "selected", "full"):
        for repetition in range(5):
            run = tmp_path / f"{posture}-{repetition}"
            run.mkdir()
            (run / "receipt.json").write_text(json.dumps({
                "runId": run.name, "posture": posture,
                "canonicality": {"blockers": []},
                "workload": {"completed": 10}, "latencyMs": {"count": 10},
            }))
    assert srv5_harness.validate_bundle(tmp_path)["verdict"] == "pass"
    (tmp_path / "none-0" / "receipt.json").unlink()
    assert srv5_harness.validate_bundle(tmp_path)["verdict"] == "blocked"


def test_bundle_validation_binds_receipts_to_recorded_schedule(tmp_path: Path):
    configuration = {"blocks": 1, "postures": ["selected", "full"], "fault": "auth-freeze",
                     "frameworkCommit": "framework", "sutCommit": "sut",
                     "selectionId": "fault-qualification", "selectionSourceSha256": "goal"}
    (tmp_path / "schedule.json").write_text(json.dumps({
        "configuration": configuration,
        "runs": [{"block": 1, "posture": "selected"}, {"block": 1, "posture": "full"}],
    }))
    for posture in ("selected", "full"):
        run = tmp_path / f"b01-{posture}"
        run.mkdir()
        (run / "receipt.json").write_text(json.dumps({
            "runId": run.name, "posture": posture,
            "source": {"frameworkCommit": "framework", "sutCommit": "sut",
                       "selectionId": "fault-qualification", "selectionSourceSha256": "goal"},
            "intervention": {"scenario": "auth-freeze"}, "canonicality": {"blockers": []},
            "workload": {"completed": 10}, "latencyMs": {"count": 10},
        }))
    assert srv5_harness.validate_bundle(tmp_path, blocks=1,
                                        postures_expected=("selected", "full"))["verdict"] == "pass"
    receipt_path = tmp_path / "b01-selected" / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["source"]["frameworkCommit"] = "other"
    receipt_path.write_text(json.dumps(receipt))
    assert srv5_harness.validate_bundle(tmp_path, blocks=1,
                                        postures_expected=("selected", "full"))["verdict"] == "blocked"
