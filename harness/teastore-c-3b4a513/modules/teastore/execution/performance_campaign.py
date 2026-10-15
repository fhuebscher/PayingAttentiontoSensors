#!/usr/bin/env python3
"""TeaStore lifecycle primitives plus one gate-internal candidate-cell producer.

The legacy CLI and ``run_one`` remain diagnostic construction denials.  The
candidate entry point accepts only the immutable contract emitted by the
admission layer and is invoked by the bounded remote controller.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, NoReturn


PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTAINER_ID_RE = re.compile(r"^[0-9a-f]{64}$")
DESCRIPTOR_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
CANDIDATE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
APP_SERVICES = ("webui", "auth", "persistence", "image", "recommender")
RUNTIME_SERVICES = (*APP_SERVICES, "registry", "db", "rabbitmq")
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
CONTAINER_IMAGE_INSPECT_FORMAT = (
    '{{.Id}}\t{{.Image}}\t{{.Config.Image}}\t'
    '{{index .Config.Labels "com.docker.compose.project"}}\t'
    '{{index .Config.Labels "com.docker.compose.service"}}'
)
IMAGE_INSPECT_FORMAT = '{{.Id}}\t{{json .RepoDigests}}'
COMPOSE_BASE = [
    "docker", "compose",
    "-f", "modules/teastore/deployment/compose/docker-compose_kieker.yaml",
    "-f", "modules/teastore/deployment/compose/docker-compose_rabbitmq.yaml",
    "-f", "modules/teastore/deployment/compose/isolation.override.yaml",
]
OVERRIDES = {
    "none": "modules/teastore/postures/none.override.yaml",
    "selected": "modules/teastore/deployment/compose/compiled-selected.override.yaml",
    "full": "modules/teastore/deployment/compose/compiled-full.override.yaml",
}
ALLOWED_POSTURES = frozenset(OVERRIDES)
ALLOWED_FAULTS = frozenset({"none", "auth-freeze", "persistence-crash"})
# F-ADH-075.  The longest pause any campaign cell injects.  ``_candidate_args``
# reads this constant, so the fault duration and the heartbeat floor derived from
# it below cannot drift apart.
CANDIDATE_FAULT_OUTAGE_SECONDS = 150
# A paused JVM emits no AMQP heartbeat for the whole outage, so any negotiated
# timeout shorter than the outage guarantees a mid-pause connection close --
# exactly the campaign #6 loss.  0 means "no timeout" and is always acceptable;
# otherwise require twice the longest pause, which leaves margin for the
# post-resume publish and for the resume itself being observed a few seconds
# late.  Kieker cannot request 0 (heartbeat=0 is its UNSET sentinel and becomes
# DEFAULT_HEARTBEAT=60), so docker-compose_kieker.yaml requests 900 and the
# broker's own 0 makes the negotiation max(0, 900) = 900.
BROKER_HEARTBEAT_FLOOR_SECONDS = 2 * CANDIDATE_FAULT_OUTAGE_SECONDS
# Field order for ``rabbitmqctl list_connections``.  ``client_properties`` is a
# rendered Erlang proplist and is kept last so a tab split cannot be confused by
# its internal punctuation.  Verified against rabbitmq:3-management.
BROKER_CONNECTION_FIELDS = ("user", "peer_host", "timeout", "client_properties")
# The public diagnostic CLI remains limited to smoke validation.  Candidate
# evidence enters only through ``candidate_cell_executor.py``, whose immutable
# contract enables the separate application-witness and native-token path.
ALLOWED_EVIDENCE_LABELS = frozenset({"smoke-validation"})
CONSTRUCTION_RUNTIME_BLOCKED = (
    "construction blocked: direct cell execution has no affirmative runtime "
    "authorization, outer-lease proof, or deadline-controller binding"
)
CANDIDATE_CONTRACT = "teastore-candidate-cell-invocation-v1"
CANDIDATE_PRODUCTION_KIND = "teastore-candidate-cell-production-v1"
CANDIDATE_EVIDENCE_LABEL = "candidate-evidence"


def _study_epoch_module():
    """The tree's study-epoch selector (execution/study_epoch.py), loaded by path (python3 -I)."""
    path = Path(__file__).resolve().parent / "study_epoch.py"
    name = "teastore_study_epoch_" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:  # pragma: no cover - installation defect
            raise RuntimeError(f"cannot load the study-epoch selector: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


# With no selector this is the frozen epoch and every constant below equals its c1724b1 literal.
CANDIDATE_EPOCH = _study_epoch_module().active(Path(__file__).resolve().parents[3])
CANDIDATE_STUDY_EPOCH = CANDIDATE_EPOCH["studyEpoch"]
CANDIDATE_SUT_COMMIT = "34b37f7e7be433ce72d5f9455e66922a13116749"
CANDIDATE_COMMON_ARTIFACTS = {
    "receipt.json", "journey-ledger.plan.json", "journey-ledger.jsonl",
    "auth.log", "persistence.log", "app-witness.jsonl",
    "app-witness-extraction.json", "service-log-capture.json",
    "native-token-correlation.json", "native-token-correlation-extraction.json",
    "kieker-amqp.spool", "traces.json", "capture-terminal.json",
    "posture-proof.json", "queue-proof.json", "runtime-images.json",
    "candidate-validation.json", "system-samples.json",
}
# Traffic sweep: every service's log with Docker receive timestamps (docker compose logs --timestamps).
APPLICATION_LOG_ARTIFACT = "application.log"
if CANDIDATE_EPOCH["sweep"]:
    CANDIDATE_COMMON_ARTIFACTS = CANDIDATE_COMMON_ARTIFACTS | {APPLICATION_LOG_ARTIFACT}
RESOURCE_INTERVAL_SECONDS = 5.0
# sys lineage (2026-09-29): cgroup-v2 counters in every cell, cost and fault alike.
# Not a barrier participant and never a cost input; fault-window rows are detection
# signals only, and a stopped container is a null row.
SYSTEM_SAMPLES_ARTIFACT = "system-samples.json"
SYSTEM_SAMPLE_INTERVAL_SECONDS = 5.0
SYSTEM_PROBE_JOIN_SLACK_SECONDS = 90.0
RESOURCE_COMMAND_TIMEOUT_SECONDS = 4.0
RESOURCE_MAXIMUM_START_LATENESS_SECONDS = 1.0
# The probe resolves the Compose inventory with two bounded Docker queries before
# joining the barrier.  Keep enough lead for both worst-case queries plus process
# startup; a late probe fails instead of shifting the scientific window.
MEASUREMENT_BARRIER_LEAD_SECONDS = 15.0
COLLECTOR_FROZEN_SERVICE_REGEX = r'tools\.descartes\.teastore\.([a-zA-Z0-9_]+)\.'
COLLECTOR_FROZEN_SERVICE_MAP = {
    "store": "auth", "entities": "persistence", "registryclient": "registry",
}
COLLECTOR_BASE_STAT_FIELDS = frozenset({
    "messages", "containers_ok", "containers_bad", "records_ok", "records_bad",
    "record_parse_success_ratio", "container_parse_success_ratio",
    "acknowledgement_mode", "runtime_host_map_loaded", "correlation",
})
COLLECTOR_ATTRIBUTION_STAT_FIELDS = frozenset({
    "attribution_configuration", "attribution_configuration_sha256",
})
COLLECTOR_STAT_FIELDS = (
    COLLECTOR_BASE_STAT_FIELDS | COLLECTOR_ATTRIBUTION_STAT_FIELDS | {"spool"}
)
LEGACY_COLLECTOR_STAT_FIELDS = COLLECTOR_BASE_STAT_FIELDS
SPOOL_ARTIFACT_NAME = "kieker-amqp.spool"
# The collector's terminal work (drain remainder, seal, replay the spool) is
# data-proportional, so its join uses a stall detector rather than a guessed
# constant: the hard cap only backstops a collector that keeps beating without
# ever finishing (F-ADH-061).
COLLECTOR_JOIN_HARD_CAP_SECONDS = 600.0
COLLECTOR_NO_PROGRESS_TIMEOUT_SECONDS = 60.0
COLLECTOR_SPOOL_FIELDS = frozenset({
    "schemaVersion", "path", "deliveryCount", "uniqueBodyCount",
    "duplicateBodyCount", "rawBodyBytes", "spoolBytes", "artifactSha256",
    "terminalDigestSha256", "sealed", "complete", "blockers",
    "replayedEventCount", "replayedRecordFailures",
})
COLLECTOR_CORRELATION_FIELDS = frozenset({
    "events", "parentResolution", "serviceAttribution",
    "eventsWithCorrelationErrors", "eventsWithUnwovenRootParent",
    "eventsWithProbeOrphanRoot", "eventsWithCorrelationWarnings",
    "eventsWithServiceAttributionErrors", "traceCompleteness",
})
COLLECTOR_TRACE_COMPLETENESS_FIELDS = frozenset({
    "traces", "tracesWithEoiGaps", "missingEoiCount",
    "tracesNotStartingAtZero",
})
COLLECTOR_PARENT_STATES = frozenset({
    "root", "resolved", "missing", "ambiguous", "unresolved",
})
COLLECTOR_ATTRIBUTION_STATES = frozenset({
    "runtime-host-only", "runtime-host-and-signature-agree",
    "runtime-host-overrides-shared-signature", "runtime-host-signature-conflict",
    "unresolved", "ambiguous-shared-signature", "declaring-signature-fallback",
})
COLLECTOR_ATTRIBUTION_ERROR_STATES = frozenset({
    "runtime-host-signature-conflict", "unresolved", "ambiguous-shared-signature",
    "declaring-signature-fallback",
})
SELECTION_SOURCES = {
    "auth": Path("modules/teastore/activation/auth-selection.json"),
    "fault-qualification": Path("modules/teastore/goals/fault-qualification.json"),
}
# F-ADH-072: posture -> (selection id, compiled manifest, compiled aop.xml).
# All three are rendered by src/obsplacement/selection.py from one catalog, so
# the woven join-point sets nest. Campaign #6 mounted a rendered aop.xml for
# `selected` only and left `full`/`none` on the stock in-image file, which
# excludes ~100 join points the rendered `selected` wove -- the postures were
# therefore incomparable and cost(selected) exceeded cost(full).
COMPILED_ACTIVATION = {
    "selected": ("fault-qualification",
                 Path(".local/compiled/teastore/manifest.json"),
                 Path(".local/compiled/teastore/aop.xml")),
    "full": ("catalog-all",
             Path(".local/compiled/teastore/full.manifest.json"),
             Path(".local/compiled/teastore/full.aop.xml")),
    "none": ("catalog-empty",
             Path(".local/compiled/teastore/none.manifest.json"),
             Path(".local/compiled/teastore/none.aop.xml")),
}


def fixed_load_module():
    """Load the workload's own evidence validator from the retained release."""
    path = Path("modules/teastore/workload/fixed_load.py")
    spec = importlib.util.spec_from_file_location("teastore_fixed_load_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load fixed-load validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resource_probe_module():
    """Load the resource producer's pure replay checker from the retained release."""
    path = Path("modules/teastore/collectors/performance_probe_v3.py")
    spec = importlib.util.spec_from_file_location("teastore_resource_probe_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load resource evidence validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selection_compiler_module():
    """Load the selection compiler from the retained release."""
    path = Path("src/obsplacement/selection.py")
    spec = importlib.util.spec_from_file_location("teastore_selection_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load selection compiler: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def native_collector_module():
    """Load the raw-spool replay implementation used by the collector itself."""
    path = Path("modules/teastore/collectors/kieker_native.py")
    spec = importlib.util.spec_from_file_location("teastore_kieker_spool_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Kieker spool replay: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replay_spool_evidence(spool_path: Path, runtime_images_path: Path) -> dict:
    """Independently regenerate events and counters from one sealed body spool."""
    module = native_collector_module()
    runtime_host_map = module.load_runtime_host_service_map(runtime_images_path)
    attribution, attribution_sha256 = module.frozen_attribution_configuration(
        runtime_host_map,
    )
    events, summary, counts = module.replay_spooled_events(
        spool_path,
        re.compile(module.DEFAULT_SERVICE_REGEX),
        module.DEFAULT_SERVICE_MAP,
        attribution["effectiveHostAliases"],
    )
    return {
        "events": events,
        "summary": summary,
        "counts": counts,
        "attributionConfiguration": attribution,
        "attributionConfigurationSha256": attribution_sha256,
        # F-ADH-084: typed description of every body the parser rejected, so a
        # containers_bad counter stops being anonymous in every validator.
        "containerParseFailures": module.spool_container_parse_diagnostics(spool_path),
    }


def validate_journey_evidence(aggregate: dict, ledger_path: Path) -> dict:
    """Replay the immutable plan and append-only ledger against its aggregate."""
    module = fixed_load_module()
    plan_path = module.journey_plan_path(ledger_path)
    validation = module.validate_journey_ledger(plan_path, ledger_path)
    evidence = aggregate.get("journeyEvidence")
    expected = {
        "plan": plan_path.name,
        "ledger": ledger_path.name,
        "planSha256": validation["planSha256"],
        "lastRecordSha256": validation["lastRecordSha256"],
    }
    if evidence != expected:
        raise RuntimeError("workload aggregate journey evidence differs from retained ledger")
    if aggregate.get("offered") != validation["terminalJourneys"]:
        raise RuntimeError("workload aggregate denominator differs from retained ledger")
    if aggregate.get("settled") != validation["terminalJourneys"]:
        raise RuntimeError("workload aggregate settled count differs from retained ledger")
    return validation


def parse_postures(value: str) -> tuple[str, ...]:
    postures = tuple(value.split(","))
    if not postures or len(set(postures)) != len(postures) or any(item not in ALLOWED_POSTURES for item in postures):
        raise ValueError(f"postures must be unique values from {sorted(ALLOWED_POSTURES)}")
    return postures


def validate_parameters(args: argparse.Namespace) -> tuple[str, ...]:
    postures = parse_postures(args.postures)
    if args.blocks <= 0 or args.warmup < 0 or args.duration <= 0 or args.concurrency <= 0:
        raise ValueError("blocks, duration, and concurrency must be positive; warmup must be non-negative")
    if not math.isfinite(args.rate) or args.rate <= 0:
        raise ValueError("rate must be finite and positive")
    if args.fault not in ALLOWED_FAULTS:
        raise ValueError(f"unknown fault: {args.fault}")
    if args.fault == "none":
        if args.fault_at != 240 or args.outage != 30:
            raise ValueError("fault timing must remain at defaults when no fault is requested")
    elif args.fault_at < 0 or args.outage <= 0 or args.fault_at + args.outage >= args.duration:
        raise ValueError("fault and recovery must fit strictly inside the measurement window")
    if not COMMIT_RE.fullmatch(args.framework_commit):
        raise ValueError("framework commit must be the full 40-character Git object")
    if not COMMIT_RE.fullmatch(args.sut_reference_commit):
        raise ValueError("SUT reference commit must be the full 40-character Git object")
    if not DESCRIPTOR_ID_RE.fullmatch(args.descriptor_id):
        raise ValueError("descriptor id must be a lowercase filesystem-safe identifier")
    if not SHA256_RE.fullmatch(args.descriptor_sha256):
        raise ValueError("descriptor sha256 must be a full lowercase 64-character digest")
    if args.evidence_label not in ALLOWED_EVIDENCE_LABELS:
        raise ValueError(f"evidence label must be one of {sorted(ALLOWED_EVIDENCE_LABELS)}")
    project_name()
    return postures


def campaign_configuration(args: argparse.Namespace, postures: tuple[str, ...]) -> dict:
    selection_source = SELECTION_SOURCES[args.selection_id]
    return {
        "schemaVersion": 1, "seed": args.seed, "blocks": args.blocks,
        "postures": list(postures), "warmupSeconds": args.warmup,
        "measurementSeconds": args.duration, "journeysPerSecond": args.rate,
        "concurrency": args.concurrency, "fault": args.fault,
        "faultAtSeconds": args.fault_at if args.fault != "none" else None,
        "outageSeconds": args.outage if args.fault != "none" else None,
        "frameworkCommit": args.framework_commit,
        "sutReferenceCommit": args.sut_reference_commit,
        "selectionId": args.selection_id,
        "descriptorId": args.descriptor_id,
        "descriptorSha256": args.descriptor_sha256,
        "evidenceLabel": args.evidence_label,
        "collectorDurationSeconds": args.duration + 30,
        "collectorInactivityTimeoutSeconds": 10,
        "composeProject": project_name(),
        "selectionSourceSha256": sha256(selection_source),
        "activationManifestSha256": sha256(Path(".local/compiled/teastore/manifest.json")),
    }


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def command(args: list[str], *, output: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if output:
        output.write_text(result.stdout + ("\nSTDERR\n" + result.stderr if result.stderr else ""))
    if check and result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {args}\n{result.stderr}")
    return result


def capture_bytes(args: list[str]) -> subprocess.CompletedProcess:
    """Run one argv and keep stdout as raw bytes (no decoding, so no byte in a log can raise)."""
    return subprocess.run(args, capture_output=True, check=False)


def compose(posture: str, *args: str) -> list[str]:
    value = [*COMPOSE_BASE[:2], "-p", project_name(), *COMPOSE_BASE[2:]]
    if OVERRIDES[posture]:
        value.extend(["-f", OVERRIDES[posture]])
    return [*value, *args]


def project_name() -> str:
    value = os.environ.get("OBSPLACEMENT_COMPOSE_PROJECT", "")
    if not PROJECT_RE.fullmatch(value):
        raise ValueError(
            "OBSPLACEMENT_COMPOSE_PROJECT must be an explicit lowercase campaign namespace "
            "(1-63 characters)"
        )
    return value


def project_resources() -> dict:
    project = project_name()
    label = f"label=com.docker.compose.project={project}"
    commands = {
        "containers": ["docker", "ps", "-aq", "--filter", label],
        "networks": ["docker", "network", "ls", "-q", "--filter", label],
        "volumes": ["docker", "volume", "ls", "-q", "--filter", label],
    }
    proof = {"project": project, "queries": {}, "queryPassed": True}
    for kind, argv in commands.items():
        try:
            observed = command(argv, check=False)
            proof[kind] = sorted(line for line in observed.stdout.splitlines() if line)
            proof["queries"][kind] = {
                "command": argv, "returnCode": observed.returncode,
                "stdout": observed.stdout, "stderr": observed.stderr,
            }
            if observed.returncode != 0:
                proof["queryPassed"] = False
        except Exception as exc:  # noqa: BLE001 - absence proof must fail closed
            proof[kind] = []
            proof["queries"][kind] = {
                "command": argv, "returnCode": None,
                "stdout": "", "stderr": f"{type(exc).__name__}: {exc}",
            }
            proof["queryPassed"] = False
    return proof


def resources_clean(proof: dict) -> bool:
    project = proof.get("project")
    if not isinstance(project, str) or not project or proof.get("queryPassed") is not True:
        return False
    label = f"label=com.docker.compose.project={project}"
    expected = {
        "containers": ["docker", "ps", "-aq", "--filter", label],
        "networks": ["docker", "network", "ls", "-q", "--filter", label],
        "volumes": ["docker", "volume", "ls", "-q", "--filter", label],
    }
    queries = proof.get("queries")
    return (
        isinstance(queries, dict) and set(queries) == set(expected)
        and all(
            isinstance(queries[kind], dict)
            and set(queries[kind]) == {"command", "returnCode", "stdout", "stderr"}
            and queries[kind].get("command") == argv
            and queries[kind].get("returnCode") == 0
            and queries[kind].get("stderr") == ""
            and sorted(line for line in queries[kind].get("stdout", "").splitlines() if line)
            == proof.get(kind)
            for kind, argv in expected.items()
        )
        and all(proof.get(kind) == [] for kind in expected)
    )


def service_container(posture: str, service: str) -> str:
    result = command(compose(posture, "ps", "-q", service), check=False)
    identifiers = [line for line in result.stdout.splitlines() if line]
    if result.returncode or len(identifiers) != 1:
        raise RuntimeError(f"expected exactly one {service} container, found {identifiers}")
    return identifiers[0]


def _exact_inspect_fields(result: subprocess.CompletedProcess, description: str,
                          count: int) -> list[str]:
    if result.returncode != 0 or result.stderr:
        raise RuntimeError(
            f"{description} failed ({result.returncode}): {result.stderr or 'unexpected status'}")
    lines = result.stdout.splitlines()
    if len(lines) != 1 or len(lines[0].split("\t")) != count:
        raise RuntimeError(f"{description} must return exactly one {count}-field row")
    return lines[0].split("\t")


def validate_runtime_images(
    document: dict, *, expected_content_references: Mapping[str, str] | None = None,
) -> None:
    if set(document) != {"schemaVersion", "capturedAt", "composeProject", "services"}:
        raise RuntimeError("runtime image proof top-level fields differ")
    if document.get("schemaVersion") != 1 or document.get("composeProject") != project_name():
        raise RuntimeError("runtime image proof project/schema binding differs")
    services = document.get("services")
    if not isinstance(services, dict) or set(services) != set(RUNTIME_SERVICES):
        raise RuntimeError("runtime image proof service set differs")
    digest_re = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
    if expected_content_references is not None and (
        not isinstance(expected_content_references, Mapping)
        or set(expected_content_references) != set(RUNTIME_SERVICES)
        or any(
            not isinstance(value, str) or not digest_re.fullmatch(value)
            for value in expected_content_references.values()
        )
    ):
        raise RuntimeError("candidate expected image references differ")
    for service in RUNTIME_SERVICES:
        item = services[service]
        expected_fields = {
            "containerId", "declaredImage", "containerImageId", "imageInspectId",
            "repoDigests", "composeProjectLabel", "composeServiceLabel", "queries",
        }
        if not isinstance(item, dict) or set(item) != expected_fields:
            raise RuntimeError(f"runtime image proof fields differ for {service}")
        container_id = item.get("containerId")
        declared = item.get("declaredImage")
        container_image = item.get("containerImageId")
        inspected_image = item.get("imageInspectId")
        digests = item.get("repoDigests")
        if not isinstance(container_id, str) or not CONTAINER_ID_RE.fullmatch(container_id):
            raise RuntimeError(f"runtime container identity is incomplete for {service}")
        if not isinstance(declared, str) or not declared:
            raise RuntimeError(f"declared runtime image is missing for {service}")
        if declared != EXPECTED_RUNTIME_IMAGES[service]:
            raise RuntimeError(f"declared runtime image differs from the deployment contract for {service}")
        if (not isinstance(container_image, str) or not IMAGE_ID_RE.fullmatch(container_image)
                or inspected_image != container_image):
            raise RuntimeError(f"runtime image IDs disagree for {service}")
        if (not isinstance(digests, list)
                or any(not isinstance(value, str) or not digest_re.fullmatch(value)
                       for value in digests)
                or digests != sorted(set(digests))):
            raise RuntimeError(f"repository digests are incomplete for {service}")
        if expected_content_references is None:
            if not digests or any(
                not value.startswith(
                    f"{EXPECTED_RUNTIME_REPOSITORIES[service]}@sha256:"
                ) for value in digests
            ):
                raise RuntimeError(f"repository digests are incomplete for {service}")
        else:
            expected_image_id = expected_content_references[service].split("@", 1)[1]
            if expected_image_id != container_image:
                raise RuntimeError(
                    f"candidate target-built image ID differs for {service}"
                )
        if (item.get("composeProjectLabel") != project_name()
                or item.get("composeServiceLabel") != service):
            raise RuntimeError(f"Compose ownership labels disagree for {service}")
        queries = item.get("queries")
        expected_queries = {
            "containerInspect": ["docker", "inspect", "--format",
                                 CONTAINER_IMAGE_INSPECT_FORMAT, container_id],
            "imageInspect": ["docker", "image", "inspect", "--format",
                             IMAGE_INSPECT_FORMAT, declared],
        }
        if not isinstance(queries, dict) or set(queries) != set(expected_queries):
            raise RuntimeError(f"runtime image queries differ for {service}")
        for name, argv in expected_queries.items():
            query = queries[name]
            if (not isinstance(query, dict)
                    or set(query) != {"command", "returnCode", "stdout", "stderr"}
                    or query.get("command") != argv or query.get("returnCode") != 0
                    or query.get("stderr") != ""):
                raise RuntimeError(f"runtime image query proof is incomplete for {service}/{name}")
        container_fields = queries["containerInspect"]["stdout"].strip("\n").split("\t")
        image_fields = queries["imageInspect"]["stdout"].strip("\n").split("\t")
        if (len(container_fields) != 5
                or container_fields != [container_id, container_image, declared,
                                        project_name(), service]):
            raise RuntimeError(f"container inspect output disagrees for {service}")
        if len(image_fields) != 2 or image_fields[0] != inspected_image:
            raise RuntimeError(f"image inspect output disagrees for {service}")
        try:
            raw_digests = json.loads(image_fields[1])
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"image inspect digests are invalid for {service}") from exc
        if raw_digests is None and expected_content_references is not None:
            raw_digests = []
        if not isinstance(raw_digests, list) or sorted(raw_digests) != digests:
            raise RuntimeError(f"image inspect digests disagree for {service}")


def runtime_image_proof(
    posture: str, *, expected_content_references: Mapping[str, str] | None = None,
) -> dict:
    proof = {
        "schemaVersion": 1, "capturedAt": now(),
        "composeProject": project_name(), "services": {},
    }
    for service in RUNTIME_SERVICES:
        container_id = service_container(posture, service)
        container_argv = ["docker", "inspect", "--format",
                          CONTAINER_IMAGE_INSPECT_FORMAT, container_id]
        container_result = command(container_argv, check=False)
        container_fields = _exact_inspect_fields(
            container_result, f"container inspect for {service}", 5)
        inspected_container, container_image, declared, project_label, service_label = container_fields
        if inspected_container != container_id:
            raise RuntimeError(f"container inspect identity disagrees for {service}")
        image_argv = (["docker", "image", "inspect", "--format", IMAGE_INSPECT_FORMAT,
                       declared] if declared else [])
        if not image_argv:
            raise RuntimeError(f"declared runtime image is missing for {service}")
        image_result = command(image_argv, check=False)
        image_fields = _exact_inspect_fields(image_result, f"image inspect for {service}", 2)
        inspected_image = image_fields[0]
        try:
            repo_digests = json.loads(image_fields[1])
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"image inspect digests are invalid for {service}") from exc
        proof["services"][service] = {
            "containerId": container_id,
            "declaredImage": declared,
            "containerImageId": container_image,
            "imageInspectId": inspected_image,
            "repoDigests": sorted(repo_digests or []),
            "composeProjectLabel": project_label,
            "composeServiceLabel": service_label,
            "queries": {
                "containerInspect": {
                    "command": container_argv, "returnCode": container_result.returncode,
                    "stdout": container_result.stdout,
                    "stderr": container_result.stderr,
                },
                "imageInspect": {
                    "command": image_argv, "returnCode": image_result.returncode,
                    "stdout": image_result.stdout,
                    "stderr": image_result.stderr,
                },
            },
        }
    validate_runtime_images(
        proof, expected_content_references=expected_content_references,
    )
    return proof


def wait_ready(timeout: int = 240) -> None:
    url = "http://localhost:8080/tools.descartes.teastore.webui/status"
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = command(["curl", "-fsS", "--max-time", "10", url], check=False)
        if result.returncode == 0 and result.stdout.count("OK") >= 5:
            return
        time.sleep(5)
    raise RuntimeError("TeaStore readiness failed")


def wait_broker(posture: str, timeout: int = 120) -> None:
    container = service_container(posture, "rabbitmq")
    deadline = time.time() + timeout
    while time.time() < deadline:
        ping = command([
            "docker", "exec", container, "rabbitmq-diagnostics", "-q", "ping"
        ], check=False)
        auth = command([
            "docker", "exec", container, "rabbitmqctl",
            "authenticate_user", "admin", "nimda",
        ], check=False)
        queues = command([
            "docker", "exec", container, "rabbitmqctl",
            "list_queues", "-q", "name",
        ], check=False)
        if ping.returncode == 0 and auth.returncode == 0 and "kieker" in queues.stdout.split():
            time.sleep(5)
            return
        time.sleep(2)
    raise RuntimeError("RabbitMQ readiness failed")


def wait_consumer(posture: str, timeout: int = 30) -> dict:
    deadline = time.time() + timeout
    state = queue_state(posture)
    while time.time() < deadline and state["consumers"] != 1:
        time.sleep(0.5)
        state = queue_state(posture)
    return state


def wait_queue_drained(posture: str, timeout: int = 30) -> dict:
    deadline = time.time() + timeout
    state = queue_state(posture)
    while time.time() < deadline and (state["messages"] != 0 or state["consumers"] != 0):
        time.sleep(0.5)
        state = queue_state(posture)
    return state


def posture_proof(posture: str) -> dict:
    """Bind the posture to the exact bytes every service actually weaves.

    Raises before warm-up when the mounted aop.xml is not the local re-render of
    the catalog for this posture, so a mis-realised lattice costs no measurement.
    """
    catalog_path = Path("modules/teastore/activation/catalog.json")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog_groups = sorted(row["id"] for row in catalog["activationGroups"])
    selection_id, manifest_path, aop_path = COMPILED_ACTIVATION[posture]
    if posture == "selected":
        requested = json.loads(
            SELECTION_SOURCES["fault-qualification"].read_text(encoding="utf-8"),
        )["logicalSensors"]
    elif posture == "full":
        requested = [row["id"] for row in catalog["logicalSensors"]]
    else:
        requested = []
    compiler = selection_compiler_module()
    compiled = compiler.compile_selection(catalog, requested)
    rendered_sha = hashlib.sha256(compiler.render_aop(compiled).encode()).hexdigest()
    file_sha = sha256(aop_path)
    if rendered_sha != file_sha:
        raise RuntimeError(
            f"posture {posture}: compiled {aop_path} ({file_sha}) differs from the "
            f"local re-render ({rendered_sha})"
        )
    required = list(compiled["selectedActivationGroups"])
    enabled = posture != "none"
    proof = {
        "schemaVersion": 3,
        "requested": posture,
        "catalogId": catalog["id"],
        "catalogSha256": sha256(catalog_path),
        "selectionId": selection_id,
        "goalLogicalSensors": sorted(requested),
        "closureGroups": required,
        "requiredGroups": required,
        "forbiddenGroups": sorted(set(catalog_groups) - set(required)),
        "aopSha256": rendered_sha,
        "manifestSha256": sha256(manifest_path),
        "monitoringEnabled": enabled,
        "services": {},
    }
    expected_line = f"kieker.monitoring.enabled={'true' if enabled else 'false'}"
    for service in APP_SERVICES:
        container = service_container(posture, service)
        digest = command(
            ["docker", "exec", container, "sha256sum", "/usr/local/tomcat/lib/aop.xml"],
            check=False,
        )
        config = command([
            "docker", "exec", container, "sh", "-c",
            "grep -E '^kieker.monitoring.enabled=' /kieker/config/kieker.monitoring.properties || true",
        ], check=False)
        logs = command(["docker", "logs", container], check=False)
        fields = digest.stdout.split()
        observed = fields[0] if digest.returncode == 0 and fields else None
        configuration = config.stdout.strip()
        proof["services"][service] = {
            "aopSha256": observed,
            "configuration": configuration,
            "writerInitializationFailed": (
                "Failed to load class for name 'kieker.monitoring.writer.amqp.ChunkingAmqpWriter'"
                in (logs.stdout + logs.stderr)
            ),
        }
        if observed != rendered_sha or configuration != expected_line:
            raise RuntimeError(
                f"posture {posture}: {service} mounts aop {observed} / "
                f"{configuration!r}, expected {rendered_sha} / {expected_line!r}"
            )
    return proof


def queue_state(posture: str) -> dict:
    container = service_container(posture, "rabbitmq")
    argv = [
        "docker", "exec", container, "rabbitmqctl",
        "list_queues", "-q", "name", "messages", "consumers",
    ]
    result = command(argv, check=False)
    if result.returncode != 0 or result.stderr:
        raise RuntimeError(
            f"RabbitMQ queue-state query failed ({result.returncode}): {result.stderr}")
    matches = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if fields and fields[0] == "kieker":
            if len(fields) != 3:
                raise RuntimeError(f"malformed kieker queue-state row: {line!r}")
            matches.append((int(fields[1]), int(fields[2])))
    if len(matches) != 1 or any(value < 0 for value in matches[0]):
        raise RuntimeError(f"expected exactly one non-negative kieker queue row, found {matches}")
    messages, consumers = matches[0]
    return {
        "containerId": container, "messages": messages, "consumers": consumers,
        "query": {"command": argv, "returnCode": result.returncode,
                  "stdout": result.stdout, "stderr": result.stderr},
    }


def broker_proof(posture: str) -> dict:
    """Prove the broker's heartbeat and overflow policy at run time.

    F-ADH-073: the campaign #6 loss was a broker default, not a Kieker defect,
    and nothing in the evidence chain recorded it. `complete` on the spool only
    means the frame chain was sealed -- producer-side publish failures and
    broker-side drops are invisible there, so they are proven here instead.
    """
    container = service_container(posture, "rabbitmq")
    queries = {
        "heartbeat": ["docker", "exec", container, "rabbitmqctl", "eval",
                      "application:get_env(rabbit, heartbeat)."],
        "queueArguments": ["docker", "exec", container, "rabbitmqctl", "list_queues",
                           "-q", "name", "arguments"],
        "connections": ["docker", "exec", container, "rabbitmqctl", "list_connections",
                        "-q", *BROKER_CONNECTION_FIELDS],
    }
    results = {name: command(argv, check=False) for name, argv in queries.items()}
    proof = {
        name: {"command": queries[name], "returnCode": result.returncode,
               "stdout": result.stdout, "stderr": result.stderr}
        for name, result in results.items()
    }
    heartbeat = results["heartbeat"].stdout.strip()
    connections = parse_broker_connections(results["connections"].stdout)
    return {
        "schemaVersion": 2,
        "queries": proof,
        "heartbeatSeconds": 0 if heartbeat == "{ok,0}" else None,
        "queueArguments": results["queueArguments"].stdout.strip(),
        "connections": connections,
        # Retained for continuity with schema v1 evidence; ``connections`` is the
        # authority and carries the identity needed to name an offender.
        "connectionTimeouts": [row["timeoutSeconds"] for row in connections],
    }


def parse_broker_connections(stdout: str) -> list[dict]:
    """Normalize ``rabbitmqctl list_connections`` rows into identified records.

    ``-q`` suppresses rabbitmqctl's informational chatter but still emits the
    column header, so that one row is skipped by name.  ``client_properties`` is
    last and is split with a bounded maxsplit, so punctuation (or a tab) inside
    the rendered proplist cannot shift the timeout column.  Anything else that
    does not parse raises: an unparsed connection is an unproven connection, and
    campaign #6 was lost precisely by not noticing one.
    """
    header = "\t".join(BROKER_CONNECTION_FIELDS)
    connections: list[dict] = []
    for line in stdout.splitlines():
        if not line.strip() or line.strip() == header:
            continue
        fields = line.split("\t", len(BROKER_CONNECTION_FIELDS) - 1)
        if (len(fields) != len(BROKER_CONNECTION_FIELDS)
                or not fields[2].lstrip("-").isdigit()):
            raise RuntimeError(f"malformed rabbitmqctl connection row: {line!r}")
        connections.append({
            "user": fields[0], "peerHost": fields[1],
            "timeoutSeconds": int(fields[2]), "clientProperties": fields[3],
        })
    return connections


def broker_proof_blockers(proof: dict) -> list[str]:
    """Every condition that would let campaign #6's loss mechanism recur."""
    blockers: list[str] = []
    if not isinstance(proof, dict) or proof.get("heartbeatSeconds") != 0:
        blockers.append("broker heartbeat is not disabled")
        return blockers
    arguments = proof.get("queueArguments", "")
    # Verified against rabbitmq:3-management de912cbb on 2026-09-04: with the
    # env var set, `rabbitmqctl eval application:get_env(rabbit, heartbeat).`
    # answers {ok,0} and list_queues reports
    # [{"x-max-length",50000},{"x-overflow","reject-publish"}].
    if not ("reject-publish" in arguments and "50000" in arguments):
        blockers.append("kieker queue overflow policy differs")
    connections = proof.get("connections")
    if not isinstance(connections, list) or not connections:
        blockers.append("broker reported no AMQP connections at the barrier")
        return blockers
    # F-ADH-075.  The old rule -- every negotiated timeout must be 0 -- was not
    # merely strict, it was unachievable: Kieker cannot request 0 (see
    # BROKER_HEARTBEAT_FLOOR_SECONDS), so the broker always answered 60 and the
    # gate blocked every fault cell.  The honest condition is that no negotiated
    # timeout may expire during a fault pause: 0 means no timeout at all, and any
    # other value must clear the floor derived from the longest pause.
    offenders = []
    for index, row in enumerate(connections):
        if not isinstance(row, dict):
            offenders.append(f"connection {index} is not a record")
            continue
        timeout = row.get("timeoutSeconds")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 0:
            offenders.append(f"connection {index} has no usable negotiated timeout")
            continue
        if timeout == 0 or timeout >= BROKER_HEARTBEAT_FLOOR_SECONDS:
            continue
        offenders.append(
            f"{row.get('user')}@{row.get('peerHost')} negotiated {timeout}s")
    if offenders:
        blockers.append(
            "an AMQP connection negotiated a heartbeat below the "
            f"{BROKER_HEARTBEAT_FLOOR_SECONDS}s fault-pause floor "
            f"(0 or >= floor required): {offenders}")
    return blockers


def collector_barrier_acknowledgement(posture: str, barrier_monotonic: float) -> dict:
    """Bracket the exact queue-state query used as the barrier acknowledgement."""

    query_started_at = now()
    query_started_offset = time.monotonic() - barrier_monotonic
    state = queue_state(posture)
    query_completed_at = now()
    query_completed_offset = time.monotonic() - barrier_monotonic
    return {
        "queryStartedAtWall": query_started_at,
        "queryStartedMonotonicOffsetSeconds": query_started_offset,
        "queryCompletedAtWall": query_completed_at,
        "queryCompletedMonotonicOffsetSeconds": query_completed_offset,
        "queueState": state,
    }


def purge_queue(posture: str) -> dict:
    container = service_container(posture, "rabbitmq")
    before = queue_state(posture)
    argv = ["docker", "exec", container, "rabbitmqctl", "purge_queue", "kieker"]
    result = command(argv, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"RabbitMQ purge failed ({result.returncode}): {result.stderr}")
    after = queue_state(posture)
    return {
        "before": before,
        "command": {"command": argv, "returnCode": result.returncode,
                    "stdout": result.stdout, "stderr": result.stderr},
        "after": after,
    }


def validate_queue_proof(document: dict, *, expected_project: str | None = None) -> None:
    if set(document) != {
            "schemaVersion", "composeProject", "purge", "measurement", "broker"}:
        raise RuntimeError("queue proof top-level fields differ")
    project = project_name() if expected_project is None else expected_project
    if not isinstance(project, str) or PROJECT_RE.fullmatch(project) is None:
        raise RuntimeError("queue proof expected project is invalid")
    if document.get("schemaVersion") != 2 or document.get("composeProject") != project:
        raise RuntimeError("queue proof project/schema binding differs")
    purge = document.get("purge")
    measurement = document.get("measurement")
    if not isinstance(purge, dict) or set(purge) != {"before", "command", "after"}:
        raise RuntimeError("queue purge proof fields differ")
    if (not isinstance(measurement, dict)
            or set(measurement) != {"before", "consumerAtStart", "after", "depthSamples"}):
        raise RuntimeError("queue measurement proof fields differ")
    samples = measurement["depthSamples"]
    if not isinstance(samples, list) or not samples:
        raise RuntimeError("queue depth was not sampled across the measurement window")
    for sample in samples:
        if (not isinstance(sample, dict)
                or set(sample) != {"monotonicOffsetSeconds", "messages", "consumers"}
                or any(not isinstance(sample[name], int) or isinstance(sample[name], bool)
                       or sample[name] < 0 for name in ("messages", "consumers"))):
            raise RuntimeError("queue depth sample fields differ")
        if sample["consumers"] != 1:
            raise RuntimeError(
                f"collector exclusivity lapsed mid-window: {sample['consumers']} consumers")
    deepest = max(sample["messages"] for sample in samples)
    if deepest >= QUEUE_DEPTH_BLOCK_THRESHOLD:
        raise RuntimeError(
            f"kieker queue depth reached {deepest} of 50000 mid-window: "
            "broker-side loss cannot be excluded")
    states = [purge["before"], purge["after"], measurement["before"],
              measurement["consumerAtStart"], measurement["after"]]
    container_ids = set()
    for state in states:
        if not isinstance(state, dict) or set(state) != {
                "containerId", "messages", "consumers", "query"}:
            raise RuntimeError("queue state proof fields differ")
        container_id = state.get("containerId")
        if not isinstance(container_id, str) or not CONTAINER_ID_RE.fullmatch(container_id):
            raise RuntimeError("queue state container identity is incomplete")
        container_ids.add(container_id)
        if any(not isinstance(state.get(name), int) or isinstance(state.get(name), bool)
               or state[name] < 0 for name in ("messages", "consumers")):
            raise RuntimeError("queue state counts are invalid")
        expected = ["docker", "exec", container_id, "rabbitmqctl", "list_queues",
                    "-q", "name", "messages", "consumers"]
        query = state.get("query")
        if (not isinstance(query, dict)
                or set(query) != {"command", "returnCode", "stdout", "stderr"}
                or query.get("command") != expected or query.get("returnCode") != 0
                or query.get("stderr") != ""):
            raise RuntimeError("queue-state query proof is incomplete")
        rows = [line.split() for line in query["stdout"].splitlines()
                if line.split() and line.split()[0] == "kieker"]
        expected_row = [["kieker", str(state["messages"]), str(state["consumers"])]]
        if rows != expected_row:
            raise RuntimeError("queue-state query output disagrees with normalized counts")
    if len(container_ids) != 1:
        raise RuntimeError("queue proof spans more than one RabbitMQ container")
    container_id = next(iter(container_ids))
    expected_purge = ["docker", "exec", container_id, "rabbitmqctl", "purge_queue", "kieker"]
    purge_command = purge.get("command")
    if (not isinstance(purge_command, dict)
            or set(purge_command) != {"command", "returnCode", "stdout", "stderr"}
            or purge_command.get("command") != expected_purge
            or purge_command.get("returnCode") != 0):
        raise RuntimeError("queue purge command proof is incomplete")
    broker = document.get("broker")
    if not isinstance(broker, dict) or set(broker) != {
            "schemaVersion", "queries", "heartbeatSeconds", "queueArguments",
            "connections", "connectionTimeouts"}:
        raise RuntimeError("broker proof fields differ")
    connections = broker["connections"]
    if not isinstance(connections, list) or any(
            not isinstance(row, dict) for row in connections):
        raise RuntimeError("broker connection records are not an array of objects")
    if broker.get("connectionTimeouts") != [
            row.get("timeoutSeconds") for row in connections]:
        raise RuntimeError(
            "broker connection timeouts disagree with the connection records")
    broker_blockers = broker_proof_blockers(broker)
    if broker_blockers:
        raise RuntimeError(f"broker proof conditions were not met: {broker_blockers}")
    if (purge["before"]["consumers"] != 0 or purge["after"]["messages"] != 0
            or purge["after"]["consumers"] != 0
            or measurement["before"]["messages"] != 0
            or measurement["before"]["consumers"] != 0
            or measurement["consumerAtStart"]["consumers"] != 1
            or measurement["after"]["messages"] != 0
            or measurement["after"]["consumers"] != 0):
        raise RuntimeError("queue purge/exclusivity/drain conditions were not proven")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_collector_attribution_binding(
    stats: dict,
    *,
    runtime_images_path: Path | None = None,
    require_candidate: bool = False,
) -> tuple[dict, str]:
    """Validate the complete attribution document and its canonical digest."""

    configuration = stats.get("attribution_configuration")
    digest = stats.get("attribution_configuration_sha256")
    if not isinstance(configuration, dict) or not isinstance(digest, str):
        raise RuntimeError("collector attribution configuration binding is missing")
    if not SHA256_RE.fullmatch(digest):
        raise RuntimeError("collector attribution configuration digest is invalid")
    module = native_collector_module()
    try:
        reconstructed, reconstructed_digest = module.frozen_attribution_configuration(
            configuration.get("runtimeHostAliases"),
            configuration.get("explicitHostAliases"),
        )
    except Exception as exc:  # noqa: BLE001 - malformed aliases must fail closed
        raise RuntimeError(
            f"collector attribution configuration is malformed: {type(exc).__name__}: {exc}"
        ) from exc
    if configuration != reconstructed:
        raise RuntimeError("collector attribution configuration differs from frozen inputs")
    if digest != reconstructed_digest:
        raise RuntimeError("collector attribution configuration digest disagrees with content")
    if require_candidate and configuration.get("explicitHostAliases") != {}:
        raise RuntimeError("candidate collector attribution contains explicit host aliases")
    if runtime_images_path is not None:
        try:
            runtime_host_map = module.load_runtime_host_service_map(runtime_images_path)
            expected, expected_digest = module.frozen_attribution_configuration(
                runtime_host_map,
            )
        except Exception as exc:  # noqa: BLE001 - runtime proof is part of the binding
            raise RuntimeError(
                f"collector attribution runtime proof is invalid: {type(exc).__name__}: {exc}"
            ) from exc
        if configuration != expected or digest != expected_digest:
            raise RuntimeError(
                "collector attribution configuration differs from runtime-images proof"
            )
    return configuration, digest


def collector_stats(
    stderr: str,
    *,
    require_attribution_binding: bool = False,
    runtime_images_path: Path | None = None,
) -> dict:
    """Extract exactly one complete, internally consistent collector summary."""
    decoder = json.JSONDecoder()
    candidates = []
    for index, character in enumerate(stderr):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(stderr[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and COLLECTOR_STAT_FIELDS.intersection(value):
            candidates.append(value)
    if len(candidates) != 1:
        raise RuntimeError(f"expected exactly one collector stats object, found {len(candidates)}")
    stats = candidates[0]
    observed_fields = frozenset(stats)
    allowed_fields = {
        LEGACY_COLLECTOR_STAT_FIELDS,
        LEGACY_COLLECTOR_STAT_FIELDS | {"spool"},
        LEGACY_COLLECTOR_STAT_FIELDS | COLLECTOR_ATTRIBUTION_STAT_FIELDS,
        COLLECTOR_STAT_FIELDS,
    }
    if observed_fields not in allowed_fields:
        missing = sorted(COLLECTOR_STAT_FIELDS - set(stats))
        extra = sorted(set(stats) - COLLECTOR_STAT_FIELDS)
        raise RuntimeError(f"collector stats fields differ (missing={missing}, extra={extra})")
    has_attribution = COLLECTOR_ATTRIBUTION_STAT_FIELDS <= observed_fields
    if require_attribution_binding and not has_attribution:
        raise RuntimeError("collector attribution configuration binding is required")
    count_fields = ("messages", "containers_ok", "containers_bad", "records_ok", "records_bad")
    if any(not isinstance(stats[field], int) or isinstance(stats[field], bool) or stats[field] < 0
           for field in count_fields):
        raise RuntimeError("collector count fields must be non-negative integers")
    ratio_fields = ("record_parse_success_ratio", "container_parse_success_ratio")
    if any(not isinstance(stats[field], (int, float)) or isinstance(stats[field], bool)
           or not math.isfinite(stats[field]) or not 0.0 <= stats[field] <= 1.0
           for field in ratio_fields):
        raise RuntimeError("collector parse ratios must be finite numbers in [0, 1]")
    records = stats["records_ok"] + stats["records_bad"]
    containers = stats["containers_ok"] + stats["containers_bad"]
    expected_records = stats["records_ok"] / records if records else 0.0
    expected_containers = stats["containers_ok"] / containers if containers else 0.0
    if not math.isclose(stats["record_parse_success_ratio"], expected_records, abs_tol=1e-12):
        raise RuntimeError("collector record parse ratio disagrees with record counts")
    if not math.isclose(stats["container_parse_success_ratio"], expected_containers, abs_tol=1e-12):
        raise RuntimeError("collector container parse ratio disagrees with container counts")
    if not isinstance(stats["runtime_host_map_loaded"], bool):
        raise RuntimeError("collector runtime_host_map_loaded must be boolean")
    if stats["acknowledgement_mode"] not in {"manual", "automatic"}:
        raise RuntimeError("collector acknowledgement_mode is invalid")
    correlation = stats["correlation"]
    if not isinstance(correlation, dict) or set(correlation) != COLLECTOR_CORRELATION_FIELDS:
        raise RuntimeError("collector correlation summary fields differ")
    correlation_counts = (
        "events", "eventsWithCorrelationErrors", "eventsWithUnwovenRootParent",
        "eventsWithProbeOrphanRoot", "eventsWithCorrelationWarnings",
        "eventsWithServiceAttributionErrors",
    )
    if any(not isinstance(correlation[field], int) or isinstance(correlation[field], bool)
           or correlation[field] < 0 for field in correlation_counts):
        raise RuntimeError("collector correlation counters must be non-negative integers")
    if correlation["events"] != stats["records_ok"]:
        raise RuntimeError("collector correlation event count differs from records_ok")
    for field, allowed in (
        ("parentResolution", COLLECTOR_PARENT_STATES),
        ("serviceAttribution", COLLECTOR_ATTRIBUTION_STATES),
    ):
        counter = correlation[field]
        if (not isinstance(counter, dict) or not set(counter) <= allowed
                or any(not isinstance(value, int) or isinstance(value, bool) or value <= 0
                       for value in counter.values())
                or sum(counter.values()) != correlation["events"]):
            raise RuntimeError(f"collector correlation {field} counter is invalid")
    if (correlation["eventsWithCorrelationErrors"] > correlation["events"]
            or correlation["eventsWithCorrelationWarnings"] > correlation["events"]
            or correlation["eventsWithServiceAttributionErrors"] > correlation["events"]):
        raise RuntimeError("collector correlation error counts exceed retained events")
    completeness = correlation["traceCompleteness"]
    if (not isinstance(completeness, dict)
            or set(completeness) != COLLECTOR_TRACE_COMPLETENESS_FIELDS
            or any(not isinstance(completeness[field], int)
                   or isinstance(completeness[field], bool)
                   or completeness[field] < 0
                   for field in COLLECTOR_TRACE_COMPLETENESS_FIELDS)
            or completeness["tracesWithEoiGaps"] > completeness["traces"]
            or completeness["tracesNotStartingAtZero"] > completeness["traces"]
            or (completeness["tracesWithEoiGaps"] == 0)
            != (completeness["missingEoiCount"] == 0)):
        raise RuntimeError("collector trace-completeness counters are invalid")
    unresolved_parent_events = sum(
        correlation["parentResolution"].get(state, 0)
        for state in ("missing", "ambiguous", "unresolved")
    )
    if correlation["eventsWithCorrelationErrors"] < unresolved_parent_events:
        raise RuntimeError("collector correlation errors undercount unresolved parents")
    # Unwoven-root-parent events are a subset of the events that carry a
    # correlation error, and each such event has parent_resolution "missing".
    if (correlation["eventsWithUnwovenRootParent"]
            > correlation["eventsWithCorrelationErrors"]
            or correlation["eventsWithUnwovenRootParent"]
            > correlation["parentResolution"].get("missing", 0)):
        raise RuntimeError("collector unwoven-root-parent count is inconsistent")
    # F-ADH-083: readiness-probe orphans are a subset of the unwoven roots.
    if correlation["eventsWithProbeOrphanRoot"] > correlation["eventsWithUnwovenRootParent"]:
        raise RuntimeError("collector probe-orphan-root count is inconsistent")
    attributed_error_events = sum(
        correlation["serviceAttribution"].get(state, 0)
        for state in COLLECTOR_ATTRIBUTION_ERROR_STATES
    )
    if correlation["eventsWithServiceAttributionErrors"] != attributed_error_events:
        raise RuntimeError("collector service-attribution errors disagree with statuses")
    if "spool" in stats:
        validate_spool_summary(stats["spool"], expected_messages=stats["messages"],
                               expected_events=stats["records_ok"],
                               expected_bad_records=stats["records_bad"])
    if has_attribution:
        validate_collector_attribution_binding(
            stats,
            runtime_images_path=runtime_images_path,
            require_candidate=require_attribution_binding,
        )
    return stats


def validate_spool_summary(
    summary: object,
    *,
    expected_messages: int,
    expected_events: int,
    expected_bad_records: int,
) -> dict:
    """Type and reconcile the collector's terminal spool projection."""

    if not isinstance(summary, dict) or set(summary) != COLLECTOR_SPOOL_FIELDS:
        raise RuntimeError("collector spool summary fields differ")
    integer_fields = (
        "deliveryCount", "uniqueBodyCount", "duplicateBodyCount", "rawBodyBytes",
        "spoolBytes", "replayedEventCount", "replayedRecordFailures",
    )
    if any(not isinstance(summary.get(field), int) or isinstance(summary.get(field), bool)
           or summary[field] < 0 for field in integer_fields):
        raise RuntimeError("collector spool counters are invalid")
    if (summary.get("schemaVersion") != 1
            or summary.get("path") != SPOOL_ARTIFACT_NAME
            or summary.get("sealed") is not True
            or summary.get("complete") is not True
            or summary.get("blockers") != []):
        raise RuntimeError("collector spool is not terminally complete")
    for field in ("artifactSha256", "terminalDigestSha256"):
        if not isinstance(summary.get(field), str) or not SHA256_RE.fullmatch(summary[field]):
            raise RuntimeError(f"collector spool {field} is invalid")
    if (summary["deliveryCount"] != expected_messages
            or summary["uniqueBodyCount"] != expected_messages
            or summary["duplicateBodyCount"] != 0
            or summary["replayedEventCount"] != expected_events
            or summary["replayedRecordFailures"] != expected_bad_records):
        raise RuntimeError("collector spool counters do not reconcile")
    if summary["spoolBytes"] <= summary["rawBodyBytes"]:
        raise RuntimeError("collector spool byte counts are impossible")
    return summary


# F-ADH-074: fault-regime exposure tolerance.
#
# A canonicality rule calibrated on the no-fault baseline fires on a legitimate
# variant.  Scoped by *record timestamp* to the recorded exposure window, never
# by index and never blanket on `fault != "none"`: loss outside the window is a
# real pipeline defect and must keep blocking.  Campaign #6's auth-freeze abort
# is the reference case -- its loss happened ~5.2 s after the intervention
# ended (broker closed the AMQP connection on a missed heartbeat mid-pause, the
# post-resume publish hit a broken pipe), i.e. *outside* the 0.512 s settle, so
# it stays blocked under this rule.  That is the acceptance criterion for the
# tolerance, not a limitation of it.  The cause is fixed producer-side by
# F-ADH-073 (broker heartbeat 0).
# The kieker queue is bounded at x-max-length 50000. Boundary samples alone
# cannot see a mid-window burst that approaches or crosses that limit and then
# drains before the closing sample, so the depth is sampled across the window.
QUEUE_DEPTH_SAMPLE_SECONDS = 5.0
QUEUE_DEPTH_BLOCK_THRESHOLD = 25_000
EXPOSURE_MAX_SETTLE_SECONDS = 30.0
EXPOSURE_SETTLE_MARGIN_SECONDS = 0.0
# F-ADH-076: a conflicting-native-identity record parks None on the depth stack
# (kieker_native), so its in-window children resolve as
# ambiguous-parent-native-identity.  Same loss, child-side name; campaign #7
# died on exactly 3 such events 26-33 s into a proven auth freeze while the 55
# parents were tolerated.
EXPOSURE_TOLERABLE_ERROR_PREFIXES = (
    "missing-parent-at-depth-", "conflicting-native-identity",
    "ambiguous-parent-native-identity",
)
# Mirrors kieker_native.UNWOVEN_ROOT_PARENT_ERROR; that error is already netted
# out by the unwoven-root rule (F-ADH-064), so it must not be counted twice.
UNWOVEN_ROOT_PARENT_ERROR = "missing-parent-at-depth-0"
# F-ADH-084: restarting a container restarts its Kieker monitoring controller,
# which republishes a KiekerMetadataRecord banner. This parser handles only
# execution records, so the banner's container is rejected whole and shows up as
# an anonymous containers_bad=1 with records_bad=0 -- the crash arm's own
# signature, not loss. Mirrors kieker_native.NON_EXECUTION_RECORD_CLASSES.
NON_EXECUTION_RECORD_CLASSES = frozenset({
    "kieker.common.record.misc.KiekerMetadataRecord",
})


def exposure_window(intervention: dict | None, fault: str) -> dict | None:
    """[onset lower bound, readiness observation] in epoch seconds, or None.

    The lower bound is the scheduled onset when retained (F-ADH-085 below),
    otherwise actualOnsetWall.

    None whenever there is no proven intervention to attribute loss to, so a
    no-fault cell can never carry a tolerance.
    """
    if fault == "none" or not isinstance(intervention, dict):
        return None
    if intervention.get("successful") is not True:
        return None
    readiness = intervention.get("readiness")
    if not isinstance(readiness, dict):
        return None
    try:
        onset = datetime.fromisoformat(intervention["actualOnsetWall"]).timestamp()
        offset = datetime.fromisoformat(intervention["actualOffsetWall"]).timestamp()
        observed = datetime.fromisoformat(readiness["observedAtWall"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return None
    settle = observed - offset
    if offset < onset or not 0.0 <= settle <= EXPOSURE_MAX_SETTLE_SECONDS:
        return None
    # F-ADH-085: actualOnsetWall is the first `docker inspect` taken AFTER the
    # pause/stop command returned, so the container was already frozen for up
    # to one command duration before it (0.18-0.30 s for pause, ~11 s for stop
    # across campaigns #6-#12). Records logged inside that span are the
    # intervention's own loss, not a defect: TeaStore #12 aborted on an auth
    # trace logged 13 ms before the sample. The controller sleeps until the
    # shared barrier + fault_at before issuing the command, so the scheduled
    # onset is the earliest instant the freeze can have begun and bounds the
    # window from below. Absent, unreadable, later than the sample, or further
    # back than the settle bound, the strict sample stays the start.
    start = onset
    scheduled = (intervention.get("measurementBarrier") or {}).get("scheduledOnsetWall")
    if isinstance(scheduled, str):
        try:
            candidate = datetime.fromisoformat(scheduled).timestamp()
        except ValueError:
            candidate = None
        if candidate is not None and 0.0 <= onset - candidate <= EXPOSURE_MAX_SETTLE_SECONDS:
            start = candidate
    return {
        "startEpoch": start,
        "endEpoch": observed + EXPOSURE_SETTLE_MARGIN_SECONDS,
        "settleSeconds": settle,
        "marginSeconds": EXPOSURE_SETTLE_MARGIN_SECONDS,
    }


def _logging_seconds(event: dict) -> float:
    """Kieker loggingTimestamp in epoch seconds, falling back to tin."""
    return float(event.get("collector_timestamp") or event["timestamp"])


def container_parse_failure_tolerable(
    failure: object, window: dict | None, intervention: dict | None,
) -> bool:
    """Is one rejected AMQP container the intervention's own restart banner?

    Every conjunct must hold, and each one is read from retained bytes:

    1. there is a proven exposure window (so no cost cell can ever tolerate);
    2. the container declared only non-execution record classes;
    3. no execution record parsed out of it, so the rejection discarded no
       measurement at all;
    4. its own logging timestamp lies inside the window;
    5. the only container identifiers it names are the container this
       intervention itself stopped.

    Anything else -- a different container, a different class, an unreadable
    timestamp, one lost execution -- is residual and keeps blocking.
    """
    if window is None or not isinstance(failure, dict) or not isinstance(intervention, dict):
        return False
    classes = failure.get("recordClasses")
    if not isinstance(classes, list) or not classes:
        return False
    if any(name not in NON_EXECUTION_RECORD_CLASSES for name in classes):
        return False
    if failure.get("parsedExecutionRecords") != 0:
        return False
    stamp = failure.get("loggingTimestampNs")
    if not isinstance(stamp, int) or isinstance(stamp, bool):
        return False
    if not window["startEpoch"] <= stamp / 1e9 <= window["endEpoch"]:
        return False
    target = intervention.get("targetContainerId")
    identifiers = failure.get("registryContainerIds")
    if not isinstance(target, str) or not target or not isinstance(identifiers, list):
        return False
    if not identifiers:
        return False
    return all(isinstance(name, str) and name and target.startswith(name)
               for name in identifiers)


def exposure_tolerance(events: list, intervention: dict | None, *, fault: str,
                       container_failures: object = ()) -> dict:
    """Split correlation errors, EOI gaps and rejected containers into
    tolerated vs residual.

    Tolerated requires the loss to be bounded in time on *both* sides: the
    sequence resumed inside the window, and a retained execution that was still
    open when it resumed also completed inside the window.  Loss that cannot be
    bounded that way is residual and still blocks.
    """
    window = exposure_window(intervention, fault)
    failures = list(container_failures or ())
    result = {
        "schemaVersion": 1,
        "rule": "timestamp-scoped-exposure-tolerance-v2",
        "fault": fault,
        "applied": window is not None,
        "window": window,
        "toleratedCorrelationErrorEvents": 0,
        "toleratedEoiGapTraces": 0,
        "toleratedMissingEoiCount": 0,
        "toleratedContainerParseFailures": 0,
        "residualCorrelationErrorEvents": 0,
        "residualEoiGapTraces": 0,
        "residualMissingEoiCount": 0,
        "residualContainerParseFailures": 0,
        # Reported, never hidden: whatever was rejected stays in the receipt.
        "containerParseFailures": failures,
    }
    for failure in failures:
        if container_parse_failure_tolerable(failure, window, intervention):
            result["toleratedContainerParseFailures"] += 1
        else:
            result["residualContainerParseFailures"] += 1
    if window is None:
        return result
    low, high = window["startEpoch"], window["endEpoch"]

    def inside(value: float) -> bool:
        return low <= value <= high

    by_trace: dict = {}
    for event in events:
        errors = [name for name in (event.get("correlation_errors") or [])
                  if name != UNWOVEN_ROOT_PARENT_ERROR]
        if errors:
            tolerable = all(name.startswith(EXPOSURE_TOLERABLE_ERROR_PREFIXES)
                            for name in errors)
            if tolerable and inside(_logging_seconds(event)):
                result["toleratedCorrelationErrorEvents"] += 1
            else:
                result["residualCorrelationErrorEvents"] += 1
        index = event.get("eoi")
        if isinstance(index, int) and not isinstance(index, bool) and index >= 0:
            trace = event.get("kieker_trace_id", event.get("trace_id"))
            by_trace.setdefault(trace, {})[index] = event

    for indices in by_trace.values():
        ordered = sorted(indices)
        tolerated = residual = 0
        for previous, following in zip(ordered, ordered[1:]):
            missing = following - previous - 1
            if missing <= 0:
                continue
            resumed_at = float(indices[following]["timestamp"])
            # eoi order is start order, so the lost executions started no later
            # than `resumed_at`; an enclosing execution still open at that
            # moment bounds the loss from above by its own completion.
            enclosing = [_logging_seconds(indices[key]) for key in ordered
                         if key < following and _logging_seconds(indices[key]) >= resumed_at]
            if inside(resumed_at) and enclosing and inside(min(enclosing)):
                tolerated += missing
            else:
                residual += missing
        if residual:
            result["residualEoiGapTraces"] += 1
            result["residualMissingEoiCount"] += residual
        elif tolerated:
            result["toleratedEoiGapTraces"] += 1
        result["toleratedMissingEoiCount"] += tolerated
    return result


def collector_process_blockers(collector_returncode: int, probe_returncode: int | None,
                               stats: dict | None, stats_error: str | None,
                               *, effect_contract: bool = False,
                               require_spool: bool = False,
                               entry_point_woven: bool = True,
                               tolerance: dict | None = None,
                               trace_completeness_deferred: bool = False) -> list[str]:
    """``trace_completeness_deferred`` (traffic sweep only, protocol decision 25): native-parent correlation
    errors, missing woven roots and EOI gaps are not blocked here; the cell validator decides them per journey
    with the shared trace-completeness rule (``validation/candidate_pilot.py``, ``sweep_trace_completeness``).
    Everything else below is unchanged, and without the flag nothing is."""
    blockers = []
    if tolerance is not None and not tolerance.get("applied"):
        counted = sum(value for key, value in tolerance.items()
                      if key.startswith("tolerated") and isinstance(value, int))
        if counted:
            blockers.append(
                "exposure tolerance applied without a proven intervention: "
                f"{counted} events")
            tolerance = None
    if collector_returncode != 0:
        blockers.append(f"collector process failed with return code {collector_returncode}")
    if probe_returncode is not None and probe_returncode != 0:
        blockers.append(f"performance probe failed with return code {probe_returncode}")
    if stats_error:
        blockers.append(f"collector stats invalid: {stats_error}")
    elif stats:
        if stats["acknowledgement_mode"] != "manual":
            blockers.append("collector AMQP acknowledgement mode was not manual")
        if stats["runtime_host_map_loaded"] is not True:
            blockers.append("collector runtime host/service map was not loaded")
        if require_spool and "spool" not in stats:
            blockers.append("collector has no durable terminal body spool")
        elif "spool" in stats:
            try:
                validate_spool_summary(
                    stats["spool"], expected_messages=stats["messages"],
                    expected_events=stats["records_ok"],
                    expected_bad_records=stats["records_bad"],
                )
            except RuntimeError as exc:
                blockers.append(f"collector durable spool invalid: {exc}")
        correlation = stats["correlation"]
        # A missing depth-0 parent is expected when the posture does not weave
        # the trace-starting sensor (there is no root to observe). Every other
        # correlation error, and any missing root when the entry point IS woven,
        # is a genuine defect and still blocks. See F-ADH-064.
        unwoven_root = correlation.get("eventsWithUnwovenRootParent", 0)
        # F-ADH-083: the harness's own readiness probes (wait_ready() after a
        # fault recovery) mint parentless traces; when all four conjuncts of
        # kieker_native.probe_orphan_root_indices hold they are counted here,
        # not treated as lost roots. Any other missing root still blocks.
        probe_orphans = correlation.get("eventsWithProbeOrphanRoot", 0)
        if probe_orphans > unwoven_root:
            blockers.append("collector probe-orphan-root count is inconsistent")
            probe_orphans = 0
        if probe_orphans and not effect_contract:
            # wait_ready() runs before the purge on cost cells, so any probe
            # orphan inside a cost window is a purge leak, not the harness.
            blockers.append(
                f"collector readiness-probe orphans on cost evidence: {probe_orphans} events")
        tolerated_events = (tolerance or {}).get("toleratedCorrelationErrorEvents", 0)
        genuine_errors = (
            correlation["eventsWithCorrelationErrors"] - unwoven_root - tolerated_events
        )
        if genuine_errors != 0 and not trace_completeness_deferred:
            blockers.append(
                "collector native parent correlation errors: "
                f"{genuine_errors} events"
                + (f" ({tolerated_events} tolerated inside the exposure window)"
                   if tolerated_events else "")
            )
        if unwoven_root - probe_orphans != 0 and entry_point_woven and not trace_completeness_deferred:
            blockers.append(
                "collector missing native trace roots while the entry point is "
                f"woven: {unwoven_root - probe_orphans} events"
                + (f" ({probe_orphans} readiness-probe orphans excused)"
                   if probe_orphans else "")
            )
        if correlation["eventsWithCorrelationWarnings"] != 0:
            blockers.append(
                "collector native correlation/replay warnings: "
                f"{correlation['eventsWithCorrelationWarnings']} events"
            )
        if correlation["eventsWithServiceAttributionErrors"] != 0:
            blockers.append(
                "collector service-attribution errors: "
                f"{correlation['eventsWithServiceAttributionErrors']} events"
            )
        completeness = correlation["traceCompleteness"]
        tolerated_traces = (tolerance or {}).get("toleratedEoiGapTraces", 0)
        tolerated_indices = (tolerance or {}).get("toleratedMissingEoiCount", 0)
        if completeness["tracesWithEoiGaps"] - tolerated_traces != 0 and not trace_completeness_deferred:
            blockers.append(
                "collector native EOI completeness gaps: "
                f"{completeness['missingEoiCount'] - tolerated_indices} missing "
                f"indices across {completeness['tracesWithEoiGaps'] - tolerated_traces} traces"
            )
        # F-ADH-084: a rejected container is netted out only when the retained
        # bytes prove it is the intervention's own restart banner (see
        # container_parse_failure_tolerable). The diagnostics must account for
        # every rejection, otherwise the tolerance is not trusted at all.
        tolerated_containers = (tolerance or {}).get("toleratedContainerParseFailures", 0)
        declared = (tolerance or {}).get("containerParseFailures")
        if declared is not None and len(declared) != stats["containers_bad"]:
            blockers.append(
                "collector container parse diagnostics do not account for every "
                f"rejection: {len(declared)} described, {stats['containers_bad']} counted"
            )
            tolerated_containers = 0
        if tolerated_containers > stats["containers_bad"]:
            blockers.append("collector container parse tolerance is inconsistent")
            tolerated_containers = 0
        genuine_containers = stats["containers_bad"] - tolerated_containers
        if genuine_containers != 0:
            blockers.append(
                "collector container parse failures: "
                f"{genuine_containers} containers"
                + (f" ({tolerated_containers} tolerated inside the exposure window)"
                   if tolerated_containers else "")
            )
        maximum_records_bad = 1 if effect_contract else 0
        if stats["records_bad"] > maximum_records_bad:
            blockers.append(
                "collector record parse failures exceed the "
                f"{'effect-smoke' if effect_contract else 'cost'} allowance: "
                f"{stats['records_bad']} records"
            )
    return blockers


def collector_event_blockers(events: list, stats: dict | None) -> list[str]:
    """Recompute nested collector counters from retained events.

    The stderr summary is typed at ingestion, but it is still producer-authored.
    This replay prevents a flattering all-zero error summary from hiding defects
    that remain visible in ``traces.json``.
    """
    if stats is None:
        return []
    blockers: list[str] = []
    if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
        return ["collector retained events are not a list of objects"]
    parent_states: dict[str, int] = {}
    attribution_states: dict[str, int] = {}
    correlation_errors = 0
    correlation_warnings = 0
    attribution_errors = 0
    for event in events:
        parent = event.get("parent_resolution")
        attribution = event.get("service_attribution_status")
        parent_states[parent] = parent_states.get(parent, 0) + 1
        attribution_states[attribution] = attribution_states.get(attribution, 0) + 1
        correlation_errors += bool(event.get("correlation_errors"))
        correlation_warnings += bool(event.get("correlation_warnings"))
        attribution_errors += bool(event.get("service_attribution_errors"))
    native = native_collector_module()
    observed = {
        "events": len(events),
        "parentResolution": dict(sorted(parent_states.items())),
        "serviceAttribution": dict(sorted(attribution_states.items())),
        "eventsWithCorrelationErrors": correlation_errors,
        "eventsWithUnwovenRootParent": native.count_unwoven_root_parents(events),
        "eventsWithProbeOrphanRoot": native.count_probe_orphan_roots(events),
        "eventsWithCorrelationWarnings": correlation_warnings,
        "eventsWithServiceAttributionErrors": attribution_errors,
        "traceCompleteness": native.trace_completeness(
            native.collect_trace_eois(events)),
    }
    if stats["correlation"] != observed:
        blockers.append("collector correlation summary differs from retained events")
    return blockers


def analysis_contract(fault: str) -> dict:
    """Return the mutually exclusive scientific claim surface for one run."""
    if fault == "none":
        return {
            "analysisKind": "cost", "resourceUse": "cost-proxy",
            "usesPerformanceProbe": True,
        }
    return {
        "analysisKind": "effect", "resourceUse": "diagnostic-only",
        "usesPerformanceProbe": False,
    }


def expected_workload_return_code(fault: str, workload: dict) -> int:
    """Bind fixed-load exit status to retained outcomes exactly as the producer does."""

    has_unsuccessful_journey = (
        workload.get("failed", 0) > 0 or workload.get("timedOut", 0) > 0
    )
    return 2 if has_unsuccessful_journey else 0


def workload_process_blockers(fault: str, workload: dict, returncode: int) -> list[str]:
    """Check process status without confusing expected fault effects with failure."""

    blockers: list[str] = []
    expected = expected_workload_return_code(fault, workload)
    if returncode != expected:
        blockers.append(
            "workload process return code differs from retained terminal outcomes: "
            f"expected {expected}, got {returncode}"
        )
    if fault == "none" and (
        workload.get("failed", 0) > 0 or workload.get("timedOut", 0) > 0
    ):
        blockers.append(
            "workload failures: "
            f"{workload.get('failed', 0)} failed, "
            f"{workload.get('timedOut', 0)} timed out / {workload.get('offered')} offered"
        )
    return blockers


def measurement_participants(fault: str) -> list[str]:
    participants = ["workload", "collector"]
    if fault == "none":
        participants.insert(1, "performance-probe")
    else:
        participants.append("intervention-controller")
    return participants


def performance_probe_command(
    fault: str, run_dir: Path, duration: float, barrier_epoch: float, barrier_id: str,
) -> list[str] | None:
    """Build the strict cost probe command; effect runs deliberately have none."""
    if fault != "none":
        return None
    return [
        "/usr/bin/python3", "-I", "modules/teastore/collectors/performance_probe_v3.py",
        "--project", project_name(), "--duration", str(duration),
        "--interval", str(RESOURCE_INTERVAL_SECONDS),
        "--command-timeout", str(RESOURCE_COMMAND_TIMEOUT_SECONDS),
        "--maximum-start-lateness", str(RESOURCE_MAXIMUM_START_LATENESS_SECONDS),
        "--output", str(run_dir / "resources.json"),
        "--start-at-epoch", str(barrier_epoch), "--barrier-id", barrier_id,
        "--exclude-service", "rabbitmq", "--exclude-service", "db",
        "--exclude-service", "registry",
        *[argument for service in APP_SERVICES
          for argument in ("--require-service", service)],
    ]


def system_probe_command(
    run_dir: Path, duration: float, barrier_epoch: float,
) -> list[str]:
    """Build the cgroup-v2 system probe command; unlike the cost probe it runs in every cell."""
    return [
        "/usr/bin/python3", "-I", "modules/teastore/collectors/system_probe.py",
        "--project", project_name(), "--duration", str(duration),
        "--interval", str(SYSTEM_SAMPLE_INTERVAL_SECONDS),
        "--start-at-epoch", str(barrier_epoch),
        "--output", str(run_dir / SYSTEM_SAMPLES_ARTIFACT),
        *[argument for service in APP_SERVICES
          for argument in ("--require-service", service)],
    ]


def _communicate_with_watchdog(
    process: subprocess.Popen, timeout: float,
    heartbeat_path: Path, no_progress_timeout: float,
) -> tuple[str, str]:
    """Wait for the child while its heartbeat file keeps advancing.

    Raises subprocess.TimeoutExpired when the hard cap elapses or when the
    heartbeat mtime has not changed for no_progress_timeout seconds; the
    exception carries no_heartbeat_progress=True in the stalled case so the
    join proof can name the cause (F-ADH-061). Freshness is judged by mtime
    *changes* against a local monotonic clock, never by comparing mtime to
    wall time, so clock skew cannot fake or hide progress.
    """
    hard_deadline = time.monotonic() + timeout
    last_progress = time.monotonic()
    last_mtime: float | None = None
    while True:
        remaining = hard_deadline - time.monotonic()
        poll = max(0.05, min(5.0, no_progress_timeout / 4.0, remaining))
        try:
            return process.communicate(timeout=poll)
        except subprocess.TimeoutExpired:
            pass
        try:
            mtime = heartbeat_path.stat().st_mtime
        except OSError:
            mtime = None
        if mtime is not None and mtime != last_mtime:
            last_mtime = mtime
            last_progress = time.monotonic()
        stalled = time.monotonic() - last_progress >= no_progress_timeout
        if time.monotonic() >= hard_deadline or stalled:
            exc = subprocess.TimeoutExpired(process.args, timeout)
            exc.no_heartbeat_progress = stalled
            raise exc


def join_child_process(process: subprocess.Popen, timeout: float, *,
                       heartbeat_path: Path | None = None,
                       no_progress_timeout: float | None = None) -> tuple[str, str, dict]:
    """Join one exact child; on timeout/error terminate, then kill, and always wait.

    With heartbeat_path and no_progress_timeout, the join additionally fails
    closed as soon as the child stops advancing the heartbeat file, so timeout
    can be a generous hard cap instead of a guess at data-proportional work.
    """
    proof = {
        "pid": process.pid, "command": list(process.args), "timeoutSeconds": timeout,
        "noProgressTimeoutSeconds": no_progress_timeout,
        "timedOut": False, "communicationError": None,
        "terminateSent": False, "killSent": False,
        "joined": False, "returnCode": None,
    }
    stdout = ""
    stderr = ""

    def text(value: str | bytes | None) -> str:
        if value is None:
            return ""
        return value.decode(errors="replace") if isinstance(value, bytes) else value

    needs_stop = False
    try:
        if heartbeat_path is not None and no_progress_timeout is not None:
            stdout, stderr = _communicate_with_watchdog(
                process, timeout, heartbeat_path, no_progress_timeout)
        else:
            stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proof["timedOut"] = True
        if getattr(exc, "no_heartbeat_progress", False):
            proof["communicationError"] = (
                f"no heartbeat progress for {no_progress_timeout}s")
        stdout, stderr = text(exc.stdout), text(exc.stderr)
        needs_stop = True
    except Exception as exc:  # noqa: BLE001 - any communication error must stop the exact child
        proof["communicationError"] = f"{type(exc).__name__}: {exc}"
        needs_stop = True

    if needs_stop:
        try:
            process.terminate()
            proof["terminateSent"] = True
        except Exception as exc:  # noqa: BLE001 - escalate to kill below
            proof["communicationError"] = (
                f"{proof['communicationError'] + '; ' if proof['communicationError'] else ''}"
                f"terminate: {type(exc).__name__}: {exc}")
        try:
            stdout, stderr = process.communicate(timeout=10)
        except Exception as exc:  # TimeoutExpired and any other failure both require kill
            if isinstance(exc, subprocess.TimeoutExpired):
                proof["timedOut"] = True
                stdout, stderr = text(exc.stdout) or stdout, text(exc.stderr) or stderr
            else:
                proof["communicationError"] = (
                    f"{proof['communicationError'] + '; ' if proof['communicationError'] else ''}"
                    f"post-terminate communicate: {type(exc).__name__}: {exc}")
            process.kill()
            proof["killSent"] = True
            try:
                stdout, stderr = process.communicate(timeout=10)
            except Exception as final_exc:  # noqa: BLE001 - wait is the final exact-child fallback
                proof["communicationError"] = (
                    f"{proof['communicationError'] + '; ' if proof['communicationError'] else ''}"
                    f"post-kill communicate: {type(final_exc).__name__}: {final_exc}")
                process.wait(timeout=10)

    if process.poll() is None:
        process.kill()
        proof["killSent"] = True
        process.wait(timeout=10)
    proof["returnCode"] = process.returncode
    proof["joined"] = process.poll() is not None
    if not proof["joined"]:
        raise RuntimeError(f"child process {process.pid} could not be joined")
    return text(stdout), text(stderr), proof


def container_state(container: str, *, with_cpu_quota: bool = False) -> dict:
    result = command(["docker", "inspect", container], check=False)
    if result.returncode:
        absent = {"exists": False, "running": False, "paused": False,
                  "returnCode": result.returncode, "stderr": result.stderr}
        if with_cpu_quota:
            absent["nanoCpus"] = None
        return absent
    inspected = json.loads(result.stdout)[0]
    state = inspected["State"]
    observed = {"exists": True, "running": bool(state["Running"]), "paused": bool(state["Paused"]),
                "status": state["Status"], "returnCode": 0}
    if with_cpu_quota:
        # Traffic sweep CPU throttle: the quota as the daemon holds it (0 = unset).
        observed["nanoCpus"] = int((inspected.get("HostConfig") or {}).get("NanoCpus") or 0)
    return observed


def host_nanocpus() -> int:
    """Every CPU the daemon sees, as NanoCPUs: the most ``docker update --cpus`` accepts.

    ``docker update --cpus 0`` is a no-op (the daemon skips a zero NanoCPUs; measured on fb14srv4,
    Hotel LMT pilot 2026-09-28), so a throttle is lifted by raising the quota to the whole host.
    """
    result = command(["docker", "info", "--format", "{{.NCPU}}"], check=False)
    value = result.stdout.strip()
    if result.returncode != 0 or not value.isdigit() or int(value) < 1:
        raise RuntimeError("docker info did not report the host CPU count")
    return int(value) * 1_000_000_000


def wait_ready_stamped(probes: list, anchor_monotonic: float, timeout: int = 240, *,
                       not_before_monotonic: float | None = None) -> None:
    """``wait_ready`` with every SUT request stamped (traffic sweep).

    The readiness requests (GET /status) are served by the SUT inside the measurement, so each one's
    start and end, relative to the measurement barrier, go into the fault receipt and the analysis can
    exclude their windows from sensor scoring.  Predicate and cadence are wait_ready's.

    ``not_before_monotonic`` (campaign B, H10): no request may be issued before this monotonic instant, the end of the
    no-probe window (fault onset to the later of the scored window's end and the revert's return).  A probe that
    would fall inside it raises, so the fault receipt records the error and the cell is invalid; it is not delayed.
    """
    url = "http://localhost:8080/tools.descartes.teastore.webui/status"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not_before_monotonic is not None and time.monotonic() < not_before_monotonic:
            raise RuntimeError("readiness probe inside the no-probe window of the fault (H10)")
        started = time.monotonic() - anchor_monotonic
        result = command(["curl", "-fsS", "--max-time", "10", url], check=False)
        ready = result.returncode == 0 and result.stdout.count("OK") >= 5
        probes.append({
            "phase": "post-revert-readiness", "request": "GET /tools.descartes.teastore.webui/status",
            "startMonotonicOffsetSeconds": started,
            "endMonotonicOffsetSeconds": time.monotonic() - anchor_monotonic,
            "ready": ready,
        })
        if ready:
            return
        time.sleep(5)
    raise RuntimeError("TeaStore readiness failed")


FREEZE_EVENT_ACTIONS = ("pause", "unpause")
FREEZE_EVENTS_TIMEOUT_SECONDS = 30


def freeze_event_offset(event_time_ns: int, barrier_wall_epoch: float, collected_wall_epoch: float,
                        collected_monotonic_offset: float) -> float:
    """A Docker event time (ns, host wall clock) as a monotonic offset from the measurement barrier.

    Linear between two instants whose wall and monotonic readings were taken together: the barrier (offset 0) and the
    collection of the events (``collected_monotonic_offset``).  Over the cell's few minutes this cancels any wall-clock
    slew against the monotonic clock.  The validator recomputes it from the recorded numbers with this same formula.
    """
    span = collected_wall_epoch - barrier_wall_epoch
    if not span > 0:
        raise ValueError("the events were collected before the measurement barrier")
    return (event_time_ns / 1e9 - barrier_wall_epoch) * (collected_monotonic_offset / span)


def collect_freeze_events(target: str, barrier_wall_epoch: float, anchor_monotonic: float,
                          onset_issued_offset: float) -> dict:
    """Replay the Docker pause and unpause events of ``target`` (campaign B, H4), after the revert.

    ``docker events --since --until`` with ``until`` already past returns the daemon's buffered events at once; the
    ``timeout`` wrapper bounds a stuck client.  Only whitelisted fields of each event are kept (no actor attributes).
    A failure is recorded, never raised: the validator blocks the cell on it, so the rest of the receipt is kept.
    """
    collected_wall = time.time()
    collected_monotonic_offset = time.monotonic() - anchor_monotonic
    since = barrier_wall_epoch + onset_issued_offset - 2.0
    argv = ["timeout", str(FREEZE_EVENTS_TIMEOUT_SECONDS), "docker", "events",
            "--since", "%.3f" % since, "--until", "%.3f" % collected_wall,
            "--filter", f"container={target}", "--filter", "type=container",
            "--filter", "event=pause", "--filter", "event=unpause", "--format", "{{json .}}"]
    record: dict[str, Any] = {"command": argv, "returnCode": None, "error": None, "rows": []}
    try:
        result = command(argv, check=False)
        record["returnCode"] = result.returncode
        if result.returncode != 0:
            record["error"] = f"docker events returned {result.returncode}: {result.stderr.strip()[:300]}"
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            actor = event.get("Actor") if isinstance(event.get("Actor"), dict) else {}
            time_ns = event.get("timeNano")
            record["rows"].append({
                "action": event.get("Action", event.get("status")),
                "type": event.get("Type"),
                "containerId": actor.get("ID", event.get("id")),
                "timeNano": time_ns,
                "monotonicOffsetSeconds": freeze_event_offset(
                    time_ns, barrier_wall_epoch, collected_wall, collected_monotonic_offset),
            })
    except Exception as exc:  # noqa: BLE001 - kept as evidence; the validator blocks on it
        record["error"] = f"{type(exc).__name__}: {exc}"
    return {
        "clock": {
            "barrierWallEpochSeconds": barrier_wall_epoch, "barrierMonotonicOffsetSeconds": 0.0,
            "collectedWallEpochSeconds": collected_wall,
            "collectedMonotonicOffsetSeconds": collected_monotonic_offset,
            "mapping": "offset = (event wall - barrier wall) x collected offset / (collected wall - barrier wall)",
        },
        "events": record,
    }


def build_freeze_stamps(fault: str, target: str, harness: Mapping[str, Any], stamps: Mapping[str, Any],
                        readbacks: list, barrier_wall_epoch: float, anchor_monotonic: float) -> dict:
    """The ``sweep.freezeStamps`` record of one fault cell (H4, record-not-block).

    ``status`` is ``recorded`` with no failures, else ``missing`` with every reason in ``failures`` and their number in
    ``failureCount``.  Never raises: a failure to collect or shape the record is itself a reason.
    """
    failures: list = []
    clock = events = None
    try:
        if fault == "auth-freeze":
            collected = collect_freeze_events(
                target, barrier_wall_epoch, anchor_monotonic, stamps["onsetCommandIssuedMonotonicOffsetSeconds"])
            clock, events = collected["clock"], collected["events"]
            if events["error"] is not None:
                failures.append(f"docker events query: {events['error']}")
            elif [row["action"] for row in events["rows"]] != list(FREEZE_EVENT_ACTIONS):
                failures.append("the target's Docker events are not exactly one pause then one unpause: %s" % (
                    [row["action"] for row in events["rows"]],))
            elif any(row["containerId"] != target or row["type"] != "container" for row in events["rows"]):
                failures.append("a Docker event names another container or type")
    except Exception as exc:  # noqa: BLE001 - a reason, not a cell failure
        failures.append(f"freeze events: {type(exc).__name__}: {exc}")
    return {
        "schemaVersion": 1, "version": harness["version"], "scenario": fault, "targetContainerId": target,
        "toleranceSeconds": harness["freezeEventToleranceSeconds"],
        "commands": {
            "onsetIssuedMonotonicOffsetSeconds": stamps["onsetCommandIssuedMonotonicOffsetSeconds"],
            "onsetReturnedMonotonicOffsetSeconds": stamps["onsetCommandReturnedMonotonicOffsetSeconds"],
            "revertIssuedMonotonicOffsetSeconds": stamps["revertCommandIssuedMonotonicOffsetSeconds"],
            "revertReturnedMonotonicOffsetSeconds": stamps["revertCommandReturnedMonotonicOffsetSeconds"],
        },
        "readbacks": list(readbacks),
        "clock": clock,
        "events": events,
        "status": "missing" if failures else "recorded",
        "failures": failures,
        "failureCount": len(failures),
    }


def inject_fault(fault: str, fault_at: int, outage: int, run_dir: Path,
                 posture: str = "full", *, measurement_barrier_epoch: float | None = None,
                 measurement_barrier_monotonic: float | None = None,
                 measurement_barrier_id: str | None = None,
                 target_image: dict | None = None,
                 sweep_timing: Mapping[str, Any] | None = None) -> dict:
    """Apply and independently sample a bounded intervention.

    The target-state samples are evidence about the sampled instants only.  They
    deliberately do not claim continuous service unavailability between samples.

    ``sweep_timing`` (traffic sweep only) adds the pre-command onset stamp and the
    revert stamps (F1), the stamped readiness probes, the CPU-throttle fault, and a
    hold timed from the first post-command sample.  Without it the function is the
    frozen epoch's, byte for byte in its receipt.
    """
    sweep = sweep_timing is not None
    if sweep and fault not in ("auth-freeze", "persistence-cpu-throttle"):
        raise ValueError(f"unknown sweep fault: {fault}")
    # Campaign B (H10 probe window, H4 freeze stamps): declared by the plan cell, absent from every earlier epoch's
    # cells, whose receipts stay byte for byte what they were.
    harness = sweep_timing.get("faultHarness") if sweep else None
    if harness is not None and (not isinstance(harness, Mapping) or harness.get("version") != "h4-h10-v1"):
        raise ValueError(f"unknown fault harness declaration: {harness!r}")
    readbacks: list = []
    if not sweep and fault == "persistence-cpu-throttle":
        raise ValueError("the CPU throttle exists only in the traffic sweep")
    service = "auth" if fault == "auth-freeze" else "persistence"
    throttle = fault == "persistence-cpu-throttle"
    controller_monotonic = time.monotonic()
    offset_anchor = (
        measurement_barrier_monotonic
        if measurement_barrier_monotonic is not None else controller_monotonic
    )
    receipt = {
        "schemaVersion": 3,
        "scenario": fault,
        "service": service,
        "independentOfKieker": True,
        "intervalLabel": "intervention-exposure",
        "functionalOutage": None,
        "measurementBarrier": {
            "id": measurement_barrier_id,
            "wall": (
                datetime.fromtimestamp(measurement_barrier_epoch, timezone.utc).isoformat()
                if measurement_barrier_epoch is not None else None
            ),
            "scheduledOnsetSeconds": fault_at,
            "scheduledOnsetWall": (
                datetime.fromtimestamp(
                    measurement_barrier_epoch + fault_at, timezone.utc).isoformat()
                if measurement_barrier_epoch is not None else None
            ),
        },
        "requestedHoldSeconds": outage,
        "targetContainerId": None,
        "targetImage": target_image,
        "preState": None,
        "commandVector": None,
        "commandResult": None,
        "actualOnsetWall": None,
        "actualOnsetMonotonicOffsetSeconds": None,
        "actualOffsetWall": None,
        "actualOffsetMonotonicOffsetSeconds": None,
        "duringStateSamples": [],
        "recoveryAction": None,
        "sameTargetIdentity": False,
        "readiness": None,
        "postState": None,
        "interventionThreadJoined": None,
        "laterInterventionMutationObserved": False,
        "manifested": False,
        "recovered": False,
        "outageHeld": False,
        "successful": False,
        "error": None,
        "operational": {
            "controllerStartedAt": now(),
            "controllerEndedAt": None,
            "commandResults": [],
            "actualHoldSeconds": None,
            "continuousTargetStateProven": False,
        },
    }
    stamps: dict[str, Any] = {}
    if sweep:
        stamps = {
            "onsetCommandIssuedWall": None, "onsetCommandIssuedMonotonicOffsetSeconds": None,
            "onsetCommandReturnedMonotonicOffsetSeconds": None,
            "revertCommandIssuedWall": None, "revertCommandIssuedMonotonicOffsetSeconds": None,
            "revertCommandReturnedMonotonicOffsetSeconds": None,
        }
        receipt["sweep"] = {
            "schemaVersion": 1,
            "onsetSource": "pre-command",
            "commandStamps": stamps,
            "probes": [],
            "throttle": None,
        }
        if harness is not None:
            receipt["sweep"]["probePolicy"] = None
            receipt["sweep"]["freezeStamps"] = None
    target: str | None = None

    def run(args: list[str]) -> dict:
        result = command(args, check=False)
        record = {"command": args, "returnCode": result.returncode,
                  "stdout": result.stdout, "stderr": result.stderr}
        receipt["operational"]["commandResults"].append(record)
        return record

    def sampled_state(phase: str) -> dict:
        observed_at = now()
        observed_offset = time.monotonic() - offset_anchor
        state = container_state(target, with_cpu_quota=True) if throttle else container_state(target)
        if harness is not None:
            # H4: the applied-state readback's own issue and return stamps (the sample's stamp is its issue).
            readbacks.append({
                "phase": phase, "issuedMonotonicOffsetSeconds": observed_offset,
                "returnedMonotonicOffsetSeconds": time.monotonic() - offset_anchor,
                "paused": state.get("paused"), "nanoCpus": state.get("nanoCpus"),
            })
        normalized = {
            "phase": phase,
            "observedAtWall": observed_at,
            "observedAtMonotonicOffsetSeconds": observed_offset,
            "state": state,
        }
        receipt["duringStateSamples"].append(normalized)
        return state

    try:
        if (not isinstance(measurement_barrier_id, str)
                or not re.fullmatch(r"barrier-[0-9a-f]{32}", measurement_barrier_id)
                or isinstance(measurement_barrier_epoch, bool)
                or not isinstance(measurement_barrier_epoch, (int, float))
                or not math.isfinite(measurement_barrier_epoch)
                or isinstance(measurement_barrier_monotonic, bool)
                or not isinstance(measurement_barrier_monotonic, (int, float))
                or not math.isfinite(measurement_barrier_monotonic)):
            raise RuntimeError("fault controller is not bound to a complete shared measurement barrier")
        target = service_container(posture, service)
        receipt["targetContainerId"] = target
        target_image_fields = {
            "containerId", "declaredImage", "containerImageId", "imageInspectId",
            "repoDigests",
        }
        if (not isinstance(target_image, dict) or set(target_image) != target_image_fields
                or target_image.get("containerId") != target
                or not isinstance(target, str) or not CONTAINER_ID_RE.fullmatch(target)
                or not IMAGE_ID_RE.fullmatch(str(target_image.get("containerImageId", "")))
                or not IMAGE_ID_RE.fullmatch(str(target_image.get("imageInspectId", "")))
                or not isinstance(target_image.get("declaredImage"), str)
                or not isinstance(target_image.get("repoDigests"), list)):
            raise RuntimeError("fault target image proof is absent or bound to another container")
        receipt["preState"] = (
            container_state(target, with_cpu_quota=True) if throttle else container_state(target))
        if (not receipt["preState"].get("exists") or not receipt["preState"].get("running")
                or receipt["preState"].get("paused")):
            raise RuntimeError(f"fault target is not ready before intervention: {receipt['preState']}")
        host_quota = None
        if throttle:
            host_quota = host_nanocpus()
            throttle_quota = int(sweep_timing["cpuThrottleNanoCpus"])
            receipt["sweep"]["throttle"] = {
                "cpus": sweep_timing["cpuThrottleCpus"], "nanoCpus": throttle_quota,
                "preNanoCpus": receipt["preState"]["nanoCpus"], "hostNanoCpus": host_quota,
                "revertCpus": str(host_quota // 1_000_000_000),
            }
            if receipt["preState"]["nanoCpus"] not in (0, host_quota):
                raise RuntimeError("fault target CPU quota is already set before intervention")
        if measurement_barrier_monotonic is None:
            time.sleep(fault_at)
        else:
            delay = measurement_barrier_monotonic + fault_at - time.monotonic()
            if delay < -1.0:
                raise RuntimeError("fault controller missed the shared measurement barrier")
            if delay > 0:
                time.sleep(delay)
        if throttle:
            onset_command = ["docker", "update", "--cpus", str(sweep_timing["cpuThrottleCpus"]), target]
        else:
            onset_command = (
                compose(posture, "pause", "auth")
                if fault == "auth-freeze" else compose(posture, "stop", "persistence")
            )
        receipt["commandVector"] = onset_command
        if sweep:
            # F1 / F-ADH-085: the onset stamp is taken immediately before the command.
            stamps["onsetCommandIssuedWall"] = now()
            stamps["onsetCommandIssuedMonotonicOffsetSeconds"] = time.monotonic() - offset_anchor
        receipt["commandResult"] = run(onset_command)
        if sweep:
            stamps["onsetCommandReturnedMonotonicOffsetSeconds"] = time.monotonic() - offset_anchor
        if fault == "auth-freeze":
            during_state = sampled_state("manifested")
            receipt["manifested"] = during_state["paused"]
        elif throttle:
            during_state = sampled_state("manifested")
            receipt["manifested"] = (
                during_state["exists"] and during_state["running"] and not during_state["paused"]
                and during_state["nanoCpus"] == int(sweep_timing["cpuThrottleNanoCpus"]))
        elif fault == "persistence-crash":
            during_state = sampled_state("manifested")
            receipt["manifested"] = during_state["exists"] and not during_state["running"]
        else:
            raise ValueError(f"unknown fault: {fault}")
        first_sample = receipt["duringStateSamples"][0]
        receipt["actualOnsetWall"] = first_sample["observedAtWall"]
        receipt["actualOnsetMonotonicOffsetSeconds"] = first_sample[
            "observedAtMonotonicOffsetSeconds"]
        if sweep:
            # The hold is timed from the first post-command sample, so the samples' own
            # durations are not added on top of it (F1 bounds the commands' distance).
            first_monotonic = offset_anchor + first_sample["observedAtMonotonicOffsetSeconds"]
            for phase, fraction in (("hold-midpoint", 0.5), ("hold-end", 1.0)):
                while time.monotonic() < first_monotonic + outage * fraction:
                    time.sleep(max(0.0, first_monotonic + outage * fraction - time.monotonic()))
                sampled_state(phase)
        else:
            time.sleep(outage / 2)
            sampled_state("hold-midpoint")
            time.sleep(outage / 2)
            sampled_state("hold-end")
        final_sample = receipt["duringStateSamples"][-1]
        receipt["actualOffsetWall"] = final_sample["observedAtWall"]
        receipt["actualOffsetMonotonicOffsetSeconds"] = final_sample[
            "observedAtMonotonicOffsetSeconds"]
        receipt["operational"]["actualHoldSeconds"] = (
            receipt["actualOffsetMonotonicOffsetSeconds"]
            - receipt["actualOnsetMonotonicOffsetSeconds"]
        )
        if fault == "auth-freeze":
            expected_during = lambda state: state.get("exists") and state.get("running") and state.get("paused")
            recovery_vector = compose(posture, "unpause", "auth")
        elif throttle:
            expected_during = lambda state: (
                state.get("exists") and state.get("running") and not state.get("paused")
                and state.get("nanoCpus") == int(sweep_timing["cpuThrottleNanoCpus"]))
            recovery_vector = ["docker", "update", "--cpus", str(host_quota // 1_000_000_000), target]
        else:
            expected_during = lambda state: state.get("exists") and not state.get("running")
            recovery_vector = compose(posture, "start", "persistence")
        receipt["manifested"] = receipt["manifested"] and all(
            expected_during(sample["state"]) for sample in receipt["duringStateSamples"]
        )
        if sweep:
            stamps["revertCommandIssuedWall"] = now()
            stamps["revertCommandIssuedMonotonicOffsetSeconds"] = time.monotonic() - offset_anchor
        recovery_result = run(recovery_vector)
        if sweep:
            stamps["revertCommandReturnedMonotonicOffsetSeconds"] = time.monotonic() - offset_anchor
        no_probe_until = None
        if harness is not None:
            # H10: no readiness probe from the onset command's issue to the later of the scored window's end and the
            # revert's return.  The probes below start after the revert, so this records and enforces what the
            # sweep's order of operations already gave.
            scored_end = float(fault_at) + float(outage)
            no_probe_until = max(scored_end, stamps["revertCommandReturnedMonotonicOffsetSeconds"])
            receipt["sweep"]["probePolicy"] = {
                "version": harness["version"],
                "noProbeFromMonotonicOffsetSeconds": stamps["onsetCommandIssuedMonotonicOffsetSeconds"],
                "scoredWindowEndMonotonicOffsetSeconds": scored_end,
                "noProbeUntilMonotonicOffsetSeconds": no_probe_until,
            }
        receipt["recoveryAction"] = {
            "commandVector": recovery_vector,
            "commandResult": recovery_result,
        }
        if sweep:
            wait_ready_stamped(
                receipt["sweep"]["probes"], offset_anchor,
                **({} if no_probe_until is None else {"not_before_monotonic": offset_anchor + no_probe_until}))
        else:
            wait_ready()
        receipt["postState"] = (
            container_state(target, with_cpu_quota=True) if throttle else container_state(target))
        receipt["sameTargetIdentity"] = service_container(posture, service) == target
        receipt["readiness"] = {
            "predicate": "all-five-application-services-report-OK",
            "observedAtWall": now(),
            "observedAtMonotonicOffsetSeconds": time.monotonic() - offset_anchor,
            "successful": True,
        }
        receipt["recovered"] = (
            receipt["sameTargetIdentity"]
            and receipt["postState"]["running"]
            and not receipt["postState"]["paused"]
            and (not throttle or receipt["postState"].get("nanoCpus") == host_quota)
        )
        if harness is not None:
            # H4 (record, don't block; decision 69): the freeze stamps, collected after the readiness so no query
            # touches the recovery.  A pause also gets the daemon's own pause and unpause events; the throttle has its
            # command and readback stamps only.  Anything that goes wrong here is kept as a reason in
            # ``freezeStamps.failures`` and leaves the receipt (and so the cell) valid; the reader then falls back to
            # [onset command issued, onset command returned].
            receipt["sweep"]["freezeStamps"] = build_freeze_stamps(
                fault, target, harness, stamps, readbacks, float(measurement_barrier_epoch), offset_anchor)
    except Exception as exc:  # noqa: BLE001 - retain exact intervention failure as evidence
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        receipt["operational"]["controllerEndedAt"] = now()
        receipt["outageHeld"] = (
            receipt["operational"].get("actualHoldSeconds") or 0) >= outage
        receipt["successful"] = (receipt["manifested"] and receipt["recovered"] and receipt["outageHeld"] and
                                 receipt["error"] is None and
                                 all(item["returnCode"] == 0 for item in receipt["operational"]["commandResults"]))
        (run_dir / "intervention.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def bind_intervention_thread(receipt: dict, run_dir: Path, *, joined: bool) -> dict:
    """Make thread termination part of the retained, normalized fault truth."""
    receipt["interventionThreadJoined"] = joined
    receipt["successful"] = bool(receipt.get("successful") and joined)
    (run_dir / "intervention.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def teardown_project(posture: str, run_dir: Path) -> tuple[dict, dict]:
    argv = compose(posture, "down", "-v", "--remove-orphans")
    try:
        result = command(argv, output=run_dir / "down-after.log", check=False)
        down = {
            "schemaVersion": 1, "command": argv, "returnCode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr,
        }
    except Exception as exc:  # noqa: BLE001 - preserve teardown failure as evidence
        down = {
            "schemaVersion": 1, "command": argv, "returnCode": None,
            "stdout": "", "stderr": f"{type(exc).__name__}: {exc}",
        }
        (run_dir / "down-after.log").write_text(down["stderr"] + "\n")
    (run_dir / "down-command.json").write_text(json.dumps(down, indent=2, sort_keys=True) + "\n")
    remaining = project_resources()
    (run_dir / "teardown.json").write_text(json.dumps(remaining, indent=2, sort_keys=True) + "\n")
    return down, remaining


def bind_teardown(receipt: dict, down: dict, remaining: dict, run_dir: Path,
                  evidence_label: str) -> None:
    expected_down = compose(receipt["posture"], "down", "-v", "--remove-orphans")
    clean = (
        down.get("command") == expected_down
        and down.get("returnCode") == 0
        and remaining.get("project") == project_name()
        and resources_clean(remaining)
    )
    receipt["teardown"] = {
        "downCommand": down, "projectResources": remaining, "projectClean": clean,
    }
    blockers = receipt["canonicality"]["blockers"]
    if not clean and "compose project teardown incomplete" not in blockers:
        blockers.append("compose project teardown incomplete")
    receipt["canonicality"]["label"] = evidence_label if not blockers else "noncanonical"
    (run_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


def collector_subprocess_environment(
        ambient: dict[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ if ambient is None else ambient)
    environment.pop("SUT_TRACE_HOST_SERVICE_MAP", None)
    environment.update({
        "PYTHONPATH": "modules/teastore",
        "RABBITMQ_AUTO_ACK": "false",
        "SUT_TRACE_SERVICE_REGEX": COLLECTOR_FROZEN_SERVICE_REGEX,
        "SUT_TRACE_SERVICE_MAP": json.dumps(
            COLLECTOR_FROZEN_SERVICE_MAP,
            sort_keys=True,
            separators=(",", ":"),
        ),
    })
    return environment


def capture_candidate_service_logs(
    run_dir: Path,
    runtime_images: Mapping[str, Any],
    *,
    measurement_started_at: str,
    measurement_ended_at: str,
) -> dict[str, Any]:
    """Capture only the two application logs used by candidate path replay.

    The bounds are passed to Docker as separate argv values.  The auth
    container environment is inspected independently so the retained receipt
    can prove that parameter logging was absent or exactly false.
    """

    services = runtime_images.get("services")
    if not isinstance(services, Mapping):
        raise RuntimeError("runtime image proof has no service inventory")
    captures: dict[str, Any] = {}
    for service in ("auth", "persistence"):
        row = services.get(service)
        container_id = row.get("containerId") if isinstance(row, Mapping) else None
        if not isinstance(container_id, str) or CONTAINER_ID_RE.fullmatch(container_id) is None:
            raise RuntimeError(f"candidate {service} container identity is absent")
        argv = [
            "docker", "logs", "--since", measurement_started_at,
            "--until", measurement_ended_at, container_id,
        ]
        result = command(argv, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"bounded candidate log capture failed for {service}")
        payload = result.stdout + result.stderr
        path = run_dir / f"candidate-{service}.log"
        path.write_text(payload, encoding="utf-8")
        captures[service] = {
            "containerId": container_id,
            "command": argv,
            "returnCode": result.returncode,
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }

    auth_id = captures["auth"]["containerId"]
    inspect_argv = [
        "docker", "inspect", "--format", "{{json .Config.Env}}", auth_id,
    ]
    inspected = command(inspect_argv, check=False)
    if inspected.returncode != 0 or inspected.stderr or len(inspected.stdout.splitlines()) != 1:
        raise RuntimeError("candidate LOG_PARAMETERS inspection failed")
    try:
        environment = json.loads(inspected.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("candidate LOG_PARAMETERS inspection is not JSON") from exc
    if not isinstance(environment, list) or any(not isinstance(item, str) for item in environment):
        raise RuntimeError("candidate container environment is not a string list")
    values = [item.split("=", 1)[1] for item in environment if item.startswith("LOG_PARAMETERS=")]
    if not values:
        parameter_state, parameter_value = "absent", None
    elif values == ["false"]:
        parameter_state, parameter_value = "false", "false"
    else:
        raise RuntimeError("LOG_PARAMETERS is duplicated or not exactly false")
    proof = {
        "schemaVersion": 1,
        "measurementWindow": {
            "startedAt": measurement_started_at,
            "endedAt": measurement_ended_at,
        },
        "captures": captures,
        "logParameters": {
            "command": inspect_argv,
            "returnCode": inspected.returncode,
            "state": parameter_state,
            "rawValue": parameter_value,
            "parameterLoggingEnabled": False,
        },
    }
    (run_dir / "candidate-service-log-source.json").write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return proof


def run_one(root: Path, run_id: str, posture: str, args: argparse.Namespace) -> dict:
    """Keep the legacy diagnostic cell entrance permanently non-authorizing."""

    raise RuntimeError(CONSTRUCTION_RUNTIME_BLOCKED)


def _execute_candidate_runtime_slice(
    root: Path, run_id: str, posture: str, args: argparse.Namespace, *,
    expected_image_references: Mapping[str, str],
) -> dict:
    """Run the reviewed lifecycle only for the gate-internal candidate adapter.

    This private slice is not a second CLI.  ``execute_candidate_cell`` derives
    every argument from an already validated immutable contract, and the public
    ``run_one`` above remains blocked before output creation or Docker access.
    """

    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    ownership = {"composeProject": project_name(), "resourcesBefore": project_resources()}
    (run_dir / "ownership-preflight.json").write_text(json.dumps(ownership, indent=2, sort_keys=True) + "\n")
    if not resources_clean(ownership["resourcesBefore"]):
        raise RuntimeError(f"compose namespace is not empty: {ownership['resourcesBefore']}")
    owns_project = False
    receipt: dict | None = None
    collector: subprocess.Popen | None = None
    probe: subprocess.Popen | None = None
    system_probe: subprocess.Popen | None = None
    fault_thread: threading.Thread | None = None
    child_proofs: dict[str, dict] = {}
    child_outputs: dict[str, tuple[str, str]] = {}
    analysis = analysis_contract(args.fault)
    try:
        # Mark ownership before the first mutating command because Compose can create
        # partial resources even when `up` ultimately fails.
        owns_project = True
        command(compose(posture, "up", "-d", "rabbitmq"), output=run_dir / "up-broker.log")
        wait_broker(posture)
        command(compose(posture, "up", "-d"), output=run_dir / "up.log")
        wait_ready()
        runtime_images = runtime_image_proof(
            posture, expected_content_references=expected_image_references,
        )
        runtime_images_path = run_dir / "runtime-images.json"
        runtime_images_path.write_text(
            json.dumps(runtime_images, indent=2, sort_keys=True) + "\n")
        proof = posture_proof(posture)
        (run_dir / "posture-proof.json").write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
        timing = getattr(args, "timing", None)
        # Traffic sweep: warm-up at the plan's warm-up rate (10/s in every cell) on the cell's route, with the
        # plan's timeout; the frozen epoch's argv is unchanged.
        warmup_rate = args.rate if timing is None else timing["warmupJourneysPerSecond"]
        sweep_workload_args = [] if timing is None else [
            "--timeout", str(timing["requestTimeoutSeconds"]), "--journey-kind", timing["journeyKind"],
        ]
        command([
            "/usr/bin/python3", "-I", "modules/teastore/workload/fixed_load.py", "--rate", str(warmup_rate),
            "--duration", str(args.warmup), "--concurrency", str(args.concurrency),
            "--output", str(run_dir / "warmup.json"),
            "--journey-ledger", str(run_dir / "warmup-journey-ledger.jsonl"),
            *sweep_workload_args,
        ], output=run_dir / "warmup.log")
        warmup = json.loads((run_dir / "warmup.json").read_text())
        warmup_ledger_path = run_dir / "warmup-journey-ledger.jsonl"
        validate_journey_evidence(warmup, warmup_ledger_path)
        purge = purge_queue(posture)
        before = queue_state(posture)
        traces = run_dir / "traces.json"
        spool_path = run_dir / SPOOL_ARTIFACT_NAME
        collector = subprocess.Popen([
            "/usr/bin/python3", "-I", "modules/teastore/collectors/kieker_native.py", "--duration", str(args.duration + 30),
            "--inactivity-timeout", "10", "--output", str(traces),
            "--spool", str(spool_path),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=collector_subprocess_environment())
        consumer_state = wait_consumer(posture)
        measurement_barrier_epoch = time.time() + MEASUREMENT_BARRIER_LEAD_SECONDS
        measurement_barrier_monotonic = time.monotonic() + MEASUREMENT_BARRIER_LEAD_SECONDS
        barrier_id = "barrier-" + hashlib.sha256(
            f"{args.descriptor_sha256}\0{run_id}\0{measurement_barrier_epoch:.9f}".encode()
        ).hexdigest()[:32]
        barrier_path = run_dir / "measurement-barrier.json"
        barrier = {
            "schemaVersion": 2,
            "barrierId": barrier_id,
            "createdAt": now(),
            "barrierAt": datetime.fromtimestamp(
                measurement_barrier_epoch, timezone.utc).isoformat(),
            "barrierAtEpoch": measurement_barrier_epoch,
            "barrierMonotonic": measurement_barrier_monotonic,
            "measurementSeconds": args.duration,
            "participants": measurement_participants(args.fault),
            "collectorAcknowledgement": None,
        }
        barrier_path.write_text(json.dumps(barrier, indent=2, sort_keys=True) + "\n")
        resources_path = run_dir / "resources.json"
        probe_command = performance_probe_command(
            args.fault, run_dir, args.duration, measurement_barrier_epoch, barrier_id)
        if probe_command is not None:
            probe = subprocess.Popen(
                probe_command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        system_samples_path = run_dir / SYSTEM_SAMPLES_ARTIFACT
        system_probe = subprocess.Popen(
            system_probe_command(run_dir, args.duration, measurement_barrier_epoch),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        intervention: dict | None = None
        fault_result: dict = {}
        fault_exception: list[str] = []
        barrier_exception: list[str] = []
        broker_state: list[dict] = []

        def acknowledge_collector_barrier() -> None:
            try:
                delay = measurement_barrier_monotonic - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                acknowledged = collector_barrier_acknowledgement(
                    posture, measurement_barrier_monotonic)
                barrier["collectorAcknowledgement"] = acknowledged
                broker_state.append(broker_proof(posture))
                barrier_path.write_text(
                    json.dumps(barrier, indent=2, sort_keys=True) + "\n")
            except Exception as exc:  # noqa: BLE001 - thread failure must reach receipt
                barrier_exception.append(f"{type(exc).__name__}: {exc}")

        depth_samples: list[dict] = []
        depth_exception: list[str] = []

        def sample_queue_depth() -> None:
            try:
                deadline = measurement_barrier_monotonic + args.duration
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return
                    delay = measurement_barrier_monotonic - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                    state = queue_state(posture)
                    depth_samples.append({
                        "monotonicOffsetSeconds": time.monotonic() - measurement_barrier_monotonic,
                        "messages": state["messages"],
                        "consumers": state["consumers"],
                    })
                    time.sleep(min(QUEUE_DEPTH_SAMPLE_SECONDS, max(deadline - time.monotonic(), 0)))
            except Exception as exc:  # noqa: BLE001 - thread failure must reach the receipt
                depth_exception.append(f"{type(exc).__name__}: {exc}")

        barrier_thread = threading.Thread(target=acknowledge_collector_barrier)
        barrier_thread.start()
        depth_thread = threading.Thread(target=sample_queue_depth)
        depth_thread.start()
        if args.fault != "none":
            def apply_intervention() -> None:
                try:
                    fault_result.update(inject_fault(
                        args.fault, args.fault_at, args.outage, run_dir, posture,
                        measurement_barrier_epoch=measurement_barrier_epoch,
                        measurement_barrier_monotonic=measurement_barrier_monotonic,
                        measurement_barrier_id=barrier_id,
                        target_image={key: runtime_images["services"][
                            "auth" if args.fault == "auth-freeze" else "persistence"][key]
                            for key in (
                                "containerId", "declaredImage", "containerImageId",
                                "imageInspectId", "repoDigests",
                            )},
                        **({} if timing is None else {"sweep_timing": timing}),
                    ))
                except Exception as exc:  # noqa: BLE001 - thread exceptions must reach the receipt
                    fault_exception.append(f"{type(exc).__name__}: {exc}")
            fault_thread = threading.Thread(target=apply_intervention)
            fault_thread.start()
        workload_result = command([
            "/usr/bin/python3", "-I", "modules/teastore/workload/fixed_load.py", "--rate", str(args.rate),
            "--duration", str(args.duration), "--concurrency", str(args.concurrency),
            "--output", str(run_dir / "workload.json"),
            "--journey-ledger", str(run_dir / "journey-ledger.jsonl"),
            "--start-at-epoch", str(measurement_barrier_epoch),
            "--barrier-id", barrier_id,
            *sweep_workload_args,
        ], output=run_dir / "workload.log", check=False)
        barrier_thread.join(timeout=args.duration + 30)
        depth_thread.join(timeout=args.duration + 30)
        if fault_thread:
            fault_thread.join(timeout=args.duration + args.outage)
            intervention = fault_result or None
            if intervention is not None:
                bind_intervention_thread(
                    intervention, run_dir, joined=not fault_thread.is_alive())
        if probe is not None:
            probe_out, probe_err, child_proofs["performanceProbe"] = join_child_process(
                probe, args.duration + 90)
            child_outputs["performanceProbe"] = (probe_out, probe_err)
            (run_dir / "probe.log").write_text(probe_out + probe_err)
        system_out, system_err, child_proofs["systemProbe"] = join_child_process(
            system_probe, args.duration + SYSTEM_PROBE_JOIN_SLACK_SECONDS)
        child_outputs["systemProbe"] = (system_out, system_err)
        (run_dir / "system-probe.log").write_text(system_out + system_err)
        collector_heartbeat = native_collector_module().collector_heartbeat_path(
            spool_path)
        collector_out, collector_err, child_proofs["collector"] = join_child_process(
            collector, COLLECTOR_JOIN_HARD_CAP_SECONDS,
            heartbeat_path=collector_heartbeat,
            no_progress_timeout=COLLECTOR_NO_PROGRESS_TIMEOUT_SECONDS)
        collector_heartbeat.unlink(missing_ok=True)
        child_outputs["collector"] = (collector_out, collector_err)
        (run_dir / "collector.stdout").write_text(collector_out)
        (run_dir / "collector.stderr").write_text(collector_err)
        child_processes_path = run_dir / "child-processes.json"
        child_processes_path.write_text(
            json.dumps(child_proofs, indent=2, sort_keys=True) + "\n")
        after = wait_queue_drained(posture)
        broker = broker_state[0] if broker_state else None
        acknowledgement = barrier.get("collectorAcknowledgement")
        consumer_at_start = (
            acknowledgement.get("queueState")
            if isinstance(acknowledgement, dict) else None
        )
        queue_proof = {
            "schemaVersion": 2, "composeProject": project_name(), "purge": purge,
            "measurement": {"before": before, "consumerAtStart": consumer_at_start,
                            "after": after, "depthSamples": depth_samples},
            "broker": broker,
        }
        queue_proof_path = run_dir / "queue-proof.json"
        queue_proof_path.write_text(json.dumps(queue_proof, indent=2, sort_keys=True) + "\n")
        queue_proof_error = None
        try:
            validate_queue_proof(queue_proof)
        except RuntimeError as exc:
            queue_proof_error = str(exc)
        workload = json.loads((run_dir / "workload.json").read_text())
        resources = json.loads(resources_path.read_text()) if probe is not None else None
        events = json.loads(traces.read_text()) if traces.exists() else []
        stats = None
        stats_error = None
        try:
            stats = collector_stats(
                collector_err,
                require_attribution_binding=True,
                runtime_images_path=runtime_images_path,
            )
        except RuntimeError as exc:
            stats_error = str(exc)
        spool_replay = None
        spool_replay_error = None
        try:
            spool_replay = replay_spool_evidence(spool_path, runtime_images_path)
        except Exception as exc:  # noqa: BLE001 - raw replay must fail closed
            spool_replay_error = f"{type(exc).__name__}: {exc}"
        manifest = COMPILED_ACTIVATION[posture][1]
        telemetry_bytes = traces.stat().st_size if traces.exists() else 0
        blockers = []
        if spool_replay_error:
            blockers.append(f"collector durable spool replay failed: {spool_replay_error}")
        elif spool_replay is not None:
            replay_summary = spool_replay["summary"]
            if replay_summary.get("complete") is not True:
                blockers.append(
                    f"collector durable spool is incomplete: {replay_summary.get('blockers')}"
                )
            if spool_replay["events"] != events:
                blockers.append("traces.json differs from deterministic durable spool replay")
            if stats is None or stats.get("spool") != replay_summary:
                blockers.append("collector spool summary differs from independent replay")
            if stats is not None:
                if (
                    stats.get("attribution_configuration")
                    != spool_replay["attributionConfiguration"]
                    or stats.get("attribution_configuration_sha256")
                    != spool_replay["attributionConfigurationSha256"]
                ):
                    blockers.append(
                        "collector attribution configuration differs from independent replay"
                    )
                expected_counts = {
                    field: stats[field] for field in (
                        "messages", "containers_ok", "containers_bad",
                        "records_ok", "records_bad",
                    )
                }
                if spool_replay["counts"] != expected_counts:
                    blockers.append("collector counters differ from durable spool replay")
        if resources is not None:
            resource_replay = resource_probe_module().validate_resource_evidence(
                resources,
                required_services=set(APP_SERVICES),
                expected_barrier_id=barrier_id,
                expected_start_epoch=measurement_barrier_epoch,
                expected_duration_seconds=args.duration,
            )
            if resource_replay.get("verdict") != "pass":
                blockers.append(
                    "performance resource evidence failed replay: "
                    f"{resource_replay.get('blockers')}"
                )
        blockers.extend(workload_process_blockers(
            args.fault, workload, workload_result.returncode,
        ))
        if workload.get("schemaVersion") != 2:
            blockers.append("measurement workload did not emit the enriched v2 aggregate")
        if resources is not None and resources.get("schemaVersion") != 3:
            blockers.append("performance probe did not emit replayable fixed-slot v3 evidence")
        if abs(float(workload.get("startedAtEpoch", 0)) - measurement_barrier_epoch) > 1.0:
            blockers.append("workload did not join the shared measurement barrier")
        if resources is not None:
            if abs(float(resources.get("nominalStartAtEpoch", 0)) - measurement_barrier_epoch) > 1e-6:
                blockers.append("performance probe did not join the shared measurement barrier")
            if resources.get("requiredServices") != sorted(APP_SERVICES):
                blockers.append("performance probe did not bind the complete application service set")
            if resources.get("barrierId") != barrier_id:
                blockers.append("performance probe barrier ID differs from controller receipt")
        if child_proofs["systemProbe"]["returnCode"] != 0:
            blockers.append(
                "system probe exited "
                f"{child_proofs['systemProbe']['returnCode']}: {system_err.strip()[-500:]}")
        if not system_samples_path.is_file():
            blockers.append("system probe did not write system-samples.json")
        if barrier_thread.is_alive() or barrier_exception:
            blockers.append(f"collector barrier acknowledgement failed: {barrier_exception}")
        if (not isinstance(acknowledgement, dict)
                or acknowledgement.get("queueState", {}).get("consumers") != 1):
            blockers.append("collector was not independently acknowledged at the shared barrier")
        journey_ledger_path = run_dir / "journey-ledger.jsonl"
        journey_plan_path = run_dir / "journey-ledger.plan.json"
        journey_validation = None
        try:
            journey_validation = validate_journey_evidence(workload, journey_ledger_path)
        except Exception as exc:  # noqa: BLE001 - retained evidence must fail closed
            blockers.append(
                f"measurement journey evidence is invalid: {type(exc).__name__}: {exc}"
            )
        if posture == "none" and events:
            blockers.append("none posture emitted telemetry")
        if posture in {"selected", "full"} and not events:
            blockers.append(f"{posture} posture emitted no telemetry")
        if before["messages"] != 0:
            blockers.append(f"queue nonempty before window: {before['messages']}")
        if consumer_state["consumers"] != 1:
            blockers.append(f"collector exclusivity not proven: {consumer_state['consumers']} consumers")
        if queue_proof_error:
            blockers.append(f"queue lifecycle proof invalid: {queue_proof_error}")
        tolerance = exposure_tolerance(
            events, intervention, fault=args.fault,
            container_failures=(
                spool_replay["containerParseFailures"] if spool_replay is not None else ()
            ),
        )
        blockers.extend(collector_process_blockers(
            child_proofs["collector"]["returnCode"],
            child_proofs.get("performanceProbe", {}).get("returnCode"), stats, stats_error,
            effect_contract=args.fault != "none", require_spool=True,
            entry_point_woven=native_collector_module().entry_point_woven(
                proof["closureGroups"]),
            tolerance=tolerance,
            trace_completeness_deferred=timing is not None))
        blockers.extend(collector_event_blockers(events, stats))
        for name, child in child_proofs.items():
            if child["timedOut"] or child["communicationError"] or not child["joined"]:
                blockers.append(f"{name} lifecycle was not clean: {child}")
        expected_hash = sha256(COMPILED_ACTIVATION[posture][2])
        bad_hashes = [service for service, value in proof["services"].items()
                      if value["aopSha256"] != expected_hash]
        if bad_hashes or proof["aopSha256"] != expected_hash:
            blockers.append(f"{posture} AOP hash mismatch: {bad_hashes or 'proof'}")
        writer_failures = [service for service, value in proof["services"].items() if value["writerInitializationFailed"]]
        if posture != "none" and writer_failures:
            blockers.append(f"Kieker writer initialization failed: {writer_failures}")
        expected = f"kieker.monitoring.enabled={'false' if posture == 'none' else 'true'}"
        mismatched = [service for service, value in proof["services"].items()
                      if value["configuration"] != expected]
        if mismatched:
            blockers.append(f"{posture} runtime configuration mismatch: {mismatched}")
        if fault_thread and fault_thread.is_alive():
            blockers.append(f"fault intervention did not terminate: {args.fault}")
        if fault_exception:
            blockers.append(f"fault intervention raised: {fault_exception}")
        if args.fault != "none" and (not intervention or not intervention.get("successful")):
            blockers.append(f"fault manifestation/recovery not proven: {args.fault}")
        measured_start_epoch = (
            resources["nominalStartAtEpoch"]
            if resources is not None else barrier["barrierAtEpoch"])
        measured_end_epoch = (
            resources["nominalEndAtEpoch"]
            if resources is not None else barrier["barrierAtEpoch"] + args.duration)
        measured_started = datetime.fromtimestamp(
            measured_start_epoch, timezone.utc).isoformat()
        measured_ended = datetime.fromtimestamp(
            measured_end_epoch, timezone.utc).isoformat()
        workload_settled = datetime.fromtimestamp(
            workload["endedAtEpoch"], timezone.utc).isoformat()
        resource_endpoint = (
            resources["applicationCpuSeconds"] / workload["offered"]
            if resources is not None and workload["offered"] else None)
        resource_projection = None
        if resources is not None:
            resource_projection = {
                **{key: resources[key] for key in (
                    "applicationCpuSeconds", "applicationMemoryPeakBytes", "hostCpuSeconds",
                )},
                "contract": resources["contract"],
                "artifactSha256": sha256(resources_path),
                "nominalStartAtEpoch": resources["nominalStartAtEpoch"],
                "nominalEndAtEpoch": resources["nominalEndAtEpoch"],
                "measurementDurationSeconds": resources["measurementDurationSeconds"],
                "samplingIntervalSeconds": resources["sampling"]["intervalSeconds"],
                "offeredJourneys": workload["offered"],
                "applicationCpuSecondsPerOfferedJourney": resource_endpoint,
            }
        if getattr(args, "candidate_contract", False) is True:
            capture_candidate_service_logs(
                run_dir,
                runtime_images,
                measurement_started_at=measured_started,
                measurement_ended_at=measured_ended,
            )
        if timing is not None and timing.get("applicationLogTimestamps") is True:
            # Traffic sweep: every service's log with Docker receive timestamps, before teardown.
            logs_argv = compose(posture, "logs", "--timestamps", "--no-color")
            logs = capture_bytes(logs_argv)
            # Raw bytes: a non-UTF-8 byte in any service's log must not lose the cell (the validator decodes
            # with replacement and records the count).
            (run_dir / APPLICATION_LOG_ARTIFACT).write_bytes(logs.stdout)
            if logs.returncode != 0 or not logs.stdout.strip():
                blockers.append(
                    f"application log capture failed ({logs.returncode}): "
                    f"{logs.stderr.decode('utf-8', 'replace').strip()[-300:]}")
        receipt = {
            "schemaVersion": 2, "runId": run_id, "sut": "teastore", "posture": posture,
            "analysisKind": analysis["analysisKind"],
            "resourceUse": analysis["resourceUse"],
            "source": {"frameworkCommit": args.framework_commit,
                       "sutReferenceCommit": args.sut_reference_commit,
                       "dirty": False, "selectionId": args.selection_id,
                       "descriptorId": args.descriptor_id,
                       "descriptorSha256": args.descriptor_sha256,
                       "evidenceLabel": args.evidence_label,
                       "runtimeImagesSha256": sha256(runtime_images_path),
                       "queueProofSha256": sha256(queue_proof_path),
                       "childProcessesSha256": sha256(child_processes_path),
                       "spoolSha256": sha256(spool_path) if spool_path.is_file() else None,
                       "collectorAttributionConfigurationSha256": (
                           stats.get("attribution_configuration_sha256")
                           if stats else None
                       ),
                       "selectionSourceSha256": sha256(SELECTION_SOURCES[args.selection_id]),
                       "activationManifestSha256": sha256(COMPILED_ACTIVATION[posture][1])},
            "window": {"startedAt": measured_started, "endedAt": measured_ended,
                       "workloadSettledAt": workload_settled,
                       "warmupSeconds": args.warmup, "measurementSeconds": args.duration,
                       "barrierAt": barrier["barrierAt"]},
            "workload": {key: workload[key] for key in (
                "offered", "completed", "successful", "failed", "timedOut", "settled",
                "concurrency",
            )},
            "latencyMs": workload["latencyMs"],
            "resources": resource_projection,
            "exposureTolerance": tolerance,
            "telemetry": {"records": len(events), "bytes": telemetry_bytes,
                          "uniqueSignatures": len({event.get("signature_sha1") for event in events}),
                          "services": {service: sum(event.get("service") == service for event in events)
                                       for service in sorted({event.get("service") for event in events if event.get("service")})},
                          "parseFailures": stats["records_bad"] if stats else None,
                          "collectorStats": stats,
                          "spool": stats.get("spool") if stats else None},
            "processes": {
                "workload": {"returnCode": workload_result.returncode},
                "collector": child_proofs["collector"],
                **({"performanceProbe": child_proofs["performanceProbe"]}
                   if "performanceProbe" in child_proofs else {}),
                "systemProbe": child_proofs["systemProbe"],
            },
            "queue": {"purgedBefore": purge["after"]["messages"] == 0,
                      "messagesBefore": before["messages"],
                      "messagesAfter": after["messages"],
                      "exclusiveConsumer": (
                          isinstance(consumer_at_start, dict)
                          and consumer_at_start.get("consumers") == 1
                      ),
                      "proofSha256": sha256(queue_proof_path)},
            "postureProof": proof,
            "intervention": intervention,
            "canonicality": {"label": args.evidence_label if not blockers else "noncanonical",
                             "blockers": blockers},
            "candidateArtifacts": {
                "measurementBarrierSha256": sha256(barrier_path),
                "journeyPlanSha256": sha256(journey_plan_path)
                    if journey_plan_path.is_file() else None,
                "journeyLedgerSha256": sha256(journey_ledger_path)
                    if journey_ledger_path.is_file() else None,
                "journeyPlanCanonicalSha256": (
                    journey_validation["planSha256"] if journey_validation else None
                ),
                "journeyLedgerLastRecordSha256": (
                    journey_validation["lastRecordSha256"] if journey_validation else None
                ),
                "appWitnessSha256": None,
                "pathGroundTruthStatus": "unsupported",
                "pathGroundTruthReason": (
                    "TeaStore application-side witness extraction is not yet installed; "
                    "Kieker presence cannot substitute for execution truth."
                ),
            },
        }
        (run_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        return receipt
    finally:
        if owns_project:
            if fault_thread is not None:
                fault_thread.join()
            for name, child in (("collector", collector), ("performanceProbe", probe),
                                ("systemProbe", system_probe)):
                if child is not None and name not in child_proofs:
                    stdout, stderr, child_proofs[name] = join_child_process(child, 0)
                    child_outputs[name] = (stdout, stderr)
            if collector is not None:
                collector_out, collector_err = child_outputs.get("collector", ("", ""))
                (run_dir / "collector.stdout").write_text(collector_out)
                (run_dir / "collector.stderr").write_text(collector_err)
            if probe is not None:
                probe_out, probe_err = child_outputs.get("performanceProbe", ("", ""))
                (run_dir / "probe.log").write_text(probe_out + probe_err)
            if system_probe is not None:
                system_out, system_err = child_outputs.get("systemProbe", ("", ""))
                (run_dir / "system-probe.log").write_text(system_out + system_err)
            (run_dir / "child-processes.json").write_text(
                json.dumps(child_proofs, indent=2, sort_keys=True) + "\n")
            unjoined_children = any(
                not value.get("joined") for value in child_proofs.values()
            )
            for service in RUNTIME_SERVICES:
                try:
                    container = service_container(posture, service)
                except Exception as exc:  # noqa: BLE001 - diagnostics cannot prevent teardown
                    (run_dir / f"{service}.log").write_text(f"container lookup failed: {exc}\n")
                    continue
                try:
                    result = command(["docker", "logs", container], check=False)
                    (run_dir / f"{service}.log").write_text(result.stdout + result.stderr)
                except Exception as exc:  # noqa: BLE001 - diagnostics cannot prevent teardown
                    (run_dir / f"{service}.log").write_text(
                        f"container log capture failed: {type(exc).__name__}: {exc}\n")
            down, remaining = teardown_project(posture, run_dir)
            if receipt is not None:
                bind_teardown(receipt, down, remaining, run_dir, args.evidence_label)
            if unjoined_children:
                raise RuntimeError(
                    "one or more exact campaign child processes remained live"
                )


def _candidate_module(relative: str, name: str):
    path = Path(relative)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - installation defect
        raise RuntimeError(f"cannot load candidate helper: {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _candidate_json(path: Path, where: str) -> Any:
    before = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        raise RuntimeError(f"{where} is not a regular non-symlink file")
    payload = path.read_bytes()
    after = path.lstat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise RuntimeError(f"{where} changed while being read")
    try:
        return json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_candidate_no_duplicates,
            parse_constant=_candidate_reject_constant,
        )
    except RuntimeError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{where} is invalid JSON") from exc


def _candidate_write_json(path: Path, document: Any) -> None:
    path.write_text(
        json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _candidate_reject_constant(value: str) -> NoReturn:
    raise RuntimeError(f"candidate JSON contains non-finite constant: {value}")


def _candidate_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise RuntimeError(f"candidate JSON repeats key: {key}")
        value[key] = item
    return value


def _candidate_same(left: Any, right: Any) -> bool:
    try:
        return json.dumps(
            left, allow_nan=False, ensure_ascii=False, separators=(",", ":"),
            sort_keys=True,
        ) == json.dumps(
            right, allow_nan=False, ensure_ascii=False, separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError):
        return False


def _publish_regular(source: Path, destination: Path) -> None:
    before = source.lstat()
    if source.is_symlink() or not stat.S_ISREG(before.st_mode):
        raise RuntimeError(f"candidate source artifact is not regular: {source.name}")
    payload = source.read_bytes()
    after = source.lstat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise RuntimeError(f"candidate source artifact changed: {source.name}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(destination, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:  # pragma: no cover - operating-system invariant
                raise RuntimeError("candidate artifact write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validate_candidate_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    keys = {
        "schemaVersion", "contract", "campaignId", "campaignSha256",
        "gatePlanSha256", "runtimeReadinessSha256", "gateRunSha256",
        "frameworkCommit", "descriptorCanonicalSha256",
        "compiledPlanCanonicalSha256", "runId", "runKey", "ordinalPosition",
        "compiledArtifactRoot", "coldStart", "target", "runtimeInputs",
        "workload", "posture", "window", "faultGroundTruth",
        "pathGroundTruth", "attemptPolicy", "requiredArtifacts", "terminalPolicy",
    }
    if not isinstance(contract, Mapping) or set(contract) != keys:
        raise RuntimeError("candidate contract fields differ")
    key = contract.get("runKey")
    if not isinstance(key, Mapping) or set(key) != {
        "studyEpoch", "regime", "block", "posture", "attempt",
    }:
        raise RuntimeError("candidate run key fields differ")
    regime = key.get("regime")
    posture = key.get("posture")
    sweep = CANDIDATE_EPOCH["sweep"] is True
    scenario = CANDIDATE_EPOCH["scenarios"].get(regime, "unknown")
    cost = regime == "no-fault-cost"
    if (
        type(contract.get("schemaVersion")) is not int
        or contract.get("schemaVersion") != 1
        or contract.get("contract") != CANDIDATE_CONTRACT
        or contract.get("coldStart") is not True
        or key.get("studyEpoch") != CANDIDATE_STUDY_EPOCH
        or scenario == "unknown"
        or posture not in ALLOWED_POSTURES
        or posture not in CANDIDATE_EPOCH["postures"]
        or type(key.get("block")) is not int
        or not 1 <= key["block"] <= CANDIDATE_EPOCH["blocksPerRegime"]
        or type(key.get("attempt")) is not int
        or key["attempt"] != 1
        or type(contract.get("ordinalPosition")) is not int
        or contract["ordinalPosition"] not in range(1, CANDIDATE_EPOCH["maximumOrdinal"] + 1)
        or not isinstance(contract.get("campaignId"), str)
        or CANDIDATE_ID_RE.fullmatch(contract["campaignId"]) is None
        or not isinstance(contract.get("runId"), str)
        or not isinstance(contract.get("compiledArtifactRoot"), str)
        or any(
            not isinstance(contract.get(name), str)
            or SHA256_RE.fullmatch(contract[name]) is None
            for name in (
                "campaignSha256", "gatePlanSha256", "runtimeReadinessSha256",
                "gateRunSha256", "descriptorCanonicalSha256",
                "compiledPlanCanonicalSha256",
            )
        )
        or not isinstance(contract.get("frameworkCommit"), str)
        or COMMIT_RE.fullmatch(contract["frameworkCommit"]) is None
    ):
        raise RuntimeError("candidate contract identity or digest differs")
    for name in ("runId", "compiledArtifactRoot"):
        raw = contract[name]
        path = PurePosixPath(raw)
        if path.is_absolute() or path.as_posix() != raw or any(
            part in {"", ".", ".."} for part in path.parts
        ):
            raise RuntimeError(f"candidate {name} is unsafe")
    target = contract.get("target")
    if not isinstance(target, Mapping) or set(target) != {
        "host", "transportUser", "executionUser", "executionUid",
        "executionGid", "executionMethod", "releaseRoot", "resultsRoot",
        "exclusiveLeasePath", "outerLeaseScope",
    } or (
        target.get("host") != "fb14srv5"
        or target.get("transportUser") != "root"
        or target.get("executionUser") != "stig"
        or target.get("executionUid") != 1015
        or target.get("executionGid") != 1015
        or target.get("executionMethod") != "runuser"
        or not isinstance(target.get("releaseRoot"), str)
        or re.fullmatch(
            r"/home/stig/\.local/share/observability-placement/candidate-v4/teastore/"
            r"releases/[0-9a-f]{32}-[0-9a-f]{12}-[0-9a-f]{16}",
            target["releaseRoot"],
        ) is None
        or not isinstance(target.get("resultsRoot"), str)
        or re.fullmatch(
            r"/home/stig/\.local/share/observability-placement/candidate-v4/teastore/"
            r"results/[0-9a-f]{32}",
            target["resultsRoot"],
        ) is None
        or target.get("exclusiveLeasePath") != (
            "/home/stig/.local/share/observability-placement/candidate-v4/"
            "teastore/leases/host-exclusive.lock"
        )
        or target.get("outerLeaseScope") != CANDIDATE_EPOCH["outerLeaseScope"]
    ):
        raise RuntimeError("candidate target or lease differs")
    if contract.get("attemptPolicy") != {
        "attempt": 1, "startedBeforeFirstExternalMutation": True,
        "retryAllowed": False, "substitutionAllowed": False,
        "rerandomizationAllowed": False,
    } or contract.get("terminalPolicy") != {
        "candidateCellValidationRequired": True,
        "ownedResourcesCleanRequired": True,
        "outerLeaseHeldRequired": True,
        "deadlineControllerSettledRequired": True,
        "promotionAuthorized": False,
    }:
        raise RuntimeError("candidate attempt or terminal policy differs")
    compiler = _candidate_module(
        CANDIDATE_EPOCH["compilerRelative"],
        "teastore_candidate_runtime_contract_compiler",
    )
    descriptor = compiler.frozen_descriptor()
    timing = None
    if sweep:
        # The contract may not bring its own numbers: its timing must be the compiled plan's for this run ID,
        # byte for byte, with the installed descriptor's pinned digests.
        compiled = compiler.compiled_cell(contract["runId"])
        timing = compiled["timing"]
        if (
            not _candidate_same(compiled["runKey"], dict(key))
            or compiled["ordinalPosition"] != contract["ordinalPosition"]
            or compiled["artifactRoot"] != contract["compiledArtifactRoot"]
            or compiled["fault"] != scenario
        ):
            raise RuntimeError("candidate contract differs from the compiled sweep cell")
    workload = contract.get("workload")
    expected_workload = {
        "id": descriptor["workload"]["id"],
        "kind": descriptor["workload"]["kind"],
        "population": descriptor["workload"]["population"],
        "journeysPerSecond": (
            descriptor["workload"]["journeysPerSecond"] if timing is None
            else timing["journeysPerSecond"]),
        "concurrency": descriptor["workload"]["concurrency"],
        "offeredJourneys": (
            descriptor["timing"]["offeredJourneysPerRun"] if timing is None else timing["offered"]),
        "excludedActions": copy.deepcopy(descriptor["workload"]["excludedActions"]),
        "ledgerContract": copy.deepcopy(descriptor["workload"]["journeyLedger"]),
    }
    if not isinstance(workload, Mapping) or not _candidate_same(
        dict(workload), expected_workload,
    ):
        raise RuntimeError("candidate workload differs from the frozen population")
    window = contract.get("window")
    expected_analysis = "cost" if cost else "effect"
    expected_window = {
        "analysisKind": expected_analysis,
        "artifactRootClass": "cost" if cost else f"effect/{scenario}",
        "warmupSeconds": descriptor["timing"]["warmupSeconds"],
        "measurementSeconds": descriptor["timing"]["measurementSeconds"],
        "sharedBarrierRequired": True,
        "sharedBarrierParticipants": copy.deepcopy(
            descriptor["timing"]["sharedBarrierParticipants"]
        ),
        "resourceProjectionAllowed": cost,
        "resourcesClaimUse": "cost-proxy" if cost else "diagnostic-only",
        "poolWithOtherRegime": False,
    }
    if timing is not None:
        expected_window["warmupSeconds"] = timing["warmupSeconds"]
        expected_window["measurementSeconds"] = timing["measurementSeconds"]
        expected_window["timing"] = copy.deepcopy(timing)
    if not isinstance(window, Mapping) or not _candidate_same(
        dict(window), expected_window,
    ):
        raise RuntimeError("candidate cost/effect window differs")
    posture_contract = contract.get("posture")
    expected_posture = {
        "id": posture,
        "selectionId": "fault-qualification" if posture == "selected" else None,
        "proofRequirements": copy.deepcopy(
            descriptor["postureProof"][posture]["requires"]
        ),
    }
    if not isinstance(posture_contract, Mapping) or not _candidate_same(
        dict(posture_contract), expected_posture,
    ):
        raise RuntimeError("candidate posture differs from the scheduled cell")
    fault = contract.get("faultGroundTruth")
    expected_fault = {
        "required": not cost,
        "scenario": scenario,
        "artifact": "intervention.json" if not cost else None,
        "independentOfKieker": True,
        "faultOnsetSeconds": (
            None if cost else descriptor["timing"]["faultOnsetSeconds"] if timing is None
            else timing["faultOnsetSeconds"]
        ),
        "holdSeconds": (
            None if cost else descriptor["timing"]["interventionHoldSeconds"] if timing is None
            else timing["faultHoldSeconds"]
        ),
        "commandSuccessAloneEstablishesTruth": False,
        "failedManifestationOrRecoveryStopsCampaign": True,
    }
    if not isinstance(fault, Mapping) or not _candidate_same(dict(fault), expected_fault):
        raise RuntimeError("candidate fault ground-truth contract differs")
    expected_path = {
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
    }
    path_ground_truth = contract.get("pathGroundTruth")
    if not isinstance(path_ground_truth, Mapping) or not _candidate_same(
        dict(path_ground_truth), expected_path,
    ):
        raise RuntimeError("candidate path ground-truth contract differs")
    runtime_inputs = contract.get("runtimeInputs")
    images = runtime_inputs.get("imageDigests") if isinstance(runtime_inputs, Mapping) else None
    if not isinstance(runtime_inputs, Mapping) or set(runtime_inputs) != {
        "imageDigests", "transportImplementationSha256", "controllerDigests",
        "gateSetupSha256", "releaseManifestSha256", "bundleSha256",
        "releaseBindingSha256", "readinessArchiveSha256",
    } or not isinstance(images, Mapping) or set(images) != set(RUNTIME_SERVICES) or any(
        not isinstance(value, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*@sha256:[0-9a-f]{64}", value) is None
        for value in images.values()
    ):
        raise RuntimeError("candidate image digest inputs differ")
    if any(
        not isinstance(runtime_inputs.get(name), str)
        or SHA256_RE.fullmatch(runtime_inputs[name]) is None
        for name in (
            "gateSetupSha256", "releaseManifestSha256", "bundleSha256",
            "releaseBindingSha256", "readinessArchiveSha256",
        )
    ):
        raise RuntimeError("candidate installed release digest inputs differ")
    adapter = _candidate_module(
        "modules/teastore/execution/candidate_runtime_adapter.py",
        "teastore_candidate_runtime_contract_adapter",
    )
    controller_digests = runtime_inputs.get("controllerDigests")
    expected_controllers = {
        name: sha256(Path(relative))
        for name, relative in adapter.CONTROLLER_PATHS.items()
    }
    if controller_digests != expected_controllers or runtime_inputs.get(
        "transportImplementationSha256"
    ) != expected_controllers["bounded-candidate-transport"]:
        raise RuntimeError("candidate controller digest inputs differ")
    required = set(CANDIDATE_COMMON_ARTIFACTS) | {
        "content-manifest.json", "cell-cleanup.json",
        "resources.json" if cost else "intervention.json",
    }
    if contract.get("requiredArtifacts") != sorted(required):
        raise RuntimeError("candidate required artifact set differs")
    return copy.deepcopy(dict(contract))


def _candidate_args(contract: Mapping[str, Any], output: Path) -> argparse.Namespace:
    key = contract["runKey"]
    scenario = contract["faultGroundTruth"]["scenario"] or "none"
    timing = contract["window"].get("timing") if CANDIDATE_EPOCH["sweep"] else None
    if timing is not None:
        # Traffic sweep: every value is the compiled plan's (``_validate_candidate_contract`` bound it).
        return argparse.Namespace(
            output=output,
            framework_commit=contract["frameworkCommit"],
            sut_reference_commit=CANDIDATE_SUT_COMMIT,
            blocks=1,
            seed=0,
            warmup=timing["warmupSeconds"],
            duration=timing["measurementSeconds"],
            rate=timing["journeysPerSecond"],
            concurrency=timing["concurrency"],
            postures=key["posture"],
            fault=scenario,
            fault_at=timing["faultOnsetSeconds"],
            outage=timing["faultHoldSeconds"],
            selection_id="fault-qualification",
            descriptor_id=CANDIDATE_STUDY_EPOCH,
            descriptor_sha256=contract["descriptorCanonicalSha256"],
            evidence_label=CANDIDATE_EVIDENCE_LABEL,
            candidate_contract=True,
            timing=copy.deepcopy(dict(timing)),
        )
    return argparse.Namespace(
        output=output,
        framework_commit=contract["frameworkCommit"],
        sut_reference_commit=CANDIDATE_SUT_COMMIT,
        blocks=1,
        seed=0,
        warmup=120,
        duration=600,
        rate=0.15,
        concurrency=8,
        postures=key["posture"],
        fault=scenario,
        fault_at=180,
        outage=CANDIDATE_FAULT_OUTAGE_SECONDS,
        selection_id="fault-qualification",
        descriptor_id=CANDIDATE_STUDY_EPOCH,
        descriptor_sha256=contract["descriptorCanonicalSha256"],
        evidence_label=CANDIDATE_EVIDENCE_LABEL,
        candidate_contract=True,
    )


def _verify_candidate_images(
    runtime_images: Mapping[str, Any], expected: Mapping[str, str],
) -> None:
    validate_runtime_images(
        dict(runtime_images), expected_content_references=expected,
    )


def _candidate_capture_terminal(
    root: Path,
    receipt: Mapping[str, Any],
    queue_proof: Mapping[str, Any],
    child_processes: Mapping[str, Any],
) -> dict[str, Any]:
    validator = _candidate_module(
        "modules/teastore/validation/candidate_pilot.py",
        "teastore_candidate_runtime_capture_replay",
    )
    traces = _candidate_json(root / "traces.json", "candidate traces")
    if not isinstance(traces, list) or any(not isinstance(row, dict) for row in traces):
        raise RuntimeError("candidate traces are not an array of objects")
    start = datetime.fromisoformat(
        receipt["window"]["measurementStartedAt"].replace("Z", "+00:00")
    )
    end = datetime.fromisoformat(
        receipt["window"]["measurementEndedAt"].replace("Z", "+00:00")
    )
    times = [validator._native_time(event) for event in traces]
    if len(traces) != len(times):  # defensive: validator must remain Python 3.9-safe
        raise RuntimeError("candidate trace timestamps differ in length")
    measurement = [
        event for event, timestamp in zip(traces, times)
        if start <= timestamp < end
    ]
    native_ids = [validator._original_native_trace_id(event) for event in traces]
    if any(value is None for value in native_ids):
        raise RuntimeError("candidate capture contains a non-original trace identity")
    stats = receipt["telemetry"]["collectorStats"]
    spool = stats["spool"]
    if spool.get("complete") is not True or spool.get("duplicateBodyCount") != 0:
        raise RuntimeError("candidate raw spool is incomplete or redelivered")
    validate_queue_proof(dict(queue_proof))
    at_barrier = queue_proof["measurement"]["consumerAtStart"]
    if at_barrier["messages"] != 0:
        raise RuntimeError("candidate queue was non-empty at the measurement barrier")
    unjoined = sum(
        value.get("joined") is not True
        for value in child_processes.values()
        if isinstance(value, Mapping)
    )
    return {
        "complete": True,
        "settled": True,
        "hashReconciled": True,
        "queuePurgedBefore": queue_proof["purge"]["after"]["messages"] == 0,
        "queueMessagesAtBarrier": at_barrier["messages"],
        "exclusiveCollector": at_barrier["consumers"] == 1,
        "foreignWriters": 0,
        "unjoinedChildren": unjoined,
        "rawRecords": len(traces),
        "measurementRecords": len(measurement),
        "uniqueNativeTraces": len(set(native_ids)),
        "uniqueSignatures": len({row.get("signature_sha1") for row in traces}),
        "uniqueMessageBodies": len({row.get("message_sha1") for row in traces}),
        "redeliveredMessageSha1": [],
    }


def _candidate_receipt(
    contract: Mapping[str, Any], operational: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    legacy = _candidate_json(operational / "receipt.json", "runtime slice receipt")
    warmup = _candidate_json(operational / "warmup.json", "candidate warmup")
    workload = _candidate_json(operational / "workload.json", "candidate workload")
    runtime_images = _candidate_json(
        operational / "runtime-images.json", "candidate runtime images",
    )
    queue_proof = _candidate_json(
        operational / "queue-proof.json", "candidate queue proof",
    )
    child_processes = _candidate_json(
        operational / "child-processes.json", "candidate child process proof",
    )
    _verify_candidate_images(
        runtime_images, contract["runtimeInputs"]["imageDigests"],
    )
    canonicality = legacy.get("canonicality")
    teardown = legacy.get("teardown")
    if not isinstance(canonicality, Mapping) or canonicality.get("blockers") != []:
        raise RuntimeError(f"candidate runtime slice is blocked: {canonicality}")
    if not isinstance(teardown, Mapping) or teardown.get("projectClean") is not True:
        raise RuntimeError("candidate runtime slice did not prove owned cleanup")
    barrier = _candidate_json(
        operational / "measurement-barrier.json", "candidate measurement barrier",
    )
    measurement_start = datetime.fromtimestamp(
        float(barrier["barrierAtEpoch"]), timezone.utc,
    )
    timing = contract["window"].get("timing") if CANDIDATE_EPOCH["sweep"] else None
    # Frozen epoch: 600 s measurement, warm-up 0.15/s x 120 s = 18 journeys at concurrency 8.
    # Traffic sweep: every value from the cell's compiled timing.
    measurement_seconds = 600 if timing is None else timing["measurementSeconds"]
    warmup_design = (
        {"rate": 0.15, "seconds": 120, "offered": 18, "concurrency": 8} if timing is None else {
            "rate": timing["warmupJourneysPerSecond"], "seconds": timing["warmupSeconds"],
            "offered": timing["warmupOffered"], "concurrency": timing["concurrency"],
        })
    measurement_end = measurement_start + timedelta(seconds=measurement_seconds)
    warmup_schedule = warmup.get("schedule") if isinstance(warmup, Mapping) else None
    if not isinstance(warmup_schedule, Mapping) or (
        warmup.get("schemaVersion") != 2
        or warmup_schedule.get("kind") != "fixed-open-loop"
        or warmup_schedule.get("journeysPerSecond") != warmup_design["rate"]
        or warmup_schedule.get("durationSeconds") != warmup_design["seconds"]
        or warmup.get("offered") != warmup_design["offered"]
        or warmup.get("settled") != warmup_design["offered"]
        or warmup.get("concurrency") != warmup_design["concurrency"]
    ):
        raise RuntimeError(
            "candidate warmup differs from the frozen 120-second design" if timing is None
            else f"candidate warmup differs from the {warmup_design['seconds']}-second sweep design")
    try:
        warmup_start = datetime.fromtimestamp(
            float(warmup_schedule["barrierAtEpoch"]), timezone.utc,
        )
        warmup_nominal_end = warmup_start + timedelta(seconds=warmup_design["seconds"])
        warmup_settled = datetime.fromtimestamp(
            float(warmup["endedAtEpoch"]), timezone.utc,
        )
    except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
        raise RuntimeError("candidate warmup boundaries are invalid") from exc
    if not warmup_start <= warmup_settled <= measurement_start or (
        warmup_nominal_end > measurement_start
    ):
        raise RuntimeError("candidate warmup and setup boundaries overlap measurement")
    key = contract["runKey"]
    cost = key["regime"] == "no-fault-cost"
    stats = legacy["telemetry"]["collectorStats"]
    receipt = {
        "schemaVersion": 2,
        "contract": "teastore-candidate-pilot-evidence-v1",
        "studyEpoch": CANDIDATE_STUDY_EPOCH,
        "population": "login-browse-v1" if timing is None else timing["workloadId"],
        "selectionId": "fault-qualification" if key["posture"] == "selected" else None,
        "source": {
            "sutCommit": CANDIDATE_SUT_COMMIT,
            "frameworkCommit": contract["frameworkCommit"],
            "frameworkDirty": False,
            "host": "fb14srv5",
            "exclusiveLease": True,
            "imageDigests": copy.deepcopy(contract["runtimeInputs"]["imageDigests"]),
            "spoolSha256": sha256(operational / SPOOL_ARTIFACT_NAME),
            "runtimeImagesSha256": sha256(operational / "runtime-images.json"),
            "collectorAttributionConfigurationSha256": stats[
                "attribution_configuration_sha256"
            ],
        },
        "run": {
            "runId": contract["runId"],
            "regime": key["regime"],
            "block": key["block"],
            "posture": key["posture"],
            "attempt": 1,
        },
        "analysisKind": "cost" if cost else "effect",
        "resourceUse": "cost-proxy" if cost else "diagnostic-only",
        "window": {
            "warmupStartedAt": warmup_start.isoformat(),
            "warmupEndedAt": warmup_nominal_end.isoformat(),
            "warmupSettledAt": warmup_settled.isoformat(),
            "warmupDurationSeconds": warmup_design["seconds"],
            "measurementStartedAt": measurement_start.isoformat(),
            "measurementEndedAt": measurement_end.isoformat(),
            "measurementStartMonotonic": float(barrier["barrierMonotonic"]),
            "measurementEndMonotonic": float(barrier["barrierMonotonic"]) + float(measurement_seconds),
            "sharedBarrierId": barrier["barrierId"],
        },
        "workload": {
            "offered": workload["offered"],
            "successful": workload["successful"],
            "failed": workload["failed"],
            "timedOut": workload["timedOut"],
            "requests": workload["requests"],
        },
        "latencyMs": copy.deepcopy(workload["latencyMs"]),
        "resources": copy.deepcopy(legacy["resources"]) if cost else None,
        "intervention": copy.deepcopy(legacy["intervention"]),
        "exposureTolerance": copy.deepcopy(legacy["exposureTolerance"]),
        "telemetry": {
            "collectorStats": copy.deepcopy(stats),
            "spool": copy.deepcopy(stats["spool"]),
        },
        "artifacts": {},
    }
    if timing is not None:
        # The validator re-derives this from the compiled plan; a receipt cannot bring its own numbers.
        receipt["timing"] = copy.deepcopy(dict(timing))
    return receipt, queue_proof, child_processes


BLOCKED_EVIDENCE_SUFFIX = ".blocked-evidence"


def preserve_blocked_evidence(
    output: Path, error: BaseException, *, run_id: str | None = None,
    run_key: Mapping[str, Any] | None = None,
) -> Path | None:
    """Quarantine a byte-complete copy of a blocked cell's evidence for replay.

    Three campaign one-shots aborted on terminal-validation gates whose offline
    diagnosis needed evidence that no longer existed once the abort settled:
    Docker-side state dies with the emergency ``down -v``, and a blocked
    extractor writes no partial output at all.  Copying the entire attempted
    output root (including ``.operational`` staging) into an out-of-band
    sibling before any outer cleanup layer runs makes the whole terminal
    validation replayable offline.  Preservation is diagnostic and best-effort:
    it never mutates the output root, never overwrites an existing quarantine,
    and its own failure must never mask the original abort.
    """

    output = Path(output)
    if output.is_symlink() or not output.is_dir():
        return None
    quarantine = output.parent / (output.name + BLOCKED_EVIDENCE_SUFFIX)
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

    shutil.copytree(output, staging, symlinks=True, copy_function=_link_or_copy)
    preserved = sorted(
        str(path.relative_to(staging))
        for path in staging.rglob("*") if path.is_file() and not path.is_symlink()
    )
    manifest = {
        "schemaVersion": 1,
        "kind": "teastore-candidate-blocked-evidence-v1",
        "runId": run_id,
        "runKey": dict(run_key) if isinstance(run_key, Mapping) else None,
        "preservedAt": now(),
        "outputRoot": str(output),
        "errorType": type(error).__name__,
        "error": str(error)[:2000],
        "preservedFiles": [
            {"path": name, "bytes": (staging / name).stat().st_size}
            for name in preserved
        ],
    }
    (staging / "blocked-evidence-manifest.json").write_text(
        json.dumps(manifest, allow_nan=False, indent=2, sort_keys=True) + "\n")
    staging.replace(quarantine)
    return quarantine


def execute_candidate_cell(contract: Mapping[str, Any], output: Path) -> dict[str, Any]:
    """Produce one exact candidate cell from the gate-internal immutable contract.

    The remote controller, not this producer, adds the lease/deadline cleanup
    proof and closes the final content manifest.  On any failure the attempted
    output root remains visible and no valid seal is returned.
    """

    contract = _validate_candidate_contract(contract)
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise RuntimeError("candidate cell output exists before attempt one")
    output_parent = output.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    if output_parent.is_symlink() or not output_parent.is_dir():
        raise RuntimeError("candidate cell output parent is not a real directory")
    key = contract["runKey"]
    expected_suffix = (
        "runs", key["regime"],
        f"b{key['block']:02d}-{contract['ordinalPosition']:02d}-{key['posture']}",
    )
    if len(output.parts) < 3 or tuple(output.parts[-3:]) != expected_suffix:
        raise RuntimeError("candidate output path differs from frozen campaign identity")

    project = "teastore_candidate_" + hashlib.sha256(
        contract["campaignId"].encode("utf-8")
    ).hexdigest()[:16]
    previous_project = os.environ.get("OBSPLACEMENT_COMPOSE_PROJECT")
    if previous_project is not None:
        raise RuntimeError("ambient Compose project cannot enter candidate execution")
    os.environ["OBSPLACEMENT_COMPOSE_PROJECT"] = project
    operational = output / ".operational"
    try:
        args = _candidate_args(contract, output)
        _execute_candidate_runtime_slice(
            output, ".operational", contract["runKey"]["posture"], args,
            expected_image_references=contract["runtimeInputs"]["imageDigests"],
        )
        receipt, queue_proof, child_processes = _candidate_receipt(contract, operational)

        sources = {
            "journey-ledger.plan.json": operational / "journey-ledger.plan.json",
            "journey-ledger.jsonl": operational / "journey-ledger.jsonl",
            "auth.log": operational / "candidate-auth.log",
            "persistence.log": operational / "candidate-persistence.log",
            "kieker-amqp.spool": operational / SPOOL_ARTIFACT_NAME,
            "traces.json": operational / "traces.json",
            "posture-proof.json": operational / "posture-proof.json",
            "queue-proof.json": operational / "queue-proof.json",
            "runtime-images.json": operational / "runtime-images.json",
            SYSTEM_SAMPLES_ARTIFACT: operational / SYSTEM_SAMPLES_ARTIFACT,
            **({APPLICATION_LOG_ARTIFACT: operational / APPLICATION_LOG_ARTIFACT}
               if APPLICATION_LOG_ARTIFACT in CANDIDATE_COMMON_ARTIFACTS else {}),
            ("resources.json" if receipt["analysisKind"] == "cost" else "intervention.json"):
                operational / (
                    "resources.json" if receipt["analysisKind"] == "cost"
                    else "intervention.json"
                ),
        }
        for name, source in sources.items():
            _publish_regular(source, output / name)

        capture_source = _candidate_json(
            operational / "candidate-service-log-source.json",
            "candidate service-log source proof",
        )
        auth_capture = capture_source["captures"]["auth"]
        service_capture = {
            "schema": "teastore.service-log-capture-receipt",
            "schemaVersion": 1,
            "status": "complete",
            "runId": contract["runId"],
            "service": "auth",
            "containerId": auth_capture["containerId"],
            "source": "docker-container-stdout-stderr",
            "measurementWindow": copy.deepcopy(capture_source["measurementWindow"]),
            "capturedLog": {
                "scope": "measurement-window", "path": "auth.log",
                "sha256": sha256(output / "auth.log"), "complete": True,
            },
            "logParameters": {
                "name": "LOG_PARAMETERS",
                "inspectionSource": "container-config-env",
                "state": capture_source["logParameters"]["state"],
                "rawValue": capture_source["logParameters"]["rawValue"],
                "parameterLoggingEnabled": False,
            },
        }
        _candidate_write_json(output / "service-log-capture.json", service_capture)
        _candidate_write_json(output / "receipt.json", receipt)

        witness = _candidate_module(
            "modules/teastore/witness/extract_app_witness.py",
            "teastore_candidate_runtime_app_witness",
        )
        witness.extract(
            auth_log=output / "auth.log",
            persistence_log=output / "persistence.log",
            journey_ledger=output / "journey-ledger.jsonl",
            run_receipt=output / "receipt.json",
            output=output / "app-witness.jsonl",
            extraction_receipt=output / "app-witness-extraction.json",
        )
        native_token = _candidate_module(
            "modules/teastore/witness/extract_native_token_correlation.py",
            "teastore_candidate_runtime_native_token",
        )
        native_token.extract(
            auth_log=output / "auth.log",
            journey_ledger=output / "journey-ledger.jsonl",
            traces=output / "traces.json",
            run_receipt=output / "receipt.json",
            service_log_capture_receipt=output / "service-log-capture.json",
            posture_proof=output / "posture-proof.json",
            output=output / "native-token-correlation.json",
            extraction_receipt=output / "native-token-correlation-extraction.json",
        )
        capture_terminal = _candidate_capture_terminal(
            output, receipt, queue_proof, child_processes,
        )
        _candidate_write_json(output / "capture-terminal.json", capture_terminal)

        artifact_names = (
            CANDIDATE_COMMON_ARTIFACTS
            | {"resources.json" if receipt["analysisKind"] == "cost" else "intervention.json"}
        ) - {"receipt.json", "candidate-validation.json"}
        receipt["artifacts"] = {
            name: {"sha256": sha256(output / name)} for name in sorted(artifact_names)
        }
        _candidate_write_json(output / "receipt.json", receipt)
        candidate = _candidate_module(
            "modules/teastore/validation/candidate_pilot.py",
            "teastore_candidate_runtime_scientific_validator",
        )
        report = candidate.validate_run(output, expected=copy.deepcopy(contract["runKey"]))
        _candidate_write_json(output / "candidate-validation.json", report)
        if report.get("verdict") != "pass" or report.get("cellStatus") != "valid":
            raise RuntimeError(
                f"candidate scientific validation blocked: {report.get('cellStatus')}"
            )
        if not isinstance(operational, Path) or operational.parent != output or (
            operational.name != ".operational" or operational.is_symlink()
        ):
            raise RuntimeError("candidate operational staging identity differs")
        shutil.rmtree(operational)
        expected_before_controller = set(contract["requiredArtifacts"]) - {
            "content-manifest.json", "cell-cleanup.json",
        }
        if {path.name for path in output.iterdir()} != expected_before_controller:
            raise RuntimeError("candidate producer artifact membership differs")
        return {
            "schemaVersion": 1,
            "kind": CANDIDATE_PRODUCTION_KIND,
            "runId": contract["runId"],
            "runKey": copy.deepcopy(contract["runKey"]),
            "state": "validated",
            "safeToContinue": True,
            "ownedResourcesClean": True,
            "candidateValidationSha256": sha256(output / "candidate-validation.json"),
            "reason": None,
            "promotionAuthorized": False,
        }
    except BaseException as failure:
        # Retain the diagnosable evidence state before any outer cleanup layer
        # observes the abort; preservation failure must not mask the abort.
        try:
            preserve_blocked_evidence(
                output, failure,
                run_id=contract["runId"], run_key=dict(contract["runKey"]),
            )
        except Exception as retain_error:  # noqa: BLE001 - best-effort quarantine
            if hasattr(failure, "add_note"):
                failure.add_note(
                    "blocked-evidence preservation failed: "
                    f"{type(retain_error).__name__}: {retain_error}"
                )
        raise
    finally:
        if previous_project is None:
            os.environ.pop("OBSPLACEMENT_COMPOSE_PROJECT", None)
        else:  # pragma: no cover - guarded above, retained for structured cleanup
            os.environ["OBSPLACEMENT_COMPOSE_PROJECT"] = previous_project


def validate_existing_receipt(path: Path, run_id: str, posture: str, configuration: dict) -> None:
    receipt = json.loads(path.read_text())
    source = receipt.get("source", {})
    mismatches = []
    expected_analysis = analysis_contract(configuration.get("fault", "none"))
    for actual, expected, name in (
        (receipt.get("runId"), run_id, "runId"),
        (receipt.get("posture"), posture, "posture"),
        (source.get("frameworkCommit"), configuration["frameworkCommit"], "frameworkCommit"),
        (source.get("sutReferenceCommit"), configuration["sutReferenceCommit"],
         "sutReferenceCommit"),
        (source.get("selectionId"), configuration["selectionId"], "selectionId"),
        (source.get("selectionSourceSha256"), configuration["selectionSourceSha256"], "selectionSourceSha256"),
        (source.get("descriptorId"), configuration["descriptorId"], "descriptorId"),
        (source.get("descriptorSha256"), configuration["descriptorSha256"], "descriptorSha256"),
        (source.get("evidenceLabel"), configuration["evidenceLabel"], "evidenceLabel"),
    ):
        if actual != expected:
            mismatches.append(name)
    if posture == "selected" and source.get("activationManifestSha256") != configuration["activationManifestSha256"]:
        mismatches.append("activationManifestSha256")
    if receipt.get("analysisKind") != expected_analysis["analysisKind"]:
        mismatches.append("analysisKind")
    if receipt.get("resourceUse") != expected_analysis["resourceUse"]:
        mismatches.append("resourceUse")
    if expected_analysis["usesPerformanceProbe"]:
        if not isinstance(receipt.get("resources"), dict):
            mismatches.append("resources")
    elif receipt.get("resources") is not None:
        mismatches.append("resources")
    runtime_images_path = path.parent / "runtime-images.json"
    try:
        runtime_images = json.loads(runtime_images_path.read_text())
        validate_runtime_images(runtime_images)
        if source.get("runtimeImagesSha256") != sha256(runtime_images_path):
            mismatches.append("runtimeImagesSha256")
    except (OSError, json.JSONDecodeError, RuntimeError):
        mismatches.append("runtimeImages")
    queue_proof_path = path.parent / "queue-proof.json"
    try:
        queue_proof = json.loads(queue_proof_path.read_text())
        validate_queue_proof(queue_proof)
        queue_digest = sha256(queue_proof_path)
        if (source.get("queueProofSha256") != queue_digest
                or receipt.get("queue", {}).get("proofSha256") != queue_digest):
            mismatches.append("queueProofSha256")
    except (OSError, json.JSONDecodeError, RuntimeError):
        mismatches.append("queueProof")
    child_processes_path = path.parent / "child-processes.json"
    try:
        child_processes = json.loads(child_processes_path.read_text())
        expected_children = {
            "collector": receipt.get("processes", {}).get("collector"),
        }
        if expected_analysis["usesPerformanceProbe"]:
            expected_children["performanceProbe"] = receipt.get(
                "processes", {}).get("performanceProbe")
        elif "performanceProbe" in receipt.get("processes", {}):
            mismatches.append("performanceProbe")
        expected_children["systemProbe"] = receipt.get("processes", {}).get("systemProbe")
        if (child_processes != expected_children
                or source.get("childProcessesSha256") != sha256(child_processes_path)
                or any(not isinstance(value, dict) or value.get("joined") is not True
                       for value in child_processes.values())):
            mismatches.append("childProcesses")
    except (OSError, json.JSONDecodeError, AttributeError):
        mismatches.append("childProcesses")
    if receipt.get("schemaVersion") == 2:
        spool_path = path.parent / SPOOL_ARTIFACT_NAME
        try:
            replay = replay_spool_evidence(spool_path, runtime_images_path)
            summary = replay["summary"]
            telemetry = receipt.get("telemetry", {})
            stats = telemetry.get("collectorStats", {})
            _, attribution_digest = validate_collector_attribution_binding(
                stats,
                runtime_images_path=runtime_images_path,
                require_candidate=True,
            )
            if (summary.get("complete") is not True
                    or source.get("spoolSha256") != sha256(spool_path)
                    or source.get("collectorAttributionConfigurationSha256")
                    != attribution_digest
                    or telemetry.get("spool") != summary
                    or stats.get("spool") != summary
                    or stats.get("attribution_configuration")
                    != replay["attributionConfiguration"]
                    or stats.get("attribution_configuration_sha256")
                    != replay["attributionConfigurationSha256"]
                    or replay["events"] != json.loads((path.parent / "traces.json").read_text())):
                mismatches.append("durableSpool")
        except Exception:  # noqa: BLE001 - malformed durable evidence is incompatible
            mismatches.append("durableSpool")
    canonicality = receipt.get("canonicality", {})
    if canonicality.get("label") != configuration["evidenceLabel"] or canonicality.get("blockers") != []:
        mismatches.append("canonicality")
    teardown = receipt.get("teardown", {})
    down = teardown.get("downCommand", {})
    remaining = teardown.get("projectResources", {})
    if (teardown.get("projectClean") is not True
            or down.get("command") != compose(posture, "down", "-v", "--remove-orphans")
            or down.get("returnCode") != 0
            or remaining.get("project") != project_name()
            or not resources_clean(remaining)):
        mismatches.append("teardown")
    if mismatches:
        raise RuntimeError(f"existing receipt {path} is incompatible with schedule: {mismatches}")


def main() -> int:
    # The CLI itself is retained only for review.  Block before argument-driven
    # output creation, schedule materialization, Docker inventory, or run_one.
    raise RuntimeError(CONSTRUCTION_RUNTIME_BLOCKED)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--framework-commit", required=True)
    parser.add_argument("--sut-reference-commit", required=True)
    parser.add_argument("--blocks", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260803)
    parser.add_argument("--warmup", type=int, default=120)
    parser.add_argument("--duration", type=int, default=600)
    parser.add_argument("--rate", type=float, default=0.15)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--postures", default="none,selected,full")
    parser.add_argument("--fault", choices=("none", "auth-freeze", "persistence-crash"), default="none")
    parser.add_argument("--fault-at", type=int, default=240)
    parser.add_argument("--outage", type=int, default=30)
    parser.add_argument("--selection-id", choices=("auth", "fault-qualification"), default="auth")
    parser.add_argument("--descriptor-id", required=True)
    parser.add_argument("--descriptor-sha256", required=True)
    parser.add_argument("--evidence-label", choices=sorted(ALLOWED_EVIDENCE_LABELS), required=True)
    args = parser.parse_args()
    try:
        configured_postures = validate_parameters(args)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    schedule = []
    for block in range(1, args.blocks + 1):
        postures = list(configured_postures)
        rng.shuffle(postures)
        schedule.extend({"block": block, "posture": posture} for posture in postures)
    configuration = campaign_configuration(args, configured_postures)
    schedule_document = {"configuration": configuration, "runs": schedule}
    schedule_path = args.output / "schedule.json"
    if schedule_path.exists():
        if json.loads(schedule_path.read_text()) != schedule_document:
            raise RuntimeError("existing schedule.json differs from requested campaign")
    else:
        schedule_path.write_text(json.dumps(schedule_document, indent=2, sort_keys=True) + "\n")
    result = 0
    try:
        for item in schedule:
            run_id = f"b{item['block']:02d}-{item['posture']}"
            receipt_path = args.output / run_id / "receipt.json"
            if receipt_path.exists():
                validate_existing_receipt(receipt_path, run_id, item["posture"], configuration)
                continue
            receipt = run_one(args.output, run_id, item["posture"], args)
            if receipt["canonicality"]["blockers"]:
                result = 2
                break
    finally:
        final_resources = project_resources()
        clean = resources_clean(final_resources)
        (args.output / "final-hygiene.json").write_text(json.dumps({
            "schemaVersion": 1, "capturedAt": now(), "composeProject": project_name(),
            "projectResources": final_resources, "projectClean": clean,
        }, indent=2, sort_keys=True) + "\n")
        if not clean:
            result = 2
    return result


if __name__ == "__main__":
    raise SystemExit(main())
