#!/usr/bin/env python3
"""Collect replayable TeaStore resource evidence on fixed-rate nominal slots."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any


UNITS = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}
BARRIER_ID = re.compile(r"^barrier-[0-9a-f]{32}$")
CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")
CONTRACT = "teastore-resource-probe-v3"
SAMPLING_SEMANTICS = "fixed-rate-slots-v1"
CLOCK_SEMANTICS = "wall-barrier-monotonic-slots-v1"
HOST_CPU_SCOPE = "nominal-window-diagnostic"
DEFAULT_INTERVAL_SECONDS = 5.0
DEFAULT_COMMAND_TIMEOUT_SECONDS = 4.0
DEFAULT_MAXIMUM_START_LATENESS_SECONDS = 1.0


def _number(value: Any, *, positive: bool = False) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and (float(value) > 0 if positive else float(value) >= 0)
    )


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _integer(value: Any, *, positive: bool = False) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and (value > 0 if positive else value >= 0)
    )


def _close(left: Any, right: Any, *, tolerance: float = 1e-6) -> bool:
    return _number(left) and _number(right) and math.isclose(
        float(left), float(right), rel_tol=1e-9, abs_tol=tolerance)


def _finite_close(left: Any, right: Any, *, tolerance: float = 1e-6) -> bool:
    return _finite_number(left) and _finite_number(right) and math.isclose(
        float(left), float(right), rel_tol=1e-9, abs_tol=tolerance)


def bytes_value(text: str) -> float:
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)([KMG]iB|B)\s*", text)
    if not match:
        raise ValueError(f"unsupported Docker memory value: {text!r}")
    return float(match.group(1)) * UNITS[match.group(2)]


def host_ticks() -> tuple[int, int]:
    fields = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
    values = [int(value) for value in fields]
    if len(values) < 4:
        raise RuntimeError("/proc/stat aggregate CPU row is malformed")
    # Linux guest and guest_nice are already included in user and nice.  Use
    # only the first eight counters so the retained total does not double count
    # them and can be replayed directly from the evidence.
    values = values[:8]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def _run(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, text=True, capture_output=True, check=True, timeout=timeout,
    )


def resolve_containers(
    project: str,
    excluded_services: set[str],
    required_services: set[str],
    command_timeout: float,
) -> dict[str, str]:
    """Resolve one stable full container ID for every required service."""

    ids = _run([
        "docker", "ps", "-q", "--no-trunc", "--filter",
        f"label=com.docker.compose.project={project}",
    ], command_timeout).stdout.split()
    if not ids:
        raise RuntimeError(f"no containers found for required services {sorted(required_services)}")
    if any(CONTAINER_ID.fullmatch(value) is None for value in ids):
        raise RuntimeError("Docker inventory returned a malformed or truncated container ID")
    inspected = _run([
        "docker", "inspect", "--format",
        '{{.Id}}\t{{index .Config.Labels "com.docker.compose.service"}}', *ids,
    ], command_timeout).stdout.splitlines()
    observed: dict[str, list[str]] = {}
    for line in inspected:
        parts = line.split("\t")
        if len(parts) != 2 or CONTAINER_ID.fullmatch(parts[0]) is None or not parts[1]:
            raise RuntimeError("Docker service inventory row is malformed")
        if parts[1] not in excluded_services:
            observed.setdefault(parts[1], []).append(parts[0])
    duplicates = sorted(service for service, values in observed.items() if len(values) != 1)
    missing = sorted(required_services - set(observed))
    unexpected = sorted(set(observed) - required_services)
    if duplicates or missing or unexpected:
        raise RuntimeError(
            "application container set differs: "
            f"missing={missing}, unexpected={unexpected}, duplicates={duplicates}"
        )
    return {service: observed[service][0] for service in sorted(required_services)}


def collect_slot(
    container_identity: dict[str, str], command_timeout: float,
) -> tuple[float, float, list[dict[str, Any]]]:
    """Collect and normalize exactly one Docker stats row per bound service."""

    output = _run([
        "docker", "stats", "--no-stream", "--format", "{{json .}}",
        *container_identity.values(),
    ], command_timeout).stdout
    raw_rows = [json.loads(line) for line in output.splitlines() if line.strip()]
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_rows:
        short_id = raw.get("ID", raw.get("Container"))
        if not isinstance(short_id, str) or not short_id:
            raise RuntimeError("Docker stats row has no container identity")
        matches = [
            (service, full_id) for service, full_id in container_identity.items()
            if full_id.startswith(short_id)
        ]
        if len(matches) != 1:
            raise RuntimeError(f"Docker stats identity is missing or ambiguous: {short_id!r}")
        service, full_id = matches[0]
        if service in seen:
            raise RuntimeError(f"Docker stats duplicated service {service!r}")
        seen.add(service)
        cpu_text = raw.get("CPUPerc")
        memory_text = raw.get("MemUsage")
        name = raw.get("Name")
        if not isinstance(cpu_text, str) or not cpu_text.endswith("%") or not isinstance(
            memory_text, str
        ) or "/" not in memory_text or not isinstance(name, str) or not name:
            raise RuntimeError(f"Docker stats row for {service!r} is malformed")
        cpu = float(cpu_text[:-1])
        memory = bytes_value(memory_text.split("/", 1)[0])
        if not _number(cpu) or not _number(memory):
            raise RuntimeError(f"Docker stats row for {service!r} is non-finite")
        normalized.append({
            "service": service,
            "containerId": full_id,
            "name": name,
            "cpuPercent": cpu,
            "memoryBytes": memory,
        })
    missing = sorted(set(container_identity) - seen)
    if missing or len(normalized) != len(container_identity):
        raise RuntimeError(f"Docker stats service set differs: missing={missing}")
    normalized.sort(key=lambda row: row["service"])
    return (
        sum(float(row["cpuPercent"]) for row in normalized),
        sum(float(row["memoryBytes"]) for row in normalized),
        normalized,
    )


def validate_resource_evidence(
    document: Any,
    *,
    required_services: set[str] | None = None,
    expected_barrier_id: str | None = None,
    expected_start_epoch: float | None = None,
    expected_duration_seconds: float | None = None,
) -> dict[str, Any]:
    """Purely replay shape, identities, fixed slots, and aggregate arithmetic."""

    blockers: list[str] = []
    fields = {
        "schemaVersion", "contract", "barrierId", "requestedStartAtEpoch",
        "nominalStartAtEpoch", "nominalEndAtEpoch", "measurementDurationSeconds",
        "collectorStartedAtEpoch", "collectorEndedAtEpoch", "clock", "sampling",
        "excludedServices", "requiredServices", "containerIdentity", "samples",
        "applicationCpuSeconds", "applicationMemoryPeakBytes", "hostCpuSeconds",
        "hostCpuScope", "hostCpuAccounting",
    }
    if not isinstance(document, dict) or set(document) != fields:
        return {"verdict": "blocked", "blockers": ["resource evidence fields differ"]}
    if document.get("schemaVersion") != 3 or document.get("contract") != CONTRACT:
        blockers.append("resource evidence contract differs")
    barrier_id = document.get("barrierId")
    if not isinstance(barrier_id, str) or BARRIER_ID.fullmatch(barrier_id) is None:
        blockers.append("resource barrier ID is malformed")
    if expected_barrier_id is not None and barrier_id != expected_barrier_id:
        blockers.append("resource barrier ID differs from the expected run")
    start = document.get("nominalStartAtEpoch")
    requested = document.get("requestedStartAtEpoch")
    end = document.get("nominalEndAtEpoch")
    duration = document.get("measurementDurationSeconds")
    if (not _number(start) or not _number(requested) or not _number(end)
            or not _number(duration, positive=True) or not _close(start, requested)
            or not _close(float(end) - float(start), duration)):
        blockers.append("resource nominal window is invalid")
    if expected_start_epoch is not None and not _close(start, expected_start_epoch):
        blockers.append("resource nominal start differs from the expected barrier")
    if expected_duration_seconds is not None and not _close(duration, expected_duration_seconds):
        blockers.append("resource duration differs from the expected run")
    collector_started = document.get("collectorStartedAtEpoch")
    collector_ended = document.get("collectorEndedAtEpoch")
    if not _number(collector_started) or not _number(collector_ended):
        blockers.append("resource collector wall timestamps are invalid")
    clock = document.get("clock")
    clock_fields = {
        "semantics", "anchorWallEpoch", "anchorMonotonicSeconds",
        "barrierMonotonicSeconds", "collectorStartedMonotonicOffsetSeconds",
        "collectorEndedMonotonicOffsetSeconds",
    }
    if not isinstance(clock, dict) or set(clock) != clock_fields:
        blockers.append("resource clock contract fields differ")
        clock = {}
    anchor_wall = clock.get("anchorWallEpoch")
    anchor_monotonic = clock.get("anchorMonotonicSeconds")
    barrier_monotonic = clock.get("barrierMonotonicSeconds")
    collector_started_offset = clock.get("collectorStartedMonotonicOffsetSeconds")
    collector_ended_offset = clock.get("collectorEndedMonotonicOffsetSeconds")
    barrier_binding_ok = (
        _number(anchor_wall) and _number(anchor_monotonic)
        and _number(barrier_monotonic) and _number(start)
        and _finite_close(
            barrier_monotonic,
            float(anchor_monotonic) + float(start) - float(anchor_wall),
        )
    )
    collector_coverage_ok = (
        _finite_number(collector_started_offset)
        and float(collector_started_offset) <= DEFAULT_MAXIMUM_START_LATENESS_SECONDS
        and _number(collector_ended_offset)
        and _number(duration, positive=True)
        and float(collector_ended_offset) >= float(duration)
    )
    if (clock.get("semantics") != CLOCK_SEMANTICS or not barrier_binding_ok
            or not collector_coverage_ok):
        blockers.append("resource collector does not cover the nominal window")
    if document.get("excludedServices") != ["db", "rabbitmq", "registry"]:
        blockers.append("resource excluded-service boundary differs")
    declared_services = document.get("requiredServices")
    expected_services = sorted(required_services) if required_services is not None else declared_services
    if (not isinstance(declared_services, list) or not declared_services
            or declared_services != sorted(set(declared_services))
            or (required_services is not None and declared_services != expected_services)):
        blockers.append("resource required-service set differs")
        expected_services = declared_services if isinstance(declared_services, list) else []
    identities = document.get("containerIdentity")
    if (not isinstance(identities, dict) or set(identities) != set(expected_services)
            or any(not isinstance(value, str) or CONTAINER_ID.fullmatch(value) is None
                   for value in identities.values())
            or len(set(identities.values())) != len(identities)):
        blockers.append("resource container identity map is invalid")
        identities = identities if isinstance(identities, dict) else {}
    sampling = document.get("sampling")
    sampling_fields = {
        "semantics", "intervalSeconds", "commandTimeoutSeconds", "expectedSlots",
        "completedSlots", "missedSlots", "maximumStartLatenessSeconds",
    }
    if not isinstance(sampling, dict) or set(sampling) != sampling_fields:
        blockers.append("resource sampling contract fields differ")
        sampling = {}
    interval = sampling.get("intervalSeconds")
    timeout = sampling.get("commandTimeoutSeconds")
    lateness_limit = sampling.get("maximumStartLatenessSeconds")
    if (sampling.get("semantics") != SAMPLING_SEMANTICS
            or not _number(interval, positive=True)
            or float(interval) != DEFAULT_INTERVAL_SECONDS
            or not _number(timeout, positive=True)
            or float(timeout) != DEFAULT_COMMAND_TIMEOUT_SECONDS
            or not _number(lateness_limit)
            or float(lateness_limit) != DEFAULT_MAXIMUM_START_LATENESS_SECONDS):
        blockers.append("resource sampling policy is invalid")
    expected_slots = None
    if _number(duration, positive=True) and _number(interval, positive=True):
        expected_slots = math.ceil(float(duration) / float(interval))
    samples = document.get("samples")
    if (not isinstance(samples, list) or expected_slots is None
            or sampling.get("expectedSlots") != expected_slots
            or sampling.get("completedSlots") != len(samples)
            or len(samples) != expected_slots or sampling.get("missedSlots") != []):
        blockers.append("resource slot coverage is incomplete")
        samples = samples if isinstance(samples, list) else []
    sample_fields = {
        "slot", "scheduledAtEpoch", "startedAtEpoch", "completedAtEpoch",
        "scheduledMonotonicOffsetSeconds", "startedMonotonicOffsetSeconds",
        "completedMonotonicOffsetSeconds", "startLatenessSeconds",
        "integrationWeightSeconds",
        "applicationCpuPercent", "applicationCpuSecondsContribution",
        "applicationMemoryBytes", "containers",
    }
    row_fields = {"service", "containerId", "name", "cpuPercent", "memoryBytes"}
    computed_cpu = 0.0
    computed_peak = 0.0
    computed_weight = 0.0
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict) or set(sample) != sample_fields:
            blockers.append(f"resource sample {index} fields differ")
            continue
        scheduled = sample.get("scheduledAtEpoch")
        actual_start_wall = sample.get("startedAtEpoch")
        completed_wall = sample.get("completedAtEpoch")
        scheduled_monotonic_offset = sample.get("scheduledMonotonicOffsetSeconds")
        actual_start_monotonic_offset = sample.get("startedMonotonicOffsetSeconds")
        completed_monotonic_offset = sample.get("completedMonotonicOffsetSeconds")
        weight = sample.get("integrationWeightSeconds")
        expected_scheduled = float(start) + index * float(interval) if _number(
            start
        ) and _number(interval, positive=True) else None
        expected_weight = min(
            float(interval), max(0.0, float(end) - float(expected_scheduled))
        ) if expected_scheduled is not None and _number(end) else None
        timing_ok = (
            sample.get("slot") == index and expected_scheduled is not None
            and _close(scheduled, expected_scheduled)
            and _number(actual_start_wall) and _number(completed_wall)
            and _number(scheduled_monotonic_offset)
            and _close(scheduled_monotonic_offset, index * float(interval))
            and _number(actual_start_monotonic_offset)
            and _number(completed_monotonic_offset)
            and float(completed_monotonic_offset) >= float(actual_start_monotonic_offset)
            and float(actual_start_monotonic_offset) >= float(scheduled_monotonic_offset)
            and _number(lateness_limit)
            and _close(
                sample.get("startLatenessSeconds"),
                float(actual_start_monotonic_offset) - float(scheduled_monotonic_offset),
            )
            and float(sample["startLatenessSeconds"]) <= float(lateness_limit)
            and expected_weight is not None and _close(weight, expected_weight)
            and float(completed_monotonic_offset)
            <= float(scheduled_monotonic_offset) + float(expected_weight)
        )
        if not timing_ok:
            blockers.append(f"resource sample {index} timing is invalid")
        rows = sample.get("containers")
        rows_ok = isinstance(rows, list) and len(rows) == len(expected_services)
        seen_services: list[str] = []
        row_cpu = 0.0
        row_memory = 0.0
        if rows_ok:
            for row in rows:
                if not isinstance(row, dict) or set(row) != row_fields:
                    rows_ok = False
                    continue
                service = row.get("service")
                if (service not in expected_services or service in seen_services
                        or row.get("containerId") != identities.get(service)
                        or not isinstance(row.get("name"), str) or not row["name"]
                        or not _number(row.get("cpuPercent"))
                        or not _number(row.get("memoryBytes"))):
                    rows_ok = False
                    continue
                seen_services.append(service)
                row_cpu += float(row["cpuPercent"])
                row_memory += float(row["memoryBytes"])
            rows_ok &= seen_services == expected_services
        cpu = sample.get("applicationCpuPercent")
        memory = sample.get("applicationMemoryBytes")
        contribution = sample.get("applicationCpuSecondsContribution")
        if (not rows_ok or not _close(cpu, row_cpu) or not _close(memory, row_memory)
                or not _number(contribution) or not _number(weight)
                or not _close(contribution, float(cpu) / 100.0 * float(weight))):
            blockers.append(f"resource sample {index} rows or arithmetic are invalid")
        if _number(contribution):
            computed_cpu += float(contribution)
        if _number(memory):
            computed_peak = max(computed_peak, float(memory))
        if _number(weight):
            computed_weight += float(weight)
    if (not _close(computed_weight, duration)
            or not _close(document.get("applicationCpuSeconds"), computed_cpu)
            or not _close(document.get("applicationMemoryPeakBytes"), computed_peak)):
        blockers.append("resource aggregate arithmetic does not replay")
    host = document.get("hostCpuAccounting")
    host_fields = {"tickRateHz", "start", "end", "busyTicks"}
    endpoint_fields = {"totalTicks", "idleTicks", "monotonicOffsetSeconds"}
    if not isinstance(host, dict) or set(host) != host_fields:
        blockers.append("resource host CPU accounting fields differ")
        host = {}
    host_start = host.get("start")
    host_end = host.get("end")
    if (not isinstance(host_start, dict) or set(host_start) != endpoint_fields
            or not isinstance(host_end, dict) or set(host_end) != endpoint_fields):
        blockers.append("resource host CPU endpoint fields differ")
        host_start = {}
        host_end = {}
    tick_rate = host.get("tickRateHz")
    start_total = host_start.get("totalTicks")
    start_idle = host_start.get("idleTicks")
    end_total = host_end.get("totalTicks")
    end_idle = host_end.get("idleTicks")
    busy_ticks = host.get("busyTicks")
    start_tick_offset = host_start.get("monotonicOffsetSeconds")
    end_tick_offset = host_end.get("monotonicOffsetSeconds")
    counters_ok = (
        _integer(tick_rate, positive=True)
        and _integer(start_total) and _integer(start_idle)
        and _integer(end_total) and _integer(end_idle)
        and _integer(busy_ticks)
        and start_idle <= start_total and end_idle <= end_total
        and end_total >= start_total and end_idle >= start_idle
    )
    derived_busy_ticks = None
    if counters_ok:
        derived_busy_ticks = (end_total - start_total) - (end_idle - start_idle)
        counters_ok = derived_busy_ticks >= 0 and busy_ticks == derived_busy_ticks
    endpoint_timing_ok = (
        _number(start_tick_offset)
        and float(start_tick_offset) <= DEFAULT_MAXIMUM_START_LATENESS_SECONDS
        and _number(end_tick_offset)
        and _number(duration, positive=True)
        and float(end_tick_offset) >= float(duration)
    )
    replayed_host_cpu_seconds = (
        float(derived_busy_ticks) / float(tick_rate)
        if counters_ok else None
    )
    if (not counters_ok or not endpoint_timing_ok
            or not _close(document.get("hostCpuSeconds"), replayed_host_cpu_seconds)
            or document.get("hostCpuScope") != HOST_CPU_SCOPE):
        blockers.append("resource host CPU diagnostic is invalid")
    return {
        "verdict": "pass" if not blockers else "blocked",
        "blockers": blockers,
        "applicationCpuSeconds": computed_cpu if not blockers else None,
        "applicationMemoryPeakBytes": computed_peak if not blockers else None,
        "integrationWeightSeconds": computed_weight if not blockers else None,
    }


def sample(
    project: str,
    duration: float,
    interval: float,
    excluded_services: set[str] | None = None,
    required_services: set[str] | None = None,
    start_at_epoch: float | None = None,
    barrier_id: str | None = None,
    command_timeout: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    maximum_start_lateness: float = DEFAULT_MAXIMUM_START_LATENESS_SECONDS,
) -> dict[str, Any]:
    excluded_services = excluded_services or set()
    required_services = required_services or set()
    if barrier_id is None or BARRIER_ID.fullmatch(barrier_id) is None:
        raise ValueError("barrier_id must be a bounded controller-generated identifier")
    if start_at_epoch is None or not math.isfinite(start_at_epoch):
        raise ValueError("start_at_epoch must be finite and explicit")
    if (not _number(duration, positive=True) or not _number(interval, positive=True)
            or float(interval) != DEFAULT_INTERVAL_SECONDS
            or not _number(command_timeout, positive=True)
            or float(command_timeout) != DEFAULT_COMMAND_TIMEOUT_SECONDS
            or not _number(maximum_start_lateness)
            or float(maximum_start_lateness)
            != DEFAULT_MAXIMUM_START_LATENESS_SECONDS):
        raise ValueError("duration, cadence, timeout, or lateness policy is invalid")
    collector_started = time.time()
    collector_started_monotonic = time.monotonic()
    identity = resolve_containers(
        project, excluded_services, required_services, command_timeout)
    anchor_wall = time.time()
    anchor_monotonic = time.monotonic()
    barrier_monotonic = anchor_monotonic + start_at_epoch - anchor_wall
    delay = barrier_monotonic - time.monotonic()
    if delay < -1.0:
        raise ValueError("shared measurement barrier is already more than one second in the past")
    if delay > 0:
        time.sleep(delay)
    tick_rate = os.sysconf("SC_CLK_TCK")
    total0, idle0 = host_ticks()
    host_start_monotonic = time.monotonic()
    nominal_end = start_at_epoch + duration
    nominal_end_monotonic = barrier_monotonic + duration
    expected_slots = math.ceil(duration / interval)
    samples: list[dict[str, Any]] = []
    for slot in range(expected_slots):
        scheduled = start_at_epoch + slot * interval
        scheduled_monotonic = barrier_monotonic + slot * interval
        delay = scheduled_monotonic - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        actual_start_monotonic = time.monotonic()
        actual_start = time.time()
        lateness = actual_start_monotonic - scheduled_monotonic
        if lateness < 0 or lateness > maximum_start_lateness:
            raise RuntimeError(f"resource slot {slot} missed its fixed-rate start")
        cpu, memory, rows = collect_slot(identity, command_timeout)
        completed_monotonic = time.monotonic()
        completed = time.time()
        weight = min(interval, nominal_end - scheduled)
        if completed_monotonic > scheduled_monotonic + weight:
            raise RuntimeError(f"resource slot {slot} overran its nominal slot")
        samples.append({
            "slot": slot, "scheduledAtEpoch": scheduled,
            "startedAtEpoch": actual_start, "completedAtEpoch": completed,
            "scheduledMonotonicOffsetSeconds": scheduled_monotonic - barrier_monotonic,
            "startedMonotonicOffsetSeconds": actual_start_monotonic - barrier_monotonic,
            "completedMonotonicOffsetSeconds": completed_monotonic - barrier_monotonic,
            "startLatenessSeconds": lateness, "integrationWeightSeconds": weight,
            "applicationCpuPercent": cpu,
            "applicationCpuSecondsContribution": cpu / 100.0 * weight,
            "applicationMemoryBytes": memory, "containers": rows,
        })
    delay = nominal_end_monotonic - time.monotonic()
    if delay > 0:
        time.sleep(delay)
    total1, idle1 = host_ticks()
    host_end_monotonic = time.monotonic()
    collector_ended_monotonic = time.monotonic()
    collector_ended = time.time()
    busy_ticks = (total1 - total0) - (idle1 - idle0)
    result = {
        "schemaVersion": 3, "contract": CONTRACT, "barrierId": barrier_id,
        "requestedStartAtEpoch": start_at_epoch,
        "nominalStartAtEpoch": start_at_epoch, "nominalEndAtEpoch": nominal_end,
        "measurementDurationSeconds": duration,
        "collectorStartedAtEpoch": collector_started,
        "collectorEndedAtEpoch": collector_ended,
        "clock": {
            "semantics": CLOCK_SEMANTICS,
            "anchorWallEpoch": anchor_wall,
            "anchorMonotonicSeconds": anchor_monotonic,
            "barrierMonotonicSeconds": barrier_monotonic,
            "collectorStartedMonotonicOffsetSeconds": (
                collector_started_monotonic - barrier_monotonic),
            "collectorEndedMonotonicOffsetSeconds": (
                collector_ended_monotonic - barrier_monotonic),
        },
        "sampling": {
            "semantics": SAMPLING_SEMANTICS, "intervalSeconds": interval,
            "commandTimeoutSeconds": command_timeout, "expectedSlots": expected_slots,
            "completedSlots": len(samples), "missedSlots": [],
            "maximumStartLatenessSeconds": maximum_start_lateness,
        },
        "excludedServices": sorted(excluded_services),
        "requiredServices": sorted(required_services),
        "containerIdentity": identity, "samples": samples,
        "applicationCpuSeconds": sum(
            row["applicationCpuSecondsContribution"] for row in samples),
        "applicationMemoryPeakBytes": max(
            (row["applicationMemoryBytes"] for row in samples), default=0.0),
        "hostCpuSeconds": busy_ticks / tick_rate,
        "hostCpuScope": HOST_CPU_SCOPE,
        "hostCpuAccounting": {
            "tickRateHz": tick_rate,
            "start": {
                "totalTicks": total0,
                "idleTicks": idle0,
                "monotonicOffsetSeconds": host_start_monotonic - barrier_monotonic,
            },
            "end": {
                "totalTicks": total1,
                "idleTicks": idle1,
                "monotonicOffsetSeconds": host_end_monotonic - barrier_monotonic,
            },
            "busyTicks": busy_ticks,
        },
    }
    replay = validate_resource_evidence(
        result, required_services=required_services, expected_barrier_id=barrier_id,
        expected_start_epoch=start_at_epoch, expected_duration_seconds=duration,
    )
    if replay["verdict"] != "pass":
        raise RuntimeError(f"self-validation failed: {replay['blockers']}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--command-timeout", type=float,
                        default=DEFAULT_COMMAND_TIMEOUT_SECONDS)
    parser.add_argument("--maximum-start-lateness", type=float,
                        default=DEFAULT_MAXIMUM_START_LATENESS_SECONDS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude-service", action="append", default=[])
    parser.add_argument("--require-service", action="append", default=[])
    parser.add_argument("--start-at-epoch", type=float, required=True)
    parser.add_argument("--barrier-id", required=True)
    args = parser.parse_args()
    result = sample(
        args.project, args.duration, args.interval, set(args.exclude_service),
        set(args.require_service), args.start_at_epoch, args.barrier_id,
        args.command_timeout, args.maximum_start_lateness,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
