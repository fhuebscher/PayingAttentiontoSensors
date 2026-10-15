#!/usr/bin/env python3
"""Fail-closed remote tombstone for the UNSUPPORTED OTel Demo pilot.

The frozen 18-cell identities are preserved outside this controller.  No cell
may run because ``none`` and ``selected`` are structurally unsupported and a
complete ``none/selected/full`` block is the frozen comparative unit.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import http.client
import json
import math
import os
import pwd
import re
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, NamedTuple, Sequence


RUN_COUNT = 36
# Design order of the offpath epoch; the ordinal positions a cell may carry follow from it.
POSTURES = ("none", "selected", "async", "full")
APP_SERVICES = (
    "accountingservice", "adservice", "cartservice", "checkoutservice",
    "currencyservice", "emailservice", "flagd", "flagd-ui",
    "frauddetectionservice", "frontend", "frontendproxy", "imageprovider",
    "kafka", "loadgenerator", "paymentservice", "productcatalogservice",
    "quoteservice", "recommendationservice", "shippingservice",
)
COST_APP_SERVICES = tuple(
    service for service in APP_SERVICES if service != "loadgenerator"
)
# The synchronous checkout path, in traversal order (candidate_pilot.
# OFFPATH_SYNC_PATH; the runtime's SELECTED_CLOSURE as a set). Trace
# correlation reports a journey's path as this set intersected with its trace.
TARGET_PATH = (
    "frontendproxy", "frontend", "cartservice", "checkoutservice",
    "productcatalogservice", "currencyservice", "shippingservice", "quoteservice",
    "paymentservice", "emailservice", "flagd",
)
# The orders topic's broker and consumers: excluded from the synchronous
# comparison of the workload path check.
ASYNC_SERVICES = ("accountingservice", "frauddetectionservice", "kafka")
# How the target controller applies and reverts each fault action.
FAULT_ACTIONS = {"pause": ("pause", "unpause"), "stop": ("stop", "start")}
# The checkout journey's place-order body: upstream loadgenerator people.json[0]
# (src/loadgenerator/people.json at 2d4661e; a documented test card), with the
# journey token as userId so carts never mix across journeys.
CHECKOUT_PERSON = {
    "email": "larry_sergei@example.com",
    "address": {
        "streetAddress": "1600 Amphitheatre Parkway", "zipCode": "94043",
        "city": "Mountain View", "state": "CA", "country": "United States",
    },
    "userCurrency": "USD",
    "creditCard": {
        "creditCardNumber": "4432-8015-6152-0454", "creditCardExpirationMonth": 1,
        "creditCardExpirationYear": 2039, "creditCardCvv": 672,
    },
}
READINESS_TOKEN = "readiness-not-scored"
# Seconds between the end of the window (CPU snapshot, capture stopped) and
# reading the collector carrier, so the SDKs' batch exporters (5 s default
# schedule) have flushed the last journeys' spans. Engineering default.
COLLECTOR_SETTLE_SECONDS = 15
# Span ``service.name`` -> catalog service id, for the services whose telemetry
# names itself differently from the catalog. Explicit, never derived by
# normalising spellings. The one entry is the Envoy tracer's ``service_name``
# in the pinned upstream config (src/frontendproxy/envoy.tmpl.yaml, 1.12.0);
# candidate_runtime.verify_span_service_aliases() re-reads that file at plan
# time and refuses if this table and the config disagree.
SPAN_SERVICE_ALIASES = {"frontend-proxy": "frontendproxy"}
# The collector's own telemetry. Not an application service, so it is never in
# a posture's active closure. Excluded from the application-signal check in
# every posture: U3 (2026-09-23, "yes for none") covered none; the user's
# override of the fired run-2 stop rule (research/OTEL_RUN2_STOPPING_RULE.md,
# 77002f6) extended it to selected and full. The collector is harness
# infrastructure present identically in every posture; excluding this one
# named service cannot hide an application service.
COLLECTOR_SELF_SERVICE = "otelcol"
# The debug exporter prints every data point, log record and span event as
# ``Timestamp: 2026-09-18 15:06:12.450767915 +0000 UTC``; an unset pdata
# timestamp prints as the Unix epoch and is skipped.
_DEBUG_TIMESTAMP_LABEL = "Timestamp: "
_DEBUG_TIMESTAMP_SUFFIX = " +0000 UTC"
_COMPOSE_LOG_SEPARATOR = "| "
SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
HEX32 = re.compile(r"^[0-9a-f]{32}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_TARGET = {
    "host": "fb14srv6", "transportUser": "root", "setupUser": "root",
    "executionIdentity": {"user": "stig", "uid": 1016, "gid": 1016, "supplementalGids": [998]},
}
EXPECTED_RELEASE_PARENT = "/home/stig/observability-placement-candidate-v4-otel-srv6"
EXPECTED_ARTIFACT_PARENT = "/home/stig/observability-placement-candidate-v4-runs"
EXPECTED_LEASE_PATH = "/home/stig/observability-placement-candidate-v4-runs/.srv6-runtime.lock"
EXPECTED_PROJECT_PREFIX = "otel_candidate_v4_"
EXPECTED_PORTS = {"frontend": 18080, "frontendProxyOtlp": 18081, "grafana": 18082, "jaeger": 18083, "prometheus": 18084}
EXPECTED_CLEANUP_RESERVE_SECONDS = 600
EXPECTED_MINIMUM_REMAINING_SECONDS = 36_000


# Study epochs this installed controller may execute. The frozen v1 epoch is
# UNSUPPORTED: its byte-pinned descriptor's postureRealization says none and
# selected are unsupported. The v2 epoch (otel-demo-candidate-pilot-v2,
# change admit-otel-demo-candidate-pilot-v2) writes D13's no-telemetry-emitted
# reading into a new frozen descriptor and is the epoch this tuple is meant
# to admit. While it is empty every entry point refuses before reading a
# package. Admitting the epoch is a governed edit of this constant and of
# candidate_setup.ADMITTED_STUDY_EPOCHS (the two tuples must be identical;
# candidate_runtime.admitted_study_epochs() refuses if they differ).
# v3 (four postures, research/otel-postures/DECLARATION.md in the main repo) is
# admitted in place of v2: the tombstone names only the current epoch, and this
# controller no longer understands v2's 18-cell package shape (RUN_COUNT = 24).
# The offpath epoch (research/otel-offpath/DECLARATION.md in the main repo)
# replaces v3: this controller understands only the 36-cell checkout-journey
# package shape.
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
ADMITTED_STUDY_EPOCHS: tuple[str, ...] = ("otel-offpath-e-v1",)
# Study epochs whose package shape this controller understands. Knowing an
# epoch is not admitting it: a package for a known-but-unadmitted epoch is
# parsed exactly and then refused by refuse_unsupported.
KNOWN_STUDY_EPOCHS = ("otel-demo-offpath-v1",)
UNSUPPORTED_STUDY_EPOCHS = ("otel-demo-candidate-pilot-v1",)


class RuntimeFailure(RuntimeError):
    pass


def refuse_unsupported(operation: str, study_epoch: str | None = None) -> None:
    """Fail closed unless ``study_epoch`` is admitted; with no admitted epoch this
    refuses before any package bytes are read (the UNSUPPORTED tombstone)."""
    if not ADMITTED_STUDY_EPOCHS or study_epoch not in ADMITTED_STUDY_EPOCHS:
        epoch = study_epoch if isinstance(study_epoch, str) else UNSUPPORTED_STUDY_EPOCHS[0]
        raise RuntimeFailure(
            f"{operation} refused: {epoch} is UNSUPPORTED; "
            "no cell mutation or full-only execution is allowed"
        )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise RuntimeFailure(f"non-canonical execution value: {exc}") from exc


def safe_absolute(value: Any, where: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise RuntimeFailure(f"unsafe {where}")
    pure = PurePosixPath(value)
    if not pure.is_absolute() or str(pure) != value or any(part in {"", ".", ".."} for part in pure.parts):
        raise RuntimeFailure(f"unsafe {where}")
    return Path(value)


def read_json(path: Path, where: str) -> dict[str, Any]:
    try:
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeFailure(f"{where} is not a regular file")
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(RuntimeFailure(f"non-finite {value}")))
    except RuntimeFailure:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeFailure(f"cannot read {where}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeFailure(f"{where} is not an object")
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


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


def command(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = True,
    timeout: float | None = None,
    binary: bool = False,
) -> subprocess.CompletedProcess[Any]:
    """Run one target command.  Text mode decodes UTF-8 with replacement (U+FFFD): container and CLI output is bytes,
    not guaranteed UTF-8, and a strict decode turns one stray byte into an aborted campaign (Hotel sweep1 attempt 2,
    2026-10-03: one 0xbf in `docker compose logs`; TeaStore 9181964).  For valid UTF-8 the text is unchanged.
    ``binary=True`` returns the raw bytes (container logs are retained byte for byte)."""
    decoding: dict[str, Any] = {} if binary else {"encoding": "utf-8", "errors": "replace"}
    result = subprocess.run(
        list(argv), cwd=cwd, env=None if env is None else dict(env),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        timeout=timeout, **decoding,
    )
    if check and result.returncode:
        stderr = result.stderr.decode("utf-8", errors="replace") if binary else result.stderr
        raise RuntimeFailure(
            f"command {argv[0]} failed ({result.returncode}): {stderr.strip()}"
        )
    return result


SWEEP_STUDY_EPOCH = "otel-traffic-sweep-v1"
# 2026-10-04: the quiet calibration epoch (40 no-fault cells of the sweep's shape) runs the same timed cell runner.
QUIET_STUDY_EPOCH = "otel-quiet-calibration-v1"
# 2026-10-09: the repeat-episodes epoch (campaign B: the sweep's 12 cells x 3 blocks, H10 and H4) runs the same timed
# cell runner; its H10/H4 behaviour is named in each cell's compiled timing (duringFaultProbe, freezeStamps).
REPEAT_STUDY_EPOCH = "otel-repeat-episodes-v1"
# 2026-10-11: campaign C (otel-repeat-episodes-c-v1, main repo research/PROTOCOL_DRAFT_20261002.md decision 82) is B's shape
# exactly under a new epoch: every rule this file applies to B's cells (H10/H4 flags, the trace rule per cell kind) applies
# to C's.  ``REPEAT_STUDY_EPOCHS`` is that family; B's behaviour is unchanged.
REPEAT_C_STUDY_EPOCH = "otel-repeat-episodes-c-v1"
# 2026-10-12: the load pilot (otel-load-pilot-v1, main repo research/traffic-sweep/BUDGET_D.md amendment 1) runs C's cell at
# 100 and 200 req/s: H10, H4 and the trace rule per cell kind exactly as C's, so it joins the family; only its cells carry
# ``generatorOpenFilesMinimum`` (ensure_generator_open_files).
LOAD_PILOT_STUDY_EPOCH = "otel-load-pilot-v1"
# 2026-10-13: the off-path manifestation pilot (otel-offpath-pilot-v1, main repo research/traffic-sweep/BUDGET_E.md) runs the
# same cell with the load pilot's generator sizing, and its cells carry ``workloadMix`` (the upstream Locust task mix as an
# open loop, one ledger row per request with its route): H10, H4 and the trace rule per cell kind as C's, so it joins the family.
OFFPATH_PILOT_STUDY_EPOCH = "otel-offpath-pilot-v1"
# 2026-10-12: the second off-path pilot (otel-offpath-pilot-v2, BUDGET_E amendment 1, decision 108) is v1's cell at 25 and 50 req/s of the
# same mix without the throttle: the same family rules (H10, H4, the trace rule per cell kind, the mix).
OFFPATH_PILOT_V2_STUDY_EPOCH = "otel-offpath-pilot-v2"
# 2026-10-12: campaign E (otel-offpath-e-v1, BUDGET_E, decisions 95-102) is the pilot v2's cell in 5 blocks at one rate with a kept set of faults:
# the same family rules.  NOT admitted by the tombstone here: the selector and ADMITTED_STUDY_EPOCHS still name the running pilot.
OFFPATH_E_STUDY_EPOCH = "otel-offpath-e-v1"
REPEAT_STUDY_EPOCHS = (
    REPEAT_STUDY_EPOCH, REPEAT_C_STUDY_EPOCH, LOAD_PILOT_STUDY_EPOCH, OFFPATH_PILOT_STUDY_EPOCH, OFFPATH_PILOT_V2_STUDY_EPOCH,
    OFFPATH_E_STUDY_EPOCH)
TIMED_STUDY_EPOCHS = (SWEEP_STUDY_EPOCH, QUIET_STUDY_EPOCH, *REPEAT_STUDY_EPOCHS)


def is_timed(cell: Any) -> bool:
    """A parameterised (timed-epoch) cell carries its compiled timing; a frozen offpath cell never does."""
    return isinstance(cell, Mapping) and isinstance(cell.get("timing"), dict)


def _plan_value(document: Mapping[str, Any], key: str) -> int:
    """One plan-level value every timed cell of the package repeats (compiled timing), or a refusal."""
    cells = document.get("cells")
    if not isinstance(cells, list) or not cells or not all(is_timed(cell) for cell in cells):
        raise RuntimeFailure("a timed-epoch package must carry the compiled timing in every cell")
    values = {cell["timing"].get(key) for cell in cells}
    value = next(iter(values)) if len(values) == 1 else None
    if type(value) is not int or value < 1:
        raise RuntimeFailure(f"timed cells disagree on {key}")
    return value


def expected_run_count(document: Mapping[str, Any]) -> int:
    """The frozen epoch's reviewed literal; a timed epoch's count from its compiled timing."""
    if document.get("studyEpoch") in TIMED_STUDY_EPOCHS:
        return _plan_value(document, "planRunCount")
    if isinstance(document.get("cells"), list) and any(is_timed(cell) for cell in document["cells"]):
        raise RuntimeFailure("a frozen-epoch package carries timed cells")
    return RUN_COUNT


def expected_minimum_remaining(document: Mapping[str, Any]) -> int:
    if document.get("studyEpoch") in TIMED_STUDY_EPOCHS:
        return _plan_value(document, "planMinimumRemainingSeconds")
    return EXPECTED_MINIMUM_REMAINING_SECONDS


def validate_package(
    document: Mapping[str, Any],
    *,
    clock=lambda: datetime.now(timezone.utc),
) -> tuple[list[dict[str, Any]], Path, Path, str, datetime]:
    required = {
        "schemaVersion", "kind", "campaignId", "studyEpoch", "gatePlanSha256",
        "gateSetupSha256", "setupReceiptSha256", "targetContractSha256", "target",
        "runtimeReadinessSha256", "gateRunSha256", "authorizationDeadline",
        "cleanupReserveSeconds", "minimumRemainingAtFirstMutationSeconds",
        "releaseRoot", "remoteSourceRoot", "materializedSourceSha256", "imageIds",
        "installedControllerDigests", "exclusiveLeasePath", "leaseLaunchMode", "remoteArtifactRoot",
        "composeProject", "composePorts", "systemdUnit", "handoff", "runCount",
        "controllerDigests", "authorizedRunIds", "cells", "oneShot",
        "promotionAuthorized",
    }
    if set(document) != required or document.get("schemaVersion") != 1 or document.get("kind") != "otel-demo-candidate-execution-package-v1":
        raise RuntimeFailure("execution package shape differs")
    if document.get("studyEpoch") not in KNOWN_STUDY_EPOCHS + ADMITTED_STUDY_EPOCHS + UNSUPPORTED_STUDY_EPOCHS:
        raise RuntimeFailure("execution package names an unknown study epoch")
    run_count = expected_run_count(document)
    if (
        type(document.get("runCount")) is not int
        or document["runCount"] != run_count
        or document.get("oneShot") is not True
        or document.get("promotionAuthorized") is not False
        or SAFE_NAME.fullmatch(str(document.get("campaignId"))) is None
        or SAFE_NAME.fullmatch(str(document.get("composeProject"))) is None
        or any(HEX64.fullmatch(str(document.get(key))) is None for key in ("gatePlanSha256", "runtimeReadinessSha256", "gateRunSha256"))
        or document.get("target") != EXPECTED_TARGET
        or document.get("composePorts") != EXPECTED_PORTS
        or not str(document.get("composeProject", "")).startswith(EXPECTED_PROJECT_PREFIX)
        or document.get("systemdUnit") != f"{document.get('composeProject')}.service"
        or document.get("leaseLaunchMode") != "systemd-run-flock-no-fork-inherited-fd"
        or document.get("cleanupReserveSeconds") != EXPECTED_CLEANUP_RESERVE_SECONDS
        or document.get("minimumRemainingAtFirstMutationSeconds")
        != expected_minimum_remaining(document)
        or any(HEX64.fullmatch(str(document.get(key))) is None for key in (
            "gateSetupSha256", "setupReceiptSha256", "targetContractSha256",
            "materializedSourceSha256",
        ))
    ):
        raise RuntimeFailure("execution package identity or authority differs")
    controllers = document["controllerDigests"]
    images = document["imageIds"]
    own_digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if (
        not isinstance(controllers, dict)
        or controllers.get("remote-compose-controller") != own_digest
        or any(HEX64.fullmatch(str(value)) is None for value in controllers.values())
        or document["installedControllerDigests"] != controllers
        or not isinstance(images, dict)
        or set(images) != set(APP_SERVICES)
        or any(re.fullmatch(r"sha256:[0-9a-f]{64}", str(value)) is None for value in images.values())
    ):
        raise RuntimeFailure("remote controller bytes differ from the authorized package")
    cells = document["cells"]
    if not isinstance(cells, list) or len(cells) != run_count:
        raise RuntimeFailure(f"execution package does not contain exactly {run_count} cells")
    root = safe_absolute(document["remoteArtifactRoot"], "artifact root")
    release = safe_absolute(document["releaseRoot"], "release root")
    source = safe_absolute(document["remoteSourceRoot"], "source root")
    lease = safe_absolute(document["exclusiveLeasePath"], "lease path")
    if (
        root.parent != Path(EXPECTED_ARTIFACT_PARENT)
        or root.name != document["campaignId"]
        or str(lease) != EXPECTED_LEASE_PATH
        or release.parent != Path(EXPECTED_RELEASE_PARENT)
        or source != release / "source"
    ):
        raise RuntimeFailure("execution roots differ from the reviewed srv6 allocation")
    ids = [cell.get("runId") for cell in cells if isinstance(cell, dict)]
    if (
        len(ids) != run_count
        or len(set(ids)) != run_count
        or document["authorizedRunIds"] != ids
    ):
        raise RuntimeFailure("execution package cell identities are incomplete or duplicate")
    attempts = {
        cell.get("runKey", {}).get("attempt") if isinstance(cell.get("runKey"), dict) else None
        for cell in cells
    }
    attempt = next(iter(attempts)) if len(attempts) == 1 else None
    if type(attempt) is not int or attempt < 1:
        raise RuntimeFailure("execution package cells do not share one positive attempt")
    for cell in cells:
        key = cell.get("runKey", {})
        artifact_root = safe_absolute(cell.get("remoteArtifactRoot"), "cell artifact root")
        try:
            relative = artifact_root.relative_to(root)
        except ValueError as exc:
            raise RuntimeFailure("cell artifact root escapes campaign root") from exc
        if (
            key.get("attempt") != attempt
            or not isinstance(cell.get("attemptPolicy"), dict)
            or cell["attemptPolicy"].get("attempt") != attempt
            or cell.get("campaignId") != document["campaignId"]
            or cell.get("studyEpoch") != document["studyEpoch"]
            or cell.get("target") != document["target"]
            or cell.get("releaseRoot") != str(release)
            or cell.get("remoteSourceRoot") != str(source)
            or cell.get("materializedSourceSha256") != document["materializedSourceSha256"]
            or cell.get("imageIds") != document["imageIds"]
            or cell.get("installedControllerDigests") != document["installedControllerDigests"]
            or cell.get("targetContractSha256") != document["targetContractSha256"]
            or cell.get("gateSetupSha256") != document["gateSetupSha256"]
            or cell.get("setupReceiptSha256") != document["setupReceiptSha256"]
            or cell.get("compose", {}).get("project") != document["composeProject"]
            or cell.get("exclusiveLeasePath") != document["exclusiveLeasePath"]
            or str(relative) != cell.get("compiledArtifactRoot")
            or cell.get("posture", {}).get("id") not in set(POSTURES)
            or cell.get("attemptPolicy", {}).get("retryAllowed") is not False
            or cell.get("attemptPolicy", {}).get("substitutionAllowed") is not False
            or cell.get("attemptPolicy", {}).get("rerandomizationAllowed") is not False
            or cell.get("promotionAuthorized") is not False
        ):
            raise RuntimeFailure("execution package permits attempt substitution or retry")
    try:
        deadline = datetime.fromisoformat(document["authorizationDeadline"].removesuffix("Z") + "+00:00")
    except (TypeError, ValueError) as exc:
        raise RuntimeFailure("authorization deadline is invalid") from exc
    if deadline.tzinfo != timezone.utc:
        raise RuntimeFailure("authorization deadline is not UTC")
    observed = clock()
    if observed.tzinfo != timezone.utc:
        raise RuntimeFailure("target controller clock is not timezone-aware UTC")
    remaining = math.floor((deadline - observed).total_seconds())
    if remaining < document["minimumRemainingAtFirstMutationSeconds"]:
        raise RuntimeFailure(
            "authorization deadline leaves too little time at target controller start"
        )
    return cells, root, lease, document["composeProject"], deadline


def validate_local_target(
    target: Mapping[str, Any],
    *,
    observed_host: str | None = None,
    observed_user: str | None = None,
    observed_uid: int | None = None,
    observed_gid: int | None = None,
    observed_groups: Sequence[int] | None = None,
) -> dict[str, Any]:
    host = socket.gethostname() if observed_host is None else observed_host
    user = pwd.getpwuid(os.geteuid()).pw_name if observed_user is None else observed_user
    uid = os.geteuid() if observed_uid is None else observed_uid
    gid = os.getegid() if observed_gid is None else observed_gid
    groups = sorted(os.getgroups() if observed_groups is None else observed_groups)
    observed = {"host": host, "executionUser": user, "uid": uid, "gid": gid, "supplementalGids": groups}
    if (
        target != EXPECTED_TARGET or host != "fb14srv6" or user != "stig"
        or uid != 1016 or gid != 1016 or set(groups) != {998, gid}
        # 2026-09-18: was `groups != [998]`, which no process could satisfy.
        # Linux getgroups() includes the primary gid, so `runuser --user stig
        # --group stig --supp-group docker` yields [998, 1016], not [998].
        # {998, gid} is exactly as tight: docker plus the primary gid already
        # asserted above, and nothing else. This assertion had never executed,
        # because the numeric --group spelling failed earlier in the argv.
    ):
        raise RuntimeFailure("remote controller is running under the wrong target or execution identity")
    return observed


def inherited_lease_fd(lease_path: Path, *, fd_root: Path = Path("/proc/self/fd")) -> int:
    try:
        for candidate in fd_root.iterdir():
            if not candidate.name.isdigit():
                continue
            try:
                if Path(os.readlink(candidate)).resolve() == lease_path.resolve():
                    return int(candidate.name)
            except OSError:
                continue
    except OSError as exc:
        raise RuntimeFailure(f"cannot inspect inherited lease descriptors: {exc}") from exc
    raise RuntimeFailure("systemd/flock launcher did not pass the held shared lease")


def cell_environment(cell: Mapping[str, Any]) -> dict[str, str]:
    compose = cell["compose"]
    ports = compose["ports"]
    environment = dict(os.environ)
    environment.update({str(key): str(value) for key, value in cell["posture"]["environment"].items()})
    environment.update({
        "DEMO_VERSION": "1.12.0",
        "ENVOY_PORT": str(ports["frontend"]),
        "FRONTEND_PROXY_OTLP_HOST_PORT": str(ports["frontendProxyOtlp"]),
        "GRAFANA_HOST_PORT": str(ports["grafana"]),
        "JAEGER_HOST_PORT": str(ports["jaeger"]),
        "PROMETHEUS_HOST_PORT": str(ports["prometheus"]),
        "OTEL_PLACEMENT_ENABLED": "true" if cell["posture"]["id"] != "none" else "false",
        "OTEL_PLACEMENT_DISABLED": "true" if cell["posture"]["id"] == "none" else "false",
        "OTEL_COLLECTOR_CONFIG": f"{cell['remoteSourceRoot']}/src/otelcollector/otelcol-placement.yml",
        "OTEL_COLLECTOR_CONFIG_EXTRAS": f"{cell['remoteSourceRoot']}/src/otelcollector/otelcol-config-extras.yml",
    })
    source_digest = (Path(cell["remoteSourceRoot"]) / ".source.sha256").read_text().strip()
    if source_digest != cell["materializedSourceSha256"] or source_tree_sha256(Path(cell["remoteSourceRoot"])) != source_digest:
        raise RuntimeFailure("materialized source digest differs from the authorized installed bytes")
    environment["OTEL_IMAGE_TAG"] = f"1.12.0-{source_digest[:16]}"
    return environment


def compose(cell: Mapping[str, Any], *arguments: str) -> list[str]:
    source = cell["remoteSourceRoot"]
    return [
        "docker", "compose", "-p", cell["compose"]["project"],
        "-f", f"{source}/docker-compose.obsplacement.yml",
        "-f", f"{source}/compose.otel-placement.yml",
        "-f", f"{source}/compose.candidate-postures.yml",
        *arguments,
    ]


def verify_installed_images(cell: Mapping[str, Any], environment: Mapping[str, str]) -> str:
    """Check every rendered image ID and return the rendered Compose config digest."""
    rendered = command(
        compose(cell, "config", "--format", "json"),
        cwd=Path(cell["remoteSourceRoot"]), env=environment,
    )
    try:
        services = json.loads(rendered.stdout).get("services", {})
    except (json.JSONDecodeError, AttributeError) as exc:
        raise RuntimeFailure("rendered Compose config is invalid") from exc
    for service, expected in cell["imageIds"].items():
        reference = (services.get(service) or {}).get("image")
        if not isinstance(reference, str) or not reference:
            raise RuntimeFailure(f"rendered image reference is absent for {service}")
        observed = command(["docker", "image", "inspect", "--format", "{{.Id}}", reference]).stdout.strip()
        if observed != expected:
            raise RuntimeFailure(f"installed image ID differs for {service}")
    return hashlib.sha256(rendered.stdout.encode("utf-8")).hexdigest()


def project_resources(project: str) -> dict[str, list[str]]:
    label = f"label=com.docker.compose.project={project}"
    queries = {
        "containers": ["docker", "ps", "-aq", "--filter", label],
        "networks": ["docker", "network", "ls", "-q", "--filter", label],
        "volumes": ["docker", "volume", "ls", "-q", "--filter", label],
    }
    return {
        key: sorted(line for line in command(argv, check=False).stdout.splitlines() if line)
        for key, argv in queries.items()
    }


def container_id(cell: Mapping[str, Any], service: str, environment: Mapping[str, str]) -> str:
    result = command(compose(cell, "ps", "-q", service), cwd=Path(cell["remoteSourceRoot"]), env=environment)
    values = [line for line in result.stdout.splitlines() if line]
    if len(values) != 1:
        raise RuntimeFailure(f"expected one {service} container, found {values}")
    return values[0]


def post_json(url: str, body: Mapping[str, Any], headers: Mapping[str, str], timeout: float) -> dict[str, Any]:
    """One POST; ok means HTTP 200. Never raises for an HTTP or socket failure."""
    started = time.time()
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"content-type": "application/json", **dict(headers)},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            status = response.status
            error = None if status == 200 else f"HTTP {status}"
            return {"status": status, "bytes": len(payload), "startedAtEpoch": started, "endedAtEpoch": time.time(), "error": error}
    except (OSError, urllib.error.HTTPError) as exc:
        return {"status": getattr(exc, "code", None), "bytes": 0, "startedAtEpoch": started, "endedAtEpoch": time.time(), "error": f"{type(exc).__name__}: {exc}"}


def journey_steps(
    base: str, workload: Mapping[str, Any], token: str, trace_id: str, traceparent: str,
) -> list[dict[str, Any]]:
    """Add to cart, then (only if that succeeded) place the order.

    One W3C trace per journey. add-to-cart carries the journey's token and the
    ledger row's traceparent, so the frontendproxy witness sees every offered
    journey exactly once; place-order carries ``<token>-order`` and its own span
    id under the same trace id.
    """
    timeout = float(workload["stepTimeoutSeconds"])
    cart = post_json(
        base + workload["cartPath"],
        {"item": {"productId": workload["productId"], "quantity": 1}, "userId": token},
        {"traceparent": traceparent, "x-obsplacement-request-token": token}, timeout,
    )
    steps = [{"name": "add-to-cart", **cart}]
    if cart["error"] is None:
        order_span = hashlib.sha256(f"{token}\0order-span".encode()).hexdigest()[:16]
        order = post_json(
            base + workload["urlPath"], {**CHECKOUT_PERSON, "userId": token},
            {"traceparent": f"00-{trace_id}-{order_span}-01", "x-obsplacement-request-token": f"{token}-order"},
            timeout,
        )
        steps.append({"name": "place-order", **order})
    return steps


def wait_ready(base: str, workload: Mapping[str, Any], deadline: datetime, timeout: int = 600) -> None:
    """Ready means one complete journey returns 200 on both steps (the checkout
    stack, Kafka included, is up); a readiness journey is never scored."""
    end = min(time.monotonic() + timeout, time.monotonic() + max(0, (deadline - datetime.now(timezone.utc)).total_seconds()))
    attempt = 0
    while time.monotonic() < end:
        attempt += 1
        user = f"{READINESS_TOKEN}-{attempt}-{int(time.time() * 1000)}"
        trace_id = hashlib.sha256(user.encode()).hexdigest()[:32]
        steps = journey_steps(base, workload, user, trace_id, f"00-{trace_id}-{trace_id[:16]}-01")
        if len(steps) == 2 and all(step["error"] is None for step in steps):
            return
        time.sleep(5)
    raise RuntimeFailure("checkout journey readiness deadline expired")


def route_available(url: str, timeout: float = 5.0) -> bool:
    """A GET through the entry point (diagnostic fault probe, never scored)."""
    try:
        request = urllib.request.Request(url, headers={"x-obsplacement-request-token": READINESS_TOKEN})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            return response.status == 200
    except (OSError, urllib.error.HTTPError):
        return False


class DockerSocketConnection(http.client.HTTPConnection):
    def __init__(self) -> None:
        super().__init__("localhost")

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect("/var/run/docker.sock")


def docker_stats(container: str) -> dict[str, Any]:
    connection = DockerSocketConnection()
    try:
        connection.request("GET", f"/v1.40/containers/{container}/stats?stream=false")
        response = connection.getresponse()
        payload = response.read()
    finally:
        connection.close()
    if response.status != 200:
        raise RuntimeFailure(f"Docker stats API returned {response.status}")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise RuntimeFailure("Docker stats response is not an object")
    return value


def cpu_snapshot(cell: Mapping[str, Any], environment: Mapping[str, str]) -> dict[str, Any]:
    captured_at_start = now_iso()
    identifiers = {
        service: container_id(cell, service, environment)
        for service in COST_APP_SERVICES
    }

    def sample(item: tuple[str, str]) -> tuple[str, dict[str, Any]]:
        service, identifier = item
        stats = docker_stats(identifier)
        value = stats.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage")
        if type(value) is not int or value < 0:
            raise RuntimeFailure(f"{service} lacks cumulative CPU nanoseconds")
        return service, {
            "containerId": identifier,
            "totalUsageNanoseconds": value,
        }

    with ThreadPoolExecutor(max_workers=len(identifiers)) as pool:
        sampled = dict(pool.map(sample, identifiers.items()))
    services = {service: sampled[service] for service in COST_APP_SERVICES}
    total = sum(row["totalUsageNanoseconds"] for row in services.values())
    return {
        "capturedAtStart": captured_at_start,
        "capturedAtEnd": now_iso(),
        "counter": "docker-engine-cpu_stats.cpu_usage.total_usage",
        "services": services,
        "totalNanoseconds": total,
    }


def request_identity(namespace: str, sequence: int) -> tuple[str, str, str]:
    digest = hashlib.sha256(f"{namespace}\0{sequence}".encode()).hexdigest()
    token = f"opq-{digest[:24]}"
    trace_id = digest[:32]
    span_id = hashlib.sha256(f"{token}\0span".encode()).hexdigest()[:16]
    return token, trace_id, f"00-{trace_id}-{span_id}-01"


def one_journey(base: str, workload: Mapping[str, Any], scheduled: float, token: str, trace_id: str, traceparent: str) -> dict[str, Any]:
    """One ledger row per offered journey, in the v1-v3 row format plus steps."""
    delay = scheduled - time.time()
    if delay > 0:
        time.sleep(delay)
    started = time.time()
    steps = journey_steps(base, workload, token, trace_id, traceparent)
    last = steps[-1]
    failed = next((step for step in steps if step["error"] is not None), None)
    complete = failed is None and len(steps) == 2
    return {
        "requestToken": token, "originalTraceId": trace_id, "traceparent": traceparent,
        "scheduledAtEpoch": scheduled, "startedAtEpoch": started, "endedAtEpoch": time.time(),
        "status": last["status"], "bytes": last["bytes"],
        "error": None if complete else f"{(failed or last)['name']}: {(failed or last)['error']}",
        "steps": steps,
    }


def run_workload(base: str, workload: Mapping[str, Any], namespace: str, duration: int) -> dict[str, Any]:
    rate = workload["requestsPerSecond"]
    concurrency = workload["concurrency"]
    url = base + workload["urlPath"]
    started = time.time()
    offered = duration * rate
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = []
        for sequence in range(offered):
            token, trace_id, traceparent = request_identity(namespace, sequence)
            futures.append(pool.submit(one_journey, base, workload, started + sequence / rate, token, trace_id, traceparent))
        requests = [future.result() for future in futures]
    return {
        "schemaVersion": 1, "url": url, "tokenNamespace": namespace,
        "ratePerSecond": rate, "concurrency": concurrency,
        "startedAtEpoch": started, "endedAtEpoch": time.time(),
        "offered": offered,
        "completed": sum(item["error"] is None for item in requests),
        "failed": sum(item["error"] is not None for item in requests),
        "requests": requests,
    }


class Capture(NamedTuple):
    """A running tcpdump plus the file its diagnostics are written to."""

    process: subprocess.Popen
    log: Path


def start_capture(path: Path) -> Capture:
    """Start a privileged tcpdump that ``stop_capture`` can actually stop.

    The process tree is ``controller -> sudo (root) -> tcpdump``, and tcpdump
    drops privileges to a packaged account of its own.  Three properties are
    load-bearing, each learned from a failure on fb14srv6:

    * ``start_new_session=True`` puts ``sudo`` and the ``tcpdump`` it supervises
      into a process group of their own, so ``stop_capture`` can signal the
      group rather than only the ``sudo`` we happen to hold a handle on.  A
      signal sent to ``process.pid`` alone does not reach the grandchild.
    * stdout and stderr go to a **file**, never a pipe.  A surviving grandchild
      inherits the write end of a pipe, so ``communicate()`` blocks for an EOF
      that never arrives -- and ``/proc`` is ``hidepid=invisible`` on the
      targets, so the survivor can be neither seen nor signalled afterwards.
      A file has no such owner, so the wait cannot hang on one.
    * ``-Z`` drops tcpdump to the user running this controller.  Without it
      tcpdump drops to its own ``tcpdump`` account and leaves the capture
      ``0600 tcpdump:tcpdump``, which this controller then cannot read back:
      ``telemetry_bytes`` would fail on both the sha256 and the ``tshark`` pass.

    The log is deliberately *not* placed in the cell artifact root.  What the
    harness emits per cell is a preregistered set, not an engineering default.
    """
    handle, log_name = tempfile.mkstemp(prefix="tcpdump-", suffix=".log")
    log = Path(log_name)
    try:
        process = subprocess.Popen(
            [
                "sudo", "-n", "tcpdump",
                "-Z", pwd.getpwuid(os.geteuid()).pw_name,
                "-i", "any", "-s", "0", "-U", "-w", str(path),
                "tcp dst port 4317 or tcp dst port 4318",
            ],
            stdout=handle, stderr=subprocess.STDOUT, start_new_session=True,
        )
    finally:
        os.close(handle)
    return Capture(process, log)


def stop_capture(capture: Capture) -> None:
    """Stop the capture and reap the whole process group, or fail loudly.

    Signals go to the process group so that the privilege-dropped tcpdump --
    not just its ``sudo`` parent -- receives them and flushes the savefile.
    SIGINT is what makes tcpdump close the pcap cleanly; SIGKILL is the
    escalation, and would leave a truncated capture, so a SIGKILLed tcpdump is
    reported as a failure rather than quietly accepted.  Idempotent: the finally
    block in ``run_cell`` may call this after the normal path already has.
    """
    process = capture.process
    try:
        for signal_number, timeout in ((signal.SIGINT, 30), (signal.SIGKILL, 10)):
            if process.poll() is not None:
                break
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(os.getpgid(process.pid), signal_number)
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=timeout)
        stderr = ""
        if capture.log.exists():
            stderr = capture.log.read_text(encoding="utf-8", errors="replace")
        if process.poll() is None:
            raise RuntimeFailure(f"tcpdump did not stop: {stderr.strip()}")
        if process.returncode not in {0, 130}:
            raise RuntimeFailure(f"tcpdump failed: {stderr.strip()}")
    finally:
        with contextlib.suppress(OSError):
            capture.log.unlink()


def _sum_tshark(path: Path, display_filter: str, field: str) -> int:
    output = command(["tshark", "-r", str(path), "-Y", display_filter, "-T", "fields", "-e", field]).stdout
    values = [int(line) for line in output.splitlines() if line.strip()]
    return sum(values)


def telemetry_bytes(path: Path) -> dict[str, Any]:
    base = "(tcp.dstport == 4317 || tcp.dstport == 4318)"
    emitted = _sum_tshark(path, f"{base} && tcp.len > 0 && !tcp.analysis.retransmission", "tcp.len")
    wire = _sum_tshark(path, base, "frame.len")
    return {
        "schemaVersion": 1,
        "captureTool": "tshark",
        "filter": "tcp dst port 4317 or tcp dst port 4318",
        "emittedTelemetryBytes": emitted,
        "onWireTelemetryBytes": wire,
        "retransmissionsExcludedFromEmitted": True,
        "pcapSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def inject_fault(cell: Mapping[str, Any], environment: Mapping[str, str], base: str, barrier: float, output: dict[str, Any]) -> None:
    """Apply one declared fault to ``cell["fault"]["service"]`` and prove it by
    independent state probes, as Hotel's compose_pause.py does.

    ``appliedMonotonic`` is taken after the fault is observed in the target's
    state and before the route probe; ``revertingMonotonic`` just before the
    revert command. [applied, reverting] is the detection window; both are also
    given relative to the shared barrier, as the v1-v3 onset/offset fields are.
    The hold is measured from the fault command itself, so the probes' own
    duration is not added on top of it (Hotel campaign #1, D21).
    """
    fault = cell["fault"]
    scenario, service, action = fault["scenario"], fault["service"], fault["action"]
    onset = fault["onsetSeconds"]
    hold = fault["holdSeconds"]
    apply, revert = FAULT_ACTIONS[action]
    probe_url = f"{base}/api/products/{cell['workload']['productId']}"
    receipt: dict[str, Any] = {
        "scenario": scenario, "service": service,
        "targetContainerId": None, "targetImageId": None,
        "preState": None, "duringStateSamples": [], "postState": None,
        "actualOnsetMonotonicOffsetSeconds": None,
        "actualOffsetMonotonicOffsetSeconds": None,
        "barrierMonotonic": barrier, "appliedMonotonic": None, "revertingMonotonic": None,
        "appliedMonotonicOffsetSeconds": None, "revertingMonotonicOffsetSeconds": None,
        "duringRouteAvailable": None,
        "manifested": False, "recovered": False, "successful": False,
        "error": None,
    }
    applied = False
    try:
        remaining = barrier + onset - time.monotonic()
        if remaining > 0: time.sleep(remaining)
        identifier = container_id(cell, service, environment)
        inspected = json.loads(command(["docker", "inspect", identifier]).stdout)[0]
        receipt["targetContainerId"] = identifier
        receipt["targetImageId"] = inspected["Image"]
        receipt["preState"] = inspected["State"]
        began = time.monotonic()
        receipt["actualOnsetMonotonicOffsetSeconds"] = began - barrier
        command(compose(cell, apply, service), cwd=Path(cell["remoteSourceRoot"]), env=environment)
        applied = True
        during = json.loads(command(["docker", "inspect", identifier]).stdout)[0]["State"]
        receipt["duringStateSamples"].append(during)
        receipt["appliedMonotonic"] = time.monotonic()
        receipt["appliedMonotonicOffsetSeconds"] = receipt["appliedMonotonic"] - barrier
        receipt["duringRouteAvailable"] = route_available(probe_url)
        if action == "pause":
            state_holds = bool(during.get("Running") and during.get("Paused"))
        else:
            state_holds = not during.get("Running")
        route_holds = (
            receipt["duringRouteAvailable"] is False
            if fault["entryRouteDuringFault"] == "must-be-unavailable" else True
        )
        # H10: the route is not probed during the fault, so manifestation rests on the container state read back (and,
        # for a pause, the Docker pause event the cell runner checks after the worker settles).
        receipt["manifested"] = state_holds and route_holds
        remaining = hold - (time.monotonic() - began)
        if remaining > 0: time.sleep(remaining)
        receipt["revertingMonotonic"] = time.monotonic()
        receipt["revertingMonotonicOffsetSeconds"] = receipt["revertingMonotonic"] - barrier
        command(compose(cell, revert, service), cwd=Path(cell["remoteSourceRoot"]), env=environment)
        applied = False
        receipt["actualOffsetMonotonicOffsetSeconds"] = time.monotonic() - barrier
        wait_ready(base, cell["workload"], datetime.now(timezone.utc) + timedelta(minutes=5), timeout=300)
        post = json.loads(command(["docker", "inspect", identifier]).stdout)[0]["State"]
        receipt["postState"] = post
        receipt["recovered"] = bool(post.get("Running") and not post.get("Paused"))
        receipt["successful"] = receipt["manifested"] and receipt["recovered"]
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if applied:
            command(compose(cell, revert, service), cwd=Path(cell["remoteSourceRoot"]), env=environment, check=False)
    output.update(receipt)


def parse_application_witness(log: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
    offered = {item["requestToken"]: item["traceparent"] for item in requests}
    rows = []
    for line in log.splitlines():
        start = line.find("{")
        if start < 0: continue
        try: value = json.loads(line[start:])
        except json.JSONDecodeError: continue
        if value.get("obsplacement_kind") != "application-request-witness": continue
        token = value.get("request_token")
        if token in offered:
            rows.append(value)
    counts: dict[str, int] = {}
    for row in rows: counts[row["request_token"]] = counts.get(row["request_token"], 0) + 1
    return {
        "schemaVersion": 1, "source": "frontendproxy-json-access-log",
        "offeredTokens": len(offered), "witnessedTokens": len(counts),
        "duplicateWitnessTokens": sorted(token for token, count in counts.items() if count != 1),
        "unknownWitnessTokens": sorted({row["request_token"] for row in rows} - set(offered)),
        "rows": rows,
    }


def catalog_service(span_service: str) -> str:
    return SPAN_SERVICE_ALIASES.get(span_service, span_service)


def _debug_record_epoch(line: str) -> float | None:
    """Epoch seconds of one debug-exporter ``Timestamp:`` record, else None."""
    _, separator, payload = line.partition(_COMPOSE_LOG_SEPARATOR)
    text = (payload if separator else line).strip()
    if not text.startswith(_DEBUG_TIMESTAMP_LABEL) or not text.endswith(_DEBUG_TIMESTAMP_SUFFIX):
        return None
    stamp = text[len(_DEBUG_TIMESTAMP_LABEL):-len(_DEBUG_TIMESTAMP_SUFFIX)]
    whole, _, fraction = stamp.partition(".")
    try:
        moment = datetime.strptime(whole, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    if fraction and not fraction.isdigit():
        return None
    seconds = moment.timestamp() + (int(fraction[:9].ljust(9, "0")) / 1e9 if fraction else 0.0)
    return None if seconds == 0 else seconds


def collector_carrier_coverage(log: str, window_start_epoch: float) -> dict[str, Any]:
    """Fail-closed check that the collector carrier covers the whole window.

    The first retained ``Timestamp:`` record, in carrier order, must precede
    the measurement window start. Run 1's carrier was a rotated json-file log
    that kept only the last 9-14 s of each 599 s window; this is the check
    that would have refused it.
    """
    first = None
    for line in log.splitlines():
        first = _debug_record_epoch(line)
        if first is not None:
            break
    covers = first is not None and first < window_start_epoch
    return {"firstRecordEpoch": first, "windowStartEpoch": window_start_epoch, "coversWindow": covers}


def require_collector_carrier_coverage(log: str, window_start_epoch: float) -> None:
    coverage = collector_carrier_coverage(log, window_start_epoch)
    if not coverage["coversWindow"]:
        raise RuntimeFailure(
            "collector carrier does not cover the measurement window: first retained record "
            f"{coverage['firstRecordEpoch']!r} is not before window start {window_start_epoch!r}"
        )


def trace_services(log: str) -> dict[str, set[str]]:
    """Trace id -> catalog services whose spans carry it (collector excluded)."""
    services: dict[str, set[str]] = {}
    current_service: str | None = None
    for line in log.splitlines():
        service_match = re.search(r"service\.name:\s*Str\(([^)]+)\)", line)
        if service_match:
            current_service = catalog_service(service_match.group(1))
        trace_match = re.search(r"(?i)Trace ID\s*:\s*([0-9a-f]{32})", line)
        if trace_match:
            services.setdefault(trace_match.group(1).lower(), set())
            if current_service and current_service != COLLECTOR_SELF_SERVICE:
                services[trace_match.group(1).lower()].add(current_service)
    return services


def parse_trace_correlation(log: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
    by_trace = trace_services(log)
    rows = []
    for item in requests:
        trace_id = item["originalTraceId"]
        services = by_trace.get(trace_id, set())
        rows.append({
            "requestToken": item["requestToken"],
            "injectedOriginalTraceId": trace_id,
            "observedOriginalTraceIds": [trace_id] if trace_id in by_trace else [],
            "observedPathServices": sorted(set(TARGET_PATH).intersection(services)),
            # Every catalog service in the journey's trace, async consumers
            # included: what the workload path check and the adapter read.
            "observedTraceServices": sorted(services),
        })
    return {
        "schemaVersion": 1,
        "correlation": "injected-w3c-original-trace-id",
        "crossTraceAssembly": False,
        # Run 2 (2026-09-24): len(observed) counted every trace id in the carrier (735-737 selected,
        # 1,635-1,699 full) while the terminal validator replays the distinct request-correlated ids
        # from the rows (600). Emit the quantity the validator replays.
        "observedUniqueTraceIds": len({r["injectedOriginalTraceId"] for r in rows if r["observedOriginalTraceIds"]}),
        "rows": rows,
    }


PROBE_EXEC_ATTEMPTS = 3

POSTURE_CONFIG_DIGEST_CONTROLLERS = (
    "base-compose-overlay", "candidate-posture-overlay", "posture-catalog", "materializer",
)


def posture_config_document(cell: Mapping[str, Any]) -> dict[str, Any]:
    """Same formula as candidate_runtime.posture_config_document (strings only, so
    the two digests compare bit-exactly)."""
    return {
        "posture": cell["posture"]["id"],
        "environment": {str(key): str(value) for key, value in cell["posture"]["environment"].items()},
        "controllerDigests": {
            name: cell["installedControllerDigests"][name] for name in POSTURE_CONFIG_DIGEST_CONTROLLERS
        },
        "materializedSourceSha256": cell["materializedSourceSha256"],
    }


def _marker_matches(probe: Mapping[str, Any], value: str | None) -> bool | None:
    """True when ``value`` carries the loaded marker, False when it carries the
    not-loaded marker (or is absent/non-matching for exec-time probes), None when
    undecidable for a container-env probe."""
    if value is None:
        return None
    if "loadedWhenContains" in probe and probe["loadedWhenContains"] in value:
        return True
    if "loadedWhenEquals" in probe and value == probe["loadedWhenEquals"]:
        return True
    if "notLoadedWhenEquals" in probe:
        return False if value == probe["notLoadedWhenEquals"] else None
    return False


def probe_instrumentation_control(
    identifier: str, inspected: Mapping[str, Any], probe: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Observe whether a service's instrumentation control is enabled or disabled.

    ``container-env`` reads the exec-time environment Docker gave PID 1
    (``Config.Env``); ``pid1-environ`` reads ``/proc/1/environ`` inside the
    container (the environment the wrapper handed to the final program, e.g. the
    PYTHONPATH opentelemetry-instrument injects or the CoreCLR profiler variables
    instrument.sh exports); ``process-args`` reads the host-side ``docker top``
    argv (e.g. ``-javaagent`` on the Kafka JVM, ``--require`` on node);
    ``container-file`` reads a rendered config inside the container. Probes that
    need ``docker exec`` may be unavailable in shell-less images and then report
    ``indeterminate`` rather than guessing.
    """
    config = inspected.get("Config", {})
    variables = dict(value.split("=", 1) for value in config.get("Env", []) if "=" in value)
    evidence: dict[str, Any] = {
        "entrypoint": config.get("Entrypoint"),
        "cmd": config.get("Cmd"),
        "otelPlacementEnabled": variables.get("OTEL_PLACEMENT_ENABLED"),
    }
    if probe is None:
        return {"observedControl": "not-probed", "evidence": evidence}

    def exec_with_retry(argv: list[str]) -> tuple[Any, int]:
        # Run 2 (2026-09-24): one container-file read returned rc != 0 with an empty stderr in 1 of 12
        # enabled cells. Bounded retry (3 tries, 1 s apart); every try is counted in the evidence.
        for attempt in range(1, PROBE_EXEC_ATTEMPTS + 1):
            result = command(argv, check=False)
            if result.returncode == 0 or attempt == PROBE_EXEC_ATTEMPTS:
                return result, attempt
            time.sleep(1.0)
        raise AssertionError("unreachable")

    kind = probe.get("kind")
    decision: bool | None = None
    if kind == "container-env":
        value = variables.get(str(probe.get("variable")))
        evidence["containerEnv"] = {str(probe.get("variable")): value}
        decision = _marker_matches(probe, value)
    elif kind == "pid1-environ":
        result, tries = exec_with_retry(["docker", "exec", identifier, "cat", "/proc/1/environ"])
        if result.returncode != 0:
            evidence["pid1Environ"] = {"available": False, "attempts": tries, "error": result.stderr.strip()[:500]}
        else:
            environ = dict(
                item.split("=", 1) for item in result.stdout.split("\0") if "=" in item
            )
            value = environ.get(str(probe.get("variable")))
            evidence["pid1Environ"] = {"available": True, "attempts": tries, str(probe.get("variable")): value}
            decision = bool(_marker_matches(probe, value)) if value is not None else False
    elif kind == "process-args":
        result = command(["docker", "top", identifier, "-eo", "pid,args"], check=False)
        if result.returncode != 0:
            evidence["processArgs"] = {"available": False, "error": result.stderr.strip()[:500]}
        else:
            lines = [line.strip() for line in result.stdout.splitlines()[1:] if line.strip()]
            evidence["processArgs"] = {"available": True, "lines": lines}
            decision = any(probe.get("loadedWhenContains", "\0") in line for line in lines)
    elif kind == "container-file":
        result, tries = exec_with_retry(["docker", "exec", identifier, "cat", str(probe.get("path"))])
        if result.returncode != 0:
            evidence["containerFile"] = {"path": probe.get("path"), "available": False, "attempts": tries, "error": result.stderr.strip()[:500]}
        else:
            marker = probe.get("loadedWhenContains", "\0")
            evidence["containerFile"] = {
                "path": probe.get("path"), "available": True, "attempts": tries,
                "sha256": hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
                "containsLoadedMarker": marker in result.stdout,
            }
            decision = marker in result.stdout
    else:
        raise RuntimeFailure(f"unknown runtime probe kind {kind!r}")
    if decision is None:
        control = "indeterminate"
    else:
        control = "enabled" if decision else "disabled"
    return {"observedControl": control, "evidence": evidence}


def posture_proof(
    cell: Mapping[str, Any], environment: Mapping[str, str], collector_log: str,
    rendered_compose_config_sha256: str,
) -> dict[str, Any]:
    active = cell["posture"]["expected"]["activeApplicationServices"]
    catalog = read_json(Path(cell["remoteSourceRoot"]) / "candidate-posture-contract.json", "posture catalog")
    instrumentation = catalog["serviceInstrumentation"]
    services: dict[str, Any] = {}
    observed_signal_services = sorted({
        catalog_service(name)
        for name in re.findall(r"service\.name:\s*Str\(([^)]+)\)", collector_log)
    })
    loaded: list[str] = []
    control_exact = True
    # A timed (traffic-sweep) cell removes the upstream generator right after `up`, so it has no container to prove;
    # upstream-generator.json records its absence instead.
    not_started = sorted(cell["timing"]["upstreamGeneratorsOff"]) if is_timed(cell) else []
    for service in APP_SERVICES:
        if service in not_started:
            continue
        identifier = container_id(cell, service, environment)
        inspected = json.loads(command(["docker", "inspect", identifier]).stdout)[0]
        if inspected.get("Image") != cell["imageIds"][service]:
            raise RuntimeFailure(f"running image ID differs for {service}")
        variables = dict(value.split("=", 1) for value in inspected["Config"]["Env"] if "=" in value)
        row = instrumentation[service]
        expected_control = "enabled" if service in active else "disabled"
        expected_load = "loaded" if service in active else row["disabledLoadState"]
        probed = probe_instrumentation_control(identifier, inspected, row["runtimeProbe"])
        observed_control = probed["observedControl"]
        if observed_control == "enabled":
            observed_load = "loaded"
            loaded.append(service)
        elif observed_control == "disabled":
            observed_load = row["disabledLoadState"]
        else:
            observed_load = observed_control
        if row["runtimeProbe"] is not None and observed_control != expected_control:
            control_exact = False
        services[service] = {
            "containerId": identifier, "imageId": inspected["Image"],
            "otelSdkDisabled": variables.get("OTEL_SDK_DISABLED"),
            "tracesExporter": variables.get("OTEL_TRACES_EXPORTER"),
            "metricsExporter": variables.get("OTEL_METRICS_EXPORTER"),
            "logsExporter": variables.get("OTEL_LOGS_EXPORTER"),
            "expectedActive": service in active,
            "instrumentation": {
                "mechanism": row["mechanism"],
                "expectedControl": expected_control,
                "expectedLoadState": expected_load,
                "probe": row["runtimeProbe"],
                "observedControl": observed_control,
                "observedLoadState": observed_load,
                "evidence": probed["evidence"],
            },
        }
    excluded = {COLLECTOR_SELF_SERVICE}
    unexpected = sorted(set(observed_signal_services) - set(active) - excluded)
    proof = {
        "schemaVersion": 2, "posture": cell["posture"]["id"],
        "expectedActiveApplicationServices": active,
        "observedSignalServices": observed_signal_services,
        "unexpectedSignalServices": unexpected,
        "postureConfigSha256": hashlib.sha256(canonical_bytes(posture_config_document(cell))).hexdigest(),
        "renderedComposeConfigSha256": rendered_compose_config_sha256,
        "services": services,
        "loadedServices": sorted(loaded),
        "exact": not unexpected and control_exact,
    }
    if is_timed(cell):
        proof["notStartedServices"] = not_started
    return proof


def workload_path_check(cell: Mapping[str, Any], cell_root: Path, receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Does the first no-fault full cell's traced checkout path equal the literal?

    Rule (descriptor workload.pathCheck): every journey with error None has its
    trace's services minus the async consumers equal to the synchronous path,
    and at least one such journey exists. Read from the cell's own retained
    artifacts, so the terminal validator replays it byte-for-byte.
    """
    check = cell["workloadPathCheck"]
    expected = sorted(check["synchronousPath"])
    excluded = set(check["asynchronousServices"])
    result: dict[str, Any] = {
        "schemaVersion": 1, "kind": "otel-demo-offpath-workload-path-check-v1",
        "runId": cell["runId"], "runKey": cell["runKey"],
        "synchronousPath": expected, "asynchronousServices": sorted(excluded),
        "cellState": receipt.get("state"),
        "successfulJourneys": 0, "matchingJourneys": 0, "mismatchCount": 0,
        "observedSynchronousSets": {}, "firstMismatches": [], "verdict": "fail",
    }
    if receipt.get("state") != "valid":
        return result
    ledger = read_json(cell_root / "request-ledger.json", "request ledger")
    correlation = read_json(cell_root / "trace-correlation.json", "trace correlation")
    by_token = {row["requestToken"]: row for row in correlation["rows"]}
    counts: dict[str, int] = {}
    for request in ledger["requests"]:
        if request.get("error") is not None:
            continue
        result["successfulJourneys"] += 1
        observed = sorted(set(by_token[request["requestToken"]]["observedTraceServices"]) - excluded)
        label = ",".join(observed)
        counts[label] = counts.get(label, 0) + 1
        if observed == expected:
            result["matchingJourneys"] += 1
        else:
            result["mismatchCount"] += 1
            if len(result["firstMismatches"]) < 20:
                result["firstMismatches"].append({"requestToken": request["requestToken"], "observed": observed})
    result["observedSynchronousSets"] = dict(sorted(counts.items()))
    if result["successfulJourneys"] > 0 and result["mismatchCount"] == 0:
        result["verdict"] = "pass"
    return result


def content_manifest(root: Path, required: Sequence[str]) -> dict[str, Any]:
    rows = []
    for name in sorted(set(required) - {"content-manifest.json"}):
        path = root / name
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeFailure(f"required artifact {name} is not a regular file")
        payload = path.read_bytes()
        rows.append({"path": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    return {"schemaVersion": 1, "algorithm": "sha256", "files": rows}

# ------------------------------------------------------------------ traffic-sweep epoch (otel-traffic-sweep-v1)
# One route through the entry point at a per-cell rate, a fault at a seeded onset, the upstream generator off,
# protocol gates evaluated here before the next cell.  Every number comes from the cell's compiled timing
# (candidate_sweep.cell_timing via candidate_runtime._sweep_cell_contract); nothing below is an epoch literal.
# Seconds the fault worker resolves its target before the scheduled onset, so the pre-command stamp sits on the
# schedule (F1 allows 1 s) instead of after a `docker compose ps` round trip.
PRE_ONSET_RESOLVE_SECONDS = 3.0
ROUTE_PROBE_TIMEOUT_SECONDS = 5.0
ROUTE_READY_INTERVAL_SECONDS = 1.0
ROUTE_READY_TIMEOUT_SECONDS = 300
PROTOCOL_GATES_RELEASE_PATH = "repository/modules/otel-demo/validation/protocol_gates.py"
PROTOCOL_GATES_BLOCKING = ("F1", "G1", "G2", "G4")


def http_get(url: str, headers: Mapping[str, str], timeout: float) -> tuple[Any, int, Any]:
    """One GET: (status, body bytes, error). error is None iff HTTP 200. Never raises for an HTTP or socket
    failure (a timeout reads "timed out", the rule the ledger's outcome uses)."""
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            status = response.status
            return status, len(payload), None if status == 200 else f"HTTP {status}"
    except urllib.error.HTTPError as exc:
        return exc.code, 0, f"HTTPError: {exc}"
    except (OSError, http.client.HTTPException, ValueError) as exc:
        return None, 0, f"{type(exc).__name__}: {exc}"


def request_outcome(status: Any, error: Any) -> str:
    """ok iff HTTP 200; timeout iff the client error says "timed out"; failed otherwise (Hotel's mapping)."""
    if error is None and status == 200:
        return "ok"
    if isinstance(error, str) and "timed out" in error:
        return "timeout"
    return "failed"


def one_route_request(
    url: str, timeout: float, barrier: float, barrier_epoch: float, offset: float,
    token: str, trace_id: str, traceparent: str,
) -> dict[str, Any]:
    """One ledger row: scheduled at barrier + offset on the monotonic clock the fault receipt uses."""
    delay = barrier + offset - time.monotonic()
    if delay > 0:
        time.sleep(delay)
    started_monotonic, started = time.monotonic(), time.time()
    status, size, error = http_get(url, {"traceparent": traceparent, "x-obsplacement-request-token": token}, timeout)
    ended_monotonic, ended = time.monotonic(), time.time()
    return {
        "requestToken": token, "originalTraceId": trace_id, "traceparent": traceparent,
        "scheduledOffsetSeconds": offset, "scheduledAtEpoch": barrier_epoch + offset,
        "startedAtEpoch": started, "endedAtEpoch": ended,
        "startedMonotonic": started_monotonic, "endedMonotonic": ended_monotonic,
        "status": status, "bytes": size, "error": error, "outcome": request_outcome(status, error),
    }


def run_route_workload(
    base: str, workload: Mapping[str, Any], namespace: str, *, rate: float, offered: int, duration: float,
    barrier: float, barrier_epoch: float,
) -> dict[str, Any]:
    """Open loop on the cell's one route: request i is scheduled at barrier + i / rate; the worker cap and the
    client timeout come from the contract.  Returns no earlier than barrier + duration, so every rate observes
    the same window length."""
    url = base + workload["urlPath"]
    timeout = float(workload["requestTimeoutSeconds"])
    with ThreadPoolExecutor(max_workers=int(workload["concurrency"])) as pool:
        futures = []
        for sequence in range(offered):
            token, trace_id, traceparent = request_identity(namespace, sequence)
            futures.append(pool.submit(
                one_route_request, url, timeout, barrier, barrier_epoch, sequence / rate, token, trace_id, traceparent,
            ))
        requests = [future.result() for future in futures]
    remaining = barrier + duration - time.monotonic()
    if remaining > 0:
        time.sleep(remaining)
    return {
        "schemaVersion": 1, "kind": "otel-demo-route-ledger-v1", "method": workload["method"], "url": url,
        "tokenNamespace": namespace, "ratePerSecond": rate, "concurrency": int(workload["concurrency"]),
        "requestTimeoutSeconds": timeout, "durationSeconds": duration,
        "barrierMonotonic": barrier, "barrierEpoch": barrier_epoch,
        "startedAtEpoch": barrier_epoch, "endedAtEpoch": time.time(),
        "offered": offered,
        "completed": sum(item["outcome"] == "ok" for item in requests),
        "failed": sum(item["outcome"] != "ok" for item in requests),
        "requests": requests,
    }


# ------------------------------------------------------------------ off-path pilot: the multi-route task mix
# 2026-10-13 (otel-offpath-pilot-v1, main repo research/traffic-sweep/BUDGET_E.md): the upstream Locust task mix as an open
# loop with one ledger row per request (research/load-generator/DESIGN.md 2.3, 3.1 and 4.2).  The mix is data in each cell's
# compiled timing (``workloadMix``, candidate_offpath_pilot.build_mix); the request sequence is code here, a pure function of
# (token namespace, mix, offered count), so the terminal replays every row's route and parameters from the plan.  A cell
# whose timing has no ``workloadMix`` (every earlier epoch) runs ``run_route_workload`` exactly as before.
MIX_KIND = "otel-demo-upstream-locust-mix-v1"
MIX_LEDGER_KIND = "otel-demo-mix-ledger-v1"
# A dependent request waits for its predecessor's end at most the client timeout plus this slack (the predecessor's own
# deadline is the timeout); it is sent after that wait whatever the predecessor's outcome (upstream's behaviour).
MIX_DEPENDENCY_SLACK_SECONDS = 5.0
MIX_TASK_IDS = (
    "index", "browse_product", "get_recommendations", "get_ads", "view_cart", "add_to_cart", "checkout", "checkout_multi",
)


def has_mix(timing: Any) -> bool:
    """True for a compiled timing that carries the multi-route mix (the off-path pilot's cells only)."""
    return isinstance(timing, Mapping) and "workloadMix" in timing


def _mix_draw(namespace: str, task_index: int, label: str, modulus: int) -> int:
    digest = hashlib.sha256(f"{namespace}\0mix\0{task_index}\0{label}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % int(modulus)


def _mix_body(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def mix_task_requests(mix: Mapping[str, Any], namespace: str, task_index: int, task: str) -> list[dict[str, Any]]:
    """The requests of one upstream task, in order: route, method, target (path and query), body and whether the request
    needs its predecessor (``after``).  Upstream's tasks, parameters drawn from sha256 instead of random."""
    routes = mix["routes"]
    products, categories = mix["products"], mix["categories"]
    quantities, multi_adds, people = mix["quantities"], mix["multiAdds"], mix["people"]
    user = "u" + hashlib.sha256(f"{namespace}\0mix\0{task_index}\0user".encode("utf-8")).hexdigest()[:24]

    def request(route: str, *, product: str = "", category: str | None = None, body: Any = None, after: bool = False):
        spec = routes[route]
        path = spec["path"]
        if "{category}" in path:
            path = path.format(category=category) if category is not None else path.split("?")[0]
        else:
            path = path.format(productId=product) if "{productId}" in path else path
        return {
            "route": route, "method": spec["method"], "target": path,
            "body": None if body is None else _mix_body(body), "after": after,
        }

    def add_to_cart(index: int) -> list[dict[str, Any]]:
        product = products[_mix_draw(namespace, task_index, f"add{index}-product", len(products))]
        quantity = quantities[_mix_draw(namespace, task_index, f"add{index}-quantity", len(quantities))]
        return [
            request("product", product=product),
            request("add-to-cart", body={"item": {"productId": product, "quantity": quantity}, "userId": user}),
        ]

    def checkout() -> dict[str, Any]:
        person = dict(people[_mix_draw(namespace, task_index, "person", len(people))])
        person["userId"] = user
        return request("checkout", body=person, after=True)

    if task == "index":
        return [request("index")]
    if task == "browse_product":
        return [request("product", product=products[_mix_draw(namespace, task_index, "product", len(products))])]
    if task == "get_recommendations":
        return [request("recommendations", product=products[_mix_draw(namespace, task_index, "product", len(products))])]
    if task == "get_ads":
        return [request("ads", category=categories[_mix_draw(namespace, task_index, "category", len(categories))])]
    if task == "view_cart":
        return [request("view-cart")]
    if task == "add_to_cart":
        return add_to_cart(0)
    if task == "checkout":
        return add_to_cart(0) + [checkout()]
    if task == "checkout_multi":
        adds = multi_adds[_mix_draw(namespace, task_index, "adds", len(multi_adds))]
        rows: list[dict[str, Any]] = []
        for index in range(adds):
            rows += add_to_cart(index)
        return rows + [checkout()]
    raise RuntimeFailure(f"workload mix names an unknown task {task!r}")


def mix_plan(mix: Mapping[str, Any], namespace: str, offered: int) -> list[dict[str, Any]]:
    """The first ``offered`` requests of the mix for a token namespace.  Tasks come in smooth weighted round-robin order (nginx's
    algorithm; ties to the earlier task); each task's requests take the next plan slots; the last task is cut at ``offered``.
    A request's ``dependsOn`` is the sequence of the request it needs (the cart POST before a checkout), else None."""
    if mix.get("kind") != MIX_KIND:
        raise RuntimeFailure("workload mix kind differs")
    tasks = mix["tasks"]
    ids = tuple(task["id"] for task in tasks)
    weights = [int(task["weight"]) for task in tasks]
    if ids != MIX_TASK_IDS or sum(weights) != int(mix["cycleWeight"]) or any(weight < 1 for weight in weights):
        raise RuntimeFailure("workload mix tasks or weights differ from the upstream task set")
    total = sum(weights)
    current = [0] * len(tasks)
    plan: list[dict[str, Any]] = []
    task_index = 0
    while len(plan) < offered:
        for position, weight in enumerate(weights):
            current[position] += weight
        pick = max(range(len(tasks)), key=lambda position: (current[position], -position))
        current[pick] -= total
        for step, row in enumerate(mix_task_requests(mix, namespace, task_index, ids[pick])):
            sequence = len(plan)
            plan.append({
                "sequence": sequence, "taskIndex": task_index, "task": ids[pick], "step": step, "route": row["route"],
                "method": row["method"], "target": row["target"], "body": row["body"],
                "bodySha256": None if row["body"] is None else hashlib.sha256(row["body"]).hexdigest(),
                "dependsOn": sequence - 1 if row["after"] else None,
            })
        task_index += 1
    del plan[offered:]
    return plan


def http_post(url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> tuple[Any, int, Any]:
    """One POST of a JSON body: (status, body bytes, error), error None iff HTTP 200; never raises for an HTTP or socket failure
    (the same mapping as ``http_get``)."""
    request = urllib.request.Request(
        url, data=body, method="POST", headers={"content-type": "application/json", **dict(headers)},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            status = response.status
            return status, len(payload), None if status == 200 else f"HTTP {status}"
    except urllib.error.HTTPError as exc:
        return exc.code, 0, f"HTTPError: {exc}"
    except (OSError, http.client.HTTPException, ValueError) as exc:
        return None, 0, f"{type(exc).__name__}: {exc}"


def http_exchange(method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float) -> tuple[Any, int, Any]:
    if method == "GET":
        return http_get(url, headers, timeout)
    if method == "POST":
        return http_post(url, body if body is not None else b"", headers, timeout)
    raise RuntimeFailure(f"unsupported request method {method!r}")


def one_mix_request(
    base: str, timeout: float, barrier: float, barrier_epoch: float, offset: float, item: Mapping[str, Any],
    identity: tuple[str, str, str], dependency: threading.Event | None, finished: threading.Event | None,
) -> dict[str, Any]:
    """One ledger row: scheduled at barrier + offset on the monotonic clock the fault receipt uses; a request with a predecessor
    starts at max(its slot, the predecessor's end) and is sent whatever the predecessor's outcome."""
    token, trace_id, traceparent = identity
    try:
        delay = barrier + offset - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        if dependency is not None:
            dependency.wait(timeout + MIX_DEPENDENCY_SLACK_SECONDS)
        started_monotonic, started = time.monotonic(), time.time()
        status, size, error = http_exchange(
            item["method"], base + item["target"], {"traceparent": traceparent, "x-obsplacement-request-token": token},
            item["body"], timeout,
        )
        ended_monotonic, ended = time.monotonic(), time.time()
    finally:
        if finished is not None:
            finished.set()
    return {
        "requestToken": token, "originalTraceId": trace_id, "traceparent": traceparent,
        "scheduledOffsetSeconds": offset, "scheduledAtEpoch": barrier_epoch + offset,
        "startedAtEpoch": started, "endedAtEpoch": ended,
        "startedMonotonic": started_monotonic, "endedMonotonic": ended_monotonic,
        "status": status, "bytes": size, "error": error, "outcome": request_outcome(status, error),
        "route": item["route"], "task": item["task"], "taskIndex": item["taskIndex"], "step": item["step"],
        "method": item["method"], "target": item["target"], "bodySha256": item["bodySha256"],
        "dependsOn": item["dependsOn"],
    }


def mix_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Requests per task and per route of a ledger's rows (sorted keys), recorded in the ledger and replayed by the terminal."""
    tasks: dict[str, int] = {}
    routes: dict[str, int] = {}
    for row in rows:
        tasks[row["task"]] = tasks.get(row["task"], 0) + 1
        routes[row["route"]] = routes.get(row["route"], 0) + 1
    return {"taskCounts": dict(sorted(tasks.items())), "routeCounts": dict(sorted(routes.items()))}


def run_mix_workload(
    base: str, workload: Mapping[str, Any], mix: Mapping[str, Any], namespace: str, *, rate: float, offered: int,
    duration: float, barrier: float, barrier_epoch: float,
) -> dict[str, Any]:
    """Open loop over the mix: request i is scheduled at barrier + i / rate; the worker cap and the client timeout come from the
    contract.  Returns no earlier than barrier + duration, like ``run_route_workload``."""
    timeout = float(workload["requestTimeoutSeconds"])
    plan = mix_plan(mix, namespace, offered)
    waited_for = {item["dependsOn"] for item in plan if item["dependsOn"] is not None}
    events = {sequence: threading.Event() for sequence in waited_for}
    with ThreadPoolExecutor(max_workers=int(workload["concurrency"])) as pool:
        futures = []
        for item in plan:
            sequence = item["sequence"]
            futures.append(pool.submit(
                one_mix_request, base, timeout, barrier, barrier_epoch, sequence / rate, item,
                request_identity(namespace, sequence),
                None if item["dependsOn"] is None else events[item["dependsOn"]], events.get(sequence),
            ))
        requests = [future.result() for future in futures]
    remaining = barrier + duration - time.monotonic()
    if remaining > 0:
        time.sleep(remaining)
    return {
        "schemaVersion": 1, "kind": MIX_LEDGER_KIND, "method": "MIX", "url": base + "/",
        "tokenNamespace": namespace, "ratePerSecond": rate, "concurrency": int(workload["concurrency"]),
        "requestTimeoutSeconds": timeout, "durationSeconds": duration,
        "barrierMonotonic": barrier, "barrierEpoch": barrier_epoch,
        "startedAtEpoch": barrier_epoch, "endedAtEpoch": time.time(),
        "offered": offered,
        "completed": sum(item["outcome"] == "ok" for item in requests),
        "failed": sum(item["outcome"] != "ok" for item in requests),
        "mixSha256": hashlib.sha256(canonical_bytes(mix)).hexdigest(),
        **mix_counts(requests),
        "requests": requests,
    }


def run_cell_workload(
    base: str, workload: Mapping[str, Any], timing: Mapping[str, Any], namespace: str, *, rate: float, offered: int,
    duration: float, barrier: float, barrier_epoch: float,
) -> dict[str, Any]:
    """The timed cell's workload: the mix when the compiled timing carries one, else the cell's one route."""
    if has_mix(timing):
        return run_mix_workload(
            base, workload, timing["workloadMix"], namespace, rate=rate, offered=offered, duration=duration,
            barrier=barrier, barrier_epoch=barrier_epoch,
        )
    return run_route_workload(
        base, workload, namespace, rate=rate, offered=offered, duration=duration, barrier=barrier,
        barrier_epoch=barrier_epoch,
    )


def timed_probe(receipt: dict[str, Any] | None, phase: str, url: str) -> bool:
    """One route probe (token readiness-not-scored, never in the ledger), stamped into receipt["probes"] so the
    analysis can exclude its window from sensor scoring."""
    started = time.monotonic()
    status, _, error = http_get(url, {"x-obsplacement-request-token": READINESS_TOKEN}, ROUTE_PROBE_TIMEOUT_SECONDS)
    available = error is None and status == 200
    if receipt is not None:
        receipt["probes"].append({
            "phase": phase, "startMonotonic": started, "endMonotonic": time.monotonic(),
            "available": available, "status": status,
        })
    return available


def wait_route_ready(
    base: str, workload: Mapping[str, Any], deadline: datetime, *, receipt: dict[str, Any] | None = None,
    phase: str = "readiness", timeout: float = ROUTE_READY_TIMEOUT_SECONDS,
) -> float:
    """Poll the cell's route until it returns 200; the monotonic time it did."""
    url = base + workload["urlPath"]
    end = min(time.monotonic() + timeout, time.monotonic() + max(0.0, (deadline - datetime.now(timezone.utc)).total_seconds()))
    while time.monotonic() < end:
        if timed_probe(receipt, phase, url):
            return time.monotonic()
        time.sleep(ROUTE_READY_INTERVAL_SECONDS)
    raise RuntimeFailure("route readiness deadline expired")


def upstream_generator_state(cell: Mapping[str, Any], environment: Mapping[str, str]) -> dict[str, Any]:
    """Every container (running or not) of each upstream generator the cell turns off: must be none.  Asked of
    the Docker engine by Compose labels, not of the Compose CLI, so a service with no container is an empty answer
    rather than a CLI-version-dependent error."""
    project = cell["compose"]["project"]
    services = {}
    for service in cell["timing"]["upstreamGeneratorsOff"]:
        result = command([
            "docker", "ps", "-a", "-q",
            "--filter", f"label=com.docker.compose.project={project}",
            "--filter", f"label=com.docker.compose.service={service}",
        ], check=False)
        services[service] = {
            "returnCode": result.returncode,
            "containers": sorted(line for line in result.stdout.splitlines() if line.strip()),
        }
    return {"observedAt": now_iso(), "services": services}


def _nanocpus(identifier: str) -> int:
    inspected = json.loads(command(["docker", "inspect", identifier]).stdout)[0]
    return int(inspected.get("HostConfig", {}).get("NanoCpus") or 0)


def _cpus_argument(nanocpus: int) -> str:
    if nanocpus <= 0 or nanocpus % 1_000_000:
        raise RuntimeFailure(f"CPU quota {nanocpus} has no exact --cpus spelling")
    return "%d.%03d" % (nanocpus // 1_000_000_000, (nanocpus % 1_000_000_000) // 1_000_000)


# ------------------------------------------------------------------ campaign B: H10 and H4 (otel-repeat-episodes-v1)
# H10 (no readiness probe from the fault onset to the end of the hold) and H4 (stamp the freeze) are named in the cell's
# compiled timing (``duringFaultProbe``, ``freezeStamps``) and exist only in the repeat epoch; a sweep or quiet cell
# carries neither key and runs the code below it exactly as before.
ENTRY_ROUTE_NOT_PROBED = "not-probed-h10"
FREEZE_KIND = "otel-demo-fault-freeze-stamps-v1"
DOCKER_EVENTS_FILE = "docker-events.json"
DOCKER_EVENTS_KIND = "otel-demo-fault-docker-events-v1"
DOCKER_EVENT_ACTIONS = ("pause", "unpause")
# The pause event is emitted by the daemon after the kernel confirms the freeze, between the Compose command's issue and
# its return; the tolerance covers the wall-to-monotonic mapping (the barrier's two clock reads) and rounding.
FREEZE_EVENT_TOLERANCE_SECONDS = 0.25
DOCKER_EVENTS_MAPPING = (
    "offsetSeconds = timeNano / 1e9 - clock.barrierEpoch (seconds after the shared barrier); "
    "monotonic = clock.barrierMonotonic + offsetSeconds"
)


# 2026-10-12 (load pilot): every in-flight request of the open-loop generator holds one socket in this process, and a
# systemd unit's default soft RLIMIT_NOFILE is 1024.  At 200 req/s a binding throttle can hold rate x timeout = 3000
# requests open, and an EMFILE would be recorded as a failed request of the target.  A cell whose compiled timing names
# ``generatorOpenFilesMinimum`` raises the soft limit to it (never above the hard limit) before any container starts, or is
# refused.  A timing without the key (every earlier epoch) leaves the limits as they are.
GENERATOR_OPEN_FILES_KEY = "generatorOpenFilesMinimum"


def ensure_generator_open_files(
    timing: Mapping[str, Any], *, getrlimit: Any = None, setrlimit: Any = None,
) -> dict[str, Any] | None:
    """Raise RLIMIT_NOFILE's soft limit to the cell's declared minimum, or refuse; None when the cell declares none."""
    if GENERATOR_OPEN_FILES_KEY not in timing:
        return None
    import resource
    getrlimit = getrlimit or resource.getrlimit
    setrlimit = setrlimit or resource.setrlimit
    need = timing[GENERATOR_OPEN_FILES_KEY]
    if type(need) is not int or need < int(timing["concurrency"]):
        raise RuntimeFailure("generatorOpenFilesMinimum must be an integer covering the cell's concurrency")
    soft, hard = getrlimit(resource.RLIMIT_NOFILE)
    before = {"soft": soft, "hard": hard}
    unlimited = resource.RLIM_INFINITY
    if soft != unlimited and soft < need:
        if hard != unlimited and hard < need:
            raise RuntimeFailure(f"open-file hard limit {hard} is below the generator's declared minimum {need}")
        setrlimit(resource.RLIMIT_NOFILE, (need, hard))
        soft, hard = getrlimit(resource.RLIMIT_NOFILE)
        if soft != unlimited and soft < need:
            raise RuntimeFailure(f"open-file soft limit stayed at {soft}, below the generator's declared minimum {need}")
    return {"minimum": need, "before": before, "after": {"soft": soft, "hard": hard}}


def h10_enabled(timing: Mapping[str, Any]) -> bool:
    """True iff the compiled timing says no probe during the fault (the key is absent from every other epoch)."""
    return timing.get("duringFaultProbe") is False


def freeze_enabled(timing: Mapping[str, Any]) -> bool:
    return timing.get("freezeStamps") is True


def require_harness_flags_consistent(cell: Mapping[str, Any]) -> None:
    """H10/H4 belong to the repeat epoch's cells and nothing else: the flags, the scenario's entry-route expectation and
    the epoch must agree before any container is started."""
    timing = cell["timing"]
    repeat = cell.get("studyEpoch") in REPEAT_STUDY_EPOCHS
    if ("duringFaultProbe" in timing) != repeat or ("freezeStamps" in timing) != repeat:
        raise RuntimeFailure("only the repeat-episodes epoch's compiled timing names H10 (duringFaultProbe) and H4 (freezeStamps)")
    if repeat and (timing["duringFaultProbe"] is not False or timing["freezeStamps"] is not True):
        raise RuntimeFailure("the repeat-episodes epoch runs with H10 and H4 on")
    fault = cell["fault"]
    if fault["scenario"] is not None and (fault["entryRouteDuringFault"] == ENTRY_ROUTE_NOT_PROBED) != h10_enabled(timing):
        raise RuntimeFailure("the scenario's entry-route expectation differs from the cell's H10 flag")


def freeze_stamps(action: str, issued: float, returned: float, readback: float, barrier: float) -> dict[str, Any]:
    """H4: the monotonic stamps around the fault command, on the receipt's clock.  ``commandIssuedMonotonic`` is
    ``startedMonotonic`` (taken immediately before the command) and ``stateReadbackMonotonic`` is ``appliedMonotonic``."""
    return {
        "schemaVersion": 1, "kind": FREEZE_KIND, "action": action,
        "commandIssuedMonotonic": issued, "commandReturnedMonotonic": returned, "stateReadbackMonotonic": readback,
        "commandIssuedOffsetSeconds": issued - barrier, "commandReturnedOffsetSeconds": returned - barrier,
        "stateReadbackOffsetSeconds": readback - barrier,
        "dockerEventsFile": DOCKER_EVENTS_FILE if action == "pause" else None,
    }


class DockerEvents(NamedTuple):
    """A running ``docker events`` stream plus the files its output goes to (outside the cell artifact root)."""

    process: subprocess.Popen
    out: Path
    err: Path
    argv: list[str]
    since: int


def docker_events_argv(project: str, since: int) -> list[str]:
    return [
        "docker", "events", "--since", str(int(since)), "--filter", "type=container",
        *(item for action in DOCKER_EVENT_ACTIONS for item in ("--filter", f"event={action}")),
        "--filter", f"label=com.docker.compose.project={project}", "--format", "{{json .}}",
    ]


def start_docker_events(cell: Mapping[str, Any]) -> DockerEvents:
    """Start a live stream of the project's pause and unpause events.  A stream, not a ``--since/--until`` query after
    the fact: the daemon replays only a bounded buffer of recent events, which a 25-container stack's health checks can
    roll over within a cell.  Output goes to files beside nothing the cell retains, as ``start_capture``'s does."""
    since = int(time.time()) - 1
    argv = docker_events_argv(cell["compose"]["project"], since)
    out_handle, out_name = tempfile.mkstemp(prefix="docker-events-", suffix=".jsonl")
    err_handle, err_name = tempfile.mkstemp(prefix="docker-events-", suffix=".err")
    try:
        process = subprocess.Popen(argv, stdout=out_handle, stderr=err_handle, stdin=subprocess.DEVNULL)
    finally:
        os.close(out_handle)
        os.close(err_handle)
    return DockerEvents(process, Path(out_name), Path(err_name), argv, since)


def stop_docker_events(handle: DockerEvents) -> dict[str, Any]:
    """Stop the stream and return what it produced: its argv, whether it had already exited, its raw JSON lines."""
    process = handle.process
    exited_before_stop = process.poll() is not None
    try:
        if not exited_before_stop:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        text = handle.out.read_text(encoding="utf-8", errors="replace") if handle.out.exists() else ""
        stderr = handle.err.read_text(encoding="utf-8", errors="replace") if handle.err.exists() else ""
    finally:
        for path in (handle.out, handle.err):
            with contextlib.suppress(OSError):
                path.unlink()
    return {
        "argv": list(handle.argv), "sinceEpoch": handle.since, "exitedBeforeStop": exited_before_stop,
        "returnCode": process.returncode, "stderr": stderr[:2000], "error": None,
        "raw": [line for line in text.splitlines() if line.strip()],
    }


def parse_docker_events(raw: Sequence[str], clock: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The stream's JSON lines as events with their time on the cell's clock (``DOCKER_EVENTS_MAPPING``).  A line that
    is not one event object with an integer ``timeNano`` raises."""
    events, problems = parse_docker_events_lenient(raw, clock)
    if problems:
        raise RuntimeFailure(problems[0])
    return events


def parse_docker_events_lenient(raw: Sequence[str], clock: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Like ``parse_docker_events`` but a bad line is skipped and named in the second result (decision 69: H4 is
    recorded, never blocking, so one unparseable line must not cost the cell)."""
    events: list[dict[str, Any]] = []
    problems: list[str] = []
    for line in raw:
        try:
            row = json.loads(line)
        except ValueError:
            problems.append(f"docker event line is not JSON: {line[:200]!r}")
            continue
        actor = row.get("Actor") if isinstance(row, dict) else None
        if not isinstance(row, dict) or not isinstance(actor, dict) or type(row.get("timeNano")) is not int:
            problems.append(f"docker event line has no Actor or integer timeNano: {line[:200]!r}")
            continue
        attributes = actor.get("Attributes") if isinstance(actor.get("Attributes"), dict) else {}
        offset = row["timeNano"] / 1e9 - float(clock["barrierEpoch"])
        events.append({
            "action": row.get("Action", row.get("status")), "containerId": actor.get("ID", row.get("id")),
            "service": attributes.get("com.docker.compose.service"), "timeNano": row["timeNano"],
            "offsetSeconds": offset, "monotonic": float(clock["barrierMonotonic"]) + offset,
        })
    return events, problems


def freeze_status(reasons: Sequence[Mapping[str, str]]) -> str:
    """``ok`` with no reason; ``missing`` if every reason is an absence (no stream, no event); else ``contradictory``."""
    if not reasons:
        return "ok"
    return "missing" if all(row["kind"] == "missing" for row in reasons) else "contradictory"


def freeze_stamp_check(intervention: Mapping[str, Any]) -> dict[str, Any]:
    """H4 over the receipt's own freeze stamps, as a record (decision 69: recorded, never blocking): the stamps must be
    ordered and agree with the receipt's ``startedMonotonic`` and ``appliedMonotonic``.  Pure: the terminal replays it."""
    freeze = intervention.get("freeze")
    reasons: list[dict[str, str]] = []
    if not isinstance(freeze, Mapping):
        reasons.append({"kind": "missing", "reason": "the receipt carries no freeze stamps"})
    else:
        issued, returned, readback = (freeze["commandIssuedMonotonic"], freeze["commandReturnedMonotonic"], freeze["stateReadbackMonotonic"])
        if not issued <= returned <= readback:
            reasons.append({"kind": "contradictory", "reason": "the freeze stamps are not ordered issued <= returned <= readback"})
        if issued != intervention.get("startedMonotonic"):
            reasons.append({"kind": "contradictory", "reason": "commandIssuedMonotonic differs from the receipt's startedMonotonic"})
        if readback != intervention.get("appliedMonotonic"):
            reasons.append({"kind": "contradictory", "reason": "stateReadbackMonotonic differs from the receipt's appliedMonotonic"})
        reverting = intervention.get("revertingMonotonic")
        if isinstance(reverting, (int, float)) and not returned <= reverting:
            reasons.append({"kind": "contradictory", "reason": "the freeze command returned after the revert command was issued"})
    return {"status": freeze_status(reasons), "failures": len(reasons), "reasons": reasons}


def docker_events_verdict(
    events: Sequence[Mapping[str, Any]], stream: Mapping[str, Any], intervention: Mapping[str, Any] | None,
    problems: Sequence[str] = (),
) -> dict[str, Any]:
    """H4 over the target container's events, as a record (decision 69: never blocking).  ``status`` is ``ok`` iff
    there is exactly one ``pause`` in [command issued, command returned] and exactly one ``unpause`` in [revert command
    issued, revert command returned], each widened by the declared tolerance, on a stream that was alive when stopped;
    ``missing`` if everything wrong is an absence (no stream, no event); ``contradictory`` otherwise.  ``failures`` counts
    the reasons.  Pure: the terminal replays it from the retained record."""
    reasons: list[dict[str, str]] = []

    def note(kind: str, reason: str) -> None:
        reasons.append({"kind": kind, "reason": reason})

    freeze = intervention.get("freeze") if isinstance(intervention, Mapping) else None
    target = intervention.get("targetContainerId") if isinstance(intervention, Mapping) else None
    if stream.get("error") is not None:
        note("missing", f"the docker events stream could not be used: {stream['error']}")
    elif stream.get("exitedBeforeStop") is not False:
        note("missing", f"the docker events stream had exited before the fault settled (return code {stream.get('returnCode')})")
    for problem in problems:
        note("contradictory", problem)
    empty = {"pauseEvents": None, "unpauseEvents": None, "pauseOffsetSeconds": None, "unpauseOffsetSeconds": None,
             "onsetIntervalSeconds": None, "otherContainerEvents": None}
    if not isinstance(freeze, Mapping) or target is None:
        note("missing", "the fault receipt carries no freeze stamps or target container")
        return {**empty, "status": freeze_status(reasons), "failures": len(reasons), "reasons": reasons}
    mine = [row for row in events if row["containerId"] == target]
    pauses = [row for row in mine if row["action"] == "pause"]
    unpauses = [row for row in mine if row["action"] == "unpause"]
    for name, rows in (("pause", pauses), ("unpause", unpauses)):
        if not rows:
            note("missing", f"no {name} event of the target container")
        elif len(rows) > 1:
            note("contradictory", f"{len(rows)} {name} events of the target container, not exactly one")
    tolerance = FREEZE_EVENT_TOLERANCE_SECONDS
    pause_at = unpause_at = None
    if len(pauses) == 1:
        pause_at = pauses[0]["offsetSeconds"]
        low, high = freeze["commandIssuedOffsetSeconds"], freeze["commandReturnedOffsetSeconds"]
        if not low - tolerance <= pause_at <= high + tolerance:
            note("contradictory", f"the pause event ({pause_at:.3f} s) is outside the pause command [{low:.3f}, {high:.3f}] s")
    if len(unpauses) == 1:
        unpause_at = unpauses[0]["offsetSeconds"]
        low, high = intervention["revertingMonotonicOffsetSeconds"], intervention["actualOffsetMonotonicOffsetSeconds"]
        if not low - tolerance <= unpause_at <= high + tolerance:
            note("contradictory", f"the unpause event ({unpause_at:.3f} s) is outside the unpause command [{low:.3f}, {high:.3f}] s")
    if pause_at is not None and unpause_at is not None and not pause_at < unpause_at:
        note("contradictory", "the unpause event does not follow the pause event")
    return {
        "pauseEvents": len(pauses), "unpauseEvents": len(unpauses),
        "pauseOffsetSeconds": pause_at, "unpauseOffsetSeconds": unpause_at,
        "onsetIntervalSeconds": None if pause_at is None else [freeze["commandIssuedOffsetSeconds"], pause_at],
        "otherContainerEvents": len(events) - len(mine),
        "status": freeze_status(reasons), "failures": len(reasons), "reasons": reasons,
    }


def docker_events_record(
    cell: Mapping[str, Any], stream: Mapping[str, Any], barrier: float, barrier_epoch: float,
    stopped_at: Mapping[str, Any], intervention: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """``docker-events.json``: the stream's raw lines, the events parsed onto the cell's clock, the verdict (a record:
    ``status`` ok | missing | contradictory, ``failures``, ``reasons``; decision 69), and the mapping (the barrier's two
    clocks plus one more pair read when the stream stopped, so the analysis can check drift).  The terminal re-derives
    ``events``, ``parseProblems`` and ``verdict`` from ``raw``, ``clock`` and the receipt."""
    clock = {
        "barrierMonotonic": barrier, "barrierEpoch": barrier_epoch, "mapping": DOCKER_EVENTS_MAPPING,
        "stopPair": {"epoch": stopped_at["epoch"], "monotonic": stopped_at["monotonic"]},
    }
    events, problems = parse_docker_events_lenient(stream["raw"], clock)
    return {
        "schemaVersion": 1, "kind": DOCKER_EVENTS_KIND, "runId": cell["runId"], "service": cell["fault"]["service"],
        "containerId": None if intervention is None else intervention.get("targetContainerId"),
        "clock": clock,
        "stream": {key: stream[key] for key in ("argv", "sinceEpoch", "exitedBeforeStop", "returnCode", "stderr", "error")},
        "raw": list(stream["raw"]), "events": events, "parseProblems": problems,
        "verdict": docker_events_verdict(events, stream, intervention, problems),
    }


def inject_sweep_fault(
    cell: Mapping[str, Any], environment: Mapping[str, str], base: str, barrier: float, output: dict[str, Any],
) -> None:
    """Apply the cell's fault at barrier + timing.faultOnsetSeconds for timing.faultHoldSeconds.

    The target container (one Compose round trip) and, for a CPU throttle, the host's CPU count are resolved when the
    worker starts at the barrier, a minute before the onset, so a slow Compose CLI cannot delay the stamp (review
    2026-10-03, M2); only a direct `docker inspect` (the pre-state and the original quota) runs
    PRE_ONSET_RESOLVE_SECONDS before the onset.  ``startedMonotonic`` is stamped immediately before the apply
    command (F-ADH-085: pre-command), ``appliedMonotonic`` after the change is observed in the container's state,
    ``revertingMonotonic`` immediately before the revert command and ``revertedMonotonic`` after it returns.
    Every route probe inside the measurement is stamped into ``probes``.
    """
    fault, timing = cell["fault"], cell["timing"]
    scenario, service, action = fault["scenario"], fault["service"], fault["action"]
    onset, hold = float(timing["faultOnsetSeconds"]), float(timing["faultHoldSeconds"])
    probe_url = base + cell["workload"]["urlPath"]
    probe_during = not h10_enabled(timing)      # H10 (repeat epoch): no route probe from the onset to the end of the hold
    stamp_freeze = freeze_enabled(timing)       # H4 (repeat epoch): the freeze stamps
    source = Path(cell["remoteSourceRoot"])
    receipt: dict[str, Any] = {
        "scenario": scenario, "service": service, "action": action,
        "targetContainerId": None, "targetImageId": None,
        "preState": None, "duringStateSamples": [], "postState": None,
        "scheduledOnsetSeconds": onset, "scheduledHoldSeconds": hold,
        "barrierMonotonic": barrier, "onsetSource": "pre-command",
        "startedMonotonic": None, "actualOnsetMonotonicOffsetSeconds": None,
        "appliedMonotonic": None, "appliedMonotonicOffsetSeconds": None,
        "revertingMonotonic": None, "revertingMonotonicOffsetSeconds": None,
        "revertedMonotonic": None, "actualOffsetMonotonicOffsetSeconds": None,
        "readyAtMonotonic": None, "duringRouteAvailable": None,
        "throttle": None, "probes": [],
        "manifested": False, "recovered": False, "successful": False,
        "error": None,
    }
    if stamp_freeze:
        receipt["freeze"] = None
    applied = False
    revert_argv: list[str] | None = None
    try:
        if action not in ("pause", "cpu-throttle"):
            raise RuntimeFailure(f"timed fault action {action!r} is not implemented")
        identifier = container_id(cell, service, environment)
        host = (
            int(command(["docker", "info", "--format", "{{.NCPU}}"]).stdout.strip()) * 1_000_000_000
            if action == "cpu-throttle" else None
        )
        lead = barrier + onset - PRE_ONSET_RESOLVE_SECONDS - time.monotonic()
        if lead > 0:
            time.sleep(lead)
        inspected = json.loads(command(["docker", "inspect", identifier]).stdout)[0]
        receipt["targetContainerId"] = identifier
        receipt["targetImageId"] = inspected["Image"]
        receipt["preState"] = inspected["State"]
        if action == "pause":
            apply_argv = compose(cell, "pause", service)
            revert_argv = compose(cell, "unpause", service)
        else:
            original = int(inspected.get("HostConfig", {}).get("NanoCpus") or 0)
            # `docker update --cpus 0` is a no-op (the daemon skips a zero NanoCpus; Hotel lmt_faults.py, measured
            # on fb14srv4 2026-09-28), so an unset original quota is lifted to every host CPU instead.
            restore = original if original > 0 else host
            receipt["throttle"] = {
                "originalNanoCpus": original, "appliedNanoCpus": int(fault["nanoCpus"]),
                "restoreNanoCpus": restore, "hostNanoCpus": host,
                "duringNanoCpus": None, "postNanoCpus": None,
            }
            apply_argv = ["docker", "update", "--cpus", _cpus_argument(int(fault["nanoCpus"])), identifier]
            revert_argv = ["docker", "update", "--cpus", _cpus_argument(restore), identifier]
        remaining = barrier + onset - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        began = time.monotonic()
        receipt["startedMonotonic"] = began
        receipt["actualOnsetMonotonicOffsetSeconds"] = began - barrier
        applied = True
        command(apply_argv, cwd=source, env=environment)
        returned = time.monotonic()
        during = json.loads(command(["docker", "inspect", identifier]).stdout)[0]
        receipt["duringStateSamples"].append(during["State"])
        receipt["appliedMonotonic"] = time.monotonic()
        receipt["appliedMonotonicOffsetSeconds"] = receipt["appliedMonotonic"] - barrier
        if stamp_freeze:
            receipt["freeze"] = freeze_stamps(action, began, returned, receipt["appliedMonotonic"], barrier)
        if probe_during:
            receipt["duringRouteAvailable"] = timed_probe(receipt, "during-fault", probe_url)
        state = during["State"]
        if action == "pause":
            state_holds = bool(state.get("Running") and state.get("Paused"))
        else:
            observed = int(during.get("HostConfig", {}).get("NanoCpus") or 0)
            receipt["throttle"]["duringNanoCpus"] = observed
            state_holds = bool(state.get("Running") and not state.get("Paused") and observed == int(fault["nanoCpus"]))
        route_holds = (
            receipt["duringRouteAvailable"] is False
            if fault["entryRouteDuringFault"] == "must-be-unavailable" else True
        )
        receipt["manifested"] = state_holds and route_holds
        remaining = hold - (time.monotonic() - began)
        if remaining > 0:
            time.sleep(remaining)
        receipt["revertingMonotonic"] = time.monotonic()
        receipt["revertingMonotonicOffsetSeconds"] = receipt["revertingMonotonic"] - barrier
        command(revert_argv, cwd=source, env=environment)
        applied = False
        receipt["revertedMonotonic"] = time.monotonic()
        receipt["actualOffsetMonotonicOffsetSeconds"] = receipt["revertedMonotonic"] - barrier
        receipt["readyAtMonotonic"] = wait_route_ready(
            base, cell["workload"], datetime.now(timezone.utc) + timedelta(minutes=5),
            receipt=receipt, phase="post-revert",
        )
        post = json.loads(command(["docker", "inspect", identifier]).stdout)[0]
        receipt["postState"] = post["State"]
        recovered = bool(post["State"].get("Running") and not post["State"].get("Paused"))
        if action == "cpu-throttle":
            observed = int(post.get("HostConfig", {}).get("NanoCpus") or 0)
            receipt["throttle"]["postNanoCpus"] = observed
            recovered = recovered and observed == receipt["throttle"]["restoreNanoCpus"]
        receipt["recovered"] = recovered
        receipt["successful"] = receipt["manifested"] and receipt["recovered"]
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if applied and revert_argv is not None:
            command(revert_argv, cwd=source, env=environment, check=False)
    output.update(receipt)


def load_protocol_gates(path: Path, expected_sha256: str):
    """The vendored shared gates, loaded by path (python3 -I drops this directory from sys.path) and only after
    their bytes match the installed controller digest."""
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise RuntimeFailure("protocol gate module bytes differ from the installed controller digest")
    import importlib.util
    spec = importlib.util.spec_from_file_location("otel_candidate_remote_protocol_gates", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeFailure("protocol gate module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def protocol_cell(
    cell: Mapping[str, Any], ledger: Mapping[str, Any], intervention: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """The normalised cell of protocol_gates.py (GATES.md mapping table), barrier = 0, one monotonic clock."""
    timing = cell["timing"]
    barrier = float(ledger["barrierMonotonic"])
    normalised: dict[str, Any] = {
        "cellId": cell["runId"],
        "kind": "fault" if cell["fault"]["scenario"] is not None else "nofault",
        "posture": cell["posture"]["id"],
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
                "scheduled": float(row["scheduledOffsetSeconds"]),
                "started": float(row["startedMonotonic"]) - barrier,
                "ended": float(row["endedMonotonic"]) - barrier,
                "status": row["outcome"],
            }
            for row in ledger["requests"]
        ],
    }
    if intervention is not None:
        normalised["fault"] = {
            "scheduledOnset": float(timing["faultOnsetSeconds"]),
            "scheduledHold": float(timing["faultHoldSeconds"]),
            # startedMonotonic is stamped immediately before the command (F-ADH-085); appliedMonotonic after the
            # change was observed, so it is an upper bound of the command's return.
            "onsetCommandIssued": float(intervention["actualOnsetMonotonicOffsetSeconds"]),
            "onsetCommandReturned": float(intervention["appliedMonotonicOffsetSeconds"]),
            "revertCommandIssued": float(intervention["revertingMonotonicOffsetSeconds"]),
            "revertCommandReturned": float(intervention["actualOffsetMonotonicOffsetSeconds"]),
            "onsetSource": intervention["onsetSource"],
            "manifested": intervention["manifested"] is True,
            "reverted": intervention["recovered"] is True,
        }
    return normalised


def protocol_gate_record(
    cell: Mapping[str, Any], ledger: Mapping[str, Any], intervention: Mapping[str, Any] | None,
    gates: Any, module_sha256: str,
) -> dict[str, Any]:
    """F1 (fault cells), G1, G2 and G4 of the vendored shared gates, plus the non-blocking R2.recovery record.

    P0, R1 and R2 are recorded as not evaluated (the harness writes none of their inputs) and G4's channel scope
    is the ledger alone.  The same function, fed the retained artifacts, is the terminal validator's replay."""
    normalised = protocol_cell(cell, ledger, intervention)
    profile = {
        "sut": "otel-demo", "routes": [cell["workload"]["urlPath"]], "rate": float(ledger["ratePerSecond"]),
        "services": list(cell["workload"]["routeServices"]), "channels": {}, "emitters": {},
    }
    records = [gates.g1(normalised), gates.g2(normalised), gates.g4(normalised, profile), gates.r2_recovery(normalised)]
    if normalised["kind"] == "fault":
        records.insert(0, gates.f1(normalised))
    blocking = [row["gate"] for row in records if row["gate"] in PROTOCOL_GATES_BLOCKING]
    failed = [row["gate"] for row in records if row["gate"] in blocking and row["verdict"] != "pass"]
    return {
        "schemaVersion": 1,
        "kind": "otel-demo-sweep-protocol-gates-v1",
        "runId": cell["runId"],
        "module": "modules/otel-demo/validation/protocol_gates.py",
        "moduleSha256": module_sha256,
        "blocking": blocking,
        "notEvaluated": ["P0", "R1", "R2"],
        "g4ChannelScope": "ledger-only",
        "canFire": gates.entry_rule_can_fire(normalised),
        "verdicts": records,
        "failedGates": failed,
        "valid": not failed,
    }


def names_trace_rule(cell: Mapping[str, Any]) -> bool:
    """Whether the cell's compiled timing must carry ``traceCompletenessRule`` (decision 56): every quiet-epoch cell and
    the no-fault cells of the repeat epoch; never a sweep cell, never a repeat-epoch fault cell (decision 25)."""
    epoch = cell.get("studyEpoch")
    if epoch == QUIET_STUDY_EPOCH:
        return True
    return epoch in REPEAT_STUDY_EPOCHS and cell["timing"]["faultApplied"] is False


def completeness_requirements(
    timing: Mapping[str, Any], active: set[str],
) -> tuple[list[str], dict[str, list[str]] | None]:
    """What a complete trace needs: the cell's one route's services (every earlier epoch), or, for a cell whose timing carries
    the multi-route mix, per route the services the route is guaranteed to reach within the active closure (the first value is
    then their union, sorted, for the record's counters)."""
    if not has_mix(timing):
        return sorted(set(timing["route"]["services"]) & active), None
    by_route = {
        route: sorted(set(spec["requiredServices"]) & active) for route, spec in sorted(timing["workloadMix"]["routes"].items())
    }
    return sorted({service for services in by_route.values() for service in services}), by_route


def request_is_complete(
    request: Mapping[str, Any], row: Mapping[str, Any] | None, required: list[str], by_route: Mapping[str, list[str]] | None,
) -> bool:
    """Decision 25/56 completeness of one request: its own trace id observed and, for the single route, exactly the route's
    services within the closure on the clipped path; for the mix, every service its route is guaranteed to reach observed in the
    trace (services beyond that set are neither required nor unexpected)."""
    own = row is not None and row["observedOriginalTraceIds"] == [request["originalTraceId"]]
    if by_route is None:
        return own and row["observedPathServices"] == required
    return own and set(by_route[request["route"]]) <= set(row["observedTraceServices"])


def trace_completeness(
    cell: Mapping[str, Any], ledger: Mapping[str, Any], correlation: Mapping[str, Any],
    intervention: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Incomplete traces per window, and the shared rule's verdict (protocol decision 25, user 2026-10-03).

    Windows by request START, barrier-relative on the fault receipt's monotonic clock.  Fault cells: ``pre-onset``
    (start before the onset command was issued), ``fault-and-drain`` (start in [onset issued, route ready +
    timing.traceDrainSeconds]) and ``after-drain``; no-fault cells: ``whole-measurement``.  Complete = the request's
    own trace id observed and exactly the route's services within the active closure.  (i) Incomplete traces in
    ``fault-and-drain`` are recorded as the fault's effect and never block; (ii) the cell is blocked only if the
    successful requests of every other window with an incomplete trace exceed max(allowanceMinimum,
    floor(allowanceShare x their successful requests)).  Unsuccessful requests are counted per window, never in the
    rule.  The same function, fed the retained artifacts, is the terminal validator's replay.

    2026-10-04 (protocol decision 56): a compiled timing that names ``traceCompletenessRule`` -- the quiet calibration
    epoch's, and (2026-10-09) the repeat epoch's no-fault cells' -- is recorded by ``trace_loss_record`` instead.  A timing without the key is the sweep's,
    and everything below is decision 25 as at c532853."""
    timing = cell["timing"]
    if ("traceCompletenessRule" in timing) != names_trace_rule(cell):
        raise RuntimeFailure(
            "only the quiet calibration epoch's compiled timing (and the repeat epoch's no-fault cells) names a trace "
            "completeness rule"
        )
    if "traceCompletenessRule" in timing:
        return trace_loss_record(cell, ledger, correlation, intervention)
    active = set(cell["posture"]["expected"]["activeApplicationServices"])
    required, by_route = completeness_requirements(timing, active)
    barrier = float(ledger["barrierMonotonic"])
    rows = {row["requestToken"]: row for row in correlation["rows"]}
    if intervention is None:
        names = ("whole-measurement",)
        bounds = None
    else:
        names = ("pre-onset", "fault-and-drain", "after-drain")
        fault_start = float(intervention["actualOnsetMonotonicOffsetSeconds"])
        drain_end = float(intervention["readyAtMonotonic"]) - barrier + float(timing["traceDrainSeconds"])
        bounds = [fault_start, drain_end]
    windows: dict[str, dict[str, Any]] = {
        name: {
            "requests": 0, "successful": 0, "complete": 0, "incomplete": 0, "incompleteRequestTokens": [],
            "unsuccessful": 0, "unsuccessfulIncomplete": 0,
        }
        for name in names
    }
    for request in ledger["requests"]:
        start = float(request["startedMonotonic"]) - barrier
        if bounds is None:
            name = "whole-measurement"
        elif start < bounds[0]:
            name = "pre-onset"
        elif start <= bounds[1]:
            name = "fault-and-drain"
        else:
            name = "after-drain"
        row = rows.get(request["requestToken"])
        complete = request_is_complete(request, row, required, by_route)
        window = windows[name]
        window["requests"] += 1
        if request["outcome"] == "ok":
            window["successful"] += 1
            if complete:
                window["complete"] += 1
            else:
                window["incomplete"] += 1
                window["incompleteRequestTokens"].append(request["requestToken"])
        else:
            window["unsuccessful"] += 1
            window["unsuccessfulIncomplete"] += int(not complete)
    blocking = [name for name in names if name != "fault-and-drain"]
    successful = sum(windows[name]["successful"] for name in blocking)
    incomplete = sum(windows[name]["incomplete"] for name in blocking)
    allowance = max(
        int(timing["traceIncompleteAllowanceMinimum"]),
        int(math.floor(float(timing["traceIncompleteAllowanceShare"]) * successful + 1e-9)),
    )
    return {
        "schemaVersion": 2, "kind": "otel-demo-sweep-trace-completeness-v2", "runId": cell["runId"],
        "rule": "protocol-decision-25", "requiredPathServices": required,
        **({} if by_route is None else {"requiredServicesByRoute": by_route}),
        "faultAndDrainWindowSeconds": bounds, "drainSeconds": float(timing["traceDrainSeconds"]),
        "allowanceShare": float(timing["traceIncompleteAllowanceShare"]),
        "allowanceMinimum": int(timing["traceIncompleteAllowanceMinimum"]),
        "windows": windows, "blockingWindows": blocking,
        "recordedFaultEffectIncomplete": (
            windows["fault-and-drain"]["incomplete"] if "fault-and-drain" in windows else None
        ),
        "successful": successful, "incomplete": incomplete, "allowance": allowance,
        "valid": incomplete <= allowance,
    }


# Protocol decision 56 (user 2026-10-04, main repo research/PROTOCOL_DRAFT_20261002.md round 12, after the quiet run's
# attempt 1 stopped on a lost batch of productcatalogservice spans): the value the quiet epoch's compiled timing gives
# ``traceCompletenessRule``.
TRACE_LOSS_RULE = "protocol-decision-56"


def trace_loss_record(
    cell: Mapping[str, Any], ledger: Mapping[str, Any], correlation: Mapping[str, Any],
    intervention: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Protocol decision 56 (user 2026-10-04): in the quiet calibration epoch's no-fault cells an incomplete trace is
    telemetry loss, recorded and never blocking.

    One ``whole-measurement`` window.  Complete keeps decision 25's meaning: the request's own trace id observed and
    exactly the route's services within the active closure.  The window keeps decision 25's counts (successful,
    complete, incomplete with tokens; unsuccessful requests separately) and adds, for every successful incomplete
    request, its scheduled offset, whether its own trace id was observed, the required path services missing from it
    and any unexpected ones; the number of incomplete requests missing each required service; and the contiguous runs
    of consecutively scheduled requests that are each successful and incomplete (a complete or an unsuccessful request
    ends a run), each with its first and last scheduled offset, request count and missing services, so a lost export
    batch shows as one run.  What decision 25 would have ruled is recorded beside it and not applied.  The record is
    valid by rule; G1/G2/G4, the container-health guard and the terminal's ledger and witness checks stay blocking.
    The same function, fed the retained artifacts, is the terminal validator's replay."""
    timing = cell["timing"]
    if timing["traceCompletenessRule"] != TRACE_LOSS_RULE:
        raise RuntimeFailure(f"unknown trace completeness rule {timing['traceCompletenessRule']!r}")
    if intervention is not None or timing["faultApplied"] is not False:
        raise RuntimeFailure("the record-only trace rule (protocol decision 56) applies to no-fault cells only")
    active = set(cell["posture"]["expected"]["activeApplicationServices"])
    required, by_route = completeness_requirements(timing, active)
    rows = {row["requestToken"]: row for row in correlation["rows"]}
    window: dict[str, Any] = {
        "requests": 0, "successful": 0, "complete": 0, "incomplete": 0, "incompleteRequestTokens": [],
        "unsuccessful": 0, "unsuccessfulIncomplete": 0, "incompleteRequests": [],
        "incompleteByMissingService": {service: 0 for service in required}, "incompleteRuns": [],
    }
    run: dict[str, Any] | None = None
    for request in sorted(ledger["requests"], key=lambda item: float(item["scheduledOffsetSeconds"])):
        row = rows.get(request["requestToken"])
        own = row is not None and row["observedOriginalTraceIds"] == [request["originalTraceId"]]
        complete = request_is_complete(request, row, required, by_route)
        window["requests"] += 1
        if request["outcome"] != "ok":
            window["unsuccessful"] += 1
            window["unsuccessfulIncomplete"] += int(not complete)
            run = None
            continue
        window["successful"] += 1
        if complete:
            window["complete"] += 1
            run = None
            continue
        route_required = required if by_route is None else by_route[request["route"]]
        observed = (
            set(row["observedPathServices"] if by_route is None else row["observedTraceServices"]) if row is not None else set()
        )
        missing = sorted(set(route_required) - observed)
        offset = float(request["scheduledOffsetSeconds"])
        window["incomplete"] += 1
        window["incompleteRequestTokens"].append(request["requestToken"])
        window["incompleteRequests"].append({
            "requestToken": request["requestToken"], "scheduledOffsetSeconds": offset, "ownTraceObserved": own,
            "missingServices": missing,
            "unexpectedServices": sorted(observed - set(required)) if by_route is None else [],
        })
        for service in missing:
            window["incompleteByMissingService"][service] += 1
        if run is None:
            run = {
                "firstScheduledOffsetSeconds": offset, "lastScheduledOffsetSeconds": offset, "requests": 0,
                "missingServices": [],
            }
            window["incompleteRuns"].append(run)
        run["lastScheduledOffsetSeconds"] = offset
        run["requests"] += 1
        run["missingServices"] = sorted(set(run["missingServices"]) | set(missing))
    successful, incomplete = window["successful"], window["incomplete"]
    decision25 = max(
        int(timing["traceIncompleteAllowanceMinimum"]),
        int(math.floor(float(timing["traceIncompleteAllowanceShare"]) * successful + 1e-9)),
    )
    return {
        "schemaVersion": 3, "kind": "otel-demo-quiet-trace-completeness-v3", "runId": cell["runId"],
        "rule": TRACE_LOSS_RULE, "blocking": False, "requiredPathServices": required,
        **({} if by_route is None else {"requiredServicesByRoute": by_route}),
        "faultAndDrainWindowSeconds": None, "windows": {"whole-measurement": window}, "blockingWindows": [],
        "recordedFaultEffectIncomplete": None,
        "successful": successful, "incomplete": incomplete, "allowance": None,
        "decision25Counterfactual": {
            "allowance": decision25, "wouldHaveBlocked": incomplete > decision25, "applied": False,
        },
        "valid": True,
    }


def apply_memory_limits(cell: Mapping[str, Any], environment: Mapping[str, str]) -> list[dict[str, Any]]:
    """The epoch's declared memory-limit deviations (compiled timing), applied to the running containers with
    `docker update` and verified by inspect.  The swap allowance keeps the ratio the container had (the daemon's
    default is twice the memory limit); unlimited swap stays unlimited."""
    updates = []
    for service, limit in sorted(cell["timing"]["serviceMemoryLimitBytes"].items()):
        identifier = container_id(cell, service, environment)
        host = json.loads(command(["docker", "inspect", identifier]).stdout)[0]["HostConfig"]
        memory, swap = int(host.get("Memory") or 0), int(host.get("MemorySwap") or 0)
        argv = ["docker", "update", "--memory", str(int(limit))]
        if swap == -1:
            argv += ["--memory-swap", "-1"]
        elif swap > 0 and memory > 0:
            argv += ["--memory-swap", str(int(limit) * swap // memory)]
        argv.append(identifier)
        command(argv)
        after = json.loads(command(["docker", "inspect", identifier]).stdout)[0]["HostConfig"]
        observed = {"memory": int(after.get("Memory") or 0), "memorySwap": int(after.get("MemorySwap") or 0)}
        if observed["memory"] != int(limit):
            raise RuntimeFailure(f"memory limit of {service} is {observed['memory']}, not the declared {limit}")
        updates.append({
            "service": service, "containerId": identifier, "argv": argv,
            "before": {"memory": memory, "memorySwap": swap}, "after": observed,
        })
    return updates


def project_containers(cell: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every container carrying the project's Compose label (running or not), as the Docker engine reports it."""
    project = cell["compose"]["project"]
    listing = command([
        "docker", "ps", "-a", "--no-trunc", "-q", "--filter", f"label=com.docker.compose.project={project}",
    ]).stdout
    identifiers = sorted(line.strip() for line in listing.splitlines() if line.strip())
    if not identifiers:
        return []
    rows = []
    for item in json.loads(command(["docker", "inspect", *identifiers]).stdout):
        labels = (item.get("Config") or {}).get("Labels") or {}
        state = item.get("State") or {}
        rows.append({
            "containerId": item.get("Id"), "service": labels.get("com.docker.compose.service"),
            "status": state.get("Status"), "oomKilled": state.get("OOMKilled") is True,
            "restartCount": int(item.get("RestartCount") or 0),
            "memoryBytes": int((item.get("HostConfig") or {}).get("Memory") or 0),
        })
    return sorted(rows, key=lambda row: (str(row["service"]), str(row["containerId"])))


def container_health_verdict(
    cell: Mapping[str, Any], baseline: list[dict[str, Any]] | None, final: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Pure verdict over the two inspections (the terminal replays it): any OOMKilled container, an application
    container restarted or replaced since the baseline, or a declared memory limit not in effect invalidates."""
    if final is None:
        return {"oomKilled": [], "restartedApplicationServices": [], "missingApplicationServices": [],
                "memoryLimitsNotInEffect": [], "reasons": ["the final inspection is missing"], "valid": False}
    application = set(APP_SERVICES)
    before = {row["containerId"]: row for row in (baseline or [])}
    final_ids = {row["containerId"] for row in final}
    oom = sorted({str(row["service"]) for row in final if row["oomKilled"]})
    restarted = sorted({
        str(row["service"]) for row in final
        if row["service"] in application and (
            row["containerId"] not in before or row["restartCount"] > before[row["containerId"]]["restartCount"]
        )
    }) if baseline is not None else []
    missing = sorted({
        str(row["service"]) for row in (baseline or [])
        if row["service"] in application and row["containerId"] not in final_ids
    })
    limits = cell["timing"]["serviceMemoryLimitBytes"]
    not_in_effect = sorted(
        service for service, limit in limits.items()
        if [row["memoryBytes"] for row in final if row["service"] == service] != [int(limit)]
    )
    reasons = []
    if oom:
        reasons.append("OOMKilled: " + ", ".join(oom))
    if restarted:
        reasons.append("application container restarted during the cell: " + ", ".join(restarted))
    if missing:
        reasons.append("application container gone during the cell: " + ", ".join(missing))
    if not_in_effect:
        reasons.append("declared memory limit not in effect: " + ", ".join(not_in_effect))
    if baseline is None:
        reasons.append("the baseline inspection is missing")
    return {"oomKilled": oom, "restartedApplicationServices": restarted, "missingApplicationServices": missing,
            "memoryLimitsNotInEffect": not_in_effect, "reasons": reasons, "valid": not reasons}


def run_sweep_cell(cell: Mapping[str, Any], deadline: datetime) -> dict[str, Any]:
    """One traffic-sweep cell: fresh project, upstream generator removed, stack readiness, a 10/s warm-up on
    the route, the measurement at the cell's rate with its fault, then the frozen epoch's capture, plus the
    timestamped application logs and the protocol gates.  Any gate other than pass invalidates the cell."""
    timing = cell["timing"]
    workload = cell["workload"]
    require_harness_flags_consistent(cell)
    root = safe_absolute(cell["remoteArtifactRoot"], "cell artifact root")
    environment = cell_environment(cell)
    rendered_compose_config_sha256 = verify_installed_images(cell, environment)
    gates_path = Path(cell["releaseRoot"]) / PROTOCOL_GATES_RELEASE_PATH
    gates_sha256 = cell["installedControllerDigests"]["protocol-gates"]
    gates = load_protocol_gates(gates_path, gates_sha256)
    root.mkdir(parents=True, exist_ok=False)
    project = cell["compose"]["project"]
    source = Path(cell["remoteSourceRoot"])
    preflight = project_resources(project)
    if any(preflight.values()):
        raise RuntimeFailure(f"Compose project already owns resources: {preflight}")
    # The upstream generator is removed right after `up`, before readiness, with plain Compose commands: `up --scale
    # loadgenerator=0` would leave frontendproxy's required `depends_on: loadgenerator` to Compose-version semantics
    # (review 2026-10-03, B1).  It runs only between `up` and the removal, never in the warm-up or the measurement.
    off = list(timing["upstreamGeneratorsOff"])
    owns = False
    capture: Capture | None = None
    error: str | None = None
    result: dict[str, Any] = {}
    memory_updates: list[dict[str, Any]] = []
    baseline: list[dict[str, Any]] | None = None
    events: DockerEvents | None = None
    try:
        ensure_generator_open_files(timing)        # load pilot only: before any container starts (refused cell = no mutation)
        owns = True
        command(compose(cell, "up", "-d", "--no-build"), cwd=source, env=environment)
        command(compose(cell, "rm", "--stop", "--force", *off), cwd=source, env=environment)
        generator_after_removal = upstream_generator_state(cell, environment)
        if any(row["returnCode"] != 0 or row["containers"] for row in generator_after_removal["services"].values()):
            raise RuntimeFailure(f"an upstream generator the cell turns off has a container: {generator_after_removal}")
        memory_updates = apply_memory_limits(cell, environment)
        base = f"http://127.0.0.1:{cell['compose']['ports']['frontend']}"
        wait_ready(base, workload["readinessJourney"], deadline)
        wait_route_ready(base, workload, deadline)
        baseline = project_containers(cell)
        warm_barrier = time.monotonic()
        run_cell_workload(
            base, workload, timing, f"warmup-{cell['runId']}", rate=float(timing["warmupRequestsPerSecond"]),
            offered=int(timing["warmupOffered"]), duration=float(timing["warmupSeconds"]),
            barrier=warm_barrier, barrier_epoch=time.time(),
        )
        pcap = root / "telemetry.pcap"
        capture = start_capture(pcap)
        time.sleep(1)
        cpu_before = cpu_snapshot(cell, environment)
        want_events = freeze_enabled(timing) and cell["fault"]["action"] == "pause"
        events_error: str | None = None
        if want_events:
            # H4: live, before the barrier, so no pause event can be missed.  Recorded, never blocking (decision 69):
            # a stream that cannot start leaves a record saying so, not an invalid cell.
            try:
                events = start_docker_events(cell)
            except Exception as exc:
                events_error = f"{type(exc).__name__}: {exc}"
        barrier = time.monotonic()
        barrier_epoch = time.time()
        fault_result: dict[str, Any] = {}
        fault_thread = None
        if cell["fault"]["scenario"] is not None:
            fault_thread = threading.Thread(
                target=inject_sweep_fault, args=(cell, environment, base, barrier, fault_result), daemon=True,
            )
            fault_thread.start()
        ledger = run_cell_workload(
            base, workload, timing, workload["tokenNamespace"], rate=float(timing["requestsPerSecond"]),
            offered=int(timing["offered"]), duration=float(timing["measurementSeconds"]),
            barrier=barrier, barrier_epoch=barrier_epoch,
        )
        intervention: dict[str, Any] | None = None
        if fault_thread is not None:
            fault_thread.join(timeout=float(timing["measurementSeconds"]) + ROUTE_READY_TIMEOUT_SECONDS)
            if fault_thread.is_alive():
                raise RuntimeFailure("fault worker did not settle")
            intervention = fault_result
            if isinstance(intervention.get("freeze"), dict):
                intervention["freeze"]["stampCheck"] = freeze_stamp_check(intervention)      # H4, recorded (decision 69)
            write_json(root / "intervention.json", intervention)
            if want_events:
                stopped_at = {"epoch": time.time(), "monotonic": time.monotonic()}
                try:
                    if events is None:
                        raise RuntimeFailure(events_error or "the docker events stream was not started")
                    handle, events = events, None
                    stream = stop_docker_events(handle)
                except Exception as exc:
                    stream = {
                        "argv": docker_events_argv(cell["compose"]["project"], 0), "sinceEpoch": 0,
                        "exitedBeforeStop": True, "returnCode": None, "stderr": "", "raw": [],
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                write_json(root / DOCKER_EVENTS_FILE, docker_events_record(
                    cell, stream, barrier, barrier_epoch, stopped_at, intervention))
            if intervention.get("successful") is not True:
                raise RuntimeFailure("fault manifestation or recovery failed")
        cpu_after = cpu_snapshot(cell, environment)
        stop_capture(capture); capture = None
        time.sleep(COLLECTOR_SETTLE_SECONDS)
        # Container logs are bytes, not guaranteed UTF-8: retained raw, parsed with replacement (U+FFFD).
        collector_bytes = command(
            compose(cell, "logs", "--no-color", "otelcol"), cwd=source, env=environment, check=False, binary=True,
        ).stdout
        proxy_bytes = command(
            compose(cell, "logs", "--no-color", "frontendproxy"), cwd=source, env=environment, check=False, binary=True,
        ).stdout
        services = [
            service for service in APP_SERVICES if service not in set(timing["upstreamGeneratorsOff"])
        ]
        application_bytes = command(
            compose(cell, "logs", "--no-color", "--timestamps", *services), cwd=source, env=environment, check=False,
            binary=True,
        ).stdout
        collector = collector_bytes.decode("utf-8", errors="replace")
        proxy = proxy_bytes.decode("utf-8", errors="replace")
        generator_after_window = upstream_generator_state(cell, environment)
        (root / "otelcol.log").write_bytes(collector_bytes)
        (root / "application.log").write_bytes(application_bytes)
        write_json(root / "upstream-generator.json", {
            "schemaVersion": 1, "kind": "otel-demo-upstream-generator-off-v1",
            "mechanism": " ".join(["docker", "compose", "rm", "--stop", "--force", *off]) + " after up, before readiness",
            "afterRemoval": generator_after_removal, "afterWindow": generator_after_window,
        })
        if any(row["returnCode"] != 0 or row["containers"] for row in generator_after_window["services"].values()):
            raise RuntimeFailure("an upstream generator the cell turns off acquired a container during the cell")
        require_collector_carrier_coverage(collector, ledger["startedAtEpoch"])
        write_json(root / "request-ledger.json", ledger)
        write_json(root / "application-witness.json", parse_application_witness(proxy, ledger["requests"]))
        correlation = parse_trace_correlation(collector, ledger["requests"])
        write_json(root / "trace-correlation.json", correlation)
        completeness = trace_completeness(cell, ledger, correlation, intervention)
        write_json(root / "trace-completeness.json", completeness)
        write_json(root / "posture-proof.json", posture_proof(cell, environment, collector, rendered_compose_config_sha256))
        write_json(root / "telemetry-bytes.json", telemetry_bytes(pcap))
        delta = cpu_after["totalNanoseconds"] - cpu_before["totalNanoseconds"]
        if delta < 0: raise RuntimeFailure("cumulative CPU counter decreased")
        write_json(root / "resources.json", {
            "schemaVersion": 1,
            "counter": "docker-engine-cpu_stats.cpu_usage.total_usage",
            "before": cpu_before,
            "after": cpu_after,
            "applicationCpuSeconds": delta / 1_000_000_000,
            "offeredRequests": ledger["offered"],
            "cpuSecondsPerOfferedRequest": delta / 1_000_000_000 / ledger["offered"],
            "claimUse": "diagnostic-only",
        })
        record = protocol_gate_record(cell, ledger, intervention, gates, gates_sha256)
        write_json(root / "protocol-gates.json", record)
        if not record["valid"]:
            raise RuntimeFailure(f"protocol gate(s) {', '.join(record['failedGates'])} did not pass")
        if not completeness["valid"]:
            raise RuntimeFailure(
                f"trace completeness: {completeness['incomplete']} incomplete of {completeness['successful']} "
                f"successful requests outside the fault-and-drain window exceeds the allowance "
                f"{completeness['allowance']}"
            )
        result = {"offered": ledger["offered"], "completed": ledger["completed"], "failed": ledger["failed"]}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if capture is not None:
            with contextlib.suppress(Exception): stop_capture(capture)
        if events is not None:
            with contextlib.suppress(Exception): stop_docker_events(events)
        if owns:
            # The container-health guard: every project container, after the captures and before cleanup.
            final: list[dict[str, Any]] | None = None
            inspection_error = None
            try:
                final = project_containers(cell)
            except Exception as exc:
                inspection_error = f"{type(exc).__name__}: {exc}"
            verdict = container_health_verdict(cell, baseline, final)
            write_json(root / "container-health.json", {
                "schemaVersion": 1, "kind": "otel-demo-sweep-container-health-v1", "runId": cell["runId"],
                "memoryLimitUpdates": memory_updates, "baselineAt": "after readiness, before the warm-up",
                "baseline": baseline, "finalAt": "after the captures, before cleanup", "final": final,
                "inspectionError": inspection_error, **verdict,
            })
            if error is None and not verdict["valid"]:
                error = "RuntimeFailure: container health: " + "; ".join(verdict["reasons"])
            command(compose(cell, "down", "--remove-orphans", "--volumes"), cwd=source, env=environment, check=False)
        remaining = project_resources(project)
        cleanup = {"schemaVersion": 1, "project": project, "remainingResources": remaining, "ownedResourcesClean": not any(remaining.values()), "completedAt": now_iso()}
        write_json(root / "cell-cleanup.json", cleanup)
    return _seal_cell(cell, root, error, cleanup, result)


def _seal_cell(
    cell: Mapping[str, Any], root: Path, error: str | None, cleanup: Mapping[str, Any], result: Mapping[str, Any],
) -> dict[str, Any]:
    """The receipt and content manifest, the frozen run_cell's tail."""
    state = "valid" if error is None and cleanup["ownedResourcesClean"] else "invalid"
    receipt = {"schemaVersion": 1, "kind": "otel-demo-candidate-cell-receipt-v1", "target": cell["target"], "runId": cell["runId"], "runKey": cell["runKey"], "state": state, "result": dict(result), "error": error, "promotionAuthorized": False}
    write_json(root / "receipt.json", receipt)
    if state == "valid":
        missing = sorted(
            (set(cell["requiredArtifacts"]) - {"content-manifest.json"})
            - {path.name for path in root.iterdir()}
        )
        extra = sorted({path.name for path in root.iterdir()} - set(cell["requiredArtifacts"]))
        if missing or extra:
            receipt["state"] = "invalid"; receipt["error"] = f"artifact population differs: missing={missing}, extra={extra}"
            write_json(root / "receipt.json", receipt)
        else:
            write_json(root / "content-manifest.json", content_manifest(root, cell["requiredArtifacts"]))
    return receipt


def run_cell(cell: Mapping[str, Any], deadline: datetime) -> dict[str, Any]:
    refuse_unsupported("candidate cell", cell.get("studyEpoch") if isinstance(cell, Mapping) else None)
    if datetime.now(timezone.utc).timestamp() + 900 >= deadline.timestamp():
        raise RuntimeFailure("deadline reserve reached before cell start")
    if is_timed(cell):
        if cell.get("studyEpoch") not in TIMED_STUDY_EPOCHS:
            raise RuntimeFailure("a timed cell must belong to a timed epoch (traffic sweep or quiet calibration)")
        return run_sweep_cell(cell, deadline)
    root = safe_absolute(cell["remoteArtifactRoot"], "cell artifact root")
    environment = cell_environment(cell)
    rendered_compose_config_sha256 = verify_installed_images(cell, environment)
    root.mkdir(parents=True, exist_ok=False)
    project = cell["compose"]["project"]
    source = Path(cell["remoteSourceRoot"])
    preflight = project_resources(project)
    if any(preflight.values()):
        raise RuntimeFailure(f"Compose project already owns resources: {preflight}")
    owns = False
    capture: Capture | None = None
    error: str | None = None
    result: dict[str, Any] = {}
    try:
        owns = True
        command(compose(cell, "up", "-d", "--no-build"), cwd=source, env=environment)
        base = f"http://127.0.0.1:{cell['compose']['ports']['frontend']}"
        wait_ready(base, cell["workload"], deadline)
        warm_namespace = f"warmup-{cell['runId']}"
        run_workload(base, cell["workload"], warm_namespace, cell["window"]["warmupSeconds"])
        pcap = root / "telemetry.pcap"
        capture = start_capture(pcap)
        time.sleep(1)
        cpu_before = cpu_snapshot(cell, environment)
        barrier = time.monotonic()
        fault_result: dict[str, Any] = {}
        fault_thread = None
        if cell["fault"]["scenario"] is not None:
            fault_thread = threading.Thread(target=inject_fault, args=(cell, environment, base, barrier, fault_result), daemon=True)
            fault_thread.start()
        ledger = run_workload(base, cell["workload"], cell["workload"]["tokenNamespace"], cell["window"]["measurementSeconds"])
        if fault_thread is not None:
            fault_thread.join(timeout=cell["window"]["measurementSeconds"] + 300)
            if fault_thread.is_alive(): raise RuntimeFailure("fault worker did not settle")
            # Retain the independent state-probe receipt even when the
            # intervention failed, then stop this cell before any outcome can
            # be mistaken for a successful fault exposure.
            write_json(root / "intervention.json", fault_result)
            if fault_result.get("successful") is not True:
                raise RuntimeFailure("fault manifestation or recovery failed")
        cpu_after = cpu_snapshot(cell, environment)
        stop_capture(capture); capture = None
        time.sleep(COLLECTOR_SETTLE_SECONDS)
        collector = command(compose(cell, "logs", "--no-color", "otelcol"), cwd=source, env=environment, check=False).stdout
        proxy = command(compose(cell, "logs", "--no-color", "frontendproxy"), cwd=source, env=environment, check=False).stdout
        (root / "otelcol.log").write_text(collector, encoding="utf-8")
        # Retain the carrier first, then refuse the cell if it was truncated:
        # a trace-derived artifact built from a partial carrier is not evidence.
        require_collector_carrier_coverage(collector, ledger["startedAtEpoch"])
        write_json(root / "request-ledger.json", ledger)
        write_json(root / "application-witness.json", parse_application_witness(proxy, ledger["requests"]))
        write_json(root / "trace-correlation.json", parse_trace_correlation(collector, ledger["requests"]))
        write_json(root / "posture-proof.json", posture_proof(cell, environment, collector, rendered_compose_config_sha256))
        write_json(root / "telemetry-bytes.json", telemetry_bytes(pcap))
        delta = cpu_after["totalNanoseconds"] - cpu_before["totalNanoseconds"]
        if delta < 0: raise RuntimeFailure("cumulative CPU counter decreased")
        resource_value = {
            "schemaVersion": 1,
            "counter": "docker-engine-cpu_stats.cpu_usage.total_usage",
            "before": cpu_before,
            "after": cpu_after,
            "applicationCpuSeconds": delta / 1_000_000_000,
            "offeredRequests": ledger["offered"],
            "cpuSecondsPerOfferedRequest": (
                delta / 1_000_000_000 / ledger["offered"]
            ),
        }
        if cell["window"]["kind"] == "cost":
            resource_value["claimUse"] = "cost-proxy"
            write_json(root / "resources.json", resource_value)
        else:
            resource_value["claimUse"] = "diagnostic-only"
            write_json(root / "effect-resources.json", resource_value)
            write_json(root / "intervention.json", fault_result)
        result = {"offered": ledger["offered"], "completed": ledger["completed"], "failed": ledger["failed"]}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if capture is not None:
            with contextlib.suppress(Exception): stop_capture(capture)
        if owns:
            command(compose(cell, "down", "--remove-orphans", "--volumes"), cwd=source, env=environment, check=False)
        remaining = project_resources(project)
        cleanup = {"schemaVersion": 1, "project": project, "remainingResources": remaining, "ownedResourcesClean": not any(remaining.values()), "completedAt": now_iso()}
        write_json(root / "cell-cleanup.json", cleanup)
    state = "valid" if error is None and cleanup["ownedResourcesClean"] else "invalid"
    receipt = {"schemaVersion": 1, "kind": "otel-demo-candidate-cell-receipt-v1", "target": cell["target"], "runId": cell["runId"], "runKey": cell["runKey"], "state": state, "result": result, "error": error, "promotionAuthorized": False}
    write_json(root / "receipt.json", receipt)
    if state == "valid":
        missing = sorted(
            (set(cell["requiredArtifacts"]) - {"content-manifest.json"})
            - {path.name for path in root.iterdir()}
        )
        extra = sorted({path.name for path in root.iterdir()} - set(cell["requiredArtifacts"]))
        if missing or extra:
            receipt["state"] = "invalid"; receipt["error"] = f"artifact population differs: missing={missing}, extra={extra}"
            write_json(root / "receipt.json", receipt)
        else:
            write_json(root / "content-manifest.json", content_manifest(root, cell["requiredArtifacts"]))
    return receipt


def require_path_check_before_faults(cells: Sequence[Mapping[str, Any]]) -> int:
    """Exactly one cell gates the campaign: a no-fault full cell that precedes
    every fault cell. Returns its index; refuses before any mutation otherwise."""
    if any(
        not isinstance(cell.get("workloadPathCheck"), dict)
        or type(cell["workloadPathCheck"].get("gatesCampaign")) is not bool
        for cell in cells
    ):
        raise RuntimeFailure("a cell carries no workload path check flag")
    gates = [index for index, cell in enumerate(cells) if cell["workloadPathCheck"]["gatesCampaign"]]
    faults = [index for index, cell in enumerate(cells) if (cell.get("fault") or {}).get("scenario") is not None]
    if cells and all(is_timed(cell) for cell in cells):
        # The traffic sweep checks its route's path in every cell (terminal correlation rule) and leads with a
        # fault cell by design, so no cell gates the campaign on the offpath selected literal.
        if gates:
            raise RuntimeFailure("a timed-epoch package names a workload path check cell")
        return -1
    if len(gates) != 1:
        raise RuntimeFailure("execution package does not name exactly one workload path check cell")
    gate = cells[gates[0]]
    if (
        gate.get("runKey", {}).get("regime") != "no-fault-cost"
        or gate.get("posture", {}).get("id") != "full"
        or (faults and gates[0] > min(faults))
        or sorted(gate["workloadPathCheck"].get("synchronousPath", [])) != sorted(TARGET_PATH)
        or sorted(gate["workloadPathCheck"].get("asynchronousServices", [])) != sorted(ASYNC_SERVICES)
    ):
        raise RuntimeFailure("the workload path check cell is not a no-fault full cell before every fault cell")
    return gates[0]


def _run_campaign(document: Mapping[str, Any]) -> dict[str, Any]:
    if not ADMITTED_STUDY_EPOCHS:
        refuse_unsupported("candidate campaign implementation")
    cells, root, lease_path, project, deadline = validate_package(document)
    refuse_unsupported("candidate campaign implementation", document["studyEpoch"])
    target = validate_local_target(document["target"])
    controller_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    expected_sha = cells[0].get("posture", {}).get("environment")  # force complete cell parse before mutation
    if not isinstance(expected_sha, dict):
        raise RuntimeFailure("cell posture environment is absent")
    require_path_check_before_faults(cells)
    if root.exists() and not (root / ".controller").is_dir():
        raise RuntimeFailure("artifact root is not the controller-owned staging root")
    root.mkdir(parents=True, exist_ok=True)
    marker = root / ".attempt-started"
    if marker.exists() or marker.is_symlink():
        raise RuntimeFailure("one-shot campaign already started; retry is forbidden")
    lease_fd = inherited_lease_fd(lease_path)
    # A second nonblocking lock through a new open description must fail while
    # the no-fork launcher holds the inherited descriptor for this process.
    with lease_path.open("a+") as probe:
        try:
            fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(probe.fileno(), fcntl.LOCK_UN)
            raise RuntimeFailure("inherited shared lease is not actually held")
    if lease_fd < 3:
        raise RuntimeFailure("shared lease descriptor is not a launcher-owned descriptor")
    if True:
        if any(project_resources(project).values()):
            raise RuntimeFailure("owned Compose project is not initially empty")
        marker.write_text(json.dumps({"startedAt": now_iso(), "controllerSha256": controller_sha}) + "\n")
        receipts = []
        run_count = expected_run_count(document)
        ordinals = range(1, (run_count if is_timed(cells[0]) else len(POSTURES)) + 1)
        for index, cell in enumerate(cells):
            if cell.get("ordinalPosition") not in set(ordinals):
                raise RuntimeFailure("cell ordinal differs")
            receipt = run_cell(cell, deadline)
            receipts.append(receipt)
            if receipt["state"] != "valid": break
            if cell["workloadPathCheck"]["gatesCampaign"]:
                check = workload_path_check(cell, Path(cell["remoteArtifactRoot"]), receipt)
                write_json(root / "workload-path-check.json", check)
                if check["verdict"] != "pass":
                    break
        terminal = {"schemaVersion": 1, "kind": "otel-demo-candidate-remote-terminal-v1", "target": target, "expectedCells": run_count, "attemptedCells": len(receipts), "validCells": sum(row["state"] == "valid" for row in receipts), "stopped": len(receipts) != run_count, "promotionAuthorized": False}
        write_json(root / "remote-terminal.json", terminal)
        remaining = project_resources(project)
        release = {
            "schemaVersion": 1,
            "kind": "srv6-otel-host-release-v1",
            "campaignId": document["campaignId"],
            "systemdUnit": document["systemdUnit"],
            "leasePath": str(lease_path),
            "leaseDescriptor": lease_fd,
            "leaseHeldUntilControllerExit": True,
            "composeProject": project,
            "remainingOwnedResources": remaining,
            "reservedPorts": sorted(document["composePorts"].values()),
            "successor": "online-boutique",
            "successorMustRecheckLeaseAndPorts": True,
            "readyForSuccessorAfterControllerExit": not any(remaining.values()),
            "foreignResourcesTouched": [],
            "completedAt": now_iso(),
        }
        write_json(root / "host-release.json", release)
        return terminal


def _bounded_abort_identity(
    document: Mapping[str, Any],
) -> tuple[Path, str, str] | None:
    """Recover only the fixed campaign control identity from an invalid package."""
    campaign = document.get("campaignId")
    project = document.get("composeProject")
    if (
        not isinstance(campaign, str)
        or SAFE_NAME.fullmatch(campaign) is None
        or not isinstance(project, str)
        or SAFE_NAME.fullmatch(project) is None
        or not project.startswith(EXPECTED_PROJECT_PREFIX)
    ):
        return None
    root = Path(EXPECTED_ARTIFACT_PARENT) / campaign
    if document.get("remoteArtifactRoot") != str(root):
        return None
    unit = f"{project}.service"
    if document.get("systemdUnit") != unit:
        return None
    return root, campaign, unit


def _retain_campaign_abort(document: Mapping[str, Any], exc: Exception) -> None:
    identity = _bounded_abort_identity(document)
    if identity is None:
        return
    root, campaign, unit = identity
    controller = root / ".controller"
    if (
        root.is_symlink()
        or not root.is_dir()
        or controller.is_symlink()
        or not controller.is_dir()
    ):
        return
    abort = {
        "schemaVersion": 1,
        "kind": "otel-demo-candidate-campaign-abort-v1",
        "campaignId": campaign,
        "target": EXPECTED_TARGET,
        "systemdUnit": unit,
        "errorType": type(exc).__name__,
        "error": str(exc)[:4096],
        "completedAt": now_iso(),
        "promotionAuthorized": False,
    }
    abort_path = root / "campaign-abort.json"
    if abort_path.exists() or abort_path.is_symlink():
        return
    try:
        descriptor = os.open(
            abort_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(abort, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        pass


def run_campaign(document: Mapping[str, Any]) -> dict[str, Any]:
    """Retain an abort even when exact-package validation fails before mutation."""
    if not ADMITTED_STUDY_EPOCHS:
        refuse_unsupported("candidate campaign")
    try:
        return _run_campaign(document)
    except Exception as exc:
        _retain_campaign_abort(document, exc)
        raise


def cleanup(document: Mapping[str, Any]) -> dict[str, Any]:
    if not ADMITTED_STUDY_EPOCHS:
        refuse_unsupported("candidate cleanup")
    cells, _, lease_path, project, _ = validate_package(document)
    refuse_unsupported("candidate cleanup", document["studyEpoch"])
    validate_local_target(document["target"])
    cell = cells[0]
    environment = cell_environment(cell)
    command(compose(cell, "down", "--remove-orphans", "--volumes"), cwd=Path(cell["remoteSourceRoot"]), env=environment, check=False)
    remaining = project_resources(project)
    return {"project": project, "leasePath": str(lease_path), "remainingResources": remaining, "clean": not any(remaining.values())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "cleanup"))
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args(argv)
    if not ADMITTED_STUDY_EPOCHS:
        refuse_unsupported(f"candidate remote command {args.command}")
    document = read_json(args.package, "execution package")
    result = run_campaign(document) if args.command == "run" else cleanup(document)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not result.get("stopped") and result.get("clean", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
