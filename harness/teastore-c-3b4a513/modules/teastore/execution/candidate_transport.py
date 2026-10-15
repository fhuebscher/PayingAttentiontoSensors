#!/usr/bin/env python3
"""Bounded argv-only transport for one exact TeaStore 27-cell campaign.

The transport consumes a package already admitted by ``candidate_runtime_adapter``.
It cannot create gate receipts and accepts no free-form remote command.  The
remote controller owns one flock for the complete campaign and applies the
authorization deadline.  Tests inject a runner; importing this module performs
no process, network, SSH, Docker, or filesystem mutation.
"""
from __future__ import annotations

import copy
import base64
import hashlib
import importlib.util
import json
import math
import pwd
import re
import stat
import subprocess
import sys
import os
import io
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, NoReturn, Optional, Sequence


ROOT = Path(__file__).resolve().parents[3]


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


# With no selector every value below equals its c1724b1 literal (the frozen 27-cell epoch).
EPOCH = _study_epoch_module().active(ROOT)
TARGET = "fb14srv5"
TRANSPORT_USER = "root"
EXECUTION_USER = "stig"
EXECUTION_UID = 1015
EXECUTION_GID = 1015
EXECUTION_METHOD = "runuser"
RUN_COUNT = EPOCH["runCount"]
MINIMUM_FIRST_MUTATION_SECONDS = EPOCH["minimumFirstMutationRemainingSeconds"]
OUTER_LEASE_SCOPE = EPOCH["outerLeaseScope"]
MAX_READINESS_ARCHIVE_BYTES = 64 * 1024 * 1024
# Must not exceed the installed reader's own hard bound on the spec member.
MAX_CAPTURE_SPEC_BYTES = 65536
PACKAGE_KIND = "teastore-candidate-runtime-package-v1"
ABORT_KIND = "teastore-candidate-controller-abort-v1"
TRANSPORT_CONTRACT = "teastore-candidate-bounded-transport-v1"
REMOTE_CONTROLLER = "modules/teastore/execution/candidate_remote_controller.py"
REMOTE_INSTALLER = "modules/teastore/execution/candidate_release_installer.py"
CANDIDATE_V4_ROOT = "/home/stig/.local/share/observability-placement/candidate-v4/teastore"
REMOTE_RELEASES = f"{CANDIDATE_V4_ROOT}/releases"
REMOTE_RESULTS = f"{CANDIDATE_V4_ROOT}/results"
REMOTE_READINESS_CONTROLS = "/var/lib/observability-placement/candidate-v4/teastore/readiness"
LEASE_PATH = f"{CANDIDATE_V4_ROOT}/leases/host-exclusive.lock"
SAFE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TransportError(ValueError):
    """The admitted package or bounded transport result differs."""


def _reject_constant(value: str) -> NoReturn:
    raise TransportError(f"non-finite JSON value is forbidden: {value}")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TransportError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, allow_nan=False, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TransportError(f"value is not canonical JSON: {exc}") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def strict_json(payload: bytes, where: str) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_no_duplicates, parse_constant=_reject_constant,
        )
    except TransportError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TransportError(f"invalid JSON in {where}: {exc}") from exc
    if not isinstance(value, dict):
        raise TransportError(f"{where} must contain one object")
    return value


def _regular_payload(path: Path, where: str) -> bytes:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise TransportError(f"{where} is not a regular non-symlink file")
        payload = path.read_bytes()
        after = path.lstat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ) or len(payload) != before.st_size:
            raise TransportError(f"{where} changed while being read")
        return payload
    except TransportError:
        raise
    except OSError as exc:
        raise TransportError(f"cannot read {where}: {exc}") from exc


def _adapter_module():
    import importlib.util
    path = Path(__file__).with_name("candidate_runtime_adapter.py")
    spec = importlib.util.spec_from_file_location(
        "teastore_candidate_transport_gate_adapter", path,
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise TransportError("cannot load candidate runtime gate adapter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _exclusive_bytes(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:  # pragma: no cover
                raise TransportError("release artifact write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def build_release_bundle(
    bindings: Any, *, bundle_path: Path, manifest_path: Path,
) -> dict[str, Any]:
    """Build and inspect one exact clean-HEAD Git bundle before GATE-SETUP."""

    bundle_path = Path(bundle_path)
    manifest_path = Path(manifest_path)
    if bundle_path.exists() or bundle_path.is_symlink() or manifest_path.exists() or (
        manifest_path.is_symlink()
    ):
        raise TransportError("release bundle or manifest output already exists")
    environment = {
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": "/nonexistent-candidate-v4-bundle", "LC_ALL": "C", "LANG": "C",
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0",
    }
    def git(*args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ("git", "-C", str(ROOT), *args), check=False, capture_output=True,
            env=environment,
        )
    if git("rev-parse", "HEAD").stdout.decode().strip() != bindings.framework_commit or (
        git("rev-parse", "HEAD^{tree}").stdout.decode().strip() != bindings.framework_tree
    ) or git(
        "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none",
    ).stdout:
        raise TransportError("release bundle source is not the exact clean bound HEAD")
    try:
        submodule = ROOT / "upstream/teastore"
        submodule_git = subprocess.run(
            ("git", "-C", str(submodule), "rev-parse", "HEAD"),
            check=False, capture_output=True, env=environment,
        )
        submodule_tree = subprocess.run(
            ("git", "-C", str(submodule), "rev-parse", "HEAD^{tree}"),
            check=False, capture_output=True, env=environment,
        )
        submodule_status = subprocess.run(
            ("git", "-C", str(submodule), "status", "--porcelain=v1",
             "--untracked-files=all"), check=False, capture_output=True,
            env=environment,
        )
        expected_submodule = "34b37f7e7be433ce72d5f9455e66922a13116749"
        if (
            submodule_git.returncode != 0
            or submodule_git.stdout.decode().strip() != expected_submodule
            or submodule_tree.returncode != 0
            or COMMIT_RE.fullmatch(submodule_tree.stdout.decode().strip()) is None
            or submodule_status.returncode != 0
            or submodule_status.stdout
        ):
            raise TransportError(
                "upstream/teastore is not initialized at the exact clean source commit"
            )
        with tempfile.TemporaryDirectory(prefix="teastore-candidate-v4-bundle-") as raw:
            temporary = Path(raw)
            super_bundle = temporary / "superproject.bundle"
            source_bundle = temporary / "upstream-teastore.bundle"
            created = git("bundle", "create", str(super_bundle), "HEAD")
            source_created = subprocess.run(
                ("git", "-C", str(submodule), "bundle", "create",
                 str(source_bundle), "HEAD"), check=False, capture_output=True,
                env=environment,
            )
            if created.returncode != 0 or source_created.returncode != 0:
                raise TransportError("exact superproject or TeaStore bundle creation failed")
            super_payload = _regular_payload(super_bundle, "superproject Git bundle")
            source_payload = _regular_payload(source_bundle, "TeaStore Git bundle")
            listed = git("bundle", "list-heads", str(super_bundle))
            source_listed = subprocess.run(
                ("git", "-C", str(submodule), "bundle", "list-heads",
                 str(source_bundle)), check=False, capture_output=True,
                env=environment,
            )
            if listed.returncode != 0 or listed.stdout.decode(
                "ascii", errors="strict"
            ).splitlines() != [f"{bindings.framework_commit} HEAD"] or (
                source_listed.returncode != 0
                or source_listed.stdout.decode("ascii", errors="strict").splitlines()
                != [f"{expected_submodule} HEAD"]
            ):
                raise TransportError("release bundle member HEAD differs")
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                for name, payload in (
                    ("superproject.bundle", super_payload),
                    ("upstream-teastore.bundle", source_payload),
                ):
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    info.mode = 0o600
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    archive.addfile(info, io.BytesIO(payload))
            bundle = stream.getvalue()
            _exclusive_bytes(bundle_path, bundle)
            members = {
                "superproject.bundle": {
                    "sha256": hashlib.sha256(super_payload).hexdigest(),
                    "bytes": len(super_payload), "commit": bindings.framework_commit,
                    "tree": bindings.framework_tree,
                },
                "upstream-teastore.bundle": {
                    "sha256": hashlib.sha256(source_payload).hexdigest(),
                    "bytes": len(source_payload), "commit": expected_submodule,
                    "tree": submodule_tree.stdout.decode().strip(),
                },
            }
        manifest = {
            "schemaVersion": 1,
            "kind": "teastore-candidate-release-manifest-v1",
            "frameworkCommit": bindings.framework_commit,
            "frameworkTree": bindings.framework_tree,
            "bundleFormat": "candidate-v4-tar-v1",
            "bundleSha256": hashlib.sha256(bundle).hexdigest(),
            "bundleBytes": len(bundle),
            "bundleMembers": members,
            "controllerDigests": copy.deepcopy(bindings.controller_sha256),
            "submoduleCommits": {
                "upstream/teastore": "34b37f7e7be433ce72d5f9455e66922a13116749",
            },
            "setupSourceBuildAllowed": True,
            "campaignSourceBuildAllowed": False,
        }
        _adapter_module().validate_release_manifest(manifest, bindings)
        _exclusive_bytes(
            manifest_path,
            json.dumps(manifest, allow_nan=False, indent=2, sort_keys=True).encode() + b"\n",
        )
        return manifest
    except Exception:
        bundle_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise


def build_capture_spec(
    bindings: Any, release_binding: Mapping[str, Any], *, archive_path: Path,
) -> str:
    """Seal the identity-only v2 readiness ingress.

    The installed target generates its whole readiness tree from installed
    bytes and live probes; this ingress carries identity only. The installed
    reader accepts exactly one member named capture-spec.json and rejects
    caller-authored observations, reports, verdicts, hashes, and seals, so no
    evidence may be added here -- the point is that the caller cannot pre-state
    what the target is supposed to find.
    """

    archive_path = Path(archive_path)
    if archive_path.exists() or archive_path.is_symlink():
        raise TransportError("readiness capture spec output already exists")
    spec = {
        "schemaVersion": 1,
        "kind": "teastore-candidate-readiness-capture-spec-v2",
        "seams": list(_adapter_module().READINESS_SEAMS),
        "descriptorCanonicalSha256": bindings.descriptor_sha256,
        "compiledPlanCanonicalSha256": bindings.plan_sha256,
        "releaseBindingSha256": canonical_sha256(dict(release_binding)),
    }
    payload = json.dumps(
        spec, allow_nan=False, indent=2, sort_keys=True,
    ).encode() + b"\n"
    if len(payload) > MAX_CAPTURE_SPEC_BYTES:
        raise TransportError("readiness capture spec exceeds its byte bound")
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        info = tarfile.TarInfo("capture-spec.json")
        info.type = tarfile.REGTYPE
        info.size = len(payload)
        info.mode = 0o600
        info.uid = info.gid = info.mtime = 0
        archive.addfile(info, io.BytesIO(payload))
    sealed = stream.getvalue()
    if len(sealed) > MAX_READINESS_ARCHIVE_BYTES:
        raise TransportError("readiness archive exceeds its transfer byte bound")
    _exclusive_bytes(archive_path, sealed)
    return hashlib.sha256(sealed).hexdigest()


def _safe(value: Any, where: str) -> str:
    if not isinstance(value, str) or SAFE_RE.fullmatch(value) is None:
        raise TransportError(f"{where} is not a safe identifier")
    return value


def _safe_relative_identifier(value: Any, where: str) -> str:
    """Accept a normalized slash-separated identity with safe path segments."""

    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise TransportError(f"{where} is not a safe relative identifier")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(
        segment in {"", ".", ".."} or SAFE_RE.fullmatch(segment) is None
        for segment in path.parts
    ):
        raise TransportError(f"{where} is not a normalized safe identifier")
    return value


def _same(left: Any, right: Any) -> bool:
    try:
        return canonical_bytes(left) == canonical_bytes(right)
    except TransportError:
        return False


def _timestamp(value: Any, where: str) -> datetime:
    if not isinstance(value, str):
        raise TransportError(f"{where} is not a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TransportError(f"{where} is not ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TransportError(f"{where} has no UTC offset")
    return parsed.astimezone(timezone.utc)


def build_runtime_package(runtime_package: Any) -> dict[str, Any]:
    """Project an already validated RuntimePackage into remote controller input."""

    bindings = runtime_package.bindings
    authorization = runtime_package.gate_run.get("authorization", {})
    campaign_id = _safe(authorization.get("campaignId"), "campaign ID")
    cells = []
    # Import lazily to keep the transport independent from authorization logic.
    import importlib.util
    adapter_path = Path(__file__).with_name("candidate_runtime_adapter.py")
    spec = importlib.util.spec_from_file_location(
        "teastore_candidate_transport_adapter", adapter_path,
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise TransportError("cannot load candidate runtime adapter")
    adapter = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = adapter
    spec.loader.exec_module(adapter)
    for cell in bindings.cells:
        cells.append(adapter.build_cell_contract(runtime_package, cell))
    if len(cells) != RUN_COUNT or [row["runId"] for row in cells] != list(
        authorization.get("authorizedRunIds", [])
    ):
        raise TransportError(f"runtime package does not preserve the exact {RUN_COUNT}-cell order")
    return {
        "schemaVersion": 1,
        "kind": PACKAGE_KIND,
        "campaignId": campaign_id,
        "target": TARGET,
        "transportUser": authorization["transportUser"],
        "executionUser": authorization["executionUser"],
        "executionUid": authorization["executionUid"],
        "executionGid": authorization["executionGid"],
        "executionMethod": authorization["executionMethod"],
        "setupId": authorization["setupId"],
        "releaseRoot": authorization["releaseRoot"],
        "resultsRoot": authorization["resultsRoot"],
        "gateSetupSha256": authorization["gateSetupSha256"],
        "releaseManifestSha256": authorization["releaseManifestSha256"],
        "bundleSha256": authorization["bundleSha256"],
        "releaseInstalledAt": authorization["releaseInstalledAt"],
        "releaseBindingSha256": canonical_sha256(runtime_package.readiness["release"]),
        "frameworkCommit": bindings.framework_commit,
        "campaignSha256": bindings.campaign_sha256,
        "campaignManifestBase64": base64.b64encode(
            (bindings.root / "campaign.json").read_bytes()
        ).decode("ascii"),
        "descriptorCanonicalSha256": bindings.descriptor_sha256,
        "compiledPlanCanonicalSha256": bindings.plan_sha256,
        "gatePlanSha256": runtime_package.gate_plan_sha256,
        "runtimeReadinessSha256": runtime_package.readiness_sha256,
        "readinessArchiveSha256": runtime_package.readiness.get(
            "ingressArchiveSha256",
            runtime_package.readiness.get("readinessArchiveSha256"),
        ),
        "runtimePreflightCapturedAt": runtime_package.readiness[
            "runtimePreflight"
        ]["capturedAt"],
        "gateRunSha256": runtime_package.gate_run_sha256,
        "notBefore": authorization["notBefore"],
        "authorizationDeadline": authorization["authorizationDeadline"],
        "cleanupReserveSeconds": authorization["cleanupReserveSeconds"],
        "outerLeasePath": authorization["exclusiveLeasePath"],
        "outerLeaseScope": OUTER_LEASE_SCOPE,
        "oneShot": True,
        "retryAllowed": False,
        "substitutionAllowed": False,
        "rerandomizationAllowed": False,
        "runCount": RUN_COUNT,
        "cells": cells,
        "promotionAuthorized": False,
    }


def _terminal_module():
    import importlib.util
    path = ROOT / "modules/teastore/validation/candidate_terminal.py"
    spec = importlib.util.spec_from_file_location(
        "teastore_candidate_transport_terminal", path,
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise TransportError("cannot load candidate terminal validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_fetched_abort(
    root: Path, package: Mapping[str, Any], *, package_sha256: str,
) -> dict[str, Any]:
    """Validate one retained controller failure as terminal non-evidence."""

    document = strict_json(
        _regular_payload(Path(root) / "campaign-abort.json", "fetched campaign abort"),
        "fetched campaign abort",
    )
    expected_keys = {
        "schemaVersion", "kind", "campaignId", "setupId", "frameworkCommit",
        "packageSha256", "campaignSha256", "stage", "errorType", "error",
        "journalRows", "validCells", "experimentalState", "retryAllowed",
        "promotionAuthorized", "recordedAt",
    }
    if (
        set(document) != expected_keys
        or type(document.get("schemaVersion")) is not int
        or document.get("schemaVersion") != 1
        or document.get("kind") != ABORT_KIND
        or document.get("campaignId") != package.get("campaignId")
        or document.get("setupId") != package.get("setupId")
        or document.get("frameworkCommit") != package.get("frameworkCommit")
        or document.get("packageSha256") != package_sha256
        or document.get("campaignSha256") != package.get("campaignSha256")
        or document.get("stage") not in {
            "controller-preflight", "outer-lease-acquisition",
            "campaign-initialization", "cell-execution", "terminal-validation",
        }
        or not isinstance(document.get("errorType"), str)
        or not document["errorType"]
        or not isinstance(document.get("error"), str)
        or not document["error"].startswith(f"{document['errorType']}: ")
        or type(document.get("journalRows")) is not int
        or not 0 <= document["journalRows"] <= RUN_COUNT
        or type(document.get("validCells")) is not int
        or not 0 <= document["validCells"] <= document["journalRows"]
        or document.get("experimentalState") != "ABSTAINED"
        or document.get("retryAllowed") is not False
        or document.get("promotionAuthorized") is not False
    ):
        raise TransportError("fetched campaign abort identity or state differs")
    _timestamp(document.get("recordedAt"), "fetched campaign abort recordedAt")
    journal_path = Path(root) / "runtime-journal.jsonl"
    observed_rows = 0
    observed_valid = 0
    if journal_path.exists() or journal_path.is_symlink():
        lines = _regular_payload(journal_path, "fetched candidate runtime journal").splitlines()
        observed_rows = len(lines)
        for index, line in enumerate(lines):
            row = strict_json(line, f"fetched runtime journal row {index}")
            if row.get("state") == "valid":
                observed_valid += 1
    if (
        observed_rows != document["journalRows"]
        or observed_valid != document["validCells"]
    ):
        raise TransportError("fetched campaign abort journal counts differ")
    campaign_path = Path(root) / "campaign.json"
    if campaign_path.exists() or campaign_path.is_symlink():
        if hashlib.sha256(_regular_payload(
            campaign_path, "fetched campaign manifest",
        )).hexdigest() != package["campaignSha256"]:
            raise TransportError("fetched campaign abort manifest differs")
    return copy.deepcopy(document)


def replay_fetched_campaign(root: Path, package: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct external cell anchors from the append-only remote journal."""

    root = Path(root)
    journal_payload = _regular_payload(
        root / "runtime-journal.jsonl", "fetched candidate runtime journal",
    )
    records: list[dict[str, Any]] = []
    previous = "0" * 64
    for index, line in enumerate(journal_payload.splitlines()):
        row = strict_json(line, f"fetched runtime journal row {index}")
        expected_keys = {
            "schemaVersion", "kind", "sequence", "previousRecordSha256",
            "recordSha256", "runId", "runKey", "state", "manifestSha256",
            "reason", "recordedAt",
        }
        digest = row.get("recordSha256")
        body = {key: value for key, value in row.items() if key != "recordSha256"}
        if (
            set(row) != expected_keys
            or row.get("schemaVersion") != 1
            or row.get("kind") != "teastore-candidate-runtime-journal-v1"
            or row.get("sequence") != index
            or row.get("previousRecordSha256") != previous
            or row.get("state") != "valid"
            or row.get("reason") is not None
            or not isinstance(digest, str)
            or digest != canonical_sha256(body)
            or not isinstance(row.get("manifestSha256"), str)
            or SHA256_RE.fullmatch(row["manifestSha256"]) is None
        ):
            raise TransportError("fetched candidate runtime journal does not replay")
        previous = digest
        records.append(row)
    if len(records) != RUN_COUNT or [row["runId"] for row in records] != [
        cell["runId"] for cell in package["cells"]
    ]:
        raise TransportError(f"fetched candidate journal is not the exact {RUN_COUNT}-cell order")
    anchors = {row["runId"]: row["manifestSha256"] for row in records}
    report = _terminal_module().validate_candidate_campaign(
        root,
        expected_campaign_sha256=package["campaignSha256"],
        manifest_anchors=anchors,
    )
    if report.get("verdict") != "pass" or report.get("runCount") != RUN_COUNT:
        raise TransportError("fetched candidate campaign failed local terminal replay")
    retained = strict_json(
        _regular_payload(
            root / "campaign-terminal-validation.json",
            "fetched campaign terminal validation",
        ),
        "fetched campaign terminal validation",
    )
    if not _same(retained, report):
        raise TransportError("fetched and locally replayed terminal reports differ")
    return report


def validate_runtime_package(document: Any) -> dict[str, Any]:
    """Validate remote package structure before any transport side effect."""

    keys = {
        "schemaVersion", "kind", "campaignId", "target", "transportUser",
        "executionUser", "executionUid", "executionGid", "executionMethod",
        "setupId", "releaseRoot", "resultsRoot", "gateSetupSha256",
        "releaseManifestSha256", "bundleSha256", "releaseInstalledAt",
        "releaseBindingSha256",
        "frameworkCommit", "campaignSha256", "descriptorCanonicalSha256",
        "campaignManifestBase64",
        "compiledPlanCanonicalSha256", "gatePlanSha256",
        "runtimeReadinessSha256", "gateRunSha256", "notBefore",
        "readinessArchiveSha256", "runtimePreflightCapturedAt",
        "authorizationDeadline", "cleanupReserveSeconds", "outerLeasePath",
        "outerLeaseScope", "oneShot", "retryAllowed", "substitutionAllowed",
        "rerandomizationAllowed", "runCount", "cells", "promotionAuthorized",
    }
    if not isinstance(document, dict) or set(document) != keys:
        raise TransportError("runtime package fields differ")
    if (
        type(document["schemaVersion"]) is not int
        or document["schemaVersion"] != 1
        or document["kind"] != PACKAGE_KIND
        or document["target"] != TARGET
        or document["transportUser"] != TRANSPORT_USER
        or document["executionUser"] != EXECUTION_USER
        or document["executionUid"] != EXECUTION_UID
        or document["executionGid"] != EXECUTION_GID
        or document["executionMethod"] != EXECUTION_METHOD
        or COMMIT_RE.fullmatch(str(document["frameworkCommit"])) is None
        or any(
            not isinstance(document[name], str)
            or SHA256_RE.fullmatch(document[name]) is None
            for name in (
                "campaignSha256", "descriptorCanonicalSha256",
                "compiledPlanCanonicalSha256", "gatePlanSha256",
                "runtimeReadinessSha256", "gateRunSha256", "gateSetupSha256",
                "releaseManifestSha256", "bundleSha256", "releaseBindingSha256",
                "readinessArchiveSha256",
            )
        )
        or document["outerLeasePath"] != LEASE_PATH
        or not isinstance(document["setupId"], str)
        or re.fullmatch(r"[0-9a-f]{32}", document["setupId"]) is None
        or document["releaseRoot"] != (
            f"{REMOTE_RELEASES}/{document['setupId']}-"
            f"{document['frameworkCommit'][:12]}-{document['bundleSha256'][:16]}"
        )
        or document["resultsRoot"] != f"{REMOTE_RESULTS}/{document['setupId']}"
        or document["outerLeaseScope"] != OUTER_LEASE_SCOPE
        or document["oneShot"] is not True
        or document["retryAllowed"] is not False
        or document["substitutionAllowed"] is not False
        or document["rerandomizationAllowed"] is not False
        or document["promotionAuthorized"] is not False
        or type(document["cleanupReserveSeconds"]) is not int
        or document["cleanupReserveSeconds"] != 300
        or type(document["runCount"]) is not int
        or document["runCount"] != RUN_COUNT
    ):
        raise TransportError("runtime package identity, boundary, or type differs")
    _timestamp(document["releaseInstalledAt"], "runtime package releaseInstalledAt")
    preflight = _timestamp(
        document["runtimePreflightCapturedAt"],
        "runtime package runtimePreflightCapturedAt",
    )
    not_before = _timestamp(document["notBefore"], "runtime package notBefore")
    deadline = _timestamp(
        document["authorizationDeadline"], "runtime package authorizationDeadline",
    )
    if not_before >= deadline:
        raise TransportError("runtime package authorization interval is empty")
    try:
        campaign_bytes = base64.b64decode(
            document["campaignManifestBase64"], validate=True,
        )
    except (TypeError, ValueError) as exc:
        raise TransportError("runtime package campaign manifest is not base64") from exc
    campaign = strict_json(campaign_bytes, "runtime package campaign manifest")
    campaign_keys = {
        "schemaVersion", "contract", "kind", "studyEpoch", "descriptorId",
        "descriptorCanonicalSha256", "descriptorBytesSha256",
        "compiledPlanCanonicalSha256", "compiledPlanBytesSha256",
        "scheduleVersion", "selectorDigests", "schedules", "runs", "runCount",
        "maximumEvidenceLabel", "canonical", "promotionAuthorized",
        "runtimeEnabledByThisManifest",
    }
    if (
        hashlib.sha256(campaign_bytes).hexdigest() != document["campaignSha256"]
        or set(campaign) != campaign_keys
        or type(campaign.get("schemaVersion")) is not int
        or campaign.get("schemaVersion") != 1
        or campaign.get("contract") != "teastore-candidate-pilot-evidence-v1"
        or campaign.get("kind") != "candidate-pilot-campaign"
        or campaign.get("studyEpoch") != EPOCH["studyEpoch"]
        or not isinstance(campaign.get("descriptorId"), str)
        or campaign.get("descriptorCanonicalSha256")
        != document["descriptorCanonicalSha256"]
        or campaign.get("compiledPlanCanonicalSha256")
        != document["compiledPlanCanonicalSha256"]
        or any(
            not isinstance(campaign.get(name), str)
            or SHA256_RE.fullmatch(campaign[name]) is None
            for name in ("descriptorBytesSha256", "compiledPlanBytesSha256")
        )
        or campaign.get("scheduleVersion") != EPOCH["scheduleVersion"]
        or not isinstance(campaign.get("selectorDigests"), dict)
        or not isinstance(campaign.get("schedules"), dict)
        or campaign.get("runCount") != RUN_COUNT
        or campaign.get("maximumEvidenceLabel") != "candidate-evidence"
        or campaign.get("canonical") is not False
        or campaign.get("runtimeEnabledByThisManifest") is not False
        or campaign.get("promotionAuthorized") is not False
    ):
        raise TransportError("runtime package campaign manifest binding differs")
    _safe(document["campaignId"], "campaign ID")
    cells = document["cells"]
    if not isinstance(cells, list) or len(cells) != RUN_COUNT:
        raise TransportError(f"runtime package must contain exactly {RUN_COUNT} cells")
    campaign_runs = campaign.get("runs")
    if not isinstance(campaign_runs, list) or len(campaign_runs) != RUN_COUNT:
        raise TransportError(f"embedded campaign must contain exactly {RUN_COUNT} run rows")
    cell_keys = {
        "schemaVersion", "contract", "campaignId", "campaignSha256",
        "gatePlanSha256", "runtimeReadinessSha256", "gateRunSha256",
        "frameworkCommit", "descriptorCanonicalSha256",
        "compiledPlanCanonicalSha256", "runId", "runKey", "ordinalPosition",
        "compiledArtifactRoot", "coldStart", "target", "runtimeInputs",
        "workload", "posture", "window", "faultGroundTruth",
        "pathGroundTruth", "attemptPolicy", "requiredArtifacts", "terminalPolicy",
    }
    campaign_row_keys = {
        "studyEpoch", "regime", "block", "posture", "attempt", "ordinal",
        "runId", "compiledArtifactRoot", "path",
    }
    run_ids: list[str] = []
    roots: list[str] = []
    if len(cells) != len(campaign_runs):
        raise TransportError("runtime cells and frozen campaign rows differ in length")
    for index, (cell, campaign_row) in enumerate(zip(cells, campaign_runs)):
        if not isinstance(cell, dict) or set(cell) != cell_keys:
            raise TransportError(f"runtime cell {index} is not an object")
        if not isinstance(campaign_row, dict) or set(campaign_row) != campaign_row_keys:
            raise TransportError(f"campaign run row {index} fields differ")
        expected_run_key = {
            key: campaign_row[key]
            for key in ("studyEpoch", "regime", "block", "posture", "attempt")
        }
        if (
            type(cell.get("schemaVersion")) is not int
            or cell.get("schemaVersion") != 1
            or cell.get("contract") != "teastore-candidate-cell-invocation-v1"
            or cell.get("coldStart") is not True
            or not _same(cell.get("runKey"), expected_run_key)
            or cell.get("runId") != campaign_row["runId"]
            or cell.get("compiledArtifactRoot") != campaign_row["compiledArtifactRoot"]
            or cell.get("ordinalPosition") != campaign_row["ordinal"]
        ) or (
            cell.get("campaignId") != document["campaignId"]
            or cell.get("frameworkCommit") != document["frameworkCommit"]
            or cell.get("campaignSha256") != document["campaignSha256"]
            or cell.get("descriptorCanonicalSha256")
            != document["descriptorCanonicalSha256"]
            or cell.get("compiledPlanCanonicalSha256")
            != document["compiledPlanCanonicalSha256"]
            or cell.get("gatePlanSha256") != document["gatePlanSha256"]
            or cell.get("runtimeReadinessSha256")
            != document["runtimeReadinessSha256"]
            or cell.get("gateRunSha256") != document["gateRunSha256"]
        ):
            raise TransportError(f"runtime cell {index} binding differs")
        run_id = _safe_relative_identifier(
            cell.get("runId"), f"runtime cell {index} runId",
        )
        ordinal = cell.get("ordinalPosition")
        if type(ordinal) is not int or ordinal not in range(1, EPOCH["maximumOrdinal"] + 1):
            raise TransportError(f"runtime cell {index} ordinal differs")
        compiled_root = _safe_relative_identifier(
            cell.get("compiledArtifactRoot"), f"runtime cell {index} artifact root",
        )
        campaign_path = _safe_relative_identifier(
            campaign_row.get("path"), f"campaign run row {index} path",
        )
        if not campaign_path.startswith(f"runs/{expected_run_key['regime']}/"):
            raise TransportError(f"campaign run row {index} path differs")
        if cell.get("target") != {
            "host": TARGET,
            "transportUser": TRANSPORT_USER,
            "executionUser": document["executionUser"],
            "executionUid": document["executionUid"],
            "executionGid": document["executionGid"],
            "executionMethod": document["executionMethod"],
            "releaseRoot": document["releaseRoot"],
            "resultsRoot": document["resultsRoot"],
            "exclusiveLeasePath": LEASE_PATH,
            "outerLeaseScope": OUTER_LEASE_SCOPE,
        } or cell.get("attemptPolicy") != {
            "attempt": 1,
            "startedBeforeFirstExternalMutation": True,
            "retryAllowed": False,
            "substitutionAllowed": False,
            "rerandomizationAllowed": False,
        } or cell.get("terminalPolicy") != {
            "candidateCellValidationRequired": True,
            "ownedResourcesCleanRequired": True,
            "outerLeaseHeldRequired": True,
            "deadlineControllerSettledRequired": True,
            "promotionAuthorized": False,
        }:
            raise TransportError(f"runtime cell {index} authority boundary differs")
        runtime_inputs = cell.get("runtimeInputs")
        if not isinstance(runtime_inputs, dict) or any(
            runtime_inputs.get(name) != document[name]
            for name in (
                "gateSetupSha256", "releaseManifestSha256", "bundleSha256",
                "releaseBindingSha256", "readinessArchiveSha256",
            )
        ):
            raise TransportError(f"runtime cell {index} release binding differs")
        run_ids.append(run_id)
        roots.append(compiled_root)
    if len(set(run_ids)) != RUN_COUNT or len(set(roots)) != RUN_COUNT:
        raise TransportError("runtime cells repeat identity or artifact root")
    return copy.deepcopy(document)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes


Runner = Callable[[Sequence[str], Optional[bytes]], CommandResult]


def subprocess_runner(argv: Sequence[str], data: bytes | None = None) -> CommandResult:
    try:
        local_home = pwd.getpwuid(os.getuid()).pw_dir
    except KeyError as exc:  # pragma: no cover - local account invariant
        raise TransportError("local transport uid has no passwd home") from exc
    environment = {
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": local_home, "LC_ALL": "C", "LANG": "C",
    }
    # The default OpenSSH client needs the real user home for the configured
    # fb14srv5 alias and may use the caller's already-authorized agent socket.
    # The explicit root@ host operand still overrides a conflicting User line.
    if isinstance(os.environ.get("SSH_AUTH_SOCK"), str):
        environment["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]
    result = subprocess.run(
        list(argv), input=data, capture_output=True, check=False,
        env=environment,
    )
    return CommandResult(result.returncode, result.stdout, result.stderr)


class BoundedSrv5SetupController:
    """Read-only probe plus one exact GATE-SETUP-authorized root bootstrap."""

    def __init__(
        self,
        *,
        bindings: Any,
        runner: Runner = subprocess_runner,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.bindings = bindings
        self.runner = runner
        self.clock = clock
        if COMMIT_RE.fullmatch(str(bindings.framework_commit)) is None or (
            COMMIT_RE.fullmatch(str(bindings.framework_tree)) is None
        ):
            raise TransportError("setup controller framework identity is malformed")

    @property
    def installer_path(self) -> Path:
        return ROOT / REMOTE_INSTALLER

    def probe(self) -> dict[str, Any]:
        """Run the exact installer probe through stdin; it performs no mutation."""

        payload = _regular_payload(self.installer_path, "candidate release installer")
        digest = hashlib.sha256(payload).hexdigest()
        result = self.runner((
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "--",
            f"{TRANSPORT_USER}@{TARGET}", "/usr/bin/python3", "-I", "-", "probe",
            "--probe-sha256", digest,
        ), payload)
        if result.returncode != 0:
            raise TransportError("read-only candidate-v4 target probe failed")
        proof = strict_json(result.stdout, "candidate-v4 target proof")
        try:
            _adapter_module().validate_target_proof(proof, self.bindings)
        except Exception as exc:  # noqa: BLE001 - remote proof must fail closed
            raise TransportError(f"candidate-v4 target proof differs: {exc}") from exc
        return proof

    def setup(
        self,
        *,
        gate_plan_path: Path,
        target_proof_path: Path,
        release_manifest_path: Path,
        gate_setup_path: Path,
        bundle_path: Path,
    ) -> dict[str, Any]:
        """Stage exact inputs only after complete local setup-gate replay."""

        named_paths = {
            "gate-plan": Path(gate_plan_path),
            "target-proof": Path(target_proof_path),
            "release-manifest": Path(release_manifest_path),
            "gate-setup": Path(gate_setup_path),
            "bundle": Path(bundle_path),
            "installer": self.installer_path,
        }
        payloads = {
            name: _regular_payload(path, f"candidate setup {name}")
            for name, path in named_paths.items()
        }
        documents = {
            name: strict_json(payloads[name], f"candidate setup {name}")
            for name in ("gate-plan", "target-proof", "release-manifest", "gate-setup")
        }
        manifest = documents["release-manifest"]
        if manifest.get("bundleSha256") != hashlib.sha256(payloads["bundle"]).hexdigest() or (
            manifest.get("bundleBytes") != len(payloads["bundle"])
        ):
            raise TransportError("candidate setup bundle bytes differ from manifest")
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise TransportError("setup controller clock is not timezone-aware")
        adapter = _adapter_module()
        try:
            setup_sha = adapter.validate_gate_setup(
                documents["gate-setup"], self.bindings, documents["gate-plan"],
                documents["target-proof"], manifest, now=now.astimezone(timezone.utc),
            )
        except Exception as exc:  # noqa: BLE001 - no remote write before this point
            raise TransportError(f"candidate GATE-SETUP replay failed: {exc}") from exc
        setup_id = documents["gate-setup"]["authorization"]["setupId"]
        remote: dict[str, str] = {
            name: f"/root/.obsplacement-candidate-v4-{setup_id}.{name}.pending"
            for name in named_paths
        }
        installer_sha = hashlib.sha256(payloads["installer"]).hexdigest()
        # Every transfer target is derived from the validated 128-bit setup ID.
        # No legacy /home/stig/observability-placement-* root is writable here.
        installer_staged = False
        cleanup_confirmed = False
        try:
            for name in (
                "installer", "gate-plan", "target-proof", "release-manifest",
                "gate-setup", "bundle",
            ):
                copied = self.runner((
                    "scp", "--", str(named_paths[name].resolve()),
                    f"{TRANSPORT_USER}@{TARGET}:{remote[name]}",
                ), None)
                if copied.returncode != 0:
                    raise TransportError(f"candidate setup staging failed for {name}")
                if name == "installer":
                    installer_staged = True
            result = self.runner((
                "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "--",
                f"{TRANSPORT_USER}@{TARGET}", "/usr/bin/python3", "-I", remote["installer"], "setup",
                "--setup-id", setup_id,
                "--gate-plan", remote["gate-plan"],
                "--target-proof", remote["target-proof"],
                "--release-manifest", remote["release-manifest"],
                "--gate-setup", remote["gate-setup"],
                "--bundle", remote["bundle"],
                "--expected-self-sha256", installer_sha,
            ), None)
            if result.returncode != 0:
                try:
                    blocked = strict_json(result.stdout, "blocked release installation")
                except TransportError:
                    blocked = {}
                cleanup = blocked.get("stagingCleanup")
                cleanup_confirmed = (
                    isinstance(cleanup, Mapping)
                    and cleanup.get("schemaVersion") == 1
                    and cleanup.get("kind")
                    == "teastore-candidate-setup-staging-cleanup-v1"
                    and cleanup.get("state") == "clean"
                    and cleanup.get("setupId") == setup_id
                )
                # Carry the installer's own diagnosis outward. Without it a
                # remote refusal is indistinguishable from a transport failure.
                detail = blocked.get("error")
                if not isinstance(detail, str) or not detail:
                    stderr = result.stderr
                    if isinstance(stderr, bytes):
                        stderr = stderr.decode("utf-8", errors="replace")
                    detail = (stderr or "").strip()[-500:] or "no installer diagnosis"
                raise TransportError(
                    f"candidate-v4 exact release installation failed: {detail}"
                )
        except Exception as exc:
            # If the installer itself reached the target, ask that exact byte
            # string to remove only this setup ID's six staging files. Failure
            # remains visible rather than silently blessing debris.
            if installer_staged and not cleanup_confirmed:
                cleanup_result = self.runner((
                    "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "--",
                    f"{TRANSPORT_USER}@{TARGET}", "/usr/bin/python3", "-I", remote["installer"],
                    "cleanup-staging", "--setup-id", setup_id,
                    "--expected-self-sha256", installer_sha,
                ), None)
                if cleanup_result.returncode != 0:
                    raise TransportError(
                        f"{exc}; exact setup staging cleanup was not confirmed"
                    ) from exc
            raise
        receipt = strict_json(result.stdout, "candidate-v4 release install receipt")
        authorization = documents["gate-setup"]["authorization"]
        expected = {
            "schemaVersion": 1,
            "kind": "teastore-candidate-release-install-v1",
            "state": "installed",
            "setupId": setup_id,
            "target": TARGET,
            "transportUser": TRANSPORT_USER,
            "executionUser": authorization["executionUser"],
            "executionUid": authorization["executionUid"],
            "executionGid": authorization["executionGid"],
            "executionMethod": authorization["executionMethod"],
            "frameworkCommit": self.bindings.framework_commit,
            "frameworkTree": self.bindings.framework_tree,
            "bundleSha256": manifest["bundleSha256"],
            "releaseManifestSha256": canonical_sha256(manifest),
            "gateSetupSha256": setup_sha,
            "releaseRoot": authorization["releaseRoot"],
            "resultsRoot": authorization["resultsRoot"],
            "exclusiveLeasePath": LEASE_PATH,
            "controllerDigests": copy.deepcopy(self.bindings.controller_sha256),
            "imageBuildReceiptSha256": receipt.get("imageBuildReceiptSha256"),
            "imageBuild": receipt.get("imageBuild"),
            "activationCompile": expected_activation_compile(),
            "runtimeExecuted": False,
            "promotionAuthorized": False,
        }
        try:
            image_build = _adapter_module().validate_image_build_receipt(
                receipt.get("imageBuild"), setup_id=setup_id,
                framework_commit=self.bindings.framework_commit,
            )
        except Exception as exc:  # noqa: BLE001 - target receipt must replay locally
            raise TransportError(f"candidate image-build receipt differs: {exc}") from exc
        if (
            set(receipt) != set(expected) | {"installedAt"}
            or any(not _same(receipt.get(key), value) for key, value in expected.items())
            or receipt.get("imageBuildReceiptSha256") != canonical_sha256(image_build)
        ):
            raise TransportError("candidate-v4 release install receipt differs")
        _timestamp(receipt.get("installedAt"), "release install receipt installedAt")
        return receipt

    def admit_readiness(
        self,
        *,
        archive_path: Path,
        release_binding: Mapping[str, Any],
        local_output: Path,
    ) -> dict[str, Any]:
        """Run installed readiness replay, then fetch and replay its exact output."""

        archive_payload = _regular_payload(Path(archive_path), "readiness archive")
        if len(archive_payload) > MAX_READINESS_ARCHIVE_BYTES:
            raise TransportError("readiness archive exceeds its byte bound")
        archive_sha = hashlib.sha256(archive_payload).hexdigest()
        release = copy.deepcopy(dict(release_binding))
        setup_id = release.get("setupId")
        if (
            not isinstance(setup_id, str)
            or re.fullmatch(r"[0-9a-f]{32}", setup_id) is None
            or release.get("frameworkCommit") != self.bindings.framework_commit
            or release.get("transportUser") != TRANSPORT_USER
            or release.get("executionUser") != EXECUTION_USER
            or release.get("executionUid") != EXECUTION_UID
            or release.get("executionGid") != EXECUTION_GID
            or release.get("executionMethod") != EXECUTION_METHOD
        ):
            raise TransportError("readiness release binding differs")
        release_sha = canonical_sha256(release)
        installer = f"{release['releaseRoot']}/{REMOTE_INSTALLER}"
        result = self.runner((
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "--",
            f"{TRANSPORT_USER}@{TARGET}", "/usr/bin/python3", "-I", installer,
            "admit-readiness", "--archive-sha256", archive_sha,
            "--setup-id", setup_id,
            "--framework-commit", self.bindings.framework_commit,
            "--release-binding-sha256", release_sha,
        ), archive_payload)
        if result.returncode != 0:
            # Same reason the setup path carries its remote diagnosis: without
            # it a target refusal is indistinguishable from a transport fault.
            stderr = result.stderr
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            try:
                blocked = strict_json(result.stdout, "blocked readiness replay")
            except TransportError:
                blocked = {}
            detail = blocked.get("error") if isinstance(blocked, Mapping) else None
            if not isinstance(detail, str) or not detail:
                detail = (stderr or "").strip()[-500:] or "no installer diagnosis"
            raise TransportError(
                f"installed candidate readiness replay failed: {detail}"
            )
        receipt = strict_json(result.stdout, "installed candidate readiness receipt")
        expected = {
            "schemaVersion": 1,
            "kind": "teastore-candidate-installed-readiness-v1",
            "setupId": setup_id,
            "frameworkCommit": self.bindings.framework_commit,
            "releaseBindingSha256": release_sha,
            "ingressArchiveSha256": archive_sha,
            "captureTreeSha256": receipt.get("captureTreeSha256"),
            "readinessCanonicalSha256": receipt.get("readinessCanonicalSha256"),
            "runtimePreflightSha256": receipt.get("runtimePreflightSha256"),
            "runtimePreflightCapturedAt": receipt.get("runtimePreflightCapturedAt"),
            "readinessRoot": f"{REMOTE_READINESS_CONTROLS}/{setup_id}/{archive_sha[:16]}",
            "validatedAt": receipt.get("validatedAt"),
            "experimentalCellsExecuted": 0,
            "runtimeReady": True,
            "promotionAuthorized": False,
        }
        if (
            not _same(receipt, expected)
            or not isinstance(receipt.get("readinessCanonicalSha256"), str)
            or SHA256_RE.fullmatch(receipt["readinessCanonicalSha256"]) is None
            or not isinstance(receipt.get("runtimePreflightSha256"), str)
            or SHA256_RE.fullmatch(receipt["runtimePreflightSha256"]) is None
            or not isinstance(receipt.get("captureTreeSha256"), str)
            or SHA256_RE.fullmatch(receipt["captureTreeSha256"]) is None
            or receipt["captureTreeSha256"] == archive_sha
        ):
            raise TransportError("installed candidate readiness receipt differs")
        _timestamp(receipt.get("validatedAt"), "installed readiness validatedAt")
        _timestamp(
            receipt.get("runtimePreflightCapturedAt"),
            "installed readiness runtimePreflightCapturedAt",
        )
        local_output = Path(local_output)
        pending = local_output.with_name(f".{local_output.name}.readiness-fetch")
        if (
            local_output.exists() or local_output.is_symlink()
            or pending.exists() or pending.is_symlink()
        ):
            raise TransportError("local readiness output or pending fetch already exists")
        local_output.parent.mkdir(parents=True, exist_ok=True)
        fetched = self.runner((
            "scp", "-r", "--", f"{TRANSPORT_USER}@{TARGET}:{receipt['readinessRoot']}",
            str(pending),
        ), None)
        if fetched.returncode != 0 or not pending.is_dir() or pending.is_symlink():
            raise TransportError("installed readiness result fetch was not complete")
        pending.rename(local_output)
        retained_receipt = strict_json(
            _regular_payload(
                local_output / "readiness-admission.json",
                "fetched readiness admission",
            ),
            "fetched readiness admission",
        )
        readiness = strict_json(
            _regular_payload(local_output / "readiness.json", "fetched readiness"),
            "fetched readiness",
        )
        try:
            local_sha = _adapter_module().validate_readiness(
                readiness, self.bindings, readiness_parent=local_output,
            )
        except Exception as exc:  # noqa: BLE001 - local replay must fail closed
            raise TransportError(f"fetched readiness replay failed: {exc}") from exc
        if (
            retained_receipt != receipt
            or local_sha != receipt["readinessCanonicalSha256"]
            or readiness.get("ingressArchiveSha256") != archive_sha
            or readiness.get("captureTreeSha256") != receipt["captureTreeSha256"]
            or canonical_sha256(readiness.get("runtimePreflight"))
            != receipt["runtimePreflightSha256"]
        ):
            raise TransportError("remote and local readiness replays differ")
        return receipt


def expected_activation_compile() -> dict[str, Any]:
    """Re-derive the compiled activation receipt from this host's own source.

    The target renders .local/compiled/teastore/{aop.xml,manifest.json} into
    the release before sealing it, because that bind source is a build product
    and cannot travel in the Git bundle. Both sides derive it from the same
    committed catalog and goal, so the host can check the target's receipt
    against its own computation rather than trusting the reported digest.
    """

    catalog_path = ROOT / "modules/teastore/activation/catalog.json"
    goal_path = ROOT / "modules/teastore/goals/fault-qualification.json"
    compiler_path = ROOT / "src/obsplacement/selection.py"
    catalog_payload = _regular_payload(catalog_path, "activation catalog")
    goal_payload = _regular_payload(goal_path, "activation goal")
    specification = importlib.util.spec_from_file_location(
        "candidate_v4_selection_host", compiler_path,
    )
    if specification is None or specification.loader is None:
        raise TransportError("activation selection compiler is not importable")
    compiler = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(compiler)
    catalog = json.loads(catalog_payload)
    requested = json.loads(goal_payload)["logicalSensors"]
    all_sensors = [row["id"] for row in catalog.get("logicalSensors", [])]
    # Mirror of candidate_release_installer.ACTIVATION_OUTPUTS: the two sides
    # must agree byte for byte, so the posture table is duplicated rather than
    # imported across the host/target boundary.
    wanted = {"selected": requested, "full": all_sensors, "none": []}
    selection_ids = {
        "selected": "fault-qualification", "full": "catalog-all", "none": "catalog-empty",
    }
    postures = {}
    for posture, sensors in wanted.items():
        compiled = compiler.compile_selection(catalog, sensors)
        manifest_bytes = (
            json.dumps(compiled, indent=2, sort_keys=True, allow_nan=False).encode()
            + b"\n"
        )
        postures[posture] = {
            "selectionId": selection_ids[posture],
            "goalLogicalSensors": sorted(sensors),
            "manifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "aopSha256": hashlib.sha256(compiler.render_aop(compiled).encode()).hexdigest(),
            "selectedActivationGroups": list(compiled["selectedActivationGroups"]),
        }
    return {
        "schemaVersion": 2,
        "catalogSha256": hashlib.sha256(catalog_payload).hexdigest(),
        "goalSha256": hashlib.sha256(goal_payload).hexdigest(),
        "postures": postures,
    }


def campaign_unit_name(
    campaign_id: str, setup_id: str, package_sha256: str,
) -> str:
    """Mirror the installer's per-attempt transient unit name.

    Kept byte-identical to _campaign_unit_name in candidate_release_installer;
    the two cannot import each other because one only ever runs on the target.
    A test pins them together so this copy cannot drift.
    """

    digest = hashlib.sha256(b"\0".join(
        value.encode("ascii") for value in (campaign_id, setup_id, package_sha256)
    )).hexdigest()
    return "teastore-candidate-v4-" + digest[:32]


def _remote_diagnosis(result: Any) -> str:
    """Carry the remote's own refusal outward instead of a generic message.

    The installer prints {"error": ..., "state": "blocked"} on stdout and exits
    non-zero. Dropping it turned every remote refusal into an indistinguishable
    transport failure, which is what made the campaign undebuggable.
    """

    for stream in (getattr(result, "stdout", None), getattr(result, "stderr", None)):
        if isinstance(stream, bytes):
            stream = stream.decode("utf-8", errors="replace")
        if not stream:
            continue
        try:
            document = json.loads(stream)
        except ValueError:
            continue
        if isinstance(document, dict) and isinstance(document.get("error"), str):
            return document["error"]
    for stream in (getattr(result, "stderr", None), getattr(result, "stdout", None)):
        if isinstance(stream, bytes):
            stream = stream.decode("utf-8", errors="replace")
        if stream and stream.strip():
            return stream.strip()[-500:]
    return "no remote diagnosis"


class BoundedSrv5CampaignController:
    """Launch one exact package through the installed, gate-bound root wrapper."""

    def __init__(
        self,
        *,
        framework_commit: str,
        release_binding: Mapping[str, Any],
        runner: Runner = subprocess_runner,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if COMMIT_RE.fullmatch(framework_commit) is None:
            raise TransportError("framework commit must be one full Git object")
        self.framework_commit = framework_commit
        self.release_binding = copy.deepcopy(dict(release_binding))
        self.runner = runner
        self.clock = clock

    def describe(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "contract": TRANSPORT_CONTRACT,
            "target": TARGET,
            "transportUser": TRANSPORT_USER,
            "executionUser": self.release_binding.get("executionUser"),
            "executionMethod": self.release_binding.get("executionMethod"),
            "releaseRoot": self.release_binding.get("releaseRoot"),
            "resultsRoot": self.release_binding.get("resultsRoot"),
            "evidenceLabel": "candidate-evidence",
            "outerLeasePath": LEASE_PATH,
            "outerLeaseScope": OUTER_LEASE_SCOPE,
            "deadlineEnforced": True,
            "cleanupEnforced": True,
            "candidateDescriptorAccepted": True,
        }

    def _load_package(
        self, package_path: Path, *, require_fresh_execution_window: bool,
    ) -> tuple[dict[str, Any], bytes]:
        path = Path(package_path)
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise TransportError("runtime package is not a regular non-symlink file")
        payload = path.read_bytes()
        after = path.lstat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise TransportError("runtime package changed while being read")
        package = validate_runtime_package(strict_json(payload, "runtime package"))
        if package["frameworkCommit"] != self.framework_commit:
            raise TransportError("runtime package commit differs from controller release")
        if require_fresh_execution_window:
            now = self.clock()
            if (
                not isinstance(now, datetime)
                or now.tzinfo is None
                or now.utcoffset() is None
            ):
                raise TransportError("bounded transport clock is not timezone-aware")
            now = now.astimezone(timezone.utc)
            not_before = _timestamp(package["notBefore"], "runtime package notBefore")
            deadline = _timestamp(
                package["authorizationDeadline"],
                "runtime package authorizationDeadline",
            )
            if now < not_before or math.floor((deadline - now).total_seconds()) < (
                MINIMUM_FIRST_MUTATION_SECONDS
            ):
                raise TransportError(
                    "runtime authorization window is not open or is too short before transfer"
                )
        expected_release = {
            key: package[key] for key in (
                "setupId", "target", "transportUser", "executionUser",
                "executionUid", "executionGid", "executionMethod", "frameworkCommit",
                "bundleSha256", "releaseManifestSha256", "gateSetupSha256",
                "releaseRoot", "resultsRoot", "outerLeasePath",
            )
        }
        observed_release = {
            key: self.release_binding.get(key) for key in expected_release
        }
        observed_release["outerLeasePath"] = self.release_binding.get(
            "exclusiveLeasePath"
        )
        if not _same(observed_release, expected_release) or canonical_sha256(
            self.release_binding
        ) != package["releaseBindingSha256"]:
            raise TransportError("installed release binding differs before launch")
        return package, payload

    @staticmethod
    def _remote_output(package: Mapping[str, Any]) -> str:
        return f"{package['resultsRoot']}/{package['campaignId']}"

    def _status(
        self, package: Mapping[str, Any], package_sha256: str,
    ) -> dict[str, Any]:
        installer = f"{package['releaseRoot']}/{REMOTE_INSTALLER}"
        result = self.runner((
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "--",
            f"{TRANSPORT_USER}@{TARGET}", "/usr/bin/python3", "-I", installer,
            "campaign-status", "--setup-id", package["setupId"],
            "--campaign-id", package["campaignId"],
            "--package-sha256", package_sha256,
            "--release-binding-sha256", package["releaseBindingSha256"],
        ), None)
        if result.returncode != 0:
            raise TransportError(
                f"candidate remote status is unavailable: {_remote_diagnosis(result)}"
            )
        status_document = strict_json(result.stdout, "candidate remote status")
        expected_keys = {
            "schemaVersion", "kind", "setupId", "campaignId", "packageSha256",
            "state", "leaseHeld", "resultExists", "journalRows",
            "hostLeaseHeld",
            "terminalExists", "abortExists", "promotionAuthorized",
            "systemdState",
            "leaseReceiptSha256",
        }
        if (
            set(status_document) != expected_keys
            or status_document.get("schemaVersion") != 1
            or status_document.get("kind") != "teastore-candidate-remote-status-v1"
            or status_document.get("setupId") != package["setupId"]
            or status_document.get("campaignId") != package["campaignId"]
            or status_document.get("packageSha256") != package_sha256
            or status_document.get("state") not in {
                "not-started", "staged", "running", "stopped", "complete",
            }
            or type(status_document.get("leaseHeld")) is not bool
            or type(status_document.get("hostLeaseHeld")) is not bool
            or type(status_document.get("resultExists")) is not bool
            or type(status_document.get("journalRows")) is not int
            or not 0 <= status_document["journalRows"] <= RUN_COUNT
            or type(status_document.get("terminalExists")) is not bool
            or type(status_document.get("abortExists")) is not bool
            or not isinstance(status_document.get("systemdState"), dict)
            or set(status_document["systemdState"]) != {
                "unitName", "loadState", "activeState", "subState", "result",
                "execMainStatus", "rawSha256",
            }
            or status_document["systemdState"].get("unitName") != campaign_unit_name(
                package["campaignId"], package["setupId"], package_sha256,
            )
            or status_document["systemdState"].get("loadState") not in {
                "loaded", "not-found",
            }
            # "not-found" is only ever the never-launched reading, so it is
            # admitted solely with the full shape of a campaign that has left
            # no trace at all. Anything that ran must still show a loaded unit.
            or (
                status_document["systemdState"].get("loadState") == "not-found"
                and (
                    status_document["state"] not in {"not-started", "staged"}
                    or status_document["resultExists"] is not False
                    or status_document["journalRows"] != 0
                    or status_document["leaseHeld"] is not False
                    or status_document["hostLeaseHeld"] is not False
                    or status_document["terminalExists"] is not False
                    or status_document["abortExists"] is not False
                    or status_document["leaseReceiptSha256"] is not None
                )
            )
            or status_document["systemdState"].get("activeState") not in {
                "active", "inactive", "failed",
            }
            or type(status_document["systemdState"].get("execMainStatus")) is not int
            or not isinstance(status_document["systemdState"].get("rawSha256"), str)
            or SHA256_RE.fullmatch(status_document["systemdState"]["rawSha256"]) is None
            or (
                status_document.get("leaseReceiptSha256") is not None
                and (
                    not isinstance(status_document["leaseReceiptSha256"], str)
                    or SHA256_RE.fullmatch(status_document["leaseReceiptSha256"]) is None
                )
            )
            or (
                status_document.get("leaseReceiptSha256") is None
                and status_document.get("abortExists") is not True
                # A campaign whose unit never existed has no lease to receipt
                # for; the not-found shape above already pins that case.
                and status_document["systemdState"].get("loadState") != "not-found"
            )
            or status_document.get("promotionAuthorized") is not False
            or (status_document["state"] == "running")
            is not status_document["leaseHeld"]
            or (status_document["state"] == "running")
            is not (status_document["systemdState"]["activeState"] == "active")
            or (status_document["state"] == "complete" and (
                status_document["systemdState"]["result"] != "success"
                or status_document["systemdState"]["execMainStatus"] != 0
            ))
            or (status_document["state"] == "complete" and (
                not status_document["resultExists"]
                or not status_document["terminalExists"]
                or status_document["abortExists"]
                or status_document["journalRows"] != RUN_COUNT
            ))
        ):
            raise TransportError("candidate remote status identity or state differs")
        return status_document

    def status(self, package_path: Path) -> dict[str, Any]:
        """Read one campaign state; this never resumes or authorizes execution."""

        package, payload = self._load_package(
            package_path, require_fresh_execution_window=False,
        )
        return self._status(package, hashlib.sha256(payload).hexdigest())

    def _fetch(
        self,
        package: Mapping[str, Any],
        *,
        status_document: Mapping[str, Any],
        local_output: Path,
    ) -> dict[str, Any] | None:
        if status_document.get("state") not in {"complete", "stopped"} or (
            status_document.get("resultExists") is not True
        ):
            raise TransportError("candidate result is not terminal and cannot be fetched")
        campaign = package["campaignId"]
        remote_output = self._remote_output(package)
        local_output = Path(local_output)
        local_pending = local_output.with_name(f".{local_output.name}.fetch-{campaign}")
        if (
            local_output.exists() or local_output.is_symlink()
            or local_pending.exists() or local_pending.is_symlink()
        ):
            raise TransportError("local candidate result or fetch root already exists")
        local_output.parent.mkdir(parents=True, exist_ok=True)
        fetch_result = self.runner((
            "scp", "-r", "--", f"{TRANSPORT_USER}@{TARGET}:{remote_output}",
            str(local_pending),
        ), None)
        fetched = fetch_result.returncode == 0 and local_pending.is_dir() and (
            not local_pending.is_symlink()
        )
        if not fetched:
            raise TransportError("terminal candidate result fetch was not complete")
        local_pending.rename(local_output)
        if status_document["state"] == "complete":
            return replay_fetched_campaign(local_output, package)
        if status_document.get("abortExists") is True:
            return validate_fetched_abort(
                local_output, package,
                package_sha256=status_document["packageSha256"],
            )
        return None

    def refetch(self, package_path: Path, *, local_output: Path) -> dict[str, Any]:
        """Status then fetch a terminal result after an SSH interruption."""

        package, payload = self._load_package(
            package_path, require_fresh_execution_window=False,
        )
        status_document = self._status(package, hashlib.sha256(payload).hexdigest())
        replay = self._fetch(
            package, status_document=status_document, local_output=local_output,
        )
        return {"status": status_document, "localReplay": replay}

    def launch(self, package_path: Path, *, local_output: Path) -> dict[str, Any]:
        """Launch once, then fetch and locally replay the terminal result tree."""

        package, payload = self._load_package(
            package_path, require_fresh_execution_window=True,
        )
        campaign = package["campaignId"]
        package_sha = hashlib.sha256(payload).hexdigest()
        remote_output = self._remote_output(package)
        installer = f"{package['releaseRoot']}/{REMOTE_INSTALLER}"
        launch_result = self.runner((
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "--",
            f"{TRANSPORT_USER}@{TARGET}", "/usr/bin/python3", "-I", installer,
            "launch-campaign", "--package-sha256", package_sha,
            "--output", remote_output, "--framework-commit", self.framework_commit,
            "--release-binding-sha256", package["releaseBindingSha256"],
        ), payload)
        try:
            status_document = self._status(package, package_sha)
        except TransportError as exc:
            if launch_result.returncode != 0:
                # Refusing to relaunch stays correct -- a non-zero rc can still
                # mean SSH died after the unit started -- but the remote's own
                # words have to come out with it. Without them this message
                # described a running campaign that had in fact never started.
                raise TransportError(
                    "launch transport ended without terminal status; the remote may still "
                    "be running, so use status/refetch and do not launch again. "
                    f"Remote launch said: {_remote_diagnosis(launch_result)}"
                ) from exc
            raise
        if status_document["state"] in {"staged", "running"}:
            if launch_result.returncode != 0:
                raise TransportError(
                    "launch transport ended while the remote is still running or staged; "
                    "use status/refetch and do not relaunch"
                )
            receipt = strict_json(launch_result.stdout, "remote start receipt")
            expected_start_keys = {
                "schemaVersion", "kind", "campaignId", "frameworkCommit",
                "packageSha256", "unitName", "state", "promotionAuthorized",
            }
            if (
                set(receipt) != expected_start_keys
                or receipt.get("schemaVersion") != 1
                or receipt.get("kind") != "teastore-candidate-remote-start-v1"
                or receipt.get("campaignId") != campaign
                or receipt.get("frameworkCommit") != self.framework_commit
                or receipt.get("packageSha256") != package_sha
                or not isinstance(receipt.get("unitName"), str)
                or not receipt["unitName"].startswith("teastore-candidate-v4-")
                or receipt.get("state") != "started"
                or receipt.get("promotionAuthorized") is not False
            ):
                raise TransportError("detached remote start receipt differs")
            return receipt
        replay = self._fetch(
            package, status_document=status_document, local_output=local_output,
        )
        if status_document["state"] == "stopped":
            raise TransportError("remote candidate stopped; failure results retained locally")
        if replay is None:  # pragma: no cover - complete status always replays
            raise TransportError("terminal candidate result was not locally replayed")
        if launch_result.returncode == 0:
            receipt = strict_json(launch_result.stdout, "remote launch receipt")
        else:
            # An SSH channel can fail after the remote completed. The retained
            # terminal tree plus independent local replay is the recovery
            # authority; this reconstructed receipt is fully byte-bound.
            receipt = {
                "schemaVersion": 1,
                "kind": "teastore-candidate-remote-launch-v1",
                "campaignId": campaign,
                "frameworkCommit": self.framework_commit,
                "packageSha256": package_sha,
                "runCount": RUN_COUNT,
                "state": "complete",
                "promotionAuthorized": False,
            }
        if receipt != {
            "schemaVersion": 1,
            "kind": "teastore-candidate-remote-launch-v1",
            "campaignId": campaign,
            "frameworkCommit": self.framework_commit,
            "packageSha256": package_sha,
            "runCount": RUN_COUNT,
            "state": "complete",
            "promotionAuthorized": False,
        }:
            raise TransportError("remote launch receipt identity or state differs")
        return receipt


__all__ = [
    "BoundedSrv5CampaignController", "BoundedSrv5SetupController",
    "ABORT_KIND", "CommandResult", "PACKAGE_KIND", "TRANSPORT_CONTRACT",
    "TransportError",
    "build_capture_spec", "build_release_bundle", "build_runtime_package",
    "canonical_sha256", "replay_fetched_campaign", "strict_json",
    "subprocess_runner", "validate_fetched_abort", "validate_runtime_package",
]
