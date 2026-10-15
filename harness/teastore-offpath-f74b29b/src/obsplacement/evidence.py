"""Content-address and validate filesystem-backed experiment campaigns."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

MANIFEST_NAME = "evidence-manifest.json"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(campaign: Path) -> dict[str, Any]:
    campaign = campaign.resolve()
    if not campaign.is_dir():
        raise FileNotFoundError(f"campaign directory does not exist: {campaign}")
    files = []
    for path in sorted(campaign.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"evidence bundle may not contain symlinks: {path}")
        # Only the root snapshot is self-referential. A nested manifest is an
        # ordinary campaign artifact and must remain in the content hash.
        if path.is_file() and path != campaign / MANIFEST_NAME:
            files.append({
                "path": path.relative_to(campaign).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            })
    payload = json.dumps(files, separators=(",", ":"), sort_keys=True).encode()
    return {
        "schemaVersion": 1,
        "algorithm": "sha256",
        "fileCount": len(files),
        "totalBytes": sum(item["bytes"] for item in files),
        "files": files,
        "evidenceSha256": hashlib.sha256(payload).hexdigest(),
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_run_ids(schedule: dict[str, Any]) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    if not isinstance(schedule, dict):
        return [], ["schedule.json must contain an object"]
    runs = schedule.get("runs")
    if not isinstance(runs, list) or not runs:
        return [], ["schedule.runs must be a non-empty list"]
    identifiers: list[str] = []
    for index, item in enumerate(runs):
        if (not isinstance(item, dict) or not isinstance(item.get("block"), int) or
                isinstance(item.get("block"), bool) or item.get("block", 0) <= 0 or
                not isinstance(item.get("posture"), str) or not item.get("posture")):
            problems.append(f"schedule.runs[{index}] lacks integer block/string posture")
            continue
        run_id = item.get("runId", f"b{item['block']:02d}-{item['posture']}")
        if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
            problems.append(f"schedule.runs[{index}] has unsafe runId")
            continue
        identifiers.append(run_id)
    if len(identifiers) != len(set(identifiers)):
        problems.append("schedule contains duplicate run identifiers")
    return identifiers, problems


def validate_campaign(campaign: Path) -> dict[str, Any]:
    campaign = campaign.resolve()
    errors: list[str] = []
    blockers: list[str] = []
    schedule_path = campaign / "schedule.json"
    if not schedule_path.is_file():
        return {"schemaVersion": 1, "valid": False, "complete": False,
                "maturity": "quarantine", "errors": ["missing schedule.json"],
                "canonicalityBlockers": [], "expectedRuns": [], "receiptCount": 0}
    try:
        schedule = _read_json(schedule_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {"schemaVersion": 1, "valid": False, "complete": False,
                "maturity": "quarantine", "errors": [f"invalid schedule.json: {exc}"],
                "canonicalityBlockers": [], "expectedRuns": [], "receiptCount": 0}
    expected, schedule_errors = _expected_run_ids(schedule)
    errors.extend(schedule_errors)
    actual_paths = {path.parent.name: path for path in campaign.glob("*/receipt.json")}
    missing = sorted(set(expected) - set(actual_paths))
    unexpected = sorted(set(actual_paths) - set(expected))
    if missing:
        errors.append(f"missing receipts: {missing}")
    if unexpected:
        errors.append(f"unexpected receipts: {unexpected}")
    labels: list[str] = []
    receipts: dict[str, dict[str, Any]] = {}
    for run_id in sorted(set(expected) & set(actual_paths)):
        try:
            receipt = _read_json(actual_paths[run_id])
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid receipt {run_id}: {exc}")
            continue
        if not isinstance(receipt, dict):
            errors.append(f"receipt {run_id} must contain an object")
            continue
        receipts[run_id] = receipt
        missing_fields = sorted({"schemaVersion", "runId", "sut", "posture", "canonicality"} - set(receipt))
        if missing_fields:
            errors.append(f"receipt {run_id} lacks required structural fields: {missing_fields}")
        if receipt.get("schemaVersion") != 1:
            errors.append(f"receipt {run_id} has unsupported schemaVersion")
        if receipt.get("runId") != run_id:
            errors.append(f"receipt {run_id} declares runId={receipt.get('runId')!r}")
        if not isinstance(receipt.get("sut"), str) or not receipt.get("sut"):
            errors.append(f"receipt {run_id} lacks a non-empty sut")
        scheduled = next((item for item in schedule.get("runs", [])
                          if item.get("runId", f"b{item.get('block', 0):02d}-{item.get('posture')}") == run_id), {})
        if scheduled and receipt.get("posture") != scheduled.get("posture"):
            errors.append(f"receipt {run_id} posture differs from schedule")
        canonicality = receipt.get("canonicality")
        if not isinstance(canonicality, dict):
            blockers.append(f"{run_id}: missing canonicality declaration")
            errors.append(f"receipt {run_id} canonicality must be an object")
            continue
        label = canonicality.get("label")
        declared_blockers = canonicality.get("blockers")
        if not isinstance(label, str) or not label:
            errors.append(f"receipt {run_id} canonicality label must be a non-empty string")
            label = "unknown"
        if (not isinstance(declared_blockers, list) or
                any(not isinstance(item, str) or not item for item in declared_blockers)):
            errors.append(f"receipt {run_id} canonicality blockers must be a list of non-empty strings")
            declared_blockers = []
        labels.append(label)
        for blocker in declared_blockers:
            blockers.append(f"{run_id}: {blocker}")
    complete = bool(expected) and not errors and len(actual_paths) == len(expected)
    if complete and len(expected) > 1 and not any(
            (campaign / name).is_file() for name in
            ("paired-analysis.json", "paired-analysis-v2.json", "summary.json")):
        errors.append("complete multi-run campaign lacks paired analysis")
        complete = False
    elif complete and len(expected) > 1:
        analysis_path = next(campaign / name for name in
                             ("paired-analysis.json", "paired-analysis-v2.json", "summary.json")
                             if (campaign / name).is_file())
        try:
            analysis = _read_json(analysis_path)
            if not isinstance(analysis, dict):
                errors.append(f"{analysis_path.name} must contain an object")
                complete = False
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid {analysis_path.name}: {exc}")
            complete = False
    valid = complete and not errors
    if not valid:
        maturity = "quarantine"
    elif blockers or any("noncanonical" in label for label in labels):
        maturity = "noncanonical"
    else:
        maturity = "candidate-evidence"
        if labels and all(label == "canonical-evidence" for label in labels):
            blockers.append("generic structural validation cannot promote canonical evidence")
    return {
        "schemaVersion": 1,
        "valid": valid,
        "complete": complete,
        "maturity": maturity,
        "errors": errors,
        "canonicalityBlockers": blockers,
        "expectedRuns": expected,
        "receiptCount": len(actual_paths),
        "validationScope": "generic-structural-only",
    }
