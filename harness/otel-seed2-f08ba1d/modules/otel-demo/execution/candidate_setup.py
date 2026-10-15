#!/usr/bin/env python3
"""Fail-closed setup controller for the srv6 OTel candidate.

Setup is unreachable while ``ADMITTED_STUDY_EPOCHS`` is empty: the v1 epoch is
UNSUPPORTED (its frozen ``none`` and ``selected`` postures are not structurally
realizable) and the v2 epoch is not admitted until the governed edit of that
tuple lands.  The reviewed allocation is retained as provenance either way.
"""
from __future__ import annotations

import argparse
import fcntl
import grp
import hashlib
import json
import os
import pwd
import re
import shutil
import socket
import stat
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
TARGET_HOST = "fb14srv6"
TRANSPORT_USER = "root"
EXECUTION_USER = "stig"
EXECUTION_UID = 1016
EXECUTION_GID = 1016
DOCKER_GID = 998
DOCKER_VERSION = "29.6.1"
UPSTREAM_COMMIT = "2d4661e4897aa7b2d2ddbb5ef8c4824ca8a1b88d"
RELEASE_PARENT = Path("/home/stig/observability-placement-candidate-v4-otel-srv6")
ARTIFACT_PARENT = Path("/home/stig/observability-placement-candidate-v4-runs")
LEASE_PATH = ARTIFACT_PARENT / ".srv6-runtime.lock"
PORTS = {
    "frontend": 18080,
    "frontendProxyOtlp": 18081,
    "grafana": 18082,
    "jaeger": 18083,
    "prometheus": 18084,
}


# Study epochs this installed controller may set up. The frozen v1 epoch is
# UNSUPPORTED: its byte-pinned descriptor's postureRealization says none and
# selected are unsupported. The v2 epoch (otel-demo-candidate-pilot-v2,
# change admit-otel-demo-candidate-pilot-v2) writes D13's no-telemetry-emitted
# reading into a new frozen descriptor and is the epoch this tuple is meant
# to admit. While it is empty every entry point refuses before reading a
# package, and candidate_runtime.admitted_study_epochs() reads this tuple live
# so the local chain refuses too. Admitting the epoch is a governed edit of
# this constant and of candidate_remote.ADMITTED_STUDY_EPOCHS (same tuple).
# v3 (four postures, research/otel-postures/DECLARATION.md in the main repo) is
# admitted in place of v2 (the tombstone names only the current epoch); the same
# tuple as candidate_remote.ADMITTED_STUDY_EPOCHS.
# The offpath epoch (research/otel-offpath/DECLARATION.md in the main repo)
# replaces v3; the same tuple as candidate_remote.ADMITTED_STUDY_EPOCHS.
# The traffic-sweep epoch (otel-traffic-sweep-v1, main repo research/traffic-sweep/DECLARATION_OTEL.md, frozen
# 2026-10-03) replaces offpath in the tombstone, in the same commit that adds execution/study-epoch.json: like
# v3 -> offpath, the tombstone names only the current epoch.  Removing both restores offpath.
# The quiet calibration epoch (otel-quiet-calibration-v1, main repo research/PROTOCOL_DRAFT_20261002.md decision 48)
# replaces the sweep in the tombstone, in the same commit that points execution/study-epoch.json at it (2026-10-04);
# the sweep (relaunch 1 terminal-valid 12/12) keeps its compiler, descriptor and digests and is re-admitted by
# naming it here and in the selector again.
# The repeat-episodes epoch (otel-repeat-episodes-v1, campaign B, decisions 49/50) replaces the quiet epoch in the tombstone, in the
# same commit that points execution/study-epoch.json at it (2026-10-09); the quiet epoch (relaunch 1 attempt 2) keeps its compiler,
# descriptor and digests and is re-admitted by naming it here and in the selector again.
# The quiet calibration epoch is re-admitted for run A2 (main repo research/PROTOCOL_DRAFT_20261002.md decision 68; attempt 3 after
# attempts 1 and 2 are spent) by naming it here and in the selector again (2026-10-10); campaign B (otel-repeat-episodes-v1) is terminal.
# Campaign C (otel-repeat-episodes-c-v1, main repo research/PROTOCOL_DRAFT_20261002.md decision 82, BUDGET_C.md) replaces the quiet
# epoch in the tombstone, in the same commit that points execution/study-epoch.json at it (2026-10-11); quiet run A2 (attempt 3) is
# terminal, and every earlier epoch keeps its compiler, descriptor and digests.
# The load pilot (otel-load-pilot-v1, main repo research/traffic-sweep/BUDGET_D.md amendment 1) replaces campaign C in the tombstone, in
# the same commit that points execution/study-epoch.json at it (2026-10-12); C attempt 1 is terminal and recorded spent, and every
# earlier epoch keeps its compiler, descriptor and digests.
# The off-path manifestation pilot (otel-offpath-pilot-v1, main repo research/traffic-sweep/BUDGET_E.md) replaces the load pilot in the
# tombstone, in the same commit that points execution/study-epoch.json at it (2026-10-13); the load pilot's attempt 1 is terminal
# and recorded spent (ba27afc), and every earlier epoch keeps its compiler, descriptor and digests.
# The second off-path pilot (otel-offpath-pilot-v2, BUDGET_E amendment 1, decision 108) replaces v1 in the tombstone, in the same commit that
# points execution/study-epoch.json at it (2026-10-12); v1 attempt 1 is terminal and recorded spent (12b626a), and every earlier epoch keeps its
# compiler, descriptor and digests.
# Campaign E (otel-offpath-e-v1, main repo research/traffic-sweep/BUDGET_E.md and DECLARATION_E_OTEL.md) replaces the second off-path pilot in the
# tombstone, in the same commit that points execution/study-epoch.json at it (2026-10-13); pilot v2 attempt 1 is terminal and recorded spent
# (c547ebb), and every earlier epoch keeps its compiler, descriptor and digests.
# 2026-10-14: campaign F (otel-offpath-f-v1) replaces campaign E in the tombstone, in the same commit that points
# execution/study-epoch.json at it; E attempt 1 is recorded spent (e58580a).
ADMITTED_STUDY_EPOCHS: tuple[str, ...] = ("otel-offpath-f-v1",)
# Study epochs whose package shape this controller understands. Knowing an
# epoch is not admitting it: a package for a known-but-unadmitted epoch is
# parsed exactly and then refused by refuse_unsupported.
KNOWN_STUDY_EPOCHS = ("otel-demo-offpath-v1",)
UNSUPPORTED_STUDY_EPOCHS = ("otel-demo-candidate-pilot-v1",)
# The installed controller set the setup receipt binds; mirrors
# candidate_runtime.CONTROLLER_PATHS exactly (tested) so a transported package
# cannot widen or narrow what is digested.
FIXED_CONTROLLER_PATHS = {
    "candidate-compiler": "modules/otel-demo/execution/candidate_pilot.py",
    "runtime-admission": "modules/otel-demo/execution/candidate_runtime.py",
    "remote-setup-controller": "modules/otel-demo/execution/candidate_setup.py",
    "remote-compose-controller": "modules/otel-demo/execution/candidate_remote.py",
    "candidate-terminal": "modules/otel-demo/validation/candidate_terminal.py",
    "unsupported-disposition": "modules/otel-demo/validation/candidate_unsupported.py",
    "materializer": "modules/otel-demo/materialize.py",
    "workload": "modules/otel-demo/workload.py",
    "posture-catalog": "modules/otel-demo/postures/catalog.json",
    "target-contract": "modules/otel-demo/execution/candidate-target-allocation.json",
    "base-compose-overlay": "modules/otel-demo/deployment/compose.otel-placement.yml",
    "candidate-posture-overlay": "modules/otel-demo/deployment/compose.candidate-postures.yml",
}


# A parameterised epoch swaps the compiler and adds its own digest-bound inputs; mirrors
# candidate_runtime.EPOCH_CONTROLLER_PATHS exactly (tested).  The frozen epoch's set above is unchanged.
EPOCH_CONTROLLER_PATHS = {
    "otel-traffic-sweep-v1": {
        "candidate-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "candidate-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-04: the quiet calibration epoch (candidate_quiet.py) reads the sweep compiler and its descriptor too.
    "otel-quiet-calibration-v1": {
        "candidate-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "candidate-descriptor": "pipelines/campaigns/otel-quiet-calibration-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-09: the repeat-episodes epoch (candidate_repeat.py, campaign B) reads the sweep pair and the quiet compiler too.
    "otel-repeat-episodes-v1": {
        "candidate-compiler": "modules/otel-demo/execution/candidate_repeat.py",
        "candidate-descriptor": "pipelines/campaigns/otel-repeat-episodes-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "quiet-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-11: campaign C (candidate_repeat_c.py, decision 82) reads B's compiler and descriptor too.
    "otel-repeat-episodes-c-v1": {
        "candidate-compiler": "modules/otel-demo/execution/candidate_repeat_c.py",
        "candidate-descriptor": "pipelines/campaigns/otel-repeat-episodes-c-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "quiet-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "repeat-compiler": "modules/otel-demo/execution/candidate_repeat.py",
        "repeat-descriptor": "pipelines/campaigns/otel-repeat-episodes-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-12: the load pilot (candidate_load_pilot.py, BUDGET_D.md amendment 1) reads C's compiler and descriptor too.
    "otel-load-pilot-v1": {
        "candidate-compiler": "modules/otel-demo/execution/candidate_load_pilot.py",
        "candidate-descriptor": "pipelines/campaigns/otel-load-pilot-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "quiet-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "repeat-compiler": "modules/otel-demo/execution/candidate_repeat.py",
        "repeat-descriptor": "pipelines/campaigns/otel-repeat-episodes-v1.json",
        "repeat-c-compiler": "modules/otel-demo/execution/candidate_repeat_c.py",
        "repeat-c-descriptor": "pipelines/campaigns/otel-repeat-episodes-c-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-13: the off-path pilot (candidate_offpath_pilot.py, BUDGET_E.md) reads C's compiler and descriptor too.
    "otel-offpath-pilot-v1": {
        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_pilot.py",
        "candidate-descriptor": "pipelines/campaigns/otel-offpath-pilot-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "quiet-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "repeat-compiler": "modules/otel-demo/execution/candidate_repeat.py",
        "repeat-descriptor": "pipelines/campaigns/otel-repeat-episodes-v1.json",
        "repeat-c-compiler": "modules/otel-demo/execution/candidate_repeat_c.py",
        "repeat-c-descriptor": "pipelines/campaigns/otel-repeat-episodes-c-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-12: the second off-path pilot (candidate_offpath_pilot_v2.py, BUDGET_E amendment 1) reads C's compiler and descriptor too.
    "otel-offpath-pilot-v2": {
        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_pilot_v2.py",
        "candidate-descriptor": "pipelines/campaigns/otel-offpath-pilot-v2.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "quiet-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "repeat-compiler": "modules/otel-demo/execution/candidate_repeat.py",
        "repeat-descriptor": "pipelines/campaigns/otel-repeat-episodes-v1.json",
        "repeat-c-compiler": "modules/otel-demo/execution/candidate_repeat_c.py",
        "repeat-c-descriptor": "pipelines/campaigns/otel-repeat-episodes-c-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-12: campaign E (candidate_offpath_e.py, BUDGET_E) reads C's compiler and descriptor too; the tombstone below does not name it yet.
    "otel-offpath-e-v1": {
        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_e.py",
        "candidate-descriptor": "pipelines/campaigns/otel-offpath-e-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "quiet-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "repeat-compiler": "modules/otel-demo/execution/candidate_repeat.py",
        "repeat-descriptor": "pipelines/campaigns/otel-repeat-episodes-v1.json",
        "repeat-c-compiler": "modules/otel-demo/execution/candidate_repeat_c.py",
        "repeat-c-descriptor": "pipelines/campaigns/otel-repeat-episodes-c-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-14: campaign F (candidate_offpath_f.py, BUDGET_F) reads C's compiler and descriptor too; the tombstone below does not name it.
    "otel-offpath-f-v1": {
        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_f.py",
        "candidate-descriptor": "pipelines/campaigns/otel-offpath-f-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "quiet-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "repeat-compiler": "modules/otel-demo/execution/candidate_repeat.py",
        "repeat-descriptor": "pipelines/campaigns/otel-repeat-episodes-v1.json",
        "repeat-c-compiler": "modules/otel-demo/execution/candidate_repeat_c.py",
        "repeat-c-descriptor": "pipelines/campaigns/otel-repeat-episodes-c-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
}


def controller_paths(study_epoch: str) -> dict[str, str]:
    """The installed controller set the setup receipt binds for one study epoch."""
    return {**FIXED_CONTROLLER_PATHS, **EPOCH_CONTROLLER_PATHS.get(study_epoch, {})}


class SetupFailure(RuntimeError):
    pass


def refuse_unsupported(operation: str, study_epoch: str | None = None) -> None:
    """Fail closed unless ``study_epoch`` is an admitted epoch.

    With no admitted epoch at all this refuses before any package is read, which
    is the tombstone behaviour of the UNSUPPORTED v1 epoch. Once an epoch is
    admitted the package's own ``studyEpoch`` decides.
    """
    if not ADMITTED_STUDY_EPOCHS or study_epoch not in ADMITTED_STUDY_EPOCHS:
        epoch = study_epoch if isinstance(study_epoch, str) else UNSUPPORTED_STUDY_EPOCHS[0]
        raise SetupFailure(
            f"{operation} refused: {epoch} is UNSUPPORTED; "
            "no setup, target mutation, or full-only execution is allowed"
        )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise SetupFailure(f"non-canonical setup value: {exc}") from exc


def digest(path: Path) -> str:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise SetupFailure(f"{path} is not a regular non-symlink file")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise SetupFailure(f"cannot read {path}: {exc}") from exc
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise SetupFailure(f"{path} changed while read")
    return hashlib.sha256(payload).hexdigest()


def source_tree_sha256(root: Path) -> str:
    value = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts and path.name != ".source.sha256":
            relative = str(path.relative_to(root)).encode()
            payload = path.read_bytes()
            value.update(len(relative).to_bytes(8, "big")); value.update(relative)
            value.update(stat.S_IMODE(path.stat().st_mode).to_bytes(4, "big"))
            value.update(len(payload).to_bytes(8, "big")); value.update(payload)
    return value.hexdigest()


def frozen_source_tree_sha256(root: Path) -> str:
    value = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts and path.name != ".source.sha256":
            relative = str(path.relative_to(root)).encode()
            payload = path.read_bytes()
            projected_mode = 0o555 if stat.S_IMODE(path.stat().st_mode) & 0o111 else 0o444
            value.update(len(relative).to_bytes(8, "big")); value.update(relative)
            value.update(projected_mode.to_bytes(4, "big"))
            value.update(len(payload).to_bytes(8, "big")); value.update(payload)
    return value.hexdigest()


def safe_absolute(value: Any, where: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise SetupFailure(f"unsafe {where}")
    pure = PurePosixPath(value)
    if not pure.is_absolute() or str(pure) != value or any(part in {"", ".", ".."} for part in pure.parts):
        raise SetupFailure(f"unsafe {where}")
    return Path(value)


def read_json(path: Path, where: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(SetupFailure(f"non-finite {value}")))
    except SetupFailure:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SetupFailure(f"cannot read {where}: {exc}") from exc
    if not isinstance(value, dict):
        raise SetupFailure(f"{where} is not an object")
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def command(
    argv: Sequence[str], *, cwd: Path | None = None,
    env: Mapping[str, str] | None = None, timeout: int = 120, check: bool = True,
) -> subprocess.CompletedProcess[str]:
    # UTF-8 with replacement: build, pull and inspect output is bytes, not guaranteed UTF-8 (the class that cost
    # Hotel's sweep1 attempt 2 its campaign, 2026-10-03); for valid UTF-8 the text is unchanged.
    result = subprocess.run(
        list(argv), cwd=cwd, env=None if env is None else dict(env), encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False,
    )
    if check and result.returncode:
        raise SetupFailure(f"{argv[0]} failed ({result.returncode}): {result.stderr.strip()}")
    return result


def _under(child: Path, parent: Path, where: str) -> None:
    try:
        relative = child.relative_to(parent)
    except ValueError as exc:
        raise SetupFailure(f"{where} escapes its registered parent") from exc
    if not relative.parts:
        raise SetupFailure(f"{where} must be a child of its registered parent")


def validate_package(document: Mapping[str, Any], staging: Path) -> dict[str, Any]:
    required = {
        "schemaVersion", "kind", "campaignId", "studyEpoch", "frameworkCommit",
        "gatePlanSha256", "gateSetupSha256", "targetContractSha256",
        "target", "executionIdentity", "repositoryBundleSha256",
        "upstreamBundleSha256", "upstreamCommit", "releaseRoot",
        "repositoryRoot", "remoteSourceRoot", "remoteArtifactRoot",
        "setupStagingRoot", "leasePath", "composeProject", "ports",
        "controllerDigests", "expectedMaterializedSourceSha256", "oneShot",
        "readinessProbeAuthorized", "runtimeAuthorized", "promotionAuthorized",
    }
    if set(document) != required or document.get("schemaVersion") != 1 or document.get("kind") != "otel-demo-candidate-setup-package-v1":
        raise SetupFailure("setup package shape differs")
    if document.get("studyEpoch") not in KNOWN_STUDY_EPOCHS + ADMITTED_STUDY_EPOCHS + UNSUPPORTED_STUDY_EPOCHS:
        raise SetupFailure("setup package names an unknown study epoch")
    if (
        document.get("target") != {"host": TARGET_HOST, "transportUser": TRANSPORT_USER, "setupUser": TRANSPORT_USER}
        or document.get("executionIdentity") != {"user": EXECUTION_USER, "uid": EXECUTION_UID, "gid": EXECUTION_GID, "supplementalGids": [DOCKER_GID]}
        or document.get("upstreamCommit") != UPSTREAM_COMMIT
        or document.get("ports") != PORTS
        or document.get("oneShot") is not True
        or document.get("readinessProbeAuthorized") is not True
        or document.get("runtimeAuthorized") is not False
        or document.get("promotionAuthorized") is not False
        or SAFE_NAME.fullmatch(str(document.get("campaignId"))) is None
        or SAFE_NAME.fullmatch(str(document.get("composeProject"))) is None
        or HEX40.fullmatch(str(document.get("frameworkCommit"))) is None
        or any(HEX64.fullmatch(str(document.get(key))) is None for key in (
            "gatePlanSha256", "gateSetupSha256", "targetContractSha256",
            "repositoryBundleSha256", "upstreamBundleSha256",
            "expectedMaterializedSourceSha256",
        ))
    ):
        raise SetupFailure("setup package identity or authority differs")
    release = safe_absolute(document["releaseRoot"], "release root")
    repository = safe_absolute(document["repositoryRoot"], "repository root")
    source = safe_absolute(document["remoteSourceRoot"], "source root")
    artifacts = safe_absolute(document["remoteArtifactRoot"], "artifact root")
    package_staging = safe_absolute(document["setupStagingRoot"], "setup staging root")
    lease = safe_absolute(document["leasePath"], "lease path")
    _under(release, RELEASE_PARENT, "release root")
    _under(artifacts, ARTIFACT_PARENT, "artifact root")
    _under(package_staging, ARTIFACT_PARENT, "setup staging root")
    if repository != release / "repository" or source != release / "source" or lease != LEASE_PATH or package_staging != staging:
        raise SetupFailure("derived setup paths differ")
    controllers = document["controllerDigests"]
    if not isinstance(controllers, dict) or not controllers or any(HEX64.fullmatch(str(value)) is None for value in controllers.values()):
        raise SetupFailure("controller digest population differs")
    return dict(document)


def validate_local_identity(*, host: str | None = None, euid: int | None = None) -> None:
    observed_host = socket.gethostname() if host is None else host
    observed_euid = os.geteuid() if euid is None else euid
    if observed_host != TARGET_HOST or observed_euid != 0:
        raise SetupFailure("setup controller is not root on the reviewed host")
    account = pwd.getpwnam(EXECUTION_USER)
    docker_group = grp.getgrgid(DOCKER_GID)
    groups = os.getgrouplist(EXECUTION_USER, account.pw_gid)
    if account.pw_uid != EXECUTION_UID or account.pw_gid != EXECUTION_GID or DOCKER_GID not in groups or docker_group.gr_gid != DOCKER_GID:
        raise SetupFailure("registered execution identity or Docker group differs")


def docker_inventory() -> dict[str, Any]:
    projects_raw = command(["docker", "compose", "ls", "--all", "--format", "json"], check=False).stdout.strip()
    try:
        projects = json.loads(projects_raw or "[]")
    except json.JSONDecodeError as exc:
        raise SetupFailure("Docker Compose inventory is not JSON") from exc
    if not isinstance(projects, list):
        raise SetupFailure("Docker Compose inventory is not a list")
    rows = sorted(
        ({"name": str(row.get("Name", "")), "status": str(row.get("Status", "")), "configFiles": str(row.get("ConfigFiles", ""))} for row in projects if isinstance(row, dict)),
        key=lambda row: (row["name"], row["configFiles"]),
    )
    running = sorted(line for line in command(["docker", "ps", "-q"], check=False).stdout.splitlines() if line)
    volumes = sorted(line for line in command(["docker", "volume", "ls", "-q"], check=False).stdout.splitlines() if line)
    return {"composeProjects": rows, "runningContainers": running, "volumes": volumes}


def assert_no_active_foreign(inventory: Mapping[str, Any]) -> None:
    active_projects = [row for row in inventory["composeProjects"] if "running" in row["status"].lower()]
    if inventory["runningContainers"] or active_projects:
        raise SetupFailure("foreign active containers or Compose projects are present")


PORT_TEARDOWN_WAIT_SECONDS = 30


def ports_free(ports: Sequence[int], *, wait_seconds: int = PORT_TEARDOWN_WAIT_SECONDS) -> None:
    """Refuse unless every reserved port is free of an actual listener.

    Hotel lesson 8 (fixed there in 42ac455, ported here before it can bite):
    this probe used to bind with SO_REUSEADDR explicitly *disabled*, which
    makes a port in TIME_WAIT -- owned by nobody, accepting nothing, left
    behind by our own previous teardown -- indistinguishable from a foreign
    listener. On Linux SO_REUSEADDR still refuses to bind over a socket that
    is actually LISTENing on the same address, so enabling it keeps the check
    that matters and drops only the false positive. The bounded retry covers
    the narrower race where a Compose project is still unpublishing.
    """
    deadline = time.monotonic() + max(0, int(wait_seconds))
    while True:
        occupied: list[int] = []
        sockets: list[socket.socket] = []
        try:
            for port in ports:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(("0.0.0.0", int(port)))
                except OSError:
                    occupied.append(int(port))
                    sock.close()
                else:
                    sockets.append(sock)
        finally:
            for sock in sockets:
                sock.close()
        if not occupied:
            return
        if time.monotonic() >= deadline:
            raise SetupFailure(f"reserved port is occupied: {occupied}")
        time.sleep(1.0)


def _group_name(gid: int, what: str) -> str:
    """Spell a gid the way `runuser` demands, without loosening the contract.

    `runuser(1)` from util-linux 2.36.1 (Debian bullseye, all three hosts)
    rejects a numeric `--group`/`--supp-group` with "group <gid> does not
    exist" even when that gid is present in /etc/group -- measured on
    fb14srv6 2026-09-15, where `--group 1016` fails and `--group stig`
    succeeds for the same account. The numeric gid stays the contract (it is
    pinned in the descriptor and already verified against the account by
    `_require_execution_identity`); this only chooses how it is spelled.
    """
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError as exc:
        raise SetupFailure(
            f"{what} gid {gid} has no group entry on this host"
        ) from exc


def run_as_stig(argv: Sequence[str], *, cwd: Path, environment: Mapping[str, str] | None = None, timeout: int = 3600) -> subprocess.CompletedProcess[str]:
    prefix = [
        "runuser", "--user", EXECUTION_USER,
        "--group", _group_name(EXECUTION_GID, "execution"),
        "--supp-group", _group_name(DOCKER_GID, "docker"), "--",
    ]
    if environment:
        prefix.extend(["env", *[f"{key}={value}" for key, value in sorted(environment.items())]])
    return command([*prefix, *argv], cwd=cwd, timeout=timeout)


def compose_argv(source: Path, project: str, *arguments: str) -> list[str]:
    return [
        "docker", "compose", "-p", project,
        "-f", str(source / "docker-compose.obsplacement.yml"),
        "-f", str(source / "compose.otel-placement.yml"),
        "-f", str(source / "compose.candidate-postures.yml"),
        *arguments,
    ]


# Enabled values of the agent-clearing overlay variables. These are the exact
# upstream image ENV values (materialize.py AGENT_ENVIRONMENT verifies them
# against the pinned Dockerfiles at materialization); the install-time
# ``compose pull/build/config`` renders the full posture, so it supplies them.
FULL_POSTURE_AGENT_ENVIRONMENT = {
    "OTEL_CANDIDATE_ADSERVICE_JAVA_TOOL_OPTIONS": "-javaagent:/usr/src/app/opentelemetry-javaagent.jar",
    "OTEL_CANDIDATE_FRAUDDETECTIONSERVICE_JAVA_TOOL_OPTIONS": "-javaagent:/app/opentelemetry-javaagent.jar",
    "OTEL_CANDIDATE_KAFKA_KAFKA_OPTS": "-javaagent:/tmp/opentelemetry-javaagent.jar -Dotel.jmx.target.system=kafka-broker",
    "OTEL_CANDIDATE_FLAGD_OTEL_COLLECTOR_URI": "otelcol:4317",
    "OTEL_CANDIDATE_FLAGD_METRICS_EXPORTER": "otel",
}


# 2026-10-14 (campaign F): the install-time full-posture environment carries the metric export interval exactly when the materialized posture
# overlay binds it (materialize.render_posture_overlay renders the binding for the campaign-F epoch only); a bound overlay without the value
# fails closed at ``compose config`` (the overlay's ``:?``).  candidate_runtime.METRIC_EXPORT_INTERVAL_MILLISECONDS is the same statement.
METRIC_EXPORT_INTERVAL_VARIABLE = "OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"
METRIC_EXPORT_INTERVAL_MILLISECONDS = "5000"


def compose_environment(source: Path, source_digest: str) -> dict[str, str]:
    catalog = read_json(source / "candidate-posture-contract.json", "posture catalog")
    environment = {
        "DEMO_VERSION": "1.12.0",
        "ENVOY_PORT": str(PORTS["frontend"]),
        "FRONTEND_PROXY_OTLP_HOST_PORT": str(PORTS["frontendProxyOtlp"]),
        "GRAFANA_HOST_PORT": str(PORTS["grafana"]),
        "JAEGER_HOST_PORT": str(PORTS["jaeger"]),
        "PROMETHEUS_HOST_PORT": str(PORTS["prometheus"]),
        "OTEL_PLACEMENT_ENABLED": "true", "OTEL_PLACEMENT_DISABLED": "false",
        "OTEL_IMAGE_TAG": f"1.12.0-{source_digest[:16]}",
        "OTEL_CANDIDATE_ENVOY_CONFIG": str(source / "src/frontendproxy/envoy.tmpl.yaml"),
        "OTEL_CANDIDATE_IMAGEPROVIDER_NGINX_TEMPLATE": str(source / "src/imageprovider/nginx.conf.template"),
    }
    environment.update(FULL_POSTURE_AGENT_ENVIRONMENT)
    for service in catalog["applicationServices"]:
        key = service.replace("-", "_").upper()
        environment[f"OTEL_CANDIDATE_{key}_DISABLED"] = "false"
        environment[f"OTEL_CANDIDATE_{key}_ENABLED"] = "true"
        environment[f"OTEL_CANDIDATE_{key}_EXPORTER"] = "otlp"
    overlay = source / "compose.candidate-postures.yml"
    if overlay.is_file() and "${" + METRIC_EXPORT_INTERVAL_VARIABLE + ":?" in overlay.read_text(encoding="utf-8"):
        environment[METRIC_EXPORT_INTERVAL_VARIABLE] = METRIC_EXPORT_INTERVAL_MILLISECONDS
    return environment


def image_ids(source: Path, project: str, environment: Mapping[str, str]) -> dict[str, str]:
    config = run_as_stig(compose_argv(source, project, "config", "--format", "json"), cwd=source, environment=environment)
    try:
        document = json.loads(config.stdout)
    except json.JSONDecodeError as exc:
        raise SetupFailure("rendered Compose config is not JSON") from exc
    catalog = read_json(source / "candidate-posture-contract.json", "posture catalog")
    services = document.get("services", {})
    result: dict[str, str] = {}
    for service in catalog["applicationServices"]:
        reference = (services.get(service) or {}).get("image")
        if not isinstance(reference, str) or not reference:
            raise SetupFailure(f"rendered Compose image is absent for {service}")
        identifier = run_as_stig(["docker", "image", "inspect", "--format", "{{.Id}}", reference], cwd=source).stdout.strip()
        if IMAGE_ID.fullmatch(identifier) is None:
            raise SetupFailure(f"built image ID is invalid for {service}")
        result[service] = identifier
    return result


def _freeze_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_symlink():
            raise SetupFailure("installed source contains an unexpected symlink")
        mode = stat.S_IMODE(path.stat().st_mode)
        if path.is_dir():
            path.chmod(0o555)
        elif mode & 0o111:
            path.chmod(0o555)
        else:
            path.chmod(0o444)
    root.chmod(0o555)


# Hotel lesson 3, ported before it can bite. The install runs under root's
# LOGIN SHELL on fb14srv6, whose umask is 077 (measured 2026-09-12, same as
# fb14srv4). Every mode passed to mkdir() is masked by it, so `mkdir(0o755)`
# silently produces 0700 and the execution identity cannot traverse into the
# release it is supposed to run from. On fb14srv4 that surfaced three gates
# later as a `campaign-path-ownership` readiness failure and cost a launch
# attempt (fixed there in 0413191).
#
# Three defences, because the umask is not the only way a mode can be wrong:
#   1. set the process umask explicitly, so nothing inherits 077;
#   2. chmod each directory after creating it, so a wrong mode cannot survive
#      even if the umask were changed again underneath us;
#   3. re-read and VERIFY the modes, so a silently-wrong mode fails the
#      install rather than the readiness gate.
INSTALL_UMASK = 0o022
EXPECTED_DIRECTORY_MODES = {
    "releaseParent": 0o755,
    "artifactParent": 0o755,
    "releaseRoot": 0o755,
    "repositoryRoot": 0o755,
    "remoteArtifactRoot": 0o750,
    "controllerRoot": 0o750,
}


def enforce_directory_mode(path: Path, mode: int, where: str) -> None:
    """chmod then re-read; a directory whose mode did not take fails closed."""
    if path.is_symlink() or not path.is_dir():
        raise SetupFailure(f"{where} is not an exact directory")
    os.chmod(path, mode)
    observed = stat.S_IMODE(path.lstat().st_mode)
    if observed != mode:
        raise SetupFailure(
            f"{where} mode is {observed:04o}, not the required {mode:04o}"
        )


def verify_execution_identity_can_traverse(paths: Sequence[Path]) -> None:
    """Prove, as the execution identity itself, that each path is traversable.

    A mode check answers "are the bits right"; this answers the question the
    campaign actually depends on, the way Hotel's readiness seam eventually
    did -- but at install time, where the failure is cheap.
    """
    for path in paths:
        probe = subprocess.run(
            ["runuser", "--user", EXECUTION_USER, "--", "test", "-x", str(path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        if probe.returncode != 0:
            raise SetupFailure(
                f"{EXECUTION_USER} cannot traverse {path} after install"
            )


def install(document: Mapping[str, Any], staging: Path) -> dict[str, Any]:
    if not ADMITTED_STUDY_EPOCHS:
        refuse_unsupported("candidate setup")
    package = validate_package(document, staging)
    refuse_unsupported("candidate setup", package["studyEpoch"])
    validate_local_identity()
    os.umask(INSTALL_UMASK)  # see INSTALL_UMASK: root's zsh login shell is 077
    started_at = now_iso()
    repository_bundle = staging / "framework.bundle"
    upstream_bundle = staging / "opentelemetry-demo.bundle"
    if digest(repository_bundle) != package["repositoryBundleSha256"] or digest(upstream_bundle) != package["upstreamBundleSha256"]:
        raise SetupFailure("transferred Git bundle bytes differ")
    if digest(staging / "candidate_setup.py") != package["controllerDigests"].get("remote-setup-controller"):
        raise SetupFailure("setup controller bytes differ")
    release = Path(package["releaseRoot"])
    repository = Path(package["repositoryRoot"])
    source = Path(package["remoteSourceRoot"])
    artifacts = Path(package["remoteArtifactRoot"])
    marker = staging / ".setup-attempt-started"
    if marker.exists() or marker.is_symlink():
        raise SetupFailure("one-shot setup was already attempted")
    marker.write_text(now_iso() + "\n", encoding="ascii")
    for path in (release, artifacts):
        if path.exists() or path.is_symlink():
            raise SetupFailure("release or artifact root is not absent")
    for parent, key in ((RELEASE_PARENT, "releaseParent"), (ARTIFACT_PARENT, "artifactParent")):
        parent.mkdir(parents=True, exist_ok=True)
        enforce_directory_mode(parent, EXPECTED_DIRECTORY_MODES[key], str(parent))
    before = docker_inventory()
    assert_no_active_foreign(before)
    ports_free(list(PORTS.values()))
    LEASE_PATH.touch(mode=0o660, exist_ok=True)
    os.chown(LEASE_PATH, 0, EXECUTION_GID)
    os.chmod(LEASE_PATH, 0o660)
    with LEASE_PATH.open("a+") as lease:
        try:
            fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SetupFailure("shared srv6 runtime lease is held") from exc
        release.mkdir(mode=0o755)
        enforce_directory_mode(release, EXPECTED_DIRECTORY_MODES["releaseRoot"], str(release))
        command(["git", "clone", "--no-checkout", str(repository_bundle), str(repository)], timeout=600)
        enforce_directory_mode(repository, EXPECTED_DIRECTORY_MODES["repositoryRoot"], str(repository))
        command(["git", "-C", str(repository), "checkout", "--detach", package["frameworkCommit"]], timeout=300)
        upstream = repository / "upstream/opentelemetry-demo"
        if upstream.exists() and any(upstream.iterdir()):
            raise SetupFailure("repository bundle carried unreviewed submodule worktree bytes")
        upstream.mkdir(parents=True, exist_ok=True)
        command(["git", "clone", "--no-checkout", str(upstream_bundle), str(upstream)], timeout=600)
        command(["git", "-C", str(upstream), "checkout", "--detach", UPSTREAM_COMMIT], timeout=300)
        if command(["git", "-C", str(repository), "rev-parse", "HEAD"]).stdout.strip() != package["frameworkCommit"]:
            raise SetupFailure("installed framework commit differs")
        if command(["git", "-C", str(upstream), "rev-parse", "HEAD"]).stdout.strip() != UPSTREAM_COMMIT:
            raise SetupFailure("installed upstream commit differs")
        command(["/usr/bin/python3", "-I", str(repository / "modules/otel-demo/materialize.py"), "--out", str(source)], timeout=600)
        source_sha = frozen_source_tree_sha256(source)
        if source_sha != package["expectedMaterializedSourceSha256"]:
            raise SetupFailure("projected frozen source digest differs from GATE-PLAN")
        (source / ".source.sha256").write_text(source_sha, encoding="ascii")
        environment = compose_environment(source, source_sha)
        run_as_stig(compose_argv(source, package["composeProject"], "pull", "--ignore-buildable"), cwd=source, environment=environment)
        run_as_stig(
            compose_argv(
                source, package["composeProject"], "build",
                "frontendproxy", "frontend", "recommendationservice",
                # Source-placement-guarded in-code-SDK services (SOURCE_PLACEMENT_GUARD_FILES):
                # a local build is the only way the patched source, not the pulled ghcr
                # image, is what the container actually runs.
                "cartservice", "checkoutservice", "currencyservice",
                "productcatalogservice", "shippingservice",
            ),
            cwd=source, environment=environment,
        )
        images = image_ids(source, package["composeProject"], environment)
        after = docker_inventory()
        assert_no_active_foreign(after)
        if before["volumes"] != after["volumes"]:
            raise SetupFailure("setup changed the foreign volume inventory")
        # Validate the installed fixed files without accepting paths from the
        # transported package.
        expected_paths = controller_paths(package["studyEpoch"])
        installed = {name: digest(repository / relative) for name, relative in expected_paths.items()}
        if set(package["controllerDigests"]) != set(expected_paths):
            raise SetupFailure("controller digest population differs from the fixed controller set")
        for name, observed in installed.items():
            if package["controllerDigests"].get(name) != observed:
                raise SetupFailure(f"installed controller bytes differ for {name}")
        _freeze_tree(source)
        observed_frozen_sha = source_tree_sha256(source)
        marker_path = source / ".source.sha256"
        if observed_frozen_sha != source_sha or stat.S_IMODE(marker_path.stat().st_mode) != 0o444:
            raise SetupFailure("frozen materialized source digest differs from GATE-PLAN")
        (artifacts / ".controller").mkdir(parents=True, mode=0o750)
        shutil.copy2(repository / "modules/otel-demo/execution/candidate_remote.py", artifacts / ".controller/candidate_remote.py")
        os.chown(artifacts, EXECUTION_UID, EXECUTION_GID)
        os.chown(artifacts / ".controller", EXECUTION_UID, EXECUTION_GID)
        os.chown(artifacts / ".controller/candidate_remote.py", EXECUTION_UID, EXECUTION_GID)
        enforce_directory_mode(artifacts, EXPECTED_DIRECTORY_MODES["remoteArtifactRoot"], str(artifacts))
        enforce_directory_mode(
            artifacts / ".controller", EXPECTED_DIRECTORY_MODES["controllerRoot"],
            str(artifacts / ".controller"),
        )
        os.chmod(artifacts / ".controller/candidate_remote.py", 0o640)
        # The execution identity must be able to reach BOTH trees it runs
        # from: the frozen source under the release root (Compose context)
        # and its own artifact root. Proven here, as that identity, while the
        # install can still be abandoned cheaply.
        verify_execution_identity_can_traverse(
            (RELEASE_PARENT, release, source, ARTIFACT_PARENT, artifacts, artifacts / ".controller")
        )
        receipt = {
            "schemaVersion": 1,
            "kind": "otel-demo-candidate-setup-receipt-v1",
            "campaignId": package["campaignId"],
            "target": package["target"],
            "executionIdentity": package["executionIdentity"],
            "frameworkCommit": package["frameworkCommit"],
            "upstreamCommit": UPSTREAM_COMMIT,
            "gatePlanSha256": package["gatePlanSha256"],
            "gateSetupSha256": package["gateSetupSha256"],
            "targetContractSha256": package["targetContractSha256"],
            "repositoryBundleSha256": package["repositoryBundleSha256"],
            "upstreamBundleSha256": package["upstreamBundleSha256"],
            "releaseRoot": str(release), "repositoryRoot": str(repository),
            "remoteSourceRoot": str(source), "remoteArtifactRoot": str(artifacts),
            "leasePath": str(LEASE_PATH), "composeProject": package["composeProject"],
            "ports": PORTS, "materializedSourceSha256": source_sha,
            "imageIds": images, "installedControllerDigests": installed,
            "dockerVersion": command(["docker", "version", "--format", "{{.Server.Version}}"] ).stdout.strip(),
            "dockerGid": grp.getgrnam("docker").gr_gid,
            "foreignInventoryBefore": before, "foreignInventoryAfter": after,
            "foreignVolumesPreserved": before["volumes"] == after["volumes"],
            "activeForeignResourcesAbsent": True,
            "containersStarted": False, "cellsRun": 0,
            "runtimeAuthorized": False, "promotionAuthorized": False,
            "startedAt": started_at,
            "completedAt": now_iso(),
        }
        if receipt["dockerVersion"] != DOCKER_VERSION or receipt["dockerGid"] != DOCKER_GID:
            raise SetupFailure("Docker version or group differs")
        write_json(artifacts / ".controller/setup-receipt.json", receipt)
        os.chown(artifacts / ".controller/setup-receipt.json", EXECUTION_UID, EXECUTION_GID)
        return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install",))
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args(argv)
    if not ADMITTED_STUDY_EPOCHS:
        refuse_unsupported(f"candidate setup command {args.command}")
    package_path = args.package.resolve()
    result = install(read_json(package_path, "setup package"), package_path.parent)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ADMITTED_STUDY_EPOCHS", "FIXED_CONTROLLER_PATHS", "FULL_POSTURE_AGENT_ENVIRONMENT",
    "SetupFailure", "assert_no_active_foreign", "compose_environment", "docker_inventory",
    "install", "ports_free", "refuse_unsupported", "validate_local_identity",
    "INSTALL_UMASK", "EXPECTED_DIRECTORY_MODES", "enforce_directory_mode",
    "verify_execution_identity_can_traverse", "PORT_TEARDOWN_WAIT_SECONDS",
    "validate_package",
]
