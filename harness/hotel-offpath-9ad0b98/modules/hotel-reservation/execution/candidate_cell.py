#!/usr/bin/env python3
"""Execute one exact, human-admitted Hotel candidate lifecycle action.

The command is intentionally narrow: every mutable value is replayed from the
runtime admission and frozen compiler.  Merely invoking this file without a
valid admission on stdin cannot reach Docker or create a runtime lease.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "modules" / "hotel-reservation"
SERVICES = (
    "consul", "frontend", "search", "geo", "rate", "reservation", "profile",
    "user", "recommendation", "review", "attractions", "jaeger",
    "memcached-rate", "memcached-review", "memcached-profile", "memcached-reserve",
    "mongodb-geo", "mongodb-profile", "mongodb-rate", "mongodb-review",
    "mongodb-attractions", "mongodb-recommendation", "mongodb-reservation", "mongodb-user",
)
APPLICATION_SERVICES = (
    "frontend", "search", "geo", "rate", "reservation", "profile",
    "user", "recommendation", "review", "attractions",
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CellError(RuntimeError):
    """An admitted lifecycle action failed before producing valid evidence."""


def _load(name: str, relative: str):
    path = MODULE / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise CellError(f"cannot load candidate component {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load("hotel_candidate_cell_runtime", "execution/candidate_runtime.py")
materializer = _load("hotel_candidate_cell_materializer", "candidate_materialize.py")
workload = _load("hotel_candidate_cell_workload", "workload/candidate_search.py")
faults = _load("hotel_candidate_cell_faults", "faults/lmt_faults.py")
resources = _load("hotel_candidate_cell_resources", "collectors/candidate_resources.py")
system = _load("hotel_candidate_cell_system", "collectors/system_state.py")
compiler = _load("hotel_candidate_cell_compiler", "execution/candidate_pilot.py")
witness = _load("hotel_candidate_cell_witness", "witness/candidate_evidence.py")
collector = _load("hotel_candidate_cell_jaeger", "collectors/jaeger_api.py")
normalizer = _load("hotel_candidate_cell_normalizer", "normalizers/jaeger.py")
terminal = _load("hotel_candidate_cell_terminal", "validation/candidate_terminal.py")
smoke = _load("hotel_candidate_cell_smoke", "execution/smoke.py")


def _write_json(path: Path, document: Any) -> None:
    payload = json.dumps(document, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        if os.write(descriptor, payload) != len(payload):
            raise CellError(f"short write to {path}")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = runtime.strict_json(path.read_bytes(), str(path))
    except OSError as exc:
        raise CellError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CellError(f"{path} must contain one JSON object")
    return value


def _command(
    arguments: list[str], *, environment: dict[str, str] | None = None,
    timeout: float = 600, check: bool = True, binary: bool = False,
) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            arguments, text=not binary, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=environment, check=False, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CellError(f"command could not complete: {arguments[0]}: {exc}") from exc
    if check and result.returncode:
        raise CellError(
            f"command failed ({result.returncode}): {arguments[0]}: "
            f"{result.stderr.strip() or 'no diagnostic'}"
        )
    return result


def _compose(source: Path, project: str, *arguments: str) -> list[str]:
    return [
        "docker", "compose", "-p", project,
        "-f", str(source / "docker-compose.obsplacement.yml"),
        "-f", str(MODULE / "deployment/compose.observability-placement.yml"),
        *arguments,
    ]


def _deadline(admission: Mapping[str, Any], reserve: float = 300) -> None:
    deadline = runtime._timestamp(admission["bindings"]["deadline"], "runtime deadline")
    if (deadline - datetime.now(timezone.utc)).total_seconds() <= reserve:
        raise CellError("runtime deadline has reached its owned-cleanup reserve")


def _admission(
    envelope: Any, expected_sha: str, *, require_clean_framework: bool = True,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not isinstance(envelope, dict) or set(envelope) != {"admission", "contract"}:
        raise CellError("runner stdin must contain the exact admission and optional contract")
    admission = envelope.get("admission")
    contract = envelope.get("contract")
    if not isinstance(admission, dict):
        raise CellError("runtime admission is missing")
    body = {key: value for key, value in admission.items() if key != "admissionCanonicalSha256"}
    if (
        SHA256.fullmatch(expected_sha) is None
        or admission.get("admissionCanonicalSha256") != expected_sha
        or runtime.canonical_sha256(body) != expected_sha
        or admission.get("runtimeAuthorized") is not True
        or admission.get("externalMutationAuthorized") is not True
        or admission.get("promotionAuthorized") is not False
    ):
        raise CellError("runtime admission identity or authority differs")
    if require_clean_framework:
        installed_manifest = ROOT / "install-manifest.json"
        if installed_manifest.is_file() and not installed_manifest.is_symlink():
            runtime.verify_installed_payload(
                admission["bindings"]["frameworkCommit"],
                admission["bindings"]["installationManifestCanonicalSha256"],
                ROOT, full=False,
            )
        else:
            runtime._verify_git(admission["bindings"]["frameworkCommit"], runtime._git_state())
    if contract is not None:
        expected_contracts = runtime.cell_contracts(admission)
        matches = [row for row in expected_contracts if row["runId"] == contract.get("runId")]
        if len(matches) != 1 or runtime.canonical_bytes(matches[0]) != runtime.canonical_bytes(contract):
            raise CellError("cell contract is not an exact admitted plan cell")
    return admission, contract


def _bindings(admission: Mapping[str, Any]) -> tuple[Path, Path]:
    binding = admission["bindings"]
    if binding["checkoutRoot"] == ".":
        checkout = ROOT
    else:
        checkout = Path(binding["checkoutRoot"])
    if checkout.resolve(strict=True) != ROOT.resolve(strict=True):
        raise CellError("runner checkout differs from the admitted checkout")
    artifact = Path(binding["artifactRoot"])
    artifact = (ROOT / artifact).resolve() if not artifact.is_absolute() else artifact.resolve()
    policy = runtime._validate_policy(runtime._json_file(runtime.POLICY, "runtime policy"))
    allowed = policy["allowedTransports"][binding["transportId"]]
    parent = Path(allowed["artifactParent"])
    parent = (ROOT / parent).resolve() if not parent.is_absolute() else parent.resolve()
    if artifact.parent != parent or artifact.name != binding["campaignId"]:
        raise CellError("runtime artifact root differs from the exact admitted parent")
    return checkout, artifact


def _lease(admission: Mapping[str, Any]) -> Path:
    value = Path(admission["bindings"]["leasePath"])
    return (ROOT / value).resolve() if not value.is_absolute() else value.resolve()


def _lease_owner(admission: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "kind": "hotel-candidate-runtime-lease-v1",
        "campaignId": admission["bindings"]["campaignId"],
        "admissionCanonicalSha256": admission["admissionCanonicalSha256"],
        "deadline": admission["bindings"]["deadline"],
        "projectPrefix": admission["bindings"]["projectPrefix"],
        "ports": admission["bindings"]["ports"],
    }


def _owned_projects(admission: Mapping[str, Any]) -> tuple[str, ...]:
    """Derive cleanup identities without reading mutable plan/controller bytes."""
    binding = admission.get("bindings")
    if not isinstance(binding, dict):
        raise CellError("runtime admission bindings are missing")
    campaign_id = binding.get("campaignId")
    prefix = binding.get("projectPrefix")
    if runtime.CAMPAIGN_ID.fullmatch(str(campaign_id)) is None or prefix != "hotel_candidate_v4":
        raise CellError("cleanup project derivation differs from the admitted namespace")
    # 2026-09-22: was `range(1, 25)`, the seventh site to freeze the old 24-cell
    # shape as a literal. Hotel #6 ran 54 cells, all 54 valid, and was then sealed
    # INVALID at campaign level: this enumerated 24 projects, the lease-release
    # check compares `cleanup["projectsChecked"]` against the admission's cell
    # contracts for exact list equality, the 24-vs-54 mismatch made the cleanup
    # receipt "missing-or-invalid", and the campaign verdict followed.
    # runCount is the admitted count, carried in the GATE-RUN sentence and the
    # bindings, so it is the immutable source this function is meant to use --
    # no mutable plan or controller bytes are read.
    run_count = binding.get("runCount")
    if not isinstance(run_count, int) or isinstance(run_count, bool) or not 1 <= run_count <= 999:
        raise CellError("admitted run count is missing or out of range")
    # The suffix is sha256(campaignId)[:8], NOT the campaign id's own trailing hex.
    # candidate_runtime.py:2180 is the authoritative derivation and the two must agree
    # or cleanup enumerates projects that were never created.
    suffix = hashlib.sha256(str(campaign_id).encode()).hexdigest()[:8]
    projects = tuple(
        f"{prefix}_{suffix}_{ordinal:02d}" for ordinal in range(1, run_count + 1)
    )
    if any(runtime.PROJECT.fullmatch(project) is None for project in projects):
        raise CellError("cleanup project identity is invalid")
    return projects


def _require_lease(admission: Mapping[str, Any]) -> None:
    lease = _lease(admission)
    owner = lease if lease.is_file() and not lease.is_symlink() else lease / "owner.json"
    if _read_json(owner) != _lease_owner(admission):
        raise CellError("runtime lease is absent or owned by another campaign")


def acquire_lease(admission: Mapping[str, Any]) -> dict[str, Any]:
    _deadline(admission, 300)
    lease = _lease(admission)
    lease.parent.mkdir(parents=True, exist_ok=True)
    try:
        lease.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise CellError(f"runtime lease already exists and will not be stolen: {lease}") from exc
    try:
        _write_json(lease / "owner.json", _lease_owner(admission))
    except Exception:
        lease.rmdir()
        raise
    return {"acquired": True, "leasePath": admission["bindings"]["leasePath"]}


def _port_free(port: int) -> bool:
    """True when nothing is listening on the fixed port.

    SO_REUSEADDR makes the probe ignore the previous cell's own TIME_WAIT
    connections (the workload opens hundreds to 127.0.0.1:35005, and they
    outlive `compose down` by up to 60 s) while still failing against a live
    listener. Without it the second cell of the first real campaign
    (2026-09-06) was refused as "not clean at mutation boundary".
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def _boundary_clean(project: str, *, timeout_seconds: float = 30.0) -> tuple[bool, float]:
    """Wait, bounded, for the previous cell's Docker teardown to finish releasing
    the project's resources and the fixed ports; returns (clean, waited)."""
    started = time.monotonic()
    while True:
        clean = (
            not any(smoke.project_resources(project).values())
            and _port_free(35005) and _port_free(36685)
        )
        waited = time.monotonic() - started
        if clean or waited >= timeout_seconds:
            return clean, waited
        time.sleep(1.0)


def preflight(admission: Mapping[str, Any]) -> dict[str, Any]:
    _require_lease(admission)
    _deadline(admission, 300)
    _, artifact = _bindings(admission)
    if artifact.exists() or artifact.is_symlink():
        raise CellError("campaign artifact root already exists")
    source_proof = materializer._load_base().verify_source()
    expected = materializer._load_base().pinned_commit()
    if (
        source_proof.get("upstreamCommit") != expected
        or source_proof.get("sourceCheckoutClean") is not True
    ):
        raise CellError("Hotel source input is not the exact replayed package or checkout")
    docker = _command(["docker", "version", "--format", "{{json .}}"], timeout=20)
    compose = _command(["docker", "compose", "version", "--short"], timeout=20)
    contracts = runtime.cell_contracts(admission)
    collisions = [row["project"] for row in contracts if any(smoke.project_resources(row["project"]).values())]
    nuisance = _nuisance_snapshot()
    ports = admission["bindings"]["ports"]
    if collisions or not all(_port_free(port) for port in ports.values()):
        raise CellError(f"preflight collision: projects={collisions}, ports={ports}")
    return {
        "passed": True,
        "sourceCommit": expected,
        "projectsChecked": len(contracts),
        "ports": ports,
        "dockerVersionSha256": hashlib.sha256(docker.stdout.encode()).hexdigest(),
        "composeVersion": compose.stdout.strip(),
        "foreignProject": nuisance["foreignProject"],
        "foreignResources": nuisance["foreignRows"],
        "hostLoad": nuisance["loadAverage"],
    }


def _runtime_environment(proof: Mapping[str, Any], posture: str) -> dict[str, str]:
    images = proof["runtimeImages"]
    lock = _read_json(MODULE / "deployment/runtime-inputs.lock.json")
    image = "obsplacement/hotel-reservation-candidate:" + proof["materializedSourceSha256"][:16]
    return {
        **os.environ,
        "HR_FRONTEND_PORT": "35005",
        "HR_JAEGER_QUERY_PORT": "36685",
        # A service without a tracer runs JAEGER_DISABLED=true -> opentracing.NoopTracer
        # (tracer-disabled, NOT source-off: the nethttp/otgrpc wrappers stay installed).
        # The overlay gives frontend its own pair so `selected` can trace it alone.
        "HR_JAEGER_SAMPLE_RATIO": "1" if compiler.traces(posture, "search") else "0",
        "HR_JAEGER_DISABLED": "false" if compiler.traces(posture, "search") else "true",
        "HR_FRONTEND_JAEGER_SAMPLE_RATIO": "1" if compiler.traces(posture, "frontend") else "0",
        "HR_FRONTEND_JAEGER_DISABLED": "false" if compiler.traces(posture, "frontend") else "true",
        "HR_SOURCE_SHA256": proof["materializedSourceSha256"],
        "HR_APP_IMAGE": image,
        "HR_CONSUL_IMAGE": images["consul"],
        "HR_JAEGER_IMAGE": images["jaeger"],
        "HR_MEMCACHED_IMAGE": images["memcached"],
        "HR_MONGO_IMAGE": images["mongo"],
        **lock["applicationEnvironment"],
        # LMT+S pilot: the posture, not the lock, sets the application log level.
        "LOG_LEVEL": compiler.LOG_LEVEL_BY_POSTURE[posture],
    }


def _validate_rendered_compose(
    rendered: str, proof: Mapping[str, Any], build: Mapping[str, Any], posture: str,
) -> None:
    try:
        document = runtime.strict_json(rendered, "rendered Compose")
    except runtime.GateError as exc:
        raise CellError(f"rendered Compose is invalid JSON: {exc}") from exc
    services = document.get("services") if isinstance(document, dict) else None
    if not isinstance(services, dict) or set(SERVICES) - set(services):
        raise CellError("rendered Compose omits an admitted service")
    app_services = {
        "frontend", "search", "geo", "rate", "reservation", "profile",
        "user", "recommendation", "review", "attractions",
    }
    memcached = {name for name in SERVICES if name.startswith("memcached-")}
    mongo = {name for name in SERVICES if name.startswith("mongodb-")}
    expected_images = {
        **{name: build["imageReference"] for name in app_services},
        "consul": proof["runtimeImages"]["consul"],
        "jaeger": proof["runtimeImages"]["jaeger"],
        **{name: proof["runtimeImages"]["memcached"] for name in memcached},
        **{name: proof["runtimeImages"]["mongo"] for name in mongo},
    }
    actual_images = {name: services[name].get("image") for name in expected_images}
    if actual_images != expected_images or any(
        services[name].get("container_name") is not None for name in SERVICES
    ):
        raise CellError("rendered Compose image pins or project isolation differ")
    published = set()
    try:
        for name, service in services.items():
            for row in service.get("ports") or []:
                if not isinstance(row, dict):
                    raise CellError(
                        "rendered Compose does not use explicit long port syntax"
                    )
                published.add((
                    name, int(row.get("target")), int(row.get("published")),
                    row.get("host_ip"), row.get("protocol", "tcp"),
                ))
    except (TypeError, ValueError) as exc:
        raise CellError(f"rendered Compose published ports are malformed: {exc}") from exc
    if published != {
        ("frontend", 5000, 35005, "127.0.0.1", "tcp"),
        ("jaeger", 16686, 36685, "127.0.0.1", "tcp"),
    }:
        raise CellError("rendered Compose published ports differ from the admitted loopback ports")
    expected_level = compiler.LOG_LEVEL_BY_POSTURE[posture]
    for name in app_services:
        environment = services[name].get("environment")
        if not isinstance(environment, dict) or (
            str(environment.get("JAEGER_SAMPLE_RATIO")) != ("1" if compiler.traces(posture, name) else "0")
            or str(environment.get("JAEGER_DISABLED")).lower()
            != ("false" if compiler.traces(posture, name) else "true")
            or str(environment.get("TLS")) != "0"
            or str(environment.get("GC")) != "100"
            or str(environment.get("LOG_LEVEL")) != expected_level
            or (
                name in {"review", "attractions"}
                and str(environment.get("MEMC_TIMEOUT")) != "2"
            )
        ):
            raise CellError(f"rendered Compose application environment differs: {name}")


def prepare_campaign(admission: Mapping[str, Any]) -> dict[str, Any]:
    _require_lease(admission)
    _deadline(admission, 300)
    _, artifact = _bindings(admission)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    try:
        artifact.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise CellError("refusing to replace a campaign artifact root") from exc
    _write_json(artifact / "runtime-admission.json", admission)
    source = artifact / "materialized-source"
    proof = materializer.materialize(source)
    _write_json(artifact / "materialization-proof.json", proof)
    environment = _runtime_environment(proof, "full")
    image = environment["HR_APP_IMAGE"]
    build = _command(
        [
            "docker", "build", "--pull=false",
            "--label", "org.obsplacement.materialized-source-sha256=" + proof["materializedSourceSha256"],
            "-t", image, str(source),
        ], environment=environment, timeout=1800,
    )
    (artifact / "application-build.log").write_text(build.stdout + build.stderr, encoding="utf-8")
    inspected = runtime.strict_json(
        _command(["docker", "image", "inspect", image], timeout=30).stdout,
        "candidate application image inspect",
    )
    if not isinstance(inspected, list) or len(inspected) != 1:
        raise CellError("candidate application image inspection is incomplete")
    image_id = inspected[0].get("Id")
    labels = inspected[0].get("Config", {}).get("Labels") or {}
    if (
        not isinstance(image_id, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None
        or labels.get("org.obsplacement.materialized-source-sha256") != proof["materializedSourceSha256"]
    ):
        raise CellError("candidate application image is not bound to the patched source")
    build_proof = {
        "schemaVersion": 1,
        "imageReference": image,
        "imageId": image_id,
        "materializedSourceSha256": proof["materializedSourceSha256"],
        "builderReference": proof["runtimeImages"]["builder"],
        "runtimeInputsSha256": proof["runtimeInputsSha256"],
    }
    _write_json(artifact / "application-build-proof.json", build_proof)
    return {"prepared": True, "applicationImageId": image_id, "materializedSourceSha256": proof["materializedSourceSha256"]}


def _collection_scope(study_epoch: Any) -> tuple:
    """The services this epoch collects: the ten application services, plus those the epoch declares
    (consul in hotel-offpath-v1; candidate_runtime.collection_extra_services)."""
    return APPLICATION_SERVICES + tuple(runtime.collection_extra_services(study_epoch))


def _pausable_services(study_epoch: Any) -> tuple:
    """Containers an owned cleanup unpauses before `down`: the two on-path pause targets, plus the epoch's extras."""
    return ("search", "reservation") + tuple(runtime.collection_extra_services(study_epoch))


def _container_identities(
    source: Path, project: str, environment: dict[str, str], services: tuple = APPLICATION_SERVICES,
) -> dict[str, str]:
    identities: dict[str, str] = {}
    for service in services:
        value = _command(_compose(source, project, "ps", "-q", service), environment=environment, timeout=20).stdout.strip()
        if re.fullmatch(r"[0-9a-f]{64}", value) is None or value in identities:
            raise CellError(f"application container identity is missing or duplicated: {service}")
        identities[value] = service
    return identities


def _image_receipt(
    source: Path, project: str, environment: dict[str, str],
    proof: Mapping[str, Any], build: Mapping[str, Any], services: tuple = APPLICATION_SERVICES,
) -> dict[str, Any]:
    rows = []
    for container, service in sorted(
        _container_identities(source, project, environment, services).items(), key=lambda row: row[1],
    ):
        inspected = runtime.strict_json(
            _command(["docker", "inspect", container], timeout=30).stdout,
            f"container inspect {service}",
        )
        if not isinstance(inspected, list) or len(inspected) != 1:
            raise CellError(f"container inspection is incomplete: {service}")
        labels = inspected[0].get("Config", {}).get("Labels") or {}
        row = {
            "service": service,
            "containerId": container,
            "project": labels.get("com.docker.compose.project"),
            "imageId": inspected[0].get("Image"),
        }
        rows.append(row)
    return {
        "schemaVersion": 1,
        "project": project,
        "materializedSourceSha256": proof["materializedSourceSha256"],
        "applicationImageId": build["imageId"],
        "applicationImageReference": build["imageReference"],
        "runtimeInputsSha256": proof["runtimeInputsSha256"],
        "containers": rows,
    }


POSTURE_CLASSIFICATION = {
    "none": "logs-fatal-sampler-off-tracer-disabled",
    "metrics": "logs-info-sampler-on-tracer-disabled",
    "selected": "logs-info-sampler-on-tracer-frontend-only",
    "full": "logs-info-sampler-on-tracer-full-sampling",
}


def _posture_receipt(posture: str, identities: Mapping[str, str]) -> dict[str, Any]:
    expected = {s: "1" if compiler.traces(posture, s) else "0" for s in APPLICATION_SERVICES}
    expected_disabled = {s: "false" if compiler.traces(posture, s) else "true" for s in APPLICATION_SERVICES}
    expected_level = compiler.LOG_LEVEL_BY_POSTURE[posture]
    values: dict[str, str | None] = {}
    disabled: dict[str, str | None] = {}
    levels: dict[str, str | None] = {}
    for container, service in identities.items():
        inspected = runtime.strict_json(
            _command(["docker", "inspect", container], timeout=30).stdout,
            f"posture inspect {service}",
        )[0]
        variables = dict(
            item.split("=", 1) for item in inspected.get("Config", {}).get("Env", []) if "=" in item
        )
        values[service] = variables.get("JAEGER_SAMPLE_RATIO")
        disabled[service] = variables.get("JAEGER_DISABLED")
        levels[service] = variables.get("LOG_LEVEL")
    if values != expected:
        raise CellError("runtime sample ratio differs from the posture's traced services")
    # Checked on the live containers for every posture; the receipt shape stays
    # the one every banked cell was sealed with (the rendered Compose file is
    # retained alongside and carries JAEGER_DISABLED per service).
    if {service: str(value).lower() for service, value in disabled.items()} != expected_disabled:
        raise CellError("runtime tracer enablement differs from the posture's traced services")
    if levels != {service: expected_level for service in APPLICATION_SERVICES}:
        raise CellError("runtime log level differs across application services")
    return {
        "schemaVersion": 3,
        "requested": posture,
        "expectedSampleRatio": expected,
        "services": values,
        "tracedServices": sorted(compiler.TRACED_SERVICES_BY_POSTURE[posture]),
        "logLevel": expected_level,
        "metricSampler": posture in compiler.SAMPLER_POSTURES,
        "sourceWorkDisabled": False,
        "classification": POSTURE_CLASSIFICATION[posture],
    }


def _owned_cleanup(source: Path, contract: Mapping[str, Any], environment: dict[str, str]) -> dict[str, Any]:
    project = contract["project"]
    _command(
        _compose(source, project, "unpause", *_pausable_services(contract.get("studyEpoch"))),
        environment=environment, timeout=30, check=False,
    )
    result = _command(
        _compose(source, project, "down", "-v", "--remove-orphans"),
        environment=environment, timeout=180, check=False,
    )
    remaining = smoke.project_resources(project)
    return {
        "schemaVersion": 1,
        "kind": "hotel-candidate-cell-cleanup-v1",
        "project": project,
        "unpauseAttempted": True,
        "composeDownReturnCode": result.returncode,
        "ownedResourcesRemaining": remaining,
        "foreignResourcesMutated": False,
        "artifactDeletionAttempted": False,
    }


BLOCKED_EVIDENCE_SUFFIX = ".blocked-evidence"
BLOCKED_EVIDENCE_MANIFEST = "blocked-evidence-manifest.json"


def _file_sha256(path: Path) -> str:
    """Chunked sha256 -- avoids `.read_bytes()` holding a whole large
    evidence file (e.g. a multi-hundred-MB traces.json) in memory at once."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preserve_blocked_evidence(
    run_root: Path, error: BaseException, *, run_id: str | None = None,
    run_key: Mapping[str, Any] | None = None,
) -> Path | None:
    """Quarantine a byte-complete copy of a blocked cell's evidence for replay.

    This is the Hotel port of the TeaStore pattern that turned three blind
    campaign aborts into offline-replayable ones.  A blocked cell loses its
    Docker-side state to the owned ``compose down -v`` in ``run_cell``'s
    ``finally``, and a cell blocked at terminal validation never gets a content
    manifest, so the Jaeger capture, the normalized traces, the application log
    and the correlation document are the only surviving diagnosis surface.
    Copying the whole attempted run root into an out-of-band sibling before any
    cleanup layer observes the abort makes the entire terminal validation
    replayable offline instead of costing another one-shot.

    Preservation is diagnostic and strictly best-effort: it never mutates the
    run root, never overwrites an existing quarantine, and its own failure must
    never mask the original abort.
    """
    run_root = Path(run_root)
    if run_root.is_symlink() or not run_root.is_dir():
        return None
    quarantine = run_root.parent / (run_root.name + BLOCKED_EVIDENCE_SUFFIX)
    if quarantine.exists() or quarantine.is_symlink():
        return quarantine
    staging = quarantine.with_name(quarantine.name + ".tmp")
    if staging.exists() or staging.is_symlink():
        return None

    def _link_or_copy(source: str, destination: str) -> None:
        try:
            os.link(source, destination)
        except OSError:
            shutil.copy2(source, destination)

    shutil.copytree(run_root, staging, symlinks=True, copy_function=_link_or_copy)
    preserved = sorted(
        path.relative_to(staging).as_posix()
        for path in staging.rglob("*") if path.is_file() and not path.is_symlink()
    )
    manifest = {
        "schemaVersion": 1,
        "kind": "hotel-candidate-blocked-evidence-v1",
        "runId": run_id,
        "runKey": dict(run_key) if isinstance(run_key, Mapping) else None,
        "preservedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "runtimeArtifactRoot": str(run_root),
        "errorType": type(error).__name__,
        "error": str(error)[:2000],
        # A per-file sha256 lets the quarantine copy's integrity be verified
        # independently later, without re-trusting the byte count alone.
        "preservedFiles": [
            {
                "path": name,
                "bytes": (staging / name).stat().st_size,
                "sha256": _file_sha256(staging / name),
            }
            for name in preserved
        ],
        "promotionAuthorized": False,
    }
    (staging / BLOCKED_EVIDENCE_MANIFEST).write_text(
        json.dumps(manifest, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    staging.replace(quarantine)
    return quarantine


def _quarantine_blocked_cell(
    run_root: Path, contract: Mapping[str, Any], failure: BaseException,
) -> Path | None:
    """Preserve blocked evidence without ever masking the original abort."""
    try:
        return preserve_blocked_evidence(
            run_root, failure, run_id=contract.get("runId"),
            run_key=contract.get("runKey"),
        )
    except Exception as retain_error:  # noqa: BLE001 - best-effort quarantine
        if hasattr(failure, "add_note"):
            failure.add_note(
                "blocked-evidence preservation failed: "
                f"{type(retain_error).__name__}: {retain_error}"
            )
        return None


def _cli_number(value: Any) -> str:
    """10 -> '10', 0.05 -> '0.05': the frozen epoch's warm-up argv stays the literal it was."""
    number = float(value)
    return str(int(number)) if number.is_integer() else repr(number)


def _jaeger_remainder(raw: Mapping[str, Any], start_us: int, end_us: int) -> dict[str, Any]:
    """Every trace the other nine application services return in the frontend query's window that the
    frontend query did not already retain.  One service at a time, keeping only the remainder, so memory
    stays at one response; the union with jaeger-raw.json is the whole trace store for these services."""
    frontend_ids = {trace.get("traceID") for query in raw["queries"] for trace in query["response"]["data"]}
    kept: set = set()
    queries = []
    for service in [name for name in APPLICATION_SERVICES if name != "frontend"]:
        response = collector.collect("http://127.0.0.1:36685", [service], start_us, end_us)["queries"][0]
        traces = [
            trace for trace in response["response"]["data"]
            if trace.get("traceID") not in frontend_ids and trace.get("traceID") not in kept
        ]
        kept.update(trace.get("traceID") for trace in traces)
        queries.append({"service": service, "traceCount": response["traceCount"], "traces": traces})
    return {
        "schemaVersion": 1, "kind": "hotel-jaeger-all-services-remainder-v1",
        "window": raw["window"], "limitPerService": raw["limitPerService"],
        "frontendTraceCount": len(frontend_ids), "queries": queries,
    }


def _nuisance_snapshot() -> dict[str, Any]:
    """Host condition v2: verify and record that no foreign Compose project or
    container is present (the dps_training_k co-tenant of campaigns #1-#5 is
    decommissioned).  Absence is established by inventory, not assumed."""
    listing = runtime.strict_json(
        _command(["docker", "compose", "ls", "--all", "--format", "json"], timeout=30).stdout,
        "Compose project inventory",
    )
    rows = _command([
        "docker", "ps", "-a", "--no-trunc", "--format",
        "{{.ID}}|{{.State}}|{{.Image}}|{{.Names}}|{{.Labels}}",
    ], timeout=30).stdout.splitlines()
    foreign = runtime.foreign_rows([row for row in rows if row], listing)
    if foreign:
        raise CellError(f"a foreign Compose project or container is present: {foreign[:3]}")
    return {
        "capturedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "loadAverage": list(os.getloadavg()),
        "foreignProject": None,
        "foreignRows": foreign,
    }


def run_cell(admission: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    _require_lease(admission)
    _deadline(admission, 300)
    # Frozen epoch: the constants this function held as literals at e4fd4c7; a parameterised epoch: the
    # cell's compiled timing (rate, measurement, onset, hold, offered are plan values).  Resolved before the
    # run root exists, so a timing refusal leaves no partial cell directory behind.
    timing = runtime.cell_timing(contract)
    _, artifact = _bindings(admission)
    source = artifact / "materialized-source"
    proof = _read_json(artifact / "materialization-proof.json")
    build = _read_json(artifact / "application-build-proof.json")
    run_root = Path(contract["runtimeArtifactRoot"])
    run_root = (ROOT / run_root).resolve() if not run_root.is_absolute() else run_root.resolve()
    expected_parent = artifact / "runs" / Path(contract["compiledArtifactRoot"]).parent
    if run_root.parent != expected_parent.resolve() or run_root.exists() or run_root.is_symlink():
        raise CellError("cell artifact root differs or already exists")
    run_root.mkdir(parents=True, mode=0o700)
    _write_json(run_root / "cell-contract.json", contract)
    _write_json(run_root / "source-proof.json", proof)
    _write_json(run_root / "application-build-proof.json", build)
    posture = contract["runKey"]["posture"]
    measurement = float(timing["measurementSeconds"])
    onset, hold = timing["faultOnsetSeconds"], timing["faultHoldSeconds"]
    slack = float(timing["collectorJoinSlackSeconds"])
    environment = _runtime_environment(proof, posture)
    base_url = "http://127.0.0.1:35005"
    probe_url = workload.search_url(base_url, 0)
    project = contract["project"]
    nuisance_before = _nuisance_snapshot()
    boundary_clean, boundary_wait = _boundary_clean(project)
    if not boundary_clean:
        raise CellError(
            "cell project or fixed ports are not clean at mutation boundary "
            f"after waiting {boundary_wait:.1f} s"
        )
    # ponytail: the wait is not retained as an artifact; every cell directory
    # is manifest-bound and an extra file would need a schema change.
    cleanup: dict[str, Any] | None = None
    fault_cancel = threading.Event()
    fault_result: dict[str, Any] = {}
    worker_errors: list[str] = []
    fault_thread: threading.Thread | None = None
    cpu_thread: threading.Thread | None = None
    cpu_result: dict[str, Any] = {}
    system_thread: threading.Thread | None = None
    events: Any = None
    try:
        rendered = _command(
            _compose(source, project, "config", "--format", "json"),
            environment=environment, timeout=60,
        )
        _validate_rendered_compose(rendered.stdout, proof, build, posture)
        (run_root / "compose-rendered.yml").write_text(rendered.stdout, encoding="utf-8")
        up = _command(
            _compose(source, project, "up", "-d", "--no-build", *SERVICES),
            environment=environment, timeout=600,
        )
        (run_root / "compose-up.log").write_text(up.stdout + up.stderr, encoding="utf-8")
        smoke.wait_ready(probe_url, timeout=300)
        all_images = smoke.image_receipt(project)
        smoke.validate_published_ports(all_images, 35005, 36685)
        # Collected services: the ten application containers, plus the epoch's extras (consul in hotel-offpath-v1).
        # `identities` stays the ten (posture proof); `collected` is what the collectors and the image receipt read.
        scope = _collection_scope(contract.get("studyEpoch"))
        collected = _container_identities(source, project, environment, scope)
        identities = {container: service for container, service in collected.items() if service in APPLICATION_SERVICES}
        _write_json(run_root / "images.json", _image_receipt(source, project, environment, proof, build, scope))
        _write_json(run_root / "posture-proof.json", _posture_receipt(posture, identities))
        # Candidate opportunities are only the declared measurement; use the established
        # non-tokenized load generator for the warmup (frozen: 30 s at 10/s; sweep: at the cell's rate).
        warmup = _command([
            sys.executable, str(MODULE / "workload/fixed_search.py"),
            "--base-url", base_url, "--rate", _cli_number(timing["warmupRequestsPerSecond"]),
            "--duration", _cli_number(timing["warmupSeconds"]),
            "--concurrency", str(timing["concurrency"]), "--output", str(run_root / "warmup.json"),
        ], timeout=float(timing["warmupSeconds"]) + 60, check=False)
        (run_root / "warmup.log").write_text(warmup.stdout + warmup.stderr, encoding="utf-8")
        if warmup.returncode:
            raise CellError(f"{_cli_number(timing['warmupSeconds'])}-second fixed warmup failed")
        barrier_at = datetime.now(timezone.utc) + timedelta(seconds=5)
        barrier_monotonic = time.monotonic() + 5
        plan = workload.build_plan(
            contract["runId"], contract["compiledPlanCanonicalSha256"],
            barrier_at, barrier_monotonic,
            rate=float(timing["requestsPerSecond"]), duration_seconds=measurement,
        )
        workload.write_plan(run_root / "opportunity-plan.json", plan)
        window_end_monotonic = barrier_monotonic + measurement
        # LMT+S pilot, always on in every posture: docker events, the 5 s system
        # sampler, two TCP snapshots and the cost cgroups at both window edges.
        events = system.EventStream(project, run_root / "docker-events.jsonl")
        system_result: dict[str, Any] = {}

        def collect_system() -> None:
            try:
                sampler = system.SystemSampler(collected, barrier_monotonic, window_end_monotonic)
                time.sleep(max(0.0, barrier_monotonic - time.monotonic()))
                start_edge = system.cost_edges(collected, "window-start")
                sampler.start()
                snapshots = []
                offsets = timing["tcpSnapshotOffsetsSeconds"]
                for label, offset in (("pre-fault", offsets["pre-fault"]), ("during-fault", offsets["during-fault"])):
                    time.sleep(max(0.0, barrier_monotonic + offset - time.monotonic()))
                    snapshots.append(system.tcp_snapshot(collected, label))
                time.sleep(max(0.0, window_end_monotonic - time.monotonic()))
                end_edge = system.cost_edges(collected, "window-end")
                sampler.join(timeout=30)
                if sampler.is_alive() or sampler.error:
                    raise system.SystemError_(sampler.error or "system sampler did not finish")
                system_result["cost"] = system.cost_document(start_edge, end_edge)
                system_result["samples"] = sampler.document()
                system_result["tcp"] = {"schemaVersion": 1, "kind": "hotel-lmt-tcp-snapshots-v1",
                                        "snapshots": snapshots}
            except Exception as exc:
                worker_errors.append(f"system collector: {type(exc).__name__}: {exc}")

        system_thread = threading.Thread(target=collect_system, daemon=True)
        system_thread.start()

        def collect_cpu() -> None:
            try:
                cpu_result.update(resources.collect_cpu(
                    project, collected, barrier_monotonic, window_end_monotonic,
                ))
            except Exception as exc:
                worker_errors.append(f"CPU collector: {type(exc).__name__}: {exc}")

        if posture in compiler.SAMPLER_POSTURES:
            cpu_thread = threading.Thread(target=collect_cpu, daemon=True)
            cpu_thread.start()
        if contract["fault"] is not None:
            def inject_fault() -> None:
                try:
                    fault_result.update(faults.inject(
                        source, project, contract["fault"], onset, hold,
                        probe_url, run_root / "fault-receipt.json", fault_cancel,
                        env=environment, scheduled_at_seconds=onset,
                        start_at_monotonic=barrier_monotonic + onset,
                        record_probes=bool(timing["probeStamps"]),
                    ))
                except Exception as exc:
                    worker_errors.append(f"fault adapter: {type(exc).__name__}: {exc}")

            fault_thread = threading.Thread(target=inject_fault, daemon=True)
            fault_thread.start()
        reconciliation = workload.execute_plan(
            plan, base_url, run_root / "opportunity-ledger.jsonl",
            concurrency=timing["concurrency"], timeout=timing["requestTimeoutSeconds"],
        )
        _write_json(run_root / "workload-reconciliation.json", reconciliation)
        if fault_thread is not None:
            fault_thread.join(timeout=180)
            if fault_thread.is_alive():
                raise CellError("fault adapter exceeded its bounded lifecycle")
        if cpu_thread is not None:
            cpu_thread.join(timeout=30 + slack)
            if cpu_thread.is_alive():
                raise CellError("CPU collector exceeded its bounded lifecycle")
        system_thread.join(timeout=60 + slack)
        if system_thread.is_alive():
            raise CellError("system collector exceeded its bounded lifecycle")
        time.sleep(2)
        events_summary = events.stop()
        events = None
        if worker_errors:
            raise CellError("; ".join(worker_errors))
        if cpu_thread is not None:
            _write_json(run_root / "cpu.json", cpu_result)
        _write_json(run_root / "cost-cgroup.json", system_result["cost"])
        _write_json(run_root / "system-samples.json", system_result["samples"])
        _write_json(run_root / "tcp-snapshots.json", system_result["tcp"])
        _write_json(run_root / "docker-events.json", events_summary)
        # Allow the Jaeger collector tail to settle, then retain one complete query.
        time.sleep(5)
        query_start_us = int(barrier_at.timestamp() * 1_000_000)
        query_end_us = int(
            (barrier_at + timedelta(seconds=timing["jaegerQueryWindowSeconds"])).timestamp() * 1_000_000
        )
        raw = collector.collect("http://127.0.0.1:36685", ["frontend"], query_start_us, query_end_us)
        normalized = normalizer.normalize(raw)
        _write_json(run_root / "jaeger-raw.json", raw)
        if timing["jaegerAllServicesRemainder"]:
            _write_json(
                run_root / terminal.JAEGER_REMAINDER, _jaeger_remainder(raw, query_start_us, query_end_us),
            )
        _write_json(run_root / "traces-normalized.json", normalized)
        capture_terminal = {
            "schemaVersion": 1,
            "kind": "hotel-jaeger-capture-terminal-v1",
            "queriesComplete": True,
            "collectorTailComplete": True,
            "backendReadyAtTerminal": smoke.request_ok("http://127.0.0.1:36685/api/services"),
        }
        _write_json(run_root / "capture-terminal.json", capture_terminal)
        # Sweep: Docker's own sub-second timestamps on every line (application stamps are whole seconds).
        log_flags = ("--timestamps",) if timing["applicationLogTimestamps"] else ()
        # Container logs are bytes, not guaranteed UTF-8: sweep1 attempt 2 (2026-10-03) lost cell 26 and the
        # campaign to one 0xbf byte under strict decoding. Kept raw; parsed with replacement (U+FFFD).
        logs = _command(
            _compose(source, project, "logs", "--no-color", *log_flags, *scope),
            environment=environment, timeout=120, check=False, binary=True,
        )
        (run_root / "application.log").write_bytes(logs.stdout + logs.stderr)
        log_text = (logs.stdout + logs.stderr).decode("utf-8", errors="replace")
        emissions = resources.parse_emissions(
            log_text,
            int(barrier_at.timestamp() * 1_000_000_000),
            int((barrier_at + timedelta(seconds=measurement)).timestamp() * 1_000_000_000),
        )
        _write_json(run_root / "emissions.json", emissions)
        correlation = witness.correlate(
            plan, witness.ledger_rows(run_root / "opportunity-ledger.jsonl"),
            log_text, normalized, posture=posture,
            scenario=contract["fault"], fault_receipt=fault_result or None,
            raw=raw, capture_terminal=capture_terminal,
            unsupported_postures=runtime.posture_ceiling()["unsupportedPostures"],
            timing=contract.get("timing"),
        )
        _write_json(run_root / "correlation.json", correlation)
    except BaseException as failure:
        # Quarantine the attempted evidence BEFORE the owned Docker teardown in
        # the finally below, so an abort keeps a pre-cleanup snapshot instead of
        # only whatever survives cleanup.  Idempotent and best-effort.
        _quarantine_blocked_cell(run_root, contract, failure)
        raise
    finally:
        fault_cancel.set()
        if fault_thread is not None:
            fault_thread.join(timeout=30)
        if events is not None:
            try:
                events.stop()
            except Exception:  # noqa: BLE001 - the original failure is what matters
                pass
        try:
            cleanup = _owned_cleanup(source, contract, environment)
            _write_json(run_root / "cell-cleanup.json", cleanup)
        finally:
            nuisance_after = _nuisance_snapshot()
            _write_json(run_root / "nuisance.json", {
                "schemaVersion": 2,
                "kind": "hotel-srv4-cell-nuisance-v2",
                "factors": list(runtime.NUISANCE_FACTORS),
                "hostCondition": runtime.HOST_CONDITION_ID,
                "poolingBoundary": runtime.POOLING_BOUNDARY,
                "notPoolableWith": runtime.not_poolable_with(),
                "before": nuisance_before,
                "after": nuisance_after,
                "foreignMutationActions": [],
                "absoluteCostOrLatencyCanonical": False,
            })
    try:
        if cleanup["composeDownReturnCode"] != 0 or any(cleanup["ownedResourcesRemaining"].values()):
            raise CellError("owned cell cleanup did not reach zero resources")
        terminal.write_manifest(run_root)
        result = terminal.validate_cell(run_root, contract)
    except BaseException as failure:
        # A cell blocked at terminal validation is the F-ADH-065-class abort the
        # quarantine exists for: cleanup has already run, so the complete run
        # root is the only replayable diagnosis surface left.
        _quarantine_blocked_cell(run_root, contract, failure)
        raise
    _write_json(run_root / "cell-terminal.json", result)
    return result


def cleanup_campaign(admission: Mapping[str, Any]) -> dict[str, Any]:
    _require_lease(admission)
    _, artifact = _bindings(admission)
    source = artifact / "materialized-source"
    proof = _read_json(artifact / "materialization-proof.json") if artifact.exists() else None
    failures = []
    projects = list(_owned_projects(admission))
    for project in projects:
        if proof is not None:
            environment = _runtime_environment(proof, "full")
            _command(
                _compose(source, project, "unpause", *_pausable_services(runtime.STUDY_EPOCH)),
                environment=environment, timeout=30, check=False,
            )
            result = _command(_compose(source, project, "down", "-v", "--remove-orphans"), environment=environment, timeout=180, check=False)
            if result.returncode:
                failures.append({"project": project, "downReturnCode": result.returncode})
        remaining = smoke.project_resources(project)
        if any(remaining.values()):
            failures.append({"project": project, "remaining": remaining})
    return {"ownedResourcesRemaining": failures, "projectsChecked": projects}


def release_lease(admission: Mapping[str, Any]) -> dict[str, Any]:
    _require_lease(admission)
    remaining = {
        project: smoke.project_resources(project)
        for project in _owned_projects(admission)
    }
    _, artifact = _bindings(admission)
    lease = _lease(admission)
    (lease / "owner.json").unlink()
    lease.rmdir()
    uncleared = {
        project: value for project, value in remaining.items() if any(value.values())
    }
    if artifact.exists():
        _write_json(artifact / "campaign-cleanup.json", {
            "schemaVersion": 1,
            "kind": "hotel-candidate-campaign-cleanup-v1",
            "ownedProjects": list(_owned_projects(admission)),
            "ownedResourcesRemaining": (
                uncleared if uncleared else {"containers": [], "networks": [], "volumes": []}
            ),
            "foreignResourcesMutated": False,
            "leaseReleased": True,
            "artifactDeletionAttempted": False,
        })
    return {
        "released": True,
        "leasePath": admission["bindings"]["leasePath"],
        "ownedResourcesRemainingAtRelease": uncleared,
    }


def validate_campaign(admission: Mapping[str, Any]) -> dict[str, Any]:
    _, artifact = _bindings(admission)
    terminal.write_manifest(artifact)
    result = terminal.validate_campaign(artifact, runtime.cell_contracts(admission), admission)
    _write_json(artifact / "campaign-terminal.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=(
        "acquire-lease", "preflight", "prepare-campaign", "run-cell",
        "cleanup", "release-lease", "validate-campaign",
    ))
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--admission-sha256", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--contract-sha256")
    args = parser.parse_args()
    try:
        envelope = runtime.strict_json(sys.stdin.buffer.read(), "runner stdin")
        admission, contract = _admission(
            envelope, args.admission_sha256,
            require_clean_framework=args.action not in {"cleanup", "release-lease"},
        )
        binding = admission["bindings"]
        if binding["campaignId"] != args.campaign_id or binding["artifactRoot"] != args.artifact_root:
            raise CellError("runner arguments differ from the admitted campaign")
        if contract is None:
            if args.run_id is not None or args.contract_sha256 is not None:
                raise CellError("non-cell action contains a cell argument")
        elif (
            args.action != "run-cell" or args.run_id != contract["runId"]
            or args.contract_sha256 != runtime.canonical_sha256(contract)
        ):
            raise CellError("cell arguments differ from the admitted cell contract")
        if args.action == "acquire-lease":
            result = acquire_lease(admission)
        elif args.action == "preflight":
            result = preflight(admission)
        elif args.action == "prepare-campaign":
            result = prepare_campaign(admission)
        elif args.action == "run-cell":
            result = run_cell(admission, contract)
        elif args.action == "cleanup":
            result = cleanup_campaign(admission)
        elif args.action == "release-lease":
            result = release_lease(admission)
        else:
            result = validate_campaign(admission)
    except (CellError, runtime.GateError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
