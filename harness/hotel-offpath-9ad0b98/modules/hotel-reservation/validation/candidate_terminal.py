#!/usr/bin/env python3
"""Deterministically validate one Hotel candidate cell or the whole campaign.

The validator only reads retained artifacts.  It never contacts Docker,
Jaeger, or the experiment host, and it never upgrades candidate evidence to
canonical evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, NoReturn


ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "modules" / "hotel-reservation"
MANIFEST = "content-manifest.json"
CELL_TERMINAL = "cell-terminal.json"
CAMPAIGN_TERMINAL = "campaign-terminal.json"
REQUIRED_COMMON = (
    "cell-contract.json",
    "source-proof.json",
    "application-build-proof.json",
    "compose-rendered.yml",
    "opportunity-plan.json",
    "opportunity-ledger.jsonl",
    "workload-reconciliation.json",
    "application.log",
    "jaeger-raw.json",
    "traces-normalized.json",
    "capture-terminal.json",
    "emissions.json",
    "cost-cgroup.json",
    "system-samples.json",
    "tcp-snapshots.json",
    "docker-events.jsonl",
    "docker-events.json",
    "correlation.json",
    "posture-proof.json",
    "images.json",
    "nuisance.json",
    "cell-cleanup.json",
)
SHA256 = __import__("re").compile(r"^[0-9a-f]{64}$")
APPLICATION_SERVICES = (
    "frontend", "search", "geo", "rate", "reservation", "profile",
    "user", "recommendation", "review", "attractions",
)


def collection_scope(contract: Mapping[str, Any]) -> tuple:
    """The services an epoch collects: the ten application services, plus what the epoch declares (consul in
    hotel-offpath-v1), read from the cell contract's study epoch (the admitted plan fixes it)."""
    return APPLICATION_SERVICES + tuple(runtime_policy.collection_extra_services(contract.get("studyEpoch")))


COMPOSE_SERVICES = (
    "consul", "frontend", "search", "geo", "rate", "reservation", "profile",
    "user", "recommendation", "review", "attractions", "jaeger",
    "memcached-rate", "memcached-review", "memcached-profile", "memcached-reserve",
    "mongodb-geo", "mongodb-profile", "mongodb-rate", "mongodb-review",
    "mongodb-attractions", "mongodb-recommendation", "mongodb-reservation", "mongodb-user",
)
PATH_REMAP: tuple[Path, Path] | None = None


class TerminalError(ValueError):
    """Retained candidate evidence is incomplete, stale, or inconsistent."""


def _reject_constant(value: str) -> NoReturn:
    raise TerminalError(f"non-finite JSON value is forbidden: {value}")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise TerminalError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_bytes(payload: bytes, where: str) -> Any:
    try:
        return json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except TerminalError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TerminalError(f"invalid JSON in {where}: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, allow_nan=False, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TerminalError(f"value is not canonical JSON: {exc}") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _runtime_path(value: Any) -> Path:
    path = Path(str(value))
    if path.is_absolute() and PATH_REMAP is not None:
        remote, local = PATH_REMAP
        if path == remote or remote in path.parents:
            return (local / path.relative_to(remote)).resolve()
    return (ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def configure_path_remap(remote_root: Path, local_root: Path) -> None:
    """Permit byte-preserving local replay of one fetched remote campaign."""
    global PATH_REMAP
    remote = Path(remote_root)
    local = Path(local_root).resolve(strict=True)
    if not remote.is_absolute() or not local.is_dir():
        raise TerminalError("terminal replay path remap is invalid")
    PATH_REMAP = (remote, local)


def _load(name: str, relative: str):
    path = MODULE / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise TerminalError(f"cannot load validator {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


workload = _load("hotel_candidate_terminal_workload", "workload/candidate_search.py")
resources = _load("hotel_candidate_terminal_resources", "collectors/candidate_resources.py")
witness = _load("hotel_candidate_terminal_witness", "witness/candidate_evidence.py")
compiler = _load("hotel_candidate_terminal_compiler", "execution/candidate_pilot.py")
jaeger_normalizer = _load(
    "hotel_candidate_terminal_jaeger_normalizer", "normalizers/jaeger.py"
)
# D6: the unsupported-posture claim ceiling is declared runtime policy, so the
# terminal validator reads it instead of restating the list as a literal.
runtime_policy = _load(
    "hotel_candidate_terminal_runtime_policy", "execution/candidate_runtime.py"
)


def posture_ceiling() -> dict[str, Any]:
    try:
        return runtime_policy.posture_ceiling()
    except Exception as exc:  # noqa: BLE001 - any policy defect fails the replay
        raise TerminalError(f"declared posture ceiling is unavailable: {exc}") from exc


def posture_ceiling_for_plan(plan_sha256: Any) -> tuple[dict[str, Any], int]:
    """Ceiling and scheduled cell count bound to one compiled-plan digest.

    The ceiling is versioned, never edited: a retained cell is replayed against
    the ceiling its gate-pinned plan digest carried, so widening the ceiling for
    a new campaign leaves every banked cell validating byte-for-byte.
    """
    if not isinstance(plan_sha256, str):
        raise TerminalError("cell contract does not pin a compiled plan digest")
    try:
        return runtime_policy.posture_ceiling_for_plan(plan_sha256)
    except Exception as exc:  # noqa: BLE001 - any policy defect fails the replay
        raise TerminalError(f"declared posture ceiling is unavailable: {exc}") from exc


def posture_ceiling_for(contract: Mapping[str, Any]) -> dict[str, Any]:
    return posture_ceiling_for_plan(contract.get("compiledPlanCanonicalSha256"))[0]


def _read_file(path: Path, where: str) -> bytes:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise TerminalError(f"{where} is not a regular non-symlink file")
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        payload = path.read_bytes()
        after = path.lstat()
        if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise TerminalError(f"{where} changed while being read")
        if len(payload) != before.st_size:
            raise TerminalError(f"{where} size changed while being read")
        return payload
    except TerminalError:
        raise
    except OSError as exc:
        raise TerminalError(f"cannot read {where}: {exc}") from exc


def _json(path: Path, where: str) -> dict[str, Any]:
    value = strict_json_bytes(_read_file(path, where), where)
    if not isinstance(value, dict):
        raise TerminalError(f"{where} must contain one JSON object")
    return value


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    payload = _read_file(path, path.relative_to(root).as_posix())
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _evidence_files(root: Path) -> list[Path]:
    if root.is_symlink() or not root.is_dir():
        raise TerminalError("candidate evidence root is not a regular directory")
    files = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise TerminalError(f"candidate evidence contains a symlink: {path.relative_to(root)}")
        if path in {root / MANIFEST, root / CELL_TERMINAL, root / CAMPAIGN_TERMINAL}:
            continue
        if path.is_file():
            files.append(path)
        elif not path.is_dir():
            raise TerminalError(f"candidate evidence contains a non-regular entry: {path.relative_to(root)}")
    return files


def write_manifest(root: Path) -> dict[str, Any]:
    """Publish a one-time content seal without replacing an existing history."""
    root = root.resolve(strict=True)
    path = root / MANIFEST
    if path.exists() or path.is_symlink():
        raise TerminalError("refusing to replace candidate content manifest")
    document = {
        "schemaVersion": 1,
        "algorithm": "sha256",
        "files": [_file_record(item, root) for item in _evidence_files(root)],
    }
    payload = json.dumps(document, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".content-manifest.", dir=root)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return document


def verify_manifest(root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    path = root / MANIFEST
    document = _json(path, "candidate content manifest")
    if set(document) != {"schemaVersion", "algorithm", "files"} or (
        document.get("schemaVersion") != 1 or document.get("algorithm") != "sha256"
    ):
        raise TerminalError("candidate content manifest header differs")
    rows = document.get("files")
    if not isinstance(rows, list):
        raise TerminalError("candidate content manifest rows are missing")
    declared: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}:
            raise TerminalError("candidate content manifest row fields differ")
        relative = row.get("path")
        if (
            not isinstance(relative, str) or not relative or "\\" in relative
            or Path(relative).is_absolute() or Path(relative).as_posix() != relative
            or any(part in {"", ".", ".."} for part in Path(relative).parts)
            or relative in {MANIFEST, CELL_TERMINAL, CAMPAIGN_TERMINAL}
            or relative in declared
            or type(row.get("bytes")) is not int or row["bytes"] < 0
            or SHA256.fullmatch(str(row.get("sha256"))) is None
        ):
            raise TerminalError("candidate content manifest row is unsafe or malformed")
        declared[relative] = row
    observed = {item.relative_to(root).as_posix(): item for item in _evidence_files(root)}
    if set(observed) != set(declared):
        raise TerminalError("candidate content manifest membership differs")
    for relative, path_item in observed.items():
        if _file_record(path_item, root) != declared[relative]:
            raise TerminalError(f"candidate content manifest digest differs: {relative}")
    return {
        "verdict": "pass",
        "manifestSha256": hashlib.sha256(_read_file(path, MANIFEST)).hexdigest(),
        "fileCount": len(rows),
    }


POSTURE_CLASSIFICATION = {
    "none": "logs-fatal-sampler-off-tracer-disabled",
    "metrics": "logs-info-sampler-on-tracer-disabled",
    "selected": "logs-info-sampler-on-tracer-frontend-only",
    "full": "logs-info-sampler-on-tracer-full-sampling",
}


def _posture(document: Any, contract: Mapping[str, Any]) -> None:
    posture = contract["runKey"]["posture"]
    expected = {name: "1" if compiler.traces(posture, name) else "0" for name in APPLICATION_SERVICES}
    if (
        not isinstance(document, dict)
        or set(document) != {
            "schemaVersion", "requested", "expectedSampleRatio", "services",
            "tracedServices", "logLevel", "metricSampler",
            "sourceWorkDisabled", "classification",
        }
        or document.get("schemaVersion") != 3
        or document.get("requested") != posture
        or document.get("expectedSampleRatio") != expected
        or document.get("services") != expected
        or document.get("tracedServices") != sorted(compiler.TRACED_SERVICES_BY_POSTURE.get(posture, ()))
        or document.get("logLevel") != compiler.LOG_LEVEL_BY_POSTURE.get(posture)
        or document.get("metricSampler") is not (posture in compiler.SAMPLER_POSTURES)
        or document.get("sourceWorkDisabled") is not False
        or document.get("classification") != POSTURE_CLASSIFICATION.get(posture)
    ):
        raise TerminalError("posture proof differs or overclaims source work")


def _images(document: Any, contract: Mapping[str, Any]) -> None:
    scope = collection_scope(contract)
    if not isinstance(document, dict) or set(document) != {
        "schemaVersion", "project", "materializedSourceSha256", "applicationImageId",
        "applicationImageReference", "runtimeInputsSha256", "containers",
    }:
        raise TerminalError("runtime image receipt fields differ")
    rows = document.get("containers")
    by_service = {
        row.get("service"): row for row in rows or [] if isinstance(row, dict)
    }
    if (
        document.get("schemaVersion") != 1
        or document.get("project") != contract["project"]
        or SHA256.fullmatch(str(document.get("materializedSourceSha256"))) is None
        or __import__("re").fullmatch(
            r"sha256:[0-9a-f]{64}", str(document.get("applicationImageId", ""))
        ) is None
        or document.get("applicationImageReference") != (
            "obsplacement/hotel-reservation-candidate:"
            + document["materializedSourceSha256"][:16]
        )
        or SHA256.fullmatch(str(document.get("runtimeInputsSha256"))) is None
        or not isinstance(rows, list)
        or len(rows) != len(scope)
        or set(by_service) != set(scope)
        or any(
            set(row) != {"service", "containerId", "project", "imageId"}
            or row["project"] != contract["project"]
            # The ten application containers run the one application image.  An extra collected service (consul in
            # hotel-offpath-v1) runs its own pinned image: a sha256 image ID that is not the application image's.
            or (row["imageId"] != document["applicationImageId"] if row["service"] in APPLICATION_SERVICES
                else (__import__("re").fullmatch(r"sha256:[0-9a-f]{64}", str(row["imageId"])) is None
                      or row["imageId"] == document["applicationImageId"]))
            or __import__("re").fullmatch(r"[0-9a-f]{64}", str(row["containerId"])) is None
            for row in by_service.values()
        )
    ):
        raise TerminalError("application image provenance or project scope differs")


def _cleanup(document: Any, contract: Mapping[str, Any]) -> None:
    if document != {
        "schemaVersion": 1,
        "kind": "hotel-candidate-cell-cleanup-v1",
        "project": contract["project"],
        "unpauseAttempted": True,
        "composeDownReturnCode": 0,
        "ownedResourcesRemaining": {"containers": [], "networks": [], "volumes": []},
        "foreignResourcesMutated": False,
        "artifactDeletionAttempted": False,
    }:
        raise TerminalError("cell cleanup is incomplete or outside ownership")


def _nuisance(document: Any, contract: Mapping[str, Any]) -> dict[str, Any]:
    try:
        condition = runtime_policy.host_condition_for_plan(contract.get("compiledPlanCanonicalSha256"))
    except Exception as exc:  # noqa: BLE001 - any policy defect fails the replay
        raise TerminalError(f"declared host condition is unavailable: {exc}") from exc
    if condition["foreignProject"] is None:
        return _nuisance_v2(document, contract, condition)
    # Host condition v1 (dps_training_k co-tenant), kept verbatim for the banked cells.
    if (
        not isinstance(document, dict)
        or set(document) != {
            "schemaVersion", "kind", "factors", "before", "after",
            "foreignMutationActions", "absoluteCostOrLatencyCanonical",
        }
        or document["schemaVersion"] != 1
        or document["kind"] != "hotel-srv4-cell-nuisance-v1"
        or document["factors"] != ["host-load", "dps_training_k"]
        or contract.get("nuisanceFactors") != ["host-load", "dps_training_k"]
        or document["foreignMutationActions"] != []
        or document["absoluteCostOrLatencyCanonical"] is not False
        or contract.get("absoluteCostOrLatencyCanonical") is not False
    ):
        raise TerminalError("srv4 nuisance identity or candidate-only ceiling differs")
    for label in ("before", "after"):
        row = document[label]
        if (
            not isinstance(row, dict)
            or set(row) != {
                "capturedAt", "loadAverage", "foreignProject", "foreignConfigPath",
                "foreignStateCounts", "foreignIdentityRows", "foreignResources",
            }
            or row["foreignProject"] != "dps_training_k"
            or row["foreignConfigPath"] != (
                "/home/cgade/tests_2/dps.training_k/backend/dps_training_k/docker-compose.yml"
            )
            or row["foreignStateCounts"] != {"running": 5}
            or not isinstance(row["foreignIdentityRows"], list)
            # 2026-09-18: 6 -> 5. This counts the SAME containers as the
            # foreignStateCounts pin re-pinned in e06c466/8fa74f5; the co-tenant
            # removed one container that sat in `created` and had never run. Both
            # pins describe one fact and must move together. This was the sixth
            # site and it aborted campaign #5 at cell 1.
            or len(row["foreignIdentityRows"]) != 5
            or not isinstance(row["loadAverage"], list)
            or len(row["loadAverage"]) != 3
            or any(not isinstance(value, (int, float)) or value < 0 for value in row["loadAverage"])
            or not isinstance(row["foreignResources"], dict)
            or not row["foreignResources"].get("containers")
        ):
            raise TerminalError("srv4 host-load or dps_training_k nuisance facts differ")
    if any(
        document["before"][key] != document["after"][key]
        for key in ("foreignConfigPath", "foreignStateCounts", "foreignIdentityRows", "foreignResources")
    ):
        raise TerminalError("foreign dps_training_k resource identity changed during a cell")
    return {
        "factors": document["factors"],
        "absoluteCostOrLatencyCanonical": False,
        "foreignResourcesCanonicalSha256": canonical_sha256(
            document["before"]["foreignResources"]
        ),
    }


def _nuisance_v2(
    document: Any, contract: Mapping[str, Any], condition: Mapping[str, Any],
) -> dict[str, Any]:
    """Host condition v2: no foreign Compose project or container, verified and
    recorded before and after the cell; the pooling boundary against the 103
    co-tenant cells travels inside the evidence."""
    factors = list(condition["factors"])
    if (
        not isinstance(document, dict)
        or set(document) != {
            "schemaVersion", "kind", "factors", "hostCondition", "poolingBoundary",
            "notPoolableWith",
            "before", "after", "foreignMutationActions", "absoluteCostOrLatencyCanonical",
        }
        or document["schemaVersion"] != 2
        or document["kind"] != "hotel-srv4-cell-nuisance-v2"
        or document["factors"] != factors
        or document["hostCondition"] != condition["id"]
        or document["poolingBoundary"] != condition["poolingBoundary"]
        # enforced, not merely tolerated: the boundary is only checkable if the
        # digest list in the cell matches what the policy's retired records say.
        or document["notPoolableWith"] != runtime_policy.not_poolable_with()
        or contract.get("nuisanceFactors") != factors
        or contract.get("foreignProject") is not None
        or document["foreignMutationActions"] != []
        or document["absoluteCostOrLatencyCanonical"] is not False
        or contract.get("absoluteCostOrLatencyCanonical") is not False
    ):
        raise TerminalError("host-condition identity or candidate-only ceiling differs")
    for label in ("before", "after"):
        row = document[label]
        if (
            not isinstance(row, dict)
            or set(row) != {"capturedAt", "loadAverage", "foreignProject", "foreignRows"}
            or row["foreignProject"] is not None
            or row["foreignRows"] != []
            or not isinstance(row["loadAverage"], list)
            or len(row["loadAverage"]) != 3
            or any(not isinstance(value, (int, float)) or value < 0 for value in row["loadAverage"])
        ):
            raise TerminalError("host-load or foreign-absence facts differ")
    return {
        "factors": factors,
        "absoluteCostOrLatencyCanonical": False,
        "hostCondition": condition["id"],
        "poolingBoundary": condition["poolingBoundary"],
    }


def _reconciliation(
    document: Any, ledger_validation: Mapping[str, Any], plan: Mapping[str, Any],
    ledger_path: Path, offered: int,
) -> None:
    if (
        not isinstance(document, dict)
        or document.get("schemaVersion") != 1
        or document.get("kind") != "hotel-candidate-workload-reconciliation-v1"
        or document.get("offered") != offered
        or document.get("terminalSettled") != offered
        or document.get("completed", -1) + document.get("failed", -1) != offered
        or document.get("planSha256") != plan["planCanonicalSha256"]
        or document.get("ledgerSha256") != hashlib.sha256(
            _read_file(ledger_path, "opportunity ledger")
        ).hexdigest()
        or document.get("validation") != ledger_validation
    ):
        raise TerminalError("workload reconciliation differs from terminal ledger")


def _source_provenance(root: Path, images: Mapping[str, Any]) -> None:
    proof = _json(root / "source-proof.json", "candidate source proof")
    build = _json(root / "application-build-proof.json", "application build proof")
    lock = _json(MODULE / "deployment/runtime-inputs.lock.json", "runtime input lock")
    expected_patch = hashlib.sha256(
        _read_file(MODULE / "witness/hotel-candidate-witness.patch", "candidate source patch")
    ).hexdigest()
    expected_inputs = hashlib.sha256(
        _read_file(MODULE / "deployment/runtime-inputs.lock.json", "runtime input lock")
    ).hexdigest()
    expected_manifest = hashlib.sha256(
        _read_file(MODULE / "witness/patch-manifest.json", "candidate patch manifest")
    ).hexdigest()
    if (
        proof.get("upstreamCommit") != "6ecb09706140f8730b5385c08f1386c654c3c526"
        or proof.get("sourceCheckoutClean") is not True
        or proof.get("candidatePatchId") != "hotel-lmt-pilot-witness-and-log-fatal-v1"
        or proof.get("candidatePatchSha256") != expected_patch
        or proof.get("patchManifestSha256") != expected_manifest
        or proof.get("runtimeInputsSha256") != expected_inputs
        or proof.get("runtimeImages") != lock["images"]
        or SHA256.fullmatch(str(proof.get("materializedSourceSha256"))) is None
        or set(build) != {
            "schemaVersion", "imageReference", "imageId",
            "materializedSourceSha256", "builderReference", "runtimeInputsSha256",
        }
        or build.get("schemaVersion") != 1
        or build.get("materializedSourceSha256") != proof["materializedSourceSha256"]
        or build.get("runtimeInputsSha256") != expected_inputs
        or build.get("builderReference") != lock["images"]["builder"]
        or build.get("imageReference") != images.get("applicationImageReference")
        or build.get("imageId") != images.get("applicationImageId")
        or images.get("materializedSourceSha256") != proof["materializedSourceSha256"]
        or images.get("runtimeInputsSha256") != expected_inputs
    ):
        raise TerminalError("candidate source, runtime inputs, build, and container image are not transitively bound")


def _compose_provenance(
    root: Path, contract: Mapping[str, Any], images: Mapping[str, Any],
) -> None:
    document = strict_json_bytes(
        _read_file(root / "compose-rendered.yml", "rendered Compose"),
        "rendered Compose",
    )
    services = document.get("services") if isinstance(document, dict) else None
    if not isinstance(services, dict) or set(services) != set(COMPOSE_SERVICES):
        raise TerminalError("rendered Compose services are missing")
    lock = _json(MODULE / "deployment/runtime-inputs.lock.json", "runtime input lock")
    app_services = {
        "frontend", "search", "geo", "rate", "reservation", "profile",
        "user", "recommendation", "review", "attractions",
    }
    expected_images = {
        **{name: images["applicationImageReference"] for name in app_services},
        "consul": lock["images"]["consul"],
        "jaeger": lock["images"]["jaeger"],
        **{
            name: lock["images"]["memcached"]
            for name in services if name.startswith("memcached-")
        },
        **{
            name: lock["images"]["mongo"]
            for name in services if name.startswith("mongodb-")
        },
    }
    posture = contract["runKey"]["posture"]
    environment_expected = {
        **lock["applicationEnvironment"], "LOG_LEVEL": compiler.LOG_LEVEL_BY_POSTURE[posture],
    }
    try:
        published = {
            (
                name, int(row.get("target")), int(row.get("published")),
                row.get("host_ip"), row.get("protocol", "tcp"),
            )
            for name, service in services.items()
            for row in (service.get("ports") or [])
            if isinstance(row, dict)
        }
        port_rows = sum(
            len(service.get("ports") or []) for service in services.values()
        )
    except (TypeError, ValueError) as exc:
        raise TerminalError(
            f"rendered Compose published ports are malformed: {exc}"
        ) from exc
    if (
        set(expected_images) - set(services)
        or any(services[name].get("image") != value for name, value in expected_images.items())
        or any(services[name].get("container_name") is not None for name in services)
        or len(published) != port_rows
        or published != {
            ("frontend", 5000, 35005, "127.0.0.1", "tcp"),
            ("jaeger", 16686, 36685, "127.0.0.1", "tcp"),
        }
        or any(
            not isinstance(services[name].get("environment"), dict)
            or str(services[name]["environment"].get("JAEGER_SAMPLE_RATIO"))
            != ("1" if compiler.traces(posture, name) else "0")
            or str(services[name]["environment"].get("JAEGER_DISABLED")).lower()
            != ("false" if compiler.traces(posture, name) else "true")
            or any(
                str(services[name]["environment"].get(key)) != value
                for key, value in environment_expected.items()
                if key != "MEMC_TIMEOUT" or name in {"review", "attractions"}
            )
            for name in app_services
        )
    ):
        raise TerminalError("rendered Compose image pins, environment, or isolation differ")


FAULT_EVENT_ACTIONS = {
    "search-pause": ["pause", "unpause"], "reservation-pause": ["pause", "unpause"],
    "profile-cpu-throttle": ["update", "update"], "rate-net-delay": [],
    "consul-pause": ["pause", "unpause"],
}
# hotel-offpath-v1: the off-path pause target.  Its manifestation is two legs: the receipt's container read back as
# paused (witness.validate_fault_receipt) and these docker events on the target's own container id, checked below
# in _system before any protocol gate runs; the route outage is recorded and not required.
OFFPATH_FAULT_TARGETS = {"consul-pause": "consul"}


def _system(root: Path, contract: Mapping[str, Any], plan: Mapping[str, Any],
            images: Mapping[str, Any], timing: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """LMT+S always-on evidence: cost cgroups, system samples, TCP snapshots, events."""
    if timing is None:
        timing = _cell_timing(contract)
    services = {row["service"]: row["containerId"] for row in images["containers"]}
    scope = collection_scope(contract)
    measurement = float(timing["measurementSeconds"])
    start = float(plan["barrierMonotonic"])
    cost = _json(root / "cost-cgroup.json", "cost cgroup evidence")
    daemons = ("docker.service", "containerd.service")
    if (
        cost.get("schemaVersion") != 1 or cost.get("kind") != "hotel-lmt-cost-cgroup-v1"
        or set(cost.get("containersCpuSeconds", {})) != set(scope)
        or set(cost.get("daemonsCpuSeconds", {})) != set(daemons)
        or any(not isinstance(v, (int, float)) or v < 0 for v in
               list(cost["containersCpuSeconds"].values()) + list(cost["daemonsCpuSeconds"].values()))
        or not isinstance(cost.get("windowSeconds"), (int, float))
        or not measurement - 1.0 <= cost["windowSeconds"] <= measurement + 2.0
        or not -0.5 <= cost["start"]["monotonic"] - start <= 1.0
    ):
        raise TerminalError("cost cgroup evidence differs from the admitted window")
    # Re-derive every figure from the retained edges (integer usec deltas and one float
    # subtraction each: identical on the 3.9 host and a 3.13 replay).
    try:
        edges_ok = (
            cost["windowSeconds"] == cost["end"]["monotonic"] - cost["start"]["monotonic"]
            and all(cost["containersCpuSeconds"][name]
                    == (cost["end"]["containersUsageUsec"][name] - cost["start"]["containersUsageUsec"][name]) / 1e6
                    for name in scope)
            and all(cost["daemonsCpuSeconds"][unit]
                    == (cost["end"]["daemonsUsageUsec"][unit] - cost["start"]["daemonsUsageUsec"][unit]) / 1e6
                    for unit in daemons)
        )
    except (KeyError, TypeError) as exc:
        raise TerminalError(f"cost cgroup edges are malformed: {exc}") from exc
    if not edges_ok:
        raise TerminalError("cost cgroup figures differ from their own retained edges")
    samples = _json(root / "system-samples.json", "system samples")
    rows = samples.get("samples") if isinstance(samples, dict) else None
    if (
        samples.get("kind") != "hotel-lmt-system-samples-v1" or not isinstance(rows, list)
        or len(rows) < timing["minimumSystemSamples"]
        or any(set(row.get("services", {})) != set(scope) for row in rows)
    ):
        raise TerminalError("system samples are incomplete")
    tcp = _json(root / "tcp-snapshots.json", "TCP snapshots")
    snaps = tcp.get("snapshots") if isinstance(tcp, dict) else None
    if (
        not isinstance(snaps, list) or [row.get("label") for row in snaps] != ["pre-fault", "during-fault"]
        or any(set(row.get("services", {})) != set(scope) for row in snaps)
    ):
        raise TerminalError("TCP snapshots are incomplete")
    summary = _json(root / "docker-events.json", "docker events summary")
    lines = [line for line in _read_file(root / "docker-events.jsonl", "docker events").decode().splitlines() if line.strip()]
    events = [strict_json_bytes(line.encode(), "docker event") for line in lines]
    if summary.get("kind") != "hotel-lmt-docker-events-v1" or summary.get("rows") != len(events):
        raise TerminalError("docker events summary differs from the retained stream")
    fault = contract.get("fault")
    target = {**compiler.FAULT_TARGETS, **OFFPATH_FAULT_TARGETS}.get(fault) if fault else None
    # Every pause/unpause/update in the project's stream counts, on any container:
    # a cost cell admits none, a fault cell exactly its own actions on its target.
    mutations = [
        event for event in events if event.get("Action") in {"pause", "unpause", "update"}
    ]
    actions = [
        event.get("Action") for event in mutations
        if target is not None and event.get("Actor", {}).get("ID") == services.get(target)
    ]
    if len(actions) != len(mutations) or actions != (FAULT_EVENT_ACTIONS[fault] if fault else []):
        raise TerminalError("docker events do not record exactly the admitted fault actions")
    # F-ADH-069: builtin sum() over floats differs between the 3.9 host and a 3.12+ replay.
    # The container aggregate stays the ten application containers (comparable across epochs); an epoch's extra
    # collected services (consul in hotel-offpath-v1) are reported beside it, never inside it.
    result = {"costContainersCpuSeconds": resources._sequential_sum(
                [cost["containersCpuSeconds"][name] for name in sorted(cost["containersCpuSeconds"])
                 if name in APPLICATION_SERVICES]),
              "costDaemonsCpuSeconds": resources._sequential_sum(
                [cost["daemonsCpuSeconds"][name] for name in sorted(cost["daemonsCpuSeconds"])]),
              "systemSamples": len(rows), "dockerEvents": len(events), "faultEventActions": actions}
    if len(scope) != len(APPLICATION_SERVICES):
        result["costExtraServicesCpuSeconds"] = {
            name: cost["containersCpuSeconds"][name] for name in scope if name not in APPLICATION_SERVICES}
    return result


def _jaeger(
    raw: Any, normalized: Any, capture: Any, plan: Mapping[str, Any], window_seconds: Any = 125,
) -> None:
    queries = raw.get("queries") if isinstance(raw, dict) else None
    expected_start = int(workload.parse_iso(plan["barrierAt"], "barrierAt").timestamp() * 1_000_000)
    expected_end = expected_start + int(window_seconds) * 1_000_000
    if (
        not isinstance(raw, dict)
        or raw.get("schemaVersion") != 1
        or raw.get("collector") != "jaeger-query-api-v1"
        or raw.get("window") != {"startUs": expected_start, "endUs": expected_end}
        or raw.get("limitPerService") != 10000
        or not isinstance(queries, list)
        or len(queries) != 1
        or queries[0].get("service") != "frontend"
        or not isinstance(queries[0].get("response", {}).get("data"), list)
        or queries[0].get("response", {}).get("errors")
        or queries[0].get("traceCount") != len(queries[0]["response"]["data"])
        or queries[0]["traceCount"] >= 10000
        or capture != {
            "schemaVersion": 1,
            "kind": "hotel-jaeger-capture-terminal-v1",
            "queriesComplete": True,
            "collectorTailComplete": True,
            "backendReadyAtTerminal": True,
        }
    ):
        raise TerminalError("raw Jaeger window, query, limit, or terminal receipt differs")
    try:
        replay = jaeger_normalizer.normalize(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise TerminalError(f"raw Jaeger capture cannot be normalized: {exc}") from exc
    if canonical_bytes(replay) != canonical_bytes(normalized):
        raise TerminalError("normalized Jaeger capture differs from raw deterministic replay")


def _correlation(
    document: Any, replay: Mapping[str, Any], contract: Mapping[str, Any], offered: int | None = None,
) -> None:
    if offered is None:
        offered = _cell_timing(contract)["offered"]
    posture = contract["runKey"]["posture"]
    ceiling = posture_ceiling_for(contract)
    if canonical_bytes(document) != canonical_bytes(replay):
        raise TerminalError("retained request/trace correlation differs from replay")
    if posture not in ceiling["supportedPostures"]:
        raise TerminalError("cell posture is outside the declared supported ceiling")
    if (
        document.get("posture") != posture
        or document.get("scenario") != contract["fault"]
        or document.get("offered") != offered
        or document.get("sourceCostComparison") != {
            "state": ceiling["sourceCostComparisonState"], "numericValue": None,
            "reason": ceiling["sourceCostUnsupportedReason"],
        }
        or document.get("unsupportedPostures") != ceiling["unsupportedPostures"]
    ):
        raise TerminalError("correlation classification or missingness differs")
    rows = document.get("rows", [])
    if posture in witness.EMPTY_CAPTURE_POSTURES:
        if document.get("emptyCaptureProof", {}).get("classification") != witness.EMPTY_CAPTURE_POSTURES[posture]:
            raise TerminalError(f"{posture} lacks its declared empty-capture proof")
        if any(
            (row.get("applicationWitness") is True and (
                row.get("state") != "supported" or row.get("reconstructed") is not False
            ))
            or (row.get("applicationWitness") is False and (
                row.get("state") != "unsupported" or row.get("reconstructed") is not None
            ))
            for row in rows
        ):
            raise TerminalError(f"{posture} rows do not preserve witnessed negatives and missingness")
    elif not rows or any(
        row.get("state") not in {"supported", "unsupported"}
        or (
            row.get("phase") == "during" and contract["fault"] in witness.PAUSE_TARGETS
            and row.get("state") != "unsupported"
        )
        for row in rows
    ):
        raise TerminalError("full correlation rows have invalid support states")


JAEGER_REMAINDER = "jaeger-raw-remainder.json"


def _cell_timing(contract: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return runtime_policy.cell_timing(contract)
    except Exception as exc:  # noqa: BLE001 - any timing defect fails the replay
        raise TerminalError(f"cell timing is unavailable: {exc}") from exc


def _jaeger_remainder(document: Any, raw: Mapping[str, Any]) -> dict[str, Any]:
    """The all-services capture: every trace the other application services return in the same window that
    the frontend query did not already retain (parameterised epochs; the frontend query stays the scored one).
    """
    frontend_ids = {
        trace.get("traceID") for query in raw.get("queries", []) for trace in query["response"]["data"]
    }
    queries = document.get("queries") if isinstance(document, dict) else None
    expected_services = [name for name in APPLICATION_SERVICES if name != "frontend"]
    if (
        not isinstance(document, dict)
        or set(document) != {
            "schemaVersion", "kind", "window", "limitPerService", "frontendTraceCount", "queries",
        }
        or document["schemaVersion"] != 1
        or document["kind"] != "hotel-jaeger-all-services-remainder-v1"
        or document["window"] != raw.get("window")
        or document["limitPerService"] != raw.get("limitPerService")
        or document["frontendTraceCount"] != len(frontend_ids)
        or not isinstance(queries, list)
        or [row.get("service") for row in queries if isinstance(row, dict)] != expected_services
    ):
        raise TerminalError("Jaeger all-services remainder header differs")
    kept = set()
    for row in queries:
        traces = row.get("traces")
        if (
            set(row) != {"service", "traceCount", "traces"}
            or not isinstance(traces, list)
            or type(row["traceCount"]) is not int
            or not len(traces) <= row["traceCount"] < document["limitPerService"]
            or any(not isinstance(trace, dict) or not trace.get("traceID") for trace in traces)
        ):
            raise TerminalError("Jaeger all-services remainder query is malformed or reached its limit")
        for trace in traces:
            if trace["traceID"] in frontend_ids or trace["traceID"] in kept:
                raise TerminalError("Jaeger all-services remainder repeats an already retained trace")
            kept.add(trace["traceID"])
    return {
        "frontendTraces": len(frontend_ids),
        "remainderTraces": len(kept),
        "traceCountByService": {row["service"]: row["traceCount"] for row in queries},
    }


def _ledger_status(row: Mapping[str, Any]) -> str:
    if row.get("outcome") == "completed" and row.get("statusCode") == 200:
        return "ok"
    if "timed out" in str(row.get("error") or "").lower():
        return "timeout"
    return "failed"


def protocol_cell(
    contract: Mapping[str, Any], timing: Mapping[str, Any], plan: Mapping[str, Any],
    ledger: list[Mapping[str, Any]], fault_receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """The normalised cell of protocol_gates.py (GATES.md mapping table), barrier = 0."""
    barrier = float(plan["barrierMonotonic"])
    cell: dict[str, Any] = {
        "cellId": contract["runId"],
        "kind": "fault" if contract.get("fault") is not None else "nofault",
        "posture": contract["runKey"]["posture"],
        "valid": True,   # reached only after every harness check of this cell passed
        "plan": {
            "offered": timing["offered"],
            "rate": float(timing["requestsPerSecond"]),
            "durationSeconds": float(timing["measurementSeconds"]),
            "window": [float(value) for value in timing["scoredWindowSeconds"]],
        },
        "measurement": [0.0, float(timing["measurementSeconds"])],
        "ledgerKind": "ledger",
        "ledger": [
            {
                "scheduled": float(row["scheduledMonotonicOffsetSeconds"]),
                "started": float(row["actualStartMonotonic"]) - barrier,
                "ended": float(row["actualEndMonotonic"]) - barrier,
                "status": _ledger_status(row),
            }
            for row in ledger
        ],
    }
    if fault_receipt is not None:
        pause = fault_receipt.get("faultKind") == "pause"
        returned = fault_receipt["unpausedAtMonotonic"] if pause else fault_receipt["revertedAtMonotonic"]
        recovery = fault_receipt.get("recoveryState") or {}
        cell["fault"] = {
            "scheduledOnset": float(timing["faultOnsetSeconds"]),
            "scheduledHold": float(timing["faultHoldSeconds"]),
            # startedMonotonic is stamped immediately before the command (F-ADH-085); appliedMonotonic after
            # the change was observed, so it is an upper bound of the command's return.
            "onsetCommandIssued": float(fault_receipt["startedMonotonic"]) - barrier,
            "onsetCommandReturned": float(fault_receipt["appliedMonotonic"]) - barrier,
            "revertCommandIssued": float(fault_receipt["revertingMonotonic"]) - barrier,
            "revertCommandReturned": float(returned) - barrier,
            "onsetSource": "pre-command",
            "manifested": fault_receipt.get("manifested") is True,
            "reverted": (
                recovery.get("paused") is False and fault_receipt.get("recovered") is True
                if pause else fault_receipt.get("reverted") is True
            ),
        }
    return cell


def protocol_gate_record(
    contract: Mapping[str, Any], timing: Mapping[str, Any], plan: Mapping[str, Any],
    ledger: list[Mapping[str, Any]], fault_receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """F1 (fault cells), G1, G2 and G4 of the vendored shared gates; the cell is invalid unless all pass.

    P0, R1 and R2 are recorded as not evaluated (the harness writes none of their inputs), G4's channel scope
    is the ledger alone (no per-channel counts), and R2.recovery is recorded but never blocks.
    """
    gates = _load("hotel_candidate_terminal_protocol_gates", "validation/protocol_gates.py")
    cell = protocol_cell(contract, timing, plan, ledger, fault_receipt)
    # The profile rate is the rate the workload actually planned, so G4 compares the compiled plan with the
    # retained opportunity plan rather than a value with itself.
    profile = {
        "sut": "hotel-reservation", "routes": ["/hotels"], "rate": float(plan["rate"]),
        "services": list(APPLICATION_SERVICES), "channels": {}, "emitters": {},
    }
    records = [gates.g1(cell), gates.g2(cell), gates.g4(cell, profile), gates.r2_recovery(cell)]
    if cell["kind"] == "fault":
        records.insert(0, gates.f1(cell))
    blocking = [row["gate"] for row in records if row["gate"] in ("F1", "G1", "G2", "G4")]
    failed = [row["gate"] for row in records if row["gate"] in blocking and row["verdict"] != "pass"]
    if failed:
        reasons = "; ".join(row["reason"] for row in records if row["gate"] in failed)
        raise TerminalError(f"protocol gate(s) {', '.join(failed)} did not pass: {reasons}")
    return {
        "module": "validation/protocol_gates.py",
        "moduleSha256": hashlib.sha256(
            _read_file(MODULE / "validation/protocol_gates.py", "vendored protocol gates")
        ).hexdigest(),
        "blocking": blocking,
        "notEvaluated": ["P0", "R1", "R2"],
        "g4ChannelScope": "ledger-only",
        "canFire": gates.entry_rule_can_fire(cell),
        "verdicts": records,
    }


def validate_cell(root: Path, expected_contract: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Replay one terminal cell. Raises on every invalid or missing artifact."""
    root = Path(root).resolve(strict=True)
    contract = _json(root / "cell-contract.json", "cell contract")
    ceiling = posture_ceiling_for(contract)
    if expected_contract is not None and canonical_bytes(contract) != canonical_bytes(expected_contract):
        raise TerminalError("cell contract differs from the admitted compiled-plan cell")
    if (
        contract.get("schemaVersion") != 1
        or contract.get("kind") != "hotel-candidate-cell-contract-v1"
        or _runtime_path(contract.get("runtimeArtifactRoot")) != root
        or contract.get("runtimeAuthorized") is not True
        or contract.get("promotionAuthorized") is not False
        or contract.get("canonical") is not False
    ):
        raise TerminalError("cell contract identity or evidence ceiling differs")
    timing = _cell_timing(contract)
    parameterised = "timing" in contract
    required = set(REQUIRED_COMMON)
    if parameterised and timing["jaegerAllServicesRemainder"]:
        required.add(JAEGER_REMAINDER)
    if contract.get("fault") is not None:
        required.add("fault-receipt.json")
    if contract["runKey"]["posture"] in compiler.SAMPLER_POSTURES:
        required.add("cpu.json")
    missing = sorted(name for name in required if not (root / name).is_file())
    if missing:
        raise TerminalError(f"candidate cell is missing artifacts: {missing}")
    manifest = verify_manifest(root)
    plan = workload.validate_plan(_json(root / "opportunity-plan.json", "opportunity plan"))
    if plan["runId"] != contract["runId"] or plan["compiledPlanSha256"] != contract["compiledPlanCanonicalSha256"]:
        raise TerminalError("opportunity plan is not bound to the cell contract")
    if parameterised and (
        plan["rate"] != float(timing["requestsPerSecond"])
        or plan["durationSeconds"] != float(timing["measurementSeconds"])
        or plan["offered"] != timing["offered"]
    ):
        raise TerminalError("opportunity plan rate, duration or offered count differs from the cell's compiled timing")
    ledger_validation = workload.validate_ledger(plan, root / "opportunity-ledger.jsonl")
    _reconciliation(
        _json(root / "workload-reconciliation.json", "workload reconciliation"),
        ledger_validation, plan, root / "opportunity-ledger.jsonl", timing["offered"],
    )
    images = _json(root / "images.json", "runtime images")
    _images(images, contract)
    _source_provenance(root, images)
    _compose_provenance(root, contract, images)
    expected_cpu_start = float(plan["barrierMonotonic"])
    cpu_validation = None
    if contract["runKey"]["posture"] in compiler.SAMPLER_POSTURES:
        cpu = _json(root / "cpu.json", "CPU evidence")
        if (
            cpu.get("project") != contract["project"]
            or cpu.get("containerIdentities") != {
                row["containerId"]: row["service"] for row in images["containers"]
            }
            or cpu.get("windowStartMonotonic") != expected_cpu_start
            or cpu.get("windowEndMonotonic") != expected_cpu_start + float(timing["measurementSeconds"])
        ):
            raise TerminalError("CPU evidence project or measurement window differs")
        cpu_validation = resources.validate_cpu(cpu, collection_scope(contract))
    elif (root / "cpu.json").exists():
        raise TerminalError("a sampler-off posture retained docker-stats CPU evidence")
    system_validation = _system(root, contract, plan, images, timing)
    emissions = _json(root / "emissions.json", "emission evidence")
    expected_emission_start = int(
        workload.parse_iso(plan["barrierAt"], "barrierAt").timestamp() * 1_000_000_000
    )
    if (
        emissions.get("windowStartUnixNano") != expected_emission_start
        or emissions.get("windowEndUnixNano")
        != expected_emission_start + int(timing["measurementSeconds"]) * 1_000_000_000
    ):
        raise TerminalError("emission measurement window differs")
    emission_validation = resources.validate_emissions(emissions)
    _posture(_json(root / "posture-proof.json", "posture proof"), contract)
    nuisance = _nuisance(_json(root / "nuisance.json", "srv4 nuisance evidence"), contract)
    _cleanup(_json(root / "cell-cleanup.json", "cell cleanup"), contract)
    raw = _json(root / "jaeger-raw.json", "raw Jaeger capture")
    normalized = _json(root / "traces-normalized.json", "normalized Jaeger capture")
    capture_terminal = _json(root / "capture-terminal.json", "Jaeger terminal capture")
    _jaeger(raw, normalized, capture_terminal, plan, timing["jaegerQueryWindowSeconds"])
    remainder = None
    if JAEGER_REMAINDER in required:
        remainder = _jaeger_remainder(_json(root / JAEGER_REMAINDER, "Jaeger all-services remainder"), raw)
    fault = _json(root / "fault-receipt.json", "fault receipt") if contract.get("fault") else None
    replay = witness.correlate(
        plan, witness.ledger_rows(root / "opportunity-ledger.jsonl"),
        # ponytail: replacement decoding matches the cell runner (raw container bytes); a replaced byte cannot form a
        # witness or emission marker, so it can only drop a malformed line, never invent one.
        _read_file(root / "application.log", "application log").decode("utf-8", errors="replace"),
        normalized, posture=contract["runKey"]["posture"], scenario=contract["fault"],
        fault_receipt=fault, raw=raw, capture_terminal=capture_terminal,
        unsupported_postures=ceiling["unsupportedPostures"],
        timing=contract.get("timing"),
    )
    correlation = _json(root / "correlation.json", "request/trace correlation")
    _correlation(correlation, replay, contract, timing["offered"])
    posture = contract["runKey"]["posture"]
    if posture in witness.EMPTY_CAPTURE_POSTURES and emission_validation["eventCount"] != 0:
        raise TerminalError(f"{posture} unexpectedly contains source-emitted sampled spans")
    if posture in compiler.TRACE_POSTURES and emission_validation["eventCount"] <= 0:
        raise TerminalError(f"{posture} posture has no source-emitted sampled spans")
    body = {
        "schemaVersion": 1,
        "kind": "hotel-candidate-cell-terminal-v1",
        "runId": contract["runId"],
        "project": contract["project"],
        "manifest": manifest,
        "opportunities": ledger_validation,
        "cpu": cpu_validation,
        "system": system_validation,
        "emissions": emission_validation,
        "correlationCanonicalSha256": correlation["canonicalSha256"],
        "faultTruthState": correlation["faultTruth"]["state"],
        "nuisance": nuisance,
        "evidenceLabel": "candidate-evidence",
        "canonical": False,
        "absoluteCostOrLatencyCanonical": False,
        "sourceCostComparisonState": ceiling["sourceCostComparisonState"],
        "unsupportedPostures": [row["id"] for row in ceiling["unsupportedPostures"]],
        "candidateCellValid": True,
        "promotionAuthorized": False,
    }
    if parameterised:
        # Parameterised epochs only, so a frozen-epoch terminal stays byte-identical.
        body["protocolGates"] = protocol_gate_record(
            contract, timing, plan, witness.ledger_rows(root / "opportunity-ledger.jsonl"), fault,
        )
        if remainder is not None:
            body["jaegerAllServicesRemainder"] = remainder
        if "traceCompleteness" in correlation:
            # Decision 25: incomplete traces per window, auditable from the terminal document itself.
            body["traceCompleteness"] = correlation["traceCompleteness"]
    if "faultPathTruth" in correlation:
        # Surface the fault-cell truncation accounting in the cell terminal so a
        # during-fault allowance is auditable from the terminal document itself.
        # Cost cells have no such block, so their terminal stays byte-identical.
        body["faultPathTruth"] = correlation["faultPathTruth"]
    return {**body, "canonicalSha256": canonical_sha256(body)}


def validate_campaign(
    root: Path, contracts: list[Mapping[str, Any]], admission: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(root).resolve(strict=True)
    plan_sha256 = admission.get("bindings", {}).get("compiledPlanCanonicalSha256")
    ceiling, cell_count = posture_ceiling_for_plan(plan_sha256)
    if any(row.get("compiledPlanCanonicalSha256") != plan_sha256 for row in contracts):
        raise TerminalError("admitted contracts are not all bound to the campaign's compiled plan")
    if len(contracts) != cell_count or len({row.get("runId") for row in contracts}) != cell_count:
        raise TerminalError(f"campaign does not have {cell_count} unique admitted contracts")
    if _runtime_path(admission.get("bindings", {}).get("artifactRoot")) != root:
        raise TerminalError("campaign root differs from runtime admission")
    manifest = verify_manifest(root)
    results = []
    cost_roots: set[Path] = set()
    effect_roots: set[Path] = set()
    for contract in contracts:
        cell_root = _runtime_path(contract.get("runtimeArtifactRoot"))
        if not cell_root.exists():
            raise TerminalError("candidate cell root is missing")
        if root not in cell_root.parents:
            raise TerminalError("candidate cell root escapes campaign root")
        if contract.get("fault") is None:
            cost_roots.add(cell_root)
        else:
            effect_roots.add(cell_root)
        replay = validate_cell(cell_root, contract)
        terminal = _json(cell_root / CELL_TERMINAL, "retained cell terminal")
        if canonical_bytes(terminal) != canonical_bytes(replay):
            raise TerminalError(f"retained cell terminal differs: {contract.get('runId')}")
        results.append(replay)
    if cost_roots & effect_roots:
        raise TerminalError("cost and effect evidence roots overlap")
    cleanup = _json(root / "campaign-cleanup.json", "campaign cleanup")
    if cleanup != {
        "schemaVersion": 1,
        "kind": "hotel-candidate-campaign-cleanup-v1",
        "ownedProjects": [row["project"] for row in contracts],
        "ownedResourcesRemaining": {"containers": [], "networks": [], "volumes": []},
        "foreignResourcesMutated": False,
        "leaseReleased": False,
        "artifactDeletionAttempted": False,
    }:
        raise TerminalError("campaign cleanup or lease terminal state differs")
    body = {
        "schemaVersion": 1,
        "kind": "hotel-candidate-campaign-terminal-v1",
        "campaignId": admission["bindings"]["campaignId"],
        "admissionCanonicalSha256": admission["admissionCanonicalSha256"],
        "cellCount": cell_count,
        "validCellCount": len(results),
        "manifest": manifest,
        "runIdsCanonicalSha256": canonical_sha256(sorted(row["runId"] for row in results)),
        "evidenceLabel": "candidate-evidence",
        "canonical": False,
        "sourceCostComparisonState": ceiling["sourceCostComparisonState"],
        "unsupportedPostures": [row["id"] for row in ceiling["unsupportedPostures"]],
        "candidateCampaignValid": True,
        "promotionAuthorized": False,
    }
    return {**body, "canonicalSha256": canonical_sha256(body)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true")
    commands = parser.add_subparsers(dest="command")
    seal = commands.add_parser("seal-cell")
    seal.add_argument("root", type=Path)
    cell = commands.add_parser("validate-cell")
    cell.add_argument("root", type=Path)
    args = parser.parse_args()
    try:
        if args.self_check:
            if args.command is not None:
                raise TerminalError("self-check cannot be combined with an artifact command")
            strict_json_bytes(b'{"ok":true}', "self-check-valid")
            try:
                strict_json_bytes(b'{"duplicate":1,"duplicate":2}', "self-check-planted-duplicate")
            except TerminalError as exc:
                if str(exc) != "duplicate JSON key: duplicate":
                    raise TerminalError("self-check planted diagnostic differs") from exc
            else:
                raise TerminalError("self-check planted duplicate was not rejected")
            result = {"kind": "hotel-candidate-terminal-self-check-v1", "status": "pass"}
        elif args.command == "seal-cell":
            result = write_manifest(args.root)
        elif args.command == "validate-cell":
            result = validate_cell(args.root)
        else:
            raise TerminalError("an artifact command or --self-check is required")
    except (TerminalError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
