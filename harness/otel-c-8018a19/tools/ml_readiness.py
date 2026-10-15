#!/usr/bin/env python3
"""Extract leakage-safe run rows and fail-closed ML readiness diagnostics."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from obsplacement.evidence import build_manifest  # noqa: E402
from obsplacement.objectives import OBJECTIVE_DIRECTIONS, receipt_objectives  # noqa: E402


ELIGIBLE_QUALIFICATIONS = {"candidate-evidence", "canonical-evidence"}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest_file(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _stable_id(*parts: object) -> str:
    encoded = json.dumps(parts, separators=(",", ":"), sort_keys=True).encode()
    return _digest_bytes(encoded)[:24]


def _block(run_id: str) -> str:
    prefix = run_id.split("-", 1)[0]
    return prefix if len(prefix) >= 2 and prefix[0] == "b" and prefix[1:].isdigit() else "unknown"


def _configuration(campaign: Path) -> dict[str, Any]:
    schedule = campaign / "schedule.json"
    if not schedule.is_file():
        return {}
    value = _read(schedule)
    configured = value.get("configuration", value) if isinstance(value, dict) else {}
    return configured if isinstance(configured, dict) else {}


def _load_signature(configuration: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "rate": ("requestsPerSecond", "rate"),
        "concurrency": ("concurrency",),
        "durationSeconds": ("measurementSeconds", "duration", "durationSeconds"),
    }
    result: dict[str, Any] = {}
    for target, keys in aliases.items():
        for key in keys:
            if configuration.get(key) is not None:
                result[target] = configuration[key]
                break
    workload = receipt.get("workload", {}) if isinstance(receipt.get("workload"), dict) else {}
    if "concurrency" not in result and workload.get("concurrency") is not None:
        result["concurrency"] = workload["concurrency"]
    if not result and workload.get("offered") is not None:
        result["offeredRequests"] = workload["offered"]
    return result


def _source_hashes(receipt: dict[str, Any]) -> dict[str, str]:
    source = receipt.get("source", {}) if isinstance(receipt.get("source"), dict) else {}
    return {str(key): str(value) for key, value in sorted(source.items())
            if value is not None and isinstance(value, (str, int)) and
            ("sha" in str(key).lower() or "commit" in str(key).lower())}


def _family(module: str | None, readiness: dict[str, Any]) -> str:
    for item in readiness.get("modules", []):
        if item.get("module") == module:
            return str(item.get("applicationFamily", "unknown"))
    return "unknown"


def _goal(configuration: dict[str, Any], receipt: dict[str, Any]) -> str:
    for value in (configuration.get("goal"), configuration.get("goal_id"),
                  receipt.get("goal"), receipt.get("goalId")):
        if isinstance(value, str) and value:
            return value
    visibility = receipt.get("visibility", {})
    if isinstance(visibility, dict) and isinstance(visibility.get("goalId"), str):
        return visibility["goalId"]
    shared = configuration.get("sharedContract", {})
    if isinstance(shared, dict) and isinstance(shared.get("goalRef"), str):
        return shared["goalRef"]
    return "unknown"


def _campaign_metadata_digest(campaign: Path, receipt_paths: list[Path]) -> str:
    metadata = []
    for name in ("schedule.json", "summary.json", "paired-analysis-v2.json", "paired-analysis.json"):
        path = campaign / name
        if path.is_file():
            metadata.append((name, _digest_file(path)))
    metadata.extend((path.parent.name, _digest_file(path)) for path in receipt_paths)
    return _digest_bytes(json.dumps(metadata, separators=(",", ":"), sort_keys=True).encode())


def _curation_binding(campaign_path: str, campaign: Path, evidence: dict[str, Any],
                      readiness: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    curated = evidence.get("curatedReadiness", {})
    try:
        observed = build_manifest(campaign)["evidenceSha256"]
    except (OSError, TypeError, ValueError) as exc:
        observed = None
        blockers.append(f"current campaign digest cannot be recomputed: {type(exc).__name__}: {exc}")
    inventory_sha256 = evidence.get("evidenceManifestSha256")
    if observed != inventory_sha256:
        blockers.append("current campaign digest differs from evidence inventory")
    if (curated.get("ledgerEntryMatched") is not True or
            curated.get("evidenceDigestMatched") is not True):
        blockers.append("inventory curation is not digest-bound to readiness")
    if (curated.get("observedEvidenceSha256") != observed or
            curated.get("reviewedEvidenceSha256") != observed):
        blockers.append("inventory curation digest fields differ from current campaign")
    authoritative = [
        (module, entry)
        for module in readiness.get("modules", []) if isinstance(module, dict)
        for entry in module.get("priorEvidence", []) if isinstance(entry, dict)
        if entry.get("artifactPath", "").rstrip("/") == campaign_path.rstrip("/") and
        entry.get("evidenceSha256") == observed
    ]
    if len(authoritative) != 1:
        blockers.append("campaign does not have exactly one authoritative readiness binding")
    module, ledger = authoritative[0] if len(authoritative) == 1 else (None, None)
    module_name = module.get("module") if isinstance(module, dict) else None
    ledger_sha256 = ledger.get("evidenceSha256") if isinstance(ledger, dict) else None
    if ledger is None:
        blockers.append("campaign has no matching readiness evidence entry")
    if curated.get("module") != module_name:
        blockers.append("inventory module differs from authoritative readiness binding")
    if isinstance(ledger, dict) and curated.get("evidenceId") != ledger.get("id"):
        blockers.append("inventory evidence ID differs from readiness ledger")
    if evidence.get("sut") != module_name:
        blockers.append("inventory SUT differs from authoritative readiness module")
    if observed != ledger_sha256:
        blockers.append("current campaign digest differs from readiness ledger")
    if isinstance(ledger, dict) and curated.get("scientificQualification") != ledger.get(
            "curatedScientificQualification"):
        blockers.append("inventory qualification differs from readiness ledger")
    if isinstance(module, dict) and curated.get("moduleCeiling") != module.get(
            "highestScientificQualification"):
        blockers.append("inventory module ceiling differs from readiness ledger")
    return {
        "passed": not blockers,
        "blockers": blockers,
        "observedEvidenceSha256": observed,
        "inventoryEvidenceSha256": inventory_sha256,
        "readinessEvidenceSha256": ledger_sha256,
        "boundModule": module_name,
    }


def extract_rows(repo_root: Path, inventory: dict[str, Any], readiness: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for evidence in inventory.get("campaigns", []):
        campaign_path = str(evidence["path"])
        campaign = repo_root / campaign_path
        receipt_paths = sorted(campaign.glob("*/receipt.json")) if campaign.is_dir() else []
        configuration = _configuration(campaign) if campaign.is_dir() else {}
        curated = evidence.get("curatedReadiness", {})
        curation_binding = _curation_binding(campaign_path, campaign, evidence, readiness)
        qualification = (str(curated.get("scientificQualification", "unlisted-evidence"))
                         if curation_binding["passed"] else "unlisted-evidence")
        module = curation_binding.get("boundModule")
        family = _family(module, readiness)
        campaign_digest = _campaign_metadata_digest(campaign, receipt_paths) if receipt_paths else None
        receipt_documents = [(path, _read(path)) for path in receipt_paths]
        campaign_goal = _goal(configuration, {})
        if campaign_goal == "unknown":
            campaign_goal = next((goal for _, receipt in receipt_documents
                                  if (goal := _goal(configuration, receipt)) != "unknown"), "unknown")
        for receipt_path, receipt in receipt_documents:
            run_id = str(receipt.get("runId") or receipt_path.parent.name)
            block = _block(run_id)
            intervention = receipt.get("intervention", {}) if isinstance(receipt.get("intervention"), dict) else {}
            fault = str(intervention.get("scenario") or configuration.get("fault") or "none")
            load = _load_signature(configuration, receipt)
            goal = campaign_goal
            objectives = receipt_objectives(receipt)
            split_group = _stable_id(campaign_path, block)
            independence_group = _stable_id(campaign_path, goal, fault, load)
            rows.append({
                "schemaVersion": 1,
                "campaign": campaign_path,
                "runId": run_id,
                "block": block,
                "posture": str(receipt.get("posture", "unknown")),
                "sut": str(module if curation_binding["passed"] else
                           evidence.get("sut") or receipt.get("sut", "unknown")),
                "sutAttributionBound": curation_binding["passed"],
                "family": family,
                "goal": goal,
                "fault": fault,
                "load": load,
                "objectives": objectives["values"],
                "objectiveMissing": {key: value is None for key, value in objectives["values"].items()},
                "observedObjectives": objectives["observed"],
                "missingObjectives": objectives["missing"],
                "feasibility": objectives["feasibility"],
                "provenance": {
                    "receiptSha256": _digest_file(receipt_path),
                    "campaignMetadataSha256": campaign_digest,
                    "sourceHashes": _source_hashes(receipt),
                    "curationBinding": curation_binding,
                },
                "curatedQualification": qualification,
                "curatedEvidenceId": curated.get("evidenceId"),
                "splitGroupId": split_group,
                "independenceGroupId": independence_group,
            })
    return rows


def _criterion(observed: int | float | bool, required: int | float | bool) -> dict[str, Any]:
    passed = observed is True if required is True else bool(observed >= required)  # type: ignore[operator]
    return {"observed": observed, "required": required, "pass": passed}


def sufficiency(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in rows if row["curatedQualification"] in ELIGIBLE_QUALIFICATIONS]
    groups = {row["independenceGroupId"] for row in eligible}
    campaigns = {row["campaign"] for row in eligible}
    split_groups = {row["splitGroupId"] for row in eligible}
    three_objectives = sum(len(row["observedObjectives"]) >= 3 for row in eligible)
    visibility_target_rows = sum(row["objectives"].get("required_sensor_retention") is not None for row in eligible)
    visibility_coverage = visibility_target_rows / len(eligible) if eligible else 0.0
    known_goal_coverage = (sum(row.get("goal", "unknown") != "unknown" for row in eligible) / len(eligible)
                           if eligible else 0.0)
    # Context identifiers are not accepted as learned, generalizable explanatory
    # features. A later topology/config extractor must explicitly populate them.
    generalizable_features = 0
    xgb_criteria = {
        "independentCampaignFaultLoadGroups": _criterion(len(groups), 20),
        "independentCampaigns": _criterion(len(campaigns), 5),
        "eligibleRows": _criterion(len(eligible), 100),
        "generalizableExplanatoryFeatures": _criterion(generalizable_features, 5),
        "requiredSensorRetentionCoverage": _criterion(visibility_coverage, 0.8),
        "knownGoalCoverage": _criterion(known_goal_coverage, 1.0),
    }
    gmm_criteria = {
        "independentCampaignFaultLoadGroups": _criterion(len(groups), 10),
        "independentSplitGroups": _criterion(len(split_groups), 30),
        "eligibleRows": _criterion(len(eligible), 60),
        "rowsWithAtLeastThreeObjectives": _criterion(three_objectives, 50),
        "frozenMissingDataStrategy": _criterion(False, True),
        "knownGoalCoverage": _criterion(known_goal_coverage, 1.0),
    }
    return {
        "eligibilityPolicy": "Only curated candidate-evidence or canonical-evidence rows count; postures sharing a campaign/block must remain in one split.",
        "eligibleRows": len(eligible),
        "excludedRows": len(rows) - len(eligible),
        "models": {
            "xgboost": {
                "ready": all(item["pass"] for item in xgb_criteria.values()),
                "criteria": xgb_criteria,
                "blockers": [name for name, item in xgb_criteria.items() if not item["pass"]],
                "intendedRole": "supervised preprocessing/placement steering after targets and topology/config features are frozen",
            },
            "gaussianMixture": {
                "ready": all(item["pass"] for item in gmm_criteria.values()),
                "criteria": gmm_criteria,
                "blockers": [name for name, item in gmm_criteria.items() if not item["pass"]],
                "intendedRole": "exploratory objective-regime clustering, not a selector or causal estimator",
            },
        },
    }


def build_report(repo_root: Path, inventory_path: Path, readiness_path: Path) -> dict[str, Any]:
    inventory, readiness = _read(inventory_path), _read(readiness_path)
    rows = extract_rows(repo_root, inventory, readiness)
    return {
        "schemaVersion": 1,
        "asOf": inventory.get("asOf"),
        "datasetSchema": "research/ml-run-dataset.schema.json",
        "rawTelemetryIncluded": False,
        "objectiveDirections": OBJECTIVE_DIRECTIONS,
        "summary": {
            "rows": len(rows),
            "campaigns": len({row["campaign"] for row in rows}),
            "splitGroups": len({row["splitGroupId"] for row in rows}),
            "independenceGroups": len({row["independenceGroupId"] for row in rows}),
            "qualificationCounts": dict(sorted(Counter(row["curatedQualification"] for row in rows).items())),
            "unknownGoalRows": sum(row["goal"] == "unknown" for row in rows),
        },
        "dataSufficiency": sufficiency(rows),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--inventory", type=Path, default=ROOT / "research/evidence-inventory.json")
    parser.add_argument("--readiness", type=Path, default=ROOT / "research/five-module-readiness.json")
    args = parser.parse_args()
    print(json.dumps(build_report(args.repo_root, args.inventory, args.readiness), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
