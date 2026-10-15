#!/usr/bin/env python3
"""Independent terminal replay for TeaStore candidate cells and campaigns.

The producer may write evidence; this validator only reads it.  A cell passes
only when its closed content manifest, candidate report, identity, and cleanup
receipt all replay.  A campaign passes only when the frozen manifest names
exactly 27 distinct roots, every root passes, and no undeclared run root exists.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, NoReturn


ROOT = Path(__file__).resolve().parents[3]
CELL_KIND = "teastore-candidate-terminal-validation-v1"
CAMPAIGN_KIND = "teastore-candidate-campaign-terminal-validation-v1"
CAMPAIGN_CONTRACT = "teastore-candidate-pilot-evidence-v1"


def _study_epoch_module():
    """The tree's study-epoch selector (execution/study_epoch.py), loaded by path (python3 -I)."""
    path = Path(__file__).resolve().parents[1] / "execution/study_epoch.py"
    name = "teastore_study_epoch_" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:  # pragma: no cover - install defect
            raise ValueError(f"cannot load the study-epoch selector: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


# With no selector: the frozen epoch, 27 cells (c1724b1 literals).
EPOCH = _study_epoch_module().active(ROOT)
STUDY_EPOCH = EPOCH["studyEpoch"]
RUN_COUNT = EPOCH["runCount"]
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

COMMON_ARTIFACTS = {
    "receipt.json", "journey-ledger.plan.json", "journey-ledger.jsonl",
    "auth.log", "persistence.log", "app-witness.jsonl",
    "app-witness-extraction.json", "service-log-capture.json",
    "native-token-correlation.json", "native-token-correlation-extraction.json",
    "kieker-amqp.spool", "traces.json", "capture-terminal.json",
    "posture-proof.json", "queue-proof.json", "runtime-images.json",
    "system-samples.json",
    "candidate-validation.json", "cell-cleanup.json", "content-manifest.json",
}
if EPOCH["sweep"]:
    COMMON_ARTIFACTS = COMMON_ARTIFACTS | {"application.log"}


class TerminalError(ValueError):
    """Candidate evidence cannot be replayed at the terminal boundary."""


def _reject_constant(value: str) -> NoReturn:
    raise TerminalError(f"non-finite JSON value is forbidden: {value}")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TerminalError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, allow_nan=False, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TerminalError(f"value is not canonical JSON: {exc}") from exc


def _same(left: Any, right: Any) -> bool:
    try:
        return _canonical(left) == _canonical(right)
    except TerminalError:
        return False


def _safe_relative(value: Any, where: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise TerminalError(f"{where} is not a safe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise TerminalError(f"{where} is not normalized")
    return path


def _regular_bytes(path: Path, where: str) -> bytes:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise TerminalError(f"{where} is not a singly-linked regular file")
        payload = path.read_bytes()
        after = path.lstat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ) or len(payload) != before.st_size:
            raise TerminalError(f"{where} changed while being read")
        return payload
    except TerminalError:
        raise
    except OSError as exc:
        raise TerminalError(f"cannot read {where}: {exc}") from exc


def _json_bytes(payload: bytes, where: str) -> Any:
    try:
        return json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_no_duplicates, parse_constant=_reject_constant,
        )
    except TerminalError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TerminalError(f"invalid JSON in {where}: {exc}") from exc


def _json_file(path: Path, where: str) -> Any:
    return _json_bytes(_regular_bytes(path, where), where)


def _candidate_validator():
    path = Path(__file__).with_name("candidate_pilot.py")
    spec = importlib.util.spec_from_file_location(
        "teastore_candidate_terminal_evidence_validator", path,
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise TerminalError(f"cannot load candidate validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest_snapshot(root: Path, required: set[str]) -> tuple[str, dict[str, str]]:
    try:
        metadata = root.lstat()
    except OSError as exc:
        raise TerminalError(f"cannot inspect candidate cell root: {exc}") from exc
    if root.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise TerminalError("candidate cell root is not a real directory")
    observed: dict[str, Path] = {}
    for path in root.iterdir():
        if path.name.startswith("."):
            raise TerminalError(f"candidate cell contains hidden entry: {path.name}")
        observed[path.name] = path
    if set(observed) != required:
        raise TerminalError(
            "candidate cell membership differs: "
            f"missing={sorted(required - set(observed))}, "
            f"extra={sorted(set(observed) - required)}"
        )
    manifest_payload = _regular_bytes(
        observed["content-manifest.json"], "candidate content manifest",
    )
    manifest = _json_bytes(manifest_payload, "candidate content manifest")
    if not isinstance(manifest, dict) or set(manifest) != {
        "schemaVersion", "algorithm", "files",
    } or type(manifest.get("schemaVersion")) is not int or (
        manifest.get("schemaVersion") != 1 or manifest.get("algorithm") != "sha256"
    ):
        raise TerminalError("candidate content manifest schema differs")
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise TerminalError("candidate content manifest files is not a list")
    declared: dict[str, dict[str, Any]] = {}
    ordered: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}:
            raise TerminalError(f"candidate manifest row {index} fields differ")
        relative = _safe_relative(row.get("path"), f"candidate manifest row {index}")
        name = relative.as_posix()
        if len(relative.parts) != 1 or name == "content-manifest.json" or name in declared:
            raise TerminalError(f"candidate manifest row {index} path differs")
        if type(row.get("bytes")) is not int or row["bytes"] < 0 or not isinstance(
            row.get("sha256"), str
        ) or SHA256_RE.fullmatch(row["sha256"]) is None:
            raise TerminalError(f"candidate manifest row {index} size/digest differs")
        declared[name] = row
        ordered.append(name)
    expected = required - {"content-manifest.json"}
    if set(declared) != expected or ordered != sorted(ordered):
        raise TerminalError("candidate content manifest membership/order differs")
    digests: dict[str, str] = {}
    for name in sorted(expected):
        payload = _regular_bytes(observed[name], f"candidate artifact {name}")
        digest = hashlib.sha256(payload).hexdigest()
        if declared[name] != {"path": name, "bytes": len(payload), "sha256": digest}:
            raise TerminalError(f"candidate artifact digest/size differs: {name}")
        digests[name] = digest
    return hashlib.sha256(manifest_payload).hexdigest(), digests


def _required_for(run_key: Mapping[str, Any]) -> set[str]:
    regime = run_key.get("regime")
    required = set(COMMON_ARTIFACTS)
    if regime == "no-fault-cost":
        required.add("resources.json")
    elif regime in EPOCH["regimes"] and EPOCH["scenarios"].get(regime) is not None:
        required.add("intervention.json")
    else:
        raise TerminalError("candidate run regime is invalid")
    return required


def validate_candidate_cell(
    root: Path,
    *,
    expected_run_key: Mapping[str, Any],
    expected_manifest_sha256: str,
    expected_run_id: str | None = None,
) -> dict[str, Any]:
    """Replay one closed cell without writing a new blessing.

    ``expected_run_id`` (traffic sweep: four cells share one run key and differ by rate) binds the
    receipt's run ID to the campaign row as well.
    """

    blockers: list[str] = []
    run_key = dict(expected_run_key)
    manifest_sha256: str | None = None
    try:
        if not isinstance(expected_manifest_sha256, str) or SHA256_RE.fullmatch(
            expected_manifest_sha256
        ) is None:
            raise TerminalError("expected manifest SHA-256 is invalid")
        manifest_sha256, _ = _manifest_snapshot(Path(root), _required_for(run_key))
        if manifest_sha256 != expected_manifest_sha256:
            raise TerminalError("candidate content manifest differs from external anchor")
        operational = _candidate_validator().validate_operational_proofs(
            Path(root), posture=run_key.get("posture"),
        )
        if (
            operational.get("zeroConsumerPurge") is not True
            or operational.get("emptySingleCollectorBarrier") is not True
            or operational.get("terminalDrain") is not True
        ):
            raise TerminalError("candidate operational proof replay differs")
        retained = _json_file(
            Path(root) / "candidate-validation.json", "candidate validation report",
        )
        replayed = _candidate_validator().validate_run(
            Path(root), expected=dict(run_key),
        )
        if retained != replayed or replayed.get("verdict") != "pass" or not _same(
            replayed.get("runKey"), run_key,
        ):
            raise TerminalError("candidate validation report does not replay to pass")
        receipt = _json_file(Path(root) / "receipt.json", "candidate receipt")
        receipt_run = receipt.get("run") if isinstance(receipt, dict) else None
        receipt_run_id = receipt_run.get("runId") if isinstance(receipt_run, dict) else None
        if not isinstance(receipt_run_id, str) or (
            expected_run_id is not None and receipt_run_id != expected_run_id
        ):
            raise TerminalError("candidate receipt run identity differs")
        expected_run_id = receipt_run_id
        cleanup = _json_file(Path(root) / "cell-cleanup.json", "cell cleanup proof")
        expected_cleanup = {
            "schemaVersion": 1,
            "kind": "teastore-candidate-cell-cleanup-v1",
            "runId": expected_run_id,
            "outerLeaseHeld": True,
            "deadlineControllerSettled": True,
            "ownedResourcesClean": True,
            "safeToContinue": True,
        }
        if not isinstance(cleanup, dict) or set(cleanup) != {
            "schemaVersion", "kind", "runId", "outerLeaseHeld",
            "deadlineControllerSettled", "ownedResourcesClean", "safeToContinue",
        } or cleanup != expected_cleanup:
            raise TerminalError("candidate cell cleanup proof differs")
        # A second manifest pass catches mutation during the semantic replay.
        second_sha, _ = _manifest_snapshot(Path(root), _required_for(run_key))
        if second_sha != manifest_sha256:
            raise TerminalError("candidate artifacts changed across terminal replay")
    except Exception as exc:  # noqa: BLE001 - terminal validation must return a verdict
        blockers.append(f"{type(exc).__name__}: {exc}")
    return {
        "schemaVersion": 1,
        "kind": CELL_KIND,
        "verdict": "pass" if not blockers else "blocked",
        "runKey": run_key,
        "manifestSha256": manifest_sha256,
        "blockers": blockers,
    }


def _real_directory(path: Path, where: str) -> None:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise TerminalError(f"{where} is not a real directory")


def validate_candidate_campaign(
    root: Path,
    *,
    expected_campaign_sha256: str,
    manifest_anchors: Mapping[str, str],
) -> dict[str, Any]:
    """Replay the exact 27-cell population and reject any undeclared run root."""

    root = Path(root)
    blockers: list[str] = []
    run_reports: list[dict[str, Any]] = []
    campaign_sha256: str | None = None
    try:
        _real_directory(root, "candidate campaign root")
        campaign_payload = _regular_bytes(root / "campaign.json", "campaign manifest")
        campaign_sha256 = hashlib.sha256(campaign_payload).hexdigest()
        if expected_campaign_sha256 != campaign_sha256:
            raise TerminalError("campaign manifest differs from external anchor")
        campaign = _json_bytes(campaign_payload, "campaign manifest")
        if not isinstance(campaign, dict) or campaign.get("contract") != CAMPAIGN_CONTRACT or (
            campaign.get("studyEpoch") != STUDY_EPOCH
            or type(campaign.get("runCount")) is not int
            or campaign.get("runCount") != RUN_COUNT
            or campaign.get("canonical") is not False
            or campaign.get("promotionAuthorized") is not False
        ):
            raise TerminalError("campaign identity or evidence ceiling differs")
        runs = campaign.get("runs")
        if not isinstance(runs, list) or len(runs) != RUN_COUNT:
            raise TerminalError(f"campaign does not declare exactly {RUN_COUNT} runs")
        run_ids = [row.get("runId") if isinstance(row, dict) else None for row in runs]
        paths = [row.get("path") if isinstance(row, dict) else None for row in runs]
        if (len(set(run_ids)) != RUN_COUNT or None in run_ids or len(set(paths)) != RUN_COUNT
                or None in paths):
            raise TerminalError("campaign run identities or paths repeat")
        if set(manifest_anchors) != set(run_ids) or any(
            not isinstance(value, str) or SHA256_RE.fullmatch(value) is None
            for value in manifest_anchors.values()
        ):
            raise TerminalError(f"external cell-manifest anchors differ from {RUN_COUNT} runs")
        declared_paths: set[str] = set()
        for row in runs:
            path = _safe_relative(row["path"], "campaign run path")
            if len(path.parts) != 3 or path.parts[0] != "runs" or path.parts[1] != row.get(
                "regime"
            ):
                raise TerminalError("campaign run path is not regime-separated")
            declared_paths.add(path.as_posix())
            current = root
            for part in path.parts:
                current = current / part
                _real_directory(current, f"campaign run path {path}")
            expected_key = {
                key: row[key] for key in (
                    "studyEpoch", "regime", "block", "posture", "attempt"
                )
            }
            run_reports.append(validate_candidate_cell(
                current, expected_run_key=expected_key,
                expected_manifest_sha256=manifest_anchors[row["runId"]],
                **({"expected_run_id": row["runId"]} if EPOCH["sweep"] else {}),
            ))
        observed_paths: set[str] = set()
        runs_root = root / "runs"
        _real_directory(runs_root, "campaign runs root")
        for regime in runs_root.iterdir():
            _real_directory(regime, "campaign regime root")
            for cell in regime.iterdir():
                _real_directory(cell, "campaign cell root")
                observed_paths.add(cell.relative_to(root).as_posix())
        if observed_paths != declared_paths:
            raise TerminalError(
                "campaign run-root membership differs: "
                f"missing={sorted(declared_paths - observed_paths)}, "
                f"extra={sorted(observed_paths - declared_paths)}"
            )
        if any(report["verdict"] != "pass" for report in run_reports):
            raise TerminalError("at least one candidate cell failed terminal replay")
        scientific = _candidate_validator().validate_campaign(root)
        if scientific.get("verdict") != "pass" or len(scientific.get("runReports", [])) != RUN_COUNT:
            raise TerminalError(f"scientific campaign replay did not pass exactly {RUN_COUNT} cells")
    except Exception as exc:  # noqa: BLE001 - return a closed terminal verdict
        blockers.append(f"{type(exc).__name__}: {exc}")
    return {
        "schemaVersion": 1,
        "kind": CAMPAIGN_KIND,
        "verdict": "pass" if not blockers else "blocked",
        "campaignSha256": campaign_sha256,
        "runCount": len(run_reports),
        "runReports": run_reports,
        "blockers": blockers,
        "promotionAuthorized": False,
    }


__all__ = [
    "CAMPAIGN_KIND", "CELL_KIND", "TerminalError",
    "validate_candidate_campaign", "validate_candidate_cell",
]
