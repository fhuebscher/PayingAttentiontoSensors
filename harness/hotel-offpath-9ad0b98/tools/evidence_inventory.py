#!/usr/bin/env python3
"""Inventory local campaign evidence without modifying or promoting it.

The generic validator establishes filesystem structure only.  Scientific
qualification always comes from the separately reviewed readiness ledger.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from obsplacement.evidence import build_manifest, validate_campaign  # noqa: E402
from obsplacement.paired_analysis import analyze_directory  # noqa: E402


def _load_function(path: Path, function: str) -> Callable[..., dict[str, Any]]:
    spec = importlib.util.spec_from_file_location(f"evidence_inventory_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, function)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _is_non_authoritative_path(path: Path, evidence_root: Path) -> bool:
    """Recognize only explicit quarantine/partial-extraction naming markers."""
    for part in path.relative_to(evidence_root).parts:
        tokens = part.lower().split(".")
        if any(token == "quarantine" or token.startswith("quarantine-") or
               token == "partial-extract" or token.startswith("partial-extract-")
               for token in tokens):
            return True
    return False


def discover_campaign_roots(evidence_root: Path) -> list[Path]:
    """Find campaign roots using manifests, summaries, and receipt layout."""
    if not evidence_root.is_dir():
        return []
    roots = {path.parent for name in ("schedule.json", "summary.json")
             for path in evidence_root.rglob(name)}
    roots.update(path.parent.parent for path in evidence_root.rglob("receipt.json"))
    # A summary in a run directory is not a campaign marker when its parent has a
    # schedule or multiple receipt children.
    candidates = []
    for root in sorted(roots):
        if _is_non_authoritative_path(root, evidence_root):
            continue
        if root.name.startswith("b") and (root.parent / "schedule.json").is_file():
            continue
        candidates.append(root)
    return candidates


def _detect_sut(campaign: Path) -> str:
    schedule_path = campaign / "schedule.json"
    if schedule_path.is_file():
        try:
            schedule = _read_json(schedule_path)
            configured = schedule.get("configuration", {})
            value = configured.get("sut") or schedule.get("sut")
            if value:
                channel = str(configured.get("channel") or schedule.get("channel") or "").lower()
                if value == "online-boutique" and "lgtm" in channel:
                    return "online-boutique-lgtm"
                return str(value)
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    for receipt_path in sorted(campaign.glob("*/receipt.json")):
        try:
            value = _read_json(receipt_path).get("sut")
            if value:
                return str(value)
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
    lowered = campaign.as_posix().lower()
    if "teastore" in lowered or "performance-" in lowered:
        return "teastore"
    if "otel" in lowered:
        return "otel-demo"
    if "hotel" in lowered:
        return "hotel-reservation"
    return "unknown"


def _module_for_sut(sut: str, readiness: dict[str, Any]) -> dict[str, Any] | None:
    aliases = {
        "teastore": "teastore",
        "otel-demo": "otel-demo",
        "hotel-reservation": "hotel-reservation",
        "online-boutique": "online-boutique",
        "online-boutique-lgtm": "online-boutique-lgtm",
    }
    expected = aliases.get(sut)
    for module in readiness.get("modules", []):
        if module.get("module") == expected:
            return module
    return None


def _curated(campaign_path: str, sut: str, evidence_sha256: str,
             readiness: dict[str, Any]) -> dict[str, Any]:
    module = _module_for_sut(sut, readiness)
    if module is None:
        return {
            "ledgerEntryMatched": False,
            "module": None,
            "moduleCeiling": "unreviewed",
            "evidenceDigestMatched": False,
            "scientificQualification": "unlisted-evidence",
            "claimBoundary": "No module or prior-evidence ledger entry matches this campaign; do not cite it.",
            "promotionApplied": False,
        }
    for entry in module.get("priorEvidence", []):
        if entry.get("artifactPath", "").rstrip("/") == campaign_path.rstrip("/"):
            reviewed_sha256 = entry.get("evidenceSha256")
            if reviewed_sha256 != evidence_sha256:
                return {
                    "ledgerEntryMatched": False,
                    "readinessPathMatched": True,
                    "evidenceDigestMatched": False,
                    "module": module["module"],
                    "moduleCeiling": module["highestScientificQualification"],
                    "evidenceId": entry.get("id"),
                    "reviewedEvidenceSha256": reviewed_sha256,
                    "observedEvidenceSha256": evidence_sha256,
                    "scientificQualification": "unlisted-evidence",
                    "claimBoundary": (
                        "Campaign path matches a reviewed entry but its current bytes differ from "
                        "the reviewed evidence digest; quarantine this copy and do not cite it."
                    ),
                    "curationBlockers": ["current evidence digest differs from readiness ledger"],
                    "promotionApplied": False,
                }
            return {
                "ledgerEntryMatched": True,
                "readinessPathMatched": True,
                "evidenceDigestMatched": True,
                "module": module["module"],
                "moduleCeiling": module["highestScientificQualification"],
                "evidenceId": entry.get("id"),
                "reviewedEvidenceSha256": reviewed_sha256,
                "observedEvidenceSha256": evidence_sha256,
                "scientificQualification": entry["curatedScientificQualification"],
                "claimBoundary": entry["claimBoundary"],
                "promotionApplied": False,
            }
    return {
        "ledgerEntryMatched": False,
        "readinessPathMatched": False,
        "evidenceDigestMatched": False,
        "module": module["module"],
        "moduleCeiling": module["highestScientificQualification"],
        "scientificQualification": "unlisted-evidence",
        "claimBoundary": "Campaign is not individually reviewed in the readiness ledger; module status cannot promote it.",
        "promotionApplied": False,
    }


def _artifact_counts(campaign: Path) -> dict[str, Any]:
    receipts = list(campaign.glob("*/receipt.json"))
    return {
        "receipts": len(receipts),
        "schedulePresent": (campaign / "schedule.json").is_file(),
        "summaryPresent": (campaign / "summary.json").is_file(),
        "pairedAnalysisPresent": any((campaign / name).is_file() for name in
                                     ("paired-analysis.json", "paired-analysis-v2.json")),
    }


def _teastore_checks(campaign: Path) -> dict[str, Any]:
    receipt_validate = _load_function(
        ROOT / "modules/teastore/validation/performance_receipt.py", "validate")
    native_validate = _load_function(
        ROOT / "modules/teastore/validation/native_kieker.py", "validate")
    bundle_validate = _load_function(
        ROOT / "modules/teastore/execution/srv5_harness.py", "validate_bundle")

    receipt_paths = sorted(campaign.glob("*/receipt.json"))
    denominator_failures: list[dict[str, Any]] = []
    for path in receipt_paths:
        result = receipt_validate(_read_json(path))
        if result["verdict"] != "pass":
            denominator_failures.append({"runId": path.parent.name, "blockers": result["blockers"]})
    denominators = {
        "validator": "modules/teastore/validation/performance_receipt.py",
        "status": "pass" if receipt_paths and not denominator_failures else "blocked",
        "checkedReceipts": len(receipt_paths),
        "failures": denominator_failures,
    }

    try:
        schedule = _read_json(campaign / "schedule.json")
        runs = schedule.get("runs", [])
        postures = tuple(dict.fromkeys(str(item["posture"]) for item in runs))
        blocks = len({int(item["block"]) for item in runs})
        bundle = bundle_validate(campaign, blocks=blocks, postures_expected=postures)
        immutable_schedule = {
            "validator": "modules/teastore/execution/srv5_harness.py:validate_bundle",
            "status": bundle["verdict"],
            "receipts": bundle["receipts"],
            "postures": bundle["postures"],
            "failureCount": len(bundle["failures"]),
        }
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        immutable_schedule = {"status": "incompatible", "reason": str(exc)}

    try:
        paired = analyze_directory(campaign)
        warnings = list(paired.get("diagnostics", {}).get("warnings", []))
        paired_check = {
            "analyzer": "obsplacement.paired_analysis.analyze_directory",
            "status": paired["verdict"],
            "blocks": paired["blocks"],
            "failureCount": len(paired.get("failures", [])),
            "executionOrderCount": len(paired.get("diagnostics", {}).get("executionOrder", [])),
            "driftWarningCount": sum("drift" in warning for warning in warnings),
            "outlierWarningCount": sum("outlier" in warning for warning in warnings),
            "warnings": warnings,
        }
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        paired_check = {"status": "incompatible", "reason": str(exc)}

    trace_paths = sorted(campaign.glob("*/traces.json"))
    compatible = 0
    checked_events = 0
    unique_message_hashes = 0
    duplicate_message_events = 0
    runs_with_duplicate_records: list[str] = []
    failures: list[dict[str, Any]] = []
    empty_expected = 0
    for path in trace_paths:
        events = _read_json(path)
        if events == []:
            empty_expected += 1
            continue
        if not isinstance(events, list):
            failures.append({"runId": path.parent.name, "blockers": ["trace artifact is not a list"]})
            continue
        compatible += 1
        result = native_validate(events)
        checked_events += int(result.get("counts", {}).get("events", 0))
        usable_events = [event for event in events
                         if isinstance(event, dict) and event.get("message_sha1")]
        hashes = [str(event["message_sha1"]) for event in usable_events]
        unique_message_hashes += len(set(hashes))
        # One RabbitMQ message normally expands into several Kieker events, so
        # hash repetition alone is not replay.  Repeated record identities under
        # the same packet hash are the conservative duplicate indicator.
        identities = [
            (event.get("message_sha1"), event.get("trace_id"), event.get("eoi"),
             event.get("ess"), event.get("signature_sha1"), event.get("tin"), event.get("tout"))
            for event in usable_events
        ]
        duplicates = len(identities) - len(set(identities))
        duplicate_message_events += duplicates
        if duplicates:
            runs_with_duplicate_records.append(path.parent.name)
        if result["verdict"] != "pass":
            failures.append({"runId": path.parent.name, "blockers": result["blockers"]})
    if not trace_paths:
        replay_status = "missing-input"
    elif not compatible:
        replay_status = "not-applicable" if empty_expected else "incompatible"
    else:
        replay_status = "pass" if not failures else "blocked"
    replay = {
        "validator": "modules/teastore/validation/native_kieker.py",
        "status": replay_status,
        "compatibleArtifacts": compatible,
        "expectedEmptyArtifacts": empty_expected,
        "checkedEvents": checked_events,
        "uniqueMessageHashes": unique_message_hashes,
        "duplicateMessageEvents": duplicate_message_events,
        "runsWithDuplicateMessageRecords": runs_with_duplicate_records,
        "failures": failures,
        "requiredFields": ["message_sha1", "signature_sha1", "trace_id", "eoi", "ess"],
    }
    if not trace_paths:
        replay["missingCheck"] = "No native traces.json input; RabbitMQ replay/duplicate risk is unresolved."

    return {
        "denominatorsAndProvenance": denominators,
        "immutableSchedule": immutable_schedule,
        "orderDriftOutliers": paired_check,
        "rabbitMqReplayHashes": replay,
    }


def _caveats(sut: str, campaign_path: str, curated: dict[str, Any], generic: dict[str, Any]) -> list[str]:
    result = [curated["claimBoundary"]]
    if sut == "otel-demo":
        result.append("Collector exports establish emission, not removal of all request-path instrumentation work.")
        result.append("Fault-bearing lifecycle receipts are controls, not an overhead estimate.")
    elif sut == "hotel-reservation":
        result.append("sample-zero is sampling suppression, not source-work-off.")
        result.append("Missing immutable schedule and paired repetitions keep this evidence noncanonical.")
    if not generic.get("valid"):
        result.append("Generic structural validation quarantined this campaign.")
    return list(dict.fromkeys(result))


def build_inventory(evidence_root: Path, readiness_path: Path, *, repo_root: Path = ROOT) -> dict[str, Any]:
    readiness = _read_json(readiness_path)
    campaigns = []
    for campaign in discover_campaign_roots(evidence_root):
        path = _relative(campaign, repo_root)
        sut = _detect_sut(campaign)
        generic = validate_campaign(campaign)
        manifest = build_manifest(campaign)
        curated = _curated(path, sut, manifest["evidenceSha256"], readiness)
        entry: dict[str, Any] = {
            "path": path,
            "sut": sut,
            "evidenceManifestSha256": manifest["evidenceSha256"],
            "artifacts": _artifact_counts(campaign),
            "genericStructuralValidation": generic,
            "curatedReadiness": curated,
            "caveats": _caveats(sut, path, curated, generic),
        }
        if sut == "teastore":
            entry["specializedChecks"] = _teastore_checks(campaign)
        campaigns.append(entry)
    qualifications = Counter(item["curatedReadiness"]["scientificQualification"] for item in campaigns)
    generic = Counter(item["genericStructuralValidation"]["maturity"] for item in campaigns)
    return {
        "schemaVersion": 1,
        "asOf": readiness.get("asOf"),
        "evidenceRoot": _relative(evidence_root, repo_root),
        "evidenceRootPresent": evidence_root.is_dir(),
        "rawTelemetryIncluded": False,
        "policy": "Generic structural validation never promotes curated scientific qualification.",
        "summary": {
            "campaigns": len(campaigns),
            "genericStructuralMaturity": dict(sorted(generic.items())),
            "curatedScientificQualification": dict(sorted(qualifications.items())),
        },
        "campaigns": campaigns,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=ROOT / ".local/evidence")
    parser.add_argument("--readiness", type=Path, default=ROOT / "research/five-module-readiness.json")
    args = parser.parse_args()
    print(json.dumps(build_inventory(args.evidence_root, args.readiness), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
