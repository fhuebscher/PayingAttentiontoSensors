import importlib.util
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


MODULE = Path(__file__).parents[1] / "modules/teastore/validation/srv5_terminal.py"
SPEC = importlib.util.spec_from_file_location("srv5_terminal", MODULE)
srv5_terminal = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(srv5_terminal)

FIXED_LOAD_MODULE = Path(__file__).parents[1] / "modules/teastore/workload/fixed_load.py"
FIXED_LOAD_SPEC = importlib.util.spec_from_file_location(
    "fixed_load_for_terminal_tests", FIXED_LOAD_MODULE)
fixed_load = importlib.util.module_from_spec(FIXED_LOAD_SPEC)
assert FIXED_LOAD_SPEC.loader
FIXED_LOAD_SPEC.loader.exec_module(fixed_load)


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def clean_resources(project: str) -> dict:
    label = f"label=com.docker.compose.project={project}"
    commands = {
        "containers": ["docker", "ps", "-aq", "--filter", label],
        "networks": ["docker", "network", "ls", "-q", "--filter", label],
        "volumes": ["docker", "volume", "ls", "-q", "--filter", label],
    }
    return {
        "project": project,
        "queryPassed": True,
        "containers": [],
        "networks": [],
        "volumes": [],
        "queries": {
            kind: {"command": command, "returnCode": 0, "stdout": "", "stderr": ""}
            for kind, command in commands.items()
        },
    }


def sanitized_query(command: list[str], *, return_code: int = 0,
                    stdout: str = "", stderr: str = "") -> dict:
    def stream(value: str) -> dict:
        payload = value.encode()
        return {
            "sha256": srv5_terminal._sha256_bytes(payload),
            "bytes": len(payload),
            "lineCount": len(value.splitlines()),
        }

    return {
        "command": command, "returnCode": return_code,
        "stdout": stream(stdout), "stderr": stream(stderr),
    }


def compact_tree(
    root: str, *, entry_count: int = 1, file_count: int = 0,
    total_file_bytes: int = 0,
) -> dict:
    """Build the exact compact, complete two-pass tree proof produced by the harness."""

    chunk_size = 4096
    if entry_count == 1 and file_count == 0:
        root_record = {
            "path": ".", "kind": "directory", "mode": 0o40700,
            "uid": 1000, "gid": 1000, "size": 4096,
            "mtimeNs": 1, "ctimeNs": 1, "device": 1, "inode": 1,
            "nlink": 2, "symlinkTargetSha256": "",
        }
        chunks = [srv5_terminal._sha256_bytes(
            (json.dumps(root_record, sort_keys=True, separators=(",", ":")) + "\n").encode())]
    else:
        chunks = [
            srv5_terminal._sha256_bytes(f"{root}:chunk:{index}".encode())
            for index in range((entry_count + chunk_size - 1) // chunk_size)
        ]
    metadata_sha256 = srv5_terminal._sha256_bytes(json.dumps({
        "algorithm": "sha256", "chunkSize": chunk_size,
        "entryCount": entry_count, "chunks": chunks,
    }, sort_keys=True, separators=(",", ":")).encode())
    summary = {
        "dialect": "srv5-tree-metadata-v1", "algorithm": "sha256",
        "complete": True, "exists": True, "rootKind": "directory",
        "entryCount": entry_count,
        "kindCounts": {
            "directory": entry_count - file_count, "file": file_count,
            "symlink": 0, "other": 0,
        },
        "totalFileBytes": total_file_bytes,
        "oldestMtimeNs": 1, "newestMtimeNs": 1,
        "metadataSha256": metadata_sha256,
        "chunkSize": chunk_size, "chunkCount": len(chunks), "chunkSha256": chunks,
        "errorCount": 0,
        "errorSha256": srv5_terminal._sha256_bytes(b"[]"),
    }
    pass_sha256 = srv5_terminal._sha256_bytes(json.dumps(
        summary, sort_keys=True, separators=(",", ":")).encode())
    return {
        "root": root, **summary,
        "firstPassSha256": pass_sha256, "secondPassSha256": pass_sha256,
        "stable": True,
    }


def comprehensive_inventory(
    campaign_name: str, captured_at: datetime, *, completed: bool = True,
) -> dict:
    """A complete sanitized-v3 proof shaped like srv5_harness.REMOTE_INVENTORY."""

    project = f"obst-{campaign_name}"
    session = f"teastore-{campaign_name}"
    result_tree = compact_tree(srv5_terminal.REMOTE_RESULTS)
    release_tree = compact_tree(srv5_terminal.REMOTE_RUNS)
    resources = {
        "project": project, "queryPassed": True,
        "containers": [], "networks": [], "volumes": [],
    }
    result_paths = {
        "resultRoot": completed, "log": completed, "exit": completed,
    }
    required_ports = {str(port): [] for port in srv5_terminal.REQUIRED_PORTS}
    classifications = {name: 0 for name in srv5_terminal.RESOURCE_CLASSES}
    classification = {
        "policySource": "modules/teastore/deployment/srv5.yaml",
        "policySha256": srv5_terminal._sha256_bytes((
            Path(__file__).parents[1] / "modules/teastore/deployment/srv5.yaml"
        ).read_bytes()),
        "counts": classifications,
        "blocking": [],
    }
    docker = {
        "containers": [], "images": [], "composeProjects": [], "networks": [],
        "volumes": [], "eventsLastHour": [], "queueStates": [], "parseErrors": [],
        "info": {
            "serverVersion": "29.6.1", "containers": 0, "containersRunning": 0,
            "containersPaused": 0, "containersStopped": 0, "images": 0,
            "driver": "overlay2", "cgroupDriver": "systemd", "cgroupVersion": "2",
            "nCpu": 16, "memTotal": 1024, "dockerRootDirSha256": "d" * 64,
        },
    }
    paths = {
        "resultTree": result_tree,
        "releaseTree": release_tree,
        "allOpenWriters": [],
    }
    tool_names = {
        "tool.dockerServer", "tool.dockerCompose", "tool.tmux", "tool.screen",
        "tool.python", "tool.ss", "tool.setsid", "tool.flock", "docker.daemonStarted",
    }
    host = {
        "hostnameSha256": "a" * 64, "kernel": "5.10", "platformSha256": "b" * 64,
        "bootEpoch": 1, "bootUtc": "1970-01-01T00:00:01+00:00", "cpuCount": 16,
        "loadAverage": [0.1, 0.2, 0.3],
        "memoryKiB": {"MemTotal": 1024, "MemAvailable": 512, "SwapTotal": 0, "SwapFree": 0},
        "rootFilesystem": {
            "path": "/", "blockSize": 4096, "totalKiB": 200 * 1024 * 1024,
            "freeKiB": 100 * 1024 * 1024, "totalInodes": 1000, "freeInodes": 900,
        },
        "toolVersions": {
            name: {"valueSha256": "c" * 64, "present": True} for name in tool_names
        },
    }
    stable = {
        "containers": [], "images": [], "composeProjects": [], "networks": [], "volumes": [],
        "runningContainers": [], "projectResources": resources, "requiredPorts": required_ports,
        "experimentSessions": [], "relevantProcesses": [], "resultPaths": result_paths,
        "releaseExists": completed,
        "resultTreeSha256": result_tree["metadataSha256"],
        "releaseTreeSha256": release_tree["metadataSha256"],
        "openWriters": [], "allOpenWriters": [],
        "timeSynchronized": True, "queueStates": [], "classification": classification,
    }
    label = f"label=com.docker.compose.project={project}"
    commands = {
        "project.containers": ["docker", "ps", "-aq", "--no-trunc", "--filter", label],
        "project.networks": ["docker", "network", "ls", "-q", "--no-trunc", "--filter", label],
        "project.volumes": ["docker", "volume", "ls", "-q", "--filter", label],
        "containers.list": ["docker", "ps", "-aq", "--no-trunc"],
        "containers.inspect": ["docker", "inspect"],
        "images.inspect": ["docker", "image", "inspect"],
        "compose.projects": ["docker", "compose", "ls", "--all", "--format", "json"],
        "networks.list": ["docker", "network", "ls", "-q", "--no-trunc"],
        "networks.inspect": ["docker", "network", "inspect"],
        "volumes.list": ["docker", "volume", "ls", "-q"],
        "volumes.inspect": ["docker", "volume", "inspect"],
        "docker.info": ["docker", "info", "--format", "{{json .}}"],
        "host.listeners": ["ss", "-H", "-lntup"],
        "host.processes": ["ps", "-eo", "pid=,ppid=,user=,lstart=,etimes=,args="],
        "sessions.exact": ["tmux", "has-session", "-t", session],
        "sessions.tmux": ["tmux", "list-sessions", "-F", "#{session_name}\t#{session_created}\t#{session_attached}"],
        "sessions.screen": ["screen", "-ls"],
        "host.timeSync": ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
        "tool.dockerServer": ["docker", "version", "--format", "{{.Server.Version}}"],
        "tool.dockerCompose": ["docker", "compose", "version", "--short"],
        "tool.tmux": ["tmux", "-V"], "tool.screen": ["screen", "--version"],
        "tool.python": ["python3", "--version"], "tool.ss": ["ss", "--version"],
        "tool.setsid": ["setsid", "--version"], "tool.flock": ["flock", "--version"],
        "docker.daemonStarted": ["systemctl", "show", "docker", "--property=ActiveEnterTimestamp", "--value"],
    }
    proofs = {name: sanitized_query(command) for name, command in commands.items()}
    proofs["docker.events"] = sanitized_query([
        "docker", "events", "--since", "1000", "--until", "4600", "--format", "{{json .}}",
    ])
    proofs["host.timeSync"] = sanitized_query(
        commands["host.timeSync"], stdout="yes\n")
    proofs["sessions.exact"] = sanitized_query(
        commands["sessions.exact"], return_code=1, stderr="no server running\n")
    proofs["sessions.tmux"] = sanitized_query(
        commands["sessions.tmux"], return_code=1, stderr="no server running\n")
    proofs["sessions.screen"] = sanitized_query(
        commands["sessions.screen"], return_code=1, stdout="No Sockets found.\n")
    return {
        "schemaVersion": 3, "capturedAt": captured_at.isoformat(), "target": "fb14srv5",
        "campaign": campaign_name, "composeProject": project, "session": session,
        "active": False, "projectResources": resources, "openWriters": [],
        "runningContainers": [], "rootFreeKiB": 100 * 1024 * 1024,
        "cpuCount": 16, "load1": 0.1, "resultPaths": result_paths,
        "releaseExists": completed, "host": host, "docker": docker, "listeners": [],
        "requiredPorts": required_ports, "sessions": {"all": [], "experimentLike": []},
        "processes": {"experimentLike": []}, "paths": paths,
        "timeSync": {"synchronized": True}, "classification": classification,
        "stableState": stable,
        "stateFingerprint": srv5_terminal._sha256_bytes(json.dumps(
            stable, sort_keys=True, separators=(",", ":")).encode()),
        "queryProofs": proofs, "queryPassed": True, "verdict": "pass", "blockers": [],
    }
def runtime_images(project: str) -> dict:
    services = {}
    for index, service in enumerate(srv5_terminal.RUNTIME_SERVICES, start=1):
        digit = f"{index:x}"
        container_id = digit * 64
        image_id = f"sha256:{digit * 64}"
        declared = srv5_terminal.EXPECTED_RUNTIME_IMAGES[service]
        repository = srv5_terminal.EXPECTED_RUNTIME_REPOSITORIES[service]
        services[service] = {
            "containerId": container_id,
            "declaredImage": declared,
            "containerImageId": image_id,
            "imageInspectId": image_id,
            "repoDigests": [f"{repository}@sha256:{digit * 64}"],
            "composeProjectLabel": project,
            "composeServiceLabel": service,
            "queries": {
                "containerInspect": {
                    "command": ["docker", "inspect", "--format",
                                srv5_terminal.CONTAINER_IMAGE_INSPECT_FORMAT, container_id],
                    "returnCode": 0,
                    "stdout": f"{container_id}\t{image_id}\t{declared}\t{project}\t{service}\n",
                    "stderr": "",
                },
                "imageInspect": {
                    "command": ["docker", "image", "inspect", "--format",
                                srv5_terminal.IMAGE_INSPECT_FORMAT, declared],
                    "returnCode": 0,
                    "stdout": f"{image_id}\t{json.dumps([f'{repository}@sha256:{digit * 64}'])}\n",
                    "stderr": "",
                },
            },
        }
    return {
        "schemaVersion": 1,
        "capturedAt": "2026-08-28T00:00:00+00:00",
        "composeProject": project,
        "services": services,
    }


def queue_state(container_id: str, messages: int, consumers: int) -> dict:
    command = ["docker", "exec", container_id, "rabbitmqctl", "list_queues",
               "-q", "name", "messages", "consumers"]
    return {
        "containerId": container_id,
        "messages": messages,
        "consumers": consumers,
        "query": {
            "command": command, "returnCode": 0,
            "stdout": f"kieker\t{messages}\t{consumers}\n", "stderr": "",
        },
    }


def queue_proof(project: str) -> dict:
    container_id = "a" * 64
    before = queue_state(container_id, 2, 0)
    empty = queue_state(container_id, 0, 0)
    exclusive = queue_state(container_id, 0, 1)
    purge_command = ["docker", "exec", container_id, "rabbitmqctl", "purge_queue", "kieker"]
    return {
        "schemaVersion": 1,
        "composeProject": project,
        "purge": {
            "before": before,
            "command": {"command": purge_command, "returnCode": 0, "stdout": "", "stderr": ""},
            "after": empty,
        },
        "measurement": {"before": empty, "consumerAtStart": exclusive, "after": empty},
    }


def child_process(name: str) -> dict:
    return {
        "pid": 4200 if name == "collector" else 4201,
        "command": ["python3", f"{name}.py"],
        "timeoutSeconds": 60,
        "noProgressTimeoutSeconds": 60 if name == "collector" else None,
        "timedOut": False,
        "communicationError": None,
        "terminateSent": False,
        "killSent": False,
        "joined": True,
        "returnCode": 0,
    }


def descriptor(posture: str = "full", *, deadline: bool = False) -> dict:
    document = {
        "schemaVersion": 1,
        "id": "teastore-performance-diagnostic-smoke",
        "evidenceLabel": "smoke-validation",
        "module": "teastore",
        "target": "fb14srv5",
        "executor": "ssh-compose",
        "source": {
            "frameworkCommit": "required-at-materialization",
            "sutReferenceCommit": "34b37f7e7be433ce72d5f9455e66922a13116749",
        },
        "runner": "modules/teastore/execution/performance_campaign.py",
        "design": {
            "blocks": 1,
            "seed": 20260803,
            "postures": [{"id": posture, "contract": f"postures/{posture}.yaml"}],
            "warmupSeconds": 120,
            "measurementSeconds": 60,
            "workload": {
                "path": "modules/teastore/workload/fixed_load.py",
                "kind": "fixed-open-loop",
                "journeysPerSecond": 0.15,
                "concurrency": 8,
            },
            "fault": {"scenario": "none"},
            "selectionId": "auth",
            "coldStartEachRun": True,
        },
        "collector": {
            "path": "modules/teastore/collectors/kieker_native.py",
            "durationSeconds": 90,
            "inactivityTimeoutSeconds": 10,
            "queue": "kieker",
            "requiredConsumers": 1,
        },
        "validation": [
            "immutable-descriptor-binding",
            "performance-receipt",
            "native-kieker-contract",
            "queue-purge-recorded",
            "exclusive-consumer",
            "complete-shutdown",
            "content-manifest",
            "runtime-image-provenance",
            "queue-proof-replay",
            "child-process-termination",
            "sanitized-host-inventory",
            "retained-60s-preflight",
            "host-wide-execution-lease",
            "external-manifest-anchor",
        ],
        "promotion": {"canonical": False, "reason": "diagnostic only"},
    }
    if deadline:
        document["validation"].extend(sorted(srv5_terminal.DEADLINE_VALIDATION_GATES))
    return document


def event(service: str, signature: str) -> dict:
    digit = "a" if service == "auth" else "b"
    return {
        "trace_id": f"native-{service}",
        "eoi": 0,
        "ess": 0,
        "message_sha1": digit * 40,
        "signature_sha1": signature,
        "source": "kieker_native",
        "service": service,
        "parent_resolution": "root",
        "correlation_errors": [],
        "correlation_warnings": [],
        "service_attribution_status": "runtime-host-and-signature-agree",
        "service_attribution_errors": [],
    }


def collector_correlation(events: list[dict]) -> dict:
    return {
        "events": len(events),
        "parentResolution": {"root": len(events)} if events else {},
        "serviceAttribution": (
            {"runtime-host-and-signature-agree": len(events)} if events else {}
        ),
        "eventsWithCorrelationErrors": 0,
        "eventsWithUnwovenRootParent": 0,
        "eventsWithProbeOrphanRoot": 0,
        "eventsWithCorrelationWarnings": 0,
        "eventsWithServiceAttributionErrors": 0,
        "traceCompleteness": {
            "traces": len(events),
            "tracesWithEoiGaps": 0,
            "missingEoiCount": 0,
            "tracesNotStartingAtZero": 0,
        },
    }


def reseal(root: Path) -> None:
    # Fixture maintenance only. Production write_manifest deliberately refuses
    # to replace a seal; tests that plant semantic defects remove the old seal
    # explicitly so they exercise the semantic checker rather than only hashing.
    (root / srv5_terminal.MANIFEST_NAME).unlink(missing_ok=True)
    srv5_terminal.write_manifest(root)


def deadline_cleanup(owner: dict, now: datetime) -> dict:
    project = owner["composeProject"]
    release = owner["release"]
    label = f"label=com.docker.compose.project={project}"
    empty = {"sha256": srv5_terminal._sha256_bytes(b""), "bytes": 0, "lineCount": 0}

    def bounded(command: list[str]) -> dict:
        return {
            "attempted": True,
            "command": command,
            "returnCode": 0,
            "timedOut": False,
            "errorCode": None,
            "stdout": dict(empty),
            "stderr": dict(empty),
        }

    commands = {
        "containers": ["docker", "ps", "-aq", "--no-trunc", "--filter", label],
        "networks": ["docker", "network", "ls", "-q", "--no-trunc", "--filter", label],
        "volumes": ["docker", "volume", "ls", "-q", "--filter", label],
    }
    verification = {
        "label": label,
        "queries": {
            kind: bounded(command) | {
                "identifiers": {"count": 0, "sha256": empty["sha256"], "parseValid": True},
            }
            for kind, command in commands.items()
        },
        "remaining": {"containers": 0, "networks": 0, "volumes": 0},
        "clean": True,
    }
    fallback_prefixes = {
        "containers": ["docker", "rm", "-f", "--"],
        "networks": ["docker", "network", "rm", "--"],
        "volumes": ["docker", "volume", "rm", "-f", "--"],
    }
    fallback_actions = {
        kind: {
            "attempted": False,
            "command": command,
            "returnCode": None,
            "timedOut": False,
            "errorCode": None,
            "stdout": dict(empty),
            "stderr": dict(empty),
            "identifierCount": 0,
            "identifiersSha256": empty["sha256"],
        }
        for kind, command in fallback_prefixes.items()
    }
    compose_command = ["docker", "compose", "-p", project]
    for relative in srv5_terminal.DEADLINE_COMPOSE_FILES:
        compose_command.extend(["-f", f"{release}/{relative}"])
    compose_command.extend(["down", "--volumes", "--remove-orphans"])
    triggered = now - timedelta(seconds=3)
    completed = now - timedelta(seconds=2)
    return {
        "schemaVersion": 1,
        "kind": "deadline-cleanup",
        "campaign": owner["campaign"],
        "composeProject": project,
        "release": release,
        "resultRoot": owner["resultRoot"],
        "trigger": {
            "reason": "runner-exit",
            "signal": None,
            "stopEpoch": owner["experimentStopEpoch"],
            "authorizationDeadlineEpoch": owner["authorizationDeadlineEpoch"],
            "triggeredAt": triggered.isoformat(),
        },
        "processGroup": {
            "pid": 5000,
            "processGroupId": 5000,
            "identityValidated": True,
            "aliveAtCleanupStart": False,
            "termSent": False,
            "termSentAt": None,
            "exitedDuringTermGrace": None,
            "killRequired": False,
            "killSent": False,
            "killSentAt": None,
            "gone": True,
            "runnerReturnCode": 0,
        },
        "composeTeardown": bounded(compose_command) | {
            "cwd": release,
            "composeFiles": list(srv5_terminal.DEADLINE_COMPOSE_FILES),
        },
        "verification": {
            "initial": verification,
            "fallback": {"required": False, "actions": fallback_actions},
            "final": verification,
        },
        "authorization": {
            "completedAt": completed.isoformat(),
            "completedAtEpoch": completed.timestamp(),
            "beforeDeadline": True,
            "leaseFinalizerReserveSeconds": srv5_terminal.DEADLINE_LEASE_FINALIZER_SECONDS,
            "leaseFinalizerWindowAvailable": True,
            "leaseReleaseDelegatedToLauncherFinalizer": True,
        },
        "outcome": "clean",
        "blockers": [],
        "warnings": [],
    }


def campaign(tmp_path: Path, posture: str = "full", *, deadline: bool = False):
    root = tmp_path / "campaign-1"
    root.mkdir()
    now = datetime.now(timezone.utc)
    descriptor_path = root / "campaign-descriptor.json"
    write(descriptor_path, descriptor(posture, deadline=deadline))
    digest = srv5_terminal._sha256_bytes(descriptor_path.read_bytes())
    project = "obst-campaign-1"
    run_id = f"b01-{posture}"
    configuration = {
        "schemaVersion": 1,
        "descriptorId": "teastore-performance-diagnostic-smoke",
        "descriptorSha256": digest,
        "evidenceLabel": "smoke-validation",
        "seed": 20260803,
        "blocks": 1,
        "postures": [posture],
        "warmupSeconds": 120,
        "measurementSeconds": 60,
        "journeysPerSecond": 0.15,
        "concurrency": 8,
        "fault": "none",
        "faultAtSeconds": None,
        "outageSeconds": None,
        "sutReferenceCommit": "34b37f7e7be433ce72d5f9455e66922a13116749",
        "selectionId": "auth",
        "collectorDurationSeconds": 90,
        "collectorInactivityTimeoutSeconds": 10,
        "frameworkCommit": "4" * 40,
        "selectionSourceSha256": "5" * 64,
        "activationManifestSha256": "6" * 64,
        "composeProject": project,
    }
    write(root / "schedule.json", {
        "configuration": configuration,
        "runs": [{"block": 1, "posture": posture}],
    })
    owner = {
        "schemaVersion": 1,
        "campaign": root.name,
        "target": "fb14srv5",
        "session": f"teastore-{root.name}",
        "composeProject": project,
        "frameworkCommit": configuration["frameworkCommit"],
        "sutReferenceCommit": configuration["sutReferenceCommit"],
        "release": (
            f"/home/stig/observability-placement-runs/"
            f"{configuration['frameworkCommit'][:12]}/{root.name}"
        ),
        "resultRoot": f"/home/stig/observability-placement-results/{root.name}",
        "descriptorId": configuration["descriptorId"],
        "descriptorSha256": configuration["descriptorSha256"],
        "expectedReceipts": 1,
    }
    if deadline:
        candidate_source_path = (
            Path(__file__).parents[1] / "pipelines/campaigns/teastore-candidate-pilot-sys-v1.json"
        )
        candidate_source = json.loads(candidate_source_path.read_text(encoding="utf-8"))
        candidate_module = srv5_terminal._load_module(
            Path(__file__).parents[1] / "modules/teastore/execution/candidate_pilot.py",
            "candidate_pilot_for_terminal_fixture",
        )
        authorization_deadline = now + timedelta(hours=2)
        admission = candidate_module.admit_runtime(
            candidate_source,
            mode="diagnostic",
            evidence_label="smoke-validation",
            now=now - timedelta(minutes=10),
            authorization_deadline=authorization_deadline,
            time_budget_seconds=7200,
            diagnostic_run_count=1,
            diagnostic_warmup_seconds=120,
            diagnostic_measurement_seconds=60,
            lifecycle_allowance_seconds=0,
        )
        write(root / "runtime-admission-source.json", candidate_source)
        write(root / "runtime-admission.json", admission)
        deadline_epoch = math.floor(authorization_deadline.timestamp())
        owner.update({
            "schemaVersion": 2,
            "runtimeAdmissionSha256": srv5_terminal._sha256_bytes(
                (root / "runtime-admission.json").read_bytes()),
            "authorizationDeadlineEpoch": deadline_epoch,
            "experimentStopEpoch": deadline_epoch - srv5_terminal.DEADLINE_CLEANUP_RESERVE_SECONDS,
            "cleanupReserveSeconds": srv5_terminal.DEADLINE_CLEANUP_RESERVE_SECONDS,
        })
    write(root / "harness-owner.json", owner)
    run = root / run_id
    run.mkdir()
    image_proof = runtime_images(project)
    write(run / "runtime-images.json", image_proof)
    image_digest = srv5_terminal._sha256_bytes((run / "runtime-images.json").read_bytes())
    retained_queue = queue_proof(project)
    write(run / "queue-proof.json", retained_queue)
    queue_digest = srv5_terminal._sha256_bytes((run / "queue-proof.json").read_bytes())
    retained_children = {
        "collector": child_process("collector"),
        "performanceProbe": child_process("performanceProbe"),
    }
    write(run / "child-processes.json", retained_children)
    child_digest = srv5_terminal._sha256_bytes((run / "child-processes.json").read_bytes())
    events = [] if posture == "none" else [event("auth", "sig-a"), event("webui", "sig-b")]
    write(run / "traces.json", events)
    telemetry_bytes = (run / "traces.json").stat().st_size
    collector_stats = {
        "messages": len(events),
        "containers_ok": len(events),
        "containers_bad": 0,
        "records_ok": len(events),
        "records_bad": 0,
        "record_parse_success_ratio": 1.0 if events else 0.0,
        "container_parse_success_ratio": 1.0 if events else 0.0,
        "acknowledgement_mode": "manual",
        "runtime_host_map_loaded": True,
        "correlation": collector_correlation(events),
    }
    (run / "collector.stderr").write_text(json.dumps(collector_stats, indent=2) + "\n")
    measured_started = datetime(2026, 8, 28, tzinfo=timezone.utc).timestamp()
    measured_ended = measured_started + 60
    workload = {
        "schemaVersion": 1,
        "startedAtEpoch": measured_started,
        "endedAtEpoch": measured_ended,
        "schedule": {
            "kind": "fixed-open-loop", "journeysPerSecond": 0.15,
            "durationSeconds": 60,
        },
        "offered": 9, "completed": 9, "failed": 0, "concurrency": 8,
        "requests": 90,
        "latencyMs": {"count": 9, "p50": 1, "p95": 2, "p99": 3, "mean": 1.5},
        "failures": [],
    }
    warmup = {
        "schemaVersion": 1,
        "startedAtEpoch": measured_started - 120,
        "endedAtEpoch": measured_started,
        "schedule": {
            "kind": "fixed-open-loop", "journeysPerSecond": 0.15,
            "durationSeconds": 120,
        },
        "offered": 18, "completed": 18, "failed": 0, "concurrency": 8,
        "requests": 180,
        "latencyMs": {"count": 18, "p50": 1, "p95": 2, "p99": 3, "mean": 1.5},
        "failures": [],
    }
    resources = {
        "schemaVersion": 1,
        "startedAtEpoch": measured_started,
        "endedAtEpoch": measured_ended,
        "applicationCpuSeconds": 1,
        "applicationMemoryPeakBytes": 2,
        "hostCpuSeconds": 3,
        "sampleIntervalSeconds": 2,
        "excludedServices": ["db", "rabbitmq", "registry"],
        "samples": [{
            "epoch": measured_started + 1,
            "applicationCpuPercent": 1,
            "applicationMemoryBytes": 2,
            "containers": [{"Name": "webui", "CPUPerc": "1.0%", "MemUsage": "2B / 1GiB"}],
        }],
    }
    enabled = "false" if posture == "none" else "true"
    posture_services = {
        service: {
            "aopSha256": "7" * 64,
            "configuration": f"kieker.monitoring.enabled={enabled}",
            "writerInitializationFailed": False,
        }
        for service in srv5_terminal.APP_SERVICES
    }
    retained_posture = {"requested": posture, "services": posture_services}
    write(run / "workload.json", workload)
    write(run / "warmup.json", warmup)
    write(run / "resources.json", resources)
    write(run / "posture-proof.json", retained_posture)
    down = {
        "schemaVersion": 1,
        "command": srv5_terminal._compose_down(project, posture),
        "returnCode": 0,
        "stdout": "",
        "stderr": "",
    }
    teardown = clean_resources(project)
    write(run / "ownership-preflight.json", {
        "composeProject": project,
        "resourcesBefore": clean_resources(project),
    })
    write(run / "down-command.json", down)
    write(run / "teardown.json", teardown)
    receipt = {
        "schemaVersion": 1,
        "runId": run_id,
        "sut": "teastore",
        "posture": posture,
        "source": {
            "frameworkCommit": configuration["frameworkCommit"],
            "sutReferenceCommit": configuration["sutReferenceCommit"],
            "dirty": False,
            "selectionId": "auth",
            "selectionSourceSha256": configuration["selectionSourceSha256"],
            "activationManifestSha256": configuration["activationManifestSha256"] if posture == "selected" else None,
            "descriptorId": configuration["descriptorId"],
            "descriptorSha256": configuration["descriptorSha256"],
            "evidenceLabel": configuration["evidenceLabel"],
            "runtimeImagesSha256": image_digest,
            "queueProofSha256": queue_digest,
            "childProcessesSha256": child_digest,
        },
        "window": {
            "startedAt": datetime.fromtimestamp(measured_started, timezone.utc).isoformat(),
            "endedAt": datetime.fromtimestamp(measured_ended, timezone.utc).isoformat(),
            "warmupSeconds": 120,
            "measurementSeconds": 60,
        },
        "workload": {"offered": 9, "completed": 9, "failed": 0, "concurrency": 8},
        "latencyMs": workload["latencyMs"],
        "resources": {"applicationCpuSeconds": 1, "applicationMemoryPeakBytes": 2, "hostCpuSeconds": 3},
        "telemetry": {
            "records": len(events),
            "bytes": telemetry_bytes,
            "uniqueSignatures": len({row["signature_sha1"] for row in events}),
            "parseFailures": 0,
            "collectorStats": collector_stats,
        },
        "processes": {
            "workload": {"returnCode": 0},
            "collector": retained_children["collector"],
            "performanceProbe": retained_children["performanceProbe"],
        },
        "postureProof": retained_posture,
        "queue": {
            "purgedBefore": True,
            "messagesBefore": 0,
            "messagesAfter": 0,
            "exclusiveConsumer": True,
            "proofSha256": queue_digest,
        },
        "canonicality": {"label": "smoke-validation", "blockers": []},
        "teardown": {"downCommand": down, "projectResources": teardown, "projectClean": True},
    }
    write(run / "receipt.json", receipt)
    first_preflight = comprehensive_inventory(
        root.name, now - timedelta(seconds=66), completed=False)
    second_preflight = comprehensive_inventory(
        root.name, now - timedelta(seconds=6), completed=False)
    write(root / "preflight.json", {
        "schemaVersion": 1,
        "recordedAt": (now - timedelta(seconds=5)).isoformat(),
        "campaign": root.name,
        "target": "fb14srv5",
        "source": {
            "frameworkCommit": configuration["frameworkCommit"],
            "sutReferenceCommit": configuration["sutReferenceCommit"],
            "descriptorId": configuration["descriptorId"],
            "descriptorSha256": configuration["descriptorSha256"],
        },
        "preflight": {
            "schemaVersion": 2,
            "campaign": root.name,
            "target": "fb14srv5",
            "settleSeconds": 60,
            "stable": True,
            "first": first_preflight,
            "second": second_preflight,
            "verdict": "pass",
            "blockers": [],
        },
    })
    write(root / "final-hygiene.json", {
        "schemaVersion": 1,
        "capturedAt": (now - timedelta(seconds=2)).isoformat(),
        "composeProject": project,
        "projectResources": clean_resources(project),
        "projectClean": True,
    })
    status = {"campaign": root.name, "active": False, "exitCode": "0", "receipts": 1, "expected": 1}
    remote = comprehensive_inventory(root.name, now)
    if deadline:
        write(root / "deadline-cleanup.json", deadline_cleanup(owner, now))
    write(root / "execution-lease.json", {
        "schemaVersion": 1,
        "scope": "fb14srv5:teastore-performance",
        "lockPath": srv5_terminal.HOST_LEASE_PATH,
        "campaign": root.name,
        "launcherPid": 4100,
        "acquisition": {
            "attemptedAt": (now - timedelta(seconds=4)).isoformat(),
            "acquired": True,
            "acquiredAt": (now - timedelta(seconds=3)).isoformat(),
            "returnCode": 0,
            "mechanism": "flock-nonblocking-fd",
        },
        "release": {
            "requestedAt": (now - timedelta(seconds=1)).isoformat(),
            "unlockReturnCode": 0,
            "verificationReturnCode": 0,
            "observed": True,
            "mechanism": "unlock-close-and-nonblocking-reacquire",
        },
    })
    write(root / "terminal-status.json", status)
    write(root / "remote-final-state.json", remote)
    reseal(root)
    return root, descriptor_path, status, remote


def validate(parts):
    return srv5_terminal.validate_campaign(*parts)


def test_v2_resource_probe_requires_complete_services_and_shared_barrier():
    document = {
        "schemaVersion": 2,
        "startedAtEpoch": 1000.2,
        "endedAtEpoch": 1060.2,
        "applicationCpuSeconds": 1,
        "applicationMemoryPeakBytes": 2,
        "hostCpuSeconds": 3,
        "sampleIntervalSeconds": 2,
        "excludedServices": ["db", "rabbitmq", "registry"],
        "requiredServices": sorted(srv5_terminal.APP_SERVICES),
        "requestedStartAtEpoch": 1000.0,
        "barrierId": "barrier-" + "a" * 32,
        "samples": [{
            "epoch": 1001.0,
            "applicationCpuPercent": 1,
            "applicationMemoryBytes": 2,
            "containers": [{}],
        }],
    }
    receipt = {"resources": {
        "applicationCpuSeconds": 1,
        "applicationMemoryPeakBytes": 2,
        "hostCpuSeconds": 3,
    }}
    assert srv5_terminal._resources_artifact_blockers(
        document, receipt=receipt, where="planted") == []

    missing = dict(document, requiredServices=["auth"])
    blockers = srv5_terminal._resources_artifact_blockers(
        missing, receipt=receipt, where="planted")
    assert any("service set is incomplete" in item for item in blockers)

    stale = dict(document, requestedStartAtEpoch=990.0)
    blockers = srv5_terminal._resources_artifact_blockers(
        stale, receipt=receipt, where="planted")
    assert any("shared measurement barrier" in item for item in blockers)


def test_v3_resource_identity_is_cross_bound_to_runtime_image_proof():
    identities = {
        service: f"{index + 1:064x}"
        for index, service in enumerate(sorted(srv5_terminal.APP_SERVICES))
    }
    document = {
        "schemaVersion": 3,
        "contract": "teastore-resource-probe-v3",
        "containerIdentity": identities,
        "applicationCpuSeconds": 1.0,
        "applicationMemoryPeakBytes": 2.0,
        "hostCpuSeconds": 3.0,
        "nominalStartAtEpoch": 1000.0,
        "nominalEndAtEpoch": 1010.0,
        "measurementDurationSeconds": 10.0,
        "sampling": {"intervalSeconds": 5.0},
    }
    receipt = {"resources": {
        "applicationCpuSeconds": 1.0,
        "applicationMemoryPeakBytes": 2.0,
        "hostCpuSeconds": 3.0,
        "contract": "teastore-resource-probe-v3",
        "artifactSha256": "d" * 64,
        "nominalStartAtEpoch": 1000.0,
        "nominalEndAtEpoch": 1010.0,
        "measurementDurationSeconds": 10.0,
        "samplingIntervalSeconds": 5.0,
        "offeredJourneys": 2,
        "applicationCpuSecondsPerOfferedJourney": 0.5,
    }}

    class PassingReplay:
        @staticmethod
        def validate_resource_evidence(*_args, **_kwargs):
            return {"verdict": "pass", "blockers": []}

    assert srv5_terminal._resources_artifact_blockers(
        document, receipt=receipt, where="planted", resource_validator=PassingReplay,
        artifact_sha256="d" * 64, offered_journeys=2,
        expected_container_identity=identities,
    ) == []
    drifted = dict(identities)
    drifted["persistence"] = "f" * 64
    blockers = srv5_terminal._resources_artifact_blockers(
        document, receipt=receipt, where="planted", resource_validator=PassingReplay,
        artifact_sha256="d" * 64, offered_journeys=2,
        expected_container_identity=drifted,
    )
    assert any("independent runtime-image proof" in item for item in blockers)


def test_v2_workload_aggregate_replays_the_shared_barrier():
    started = 1000.0
    ended = 1060.0
    document = {
        "schemaVersion": 2,
        "controllerStartedAtEpoch": 999.0,
        "startedAtEpoch": started,
        "endedAtEpoch": ended,
        "schedule": {
            "kind": "fixed-open-loop",
            "journeysPerSecond": 0.15,
            "durationSeconds": 60,
            "barrierAtEpoch": started,
            "barrierId": "barrier-" + "a" * 32,
        },
        "offered": 9,
        "completed": 9,
        "successful": 9,
        "failed": 0,
        "timedOut": 0,
        "settled": 9,
        "concurrency": 8,
        "requests": 9,
        "latencyMs": {
            "denominator": "successful-journeys",
            "count": 9, "p50": 1, "p95": 2, "p99": 3, "mean": 1.5,
        },
        "failures": [],
        "journeyEvidence": {
            "plan": "journey-ledger.plan.json",
            "ledger": "journey-ledger.jsonl",
            "planSha256": "b" * 64,
            "lastRecordSha256": "c" * 64,
        },
    }
    receipt = {
        "workload": {
            "offered": 9, "completed": 9, "successful": 9, "failed": 0,
            "timedOut": 0, "settled": 9, "concurrency": 8,
        },
        "latencyMs": document["latencyMs"],
        "window": {
            "startedAt": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "endedAt": datetime.fromtimestamp(ended, timezone.utc).isoformat(),
            "barrierAt": datetime.fromtimestamp(started, timezone.utc).isoformat(),
        },
    }
    configuration = {"journeysPerSecond": 0.15, "concurrency": 8}
    assert srv5_terminal._workload_artifact_blockers(
        document, configuration=configuration, receipt=receipt,
        duration_seconds=60, where="planted") == []

    late_controller = dict(document, controllerStartedAtEpoch=1001.0)
    blockers = srv5_terminal._workload_artifact_blockers(
        late_controller, configuration=configuration, receipt=receipt,
        duration_seconds=60, where="planted")
    assert any("controller/barrier" in item for item in blockers)

    attacked = dict(document, schedule={**document["schedule"], "barrierAtEpoch": 1001.0})
    blockers = srv5_terminal._workload_artifact_blockers(
        attacked, configuration=configuration, receipt=receipt,
        duration_seconds=60, where="planted")
    assert any("schedule differs" in item for item in blockers)


def test_terminal_replays_real_append_only_journey_evidence(monkeypatch, tmp_path: Path):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'<a href="/category?category=1">category</a>'

    class Opener:
        def open(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(fixed_load.urllib.request, "build_opener", lambda *_args: Opener())
    ledger = tmp_path / "journey-ledger.jsonl"
    aggregate = fixed_load.run(
        "http://teastore/tools.descartes.teastore.webui",
        100.0, 0.01, 1, 1.0, ledger, barrier_id="barrier-terminal-v1",
    )
    plan = ledger.with_suffix(".plan.json")
    validation = fixed_load.validate_journey_ledger(plan, ledger)
    receipt = {"candidateArtifacts": {
        "measurementBarrierSha256": "a" * 64,
        "journeyPlanSha256": srv5_terminal._sha256_bytes(plan.read_bytes()),
        "journeyLedgerSha256": srv5_terminal._sha256_bytes(ledger.read_bytes()),
        "journeyPlanCanonicalSha256": validation["planSha256"],
        "journeyLedgerLastRecordSha256": validation["lastRecordSha256"],
        "appWitnessSha256": None,
        "pathGroundTruthStatus": "unsupported",
        "pathGroundTruthReason": "application witness is not installed",
    }}
    assert srv5_terminal._journey_evidence_blockers(
        tmp_path, aggregate, ledger_name=ledger.name, fixed_load=fixed_load,
        receipt=receipt, where="planted",
    ) == []

    ledger.write_bytes(ledger.read_bytes()[:-1])
    blockers = srv5_terminal._journey_evidence_blockers(
        tmp_path, aggregate, ledger_name=ledger.name, fixed_load=fixed_load,
        receipt=receipt, where="planted",
    )
    assert any("truncated" in item for item in blockers)


def test_terminal_replays_legacy_v1_shared_barrier_and_collector_acknowledgement():
    epoch = datetime(2026, 8, 28, tzinfo=timezone.utc).timestamp()
    barrier_id = "barrier-" + "d" * 32
    collector_state = queue_state("e" * 64, 0, 1)
    document = {
        "schemaVersion": 1,
        "barrierId": barrier_id,
        "createdAt": datetime.fromtimestamp(epoch - 1, timezone.utc).isoformat(),
        "barrierAt": datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
        "barrierAtEpoch": epoch,
        "barrierMonotonic": 500.0,
        "measurementSeconds": 60,
        "participants": ["workload", "performance-probe", "collector"],
        "collectorAcknowledgement": {
            "observedAt": datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
            "observedMonotonicOffsetSeconds": 0.0,
            "queueState": collector_state,
        },
    }
    workload = {"schedule": {"barrierId": barrier_id, "barrierAtEpoch": epoch}}
    resources = {"barrierId": barrier_id, "requestedStartAtEpoch": epoch}
    receipt = {
        "intervention": None,
        "window": {"barrierAt": document["barrierAt"]},
    }
    queue = {"measurement": {"consumerAtStart": collector_state}}
    assert srv5_terminal._measurement_barrier_blockers(
        document, workload=workload, resources=resources, receipt=receipt,
        queue_proof=queue, duration_seconds=60, where="planted",
    ) == []

    drifted = dict(document, barrierId="barrier-" + "f" * 32)
    blockers = srv5_terminal._measurement_barrier_blockers(
        drifted, workload=workload, resources=resources, receipt=receipt,
        queue_proof=queue, duration_seconds=60, where="planted",
    )
    assert any("participant bindings differ" in item for item in blockers)


def v2_measurement_barrier_inputs(
    *, start_offset: float = 0.0, completed_offset: float = 0.5,
):
    epoch = datetime(2026, 8, 28, tzinfo=timezone.utc).timestamp()
    barrier_id = "barrier-" + "d" * 32
    collector_state = queue_state("e" * 64, 0, 1)
    document = {
        "schemaVersion": 2,
        "barrierId": barrier_id,
        "createdAt": datetime.fromtimestamp(epoch - 1, timezone.utc).isoformat(),
        "barrierAt": datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
        "barrierAtEpoch": epoch,
        "barrierMonotonic": 500.0,
        "measurementSeconds": 60,
        "participants": ["workload", "performance-probe", "collector"],
        "collectorAcknowledgement": {
            "queryStartedAtWall": datetime.fromtimestamp(
                epoch + start_offset, timezone.utc).isoformat(),
            "queryStartedMonotonicOffsetSeconds": start_offset,
            "queryCompletedAtWall": datetime.fromtimestamp(
                epoch + completed_offset, timezone.utc).isoformat(),
            "queryCompletedMonotonicOffsetSeconds": completed_offset,
            "queueState": collector_state,
        },
    }
    workload = {"schedule": {"barrierId": barrier_id, "barrierAtEpoch": epoch}}
    resources = {"barrierId": barrier_id, "requestedStartAtEpoch": epoch}
    receipt = {"intervention": None, "window": {"barrierAt": document["barrierAt"]}}
    queue = {"measurement": {"consumerAtStart": collector_state}}
    return document, workload, resources, receipt, queue


def test_v2_collector_query_timing_accepts_exact_early_and_late_boundaries():
    document, workload, resources, receipt, queue = v2_measurement_barrier_inputs(
        start_offset=-1.0, completed_offset=5.0)
    assert srv5_terminal._measurement_barrier_blockers(
        document, workload=workload, resources=resources, receipt=receipt,
        queue_proof=queue, duration_seconds=60, where="planted",
    ) == []


def test_effect_barrier_excludes_cost_probe_and_resource_binding():
    document, workload, _resources, receipt, queue = v2_measurement_barrier_inputs()
    document["participants"] = ["workload", "collector", "intervention-controller"]
    receipt.update(
        analysisKind="effect",
        resourceUse="diagnostic-only",
        intervention={"scenario": "persistence-crash"},
        resources=None,
    )
    assert srv5_terminal._measurement_barrier_blockers(
        document, workload=workload, resources=None, receipt=receipt,
        queue_proof=queue, duration_seconds=60, where="planted",
    ) == []

    document["participants"].insert(1, "performance-probe")
    blockers = srv5_terminal._measurement_barrier_blockers(
        document, workload=workload, resources=None, receipt=receipt,
        queue_proof=queue, duration_seconds=60, where="planted",
    )
    assert any("participant set differs" in item for item in blockers)


def effect_intervention_inputs():
    epoch = datetime(2026, 8, 29, tzinfo=timezone.utc)
    project = "obst-effect-proof"
    posture = "full"
    barrier_id = "barrier-" + "d" * 32
    images = runtime_images(project)
    runtime_target = images["services"]["persistence"]
    target_image = {
        key: runtime_target[key] for key in (
            "containerId", "declaredImage", "containerImageId", "imageInspectId",
            "repoDigests",
        )
    }
    configuration = {
        "fault": "persistence-crash",
        "faultAtSeconds": 240,
        "outageSeconds": 30,
        "measurementSeconds": 600,
        "composeProject": project,
    }
    barrier = {
        "schemaVersion": 2,
        "barrierId": barrier_id,
        "createdAt": (epoch - timedelta(seconds=15)).isoformat(),
        "barrierAt": epoch.isoformat(),
        "barrierAtEpoch": epoch.timestamp(),
        "barrierMonotonic": 500.0,
        "measurementSeconds": 600,
        "participants": ["workload", "collector", "intervention-controller"],
        "collectorAcknowledgement": None,
    }

    def at(offset: float) -> str:
        return (epoch + timedelta(seconds=offset)).isoformat()

    def state(*, running: bool, status: str) -> dict:
        return {
            "exists": True, "running": running, "paused": False,
            "status": status, "returnCode": 0,
        }

    onset_vector = srv5_terminal._compose_service_action(
        project, posture, "stop", "persistence")
    recovery_vector = srv5_terminal._compose_service_action(
        project, posture, "start", "persistence")
    onset_result = {
        "command": onset_vector, "returnCode": 0, "stdout": "", "stderr": "",
    }
    recovery_result = {
        "command": recovery_vector, "returnCode": 0, "stdout": "", "stderr": "",
    }
    onset = 240.2
    midpoint = 255.2
    offset = 270.2
    readiness = 271.0
    intervention = {
        "schemaVersion": 3,
        "scenario": "persistence-crash",
        "service": "persistence",
        "independentOfKieker": True,
        "intervalLabel": "intervention-exposure",
        "functionalOutage": None,
        "measurementBarrier": {
            "id": barrier_id,
            "wall": epoch.isoformat(),
            "scheduledOnsetSeconds": 240,
            "scheduledOnsetWall": at(240),
        },
        "requestedHoldSeconds": 30,
        "targetContainerId": runtime_target["containerId"],
        "targetImage": target_image,
        "preState": state(running=True, status="running"),
        "commandVector": onset_vector,
        "commandResult": onset_result,
        "actualOnsetWall": at(onset),
        "actualOnsetMonotonicOffsetSeconds": onset,
        "actualOffsetWall": at(offset),
        "actualOffsetMonotonicOffsetSeconds": offset,
        "duringStateSamples": [
            {
                "phase": phase,
                "observedAtWall": at(observed),
                "observedAtMonotonicOffsetSeconds": observed,
                "state": state(running=False, status="exited"),
            }
            for phase, observed in (
                ("manifested", onset), ("hold-midpoint", midpoint),
                ("hold-end", offset),
            )
        ],
        "recoveryAction": {
            "commandVector": recovery_vector,
            "commandResult": recovery_result,
        },
        "sameTargetIdentity": True,
        "readiness": {
            "predicate": "all-five-application-services-report-OK",
            "observedAtWall": at(readiness),
            "observedAtMonotonicOffsetSeconds": readiness,
            "successful": True,
        },
        "postState": state(running=True, status="running"),
        "interventionThreadJoined": True,
        "laterInterventionMutationObserved": False,
        "manifested": True,
        "recovered": True,
        "outageHeld": True,
        "successful": True,
        "error": None,
        "operational": {
            "controllerStartedAt": at(-10),
            "controllerEndedAt": at(readiness),
            "commandResults": [onset_result, recovery_result],
            "actualHoldSeconds": offset - onset,
            "continuousTargetStateProven": False,
        },
    }
    return intervention, configuration, barrier, images, posture


def shift_intervention_observation(intervention: dict, barrier: dict, onset: float) -> None:
    """Move the retained manifestation/recovery observations as one interval."""

    old_onset = intervention["actualOnsetMonotonicOffsetSeconds"]
    delta = onset - old_onset
    barrier_wall = datetime.fromisoformat(barrier["barrierAt"])

    def wall(offset: float) -> str:
        return (barrier_wall + timedelta(seconds=offset)).isoformat()

    intervention["actualOnsetMonotonicOffsetSeconds"] += delta
    intervention["actualOnsetWall"] = wall(
        intervention["actualOnsetMonotonicOffsetSeconds"])
    intervention["actualOffsetMonotonicOffsetSeconds"] += delta
    intervention["actualOffsetWall"] = wall(
        intervention["actualOffsetMonotonicOffsetSeconds"])
    for sample in intervention["duringStateSamples"]:
        sample["observedAtMonotonicOffsetSeconds"] += delta
        sample["observedAtWall"] = wall(
            sample["observedAtMonotonicOffsetSeconds"])
    readiness = intervention["readiness"]
    readiness["observedAtMonotonicOffsetSeconds"] += delta
    readiness["observedAtWall"] = wall(
        readiness["observedAtMonotonicOffsetSeconds"])
    intervention["operational"]["controllerEndedAt"] = readiness["observedAtWall"]


def test_effect_intervention_sidecar_replays_against_barrier_and_runtime_identity():
    intervention, configuration, barrier, images, posture = effect_intervention_inputs()
    assert srv5_terminal._intervention_artifact_blockers(
        intervention,
        receipt_intervention=json.loads(json.dumps(intervention)),
        configuration=configuration,
        barrier=barrier,
        runtime_images=images,
        posture=posture,
        where="planted",
    ) == []


def test_observed_eleven_second_persistence_manifestation_lag_is_admissible():
    intervention, configuration, barrier, images, posture = effect_intervention_inputs()
    # canddiag-effect-20260829-1854 observed the stopped state 11.009 s after
    # schedule.  Docker's graceful stop explains that observation; the artifact
    # does not independently retain when the stop command was issued.
    shift_intervention_observation(intervention, barrier, 251.0091716311872)
    assert srv5_terminal._intervention_artifact_blockers(
        intervention,
        receipt_intervention=json.loads(json.dumps(intervention)),
        configuration=configuration,
        barrier=barrier,
        runtime_images=images,
        posture=posture,
        where="observed-persistence-smoke",
    ) == []


def test_auth_freeze_paused_state_remains_supported_by_shared_replay():
    intervention, configuration, barrier, images, posture = effect_intervention_inputs()
    configuration["fault"] = "auth-freeze"
    runtime_target = images["services"]["auth"]
    intervention.update(
        scenario="auth-freeze",
        service="auth",
        targetContainerId=runtime_target["containerId"],
        targetImage={
            key: runtime_target[key] for key in (
                "containerId", "declaredImage", "containerImageId", "imageInspectId",
                "repoDigests",
            )
        },
    )
    onset = srv5_terminal._compose_service_action(
        configuration["composeProject"], posture, "pause", "auth")
    recovery = srv5_terminal._compose_service_action(
        configuration["composeProject"], posture, "unpause", "auth")
    onset_result = {"command": onset, "returnCode": 0, "stdout": "", "stderr": ""}
    recovery_result = {
        "command": recovery, "returnCode": 0, "stdout": "", "stderr": "",
    }
    intervention["commandVector"] = onset
    intervention["commandResult"] = onset_result
    intervention["recoveryAction"] = {
        "commandVector": recovery, "commandResult": recovery_result,
    }
    intervention["operational"]["commandResults"] = [onset_result, recovery_result]
    for sample in intervention["duringStateSamples"]:
        sample["state"].update(running=True, paused=True, status="paused")
    assert srv5_terminal._intervention_artifact_blockers(
        intervention,
        receipt_intervention=json.loads(json.dumps(intervention)),
        configuration=configuration,
        barrier=barrier,
        runtime_images=images,
        posture=posture,
        where="planted-auth",
    ) == []
    shift_intervention_observation(intervention, barrier, 251.0)
    blockers = srv5_terminal._intervention_artifact_blockers(
        intervention,
        receipt_intervention=json.loads(json.dumps(intervention)),
        configuration=configuration,
        barrier=barrier,
        runtime_images=images,
        posture=posture,
        where="planted-auth-late",
    )
    assert any("scenario-specific lag bound" in item for item in blockers)


@pytest.mark.parametrize(
    "defect",
    [
        "receipt-mismatch", "extra-field", "wrong-barrier", "late-onset",
        "wrong-hold", "wrong-target-id", "wrong-target-image", "bad-prestate",
        "late-runtime-image", "missing-sample", "bad-during-state", "shifted-midpoint",
        "boolean-command-return", "boolean-state-return", "wrong-recovery-command",
        "failed-recovery", "bad-poststate", "failed-readiness", "unjoined-thread",
        "wrong-operational-results", "continuous-overclaim", "nonfinite-offset",
    ],
)
def test_effect_intervention_replay_watches_planted_defects(defect: str):
    intervention, configuration, barrier, images, posture = effect_intervention_inputs()
    receipt_intervention = json.loads(json.dumps(intervention))
    if defect == "receipt-mismatch":
        receipt_intervention["manifested"] = False
    elif defect == "extra-field":
        intervention["unreviewed"] = True
    elif defect == "wrong-barrier":
        intervention["measurementBarrier"]["id"] = "barrier-" + "e" * 32
    elif defect == "late-onset":
        shift_intervention_observation(intervention, barrier, 256.0)
    elif defect == "wrong-hold":
        intervention["requestedHoldSeconds"] = 29
    elif defect == "wrong-target-id":
        intervention["targetContainerId"] = "f" * 64
    elif defect == "wrong-target-image":
        intervention["targetImage"]["declaredImage"] = "unreviewed/image"
    elif defect == "bad-prestate":
        intervention["preState"]["running"] = False
    elif defect == "late-runtime-image":
        images["capturedAt"] = (
            datetime.fromisoformat(barrier["barrierAt"]) + timedelta(seconds=1)
        ).isoformat()
    elif defect == "missing-sample":
        intervention["duringStateSamples"].pop()
    elif defect == "bad-during-state":
        intervention["duringStateSamples"][1]["state"]["running"] = True
    elif defect == "shifted-midpoint":
        midpoint = intervention["duringStateSamples"][1]
        midpoint["observedAtMonotonicOffsetSeconds"] += 5.0
        midpoint["observedAtWall"] = (
            datetime.fromisoformat(midpoint["observedAtWall"]) + timedelta(seconds=5)
        ).isoformat()
    elif defect == "boolean-command-return":
        intervention["commandResult"]["returnCode"] = False
    elif defect == "boolean-state-return":
        intervention["duringStateSamples"][0]["state"]["returnCode"] = False
    elif defect == "wrong-recovery-command":
        intervention["recoveryAction"]["commandVector"][-2] = "restart"
    elif defect == "failed-recovery":
        intervention["recoveryAction"]["commandResult"]["returnCode"] = 1
    elif defect == "bad-poststate":
        intervention["postState"]["running"] = False
    elif defect == "failed-readiness":
        intervention["readiness"]["successful"] = False
    elif defect == "unjoined-thread":
        intervention["interventionThreadJoined"] = False
    elif defect == "wrong-operational-results":
        intervention["operational"]["commandResults"].reverse()
    elif defect == "continuous-overclaim":
        intervention["operational"]["continuousTargetStateProven"] = True
    else:
        intervention["actualOffsetMonotonicOffsetSeconds"] = float("nan")
    if defect != "receipt-mismatch":
        # Re-forge the receipt projection too: each mutation must be caught by
        # semantic replay, not merely by the sidecar/receipt equality check.
        receipt_intervention = json.loads(json.dumps(intervention))
    blockers = srv5_terminal._intervention_artifact_blockers(
        intervention,
        receipt_intervention=receipt_intervention,
        configuration=configuration,
        barrier=barrier,
        runtime_images=images,
        posture=posture,
        where="planted",
    )
    assert blockers, defect


def test_effect_run_blockers_require_the_retained_intervention_sidecar(tmp_path: Path):
    run_id = "b01-full"
    run = tmp_path / run_id
    run.mkdir()
    write(run / "receipt.json", {
        "runId": run_id,
        "posture": "full",
        "analysisKind": "effect",
        "resourceUse": "diagnostic-only",
        "resources": None,
        "intervention": {"scenario": "persistence-crash", "successful": True},
        "source": {},
        "canonicality": {"label": "smoke-validation", "blockers": []},
        "window": {"warmupSeconds": 120, "measurementSeconds": 600},
        "workload": {"concurrency": 8},
    })
    configuration = {
        "composeProject": "obst-effect-proof",
        "frameworkCommit": "a" * 40,
        "sutReferenceCommit": "b" * 40,
        "selectionId": "fault-qualification",
        "selectionSourceSha256": "c" * 64,
        "activationManifestSha256": "d" * 64,
        "descriptorId": "effect-proof",
        "descriptorSha256": "e" * 64,
        "evidenceLabel": "smoke-validation",
        "warmupSeconds": 120,
        "measurementSeconds": 600,
        "journeysPerSecond": 0.15,
        "concurrency": 8,
        "fault": "persistence-crash",
        "faultAtSeconds": 240,
        "outageSeconds": 30,
    }

    class PassValidator:
        @staticmethod
        def validate(_value):
            return {"verdict": "pass", "blockers": []}

    blockers = srv5_terminal._run_blockers(
        tmp_path, run_id, "full", configuration,
        PassValidator, PassValidator, object(), object(), object(),
    )
    assert any("intervention artifact unreadable" in item for item in blockers)


def test_no_fault_cost_run_rejects_a_stray_intervention_sidecar(tmp_path: Path):
    run_id = "b01-full"
    run = tmp_path / run_id
    run.mkdir()
    write(run / "receipt.json", {
        "runId": run_id,
        "posture": "full",
        "analysisKind": "cost",
        "resourceUse": "cost-proxy",
        "resources": None,
        "intervention": None,
        "source": {},
        "canonicality": {"label": "smoke-validation", "blockers": []},
        "window": {"warmupSeconds": 120, "measurementSeconds": 60},
        "workload": {"concurrency": 8},
    })
    write(run / "intervention.json", {"scenario": "persistence-crash"})
    configuration = {
        "composeProject": "obst-cost-proof",
        "frameworkCommit": "a" * 40,
        "sutReferenceCommit": "b" * 40,
        "selectionId": "auth",
        "selectionSourceSha256": "c" * 64,
        "activationManifestSha256": "d" * 64,
        "descriptorId": "cost-proof",
        "descriptorSha256": "e" * 64,
        "evidenceLabel": "smoke-validation",
        "warmupSeconds": 120,
        "measurementSeconds": 60,
        "journeysPerSecond": 0.15,
        "concurrency": 8,
        "fault": "none",
        "faultAtSeconds": None,
        "outageSeconds": None,
    }

    class PassValidator:
        @staticmethod
        def validate(_value):
            return {"verdict": "pass", "blockers": []}

    blockers = srv5_terminal._run_blockers(
        tmp_path, run_id, "full", configuration,
        PassValidator, PassValidator, object(), object(), object(),
    )
    assert any("forbidden intervention artifact" in item for item in blockers)


def test_effect_child_process_contract_has_no_performance_probe():
    collector = child_process("collector")
    retained = {"collector": collector}
    projected = {"workload": {"returnCode": 0}, "collector": collector}
    assert srv5_terminal._child_process_blockers(
        retained, projected, "planted", expect_performance_probe=False,
    ) == []
    retained["performanceProbe"] = child_process("performanceProbe")
    blockers = srv5_terminal._child_process_blockers(
        retained, projected, "planted", expect_performance_probe=False,
    )
    assert any("artifact fields differ" in item for item in blockers)


@pytest.mark.parametrize(
    "effect_contract,failed,timed_out,expected",
    [
        (False, 0, 0, 0),
        (False, 1, 0, 2),
        (False, 0, 1, 2),
        (True, 0, 0, 0),
        (True, 1, 0, 2),
        (True, 0, 1, 2),
    ],
)
def test_effect_workload_return_code_replays_retained_outcomes(
    effect_contract: bool, failed: int, timed_out: int, expected: int,
):
    workload = {"failed": failed, "timedOut": timed_out}
    expected_rc = srv5_terminal._expected_fixed_load_return_code(
        workload, effect_contract=effect_contract)
    assert expected_rc == expected
    collector = child_process("collector")
    retained = {"collector": collector}
    projected = {
        "workload": {"returnCode": expected},
        "collector": collector,
    }
    assert srv5_terminal._child_process_blockers(
        retained,
        projected,
        "planted-workload",
        expect_performance_probe=False,
        expected_workload_return_code=expected_rc,
    ) == []
    projected["workload"]["returnCode"] = 0 if expected == 2 else 2
    blockers = srv5_terminal._child_process_blockers(
        retained,
        projected,
        "planted-workload",
        expect_performance_probe=False,
        expected_workload_return_code=expected_rc,
    )
    assert any("receipt process fields differ" in item for item in blockers)


def test_no_fault_cost_run_cannot_hide_failed_workload_behind_matching_rc2(
    tmp_path: Path,
):
    root, descriptor_path, status, remote = campaign(tmp_path)
    run = root / "b01-full"
    workload_path = run / "workload.json"
    receipt_path = run / "receipt.json"
    workload = json.loads(workload_path.read_text())
    workload.update(completed=8, failed=1, failures=["planted no-fault failure"])
    workload["latencyMs"]["count"] = 8
    write(workload_path, workload)
    receipt = json.loads(receipt_path.read_text())
    receipt["workload"].update(completed=8, failed=1)
    receipt["latencyMs"] = workload["latencyMs"]
    receipt["processes"]["workload"]["returnCode"] = 2
    write(receipt_path, receipt)
    reseal(root)

    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any(
        "no-fault" in blocker and "unsuccessful" in blocker
        for blocker in report["blockers"]
    )
    assert not any(
        "receipt process fields differ" in blocker
        for blocker in report["blockers"]
    )


def effect_telemetry_inputs():
    events = [event("auth", "sig-a"), event("webui", "sig-b")]
    stats = {
        "messages": 3,
        "containers_ok": 3,
        "containers_bad": 0,
        "records_ok": len(events),
        "records_bad": 1,
        "record_parse_success_ratio": 2 / 3,
        "container_parse_success_ratio": 1.0,
        "acknowledgement_mode": "manual",
        "runtime_host_map_loaded": True,
        "correlation": collector_correlation(events),
    }
    telemetry = {"parseFailures": 1}
    return events, telemetry, stats


def test_full_effect_telemetry_allows_one_explicit_bounded_parse_loss():
    events, telemetry, stats = effect_telemetry_inputs()
    assert srv5_terminal._collector_telemetry_blockers(
        events,
        telemetry,
        stats,
        posture="full",
        effect_contract=True,
        where="observed-effect-smoke",
    ) == []


@pytest.mark.parametrize(
    "defect,expected",
    [
        ("two-bad-records", "at most one"),
        ("bad-container", "container parse failures"),
        ("hidden-parse-count", "does not surface"),
        ("wrong-records-ok", "retained event count"),
        ("messages-containers-differ", "messages and containers_ok differ"),
        ("gap-exceeds-bad-records", "bounded unexplained"),
    ],
)
def test_effect_telemetry_replay_watches_planted_defects(defect: str, expected: str):
    events, telemetry, stats = effect_telemetry_inputs()
    if defect == "two-bad-records":
        stats["records_bad"] = 2
        telemetry["parseFailures"] = 2
    elif defect == "bad-container":
        stats["containers_bad"] = 1
    elif defect == "hidden-parse-count":
        telemetry["parseFailures"] = 0
    elif defect == "wrong-records-ok":
        stats["records_ok"] = len(events) + 1
    elif defect == "messages-containers-differ":
        stats["containers_ok"] = 2
    else:
        stats["messages"] = 4
        stats["containers_ok"] = 4
    blockers = srv5_terminal._collector_telemetry_blockers(
        events,
        telemetry,
        stats,
        posture="full",
        effect_contract=True,
        where="planted-effect-smoke",
    )
    assert any(expected in item for item in blockers), blockers


def _tolerable_correlation_inputs():
    """An effect cell whose only correlation errors are the fault's signature."""
    events, telemetry, stats = effect_telemetry_inputs()
    correlation = stats["correlation"]
    correlation["eventsWithCorrelationErrors"] = 3
    correlation["traceCompleteness"]["tracesWithEoiGaps"] = 2
    correlation["traceCompleteness"]["missingEoiCount"] = 5
    return events, telemetry, stats


def test_effect_correlation_errors_inside_the_exposure_window_are_tolerated():
    """F-ADH-080: this validator must honour the tolerance the others honour."""
    events, telemetry, stats = _tolerable_correlation_inputs()
    blockers = srv5_terminal._collector_telemetry_blockers(
        events, telemetry, stats,
        posture="full", effect_contract=True, where="tolerated-effect",
        exposure_tolerance={
            "toleratedCorrelationErrorEvents": 3,
            "residualCorrelationErrorEvents": 0,
            "residualEoiGapTraces": 0,
            "residualMissingEoiCount": 0,
        },
    )
    assert not any("correlation errors are nonzero" in item for item in blockers), blockers
    assert not any("EOI completeness gaps" in item for item in blockers), blockers


def test_an_absent_exposure_tolerance_still_means_zero_tolerance():
    events, telemetry, stats = _tolerable_correlation_inputs()
    blockers = srv5_terminal._collector_telemetry_blockers(
        events, telemetry, stats,
        posture="full", effect_contract=True, where="untolerated-effect",
    )
    assert any("correlation errors are nonzero" in item for item in blockers), blockers
    assert any("EOI completeness gaps" in item for item in blockers), blockers


def test_a_tolerance_may_not_excuse_more_than_the_collector_observed():
    events, telemetry, stats = _tolerable_correlation_inputs()
    blockers = srv5_terminal._collector_telemetry_blockers(
        events, telemetry, stats,
        posture="full", effect_contract=True, where="overreaching-effect",
        exposure_tolerance={
            "toleratedCorrelationErrorEvents": 4,
            "residualCorrelationErrorEvents": 0,
            "residualEoiGapTraces": 0,
            "residualMissingEoiCount": 0,
        },
    )
    assert any("exceeds the observed collector counters" in item for item in blockers), blockers


def test_cost_evidence_may_not_carry_a_nonzero_exposure_tolerance():
    events, telemetry, stats = effect_telemetry_inputs()
    blockers = srv5_terminal._collector_telemetry_blockers(
        events, telemetry, stats,
        posture="full", effect_contract=False, where="tolerant-cost",
        exposure_tolerance={
            "toleratedCorrelationErrorEvents": 1,
            "residualCorrelationErrorEvents": 0,
            "residualEoiGapTraces": 0,
            "residualMissingEoiCount": 0,
        },
    )
    assert any("nonzero exposure tolerance" in item for item in blockers), blockers


def test_a_malformed_exposure_tolerance_fails_closed():
    events, telemetry, stats = _tolerable_correlation_inputs()
    blockers = srv5_terminal._collector_telemetry_blockers(
        events, telemetry, stats,
        posture="full", effect_contract=True, where="malformed-effect",
        exposure_tolerance={"toleratedCorrelationErrorEvents": "3"},
    )
    assert any("exposure tolerance counters differ" in item for item in blockers), blockers


def test_cost_telemetry_retains_zero_parse_failure_rule():
    events, telemetry, stats = effect_telemetry_inputs()
    blockers = srv5_terminal._collector_telemetry_blockers(
        events,
        telemetry,
        stats,
        posture="full",
        effect_contract=False,
        where="planted-cost",
    )
    assert any("exactly zero" in item for item in blockers)


@pytest.mark.parametrize(
    "defect,expected",
    [
        ("automatic-ack", "acknowledgement mode was not manual"),
        ("correlation-error", "parent correlation errors"),
        ("duplicate-warning", "correlation/replay warnings"),
        ("attribution-error", "service-attribution errors"),
        ("eoi-gap", "EOI completeness gaps"),
        ("flattering-summary", "differs from retained events"),
    ],
)
def test_terminal_replays_native_correlation_defects(defect: str, expected: str):
    events, telemetry, stats = effect_telemetry_inputs()
    correlation = stats["correlation"]
    if defect == "automatic-ack":
        stats["acknowledgement_mode"] = "automatic"
    elif defect == "correlation-error":
        events[0]["correlation_errors"] = ["missing-parent-at-depth-0"]
        correlation["eventsWithCorrelationErrors"] = 1
    elif defect == "duplicate-warning":
        events[0]["correlation_warnings"] = ["duplicate-native-identity-observation"]
        correlation["eventsWithCorrelationWarnings"] = 1
    elif defect == "attribution-error":
        events[0]["service_attribution_status"] = "runtime-host-signature-conflict"
        events[0]["service_attribution_errors"] = ["runtime-host-signature-conflict"]
        correlation["serviceAttribution"] = {
            "runtime-host-and-signature-agree": 1,
            "runtime-host-signature-conflict": 1,
        }
        correlation["eventsWithServiceAttributionErrors"] = 1
    elif defect == "eoi-gap":
        events[1]["trace_id"] = events[0]["trace_id"]
        events[1]["eoi"] = 2
        events[1]["parent_resolution"] = "resolved"
        correlation["parentResolution"] = {"resolved": 1, "root": 1}
        correlation["traceCompleteness"] = {
            "traces": 1,
            "tracesWithEoiGaps": 1,
            "missingEoiCount": 1,
            "tracesNotStartingAtZero": 0,
        }
    else:
        events[0]["correlation_errors"] = ["missing-parent-at-depth-0"]
    blockers = srv5_terminal._collector_telemetry_blockers(
        events,
        telemetry,
        stats,
        posture="full",
        effect_contract=True,
        where="planted-native-correlation",
    )
    assert any(expected in blocker for blocker in blockers), blockers


@pytest.mark.parametrize("defect", [
    "reversed", "late", "too-early", "pre-query-style", "queue-mismatch",
])
def test_v2_collector_query_timing_watches_planted_defects(defect: str):
    document, workload, resources, receipt, queue = v2_measurement_barrier_inputs()
    acknowledgement = document["collectorAcknowledgement"]
    epoch = document["barrierAtEpoch"]
    if defect == "reversed":
        acknowledgement["queryCompletedAtWall"] = datetime.fromtimestamp(
            epoch - 0.1, timezone.utc).isoformat()
        acknowledgement["queryCompletedMonotonicOffsetSeconds"] = -0.1
    elif defect == "late":
        acknowledgement["queryCompletedAtWall"] = datetime.fromtimestamp(
            epoch + 5.001, timezone.utc).isoformat()
        acknowledgement["queryCompletedMonotonicOffsetSeconds"] = 5.001
    elif defect == "too-early":
        acknowledgement["queryStartedAtWall"] = datetime.fromtimestamp(
            epoch - 1.001, timezone.utc).isoformat()
        acknowledgement["queryStartedMonotonicOffsetSeconds"] = -1.001
    elif defect == "pre-query-style":
        document["collectorAcknowledgement"] = {
            "observedAt": datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
            "observedMonotonicOffsetSeconds": 0.0,
            "queueState": acknowledgement["queueState"],
        }
    else:
        queue["measurement"]["consumerAtStart"] = queue_state("e" * 64, 1, 1)

    blockers = srv5_terminal._measurement_barrier_blockers(
        document, workload=workload, resources=resources, receipt=receipt,
        queue_proof=queue, duration_seconds=60, where="planted",
    )
    expected = (
        "differs from queue proof" if defect == "queue-mismatch"
        else "fields differ" if defect == "pre-query-style"
        else "query timing is invalid"
    )
    assert any(expected in item for item in blockers), blockers


def test_valid_campaign_and_non_circular_manifest_pass(tmp_path: Path):
    parts = campaign(tmp_path)
    report = validate(parts)
    assert report["verdict"] == "pass", report["blockers"]
    manifest = json.loads((parts[0] / srv5_terminal.MANIFEST_NAME).read_text())
    assert srv5_terminal.MANIFEST_NAME not in {row["path"] for row in manifest["files"]}
    assert srv5_terminal.verify_manifest(parts[0])["verdict"] == "pass"


def test_manifest_excludes_derived_terminal_report(tmp_path: Path):
    root, _, _, _ = campaign(tmp_path)
    write(root / srv5_terminal.TERMINAL_REPORT_NAME, {"verdict": "pass"})
    reseal(root)
    manifest = json.loads((root / srv5_terminal.MANIFEST_NAME).read_text())
    paths = {row["path"] for row in manifest["files"]}
    assert srv5_terminal.MANIFEST_NAME not in paths
    assert srv5_terminal.TERMINAL_REPORT_NAME not in paths
    write(root / srv5_terminal.TERMINAL_REPORT_NAME, {"verdict": "blocked"})
    assert srv5_terminal.verify_manifest(root)["verdict"] == "pass"


def test_existing_manifest_cannot_be_overwritten_to_bless_a_changed_artifact(
    tmp_path: Path,
):
    root, _, _, _ = campaign(tmp_path)
    original = (root / srv5_terminal.MANIFEST_NAME).read_bytes()
    (root / "schedule.json").write_text("{}\n")

    with pytest.raises(FileExistsError, match="already exists"):
        srv5_terminal.write_manifest(root)

    assert (root / srv5_terminal.MANIFEST_NAME).read_bytes() == original
    report = srv5_terminal.verify_manifest(root)
    assert report["verdict"] == "blocked"
    assert any("digest/size mismatch" in blocker for blocker in report["blockers"])


def test_external_manifest_anchor_rejects_delete_mutate_and_reseal(tmp_path: Path):
    parts = campaign(tmp_path)
    root = parts[0]
    original_anchor = srv5_terminal.verify_manifest(root)["manifestSha256"]
    (root / srv5_terminal.MANIFEST_NAME).unlink()
    with (root / "b01-full" / "collector.stderr").open("a") as handle:
        handle.write("PLANTED-POST-SEAL\n")
    srv5_terminal.write_manifest(root)
    assert srv5_terminal.verify_manifest(root)["verdict"] == "pass"
    report = srv5_terminal.validate_campaign(
        *parts, expected_manifest_sha256=original_anchor, require_fresh_remote=False)
    assert report["verdict"] == "blocked"
    assert any("external manifest anchor" in blocker for blocker in report["blockers"])


def test_retained_revalidation_does_not_apply_wall_clock_freshness(
    tmp_path: Path, monkeypatch
):
    parts = campaign(tmp_path)
    anchor = srv5_terminal.verify_manifest(parts[0])["manifestSha256"]
    monkeypatch.setattr(srv5_terminal, "MAX_REMOTE_AGE_SECONDS", -1)
    assert srv5_terminal.validate_campaign(*parts)["verdict"] == "blocked"
    report = srv5_terminal.validate_campaign(
        *parts, expected_manifest_sha256=anchor, require_fresh_remote=False)
    assert report["verdict"] == "pass", report["blockers"]


def test_deadline_admission_and_owned_cleanup_cross_terminal_validation(tmp_path: Path):
    parts = campaign(tmp_path, deadline=True)
    report = validate(parts)
    assert report["verdict"] == "pass", report["blockers"]


@pytest.mark.parametrize("offset_microseconds,expected", [(-1, "blocked"), (1, "pass")])
def test_deadline_lease_order_is_strict_at_subsecond_precision(
    tmp_path: Path, offset_microseconds: int, expected: str
):
    root, descriptor_path, status, remote = campaign(tmp_path, deadline=True)
    lease = json.loads((root / "execution-lease.json").read_text())
    cleanup = json.loads((root / "deadline-cleanup.json").read_text())
    completed = datetime.fromisoformat(cleanup["authorization"]["completedAt"])
    lease["release"]["requestedAt"] = (
        completed + timedelta(microseconds=offset_microseconds)
    ).isoformat()
    write(root / "execution-lease.json", lease)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == expected, report["blockers"]


@pytest.mark.parametrize("defect", [
    "admission-digest",
    "admission-replay",
    "cleanup-missing",
    "cleanup-residue",
    "cleanup-runner-failed",
    "cleanup-after-finalizer-window",
    "cleanup-fallback-decision",
    "cleanup-lease-order",
])
def test_deadline_contract_watches_planted_defects(tmp_path: Path, defect: str):
    root, descriptor_path, status, remote = campaign(tmp_path, deadline=True)
    if defect == "admission-digest":
        owner = json.loads((root / "harness-owner.json").read_text())
        owner["runtimeAdmissionSha256"] = "0" * 64
        write(root / "harness-owner.json", owner)
    elif defect == "admission-replay":
        admission = json.loads((root / "runtime-admission.json").read_text())
        admission["runCount"] = 2
        write(root / "runtime-admission.json", admission)
        owner = json.loads((root / "harness-owner.json").read_text())
        owner["runtimeAdmissionSha256"] = srv5_terminal._sha256_bytes(
            (root / "runtime-admission.json").read_bytes())
        write(root / "harness-owner.json", owner)
    elif defect == "cleanup-missing":
        (root / "deadline-cleanup.json").unlink()
    elif defect == "cleanup-lease-order":
        lease = json.loads((root / "execution-lease.json").read_text())
        cleanup = json.loads((root / "deadline-cleanup.json").read_text())
        completed = datetime.fromisoformat(cleanup["authorization"]["completedAt"])
        lease["release"]["requestedAt"] = (completed - timedelta(seconds=1)).isoformat()
        write(root / "execution-lease.json", lease)
    else:
        cleanup = json.loads((root / "deadline-cleanup.json").read_text())
        if defect == "cleanup-residue":
            cleanup["verification"]["final"]["remaining"]["containers"] = 1
            cleanup["verification"]["final"]["queries"]["containers"]["identifiers"]["count"] = 1
        elif defect == "cleanup-runner-failed":
            cleanup["processGroup"]["runnerReturnCode"] = 7
        elif defect == "cleanup-after-finalizer-window":
            deadline_epoch = cleanup["trigger"]["authorizationDeadlineEpoch"]
            completed = datetime.fromtimestamp(
                deadline_epoch - srv5_terminal.DEADLINE_LEASE_FINALIZER_SECONDS + 1,
                timezone.utc,
            )
            cleanup["authorization"]["completedAt"] = completed.isoformat()
            cleanup["authorization"]["completedAtEpoch"] = completed.timestamp()
        else:
            cleanup["verification"]["fallback"]["required"] = True
        write(root / "deadline-cleanup.json", cleanup)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("admission" in item or "cleanup" in item for item in report["blockers"])


@pytest.mark.parametrize("field,value", [("active", True), ("exitCode", ""), ("receipts", 0), ("expected", 2)])
def test_terminal_status_defects_are_blocked(tmp_path: Path, field: str, value):
    root, descriptor_path, status, remote = campaign(tmp_path)
    status[field] = value
    assert validate((root, descriptor_path, status, remote))["verdict"] == "blocked"


def test_missing_and_duplicate_key_schedules_are_blocked(tmp_path: Path):
    root, descriptor_path, status, remote = campaign(tmp_path)
    (root / "schedule.json").unlink()
    reseal(root)
    assert validate((root, descriptor_path, status, remote))["verdict"] == "blocked"
    (root / "schedule.json").write_text('{"configuration":{},"configuration":{},"runs":[]}')
    reseal(root)
    assert validate((root, descriptor_path, status, remote))["verdict"] == "blocked"


@pytest.mark.parametrize("field,value", [
    ("schemaVersion", 2),
    ("campaign", "other"),
    ("target", "fb14srv6"),
    ("session", "teastore-other"),
    ("composeProject", "obst-other"),
    ("frameworkCommit", "7" * 40),
    ("sutReferenceCommit", "8" * 40),
    ("release", "/home/stig/observability-placement-runs/wrong"),
    ("resultRoot", "/home/stig/observability-placement-results/wrong"),
    ("descriptorId", "other"),
    ("descriptorSha256", "9" * 64),
    ("expectedReceipts", 2),
])
def test_harness_owner_defects_are_blocked(tmp_path: Path, field: str, value):
    root, descriptor_path, status, remote = campaign(tmp_path)
    path = root / "harness-owner.json"
    owner = json.loads(path.read_text())
    owner[field] = value
    write(path, owner)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("harness owner" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize("defect", ["missing", "missing-result-root", "extra", "malformed"])
def test_harness_owner_shape_is_fail_closed(tmp_path: Path, defect: str):
    root, descriptor_path, status, remote = campaign(tmp_path)
    path = root / "harness-owner.json"
    if defect == "missing":
        path.unlink()
    elif defect == "missing-result-root":
        owner = json.loads(path.read_text())
        owner.pop("resultRoot")
        write(path, owner)
    elif defect == "extra":
        owner = json.loads(path.read_text())
        owner["trusted"] = True
        write(path, owner)
    else:
        path.write_text("{not-json")
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("harness owner" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize("field,value", [
    ("descriptorId", "other"),
    ("descriptorSha256", "0" * 64),
    ("measurementSeconds", 61),
])
def test_descriptor_binding_defects_are_blocked(tmp_path: Path, field: str, value):
    root, descriptor_path, status, remote = campaign(tmp_path)
    schedule = json.loads((root / "schedule.json").read_text())
    schedule["configuration"][field] = value
    write(root / "schedule.json", schedule)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("descriptor" in blocker for blocker in report["blockers"])


def test_receipt_canonicality_label_is_descriptor_bound(tmp_path: Path):
    root, descriptor_path, status, remote = campaign(tmp_path)
    receipt_path = root / "b01-full" / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["canonicality"]["label"] = "candidate-evidence"
    write(receipt_path, receipt)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("canonicality label" in blocker for blocker in report["blockers"])


def test_receipt_id_and_performance_contract_defects_are_blocked(tmp_path: Path):
    root, descriptor_path, status, remote = campaign(tmp_path)
    run = root / "b01-full"
    receipt = json.loads((run / "receipt.json").read_text())
    receipt["latencyMs"]["count"] = 8
    write(run / "receipt.json", receipt)
    reseal(root)
    assert validate((root, descriptor_path, status, remote))["verdict"] == "blocked"
    (run / "receipt.json").rename(run / "other.json")
    reseal(root)
    assert validate((root, descriptor_path, status, remote))["verdict"] == "blocked"


def test_nested_extra_receipt_is_not_ignored(tmp_path: Path):
    root, descriptor_path, status, remote = campaign(tmp_path)
    write(root / "nested" / "receipt.json", {})
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("receipt IDs differ" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize("posture", ["selected", "full"])
def test_selected_and_full_require_native_kieker_contract(tmp_path: Path, posture: str):
    root, descriptor_path, status, remote = campaign(tmp_path, posture)
    traces_path = root / f"b01-{posture}" / "traces.json"
    traces = json.loads(traces_path.read_text())
    traces[0]["source"] = "invented"
    write(traces_path, traces)
    receipt_path = root / f"b01-{posture}" / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["telemetry"]["bytes"] = traces_path.stat().st_size
    write(receipt_path, receipt)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("native Kieker" in blocker for blocker in report["blockers"])


def test_malformed_descriptor_returns_a_blocked_verdict(tmp_path: Path):
    root, descriptor_path, status, remote = campaign(tmp_path)
    malformed = json.loads(descriptor_path.read_text())
    malformed["design"]["blocks"] = "one"
    malformed["validation"] = [{}]
    write(descriptor_path, malformed)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert report["blockers"]


def test_none_posture_must_be_exactly_empty(tmp_path: Path):
    root, descriptor_path, status, remote = campaign(tmp_path, "none")
    assert validate((root, descriptor_path, status, remote))["verdict"] == "pass"
    run = root / "b01-none"
    write(run / "traces.json", [event("auth", "sig")])
    receipt = json.loads((run / "receipt.json").read_text())
    receipt["telemetry"].update({"records": 1, "bytes": (run / "traces.json").stat().st_size, "uniqueSignatures": 1})
    write(run / "receipt.json", receipt)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("exactly empty" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize("field,value", [("records", 9), ("bytes", 9), ("uniqueSignatures", 9)])
def test_telemetry_denominators_are_recomputed(tmp_path: Path, field: str, value: int):
    root, descriptor_path, status, remote = campaign(tmp_path)
    receipt_path = root / "b01-full" / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["telemetry"][field] = value
    write(receipt_path, receipt)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("count/bytes/signatures" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize("defect", ["workload", "resources", "warmup", "posture"])
def test_retained_raw_run_artifacts_are_replayed(tmp_path: Path, defect: str):
    root, descriptor_path, status, remote = campaign(tmp_path)
    run = root / "b01-full"
    receipt_path = run / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if defect == "workload":
        path = run / "workload.json"
        value = json.loads(path.read_text())
        value["latencyMs"]["p95"] = 999
        write(path, value)
    elif defect == "resources":
        path = run / "resources.json"
        value = json.loads(path.read_text())
        value["applicationMemoryPeakBytes"] = 999
        receipt["resources"]["applicationMemoryPeakBytes"] = 999
        write(path, value)
        write(receipt_path, receipt)
    elif defect == "warmup":
        path = run / "warmup.json"
        value = json.loads(path.read_text())
        value.update({"completed": 17, "failed": 1, "failures": ["planted"]})
        value["latencyMs"]["count"] = 17
        write(path, value)
    else:
        path = run / "posture-proof.json"
        value = json.loads(path.read_text())
        value["services"]["auth"]["configuration"] = "kieker.monitoring.enabled=false"
        receipt["postureProof"] = value
        write(path, value)
        write(receipt_path, receipt)
    reseal(root)

    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any(
        token in blocker
        for blocker in report["blockers"]
        for token in ("workload artifact", "resources artifact", "warmup artifact", "posture proof")
    )


@pytest.mark.parametrize("defect", ["invalid-sha1", "duplicate-body"])
def test_native_message_body_identity_is_valid_and_reconciled(tmp_path: Path, defect: str):
    root, descriptor_path, status, remote = campaign(tmp_path)
    traces_path = root / "b01-full" / "traces.json"
    events = json.loads(traces_path.read_text())
    events[1]["message_sha1"] = "z" * 40 if defect == "invalid-sha1" else events[0]["message_sha1"]
    write(traces_path, events)
    reseal(root)

    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    expected = "invalid native message_sha1" if defect == "invalid-sha1" else "unique message bodies"
    assert any(expected in blocker for blocker in report["blockers"])


def test_collector_summary_is_replayed_and_must_be_unambiguous(tmp_path: Path):
    root, descriptor_path, status, remote = campaign(tmp_path)
    stderr = root / "b01-full" / "collector.stderr"
    summary = stderr.read_text()
    stderr.write_text(summary + summary)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("collector summary replay failed" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize("defect", ["missing", "semantic", "digest"])
def test_runtime_image_proof_is_required_and_receipt_bound(tmp_path: Path, defect: str):
    root, descriptor_path, status, remote = campaign(tmp_path)
    run = root / "b01-full"
    proof_path = run / "runtime-images.json"
    receipt_path = run / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if defect == "missing":
        proof_path.unlink()
    elif defect == "semantic":
        proof = json.loads(proof_path.read_text())
        proof["services"]["webui"]["imageInspectId"] = "sha256:" + "f" * 64
        write(proof_path, proof)
        receipt["source"]["runtimeImagesSha256"] = srv5_terminal._sha256_bytes(
            proof_path.read_bytes())
        write(receipt_path, receipt)
    else:
        receipt["source"]["runtimeImagesSha256"] = "f" * 64
        write(receipt_path, receipt)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any(
        "runtime image" in blocker or "source/descriptor binding" in blocker
        for blocker in report["blockers"]
    )


def test_self_consistent_unexpected_runtime_repository_is_blocked(tmp_path: Path):
    root, descriptor_path, status, remote = campaign(tmp_path)
    run = root / "b01-full"
    proof_path = run / "runtime-images.json"
    receipt_path = run / "receipt.json"
    proof = json.loads(proof_path.read_text())
    item = proof["services"]["webui"]
    declared = "unexpected/teastore-webui:latest"
    repository_digest = "unexpected/teastore-webui@sha256:" + "1" * 64
    item["declaredImage"] = declared
    item["repoDigests"] = [repository_digest]
    item["queries"]["containerInspect"]["stdout"] = (
        f"{item['containerId']}\t{item['containerImageId']}\t{declared}\t"
        f"{proof['composeProject']}\twebui\n"
    )
    item["queries"]["imageInspect"]["command"][-1] = declared
    item["queries"]["imageInspect"]["stdout"] = (
        f"{item['imageInspectId']}\t{json.dumps([repository_digest])}\n"
    )
    write(proof_path, proof)
    receipt = json.loads(receipt_path.read_text())
    receipt["source"]["runtimeImagesSha256"] = srv5_terminal._sha256_bytes(
        proof_path.read_bytes())
    write(receipt_path, receipt)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any(
        "deployment contract" in blocker or "repository digests are invalid" in blocker
        for blocker in report["blockers"]
    )


@pytest.mark.parametrize("defect", ["missing", "semantic", "digest"])
def test_queue_proof_is_required_replayed_and_receipt_bound(tmp_path: Path, defect: str):
    root, descriptor_path, status, remote = campaign(tmp_path)
    run = root / "b01-full"
    proof_path = run / "queue-proof.json"
    receipt_path = run / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if defect == "missing":
        proof_path.unlink()
    elif defect == "semantic":
        proof = json.loads(proof_path.read_text())
        state = proof["measurement"]["consumerAtStart"]
        state["consumers"] = 0
        state["query"]["stdout"] = "kieker\t0\t0\n"
        write(proof_path, proof)
        digest = srv5_terminal._sha256_bytes(proof_path.read_bytes())
        receipt["queue"]["proofSha256"] = digest
        receipt["source"]["queueProofSha256"] = digest
        write(receipt_path, receipt)
    else:
        receipt["queue"]["proofSha256"] = "f" * 64
        write(receipt_path, receipt)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("queue proof" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize("defect", ["missing", "not-joined"])
def test_child_process_proof_is_required_and_replayed(tmp_path: Path, defect: str):
    root, descriptor_path, status, remote = campaign(tmp_path)
    run = root / "b01-full"
    child_path = run / "child-processes.json"
    receipt_path = run / "receipt.json"
    if defect == "missing":
        child_path.unlink()
    else:
        children = json.loads(child_path.read_text())
        children["collector"]["joined"] = False
        write(child_path, children)
        receipt = json.loads(receipt_path.read_text())
        receipt["processes"]["collector"] = children["collector"]
        receipt["source"]["childProcessesSha256"] = srv5_terminal._sha256_bytes(
            child_path.read_bytes())
        write(receipt_path, receipt)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("child processes" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize("name,planted", [
    ("collector", None),
    ("collector", 0),
    ("performanceProbe", 60),
])
def test_join_watchdog_policy_is_pinned_per_child(
        tmp_path: Path, name: str, planted):
    root, descriptor_path, status, remote = campaign(tmp_path)
    run = root / "b01-full"
    child_path = run / "child-processes.json"
    receipt_path = run / "receipt.json"
    children = json.loads(child_path.read_text())
    children[name]["noProgressTimeoutSeconds"] = planted
    write(child_path, children)
    receipt = json.loads(receipt_path.read_text())
    receipt["processes"][name] = children[name]
    receipt["source"]["childProcessesSha256"] = srv5_terminal._sha256_bytes(
        child_path.read_bytes())
    write(receipt_path, receipt)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("join watchdog policy differs" in blocker
               for blocker in report["blockers"])


def test_all_measured_processes_must_exit_zero(tmp_path: Path):
    root, descriptor_path, status, remote = campaign(tmp_path)
    receipt_path = root / "b01-full" / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["processes"]["performanceProbe"]["returnCode"] = 7
    receipt["canonicality"]["blockers"] = []
    write(receipt_path, receipt)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("receipt differs from retained child proof" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize("artifact", [
    "b01-full/ownership-preflight.json",
    "b01-full/teardown.json",
    "final-hygiene.json",
])
def test_each_owned_resource_proof_is_authoritatively_replayed(tmp_path: Path, artifact: str):
    root, descriptor_path, status, remote = campaign(tmp_path)
    path = root / artifact
    value = json.loads(path.read_text())
    proof = value.get("resourcesBefore") or value.get("projectResources") or value
    proof["queries"]["containers"]["returnCode"] = 1
    write(path, value)
    reseal(root)
    assert validate((root, descriptor_path, status, remote))["verdict"] == "blocked"


def test_down_command_and_receipt_teardown_must_match_retained_proof(tmp_path: Path):
    root, descriptor_path, status, remote = campaign(tmp_path)
    path = root / "b01-full" / "down-command.json"
    value = json.loads(path.read_text())
    value["command"].remove("-v")
    write(path, value)
    receipt_path = root / "b01-full" / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["teardown"]["downCommand"] = value
    write(receipt_path, receipt)
    reseal(root)
    assert validate((root, descriptor_path, status, remote))["verdict"] == "blocked"


def test_remote_proof_must_be_fresh_empty_and_bound(tmp_path: Path):
    root, descriptor_path, status, remote = campaign(tmp_path)
    remote["capturedAt"] = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    remote["projectResources"]["containers"] = ["survivor"]
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("stale" in blocker for blocker in report["blockers"])
    assert any(
        "current-project resources" in blocker or "authoritative replay failed" in blocker
        for blocker in report["blockers"]
    )


@pytest.mark.parametrize("defect", ["command-dialect", "stable-relation", "classification"])
def test_comprehensive_inventory_gate_detects_planted_defects(tmp_path: Path, defect: str):
    root, descriptor_path, status, remote = campaign(tmp_path)
    if defect == "command-dialect":
        remote["queryProofs"]["project.containers"]["command"].remove("--no-trunc")
    elif defect == "stable-relation":
        remote["stableState"]["timeSynchronized"] = False
        remote["stateFingerprint"] = srv5_terminal._sha256_bytes(json.dumps(
            remote["stableState"], sort_keys=True, separators=(",", ":")).encode())
    else:
        remote["classification"]["blocking"] = [{
            "resourceType": "volume", "identity": "planted",
            "classification": "unknown", "reason": "planted unknown ownership",
        }]
        remote["stableState"]["classification"] = remote["classification"]
        remote["stateFingerprint"] = srv5_terminal._sha256_bytes(json.dumps(
            remote["stableState"], sort_keys=True, separators=(",", ":")).encode())
        remote["verdict"] = "blocked"
        remote["blockers"] = ["host resource classification contains blocking resources"]
    write(root / "remote-final-state.json", remote)
    reseal(root)

    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    expected = {
        "command-dialect": "query command/result differs",
        "stable-relation": "stable state differs",
        "classification": "blocking classifications do not replay",
    }[defect]
    assert any(expected in item for item in report["blockers"]), report["blockers"]


@pytest.mark.parametrize("name,collection,identity_key,prefix", [
    ("containers.inspect", "containers", "id", ["docker", "inspect"]),
    ("networks.inspect", "networks", "id", ["docker", "network", "inspect"]),
    ("volumes.inspect", "volumes", "name", ["docker", "volume", "inspect"]),
])
def test_inventory_inspect_commands_accept_exact_identity_permutations(
    name: str, collection: str, identity_key: str, prefix: list[str],
):
    remote = comprehensive_inventory("permutation", datetime.now(timezone.utc))
    remote["docker"][collection] = [
        {identity_key: "identity-a"},
        {identity_key: "identity-b"},
    ]
    remote["queryProofs"][name]["command"] = [
        *prefix, "identity-b", "identity-a",
    ]

    blockers = srv5_terminal._inventory_query_blockers(
        remote, remote["composeProject"], remote["session"])
    assert not any(name in blocker for blocker in blockers), blockers


@pytest.mark.parametrize("name,collection,identity_key,prefix", [
    ("containers.inspect", "containers", "id", ["docker", "inspect"]),
    ("networks.inspect", "networks", "id", ["docker", "network", "inspect"]),
    ("volumes.inspect", "volumes", "name", ["docker", "volume", "inspect"]),
])
@pytest.mark.parametrize("defect,identities", [
    ("missing", ["identity-a"]),
    ("extra", ["identity-b", "identity-a", "identity-extra"]),
    ("duplicate", ["identity-a", "identity-a"]),
])
def test_inventory_inspect_commands_reject_identity_set_defects(
    name: str, collection: str, identity_key: str, prefix: list[str],
    defect: str, identities: list[str],
):
    remote = comprehensive_inventory(f"inspect-{defect}", datetime.now(timezone.utc))
    remote["docker"][collection] = [
        {identity_key: "identity-a"},
        {identity_key: "identity-b"},
    ]
    remote["queryProofs"][name]["command"] = [*prefix, *identities]

    blockers = srv5_terminal._inventory_query_blockers(
        remote, remote["composeProject"], remote["session"])
    assert any(
        f"query command/result differs: {name}" in blocker for blocker in blockers
    ), blockers


def test_terminal_accepts_compact_full_tree_above_legacy_entry_cap(tmp_path: Path):
    root, descriptor_path, status, remote = campaign(tmp_path)
    result_tree = compact_tree(
        srv5_terminal.REMOTE_RESULTS,
        entry_count=50_001,
        file_count=50_000,
        total_file_bytes=123_456_789,
    )
    remote["paths"]["resultTree"] = result_tree
    remote["stableState"]["resultTreeSha256"] = result_tree["metadataSha256"]
    remote["stateFingerprint"] = srv5_terminal._sha256_bytes(json.dumps(
        remote["stableState"], sort_keys=True, separators=(",", ":")).encode())
    write(root / "remote-final-state.json", remote)
    reseal(root)

    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "pass", report["blockers"]


@pytest.mark.parametrize("defect", ["racy", "summary-digest", "legacy-capped-shape"])
def test_compact_full_tree_rollup_detects_planted_defects(tmp_path: Path, defect: str):
    root, descriptor_path, status, remote = campaign(tmp_path)
    tree = remote["paths"]["resultTree"]
    if defect == "racy":
        tree["firstPassSha256"] = "f" * 64
        tree["stable"] = False
        remote["queryPassed"] = False
        remote["verdict"] = "blocked"
        remote["blockers"] = [
            "one or more comprehensive inventory queries failed",
            "result or release tree scan was unreadable or changed during inventory",
        ]
    elif defect == "summary-digest":
        tree["entryCount"] += 1
    else:
        remote["paths"]["resultTree"] = {
            "root": srv5_terminal.REMOTE_RESULTS,
            "exists": True,
            "entries": [],
            "truncated": False,
            "sha256": srv5_terminal._sha256_bytes(b"[]"),
        }
    write(root / "remote-final-state.json", remote)
    reseal(root)

    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    expected = "full-tree rollup" if defect == "racy" else "authoritative replay failed"
    assert any(expected in item for item in report["blockers"]), report["blockers"]


@pytest.mark.parametrize("defect", ["dialect", "incomplete", "root", "error-digest"])
def test_terminal_independently_enforces_full_tree_invariants(
    tmp_path: Path, monkeypatch, defect: str,
):
    root, _descriptor_path, _status, remote = campaign(tmp_path)
    tree = remote["paths"]["resultTree"]
    if defect == "dialect":
        tree["dialect"] = "unversioned-tree"
    elif defect == "incomplete":
        tree["complete"] = False
    elif defect == "root":
        tree["root"] = "/tmp/not-the-results-namespace"
    else:
        tree["errorSha256"] = srv5_terminal._sha256_bytes(b"alternate-empty-errors")

    class AcceptingHarness:
        @staticmethod
        def inventory(*_args, **_kwargs):
            return remote

    monkeypatch.setattr(srv5_terminal, "_load_module", lambda *_args: AcceptingHarness)
    blockers = srv5_terminal._terminal_inventory_blockers(
        remote,
        target="fb14srv5",
        campaign=root.name,
        project=remote["composeProject"],
        release=f"{srv5_terminal.REMOTE_RUNS}/{'a' * 12}/{root.name}",
    )
    expected = {
        "dialect": "dialect is invalid",
        "incomplete": "invalid or incomplete",
        "root": "exact host namespace",
        "error-digest": "non-empty error digest",
    }[defect]
    assert any(expected in item for item in blockers), blockers


@pytest.mark.parametrize("defect", ["not-acquired", "not-released", "wrong-scope"])
def test_execution_lease_must_be_acquired_and_released(tmp_path: Path, defect: str):
    root, descriptor_path, status, remote = campaign(tmp_path)
    path = root / "execution-lease.json"
    lease = json.loads(path.read_text())
    if defect == "not-acquired":
        lease["acquisition"].update({"acquired": False, "acquiredAt": None, "returnCode": 75})
    elif defect == "not-released":
        lease["release"].update({
            "requestedAt": None, "unlockReturnCode": None,
            "verificationReturnCode": None, "observed": False,
        })
    else:
        lease["scope"] = "fb14srv5:other"
    write(path, lease)
    reseal(root)

    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("execution lease" in item for item in report["blockers"])


@pytest.mark.parametrize("defect", ["source", "settle", "snapshot-identity"])
def test_retained_launch_preflight_is_identity_bound_and_stable(tmp_path: Path, defect: str):
    root, descriptor_path, status, remote = campaign(tmp_path)
    path = root / "preflight.json"
    record = json.loads(path.read_text())
    if defect == "source":
        record["source"]["descriptorSha256"] = "f" * 64
    elif defect == "settle":
        record["preflight"]["settleSeconds"] = 59
    else:
        record["preflight"]["second"]["campaign"] = "other"
    write(path, record)
    reseal(root)

    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("preflight" in item for item in report["blockers"])


def test_old_loose_inventory_dialect_is_rejected(tmp_path: Path):
    root, descriptor_path, status, remote = campaign(tmp_path)
    assert validate((root, descriptor_path, status, remote))["verdict"] == "pass"
    remote["queries"] = {}
    write(root / "remote-final-state.json", remote)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any("authoritative replay failed" in item for item in report["blockers"])


@pytest.mark.parametrize("artifact,argument", [
    ("terminal-status.json", "status"),
    ("remote-final-state.json", "remote"),
])
def test_retained_terminal_proofs_must_equal_supplied_values(
    tmp_path: Path, artifact: str, argument: str
):
    root, descriptor_path, status, remote = campaign(tmp_path)
    path = root / artifact
    retained = json.loads(path.read_text())
    retained["campaign"] = "other"
    write(path, retained)
    reseal(root)
    report = validate((root, descriptor_path, status, remote))
    assert report["verdict"] == "blocked"
    assert any(f"retained {'terminal status' if argument == 'status' else 'remote final state'} differs" in item
               for item in report["blockers"])


def test_manifest_detects_changed_and_unlisted_files(tmp_path: Path):
    root, _, _, _ = campaign(tmp_path)
    (root / "schedule.json").write_text("{}\n")
    report = srv5_terminal.verify_manifest(root)
    assert report["verdict"] == "blocked"
    assert any("digest/size mismatch" in blocker for blocker in report["blockers"])
    reseal(root)
    (root / "unlisted.txt").write_text("new")
    report = srv5_terminal.verify_manifest(root)
    assert report["verdict"] == "blocked"
    assert any("membership differs" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize(
    "skew_micros,expected_clean",
    [(1, True), (-1, True), (3, False)],
    ids=["one-micro-late", "one-micro-early", "three-micros"],
)
def test_intervention_barrier_walls_tolerate_epoch_float_rounding(
    skew_micros: int, expected_clean: bool,
):
    """F-ADH-070: the producer derives the intervention barrier walls from
    epoch-float arithmetic while this validator replays them with
    datetime+timedelta; a one-microsecond rounding difference must not block,
    and a three-microsecond deviation must still block."""
    intervention, configuration, barrier, images, posture = effect_intervention_inputs()
    barrier_at = datetime.fromisoformat(barrier["barrierAt"])
    onset_seconds = intervention["measurementBarrier"]["scheduledOnsetSeconds"]
    intervention["measurementBarrier"]["scheduledOnsetWall"] = (
        barrier_at + timedelta(seconds=onset_seconds)
        + timedelta(microseconds=skew_micros)
    ).isoformat()
    receipt_intervention = json.loads(json.dumps(intervention))
    blockers = srv5_terminal._intervention_artifact_blockers(
        intervention,
        receipt_intervention=receipt_intervention,
        configuration=configuration,
        barrier=barrier,
        runtime_images=images,
        posture=posture,
        where="rounding-envelope",
    )
    timing = [item for item in blockers if "barrier/timing differs" in item]
    if expected_clean:
        assert not timing, blockers
    else:
        assert timing, blockers


# F-ADH-084: the campaign's producer gate, this terminal validator, the receipt
# validator and candidate_pilot must all net out a rejected AMQP container by
# the SAME rule, so a crash cell cannot be valid in one copy and blocked in
# another. The rule itself lives in performance_campaign.exposure_tolerance.
CRASH_BANNER_DIAGNOSTIC = {
    "schemaVersion": 1,
    "sequence": 1399,
    "bodyBytes": 155,
    "bodySha256": "e" * 64,
    "error": "37 unconsumed records-region bytes",
    "recordClasses": ["kieker.common.record.misc.KiekerMetadataRecord"],
    "parsedExecutionRecords": 0,
    "loggingTimestampNs": 1_788_693_604_746_414_240,
    "registryContainerIds": ["640b7c0a2577"],
}


def container_tolerance(**updates) -> dict:
    value = {
        "schemaVersion": 1,
        "rule": "timestamp-scoped-exposure-tolerance-v2",
        "fault": "persistence-crash",
        "applied": True,
        "window": {"startEpoch": 1_788_693_448.493637, "endEpoch": 1_788_693_609.828891,
                   "settleSeconds": 11.130717039108276, "marginSeconds": 0.0},
        "toleratedCorrelationErrorEvents": 0,
        "toleratedEoiGapTraces": 0,
        "toleratedMissingEoiCount": 0,
        "toleratedContainerParseFailures": 1,
        "residualCorrelationErrorEvents": 0,
        "residualEoiGapTraces": 0,
        "residualMissingEoiCount": 0,
        "residualContainerParseFailures": 0,
        "containerParseFailures": [CRASH_BANNER_DIAGNOSTIC],
    }
    value.update(updates)
    return value


def test_terminal_validator_nets_out_only_an_accounted_restart_banner():
    events, telemetry, stats = effect_telemetry_inputs()
    stats["records_bad"] = 0
    stats["record_parse_success_ratio"] = 1.0
    telemetry["parseFailures"] = 0
    stats["containers_bad"] = 1
    stats["container_parse_success_ratio"] = 3 / 4

    def blockers(tolerance, *, effect_contract=True):
        return srv5_terminal._collector_telemetry_blockers(
            events, telemetry, stats, posture="full",
            effect_contract=effect_contract, where="crash-arm",
            exposure_tolerance=tolerance)

    assert not any("container parse" in blocker
                   for blocker in blockers(container_tolerance()))
    # No tolerance at all still means zero tolerance.
    assert any("container parse failures are not exactly zero"
               in blocker for blocker in blockers(None))
    # Cost evidence may never carry one.
    assert any("cost evidence carries a nonzero container parse tolerance"
               in blocker for blocker in blockers(container_tolerance(),
                                                  effect_contract=False))
    # A claim its own diagnostics do not cover is refused outright.
    for label, tolerance in {
        "undescribed": container_tolerance(containerParseFailures=[]),
        "over-claimed": container_tolerance(toleratedContainerParseFailures=2),
        "not-a-list": container_tolerance(containerParseFailures={}),
    }.items():
        assert any("not accounted for by its diagnostics" in blocker
                   for blocker in blockers(tolerance)), label
        assert any("container parse failures are not exactly zero" in blocker
                   for blocker in blockers(tolerance)), label
    assert any("container parse tolerance counters differ" in blocker
               for blocker in blockers(container_tolerance(
                   toleratedContainerParseFailures="1")))


def test_terminal_container_tolerance_matches_the_producer_rule():
    """One formula: this validator's netting equals what the producer derives."""
    campaign = importlib.util.module_from_spec(
        importlib.util.spec_from_file_location(
            "campaign_for_terminal_container_tolerance",
            Path(__file__).parents[1] / "modules/teastore/execution/performance_campaign.py",
        ))
    campaign.__loader__.exec_module(campaign)
    intervention = {
        "successful": True, "service": "persistence",
        "targetContainerId": "640b7c0a2577" + "0" * 52,
        "actualOnsetWall": "2026-09-06T11:17:28.493637+00:00",
        "actualOffsetWall": "2026-09-06T11:19:58.698174+00:00",
        "readiness": {"observedAtWall": "2026-09-06T11:20:09.828891+00:00"},
    }
    produced = campaign.exposure_tolerance(
        [], intervention, fault="persistence-crash",
        container_failures=[CRASH_BANNER_DIAGNOSTIC])
    assert produced == container_tolerance()
