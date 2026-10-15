import copy
import json
from pathlib import Path

from obsplacement.readiness import load_and_validate, validate_readiness


ROOT = Path(__file__).parents[1]
LEDGER = ROOT / "research/five-module-readiness.json"


def test_five_module_readiness_is_curated_and_auditable():
    report = load_and_validate(LEDGER, ROOT)
    assert report["valid"], report
    assert report["moduleCount"] == 5
    assert report["applicationFamilyCount"] == 4
    assert all(item["verdict"] == "pass" for item in report["extensionAudits"].values())


def test_generic_maturity_cannot_promote_curated_scientific_status():
    document = json.loads(LEDGER.read_text())
    otel = next(row for row in document["modules"] if row["module"] == "otel-demo")
    assert otel["priorEvidence"][0]["genericStructuralMaturity"] == "candidate-evidence"
    assert otel["priorEvidence"][0]["curatedScientificQualification"] == "smoke-validation"
    assert otel["highestScientificQualification"] == "smoke-validation"


def test_readiness_rejects_channel_as_fifth_family_and_lock_drift():
    document = json.loads(LEDGER.read_text())
    changed = copy.deepcopy(document)
    lgtm = next(row for row in changed["modules"] if row["module"] == "online-boutique-lgtm")
    lgtm["applicationFamily"] = "online-boutique-lgtm"
    lgtm["sourceCommit"] = "0" * 40
    report = validate_readiness(changed, ROOT)
    assert not report["valid"]
    assert any("four application families" in error for error in report["errors"])
    assert any("source.lock" in error for error in report["errors"])


def test_readiness_rejects_level_contradictions_and_unbound_evidence_paths():
    document = json.loads(LEDGER.read_text())
    changed = copy.deepcopy(document)
    teastore = next(row for row in changed["modules"] if row["module"] == "teastore")
    teastore["evidenceLevels"]["candidate"] = "absent"
    evidence = teastore["priorEvidence"][0]
    evidence["artifactPath"] = ".local/evidence/does-not-exist"
    evidence.pop("artifactAvailability", None)
    evidence.pop("evidenceSha256", None)
    report = validate_readiness(changed, ROOT)
    assert not report["valid"]
    assert any("contradict" in error for error in report["errors"])
    assert any("availability" in error for error in report["errors"])
    assert any("evidence digest" in error for error in report["errors"])
