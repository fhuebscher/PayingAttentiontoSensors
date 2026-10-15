#!/usr/bin/env python3
"""Fixed-rate TeaStore workload with immutable and append-only journey evidence."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import http.cookiejar
import json
import math
import os
import re
import signal
import statistics
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


AGGREGATE_SCHEMA_VERSION = 2
PLAN_ARTIFACT_TYPE = "teastore-expected-opportunity-plan"
LEDGER_ARTIFACT_TYPE = "teastore-journey-ledger-record"
LEDGER_SCHEMA_VERSION = 1
WORKLOAD_ID = "login-browse-v1"
# Traffic sweep (teastore-traffic-sweep-v1, 2026-10-03): a journey of the login step only.  The workload id
# names the journey shape, so a login-only ledger never passes as a login-browse one.  The default kind is the
# frozen login-browse journey and every frozen output is unchanged.
JOURNEY_KINDS = {"login-browse": WORKLOAD_ID, "login-only": "login-only-v1"}
CORRELATION_HEADER = "X-Observability-Journey-Id"
GENESIS_HASH = "0" * 64
START_BARRIER_PAST_TOLERANCE_SECONDS = 1.0

EXPECTED_PATH = {
    "id": "login-path-v1",
    "claim": "expected-not-executed",
    "requiredLogicalSensors": ["operation:auth", "operation:persistence"],
    "requiredDirectEdge": {
        "parent": "operation:auth",
        "child": "operation:persistence",
        "predicate": "persistence.parentId == auth.spanId in same original native trace",
    },
}
TOKEN_CONTRACT = {
    "generation": "uuid4-before-outcome",
    "requestInjection": {"header": CORRELATION_HEADER, "step": "login"},
    "applicationWitnessExtraction": "required-independent-artifact",
    "nativeTraceExtraction": "required-original-trace-token",
    "uniqueness": "one-token-per-offered-journey",
    "mapping": "one-token-to-one-journey-and-at-most-one-native-trace",
}
CLOCK_CONTRACT = {
    "wallClock": "UTC",
    "monotonicValues": "seconds-relative-to-barrier",
}

_OPAQUE_ID = re.compile(r"^journey-[0-9a-f]{32}$")
_BARRIER_ID = re.compile(r"^barrier-[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ERROR_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_QUERY_KEYS = {
    "authorization", "cookie", "credential", "key", "password", "secret", "token", "username",
}
_STEPS_TO_ROUTES = {
    "login": "login-action",
    "browse-home": "home",
    "browse-category": "category",
    "browse-product": "product",
    "return-home": "home",
}
_TERMINAL_OUTCOMES = {"succeeded", "failed", "timeout", "interrupted", "aborted"}


class WorkloadInterrupted(BaseException):
    """Signal-safe interruption marker that must not become a journey failure."""


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _record_sha256(record: dict) -> str:
    unsigned = dict(record)
    unsigned.pop("recordSha256", None)
    return _sha256(unsigned)


def _id_set_sha256(values: list[str]) -> str:
    return _sha256(sorted(values))


def _utc(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def _exact_keys(value: object, expected: set[str], where: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be an object")
    if set(value) != expected:
        raise ValueError(
            f"{where} keys differ: missing={sorted(expected - set(value))}, "
            f"extra={sorted(set(value) - expected)}")
    return value


def _number(value: object, where: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{where} must be a finite number")
    number = float(value)
    if positive and number <= 0:
        raise ValueError(f"{where} must be positive")
    if not positive and number < 0:
        raise ValueError(f"{where} must be non-negative")
    return number


def _integer(value: object, where: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{where} must be an integer >= {minimum}")
    return value


def _utc_value(value: object, where: str) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{where} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{where} is not a valid ISO-8601 timestamp") from exc
    if parsed.utcoffset() != dt.timedelta(0):
        raise ValueError(f"{where} must be UTC")
    return parsed


def _safe_error_type(value: object, where: str) -> str:
    if not isinstance(value, str) or not _ERROR_TYPE.fullmatch(value):
        raise ValueError(f"{where} must be a bounded error type without free-form text")
    return value


def _safe_target(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.startswith("/") or len(value) > 512:
        raise ValueError(f"{where} must be a bounded relative target")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise ValueError(f"{where} must not contain an origin, credentials, or fragment")
    for key, _ in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        if key.casefold() in _SENSITIVE_QUERY_KEYS:
            raise ValueError(f"{where} contains a sensitive query key")
    return value


def journey_plan_path(ledger_path: Path) -> Path:
    """Derive the immutable plan sibling from the append-only JSONL path."""
    if ledger_path.suffix != ".jsonl":
        raise ValueError("journey ledger path must end in .jsonl")
    return ledger_path.with_suffix(".plan.json")


def _validate_expected_path(value: object, where: str) -> dict:
    path = _exact_keys(value, {
        "id", "claim", "requiredLogicalSensors", "requiredDirectEdge",
    }, where)
    edge = _exact_keys(path["requiredDirectEdge"], {"parent", "child", "predicate"}, f"{where}.requiredDirectEdge")
    normalized = dict(path)
    normalized["requiredDirectEdge"] = edge
    if normalized != EXPECTED_PATH:
        raise ValueError(f"{where} differs from the frozen login-path contract")
    return path


def validate_expected_opportunity_plan(document: object) -> dict:
    root = _exact_keys(document, {
        "artifactType", "schemaVersion", "workloadId", "barrierId",
        "controllerStartedAt", "barrierAt", "clock", "schedule", "expectedPath",
        "tokenContract", "opportunities",
    }, "plan")
    if root["artifactType"] != PLAN_ARTIFACT_TYPE or root["schemaVersion"] != LEDGER_SCHEMA_VERSION:
        raise ValueError("plan schema binding differs")
    if root["workloadId"] not in JOURNEY_KINDS.values():
        raise ValueError("plan workloadId differs")
    workload_id = root["workloadId"]
    if not isinstance(root["barrierId"], str) or not _BARRIER_ID.fullmatch(root["barrierId"]):
        raise ValueError("plan barrierId is invalid")
    controller_started = _utc_value(root["controllerStartedAt"], "plan.controllerStartedAt")
    barrier_at = _utc_value(root["barrierAt"], "plan.barrierAt")
    if root["clock"] != CLOCK_CONTRACT:
        raise ValueError("plan clock contract differs")
    schedule = _exact_keys(root["schedule"], {
        "kind", "journeysPerSecond", "durationSeconds", "offered",
    }, "plan.schedule")
    if schedule["kind"] != "fixed-open-loop":
        raise ValueError("plan schedule kind differs")
    rate = _number(schedule["journeysPerSecond"], "plan.schedule.journeysPerSecond", positive=True)
    duration = _number(schedule["durationSeconds"], "plan.schedule.durationSeconds", positive=True)
    offered = _integer(schedule["offered"], "plan.schedule.offered", minimum=1)
    if offered != max(1, math.floor(rate * duration)):
        raise ValueError("plan offered count differs from fixed schedule")
    _validate_expected_path(root["expectedPath"], "plan.expectedPath")
    if root["tokenContract"] != TOKEN_CONTRACT:
        raise ValueError("plan token contract differs")
    opportunities = root["opportunities"]
    if not isinstance(opportunities, list) or len(opportunities) != offered:
        raise ValueError("plan opportunities do not equal offered count")
    ids: set[str] = set()
    tokens: set[str] = set()
    opportunity_ids: set[str] = set()
    for index, value in enumerate(opportunities):
        where = f"plan.opportunities[{index}]"
        row = _exact_keys(value, {
            "sequence", "journeyId", "opportunityId", "opaqueToken", "tokenAllocatedAt",
            "scheduledAt", "scheduledMonotonicOffsetSeconds",
        }, where)
        if row["sequence"] != index:
            raise ValueError(f"{where}.sequence is not contiguous")
        if not isinstance(row["journeyId"], str) or not _OPAQUE_ID.fullmatch(row["journeyId"]):
            raise ValueError(f"{where}.journeyId is invalid")
        if row["journeyId"] in ids:
            raise ValueError("plan contains duplicate journey IDs")
        ids.add(row["journeyId"])
        if row["opaqueToken"] != row["journeyId"] or row["opaqueToken"] in tokens:
            raise ValueError("plan opaque tokens are not unique journey IDs")
        tokens.add(row["opaqueToken"])
        expected_opportunity = f"{workload_id}:{index:06d}"
        if row["opportunityId"] != expected_opportunity or row["opportunityId"] in opportunity_ids:
            raise ValueError(f"{where}.opportunityId is invalid or duplicated")
        opportunity_ids.add(row["opportunityId"])
        allocated = _utc_value(row["tokenAllocatedAt"], f"{where}.tokenAllocatedAt")
        scheduled = _utc_value(row["scheduledAt"], f"{where}.scheduledAt")
        expected_offset = index / rate
        actual_offset = _number(
            row["scheduledMonotonicOffsetSeconds"],
            f"{where}.scheduledMonotonicOffsetSeconds",
        )
        if abs(actual_offset - expected_offset) > 1e-9:
            raise ValueError(f"{where} scheduled offset differs")
        expected_scheduled = barrier_at + dt.timedelta(seconds=expected_offset)
        if abs((scheduled - expected_scheduled).total_seconds()) > 1e-6:
            raise ValueError(f"{where}.scheduledAt differs from barrier schedule")
        if allocated < controller_started - dt.timedelta(seconds=0.001):
            raise ValueError(f"{where}.tokenAllocatedAt precedes controller start")
    return {
        "plan": root,
        "planSha256": _sha256(root),
        "opportunities": {row["journeyId"]: row for row in opportunities},
        "durationSeconds": duration,
        "offered": offered,
        "workloadId": workload_id,
    }


def _load_jsonl(path: Path) -> list[dict]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read journey ledger: {exc}") from exc
    if not payload:
        raise ValueError("journey ledger is empty")
    if not payload.endswith(b"\n"):
        raise ValueError("journey ledger has a truncated final line")
    raw_lines = payload.splitlines()
    if any(not line.strip() for line in raw_lines):
        raise ValueError("journey ledger contains an empty line")
    records: list[dict] = []
    for index, line in enumerate(raw_lines):
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"journey ledger line {index + 1} is invalid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError(f"journey ledger line {index + 1} is not an object")
        records.append(value)
    return records


def _validate_request(value: object, where: str, *, journey_start: float, journey_end: float) -> dict:
    request = _exact_keys(value, {
        "sequence", "step", "routeId", "target", "actualStartMonotonic",
        "actualEndMonotonic", "startedAt", "endedAt", "latencyMs", "statusCode",
        "outcome", "error",
    }, where)
    sequence = _integer(request["sequence"], f"{where}.sequence")
    if request["step"] not in _STEPS_TO_ROUTES or request["routeId"] != _STEPS_TO_ROUTES[request["step"]]:
        raise ValueError(f"{where} step/route identity differs")
    _safe_target(request["target"], f"{where}.target")
    started = _number(request["actualStartMonotonic"], f"{where}.actualStartMonotonic")
    ended = _number(request["actualEndMonotonic"], f"{where}.actualEndMonotonic")
    if started + 1e-6 < journey_start or ended + 1e-6 < started or ended > journey_end + 1e-6:
        raise ValueError(f"{where} monotonic window is outside its journey")
    _utc_value(request["startedAt"], f"{where}.startedAt")
    _utc_value(request["endedAt"], f"{where}.endedAt")
    latency = _number(request["latencyMs"], f"{where}.latencyMs")
    if abs(latency - (ended - started) * 1000) > 1.0:
        raise ValueError(f"{where}.latencyMs differs from monotonic duration")
    status = request["statusCode"]
    if status is not None and (
        isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599
    ):
        raise ValueError(f"{where}.statusCode is invalid")
    if request["outcome"] not in {"succeeded", "failed"}:
        raise ValueError(f"{where}.outcome is invalid")
    error = request["error"]
    if error is not None:
        error = _exact_keys(error, {"type"}, f"{where}.error")
        _safe_error_type(error["type"], f"{where}.error.type")
    if (request["outcome"] == "succeeded") != (error is None):
        raise ValueError(f"{where} outcome and error disagree")
    if sequence < 0:  # unreachable after _integer; documents the contiguous check caller owns
        raise ValueError(f"{where}.sequence is invalid")
    return request


def _validate_journey_record(
    record: dict,
    where: str,
    *,
    plan_info: dict,
) -> None:
    row = _exact_keys(record, {
        "artifactType", "schemaVersion", "recordType", "recordSequence",
        "previousRecordSha256", "recordSha256", "planSha256", "workloadId", "barrierId",
        "sequence", "journeyId", "opportunityId", "opaqueToken", "tokenAllocatedAt",
        "scheduledAt", "scheduledMonotonicOffsetSeconds", "actualStartMonotonic",
        "actualEndMonotonic", "startedAt", "endedAt", "expectedPath", "requests",
        "requestCount", "outcome", "errors", "terminalSettled", "endedAfterNominalWindow",
    }, where)
    if row["recordType"] != "journey-terminal":
        raise ValueError(f"{where}.recordType differs")
    if row["workloadId"] != plan_info["workloadId"] or row["barrierId"] != plan_info["plan"]["barrierId"]:
        raise ValueError(f"{where} workload/barrier binding differs")
    journey_id = row["journeyId"]
    planned = plan_info["opportunities"].get(journey_id)
    if planned is None:
        raise ValueError(f"{where}.journeyId is not in the immutable plan")
    for field in (
        "sequence", "journeyId", "opportunityId", "opaqueToken", "tokenAllocatedAt",
        "scheduledAt", "scheduledMonotonicOffsetSeconds",
    ):
        if row[field] != planned[field]:
            raise ValueError(f"{where}.{field} differs from immutable plan")
    _validate_expected_path(row["expectedPath"], f"{where}.expectedPath")
    if row["terminalSettled"] is not True:
        raise ValueError(f"{where} is not terminally settled")
    outcome = row["outcome"]
    if outcome not in _TERMINAL_OUTCOMES:
        raise ValueError(f"{where}.outcome is invalid")
    ended = _number(row["actualEndMonotonic"], f"{where}.actualEndMonotonic")
    _utc_value(row["endedAt"], f"{where}.endedAt")
    if row["endedAfterNominalWindow"] is not (ended > plan_info["durationSeconds"]):
        raise ValueError(f"{where}.endedAfterNominalWindow differs from end time")
    never_started = row["actualStartMonotonic"] is None
    if never_started:
        if outcome not in {"interrupted", "aborted"} or row["startedAt"] is not None:
            raise ValueError(f"{where} unstarted outcome/timestamps disagree")
        journey_start = ended
    else:
        journey_start = _number(row["actualStartMonotonic"], f"{where}.actualStartMonotonic")
        _utc_value(row["startedAt"], f"{where}.startedAt")
        if journey_start + 1e-6 < float(row["scheduledMonotonicOffsetSeconds"]) or ended < journey_start:
            raise ValueError(f"{where} starts before schedule or ends before start")
        if _utc_value(row["tokenAllocatedAt"], f"{where}.tokenAllocatedAt") > _utc_value(
            row["startedAt"], f"{where}.startedAt"
        ):
            raise ValueError(f"{where} token was not allocated before outcome acquisition")
    requests = row["requests"]
    if not isinstance(requests, list):
        raise ValueError(f"{where}.requests must be an array")
    request_error_pairs: set[tuple[int, str]] = set()
    for index, value in enumerate(requests):
        request = _validate_request(
            value,
            f"{where}.requests[{index}]",
            journey_start=journey_start,
            journey_end=ended,
        )
        if request["sequence"] != index:
            raise ValueError(f"{where}.requests sequences are not contiguous")
        if request["error"] is not None:
            request_error_pairs.add((index, request["error"]["type"]))
    if row["requestCount"] != len(requests):
        raise ValueError(f"{where}.requestCount differs from retained requests")
    errors = row["errors"]
    if not isinstance(errors, list):
        raise ValueError(f"{where}.errors must be an array")
    recorded_request_errors: set[tuple[int, str]] = set()
    seen_errors: set[tuple[str, int | None, str]] = set()
    for index, value in enumerate(errors):
        error_where = f"{where}.errors[{index}]"
        error = _exact_keys(value, {"type", "scope", "requestSequence"}, error_where)
        error_type = _safe_error_type(error["type"], f"{error_where}.type")
        if error["scope"] == "request":
            request_sequence = _integer(error["requestSequence"], f"{error_where}.requestSequence")
            if request_sequence >= len(requests):
                raise ValueError(f"{error_where}.requestSequence is out of range")
            recorded_request_errors.add((request_sequence, error_type))
        elif error["scope"] == "journey":
            if error["requestSequence"] is not None:
                raise ValueError(f"{error_where} journey error names a request")
            request_sequence = None
        else:
            raise ValueError(f"{error_where}.scope is invalid")
        key = (error["scope"], request_sequence, error_type)
        if key in seen_errors:
            raise ValueError(f"{where}.errors contains a duplicate")
        seen_errors.add(key)
    if recorded_request_errors != request_error_pairs:
        raise ValueError(f"{where}.errors is not complete for request failures")
    has_timeout = any("timeout" in error["type"].casefold() for error in errors)
    if outcome == "succeeded" and errors:
        raise ValueError(f"{where} succeeded with errors")
    if outcome != "succeeded" and not errors:
        raise ValueError(f"{where} non-success lacks an error")
    if outcome == "timeout" and not has_timeout:
        raise ValueError(f"{where} timeout outcome and errors disagree")
    if outcome == "failed" and has_timeout:
        raise ValueError(f"{where} failure with timeout evidence must use timeout outcome")


def validate_journey_ledger(plan: object | Path, ledger_path: Path) -> dict:
    """Reconcile immutable opportunities against a complete hash-chained JSONL ledger."""
    if isinstance(plan, Path):
        try:
            plan = json.loads(plan.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read expected-opportunity plan: {exc}") from exc
    plan_info = validate_expected_opportunity_plan(plan)
    records = _load_jsonl(ledger_path)
    previous = GENESIS_HASH
    journey_records: list[dict] = []
    reconciliation: dict | None = None
    for index, record in enumerate(records):
        where = f"ledger record {index}"
        if record.get("artifactType") != LEDGER_ARTIFACT_TYPE or record.get("schemaVersion") != LEDGER_SCHEMA_VERSION:
            raise ValueError(f"{where} schema binding differs")
        if record.get("recordSequence") != index:
            raise ValueError(f"{where} recordSequence is not contiguous")
        if record.get("previousRecordSha256") != previous:
            raise ValueError(f"{where} breaks the hash chain")
        claimed_hash = record.get("recordSha256")
        if not isinstance(claimed_hash, str) or not _HASH.fullmatch(claimed_hash) or claimed_hash != _record_sha256(record):
            raise ValueError(f"{where} record hash differs")
        if record.get("planSha256") != plan_info["planSha256"]:
            raise ValueError(f"{where} plan hash differs")
        previous = claimed_hash
        if record.get("recordType") == "journey-terminal":
            if reconciliation is not None:
                raise ValueError("journey record appears after reconciliation")
            _validate_journey_record(record, where, plan_info=plan_info)
            journey_records.append(record)
        elif record.get("recordType") == "reconciliation":
            if reconciliation is not None or index != len(records) - 1:
                raise ValueError("reconciliation must be unique and final")
            reconciliation = _exact_keys(record, {
                "artifactType", "schemaVersion", "recordType", "recordSequence",
                "previousRecordSha256", "recordSha256", "planSha256", "workloadId", "barrierId",
                "state", "terminalReason", "expectedJourneys", "terminalJourneys",
                "terminalJourneyIdsSha256", "terminalOpportunityIdsSha256", "finalizedAt",
                "terminalSettled",
            }, where)
        else:
            raise ValueError(f"{where}.recordType is invalid")
    if reconciliation is None:
        raise ValueError("journey ledger is truncated or lacks final reconciliation")
    if len(records) != plan_info["offered"] + 1 or len(journey_records) != plan_info["offered"]:
        raise ValueError("journey terminal row count differs from immutable plan")
    journey_ids = [row["journeyId"] for row in journey_records]
    opportunity_ids = [row["opportunityId"] for row in journey_records]
    if len(journey_ids) != len(set(journey_ids)):
        raise ValueError("journey ledger contains duplicate journey IDs")
    if len(opportunity_ids) != len(set(opportunity_ids)):
        raise ValueError("journey ledger contains duplicate opportunity IDs")
    if set(journey_ids) != set(plan_info["opportunities"]):
        raise ValueError("journey ledger terminal IDs differ from immutable plan")
    if reconciliation["workloadId"] != plan_info["workloadId"] or reconciliation["barrierId"] != plan_info["plan"]["barrierId"]:
        raise ValueError("reconciliation workload/barrier binding differs")
    state = reconciliation["state"]
    if state not in {"completed", "interrupted", "failed"}:
        raise ValueError("reconciliation state is invalid")
    reason = reconciliation["terminalReason"]
    if state == "completed":
        if reason is not None or any(row["outcome"] in {"interrupted", "aborted"} for row in journey_records):
            raise ValueError("completed reconciliation contains interruption/abort state")
    else:
        _safe_error_type(reason, "reconciliation.terminalReason")
    if reconciliation["expectedJourneys"] != plan_info["offered"] or reconciliation["terminalJourneys"] != len(journey_records):
        raise ValueError("reconciliation journey counts differ")
    if reconciliation["terminalJourneyIdsSha256"] != _id_set_sha256(journey_ids):
        raise ValueError("reconciliation journey ID hash differs")
    if reconciliation["terminalOpportunityIdsSha256"] != _id_set_sha256(opportunity_ids):
        raise ValueError("reconciliation opportunity ID hash differs")
    _utc_value(reconciliation["finalizedAt"], "reconciliation.finalizedAt")
    if reconciliation["terminalSettled"] is not True:
        raise ValueError("reconciliation is not terminally settled")
    return {
        "verdict": "pass",
        "planSha256": plan_info["planSha256"],
        "records": len(records),
        "terminalJourneys": len(journey_records),
        "state": state,
        "lastRecordSha256": records[-1]["recordSha256"],
    }


def _write_immutable_json(path: Path, document: dict) -> None:
    """Publish a fully written file exactly once without replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(document, temporary, indent=2, sort_keys=True, allow_nan=False)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.link(temporary_name, path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


class AppendOnlyJourneyLedger:
    """Immutable plan plus O_APPEND terminal records and final reconciliation."""

    def __init__(self, ledger_path: Path, plan: dict) -> None:
        self.ledger_path = ledger_path
        self.plan_path = journey_plan_path(ledger_path)
        self._lock = threading.RLock()
        self._plan_info = validate_expected_opportunity_plan(plan)
        self._plan = plan
        self._runtime: dict[str, dict | None] = {
            row["journeyId"]: None for row in plan["opportunities"]
        }
        self._terminal: set[str] = set()
        self._record_sequence = 0
        self._previous_hash = GENESIS_HASH
        self._closed = False
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(
            ledger_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND,
            0o600,
        )
        try:
            _write_immutable_json(self.plan_path, plan)
        except BaseException:
            os.close(self._fd)
            ledger_path.unlink(missing_ok=True)
            raise

    def _append(self, record: dict) -> dict:
        with self._lock:
            if self._closed:
                raise RuntimeError("journey ledger is already finalized")
            complete = {
                "artifactType": LEDGER_ARTIFACT_TYPE,
                "schemaVersion": LEDGER_SCHEMA_VERSION,
                "recordSequence": self._record_sequence,
                "previousRecordSha256": self._previous_hash,
                "planSha256": self._plan_info["planSha256"],
                **record,
            }
            complete["recordSha256"] = _record_sha256(complete)
            payload = _canonical(complete) + b"\n"
            view = memoryview(payload)
            while view:
                written = os.write(self._fd, view)
                if written <= 0:
                    raise OSError("append-only ledger write made no progress")
                view = view[written:]
            os.fsync(self._fd)
            self._record_sequence += 1
            self._previous_hash = complete["recordSha256"]
            return complete

    def start(self, journey_id: str, barrier_monotonic: float) -> tuple[float, float]:
        with self._lock:
            if journey_id not in self._runtime or self._runtime[journey_id] is not None:
                raise RuntimeError("journey start is unknown or duplicated")
            started_wall = time.time()
            started_monotonic = time.monotonic()
            self._runtime[journey_id] = {
                "startedAt": _utc(started_wall),
                "actualStartMonotonic": max(0.0, started_monotonic - barrier_monotonic),
            }
            return started_wall, started_monotonic

    def _terminal_record(
        self,
        journey_id: str,
        *,
        evidence: dict,
    ) -> dict:
        planned = self._plan_info["opportunities"][journey_id]
        runtime = self._runtime[journey_id]
        return {
            "recordType": "journey-terminal",
            "workloadId": self._plan_info["workloadId"],
            "barrierId": self._plan["barrierId"],
            **planned,
            "actualStartMonotonic": runtime["actualStartMonotonic"] if runtime else None,
            "actualEndMonotonic": evidence["actualEndMonotonic"],
            "startedAt": runtime["startedAt"] if runtime else None,
            "endedAt": evidence["endedAt"],
            "expectedPath": EXPECTED_PATH,
            "requests": evidence["requests"],
            "requestCount": len(evidence["requests"]),
            "outcome": evidence["outcome"],
            "errors": evidence["errors"],
            "terminalSettled": True,
            "endedAfterNominalWindow": (
                evidence["actualEndMonotonic"] > self._plan_info["durationSeconds"]),
        }

    def finish(self, journey_id: str, evidence: dict) -> None:
        with self._lock:
            if journey_id in self._terminal or self._runtime.get(journey_id) is None:
                raise RuntimeError("journey terminalization is unknown, unstarted, or duplicated")
            self._append(self._terminal_record(journey_id, evidence=evidence))
            self._terminal.add(journey_id)

    def finalize(self, state: str, reason: str | None, barrier_monotonic: float) -> dict:
        with self._lock:
            if state not in {"completed", "interrupted", "failed"}:
                raise ValueError("terminal ledger state is invalid")
            if self._closed:
                raise RuntimeError("journey ledger is already finalized")
            missing = [
                row["journeyId"] for row in self._plan["opportunities"]
                if row["journeyId"] not in self._terminal
            ]
            if state == "completed" and missing:
                state = "failed"
                reason = "IncompleteJourney"
            terminal_type = "Interrupted" if state == "interrupted" else (reason or "Aborted")
            for journey_id in missing:
                now_wall = time.time()
                now_offset = max(0.0, time.monotonic() - barrier_monotonic)
                evidence = {
                    "actualEndMonotonic": now_offset,
                    "endedAt": _utc(now_wall),
                    "outcome": "interrupted" if state == "interrupted" else "aborted",
                    "requests": [],
                    "errors": [{
                        "type": terminal_type,
                        "scope": "journey",
                        "requestSequence": None,
                    }],
                }
                self._append(self._terminal_record(journey_id, evidence=evidence))
                self._terminal.add(journey_id)
            journey_ids = list(self._terminal)
            opportunity_ids = [
                self._plan_info["opportunities"][journey_id]["opportunityId"]
                for journey_id in journey_ids
            ]
            final_record = self._append({
                "recordType": "reconciliation",
                "workloadId": self._plan_info["workloadId"],
                "barrierId": self._plan["barrierId"],
                "state": state,
                "terminalReason": None if state == "completed" else reason,
                "expectedJourneys": self._plan_info["offered"],
                "terminalJourneys": len(self._terminal),
                "terminalJourneyIdsSha256": _id_set_sha256(journey_ids),
                "terminalOpportunityIdsSha256": _id_set_sha256(opportunity_ids),
                "finalizedAt": _utc(time.time()),
                "terminalSettled": True,
            })
            self._closed = True
            os.close(self._fd)
            validation = validate_journey_ledger(self.plan_path, self.ledger_path)
            validation["reconciliation"] = final_record
            return validation


def _request_evidence(
    *,
    sequence: int,
    step: str,
    target: str,
    started_wall: float,
    started_monotonic: float,
    ended_wall: float,
    ended_monotonic: float,
    barrier_monotonic: float,
    status_code: int | None,
    error_type: str | None,
) -> dict:
    return {
        "sequence": sequence,
        "step": step,
        "routeId": _STEPS_TO_ROUTES[step],
        "target": target,
        "actualStartMonotonic": max(0.0, started_monotonic - barrier_monotonic),
        "actualEndMonotonic": max(0.0, ended_monotonic - barrier_monotonic),
        "startedAt": _utc(started_wall),
        "endedAt": _utc(ended_wall),
        "latencyMs": max(0.0, (ended_monotonic - started_monotonic) * 1000),
        "statusCode": status_code,
        "outcome": "failed" if error_type else "succeeded",
        "error": {"type": error_type} if error_type else None,
    }


def journey(
    base: str,
    user: str,
    timeout: float,
    *,
    journey_id: str | None = None,
    barrier_monotonic: float | None = None,
    started_wall: float | None = None,
    started_monotonic: float | None = None,
    journey_kind: str = "login-browse",
) -> dict:
    started_wall = time.time() if started_wall is None else started_wall
    started_monotonic = time.monotonic() if started_monotonic is None else started_monotonic
    barrier_monotonic = started_monotonic if barrier_monotonic is None else barrier_monotonic
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    errors: list[str] = []
    structured_errors: list[dict] = []
    request_rows: list[dict] = []

    def request(step: str, path: str, data: dict | None = None) -> str:
        encoded = urllib.parse.urlencode(data).encode() if data else None
        req = urllib.request.Request(base + path, data=encoded)
        if journey_id is not None and step == "login":
            req.add_header(CORRELATION_HEADER, journey_id)
        request_started_wall = time.time()
        request_started_monotonic = time.monotonic()
        status_code: int | None = None
        error_type: str | None = None
        body = ""
        try:
            with opener.open(req, timeout=timeout) as response:
                status_code = int(response.status)
                if response.status >= 500:
                    error_type = "HTTPStatusError"
                    errors.append(f"HTTP {response.status} {path}")
                body = response.read().decode(errors="replace")
        except Exception as exc:  # noqa: BLE001 - errors retain type/path, never free-form exception text
            code = getattr(exc, "code", None)
            status_code = int(code) if isinstance(code, int) and not isinstance(code, bool) else None
            error_type = type(exc).__name__
            errors.append(f"{error_type} {path}")
        request_ended_wall = time.time()
        request_ended_monotonic = time.monotonic()
        sequence = len(request_rows)
        request_rows.append(_request_evidence(
            sequence=sequence,
            step=step,
            target=path,
            started_wall=request_started_wall,
            started_monotonic=request_started_monotonic,
            ended_wall=request_ended_wall,
            ended_monotonic=request_ended_monotonic,
            barrier_monotonic=barrier_monotonic,
            status_code=status_code,
            error_type=error_type,
        ))
        if error_type:
            structured_errors.append({
                "type": error_type,
                "scope": "request",
                "requestSequence": sequence,
            })
        return body

    request("login", "/loginAction", {
        "username": user, "password": "password", "signin": "Sign in",
    })
    if journey_kind == "login-only":
        pass
    elif journey_kind == "login-browse":
        home = request("browse-home", "/")
        categories = list(dict.fromkeys(re.findall(r"category=([0-9]+)", home)))[:3]
        if not categories:
            errors.append("no categories")
            structured_errors.append({
                "type": "NoCategories", "scope": "journey", "requestSequence": None,
            })
        for category in categories:
            page = request("browse-category", f"/category?category={category}&number=30")
            products = list(dict.fromkeys(re.findall(r"product\?id=([0-9]+)", page)))[:3]
            for product in products:
                request("browse-product", f"/product?id={product}")
        request("return-home", "/")
    else:
        raise ValueError(f"unknown journey kind: {journey_kind}")
    ended_wall = time.time()
    ended_monotonic = time.monotonic()
    has_timeout = any("timeout" in error["type"].casefold() for error in structured_errors)
    outcome = "timeout" if has_timeout else ("failed" if errors else "succeeded")
    return {
        "durationMs": (ended_monotonic - started_monotonic) * 1000,
        "requests": len(request_rows),
        "ok": outcome == "succeeded",
        "outcome": outcome,
        "errors": errors,
        "_ledger": {
            "actualEndMonotonic": max(0.0, ended_monotonic - barrier_monotonic),
            "endedAt": _utc(ended_wall),
            "outcome": outcome,
            "errors": structured_errors,
            "requests": request_rows,
        },
    }


def _execute_journey(
    ledger: AppendOnlyJourneyLedger,
    journey_id: str,
    barrier_monotonic: float,
    base: str,
    user: str,
    timeout: float,
    journey_kind: str = "login-browse",
) -> dict:
    started_wall, started_monotonic = ledger.start(journey_id, barrier_monotonic)
    try:
        result = journey(
            base,
            user,
            timeout,
            journey_id=journey_id,
            barrier_monotonic=barrier_monotonic,
            started_wall=started_wall,
            started_monotonic=started_monotonic,
            journey_kind=journey_kind,
        )
    except Exception as exc:  # noqa: BLE001 - retain only the safe exception class
        ended_wall = time.time()
        ended_monotonic = time.monotonic()
        error_type = type(exc).__name__
        result = {
            "durationMs": (ended_monotonic - started_monotonic) * 1000,
            "requests": 0,
            "ok": False,
            "outcome": "timeout" if "timeout" in error_type.casefold() else "failed",
            "errors": [f"internal journey failure: {error_type}"],
            "_ledger": {
                "actualEndMonotonic": max(0.0, ended_monotonic - barrier_monotonic),
                "endedAt": _utc(ended_wall),
                "outcome": "timeout" if "timeout" in error_type.casefold() else "failed",
                "errors": [{
                    "type": error_type, "scope": "journey", "requestSequence": None,
                }],
                "requests": [],
            },
        }
    ledger.finish(journey_id, result.pop("_ledger"))
    return result


def _new_journey_id() -> str:
    return f"journey-{uuid.uuid4().hex}"


def _default_barrier_id(barrier_epoch: float, workload_id: str = WORKLOAD_ID) -> str:
    digest = hashlib.sha256(f"{workload_id}\0{barrier_epoch:.6f}".encode()).hexdigest()[:20]
    return f"barrier-{digest}"


def run(
    base: str,
    rate: float,
    duration: float,
    concurrency: int,
    timeout: float,
    journey_ledger: Path,
    start_at_epoch: float | None = None,
    barrier_id: str | None = None,
    journey_kind: str = "login-browse",
) -> dict:
    if rate <= 0 or duration <= 0 or concurrency <= 0 or timeout <= 0:
        raise ValueError("rate, duration, concurrency, and timeout must be positive")
    if journey_kind not in JOURNEY_KINDS:
        raise ValueError(f"journey kind must be one of {sorted(JOURNEY_KINDS)}")
    workload_id = JOURNEY_KINDS[journey_kind]
    controller_started_wall = time.time()
    controller_started_monotonic = time.monotonic()
    if start_at_epoch is None:
        barrier_wall = controller_started_wall
    elif isinstance(start_at_epoch, bool) or not isinstance(start_at_epoch, (int, float)) or not math.isfinite(start_at_epoch):
        raise ValueError("start_at_epoch must be a finite UNIX timestamp")
    else:
        barrier_wall = float(start_at_epoch)
        if barrier_wall < controller_started_wall - START_BARRIER_PAST_TOLERANCE_SECONDS:
            raise ValueError("start_at_epoch is more than one second in the past")
    barrier_id = _default_barrier_id(barrier_wall, workload_id) if barrier_id is None else barrier_id
    if not isinstance(barrier_id, str) or not _BARRIER_ID.fullmatch(barrier_id):
        raise ValueError("barrier_id must match barrier-<bounded identifier>")
    barrier_monotonic = controller_started_monotonic + (barrier_wall - controller_started_wall)
    offered = max(1, math.floor(rate * duration))
    ids = [_new_journey_id() for _ in range(offered)]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate journey IDs generated before workload start")
    opportunities = []
    for index, journey_id in enumerate(ids):
        opportunities.append({
            "sequence": index,
            "journeyId": journey_id,
            "opportunityId": f"{workload_id}:{index:06d}",
            "opaqueToken": journey_id,
            "tokenAllocatedAt": _utc(time.time()),
            "scheduledAt": _utc(barrier_wall + index / rate),
            "scheduledMonotonicOffsetSeconds": index / rate,
        })
    plan = {
        "artifactType": PLAN_ARTIFACT_TYPE,
        "schemaVersion": LEDGER_SCHEMA_VERSION,
        "workloadId": workload_id,
        "barrierId": barrier_id,
        "controllerStartedAt": _utc(controller_started_wall),
        "barrierAt": _utc(barrier_wall),
        "clock": CLOCK_CONTRACT,
        "schedule": {
            "kind": "fixed-open-loop",
            "journeysPerSecond": rate,
            "durationSeconds": duration,
            "offered": offered,
        },
        "expectedPath": EXPECTED_PATH,
        "tokenContract": TOKEN_CONTRACT,
        "opportunities": opportunities,
    }
    ledger = AppendOnlyJourneyLedger(journey_ledger, plan)
    results: list[dict] = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = []
            for index, journey_id in enumerate(ids):
                due = barrier_monotonic + index / rate
                delay = due - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                futures.append(pool.submit(
                    _execute_journey,
                    ledger,
                    journey_id,
                    barrier_monotonic,
                    base,
                    f"user{2 + index % 80}",
                    timeout,
                    journey_kind,
                ))
            for future in futures:
                results.append(future.result())
    except BaseException as exc:
        interrupted = isinstance(exc, (KeyboardInterrupt, WorkloadInterrupted))
        ledger.finalize(
            "interrupted" if interrupted else "failed",
            getattr(exc, "signal_name", None) or type(exc).__name__,
            barrier_monotonic,
        )
        raise
    ledger_validation = ledger.finalize("completed", None, barrier_monotonic)
    durations = [item["durationMs"] for item in results if item["ok"]]
    successful = sum(item["outcome"] == "succeeded" for item in results)
    failed = sum(item["outcome"] == "failed" for item in results)
    timed_out = sum(item["outcome"] == "timeout" for item in results)
    return {
        "schemaVersion": AGGREGATE_SCHEMA_VERSION,
        "startedAtEpoch": barrier_wall,
        "controllerStartedAtEpoch": controller_started_wall,
        "endedAtEpoch": time.time(),
        "schedule": {
            "kind": "fixed-open-loop",
            "journeysPerSecond": rate,
            "durationSeconds": duration,
            "barrierAtEpoch": barrier_wall,
            "barrierId": barrier_id,
        },
        "offered": offered,
        "completed": successful,
        "successful": successful,
        "failed": failed,
        "timedOut": timed_out,
        "settled": len(results),
        "concurrency": concurrency,
        "requests": sum(item["requests"] for item in results),
        "latencyMs": {
            "denominator": "successful-journeys",
            "count": len(durations),
            "p50": percentile(durations, 0.50),
            "p95": percentile(durations, 0.95),
            "p99": percentile(durations, 0.99),
            "mean": statistics.fmean(durations) if durations else None,
        },
        "failures": [error for item in results for error in item["errors"]],
        "journeyEvidence": {
            "plan": journey_plan_path(journey_ledger).name,
            "ledger": journey_ledger.name,
            "planSha256": ledger_validation["planSha256"],
            "lastRecordSha256": ledger_validation["lastRecordSha256"],
        },
    }


def _signal_interrupt(signum: int, _frame: object) -> None:
    exc = WorkloadInterrupted(signal.Signals(signum).name)
    exc.signal_name = signal.Signals(signum).name
    raise exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080/tools.descartes.teastore.webui")
    parser.add_argument("--rate", type=float, required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--start-at-epoch", type=float)
    parser.add_argument("--barrier-id")
    parser.add_argument("--journey-ledger", type=Path, required=True)
    parser.add_argument("--journey-kind", choices=sorted(JOURNEY_KINDS), default="login-browse")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.rate <= 0 or args.duration <= 0 or args.concurrency <= 0 or args.timeout <= 0:
        parser.error("rate, duration, concurrency, and timeout must be positive")
    if args.output.resolve() in {
        args.journey_ledger.resolve(), journey_plan_path(args.journey_ledger).resolve(),
    }:
        parser.error("--output must differ from both journey evidence paths")
    previous_handlers = {
        signum: signal.signal(signum, _signal_interrupt)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        result = run(
            args.base_url,
            args.rate,
            args.duration,
            args.concurrency,
            args.timeout,
            args.journey_ledger,
            args.start_at_epoch,
            args.barrier_id,
            args.journey_kind,
        )
    except (FileExistsError, ValueError) as exc:
        parser.error(str(exc))
    except (KeyboardInterrupt, WorkloadInterrupted):
        return 130
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in (
        "offered", "completed", "failed", "requests", "latencyMs",
    )}, indent=2))
    return 0 if result["failed"] == 0 and result["timedOut"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
