#!/usr/bin/env python3
"""Sample Docker application CPU/memory and host CPU for a measurement window."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import time
from pathlib import Path


UNITS = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}
BARRIER_ID = re.compile(r"^barrier-[0-9a-f]{32}$")


def bytes_value(text: str) -> float:
    match = re.match(r"\s*([0-9.]+)([KMG]iB|B)", text)
    return float(match.group(1)) * UNITS[match.group(2)] if match else 0.0


def host_ticks() -> tuple[int, int]:
    fields = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
    values = [int(value) for value in fields]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def docker_sample(project: str, excluded_services: set[str],
                  required_services: set[str] | None = None) -> tuple[float, float, list[dict]]:
    required_services = required_services or set()
    ids = subprocess.run(
        ["docker", "ps", "-q", "--filter", f"label=com.docker.compose.project={project}"],
        text=True, capture_output=True, check=True,
    ).stdout.split()
    if not ids:
        if required_services:
            raise RuntimeError(f"no containers found for required services {sorted(required_services)}")
        return 0.0, 0.0, []
    if excluded_services:
        retained = []
        for container_id in ids:
            service = subprocess.run(
                ["docker", "inspect", "-f", "{{index .Config.Labels \"com.docker.compose.service\"}}", container_id],
                text=True, capture_output=True, check=True,
            ).stdout.strip()
            if service not in excluded_services:
                retained.append(container_id)
        ids = retained
    if not ids:
        if required_services:
            raise RuntimeError(f"no retained containers for required services {sorted(required_services)}")
        return 0.0, 0.0, []
    observed_services: list[str] = []
    for container_id in ids:
        service = subprocess.run(
            ["docker", "inspect", "-f", "{{index .Config.Labels \"com.docker.compose.service\"}}", container_id],
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        observed_services.append(service)
    if required_services:
        duplicates = sorted({name for name in observed_services if observed_services.count(name) != 1})
        missing = sorted(required_services - set(observed_services))
        unexpected = sorted(set(observed_services) - required_services)
        if duplicates or missing or unexpected:
            raise RuntimeError(
                "application container set differs: "
                f"missing={missing}, unexpected={unexpected}, duplicates={duplicates}"
            )
    output = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", *ids],
        text=True, capture_output=True, check=True,
    ).stdout
    rows = [json.loads(line) for line in output.splitlines() if line.strip()]
    cpu = sum(float(row["CPUPerc"].rstrip("%")) for row in rows)
    memory = sum(bytes_value(row["MemUsage"].split("/")[0]) for row in rows)
    return cpu, memory, rows


def sample(project: str, duration: float, interval: float,
           excluded_services: set[str] | None = None,
           required_services: set[str] | None = None,
           start_at_epoch: float | None = None,
           barrier_id: str | None = None) -> dict:
    excluded_services = excluded_services or set()
    required_services = required_services or set()
    if barrier_id is not None and not BARRIER_ID.fullmatch(barrier_id):
        raise ValueError("barrier_id must be a bounded controller-generated identifier")
    if start_at_epoch is not None:
        if not math.isfinite(start_at_epoch):
            raise ValueError("start_at_epoch must be finite")
        delay = start_at_epoch - time.time()
        if delay < -1.0:
            raise ValueError("shared measurement barrier is already more than one second in the past")
        if delay > 0:
            time.sleep(delay)
    tick_rate = os.sysconf("SC_CLK_TCK")
    total0, idle0 = host_ticks()
    started = time.time()
    samples = []
    app_cpu_seconds = 0.0
    last = time.monotonic()
    deadline = last + duration
    while time.monotonic() < deadline:
        cpu_percent, memory, rows = docker_sample(
            project, excluded_services, required_services)
        now = time.monotonic()
        elapsed = now - last
        app_cpu_seconds += cpu_percent / 100.0 * elapsed
        samples.append({"epoch": time.time(), "applicationCpuPercent": cpu_percent, "applicationMemoryBytes": memory, "containers": rows})
        last = now
        time.sleep(max(0.0, min(interval, deadline - time.monotonic())))
    total1, idle1 = host_ticks()
    return {
        "schemaVersion": 2,
        "startedAtEpoch": started,
        "endedAtEpoch": time.time(),
        "applicationCpuSeconds": app_cpu_seconds,
        "applicationMemoryPeakBytes": max((row["applicationMemoryBytes"] for row in samples), default=0),
        "hostCpuSeconds": ((total1 - total0) - (idle1 - idle0)) / tick_rate,
        "sampleIntervalSeconds": interval,
        "excludedServices": sorted(excluded_services),
        "requiredServices": sorted(required_services),
        "requestedStartAtEpoch": start_at_epoch,
        "barrierId": barrier_id,
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude-service", action="append", default=[])
    parser.add_argument("--require-service", action="append", default=[])
    parser.add_argument("--start-at-epoch", type=float)
    parser.add_argument("--barrier-id")
    args = parser.parse_args()
    if args.duration <= 0 or args.interval <= 0:
        parser.error("duration and interval must be positive")
    result = sample(
        args.project, args.duration, args.interval, set(args.exclude_service),
        set(args.require_service), args.start_at_epoch, args.barrier_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
