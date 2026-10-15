#!/usr/bin/env python3
"""Gate-bound, transport-injected adapter for the TeaStore candidate pilot.

This module has deliberately no SSH, Docker, or command-line launch surface.
Its sole subprocess use is a fixed-environment, read-only Git identity check.
It replays the immutable 27-cell campaign and typed gate bindings, and can
construct per-cell contracts for review.  Production readiness is established
only by deterministic replay of a positive capture and a watched planted
defect for every seam; retained assertions alone remain insufficient.

The receipts are tamper-evident bindings, not identity signatures.  Whoever
creates them remains an external human-authority concern.  In particular, this
module cannot turn a generic acknowledgement into approval and cannot make a
diagnostic controller candidate-capable.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, NoReturn, Optional, Protocol


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
STUDY_EPOCH = EPOCH["studyEpoch"]
CHANGE_ID = "admit-teastore-candidate-runtime"
TARGET = "fb14srv5"
TARGET_HOSTNAME = "fb14srv5.<redacted-domain>"
TARGET_MACHINE_ID_SHA256 = "c43aa7be531dd44146e45811b3aa5b796df1945e346164529c205d7f4d559773"
TRANSPORT_USER = "root"
EXECUTION_USER = "stig"
EXECUTION_UID = 1015
EXECUTION_GID = 1015
EXECUTION_DOCKER_GID = 999
EXECUTION_METHOD = "runuser"
EXECUTION_USERS = (EXECUTION_USER,)
EXECUTION_SUPPLEMENTARY_GIDS = (999, 1015)
DOCKER_SERVER_VERSION = "29.6.1"
# Mirrors RELEASE_BINDING_KEYS in candidate_release_installer. The installer
# only ever runs on the target, so the two cannot import each other; a test
# pins them equal so a field added to one cannot silently omit the other.
RELEASE_BINDING_KEYS = frozenset({
    "setupId", "target", "transportUser", "executionUser", "executionUid",
    "executionGid", "executionMethod", "frameworkCommit", "frameworkTree",
    "bundleSha256", "releaseManifestSha256", "gateSetupSha256", "releaseRoot",
    "resultsRoot", "exclusiveLeasePath", "controllerDigests",
    "imageBuildReceiptSha256", "imageBuild", "activationCompile", "installedAt",
})
PROJECT_PREFIX = "teastore_candidate_"
RESERVED_PORTS = (3306, 5672, 8080, 8082, 15672)
CANDIDATE_V4_ROOT = "/home/stig/.local/share/observability-placement/candidate-v4/teastore"
RELEASES_ROOT = f"{CANDIDATE_V4_ROOT}/releases"
RESULTS_ROOT = f"{CANDIDATE_V4_ROOT}/results"
LEASE_PATH = f"{CANDIDATE_V4_ROOT}/leases/host-exclusive.lock"
EVIDENCE_LABEL = "candidate-evidence"
RUN_COUNT = EPOCH["runCount"]
ATTEMPT = 1
CLEANUP_RESERVE_SECONDS = 300
MINIMUM_FIRST_MUTATION_REMAINING_SECONDS = EPOCH["minimumFirstMutationRemainingSeconds"]
OUTER_LEASE_SCOPE = EPOCH["outerLeaseScope"]
MAX_GATE_RUN_AGE_SECONDS = 15 * 60
MAX_GATE_SETUP_AGE_SECONDS = 15 * 60
MAX_CLOCK_SKEW_SECONDS = 5

PLAN_KIND = "teastore-candidate-gate-plan"
SETUP_KIND = "teastore-candidate-gate-setup-v1"
RUN_KIND = "teastore-candidate-gate-run"
TARGET_PROOF_KIND = "teastore-candidate-target-proof-v1"
RELEASE_MANIFEST_KIND = "teastore-candidate-release-manifest-v1"
RELEASE_INSTALL_KIND = "teastore-candidate-release-install-v1"
IMAGE_BUILD_KIND = "teastore-candidate-patched-image-build-v1"
READINESS_KIND = "teastore-candidate-runtime-readiness"
RUNTIME_PREFLIGHT_KIND = "teastore-candidate-installed-runtime-preflight-v1"
READINESS_EVIDENCE_KIND = "teastore-candidate-runtime-seam-evidence"
FAILURE_WITNESS_KIND = "teastore-candidate-runtime-failure-witness"
CELL_CONTRACT = "teastore-candidate-cell-invocation-v1"
TRANSPORT_CONTRACT = "teastore-candidate-bounded-transport-v1"
CANDIDATE_CAMPAIGN_CONTRACT = "teastore-candidate-pilot-evidence-v1"
CANDIDATE_TERMINAL_KIND = "teastore-candidate-terminal-validation-v1"
CANDIDATE_TERMINAL_VALIDATOR_RELATIVE = (
    "modules/teastore/validation/candidate_terminal.py"
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
CAMPAIGN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SETUP_ID_RE = re.compile(r"^[0-9a-f]{32}$")
IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*@sha256:[0-9a-f]{64}$")

CONTROLLER_PATHS = {
    "candidate-compiler": "modules/teastore/execution/candidate_pilot.py",
    "candidate-orchestrator": "modules/teastore/execution/candidate_orchestrator.py",
    "candidate-runtime-adapter": "modules/teastore/execution/candidate_runtime_adapter.py",
    "candidate-readiness-checker": "modules/teastore/validation/candidate_readiness.py",
    "candidate-terminal-validator": "modules/teastore/validation/candidate_terminal.py",
    "bounded-candidate-transport": "modules/teastore/execution/candidate_transport.py",
    "candidate-remote-controller": (
        "modules/teastore/execution/candidate_remote_controller.py"
    ),
    "candidate-cell-executor": "modules/teastore/execution/candidate_cell_executor.py",
    "candidate-release-installer": (
        "modules/teastore/execution/candidate_release_installer.py"
    ),
    "candidate-target-allocation": (
        "modules/teastore/execution/candidate-target-v4.json"
    ),
    "candidate-validator": "modules/teastore/validation/candidate_pilot.py",
    "secret-scanner": "modules/teastore/validation/secret_scan.py",
    "diagnostic-server-harness": "modules/teastore/execution/srv5_harness.py",
    "bounded-performance-runner": "modules/teastore/execution/performance_campaign.py",
    "diagnostic-terminal-validator": "modules/teastore/validation/srv5_terminal.py",
    "performance-receipt-validator": (
        "modules/teastore/validation/performance_receipt.py"
    ),
    "native-kieker-validator": "modules/teastore/validation/native_kieker.py",
    "fixed-load-runner": "modules/teastore/workload/fixed_load.py",
    "native-collector": "modules/teastore/collectors/kieker_native.py",
    "performance-probe-v3": "modules/teastore/collectors/performance_probe_v3.py",
    "system-probe": "modules/teastore/collectors/system_probe.py",
    "application-witness-extractor": "modules/teastore/witness/extract_app_witness.py",
    "native-token-extractor": (
        "modules/teastore/witness/extract_native_token_correlation.py"
    ),
    "native-token-validator": (
        "modules/teastore/validation/native_token_correlation.py"
    ),
    "native-token-correlation-schema": (
        "modules/teastore/witness/native-token-correlation.schema.json"
    ),
    "patched-image-validator": "modules/teastore/validation/patched_images.py",
    # Non-Python inputs below are read or executed by the live controllers.
    # They are controller dependencies even though they are not import targets.
    "auth-selection": "modules/teastore/activation/auth-selection.json",
    "activation-catalog": "modules/teastore/activation/catalog.json",
    "fault-qualification": "modules/teastore/goals/fault-qualification.json",
    "server-policy": "modules/teastore/deployment/srv5.yaml",
    "compose-kieker": (
        "modules/teastore/deployment/compose/docker-compose_kieker.yaml"
    ),
    "compose-rabbitmq": (
        "modules/teastore/deployment/compose/docker-compose_rabbitmq.yaml"
    ),
    "compose-isolation": (
        "modules/teastore/deployment/compose/isolation.override.yaml"
    ),
    "compose-selected": (
        "modules/teastore/deployment/compose/compiled-selected.override.yaml"
    ),
    "compose-full": (
        "modules/teastore/deployment/compose/compiled-full.override.yaml"
    ),
    "posture-none": "modules/teastore/postures/none.override.yaml",
    "posture-full": "modules/teastore/postures/native-full.yaml",
    "patched-image-inputs": "modules/teastore/images/patched-image-inputs.json",
    "patched-image-lock-schema": (
        "modules/teastore/images/patched-image-lock.schema.json"
    ),
    "patched-image-auth-dockerfile": "modules/teastore/images/Dockerfile.auth",
    "patched-image-persistence-dockerfile": (
        "modules/teastore/images/Dockerfile.persistence"
    ),
    "patched-image-webui-dockerfile": "modules/teastore/images/Dockerfile.webui",
    "teastore-source-lock": "modules/teastore/source.lock",
    "application-witness-v3-manifest": (
        "modules/teastore/witness/patch-manifest-v3.json"
    ),
    "application-witness-v3-patch": (
        "modules/teastore/witness/teastore-app-witness-v3.patch"
    ),
    "application-witness-v2-manifest": (
        "modules/teastore/witness/patch-manifest-v2.json"
    ),
    "application-witness-v2-patch": (
        "modules/teastore/witness/teastore-app-witness-v2.patch"
    ),
    "application-witness-v1-manifest": (
        "modules/teastore/witness/patch-manifest.json"
    ),
    "application-witness-v1-patch": (
        "modules/teastore/witness/teastore-app-witness-v1.patch"
    ),
}
if EPOCH["sweep"]:
    # Traffic sweep: the active compiler is the sweep compiler; the frozen compiler it reads, its
    # descriptor, the vendored protocol gates and the selector itself are digest-bound too.
    CONTROLLER_PATHS = {
        **CONTROLLER_PATHS,
        "candidate-compiler": EPOCH["compilerRelative"],
        "frozen-compiler": "modules/teastore/execution/candidate_pilot.py",
        "sweep-descriptor": EPOCH["descriptorRelative"],
        "protocol-gates": "modules/teastore/validation/protocol_gates.py",
        "study-epoch-loader": "modules/teastore/execution/study_epoch.py",
        "study-epoch-selector": EPOCH["selectorRelative"],
    }
    # Quiet calibration (2026-10-04): its compiler also reads the sweep compiler and the sweep descriptor, so they are
    # bound too ("sweep-descriptor" then names the sweep's file and "quiet-descriptor" the quiet one).  The sweep
    # epoch declares no additional paths, so its controller set is unchanged.
    CONTROLLER_PATHS.update(EPOCH.get("additionalControllerPaths", {}))

READINESS_SEAMS = (
    "patched-sut-images",
    "application-witness-finalization",
    "measurement-scoped-auth-log-capture",
    "parameter-logging-disabled",
    "native-token-correlation",
    "cross-message-parent-and-service-attribution",
    "none-selected-full-materialization",
    "queue-and-capture-reconciliation",
    "candidate-cell-validation",
    "candidate-terminal-validation",
    "bounded-transport",
    "outer-lease-deadline-and-cleanup",
)
IMAGE_SERVICES = (
    "registry", "db", "persistence", "auth", "image", "recommender", "webui",
    "rabbitmq",
)
PATCHED_SERVICES = ("auth", "persistence", "webui")
SOURCE_COMMIT = "34b37f7e7be433ce72d5f9455e66922a13116749"
PATCH_SHA256 = "2199c0f6e9ab1098afcac3c6b5a68d7860ad1b94b70019d790862eb1a7d60094"
MAVEN_COMMAND = (
    "mvn", "-B", "-ntp", "-pl",
    "utilities/tools.descartes.teastore.registryclient,"
    "services/tools.descartes.teastore.webui,"
    "services/tools.descartes.teastore.auth,"
    "services/tools.descartes.teastore.persistence",
    "-am", "clean", "verify",
)
DECLARED_RUNTIME_IMAGES = {
    "registry": "descartesresearch/teastore-registry",
    "db": "descartesresearch/teastore-db",
    "persistence": "descartesresearch/teastore-persistence",
    "auth": "descartesresearch/teastore-auth",
    "image": "descartesresearch/teastore-image",
    "recommender": "descartesresearch/teastore-recommender",
    "webui": "descartesresearch/teastore-webui",
    "rabbitmq": "rabbitmq:3-management",
}
PATCHED_IMAGE_REPOSITORIES = {
    "auth": "observability-placement/teastore-auth-witness",
    "persistence": "observability-placement/teastore-persistence-witness",
    "webui": "observability-placement/teastore-webui-witness",
}

COMMON_ARTIFACTS = (
    "receipt.json",
    "journey-ledger.plan.json",
    "journey-ledger.jsonl",
    "auth.log",
    "persistence.log",
    "app-witness.jsonl",
    "app-witness-extraction.json",
    "service-log-capture.json",
    "native-token-correlation.json",
    "native-token-correlation-extraction.json",
    "kieker-amqp.spool",
    "traces.json",
    "capture-terminal.json",
    "posture-proof.json",
    "queue-proof.json",
    "runtime-images.json",
    "system-samples.json",
    "candidate-validation.json",
    "content-manifest.json",
    "cell-cleanup.json",
)
if EPOCH["sweep"]:
    COMMON_ARTIFACTS = (*COMMON_ARTIFACTS, "application.log")


class GateError(ValueError):
    """A gate, readiness, schedule, or transport binding failed closed."""


@dataclass(frozen=True)
class GitRepositoryState:
    """Git identity observed without consulting user or system configuration."""

    commit: str
    head_tree: str
    commit_tree: str
    tracked_dirty: bool
    status: bytes
    concealment_config: bytes
    index_concealment: tuple[str, ...]


def _reject_constant(value: str) -> NoReturn:
    raise GateError(f"non-finite JSON value is forbidden: {value}")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GateError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(payload: bytes, where: str) -> Any:
    try:
        return json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except GateError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GateError(f"invalid JSON in {where}: {exc}") from exc


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, allow_nan=False, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GateError(f"value is not canonical JSON: {exc}") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _same_json_type(value: Any, expected: Any) -> bool:
    """Compare JSON values without Python's bool/int/float equivalence."""

    try:
        return _canonical_bytes(value) == _canonical_bytes(expected)
    except GateError:
        return False


def _exact_int(value: Any, expected: int) -> bool:
    return type(value) is int and value == expected


def _file_bytes(path: Path, where: str) -> bytes:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise GateError(f"{where} is not a regular non-symlink file")
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        payload = path.read_bytes()
        after = path.lstat()
        if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise GateError(f"{where} changed while being read")
        if len(payload) != before.st_size:
            raise GateError(f"{where} size changed while being read")
        return payload
    except GateError:
        raise
    except OSError as exc:
        raise GateError(f"cannot read {where}: {exc}") from exc


def _git_result(
    repository_arguments: tuple[str, ...],
    *,
    allowed_returncodes: tuple[int, ...] = (0,),
):
    """Run one read-only Git query without ambient Git configuration/state."""

    environment = {
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": "/nonexistent-candidate-runtime-home",
        "XDG_CONFIG_HOME": "/nonexistent-candidate-runtime-config",
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    command = (
        "git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
        "-C", str(ROOT), *repository_arguments,
    )
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            env=environment,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GateError(f"cannot establish controlled Git identity: {exc}") from exc
    if result.returncode not in allowed_returncodes:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise GateError(
            f"controlled Git identity query failed ({repository_arguments[0]}): "
            f"{detail or 'no diagnostic'}"
        )
    return result


def _git(repository_arguments: tuple[str, ...]) -> bytes:
    return _git_result(repository_arguments).stdout


def _git_repository_state() -> GitRepositoryState:
    """Return HEAD/commit-tree and dirtiness under a controlled Git env."""

    top = _git(("rev-parse", "--show-toplevel")).decode(
        "utf-8", errors="strict"
    ).strip()
    if Path(top).resolve() != ROOT.resolve():
        raise GateError("candidate runtime adapter is not at the Git worktree root")
    commit = _git(("rev-parse", "--verify", "HEAD^{commit}")).decode(
        "ascii", errors="strict"
    ).strip()
    head_tree = _git(("rev-parse", "--verify", "HEAD^{tree}")).decode(
        "ascii", errors="strict"
    ).strip()
    commit_tree = _git(("rev-parse", "--verify", f"{commit}^{{tree}}")).decode(
        "ascii", errors="strict"
    ).strip()
    # diff-index --quiet short-circuits on a stat mismatch rather than reading
    # content, so a freshly installed release -- whose extract, chown, and seal
    # guarantee a stale stat cache -- reports every tracked file as dirty even
    # when each byte matches HEAD. Refresh the cache first. This compares
    # content for stat-differing entries, so genuine modifications are still
    # reported; only the false positive disappears.
    _git_result(("update-index", "--refresh", "-q"), allowed_returncodes=(0, 1))
    tracked = _git_result(
        ("diff-index", "--ignore-submodules=none", "--quiet", "HEAD", "--"),
        allowed_returncodes=(0, 1),
    )
    status = _git((
        "status", "--porcelain=v1", "-z", "--untracked-files=all",
        "--ignore-submodules=none",
    ))
    concealment = _git_result(
        (
            "config", "--local", "--show-origin", "--get-regexp",
            (
                r"^(filter\.|core\.attributesfile$|core\.excludesfile$|"
                r"core\.fsmonitor$|core\.fsmonitorhookversion$|"
                r"core\.ignorestat$|core\.untrackedcache$|"
                r"submodule\..*\.ignore$|diff\.ignoresubmodules$|"
                r"extensions\.worktreeconfig$)"
            ),
        ),
        allowed_returncodes=(0, 1),
    )
    index_records = _git(("ls-files", "-v", "-z", "--"))
    index_concealment: list[str] = []
    for raw in index_records.split(b"\0"):
        if not raw:
            continue
        try:
            entry = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise GateError(f"non-UTF-8 Git index flag record: {exc}") from exc
        if len(entry) < 3 or entry[1] != " ":
            raise GateError("malformed Git index flag record")
        tag, relative = entry[0], entry[2:]
        if tag.islower() or tag == "S":
            index_concealment.append(relative)
    if (
        COMMIT_RE.fullmatch(commit) is None
        or COMMIT_RE.fullmatch(head_tree) is None
        or COMMIT_RE.fullmatch(commit_tree) is None
    ):
        raise GateError("controlled Git identity returned malformed object IDs")
    return GitRepositoryState(
        commit=commit,
        head_tree=head_tree,
        commit_tree=commit_tree,
        tracked_dirty=tracked.returncode == 1,
        status=status,
        concealment_config=concealment.stdout,
        index_concealment=tuple(index_concealment),
    )


def _verify_git_binding(
    framework_commit: str,
    state: GitRepositoryState,
    *,
    previous: GitRepositoryState | None = None,
) -> None:
    if state.commit != framework_commit:
        raise GateError("framework_commit is not the exact current Git HEAD commit")
    if state.head_tree != state.commit_tree:
        raise GateError("current Git HEAD tree differs from the bound commit tree")
    if state.concealment_config:
        raise GateError("repository Git configuration can conceal execution bytes")
    if state.index_concealment:
        raise GateError("Git index flags can conceal modified execution bytes")
    if state.tracked_dirty or state.status:
        raise GateError("current Git worktree is not clean")
    if previous is not None and state != previous:
        raise GateError("Git commit/tree/worktree changed while bindings were inspected")


def _safe_relative_path(value: Any, where: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise GateError(f"{where} must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or value in {".", ".."}
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise GateError(f"{where} is not a normalized safe relative path")
    return path


def _artifact_root(parent: Path, relative: Any) -> Path:
    path = _safe_relative_path(relative, "runtime readiness artifactRoot")
    try:
        current = Path(parent).resolve(strict=True)
        for part in path.parts:
            current = current / part
            metadata = current.lstat()
            if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
                raise GateError(
                    "runtime readiness artifactRoot crosses a symlink or non-directory"
                )
        return current
    except GateError:
        raise
    except OSError as exc:
        raise GateError(f"cannot resolve runtime readiness artifactRoot: {exc}") from exc


def _artifact_file(root: Path, relative: Any, where: str) -> tuple[Path, bytes]:
    path = _safe_relative_path(relative, where)
    current = root
    try:
        for part in path.parts[:-1]:
            current = current / part
            metadata = current.lstat()
            if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
                raise GateError(f"{where} crosses a symlink or non-directory")
        candidate = current / path.parts[-1]
        return candidate, _file_bytes(candidate, where)
    except GateError:
        raise
    except OSError as exc:
        raise GateError(f"cannot resolve {where}: {exc}") from exc


def _json_file(path: Path, where: str) -> dict[str, Any]:
    value = _strict_json(_file_bytes(path, where), where)
    if not isinstance(value, dict):
        raise GateError(f"{where} must contain one JSON object")
    return value


def _exact(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateError(f"{where} must be an object")
    actual = set(value)
    if actual != keys:
        raise GateError(
            f"{where} fields differ: missing={sorted(keys - actual)}, "
            f"unknown={sorted(actual - keys)}"
        )
    return value


def _timestamp(value: Any, where: str) -> datetime:
    if not isinstance(value, str):
        raise GateError(f"{where} must be an ISO-8601 string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise GateError(f"{where} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GateError(f"{where} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise GateError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _candidate_module():
    path = ROOT / EPOCH["compilerRelative"]
    spec = importlib.util.spec_from_file_location("candidate_runtime_frozen_compiler", path)
    if spec is None or spec.loader is None:  # pragma: no cover - install defect
        raise GateError(f"cannot load candidate compiler: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate_validator_module():
    path = ROOT / "modules/teastore/validation/candidate_pilot.py"
    spec = importlib.util.spec_from_file_location("candidate_runtime_cell_validator", path)
    if spec is None or spec.loader is None:  # pragma: no cover - install defect
        raise GateError(f"cannot load candidate validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate_terminal_validator_module(
    contract: Mapping[str, Any],
):
    """Load only a real, content-bound terminal validator.

    The path is intentionally absent in this construction epoch.  Merely
    dropping a Python file into the checkout is insufficient: its digest must
    also be part of the immutable controller map in the cell contract.
    """

    path = ROOT / CANDIDATE_TERMINAL_VALIDATOR_RELATIVE
    if not path.exists() and not path.is_symlink():
        return None
    payload = _file_bytes(path, "candidate terminal validator")
    expected = contract.get("runtimeInputs", {}).get("controllerDigests", {}).get(
        "candidate-terminal-validator"
    )
    observed = hashlib.sha256(payload).hexdigest()
    if expected != observed:
        raise GateError(
            "candidate terminal validator is present but not content-bound by the cell"
        )
    spec = importlib.util.spec_from_file_location(
        "candidate_runtime_terminal_validator", path
    )
    if spec is None or spec.loader is None:  # pragma: no cover - install defect
        raise GateError(f"cannot load candidate terminal validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "validate_candidate_cell", None)):
        raise GateError("candidate terminal validator has no validate_candidate_cell")
    return module


def _candidate_readiness_module():
    path = ROOT / "modules/teastore/validation/candidate_readiness.py"
    spec = importlib.util.spec_from_file_location(
        "candidate_runtime_readiness_replayer", path,
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise GateError(f"cannot load candidate readiness checker: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "validate_seam_pair", None)):
        raise GateError("candidate readiness checker has no validate_seam_pair")
    return module


def controller_digests() -> dict[str, str]:
    """Hash the exact local controller bytes that a future run must bind."""

    return {
        name: hashlib.sha256(_file_bytes(ROOT / relative, relative)).hexdigest()
        for name, relative in CONTROLLER_PATHS.items()
    }


def _frozen_timing(descriptor: Mapping[str, Any]) -> dict[str, int]:
    """Return timing only after replaying it against the frozen compiler."""

    timing = descriptor.get("timing")
    if not isinstance(timing, dict):
        raise GateError("candidate descriptor timing is absent")
    compiler = _candidate_module()
    if EPOCH["sweep"]:
        # Traffic sweep: onset and hold are per-cell plan values (cell["timing"]); only the shared
        # values are descriptor-level, replayed against the sweep compiler.
        expected = {
            "warmupSeconds": compiler.WARMUP_SECONDS,
            "measurementSeconds": compiler.MEASUREMENT_SECONDS,
            "minimumTimedSeconds": compiler.MINIMUM_TIMED_SECONDS,
        }
        if any(not _exact_int(timing.get(key), value) for key, value in expected.items()):
            raise GateError("candidate timing differs from the sweep compiler")
        return expected
    expected = {
        "warmupSeconds": compiler.WARMUP_SECONDS,
        "measurementSeconds": compiler.MEASUREMENT_SECONDS,
        "faultOnsetSeconds": compiler.FAULT_ONSET_SECONDS,
        "interventionHoldSeconds": compiler.INTERVENTION_HOLD_SECONDS,
        "minimumTimedSeconds": compiler.MINIMUM_TIMED_SECONDS,
    }
    if any(not _exact_int(timing.get(key), value) for key, value in expected.items()):
        raise GateError("candidate timing differs from the frozen compiler")
    if not _same_json_type(expected, {
        "warmupSeconds": 120,
        "measurementSeconds": 600,
        "faultOnsetSeconds": 180,
        "interventionHoldSeconds": 150,
        "minimumTimedSeconds": 19_440,
    }):
        raise GateError("installed compiler timing differs from candidate-pilot v1")
    return expected


@dataclass(frozen=True)
class CampaignBindings:
    root: Path
    framework_commit: str
    framework_tree: str
    descriptor: dict[str, Any]
    plan: dict[str, Any]
    campaign: dict[str, Any]
    descriptor_sha256: str
    plan_sha256: str
    campaign_sha256: str
    run_ids: tuple[str, ...]
    cells: tuple[dict[str, Any], ...]
    controller_sha256: dict[str, str]


def inspect_campaign(root: Path, framework_commit: str) -> CampaignBindings:
    """Replay one already-materialized candidate campaign without writing it."""

    if not isinstance(framework_commit, str) or COMMIT_RE.fullmatch(framework_commit) is None:
        raise GateError("framework_commit must be one full lowercase Git object")
    initial_git_state = _git_repository_state()
    _verify_git_binding(framework_commit, initial_git_state)
    root = Path(root).resolve()
    descriptor_path = root / "campaign-descriptor.json"
    plan_path = root / "compiled-plan.json"
    campaign_path = root / "campaign.json"
    descriptor_bytes = _file_bytes(descriptor_path, "campaign descriptor")
    plan_bytes = _file_bytes(plan_path, "compiled plan")
    campaign_bytes = _file_bytes(campaign_path, "campaign manifest")
    descriptor = _strict_json(descriptor_bytes, "campaign descriptor")
    plan = _strict_json(plan_bytes, "compiled plan")
    campaign = _strict_json(campaign_bytes, "campaign manifest")
    if not all(isinstance(value, dict) for value in (descriptor, plan, campaign)):
        raise GateError("candidate descriptor, plan, and campaign must be JSON objects")
    campaign = _exact(campaign, {
        "schemaVersion", "contract", "kind", "studyEpoch", "descriptorId",
        "descriptorCanonicalSha256", "descriptorBytesSha256",
        "compiledPlanCanonicalSha256", "compiledPlanBytesSha256",
        "scheduleVersion", "selectorDigests", "schedules", "runs", "runCount",
        "maximumEvidenceLabel", "canonical", "promotionAuthorized",
        "runtimeEnabledByThisManifest",
    }, "campaign manifest")

    compiler = _candidate_module()
    try:
        compiler.validate_descriptor(descriptor)
        compiler.validate_plan(descriptor, plan)
    except ValueError as exc:
        raise GateError(f"candidate descriptor/plan replay failed: {exc}") from exc
    _frozen_timing(descriptor)
    if (
        not _exact_int(plan.get("runCount"), RUN_COUNT)
        or not _exact_int(campaign.get("runCount"), RUN_COUNT)
    ):
        raise GateError(f"candidate campaign does not contain exactly {RUN_COUNT} cells")
    if plan.get("studyEpoch") != STUDY_EPOCH or campaign.get("studyEpoch") != STUDY_EPOCH:
        raise GateError("candidate campaign study epoch differs")
    descriptor_sha = canonical_sha256(descriptor)
    plan_sha = canonical_sha256(plan)
    campaign_sha = hashlib.sha256(campaign_bytes).hexdigest()
    if (
        not _exact_int(campaign.get("schemaVersion"), 1)
        or campaign.get("contract") != CANDIDATE_CAMPAIGN_CONTRACT
        or campaign.get("kind") != "candidate-pilot-campaign"
        or campaign.get("scheduleVersion") != EPOCH["scheduleVersion"]
        or campaign.get("descriptorCanonicalSha256") != descriptor_sha
        or campaign.get("compiledPlanCanonicalSha256") != plan_sha
        or campaign.get("descriptorBytesSha256") != hashlib.sha256(descriptor_bytes).hexdigest()
        or campaign.get("compiledPlanBytesSha256") != hashlib.sha256(plan_bytes).hexdigest()
        or campaign.get("maximumEvidenceLabel") != EVIDENCE_LABEL
        or campaign.get("canonical") is not False
        or campaign.get("promotionAuthorized") is not False
        or campaign.get("runtimeEnabledByThisManifest") is not False
    ):
        raise GateError("campaign manifest bindings or non-authority boundary differ")

    # Execution order: the frozen regime-major regimeRoots, or the sweep's blocks (lead cell, seeded order).
    cells: list[dict[str, Any]] = copy.deepcopy(
        _study_epoch_module().flatten_plan_cells(plan))
    run_ids = tuple(cell.get("runId") for cell in cells)
    expected_campaign_runs = []
    for cell in cells:
        key = cell["runKey"]
        block = key["block"]
        ordinal = cell["ordinalPosition"]
        expected_campaign_runs.append({
            "studyEpoch": key["studyEpoch"],
            "regime": key["regime"],
            "block": block,
            "posture": key["posture"],
            "attempt": key["attempt"],
            "ordinal": ordinal,
            "runId": cell["runId"],
            "compiledArtifactRoot": cell["artifactRoot"],
            "path": (
                f"runs/{key['regime']}/b{block:02d}-{ordinal:02d}-{key['posture']}"
            ),
        })
    allocation = plan.get("scheduleAllocation", {})
    expected_selectors = {
        regime: allocation[regime]["selectorSha256"] for regime in allocation
    }
    expected_schedules = {
        regime: allocation[regime]["blocks"] for regime in allocation
    }
    if (
        len(cells) != RUN_COUNT
        or len(set(run_ids)) != RUN_COUNT
        or any(not isinstance(run_id, str) for run_id in run_ids)
        or not _same_json_type(campaign.get("runs"), expected_campaign_runs)
        or not _same_json_type(campaign.get("selectorDigests"), expected_selectors)
        or not _same_json_type(campaign.get("schedules"), expected_schedules)
        or any(
            not _exact_int(cell.get("runKey", {}).get("attempt"), ATTEMPT)
            for cell in cells
        )
    ):
        raise GateError("campaign cell order, identity, or attempt differs")
    digests = controller_digests()
    final_git_state = _git_repository_state()
    _verify_git_binding(
        framework_commit, final_git_state, previous=initial_git_state,
    )
    return CampaignBindings(
        root=root,
        framework_commit=framework_commit,
        framework_tree=initial_git_state.head_tree,
        descriptor=copy.deepcopy(descriptor),
        plan=copy.deepcopy(plan),
        campaign=copy.deepcopy(campaign),
        descriptor_sha256=descriptor_sha,
        plan_sha256=plan_sha,
        campaign_sha256=campaign_sha,
        run_ids=run_ids,
        cells=tuple(cells),
        controller_sha256=digests,
    )


def plan_binding(bindings: CampaignBindings) -> dict[str, Any]:
    return {
        "studyEpoch": STUDY_EPOCH,
        "changeId": CHANGE_ID,
        "frameworkCommit": bindings.framework_commit,
        "descriptorCanonicalSha256": bindings.descriptor_sha256,
        "compiledPlanCanonicalSha256": bindings.plan_sha256,
        "runCount": RUN_COUNT,
        "target": TARGET,
        "maximumEvidenceLabel": EVIDENCE_LABEL,
    }


def expected_gate_plan_text(bindings: CampaignBindings) -> str:
    value = plan_binding(bindings)
    return (
        f"APPROVE GATE-PLAN study={value['studyEpoch']} change={value['changeId']} "
        f"framework={value['frameworkCommit']} "
        f"descriptor={value['descriptorCanonicalSha256']} "
        f"plan={value['compiledPlanCanonicalSha256']} runs={RUN_COUNT} "
        f"maximum-evidence={EVIDENCE_LABEL} runtime-not-authorized"
    )


def validate_gate_plan(document: Any, bindings: CampaignBindings) -> str:
    root = _exact(document, {
        "schemaVersion", "kind", "gate", "decision", "typedApproval",
        "approvedBy", "approvedAt", "bindings", "runtimeAuthorized",
        "promotionAuthorized",
    }, "GATE-PLAN")
    if (
        not _exact_int(root["schemaVersion"], 1)
        or root["kind"] != PLAN_KIND
        or root["gate"] != "GATE-PLAN"
        or root["decision"] != "approve-exact-plan"
        or root["typedApproval"] != expected_gate_plan_text(bindings)
        or not isinstance(root["approvedBy"], str)
        or not root["approvedBy"].strip()
        or not _same_json_type(root["bindings"], plan_binding(bindings))
        or root["runtimeAuthorized"] is not False
        or root["promotionAuthorized"] is not False
    ):
        raise GateError("GATE-PLAN identity, exact typed approval, or authority ceiling differs")
    _timestamp(root["approvedAt"], "GATE-PLAN.approvedAt")
    return canonical_sha256(root)


def candidate_release_root(
    *, setup_id: str, framework_commit: str, bundle_sha256: str,
) -> str:
    """Derive the only admitted v4 release path from collision-resistant inputs."""

    if SETUP_ID_RE.fullmatch(setup_id) is None:
        raise GateError("candidate setup ID must be 128-bit lowercase hexadecimal")
    if COMMIT_RE.fullmatch(framework_commit) is None or SHA256_RE.fullmatch(
        bundle_sha256
    ) is None:
        raise GateError("candidate release identity is malformed")
    return (
        f"{RELEASES_ROOT}/{setup_id}-{framework_commit[:12]}-"
        f"{bundle_sha256[:16]}"
    )


def candidate_results_root(*, setup_id: str) -> str:
    if SETUP_ID_RE.fullmatch(setup_id) is None:
        raise GateError("candidate setup ID must be 128-bit lowercase hexadecimal")
    return f"{RESULTS_ROOT}/{setup_id}"


def validate_target_proof(document: Any, bindings: CampaignBindings) -> str:
    """Validate a retained, read-only target identity and Docker capability probe."""

    root = _exact(document, {
        "schemaVersion", "kind", "target", "capturedAt", "probeSha256",
        "transport", "executionCapabilities", "dockerSocket", "legacyRoots",
        "candidateV4Root", "hostIdentity", "pythonRuntime",
    }, "candidate target proof")
    host_identity = _exact(
        root["hostIdentity"], {"hostname", "fqdn", "machineIdSha256"},
        "candidate target host identity",
    )
    if (
        host_identity["hostname"] != TARGET
        or host_identity["fqdn"] != TARGET_HOSTNAME
        or not isinstance(host_identity["machineIdSha256"], str)
        or SHA256_RE.fullmatch(host_identity["machineIdSha256"]) is None
        or host_identity["machineIdSha256"] != TARGET_MACHINE_ID_SHA256
    ):
        raise GateError("candidate target host identity differs")
    python_runtime = _exact(
        root["pythonRuntime"], {
            "executable", "version", "requiredLanguageVersion", "observedTargetPatch",
        },
        "candidate target Python runtime",
    )
    version = python_runtime["version"]
    if (
        python_runtime["executable"] != "/usr/bin/python3"
        or python_runtime["requiredLanguageVersion"] != [3, 9]
        or python_runtime["observedTargetPatch"] != [3, 9, 2]
        or not isinstance(version, list)
        or len(version) != 3
        or any(type(value) is not int or value < 0 for value in version)
        or version != [3, 9, 2]
    ):
        raise GateError("candidate target Python runtime differs")
    transport = _exact(root["transport"], {"user", "uid", "gid"}, "target transport")
    capabilities = _exact(
        root["executionCapabilities"], {"root", EXECUTION_USER},
        "target execution capabilities",
    )
    docker_socket = _exact(
        root["dockerSocket"], {"path", "ownerUid", "ownerGid", "mode"},
        "target Docker socket",
    )
    if (
        not _exact_int(root["schemaVersion"], 1)
        or root["kind"] != TARGET_PROOF_KIND
        or root["target"] != TARGET
        or root["probeSha256"] != bindings.controller_sha256[
            "candidate-release-installer"
        ]
        or transport != {"user": TRANSPORT_USER, "uid": 0, "gid": 0}
        or docker_socket != {
            "path": "/var/run/docker.sock", "ownerUid": 0,
            "ownerGid": EXECUTION_DOCKER_GID, "mode": "0660",
        }
    ):
        raise GateError("target proof transport identity or probe bytes differ")
    _timestamp(root["capturedAt"], "candidate target proof capturedAt")
    expected_methods = {EXECUTION_USER: EXECUTION_METHOD, "root": "direct"}
    for user, value in capabilities.items():
        row = _exact(
            value,
            {"uid", "gid", "supplementaryGids", "home", "executionMethod",
             "dockerAccess", "dockerProbeExitCode"},
            f"target execution capability {user}",
        )
        if (
            type(row["uid"]) is not int
            or row["uid"] < 0
            or type(row["gid"]) is not int
            or row["gid"] < 0
            or not isinstance(row["supplementaryGids"], list)
            or any(type(group) is not int or group < 0 for group in row["supplementaryGids"])
            or row["supplementaryGids"] != sorted(set(row["supplementaryGids"]))
            or not isinstance(row["home"], str)
            or row["executionMethod"] != expected_methods[user]
            or type(row["dockerAccess"]) is not bool
            or type(row["dockerProbeExitCode"]) is not int
            or (row["dockerAccess"] is not (row["dockerProbeExitCode"] == 0))
            or (user == "root" and (row["uid"] != 0 or row["home"] != "/root"))
            or (user == EXECUTION_USER and (
                row["uid"] != EXECUTION_UID
                or row["gid"] != EXECUTION_GID
                or EXECUTION_DOCKER_GID not in row["supplementaryGids"]
                or row["home"] != "/home/stig"
            ))
        ):
            raise GateError(f"target execution capability {user} differs")
    legacy = root["legacyRoots"]
    expected_legacy = {
        "/home/stig/observability-placement-runs",
        "/home/stig/observability-placement-results",
    }
    if not isinstance(legacy, list) or len(legacy) != 2:
        raise GateError("target proof must report both inaccessible legacy roots")
    observed_legacy: set[str] = set()
    for index, value in enumerate(legacy):
        row = _exact(
            value, {"path", "exists", "ownerUid", "ownerGid", "mode",
                    "accessibleByStig"}, f"legacy root {index}",
        )
        if (
            row["path"] not in expected_legacy
            or row["path"] in observed_legacy
            or type(row["exists"]) is not bool
            or (row["ownerUid"] is not None and type(row["ownerUid"]) is not int)
            or (row["ownerGid"] is not None and type(row["ownerGid"]) is not int)
            or (row["mode"] is not None and (
                not isinstance(row["mode"], str)
                or re.fullmatch(r"0[0-7]{3}", row["mode"]) is None
            ))
            or type(row["accessibleByStig"]) is not bool
            or row["exists"] is not True
            or row["ownerUid"] != 0
            or row["ownerGid"] != 0
            or row["mode"] != "0700"
            or row["accessibleByStig"] is not False
        ):
            raise GateError("target legacy-root observation differs")
        observed_legacy.add(row["path"])
    candidate = _exact(
        root["candidateV4Root"], {"path", "exists"}, "candidate v4 root",
    )
    if candidate["path"] != CANDIDATE_V4_ROOT or type(candidate["exists"]) is not bool:
        raise GateError("target proof candidate-v4 root differs")
    return canonical_sha256(root)


def validate_release_manifest(document: Any, bindings: CampaignBindings) -> str:
    root = _exact(document, {
        "schemaVersion", "kind", "frameworkCommit", "frameworkTree",
        "bundleFormat", "bundleSha256", "bundleBytes", "bundleMembers",
        "controllerDigests", "submoduleCommits", "setupSourceBuildAllowed",
        "campaignSourceBuildAllowed",
    }, "candidate release manifest")
    controllers = _validate_sha_map(
        root["controllerDigests"], set(CONTROLLER_PATHS),
        "candidate release controllers",
    )
    submodules = _exact(
        root["submoduleCommits"], {"upstream/teastore"},
        "candidate release submodules",
    )
    members = _exact(
        root["bundleMembers"], {"superproject.bundle", "upstream-teastore.bundle"},
        "candidate release bundle members",
    )
    for name, value in members.items():
        member = _exact(
            value, {"sha256", "bytes", "commit", "tree"},
            f"candidate release bundle member {name}",
        )
        if (
            not isinstance(member["sha256"], str)
            or SHA256_RE.fullmatch(member["sha256"]) is None
            or type(member["bytes"]) is not int
            or member["bytes"] <= 0
            or not isinstance(member["commit"], str)
            or COMMIT_RE.fullmatch(member["commit"]) is None
            or not isinstance(member["tree"], str)
            or COMMIT_RE.fullmatch(member["tree"]) is None
        ):
            raise GateError(f"candidate release bundle member {name} differs")
    if (
        not _exact_int(root["schemaVersion"], 1)
        or root["kind"] != RELEASE_MANIFEST_KIND
        or root["frameworkCommit"] != bindings.framework_commit
        or root["frameworkTree"] != bindings.framework_tree
        or root["bundleFormat"] != "candidate-v4-tar-v1"
        or not isinstance(root["bundleSha256"], str)
        or SHA256_RE.fullmatch(root["bundleSha256"]) is None
        or type(root["bundleBytes"]) is not int
        or root["bundleBytes"] <= 0
        or controllers != bindings.controller_sha256
        or submodules["upstream/teastore"]
        != "34b37f7e7be433ce72d5f9455e66922a13116749"
        or members["superproject.bundle"]["commit"] != bindings.framework_commit
        or members["superproject.bundle"]["tree"] != bindings.framework_tree
        or members["upstream-teastore.bundle"]["commit"]
        != submodules["upstream/teastore"]
        or root["setupSourceBuildAllowed"] is not True
        or root["campaignSourceBuildAllowed"] is not False
    ):
        raise GateError("candidate release manifest identity or boundary differs")
    return canonical_sha256(root)


def setup_authorization(
    bindings: CampaignBindings,
    gate_plan_sha256: str,
    target_proof: Mapping[str, Any],
    release_manifest: Mapping[str, Any],
    *,
    setup_id: str,
    execution_user: str,
    not_before: str,
    authorization_deadline: str,
) -> dict[str, Any]:
    """Build the exact setup-only authority between GATE-PLAN and readiness."""

    if execution_user != EXECUTION_USER:
        raise GateError("candidate execution user is not admitted")
    capabilities = target_proof.get("executionCapabilities", {})
    capability = capabilities.get(execution_user) if isinstance(capabilities, Mapping) else None
    if (
        not isinstance(capability, Mapping)
        or capability.get("uid") != EXECUTION_UID
        or capability.get("gid") != EXECUTION_GID
        or capability.get("executionMethod") != EXECUTION_METHOD
        or not isinstance(capability.get("supplementaryGids"), list)
        or EXECUTION_DOCKER_GID not in capability["supplementaryGids"]
        or capability.get("dockerAccess") is not True
    ):
        raise GateError("chosen execution user has no retained Docker-access proof")
    bundle_sha = release_manifest.get("bundleSha256")
    if not isinstance(bundle_sha, str):
        raise GateError("candidate release bundle digest is absent")
    return {
        "setupId": setup_id,
        "studyEpoch": STUDY_EPOCH,
        "target": TARGET,
        "transportUser": TRANSPORT_USER,
        "executionUser": execution_user,
        "executionUid": EXECUTION_UID,
        "executionGid": EXECUTION_GID,
        "executionMethod": EXECUTION_METHOD,
        "frameworkCommit": bindings.framework_commit,
        "frameworkTree": bindings.framework_tree,
        "descriptorCanonicalSha256": bindings.descriptor_sha256,
        "compiledPlanCanonicalSha256": bindings.plan_sha256,
        "gatePlanSha256": gate_plan_sha256,
        "targetProofSha256": canonical_sha256(target_proof),
        "releaseManifestSha256": canonical_sha256(release_manifest),
        "bundleSha256": bundle_sha,
        "bundleBytes": release_manifest["bundleBytes"],
        "controllerDigestsSha256": canonical_sha256(
            release_manifest["controllerDigests"]
        ),
        "releaseRoot": candidate_release_root(
            setup_id=setup_id,
            framework_commit=bindings.framework_commit,
            bundle_sha256=bundle_sha,
        ),
        "resultsRoot": candidate_results_root(setup_id=setup_id),
        "exclusiveLeasePath": LEASE_PATH,
        "allowedActions": [
            "install-exact-release",
            "build-and-inspect-patched-images",
            "collect-runtime-readiness",
            "cleanup-readiness-resources",
            "remove-setup-staging",
        ],
        "experimentalCellsAuthorized": 0,
        "notBefore": not_before,
        "authorizationDeadline": authorization_deadline,
    }


def expected_gate_setup_text(authorization: Mapping[str, Any]) -> str:
    return (
        f"APPROVE GATE-SETUP setup={authorization['setupId']} "
        f"target={authorization['target']} transport-user={TRANSPORT_USER} "
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


def validate_gate_setup(
    document: Any,
    bindings: CampaignBindings,
    gate_plan: Mapping[str, Any],
    target_proof: Mapping[str, Any],
    release_manifest: Mapping[str, Any],
    *,
    now: datetime,
) -> str:
    root = _exact(document, {
        "schemaVersion", "kind", "gate", "decision", "typedApproval",
        "approvedBy", "approvedAt", "authorization", "runtimeAuthorized",
        "promotionAuthorized",
    }, "GATE-SETUP")
    authorization = _exact(root["authorization"], {
        "setupId", "studyEpoch", "target", "transportUser", "executionUser",
        "executionUid", "executionGid", "executionMethod", "frameworkCommit",
        "frameworkTree", "descriptorCanonicalSha256",
        "compiledPlanCanonicalSha256", "gatePlanSha256", "targetProofSha256",
        "releaseManifestSha256", "bundleSha256", "bundleBytes",
        "controllerDigestsSha256", "releaseRoot", "resultsRoot",
        "exclusiveLeasePath", "allowedActions", "experimentalCellsAuthorized",
        "notBefore", "authorizationDeadline",
    }, "GATE-SETUP.authorization")
    gate_plan_sha = validate_gate_plan(dict(gate_plan), bindings)
    validate_target_proof(dict(target_proof), bindings)
    validate_release_manifest(dict(release_manifest), bindings)
    expected = setup_authorization(
        bindings, gate_plan_sha, target_proof, release_manifest,
        setup_id=authorization["setupId"],
        execution_user=authorization["executionUser"],
        not_before=authorization["notBefore"],
        authorization_deadline=authorization["authorizationDeadline"],
    )
    if (
        not _exact_int(root["schemaVersion"], 1)
        or root["kind"] != SETUP_KIND
        or root["gate"] != "GATE-SETUP"
        or root["decision"] != "authorize-exact-setup-only"
        or root["typedApproval"] != expected_gate_setup_text(expected)
        or not isinstance(root["approvedBy"], str)
        or not root["approvedBy"].strip()
        or not _same_json_type(authorization, expected)
        or root["runtimeAuthorized"] is not False
        or root["promotionAuthorized"] is not False
    ):
        raise GateError("GATE-SETUP identity, typed approval, or authority ceiling differs")
    observed = _now(lambda: now)
    approved = _timestamp(root["approvedAt"], "GATE-SETUP.approvedAt")
    plan_approved = _timestamp(gate_plan["approvedAt"], "GATE-PLAN.approvedAt")
    proof_captured = _timestamp(target_proof["capturedAt"], "target proof capturedAt")
    not_before = _timestamp(authorization["notBefore"], "GATE-SETUP.notBefore")
    deadline = _timestamp(
        authorization["authorizationDeadline"], "GATE-SETUP.authorizationDeadline"
    )
    if plan_approved > approved or proof_captured > approved:
        raise GateError("GATE-SETUP predates its plan or target proof")
    age = math.floor((observed - approved).total_seconds())
    if age < -MAX_CLOCK_SKEW_SECONDS or age > MAX_GATE_SETUP_AGE_SECONDS:
        raise GateError("GATE-SETUP is not a fresh approval")
    if observed < not_before or deadline <= observed:
        raise GateError("GATE-SETUP authorization window is not open")
    return canonical_sha256(root)


def _validate_sha_map(value: Any, expected_keys: set[str], where: str) -> dict[str, str]:
    row = _exact(value, expected_keys, where)
    for key, digest in row.items():
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise GateError(f"{where}.{key} must be one lowercase SHA-256")
    return row


def _image_repository(image: str) -> str:
    tail = image.rsplit("/", 1)[-1]
    return image.rsplit(":", 1)[0] if ":" in tail else image


def validate_image_build_receipt(
    value: Any, *, setup_id: str, framework_commit: str,
) -> dict[str, Any]:
    """Replay the setup-time build/inspection receipt without trusting labels alone."""

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
    input_contract = ROOT / CONTROLLER_PATHS["patched-image-inputs"]
    expected_input_sha = hashlib.sha256(
        _file_bytes(input_contract, "patched-image input contract")
    ).hexdigest()
    if (
        not _exact_int(root.get("schemaVersion"), 1)
        or root.get("kind") != IMAGE_BUILD_KIND
        or root.get("setupId") != setup_id
        or root.get("target") != TARGET
        or root.get("executionUser") != EXECUTION_USER
        or not _exact_int(root.get("executionUid"), EXECUTION_UID)
        or not _exact_int(root.get("executionGid"), EXECUTION_GID)
        or root.get("frameworkCommit") != framework_commit
        or root.get("sourceCommit") != SOURCE_COMMIT
        or root.get("patchSha256") != PATCH_SHA256
        or root.get("inputContractSha256") != expected_input_sha
        or root.get("mavenCommand") != list(MAVEN_COMMAND)
        or any(
            not isinstance(root.get(key), str)
            or SHA256_RE.fullmatch(root[key]) is None
            for key in ("mavenStdoutSha256", "mavenStderrSha256")
        )
        or not isinstance(services, dict)
        or set(services) != set(IMAGE_SERVICES)
        or not isinstance(images, dict)
        or set(images) != set(IMAGE_SERVICES)
        or not _exact_int(root.get("cellsRun"), 0)
        or not _exact_int(root.get("containersStarted"), 0)
        or root.get("temporaryContainersRemoved") is not True
        or root.get("ready") is not True
        or root.get("promotionAuthorized") is not False
        or not isinstance(root.get("priorDeclaredImageConfigIds"), dict)
        or set(root["priorDeclaredImageConfigIds"]) != set(PATCHED_IMAGE_REPOSITORIES)
        or not isinstance(root.get("uniqueBuildTags"), dict)
        or set(root["uniqueBuildTags"]) != set(PATCHED_IMAGE_REPOSITORIES)
    ):
        raise GateError("patched-image build identity or authority differs")
    started = _timestamp(root.get("buildStartedAt"), "patched-image buildStartedAt")
    completed = _timestamp(root.get("completedAt"), "patched-image completedAt")
    if completed < started:
        raise GateError("patched-image build timestamps are reversed")
    for service, declared in DECLARED_RUNTIME_IMAGES.items():
        row = _exact(services.get(service), {
            "mode", "declaredImage", "imageConfigId", "localContentReference",
            "architecture", "operatingSystem", "repoDigests", "artifactSha256",
            "dockerfileSha256", "labels",
        }, f"patched-image service {service}")
        patched = service in PATCHED_IMAGE_REPOSITORIES
        repository = PATCHED_IMAGE_REPOSITORIES.get(
            service, _image_repository(declared),
        )
        image_id = row.get("imageConfigId")
        content_reference = (
            f"{repository}@{image_id}" if isinstance(image_id, str) else ""
        )
        repo_digests = row.get("repoDigests")
        expected_labels = {
            "org.opencontainers.image.revision": SOURCE_COMMIT,
            "org.observability-placement.patch.sha256": PATCH_SHA256,
            "org.observability-placement.service": service,
        }
        if (
            row.get("mode") != ("patched-build" if patched else "exact-inspection")
            or row.get("declaredImage") != declared
            or not isinstance(image_id, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None
            or row.get("localContentReference") != content_reference
            or images.get(service) != content_reference
            or row.get("architecture") != "amd64"
            or row.get("operatingSystem") != "linux"
            or not isinstance(repo_digests, list)
            or any(
                not isinstance(item, str)
                or re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", item) is None
                for item in repo_digests
            )
            or repo_digests != sorted(set(repo_digests))
            or (
                patched and (
                    not isinstance(row.get("artifactSha256"), str)
                    or SHA256_RE.fullmatch(row["artifactSha256"]) is None
                    or not isinstance(row.get("dockerfileSha256"), str)
                    or SHA256_RE.fullmatch(row["dockerfileSha256"]) is None
                    or row.get("labels") != expected_labels
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
            raise GateError(f"patched-image service identity differs: {service}")
    return copy.deepcopy(root)


def _validate_readiness_release(
    summary: Any,
    install: Any,
    *,
    bindings: CampaignBindings,
    gate_setup_sha256: str,
    release_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    keys = RELEASE_BINDING_KEYS
    row = _exact(summary, keys, "runtime readiness release summary")
    receipt = _exact(install, keys | {
        "schemaVersion", "kind", "state", "runtimeExecuted",
        "promotionAuthorized",
    }, "runtime readiness release install receipt")
    if not _same_json_type(row, {key: receipt[key] for key in keys}):
        raise GateError("runtime readiness release summary differs from install receipt")
    if (
        not _exact_int(receipt["schemaVersion"], 1)
        or receipt["kind"] != RELEASE_INSTALL_KIND
        or receipt["state"] != "installed"
        or receipt["setupId"] != row["setupId"]
        or receipt["target"] != TARGET
        or receipt["transportUser"] != TRANSPORT_USER
        or receipt["executionUser"] != EXECUTION_USER
        or receipt["executionUid"] != EXECUTION_UID
        or receipt["executionGid"] != EXECUTION_GID
        or receipt["executionMethod"] != EXECUTION_METHOD
        or receipt["frameworkCommit"] != bindings.framework_commit
        or receipt["frameworkTree"] != bindings.framework_tree
        or receipt["bundleSha256"] != release_manifest["bundleSha256"]
        or receipt["releaseManifestSha256"] != canonical_sha256(release_manifest)
        or receipt["gateSetupSha256"] != gate_setup_sha256
        or receipt["releaseRoot"] != candidate_release_root(
            setup_id=receipt["setupId"],
            framework_commit=bindings.framework_commit,
            bundle_sha256=release_manifest["bundleSha256"],
        )
        or receipt["resultsRoot"] != candidate_results_root(
            setup_id=receipt["setupId"]
        )
        or receipt["exclusiveLeasePath"] != LEASE_PATH
        or receipt["controllerDigests"] != bindings.controller_sha256
        or receipt["runtimeExecuted"] is not False
        or receipt["promotionAuthorized"] is not False
    ):
        raise GateError("runtime readiness release install identity differs")
    image_build = validate_image_build_receipt(
        receipt["imageBuild"], setup_id=receipt["setupId"],
        framework_commit=bindings.framework_commit,
    )
    if receipt["imageBuildReceiptSha256"] != canonical_sha256(image_build):
        raise GateError("runtime readiness patched-image receipt digest differs")
    _timestamp(receipt["installedAt"], "runtime readiness release installedAt")
    return copy.deepcopy(row)


def _validate_runtime_preflight(value: Any, *, release: Mapping[str, Any]) -> datetime:
    """Validate the installed, read-only resource proof captured before GATE-RUN."""

    root = _exact(value, {
        "schemaVersion", "kind", "target", "capturedAt", "executionIdentity",
        "docker", "resourceInventory", "blockers", "ready",
        "experimentalCellsExecuted", "mutationPerformed",
    }, "installed runtime preflight")
    identity = _exact(root["executionIdentity"], {
        "user", "uid", "gid", "supplementaryGids", "executionMethod",
    }, "installed runtime preflight execution identity")
    docker = _exact(root["docker"], {
        "serverVersion", "socketOwnerUid", "socketOwnerGid", "socketMode",
        "accessAsExecutionUser",
    }, "installed runtime preflight Docker proof")
    inventory = _exact(root["resourceInventory"], {
        "projectPrefix", "reservedPorts", "composeProjects",
        "reservedPortListeners",
    }, "installed runtime preflight resource inventory")
    if (
        not _exact_int(root["schemaVersion"], 1)
        or root["kind"] != RUNTIME_PREFLIGHT_KIND
        or root["target"] != TARGET
        or identity != {
            "user": EXECUTION_USER,
            "uid": EXECUTION_UID,
            "gid": EXECUTION_GID,
            "supplementaryGids": list(EXECUTION_SUPPLEMENTARY_GIDS),
            "executionMethod": EXECUTION_METHOD,
        }
        or docker != {
            "serverVersion": DOCKER_SERVER_VERSION,
            "socketOwnerUid": 0,
            "socketOwnerGid": EXECUTION_DOCKER_GID,
            "socketMode": "0660",
            "accessAsExecutionUser": True,
        }
        or inventory["projectPrefix"] != PROJECT_PREFIX
        or inventory["reservedPorts"] != list(RESERVED_PORTS)
        or root["blockers"] != []
        or root["ready"] is not True
        or not _exact_int(root["experimentalCellsExecuted"], 0)
        or root["mutationPerformed"] is not False
    ):
        raise GateError("installed runtime preflight identity or readiness differs")
    projects = inventory["composeProjects"]
    if not isinstance(projects, list):
        raise GateError("installed runtime preflight Compose inventory is malformed")
    observed_names: list[str] = []
    for index, value in enumerate(projects):
        row = _exact(value, {
            "name", "status", "configFiles", "active", "candidateNamespace",
        }, f"installed runtime preflight Compose project {index}")
        if (
            not isinstance(row["name"], str) or not row["name"]
            or not isinstance(row["status"], str) or not row["status"]
            or not isinstance(row["configFiles"], str)
            or type(row["active"]) is not bool
            or type(row["candidateNamespace"]) is not bool
            or row["candidateNamespace"] is not row["name"].startswith(PROJECT_PREFIX)
            or row["active"] is True
            or row["candidateNamespace"] is True
        ):
            raise GateError("installed runtime preflight has active or overlapping project")
        observed_names.append(row["name"])
    if observed_names != sorted(set(observed_names)):
        raise GateError("installed runtime preflight Compose projects are not unique/sorted")
    listeners = inventory["reservedPortListeners"]
    if not isinstance(listeners, list) or listeners:
        raise GateError("installed runtime preflight has a reserved host-port listener")
    captured = _timestamp(root["capturedAt"], "installed runtime preflight capturedAt")
    installed = _timestamp(release["installedAt"], "installed release installedAt")
    if captured < installed:
        raise GateError("installed runtime preflight predates exact release installation")
    return captured


def validate_readiness(
    document: Any,
    bindings: CampaignBindings,
    *,
    readiness_parent: Path,
) -> str:
    if isinstance(document, Mapping) and "readinessArchiveSha256" in document:
        raise GateError(
            "runtime readiness semantic replay failed: legacy caller-authored "
            "rawObservations or nested capture seal is forbidden"
        )
    root = _exact(document, {
        "schemaVersion", "kind", "studyEpoch", "frameworkCommit",
        "descriptorCanonicalSha256", "compiledPlanCanonicalSha256", "target",
        "runCount", "artifactRoot", "controllerDigests", "imageDigests",
        "patchedServices", "setupArtifacts", "release", "seams", "transport",
        "ingressArchiveSha256", "captureTreeSha256", "captureManifestPath",
        "captureManifestSha256", "runtimePreflight", "runtimeReady",
        "candidateEvidenceAuthorized", "promotionAuthorized",
    }, "runtime readiness")
    if (
        not _exact_int(root["schemaVersion"], 2)
        or root["kind"] != READINESS_KIND
        or root["studyEpoch"] != STUDY_EPOCH
        or root["frameworkCommit"] != bindings.framework_commit
        or root["descriptorCanonicalSha256"] != bindings.descriptor_sha256
        or root["compiledPlanCanonicalSha256"] != bindings.plan_sha256
        or root["target"] != TARGET
        or not _exact_int(root["runCount"], RUN_COUNT)
        or any(not isinstance(root[key], str) or SHA256_RE.fullmatch(root[key]) is None
               for key in ("ingressArchiveSha256", "captureTreeSha256", "captureManifestSha256"))
        or root["patchedServices"] != list(PATCHED_SERVICES)
        or root["runtimeReady"] is not True
        or root["candidateEvidenceAuthorized"] is not False
        or root["promotionAuthorized"] is not False
    ):
        raise GateError("runtime-readiness source, scope, or authority ceiling differs")
    if root["ingressArchiveSha256"] == root["captureTreeSha256"]:
        raise GateError("runtime readiness ingress archive and capture tree digests alias")
    controllers = _validate_sha_map(
        root["controllerDigests"], set(CONTROLLER_PATHS), "runtime readiness controllers")
    if controllers != bindings.controller_sha256:
        raise GateError("runtime-readiness controller bytes differ from this checkout")
    artifacts = _artifact_root(readiness_parent, root["artifactRoot"])
    manifest_path, manifest_bytes = _artifact_file(
        readiness_parent, root["captureManifestPath"], "root capture manifest",
    )
    if hashlib.sha256(manifest_bytes).hexdigest() != root["captureManifestSha256"]:
        raise GateError("root capture manifest byte digest differs")
    capture_manifest = _strict_json(manifest_bytes, str(manifest_path))
    capture_manifest = _exact(capture_manifest, {
        "schemaVersion", "kind", "ingressArchiveSha256", "entries",
        "entriesCanonicalSha256",
    }, "root capture manifest")
    actual_entries = []
    for path in sorted(value for value in artifacts.rglob("*") if value.is_file()):
        payload = _file_bytes(path, "root capture manifest member")
        actual_entries.append({"path": path.relative_to(artifacts).as_posix(),
                               "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    if (
        capture_manifest.get("schemaVersion") != 1
        or capture_manifest.get("kind") != "teastore-candidate-root-capture-manifest-v2"
        or capture_manifest.get("ingressArchiveSha256") != root["ingressArchiveSha256"]
        or capture_manifest.get("entries") != actual_entries
        or capture_manifest.get("entriesCanonicalSha256") != canonical_sha256(actual_entries)
            or canonical_sha256(capture_manifest) != root["captureTreeSha256"]
    ):
        raise GateError("root capture tree differs from its enclosing manifest")
    setup_artifacts = _exact(root["setupArtifacts"], {
        "gatePlanPath", "gatePlanBytesSha256", "targetProofPath",
        "targetProofBytesSha256", "releaseManifestPath",
        "releaseManifestBytesSha256", "gateSetupPath", "gateSetupBytesSha256",
        "releaseInstallPath", "releaseInstallBytesSha256",
    }, "runtime readiness setup artifacts")
    setup_payloads: dict[str, bytes] = {}
    setup_documents: dict[str, dict[str, Any]] = {}
    setup_names = {
        "gatePlan": ("gatePlanPath", "gatePlanBytesSha256"),
        "targetProof": ("targetProofPath", "targetProofBytesSha256"),
        "releaseManifest": ("releaseManifestPath", "releaseManifestBytesSha256"),
        "gateSetup": ("gateSetupPath", "gateSetupBytesSha256"),
        "releaseInstall": ("releaseInstallPath", "releaseInstallBytesSha256"),
    }
    retained_paths: set[str] = set()
    for name, (path_key, sha_key) in setup_names.items():
        relative = setup_artifacts[path_key]
        if relative in retained_paths:
            raise GateError("runtime readiness setup artifacts alias")
        retained_paths.add(relative)
        _, payload = _artifact_file(
            artifacts, relative, f"runtime readiness {name} artifact",
        )
        expected_sha = setup_artifacts[sha_key]
        if (
            not isinstance(expected_sha, str)
            or SHA256_RE.fullmatch(expected_sha) is None
            or hashlib.sha256(payload).hexdigest() != expected_sha
        ):
            raise GateError(f"runtime readiness {name} artifact is unbound")
        setup_payloads[name] = payload
        parsed = _strict_json(payload, f"runtime readiness {name} artifact")
        if not isinstance(parsed, dict):
            raise GateError(f"runtime readiness {name} artifact is not an object")
        setup_documents[name] = parsed
    gate_plan_sha = validate_gate_plan(setup_documents["gatePlan"], bindings)
    validate_target_proof(setup_documents["targetProof"], bindings)
    validate_release_manifest(setup_documents["releaseManifest"], bindings)
    # Time freshness was enforced at mutation.  Readiness replays the complete
    # non-temporal setup identity and its retained digest without pretending a
    # later wall clock can retroactively invalidate an already installed release.
    gate_setup = setup_documents["gateSetup"]
    gate_setup_root = _exact(gate_setup, {
        "schemaVersion", "kind", "gate", "decision", "typedApproval",
        "approvedBy", "approvedAt", "authorization", "runtimeAuthorized",
        "promotionAuthorized",
    }, "retained GATE-SETUP")
    authorization = gate_setup_root.get("authorization")
    if not isinstance(authorization, Mapping):
        raise GateError("retained GATE-SETUP authorization is absent")
    expected_setup = setup_authorization(
        bindings, gate_plan_sha, setup_documents["targetProof"],
        setup_documents["releaseManifest"],
        setup_id=authorization.get("setupId"),
        execution_user=authorization.get("executionUser"),
        not_before=authorization.get("notBefore"),
        authorization_deadline=authorization.get("authorizationDeadline"),
    )
    if (
        gate_setup_root.get("schemaVersion") != 1
        or gate_setup_root.get("kind") != SETUP_KIND
        or gate_setup_root.get("gate") != "GATE-SETUP"
        or gate_setup_root.get("decision") != "authorize-exact-setup-only"
        or gate_setup_root.get("typedApproval") != expected_gate_setup_text(expected_setup)
        or not _same_json_type(authorization, expected_setup)
        or gate_setup_root.get("runtimeAuthorized") is not False
        or gate_setup_root.get("promotionAuthorized") is not False
    ):
        raise GateError("retained GATE-SETUP identity or ceiling differs")
    gate_setup_sha = canonical_sha256(gate_setup_root)
    release = _validate_readiness_release(
        root["release"], setup_documents["releaseInstall"],
        bindings=bindings,
        gate_setup_sha256=gate_setup_sha,
        release_manifest=setup_documents["releaseManifest"],
    )
    _validate_runtime_preflight(root["runtimePreflight"], release=release)
    images = _exact(root["imageDigests"], set(IMAGE_SERVICES), "runtime readiness images")
    if any(not isinstance(value, str) or IMAGE_RE.fullmatch(value) is None
           for value in images.values()):
        raise GateError("runtime-readiness images must be exact digest references")
    if images != release["imageBuild"]["imageDigests"]:
        raise GateError("runtime-readiness images differ from target build inspection")
    seams = _exact(root["seams"], set(READINESS_SEAMS), "runtime readiness seams")
    readiness_replayer = _candidate_readiness_module()
    readiness_validator_sha = bindings.controller_sha256[
        "candidate-readiness-checker"
    ]
    for name, row in seams.items():
        checked = _exact(
            row, {
                "status", "evidencePath", "evidenceSha256",
                "failureWitnessPath", "failureWitnessSha256",
            },
            f"runtime readiness seam {name}")
        if checked["status"] != "pass":
            raise GateError(f"runtime readiness seam {name} has not passed")
        evidence_path, evidence_bytes = _artifact_file(
            artifacts, checked["evidencePath"],
            f"runtime readiness seam {name} evidence")
        witness_path, witness_bytes = _artifact_file(
            artifacts, checked["failureWitnessPath"],
            f"runtime readiness seam {name} failure witness")
        relative_paths = (checked["evidencePath"], checked["failureWitnessPath"])
        if relative_paths[0] == relative_paths[1] or any(
            path in retained_paths for path in relative_paths
        ):
            raise GateError("runtime readiness seam artifacts must be path-distinct")
        retained_paths.update(relative_paths)
        for key, payload in (
            ("evidenceSha256", evidence_bytes),
            ("failureWitnessSha256", witness_bytes),
        ):
            expected = checked[key]
            if (
                not isinstance(expected, str)
                or SHA256_RE.fullmatch(expected) is None
                or hashlib.sha256(payload).hexdigest() != expected
            ):
                raise GateError(f"runtime readiness seam {name}.{key} is unbound")
        evidence = _strict_json(evidence_bytes, str(evidence_path))
        evidence = _exact(
            evidence,
            {"schemaVersion", "kind", "seam", "status", "validatorSha256", "observations"},
            f"runtime readiness seam {name} retained evidence",
        )
        if (
            not _exact_int(evidence["schemaVersion"], 1)
            or evidence["kind"] != READINESS_EVIDENCE_KIND
            or evidence["seam"] != name
            or evidence["status"] != "pass"
            or not isinstance(evidence["validatorSha256"], str)
            or SHA256_RE.fullmatch(evidence["validatorSha256"]) is None
            or evidence["validatorSha256"] not in set(bindings.controller_sha256.values())
            or not isinstance(evidence["observations"], dict)
        ):
            raise GateError(f"runtime readiness seam {name} evidence contract differs")
        witness = _strict_json(witness_bytes, str(witness_path))
        witness = _exact(
            witness,
            {
                "schemaVersion", "kind", "seam", "status", "plantedDefect",
                "checkerExitCode", "validatorSha256", "observations",
            },
            f"runtime readiness seam {name} retained failure witness",
        )
        if (
            not _exact_int(witness["schemaVersion"], 1)
            or witness["kind"] != FAILURE_WITNESS_KIND
            or witness["seam"] != name
            or witness["status"] != "detected"
            or not isinstance(witness["plantedDefect"], str)
            or not witness["plantedDefect"].strip()
            or type(witness["checkerExitCode"]) is not int
            or witness["checkerExitCode"] == 0
            or witness["validatorSha256"] != evidence["validatorSha256"]
            or not isinstance(witness["observations"], dict)
        ):
            raise GateError(f"runtime readiness seam {name} failure witness contract differs")
        try:
            readiness_replayer.validate_seam_pair(
                artifacts,
                seam=name,
                evidence=evidence,
                failure_witness=witness,
                framework_commit=bindings.framework_commit,
                descriptor_sha256=bindings.descriptor_sha256,
                plan_sha256=bindings.plan_sha256,
                image_digests=images,
                validator_sha256=readiness_validator_sha,
            )
        except Exception as exc:  # noqa: BLE001 - readiness must fail closed
            raise GateError(
                f"runtime readiness seam {name} semantic replay failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
    transport = _exact(root["transport"], {
        "schemaVersion", "contract", "target", "evidenceLabel", "outerLeasePath",
        "outerLeaseScope", "deadlineEnforced", "cleanupEnforced",
        "candidateDescriptorAccepted", "controllerDigests", "implementationPath",
        "implementationSha256", "transportUser", "executionUser",
        "executionMethod", "releaseRoot", "resultsRoot",
    }, "runtime readiness transport")
    if (
        not _exact_int(transport["schemaVersion"], 1)
        or transport["contract"] != TRANSPORT_CONTRACT
        or transport["target"] != TARGET
        or transport["evidenceLabel"] != EVIDENCE_LABEL
        or transport["outerLeasePath"] != LEASE_PATH
        or transport["outerLeaseScope"] != OUTER_LEASE_SCOPE
        or transport["deadlineEnforced"] is not True
        or transport["cleanupEnforced"] is not True
        or transport["candidateDescriptorAccepted"] is not True
        or transport["controllerDigests"] != bindings.controller_sha256
        or transport.get("transportUser") != TRANSPORT_USER
        or transport.get("executionUser") != release["executionUser"]
        or transport.get("executionMethod") != release["executionMethod"]
        or transport.get("releaseRoot") != release["releaseRoot"]
        or transport.get("resultsRoot") != release["resultsRoot"]
    ):
        raise GateError("bounded transport capability differs or remains diagnostic-only")
    implementation_path, implementation_bytes = _artifact_file(
        artifacts, transport["implementationPath"],
        "runtime readiness transport implementation")
    if transport["implementationPath"] in retained_paths:
        raise GateError("transport implementation path aliases a seam artifact")
    implementation_sha = transport["implementationSha256"]
    if (
        not isinstance(implementation_sha, str)
        or SHA256_RE.fullmatch(implementation_sha) is None
        or hashlib.sha256(implementation_bytes).hexdigest() != implementation_sha
        or not implementation_path.name.endswith(".py")
        or implementation_sha != bindings.controller_sha256[
            "bounded-candidate-transport"
        ]
        or implementation_bytes != _file_bytes(
            ROOT / CONTROLLER_PATHS["bounded-candidate-transport"],
            "installed bounded candidate transport",
        )
    ):
        raise GateError("bounded transport implementation bytes are unbound")
    try:
        compile(
            implementation_bytes.decode("utf-8", errors="strict"),
            str(implementation_path),
            "exec",
        )
    except (UnicodeError, SyntaxError) as exc:
        raise GateError("bounded transport implementation is not valid UTF-8 Python") from exc
    return canonical_sha256(root)


def run_authorization(
    bindings: CampaignBindings,
    gate_plan_sha256: str,
    readiness_sha256: str,
    *,
    readiness: Mapping[str, Any],
    campaign_id: str,
    not_before: str,
    authorization_deadline: str,
) -> dict[str, Any]:
    release = readiness.get("release")
    if not isinstance(release, Mapping):
        raise GateError("runtime readiness has no exact installed release")
    return {
        "campaignId": campaign_id,
        "studyEpoch": STUDY_EPOCH,
        "target": TARGET,
        "transportUser": TRANSPORT_USER,
        "executionUser": release["executionUser"],
        "executionUid": release["executionUid"],
        "executionGid": release["executionGid"],
        "executionMethod": release["executionMethod"],
        "releaseRoot": release["releaseRoot"],
        "resultsRoot": release["resultsRoot"],
        "exclusiveLeasePath": release["exclusiveLeasePath"],
        "setupId": release["setupId"],
        "gateSetupSha256": release["gateSetupSha256"],
        "releaseManifestSha256": release["releaseManifestSha256"],
        "bundleSha256": release["bundleSha256"],
        "releaseInstalledAt": release["installedAt"],
        "frameworkCommit": bindings.framework_commit,
        "descriptorCanonicalSha256": bindings.descriptor_sha256,
        "compiledPlanCanonicalSha256": bindings.plan_sha256,
        "gatePlanSha256": gate_plan_sha256,
        "runtimeReadinessSha256": readiness_sha256,
        "readinessArchiveSha256": readiness.get(
            "ingressArchiveSha256", readiness.get("readinessArchiveSha256")
        ),
        "runtimePreflightCapturedAt": readiness["runtimePreflight"]["capturedAt"],
        "authorizedRunIds": list(bindings.run_ids),
        "runCount": RUN_COUNT,
        "attempt": ATTEMPT,
        "evidenceLabel": EVIDENCE_LABEL,
        "oneShot": True,
        "retryAllowed": False,
        "substitutionAllowed": False,
        "rerandomizationAllowed": False,
        "notBefore": not_before,
        "authorizationDeadline": authorization_deadline,
        "cleanupReserveSeconds": CLEANUP_RESERVE_SECONDS,
        "minimumRemainingAtFirstMutationSeconds": (
            MINIMUM_FIRST_MUTATION_REMAINING_SECONDS
        ),
    }


def expected_gate_run_text(authorization: Mapping[str, Any]) -> str:
    return (
        f"APPROVE GATE-RUN campaign={authorization['campaignId']} "
        f"target={authorization['target']} framework={authorization['frameworkCommit']} "
        f"transport-user={authorization['transportUser']} "
        f"execution-user={authorization['executionUser']} "
        f"release={authorization['releaseRoot']} "
        f"gate-setup={authorization['gateSetupSha256']} "
        f"descriptor={authorization['descriptorCanonicalSha256']} "
        f"plan={authorization['compiledPlanCanonicalSha256']} "
        f"gate-plan={authorization['gatePlanSha256']} "
        f"readiness={authorization['runtimeReadinessSha256']} "
        f"readiness-archive={authorization['readinessArchiveSha256']} "
        f"preflight={authorization['runtimePreflightCapturedAt']} runs={RUN_COUNT} "
        f"attempts=1 no-retry no-substitution no-rerandomization "
        f"deadline={authorization['authorizationDeadline']}"
    )


@dataclass(frozen=True)
class RuntimePackage:
    bindings: CampaignBindings
    gate_plan: dict[str, Any]
    gate_plan_sha256: str
    readiness: dict[str, Any]
    readiness_sha256: str
    gate_run: dict[str, Any]
    gate_run_sha256: str
    validated_at: datetime


def _validate_gate_run_non_temporal(
    document: Any,
    bindings: CampaignBindings,
    gate_plan: dict[str, Any],
    gate_plan_sha256: str,
    readiness_sha256: str,
    readiness: Mapping[str, Any],
) -> tuple[dict[str, Any], datetime, datetime, datetime, datetime, str]:
    """Replay the complete GATE-RUN identity without consulting a clock."""

    root = _exact(document, {
        "schemaVersion", "kind", "gate", "decision", "typedApproval",
        "approvedBy", "approvedAt", "authorization", "promotionAuthorized",
    }, "GATE-RUN")
    authorization = _exact(root["authorization"], {
        "campaignId", "studyEpoch", "target", "transportUser", "executionUser",
        "executionUid", "executionGid", "executionMethod", "releaseRoot",
        "resultsRoot", "exclusiveLeasePath", "setupId", "gateSetupSha256",
        "releaseManifestSha256", "bundleSha256", "releaseInstalledAt",
        "frameworkCommit", "descriptorCanonicalSha256",
        "compiledPlanCanonicalSha256", "gatePlanSha256", "runtimeReadinessSha256",
        "readinessArchiveSha256", "runtimePreflightCapturedAt",
        "authorizedRunIds", "runCount", "attempt", "evidenceLabel", "oneShot",
        "retryAllowed", "substitutionAllowed", "rerandomizationAllowed", "notBefore",
        "authorizationDeadline", "cleanupReserveSeconds",
        "minimumRemainingAtFirstMutationSeconds",
    }, "GATE-RUN.authorization")
    if not isinstance(authorization["campaignId"], str) or CAMPAIGN_RE.fullmatch(
        authorization["campaignId"]
    ) is None:
        raise GateError("GATE-RUN campaignId is unsafe")
    expected = run_authorization(
        bindings, gate_plan_sha256, readiness_sha256,
        readiness=readiness,
        campaign_id=authorization["campaignId"],
        not_before=authorization["notBefore"],
        authorization_deadline=authorization["authorizationDeadline"],
    )
    if (
        not _exact_int(root["schemaVersion"], 1)
        or root["kind"] != RUN_KIND
        or root["gate"] != "GATE-RUN"
        or root["decision"] != "authorize-one-shot-exact-run"
        or root["typedApproval"] != expected_gate_run_text(expected)
        or not isinstance(root["approvedBy"], str)
        or not root["approvedBy"].strip()
        or not _same_json_type(authorization, expected)
        or root["promotionAuthorized"] is not False
    ):
        raise GateError("GATE-RUN identity, typed approval, exact scope, or ceiling differs")
    approved = _timestamp(root["approvedAt"], "GATE-RUN.approvedAt")
    plan_approved = _timestamp(gate_plan["approvedAt"], "GATE-PLAN.approvedAt")
    release_installed = _timestamp(
        authorization["releaseInstalledAt"], "GATE-RUN.releaseInstalledAt"
    )
    preflight_captured = _timestamp(
        authorization["runtimePreflightCapturedAt"],
        "GATE-RUN.runtimePreflightCapturedAt",
    )
    not_before = _timestamp(authorization["notBefore"], "GATE-RUN.notBefore")
    deadline = _timestamp(
        authorization["authorizationDeadline"], "GATE-RUN.authorizationDeadline")
    if (
        plan_approved > approved
        or release_installed > preflight_captured
        or preflight_captured > approved
    ):
        raise GateError("GATE-RUN ordering differs from plan, release, or fresh preflight")
    return root, approved, preflight_captured, not_before, deadline, canonical_sha256(root)


def _validate_gate_run_temporal(
    *,
    approved: datetime,
    preflight_captured: datetime,
    not_before: datetime,
    deadline: datetime,
    now: datetime,
) -> None:
    """Apply only the wall-clock-dependent part of GATE-RUN replay."""

    if approved > now.replace(microsecond=0) and (
        approved - now
    ).total_seconds() > MAX_CLOCK_SKEW_SECONDS:
        raise GateError("GATE-RUN approval timestamp is in the future")
    age = math.floor((now - approved).total_seconds())
    if age < -MAX_CLOCK_SKEW_SECONDS or age > MAX_GATE_RUN_AGE_SECONDS:
        raise GateError("GATE-RUN is not a fresh approval")
    preflight_age = math.floor((now - preflight_captured).total_seconds())
    if preflight_age < -MAX_CLOCK_SKEW_SECONDS or preflight_age > MAX_GATE_RUN_AGE_SECONDS:
        raise GateError("installed runtime preflight is not fresh")
    if now < not_before:
        raise GateError("GATE-RUN authorization window has not opened")
    remaining = math.floor((deadline - now).total_seconds())
    if remaining < MINIMUM_FIRST_MUTATION_REMAINING_SECONDS:
        raise GateError(
            f"GATE-RUN does not leave {MINIMUM_FIRST_MUTATION_REMAINING_SECONDS:,} seconds "
            "before the authorization deadline"
        )


def validate_gate_run(
    document: Any,
    bindings: CampaignBindings,
    gate_plan: dict[str, Any],
    gate_plan_sha256: str,
    readiness_sha256: str,
    readiness: Mapping[str, Any],
    *,
    now: datetime,
) -> str:
    """Replay GATE-RUN identity and then its time window against ``now``."""

    _, approved, preflight, not_before, deadline, digest = _validate_gate_run_non_temporal(
        document, bindings, gate_plan, gate_plan_sha256, readiness_sha256,
        readiness,
    )
    _validate_gate_run_temporal(
        approved=approved,
        preflight_captured=preflight,
        not_before=not_before,
        deadline=deadline,
        now=now,
    )
    return digest


def authorize_from_files(
    campaign_root: Path,
    gate_plan_path: Path,
    readiness_path: Path,
    gate_run_path: Path,
    *,
    framework_commit: str,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> RuntimePackage:
    """Replay all local inputs immediately before a possible first mutation."""

    # Read all caller-controlled local documents before any clock side effect.
    # This also means a missing or malformed later receipt cannot consume a
    # one-shot/externally instrumented clock while an earlier receipt happens
    # to be structurally valid.
    gate_plan = _json_file(Path(gate_plan_path), "GATE-PLAN receipt")
    readiness_path = Path(readiness_path)
    readiness = _json_file(readiness_path, "runtime-readiness receipt")
    gate_run = _json_file(Path(gate_run_path), "GATE-RUN receipt")

    bindings = inspect_campaign(campaign_root, framework_commit)
    gate_plan_sha = validate_gate_plan(gate_plan, bindings)
    readiness_sha = validate_readiness(
        readiness, bindings, readiness_parent=readiness_path.parent)
    _, approved, preflight, not_before, deadline, gate_run_sha = (
        _validate_gate_run_non_temporal(
            gate_run, bindings, gate_plan, gate_plan_sha, readiness_sha,
            readiness,
        )
    )

    # The caller clock is the last local dependency consulted: every byte and
    # every non-temporal binding has already replayed successfully.
    observed = _now(clock)
    _validate_gate_run_temporal(
        approved=approved,
        preflight_captured=preflight,
        not_before=not_before,
        deadline=deadline,
        now=observed,
    )
    return RuntimePackage(
        bindings=bindings,
        gate_plan=copy.deepcopy(gate_plan),
        gate_plan_sha256=gate_plan_sha,
        readiness=copy.deepcopy(readiness),
        readiness_sha256=readiness_sha,
        gate_run=copy.deepcopy(gate_run),
        gate_run_sha256=gate_run_sha,
        validated_at=observed,
    )


def build_cell_contract(package: RuntimePackage, cell: Mapping[str, Any]) -> dict[str, Any]:
    """Construct one exact cell contract; this function performs no runtime I/O."""

    expected = next(
        (item for item in package.bindings.cells if item["runId"] == cell.get("runId")),
        None,
    )
    if expected is None or not _same_json_type(cell, expected):
        raise GateError("cell differs from the immutable compiled schedule")
    key = expected["runKey"]
    regime = key["regime"]
    posture = key["posture"]
    fault = expected["fault"]
    cost = regime == "no-fault-cost"
    if cost != (fault is None):
        raise GateError("compiled cost/effect boundary differs")
    required_artifacts = list(COMMON_ARTIFACTS)
    if cost:
        required_artifacts.append("resources.json")
    else:
        required_artifacts.append("intervention.json")
    descriptor = package.bindings.descriptor
    timing = _frozen_timing(descriptor)
    cell_timing = None
    if EPOCH["sweep"]:
        # Traffic sweep: per-cell values come from the compiled cell (already replayed against the plan).
        cell_timing = expected.get("timing")
        if not isinstance(cell_timing, dict) or cell_timing.get("fault") != fault:
            raise GateError("compiled sweep cell has no timing for its fault")
        timing = {
            "warmupSeconds": cell_timing["warmupSeconds"],
            "measurementSeconds": cell_timing["measurementSeconds"],
            "faultOnsetSeconds": cell_timing["faultOnsetSeconds"],
            "interventionHoldSeconds": cell_timing["faultHoldSeconds"],
        }
    workload = {
        "id": descriptor["workload"]["id"],
        "kind": descriptor["workload"]["kind"],
        "population": descriptor["workload"]["population"],
        "journeysPerSecond": (
            descriptor["workload"]["journeysPerSecond"] if cell_timing is None
            else cell_timing["journeysPerSecond"]),
        "concurrency": descriptor["workload"]["concurrency"],
        "offeredJourneys": (
            descriptor["timing"]["offeredJourneysPerRun"] if cell_timing is None
            else cell_timing["offered"]),
        "excludedActions": copy.deepcopy(descriptor["workload"]["excludedActions"]),
        "ledgerContract": copy.deepcopy(descriptor["workload"]["journeyLedger"]),
    }
    window = {
        "analysisKind": "cost" if cost else "effect",
        "artifactRootClass": "cost" if cost else f"effect/{fault}",
        "warmupSeconds": timing["warmupSeconds"],
        "measurementSeconds": timing["measurementSeconds"],
        "sharedBarrierRequired": True,
        "sharedBarrierParticipants": copy.deepcopy(
            descriptor["timing"]["sharedBarrierParticipants"]
        ),
        "resourceProjectionAllowed": cost,
        "resourcesClaimUse": "cost-proxy" if cost else "diagnostic-only",
        "poolWithOtherRegime": False,
    }
    if cell_timing is not None:
        window["timing"] = copy.deepcopy(cell_timing)
    return {
        "schemaVersion": 1,
        "contract": CELL_CONTRACT,
        "campaignId": package.gate_run["authorization"]["campaignId"],
        "campaignSha256": package.bindings.campaign_sha256,
        "gatePlanSha256": package.gate_plan_sha256,
        "runtimeReadinessSha256": package.readiness_sha256,
        "gateRunSha256": package.gate_run_sha256,
        "frameworkCommit": package.bindings.framework_commit,
        "descriptorCanonicalSha256": package.bindings.descriptor_sha256,
        "compiledPlanCanonicalSha256": package.bindings.plan_sha256,
        "runId": expected["runId"],
        "runKey": copy.deepcopy(key),
        "ordinalPosition": expected["ordinalPosition"],
        "compiledArtifactRoot": expected["artifactRoot"],
        "coldStart": True,
        "target": {
            "host": TARGET,
            "transportUser": package.gate_run["authorization"]["transportUser"],
            "executionUser": package.gate_run["authorization"]["executionUser"],
            "executionUid": package.gate_run["authorization"]["executionUid"],
            "executionGid": package.gate_run["authorization"]["executionGid"],
            "executionMethod": package.gate_run["authorization"]["executionMethod"],
            "releaseRoot": package.gate_run["authorization"]["releaseRoot"],
            "resultsRoot": package.gate_run["authorization"]["resultsRoot"],
            "exclusiveLeasePath": LEASE_PATH,
            "outerLeaseScope": OUTER_LEASE_SCOPE,
        },
        "runtimeInputs": {
            "imageDigests": copy.deepcopy(package.readiness["imageDigests"]),
            "transportImplementationSha256": package.readiness["transport"][
                "implementationSha256"
            ],
            "controllerDigests": copy.deepcopy(package.bindings.controller_sha256),
            "gateSetupSha256": package.readiness["release"]["gateSetupSha256"],
            "releaseManifestSha256": package.readiness["release"][
                "releaseManifestSha256"
            ],
            "bundleSha256": package.readiness["release"]["bundleSha256"],
            "releaseBindingSha256": canonical_sha256(package.readiness["release"]),
            "readinessArchiveSha256": package.readiness.get(
                "ingressArchiveSha256", package.readiness.get("readinessArchiveSha256")
            ),
        },
        "workload": workload,
        "posture": {
            "id": posture,
            "selectionId": "fault-qualification" if posture == "selected" else None,
            "proofRequirements": copy.deepcopy(
                descriptor["postureProof"][posture]["requires"]),
        },
        "window": window,
        "faultGroundTruth": {
            "required": not cost,
            "scenario": fault,
            "artifact": "intervention.json" if not cost else None,
            "independentOfKieker": True,
            "faultOnsetSeconds": timing["faultOnsetSeconds"] if not cost else None,
            "holdSeconds": timing["interventionHoldSeconds"] if not cost else None,
            "commandSuccessAloneEstablishesTruth": False,
            "failedManifestationOrRecoveryStopsCampaign": True,
        },
        "pathGroundTruth": {
            "expectedOpportunitySource": "journey-ledger.plan.json",
            "executedDenominatorSource": "app-witness.jsonl",
            "applicationSourceArtifacts": ["auth.log", "persistence.log"],
            "nativeTraceSource": "traces.json",
            "nativeEventsCarryWorkloadTokens": False,
            "nativeBridgeSource": "auth.log",
            "nativeBridgeService": "auth",
            "nativeTokenCorrelationArtifact": "native-token-correlation.json",
            "nativeTokenExtractionArtifact": "native-token-correlation-extraction.json",
            "serviceLogCaptureArtifact": "service-log-capture.json",
            "serviceLogCaptureScope": "measurement-window",
            "parameterLoggingRequirement": "LOG_PARAMETERS-absent-or-false",
            "nativeTokenMapping": (
                "one-token-to-one-journey-and-at-most-one-original-native-trace"
            ),
            "terminalCaptureSource": "capture-terminal.json",
            "validationReport": "candidate-validation.json",
            "correlation": descriptor["groundTruth"]["path"]["correlation"],
            "requiredEdge": descriptor["groundTruth"]["path"]["requiredEdge"],
            "scoredPhases": copy.deepcopy(
                descriptor["groundTruth"]["path"]["scoredPhases"]
            ),
            "crossTraceAssemblyAllowed": False,
            "missingState": "unsupported",
            "missingValue": None,
        },
        "attemptPolicy": {
            "attempt": ATTEMPT,
            "startedBeforeFirstExternalMutation": True,
            "retryAllowed": False,
            "substitutionAllowed": False,
            "rerandomizationAllowed": False,
        },
        "requiredArtifacts": sorted(required_artifacts),
        "terminalPolicy": {
            "candidateCellValidationRequired": True,
            "ownedResourcesCleanRequired": True,
            "outerLeaseHeldRequired": True,
            "deadlineControllerSettledRequired": True,
            "promotionAuthorized": False,
        },
    }


class CellTransport(Protocol):
    """Per-cell transport boundary used by the adapter replay contract."""

    def describe(self) -> Mapping[str, Any]: ...

    def execute(self, contract: Mapping[str, Any], artifact_root: Path) -> "TransportOutcome": ...


@dataclass(frozen=True)
class TransportOutcome:
    run_id: str
    run_key: dict[str, Any]
    state: str
    safe_to_continue: bool
    evidence_sha256: str | None
    candidate_validation_sha256: str
    fault_ground_truth_sha256: str | None
    path_ground_truth_sha256: str
    native_token_correlation_sha256: str
    native_token_extraction_sha256: str
    service_log_capture_sha256: str
    posture_proof_sha256: str
    queue_proof_sha256: str
    resource_evidence_sha256: str | None
    system_samples_sha256: str
    cleanup_proof_sha256: str
    outer_lease_held: bool
    deadline_controller_settled: bool
    owned_resources_clean: bool
    reason: str | None = None


ResultFactory = Callable[[str, bool, Optional[str], Optional[str]], Any]


def _artifact_sha(root: Path, name: str) -> str:
    return hashlib.sha256(_file_bytes(root / name, name)).hexdigest()


@dataclass(frozen=True)
class ContentManifestSnapshot:
    """Hashes and sizes recomputed from one stable read of every sealed file."""

    manifest_sha256: str
    artifact_sha256: dict[str, str]
    artifact_bytes: dict[str, int]


def _validate_content_manifest(
    root: Path,
    required_artifacts: Any,
) -> ContentManifestSnapshot:
    """Replay a closed, flat candidate-cell content manifest.

    The manifest cannot list itself.  Every other required artifact must be a
    regular, non-symlink file at the evidence root, and no undeclared entry may
    coexist with the seal.  Hashes and sizes are recomputed from bytes that are
    checked for identity/size/mtime stability while read.
    """

    root = Path(root)
    try:
        root_metadata = root.lstat()
    except OSError as exc:
        raise GateError(f"cannot inspect candidate artifact root: {exc}") from exc
    if root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
        raise GateError("candidate artifact root must be a real directory")
    if not isinstance(required_artifacts, list) or any(
        not isinstance(name, str) for name in required_artifacts
    ):
        raise GateError("cell requiredArtifacts must be a list of file names")
    if required_artifacts != sorted(required_artifacts) or len(required_artifacts) != len(
        set(required_artifacts)
    ):
        raise GateError("cell requiredArtifacts must be unique and sorted")
    required = set(required_artifacts)
    if "content-manifest.json" not in required:
        raise GateError("cell requiredArtifacts omits content-manifest.json")
    for name in required:
        path = _safe_relative_path(name, "cell required artifact")
        if len(path.parts) != 1:
            raise GateError("candidate cell artifacts must be flat files")

    observed: dict[str, Path] = {}
    try:
        for path in root.iterdir():
            metadata = path.lstat()
            name = path.name
            if (
                path.is_symlink()
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
            ):
                raise GateError(
                    f"candidate artifact {name} is not a singly-linked regular file"
                )
            observed[name] = path
    except GateError:
        raise
    except OSError as exc:
        raise GateError(f"cannot enumerate candidate artifacts: {exc}") from exc
    if set(observed) != required:
        raise GateError(
            "candidate artifact membership differs: "
            f"missing={sorted(required - set(observed))}, "
            f"extra={sorted(set(observed) - required)}"
        )

    manifest_bytes = _file_bytes(
        observed["content-manifest.json"], "content-manifest.json"
    )
    if observed["content-manifest.json"].lstat().st_nlink != 1:
        raise GateError("content-manifest.json acquired a hard-link alias")
    manifest = _strict_json(manifest_bytes, "content-manifest.json")
    manifest = _exact(
        manifest, {"schemaVersion", "algorithm", "files"}, "content manifest"
    )
    if (
        type(manifest["schemaVersion"]) is not int
        or manifest["schemaVersion"] != 1
        or manifest["algorithm"] != "sha256"
    ):
        raise GateError("content manifest schema or algorithm differs")
    rows = manifest["files"]
    if not isinstance(rows, list):
        raise GateError("content manifest files must be a list")
    declared: dict[str, dict[str, Any]] = {}
    ordered_paths: list[str] = []
    for index, value in enumerate(rows):
        row = _exact(
            value, {"path", "bytes", "sha256"}, f"content manifest row {index}"
        )
        path = _safe_relative_path(row["path"], f"content manifest row {index}.path")
        name = path.as_posix()
        if len(path.parts) != 1 or name == "content-manifest.json":
            raise GateError(f"content manifest row {index} names a non-sealable path")
        if name in declared:
            raise GateError(f"content manifest repeats path: {name}")
        if (
            type(row["bytes"]) is not int
            or row["bytes"] < 0
            or not isinstance(row["sha256"], str)
            or SHA256_RE.fullmatch(row["sha256"]) is None
        ):
            raise GateError(f"content manifest row {index} size or digest is invalid")
        declared[name] = row
        ordered_paths.append(name)
    expected_sealed = required - {"content-manifest.json"}
    if set(declared) != expected_sealed:
        raise GateError(
            "content manifest membership differs: "
            f"missing={sorted(expected_sealed - set(declared))}, "
            f"extra={sorted(set(declared) - expected_sealed)}"
        )
    if ordered_paths != sorted(ordered_paths):
        raise GateError("content manifest rows must be sorted by path")

    artifact_sha256: dict[str, str] = {}
    artifact_bytes: dict[str, int] = {}
    for name in sorted(expected_sealed):
        payload = _file_bytes(observed[name], name)
        if observed[name].lstat().st_nlink != 1:
            raise GateError(f"candidate artifact {name} acquired a hard-link alias")
        digest = hashlib.sha256(payload).hexdigest()
        if declared[name]["bytes"] != len(payload) or declared[name]["sha256"] != digest:
            raise GateError(f"content manifest digest or size differs for {name}")
        artifact_sha256[name] = digest
        artifact_bytes[name] = len(payload)
    return ContentManifestSnapshot(
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        artifact_sha256=artifact_sha256,
        artifact_bytes=artifact_bytes,
    )


class CandidateCellAdapter:
    """Execute immutable cells in order through one already admitted transport."""

    def __init__(
        self,
        package: RuntimePackage,
        transport: CellTransport,
        result_factory: ResultFactory,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        # Keep the validated authorization graph isolated from caller mutation.
        self._package = copy.deepcopy(package)
        self._transport = transport
        self._result_factory = result_factory
        self._clock = clock
        self._next_index = 0
        self._stopped = False

    def __call__(self, cell: dict[str, Any], artifact_root: Path) -> Any:
        if self._stopped:
            raise GateError("candidate adapter is permanently stopped after an attempt")
        if self._next_index >= len(self._package.bindings.cells):
            raise GateError("candidate adapter has no remaining scheduled cell")
        expected = self._package.bindings.cells[self._next_index]
        if not _same_json_type(cell, expected):
            raise GateError("candidate cell is missing, reordered, relabelled, or substituted")
        observed_now = _now(self._clock)
        gate = self._package.gate_run
        _, approved, preflight, not_before, deadline, digest = (
            _validate_gate_run_non_temporal(
            gate,
            self._package.bindings,
            self._package.gate_plan,
            self._package.gate_plan_sha256,
            self._package.readiness_sha256,
            self._package.readiness,
            )
        )
        if digest != self._package.gate_run_sha256:
            raise GateError("retained GATE-RUN digest changed")
        if self._next_index == 0:
            _validate_gate_run_temporal(
                approved=approved, preflight_captured=preflight,
                not_before=not_before, deadline=deadline,
                now=observed_now,
            )
        elif observed_now < not_before or math.floor(
            (deadline - observed_now).total_seconds()
        ) <= CLEANUP_RESERVE_SECONDS:
            raise GateError("candidate authorization entered its cleanup reserve")
        contract = build_cell_contract(self._package, expected)
        campaign_row = next(
            row for row in self._package.bindings.campaign["runs"]
            if row["runId"] == expected["runId"]
        )
        expected_root = self._package.bindings.root / campaign_row["path"]
        artifact_root = Path(artifact_root)
        if artifact_root.resolve(strict=False) != expected_root.resolve(strict=False):
            raise GateError("candidate artifact root differs from the compiled campaign path")
        if artifact_root.exists() or artifact_root.is_symlink():
            raise GateError("candidate artifact root exists before first attempt")
        description = self._transport.describe()
        capability = self._package.readiness["transport"]
        expected_description = {
            key: capability[key] for key in (
                "schemaVersion", "contract", "target", "evidenceLabel",
                "outerLeasePath", "outerLeaseScope", "deadlineEnforced",
                "cleanupEnforced", "candidateDescriptorAccepted", "transportUser",
                "executionUser", "executionMethod", "releaseRoot", "resultsRoot",
            )
        }
        if not _same_json_type(description, expected_description):
            raise GateError("injected transport capability differs from readiness")
        # The attempt is consumed before the transport boundary can mutate.
        self._next_index += 1
        self._stopped = True
        try:
            outcome = self._transport.execute(contract, artifact_root)
            if not isinstance(outcome, TransportOutcome):
                raise GateError("transport did not return a typed outcome")
            self._validate_outcome(contract, artifact_root, outcome)
        except Exception:
            # No retry or substitution exists in this epoch.
            raise
        if outcome.safe_to_continue:
            self._stopped = False
        return self._result_factory(
            outcome.run_id,
            outcome.safe_to_continue,
            outcome.evidence_sha256,
            outcome.reason,
        )

    @staticmethod
    def _validate_outcome(
        contract: Mapping[str, Any], root: Path, outcome: TransportOutcome,
    ) -> None:
        if (
            outcome.run_id != contract["runId"]
            or not _same_json_type(outcome.run_key, contract["runKey"])
            or outcome.state not in {
                "valid", "invalid", "aborted", "missing-artifact", "unsupported",
            }
            or type(outcome.safe_to_continue) is not bool
            or type(outcome.outer_lease_held) is not bool
            or type(outcome.deadline_controller_settled) is not bool
            or type(outcome.owned_resources_clean) is not bool
            or (outcome.reason is not None and (
                not isinstance(outcome.reason, str) or not outcome.reason.strip()
            ))
        ):
            raise GateError("transport outcome identity, state, or types differ")
        if outcome.state != "valid" and outcome.evidence_sha256 is not None:
            raise GateError("a non-valid cell cannot expose a candidate-evidence seal")
        manifest_snapshot = None
        if outcome.state == "valid":
            manifest_snapshot = _validate_content_manifest(
                root, contract.get("requiredArtifacts")
            )
            if outcome.evidence_sha256 != manifest_snapshot.manifest_sha256:
                raise GateError("candidate-evidence seal differs from the content manifest")
        digest_fields = {
            "candidate-validation.json": outcome.candidate_validation_sha256,
            "native-token-correlation.json": outcome.native_token_correlation_sha256,
            "native-token-correlation-extraction.json": (
                outcome.native_token_extraction_sha256
            ),
            "service-log-capture.json": outcome.service_log_capture_sha256,
            "posture-proof.json": outcome.posture_proof_sha256,
            "queue-proof.json": outcome.queue_proof_sha256,
            "system-samples.json": outcome.system_samples_sha256,
            "cell-cleanup.json": outcome.cleanup_proof_sha256,
        }
        if outcome.evidence_sha256 is not None:
            digest_fields["content-manifest.json"] = outcome.evidence_sha256
        cost = contract["window"]["analysisKind"] == "cost"
        if cost:
            if outcome.fault_ground_truth_sha256 is not None:
                raise GateError("cost cell returned a fault-ground-truth digest")
            if outcome.resource_evidence_sha256 is None:
                raise GateError("cost cell omitted resource evidence")
            digest_fields["resources.json"] = outcome.resource_evidence_sha256
        else:
            if outcome.fault_ground_truth_sha256 is None:
                raise GateError("effect cell omitted fault ground truth")
            if outcome.resource_evidence_sha256 is not None:
                raise GateError("effect cell exposed a resource cost projection")
            digest_fields["intervention.json"] = outcome.fault_ground_truth_sha256
        if outcome.path_ground_truth_sha256 != outcome.candidate_validation_sha256:
            raise GateError("path-ground-truth digest differs from candidate validation")
        for name, expected in digest_fields.items():
            if not isinstance(expected, str) or SHA256_RE.fullmatch(expected) is None:
                raise GateError(f"transport outcome digest for {name} is invalid")
            observed_digest = (
                manifest_snapshot.artifact_sha256.get(name)
                if manifest_snapshot is not None and name != "content-manifest.json"
                else _artifact_sha(root, name)
            )
            if observed_digest != expected:
                raise GateError(f"transport outcome digest for {name} does not reconcile")
        report = _json_file(root / "candidate-validation.json", "candidate validation")
        try:
            replayed = _candidate_validator_module().validate_run(
                root, expected=copy.deepcopy(contract["runKey"]))
        except Exception as exc:  # noqa: BLE001 - evidence replay must fail closed
            raise GateError(
                f"candidate validation could not be replayed: {type(exc).__name__}"
            ) from exc
        if not _same_json_type(report, replayed):
            raise GateError("retained candidate validation differs from independent replay")
        expected_state = "valid" if replayed.get("verdict") == "pass" else replayed.get(
            "cellStatus"
        )
        if outcome.state != expected_state:
            raise GateError("candidate validation state differs from transport outcome")
        if outcome.state == "valid":
            terminal_module = _candidate_terminal_validator_module(contract)
            if terminal_module is None:
                raise GateError("candidate terminal validator is absent")
            try:
                terminal = terminal_module.validate_candidate_cell(
                    root,
                    expected_run_key=copy.deepcopy(contract["runKey"]),
                    expected_manifest_sha256=manifest_snapshot.manifest_sha256,
                )
            except Exception as exc:  # noqa: BLE001 - terminal replay fails closed
                raise GateError(
                    f"candidate terminal replay failed: {type(exc).__name__}"
                ) from exc
            terminal = _exact(
                terminal,
                {
                    "schemaVersion", "kind", "verdict", "runKey",
                    "manifestSha256", "blockers",
                },
                "candidate terminal replay",
            )
            if (
                not _exact_int(terminal["schemaVersion"], 1)
                or terminal["kind"] != CANDIDATE_TERMINAL_KIND
                or terminal["verdict"] != "pass"
                or not _same_json_type(terminal["runKey"], contract["runKey"])
                or terminal["manifestSha256"] != manifest_snapshot.manifest_sha256
                or terminal["blockers"] != []
            ):
                raise GateError("candidate terminal replay did not pass exactly")
            replayed_manifest = _validate_content_manifest(
                root, contract.get("requiredArtifacts")
            )
            if replayed_manifest != manifest_snapshot:
                raise GateError("candidate artifacts changed across terminal replay")
        operationally_clean = (
            outcome.outer_lease_held
            and outcome.deadline_controller_settled
            and outcome.owned_resources_clean
        )
        if outcome.safe_to_continue and not operationally_clean:
            raise GateError("transport declared safe continuation without operational cleanup")
        if outcome.state == "valid" and (
            not outcome.safe_to_continue or outcome.evidence_sha256 is None
            or not operationally_clean
        ):
            raise GateError("valid cell lacks evidence or safe terminal cleanup")
        if not cost and outcome.state != "valid" and outcome.safe_to_continue:
            raise GateError("failed effect ground truth cannot permit later cell mutation")


__all__ = [
    "CandidateCellAdapter", "CampaignBindings", "GateError", "RuntimePackage",
    "TransportOutcome", "authorize_from_files", "build_cell_contract",
    "candidate_release_root", "candidate_results_root", "canonical_sha256",
    "controller_digests", "expected_gate_plan_text", "expected_gate_run_text",
    "expected_gate_setup_text", "inspect_campaign", "plan_binding",
    "run_authorization", "setup_authorization", "validate_gate_plan",
    "validate_gate_run", "validate_gate_setup", "validate_image_build_receipt",
    "validate_readiness",
    "validate_release_manifest", "validate_target_proof",
]
