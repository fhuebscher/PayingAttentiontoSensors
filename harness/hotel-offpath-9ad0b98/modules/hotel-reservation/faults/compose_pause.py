#!/usr/bin/env python3
"""Apply and prove a bounded Compose pause with exception-safe recovery."""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OVERLAY = ROOT / "modules/hotel-reservation/deployment/compose.observability-placement.yml"
ALLOWED = {"search-pause": "search", "reservation-pause": "reservation"}
# hotel-offpath-v1: a pause of a container that is NOT on the request path (consul: services register without
# health checks and the frontend's resolver keeps its existing connections).  Same commands and receipt as an
# on-path pause; only the manifestation rule differs (see inject): the pause must be read back from the container,
# a route outage is recorded (outageObserved) but not required.
OFFPATH_ALLOWED = {"consul-pause": "consul"}
REQUIRED_COMPOSE_ENV = ("HR_FRONTEND_PORT", "HR_JAEGER_QUERY_PORT", "HR_SOURCE_SHA256")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def command(argv: list[str], check: bool = True,
            env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(argv, text=True, capture_output=True, check=False, env=env)
    if check and result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {argv}\n{result.stderr}")
    return result


def compose(source: Path, project: str, *args: str) -> list[str]:
    return ["docker", "compose", "-p", project, "-f", str(source / "docker-compose.obsplacement.yml"),
            "-f", str(OVERLAY), *args]


def container_state(source: Path, project: str, service: str,
                    env: dict[str, str] | None = None) -> dict:
    cid = command(compose(source, project, "ps", "-q", service), env=env).stdout.strip()
    if not cid:
        return {"exists": False, "running": False, "paused": False}
    result = command(["docker", "inspect", cid], check=False)
    if result.returncode:
        return {"exists": False, "running": False, "paused": False,
                "inspectReturnCode": result.returncode}
    state = json.loads(result.stdout)[0]["State"]
    return {"exists": True, "running": bool(state["Running"]),
            "paused": bool(state["Paused"]), "status": state["Status"]}


def route_available(url: str, timeout: float = 5.0) -> bool:
    try:
        with urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        ).open(url, timeout=timeout) as response:
            response.read()
            return response.status == 200
    except OSError:
        return False


def timed_probe(receipt: dict, phase: str, url: str) -> bool:
    """route_available, stamped into receipt["probes"] when the cell asked for probe stamps (sweep epoch).

    The probes are requests the SUT serves inside the measurement; the analysis excludes their windows from
    every sensor's scoring (traffic-sweep declaration).  Without the key the call is exactly route_available.
    """
    if "probes" not in receipt:
        return route_available(url)
    started = time.monotonic()
    available = route_available(url)
    receipt["probes"].append({"phase": phase, "startMonotonic": started,
                              "endMonotonic": time.monotonic(), "available": available})
    return available


def wait_recovered(url: str, timeout: float = 120.0,
                   cancel: threading.Event | None = None) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cancel is not None and cancel.is_set():
            return False
        if route_available(url):
            return True
        if cancel is not None:
            cancel.wait(2)
        else:
            time.sleep(2)
    return False


def validate(scenario: str, fault_at: float, outage: float) -> str:
    if scenario not in ALLOWED and scenario not in OFFPATH_ALLOWED:
        raise ValueError(f"scenario must be one of {sorted(set(ALLOWED) | set(OFFPATH_ALLOWED))}")
    if not math.isfinite(fault_at) or fault_at < 0:
        raise ValueError("fault-at must be finite and non-negative")
    if not math.isfinite(outage) or outage <= 0:
        raise ValueError("outage must be finite and positive")
    return ALLOWED[scenario] if scenario in ALLOWED else OFFPATH_ALLOWED[scenario]


def _write_receipt(output: Path, receipt: dict) -> None:
    payload = json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(output, flags, 0o600)
    except OSError as exc:
        raise RuntimeError(f"cannot create exclusive fault receipt: {exc}") from exc
    try:
        if os.write(descriptor, payload) != len(payload):
            raise RuntimeError("short write to fault receipt")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def inject(source: Path, project: str, scenario: str, fault_at: float, outage: float,
           probe_url: str, output: Path, cancel: threading.Event | None = None,
           env: dict[str, str] | None = None, *,
           scheduled_at_seconds: float | None = None,
           start_at_monotonic: float | None = None, record_probes: bool = False) -> dict:
    service = validate(scenario, fault_at, outage)
    scheduled = fault_at if scheduled_at_seconds is None else scheduled_at_seconds
    if not math.isfinite(scheduled) or scheduled < 0:
        raise ValueError("scheduled-at-seconds must be finite and non-negative")
    if start_at_monotonic is not None and (
        not math.isfinite(start_at_monotonic) or start_at_monotonic <= 0
    ):
        raise ValueError("start-at-monotonic must be finite and positive")
    effective_env = dict(os.environ if env is None else env)
    missing = [name for name in REQUIRED_COMPOSE_ENV if not effective_env.get(name)]
    if missing:
        raise ValueError(f"fault adapter lacks required Compose environment: {missing}")
    receipt = {"schemaVersion": 1, "faultKind": "pause", "scenario": scenario, "targetService": service,
               "scheduledAtSeconds": scheduled, "requestedOutageSeconds": outage,
               "startedAt": None, "endedAt": None, "manifested": False,
               "outageObserved": False, "recovered": False, "successful": False,
               "preState": None, "preRouteAvailable": False,
               "duringState": None, "recoveryState": None,
               "startedMonotonic": None, "appliedMonotonic": None,
               "revertingMonotonic": None, "unpausedAtMonotonic": None,
               "readyAtMonotonic": None, "endedMonotonic": None,
               "commands": [], "error": None}
    if record_probes:
        receipt["probes"] = []
    paused = False
    began: float | None = None
    try:
        if start_at_monotonic is not None:
            remaining = max(0.0, start_at_monotonic - time.monotonic())
            if cancel is not None and cancel.wait(remaining):
                raise RuntimeError("intervention cancelled before injection")
            if cancel is None and remaining > 0:
                time.sleep(remaining)
        receipt["preState"] = container_state(source, project, service, env=effective_env)
        receipt["preRouteAvailable"] = timed_probe(receipt, "pre", probe_url)
        if (receipt["preState"].get("running") is not True or
                receipt["preState"].get("paused") is not False or
                receipt["preRouteAvailable"] is not True):
            raise RuntimeError("fault precondition is not independently established")
        if start_at_monotonic is None:
            if cancel is not None and cancel.wait(fault_at):
                raise RuntimeError("intervention cancelled before injection")
            if cancel is None:
                time.sleep(fault_at)
        receipt["startedAt"] = now()
        began = time.monotonic()
        receipt["startedMonotonic"] = began
        result = command(compose(source, project, "pause", service), check=False, env=effective_env)
        receipt["commands"].append({"action": "pause", "returnCode": result.returncode,
                                    "stdout": result.stdout, "stderr": result.stderr})
        receipt["duringState"] = container_state(source, project, service, env=effective_env)
        paused = bool(receipt["duringState"]["paused"])
        # LMT+S pilot: detection-window edges inside the fault (after the pause is
        # observed, before the unpause command), beside the harness's own phase stamps.
        receipt["appliedMonotonic"] = time.monotonic()
        receipt["outageObserved"] = not timed_probe(receipt, "during", probe_url)
        # On-path pause: manifested needs the route outage as well.  Off-path pause: the container read back as
        # paused is the manifestation; the outage is recorded, never required (the terminal validator adds the
        # independent leg, the docker pause/unpause events on the target).
        receipt["manifested"] = paused if scenario in OFFPATH_ALLOWED else (paused and receipt["outageObserved"])
        # The hold is measured from the pause itself, so the during-probe's own
        # duration (up to its 5 s timeout) is not added on top of it. Hotel
        # campaign #1 cell 9 held 20.4 s for a requested 15 s that way (D21).
        remaining = max(0.0, outage - (time.monotonic() - began))
        if cancel is not None and cancel.wait(remaining):
            raise RuntimeError("intervention cancelled during outage")
        if cancel is None:
            time.sleep(remaining)
        receipt["revertingMonotonic"] = time.monotonic()
        result = command(compose(source, project, "unpause", service), check=False, env=effective_env)
        receipt["commands"].append({"action": "unpause", "returnCode": result.returncode,
                                    "stdout": result.stdout, "stderr": result.stderr})
        paused = paused and result.returncode != 0
        receipt["unpausedAtMonotonic"] = time.monotonic()
        receipt["actualOutageSeconds"] = receipt["unpausedAtMonotonic"] - began
        receipt["recovered"] = wait_recovered(probe_url, cancel=cancel)
        if receipt["recovered"]:
            receipt["readyAtMonotonic"] = time.monotonic()
        receipt["recoveryState"] = container_state(source, project, service, env=effective_env)
    except Exception as exc:  # retain exact intervention failure in evidence
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if paused or receipt["error"] is not None:
            result = command(compose(source, project, "unpause", service), check=False,
                             env=effective_env)
            receipt["commands"].append({"action": "unpause-finally", "returnCode": result.returncode,
                                        "stdout": result.stdout, "stderr": result.stderr})
            if result.returncode == 0:
                if receipt["unpausedAtMonotonic"] is None:
                    receipt["unpausedAtMonotonic"] = time.monotonic()
                receipt["recovered"] = wait_recovered(
                    probe_url, timeout=30.0 if cancel is not None and cancel.is_set() else 120.0)
                if receipt["recovered"]:
                    receipt["readyAtMonotonic"] = time.monotonic()
                receipt["recoveryState"] = container_state(
                    source, project, service, env=effective_env)
        if began is not None and "actualOutageSeconds" not in receipt:
            receipt["actualOutageSeconds"] = time.monotonic() - began
        receipt["endedAt"] = now()
        receipt["endedMonotonic"] = time.monotonic()
        receipt["successful"] = (
            receipt["preRouteAvailable"] and receipt["manifested"] and receipt["recovered"] and
            receipt["startedMonotonic"] < receipt["unpausedAtMonotonic"] <= receipt["readyAtMonotonic"] and
            receipt.get("actualOutageSeconds", 0) >= outage and receipt["error"] is None and
            all(item["returnCode"] == 0 for item in receipt["commands"])
        )
        _write_receipt(output, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--fault-at", required=True, type=float)
    parser.add_argument("--outage", required=True, type=float)
    parser.add_argument("--probe-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        validate(args.scenario, args.fault_at, args.outage)
    except ValueError as exc:
        parser.error(str(exc))
    return 0 if inject(args.source, args.project, args.scenario, args.fault_at,
                       args.outage, args.probe_url, args.output)["successful"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
