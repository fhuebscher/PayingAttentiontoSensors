from __future__ import annotations

import importlib.util
import json
from pathlib import Path


TOOL = Path(__file__).resolve().parents[1] / "tools/evidence_inventory.py"
SPEC = importlib.util.spec_from_file_location("evidence_inventory", TOOL)
assert SPEC and SPEC.loader
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def readiness(path: Path, artifact: str = ".local/evidence/otel-case",
              evidence_sha256: str = "0" * 64) -> None:
    write_json(path, {
        "schemaVersion": 1,
        "asOf": "2026-08-09",
        "modules": [{
            "module": "otel-demo",
            "highestScientificQualification": "smoke-validation",
            "priorEvidence": [{
                "id": "otel-case",
                "artifactPath": artifact,
                "evidenceSha256": evidence_sha256,
                "genericStructuralMaturity": "candidate-evidence",
                "curatedScientificQualification": "smoke-validation",
                "claimBoundary": "Lifecycle smoke only; no cost inference.",
            }],
        }],
    })


def receipt(run_id: str, posture: str) -> dict:
    return {
        "schemaVersion": 1,
        "runId": run_id,
        "sut": "otel-demo",
        "posture": posture,
        "canonicality": {"label": "candidate-evidence", "blockers": []},
    }


def test_curated_qualification_is_not_promoted_by_generic_validator(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    root = repo / ".local/evidence/otel-case"
    write_json(root / "schedule.json", {"runs": [{"block": 1, "posture": "full"}]})
    write_json(root / "b01-full/receipt.json", receipt("b01-full", "full"))
    ledger = repo / "readiness.json"
    readiness(ledger, evidence_sha256=inventory.build_manifest(root)["evidenceSha256"])

    report = inventory.build_inventory(repo / ".local/evidence", ledger, repo_root=repo)

    assert report["summary"]["campaigns"] == 1
    campaign = report["campaigns"][0]
    assert campaign["genericStructuralValidation"]["maturity"] == "candidate-evidence"
    assert campaign["curatedReadiness"]["scientificQualification"] == "smoke-validation"
    assert campaign["curatedReadiness"]["promotionApplied"] is False
    assert len(campaign["evidenceManifestSha256"]) == 64
    assert report["rawTelemetryIncluded"] is False


def test_legacy_schedule_is_discovered_but_quarantined(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    root = repo / ".local/evidence/otel-case"
    write_json(root / "schedule.json", {"sut": "otel-demo", "postures": ["full"]})
    ledger = repo / "readiness.json"
    readiness(ledger, evidence_sha256=inventory.build_manifest(root)["evidenceSha256"])

    report = inventory.build_inventory(repo / ".local/evidence", ledger, repo_root=repo)

    campaign = report["campaigns"][0]
    assert campaign["genericStructuralValidation"]["maturity"] == "quarantine"
    assert "schedule.runs" in campaign["genericStructuralValidation"]["errors"][0]
    assert campaign["curatedReadiness"]["scientificQualification"] == "smoke-validation"


def test_summary_and_receipts_discover_campaign_without_schedule(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    root = repo / ".local/evidence/hotel-case"
    write_json(root / "summary.json", {"schemaVersion": 1})
    write_json(root / "full/receipt.json", {
        "schemaVersion": 1, "runId": "full", "sut": "hotel-reservation",
        "posture": "full", "canonicality": {"label": "noncanonical", "blockers": []},
    })
    ledger = repo / "readiness.json"
    write_json(ledger, {"asOf": "2026-08-09", "modules": []})

    report = inventory.build_inventory(repo / ".local/evidence", ledger, repo_root=repo)

    assert [item["path"] for item in report["campaigns"]] == [".local/evidence/hotel-case"]
    assert report["campaigns"][0]["genericStructuralValidation"]["maturity"] == "quarantine"


def test_clean_checkout_without_local_evidence_is_valid_empty_inventory(tmp_path: Path) -> None:
    ledger = tmp_path / "readiness.json"
    readiness(ledger)

    report = inventory.build_inventory(tmp_path / ".local/evidence", ledger, repo_root=tmp_path)

    assert report["evidenceRootPresent"] is False
    assert report["campaigns"] == []
    assert report["summary"]["campaigns"] == 0


def test_discovery_never_lists_quarantine_or_partial_extractions(tmp_path: Path) -> None:
    evidence = tmp_path / ".local/evidence"
    for name in ("otel-pristine", "study-quarantine-effect",
                 "otel.quarantine-mutated", "otel.partial-extract"):
        root = evidence / name
        write_json(root / "schedule.json", {"runs": [{"block": 1, "posture": "full"}]})
        write_json(root / "b01-full/receipt.json", receipt("b01-full", "full"))

    assert inventory.discover_campaign_roots(evidence) == [
        evidence / "otel-pristine", evidence / "study-quarantine-effect"]


def test_online_boutique_lgtm_channel_maps_to_its_distinct_module(tmp_path: Path) -> None:
    campaign = tmp_path / "campaign"
    write_json(campaign / "schedule.json", {
        "configuration": {"sut": "online-boutique", "channel": "kind-lgtm"},
        "runs": [{"block": 1, "posture": "full"}],
    })

    assert inventory._detect_sut(campaign) == "online-boutique-lgtm"


def test_same_path_changed_bytes_cannot_inherit_curated_qualification(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    root = repo / ".local/evidence/otel-case"
    write_json(root / "schedule.json", {"runs": [{"block": 1, "posture": "full"}]})
    receipt_path = root / "b01-full/receipt.json"
    write_json(receipt_path, receipt("b01-full", "full"))
    ledger = repo / "readiness.json"
    reviewed_sha256 = inventory.build_manifest(root)["evidenceSha256"]
    readiness(ledger, evidence_sha256=reviewed_sha256)
    changed = receipt("b01-full", "full")
    changed["posture"] = "mutated-in-place"
    write_json(receipt_path, changed)

    campaign = inventory.build_inventory(
        repo / ".local/evidence", ledger, repo_root=repo)["campaigns"][0]

    assert campaign["curatedReadiness"]["scientificQualification"] == "unlisted-evidence"
    assert campaign["curatedReadiness"]["ledgerEntryMatched"] is False
    assert campaign["curatedReadiness"]["evidenceDigestMatched"] is False
    assert "differ" in campaign["curatedReadiness"]["claimBoundary"]
