#!/usr/bin/env python3
"""TeaStore system probe (sys lineage, 2026-09-29): cgroup-v2 counters for every container of the cell's Compose project.

Runs in every cell, cost and fault alike, beside the unchanged ``performance_probe_v3.py``. Every ``--interval`` seconds from
``--start-at-epoch`` it reads, per container: ``cpu.stat usage_usec``, ``memory.current``, ``io.stat`` bytes and PSI ``some
total`` for cpu, memory and io, plus ``usage_usec`` of ``docker.service`` and ``containerd.service``.

Fault-window samples are detection signals only; no cost is computed from a fault cell. A container that is stopped
(persistence-crash) has no cgroup scope: its row is ``null`` for that sample, never zero. A restart resets the counters, so
readers take rates only between consecutive non-null samples whose counters did not decrease.
Ported from Hotel's ``collectors/system_state.py`` (LMT pilot); TCP snapshots are dropped because cells run as ``stig`` without sudo.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

CGROUP = Path("/sys/fs/cgroup")
DAEMON_UNITS = ("docker.service", "containerd.service")
KIND = "teastore-system-samples-v1"


def _now(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def _kv(path: Path) -> dict:
    rows = {}
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) == 2:
            rows[parts[0]] = int(parts[1])
    return rows


def _psi_some_total(path: Path) -> int | None:
    if not path.is_file():
        return None
    for line in path.read_text().splitlines():
        if line.startswith("some "):
            for field in line.split()[1:]:
                key, _, value = field.partition("=")
                if key == "total":
                    return int(value)
    return None


def read_scope(scope: Path) -> dict | None:
    """One container's counters, or None when its scope is gone (stopped container) or vanishes mid-read."""
    try:
        read = write = 0
        for line in (scope / "io.stat").read_text().splitlines():
            for field in line.split()[1:]:
                key, _, value = field.partition("=")
                if key == "rbytes":
                    read += int(value)
                elif key == "wbytes":
                    write += int(value)
        return {"cpuUsageUsec": _kv(scope / "cpu.stat")["usage_usec"],
                "memoryCurrent": int((scope / "memory.current").read_text()),
                "rbytes": read, "wbytes": write,
                **{"psi%sSomeTotalUsec" % r.capitalize(): _psi_some_total(scope / ("%s.pressure" % r))
                   for r in ("cpu", "memory", "io")}}
    except (OSError, KeyError, ValueError):
        return None


def sample(root: Path, containers: dict, epoch: float) -> dict:
    """``containers`` maps service -> full container id."""
    services = {s: read_scope(root / "system.slice" / ("docker-%s.scope" % cid)) for s, cid in sorted(containers.items())}
    daemons = {}
    for unit in DAEMON_UNITS:
        try:
            daemons[unit] = _kv(root / "system.slice" / unit / "cpu.stat")["usage_usec"]
        except (OSError, KeyError, ValueError):
            daemons[unit] = None
    return {"epoch": epoch, "at": _now(epoch), "monotonic": time.monotonic(), "services": services, "daemons": daemons}


def resolve(project: str, required: list) -> dict:
    ids = subprocess.run(["docker", "ps", "-q", "--no-trunc", "--filter", "label=com.docker.compose.project=%s" % project],
                         text=True, capture_output=True, check=True, timeout=20).stdout.split()
    if not ids:
        raise RuntimeError("no running container in project %s" % project)
    out = subprocess.run(["docker", "inspect", "--format", '{{.Id}} {{index .Config.Labels "com.docker.compose.service"}}', *ids],
                         text=True, capture_output=True, check=True, timeout=20).stdout
    containers = {}
    for line in out.splitlines():
        cid, _, service = line.partition(" ")
        if service in containers:
            raise RuntimeError("service has two containers: %s" % service)
        containers[service] = cid
    missing = sorted(set(required) - set(containers))
    if missing:
        raise RuntimeError("required services have no container: %s" % missing)
    return containers


def run(root: Path, containers: dict, start_epoch: float, duration: float, interval: float, clock=time.time,
        sleep=time.sleep) -> list:
    samples, k = [], 0
    while k * interval <= duration:
        target = start_epoch + k * interval
        sleep(max(0.0, target - clock()))
        row = sample(root, containers, target)
        row["lateSeconds"] = round(clock() - target, 3)
        samples.append(row)
        k += 1
    return samples


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True)
    p.add_argument("--duration", type=float, required=True)
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--start-at-epoch", type=float, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--require-service", action="append", default=[])
    a = p.parse_args(argv)
    containers = resolve(a.project, a.require_service)
    samples = run(CGROUP, containers, a.start_at_epoch, a.duration, a.interval)
    missing_at_start = sorted(s for s in a.require_service if samples[0]["services"].get(s) is None)
    doc = {"schemaVersion": 1, "kind": KIND, "project": a.project, "intervalSeconds": a.interval,
           "durationSeconds": a.duration, "startAtEpoch": a.start_at_epoch, "containers": containers,
           "requiredServices": sorted(a.require_service), "requiredMissingAtStart": missing_at_start, "samples": samples}
    with a.output.open("x", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=1, sort_keys=True)
        handle.write("\n")
    return 3 if missing_at_start else 0


if __name__ == "__main__":
    sys.exit(main())
