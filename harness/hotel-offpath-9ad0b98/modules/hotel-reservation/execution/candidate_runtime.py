#!/usr/bin/env python3
"""Human-gated, plan-consuming Hotel candidate runtime admission and adapter."""
from __future__ import annotations

import argparse
import ast
import copy
import fcntl
import grp
import hashlib
import importlib.util
import io
import json
import os
import pwd
import re
import shlex
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, NoReturn, Protocol


# Never write bytecode from this process.  `_load_compiler` imports the frozen
# compiler out of the installed checkout, and on the target that checkout is the
# payload the `installed-bundle-bytes` seam has just verified byte-for-byte.  A
# `__pycache__/candidate_pilot.cpython-39.pyc` written on first import adds a file
# the manifest never declared, so `observedEntriesSha256` stops matching
# `expectedEntriesSha256` and readiness fails with "installed payload does not
# replay" -- which is exactly what happened to Hotel #6 on 2026-09-21 (2422 files
# observed against 2418 installed).
#
# This is set in-process rather than by argv or environment on purpose: target
# invocations are `python3 -I`, whose isolated mode implies `-E`, so
# PYTHONDONTWRITEBYTECODE is ignored; and adding `-B` would shift argv positions
# that retained readiness evidence is replayed against byte-for-byte
# (`_replayed_spelling(facts, 4, ...)`).  Suppressing the write keeps the gate as
# strict as it was -- a stray .pyc still fails the seam, it just is not this
# process that creates one.  Controller-side it is a bonus: a stale .pyc served
# from a cache silently substituted an OLD pinned plan digest earlier the same day.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "modules" / "hotel-reservation"
DESCRIPTOR = ROOT / "pipelines" / "campaigns" / "hotel-reservation-selected-v1.json"
POLICY = MODULE / "execution" / "runtime-policy.json"
STUDY_EPOCH = "hotel-reservation-selected-v1"
CHANGE_ID = "admit-hotel-reservation-candidate-runtime"
# Host condition v2 (2026-09-21): the dps_training_k co-tenant of campaigns #1-#5 is
# decommissioned and fb14srv4 runs zero foreign containers.  Absence is verified and
# recorded positively -- an unverified absence is not evidence.  The v1 condition
# lives on, verbatim, in the retired posture-ceiling record keyed by the v1 plan digest.
HOST_CONDITION_ID = "no-foreign-compose-project"
NUISANCE_FACTORS = ("host-load", HOST_CONDITION_ID)
POOLING_BOUNDARY = "Cells produced under this host condition were measured without the dps_training_k co-tenant that was running throughout Hotel campaigns #1-#5 (103 banked cells); they are a different host condition and must not be pooled with those cells."
OWN_PROJECT_PREFIX = "hotel_candidate_v4"
PLAN_KIND = "hotel-candidate-gate-plan-v1"
SETUP_KIND = "hotel-candidate-gate-setup-v1"
RUN_KIND = "hotel-candidate-gate-run-v1"
READINESS_KIND = "hotel-candidate-target-readiness-v4"
ADMISSION_KIND = "hotel-candidate-runtime-admission-v1"
CELL_KIND = "hotel-candidate-cell-contract-v1"
ABORT_KIND = "hotel-candidate-campaign-abort-v1"
JOURNAL_KIND = "hotel-candidate-runtime-journal-v1"
JOURNAL_NAME = "runtime-journal.jsonl"
CONTROLLER_ABORT_KIND = "hotel-candidate-controller-abort-v1"
CONTROLLER_ABORT_NAME = "campaign-abort.json"
CONTROLLER_ABORT_STAGES = (
    "campaign-preflight", "campaign-preparation", "cell-execution",
    "campaign-cleanup", "lease-release", "terminal-validation",
)
JOURNAL_STATES = ("valid", "stopped")
CAMPAIGN_ID = re.compile(r"^hotel-v1-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}$")
SETUP_ID = re.compile(r"^hotel-setup-v1-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}$")
READINESS_CAPTURE_ID = re.compile(
    r"^hotel-readiness-v1-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}$"
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
PROJECT = re.compile(r"^hotel_candidate_v4_[0-9a-f]{8}_[0-9]{2}$")

TARGET = {
    "target": "fb14srv4",
    "transportUser": "root",
    "setupUser": "root",
    "executionUser": "fhuebscher",
    "executionUid": 1007,
    "executionGid": 1007,
    "supplementalGids": [27, 998],
    "dockerGid": 998,
    "dockerVersion": "29.6.1",
    "authorizedParent": "/home/fhuebscher/observability-placement-candidate-v4-hotel-srv4",
    "releaseParent": "/home/fhuebscher/observability-placement-candidate-v4-hotel-srv4",
    "checkoutRoot": "/home/fhuebscher/observability-placement-candidate-v4-hotel-srv4/checkout",
    "artifactParent": "/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1",
    "leaseRoot": "/home/fhuebscher/observability-placement-candidate-v4-runs",
    "leasePath": "/home/fhuebscher/observability-placement-candidate-v4-runs/.hotel-candidate-v1.lock",
    "controlRoot": "/home/fhuebscher/observability-placement-candidate-v4-hotel-srv4/control",
    "uploadPath": "/tmp/obsplacement-hotel-srv4-20260830-a53f9c27.tar",
}
TARGET_PROJECTION = {
    "status": "allocated",
    "host": "fb14srv4",
    "transportUsers": ["root"],
    "setupUsers": ["root"],
    "executionIdentities": [{
        "user": "fhuebscher", "uid": 1007, "gid": 1007,
        "supplementalGids": [27, 998],
    }],
    "releaseParent": TARGET["releaseParent"],
    "artifactParent": TARGET["artifactParent"],
    "leasePath": TARGET["leasePath"],
    "projectPrefix": "hotel_candidate_v4",
    "reservedPorts": [35005, 36685],
    "freshReadinessAfter": None,
    "readinessRequirements": [
        "exact non-symlink setup-installed paths owned and traversable by fhuebscher",
        "artifact root absent before setup",
        "fixed ports free",
        "competing lease absent",
        "no foreign Compose project present: `docker compose ls --all` lists only hotel_candidate_v4 projects and `docker ps -a` shows no container outside them, verified at setup, at readiness and before and after every cell (the dps_training_k co-tenant of campaigns #1-#5 was decommissioned on 2026-09-21; Cells produced under this host condition were measured without the dps_training_k co-tenant that was running throughout Hotel campaigns #1-#5 (103 banked cells); they are a different host condition and must not be pooled with those cells.)",
        "no deletion or alteration of foreign resources",
        "absolute cost and latency claims remain noncanonical",
    ],
}

# Every absolute SPELLING a target binary of the Hotel argv may have, most
# preferred first. These are spellings, not contracts: the execution identity
# (fhuebscher/1007/1007, supplemental [27, 998], docker gid 998) stays literal
# everywhere and is still asserted exactly as before.
#
# Why this exists: `/usr/sbin/runuser` exists ONLY on fb14srv4 (its /sbin is a
# symlink to usr/sbin); fb14srv5 and fb14srv6 carry `/sbin/runuser` only
# (research/host-topology.json). Hotel worked purely because it runs on the one
# host where its guess is right. The same baked path killed the first real OTel
# launch on 2026-09-17 with "flock: failed to execute /usr/sbin/runuser".
#
# The order is deliberate and NOT TeaStore's: fb14srv4's current spelling comes
# first, so on fb14srv4 every emitted argv is byte-identical to what Hotel
# emitted before this change and retained readiness/launch evidence still
# replays. On a host that lacks the first spelling the second is used.
RUNUSER_CANDIDATES = ("/usr/sbin/runuser", "/sbin/runuser")
TARGET_PYTHON_CANDIDATES = ("/usr/bin/python3", "/bin/python3")


def _resolve_target_binary(name: str, candidates: tuple[str, ...]) -> str:
    """Resolve one target binary among fixed absolute candidates, ON the target.

    TeaStore's stricter process-local form (`candidate_release_installer.
    _resolve_target_binary`): PATH is never consulted and each candidate must be
    a root-owned regular executable. Use this only from code that actually runs
    on fb14srv4; controller-side argv must use ``resolve_target_binary_over_ssh``.

    2026-09-21: this resolver used `os.lstat` alone and skipped any candidate
    that was itself a symlink, on the theory that a link is replaceable. That
    refused `python3` on every Debian host in the lab -- `/usr/bin/python3` and
    `/bin/python3` are both root-owned symlinks to `python3.9` on fb14srv4 -- so
    Hotel #6's `auto` raised "no root-owned python3" before any cell was spent.
    TeaStore hit the identical bug in its own copy of this function and fixed it
    in f2edc1b; that commit never reached this lineage, so the fix is ported here
    rather than cherry-picked. Adding `python3.9` to the candidate list would
    hardcode a minor version and recreate the class, so the link is followed and
    the predicate applied to what it points at:

      * the candidate itself must be root-owned (`os.lstat`), so an unprivileged
        user cannot interpose a link of their own;
      * `os.path.realpath` follows the chain (loops and dangling links fail the
        `os.stat` below, so they are refused, not certified);
      * the resolved target must be a root-owned regular file, and executable.

    What is returned is the SPELLING, never the realpath: the target proof
    compares `pythonRuntime.executable`, which is the probe's `sys.executable`,
    and CPython reports the invoked spelling (`/usr/bin/python3`), not the link
    target. For a candidate that is not a symlink lstat == stat, so behaviour is
    unchanged.
    """
    for candidate in candidates:
        try:
            link_info = os.lstat(candidate)
        except OSError:
            continue
        if link_info.st_uid != 0:
            continue
        try:
            target_info = os.stat(os.path.realpath(candidate))
        except OSError:
            continue
        if (
            stat.S_ISREG(target_info.st_mode)
            and target_info.st_uid == 0
            and os.access(candidate, os.X_OK)
        ):
            return candidate
    raise GateError(f"no root-owned {name} among {list(candidates)}")


def target_runuser() -> str:
    return _resolve_target_binary("runuser", RUNUSER_CANDIDATES)


def target_python() -> str:
    return _resolve_target_binary("python3", TARGET_PYTHON_CANDIDATES)


_SSH_BINARY_PROBES: list[dict[str, Any]] = []
_SSH_BINARY_CACHE: dict[tuple[str, str], str] = {}


def resolve_target_binary_over_ssh(
    name: str,
    candidates: tuple[str, ...] = (),
    *,
    destination: str = "root@" + TARGET["target"],
    runner: Callable[..., Any] | None = None,
) -> str:
    """Resolve one target binary ON THE TARGET, for controller-side ssh argv.

    OTel's discipline (`modules/otel-demo/execution/candidate_runtime.
    ComposeSshAdapter._resolve_launch_tokens`): the controller cannot lstat the
    target, so it asks the target and proves the answer executable with
    ``test -x`` at exactly the resolved path, records the probe, and spends the
    SAME resolved token in the guard and in the guarded command.

    It deviates from OTel in one place, deliberately: OTel asks ``command -v``,
    which consults the remote login shell's PATH. This walks the same fixed
    absolute candidate list the process-local resolver uses. PATH-independence is
    what keeps fb14srv4's emitted argv byte-identical, and it does not admit a
    binary planted in some other PATH directory.

    Honest limit, stated rather than hidden: over ssh this asserts executability
    only. Unlike ``_resolve_target_binary`` it does NOT assert root ownership or
    regular-file-ness, because `test` cannot. OTel's form has the same limit.
    """
    resolved = _SSH_BINARY_CACHE.get((destination, name))
    if resolved is not None:
        return resolved
    if not candidates:
        candidates = {"runuser": RUNUSER_CANDIDATES, "python3": TARGET_PYTHON_CANDIDATES}[name]
    if runner is None:
        runner = subprocess.run
    for candidate in candidates:
        argv = [
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "--",
            destination, "test", "-x", candidate,
        ]
        try:
            result = runner(
                argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False, timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise GateError(f"target binary probe for {name!r} failed: {exc}") from exc
        _SSH_BINARY_PROBES.append({
            "binary": name, "candidate": candidate,
            "destination": destination, "returnCode": result.returncode,
        })
        if result.returncode == 0:
            _SSH_BINARY_CACHE[(destination, name)] = candidate
            return candidate
    raise GateError(f"no executable {name} among {list(candidates)} on {destination}")


def _replayed_spelling(
    facts: Any, index: int, name: str, candidates: tuple[str, ...],
) -> str:
    """Admit the target's own spelling of a replayed argv binary, or nothing.

    The controller re-validates readiness evidence it did not produce and cannot
    lstat the target, so it cannot re-derive which spelling was spent. It admits
    exactly the members of the fixed absolute candidate list and nothing else:
    anything outside the list falls back to ``candidates[0]``, which makes the
    caller's byte-equality check fail with its original message.

    THIS WIDENS THE SEAM, and the widening is the point. Before this change
    `target-runner-executable-replay` and `terminal-validator-executable-replay`
    accepted exactly ``/usr/sbin/runuser`` and ``/usr/bin/python3``; they now
    accept either member of a two-element list of fixed absolute paths. On
    fb14srv4 nothing changes. On fb14srv5/fb14srv6 the seam stops rejecting the
    only spelling those hosts have. It does not accept a relative path, a PATH
    lookup, or any path outside the list.
    """
    if isinstance(facts, Mapping):
        argv = facts.get("argv")
        if isinstance(argv, list) and len(argv) > index and argv[index] in candidates:
            return str(argv[index])
    return candidates[0]


CONTROLLER_PATHS = {
    "candidate-compiler": "modules/hotel-reservation/execution/candidate_pilot.py",
    "candidate-runtime": "modules/hotel-reservation/execution/candidate_runtime.py",
    "candidate-cell-runner": "modules/hotel-reservation/execution/candidate_cell.py",
    "candidate-terminal": "modules/hotel-reservation/validation/candidate_terminal.py",
    "candidate-materializer": "modules/hotel-reservation/candidate_materialize.py",
    "candidate-workload": "modules/hotel-reservation/workload/candidate_search.py",
    "candidate-resources": "modules/hotel-reservation/collectors/candidate_resources.py",
    "candidate-witness": "modules/hotel-reservation/witness/candidate_evidence.py",
    "request-emission-patch": "modules/hotel-reservation/witness/hotel-candidate-witness.patch",
    "patch-manifest": "modules/hotel-reservation/witness/patch-manifest.json",
    "runtime-input-lock": "modules/hotel-reservation/deployment/runtime-inputs.lock.json",
    "runtime-policy": "modules/hotel-reservation/execution/runtime-policy.json",
    "base-materializer": "modules/hotel-reservation/materialize.py",
    "base-smoke": "modules/hotel-reservation/execution/smoke.py",
    "fault-adapter": "modules/hotel-reservation/faults/compose_pause.py",
    "fault-adapter-lmt": "modules/hotel-reservation/faults/lmt_faults.py",
    "system-collector": "modules/hotel-reservation/collectors/system_state.py",
    "jaeger-collector": "modules/hotel-reservation/collectors/jaeger_api.py",
    "jaeger-normalizer": "modules/hotel-reservation/normalizers/jaeger.py",
    "compose-overlay": "modules/hotel-reservation/deployment/compose.observability-placement.yml",
    "source-lock": "modules/hotel-reservation/source.lock",
    "candidate-descriptor": "pipelines/campaigns/hotel-reservation-selected-v1.json",
}
READINESS_SEAMS = (
    "installed-bundle-bytes",
    "target-execution-identity",
    "docker-runtime-and-membership",
    "campaign-path-ownership",
    "fixed-ports-free",
    "foreign-project-preserved",
    "target-runner-executable-replay",
    "terminal-validator-executable-replay",
)


class GateError(ValueError):
    """A plan, readiness, run, or transport binding failed closed."""


class Terminated(BaseException):
    """Raised by `_on_sigterm` to convert a delivered SIGTERM into an
    exception `execute_campaign` can retain an abort for before dying.

    Deliberately a `BaseException`, not an `Exception`: it must flow past
    `except Exception` (which stays a meaningful "runtime-error"
    classification for actual runtime defects) and be caught only by the
    dedicated `except BaseException` wrapper that retains a stop record.
    """


@dataclass(frozen=True)
class GitState:
    commit: str
    tree: str
    commit_tree: str
    dirty: bool
    status: bytes
    concealment: bytes
    index_concealment: tuple[str, ...]


@dataclass(frozen=True)
class Bindings:
    framework_commit: str
    framework_tree: str
    descriptor_sha256: str
    compiled_plan_sha256: str
    runtime_policy_sha256: str
    controller_sha256: dict[str, str]
    run_count: int
    # D6: the claim ceiling for postures this SUT cannot express is declared
    # policy, never a literal in the binding or the validator.
    unsupported_postures: tuple[str, ...]
    source_cost_comparison_state: str


@dataclass(frozen=True)
class BundleInfo:
    path: Path
    bundle_sha256: str
    bundle_size_bytes: int
    manifest_canonical_sha256: str
    manifest: dict[str, Any]


class RuntimeTransport(Protocol):
    transport_id: str
    target: str

    def acquire_lease(self, admission: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def preflight(self, admission: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def prepare_campaign(self, admission: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def record_attempt_start(self, admission: Mapping[str, Any], contract: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def run_cell(self, admission: Mapping[str, Any], contract: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def validate_campaign(self, admission: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def cleanup(self, admission: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def release_lease(self, admission: Mapping[str, Any]) -> Mapping[str, Any]: ...


def _reject_constant(value: str) -> NoReturn:
    raise GateError(f"non-finite JSON value is forbidden: {value}")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise GateError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json(value: bytes | str, where: str) -> Any:
    try:
        text = value.decode("utf-8", errors="strict") if isinstance(value, bytes) else value
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except GateError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GateError(f"invalid JSON in {where}: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, allow_nan=False, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GateError(f"value is not canonical JSON: {exc}") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _file(path: Path, where: str) -> bytes:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise GateError(f"{where} is not a regular non-symlink file")
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        payload = path.read_bytes()
        after = path.lstat()
        if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise GateError(f"{where} changed while being read")
        return payload
    except GateError:
        raise
    except OSError as exc:
        raise GateError(f"cannot read {where}: {exc}") from exc


def _json_file(path: Path, where: str) -> dict[str, Any]:
    value = strict_json(_file(path, where), where)
    if not isinstance(value, dict):
        raise GateError(f"{where} must contain one JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(_file(path, str(path))).hexdigest()


def _timestamp(value: Any, where: str) -> datetime:
    if not isinstance(value, str):
        raise GateError(f"{where} must be an ISO-8601 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise GateError(f"{where} is not an ISO-8601 timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise GateError(f"{where} must include an offset")
    return result.astimezone(timezone.utc)


def _now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise GateError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc)


# ------------------------------------------------------------------------------- study-epoch selection
# 2026-10-03 (branch hotel-protocol-20261002): this checkout carries two epochs.  The frozen
# hotel-reservation-selected-v1 (candidate_pilot.py, plan 189604cc...) stays the active epoch, and every
# constant above keeps its value, unless the committed file execution/study-epoch.json selects another one.
# The selector is a controller file like any other: committing it is a framework commit (every gate sentence
# is re-derived) and, when present, its digest is bound in CONTROLLER_PATHS.  No selector = the frozen
# epoch, byte-for-byte as at e4fd4c7.  A cell is replayed under the selector of its own epoch.
FROZEN_STUDY_EPOCH = STUDY_EPOCH
EPOCH_SELECTOR = MODULE / "execution" / "study-epoch.json"
SWEEP_STUDY_EPOCH = "hotel-traffic-sweep-v1"
EPOCH_CONTROLLER_PATHS = {
    SWEEP_STUDY_EPOCH: {
        "candidate-compiler": "modules/hotel-reservation/execution/candidate_sweep.py",
        "candidate-descriptor": "pipelines/campaigns/hotel-traffic-sweep-v1.json",
        "runtime-policy": "modules/hotel-reservation/execution/runtime-policy.hotel-traffic-sweep-v1.json",
        "frozen-compiler": "modules/hotel-reservation/execution/candidate_pilot.py",
        # The witness reads ground truth from the frozen descriptor in every epoch (candidate_evidence.py).
        "frozen-descriptor": "pipelines/campaigns/hotel-reservation-selected-v1.json",
        "protocol-gates": "modules/hotel-reservation/validation/protocol_gates.py",
        "study-epoch-selector": "modules/hotel-reservation/execution/study-epoch.json",
    },
}
# 2026-10-04: the quiet calibration run (protocol decision 48) is a third epoch: the sweep's no-fault cell only,
# 40 cells in one seeded order.  Its compiler reads the sweep compiler as a library, so that file is bound too.
QUIET_STUDY_EPOCH = "hotel-quiet-calibration-v1"
EPOCH_CONTROLLER_PATHS[QUIET_STUDY_EPOCH] = {
    "candidate-compiler": "modules/hotel-reservation/execution/candidate_quiet.py",
    "candidate-descriptor": "pipelines/campaigns/hotel-quiet-calibration-v1.json",
    "runtime-policy": "modules/hotel-reservation/execution/runtime-policy.hotel-quiet-calibration-v1.json",
    "sweep-compiler": "modules/hotel-reservation/execution/candidate_sweep.py",
    "frozen-compiler": "modules/hotel-reservation/execution/candidate_pilot.py",
    "frozen-descriptor": "pipelines/campaigns/hotel-reservation-selected-v1.json",
    "protocol-gates": "modules/hotel-reservation/validation/protocol_gates.py",
    "study-epoch-selector": "modules/hotel-reservation/execution/study-epoch.json",
}
# 2026-10-15: hotel-offpath-v1 (budget BUDGET_OVERNIGHT_20261014 item 4) adds the consul container to the collection
# scope (logs, docker stats, cgroup cost edges, system samples, TCP snapshots, image receipt) of every cell of that
# epoch, because consul is its off-path pause target; every other epoch collects the ten application services only.
# Keyed by the cell contract's `studyEpoch`, which the admitted plan fixes byte for byte.
OFFPATH_STUDY_EPOCH = "hotel-offpath-v1"
COLLECTION_EXTRA_SERVICES = {OFFPATH_STUDY_EPOCH: ("consul",)}
# Its compiler reads the sweep compiler as a library (so that file is bound too), like the quiet epoch's.
EPOCH_CONTROLLER_PATHS[OFFPATH_STUDY_EPOCH] = {
    "candidate-compiler": "modules/hotel-reservation/execution/candidate_offpath.py",
    "candidate-descriptor": "pipelines/campaigns/hotel-offpath-v1.json",
    "runtime-policy": "modules/hotel-reservation/execution/runtime-policy.hotel-offpath-v1.json",
    "sweep-compiler": "modules/hotel-reservation/execution/candidate_sweep.py",
    "frozen-compiler": "modules/hotel-reservation/execution/candidate_pilot.py",
    "frozen-descriptor": "pipelines/campaigns/hotel-reservation-selected-v1.json",
    "protocol-gates": "modules/hotel-reservation/validation/protocol_gates.py",
    "study-epoch-selector": "modules/hotel-reservation/execution/study-epoch.json",
}


def collection_extra_services(study_epoch: Any) -> tuple:
    """Services collected beside the ten application services in ``study_epoch`` (none unless declared above)."""
    return COLLECTION_EXTRA_SERVICES.get(study_epoch, ()) if isinstance(study_epoch, str) else ()


def _selected_study_epoch() -> str:
    if not EPOCH_SELECTOR.exists() and not EPOCH_SELECTOR.is_symlink():
        return FROZEN_STUDY_EPOCH
    document = _json_file(EPOCH_SELECTOR, "study epoch selector")
    if (
        set(document) != {"schemaVersion", "studyEpoch"} or document["schemaVersion"] != 1
        or document["studyEpoch"] not in EPOCH_CONTROLLER_PATHS
    ):
        raise GateError("study epoch selector names no declared non-frozen epoch")
    return document["studyEpoch"]


STUDY_EPOCH = _selected_study_epoch()
if STUDY_EPOCH != FROZEN_STUDY_EPOCH:
    CONTROLLER_PATHS = {**CONTROLLER_PATHS, **EPOCH_CONTROLLER_PATHS[STUDY_EPOCH]}
    DESCRIPTOR = ROOT / CONTROLLER_PATHS["candidate-descriptor"]
    POLICY = ROOT / CONTROLLER_PATHS["runtime-policy"]


def _load_compiler():
    path = ROOT / CONTROLLER_PATHS["candidate-compiler"]
    spec = importlib.util.spec_from_file_location("hotel_runtime_frozen_compiler", path)
    if spec is None or spec.loader is None:
        raise GateError("cannot load frozen Hotel compiler")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The scheduled cell count is the frozen compiler's TOTAL_RUNS, never a literal
# restated here: the compiled plan, the policy budget, the gate sentences and the
# execution receipts all derive from one reviewed source.
CELL_COUNT = _load_compiler().TOTAL_RUNS
# Wall budget: the frozen epoch's reviewed literals (18000 / 17700); a parameterised epoch's compiler derives
# its own from cells x cell period (candidate_sweep.py MAXIMUM_WALL_SECONDS), whole hours for the driver.
MAXIMUM_WALL_SECONDS = int(getattr(_load_compiler(), "MAXIMUM_WALL_SECONDS", 18000))
MINIMUM_FIRST_MUTATION_REMAINING_SECONDS = int(
    getattr(_load_compiler(), "MINIMUM_FIRST_MUTATION_REMAINING_SECONDS", 17700)
)


def _load_frozen_compiler():
    """candidate_pilot.py under its own module name, whatever epoch is active (posture vocabulary, timing)."""
    path = MODULE / "execution" / "candidate_pilot.py"
    spec = importlib.util.spec_from_file_location("hotel_runtime_frozen_timing_compiler", path)
    if spec is None or spec.loader is None:
        raise GateError("cannot load frozen Hotel compiler")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CELL_TIMING_KEYS = frozenset({
    "requestsPerSecond", "interArrivalSeconds", "concurrency", "requestTimeoutSeconds",
    "warmupSeconds", "warmupRequestsPerSecond", "measurementSeconds", "offered", "faultApplied",
    "faultOnsetBaseSeconds", "faultOnsetPhaseOffsetSeconds", "faultOnsetSeconds", "faultHoldSeconds",
    "scoredWindowSeconds", "minimumWitnessedStartsByPhase", "tcpSnapshotOffsetsSeconds",
    "jaegerQueryWindowSeconds", "minimumSystemSamples", "collectorJoinSlackSeconds",
    "applicationLogTimestamps", "jaegerAllServicesRemainder", "probeStamps",
})


def cell_timing(contract: Mapping[str, Any]) -> dict[str, Any]:
    """The per-cell timing the runner and the validators read.

    A frozen-epoch contract carries no ``timing``: its values are the frozen compiler's constants plus the
    literals the cell runner and the validator held at e4fd4c7 (1 s request timeout, TCP snapshots at 30 /
    52 s, a 125 s Jaeger window, >= 24 system samples), so its behaviour is unchanged.  A parameterised
    contract's timing must be exactly the active compiled plan's timing for that run ID: a retained contract
    cannot bring its own numbers.
    """
    timing = contract.get("timing")
    if timing is None:
        frozen = _load_frozen_compiler()
        return {
            "requestsPerSecond": frozen.REQUESTS_PER_SECOND,
            "concurrency": frozen.CONCURRENCY,
            "requestTimeoutSeconds": 1,
            "warmupSeconds": frozen.WARMUP_SECONDS,
            "warmupRequestsPerSecond": frozen.REQUESTS_PER_SECOND,
            "measurementSeconds": frozen.MEASUREMENT_SECONDS,
            "offered": frozen.OFFERED_PER_RUN,
            "faultOnsetSeconds": frozen.FAULT_ONSET_SECONDS,
            "faultHoldSeconds": frozen.FAULT_HOLD_SECONDS,
            "minimumWitnessedStartsByPhase": None,
            "tcpSnapshotOffsetsSeconds": {"pre-fault": 30, "during-fault": 52},
            "jaegerQueryWindowSeconds": 125,
            "minimumSystemSamples": 24,
            "collectorJoinSlackSeconds": 0,
            "applicationLogTimestamps": False,
            "jaegerAllServicesRemainder": False,
            "probeStamps": False,
        }
    if not isinstance(timing, dict) or set(timing) != CELL_TIMING_KEYS:
        raise GateError("cell timing fields differ")
    compiled = [cell for cell in _flatten_plan() if cell["runId"] == contract.get("runId")]
    if len(compiled) != 1 or canonical_bytes(compiled[0].get("timing")) != canonical_bytes(timing):
        raise GateError("cell timing is not the active compiled plan's timing for this run ID")
    return copy.deepcopy(timing)


def _git_result(arguments: tuple[str, ...], allowed: tuple[int, ...] = (0,)):
    environment = {
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": "/nonexistent-hotel-runtime-home",
        "LC_ALL": "C", "LANG": "C",
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
    }
    result = subprocess.run(
        ("git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
         "-C", str(ROOT), *arguments),
        env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=10,
    )
    if result.returncode not in allowed:
        raise GateError(f"controlled Git query failed: {arguments[0]}")
    return result


def _git_state() -> GitState:
    def value(arguments: tuple[str, ...]) -> str:
        return _git_result(arguments).stdout.decode("ascii", errors="strict").strip()
    top = value(("rev-parse", "--show-toplevel"))
    if Path(top).resolve() != ROOT.resolve():
        raise GateError("runtime adapter is not at the Git worktree root")
    commit = value(("rev-parse", "--verify", "HEAD^{commit}"))
    tree = value(("rev-parse", "--verify", "HEAD^{tree}"))
    commit_tree = value(("rev-parse", "--verify", f"{commit}^{{tree}}"))
    tracked = _git_result(
        ("diff-index", "--ignore-submodules=none", "--quiet", "HEAD", "--"),
        allowed=(0, 1),
    )
    status = _git_result((
        "status", "--porcelain=v1", "-z", "--untracked-files=all",
        "--ignore-submodules=none",
    )).stdout
    concealment = _git_result((
        "config", "--local", "--show-origin", "--get-regexp",
        r"^(filter\.|core\.attributesfile$|core\.excludesfile$|core\.fsmonitor$|"
        r"core\.ignorestat$|core\.untrackedcache$|submodule\..*\.ignore$|"
        r"diff\.ignoresubmodules$|extensions\.worktreeconfig$)",
    ), allowed=(0, 1)).stdout
    flags = []
    for raw in _git_result(("ls-files", "-v", "-z", "--")).stdout.split(b"\0"):
        if not raw:
            continue
        row = raw.decode("utf-8", errors="strict")
        if len(row) < 3 or row[1] != " ":
            raise GateError("malformed Git index flag record")
        if row[0].islower() or row[0] == "S":
            flags.append(row[2:])
    return GitState(
        commit, tree, commit_tree, tracked.returncode == 1, status,
        concealment, tuple(flags),
    )


def _verify_git(expected_commit: str, state: GitState, previous: GitState | None = None) -> None:
    if COMMIT.fullmatch(expected_commit) is None or state.commit != expected_commit:
        raise GateError("framework commit is not the exact current Git HEAD")
    if state.tree != state.commit_tree:
        raise GateError("HEAD tree differs from the bound commit tree")
    if state.dirty or state.status:
        raise GateError("runtime worktree is not clean")
    if state.concealment or state.index_concealment:
        raise GateError("Git configuration or index flags can conceal runtime bytes")
    if previous is not None and state != previous:
        raise GateError("Git identity changed while runtime bindings were inspected")


def _validate_posture_ceiling(document: Any) -> dict[str, Any]:
    """Fail closed on the declared supported/unsupported posture ceiling (D6).

    The ceiling used to live as a literal in ``plan_binding`` and in the
    terminal validator.  It is declared policy now, so the supported-posture
    set is data that the gate sentence, the plan binding, and every terminal
    replay read from one reviewed source instead of four copies of a list.
    """
    if not isinstance(document, dict) or set(document) != {
        "supportedPostures", "unsupportedPostures", "unsupportedReason",
        "sourceCostComparisonState", "sourceCostUnsupportedReason",
        "admissibleContrasts", "prohibitedClaims",
    }:
        raise GateError("runtime posture ceiling fields differ")
    supported = document["supportedPostures"]
    unsupported = document["unsupportedPostures"]
    if (
        not isinstance(supported, list) or not supported
        or any(not isinstance(value, str) or not value for value in supported)
        or len(set(supported)) != len(supported)
        or not isinstance(unsupported, list) or not unsupported
        or not isinstance(document["unsupportedReason"], str)
        or not document["unsupportedReason"]
        or document["sourceCostComparisonState"] != "unsupported"
        # Retired ceilings keep the reason they were sealed with; the LMT+S pilot's is new.
        or document["sourceCostUnsupportedReason"] not in {
            "sample-zero-is-not-source-off", "no-posture-is-source-off",
        }
    ):
        raise GateError("runtime posture ceiling identity or reasons differ")
    identifiers = []
    for row in unsupported:
        if (
            not isinstance(row, dict) or set(row) != {"id", "state", "numericValue"}
            or not isinstance(row["id"], str) or not row["id"]
            or row["state"] != "unsupported" or row["numericValue"] is not None
        ):
            raise GateError("runtime posture ceiling row is malformed or claims a value")
        identifiers.append(row["id"])
    if len(set(identifiers)) != len(identifiers) or set(identifiers) & set(supported):
        raise GateError("runtime posture ceiling supported and unsupported sets overlap")
    _validate_claim_ceiling(document, supported, identifiers)
    return document


LATTICE_NESTING_CLAIM = "placement-lattice-nesting"


def _validate_claim_ceiling(
    document: Mapping[str, Any], supported: list, unsupported: list
) -> None:
    """Fail closed on the claims this evidence may never support (D6).

    Hotel weaves its entry point unconditionally and upstream DeathStarBench
    ships no service-level source guard, so ``none`` and ``selected`` are
    *unsupported*, not merely untested.  A Hotel campaign may therefore back
    exactly one contrast -- ``full`` against ``sample-zero``, each under its own
    regimes -- and may never back a placement-lattice nesting claim, because a
    lattice needs the very rungs this SUT cannot express.  Declaring the ceiling
    here puts it inside ``runtimePolicyCanonicalSha256``, so every GATE-PLAN and
    every receipt commits to it by digest instead of by prose.
    """
    contrasts = document["admissibleContrasts"]
    prohibited = document["prohibitedClaims"]
    if (
        not isinstance(contrasts, list) or not contrasts
        or not isinstance(prohibited, list) or not prohibited
        or any(not isinstance(value, str) or not value for value in prohibited)
        or sorted(set(prohibited)) != prohibited
    ):
        raise GateError("runtime claim ceiling contrasts or prohibited claims are malformed")
    seen = set()
    for row in contrasts:
        if (
            not isinstance(row, list) or len(row) != 2
            or any(value not in supported for value in row)
            or row[0] == row[1] or tuple(sorted(row)) in seen
        ):
            raise GateError("admissible contrast is not a fresh pair of supported postures")
        seen.add(tuple(sorted(row)))
    # Exact equality, not containment: a prohibited-claim set that drifts either
    # way is a governance defect.  Dropping an entry would silently re-admit a
    # comparison the SUT cannot express; adding one that names a supported
    # posture would forbid the only contrast the campaign exists to make.
    required = {LATTICE_NESTING_CLAIM}
    required.update("{0}-posture-comparison".format(value) for value in unsupported)
    if set(prohibited) != required:
        raise GateError(
            "prohibited claims must be exactly lattice nesting plus every unsupported posture"
        )


def posture_ceiling() -> dict[str, Any]:
    """Read the reviewed *current* posture ceiling from declared runtime policy."""
    return copy.deepcopy(
        _validate_policy(_json_file(POLICY, "runtime policy"))["postureCeiling"]
    )


RETIRED_CEILING_FIELDS = {
    "version", "compiledPlanCanonicalSha256", "descriptorCanonicalSha256",
    "runCount", "retiredAt", "reason", "postureCeiling", "hostCondition",
}


def _validate_retired_ceilings(document: Any) -> list[dict[str, Any]]:
    """Fail closed on the versioned history of retired posture ceilings.

    A ceiling is never edited in place: every retained ``correlation.json`` and
    ``cell-terminal.json`` embeds the ceiling it was sealed under as data, and the
    cell contract pins the compiled-plan digest that carried it.  Widening the
    ceiling therefore retires the old one into this list, keyed by that plan
    digest, so banked cells keep replaying against the ceiling they were run
    under while new cells run under the current one.  Re-sealing retained
    evidence is not an option: it would rewrite the cells and the gate sentences
    that pinned them.
    """
    if not isinstance(document, list):
        raise GateError("retired posture ceilings must be a list")
    seen_plans: set[str] = set()
    seen_versions: set[int] = set()
    for row in document:
        if not isinstance(row, dict) or set(row) != RETIRED_CEILING_FIELDS:
            raise GateError("retired posture ceiling record fields differ")
        if (
            not isinstance(row["version"], int) or isinstance(row["version"], bool)
            or row["version"] < 1 or row["version"] in seen_versions
            or SHA256.fullmatch(str(row["compiledPlanCanonicalSha256"])) is None
            or SHA256.fullmatch(str(row["descriptorCanonicalSha256"])) is None
            or row["compiledPlanCanonicalSha256"] in seen_plans
            or not isinstance(row["runCount"], int) or isinstance(row["runCount"], bool)
            or row["runCount"] < 1
            or not isinstance(row["retiredAt"], str) or not row["retiredAt"]
            or not isinstance(row["reason"], str) or not row["reason"]
        ):
            raise GateError("retired posture ceiling record is malformed")
        _validate_posture_ceiling(row["postureCeiling"])
        condition = row["hostCondition"]
        if (
            not isinstance(condition, dict) or not isinstance(condition.get("id"), str)
            or not isinstance(condition.get("factors"), list) or not condition["factors"]
            or "foreignProject" not in condition
        ):
            raise GateError("retired host condition is malformed")
        seen_plans.add(row["compiledPlanCanonicalSha256"])
        seen_versions.add(row["version"])
    return document


def posture_ceiling_for_plan(plan_sha256: str) -> tuple[dict[str, Any], int]:
    """Select the ceiling and scheduled cell count bound to one compiled-plan digest.

    The frozen compiler's plan digest selects the current ceiling; a retired
    plan digest selects the ceiling it was retired with.  Any other digest is
    refused, so a cell can only ever be replayed against a ceiling that a gate
    sentence once pinned.
    """
    policy = _validate_policy(_json_file(POLICY, "runtime policy"))
    compiler = _load_compiler()
    if plan_sha256 == compiler.EXPECTED_PLAN_SHA256:
        return copy.deepcopy(policy["postureCeiling"]), int(compiler.TOTAL_RUNS)
    for row in policy["retiredPostureCeilings"]:
        if row["compiledPlanCanonicalSha256"] == plan_sha256:
            return copy.deepcopy(row["postureCeiling"]), int(row["runCount"])
    raise GateError("compiled plan digest is bound to no declared posture ceiling")


def not_poolable_with() -> list[str]:
    """Compiled-plan digests whose cells are a DIFFERENT host condition to this one.

    `poolingBoundary` states the boundary in prose, which explains but cannot be
    checked. This returns the thing a tool can compare: the plan digest of every
    retired ceiling whose host condition differs from the current one, so a cell
    carrying digest X can be refused for pooling with a cell carrying digest Y
    without anyone reading a sentence.

    Derived from the policy's retired records, never a literal: the retirement is
    already the authority on which conditions existed.
    """
    policy = _validate_policy(_json_file(POLICY, "runtime policy"))
    current = policy["hostCondition"]["id"]
    return sorted(
        row["compiledPlanCanonicalSha256"]
        for row in policy["retiredPostureCeilings"]
        if row["hostCondition"]["id"] != current
    )


def host_condition_for_plan(plan_sha256: str) -> dict[str, Any]:
    """Select the host (co-tenant) condition bound to one compiled-plan digest.

    Banked cells were measured with the dps_training_k co-tenant present and their
    terminal replays keep asserting it; cells under the current condition assert
    its verified absence.  The two are different host conditions and are never
    pooled.
    """
    policy = _validate_policy(_json_file(POLICY, "runtime policy"))
    if plan_sha256 == _load_compiler().EXPECTED_PLAN_SHA256:
        return copy.deepcopy(policy["hostCondition"])
    for row in policy["retiredPostureCeilings"]:
        if row["compiledPlanCanonicalSha256"] == plan_sha256:
            return copy.deepcopy(row["hostCondition"])
    raise GateError("compiled plan digest is bound to no declared host condition")


def unsupported_posture_ids(ceiling: Mapping[str, Any]) -> list[str]:
    return [row["id"] for row in ceiling["unsupportedPostures"]]


def _validate_policy(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != {
        "schemaVersion", "studyEpoch", "changeId", "allowedTransports", "targetProjection", "ports",
        "projectPrefix", "foreignProject", "claimCeiling", "postureCeiling",
        "retiredPostureCeilings", "hostCondition", "maximumCells", "maximumWallSeconds",
        "cleanupReserveSeconds", "minimumFirstMutationRemainingSeconds",
        "maximumGateAgeSeconds", "maximumClockSkewSeconds", "execution", "setup", "cleanup",
    }:
        raise GateError("runtime policy fields differ")
    _validate_posture_ceiling(document["postureCeiling"])
    _validate_retired_ceilings(document["retiredPostureCeilings"])
    if (
        document["schemaVersion"] != 2
        or document["studyEpoch"] != STUDY_EPOCH
        or document["changeId"] != CHANGE_ID
        or document["maximumCells"] != CELL_COUNT
        or document["maximumWallSeconds"] != MAXIMUM_WALL_SECONDS
        or document["cleanupReserveSeconds"] != 300
        or document["minimumFirstMutationRemainingSeconds"] != MINIMUM_FIRST_MUTATION_REMAINING_SECONDS
        or document["maximumGateAgeSeconds"] != 900
        or document["maximumClockSkewSeconds"] != 5
        or document["ports"] != {"frontend": 35005, "jaegerQuery": 36685}
        or document["projectPrefix"] != OWN_PROJECT_PREFIX
        or document["foreignProject"] is not None
        or document["hostCondition"] != {
            "id": HOST_CONDITION_ID, "factors": list(NUISANCE_FACTORS),
            "foreignProject": None, "poolingBoundary": POOLING_BOUNDARY,
        }
    ):
        raise GateError("runtime policy identity, budget, or ports differ")
    if document["allowedTransports"] != {"ssh-compose": TARGET}:
        raise GateError("runtime transport targets or roots differ")
    if document["targetProjection"] != TARGET_PROJECTION:
        raise GateError("v4 target projection fields differ")
    if document["claimCeiling"] != {
        "maximumEvidenceLabel": "candidate-evidence",
        "canonical": False,
        "absoluteCostOrLatencyCanonical": False,
        "nuisanceRecordedEveryCell": list(NUISANCE_FACTORS),
    }:
        raise GateError("srv4 candidate-only claim ceiling differs")
    if document["execution"] != {
        "oneControllerOwnsTarget": True, "cellsSequential": True,
        "coldStartEachCell": True, "retryMayReplaceCell": False,
        "stopOnFirstInvalidCell": True, "costAndEffectRootsDisjoint": True,
        "detachedTargetController": True, "terminalReplayLocal": True,
    }:
        raise GateError("runtime execution safety policy differs")
    if document["setup"] != {
        "oneShot": True, "exactBundleOnly": True,
        "userOrKeyMutationAllowed": False, "foreignResourceMutationAllowed": False,
    }:
        raise GateError("runtime setup safety policy differs")
    if document["cleanup"] != {
        "actions": [
            "unpause-owned-fault-target-if-needed",
            "docker-compose-down-volumes-remove-orphans",
            "verify-zero-owned-containers-networks-volumes",
            "release-exact-campaign-lease-even-if-cleanup-fails",
        ],
        "foreignProjectMutationAllowed": False,
        "artifactDeletionAllowed": False,
        "leaseReleaseAlwaysAttempted": True,
    }:
        raise GateError("runtime cleanup policy differs")
    return document


def inspect_bindings(framework_commit: str) -> Bindings:
    first = _git_state()
    _verify_git(framework_commit, first)
    compiler = _load_compiler()
    descriptor = compiler.load_descriptor(DESCRIPTOR)
    plan = compiler.compile_plan(descriptor)
    compiler.validate_plan(plan, descriptor)
    policy = _validate_policy(_json_file(POLICY, "runtime policy"))
    ceiling = _validate_posture_ceiling(policy["postureCeiling"])
    # Declared policy and the digest-frozen compiled plan must agree about the
    # claim ceiling; a divergence is a governance defect, not something to adapt.
    if plan["unsupportedPostures"] != ceiling["unsupportedPostures"]:
        raise GateError("declared posture ceiling differs from the compiled plan")
    if any(
        row["compiledPlanCanonicalSha256"] == plan["planCanonicalSha256"]
        for row in policy["retiredPostureCeilings"]
    ):
        raise GateError("compiled plan digest is already bound to a retired posture ceiling")
    controllers = {}
    for name, relative in CONTROLLER_PATHS.items():
        controllers[name] = _sha256(ROOT / relative)
    second = _git_state()
    _verify_git(framework_commit, second, first)
    return Bindings(
        framework_commit=framework_commit,
        framework_tree=first.tree,
        descriptor_sha256=compiler.canonical_sha256(descriptor),
        compiled_plan_sha256=plan["planCanonicalSha256"],
        runtime_policy_sha256=canonical_sha256(policy),
        controller_sha256=controllers,
        run_count=plan["runCount"],
        unsupported_postures=tuple(unsupported_posture_ids(ceiling)),
        source_cost_comparison_state=ceiling["sourceCostComparisonState"],
    )


def plan_binding(bindings: Bindings) -> dict[str, Any]:
    return {
        "studyEpoch": STUDY_EPOCH,
        "changeId": CHANGE_ID,
        "frameworkCommit": bindings.framework_commit,
        "frameworkTree": bindings.framework_tree,
        "descriptorCanonicalSha256": bindings.descriptor_sha256,
        "compiledPlanCanonicalSha256": bindings.compiled_plan_sha256,
        "runtimePolicyCanonicalSha256": bindings.runtime_policy_sha256,
        "controllerSha256": dict(sorted(bindings.controller_sha256.items())),
        "runCount": bindings.run_count,
        "maximumEvidenceLabel": "candidate-evidence",
        "canonical": False,
        "absoluteCostOrLatencyCanonical": False,
        "nuisanceRecordedEveryCell": list(NUISANCE_FACTORS),
        "unsupportedPostures": list(bindings.unsupported_postures),
        "sourceCostComparisonState": bindings.source_cost_comparison_state,
        "targetContract": copy.deepcopy(TARGET_PROJECTION),
    }


def expected_gate_plan_text(bindings: Bindings) -> str:
    value = plan_binding(bindings)
    # The unsupported set is declared policy (D6); the trailing source-cost
    # token is the comparison state, not a posture.
    if value["sourceCostComparisonState"] != "unsupported":
        raise GateError("declared source-cost comparison state is not unsupported")
    unsupported = ",".join([*value["unsupportedPostures"], "source-cost"])
    return (
        f"APPROVE GATE-PLAN study={STUDY_EPOCH} change={CHANGE_ID} "
        f"commit={value['frameworkCommit']} tree={value['frameworkTree']} "
        f"descriptor={value['descriptorCanonicalSha256']} "
        f"plan={value['compiledPlanCanonicalSha256']} "
        f"policy={value['runtimePolicyCanonicalSha256']} cells={value['runCount']} "
        "ceiling=candidate-evidence canonical=false "
        f"absolute-cost-latency-canonical=false nuisance={','.join(NUISANCE_FACTORS)} "
        "target=fb14srv4 transportUser=root setupUser=root "
        "executionUser=fhuebscher uid=1007 gid=1007 dockerGid=998 docker=29.6.1 "
        f"ports=35005,36685 unsupported={unsupported}"
    )


def validate_gate_plan(document: Any, bindings: Bindings) -> dict[str, Any]:
    keys = {
        "schemaVersion", "kind", "gate", "decision", "typedApproval",
        "approvedBy", "approvedAt", "bindings", "runtimeAuthorized",
        "setupAuthorized", "externalMutationAuthorized", "promotionAuthorized",
    }
    if not isinstance(document, dict) or set(document) != keys:
        raise GateError("GATE-PLAN receipt fields differ")
    if (
        document["schemaVersion"] != 1 or document["kind"] != PLAN_KIND
        or document["gate"] != "GATE-PLAN" or document["decision"] != "approve-exact-plan"
        or document["typedApproval"] != expected_gate_plan_text(bindings)
        or document["bindings"] != plan_binding(bindings)
        or not isinstance(document["approvedBy"], str) or not document["approvedBy"].strip()
        or document["runtimeAuthorized"] is not False
        or document["setupAuthorized"] is not False
        or document["externalMutationAuthorized"] is not False
        or document["promotionAuthorized"] is not False
    ):
        raise GateError("GATE-PLAN identity, typed approval, or authority ceiling differs")
    _timestamp(document["approvedAt"], "GATE-PLAN.approvedAt")
    return document


def _payload_entries(root: Path) -> list[dict[str, Any]]:
    """Describe every installed payload byte without trusting archive metadata."""
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == "install-manifest.json" or path.is_dir():
            continue
        before = path.lstat()
        mode = stat.S_IMODE(before.st_mode)
        if path.is_symlink():
            payload = os.readlink(path).encode("utf-8")
            kind = "symlink"
        elif stat.S_ISREG(before.st_mode):
            payload = path.read_bytes()
            kind = "file"
        else:
            raise GateError(f"bundle contains unsupported file type: {relative}")
        rows.append({
            "path": relative,
            "kind": kind,
            "mode": mode,
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
    return rows


def _git_source_query(source: Path, arguments: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), *arguments],
        env={
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "HOME": "/nonexistent-hotel-bundle-home",
            "LC_ALL": "C", "LANG": "C",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
        },
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    if result.returncode:
        raise GateError(f"controlled source query failed: {arguments[0]}")
    return result.stdout.decode("utf-8", errors="strict").strip()


def build_setup_bundle(
    framework_commit: str, submodule_source: Path, output: Path,
) -> BundleInfo:
    """Create the exact one-shot install payload; this performs no remote action."""
    bindings = inspect_bindings(framework_commit)
    expected_source = "6ecb09706140f8730b5385c08f1386c654c3c526"
    source = submodule_source.resolve(strict=True)
    if _git_source_query(source, ["rev-parse", "HEAD"]) != expected_source:
        raise GateError("Hotel bundle source is not the exact pinned commit")
    if _git_source_query(source, ["status", "--porcelain", "--", "hotelReservation"]):
        raise GateError("Hotel bundle source is dirty")
    source_tree = _git_source_query(source, ["rev-parse", f"{expected_source}:hotelReservation"])
    if output.exists() or output.is_symlink():
        raise GateError("refusing to replace setup bundle")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="hotel-srv4-bundle-", dir=output.parent))
    try:
        archive = _git_result(("archive", "--format=tar", framework_commit))
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as bundle:
            bundle.extractall(staging, filter="data")
        submodule_target = staging / "upstream" / "deathstarbench"
        submodule_target.mkdir(parents=True, exist_ok=True)
        source_archive = subprocess.run(
            ["git", "-C", str(source), "archive", "--format=tar", f"{expected_source}:hotelReservation"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=60,
        )
        if source_archive.returncode:
            raise GateError("cannot archive exact Hotel source")
        hotel_root = submodule_target / "hotelReservation"
        hotel_root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(source_archive.stdout), mode="r:") as bundle:
            bundle.extractall(hotel_root, filter="data")
        source_entries = _payload_entries(hotel_root)
        source_receipt = {
            "schemaVersion": 1,
            "kind": "hotel-source-package-v1",
            "upstreamCommit": expected_source,
            "upstreamTree": source_tree,
            "subdirectory": "hotelReservation",
            "entries": source_entries,
        }
        source_receipt["canonicalSha256"] = canonical_sha256(source_receipt)
        (submodule_target / ".obsplacement-source-package.json").write_bytes(
            canonical_bytes(source_receipt) + b"\n"
        )
        entries = _payload_entries(staging)
        manifest = {
            "schemaVersion": 1,
            "kind": "hotel-srv4-install-manifest-v1",
            "frameworkCommit": framework_commit,
            "frameworkTree": bindings.framework_tree,
            "sourceCommit": expected_source,
            "sourceTree": source_tree,
            "targetContract": plan_binding(bindings)["targetContract"],
            "entries": entries,
        }
        manifest["manifestCanonicalSha256"] = canonical_sha256(manifest)
        (staging / "install-manifest.json").write_bytes(canonical_bytes(manifest) + b"\n")

        def normalized(info: tarfile.TarInfo) -> tarfile.TarInfo:
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            info.mtime = 0
            info.pax_headers = {}
            return info

        with tarfile.open(output, mode="w", format=tarfile.PAX_FORMAT) as bundle:
            for path in sorted(staging.rglob("*")):
                bundle.add(path, arcname=path.relative_to(staging).as_posix(), recursive=False, filter=normalized)
        return BundleInfo(
            path=output,
            bundle_sha256=_sha256(output),
            bundle_size_bytes=output.stat().st_size,
            manifest_canonical_sha256=manifest["manifestCanonicalSha256"],
            manifest=manifest,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def verify_installed_payload(
    expected_commit: str, expected_manifest_sha256: str, root: Path = ROOT,
    *, full: bool,
) -> dict[str, Any]:
    """Replay the installed manifest and, at admission, every installed byte."""
    manifest = _json_file(root / "install-manifest.json", "installed payload manifest")
    body = {key: value for key, value in manifest.items() if key != "manifestCanonicalSha256"}
    if (
        set(manifest) != {
            "schemaVersion", "kind", "frameworkCommit", "frameworkTree",
            "sourceCommit", "sourceTree", "targetContract", "entries",
            "manifestCanonicalSha256",
        }
        or manifest["schemaVersion"] != 1
        or manifest["kind"] != "hotel-srv4-install-manifest-v1"
        or manifest["frameworkCommit"] != expected_commit
        or manifest["targetContract"] != TARGET_PROJECTION
        or manifest["manifestCanonicalSha256"] != canonical_sha256(body)
        or manifest["manifestCanonicalSha256"] != expected_manifest_sha256
        or not isinstance(manifest["entries"], list)
    ):
        raise GateError("installed payload manifest identity differs")
    selected = manifest["entries"] if full else [
        row for row in manifest["entries"]
        if row.get("path") in set(CONTROLLER_PATHS.values())
    ]
    if not full and len(selected) != len(CONTROLLER_PATHS):
        raise GateError("installed payload manifest omits a controller")
    for row in selected:
        if not isinstance(row, dict) or set(row) != {"path", "kind", "mode", "size", "sha256"}:
            raise GateError("installed payload entry fields differ")
        relative = _safe_relative(row["path"], "installed payload path")
        path = root.joinpath(*relative.parts)
        resolved_root = root.resolve(strict=True)
        if row["kind"] == "symlink":
            if not path.is_symlink():
                raise GateError(f"installed payload type differs: {row['path']}")
            payload = os.readlink(path).encode("utf-8")
        else:
            resolved = path.resolve(strict=True)
            if resolved_root not in resolved.parents or path.is_symlink() or not path.is_file():
                raise GateError(f"installed payload path escapes: {row['path']}")
            payload = path.read_bytes()
        if (
            len(payload) != row["size"]
            or hashlib.sha256(payload).hexdigest() != row["sha256"]
            or stat.S_IMODE(path.lstat().st_mode) != row["mode"]
        ):
            raise GateError(f"installed payload bytes differ: {row['path']}")
    return manifest


def setup_binding(
    bindings: Bindings, gate_plan: Mapping[str, Any], bundle: Mapping[str, Any],
    setup_id: str,
) -> dict[str, Any]:
    if SETUP_ID.fullmatch(str(setup_id)) is None:
        raise GateError("setup identity is not allowed")
    expected_bundle_keys = {
        "bundleSha256", "bundleSizeBytes", "manifestCanonicalSha256",
    }
    if not isinstance(bundle, Mapping) or set(bundle) != expected_bundle_keys:
        raise GateError("setup bundle binding fields differ")
    if (
        SHA256.fullmatch(str(bundle["bundleSha256"])) is None
        or SHA256.fullmatch(str(bundle["manifestCanonicalSha256"])) is None
        or not isinstance(bundle["bundleSizeBytes"], int)
        or bundle["bundleSizeBytes"] <= 0
    ):
        raise GateError("setup bundle identity is invalid")
    return {
        **plan_binding(bindings),
        "gatePlanCanonicalSha256": canonical_sha256(gate_plan),
        "operationalTarget": copy.deepcopy(TARGET),
        "setupId": setup_id,
        **dict(bundle),
        "oneShot": True,
        "exactBundleOnly": True,
        "readinessProbeAuthorized": True,
        "readinessCaptureMode": "repeatable-append-only-zero-cell",
        "cellsAuthorized": 0,
        "userOrKeyMutationAllowed": False,
        "foreignResourceMutationAllowed": False,
    }


def expected_gate_setup_text(binding: Mapping[str, Any]) -> str:
    target = binding["operationalTarget"]
    return (
        f"APPROVE GATE-SETUP study={STUDY_EPOCH} change={CHANGE_ID} "
        f"commit={binding['frameworkCommit']} setup={binding['setupId']} "
        f"bundle={binding['bundleSha256']} manifest={binding['manifestCanonicalSha256']} "
        f"bytes={binding['bundleSizeBytes']} target={target['target']} "
        f"transportUser={target['transportUser']} setupUser={target['setupUser']} "
        f"executionUser={target['executionUser']} checkout={target['checkoutRoot']} "
        "action=install-exact-bundle-once readiness-probe=repeatable-append-only-zero-cell "
        "cells=0 user-key-mutation=false "
        "foreign-mutation=false runtime=false promotion=false"
    )


def validate_gate_setup(
    document: Any, bindings: Bindings, gate_plan: Mapping[str, Any],
    *, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    require_fresh: bool = True,
) -> dict[str, Any]:
    keys = {
        "schemaVersion", "kind", "gate", "decision", "typedApproval",
        "approvedBy", "approvedAt", "bindings", "setupAuthorized",
        "externalMutationAuthorized", "runtimeAuthorized", "promotionAuthorized",
    }
    if not isinstance(document, dict) or set(document) != keys:
        raise GateError("GATE-SETUP receipt fields differ")
    supplied = document.get("bindings")
    if not isinstance(supplied, dict):
        raise GateError("GATE-SETUP bindings are missing")
    expected = setup_binding(
        bindings, gate_plan,
        {key: supplied.get(key) for key in (
            "bundleSha256", "bundleSizeBytes", "manifestCanonicalSha256"
        )},
        supplied.get("setupId"),
    )
    if (
        document["schemaVersion"] != 1 or document["kind"] != SETUP_KIND
        or document["gate"] != "GATE-SETUP"
        or document["decision"] != "authorize-exact-one-shot-setup"
        or supplied != expected
        or document["typedApproval"] != expected_gate_setup_text(expected)
        or not isinstance(document["approvedBy"], str) or not document["approvedBy"].strip()
        or document["setupAuthorized"] is not True
        or document["externalMutationAuthorized"] is not True
        or document["runtimeAuthorized"] is not False
        or document["promotionAuthorized"] is not False
    ):
        raise GateError("GATE-SETUP identity, typed approval, or authority differs")
    approved = _timestamp(document["approvedAt"], "GATE-SETUP.approvedAt")
    plan_approved = _timestamp(gate_plan["approvedAt"], "GATE-PLAN.approvedAt")
    if approved < plan_approved:
        raise GateError("GATE-SETUP predates GATE-PLAN")
    if require_fresh:
        now = _now(clock)
        policy = _validate_policy(_json_file(POLICY, "runtime policy"))
        age = (now - approved).total_seconds()
        if age < -policy["maximumClockSkewSeconds"] or age > policy["maximumGateAgeSeconds"]:
            raise GateError("GATE-SETUP is future-dated beyond skew or stale")
    return document


def _safe_relative(value: Any, where: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise GateError(f"{where} is not a POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise GateError(f"{where} is not a normalized relative path")
    return path


def replay_readiness_seam(
    seam: str, document: Any, bindings: Bindings, gate_setup: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute one target-readiness verdict from raw retained facts."""
    if not isinstance(document, dict) or set(document) != {
        "schemaVersion", "kind", "checkId", "facts",
    }:
        raise GateError(f"{seam}: evidence envelope differs")
    if (
        document["schemaVersion"] != 1
        or document["kind"] != "hotel-srv4-readiness-evidence-v1"
        or document["checkId"] != seam
        or not isinstance(document["facts"], dict)
    ):
        raise GateError(f"{seam}: evidence identity differs")
    facts = document["facts"]
    target = TARGET
    setup = gate_setup["bindings"]
    if seam == "installed-bundle-bytes":
        if set(facts) != {
            "bundleSha256", "bundleSizeBytes", "manifestCanonicalSha256",
            "expectedEntriesSha256", "observedEntriesSha256", "installedFileCount",
        }:
            raise GateError(f"{seam}: fact fields differ")
        if (
            facts["bundleSha256"] != setup["bundleSha256"]
            or facts["bundleSizeBytes"] != setup["bundleSizeBytes"]
            or facts["manifestCanonicalSha256"] != setup["manifestCanonicalSha256"]
            or SHA256.fullmatch(str(facts["expectedEntriesSha256"])) is None
            or facts["observedEntriesSha256"] != facts["expectedEntriesSha256"]
            or not isinstance(facts["installedFileCount"], int)
            or facts["installedFileCount"] <= 0
        ):
            raise GateError(f"{seam}: installed payload does not replay")
    elif seam == "target-execution-identity":
        if facts != {
            "transportUser": "root", "setupUser": "root",
            "executionUser": "fhuebscher", "uid": 1007, "gid": 1007,
            "supplementaryGids": [27, 998], "accountMutationObserved": False,
        }:
            raise GateError(f"{seam}: uid/gid or immutable account boundary differs")
    elif seam == "docker-runtime-and-membership":
        if set(facts) != {
            "serverVersion", "socketGid", "executionUserGids",
            "daemonReachableAsExecutionUser", "composeAvailable",
        } or (
            facts["serverVersion"] != target["dockerVersion"]
            or facts["socketGid"] != target["dockerGid"]
            or not isinstance(facts["executionUserGids"], list)
            or target["dockerGid"] not in facts["executionUserGids"]
            or facts["daemonReachableAsExecutionUser"] is not True
            or facts["composeAvailable"] is not True
        ):
            raise GateError(f"{seam}: Docker identity or execution access differs")
    elif seam == "campaign-path-ownership":
        expected_paths = {
            key: target[key] for key in (
                "authorizedParent", "releaseParent", "checkoutRoot", "artifactParent", "leaseRoot",
                "leasePath", "controlRoot",
            )
        }
        if set(facts) != {"paths", "ownership", "preSetupAbsent", "leasePathAbsent"} or (
            facts["paths"] != expected_paths
            or facts["ownership"] != [
                {"path": target["releaseParent"], "uid": 0, "gid": 0,
                 "traversable": True, "writable": False, "symlink": False},
                {"path": target["checkoutRoot"], "uid": 0, "gid": 0,
                 "traversable": True, "writable": False, "symlink": False},
                {"path": target["artifactParent"], "uid": 1007, "gid": 1007,
                 "traversable": True, "writable": True, "symlink": False},
                {"path": target["leaseRoot"], "uid": 0, "gid": 0,
                 "traversable": True, "writable": False, "symlink": False},
                {"path": target["controlRoot"], "uid": 0, "gid": 0,
                 "traversable": False, "writable": False, "symlink": False},
            ]
            or facts["preSetupAbsent"] != [
                target["releaseParent"], target["artifactParent"], target["leasePath"]
            ]
            or facts["leasePathAbsent"] is not True
        ):
            raise GateError(f"{seam}: installed path ownership differs")
    elif seam == "fixed-ports-free":
        if facts != {
            "observations": [
                {"port": 35005, "listeners": []},
                {"port": 36685, "listeners": []},
            ]
        }:
            raise GateError(f"{seam}: fixed Hotel ports are not free")
    elif seam == "foreign-project-preserved":
        if set(facts) != {
            "project", "beforeFingerprint", "afterFingerprint",
            "configPath", "beforeStateCounts", "afterStateCounts",
            "beforeResources", "afterResources", "mutationActions",
        } or (
            facts["project"] is not None
            or facts["configPath"] is not None
            or facts["beforeStateCounts"] != {}
            or facts["afterStateCounts"] != {}
            or SHA256.fullmatch(str(facts["beforeFingerprint"])) is None
            or facts["afterFingerprint"] != facts["beforeFingerprint"]
            or facts["beforeResources"] != []
            or facts["afterResources"] != []
            or facts["mutationActions"] != []
        ):
            raise GateError(f"{seam}: a foreign Compose project or container is present")
    elif seam == "target-runner-executable-replay":
        expected_argv = [
            _replayed_spelling(facts, 0, "runuser", RUNUSER_CANDIDATES),
            "--user", "fhuebscher", "--",
            _replayed_spelling(facts, 4, "python3", TARGET_PYTHON_CANDIDATES), "-I",
            target["checkoutRoot"] + "/modules/hotel-reservation/execution/candidate_runtime.py",
            "--target-self-check", setup["manifestCanonicalSha256"],
        ]
        if set(facts) != {"argv", "returnCode", "stdout", "stderr"} or (
            facts["argv"] != expected_argv or facts["returnCode"] != 0
            or facts["stderr"] != "" or facts["stdout"] != {
                "kind": "hotel-srv4-target-self-check-v1", "status": "pass",
                "manifestCanonicalSha256": setup["manifestCanonicalSha256"],
                "executionUid": 1007, "executionGid": 1007,
            }
        ):
            raise GateError(f"{seam}: installed target runner did not execute and replay")
    elif seam == "terminal-validator-executable-replay":
        expected_argv = [
            _replayed_spelling(facts, 0, "runuser", RUNUSER_CANDIDATES),
            "--user", "fhuebscher", "--",
            _replayed_spelling(facts, 4, "python3", TARGET_PYTHON_CANDIDATES), "-I",
            target["checkoutRoot"] + "/modules/hotel-reservation/validation/candidate_terminal.py",
            "--self-check",
        ]
        if set(facts) != {"argv", "returnCode", "stdout", "stderr"} or (
            facts["argv"] != expected_argv or facts["returnCode"] != 0
            or facts["stderr"] != "" or facts["stdout"] != {
                "kind": "hotel-candidate-terminal-self-check-v1", "status": "pass",
            }
        ):
            raise GateError(f"{seam}: local terminal validator did not execute and replay")
    else:
        raise GateError(f"unknown readiness seam: {seam}")
    return {"checkId": seam, "verdict": "pass"}


def validate_readiness(
    document: Any, bindings: Bindings, gate_setup: Mapping[str, Any], artifact_parent: Path,
    *, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    keys = {
        "schemaVersion", "kind", "studyEpoch", "changeId", "bindings",
        "gateSetupCanonicalSha256", "captureId", "artifactRoot", "observedAt", "setupCompletedAt",
        "hostObserved", "producer", "seams", "promotionAuthorized",
    }
    if not isinstance(document, dict) or set(document) != keys:
        raise GateError("runtime readiness receipt fields differ")
    if (
        document["schemaVersion"] != 4 or document["kind"] != READINESS_KIND
        or document["studyEpoch"] != STUDY_EPOCH or document["changeId"] != CHANGE_ID
        or document["bindings"] != plan_binding(bindings)
        or document["gateSetupCanonicalSha256"] != canonical_sha256(gate_setup)
        or READINESS_CAPTURE_ID.fullmatch(str(document["captureId"])) is None
        or document["artifactRoot"] != "readiness-" + document["captureId"]
        or document["hostObserved"] != TARGET["target"]
        or document["producer"] != {
            "target": TARGET["target"],
            "transportUser": TARGET["transportUser"],
            "entrypoint": TARGET["checkoutRoot"] + "/" + CONTROLLER_PATHS["candidate-runtime"],
            "entrypointSha256": bindings.controller_sha256["candidate-runtime"],
            "captureId": document["captureId"],
            "cellsRun": 0,
        }
        or document["promotionAuthorized"] is not False
    ):
        raise GateError("runtime readiness identity or authority differs")
    observed = _timestamp(document["observedAt"], "runtime readiness observedAt")
    setup_completed = _timestamp(document["setupCompletedAt"], "runtime readiness setupCompletedAt")
    setup_approved = _timestamp(gate_setup["approvedAt"], "GATE-SETUP.approvedAt")
    if setup_completed < setup_approved or observed < setup_completed:
        raise GateError("runtime readiness predates setup completion")
    policy = _validate_policy(_json_file(POLICY, "runtime policy"))
    age = (_now(clock) - observed).total_seconds()
    if age < -policy["maximumClockSkewSeconds"] or age > policy["maximumGateAgeSeconds"]:
        raise GateError("runtime readiness is future-dated beyond skew or stale")
    candidate_root = artifact_parent / _safe_relative(
        document["artifactRoot"], "readiness artifact root"
    )
    if candidate_root.is_symlink():
        raise GateError("runtime readiness artifact root is a symlink")
    root = candidate_root.resolve(strict=True)
    if artifact_parent.resolve(strict=True) not in root.parents or root.is_symlink() or not root.is_dir():
        raise GateError("runtime readiness artifact root escapes its parent")
    seams = document.get("seams")
    if not isinstance(seams, list) or [row.get("id") for row in seams if isinstance(row, dict)] != list(READINESS_SEAMS):
        raise GateError("runtime readiness seam order differs")
    for row in seams:
        if set(row) != {
            "id", "evidencePath", "evidenceSha256", "failureWitnessPath",
            "failureWitnessSha256", "expectedFailureDiagnostic",
        }:
            raise GateError(f"runtime readiness seam fields differ: {row.get('id')}")
        loaded: dict[str, Any] = {}
        for path_key, sha_key in (("evidencePath", "evidenceSha256"), ("failureWitnessPath", "failureWitnessSha256")):
            path = root / _safe_relative(row[path_key], f"{row['id']} {path_key}")
            resolved = path.resolve(strict=True)
            if root not in resolved.parents or path.is_symlink() or not path.is_file():
                raise GateError(f"runtime readiness artifact escapes root: {row['id']}")
            if _sha256(path) != row[sha_key] or SHA256.fullmatch(str(row[sha_key])) is None:
                raise GateError(f"runtime readiness digest differs: {row['id']} {path_key}")
            loaded[path_key] = _json_file(path, f"readiness {row['id']} {path_key}")
        replay_readiness_seam(row["id"], loaded["evidencePath"], bindings, gate_setup)
        try:
            replay_readiness_seam(
                row["id"], loaded["failureWitnessPath"], bindings, gate_setup,
            )
        except GateError as exc:
            if str(exc) != row["expectedFailureDiagnostic"]:
                raise GateError(f"runtime readiness planted diagnostic differs: {row['id']}") from exc
        else:
            raise GateError(f"runtime readiness planted defect was not rejected: {row['id']}")
    return document


def _bindings_from_installed_gate_setup(document: Any) -> Bindings:
    """Recover and revalidate the immutable plan binding on the installed target."""
    keys = {
        "schemaVersion", "kind", "gate", "decision", "typedApproval",
        "approvedBy", "approvedAt", "bindings", "setupAuthorized",
        "externalMutationAuthorized", "runtimeAuthorized", "promotionAuthorized",
    }
    if not isinstance(document, dict) or set(document) != keys:
        raise GateError("installed GATE-SETUP receipt fields differ")
    supplied = document.get("bindings")
    if not isinstance(supplied, dict):
        raise GateError("installed GATE-SETUP bindings are missing")
    # D6: recover the claim ceiling from the installed policy, never from the
    # receipt, so the identity comparison below still proves the receipt agrees
    # with declared policy instead of comparing the receipt with itself.
    ceiling = _validate_posture_ceiling(
        _validate_policy(_json_file(POLICY, "runtime policy"))["postureCeiling"]
    )
    try:
        recovered = Bindings(
            framework_commit=supplied["frameworkCommit"],
            framework_tree=supplied["frameworkTree"],
            descriptor_sha256=supplied["descriptorCanonicalSha256"],
            compiled_plan_sha256=supplied["compiledPlanCanonicalSha256"],
            runtime_policy_sha256=supplied["runtimePolicyCanonicalSha256"],
            controller_sha256=dict(supplied["controllerSha256"]),
            run_count=supplied["runCount"],
            unsupported_postures=tuple(unsupported_posture_ids(ceiling)),
            source_cost_comparison_state=ceiling["sourceCostComparisonState"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GateError("installed GATE-SETUP plan binding is malformed") from exc
    base = plan_binding(recovered)
    setup_only = {
        "gatePlanCanonicalSha256", "operationalTarget", "setupId",
        "bundleSha256", "bundleSizeBytes", "manifestCanonicalSha256",
        "oneShot", "exactBundleOnly", "readinessProbeAuthorized", "readinessCaptureMode",
        "cellsAuthorized",
        "userOrKeyMutationAllowed", "foreignResourceMutationAllowed",
    }
    if (
        set(supplied) != set(base) | setup_only
        or COMMIT.fullmatch(str(recovered.framework_commit)) is None
        or COMMIT.fullmatch(str(recovered.framework_tree)) is None
        or any(SHA256.fullmatch(str(value)) is None for value in (
            recovered.descriptor_sha256, recovered.compiled_plan_sha256,
            recovered.runtime_policy_sha256,
        ))
        or set(recovered.controller_sha256) != set(CONTROLLER_PATHS)
        or any(SHA256.fullmatch(str(value)) is None for value in recovered.controller_sha256.values())
        or recovered.run_count != CELL_COUNT
        or any(supplied.get(key) != value for key, value in base.items())
        or supplied.get("operationalTarget") != TARGET
        or SETUP_ID.fullmatch(str(supplied.get("setupId"))) is None
        or SHA256.fullmatch(str(supplied.get("gatePlanCanonicalSha256"))) is None
        or SHA256.fullmatch(str(supplied.get("bundleSha256"))) is None
        or SHA256.fullmatch(str(supplied.get("manifestCanonicalSha256"))) is None
        or not isinstance(supplied.get("bundleSizeBytes"), int)
        or supplied["bundleSizeBytes"] <= 0
        or supplied.get("oneShot") is not True
        or supplied.get("exactBundleOnly") is not True
        or supplied.get("readinessProbeAuthorized") is not True
        or supplied.get("readinessCaptureMode") != "repeatable-append-only-zero-cell"
        or supplied.get("cellsAuthorized") != 0
        or supplied.get("userOrKeyMutationAllowed") is not False
        or supplied.get("foreignResourceMutationAllowed") is not False
        or document.get("schemaVersion") != 1
        or document.get("kind") != SETUP_KIND
        or document.get("gate") != "GATE-SETUP"
        or document.get("decision") != "authorize-exact-one-shot-setup"
        or document.get("typedApproval") != expected_gate_setup_text(supplied)
        or not isinstance(document.get("approvedBy"), str)
        or not document["approvedBy"].strip()
        or document.get("setupAuthorized") is not True
        or document.get("externalMutationAuthorized") is not True
        or document.get("runtimeAuthorized") is not False
        or document.get("promotionAuthorized") is not False
    ):
        raise GateError("installed GATE-SETUP identity or authority differs")
    _timestamp(document["approvedAt"], "installed GATE-SETUP.approvedAt")
    return recovered


def _validate_target_setup_receipt(
    document: Any, gate_setup: Mapping[str, Any], manifest: Mapping[str, Any],
) -> dict[str, Any]:
    keys = {
        "schemaVersion", "kind", "setupId", "target", "bundleSha256",
        "bundleSizeBytes", "manifestCanonicalSha256", "installedEntriesSha256",
        "installedFileCount", "executionUid", "executionGid", "dockerGid",
        "dockerVersion", "foreignProject", "foreignConfigPath", "foreignStateCounts",
        "foreignFingerprint", "foreignResources", "ports", "preSetupAbsent",
        "gateSetupCanonicalSha256", "completedAt", "cellsRun", "runtimeStarted",
        "foreignMutation",
    }
    binding = gate_setup["bindings"]
    if not isinstance(document, dict) or set(document) != keys:
        raise GateError("target setup install receipt fields differ")
    if (
        document["schemaVersion"] != 1
        or document["kind"] != "hotel-srv4-install-receipt-v1"
        or document["setupId"] != binding["setupId"]
        or document["target"] != TARGET["target"]
        or document["bundleSha256"] != binding["bundleSha256"]
        or document["bundleSizeBytes"] != binding["bundleSizeBytes"]
        or document["manifestCanonicalSha256"] != binding["manifestCanonicalSha256"]
        or document["installedEntriesSha256"] != canonical_sha256(manifest["entries"])
        or document["installedFileCount"] != len(manifest["entries"])
        or document["executionUid"] != TARGET["executionUid"]
        or document["executionGid"] != TARGET["executionGid"]
        or document["dockerGid"] != TARGET["dockerGid"]
        or document["dockerVersion"] != TARGET["dockerVersion"]
        or document["foreignProject"] is not None
        or document["foreignConfigPath"] is not None
        or document["foreignStateCounts"] != {}
        or SHA256.fullmatch(str(document["foreignFingerprint"])) is None
        or document["foreignResources"] != []
        or document["ports"] != {"35005": [], "36685": []}
        or document["preSetupAbsent"] != [
            TARGET["releaseParent"], TARGET["artifactParent"], TARGET["leasePath"],
        ]
        or document["gateSetupCanonicalSha256"] != canonical_sha256(gate_setup)
        or document["cellsRun"] != 0
        or document["runtimeStarted"] is not False
        or document["foreignMutation"] is not False
    ):
        raise GateError("target setup install receipt identity or boundary differs")
    _timestamp(document["completedAt"], "target setup install completedAt")
    return document


def _target_probe(argv: list[str], *, json_stdout: bool = False) -> dict[str, Any]:
    try:
        result = subprocess.run(
            argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"argv": argv, "returnCode": 125, "stdout": "", "stderr": str(exc)}
    stdout: Any = result.stdout
    if json_stdout and result.returncode == 0:
        try:
            stdout = strict_json(result.stdout, "target readiness command stdout")
        except GateError:
            stdout = result.stdout
    return {
        "argv": argv, "returnCode": result.returncode,
        "stdout": stdout, "stderr": result.stderr,
    }


def foreign_rows(ps_rows: list[str], projects: Any, prefix: str = OWN_PROJECT_PREFIX) -> list[str]:
    """Every container or Compose project on the host that is not the campaign's own.

    Host condition v2 requires this list to be empty before and after every step;
    it is recorded, not assumed, so an absence claim is backed by the inventory
    that established it.
    """
    if not isinstance(projects, list):
        raise GateError("compose inventory differs")
    foreign = []
    for row in ps_rows:
        labels = dict(
            item.split("=", 1) for item in row.split("|", 4)[4].split(",") if "=" in item
        ) if row.count("|") >= 4 else {}
        if not str(labels.get("com.docker.compose.project", "")).startswith(prefix):
            foreign.append(row)
    for row in projects:
        name = row.get("Name") if isinstance(row, dict) else None
        if not str(name).startswith(prefix):
            foreign.append(f"compose-project|{name}|{row.get('ConfigFiles') if isinstance(row, dict) else None}")
    return sorted(foreign)


def _target_foreign_snapshot() -> dict[str, Any]:
    rows_probe = _target_probe([
        "docker", "ps", "-a", "--no-trunc",
        "--format", "{{.ID}}|{{.State}}|{{.Image}}|{{.Names}}|{{.Labels}}",
    ])
    projects_probe = _target_probe(["docker", "compose", "ls", "--all", "--format", "json"])
    if rows_probe["returnCode"] or projects_probe["returnCode"]:
        raise GateError("host container inventory command failed")
    try:
        projects = strict_json(projects_probe["stdout"], "target compose inventory")
    except GateError as exc:
        raise GateError("target compose inventory is invalid") from exc
    rows = foreign_rows(
        [row for row in str(rows_probe["stdout"]).splitlines() if row], projects,
    )
    if rows:
        raise GateError("a foreign Compose project or container is present on the target")
    value = {"project": None, "configPath": None, "stateCounts": {}, "rows": rows}
    value["sha256"] = canonical_sha256(value)
    return value


def _mode_allows(metadata: os.stat_result, uid: int, gids: set[int], masks: tuple[int, int, int]) -> bool:
    if metadata.st_uid == uid:
        mask = masks[0]
    elif metadata.st_gid in gids:
        mask = masks[1]
    else:
        mask = masks[2]
    return bool(metadata.st_mode & mask)


def _path_access(path: Path, uid: int, gids: set[int]) -> tuple[bool, bool]:
    chain = [path, *path.parents]
    traversable = all(
        _mode_allows(item.stat(), uid, gids, (stat.S_IXUSR, stat.S_IXGRP, stat.S_IXOTH))
        for item in chain if item != Path("/")
    )
    writable = _mode_allows(path.stat(), uid, gids, (stat.S_IWUSR, stat.S_IWGRP, stat.S_IWOTH))
    return traversable, writable


def _port_observation(port: int) -> dict[str, Any]:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return {"port": port, "listeners": ["occupied"]}
    return {"port": port, "listeners": []}


def _plant_readiness_defect(seam: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
    planted = copy.deepcopy(dict(evidence))
    facts = planted["facts"]
    if seam == "installed-bundle-bytes":
        facts["observedEntriesSha256"] = "0" * 64
    elif seam == "target-execution-identity":
        facts["uid"] = TARGET["executionUid"] + 1
    elif seam == "docker-runtime-and-membership":
        facts["serverVersion"] = "0.0.0-planted"
    elif seam == "campaign-path-ownership":
        facts["ownership"][0]["symlink"] = True
    elif seam == "fixed-ports-free":
        facts["observations"][0]["listeners"] = ["planted"]
    elif seam == "foreign-project-preserved":
        facts["afterFingerprint"] = "0" * 64
    elif seam in {"target-runner-executable-replay", "terminal-validator-executable-replay"}:
        facts["returnCode"] = 1
    else:
        raise GateError(f"cannot plant unknown readiness seam: {seam}")
    return planted


def _write_exclusive_json(path: Path, value: Any, *, uid: int | None = None, gid: int | None = None) -> None:
    payload = canonical_bytes(value) + b"\n"
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600,
    )
    try:
        if os.write(descriptor, payload) != len(payload):
            raise GateError(f"short write to {path.name}")
        os.fsync(descriptor)
        if uid is not None and gid is not None:
            os.fchown(descriptor, uid, gid)
    finally:
        os.close(descriptor)


def new_readiness_capture_id(
    *, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> str:
    observed = _now(clock)
    stamp = observed.strftime("%Y%m%dt%H%M%Sz")
    return f"hotel-readiness-v1-{stamp}-{secrets.token_hex(4)}"


def produce_target_readiness(
    setup_id: str, capture_id: str, *,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Run fixed read-only target probes and retain their watched-failure replay."""
    if SETUP_ID.fullmatch(setup_id) is None:
        raise GateError("target readiness setup identity differs")
    if READINESS_CAPTURE_ID.fullmatch(capture_id) is None:
        raise GateError("target readiness capture identity differs")
    if os.geteuid() != 0 or ROOT.resolve() != Path(TARGET["checkoutRoot"]):
        raise GateError("target readiness producer is not root in the exact installed checkout")
    if socket.gethostname().split(".")[0] != TARGET["target"]:
        raise GateError("target readiness producer host differs")
    control = Path(TARGET["controlRoot"])
    gate_setup = _json_file(control / "gate-setup.json", "installed GATE-SETUP")
    bindings = _bindings_from_installed_gate_setup(gate_setup)
    if gate_setup["bindings"]["setupId"] != setup_id:
        raise GateError("target readiness setup ID differs from installed gate")
    manifest = verify_installed_payload(
        bindings.framework_commit, gate_setup["bindings"]["manifestCanonicalSha256"],
        ROOT, full=True,
    )
    setup_receipt = _validate_target_setup_receipt(
        _json_file(control / "setup-install.json", "target setup install receipt"),
        gate_setup, manifest,
    )
    manifest_by_path = {
        row.get("path"): row.get("sha256") for row in manifest["entries"]
        if isinstance(row, dict)
    }
    if any(
        manifest_by_path.get(path) != bindings.controller_sha256[name]
        for name, path in CONTROLLER_PATHS.items()
    ):
        raise GateError("installed controller digest differs from GATE-PLAN")
    root_name = "readiness-" + capture_id
    artifact_parent = Path(TARGET["artifactParent"])
    artifact_root = artifact_parent / root_name
    if artifact_root.exists() or artifact_root.is_symlink():
        if artifact_root.is_symlink() or not artifact_root.is_dir():
            raise GateError("target readiness capture path is not an append-only directory")
        try:
            retained = _json_file(
                artifact_root / "readiness.json", "retained target readiness capture",
            )
            return validate_readiness(
                retained, bindings, gate_setup, artifact_parent, clock=clock,
            )
        except (GateError, OSError) as exc:
            raise GateError(
                "target readiness capture identity already exists but is incomplete or invalid"
            ) from exc
    expected_entries = manifest["entries"]
    observed_entries = _payload_entries(ROOT)
    account = pwd.getpwnam(TARGET["executionUser"])
    all_gids = sorted(set(os.getgrouplist(TARGET["executionUser"], account.pw_gid)))
    supplementary = sorted(set(all_gids) - {account.pw_gid})
    docker_root = _target_probe(["docker", "version", "--format", "{{.Server.Version}}"])
    runuser = target_runuser()
    python3 = target_python()
    docker_user = _target_probe([
        runuser, "--user", TARGET["executionUser"], "--",
        "docker", "version", "--format", "{{.Server.Version}}",
    ])
    compose_user = _target_probe([
        runuser, "--user", TARGET["executionUser"], "--",
        "docker", "compose", "version", "--short",
    ])
    identity_gids = set(all_gids)
    ownership = []
    for key in ("releaseParent", "checkoutRoot", "artifactParent", "leaseRoot", "controlRoot"):
        path = Path(TARGET[key])
        metadata = path.lstat()
        traversable, writable = _path_access(path, TARGET["executionUid"], identity_gids)
        ownership.append({
            "path": str(path), "uid": metadata.st_uid, "gid": metadata.st_gid,
            "traversable": traversable, "writable": writable, "symlink": path.is_symlink(),
        })
    current_foreign = _target_foreign_snapshot()
    target_runner_argv = [
        runuser, "--user", TARGET["executionUser"], "--",
        python3, "-I",
        TARGET["checkoutRoot"] + "/" + CONTROLLER_PATHS["candidate-runtime"],
        "--target-self-check", gate_setup["bindings"]["manifestCanonicalSha256"],
    ]
    terminal_argv = [
        runuser, "--user", TARGET["executionUser"], "--",
        python3, "-I",
        TARGET["checkoutRoot"] + "/" + CONTROLLER_PATHS["candidate-terminal"],
        "--self-check",
    ]
    evidence_by_seam = {
        "installed-bundle-bytes": {
            "bundleSha256": gate_setup["bindings"]["bundleSha256"],
            "bundleSizeBytes": gate_setup["bindings"]["bundleSizeBytes"],
            "manifestCanonicalSha256": gate_setup["bindings"]["manifestCanonicalSha256"],
            "expectedEntriesSha256": canonical_sha256(expected_entries),
            "observedEntriesSha256": canonical_sha256(observed_entries),
            "installedFileCount": len(observed_entries),
        },
        "target-execution-identity": {
            "transportUser": "root", "setupUser": "root",
            "executionUser": account.pw_name, "uid": account.pw_uid, "gid": account.pw_gid,
            "supplementaryGids": supplementary, "accountMutationObserved": False,
        },
        "docker-runtime-and-membership": {
            "serverVersion": str(docker_root["stdout"]).strip(),
            "socketGid": os.stat("/var/run/docker.sock").st_gid,
            "executionUserGids": all_gids,
            "daemonReachableAsExecutionUser": (
                docker_user["returnCode"] == 0
                and str(docker_user["stdout"]).strip() == str(docker_root["stdout"]).strip()
            ),
            "composeAvailable": compose_user["returnCode"] == 0,
        },
        "campaign-path-ownership": {
            "paths": {key: TARGET[key] for key in (
                "authorizedParent", "releaseParent", "checkoutRoot", "artifactParent",
                "leaseRoot", "leasePath", "controlRoot",
            )},
            "ownership": ownership,
            "preSetupAbsent": setup_receipt["preSetupAbsent"],
            "leasePathAbsent": not os.path.lexists(TARGET["leasePath"]),
        },
        "fixed-ports-free": {
            "observations": [_port_observation(35005), _port_observation(36685)],
        },
        "foreign-project-preserved": {
            "project": None,
            "beforeFingerprint": setup_receipt["foreignFingerprint"],
            "afterFingerprint": current_foreign["sha256"],
            "configPath": current_foreign["configPath"],
            "beforeStateCounts": setup_receipt["foreignStateCounts"],
            "afterStateCounts": current_foreign["stateCounts"],
            "beforeResources": setup_receipt["foreignResources"],
            "afterResources": current_foreign["rows"],
            "mutationActions": [],
        },
        "target-runner-executable-replay": _target_probe(target_runner_argv, json_stdout=True),
        "terminal-validator-executable-replay": _target_probe(terminal_argv, json_stdout=True),
    }
    prepared: list[tuple[str, dict[str, Any], dict[str, Any], str]] = []
    for seam in READINESS_SEAMS:
        positive = {
            "schemaVersion": 1, "kind": "hotel-srv4-readiness-evidence-v1",
            "checkId": seam, "facts": evidence_by_seam[seam],
        }
        replay_readiness_seam(seam, positive, bindings, gate_setup)
        planted = _plant_readiness_defect(seam, positive)
        try:
            replay_readiness_seam(seam, planted, bindings, gate_setup)
        except GateError as exc:
            diagnostic = str(exc)
        else:
            raise GateError(f"target readiness planted defect was not rejected: {seam}")
        prepared.append((seam, positive, planted, diagnostic))
    observed = _now(clock)
    setup_completed = _timestamp(setup_receipt["completedAt"], "target setup install completedAt")
    if observed < setup_completed:
        raise GateError("target readiness clock predates setup completion")
    try:
        artifact_root.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise GateError("target readiness capture identity was claimed concurrently") from exc
    seams = []
    for index, (seam, positive, planted, diagnostic) in enumerate(prepared):
        evidence_name = f"{index:02d}-{seam}-pass.json"
        failure_name = f"{index:02d}-{seam}-planted.json"
        evidence_path = artifact_root / evidence_name
        failure_path = artifact_root / failure_name
        _write_exclusive_json(evidence_path, positive, uid=TARGET["executionUid"], gid=TARGET["executionGid"])
        _write_exclusive_json(failure_path, planted, uid=TARGET["executionUid"], gid=TARGET["executionGid"])
        seams.append({
            "id": seam, "evidencePath": evidence_name,
            "evidenceSha256": _sha256(evidence_path),
            "failureWitnessPath": failure_name,
            "failureWitnessSha256": _sha256(failure_path),
            "expectedFailureDiagnostic": diagnostic,
        })
    receipt = {
        "schemaVersion": 4, "kind": READINESS_KIND,
        "studyEpoch": STUDY_EPOCH, "changeId": CHANGE_ID,
        "bindings": plan_binding(bindings),
        "gateSetupCanonicalSha256": canonical_sha256(gate_setup),
        "captureId": capture_id,
        "artifactRoot": root_name,
        "observedAt": observed.isoformat().replace("+00:00", "Z"),
        "setupCompletedAt": setup_completed.isoformat().replace("+00:00", "Z"),
        "hostObserved": TARGET["target"],
        "producer": {
            "target": TARGET["target"], "transportUser": TARGET["transportUser"],
            "entrypoint": TARGET["checkoutRoot"] + "/" + CONTROLLER_PATHS["candidate-runtime"],
            "entrypointSha256": bindings.controller_sha256["candidate-runtime"],
            "captureId": capture_id,
            "cellsRun": 0,
        },
        "seams": seams, "promotionAuthorized": False,
    }
    _write_exclusive_json(
        artifact_root / "readiness.json", receipt,
        uid=TARGET["executionUid"], gid=TARGET["executionGid"],
    )
    os.chown(artifact_root, TARGET["executionUid"], TARGET["executionGid"])
    return receipt


def _artifact_root(policy: dict[str, Any], transport_id: str, campaign_id: str) -> str:
    parent = policy["allowedTransports"][transport_id]["artifactParent"]
    return f"{parent}/{campaign_id}"


def _run_binding(
    bindings: Bindings, gate_plan: dict[str, Any], gate_setup: dict[str, Any],
    readiness: dict[str, Any],
    transport_id: str, campaign_id: str, deadline: str,
) -> dict[str, Any]:
    policy = _validate_policy(_json_file(POLICY, "runtime policy"))
    if transport_id not in policy["allowedTransports"] or CAMPAIGN_ID.fullmatch(campaign_id) is None:
        raise GateError("transport or campaign identity is not allowed")
    transport = policy["allowedTransports"][transport_id]
    return {
        **plan_binding(bindings),
        "gatePlanCanonicalSha256": canonical_sha256(gate_plan),
        "gateSetupCanonicalSha256": canonical_sha256(gate_setup),
        "readinessCanonicalSha256": canonical_sha256(readiness),
        "readinessCaptureId": readiness["captureId"],
        "readinessObservedAt": readiness["observedAt"],
        "transportId": transport_id,
        "target": transport["target"],
        "transportUser": transport["transportUser"],
        "setupUser": transport["setupUser"],
        "executionUser": transport["executionUser"],
        "executionUid": transport["executionUid"],
        "executionGid": transport["executionGid"],
        "supplementalGids": transport["supplementalGids"],
        "dockerGid": transport["dockerGid"],
        "dockerVersion": transport["dockerVersion"],
        "authorizedParent": transport["authorizedParent"],
        "releaseParent": transport["releaseParent"],
        "checkoutRoot": transport["checkoutRoot"],
        "campaignId": campaign_id,
        "artifactRoot": _artifact_root(policy, transport_id, campaign_id),
        "artifactParent": transport["artifactParent"],
        "leaseRoot": transport["leaseRoot"],
        "leasePath": transport["leasePath"],
        "controlRoot": transport["controlRoot"],
        "projectPrefix": policy["projectPrefix"],
        "ports": policy["ports"],
        "foreignProject": policy["foreignProject"],
        "bundleSha256": gate_setup["bindings"]["bundleSha256"],
        "installationManifestCanonicalSha256": gate_setup["bindings"]["manifestCanonicalSha256"],
        "deadline": deadline,
        "maximumWallSeconds": policy["maximumWallSeconds"],
        "cleanupReserveSeconds": policy["cleanupReserveSeconds"],
        "stopCondition": "first-invalid-cell-or-deadline-before-cleanup-reserve",
        "cleanupActions": policy["cleanup"]["actions"],
    }


def expected_gate_run_text(binding: Mapping[str, Any]) -> str:
    return (
        f"APPROVE GATE-RUN study={STUDY_EPOCH} change={CHANGE_ID} "
        f"commit={binding['frameworkCommit']} plan={binding['compiledPlanCanonicalSha256']} "
        f"transport={binding['transportId']} target={binding['target']} "
        f"transportUser={binding['transportUser']} setupUser={binding['setupUser']} "
        f"executionUser={binding['executionUser']} uid={binding['executionUid']} "
        f"gid={binding['executionGid']} dockerGid={binding['dockerGid']} "
        f"campaign={binding['campaignId']} "
        f"readinessCapture={binding['readinessCaptureId']} "
        f"readinessObserved={binding['readinessObservedAt']} "
        f"root={binding['artifactRoot']} lease={binding['leasePath']} "
        f"projectPrefix={binding['projectPrefix']} ports=35005,36685 cells={binding['runCount']} "
        f"wallSeconds={MAXIMUM_WALL_SECONDS} cleanupReserveSeconds=300 deadline={binding['deadline']} "
        f"nuisance={','.join(NUISANCE_FACTORS)} claim=candidate-only "
        "stop=first-invalid-or-deadline cleanup=owned-resources-only "
        "foreign-mutation=false promotion=false"
    )


def validate_gate_run(
    document: Any, bindings: Bindings, gate_plan: dict[str, Any], gate_setup: dict[str, Any],
    readiness: dict[str, Any], *, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    keys = {
        "schemaVersion", "kind", "gate", "decision", "typedApproval",
        "approvedBy", "approvedAt", "bindings", "runtimeAuthorized",
        "externalMutationAuthorized", "promotionAuthorized",
    }
    if not isinstance(document, dict) or set(document) != keys:
        raise GateError("GATE-RUN receipt fields differ")
    run_binding = document.get("bindings")
    if not isinstance(run_binding, dict):
        raise GateError("GATE-RUN bindings are missing")
    expected = _run_binding(
        bindings, gate_plan, gate_setup, readiness, run_binding.get("transportId"),
        run_binding.get("campaignId"), run_binding.get("deadline"),
    )
    if (
        document["schemaVersion"] != 1 or document["kind"] != RUN_KIND
        or document["gate"] != "GATE-RUN" or document["decision"] != "authorize-exact-run"
        or run_binding != expected or document["typedApproval"] != expected_gate_run_text(expected)
        or not isinstance(document["approvedBy"], str) or not document["approvedBy"].strip()
        or document["runtimeAuthorized"] is not True
        or document["externalMutationAuthorized"] is not True
        or document["promotionAuthorized"] is not False
    ):
        raise GateError("GATE-RUN identity, typed approval, or authority differs")
    now = _now(clock)
    approved = _timestamp(document["approvedAt"], "GATE-RUN.approvedAt")
    plan_approved = _timestamp(gate_plan["approvedAt"], "GATE-PLAN.approvedAt")
    deadline = _timestamp(expected["deadline"], "GATE-RUN.deadline")
    policy = _validate_policy(_json_file(POLICY, "runtime policy"))
    if approved < plan_approved:
        raise GateError("GATE-RUN predates GATE-PLAN")
    age = (now - approved).total_seconds()
    setup_approved = _timestamp(gate_setup["approvedAt"], "GATE-SETUP.approvedAt")
    if approved < setup_approved:
        raise GateError("GATE-RUN predates GATE-SETUP")
    if age < -policy["maximumClockSkewSeconds"] or age > policy["maximumGateAgeSeconds"]:
        raise GateError("GATE-RUN is future-dated beyond skew or stale")
    readiness_observed = _timestamp(expected["readinessObservedAt"], "GATE-RUN.readinessObservedAt")
    readiness_age = (now - readiness_observed).total_seconds()
    if (
        approved < readiness_observed
        or readiness_age < -policy["maximumClockSkewSeconds"]
        or readiness_age > policy["maximumGateAgeSeconds"]
    ):
        raise GateError("GATE-RUN is not bound to fresh target-produced readiness")
    remaining = (deadline - now).total_seconds()
    if remaining < policy["minimumFirstMutationRemainingSeconds"]:
        raise GateError("GATE-RUN leaves insufficient run plus cleanup time")
    if remaining > policy["maximumWallSeconds"] + policy["maximumClockSkewSeconds"]:
        raise GateError("GATE-RUN deadline exceeds the bounded wall budget")
    return document


def admit_runtime(
    framework_commit: str, gate_plan_path: Path, gate_setup_path: Path, readiness_path: Path,
    readiness_artifact_parent: Path, gate_run_path: Path,
    *, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    bindings = inspect_bindings(framework_commit)
    gate_plan = validate_gate_plan(_json_file(gate_plan_path, "GATE-PLAN"), bindings)
    gate_setup = validate_gate_setup(
        _json_file(gate_setup_path, "GATE-SETUP"), bindings, gate_plan, clock=clock,
        require_fresh=False,
    )
    readiness_document = _json_file(readiness_path, "runtime readiness")
    expected_readiness_path = (
        readiness_artifact_parent
        / _safe_relative(readiness_document.get("artifactRoot"), "readiness artifact root")
        / "readiness.json"
    )
    if readiness_path.resolve(strict=True) != expected_readiness_path.resolve(strict=True):
        raise GateError("runtime readiness path is not the fetched target-produced receipt")
    readiness = validate_readiness(
        readiness_document, bindings, gate_setup,
        readiness_artifact_parent, clock=clock,
    )
    gate_run = validate_gate_run(
        _json_file(gate_run_path, "GATE-RUN"), bindings, gate_plan, gate_setup, readiness,
        clock=clock,
    )
    current = inspect_bindings(framework_commit)
    if current != bindings:
        raise GateError("runtime bindings changed during admission")
    body = {
        "schemaVersion": 1,
        "kind": ADMISSION_KIND,
        "bindings": gate_run["bindings"],
        "gatePlanCanonicalSha256": canonical_sha256(gate_plan),
        "gateSetupCanonicalSha256": canonical_sha256(gate_setup),
        "readinessCanonicalSha256": canonical_sha256(readiness),
        "gateRunCanonicalSha256": canonical_sha256(gate_run),
        "runtimeAuthorized": True,
        "externalMutationAuthorized": True,
        "promotionAuthorized": False,
        "issuedAt": _now(clock).isoformat().replace("+00:00", "Z"),
    }
    return {**body, "admissionCanonicalSha256": canonical_sha256(body)}


def validate_launch_admission(
    admission: Any, *,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Independently consume freshness and a full runtime budget at launch."""
    if not isinstance(admission, dict):
        raise GateError("detached launch admission is not an object")
    body = {key: value for key, value in admission.items() if key != "admissionCanonicalSha256"}
    binding = admission.get("bindings")
    policy = _validate_policy(_json_file(POLICY, "runtime policy"))
    transport = policy["allowedTransports"]["ssh-compose"]
    if (
        admission.get("schemaVersion") != 1
        or admission.get("kind") != ADMISSION_KIND
        or admission.get("admissionCanonicalSha256") != canonical_sha256(body)
        or admission.get("runtimeAuthorized") is not True
        or admission.get("externalMutationAuthorized") is not True
        or admission.get("promotionAuthorized") is not False
        or not isinstance(binding, dict)
        or binding.get("transportId") != "ssh-compose"
        or any(binding.get(key) != value for key, value in transport.items() if key != "uploadPath")
        or CAMPAIGN_ID.fullmatch(str(binding.get("campaignId"))) is None
        or READINESS_CAPTURE_ID.fullmatch(str(binding.get("readinessCaptureId"))) is None
        or binding.get("artifactRoot") != _artifact_root(
            policy, "ssh-compose", binding.get("campaignId", "")
        )
        or binding.get("maximumWallSeconds") != policy["maximumWallSeconds"]
        or binding.get("cleanupReserveSeconds") != policy["cleanupReserveSeconds"]
    ):
        raise GateError("detached launch admission identity, authority, or budget differs")
    now = _now(clock)
    issued = _timestamp(admission.get("issuedAt"), "runtime admission issuedAt")
    readiness = _timestamp(
        binding.get("readinessObservedAt"), "runtime admission readinessObservedAt",
    )
    deadline = _timestamp(binding.get("deadline"), "runtime admission deadline")
    max_age = policy["maximumGateAgeSeconds"]
    skew = policy["maximumClockSkewSeconds"]
    for label, observed in (("admission", issued), ("readiness", readiness)):
        age = (now - observed).total_seconds()
        if age < -skew or age > max_age:
            raise GateError(f"detached launch {label} is future-dated beyond skew or stale")
    if issued < readiness:
        raise GateError("detached launch admission predates its readiness capture")
    remaining = (deadline - now).total_seconds()
    if remaining < policy["minimumFirstMutationRemainingSeconds"]:
        raise GateError("detached launch no longer has the full planned mutation and cleanup budget")
    if remaining > policy["maximumWallSeconds"] + skew:
        raise GateError("detached launch deadline exceeds the admitted runtime budget")
    return admission


def _flatten_plan() -> list[dict[str, Any]]:
    compiler = _load_compiler()
    descriptor = compiler.load_descriptor(DESCRIPTOR)
    plan = compiler.compile_plan(descriptor)
    cells = []
    for root in plan.get("regimeRoots", []):
        for block in root["blocks"]:
            cells.extend(copy.deepcopy(block["cells"]))
    # A parameterised epoch compiles its execution order block by block (randomised within each block).
    for block in plan.get("blocks", []):
        cells.extend(copy.deepcopy(block["cells"]))
    # The quiet calibration epoch compiles one seeded order over all its cells (no block-wise order).
    if "sequence" in plan:
        cells.extend(copy.deepcopy(plan["sequence"]["cells"]))
    if len(cells) != CELL_COUNT or len({cell["runId"] for cell in cells}) != CELL_COUNT:
        raise GateError(f"compiled plan does not contain {CELL_COUNT} unique cells")
    return cells


def cell_contracts(admission: Mapping[str, Any]) -> list[dict[str, Any]]:
    if (
        admission.get("schemaVersion") != 1 or admission.get("kind") != ADMISSION_KIND
        or admission.get("runtimeAuthorized") is not True
        or admission.get("externalMutationAuthorized") is not True
        or admission.get("promotionAuthorized") is not False
    ):
        raise GateError("runtime admission is not affirmative and bounded")
    body = {key: value for key, value in admission.items() if key != "admissionCanonicalSha256"}
    if admission.get("admissionCanonicalSha256") != canonical_sha256(body):
        raise GateError("runtime admission self digest differs")
    binding = admission["bindings"]
    campaign_suffix = hashlib.sha256(binding["campaignId"].encode()).hexdigest()[:8]
    contracts = []
    for ordinal, cell in enumerate(_flatten_plan(), start=1):
        project = f"{binding['projectPrefix']}_{campaign_suffix}_{ordinal:02d}"
        if PROJECT.fullmatch(project) is None:
            raise GateError("derived Compose project identity is invalid")
        contract = {
            "schemaVersion": 1,
            "kind": CELL_KIND,
            "studyEpoch": STUDY_EPOCH,
            "runId": cell["runId"],
            "runKey": cell["runKey"],
            "position": cell["position"],
            "fault": cell["fault"],
            "postureRole": cell["postureRole"],
            "compiledArtifactRoot": cell["artifactRoot"],
            "runtimeArtifactRoot": f"{binding['artifactRoot']}/runs/{cell['artifactRoot']}",
            "ordinal": ordinal,
            "project": project,
            "ports": binding["ports"],
            "transportId": binding["transportId"],
            "target": binding["target"],
            "leasePath": binding["leasePath"],
            "deadline": binding["deadline"],
            "compiledPlanCanonicalSha256": binding["compiledPlanCanonicalSha256"],
            "admissionCanonicalSha256": admission["admissionCanonicalSha256"],
            "cleanupActions": binding["cleanupActions"],
            "foreignProject": binding["foreignProject"],
            "nuisanceFactors": list(NUISANCE_FACTORS),
            "absoluteCostOrLatencyCanonical": False,
            "runtimeAuthorized": True,
            "promotionAuthorized": False,
            "canonical": False,
        }
        if "timing" in cell:
            # Parameterised epochs only: the frozen epoch's contracts stay byte-identical.
            contract["timing"] = copy.deepcopy(cell["timing"])
        contracts.append(contract)
    return contracts


def frozen_cell_contracts(admission: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Compile the schedule twice and refuse anything that is not identical.

    The compiled schedule is immutable: the orchestrator may not re-randomize,
    substitute, reorder, or repair a cell.  ``cell_contracts`` recompiles the
    frozen descriptor on every call, so an independent second compilation must
    be byte-identical, must carry the plan digest the admission was gated on,
    and must present the 24 unique cells in one fixed order.
    """
    compiler = _load_compiler()
    expected_plan = getattr(compiler, "EXPECTED_PLAN_SHA256", None)
    if SHA256.fullmatch(str(expected_plan)) is None:
        raise GateError("frozen compiler does not pin a compiled plan digest")
    if admission["bindings"]["compiledPlanCanonicalSha256"] != expected_plan:
        raise GateError("admitted compiled plan digest differs from the frozen plan")
    contracts = cell_contracts(admission)
    if canonical_bytes(contracts) != canonical_bytes(cell_contracts(admission)):
        raise GateError("compiled schedule is not deterministic across compilations")
    if len(contracts) != CELL_COUNT or len({row["runId"] for row in contracts}) != CELL_COUNT:
        raise GateError(f"compiled schedule does not contain {CELL_COUNT} unique cells")
    if [row["ordinal"] for row in contracts] != list(range(1, CELL_COUNT + 1)):
        raise GateError("compiled schedule ordinals are not the fixed sequence")
    return contracts


def _assert_scheduled_cell(
    contracts: list[Mapping[str, Any]], ordinal: int, contract: Mapping[str, Any],
) -> None:
    """Refuse a cell that differs from its compiled position; never adapt."""
    if not 1 <= ordinal <= len(contracts):
        raise GateError("cell ordinal is outside the compiled schedule")
    if canonical_bytes(contracts[ordinal - 1]) != canonical_bytes(contract):
        raise GateError("dispatched cell differs from the compiled schedule cell")


def _journal_path(admission: Mapping[str, Any]) -> Path:
    artifact = Path(admission["bindings"]["artifactRoot"])
    if artifact.is_symlink() or not artifact.is_dir():
        raise GateError("campaign artifact root is unavailable for the runtime journal")
    return artifact / JOURNAL_NAME


def _journal_record(
    records: list[Mapping[str, Any]], *, campaign_id: str, contract: Mapping[str, Any],
    state: str, cell_receipt_sha256: str | None, reason: str | None,
    compiled_plan_sha256: str, admission_sha256: str,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Build one tamper-evident, hash-chained journal record for one cell.

    Every row is bound to `compiledPlanCanonicalSha256`/
    `admissionCanonicalSha256` -- a completed campaign never writes a
    controller-abort document, so without this binding nothing in the
    journal chain proves which admitted plan a *complete* campaign actually
    charged against; `replay_runtime_journal` refuses a chain whose rows
    disagree with each other or with the caller's admission.
    """
    if state not in JOURNAL_STATES:
        raise GateError("runtime journal state is not a declared terminal cell state")
    if SHA256.fullmatch(str(compiled_plan_sha256)) is None or SHA256.fullmatch(str(admission_sha256)) is None:
        raise GateError("runtime journal record needs exact plan/admission digests")
    body = {
        "schemaVersion": 1,
        "kind": JOURNAL_KIND,
        "campaignId": campaign_id,
        "compiledPlanCanonicalSha256": compiled_plan_sha256,
        "admissionCanonicalSha256": admission_sha256,
        "sequence": len(records),
        "previousRecordSha256": (
            records[-1]["recordSha256"] if records else "0" * 64
        ),
        "runId": contract["runId"],
        "runKey": copy.deepcopy(contract["runKey"]),
        "ordinal": contract["ordinal"],
        "state": state,
        "cellReceiptCanonicalSha256": cell_receipt_sha256,
        "reason": None if reason is None else str(reason)[:4096],
        "recordedAt": _now(clock).isoformat().replace("+00:00", "Z"),
        "promotionAuthorized": False,
    }
    return {**body, "recordSha256": canonical_sha256(body)}


def _append_journal(path: Path, record: Mapping[str, Any]) -> None:
    """Append one record durably; a journal that cannot be written is fatal."""
    payload = canonical_bytes(record) + b"\n"
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise GateError(f"cannot open the runtime journal: {exc}") from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise GateError("runtime journal is not a regular file")
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:  # pragma: no cover - short write on a regular file
                raise GateError("runtime journal append made no progress")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def replay_runtime_journal(
    path: Path, contracts: list[Mapping[str, Any]], *, campaign_id: str,
    compiled_plan_sha256: str, admission_sha256: str,
) -> dict[str, Any]:
    """Replay the hash chain offline and prove one unambiguous terminal state.

    Every row must agree with the caller's `compiled_plan_sha256`/
    `admission_sha256` -- not merely with each other -- so a chain that is
    internally consistent but was journalled against a different admitted
    plan is refused too.
    """
    path = Path(path)
    if CAMPAIGN_ID.fullmatch(str(campaign_id)) is None:
        raise GateError("runtime journal replay needs one exact campaign identity")
    if (
        SHA256.fullmatch(str(compiled_plan_sha256)) is None
        or SHA256.fullmatch(str(admission_sha256)) is None
    ):
        raise GateError("runtime journal replay needs the admitted plan/admission digests")
    if path.is_symlink() or not path.is_file():
        raise GateError("runtime journal is not a regular file")
    payload = path.read_bytes()
    if payload and not payload.endswith(b"\n"):
        raise GateError("runtime journal has a truncated final record")
    lines = payload.splitlines()
    if len(lines) > len(contracts):
        raise GateError("runtime journal contains more cells than the compiled plan")
    records: list[dict[str, Any]] = []
    valid_cells = 0
    stopped = False
    for index, line in enumerate(lines):
        if stopped:
            raise GateError("runtime journal contains a record after its terminal stop")
        record = strict_json(line, f"runtime journal row {index}")
        if not isinstance(record, dict) or set(record) != {
            "schemaVersion", "kind", "campaignId", "compiledPlanCanonicalSha256",
            "admissionCanonicalSha256", "sequence", "previousRecordSha256",
            "runId", "runKey", "ordinal", "state", "cellReceiptCanonicalSha256",
            "reason", "recordedAt", "promotionAuthorized", "recordSha256",
        }:
            raise GateError(f"runtime journal row {index} fields differ")
        body = {key: value for key, value in record.items() if key != "recordSha256"}
        expected_previous = records[-1]["recordSha256"] if records else "0" * 64
        contract = contracts[index]
        if (
            record["schemaVersion"] != 1
            or record["kind"] != JOURNAL_KIND
            or record["campaignId"] != campaign_id
            or record["compiledPlanCanonicalSha256"] != compiled_plan_sha256
            or record["admissionCanonicalSha256"] != admission_sha256
            or record["sequence"] != index
            or record["previousRecordSha256"] != expected_previous
            or record["recordSha256"] != canonical_sha256(body)
            or record["runId"] != contract["runId"]
            or canonical_bytes(record["runKey"]) != canonical_bytes(contract["runKey"])
            or record["ordinal"] != contract["ordinal"]
            or record["state"] not in JOURNAL_STATES
            or record["promotionAuthorized"] is not False
        ):
            raise GateError(f"runtime journal row {index} breaks the chain or the schedule")
        _timestamp(record["recordedAt"], f"runtime journal row {index} recordedAt")
        if record["state"] == "valid":
            if (
                SHA256.fullmatch(str(record["cellReceiptCanonicalSha256"])) is None
                or record["reason"] is not None
            ):
                raise GateError(f"runtime journal row {index} claims validity without a receipt")
            valid_cells += 1
        else:
            if record["cellReceiptCanonicalSha256"] is not None or not record["reason"]:
                raise GateError(f"runtime journal row {index} stops without a reason")
            stopped = True
        records.append(record)
    return {
        "schemaVersion": 1,
        "kind": "hotel-candidate-runtime-journal-replay-v1",
        "rows": len(records),
        "validCells": valid_cells,
        "terminalStop": stopped,
        "complete": not stopped and len(records) == len(contracts),
        "chainHeadSha256": records[-1]["recordSha256"] if records else "0" * 64,
    }


def _controller_abort_document(
    admission: Mapping[str, Any], *, stage: str, failure_type: str,
    failure_message: str, valid_cells: int, journal_rows: int,
    attempted_cells: int, chain_head_sha256: str,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """One terminal non-result for a campaign that stopped before every scheduled cell."""
    if stage not in CONTROLLER_ABORT_STAGES:
        raise GateError("controller abort stage is not a declared campaign stage")
    body = {
        "schemaVersion": 1,
        "kind": CONTROLLER_ABORT_KIND,
        "campaignId": admission["bindings"]["campaignId"],
        "admissionCanonicalSha256": admission["admissionCanonicalSha256"],
        "compiledPlanCanonicalSha256": admission["bindings"]["compiledPlanCanonicalSha256"],
        "scheduledCells": CELL_COUNT,
        "attemptedCells": attempted_cells,
        "journalRows": journal_rows,
        "validCells": valid_cells,
        "journalChainHeadSha256": chain_head_sha256,
        "stage": stage,
        "failureType": str(failure_type)[:256],
        "failureMessage": str(failure_message)[:4096],
        "experimentalState": "ABSTAINED",
        "retryAllowed": False,
        "candidateCampaignValid": False,
        "runtimeAuthorized": True,
        "promotionAuthorized": False,
        "terminalAt": _now(clock).isoformat().replace("+00:00", "Z"),
    }
    return {**body, "abortCanonicalSha256": canonical_sha256(body)}


def validate_controller_abort(
    value: Any, admission: Mapping[str, Any], campaign_id: str,
) -> dict[str, Any]:
    """Recognize only a complete, self-consistent, abstaining abort document."""
    expected = {
        "schemaVersion", "kind", "campaignId", "admissionCanonicalSha256",
        "compiledPlanCanonicalSha256", "scheduledCells", "attemptedCells",
        "journalRows", "validCells", "journalChainHeadSha256", "stage",
        "failureType", "failureMessage", "experimentalState", "retryAllowed",
        "candidateCampaignValid", "runtimeAuthorized", "promotionAuthorized",
        "terminalAt", "abortCanonicalSha256",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise GateError("controller abort fields differ")
    body = {key: item for key, item in value.items() if key != "abortCanonicalSha256"}
    counts = (value.get("attemptedCells"), value.get("journalRows"), value.get("validCells"))
    if (
        value.get("schemaVersion") != 1
        or value.get("kind") != CONTROLLER_ABORT_KIND
        or value.get("campaignId") != campaign_id
        or value.get("admissionCanonicalSha256") != admission.get("admissionCanonicalSha256")
        or value.get("compiledPlanCanonicalSha256")
        != admission.get("bindings", {}).get("compiledPlanCanonicalSha256")
        or value.get("abortCanonicalSha256") != canonical_sha256(body)
        or value.get("scheduledCells") != CELL_COUNT
        or any(
            not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= CELL_COUNT
            for count in counts
        )
        or value["validCells"] > value["journalRows"]
        or value["journalRows"] > value["attemptedCells"]
        or SHA256.fullmatch(str(value.get("journalChainHeadSha256"))) is None
        or value.get("stage") not in CONTROLLER_ABORT_STAGES
        or not isinstance(value.get("failureType"), str) or not value["failureType"]
        or not isinstance(value.get("failureMessage"), str)
        or value.get("experimentalState") != "ABSTAINED"
        or value.get("retryAllowed") is not False
        or value.get("candidateCampaignValid") is not False
        or value.get("runtimeAuthorized") is not True
        or value.get("promotionAuthorized") is not False
    ):
        raise GateError("controller abort identity or terminal semantics differ")
    _timestamp(value.get("terminalAt"), "controller abort terminalAt")
    return value


def _retain_controller_abort(
    admission: Mapping[str, Any], *, stage: str, failure_type: str,
    failure_message: str, valid_cells: int, journal_rows: int,
    attempted_cells: int, chain_head_sha256: str,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any] | None:
    """Write the abort document exclusively; retention must not mask an abort."""
    abort = _controller_abort_document(
        admission, stage=stage, failure_type=failure_type,
        failure_message=failure_message, valid_cells=valid_cells,
        journal_rows=journal_rows, attempted_cells=attempted_cells,
        chain_head_sha256=chain_head_sha256, clock=clock,
    )
    path = Path(admission["bindings"]["artifactRoot"]) / CONTROLLER_ABORT_NAME
    if path.exists() or path.is_symlink():
        return validate_controller_abort(
            _json_file(path, "retained controller abort"), admission,
            admission["bindings"]["campaignId"],
        )
    _write_exclusive_json(path, abort)
    return validate_controller_abort(
        _json_file(path, "retained controller abort"), admission,
        admission["bindings"]["campaignId"],
    )


def _on_sigterm(signum: int, frame: Any) -> NoReturn:
    """Convert a delivered SIGTERM into a raised `Terminated` (see its
    docstring) rather than letting the default disposition kill the process
    with no exception raised and no `finally` block run."""
    raise Terminated()


def execute_campaign(
    admission: Mapping[str, Any], transport: RuntimeTransport,
    *, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Drive the immutable compiled schedule once, journalling every cell.

    One-shot semantics: no retry, no substitution, no re-randomization.  The
    first cell that does not return a terminally valid receipt stops the
    campaign, its evidence is already quarantined by the cell producer, a
    hash-chained journal record states why, and an abstaining abort document
    is retained beside the journal.
    """
    contracts = frozen_cell_contracts(admission)
    binding = admission["bindings"]
    campaign_id = binding["campaignId"]
    compiled_plan_sha256 = binding["compiledPlanCanonicalSha256"]
    admission_sha256 = admission["admissionCanonicalSha256"]
    if transport.transport_id != binding["transportId"] or transport.target != binding["target"]:
        raise GateError("runtime transport differs from GATE-RUN")
    records = []
    journal_records: list[dict[str, Any]] = []
    lease = transport.acquire_lease(admission)
    if lease.get("acquired") is not True:
        raise GateError("exact campaign lease was not acquired")
    status = "running"
    stage = "campaign-preflight"
    abort_reason: tuple[str, str] | None = None
    cleanup: Mapping[str, Any] = {}
    release: Mapping[str, Any] = {}
    errors: list[dict[str, str]] = []
    journal: Path | None = None
    abort: dict[str, Any] | None = None

    def retain_abort(current_stage: str) -> None:
        nonlocal abort
        try:
            abort = _retain_controller_abort(
                admission, stage=current_stage,
                failure_type=abort_reason[0] if abort_reason else "UnknownFailure",
                failure_message=abort_reason[1] if abort_reason else status,
                valid_cells=sum(1 for row in journal_records if row["state"] == "valid"),
                journal_rows=len(journal_records),
                attempted_cells=len(records),
                chain_head_sha256=(
                    journal_records[-1]["recordSha256"] if journal_records else "0" * 64
                ),
                clock=clock,
            )
        except Exception as exc:  # noqa: BLE001 - retention never masks the abort
            errors.append({
                "phase": "abort-retention", "type": type(exc).__name__,
                "message": str(exc)[:4096],
            })

    # A delivered SIGTERM must not simply kill the process with no stop
    # record: the handler converts it into a raised `Terminated`
    # (BaseException, not Exception -- see that class's docstring), which
    # the outer `except BaseException` below retains an abort for before
    # re-raising so the process still dies, but only after a terminal state
    # exists.  The previous disposition is always restored on the way out.
    previous_sigterm_handler = signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        try:
            try:
                if transport.preflight(admission).get("passed") is not True:
                    raise GateError("runtime preflight failed")
                stage = "campaign-preparation"
                if transport.prepare_campaign(admission).get("prepared") is not True:
                    raise GateError("candidate campaign preparation failed")
                journal = _journal_path(admission)
                if journal.exists() or journal.is_symlink():
                    raise GateError("runtime journal already exists for this one-shot campaign")
                stage = "cell-execution"
                for ordinal, contract in enumerate(contracts, start=1):
                    remaining = (
                        _timestamp(binding["deadline"], "deadline") - _now(clock)
                    ).total_seconds()
                    if remaining <= 300:
                        status = "stopped-deadline"
                        abort_reason = (
                            "DeadlineReserve",
                            "runtime deadline reached the owned-cleanup reserve before this cell",
                        )
                        break
                    # The compiled schedule is immutable; a drifted cell raises here
                    # rather than being adapted, substituted, or reordered.
                    _assert_scheduled_cell(contracts, ordinal, contract)
                    recorder = getattr(transport, "record_attempt_start", None)
                    if recorder is None:
                        raise GateError(
                            "runtime transport cannot durably charge an attempt before dispatch"
                        )
                    attempt = dict(recorder(admission, contract))
                    record: dict[str, Any] = {
                        "runId": contract["runId"], "attemptStart": attempt,
                        "receipt": None,
                    }
                    records.append(record)
                    try:
                        receipt = dict(transport.run_cell(admission, contract))
                    except Exception as exc:
                        # Charge the failed cell to the chain before propagating, so the
                        # journal alone identifies which cell stopped the campaign.
                        journal_record = _journal_record(
                            journal_records, campaign_id=campaign_id, contract=contract,
                            state="stopped", cell_receipt_sha256=None,
                            reason=f"{type(exc).__name__}: {exc}",
                            compiled_plan_sha256=compiled_plan_sha256,
                            admission_sha256=admission_sha256,
                            clock=clock,
                        )
                        _append_journal(journal, journal_record)
                        journal_records.append(journal_record)
                        raise
                    record["receipt"] = receipt
                    if receipt.get("candidateCellValid") is not True:
                        reason = (
                            "cell receipt is not terminally valid: "
                            f"candidateCellValid={receipt.get('candidateCellValid')!r}"
                        )
                        journal_record = _journal_record(
                            journal_records, campaign_id=campaign_id, contract=contract,
                            state="stopped", cell_receipt_sha256=None, reason=reason,
                            compiled_plan_sha256=compiled_plan_sha256,
                            admission_sha256=admission_sha256,
                            clock=clock,
                        )
                        _append_journal(journal, journal_record)
                        journal_records.append(journal_record)
                        status = "stopped-invalid-cell"
                        abort_reason = ("InvalidCell", reason)
                        break
                    # Strict equality, no `None` carve-out: a receipt with no runId
                    # at all must not silently pass as "the scheduled cell."
                    if receipt.get("runId") != contract["runId"]:
                        raise GateError("cell receipt identifies a different scheduled cell")
                    journal_record = _journal_record(
                        journal_records, campaign_id=campaign_id, contract=contract,
                        state="valid", cell_receipt_sha256=canonical_sha256(receipt),
                        reason=None,
                        compiled_plan_sha256=compiled_plan_sha256,
                        admission_sha256=admission_sha256,
                        clock=clock,
                    )
                    _append_journal(journal, journal_record)
                    journal_records.append(journal_record)
            except Exception as exc:
                status = "runtime-error"
                abort_reason = (type(exc).__name__, str(exc)[:4096])
                errors.append(
                    {"phase": "runtime", "type": type(exc).__name__, "message": str(exc)[:4096]}
                )
            finally:
                if status != "running":
                    # Abstain durably BEFORE cleanup, which can itself fail or hang: a
                    # terminal non-result must never depend on cleanup succeeding.
                    retain_abort(stage)
                try:
                    cleanup = transport.cleanup(admission)
                except Exception as exc:
                    cleanup = {"ownedResourcesRemaining": "unknown", "cleanupRaised": True}
                    errors.append(
                        {"phase": "cleanup", "type": type(exc).__name__, "message": str(exc)[:4096]}
                    )
                finally:
                    try:
                        release = transport.release_lease(admission)
                    except Exception as exc:
                        release = {"released": False, "releaseRaised": True}
                        errors.append({
                            "phase": "release", "type": type(exc).__name__,
                            "message": str(exc)[:4096],
                        })
                if (
                    cleanup.get("ownedResourcesRemaining") not in ([], {})
                    or release.get("released") is not True
                    or any(row["phase"] in {"cleanup", "release"} for row in errors)
                ):
                    if status in {"running", "complete"}:
                        stage = (
                            "lease-release"
                            if any(row["phase"] == "release" for row in errors)
                            else "campaign-cleanup"
                        )
                        abort_reason = (
                            "CleanupFailed", "owned cleanup or lease release did not settle",
                        )
                    status = "cleanup-failed"
            if status == "running":
                stage = "terminal-validation"
                try:
                    campaign = transport.validate_campaign(admission)
                except Exception as exc:
                    status = "stopped-invalid-campaign"
                    abort_reason = (type(exc).__name__, str(exc)[:4096])
                    errors.append({
                        "phase": "campaign-validation", "type": type(exc).__name__,
                        "message": str(exc)[:4096],
                    })
                else:
                    if campaign.get("candidateCampaignValid") is True:
                        status = "complete"
                    else:
                        status = "stopped-invalid-campaign"
                        abort_reason = (
                            "InvalidCampaign",
                            "terminal campaign replay did not return candidateCampaignValid",
                        )
            journal_replay: dict[str, Any] | None = None
            if journal is not None:
                try:
                    journal_replay = replay_runtime_journal(
                        journal, contracts, campaign_id=campaign_id,
                        compiled_plan_sha256=compiled_plan_sha256, admission_sha256=admission_sha256,
                    )
                except Exception as exc:
                    errors.append({
                        "phase": "journal-replay", "type": type(exc).__name__,
                        "message": str(exc)[:4096],
                    })
            if status != "complete" and abort is None:
                # A campaign that only became non-terminal during cleanup or terminal
                # validation abstains here instead.  Retention is idempotent, so an
                # abort already written before cleanup is never restated or replaced.
                retain_abort(stage)
            return {
                "schemaVersion": 1,
                "kind": "hotel-candidate-execution-receipt-v1",
                "status": status,
                "scheduledCells": CELL_COUNT,
                "attemptedCells": len(records),
                "records": records,
                "journal": journal_replay,
                "campaignAbort": abort,
                "cleanup": dict(cleanup),
                "leaseRelease": dict(release),
                "errors": errors,
                "runtimeAuthorized": True,
                "promotionAuthorized": False,
            }
        except BaseException:
            # Reached only by a BaseException that is not an Exception (e.g.
            # `Terminated` from a delivered SIGTERM, or `KeyboardInterrupt`):
            # `except Exception` above never sees these, and without this
            # handler they would propagate with `status` still "running" and
            # no abort ever retained.
            if status == "running":
                status = "interrupted"
            retain_abort(stage)
            raise
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm_handler)


class CommandComposeTransport:
    """Fixed root SSH transport that executes every runner action as fhuebscher."""

    def __init__(self, transport_id: str, target: str, checkout_root: str):
        if (
            transport_id != "ssh-compose" or target != TARGET["target"]
            or checkout_root != TARGET["checkoutRoot"]
        ):
            raise GateError("SSH transport differs from the frozen target or checkout")
        self.transport_id = transport_id
        self.target = target
        self.checkout_root = checkout_root

    def record_attempt_start(self, admission, contract):
        return self._invoke("record-attempt-start", admission, contract)

    def _base(self) -> list[str]:
        runner = f"{self.checkout_root.rstrip('/')}/modules/hotel-reservation/execution/candidate_cell.py"
        if self.target != TARGET["target"] or self.checkout_root != TARGET["checkoutRoot"]:
            raise GateError("SSH transport differs from the frozen host or checkout")
        return [
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "--",
            "root@fb14srv4",
            resolve_target_binary_over_ssh("runuser"), "--user", "fhuebscher", "--",
            resolve_target_binary_over_ssh("python3"), "-I", runner,
        ]

    def _invoke(self, action: str, admission: Mapping[str, Any], contract: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if action not in {"acquire-lease", "preflight", "prepare-campaign", "run-cell", "validate-campaign", "cleanup", "release-lease"}:
            raise GateError("remote runner action is not allowlisted")
        binding = admission["bindings"]
        command = [
            *self._base(), action, "--campaign-id", binding["campaignId"],
            "--artifact-root", binding["artifactRoot"],
            "--admission-sha256", admission["admissionCanonicalSha256"],
        ]
        if contract is not None:
            command.extend(("--run-id", contract["runId"], "--contract-sha256", canonical_sha256(contract)))
        envelope = {"admission": admission, "contract": contract}
        deadline = _timestamp(binding["deadline"], "runtime deadline")
        if action in {"cleanup", "release-lease"}:
            # Cleanup remains callable after a missed deadline; a deadline must
            # never become a reason to strand an admitted owned resource.
            available = 300.0
        else:
            available = (
                deadline - datetime.now(timezone.utc)
            ).total_seconds() - 300
            if available <= 0:
                raise GateError(f"candidate runner action has no deadline budget: {action}")
        try:
            result = subprocess.run(
                command, input=json.dumps(envelope, sort_keys=True, separators=(",", ":")),
                text=True, capture_output=True, check=False, timeout=min(18100, available),
                cwd=None,
            )
        except subprocess.TimeoutExpired as exc:
            raise GateError(f"candidate runner action timed out: {action}") from exc
        except OSError as exc:
            raise GateError(f"candidate runner action could not start: {action}") from exc
        if result.returncode:
            # Do not reflect an unbounded or attacker-controlled remote log into
            # a gate error.  The cell runner owns durable diagnostics.
            detail = result.stderr.strip()[:4096]
            raise GateError(f"candidate runner action failed: {action}: {detail}")
        if len(result.stdout.encode("utf-8")) > 1024 * 1024:
            raise GateError(f"candidate runner action returned oversized JSON: {action}")
        value = strict_json(result.stdout, f"candidate runner {action}")
        if not isinstance(value, dict):
            raise GateError(f"candidate runner {action} did not return an object")
        return value

    def acquire_lease(self, admission): return self._invoke("acquire-lease", admission)
    def preflight(self, admission): return self._invoke("preflight", admission)
    def prepare_campaign(self, admission): return self._invoke("prepare-campaign", admission)
    def run_cell(self, admission, contract): return self._invoke("run-cell", admission, contract)
    def validate_campaign(self, admission): return self._invoke("validate-campaign", admission)
    def cleanup(self, admission): return self._invoke("cleanup", admission)
    def release_lease(self, admission): return self._invoke("release-lease", admission)


class TargetComposeTransport(CommandComposeTransport):
    """The detached srv4 controller's target-local fixed-argv transport."""

    def __init__(self, admission: Mapping[str, Any], lease_fd: int):
        binding = admission["bindings"]
        super().__init__(binding["transportId"], binding["target"], binding["checkoutRoot"])
        groups = os.getgroups()
        if os.getuid() != 1007 or os.getgid() != 1007 or not {27, 998}.issubset(groups):
            raise GateError("target controller is not fhuebscher 1007/1007 with supplemental gids 27,998")
        if not isinstance(lease_fd, int) or lease_fd < 3:
            raise GateError("target controller did not receive an explicit inherited lease descriptor")
        lease_path = Path(binding["leasePath"])
        try:
            path_state = lease_path.lstat()
            descriptor_state = os.fstat(lease_fd)
        except OSError as exc:
            raise GateError("target controller cannot inspect the inherited lease descriptor") from exc
        if (
            lease_path.is_symlink()
            or not stat.S_ISREG(path_state.st_mode)
            or not stat.S_ISREG(descriptor_state.st_mode)
            or (path_state.st_dev, path_state.st_ino)
            != (descriptor_state.st_dev, descriptor_state.st_ino)
        ):
            raise GateError("inherited lease descriptor does not identify the exact lease file")
        owner = _json_file(lease_path, "root-held flock lease")
        if (
            owner.get("campaignId") != binding["campaignId"]
            or owner.get("admissionCanonicalSha256") != admission["admissionCanonicalSha256"]
        ):
            raise GateError("root-held flock lease identity differs")
        self._lease_fd: int | None = lease_fd
        self._cleanup_receipt: dict[str, Any] | None = None

    def _base(self) -> list[str]:
        runner = self.checkout_root.rstrip("/") + "/modules/hotel-reservation/execution/candidate_cell.py"
        return [target_python(), "-I", runner]

    def acquire_lease(self, admission: Mapping[str, Any]) -> Mapping[str, Any]:
        lease_path = Path(admission["bindings"]["leasePath"])
        owner = _json_file(lease_path, "root-held flock lease")
        if (
            owner.get("campaignId") != admission["bindings"]["campaignId"]
            or owner.get("admissionCanonicalSha256") != admission["admissionCanonicalSha256"]
        ):
            raise GateError("root-held flock lease identity differs")
        descriptor = os.open(lease_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                raise GateError("root transport did not retain the campaign flock")
        finally:
            os.close(descriptor)
        return {"acquired": True, "owner": "root-transport-flock"}

    def record_attempt_start(
        self, admission: Mapping[str, Any], contract: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        artifact = Path(admission["bindings"]["artifactRoot"])
        if artifact.is_symlink() or not artifact.is_dir():
            raise GateError("campaign artifact root is unavailable for attempt charging")
        path = artifact / "attempt-starts.jsonl"
        previous = "0" * 64
        ordinal = 1
        if path.exists():
            rows = path.read_bytes().splitlines()
            if rows:
                prior = strict_json(rows[-1].decode("utf-8"), "prior attempt-start row")
                previous = prior["recordSha256"]
                ordinal = int(prior["attemptOrdinal"]) + 1
        body = {
            "schemaVersion": 1, "kind": "hotel-candidate-attempt-start-v1",
            "campaignId": admission["bindings"]["campaignId"],
            "runId": contract["runId"], "attemptOrdinal": ordinal,
            "previousRecordSha256": previous,
            "admissionCanonicalSha256": admission["admissionCanonicalSha256"],
            "startedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        row = {**body, "recordSha256": canonical_sha256(body)}
        descriptor = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            payload = canonical_bytes(row) + b"\n"
            if os.write(descriptor, payload) != len(payload):
                raise GateError("short write to durable attempt-start ledger")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return row

    def cleanup(self, admission: Mapping[str, Any]) -> Mapping[str, Any]:
        result = dict(super().cleanup(admission))
        self._cleanup_receipt = result
        return result

    def release_lease(self, admission: Mapping[str, Any]) -> Mapping[str, Any]:
        binding = admission["bindings"]
        descriptor = self._lease_fd
        if descriptor is None:
            raise GateError("inherited campaign flock was already released")
        projects = [row["project"] for row in cell_contracts(admission)]
        observed_cleanup: Any = self._cleanup_receipt
        if (
            isinstance(observed_cleanup, dict)
            and observed_cleanup.get("projectsChecked") == projects
            and isinstance(observed_cleanup.get("ownedResourcesRemaining"), list)
        ):
            remaining: Any = observed_cleanup["ownedResourcesRemaining"]
        else:
            remaining = [{"cleanupReceipt": "missing-or-invalid"}]
        artifact = Path(binding["artifactRoot"])
        if artifact.is_symlink() or not artifact.is_dir():
            raise GateError("campaign artifact root is unavailable at lease release")
        # Close only the child's duplicate. The root supervisor retains the
        # same open-file description and unlocks after its terminal tree seal.
        os.close(descriptor)
        self._lease_fd = None
        cleanup_document = {
            "schemaVersion": 1,
            "kind": "hotel-candidate-campaign-cleanup-v1",
            "ownedProjects": projects,
            "ownedResourcesRemaining": (
                {"containers": [], "networks": [], "volumes": []}
                if remaining == [] else remaining
            ),
            "foreignResourcesMutated": False,
            "leaseReleased": False,
            "artifactDeletionAttempted": False,
        }
        _write_exclusive_json(artifact / "campaign-cleanup.json", cleanup_document)
        retained = _json_file(
            artifact / "campaign-cleanup.json", "retained campaign cleanup",
        )
        if canonical_bytes(retained) != canonical_bytes(cleanup_document):
            raise GateError("retained campaign cleanup differs from explicit lease release")
        return {
            "released": True,
            "releaseMechanism": "root-supervisor-release-after-terminal-seal",
            "leasePath": binding["leasePath"],
            "persistentLeaseFileRetained": True,
            "ownedResourcesRemainingAtRelease": remaining,
        }


def _terminal_execution_receipt(
    path: Path, admission: Mapping[str, Any], campaign_id: str,
) -> bool:
    """Recognize only a complete, retained execution-state envelope.

    A non-complete campaign is only terminal once its embedded abort document
    is itself genuine: `validate_controller_abort` recomputes
    `abortCanonicalSha256` and checks `campaignId` /
    `admissionCanonicalSha256` against `admission`, rather than trusting the
    ad hoc shape checks this function used to run on `abort` directly (which
    never recomputed the digest and never checked identity against
    `campaign_id`/`admission` at all).
    """
    try:
        value = _json_file(path, "target execution receipt")
    except GateError:
        return False
    abort = value.get("campaignAbort")
    if value.get("status") == "complete":
        if abort is not None:
            return False
    else:
        if not isinstance(abort, dict):
            return False
        try:
            validate_controller_abort(abort, admission, campaign_id)
        except GateError:
            return False
    return (
        value.get("schemaVersion") == 1
        and value.get("kind") == "hotel-candidate-execution-receipt-v1"
        and value.get("status") in {
            "complete", "stopped-invalid-campaign", "stopped-invalid-cell",
            "stopped-deadline", "runtime-error", "cleanup-failed",
        }
        and value.get("scheduledCells") == CELL_COUNT
        and isinstance(value.get("attemptedCells"), int)
        and not isinstance(value.get("attemptedCells"), bool)
        and 0 <= value["attemptedCells"] <= CELL_COUNT
        and value.get("runtimeAuthorized") is True
        and value.get("promotionAuthorized") is False
    )


def _campaign_abort_document(
    admission: Mapping[str, Any], *, failure_type: str, failure_message: str,
    child_return_code: int | None, execution_receipt_present: bool,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    body = {
        "schemaVersion": 1,
        "kind": ABORT_KIND,
        "campaignId": admission["bindings"]["campaignId"],
        "admissionCanonicalSha256": admission["admissionCanonicalSha256"],
        "terminalAt": _now(clock).isoformat().replace("+00:00", "Z"),
        "phase": "target-controller-supervisor",
        "failureType": str(failure_type)[:256],
        "failureMessage": str(failure_message)[:4096],
        "childReturnCode": child_return_code,
        "executionReceiptPresent": execution_receipt_present,
        "executionReceiptValid": False,
        "attemptedCells": None,
        "ownedCleanupState": "unknown-requires-next-preflight-or-operator-review",
        "leaseReleaseStatus": "supervisor-finally-attempted-after-abort-retention",
        "candidateCampaignValid": False,
        "runtimeAuthorized": True,
        "promotionAuthorized": False,
    }
    return {**body, "abortCanonicalSha256": canonical_sha256(body)}


def validate_campaign_abort(
    value: Any, admission: Mapping[str, Any], campaign_id: str,
) -> dict[str, Any]:
    expected = {
        "schemaVersion", "kind", "campaignId", "admissionCanonicalSha256",
        "terminalAt", "phase", "failureType", "failureMessage",
        "childReturnCode", "executionReceiptPresent", "executionReceiptValid",
        "attemptedCells", "ownedCleanupState", "leaseReleaseStatus",
        "candidateCampaignValid", "runtimeAuthorized", "promotionAuthorized",
        "abortCanonicalSha256",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise GateError("campaign abort fields differ")
    body = {key: item for key, item in value.items() if key != "abortCanonicalSha256"}
    return_code = value.get("childReturnCode")
    if (
        value.get("schemaVersion") != 1
        or value.get("kind") != ABORT_KIND
        or value.get("campaignId") != campaign_id
        or value.get("admissionCanonicalSha256") != admission.get("admissionCanonicalSha256")
        or value.get("abortCanonicalSha256") != canonical_sha256(body)
        or value.get("phase") != "target-controller-supervisor"
        or not isinstance(value.get("failureType"), str)
        or not value["failureType"] or len(value["failureType"]) > 256
        or not isinstance(value.get("failureMessage"), str)
        or len(value["failureMessage"]) > 4096
        or (return_code is not None and (
            not isinstance(return_code, int) or isinstance(return_code, bool)
        ))
        or not isinstance(value.get("executionReceiptPresent"), bool)
        or value.get("executionReceiptValid") is not False
        or value.get("attemptedCells") is not None
        or value.get("ownedCleanupState") != "unknown-requires-next-preflight-or-operator-review"
        or value.get("leaseReleaseStatus") != "supervisor-finally-attempted-after-abort-retention"
        or value.get("candidateCampaignValid") is not False
        or value.get("runtimeAuthorized") is not True
        or value.get("promotionAuthorized") is not False
    ):
        raise GateError("campaign abort identity or terminal semantics differ")
    _timestamp(value.get("terminalAt"), "campaign abort terminalAt")
    return value


def validate_supervisor_start_window(
    admission: Mapping[str, Any], *,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> datetime:
    """Consume freshness and full remaining budget at the child-start seam."""
    binding = admission.get("bindings")
    if not isinstance(binding, dict):
        raise GateError("target supervisor admission bindings are missing")
    now = _now(clock)
    issued = _timestamp(admission.get("issuedAt"), "target supervisor admission issuedAt")
    readiness = _timestamp(
        binding.get("readinessObservedAt"), "target supervisor readinessObservedAt",
    )
    deadline = _timestamp(binding.get("deadline"), "target supervisor deadline")
    for label, observed in (("admission", issued), ("readiness", readiness)):
        age = (now - observed).total_seconds()
        if age < -5 or age > 900:
            raise GateError(f"target supervisor {label} is stale or future-dated")
    remaining = (deadline - now).total_seconds()
    if (
        issued < readiness or remaining < MINIMUM_FIRST_MUTATION_REMAINING_SECONDS
        or remaining > MAXIMUM_WALL_SECONDS + 5
    ):
        raise GateError("target supervisor lacks fresh readiness or the full runtime budget")
    return deadline


def _root_terminal_observation_and_seal(
    admission: Mapping[str, Any], control: Path,
    *, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Root-observe every fixed owned identity and seal the retained tree."""
    projects = [row["project"] for row in cell_contracts(admission)]
    def listed(kind: str, project: str) -> list[str]:
        command = (
            ["docker", "ps", "-a", "-q", "--filter", f"label=com.docker.compose.project={project}"]
            if kind == "ps" else
            ["docker", kind, "ls", "-q", "--filter", f"label=com.docker.compose.project={project}"]
        )
        result = subprocess.run(command, text=True, capture_output=True, check=False, timeout=30)
        if result.returncode:
            raise GateError(f"root terminal observation cannot list {kind} for {project}")
        return sorted(value for value in result.stdout.splitlines() if value)
    remaining: dict[str, dict[str, list[str]]] = {}
    failures = []
    for project in projects:
        row: dict[str, list[str]] = {}
        for resource, command_kind in (
            ("containers", "ps"), ("networks", "network"), ("volumes", "volume"),
        ):
            try:
                row[resource] = listed(command_kind, project)
            except Exception as exc:
                failures.append({
                    "project": project, "resource": resource,
                    "type": type(exc).__name__, "message": str(exc)[:4096],
                })
        if len(row) == 3:
            remaining[project] = row
    observation = {
        "schemaVersion": 1, "kind": "hotel-srv4-root-terminal-observation-v1",
        "campaignId": admission["bindings"]["campaignId"],
        "observedAt": _now(clock).isoformat().replace("+00:00", "Z"),
        "projectsChecked": projects,
        "state": "observed" if not failures else "unknown",
        "ownedResourcesRemaining": remaining if not failures else None,
        "failures": failures,
        "foreignProjectMutated": False,
    }
    _write_exclusive_json(control / "root-cleanup-observation.json", observation, uid=0, gid=0)
    _validate_root_cleanup_observation(observation, admission)
    artifact = Path(admission["bindings"]["artifactRoot"])
    entries = []
    for tree, label in ((artifact, "artifact"), (control, "control")):
        if tree.exists() and not tree.is_symlink():
            for path in sorted(value for value in tree.rglob("*") if value.is_file() and not value.is_symlink()):
                if path.name == "terminal-tree-seal.json":
                    continue
                entries.append({
                    "tree": label, "path": path.relative_to(tree).as_posix(),
                    "size": path.stat().st_size, "sha256": _sha256(path),
                })
    seal_body = {
        "schemaVersion": 1, "kind": "hotel-srv4-terminal-tree-seal-v1",
        "campaignId": admission["bindings"]["campaignId"],
        "sealedAt": _now(clock).isoformat().replace("+00:00", "Z"),
        "entries": entries, "entriesCanonicalSha256": canonical_sha256(entries),
        "rootObservationSha256": canonical_sha256(observation),
        "ownedResourcesState": observation["state"],
        "ownedResourcesRemaining": observation["ownedResourcesRemaining"],
    }
    seal = {**seal_body, "sealCanonicalSha256": canonical_sha256(seal_body)}
    _write_exclusive_json(control / "terminal-tree-seal.json", seal, uid=0, gid=0)
    return seal


def _validate_root_cleanup_observation(
    value: Any, admission: Mapping[str, Any],
) -> dict[str, Any]:
    expected_projects = [row["project"] for row in cell_contracts(admission)]
    required = {
        "schemaVersion", "kind", "campaignId", "observedAt", "projectsChecked",
        "state", "ownedResourcesRemaining", "failures", "foreignProjectMutated",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise GateError("root cleanup observation fields differ")
    state = value.get("state")
    remaining = value.get("ownedResourcesRemaining")
    failures = value.get("failures")
    if (
        value.get("schemaVersion") != 1
        or value.get("kind") != "hotel-srv4-root-terminal-observation-v1"
        or value.get("campaignId") != admission["bindings"]["campaignId"]
        or value.get("projectsChecked") != expected_projects
        or state not in {"observed", "unknown"}
        or value.get("foreignProjectMutated") is not False
        or not isinstance(failures, list)
        or (state == "observed" and failures != [])
        or (state == "unknown" and not failures)
        or (state == "unknown" and remaining is not None)
    ):
        raise GateError("root cleanup observation identity or state differs")
    if state == "observed":
        if not isinstance(remaining, dict) or list(remaining) != expected_projects:
            raise GateError("root cleanup observation project population differs")
        for project, resources in remaining.items():
            if not isinstance(resources, dict) or set(resources) != {
                "containers", "networks", "volumes",
            }:
                raise GateError("root cleanup observation resource shape differs")
            for rows in resources.values():
                if (
                    not isinstance(rows, list)
                    or any(not isinstance(item, str) or not item for item in rows)
                    or rows != sorted(set(rows))
                ):
                    raise GateError("root cleanup observation resource identities differ")
    else:
        for failure in failures:
            if (
                not isinstance(failure, dict)
                or set(failure) != {"project", "resource", "type", "message"}
                or failure.get("project") not in expected_projects
                or failure.get("resource") not in {"containers", "networks", "volumes"}
                or not isinstance(failure.get("type"), str) or not failure["type"]
                or not isinstance(failure.get("message"), str)
            ):
                raise GateError("root cleanup observation failure shape differs")
    _timestamp(value.get("observedAt"), "root cleanup observedAt")
    return value


def validate_terminal_tree_seal(
    control: Path, artifact: Path, admission: Mapping[str, Any],
) -> dict[str, Any]:
    seal = _json_file(control / "terminal-tree-seal.json", "terminal tree seal")
    if not isinstance(seal, dict) or set(seal) != {
        "schemaVersion", "kind", "campaignId", "sealedAt", "entries",
        "entriesCanonicalSha256", "rootObservationSha256", "ownedResourcesState",
        "ownedResourcesRemaining", "sealCanonicalSha256",
    }:
        raise GateError("terminal tree seal fields differ")
    entries = []
    for tree, label in ((artifact, "artifact"), (control, "control")):
        if tree.exists() and not tree.is_symlink():
            for path in sorted(value for value in tree.rglob("*") if value.is_file() and not value.is_symlink()):
                if path.name == "terminal-tree-seal.json":
                    continue
                entries.append({
                    "tree": label, "path": path.relative_to(tree).as_posix(),
                    "size": path.stat().st_size, "sha256": _sha256(path),
                })
    body = {key: value for key, value in seal.items() if key != "sealCanonicalSha256"}
    observation = _validate_root_cleanup_observation(
        _json_file(control / "root-cleanup-observation.json", "root cleanup observation"),
        admission,
    )
    if (
        seal.get("schemaVersion") != 1
        or seal.get("kind") != "hotel-srv4-terminal-tree-seal-v1"
        or seal.get("campaignId") != admission["bindings"]["campaignId"]
        or seal.get("entries") != entries
        or seal.get("entriesCanonicalSha256") != canonical_sha256(entries)
        or seal.get("rootObservationSha256") != canonical_sha256(observation)
        or seal.get("ownedResourcesState") != observation["state"]
        or seal.get("ownedResourcesRemaining") != observation["ownedResourcesRemaining"]
        or seal.get("sealCanonicalSha256") != canonical_sha256(body)
    ):
        raise GateError("terminal tree seal differs from retained bytes")
    _timestamp(seal.get("sealedAt"), "terminal tree sealedAt")
    return seal


def supervise_target_controller(
    admission_path: Path, execution_receipt: Path, campaign_abort: Path,
    lease_fd: int, *, popen_factory: Callable[..., Any] = subprocess.Popen,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Retain a terminal abort if the detached unprivileged child exits early."""
    admission = _json_file(admission_path, "supervised target runtime admission")
    body = {key: value for key, value in admission.items() if key != "admissionCanonicalSha256"}
    binding = admission.get("bindings")
    if (
        os.geteuid() != 0
        or not isinstance(binding, dict)
        or admission.get("admissionCanonicalSha256") != canonical_sha256(body)
        or admission.get("runtimeAuthorized") is not True
        or admission.get("externalMutationAuthorized") is not True
        or admission.get("promotionAuthorized") is not False
        or binding.get("target") != TARGET["target"]
        or binding.get("checkoutRoot") != TARGET["checkoutRoot"]
        or binding.get("controlRoot") != TARGET["controlRoot"]
        or binding.get("leasePath") != TARGET["leasePath"]
        or CAMPAIGN_ID.fullmatch(str(binding.get("campaignId"))) is None
    ):
        raise GateError("target supervisor admission or execution identity differs")
    deadline = validate_supervisor_start_window(admission, clock=clock)
    control = Path(binding["controlRoot"]) / binding["campaignId"]
    if (
        admission_path != control / "runtime-admission.json"
        or execution_receipt != control / "execution-receipt.json"
        or campaign_abort != control / "campaign-abort.json"
        or execution_receipt.exists() or execution_receipt.is_symlink()
        or campaign_abort.exists() or campaign_abort.is_symlink()
    ):
        raise GateError("target supervisor control paths differ or are already terminal")
    lease_path = Path(binding["leasePath"])
    try:
        path_state = lease_path.lstat()
        descriptor_state = os.fstat(lease_fd)
    except OSError as exc:
        raise GateError("target supervisor cannot inspect the inherited lease") from exc
    if (
        lease_fd < 3 or lease_path.is_symlink()
        or not stat.S_ISREG(path_state.st_mode)
        or not stat.S_ISREG(descriptor_state.st_mode)
        or (path_state.st_dev, path_state.st_ino)
        != (descriptor_state.st_dev, descriptor_state.st_ino)
    ):
        raise GateError("target supervisor inherited lease identity differs")
    owner = _json_file(lease_path, "target supervisor lease owner")
    if (
        owner.get("campaignId") != binding["campaignId"]
        or owner.get("admissionCanonicalSha256") != admission["admissionCanonicalSha256"]
    ):
        raise GateError("target supervisor lease owner differs")

    child_receipt = Path(binding["artifactRoot"] + ".controller-result.json")
    if child_receipt.exists() or child_receipt.is_symlink():
        raise GateError("target child result path already exists")
    # The control directory is root-only by design (readiness seam
    # campaign-path-ownership: controlRoot is not traversable by fhuebscher), so
    # the unprivileged child cannot read control/<campaign>/runtime-admission.json
    # (first real launch, 2026-09-06: 'cannot read target runtime admission:
    # Permission denied'). It gets a byte-identical, execution-user-owned copy
    # beside its receipt path; the child re-verifies the canonical digest.
    child_admission = Path(binding["artifactRoot"] + ".runtime-admission.json")
    if child_admission.exists() or child_admission.is_symlink():
        raise GateError("target child admission path already exists")
    _write_exclusive_json(child_admission, admission, uid=1007, gid=1007)
    command = [
        target_runuser(), "--user", "fhuebscher", "--", target_python(), "-I",
        TARGET["checkoutRoot"] + "/modules/hotel-reservation/execution/candidate_runtime.py",
        "--resume-admission", str(child_admission),
        "--execution-receipt", str(child_receipt),
        "--lease-fd", str(lease_fd),
    ]
    process: Any | None = None
    return_code: int | None = None
    failure_type = "MissingExecutionReceipt"
    failure_message = "target controller exited without a valid terminal execution receipt"
    try:
        process = popen_factory(
            command, stdin=subprocess.DEVNULL, stdout=None, stderr=None,
            cwd=TARGET["checkoutRoot"], start_new_session=False,
            close_fds=True, pass_fds=(lease_fd,),
        )
        timeout = max(
            1.0,
            (deadline - _now(clock)).total_seconds() + 5.0,
        )
        try:
            return_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            failure_type = "ControllerTimeout"
            failure_message = "target controller exceeded its admitted deadline and clock-skew allowance"
            try:
                process.terminate()
                process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            return_code = process.poll()
        if return_code not in (None, 0) and failure_type != "ControllerTimeout":
            failure_type = "ControllerExit"
            failure_message = f"target controller exited with status {return_code}"
    except Exception as exc:
        failure_type = type(exc).__name__
        failure_message = str(exc)
    try:
        valid_receipt = _terminal_execution_receipt(
            child_receipt, admission, binding["campaignId"],
        ) if child_receipt.exists() and not child_receipt.is_symlink() else False
        if not valid_receipt:
            abort = _campaign_abort_document(
                admission, failure_type=failure_type,
                failure_message=(
                    failure_message if return_code in (None, 0)
                    else f"target controller exited with status {return_code} before a valid receipt"
                ),
                child_return_code=return_code,
                execution_receipt_present=child_receipt.exists(), clock=clock,
            )
            _write_exclusive_json(
                campaign_abort, abort,
                uid=0, gid=0,
            )
            validate_campaign_abort(
                _json_file(campaign_abort, "retained campaign abort"),
                admission, binding["campaignId"],
            )
            terminal_artifact = "campaign-abort.json"
        else:
            retained = _json_file(child_receipt, "unprivileged child execution result")
            _write_exclusive_json(execution_receipt, retained, uid=0, gid=0)
            child_receipt.unlink()
            terminal_artifact = "execution-receipt.json"
    finally:
        try:
            _root_terminal_observation_and_seal(admission, control, clock=clock)
        finally:
            try:
                fcntl.flock(lease_fd, fcntl.LOCK_UN)
            finally:
                os.close(lease_fd)
    return {
        "schemaVersion": 1,
        "kind": "hotel-srv4-target-supervisor-terminal-v1",
        "campaignId": binding["campaignId"],
        "childReturnCode": return_code,
        "completionArtifact": terminal_artifact,
        "leaseReleaseAttempted": True,
        "promotionAuthorized": False,
    }


def retain_supervisor_boot_abort(
    admission_path: Path, execution_receipt: Path, campaign_abort: Path,
    failure: BaseException,
    *, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any] | None:
    """Best-effort terminalization for a supervisor failure before child wait."""
    admission = _json_file(admission_path, "failed supervisor runtime admission")
    binding = admission.get("bindings")
    if not isinstance(binding, dict) or CAMPAIGN_ID.fullmatch(str(binding.get("campaignId"))) is None:
        raise GateError("failed supervisor admission cannot identify its campaign")
    control = Path(binding.get("controlRoot", "")) / binding["campaignId"]
    if (
        admission_path != control / "runtime-admission.json"
        or execution_receipt != control / "execution-receipt.json"
        or campaign_abort != control / "campaign-abort.json"
    ):
        raise GateError("failed supervisor control paths differ")
    if _terminal_execution_receipt(execution_receipt, admission, binding["campaignId"]):
        return None
    if campaign_abort.exists() and not campaign_abort.is_symlink():
        retained = _json_file(campaign_abort, "existing supervisor campaign abort")
        return validate_campaign_abort(retained, admission, binding["campaignId"])
    abort = _campaign_abort_document(
        admission, failure_type=type(failure).__name__,
        failure_message=str(failure), child_return_code=None,
        execution_receipt_present=execution_receipt.exists(), clock=clock,
    )
    _write_exclusive_json(
        campaign_abort, abort,
        uid=0, gid=0,
    )
    return validate_campaign_abort(
        _json_file(campaign_abort, "retained supervisor boot abort"),
        admission, binding["campaignId"],
    )


REMOTE_DETACHED_LAUNCH = r'''
import datetime,fcntl,hashlib,json,os,re,signal,stat,subprocess,sys
PARENT="/home/fhuebscher/observability-placement-candidate-v4-hotel-srv4/control"
CHECKOUT="/home/fhuebscher/observability-placement-candidate-v4-hotel-srv4/checkout"
LEASE="/home/fhuebscher/observability-placement-candidate-v4-runs/.hotel-candidate-v1.lock"
def binpath(name,cands):
    # Spelling only; every identity contract stays literal. /usr/sbin/runuser
    # exists only on fb14srv4, /sbin/runuser only on fb14srv5+srv6. Candidate
    # order keeps fb14srv4's emitted argv byte-identical.
    # 2026-09-21: the candidate is lstat'ed so an unprivileged user cannot
    # interpose a link, but the link is then FOLLOWED and the predicate applied
    # to its target -- /usr/bin/python3 and /bin/python3 are both root-owned
    # symlinks to python3.9 on fb14srv4, so skipping symlinks refused python3
    # outright. The SPELLING is still what is returned and spent.
    for c in cands:
        try: st=os.lstat(c)
        except OSError: continue
        if st.st_uid!=0: continue
        try: t=os.stat(os.path.realpath(c))
        except OSError: continue
        if stat.S_ISREG(t.st_mode) and t.st_uid==0 and os.access(c,os.X_OK): return c
    raise RuntimeError("no root-owned "+name+" among "+repr(list(cands)))
RUNUSER_CANDIDATES=("/usr/sbin/runuser","/sbin/runuser")
PYTHON_CANDIDATES=("/usr/bin/python3","/bin/python3")
def canon(v): return json.dumps(v,allow_nan=False,ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode()
def timestamp(v):
    if not isinstance(v,str) or not v.endswith("Z"): raise RuntimeError("timestamp is not canonical UTC")
    parsed=datetime.datetime.fromisoformat(v[:-1]+"+00:00")
    if parsed.tzinfo is None or parsed.utcoffset()!=datetime.timedelta(0): raise RuntimeError("timestamp is not UTC")
    return parsed
control=None; process=None; lease_fd=None
try:
    admission=json.load(sys.stdin)
    body={k:v for k,v in admission.items() if k!="admissionCanonicalSha256"}
    binding=admission["bindings"]
    campaign=binding["campaignId"]
    if (admission.get("admissionCanonicalSha256")!=hashlib.sha256(canon(body)).hexdigest()
        or not re.fullmatch(r"hotel-v1-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}",campaign)
        or binding.get("target")!="fb14srv4" or binding.get("transportUser")!="root"
        or binding.get("executionUser")!="fhuebscher" or binding.get("executionUid")!=1007
        or binding.get("executionGid")!=1007 or binding.get("supplementalGids")!=[27,998]
        or binding.get("dockerGid")!=998 or binding.get("releaseParent")!=os.path.dirname(PARENT)
        or binding.get("checkoutRoot")!=CHECKOUT or binding.get("controlRoot")!=PARENT
        or binding.get("leasePath")!=LEASE
        or not re.fullmatch(r"hotel-readiness-v1-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}",str(binding.get("readinessCaptureId")))
        or binding.get("maximumWallSeconds")!=18000 or binding.get("cleanupReserveSeconds")!=300
        or admission.get("runtimeAuthorized") is not True
        or admission.get("externalMutationAuthorized") is not True
        or admission.get("promotionAuthorized") is not False):
        raise RuntimeError("detached launch admission differs")
    now=datetime.datetime.now(datetime.timezone.utc)
    issued=timestamp(admission.get("issuedAt")); readiness=timestamp(binding.get("readinessObservedAt"))
    deadline=timestamp(binding.get("deadline"))
    for label,observed in (("admission",issued),("readiness",readiness)):
        age=(now-observed).total_seconds()
        if age < -5 or age > 900: raise RuntimeError("detached launch "+label+" is stale or future-dated")
    if issued < readiness: raise RuntimeError("detached launch admission predates readiness")
    remaining=(deadline-now).total_seconds()
    if remaining < 17700 or remaining > 18005: raise RuntimeError("detached launch lacks the full planned mutation and cleanup budget")
    # Retain a root-owned attempt envelope before the shared flock can reject
    # this campaign, so lease conflict is itself a durable terminal outcome.
    control=os.path.join(PARENT,campaign)
    os.mkdir(control,0o700); os.chown(control,0,0)
    admission_path=os.path.join(control,"runtime-admission.json")
    fd=os.open(admission_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    payload=canon(admission)+b"\n"; os.write(fd,payload); os.fsync(fd); os.close(fd); os.chown(admission_path,0,0)
    attempt={"schemaVersion":1,"kind":"hotel-srv4-launch-attempt-v1","campaignId":campaign,
             "admissionCanonicalSha256":admission["admissionCanonicalSha256"],
             "attemptedAt":now.isoformat().replace("+00:00","Z"),"leaseAcquired":False}
    path=os.path.join(control,"launch-attempt.json")
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    os.write(fd,canon(attempt)+b"\n"); os.fsync(fd); os.close(fd); os.chown(path,0,0)
    lease_fd=os.open(LEASE,os.O_RDWR|os.O_CREAT|getattr(os,"O_NOFOLLOW",0),0o640)
    if not stat.S_ISREG(os.fstat(lease_fd).st_mode): raise RuntimeError("lease path is not a regular file")
    os.fchmod(lease_fd,0o640); os.fchown(lease_fd,0,1007)
    fcntl.flock(lease_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    owner={"schemaVersion":1,"kind":"hotel-candidate-runtime-lease-v1","campaignId":campaign,
           "admissionCanonicalSha256":admission["admissionCanonicalSha256"],"deadline":binding["deadline"],
           "projectPrefix":binding["projectPrefix"],"ports":binding["ports"]}
    os.ftruncate(lease_fd,0); os.lseek(lease_fd,0,os.SEEK_SET)
    os.write(lease_fd,canon(owner)+b"\n"); os.fsync(lease_fd)
    log_path=os.path.join(control,"controller.log")
    receipt_path=os.path.join(control,"execution-receipt.json")
    log=open(log_path,"xb",buffering=0); os.chown(log_path,0,0)
    abort_path=os.path.join(control,"campaign-abort.json")
    command=[binpath("python3",PYTHON_CANDIDATES),"-I",
             CHECKOUT+"/modules/hotel-reservation/execution/candidate_runtime.py",
             "--supervise-admission",admission_path,"--execution-receipt",receipt_path,
             "--campaign-abort",abort_path,"--lease-fd",str(lease_fd)]
    process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                             cwd=CHECKOUT,start_new_session=True,close_fds=True,pass_fds=(lease_fd,))
    launch={"schemaVersion":1,"kind":"hotel-srv4-detached-launch-v1","campaignId":campaign,
            "pid":process.pid,"admissionCanonicalSha256":admission["admissionCanonicalSha256"],
            "argv":command}
    launch_path=os.path.join(control,"launch.json")
    fd=os.open(launch_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    os.write(fd,canon(launch)+b"\n"); os.fsync(fd); os.close(fd); os.chown(launch_path,0,0)
    os.close(lease_fd); lease_fd=None
    print(json.dumps(launch,sort_keys=True,separators=(",", ":")))
except Exception as exc:
    if process is not None:
        try: os.killpg(process.pid,signal.SIGTERM); process.wait(timeout=10)
        except Exception:
            try: os.killpg(process.pid,signal.SIGKILL)
            except Exception: pass
    try:
        if control is not None and os.path.isdir(control):
            receipt=os.path.join(control,"execution-receipt.json")
            abort=os.path.join(control,"campaign-abort.json")
            if not os.path.exists(receipt) and not os.path.lexists(abort):
                body={"schemaVersion":1,"kind":"hotel-candidate-campaign-abort-v1",
                      "campaignId":campaign,"admissionCanonicalSha256":admission["admissionCanonicalSha256"],
                      "terminalAt":datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z"),
                      "phase":"target-controller-supervisor","failureType":type(exc).__name__,
                      "failureMessage":str(exc)[:4096],"childReturnCode":None,
                      "executionReceiptPresent":False,"executionReceiptValid":False,"attemptedCells":None,
                      "ownedCleanupState":"unknown-requires-next-preflight-or-operator-review",
                      "leaseReleaseStatus":"supervisor-finally-attempted-after-abort-retention",
                      "candidateCampaignValid":False,"runtimeAuthorized":True,"promotionAuthorized":False}
                body["abortCanonicalSha256"]=hashlib.sha256(canon(body)).hexdigest()
                fd=os.open(abort,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
                payload=canon(body)+b"\n"; os.write(fd,payload); os.fsync(fd); os.close(fd); os.chown(abort,0,0)
            seal_path=os.path.join(control,"terminal-tree-seal.json")
            if os.path.isfile(abort) and not os.path.lexists(seal_path):
                observed=subprocess.run(
                    [binpath("python3",PYTHON_CANDIDATES),"-I",CHECKOUT+"/modules/hotel-reservation/execution/candidate_runtime.py",
                     "--root-terminal-observe-admission",os.path.join(control,"runtime-admission.json")],
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    cwd=CHECKOUT,check=False,timeout=180)
                if observed.returncode:
                    failure_path=os.path.join(control,"root-cleanup-observation-failure.json")
                    failure={"schemaVersion":1,"kind":"hotel-srv4-root-terminal-observation-failure-v1",
                             "campaignId":campaign,"state":"unknown","failureType":"ObservationProcessExit",
                             "returnCode":observed.returncode,"ownedResourcesRemaining":None}
                    fd=os.open(failure_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
                    payload=canon(failure)+b"\n"; os.write(fd,payload); os.fsync(fd); os.close(fd); os.chown(failure_path,0,0)
    except Exception: pass
    if lease_fd is not None:
        try: fcntl.flock(lease_fd,fcntl.LOCK_UN)
        except Exception: pass
        try: os.close(lease_fd)
        except Exception: pass
    print(json.dumps({"error":type(exc).__name__+": "+str(exc)},sort_keys=True),file=sys.stderr)
    raise SystemExit(1)
'''



def _rebudget_launcher(program: str, wall: int, minimum: int) -> str:
    """The embedded launcher with a parameterised epoch's budget; the frozen 18000 / 17700 text otherwise.

    Each literal is replaced exactly once or the module refuses to load, so a reviewed safety seam cannot
    silently keep the frozen budget (the launcher runs as root from ssh stdin, not from the checkout).
    """
    if (wall, minimum) == (18000, 17700):
        return program
    for old, new in (
        ('binding.get("maximumWallSeconds")!=18000', 'binding.get("maximumWallSeconds")!=%d' % wall),
        ("remaining < 17700 or remaining > 18005", "remaining < %d or remaining > %d" % (minimum, wall + 5)),
    ):
        if program.count(old) != 1:
            raise GateError("embedded launcher budget literal is not present exactly once")
        program = program.replace(old, new)
    return program


REMOTE_DETACHED_LAUNCH = _rebudget_launcher(
    REMOTE_DETACHED_LAUNCH, MAXIMUM_WALL_SECONDS, MINIMUM_FIRST_MUTATION_REMAINING_SECONDS,
)

REMOTE_STATUS = r'''
import fcntl,json,os,re,sys
PARENT="/home/fhuebscher/observability-placement-candidate-v4-hotel-srv4/control"
LEASE="/home/fhuebscher/observability-placement-candidate-v4-runs/.hotel-candidate-v1.lock"
campaign=sys.stdin.read().strip()
if not re.fullmatch(r"hotel-v1-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}",campaign): raise SystemExit(2)
root=os.path.join(PARENT,campaign)
launch_path=os.path.join(root,"launch.json"); receipt=os.path.join(root,"execution-receipt.json")
abort=os.path.join(root,"campaign-abort.json")
def regular(path): return os.path.isfile(path) and not os.path.islink(path)
launch_present=regular(launch_path); receipt_present=regular(receipt); abort_present=regular(abort)
if os.path.lexists(receipt) and not receipt_present: raise SystemExit(3)
if os.path.lexists(abort) and not abort_present: raise SystemExit(3)
if abort_present:
    with open(abort,"r",encoding="utf-8") as handle: completion=json.load(handle)
    if completion.get("kind")!="hotel-candidate-campaign-abort-v1" or completion.get("campaignId")!=campaign: raise SystemExit(3)
    completion_artifact="campaign-abort.json"
elif receipt_present:
    with open(receipt,"r",encoding="utf-8") as handle: completion=json.load(handle)
    if completion.get("kind")!="hotel-candidate-execution-receipt-v1": raise SystemExit(3)
    completion_artifact="execution-receipt.json"
else: completion_artifact=None
if launch_present:
    with open(launch_path,"r",encoding="utf-8") as handle: launch=json.load(handle)
    if launch.get("campaignId")!=campaign: raise SystemExit(3)
    pid=launch.get("pid")
else: pid=None  # fresh identity (no launch, no completion): the pre-launch dry run's expected answer
terminal=completion_artifact is not None; running=False
if not terminal and isinstance(pid,int) and pid>1:
    try: os.kill(pid,0); running=True
    except ProcessLookupError: pass
    except PermissionError: running=True
lease_present=regular(LEASE); lease_locked=False; lease_owned=False
if lease_present:
    fd=os.open(LEASE,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        try:
            os.lseek(fd,0,os.SEEK_SET); owner=json.loads(os.read(fd,65536).decode("utf-8"))
            lease_owned=owner.get("campaignId")==campaign
        except Exception: raise SystemExit(3)
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: lease_locked=True
        else: fcntl.flock(fd,fcntl.LOCK_UN)
    finally: os.close(fd)
value={"schemaVersion":1,"kind":"hotel-srv4-detached-status-v1","campaignId":campaign,
       "pid":pid,"running":running,"terminal":terminal,"launchPresent":launch_present,
       "executionReceiptPresent":receipt_present,"campaignAbortPresent":abort_present,
       "completionArtifact":completion_artifact,
       "controllerLogPresent":os.path.isfile(os.path.join(root,"controller.log")),
       "leasePresent":lease_present,"leaseLocked":lease_locked,
       "leaseOwnedByCampaign":lease_owned,
       "leaseLockedByCampaign":lease_owned and lease_locked}
print(json.dumps(value,sort_keys=True,separators=(",", ":")))
'''


REMOTE_REFETCH_ARCHIVE = r'''
import os,re,sys,tarfile
campaign=sys.stdin.read().strip()
if not re.fullmatch(r"hotel-v1-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}",campaign): raise SystemExit(2)
artifact=os.path.join("/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1",campaign)
control=os.path.join("/home/fhuebscher/observability-placement-candidate-v4-hotel-srv4/control",campaign)
if os.path.islink(control) or not os.path.isdir(control): raise SystemExit(3)
if os.path.lexists(artifact) and (os.path.islink(artifact) or not os.path.isdir(artifact)): raise SystemExit(3)
with tarfile.open(fileobj=sys.stdout.buffer,mode="w|gz",format=tarfile.PAX_FORMAT) as bundle:
    if os.path.isdir(artifact): bundle.add(artifact,arcname="evidence/"+campaign,recursive=True)
    bundle.add(control,arcname="control/"+campaign,recursive=True)
'''


def validate_local_replay_binding(admission: Mapping[str, Any]) -> Bindings:
    """Require the clean local replay code to be the exact admitted revision."""
    binding = admission.get("bindings")
    if not isinstance(binding, dict):
        raise GateError("refetched admission bindings are missing")
    current = inspect_bindings(binding.get("frameworkCommit"))
    expected = plan_binding(current)
    if any(binding.get(key) != value for key, value in expected.items()):
        raise GateError("local replay revision, plan, descriptor, policy, or controller differs")
    return current


class DetachedSshController:
    """Launch once, then allow status/refetch from any later local session."""

    def _ssh(self, code: str, payload: str, timeout: float = 30) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "--",
                 "root@fb14srv4", resolve_target_binary_over_ssh("python3"),
                 "-I", "-c", shlex.quote(code)],
                input=payload, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False, timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise GateError(f"srv4 detached control failed to complete: {exc}") from exc
        if result.returncode:
            raise GateError("srv4 detached control rejected the request: " + result.stderr[:4096])
        return result

    def launch(
        self, admission: Mapping[str, Any], *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> dict[str, Any]:
        validate_embedded_remote_programs()
        validate_launch_admission(admission, clock=clock)
        value = strict_json(
            self._ssh(REMOTE_DETACHED_LAUNCH, canonical_bytes(admission).decode()).stdout,
            "srv4 detached launch",
        )
        binding = admission["bindings"]
        control = Path(binding["controlRoot"]) / binding["campaignId"]
        expected_argv = [
            _replayed_spelling(value, 0, "python3", TARGET_PYTHON_CANDIDATES), "-I",
            binding["checkoutRoot"] + "/modules/hotel-reservation/execution/candidate_runtime.py",
            "--supervise-admission", str(control / "runtime-admission.json"),
            "--execution-receipt", str(control / "execution-receipt.json"),
            "--campaign-abort", str(control / "campaign-abort.json"),
            "--lease-fd", value.get("argv", [None])[-1] if isinstance(value, dict) and isinstance(value.get("argv"), list) else None,
        ]
        if (
            not isinstance(value, dict)
            or set(value) != {"schemaVersion", "kind", "campaignId", "pid", "admissionCanonicalSha256", "argv"}
            or value.get("schemaVersion") != 1
            or value.get("kind") != "hotel-srv4-detached-launch-v1"
            or value.get("campaignId") != binding["campaignId"]
            or value.get("admissionCanonicalSha256") != admission["admissionCanonicalSha256"]
            or not isinstance(value.get("pid"), int) or isinstance(value.get("pid"), bool) or value["pid"] <= 1
            or not isinstance(value.get("argv"), list) or value["argv"] != expected_argv
            or not isinstance(value["argv"][-1], str) or not value["argv"][-1].isdigit()
            or int(value["argv"][-1]) < 3
        ):
            raise GateError("srv4 detached launch receipt differs")
        return value

    def status(self, campaign_id: str) -> dict[str, Any]:
        if CAMPAIGN_ID.fullmatch(campaign_id) is None:
            raise GateError("status campaign identity differs")
        value = strict_json(self._ssh(REMOTE_STATUS, campaign_id).stdout, "srv4 status")
        if (
            not isinstance(value, dict)
            or set(value) != {
                "schemaVersion", "kind", "campaignId", "pid", "running",
                "terminal", "launchPresent", "executionReceiptPresent",
                "campaignAbortPresent", "completionArtifact", "controllerLogPresent",
                "leasePresent", "leaseLocked", "leaseOwnedByCampaign",
                "leaseLockedByCampaign",
            }
            or value["schemaVersion"] != 1
            or value["kind"] != "hotel-srv4-detached-status-v1"
            or value["campaignId"] != campaign_id
            or not isinstance(value["running"], bool)
            or not isinstance(value["terminal"], bool)
            or not isinstance(value["launchPresent"], bool)
            or not isinstance(value["executionReceiptPresent"], bool)
            or not isinstance(value["campaignAbortPresent"], bool)
            or value["completionArtifact"] not in {
                None, "execution-receipt.json", "campaign-abort.json",
            }
            or not isinstance(value["leasePresent"], bool)
            or not isinstance(value["leaseLocked"], bool)
            or not isinstance(value["leaseOwnedByCampaign"], bool)
            or not isinstance(value["leaseLockedByCampaign"], bool)
            or value["terminal"] != (value["completionArtifact"] is not None)
            or (
                value["completionArtifact"] == "execution-receipt.json"
                and value["executionReceiptPresent"] is not True
            )
            or (
                value["completionArtifact"] == "campaign-abort.json"
                and value["campaignAbortPresent"] is not True
            )
            or value["running"] is True and value["terminal"] is True
            or value["leaseLockedByCampaign"] is True and (
                value["leaseLocked"] is not True or value["leaseOwnedByCampaign"] is not True
            )
        ):
            raise GateError("srv4 detached status receipt differs")
        return value

    def capture_readiness(
        self, setup_id: str, destination: Path, *, capture_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute the installed target producer, then fetch its exact retained bytes."""
        if SETUP_ID.fullmatch(setup_id) is None:
            raise GateError("readiness capture setup identity differs")
        if capture_id is None:
            capture_id = new_readiness_capture_id()
        if READINESS_CAPTURE_ID.fullmatch(capture_id) is None:
            raise GateError("readiness capture identity differs")
        destination = destination.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "--",
            "root@fb14srv4", resolve_target_binary_over_ssh("python3"), "-I",
            TARGET["checkoutRoot"] + "/" + CONTROLLER_PATHS["candidate-runtime"],
            "--target-readiness", setup_id,
            "--readiness-capture-id", capture_id,
        ]
        try:
            produced = subprocess.run(
                command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False, timeout=900,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise GateError(f"srv4 readiness producer failed to complete: {exc}") from exc
        if produced.returncode:
            raise GateError("srv4 readiness producer rejected the request: " + produced.stderr[:4096])
        readiness = strict_json(produced.stdout, "srv4 target-produced readiness")
        expected_root = "readiness-" + capture_id
        if (
            not isinstance(readiness, dict)
            or readiness.get("schemaVersion") != 4
            or readiness.get("kind") != READINESS_KIND
            or readiness.get("captureId") != capture_id
            or readiness.get("artifactRoot") != expected_root
            or readiness.get("hostObserved") != TARGET["target"]
            or readiness.get("producer", {}).get("cellsRun") != 0
            or readiness.get("promotionAuthorized") is not False
        ):
            raise GateError("srv4 target-produced readiness receipt differs")
        archive_path = destination.parent / (destination.name + ".tar.gz")
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_dir() or not archive_path.is_file():
                raise GateError("existing local readiness capture is incomplete")
            retained = _json_file(
                destination / expected_root / "readiness.json",
                "existing fetched target-produced readiness",
            )
            if canonical_bytes(retained) != canonical_bytes(readiness):
                raise GateError("existing local readiness capture differs from target")
            return {
                "schemaVersion": 1,
                "kind": "hotel-srv4-readiness-capture-v1",
                "setupId": setup_id,
                "captureId": capture_id,
                "artifactParent": str(destination),
                "readinessPath": str(destination / expected_root / "readiness.json"),
                "archiveSha256": _sha256(archive_path),
                "readinessCanonicalSha256": canonical_sha256(readiness),
                "cellsRun": 0,
                "promotionAuthorized": False,
            }
        if archive_path.is_symlink() or (archive_path.exists() and not archive_path.is_file()):
            raise GateError("readiness capture archive path is unsafe")
        if archive_path.exists():
            # A tarball without its extracted directory is a leftover of an earlier
            # capture (the drivers archive the directory, the tarball survived);
            # its root is the OLD capture id, so reusing it can only fail the
            # member-name rule below. Re-fetch instead (first real run, 2026-09-06).
            archive_path.unlink()
        if not archive_path.exists():
            with archive_path.open("xb") as output:
                fetched = subprocess.run(
                    ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "--",
                     "root@fb14srv4", "/bin/tar", "-C", TARGET["artifactParent"],
                     "-czf", "-", expected_root],
                    stdout=output, stderr=subprocess.PIPE, check=False, timeout=900,
                )
            if fetched.returncode:
                raise GateError(
                    "srv4 readiness capture failed: "
                    + fetched.stderr.decode(errors="replace")[:4096]
                )
        staging = Path(tempfile.mkdtemp(prefix=".hotel-readiness-", dir=destination.parent))
        try:
            with tarfile.open(archive_path, mode="r:gz") as bundle:
                for member in bundle.getmembers():
                    if (
                        not member.name or member.name.startswith("/") or "\\" in member.name
                        or any(part in {"", ".", ".."} for part in member.name.split("/"))
                        or member.issym() or member.islnk()
                        or not (member.isdir() or member.isfile())
                        or not (
                            member.name == expected_root
                            or member.name.startswith(expected_root + "/")
                        )
                    ):
                        raise GateError("readiness capture archive contains an unsafe member")
                bundle.extractall(staging, filter="data")
            retained = _json_file(
                staging / expected_root / "readiness.json",
                "fetched target-produced readiness",
            )
            if canonical_bytes(retained) != canonical_bytes(readiness):
                raise GateError("fetched target-produced readiness differs from SSH receipt")
            os.rename(staging, destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        readiness_path = destination / expected_root / "readiness.json"
        retained = _json_file(readiness_path, "fetched target-produced readiness")
        if canonical_bytes(retained) != canonical_bytes(readiness):
            raise GateError("fetched target-produced readiness differs from SSH receipt")
        return {
            "schemaVersion": 1,
            "kind": "hotel-srv4-readiness-capture-v1",
            "setupId": setup_id,
            "captureId": capture_id,
            "artifactParent": str(destination),
            "readinessPath": str(readiness_path),
            "archiveSha256": _sha256(archive_path),
            "readinessCanonicalSha256": canonical_sha256(readiness),
            "cellsRun": 0,
            "promotionAuthorized": False,
        }

    def refetch_and_replay(self, campaign_id: str, destination: Path) -> dict[str, Any]:
        """Read-only refetch followed by a fresh local terminal replay."""
        current = self.status(campaign_id)
        if (
            current["running"] is True or current["terminal"] is not True
            or current["completionArtifact"] not in {
                "execution-receipt.json", "campaign-abort.json",
            }
            or current["leaseLockedByCampaign"] is True
        ):
            raise GateError("srv4 campaign is not terminal and refetchable")
        destination = destination.resolve()
        if destination.exists() or destination.is_symlink():
            raise GateError("refusing to replace a fetched campaign")
        destination.parent.mkdir(parents=True, exist_ok=True)
        archive_path = destination.parent / (destination.name + ".tar.gz")
        if archive_path.exists() or archive_path.is_symlink():
            raise GateError("refetch archive path already exists")
        evidence_relative = f"evidence/{campaign_id}"
        control_relative = f"control/{campaign_id}"
        with archive_path.open("xb") as output:
            result = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "--",
                 "root@fb14srv4", resolve_target_binary_over_ssh("python3"),
                 "-I", "-c", shlex.quote(REMOTE_REFETCH_ARCHIVE)],
                input=campaign_id.encode(),
                stdout=output, stderr=subprocess.PIPE, check=False, timeout=1800,
            )
        if result.returncode:
            raise GateError("srv4 evidence refetch failed: " + result.stderr.decode(errors="replace")[:4096])
        destination.mkdir(mode=0o700)
        with tarfile.open(archive_path, mode="r:gz") as bundle:
            for member in bundle.getmembers():
                if (
                    not member.name
                    or member.name.startswith("/")
                    or "\\" in member.name
                    or any(part in {"", ".", ".."} for part in member.name.split("/"))
                    or member.issym() or member.islnk()
                    or not (member.isdir() or member.isfile())
                    or not (
                        member.name == evidence_relative
                        or member.name.startswith(evidence_relative + "/")
                        or member.name == control_relative
                        or member.name.startswith(control_relative + "/")
                    )
                ):
                    raise GateError("refetched campaign archive contains an unsafe member")
            bundle.extractall(destination, filter="data")
        control = destination / control_relative
        artifact = destination / evidence_relative
        admission = _json_file(control / "runtime-admission.json", "refetched admission")
        body = {key: value for key, value in admission.items() if key != "admissionCanonicalSha256"}
        if (
            admission.get("admissionCanonicalSha256") != canonical_sha256(body)
            or admission.get("bindings", {}).get("campaignId") != campaign_id
            or admission.get("bindings", {}).get("artifactRoot") != (
                TARGET["artifactParent"] + "/" + campaign_id
            )
        ):
            raise GateError("refetched admission identity differs")
        terminal_seal = validate_terminal_tree_seal(control, artifact, admission)
        if current["completionArtifact"] == "campaign-abort.json":
            abort = validate_campaign_abort(
                _json_file(control / "campaign-abort.json", "refetched campaign abort"),
                admission, campaign_id,
            )
            receipt = {
                "schemaVersion": 1,
                "kind": "hotel-srv4-local-terminal-refetch-v1",
                "campaignId": campaign_id,
                "archiveSha256": _sha256(archive_path),
                "admissionCanonicalSha256": admission["admissionCanonicalSha256"],
                "targetAbortCanonicalSha256": abort["abortCanonicalSha256"],
                "targetExecutionStatus": "campaign-abort",
                "localReplayPerformed": False,
                "status": "target-abort-retained-no-pass-replay",
                "maximumEvidenceLabel": "candidate-evidence",
                "absoluteCostOrLatencyCanonical": False,
                "promotionAuthorized": False,
            }
            _write_exclusive_json(destination / "local-terminal-refetch.json", receipt)
            return receipt
        execution = _json_file(control / "execution-receipt.json", "refetched execution receipt")
        terminal_statuses = {
            "complete", "stopped-invalid-campaign", "stopped-invalid-cell",
            "stopped-deadline", "runtime-error", "cleanup-failed",
        }
        if (
            execution.get("schemaVersion") != 1
            or execution.get("kind") != "hotel-candidate-execution-receipt-v1"
            or execution.get("status") not in terminal_statuses
            or execution.get("scheduledCells") != CELL_COUNT
            or not isinstance(execution.get("attemptedCells"), int)
            or not 0 <= execution["attemptedCells"] <= CELL_COUNT
            or not isinstance(execution.get("records"), list)
            or len(execution["records"]) != execution["attemptedCells"]
            or not isinstance(execution.get("errors"), list)
            or execution.get("runtimeAuthorized") is not True
            or execution.get("promotionAuthorized") is not False
        ):
            raise GateError("refetched admission or execution terminal state differs")
        if execution["status"] != "complete":
            receipt = {
                "schemaVersion": 1,
                "kind": "hotel-srv4-local-terminal-refetch-v1",
                "campaignId": campaign_id,
                "archiveSha256": _sha256(archive_path),
                "admissionCanonicalSha256": admission["admissionCanonicalSha256"],
                "targetExecutionReceiptCanonicalSha256": canonical_sha256(execution),
                "targetExecutionStatus": execution["status"],
                "localReplayPerformed": False,
                "status": "target-terminal-retained-no-pass-replay",
                "maximumEvidenceLabel": "candidate-evidence",
                "absoluteCostOrLatencyCanonical": False,
                "promotionAuthorized": False,
            }
            _write_exclusive_json(destination / "local-terminal-refetch.json", receipt)
            return receipt
        observed_remaining = terminal_seal.get("ownedResourcesRemaining")
        if (
            terminal_seal.get("ownedResourcesState") != "observed"
            or not isinstance(observed_remaining, dict)
            or any(
                resources.get(kind)
                for resources in observed_remaining.values()
                for kind in ("containers", "networks", "volumes")
            )
        ):
            raise GateError("complete target execution has live or unknown owned resources")
        if (
            execution["attemptedCells"] != CELL_COUNT
            or execution.get("leaseRelease", {}).get("released") is not True
            or not artifact.is_dir() or artifact.is_symlink()
        ):
            raise GateError("complete target execution lacks complete retained evidence")
        validate_local_replay_binding(admission)
        terminal_path = ROOT / "modules/hotel-reservation/validation/candidate_terminal.py"
        spec = importlib.util.spec_from_file_location("hotel_candidate_local_refetch_terminal", terminal_path)
        if spec is None or spec.loader is None:
            raise GateError("cannot load local terminal replay")
        terminal = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = terminal
        spec.loader.exec_module(terminal)
        terminal.configure_path_remap(Path(admission["bindings"]["artifactRoot"]), artifact)
        replay = terminal.validate_campaign(artifact, cell_contracts(admission), admission)
        retained = _json_file(artifact / "campaign-terminal.json", "refetched campaign terminal")
        if canonical_bytes(replay) != canonical_bytes(retained):
            raise GateError("fresh local terminal replay differs from retained target terminal")
        receipt = {
            "schemaVersion": 1,
            "kind": "hotel-srv4-local-terminal-replay-v1",
            "campaignId": campaign_id,
            "archiveSha256": _sha256(archive_path),
            "admissionCanonicalSha256": admission["admissionCanonicalSha256"],
            "targetExecutionReceiptCanonicalSha256": canonical_sha256(execution),
            "localCampaignTerminalCanonicalSha256": canonical_sha256(replay),
            "status": "pass",
            "maximumEvidenceLabel": "candidate-evidence",
            "absoluteCostOrLatencyCanonical": False,
            "promotionAuthorized": False,
        }
        replay_path = destination / "local-terminal-replay.json"
        replay_path.write_bytes(canonical_bytes(receipt) + b"\n")
        return receipt


REMOTE_ONE_SHOT_INSTALL = r'''
import datetime,hashlib,json,os,pwd,grp,re,shutil,socket,stat,subprocess,sys,tarfile
TARGET="fb14srv4"
PARENT="/home/fhuebscher/observability-placement-candidate-v4-hotel-srv4"
CHECKOUT=PARENT+"/checkout"; CONTROL=PARENT+"/control"
ARTIFACT="/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1"
LEASE_ROOT="/home/fhuebscher/observability-placement-candidate-v4-runs"
LEASE_PATH=LEASE_ROOT+"/.hotel-candidate-v1.lock"
UPLOAD="/tmp/obsplacement-hotel-srv4-20260830-a53f9c27.tar"
def binpath(name,cands):
    # Spelling only; every identity contract stays literal. /usr/sbin/runuser
    # exists only on fb14srv4, /sbin/runuser only on fb14srv5+srv6. Candidate
    # order keeps fb14srv4's emitted argv byte-identical.
    # 2026-09-21: the candidate is lstat'ed so an unprivileged user cannot
    # interpose a link, but the link is then FOLLOWED and the predicate applied
    # to its target -- /usr/bin/python3 and /bin/python3 are both root-owned
    # symlinks to python3.9 on fb14srv4, so skipping symlinks refused python3
    # outright. The SPELLING is still what is returned and spent.
    for c in cands:
        try: st=os.lstat(c)
        except OSError: continue
        if st.st_uid!=0: continue
        try: t=os.stat(os.path.realpath(c))
        except OSError: continue
        if stat.S_ISREG(t.st_mode) and t.st_uid==0 and os.access(c,os.X_OK): return c
    raise RuntimeError("no root-owned "+name+" among "+repr(list(cands)))
RUNUSER_CANDIDATES=("/usr/sbin/runuser","/sbin/runuser")
PYTHON_CANDIDATES=("/usr/bin/python3","/bin/python3")
def canon(v): return json.dumps(v,allow_nan=False,ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode()
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        while True:
            chunk=f.read(1024*1024)
            if not chunk: break
            h.update(chunk)
    return h.hexdigest()
def foreign():
    # Host condition v2: every container and Compose project that is not hotel_candidate_v4's own.
    p=subprocess.run(["docker","ps","-a","--no-trunc","--format","{{.ID}}|{{.State}}|{{.Image}}|{{.Names}}|{{.Labels}}"],text=True,capture_output=True,check=True,timeout=30)
    rows=[]
    for row in (x for x in p.stdout.splitlines() if x):
        labels=dict(i.split("=",1) for i in row.split("|",4)[4].split(",") if "=" in i) if row.count("|")>=4 else {}
        if not str(labels.get("com.docker.compose.project","")).startswith("hotel_candidate_v4"): rows.append(row)
    listing=subprocess.run(["docker","compose","ls","--all","--format","json"],text=True,capture_output=True,check=True,timeout=30)
    for x in json.loads(listing.stdout):
        name=x.get("Name") if isinstance(x,dict) else None
        if not str(name).startswith("hotel_candidate_v4"): rows.append("compose-project|%s|%s" % (name, x.get("ConfigFiles") if isinstance(x,dict) else None))
    value={"project":None,"configPath":None,"stateCounts":{},"rows":sorted(rows)}
    value["sha256"]=hashlib.sha256(canon(value)).hexdigest(); return value
def port_free(port):
    s=socket.socket();
    try: s.bind(("127.0.0.1",port)); return True
    except OSError: return False
    finally: s.close()
created=[]; install_complete=False
try:
    setup=json.load(sys.stdin); binding=setup["bindings"]; target=binding["operationalTarget"]
    if (setup.get("kind")!="hotel-candidate-gate-setup-v1" or setup.get("setupAuthorized") is not True
        or setup.get("runtimeAuthorized") is not False or setup.get("promotionAuthorized") is not False
        or target.get("target")!=TARGET or target.get("transportUser")!="root" or target.get("setupUser")!="root"
        or target.get("executionUser")!="fhuebscher" or target.get("executionUid")!=1007
        or target.get("executionGid")!=1007 or target.get("dockerGid")!=998
        or target.get("authorizedParent")!=PARENT or target.get("releaseParent")!=PARENT
        or target.get("checkoutRoot")!=CHECKOUT
        or target.get("artifactParent")!=ARTIFACT or target.get("leaseRoot")!=LEASE_ROOT
        or target.get("leasePath")!=LEASE_PATH
        or target.get("controlRoot")!=CONTROL or target.get("uploadPath")!=UPLOAD
        or binding.get("readinessProbeAuthorized") is not True
        or binding.get("readinessCaptureMode")!="repeatable-append-only-zero-cell"
        or binding.get("cellsAuthorized")!=0):
        raise RuntimeError("setup authority or target binding differs")
    if os.geteuid()!=0: raise RuntimeError("setup is not root")
    if os.path.lexists(PARENT) or os.path.lexists(ARTIFACT) or os.path.lexists(LEASE_PATH):
        raise RuntimeError("one-shot release, artifact, or lease path already exists")
    st=os.lstat(UPLOAD)
    if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode): raise RuntimeError("uploaded bundle is not a regular file")
    if st.st_size!=binding["bundleSizeBytes"] or sha(UPLOAD)!=binding["bundleSha256"]: raise RuntimeError("uploaded bundle bytes differ")
    user=pwd.getpwnam("fhuebscher")
    gids=sorted({g.gr_gid for g in grp.getgrall() if "fhuebscher" in g.gr_mem}|{user.pw_gid})
    if user.pw_uid!=1007 or user.pw_gid!=1007 or not {27,998}.issubset(gids): raise RuntimeError("execution identity or supplemental groups differ")
    version=subprocess.run(["docker","version","--format","{{.Server.Version}}"],text=True,capture_output=True,check=True,timeout=30).stdout.strip()
    access=subprocess.run([binpath("runuser",RUNUSER_CANDIDATES),"--user","fhuebscher","--","docker","version","--format","{{.Server.Version}}"],text=True,capture_output=True,check=True,timeout=30).stdout.strip()
    if version!="29.6.1" or access!=version: raise RuntimeError("Docker version or execution access differs")
    if not port_free(35005) or not port_free(36685): raise RuntimeError("fixed Hotel ports are occupied")
    before=foreign()
    # 2026-09-21: host condition v2. dps_training_k is decommissioned; a foreign container or
    # Compose project of ANY name refuses setup, and the (empty) inventory is recorded.
    if before["rows"]: raise RuntimeError("a foreign Compose project or container is present: %s" % before["rows"][:3])
    # root@fb14srv4 logs in with zsh and umask 077, which turned mkdir(0o755) into 0700 and made
    # the readiness seam campaign-path-ownership reject the first real install (2026-09-06).
    # Modes are set explicitly and verified below, not left to the login shell.
    os.umask(0o022)
    os.makedirs(os.path.dirname(PARENT),mode=0o755,exist_ok=True)
    os.mkdir(PARENT,0o755); created.append((PARENT,os.lstat(PARENT).st_dev,os.lstat(PARENT).st_ino))
    os.mkdir(CHECKOUT,0o755)
    with tarfile.open(UPLOAD,"r:") as bundle:
        for member in bundle.getmembers():
            name=member.name
            if (not name or name.startswith("/") or "\\" in name or any(x in {"",".",".."} for x in name.split("/"))
                or member.issym() or member.islnk() or not (member.isdir() or member.isfile())):
                raise RuntimeError("bundle member is unsafe")
        # The exact reviewed archive is already restricted to normalized
        # regular files/directories with no links.  Calling extractall without
        # the Python-3.12-only filter keyword keeps this compatible with the
        # cluster's Python 3.9 baseline (the interpreter itself is resolved by
        # binpath, not fixed).
        bundle.extractall(CHECKOUT)
    with open(CHECKOUT+"/install-manifest.json","rb") as f: manifest=json.load(f)
    body={k:v for k,v in manifest.items() if k!="manifestCanonicalSha256"}
    if (manifest.get("manifestCanonicalSha256")!=hashlib.sha256(canon(body)).hexdigest()
        or manifest.get("manifestCanonicalSha256")!=binding["manifestCanonicalSha256"]):
        raise RuntimeError("installed manifest identity differs")
    observed=[]
    for row in manifest["entries"]:
        path=os.path.join(CHECKOUT,*row["path"].split("/")); real=os.path.realpath(path)
        if not real.startswith(os.path.realpath(CHECKOUT)+os.sep) or os.path.islink(path) or not os.path.isfile(path):
            raise RuntimeError("installed payload path escapes")
        data=open(path,"rb").read(); actual={"path":row["path"],"kind":"file","mode":stat.S_IMODE(os.lstat(path).st_mode),"size":len(data),"sha256":hashlib.sha256(data).hexdigest()}
        observed.append(actual)
    if observed!=manifest["entries"]: raise RuntimeError("installed payload bytes differ")
    os.mkdir(CONTROL,0o700)
    os.makedirs(LEASE_ROOT,mode=0o755,exist_ok=True)
    os.mkdir(ARTIFACT,0o700); created.append((ARTIFACT,os.lstat(ARTIFACT).st_dev,os.lstat(ARTIFACT).st_ino))
    # The reviewed controller and all authority/control receipts stay root-owned.
    # Only the separate experiment artifact tree is writable by uid 1007.
    for base,dirs,files in os.walk(PARENT):
        os.chown(base,0,0)
        for name in dirs+files: os.chown(os.path.join(base,name),0,0,follow_symlinks=False)
    os.chown(ARTIFACT,1007,1007)
    for path,mode in ((PARENT,0o755),(CHECKOUT,0o755),(LEASE_ROOT,0o755),(CONTROL,0o700),(ARTIFACT,0o700)):
        os.chmod(path,mode)
        if stat.S_IMODE(os.lstat(path).st_mode)!=mode: raise RuntimeError("installed directory mode differs: "+path)
    after=foreign()
    if after!=before: raise RuntimeError("host container inventory changed during setup")
    receipt={"schemaVersion":1,"kind":"hotel-srv4-install-receipt-v1","setupId":binding["setupId"],
             "target":"fb14srv4","bundleSha256":binding["bundleSha256"],"bundleSizeBytes":binding["bundleSizeBytes"],
             "manifestCanonicalSha256":binding["manifestCanonicalSha256"],"installedEntriesSha256":hashlib.sha256(canon(observed)).hexdigest(),
             "installedFileCount":len(observed),"executionUid":1007,"executionGid":1007,"dockerGid":998,"dockerVersion":version,
             "foreignProject":None,"foreignConfigPath":after["configPath"],
             "foreignStateCounts":after["stateCounts"],"foreignFingerprint":after["sha256"],"foreignResources":after["rows"],
             "ports":{"35005":[],"36685":[]},
             "preSetupAbsent":[PARENT,ARTIFACT,LEASE_PATH],
             "gateSetupCanonicalSha256":hashlib.sha256(canon(setup)).hexdigest(),
             "completedAt":datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z"),
             "cellsRun":0,"runtimeStarted":False,"foreignMutation":False}
    for name,value in (("gate-setup.json",setup),("setup-install.json",receipt)):
        path=CONTROL+"/"+name; fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
        os.write(fd,canon(value)+b"\n"); os.fsync(fd); os.close(fd); os.chown(path,0,0)
    os.unlink(UPLOAD)
    install_complete=True
    print(json.dumps(receipt,sort_keys=True,separators=(",", ":")))
except Exception as exc:
    if not install_complete:
        for path,device,inode in reversed(created):
            try:
                state=os.lstat(path)
                if stat.S_ISDIR(state.st_mode) and not stat.S_ISLNK(state.st_mode) and (state.st_dev,state.st_ino)==(device,inode):
                    shutil.rmtree(path)
            except FileNotFoundError: pass
            except Exception: pass
    try:
        if os.path.isfile(UPLOAD) and not os.path.islink(UPLOAD): os.unlink(UPLOAD)
    except Exception: pass
    print(json.dumps({"error":type(exc).__name__+": "+str(exc)},sort_keys=True),file=sys.stderr)
    raise SystemExit(1)
'''


def validate_embedded_remote_programs(
    *, installer: str = REMOTE_ONE_SHOT_INSTALL,
    launcher: str = REMOTE_DETACHED_LAUNCH,
    status: str = REMOTE_STATUS,
) -> None:
    """Fail closed if a reviewed remote safety seam is removed."""
    try:
        installer_tree = ast.parse(installer, filename="hotel-srv4-one-shot-installer")
        compile(installer, "hotel-srv4-one-shot-installer", "exec")
        compile(launcher, "hotel-srv4-detached-launcher", "exec")
        compile(status, "hotel-srv4-detached-status", "exec")
    except SyntaxError as exc:
        raise GateError(f"embedded remote program is invalid: {exc}") from exc
    if (
        any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "extractall"
            and any(keyword.arg == "filter" for keyword in node.keywords)
            for node in ast.walk(installer_tree)
        )
        or "member.issym()" not in installer
        or "member.islnk()" not in installer
        or "not (member.isdir() or member.isfile())" not in installer
        or "created.append((PARENT" not in installer
        or "shutil.rmtree(path)" not in installer
    ):
        raise GateError("one-shot installer lost Python-3.9 extraction or exact rollback safety")
    if (
        '"--supervise-admission"' not in launcher
        or '"campaign-abort.json"' not in launcher
        or '"launch-attempt.json"' not in launcher
        or launcher.find('"launch-attempt.json"') > launcher.find("fcntl.flock(lease_fd,fcntl.LOCK_EX")
        or '"terminal-tree-seal.json"' not in launcher
        or '"--root-terminal-observe-admission"' not in launcher
        or '"ownedResourcesRemaining":{}' in launcher
        or "lease_fd is not None" not in launcher
        or "os.killpg(process.pid" not in launcher
        or launcher.rfind('payload=canon(body)+b"\\n"')
        > launcher.rfind("fcntl.flock(lease_fd,fcntl.LOCK_UN)")
    ):
        raise GateError("detached launcher lost its durable supervised-abort path")
    if (
        'completion_artifact="campaign-abort.json"' not in status
        or 'owner.get("campaignId")==campaign' not in status
        or '"leaseLockedByCampaign"' not in status
    ):
        raise GateError("detached status lost durable completion or lease-owner discovery")


class SshSetupInstaller:
    """The only setup mutation path: upload and install one exact reviewed tar."""

    def install(
        self, bundle: Path, gate_setup: Mapping[str, Any], *, bindings: Bindings,
        gate_plan: Mapping[str, Any],
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> dict[str, Any]:
        validate_embedded_remote_programs()
        validate_gate_setup(gate_setup, bindings, gate_plan, clock=clock, require_fresh=True)
        binding = gate_setup["bindings"]
        if (
            _sha256(bundle) != binding["bundleSha256"]
            or bundle.stat().st_size != binding["bundleSizeBytes"]
        ):
            raise GateError("local setup bundle differs from GATE-SETUP")
        upload = binding["operationalTarget"]["uploadPath"]
        copy = subprocess.run(
            ["scp", "-p", "--", str(bundle), f"root@fb14srv4:{upload}"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=900,
        )
        if copy.returncode:
            raise GateError("exact setup bundle upload failed: " + copy.stderr[:4096])
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "--",
             "root@fb14srv4", resolve_target_binary_over_ssh("python3"),
             "-I", "-c", shlex.quote(REMOTE_ONE_SHOT_INSTALL)],
            input=canonical_bytes(gate_setup).decode(), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=900,
        )
        if result.returncode:
            raise GateError("one-shot srv4 setup failed: " + result.stderr[:4096])
        value = strict_json(result.stdout, "srv4 setup install receipt")
        if (
            not isinstance(value, dict)
            or value.get("kind") != "hotel-srv4-install-receipt-v1"
            or value.get("bundleSha256") != binding["bundleSha256"]
            or value.get("manifestCanonicalSha256") != binding["manifestCanonicalSha256"]
            or value.get("gateSetupCanonicalSha256") != canonical_sha256(gate_setup)
            or value.get("cellsRun") != 0
            or value.get("runtimeStarted") is not False
            or value.get("foreignMutation") is not False
        ):
            raise GateError("srv4 setup install receipt differs")
        return value

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework-commit")
    parser.add_argument("--gate-plan", type=Path)
    parser.add_argument("--gate-setup", type=Path)
    parser.add_argument("--readiness", type=Path)
    parser.add_argument("--readiness-artifact-parent", type=Path)
    parser.add_argument("--gate-run", type=Path)
    parser.add_argument("--admission-output", type=Path)
    parser.add_argument("--launch-detached", action="store_true")
    parser.add_argument("--target-readiness")
    parser.add_argument("--readiness-capture-id")
    parser.add_argument("--capture-readiness-setup")
    parser.add_argument("--capture-readiness-destination", type=Path)
    parser.add_argument("--target-self-check")
    parser.add_argument("--supervise-admission", type=Path)
    parser.add_argument("--root-terminal-observe-admission", type=Path)
    parser.add_argument("--resume-admission", type=Path)
    parser.add_argument("--execution-receipt", type=Path)
    parser.add_argument("--campaign-abort", type=Path)
    parser.add_argument("--lease-fd", type=int)
    parser.add_argument("--status-campaign")
    parser.add_argument("--refetch-campaign")
    parser.add_argument("--refetch-destination", type=Path)
    args = parser.parse_args()
    try:
        if args.root_terminal_observe_admission is not None:
            if os.geteuid() != 0:
                raise GateError("root terminal observation requires root")
            observed_admission = _json_file(
                args.root_terminal_observe_admission, "root terminal observation admission",
            )
            observed_binding = observed_admission.get("bindings", {})
            expected_control = Path(observed_binding.get("controlRoot", "")) / str(
                observed_binding.get("campaignId", "")
            )
            if args.root_terminal_observe_admission != expected_control / "runtime-admission.json":
                raise GateError("root terminal observation admission path differs")
            _root_terminal_observation_and_seal(observed_admission, expected_control)
            return 0
        if args.target_readiness is not None:
            if args.readiness_capture_id is None:
                raise GateError("target readiness requires an append-only capture identity")
            print(json.dumps(
                produce_target_readiness(
                    args.target_readiness, args.readiness_capture_id,
                ), indent=2, sort_keys=True,
            ))
            return 0
        if args.readiness_capture_id is not None:
            raise GateError("readiness capture identity requires target readiness")
        if args.target_self_check is not None:
            manifest = _json_file(ROOT / "install-manifest.json", "installed payload manifest")
            verify_installed_payload(
                manifest.get("frameworkCommit"), args.target_self_check, ROOT, full=True,
            )
            if os.getuid() != 1007 or os.getgid() != 1007 or not {27, 998}.issubset(os.getgroups()):
                raise GateError("target self-check execution identity differs")
            print(json.dumps({
                "kind": "hotel-srv4-target-self-check-v1", "status": "pass",
                "manifestCanonicalSha256": args.target_self_check,
                "executionUid": 1007, "executionGid": 1007,
            }, sort_keys=True, separators=(",", ":")))
            return 0
        if args.status_campaign is not None:
            print(json.dumps(DetachedSshController().status(args.status_campaign), indent=2, sort_keys=True))
            return 0
        if args.capture_readiness_setup is not None:
            if args.capture_readiness_destination is None:
                raise GateError("readiness capture requires an exclusive destination")
            print(json.dumps(
                DetachedSshController().capture_readiness(
                    args.capture_readiness_setup, args.capture_readiness_destination,
                ), indent=2, sort_keys=True,
            ))
            return 0
        if args.capture_readiness_destination is not None:
            raise GateError("readiness capture destination requires a setup identity")
        if args.refetch_campaign is not None:
            if args.refetch_destination is None:
                raise GateError("refetch requires an exclusive destination")
            print(json.dumps(
                DetachedSshController().refetch_and_replay(
                    args.refetch_campaign, args.refetch_destination,
                ), indent=2, sort_keys=True,
            ))
            return 0
        if args.refetch_destination is not None:
            raise GateError("refetch destination requires a campaign")
        if args.supervise_admission is not None:
            if (
                args.execution_receipt is None or args.campaign_abort is None
                or args.lease_fd is None or args.resume_admission is not None
            ):
                raise GateError(
                    "target supervision requires its admission, receipt, abort, and inherited lease only"
                )
            try:
                result = supervise_target_controller(
                    args.supervise_admission, args.execution_receipt,
                    args.campaign_abort, args.lease_fd,
                )
            except Exception as exc:
                try:
                    retain_supervisor_boot_abort(
                        args.supervise_admission, args.execution_receipt,
                        args.campaign_abort, exc,
                    )
                    failed_admission = _json_file(
                        args.supervise_admission, "failed supervised admission",
                    )
                    failed_control = args.supervise_admission.parent
                    if not (failed_control / "terminal-tree-seal.json").exists():
                        _root_terminal_observation_and_seal(
                            failed_admission, failed_control,
                        )
                finally:
                    try:
                        fcntl.flock(args.lease_fd, fcntl.LOCK_UN)
                    except OSError:
                        pass
                    try:
                        os.close(args.lease_fd)
                    except OSError:
                        pass
                raise GateError(
                    f"target supervisor failed after terminal abort retention: {exc}"
                ) from exc
            # Do not append to controller.log after the root terminal-tree seal.
            # Status/refetch consume the retained root-owned receipts instead.
            return 0
        if args.campaign_abort is not None:
            raise GateError("a campaign abort path requires target supervision")
        if args.resume_admission is not None:
            if args.execution_receipt is None or args.lease_fd is None:
                raise GateError("target resume requires an execution receipt path and inherited lease")
            admission = _json_file(args.resume_admission, "target runtime admission")
            body = {key: value for key, value in admission.items() if key != "admissionCanonicalSha256"}
            binding = admission.get("bindings")
            if (
                not isinstance(binding, dict)
                or admission.get("admissionCanonicalSha256") != canonical_sha256(body)
                or admission.get("runtimeAuthorized") is not True
                or admission.get("externalMutationAuthorized") is not True
                or admission.get("promotionAuthorized") is not False
                or binding.get("target") != "fb14srv4"
                or binding.get("executionUser") != "fhuebscher"
                or binding.get("executionUid") != 1007
                or binding.get("executionGid") != 1007
                or binding.get("supplementalGids") != [27, 998]
                or binding.get("dockerGid") != 998
                or binding.get("checkoutRoot") != str(ROOT)
            ):
                raise GateError("target runtime admission or identity differs")
            verify_installed_payload(
                binding["frameworkCommit"],
                binding["installationManifestCanonicalSha256"], ROOT, full=True,
            )
            expected_receipt = Path(binding["artifactRoot"] + ".controller-result.json")
            if args.execution_receipt != expected_receipt or args.execution_receipt.exists():
                raise GateError("target execution receipt path differs or already exists")
            result = execute_campaign(admission, TargetComposeTransport(admission, args.lease_fd))
            payload = canonical_bytes(result) + b"\n"
            descriptor = os.open(
                args.execution_receipt,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            try:
                if os.write(descriptor, payload) != len(payload):
                    raise GateError("short write to target execution receipt")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.lease_fd is not None:
            raise GateError("an inherited lease descriptor requires target resume")
        required = {
            "framework-commit": args.framework_commit,
            "gate-plan": args.gate_plan,
            "gate-setup": args.gate_setup,
            "readiness": args.readiness,
            "readiness-artifact-parent": args.readiness_artifact_parent,
            "gate-run": args.gate_run,
            "admission-output": args.admission_output,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise GateError(f"local admission arguments are missing: {missing}")
        admission = admit_runtime(
            args.framework_commit, args.gate_plan, args.gate_setup, args.readiness,
            args.readiness_artifact_parent, args.gate_run,
        )
        if args.admission_output.exists():
            raise GateError("refusing to replace runtime admission")
        args.admission_output.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(admission, indent=2, sort_keys=True).encode() + b"\n"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(args.admission_output, flags, 0o600)
        except OSError as exc:
            raise GateError(f"cannot create exclusive runtime admission: {exc}") from exc
        try:
            if os.write(descriptor, payload) != len(payload):
                raise GateError("short write to runtime admission")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if args.launch_detached:
            result = DetachedSshController().launch(admission)
        else:
            result = {
                "runtimeAdmissionCreated": True,
                "executionStarted": False,
                "admissionCanonicalSha256": admission["admissionCanonicalSha256"],
            }
    except GateError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
