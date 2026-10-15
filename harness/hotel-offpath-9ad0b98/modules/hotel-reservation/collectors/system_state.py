#!/usr/bin/env python3
"""LMT+S pilot system collector: always on, identical in every posture.

- ``cost_edges``: cumulative cgroup-v2 CPU (``cpu.stat usage_usec``) of the ten application
  containers plus ``docker.service`` and ``containerd.service``, read once at each window edge.
  The daemon-side cgroups carry the cost of json-file logging and docker-stats sampling that a
  per-container reading cannot see.
- ``SystemSampler``: every 5 s, per application container: CPU usage, ``memory.current``,
  ``io.stat`` bytes and PSI ``some total`` for cpu, memory and io.
- ``EventStream``: ``docker events`` for the cell's own Compose project, JSON lines.
- ``tcp_snapshot``: established TCP peers per application container (``ss`` in its netns), with
  the container IP map, so a service graph can be read without traces.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

CGROUP = Path("/sys/fs/cgroup")
DAEMON_UNITS = ("docker.service", "containerd.service")
SAMPLE_INTERVAL_SECONDS = 5.0


class SystemError_(RuntimeError):
    """A system reading could not be taken; the cell is invalid, never zero-filled."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _container_cgroup(cid: str) -> Path:
    path = CGROUP / "system.slice" / f"docker-{cid}.scope"
    if not path.is_dir():
        raise SystemError_(f"container cgroup is missing: {cid[:12]}")
    return path


def _kv(path: Path) -> dict:
    rows = {}
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) == 2:
            rows[parts[0]] = int(parts[1])
    return rows


def _usage_usec(path: Path) -> int:
    return _kv(path / "cpu.stat")["usage_usec"]


def _io_bytes(path: Path) -> dict:
    read = write = 0
    for line in (path / "io.stat").read_text().splitlines():
        for field in line.split()[1:]:
            key, _, value = field.partition("=")
            if key == "rbytes":
                read += int(value)
            elif key == "wbytes":
                write += int(value)
    return {"rbytes": read, "wbytes": write}


def _psi_some_total(path: Path, resource: str) -> int | None:
    target = path / f"{resource}.pressure"
    if not target.is_file():
        return None
    for line in target.read_text().splitlines():
        if line.startswith("some "):
            for field in line.split()[1:]:
                key, _, value = field.partition("=")
                if key == "total":
                    return int(value)
    return None


def cost_edges(identities: dict, label: str) -> dict:
    """One reading of every cost cgroup; ``identities`` maps container id -> service."""
    containers = {service: _usage_usec(_container_cgroup(cid)) for cid, service in identities.items()}
    daemons = {unit: _usage_usec(CGROUP / "system.slice" / unit) for unit in DAEMON_UNITS}
    return {"label": label, "at": _now(), "monotonic": time.monotonic(),
            "containersUsageUsec": containers, "daemonsUsageUsec": daemons}


def cost_document(start: dict, end: dict) -> dict:
    if set(start["containersUsageUsec"]) != set(end["containersUsageUsec"]):
        raise SystemError_("cost edges cover different containers")
    delta_c = {s: end["containersUsageUsec"][s] - start["containersUsageUsec"][s] for s in start["containersUsageUsec"]}
    delta_d = {u: end["daemonsUsageUsec"][u] - start["daemonsUsageUsec"][u] for u in DAEMON_UNITS}
    if any(v < 0 for v in list(delta_c.values()) + list(delta_d.values())):
        raise SystemError_("a cumulative CPU counter decreased inside the window")
    return {"schemaVersion": 1, "kind": "hotel-lmt-cost-cgroup-v1", "start": start, "end": end,
            "windowSeconds": end["monotonic"] - start["monotonic"],
            "containersCpuSeconds": {s: v / 1e6 for s, v in sorted(delta_c.items())},
            "daemonsCpuSeconds": {u: v / 1e6 for u, v in sorted(delta_d.items())}}


class SystemSampler(threading.Thread):
    def __init__(self, identities: dict, start_monotonic: float, end_monotonic: float):
        super().__init__(daemon=True)
        self.identities, self.start_at, self.end_at = dict(identities), start_monotonic, end_monotonic
        self.samples: list = []
        self.error: str | None = None

    def run(self) -> None:
        try:
            paths = {service: _container_cgroup(cid) for cid, service in self.identities.items()}
            tick = self.start_at
            while tick <= self.end_at:
                time.sleep(max(0.0, tick - time.monotonic()))
                row = {"monotonic": time.monotonic(), "at": _now(), "services": {}}
                for service, path in sorted(paths.items()):
                    row["services"][service] = {
                        "cpuUsageUsec": _usage_usec(path),
                        "memoryCurrent": int((path / "memory.current").read_text()),
                        **_io_bytes(path),
                        **{f"psi{r.capitalize()}SomeTotalUsec": _psi_some_total(path, r)
                           for r in ("cpu", "memory", "io")},
                    }
                self.samples.append(row)
                tick += SAMPLE_INTERVAL_SECONDS
        except Exception as exc:  # noqa: BLE001 - surfaced by the cell as invalid
            self.error = f"{type(exc).__name__}: {exc}"

    def document(self) -> dict:
        return {"schemaVersion": 1, "kind": "hotel-lmt-system-samples-v1",
                "intervalSeconds": SAMPLE_INTERVAL_SECONDS, "samples": self.samples}


class EventStream:
    def __init__(self, project: str, output: Path):
        self.output = output
        self.handle = output.open("x", encoding="utf-8")
        self.process = subprocess.Popen(
            ["docker", "events", "--filter", f"label=com.docker.compose.project={project}",
             "--format", "{{json .}}"], stdout=self.handle, stderr=subprocess.PIPE, text=True)
        self.startedAt = _now()

    def stop(self) -> dict:
        self.process.terminate()
        try:
            _, stderr = self.process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            _, stderr = self.process.communicate()
        self.handle.close()
        lines = [line for line in self.output.read_text(encoding="utf-8").splitlines() if line.strip()]
        for line in lines:
            json.loads(line)   # every retained row is one JSON event
        return {"schemaVersion": 1, "kind": "hotel-lmt-docker-events-v1", "startedAt": self.startedAt,
                "stoppedAt": _now(), "rows": len(lines), "stderr": (stderr or "")[:2000]}


def _pid(cid: str) -> int:
    out = subprocess.run(["docker", "inspect", "--format", "{{.State.Pid}}", cid],
                         text=True, capture_output=True, check=True, timeout=20).stdout
    return int(out.strip())


def _ip(cid: str) -> list:
    out = subprocess.run(["docker", "inspect", "--format", "{{json .NetworkSettings.Networks}}", cid],
                         text=True, capture_output=True, check=True, timeout=20).stdout
    return sorted(net.get("IPAddress") for net in json.loads(out).values() if net.get("IPAddress"))


def tcp_snapshot(identities: dict, label: str) -> dict:
    rows = {}
    for cid, service in sorted(identities.items(), key=lambda item: item[1]):
        result = subprocess.run(["sudo", "-n", "nsenter", "-t", str(_pid(cid)), "-n", "ss", "-Htn",
                                 "state", "established"], text=True, capture_output=True, timeout=20)
        if result.returncode:
            raise SystemError_(f"TCP snapshot failed for {service}: {result.stderr.strip()[:200]}")
        peers = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                peers.append({"local": parts[-2], "peer": parts[-1]})
        rows[service] = {"ips": _ip(cid), "established": peers}
    return {"label": label, "at": _now(), "monotonic": time.monotonic(), "services": rows}
