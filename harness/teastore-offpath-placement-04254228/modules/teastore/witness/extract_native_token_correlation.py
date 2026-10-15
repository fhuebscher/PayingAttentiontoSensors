#!/usr/bin/env python3
"""Extract a fail-closed TeaStore token-to-original-Kieker-trace bridge.

The bridge is application log evidence, not a field copied into native events.
This module performs no Docker, SSH, network, or process action.  It accepts a
separately retained measurement-scoped auth-log capture receipt and refuses to
write when parameter logging was not proven absent/false.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn


BASE_COMMIT = "34b37f7e7be433ce72d5f9455e66922a13116749"
MARKER = "OBSERVABILITY_NATIVE_TRACE_BRIDGE "
TOKEN = re.compile(r"^journey-[0-9a-f]{32}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")
SIGNED_LONG_MIN = -(2**63)
SIGNED_LONG_MAX = 2**63 - 1
BRIDGE_KEYS = {"token", "nativeTraceId", "service"}
MAPPING_KEYS = {"mappingId", "token", "nativeTraceId", "service"}
TOKEN_SMUGGLING_FIELDS = {
    "opaqueToken", "token", "journeyId", "observabilityJourneyId",
    "X-Observability-Journey-Id",
}

_SECRET_SCAN_PATH = Path(__file__).parents[1] / "validation" / "secret_scan.py"
_SECRET_SCAN_SPEC = importlib.util.spec_from_file_location(
    "teastore_secret_scan_for_native_token", _SECRET_SCAN_PATH)
if _SECRET_SCAN_SPEC is None or _SECRET_SCAN_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot load TeaStore secret scanner: {_SECRET_SCAN_PATH}")
_SECRET_SCAN = importlib.util.module_from_spec(_SECRET_SCAN_SPEC)
_SECRET_SCAN_SPEC.loader.exec_module(_SECRET_SCAN)

_FIXED_LOAD_PATH = Path(__file__).parents[1] / "workload/fixed_load.py"
_FIXED_LOAD_SPEC = importlib.util.spec_from_file_location(
    "teastore_fixed_load_for_native_token", _FIXED_LOAD_PATH)
if _FIXED_LOAD_SPEC is None or _FIXED_LOAD_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot load TeaStore workload validator: {_FIXED_LOAD_PATH}")
_FIXED_LOAD = importlib.util.module_from_spec(_FIXED_LOAD_SPEC)
_FIXED_LOAD_SPEC.loader.exec_module(_FIXED_LOAD)


def _study_epoch_module():
    """The tree's study-epoch selector (execution/study_epoch.py), loaded by path for python3 -I."""
    path = Path(__file__).resolve().parents[1] / "execution" / "study_epoch.py"
    spec = importlib.util.spec_from_file_location("teastore_study_epoch_for_" + __name__, path)
    if spec is None or spec.loader is None:  # pragma: no cover - install defect
        raise RuntimeError(f"cannot load the study-epoch selector: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_STUDY_EPOCH = _study_epoch_module()
# Without a selector: auth-freeze-effect and persistence-crash-effect, the frozen set, and no drain allowance.
EFFECT_REGIMES = frozenset(
    regime for regime, fault in _STUDY_EPOCH.active(Path(__file__).resolve().parents[3])["scenarios"].items()
    if fault is not None)
SWEEP_EPOCH_ACTIVE = _STUDY_EPOCH.active(Path(__file__).resolve().parents[3])["sweep"] is True

# The collector owns the canonical trace-root activation groups and the
# entry_point_woven() closure test; loading it here keeps the extractor's
# F-ADH-065 gate keyed to the same definition the collector correlates with.
_NATIVE_COLLECTOR_PATH = Path(__file__).parents[1] / "collectors/kieker_native.py"
_NATIVE_COLLECTOR_SPEC = importlib.util.spec_from_file_location(
    "teastore_kieker_native_for_native_token", _NATIVE_COLLECTOR_PATH)
if _NATIVE_COLLECTOR_SPEC is None or _NATIVE_COLLECTOR_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot load TeaStore native collector: {_NATIVE_COLLECTOR_PATH}")
_NATIVE_COLLECTOR = importlib.util.module_from_spec(_NATIVE_COLLECTOR_SPEC)
_NATIVE_COLLECTOR_SPEC.loader.exec_module(_NATIVE_COLLECTOR)


class CorrelationError(ValueError):
    """The retained inputs do not establish an unambiguous native mapping."""


def _reject_constant(value: str) -> NoReturn:
    raise CorrelationError(f"non-finite JSON value is forbidden: {value}")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CorrelationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(payload: bytes, where: str) -> Any:
    try:
        return json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except CorrelationError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CorrelationError(f"invalid JSON in {where}: {exc}") from exc


def _file_bytes(path: Path, where: str) -> bytes:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise CorrelationError(f"{where} is not a regular non-symlink file")
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        payload = path.read_bytes()
        after = path.lstat()
        if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise CorrelationError(f"{where} changed while being read")
        return payload
    except CorrelationError:
        raise
    except OSError as exc:
        raise CorrelationError(f"cannot read {where}: {exc}") from exc


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path, where: str) -> str:
    return _sha256_bytes(_file_bytes(path, where))


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, allow_nan=False, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CorrelationError(f"value is not canonical JSON: {exc}") from exc


def _iso(value: Any, where: str) -> datetime:
    if not isinstance(value, str):
        raise CorrelationError(f"{where} is not a timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CorrelationError(f"{where} is not ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CorrelationError(f"{where} has no UTC offset")
    return parsed


def canonical_native_trace_id(value: Any) -> str:
    """Return a canonical Java signed-long decimal string, excluding -1."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise CorrelationError("nativeTraceId is not a string/integer signed long")
    text = str(value)
    if not re.fullmatch(r"-?(0|[1-9][0-9]*)", text):
        raise CorrelationError(f"nativeTraceId is not canonical decimal: {text!r}")
    parsed = int(text)
    if not SIGNED_LONG_MIN <= parsed <= SIGNED_LONG_MAX or parsed == -1:
        raise CorrelationError(f"nativeTraceId is outside the admitted signed-long domain: {text}")
    if str(parsed) != text:
        raise CorrelationError(f"nativeTraceId is not canonical decimal: {text!r}")
    return text


def _safe_relative(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise CorrelationError(f"{where} is not a safe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise CorrelationError(f"{where} is not a normalized relative path")
    return value


def _read_ledger(path: Path) -> tuple[list[dict[str, Any]], Path, dict[str, Any]]:
    if path.suffix != ".jsonl":
        raise CorrelationError("journey ledger must be the hash-chained JSONL artifact")
    plan = _FIXED_LOAD.journey_plan_path(path)
    try:
        validation = _FIXED_LOAD.validate_journey_ledger(plan, path)
    except (OSError, ValueError) as exc:
        raise CorrelationError(f"journey ledger validation failed: {exc}") from exc
    payload = _file_bytes(path, "journey ledger")
    if not payload or not payload.endswith(b"\n"):
        raise CorrelationError("journey ledger is empty or truncated")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(payload.splitlines(), 1):
        row = _strict_json(line, f"journey ledger line {number}")
        if not isinstance(row, dict):
            raise CorrelationError(f"journey ledger line {number} is not an object")
        if row.get("recordType") == "journey-terminal":
            rows.append(row)
    if not rows:
        raise CorrelationError("journey ledger has no terminal journeys")
    for row in rows:
        token = row.get("opaqueToken")
        if not isinstance(token, str) or TOKEN.fullmatch(token) is None:
            raise CorrelationError("journey ledger contains an invalid token")
    if len({row["opaqueToken"] for row in rows}) != len(rows):
        raise CorrelationError("journey ledger contains duplicate tokens")
    return rows, plan, validation


def _run_identity(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    receipt = _strict_json(_file_bytes(path, "run receipt"), "run receipt")
    if not isinstance(receipt, dict) or not isinstance(receipt.get("run"), dict):
        raise CorrelationError("run receipt lacks run identity")
    if not isinstance(receipt.get("window"), dict):
        raise CorrelationError("run receipt lacks a measurement window")
    run = receipt["run"]
    if run.get("posture") not in {"none", "selected", "full"}:
        raise CorrelationError("run receipt posture is invalid")
    if not isinstance(run.get("runId"), str) or not run["runId"]:
        raise CorrelationError("run receipt runId is invalid")
    window = {
        "startedAt": receipt["window"].get("measurementStartedAt"),
        "endedAt": receipt["window"].get("measurementEndedAt"),
    }
    if _iso(window["startedAt"], "measurement start") >= _iso(
        window["endedAt"], "measurement end"
    ):
        raise CorrelationError("measurement window is unordered")
    return receipt, window


def _validate_log_capture(
    document: Any, *, auth_log_sha256: str, run_id: str, window: dict[str, str],
) -> dict[str, Any]:
    keys = {
        "schema", "schemaVersion", "status", "runId", "service", "containerId",
        "source", "measurementWindow", "capturedLog", "logParameters",
    }
    if not isinstance(document, dict) or set(document) != keys:
        raise CorrelationError("service-log-capture receipt fields differ")
    capture = document.get("capturedLog")
    parameters = document.get("logParameters")
    if (
        document.get("schema") != "teastore.service-log-capture-receipt"
        or document.get("schemaVersion") != 1
        or document.get("status") != "complete"
        or document.get("runId") != run_id
        or document.get("service") != "auth"
        or not isinstance(document.get("containerId"), str)
        or CONTAINER_ID.fullmatch(document["containerId"]) is None
        or document.get("source") != "docker-container-stdout-stderr"
        or document.get("measurementWindow") != window
        or not isinstance(capture, dict)
        or set(capture) != {"scope", "path", "sha256", "complete"}
        or capture.get("scope") != "measurement-window"
        or _safe_relative(capture.get("path"), "captured auth log path") != "auth.log"
        or capture.get("sha256") != auth_log_sha256
        or capture.get("complete") is not True
        or not isinstance(parameters, dict)
        or set(parameters) != {
            "name", "inspectionSource", "state", "rawValue", "parameterLoggingEnabled",
        }
        or parameters.get("name") != "LOG_PARAMETERS"
        or parameters.get("inspectionSource") != "container-config-env"
    ):
        raise CorrelationError("service-log-capture scope, identity, or hash differs")
    state = parameters.get("state")
    raw = parameters.get("rawValue")
    if parameters.get("parameterLoggingEnabled") is not False or not (
        (state == "absent" and raw is None) or (state == "false" and raw == "false")
    ):
        raise CorrelationError("LOG_PARAMETERS was not proven absent or exactly false")
    return document


def _bridge_rows(payload: bytes) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    try:
        raw_text = payload.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise CorrelationError("auth log is not UTF-8") from exc
    # JVM stack-frame source locations are not assignments in the traffic sweep only (secret_scan.JVM_SOURCE_KEY).
    if _SECRET_SCAN.contains_secret_text(raw_text, jvm_source_locations=SWEEP_EPOCH_ACTIVE):
        raise CorrelationError("auth log contains secret-bearing raw text")
    lines = raw_text.splitlines()
    for number, line in enumerate(lines, 1):
        if MARKER not in line:
            continue
        if line.count(MARKER) != 1:
            raise CorrelationError(f"auth log line {number} contains multiple bridge markers")
        row = _strict_json(line.split(MARKER, 1)[1].encode(), f"auth bridge line {number}")
        if (
            not isinstance(row, dict)
            or set(row) != BRIDGE_KEYS
            or row.get("service") != "auth"
            or not isinstance(row.get("token"), str)
            or TOKEN.fullmatch(row["token"]) is None
        ):
            raise CorrelationError(f"auth bridge line {number} violates the fixed schema")
        rows.append({
            "token": row["token"],
            "nativeTraceId": canonical_native_trace_id(row.get("nativeTraceId")),
            "service": "auth",
        })
    return rows


def _native_trace_ids(value: Any) -> tuple[set[str], int]:
    if not isinstance(value, list):
        raise CorrelationError("traces.json is not an array")
    ids: set[str] = set()
    for number, event in enumerate(value, 1):
        if not isinstance(event, dict):
            raise CorrelationError(f"native event {number} is not an object")
        smuggled = sorted(TOKEN_SMUGGLING_FIELDS & set(event))
        if smuggled:
            raise CorrelationError(
                f"native event {number} carries forbidden token fields: {smuggled}")
        trace_id = canonical_native_trace_id(event.get("trace_id"))
        kieker_id = canonical_native_trace_id(event.get("kieker_trace_id"))
        if event.get("source") != "kieker_native" or trace_id != kieker_id:
            raise CorrelationError(f"native event {number} lacks original Kieker provenance")
        explicit = event.get("original_native_trace_id")
        if explicit is not None and canonical_native_trace_id(explicit) != trace_id:
            raise CorrelationError(f"native event {number} has conflicting native identity")
        source = event.get("nativeTraceIdSource")
        if source is not None and source != "kieker-original":
            raise CorrelationError(f"native event {number} uses a synthetic identity source")
        ids.add(trace_id)
    return ids, len(value)


def _mapping_id(row: dict[str, str]) -> str:
    return _sha256_bytes(_canonical_bytes(row))


def _required_bridge_tokens(
    ledger_rows: list[dict[str, Any]], run_receipt: dict[str, Any],
) -> set[str]:
    run = run_receipt["run"]
    if run["posture"] == "none":
        return set()
    regime = run.get("regime")
    if regime == "no-fault-cost":
        return {row["opaqueToken"] for row in ledger_rows}
    if regime not in EFFECT_REGIMES:
        raise CorrelationError("run receipt regime is invalid")
    intervention = run_receipt.get("intervention")
    if not isinstance(intervention, dict):
        raise CorrelationError("effect run lacks intervention timing")
    try:
        onset = float(intervention["actualOnsetMonotonicOffsetSeconds"])
        offset = float(intervention["actualOffsetMonotonicOffsetSeconds"])
        readiness = float(intervention["readiness"]["observedAtMonotonicOffsetSeconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CorrelationError("effect intervention timing is invalid") from exc
    if not onset < offset <= readiness:
        raise CorrelationError("effect intervention timing is unordered")
    # Traffic sweep, Q3: a journey that started inside the post-readiness drain allowance and failed is not scored.
    allowance = _STUDY_EPOCH.drain_allowance(run_receipt) if SWEEP_EPOCH_ACTIVE else None
    required: set[str] = set()
    for row in ledger_rows:
        start = row.get("actualStartMonotonic")
        end = row.get("actualEndMonotonic")
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               for value in (start, end)):
            raise CorrelationError("effect journey lacks monotonic bounds")
        # F-ADH-079: classify by the journey's whole span, not by its start.
        if float(end) <= onset or float(start) >= readiness:
            if float(end) > onset and _STUDY_EPOCH.drain_excused(
                    start, readiness, row.get("outcome"), allowance):
                continue
            required.add(row["opaqueToken"])
    return required


def _entry_point_woven(posture_proof: Path) -> tuple[bool, bytes]:
    """Return (entry point woven, raw posture-proof bytes) from the retained proof.

    Wovenness is closure membership, not a posture name: the entry point is
    woven exactly when the proof's closureGroups intersect the collector's
    trace-root activation groups. A proof whose closureGroups are missing or
    malformed is treated as woven so the trace-to-token gate stays strict when
    the closure cannot be proven.
    """
    proof_bytes = _file_bytes(posture_proof, "posture proof")
    proof = _strict_json(proof_bytes, "posture proof")
    closure = proof.get("closureGroups") if isinstance(proof, dict) else None
    if not isinstance(closure, list) or not all(
        isinstance(group, str) for group in closure
    ):
        closure = None
    return _NATIVE_COLLECTOR.entry_point_woven(closure), proof_bytes


def reconcile(
    *, auth_log: Path, journey_ledger: Path, traces: Path, run_receipt: Path,
    service_log_capture_receipt: Path, posture_proof: Path,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Replay all retained inputs and return expected mapping rows and receipt."""
    auth_bytes = _file_bytes(auth_log, "auth log")
    trace_bytes = _file_bytes(traces, "native traces")
    trace_document = _strict_json(trace_bytes, "native traces")
    trace_ids, native_events = _native_trace_ids(trace_document)
    ledger_rows, journey_plan, ledger_validation = _read_ledger(journey_ledger)
    run, window = _run_identity(run_receipt)
    capture_bytes = _file_bytes(
        service_log_capture_receipt, "service-log-capture receipt")
    capture = _strict_json(capture_bytes, "service-log-capture receipt")
    capture = _validate_log_capture(
        capture,
        auth_log_sha256=_sha256_bytes(auth_bytes),
        run_id=run["run"]["runId"],
        window=window,
    )
    bridge = _bridge_rows(auth_bytes)
    # F-ADH-078: a thawed service replays the requests it could not serve, and
    # every replay of the same request logs the same bridge row -- same token,
    # same native trace, same service. Those rows are byte-identical, so they
    # carry no information and no contradiction; collapse them and count how
    # many were collapsed. The duplicate-token rule below then means what its
    # own comment always claimed: one token resolving to DIFFERENT native
    # traces. by_token already collapsed them silently downstream, so this only
    # makes the arithmetic honest about it.
    collapsed_bridge: list[dict[str, str]] = []
    seen_bridge: set[tuple[str, str, str]] = set()
    for row in bridge:
        identity = (row["token"], row["nativeTraceId"], row["service"])
        if identity in seen_bridge:
            continue
        seen_bridge.add(identity)
        collapsed_bridge.append(row)
    collapsed_bridge_observations = len(bridge) - len(collapsed_bridge)
    bridge = collapsed_bridge
    expected_tokens = [row["opaqueToken"] for row in ledger_rows]
    expected_set = set(expected_tokens)
    unknown = sorted({row["token"] for row in bridge} - expected_set)
    if unknown:
        raise CorrelationError(f"bridge contains tokens absent from the ledger: {unknown[:10]}")
    token_counts = Counter(row["token"] for row in bridge)
    trace_counts = Counter(row["nativeTraceId"] for row in bridge)
    duplicate_tokens = sorted(token for token, count in token_counts.items() if count != 1)
    duplicate_traces = sorted(trace for trace, count in trace_counts.items() if count != 1)
    if duplicate_tokens:
        # A request token mapping to more than one DISTINCT native trace (its
        # telemetry split across traces) is a genuine defect in every posture.
        # Byte-identical repeats were collapsed above (F-ADH-078), so reaching
        # here means the trace ids really differ.
        raise CorrelationError(f"one token maps more than once: {duplicate_tokens[:10]}")
    # F-ADH-065: when the woven closure omits every trace-root (entry-point)
    # activation group, native traces degenerate to one-per-worker-thread and
    # legitimately carry many request tokens, so a native trace mapping to
    # multiple tokens is the expected structural shape, not a defect. Wovenness
    # is keyed on the retained posture proof's closureGroups, not the posture
    # name, so a future placement whose closure keeps the entry point stays
    # strict. This is the token-correlation twin of F-ADH-062/064.
    entry_point_woven, posture_proof_bytes = _entry_point_woven(posture_proof)
    if duplicate_traces and entry_point_woven:
        raise CorrelationError(f"one native trace maps to multiple tokens: {duplicate_traces[:10]}")
    missing_native = sorted({row["nativeTraceId"] for row in bridge} - trace_ids)
    if missing_native:
        raise CorrelationError(f"bridge references absent native traces: {missing_native[:10]}")
    if run["run"]["posture"] == "none" and (bridge or trace_ids):
        raise CorrelationError("none posture must retain no bridge rows and no native events")
    required_tokens = _required_bridge_tokens(ledger_rows, run)
    missing_required = sorted(required_tokens - set(token_counts))
    if missing_required:
        raise CorrelationError(
            "required scored tokens have no native bridge: "
            f"{missing_required[:10]}")
    by_token = {row["token"]: row for row in bridge}
    mappings: list[dict[str, str]] = []
    for token in expected_tokens:
        if token not in required_tokens:
            continue
        core = dict(by_token[token])
        mappings.append({"mappingId": _mapping_id(core), **core})
    output_bytes = _canonical_bytes(mappings) + b"\n"
    receipt = {
        "schema": "teastore.native-token-correlation-extraction-receipt",
        "schemaVersion": 1,
        "status": "complete",
        "sourceCommit": BASE_COMMIT,
        "runId": run["run"]["runId"],
        "posture": run["run"]["posture"],
        "entryPointWoven": entry_point_woven,
        "measurementWindow": window,
        "counts": {
            "ledgerJourneys": len(ledger_rows),
            "bridgeObservations": len(bridge),
            "collapsedBridgeObservations": collapsed_bridge_observations,
            "correlationRows": len(mappings),
            "requiredScoredMappings": len(required_tokens),
            "uniqueNativeTraceIds": len(trace_ids),
            "nativeEvents": native_events,
        },
        "inputs": {
            "authLog": {"path": "auth.log", "sha256": _sha256_bytes(auth_bytes)},
            "journeyLedger": {
                "path": "journey-ledger.jsonl",
                "sha256": _sha256(journey_ledger, "journey ledger"),
            },
            "journeyPlan": {
                "path": "journey-ledger.plan.json",
                "sha256": _sha256(journey_plan, "journey plan"),
            },
            "traces": {"path": "traces.json", "sha256": _sha256_bytes(trace_bytes)},
            "serviceLogCaptureReceipt": {
                "path": "service-log-capture.json",
                "sha256": _sha256_bytes(capture_bytes),
            },
            "postureProof": {
                "path": "posture-proof.json",
                "sha256": _sha256_bytes(posture_proof_bytes),
            },
        },
        "journeyLedgerValidation": {
            "verdict": ledger_validation["verdict"],
            "planSha256": ledger_validation["planSha256"],
            "lastRecordSha256": ledger_validation["lastRecordSha256"],
            "terminalJourneys": ledger_validation["terminalJourneys"],
            "state": ledger_validation["state"],
        },
        "serviceLogCapture": {
            "status": capture["status"],
            "measurementScoped": capture["capturedLog"]["scope"] == "measurement-window",
            "logParametersState": capture["logParameters"]["state"],
            "parameterLoggingEnabled": capture["logParameters"]["parameterLoggingEnabled"],
        },
        "nativeTokenCorrelationSha256": _sha256_bytes(output_bytes),
    }
    return mappings, receipt


def _atomic_write(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise CorrelationError(f"output parent is a symlink: {path.parent}")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.link(temporary_name, path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def extract(
    *, auth_log: Path, journey_ledger: Path, traces: Path, run_receipt: Path,
    service_log_capture_receipt: Path, posture_proof: Path, output: Path,
    extraction_receipt: Path,
) -> dict[str, Any]:
    if output == extraction_receipt:
        raise CorrelationError("mapping and extraction receipt paths must differ")
    if output.exists() or output.is_symlink() or extraction_receipt.exists() \
            or extraction_receipt.is_symlink():
        raise FileExistsError("refusing to overwrite retained correlation evidence")
    rows, receipt = reconcile(
        auth_log=auth_log,
        journey_ledger=journey_ledger,
        traces=traces,
        run_receipt=run_receipt,
        service_log_capture_receipt=service_log_capture_receipt,
        posture_proof=posture_proof,
    )
    mapping_bytes = _canonical_bytes(rows) + b"\n"
    receipt_bytes = json.dumps(
        receipt, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True,
    ).encode("utf-8") + b"\n"
    _atomic_write(output, mapping_bytes)
    try:
        _atomic_write(extraction_receipt, receipt_bytes)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auth-log", type=Path, required=True)
    parser.add_argument("--journey-ledger", type=Path, required=True)
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--run-receipt", type=Path, required=True)
    parser.add_argument("--service-log-capture-receipt", type=Path, required=True)
    parser.add_argument("--posture-proof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--extraction-receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = extract(**vars(args))
    except (CorrelationError, FileExistsError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
