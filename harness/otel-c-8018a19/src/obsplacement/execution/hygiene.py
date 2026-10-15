"""Read-only server inventory with explicit ownership classification."""
from __future__ import annotations

import argparse
import json
import subprocess
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


COMMANDS = {
    "host": "hostname; date -u +%FT%TZ; uptime; uname -a",
    "resources": "free -b; df -B1 /; df -i /",
    "docker_version": "docker version --format '{{json .}}'",
    "compose_projects": "docker compose ls --all --format json",
    "containers": "docker ps -a --no-trunc --format '{{json .}}'",
    "networks": "docker network ls --no-trunc --format '{{json .}}'",
    "volumes": "docker volume ls --format '{{json .}}'",
    "ports": "ss -lntup 2>/dev/null || true",
    "tmux_root": "tmux ls 2>/dev/null || true",
    "tmux_experiment": "su - stig -c 'tmux ls' 2>/dev/null || true",
    "processes": "ps -eo user,pid,ppid,lstart,etime,cmd --sort=start_time",
    "writers": "lsof +D /home/stig/teastore/data/experiments 2>/dev/null || true",
}
SSH_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")


@dataclass(frozen=True)
class Result:
    stdout: str
    stderr: str
    returncode: int


def run_remote(target: str, command: str) -> Result:
    if not SSH_TARGET.fullmatch(target) or target in {".", ".."}:
        raise ValueError(f"unsafe SSH target: {target!r}")
    proc = subprocess.run(
        ["ssh", "--", target, command], text=True, capture_output=True, check=False
    )
    return Result(proc.stdout, proc.stderr, proc.returncode)


def json_lines(value: str) -> list[dict]:
    rows = []
    for line in value.splitlines():
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def classify(containers: list[dict], allowed_legacy: set[str], desired: str) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    blockers: list[str] = []
    for container in containers:
        labels_text = str(container.get("Labels", ""))
        labels = {}
        for item in labels_text.split(","):
            if "=" in item:
                key, value = item.split("=", 1)
                labels[key] = value
        project = labels.get("com.docker.compose.project", "")
        state = str(container.get("State", ""))
        if project == desired:
            ownership = "owned-current"
        elif project in allowed_legacy:
            ownership = "owned-legacy"
        elif project:
            ownership = "foreign"
        else:
            ownership = "unknown"
        row = {
            "id": container.get("ID"), "name": container.get("Names"),
            "project": project or None, "state": state, "ownership": ownership,
        }
        rows.append(row)
        if state == "running" and ownership in {"foreign", "unknown"}:
            blockers.append(f"running {ownership} container {row['name']}")
    return rows, blockers


def inventory(target: str, allowed_legacy: set[str], desired: str) -> dict:
    captured = datetime.now(timezone.utc).isoformat()
    raw = {name: run_remote(target, command) for name, command in COMMANDS.items()}
    errors = [name for name, result in raw.items() if result.returncode != 0]
    containers = json_lines(raw["containers"].stdout)
    classifications, blockers = classify(containers, allowed_legacy, desired)
    running_legacy = [r for r in classifications if r["state"] == "running" and r["ownership"] == "owned-legacy"]
    if running_legacy:
        blockers.append(f"{len(running_legacy)} approved legacy containers still running")
    if raw["writers"].stdout.strip():
        blockers.append("experiment result directory has open writers")
    if errors:
        blockers.append(f"inventory commands failed: {errors}")
    return {
        "schemaVersion": 1,
        "target": target,
        "capturedAt": captured,
        "policy": {"desiredProject": desired, "allowedLegacyProjects": sorted(allowed_legacy)},
        "inventory": {
            name: {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
            for name, result in raw.items()
        },
        "classifications": classifications,
        "verdict": "inventory-error" if errors else ("blocked" if blockers else "pass"),
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--desired-project", required=True)
    parser.add_argument("--allow-legacy", action="append", default=[])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = inventory(args.target, set(args.allow_legacy), args.desired_project)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "blockers": report["blockers"]}, indent=2))
    return 0 if report["verdict"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
