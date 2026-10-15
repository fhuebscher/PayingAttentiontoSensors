import importlib.util
import json
from pathlib import Path

import mlflow
import pytest

from obsplacement.evidence import build_manifest


MODULE = Path(__file__).parents[1] / "tools/mlflow_manifest.py"
SPEC = importlib.util.spec_from_file_location("mlflow_manifest", MODULE)
mlflow_manifest = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(mlflow_manifest)


@pytest.fixture(autouse=True)
def _artifact_root_outside_the_repository(tmp_path: Path, monkeypatch):
    """Keep MLflow's default `./mlruns` artifact root out of the working tree.

    With a sqlite backend MLflow resolves an experiment's artifact location
    relative to the process working directory, so any experiment this module
    does not create itself left an `mlruns/` directory in the repository root.
    The multi-SUT construction delivery gate treats an ignored, non-cache
    delivery as forbidden, so a plain test run made the repository look dirty
    to `tools/validate_multisut_construction.py`.
    """
    monkeypatch.chdir(tmp_path)


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


def campaign(root: Path) -> Path:
    write(root / "schedule.json", {"configuration": {
        "sut": "test", "channel": "fixture", "goal": "path"}, "runs": [
        {"block": 1, "posture": "full"}, {"block": 1, "posture": "off"},
    ]})
    for posture in ("full", "off"):
        write(root / f"b01-{posture}/receipt.json", {
            "schemaVersion": 1, "runId": f"b01-{posture}", "sut": "test", "posture": posture,
            "workload": {"offered": 2, "completed": 2, "failed": 0},
            "canonicality": {"label": "candidate-evidence", "blockers": []},
        })
    write(root / "summary.json", {"verdict": "candidate"})
    return root


def test_import_is_parent_scoped_and_idempotent(tmp_path: Path):
    evidence = campaign(tmp_path / "campaign")
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    mlflow.set_tracking_uri(uri)
    mlflow.create_experiment("test-import", artifact_location=(tmp_path / "artifacts").as_uri())
    first = mlflow_manifest.import_campaign(evidence, "test-import", uri)
    second = mlflow_manifest.import_campaign(evidence, "test-import", uri)
    assert second == first
    mlflow.set_tracking_uri(uri)
    experiment = mlflow.get_experiment_by_name("test-import")
    assert experiment is not None
    children = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string=f"tags.`mlflow.parentRunId` = '{first}' AND tags.run_role = 'campaign-receipt'",
        output_format="list",
    )
    assert len(children) == 2
    assert all(item.data.tags["import_status"] == "complete" for item in children)
    parent = mlflow.get_run(first)
    assert parent.data.tags["evidence_manifest_sha256"] == build_manifest(evidence)["evidenceSha256"]
    assert parent.data.tags["curated_scientific_qualification"] == "unlisted-evidence"
    assert parent.data.tags["scientific_use_eligible"] == "false"
    assert parent.data.tags["module"] == "test"
    assert parent.data.tags["channel"] == "fixture"
    assert parent.data.tags["goal"] == "path"
    assert all(item.data.tags["module"] == "test" and
               item.data.tags["channel"] == "fixture" and
               item.data.tags["goal"] == "path" for item in children)


def test_byte_identical_receipts_remain_distinct_children(tmp_path: Path):
    evidence = tmp_path / "identical"
    write(evidence / "schedule.json", {"configuration": {"sut": "test"}, "runs": [
        {"runId": "one", "block": 1, "posture": "full"},
        {"runId": "two", "block": 1, "posture": "off"},
    ]})
    identical = {"schemaVersion": 1, "sut": "test", "canonicality": {
        "label": "noncanonical", "blockers": ["synthetic importer fixture"]}}
    write(evidence / "one/receipt.json", identical)
    write(evidence / "two/receipt.json", identical)
    write(evidence / "summary.json", {"verdict": "noncanonical"})
    uri = f"sqlite:///{tmp_path / 'identical.db'}"
    mlflow.set_tracking_uri(uri)
    mlflow.create_experiment("identical-import", artifact_location=(tmp_path / "artifacts").as_uri())
    parent = mlflow_manifest.import_campaign(evidence, "identical-import", uri)
    experiment = mlflow.get_experiment_by_name("identical-import")
    children = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string=f"tags.`mlflow.parentRunId` = '{parent}' AND tags.run_role = 'campaign-receipt'",
        output_format="list",
    )
    assert len(children) == 2
    assert {item.data.tags["receipt_path"] for item in children} == {
        "one/receipt.json", "two/receipt.json"}
    assert len({item.data.tags["receipt_sha256"] for item in children}) == 1
    assert len({item.data.tags["receipt_identity_sha256"] for item in children}) == 2


def test_digest_bound_curated_ceiling_overrides_generic_candidate(tmp_path: Path):
    repo = tmp_path / "repo"
    evidence = campaign(repo / ".local/evidence/campaign")
    evidence_sha = build_manifest(evidence)["evidenceSha256"]
    inventory_path = repo / "research/evidence-inventory.json"
    readiness_path = repo / "research/five-module-readiness.json"

    def inventory(qualification: str) -> None:
        claim = ("Lifecycle smoke only." if qualification == "smoke-validation"
                 else "Candidate within fixture scope.")
        write(inventory_path, {"campaigns": [{
            "path": ".local/evidence/campaign",
            "evidenceManifestSha256": evidence_sha,
            "curatedReadiness": {
                "ledgerEntryMatched": True,
                "module": "test",
                "moduleCeiling": qualification,
                "evidenceId": "campaign",
                "evidenceDigestMatched": True,
                "observedEvidenceSha256": evidence_sha,
                "reviewedEvidenceSha256": evidence_sha,
                "scientificQualification": qualification,
                "claimBoundary": claim,
            },
        }]})
        write(readiness_path, {"modules": [{
            "module": "test", "highestScientificQualification": qualification,
            "priorEvidence": [{"id": "campaign", "artifactPath": ".local/evidence/campaign",
                               "evidenceSha256": evidence_sha,
                               "curatedScientificQualification": qualification,
                               "claimBoundary": claim}],
        }]})

    inventory("smoke-validation")
    uri = f"sqlite:///{tmp_path / 'curated.db'}"
    mlflow.set_tracking_uri(uri)
    mlflow.create_experiment("curated-import", artifact_location=(tmp_path / "artifacts").as_uri())
    smoke_parent = mlflow_manifest.import_campaign(
        evidence, "curated-import", uri, inventory_path=inventory_path,
        readiness_path=readiness_path, repo_root=repo)
    assert mlflow_manifest.import_campaign(
        evidence, "curated-import", uri, inventory_path=inventory_path,
        readiness_path=readiness_path, repo_root=repo) == smoke_parent
    smoke = mlflow.get_run(smoke_parent)
    assert smoke.data.tags["structural_maturity"] == "candidate-evidence"
    assert smoke.data.tags["curated_scientific_qualification"] == "smoke-validation"
    assert smoke.data.tags["curation_digest_bound"] == "true"
    assert smoke.data.tags["scientific_use_eligible"] == "false"

    forged = json.loads(inventory_path.read_text())
    forged["campaigns"][0]["curatedReadiness"]["scientificQualification"] = "canonical-evidence"
    forged["campaigns"][0]["curatedReadiness"]["moduleCeiling"] = "canonical-evidence"
    write(inventory_path, forged)
    forged_parent = mlflow_manifest.import_campaign(
        evidence, "curated-import", uri, inventory_path=inventory_path,
        readiness_path=readiness_path, repo_root=repo)
    forged_run = mlflow.get_run(forged_parent)
    assert forged_run.data.tags["curation_status"] == "readiness-binding-mismatch"
    assert forged_run.data.tags["curation_digest_bound"] == "false"
    assert forged_run.data.tags["curated_scientific_qualification"] == "unlisted-evidence"
    assert forged_run.data.tags["scientific_use_eligible"] == "false"

    inventory("candidate-evidence")
    candidate_parent = mlflow_manifest.import_campaign(
        evidence, "curated-import", uri, inventory_path=inventory_path,
        readiness_path=readiness_path, repo_root=repo)
    assert candidate_parent != smoke_parent
    candidate = mlflow.get_run(candidate_parent)
    assert candidate.data.tags["curated_scientific_qualification"] == "candidate-evidence"
    assert candidate.data.tags["scientific_use_eligible"] == "true"


def test_stale_curated_digest_fails_closed(tmp_path: Path):
    repo = tmp_path / "repo"
    evidence = campaign(repo / ".local/evidence/campaign")
    inventory_path = repo / "research/evidence-inventory.json"
    readiness_path = repo / "research/five-module-readiness.json"
    write(inventory_path, {"campaigns": [{
        "path": ".local/evidence/campaign",
        "evidenceManifestSha256": "0" * 64,
        "curatedReadiness": {
            "ledgerEntryMatched": True,
            "moduleCeiling": "canonical-evidence",
            "scientificQualification": "canonical-evidence",
            "claimBoundary": "stale review",
        },
    }]})
    write(readiness_path, {"modules": [{
        "module": None, "highestScientificQualification": "canonical-evidence",
        "priorEvidence": [{"id": None, "artifactPath": ".local/evidence/campaign",
                           "evidenceSha256": "0" * 64,
                           "curatedScientificQualification": "canonical-evidence",
                           "claimBoundary": "stale review"}],
    }]})
    uri = f"sqlite:///{tmp_path / 'stale.db'}"
    mlflow.set_tracking_uri(uri)
    mlflow.create_experiment("stale-import", artifact_location=(tmp_path / "artifacts").as_uri())
    parent = mlflow_manifest.import_campaign(
        evidence, "stale-import", uri, inventory_path=inventory_path,
        readiness_path=readiness_path, repo_root=repo)
    run = mlflow.get_run(parent)
    assert run.data.tags["curation_status"] == "evidence-digest-mismatch"
    assert run.data.tags["curated_scientific_qualification"] == "unlisted-evidence"
    assert run.data.tags["scientific_use_eligible"] == "false"
