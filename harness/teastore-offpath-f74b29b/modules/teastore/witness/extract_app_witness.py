#!/usr/bin/env python3
"""Extract an exact, Kieker-independent TeaStore application-path witness.

The extractor is intentionally fail closed.  It emits one consolidated JSONL
row only when auth and persistence each emitted exactly one fixed-schema row
for a pre-allocated workload token.  Fault-exposure and recovery journeys may
have no pair; every scored no-fault/before/after opportunity must have a pair.

Strictness is keyed on whether the journey is scored, which the preregistered
phase partition fixes before the run.  A thawed service replays the requests it
could not serve, so an unscored exposure journey may log one observation per
retry, or log its pair after the client already gave up (F-ADH-077).  Those rows
are counted and excluded; on a scored journey either shape still blocks.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn


BASE_COMMIT = "34b37f7e7be433ce72d5f9455e66922a13116749"
MARKER = "OBSERVABILITY_APP_WITNESS "
OBSERVATION_SCHEMA = "teastore.app-witness-observation"
OUTPUT_SCHEMA = "teastore.app-witness"
TOKEN = re.compile(r"journey-[0-9a-f]{32}\Z")
SERVICES = {
    "auth": "login-persistence-request",
    "persistence": "login-user-lookup",
}
OBSERVATION_KEYS = {
    "schema", "schemaVersion", "observedAtUtc", "journeyId", "service", "event",
}
SECRET_KEYS = {
    "authorization", "cookie", "credential", "password", "requestbody", "session", "sid",
}

_SECRET_SCAN_PATH = Path(__file__).parents[1] / "validation" / "secret_scan.py"
_SECRET_SCAN_SPEC = importlib.util.spec_from_file_location(
    "teastore_secret_scan_for_app_witness", _SECRET_SCAN_PATH)
if _SECRET_SCAN_SPEC is None or _SECRET_SCAN_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot load TeaStore secret scanner: {_SECRET_SCAN_PATH}")
_SECRET_SCAN = importlib.util.module_from_spec(_SECRET_SCAN_SPEC)
_SECRET_SCAN_SPEC.loader.exec_module(_SECRET_SCAN)

_FIXED_LOAD_PATH = Path(__file__).parents[1] / "workload/fixed_load.py"
_FIXED_LOAD_SPEC = importlib.util.spec_from_file_location(
    "teastore_fixed_load_for_app_witness", _FIXED_LOAD_PATH)
if _FIXED_LOAD_SPEC is None or _FIXED_LOAD_SPEC.loader is None:  # pragma: no cover - install defect
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


class WitnessError(ValueError):
    """The application witness cannot support an executed-path claim."""


def _reject_constant(value: str) -> NoReturn:
    raise WitnessError(f"non-finite JSON value is forbidden: {value}")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WitnessError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(value: str) -> Any:
    try:
        return json.loads(
            value,
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except WitnessError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise WitnessError(f"malformed JSON: {exc}") from exc


def _iso(value: Any) -> datetime:
    if not isinstance(value, str):
        raise WitnessError("timestamp is not a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WitnessError(f"invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WitnessError("timestamp has no UTC offset")
    return parsed


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return _json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WitnessError(f"cannot read {path}: {exc}") from exc


def _read_ledger(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any], Path]:
    if path.suffix != ".jsonl":
        raise WitnessError("journey ledger must be the hash-chained JSONL artifact")
    plan_path = _FIXED_LOAD.journey_plan_path(path)
    try:
        validation = _FIXED_LOAD.validate_journey_ledger(plan_path, path)
    except ValueError as exc:
        raise WitnessError(f"journey ledger validation failed: {exc}") from exc
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WitnessError(f"cannot read journey ledger: {exc}") from exc
    stripped = text.lstrip()
    if not stripped:
        raise WitnessError("journey ledger is empty")
    records = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            raise WitnessError(f"journey ledger line {line_number} is empty")
        row = _json(line)
        if not isinstance(row, dict):
            raise WitnessError(f"journey ledger line {line_number} is not an object")
        records.append(row)
    rows = [row for row in records if row.get("recordType") == "journey-terminal"]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise WitnessError("journey ledger has no terminal journey rows")
    return rows, validation, plan_path


def _journey_fields(row: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "journeyId": row.get("journeyId"),
        "opportunityId": row.get("opportunityId"),
        "opaqueToken": row.get("opaqueToken"),
        "startedAt": row.get("startedAt", row.get("startedAtUtc")),
        "endedAt": row.get("endedAt", row.get("endedAtUtc")),
        "actualStartMonotonic": row.get("actualStartMonotonic"),
        "actualEndMonotonic": row.get("actualEndMonotonic"),
        "outcome": row.get("outcome"),
    }
    if not all(isinstance(normalized[key], str) and normalized[key]
               for key in ("journeyId", "opportunityId", "opaqueToken", "startedAt", "endedAt")):
        raise WitnessError("journey identity or wall-clock bounds are absent")
    if TOKEN.fullmatch(normalized["opaqueToken"]) is None:
        raise WitnessError(f"journey has invalid opaque token: {normalized['journeyId']}")
    if _iso(normalized["startedAt"]) > _iso(normalized["endedAt"]):
        raise WitnessError(f"journey ends before it starts: {normalized['journeyId']}")
    return normalized


def _phase(journey: dict[str, Any], regime: str, intervention: Any) -> str:
    if regime == "no-fault-cost":
        return "measurement"
    if not isinstance(intervention, dict):
        raise WitnessError("effect receipt has no intervention ground truth")
    start = journey.get("actualStartMonotonic")
    end = journey.get("actualEndMonotonic")
    if any(not isinstance(value, (int, float)) or isinstance(value, bool)
           or not math.isfinite(value) for value in (start, end)):
        raise WitnessError("effect journey has no finite monotonic bounds")
    try:
        onset = float(intervention["actualOnsetMonotonicOffsetSeconds"])
        offset = float(intervention["actualOffsetMonotonicOffsetSeconds"])
        readiness = float(
            intervention["readiness"]["observedAtMonotonicOffsetSeconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise WitnessError("effect intervention monotonic bounds are invalid") from exc
    if not (math.isfinite(onset) and math.isfinite(offset) and math.isfinite(readiness)
            and onset < offset <= readiness):
        raise WitnessError("effect intervention monotonic bounds are unordered")
    # F-ADH-079: a 150 s outage is long enough for a multi-request journey that
    # started just before onset to have its later requests execute inside the
    # freeze and fail. Classifying by start alone labelled such a journey a
    # clean "before" baseline and then blocked the cell for its failure. A
    # journey is baseline evidence only if it ENDED before onset; anything
    # overlapping the outage window is exposure evidence and is not scored.
    if end <= onset:
        return "before"
    if start >= readiness:
        return "after"
    if start < offset:
        return "during"
    return "recovery"


def _read_observations(path: Path, expected_service: str) -> list[dict[str, Any]]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WitnessError(f"missing {expected_service} service log: {exc}") from exc
    # JVM stack-frame source locations are not assignments in the traffic sweep only (secret_scan.JVM_SOURCE_KEY).
    if _SECRET_SCAN.contains_secret_text(raw_text, jvm_source_locations=SWEEP_EPOCH_ACTIVE):
        raise WitnessError(f"{expected_service} log contains secret-bearing raw text")
    lines = raw_text.splitlines()
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if MARKER not in line:
            continue
        payload = line.split(MARKER, 1)[1]
        row = _json(payload)
        if not isinstance(row, dict):
            raise WitnessError(f"{expected_service} log line {line_number} is not an object")
        lowered_keys = {str(key).replace("_", "").replace("-", "").casefold() for key in row}
        disclosed = sorted(lowered_keys & SECRET_KEYS)
        if disclosed:
            raise WitnessError(
                f"{expected_service} log line {line_number} has secret-bearing fields: {disclosed}")
        if set(row) != OBSERVATION_KEYS:
            raise WitnessError(f"{expected_service} log line {line_number} has non-contract fields")
        if (row.get("schema") != OBSERVATION_SCHEMA or row.get("schemaVersion") != 1
                or row.get("service") != expected_service
                or row.get("event") != SERVICES[expected_service]):
            raise WitnessError(f"{expected_service} log line {line_number} violates the event contract")
        token = row.get("journeyId")
        if not isinstance(token, str) or TOKEN.fullmatch(token) is None:
            raise WitnessError(f"{expected_service} log line {line_number} has an invalid token")
        _iso(row.get("observedAtUtc"))
        rows.append(row)
    return rows


def _atomic_write(path: Path, payload: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".tmp", delete=False) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.link(temporary_name, path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def extract(
    *,
    auth_log: Path,
    persistence_log: Path,
    journey_ledger: Path,
    run_receipt: Path,
    output: Path,
    extraction_receipt: Path,
) -> dict[str, Any]:
    """Reconcile logs to the frozen scored population and write terminal artifacts."""
    if output == extraction_receipt:
        raise WitnessError("witness output and extraction receipt must be different files")
    if output.exists() or extraction_receipt.exists():
        raise FileExistsError("refusing to overwrite an existing witness artifact")
    receipt = _read_json(run_receipt)
    if not isinstance(receipt, dict):
        raise WitnessError("run receipt is not an object")
    run = receipt.get("run")
    window = receipt.get("window")
    if not isinstance(run, dict) or not isinstance(window, dict):
        raise WitnessError("run receipt lacks run/window objects")
    regime = run.get("regime")
    if regime != "no-fault-cost" and regime not in EFFECT_REGIMES:
        raise WitnessError("run receipt has an unknown regime")
    try:
        window_start = _iso(window["measurementStartedAt"])
        window_end = _iso(window["measurementEndedAt"])
    except KeyError as exc:
        raise WitnessError("run receipt lacks measurement wall-clock bounds") from exc
    if window_start >= window_end:
        raise WitnessError("measurement wall-clock bounds are unordered")

    ledger_rows, ledger_validation, journey_plan = _read_ledger(journey_ledger)
    journeys = [_journey_fields(row) for row in ledger_rows]
    identities = {
        "journeyId": [row["journeyId"] for row in journeys],
        "opportunityId": [row["opportunityId"] for row in journeys],
        "opaqueToken": [row["opaqueToken"] for row in journeys],
    }
    for name, values in identities.items():
        if len(set(values)) != len(values):
            raise WitnessError(f"duplicate {name} in journey ledger")
    for row in journeys:
        if not (window_start <= _iso(row["startedAt"]) <= _iso(row["endedAt"]) <= window_end):
            raise WitnessError(f"journey is outside measurement window: {row['journeyId']}")
        row["phase"] = _phase(row, regime, receipt.get("intervention"))

    observations = (
        _read_observations(auth_log, "auth")
        + _read_observations(persistence_log, "persistence")
    )
    expected_tokens = {row["opaqueToken"] for row in journeys}
    by_token_service: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"auth": [], "persistence": []})
    for row in observations:
        observed = _iso(row["observedAtUtc"])
        if not (window_start <= observed <= window_end):
            raise WitnessError(f"out-of-window witness row: {row['journeyId']}")
        token = row["journeyId"]
        if token not in expected_tokens:
            raise WitnessError(f"witness token is absent from journey ledger: {token}")
        by_token_service[token][row["service"]].append(row)

    # Traffic sweep, Q3: a fault-cell journey that started inside the post-readiness drain allowance and failed is
    # not scored (and so needs no witness); frozen and no-fault receipts carry no allowance.
    allowance = _STUDY_EPOCH.drain_allowance(receipt) if SWEEP_EPOCH_ACTIVE else None
    intervention = receipt.get("intervention")
    readiness = (
        intervention.get("readiness", {}).get("observedAtMonotonicOffsetSeconds")
        if allowance is not None and isinstance(intervention, dict) else None)
    output_rows: list[dict[str, Any]] = []
    required_count = 0
    partial_optional_count = 0
    unscored_excluded_rows = 0
    phase_counts: dict[str, int] = defaultdict(int)
    for journey in journeys:
        phase = journey["phase"]
        phase_counts[phase] += 1
        required = regime == "no-fault-cost" or phase in {"before", "after"}
        if required and phase == "after" and _STUDY_EPOCH.drain_excused(
                journey["actualStartMonotonic"], readiness, journey["outcome"], allowance):
            required = False
        required_count += int(required)
        grouped = by_token_service[journey["opaqueToken"]]
        auth = grouped["auth"]
        persistence = grouped["persistence"]
        if len(auth) > 1 or len(persistence) > 1:
            if required:
                raise WitnessError(
                    f"duplicate token/service observation: {journey['opaqueToken']}")
            # F-ADH-077: a frozen service replays its queued requests after
            # thaw. A journey the client already abandoned can therefore log one
            # observation per retry, all carrying the same pre-allocated token.
            # That is the fault's own signature, and the phase partition that
            # makes this journey unscored was fixed before the run, so exclude
            # its rows from the witness instead of aborting the cell. Scored
            # phases (no-fault, before, after) stay zero-tolerance.
            unscored_excluded_rows += len(auth) + len(persistence)
            continue
        if bool(auth) != bool(persistence):
            if required:
                raise WitnessError(f"incomplete auth->persistence path: {journey['opaqueToken']}")
            # A positive observation of only one service during exposure/recovery
            # is diagnostic. Absence of the other service is not proof of a
            # negative path, so do not emit or guess a witness row.
            partial_optional_count += 1
            continue
        if required and not auth:
            missing = "auth,persistence"
            raise WitnessError(
                f"missing service observations ({missing}) for scored opportunity: "
                f"{journey['opportunityId']}")
        if not auth:
            continue
        auth_time = _iso(auth[0]["observedAtUtc"])
        persistence_time = _iso(persistence[0]["observedAtUtc"])
        journey_start = _iso(journey["startedAt"])
        journey_end = _iso(journey["endedAt"])
        if not (journey_start <= auth_time <= persistence_time <= journey_end):
            if required:
                raise WitnessError(
                    f"witness pair is outside or reversed for {journey['opaqueToken']}")
            # Same F-ADH-077 mechanism seen from the other side: the replayed
            # execution lands after the client-side journey already ended.
            unscored_excluded_rows += len(auth) + len(persistence)
            continue
        output_rows.append({
            "schema": OUTPUT_SCHEMA,
            "schemaVersion": 1,
            "journeyId": journey["journeyId"],
            "opportunityId": journey["opportunityId"],
            "opaqueToken": journey["opaqueToken"],
            "source": "application-side",
            "independentOfKieker": True,
            "observedAt": persistence[0]["observedAtUtc"],
            "authObservedAtUtc": auth[0]["observedAtUtc"],
            "persistenceObservedAtUtc": persistence[0]["observedAtUtc"],
            "authTraversed": True,
            "persistenceTraversed": True,
            "executedPath": ["auth", "persistence"],
        })
    if required_count == 0:
        raise WitnessError("run has no scored witness opportunities")

    output_bytes = b"".join(
        (json.dumps(row, allow_nan=False, separators=(",", ":"), sort_keys=True) + "\n").encode()
        for row in output_rows
    )
    output_sha256 = hashlib.sha256(output_bytes).hexdigest()
    terminal = {
        "schema": "teastore.app-witness-extraction-receipt",
        "schemaVersion": 1,
        "status": "complete",
        "sourceCommit": BASE_COMMIT,
        "regime": regime,
        "measurementWindow": {
            "startedAt": window["measurementStartedAt"],
            "endedAt": window["measurementEndedAt"],
        },
        "counts": {
            "ledgerOpportunities": len(journeys),
            "requiredScoredOpportunities": required_count,
            "completeWitnessPaths": len(output_rows),
            "partialOptionalObservations": partial_optional_count,
            "unscoredExcludedObservations": unscored_excluded_rows,
            "authObservations": sum(row["service"] == "auth" for row in observations),
            "persistenceObservations": sum(
                row["service"] == "persistence" for row in observations),
            "phases": dict(sorted(phase_counts.items())),
        },
        "inputs": {
            "authLogSha256": _sha256(auth_log),
            "persistenceLogSha256": _sha256(persistence_log),
            "journeyLedgerSha256": _sha256(journey_ledger),
            "journeyPlanSha256": _sha256(journey_plan),
        },
        "journeyLedgerValidation": {
            "verdict": ledger_validation["verdict"],
            "planSha256": ledger_validation["planSha256"],
            "lastRecordSha256": ledger_validation["lastRecordSha256"],
            "terminalJourneys": ledger_validation["terminalJourneys"],
            "state": ledger_validation["state"],
        },
        "appWitnessSha256": output_sha256,
    }
    receipt_bytes = (
        json.dumps(terminal, allow_nan=False, indent=2, sort_keys=True) + "\n").encode()
    _atomic_write(output, output_bytes)
    _atomic_write(extraction_receipt, receipt_bytes)
    return terminal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auth-log", type=Path, required=True)
    parser.add_argument("--persistence-log", type=Path, required=True)
    parser.add_argument("--journey-ledger", type=Path, required=True)
    parser.add_argument("--run-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--extraction-receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        terminal = extract(**vars(args))
    except (WitnessError, FileExistsError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(terminal, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
