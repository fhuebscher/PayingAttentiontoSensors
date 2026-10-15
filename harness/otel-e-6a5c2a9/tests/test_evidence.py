import json
from pathlib import Path

import pytest

from obsplacement.evidence import build_manifest, validate_campaign


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


def test_manifest_is_deterministic_and_excludes_itself(tmp_path):
    write(tmp_path / "schedule.json", {"runs": [{"block": 1, "posture": "full"}]})
    write(tmp_path / "b01-full/receipt.json", {"runId": "b01-full"})
    first = build_manifest(tmp_path)
    write(tmp_path / "evidence-manifest.json", first)
    assert build_manifest(tmp_path) == first
    write(tmp_path / "extra.txt", {"changed": True})
    assert build_manifest(tmp_path)["evidenceSha256"] != first["evidenceSha256"]


def test_manifest_includes_nested_manifest_named_artifact(tmp_path):
    write(tmp_path / "schedule.json", {"runs": [{"block": 1, "posture": "full"}]})
    first = build_manifest(tmp_path)
    write(tmp_path / "evidence-manifest.json", first)
    write(tmp_path / "nested/evidence-manifest.json", {"upstream": "proof"})
    rebuilt = build_manifest(tmp_path)
    assert "nested/evidence-manifest.json" in {item["path"] for item in rebuilt["files"]}
    assert rebuilt["evidenceSha256"] != first["evidenceSha256"]


def test_manifest_rejects_symlinks(tmp_path):
    (tmp_path / "data").write_text("x")
    (tmp_path / "link").symlink_to(tmp_path / "data")
    with pytest.raises(ValueError, match="symlinks"):
        build_manifest(tmp_path)


def test_campaign_validation_requires_all_receipts_and_analysis(tmp_path):
    write(tmp_path / "schedule.json", {"runs": [
        {"block": 1, "posture": "none"}, {"block": 1, "posture": "full"}]})
    write(tmp_path / "b01-none/receipt.json", {
        "schemaVersion": 1, "runId": "b01-none", "sut": "test", "posture": "none",
        "canonicality": {"label": "candidate-evidence", "blockers": []}})
    assert validate_campaign(tmp_path)["maturity"] == "quarantine"
    write(tmp_path / "b01-full/receipt.json", {
        "schemaVersion": 1, "runId": "b01-full", "sut": "test", "posture": "full",
        "canonicality": {"label": "candidate-evidence", "blockers": []}})
    assert validate_campaign(tmp_path)["maturity"] == "quarantine"
    write(tmp_path / "paired-analysis-v2.json", {"verdict": "candidate"})
    report = validate_campaign(tmp_path)
    assert report["valid"] is True
    assert report["maturity"] == "candidate-evidence"


def test_campaign_validation_accepts_explicit_run_ids_and_smoke_summary(tmp_path):
    write(tmp_path / "schedule.json", {"runs": [
        {"runId": "full", "block": 1, "posture": "full"},
        {"runId": "sample-zero", "block": 1, "posture": "sample-zero"}]})
    for run_id in ("full", "sample-zero"):
        write(tmp_path / run_id / "receipt.json", {
            "schemaVersion": 1, "runId": run_id, "sut": "test", "posture": run_id,
            "canonicality": {"label": "noncanonical-functional-smoke",
                             "blockers": ["single functional repetition"]},
        })
    write(tmp_path / "summary.json", {"label": "noncanonical-functional-smoke"})
    report = validate_campaign(tmp_path)
    assert report["valid"] is True
    assert report["maturity"] == "noncanonical"


def test_generic_validator_cannot_promote_self_declared_canonical_receipt(tmp_path):
    write(tmp_path / "schedule.json", {"runs": [{"block": 1, "posture": "full"}]})
    write(tmp_path / "b01-full/receipt.json", {
        "schemaVersion": 1, "runId": "b01-full", "sut": "test", "posture": "full",
        "canonicality": {"label": "canonical-evidence", "blockers": []},
    })
    report = validate_campaign(tmp_path)
    assert report["maturity"] == "candidate-evidence"
    assert "cannot promote canonical" in report["canonicalityBlockers"][0]


def test_campaign_validator_rejects_wrong_json_shapes_and_canonicality_types(tmp_path):
    write(tmp_path / "schedule.json", ["not", "an", "object"])
    report = validate_campaign(tmp_path)
    assert report["maturity"] == "quarantine"
    assert "must contain an object" in " ".join(report["errors"])

    write(tmp_path / "schedule.json", {"runs": [{"block": 1, "posture": "full"}]})
    write(tmp_path / "b01-full/receipt.json", {
        "schemaVersion": 2, "runId": "b01-full", "sut": "test", "posture": "full",
        "canonicality": {"label": 1, "blockers": "not-a-list"},
    })
    report = validate_campaign(tmp_path)
    assert not report["valid"]
    assert "schemaVersion" in " ".join(report["errors"])
    assert "blockers must be a list" in " ".join(report["errors"])
