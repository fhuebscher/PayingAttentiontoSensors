#!/usr/bin/env python3
"""Collect and replay Hotel candidate CPU and source-emitted span-byte evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, NoReturn


APPLICATION_SERVICES = (
    "frontend", "search", "geo", "rate", "reservation", "profile",
    "user", "recommendation", "review", "attractions",
)
# hotel-offpath-v1 only: the scope also holds the consul container (the off-path pause target), so its own CPU is
# measured beside the ten application containers.  `applicationCpuPercent` / `applicationCpuSeconds` stay the sum
# over the ten application containers (comparable with every other Hotel epoch); consul is a separate row.
EXTENDED_SERVICES = APPLICATION_SERVICES + ("consul",)
RESOURCE_CONTRACT = "hotel-candidate-scoped-resource-v1"
# `docker stats --no-stream` over the ten application containers returns one
# to two seconds after it is issued; the first admitted sample is issued this
# long before the barrier so that it lands inside validate_cpu's +2.0 s bound.
FIRST_SAMPLE_LEAD_SECONDS = 1.5
EMISSION_CONTRACT = "hotel-candidate-source-emission-v1"
EMISSION_PREFIX = "OBSPLACEMENT_EMISSION "
TRACE_ID = re.compile(r"^[0-9a-f]{16}(?:[0-9a-f]{16})?$")
SPAN_ID = re.compile(r"^[0-9a-f]{16}$")


class ResourceError(ValueError):
    """A scoped resource or emitted-byte artifact failed deterministic replay."""


def _reject_constant(value: str) -> NoReturn:
    raise ResourceError(f"non-finite JSON value is forbidden: {value}")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ResourceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json(value: str, where: str) -> Any:
    try:
        return json.loads(value, object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except ResourceError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ResourceError(f"invalid JSON in {where}: {exc}") from exc


def _number(value: Any, *, minimum: float | None = None) -> bool:
    valid = (
        isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(float(value))
    )
    return valid and (minimum is None or float(value) >= minimum)


def _close(left: Any, right: Any, tolerance: float = 1e-9) -> bool:
    return _number(left) and _number(right) and math.isclose(
        float(left), float(right), rel_tol=tolerance, abs_tol=tolerance,
    )


def _sequential_sum(values: "list[float]") -> float:
    """Left-to-right IEEE-754 double summation, pinned independently of the interpreter.

    The measurement hosts run CPython 3.9, whose builtin ``sum()`` over floats is a
    plain sequential accumulation.  CPython >= 3.12 (gh-100425) switched ``sum()`` to
    Neumaier compensated summation, which is more accurate but not bit-identical: an
    offline replay on a 3.12+ interpreter then differs from the host-written
    ``applicationCpuSeconds`` by one ulp and the bit-exact terminal gate rejects a
    valid cell (F-ADH-069 class; 33 of 103 banked Hotel cells were affected).  Both the
    collector and the validator must use this one function so the derived value is the
    same on every interpreter and equal to what the 3.9 hosts have always written.
    Do not replace with ``math.fsum``: exactly-rounded summation would change the
    value on both sides and invalidate every retained cell terminal digest.
    """
    total = 0.0
    for value in values:
        total += float(value)
    return total

def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, allow_nan=False, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def cpu_percent(value: Any) -> float:
    if not isinstance(value, str) or not value.endswith("%"):
        raise ResourceError("Docker CPU percentage must be a percent string")
    try:
        result = float(value[:-1])
    except ValueError as exc:
        raise ResourceError("Docker CPU percentage is malformed") from exc
    if not _number(result, minimum=0):
        raise ResourceError("Docker CPU percentage is not finite and non-negative")
    return result


def scope_of(services: Any) -> tuple:
    """The declared scope a set of service names is: the ten application services, or those plus consul."""
    names = set(services)
    for scope in (APPLICATION_SERVICES, EXTENDED_SERVICES):
        if names == set(scope):
            return scope
    raise ResourceError("container identity map must bind every application service once")


def _application_sum(rows: Any) -> float:
    """Sequential sum over the ten application containers' rows (a consul row is not application CPU)."""
    return _sequential_sum([row["cpuPercent"] for row in rows if row["service"] in APPLICATION_SERVICES])


def parse_stats(stdout: str, identities: dict[str, str]) -> list[dict[str, Any]]:
    if len(identities) != len(scope_of(identities.values())):
        raise ResourceError("container identity map must bind every application service once")
    rows = []
    seen: set[str] = set()
    for line_number, line in enumerate(stdout.splitlines(), start=1):
        if not line:
            continue
        document = strict_json(line, f"docker stats line {line_number}")
        if not isinstance(document, dict):
            raise ResourceError("Docker stats row is not an object")
        container = document.get("Container")
        if container not in identities or container in seen:
            raise ResourceError("Docker stats contains an unknown or duplicate container")
        seen.add(container)
        rows.append({
            "service": identities[container],
            "containerId": container,
            "cpuPercent": cpu_percent(document.get("CPUPerc")),
        })
    if seen != set(identities):
        raise ResourceError("Docker stats omitted an application container")
    return sorted(rows, key=lambda row: row["service"])


def docker_sample(
    identities: dict[str, str], *,
    run_command: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, Any]:
    command = [
        "docker", "stats", "--no-stream", "--format", "{{json .}}",
        *sorted(identities),
    ]
    result = run_command(command, text=True, capture_output=True, check=False, timeout=20)
    if result.returncode:
        raise ResourceError(f"Docker stats failed: {result.stderr.strip()}")
    rows = parse_stats(result.stdout, identities)
    return {
        "capturedAtEpoch": time.time(),
        "capturedAtMonotonic": time.monotonic(),
        "containers": rows,
        "applicationCpuPercent": _application_sum(rows),
    }


def collect_cpu(
    project: str,
    identities: dict[str, str],
    window_start_monotonic: float,
    window_end_monotonic: float,
    *, interval_seconds: float = 1.0,
    sample: Callable[[dict[str, str]], dict[str, Any]] = docker_sample,
) -> dict[str, Any]:
    if not re.fullmatch(r"hotel_candidate_v4_[0-9a-f]{8}_[0-9]{2}", project):
        raise ResourceError("project identity is outside the Hotel candidate namespace")
    if (
        not _number(window_start_monotonic, minimum=0)
        or not _number(window_end_monotonic, minimum=0)
        or float(window_end_monotonic) <= float(window_start_monotonic)
        or not _number(interval_seconds)
        or not 0.2 <= float(interval_seconds) <= 10.0
    ):
        raise ResourceError("resource window or interval is invalid")
    # The runner starts this collector before the shared barrier so the worker
    # is ready, but pre-barrier samples are not part of the admitted cost
    # window.  Waiting here also prevents an early sample from making every
    # otherwise valid cell fail terminal replay.
    # Prime the Docker stats path before the window: the first
    # `docker stats --no-stream` against freshly started containers blocks for
    # its two CPU readings (~2 s), which put the first admitted sample past the
    # validator's +2.0 s bound on the first real cell (2026-09-06); later calls
    # return in ~20 ms. This pre-barrier sample is deliberately not retained.
    if time.monotonic() < float(window_start_monotonic):
        sample(identities)
    # Each `docker stats --no-stream` call returns only after the daemon has
    # emitted a stats event for every container, i.e. one to two seconds after
    # it is issued under load (second real cell, 2026-09-06: still past the
    # +2.0 s bound with priming alone). Issue the first admitted call this long
    # before the barrier; the collector already admits samples from
    # start - 2.0 s and the replay integrates them from the window start only.
    wait_for_window = float(window_start_monotonic) - FIRST_SAMPLE_LEAD_SECONDS - time.monotonic()
    if wait_for_window > 0:
        time.sleep(wait_for_window)
    samples = []
    while time.monotonic() < float(window_end_monotonic):
        row = sample(identities)
        captured = row.get("capturedAtMonotonic")
        if not _number(captured) or captured < float(window_start_monotonic) - 2.0:
            raise ResourceError("resource sample timestamp is outside the bounded window")
        samples.append(row)
        wait = min(float(interval_seconds), float(window_end_monotonic) - time.monotonic())
        if wait > 0:
            time.sleep(wait)
    document = {
        "schemaVersion": 1,
        "contract": RESOURCE_CONTRACT,
        "project": project,
        "applicationServices": list(scope_of(identities.values())),
        "containerIdentities": dict(sorted(identities.items())),
        "windowStartMonotonic": float(window_start_monotonic),
        "windowEndMonotonic": float(window_end_monotonic),
        "intervalSeconds": float(interval_seconds),
        "samples": samples,
        "captureComplete": True,
    }
    replay = validate_cpu(document, scope_of(identities.values()))
    return {**document, "applicationCpuSeconds": replay["applicationCpuSeconds"]}


def validate_cpu(document: Any, scope: tuple = APPLICATION_SERVICES) -> dict[str, Any]:
    """Replay a CPU artifact against ``scope`` (the epoch's declared services; the ten application containers unless
    the epoch adds consul).  A document of another scope is refused, so a missing or an extra container fails."""
    if scope not in (APPLICATION_SERVICES, EXTENDED_SERVICES):
        raise ResourceError("resource scope is not a declared scope")
    keys = {
        "schemaVersion", "contract", "project", "applicationServices",
        "containerIdentities", "windowStartMonotonic", "windowEndMonotonic",
        "intervalSeconds", "samples", "captureComplete", "applicationCpuSeconds",
    }
    if not isinstance(document, dict) or set(document) != keys:
        # During collection the derived field is not installed yet.
        if not isinstance(document, dict) or set(document) != keys - {"applicationCpuSeconds"}:
            raise ResourceError("resource artifact fields differ")
    if document.get("schemaVersion") != 1 or document.get("contract") != RESOURCE_CONTRACT:
        raise ResourceError("resource artifact schema or contract differs")
    if document.get("applicationServices") != list(scope):
        raise ResourceError("resource scope differs from declared application services")
    identities = document.get("containerIdentities")
    if not isinstance(identities, dict) or set(identities.values()) != set(scope):
        raise ResourceError("resource container identities are incomplete")
    start = document.get("windowStartMonotonic")
    end = document.get("windowEndMonotonic")
    interval = document.get("intervalSeconds")
    samples = document.get("samples")
    if (
        not _number(start, minimum=0) or not _number(end, minimum=0)
        or end <= start or not _number(interval) or not 0.2 <= interval <= 10.0
        or not isinstance(samples, list) or len(samples) < 2
        or document.get("captureComplete") is not True
    ):
        raise ResourceError("resource capture is incomplete")
    previous = None
    total = 0.0
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict) or set(sample) != {
            "capturedAtEpoch", "capturedAtMonotonic", "containers",
            "applicationCpuPercent",
        }:
            raise ResourceError(f"resource sample {index} fields differ")
        captured = sample.get("capturedAtMonotonic")
        rows = sample.get("containers")
        if (
            not _number(sample.get("capturedAtEpoch"), minimum=0)
            or not _number(captured, minimum=0)
            or (previous is not None and captured <= previous)
            or not isinstance(rows, list) or len(rows) != len(scope)
        ):
            raise ResourceError(f"resource sample {index} is malformed or reordered")
        services = {row.get("service") for row in rows if isinstance(row, dict)}
        if services != set(scope) or any(
            set(row) != {"service", "containerId", "cpuPercent"}
            or identities.get(row["containerId"]) != row["service"]
            or not _number(row["cpuPercent"], minimum=0)
            for row in rows
        ):
            raise ResourceError(f"resource sample {index} escaped application scope")
        cpu = _application_sum(rows)
        if not _close(cpu, sample.get("applicationCpuPercent")):
            raise ResourceError(f"resource sample {index} CPU aggregate differs")
        upper = min(float(end), float(samples[index + 1]["capturedAtMonotonic"])) if index + 1 < len(samples) else float(end)
        lower = max(float(start), float(captured))
        if upper > lower:
            total += cpu / 100.0 * (upper - lower)
        previous = float(captured)
    if float(samples[0]["capturedAtMonotonic"]) > float(start) + 2.0:
        raise ResourceError(
            "resource capture starts too late: first sample at "
            f"{float(samples[0]['capturedAtMonotonic']) - float(start):+.3f} s from the window start"
        )
    if float(samples[-1]["capturedAtMonotonic"]) < float(end) - max(2.0, 2 * float(interval)):
        raise ResourceError("resource capture ends too early")
    if "applicationCpuSeconds" in document and not _close(document["applicationCpuSeconds"], total, 1e-7):
        raise ResourceError("resource CPU-seconds result differs from sample replay")
    return {
        "schemaVersion": 1,
        "kind": "hotel-candidate-resource-validation-v1",
        "verdict": "pass",
        "applicationCpuSeconds": total,
        "sampleCount": len(samples),
        "scope": ("declared-application-containers-only" if scope == APPLICATION_SERVICES
                  else "declared-application-containers-plus-extra-services"),
    }


def parse_emissions(
    log_text: str, window_start_unix_nano: int, window_end_unix_nano: int,
) -> dict[str, Any]:
    if (
        type(window_start_unix_nano) is not int or type(window_end_unix_nano) is not int
        or window_start_unix_nano <= 0 or window_end_unix_nano <= window_start_unix_nano
    ):
        raise ResourceError("emission window must be positive integer Unix nanoseconds")
    events = []
    seen: set[tuple[str, str]] = set()
    for line_number, line in enumerate(log_text.splitlines(), start=1):
        marker = line.find(EMISSION_PREFIX)
        if marker < 0:
            continue
        row = strict_json(line[marker + len(EMISSION_PREFIX):], f"emission line {line_number}")
        required = {
            "schema", "service", "traceId", "spanId", "startedAtUnixNano",
            "endedAtUnixNano", "compactThriftSpanBytes", "wireBytes",
        }
        if not isinstance(row, dict) or set(row) != required:
            raise ResourceError("emission witness fields differ")
        identity = (row.get("traceId"), row.get("spanId"))
        if (
            row.get("schema") != "hotel-source-emitted-span-v1"
            or row.get("service") not in APPLICATION_SERVICES
            or TRACE_ID.fullmatch(str(identity[0])) is None
            or SPAN_ID.fullmatch(str(identity[1])) is None
            or identity in seen
            or type(row.get("startedAtUnixNano")) is not int
            or type(row.get("endedAtUnixNano")) is not int
            or row["endedAtUnixNano"] < row["startedAtUnixNano"]
            or type(row.get("compactThriftSpanBytes")) is not int
            or row["compactThriftSpanBytes"] <= 0
            or row.get("wireBytes") is not False
        ):
            raise ResourceError("emission witness identity, bounds, or classification differs")
        seen.add(identity)
        if (
            row["startedAtUnixNano"] >= window_start_unix_nano
            and row["endedAtUnixNano"] <= window_end_unix_nano
        ):
            events.append(row)
    events.sort(key=lambda row: (row["startedAtUnixNano"], row["traceId"], row["spanId"]))
    body = {
        "schemaVersion": 1,
        "contract": EMISSION_CONTRACT,
        "windowStartUnixNano": window_start_unix_nano,
        "windowEndUnixNano": window_end_unix_nano,
        "eventCount": len(events),
        "compactThriftSpanBytes": sum(row["compactThriftSpanBytes"] for row in events),
        "wireBytes": None,
        "wireBytesState": "unsupported",
        "events": events,
    }
    return {**body, "canonicalSha256": canonical_sha256(body)}


def validate_emissions(document: Any) -> dict[str, Any]:
    keys = {
        "schemaVersion", "contract", "windowStartUnixNano", "windowEndUnixNano",
        "eventCount", "compactThriftSpanBytes", "wireBytes", "wireBytesState",
        "events", "canonicalSha256",
    }
    if not isinstance(document, dict) or set(document) != keys:
        raise ResourceError("emission artifact fields differ")
    body = {key: value for key, value in document.items() if key != "canonicalSha256"}
    if (
        document.get("schemaVersion") != 1
        or document.get("contract") != EMISSION_CONTRACT
        or document.get("canonicalSha256") != canonical_sha256(body)
        or document.get("wireBytes") is not None
        or document.get("wireBytesState") != "unsupported"
        or document.get("eventCount") != len(document.get("events", []))
        or document.get("compactThriftSpanBytes") != sum(
            row.get("compactThriftSpanBytes", -1) for row in document.get("events", [])
        )
    ):
        raise ResourceError("emission artifact digest, totals, or missingness differs")
    replay = parse_emissions(
        "\n".join(EMISSION_PREFIX + json.dumps(row, separators=(",", ":")) for row in document["events"]),
        document["windowStartUnixNano"], document["windowEndUnixNano"],
    )
    if canonical_sha256(replay["events"]) != canonical_sha256(document["events"]):
        raise ResourceError("emission events differ from deterministic replay")
    return {
        "schemaVersion": 1,
        "kind": "hotel-candidate-emission-validation-v1",
        "verdict": "pass",
        "eventCount": document["eventCount"],
        "compactThriftSpanBytes": document["compactThriftSpanBytes"],
        "wireBytes": None,
        "wireBytesState": "unsupported",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    cpu = commands.add_parser("validate-cpu")
    cpu.add_argument("artifact", type=Path)
    emitted = commands.add_parser("extract-emissions")
    emitted.add_argument("application_log", type=Path)
    emitted.add_argument("--start-ns", required=True, type=int)
    emitted.add_argument("--end-ns", required=True, type=int)
    emitted.add_argument("--output", required=True, type=Path)
    check = commands.add_parser("validate-emissions")
    check.add_argument("artifact", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "validate-cpu":
            document = strict_json(args.artifact.read_text(), str(args.artifact))
            declared = document.get("applicationServices") if isinstance(document, dict) else None
            result = validate_cpu(document, EXTENDED_SERVICES if declared == list(EXTENDED_SERVICES)
                                  else APPLICATION_SERVICES)
        elif args.command == "extract-emissions":
            result = parse_emissions(args.application_log.read_text(encoding="utf-8", errors="replace"), args.start_ns, args.end_ns)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        else:
            result = validate_emissions(strict_json(args.artifact.read_text(), str(args.artifact)))
    except ResourceError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
