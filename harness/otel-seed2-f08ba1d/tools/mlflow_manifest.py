#!/usr/bin/env python3
"""Import a campaign manifest and summary into a local MLflow run.

The files remain the evidence source of truth. MLflow is an index and visual
comparison surface; this deliberately logs summaries, not raw telemetry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from obsplacement.evidence import build_manifest, validate_campaign
from obsplacement.objectives import receipt_objectives


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "research/evidence-inventory.json"
DEFAULT_READINESS = ROOT / "research/five-module-readiness.json"
IMPORT_SCHEMA_VERSION = "4"


def _flat_numbers(value: Any, prefix: str = "") -> dict[str, float]:
    out: dict[str, float] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            out.update(_flat_numbers(child, f"{prefix}.{key}" if prefix else str(key)))
    elif (isinstance(value, (int, float)) and not isinstance(value, bool)
          and math.isfinite(float(value))):
        key = prefix.replace("/", "_").replace(".", "_")[:250]
        out[key] = float(value)
    return out


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _stable_digest(value: Any) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def _relative_campaign(campaign: Path, repo_root: Path) -> str:
    try:
        return campaign.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return campaign.resolve().as_posix()


def _campaign_goal(configuration: dict[str, Any], receipts: list[dict[str, Any]],
                   analysis: dict[str, Any]) -> str:
    for value in (configuration.get("goal"), configuration.get("goal_id"),
                  configuration.get("sharedContract", {}).get("goalRef")
                  if isinstance(configuration.get("sharedContract"), dict) else None,
                  analysis.get("goal")):
        if isinstance(value, str) and value:
            return value
    for receipt in receipts:
        visibility = receipt.get("visibility", {})
        for value in (receipt.get("goal"), receipt.get("goalId"),
                      visibility.get("goalId") if isinstance(visibility, dict) else None):
            if isinstance(value, str) and value:
                return value
    return "unknown"


def _curation(campaign: Path, evidence_digest: str, inventory_path: Path | None,
              readiness_path: Path | None, repo_root: Path) -> dict[str, Any]:
    """Bind a curated scientific ceiling to the exact reviewed evidence bytes."""
    campaign_path = _relative_campaign(campaign, repo_root)
    result: dict[str, Any] = {
        "campaignPath": campaign_path,
        "ledgerEntryMatched": False,
        "digestBound": False,
        "scientificQualification": "unlisted-evidence",
        "moduleCeiling": "unreviewed",
        "claimBoundary": "No digest-bound curated review matches this evidence; do not cite it.",
        "inventorySha256": None,
    }
    if inventory_path is None or not inventory_path.is_file():
        result["status"] = "inventory-unavailable"
    elif readiness_path is None or not readiness_path.is_file():
        result["status"] = "readiness-unavailable"
    else:
        raw = inventory_path.read_bytes()
        result["inventorySha256"] = hashlib.sha256(raw).hexdigest()
        inventory = json.loads(raw)
        readiness = _load(readiness_path)
        match = next((item for item in inventory.get("campaigns", [])
                      if str(item.get("path", "")).rstrip("/") == campaign_path.rstrip("/")), None)
        if match is None:
            result["status"] = "campaign-unlisted"
        else:
            curated = match.get("curatedReadiness", {})
            result["ledgerEntryMatched"] = bool(curated.get("ledgerEntryMatched", False))
            expected = match.get("evidenceManifestSha256")
            if expected != evidence_digest:
                result["status"] = "evidence-digest-mismatch"
                result["reviewedEvidenceSha256"] = expected
            elif not result["ledgerEntryMatched"]:
                result["status"] = "campaign-not-reviewed"
            else:
                module = next((item for item in readiness.get("modules", [])
                               if item.get("module") == curated.get("module")), None)
                entries = module.get("priorEvidence", []) if isinstance(module, dict) else []
                entry = next((item for item in entries
                              if item.get("artifactPath", "").rstrip("/") ==
                              campaign_path.rstrip("/") and
                              item.get("id") == curated.get("evidenceId")), None)
                exact_readiness_binding = (
                    isinstance(module, dict) and isinstance(entry, dict) and
                    entry.get("evidenceSha256") == evidence_digest and
                    curated.get("evidenceDigestMatched") is True and
                    curated.get("observedEvidenceSha256") == evidence_digest and
                    curated.get("reviewedEvidenceSha256") == evidence_digest and
                    curated.get("scientificQualification") ==
                    entry.get("curatedScientificQualification") and
                    curated.get("moduleCeiling") ==
                    module.get("highestScientificQualification") and
                    curated.get("claimBoundary") == entry.get("claimBoundary")
                )
                if not exact_readiness_binding:
                    result["status"] = "readiness-binding-mismatch"
                else:
                    result.update({
                        "status": "digest-bound",
                        "digestBound": True,
                        "scientificQualification": str(curated["scientificQualification"]),
                        "moduleCeiling": str(curated["moduleCeiling"]),
                        "module": curated.get("module"),
                        "evidenceId": curated.get("evidenceId"),
                        "claimBoundary": str(curated["claimBoundary"]),
                    })
    # Unrelated additions to the inventory must not duplicate a completed
    # import. Bind identity only to this campaign's reviewed decision.
    result["fingerprint"] = _stable_digest({
        key: value for key, value in result.items() if key != "inventorySha256"
    })
    return result


def import_campaign(campaign: Path, experiment: str, tracking_uri: str, *,
                    inventory_path: Path | None = DEFAULT_INVENTORY,
                    readiness_path: Path | None = DEFAULT_READINESS,
                    repo_root: Path = ROOT) -> str:
    import mlflow

    schedule_path = campaign / "schedule.json"
    analysis_path = next((campaign / name for name in
                          ("paired-analysis-v2.json", "paired-analysis.json", "summary.json")
                          if (campaign / name).is_file()), None)
    schedule = _load(schedule_path) if schedule_path.is_file() else {}
    analysis = _load(analysis_path) if analysis_path is not None else {}
    receipt_paths = sorted(campaign.glob("*/receipt.json"))
    receipt_documents = {path: _load(path) for path in receipt_paths}
    first_receipt = receipt_documents[receipt_paths[0]] if receipt_paths else {}
    manifest = build_manifest(campaign)
    validation = validate_campaign(campaign)
    evidence_digest = manifest["evidenceSha256"]
    curation = _curation(
        campaign, evidence_digest, inventory_path, readiness_path, repo_root)
    mlflow.set_tracking_uri(tracking_uri)
    experiment_info = mlflow.set_experiment(experiment)
    client = mlflow.tracking.MlflowClient()
    campaign_label = str(curation.get("evidenceId") or campaign.name)
    configuration = schedule.get("configuration", schedule)
    sut = str(configuration.get("sut", analysis.get("sut", first_receipt.get("sut", "unknown"))))
    module = str(curation.get("module") or sut)
    channel = str(configuration.get("channel") or first_receipt.get("channel") or "unknown")
    goal = _campaign_goal(configuration, list(receipt_documents.values()), analysis)
    receipt_identities = {}
    for path in receipt_paths:
        relative = path.relative_to(campaign).as_posix()
        receipt_digest = next(item["sha256"] for item in manifest["files"]
                              if item["path"] == relative)
        identity = hashlib.sha256(f"{relative}\0{receipt_digest}".encode()).hexdigest()
        receipt_identities[path] = {
            "path": relative, "sha256": receipt_digest, "identitySha256": identity,
        }
    expected_identities = {item["identitySha256"] for item in receipt_identities.values()}

    def find_parents(status: str) -> list:
        return mlflow.search_runs(
            experiment_ids=[experiment_info.experiment_id],
            filter_string=(f"tags.evidence_manifest_sha256 = '{evidence_digest}' AND "
                           f"tags.run_role = 'campaign' AND tags.import_status = '{status}' AND "
                           f"tags.import_schema_version = '{IMPORT_SCHEMA_VERSION}' AND "
                           f"tags.curation_fingerprint = '{curation['fingerprint']}'"),
            output_format="list",
        )

    def find_children(parent_id: str, complete_only: bool = True) -> list:
        completed = " AND tags.import_status = 'complete'" if complete_only else ""
        return mlflow.search_runs(
            experiment_ids=[experiment_info.experiment_id],
            filter_string=(f"tags.`mlflow.parentRunId` = '{parent_id}' AND "
                           f"tags.run_role = 'campaign-receipt'{completed}"),
            output_format="list",
        )

    completed_parents = find_parents("complete")
    for prior in completed_parents:
        prior_children = find_children(prior.info.run_id)
        child_identities = [child.data.tags.get("receipt_identity_sha256")
                            for child in prior_children]
        if (len(child_identities) == len(expected_identities) and
                set(child_identities) == expected_identities):
            # Repair descriptive identity on old completed schema-compatible
            # imports without creating a duplicate scientific record.
            client.set_tag(prior.info.run_id, "mlflow.runName", campaign_label)
            client.set_tag(prior.info.run_id, "campaign", campaign_label)
            client.set_tag(prior.info.run_id, "campaign_path", curation["campaignPath"])
            client.set_tag(prior.info.run_id, "sut", sut)
            client.set_tag(prior.info.run_id, "module", module)
            client.set_tag(prior.info.run_id, "channel", channel)
            client.set_tag(prior.info.run_id, "goal", goal)
            for child in prior_children:
                client.set_tag(child.info.run_id, "module", module)
                client.set_tag(child.info.run_id, "channel", channel)
                client.set_tag(child.info.run_id, "goal", goal)
            return prior.info.run_id

    resumable = find_parents("importing") + completed_parents
    if resumable:
        parent_id = resumable[0].info.run_id
    else:
        with mlflow.start_run(run_name=campaign_label) as run:
            parent_id = run.info.run_id
            mlflow.set_tags({
                "source": "campaign-manifest", "run_role": "campaign",
                "import_status": "importing", "campaign": campaign_label,
                "campaign_path": curation["campaignPath"],
                "evidence_manifest_sha256": evidence_digest,
                "import_schema_version": IMPORT_SCHEMA_VERSION,
                "curation_fingerprint": curation["fingerprint"],
            })

    try:
        with mlflow.start_run(run_id=parent_id):
            mlflow.set_tags({
                "source": "campaign-manifest", "run_role": "campaign",
                "import_status": "importing", "campaign": campaign_label,
                "campaign_path": curation["campaignPath"],
                "evidence_manifest_sha256": evidence_digest,
                "import_schema_version": IMPORT_SCHEMA_VERSION,
                "curation_fingerprint": curation["fingerprint"],
                "curation_status": curation["status"],
                "curation_digest_bound": str(curation["digestBound"]).lower(),
                "curated_scientific_qualification": curation["scientificQualification"],
                "module_evidence_ceiling": curation["moduleCeiling"],
                "scientific_use_eligible": str(
                    validation["valid"] and curation["digestBound"]
                    and curation["scientificQualification"] in
                    {"candidate-evidence", "canonical-evidence"}).lower(),
                "claim_boundary": curation["claimBoundary"][:5000],
                "structural_maturity": validation["maturity"],
                "structurally_valid": str(validation["valid"]).lower(),
                "validation_scope": validation.get("validationScope", "generic-structural-only"),
                "sut": sut, "module": module, "channel": channel, "goal": goal,
            })
            params = {k: str(v)[:500] for k, v in configuration.items()
                      if not isinstance(v, (dict, list))}
            if params:
                mlflow.log_params(params)
            numbers = _flat_numbers(analysis)
            if numbers:
                mlflow.log_metrics(numbers)
            if schedule_path.is_file():
                mlflow.log_artifact(str(schedule_path), artifact_path="evidence")
            if analysis_path is not None:
                mlflow.log_artifact(str(analysis_path), artifact_path="evidence")
            with tempfile.TemporaryDirectory() as temporary:
                generated = Path(temporary)
                manifest_path = generated / "evidence-manifest.json"
                validation_path = generated / "validation-report.json"
                curation_path = generated / "curation-report.json"
                manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
                validation_path.write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n")
                curation_path.write_text(json.dumps(curation, indent=2, sort_keys=True) + "\n")
                mlflow.log_artifact(str(manifest_path), artifact_path="evidence")
                mlflow.log_artifact(str(validation_path), artifact_path="evidence")
                mlflow.log_artifact(str(curation_path), artifact_path="evidence")

        for receipt_path, receipt_identity in receipt_identities.items():
            receipt = receipt_documents[receipt_path]
            scoped = mlflow.search_runs(
                experiment_ids=[experiment_info.experiment_id],
                filter_string=(f"tags.`mlflow.parentRunId` = '{parent_id}' AND "
                               "tags.receipt_identity_sha256 = "
                               f"'{receipt_identity['identitySha256']}'"),
                output_format="list",
            )
            if any(item.data.tags.get("import_status") == "complete" for item in scoped):
                continue
            child_id = scoped[0].info.run_id if scoped else None
            child_context = (mlflow.start_run(run_id=child_id) if child_id else
                             mlflow.start_run(run_name=receipt_path.parent.name,
                                              tags={"mlflow.parentRunId": parent_id}))
            with child_context:
                canonicality = receipt.get("canonicality", {})
                mlflow.set_tags({
                    "run_role": "campaign-receipt", "import_status": "importing",
                    "receipt_sha256": receipt_identity["sha256"],
                    "receipt_path": receipt_identity["path"],
                    "receipt_identity_sha256": receipt_identity["identitySha256"],
                    "sut": str(receipt.get("sut", sut)), "goal": goal,
                    "module": module, "channel": channel,
                    "posture": str(receipt.get("posture", "unknown")),
                    "declared_evidence_maturity": str(canonicality.get("label", "unknown")),
                    "declared_blocker_free": str(not canonicality.get("blockers", [])).lower(),
                    "curation_digest_bound": str(curation["digestBound"]).lower(),
                    "curated_scientific_qualification": curation["scientificQualification"],
                    "scientific_use_eligible": str(
                        validation["valid"] and curation["digestBound"]
                        and curation["scientificQualification"] in
                        {"candidate-evidence", "canonical-evidence"}).lower(),
                })
                metrics = _flat_numbers({key: receipt.get(key) for key in
                                         ("latencyMs", "resources", "telemetry", "workload")})
                objectives = receipt_objectives(receipt)
                metrics.update({f"objective_{key}": value for key, value in
                                objectives["values"].items() if value is not None})
                if metrics:
                    mlflow.log_metrics(metrics)
                mlflow.log_artifact(str(receipt_path), artifact_path="evidence")
                with tempfile.TemporaryDirectory() as temporary:
                    objective_path = Path(temporary) / "objective-vector.json"
                    objective_path.write_text(json.dumps(objectives, indent=2, sort_keys=True) + "\n")
                    mlflow.log_artifact(str(objective_path), artifact_path="evidence")
                mlflow.set_tags({
                    "objective_observed": ",".join(objectives["observed"]),
                    "objective_missing": ",".join(objectives["missing"]),
                })
                mlflow.set_tag("import_status", "complete")

        imported = find_children(parent_id)
        imported_identities = [child.data.tags.get("receipt_identity_sha256") for child in imported]
        if (len(imported_identities) != len(expected_identities) or
                set(imported_identities) != expected_identities):
            raise RuntimeError(
                "MLflow receipt children do not exactly match the evidence manifest: "
                f"expected={sorted(expected_identities)}, "
                f"actual={sorted(str(x) for x in imported_identities)}"
            )
        client.set_tag(parent_id, "import_status", "complete")
        client.set_tag(parent_id, "import_error", "")
        return parent_id
    except Exception as exc:
        # Keep the parent resumable. A later import fills only missing children.
        client.set_tag(parent_id, "import_status", "importing")
        client.set_tag(parent_id, "import_error", f"{type(exc).__name__}: {exc}"[:5000])
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--experiment", default="observability-placement")
    parser.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///./.local/mlflow/mlflow.db"))
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY,
                        help="digest-bearing curated evidence inventory")
    parser.add_argument("--readiness", type=Path, default=DEFAULT_READINESS,
                        help="authoritative reviewed readiness ledger")
    args = parser.parse_args()
    Path(".local/mlflow").mkdir(parents=True, exist_ok=True)
    print(import_campaign(args.campaign, args.experiment, args.tracking_uri,
                          inventory_path=args.inventory, readiness_path=args.readiness))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
