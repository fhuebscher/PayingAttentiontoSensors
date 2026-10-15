#!/usr/bin/env python3
"""Preallocate and execute the Hotel candidate's hash-chained request ledger."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import re
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, NoReturn


WORKLOAD_ID = "hotel-search-v1"
PLAN_CONTRACT = "hotel-candidate-opportunity-plan-v1"
LEDGER_CONTRACT = "hotel-candidate-opportunity-ledger-v1"
TOKEN_HEADER = "X-Obsplacement-Opportunity"
TOKEN = re.compile(r"^hr-[0-9a-f]{32}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
# 2026-09-22: widened from b0[1-4] and (full|sample-zero) to the three-posture,
# six-block shape (3 regimes x 6 blocks x 3 postures = 54 cells). This was the
# second site freezing the old 24-cell shape as a literal; the first was
# candidate_terminal.py's `len(contracts) != 24`. Hotel #6 reached its third cell
# with `full` and `sample-zero` valid -- their run IDs are unchanged by the
# reshape -- then stopped on `no-fault-cost-b01-none-a01` with "run ID is not one
# of the frozen 24 candidate cells", because only the novel rung's IDs are new.
RUN_ID = re.compile(
    r"^(no-fault-cost|search-pause-effect|reservation-pause-effect|cpu-throttle-effect|net-delay-effect)-"
    r"b0[1-4]-(none|metrics|selected|full)-a01$"
)
# 2026-10-03, hotel-traffic-sweep-v1: rate, duration and offered are per-cell plan values.  The shape is
# deliberately generic in regime, rate, block and posture (a frozen membership set here is the class of guard
# that stopped Hotel #6); membership is proven where it can be, by the cell runner and the terminal validator
# comparing the cell contract byte-for-byte with the admitted compiled plan.  The run ID carries the rate it
# was compiled for, so the plan replay below can refuse any other rate.
SWEEP_RUN_ID = re.compile(
    r"^[a-z]+(?:-[a-z]+)*-r(?P<rate>[0-9]+(?:p[0-9]+)?)-b[0-9]{2}-[a-z]+(?:-[a-z]+)*-a01$"
)
SWEEP_MAXIMUM_DURATION_SECONDS = 3600.0
PLAN_KEYS = {
    "schemaVersion", "contract", "workloadId", "runId", "compiledPlanSha256",
    "createdAt", "barrierId", "barrierAt", "barrierMonotonic", "rate",
    "durationSeconds", "offered", "opportunities", "planCanonicalSha256",
}
OPPORTUNITY_KEYS = {
    "sequence", "opportunityId", "opaqueToken", "scheduledAt",
    "scheduledMonotonicOffsetSeconds",
}
LEDGER_KEYS = {
    "schemaVersion", "contract", "recordSequence", "previousRecordSha256",
    "recordSha256", "planSha256", "workloadId", "barrierId", "sequence",
    "opportunityId", "opaqueToken", "scheduledAt",
    "scheduledMonotonicOffsetSeconds", "actualStartMonotonic",
    "actualEndMonotonic", "startedAt", "endedAt", "outcome", "statusCode",
    "error", "terminalSettled",
}


class LedgerError(ValueError):
    """The opportunity plan or terminal ledger is not exact and replayable."""


def _reject_constant(value: str) -> NoReturn:
    raise LedgerError(f"non-finite JSON value is forbidden: {value}")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise LedgerError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json(value: str, where: str) -> Any:
    try:
        return json.loads(
            value, object_pairs_hook=_pairs, parse_constant=_reject_constant,
        )
    except LedgerError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LedgerError(f"invalid JSON in {where}: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, allow_nan=False, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise LedgerError(f"value is not canonical JSON: {exc}") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise LedgerError("timestamps must be timezone aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: Any, where: str) -> datetime:
    if not isinstance(value, str):
        raise LedgerError(f"{where} must be an ISO-8601 string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise LedgerError(f"{where} is not an ISO-8601 timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise LedgerError(f"{where} must include an offset")
    return result.astimezone(timezone.utc)


def _number(value: Any) -> bool:
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def search_url(base_url: str, sequence: int) -> str:
    in_day = 9 + sequence % 10
    out_day = in_day + 1
    latitude = 38.0235 + ((sequence % 21) - 10) / 1000
    longitude = -122.095 + ((sequence % 17) - 8) / 1000
    query = urllib.parse.urlencode({
        "inDate": f"2015-04-{in_day:02d}",
        "outDate": f"2015-04-{out_day:02d}",
        "lat": f"{latitude:.4f}",
        "lon": f"{longitude:.4f}",
        "locale": "en",
    })
    return base_url.rstrip("/") + "/hotels?" + query


def build_plan(
    run_id: str,
    compiled_plan_sha256: str,
    barrier_at: datetime,
    barrier_monotonic: float,
    *,
    rate: float = 10.0,
    duration_seconds: float = 120.0,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    sweep = SWEEP_RUN_ID.fullmatch(str(run_id)) if RUN_ID.fullmatch(str(run_id)) is None else None
    if RUN_ID.fullmatch(str(run_id)) is None and sweep is None:
        raise LedgerError("run ID is not one of the frozen 80 selected-v1 cells or a traffic-sweep cell")
    if SHA256.fullmatch(str(compiled_plan_sha256)) is None:
        raise LedgerError("compiled plan SHA-256 is invalid")
    if sweep is None:
        if not _number(rate) or float(rate) != 10.0:
            raise LedgerError("candidate request rate must be exactly 10/s")
        if not _number(duration_seconds) or float(duration_seconds) != 120.0:
            raise LedgerError("candidate measurement duration must be exactly 120s")
    else:
        if not _number(rate) or float(rate) != float(sweep.group("rate").replace("p", ".")):
            raise LedgerError("traffic-sweep request rate differs from the rate its run ID was compiled for")
        if (
            not _number(duration_seconds)
            or not 0 < float(duration_seconds) <= SWEEP_MAXIMUM_DURATION_SECONDS
        ):
            raise LedgerError("traffic-sweep measurement duration must be finite and in (0, 3600] s")
    if not _number(barrier_monotonic) or float(barrier_monotonic) <= 0:
        raise LedgerError("barrier monotonic value must be finite and positive")
    created = created_at or datetime.now(timezone.utc)
    # Reject naive input before astimezone() can interpret it through the
    # ambient host timezone and make replay host-dependent.
    iso(created)
    barrier = parse_iso(iso(barrier_at), "barrierAt")
    if created.astimezone(timezone.utc) > barrier:
        raise LedgerError("opportunity plan must be allocated before the barrier")
    offered = int(round(float(rate) * float(duration_seconds)))
    if sweep is None and offered != 1200:
        raise LedgerError("candidate cell must preallocate exactly 1,200 opportunities")
    if sweep is not None and (
        offered < 1 or abs(float(rate) * float(duration_seconds) - offered) > 1e-9
    ):
        raise LedgerError("traffic-sweep rate x duration must be a positive integer number of opportunities")
    barrier_id = "barrier-" + hashlib.sha256(
        f"{compiled_plan_sha256}\0{run_id}\0{iso(barrier)}".encode("utf-8")
    ).hexdigest()[:24]
    opportunities = []
    for sequence in range(offered):
        offset = sequence / float(rate)
        token = "hr-" + hashlib.sha256(
            f"{compiled_plan_sha256}\0{run_id}\0{sequence}".encode("utf-8")
        ).hexdigest()[:32]
        opportunities.append({
            "sequence": sequence,
            "opportunityId": f"{WORKLOAD_ID}:{run_id}:{sequence:06d}",
            "opaqueToken": token,
            "scheduledAt": iso(barrier + timedelta(seconds=offset)),
            "scheduledMonotonicOffsetSeconds": offset,
        })
    body = {
        "schemaVersion": 1,
        "contract": PLAN_CONTRACT,
        "workloadId": WORKLOAD_ID,
        "runId": run_id,
        "compiledPlanSha256": compiled_plan_sha256,
        "createdAt": iso(created),
        "barrierId": barrier_id,
        "barrierAt": iso(barrier),
        "barrierMonotonic": float(barrier_monotonic),
        "rate": float(rate),
        "durationSeconds": float(duration_seconds),
        "offered": offered,
        "opportunities": opportunities,
    }
    return {**body, "planCanonicalSha256": canonical_sha256(body)}


def validate_plan(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != PLAN_KEYS:
        raise LedgerError("opportunity plan fields differ")
    if document.get("schemaVersion") != 1 or document.get("contract") != PLAN_CONTRACT:
        raise LedgerError("opportunity plan schema or contract differs")
    body = {key: value for key, value in document.items() if key != "planCanonicalSha256"}
    if document.get("planCanonicalSha256") != canonical_sha256(body):
        raise LedgerError("opportunity plan self digest differs")
    expected = build_plan(
        document.get("runId"), document.get("compiledPlanSha256"),
        parse_iso(document.get("barrierAt"), "barrierAt"),
        document.get("barrierMonotonic"), rate=document.get("rate"),
        duration_seconds=document.get("durationSeconds"),
        created_at=parse_iso(document.get("createdAt"), "createdAt"),
    )
    if canonical_bytes(expected) != canonical_bytes(document):
        raise LedgerError("opportunity plan differs from deterministic replay")
    opportunities = document.get("opportunities")
    if (
        not isinstance(opportunities, list)
        or len(opportunities) != document.get("offered")
        or any(not isinstance(row, dict) or set(row) != OPPORTUNITY_KEYS for row in opportunities)
    ):
        raise LedgerError("opportunity set is incomplete or malformed")
    tokens = [row["opaqueToken"] for row in opportunities]
    if any(TOKEN.fullmatch(str(value)) is None for value in tokens) or len(tokens) != len(set(tokens)):
        raise LedgerError("opportunity tokens are invalid or duplicated")
    return document


def write_plan(path: Path, plan: dict[str, Any]) -> None:
    validate_plan(plan)
    payload = json.dumps(plan, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise LedgerError(f"refusing to replace opportunity plan: {path}") from exc
    try:
        if os.write(descriptor, payload) != len(payload):
            raise LedgerError("short write to opportunity plan")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _request(base_url: str, opportunity: dict[str, Any], timeout: float) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    request = urllib.request.Request(
        search_url(base_url, opportunity["sequence"]),
        headers={TOKEN_HEADER: opportunity["opaqueToken"]},
        method="GET",
    )
    try:
        with urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        ).open(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
        error = None if status == 200 and body else "empty-or-non-200-response"
        outcome = "completed" if error is None else "application-failure"
    except (OSError, urllib.error.HTTPError) as exc:
        status = getattr(exc, "code", None)
        error = f"{type(exc).__name__}: {exc}"
        outcome = "transport-error"
    return {
        **opportunity,
        "actualStartMonotonic": started,
        "actualEndMonotonic": time.monotonic(),
        "startedAt": iso(started_at),
        "endedAt": iso(datetime.now(timezone.utc)),
        "outcome": outcome,
        "statusCode": status,
        "error": error,
        "terminalSettled": True,
        "scheduledMonotonicOffsetSeconds": opportunity["scheduledMonotonicOffsetSeconds"],
    }


def _ledger_record(
    result: dict[str, Any], sequence: int, previous: str, plan: dict[str, Any]
) -> dict[str, Any]:
    record = {
        "schemaVersion": 1,
        "contract": LEDGER_CONTRACT,
        "recordSequence": sequence,
        "previousRecordSha256": previous,
        "recordSha256": None,
        "planSha256": plan["planCanonicalSha256"],
        "workloadId": WORKLOAD_ID,
        "barrierId": plan["barrierId"],
        "sequence": result["sequence"],
        "opportunityId": result["opportunityId"],
        "opaqueToken": result["opaqueToken"],
        "scheduledAt": result["scheduledAt"],
        "scheduledMonotonicOffsetSeconds": result["scheduledMonotonicOffsetSeconds"],
        "actualStartMonotonic": result["actualStartMonotonic"],
        "actualEndMonotonic": result["actualEndMonotonic"],
        "startedAt": result["startedAt"],
        "endedAt": result["endedAt"],
        "outcome": result["outcome"],
        "statusCode": result["statusCode"],
        "error": result["error"],
        "terminalSettled": result["terminalSettled"],
    }
    unsigned = {key: value for key, value in record.items() if key != "recordSha256"}
    record["recordSha256"] = canonical_sha256(unsigned)
    return record


def execute_plan(
    plan: dict[str, Any], base_url: str, ledger_path: Path, *, concurrency: int = 16,
    timeout: float = 15.0, clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    validate_plan(plan)
    if type(concurrency) is not int or not 1 <= concurrency <= 128:
        raise LedgerError("concurrency must be an integer from 1 through 128")
    if not _number(timeout) or not 0 < float(timeout) <= 120:
        raise LedgerError("request timeout must be finite and in (0, 120]")
    if ledger_path.exists() or ledger_path.is_symlink():
        raise LedgerError(f"refusing to replace opportunity ledger: {ledger_path}")
    delay = float(plan["barrierMonotonic"]) - float(clock())
    if delay < -0.050:
        raise LedgerError("opportunity barrier passed before workload launch")
    if delay > 0:
        time.sleep(delay)
    started = time.monotonic()
    futures: dict[int, concurrent.futures.Future] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        for opportunity in plan["opportunities"]:
            due = started + float(opportunity["scheduledMonotonicOffsetSeconds"])
            wait = due - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            futures[opportunity["sequence"]] = pool.submit(
                _request, base_url, opportunity, float(timeout)
            )
        results = [futures[index].result() for index in range(plan["offered"])]

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(ledger_path, flags, 0o600)
    try:
        previous = "0" * 64
        records = []
        for sequence, result in enumerate(results):
            record = _ledger_record(result, sequence, previous, plan)
            payload = canonical_bytes(record) + b"\n"
            if os.write(descriptor, payload) != len(payload):
                raise LedgerError("short append to opportunity ledger")
            previous = record["recordSha256"]
            records.append(record)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    replay = validate_ledger(plan, ledger_path)
    return {
        "schemaVersion": 1,
        "kind": "hotel-candidate-workload-reconciliation-v1",
        "planSha256": plan["planCanonicalSha256"],
        "ledgerSha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
        "offered": len(records),
        "terminalSettled": len(records),
        "completed": sum(row["outcome"] == "completed" for row in records),
        "failed": sum(row["outcome"] != "completed" for row in records),
        "firstRecordSha256": records[0]["recordSha256"],
        "lastRecordSha256": records[-1]["recordSha256"],
        "validation": replay,
    }


def validate_ledger(plan: dict[str, Any], ledger_path: Path) -> dict[str, Any]:
    validate_plan(plan)
    try:
        metadata = ledger_path.lstat()
        if ledger_path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise LedgerError("opportunity ledger is not a regular non-symlink file")
        payload = ledger_path.read_bytes()
        text = payload.decode("utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise LedgerError(f"cannot read opportunity ledger: {exc}") from exc
    if not payload or not payload.endswith(b"\n") or any(not line for line in text.splitlines()):
        raise LedgerError("opportunity ledger is empty, truncated, or contains gaps")
    rows = [strict_json(line, f"ledger line {index + 1}") for index, line in enumerate(text.splitlines())]
    if len(rows) != plan["offered"]:
        raise LedgerError("opportunity ledger row count differs from offered denominator")
    previous = "0" * 64
    for index, (opportunity, row) in enumerate(zip(plan["opportunities"], rows)):
        if not isinstance(row, dict) or set(row) != LEDGER_KEYS:
            raise LedgerError(f"ledger row {index} fields differ")
        unsigned = {key: value for key, value in row.items() if key != "recordSha256"}
        expected = {
            key: opportunity[key]
            for key in OPPORTUNITY_KEYS
        }
        if (
            row["schemaVersion"] != 1
            or row["contract"] != LEDGER_CONTRACT
            or row["recordSequence"] != index
            or row["sequence"] != index
            or row["previousRecordSha256"] != previous
            or row["recordSha256"] != canonical_sha256(unsigned)
            or row["planSha256"] != plan["planCanonicalSha256"]
            or row["workloadId"] != WORKLOAD_ID
            or row["barrierId"] != plan["barrierId"]
            or any(row[key] != value for key, value in expected.items())
            or row["terminalSettled"] is not True
            or row["outcome"] not in {"completed", "application-failure", "transport-error"}
            or (
                row["outcome"] == "completed"
                and (row["statusCode"] != 200 or row["error"] is not None)
            )
            or (
                row["outcome"] != "completed"
                and (not isinstance(row["error"], str) or not row["error"])
            )
            or (
                row["statusCode"] is not None
                and (
                    type(row["statusCode"]) is not int
                    or not 100 <= row["statusCode"] <= 599
                )
            )
            or not _number(row["actualStartMonotonic"])
            or not _number(row["actualEndMonotonic"])
            or row["actualStartMonotonic"] < (
                float(plan["barrierMonotonic"])
                + float(opportunity["scheduledMonotonicOffsetSeconds"]) - 0.050
            )
            or row["actualEndMonotonic"] < row["actualStartMonotonic"]
        ):
            raise LedgerError(f"ledger row {index} identity, chain, or terminal state differs")
        parse_iso(row["startedAt"], f"ledger row {index} startedAt")
        parse_iso(row["endedAt"], f"ledger row {index} endedAt")
        previous = row["recordSha256"]
    return {
        "schemaVersion": 1,
        "kind": "hotel-candidate-opportunity-validation-v1",
        "verdict": "pass",
        "offered": len(rows),
        "terminalSettled": len(rows),
        "terminalOpportunityIdsSha256": canonical_sha256(
            sorted(row["opportunityId"] for row in rows)
        ),
        "terminalOpaqueTokensSha256": canonical_sha256(
            sorted(row["opaqueToken"] for row in rows)
        ),
        "lastRecordSha256": previous,
    }


def _load_plan(path: Path) -> dict[str, Any]:
    return validate_plan(strict_json(path.read_text(encoding="utf-8"), str(path)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--compiled-plan-sha256", required=True)
    prepare.add_argument("--barrier-at", required=True)
    prepare.add_argument("--barrier-monotonic", required=True, type=float)
    prepare.add_argument("--output", required=True, type=Path)
    run = commands.add_parser("run")
    run.add_argument("--plan", required=True, type=Path)
    run.add_argument("--base-url", required=True)
    run.add_argument("--ledger", required=True, type=Path)
    run.add_argument("--concurrency", type=int, default=16)
    run.add_argument("--timeout", type=float, default=15.0)
    check = commands.add_parser("validate")
    check.add_argument("--plan", required=True, type=Path)
    check.add_argument("--ledger", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            plan = build_plan(
                args.run_id, args.compiled_plan_sha256,
                parse_iso(args.barrier_at, "barrier-at"), args.barrier_monotonic,
            )
            write_plan(args.output, plan)
            result = {"planCanonicalSha256": plan["planCanonicalSha256"], "offered": plan["offered"]}
        elif args.command == "run":
            result = execute_plan(
                _load_plan(args.plan), args.base_url, args.ledger,
                concurrency=args.concurrency, timeout=args.timeout,
            )
        else:
            result = validate_ledger(_load_plan(args.plan), args.ledger)
    except LedgerError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
