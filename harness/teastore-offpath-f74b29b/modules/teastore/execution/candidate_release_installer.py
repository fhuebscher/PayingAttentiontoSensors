#!/usr/bin/env python3
"""Root transport wrapper for TeaStore candidate-v4 setup and launch.

The working SSH identity on fb14srv5 is root.  This wrapper makes that fact
explicit, limits root to exact setup/package installation and user handoff, and
never accepts a shell command.  A setup gate authorizes zero experimental
cells; a later package contains the fresh GATE-RUN binding consumed by the
installed candidate controller.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import math
import os
import pwd
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import io
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, NoReturn, Sequence


TARGET = "fb14srv5"
TARGET_HOSTNAME = "fb14srv5.<redacted-domain>"
TARGET_MACHINE_ID_SHA256 = "c43aa7be531dd44146e45811b3aa5b796df1945e346164529c205d7f4d559773"
TRANSPORT_USER = "root"
EXECUTION_USER = "stig"
EXECUTION_UID = 1015
EXECUTION_GID = 1015
EXECUTION_DOCKER_GID = 999
EXECUTION_METHOD = "runuser"
SETUP_KIND = "teastore-candidate-gate-setup-v1"
TARGET_PROOF_KIND = "teastore-candidate-target-proof-v1"
RELEASE_MANIFEST_KIND = "teastore-candidate-release-manifest-v1"
RELEASE_INSTALL_KIND = "teastore-candidate-release-install-v1"
PACKAGE_KIND = "teastore-candidate-runtime-package-v1"
CANDIDATE_V4_ROOT = Path(
    "/home/stig/.local/share/observability-placement/candidate-v4/teastore"
)
RELEASES_ROOT = CANDIDATE_V4_ROOT / "releases"
RESULTS_ROOT = CANDIDATE_V4_ROOT / "results"
RECEIPTS_ROOT = CANDIDATE_V4_ROOT / "receipts"
LEASE_PATH = CANDIDATE_V4_ROOT / "leases/host-exclusive.lock"
READINESS_CONTROL_ROOT = Path(
    "/var/lib/observability-placement/candidate-v4/teastore/readiness"
)
REMOTE_CONTROLLER = "modules/teastore/execution/candidate_remote_controller.py"
REMOTE_INSTALLER = "modules/teastore/execution/candidate_release_installer.py"
# The one declaration of what the release binding covers. This literal used to
# be repeated at four sites in this module alone, plus one in the runtime
# adapter and one in the transport, and every added field had to be edited into
# all six by hand or the binding digest silently stopped matching.
RELEASE_BINDING_KEYS = frozenset({
    "setupId", "target", "transportUser", "executionUser", "executionUid",
    "executionGid", "executionMethod", "frameworkCommit", "frameworkTree",
    "bundleSha256", "releaseManifestSha256", "gateSetupSha256", "releaseRoot",
    "resultsRoot", "exclusiveLeasePath", "controllerDigests",
    "imageBuildReceiptSha256", "imageBuild", "activationCompile", "installedAt",
})
# The selected posture binds this compiled AspectJ config into five containers.
# It is a build product, so it is absent from the Git bundle the release is
# built from, and the installer has to produce it before the tree is sealed.
ACTIVATION_CATALOG = "modules/teastore/activation/catalog.json"
ACTIVATION_GOAL = "modules/teastore/goals/fault-qualification.json"
ACTIVATION_SELECTION_ID = "fault-qualification"
ACTIVATION_COMPILER = "src/obsplacement/selection.py"
ACTIVATION_OUTPUT_DIR = ".local/compiled/teastore"
# F-ADH-072: every posture is rendered by the same compiler from the same
# catalog, so the lattice nests at the join point and not merely at the
# activation-group label. `full` is the whole catalog, `none` the empty
# selection (which renders "weave nothing"), `selected` the goal's sensors.
ACTIVATION_OUTPUTS = {
    "selected": (ACTIVATION_SELECTION_ID, "manifest.json", "aop.xml"),
    "full": ("catalog-all", "full.manifest.json", "full.aop.xml"),
    "none": ("catalog-empty", "none.manifest.json", "none.aop.xml"),
}
# Third-party modules the runtime imports on the target, as the execution user.
# The repository still declares no requirements.txt or pyproject.toml, so this
# is the only place the target dependency contract is written down.
RUNTIME_PYTHON_MODULES = ("jsonschema", "pika", "yaml")
RUNUSER = "/sbin/runuser"
SYSTEMD_RUN = "/usr/bin/systemd-run"
SYSTEMCTL_CANDIDATES = ("/bin/systemctl", "/usr/bin/systemctl")


def _systemctl() -> str:
    """Resolve systemctl among fixed absolute candidates, lazily.

    PATH is never consulted and each candidate must be a root-owned regular
    executable, so no writable directory can substitute a binary. Split-usr
    hosts such as this Debian target keep systemctl in /bin and have no
    /usr/bin/systemctl at all, while merged-usr hosts expose both. Resolution
    is lazy because this module is also imported on developer machines that
    have neither, and an import-time probe would break them.
    """
    for candidate in SYSTEMCTL_CANDIDATES:
        try:
            info = os.lstat(candidate)
        except OSError:
            continue
        if (
            stat.S_ISREG(info.st_mode)
            and info.st_uid == 0
            and os.access(candidate, os.X_OK)
        ):
            return candidate
    raise InstallError(
        f"no root-owned systemctl among {list(SYSTEMCTL_CANDIDATES)}"
    )
TARGET_PYTHON = "/usr/bin/python3"
SETUP_ID_RE = re.compile(r"^[0-9a-f]{32}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CAMPAIGN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
ALLOWED_SETUP_ACTIONS = [
    "install-exact-release",
    "build-and-inspect-patched-images",
    "collect-runtime-readiness",
    "cleanup-readiness-resources",
    "remove-setup-staging",
]
MAX_READINESS_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_READINESS_MEMBERS = 2048
PROJECT_PREFIX = "teastore_candidate_"
RESERVED_PORTS = (3306, 5672, 8080, 8082, 15672)
DOCKER_SERVER_VERSION = "29.6.1"
SOURCE_COMMIT = "34b37f7e7be433ce72d5f9455e66922a13116749"
PATCH_SHA256 = "2199c0f6e9ab1098afcac3c6b5a68d7860ad1b94b70019d790862eb1a7d60094"
IMAGE_BUILD_KIND = "teastore-candidate-patched-image-build-v1"
MAVEN_COMMAND = (
    "mvn", "-B", "-ntp", "-pl",
    "utilities/tools.descartes.teastore.registryclient,"
    "services/tools.descartes.teastore.webui,"
    "services/tools.descartes.teastore.auth,"
    "services/tools.descartes.teastore.persistence",
    "-am", "clean", "verify",
)
RUNTIME_IMAGES = {
    "registry": "descartesresearch/teastore-registry",
    "db": "descartesresearch/teastore-db",
    "persistence": "descartesresearch/teastore-persistence",
    "auth": "descartesresearch/teastore-auth",
    "image": "descartesresearch/teastore-image",
    "recommender": "descartesresearch/teastore-recommender",
    "webui": "descartesresearch/teastore-webui",
    "rabbitmq": "rabbitmq:3-management",
}
PATCHED_IMAGE_INPUTS = {
    "auth": {
        "artifactPath": (
            "services/tools.descartes.teastore.auth/target/"
            "tools.descartes.teastore.auth.war"
        ),
        "dockerfilePath": "modules/teastore/images/Dockerfile.auth",
        "outputRepository": "observability-placement/teastore-auth-witness",
        "overlayPath": "/usr/local/tomcat/webapps/tools.descartes.teastore.auth.war",
        "serviceClass": (
            "WEB-INF/classes/tools/descartes/teastore/auth/rest/"
            "AuthUserActionsRest.class"
        ),
        "markers": (b"login-persistence-request", b"emitNativeTraceBridge"),
    },
    "persistence": {
        "artifactPath": (
            "services/tools.descartes.teastore.persistence/target/"
            "tools.descartes.teastore.persistence.war"
        ),
        "dockerfilePath": "modules/teastore/images/Dockerfile.persistence",
        "outputRepository": "observability-placement/teastore-persistence-witness",
        "overlayPath": (
            "/usr/local/tomcat/webapps/tools.descartes.teastore.persistence.war"
        ),
        "serviceClass": (
            "WEB-INF/classes/tools/descartes/teastore/persistence/rest/"
            "UserEndpoint.class"
        ),
        "markers": (b"login-user-lookup",),
    },
    "webui": {
        "artifactPath": (
            "services/tools.descartes.teastore.webui/target/"
            "tools.descartes.teastore.webui.war"
        ),
        "dockerfilePath": "modules/teastore/images/Dockerfile.webui",
        "outputRepository": "observability-placement/teastore-webui-witness",
        "overlayPath": (
            "/usr/local/tomcat/webapps/tools.descartes.teastore.webui.war"
        ),
        "serviceClass": (
            "WEB-INF/classes/tools/descartes/teastore/webui/servlet/"
            "LoginActionServlet.class"
        ),
        "markers": (b"X-Observability-Journey-Id",),
    },
}


class InstallError(ValueError):
    """A target identity, release, setup gate, or launch boundary differs."""


def _reject_constant(value: str) -> NoReturn:
    raise InstallError(f"non-finite JSON value is forbidden: {value}")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InstallError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, allow_nan=False, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InstallError(f"value is not canonical JSON: {exc}") from exc


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _json_bytes(payload: bytes, where: str) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_no_duplicates, parse_constant=_reject_constant,
        )
    except InstallError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InstallError(f"invalid JSON in {where}: {exc}") from exc
    if not isinstance(value, dict):
        raise InstallError(f"{where} must contain one object")
    return value


def _regular_bytes(path: Path, where: str) -> bytes:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise InstallError(f"{where} is not a regular non-symlink file")
        payload = path.read_bytes()
        after = path.lstat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ) or len(payload) != before.st_size:
            raise InstallError(f"{where} changed while being read")
        return payload
    except InstallError:
        raise
    except OSError as exc:
        raise InstallError(f"cannot read {where}: {exc}") from exc


def _json_file(path: Path, where: str) -> tuple[dict[str, Any], bytes]:
    payload = _regular_bytes(path, where)
    return _json_bytes(payload, where), payload


def _exact(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise InstallError(f"{where} fields differ")
    return value


def _timestamp(value: Any, where: str) -> datetime:
    if not isinstance(value, str):
        raise InstallError(f"{where} is not a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InstallError(f"{where} is not ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InstallError(f"{where} has no UTC offset")
    return parsed.astimezone(timezone.utc)


def _run(
    argv: Sequence[str], *, cwd: Path | None = None, timeout: float | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            list(argv), cwd=cwd, check=False, capture_output=True, timeout=timeout,
            env={
                "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin",
                "HOME": "/nonexistent-candidate-v4-installer",
                "LC_ALL": "C", "LANG": "C", "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0", "GIT_NO_REPLACE_OBJECTS": "1",
            },
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            list(argv), 124, exc.stdout or b"", exc.stderr or b"timeout",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallError(f"fixed argv failed to start: {argv[0]}: {exc}") from exc


def _require_root_transport() -> None:
    try:
        observed = pwd.getpwuid(os.geteuid()).pw_name
    except KeyError as exc:
        raise InstallError("transport uid has no passwd identity") from exc
    if os.geteuid() != 0 or observed != TRANSPORT_USER:
        raise InstallError("candidate-v4 bootstrap did not execute as bound root transport")


def _docker_probe(user: str) -> tuple[bool, int]:
    command = ["docker", "info", "--format", "{{.ServerVersion}}"]
    if user == "stig":
        command = [RUNUSER, "--user", "stig", "--", *command]
    result = _run(command)
    return result.returncode == 0, result.returncode


def _legacy_root(path: Path, stig: pwd.struct_passwd) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {
            "path": str(path), "exists": False, "ownerUid": None,
            "ownerGid": None, "mode": None, "accessibleByStig": False,
        }
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise InstallError(f"legacy root is a symlink or non-directory: {path}")
    mode = stat.S_IMODE(metadata.st_mode)
    permitted = bool(
        (metadata.st_uid == stig.pw_uid and mode & stat.S_IXUSR)
        or (metadata.st_gid == stig.pw_gid and mode & stat.S_IXGRP)
        or mode & stat.S_IXOTH
    )
    return {
        "path": str(path), "exists": True, "ownerUid": metadata.st_uid,
        "ownerGid": metadata.st_gid, "mode": f"0{mode:03o}",
        "accessibleByStig": permitted,
    }


def target_proof(*, probe_sha256: str) -> dict[str, Any]:
    """Collect identity/capability facts without changing target state."""

    _require_root_transport()
    if SHA256_RE.fullmatch(probe_sha256) is None:
        raise InstallError("target probe digest is invalid")
    try:
        root_user = pwd.getpwnam("root")
        stig = pwd.getpwnam("stig")
    except KeyError as exc:
        raise InstallError("required root or stig passwd identity is absent") from exc
    root_access, root_rc = _docker_probe("root")
    stig_access, stig_rc = _docker_probe("stig")
    try:
        socket_metadata = Path("/var/run/docker.sock").lstat()
    except OSError as exc:
        raise InstallError(f"Docker socket is unavailable: {exc}") from exc
    if Path("/var/run/docker.sock").is_symlink() or not stat.S_ISSOCK(socket_metadata.st_mode):
        raise InstallError("Docker socket is not a real Unix socket")
    hostname = socket.gethostname()
    fqdn = socket.getfqdn(hostname)
    machine_id = _regular_bytes(Path("/etc/machine-id"), "target machine identity").strip()
    machine_id_sha256 = hashlib.sha256(machine_id).hexdigest()
    if (
        hostname != TARGET
        or fqdn != TARGET_HOSTNAME
        or re.fullmatch(rb"[0-9a-f]{32}", machine_id) is None
        or machine_id_sha256 != TARGET_MACHINE_ID_SHA256
    ):
        raise InstallError("target hostname or machine identity differs")
    return {
        "schemaVersion": 1,
        "kind": TARGET_PROOF_KIND,
        "target": TARGET,
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "probeSha256": probe_sha256,
        "hostIdentity": {
            "hostname": hostname,
            "fqdn": fqdn,
            "machineIdSha256": machine_id_sha256,
        },
        "pythonRuntime": {
            "executable": sys.executable,
            "version": list(sys.version_info[:3]),
            "requiredLanguageVersion": [3, 9],
            "observedTargetPatch": [3, 9, 2],
        },
        "transport": {"user": "root", "uid": 0, "gid": 0},
        "executionCapabilities": {
            "root": {
                "uid": root_user.pw_uid, "gid": root_user.pw_gid,
                "supplementaryGids": sorted(set(os.getgrouplist("root", root_user.pw_gid))),
                "home": root_user.pw_dir, "executionMethod": "direct",
                "dockerAccess": root_access, "dockerProbeExitCode": root_rc,
            },
            "stig": {
                "uid": stig.pw_uid, "gid": stig.pw_gid, "home": stig.pw_dir,
                "supplementaryGids": sorted(set(os.getgrouplist("stig", stig.pw_gid))),
                "executionMethod": "runuser", "dockerAccess": stig_access,
                "dockerProbeExitCode": stig_rc,
            },
        },
        "dockerSocket": {
            "path": "/var/run/docker.sock", "ownerUid": socket_metadata.st_uid,
            "ownerGid": socket_metadata.st_gid, "mode": f"0{stat.S_IMODE(socket_metadata.st_mode):03o}",
        },
        "legacyRoots": [
            _legacy_root(Path("/home/stig/observability-placement-runs"), stig),
            _legacy_root(Path("/home/stig/observability-placement-results"), stig),
        ],
        "candidateV4Root": {
            "path": str(CANDIDATE_V4_ROOT), "exists": CANDIDATE_V4_ROOT.exists(),
        },
    }


def _run_as_execution_user(argv: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    """Run one fixed argv-only read or launch as the admitted execution user."""

    return _run((RUNUSER, "--user", EXECUTION_USER, "--", *argv))


def _image_repository(image: str) -> str:
    tail = image.rsplit("/", 1)[-1]
    return image.rsplit(":", 1)[0] if ":" in tail else image


def _build_command(
    argv: Sequence[str], *, cwd: Path | None, deadline: datetime,
    maximum_seconds: int, cleanup: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    remaining = (deadline - datetime.now(timezone.utc)).total_seconds() - 30
    if not cleanup and remaining <= 0:
        raise InstallError("patched-image setup reached its cleanup reserve")
    timeout = float(maximum_seconds) if cleanup else max(
        1.0, min(float(maximum_seconds), remaining),
    )
    try:
        result = subprocess.run(
            list(argv), cwd=cwd, check=False, capture_output=True,
            timeout=timeout,
            env={
                "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin",
                "HOME": "/home/stig", "LC_ALL": "C", "LANG": "C",
                "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
                "GIT_NO_REPLACE_OBJECTS": "1", "MAVEN_OPTS": "-Duser.home=/home/stig",
            },
        )
    except subprocess.TimeoutExpired as exc:
        raise InstallError(f"patched-image command timed out: {argv[0]}") from exc
    except OSError as exc:
        raise InstallError(f"patched-image command could not start: {argv[0]}: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).decode(
            "utf-8", errors="replace",
        )[:800]
        raise InstallError(
            f"patched-image command failed ({result.returncode}): {argv[0]}: {detail}"
        )
    return result


def _inspect_image(
    image: str, *, deadline: datetime,
) -> tuple[dict[str, Any], subprocess.CompletedProcess[bytes]]:
    result = _build_command(
        ("docker", "image", "inspect", image), cwd=None, deadline=deadline,
        maximum_seconds=120,
    )
    try:
        rows = json.loads(
            result.stdout.decode("utf-8", errors="strict"),
            object_pairs_hook=_no_duplicates, parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InstallError(f"Docker image inspection is invalid: {image}: {exc}") from exc
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise InstallError(f"Docker image inspection cardinality differs: {image}")
    row = rows[0]
    image_id = row.get("Id")
    repo_digests = row.get("RepoDigests") or []
    config = row.get("Config")
    if (
        not isinstance(image_id, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None
        or row.get("Architecture") != "amd64"
        or row.get("Os") != "linux"
        or not isinstance(repo_digests, list)
        or any(
            not isinstance(value, str)
            or re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", value) is None
            for value in repo_digests
        )
        or not isinstance(config, dict)
    ):
        raise InstallError(f"Docker image identity/platform differs: {image}")
    return row, result


def _validate_built_wars(source: Path, contract: Mapping[str, Any]) -> dict[str, Any]:
    registry = contract.get("registryClient")
    services = contract.get("services")
    if not isinstance(registry, Mapping) or not isinstance(services, Mapping) or (
        set(services) != set(PATCHED_IMAGE_INPUTS)
    ):
        raise InstallError("patched-image WAR contract differs")
    registry_entry = registry.get("warEntry")
    registry_classes = registry.get("expectedClasses")
    registry_markers = registry.get("requiredUtf8Markers")
    if (
        not isinstance(registry_entry, str)
        or not isinstance(registry_classes, list)
        or not isinstance(registry_markers, list)
    ):
        raise InstallError("patched registry-client WAR contract differs")
    artifacts: dict[str, Any] = {}
    registry_hashes: set[str] = set()
    for service, expected in PATCHED_IMAGE_INPUTS.items():
        if services.get(service, {}).get("artifactPath") != expected["artifactPath"]:
            raise InstallError(f"patched-image artifact contract differs: {service}")
        war = source / expected["artifactPath"]
        payload = _regular_bytes(war, f"built {service} WAR")
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                if archive.testzip() is not None:
                    raise InstallError(f"built {service} WAR has a bad CRC member")
                names = archive.namelist()
                if len(names) != len(set(names)) or expected["serviceClass"] not in names or (
                    registry_entry not in names
                ):
                    raise InstallError(f"built {service} WAR closure differs")
                service_class = archive.read(expected["serviceClass"])
                if any(marker not in service_class for marker in expected["markers"]):
                    raise InstallError(f"built {service} service markers differ")
                registry_payload = archive.read(registry_entry)
            with zipfile.ZipFile(io.BytesIO(registry_payload)) as nested:
                if nested.testzip() is not None or any(
                    name not in nested.namelist() for name in registry_classes
                ):
                    raise InstallError(f"built {service} registry-client closure differs")
                combined = b"".join(nested.read(name) for name in registry_classes)
                if any(marker.encode("utf-8") not in combined for marker in registry_markers):
                    raise InstallError(f"built {service} registry-client markers differ")
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            raise InstallError(f"built {service} WAR is invalid: {exc}") from exc
        registry_sha = hashlib.sha256(registry_payload).hexdigest()
        registry_hashes.add(registry_sha)
        artifacts[service] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload), "registryClientSha256": registry_sha,
        }
    if len(registry_hashes) != 1:
        raise InstallError("built registry-client bytes differ across patched WARs")
    return artifacts


def _validate_image_build_receipt(
    value: Any, *, setup_id: str, framework_commit: str, release_root: Path,
) -> dict[str, Any]:
    root = _exact(value, {
        "schemaVersion", "kind", "setupId", "target", "executionUser",
        "executionUid", "executionGid", "frameworkCommit", "sourceCommit",
        "patchSha256", "inputContractSha256", "mavenCommand",
        "mavenStdoutSha256", "mavenStderrSha256", "services", "imageDigests",
        "buildStartedAt", "completedAt", "cellsRun", "containersStarted",
        "temporaryContainersRemoved", "ready", "promotionAuthorized",
        "priorDeclaredImageConfigIds", "uniqueBuildTags",
    }, "patched-image build receipt")
    services = root.get("services")
    images = root.get("imageDigests")
    # The contract root is supplied by the caller.  This validator runs both
    # from the installed checkout and from the root staging path, where
    # __file__ has no parents[3] to resolve.
    input_contract_sha256 = hashlib.sha256(_regular_bytes(
        release_root / "modules/teastore/images/patched-image-inputs.json",
        "patched-image input contract",
    )).hexdigest()
    if (
        type(root.get("schemaVersion")) is not int
        or root.get("schemaVersion") != 1
        or root.get("kind") != IMAGE_BUILD_KIND
        or root.get("setupId") != setup_id
        or root.get("target") != TARGET
        or root.get("executionUser") != EXECUTION_USER
        or type(root.get("executionUid")) is not int
        or root.get("executionUid") != EXECUTION_UID
        or type(root.get("executionGid")) is not int
        or root.get("executionGid") != EXECUTION_GID
        or root.get("frameworkCommit") != framework_commit
        or root.get("sourceCommit") != SOURCE_COMMIT
        or root.get("patchSha256") != PATCH_SHA256
        or root.get("inputContractSha256") != input_contract_sha256
        or root.get("mavenCommand") != list(MAVEN_COMMAND)
        or any(
            not isinstance(root.get(key), str) or SHA256_RE.fullmatch(root[key]) is None
            for key in ("mavenStdoutSha256", "mavenStderrSha256")
        )
        or not isinstance(services, dict) or set(services) != set(RUNTIME_IMAGES)
        or not isinstance(images, dict) or set(images) != set(RUNTIME_IMAGES)
        or type(root.get("cellsRun")) is not int
        or root.get("cellsRun") != 0
        or type(root.get("containersStarted")) is not int
        or root.get("containersStarted") != 0
        or root.get("temporaryContainersRemoved") is not True
        or root.get("ready") is not True
        or root.get("promotionAuthorized") is not False
        or not isinstance(root.get("priorDeclaredImageConfigIds"), dict)
        or set(root["priorDeclaredImageConfigIds"]) != set(PATCHED_IMAGE_INPUTS)
        or any(
            value is not None and (
                not isinstance(value, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
            )
            for value in root["priorDeclaredImageConfigIds"].values()
        )
        or root.get("uniqueBuildTags") != {
            service: f"{details['outputRepository']}:candidate-{setup_id}"
            for service, details in PATCHED_IMAGE_INPUTS.items()
        }
    ):
        raise InstallError("patched-image build identity or authority differs")
    started = _timestamp(root["buildStartedAt"], "patched-image buildStartedAt")
    completed = _timestamp(root["completedAt"], "patched-image completedAt")
    if completed < started:
        raise InstallError("patched-image build timestamps are reversed")
    for service, declared in RUNTIME_IMAGES.items():
        row = _exact(services.get(service), {
            "mode", "declaredImage", "imageConfigId", "localContentReference",
            "architecture", "operatingSystem", "repoDigests", "artifactSha256",
            "dockerfileSha256", "labels",
        }, f"patched-image service {service}")
        patched = service in PATCHED_IMAGE_INPUTS
        expected_repository = (
            PATCHED_IMAGE_INPUTS[service]["outputRepository"]
            if patched else _image_repository(declared)
        )
        content = f"{expected_repository}@{row['imageConfigId']}"
        if (
            row.get("mode") != ("patched-build" if patched else "exact-inspection")
            or row.get("declaredImage") != declared
            or not isinstance(row.get("imageConfigId"), str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", row["imageConfigId"]) is None
            or row.get("localContentReference") != content
            or images.get(service) != content
            or row.get("architecture") != "amd64"
            or row.get("operatingSystem") != "linux"
            or not isinstance(row.get("repoDigests"), list)
            or any(
                not isinstance(item, str)
                or re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", item) is None
                for item in row["repoDigests"]
            )
            or row["repoDigests"] != sorted(set(row["repoDigests"]))
            or (
                patched and (
                    not isinstance(row.get("artifactSha256"), str)
                    or SHA256_RE.fullmatch(row["artifactSha256"]) is None
                    or not isinstance(row.get("dockerfileSha256"), str)
                    or SHA256_RE.fullmatch(row["dockerfileSha256"]) is None
                    or row.get("labels") != {
                        "org.opencontainers.image.revision": SOURCE_COMMIT,
                        "org.observability-placement.patch.sha256": PATCH_SHA256,
                        "org.observability-placement.service": service,
                    }
                )
            )
            or (
                not patched and (
                    row.get("artifactSha256") is not None
                    or row.get("dockerfileSha256") is not None
                    or row.get("labels") != {}
                )
            )
        ):
            raise InstallError(f"patched-image service identity differs: {service}")
    return dict(root)


def build_patched_images(
    *, working_root: Path, final_release_root: Path, setup_id: str,
    framework_commit: str, authorization_deadline: str, output: Path,
) -> dict[str, Any]:
    """Build and inspect the three patched images, then bind all eight image IDs."""

    if (
        os.geteuid() != EXECUTION_UID or os.getegid() != EXECUTION_GID
        or sorted(os.getgroups()) != [EXECUTION_DOCKER_GID, EXECUTION_GID]
    ):
        raise InstallError("patched-image build is not the exact stig execution identity")
    working_root = working_root.resolve()
    final_release_root = final_release_root.resolve()
    output = output.resolve()
    if (
        SETUP_ID_RE.fullmatch(setup_id) is None
        or COMMIT_RE.fullmatch(framework_commit) is None
        or working_root != Path(__file__).resolve().parents[3]
        or working_root.parent != RELEASES_ROOT
        or working_root.name != f".pending-{setup_id}"
        or final_release_root.parent != RELEASES_ROOT
        or re.fullmatch(
            rf"{setup_id}-{framework_commit[:12]}-[0-9a-f]{{16}}",
            final_release_root.name,
        ) is None
        or output.parent != working_root
        or output.exists() or output.is_symlink()
    ):
        raise InstallError("patched-image build path or identity differs")
    deadline = _timestamp(authorization_deadline, "patched-image authorization deadline")
    if datetime.now(timezone.utc) >= deadline:
        raise InstallError("patched-image setup authorization has expired")
    observed_commit = _build_command(
        ("git", "-C", str(working_root), "rev-parse", "HEAD"), cwd=None,
        deadline=deadline, maximum_seconds=30,
    ).stdout.decode("ascii", errors="strict").strip()
    if observed_commit != framework_commit:
        raise InstallError("patched-image build framework commit differs")
    source = working_root / "upstream/teastore"
    source_head = _build_command(
        ("git", "-C", str(source), "rev-parse", "HEAD"), cwd=None,
        deadline=deadline, maximum_seconds=30,
    ).stdout.decode("ascii", errors="strict").strip()
    source_status = _build_command(
        ("git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"),
        cwd=None, deadline=deadline, maximum_seconds=30,
    ).stdout
    contract_path = working_root / "modules/teastore/images/patched-image-inputs.json"
    contract, contract_payload = _json_file(contract_path, "patched-image input contract")
    patch_path = working_root / "modules/teastore/witness/teastore-app-witness-v3.patch"
    if (
        source_head != SOURCE_COMMIT or source_status
        or hashlib.sha256(_regular_bytes(patch_path, "application witness patch")).hexdigest()
        != PATCH_SHA256
        or contract.get("source", {}).get("commit") != SOURCE_COMMIT
        or contract.get("patch", {}).get("sha256") != PATCH_SHA256
        or contract.get("toolchain", {}).get("command") != list(MAVEN_COMMAND)
    ):
        raise InstallError("patched-image source, patch, or toolchain contract differs")

    started = datetime.now(timezone.utc)
    temporary_parent = Path(tempfile.mkdtemp(
        prefix=f".candidate-images-{setup_id}-", dir=str(working_root.parent),
    ))
    ephemeral = temporary_parent / "source"
    temporary_containers: list[str] = []
    unique_tags: dict[str, str] = {}
    prior_declared_images: dict[str, str | None] = {}
    changed_declared_tags: list[str] = []
    worktree_added = False
    artifacts: dict[str, Any] = {}
    maven: subprocess.CompletedProcess[bytes] | None = None
    services: dict[str, Any] = {}
    committed = False
    try:
        for service in PATCHED_IMAGE_INPUTS:
            try:
                prior, _ = _inspect_image(
                    RUNTIME_IMAGES[service], deadline=deadline,
                )
            except InstallError:
                prior_declared_images[service] = None
            else:
                prior_declared_images[service] = prior["Id"]
        _build_command(
            ("git", "-C", str(source), "worktree", "add", "--detach",
             str(ephemeral), SOURCE_COMMIT), cwd=None, deadline=deadline,
            maximum_seconds=120,
        )
        worktree_added = True
        _build_command(
            ("git", "-C", str(ephemeral), "apply", "--check",
             "--ignore-space-change", str(patch_path)), cwd=None, deadline=deadline,
            maximum_seconds=60,
        )
        _build_command(
            ("git", "-C", str(ephemeral), "apply", "--index",
             "--ignore-space-change", str(patch_path)), cwd=None, deadline=deadline,
            maximum_seconds=60,
        )
        manifest, _ = _json_file(
            working_root / "modules/teastore/witness/patch-manifest-v3.json",
            "application witness patch manifest",
        )
        changed = _build_command(
            ("git", "-C", str(ephemeral), "diff", "--cached", "--name-only", "--"),
            cwd=None, deadline=deadline, maximum_seconds=30,
        ).stdout.decode("utf-8", errors="strict").splitlines()
        if changed != manifest.get("patchedPaths"):
            raise InstallError("patched-image source path population differs")
        unstaged = _build_command(
            ("git", "-C", str(ephemeral), "diff", "--quiet", "--"), cwd=None,
            deadline=deadline, maximum_seconds=30,
        )
        if unstaged.returncode != 0:  # pragma: no cover - _build_command rejects first
            raise InstallError("patched-image source has an unstaged diff")
        maven = _build_command(
            MAVEN_COMMAND, cwd=ephemeral, deadline=deadline, maximum_seconds=7200,
        )
        artifacts = _validate_built_wars(ephemeral, contract)
        for service, build_input in PATCHED_IMAGE_INPUTS.items():
            unique_tag = f"{build_input['outputRepository']}:candidate-{setup_id}"
            _build_command(
                ("docker", "build", "--pull", "--platform", "linux/amd64",
                 "--file", str(working_root / build_input["dockerfilePath"]),
                 "--tag", unique_tag, str(ephemeral)), cwd=None, deadline=deadline,
                maximum_seconds=3600,
            )
            unique_tags[service] = unique_tag
            row, _ = _inspect_image(unique_tag, deadline=deadline)
            labels = row["Config"].get("Labels") or {}
            expected_labels = {
                "org.opencontainers.image.revision": SOURCE_COMMIT,
                "org.observability-placement.patch.sha256": PATCH_SHA256,
                "org.observability-placement.service": service,
            }
            if any(labels.get(key) != value for key, value in expected_labels.items()):
                raise InstallError(f"patched-image labels differ: {service}")
            container_name = f"teastore_candidate_image_{setup_id[:12]}_{service}"
            created = _build_command(
                ("docker", "create", "--name", container_name, "--entrypoint",
                 "/bin/true", unique_tag), cwd=None, deadline=deadline,
                maximum_seconds=120,
            ).stdout.decode("ascii", errors="strict").strip()
            if re.fullmatch(r"[0-9a-f]{64}", created) is None:
                raise InstallError(f"patched-image inspection container differs: {service}")
            temporary_containers.append(created)
            copied = temporary_parent / f"{service}.war"
            _build_command(
                ("docker", "cp", f"{created}:{build_input['overlayPath']}", str(copied)),
                cwd=None, deadline=deadline, maximum_seconds=120,
            )
            if hashlib.sha256(_regular_bytes(copied, f"{service} image WAR")).hexdigest() != (
                artifacts[service]["sha256"]
            ):
                raise InstallError(f"patched-image overlaid WAR differs: {service}")
            _build_command(
                ("docker", "rm", "-f", created), cwd=None, deadline=deadline,
                maximum_seconds=120,
            )
            temporary_containers.remove(created)

        for service, declared in RUNTIME_IMAGES.items():
            inspected_reference = unique_tags.get(service, declared)
            try:
                row, _ = _inspect_image(inspected_reference, deadline=deadline)
            except InstallError:
                if service in PATCHED_IMAGE_INPUTS:
                    raise
                _build_command(
                    ("docker", "pull", "--platform", "linux/amd64", declared), cwd=None,
                    deadline=deadline, maximum_seconds=1800,
                )
                row, _ = _inspect_image(declared, deadline=deadline)
            patched = service in PATCHED_IMAGE_INPUTS
            repository = (
                PATCHED_IMAGE_INPUTS[service]["outputRepository"]
                if patched else _image_repository(declared)
            )
            content = f"{repository}@{row['Id']}"
            services[service] = {
                "mode": "patched-build" if patched else "exact-inspection",
                "declaredImage": declared, "imageConfigId": row["Id"],
                "localContentReference": content, "architecture": row["Architecture"],
                "operatingSystem": row["Os"],
                "repoDigests": sorted(set(row.get("RepoDigests") or [])),
                "artifactSha256": artifacts[service]["sha256"] if patched else None,
                "dockerfileSha256": hashlib.sha256(_regular_bytes(
                    working_root / PATCHED_IMAGE_INPUTS[service]["dockerfilePath"],
                    f"{service} Dockerfile",
                )).hexdigest() if patched else None,
                "labels": {
                    key: row["Config"].get("Labels", {}).get(key)
                    for key in (
                        "org.opencontainers.image.revision",
                        "org.observability-placement.patch.sha256",
                        "org.observability-placement.service",
                    )
                } if patched else {},
            }
        for service in PATCHED_IMAGE_INPUTS:
            _build_command(
                ("docker", "tag", unique_tags[service], RUNTIME_IMAGES[service]),
                cwd=None, deadline=deadline, maximum_seconds=120,
            )
            changed_declared_tags.append(service)
            installed_row, _ = _inspect_image(
                RUNTIME_IMAGES[service], deadline=deadline,
            )
            if installed_row["Id"] != services[service]["imageConfigId"]:
                raise InstallError(f"patched-image installed tag differs: {service}")
        receipt = {
            "schemaVersion": 1, "kind": IMAGE_BUILD_KIND, "setupId": setup_id,
            "target": TARGET, "executionUser": EXECUTION_USER,
            "executionUid": EXECUTION_UID, "executionGid": EXECUTION_GID,
            "frameworkCommit": framework_commit, "sourceCommit": SOURCE_COMMIT,
            "patchSha256": PATCH_SHA256,
            "inputContractSha256": hashlib.sha256(contract_payload).hexdigest(),
            "mavenCommand": list(MAVEN_COMMAND),
            "mavenStdoutSha256": hashlib.sha256(maven.stdout).hexdigest(),
            "mavenStderrSha256": hashlib.sha256(maven.stderr).hexdigest(),
            "services": services,
            "imageDigests": {
                service: services[service]["localContentReference"]
                for service in RUNTIME_IMAGES
            },
            "buildStartedAt": started.isoformat(),
            "completedAt": datetime.now(timezone.utc).isoformat(),
            "cellsRun": 0, "containersStarted": 0,
            "temporaryContainersRemoved": True, "ready": True,
            "priorDeclaredImageConfigIds": prior_declared_images,
            "uniqueBuildTags": unique_tags,
            "promotionAuthorized": False,
        }
        _validate_image_build_receipt(
            receipt, setup_id=setup_id, framework_commit=framework_commit,
            release_root=working_root,
        )
        _write_exclusive(
            output,
            json.dumps(receipt, allow_nan=False, indent=2, sort_keys=True).encode() + b"\n",
            uid=EXECUTION_UID, gid=EXECUTION_GID,
        )
        committed = True
        return receipt
    finally:
        active_error = sys.exc_info()[1]
        cleanup_errors: list[str] = []
        for container in temporary_containers:
            try:
                _build_command(
                    ("docker", "rm", "-f", container), cwd=None, deadline=deadline,
                    maximum_seconds=120, cleanup=True,
                )
            except Exception as exc:  # noqa: BLE001 - attempt every cleanup action
                cleanup_errors.append(f"container {container}: {type(exc).__name__}: {exc}")
        if worktree_added:
            try:
                _build_command(
                    ("git", "-C", str(source), "worktree", "remove", "--force",
                     str(ephemeral)), cwd=None, deadline=deadline, maximum_seconds=120,
                    cleanup=True,
                )
            except Exception as exc:  # noqa: BLE001 - retain cleanup defect
                cleanup_errors.append(f"source worktree: {type(exc).__name__}: {exc}")
        shutil.rmtree(temporary_parent, ignore_errors=True)
        if temporary_parent.exists() or temporary_parent.is_symlink():
            cleanup_errors.append("temporary build root remains")
        try:
            final_head = _build_command(
                ("git", "-C", str(source), "rev-parse", "HEAD"), cwd=None,
                deadline=deadline, maximum_seconds=30, cleanup=True,
            ).stdout.decode("ascii", errors="strict").strip()
            final_status = _build_command(
                ("git", "-C", str(source), "status", "--porcelain",
                 "--untracked-files=no"), cwd=None, deadline=deadline,
                maximum_seconds=30, cleanup=True,
            ).stdout
            if final_head != SOURCE_COMMIT or final_status:
                raise InstallError("pinned source differs after patched-image cleanup")
        except Exception as exc:  # noqa: BLE001 - retain cleanup defect
            cleanup_errors.append(f"source recheck: {type(exc).__name__}: {exc}")
        if not committed or active_error is not None or cleanup_errors:
            for service in reversed(changed_declared_tags):
                prior = prior_declared_images[service]
                argv = (
                    ("docker", "tag", prior, RUNTIME_IMAGES[service])
                    if prior is not None
                    else ("docker", "image", "rm", RUNTIME_IMAGES[service])
                )
                try:
                    _build_command(
                        argv, cwd=None, deadline=deadline, maximum_seconds=120,
                        cleanup=True,
                    )
                except Exception as exc:  # noqa: BLE001 - attempt full rollback
                    cleanup_errors.append(
                        f"declared tag {service}: {type(exc).__name__}: {exc}"
                    )
            for tag in unique_tags.values():
                try:
                    _build_command(
                        ("docker", "image", "rm", "--force", tag), cwd=None,
                        deadline=deadline, maximum_seconds=120, cleanup=True,
                    )
                except Exception as exc:  # noqa: BLE001 - attempt full rollback
                    cleanup_errors.append(f"image tag {tag}: {type(exc).__name__}: {exc}")
        if cleanup_errors:
            detail = "; ".join(cleanup_errors)
            if active_error is not None:
                raise InstallError(
                    f"{type(active_error).__name__}: {active_error}; "
                    f"patched-image cleanup failed: {detail}"
                ) from active_error
            raise InstallError(f"patched-image cleanup failed: {detail}")


def _campaign_unit_name(
    campaign_id: str, setup_id: str, package_sha256: str,
) -> str:
    """Name the transient unit after one launch attempt, not the campaign.

    systemd keeps a failed transient unit loaded until someone resets it, and
    `systemd-run --unit=` refuses a name that is still loaded.  Deriving the
    name from campaignId alone -- which is constant for every attempt at this
    study -- therefore let a single failed launch poison every later launch
    with `Unit ... already exists`, forever, with no cleanup path the harness
    could reach.  Single-campaign exclusion is owned by the outer lease and by
    the O_EXCL package write, so the unit name only has to identify the
    attempt; setupId and the package digest do that.
    """

    digest = hashlib.sha256(b"\0".join(
        value.encode("ascii") for value in (campaign_id, setup_id, package_sha256)
    )).hexdigest()
    return "teastore-candidate-v4-" + digest[:32]


def _detached_controller_command(
    package: Mapping[str, Any], *, controller: Path, output: Path,
    framework_commit: str, package_sha256: str, log_path: Path,
) -> tuple[list[str], str]:
    """Build the exact transient-service argv that outlives the SSH channel."""

    unit_name = _campaign_unit_name(
        package["campaignId"], package["setupId"], package_sha256,
    )
    deadline = _timestamp(
        package["authorizationDeadline"], "runtime authorization deadline",
    ).timestamp()
    runtime_seconds = max(1, math.ceil(deadline - datetime.now(timezone.utc).timestamp()))
    supervisor = Path(package["releaseRoot"]) / REMOTE_INSTALLER
    return ([
        SYSTEMD_RUN, "--quiet", f"--unit={unit_name}",
        "--property=Type=exec", "--property=KillMode=control-group",
        "--property=TimeoutStopSec=120s", "--property=UMask=0077",
        f"--property=RuntimeMaxSec={runtime_seconds}s",
        f"--property=WorkingDirectory={package['releaseRoot']}",
        f"--property=StandardOutput=append:{log_path}",
        f"--property=StandardError=append:{log_path}", "--",
        TARGET_PYTHON, "-I", str(supervisor), "supervise",
        "--controller", str(controller), "--package", str(package["packagePath"]),
        "--output", str(output), "--framework-commit", framework_commit,
        "--package-sha256", package_sha256,
    ], unit_name)


def _prove_execution_user_can_import_runtime_modules() -> None:
    """Prove the execution user -- not root -- can actually use the deps.

    Everything under /usr/local/lib/python3.9/dist-packages on this target had
    been installed with umask 077, so 594 directories and 6229 files were
    root-only. The installer runs as root and never noticed. The collector runs
    as stig, and Python does not fail loudly here: an unreadable package
    directory is silently treated as a *namespace package*, so `import pika`
    succeeded and only `pika.ConnectionParameters` failed, fifteen minutes into
    a cell, as AttributeError. __file__ is None for exactly that degradation,
    so it is the thing worth asserting.
    """

    probe = _run_as_execution_user((TARGET_PYTHON, "-I", "-c", (
        "import importlib, json\n"
        "report = {}\n"
        f"for name in {list(RUNTIME_PYTHON_MODULES)!r}:\n"
        "    try:\n"
        "        module = importlib.import_module(name)\n"
        "    except BaseException as exc:\n"
        "        report[name] = f'import failed: {type(exc).__name__}: {exc}'\n"
        "        continue\n"
        "    if getattr(module, '__file__', None) is None:\n"
        "        report[name] = 'resolved to an empty namespace package'\n"
        "    else:\n"
        "        report[name] = None\n"
        "print(json.dumps(report, sort_keys=True))\n"
    )))
    if probe.returncode != 0:
        raise InstallError(
            "runtime preflight could not probe execution-user imports: "
            + (probe.stdout + probe.stderr).decode("utf-8", errors="replace")[-500:]
        )
    report = _json_bytes(probe.stdout, "execution user module probe")
    if set(report) != set(RUNTIME_PYTHON_MODULES):
        raise InstallError("execution user module probe reported the wrong modules")
    broken = {name: why for name, why in report.items() if why is not None}
    if broken:
        raise InstallError(
            f"execution user {EXECUTION_USER} cannot use required Python modules: "
            + "; ".join(f"{name}: {why}" for name, why in sorted(broken.items()))
        )


def runtime_preflight() -> dict[str, Any]:
    """Capture a fresh, read-only installed-target proof before GATE-RUN.

    Stopped foreign Compose projects are retained in the inventory and are not
    treated as conflicts.  Active projects, stale candidate namespaces, and
    listeners on the exact published host ports fail closed without cleanup.
    """

    _require_root_transport()
    try:
        account = pwd.getpwnam(EXECUTION_USER)
        socket = Path("/var/run/docker.sock").lstat()
    except (KeyError, OSError) as exc:
        raise InstallError(f"runtime preflight identity is unavailable: {exc}") from exc
    groups = sorted(set(os.getgrouplist(EXECUTION_USER, account.pw_gid)))
    identity = []
    for flag in ("-u", "-g", "-G"):
        result = _run_as_execution_user(("id", flag))
        if result.returncode != 0:
            raise InstallError("runtime preflight could not prove execution identity")
        identity.append(result.stdout.decode("ascii", errors="strict").strip())
    try:
        observed_groups = sorted({int(value) for value in identity[2].split()})
    except ValueError as exc:
        raise InstallError("runtime preflight supplementary groups are malformed") from exc
    if (
        identity[:2] != [str(EXECUTION_UID), str(EXECUTION_GID)]
        or observed_groups != groups
        or account.pw_uid != EXECUTION_UID
        or account.pw_gid != EXECUTION_GID
        or EXECUTION_DOCKER_GID not in groups
        or Path("/var/run/docker.sock").is_symlink()
        or not stat.S_ISSOCK(socket.st_mode)
        or (socket.st_uid, socket.st_gid, stat.S_IMODE(socket.st_mode))
        != (0, EXECUTION_DOCKER_GID, 0o660)
    ):
        raise InstallError("runtime preflight execution identity or Docker socket differs")

    _prove_execution_user_can_import_runtime_modules()

    docker_info = _run_as_execution_user((
        "docker", "info", "--format", "{{.ServerVersion}}",
    ))
    if docker_info.returncode != 0:
        raise InstallError("runtime preflight Docker access as stig failed")
    server_version = docker_info.stdout.decode("utf-8", errors="strict").strip()
    if server_version != DOCKER_SERVER_VERSION:
        raise InstallError("runtime preflight Docker server version differs")

    compose = _run_as_execution_user((
        "docker", "compose", "ls", "--all", "--format", "json",
    ))
    if compose.returncode != 0:
        raise InstallError("runtime preflight Compose inventory failed")
    try:
        raw_projects = json.loads(
            compose.stdout.decode("utf-8", errors="strict"),
            object_pairs_hook=_no_duplicates, parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InstallError(f"runtime preflight Compose inventory is invalid: {exc}") from exc
    if not isinstance(raw_projects, list):
        raise InstallError("runtime preflight Compose inventory is not a list")
    projects: list[dict[str, Any]] = []
    blockers: list[str] = []
    seen_projects: set[str] = set()
    for value in raw_projects:
        if not isinstance(value, dict):
            raise InstallError("runtime preflight Compose row is not an object")
        name = value.get("Name")
        status_value = value.get("Status")
        config_files = value.get("ConfigFiles")
        if (
            not isinstance(name, str) or not name
            or name in seen_projects
            or not isinstance(status_value, str) or not status_value
            or not isinstance(config_files, str)
        ):
            raise InstallError("runtime preflight Compose row fields differ")
        seen_projects.add(name)
        lowered = status_value.lower()
        active = any(
            token in lowered for token in ("running", "restarting", "paused", "created")
        )
        if not active and "exited" not in lowered:
            raise InstallError("runtime preflight Compose status is unrecognized")
        candidate_namespace = name.startswith(PROJECT_PREFIX)
        projects.append({
            "name": name,
            "status": status_value,
            "configFiles": config_files,
            "active": active,
            "candidateNamespace": candidate_namespace,
        })
        if active:
            blockers.append(f"active Compose project: {name}")
        if candidate_namespace:
            blockers.append(f"candidate Compose namespace collision: {name}")
    projects.sort(key=lambda row: row["name"])

    listeners_result = _run_as_execution_user(("ss", "-H", "-ltn"))
    if listeners_result.returncode != 0:
        raise InstallError("runtime preflight listener inventory failed")
    listeners: list[dict[str, Any]] = []
    for line in listeners_result.stdout.decode("utf-8", errors="strict").splitlines():
        columns = line.split()
        if len(columns) < 4 or ":" not in columns[3]:
            raise InstallError("runtime preflight listener row is malformed")
        port_text = columns[3].rsplit(":", 1)[1]
        if not port_text.isdigit():
            raise InstallError("runtime preflight listener port is malformed")
        port = int(port_text)
        if port in RESERVED_PORTS:
            listeners.append({
                "port": port,
                "endpointSha256": hashlib.sha256(line.encode("utf-8")).hexdigest(),
            })
            blockers.append(f"reserved host port is occupied: {port}")
    listeners.sort(key=lambda row: (row["port"], row["endpointSha256"]))
    if blockers:
        raise InstallError("runtime preflight conflicts: " + "; ".join(blockers))
    return {
        "schemaVersion": 1,
        "kind": "teastore-candidate-installed-runtime-preflight-v1",
        "target": TARGET,
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "executionIdentity": {
            "user": EXECUTION_USER,
            "uid": EXECUTION_UID,
            "gid": EXECUTION_GID,
            "supplementaryGids": groups,
            "executionMethod": EXECUTION_METHOD,
        },
        "docker": {
            "serverVersion": server_version,
            "socketOwnerUid": socket.st_uid,
            "socketOwnerGid": socket.st_gid,
            "socketMode": f"0{stat.S_IMODE(socket.st_mode):03o}",
            "accessAsExecutionUser": True,
        },
        "resourceInventory": {
            "projectPrefix": PROJECT_PREFIX,
            "reservedPorts": list(RESERVED_PORTS),
            "composeProjects": projects,
            "reservedPortListeners": listeners,
        },
        "blockers": [],
        "ready": True,
        "experimentalCellsExecuted": 0,
        "mutationPerformed": False,
    }


def _expected_setup_text(authorization: Mapping[str, Any]) -> str:
    return (
        f"APPROVE GATE-SETUP setup={authorization['setupId']} "
        f"target={authorization['target']} transport-user=root "
        f"execution-user={authorization['executionUser']} "
        f"framework={authorization['frameworkCommit']} "
        f"tree={authorization['frameworkTree']} "
        f"bundle={authorization['bundleSha256']} "
        f"gate-plan={authorization['gatePlanSha256']} "
        f"target-proof={authorization['targetProofSha256']} "
        f"release-manifest={authorization['releaseManifestSha256']} "
        f"setup-only zero-experimental-cells deadline="
        f"{authorization['authorizationDeadline']}"
    )


def _release_root(authorization: Mapping[str, Any]) -> Path:
    return RELEASES_ROOT / (
        f"{authorization['setupId']}-{authorization['frameworkCommit'][:12]}-"
        f"{authorization['bundleSha256'][:16]}"
    )


def _validate_setup_inputs(
    *, gate_plan: dict[str, Any], target: dict[str, Any], manifest: dict[str, Any],
    gate_setup: dict[str, Any], bundle: bytes, self_sha256: str,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = _exact(gate_plan, {
        "schemaVersion", "kind", "gate", "decision", "typedApproval", "approvedBy",
        "approvedAt", "bindings", "runtimeAuthorized", "promotionAuthorized",
    }, "GATE-PLAN")
    proof = _exact(target, {
        "schemaVersion", "kind", "target", "capturedAt", "probeSha256",
        "transport", "executionCapabilities", "dockerSocket", "legacyRoots",
        "candidateV4Root", "hostIdentity", "pythonRuntime",
    }, "target proof")
    release = _exact(manifest, {
        "schemaVersion", "kind", "frameworkCommit", "frameworkTree",
        "bundleFormat", "bundleSha256", "bundleBytes", "bundleMembers",
        "controllerDigests", "submoduleCommits", "setupSourceBuildAllowed",
        "campaignSourceBuildAllowed",
    }, "release manifest")
    setup = _exact(gate_setup, {
        "schemaVersion", "kind", "gate", "decision", "typedApproval", "approvedBy",
        "approvedAt", "authorization", "runtimeAuthorized", "promotionAuthorized",
    }, "GATE-SETUP")
    authorization = _exact(setup["authorization"], {
        "setupId", "studyEpoch", "target", "transportUser", "executionUser",
        "executionUid", "executionGid", "executionMethod", "frameworkCommit",
        "frameworkTree", "descriptorCanonicalSha256",
        "compiledPlanCanonicalSha256", "gatePlanSha256", "targetProofSha256",
        "releaseManifestSha256", "bundleSha256", "bundleBytes",
        "controllerDigestsSha256", "releaseRoot", "resultsRoot",
        "exclusiveLeasePath", "allowedActions", "experimentalCellsAuthorized",
        "notBefore", "authorizationDeadline",
    }, "GATE-SETUP authorization")
    setup_id = authorization["setupId"]
    execution_user = authorization["executionUser"]
    capabilities = proof.get("executionCapabilities")
    capability = capabilities.get(execution_user) if isinstance(capabilities, dict) else None
    legacy = proof.get("legacyRoots")
    legacy_by_path = {
        row.get("path"): row for row in legacy if isinstance(row, dict)
    } if isinstance(legacy, list) else {}
    expected_legacy = {
        path: {"path": path, "exists": True, "ownerUid": 0, "ownerGid": 0,
               "mode": "0700", "accessibleByStig": False}
        for path in (
            "/home/stig/observability-placement-runs",
            "/home/stig/observability-placement-results",
        )
    }
    if (
        plan.get("schemaVersion") != 1
        or plan.get("gate") != "GATE-PLAN"
        or plan.get("decision") != "approve-exact-plan"
        or plan.get("runtimeAuthorized") is not False
        or plan.get("promotionAuthorized") is not False
        or proof.get("schemaVersion") != 1
        or proof.get("kind") != TARGET_PROOF_KIND
        or proof.get("target") != TARGET
        or proof.get("probeSha256") != self_sha256
        or proof.get("hostIdentity") != {
            "hostname": TARGET, "fqdn": TARGET_HOSTNAME,
            "machineIdSha256": TARGET_MACHINE_ID_SHA256,
        }
        or not isinstance(proof.get("pythonRuntime"), dict)
        or proof["pythonRuntime"].get("executable") != TARGET_PYTHON
        or proof["pythonRuntime"].get("requiredLanguageVersion") != [3, 9]
        or proof["pythonRuntime"].get("observedTargetPatch") != [3, 9, 2]
        or proof["pythonRuntime"].get("version") != [3, 9, 2]
        or proof.get("transport") != {"user": "root", "uid": 0, "gid": 0}
        or not isinstance(capabilities, dict)
        or set(capabilities) != {"root", EXECUTION_USER}
        or proof.get("dockerSocket") != {
            "path": "/var/run/docker.sock", "ownerUid": 0,
            "ownerGid": EXECUTION_DOCKER_GID, "mode": "0660",
        }
        or legacy_by_path != expected_legacy
        or release.get("schemaVersion") != 1
        or release.get("kind") != RELEASE_MANIFEST_KIND
        or release.get("bundleFormat") != "candidate-v4-tar-v1"
        or release.get("setupSourceBuildAllowed") is not True
        or release.get("campaignSourceBuildAllowed") is not False
        or not isinstance(release.get("bundleBytes"), int)
        or release["bundleBytes"] != len(bundle)
        or hashlib.sha256(bundle).hexdigest() != release.get("bundleSha256")
        or not isinstance(release.get("controllerDigests"), dict)
        or release["controllerDigests"].get("candidate-release-installer") != self_sha256
        or setup.get("schemaVersion") != 1
        or setup.get("kind") != SETUP_KIND
        or setup.get("gate") != "GATE-SETUP"
        or setup.get("decision") != "authorize-exact-setup-only"
        or setup.get("runtimeAuthorized") is not False
        or setup.get("promotionAuthorized") is not False
        or not isinstance(setup_id, str)
        or SETUP_ID_RE.fullmatch(setup_id) is None
        or execution_user != EXECUTION_USER
        or not isinstance(capability, dict)
        or capability.get("uid") != EXECUTION_UID
        or capability.get("gid") != EXECUTION_GID
        or capability.get("executionMethod") != EXECUTION_METHOD
        or not isinstance(capability.get("supplementaryGids"), list)
        or EXECUTION_DOCKER_GID not in capability["supplementaryGids"]
        or capability.get("dockerAccess") is not True
        or authorization.get("executionUid") != capability.get("uid")
        or authorization.get("executionGid") != capability.get("gid")
        or authorization.get("executionMethod") != EXECUTION_METHOD
        or authorization.get("target") != TARGET
        or authorization.get("transportUser") != TRANSPORT_USER
        or authorization.get("frameworkCommit") != release.get("frameworkCommit")
        or authorization.get("frameworkTree") != release.get("frameworkTree")
        or authorization.get("gatePlanSha256") != _canonical_sha(plan)
        or authorization.get("targetProofSha256") != _canonical_sha(proof)
        or authorization.get("releaseManifestSha256") != _canonical_sha(release)
        or authorization.get("bundleSha256") != release.get("bundleSha256")
        or authorization.get("bundleBytes") != len(bundle)
        or authorization.get("controllerDigestsSha256")
        != _canonical_sha(release["controllerDigests"])
        or authorization.get("releaseRoot") != str(_release_root(authorization))
        or authorization.get("resultsRoot") != str(RESULTS_ROOT / setup_id)
        or authorization.get("exclusiveLeasePath") != str(LEASE_PATH)
        or authorization.get("allowedActions") != ALLOWED_SETUP_ACTIONS
        or authorization.get("experimentalCellsAuthorized") != 0
        or setup.get("typedApproval") != _expected_setup_text(authorization)
    ):
        raise InstallError("GATE-SETUP inputs, target identity, or zero-cell ceiling differ")
    approved = _timestamp(setup.get("approvedAt"), "GATE-SETUP approvedAt")
    not_before = _timestamp(authorization.get("notBefore"), "GATE-SETUP notBefore")
    deadline = _timestamp(
        authorization.get("authorizationDeadline"), "GATE-SETUP deadline"
    )
    age = math.floor((now - approved).total_seconds())
    if age < -5 or age > 900 or now < not_before or now >= deadline:
        raise InstallError("GATE-SETUP is stale or outside its authorization window")
    if _timestamp(plan.get("approvedAt"), "GATE-PLAN approvedAt") > approved or (
        _timestamp(proof.get("capturedAt"), "target proof capturedAt") > approved
    ):
        raise InstallError("GATE-SETUP predates its plan or target proof")
    return authorization, release


def _safe_setup_staging(path: Path, setup_id: str, suffix: str) -> None:
    expected = Path(f"/root/.obsplacement-candidate-v4-{setup_id}.{suffix}.pending")
    if path != expected:
        raise InstallError(f"setup staging path differs for {suffix}")


def cleanup_setup_staging(*, setup_id: str, expected_self_sha256: str) -> dict[str, Any]:
    """Remove only the six exact setup staging files for one validated ID."""

    _require_root_transport()
    if SETUP_ID_RE.fullmatch(setup_id) is None or SHA256_RE.fullmatch(
        expected_self_sha256
    ) is None:
        raise InstallError("setup cleanup identity is malformed")
    paths = {
        suffix: Path(f"/root/.obsplacement-candidate-v4-{setup_id}.{suffix}.pending")
        for suffix in (
            "gate-plan", "target-proof", "release-manifest", "gate-setup",
            "bundle", "installer",
        )
    }
    installer = paths["installer"]
    if installer.exists() or installer.is_symlink():
        if hashlib.sha256(_regular_bytes(installer, "staged installer")).hexdigest() != (
            expected_self_sha256
        ):
            raise InstallError("refusing cleanup through unbound staged installer")
    removed: list[str] = []
    for suffix, path in paths.items():
        if not (path.exists() or path.is_symlink()):
            continue
        _regular_bytes(path, f"staged {suffix}")
        path.unlink()
        removed.append(suffix)
    return {
        "schemaVersion": 1,
        "kind": "teastore-candidate-setup-staging-cleanup-v1",
        "setupId": setup_id,
        "removed": sorted(removed),
        "state": "clean",
    }


def _mkdir_checked(path: Path, *, owner_uid: int, owner_gid: int) -> None:
    anchor = Path("/home/stig")
    try:
        metadata = anchor.lstat()
    except OSError as exc:
        raise InstallError(f"cannot inspect /home/stig: {exc}") from exc
    if anchor.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise InstallError("/home/stig is not a real directory")
    current = anchor
    parts = path.relative_to(anchor).parts
    for index, part in enumerate(parts):
        current = current / part
        # Only the leaf takes the caller's ownership. The shared candidate-v4
        # tree is created stig-owned by install, so applying a root-owned
        # leaf's ownership to its ancestors made the check contradict itself:
        # the supervisor asks for a root-owned .supervisor directory and was
        # then refused because results/ above it is legitimately stig-owned.
        leaf = index == len(parts) - 1
        expected_uid = owner_uid if leaf else EXECUTION_UID
        expected_gid = owner_gid if leaf else EXECUTION_GID
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            current.mkdir(mode=0o700)
            os.chown(current, expected_uid, expected_gid)
            os.chmod(current, 0o700)
            metadata = current.lstat()
        if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise InstallError(f"candidate-v4 path crosses a symlink/non-directory: {current}")
        if current == CANDIDATE_V4_ROOT or CANDIDATE_V4_ROOT in current.parents:
            if (
                metadata.st_uid != expected_uid
                or metadata.st_gid != expected_gid
                or stat.S_IMODE(metadata.st_mode) != 0o700
            ):
                raise InstallError(
                    f"candidate-v4 path owner or mode differs: {current} "
                    f"(uid {metadata.st_uid} gid {metadata.st_gid} mode "
                    f"{stat.S_IMODE(metadata.st_mode):04o}, expected uid "
                    f"{expected_uid} gid {expected_gid} mode 0700)"
                )


def _write_exclusive(path: Path, payload: bytes, *, uid: int, gid: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:  # pragma: no cover
                raise InstallError("exclusive artifact write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.fchown(descriptor, uid, gid)
    finally:
        os.close(descriptor)


def _chown_tree(path: Path, uid: int, gid: int) -> None:
    for current, directories, files in os.walk(path, topdown=False, followlinks=False):
        root = Path(current)
        for name in [*files, *directories]:
            child = root / name
            if child.is_symlink():
                raise InstallError("installed release contains a symlink")
            os.chown(child, uid, gid)
        os.chown(root, uid, gid)


def _sealed_file_mode(mode: int) -> int:
    """Read-only mode that preserves executability.

    Git tracks the owner execute bit, so sealing every file to 0444 rewrites
    tracked 100755 blobs to 100644 and leaves the worktree permanently
    unclean -- in the superproject and in the submodule, whose pointer then
    reads as -dirty. Readiness requires a clean worktree, so the seal must
    remove write access without changing executability.
    """
    return 0o555 if mode & 0o111 else 0o444


def compile_activation_artifacts(
    release_root: Path, *, uid: int, gid: int,
) -> dict[str, Any]:
    """Render the selected posture's AspectJ config into the pending release.

    compiled-selected.override.yaml bind-mounts
    .local/compiled/teastore/aop.xml into webui, auth, persistence, image and
    recommender. That path is a build product and therefore cannot be in the
    Git bundle the release is built from, and nothing in the candidate
    installer replaced the compile step the predecessor harness ran while
    staging. Docker silently creates a *directory* for a missing bind source,
    so the omission surfaced only as "not a directory" when the first cell
    started its containers, after GATE-SETUP had certified the release.

    The bytes come from the release's own copy of the selection compiler, so
    they are produced by exactly the code the validator re-derives them with.
    """

    release_root = Path(release_root)
    compiler_path = release_root / ACTIVATION_COMPILER
    catalog_path = release_root / ACTIVATION_CATALOG
    goal_path = release_root / ACTIVATION_GOAL
    for path in (compiler_path, catalog_path, goal_path):
        if not path.is_file() or path.is_symlink():
            raise InstallError(f"activation compile input is absent: {path}")
    specification = importlib.util.spec_from_file_location(
        "candidate_v4_selection", compiler_path,
    )
    if specification is None or specification.loader is None:
        raise InstallError("activation selection compiler is not importable")
    compiler = importlib.util.module_from_spec(specification)
    try:
        specification.loader.exec_module(compiler)
    except Exception as exc:  # noqa: BLE001 - surface the real import failure
        raise InstallError(f"activation selection compiler failed to load: {exc}") from exc

    catalog = _json_bytes(
        _regular_bytes(catalog_path, "activation catalog"), "activation catalog",
    )
    goal = _json_bytes(
        _regular_bytes(goal_path, "activation goal"), "activation goal",
    )
    requested = goal.get("logicalSensors")
    if not isinstance(requested, list) or not all(
        isinstance(item, str) for item in requested
    ):
        raise InstallError("activation goal logical sensors are malformed")
    all_sensors = [row["id"] for row in catalog.get("logicalSensors", [])]
    rendered: dict[str, dict[str, Any]] = {}
    for posture, (selection_id, manifest_name, aop_name) in ACTIVATION_OUTPUTS.items():
        wanted = (
            requested if posture == "selected"
            else all_sensors if posture == "full" else []
        )
        try:
            compiled = compiler.compile_selection(catalog, wanted)
            aop = compiler.render_aop(compiled)
        except Exception as exc:  # noqa: BLE001 - a bad catalog must not seal
            raise InstallError(
                f"activation selection did not compile for {posture}: {exc}",
            ) from exc
        rendered[posture] = {
            "selectionId": selection_id,
            "manifestName": manifest_name,
            "aopName": aop_name,
            "goalLogicalSensors": sorted(wanted),
            "manifestBytes": (
                json.dumps(compiled, indent=2, sort_keys=True, allow_nan=False).encode()
                + b"\n"
            ),
            "aopBytes": aop.encode(),
            "selectedActivationGroups": list(compiled["selectedActivationGroups"]),
        }

    # Not _mkdir_checked: that validates a control namespace anchored at
    # /home/stig. This directory lives inside the pending release tree the
    # installer just built, so it follows the receipt directory's pattern --
    # create each level, then hand it to the execution user.
    output = release_root
    for part in ACTIVATION_OUTPUT_DIR.split("/"):
        output = output / part
        if output.exists() or output.is_symlink():
            raise InstallError(f"activation output path already exists: {output}")
        output.mkdir(mode=0o700)
        os.chown(output, uid, gid)
    for entry in rendered.values():
        _write_exclusive(
            output / entry["manifestName"], entry["manifestBytes"], uid=uid, gid=gid,
        )
        _write_exclusive(output / entry["aopName"], entry["aopBytes"], uid=uid, gid=gid)
    return {
        "schemaVersion": 2,
        "catalogSha256": hashlib.sha256(
            _regular_bytes(catalog_path, "activation catalog"),
        ).hexdigest(),
        "goalSha256": hashlib.sha256(
            _regular_bytes(goal_path, "activation goal"),
        ).hexdigest(),
        "postures": {
            posture: {
                "selectionId": entry["selectionId"],
                "goalLogicalSensors": entry["goalLogicalSensors"],
                "manifestSha256": hashlib.sha256(entry["manifestBytes"]).hexdigest(),
                "aopSha256": hashlib.sha256(entry["aopBytes"]).hexdigest(),
                "selectedActivationGroups": entry["selectedActivationGroups"],
            }
            for posture, entry in rendered.items()
        },
    }


def _seal_release_tree(path: Path) -> None:
    """Make the immediate verifier/controller closure root-owned and immutable."""
    for current, directories, files in os.walk(path, topdown=False, followlinks=False):
        root = Path(current)
        for name in files:
            child = root / name
            if child.is_symlink():
                raise InstallError("installed release contains a symlink")
            os.chown(child, 0, 0)
            os.chmod(child, _sealed_file_mode(child.lstat().st_mode))
        for name in directories:
            child = root / name
            if child.is_symlink():
                raise InstallError("installed release contains a symlink")
            os.chown(child, 0, 0)
            os.chmod(child, 0o555)
        os.chown(root, 0, 0)
        os.chmod(root, 0o555)


def _reject_install_collision(release_root: Path, pending: Path) -> None:
    if release_root.exists() or release_root.is_symlink():
        raise InstallError("candidate-v4 release path collision")
    if pending.exists() or pending.is_symlink():
        raise InstallError("partial candidate-v4 release install already exists")


def _installed_adapter():
    path = Path(__file__).resolve().parents[3] / (
        "modules/teastore/execution/candidate_runtime_adapter.py"
    )
    spec = importlib.util.spec_from_file_location(
        "teastore_candidate_installed_readiness_adapter", path,
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise InstallError("cannot load installed candidate readiness adapter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _installed_run_count() -> int:
    """Cell count of the installed release's active epoch (27 without a study-epoch selector).

    Read through the installed adapter, which reads the committed selector; never from the root staging
    path, where this file has no release tree around it.
    """
    count = _installed_adapter().RUN_COUNT
    if type(count) is not int or count < 1:
        raise InstallError("installed epoch cell count is invalid")
    return count


def _installed_release_binding(package: Mapping[str, Any]) -> dict[str, Any]:
    """Replay the atomically installed receipt before any campaign mutation."""

    release_root = Path(__file__).resolve().parents[3]
    receipt = _json_file(
        release_root / ".git/candidate-v4-receipts/release-install.json",
        "installed release receipt",
    )[0]
    summary_keys = RELEASE_BINDING_KEYS
    _exact(receipt, summary_keys | {
        "schemaVersion", "kind", "state", "runtimeExecuted", "promotionAuthorized",
    }, "installed release receipt")
    summary = {key: receipt[key] for key in summary_keys}
    runtime_inputs = package.get("cells", [{}])[0].get("runtimeInputs", {}) if isinstance(
        package.get("cells"), list
    ) and package.get("cells") else {}
    if (
        receipt.get("schemaVersion") != 1
        or receipt.get("kind") != RELEASE_INSTALL_KIND
        or receipt.get("state") != "installed"
        or receipt.get("runtimeExecuted") is not False
        or receipt.get("promotionAuthorized") is not False
        or receipt.get("setupId") != package.get("setupId")
        or receipt.get("target") != TARGET
        or receipt.get("transportUser") != TRANSPORT_USER
        or receipt.get("executionUser") != EXECUTION_USER
        or receipt.get("executionUid") != EXECUTION_UID
        or receipt.get("executionGid") != EXECUTION_GID
        or receipt.get("executionMethod") != EXECUTION_METHOD
        or receipt.get("frameworkCommit") != package.get("frameworkCommit")
        or receipt.get("bundleSha256") != package.get("bundleSha256")
        or receipt.get("releaseManifestSha256")
        != package.get("releaseManifestSha256")
        or receipt.get("gateSetupSha256") != package.get("gateSetupSha256")
        or receipt.get("releaseRoot") != package.get("releaseRoot")
        or receipt.get("resultsRoot") != package.get("resultsRoot")
        or receipt.get("exclusiveLeasePath") != package.get("outerLeasePath")
        or receipt.get("controllerDigests") != runtime_inputs.get("controllerDigests")
        or receipt.get("imageBuildReceiptSha256") != _canonical_sha(
            receipt.get("imageBuild")
        )
        or receipt.get("imageBuild", {}).get("imageDigests")
        != runtime_inputs.get("imageDigests")
        or _canonical_sha(summary) != package.get("releaseBindingSha256")
    ):
        raise InstallError("installed release receipt or bytes differ from runtime package")
    _timestamp(receipt.get("installedAt"), "installed release receipt installedAt")
    image_build = _validate_image_build_receipt(
        receipt.get("imageBuild"), setup_id=receipt["setupId"],
        framework_commit=receipt["frameworkCommit"], release_root=release_root,
    )
    retained_image_build = _json_file(
        release_root / ".git/candidate-v4-receipts/patched-image-build.json",
        "installed patched-image build receipt",
    )[0]
    if retained_image_build != image_build:
        raise InstallError("installed patched-image build receipt bytes differ")
    for relative, label in (
        (REMOTE_CONTROLLER, "installed remote controller"),
        ("modules/teastore/execution/candidate_release_installer.py",
         "installed release installer"),
    ):
        payload = _regular_bytes(release_root / relative, label)
        authority_name = (
            "candidate-remote-controller" if relative == REMOTE_CONTROLLER
            else "candidate-release-installer"
        )
        if hashlib.sha256(payload).hexdigest() != receipt["controllerDigests"].get(
            authority_name
        ):
            raise InstallError(f"{label} digest differs after installation")
    return summary


def _installed_readiness_binding(package: Mapping[str, Any]) -> dict[str, Any]:
    """Replay the atomic installed-readiness tree immediately before launch."""

    archive_sha = package.get("readinessArchiveSha256")
    readiness_sha = package.get("runtimeReadinessSha256")
    captured = package.get("runtimePreflightCapturedAt")
    if (
        not isinstance(archive_sha, str) or SHA256_RE.fullmatch(archive_sha) is None
        or not isinstance(readiness_sha, str) or SHA256_RE.fullmatch(readiness_sha) is None
    ):
        raise InstallError("runtime package readiness identity is malformed")
    # Readiness is a control name, not an experimental artifact, so it lives in
    # the root-owned /var/lib namespace built by _root_readiness_namespace and
    # never under the execution user's results root -- stig owns that tree and
    # could rename or replace anything published there. Computing it under
    # resultsRoot both looked in a place readiness is never written to and, had
    # it existed, would have trusted a path the measured user can control.
    root = READINESS_CONTROL_ROOT / str(package.get("setupId")) / archive_sha[:16]
    try:
        root_metadata = root.lstat()
    except OSError as exc:
        raise InstallError(f"installed readiness root is unavailable: {exc}") from exc
    if root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
        raise InstallError("installed readiness root is not a real directory")
    admission = _json_file(
        root / "readiness-admission.json", "installed readiness admission",
    )[0]
    expected_admission_keys = {
        "schemaVersion", "kind", "setupId", "frameworkCommit",
        "releaseBindingSha256", "ingressArchiveSha256", "captureTreeSha256",
        "readinessCanonicalSha256",
        "runtimePreflightSha256", "runtimePreflightCapturedAt", "readinessRoot",
        "validatedAt", "experimentalCellsExecuted", "runtimeReady",
        "promotionAuthorized",
    }
    if (
        set(admission) != expected_admission_keys
        or admission.get("schemaVersion") != 1
        or admission.get("kind") != "teastore-candidate-installed-readiness-v1"
        or admission.get("setupId") != package.get("setupId")
        or admission.get("frameworkCommit") != package.get("frameworkCommit")
        or admission.get("releaseBindingSha256")
        != package.get("releaseBindingSha256")
        or admission.get("ingressArchiveSha256") != archive_sha
        or admission.get("readinessCanonicalSha256") != readiness_sha
        or admission.get("runtimePreflightCapturedAt") != captured
        or admission.get("readinessRoot") != str(root)
        or admission.get("experimentalCellsExecuted") != 0
        or admission.get("runtimeReady") is not True
        or admission.get("promotionAuthorized") is not False
    ):
        raise InstallError("installed readiness admission differs from runtime package")
    readiness = _json_file(root / "readiness.json", "installed runtime readiness")[0]
    if (
        readiness.get("ingressArchiveSha256") != archive_sha
        or admission.get("captureTreeSha256") != readiness.get("captureTreeSha256")
        or readiness.get("runtimePreflight", {}).get("capturedAt") != captured
        or _canonical_sha(readiness) != readiness_sha
        or _canonical_sha(readiness.get("runtimePreflight"))
        != admission.get("runtimePreflightSha256")
    ):
        raise InstallError("installed runtime readiness bytes differ")
    adapter = _installed_adapter()
    # _generate_installed_readiness materializes the campaign into
    # artifacts/campaign, so that is where the recompiled descriptor and plan
    # live in a published readiness tree; root/campaign never exists.
    bindings = adapter.inspect_campaign(
        root / "artifacts/campaign", package["frameworkCommit"],
    )
    replayed_sha = adapter.validate_readiness(readiness, bindings, readiness_parent=root)
    if replayed_sha != readiness_sha:
        raise InstallError("installed runtime readiness replay digest differs")
    preflight_time = _timestamp(captured, "installed runtime preflight capturedAt")
    age = (datetime.now(timezone.utc) - preflight_time).total_seconds()
    if age < -5 or age > 15 * 60:
        raise InstallError("installed runtime preflight is no longer fresh")
    return readiness


def install_release(
    *, gate_plan_path: Path, target_proof_path: Path, release_manifest_path: Path,
    gate_setup_path: Path, bundle_path: Path, expected_self_sha256: str,
) -> dict[str, Any]:
    """Validate every setup byte before creating any candidate-v4 path."""

    _require_root_transport()
    self_payload = _regular_bytes(Path(__file__), "candidate release installer")
    self_sha = hashlib.sha256(self_payload).hexdigest()
    if self_sha != expected_self_sha256:
        raise InstallError("candidate release installer bytes differ")
    gate_plan, gate_plan_bytes = _json_file(gate_plan_path, "GATE-PLAN")
    target, target_bytes = _json_file(target_proof_path, "target proof")
    manifest, manifest_bytes = _json_file(release_manifest_path, "release manifest")
    gate_setup, gate_setup_bytes = _json_file(gate_setup_path, "GATE-SETUP")
    bundle = _regular_bytes(bundle_path, "release Git bundle")
    setup_id = gate_setup.get("authorization", {}).get("setupId")
    if not isinstance(setup_id, str) or SETUP_ID_RE.fullmatch(setup_id) is None:
        raise InstallError("GATE-SETUP setup ID is invalid")
    for path, suffix in (
        (gate_plan_path, "gate-plan"), (target_proof_path, "target-proof"),
        (release_manifest_path, "release-manifest"),
        (gate_setup_path, "gate-setup"), (bundle_path, "bundle"),
        (Path(__file__), "installer"),
    ):
        _safe_setup_staging(path, setup_id, suffix)
    authorization, release = _validate_setup_inputs(
        gate_plan=gate_plan, target=target, manifest=manifest,
        gate_setup=gate_setup, bundle=bundle, self_sha256=self_sha,
        now=datetime.now(timezone.utc),
    )
    commit = authorization["frameworkCommit"]
    tree = authorization["frameworkTree"]
    if COMMIT_RE.fullmatch(commit) is None or COMMIT_RE.fullmatch(tree) is None:
        raise InstallError("release commit or tree identity is malformed")
    members = release.get("bundleMembers")
    if not isinstance(members, dict) or set(members) != {
        "superproject.bundle", "upstream-teastore.bundle",
    }:
        raise InstallError("release bundle member manifest differs")
    extracted: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:") as archive:
            rows = archive.getmembers()
            if [row.name for row in rows] != [
                "superproject.bundle", "upstream-teastore.bundle",
            ] or any(not row.isreg() for row in rows):
                raise InstallError("release bundle archive membership/type differs")
            for row in rows:
                handle = archive.extractfile(row)
                if handle is None:
                    raise InstallError("release bundle member is unreadable")
                extracted[row.name] = handle.read()
    except (tarfile.TarError, OSError) as exc:
        raise InstallError(f"release bundle archive is invalid: {exc}") from exc
    for name, payload in extracted.items():
        identity = members.get(name)
        if not isinstance(identity, dict) or set(identity) != {
            "sha256", "bytes", "commit", "tree",
        } or identity.get("bytes") != len(payload) or (
            identity.get("sha256") != hashlib.sha256(payload).hexdigest()
        ):
            raise InstallError(f"release bundle member digest differs: {name}")

    uid = authorization["executionUid"]
    gid = authorization["executionGid"]
    release_root = Path(authorization["releaseRoot"])
    results_root = Path(authorization["resultsRoot"])
    pending = RELEASES_ROOT / f".pending-{setup_id}"
    _reject_install_collision(release_root, pending)

    # No candidate-v4 root is created until every gate, hash, path, and bundle
    # head above has passed.  Subsequent failure removes only this setup's exact
    # pending clone; it never reuses or blesses a partial install.
    _mkdir_checked(RELEASES_ROOT, owner_uid=uid, owner_gid=gid)
    _mkdir_checked(RESULTS_ROOT, owner_uid=uid, owner_gid=gid)
    _mkdir_checked(LEASE_PATH.parent, owner_uid=uid, owner_gid=gid)
    _mkdir_checked(results_root, owner_uid=uid, owner_gid=gid)
    setup_sha = _canonical_sha(gate_setup)
    receipt: dict[str, Any] = {
        "schemaVersion": 1,
        "kind": RELEASE_INSTALL_KIND,
        "state": "installed",
        "setupId": setup_id,
        "target": TARGET,
        "transportUser": TRANSPORT_USER,
        "executionUser": authorization["executionUser"],
        "executionUid": uid,
        "executionGid": gid,
        "executionMethod": authorization["executionMethod"],
        "frameworkCommit": commit,
        "frameworkTree": tree,
        "bundleSha256": release["bundleSha256"],
        "releaseManifestSha256": _canonical_sha(manifest),
        "gateSetupSha256": setup_sha,
        "releaseRoot": str(release_root),
        "resultsRoot": str(results_root),
        "exclusiveLeasePath": str(LEASE_PATH),
        "controllerDigests": release["controllerDigests"],
        "installedAt": datetime.now(timezone.utc).isoformat(),
        "runtimeExecuted": False,
        "promotionAuthorized": False,
    }
    retained = {
        "gate-plan.json": gate_plan_bytes,
        "target-proof.json": target_bytes,
        "release-manifest.json": manifest_bytes,
        "gate-setup.json": gate_setup_bytes,
    }
    installed = False
    image_build: dict[str, Any] | None = None
    bundle_members_root = Path(
        tempfile.mkdtemp(prefix=f".candidate-v4-{setup_id}-", dir="/root")
    )
    try:
        for name, payload in extracted.items():
            _write_exclusive(
                bundle_members_root / name, payload, uid=0, gid=0,
            )
        super_bundle = bundle_members_root / "superproject.bundle"
        source_bundle = bundle_members_root / "upstream-teastore.bundle"
        for name, path in (
            ("superproject.bundle", super_bundle),
            ("upstream-teastore.bundle", source_bundle),
        ):
            heads = _run(("git", "bundle", "list-heads", str(path)))
            if heads.returncode != 0 or heads.stdout.decode(
                "ascii", errors="strict"
            ).splitlines() != [f"{members[name]['commit']} HEAD"]:
                raise InstallError(f"Git bundle HEAD differs: {name}")
        cloned = _run((
            "git", "-c", "core.hooksPath=/dev/null", "clone", "--no-checkout",
            "--no-hardlinks", str(super_bundle), str(pending),
        ))
        if cloned.returncode != 0:
            raise InstallError("exact release Git bundle could not be cloned")
        checkout = _run((
            "git", "-c", "core.hooksPath=/dev/null", "-C", str(pending),
            "checkout", "--detach", "--force", commit,
        ))
        if checkout.returncode != 0:
            raise InstallError("exact release commit could not be checked out")
        source_root = pending / "upstream/teastore"
        source_cloned = _run((
            "git", "-c", "core.hooksPath=/dev/null", "clone", "--no-checkout",
            "--no-hardlinks", str(source_bundle), str(source_root),
        ))
        source_checkout = _run((
            "git", "-c", "core.hooksPath=/dev/null", "-C", str(source_root),
            "checkout", "--detach", "--force",
            release["submoduleCommits"]["upstream/teastore"],
        ))
        source_commit = _run(("git", "-C", str(source_root), "rev-parse", "HEAD"))
        source_tree = _run(("git", "-C", str(source_root), "rev-parse", "HEAD^{tree}"))
        source_status = _run((
            "git", "-C", str(source_root), "status", "--porcelain=v1",
            "--untracked-files=all",
        ))
        if (
            source_cloned.returncode != 0
            or source_checkout.returncode != 0
            or source_commit.returncode != 0
            or source_commit.stdout.decode().strip()
            != release["submoduleCommits"]["upstream/teastore"]
            or source_tree.returncode != 0
            or source_tree.stdout.decode().strip()
            != members["upstream-teastore.bundle"]["tree"]
            or source_status.returncode != 0
            or source_status.stdout
        ):
            raise InstallError("installed TeaStore submodule commit/tree differs")
        observed_commit = _run(("git", "-C", str(pending), "rev-parse", "HEAD"))
        observed_tree = _run(("git", "-C", str(pending), "rev-parse", "HEAD^{tree}"))
        status = _run((
            "git", "-C", str(pending), "status", "--porcelain=v1",
            "--untracked-files=all", "--ignore-submodules=none",
        ))
        if (
            observed_commit.returncode != 0
            or observed_commit.stdout.decode().strip() != commit
            or observed_tree.returncode != 0
            or observed_tree.stdout.decode().strip() != tree
            or status.returncode != 0
            or status.stdout
        ):
            raise InstallError("installed release commit/tree/clean state differs")
        for name, digest in release["controllerDigests"].items():
            # Controller map names are authority labels; paths are recovered
            # from the installed adapter only after that adapter's own digest
            # has been checked below by the fixed required path set.
            if not isinstance(name, str) or SHA256_RE.fullmatch(str(digest)) is None:
                raise InstallError("release controller digest map is malformed")
        required = {
            "candidate-release-installer": (
                "modules/teastore/execution/candidate_release_installer.py"
            ),
            "candidate-remote-controller": (
                "modules/teastore/execution/candidate_remote_controller.py"
            ),
            "bounded-candidate-transport": (
                "modules/teastore/execution/candidate_transport.py"
            ),
            "candidate-runtime-adapter": (
                "modules/teastore/execution/candidate_runtime_adapter.py"
            ),
        }
        for name, relative in required.items():
            payload = _regular_bytes(pending / relative, f"installed {name}")
            if hashlib.sha256(payload).hexdigest() != release["controllerDigests"].get(name):
                raise InstallError(f"installed controller bytes differ: {name}")
        # The GATE-SETUP explicitly authorizes this build.  Execute it as the
        # reviewed unprivileged identity before the release is atomically
        # published, and retain the exact target-produced inspection receipt.
        _chown_tree(pending, uid, gid)
        image_build_pending = pending / ".candidate-image-build.json"
        image_builder = pending / "modules/teastore/execution/candidate_release_installer.py"
        build_result = _run((
            RUNUSER, "--user", EXECUTION_USER, "--", TARGET_PYTHON, "-I", str(image_builder),
            "build-images", "--working-root", str(pending),
            "--final-release-root", str(release_root), "--setup-id", setup_id,
            "--framework-commit", commit, "--authorization-deadline",
            authorization["authorizationDeadline"], "--output", str(image_build_pending),
        ))
        if build_result.returncode != 0:
            detail = (build_result.stdout + build_result.stderr).decode(
                "utf-8", errors="replace",
            )[:1000]
            raise InstallError(f"target patched-image build failed: {detail}")
        image_build, image_build_bytes = _json_file(
            image_build_pending, "target patched-image build receipt",
        )
        _validate_image_build_receipt(
            image_build, setup_id=setup_id, framework_commit=commit,
            release_root=pending,
        )
        image_build_pending.unlink()
        receipt["imageBuildReceiptSha256"] = _canonical_sha(image_build)
        receipt["imageBuild"] = image_build
        # Must precede the seal: the tree goes read-only immediately after.
        receipt["activationCompile"] = compile_activation_artifacts(
            pending, uid=uid, gid=gid,
        )
        receipt["installedAt"] = datetime.now(timezone.utc).isoformat()
        retained["patched-image-build.json"] = image_build_bytes
        retained["release-install.json"] = json.dumps(
            receipt, indent=2, sort_keys=True, allow_nan=False,
        ).encode() + b"\n"
        # The receipt set is part of the pending tree before its one atomic
        # rename. A crash can therefore expose either no final checkout or one
        # final checkout with the exact setup/install receipts; never a final
        # checkout whose provenance has to be reconstructed after the fact.
        receipt_dir = pending / ".git/candidate-v4-receipts"
        receipt_dir.mkdir(mode=0o700)
        for name, payload in retained.items():
            _write_exclusive(receipt_dir / name, payload, uid=uid, gid=gid)
        _seal_release_tree(pending)
        pending.rename(release_root)
        installed = True
    finally:
        rollback_errors: list[str] = []
        if not installed and image_build is not None:
            for service in reversed(tuple(PATCHED_IMAGE_INPUTS)):
                prior = image_build["priorDeclaredImageConfigIds"][service]
                argv = (
                    ("docker", "tag", prior, RUNTIME_IMAGES[service])
                    if prior is not None
                    else ("docker", "image", "rm", RUNTIME_IMAGES[service])
                )
                result = _run(argv)
                if result.returncode != 0:
                    rollback_errors.append(service)
            for tag in image_build["uniqueBuildTags"].values():
                result = _run(("docker", "image", "rm", "--force", tag))
                if result.returncode != 0:
                    rollback_errors.append(tag)
        if not installed and pending.exists() and not pending.is_symlink():
            shutil.rmtree(pending)
        shutil.rmtree(bundle_members_root)
        if rollback_errors:
            raise InstallError(
                "outer release transaction could not roll back image tags: "
                + ", ".join(rollback_errors)
            )

    for staged in (
        gate_plan_path, target_proof_path, release_manifest_path, gate_setup_path,
        bundle_path,
    ):
        staged.unlink(missing_ok=True)
    Path(__file__).unlink(missing_ok=True)
    return receipt


def launch_campaign(
    *, package_payload: bytes, expected_package_sha256: str, output: Path,
    framework_commit: str, release_binding_sha256: str,
) -> dict[str, Any]:
    """Install one stdin package O_EXCL, then hand off to the bound user."""

    _require_root_transport()
    if hashlib.sha256(package_payload).hexdigest() != expected_package_sha256:
        raise InstallError("runtime package transfer digest differs")
    package = _json_bytes(package_payload, "runtime package")
    if (
        package.get("kind") != PACKAGE_KIND
        or package.get("frameworkCommit") != framework_commit
        or package.get("transportUser") != TRANSPORT_USER
        or package.get("releaseBindingSha256") != release_binding_sha256
        or package.get("releaseRoot") != str(Path(__file__).resolve().parents[3])
        or package.get("resultsRoot") != str(output.parent)
        # The runtime package names this field outerLeasePath; exclusiveLeasePath
        # is the release-binding/receipt spelling. The two are paired explicitly
        # in _installed_release_binding, and the remote controller reads
        # package["outerLeasePath"], so reading the receipt spelling out of the
        # package here always compared None and refused every launch.
        or package.get("outerLeasePath") != str(LEASE_PATH)
        or not isinstance(package.get("campaignId"), str)
        or CAMPAIGN_RE.fullmatch(package["campaignId"]) is None
        or output.name != package["campaignId"]
        or output.exists()
        or output.is_symlink()
    ):
        raise InstallError("runtime package release, output, or identity differs")
    _installed_release_binding(package)
    _installed_readiness_binding(package)
    # Recheck only current read-only conflicts immediately before the package
    # is charged.  This never cleans or mutates a stopped foreign project.
    runtime_preflight()
    execution_user = package.get("executionUser")
    method = package.get("executionMethod")
    if execution_user != EXECUTION_USER or method != EXECUTION_METHOD:
        raise InstallError("runtime execution identity or method differs")
    try:
        account = pwd.getpwnam(execution_user)
    except KeyError as exc:
        raise InstallError("runtime execution account is absent") from exc
    if (
        account.pw_uid != EXECUTION_UID
        or account.pw_gid != EXECUTION_GID
        or package.get("executionUid") != EXECUTION_UID
        or package.get("executionGid") != EXECUTION_GID
        or EXECUTION_DOCKER_GID not in os.getgrouplist(EXECUTION_USER, EXECUTION_GID)
    ):
        raise InstallError("runtime execution uid/gid differs")
    access, _ = _docker_probe(execution_user)
    if not access:
        raise InstallError("bound runtime execution user no longer has Docker access")

    supervisor = _run((SYSTEMD_RUN, "--version"))
    if (
        supervisor.returncode != 0
        or not supervisor.stdout.startswith(b"systemd ")
    ):
        raise InstallError("detached systemd campaign supervisor is unavailable")

    package_dir = Path(package["resultsRoot"]) / ".packages"
    _mkdir_checked(package_dir, owner_uid=account.pw_uid, owner_gid=account.pw_gid)
    package_path = package_dir / f"{package['campaignId']}.json"
    _write_exclusive(
        package_path, package_payload, uid=account.pw_uid, gid=account.pw_gid,
    )
    controller = Path(package["releaseRoot"]) / REMOTE_CONTROLLER
    lease_receipt_dir = Path(package["resultsRoot"]) / ".lease-receipts"
    _mkdir_checked(
        lease_receipt_dir, owner_uid=account.pw_uid, owner_gid=account.pw_gid,
    )
    log_dir = Path(package["resultsRoot"]) / ".controller-logs"
    _mkdir_checked(log_dir, owner_uid=account.pw_uid, owner_gid=account.pw_gid)
    log_path = log_dir / f"{package['campaignId']}.log"
    command, unit_name = _detached_controller_command(
        {**package, "packagePath": str(package_path)}, controller=controller,
        output=output, framework_commit=framework_commit,
        package_sha256=expected_package_sha256, log_path=log_path,
    )
    result = _run(command, cwd=Path(package["releaseRoot"]))
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).decode("utf-8", errors="replace")[:500]
        raise InstallError(f"detached candidate controller failed to start: {detail}")
    return {
        "schemaVersion": 1,
        "kind": "teastore-candidate-remote-start-v1",
        "campaignId": package["campaignId"],
        "frameworkCommit": framework_commit,
        "packageSha256": expected_package_sha256,
        "unitName": unit_name,
        "state": "started",
        "promotionAuthorized": False,
    }


def supervise_campaign(
    *, controller: Path, package_path: Path, output: Path,
    framework_commit: str, package_sha256: str,
) -> dict[str, Any]:
    """Own the durable boundary before the unprivileged controller can start."""

    _require_root_transport()
    package_payload = _regular_bytes(package_path, "supervised runtime package")
    if hashlib.sha256(package_payload).hexdigest() != package_sha256:
        raise InstallError("supervised runtime package digest differs")
    package = _json_bytes(package_payload, "supervised runtime package")
    if (
        package.get("frameworkCommit") != framework_commit
        or package.get("campaignId") != output.name
        or package.get("resultsRoot") != str(output.parent)
        or Path(package.get("releaseRoot", "")) / REMOTE_CONTROLLER != controller
    ):
        raise InstallError("supervised campaign identity differs")
    state_dir = output.parent / ".supervisor"
    _mkdir_checked(state_dir, owner_uid=0, owner_gid=0)
    state_path = state_dir / f"{package['campaignId']}.json"
    started = datetime.now(timezone.utc).isoformat()
    command = [
        RUNUSER, "--user", EXECUTION_USER, "--", TARGET_PYTHON, "-I",
        str(controller), "launch", "--package", str(package_path),
        "--output", str(output), "--framework-commit", framework_commit,
        "--package-sha256", package_sha256,
    ]
    result = _run(command, cwd=Path(package["releaseRoot"]))
    terminal = {
        "schemaVersion": 1,
        "kind": "teastore-candidate-supervisor-terminal-v1",
        "campaignId": package["campaignId"],
        "setupId": package["setupId"],
        "packageSha256": package_sha256,
        "startedAt": started,
        "finishedAt": datetime.now(timezone.utc).isoformat(),
        "returnCode": result.returncode,
        "state": "complete" if result.returncode == 0 else "abstained",
    }
    if not state_path.exists():
        _write_exclusive(
            state_path,
            json.dumps(terminal, allow_nan=False, indent=2, sort_keys=True).encode() + b"\n",
            uid=0, gid=0,
        )
    if result.returncode != 0:
        abort_path = output / "campaign-abort.json"
        if not abort_path.exists():
            output.mkdir(mode=0o700, exist_ok=True)
            abort = {
                "schemaVersion": 1,
                "kind": "teastore-candidate-controller-abort-v1",
                "campaignId": package["campaignId"], "setupId": package["setupId"],
                "frameworkCommit": framework_commit,
                "packageSha256": package_sha256,
                "campaignSha256": package["campaignSha256"],
                "stage": "supervisor-controller-handoff",
                "errorType": "ControllerProcessExit",
                "error": f"controller process exited {result.returncode}",
                "journalRows": 0, "validCells": 0,
                "experimentalState": "ABSTAINED", "retryAllowed": False,
                "promotionAuthorized": False,
                "recordedAt": datetime.now(timezone.utc).isoformat(),
            }
            _write_exclusive(
                abort_path,
                json.dumps(abort, allow_nan=False, indent=2, sort_keys=True).encode() + b"\n",
                uid=0, gid=0,
            )
        # The controller's own stdout and stderr were captured and then
        # dropped, so the only surviving record of why a cell failed was
        # "exited 2" -- the same information loss as F-ADH-039 and F-ADH-051,
        # one layer further in.
        detail = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        raise InstallError(
            f"candidate controller exited {result.returncode}: "
            f"{detail.strip()[-2000:] or 'no controller output'}"
        )
    return terminal


def _parse_systemd_state(payload: bytes, *, unit_name: str) -> dict[str, Any]:
    try:
        lines = payload.decode("utf-8", errors="strict").splitlines()
    except UnicodeError as exc:
        raise InstallError("campaign systemd state is not UTF-8") from exc
    values: dict[str, str] = {}
    for line in lines:
        if "=" not in line:
            raise InstallError("campaign systemd state row is malformed")
        key, value = line.split("=", 1)
        if key in values:
            raise InstallError("campaign systemd state contains a duplicate field")
        values[key] = value
    if set(values) != {"LoadState", "ActiveState", "SubState", "Result", "ExecMainStatus"}:
        raise InstallError("campaign systemd state fields differ")
    if values["LoadState"] == "not-found":
        # A launch that fails before systemd-run leaves no unit behind at all,
        # and the unit name is now scoped to the attempt, so "absent" is also
        # the honest reading for a package that is staged and never started.
        # Refusing to parse it made campaign-status unanswerable in exactly the
        # state where launch tells the operator to go and run campaign-status.
        if (
            values["ActiveState"] != "inactive"
            or values["SubState"] != "dead"
            or values["Result"] != "success"
            or values["ExecMainStatus"] != "0"
        ):
            raise InstallError("absent campaign systemd unit reports live state")
    elif (
        values["LoadState"] != "loaded"
        or values["ActiveState"] not in {"active", "inactive", "failed"}
        or values["SubState"] not in {"running", "dead", "failed", "exited"}
        or values["Result"] not in {"success", "exit-code", "timeout", "signal"}
        or not values["ExecMainStatus"].isdigit()
    ):
        raise InstallError("campaign systemd state values differ")
    return {
        "unitName": unit_name,
        "loadState": values["LoadState"],
        "activeState": values["ActiveState"],
        "subState": values["SubState"],
        "result": values["Result"],
        "execMainStatus": int(values["ExecMainStatus"]),
        "rawSha256": hashlib.sha256(payload).hexdigest(),
    }


def _host_lease_held() -> bool:
    """Probe the outer lease without taking it, for any status shape."""

    if not (LEASE_PATH.exists() or LEASE_PATH.is_symlink()):
        return False
    flags = os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    lease_fd = os.open(LEASE_PATH, flags)
    try:
        if not stat.S_ISREG(os.fstat(lease_fd).st_mode):
            raise InstallError("candidate lease is not a regular file")
        try:
            fcntl.flock(lease_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(lease_fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(lease_fd)


def campaign_status(
    *, setup_id: str, campaign_id: str, expected_package_sha256: str,
    release_binding_sha256: str,
) -> dict[str, Any]:
    """Inspect one retained package/result without resuming or mutating it."""

    _require_root_transport()
    if (
        SETUP_ID_RE.fullmatch(setup_id) is None
        or CAMPAIGN_RE.fullmatch(campaign_id) is None
        or SHA256_RE.fullmatch(expected_package_sha256) is None
        or SHA256_RE.fullmatch(release_binding_sha256) is None
    ):
        raise InstallError("campaign status identity is malformed")
    results_root = RESULTS_ROOT / setup_id
    package_path = results_root / ".packages" / f"{campaign_id}.json"
    output = results_root / campaign_id
    installed = _json_file(
        Path(__file__).resolve().parents[3]
        / ".git/candidate-v4-receipts/release-install.json",
        "installed release receipt",
    )[0]
    binding_keys = RELEASE_BINDING_KEYS
    if (
        not isinstance(installed, dict)
        or not binding_keys <= set(installed)
        or installed.get("setupId") != setup_id
        or installed.get("resultsRoot") != str(results_root)
        or _canonical_sha({key: installed[key] for key in binding_keys})
        != release_binding_sha256
    ):
        raise InstallError("campaign status release binding differs")
    unit_name = _campaign_unit_name(campaign_id, setup_id, expected_package_sha256)
    systemd_result = _run((
        _systemctl(), "show", unit_name, "--no-pager",
        "--property=LoadState", "--property=ActiveState", "--property=SubState",
        "--property=Result", "--property=ExecMainStatus",
    ))
    if systemd_result.returncode != 0 or systemd_result.stderr:
        raise InstallError("campaign systemd terminal state is unavailable")
    systemd_state = _parse_systemd_state(systemd_result.stdout, unit_name=unit_name)
    if not package_path.exists() or package_path.is_symlink():
        # Every state shares one document shape: the transport compares the key
        # set exactly, so the short document this branch used to return could
        # never be accepted by the only reader that asks for it.
        return {
            "schemaVersion": 1,
            "kind": "teastore-candidate-remote-status-v1",
            "setupId": setup_id,
            "campaignId": campaign_id,
            "packageSha256": expected_package_sha256,
            "state": "not-started",
            "leaseHeld": False,
            "hostLeaseHeld": _host_lease_held(),
            "resultExists": output.exists(),
            "journalRows": 0,
            "terminalExists": False,
            "abortExists": False,
            "systemdState": systemd_state,
            "leaseReceiptSha256": None,
            "promotionAuthorized": False,
        }
    package_payload = _regular_bytes(package_path, "retained runtime package")
    if hashlib.sha256(package_payload).hexdigest() != expected_package_sha256:
        raise InstallError("retained runtime package digest differs")
    package = _json_bytes(package_payload, "retained runtime package")
    if (
        package.get("setupId") != setup_id
        or package.get("campaignId") != campaign_id
        or package.get("releaseBindingSha256") != release_binding_sha256
        or package.get("resultsRoot") != str(results_root)
    ):
        raise InstallError("retained runtime package status binding differs")
    _installed_release_binding(package)
    host_lease_held = _host_lease_held()
    result_exists = output.exists() and not output.is_symlink()
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise InstallError("retained campaign result path is not a real directory")
    journal_rows = 0
    terminal_exists = False
    abort_exists = False
    run_count = _installed_run_count()
    if result_exists:
        journal = output / "runtime-journal.jsonl"
        if journal.exists() or journal.is_symlink():
            journal_rows = len(_regular_bytes(journal, "runtime journal").splitlines())
            if journal_rows > run_count:
                raise InstallError("runtime journal exceeds the fixed campaign")
        terminal = output / "campaign-terminal-validation.json"
        terminal_exists = terminal.exists() and not terminal.is_symlink()
        if terminal.exists() or terminal.is_symlink():
            _regular_bytes(terminal, "campaign terminal validation")
        abort = output / "campaign-abort.json"
        abort_exists = abort.exists() and not abort.is_symlink()
        if abort.exists() or abort.is_symlink():
            abort_document = _json_bytes(
                _regular_bytes(abort, "campaign abort"), "campaign abort",
            )
            if (
                abort_document.get("kind")
                != "teastore-candidate-controller-abort-v1"
                or abort_document.get("campaignId") != campaign_id
                or abort_document.get("setupId") != setup_id
                or abort_document.get("frameworkCommit")
                != package.get("frameworkCommit")
                or abort_document.get("packageSha256") != expected_package_sha256
                or abort_document.get("campaignSha256")
                != package.get("campaignSha256")
                or abort_document.get("experimentalState") != "ABSTAINED"
                or abort_document.get("retryAllowed") is not False
                or abort_document.get("promotionAuthorized") is not False
            ):
                raise InstallError("retained campaign abort identity differs")
    pending_lease_receipt = results_root / ".lease-receipts" / f"{campaign_id}.pending.json"
    final_lease_receipt = results_root / ".lease-receipts" / f"{campaign_id}.json"
    lease_held = host_lease_held and pending_lease_receipt.is_file()
    lease_receipt_path = pending_lease_receipt if lease_held else final_lease_receipt
    lease_receipt = (
        _json_file(lease_receipt_path, "campaign lease receipt")[0]
        if lease_receipt_path.is_file() else None
    )
    # A package is written before systemd-run is invoked, so "staged, and the
    # unit never came into existence" is a reachable, entirely honest state --
    # and it is precisely the state launch tells the operator to inspect with
    # campaign-status.  Demanding a lease receipt here made that instruction
    # impossible to follow.  The shape is pinned tightly so it cannot mask a
    # campaign that ran and then lost its receipt.
    never_started = (
        systemd_state["loadState"] == "not-found"
        and not result_exists
        and journal_rows == 0
        and not host_lease_held
    )
    if lease_receipt is None and not abort_exists and not never_started:
        raise InstallError("campaign lease ownership receipt is absent")
    if lease_receipt is not None and (
        not isinstance(lease_receipt, dict)
        or set(lease_receipt) != {
            "schemaVersion", "kind", "campaignId", "setupId", "packageSha256",
            "leasePath", "ownerPid", "ownerToken", "device", "inode",
            "acquiredAt", "state", "releasedAt", "releaseObserved",
            "successorMayAcquire",
        }
        or lease_receipt.get("schemaVersion") != 1
        or lease_receipt.get("kind") != "teastore-candidate-lease-receipt-v1"
        or lease_receipt.get("campaignId") != campaign_id
        or lease_receipt.get("setupId") != setup_id
        or lease_receipt.get("packageSha256") != expected_package_sha256
        or lease_receipt.get("leasePath") != str(LEASE_PATH)
        or type(lease_receipt.get("ownerPid")) is not int
        or lease_receipt["ownerPid"] <= 0
        or not isinstance(lease_receipt.get("ownerToken"), str)
        or SHA256_RE.fullmatch(lease_receipt["ownerToken"]) is None
        or type(lease_receipt.get("device")) is not int
        or type(lease_receipt.get("inode")) is not int
    ):
        raise InstallError("campaign lease receipt identity differs")
    if lease_receipt is not None:
        acquired_at = _timestamp(lease_receipt["acquiredAt"], "lease acquiredAt")
    if lease_held and lease_receipt is not None:
        if (
            lease_receipt["state"] != "held"
            or lease_receipt["releasedAt"] is not None
            or lease_receipt["releaseObserved"] is not False
            or lease_receipt["successorMayAcquire"] is not False
        ):
            raise InstallError("held campaign lease receipt differs")
    elif lease_receipt is not None:
        released_at = _timestamp(lease_receipt["releasedAt"], "lease releasedAt")
        if (
            released_at < acquired_at
            or lease_receipt["state"] != "released"
            or lease_receipt["releaseObserved"] is not True
            or lease_receipt["successorMayAcquire"] is not True
        ):
            raise InstallError("released campaign lease receipt differs")
    if lease_held:
        if systemd_state["activeState"] != "active":
            raise InstallError("held lease disagrees with systemd active state")
        state = "running"
    elif terminal_exists and journal_rows == run_count and not abort_exists:
        if systemd_state["result"] != "success" or systemd_state["execMainStatus"] != 0:
            raise InstallError("terminal campaign disagrees with systemd result")
        state = "complete"
    elif result_exists:
        if systemd_state["activeState"] == "active":
            raise InstallError("stopped campaign disagrees with systemd active state")
        state = "stopped"
    else:
        state = "staged"
    return {
        "schemaVersion": 1,
        "kind": "teastore-candidate-remote-status-v1",
        "setupId": setup_id,
        "campaignId": campaign_id,
        "packageSha256": expected_package_sha256,
        "state": state,
        "leaseHeld": lease_held,
        "hostLeaseHeld": host_lease_held,
        "resultExists": result_exists,
        "journalRows": journal_rows,
        "terminalExists": terminal_exists,
        "abortExists": abort_exists,
        "systemdState": systemd_state,
        "leaseReceiptSha256": (
            _canonical_sha(lease_receipt) if lease_receipt is not None else None
        ),
        "promotionAuthorized": False,
    }


def _generate_installed_readiness(
    *, pending: Path, spec_payload: bytes, ingress_archive_sha256: str,
    install: Mapping[str, Any], release_binding_sha256: str,
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    """Construct the entire readiness tree from installed bytes and live probes."""
    adapter = _installed_adapter()
    checker_path = Path(install["releaseRoot"]) / (
        "modules/teastore/validation/candidate_readiness.py"
    )
    spec = _exact(_json_bytes(spec_payload, "readiness capture spec"), {
        "schemaVersion", "kind", "seams", "descriptorCanonicalSha256",
        "compiledPlanCanonicalSha256", "releaseBindingSha256",
    }, "readiness capture spec")
    if (
        spec.get("schemaVersion") != 1
        or spec.get("kind") != "teastore-candidate-readiness-capture-spec-v2"
        or spec.get("seams") != list(adapter.READINESS_SEAMS)
        or spec.get("releaseBindingSha256") != release_binding_sha256
    ):
        raise InstallError("readiness capture spec identity differs")

    def write(relative: str, value: Any | bytes) -> bytes:
        destination = pending / relative
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = value if isinstance(value, bytes) else (
            json.dumps(value, allow_nan=False, indent=2, sort_keys=True).encode() + b"\n"
        )
        _write_exclusive(destination, payload, uid=0, gid=0)
        return payload

    # The descriptor is an installed code/material input. The installed,
    # construction-only orchestrator recompiles the plan and campaign manifest.
    orchestrator_path = Path(install["releaseRoot"]) / (
        "modules/teastore/execution/candidate_orchestrator.py"
    )
    module_spec = importlib.util.spec_from_file_location(
        "teastore_installed_readiness_orchestrator", orchestrator_path,
    )
    if module_spec is None or module_spec.loader is None:
        raise InstallError("installed campaign materializer is unavailable")
    orchestrator = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(orchestrator)
    campaign_root = pending / "artifacts/campaign"
    campaign_root.mkdir(parents=True, mode=0o700)
    os.chown(campaign_root, 0, 0)
    materialized = orchestrator.materialize_campaign(
        campaign_root,
        Path(install["releaseRoot"]) / adapter.EPOCH["descriptorRelative"],
    )
    bindings = adapter.inspect_campaign(campaign_root, install["frameworkCommit"])
    if (
        bindings.descriptor_sha256 != spec["descriptorCanonicalSha256"]
        or bindings.plan_sha256 != spec["compiledPlanCanonicalSha256"]
        or len(bindings.run_ids) != adapter.RUN_COUNT
    ):
        raise InstallError("root-generated frozen campaign differs from capture spec")

    receipt_dir = Path(install["releaseRoot"]) / ".git/candidate-v4-receipts"
    setup_artifacts: dict[str, Any] = {}
    for camel, stem in (
        ("gatePlan", "gate-plan"), ("targetProof", "target-proof"),
        ("releaseManifest", "release-manifest"), ("gateSetup", "gate-setup"),
        ("releaseInstall", "release-install"),
    ):
        payload = _regular_bytes(receipt_dir / f"{stem}.json", f"installed {stem}")
        relative = f"artifacts/setup/{stem}.json"
        write(relative, payload)
        setup_artifacts[f"{camel}Path"] = relative.removeprefix("artifacts/")
        setup_artifacts[f"{camel}BytesSha256"] = hashlib.sha256(payload).hexdigest()

    images = copy.deepcopy(install["imageBuild"]["imageDigests"])
    context = {
        "frameworkCommit": bindings.framework_commit,
        "descriptorCanonicalSha256": bindings.descriptor_sha256,
        "compiledPlanCanonicalSha256": bindings.plan_sha256,
        "imageDigests": images,
    }
    context_payload = _canonical(context) + b"\n"
    validator_sha = bindings.controller_sha256["candidate-readiness-checker"]
    checker = adapter._candidate_readiness_module()
    seams: dict[str, Any] = {}
    for seam in adapter.READINESS_SEAMS:
        argv = [TARGET_PYTHON, "-I", "modules/teastore/validation/candidate_readiness.py", "probe", seam]
        result = subprocess.run(
            argv, input=context_payload, cwd=install["releaseRoot"], check=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C", "LC_ALL": "C"},
        )
        raw = {
            "checker": f"candidate-readiness-v2:{seam}", "argv": argv,
            "exitCode": result.returncode,
            "stdout": result.stdout.decode("utf-8", errors="strict"),
            "stderr": result.stderr.decode("utf-8", errors="strict"),
            "inputSha256": _canonical_sha(context),
        }
        positive = {
            "schemaVersion": 1, "kind": checker.INPUT_KIND, "seam": seam,
            "target": TARGET, "frameworkCommit": bindings.framework_commit,
            "descriptorCanonicalSha256": bindings.descriptor_sha256,
            "compiledPlanCanonicalSha256": bindings.plan_sha256,
            "imageDigests": images, "capturedAt": datetime.now(timezone.utc).isoformat(),
            "rawObservations": raw,
        }
        positive_report = checker.check_input(
            positive, seam=seam, framework_commit=bindings.framework_commit,
            descriptor_sha256=bindings.descriptor_sha256,
            plan_sha256=bindings.plan_sha256, image_digests=images,
        )
        if positive_report.get("verdict") != "pass":
            raise InstallError(f"live installed readiness probe blocked: {seam}")
        defect = copy.deepcopy(positive)
        facts = copy.deepcopy(checker.SEAM_EXPECTED_VALUES[seam])
        first = next(iter(facts))
        original = facts[first]
        facts[first] = (not original if isinstance(original, bool) else
                        original + 1 if isinstance(original, int) else
                        "planted-defect")
        defect["rawObservations"]["stdout"] = json.dumps(
            {"facts": facts}, sort_keys=True,
        ) + "\n"
        defect_report = checker.check_input(
            defect, seam=seam, framework_commit=bindings.framework_commit,
            descriptor_sha256=bindings.descriptor_sha256,
            plan_sha256=bindings.plan_sha256, image_digests=images,
        )
        if defect_report.get("verdict") != "blocked":
            raise InstallError(f"planted readiness defect escaped: {seam}")
        paths = {
            "pi": f"artifacts/pairs/{seam}.positive.input.json",
            "pr": f"artifacts/pairs/{seam}.positive.report.json",
            "di": f"artifacts/pairs/{seam}.defect.input.json",
            "dr": f"artifacts/pairs/{seam}.defect.report.json",
        }
        payloads = {"pi": write(paths["pi"], positive), "pr": write(paths["pr"], positive_report),
                    "di": write(paths["di"], defect), "dr": write(paths["dr"], defect_report)}
        observations = lambda i, r: {
            "inputPath": paths[i].removeprefix("artifacts/"),
            "inputSha256": hashlib.sha256(payloads[i]).hexdigest(),
            "reportPath": paths[r].removeprefix("artifacts/"),
            "reportSha256": hashlib.sha256(payloads[r]).hexdigest(),
        }
        evidence = {"schemaVersion": 1, "kind": adapter.READINESS_EVIDENCE_KIND,
                    "seam": seam, "status": "pass", "validatorSha256": validator_sha,
                    "observations": observations("pi", "pr")}
        witness = {"schemaVersion": 1, "kind": adapter.FAILURE_WITNESS_KIND,
                   "seam": seam, "status": "detected", "plantedDefect": first,
                   "checkerExitCode": 2, "validatorSha256": validator_sha,
                   "observations": observations("di", "dr")}
        ep = f"artifacts/receipts/{seam}.positive.json"
        wp = f"artifacts/receipts/{seam}.defect.json"
        eb, wb = write(ep, evidence), write(wp, witness)
        seams[seam] = {"status": "pass", "evidencePath": ep.removeprefix("artifacts/"),
                       "evidenceSha256": hashlib.sha256(eb).hexdigest(),
                       "failureWitnessPath": wp.removeprefix("artifacts/"),
                       "failureWitnessSha256": hashlib.sha256(wb).hexdigest()}

    transport_relative = "artifacts/transport/candidate_transport.py"
    transport_bytes = _regular_bytes(
        Path(install["releaseRoot"]) / "modules/teastore/execution/candidate_transport.py",
        "installed bounded transport",
    )
    write(transport_relative, transport_bytes)
    entries = []
    artifact_root = pending / "artifacts"
    for path in sorted(p for p in artifact_root.rglob("*") if p.is_file()):
        payload = _regular_bytes(path, "generated capture artifact")
        entries.append({"path": path.relative_to(artifact_root).as_posix(),
                        "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    capture_manifest = {"schemaVersion": 1, "kind": "teastore-candidate-root-capture-manifest-v2",
                        "ingressArchiveSha256": ingress_archive_sha256,
                        "entries": entries, "entriesCanonicalSha256": _canonical_sha(entries)}
    manifest_bytes = write("capture-manifest.json", capture_manifest)
    capture_tree_sha = _canonical_sha(capture_manifest)
    binding_keys = RELEASE_BINDING_KEYS
    release = {key: copy.deepcopy(install[key]) for key in binding_keys}
    readiness = {
        "schemaVersion": 2, "kind": adapter.READINESS_KIND,
        "studyEpoch": adapter.STUDY_EPOCH, "frameworkCommit": bindings.framework_commit,
        "descriptorCanonicalSha256": bindings.descriptor_sha256,
        "compiledPlanCanonicalSha256": bindings.plan_sha256, "target": TARGET,
        "runCount": adapter.RUN_COUNT, "artifactRoot": "artifacts",
        "controllerDigests": bindings.controller_sha256, "imageDigests": images,
        "patchedServices": list(adapter.PATCHED_SERVICES), "setupArtifacts": setup_artifacts,
        "release": release, "seams": seams,
        "transport": {"schemaVersion": 1, "contract": adapter.TRANSPORT_CONTRACT,
            "target": TARGET, "transportUser": TRANSPORT_USER, "executionUser": EXECUTION_USER,
            "executionMethod": EXECUTION_METHOD, "releaseRoot": install["releaseRoot"],
            "resultsRoot": install["resultsRoot"], "evidenceLabel": adapter.EVIDENCE_LABEL,
            "outerLeasePath": str(LEASE_PATH), "outerLeaseScope": adapter.OUTER_LEASE_SCOPE,
            "deadlineEnforced": True, "cleanupEnforced": True,
            "candidateDescriptorAccepted": True, "controllerDigests": bindings.controller_sha256,
            "implementationPath": transport_relative.removeprefix("artifacts/"),
            "implementationSha256": hashlib.sha256(transport_bytes).hexdigest()},
        "ingressArchiveSha256": ingress_archive_sha256,
        "captureTreeSha256": capture_tree_sha,
        "captureManifestPath": "capture-manifest.json",
        "captureManifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "runtimePreflight": copy.deepcopy(preflight), "runtimeReady": True,
        "candidateEvidenceAuthorized": False, "promotionAuthorized": False,
    }
    write("readiness.json", readiness)
    return readiness


def _read_capture_spec(archive_payload: bytes) -> bytes:
    """Accept only the v2 identity spec; legacy evidence trees are forbidden."""
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_payload), mode="r:") as archive:
            members = archive.getmembers()
            if len(members) != 1 or members[0].name != "capture-spec.json" or not members[0].isreg():
                raise InstallError(
                    "readiness ingress must contain only capture-spec.json; "
                    "caller-authored observations, reports, verdicts, hashes, and seals are forbidden"
                )
            handle = archive.extractfile(members[0])
            if handle is None:
                raise InstallError("readiness capture spec is unreadable")
            payload = handle.read()
            if len(payload) != members[0].size or len(payload) > 65536:
                raise InstallError("readiness capture spec size differs")
            return payload
    except InstallError:
        raise
    except (tarfile.TarError, OSError) as exc:
        raise InstallError(f"readiness archive is invalid: {exc}") from exc


def _root_readiness_namespace(setup_id: str) -> Path:
    """Create a control namespace whose every mutable ancestor is root-owned.

    Experimental artifacts remain under the execution user's results root.
    Control names cannot live there: ownership of a child directory does not
    stop the owner of its parent from renaming or replacing that child.
    """
    anchor = Path("/var/lib")
    state = anchor.lstat()
    if anchor.is_symlink() or not stat.S_ISDIR(state.st_mode) or state.st_uid != 0:
        raise InstallError("readiness control anchor is not a root-owned directory")
    current = anchor
    for part in READINESS_CONTROL_ROOT.relative_to(anchor).parts + (setup_id,):
        current = current / part
        try:
            state = current.lstat()
        except FileNotFoundError:
            current.mkdir(mode=0o700)
            os.chown(current, 0, 0)
            os.chmod(current, 0o700)
            state = current.lstat()
        if (
            current.is_symlink() or not stat.S_ISDIR(state.st_mode)
            or state.st_uid != 0 or state.st_gid != 0
            or stat.S_IMODE(state.st_mode) != 0o700
        ):
            raise InstallError("readiness control path is not root-owned mode 0700")
    return current


def _assert_root_namespace(path: Path, identity: tuple[int, int]) -> None:
    state = path.lstat()
    if (
        path.is_symlink() or not stat.S_ISDIR(state.st_mode)
        or (state.st_dev, state.st_ino) != identity
        or state.st_uid != 0 or state.st_gid != 0
        or stat.S_IMODE(state.st_mode) != 0o700
    ):
        raise InstallError("root readiness namespace identity changed")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validate_readiness_abort(
    path: Path, *, setup_id: str, framework_commit: str, archive_sha: str,
) -> dict[str, Any]:
    value = _json_file(path, "preexisting readiness abort")[0]
    if (
        set(value) != {"schemaVersion", "kind", "setupId", "frameworkCommit",
                       "ingressArchiveSha256", "captureTreeSha256", "runtimeReady",
                       "experimentalCellsExecuted", "experimentalState", "errorType",
                       "error", "recordedAt", "promotionAuthorized"}
        or value.get("schemaVersion") != 1
        or value.get("kind") != "teastore-candidate-readiness-capture-abort-v2"
        or value.get("setupId") != setup_id
        or value.get("frameworkCommit") != framework_commit
        or value.get("ingressArchiveSha256") != archive_sha
        or value.get("captureTreeSha256") is not None
        or value.get("runtimeReady") is not False
        or value.get("experimentalCellsExecuted") != 0
        or value.get("experimentalState") != "ABSTAINED"
        or value.get("promotionAuthorized") is not False
    ):
        raise InstallError("preexisting readiness abort identity differs")
    _timestamp(value.get("recordedAt"), "readiness abort recordedAt")
    return value


def admit_readiness_capture(
    *, archive_payload: bytes, expected_archive_sha256: str, setup_id: str,
    framework_commit: str, release_binding_sha256: str,
) -> dict[str, Any]:
    """Generate target-owned readiness from one untrusted, identity-only spec."""

    _require_root_transport()
    archive_sha = hashlib.sha256(archive_payload).hexdigest()
    if (
        archive_sha != expected_archive_sha256
        or len(archive_payload) > MAX_READINESS_ARCHIVE_BYTES
        or SETUP_ID_RE.fullmatch(setup_id) is None
        or COMMIT_RE.fullmatch(framework_commit) is None
        or SHA256_RE.fullmatch(release_binding_sha256) is None
    ):
        raise InstallError("readiness archive identity or bound size differs")
    spec_payload = _read_capture_spec(archive_payload)
    release_root = Path(__file__).resolve().parents[3]
    receipt_dir = release_root / ".git/candidate-v4-receipts"
    install = _json_file(receipt_dir / "release-install.json", "release install")[0]
    binding_keys = RELEASE_BINDING_KEYS
    setup = _json_file(receipt_dir / "gate-setup.json", "retained GATE-SETUP")[0]
    authorization = setup.get("authorization", {})
    if (
        not binding_keys <= set(install)
        or _canonical_sha({key: install[key] for key in binding_keys})
        != release_binding_sha256
        or install.get("setupId") != setup_id
        or install.get("frameworkCommit") != framework_commit
        or install.get("executionUser") != EXECUTION_USER
        or install.get("executionUid") != EXECUTION_UID
        or install.get("executionGid") != EXECUTION_GID
        or authorization.get("experimentalCellsAuthorized") != 0
        or "collect-runtime-readiness" not in authorization.get("allowedActions", [])
        or datetime.now(timezone.utc) >= _timestamp(
            authorization.get("authorizationDeadline"), "GATE-SETUP deadline"
        )
    ):
        raise InstallError("readiness capture is outside the exact installed setup authority")
    readiness_parent = _root_readiness_namespace(setup_id)
    namespace_state = readiness_parent.lstat()
    namespace_identity = (namespace_state.st_dev, namespace_state.st_ino)
    pending = readiness_parent / f".pending-{archive_sha[:16]}"
    final = readiness_parent / archive_sha[:16]
    abort_path = readiness_parent / f"abort-{archive_sha[:16]}.json"
    if abort_path.exists() or abort_path.is_symlink():
        _validate_readiness_abort(
            abort_path, setup_id=setup_id, framework_commit=framework_commit,
            archive_sha=archive_sha,
        )
        raise InstallError("validated preexisting readiness abort blocks replay")
    admitted = False
    try:
        if pending.exists() or pending.is_symlink() or final.exists() or final.is_symlink():
            raise InstallError("readiness capture path collision or partial install")
        pending.mkdir(mode=0o700)
        os.chown(pending, 0, 0)
        os.chmod(pending, 0o700)
        preflight = runtime_preflight()
        readiness = _generate_installed_readiness(
            pending=pending, spec_payload=spec_payload,
            ingress_archive_sha256=archive_sha, install=install,
            release_binding_sha256=release_binding_sha256, preflight=preflight,
        )
        readiness_path = pending / "readiness.json"
        adapter = _installed_adapter()
        bindings = adapter.inspect_campaign(
            pending / "artifacts/campaign", framework_commit,
        )
        readiness_sha = adapter.validate_readiness(
            readiness, bindings, readiness_parent=pending,
        )
        admission = {
            "schemaVersion": 1,
            "kind": "teastore-candidate-installed-readiness-v1",
            "setupId": setup_id,
            "frameworkCommit": framework_commit,
            "releaseBindingSha256": release_binding_sha256,
            "ingressArchiveSha256": archive_sha,
            "captureTreeSha256": readiness["captureTreeSha256"],
            "readinessCanonicalSha256": readiness_sha,
            "runtimePreflightSha256": _canonical_sha(preflight),
            "runtimePreflightCapturedAt": preflight["capturedAt"],
            "readinessRoot": str(final),
            "validatedAt": datetime.now(timezone.utc).isoformat(),
            "experimentalCellsExecuted": 0,
            "runtimeReady": True,
            "promotionAuthorized": False,
        }
        _write_exclusive(
            pending / "readiness-admission.json",
            json.dumps(admission, allow_nan=False, indent=2, sort_keys=True).encode()
            + b"\n",
            uid=0, gid=0,
        )
        if readiness["ingressArchiveSha256"] == readiness["captureTreeSha256"]:
            raise InstallError("ingress archive and generated capture tree digests alias")
        _assert_root_namespace(readiness_parent, namespace_identity)
        _fsync_directory(pending)
        pending.rename(final)
        _fsync_directory(readiness_parent)
        admitted = True
        return admission
    finally:
        if not admitted:
            active = sys.exc_info()[1]
            abort = {
                    "schemaVersion": 1,
                    "kind": "teastore-candidate-readiness-capture-abort-v2",
                    "setupId": setup_id,
                    "frameworkCommit": framework_commit,
                    "ingressArchiveSha256": archive_sha,
                    "captureTreeSha256": None,
                    "runtimeReady": False,
                    "experimentalCellsExecuted": 0,
                    "experimentalState": "ABSTAINED",
                    "errorType": type(active).__name__ if active is not None else "UnknownError",
                    "error": str(active)[:4096] if active is not None else "readiness generation did not commit",
                    "recordedAt": datetime.now(timezone.utc).isoformat(),
                    "promotionAuthorized": False,
                }
            try:
                _assert_root_namespace(readiness_parent, namespace_identity)
                _write_exclusive(
                    abort_path,
                    json.dumps(abort, allow_nan=False, indent=2, sort_keys=True).encode() + b"\n",
                    uid=0, gid=0,
                )
                _fsync_directory(readiness_parent)
            finally:
                if pending.exists() and not pending.is_symlink():
                    shutil.rmtree(pending)
                    _fsync_directory(readiness_parent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    probe_parser = subparsers.add_parser("probe")
    probe_parser.add_argument("--probe-sha256", required=True)
    setup_parser = subparsers.add_parser("setup")
    setup_parser.add_argument("--setup-id", required=True)
    setup_parser.add_argument("--gate-plan", type=Path, required=True)
    setup_parser.add_argument("--target-proof", type=Path, required=True)
    setup_parser.add_argument("--release-manifest", type=Path, required=True)
    setup_parser.add_argument("--gate-setup", type=Path, required=True)
    setup_parser.add_argument("--bundle", type=Path, required=True)
    setup_parser.add_argument("--expected-self-sha256", required=True)
    cleanup_parser = subparsers.add_parser("cleanup-staging")
    cleanup_parser.add_argument("--setup-id", required=True)
    cleanup_parser.add_argument("--expected-self-sha256", required=True)
    launch_parser = subparsers.add_parser("launch-campaign")
    launch_parser.add_argument("--package-sha256", required=True)
    launch_parser.add_argument("--output", type=Path, required=True)
    launch_parser.add_argument("--framework-commit", required=True)
    launch_parser.add_argument("--release-binding-sha256", required=True)
    supervise_parser = subparsers.add_parser("supervise")
    supervise_parser.add_argument("--controller", type=Path, required=True)
    supervise_parser.add_argument("--package", type=Path, required=True)
    supervise_parser.add_argument("--output", type=Path, required=True)
    supervise_parser.add_argument("--framework-commit", required=True)
    supervise_parser.add_argument("--package-sha256", required=True)
    status_parser = subparsers.add_parser("campaign-status")
    status_parser.add_argument("--setup-id", required=True)
    status_parser.add_argument("--campaign-id", required=True)
    status_parser.add_argument("--package-sha256", required=True)
    status_parser.add_argument("--release-binding-sha256", required=True)
    readiness_parser = subparsers.add_parser("admit-readiness")
    readiness_parser.add_argument("--archive-sha256", required=True)
    readiness_parser.add_argument("--setup-id", required=True)
    readiness_parser.add_argument("--framework-commit", required=True)
    readiness_parser.add_argument("--release-binding-sha256", required=True)
    image_parser = subparsers.add_parser("build-images")
    image_parser.add_argument("--working-root", type=Path, required=True)
    image_parser.add_argument("--final-release-root", type=Path, required=True)
    image_parser.add_argument("--setup-id", required=True)
    image_parser.add_argument("--framework-commit", required=True)
    image_parser.add_argument("--authorization-deadline", required=True)
    image_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    cleanup_receipt: dict[str, Any] | None = None
    try:
        if args.command == "probe":
            receipt = target_proof(probe_sha256=args.probe_sha256)
        elif args.command == "setup":
            receipt = install_release(
                gate_plan_path=args.gate_plan,
                target_proof_path=args.target_proof,
                release_manifest_path=args.release_manifest,
                gate_setup_path=args.gate_setup,
                bundle_path=args.bundle,
                expected_self_sha256=args.expected_self_sha256,
            )
        elif args.command == "cleanup-staging":
            receipt = cleanup_setup_staging(
                setup_id=args.setup_id,
                expected_self_sha256=args.expected_self_sha256,
            )
        elif args.command == "launch-campaign":
            receipt = launch_campaign(
                package_payload=sys.stdin.buffer.read(),
                expected_package_sha256=args.package_sha256,
                output=args.output,
                framework_commit=args.framework_commit,
                release_binding_sha256=args.release_binding_sha256,
            )
        elif args.command == "campaign-status":
            receipt = campaign_status(
                setup_id=args.setup_id,
                campaign_id=args.campaign_id,
                expected_package_sha256=args.package_sha256,
                release_binding_sha256=args.release_binding_sha256,
            )
        elif args.command == "supervise":
            receipt = supervise_campaign(
                controller=args.controller, package_path=args.package,
                output=args.output, framework_commit=args.framework_commit,
                package_sha256=args.package_sha256,
            )
        elif args.command == "admit-readiness":
            receipt = admit_readiness_capture(
                archive_payload=sys.stdin.buffer.read(),
                expected_archive_sha256=args.archive_sha256,
                setup_id=args.setup_id,
                framework_commit=args.framework_commit,
                release_binding_sha256=args.release_binding_sha256,
            )
        else:
            receipt = build_patched_images(
                working_root=args.working_root,
                final_release_root=args.final_release_root,
                setup_id=args.setup_id,
                framework_commit=args.framework_commit,
                authorization_deadline=args.authorization_deadline,
                output=args.output,
            )
    except Exception as exc:  # noqa: BLE001 - one bounded failure record
        error = f"{type(exc).__name__}: {exc}"
        if args.command == "setup":
            try:
                cleanup_receipt = cleanup_setup_staging(
                    setup_id=args.setup_id,
                    expected_self_sha256=args.expected_self_sha256,
                )
            except Exception as cleanup_exc:  # noqa: BLE001 - preserve both causes
                error += (
                    "; staging cleanup failed: "
                    f"{type(cleanup_exc).__name__}: {cleanup_exc}"
                )
        blocked: dict[str, Any] = {"state": "blocked", "error": error}
        if cleanup_receipt is not None:
            blocked["stagingCleanup"] = cleanup_receipt
        print(json.dumps(blocked, sort_keys=True))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "InstallError", "admit_readiness_capture", "build_patched_images",
    "campaign_status",
    "cleanup_setup_staging", "install_release", "launch_campaign", "main",
    "runtime_preflight", "supervise_campaign", "target_proof",
    "_validate_image_build_receipt",
]
