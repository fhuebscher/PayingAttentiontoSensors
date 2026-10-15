#!/usr/bin/env python3
"""Run resumable randomized OTel source-off/full blocks with a recovery fault."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import stat
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROJECT = os.environ.get("OBSPLACEMENT_COMPOSE_PROJECT", "")
PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
POSTURES = frozenset({"source-off", "full"})
APP_SERVICES = ("frontendproxy", "frontend", "recommendationservice")
# The pinned 1.12.0 release has no published flagd-ui image.  A clean host
# therefore has to build this upstream service as well as the three images
# containing placement modifications.  Keeping the list explicit preserves
# --no-build as a meaningful lifecycle/provenance gate.
BUILD_SERVICES = (*APP_SERVICES, "flagd-ui")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha256(root: Path) -> str:
    """Recompute the materializer's content-and-mode digest."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"materialized source contains a symlink: {path}")
        if path.is_file() and ".git" not in path.parts and path.name != ".source.sha256":
            relative = str(path.relative_to(root)).encode()
            payload = path.read_bytes()
            digest.update(len(relative).to_bytes(8, "big")); digest.update(relative)
            digest.update(stat.S_IMODE(path.stat().st_mode).to_bytes(4, "big"))
            digest.update(len(payload).to_bytes(8, "big")); digest.update(payload)
    return digest.hexdigest()


def upstream_sha() -> str:
    checkout = ROOT / "upstream/opentelemetry-demo"
    if checkout.exists():
        return command(["git", "-C", str(checkout), "rev-parse", "HEAD"]).stdout.strip()
    lock = ROOT / "modules/otel-demo/source.lock"
    match = re.search(r"^commit:\s*([0-9a-f]{40})$", lock.read_text(), re.MULTILINE)
    if not match:
        raise RuntimeError(f"pinned OTel commit missing from {lock}")
    return match.group(1)


def materialized_source_proof(source: Path) -> dict:
    if source.is_symlink():
        raise RuntimeError("materialized OTel source may not be a symlink")
    sentinel = source / ".obsplacement-materialized"
    digest_path = source / ".source.sha256"
    if not sentinel.is_file() or not digest_path.is_file():
        raise RuntimeError("materialized OTel source proof is incomplete")
    proof = json.loads(sentinel.read_text())
    expected = digest_path.read_text().strip()
    actual = tree_sha256(source)
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or expected != actual:
        raise RuntimeError(f"materialized OTel source digest mismatch: expected {expected}, found {actual}")
    pinned = upstream_sha()
    if proof.get("upstreamSha") != pinned:
        raise RuntimeError("materialized OTel source is not bound to the pinned upstream commit")
    return {
        "upstreamSha": pinned,
        "materializedSourceSha256": actual,
        "materializationProofSha256": sha256(sentinel),
    }


def parse_postures(value: str) -> tuple[str, ...]:
    result = tuple(value.split(","))
    if not result or len(result) != len(set(result)) or any(p not in POSTURES for p in result):
        raise ValueError(f"postures must be unique values from {sorted(POSTURES)}")
    return result


def validate(args: argparse.Namespace) -> tuple[str, ...]:
    postures = parse_postures(args.postures)
    if not PROJECT_RE.fullmatch(PROJECT):
        raise ValueError("OBSPLACEMENT_COMPOSE_PROJECT must be a safe, bounded Compose project name")
    if (not isinstance(args.blocks, int) or isinstance(args.blocks, bool) or
            not 1 <= args.blocks <= 100 or
            not isinstance(args.concurrency, int) or isinstance(args.concurrency, bool) or
            not 1 <= args.concurrency <= 1024 or
            not isinstance(args.seed, int) or isinstance(args.seed, bool) or args.seed < 0):
        raise ValueError("blocks, concurrency, and seed are outside bounded integer ranges")
    numeric = (args.duration, args.warmup, args.rate, args.fault_at, args.outage)
    if any(not math.isfinite(value) for value in numeric):
        raise ValueError("campaign numeric parameters must be finite")
    if (not 0 < args.duration <= 86400 or not 0 <= args.warmup <= 86400 or
            not 0 < args.rate <= 10000 or args.duration * args.rate > 1_000_000):
        raise ValueError("duration, warmup, rate, or offered-request bound is invalid")
    if args.fault_at < 0 or args.outage <= 0 or args.fault_at + args.outage >= args.duration:
        raise ValueError("fault and recovery must fit strictly inside the measurement window")
    if not isinstance(args.url, str) or not args.url.startswith(("http://", "https://")):
        raise ValueError("measured URL must be HTTP(S)")
    return postures


def command(argv: list[str], *, output: Path | None = None, check: bool = True,
            env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(argv, text=True, capture_output=True, check=False, env=env)
    if output:
        output.write_text(result.stdout + ("\nSTDERR\n" + result.stderr if result.stderr else ""))
    if check and result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {argv}\n{result.stderr}")
    return result


def compose(source: Path, *args: str) -> list[str]:
    return ["docker", "compose", "-p", PROJECT, "-f", str(source / "docker-compose.obsplacement.yml"),
            "-f", str(ROOT / "modules/otel-demo/deployment/compose.otel-placement.yml"), *args]


def project_resources() -> dict[str, list[str]]:
    def ids(argv: list[str]) -> list[str]:
        return sorted(line for line in command(argv, check=False).stdout.splitlines() if line)
    label = f"label=com.docker.compose.project={PROJECT}"
    return {
        "containers": ids(["docker", "ps", "-aq", "--filter", label]),
        "networks": ids(["docker", "network", "ls", "-q", "--filter", label]),
        "volumes": ids(["docker", "volume", "ls", "-q", "--filter", label]),
    }


def posture_env(posture: str, source: Path) -> dict[str, str]:
    enabled = "true" if posture == "full" else "false"
    source_digest = (source / ".source.sha256").read_text().strip()
    config = source / "src/frontendproxy" / ("envoy.tmpl.yaml" if posture == "full" else "envoy.no-tracing.tmpl.yaml")
    return {**os.environ, "DEMO_VERSION": "1.12.0",
            "OTEL_IMAGE_TAG": f"1.12.0-{source_digest[:16]}",
            "OTEL_PLACEMENT_ENABLED": enabled,
            "OTEL_PLACEMENT_DISABLED": "false" if posture == "full" else "true",
            "OTEL_ENVOY_CONFIG": str(config),
            "OTEL_COLLECTOR_CONFIG": str(source / "src/otelcollector/otelcol-placement.yml"),
            "OTEL_COLLECTOR_CONFIG_EXTRAS": str(source / "src/otelcollector/otelcol-config-extras.yml")}


def wait_ready(url: str, timeout: int = 300,
               cancel: threading.Event | None = None) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cancel is not None and cancel.is_set():
            raise RuntimeError("readiness cancelled")
        result = command(["curl", "-fsS", "--max-time", "10", url], check=False)
        if result.returncode == 0 and len(result.stdout.encode()) > 1000:
            return
        if cancel is not None:
            cancel.wait(5)
        else:
            time.sleep(5)
    raise RuntimeError(f"frontend readiness failed: {url}")


def container_id(source: Path, service: str, env: dict[str, str]) -> str:
    identifiers = [value for value in
                   command(compose(source, "ps", "-q", service), env=env).stdout.splitlines()
                   if value]
    if len(identifiers) != 1:
        raise RuntimeError(f"expected exactly one {service} container, found {identifiers}")
    return identifiers[0]


def image_receipt(source: Path, env: dict[str, str]) -> dict:
    rendered = json.loads(command(
        compose(source, "config", "--format", "json"), env=env).stdout)
    services = rendered.get("services", {})
    result = {}
    for service in BUILD_SERVICES:
        tag = services.get(service, {}).get("image")
        if not isinstance(tag, str) or not tag or tag.endswith(":latest"):
            raise RuntimeError(f"{service} build has no immutable experiment tag")
        inspected = json.loads(command(["docker", "image", "inspect", tag]).stdout)[0]
        image_id = inspected.get("Id")
        if not isinstance(image_id, str) or not image_id.startswith("sha256:"):
            raise RuntimeError(f"{service} build lacks an immutable image ID")
        result[service] = {"tag": tag, "imageId": image_id,
                           "repoDigests": sorted(inspected.get("RepoDigests") or [])}
    return result


def build_once(root: Path, source: Path, env: dict[str, str], source_proof: dict) -> dict:
    path = root / "build.json"
    if path.exists():
        recorded = json.loads(path.read_text())
        current = image_receipt(source, env)
        if (recorded.get("materializedSourceSha256") !=
                source_proof["materializedSourceSha256"] or recorded.get("images") != current):
            raise RuntimeError("refusing resume: one-time build no longer matches source/images")
        return recorded
    command(compose(source, "config"), env=env, output=root / "compose-rendered.yml")
    command(compose(source, "build", *BUILD_SERVICES),
            output=root / "build.log", env=env)
    receipt = {
        "schemaVersion": 1,
        "builtAt": now(),
        "buildCount": 1,
        "materializedSourceSha256": source_proof["materializedSourceSha256"],
        "images": image_receipt(source, env),
    }
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def posture_proof(source: Path, posture: str, env: dict[str, str], build: dict) -> dict:
    expected_source_digest = (source / ".source.sha256").read_text().strip()
    proof = {"requested": posture, "expectedMaterializedSourceSha256": expected_source_digest,
             "imageTag": env["OTEL_IMAGE_TAG"], "services": {}}
    for service in APP_SERVICES:
        cid = container_id(source, service, env)
        inspected = json.loads(command(["docker", "inspect", cid]).stdout)[0]
        variables = dict(item.split("=", 1) for item in inspected["Config"]["Env"] if "=" in item)
        embedded_source = None
        if service in {"frontend", "recommendationservice"}:
            result = command(["docker", "exec", cid, "cat", "/obsplacement-source.sha256"], check=False)
            embedded_source = result.stdout.strip() if result.returncode == 0 else None
        proof["services"][service] = {
            "containerId": cid,
            "imageId": inspected["Image"],
            "expectedImageId": build["images"][service]["imageId"],
            "otelSdkDisabled": variables.get("OTEL_SDK_DISABLED"),
            "otelPlacementEnabled": variables.get("OTEL_PLACEMENT_ENABLED"),
            "configSource": next((mount["Source"] for mount in inspected["Mounts"]
                                  if mount["Destination"] == "/home/envoy/envoy.tmpl.yaml"), None),
            "embeddedMaterializedSourceSha256": embedded_source,
        }
    proxy = proof["services"]["frontendproxy"]
    source_path = proxy["configSource"]
    proxy["envoyTracingConfigured"] = bool(source_path and "                tracing:\n" in
                                            Path(source_path).read_text(encoding="utf-8"))
    return proof


def cpu_percent(value: str) -> float:
    return float(value.removesuffix("%"))


def trace_export_stats(log: str) -> dict:
    spans = [int(value) for value in re.findall(r'TracesExporter.*?"spans":\s*(\d+)', log)]
    return {"batches": len(spans), "spans": sum(spans)}


def sample_resources(source: Path, env: dict[str, str], stop: threading.Event,
                     output: Path, interval: float = 2.0) -> None:
    ids = {service: container_id(source, service, env) for service in (*APP_SERVICES, "otelcol")}
    samples = []
    while not stop.is_set():
        captured = now()
        for service, cid in ids.items():
            result = command(["docker", "stats", "--no-stream", "--format", "{{json .}}", cid], check=False)
            if result.returncode == 0 and result.stdout.strip():
                row = json.loads(result.stdout)
                samples.append({"capturedAt": captured, "service": service,
                                "cpuPercent": cpu_percent(row["CPUPerc"]),
                                "memoryUsage": row.get("MemUsage")})
        stop.wait(interval)
    summary = {}
    for service in ids:
        values = [row["cpuPercent"] for row in samples if row["service"] == service]
        summary[service] = {"samples": len(values),
                            "meanCpuPercent": round(sum(values) / len(values), 4) if values else None,
                            "maxCpuPercent": max(values) if values else None}
    output.write_text(json.dumps({"intervalSeconds": interval, "samples": samples,
                                  "summary": summary}, indent=2, sort_keys=True) + "\n")


def inject_fault(source: Path, env: dict[str, str], fault_at: int, outage: int,
                 url: str, cancel: threading.Event, output: Path) -> dict:
    receipt = {"scenario": "frontend-pause", "scheduledAtSeconds": fault_at,
               "outageSeconds": outage, "startedAt": None, "endedAt": None,
               "manifested": False, "outageObserved": False, "recovered": False,
               "commands": [], "error": None}
    paused = False
    try:
        if cancel.wait(fault_at):
            raise RuntimeError("intervention cancelled before injection")
        receipt["startedAt"] = now()
        began = time.monotonic()
        result = command(compose(source, "pause", "frontend"), check=False, env=env)
        receipt["commands"].append({"action": "pause", "returnCode": result.returncode,
                                    "stdout": result.stdout, "stderr": result.stderr})
        state = json.loads(command(["docker", "inspect", container_id(source, "frontend", env)]).stdout)[0]["State"]
        paused = bool(state["Paused"])
        probe = command(["curl", "-fsS", "--max-time", "5", url], check=False)
        receipt["outageProbe"] = {"returnCode": probe.returncode,
                                  "stdoutBytes": len(probe.stdout.encode()), "stderr": probe.stderr}
        receipt["outageObserved"] = probe.returncode != 0
        receipt["manifested"] = paused and receipt["outageObserved"]
        if cancel.wait(outage):
            raise RuntimeError("intervention cancelled during outage")
        result = command(compose(source, "unpause", "frontend"), check=False, env=env)
        receipt["commands"].append({"action": "unpause", "returnCode": result.returncode,
                                    "stdout": result.stdout, "stderr": result.stderr})
        paused = False if result.returncode == 0 else paused
        receipt["actualOutageSeconds"] = time.monotonic() - began
        wait_ready(url, cancel=cancel)
        receipt["recovered"] = True
    except Exception as exc:  # retain exact failure in evidence
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if paused:
            result = command(compose(source, "unpause", "frontend"), check=False, env=env)
            receipt["commands"].append({"action": "unpause-finally", "returnCode": result.returncode,
                                        "stdout": result.stdout, "stderr": result.stderr})
    receipt["endedAt"] = now()
    receipt["successful"] = (receipt["manifested"] and receipt["recovered"] and
                             receipt.get("actualOutageSeconds", 0) >= outage and
                             receipt["error"] is None and
                             all(item["returnCode"] == 0 for item in receipt["commands"]))
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def run_one(root: Path, run_id: str, posture: str, args: argparse.Namespace,
            build: dict, source_proof: dict) -> dict:
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    source = args.source.resolve()
    env = posture_env(posture, source)
    existing = project_resources()
    (run_dir / "ownership-preflight.json").write_text(
        json.dumps(existing, indent=2, sort_keys=True) + "\n"
    )
    if any(existing.values()):
        raise RuntimeError(f"refusing to mutate pre-existing Compose project {PROJECT}: {existing}")
    owns_project = False
    cancel = threading.Event()
    resource_stop = threading.Event()
    resource_thread: threading.Thread | None = None
    fault_thread: threading.Thread | None = None
    try:
        owns_project = True
        command(compose(source, "up", "-d", "--no-build"), output=run_dir / "up.log", env=env)
        wait_ready(args.url)
        proof = posture_proof(source, posture, env, build)
        (run_dir / "posture-proof.json").write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
        if args.warmup:
            command(["python3", str(ROOT / "modules/otel-demo/workload.py"), "--url", args.url,
                     "--rate", str(args.rate), "--duration", str(args.warmup), "--concurrency",
                     str(args.concurrency), "--output", str(run_dir / "warmup.json")])
        fault_result: dict = {}
        resource_thread = threading.Thread(target=sample_resources,
            args=(source, env, resource_stop, run_dir / "resources.json"), daemon=True)
        resource_thread.start()
        fault_thread = threading.Thread(target=lambda: fault_result.update(inject_fault(
            source, env, args.fault_at, args.outage, args.url, cancel,
            run_dir / "intervention.json")), daemon=True)
        fault_thread.start()
        command(["python3", str(ROOT / "modules/otel-demo/workload.py"), "--url", args.url,
                 "--rate", str(args.rate), "--duration", str(args.duration), "--concurrency",
                 str(args.concurrency), "--output", str(run_dir / "workload.json")], check=False)
        fault_thread.join(timeout=args.duration + args.outage + 300)
        resource_stop.set()
        resource_thread.join(timeout=30)
        workload = json.loads((run_dir / "workload.json").read_text())
        resources = json.loads((run_dir / "resources.json").read_text())
        logs = command(compose(source, "logs", "--no-color", "otelcol"), check=False, env=env)
        (run_dir / "otelcol.log").write_text(logs.stdout + logs.stderr)
        trace_stats = trace_export_stats(logs.stdout)
        blockers = []
        expected_disabled = "false" if posture == "full" else "true"
        expected_enabled = "true" if posture == "full" else "false"
        for service, item in proof["services"].items():
            if service != "frontendproxy" and (item["otelSdkDisabled"] != expected_disabled or
                                                item["otelPlacementEnabled"] != expected_enabled):
                blockers.append(f"{service} source posture mismatch")
            if item["imageId"] != item["expectedImageId"]:
                blockers.append(f"{service} image differs from the one-time build")
            if service in {"frontend", "recommendationservice"} and (
                    item["embeddedMaterializedSourceSha256"] !=
                    proof["expectedMaterializedSourceSha256"]):
                blockers.append(f"{service} image is not bound to materialized source")
        proxy = proof["services"]["frontendproxy"]
        if posture == "source-off" and (not proxy["configSource"] or
                not proxy["configSource"].endswith("envoy.no-tracing.tmpl.yaml") or
                proxy["envoyTracingConfigured"]):
            blockers.append("frontendproxy source posture mismatch")
        if posture == "full" and not proxy["envoyTracingConfigured"]:
            blockers.append("frontendproxy full tracing configuration missing")
        if fault_thread.is_alive() or not fault_result.get("successful"):
            blockers.append("frontend fault manifestation/recovery not proven")
        if trace_stats["spans"] == 0:
            blockers.append("collector exported no spans")
        receipt = {"schemaVersion": 1, "runId": run_id, "sut": "otel-demo", "posture": posture,
                   "controlQualification": {
                       "level": "sdk-and-proxy-disabled-target-path",
                       "sourceWorkDisabled": False,
                       "limitations": [
                           "frontend application code can still call no-op OpenTelemetry APIs",
                           "recommendation process still starts through opentelemetry-instrument",
                           "non-target demo services remain instrumented",
                       ],
                   },
                   "source": {**source_proof,
                              "composeOverrideSha256": sha256(ROOT / "modules/otel-demo/deployment/compose.otel-placement.yml")},
                   "images": build["images"],
                   "workload": {key: workload[key] for key in
                                ("url", "offered", "completed", "failed", "concurrency")},
                   "latencyMs": workload["latencyMs"], "resources": resources["summary"],
                   "telemetry": {"traceExportBatches": trace_stats["batches"],
                                 "exportedSpans": trace_stats["spans"],
                   "collectorLogBytes": len(logs.stdout.encode())}, "postureProof": proof,
                   "intervention": fault_result or None,
                   "canonicality": {"label": "noncanonical-control-smoke" if not blockers else "noncanonical",
                                    "blockers": blockers}}
        (run_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        return receipt
    finally:
        cancel.set()
        resource_stop.set()
        if fault_thread is not None:
            fault_thread.join(timeout=30)
        if resource_thread is not None:
            resource_thread.join(timeout=30)
        if owns_project:
            command(compose(source, "down", "--remove-orphans"), output=run_dir / "down-after.log", check=False, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=ROOT / ".local/otel-demo")
    parser.add_argument("--blocks", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260808)
    parser.add_argument("--warmup", type=int, default=30)
    parser.add_argument("--duration", type=int, default=120)
    parser.add_argument("--rate", type=float, default=1)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--postures", default="source-off,full")
    parser.add_argument("--fault-at", type=int, default=45)
    parser.add_argument("--outage", type=int, default=15)
    parser.add_argument(
        "--url",
        default=("http://localhost:8080/api/recommendations?"
                 "productIds=OLJCESPC7Z&currencyCode=USD"),
        help="Measured journey URL; the default synchronously invokes recommendationservice",
    )
    args = parser.parse_args()
    try:
        postures = validate(args)
        source = args.source.resolve()
        source_proof = materialized_source_proof(source)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    args.output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    schedule = []
    for block in range(1, args.blocks + 1):
        ordered = list(postures); rng.shuffle(ordered)
        schedule.extend({"block": block, "posture": posture} for posture in ordered)
    configuration = {"schemaVersion": 2, "sut": "otel-demo", "goal": "otel-path-cost",
                     "composeProject": PROJECT,
                     "seed": args.seed, "blocks": args.blocks,
                     "postures": list(postures), "warmupSeconds": args.warmup,
                     "measurementSeconds": args.duration, "requestsPerSecond": args.rate,
                     "concurrency": args.concurrency, "fault": "frontend-pause",
                     "faultAtSeconds": args.fault_at, "outageSeconds": args.outage,
                     "url": args.url, **source_proof,
                     "runnerSha256": sha256(Path(__file__)),
                     "composeOverrideSha256": sha256(ROOT / "modules/otel-demo/deployment/compose.otel-placement.yml"),
                     "goalSha256": sha256(ROOT / "modules/otel-demo/goal.yaml"),
                     "imageTag": posture_env(postures[0], source)["OTEL_IMAGE_TAG"]}
    schedule_doc = {"configuration": configuration, "runs": schedule}
    schedule_path = args.output / "schedule.json"
    if schedule_path.exists():
        if json.loads(schedule_path.read_text()) != schedule_doc:
            raise RuntimeError(f"refusing to resume campaign with changed configuration: {schedule_path}")
    else:
        schedule_path.write_text(json.dumps(schedule_doc, indent=2, sort_keys=True) + "\n")
    build = build_once(args.output, source, posture_env(postures[0], source), source_proof)
    for item in schedule:
        run_id = f"b{item['block']:02d}-{item['posture']}"
        receipt_path = args.output / run_id / "receipt.json"
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            source = receipt.get("source", {})
            expected = {
                "runId": run_id, "posture": item["posture"],
                "upstreamSha": configuration["upstreamSha"],
                "materializedSourceSha256": configuration["materializedSourceSha256"],
                "composeOverrideSha256": configuration["composeOverrideSha256"],
            }
            actual = {
                "runId": receipt.get("runId"), "posture": receipt.get("posture"),
                "upstreamSha": source.get("upstreamSha"),
                "materializedSourceSha256": source.get("materializedSourceSha256"),
                "composeOverrideSha256": source.get("composeOverrideSha256"),
            }
            if actual != expected:
                raise RuntimeError(f"existing receipt differs from immutable schedule: {receipt_path}")
            continue
        if run_one(args.output, run_id, item["posture"], args,
                   build, source_proof)["canonicality"]["blockers"]:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
