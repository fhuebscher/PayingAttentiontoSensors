import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


normalizer = load("hotel_normalizer", "modules/hotel-reservation/normalizers/jaeger.py")
validator = load("hotel_validator", "modules/hotel-reservation/validation/path_visibility.py")


def raw_trace():
    operations = [
        ("f", "frontend", "HTTP GET /hotels", None),
        ("s", "search", "/search.Search/Nearby", "f"),
        ("g", "geo", "/geo.Geo/Nearby", "s"),
        ("r", "rate", "/rate.Rate/GetRates", "s"),
        ("a", "reservation", "/reservation.Reservation/CheckAvailability", "f"),
        ("p", "profile", "/profile.Profile/GetProfiles", "f"),
    ]
    processes = {f"p-{service}": {"serviceName": service} for _, service, _, _ in operations}
    spans = []
    for index, (span_id, service, operation, parent) in enumerate(operations):
        spans.append({"traceID": "trace-1", "spanID": span_id, "operationName": operation,
                      "processID": f"p-{service}", "startTime": 100 + index,
                      "duration": 10, "references": ([{"refType": "CHILD_OF",
                                                        "traceID": "trace-1", "spanID": parent}]
                                                     if parent else []), "tags": []})
    trace = {"traceID": "trace-1", "processes": processes, "spans": spans}
    response = {"data": [trace], "total": 1, "limit": 10000, "offset": 0, "errors": None}
    return {"schemaVersion": 1, "collector": "jaeger-query-api-v1",
            "window": {"startUs": 1, "endUs": 2},
            "queries": [{"service": "frontend", "traceCount": 1, "response": response},
                        {"service": "search", "traceCount": 1, "response": response}]}


def test_normalizer_deduplicates_query_overlap_but_retains_native_ids():
    result = normalizer.normalize(raw_trace())
    assert result["rawQueryTraceCount"] == 2
    assert result["uniqueTraceCount"] == 1
    assert result["spanCount"] == 6
    assert result["duplicateQuerySpansRemoved"] == 6
    assert {(event["traceId"], event["spanId"]) for event in result["events"]} == {
        ("trace-1", value) for value in "fsgarp"
    }


def test_visibility_requires_complete_path_in_one_trace():
    goal = json.loads((ROOT / "modules/hotel-reservation/goals/search-path.json").read_text())
    normalized = normalizer.normalize(raw_trace())
    report = validator.validate(normalized, goal)
    assert report["verdict"] == "pass"
    assert report["requiredSensorRetention"] == 1.0
    assert report["requiredEdgeRetention"] == 1.0
    normalized["events"] = [event for event in normalized["events"] if event["service"] != "reservation"]
    blocked = validator.validate(normalized, goal)
    assert blocked["verdict"] == "blocked"
    assert blocked["completePathTraceCount"] == 0


def test_visibility_rejects_unproven_fault():
    goal = json.loads((ROOT / "modules/hotel-reservation/goals/search-path.json").read_text())
    report = validator.validate(normalizer.normalize(raw_trace()), goal,
                                {"scenario": "search-pause", "manifested": True,
                                 "recovered": False, "successful": False})
    assert report["verdict"] == "blocked"
    assert "fault manifestation and recovery" in " ".join(report["failures"])


def test_visibility_rejects_query_limit_truncation():
    goal = json.loads((ROOT / "modules/hotel-reservation/goals/search-path.json").read_text())
    raw = raw_trace()
    raw["limitPerService"] = 1
    report = validator.validate(normalizer.normalize(raw), goal)
    assert report["verdict"] == "blocked"
    assert "truncated" in " ".join(report["failures"])
