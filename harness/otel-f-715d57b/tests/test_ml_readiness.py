from __future__ import annotations

import importlib.util
import json
from pathlib import Path


TOOL = Path(__file__).resolve().parents[1] / "tools/ml_readiness.py"
SPEC = importlib.util.spec_from_file_location("ml_readiness", TOOL)
assert SPEC and SPEC.loader
ml = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ml)


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_rows_share_split_group_within_campaign_block_and_keep_missingness(tmp_path: Path) -> None:
    campaign = tmp_path / ".local/evidence/case"
    write(campaign / "schedule.json", {"configuration": {"goal": "path-cost", "rate": 1}, "runs": []})
    base = {"schemaVersion": 1, "sut": "teastore", "workload": {"offered": 10, "completed": 10}}
    for posture in ("none", "full"):
        write(campaign / f"b01-{posture}/receipt.json", {**base, "runId": f"b01-{posture}", "posture": posture})
    inventory = {"campaigns": [{"path": ".local/evidence/case", "sut": "teastore", "curatedReadiness": {
        "module": "teastore", "scientificQualification": "candidate-evidence", "evidenceId": "case"}}]}
    readiness = {"modules": [{"module": "teastore", "applicationFamily": "teastore"}]}

    rows = ml.extract_rows(tmp_path, inventory, readiness)

    assert len(rows) == 2
    assert rows[0]["splitGroupId"] == rows[1]["splitGroupId"]
    assert rows[0]["independenceGroupId"] == rows[1]["independenceGroupId"]
    assert rows[0]["objectiveMissing"]["latency_p95_ms"] is True
    assert len(rows[0]["provenance"]["receiptSha256"]) == 64
    assert len(rows[0]["provenance"]["campaignMetadataSha256"]) == 64


def test_model_readiness_fails_closed_on_receipt_repetitions() -> None:
    rows = []
    for index in range(200):
        rows.append({
            "campaign": "one-campaign", "splitGroupId": "one-block",
            "independenceGroupId": "one-independent-group",
            "curatedQualification": "candidate-evidence",
            "observedObjectives": ["a", "b", "c"],
            "objectives": {"required_sensor_retention": 1.0},
        })

    result = ml.sufficiency(rows)

    assert result["models"]["xgboost"]["ready"] is False
    assert result["models"]["gaussianMixture"]["ready"] is False
    assert result["models"]["xgboost"]["criteria"]["independentCampaignFaultLoadGroups"]["observed"] == 1


def test_empty_clean_checkout_report_is_not_ml_ready(tmp_path: Path) -> None:
    inventory_path, readiness_path = tmp_path / "inventory.json", tmp_path / "readiness.json"
    write(inventory_path, {"asOf": "2026-08-09", "campaigns": []})
    write(readiness_path, {"modules": []})

    report = ml.build_report(tmp_path, inventory_path, readiness_path)

    assert report["rows"] == []
    assert report["rawTelemetryIncluded"] is False
    assert not report["dataSufficiency"]["models"]["xgboost"]["ready"]
    assert not report["dataSufficiency"]["models"]["gaussianMixture"]["ready"]


def test_rows_preserve_channel_module_and_propagate_campaign_goal(tmp_path: Path) -> None:
    campaign = tmp_path / ".local/evidence/lgtm"
    goal_ref = "modules/online-boutique/goals/homepage-path.json"
    write(campaign / "schedule.json", {"configuration": {
        "sut": "online-boutique", "channel": "kind-lgtm",
        "sharedContract": {"goalRef": goal_ref},
    }})
    write(campaign / "b01-full/receipt.json", {
        "schemaVersion": 1, "runId": "b01-full", "sut": "online-boutique",
        "posture": "full", "visibility": {"goalId": "receipt-goal"},
        "workload": {"offered": 1, "completed": 1},
    })
    write(campaign / "b01-none/receipt.json", {
        "schemaVersion": 1, "runId": "b01-none", "sut": "online-boutique",
        "posture": "none", "workload": {"offered": 1, "completed": 1},
    })
    digest = ml.build_manifest(campaign)["evidenceSha256"]
    inventory = {"campaigns": [{
        "path": ".local/evidence/lgtm", "sut": "online-boutique-lgtm",
        "evidenceManifestSha256": digest,
        "curatedReadiness": {
            "module": "online-boutique-lgtm", "moduleCeiling": "smoke-validation",
            "ledgerEntryMatched": True, "evidenceDigestMatched": True,
            "observedEvidenceSha256": digest, "reviewedEvidenceSha256": digest,
            "evidenceId": "lgtm", "scientificQualification": "smoke-validation"},
    }]}
    readiness = {"modules": [{"module": "online-boutique-lgtm",
                               "applicationFamily": "google-online-boutique",
                               "highestScientificQualification": "smoke-validation",
                               "priorEvidence": [{
                                   "id": "lgtm", "artifactPath": ".local/evidence/lgtm",
                                   "evidenceSha256": digest,
                                   "curatedScientificQualification": "smoke-validation",
                               }]}]}

    rows = ml.extract_rows(tmp_path, inventory, readiness)
    row = rows[0]

    assert row["sut"] == "online-boutique-lgtm"
    assert row["sutAttributionBound"] is True
    assert row["family"] == "google-online-boutique"
    assert {item["goal"] for item in rows} == {goal_ref}
    assert ml._goal({"sharedContract": {"goalRef": goal_ref}}, {}) == goal_ref


def test_rows_recompute_digest_and_reject_forged_inventory_or_same_path_mutation(
        tmp_path: Path) -> None:
    campaign_path = ".local/evidence/case"
    campaign = tmp_path / campaign_path
    write(campaign / "schedule.json", {
        "configuration": {"sut": "teastore", "goal": "path-cost"}, "runs": []})
    receipt_path = campaign / "b01-full/receipt.json"
    write(receipt_path, {"schemaVersion": 1, "runId": "b01-full", "sut": "teastore",
                         "posture": "full", "workload": {"offered": 1, "completed": 1}})
    digest = ml.build_manifest(campaign)["evidenceSha256"]
    curated = {"module": "teastore", "moduleCeiling": "candidate-evidence",
               "ledgerEntryMatched": True,
               "evidenceDigestMatched": True, "evidenceId": "case",
               "observedEvidenceSha256": digest, "reviewedEvidenceSha256": digest,
               "scientificQualification": "candidate-evidence"}
    readiness = {"modules": [{"module": "teastore", "applicationFamily": "teastore",
                               "highestScientificQualification": "candidate-evidence",
                               "priorEvidence": [{"id": "case", "artifactPath": campaign_path,
                                                  "evidenceSha256": digest,
                                                  "curatedScientificQualification":
                                                      "candidate-evidence"}]}]}

    forged_inventory = {"campaigns": [{"path": campaign_path, "sut": "teastore",
                                        "evidenceManifestSha256": "0" * 64,
                                        "curatedReadiness": curated}]}
    forged = ml.extract_rows(tmp_path, forged_inventory, readiness)[0]
    assert forged["curatedQualification"] == "unlisted-evidence"
    assert not forged["provenance"]["curationBinding"]["passed"]

    bound_inventory = {"campaigns": [{"path": campaign_path, "sut": "teastore",
                                       "evidenceManifestSha256": digest,
                                       "curatedReadiness": curated}]}
    assert ml.extract_rows(tmp_path, bound_inventory, readiness)[0][
        "curatedQualification"] == "candidate-evidence"
    write(receipt_path, {"schemaVersion": 1, "runId": "b01-full", "sut": "teastore",
                         "posture": "changed", "workload": {"offered": 1, "completed": 1}})
    changed = ml.extract_rows(tmp_path, bound_inventory, readiness)[0]
    assert changed["curatedQualification"] == "unlisted-evidence"
    assert "current campaign digest differs from evidence inventory" in changed[
        "provenance"]["curationBinding"]["blockers"]

    write(receipt_path, {"schemaVersion": 1, "runId": "b01-full", "sut": "teastore",
                         "posture": "full", "workload": {"offered": 1, "completed": 1}})
    forged_qualification = json.loads(json.dumps(bound_inventory))
    forged_qualification["campaigns"][0]["curatedReadiness"][
        "scientificQualification"] = "canonical-evidence"
    row = ml.extract_rows(tmp_path, forged_qualification, readiness)[0]
    assert row["curatedQualification"] == "unlisted-evidence"
    assert "inventory qualification differs from readiness ledger" in row[
        "provenance"]["curationBinding"]["blockers"]

    forged_sut = json.loads(json.dumps(bound_inventory))
    forged_sut["campaigns"][0]["sut"] = "hotel-reservation"
    row = ml.extract_rows(tmp_path, forged_sut, readiness)[0]
    assert row["curatedQualification"] == "unlisted-evidence"
    assert row["sut"] == "hotel-reservation"
    assert row["sutAttributionBound"] is False
    assert "inventory SUT differs from authoritative readiness module" in row[
        "provenance"]["curationBinding"]["blockers"]
