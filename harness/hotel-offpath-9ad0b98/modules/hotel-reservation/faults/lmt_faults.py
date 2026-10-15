#!/usr/bin/env python3
"""LMT+S pilot fault adapter: the two pause faults plus two degradations that are not an absence.

``profile-cpu-throttle`` sets the target container's CPU quota (``docker update --cpus``) and
``rate-net-delay`` adds a netem delay qdisc inside the target's network namespace
(``sudo -n nsenter -t <pid> -n tc``).  Both are proven on the container itself, held, and
reverted; the route stays available, so no outage is expected.  Every receipt carries
``appliedMonotonic`` (after the apply command returned and the change was observed) and
``revertingMonotonic`` (before the revert command), so the detection window lies strictly
inside the fault (the F-ADH-085 rule: both edges bounded by the fault itself).
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_pause():
    spec = importlib.util.spec_from_file_location("hotel_lmt_compose_pause", HERE / "compose_pause.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pause = _load_pause()
DEGRADATIONS = {"profile-cpu-throttle": "profile", "rate-net-delay": "rate"}
CPU_THROTTLE_NANOCPUS = 100_000_000   # --cpus 0.1
NET_DELAY = "100ms"


def _container_id(source: Path, project: str, service: str, env: dict) -> str:
    cid = pause.command(pause.compose(source, project, "ps", "-q", service), env=env).stdout.strip()
    if len(cid) != 64:
        raise RuntimeError(f"fault target container identity is missing: {service}")
    return cid


def _nanocpus(cid: str) -> int | None:
    result = pause.command(["docker", "inspect", cid], check=False)
    if result.returncode:
        return None
    return int(json.loads(result.stdout)[0]["HostConfig"].get("NanoCpus") or 0)


def _host_nanocpus() -> int:
    """Every CPU the daemon sees, the most ``--cpus`` accepts.  ``docker update --cpus 0`` is a no-op
    (the daemon skips a zero NanoCPUs, measured on fb14srv4 2026-09-28), so the quota is lifted by
    raising it to the whole host instead of unsetting it."""
    return int(pause.command(["docker", "info", "--format", "{{.NCPU}}"]).stdout.strip()) * 1_000_000_000


def _pid(cid: str) -> int:
    result = pause.command(["docker", "inspect", "--format", "{{.State.Pid}}", cid])
    pid = int(result.stdout.strip())
    if pid <= 0:
        raise RuntimeError("fault target has no running process")
    return pid


def _tc(pid: int, *args: str):
    return pause.command(["sudo", "-n", "nsenter", "-t", str(pid), "-n", "tc", *args], check=False)


def _qdisc(pid: int) -> str:
    result = _tc(pid, "qdisc", "show", "dev", "eth0")
    return result.stdout if result.returncode == 0 else ""


def _apply(scenario: str, cid: str):
    if scenario == "profile-cpu-throttle":
        return ["docker", "update", "--cpus", "0.1", cid]
    return ["sudo", "-n", "nsenter", "-t", str(_pid(cid)), "-n", "tc", "qdisc", "add", "dev", "eth0",
            "root", "netem", "delay", NET_DELAY]


def _revert(scenario: str, cid: str):
    if scenario == "profile-cpu-throttle":
        return ["docker", "update", "--cpus", str(_host_nanocpus() // 1_000_000_000), cid]
    return ["sudo", "-n", "nsenter", "-t", str(_pid(cid)), "-n", "tc", "qdisc", "del", "dev", "eth0", "root"]


def degraded(scenario: str, cid: str) -> bool:
    """True when the degradation is observable on the container, independent of the command's return code."""
    if scenario == "profile-cpu-throttle":
        return _nanocpus(cid) == CPU_THROTTLE_NANOCPUS
    shown = _qdisc(_pid(cid))
    return "netem" in shown and ("delay " + NET_DELAY) in shown


def clean(scenario: str, cid: str) -> bool:
    if scenario == "profile-cpu-throttle":
        return _nanocpus(cid) in (0, _host_nanocpus())   # unset (fresh container) or lifted to the whole host
    return "netem" not in _qdisc(_pid(cid))


def inject(source: Path, project: str, scenario: str, fault_at: float, hold: float,
           probe_url: str, output: Path, cancel: threading.Event | None = None,
           env: dict | None = None, *, scheduled_at_seconds: float | None = None,
           start_at_monotonic: float | None = None, record_probes: bool = False) -> dict:
    if scenario in pause.ALLOWED or scenario in pause.OFFPATH_ALLOWED:
        return pause.inject(source, project, scenario, fault_at, hold, probe_url, output, cancel, env,
                            scheduled_at_seconds=scheduled_at_seconds,
                            start_at_monotonic=start_at_monotonic, record_probes=record_probes)
    if scenario not in DEGRADATIONS:
        raise ValueError(f"scenario must be one of {sorted(set(pause.ALLOWED) | set(pause.OFFPATH_ALLOWED) | set(DEGRADATIONS))}")
    if not math.isfinite(hold) or hold <= 0 or start_at_monotonic is None:
        raise ValueError("degradation needs a positive hold and a monotonic start")
    service = DEGRADATIONS[scenario]
    effective_env = dict(os.environ if env is None else env)
    receipt = {"schemaVersion": 1, "faultKind": "degradation", "scenario": scenario,
               "targetService": service,
               "scheduledAtSeconds": fault_at if scheduled_at_seconds is None else scheduled_at_seconds,
               "requestedHoldSeconds": hold, "startedAt": None, "endedAt": None,
               "manifested": False, "reverted": False, "recovered": False, "successful": False,
               "preClean": False, "preRouteAvailable": False, "routeAvailableDuring": None,
               "startedMonotonic": None, "appliedMonotonic": None, "revertingMonotonic": None,
               "revertedAtMonotonic": None, "readyAtMonotonic": None, "endedMonotonic": None,
               "commands": [], "error": None}
    if record_probes:
        receipt["probes"] = []
    applied = False
    cid = None
    try:
        remaining = max(0.0, start_at_monotonic - time.monotonic())
        if cancel is not None and cancel.wait(remaining):
            raise RuntimeError("intervention cancelled before injection")
        if cancel is None and remaining > 0:
            time.sleep(remaining)
        cid = _container_id(source, project, service, effective_env)
        receipt["preClean"] = clean(scenario, cid)
        receipt["preRouteAvailable"] = pause.timed_probe(receipt, "pre", probe_url)
        if not (receipt["preClean"] and receipt["preRouteAvailable"]):
            raise RuntimeError("fault precondition is not independently established")
        receipt["startedAt"] = pause.now()
        receipt["startedMonotonic"] = time.monotonic()
        result = pause.command(_apply(scenario, cid), check=False)
        receipt["commands"].append({"action": "apply", "returnCode": result.returncode,
                                    "stdout": result.stdout, "stderr": result.stderr})
        applied = result.returncode == 0
        receipt["manifested"] = applied and degraded(scenario, cid)
        receipt["appliedMonotonic"] = time.monotonic()
        receipt["routeAvailableDuring"] = pause.timed_probe(receipt, "during", probe_url)
        remaining = max(0.0, hold - (time.monotonic() - receipt["appliedMonotonic"]))
        if cancel is not None and cancel.wait(remaining):
            raise RuntimeError("intervention cancelled during hold")
        if cancel is None:
            time.sleep(remaining)
        receipt["revertingMonotonic"] = time.monotonic()
        result = pause.command(_revert(scenario, cid), check=False)
        receipt["commands"].append({"action": "revert", "returnCode": result.returncode,
                                    "stdout": result.stdout, "stderr": result.stderr})
        receipt["revertedAtMonotonic"] = time.monotonic()
        receipt["reverted"] = result.returncode == 0 and clean(scenario, cid)
        applied = applied and not receipt["reverted"]
        receipt["actualHoldSeconds"] = receipt["revertingMonotonic"] - receipt["appliedMonotonic"]
        receipt["recovered"] = pause.wait_recovered(probe_url, cancel=cancel)
        if receipt["recovered"]:
            receipt["readyAtMonotonic"] = time.monotonic()
    except Exception as exc:  # retain exact intervention failure in evidence
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if cid is not None and (applied or receipt["error"] is not None):
            try:
                result = pause.command(_revert(scenario, cid), check=False)
                receipt["commands"].append({"action": "revert-finally", "returnCode": result.returncode,
                                            "stdout": result.stdout, "stderr": result.stderr})
                if receipt["revertedAtMonotonic"] is None:
                    receipt["revertedAtMonotonic"] = time.monotonic()
                receipt["reverted"] = clean(scenario, cid)
            except Exception as exc:  # noqa: BLE001 - the container may already be gone
                receipt["commands"].append({"action": "revert-finally", "returnCode": None,
                                            "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"})
        receipt["endedAt"] = pause.now()
        receipt["endedMonotonic"] = time.monotonic()
        edges = (receipt["startedMonotonic"], receipt["appliedMonotonic"], receipt["revertingMonotonic"],
                 receipt["revertedAtMonotonic"], receipt["readyAtMonotonic"])
        receipt["successful"] = bool(
            receipt["preRouteAvailable"] and receipt["manifested"] and receipt["reverted"]
            and receipt["recovered"] and receipt["error"] is None
            and all(value is not None for value in edges)
            and list(edges) == sorted(edges)
            and receipt.get("actualHoldSeconds", 0) >= hold
            and all(item["returnCode"] == 0 for item in receipt["commands"])
        )
        pause._write_receipt(output, receipt)
    return receipt
