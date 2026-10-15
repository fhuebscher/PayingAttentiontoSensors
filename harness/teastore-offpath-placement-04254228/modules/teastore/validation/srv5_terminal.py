#!/usr/bin/env python3
"""Fail-closed terminal validation for TeaStore campaigns fetched from srv5.

The validator is deliberately local: callers supply the last independently
captured remote state, and this module only reads the fetched evidence tree.
No value such as ``projectClean`` is trusted without replaying the retained
read-only command transcript that supports it.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import random
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping


MANIFEST_NAME = "content-manifest.json"
TERMINAL_REPORT_NAME = "terminal-validation.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
CONTAINER_ID_RE = re.compile(r"^[0-9a-f]{64}$")
IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
POSTURES = frozenset({"none", "selected", "full"})
RUNTIME_SERVICES = ("webui", "auth", "persistence", "image", "recommender", "registry", "db", "rabbitmq")
EXPECTED_RUNTIME_IMAGES = {
    "webui": "descartesresearch/teastore-webui",
    "auth": "descartesresearch/teastore-auth",
    "persistence": "descartesresearch/teastore-persistence",
    "image": "descartesresearch/teastore-image",
    "recommender": "descartesresearch/teastore-recommender",
    "registry": "descartesresearch/teastore-registry",
    "db": "descartesresearch/teastore-db",
    "rabbitmq": "rabbitmq:3-management",
}
EXPECTED_RUNTIME_REPOSITORIES = {
    **{service: image for service, image in EXPECTED_RUNTIME_IMAGES.items()
       if service != "rabbitmq"},
    "rabbitmq": "rabbitmq",
}
APP_SERVICES = ("webui", "auth", "persistence", "image", "recommender")
CONTAINER_IMAGE_INSPECT_FORMAT = (
    '{{.Id}}\t{{.Image}}\t{{.Config.Image}}\t'
    '{{index .Config.Labels "com.docker.compose.project"}}\t'
    '{{index .Config.Labels "com.docker.compose.service"}}'
)
IMAGE_INSPECT_FORMAT = '{{.Id}}\t{{json .RepoDigests}}'
MAX_REMOTE_AGE_SECONDS = 300
REMOTE_RUNS = "/home/stig/observability-placement-runs"
REMOTE_RESULTS = "/home/stig/observability-placement-results"
HOST_LEASE_PATH = f"{REMOTE_RUNS}/.teastore-performance.lock"
RESOURCE_CLASSES = (
    "owned-current", "owned-legacy", "shared-approved", "foreign", "unknown",
)
REQUIRED_PORTS = (3306, 5672, 8080, 8082, 15672)
DEADLINE_CLEANUP_RESERVE_SECONDS = 300
DEADLINE_LEASE_FINALIZER_SECONDS = 30
COLLECTOR_BARRIER_EARLY_TOLERANCE_SECONDS = 1.0
COLLECTOR_BARRIER_COMPLETION_DEADLINE_SECONDS = 5.0
# ``docker compose stop`` has a ten-second graceful-stop interval before Docker
# kills the persistence container.  The retained timestamp is the first
# post-command state observation, not an independently retained command-issuance
# timestamp, so that scenario admits an observation up to 15 seconds after the
# scheduled onset.  The auth pause path does not have that grace period.
INTERVENTION_ONSET_LATE_TOLERANCE_SECONDS = 5.0
PERSISTENCE_MANIFESTATION_LAG_BOUND_SECONDS = 15.0
INTERVENTION_CLOCK_TOLERANCE_SECONDS = 1.0
DEADLINE_VALIDATION_GATES = {
    "deadline-enforced-owned-cleanup", "runtime-admission-replay",
}
DEADLINE_COMPOSE_FILES = (
    "modules/teastore/deployment/compose/docker-compose_kieker.yaml",
    "modules/teastore/deployment/compose/docker-compose_rabbitmq.yaml",
    "modules/teastore/deployment/compose/isolation.override.yaml",
)


class DuplicateKeyError(ValueError):
    """Raised when JSON text attempts to conceal a duplicate member."""


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _read_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_no_duplicate_keys,
        parse_constant=_invalid_json_constant,
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    before = path.stat()
    payload = path.read_bytes()
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise RuntimeError(f"file changed while hashing: {path}")
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(payload),
        "sha256": _sha256_bytes(payload),
    }


def _evidence_files(root: Path, manifest_path: Path) -> list[Path]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"evidence root is not a directory: {root}")
    manifest_path = manifest_path.resolve()
    if manifest_path.parent != root:
        raise ValueError("content manifest must be at the evidence root")
    files: list[Path] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise ValueError(f"evidence contains a symbolic link: {path.relative_to(root)}")
        if path == manifest_path or path == root / TERMINAL_REPORT_NAME:
            continue
        if path.is_file():
            files.append(path)
        elif not path.is_dir():
            raise ValueError(f"evidence contains a non-regular entry: {path.relative_to(root)}")
    return files


def write_manifest(root: Path, manifest: Path | None = None) -> dict[str, Any]:
    """Create a one-time seal over evidence except its derived verdict.

    Both exclusions are necessarily circular: the manifest cannot hash itself,
    and the terminal verdict reports verification of that manifest. Every raw
    or independently captured evidence file remains sealed.  The seal is
    published atomically and may never replace an existing manifest: validation
    after mutation must fail rather than bless a new history.
    """

    root = Path(root).resolve()
    manifest_path = (manifest or (root / MANIFEST_NAME)).resolve()
    if manifest_path.parent != root:
        raise ValueError("content manifest must be at the evidence root")
    if manifest_path.exists() or manifest_path.is_symlink():
        raise FileExistsError(f"content manifest already exists: {manifest_path}")
    document = {
        "schemaVersion": 1,
        "algorithm": "sha256",
        "files": [_file_record(path, root) for path in _evidence_files(root, manifest_path)],
    }
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{manifest_path.name}.", suffix=".tmp", dir=root,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # A hard-link publication is atomic and, unlike replace(), fails if a
        # concurrent caller or an earlier validation already created the seal.
        os.link(temporary, manifest_path)
        directory = os.open(root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    return document


def verify_manifest(root: Path, manifest: Path | None = None) -> dict[str, Any]:
    """Verify manifest structure, membership, sizes, and SHA-256 digests."""

    blockers: list[str] = []
    root = Path(root).resolve()
    manifest_path = (manifest or (root / MANIFEST_NAME)).resolve()
    manifest_sha256 = None
    manifest_bytes = None
    try:
        if manifest_path.parent != root:
            raise ValueError("content manifest must be at the evidence root")
        if manifest_path.is_symlink():
            raise ValueError("content manifest is a symbolic link")
        before = manifest_path.stat()
        payload = manifest_path.read_bytes()
        after = manifest_path.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise RuntimeError("content manifest changed while being read")
        manifest_sha256 = _sha256_bytes(payload)
        manifest_bytes = len(payload)
        document = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_no_duplicate_keys,
            parse_constant=_invalid_json_constant,
        )
        if not isinstance(document, dict):
            raise ValueError("content manifest is not an object")
        if document.get("schemaVersion") != 1 or document.get("algorithm") != "sha256":
            blockers.append("content manifest schema/algorithm is invalid")
        rows = document.get("files")
        if not isinstance(rows, list):
            raise ValueError("content manifest files is not a list")
        declared: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}:
                blockers.append(f"content manifest row {index} has invalid fields")
                continue
            relative = row.get("path")
            if not isinstance(relative, str) or not relative or relative.startswith("/"):
                blockers.append(f"content manifest row {index} has an unsafe path")
                continue
            parts = Path(relative).parts
            if relative != Path(relative).as_posix() or any(part in {"", ".", ".."} for part in parts):
                blockers.append(f"content manifest row {index} has a non-normal path")
                continue
            if relative in {MANIFEST_NAME, TERMINAL_REPORT_NAME}:
                blockers.append(f"content manifest circularly lists derived file: {relative}")
                continue
            if relative in declared:
                blockers.append(f"content manifest repeats path: {relative}")
                continue
            if not isinstance(row.get("bytes"), int) or isinstance(row.get("bytes"), bool) or row["bytes"] < 0:
                blockers.append(f"content manifest has invalid size: {relative}")
            if not isinstance(row.get("sha256"), str) or not SHA256_RE.fullmatch(row["sha256"]):
                blockers.append(f"content manifest has invalid digest: {relative}")
            declared[relative] = row
        observed_paths = _evidence_files(root, manifest_path)
        observed = {path.relative_to(root).as_posix(): path for path in observed_paths}
        if set(declared) != set(observed):
            missing = sorted(set(declared) - set(observed))
            extra = sorted(set(observed) - set(declared))
            blockers.append(f"content manifest membership differs: missing={missing}, extra={extra}")
        for relative in sorted(set(declared) & set(observed)):
            actual = _file_record(observed[relative], root)
            expected = declared[relative]
            if actual["bytes"] != expected.get("bytes") or actual["sha256"] != expected.get("sha256"):
                blockers.append(f"content manifest digest/size mismatch: {relative}")
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, DuplicateKeyError) as exc:
        blockers.append(f"content manifest unreadable: {type(exc).__name__}: {exc}")
    return {
        "verdict": "pass" if not blockers else "blocked",
        "manifest": str(manifest_path),
        "manifestSha256": manifest_sha256,
        "manifestBytes": manifest_bytes,
        "blockers": blockers,
    }


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_validator(filename: str, module_name: str):
    return _load_module(Path(__file__).with_name(filename), module_name)


def _descriptor(descriptor: Path | Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    if isinstance(descriptor, Mapping):
        document = dict(descriptor)
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    else:
        path = Path(descriptor)
        payload = path.read_bytes()
        document = json.loads(
            payload,
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_invalid_json_constant,
        )
    if not isinstance(document, dict):
        raise ValueError("campaign descriptor is not an object")
    return document, _sha256_bytes(payload)


def _integer(value: Any, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _number(value: Any, *, positive: bool = False) -> bool:
    valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not valid:
        return False
    if not math.isfinite(value):
        return False
    return value > 0 if positive else True


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp is not timezone-aware")
    return parsed.astimezone(timezone.utc)


def _descriptor_configuration(document: dict[str, Any], digest: str) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    design = document.get("design")
    source = document.get("source")
    collector = document.get("collector")
    if document.get("schemaVersion") != 1:
        blockers.append("descriptor schemaVersion is not 1")
    descriptor_id = document.get("id")
    if not isinstance(descriptor_id, str) or not ID_RE.fullmatch(descriptor_id):
        blockers.append("descriptor id is invalid")
    evidence_label = document.get("evidenceLabel")
    if not isinstance(evidence_label, str) or not evidence_label:
        blockers.append("descriptor evidenceLabel is invalid")
    if document.get("module") != "teastore" or document.get("executor") != "ssh-compose":
        blockers.append("descriptor module/executor is not the TeaStore SSH contract")
    if not isinstance(document.get("target"), str) or not document.get("target"):
        blockers.append("descriptor target is invalid")
    if document.get("runner") != "modules/teastore/execution/performance_campaign.py":
        blockers.append("descriptor runner differs from the performance campaign")
    if not isinstance(source, dict) or source.get("frameworkCommit") != "required-at-materialization" or not (
        isinstance(source.get("sutReferenceCommit"), str)
        and COMMIT_RE.fullmatch(source["sutReferenceCommit"])
    ):
        blockers.append("descriptor source contract is invalid")
    if not isinstance(design, dict):
        blockers.append("descriptor design is not an object")
        return {}, blockers
    postures_raw = design.get("postures")
    posture_ids: list[str] = []
    if not isinstance(postures_raw, list) or not postures_raw:
        blockers.append("descriptor postures are missing")
    else:
        for row in postures_raw:
            if not isinstance(row, dict) or row.get("id") not in POSTURES or not isinstance(
                row.get("contract"), str
            ) or not row.get("contract"):
                blockers.append("descriptor posture contract is invalid")
                continue
            posture_ids.append(row["id"])
        if len(posture_ids) != len(set(posture_ids)):
            blockers.append("descriptor posture ids are duplicated")
    workload = design.get("workload")
    fault = design.get("fault")
    if not _integer(design.get("blocks"), minimum=1) or not _integer(design.get("seed"), minimum=0):
        blockers.append("descriptor blocks/seed is invalid")
    if not _integer(design.get("warmupSeconds"), minimum=0) or not _integer(
        design.get("measurementSeconds"), minimum=1
    ):
        blockers.append("descriptor warmup/measurement duration is invalid")
    if design.get("coldStartEachRun") is not True:
        blockers.append("descriptor does not require a cold start for every run")
    if not isinstance(workload, dict) or workload.get("path") != "modules/teastore/workload/fixed_load.py" or (
        workload.get("kind") != "fixed-open-loop"
    ) or not _number(workload.get("journeysPerSecond"), positive=True) or not _integer(
        workload.get("concurrency"), minimum=1
    ):
        blockers.append("descriptor workload contract is invalid")
    scenario = fault.get("scenario") if isinstance(fault, dict) else None
    if scenario not in {"none", "auth-freeze", "persistence-crash"}:
        blockers.append("descriptor fault scenario is invalid")
    elif scenario != "none":
        fault_at = fault.get("faultAtSeconds")
        outage = fault.get("outageSeconds")
        duration = design.get("measurementSeconds")
        if not _integer(fault_at, minimum=0) or not _integer(outage, minimum=1) or not _integer(
            duration, minimum=1
        ) or fault_at + outage >= duration:
            blockers.append("descriptor fault timing does not fit inside measurement")
    if not isinstance(collector, dict) or collector.get("path") != "modules/teastore/collectors/kieker_native.py" or (
        collector.get("queue") != "kieker" or collector.get("requiredConsumers") != 1
    ) or not _integer(collector.get("durationSeconds"), minimum=1) or not _integer(
        collector.get("inactivityTimeoutSeconds"), minimum=1
    ):
        blockers.append("descriptor collector contract is invalid")
    elif _integer(design.get("measurementSeconds"), minimum=1):
        if collector["durationSeconds"] != design["measurementSeconds"] + 30:
            blockers.append("descriptor collector duration differs from runner measurement+30")
    if not isinstance(design.get("selectionId"), str) or not design.get("selectionId"):
        blockers.append("descriptor selectionId is invalid")
    promotion = document.get("promotion")
    if not isinstance(promotion, dict) or promotion.get("canonical") is not False:
        blockers.append("diagnostic descriptor must prohibit canonical promotion")
    validation = document.get("validation")
    required_validation = {
        "immutable-descriptor-binding", "performance-receipt", "native-kieker-contract",
        "queue-purge-recorded", "exclusive-consumer", "complete-shutdown", "content-manifest",
        "runtime-image-provenance", "queue-proof-replay", "child-process-termination",
        "sanitized-host-inventory", "retained-60s-preflight",
        "host-wide-execution-lease", "external-manifest-anchor",
    }
    if not isinstance(validation, list) or not all(isinstance(item, str) for item in validation) or not (
        required_validation.issubset(set(validation))
    ):
        blockers.append("descriptor validation gates are incomplete")
    configuration = {
        "schemaVersion": 1,
        "descriptorId": descriptor_id,
        "descriptorSha256": digest,
        "evidenceLabel": evidence_label,
        "seed": design.get("seed"),
        "blocks": design.get("blocks"),
        "postures": posture_ids,
        "warmupSeconds": design.get("warmupSeconds"),
        "measurementSeconds": design.get("measurementSeconds"),
        "journeysPerSecond": workload.get("journeysPerSecond") if isinstance(workload, dict) else None,
        "concurrency": workload.get("concurrency") if isinstance(workload, dict) else None,
        "fault": scenario,
        "faultAtSeconds": fault.get("faultAtSeconds") if isinstance(fault, dict) and scenario != "none" else None,
        "outageSeconds": fault.get("outageSeconds") if isinstance(fault, dict) and scenario != "none" else None,
        "sutReferenceCommit": source.get("sutReferenceCommit") if isinstance(source, dict) else None,
        "selectionId": design.get("selectionId"),
        "collectorDurationSeconds": collector.get("durationSeconds") if isinstance(collector, dict) else None,
        "collectorInactivityTimeoutSeconds": collector.get("inactivityTimeoutSeconds") if isinstance(collector, dict) else None,
    }
    return configuration, blockers


def _resource_commands(project: str) -> dict[str, list[str]]:
    label = f"label=com.docker.compose.project={project}"
    return {
        "containers": ["docker", "ps", "-aq", "--filter", label],
        "networks": ["docker", "network", "ls", "-q", "--filter", label],
        "volumes": ["docker", "volume", "ls", "-q", "--filter", label],
    }


def _resource_blockers(proof: Any, project: str, where: str) -> list[str]:
    blockers: list[str] = []
    expected_commands = _resource_commands(project)
    expected_fields = {"project", "queries", "queryPassed", *expected_commands}
    if not isinstance(proof, dict):
        return [f"{where} is not an object"]
    if set(proof) != expected_fields:
        blockers.append(f"{where} fields differ from the authoritative resource proof")
    if proof.get("project") != project or proof.get("queryPassed") is not True:
        blockers.append(f"{where} project/queryPassed is invalid")
    queries = proof.get("queries")
    if not isinstance(queries, dict) or set(queries) != set(expected_commands):
        blockers.append(f"{where} query set is incomplete")
        return blockers
    for kind, command in expected_commands.items():
        query = queries.get(kind)
        if not isinstance(query, dict) or set(query) != {"command", "returnCode", "stdout", "stderr"}:
            blockers.append(f"{where} {kind} query fields are invalid")
            continue
        return_code = query.get("returnCode")
        if query.get("command") != command or not _integer(return_code) or return_code != 0 or not isinstance(
            query.get("stderr"), str
        ):
            blockers.append(f"{where} {kind} query did not authoritatively pass")
        stdout = query.get("stdout")
        rows = sorted(line for line in stdout.splitlines() if line) if isinstance(stdout, str) else None
        if rows is None or proof.get(kind) != rows:
            blockers.append(f"{where} {kind} list differs from query stdout")
        if rows:
            blockers.append(f"{where} retained owned {kind}: {rows}")
    return blockers


def _compose_prefix(project: str, posture: str) -> list[str]:
    command = [
        "docker", "compose", "-p", project,
        "-f", "modules/teastore/deployment/compose/docker-compose_kieker.yaml",
        "-f", "modules/teastore/deployment/compose/docker-compose_rabbitmq.yaml",
        "-f", "modules/teastore/deployment/compose/isolation.override.yaml",
    ]
    override = {
        "none": "modules/teastore/postures/none.override.yaml",
        "selected": "modules/teastore/deployment/compose/compiled-selected.override.yaml",
        "full": "modules/teastore/deployment/compose/compiled-full.override.yaml",
    }[posture]
    if override:
        command.extend(["-f", override])
    return command


def _compose_down(project: str, posture: str) -> list[str]:
    return [*_compose_prefix(project, posture), "down", "-v", "--remove-orphans"]


def _compose_service_action(
    project: str, posture: str, action: str, service: str,
) -> list[str]:
    """Return the exact shell-free intervention vector used by the runner."""
    return [*_compose_prefix(project, posture), action, service]


def _json_object(path: Path, blockers: list[str], where: str) -> dict[str, Any] | None:
    try:
        value = _read_json(path)
        if not isinstance(value, dict):
            raise ValueError("top level is not an object")
        return value
    except (OSError, ValueError, json.JSONDecodeError, DuplicateKeyError) as exc:
        blockers.append(f"{where} unreadable: {type(exc).__name__}: {exc}")
        return None


def _harness_owner_blockers(
    owner: Any,
    *,
    campaign: str,
    descriptor: Mapping[str, Any],
    descriptor_digest: str,
    configuration: Mapping[str, Any],
    expected_count: int,
    deadline_required: bool,
) -> list[str]:
    blockers: list[str] = []
    fields_v1 = {
        "schemaVersion", "campaign", "target", "session", "composeProject",
        "frameworkCommit", "sutReferenceCommit", "release", "resultRoot", "descriptorId",
        "descriptorSha256", "expectedReceipts",
    }
    fields_v2 = fields_v1 | {
        "runtimeAdmissionSha256", "authorizationDeadlineEpoch",
        "experimentStopEpoch", "cleanupReserveSeconds",
    }
    if not isinstance(owner, dict):
        return ["harness owner is not an object"]
    descriptor_source = descriptor.get("source")
    descriptor_sut = (
        descriptor_source.get("sutReferenceCommit")
        if isinstance(descriptor_source, Mapping)
        else None
    )
    expected_fields = fields_v2 if deadline_required else fields_v1
    expected_version = 2 if deadline_required else 1
    if set(owner) != expected_fields:
        blockers.append("harness owner fields differ from the exact protocol")
    framework_commit = owner.get("frameworkCommit")
    if owner.get("schemaVersion") != expected_version:
        blockers.append(f"harness owner schemaVersion is not {expected_version}")
    if owner.get("campaign") != campaign or owner.get("target") != descriptor.get("target"):
        blockers.append("harness owner campaign/target identity differs")
    compose_project = f"obst-{campaign}".lower()
    if owner.get("composeProject") != compose_project or owner.get("session") != f"teastore-{campaign}":
        blockers.append("harness owner Compose/session identity differs")
    if not isinstance(framework_commit, str) or not COMMIT_RE.fullmatch(framework_commit) or (
        framework_commit != configuration.get("frameworkCommit")
    ):
        blockers.append("harness owner framework commit differs from schedule")
    if owner.get("sutReferenceCommit") != configuration.get("sutReferenceCommit") or (
        owner.get("sutReferenceCommit") != descriptor_sut
    ):
        blockers.append("harness owner SUT reference commit differs")
    if owner.get("descriptorId") != descriptor.get("id") or owner.get("descriptorSha256") != descriptor_digest:
        blockers.append("harness owner descriptor identity/digest differs")
    if not _integer(owner.get("expectedReceipts"), minimum=1) or owner.get("expectedReceipts") != expected_count:
        blockers.append("harness owner expected receipt count differs")
    expected_release = (
        f"{REMOTE_RUNS}/{framework_commit[:12]}/{campaign}"
        if isinstance(framework_commit, str) and COMMIT_RE.fullmatch(framework_commit)
        else None
    )
    if owner.get("release") != expected_release:
        blockers.append("harness owner release path is not deterministic")
    if owner.get("resultRoot") != f"{REMOTE_RESULTS}/{campaign}":
        blockers.append("harness owner result root is not deterministic")
    if deadline_required:
        deadline = owner.get("authorizationDeadlineEpoch")
        stop = owner.get("experimentStopEpoch")
        reserve = owner.get("cleanupReserveSeconds")
        if not isinstance(owner.get("runtimeAdmissionSha256"), str) or not SHA256_RE.fullmatch(
            owner.get("runtimeAdmissionSha256", "")
        ):
            blockers.append("harness owner runtime admission digest is invalid")
        if (not _integer(deadline, minimum=1) or not _integer(stop, minimum=1)
                or reserve != DEADLINE_CLEANUP_RESERVE_SECONDS
                or deadline - stop != DEADLINE_CLEANUP_RESERVE_SECONDS):
            blockers.append("harness owner authorization deadline/stop boundary is invalid")
    return blockers


def _runtime_admission_blockers(
    root: Path,
    owner: Mapping[str, Any],
    descriptor: Mapping[str, Any],
    *,
    expected_count: int,
) -> list[str]:
    """Replay the retained admission without borrowing time after execution."""

    blockers: list[str] = []
    admission_path = root / "runtime-admission.json"
    source_path = root / "runtime-admission-source.json"
    admission = _json_object(admission_path, blockers, "runtime admission")
    source = _json_object(source_path, blockers, "runtime admission source")
    if admission is None or source is None:
        return blockers
    try:
        admission_digest = _sha256_bytes(admission_path.read_bytes())
    except OSError as exc:
        blockers.append(f"runtime admission bytes are unreadable: {exc}")
        return blockers
    if admission_digest != owner.get("runtimeAdmissionSha256"):
        blockers.append("runtime admission digest differs from harness owner")
    try:
        module = _load_module(
            Path(__file__).parents[1] / "execution" / "candidate_pilot.py",
            "teastore_candidate_pilot_terminal_admission",
        )
        module.validate_descriptor(source)
        expected = module.admit_runtime(
            source,
            mode=admission["mode"],
            evidence_label=admission["evidenceLabel"],
            now=admission["now"],
            authorization_deadline=admission["authorizationDeadline"],
            time_budget_seconds=admission["suppliedTimeBudgetSeconds"],
            diagnostic_run_count=admission["runCount"],
            diagnostic_warmup_seconds=admission["warmupSeconds"],
            diagnostic_measurement_seconds=admission["measurementSeconds"],
            lifecycle_allowance_seconds=admission["lifecycleAllowanceSeconds"],
        )
        if admission != expected:
            blockers.append("runtime admission differs from deterministic replay")
        if admission.get("descriptorSha256") != module.canonical_sha256(source):
            blockers.append("runtime admission source digest differs")
        source_binding = source.get("source") if isinstance(source.get("source"), Mapping) else {}
        diagnostic_source = (
            descriptor.get("source") if isinstance(descriptor.get("source"), Mapping) else {}
        )
        if source_binding.get("sutCommit") != diagnostic_source.get("sutReferenceCommit"):
            blockers.append("runtime admission source SUT differs from diagnostic descriptor")
    except Exception as exc:  # noqa: BLE001 - malformed admission must block, not escape
        blockers.append(f"runtime admission replay failed: {type(exc).__name__}: {exc}")
        return blockers
    design = descriptor.get("design") if isinstance(descriptor.get("design"), Mapping) else {}
    if (admission.get("mode") != "diagnostic"
            or admission.get("evidenceLabel") != descriptor.get("evidenceLabel")
            or admission.get("runCount") != expected_count
            or admission.get("warmupSeconds") != design.get("warmupSeconds")
            or admission.get("measurementSeconds") != design.get("measurementSeconds")):
        blockers.append("runtime admission differs from diagnostic campaign design")
    try:
        deadline = _timestamp(admission.get("authorizationDeadline"))
        deadline_epoch = math.floor(deadline.timestamp())
    except (ValueError, OverflowError, OSError) as exc:
        blockers.append(f"runtime admission deadline is invalid: {exc}")
    else:
        if deadline_epoch != owner.get("authorizationDeadlineEpoch"):
            blockers.append("runtime admission deadline differs from harness owner")
        if owner.get("experimentStopEpoch") != deadline_epoch - DEADLINE_CLEANUP_RESERVE_SECONDS:
            blockers.append("runtime admission does not retain the exact cleanup reserve")
    return blockers


def _deadline_command_blockers(
    value: Any,
    *,
    expected_command: list[str],
    where: str,
    identifiers: bool = False,
) -> list[str]:
    blockers: list[str] = []
    fields = {
        "attempted", "command", "returnCode", "timedOut", "errorCode", "stdout", "stderr",
    }
    if identifiers:
        fields.add("identifiers")
    if not isinstance(value, dict) or set(value) != fields:
        return [f"{where} command receipt fields differ"]
    if value.get("command") != expected_command or not isinstance(value.get("attempted"), bool) or not isinstance(
        value.get("timedOut"), bool
    ):
        blockers.append(f"{where} command identity/status is invalid")
    return_code = value.get("returnCode")
    if return_code is not None and (not isinstance(return_code, int) or isinstance(return_code, bool)):
        blockers.append(f"{where} return code is invalid")
    error_code = value.get("errorCode")
    if error_code is not None and (not isinstance(error_code, str) or not error_code):
        blockers.append(f"{where} error code is invalid")
    blockers.extend(_stream_summary_blockers(value.get("stdout"), f"{where} stdout"))
    blockers.extend(_stream_summary_blockers(value.get("stderr"), f"{where} stderr"))
    if identifiers:
        identity = value.get("identifiers")
        if not isinstance(identity, dict) or set(identity) != {"count", "sha256", "parseValid"}:
            blockers.append(f"{where} identifier summary fields differ")
        elif (not _integer(identity.get("count"))
              or not isinstance(identity.get("sha256"), str)
              or not SHA256_RE.fullmatch(identity.get("sha256", ""))
              or not isinstance(identity.get("parseValid"), bool)):
            blockers.append(f"{where} identifier summary is invalid")
    return blockers


def _deadline_verification_blockers(
    value: Any, project: str, where: str, *, require_clean: bool,
) -> list[str]:
    blockers: list[str] = []
    if not isinstance(value, dict) or set(value) != {"label", "queries", "remaining", "clean"}:
        return [f"{where} verification fields differ"]
    label = f"label=com.docker.compose.project={project}"
    if value.get("label") != label or not isinstance(value.get("clean"), bool):
        blockers.append(f"{where} label/verdict is invalid")
    queries = value.get("queries")
    remaining = value.get("remaining")
    kinds = ("containers", "networks", "volumes")
    if not isinstance(queries, dict) or set(queries) != set(kinds):
        return [*blockers, f"{where} query set differs"]
    if not isinstance(remaining, dict) or set(remaining) != set(kinds):
        return [*blockers, f"{where} remaining-resource set differs"]
    commands = {
        "containers": ["docker", "ps", "-aq", "--no-trunc", "--filter", label],
        "networks": ["docker", "network", "ls", "-q", "--no-trunc", "--filter", label],
        "volumes": ["docker", "volume", "ls", "-q", "--filter", label],
    }
    computed_clean = True
    for kind in kinds:
        query = queries[kind]
        blockers.extend(_deadline_command_blockers(
            query, expected_command=commands[kind], where=f"{where} {kind}", identifiers=True,
        ))
        identity = query.get("identifiers") if isinstance(query, Mapping) else None
        successful = (
            isinstance(query, Mapping) and query.get("attempted") is True
            and query.get("returnCode") == 0 and query.get("timedOut") is False
            and query.get("errorCode") is None and isinstance(identity, Mapping)
            and identity.get("parseValid") is True
        )
        if not successful:
            blockers.append(f"{where} {kind} query is not authoritative")
        expected_remaining = identity.get("count") if successful else None
        if remaining.get(kind) != expected_remaining:
            blockers.append(f"{where} {kind} remaining count does not replay")
        if expected_remaining != 0:
            computed_clean = False
        if require_clean:
            empty = _sha256_bytes(b"")
            if (not successful or expected_remaining != 0
                    or identity.get("sha256") != empty
                    or query.get("stdout") != {"sha256": empty, "bytes": 0, "lineCount": 0}):
                blockers.append(f"{where} {kind} does not prove zero owned resources")
    if value.get("clean") is not computed_clean:
        blockers.append(f"{where} clean verdict does not replay")
    if require_clean and value.get("clean") is not True:
        blockers.append(f"{where} is not clean")
    return blockers


def _deadline_cleanup_blockers(
    receipt: Any,
    *,
    owner: Mapping[str, Any],
    campaign: str,
    status: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    root_fields = {
        "schemaVersion", "kind", "campaign", "composeProject", "release", "resultRoot",
        "trigger", "processGroup", "composeTeardown", "verification", "authorization",
        "outcome", "blockers", "warnings",
    }
    if not isinstance(receipt, dict) or set(receipt) != root_fields:
        return ["deadline cleanup fields differ from the exact protocol"]
    project = owner.get("composeProject")
    release = owner.get("release")
    result_root = owner.get("resultRoot")
    if (receipt.get("schemaVersion") != 1 or receipt.get("kind") != "deadline-cleanup"
            or receipt.get("campaign") != campaign or receipt.get("composeProject") != project
            or receipt.get("release") != release or receipt.get("resultRoot") != result_root):
        blockers.append("deadline cleanup campaign/namespace identity differs")
    if receipt.get("outcome") != "clean" or receipt.get("blockers") != []:
        blockers.append("deadline cleanup did not finish cleanly")
    warnings = receipt.get("warnings")
    if (not isinstance(warnings, list) or warnings != sorted(set(warnings))
            or any(not isinstance(item, str) for item in warnings)):
        blockers.append("deadline cleanup warnings are malformed")

    trigger = receipt.get("trigger")
    trigger_fields = {"reason", "signal", "stopEpoch", "authorizationDeadlineEpoch", "triggeredAt"}
    triggered_at: datetime | None = None
    if not isinstance(trigger, dict) or set(trigger) != trigger_fields:
        blockers.append("deadline cleanup trigger fields differ")
        trigger = {}
    else:
        if (trigger.get("reason") != "runner-exit" or trigger.get("signal") is not None
                or trigger.get("stopEpoch") != owner.get("experimentStopEpoch")
                or trigger.get("authorizationDeadlineEpoch") != owner.get("authorizationDeadlineEpoch")):
            blockers.append("deadline cleanup trigger differs from successful admitted execution")
        try:
            triggered_at = _timestamp(trigger.get("triggeredAt"))
            if triggered_at.timestamp() >= owner.get("experimentStopEpoch", 0):
                blockers.append("successful runner exit did not precede the authorization stop epoch")
        except (ValueError, OSError, OverflowError) as exc:
            blockers.append(f"deadline cleanup trigger timestamp is invalid: {exc}")

    process = receipt.get("processGroup")
    process_fields = {
        "pid", "processGroupId", "identityValidated", "aliveAtCleanupStart", "termSent",
        "termSentAt", "exitedDuringTermGrace", "killRequired", "killSent", "killSentAt",
        "gone", "runnerReturnCode",
    }
    if not isinstance(process, dict) or set(process) != process_fields:
        blockers.append("deadline cleanup process-group fields differ")
        process = {}
    else:
        alive = process.get("aliveAtCleanupStart")
        exited = process.get("exitedDuringTermGrace")
        kill_required = process.get("killRequired")
        if (not _integer(process.get("pid"), minimum=2)
                or process.get("processGroupId") != process.get("pid")
                or process.get("identityValidated") is not True
                or process.get("gone") is not True
                or not isinstance(alive, bool)
                or not isinstance(process.get("termSent"), bool)
                or not isinstance(kill_required, bool)
                or not isinstance(process.get("killSent"), bool)
                or process.get("runnerReturnCode") != 0
                or status.get("exitCode") not in (0, "0")):
            blockers.append("deadline cleanup process-group proof is invalid")
        if alive:
            if (process.get("termSent") is not True or not isinstance(exited, bool)
                    or kill_required is not (not exited)
                    or process.get("killSent") is not kill_required):
                blockers.append("deadline cleanup TERM/KILL escalation does not replay")
            for field, required in (("termSentAt", True), ("killSentAt", kill_required)):
                value = process.get(field)
                if required:
                    try:
                        _timestamp(value)
                    except ValueError:
                        blockers.append(f"deadline cleanup {field} is invalid")
                elif value is not None:
                    blockers.append(f"deadline cleanup {field} should be null")
        elif (process.get("termSent") is not False or exited is not None
              or kill_required is not False or process.get("killSent") is not False
              or process.get("termSentAt") is not None or process.get("killSentAt") is not None):
            blockers.append("deadline cleanup no-live-group state is inconsistent")

    compose = receipt.get("composeTeardown")
    compose_command = ["docker", "compose", "-p", project]
    for relative in DEADLINE_COMPOSE_FILES:
        compose_command.extend(["-f", f"{release}/{relative}"])
    compose_command.extend(["down", "--volumes", "--remove-orphans"])
    if not isinstance(compose, dict) or set(compose) != {
        "attempted", "command", "returnCode", "timedOut", "errorCode", "stdout", "stderr",
        "cwd", "composeFiles",
    }:
        blockers.append("deadline cleanup Compose receipt fields differ")
    else:
        bounded = {key: compose[key] for key in (
            "attempted", "command", "returnCode", "timedOut", "errorCode", "stdout", "stderr",
        )}
        blockers.extend(_deadline_command_blockers(
            bounded, expected_command=compose_command, where="deadline cleanup Compose",
        ))
        if compose.get("attempted") is not True or compose.get("cwd") != release or (
            compose.get("composeFiles") != list(DEADLINE_COMPOSE_FILES)
        ):
            blockers.append("deadline cleanup Compose scope is invalid")

    verification = receipt.get("verification")
    if not isinstance(verification, dict) or set(verification) != {"initial", "fallback", "final"}:
        blockers.append("deadline cleanup verification fields differ")
    else:
        blockers.extend(_deadline_verification_blockers(
            verification.get("initial"), project, "deadline cleanup initial", require_clean=False,
        ))
        fallback = verification.get("fallback")
        if not isinstance(fallback, dict) or set(fallback) != {"required", "actions"} or not isinstance(
            fallback.get("required"), bool
        ):
            blockers.append("deadline cleanup fallback fields differ")
        elif not isinstance(fallback.get("actions"), dict) or set(fallback["actions"]) != {
            "containers", "networks", "volumes",
        }:
            blockers.append("deadline cleanup fallback action set differs")
        else:
            initial = verification.get("initial")
            compose_failed = (
                not isinstance(compose, Mapping)
                or compose.get("returnCode") != 0
                or compose.get("timedOut") is True
            )
            expected_fallback = compose_failed or not (
                isinstance(initial, Mapping) and initial.get("clean") is True
            )
            if fallback.get("required") is not expected_fallback:
                blockers.append("deadline cleanup fallback decision does not replay")
            prefixes = {
                "containers": ["docker", "rm", "-f", "--"],
                "networks": ["docker", "network", "rm", "--"],
                "volumes": ["docker", "volume", "rm", "-f", "--"],
            }
            for kind, prefix in prefixes.items():
                action = fallback["actions"][kind]
                if not isinstance(action, dict) or set(action) != {
                    "attempted", "command", "returnCode", "timedOut", "errorCode", "stdout",
                    "stderr", "identifierCount", "identifiersSha256",
                }:
                    blockers.append(f"deadline cleanup fallback {kind} fields differ")
                    continue
                count = action.get("identifierCount")
                command = action.get("command")
                if (not _integer(count) or not isinstance(action.get("identifiersSha256"), str)
                        or not SHA256_RE.fullmatch(action.get("identifiersSha256", ""))
                        or not isinstance(command, list) or command[:len(prefix)] != prefix
                        or len(command) != len(prefix) + count):
                    blockers.append(f"deadline cleanup fallback {kind} identity proof is invalid")
                blockers.extend(_deadline_command_blockers(
                    {key: action[key] for key in (
                        "attempted", "command", "returnCode", "timedOut", "errorCode", "stdout", "stderr",
                    )},
                    expected_command=command if isinstance(command, list) else prefix,
                    where=f"deadline cleanup fallback {kind}",
                ))
                initial_query = (
                    initial.get("queries", {}).get(kind)
                    if isinstance(initial, Mapping) and isinstance(initial.get("queries"), Mapping)
                    else None
                )
                initial_identity = (
                    initial_query.get("identifiers") if isinstance(initial_query, Mapping) else None
                )
                expected_count = (
                    initial_identity.get("count")
                    if expected_fallback and isinstance(initial_identity, Mapping) else 0
                )
                expected_digest = (
                    initial_identity.get("sha256")
                    if expected_fallback and isinstance(initial_identity, Mapping)
                    else _sha256_bytes(b"")
                )
                if count != expected_count or action.get("identifiersSha256") != expected_digest:
                    blockers.append(f"deadline cleanup fallback {kind} differs from initial inventory")
                if count == 0:
                    if (action.get("attempted") is not False or action.get("returnCode") is not None
                            or action.get("timedOut") is not False or action.get("errorCode") is not None):
                        blockers.append(f"deadline cleanup fallback {kind} empty action is inconsistent")
                elif (action.get("attempted") is not True or action.get("returnCode") != 0
                      or action.get("timedOut") is not False or action.get("errorCode") is not None):
                    blockers.append(f"deadline cleanup fallback {kind} did not successfully remove owned resources")
        blockers.extend(_deadline_verification_blockers(
            verification.get("final"), project, "deadline cleanup final", require_clean=True,
        ))

    authorization = receipt.get("authorization")
    completed_at: datetime | None = None
    auth_fields = {
        "completedAt", "completedAtEpoch", "beforeDeadline", "leaseFinalizerReserveSeconds",
        "leaseFinalizerWindowAvailable", "leaseReleaseDelegatedToLauncherFinalizer",
    }
    if not isinstance(authorization, dict) or set(authorization) != auth_fields:
        blockers.append("deadline cleanup authorization fields differ")
    else:
        try:
            completed_at = _timestamp(authorization.get("completedAt"))
            completed_epoch = authorization.get("completedAtEpoch")
            if (not _number(completed_epoch) or abs(completed_at.timestamp() - completed_epoch) > 0.01
                    or completed_epoch >= owner.get("authorizationDeadlineEpoch", 0)
                    or completed_epoch > owner.get("authorizationDeadlineEpoch", 0)
                        - DEADLINE_LEASE_FINALIZER_SECONDS):
                blockers.append("deadline cleanup completion time exceeds its authorization boundary")
            if triggered_at is not None and completed_at < triggered_at:
                blockers.append("deadline cleanup completed before its trigger")
        except (ValueError, OSError, OverflowError) as exc:
            blockers.append(f"deadline cleanup completion timestamp is invalid: {exc}")
        if (authorization.get("beforeDeadline") is not True
                or authorization.get("leaseFinalizerReserveSeconds") != DEADLINE_LEASE_FINALIZER_SECONDS
                or authorization.get("leaseFinalizerWindowAvailable") is not True
                or authorization.get("leaseReleaseDelegatedToLauncherFinalizer") is not True):
            blockers.append("deadline cleanup authorization/finalizer verdict is invalid")
    return blockers


def _runtime_image_blockers(document: Any, project: str, where: str) -> list[str]:
    blockers: list[str] = []
    fields = {"schemaVersion", "capturedAt", "composeProject", "services"}
    if not isinstance(document, dict) or set(document) != fields:
        return [f"{where} top-level fields differ"]
    if document.get("schemaVersion") != 1 or document.get("composeProject") != project:
        blockers.append(f"{where} project/schema binding differs")
    try:
        _timestamp(document.get("capturedAt"))
    except ValueError as exc:
        blockers.append(f"{where} timestamp is invalid: {exc}")
    services = document.get("services")
    if not isinstance(services, dict) or set(services) != set(RUNTIME_SERVICES):
        return [*blockers, f"{where} service set differs"]
    digest_re = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
    item_fields = {
        "containerId", "declaredImage", "containerImageId", "imageInspectId",
        "repoDigests", "composeProjectLabel", "composeServiceLabel", "queries",
    }
    for service in RUNTIME_SERVICES:
        item = services.get(service)
        if not isinstance(item, dict) or set(item) != item_fields:
            blockers.append(f"{where} fields differ for {service}")
            continue
        container_id = item.get("containerId")
        declared = item.get("declaredImage")
        image_id = item.get("containerImageId")
        digests = item.get("repoDigests")
        if not isinstance(container_id, str) or not CONTAINER_ID_RE.fullmatch(container_id):
            blockers.append(f"{where} container identity is invalid for {service}")
        if not isinstance(declared, str) or not declared:
            blockers.append(f"{where} declared image is missing for {service}")
        elif declared != EXPECTED_RUNTIME_IMAGES[service]:
            blockers.append(f"{where} declared image differs from the deployment contract for {service}")
        if not isinstance(image_id, str) or not IMAGE_ID_RE.fullmatch(image_id) or item.get("imageInspectId") != image_id:
            blockers.append(f"{where} image IDs differ for {service}")
        if not isinstance(digests, list) or not digests or digests != sorted(set(digests)) or any(
            not isinstance(value, str) or not digest_re.fullmatch(value) or not value.startswith(
                f"{EXPECTED_RUNTIME_REPOSITORIES[service]}@sha256:"
            ) for value in digests
        ):
            blockers.append(f"{where} repository digests are invalid for {service}")
        if item.get("composeProjectLabel") != project or item.get("composeServiceLabel") != service:
            blockers.append(f"{where} Compose labels differ for {service}")
        queries = item.get("queries")
        expected = {
            "containerInspect": ["docker", "inspect", "--format", CONTAINER_IMAGE_INSPECT_FORMAT, container_id],
            "imageInspect": ["docker", "image", "inspect", "--format", IMAGE_INSPECT_FORMAT, declared],
        }
        if not isinstance(queries, dict) or set(queries) != set(expected):
            blockers.append(f"{where} query set differs for {service}")
            continue
        for name, command in expected.items():
            query = queries.get(name)
            if not isinstance(query, dict) or set(query) != {
                "command", "returnCode", "stdout", "stderr"
            } or query.get("command") != command or not _integer(query.get("returnCode")) or (
                query.get("returnCode") != 0
            ) or not isinstance(query.get("stdout"), str) or query.get("stderr") != "":
                blockers.append(f"{where} query proof is invalid for {service}/{name}")
        if isinstance(queries, dict) and all(isinstance(queries.get(name), dict) for name in expected):
            container_fields = queries["containerInspect"].get("stdout", "").strip("\n").split("\t")
            image_fields = queries["imageInspect"].get("stdout", "").strip("\n").split("\t")
            if container_fields != [container_id, image_id, declared, project, service]:
                blockers.append(f"{where} container inspect output differs for {service}")
            if len(image_fields) != 2 or image_fields[0] != item.get("imageInspectId"):
                blockers.append(f"{where} image inspect output differs for {service}")
            else:
                try:
                    raw_digests = json.loads(
                        image_fields[1],
                        parse_constant=_invalid_json_constant,
                    )
                except (json.JSONDecodeError, ValueError) as exc:
                    blockers.append(f"{where} image inspect digests are invalid for {service}: {exc}")
                else:
                    if not isinstance(raw_digests, list) or sorted(raw_digests) != digests:
                        blockers.append(f"{where} image inspect digests differ for {service}")
    return blockers


def _queue_proof_blockers(document: Any, project: str, where: str) -> list[str]:
    blockers: list[str] = []
    if not isinstance(document, dict) or set(document) != {
        "schemaVersion", "composeProject", "purge", "measurement"
    }:
        return [f"{where} top-level fields differ"]
    if document.get("schemaVersion") != 1 or document.get("composeProject") != project:
        blockers.append(f"{where} project/schema binding differs")
    purge = document.get("purge")
    measurement = document.get("measurement")
    if not isinstance(purge, dict) or set(purge) != {"before", "command", "after"}:
        return [*blockers, f"{where} purge fields differ"]
    if not isinstance(measurement, dict) or set(measurement) != {"before", "consumerAtStart", "after"}:
        return [*blockers, f"{where} measurement fields differ"]
    states = [purge["before"], purge["after"], measurement["before"],
              measurement["consumerAtStart"], measurement["after"]]
    container_ids: set[str] = set()
    for index, state in enumerate(states):
        if not isinstance(state, dict) or set(state) != {"containerId", "messages", "consumers", "query"}:
            blockers.append(f"{where} state {index} fields differ")
            continue
        container_id = state.get("containerId")
        if not isinstance(container_id, str) or not CONTAINER_ID_RE.fullmatch(container_id):
            blockers.append(f"{where} state {index} container identity is invalid")
            continue
        container_ids.add(container_id)
        if any(not _integer(state.get(name)) for name in ("messages", "consumers")):
            blockers.append(f"{where} state {index} counts are invalid")
        expected_command = ["docker", "exec", container_id, "rabbitmqctl", "list_queues",
                            "-q", "name", "messages", "consumers"]
        query = state.get("query")
        if not isinstance(query, dict) or set(query) != {"command", "returnCode", "stdout", "stderr"} or (
            query.get("command") != expected_command or not _integer(query.get("returnCode")) or
            query.get("returnCode") != 0 or query.get("stderr") != "" or not isinstance(query.get("stdout"), str)
        ):
            blockers.append(f"{where} state {index} query proof is invalid")
            continue
        rows = [line.split() for line in query["stdout"].splitlines()
                if line.split() and line.split()[0] == "kieker"]
        if rows != [["kieker", str(state.get("messages")), str(state.get("consumers"))]]:
            blockers.append(f"{where} state {index} query output differs from counts")
    if len(container_ids) != 1:
        blockers.append(f"{where} spans multiple or missing RabbitMQ containers")
        container_id = None
    else:
        container_id = next(iter(container_ids))
    command = purge.get("command")
    expected_purge = ["docker", "exec", container_id, "rabbitmqctl", "purge_queue", "kieker"]
    if not isinstance(command, dict) or set(command) != {"command", "returnCode", "stdout", "stderr"} or (
        command.get("command") != expected_purge or not _integer(command.get("returnCode")) or
        command.get("returnCode") != 0 or not isinstance(command.get("stdout"), str) or
        not isinstance(command.get("stderr"), str)
    ):
        blockers.append(f"{where} purge command proof is invalid")
    if (purge["before"].get("consumers") != 0
            or (purge["after"].get("messages"), purge["after"].get("consumers")) != (0, 0)
            or (measurement["before"].get("messages"), measurement["before"].get("consumers")) != (0, 0)
            or (measurement["consumerAtStart"].get("messages"),
                measurement["consumerAtStart"].get("consumers")) != (0, 1)
            or (measurement["after"].get("messages"), measurement["after"].get("consumers")) != (0, 0)):
        blockers.append(f"{where} purge/exclusivity/drain conditions are not proven")
    return blockers


def _expected_fixed_load_return_code(
    workload: Any, *, effect_contract: bool,
) -> int | None:
    """Independently derive fixed-load status from retained terminal outcomes."""

    if not isinstance(workload, Mapping):
        return None
    failed = workload.get("failed")
    timed_out = workload.get("timedOut", 0)
    if not _integer(failed, minimum=0) or not _integer(timed_out, minimum=0):
        return None
    # fixed_load reports unsuccessful journeys with status 2 in every regime.
    # Cost runs still fail scientifically on those journeys; matching the
    # producer status here prevents a second, spurious process-proof blocker.
    return 2 if failed > 0 or timed_out > 0 else 0


def _child_process_blockers(
    document: Any,
    processes: Any,
    where: str,
    *,
    expect_performance_probe: bool = True,
    expected_workload_return_code: int | None = 0,
) -> list[str]:
    blockers: list[str] = []
    names = {"collector", *({"performanceProbe"} if expect_performance_probe else set())}
    if not isinstance(document, dict) or set(document) != names:
        return [f"{where} child-process artifact fields differ"]
    if (not _integer(expected_workload_return_code)
            or expected_workload_return_code not in {0, 2}):
        blockers.append(f"{where} expected workload return code is invalid")
    if not isinstance(processes, dict) or set(processes) != {*names, "workload"} or (
        processes.get("workload") != {"returnCode": expected_workload_return_code}
    ):
        blockers.append(f"{where} receipt process fields differ")
        processes = {} if not isinstance(processes, dict) else processes
    fields = {
        "pid", "command", "timeoutSeconds", "noProgressTimeoutSeconds",
        "timedOut", "communicationError",
        "terminateSent", "killSent", "joined", "returnCode",
    }
    for name in names:
        proof = document.get(name)
        if not isinstance(proof, dict) or set(proof) != fields:
            blockers.append(f"{where} {name} proof fields differ")
            continue
        if not _integer(proof.get("pid"), minimum=1) or not isinstance(proof.get("command"), list) or not (
            proof["command"]
        ) or not all(isinstance(value, str) for value in proof["command"]) or not _number(
            proof.get("timeoutSeconds"), positive=True
        ):
            blockers.append(f"{where} {name} process identity is invalid")
        # The collector's terminal work is data-proportional, so its join must
        # carry a stall watchdog; the barrier-bounded probe must not, because a
        # watchdog there could only hide a scheduling defect.
        watchdog = proof.get("noProgressTimeoutSeconds")
        if (not _number(watchdog, positive=True)
                if name == "collector" else watchdog is not None):
            blockers.append(f"{where} {name} join watchdog policy differs")
            continue
        if (proof.get("timedOut") is not False or proof.get("communicationError") is not None or
                proof.get("terminateSent") is not False or proof.get("killSent") is not False or
                proof.get("joined") is not True or not _integer(proof.get("returnCode")) or
                proof.get("returnCode") != 0):
            blockers.append(f"{where} {name} was not cleanly joined")
        if processes.get(name) != proof:
            blockers.append(f"{where} {name} receipt differs from retained child proof")
    return blockers


def _collector_telemetry_blockers(
    events: list[Any],
    telemetry: Any,
    collector_stats: Any,
    *,
    posture: str,
    effect_contract: bool,
    where: str,
    closure_groups: Any = None,
    exposure_tolerance: Any = None,
) -> list[str]:
    """Reconcile retained events with the collector's exact terminal counters.

    A single bad record is admissible only for effect smoke evidence.  It is an
    explicitly surfaced parse loss, not evidence that the message stream is
    complete or replay-free.
    """

    blockers: list[str] = []
    if not isinstance(telemetry, Mapping) or not isinstance(collector_stats, Mapping):
        return [f"{where} telemetry/collector summary fields differ"]

    native = _load_module(
        Path(__file__).parents[1] / "collectors" / "kieker_native.py",
        "terminal_native_trace_completeness",
    )
    entry_point_woven = native.entry_point_woven(closure_groups)

    count_fields = (
        "messages", "containers_ok", "containers_bad", "records_ok", "records_bad",
    )
    if any(not _integer(collector_stats.get(field), minimum=0) for field in count_fields):
        return [f"{where} collector summary counters are invalid"]

    records_bad = collector_stats["records_bad"]
    # F-ADH-084: identical formula to performance_campaign / candidate_pilot. A
    # rejected container is netted out only when the receipt's diagnostics
    # account for every rejection and prove it is the intervention's own restart
    # banner. Absent tolerance, cost evidence, or an unaccounted rejection all
    # mean ZERO netting, so every existing caller stays strict.
    tolerated_containers = 0
    if isinstance(exposure_tolerance, Mapping):
        claimed = exposure_tolerance.get("toleratedContainerParseFailures", 0)
        residual = exposure_tolerance.get("residualContainerParseFailures", 0)
        if not _integer(claimed, minimum=0) or not _integer(residual, minimum=0):
            blockers.append(f"{where} container parse tolerance counters differ")
        elif not effect_contract:
            if claimed or residual:
                blockers.append(
                    f"{where} cost evidence carries a nonzero container parse tolerance")
        elif claimed:
            described = exposure_tolerance.get("containerParseFailures")
            if (not isinstance(described, list)
                    or len(described) != collector_stats["containers_bad"]
                    or claimed > collector_stats["containers_bad"]):
                blockers.append(
                    f"{where} container parse tolerance is not accounted for by its diagnostics")
            else:
                tolerated_containers = claimed
    if collector_stats["containers_bad"] - tolerated_containers != 0:
        blockers.append(f"{where} collector container parse failures are not exactly zero")
    maximum_records_bad = 1 if effect_contract else 0
    if records_bad > maximum_records_bad:
        boundary = "at most one" if effect_contract else "exactly zero"
        blockers.append(
            f"{where} collector record parse failures must be {boundary}"
        )
    if telemetry.get("parseFailures") != records_bad:
        blockers.append(
            f"{where} telemetry parseFailures does not surface retained records_bad"
        )
    if collector_stats["records_ok"] != len(events):
        blockers.append(f"{where} collector records_ok differs from retained event count")
    if collector_stats.get("runtime_host_map_loaded") is not True:
        blockers.append(f"{where} runtime host/service map was not loaded")
    if collector_stats.get("acknowledgement_mode") != "manual":
        blockers.append(f"{where} collector AMQP acknowledgement mode was not manual")
    correlation = collector_stats.get("correlation")
    if not isinstance(correlation, Mapping):
        blockers.append(f"{where} collector correlation summary is missing")
    else:
        # A missing depth-0 parent is expected when the posture does not weave
        # the trace-starting sensor; genuine correlation errors, and any missing
        # root when the entry point IS woven, still block. See F-ADH-064.
        unwoven_root = correlation.get("eventsWithUnwovenRootParent", 0)
        # F-ADH-083: identical formula to performance_campaign / candidate_pilot.
        probe_orphans = correlation.get("eventsWithProbeOrphanRoot", 0)
        if not _integer(probe_orphans, minimum=0) or probe_orphans > unwoven_root:
            blockers.append(f"{where} probe-orphan-root count is inconsistent")
            probe_orphans = 0
        if probe_orphans and not effect_contract:
            blockers.append(f"{where} readiness-probe orphans on cost evidence")
        raw_errors = correlation.get("eventsWithCorrelationErrors") or 0
        completeness = correlation.get("traceCompleteness")
        raw_gap_traces = (
            completeness.get("tracesWithEoiGaps") if isinstance(completeness, Mapping) else None)
        raw_missing = (
            completeness.get("missingEoiCount") if isinstance(completeness, Mapping) else None)
        # F-ADH-080: the producer-side gate and candidate_pilot both subtract the
        # timestamp-scoped exposure tolerance (F-ADH-074/076) from these counters
        # for effect evidence; this validator did not, so the first fault cell
        # that candidate_pilot ever calls valid would have been blocked here for
        # the fault's own signature. An ABSENT tolerance still means ZERO
        # tolerance, so cost evidence and every existing caller stay strict.
        tolerated_events = 0
        residual_gap_traces = raw_gap_traces
        residual_missing = raw_missing
        if isinstance(exposure_tolerance, Mapping):
            counters = (
                "toleratedCorrelationErrorEvents", "residualCorrelationErrorEvents",
                "residualEoiGapTraces", "residualMissingEoiCount",
            )
            if any(not _integer(exposure_tolerance.get(name), minimum=0)
                   for name in counters):
                blockers.append(f"{where} exposure tolerance counters differ")
            elif not effect_contract:
                if any(exposure_tolerance[name] != 0 for name in counters):
                    blockers.append(
                        f"{where} cost evidence carries a nonzero exposure tolerance")
            elif (exposure_tolerance["toleratedCorrelationErrorEvents"]
                    > max(raw_errors - unwoven_root, 0)
                  or (_integer(raw_gap_traces, minimum=0)
                      and exposure_tolerance["residualEoiGapTraces"] > raw_gap_traces)
                  or (_integer(raw_missing, minimum=0)
                      and exposure_tolerance["residualMissingEoiCount"] > raw_missing)):
                # A tolerance may excuse what was observed, never more than it.
                blockers.append(
                    f"{where} exposure tolerance exceeds the observed collector counters")
            else:
                tolerated_events = exposure_tolerance["toleratedCorrelationErrorEvents"]
                residual_gap_traces = exposure_tolerance["residualEoiGapTraces"]
                residual_missing = exposure_tolerance["residualMissingEoiCount"]
        elif exposure_tolerance is not None:
            blockers.append(f"{where} exposure tolerance is not an object")
        genuine_errors = raw_errors - unwoven_root - tolerated_events
        if genuine_errors != 0:
            blockers.append(f"{where} native parent correlation errors are nonzero")
        if unwoven_root - probe_orphans != 0 and entry_point_woven:
            blockers.append(
                f"{where} missing native trace roots while the entry point is woven")
        if correlation.get("eventsWithCorrelationWarnings") != 0:
            blockers.append(f"{where} native correlation/replay warnings are nonzero")
        if correlation.get("eventsWithServiceAttributionErrors") != 0:
            blockers.append(f"{where} service-attribution errors are nonzero")
        if (not isinstance(completeness, Mapping)
                or residual_gap_traces != 0
                or residual_missing != 0):
            blockers.append(f"{where} native EOI completeness gaps are nonzero")
    parent_states: dict[Any, int] = {}
    attribution_states: dict[Any, int] = {}
    correlation_errors = 0
    correlation_warnings = 0
    attribution_errors = 0
    objects: list[Mapping] = []
    for event in events:
        if not isinstance(event, Mapping):
            blockers.append(f"{where} retained event is not an object")
            continue
        objects.append(event)
        parent = event.get("parent_resolution")
        attribution = event.get("service_attribution_status")
        parent_states[parent] = parent_states.get(parent, 0) + 1
        attribution_states[attribution] = attribution_states.get(attribution, 0) + 1
        correlation_errors += bool(event.get("correlation_errors"))
        correlation_warnings += bool(event.get("correlation_warnings"))
        attribution_errors += bool(event.get("service_attribution_errors"))
    replayed_correlation = {
        "events": len(events),
        "parentResolution": dict(sorted(parent_states.items())),
        "serviceAttribution": dict(sorted(attribution_states.items())),
        "eventsWithCorrelationErrors": correlation_errors,
        "eventsWithUnwovenRootParent": native.count_unwoven_root_parents(objects),
        "eventsWithProbeOrphanRoot": native.count_probe_orphan_roots(objects),
        "eventsWithCorrelationWarnings": correlation_warnings,
        "eventsWithServiceAttributionErrors": attribution_errors,
        "traceCompleteness": native.trace_completeness(
            native.collect_trace_eois(objects)),
    }
    if correlation != replayed_correlation:
        blockers.append(f"{where} correlation summary differs from retained events")

    if posture == "full":
        messages = collector_stats["messages"]
        containers_ok = collector_stats["containers_ok"]
        if messages != containers_ok:
            blockers.append(
                f"{where} collector messages and containers_ok differ"
            )
        unique_event_hashes = len({
            event.get("message_sha1")
            for event in events
            if isinstance(event, Mapping)
        })
        unexplained_deficit = messages - unique_event_hashes
        if effect_contract:
            if not 0 <= unexplained_deficit <= records_bad:
                blockers.append(
                    f"{where} bounded unexplained unique-message deficit is outside "
                    "[0, records_bad]"
                )
        elif unexplained_deficit != 0:
            blockers.append(
                f"{where} unique message bodies do not exactly match collector messages"
            )
    return blockers


def _durable_spool_blockers(
    spool_path: Path,
    runtime_images_path: Path,
    events: list[Any],
    telemetry: Any,
    collector_stats: Any,
    campaign_runner: Any,
    *,
    where: str,
) -> list[str]:
    """Independently replay and reconcile the schema-v2 raw-body spool."""

    blockers: list[str] = []
    try:
        spool_replay = campaign_runner.replay_spool_evidence(
            spool_path, runtime_images_path,
        )
        summary = spool_replay["summary"]
        telemetry_summary = (
            telemetry.get("spool") if isinstance(telemetry, Mapping) else None
        )
        if summary.get("complete") is not True:
            blockers.append(
                f"{where} durable spool is incomplete: {summary.get('blockers')}"
            )
        if spool_replay["events"] != events:
            blockers.append(
                f"{where} traces differ from deterministic durable spool replay"
            )
        if telemetry_summary != summary:
            blockers.append(
                f"{where} durable spool summary differs from independent replay"
            )
        if (not isinstance(collector_stats, Mapping)
                or collector_stats.get("spool") != summary):
            blockers.append(
                f"{where} collector durable spool summary differs from replay"
            )
        if (not isinstance(collector_stats, Mapping)
                or collector_stats.get("attribution_configuration")
                != spool_replay.get("attributionConfiguration")
                or collector_stats.get("attribution_configuration_sha256")
                != spool_replay.get("attributionConfigurationSha256")):
            blockers.append(
                f"{where} collector attribution configuration differs from replay"
            )
        expected_counts = {
            field: collector_stats.get(field)
            for field in (
                "messages", "containers_ok", "containers_bad",
                "records_ok", "records_bad",
            )
        } if isinstance(collector_stats, Mapping) else None
        if spool_replay["counts"] != expected_counts:
            blockers.append(
                f"{where} collector counters differ from durable spool replay"
            )
    except Exception as exc:  # noqa: BLE001 - any raw replay failure blocks evidence
        blockers.append(
            f"{where} durable spool replay failed: {type(exc).__name__}: {exc}"
        )
    return blockers


def _workload_artifact_blockers(
    document: Any,
    *,
    configuration: Mapping[str, Any],
    receipt: Mapping[str, Any] | None,
    duration_seconds: int,
    where: str,
) -> list[str]:
    """Replay a fixed-load artifact instead of trusting its receipt projection."""

    blockers: list[str] = []
    v1_fields = {
        "schemaVersion", "startedAtEpoch", "endedAtEpoch", "schedule", "offered",
        "completed", "failed", "concurrency", "requests", "latencyMs", "failures",
    }
    v2_fields = v1_fields | {
        "controllerStartedAtEpoch", "successful", "timedOut", "settled",
        "journeyEvidence",
    }
    if not isinstance(document, dict):
        return [f"{where} fields differ from fixed-load protocol"]
    schema_version = document.get("schemaVersion")
    expected_fields = v1_fields if schema_version == 1 else v2_fields if schema_version == 2 else None
    if expected_fields is None or set(document) != expected_fields:
        return [f"{where} fields differ from fixed-load protocol v{schema_version}"]
    started = document.get("startedAtEpoch")
    ended = document.get("endedAtEpoch")
    if not _number(started) or not _number(ended) or ended < started:
        blockers.append(f"{where} timestamps are invalid")
    schedule = document.get("schedule")
    expected_schedule = {
        "kind": "fixed-open-loop",
        "journeysPerSecond": configuration.get("journeysPerSecond"),
        "durationSeconds": duration_seconds,
    }
    if schema_version == 2:
        expected_schedule["barrierAtEpoch"] = started
        barrier_id = schedule.get("barrierId") if isinstance(schedule, dict) else None
        expected_schedule["barrierId"] = barrier_id
        if not isinstance(barrier_id, str) or not re.fullmatch(
            r"barrier-[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", barrier_id
        ):
            blockers.append(f"{where} barrier ID is missing or malformed")
        controller_started = document.get("controllerStartedAtEpoch")
        if (not _number(controller_started) or not _number(started)
                or float(controller_started) > float(started)):
            blockers.append(f"{where} controller/barrier timestamps are invalid")
    if schedule != expected_schedule:
        blockers.append(f"{where} schedule differs from the campaign configuration")
    counts = ("offered", "completed", "failed", "concurrency", "requests")
    if schema_version == 2:
        counts = (*counts, "successful", "timedOut", "settled")
    if any(not _integer(document.get(field), minimum=0) for field in counts):
        blockers.append(f"{where} counters are invalid")
    else:
        expected_offered = max(
            1, math.floor(float(configuration.get("journeysPerSecond", 0)) * duration_seconds)
        )
        if document["offered"] != expected_offered:
            blockers.append(f"{where} offered count differs from the fixed-rate schedule")
        if schema_version == 1:
            if document["completed"] + document["failed"] != document["offered"]:
                blockers.append(f"{where} completed/failed denominator differs from offered")
        elif not (
            document["completed"] == document["successful"]
            and document["successful"] + document["failed"] + document["timedOut"]
            == document["settled"] == document["offered"]
        ):
            blockers.append(f"{where} terminal outcome denominator differs from offered")
        if document["concurrency"] != configuration.get("concurrency"):
            blockers.append(f"{where} concurrency differs from the campaign configuration")
    failures = document.get("failures")
    if not isinstance(failures, list) or not all(isinstance(item, str) for item in failures):
        blockers.append(f"{where} failures are malformed")
    if document.get("failed") == 0 and failures != []:
        blockers.append(f"{where} reports failure text with a zero failed denominator")
    latency = document.get("latencyMs")
    latency_fields = {"count", "p50", "p95", "p99", "mean"}
    if schema_version == 2:
        latency_fields.add("denominator")
    if not isinstance(latency, dict) or set(latency) != latency_fields:
        blockers.append(f"{where} latency fields differ from fixed-load protocol")
    else:
        if not _integer(latency.get("count")) or latency["count"] != document.get("completed"):
            blockers.append(f"{where} latency count differs from completed journeys")
        if schema_version == 2 and latency.get("denominator") != "successful-journeys":
            blockers.append(f"{where} latency denominator differs")
        statistic_fields = {"p50", "p95", "p99", "mean"}
        if latency.get("count") == 0:
            if any(latency.get(field) is not None for field in statistic_fields):
                blockers.append(f"{where} empty latency statistics must be null")
        elif any(not _number(latency.get(field)) or latency[field] < 0 for field in statistic_fields):
            blockers.append(f"{where} latency values are invalid")
    if receipt is not None:
        workload_fields = ("offered", "completed", "failed", "concurrency")
        if schema_version == 2:
            workload_fields = (
                "offered", "completed", "successful", "failed", "timedOut", "settled",
                "concurrency",
            )
        expected_workload = {key: document.get(key) for key in workload_fields}
        if receipt.get("workload") != expected_workload or receipt.get("latencyMs") != latency:
            blockers.append(f"{where} differs from receipt workload/latency projection")
        window = receipt.get("window")
        if isinstance(window, dict) and _number(started) and _number(ended):
            expected_started = datetime.fromtimestamp(float(started), timezone.utc).isoformat()
            expected_ended = datetime.fromtimestamp(float(ended), timezone.utc).isoformat()
            settled_at = window.get("workloadSettledAt", window.get("endedAt"))
            if window.get("startedAt") != expected_started or settled_at != expected_ended:
                blockers.append(f"{where} timestamps differ from the receipt workload interval")
            if schema_version == 2 and window.get("barrierAt") != expected_started:
                blockers.append(f"{where} shared barrier differs from the receipt window")
            if schema_version == 2 and "workloadSettledAt" in window:
                nominal_end = datetime.fromtimestamp(
                    float(started) + duration_seconds, timezone.utc).isoformat()
                if window.get("endedAt") != nominal_end:
                    blockers.append(f"{where} nominal measurement end differs from schedule")
    return blockers


def _resources_artifact_blockers(
    document: Any,
    *,
    receipt: Mapping[str, Any],
    where: str,
    resource_validator: Any | None = None,
    expected_barrier_id: str | None = None,
    expected_start_epoch: float | None = None,
    expected_duration_seconds: float | None = None,
    artifact_sha256: str | None = None,
    offered_journeys: int | None = None,
    expected_container_identity: Mapping[str, str] | None = None,
) -> list[str]:
    """Replay the retained performance-probe artifact and its receipt projection."""

    blockers: list[str] = []
    v1_fields = {
        "schemaVersion", "startedAtEpoch", "endedAtEpoch", "applicationCpuSeconds",
        "applicationMemoryPeakBytes", "hostCpuSeconds", "sampleIntervalSeconds",
        "excludedServices", "samples",
    }
    v2_fields = v1_fields | {"requiredServices", "requestedStartAtEpoch", "barrierId"}
    if not isinstance(document, dict):
        return [f"{where} fields differ from performance-probe protocol"]
    schema_version = document.get("schemaVersion")
    if schema_version == 3:
        if resource_validator is None:
            return [f"{where} v3 replay checker is unavailable"]
        try:
            replay = resource_validator.validate_resource_evidence(
                document,
                required_services=set(APP_SERVICES),
                expected_barrier_id=expected_barrier_id,
                expected_start_epoch=expected_start_epoch,
                expected_duration_seconds=expected_duration_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - retained evidence must fail closed
            return [f"{where} v3 replay raised {type(exc).__name__}: {exc}"]
        if not isinstance(replay, Mapping) or replay.get("verdict") != "pass":
            blockers.append(
                f"{where} v3 replay blocked: "
                f"{replay.get('blockers') if isinstance(replay, Mapping) else replay}"
            )
        if (expected_container_identity is not None
                and document.get("containerIdentity") != dict(expected_container_identity)):
            blockers.append(
                f"{where} container identities differ from the independent runtime-image proof"
            )
        cpu = document.get("applicationCpuSeconds")
        endpoint = (
            float(cpu) / offered_journeys
            if _number(cpu) and _integer(offered_journeys, minimum=1) else None
        )
        expected_resources = {
            "applicationCpuSeconds": cpu,
            "applicationMemoryPeakBytes": document.get("applicationMemoryPeakBytes"),
            "hostCpuSeconds": document.get("hostCpuSeconds"),
            "contract": document.get("contract"),
            "artifactSha256": artifact_sha256,
            "nominalStartAtEpoch": document.get("nominalStartAtEpoch"),
            "nominalEndAtEpoch": document.get("nominalEndAtEpoch"),
            "measurementDurationSeconds": document.get("measurementDurationSeconds"),
            "samplingIntervalSeconds": (
                document.get("sampling", {}).get("intervalSeconds")
                if isinstance(document.get("sampling"), Mapping) else None
            ),
            "offeredJourneys": offered_journeys,
            "applicationCpuSecondsPerOfferedJourney": endpoint,
        }
        if receipt.get("resources") != expected_resources:
            blockers.append(f"{where} differs from receipt resource/cost projection")
        return blockers
    expected_fields = v1_fields if schema_version == 1 else v2_fields if schema_version == 2 else None
    if expected_fields is None or set(document) != expected_fields:
        return [f"{where} fields differ from performance-probe protocol v{schema_version}"]
    started = document.get("startedAtEpoch")
    ended = document.get("endedAtEpoch")
    if not _number(started) or not _number(ended) or ended < started:
        blockers.append(f"{where} timestamps are invalid")
    measures = ("applicationCpuSeconds", "applicationMemoryPeakBytes", "hostCpuSeconds")
    if any(not _number(document.get(field)) or document[field] < 0 for field in measures):
        blockers.append(f"{where} aggregate resource values are invalid")
    if not _number(document.get("sampleIntervalSeconds"), positive=True):
        blockers.append(f"{where} sample interval is invalid")
    if document.get("excludedServices") != ["db", "rabbitmq", "registry"]:
        blockers.append(f"{where} excluded-service boundary differs from the runner")
    if schema_version == 2:
        if document.get("requiredServices") != sorted(APP_SERVICES):
            blockers.append(f"{where} required application service set is incomplete")
        barrier_id = document.get("barrierId")
        if not isinstance(barrier_id, str) or not re.fullmatch(r"barrier-[0-9a-f]{32}", barrier_id):
            blockers.append(f"{where} barrier ID is missing or malformed")
        requested = document.get("requestedStartAtEpoch")
        if (not _number(requested) or not _number(started)
                or abs(float(started) - float(requested)) > 1.0):
            blockers.append(f"{where} did not join its shared measurement barrier")
    samples = document.get("samples")
    if not isinstance(samples, list) or not samples:
        blockers.append(f"{where} samples are missing")
    else:
        sample_fields = {"epoch", "applicationCpuPercent", "applicationMemoryBytes", "containers"}
        for index, sample in enumerate(samples):
            if not isinstance(sample, dict) or set(sample) != sample_fields:
                blockers.append(f"{where} sample {index} fields differ")
                continue
            if any(not _number(sample.get(field)) or sample[field] < 0 for field in (
                "epoch", "applicationCpuPercent", "applicationMemoryBytes"
            )) or not isinstance(sample.get("containers"), list) or not all(
                isinstance(row, dict) for row in sample["containers"]
            ):
                blockers.append(f"{where} sample {index} is malformed")
        valid_memory = [
            sample["applicationMemoryBytes"] for sample in samples
            if isinstance(sample, dict) and _number(sample.get("applicationMemoryBytes"))
        ]
        if valid_memory and document.get("applicationMemoryPeakBytes") != max(valid_memory):
            blockers.append(f"{where} memory peak does not replay from samples")
    expected_resources = {key: document.get(key) for key in measures}
    if receipt.get("resources") != expected_resources:
        blockers.append(f"{where} differs from the receipt resource projection")
    return blockers


def _journey_evidence_blockers(
    run: Path,
    aggregate: Mapping[str, Any],
    *,
    ledger_name: str,
    fixed_load: Any,
    receipt: Mapping[str, Any] | None,
    where: str,
) -> list[str]:
    """Replay the plan/hash-chain rather than trusting aggregate counters."""

    if aggregate.get("schemaVersion") != 2:
        return []
    blockers: list[str] = []
    ledger_path = run / ledger_name
    plan_path = ledger_path.with_suffix(".plan.json")
    try:
        validation = fixed_load.validate_journey_ledger(plan_path, ledger_path)
        plan = _read_json(plan_path)
        expected_evidence = {
            "plan": plan_path.name,
            "ledger": ledger_path.name,
            "planSha256": validation["planSha256"],
            "lastRecordSha256": validation["lastRecordSha256"],
        }
        if aggregate.get("journeyEvidence") != expected_evidence:
            blockers.append(f"{where} aggregate binding differs from plan/hash-chain")
        if aggregate.get("offered") != validation["terminalJourneys"] or aggregate.get(
            "settled"
        ) != validation["terminalJourneys"]:
            blockers.append(f"{where} terminal ledger denominator differs from aggregate")
        schedule = aggregate.get("schedule")
        if not isinstance(plan, dict) or not isinstance(schedule, dict) or (
            plan.get("barrierId") != schedule.get("barrierId")
        ):
            blockers.append(f"{where} plan and workload barrier IDs differ")
        if receipt is not None:
            artifacts = receipt.get("candidateArtifacts")
            expected_artifact_fields = {
                "measurementBarrierSha256", "journeyPlanSha256",
                "journeyLedgerSha256", "journeyPlanCanonicalSha256",
                "journeyLedgerLastRecordSha256", "appWitnessSha256",
                "pathGroundTruthStatus", "pathGroundTruthReason",
            }
            if not isinstance(artifacts, dict) or set(artifacts) != expected_artifact_fields:
                blockers.append(f"{where} receipt candidate-artifact fields differ")
            else:
                expected = {
                    "journeyPlanSha256": _sha256_bytes(plan_path.read_bytes()),
                    "journeyLedgerSha256": _sha256_bytes(ledger_path.read_bytes()),
                    "journeyPlanCanonicalSha256": validation["planSha256"],
                    "journeyLedgerLastRecordSha256": validation["lastRecordSha256"],
                }
                for field, value in expected.items():
                    if artifacts.get(field) != value:
                        blockers.append(f"{where} receipt {field} differs from retained evidence")
                if artifacts.get("appWitnessSha256") is not None or artifacts.get(
                    "pathGroundTruthStatus"
                ) != "unsupported" or not isinstance(artifacts.get("pathGroundTruthReason"), str):
                    blockers.append(f"{where} unsupported application witness is mislabeled")
    except Exception as exc:  # noqa: BLE001 - malformed ledgers must block, never abort
        blockers.append(f"{where} replay failed: {type(exc).__name__}: {exc}")
    return blockers


def _measurement_barrier_blockers(
    document: Any,
    *,
    workload: Mapping[str, Any],
    resources: Mapping[str, Any] | None,
    receipt: Mapping[str, Any],
    queue_proof: Mapping[str, Any] | None,
    duration_seconds: int,
    where: str,
) -> list[str]:
    """Bind all measurement participants to one retained start barrier."""

    fields = {
        "schemaVersion", "barrierId", "createdAt", "barrierAt", "barrierAtEpoch",
        "barrierMonotonic", "measurementSeconds", "participants",
        "collectorAcknowledgement",
    }
    if not isinstance(document, dict) or set(document) != fields:
        return [f"{where} fields differ"]
    blockers: list[str] = []
    barrier_id = document.get("barrierId")
    barrier_epoch = document.get("barrierAtEpoch")
    schema_version = document.get("schemaVersion")
    if schema_version not in {1, 2} or not isinstance(barrier_id, str) or not re.fullmatch(
        r"barrier-[0-9a-f]{32}", barrier_id
    ):
        blockers.append(f"{where} schema/barrier identity is invalid")
    try:
        created = _timestamp(document.get("createdAt"))
        barrier_at = _timestamp(document.get("barrierAt"))
        if not _number(barrier_epoch) or abs(barrier_at.timestamp() - float(barrier_epoch)) > 1e-6:
            blockers.append(f"{where} wall/epoch start differs")
        if created > barrier_at:
            blockers.append(f"{where} was created after its start")
    except ValueError as exc:
        blockers.append(f"{where} timestamp is invalid: {exc}")
    if not _number(document.get("barrierMonotonic"), positive=True) or document.get(
        "measurementSeconds"
    ) != duration_seconds:
        blockers.append(f"{where} monotonic start/duration is invalid")
    effect_contract = (
        receipt.get("analysisKind") == "effect"
        and receipt.get("resourceUse") == "diagnostic-only"
    )
    expected_participants = ["workload"]
    if not effect_contract:
        expected_participants.append("performance-probe")
    expected_participants.append("collector")
    if receipt.get("intervention") is not None:
        expected_participants.append("intervention-controller")
    if document.get("participants") != expected_participants:
        blockers.append(f"{where} participant set differs")
    schedule = workload.get("schedule") if isinstance(workload, Mapping) else None
    window = receipt.get("window") if isinstance(receipt.get("window"), Mapping) else None
    resource_binding_ok = effect_contract and resources is None
    if not effect_contract:
        resource_binding_ok = (
            isinstance(resources, Mapping)
            and resources.get("barrierId") == barrier_id
            and resources.get("requestedStartAtEpoch") == barrier_epoch
        )
    if not isinstance(schedule, Mapping) or schedule.get("barrierId") != barrier_id or (
        schedule.get("barrierAtEpoch") != barrier_epoch
    ) or not resource_binding_ok or not isinstance(window, Mapping) or window.get(
        "barrierAt"
    ) != document.get("barrierAt"):
        blockers.append(f"{where} participant bindings differ")
    acknowledgement = document.get("collectorAcknowledgement")
    if schema_version == 1:
        legacy_fields = {
            "observedAt", "observedMonotonicOffsetSeconds", "queueState",
        }
        if not isinstance(acknowledgement, dict) or set(acknowledgement) != legacy_fields:
            blockers.append(f"{where} collector acknowledgement fields differ")
        else:
            try:
                observed = _timestamp(acknowledgement.get("observedAt"))
                offset = acknowledgement.get("observedMonotonicOffsetSeconds")
                if not _number(offset) or float(offset) < -1.0 or observed < _timestamp(
                    document.get("barrierAt")
                ) - timedelta(seconds=1):
                    blockers.append(f"{where} collector acknowledgement timing is invalid")
            except ValueError as exc:
                blockers.append(f"{where} collector acknowledgement time is invalid: {exc}")
    elif schema_version == 2:
        query_fields = {
            "queryStartedAtWall", "queryStartedMonotonicOffsetSeconds",
            "queryCompletedAtWall", "queryCompletedMonotonicOffsetSeconds",
            "queueState",
        }
        if not isinstance(acknowledgement, dict) or set(acknowledgement) != query_fields:
            blockers.append(f"{where} collector acknowledgement fields differ")
        else:
            try:
                barrier_at = _timestamp(document.get("barrierAt"))
                started_at = _timestamp(acknowledgement.get("queryStartedAtWall"))
                completed_at = _timestamp(acknowledgement.get("queryCompletedAtWall"))
                started_offset = acknowledgement.get(
                    "queryStartedMonotonicOffsetSeconds")
                completed_offset = acknowledgement.get(
                    "queryCompletedMonotonicOffsetSeconds")
                earliest = barrier_at - timedelta(
                    seconds=COLLECTOR_BARRIER_EARLY_TOLERANCE_SECONDS)
                latest = barrier_at + timedelta(
                    seconds=COLLECTOR_BARRIER_COMPLETION_DEADLINE_SECONDS)
                if (not _number(started_offset) or not _number(completed_offset)
                        or float(started_offset)
                            < -COLLECTOR_BARRIER_EARLY_TOLERANCE_SECONDS
                        or float(completed_offset) < float(started_offset)
                        or float(completed_offset)
                            > COLLECTOR_BARRIER_COMPLETION_DEADLINE_SECONDS
                        or started_at < earliest or started_at > latest
                        or completed_at < started_at or completed_at > latest):
                    blockers.append(
                        f"{where} collector acknowledgement query timing is invalid")
            except ValueError as exc:
                blockers.append(
                    f"{where} collector acknowledgement query time is invalid: {exc}")
    if isinstance(acknowledgement, dict):
        retained_state = None
        if isinstance(queue_proof, Mapping) and isinstance(queue_proof.get("measurement"), Mapping):
            retained_state = queue_proof["measurement"].get("consumerAtStart")
        if acknowledgement.get("queueState") != retained_state:
            blockers.append(f"{where} collector acknowledgement differs from queue proof")
    return blockers


def _intervention_artifact_blockers(
    document: Any,
    *,
    receipt_intervention: Any,
    configuration: Mapping[str, Any],
    barrier: Mapping[str, Any] | None,
    runtime_images: Mapping[str, Any] | None,
    posture: str,
    where: str,
) -> list[str]:
    """Replay one retained fault receipt against independent run artifacts.

    The producer's ``successful`` boolean is only a projection.  This checker
    reconstructs it from the exact command, target identity, sampled target
    states, shared barrier, recovery readiness, and joined controller thread.
    """

    blockers: list[str] = []
    fields = {
        "schemaVersion", "scenario", "service", "independentOfKieker",
        "intervalLabel", "functionalOutage", "measurementBarrier",
        "requestedHoldSeconds", "targetContainerId", "targetImage", "preState",
        "commandVector", "commandResult", "actualOnsetWall",
        "actualOnsetMonotonicOffsetSeconds", "actualOffsetWall",
        "actualOffsetMonotonicOffsetSeconds", "duringStateSamples",
        "recoveryAction", "sameTargetIdentity", "readiness", "postState",
        "interventionThreadJoined", "laterInterventionMutationObserved",
        "manifested", "recovered", "outageHeld", "successful", "error",
        "operational",
    }
    if not isinstance(document, dict) or set(document) != fields:
        return [f"{where} fields differ from intervention schema v3"]
    if document != receipt_intervention:
        blockers.append(f"{where} differs from receipt intervention projection")
    if document.get("schemaVersion") != 3:
        blockers.append(f"{where} schemaVersion is not 3")

    scenario = configuration.get("fault")
    service_by_scenario = {
        "auth-freeze": "auth",
        "persistence-crash": "persistence",
    }
    service = service_by_scenario.get(scenario)
    if service is None or document.get("scenario") != scenario or document.get("service") != service:
        blockers.append(f"{where} scenario/service differs from descriptor")
        return blockers

    project = configuration.get("composeProject")
    fault_at = configuration.get("faultAtSeconds")
    outage = configuration.get("outageSeconds")
    duration = configuration.get("measurementSeconds")
    if (not isinstance(project, str) or not project or not _integer(fault_at)
            or not _integer(outage, minimum=1) or not _integer(duration, minimum=1)
            or fault_at + outage >= duration):
        blockers.append(f"{where} descriptor timing/project inputs are invalid")
        return blockers

    if not isinstance(barrier, Mapping):
        blockers.append(f"{where} cannot bind a missing measurement barrier")
        return blockers
    try:
        barrier_created = _timestamp(barrier.get("createdAt"))
        barrier_at = _timestamp(barrier.get("barrierAt"))
        barrier_id = barrier.get("barrierId")
        barrier_epoch = barrier.get("barrierAtEpoch")
        if (not isinstance(barrier_id, str)
                or not re.fullmatch(r"barrier-[0-9a-f]{32}", barrier_id)
                or not _number(barrier_epoch)
                or abs(barrier_at.timestamp() - float(barrier_epoch)) > 1e-6
                or barrier.get("measurementSeconds") != duration):
            blockers.append(f"{where} retained measurement barrier is invalid")
    except (TypeError, ValueError, OverflowError, OSError) as exc:
        blockers.append(f"{where} retained measurement barrier is invalid: {exc}")
        return blockers
    measurement_end = barrier_at + timedelta(seconds=duration)

    target_services = (
        runtime_images.get("services")
        if isinstance(runtime_images, Mapping) else None
    )
    try:
        runtime_images_captured = _timestamp(
            runtime_images.get("capturedAt")
            if isinstance(runtime_images, Mapping) else None
        )
        if runtime_images_captured > barrier_created:
            blockers.append(
                f"{where} runtime-image target proof was captured after barrier creation")
    except (TypeError, ValueError, OverflowError) as exc:
        blockers.append(f"{where} runtime-image target timestamp is invalid: {exc}")
    target_runtime = (
        target_services.get(service)
        if isinstance(target_services, Mapping) else None
    )
    target_fields = {
        "containerId", "declaredImage", "containerImageId", "imageInspectId",
        "repoDigests",
    }
    if not isinstance(target_runtime, Mapping):
        blockers.append(f"{where} has no independent runtime-image target")
        return blockers
    expected_target = {key: target_runtime.get(key) for key in target_fields}
    target_id = document.get("targetContainerId")
    if (not isinstance(target_id, str) or not CONTAINER_ID_RE.fullmatch(target_id)
            or target_id != target_runtime.get("containerId")
            or document.get("targetImage") != expected_target):
        blockers.append(f"{where} target identity/image differs from runtime-images.json")

    intervention_barrier = document.get("measurementBarrier")
    expected_barrier_fields = {"id", "wall", "scheduledOnsetSeconds", "scheduledOnsetWall"}
    if not isinstance(intervention_barrier, dict) or set(intervention_barrier) != expected_barrier_fields:
        blockers.append(f"{where} intervention barrier fields differ")
    else:
        try:
            scheduled_wall = _timestamp(intervention_barrier.get("scheduledOnsetWall"))
            # F-ADH-070: the producer derives these walls from epoch-float
            # arithmetic; accept the driver's 1-microsecond rounding envelope
            # rather than exact datetime equality.
            if (intervention_barrier.get("id") != barrier_id
                    or abs((_timestamp(intervention_barrier.get("wall")) - barrier_at).total_seconds()) > 1e-6
                    or intervention_barrier.get("scheduledOnsetSeconds") != fault_at
                    or abs((scheduled_wall - (barrier_at + timedelta(seconds=fault_at))).total_seconds()) > 1e-6):
                blockers.append(f"{where} intervention barrier/timing differs from descriptor")
        except (TypeError, ValueError, OverflowError) as exc:
            blockers.append(f"{where} intervention barrier timestamp is invalid: {exc}")

    state_fields = {"exists", "running", "paused", "status", "returnCode"}

    def state_matches(value: Any, *, running: bool, paused: bool) -> bool:
        expected_status = "paused" if paused else "running" if running else "exited"
        return (
            isinstance(value, dict) and set(value) == state_fields
            and value.get("exists") is True and value.get("running") is running
            and value.get("paused") is paused
            and _integer(value.get("returnCode")) and value.get("returnCode") == 0
            and value.get("status") == expected_status
        )

    if not state_matches(document.get("preState"), running=True, paused=False):
        blockers.append(f"{where} pre-intervention target state is not ready")
    if not state_matches(document.get("postState"), running=True, paused=False):
        blockers.append(f"{where} post-intervention target state is not recovered")

    onset_action = "pause" if scenario == "auth-freeze" else "stop"
    recovery_action_name = "unpause" if scenario == "auth-freeze" else "start"
    expected_onset = _compose_service_action(project, posture, onset_action, service)
    expected_recovery = _compose_service_action(
        project, posture, recovery_action_name, service)
    command_fields = {"command", "returnCode", "stdout", "stderr"}

    def command_matches(value: Any, expected: list[str]) -> bool:
        return (
            isinstance(value, dict) and set(value) == command_fields
            and value.get("command") == expected
            and _integer(value.get("returnCode")) and value.get("returnCode") == 0
            and isinstance(value.get("stdout"), str)
            and isinstance(value.get("stderr"), str)
        )

    command_result = document.get("commandResult")
    if document.get("commandVector") != expected_onset or not command_matches(
        command_result, expected_onset
    ):
        blockers.append(f"{where} onset command/result differs from exact bounded vector")
    recovery_action = document.get("recoveryAction")
    recovery_result: Any = None
    if (not isinstance(recovery_action, dict)
            or set(recovery_action) != {"commandVector", "commandResult"}):
        blockers.append(f"{where} recovery action fields differ")
    else:
        recovery_result = recovery_action.get("commandResult")
        if (recovery_action.get("commandVector") != expected_recovery
                or not command_matches(recovery_result, expected_recovery)):
            blockers.append(f"{where} recovery command/result differs from exact bounded vector")

    onset_wall = offset_wall = readiness_wall = None
    onset_offset = offset_offset = readiness_offset = None
    try:
        onset_wall = _timestamp(document.get("actualOnsetWall"))
        offset_wall = _timestamp(document.get("actualOffsetWall"))
        onset_offset = document.get("actualOnsetMonotonicOffsetSeconds")
        offset_offset = document.get("actualOffsetMonotonicOffsetSeconds")
        if not _number(onset_offset) or not _number(offset_offset):
            raise ValueError("actual monotonic offsets are not finite numbers")
        onset_offset = float(onset_offset)
        offset_offset = float(offset_offset)
        actual_hold = offset_offset - onset_offset
        manifestation_lag_bound = (
            PERSISTENCE_MANIFESTATION_LAG_BOUND_SECONDS
            if scenario == "persistence-crash"
            else INTERVENTION_ONSET_LATE_TOLERANCE_SECONDS
        )
        if (onset_offset < fault_at
                or onset_offset > fault_at + manifestation_lag_bound):
            blockers.append(
                f"{where} actual manifestation exceeded its scenario-specific lag bound"
            )
        if (not math.isclose(actual_hold, float(outage), abs_tol=1.0)
                or actual_hold < outage):
            blockers.append(f"{where} actual sampled hold differs from descriptor")
        if not barrier_at <= onset_wall < offset_wall <= measurement_end:
            blockers.append(f"{where} actual intervention wall interval is outside measurement")
        if (abs((onset_wall - barrier_at).total_seconds() - onset_offset)
                > INTERVENTION_CLOCK_TOLERANCE_SECONDS
                or abs((offset_wall - barrier_at).total_seconds() - offset_offset)
                > INTERVENTION_CLOCK_TOLERANCE_SECONDS):
            blockers.append(f"{where} intervention wall/monotonic clocks disagree")
    except (TypeError, ValueError, OverflowError) as exc:
        blockers.append(f"{where} actual intervention interval is invalid: {exc}")

    samples = document.get("duringStateSamples")
    sample_fields = {"phase", "observedAtWall", "observedAtMonotonicOffsetSeconds", "state"}
    expected_phases = ["manifested", "hold-midpoint", "hold-end"]
    sample_times: list[datetime] = []
    sample_offsets: list[float] = []
    if not isinstance(samples, list) or len(samples) != 3:
        blockers.append(f"{where} must retain exactly three during-state samples")
    else:
        for index, sample in enumerate(samples):
            if not isinstance(sample, dict) or set(sample) != sample_fields:
                blockers.append(f"{where} state sample {index} fields differ")
                continue
            expected_running = scenario == "auth-freeze"
            expected_paused = scenario == "auth-freeze"
            if (sample.get("phase") != expected_phases[index]
                    or not state_matches(
                        sample.get("state"), running=expected_running,
                        paused=expected_paused,
                    )):
                blockers.append(f"{where} state sample {index} does not prove manifestation")
            try:
                observed_wall = _timestamp(sample.get("observedAtWall"))
                observed_offset = sample.get("observedAtMonotonicOffsetSeconds")
                if not _number(observed_offset):
                    raise ValueError("sample monotonic offset is not finite")
                sample_times.append(observed_wall)
                sample_offsets.append(float(observed_offset))
                if abs((observed_wall - barrier_at).total_seconds() - float(observed_offset)) > (
                    INTERVENTION_CLOCK_TOLERANCE_SECONDS
                ):
                    blockers.append(f"{where} state sample {index} wall/monotonic clocks disagree")
            except (TypeError, ValueError, OverflowError) as exc:
                blockers.append(f"{where} state sample {index} timestamp is invalid: {exc}")
        if len(sample_times) == 3 and len(sample_offsets) == 3:
            if not (sample_times[0] < sample_times[1] < sample_times[2]
                    and sample_offsets[0] < sample_offsets[1] < sample_offsets[2]
                    and sample_times[0] == onset_wall and sample_times[2] == offset_wall
                    and sample_offsets[0] == onset_offset and sample_offsets[2] == offset_offset):
                blockers.append(f"{where} state samples do not bind the actual interval")
            if (onset_offset is None
                    or abs(sample_offsets[1] - (onset_offset + outage / 2.0))
                    > INTERVENTION_CLOCK_TOLERANCE_SECONDS):
                blockers.append(f"{where} midpoint sample differs from the declared half-hold")

    readiness = document.get("readiness")
    readiness_fields = {
        "predicate", "observedAtWall", "observedAtMonotonicOffsetSeconds", "successful",
    }
    if not isinstance(readiness, dict) or set(readiness) != readiness_fields:
        blockers.append(f"{where} recovery readiness fields differ")
    else:
        try:
            readiness_wall = _timestamp(readiness.get("observedAtWall"))
            readiness_offset = readiness.get("observedAtMonotonicOffsetSeconds")
            if (not _number(readiness_offset)
                    or readiness.get("predicate") != "all-five-application-services-report-OK"
                    or readiness.get("successful") is not True
                    or offset_wall is None or offset_offset is None
                    or not offset_wall <= readiness_wall <= measurement_end
                    or float(readiness_offset) < offset_offset
                    or abs((readiness_wall - barrier_at).total_seconds()
                           - float(readiness_offset)) > INTERVENTION_CLOCK_TOLERANCE_SECONDS):
                blockers.append(f"{where} recovery readiness does not bind the intervention window")
            else:
                readiness_offset = float(readiness_offset)
        except (TypeError, ValueError, OverflowError) as exc:
            blockers.append(f"{where} recovery readiness timestamp is invalid: {exc}")

    operational = document.get("operational")
    operational_fields = {
        "controllerStartedAt", "controllerEndedAt", "commandResults",
        "actualHoldSeconds", "continuousTargetStateProven",
    }
    if not isinstance(operational, dict) or set(operational) != operational_fields:
        blockers.append(f"{where} operational fields differ")
    else:
        try:
            controller_started = _timestamp(operational.get("controllerStartedAt"))
            controller_ended = _timestamp(operational.get("controllerEndedAt"))
            hold = operational.get("actualHoldSeconds")
            if (onset_wall is None or readiness_wall is None or not _number(hold)
                    or controller_started > onset_wall or controller_ended < readiness_wall
                    or operational.get("commandResults") != [command_result, recovery_result]
                    or onset_offset is None or offset_offset is None
                    or not math.isclose(float(hold), offset_offset - onset_offset, abs_tol=1e-9)
                    or operational.get("continuousTargetStateProven") is not False):
                blockers.append(f"{where} operational projection does not replay")
        except (TypeError, ValueError, OverflowError) as exc:
            blockers.append(f"{where} operational timestamps are invalid: {exc}")

    if (document.get("independentOfKieker") is not True
            or document.get("intervalLabel") != "intervention-exposure"
            or document.get("functionalOutage") is not None
            or document.get("requestedHoldSeconds") != outage
            or document.get("sameTargetIdentity") is not True
            or document.get("interventionThreadJoined") is not True
            or document.get("laterInterventionMutationObserved") is not False
            or document.get("manifested") is not True
            or document.get("recovered") is not True
            or document.get("outageHeld") is not True
            or document.get("successful") is not True
            or document.get("error") is not None):
        blockers.append(f"{where} terminal scientific verdict does not replay")
    return blockers


def _posture_proof_blockers(
    document: Any,
    *,
    posture: str,
    receipt: Mapping[str, Any],
    where: str,
) -> list[str]:
    blockers: list[str] = []
    if not isinstance(document, dict) or set(document) != {"requested", "services"}:
        return [f"{where} fields differ from posture-proof protocol"]
    if document.get("requested") != posture:
        blockers.append(f"{where} requested posture differs from schedule")
    services = document.get("services")
    if not isinstance(services, dict) or set(services) != set(APP_SERVICES):
        blockers.append(f"{where} service set differs from the TeaStore application")
    else:
        for service in APP_SERVICES:
            item = services.get(service)
            # F-ADH-072: every posture now mounts a rendered aop.xml, so the
            # digest and the monitoring flag are both checked everywhere.
            expected_fields = {"aopSha256", "configuration", "writerInitializationFailed"}
            if not isinstance(item, dict) or set(item) != expected_fields:
                blockers.append(f"{where} {service} fields differ")
                continue
            if not isinstance(item.get("writerInitializationFailed"), bool):
                blockers.append(f"{where} {service} writer status is malformed")
            if posture != "none" and item.get("writerInitializationFailed") is not False:
                blockers.append(f"{where} {service} writer initialization failed")
            if not isinstance(item.get("aopSha256"), str) or not SHA256_RE.fullmatch(item["aopSha256"]):
                blockers.append(f"{where} {service} AOP digest is invalid")
            expected = f"kieker.monitoring.enabled={'false' if posture == 'none' else 'true'}"
            if item.get("configuration") != expected:
                blockers.append(f"{where} {service} runtime configuration differs")
        hashes = {item.get("aopSha256") for item in services.values() if isinstance(item, dict)}
        if len(hashes) != 1:
            blockers.append(f"{where} AOP digest differs across services")
    if receipt.get("postureProof") != document:
        blockers.append(f"{where} differs from receipt posture proof")
    return blockers


def _stream_summary_blockers(value: Any, where: str) -> list[str]:
    blockers: list[str] = []
    if not isinstance(value, dict) or set(value) != {"sha256", "bytes", "lineCount"}:
        return [f"{where} is not an exact sanitized stream proof"]
    if not isinstance(value.get("sha256"), str) or not SHA256_RE.fullmatch(value["sha256"]):
        blockers.append(f"{where} digest is invalid")
    if not _integer(value.get("bytes")) or not _integer(value.get("lineCount")):
        blockers.append(f"{where} byte/line counts are invalid")
    if value.get("bytes") == 0 and (
        value.get("lineCount") != 0 or value.get("sha256") != _sha256_bytes(b"")
    ):
        blockers.append(f"{where} empty-stream proof does not replay")
    if _integer(value.get("bytes"), minimum=1) and value.get("lineCount") == 0:
        blockers.append(f"{where} nonempty stream has a zero line count")
    return blockers


def _inventory_expected_commands(document: Mapping[str, Any], project: str, session: str) -> dict[str, list[str]]:
    docker = document.get("docker") if isinstance(document.get("docker"), Mapping) else {}
    containers = docker.get("containers") if isinstance(docker.get("containers"), list) else []
    networks = docker.get("networks") if isinstance(docker.get("networks"), list) else []
    volumes = docker.get("volumes") if isinstance(docker.get("volumes"), list) else []
    container_ids = sorted(
        row.get("id") for row in containers
        if isinstance(row, Mapping) and isinstance(row.get("id"), str) and row.get("id")
    )
    image_ids = sorted({
        row.get("runtimeImageId") for row in containers
        if isinstance(row, Mapping) and isinstance(row.get("runtimeImageId"), str)
        and row.get("runtimeImageId")
    })
    network_ids = sorted(
        row.get("id") for row in networks
        if isinstance(row, Mapping) and isinstance(row.get("id"), str) and row.get("id")
    )
    volume_names = sorted(
        row.get("name") for row in volumes
        if isinstance(row, Mapping) and isinstance(row.get("name"), str) and row.get("name")
    )
    label = f"label=com.docker.compose.project={project}"
    commands = {
        "project.containers": ["docker", "ps", "-aq", "--no-trunc", "--filter", label],
        "project.networks": ["docker", "network", "ls", "-q", "--no-trunc", "--filter", label],
        "project.volumes": ["docker", "volume", "ls", "-q", "--filter", label],
        "containers.list": ["docker", "ps", "-aq", "--no-trunc"],
        "containers.inspect": ["docker", "inspect", *container_ids],
        "images.inspect": ["docker", "image", "inspect", *image_ids],
        "compose.projects": ["docker", "compose", "ls", "--all", "--format", "json"],
        "networks.list": ["docker", "network", "ls", "-q", "--no-trunc"],
        "networks.inspect": ["docker", "network", "inspect", *network_ids],
        "volumes.list": ["docker", "volume", "ls", "-q"],
        "volumes.inspect": ["docker", "volume", "inspect", *volume_names],
        "docker.info": ["docker", "info", "--format", "{{json .}}"],
        "host.listeners": ["ss", "-H", "-lntup"],
        "host.processes": ["ps", "-eo", "pid=,ppid=,user=,lstart=,etimes=,args="],
        "sessions.exact": ["tmux", "has-session", "-t", session],
        "sessions.tmux": [
            "tmux", "list-sessions", "-F",
            "#{session_name}\t#{session_created}\t#{session_attached}",
        ],
        "sessions.screen": ["screen", "-ls"],
        "host.timeSync": ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
        "tool.dockerServer": ["docker", "version", "--format", "{{.Server.Version}}"],
        "tool.dockerCompose": ["docker", "compose", "version", "--short"],
        "tool.tmux": ["tmux", "-V"],
        "tool.screen": ["screen", "--version"],
        "tool.python": ["python3", "--version"],
        "tool.ss": ["ss", "--version"],
        "tool.setsid": ["setsid", "--version"],
        "tool.flock": ["flock", "--version"],
        "docker.daemonStarted": [
            "systemctl", "show", "docker", "--property=ActiveEnterTimestamp", "--value",
        ],
    }
    queue_states = docker.get("queueStates") if isinstance(docker.get("queueStates"), list) else []
    for row in queue_states:
        if isinstance(row, Mapping) and isinstance(row.get("containerId"), str):
            container_id = row["containerId"]
            commands[f"queue.{container_id}"] = [
                "docker", "exec", container_id, "rabbitmqctl", "list_queues",
                "name", "messages_ready", "messages_unacknowledged", "consumers",
            ]
    return commands


def _inventory_query_blockers(document: Mapping[str, Any], project: str, session: str) -> list[str]:
    blockers: list[str] = []
    proofs = document.get("queryProofs")
    expected = _inventory_expected_commands(document, project, session)
    permutation_prefixes = {
        "containers.inspect": ["docker", "inspect"],
        "networks.inspect": ["docker", "network", "inspect"],
        "volumes.inspect": ["docker", "volume", "inspect"],
    }
    if not isinstance(proofs, dict) or set(proofs) != {*expected, "docker.events"}:
        return ["fresh remote inventory sanitized query ledger is not exact"]
    for name, command in expected.items():
        proof = proofs.get(name)
        if not isinstance(proof, dict) or set(proof) != {"command", "returnCode", "stdout", "stderr"}:
            blockers.append(f"fresh remote inventory query proof is malformed: {name}")
            continue
        actual_command = proof.get("command")
        command_matches = actual_command == command
        if name in permutation_prefixes:
            prefix = permutation_prefixes[name]
            expected_identities = command[len(prefix):]
            actual_identities = (
                actual_command[len(prefix):]
                if isinstance(actual_command, list) and actual_command[:len(prefix)] == prefix
                else None
            )
            command_matches = (
                isinstance(actual_identities, list)
                and all(isinstance(value, str) for value in actual_identities)
                and len(actual_identities) == len(expected_identities)
                and len(set(actual_identities)) == len(actual_identities)
                and len(set(expected_identities)) == len(expected_identities)
                and set(actual_identities) == set(expected_identities)
            )
        if not command_matches or not _integer(proof.get("returnCode")):
            blockers.append(f"fresh remote inventory query command/result differs: {name}")
        blockers.extend(_stream_summary_blockers(proof.get("stdout"), f"inventory {name} stdout"))
        blockers.extend(_stream_summary_blockers(proof.get("stderr"), f"inventory {name} stderr"))
        allowed = {0, 1} if name in {"sessions.exact", "sessions.tmux", "sessions.screen"} else {0}
        if proof.get("returnCode") not in allowed:
            blockers.append(f"fresh remote inventory query did not pass: {name}")
    events = proofs.get("docker.events")
    if not isinstance(events, dict) or set(events) != {"command", "returnCode", "stdout", "stderr"}:
        blockers.append("fresh remote inventory Docker-events proof is malformed")
    else:
        command = events.get("command")
        valid_command = (
            isinstance(command, list) and len(command) == 8
            and command[:3] == ["docker", "events", "--since"]
            and command[4] == "--until" and command[6:] == ["--format", "{{json .}}"]
        )
        try:
            valid_command = valid_command and int(command[5]) - int(command[3]) == 3600
        except (TypeError, ValueError, IndexError):
            valid_command = False
        if not valid_command or events.get("returnCode") != 0:
            blockers.append("fresh remote inventory Docker-events command/result differs")
        blockers.extend(_stream_summary_blockers(events.get("stdout"), "inventory docker.events stdout"))
        blockers.extend(_stream_summary_blockers(events.get("stderr"), "inventory docker.events stderr"))
    resources = document.get("projectResources")
    if isinstance(resources, Mapping):
        empty_stream = {"sha256": _sha256_bytes(b""), "bytes": 0, "lineCount": 0}
        for kind in ("containers", "networks", "volumes"):
            if resources.get(kind) == [] and isinstance(proofs.get(f"project.{kind}"), Mapping) and (
                proofs[f"project.{kind}"].get("stdout") != empty_stream
            ):
                blockers.append(f"fresh remote inventory empty project {kind} query is not proven empty")
    time_proof = proofs.get("host.timeSync")
    expected_yes = {"sha256": _sha256_bytes(b"yes\n"), "bytes": 4, "lineCount": 1}
    if isinstance(time_proof, Mapping) and time_proof.get("stdout") != expected_yes:
        blockers.append("fresh remote inventory time-sync output does not prove yes")
    return blockers


def _terminal_inventory_blockers(
    document: Mapping[str, Any], *, target: str, campaign: str, project: str,
    release: str, completed: bool = True,
) -> list[str]:
    """Use the harness parser, then impose terminal-only quiet-host invariants."""

    blockers: list[str] = []
    try:
        harness = _load_module(
            Path(__file__).parents[1] / "execution" / "srv5_harness.py",
            "teastore_srv5_harness_terminal_replay",
        )
        payload = (json.dumps(dict(document), sort_keys=True, separators=(",", ":")) + "\n").encode()
        harness.ssh = lambda *_args, **_kwargs: SimpleNamespace(stdout=payload)
        replayed = harness.inventory(target, campaign, release=release)
        if replayed != dict(document):
            blockers.append("fresh remote inventory differs after authoritative harness replay")
    except Exception as exc:  # noqa: BLE001 - failure to replay the producer blocks evidence
        blockers.append(f"fresh remote inventory authoritative replay failed: {type(exc).__name__}: {exc}")
        return blockers

    session = f"teastore-{campaign}"
    blockers.extend(_inventory_query_blockers(document, project, session))
    if document.get("active") is not False or document.get("runningContainers") != []:
        blockers.append("fresh remote inventory retains an active session or running container")
    resources = document.get("projectResources")
    if not isinstance(resources, Mapping) or resources.get("project") != project or (
        resources.get("queryPassed") is not True
    ) or any(resources.get(kind) != [] for kind in ("containers", "networks", "volumes")):
        blockers.append("fresh remote inventory retains current-project resources")
    sessions = document.get("sessions")
    if not isinstance(sessions, Mapping) or sessions.get("all") != [] or sessions.get("experimentLike") != []:
        blockers.append("fresh remote inventory retains a tmux/screen session")
    processes = document.get("processes")
    if not isinstance(processes, Mapping) or processes.get("experimentLike") != []:
        blockers.append("fresh remote inventory retains an experiment process")
    paths = document.get("paths")
    if document.get("openWriters") != [] or not isinstance(paths, Mapping) or paths.get("allOpenWriters") != []:
        blockers.append("fresh remote inventory retains an open evidence writer")
    if isinstance(paths, Mapping):
        expected_tree_roots = {
            "resultTree": REMOTE_RESULTS,
            "releaseTree": REMOTE_RUNS,
        }
        for name, expected_root in expected_tree_roots.items():
            tree = paths.get(name)
            if not isinstance(tree, Mapping):
                blockers.append(f"fresh remote inventory {name} full-tree rollup is missing")
                continue
            if (tree.get("dialect") != "srv5-tree-metadata-v1"
                    or tree.get("algorithm") != "sha256"
                    or tree.get("complete") is not True):
                blockers.append(
                    f"fresh remote inventory {name} full-tree dialect is invalid or incomplete")
            if (tree.get("complete") is True
                    and tree.get("errorSha256") != _sha256_bytes(b"[]")):
                blockers.append(
                    f"fresh remote inventory {name} complete tree has a non-empty error digest")
            if tree.get("root") != expected_root:
                blockers.append(
                    f"fresh remote inventory {name} root differs from its exact host namespace")
            if (tree.get("stable") is not True or tree.get("errorCount") != 0
                    or tree.get("firstPassSha256") != tree.get("secondPassSha256")):
                blockers.append(
                    f"fresh remote inventory {name} full-tree rollup is unreadable or racy")
            if tree.get("rootKind") not in {"missing", "directory"}:
                blockers.append(
                    f"fresh remote inventory {name} root is not a directory or absent")
    ports = document.get("requiredPorts")
    if not isinstance(ports, Mapping) or set(ports) != {str(port) for port in REQUIRED_PORTS} or any(
        rows != [] for rows in ports.values()
    ):
        blockers.append("fresh remote inventory has occupied or malformed required ports")
    if document.get("timeSync") != {"synchronized": True}:
        blockers.append("fresh remote inventory does not prove synchronized time")
    classification = document.get("classification")
    docker = document.get("docker")
    collections = (
        docker.get("containers", []), docker.get("composeProjects", []),
        docker.get("networks", []), docker.get("volumes", []),
    ) if isinstance(docker, Mapping) else ([], [], [], [])
    forbidden = [
        row for collection in collections for row in collection
        if isinstance(row, Mapping) and row.get("classification") in {"foreign", "unknown"}
    ]
    if not isinstance(classification, Mapping) or classification.get("blocking") != [] or forbidden or (
        not isinstance(classification.get("counts"), Mapping)
        or classification["counts"].get("foreign") != 0
        or classification["counts"].get("unknown") != 0
    ):
        blockers.append("fresh remote inventory classification is not passing or contains foreign/unknown resources")
    if not isinstance(docker, Mapping) or docker.get("parseErrors") != [] or docker.get("queueStates") != []:
        blockers.append("fresh remote inventory retains Docker parse errors or a running broker queue")
    if isinstance(docker, Mapping):
        expected_running = [
            {
                "id": row.get("id"), "name": row.get("name"),
                "composeProject": row.get("composeProject"),
                "classification": row.get("classification"),
            }
            for row in docker.get("containers", [])
            if isinstance(row, Mapping) and isinstance(row.get("state"), Mapping)
            and row["state"].get("running") is True
        ]
        if document.get("runningContainers") != expected_running:
            blockers.append("fresh remote inventory running-container summary does not replay")
    expected_paths = (
        {"resultRoot": True, "log": True, "exit": True}
        if completed else {"resultRoot": False, "log": False, "exit": False}
    )
    if document.get("resultPaths") != expected_paths or document.get("releaseExists") is not completed:
        phase = "completed" if completed else "prelaunch-absent"
        blockers.append(f"fresh remote inventory does not prove {phase} result/release paths")
    if document.get("queryPassed") is not True or document.get("verdict") != "pass" or document.get("blockers") != []:
        blockers.append("fresh remote inventory did not pass its comprehensive gate")
    return blockers


def _preflight_record_blockers(
    record: Any,
    *,
    campaign: str,
    target: str,
    project: str,
    release: str,
    descriptor: Mapping[str, Any],
    descriptor_digest: str,
    configuration: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not isinstance(record, dict) or set(record) != {
        "schemaVersion", "recordedAt", "campaign", "target", "source", "preflight",
    }:
        return ["retained launch preflight fields differ from the exact persisted protocol"]
    if record.get("schemaVersion") != 1 or record.get("campaign") != campaign or record.get("target") != target:
        blockers.append("retained launch preflight identity differs from campaign")
    expected_source = {
        "frameworkCommit": configuration.get("frameworkCommit"),
        "sutReferenceCommit": configuration.get("sutReferenceCommit"),
        "descriptorId": descriptor.get("id"),
        "descriptorSha256": descriptor_digest,
    }
    if record.get("source") != expected_source:
        blockers.append("retained launch preflight source binding differs")
    preflight = record.get("preflight")
    if not isinstance(preflight, dict) or set(preflight) != {
        "schemaVersion", "campaign", "target", "settleSeconds", "stable",
        "first", "second", "verdict", "blockers",
    }:
        return [*blockers, "retained launch preflight wrapper differs from protocol"]
    if preflight.get("schemaVersion") != 2 or preflight.get("campaign") != campaign or (
        preflight.get("target") != target or preflight.get("settleSeconds") != 60
        or preflight.get("stable") is not True or preflight.get("verdict") != "pass"
        or preflight.get("blockers") != []
    ):
        blockers.append("retained launch preflight did not pass the exact 60-second gate")
    captured: list[datetime] = []
    for name in ("first", "second"):
        snapshot = preflight.get(name)
        if not isinstance(snapshot, Mapping):
            blockers.append(f"retained launch preflight {name} inventory is not an object")
            continue
        blockers.extend(
            f"preflight {name}: {item}"
            for item in _terminal_inventory_blockers(
                snapshot, target=target, campaign=campaign, project=project,
                release=release, completed=False,
            )
        )
        try:
            captured.append(_timestamp(snapshot.get("capturedAt")))
        except ValueError as exc:
            blockers.append(f"retained launch preflight {name} timestamp is invalid: {exc}")
    if isinstance(preflight.get("first"), Mapping) and isinstance(preflight.get("second"), Mapping) and (
        preflight["first"].get("stateFingerprint") != preflight["second"].get("stateFingerprint")
    ):
        blockers.append("retained launch preflight state fingerprints differ")
    try:
        recorded = _timestamp(record.get("recordedAt"))
    except ValueError as exc:
        blockers.append(f"retained launch preflight recordedAt is invalid: {exc}")
    else:
        if len(captured) == 2:
            if captured[1] < captured[0] or (captured[1] - captured[0]).total_seconds() < 60:
                blockers.append("retained launch preflight snapshots do not span the ordered settle interval")
            if recorded < captured[1]:
                blockers.append("retained launch preflight was recorded before its second snapshot")
    return blockers


def _execution_lease_blockers(
    lease: Any, *, campaign: str, remote_captured: datetime | None,
) -> list[str]:
    blockers: list[str] = []
    fields = {"schemaVersion", "scope", "lockPath", "campaign", "launcherPid", "acquisition", "release"}
    if not isinstance(lease, dict) or set(lease) != fields:
        return ["execution lease fields differ from the exact protocol"]
    if lease.get("schemaVersion") != 1 or lease.get("scope") != "fb14srv5:teastore-performance" or (
        lease.get("lockPath") != HOST_LEASE_PATH or lease.get("campaign") != campaign
    ) or not _integer(lease.get("launcherPid"), minimum=1):
        blockers.append("execution lease identity/scope is invalid")
    acquisition = lease.get("acquisition")
    acquisition_fields = {"attemptedAt", "acquired", "acquiredAt", "returnCode", "mechanism"}
    acquired_at: datetime | None = None
    if not isinstance(acquisition, dict) or set(acquisition) != acquisition_fields:
        blockers.append("execution lease acquisition fields differ")
    else:
        try:
            attempted_at = _timestamp(acquisition.get("attemptedAt"))
            acquired_at = _timestamp(acquisition.get("acquiredAt"))
            if acquired_at < attempted_at:
                blockers.append("execution lease acquisition predates its attempt")
        except ValueError as exc:
            blockers.append(f"execution lease acquisition timestamp is invalid: {exc}")
        if acquisition.get("acquired") is not True or acquisition.get("returnCode") != 0 or (
            acquisition.get("mechanism") != "flock-nonblocking-fd"
        ):
            blockers.append("execution lease was not successfully acquired")
    release = lease.get("release")
    release_fields = {"requestedAt", "unlockReturnCode", "verificationReturnCode", "observed", "mechanism"}
    if not isinstance(release, dict) or set(release) != release_fields:
        blockers.append("execution lease release fields differ")
    else:
        released_at: datetime | None = None
        try:
            released_at = _timestamp(release.get("requestedAt"))
            if acquired_at is not None and released_at < acquired_at:
                blockers.append("execution lease release predates acquisition")
        except ValueError as exc:
            blockers.append(f"execution lease release timestamp is invalid: {exc}")
        if release.get("unlockReturnCode") != 0 or release.get("verificationReturnCode") != 0 or (
            release.get("observed") is not True
        ) or release.get("mechanism") != "unlock-close-and-nonblocking-reacquire":
            blockers.append("execution lease release was not observed and verified")
        if released_at is not None and remote_captured is not None and remote_captured < released_at:
            blockers.append("fresh remote inventory predates execution lease release")
    return blockers


def _run_blockers(
    root: Path,
    run_id: str,
    posture: str,
    configuration: dict[str, Any],
    performance_validator: Any,
    native_validator: Any,
    campaign_runner: Any,
    fixed_load: Any,
    resource_validator: Any,
) -> list[str]:
    blockers: list[str] = []
    run = root / run_id
    receipt = _json_object(run / "receipt.json", blockers, f"{run_id} receipt")
    if receipt is None:
        return blockers
    receipt_schema = receipt.get("schemaVersion")
    evidence_label = configuration.get("evidenceLabel")
    if evidence_label == "candidate-evidence" and receipt_schema != 2:
        blockers.append(f"{run_id} candidate receipt schemaVersion is not 2")
    elif receipt_schema == 1 and evidence_label != "smoke-validation":
        blockers.append(f"{run_id} historical v1 receipt is not diagnostic smoke")
    elif receipt_schema not in {1, 2}:
        blockers.append(f"{run_id} receipt schemaVersion is unsupported")
    if receipt.get("runId") != run_id or receipt.get("posture") != posture:
        blockers.append(f"{run_id} receipt identity differs from schedule")
    runtime_images_path = run / "runtime-images.json"
    runtime_images = _json_object(runtime_images_path, blockers, f"{run_id} runtime images")
    runtime_images_digest: str | None = None
    if runtime_images is not None:
        try:
            runtime_images_digest = _sha256_bytes(runtime_images_path.read_bytes())
        except OSError as exc:
            blockers.append(f"{run_id} runtime image digest unreadable: {exc}")
        try:
            blockers.extend(_runtime_image_blockers(
                runtime_images, configuration["composeProject"], f"{run_id} runtime images"))
        except Exception as exc:  # noqa: BLE001 - malformed proof must block, never abort validation
            blockers.append(f"{run_id} runtime image replay failed: {type(exc).__name__}: {exc}")
    queue_path = run / "queue-proof.json"
    child_processes_path = run / "child-processes.json"
    spool_path = run / "kieker-amqp.spool"
    try:
        queue_digest = _sha256_bytes(queue_path.read_bytes())
    except OSError:
        queue_digest = None
    try:
        child_processes_digest = _sha256_bytes(child_processes_path.read_bytes())
    except OSError:
        child_processes_digest = None
    source = receipt.get("source")
    expected_source = {
        "frameworkCommit": configuration.get("frameworkCommit"),
        "sutReferenceCommit": configuration.get("sutReferenceCommit"),
        "dirty": False,
        "selectionId": configuration.get("selectionId"),
        "selectionSourceSha256": configuration.get("selectionSourceSha256"),
        "activationManifestSha256": configuration.get("activationManifestSha256") if posture == "selected" else None,
        "descriptorId": configuration.get("descriptorId"),
        "descriptorSha256": configuration.get("descriptorSha256"),
        "evidenceLabel": configuration.get("evidenceLabel"),
        "runtimeImagesSha256": runtime_images_digest,
        "queueProofSha256": queue_digest,
        "childProcessesSha256": child_processes_digest,
    }
    if receipt_schema == 2:
        try:
            expected_source["spoolSha256"] = _sha256_bytes(spool_path.read_bytes())
        except OSError:
            expected_source["spoolSha256"] = None
        try:
            native = campaign_runner.native_collector_module()
            runtime_aliases = native.load_runtime_host_service_map(runtime_images_path)
            _, attribution_digest = native.frozen_attribution_configuration(
                runtime_aliases,
            )
            expected_source["collectorAttributionConfigurationSha256"] = (
                attribution_digest
            )
        except Exception as exc:  # noqa: BLE001 - attribution proof is required
            expected_source["collectorAttributionConfigurationSha256"] = None
            blockers.append(
                f"{run_id} collector attribution proof replay failed: "
                f"{type(exc).__name__}: {exc}"
            )
    if source != expected_source:
        blockers.append(f"{run_id} source/descriptor binding differs from schedule")
    try:
        performance = performance_validator.validate(receipt)
        if not isinstance(performance, dict) or performance.get("verdict") != "pass":
            blockers.append(f"{run_id} performance receipt blocked: {performance.get('blockers') if isinstance(performance, dict) else performance}")
    except Exception as exc:  # noqa: BLE001 - validation errors must fail closed
        blockers.append(f"{run_id} performance receipt validator failed: {type(exc).__name__}: {exc}")
    canonicality = receipt.get("canonicality")
    if not isinstance(canonicality, dict) or canonicality.get("blockers") != [] or (
        canonicality.get("label") != configuration.get("evidenceLabel")
    ):
        blockers.append(f"{run_id} canonicality label/blockers differ from descriptor")
    window = receipt.get("window")
    if not isinstance(window, dict) or window.get("warmupSeconds") != configuration.get("warmupSeconds") or (
        window.get("measurementSeconds") != configuration.get("measurementSeconds")
    ):
        blockers.append(f"{run_id} measurement window differs from schedule")
    workload = receipt.get("workload")
    if not isinstance(workload, dict) or workload.get("concurrency") != configuration.get("concurrency"):
        blockers.append(f"{run_id} workload concurrency differs from schedule")
    intervention = receipt.get("intervention")
    if configuration.get("fault") == "none":
        if intervention is not None:
            blockers.append(f"{run_id} contains an unscheduled intervention")
    elif not isinstance(intervention, dict) or intervention.get("scenario") != configuration.get("fault") or (
        intervention.get("successful") is not True
    ):
        blockers.append(f"{run_id} intervention differs from scheduled fault")

    workload_artifact = _json_object(
        run / "workload.json", blockers, f"{run_id} workload artifact")
    if workload_artifact is not None:
        try:
            blockers.extend(_workload_artifact_blockers(
                workload_artifact,
                configuration=configuration,
                receipt=receipt,
                duration_seconds=configuration["measurementSeconds"],
                where=f"{run_id} workload artifact",
            ))
            blockers.extend(_journey_evidence_blockers(
                run, workload_artifact,
                ledger_name="journey-ledger.jsonl",
                fixed_load=fixed_load,
                receipt=receipt,
                where=f"{run_id} measurement journey evidence",
            ))
        except Exception as exc:  # noqa: BLE001 - malformed evidence must block
            blockers.append(f"{run_id} workload replay failed: {type(exc).__name__}: {exc}")
    warmup_artifact = _json_object(
        run / "warmup.json", blockers, f"{run_id} warmup artifact")
    if warmup_artifact is not None:
        try:
            blockers.extend(_workload_artifact_blockers(
                warmup_artifact,
                configuration=configuration,
                receipt=None,
                duration_seconds=configuration["warmupSeconds"],
                where=f"{run_id} warmup artifact",
            ))
            blockers.extend(_journey_evidence_blockers(
                run, warmup_artifact,
                ledger_name="warmup-journey-ledger.jsonl",
                fixed_load=fixed_load,
                receipt=None,
                where=f"{run_id} warmup journey evidence",
            ))
            if warmup_artifact.get("failed") != 0:
                blockers.append(f"{run_id} warmup artifact contains failed journeys")
        except Exception as exc:  # noqa: BLE001 - malformed evidence must block
            blockers.append(f"{run_id} warmup replay failed: {type(exc).__name__}: {exc}")
    cost_window = configuration.get("fault") == "none"
    if cost_window and isinstance(workload_artifact, Mapping):
        schema_version = workload_artifact.get("schemaVersion")
        failed = workload_artifact.get("failed")
        timed_out = workload_artifact.get("timedOut", 0)
        if (schema_version in {1, 2}
                and (failed != 0 or (schema_version == 2 and timed_out != 0))):
            blockers.append(
                f"{run_id} no-fault cost measurement contains unsuccessful journeys"
            )
    resources_path = run / "resources.json"
    resources_artifact: Mapping[str, Any] | None = None
    if cost_window:
        resources_artifact = _json_object(
            resources_path, blockers, f"{run_id} resources artifact")
        if resources_artifact is not None:
            try:
                resource_digest = _sha256_bytes(resources_path.read_bytes())
                workload_schedule = (
                    workload_artifact.get("schedule", {})
                    if isinstance(workload_artifact, Mapping) else {}
                )
                blockers.extend(_resources_artifact_blockers(
                    resources_artifact,
                    receipt=receipt,
                    where=f"{run_id} resources artifact",
                    resource_validator=resource_validator,
                    expected_barrier_id=(
                        workload_schedule.get("barrierId")
                        if isinstance(workload_schedule, Mapping) else None
                    ),
                    expected_start_epoch=(
                        workload_artifact.get("startedAtEpoch")
                        if isinstance(workload_artifact, Mapping) else None
                    ),
                    expected_duration_seconds=configuration["measurementSeconds"],
                    artifact_sha256=resource_digest,
                    offered_journeys=(
                        workload_artifact.get("offered")
                        if isinstance(workload_artifact, Mapping) else None
                    ),
                    expected_container_identity=(
                        {
                            service: runtime_images["services"][service]["containerId"]
                            for service in APP_SERVICES
                        }
                        if isinstance(runtime_images, Mapping)
                        and isinstance(runtime_images.get("services"), Mapping)
                        and all(
                            isinstance(runtime_images["services"].get(service), Mapping)
                            and isinstance(
                                runtime_images["services"][service].get("containerId"), str
                            )
                            for service in APP_SERVICES
                        )
                        else None
                    ),
                ))
            except Exception as exc:  # noqa: BLE001 - malformed evidence must block
                blockers.append(
                    f"{run_id} resource replay failed: {type(exc).__name__}: {exc}"
                )
    else:
        if resources_path.exists():
            blockers.append(f"{run_id} effect run contains a forbidden cost artifact")
        if (receipt.get("analysisKind") != "effect"
                or receipt.get("resourceUse") != "diagnostic-only"
                or receipt.get("resources") is not None):
            blockers.append(f"{run_id} effect/resource claim boundary differs")
    queue_proof_for_barrier = _json_object(
        run / "queue-proof.json", blockers, f"{run_id} queue proof for barrier")
    barrier_artifact: Mapping[str, Any] | None = None
    if (isinstance(workload_artifact, Mapping)
            and workload_artifact.get("schemaVersion") == 2):
        barrier_path = run / "measurement-barrier.json"
        barrier_artifact = _json_object(
            barrier_path, blockers, f"{run_id} measurement barrier")
        if barrier_artifact is not None:
            try:
                blockers.extend(_measurement_barrier_blockers(
                    barrier_artifact,
                    workload=workload_artifact,
                    resources=resources_artifact,
                    receipt=receipt,
                    queue_proof=queue_proof_for_barrier,
                    duration_seconds=configuration["measurementSeconds"],
                    where=f"{run_id} measurement barrier",
                ))
                artifacts = receipt.get("candidateArtifacts")
                if not isinstance(artifacts, Mapping) or artifacts.get(
                    "measurementBarrierSha256"
                ) != _sha256_bytes(barrier_path.read_bytes()):
                    blockers.append(
                        f"{run_id} measurement barrier digest differs from receipt"
                    )
            except Exception as exc:  # noqa: BLE001 - malformed barriers must block
                blockers.append(
                    f"{run_id} measurement barrier replay failed: {type(exc).__name__}: {exc}"
                )
    intervention_path = run / "intervention.json"
    if cost_window:
        if intervention_path.exists():
            blockers.append(f"{run_id} no-fault cost run contains a forbidden intervention artifact")
    else:
        intervention_artifact = _json_object(
            intervention_path, blockers, f"{run_id} intervention artifact")
        if intervention_artifact is not None:
            try:
                blockers.extend(_intervention_artifact_blockers(
                    intervention_artifact,
                    receipt_intervention=receipt.get("intervention"),
                    configuration=configuration,
                    barrier=barrier_artifact,
                    runtime_images=runtime_images,
                    posture=posture,
                    where=f"{run_id} intervention artifact",
                ))
            except Exception as exc:  # noqa: BLE001 - malformed evidence must block
                blockers.append(
                    f"{run_id} intervention replay failed: {type(exc).__name__}: {exc}"
                )
    retained_posture = _json_object(
        run / "posture-proof.json", blockers, f"{run_id} posture proof")
    if retained_posture is not None:
        try:
            blockers.extend(_posture_proof_blockers(
                retained_posture, posture=posture, receipt=receipt,
                where=f"{run_id} posture proof"))
        except Exception as exc:  # noqa: BLE001 - malformed evidence must block
            blockers.append(f"{run_id} posture-proof replay failed: {type(exc).__name__}: {exc}")

    traces_path = run / "traces.json"
    try:
        events = _read_json(traces_path)
        if not isinstance(events, list):
            raise ValueError("traces are not a list")
        telemetry_bytes = traces_path.stat().st_size
    except (OSError, ValueError, json.JSONDecodeError, DuplicateKeyError) as exc:
        blockers.append(f"{run_id} traces unreadable: {type(exc).__name__}: {exc}")
        events = None
        telemetry_bytes = None
    if isinstance(events, list):
        signatures = {
            event.get("signature_sha1") if isinstance(event, dict) else None
            for event in events
        }
        observed = {
            "records": len(events),
            "bytes": telemetry_bytes,
            "uniqueSignatures": len(signatures),
        }
        telemetry = receipt.get("telemetry")
        if not isinstance(telemetry, dict) or any(telemetry.get(key) != value for key, value in observed.items()):
            blockers.append(f"{run_id} telemetry count/bytes/signatures differ from traces.json")
        collector_stderr = run / "collector.stderr"
        collector_stats: dict[str, Any] | None = None
        try:
            collector_stats = campaign_runner.collector_stats(
                collector_stderr.read_text(encoding="utf-8"),
                require_attribution_binding=receipt_schema == 2,
                runtime_images_path=(runtime_images_path if receipt_schema == 2 else None),
            )
            if not isinstance(telemetry, dict) or telemetry.get("collectorStats") != collector_stats:
                blockers.append(f"{run_id} collector stats differ from retained stderr summary")
            blockers.extend(_collector_telemetry_blockers(
                events,
                telemetry,
                collector_stats,
                posture=posture,
                effect_contract=not cost_window,
                where=f"{run_id} collector telemetry",
                closure_groups=(
                    retained_posture.get("closureGroups")
                    if isinstance(retained_posture, Mapping) else None),
                exposure_tolerance=receipt.get("exposureTolerance"),
            ))
        except Exception as exc:  # noqa: BLE001 - a missing or ambiguous summary must fail closed
            blockers.append(f"{run_id} collector summary replay failed: {type(exc).__name__}: {exc}")
        if receipt_schema == 2:
            blockers.extend(_durable_spool_blockers(
                spool_path,
                runtime_images_path,
                events,
                telemetry,
                collector_stats,
                campaign_runner,
                where=run_id,
            ))
        message_hashes = [
            event.get("message_sha1") if isinstance(event, dict) else None
            for event in events
        ]
        invalid_message_hashes = [
            value for value in message_hashes
            if not isinstance(value, str) or not SHA1_RE.fullmatch(value)
        ]
        if invalid_message_hashes:
            blockers.append(f"{run_id} traces contain invalid native message_sha1 values")
        if posture == "none":
            if events != [] or observed["records"] != 0 or observed["uniqueSignatures"] != 0:
                blockers.append(f"{run_id} none posture telemetry is not exactly empty")
        else:
            try:
                native = native_validator.validate(events)
                if not isinstance(native, dict) or native.get("verdict") != "pass":
                    blockers.append(f"{run_id} native Kieker contract blocked: {native.get('blockers') if isinstance(native, dict) else native}")
            except Exception as exc:  # noqa: BLE001 - validation errors must fail closed
                blockers.append(f"{run_id} native Kieker validator failed: {type(exc).__name__}: {exc}")

    queue_proof = _json_object(queue_path, blockers, f"{run_id} queue proof")
    if queue_proof is not None:
        try:
            blockers.extend(_queue_proof_blockers(
                queue_proof, configuration["composeProject"], f"{run_id} queue proof"))
            measurement = queue_proof.get("measurement")
            purge = queue_proof.get("purge")
            if not isinstance(measurement, dict) or not isinstance(purge, dict) or not isinstance(
                purge.get("after"), dict
            ) or not all(isinstance(measurement.get(name), dict) for name in (
                "before", "consumerAtStart", "after"
            )):
                raise ValueError("queue proof cannot be normalized into the receipt")
            expected_queue = {
                "purgedBefore": purge["after"].get("messages") == 0,
                "messagesBefore": measurement["before"].get("messages"),
                "messagesAfter": measurement["after"].get("messages"),
                "exclusiveConsumer": measurement["consumerAtStart"].get("consumers") == 1,
                "proofSha256": queue_digest,
            }
            if receipt.get("queue") != expected_queue:
                blockers.append(f"{run_id} receipt queue differs from retained queue proof")
        except Exception as exc:  # noqa: BLE001 - malformed proof must block, never abort validation
            blockers.append(f"{run_id} queue proof replay failed: {type(exc).__name__}: {exc}")

    child_processes = _json_object(
        child_processes_path, blockers, f"{run_id} child processes")
    if child_processes is not None:
        try:
            expected_workload_return_code = _expected_fixed_load_return_code(
                workload_artifact, effect_contract=not cost_window,
            )
            blockers.extend(_child_process_blockers(
                child_processes, receipt.get("processes"), f"{run_id} child processes",
                expect_performance_probe=cost_window,
                expected_workload_return_code=expected_workload_return_code,
            ))
        except Exception as exc:  # noqa: BLE001 - malformed proof must block, never abort validation
            blockers.append(f"{run_id} child-process replay failed: {type(exc).__name__}: {exc}")

    project = configuration["composeProject"]
    ownership = _json_object(run / "ownership-preflight.json", blockers, f"{run_id} ownership preflight")
    if ownership is not None:
        if set(ownership) != {"composeProject", "resourcesBefore"} or ownership.get("composeProject") != project:
            blockers.append(f"{run_id} ownership preflight is not bound to the exact project")
        blockers.extend(_resource_blockers(ownership.get("resourcesBefore"), project, f"{run_id} preflight"))
    down = _json_object(run / "down-command.json", blockers, f"{run_id} down command")
    if down is not None:
        if set(down) != {"schemaVersion", "command", "returnCode", "stdout", "stderr"} or (
            down.get("schemaVersion") != 1 or down.get("command") != _compose_down(project, posture) or
            not _integer(down.get("returnCode")) or down.get("returnCode") != 0 or
            not isinstance(down.get("stdout"), str) or not isinstance(down.get("stderr"), str)
        ):
            blockers.append(f"{run_id} down command is not exact and successful")
    teardown = _json_object(run / "teardown.json", blockers, f"{run_id} teardown")
    if teardown is not None:
        blockers.extend(_resource_blockers(teardown, project, f"{run_id} teardown"))
    expected_teardown = {
        "downCommand": down,
        "projectResources": teardown,
        "projectClean": down is not None and teardown is not None and not (
            _resource_blockers(teardown, project, f"{run_id} teardown replay")
        ),
    }
    if receipt.get("teardown") != expected_teardown or expected_teardown["projectClean"] is not True:
        blockers.append(f"{run_id} receipt teardown differs from retained exact proof")
    return blockers


def validate_campaign(
    root: Path,
    descriptor: Path | Mapping[str, Any],
    status: Mapping[str, Any],
    remote_state: Mapping[str, Any],
    *,
    expected_manifest_sha256: str | None = None,
    require_fresh_remote: bool = True,
) -> dict[str, Any]:
    """Re-read an entire fetched campaign and return one terminal verdict."""

    blockers: list[str] = []
    root = Path(root).resolve()
    descriptor_digest = ""
    if isinstance(descriptor, Mapping):
        blockers.append("descriptor must be the retained campaign-descriptor.json path")
    elif Path(descriptor).resolve() != root / "campaign-descriptor.json":
        blockers.append("descriptor path is not the retained campaign-descriptor.json")
    try:
        descriptor_doc, descriptor_digest = _descriptor(descriptor)
        expected_configuration, descriptor_blockers = _descriptor_configuration(descriptor_doc, descriptor_digest)
        blockers.extend(descriptor_blockers)
    except Exception as exc:  # noqa: BLE001 - a malformed descriptor must return a blocked verdict
        blockers.append(f"descriptor unreadable: {type(exc).__name__}: {exc}")
        descriptor_doc, expected_configuration = {}, {}

    validation_items = descriptor_doc.get("validation")
    validation_set = set(validation_items) if isinstance(validation_items, list) and all(
        isinstance(item, str) for item in validation_items
    ) else set()
    observed_deadline_gates = validation_set & DEADLINE_VALIDATION_GATES
    deadline_required = observed_deadline_gates == DEADLINE_VALIDATION_GATES
    if observed_deadline_gates and not deadline_required:
        blockers.append("descriptor enables only part of the deadline/admission validation contract")

    campaign = root.name
    if not ID_RE.fullmatch(campaign):
        blockers.append("evidence root name is not a safe campaign identifier")
    compose_project = f"obst-{campaign}".lower()
    if len(compose_project) > 63:
        blockers.append("derived Compose project exceeds the supported identifier length")
    expected_runs: list[dict[str, Any]] = []
    if expected_configuration and _integer(expected_configuration.get("blocks"), minimum=1) and _integer(
        expected_configuration.get("seed"), minimum=0
    ) and isinstance(expected_configuration.get("postures"), list) and expected_configuration["postures"] and all(
        posture in POSTURES for posture in expected_configuration["postures"]
    ):
        expected_configuration["composeProject"] = compose_project
        rng = random.Random(expected_configuration.get("seed"))
        for block in range(1, expected_configuration.get("blocks", 0) + 1):
            postures = list(expected_configuration.get("postures", []))
            rng.shuffle(postures)
            expected_runs.extend({"block": block, "posture": posture} for posture in postures)
    elif expected_configuration:
        expected_configuration["composeProject"] = compose_project
        blockers.append("descriptor cannot produce a typed run schedule")
    expected_ids = [f"b{row['block']:02d}-{row['posture']}" for row in expected_runs]
    expected_count = len(expected_ids)

    if not isinstance(status, Mapping):
        blockers.append("terminal status is not an object")
    else:
        if status.get("campaign") != campaign:
            blockers.append("terminal status campaign differs from evidence root")
        if status.get("active") is not False:
            blockers.append("terminal status is still active or malformed")
        if status.get("exitCode") not in (0, "0") or isinstance(status.get("exitCode"), bool):
            blockers.append("terminal status exit code is not exactly zero")
        if not _integer(status.get("receipts"), minimum=0) or status.get("receipts") != expected_count:
            blockers.append("terminal status receipt count differs from descriptor")
        if not _integer(status.get("expected"), minimum=0) or status.get("expected") != expected_count:
            blockers.append("terminal status expected count differs from descriptor")
    retained_status = _json_object(root / "terminal-status.json", blockers, "retained terminal status")
    if retained_status is not None and (not isinstance(status, Mapping) or retained_status != dict(status)):
        blockers.append("retained terminal status differs from supplied status proof")

    schedule = _json_object(root / "schedule.json", blockers, "schedule")
    configuration: dict[str, Any] = {}
    if schedule is not None:
        if set(schedule) != {"configuration", "runs"} or not isinstance(schedule.get("configuration"), dict) or not isinstance(
            schedule.get("runs"), list
        ):
            blockers.append("schedule shape is invalid")
        else:
            configuration = schedule["configuration"]
            dynamic_fields = {"frameworkCommit", "selectionSourceSha256", "activationManifestSha256", "composeProject"}
            required_fields = set(expected_configuration) | dynamic_fields
            if set(configuration) != required_fields:
                blockers.append("schedule configuration fields differ from descriptor-bound contract")
            for key, value in expected_configuration.items():
                if configuration.get(key) != value:
                    blockers.append(f"schedule configuration differs from descriptor: {key}")
            if not isinstance(configuration.get("frameworkCommit"), str) or not COMMIT_RE.fullmatch(
                configuration.get("frameworkCommit", "")
            ):
                blockers.append("schedule framework commit is not a full Git object")
            for field in ("selectionSourceSha256", "activationManifestSha256"):
                if not isinstance(configuration.get(field), str) or not SHA256_RE.fullmatch(configuration.get(field, "")):
                    blockers.append(f"schedule {field} is not a SHA-256 digest")
            if schedule.get("runs") != expected_runs:
                blockers.append("schedule runs/order differ from descriptor seed and design")

    owner = _json_object(root / "harness-owner.json", blockers, "harness owner")
    if owner is not None:
        blockers.extend(_harness_owner_blockers(
            owner,
            campaign=campaign,
            descriptor=descriptor_doc,
            descriptor_digest=descriptor_digest,
            configuration=configuration,
            expected_count=expected_count,
            deadline_required=deadline_required,
        ))
    deadline_cleanup: dict[str, Any] | None = None
    if deadline_required:
        if isinstance(owner, Mapping):
            blockers.extend(_runtime_admission_blockers(
                root, owner, descriptor_doc, expected_count=expected_count,
            ))
        else:
            blockers.append("runtime admission cannot bind a missing harness owner")
        deadline_cleanup = _json_object(
            root / "deadline-cleanup.json", blockers, "deadline cleanup")
        if deadline_cleanup is not None and isinstance(owner, Mapping) and isinstance(status, Mapping):
            blockers.extend(_deadline_cleanup_blockers(
                deadline_cleanup, owner=owner, campaign=campaign, status=status,
            ))
    launch_preflight = _json_object(
        root / "preflight.json", blockers, "retained launch preflight")
    if launch_preflight is not None and isinstance(owner, Mapping):
        target = descriptor_doc.get("target")
        release = owner.get("release")
        if isinstance(target, str) and isinstance(release, str):
            blockers.extend(_preflight_record_blockers(
                launch_preflight,
                campaign=campaign,
                target=target,
                project=compose_project,
                release=release,
                descriptor=descriptor_doc,
                descriptor_digest=descriptor_digest,
                configuration=configuration,
            ))
        else:
            blockers.append("retained launch preflight cannot bind invalid owner/descriptor identity")

    receipts = sorted(root.rglob("receipt.json")) if root.is_dir() else []
    actual_receipt_paths = [path.relative_to(root).as_posix() for path in receipts]
    expected_receipt_paths = sorted(f"{run_id}/receipt.json" for run_id in expected_ids)
    if actual_receipt_paths != expected_receipt_paths:
        blockers.append(
            f"receipt IDs differ from schedule: actual={actual_receipt_paths}, expected={expected_receipt_paths}"
        )
    if configuration and actual_receipt_paths == expected_receipt_paths:
        try:
            performance_validator = _load_validator("performance_receipt.py", "teastore_performance_receipt_terminal")
            native_validator = _load_validator("native_kieker.py", "teastore_native_kieker_terminal")
            campaign_runner = _load_module(
                Path(__file__).parents[1] / "execution" / "performance_campaign.py",
                "teastore_performance_campaign_terminal",
            )
            fixed_load = _load_module(
                Path(__file__).parents[1] / "workload" / "fixed_load.py",
                "teastore_fixed_load_terminal",
            )
            resource_validator = _load_module(
                Path(__file__).parents[1] / "collectors" / "performance_probe_v3.py",
                "teastore_resource_probe_terminal",
            )
            posture_by_id = {f"b{row['block']:02d}-{row['posture']}": row["posture"] for row in expected_runs}
            for run_id in expected_ids:
                blockers.extend(_run_blockers(
                    root, run_id, posture_by_id[run_id], configuration,
                    performance_validator, native_validator, campaign_runner, fixed_load,
                    resource_validator,
                ))
        except Exception as exc:  # noqa: BLE001 - loading a required checker must fail closed
            blockers.append(f"required receipt validator could not load: {type(exc).__name__}: {exc}")

    final = _json_object(root / "final-hygiene.json", blockers, "final hygiene")
    final_captured: datetime | None = None
    if final is not None:
        if set(final) != {"schemaVersion", "capturedAt", "composeProject", "projectResources", "projectClean"} or (
            final.get("schemaVersion") != 1 or final.get("composeProject") != compose_project or final.get("projectClean") is not True
        ):
            blockers.append("final hygiene shape/project/verdict is invalid")
        blockers.extend(_resource_blockers(final.get("projectResources"), compose_project, "final hygiene"))
        try:
            final_captured = _timestamp(final.get("capturedAt"))
        except ValueError as exc:
            blockers.append(f"final hygiene timestamp is invalid: {exc}")

    remote_captured: datetime | None = None
    if not isinstance(remote_state, Mapping):
        blockers.append("fresh remote state is not an object")
    else:
        target = descriptor_doc.get("target")
        release = owner.get("release") if isinstance(owner, Mapping) else ""
        if not isinstance(target, str) or not isinstance(release, str):
            blockers.append("fresh remote inventory lacks descriptor/owner binding inputs")
        else:
            blockers.extend(_terminal_inventory_blockers(
                remote_state, target=target, campaign=campaign,
                project=compose_project, release=release,
            ))
        try:
            remote_captured = _timestamp(remote_state.get("capturedAt"))
            age = (datetime.now(timezone.utc) - remote_captured).total_seconds()
            if require_fresh_remote and (age < -5 or age > MAX_REMOTE_AGE_SECONDS):
                blockers.append(f"fresh remote state proof is stale or future-dated: ageSeconds={age:.3f}")
        except ValueError as exc:
            blockers.append(f"fresh remote state timestamp is invalid: {exc}")
    if final_captured is not None and remote_captured is not None and remote_captured < final_captured:
        blockers.append("fresh remote proof predates final campaign hygiene")
    retained_remote = _json_object(root / "remote-final-state.json", blockers, "retained remote final state")
    if retained_remote is not None and (
        not isinstance(remote_state, Mapping) or retained_remote != dict(remote_state)
    ):
        blockers.append("retained remote final state differs from supplied remote proof")

    execution_lease = _json_object(
        root / "execution-lease.json", blockers, "execution lease")
    if execution_lease is not None:
        blockers.extend(_execution_lease_blockers(
            execution_lease, campaign=campaign, remote_captured=remote_captured))
        if deadline_required and deadline_cleanup is not None:
            try:
                cleanup_completed = _timestamp(deadline_cleanup["authorization"]["completedAt"])
                lease_released = _timestamp(execution_lease["release"]["requestedAt"])
                if lease_released < cleanup_completed:
                    blockers.append("execution lease was released before deadline cleanup completed")
            except (KeyError, TypeError, ValueError) as exc:
                blockers.append(f"deadline cleanup/lease ordering is invalid: {exc}")

    manifest_report = verify_manifest(root)
    if manifest_report["verdict"] != "pass":
        blockers.extend(manifest_report["blockers"])
    if expected_manifest_sha256 is not None:
        if (not isinstance(expected_manifest_sha256, str)
                or not SHA256_RE.fullmatch(expected_manifest_sha256)):
            blockers.append("external manifest anchor is not a SHA-256 digest")
        elif manifest_report.get("manifestSha256") != expected_manifest_sha256:
            blockers.append("content manifest differs from the external manifest anchor")
    return {
        "schemaVersion": 1,
        "verdict": "pass" if not blockers else "blocked",
        "campaign": campaign,
        "descriptorId": descriptor_doc.get("id"),
        "descriptorSha256": expected_configuration.get("descriptorSha256"),
        "evidenceLabel": expected_configuration.get("evidenceLabel"),
        "promotionEligible": False,
        "pathGroundTruthStatus": "unsupported",
        "expectedReceipts": expected_count,
        "observedReceipts": len(receipts),
        "manifest": manifest_report,
        "blockers": blockers,
    }
