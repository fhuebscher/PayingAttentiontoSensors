from __future__ import annotations

import importlib.util
import json
from pathlib import Path


TOOL = Path(__file__).resolve().parents[1] / "tools/cross_sut_objectives.py"
ROOT = TOOL.parents[1]
SPEC = importlib.util.spec_from_file_location("cross_sut_objectives", TOOL)
assert SPEC and SPEC.loader
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


def test_comparison_preserves_nulls_and_refuses_cross_sut_ranking(tmp_path: Path) -> None:
    dataset = tmp_path / "rows.json"
    dataset.write_text(json.dumps({
        "asOf": "2026-08-09",
        "objectiveDirections": {"latency_p95_ms": "minimize", "telemetry_bytes": "minimize"},
        "rows": [
            {"campaign": "a", "sut": "one", "family": "one", "posture": "full",
             "sutAttributionBound": True,
             "curatedQualification": "candidate-evidence", "goal": "g",
             "objectives": {"latency_p95_ms": 10, "telemetry_bytes": None}},
            {"campaign": "a", "sut": "one", "family": "one", "posture": "full",
             "sutAttributionBound": True,
             "curatedQualification": "candidate-evidence", "goal": "g",
             "objectives": {"latency_p95_ms": 20, "telemetry_bytes": None}},
            {"campaign": "b", "sut": "two", "family": "two", "posture": "off",
             "sutAttributionBound": True,
             "curatedQualification": "smoke-validation", "goal": "other",
             "objectives": {"latency_p95_ms": None, "telemetry_bytes": None}},
            {"campaign": "forged", "sut": "forged-sut", "family": "unknown", "posture": "full",
             "sutAttributionBound": False,
             "curatedQualification": "unlisted-evidence", "goal": "unknown",
             "objectives": {"latency_p95_ms": 1, "telemetry_bytes": 1}},
        ],
    }))

    report = comparison.build_comparison(dataset)

    assert report["policy"]["crossSutRankingAllowed"] is False
    assert report["policy"]["unknownsRemainNull"] is True
    first = next(group for group in report["groups"] if group["campaign"] == "a")
    assert first["objectives"]["latency_p95_ms"]["median"] == 15
    assert first["objectives"]["telemetry_bytes"]["median"] is None
    smoke = next(group for group in report["groups"] if group["campaign"] == "b")
    assert smoke["candidateRowEligible"] is False
    assert report["objectiveCoverage"]["telemetry_bytes"]["missingForAllObservedSuts"] is True
    assert "forged-sut" not in report["observedSuts"]
    assert report["policy"]["unboundRowsExcludedFromSutCoverage"] is True
    forged = next(group for group in report["groups"] if group["campaign"] == "forged")
    assert forged["descriptiveUnbound"] is True
    assert forged["candidateRowEligible"] is False


def test_generated_unlisted_online_boutique_row_is_display_only_not_sut_coverage() -> None:
    dataset_path = ROOT / "research/ml-readiness.json"
    dataset = json.loads(dataset_path.read_text())
    row = next(item for item in dataset["rows"] if "workspace-v2" in item["campaign"])

    assert row["sut"] == "online-boutique"
    assert row["sutAttributionBound"] is False
    assert row["curatedQualification"] == "unlisted-evidence"

    report = comparison.build_comparison(dataset_path)
    group = next(item for item in report["groups"] if "workspace-v2" in item["campaign"])
    assert len(report["observedSuts"]) == 5
    assert group["descriptiveUnbound"] is True
    assert group["candidateRowEligible"] is False
