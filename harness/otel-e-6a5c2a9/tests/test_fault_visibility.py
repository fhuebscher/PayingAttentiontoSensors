import importlib.util
import json
from pathlib import Path


MODULE = Path(__file__).parents[1] / "modules/teastore/validation/fault_visibility.py"
SPEC = importlib.util.spec_from_file_location("fault_visibility", MODULE)
fault_visibility = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(fault_visibility)


def test_fault_visibility_requires_declared_sensor_and_path_retention(tmp_path: Path):
    goal = tmp_path / "goal.json"
    goal.write_text(json.dumps({
        "id": "goal", "logicalSensors": ["operation:auth", "operation:persistence"],
        "scenarios": {"auth-freeze": {"targetService": "auth",
            "requiredSensors": ["operation:auth", "operation:persistence"],
            "requiredServiceEdges": [["auth", "persistence"]]}},
        "claimBoundary": "retention only",
    }))
    for block in range(1, 4):
        for posture in ("selected", "full"):
            run = tmp_path / f"b{block:02d}-{posture}"
            run.mkdir()
            (run / "receipt.json").write_text(json.dumps({
                "runId": run.name, "posture": posture,
                "window": {"startedAt": "2026-08-03T00:00:00+00:00", "endedAt": "2026-08-03T00:10:00+00:00"},
                "intervention": {"scenario": "auth-freeze", "successful": True,
                                 "startedAt": "2026-08-03T00:04:00+00:00", "endedAt": "2026-08-03T00:04:30+00:00"},
                "workload": {"failed": 1}, "canonicality": {"blockers": []},
                "source": {"selectionId": "fault-qualification",
                           "selectionSourceSha256": fault_visibility._sha256(goal)},
            }))
            (run / "traces.json").write_text(json.dumps([
                {"span_id": "a1", "parent_span_id": "", "service": "auth", "timestamp": 1785715300,
                 "message_sha1": "m1", "signature_sha1": "s1"},
                {"span_id": "p1", "parent_span_id": "a1", "service": "persistence", "timestamp": 1785715301,
                 "message_sha1": "m2", "signature_sha1": "s2"},
                {"span_id": "a2", "parent_span_id": "", "service": "auth", "timestamp": 1785715500,
                 "message_sha1": "m3", "signature_sha1": "s1"},
                {"span_id": "p2", "parent_span_id": "a2", "service": "persistence", "timestamp": 1785715501,
                 "message_sha1": "m4", "signature_sha1": "s2"},
            ]))
    assert fault_visibility.validate(tmp_path, "auth-freeze", 3, goal)["verdict"] == "pass"
    traces = tmp_path / "b01-selected" / "traces.json"
    traces.write_text("[]")
    assert fault_visibility.validate(tmp_path, "auth-freeze", 3, goal)["verdict"] == "blocked"
