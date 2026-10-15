import base64
import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import pytest


MODULE = Path(__file__).parents[1] / "modules/teastore/execution/srv5_harness.py"
SPEC = importlib.util.spec_from_file_location("srv5_harness", MODULE)
srv5_harness = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(srv5_harness)


def completed(payload: object) -> subprocess.CompletedProcess:
    stdout = payload if isinstance(payload, bytes) else (json.dumps(payload) + "\n").encode()
    return subprocess.CompletedProcess(["ssh"], 0, stdout, b"")


def runtime_admission() -> dict:
    return {
        "path": Path("admission.json"),
        "content": b'{"kind":"runtime-admission"}\n',
        "sha256": "d" * 64,
        "receipt": {"authorizationDeadline": "2100-01-01T00:00:00Z"},
        "deadlineEpoch": 4102444800,
        "stopEpoch": 4102444500,
        "cleanupReserveSeconds": 300,
    }


def query(command: list[str], *, return_code: int = 0,
          stdout: str = "", stderr: str = "") -> dict:
    return {"command": command, "returnCode": return_code,
            "stdout": stdout, "stderr": stderr}


def compact_tree(root: str, *, exists: bool = True, stable: bool = True,
                 error_count: int = 0, file_count: int = 0) -> dict:
    error_digest = hashlib.sha256(
        (b"[]" if error_count == 0 else b"planted-error")).hexdigest()
    entry_count = (1 + file_count) if exists else 0
    chunk_size = 4096
    chunks = [hashlib.sha256(f"{root}:chunk:{index}".encode()).hexdigest()
              for index in range((entry_count + chunk_size - 1) // chunk_size)]
    metadata = hashlib.sha256(json.dumps({
        "algorithm": "sha256", "chunkSize": chunk_size,
        "entryCount": entry_count, "chunks": chunks,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    summary = {
        "dialect": "srv5-tree-metadata-v1", "algorithm": "sha256",
        "complete": error_count == 0,
        "exists": exists, "rootKind": "directory" if exists else "missing",
        "entryCount": entry_count,
        "kindCounts": {"directory": 1 if exists else 0,
                       "file": file_count if exists else 0,
                       "symlink": 0, "other": 0},
        "totalFileBytes": file_count if exists else 0,
        "oldestMtimeNs": 1 if exists else None,
        "newestMtimeNs": 1 if exists else None, "metadataSha256": metadata,
        "chunkSize": chunk_size, "chunkCount": len(chunks), "chunkSha256": chunks,
        "errorCount": error_count, "errorSha256": error_digest,
    }
    second = hashlib.sha256(json.dumps(
        summary, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    first = second if stable else hashlib.sha256(b"different-first-pass").hexdigest()
    return {"root": root, **summary, "firstPassSha256": first,
            "secondPassSha256": second,
            "stable": stable and summary["complete"]}


def tree_pass_sha256(tree: dict) -> str:
    keys = {
        "dialect", "algorithm", "complete", "exists", "rootKind", "entryCount",
        "kindCounts", "totalFileBytes", "oldestMtimeNs", "newestMtimeNs",
        "metadataSha256", "chunkSize", "chunkCount", "chunkSha256",
        "errorCount", "errorSha256",
    }
    return hashlib.sha256(json.dumps(
        {key: tree[key] for key in keys}, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()


def clean_resource_proof(project: str) -> dict:
    label = f"label=com.docker.compose.project={project}"
    commands = {
        "containers": ["docker", "ps", "-aq", "--no-trunc", "--filter", label],
        "networks": ["docker", "network", "ls", "-q", "--no-trunc", "--filter", label],
        "volumes": ["docker", "volume", "ls", "-q", "--filter", label],
    }
    return {
        "project": project, "queryPassed": True,
        "containers": [], "networks": [], "volumes": [],
        "queries": {kind: query(command)
                    for kind, command in commands.items()},
    }


def inventory_proof(campaign: str = "campaign-1", target: str = "fb14srv5") -> dict:
    project = f"obst-{campaign}"
    empty_entries: list[dict] = []
    tree_digest = hashlib.sha256(json.dumps(
        empty_entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    project_resources = clean_resource_proof(project)
    result_paths = {"resultRoot": False, "log": False, "exit": False}
    required_ports = {str(port): [] for port in srv5_harness.REQUIRED_PORTS}
    result_tree = compact_tree(srv5_harness.REMOTE_RESULTS)
    release_tree = compact_tree(srv5_harness.REMOTE_RUNS)
    tree_digest = result_tree["metadataSha256"]
    stable = {
        "containers": [], "images": [], "composeProjects": [], "networks": [], "volumes": [],
        "runningContainers": [],
        "projectResources": {"project": project, "containers": [], "networks": [], "volumes": []},
        "requiredPorts": required_ports, "experimentSessions": [], "relevantProcesses": [],
        "resultPaths": result_paths, "releaseExists": False,
        "resultTreeSha256": result_tree["metadataSha256"],
        "releaseTreeSha256": release_tree["metadataSha256"],
        "openWriters": [], "allOpenWriters": [], "timeSynchronized": True,
        "queueQueries": [],
    }
    inventory_queries = {
        "runningContainers": query(["docker", "ps"]),
        "session": query(["tmux", "has-session"], return_code=1,
                         stderr="no server running\n"),
        "allContainers": query(["docker", "ps", "-aq"]),
        "containerInspect": query(["docker", "inspect"], stdout="[]\n"),
        "imageInspect": query(["docker", "image", "inspect"], stdout="[]\n"),
        "composeProjects": query(["docker", "compose", "ls"], stdout="[]\n"),
        "allNetworks": query(["docker", "network", "ls"]),
        "networkInspect": query(["docker", "network", "inspect"], stdout="[]\n"),
        "allVolumes": query(["docker", "volume", "ls"]),
        "volumeInspect": query(["docker", "volume", "inspect"], stdout="[]\n"),
        "dockerEvents": query(["docker", "events"]),
        "listeners": query(["ss", "-H", "-lntup"]),
        "processes": query(["ps"]),
        "tmuxSessions": query(["tmux", "list-sessions"], return_code=1,
                              stderr="no server running\n"),
        "screenSessions": query(["screen", "-ls"], return_code=1,
                                stdout="No Sockets found.\n"),
        "tools": {name: query([name]) for name in (
            "dockerServer", "dockerCompose", "dockerInfo", "tmux", "screen",
            "python", "ss", "setsid")},
    }
    proof = {
        "schemaVersion": 1, "capturedAt": "2026-08-28T00:00:00+00:00",
        "target": target, "campaign": campaign, "composeProject": project,
        "session": f"teastore-{campaign}", "active": False,
        "projectResources": project_resources, "openWriters": [],
        "runningContainers": [], "rootFreeKiB": 100 * 1024 * 1024,
        "cpuCount": 16, "load1": 0.1,
        "resultPaths": result_paths, "releaseExists": False,
        "host": {
            "hostname": "srv5", "kernel": "5.10", "platform": "linux",
            "bootEpoch": 1, "bootUtc": "1970-01-01T00:00:01+00:00", "cpuCount": 16,
            "loadAverage": [0.1, 0.2, 0.3],
            "memoryKiB": {"MemTotal": 1024, "MemAvailable": 512,
                         "SwapTotal": 0, "SwapFree": 0},
            "rootFilesystem": {"path": "/", "blockSize": 4096,
                               "totalKiB": 200 * 1024 * 1024,
                               "freeKiB": 100 * 1024 * 1024,
                               "totalInodes": 1000, "freeInodes": 900},
        },
        "docker": {"containers": [], "images": [], "composeProjects": [],
                   "networks": [], "volumes": [], "eventsLastHour": [],
                   "queueQueries": [], "parseErrors": []},
        "listeners": [], "requiredPorts": required_ports,
        "sessions": {"tmux": [], "screen": [], "experimentLike": []},
        "processes": {"experimentLike": []},
        "paths": {"resultTree": result_tree, "releaseTree": release_tree,
                  "allOpenWriters": []},
        "timeSync": {"synchronized": True,
                     "proof": query(["timedatectl"], stdout="yes\n")},
        "stableState": stable,
        "stateFingerprint": hashlib.sha256(json.dumps(
            stable, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "queries": inventory_queries, "queryPassed": True,
        "verdict": "pass", "blockers": [],
    }
    return proof


# Sanitized v2 fixture.  It intentionally contains no command stdout/stderr;
# only stream digests and normalized observations can be persisted by preflight.
def inventory_proof(campaign: str = "campaign-1", target: str = "fb14srv5") -> dict:
    project = f"obst-{campaign}"
    empty_entries: list[dict] = []
    empty_digest = hashlib.sha256(b"").hexdigest()
    tree_digest = hashlib.sha256(json.dumps(
        empty_entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    stream = {"sha256": empty_digest, "bytes": 0, "lineCount": 0}
    proof_names = {
        "project.containers", "project.networks", "project.volumes", "containers.list",
        "containers.inspect", "images.inspect", "compose.projects", "networks.list",
        "networks.inspect", "volumes.list", "volumes.inspect", "docker.events", "docker.info",
        "host.listeners", "host.processes", "sessions.exact", "sessions.tmux", "sessions.screen",
        "host.timeSync", "tool.dockerServer", "tool.dockerCompose", "tool.tmux", "tool.screen",
        "tool.python", "tool.ss", "tool.setsid", "tool.flock", "docker.daemonStarted",
    }
    query_proofs = {
        name: {"command": [name], "returnCode": 0,
               "stdout": dict(stream), "stderr": dict(stream)}
        for name in proof_names
    }
    project_resources = {"project": project, "queryPassed": True,
                         "containers": [], "networks": [], "volumes": []}
    result_paths = {"resultRoot": False, "log": False, "exit": False}
    required_ports = {str(port): [] for port in srv5_harness.REQUIRED_PORTS}
    result_tree = compact_tree(srv5_harness.REMOTE_RESULTS)
    release_tree = compact_tree(srv5_harness.REMOTE_RUNS)
    tree_digest = result_tree["metadataSha256"]
    classes = {label: 0 for label in srv5_harness.RESOURCE_CLASSES}
    classification = {
        "policySource": "modules/teastore/deployment/srv5.yaml",
        "policySha256": srv5_harness.load_host_policy()["sha256"],
        "counts": classes, "blocking": [],
    }
    tools = {name: {"valueSha256": empty_digest, "present": True} for name in {
        "tool.dockerServer", "tool.dockerCompose", "tool.tmux", "tool.screen",
        "tool.python", "tool.ss", "tool.setsid", "tool.flock", "docker.daemonStarted",
    }}
    stable = {
        "containers": [], "images": [], "composeProjects": [], "networks": [], "volumes": [],
        "runningContainers": [], "projectResources": project_resources,
        "requiredPorts": required_ports, "experimentSessions": [], "relevantProcesses": [],
        "resultPaths": result_paths, "releaseExists": False,
        "resultTreeSha256": result_tree["metadataSha256"],
        "releaseTreeSha256": release_tree["metadataSha256"],
        "openWriters": [], "allOpenWriters": [], "timeSynchronized": True,
        "queueStates": [], "classification": classification,
    }
    return {
        "schemaVersion": 3, "capturedAt": "2026-08-28T00:00:00+00:00",
        "target": target, "campaign": campaign, "composeProject": project,
        "session": f"teastore-{campaign}", "active": False,
        "projectResources": project_resources, "openWriters": [], "runningContainers": [],
        "rootFreeKiB": 100 * 1024 * 1024, "cpuCount": 16, "load1": 0.1,
        "resultPaths": result_paths, "releaseExists": False,
        "host": {"hostnameSha256": empty_digest, "kernel": "5.10",
                 "platformSha256": empty_digest, "bootEpoch": 1,
                 "bootUtc": "1970-01-01T00:00:01+00:00", "cpuCount": 16,
                 "loadAverage": [0.1, 0.2, 0.3],
                 "memoryKiB": {"MemTotal": 1024, "MemAvailable": 512,
                                "SwapTotal": 0, "SwapFree": 0},
                 "rootFilesystem": {"path": "/", "blockSize": 4096,
                                    "totalKiB": 200 * 1024 * 1024,
                                    "freeKiB": 100 * 1024 * 1024,
                                    "totalInodes": 1000, "freeInodes": 900},
                 "toolVersions": tools},
        "docker": {"containers": [], "images": [], "composeProjects": [],
                   "networks": [], "volumes": [], "eventsLastHour": [],
                   "queueStates": [], "parseErrors": [], "info": {}},
        "listeners": [], "requiredPorts": required_ports,
        "sessions": {"all": [], "experimentLike": []},
        "processes": {"experimentLike": []},
        "paths": {"resultTree": result_tree, "releaseTree": release_tree,
                  "allOpenWriters": []},
        "timeSync": {"synchronized": True}, "classification": classification,
        "stableState": stable,
        "stateFingerprint": hashlib.sha256(json.dumps(
            stable, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "queryProofs": query_proofs, "queryPassed": True,
        "verdict": "pass", "blockers": [],
    }


def schedule_fixture(root: Path, *, blocks: int, postures: tuple[str, ...]) -> None:
    configuration = {
        "blocks": blocks, "postures": list(postures), "fault": "none",
        "frameworkCommit": "framework", "sutReferenceCommit": "sut", "selectionId": "auth",
        "selectionSourceSha256": "goal", "descriptorId": "descriptor",
        "descriptorSha256": "d" * 64, "evidenceLabel": "smoke-validation",
    }
    runs = [{"block": block, "posture": posture}
            for block in range(1, blocks + 1) for posture in postures]
    (root / "schedule.json").write_text(json.dumps({"configuration": configuration, "runs": runs}))
    for item in runs:
        run_id = f"b{item['block']:02d}-{item['posture']}"
        run = root / run_id
        run.mkdir()
        (run / "receipt.json").write_text(json.dumps({
            "runId": run_id, "posture": item["posture"],
            "source": {"frameworkCommit": "framework", "sutReferenceCommit": "sut",
                       "selectionId": "auth", "selectionSourceSha256": "goal",
                       "descriptorId": "descriptor", "descriptorSha256": "d" * 64,
                       "evidenceLabel": "smoke-validation"},
            "intervention": None, "canonicality": {"blockers": []},
            "workload": {"completed": 10}, "latencyMs": {"count": 10},
            "teardown": {"projectClean": True},
        }))


def owner_fixture(descriptor: dict, campaign: str = "campaign-1",
                  target: str = "fb14srv5") -> dict:
    commit = "a" * 40
    return {
        "schemaVersion": 2, "campaign": campaign, "target": target,
        "session": f"teastore-{campaign}",
        "composeProject": srv5_harness.campaign_project(campaign),
        "frameworkCommit": commit,
        "sutReferenceCommit": srv5_harness.SUT_REFERENCE_COMMIT,
        "release": srv5_harness.release_path(commit, campaign),
        "resultRoot": srv5_harness.result_path(campaign),
        "descriptorId": descriptor["id"], "descriptorSha256": descriptor["sha256"],
        "expectedReceipts": descriptor["blocks"] * len(descriptor["postures"]),
        "runtimeAdmissionSha256": "d" * 64,
        "authorizationDeadlineEpoch": 4102444800,
        "experimentStopEpoch": 4102444500,
        "cleanupReserveSeconds": 300,
    }


def fetched_archive(campaign: str, owner: dict, *, include_exit: bool = True) -> bytes:
    payload = io.BytesIO()
    files = {
        f"{campaign}/harness-owner.json": (
            json.dumps(owner, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        f"{campaign}/schedule.json": b"{}\n",
        f"{campaign}.log": b"log\n",
    }
    if include_exit:
        files[f"{campaign}.exit"] = b"0\n"
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        directory = tarfile.TarInfo(campaign)
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        for name, content in files.items():
            item = tarfile.TarInfo(name)
            item.size = len(content)
            archive.addfile(item, io.BytesIO(content))
    return payload.getvalue()


def test_rejects_unsafe_campaign_identifier():
    for value in ("../../other", ".", "..", "a.b", "Campaign-1"):
        with pytest.raises(ValueError):
            srv5_harness.checked_name(value)


def test_rejects_ssh_option_and_shell_targets():
    for value in ("-oProxyCommand=bad", "host;touch-bad", "../host", "."):
        with pytest.raises(ValueError):
            srv5_harness.checked_target(value)
    assert srv5_harness.checked_target("fb14srv5.example.org") == "fb14srv5.example.org"


def test_rejects_unsafe_or_duplicate_campaign_parameters():
    base = dict(blocks=5, warmup=120, duration=600, rate=0.15, concurrency=8,
                postures="none,selected,full", fault="none", fault_at=240,
                outage=30, selection="auth")
    assert srv5_harness.validate_campaign_parameters(**base) == ("none", "selected", "full")
    with pytest.raises(ValueError):
        srv5_harness.validate_campaign_parameters(**{**base, "postures": "none,$(touch bad)"})
    with pytest.raises(ValueError):
        srv5_harness.validate_campaign_parameters(**{**base, "postures": "none,none"})
    with pytest.raises(ValueError):
        srv5_harness.validate_campaign_parameters(**{**base, "rate": float("nan")})
    with pytest.raises(ValueError):
        srv5_harness.validate_campaign_parameters(**{**base, "selection": "../../goal.json"})
    with pytest.raises(ValueError):
        srv5_harness.validate_campaign_parameters(**{**base, "fault": "$(touch bad)"})
    with pytest.raises(ValueError):
        srv5_harness.validate_campaign_parameters(**{**base, "fault": "auth-freeze", "fault_at": 590})


def test_diagnostic_descriptor_exactly_binds_the_current_runner(tmp_path: Path):
    parsed = srv5_harness.load_descriptor()
    assert parsed["postures"] == ("full",)
    assert parsed["duration"] == 60
    assert parsed["evidenceLabel"] == "smoke-validation"
    document = json.loads(parsed["content"])
    for mutation in ("wrong-workload", "wrong-collector", "unknown-field"):
        changed = json.loads(json.dumps(document))
        if mutation == "wrong-workload":
            changed["design"]["workload"]["path"] = "modules/teastore/workload/load_gen_loop.sh"
        elif mutation == "wrong-collector":
            changed["collector"]["durationSeconds"] = 91
        else:
            changed["unexpected"] = True
        path = tmp_path / f"{mutation}.json"
        path.write_text(json.dumps(changed))
        with pytest.raises(ValueError):
            srv5_harness.load_descriptor(path)


def test_effect_diagnostic_descriptor_binds_fault_timing_and_no_cost_claim(tmp_path: Path):
    path = Path(__file__).parents[1] / (
        "pipelines/campaigns/teastore-performance-effect-diagnostic-smoke.json"
    )
    parsed = srv5_harness.load_descriptor(path)
    assert parsed["fault"] == "persistence-crash"
    assert parsed["faultAt"] == 240
    assert parsed["outage"] == 30
    assert parsed["duration"] == 600
    assert parsed["selection"] == "fault-qualification"

    document = json.loads(parsed["content"])
    for mutation in (
        "wrong-selection", "missing-effect-gate", "unbounded-timing",
        "in-window-timing-drift", "different-fault", "no-fault-escape",
        "different-target", "promotion-wording", "extra-block",
        "combined-dispatch-bypass",
    ):
        changed = json.loads(json.dumps(document))
        if mutation == "wrong-selection":
            changed["design"]["selectionId"] = "auth"
        elif mutation == "missing-effect-gate":
            changed["validation"].remove("cost-effect-separation")
        elif mutation == "unbounded-timing":
            changed["design"]["fault"]["faultAtSeconds"] = 590
        elif mutation == "in-window-timing-drift":
            changed["design"]["fault"]["faultAtSeconds"] = 300
        elif mutation == "different-fault":
            changed["design"]["fault"]["scenario"] = "auth-freeze"
        elif mutation == "no-fault-escape":
            changed["design"]["fault"] = {"scenario": "none"}
            changed["validation"].remove("fault-intervention-proof")
            changed["validation"].remove("cost-effect-separation")
        elif mutation == "different-target":
            changed["target"] = "fb14srv6"
        elif mutation == "promotion-wording":
            changed["promotion"]["reason"] = "Still noncanonical, but not reviewed."
        elif mutation == "extra-block":
            changed["design"]["blocks"] = 2
        else:
            changed["id"] = "teastore-effect-diagnostic-mutated"
            changed["target"] = "fb14srv6"
            changed["design"]["fault"] = {"scenario": "none"}
            changed["validation"].remove("fault-intervention-proof")
            changed["validation"].remove("cost-effect-separation")
        planted = tmp_path / f"{mutation}.json"
        planted.write_text(json.dumps(changed))
        with pytest.raises(ValueError):
            srv5_harness.load_descriptor(planted)


def _write_admission(path: Path, *, seconds_until_deadline: int = 600,
                     observed_seconds_ago: int = 0) -> dict:
    module = srv5_harness._candidate_pilot_module()
    frozen = module.strict_json_file(srv5_harness.CANDIDATE_DESCRIPTOR)
    current = dt.datetime.now(dt.timezone.utc)
    receipt = module.admit_runtime(
        frozen,
        mode="diagnostic",
        evidence_label="smoke-validation",
        now=current - dt.timedelta(seconds=observed_seconds_ago),
        authorization_deadline=current + dt.timedelta(seconds=seconds_until_deadline),
        time_budget_seconds=18000,
        diagnostic_run_count=1,
        diagnostic_warmup_seconds=120,
        diagnostic_measurement_seconds=60,
        lifecycle_allowance_seconds=0,
    )
    path.write_text(json.dumps(receipt, sort_keys=True) + "\n")
    return receipt


def test_time_window_feasibility_is_never_runtime_admission(tmp_path: Path):
    descriptor = srv5_harness.load_descriptor()
    path = tmp_path / "admission.json"
    receipt = _write_admission(path)
    assert receipt["runtimeAuthorized"] is False
    with pytest.raises(ValueError, match="non-authorizing|does not authorize"):
        srv5_harness.load_runtime_admission(path, descriptor)

    attacked = dict(receipt, runCount=2)
    path.write_text(json.dumps(attacked) + "\n")
    with pytest.raises(ValueError, match="non-authorizing|does not authorize"):
        srv5_harness.load_runtime_admission(path, descriptor)


def test_stale_feasibility_cannot_become_runtime_authority(tmp_path: Path):
    descriptor = srv5_harness.load_descriptor()
    path = tmp_path / "stale-admission.json"
    _write_admission(path, seconds_until_deadline=100, observed_seconds_ago=3600)
    with pytest.raises(ValueError, match="non-authorizing|does not authorize"):
        srv5_harness.load_runtime_admission(path, descriptor)


def test_nonauthorizing_feasibility_receipt_never_reaches_launcher_side_effects(
        tmp_path: Path, monkeypatch):
    admission_path = tmp_path / "feasibility.json"
    receipt = _write_admission(admission_path)
    assert receipt["kind"] == "time-window-feasibility"
    assert receipt["feasible"] is True
    assert receipt["admitted"] is False
    assert receipt["runtimeAuthorized"] is False
    assert receipt["candidateEvidenceAuthorized"] is False

    calls: list[str] = []

    def planted(name, result=None):
        def invoke(*_args, **_kwargs):
            calls.append(name)
            return result
        return invoke

    monkeypatch.setattr(srv5_harness, "LOCAL_PREFLIGHTS", tmp_path / "preflight")
    monkeypatch.setattr(srv5_harness, "framework_commit", planted("commit", "a" * 40))
    monkeypatch.setattr(
        srv5_harness, "preflight", planted("preflight", {
            "verdict": "pass", "campaign": "campaign-1", "target": "fb14srv5",
        }),
    )
    monkeypatch.setattr(srv5_harness, "materialize", planted("materialize", "release"))
    monkeypatch.setattr(srv5_harness, "_write_remote", planted("write"))
    monkeypatch.setattr(srv5_harness, "ssh", planted("ssh", completed(b"")))
    monkeypatch.setattr(srv5_harness, "status", planted("status", {
        "campaign": "campaign-1", "active": True, "exitCode": "",
        "receipts": 0, "expected": 1,
    }))

    with pytest.raises(ValueError, match="non-authorizing|does not authorize"):
        srv5_harness.launch(
            "fb14srv5", "campaign-1", admission_path=admission_path,
        )
    assert calls == []


@pytest.mark.parametrize("payload", [
    b"", b"{}\n{}\n", b"[]\n", b"\xff\n", b"not-json\n",
    b'{"queryPassed":true,"queryPassed":false}\n', b'{"value":NaN}\n',
])
def test_remote_json_protocol_rejects_empty_duplicate_or_malformed_records(payload: bytes):
    with pytest.raises(RuntimeError):
        srv5_harness._strict_json(payload, "test")


def test_retained_local_json_accepts_one_pretty_printed_document_only():
    pretty = b'{\n  "campaign": "campaign-1",\n  "nested": {\n    "ok": true\n  }\n}\n'
    assert srv5_harness._strict_local_json_document(pretty, "retained test") == {
        "campaign": "campaign-1", "nested": {"ok": True},
    }
    with pytest.raises(RuntimeError):
        srv5_harness._strict_json(pretty, "remote test")


@pytest.mark.parametrize("payload", [
    b'{}{}', b'{}\n{}\n', b'{"ok":true} trailing',
    b'{"key":1,"key":2}', b'{"value":NaN}', b'{"value":Infinity}',
    b'{"value":-Infinity}', b'[]', b'\xff', b'',
])
def test_retained_local_json_rejects_concatenated_duplicate_nonfinite_or_invalid_documents(
        payload: bytes):
    with pytest.raises(RuntimeError):
        srv5_harness._strict_local_json_document(payload, "retained test")


def test_main_validate_reads_pretty_retained_documents(
        tmp_path: Path, monkeypatch, capsys):
    root = tmp_path / "campaign-1"
    root.mkdir()
    (root / "terminal-status.json").write_text(json.dumps(
        {"campaign": "campaign-1", "exitCode": "0"}, indent=2) + "\n")
    (root / "remote-final-state.json").write_text(json.dumps(
        {"schemaVersion": 3, "verdict": "pass"}, indent=2) + "\n")
    descriptor = {"target": "fb14srv5", "blocks": 1, "postures": ("full",)}
    monkeypatch.setattr(srv5_harness, "load_descriptor", lambda _path: descriptor)
    monkeypatch.setattr(srv5_harness, "_local_owner", lambda *_args, **_kwargs: {})
    observed = []

    def validate(evidence_root, received_descriptor, current, remote_state, **kwargs):
        observed.append((evidence_root, received_descriptor, current, remote_state, kwargs))
        return {"verdict": "pass"}

    monkeypatch.setattr(srv5_harness, "terminal_validate", validate)
    monkeypatch.setattr(sys, "argv", [
        "srv5_harness.py", "validate", "--campaign", "campaign-1",
        "--destination", str(tmp_path), "--manifest-sha256", "a" * 64,
    ])
    assert srv5_harness.main() == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "pass"
    assert observed == [(
        root, descriptor, {"campaign": "campaign-1", "exitCode": "0"},
        {"schemaVersion": 3, "verdict": "pass"},
        {"seal": False, "expected_manifest_sha256": "a" * 64},
    )]


def test_status_protocol_rejects_planted_type_and_exit_defects(monkeypatch):
    base = {"schemaVersion": 1, "campaign": "campaign-1", "active": False,
            "exitCode": "0", "receipts": 1, "expected": 1, "queryPassed": True,
            "tmuxReturnCode": 1, "tmuxStderr": ""}
    monkeypatch.setattr(srv5_harness, "ssh", lambda *_args, **_kwargs: completed(base))
    assert srv5_harness.status("fb14srv5", "campaign-1", 1)["exitCode"] == "0"
    for field, value in (("active", "false"), ("exitCode", "garbage"),
                         ("receipts", -1), ("queryPassed", False)):
        planted = {**base, field: value}
        monkeypatch.setattr(srv5_harness, "ssh", lambda *_args, value=planted, **_kwargs: completed(value))
        with pytest.raises(RuntimeError):
            srv5_harness.status("fb14srv5", "campaign-1", 1)


def test_inventory_identity_and_query_failures_are_fail_closed(monkeypatch):
    proof = inventory_proof()
    monkeypatch.setattr(srv5_harness, "ssh", lambda *_args, **_kwargs: completed(proof))
    assert srv5_harness.inventory("fb14srv5", "campaign-1")["verdict"] == "pass"
    mismatched = json.loads(json.dumps(proof))
    mismatched["composeProject"] = "foreign"
    monkeypatch.setattr(srv5_harness, "ssh", lambda *_args, **_kwargs: completed(mismatched))
    with pytest.raises(RuntimeError):
        srv5_harness.inventory("fb14srv5", "campaign-1")
    contradictory = json.loads(json.dumps(proof))
    contradictory["projectResources"]["queryPassed"] = False
    monkeypatch.setattr(srv5_harness, "ssh", lambda *_args, **_kwargs: completed(contradictory))
    with pytest.raises(RuntimeError):
        srv5_harness.inventory("fb14srv5", "campaign-1")


def test_inventory_replays_stability_digest_and_covers_launch_surfaces(monkeypatch):
    proof = inventory_proof()
    planted = json.loads(json.dumps(proof))
    planted["stateFingerprint"] = "f" * 64
    monkeypatch.setattr(srv5_harness, "ssh", lambda *_args, **_kwargs: completed(planted))
    with pytest.raises(RuntimeError, match="fingerprint"):
        srv5_harness.inventory("fb14srv5", "campaign-1")
    rendered = srv5_harness.REMOTE_INVENTORY.decode()
    for required in (
        "/proc/meminfo", "totalInodes", "docker\", \"inspect", "docker\", \"events",
        "compose\", \"ls", "network\", \"inspect", "volume\", \"inspect",
        "ss\", \"-H", "tmux\", \"list-sessions", "screen\", \"-ls",
        "allOpenWriters", "NTPSynchronized", "required_ports", "queue_states",
        "tool.flock", "classification", "commandSha256",
    ):
        assert required in rendered
    assert '"labels": config.get("Labels")' not in rendered


def _replace_inventory_tree(proof: dict, name: str, tree: dict, *, blocked: bool) -> None:
    proof["paths"][name] = tree
    stable_key = "resultTreeSha256" if name == "resultTree" else "releaseTreeSha256"
    proof["stableState"][stable_key] = tree["metadataSha256"]
    proof["stateFingerprint"] = hashlib.sha256(json.dumps(
        proof["stableState"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if blocked:
        proof["queryPassed"] = False
        proof["verdict"] = "blocked"
        proof["blockers"] = ["result or release tree scan was unreadable or changed during inventory"]


def test_compact_tree_rollup_covers_more_than_twenty_thousand_paths(monkeypatch):
    proof = inventory_proof()
    large = compact_tree(srv5_harness.REMOTE_RESULTS, file_count=50_000)
    _replace_inventory_tree(proof, "resultTree", large, blocked=False)
    monkeypatch.setattr(srv5_harness, "ssh", lambda *_args, **_kwargs: completed(proof))
    retained = srv5_harness.inventory("fb14srv5", "campaign-1")
    assert retained["paths"]["resultTree"]["entryCount"] == 50_001
    assert retained["paths"]["resultTree"]["chunkCount"] == 13
    assert retained["paths"]["resultTree"]["dialect"] == "srv5-tree-metadata-v1"
    assert "entries" not in retained["paths"]["resultTree"]
    assert len(json.dumps(retained["paths"]["resultTree"])) < 3_000
    rendered = srv5_harness.REMOTE_INVENTORY.decode()
    assert "max_entries" not in rendered
    assert "os.scandir" in rendered
    assert "first = tree_pass(root)" in rendered
    assert "second = tree_pass(root)" in rendered


@pytest.mark.parametrize("defect", ["changed-between-passes", "unreadable"])
def test_compact_tree_rollup_fails_closed_on_racy_or_unreadable_scans(
        monkeypatch, defect: str):
    proof = inventory_proof()
    tree = compact_tree(
        srv5_harness.REMOTE_RESULTS, stable=False,
        error_count=1 if defect == "unreadable" else 0,
    )
    _replace_inventory_tree(proof, "resultTree", tree, blocked=True)
    monkeypatch.setattr(srv5_harness, "ssh", lambda *_args, **_kwargs: completed(proof))
    inventory_function = srv5_harness.inventory
    retained = inventory_function("fb14srv5", "campaign-1")
    assert retained["verdict"] == "blocked"
    monkeypatch.setattr(srv5_harness, "inventory", lambda *_args, **_kwargs: retained)
    monkeypatch.setattr(srv5_harness.time, "sleep", lambda _seconds: None)
    with pytest.raises(RuntimeError, match="unreadable or racy"):
        srv5_harness.preflight("fb14srv5", "campaign-1", settle_seconds=1)

    contradictory = json.loads(json.dumps(proof))
    contradictory["queryPassed"] = True
    contradictory["verdict"] = "pass"
    contradictory["blockers"] = []
    monkeypatch.setattr(srv5_harness, "ssh", lambda *_args, **_kwargs: completed(contradictory))
    with pytest.raises(RuntimeError, match="claims success"):
        inventory_function("fb14srv5", "campaign-1")


@pytest.mark.parametrize("defect", ["swapped", "wrong-result", "wrong-release"])
def test_inventory_rejects_swapped_or_wrong_tree_roots(monkeypatch, defect: str):
    proof = inventory_proof()
    if defect == "swapped":
        proof["paths"]["resultTree"], proof["paths"]["releaseTree"] = (
            proof["paths"]["releaseTree"], proof["paths"]["resultTree"])
    elif defect == "wrong-result":
        proof["paths"]["resultTree"]["root"] = "/tmp/not-results"
    else:
        proof["paths"]["releaseTree"]["root"] = "/tmp/not-runs"
    monkeypatch.setattr(srv5_harness, "ssh", lambda *_args, **_kwargs: completed(proof))
    with pytest.raises(RuntimeError, match="exact host namespaces"):
        srv5_harness.inventory("fb14srv5", "campaign-1")


@pytest.mark.parametrize("defect", ["dialect", "chunk-count", "chunk-digest", "error-digest"])
def test_inventory_rejects_tree_rollup_dialect_and_chunk_defects(monkeypatch, defect: str):
    proof = inventory_proof()
    tree = proof["paths"]["resultTree"]
    if defect == "dialect":
        tree["dialect"] = "unspecified"
    elif defect == "chunk-count":
        tree["chunkCount"] += 1
    elif defect == "chunk-digest":
        tree["chunkSha256"][0] = "f" * 64
    else:
        tree["errorSha256"] = hashlib.sha256(b"alternate-empty-errors").hexdigest()
        tree["secondPassSha256"] = tree_pass_sha256(tree)
        tree["firstPassSha256"] = tree["secondPassSha256"]
    monkeypatch.setattr(srv5_harness, "ssh", lambda *_args, **_kwargs: completed(proof))
    expected = "non-empty error digest" if defect == "error-digest" else None
    with pytest.raises(RuntimeError, match=expected):
        srv5_harness.inventory("fb14srv5", "campaign-1")


def test_remote_inventory_discards_planted_raw_secrets_before_serialization(monkeypatch):
    secret = "SECRET_VALUE"
    container = [{
        "Id": "container-1", "Name": "/stopped", "Created": "now", "Image": "image-1",
        "Config": {"Image": "safe-image", "Env": [f"PASSWORD={secret}"],
                   "Labels": {"planted.secret": secret}},
        "State": {"Status": "exited", "Running": False, "ExitCode": 0},
        "HostConfig": {}, "NetworkSettings": {"Ports": {}, "Networks": {}},
        "Mounts": [], "RestartCount": 0,
    }, {
        "Id": "container-legacy", "Name": "/hotelres", "Created": "now", "Image": "image-1",
        "Config": {"Image": "safe-image", "Labels": {
            "com.docker.compose.project": "hotelres",
            "com.docker.compose.project.working_dir": "/home/stig/DeathStarBench/hotelReservation",
            "com.docker.compose.project.config_files": "/home/stig/DeathStarBench/hotelReservation/docker-compose.yml",
            "com.docker.compose.service": "frontend"}},
        "State": {"Status": "exited", "Running": False, "ExitCode": 0},
        "HostConfig": {}, "NetworkSettings": {"Ports": {}, "Networks": {}},
        "Mounts": [], "RestartCount": 0,
    }, {
        "Id": "container-foreign", "Name": "/monitoring", "Created": "now", "Image": "image-2",
        "Config": {"Image": "safe-image", "Labels": {
            "com.docker.compose.project": "rogue",
            "com.docker.compose.project.working_dir": "/srv/rogue",
            "com.docker.compose.project.config_files": "/srv/rogue/compose.yml",
            "com.docker.compose.service": "grafana"}},
        "State": {"Status": "exited", "Running": False, "ExitCode": 0},
        "HostConfig": {"RestartPolicy": {"Name": "no", "MaximumRetryCount": 0}},
        "NetworkSettings": {"Ports": {}, "Networks": {}},
        "Mounts": [{"Type": "volume", "Name": "foreign-attached", "Source": "/safe3",
                    "Destination": "/data", "RW": True}], "RestartCount": 0,
    }, {
        "Id": "container-unsafe-legacy", "Name": "/hotelres-restarting",
        "Created": "now", "Image": "image-1",
        "Config": {"Image": "safe-image", "Labels": {
            "com.docker.compose.project": "hotelres",
            "com.docker.compose.project.working_dir": "/home/stig/DeathStarBench/hotelReservation",
            "com.docker.compose.project.config_files": "/home/stig/DeathStarBench/hotelReservation/docker-compose.yml",
            "com.docker.compose.service": "unsafe"}},
        "State": {"Status": "exited", "Running": False, "Paused": False,
                  "Restarting": False, "Dead": False, "ExitCode": 0},
        "HostConfig": {"RestartPolicy": {"Name": "always", "MaximumRetryCount": 0}},
        "NetworkSettings": {"Ports": {}, "Networks": {}},
        "Mounts": [], "RestartCount": 0,
    }]
    volume = [
        {"Name": "anonymous-volume", "Driver": "local", "Scope": "local",
         "Mountpoint": "/safe", "Labels": {"planted.secret": secret}},
        {"Name": "hotelres-data", "Driver": "local", "Scope": "local",
         "Mountpoint": "/safe2", "Labels": {
             "com.docker.compose.project": "hotelres",
             "com.docker.compose.project.working_dir": "/home/stig/DeathStarBench/hotelReservation",
             "com.docker.compose.project.config_files": "/home/stig/DeathStarBench/hotelReservation/docker-compose.yml"}},
        {"Name": "foreign-attached", "Driver": "local", "Scope": "local",
         "Mountpoint": "/safe3", "Labels": {}},
    ]
    networks = [
        {"Id": "builtin-bridge", "Name": "bridge", "Driver": "bridge",
         "Scope": "local", "Internal": False, "Attachable": False,
         "Labels": {}, "Containers": {}},
        {"Id": "legacy-network", "Name": "teastore-network", "Driver": "bridge",
         "Scope": "local", "Internal": False, "Attachable": False,
         "Labels": {}, "Containers": {}},
    ]
    compose = [
        {"Name": "hotelres", "Status": "exited(1)",
         "ConfigFiles": "/home/stig/DeathStarBench/hotelReservation/docker-compose.yml"},
        {"Name": "rogue", "Status": "exited(1)",
         "ConfigFiles": "/srv/rogue/compose.yml"},
    ]

    def fake_run(argv, **_kwargs):
        stdout, stderr, returncode = "", "", 0
        if argv[:4] == ["docker", "ps", "-aq", "--no-trunc"] and "--filter" not in argv:
            stdout = "container-unsafe-legacy\ncontainer-legacy\ncontainer-foreign\ncontainer-1\n"
        elif argv[:2] == ["docker", "inspect"]:
            stdout = json.dumps(container)
        elif argv[:3] == ["docker", "image", "inspect"]:
            stdout = "[]"
        elif argv[:3] == ["docker", "compose", "ls"]:
            stdout = json.dumps(compose)
        elif argv[:3] == ["docker", "network", "inspect"]:
            stdout = json.dumps(networks)
        elif argv[:3] == ["docker", "network", "ls"] and "--filter" not in argv:
            stdout = "legacy-network\nbuiltin-bridge\n"
        elif argv[:3] == ["docker", "volume", "ls"] and "--filter" not in argv:
            stdout = "hotelres-data\nforeign-attached\nanonymous-volume\n"
        elif argv[:3] == ["docker", "volume", "inspect"]:
            stdout = json.dumps(volume)
        elif argv[:2] == ["docker", "events"]:
            stdout = json.dumps({"Type": "container", "Action": "stop", "timeNano": 1,
                                 "Actor": {"ID": "safe", "Attributes": {"secret": secret}}}) + "\n"
        elif argv[:2] == ["docker", "info"]:
            stdout = json.dumps({"ServerVersion": "1", "Secret": secret})
        elif argv[:2] == ["tmux", "has-session"]:
            returncode, stderr = 1, f"no server running {secret}"
        elif argv[:2] == ["tmux", "list-sessions"]:
            returncode, stderr = 1, f"no server running {secret}"
        elif argv[:2] == ["screen", "-ls"]:
            returncode, stdout = 1, f"No Sockets found. {secret}\n"
        elif argv[:2] == ["timedatectl", "show"]:
            stdout = "yes\n"
        elif argv[:2] == ["ss", "-H"]:
            stdout = f"tcp LISTEN 0 1 127.0.0.1:22 owner={secret}\n"
        elif argv[0] == "ps":
            stdout = f"1 0 root Thu Aug 28 00:00:00 2026 1 unrelated --token {secret}\n"
        elif argv[:3] in (["docker", "network", "ls"], ["docker", "volume", "ls"]):
            stdout = ""
        elif argv[:2] == ["docker", "ps"]:
            stdout = ""
        else:
            stdout = secret + "\n"
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    policy = srv5_harness.load_host_policy()
    assert any(item["project"] == "docker"
               for item in policy["remote"]["allowedLegacyProjects"])
    assert policy["remote"]["preserveUnreferencedVolumes"] is True
    encoded = base64.urlsafe_b64encode(json.dumps(
        policy["remote"], sort_keys=True, separators=(",", ":")).encode()).decode()
    argv = ["inventory", "fb14srv5", "campaign-1", "obst-campaign-1",
            "teastore-campaign-1", srv5_harness.result_path("campaign-1"), "-",
            encoded, policy["sha256"]]
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", argv)
    platform_module = __import__("platform")
    monkeypatch.setattr(platform_module, "node", lambda: "srv5")
    monkeypatch.setattr(platform_module, "release", lambda: "5.10")
    monkeypatch.setattr(platform_module, "platform", lambda: "linux")
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(srv5_harness.REMOTE_INVENTORY, "<inventory>", "exec"), {})
    serialized = output.getvalue()
    assert secret not in serialized
    proof = json.loads(serialized)
    assert proof["classification"]["counts"] == {
        "owned-current": 0, "owned-legacy": 2, "shared-approved": 4,
        "foreign": 3, "unknown": 2,
    }
    assert {item["identity"] for item in proof["classification"]["blocking"]} >= {
        "rogue", "container-unsafe-legacy", "foreign-attached",
    }
    assert next(row for row in proof["docker"]["volumes"]
                if row["name"] == "anonymous-volume")["classification"] == "shared-approved"
    assert next(row for row in proof["docker"]["networks"]
                if row["name"] == "teastore-network")["classification"] == "shared-approved"
    assert proof["queryProofs"]["docker.info"]["stdout"]["bytes"] > 0
    assert proof["queryProofs"]["containers.inspect"]["command"][2:] == [
        "container-1", "container-foreign", "container-legacy", "container-unsafe-legacy",
    ]
    assert proof["queryProofs"]["images.inspect"]["command"][3:] == ["image-1", "image-2"]
    assert proof["queryProofs"]["networks.inspect"]["command"][3:] == [
        "builtin-bridge", "legacy-network",
    ]
    assert proof["queryProofs"]["volumes.inspect"]["command"][3:] == [
        "anonymous-volume", "foreign-attached", "hotelres-data",
    ]
    monkeypatch.setattr(srv5_harness, "ssh", lambda *_args, **_kwargs: completed(proof))
    assert srv5_harness.inventory("fb14srv5", "campaign-1")["verdict"] == "blocked"


def test_preflight_blocks_foreign_runtime_and_stale_result_paths(monkeypatch):
    proof = inventory_proof()
    proof["runningContainers"] = [{"id": "foreign", "name": "other", "composeProject": "other"}]
    proof["resultPaths"]["log"] = True
    monkeypatch.setattr(srv5_harness, "inventory", lambda *_args, **_kwargs: proof)
    monkeypatch.setattr(srv5_harness.time, "sleep", lambda _seconds: None)
    with pytest.raises(RuntimeError) as error:
        srv5_harness.preflight("fb14srv5", "campaign-1")
    assert "running containers" in str(error.value)
    assert "result paths" in str(error.value)


def test_preflight_requires_two_stable_snapshots(monkeypatch):
    first = inventory_proof()
    second = json.loads(json.dumps(first))
    second["stateFingerprint"] = "e" * 64
    snapshots = iter((first, second))
    monkeypatch.setattr(srv5_harness, "inventory", lambda *_args, **_kwargs: next(snapshots))
    slept = []
    monkeypatch.setattr(srv5_harness.time, "sleep", lambda seconds: slept.append(seconds))
    with pytest.raises(RuntimeError, match="state changed"):
        srv5_harness.preflight("fb14srv5", "campaign-1", settle_seconds=7)
    assert slept == [7]

    snapshots = iter((first, json.loads(json.dumps(first))))
    monkeypatch.setattr(srv5_harness, "inventory", lambda *_args, **_kwargs: next(snapshots))
    proof = srv5_harness.preflight("fb14srv5", "campaign-1", settle_seconds=7)
    assert proof["stable"] is True
    assert proof["settleSeconds"] == 7


def test_bundle_validation_requires_schedule_complete_blocks_and_clean_teardown(tmp_path: Path):
    schedule_fixture(tmp_path, blocks=2, postures=("none", "selected", "full"))
    assert srv5_harness.validate_bundle(tmp_path, blocks=2)["verdict"] == "pass"
    (tmp_path / "b01-none" / "receipt.json").unlink()
    assert srv5_harness.validate_bundle(tmp_path, blocks=2)["verdict"] == "blocked"
    empty = tmp_path / "no-schedule"
    empty.mkdir()
    assert srv5_harness.validate_bundle(empty)["verdict"] == "blocked"


def test_bundle_validation_binds_receipts_to_recorded_descriptor(tmp_path: Path):
    schedule_fixture(tmp_path, blocks=1, postures=("full",))
    assert srv5_harness.validate_bundle(
        tmp_path, blocks=1, postures_expected=("full",))["verdict"] == "pass"
    receipt_path = tmp_path / "b01-full" / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["source"]["descriptorSha256"] = "e" * 64
    receipt_path.write_text(json.dumps(receipt))
    assert srv5_harness.validate_bundle(
        tmp_path, blocks=1, postures_expected=("full",))["verdict"] == "blocked"


def test_owner_is_strictly_bound_to_descriptor_and_derived_paths(tmp_path: Path):
    descriptor = srv5_harness.load_descriptor()
    owner = owner_fixture(descriptor)
    assert srv5_harness.validate_owner(
        owner, target="fb14srv5", campaign="campaign-1", descriptor=descriptor)["release"] == (
            srv5_harness.release_path("a" * 40, "campaign-1"))
    legacy = {key: value for key, value in owner.items()
              if key in srv5_harness.OWNER_FIELDS_V1}
    legacy["schemaVersion"] = 1
    assert srv5_harness.validate_owner(
        legacy, target="fb14srv5", campaign="campaign-1", descriptor=descriptor)[
            "schemaVersion"] == 1
    for field, value in (
        ("release", "/home/stig/observability-placement-runs/a;touch/pwn"),
        ("resultRoot", "/tmp/other"),
        ("expectedReceipts", True),
        ("descriptorSha256", "f" * 64),
        ("sutReferenceCommit", "b" * 40),
        ("runtimeAdmissionSha256", "bad"),
        ("experimentStopEpoch", 4102444499),
        ("cleanupReserveSeconds", 299),
    ):
        planted = {**owner, field: value}
        with pytest.raises(RuntimeError):
            srv5_harness.validate_owner(
                planted, target="fb14srv5", campaign="campaign-1", descriptor=descriptor)
    duplicate = json.dumps(owner).rstrip("}") + ',"release":"/tmp/other"}'
    path = tmp_path / "owner.json"
    path.write_text(duplicate)
    with pytest.raises(RuntimeError):
        srv5_harness._local_owner(
            path, target="fb14srv5", campaign="campaign-1", descriptor=descriptor)


def test_direct_materialize_is_construction_blocked_before_git_archive_or_ssh(monkeypatch):
    calls = []
    monkeypatch.setattr(
        srv5_harness, "execute",
        lambda *_args, **_kwargs: calls.append("git-archive"),
    )
    monkeypatch.setattr(
        srv5_harness, "ssh",
        lambda *_args, **_kwargs: calls.append("ssh"),
    )
    with pytest.raises(RuntimeError, match="construction blocked"):
        srv5_harness.materialize("fb14srv5", "a" * 40, "campaign-1", "auth")
    assert calls == []


def test_fetch_rejects_collisions_and_publishes_only_complete_owner_bound_archive(
        tmp_path: Path, monkeypatch):
    descriptor = srv5_harness.load_descriptor()
    owner = owner_fixture(descriptor)
    payload = fetched_archive("campaign-1", owner)
    calls = []
    monkeypatch.setattr(
        srv5_harness, "ssh",
        lambda *_args, **_kwargs: calls.append(1) or completed(payload),
    )
    root = srv5_harness.fetch(
        "fb14srv5", "campaign-1", tmp_path / "evidence", descriptor)
    assert root == (tmp_path / "evidence" / "campaign-1").resolve()
    assert (root / "harness.log").read_text() == "log\n"
    assert (root / "harness.exit").read_text() == "0\n"
    assert not list((tmp_path / "evidence").glob(".campaign-1.fetch-*"))
    with pytest.raises(RuntimeError, match="already exists"):
        srv5_harness.fetch(
            "fb14srv5", "campaign-1", tmp_path / "evidence", descriptor)
    assert calls == [1]

    incomplete = tmp_path / "incomplete"
    monkeypatch.setattr(
        srv5_harness, "ssh",
        lambda *_args, **_kwargs: completed(
            fetched_archive("campaign-1", owner, include_exit=False)),
    )
    with pytest.raises(RuntimeError, match="membership"):
        srv5_harness.fetch("fb14srv5", "campaign-1", incomplete, descriptor)
    assert not (incomplete / "campaign-1").exists()
    assert not list(incomplete.glob(".campaign-1.fetch-*"))


def test_launch_rejects_an_immediate_nonzero_exit(tmp_path: Path, monkeypatch):
    descriptor = srv5_harness.load_descriptor()
    writes = []
    monkeypatch.setattr(srv5_harness, "load_descriptor", lambda _path: descriptor)
    monkeypatch.setattr(srv5_harness, "load_runtime_admission",
                        lambda *_args, **_kwargs: runtime_admission())
    monkeypatch.setattr(srv5_harness, "framework_commit", lambda _descriptor: "a" * 40)
    monkeypatch.setattr(
        srv5_harness, "preflight",
        lambda *_args, **_kwargs: {
            "verdict": "pass", "campaign": "campaign-1", "target": "fb14srv5",
        },
    )
    monkeypatch.setattr(srv5_harness, "materialize", lambda *_args, **_kwargs: "release")
    monkeypatch.setattr(srv5_harness, "LOCAL_PREFLIGHTS", tmp_path / "preflight")
    monkeypatch.setattr(
        srv5_harness, "_write_remote",
        lambda _target, path, payload, **kwargs: writes.append((path, payload, kwargs)),
    )
    monkeypatch.setattr(srv5_harness, "ssh", lambda *_args, **_kwargs: completed(b""))
    monkeypatch.setattr(
        srv5_harness, "status",
        lambda *_args, **_kwargs: {"campaign": "campaign-1", "active": False,
                                  "exitCode": "7", "receipts": 0, "expected": 1},
    )
    with pytest.raises(RuntimeError, match="code 7"):
        srv5_harness.launch(
            "fb14srv5", "campaign-1", admission_path=Path("admission.json"))
    owner = json.loads(writes[0][1])
    assert owner["schemaVersion"] == 2
    assert owner["sutReferenceCommit"] == srv5_harness.SUT_REFERENCE_COMMIT
    assert owner["resultRoot"] == srv5_harness.result_path("campaign-1")
    assert owner["runtimeAdmissionSha256"] == "d" * 64
    assert owner["authorizationDeadlineEpoch"] == 4102444800
    assert owner["experimentStopEpoch"] == 4102444500
    assert owner["cleanupReserveSeconds"] == 300
    assert b"--sut-reference-commit" in writes[-1][1]
    assert b"deadline-controller.py" in writes[-1][1]
    assert b"execution-lease.json" in writes[-1][1]
    assert b"flock -n 9" in writes[-1][1]
    assert b"flock -u 9" in writes[-1][1]
    assert writes[-1][1].index(b"flock -n 9") < writes[-1][1].index(b"python3")
    assert b"experiment_stop_epoch=4102444500" in writes[-1][1]
    controller = next(payload for path, payload, _kwargs in writes
                      if path.endswith("deadline-controller.py"))
    assert b"start_new_session=True" in controller
    assert b"os.killpg(process_group, signal.SIGKILL)" in controller
    assert b'"deadline-cleanup.json"' in controller
    retained = json.loads((tmp_path / "preflight/campaign-1.json").read_text())
    assert retained["preflight"] == {
        "verdict": "pass", "campaign": "campaign-1", "target": "fb14srv5",
    }
    assert retained["source"]["frameworkCommit"] == "a" * 40


@pytest.mark.parametrize("contended", [True, False])
def test_launcher_lease_rejects_contention_before_runner_and_records_release(
        tmp_path: Path, monkeypatch, contended: bool):
    descriptor = srv5_harness.load_descriptor()
    runs = tmp_path / "runs"
    results = tmp_path / "results"
    monkeypatch.setattr(srv5_harness, "REMOTE_RUNS", str(runs))
    monkeypatch.setattr(srv5_harness, "REMOTE_RESULTS", str(results))
    monkeypatch.setattr(srv5_harness, "HOST_LEASE_PATH", str(runs / ".lease"))
    monkeypatch.setattr(srv5_harness, "LOCAL_PREFLIGHTS", tmp_path / "preflight")
    monkeypatch.setattr(srv5_harness, "load_descriptor", lambda _path: descriptor)
    monkeypatch.setattr(srv5_harness, "load_runtime_admission",
                        lambda *_args, **_kwargs: runtime_admission())
    monkeypatch.setattr(srv5_harness, "framework_commit", lambda _descriptor: "a" * 40)
    monkeypatch.setattr(srv5_harness, "preflight", lambda *_args, **_kwargs: {
        "verdict": "pass", "campaign": "campaign-1", "target": "fb14srv5",
    })
    monkeypatch.setattr(srv5_harness, "materialize", lambda *_args, **_kwargs: "unused")
    writes = []
    monkeypatch.setattr(srv5_harness, "_write_remote",
                        lambda _target, path, payload, **kwargs: writes.append((path, payload, kwargs)))
    monkeypatch.setattr(srv5_harness, "ssh", lambda *_args, **_kwargs: completed(b""))
    monkeypatch.setattr(srv5_harness, "status", lambda *_args, **_kwargs: {
        "campaign": "campaign-1", "active": True, "exitCode": "",
        "receipts": 0, "expected": 1,
    })
    srv5_harness.launch(
        "fb14srv5", "campaign-1", admission_path=Path("admission.json"))
    release = Path(srv5_harness.release_path("a" * 40, "campaign-1"))
    result = Path(srv5_harness.result_path("campaign-1"))
    runner = release / "modules/teastore/execution/performance_campaign.py"
    runner.parent.mkdir(parents=True)
    for relative in (
        "modules/teastore/deployment/compose/docker-compose_kieker.yaml",
        "modules/teastore/deployment/compose/docker-compose_rabbitmq.yaml",
        "modules/teastore/deployment/compose/isolation.override.yaml",
    ):
        compose_file = release / relative
        compose_file.parent.mkdir(parents=True, exist_ok=True)
        compose_file.write_text("services: {}\n")
    marker = tmp_path / "runner-started"
    runner.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('yes')\n")
    result.mkdir(parents=True)
    runs.mkdir(parents=True, exist_ok=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_flock = fake_bin / "flock"
    fake_flock.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"-n\" ] && [ \"${FAKE_FLOCK_CONTENDED:-0}\" = 1 ]; then exit 1; fi\n"
        "exit 0\n"
    )
    fake_flock.chmod(0o755)
    fake_setsid = fake_bin / "setsid"
    fake_setsid.write_text("#!/bin/sh\nexec \"$@\"\n")
    fake_setsid.chmod(0o755)
    fake_docker = fake_bin / "docker"
    fake_docker.write_text("#!/bin/sh\nexit 0\n")
    fake_docker.chmod(0o755)
    controller_payload = next(
        payload for path, payload, _kwargs in writes if path.endswith("deadline-controller.py"))
    controller = release / ".local/deadline-controller.py"
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_bytes(controller_payload)
    launcher_payload = next(payload for path, payload, _kwargs in writes if path.endswith(".sh"))
    launcher = tmp_path / "launcher.sh"
    launcher.write_bytes(launcher_payload)
    launcher.chmod(0o755)
    environment = dict(os.environ, PATH=str(fake_bin) + os.pathsep + os.environ["PATH"],
                       FAKE_FLOCK_CONTENDED="1" if contended else "0")
    completed_run = subprocess.run(["/bin/sh", str(launcher)], env=environment,
                                   capture_output=True, check=False)
    lease = json.loads((result / "execution-lease.json").read_text())
    assert lease["scope"] == "fb14srv5:teastore-performance"
    assert lease["lockPath"] == str(runs / ".lease")
    if contended:
        assert completed_run.returncode == 75
        assert lease["acquisition"]["acquired"] is False
        assert lease["acquisition"]["returnCode"] == 1
        assert lease["release"]["observed"] is False
        assert not marker.exists()
    else:
        assert completed_run.returncode == 0
        assert lease["acquisition"]["acquired"] is True
        assert lease["acquisition"]["returnCode"] == 0
        assert lease["release"]["unlockReturnCode"] == 0
        assert lease["release"]["verificationReturnCode"] == 0
        assert lease["release"]["observed"] is True
        cleanup = json.loads((result / "deadline-cleanup.json").read_text())
        cleanup_completed = dt.datetime.fromisoformat(
            cleanup["authorization"]["completedAt"].replace("Z", "+00:00"))
        lease_release_requested = lease["release"]["requestedAt"]
        assert "." in lease_release_requested
        assert dt.datetime.fromisoformat(
            lease_release_requested.replace("Z", "+00:00")) >= cleanup_completed
        assert marker.read_text() == "yes"


@pytest.mark.parametrize("remaining_container,expected_code", [(False, 124), (True, 125)])
def test_deadline_controller_kills_term_ignoring_group_tears_down_and_checks_residue(
        tmp_path: Path, monkeypatch, remaining_container: bool, expected_code: int):
    descriptor = srv5_harness.load_descriptor()
    runs = tmp_path / "runs"
    results = tmp_path / "results"
    monkeypatch.setattr(srv5_harness, "REMOTE_RUNS", str(runs))
    monkeypatch.setattr(srv5_harness, "REMOTE_RESULTS", str(results))
    monkeypatch.setattr(srv5_harness, "HOST_LEASE_PATH", str(runs / ".lease"))
    monkeypatch.setattr(srv5_harness, "LOCAL_PREFLIGHTS", tmp_path / "preflight")
    monkeypatch.setattr(srv5_harness, "DEADLINE_TERM_GRACE_SECONDS", 0.2)
    monkeypatch.setattr(srv5_harness, "DEADLINE_KILL_GRACE_SECONDS", 0.5)
    monkeypatch.setattr(srv5_harness, "DEADLINE_COMPOSE_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(srv5_harness, "DEADLINE_QUERY_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(srv5_harness, "DEADLINE_LEASE_FINALIZER_SECONDS", 1)
    current_epoch = int(time.time())
    admission = {
        **runtime_admission(),
        "deadlineEpoch": current_epoch + 12,
        "stopEpoch": current_epoch + 2,
        "receipt": {"authorizationDeadline": "test-deadline"},
    }
    monkeypatch.setattr(srv5_harness, "load_descriptor", lambda _path: descriptor)
    monkeypatch.setattr(srv5_harness, "load_runtime_admission",
                        lambda *_args, **_kwargs: admission)
    monkeypatch.setattr(srv5_harness, "framework_commit", lambda _descriptor: "a" * 40)
    monkeypatch.setattr(srv5_harness, "preflight", lambda *_args, **_kwargs: {
        "verdict": "pass", "campaign": "campaign-1", "target": "fb14srv5",
    })
    monkeypatch.setattr(srv5_harness, "materialize", lambda *_args, **_kwargs: "unused")
    writes = []
    monkeypatch.setattr(srv5_harness, "_write_remote",
                        lambda _target, path, payload, **kwargs: writes.append((path, payload, kwargs)))
    monkeypatch.setattr(srv5_harness, "ssh", lambda *_args, **_kwargs: completed(b""))
    monkeypatch.setattr(srv5_harness, "status", lambda *_args, **_kwargs: {
        "campaign": "campaign-1", "active": True, "exitCode": "",
        "receipts": 0, "expected": 1,
    })
    srv5_harness.launch(
        "fb14srv5", "campaign-1", admission_path=Path("admission.json"))

    release = Path(srv5_harness.release_path("a" * 40, "campaign-1"))
    result = Path(srv5_harness.result_path("campaign-1"))
    runner = release / "modules/teastore/execution/performance_campaign.py"
    runner.parent.mkdir(parents=True)
    term_seen = tmp_path / "term-seen"
    child_pid = tmp_path / "child-pid"
    runner.write_text(
        "import os, signal, time\n"
        "from pathlib import Path\n"
        f"term_seen = Path({str(term_seen)!r})\n"
        f"Path({str(child_pid)!r}).write_text(str(os.getpid()))\n"
        "signal.signal(signal.SIGTERM, lambda *_: term_seen.write_text('yes'))\n"
        "while True: time.sleep(0.05)\n"
    )
    for relative in (
        "modules/teastore/deployment/compose/docker-compose_kieker.yaml",
        "modules/teastore/deployment/compose/docker-compose_rabbitmq.yaml",
        "modules/teastore/deployment/compose/isolation.override.yaml",
    ):
        compose_file = release / relative
        compose_file.parent.mkdir(parents=True, exist_ok=True)
        compose_file.write_text("services: {}\n")
    result.mkdir(parents=True)
    runs.mkdir(parents=True, exist_ok=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_flock = fake_bin / "flock"
    fake_flock.write_text("#!/bin/sh\nexit 0\n")
    fake_flock.chmod(0o755)
    docker_log = tmp_path / "docker-commands"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$FAKE_DOCKER_LOG\"\n"
        "if [ \"$1\" = ps ] && [ \"${FAKE_REMAINING_CONTAINER:-0}\" = 1 ]; then\n"
        " printf 'abc123\\n'\n"
        "fi\n"
        "exit 0\n"
    )
    fake_docker.chmod(0o755)
    controller_payload = next(
        payload for path, payload, _kwargs in writes if path.endswith("deadline-controller.py"))
    controller = release / ".local/deadline-controller.py"
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_bytes(controller_payload)
    launcher_payload = next(payload for path, payload, _kwargs in writes if path.endswith(".sh"))
    launcher = tmp_path / "launcher.sh"
    launcher.write_bytes(launcher_payload)
    launcher.chmod(0o755)
    environment = dict(
        os.environ, PATH=str(fake_bin) + os.pathsep + os.environ["PATH"],
        FAKE_DOCKER_LOG=str(docker_log),
        FAKE_REMAINING_CONTAINER="1" if remaining_container else "0",
    )
    completed_run = subprocess.run(
        ["/bin/sh", str(launcher)], env=environment, capture_output=True,
        check=False, timeout=15)
    assert completed_run.returncode == expected_code
    assert term_seen.read_text() == "yes"
    planted_pid = int(child_pid.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(planted_pid, 0)
    receipt = json.loads((result / "deadline-cleanup.json").read_text())
    assert receipt["trigger"]["reason"] == "authorization-stop-epoch"
    assert receipt["processGroup"] == {
        **receipt["processGroup"],
        "identityValidated": True,
        "termSent": True,
        "exitedDuringTermGrace": False,
        "killRequired": True,
        "killSent": True,
        "gone": True,
        "runnerReturnCode": -signal.SIGKILL,
    }
    expected_compose = ["docker", "compose", "-p", "obst-campaign-1"]
    for relative in receipt["composeTeardown"]["composeFiles"]:
        expected_compose.extend(["-f", str(release / relative)])
    expected_compose.extend(["down", "--volumes", "--remove-orphans"])
    assert receipt["composeTeardown"]["command"] == expected_compose
    assert receipt["composeTeardown"]["returnCode"] == 0
    assert receipt["authorization"]["beforeDeadline"] is True
    assert receipt["authorization"]["leaseFinalizerWindowAvailable"] is True
    lease = json.loads((result / "execution-lease.json").read_text())
    assert lease["release"]["observed"] is True
    commands = docker_log.read_text().splitlines()
    assert commands[0].startswith("compose -p obst-campaign-1 -f ")
    assert commands[0].endswith("down --volumes --remove-orphans")
    if remaining_container:
        assert any(command == "rm -f -- abc123" for command in commands)
        assert len(commands) == 8
        assert receipt["outcome"] == "blocked"
        assert receipt["verification"]["final"]["remaining"]["containers"] == 1
        assert "remaining-containers" in receipt["blockers"]
    else:
        assert len(commands) == 7
        assert receipt["outcome"] == "clean"
        assert receipt["blockers"] == []
        assert receipt["verification"]["final"]["remaining"] == {
            "containers": 0, "networks": 0, "volumes": 0,
        }


def test_controller_finalizes_nonzero_runner_and_recovers_failed_compose_by_label(
        tmp_path: Path):
    release = tmp_path / "release"
    result = tmp_path / "results" / "campaign-1"
    result.mkdir(parents=True)
    for relative in (
        "modules/teastore/deployment/compose/docker-compose_kieker.yaml",
        "modules/teastore/deployment/compose/docker-compose_rabbitmq.yaml",
        "modules/teastore/deployment/compose/isolation.override.yaml",
    ):
        compose_file = release / relative
        compose_file.parent.mkdir(parents=True, exist_ok=True)
        compose_file.write_text("services: {}\n")
    runner = release / "runner.py"
    runner.write_text("raise SystemExit(7)\n")
    controller = release / "deadline-controller.py"
    controller.write_bytes(srv5_harness.REMOTE_DEADLINE_CONTROLLER)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker-commands"
    residue = tmp_path / "owned-container-present"
    residue.write_text("abc123\n")
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$FAKE_DOCKER_LOG\"\n"
        "if [ \"$1\" = compose ]; then exit 1; fi\n"
        "if [ \"$1\" = ps ] && [ -f \"$FAKE_RESIDUE\" ]; then cat \"$FAKE_RESIDUE\"; fi\n"
        "if [ \"$1\" = rm ] && [ \"$2\" = -f ] && [ \"$4\" = abc123 ]; then\n"
        " rm -f \"$FAKE_RESIDUE\"\n"
        "fi\n"
        "exit 0\n"
    )
    fake_docker.chmod(0o755)
    stop = int(time.time()) + 10
    deadline = stop + 10
    command = [
        sys.executable, str(controller), "campaign-1", "obst-campaign-1",
        str(release), str(result), str(stop), str(deadline), "0.2", "0.2",
        "1", "0.5", "1", str(result.parent / "campaign-1.log"),
        "python3", str(runner),
    ]
    environment = dict(
        os.environ, PATH=str(fake_bin) + os.pathsep + os.environ["PATH"],
        FAKE_DOCKER_LOG=str(docker_log), FAKE_RESIDUE=str(residue),
    )
    completed_run = subprocess.run(
        command, env=environment, capture_output=True, check=False, timeout=10)
    assert completed_run.returncode == 7
    assert not residue.exists()
    receipt = json.loads((result / "deadline-cleanup.json").read_text())
    assert receipt["trigger"]["reason"] == "runner-exit"
    assert receipt["processGroup"]["aliveAtCleanupStart"] is False
    assert receipt["processGroup"]["termSent"] is False
    assert receipt["processGroup"]["killSent"] is False
    assert receipt["processGroup"]["runnerReturnCode"] == 7
    assert receipt["composeTeardown"]["returnCode"] == 1
    assert receipt["verification"]["initial"]["remaining"]["containers"] == 1
    assert receipt["verification"]["fallback"]["required"] is True
    removal = receipt["verification"]["fallback"]["actions"]["containers"]
    assert removal["attempted"] is True
    assert removal["command"] == ["docker", "rm", "-f", "--", "abc123"]
    assert receipt["verification"]["final"]["clean"] is True
    assert receipt["outcome"] == "clean"
    assert receipt["blockers"] == []
    assert "compose-teardown-failed" in receipt["warnings"]


def test_controller_refuses_to_overwrite_preexisting_cleanup_receipt(tmp_path: Path):
    release = tmp_path / "release"
    result = tmp_path / "results" / "campaign-1"
    result.mkdir(parents=True)
    for relative in (
        "modules/teastore/deployment/compose/docker-compose_kieker.yaml",
        "modules/teastore/deployment/compose/docker-compose_rabbitmq.yaml",
        "modules/teastore/deployment/compose/isolation.override.yaml",
    ):
        compose_file = release / relative
        compose_file.parent.mkdir(parents=True, exist_ok=True)
        compose_file.write_text("services: {}\n")
    marker = tmp_path / "runner-started"
    runner = release / "runner.py"
    runner.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('yes')\n")
    controller = release / "deadline-controller.py"
    controller.write_bytes(srv5_harness.REMOTE_DEADLINE_CONTROLLER)
    receipt = result / "deadline-cleanup.json"
    planted = b'{"planted":"must-not-change"}\n'
    receipt.write_bytes(planted)
    stop = int(time.time()) + 10
    command = [
        sys.executable, str(controller), "campaign-1", "obst-campaign-1",
        str(release), str(result), str(stop), str(stop + 10), "0.2", "0.2",
        "1", "0.5", "1", str(result.parent / "campaign-1.log"),
        "python3", str(runner),
    ]
    completed_run = subprocess.run(
        command, capture_output=True, check=False, timeout=5)
    assert completed_run.returncode == 79
    assert receipt.read_bytes() == planted
    assert not marker.exists()


def test_controller_kills_term_ignoring_descendant_after_runner_exits(tmp_path: Path):
    release = tmp_path / "release"
    result = tmp_path / "results" / "campaign-1"
    result.mkdir(parents=True)
    for relative in (
        "modules/teastore/deployment/compose/docker-compose_kieker.yaml",
        "modules/teastore/deployment/compose/docker-compose_rabbitmq.yaml",
        "modules/teastore/deployment/compose/isolation.override.yaml",
    ):
        compose_file = release / relative
        compose_file.parent.mkdir(parents=True, exist_ok=True)
        compose_file.write_text("services: {}\n")
    descendant_pid = tmp_path / "descendant-pid"
    descendant_ready = tmp_path / "descendant-ready"
    descendant_term = tmp_path / "descendant-term"
    descendant = release / "descendant.py"
    descendant.write_text(
        "import os, signal, time\n"
        "from pathlib import Path\n"
        f"Path({str(descendant_pid)!r}).write_text(str(os.getpid()))\n"
        f"term = Path({str(descendant_term)!r})\n"
        "signal.signal(signal.SIGTERM, lambda *_: term.write_text('yes'))\n"
        f"Path({str(descendant_ready)!r}).write_text('yes')\n"
        "while True: time.sleep(0.05)\n"
    )
    runner = release / "runner.py"
    runner.write_text(
        "import subprocess, sys, time\n"
        "from pathlib import Path\n"
        f"ready = Path({str(descendant_ready)!r})\n"
        f"subprocess.Popen([sys.executable, {str(descendant)!r}])\n"
        "deadline = time.monotonic() + 3\n"
        "while not ready.exists() and time.monotonic() < deadline: time.sleep(0.01)\n"
        "raise SystemExit(0 if ready.exists() else 9)\n"
    )
    controller = release / "deadline-controller.py"
    controller.write_bytes(srv5_harness.REMOTE_DEADLINE_CONTROLLER)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker-commands"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$FAKE_DOCKER_LOG\"\n"
        "exit 0\n"
    )
    fake_docker.chmod(0o755)
    stop = int(time.time()) + 20
    command = [
        sys.executable, str(controller), "campaign-1", "obst-campaign-1",
        str(release), str(result), str(stop), str(stop + 10), "0.2", "0.5",
        "1", "0.5", "1", str(result.parent / "campaign-1.log"),
        "python3", str(runner),
    ]
    environment = dict(
        os.environ, PATH=str(fake_bin) + os.pathsep + os.environ["PATH"],
        FAKE_DOCKER_LOG=str(docker_log),
    )
    completed_run = subprocess.run(
        command, env=environment, capture_output=True, check=False, timeout=10)
    assert completed_run.returncode == 0
    assert descendant_term.read_text() == "yes"
    planted_pid = int(descendant_pid.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(planted_pid, 0)
    receipt = json.loads((result / "deadline-cleanup.json").read_text())
    assert receipt["trigger"]["reason"] == "runner-exit"
    process = receipt["processGroup"]
    assert process["aliveAtCleanupStart"] is True
    assert process["termSent"] is True
    assert process["exitedDuringTermGrace"] is False
    assert process["killRequired"] is True
    assert process["killSent"] is True
    assert process["gone"] is True
    assert process["runnerReturnCode"] == 0
    assert receipt["composeTeardown"]["command"][-3:] == [
        "down", "--volumes", "--remove-orphans",
    ]
    assert receipt["verification"]["final"]["clean"] is True
    assert receipt["outcome"] == "clean"
    assert receipt["blockers"] == []
    commands = docker_log.read_text().splitlines()
    assert commands[0].startswith("compose -p obst-campaign-1 -f ")
    assert all("obst-campaign-1" in command for command in commands)


def test_preflight_evidence_is_single_use_and_written_before_mutation(tmp_path: Path,
                                                                     monkeypatch):
    descriptor = srv5_harness.load_descriptor()
    proof = {"verdict": "pass", "campaign": "campaign-1", "target": "fb14srv5"}
    monkeypatch.setattr(srv5_harness, "LOCAL_PREFLIGHTS", tmp_path)
    path = srv5_harness.persist_preflight(
        "campaign-1", target="fb14srv5", commit="a" * 40,
        descriptor=descriptor, proof=proof)
    assert json.loads(path.read_text())["preflight"] == proof
    with pytest.raises(RuntimeError, match="already exists"):
        srv5_harness.persist_preflight(
            "campaign-1", target="fb14srv5", commit="a" * 40,
            descriptor=descriptor, proof=proof)


def test_retained_preflight_is_identity_bound_and_installed_once(tmp_path: Path,
                                                                 monkeypatch):
    descriptor = srv5_harness.load_descriptor()
    monkeypatch.setattr(srv5_harness, "LOCAL_PREFLIGHTS", tmp_path / "preflight")
    source = srv5_harness.persist_preflight(
        "campaign-1", target="fb14srv5", commit="a" * 40,
        descriptor=descriptor,
        proof={"verdict": "pass", "campaign": "campaign-1", "target": "fb14srv5"},
    )
    payload, record = srv5_harness.retained_preflight(
        "campaign-1", target="fb14srv5", descriptor=descriptor)
    assert payload == source.read_bytes()
    root = tmp_path / "evidence"
    root.mkdir()
    installed = srv5_harness.install_preflight(
        root, payload, record, {"frameworkCommit": "a" * 40})
    assert installed.read_bytes() == payload
    with pytest.raises(FileExistsError):
        srv5_harness.install_preflight(
            root, payload, record, {"frameworkCommit": "a" * 40})


def test_terminal_validation_seals_once_and_never_reseals(tmp_path: Path,
                                                           monkeypatch):
    root = tmp_path / "campaign-1"
    root.mkdir()
    (root / "campaign-descriptor.json").write_text("{}\n")
    calls = []

    class Terminal:
        MANIFEST_NAME = "content-manifest.json"

        @staticmethod
        def write_manifest(evidence_root):
            calls.append("seal")
            (evidence_root / Terminal.MANIFEST_NAME).write_text("sealed\n")

        @staticmethod
        def validate_campaign(*_args, **kwargs):
            calls.append(("validate", kwargs))
            return {
                "verdict": "pass",
                "manifest": {
                    "manifestSha256": kwargs["expected_manifest_sha256"],
                    "manifestBytes": len((root / Terminal.MANIFEST_NAME).read_bytes()),
                },
            }

    monkeypatch.setattr(srv5_harness, "_terminal_module", lambda: Terminal)
    current = {"campaign": "campaign-1"}
    remote = {"verdict": "pass"}
    assert srv5_harness.terminal_validate(
        root, {}, current, remote, seal=True)["verdict"] == "pass"
    sealed = (root / Terminal.MANIFEST_NAME).read_bytes()
    anchor = hashlib.sha256(sealed).hexdigest()
    assert srv5_harness.terminal_validate(
        root, {}, current, remote, seal=False,
        expected_manifest_sha256=anchor)["verdict"] == "pass"
    assert calls == [
        "seal",
        ("validate", {"expected_manifest_sha256": anchor, "require_fresh_remote": True}),
        ("validate", {"expected_manifest_sha256": anchor, "require_fresh_remote": False}),
    ]
    assert (root / Terminal.MANIFEST_NAME).read_bytes() == sealed


def test_external_manifest_seal_is_written_once_outside_evidence_root(tmp_path: Path):
    root = tmp_path / "campaign-1"
    root.mkdir()
    owner = {
        "campaign": "campaign-1", "target": "fb14srv5",
        "frameworkCommit": "a" * 40, "descriptorId": "descriptor",
        "descriptorSha256": "b" * 64,
    }
    report = {
        "verdict": "pass",
        "manifest": {"manifestSha256": "c" * 64, "manifestBytes": 123},
    }
    path, record = srv5_harness.persist_manifest_seal(root, owner=owner, report=report)
    assert path.parent == root.parent
    assert path.parent != root
    assert json.loads(path.read_text()) == record
    assert record["manifestSha256"] == "c" * 64
    with pytest.raises(RuntimeError, match="already exists"):
        srv5_harness.persist_manifest_seal(root, owner=owner, report=report)


def test_abort_program_is_exactly_scoped_and_owner_is_checked_before_mutation(monkeypatch):
    assert "cleanup-only safety carveout" in (srv5_harness.abort_owned.__doc__ or "")
    rendered = srv5_harness.REMOTE_ABORT.decode()
    assert "kill-server" not in rendered
    assert "system prune" not in rendered
    assert "label=com.docker.compose.project=" in rendered
    assert "os.killpg" in rendered
    assert "live process does not match the owned campaign group" in rendered
    assert 'type(process.get("schemaVersion")) is not int' in rendered
    calls = []
    monkeypatch.setattr(srv5_harness, "read_owner",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("mismatched owner")))
    monkeypatch.setattr(srv5_harness, "ssh", lambda *args, **kwargs: calls.append((args, kwargs)))
    with pytest.raises(RuntimeError):
        srv5_harness.abort_owned("fb14srv5", "campaign-1")
    assert calls == []


@pytest.mark.parametrize("version", [True, False, 1.0, 2.0])
def test_owner_schema_version_requires_an_exact_integer(version):
    descriptor = srv5_harness.load_descriptor()
    owner = owner_fixture(descriptor)
    owner["schemaVersion"] = version
    with pytest.raises(RuntimeError, match="schemaVersion"):
        srv5_harness.validate_owner(
            owner, target="fb14srv5", campaign="campaign-1", descriptor=descriptor,
        )
