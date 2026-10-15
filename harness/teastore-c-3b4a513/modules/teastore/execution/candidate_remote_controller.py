#!/usr/bin/env python3
"""Remote one-shot controller for the exact TeaStore candidate package.

The controller is intentionally synchronous: the SSH transport may disappear,
but the process owns one non-blocking flock for the complete 27-cell sequence.
It never resumes, retries, substitutes, or rerandomizes a started campaign.
Every cell is delegated by fixed argv to the candidate cell producer and the
final fetched tree is replayed by the independent candidate terminal validator.
"""
from __future__ import annotations

import argparse
import base64
import copy
import fcntl
import hashlib
import importlib.util
import json
import math
import os
import pwd
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, NoReturn


ROOT = Path(__file__).resolve().parents[3]
CELL_EXECUTOR = ROOT / "modules/teastore/execution/candidate_cell_executor.py"


def _study_epoch_module():
    """The tree's study-epoch selector (execution/study_epoch.py), loaded by path (python3 -I)."""
    path = Path(__file__).resolve().parent / "study_epoch.py"
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


# With no selector: 27 cells and 29,100 s (the frozen epoch's c1724b1 literals).
EPOCH = _study_epoch_module().active(ROOT)
RUN_COUNT = EPOCH["runCount"]
MINIMUM_FIRST_MUTATION_SECONDS = EPOCH["minimumFirstMutationRemainingSeconds"]
JOURNAL_KIND = "teastore-candidate-runtime-journal-v1"
ABORT_KIND = "teastore-candidate-controller-abort-v1"
COMPOSE_FILES = (
    "modules/teastore/deployment/compose/docker-compose_kieker.yaml",
    "modules/teastore/deployment/compose/docker-compose_rabbitmq.yaml",
    "modules/teastore/deployment/compose/isolation.override.yaml",
)
POSTURE_OVERRIDE = {
    "none": "modules/teastore/postures/none.override.yaml",
    "selected": "modules/teastore/deployment/compose/compiled-selected.override.yaml",
    "full": "modules/teastore/deployment/compose/compiled-full.override.yaml",
}
SAFE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ControllerError(ValueError):
    """The one-shot remote controller failed closed."""


def _load(relative: str, name: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ControllerError(f"cannot load controller dependency: {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _transport_module():
    return _load(
        "modules/teastore/execution/candidate_transport.py",
        "teastore_candidate_remote_transport_contract",
    )


def _terminal_module():
    return _load(
        "modules/teastore/validation/candidate_terminal.py",
        "teastore_candidate_remote_terminal_validator",
    )


def _reject_constant(value: str) -> NoReturn:
    raise ControllerError(f"non-finite JSON value is forbidden: {value}")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ControllerError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, allow_nan=False, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ControllerError(f"value is not canonical JSON: {exc}") from exc


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _json_bytes(payload: bytes, where: str) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_no_duplicates, parse_constant=_reject_constant,
        )
    except ControllerError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ControllerError(f"invalid JSON in {where}: {exc}") from exc
    if not isinstance(value, dict):
        raise ControllerError(f"{where} must contain one object")
    return value


def _regular_bytes(path: Path, where: str) -> bytes:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise ControllerError(f"{where} is not a regular non-symlink file")
        payload = path.read_bytes()
        after = path.lstat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ) or len(payload) != before.st_size:
            raise ControllerError(f"{where} changed while being read")
        return payload
    except ControllerError:
        raise
    except OSError as exc:
        raise ControllerError(f"cannot read {where}: {exc}") from exc


def _timestamp(value: Any, where: str) -> datetime:
    if not isinstance(value, str):
        raise ControllerError(f"{where} is not a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControllerError(f"{where} is not ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ControllerError(f"{where} has no UTC offset")
    return parsed.astimezone(timezone.utc)


def _atomic_file(path: Path, payload: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, raw = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".pending", dir=path.parent,
        )
        temporary = Path(raw)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _safe_run_path(value: Any, campaign: Mapping[str, Any]) -> PurePosixPath:
    row = next(
        (item for item in campaign["runs"] if item["runId"] == value.get("runId")),
        None,
    )
    if row is None:
        raise ControllerError("cell is absent from embedded campaign manifest")
    relative = row.get("path")
    if not isinstance(relative, str):
        raise ControllerError("campaign run path is not a string")
    path = PurePosixPath(relative)
    if path.is_absolute() or path.as_posix() != relative or len(path.parts) != 3 or (
        path.parts[0] != "runs" or path.parts[1] != value["runKey"]["regime"]
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ControllerError("campaign run path is unsafe or regime-mismatched")
    return path


def _journal_record(
    records: list[dict[str, Any]], *, cell: Mapping[str, Any], state: str,
    manifest_sha256: str | None, reason: str | None,
) -> dict[str, Any]:
    row = {
        "schemaVersion": 1,
        "kind": JOURNAL_KIND,
        "sequence": len(records),
        "previousRecordSha256": records[-1]["recordSha256"] if records else "0" * 64,
        "recordSha256": None,
        "runId": cell["runId"],
        "runKey": copy.deepcopy(cell["runKey"]),
        "state": state,
        "manifestSha256": manifest_sha256,
        "reason": reason,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
    }
    row["recordSha256"] = _sha256_value({
        key: value for key, value in row.items() if key != "recordSha256"
    })
    return row


def _append_journal(path: Path, record: Mapping[str, Any]) -> None:
    payload = _canonical(record) + b"\n"
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ControllerError("runtime journal is not a regular file")
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:  # pragma: no cover
                raise ControllerError("runtime journal append made no progress")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _retain_campaign_abort(
    output_root: Path, package: Mapping[str, Any], *, package_sha256: str,
    stage: str, error: BaseException,
) -> dict[str, Any]:
    """Retain one terminal non-result even when failure precedes output setup."""

    allowed_stages = {
        "controller-preflight", "outer-lease-acquisition",
        "campaign-initialization", "cell-execution", "terminal-validation",
    }
    if stage not in allowed_stages or SHA256_RE.fullmatch(package_sha256) is None:
        raise ControllerError("campaign abort identity is malformed")
    output_root = Path(output_root)
    if (
        output_root.parent.resolve() != Path(package["resultsRoot"]).resolve()
        or output_root.name != package["campaignId"]
    ):
        raise ControllerError("campaign abort output identity differs")
    if output_root.exists() or output_root.is_symlink():
        metadata = output_root.lstat()
        if output_root.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise ControllerError("campaign abort output is not a real directory")
    else:
        output_root.mkdir(mode=0o700)
    campaign_path = output_root / "campaign.json"
    if campaign_path.exists() or campaign_path.is_symlink():
        campaign_payload = _regular_bytes(campaign_path, "retained campaign manifest")
        if hashlib.sha256(campaign_payload).hexdigest() != package["campaignSha256"]:
            raise ControllerError("campaign abort manifest identity differs")
    journal_rows = 0
    valid_cells = 0
    journal_path = output_root / "runtime-journal.jsonl"
    if journal_path.exists() or journal_path.is_symlink():
        lines = _regular_bytes(journal_path, "runtime journal").splitlines()
        if len(lines) > RUN_COUNT:
            raise ControllerError("campaign abort journal exceeds frozen cells")
        journal_rows = len(lines)
        for index, line in enumerate(lines):
            row = _json_bytes(line, f"runtime journal row {index}")
            if row.get("state") == "valid":
                valid_cells += 1
    reason = f"{type(error).__name__}: {error}"
    abort = {
        "schemaVersion": 1, "kind": ABORT_KIND,
        "campaignId": package["campaignId"], "setupId": package["setupId"],
        "frameworkCommit": package["frameworkCommit"],
        "packageSha256": package_sha256,
        "campaignSha256": package["campaignSha256"],
        "stage": stage, "errorType": type(error).__name__,
        "error": reason[:2000], "journalRows": journal_rows,
        "validCells": valid_cells, "experimentalState": "ABSTAINED",
        "retryAllowed": False, "promotionAuthorized": False,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
    }
    abort_path = output_root / "campaign-abort.json"
    if abort_path.exists() or abort_path.is_symlink():
        retained = _json_bytes(
            _regular_bytes(abort_path, "campaign abort"), "campaign abort",
        )
        immutable = {
            "kind": ABORT_KIND, "campaignId": package["campaignId"],
            "setupId": package["setupId"],
            "frameworkCommit": package["frameworkCommit"],
            "packageSha256": package_sha256,
            "campaignSha256": package["campaignSha256"],
            "retryAllowed": False, "promotionAuthorized": False,
        }
        if any(retained.get(key) != value for key, value in immutable.items()):
            raise ControllerError("retained campaign abort identity differs")
        return retained
    _atomic_file(
        abort_path,
        json.dumps(abort, allow_nan=False, indent=2, sort_keys=True).encode() + b"\n",
    )
    return abort


CellExecutor = Callable[[Mapping[str, Any], Path, float], Mapping[str, Any]]
CleanupExecutor = Callable[[Mapping[str, Any], float], Mapping[str, Any]]


def _runtime_environment() -> dict[str, str]:
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/nonexistent",
        "LANG": "C", "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1",
    }


def _process_group_alive(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    if not _process_group_alive(process.pid):
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        pass
    if _process_group_alive(process.pid):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        pass
    settled = time.monotonic() + 2.0
    while time.monotonic() < settled and _process_group_alive(process.pid):
        time.sleep(0.05)
    if _process_group_alive(process.pid):
        raise ControllerError("candidate cell process group remained live after termination")


def _compose_project(contract: Mapping[str, Any]) -> str:
    campaign_id = contract.get("campaignId")
    if not isinstance(campaign_id, str) or SAFE_RE.fullmatch(campaign_id) is None:
        raise ControllerError("candidate cleanup campaign identity is unsafe")
    return "teastore_candidate_" + hashlib.sha256(
        campaign_id.encode("utf-8")
    ).hexdigest()[:16]


def _compose_argv(contract: Mapping[str, Any], *tail: str) -> list[str]:
    posture = contract.get("runKey", {}).get("posture")
    if posture not in POSTURE_OVERRIDE:
        raise ControllerError("candidate cleanup posture is invalid")
    argv = ["docker", "compose", "-p", _compose_project(contract)]
    for compose_file in COMPOSE_FILES:
        argv.extend(("-f", compose_file))
    override = POSTURE_OVERRIDE[posture]
    if override is not None:
        argv.extend(("-f", override))
    argv.extend(tail)
    return argv


def subprocess_cleanup_executor(
    contract: Mapping[str, Any], timeout: float,
) -> Mapping[str, Any]:
    """Recover only the campaign-owned Compose namespace by fixed argv."""

    if not math.isfinite(timeout) or timeout <= 0:
        raise ControllerError("no authorization budget remains for emergency cleanup")
    project = _compose_project(contract)
    budget = min(float(timeout), 240.0)
    started = time.monotonic()

    def invoke(argv: list[str]) -> subprocess.CompletedProcess[str]:
        remaining = budget - (time.monotonic() - started)
        if remaining <= 0:
            raise ControllerError("emergency cleanup budget expired")
        try:
            return subprocess.run(
                argv, cwd=ROOT, capture_output=True, text=True, check=False,
                timeout=remaining, env=_runtime_environment(),
            )
        except subprocess.TimeoutExpired as exc:
            raise ControllerError("emergency cleanup command timed out") from exc

    down_argv = _compose_argv(contract, "down", "-v", "--remove-orphans")
    down = invoke(down_argv)
    queries = {
        "containers": [
            "docker", "ps", "-aq", "--filter",
            f"label=com.docker.compose.project={project}",
        ],
        "networks": [
            "docker", "network", "ls", "-q", "--filter",
            f"label=com.docker.compose.project={project}",
        ],
        "volumes": [
            "docker", "volume", "ls", "-q", "--filter",
            f"label=com.docker.compose.project={project}",
        ],
    }
    inventory: dict[str, list[str]] = {}
    return_codes: dict[str, int] = {}
    for name, argv in queries.items():
        result = invoke(argv)
        return_codes[name] = result.returncode
        inventory[name] = [line for line in result.stdout.splitlines() if line]
    clean = (
        down.returncode == 0
        and all(value == 0 for value in return_codes.values())
        and all(not values for values in inventory.values())
    )
    return {
        "schemaVersion": 1,
        "kind": "teastore-candidate-emergency-cleanup-v1",
        "composeProject": project,
        "downCommand": down_argv,
        "downReturnCode": down.returncode,
        "inventoryReturnCodes": return_codes,
        "remaining": inventory,
        "ownedResourcesClean": clean,
    }


def _finalize_candidate_cell(
    contract: Mapping[str, Any], artifact_root: Path,
    production: Mapping[str, Any],
) -> dict[str, Any]:
    """Close a produced cell while the outer lease and deadline still apply.

    The producer may prove its own lifecycle and scientific artifacts, but it
    cannot truthfully attest to controller state.  Only this layer writes the
    cleanup receipt and content manifest, then asks the independent terminal
    validator to replay the sealed root.
    """

    expected_production_keys = {
        "schemaVersion", "kind", "runId", "runKey", "state",
        "safeToContinue", "ownedResourcesClean",
        "candidateValidationSha256", "reason", "promotionAuthorized",
    }
    if not isinstance(production, Mapping) or set(production) != expected_production_keys:
        raise ControllerError("candidate producer receipt fields differ")
    if (
        type(production.get("schemaVersion")) is not int
        or production.get("schemaVersion") != 1
        or production.get("kind") != "teastore-candidate-cell-production-v1"
        or production.get("runId") != contract["runId"]
        or _canonical(production.get("runKey")) != _canonical(contract["runKey"])
        or production.get("state") != "validated"
        or production.get("safeToContinue") is not True
        or production.get("ownedResourcesClean") is not True
        or production.get("reason") is not None
        or production.get("promotionAuthorized") is not False
        or not isinstance(production.get("candidateValidationSha256"), str)
        or SHA256_RE.fullmatch(production["candidateValidationSha256"]) is None
    ):
        raise ControllerError("candidate producer receipt is not admissible")

    required = contract.get("requiredArtifacts")
    if not isinstance(required, list) or any(not isinstance(name, str) for name in required):
        raise ControllerError("candidate required-artifact contract differs")
    required_set = set(required)
    if len(required_set) != len(required) or {
        "candidate-validation.json", "cell-cleanup.json", "content-manifest.json",
    } - required_set:
        raise ControllerError("candidate required-artifact contract cannot be sealed")
    expected_produced = required_set - {"cell-cleanup.json", "content-manifest.json"}
    try:
        metadata = artifact_root.lstat()
        if artifact_root.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise ControllerError("candidate artifact root is not a real directory")
        observed = {path.name for path in artifact_root.iterdir()}
    except ControllerError:
        raise
    except OSError as exc:
        raise ControllerError(f"cannot inspect candidate artifact root: {exc}") from exc
    if observed != expected_produced:
        raise ControllerError(
            "candidate producer artifact membership differs: "
            f"missing={sorted(expected_produced - observed)}, "
            f"extra={sorted(observed - expected_produced)}"
        )
    candidate_payload = _regular_bytes(
        artifact_root / "candidate-validation.json",
        "candidate scientific validation",
    )
    if hashlib.sha256(candidate_payload).hexdigest() != production[
        "candidateValidationSha256"
    ]:
        raise ControllerError("candidate validation differs from producer anchor")

    cleanup = {
        "schemaVersion": 1,
        "kind": "teastore-candidate-cell-cleanup-v1",
        "runId": contract["runId"],
        "outerLeaseHeld": True,
        "deadlineControllerSettled": True,
        "ownedResourcesClean": True,
        "safeToContinue": True,
    }
    _atomic_file(
        artifact_root / "cell-cleanup.json",
        json.dumps(cleanup, allow_nan=False, indent=2, sort_keys=True).encode() + b"\n",
    )
    rows: list[dict[str, Any]] = []
    for name in sorted(required_set - {"content-manifest.json"}):
        relative = PurePosixPath(name)
        if relative.as_posix() != name or len(relative.parts) != 1 or name.startswith("."):
            raise ControllerError("candidate required artifact is not one safe file name")
        payload = _regular_bytes(artifact_root / name, f"candidate artifact {name}")
        rows.append({
            "path": name,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
    manifest_payload = json.dumps(
        {"schemaVersion": 1, "algorithm": "sha256", "files": rows},
        allow_nan=False, indent=2, sort_keys=True,
    ).encode() + b"\n"
    _atomic_file(artifact_root / "content-manifest.json", manifest_payload)
    manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()
    replay = dict(_terminal_module().validate_candidate_cell(
        artifact_root,
        expected_run_key=copy.deepcopy(contract["runKey"]),
        expected_manifest_sha256=manifest_sha256,
    ))
    if replay.get("verdict") != "pass" or replay.get("manifestSha256") != manifest_sha256:
        raise ControllerError("candidate cell terminal replay did not pass")
    return {
        "schemaVersion": 1,
        "kind": "teastore-candidate-cell-execution-v1",
        "runId": contract["runId"],
        "runKey": copy.deepcopy(contract["runKey"]),
        "state": "valid",
        "safeToContinue": True,
        "manifestSha256": manifest_sha256,
        "reason": None,
    }


def subprocess_cell_executor(
    contract: Mapping[str, Any], artifact_root: Path, timeout: float,
) -> Mapping[str, Any]:
    """Invoke only the reviewed cell producer by argv, never a shell string."""

    contract_path = artifact_root.parent / f".{artifact_root.name}.contract.json"
    _atomic_file(contract_path, _canonical(contract) + b"\n")
    process: subprocess.Popen[bytes] | None = None
    try:
        try:
            process = subprocess.Popen(
                [
                    "/usr/bin/python3", "-I", str(CELL_EXECUTOR), "--contract", str(contract_path),
                    "--output", str(artifact_root),
                ],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True, env=_runtime_environment(),
            )
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            if process is None:  # pragma: no cover - Popen precedes communicate
                raise ControllerError("candidate cell process did not start") from exc
            _stop_process_group(process)
            stdout, stderr = process.communicate()
            raise ControllerError(
                "candidate cell executor exceeded the authorization budget"
            ) from exc
        except BaseException:
            if process is not None:
                _stop_process_group(process)
                process.communicate()
            raise
    finally:
        contract_path.unlink(missing_ok=True)
    if process is None:  # pragma: no cover - successful try always assigns it
        raise ControllerError("candidate cell process did not start")
    if _process_group_alive(process.pid):
        _stop_process_group(process)
        raise ControllerError("candidate cell executor left a live process group")
    if process.returncode != 0:
        # Keeping the FIRST 300 characters put the whole budget inside the
        # docker argv and truncated two separate diagnoses before they reached
        # the reason a cell failed. A traceback carries its exception on the
        # last lines, and a blocker list is enumerated at the end, so keep the
        # tail and keep enough of it to hold the whole list. Neither the abort
        # document nor the journal caps this field.
        text = stderr.decode("utf-8", errors="replace").strip()
        detail = text if len(text) <= 4000 else "...[head truncated]... " + text[-4000:]
        raise ControllerError(f"candidate cell executor failed: {detail or process.returncode}")
    production = _json_bytes(stdout, "candidate cell executor receipt")
    return _finalize_candidate_cell(contract, artifact_root, production)


def execute_package(
    document: Mapping[str, Any],
    output_root: Path,
    *,
    cell_executor: CellExecutor = subprocess_cell_executor,
    cleanup_executor: CleanupExecutor = subprocess_cleanup_executor,
    clock: Callable[[], float] = time.time,
    terminal_validator: Callable[..., Mapping[str, Any]] | None = None,
    package_sha256: str | None = None,
) -> dict[str, Any]:
    """Execute one package under one outer lease; no resume path exists."""

    transport = _transport_module()
    package = transport.validate_runtime_package(dict(document))
    output_root = Path(output_root)
    if output_root.exists() or output_root.is_symlink():
        raise ControllerError("one-shot candidate output root already exists")
    if output_root.parent.resolve() != Path(package["resultsRoot"]).resolve():
        raise ControllerError("candidate output root is outside the reviewed result parent")
    if output_root.name != package["campaignId"]:
        raise ControllerError("candidate output root identity differs from package")
    if package_sha256 is None:
        package_sha256 = hashlib.sha256(
            json.dumps(package, indent=2, sort_keys=True).encode() + b"\n"
        ).hexdigest()
    if SHA256_RE.fullmatch(package_sha256) is None:
        raise ControllerError("candidate package digest is invalid")
    records: list[dict[str, Any]] = []
    anchors: dict[str, str] = {}
    lease: int | None = None
    lease_receipt_pending: Path | None = None
    lease_receipt_final: Path | None = None
    lease_acquisition: dict[str, Any] | None = None
    stage = "controller-preflight"
    try:
        observed_user = pwd.getpwuid(os.geteuid()).pw_name
        if (
            observed_user != package["executionUser"]
            or os.geteuid() != package["executionUid"]
            or os.getegid() != package["executionGid"]
        ):
            raise ControllerError("candidate controller execution identity differs")
        now = float(clock())
        not_before = _timestamp(package["notBefore"], "notBefore").timestamp()
        deadline = _timestamp(
            package["authorizationDeadline"], "authorizationDeadline",
        ).timestamp()
        if now < not_before or math.floor(deadline - now) < MINIMUM_FIRST_MUTATION_SECONDS:
            raise ControllerError("runtime authorization window is not open or is too short")
        stage = "outer-lease-acquisition"
        lease_path = Path(package["outerLeasePath"])
        lease_path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        lease = os.open(lease_path, flags, 0o600)
        if not stat.S_ISREG(os.fstat(lease).st_mode):
            raise ControllerError("outer lease is not a regular file")
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ControllerError(f"outer {RUN_COUNT}-cell lease is already held") from exc
        lease_metadata = os.fstat(lease)
        lease_receipt_root = Path(package["resultsRoot"]) / ".lease-receipts"
        if not lease_receipt_root.is_dir() or lease_receipt_root.is_symlink():
            raise ControllerError("lease receipt root is unavailable")
        lease_receipt_pending = lease_receipt_root / f"{package['campaignId']}.pending.json"
        lease_receipt_final = lease_receipt_root / f"{package['campaignId']}.json"
        if (
            lease_receipt_pending.exists() or lease_receipt_pending.is_symlink()
            or lease_receipt_final.exists() or lease_receipt_final.is_symlink()
        ):
            raise ControllerError("candidate lease receipt already exists")
        lease_acquisition = {
            "schemaVersion": 1,
            "kind": "teastore-candidate-lease-receipt-v1",
            "campaignId": package["campaignId"],
            "setupId": package["setupId"],
            "packageSha256": package_sha256,
            "leasePath": str(lease_path),
            "ownerPid": os.getpid(),
            "ownerToken": hashlib.sha256(
                f"{package_sha256}\0{os.getpid()}\0{lease_metadata.st_dev}\0{lease_metadata.st_ino}".encode()
            ).hexdigest(),
            "device": lease_metadata.st_dev,
            "inode": lease_metadata.st_ino,
            "acquiredAt": datetime.now(timezone.utc).isoformat(),
            "state": "held",
            "releasedAt": None,
            "releaseObserved": False,
            "successorMayAcquire": False,
        }
        _atomic_file(
            lease_receipt_pending,
            json.dumps(lease_acquisition, allow_nan=False, indent=2, sort_keys=True).encode() + b"\n",
        )
        stage = "campaign-initialization"
        output_root.mkdir(mode=0o700)
        campaign_bytes = base64.b64decode(
            package["campaignManifestBase64"], validate=True,
        )
        _atomic_file(output_root / "campaign.json", campaign_bytes)
        campaign = _json_bytes(campaign_bytes, "embedded campaign manifest")
        journal = output_root / "runtime-journal.jsonl"
        stage = "cell-execution"
        for cell in package["cells"]:
            remaining = deadline - float(clock()) - package["cleanupReserveSeconds"]
            if remaining <= 0:
                raise ControllerError("authorization budget reached reserved cleanup interval")
            relative = _safe_run_path(cell, campaign)
            artifact_root = output_root.joinpath(*relative.parts)
            artifact_root.parent.mkdir(parents=True, exist_ok=True)
            if artifact_root.exists() or artifact_root.is_symlink():
                raise ControllerError("candidate cell root exists before first attempt")
            try:
                outcome = dict(cell_executor(cell, artifact_root, remaining))
                expected_keys = {
                    "schemaVersion", "kind", "runId", "runKey", "state",
                    "safeToContinue", "manifestSha256", "reason",
                }
                if set(outcome) != expected_keys or (
                    outcome["schemaVersion"] != 1
                    or outcome["kind"] != "teastore-candidate-cell-execution-v1"
                    or outcome["runId"] != cell["runId"]
                    or _canonical(outcome["runKey"]) != _canonical(cell["runKey"])
                    or outcome["state"] != "valid"
                    or outcome["safeToContinue"] is not True
                    or not isinstance(outcome["manifestSha256"], str)
                    or SHA256_RE.fullmatch(outcome["manifestSha256"]) is None
                    or outcome["reason"] is not None
                ):
                    raise ControllerError("candidate cell result is not terminally valid")
                anchors[cell["runId"]] = outcome["manifestSha256"]
                record = _journal_record(
                    records, cell=cell, state="valid",
                    manifest_sha256=outcome["manifestSha256"], reason=None,
                )
                _append_journal(journal, record)
                records.append(record)
            except Exception as exc:  # noqa: BLE001 - preserve the first failed attempt
                cleanup_error: Exception | None = None
                try:
                    cleanup_timeout = max(1.0, deadline - float(clock()))
                    cleanup = dict(cleanup_executor(cell, cleanup_timeout))
                    if (
                        cleanup.get("kind") != "teastore-candidate-emergency-cleanup-v1"
                        or cleanup.get("composeProject") != _compose_project(cell)
                        or cleanup.get("ownedResourcesClean") is not True
                    ):
                        raise ControllerError("emergency cleanup proof is not clean")
                except Exception as cleanup_exc:  # noqa: BLE001 - preserve both causes
                    cleanup_error = cleanup_exc
                reason = f"{type(exc).__name__}: {exc}"
                if cleanup_error is not None:
                    reason += (
                        "; emergency cleanup failed: "
                        f"{type(cleanup_error).__name__}: {cleanup_error}"
                    )
                record = _journal_record(
                    records, cell=cell, state="stopped", manifest_sha256=None,
                    reason=reason,
                )
                _append_journal(journal, record)
                records.append(record)
                if cleanup_error is not None:
                    raise ControllerError(reason) from exc
                raise
        stage = "terminal-validation"
        validator = terminal_validator or _terminal_module().validate_candidate_campaign
        terminal = dict(validator(
            output_root,
            expected_campaign_sha256=package["campaignSha256"],
            manifest_anchors=anchors,
        ))
        if terminal.get("verdict") != "pass" or terminal.get("runCount") != RUN_COUNT:
            raise ControllerError(f"{RUN_COUNT}-cell terminal campaign replay did not pass")
        _atomic_file(
            output_root / "campaign-terminal-validation.json",
            json.dumps(terminal, indent=2, sort_keys=True).encode() + b"\n",
        )
    except Exception as exc:
        try:
            _retain_campaign_abort(
                output_root, package, package_sha256=package_sha256,
                stage=stage, error=exc,
            )
        except Exception as abort_exc:
            raise ControllerError(
                f"{type(exc).__name__}: {exc}; campaign abort retention failed: "
                f"{type(abort_exc).__name__}: {abort_exc}"
            ) from exc
        raise
    finally:
        if lease is not None:
            try:
                fcntl.flock(lease, fcntl.LOCK_UN)
            finally:
                os.close(lease)
            if lease_acquisition is not None and lease_receipt_pending is not None and lease_receipt_final is not None:
                verify_flags = os.O_RDWR
                if hasattr(os, "O_NOFOLLOW"):
                    verify_flags |= os.O_NOFOLLOW
                verifier = os.open(Path(package["outerLeasePath"]), verify_flags)
                try:
                    current = os.fstat(verifier)
                    if (
                        current.st_dev != lease_acquisition["device"]
                        or current.st_ino != lease_acquisition["inode"]
                    ):
                        raise ControllerError("lease identity changed before release verification")
                    fcntl.flock(verifier, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(verifier, fcntl.LOCK_UN)
                finally:
                    os.close(verifier)
                released = dict(lease_acquisition)
                released.update({
                    "state": "released",
                    "releasedAt": datetime.now(timezone.utc).isoformat(),
                    "releaseObserved": True,
                    "successorMayAcquire": True,
                })
                _atomic_file(
                    lease_receipt_final,
                    json.dumps(released, allow_nan=False, indent=2, sort_keys=True).encode() + b"\n",
                )
                lease_receipt_pending.unlink()
    return {
        "schemaVersion": 1,
        "kind": "teastore-candidate-remote-launch-v1",
        "campaignId": package["campaignId"],
        "frameworkCommit": package["frameworkCommit"],
        "packageSha256": package_sha256,
        "runCount": len(anchors),
        "state": "complete",
        "promotionAuthorized": False,
    }


def launch(
    package_path: Path, output: Path, framework_commit: str,
    expected_package_sha256: str,
) -> dict[str, Any]:
    """Execute one root-wrapper-installed package exactly once."""

    if COMMIT_RE.fullmatch(framework_commit) is None:
        raise ControllerError("framework commit is invalid")
    if SHA256_RE.fullmatch(expected_package_sha256) is None:
        raise ControllerError("expected runtime package digest is invalid")
    payload = _regular_bytes(package_path, "installed runtime package")
    if hashlib.sha256(payload).hexdigest() != expected_package_sha256:
        raise ControllerError("installed runtime package digest differs")
    document = _transport_module().validate_runtime_package(
        _json_bytes(payload, "pending runtime package")
    )
    if document["frameworkCommit"] != framework_commit:
        raise ControllerError("pending package framework commit differs")
    receipt = execute_package(
        document, output, package_sha256=expected_package_sha256,
    )
    # Bind the remote receipt to the exact transferred bytes.  The in-process
    # helper uses a deterministic serialization only because it has no source
    # package file; this launch boundary does have the retained byte string.
    receipt["packageSha256"] = hashlib.sha256(payload).hexdigest()
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("launch",))
    parser.add_argument("--package", dest="package_path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--framework-commit", required=True)
    parser.add_argument("--package-sha256", required=True)
    args = parser.parse_args(argv)
    # The bounded SSH call may disappear during a multi-hour campaign.  HUP is
    # not an authorization revocation and must not strand the owned Compose
    # namespace; deadline and per-cell controls remain authoritative.
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        receipt = launch(
            args.package_path, args.output, args.framework_commit,
            args.package_sha256,
        )
    except Exception as exc:  # noqa: BLE001 - CLI emits one bounded failure record
        print(json.dumps({"state": "blocked", "error": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ABORT_KIND", "ControllerError", "_finalize_candidate_cell",
    "_retain_campaign_abort", "execute_package", "launch",
    "subprocess_cell_executor", "subprocess_cleanup_executor",
]
