#!/usr/bin/env python3
"""Descriptor-bound TeaStore launch, monitoring, fetch, abort, and validation."""
from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DESCRIPTOR = ROOT / "pipelines/campaigns/teastore-performance-diagnostic-smoke.json"
CANDIDATE_DESCRIPTOR = ROOT / "pipelines/campaigns/teastore-candidate-pilot-sys-v1.json"
DIAGNOSTIC_DESCRIPTOR_SHA256 = {
    "teastore-performance-diagnostic-smoke":
        "3e3372d32d9df66bb8b75a6870401cc76525e6510d108d928d8edf27f17337c2",
    "teastore-performance-effect-diagnostic-smoke":
        "5ee65f7ed8c62030b31e48d771d7ee9482172e119e9e9b03802a6cd87340cc7c",
}
SAFE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SSH_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REMOTE_RUNS = "/home/stig/observability-placement-runs"
REMOTE_RESULTS = "/home/stig/observability-placement-results"
LOCAL_PREFLIGHTS = ROOT / ".local/preflight"
HOST_POLICY_PATH = ROOT / "modules/teastore/deployment/srv5.yaml"
HOST_LEASE_PATH = f"{REMOTE_RUNS}/.teastore-performance.lock"
RESOURCE_CLASSES = (
    "owned-current", "owned-legacy", "shared-approved", "foreign", "unknown",
)
SUT_REFERENCE_COMMIT = "34b37f7e7be433ce72d5f9455e66922a13116749"
REQUIRED_PORTS = (3306, 5672, 8080, 8082, 15672)
POSTURES = frozenset({"none", "selected", "full"})
SELECTIONS = {
    "auth": "modules/teastore/activation/auth-selection.json",
    "fault-qualification": "modules/teastore/goals/fault-qualification.json",
}
FAULTS = frozenset({"none", "auth-freeze", "persistence-crash"})
EVIDENCE_LABELS = frozenset({"smoke-validation"})
DEADLINE_CLEANUP_RESERVE_SECONDS = 300
DEADLINE_TERM_GRACE_SECONDS = 10
DEADLINE_KILL_GRACE_SECONDS = 5
DEADLINE_COMPOSE_TIMEOUT_SECONDS = 120
DEADLINE_QUERY_TIMEOUT_SECONDS = 5
DEADLINE_LEASE_FINALIZER_SECONDS = 30


def _json_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _invalid_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _loads_strict(value: str | bytes) -> Any:
    return json.loads(
        value, object_pairs_hook=_json_no_duplicates,
        parse_constant=_invalid_json_constant,
    )


def checked_name(value: str) -> str:
    if not SAFE.fullmatch(value):
        raise ValueError(f"unsafe identifier: {value!r}")
    return value


def checked_target(value: str) -> str:
    if not SSH_TARGET.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"unsafe SSH target: {value!r}")
    return value


def checked_postures(value: str) -> tuple[str, ...]:
    postures = tuple(value.split(","))
    if not postures or len(set(postures)) != len(postures) or any(item not in POSTURES for item in postures):
        raise ValueError(f"postures must be unique values from {sorted(POSTURES)}")
    return postures


def validate_campaign_parameters(*, blocks: int, warmup: int, duration: int, rate: float,
                                 concurrency: int, postures: str, fault: str,
                                 fault_at: int, outage: int, selection: str) -> tuple[str, ...]:
    parsed = checked_postures(postures)
    if blocks <= 0 or warmup < 0 or duration <= 0 or concurrency <= 0:
        raise ValueError("blocks, duration, and concurrency must be positive; warmup must be non-negative")
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("rate must be finite and positive")
    if selection not in SELECTIONS:
        raise ValueError(f"selection must be one of {sorted(SELECTIONS)}")
    if fault not in FAULTS:
        raise ValueError(f"fault must be one of {sorted(FAULTS)}")
    if fault == "none":
        if fault_at != 240 or outage != 30:
            raise ValueError("fault timing must remain at defaults when no fault is requested")
    elif fault_at < 0 or outage <= 0 or fault_at + outage >= duration:
        raise ValueError("fault and recovery must fit strictly inside the measurement window")
    return parsed


def execute(args: list[str], *, data: bytes | None = None, check: bool = True,
            cwd: Path | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(args, input=data, capture_output=True, check=False, cwd=cwd)
    if check and result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {args}\n"
            + result.stderr.decode(errors="replace")
        )
    return result


def ssh(target: str, remote: str, *, data: bytes | None = None,
        check: bool = True) -> subprocess.CompletedProcess:
    target = checked_target(target)
    return execute(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "--", target, remote],
        data=data, check=check,
    )


def _exact_keys(value: object, expected: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{location} must be an object")
    actual = set(value)
    if actual != expected:
        raise ValueError(f"{location} fields differ: missing={sorted(expected - actual)}, unknown={sorted(actual - expected)}")
    return value


def _integer(value: object, location: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{location} must be an integer >= {minimum}")
    return value


def _number(value: object, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{location} must be a finite positive number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{location} must be a finite positive number")
    return number


def load_descriptor(path: Path = DEFAULT_DESCRIPTOR) -> dict[str, Any]:
    try:
        content = path.read_bytes()
        document = _loads_strict(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid campaign descriptor {path}: {exc}") from exc
    root = _exact_keys(document, {
        "schemaVersion", "id", "evidenceLabel", "module", "target", "executor",
        "source", "runner", "design", "collector", "validation", "promotion",
    }, "descriptor")
    if root["schemaVersion"] != 1:
        raise ValueError("descriptor.schemaVersion must be 1")
    checked_name(root["id"])
    content_sha256 = hashlib.sha256(content).hexdigest()
    reviewed_sha256 = DIAGNOSTIC_DESCRIPTOR_SHA256.get(root["id"])
    if reviewed_sha256 is None:
        raise ValueError("descriptor ID is not in the reviewed diagnostic allowlist")
    if content_sha256 != reviewed_sha256:
        raise ValueError("diagnostic bytes differ from the separately reviewed descriptor")
    if root["evidenceLabel"] not in EVIDENCE_LABELS:
        raise ValueError(f"descriptor.evidenceLabel must be one of {sorted(EVIDENCE_LABELS)}")
    if root["module"] != "teastore" or root["executor"] != "ssh-compose":
        raise ValueError("descriptor must bind the TeaStore ssh-compose executor")
    checked_target(root["target"])
    if root["runner"] != "modules/teastore/execution/performance_campaign.py":
        raise ValueError("descriptor.runner differs from the only supported runner")
    source = _exact_keys(
        root["source"], {"frameworkCommit", "sutReferenceCommit"}, "descriptor.source")
    if source != {
        "frameworkCommit": "required-at-materialization",
        "sutReferenceCommit": SUT_REFERENCE_COMMIT,
    }:
        raise ValueError("descriptor source binding differs from the pinned TeaStore source")
    design = _exact_keys(root["design"], {
        "blocks", "seed", "postures", "warmupSeconds", "measurementSeconds", "workload",
        "fault", "selectionId", "coldStartEachRun",
    }, "descriptor.design")
    blocks = _integer(design["blocks"], "descriptor.design.blocks", minimum=1)
    seed = _integer(design["seed"], "descriptor.design.seed")
    warmup = _integer(design["warmupSeconds"], "descriptor.design.warmupSeconds")
    duration = _integer(design["measurementSeconds"], "descriptor.design.measurementSeconds", minimum=1)
    postures_value = design["postures"]
    if not isinstance(postures_value, list) or not postures_value:
        raise ValueError("descriptor.design.postures must be a non-empty list")
    posture_contracts = {"full": "modules/teastore/postures/native-full.yaml"}
    postures: list[str] = []
    for index, value in enumerate(postures_value):
        row = _exact_keys(value, {"id", "contract"}, f"descriptor.design.postures[{index}]")
        if row.get("id") not in posture_contracts or row.get("contract") != posture_contracts[row["id"]]:
            raise ValueError(f"descriptor.design.postures[{index}] is not a supported bound posture")
        postures.append(row["id"])
    if len(postures) != len(set(postures)):
        raise ValueError("descriptor posture IDs must be unique")
    workload = _exact_keys(design["workload"], {
        "path", "kind", "journeysPerSecond", "concurrency",
    }, "descriptor.design.workload")
    if workload["path"] != "modules/teastore/workload/fixed_load.py" or workload["kind"] != "fixed-open-loop":
        raise ValueError("descriptor workload differs from the supported fixed-load runner")
    rate = _number(workload["journeysPerSecond"], "descriptor.design.workload.journeysPerSecond")
    concurrency = _integer(workload["concurrency"], "descriptor.design.workload.concurrency", minimum=1)
    fault_value = design["fault"]
    if not isinstance(fault_value, dict):
        raise ValueError("descriptor.design.fault must be an object")
    fault = fault_value.get("scenario")
    if fault == "none":
        fault_row = _exact_keys(
            fault_value, {"scenario"}, "descriptor.design.fault")
        fault_at, outage = 240, 30
    elif fault in {"auth-freeze", "persistence-crash"}:
        fault_row = _exact_keys(
            fault_value, {"scenario", "faultAtSeconds", "outageSeconds"},
            "descriptor.design.fault",
        )
        fault_at = _integer(
            fault_row["faultAtSeconds"], "descriptor.design.fault.faultAtSeconds")
        outage = _integer(
            fault_row["outageSeconds"], "descriptor.design.fault.outageSeconds", minimum=1)
    else:
        raise ValueError("descriptor.design.fault scenario is unsupported")
    if design["selectionId"] not in SELECTIONS:
        raise ValueError(f"unknown descriptor selectionId: {design['selectionId']}")
    if fault != "none" and design["selectionId"] != "fault-qualification":
        raise ValueError("effect diagnostics must bind the fault-qualification selection")
    if design["coldStartEachRun"] is not True:
        raise ValueError("descriptor must require a cold start for every run")
    if fault != "none":
        reviewed_effect = (
            "teastore-performance-effect-diagnostic-smoke",
            1,
            20260829,
            ("full",),
            120,
            600,
            0.15,
            8,
            "persistence-crash",
            240,
            30,
            "fault-qualification",
        )
        observed_effect = (
            root["id"], blocks, seed, tuple(postures), warmup, duration, rate,
            concurrency, fault, fault_at, outage, design["selectionId"],
        )
        if observed_effect != reviewed_effect:
            raise ValueError(
                "effect diagnostics must match the separately reviewed one-run "
                "persistence-crash design"
            )
    collector = _exact_keys(root["collector"], {
        "path", "durationSeconds", "inactivityTimeoutSeconds", "queue", "requiredConsumers",
    }, "descriptor.collector")
    if collector != {
        "path": "modules/teastore/collectors/kieker_native.py",
        "durationSeconds": duration + 30,
        "inactivityTimeoutSeconds": 10,
        "queue": "kieker",
        "requiredConsumers": 1,
    }:
        raise ValueError("descriptor collector does not match the runner's native-Kieker contract")
    validation = root["validation"]
    required_validation = {
        "immutable-descriptor-binding", "performance-receipt", "native-kieker-contract",
        "queue-purge-recorded", "exclusive-consumer", "complete-shutdown", "content-manifest",
        "runtime-image-provenance", "queue-proof-replay", "child-process-termination",
        "sanitized-host-inventory", "retained-60s-preflight",
        "host-wide-execution-lease", "external-manifest-anchor",
        "deadline-enforced-owned-cleanup", "runtime-admission-replay",
    }
    if fault != "none":
        required_validation.update({"fault-intervention-proof", "cost-effect-separation"})
    if not isinstance(validation, list) or len(validation) != len(set(validation)) or set(validation) != required_validation:
        raise ValueError("descriptor validation set is incomplete or duplicated")
    promotion = _exact_keys(root["promotion"], {"canonical", "reason"}, "descriptor.promotion")
    if promotion["canonical"] is not False or not isinstance(promotion["reason"], str) or not promotion["reason"].strip():
        raise ValueError("diagnostic descriptor must explicitly prohibit canonical promotion")
    parsed = validate_campaign_parameters(
        blocks=blocks, warmup=warmup, duration=duration, rate=rate,
        concurrency=concurrency, postures=",".join(postures), fault=fault,
        fault_at=fault_at, outage=outage, selection=design["selectionId"],
    )
    return {
        "path": path.resolve(), "content": content, "document": document,
        "sha256": content_sha256, "id": root["id"],
        "evidenceLabel": root["evidenceLabel"], "target": root["target"],
        "blocks": blocks, "seed": seed, "postures": parsed, "warmup": warmup,
        "duration": duration, "rate": rate, "concurrency": concurrency,
        "fault": fault, "faultAt": fault_at, "outage": outage,
        "selection": design["selectionId"],
    }


def _candidate_pilot_module():
    path = ROOT / "modules/teastore/execution/candidate_pilot.py"
    spec = importlib.util.spec_from_file_location("teastore_candidate_pilot", path)
    if not spec or not spec.loader:
        raise RuntimeError("unable to load TeaStore candidate-pilot admission validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_runtime_admission(path: Path, descriptor: dict[str, Any]) -> dict[str, Any]:
    """Replay an affirmative diagnostic runtime admission and its remaining window.

    A ``time-window-feasibility`` object is deliberately non-authorizing even
    when its arithmetic is feasible.  The current construction epoch produces
    only that object, so this loader must fail before preflight or any remote
    mutation until a separately gated affirmative admission contract exists.
    """
    module = _candidate_pilot_module()
    try:
        content = path.read_bytes()
        receipt = module.strict_json_loads(content.decode("utf-8", errors="strict"))
        frozen = module.strict_json_file(CANDIDATE_DESCRIPTOR)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"invalid runtime admission {path}: {exc}") from exc
    if not isinstance(receipt, dict):
        raise ValueError("runtime admission must be one JSON object")
    if (
        receipt.get("kind") != "runtime-admission"
        or receipt.get("admitted") is not True
        or receipt.get("runtimeAuthorized") is not True
    ):
        raise ValueError(
            "non-authorizing time-window feasibility receipt does not authorize runtime"
        )
    try:
        expected = module.admit_runtime(
            frozen,
            mode=receipt["mode"],
            evidence_label=receipt["evidenceLabel"],
            now=receipt["now"],
            authorization_deadline=receipt["authorizationDeadline"],
            time_budget_seconds=receipt["suppliedTimeBudgetSeconds"],
            diagnostic_run_count=receipt["runCount"],
            diagnostic_warmup_seconds=receipt["warmupSeconds"],
            diagnostic_measurement_seconds=receipt["measurementSeconds"],
            lifecycle_allowance_seconds=receipt["lifecycleAllowanceSeconds"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"runtime admission cannot be replayed: {exc}") from exc
    if receipt != expected:
        raise ValueError("runtime admission differs from independently replayed fields")
    expected_runs = descriptor["blocks"] * len(descriptor["postures"])
    if (receipt["mode"] != "diagnostic"
            or receipt["evidenceLabel"] != descriptor["evidenceLabel"]
            or receipt["runCount"] != expected_runs
            or receipt["warmupSeconds"] != descriptor["warmup"]
            or receipt["measurementSeconds"] != descriptor["duration"]):
        raise ValueError("runtime admission differs from the bound diagnostic descriptor")
    deadline = datetime.datetime.fromisoformat(
        receipt["authorizationDeadline"].replace("Z", "+00:00"))
    remaining = math.floor(
        (deadline - datetime.datetime.now(datetime.timezone.utc)).total_seconds())
    required = receipt["requiredAuthorizationSeconds"]
    if remaining < required:
        raise ValueError(
            f"runtime admission has only {remaining}s remaining; {required}s are required")
    deadline_epoch = math.floor(deadline.timestamp())
    stop_epoch = deadline_epoch - DEADLINE_CLEANUP_RESERVE_SECONDS
    if stop_epoch <= int(time.time()):
        raise ValueError("runtime admission leaves no reserved cleanup interval")
    return {
        "path": path.resolve(),
        "content": content,
        "sha256": hashlib.sha256(content).hexdigest(),
        "receipt": receipt,
        "deadlineEpoch": deadline_epoch,
        "stopEpoch": stop_epoch,
        "cleanupReserveSeconds": DEADLINE_CLEANUP_RESERVE_SECONDS,
    }


def _strict_json(payload: bytes, protocol: str) -> dict[str, Any]:
    try:
        rendered = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"invalid UTF-8 in remote {protocol} response") from exc
    lines = [line for line in rendered.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError(f"remote {protocol} response must contain exactly one record")
    try:
        value = _loads_strict(lines[0])
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"invalid remote {protocol} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"remote {protocol} response must be an object")
    return value


def _strict_local_json_document(payload: bytes, document: str) -> dict[str, Any]:
    """Parse one complete retained JSON document without weakening wire JSON.

    Local evidence is intentionally pretty-printed, unlike the one-record SSH
    protocols handled by :func:`_strict_json`.  ``json.loads`` consumes exactly
    one value and rejects any non-whitespace suffix; the shared hooks additionally
    reject duplicate keys and non-finite numbers.
    """
    try:
        rendered = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"invalid UTF-8 in {document}") from exc
    try:
        value = _loads_strict(rendered)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"invalid {document} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{document} must contain exactly one JSON object")
    return value


# The active inventory program deliberately discards raw command output before
# crossing the SSH boundary.  Raw Docker inspection, daemon metadata, events,
# and the host process table can contain environment values, registry metadata,
# or command-line credentials.  Only normalized fields needed by the hygiene
# decision and replayable stream digests leave the host.
REMOTE_INVENTORY = r'''
import base64, datetime, glob, hashlib, json, os, pathlib, platform, re, stat as stat_module, subprocess, sys, time

target, campaign, project, session, result_root, release_path, policy_b64, policy_sha = sys.argv[1:]
if release_path == "-": release_path = ""
policy = json.loads(base64.urlsafe_b64decode(policy_b64.encode()).decode())
required_ports = (3306, 5672, 8080, 8082, 15672)
resource_classes = ("owned-current", "owned-legacy", "shared-approved", "foreign", "unknown")
compose_label_keys = (
    "com.docker.compose.project", "com.docker.compose.project.working_dir",
    "com.docker.compose.project.config_files", "com.docker.compose.service",
)
raw_queries = {}
parse_errors = []

def digest_text(value):
    encoded = value.encode(errors="replace")
    return {"sha256": hashlib.sha256(encoded).hexdigest(), "bytes": len(encoded),
            "lineCount": len(value.splitlines())}

def query(name, argv, timeout=20):
    try:
        result = subprocess.run(argv, text=True, capture_output=True, check=False, timeout=timeout)
        row = {"command": argv, "returnCode": result.returncode,
               "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        row = {"command": argv, "returnCode": 124, "stdout": stdout,
               "stderr": stderr + "\nquery timed out"}
    except OSError as exc:
        row = {"command": argv, "returnCode": 127, "stdout": "", "stderr": str(exc)}
    raw_queries[name] = row
    return row

def query_proof(row):
    return {"command": row["command"], "returnCode": row["returnCode"],
            "stdout": digest_text(row["stdout"]), "stderr": digest_text(row["stderr"])}

def synthetic_query(name, argv, stdout="[]"):
    row = {"command": argv, "returnCode": 0, "stdout": stdout, "stderr": ""}
    raw_queries[name] = row
    return row

def lines(row):
    return [line for line in row["stdout"].splitlines() if line]

def json_list(name, row):
    if row["returnCode"] != 0:
        parse_errors.append(name + ": command failed")
        return []
    try:
        value = json.loads(row["stdout"] or "[]")
        if not isinstance(value, list): raise ValueError("not-list")
        return value
    except (TypeError, ValueError):
        parse_errors.append(name + ": invalid JSON")
        return []

def compose_rows(row):
    if row["returnCode"] != 0:
        parse_errors.append("composeProjects: command failed")
        return []
    text = row["stdout"].strip()
    if not text: return []
    try:
        value = json.loads(text)
        if isinstance(value, dict): value = [value]
        if not isinstance(value, list): raise ValueError("not-list")
        return value
    except ValueError:
        try:
            value = [json.loads(line) for line in text.splitlines() if line]
            if not all(isinstance(item, dict) for item in value): raise ValueError("not-objects")
            return value
        except ValueError:
            parse_errors.append("composeProjects: invalid JSON")
            return []

def safe_labels(value):
    if not isinstance(value, dict): return {key: "" for key in compose_label_keys}
    return {key: (value.get(key) if isinstance(value.get(key), str) else "")
            for key in compose_label_keys}

def config_paths(raw):
    return sorted(path.strip() for path in raw.split(",") if path.strip())

def legacy_match(compose_project, working_dir, config_files):
    for allowed in policy["allowedLegacyProjects"]:
        if compose_project != allowed["project"] or working_dir != allowed["workingDirectory"]:
            continue
        allowed_paths = {os.path.join(working_dir, item) for item in allowed["configFiles"]}
        observed = set(config_paths(config_files))
        if observed and observed.issubset(allowed_paths): return True
    return False

def owner_valid():
    path = pathlib.Path(result_root, "harness-owner.json")
    if not path.is_file(): return False
    try:
        owner = json.loads(path.read_text())
        return (isinstance(owner, dict) and owner.get("schemaVersion") == 1 and
                owner.get("campaign") == campaign and owner.get("target") == target and
                owner.get("session") == session and owner.get("composeProject") == project and
                owner.get("resultRoot") == result_root and
                (not release_path or owner.get("release") == release_path))
    except (OSError, TypeError, ValueError):
        return False

has_current_owner = owner_valid()

def classify(compose_project, working_dir, config_files, builtin=False):
    if builtin:
        return "shared-approved", "Docker built-in host infrastructure"
    if compose_project == project:
        if has_current_owner:
            return "owned-current", "exact campaign namespace with identity-bound owner receipt"
        return "unknown", "current namespace has no identity-bound owner receipt"
    if legacy_match(compose_project, working_dir, config_files):
        return "owned-legacy", "exact project, working directory, and config path match host policy"
    if compose_project:
        return "foreign", "Compose project is not approved by host policy"
    return "unknown", "resource has no attributable Compose ownership"

def classification_fields(compose_project, working_dir, config_files, builtin=False):
    label, reason = classify(compose_project, working_dir, config_files, builtin)
    return {"classification": label, "classificationReason": reason}

def stopped_legacy_container(row):
    state = row["state"]; restart = row["restartPolicy"]
    return (row["classification"] == "owned-legacy" and state["status"] == "exited"
            and not any(state[key] for key in ("running", "paused", "restarting", "dead"))
            and restart["name"] in policy["allowedStoppedRestartPolicies"])

def hash_value(value):
    return hashlib.sha256(str(value).encode()).hexdigest()

def tree_pass(root):
    base = pathlib.Path(root)
    dialect = "srv5-tree-metadata-v1"
    algorithm = "sha256"
    chunk_size = 4096
    chunk_hasher = hashlib.sha256()
    chunk_entries = 0
    chunk_sha256 = []
    errors = []
    kind_counts = {"directory": 0, "file": 0, "symlink": 0, "other": 0}
    entry_count = 0
    total_file_bytes = 0
    oldest_mtime_ns = None
    newest_mtime_ns = None
    root_kind = "missing"

    def error(operation, path, exc):
        errors.append({"operation": operation, "pathSha256": hash_value(str(path)),
                       "errno": int(getattr(exc, "errno", -1) or -1)})

    def stat_kind(mode):
        if stat_module.S_ISDIR(mode): return "directory"
        if stat_module.S_ISREG(mode): return "file"
        if stat_module.S_ISLNK(mode): return "symlink"
        return "other"

    try:
        os.lstat(str(base))
        exists = True
    except FileNotFoundError:
        exists = False
    except OSError as exc:
        exists = True
        root_kind = "unreadable"
        error("root-lstat", base, exc)

    stack = [base] if exists and root_kind != "unreadable" else []
    while stack:
        path = stack.pop()
        try:
            before = os.lstat(str(path))
        except OSError as exc:
            error("lstat", path, exc)
            continue
        kind = stat_kind(before.st_mode)
        if path == base: root_kind = kind
        relative = "." if path == base else path.relative_to(base).as_posix()
        target_sha = ""
        if kind == "symlink":
            try:
                target_sha = hash_value(os.readlink(str(path)))
            except OSError as exc:
                error("readlink", path, exc)
        record = {
            "path": relative, "kind": kind, "mode": before.st_mode,
            "uid": before.st_uid, "gid": before.st_gid, "size": before.st_size,
            "mtimeNs": before.st_mtime_ns, "ctimeNs": before.st_ctime_ns,
            "device": before.st_dev, "inode": before.st_ino, "nlink": before.st_nlink,
            "symlinkTargetSha256": target_sha,
        }
        chunk_hasher.update(json.dumps(record, sort_keys=True,
                            separators=(",", ":")).encode() + b"\n")
        chunk_entries += 1
        if chunk_entries == chunk_size:
            chunk_sha256.append(chunk_hasher.hexdigest())
            chunk_hasher = hashlib.sha256()
            chunk_entries = 0
        entry_count += 1
        kind_counts[kind] += 1
        if kind == "file": total_file_bytes += before.st_size
        oldest_mtime_ns = before.st_mtime_ns if oldest_mtime_ns is None else min(oldest_mtime_ns, before.st_mtime_ns)
        newest_mtime_ns = before.st_mtime_ns if newest_mtime_ns is None else max(newest_mtime_ns, before.st_mtime_ns)
        if kind != "directory": continue
        try:
            with os.scandir(str(path)) as scan:
                children = sorted((pathlib.Path(item.path) for item in scan),
                                  key=lambda item: item.name)
        except OSError as exc:
            error("scandir", path, exc)
            continue
        stack.extend(reversed(children))
        try:
            after = os.lstat(str(path))
            before_signature = (before.st_mode, before.st_uid, before.st_gid, before.st_size,
                                before.st_mtime_ns, before.st_ctime_ns, before.st_dev,
                                before.st_ino, before.st_nlink)
            after_signature = (after.st_mode, after.st_uid, after.st_gid, after.st_size,
                               after.st_mtime_ns, after.st_ctime_ns, after.st_dev,
                               after.st_ino, after.st_nlink)
            if before_signature != after_signature:
                error("directory-changed-during-scan", path, OSError(0, "changed"))
        except OSError as exc:
            error("directory-restat", path, exc)

    errors.sort(key=lambda item: (item["pathSha256"], item["operation"], item["errno"]))
    if chunk_entries:
        chunk_sha256.append(chunk_hasher.hexdigest())
    error_sha = hashlib.sha256(json.dumps(errors, sort_keys=True,
                               separators=(",", ":")).encode()).hexdigest()
    rollup = {"algorithm": algorithm, "chunkSize": chunk_size,
              "entryCount": entry_count, "chunks": chunk_sha256}
    metadata_sha = hashlib.sha256(json.dumps(
        rollup, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    summary = {
        "dialect": dialect, "algorithm": algorithm, "complete": len(errors) == 0,
        "exists": exists, "rootKind": root_kind, "entryCount": entry_count,
        "kindCounts": kind_counts, "totalFileBytes": total_file_bytes,
        "oldestMtimeNs": oldest_mtime_ns, "newestMtimeNs": newest_mtime_ns,
        "metadataSha256": metadata_sha, "chunkSize": chunk_size,
        "chunkCount": len(chunk_sha256), "chunkSha256": chunk_sha256,
        "errorCount": len(errors), "errorSha256": error_sha,
    }
    summary["passSha256"] = hashlib.sha256(json.dumps(
        summary, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return summary

def tree_snapshot(root):
    first = tree_pass(root)
    second = tree_pass(root)
    stable = first == second and second["complete"]
    return {
        "dialect": second["dialect"], "algorithm": second["algorithm"],
        "complete": second["complete"],
        "root": root, "exists": second["exists"], "rootKind": second["rootKind"],
        "entryCount": second["entryCount"], "kindCounts": second["kindCounts"],
        "totalFileBytes": second["totalFileBytes"],
        "oldestMtimeNs": second["oldestMtimeNs"], "newestMtimeNs": second["newestMtimeNs"],
        "metadataSha256": second["metadataSha256"], "chunkSize": second["chunkSize"],
        "chunkCount": second["chunkCount"], "chunkSha256": second["chunkSha256"],
        "errorCount": second["errorCount"],
        "errorSha256": second["errorSha256"], "firstPassSha256": first["passSha256"],
        "secondPassSha256": second["passSha256"], "stable": stable,
    }

def open_writers(roots):
    normalized = [os.path.realpath(root) for root in roots]
    found = []
    for fd in glob.glob("/proc/[0-9]*/fd/[0-9]*"):
        try:
            parts = fd.split("/"); pid = int(parts[2]); fd_number = int(parts[-1])
            flags_line = next(line for line in pathlib.Path(
                "/proc", str(pid), "fdinfo", str(fd_number)).read_text().splitlines()
                if line.startswith("flags:"))
            if int(flags_line.split()[1], 8) & os.O_ACCMODE == os.O_RDONLY: continue
            resolved = os.path.realpath(fd)
            if not any(resolved == root or resolved.startswith(root + os.sep) for root in normalized): continue
            command = pathlib.Path("/proc", str(pid), "cmdline").read_bytes()
            found.append({"pid": pid, "fd": fd_number, "pathSha256": hash_value(resolved),
                          "commandSha256": hashlib.sha256(command).hexdigest()})
        except (OSError, StopIteration, ValueError):
            continue
    return sorted(found, key=lambda item: (item["pid"], item["fd"]))

def meminfo():
    values = {}
    try:
        for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
            key, raw = line.split(":", 1); fields = raw.split()
            if fields and fields[0].isdigit(): values[key] = int(fields[0])
    except (OSError, ValueError): pass
    return {key: values.get(key, 0) for key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree")}

def boot_epoch():
    try:
        for line in pathlib.Path("/proc/stat").read_text().splitlines():
            if line.startswith("btime "): return int(line.split()[1])
    except (OSError, ValueError): pass
    return 0

# Exact campaign namespace queries are retained only as typed identifiers.
label = "label=com.docker.compose.project=" + project
project_query_names = {}
for kind, argv in (
    ("containers", ["docker", "ps", "-aq", "--no-trunc", "--filter", label]),
    ("networks", ["docker", "network", "ls", "-q", "--no-trunc", "--filter", label]),
    ("volumes", ["docker", "volume", "ls", "-q", "--filter", label]),
):
    row = query("project." + kind, argv); project_query_names[kind] = sorted(lines(row))

container_ids_row = query("containers.list", ["docker", "ps", "-aq", "--no-trunc"])
container_ids = sorted(lines(container_ids_row))
container_inspect_row = (query("containers.inspect", ["docker", "inspect"] + container_ids)
                         if container_ids else synthetic_query("containers.inspect", ["docker", "inspect"]))
container_raw = json_list("containers", container_inspect_row)
containers, image_ids = [], set()
for item in container_raw:
    if not isinstance(item, dict): parse_errors.append("containers: non-object row"); continue
    config = item.get("Config") if isinstance(item.get("Config"), dict) else {}
    state = item.get("State") if isinstance(item.get("State"), dict) else {}
    host = item.get("HostConfig") if isinstance(item.get("HostConfig"), dict) else {}
    network_settings = item.get("NetworkSettings") if isinstance(item.get("NetworkSettings"), dict) else {}
    labels = safe_labels(config.get("Labels")); compose_project = labels[compose_label_keys[0]]
    working_dir = labels[compose_label_keys[1]]; configs = labels[compose_label_keys[2]]
    image_id = item.get("Image") if isinstance(item.get("Image"), str) else ""
    if image_id: image_ids.add(image_id)
    port_rows = []
    for key, bindings in sorted((network_settings.get("Ports") or {}).items()):
        match = re.fullmatch(r"(\d+)/(tcp|udp|sctp)", str(key))
        if not match: continue
        host_ports = []
        for binding in bindings or []:
            if isinstance(binding, dict) and str(binding.get("HostPort", "")).isdigit():
                host_ports.append(int(binding["HostPort"]))
        port_rows.append({"containerPort": int(match.group(1)), "protocol": match.group(2),
                          "hostPorts": sorted(host_ports)})
    mount_rows = []
    for mount in item.get("Mounts") or []:
        if not isinstance(mount, dict): continue
        mount_rows.append({"type": str(mount.get("Type") or ""),
                           "volumeName": str(mount.get("Name") or ""),
                           "sourceSha256": hash_value(mount.get("Source") or ""),
                           "destination": str(mount.get("Destination") or ""),
                           "readOnly": not bool(mount.get("RW"))})
    network_rows = []
    for name, network in sorted((network_settings.get("Networks") or {}).items()):
        network = network if isinstance(network, dict) else {}
        network_rows.append({"name": name, "networkId": str(network.get("NetworkID") or "")})
    health = state.get("Health") if isinstance(state.get("Health"), dict) else {}
    restart = host.get("RestartPolicy") if isinstance(host.get("RestartPolicy"), dict) else {}
    row = {
        "id": str(item.get("Id") or ""), "name": str(item.get("Name") or "").lstrip("/"),
        "created": str(item.get("Created") or ""), "declaredImage": str(config.get("Image") or ""),
        "runtimeImageId": image_id, "composeProject": compose_project,
        "composeWorkingDirectory": working_dir, "composeConfigFiles": config_paths(configs),
        "composeService": labels[compose_label_keys[3]],
        "state": {"status": str(state.get("Status") or ""), "running": state.get("Running") is True,
                  "paused": state.get("Paused") is True, "restarting": state.get("Restarting") is True,
                  "oomKilled": state.get("OOMKilled") is True, "dead": state.get("Dead") is True,
                  "exitCode": int(state.get("ExitCode") or 0), "startedAt": str(state.get("StartedAt") or ""),
                  "finishedAt": str(state.get("FinishedAt") or ""),
                  "healthStatus": str(health.get("Status") or ""),
                  "healthFailingStreak": int(health.get("FailingStreak") or 0)},
        "restartCount": int(item.get("RestartCount") or 0),
        "restartPolicy": {"name": str(restart.get("Name") or "no"),
                          "maximumRetryCount": int(restart.get("MaximumRetryCount") or 0)},
        "ports": port_rows,
        "mounts": sorted(mount_rows, key=lambda value: (value["destination"], value["volumeName"])),
        "networks": network_rows,
        "limits": {"memory": int(host.get("Memory") or 0), "memorySwap": int(host.get("MemorySwap") or 0),
                   "nanoCpus": int(host.get("NanoCpus") or 0), "cpuQuota": int(host.get("CpuQuota") or 0),
                   "cpusetCpus": str(host.get("CpusetCpus") or ""), "pidsLimit": int(host.get("PidsLimit") or 0)},
    }
    row.update(classification_fields(compose_project, working_dir, configs))
    if row["classification"] == "owned-legacy" and not stopped_legacy_container(row):
        row.update({"classification": "foreign",
                    "classificationReason": "allow-listed legacy container is not safely stopped under an approved restart policy"})
    containers.append(row)
containers.sort(key=lambda item: item["id"])

sorted_image_ids = sorted(image_ids)
image_inspect_row = (query("images.inspect", ["docker", "image", "inspect"] + sorted_image_ids)
                     if image_ids else synthetic_query("images.inspect", ["docker", "image", "inspect"]))
images = []
for item in json_list("images", image_inspect_row):
    if isinstance(item, dict):
        images.append({"id": str(item.get("Id") or ""),
                       "repoTags": sorted(str(value) for value in (item.get("RepoTags") or [])),
                       "repoDigests": sorted(str(value) for value in (item.get("RepoDigests") or [])),
                       "created": str(item.get("Created") or ""), "size": int(item.get("Size") or 0)})
images.sort(key=lambda item: item["id"])

compose_raw = compose_rows(query("compose.projects", ["docker", "compose", "ls", "--all", "--format", "json"]))
compose_projects = []
for item in compose_raw:
    if not isinstance(item, dict): parse_errors.append("composeProjects: non-object row"); continue
    name = str(item.get("Name") or item.get("name") or "")
    config_files = str(item.get("ConfigFiles") or item.get("ConfigFiles") or "")
    paths = config_paths(config_files); working = os.path.dirname(paths[0]) if paths else ""
    running = any(row["composeProject"] == name and row["state"]["running"] for row in containers)
    row = {"name": name, "status": str(item.get("Status") or item.get("status") or ""),
           "configFiles": paths, "workingDirectory": working, "running": running}
    row.update(classification_fields(name, working, config_files))
    compose_projects.append(row)
compose_projects.sort(key=lambda item: item["name"])

network_ids_row = query("networks.list", ["docker", "network", "ls", "-q", "--no-trunc"])
network_ids = sorted(lines(network_ids_row))
network_inspect_row = (query("networks.inspect", ["docker", "network", "inspect"] + network_ids)
                       if network_ids else synthetic_query("networks.inspect", ["docker", "network", "inspect"]))
networks = []
for item in json_list("networks", network_inspect_row):
    if not isinstance(item, dict): parse_errors.append("networks: non-object row"); continue
    labels = safe_labels(item.get("Labels")); name = str(item.get("Name") or "")
    configs = labels[compose_label_keys[2]]; working = labels[compose_label_keys[1]]
    row = {"id": str(item.get("Id") or ""), "name": name, "driver": str(item.get("Driver") or ""),
           "scope": str(item.get("Scope") or ""), "internal": item.get("Internal") is True,
           "attachable": item.get("Attachable") is True, "composeProject": labels[compose_label_keys[0]],
           "composeWorkingDirectory": working, "composeConfigFiles": config_paths(configs),
           "containerIds": sorted(str(key) for key in (item.get("Containers") or {}).keys())}
    row.update(classification_fields(labels[compose_label_keys[0]], working, configs,
                                     builtin=name in {"bridge", "host", "none"}))
    inert_match = any(name == allowed["name"] and row["driver"] == allowed["driver"]
                      and row["scope"] == allowed["scope"]
                      for allowed in policy["allowedInertNetworks"])
    if (inert_match and not row["containerIds"] and row["composeProject"] != project
            and not name.startswith(project + "_")):
        row.update({"classification": "shared-approved",
                    "classificationReason": "exact policy-listed detached inert network preserved in place"})
    networks.append(row)
networks.sort(key=lambda item: item["id"])

volume_names_row = query("volumes.list", ["docker", "volume", "ls", "-q"])
volume_names = sorted(lines(volume_names_row))
volume_inspect_row = (query("volumes.inspect", ["docker", "volume", "inspect"] + volume_names)
                      if volume_names else synthetic_query("volumes.inspect", ["docker", "volume", "inspect"]))
volume_references = {}
for container in containers:
    for mount in container["mounts"]:
        if mount["type"] == "volume" and mount["volumeName"]:
            volume_references.setdefault(mount["volumeName"], []).append(container["id"])
volumes = []
for item in json_list("volumes", volume_inspect_row):
    if not isinstance(item, dict): parse_errors.append("volumes: non-object row"); continue
    labels = safe_labels(item.get("Labels")); name = str(item.get("Name") or "")
    configs = labels[compose_label_keys[2]]; working = labels[compose_label_keys[1]]
    row = {"name": name, "driver": str(item.get("Driver") or ""),
           "scope": str(item.get("Scope") or ""), "mountpointSha256": hash_value(item.get("Mountpoint") or ""),
           "composeProject": labels[compose_label_keys[0]], "composeWorkingDirectory": working,
           "composeConfigFiles": config_paths(configs), "referencedBy": sorted(volume_references.get(name, []))}
    row.update(classification_fields(labels[compose_label_keys[0]], working, configs))
    references = row["referencedBy"]
    container_by_id = {container["id"]: container for container in containers}
    if references and all(reference in container_by_id and stopped_legacy_container(
            container_by_id[reference]) for reference in references):
        row.update({"classification": "owned-legacy",
                    "classificationReason": "referenced only by exact safely stopped legacy containers"})
    elif (not references and policy["preserveUnreferencedVolumes"]
          and row["composeProject"] != project and not name.startswith(project + "_")):
        row.update({"classification": "shared-approved",
                    "classificationReason": "unreferenced inert volume preserved in place; capacity is gated separately"})
    volumes.append(row)
volumes.sort(key=lambda item: item["name"])

now_epoch = int(time.time())
event_row = query("docker.events", ["docker", "events", "--since", str(now_epoch - 3600),
                  "--until", str(now_epoch), "--format", "{{json .}}"], timeout=30)
events = []
if event_row["returnCode"] == 0:
    for line in lines(event_row):
        try:
            item = json.loads(line); actor = item.get("Actor") if isinstance(item.get("Actor"), dict) else {}
            attrs = actor.get("Attributes") if isinstance(actor.get("Attributes"), dict) else {}
            events.append({"type": str(item.get("Type") or ""), "action": str(item.get("Action") or ""),
                           "timeNano": int(item.get("timeNano") or 0),
                           "actorIdSha256": hash_value(actor.get("ID") or ""),
                           "composeProject": str(attrs.get("com.docker.compose.project") or "")})
        except (TypeError, ValueError): parse_errors.append("dockerEvents: invalid JSON row")
else: parse_errors.append("dockerEvents: command failed")
events.sort(key=lambda item: (item["timeNano"], item["actorIdSha256"]))

info_row = query("docker.info", ["docker", "info", "--format", "{{json .}}"])
docker_info = {}
if info_row["returnCode"] == 0:
    try:
        info = json.loads(info_row["stdout"])
        docker_info = {"serverVersion": str(info.get("ServerVersion") or ""),
                       "containers": int(info.get("Containers") or 0),
                       "containersRunning": int(info.get("ContainersRunning") or 0),
                       "containersPaused": int(info.get("ContainersPaused") or 0),
                       "containersStopped": int(info.get("ContainersStopped") or 0),
                       "images": int(info.get("Images") or 0), "driver": str(info.get("Driver") or ""),
                       "cgroupDriver": str(info.get("CgroupDriver") or ""),
                       "cgroupVersion": str(info.get("CgroupVersion") or ""),
                       "nCpu": int(info.get("NCPU") or 0), "memTotal": int(info.get("MemTotal") or 0),
                       "dockerRootDirSha256": hash_value(info.get("DockerRootDir") or "")}
    except (TypeError, ValueError): parse_errors.append("dockerInfo: invalid JSON")
else: parse_errors.append("dockerInfo: command failed")

listener_row = query("host.listeners", ["ss", "-H", "-lntup"])
listeners, required_port_rows = [], {str(port): [] for port in required_ports}
for line in lines(listener_row):
    fields = line.split()
    if len(fields) < 5: continue
    protocol = fields[0]; local = fields[4] if protocol in ("tcp", "udp") else fields[3]
    candidate = local.rsplit(":", 1)[-1].rstrip("]")
    if not candidate.isdigit(): continue
    row = {"protocol": protocol, "port": int(candidate), "endpointSha256": hash_value(local),
           "ownerSha256": hash_value(" ".join(fields[5:]))}
    listeners.append(row)
    if candidate in required_port_rows: required_port_rows[candidate].append(row)
listeners.sort(key=lambda item: (item["port"], item["protocol"], item["endpointSha256"]))

process_row = query("host.processes", ["ps", "-eo", "pid=,ppid=,user=,lstart=,etimes=,args="])
relevant_processes = []
pattern = re.compile(r"(?i)(performance_campaign\.py|fixed_load\.py|kieker_native\.py|load_gen_loop|observability-placement-results|observability-placement-runs)")
for line in lines(process_row):
    match = re.match(r"\s*(\d+)\s+(\d+)\s+(\S+)\s+(.+)$", line)
    if not match or int(match.group(1)) == os.getpid() or not pattern.search(line): continue
    relevant_processes.append({"pid": int(match.group(1)), "ppid": int(match.group(2)),
                               "userSha256": hash_value(match.group(3)),
                               "commandSha256": hash_value(line.strip())})
relevant_processes.sort(key=lambda item: item["pid"])

exact_session_row = query("sessions.exact", ["tmux", "has-session", "-t", session])
exact_text = (exact_session_row["stdout"] + exact_session_row["stderr"]).lower()
active = exact_session_row["returnCode"] == 0
exact_session_ok = active or (exact_session_row["returnCode"] == 1 and
                   ("no server running" in exact_text or "can't find session" in exact_text))
tmux_row = query("sessions.tmux", ["tmux", "list-sessions", "-F", "#{session_name}\t#{session_created}\t#{session_attached}"])
tmux_text = (tmux_row["stdout"] + tmux_row["stderr"]).lower()
tmux_ok = tmux_row["returnCode"] == 0 or (tmux_row["returnCode"] == 1 and "no server running" in tmux_text)
screen_row = query("sessions.screen", ["screen", "-ls"])
screen_text = (screen_row["stdout"] + screen_row["stderr"]).lower()
screen_ok = screen_row["returnCode"] == 0 or (screen_row["returnCode"] == 1 and "no sockets" in screen_text)
sessions = []
for kind, source in (("tmux", tmux_row), ("screen", screen_row)):
    for line in lines(source):
        if not line.strip() or (kind == "screen" and "\t" not in line): continue
        sessions.append({"kind": kind, "nameSha256": hash_value(line.strip()),
                         "experimentLike": bool(re.search(r"(?i)(teastore|observability|campaign|experiment|kieker)", line))})
sessions.sort(key=lambda item: (item["kind"], item["nameSha256"]))
experiment_sessions = [item for item in sessions if item["experimentLike"]]

time_row = query("host.timeSync", ["timedatectl", "show", "-p", "NTPSynchronized", "--value"])
time_synchronized = time_row["returnCode"] == 0 and time_row["stdout"].strip().lower() == "yes"
tool_commands = {
    "tool.dockerServer": ["docker", "version", "--format", "{{.Server.Version}}"],
    "tool.dockerCompose": ["docker", "compose", "version", "--short"],
    "tool.tmux": ["tmux", "-V"], "tool.screen": ["screen", "--version"],
    "tool.python": ["python3", "--version"], "tool.ss": ["ss", "--version"],
    "tool.setsid": ["setsid", "--version"], "tool.flock": ["flock", "--version"],
    "docker.daemonStarted": ["systemctl", "show", "docker", "--property=ActiveEnterTimestamp", "--value"],
}
tool_rows = {name: query(name, argv) for name, argv in tool_commands.items()}
versions = {name: {"valueSha256": hash_value(row["stdout"].strip()), "present": row["returnCode"] == 0}
            for name, row in tool_rows.items()}

queue_states = []
for container in containers:
    if not container["state"]["running"] or not ("rabbitmq" in container["declaredImage"].lower() or "rabbitmq" in container["name"].lower()): continue
    name = "queue." + container["id"]
    row = query(name, ["docker", "exec", container["id"], "rabbitmqctl", "list_queues",
                       "name", "messages_ready", "messages_unacknowledged", "consumers"])
    parsed = []
    if row["returnCode"] == 0:
        for line in lines(row):
            fields = line.split("\t")
            if len(fields) == 4 and all(value.isdigit() for value in fields[1:]):
                parsed.append({"queueNameSha256": hash_value(fields[0]), "messagesReady": int(fields[1]),
                               "messagesUnacknowledged": int(fields[2]), "consumers": int(fields[3])})
    queue_states.append({"containerId": container["id"], "queryPassed": row["returnCode"] == 0,
                         "queues": sorted(parsed, key=lambda item: item["queueNameSha256"])})

try:
    stat = os.statvfs("/"); loads = list(os.getloadavg()); cpu_count = os.cpu_count() or 0
    root_fs = {"path": "/", "blockSize": stat.f_frsize,
               "totalKiB": stat.f_blocks * stat.f_frsize // 1024,
               "freeKiB": stat.f_bavail * stat.f_frsize // 1024,
               "totalInodes": stat.f_files, "freeInodes": stat.f_favail}
except OSError:
    loads, cpu_count = [0.0, 0.0, 0.0], 0
    root_fs = {"path": "/", "blockSize": 0, "totalKiB": 0, "freeKiB": 0,
               "totalInodes": 0, "freeInodes": 0}
memory = meminfo(); boot = boot_epoch()
host = {"hostnameSha256": hash_value(platform.node()), "kernel": platform.release(),
        "platformSha256": hash_value(platform.platform()), "bootEpoch": boot,
        "bootUtc": datetime.datetime.fromtimestamp(boot, datetime.timezone.utc).isoformat() if boot else "",
        "cpuCount": cpu_count, "loadAverage": loads, "memoryKiB": memory,
        "rootFilesystem": root_fs, "toolVersions": versions}

result_paths = {"resultRoot": os.path.exists(result_root), "log": os.path.exists(result_root + ".log"),
                "exit": os.path.exists(result_root + ".exit")}
release_exists = bool(release_path and os.path.exists(release_path))
exact_roots = [result_root] + ([release_path] if release_path else [])
exact_writers = open_writers(exact_roots)
all_writers = open_writers(["/home/stig/observability-placement-results", "/home/stig/observability-placement-runs"])
paths = {"resultTree": tree_snapshot("/home/stig/observability-placement-results"),
         "releaseTree": tree_snapshot("/home/stig/observability-placement-runs"),
         "allOpenWriters": all_writers}

project_resources = {"project": project,
                     "queryPassed": all(raw_queries["project." + key]["returnCode"] == 0 for key in ("containers", "networks", "volumes")),
                     "containers": project_query_names["containers"], "networks": project_query_names["networks"],
                     "volumes": project_query_names["volumes"]}
running_containers = [{"id": item["id"], "name": item["name"], "composeProject": item["composeProject"],
                       "classification": item["classification"]} for item in containers if item["state"]["running"]]

blocking_resources = []
for resource_type, collection, identity_key in (
    ("container", containers, "id"), ("composeProject", compose_projects, "name"),
    ("network", networks, "id"), ("volume", volumes, "name"),
):
    for item in collection:
        should_block = item["classification"] in {"foreign", "unknown", "owned-current"}
        if resource_type == "container" and item["state"]["running"]: should_block = True
        if resource_type == "composeProject" and item["running"]: should_block = True
        if should_block:
            blocking_resources.append({"resourceType": resource_type, "identity": item[identity_key],
                                       "classification": item["classification"],
                                       "reason": ("running resources always block; " if ((resource_type == "container" and item["state"]["running"]) or (resource_type == "composeProject" and item["running"])) else "") + item["classificationReason"]})
counts = {label: 0 for label in resource_classes}
for collection in (containers, compose_projects, networks, volumes):
    for item in collection: counts[item["classification"]] += 1
classification = {"policySource": "modules/teastore/deployment/srv5.yaml", "policySha256": policy_sha,
                  "counts": counts, "blocking": sorted(blocking_resources,
                  key=lambda item: (item["resourceType"], item["identity"]))}

query_proofs = {name: query_proof(row) for name, row in sorted(raw_queries.items())}
semantic_query_ok = (project_resources["queryPassed"] and exact_session_ok and tmux_ok and screen_ok and
                     listener_row["returnCode"] == 0 and process_row["returnCode"] == 0 and
                     time_row["returnCode"] == 0 and all(row["returnCode"] == 0 for row in tool_rows.values()) and
                     all(state["queryPassed"] for state in queue_states))
query_passed = (semantic_query_ok and not parse_errors and cpu_count > 0 and boot > 0
                and memory["MemTotal"] > 0 and root_fs["totalKiB"] > 0
                and root_fs["totalInodes"] > 0
                and paths["resultTree"]["stable"] and paths["releaseTree"]["stable"]
                and paths["resultTree"]["rootKind"] in {"missing", "directory"}
                and paths["releaseTree"]["rootKind"] in {"missing", "directory"})

stable_state = {
    "containers": containers, "images": images, "composeProjects": compose_projects,
    "networks": networks, "volumes": volumes, "runningContainers": running_containers,
    "projectResources": project_resources, "requiredPorts": required_port_rows,
    "experimentSessions": experiment_sessions, "relevantProcesses": relevant_processes,
    "resultPaths": result_paths, "releaseExists": release_exists,
    "resultTreeSha256": paths["resultTree"]["metadataSha256"],
    "releaseTreeSha256": paths["releaseTree"]["metadataSha256"],
    "openWriters": exact_writers, "allOpenWriters": all_writers,
    "timeSynchronized": time_synchronized, "queueStates": queue_states,
    "classification": classification,
}
state_fingerprint = hashlib.sha256(json.dumps(stable_state, sort_keys=True,
                                   separators=(",", ":")).encode()).hexdigest()
blockers = []
if not query_passed: blockers.append("one or more comprehensive inventory queries failed")
if not time_synchronized: blockers.append("host time is not synchronized")
if active: blockers.append("exact campaign session is active")
if experiment_sessions: blockers.append("an experiment-like session is active")
if relevant_processes: blockers.append("an experiment process is active")
if any(required_port_rows.values()): blockers.append("one or more required ports are occupied")
if exact_writers or all_writers: blockers.append("an observability campaign path has an open writer")
if not paths["resultTree"]["stable"] or not paths["releaseTree"]["stable"]:
    blockers.append("result or release tree scan was unreadable or changed during inventory")
if paths["resultTree"]["rootKind"] not in {"missing", "directory"} or paths["releaseTree"]["rootKind"] not in {"missing", "directory"}:
    blockers.append("result or release tree root is not a directory")
if blocking_resources: blockers.append("host resource classification contains blocking resources")
if any(project_resources[key] for key in ("containers", "networks", "volumes")):
    blockers.append("current campaign Compose namespace is not empty")

proof = {
    "schemaVersion": 3, "capturedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "target": target, "campaign": campaign, "composeProject": project, "session": session,
    "active": active, "projectResources": project_resources, "openWriters": exact_writers,
    "runningContainers": running_containers, "rootFreeKiB": root_fs["freeKiB"],
    "cpuCount": cpu_count, "load1": loads[0], "resultPaths": result_paths,
    "releaseExists": release_exists, "host": host,
    "docker": {"containers": containers, "images": images, "composeProjects": compose_projects,
               "networks": networks, "volumes": volumes, "eventsLastHour": events,
               "queueStates": queue_states, "parseErrors": parse_errors, "info": docker_info},
    "listeners": listeners, "requiredPorts": required_port_rows,
    "sessions": {"all": sessions, "experimentLike": experiment_sessions},
    "processes": {"experimentLike": relevant_processes}, "paths": paths,
    "timeSync": {"synchronized": time_synchronized}, "classification": classification,
    "stableState": stable_state, "stateFingerprint": state_fingerprint,
    "queryProofs": query_proofs, "queryPassed": query_passed,
    "verdict": "pass" if not blockers else "blocked", "blockers": blockers,
}
print(json.dumps(proof, separators=(",", ":")))
'''.lstrip().encode()


def campaign_project(campaign: str) -> str:
    campaign = checked_name(campaign)
    project = f"obst-{campaign}".lower()
    if len(project) > 63:
        raise ValueError("campaign identifier is too long for an isolated Compose project")
    return project


def release_path(commit: str, campaign: str) -> str:
    if not COMMIT.fullmatch(commit):
        raise ValueError("release commit must be a full Git object")
    return f"{REMOTE_RUNS}/{commit[:12]}/{checked_name(campaign)}"


def result_path(campaign: str) -> str:
    return f"{REMOTE_RESULTS}/{checked_name(campaign)}"


def _checked_release(value: str, campaign: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(REMOTE_RUNS)}/[0-9a-f]{{12}}/{re.escape(checked_name(campaign))}$")
    if not pattern.fullmatch(value):
        raise ValueError("release path is outside the derived campaign namespace")
    return value


def _inventory_tree(value: object, location: str) -> dict[str, Any]:
    tree = _exact_keys(value, {
        "dialect", "algorithm", "complete", "root", "exists", "rootKind",
        "entryCount", "kindCounts", "totalFileBytes", "oldestMtimeNs",
        "newestMtimeNs", "metadataSha256", "chunkSize", "chunkCount",
        "chunkSha256", "errorCount", "errorSha256", "firstPassSha256",
        "secondPassSha256", "stable",
    }, location)
    if (tree["dialect"] != "srv5-tree-metadata-v1" or tree["algorithm"] != "sha256"
            or not isinstance(tree["complete"], bool)
            or not isinstance(tree["root"], str) or not isinstance(tree["exists"], bool)
            or tree["rootKind"] not in {"missing", "directory", "file", "symlink", "other", "unreadable"}
            or not isinstance(tree["stable"], bool)):
        raise RuntimeError(f"{location} has invalid identity/state types")
    counts = _exact_keys(tree["kindCounts"], {
        "directory", "file", "symlink", "other",
    }, f"{location}.kindCounts")
    integer_fields = ("entryCount", "totalFileBytes", "chunkSize", "chunkCount", "errorCount")
    if (any(isinstance(tree[key], bool) or not isinstance(tree[key], int) or tree[key] < 0
            for key in integer_fields)
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 0
                   for value in counts.values())
            or sum(counts.values()) != tree["entryCount"]):
        raise RuntimeError(f"{location} counts are malformed")
    if (tree["chunkSize"] != 4096 or not isinstance(tree["chunkSha256"], list)
            or tree["chunkCount"] != len(tree["chunkSha256"])
            or tree["chunkCount"] != ((tree["entryCount"] + tree["chunkSize"] - 1)
                                      // tree["chunkSize"])
            or any(not isinstance(value, str) or not SHA256.fullmatch(value)
                   for value in tree["chunkSha256"])):
        raise RuntimeError(f"{location} chunk rollup is malformed")
    for key in ("metadataSha256", "errorSha256", "firstPassSha256", "secondPassSha256"):
        if not isinstance(tree[key], str) or not SHA256.fullmatch(tree[key]):
            raise RuntimeError(f"{location}.{key} is malformed")
    oldest, newest = tree["oldestMtimeNs"], tree["newestMtimeNs"]
    if tree["entryCount"] == 0:
        if oldest is not None or newest is not None:
            raise RuntimeError(f"{location} empty scan has timestamps")
    elif (isinstance(oldest, bool) or not isinstance(oldest, int) or oldest < 0
          or isinstance(newest, bool) or not isinstance(newest, int) or newest < oldest):
        raise RuntimeError(f"{location} timestamp bounds are malformed")
    if ((tree["rootKind"] == "missing") != (tree["exists"] is False)
            or (not tree["exists"] and tree["entryCount"] != 0)):
        raise RuntimeError(f"{location} root existence relation is invalid")
    rollup = {"algorithm": tree["algorithm"], "chunkSize": tree["chunkSize"],
              "entryCount": tree["entryCount"], "chunks": tree["chunkSha256"]}
    expected_metadata = hashlib.sha256(json.dumps(
        rollup, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if tree["metadataSha256"] != expected_metadata:
        raise RuntimeError(f"{location} chunk metadata digest does not replay")
    second_summary = {
        "dialect": tree["dialect"], "algorithm": tree["algorithm"],
        "complete": tree["complete"],
        "exists": tree["exists"], "rootKind": tree["rootKind"],
        "entryCount": tree["entryCount"], "kindCounts": counts,
        "totalFileBytes": tree["totalFileBytes"], "oldestMtimeNs": oldest,
        "newestMtimeNs": newest, "metadataSha256": tree["metadataSha256"],
        "chunkSize": tree["chunkSize"], "chunkCount": tree["chunkCount"],
        "chunkSha256": tree["chunkSha256"],
        "errorCount": tree["errorCount"], "errorSha256": tree["errorSha256"],
    }
    expected_second = hashlib.sha256(json.dumps(
        second_summary, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if tree["secondPassSha256"] != expected_second:
        raise RuntimeError(f"{location} second-pass digest does not replay")
    if tree["complete"] != (tree["errorCount"] == 0):
        raise RuntimeError(f"{location} completeness verdict does not replay")
    empty_error_sha256 = hashlib.sha256(b"[]").hexdigest()
    if tree["complete"] and tree["errorSha256"] != empty_error_sha256:
        raise RuntimeError(f"{location} complete scan has a non-empty error digest")
    derived_stable = (tree["firstPassSha256"] == tree["secondPassSha256"]
                      and tree["complete"])
    if tree["stable"] != derived_stable:
        raise RuntimeError(f"{location} stability verdict does not replay")
    return tree


def load_host_policy(path: Path = HOST_POLICY_PATH) -> dict[str, Any]:
    """Load the checked-in ownership policy into the narrow remote protocol."""
    try:
        content = path.read_bytes()
        document = yaml.safe_load(content)
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError(f"invalid srv5 host policy: {exc}") from exc
    root = _exact_keys(document, {
        "schema_version", "target", "experiment_user", "remote_root", "project",
        "upstream_path", "ownership", "quiet_host", "reset",
    }, "srv5 policy")
    if root["schema_version"] != 1 or root["target"] != "fb14srv5":
        raise RuntimeError("srv5 host policy identity or schema differs")
    ownership = _exact_keys(
        root["ownership"], {
            "allowed_legacy_projects", "allowed_inert_networks",
            "allowed_stopped_restart_policies", "preserve_unreferenced_volumes",
            "foreign_policy", "unknown_policy",
        },
        "srv5 policy ownership",
    )
    if ownership["foreign_policy"] != "block" or ownership["unknown_policy"] != "block":
        raise RuntimeError("srv5 host policy must fail closed for foreign and unknown resources")
    allowed = ownership["allowed_legacy_projects"]
    if not isinstance(allowed, dict):
        raise RuntimeError("srv5 allowed legacy projects must be an object")
    normalized = []
    for project, raw in sorted(allowed.items()):
        if not isinstance(project, str) or not project:
            raise RuntimeError("srv5 legacy project name is invalid")
        row = _exact_keys(raw, {"working_directory", "config_files"}, f"legacy project {project}")
        if (not isinstance(row["working_directory"], str)
                or not row["working_directory"].startswith("/home/stig/")
                or not isinstance(row["config_files"], list) or not row["config_files"]
                or not all(isinstance(item, str) and item and "/" not in item
                           for item in row["config_files"])):
            raise RuntimeError(f"legacy project {project} attribution is invalid")
        normalized.append({
            "project": project, "workingDirectory": row["working_directory"],
            "configFiles": sorted(row["config_files"]),
        })
    inert_networks = ownership["allowed_inert_networks"]
    if not isinstance(inert_networks, list) or not inert_networks:
        raise RuntimeError("srv5 inert-network allow-list must be non-empty")
    normalized_networks = []
    for index, raw in enumerate(inert_networks):
        row = _exact_keys(raw, {"name", "driver", "scope"}, f"inert network {index}")
        if (not all(isinstance(row[key], str) and row[key]
                    for key in ("name", "driver", "scope"))
                or row["name"] in {"bridge", "host", "none"}):
            raise RuntimeError(f"inert network {index} attribution is invalid")
        normalized_networks.append(dict(row))
    restart_policies = ownership["allowed_stopped_restart_policies"]
    if (not isinstance(restart_policies, list) or not restart_policies
            or not all(isinstance(item, str) and item for item in restart_policies)
            or len(restart_policies) != len(set(restart_policies))):
        raise RuntimeError("srv5 stopped-container restart policies are invalid")
    if ownership["preserve_unreferenced_volumes"] is not True:
        raise RuntimeError("srv5 must explicitly preserve unreferenced volumes in place")
    quiet = _exact_keys(root["quiet_host"], {
        "permitted_running_projects", "settle_seconds", "maximum_load_per_cpu",
        "minimum_root_free_gib",
    }, "srv5 quiet-host policy")
    if quiet["permitted_running_projects"] != []:
        raise RuntimeError("srv5 policy must not permit running Compose projects")
    return {
        "path": path.resolve(), "sha256": hashlib.sha256(content).hexdigest(),
        "remote": {
            "target": root["target"], "allowedLegacyProjects": normalized,
            "allowedInertNetworks": normalized_networks,
            "allowedStoppedRestartPolicies": sorted(restart_policies),
            "preserveUnreferencedVolumes": True,
            "foreignPolicy": ownership["foreign_policy"],
            "unknownPolicy": ownership["unknown_policy"],
        },
    }


def _stream_proof_shape(value: object, location: str) -> dict[str, Any]:
    stream = _exact_keys(value, {"sha256", "bytes", "lineCount"}, location)
    if (not isinstance(stream["sha256"], str) or not SHA256.fullmatch(stream["sha256"])
            or isinstance(stream["bytes"], bool) or not isinstance(stream["bytes"], int)
            or stream["bytes"] < 0 or isinstance(stream["lineCount"], bool)
            or not isinstance(stream["lineCount"], int) or stream["lineCount"] < 0):
        raise RuntimeError(f"{location} has invalid digest/count fields")
    return stream


def _sanitized_query_shape(value: object, location: str) -> dict[str, Any]:
    proof = _exact_keys(value, {"command", "returnCode", "stdout", "stderr"}, location)
    if (not isinstance(proof["command"], list)
            or not all(isinstance(item, str) for item in proof["command"])
            or isinstance(proof["returnCode"], bool)
            or not isinstance(proof["returnCode"], int)):
        raise RuntimeError(f"{location} has invalid command fields")
    _stream_proof_shape(proof["stdout"], f"{location}.stdout")
    _stream_proof_shape(proof["stderr"], f"{location}.stderr")
    return proof


def _classified_rows(value: object, keys: set[str], location: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise RuntimeError(f"{location} must be a list")
    rows = []
    for index, item in enumerate(value):
        row = _exact_keys(item, keys | {"classification", "classificationReason"},
                          f"{location}[{index}]")
        if (row["classification"] not in RESOURCE_CLASSES
                or not isinstance(row["classificationReason"], str)
                or not row["classificationReason"]):
            raise RuntimeError(f"{location}[{index}] classification is invalid")
        rows.append(row)
    return rows


def _safe_writer_rows(value: object, location: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise RuntimeError(f"{location} must be a list")
    rows = []
    for index, item in enumerate(value):
        row = _exact_keys(item, {"pid", "fd", "pathSha256", "commandSha256"},
                          f"{location}[{index}]")
        if (isinstance(row["pid"], bool) or not isinstance(row["pid"], int) or row["pid"] < 1
                or isinstance(row["fd"], bool) or not isinstance(row["fd"], int) or row["fd"] < 0
                or any(not isinstance(row[key], str) or not SHA256.fullmatch(row[key])
                       for key in ("pathSha256", "commandSha256"))):
            raise RuntimeError(f"{location}[{index}] is malformed")
        rows.append(row)
    return rows


def inventory(target: str, campaign: str, *, release: str = "") -> dict[str, Any]:
    target = checked_target(target)
    campaign = checked_name(campaign)
    project = campaign_project(campaign)
    session = f"teastore-{campaign}"
    result_root = result_path(campaign)
    release_argument = _checked_release(release, campaign) if release else "-"
    host_policy = load_host_policy()
    encoded_policy = base64.urlsafe_b64encode(json.dumps(
        host_policy["remote"], sort_keys=True, separators=(",", ":")).encode()).decode()
    remote = (f"python3 - {target} {campaign} {project} {session} {result_root} "
              f"{release_argument} {encoded_policy} {host_policy['sha256']}")
    proof = _strict_json(ssh(target, remote, data=REMOTE_INVENTORY).stdout, "inventory")
    required = {
        "schemaVersion", "capturedAt", "target", "campaign", "composeProject", "session",
        "active", "projectResources", "openWriters", "runningContainers", "rootFreeKiB",
        "cpuCount", "load1", "resultPaths", "releaseExists", "queryProofs", "queryPassed",
        "verdict", "blockers", "host", "docker", "listeners", "requiredPorts",
        "sessions", "processes", "paths", "timeSync", "classification", "stableState",
        "stateFingerprint",
    }
    if set(proof) != required:
        raise RuntimeError("remote inventory fields differ from sanitized protocol")
    if (proof["schemaVersion"] != 3 or proof["target"] != target
            or proof["campaign"] != campaign or proof["composeProject"] != project
            or proof["session"] != session):
        raise RuntimeError("remote inventory identity differs from request")
    try:
        captured = datetime.datetime.fromisoformat(proof["capturedAt"])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("remote inventory timestamp is invalid") from exc
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise RuntimeError("remote inventory timestamp must be timezone-aware")
    if any(not isinstance(proof[field], bool)
           for field in ("active", "queryPassed", "releaseExists")):
        raise RuntimeError("remote inventory boolean fields are invalid")
    if (isinstance(proof["rootFreeKiB"], bool) or not isinstance(proof["rootFreeKiB"], int)
            or proof["rootFreeKiB"] < 0 or isinstance(proof["cpuCount"], bool)
            or not isinstance(proof["cpuCount"], int) or proof["cpuCount"] < 0
            or isinstance(proof["load1"], bool) or not isinstance(proof["load1"], (int, float))
            or not math.isfinite(proof["load1"]) or proof["load1"] < 0):
        raise RuntimeError("remote inventory host summary is malformed")
    if (not isinstance(proof["blockers"], list)
            or not all(isinstance(item, str) and item for item in proof["blockers"])):
        raise RuntimeError("remote inventory blockers are malformed")

    resources = _exact_keys(proof["projectResources"], {
        "project", "queryPassed", "containers", "networks", "volumes",
    }, "inventory.projectResources")
    if (resources["project"] != project or not isinstance(resources["queryPassed"], bool)
            or any(not isinstance(resources[kind], list)
                   or not all(isinstance(item, str) and item for item in resources[kind])
                   for kind in ("containers", "networks", "volumes"))):
        raise RuntimeError("remote inventory project resources are malformed")
    if resources["queryPassed"] is not True and proof["queryPassed"] is True:
        raise RuntimeError("remote inventory claims success over failed project queries")
    if (not isinstance(proof["resultPaths"], dict)
            or set(proof["resultPaths"]) != {"resultRoot", "log", "exit"}
            or not all(isinstance(value, bool) for value in proof["resultPaths"].values())):
        raise RuntimeError("remote inventory result paths are malformed")

    host = _exact_keys(proof["host"], {
        "hostnameSha256", "kernel", "platformSha256", "bootEpoch", "bootUtc", "cpuCount",
        "loadAverage", "memoryKiB", "rootFilesystem", "toolVersions",
    }, "inventory.host")
    if (not SHA256.fullmatch(str(host["hostnameSha256"]))
            or not SHA256.fullmatch(str(host["platformSha256"]))
            or not isinstance(host["kernel"], str) or not isinstance(host["bootUtc"], str)
            or isinstance(host["bootEpoch"], bool) or not isinstance(host["bootEpoch"], int)
            or host["bootEpoch"] < 0 or host["cpuCount"] != proof["cpuCount"]
            or not isinstance(host["loadAverage"], list) or len(host["loadAverage"]) != 3
            or any(isinstance(value, bool) or not isinstance(value, (int, float))
                   or not math.isfinite(value) or value < 0 for value in host["loadAverage"])
            or host["loadAverage"][0] != proof["load1"]):
        raise RuntimeError("remote inventory host identity/load fields are malformed")
    memory = _exact_keys(host["memoryKiB"], {
        "MemTotal", "MemAvailable", "SwapTotal", "SwapFree",
    }, "inventory.host.memoryKiB")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0
           for value in memory.values()):
        raise RuntimeError("remote inventory memory fields are malformed")
    filesystem = _exact_keys(host["rootFilesystem"], {
        "path", "blockSize", "totalKiB", "freeKiB", "totalInodes", "freeInodes",
    }, "inventory.host.rootFilesystem")
    if (filesystem["path"] != "/" or filesystem["freeKiB"] != proof["rootFreeKiB"]
            or any(isinstance(filesystem[key], bool) or not isinstance(filesystem[key], int)
                   or filesystem[key] < 0 for key in set(filesystem) - {"path"})):
        raise RuntimeError("remote inventory filesystem fields are malformed")
    expected_tools = {
        "tool.dockerServer", "tool.dockerCompose", "tool.tmux", "tool.screen",
        "tool.python", "tool.ss", "tool.setsid", "tool.flock", "docker.daemonStarted",
    }
    if not isinstance(host["toolVersions"], dict) or set(host["toolVersions"]) != expected_tools:
        raise RuntimeError("remote inventory tool inventory is incomplete")
    for name, item in host["toolVersions"].items():
        row = _exact_keys(item, {"valueSha256", "present"}, f"toolVersions.{name}")
        if not isinstance(row["present"], bool) or not SHA256.fullmatch(str(row["valueSha256"])):
            raise RuntimeError(f"toolVersions.{name} is malformed")

    docker = _exact_keys(proof["docker"], {
        "containers", "images", "composeProjects", "networks", "volumes",
        "eventsLastHour", "queueStates", "parseErrors", "info",
    }, "inventory.docker")
    containers = _classified_rows(docker["containers"], {
        "id", "name", "created", "declaredImage", "runtimeImageId", "composeProject",
        "composeWorkingDirectory", "composeConfigFiles", "composeService", "state",
        "restartCount", "restartPolicy", "ports", "mounts", "networks", "limits",
    }, "inventory.docker.containers")
    for index, container in enumerate(containers):
        restart = _exact_keys(container["restartPolicy"], {
            "name", "maximumRetryCount",
        }, f"inventory.docker.containers[{index}].restartPolicy")
        if (not isinstance(restart["name"], str) or not restart["name"]
                or isinstance(restart["maximumRetryCount"], bool)
                or not isinstance(restart["maximumRetryCount"], int)
                or restart["maximumRetryCount"] < 0):
            raise RuntimeError("remote inventory container restart policy is malformed")
    compose_projects = _classified_rows(docker["composeProjects"], {
        "name", "status", "configFiles", "workingDirectory", "running",
    }, "inventory.docker.composeProjects")
    networks = _classified_rows(docker["networks"], {
        "id", "name", "driver", "scope", "internal", "attachable", "composeProject",
        "composeWorkingDirectory", "composeConfigFiles", "containerIds",
    }, "inventory.docker.networks")
    volumes = _classified_rows(docker["volumes"], {
        "name", "driver", "scope", "mountpointSha256", "composeProject",
        "composeWorkingDirectory", "composeConfigFiles", "referencedBy",
    }, "inventory.docker.volumes")
    if (not isinstance(docker["images"], list) or not isinstance(docker["eventsLastHour"], list)
            or not isinstance(docker["queueStates"], list) or not isinstance(docker["parseErrors"], list)
            or not isinstance(docker["info"], dict)):
        raise RuntimeError("remote inventory Docker summaries are malformed")
    for index, image in enumerate(docker["images"]):
        _exact_keys(image, {"id", "repoTags", "repoDigests", "created", "size"},
                    f"inventory.docker.images[{index}]")
    for index, event in enumerate(docker["eventsLastHour"]):
        row = _exact_keys(event, {"type", "action", "timeNano", "actorIdSha256", "composeProject"},
                          f"inventory.docker.eventsLastHour[{index}]")
        if not SHA256.fullmatch(str(row["actorIdSha256"])):
            raise RuntimeError("remote inventory event identity is malformed")
    for index, queue in enumerate(docker["queueStates"]):
        row = _exact_keys(queue, {"containerId", "queryPassed", "queues"},
                          f"inventory.docker.queueStates[{index}]")
        if not isinstance(row["queryPassed"], bool) or not isinstance(row["queues"], list):
            raise RuntimeError("remote inventory queue state is malformed")
    if not all(isinstance(item, str) for item in docker["parseErrors"]):
        raise RuntimeError("remote inventory parse errors are malformed")

    if not isinstance(proof["listeners"], list):
        raise RuntimeError("remote inventory listeners are malformed")
    for index, listener in enumerate(proof["listeners"]):
        row = _exact_keys(listener, {"protocol", "port", "endpointSha256", "ownerSha256"},
                          f"inventory.listeners[{index}]")
        if not SHA256.fullmatch(str(row["endpointSha256"])) or not SHA256.fullmatch(str(row["ownerSha256"])):
            raise RuntimeError("remote inventory listener hashes are malformed")
    if (not isinstance(proof["requiredPorts"], dict)
            or set(proof["requiredPorts"]) != {str(port) for port in REQUIRED_PORTS}
            or not all(isinstance(rows, list) for rows in proof["requiredPorts"].values())):
        raise RuntimeError("remote inventory required-port rows are malformed")
    sessions = _exact_keys(proof["sessions"], {"all", "experimentLike"}, "inventory.sessions")
    for key in sessions:
        if not isinstance(sessions[key], list):
            raise RuntimeError("remote inventory sessions are malformed")
        for index, item in enumerate(sessions[key]):
            row = _exact_keys(item, {"kind", "nameSha256", "experimentLike"},
                              f"inventory.sessions.{key}[{index}]")
            if not SHA256.fullmatch(str(row["nameSha256"])) or not isinstance(row["experimentLike"], bool):
                raise RuntimeError("remote inventory session hashes are malformed")
    processes = _exact_keys(proof["processes"], {"experimentLike"}, "inventory.processes")
    if not isinstance(processes["experimentLike"], list):
        raise RuntimeError("remote inventory processes are malformed")
    for index, item in enumerate(processes["experimentLike"]):
        row = _exact_keys(item, {"pid", "ppid", "userSha256", "commandSha256"},
                          f"inventory.processes.experimentLike[{index}]")
        if not SHA256.fullmatch(str(row["userSha256"])) or not SHA256.fullmatch(str(row["commandSha256"])):
            raise RuntimeError("remote inventory process hashes are malformed")
    if proof["openWriters"] != _safe_writer_rows(proof["openWriters"], "inventory.openWriters"):
        raise RuntimeError("remote inventory exact writer rows differ")
    paths = _exact_keys(proof["paths"], {"resultTree", "releaseTree", "allOpenWriters"},
                        "inventory.paths")
    result_tree = _inventory_tree(paths["resultTree"], "inventory.paths.resultTree")
    release_tree = _inventory_tree(paths["releaseTree"], "inventory.paths.releaseTree")
    if result_tree["root"] != REMOTE_RESULTS or release_tree["root"] != REMOTE_RUNS:
        raise RuntimeError("remote inventory tree roots differ from the exact host namespaces")
    trees_safe = (result_tree["stable"] and release_tree["stable"]
                  and result_tree["rootKind"] in {"missing", "directory"}
                  and release_tree["rootKind"] in {"missing", "directory"})
    if proof["queryPassed"] and not trees_safe:
        raise RuntimeError("remote inventory claims success over unreadable or racy tree scans")
    _safe_writer_rows(paths["allOpenWriters"], "inventory.paths.allOpenWriters")
    time_sync = _exact_keys(proof["timeSync"], {"synchronized"}, "inventory.timeSync")
    if not isinstance(time_sync["synchronized"], bool):
        raise RuntimeError("remote inventory time-sync state is malformed")

    classification = _exact_keys(proof["classification"], {
        "policySource", "policySha256", "counts", "blocking",
    }, "inventory.classification")
    if (classification["policySource"] != "modules/teastore/deployment/srv5.yaml"
            or classification["policySha256"] != host_policy["sha256"]
            or not isinstance(classification["counts"], dict)
            or set(classification["counts"]) != set(RESOURCE_CLASSES)
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 0
                   for value in classification["counts"].values())
            or not isinstance(classification["blocking"], list)):
        raise RuntimeError("remote inventory classification policy is malformed or stale")
    replay_counts = {label: 0 for label in RESOURCE_CLASSES}
    for collection in (containers, compose_projects, networks, volumes):
        for item in collection:
            replay_counts[item["classification"]] += 1
    if classification["counts"] != replay_counts:
        raise RuntimeError("remote inventory classification counts do not replay")
    for index, item in enumerate(classification["blocking"]):
        row = _exact_keys(item, {"resourceType", "identity", "classification", "reason"},
                          f"inventory.classification.blocking[{index}]")
        if row["classification"] not in RESOURCE_CLASSES or not isinstance(row["reason"], str):
            raise RuntimeError("remote inventory blocking classification is malformed")
    expected_blocking = []
    for resource_type, collection, identity_key in (
        ("container", containers, "id"), ("composeProject", compose_projects, "name"),
        ("network", networks, "id"), ("volume", volumes, "name"),
    ):
        for item in collection:
            running = ((resource_type == "container" and item["state"].get("running") is True)
                       or (resource_type == "composeProject" and item.get("running") is True))
            if item["classification"] in {"foreign", "unknown", "owned-current"} or running:
                expected_blocking.append({
                    "resourceType": resource_type, "identity": item[identity_key],
                    "classification": item["classification"],
                    "reason": ("running resources always block; " if running else "")
                    + item["classificationReason"],
                })
    expected_blocking.sort(key=lambda item: (item["resourceType"], item["identity"]))
    if classification["blocking"] != expected_blocking:
        raise RuntimeError("remote inventory blocking classifications do not replay")

    expected_running = [{
        "id": item["id"], "name": item["name"], "composeProject": item["composeProject"],
        "classification": item["classification"],
    } for item in containers if item["state"].get("running") is True]
    if proof["runningContainers"] != expected_running:
        raise RuntimeError("remote inventory running-container summary does not replay")
    expected_project_resources = {
        "project": project, "queryPassed": resources["queryPassed"],
        "containers": sorted(item["id"] for item in containers if item["composeProject"] == project),
        "networks": sorted(item["id"] for item in networks if item["composeProject"] == project),
        "volumes": sorted(item["name"] for item in volumes if item["composeProject"] == project),
    }
    if resources != expected_project_resources:
        raise RuntimeError("remote inventory campaign namespace does not replay from typed resources")

    if not isinstance(proof["queryProofs"], dict):
        raise RuntimeError("remote inventory command proof ledger is malformed")
    required_query_names = {
        "project.containers", "project.networks", "project.volumes", "containers.list",
        "containers.inspect", "images.inspect", "compose.projects", "networks.list",
        "networks.inspect", "volumes.list", "volumes.inspect", "docker.events", "docker.info",
        "host.listeners", "host.processes", "sessions.exact", "sessions.tmux", "sessions.screen",
        "host.timeSync", *expected_tools,
    }
    if not required_query_names.issubset(proof["queryProofs"]):
        raise RuntimeError("remote inventory command proof ledger is incomplete")
    for name, item in proof["queryProofs"].items():
        if not isinstance(name, str) or not name:
            raise RuntimeError("remote inventory command proof name is invalid")
        _sanitized_query_shape(item, f"inventory.queryProofs.{name}")

    stable = proof["stableState"]
    stable_relations = {
        "containers": containers, "images": docker["images"],
        "composeProjects": compose_projects, "networks": networks, "volumes": volumes,
        "runningContainers": proof["runningContainers"], "projectResources": resources,
        "requiredPorts": proof["requiredPorts"], "experimentSessions": sessions["experimentLike"],
        "relevantProcesses": processes["experimentLike"], "resultPaths": proof["resultPaths"],
        "releaseExists": proof["releaseExists"],
        "resultTreeSha256": result_tree["metadataSha256"],
        "releaseTreeSha256": release_tree["metadataSha256"],
        "openWriters": proof["openWriters"],
        "allOpenWriters": paths["allOpenWriters"], "timeSynchronized": time_sync["synchronized"],
        "queueStates": docker["queueStates"], "classification": classification,
    }
    if not isinstance(stable, dict) or stable != stable_relations:
        raise RuntimeError("remote inventory stable state differs from retained observations")
    fingerprint = hashlib.sha256(json.dumps(
        stable, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if proof["stateFingerprint"] != fingerprint:
        raise RuntimeError("remote inventory state fingerprint does not replay")
    if proof["verdict"] not in {"pass", "blocked"}:
        raise RuntimeError("remote inventory verdict is invalid")
    unsafe = (proof["active"] or bool(proof["openWriters"]) or bool(proof["runningContainers"])
              or bool(classification["blocking"]) or any(proof["requiredPorts"].values())
              or bool(sessions["experimentLike"]) or bool(processes["experimentLike"])
              or not time_sync["synchronized"] or not trees_safe
              or any(resources[kind] for kind in ("containers", "networks", "volumes")))
    if proof["verdict"] == "pass" and (not proof["queryPassed"] or proof["blockers"] or unsafe):
        raise RuntimeError("remote inventory pass verdict contradicts sanitized evidence")
    if proof["verdict"] == "blocked" and not proof["blockers"]:
        raise RuntimeError("remote inventory blocked verdict lacks blockers")
    return proof


def _preflight_blockers(result: dict[str, Any], label: str) -> list[str]:
    blockers: list[str] = []
    if not result["queryPassed"]:
        blockers.append(f"{label} inventory query failure")
    if result["runningContainers"]:
        blockers.append(f"{label} running containers: {result['runningContainers']}")
    if result["classification"]["blocking"]:
        blockers.append(
            f"{label} foreign, unknown, running, or stale-current resources: "
            f"{result['classification']['blocking']}"
        )
    resources = result["projectResources"]
    if any(resources.get(kind) for kind in ("containers", "networks", "volumes")):
        blockers.append(f"{label} campaign namespace is not empty: {resources}")
    if result["active"]:
        blockers.append(f"{label} campaign tmux session already exists")
    if any(result["resultPaths"].values()):
        blockers.append(f"{label} campaign result paths already exist: {result['resultPaths']}")
    if result["releaseExists"]:
        blockers.append(f"{label} campaign release path already exists")
    if result["rootFreeKiB"] < 80 * 1024 * 1024:
        blockers.append(f"{label} less than 80 GiB root free")
    if result["cpuCount"] <= 0 or result["load1"] / result["cpuCount"] > 0.10:
        blockers.append(f"{label} host is not quiet: load1={result['load1']}, cpus={result['cpuCount']}")
    if result["openWriters"]:
        blockers.append(f"{label} campaign paths already have open writers: {result['openWriters']}")
    if result["paths"]["allOpenWriters"]:
        blockers.append(f"{label} an observability campaign path has an open writer")
    if result["sessions"]["experimentLike"]:
        blockers.append(f"{label} experiment-like sessions are active")
    if result["processes"]["experimentLike"]:
        blockers.append(f"{label} experiment processes are active")
    if any(result["requiredPorts"].values()):
        blockers.append(f"{label} required ports are occupied: {result['requiredPorts']}")
    if result["timeSync"]["synchronized"] is not True:
        blockers.append(f"{label} host time is not synchronized")
    if (not result["paths"]["resultTree"]["stable"]
            or not result["paths"]["releaseTree"]["stable"]):
        blockers.append(f"{label} result/release inventory was unreadable or racy")
    if (result["paths"]["resultTree"]["rootKind"] not in {"missing", "directory"}
            or result["paths"]["releaseTree"]["rootKind"] not in {"missing", "directory"}):
        blockers.append(f"{label} result/release inventory root is not a directory")
    return blockers


def preflight(target: str, campaign: str, *, release: str = "",
              settle_seconds: int = 60) -> dict[str, Any]:
    if isinstance(settle_seconds, bool) or not isinstance(settle_seconds, int) or settle_seconds < 1:
        raise ValueError("preflight settle interval must be a positive integer")
    first = inventory(target, campaign, release=release)
    blockers = _preflight_blockers(first, "first")
    time.sleep(settle_seconds)
    second = inventory(target, campaign, release=release)
    blockers.extend(_preflight_blockers(second, "second"))
    stable = first["stateFingerprint"] == second["stateFingerprint"]
    if not stable:
        blockers.append("host state changed during the preflight settle interval")
    if blockers:
        raise RuntimeError("preflight blocked: " + "; ".join(blockers))
    return {"schemaVersion": 2, "campaign": checked_name(campaign),
            "target": checked_target(target), "settleSeconds": settle_seconds,
            "stable": stable, "first": first, "second": second,
            "verdict": "pass", "blockers": []}


def persist_preflight(campaign: str, *, target: str, commit: str,
                      descriptor: dict[str, Any], proof: dict[str, Any]) -> Path:
    """Persist the read-only gate before the first remote mutation.

    Campaign identifiers are single-use. An existing record is retained rather
    than overwritten so a failed launch cannot erase the observation that
    authorized it.
    """
    campaign = checked_name(campaign)
    target = checked_target(target)
    if not COMMIT.fullmatch(commit):
        raise ValueError("preflight framework commit must be a full Git object")
    if proof.get("verdict") != "pass" or proof.get("campaign") != campaign or (
        proof.get("target") != target
    ):
        raise RuntimeError("only an identity-bound passing preflight can be persisted")
    record = {
        "schemaVersion": 1,
        "recordedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "campaign": campaign,
        "target": target,
        "source": {
            "frameworkCommit": commit,
            "sutReferenceCommit": SUT_REFERENCE_COMMIT,
            "descriptorId": descriptor["id"],
            "descriptorSha256": descriptor["sha256"],
        },
        "preflight": proof,
    }
    LOCAL_PREFLIGHTS.mkdir(parents=True, exist_ok=True)
    path = LOCAL_PREFLIGHTS / f"{campaign}.json"
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise RuntimeError(f"preflight evidence already exists for campaign: {campaign}") from exc
    return path


def retained_preflight(campaign: str, *, target: str,
                       descriptor: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """Read the single-use local preflight without permitting a later swap."""

    campaign = checked_name(campaign)
    target = checked_target(target)
    path = LOCAL_PREFLIGHTS / f"{campaign}.json"
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"persisted preflight evidence is missing or unsafe: {path}")
    before = path.stat()
    payload = path.read_bytes()
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise RuntimeError("persisted preflight evidence changed while being read")
    try:
        record = _loads_strict(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"persisted preflight JSON is invalid: {exc}") from exc
    if not isinstance(record, dict):
        raise RuntimeError("persisted preflight must be a JSON object")
    expected = {
        "schemaVersion", "recordedAt", "campaign", "target", "source", "preflight",
    }
    source = record.get("source")
    if (set(record) != expected or record.get("schemaVersion") != 1
            or record.get("campaign") != campaign or record.get("target") != target
            or not isinstance(source, dict) or set(source) != {
                "frameworkCommit", "sutReferenceCommit", "descriptorId", "descriptorSha256",
            }
            or not isinstance(source.get("frameworkCommit"), str)
            or not COMMIT.fullmatch(source["frameworkCommit"])
            or source.get("sutReferenceCommit") != SUT_REFERENCE_COMMIT
            or source.get("descriptorId") != descriptor["id"]
            or source.get("descriptorSha256") != descriptor["sha256"]):
        raise RuntimeError("persisted preflight identity or source binding differs")
    return payload, record


def install_preflight(root: Path, payload: bytes, record: dict[str, Any],
                      owner: dict[str, Any]) -> Path:
    """Add the already-read preflight to a new fetched tree exactly once."""

    source = record.get("source")
    if not isinstance(source, dict) or source.get("frameworkCommit") != owner.get("frameworkCommit"):
        raise RuntimeError("persisted preflight framework commit differs from fetched owner")
    destination = root / "preflight.json"
    created = False
    try:
        with destination.open("xb") as handle:
            created = True
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        destination.chmod(0o600)
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return destination


REMOTE_STATUS = r'''
import json, pathlib, subprocess, sys
campaign, session, root, expected = sys.argv[1:]
try:
    tmux = subprocess.run(["tmux", "has-session", "-t", session], text=True,
                          capture_output=True, check=False)
    tmux_rc, tmux_err = tmux.returncode, tmux.stderr
except OSError as exc:
    tmux_rc, tmux_err = 127, str(exc)
active = tmux_rc == 0
tmux_error = tmux_err.lower()
tmux_valid = (active or (tmux_rc == 1 and
              ("no server running" in tmux_error or "can't find session" in tmux_error)))
exit_path = pathlib.Path(root + ".exit")
exit_value = ""
exit_valid = True
if exit_path.exists():
    try:
        exit_value = exit_path.read_text().strip()
        parsed = int(exit_value)
        exit_valid = str(parsed) == exit_value and 0 <= parsed <= 255
    except (OSError, ValueError):
        exit_valid = False
receipts = len(list(pathlib.Path(root).glob("*/receipt.json"))) if pathlib.Path(root).is_dir() else 0
proof = {"schemaVersion": 1, "campaign": campaign, "active": active,
         "exitCode": exit_value, "receipts": receipts, "expected": int(expected),
         "queryPassed": tmux_valid and exit_valid,
         "tmuxReturnCode": tmux_rc, "tmuxStderr": tmux_err}
print(json.dumps(proof, separators=(",", ":")))
'''.lstrip().encode()


def status(target: str, campaign: str, expected: int = 15) -> dict[str, Any]:
    campaign = checked_name(campaign)
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
        raise ValueError("expected receipt count must be a non-negative integer")
    session = f"teastore-{campaign}"
    root = f"{REMOTE_RESULTS}/{campaign}"
    remote = f"python3 - {campaign} {session} {root} {expected}"
    value = _strict_json(ssh(target, remote, data=REMOTE_STATUS).stdout, "status")
    required = {"schemaVersion", "campaign", "active", "exitCode", "receipts", "expected",
                "queryPassed", "tmuxReturnCode", "tmuxStderr"}
    if set(value) != required or value.get("schemaVersion") != 1 or value.get("campaign") != campaign:
        raise RuntimeError("remote status fields or identity differ from protocol")
    if not isinstance(value["active"], bool) or not isinstance(value["queryPassed"], bool):
        raise RuntimeError("remote status booleans are invalid")
    if (isinstance(value["receipts"], bool) or not isinstance(value["receipts"], int)
            or value["receipts"] < 0 or value["expected"] != expected):
        raise RuntimeError("remote status receipt counts are invalid")
    exit_code = value["exitCode"]
    if not isinstance(exit_code, str) or (exit_code and (not exit_code.isdecimal() or int(exit_code) > 255)):
        raise RuntimeError("remote status exit code is invalid")
    if not value["queryPassed"]:
        raise RuntimeError(f"remote status query failed: {value}")
    return {key: value[key] for key in ("campaign", "active", "exitCode", "receipts", "expected")}


def framework_commit(descriptor: dict[str, Any] | None = None) -> str:
    dirty = execute(["git", "status", "--porcelain"], cwd=ROOT).stdout.decode().strip()
    if dirty:
        raise RuntimeError("framework tree is dirty; launch requires a clean commit")
    commit = execute(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.decode().strip()
    if not COMMIT.fullmatch(commit):
        raise RuntimeError("framework HEAD is not a full Git object")
    if descriptor is not None:
        try:
            relative = descriptor["path"].relative_to(ROOT).as_posix()
        except ValueError as exc:
            raise RuntimeError("campaign descriptor is outside the framework checkout") from exc
        retained = execute(["git", "show", f"{commit}:{relative}"], cwd=ROOT).stdout
        if retained != descriptor["content"]:
            raise RuntimeError("campaign descriptor bytes differ from the clean framework commit")
    return commit


def materialize(target: str, commit: str, campaign: str, selection: str) -> str:
    # Retained diagnostic materialization is not a candidate runtime surface.
    # Keep the implementation below for review, but make the public entry point
    # fail before Git archive creation, staging randomness, or SSH.
    raise RuntimeError(
        "construction blocked: direct srv5 materialization has no gate-bound "
        "candidate runtime authority"
    )

    target = checked_target(target)
    campaign = checked_name(campaign)
    if selection not in SELECTIONS:
        raise ValueError(f"selection must be one of {sorted(SELECTIONS)}")
    release = release_path(commit, campaign)
    archive = execute(["git", "archive", commit], cwd=ROOT).stdout
    parent = f"{REMOTE_RUNS}/{commit[:12]}"
    staging = f"{parent}/.staging-{campaign}-{secrets.token_hex(12)}"
    remote = f'''set -eu
umask 077
mkdir -p {parent}
test ! -e {release} && test ! -L {release} || exit 73
mkdir {staging}
cleanup() {{ rm -rf -- {staging}; }}
trap cleanup 0 1 2 15
tar -xf - -C {staging}
cd {staging}
mkdir -p .local/compiled/teastore
PYTHONPATH=src python3 -m obsplacement.selection \
 modules/teastore/activation/catalog.json \
 {SELECTIONS[selection]} \
 --manifest .local/compiled/teastore/manifest.json \
 --aop .local/compiled/teastore/aop.xml
cd {parent}
test ! -e {release} && test ! -L {release} || exit 74
mv -T -n -- {staging} {release}
test ! -e {staging} && test ! -L {staging} || exit 75
trap - 0 1 2 15
'''
    ssh(target, remote, data=archive)
    return release


def _write_remote(target: str, path: str, payload: bytes, *, executable: bool = False) -> None:
    mode = " && chmod +x " + path if executable else ""
    ssh(target, f"umask 077 && tee {path} >/dev/null{mode}", data=payload)


REMOTE_DEADLINE_CONTROLLER = r'''
import datetime
import hashlib
import json
import math
import os
import pathlib
import re
import signal
import stat
import subprocess
import sys
import time

COMPOSE_FILES = (
    "modules/teastore/deployment/compose/docker-compose_kieker.yaml",
    "modules/teastore/deployment/compose/docker-compose_rabbitmq.yaml",
    "modules/teastore/deployment/compose/isolation.override.yaml",
)
SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,68}$")
DOCKER_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


def utc(epoch=None):
    if epoch is None:
        epoch = time.time()
    return datetime.datetime.fromtimestamp(
        epoch, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def stream_summary(payload):
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "lineCount": len(payload.splitlines()),
    }


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise FileExistsError(str(path))
    temporary = path.with_name(path.name + ".pending")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    temporary.unlink()
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def parse_number(value, name, minimum):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(name + " is not numeric")
    if not math.isfinite(result) or result < minimum:
        raise ValueError(name + " is outside its allowed range")
    return result


def validate_paths(release):
    release_path = pathlib.Path(release)
    if not release_path.is_absolute():
        raise ValueError("release path is not absolute")
    resolved_release = release_path.resolve(strict=True)
    if resolved_release != release_path:
        raise ValueError("release path resolves through an alias")
    resolved = []
    for relative in COMPOSE_FILES:
        candidate = release_path / relative
        metadata = candidate.lstat()
        if not stat.S_ISREG(metadata.st_mode) or candidate.is_symlink():
            raise ValueError("compose file is not a retained regular file")
        exact = candidate.resolve(strict=True)
        if exact != resolved_release / relative:
            raise ValueError("compose file escapes the retained release")
        resolved.append(str(exact))
    return resolved_release, resolved


def available_timeout(requested, authorization_deadline, finalizer_reserve):
    available = authorization_deadline - time.time() - finalizer_reserve
    if available <= 0:
        return 0.0
    return min(requested, available)


def run_bounded(argv, cwd, env, timeout):
    empty = stream_summary(b"")
    result = {
        "attempted": False,
        "command": argv,
        "returnCode": None,
        "timedOut": False,
        "errorCode": None,
        "stdout": dict(empty),
        "stderr": dict(empty),
    }
    if timeout <= 0:
        result["errorCode"] = "authorization-budget-exhausted"
        return result, b""
    try:
        process = subprocess.Popen(
            argv, cwd=str(cwd), env=env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, start_new_session=True)
        result["attempted"] = True
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            result["timedOut"] = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                stdout, stderr = b"", b""
                result["errorCode"] = "subprocess-unreaped-after-kill"
        result["returnCode"] = process.poll()
        result["stdout"] = stream_summary(stdout)
        result["stderr"] = stream_summary(stderr)
        return result, stdout
    except OSError as exc:
        result["attempted"] = True
        result["returnCode"] = 127
        result["errorCode"] = type(exc).__name__
        return result, b""


def group_alive(process_group):
    try:
        os.killpg(process_group, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def wait_for_group(process, process_group, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        process.poll()
        if not group_alive(process_group):
            return True
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
    process.poll()
    return not group_alive(process_group)


def normalize_return_code(return_code):
    if return_code is None:
        return 70
    if return_code < 0:
        return 128 + abs(return_code)
    return min(return_code, 255)


def verify_resources(project, release_path, environment, query_timeout,
                     authorization_deadline, finalizer_reserve):
    label = "label=com.docker.compose.project=" + project
    commands = {
        "containers": ["docker", "ps", "-aq", "--no-trunc", "--filter", label],
        "networks": ["docker", "network", "ls", "-q", "--no-trunc", "--filter", label],
        "volumes": ["docker", "volume", "ls", "-q", "--filter", label],
    }
    queries = {}
    remaining = {}
    identifiers_by_kind = {}
    for kind in ("containers", "networks", "volumes"):
        result, stdout = run_bounded(
            commands[kind], release_path, environment,
            available_timeout(
                query_timeout, authorization_deadline, finalizer_reserve))
        raw_identifiers = [line for line in stdout.splitlines() if line]
        identifiers = []
        parse_valid = True
        for item in raw_identifiers:
            try:
                decoded = item.decode("ascii", errors="strict")
            except UnicodeDecodeError:
                parse_valid = False
                continue
            if not DOCKER_IDENTIFIER.fullmatch(decoded):
                parse_valid = False
            else:
                identifiers.append(decoded)
        result["identifiers"] = {
            "count": len(raw_identifiers),
            "sha256": hashlib.sha256(
                b"\n".join(sorted(raw_identifiers))).hexdigest(),
            "parseValid": parse_valid,
        }
        queries[kind] = result
        if result["returnCode"] == 0 and not result["timedOut"] and parse_valid:
            remaining[kind] = len(identifiers)
            identifiers_by_kind[kind] = identifiers
        else:
            remaining[kind] = None
            identifiers_by_kind[kind] = []
    return {
        "label": label,
        "queries": queries,
        "remaining": remaining,
        "clean": all(value == 0 for value in remaining.values()),
    }, identifiers_by_kind


def remove_scoped_resources(identifiers_by_kind, release_path, environment,
                            query_timeout, authorization_deadline,
                            finalizer_reserve):
    prefixes = {
        "containers": ["docker", "rm", "-f", "--"],
        "networks": ["docker", "network", "rm", "--"],
        "volumes": ["docker", "volume", "rm", "-f", "--"],
    }
    actions = {}
    for kind in ("containers", "networks", "volumes"):
        identifiers = identifiers_by_kind[kind]
        if identifiers:
            action, _ = run_bounded(
                prefixes[kind] + identifiers, release_path, environment,
                available_timeout(
                    query_timeout, authorization_deadline, finalizer_reserve))
        else:
            empty = stream_summary(b"")
            action = {
                "attempted": False,
                "command": prefixes[kind],
                "returnCode": None,
                "timedOut": False,
                "errorCode": None,
                "stdout": dict(empty),
                "stderr": dict(empty),
            }
        action["identifierCount"] = len(identifiers)
        action["identifiersSha256"] = hashlib.sha256(
            "\n".join(sorted(identifiers)).encode()).hexdigest()
        actions[kind] = action
    return actions


def main():
    if len(sys.argv) < 14:
        return 64
    (campaign, project, release, result_root, stop_epoch_raw,
     authorization_deadline_raw, term_grace_raw, kill_grace_raw,
     compose_timeout_raw, query_timeout_raw, finalizer_reserve_raw,
     log_path) = sys.argv[1:13]
    runner = sys.argv[13:]
    if (not SAFE.fullmatch(campaign) or project != "obst-" + campaign
            or not runner or runner[0] != "python3"):
        return 64
    stop_epoch = parse_number(stop_epoch_raw, "stop epoch", 1)
    authorization_deadline = parse_number(
        authorization_deadline_raw, "authorization deadline", stop_epoch + 1)
    term_grace = parse_number(term_grace_raw, "TERM grace", 0)
    kill_grace = parse_number(kill_grace_raw, "KILL grace", 0)
    compose_timeout = parse_number(compose_timeout_raw, "Compose timeout", 0)
    query_timeout = parse_number(query_timeout_raw, "query timeout", 0)
    finalizer_reserve = parse_number(
        finalizer_reserve_raw, "lease finalizer reserve", 1)
    release_path, compose_paths = validate_paths(release)
    result_path = pathlib.Path(result_root)
    if not result_path.is_absolute() or result_path.name != campaign:
        return 64
    log = pathlib.Path(log_path)
    if log != pathlib.Path(str(result_path) + ".log"):
        return 64
    receipt_path = result_path / "deadline-cleanup.json"
    if (receipt_path.exists() or receipt_path.is_symlink()
            or receipt_path.with_name(receipt_path.name + ".pending").exists()):
        return 79
    requested_signal = {"number": None}

    def request_stop(signum, _frame):
        requested_signal["number"] = signum

    for handled in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(handled, request_stop)
    environment = dict(os.environ)
    environment["OBSPLACEMENT_COMPOSE_PROJECT"] = project
    with log.open("ab", buffering=0) as output:
        process = subprocess.Popen(
            runner, cwd=str(release_path), env=environment, stdout=output,
            stderr=subprocess.STDOUT, start_new_session=True)
    process_group = process.pid
    identity_validated = False
    try:
        identity_validated = os.getpgid(process.pid) == process_group
    except ProcessLookupError:
        pass
    atomic_json(result_path / "harness-process.json", {
        "schemaVersion": 1, "campaign": campaign, "pid": process.pid,
        "processGroupId": process_group,
    })
    trigger_reason = None
    while process.poll() is None:
        if requested_signal["number"] is not None:
            trigger_reason = "launcher-signal"
            break
        if time.time() >= stop_epoch:
            trigger_reason = "authorization-stop-epoch"
            break
        time.sleep(min(0.1, max(0.0, stop_epoch - time.time())))
    if trigger_reason is None:
        trigger_reason = "runner-exit"

    triggered_epoch = time.time()
    blockers = []
    warnings = []
    if not identity_validated:
        blockers.append("process-group-identity-mismatch")
    alive_at_cleanup_start = group_alive(process_group)
    term_sent = False
    term_sent_at = None
    exited_during_term = None
    if alive_at_cleanup_start:
        if identity_validated:
            try:
                os.killpg(process_group, signal.SIGTERM)
                term_sent = True
                term_sent_at = utc()
            except ProcessLookupError:
                pass
        else:
            try:
                process.terminate()
                term_sent = True
                term_sent_at = utc()
            except ProcessLookupError:
                pass
        exited_during_term = wait_for_group(
            process, process_group, term_grace)
    kill_required = alive_at_cleanup_start and not exited_during_term
    kill_sent = False
    kill_sent_at = None
    if kill_required:
        try:
            if identity_validated:
                os.killpg(process_group, signal.SIGKILL)
            else:
                process.kill()
            kill_sent = True
            kill_sent_at = utc()
        except ProcessLookupError:
            pass
    if kill_required:
        group_gone = wait_for_group(
            process, process_group, kill_grace)
    else:
        process.poll()
        group_gone = not group_alive(process_group)
    try:
        process.wait(timeout=0.1)
    except subprocess.TimeoutExpired:
        pass
    if not group_gone:
        blockers.append("process-group-remains")

    compose_command = ["docker", "compose", "-p", project]
    for compose_file in compose_paths:
        compose_command.extend(["-f", compose_file])
    compose_command.extend(["down", "--volumes", "--remove-orphans"])
    compose_result, _ = run_bounded(
        compose_command, release_path, environment,
        available_timeout(compose_timeout, authorization_deadline, finalizer_reserve))
    if compose_result["timedOut"]:
        warnings.append("compose-teardown-timed-out")
    if compose_result["returnCode"] != 0:
        warnings.append("compose-teardown-failed")
    initial_verification, scoped_identifiers = verify_resources(
        project, release_path, environment, query_timeout,
        authorization_deadline, finalizer_reserve)
    fallback_required = (compose_result["returnCode"] != 0
                         or compose_result["timedOut"]
                         or not initial_verification["clean"])
    if fallback_required:
        fallback_actions = remove_scoped_resources(
            scoped_identifiers, release_path, environment, query_timeout,
            authorization_deadline, finalizer_reserve)
    else:
        fallback_actions = remove_scoped_resources(
            {kind: [] for kind in ("containers", "networks", "volumes")},
            release_path, environment, query_timeout,
            authorization_deadline, finalizer_reserve)
    for kind, action in fallback_actions.items():
        if action["attempted"] and (action["returnCode"] != 0 or action["timedOut"]):
            warnings.append("fallback-" + kind + "-failed")
    final_verification, _ = verify_resources(
        project, release_path, environment, query_timeout,
        authorization_deadline, finalizer_reserve)
    for kind, count in final_verification["remaining"].items():
        if count is None:
            blockers.append("verification-" + kind + "-failed")
        elif count:
            blockers.append("remaining-" + kind)
    completed_epoch = time.time()
    before_deadline = completed_epoch < authorization_deadline
    finalizer_window = completed_epoch <= authorization_deadline - finalizer_reserve
    if not before_deadline:
        blockers.append("authorization-deadline-reached")
    if not finalizer_window:
        blockers.append("lease-finalizer-window-exhausted")
    blockers = sorted(set(blockers))
    warnings = sorted(set(warnings))
    receipt = {
        "schemaVersion": 1,
        "kind": "deadline-cleanup",
        "campaign": campaign,
        "composeProject": project,
        "release": release,
        "resultRoot": result_root,
        "trigger": {
            "reason": trigger_reason,
            "signal": requested_signal["number"],
            "stopEpoch": int(stop_epoch),
            "authorizationDeadlineEpoch": int(authorization_deadline),
            "triggeredAt": utc(triggered_epoch),
        },
        "processGroup": {
            "pid": process.pid,
            "processGroupId": process_group,
            "identityValidated": identity_validated,
            "aliveAtCleanupStart": alive_at_cleanup_start,
            "termSent": term_sent,
            "termSentAt": term_sent_at,
            "exitedDuringTermGrace": exited_during_term,
            "killRequired": kill_required,
            "killSent": kill_sent,
            "killSentAt": kill_sent_at,
            "gone": group_gone,
            "runnerReturnCode": process.poll(),
        },
        "composeTeardown": {
            **compose_result,
            "cwd": release,
            "composeFiles": list(COMPOSE_FILES),
        },
        "verification": {
            "initial": initial_verification,
            "fallback": {
                "required": fallback_required,
                "actions": fallback_actions,
            },
            "final": final_verification,
        },
        "authorization": {
            "completedAt": utc(completed_epoch),
            "completedAtEpoch": completed_epoch,
            "beforeDeadline": before_deadline,
            "leaseFinalizerReserveSeconds": finalizer_reserve,
            "leaseFinalizerWindowAvailable": finalizer_window,
            "leaseReleaseDelegatedToLauncherFinalizer": True,
        },
        "outcome": "clean" if not blockers else "blocked",
        "blockers": blockers,
        "warnings": warnings,
    }
    try:
        atomic_json(receipt_path, receipt)
    except FileExistsError:
        return 125
    if blockers:
        return 125
    if trigger_reason == "authorization-stop-epoch":
        return 124
    if trigger_reason == "launcher-signal":
        return 130
    return normalize_return_code(process.returncode)


try:
    raise SystemExit(main())
except (OSError, ValueError) as exc:
    sys.stderr.write("deadline controller refused runtime state: " + type(exc).__name__ + "\n")
    raise SystemExit(78)
'''.lstrip().encode()


def launch(target: str, campaign: str, descriptor_path: Path = DEFAULT_DESCRIPTOR,
           admission_path: Path | None = None) -> dict[str, Any]:
    campaign = checked_name(campaign)
    target = checked_target(target)
    project = campaign_project(campaign)
    descriptor = load_descriptor(descriptor_path)
    if admission_path is None:
        raise ValueError("launch requires an explicit runtime admission receipt")
    admission = load_runtime_admission(admission_path, descriptor)
    if target != descriptor["target"]:
        raise ValueError(f"runtime target {target} differs from descriptor target {descriptor['target']}")
    commit = framework_commit(descriptor)
    release = release_path(commit, campaign)
    preflight_result = preflight(target, campaign, release=release, settle_seconds=60)
    # The preflight consumes real time.  Re-admit immediately before the first
    # external mutation so a stale receipt cannot borrow time from the cleanup reserve.
    admission = load_runtime_admission(admission_path, descriptor)
    preflight_path = persist_preflight(
        campaign, target=target, commit=commit,
        descriptor=descriptor, proof=preflight_result,
    )
    materialize(target, commit, campaign, descriptor["selection"])
    expected = descriptor["blocks"] * len(descriptor["postures"])
    result_root = result_path(campaign)
    log = f"{REMOTE_RESULTS}/{campaign}.log"
    exit_file = f"{REMOTE_RESULTS}/{campaign}.exit"
    launcher = f"{release}/.local/launch-{campaign}.sh"
    controller = f"{release}/.local/deadline-controller.py"
    ssh(target, f"mkdir -p {result_root} {release}/.local")
    control = {
        "schemaVersion": 2, "campaign": campaign, "target": target,
        "session": f"teastore-{campaign}", "composeProject": project,
        "frameworkCommit": commit, "sutReferenceCommit": SUT_REFERENCE_COMMIT,
        "release": release, "resultRoot": result_root,
        "descriptorId": descriptor["id"], "descriptorSha256": descriptor["sha256"],
        "expectedReceipts": expected,
        "runtimeAdmissionSha256": admission["sha256"],
        "authorizationDeadlineEpoch": admission["deadlineEpoch"],
        "experimentStopEpoch": admission["stopEpoch"],
        "cleanupReserveSeconds": admission["cleanupReserveSeconds"],
    }
    _write_remote(target, f"{result_root}/harness-owner.json",
                  (json.dumps(control, sort_keys=True, separators=(",", ":")) + "\n").encode())
    _write_remote(target, f"{result_root}/campaign-descriptor.json", descriptor["content"])
    _write_remote(target, f"{result_root}/runtime-admission.json", admission["content"])
    _write_remote(target, f"{result_root}/runtime-admission-source.json",
                  CANDIDATE_DESCRIPTOR.read_bytes())
    _write_remote(target, controller, REMOTE_DEADLINE_CONTROLLER)
    postures = ",".join(descriptor["postures"])
    script = f'''#!/bin/sh
cd {release} || exit 90
export OBSPLACEMENT_COMPOSE_PROJECT={project}
lease_path={HOST_LEASE_PATH}
lease_evidence={result_root}/execution-lease.json
lease_attempted_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
lease_acquired_at=
lease_acquired=0
lease_acquire_rc=1
authorization_deadline_epoch={admission["deadlineEpoch"]}
experiment_stop_epoch={admission["stopEpoch"]}
controller_pid=
write_pending_lease() {{
 printf '{{"schemaVersion":1,"scope":"fb14srv5:teastore-performance","lockPath":"{HOST_LEASE_PATH}","campaign":"{campaign}","launcherPid":%s,"acquisition":{{"attemptedAt":"%s","acquired":true,"acquiredAt":"%s","returnCode":0,"mechanism":"flock-nonblocking-fd"}},"release":{{"requestedAt":null,"unlockReturnCode":null,"verificationReturnCode":null,"observed":false,"mechanism":"unlock-close-and-nonblocking-reacquire"}}}}\n' \
  "$$" "$lease_attempted_at" "$lease_acquired_at" >"$lease_evidence.tmp"
 mv "$lease_evidence.tmp" "$lease_evidence"
}}
write_rejected_lease() {{
 printf '{{"schemaVersion":1,"scope":"fb14srv5:teastore-performance","lockPath":"{HOST_LEASE_PATH}","campaign":"{campaign}","launcherPid":%s,"acquisition":{{"attemptedAt":"%s","acquired":false,"acquiredAt":null,"returnCode":%s,"mechanism":"flock-nonblocking-fd"}},"release":{{"requestedAt":null,"unlockReturnCode":null,"verificationReturnCode":null,"observed":false,"mechanism":"unlock-close-and-nonblocking-reacquire"}}}}\n' \
  "$$" "$lease_attempted_at" "$lease_acquire_rc" >"$lease_evidence.tmp"
 mv "$lease_evidence.tmp" "$lease_evidence"
}}
finish() {{
 code="$1"
 trap - HUP INT TERM
 if [ "$lease_acquired" -eq 1 ]; then
  release_requested_at=$(utc_now)
  flock -u 9
  unlock_rc=$?
  exec 9>&-
  exec 8>>"$lease_path"
  if flock -n 8; then
   verification_rc=0
   observed=true
   flock -u 8 || true
  else
   verification_rc=$?
   observed=false
  fi
  exec 8>&-
  printf '{{"schemaVersion":1,"scope":"fb14srv5:teastore-performance","lockPath":"{HOST_LEASE_PATH}","campaign":"{campaign}","launcherPid":%s,"acquisition":{{"attemptedAt":"%s","acquired":true,"acquiredAt":"%s","returnCode":0,"mechanism":"flock-nonblocking-fd"}},"release":{{"requestedAt":"%s","unlockReturnCode":%s,"verificationReturnCode":%s,"observed":%s,"mechanism":"unlock-close-and-nonblocking-reacquire"}}}}\n' \
   "$$" "$lease_attempted_at" "$lease_acquired_at" "$release_requested_at" \
   "$unlock_rc" "$verification_rc" "$observed" >"$lease_evidence.tmp"
  mv "$lease_evidence.tmp" "$lease_evidence"
 else
  write_rejected_lease
 fi
 printf '%s\n' "$code" >{exit_file}.tmp
 mv {exit_file}.tmp {exit_file}
 exit "$code"
}}
terminate_controller() {{
 trap - HUP INT TERM
 if [ -n "$controller_pid" ]; then
  kill -TERM "$controller_pid" 2>/dev/null || true
  wait "$controller_pid" 2>/dev/null
  controller_code=$?
 else
  controller_code=130
 fi
 finish "$controller_code"
}}
exec 9>>"$lease_path"
flock -n 9
lease_acquire_rc=$?
if [ "$lease_acquire_rc" -ne 0 ]; then
 write_rejected_lease
 finish 75
fi
lease_acquired=1
utc_now() {{
 python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"))'
}}
lease_acquired_at=$(utc_now)
write_pending_lease
if [ "$?" -ne 0 ]; then
 finish 76
fi
current_epoch=$(date +%s)
if [ "$current_epoch" -ge "$experiment_stop_epoch" ]; then
 finish 77
fi
python3 {controller} \
 {campaign} {project} {release} {result_root} \
 "$experiment_stop_epoch" "$authorization_deadline_epoch" \
 {DEADLINE_TERM_GRACE_SECONDS} {DEADLINE_KILL_GRACE_SECONDS} \
 {DEADLINE_COMPOSE_TIMEOUT_SECONDS} {DEADLINE_QUERY_TIMEOUT_SECONDS} \
 {DEADLINE_LEASE_FINALIZER_SECONDS} {log} \
 python3 modules/teastore/execution/performance_campaign.py \
 --output {result_root} --framework-commit {commit} --sut-reference-commit {SUT_REFERENCE_COMMIT} \
 --descriptor-id {descriptor["id"]} --descriptor-sha256 {descriptor["sha256"]} \
 --evidence-label {descriptor["evidenceLabel"]} \
 --blocks {descriptor["blocks"]} --seed {descriptor["seed"]} \
 --warmup {descriptor["warmup"]} --duration {descriptor["duration"]} \
 --rate {descriptor["rate"]} --concurrency {descriptor["concurrency"]} \
 --postures {postures} --fault {descriptor["fault"]} \
 --fault-at {descriptor["faultAt"]} --outage {descriptor["outage"]} \
 --selection-id {descriptor["selection"]} &
controller_pid=$!
trap terminate_controller HUP INT TERM
wait "$controller_pid"
code=$?
finish "$code"
'''.encode()
    _write_remote(target, launcher, script, executable=True)
    ssh(target, f"tmux new-session -d -s teastore-{campaign} {launcher}")
    deadline = time.time() + 30
    current = None
    while time.time() < deadline:
        current = status(target, campaign, expected)
        if current["active"] or current["exitCode"]:
            break
        time.sleep(1)
    if not current or (not current["active"] and not current["exitCode"]):
        raise RuntimeError("launch acknowledgement timed out")
    if current["exitCode"] and current["exitCode"] != "0":
        raise RuntimeError(f"campaign exited during launch with code {current['exitCode']}")
    return {"commit": commit, "descriptorId": descriptor["id"],
            "descriptorSha256": descriptor["sha256"], "preflight": preflight_result,
            "preflightEvidence": str(preflight_path),
            "runtimeAdmissionSha256": admission["sha256"],
            "authorizationDeadline": admission["receipt"]["authorizationDeadline"],
            "experimentStopEpoch": admission["stopEpoch"],
            "status": current}


def safe_extract(payload: bytes, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        root = destination.resolve()
        seen: set[str] = set()
        planned: list[tuple[tarfile.TarInfo, Path]] = []
        seen_targets: set[Path] = set()
        members = archive.getmembers()
        for member in members:
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise RuntimeError(f"unsupported archive member: {member.name}")
            normalized_name = member.name.rstrip("/") if member.isdir() else member.name
            parts = Path(normalized_name).parts
            if (normalized_name in seen or not normalized_name or Path(normalized_name).is_absolute()
                    or any(part in {"", ".", ".."} for part in parts)):
                raise RuntimeError(f"duplicate or non-normal archive member: {member.name}")
            seen.add(normalized_name)
            target = (destination / normalized_name).resolve()
            if root not in target.parents and target != root:
                raise RuntimeError(f"unsafe archive member: {member.name}")
            if target in seen_targets:
                raise RuntimeError(f"archive members resolve to the same path: {member.name}")
            seen_targets.add(target)
            planned.append((member, target))
        for member, target in planned:
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                target.chmod(0o700)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.parent.chmod(0o700)
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError(f"archive file has no readable payload: {member.name}")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o600)


OWNER_FIELDS_V1 = {
    "schemaVersion", "campaign", "target", "session", "composeProject",
    "frameworkCommit", "sutReferenceCommit", "release", "resultRoot",
    "descriptorId", "descriptorSha256", "expectedReceipts",
}
OWNER_FIELDS_V2 = OWNER_FIELDS_V1 | {
    "runtimeAdmissionSha256", "authorizationDeadlineEpoch",
    "experimentStopEpoch", "cleanupReserveSeconds",
}


def validate_owner(value: object, *, target: str, campaign: str,
    descriptor: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        if not isinstance(value, dict):
            raise ValueError("owner must be an object")
        version = value.get("schemaVersion")
        if type(version) is not int or version not in {1, 2}:
            raise ValueError("owner.schemaVersion must be integer 1 or 2")
        if version == 1:
            owner = _exact_keys(value, OWNER_FIELDS_V1, "owner")
        else:
            owner = _exact_keys(value, OWNER_FIELDS_V2, "owner")
        campaign = checked_name(campaign)
        target = checked_target(target)
        framework = owner["frameworkCommit"]
        descriptor_id = owner["descriptorId"]
        descriptor_digest = owner["descriptorSha256"]
        if (owner["campaign"] != campaign
                or owner["target"] != target or owner["session"] != f"teastore-{campaign}"
                or owner["composeProject"] != campaign_project(campaign)
                or not isinstance(framework, str) or not COMMIT.fullmatch(framework)
                or owner["sutReferenceCommit"] != SUT_REFERENCE_COMMIT
                or owner["release"] != release_path(framework, campaign)
                or owner["resultRoot"] != result_path(campaign)
                or not isinstance(descriptor_id, str) or checked_name(descriptor_id) != descriptor_id
                or not isinstance(descriptor_digest, str) or not SHA256.fullmatch(descriptor_digest)
                or isinstance(owner["expectedReceipts"], bool)
                or not isinstance(owner["expectedReceipts"], int)
                or owner["expectedReceipts"] < 1):
            raise RuntimeError("owner record does not bind the requested campaign")
        if version == 2:
            deadline = owner["authorizationDeadlineEpoch"]
            stop = owner["experimentStopEpoch"]
            reserve = owner["cleanupReserveSeconds"]
            if (not isinstance(owner["runtimeAdmissionSha256"], str)
                    or not SHA256.fullmatch(owner["runtimeAdmissionSha256"])
                    or isinstance(deadline, bool) or not isinstance(deadline, int)
                    or isinstance(stop, bool) or not isinstance(stop, int)
                    or isinstance(reserve, bool) or not isinstance(reserve, int)
                    or reserve != DEADLINE_CLEANUP_RESERVE_SECONDS
                    or stop <= 0 or deadline - stop != reserve):
                raise RuntimeError("owner record has an invalid runtime admission boundary")
        if descriptor is not None:
            expected = descriptor["blocks"] * len(descriptor["postures"])
            if (owner["descriptorId"] != descriptor["id"]
                    or owner["descriptorSha256"] != descriptor["sha256"]
                    or owner["expectedReceipts"] != expected
                    or owner["target"] != descriptor["target"]):
                raise RuntimeError("owner record differs from the campaign descriptor")
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"owner record is invalid: {exc}") from exc
    return owner


def _local_owner(path: Path, *, target: str, campaign: str,
                 descriptor: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        value = _loads_strict(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"owner record is unreadable: {exc}") from exc
    return validate_owner(value, target=target, campaign=campaign, descriptor=descriptor)


def fetch(target: str, campaign: str, destination: Path,
          descriptor: dict[str, Any]) -> Path:
    target = checked_target(target)
    campaign = checked_name(campaign)
    destination.mkdir(parents=True, exist_ok=True)
    destination = destination.resolve()
    final = destination / campaign
    if final.exists() or final.is_symlink():
        raise RuntimeError(f"evidence destination already exists: {final}")
    payload = ssh(
        target,
        f"tar -C {REMOTE_RESULTS} -czf - {campaign} {campaign}.log {campaign}.exit",
    ).stdout
    staging = Path(tempfile.mkdtemp(prefix=f".{campaign}.fetch-", dir=destination))
    try:
        safe_extract(payload, staging)
        expected_top = {campaign, f"{campaign}.log", f"{campaign}.exit"}
        if {item.name for item in staging.iterdir()} != expected_top:
            raise RuntimeError("fetched archive top-level membership differs from protocol")
        root = staging / campaign
        if not root.is_dir() or root.is_symlink():
            raise RuntimeError("fetched campaign root is not a regular directory")
        for suffix, retained_name in ((".log", "harness.log"), (".exit", "harness.exit")):
            source = staging / f"{campaign}{suffix}"
            if not source.is_file() or source.is_symlink():
                raise RuntimeError(f"fetched campaign is missing {source.name}")
            source.replace(root / retained_name)
        _local_owner(root / "harness-owner.json", target=target,
                     campaign=campaign, descriptor=descriptor)
        if final.exists() or final.is_symlink():
            raise RuntimeError(f"evidence destination appeared during fetch: {final}")
        os.replace(root, final)
        return final
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def validate_bundle(root: Path, *, blocks: int = 5,
                    postures_expected: tuple[str, ...] = ("none", "selected", "full")) -> dict[str, Any]:
    """Compatibility-level receipt validation; terminal validation is authoritative."""
    receipts = sorted(root.glob("*/receipt.json"))
    failures: list[dict[str, Any]] = []
    schedule_path = root / "schedule.json"
    if not schedule_path.exists():
        failures.append({"run": "campaign", "blockers": ["missing schedule.json"]})
        schedule: dict[str, Any] = {}
    else:
        try:
            schedule = json.loads(schedule_path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            schedule = {}
            failures.append({"run": "campaign", "blockers": [f"invalid schedule.json: {exc}"]})
    configuration = schedule.get("configuration") if isinstance(schedule, dict) else None
    if not isinstance(configuration, dict):
        failures.append({"run": "campaign", "blockers": ["schedule configuration is missing"]})
        configuration = None
    if configuration:
        try:
            configured_postures = tuple(configuration["postures"])
            if configuration["blocks"] != blocks or configured_postures != postures_expected:
                failures.append({"run": "campaign", "blockers": [
                    f"validation parameters differ from recorded configuration: blocks={configuration['blocks']}, postures={configured_postures}"
                ]})
            expected_run_ids = {f"b{item['block']:02d}-{item['posture']}" for item in schedule.get("runs", [])}
            actual_run_ids = {path.parent.name for path in receipts}
            if actual_run_ids != expected_run_ids:
                failures.append({"run": "campaign", "blockers": ["receipt run IDs differ from immutable schedule"]})
        except (KeyError, TypeError, ValueError) as exc:
            failures.append({"run": "campaign", "blockers": [f"invalid schedule structure: {exc}"]})
    postures: dict[str, int] = {}
    for path in receipts:
        try:
            receipt = json.loads(path.read_text())
            posture = receipt["posture"]
            postures[posture] = postures.get(posture, 0) + 1
            blockers = receipt.get("canonicality", {}).get("blockers", [])
            if blockers:
                failures.append({"run": receipt.get("runId"), "blockers": blockers})
            if receipt["latencyMs"]["count"] != receipt["workload"]["completed"]:
                failures.append({"run": receipt.get("runId"), "blockers": ["latency denominator mismatch"]})
            if receipt.get("teardown", {}).get("projectClean") is not True:
                failures.append({"run": receipt.get("runId"), "blockers": ["owned project teardown is not proven"]})
            if configuration:
                source = receipt.get("source", {})
                mapping = (
                    ("frameworkCommit", "frameworkCommit"),
                    ("sutReferenceCommit", "sutReferenceCommit"),
                    ("selectionId", "selectionId"), ("selectionSourceSha256", "selectionSourceSha256"),
                    ("descriptorId", "descriptorId"), ("descriptorSha256", "descriptorSha256"),
                    ("evidenceLabel", "evidenceLabel"),
                )
                mismatched = [field for field, key in mapping if source.get(field) != configuration.get(key)]
                if mismatched:
                    failures.append({"run": receipt.get("runId"),
                                     "blockers": [f"source differs from schedule: {mismatched}"]})
                expected_fault = configuration.get("fault")
                actual_fault = (receipt.get("intervention") or {}).get("scenario", "none")
                if actual_fault != expected_fault:
                    failures.append({"run": receipt.get("runId"), "blockers": [
                        f"intervention {actual_fault} differs from scheduled {expected_fault}"]})
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            failures.append({"run": path.parent.name, "blockers": [f"invalid receipt: {exc}"]})
    expected = {posture: blocks for posture in postures_expected}
    if postures != expected:
        failures.append({"run": "campaign", "blockers": [f"posture counts {postures}, expected {expected}"]})
    return {"verdict": "pass" if not failures else "blocked", "receipts": len(receipts),
            "postures": postures, "failures": failures}


def _terminal_module():
    path = ROOT / "modules/teastore/validation/srv5_terminal.py"
    spec = importlib.util.spec_from_file_location("teastore_srv5_terminal", path)
    if not spec or not spec.loader:
        raise RuntimeError("unable to load TeaStore terminal validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def terminal_validate(root: Path, descriptor: dict[str, Any], current: dict[str, Any],
                      remote_state: dict[str, Any], *, seal: bool,
                      expected_manifest_sha256: str | None = None) -> dict[str, Any]:
    module = _terminal_module()
    manifest = root / module.MANIFEST_NAME
    if seal:
        for name, document in (
            ("terminal-status.json", current),
            ("remote-final-state.json", remote_state),
        ):
            path = root / name
            try:
                with path.open("x", encoding="utf-8") as handle:
                    json.dump(document, handle, indent=2, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except FileExistsError as exc:
                raise RuntimeError(f"fetched evidence already contains {name}") from exc
        module.write_manifest(root)
    elif not manifest.is_file() or manifest.is_symlink():
        raise RuntimeError("revalidation requires the existing one-time content manifest")
    if seal:
        expected_manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    elif (not isinstance(expected_manifest_sha256, str)
          or not SHA256.fullmatch(expected_manifest_sha256)):
        raise RuntimeError("revalidation requires the externally retained manifest SHA-256")
    report = module.validate_campaign(
        root, root / "campaign-descriptor.json", current, remote_state,
        expected_manifest_sha256=expected_manifest_sha256,
        require_fresh_remote=seal,
    )
    (root / "terminal-validation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def persist_manifest_seal(root: Path, *, owner: dict[str, Any],
                          report: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    """Retain and emit the manifest digest outside the sealed evidence root."""

    manifest = report.get("manifest")
    digest = manifest.get("manifestSha256") if isinstance(manifest, dict) else None
    size = manifest.get("manifestBytes") if isinstance(manifest, dict) else None
    if (not isinstance(digest, str) or not SHA256.fullmatch(digest)
            or isinstance(size, bool) or not isinstance(size, int) or size < 1):
        raise RuntimeError("terminal validation did not return a usable manifest anchor")
    record = {
        "schemaVersion": 1,
        "recordedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "campaign": owner["campaign"],
        "target": owner["target"],
        "frameworkCommit": owner["frameworkCommit"],
        "descriptorId": owner["descriptorId"],
        "descriptorSha256": owner["descriptorSha256"],
        "manifestSha256": digest,
        "manifestBytes": size,
        "terminalVerdict": report.get("verdict"),
    }
    path = root.parent / f"{owner['campaign']}.manifest-seal.json"
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise RuntimeError(f"external manifest anchor already exists: {path}") from exc
    return path, record


def wait_fetch(target: str, campaign: str, destination: Path, poll: int,
               descriptor_path: Path = DEFAULT_DESCRIPTOR) -> dict[str, Any]:
    descriptor = load_descriptor(descriptor_path)
    preflight_payload, preflight_record = retained_preflight(
        campaign, target=target, descriptor=descriptor)
    expected = descriptor["blocks"] * len(descriptor["postures"])
    while True:
        current = status(target, campaign, expected)
        print(json.dumps(current), flush=True)
        if not current["active"]:
            if current["exitCode"] == "":
                raise RuntimeError("campaign stopped without an exit receipt")
            break
        time.sleep(poll)
    root = fetch(target, campaign, destination, descriptor)
    owner = _local_owner(root / "harness-owner.json", target=target,
                         campaign=campaign, descriptor=descriptor)
    install_preflight(root, preflight_payload, preflight_record, owner)
    remote_state = inventory(target, campaign, release=owner["release"])
    report = terminal_validate(root, descriptor, current, remote_state, seal=True)
    seal_path, seal_record = persist_manifest_seal(root, owner=owner, report=report)
    return {"status": current, "evidence": str(root), "remoteState": remote_state,
            "validation": report, "manifestSeal": seal_record,
            "manifestSealPath": str(seal_path)}


def read_owner(target: str, campaign: str,
               descriptor: dict[str, Any] | None = None) -> dict[str, Any]:
    target = checked_target(target)
    campaign = checked_name(campaign)
    root = result_path(campaign)
    owner = _strict_json(ssh(target, f"cat {root}/harness-owner.json").stdout, "owner")
    return validate_owner(owner, target=target, campaign=campaign, descriptor=descriptor)


REMOTE_ABORT = r'''
import json, os, pathlib, signal, subprocess, sys, time
campaign, project, session, release, result_root = sys.argv[1:]
def query(argv, **kwargs):
    try:
        value = subprocess.run(argv, text=True, capture_output=True, check=False, **kwargs)
        return {"command": argv, "returnCode": value.returncode,
                "stdout": value.stdout, "stderr": value.stderr}
    except OSError as exc:
        return {"command": argv, "returnCode": 127, "stdout": "", "stderr": str(exc)}
actions = []
process_path = pathlib.Path(result_root, "harness-process.json")
if process_path.is_file():
    process_action = {"kind": "owned-process-group", "path": str(process_path),
                      "validated": False, "termSent": False, "killSent": False,
                      "error": None}
    try:
        process = json.loads(process_path.read_text())
        if (not isinstance(process, dict) or set(process) != {
                "schemaVersion", "campaign", "pid", "processGroupId"}
                or type(process.get("schemaVersion")) is not int
                or process.get("schemaVersion") != 1 or process.get("campaign") != campaign
                or isinstance(process.get("pid"), bool) or not isinstance(process.get("pid"), int)
                or process.get("pid") <= 1 or process.get("processGroupId") != process.get("pid")):
            raise ValueError("process receipt fields or identity differ")
        pid = process["pid"]
        stat = pathlib.Path("/proc", str(pid), "stat").read_text()
        fields = stat.rsplit(")", 1)[1].split()
        process_group = int(fields[2])
        command = pathlib.Path("/proc", str(pid), "cmdline").read_bytes().replace(
            b"\0", b" ").decode(errors="replace")
        cwd = os.path.realpath(pathlib.Path("/proc", str(pid), "cwd"))
        if (process_group != pid or cwd != release
                or "modules/teastore/execution/performance_campaign.py" not in command):
            raise ValueError("live process does not match the owned campaign group")
        process_action.update({"validated": True, "pid": pid,
                               "processGroupId": process_group, "command": command,
                               "cwd": cwd})
        os.killpg(pid, signal.SIGTERM); process_action["termSent"] = True
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                os.killpg(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.25)
        else:
            os.killpg(pid, signal.SIGKILL); process_action["killSent"] = True
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        process_action["error"] = type(exc).__name__ + ": " + str(exc)
    actions.append(process_action)
present = query(["tmux", "has-session", "-t", session])
if present["returnCode"] == 0:
    actions.append(query(["tmux", "kill-session", "-t", session]))
elif present["returnCode"] != 1:
    actions.append(present)
env = dict(os.environ); env["OBSPLACEMENT_COMPOSE_PROJECT"] = project
compose = ["docker", "compose", "-p", project,
           "-f", "modules/teastore/deployment/compose/docker-compose_kieker.yaml",
           "-f", "modules/teastore/deployment/compose/docker-compose_rabbitmq.yaml",
           "-f", "modules/teastore/deployment/compose/isolation.override.yaml",
           "down", "-v", "--remove-orphans"]
if pathlib.Path(release).is_dir():
    actions.append(query(compose, cwd=release, env=env))
label = "label=com.docker.compose.project=" + project
for list_command, remove_prefix in (
    (["docker", "ps", "-aq", "--filter", label], ["docker", "rm", "-f"]),
    (["docker", "network", "ls", "-q", "--filter", label], ["docker", "network", "rm"]),
    (["docker", "volume", "ls", "-q", "--filter", label], ["docker", "volume", "rm"]),
):
    listed = query(list_command); actions.append(listed)
    if listed["returnCode"] == 0:
        identifiers = [line for line in listed["stdout"].splitlines() if line]
        if identifiers:
            actions.append(query(remove_prefix + identifiers))
receipt = {"schemaVersion": 1, "campaign": campaign, "composeProject": project,
           "session": session, "release": release, "actions": actions}
pathlib.Path(result_root).mkdir(parents=True, exist_ok=True)
pathlib.Path(result_root, "abort.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
exit_path = pathlib.Path(result_root + ".exit")
if not exit_path.exists(): exit_path.write_text("130\n")
print(json.dumps(receipt, separators=(",", ":")))
'''.lstrip().encode()


def abort_owned(target: str, campaign: str,
                descriptor_path: Path = DEFAULT_DESCRIPTOR) -> dict[str, Any]:
    """Clean up one proven-owned campaign as a cleanup-only safety carveout.

    This emergency path does not launch, materialize, retry, or authorize a
    campaign.  It may mutate only after the retained owner receipt binds the
    exact campaign resources, and it verifies that those resources are gone.
    """

    descriptor = load_descriptor(descriptor_path)
    target = checked_target(target)
    if target != descriptor["target"]:
        raise ValueError(f"runtime target {target} differs from descriptor target {descriptor['target']}")
    owner = read_owner(target, campaign, descriptor)
    result_root = result_path(campaign)
    remote = (f"python3 - {campaign} {owner['composeProject']} {owner['session']} "
              f"{owner['release']} {result_root}")
    actions = _strict_json(ssh(target, remote, data=REMOTE_ABORT).stdout, "abort")
    proof = inventory(target, campaign, release=owner["release"])
    clean = (proof["queryPassed"] and not proof["active"] and not proof["openWriters"]
             and not any(proof["projectResources"].get(key) for key in ("containers", "networks", "volumes")))
    return {"verdict": "pass" if clean else "blocked", "owner": owner,
            "actions": actions, "finalState": proof}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inventory", "launch", "status", "wait-fetch", "validate", "abort"))
    parser.add_argument("--target")
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    parser.add_argument("--admission", type=Path,
                        help="runtime-admission receipt required for launch")
    parser.add_argument("--destination", type=Path, default=Path(".local/evidence"))
    parser.add_argument("--poll", type=int, default=60)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    try:
        descriptor = load_descriptor(args.descriptor)
        target = args.target or descriptor["target"]
        if args.poll <= 0:
            raise ValueError("poll must be positive")
        if args.command == "inventory":
            result = inventory(target, args.campaign)
        elif args.command == "launch":
            result = launch(target, args.campaign, args.descriptor, args.admission)
        elif args.command == "status":
            result = status(target, args.campaign, descriptor["blocks"] * len(descriptor["postures"]))
        elif args.command == "wait-fetch":
            result = wait_fetch(target, args.campaign, args.destination, args.poll, args.descriptor)
        elif args.command == "abort":
            result = abort_owned(target, args.campaign, args.descriptor)
        else:
            root = args.destination / args.campaign
            _local_owner(root / "harness-owner.json", target=target,
                         campaign=args.campaign, descriptor=descriptor)
            current = _strict_local_json_document(
                (root / "terminal-status.json").read_bytes(), "retained terminal status")
            remote_state = _strict_local_json_document(
                (root / "remote-final-state.json").read_bytes(), "retained remote final state")
            result = terminal_validate(
                root, descriptor, current, remote_state, seal=False,
                expected_manifest_sha256=args.manifest_sha256)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    verdict = result.get("verdict", result.get("validation", {}).get("verdict", "pass"))
    return 0 if verdict == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
