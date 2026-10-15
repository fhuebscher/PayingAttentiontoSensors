"""Validate the curated five-module readiness and prior-evidence ledger."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .module_audit import audit
from .evidence import build_manifest, validate_campaign


EXPECTED_MODULES = {
    "teastore", "otel-demo", "hotel-reservation", "online-boutique",
    "online-boutique-lgtm",
}
QUALIFICATIONS = ("desk-qualified", "smoke-validation", "candidate-evidence", "canonical-evidence")
LEVELS = ("smoke", "candidate", "canonical")
LEVEL_STATUS = {"absent", "passed"}
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
QUALIFICATION_LEVELS = {
    "desk-qualified": {"smoke": "absent", "candidate": "absent", "canonical": "absent"},
    "smoke-validation": {"smoke": "passed", "candidate": "absent", "canonical": "absent"},
    "candidate-evidence": {"smoke": "passed", "candidate": "passed", "canonical": "absent"},
    "canonical-evidence": {"smoke": "passed", "candidate": "passed", "canonical": "passed"},
}


def _lock_commit(path: Path) -> str | None:
    match = re.search(r"^commit:\s*([0-9a-f]{40})$", path.read_text(), re.MULTILINE)
    return match.group(1) if match else None


def validate_readiness(document: dict[str, Any], root: Path) -> dict[str, Any]:
    errors: list[str] = []
    if document.get("schemaVersion") != 1:
        errors.append("readiness ledger schemaVersion must be 1")
    modules = document.get("modules")
    if not isinstance(modules, list):
        modules = []
        errors.append("modules must be a list")
    names = [row.get("module") for row in modules if isinstance(row, dict)]
    if set(names) != EXPECTED_MODULES or len(names) != len(EXPECTED_MODULES):
        errors.append("readiness ledger must contain each of the five modules exactly once")
    families = {row.get("applicationFamily") for row in modules if isinstance(row, dict)}
    if len(families) != 4:
        errors.append("five modules must remain explicitly mapped to four application families")
    audits = {}
    for row in modules:
        if not isinstance(row, dict):
            continue
        name = row.get("module")
        if name not in EXPECTED_MODULES:
            continue
        qualification = row.get("highestScientificQualification")
        if qualification not in QUALIFICATIONS:
            errors.append(f"{name}: invalid scientific qualification")
        levels = row.get("evidenceLevels", {})
        if set(levels) != set(LEVELS) or any(value not in LEVEL_STATUS for value in levels.values()):
            errors.append(f"{name}: evidence levels must declare smoke/candidate/canonical as passed or absent")
        elif qualification in QUALIFICATION_LEVELS and levels != QUALIFICATION_LEVELS[qualification]:
            errors.append(f"{name}: evidence levels contradict curated qualification")
        commit = row.get("sourceCommit")
        if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
            errors.append(f"{name}: source commit is not an exact Git object")
        lock = root / "modules" / name / "source.lock"
        if not lock.is_file() or _lock_commit(lock) != commit:
            errors.append(f"{name}: readiness source commit differs from source.lock")
        prior_evidence = row.get("priorEvidence", [])
        if not isinstance(prior_evidence, list):
            errors.append(f"{name}: priorEvidence must be a list")
            prior_evidence = []
        for evidence in prior_evidence:
            if not isinstance(evidence, dict):
                errors.append(f"{name}: prior evidence entry must be an object")
                continue
            if not evidence.get("claimBoundary"):
                errors.append(f"{name}: prior evidence lacks a curated claim boundary")
            curated = evidence.get("curatedScientificQualification")
            if curated not in QUALIFICATIONS:
                errors.append(f"{name}: prior evidence lacks valid curated scientific qualification")
            elif qualification in QUALIFICATIONS and QUALIFICATIONS.index(curated) > QUALIFICATIONS.index(qualification):
                errors.append(f"{name}: prior evidence exceeds the module qualification ceiling")
            artifact_value = evidence.get("artifactPath")
            if not isinstance(artifact_value, str) or not artifact_value or Path(artifact_value).is_absolute() or ".." in Path(artifact_value).parts:
                errors.append(f"{name}: prior evidence has an unsafe or missing artifact path")
                continue
            artifact = root / artifact_value
            recorded_digest = evidence.get("evidenceSha256")
            availability = evidence.get("artifactAvailability")
            if not isinstance(recorded_digest, str) or not DIGEST_RE.fullmatch(recorded_digest):
                errors.append(f"{name}: prior evidence lacks an exact evidence digest")
            if availability not in {"tracked", "local-untracked"}:
                errors.append(f"{name}: prior evidence lacks an explicit artifact availability")
            if artifact.is_dir():
                observed_digest = build_manifest(artifact)["evidenceSha256"]
                if recorded_digest != observed_digest:
                    errors.append(f"{name}: prior evidence content differs from its recorded digest")
                observed = validate_campaign(artifact)["maturity"]
                if evidence.get("genericStructuralMaturity") != observed:
                    errors.append(
                        f"{name}: recorded generic maturity differs from available artifact "
                        f"({evidence.get('genericStructuralMaturity')} != {observed})"
                    )
            elif availability != "local-untracked":
                errors.append(f"{name}: required evidence artifact is missing: {artifact_value}")
        report = audit(root / "modules" / name)
        audits[name] = report
        if report["verdict"] != "pass":
            errors.append(f"{name}: extension ledger audit failed")
    ob = {row.get("module"): row for row in modules if isinstance(row, dict)}
    if (ob.get("online-boutique", {}).get("applicationFamily") !=
            ob.get("online-boutique-lgtm", {}).get("applicationFamily")):
        errors.append("Online Boutique channels must not be counted as independent application families")
    scope = document.get("scope", {})
    if scope.get("genericValidationRole") != "structural-only":
        errors.append("generic validation must remain structural-only")
    return {
        "schemaVersion": 1,
        "valid": not errors,
        "errors": errors,
        "moduleCount": len(names),
        "applicationFamilyCount": len(families),
        "extensionAudits": audits,
    }


def load_and_validate(path: Path, root: Path) -> dict[str, Any]:
    return validate_readiness(json.loads(path.read_text()), root)
