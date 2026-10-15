#!/usr/bin/env python3
"""Run an isolated, noncanonical Hotel Reservation functional smoke."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "modules" / "hotel-reservation"
OVERLAY = MODULE / "deployment" / "compose.observability-placement.yml"
SERVICES = ("frontend", "search", "geo", "rate", "reservation", "profile", "jaeger")
APP_SERVICES = ("frontend", "search", "geo", "rate", "reservation", "profile")
PROJECT_RE = re.compile(r"^obsplacement-hotel-[a-z0-9][a-z0-9-]{5,48}$")
UPSTREAM_SHA = "6ecb09706140f8730b5385c08f1386c654c3c526"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_sha256(value: object) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def command(argv: list[str], *, check: bool = True, output: Path = None,
            env: dict = None) -> subprocess.CompletedProcess:
    result = subprocess.run(argv, text=True, capture_output=True, check=False, env=env)
    if output is not None:
        output.write_text(result.stdout + ("\nSTDERR\n" + result.stderr if result.stderr else ""))
    if check and result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {argv}\n{result.stderr}")
    return result


def compose(source: Path, project: str, *args: str) -> list[str]:
    return ["docker", "compose", "-p", project,
            "-f", str(source / "docker-compose.obsplacement.yml"),
            "-f", str(OVERLAY), *args]


def environment(posture: str, frontend_port: int, jaeger_port: int,
                app_image: str | None = None, source_sha256: str | None = None) -> dict:
    values = {**os.environ, "HR_JAEGER_SAMPLE_RATIO": "1" if posture == "full" else "0",
            "HR_JAEGER_DISABLED": "true" if posture == "none" else "false",
            # The overlay reads frontend's tracer from its own pair (candidate `selected`); smoke keeps it uniform.
            "HR_FRONTEND_JAEGER_SAMPLE_RATIO": "1" if posture == "full" else "0",
            "HR_FRONTEND_JAEGER_DISABLED": "true" if posture == "none" else "false",
            "HR_FRONTEND_PORT": str(frontend_port),
            "HR_JAEGER_QUERY_PORT": str(jaeger_port)}
    if app_image:
        values["HR_APP_IMAGE"] = app_image
    if source_sha256:
        values["HR_SOURCE_SHA256"] = source_sha256
    return values


def validate(source: Path, output: Path, project: str, frontend_port: int,
             jaeger_port: int, rate: float, duration: float, concurrency: int,
             fault_at: float, outage: float, blocks: int = 1, seed: int = 0,
             warmup: float = 5.0) -> dict:
    if not PROJECT_RE.fullmatch(project):
        raise ValueError("project must be a fresh obsplacement-hotel-* namespace")
    if not all(isinstance(port, int) and not isinstance(port, bool) and 1024 <= port <= 65535
               for port in (frontend_port, jaeger_port)) or frontend_port == jaeger_port:
        raise ValueError("frontend and Jaeger ports must be distinct integers from 1024 through 65535")
    finite = (rate, duration, fault_at, outage, warmup)
    if (any(not math.isfinite(value) for value in finite) or
            not 0 < rate <= 10000 or not 0 < duration <= 86400 or
            rate * duration > 1_000_000):
        raise ValueError("rate/duration/fault parameters must be finite; rate and duration positive")
    if not isinstance(concurrency, int) or isinstance(concurrency, bool) or not 1 <= concurrency <= 128:
        raise ValueError("concurrency must be an integer from 1 through 128")
    if not isinstance(blocks, int) or isinstance(blocks, bool) or not 1 <= blocks <= 100:
        raise ValueError("blocks must be an integer from 1 through 100")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if not 0 < warmup <= 3600:
        raise ValueError("warmup must be finite and in (0, 3600] seconds")
    if fault_at < 0 or outage <= 0 or fault_at + outage >= duration:
        raise ValueError("fault and recovery must fit strictly within the measurement window")
    if output.exists():
        raise ValueError(f"output must not already exist: {output}")
    proof_path = source / ".obsplacement-materialized"
    digest_path = source / ".source.sha256"
    generated = source / "docker-compose.obsplacement.yml"
    if source.is_symlink() or not proof_path.is_file() or not digest_path.is_file() or not generated.is_file():
        raise ValueError("materialized source proof and isolated Compose file are required")
    proof = json.loads(proof_path.read_text())
    materializer = load("hotel_smoke_materializer", MODULE / "materialize.py")
    expected_digest = digest_path.read_text().strip()
    actual_digest = materializer.tree_sha256(source)
    if (proof.get("upstreamCommit") != UPSTREAM_SHA or
            proof.get("sourceCheckoutClean") is not True or
            proof.get("materializedSourceSha256") != expected_digest or
            expected_digest != actual_digest):
        raise ValueError("materialized source provenance or tree digest does not match")
    if proof.get("generatedComposeSha256") != sha256(generated):
        raise ValueError("generated Compose hash does not match source proof")
    compose_text = generated.read_text()
    if "container_name:" in compose_text:
        raise ValueError("isolated Compose still contains a global container name")
    expected_ports = {"${HR_FRONTEND_PORT:?set HR_FRONTEND_PORT}",
                      "${HR_JAEGER_QUERY_PORT:?set HR_JAEGER_QUERY_PORT}"}
    if any(token not in compose_text for token in expected_ports):
        raise ValueError("isolated Compose lacks required configurable loopback ports")
    return proof


def project_resources(project: str) -> dict:
    def lines(argv: list[str]) -> list[str]:
        value = command(argv).stdout.strip()
        return sorted(line for line in value.splitlines() if line)
    return {
        "containers": lines(["docker", "ps", "-aq", "--filter",
                             f"label=com.docker.compose.project={project}"]),
        "networks": lines(["docker", "network", "ls", "-q", "--filter",
                           f"label=com.docker.compose.project={project}"]),
        "volumes": lines(["docker", "volume", "ls", "-q", "--filter",
                          f"label=com.docker.compose.project={project}"]),
    }


def foreign_fingerprint(project: str) -> dict:
    rows = command(["docker", "ps", "-a", "--no-trunc", "--filter",
                    f"label=com.docker.compose.project={project}", "--format",
                    "{{.ID}}|{{.State}}|{{.Status}}|{{.Image}}|{{.Labels}}|{{.Ports}}"]).stdout.splitlines()
    rows = sorted(rows)
    encoded = "\n".join(rows).encode()
    return {"project": project, "rows": rows, "sha256": hashlib.sha256(encoded).hexdigest()}


def assert_port_free(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", port))


def request_ok(url: str, timeout: float = 10) -> bool:
    try:
        with urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        ).open(url, timeout=timeout) as response:
            return response.status == 200 and bool(response.read())
    except (OSError, urllib.error.HTTPError):
        return False


def wait_ready(url: str, timeout: float = 300) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if request_ok(url):
            return
        time.sleep(5)
    raise RuntimeError(f"readiness failed: {url}")


def image_receipt(project: str) -> list[dict]:
    ids = command(["docker", "ps", "-q", "--filter",
                   f"label=com.docker.compose.project={project}"]).stdout.split()
    if not ids:
        raise RuntimeError("project has no running containers")
    rows = []
    for container_id in ids:
        inspected = json.loads(command(["docker", "inspect", container_id]).stdout)[0]
        image_id = inspected.get("Image")
        if not image_id or not image_id.startswith("sha256:"):
            raise RuntimeError(f"container {container_id} lacks immutable image ID")
        image = json.loads(command(["docker", "image", "inspect", image_id]).stdout)[0]
        labels = inspected["Config"].get("Labels") or {}
        rows.append({"containerId": container_id, "name": inspected["Name"].lstrip("/"),
                     "service": labels.get("com.docker.compose.service"),
                     "project": labels.get("com.docker.compose.project"),
                     "imageId": image_id, "repoDigests": sorted(image.get("RepoDigests") or []),
                     "publishedPorts": inspected["NetworkSettings"].get("Ports") or {}})
    if any(row["project"] != project for row in rows):
        raise RuntimeError("image inventory escaped project ownership")
    return sorted(rows, key=lambda row: (row["service"] or "", row["containerId"]))


def validate_published_ports(images: list[dict], frontend_port: int, jaeger_port: int) -> None:
    actual = set()
    for row in images:
        for container_port, bindings in row["publishedPorts"].items():
            for binding in bindings or []:
                actual.add((row["service"], container_port, binding.get("HostIp"),
                            int(binding.get("HostPort"))))
    expected = {
        ("frontend", "5000/tcp", "127.0.0.1", frontend_port),
        ("jaeger", "16686/tcp", "127.0.0.1", jaeger_port),
    }
    if actual != expected:
        raise RuntimeError(f"published-port isolation mismatch: actual={sorted(actual)}, expected={sorted(expected)}")


def build_images(source: Path, project: str, env: dict, source_proof: dict,
                 output: Path) -> dict:
    """Build the shared application image once and bind it to materialized source."""
    image_name = env.get("HR_APP_IMAGE")
    if not image_name or image_name.endswith(":latest"):
        raise RuntimeError("Hotel application image must be content-addressed, not latest")
    command(compose(source, project, "build", "frontend"), output=output, env=env)
    inspected = json.loads(command(["docker", "image", "inspect", image_name]).stdout)[0]
    image_id = inspected.get("Id")
    if not image_id or not image_id.startswith("sha256:"):
        raise RuntimeError("built Hotel application image lacks immutable image ID")
    labels = inspected.get("Config", {}).get("Labels") or {}
    expected_source = source_proof["materializedSourceSha256"]
    if labels.get("org.obsplacement.materialized-source-sha256") != expected_source:
        raise RuntimeError("built Hotel application image is not bound to materialized source")
    return {
        "imageName": image_name,
        "imageId": image_id,
        "repoDigests": sorted(inspected.get("RepoDigests") or []),
        "materializedSourceSha256": expected_source,
        "buildMode": "build-once-then-up-no-build",
    }


def validate_app_image_binding(images: list[dict], build_proof: dict) -> None:
    by_service = {row["service"]: row for row in images}
    missing = sorted(set(APP_SERVICES) - set(by_service))
    wrong = sorted(service for service in APP_SERVICES
                   if service in by_service and by_service[service]["imageId"] != build_proof["imageId"])
    if missing or wrong:
        raise RuntimeError(f"application image binding mismatch: missing={missing}, wrong={wrong}")


# ponytail: `none` is JAEGER_DISABLED=true, which makes cfg.NewTracer return
# opentracing.NoopTracer (vendor config.go:220) -- no span allocation, no header
# injection, no reporter goroutine, no UDP export. The nethttp/otgrpc wrappers are
# STILL installed on every handler and dialer, so this is tracer-off, NOT source-off;
# `source-off` remains unsupported and needs the upstream service-level guard.
POSTURE_ENV = {
    "none":        {"JAEGER_SAMPLE_RATIO": "0", "JAEGER_DISABLED": "true"},
    "sample-zero": {"JAEGER_SAMPLE_RATIO": "0", "JAEGER_DISABLED": "false"},
    "full":        {"JAEGER_SAMPLE_RATIO": "1", "JAEGER_DISABLED": "false"},
}
POSTURE_CLASSIFICATION = {
    "none": "tracer-disabled-not-source-off",
    "sample-zero": "emission-off-not-source-off",
    "full": "full-root-sampling",
}


def posture_proof(project: str, posture: str, images: list[dict]) -> dict:
    expected = POSTURE_ENV[posture]
    services = {}
    for row in images:
        if row["service"] in APP_SERVICES:
            inspected = json.loads(command(["docker", "inspect", row["containerId"]]).stdout)[0]
            variables = dict(item.split("=", 1) for item in inspected["Config"].get("Env", []) if "=" in item)
            services[row["service"]] = {key: variables.get(key) for key in expected}
    missing = sorted(set(APP_SERVICES) - set(services))
    if missing or any(value != expected for value in services.values()):
        raise RuntimeError(f"posture proof mismatch: missing={missing}, values={services}")
    return {"requested": posture, "expectedEnvironment": expected, "services": services,
            "sourceWorkDisabled": False,
            "classification": POSTURE_CLASSIFICATION[posture]}


def collect_evidence(run_dir: Path, frontend_port: int, jaeger_port: int,
                     workload: dict) -> tuple[dict, dict]:
    collector = load("hotel_smoke_collector", MODULE / "collectors/jaeger_api.py")
    normalizer = load("hotel_smoke_normalizer", MODULE / "normalizers/jaeger.py")
    start_us = int(workload["startedAtEpoch"] * 1_000_000)
    end_us = int((workload["endedAtEpoch"] + 5) * 1_000_000)
    raw = collector.collect(f"http://127.0.0.1:{jaeger_port}", ["frontend"], start_us, end_us)
    normalized = normalizer.normalize(raw)
    (run_dir / "jaeger-raw.json").write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n")
    (run_dir / "traces-normalized.json").write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")
    return raw, normalized


def run_posture(root: Path, source: Path, project: str, posture: str, frontend_port: int,
                jaeger_port: int, rate: float, duration: float, concurrency: int,
                fault_at: float, outage: float, app_image: str,
                build_proof: dict, *, run_id: str | None = None, block: int = 1,
                warmup: float = 5.0, campaign_proof: dict | None = None) -> dict:
    run_id = run_id or posture
    if not (run_id == posture or re.fullmatch(rf"b[0-9]{{2,3}}-{re.escape(posture)}", run_id)):
        raise ValueError(f"invalid run ID: {run_id}")
    if not isinstance(block, int) or isinstance(block, bool) or not 1 <= block <= 100:
        raise ValueError("block must be an integer from 1 through 100")
    run_dir = root / run_id
    run_dir.mkdir()
    env = environment(posture, frontend_port, jaeger_port, app_image,
                      build_proof["materializedSourceSha256"])
    base_url = f"http://127.0.0.1:{frontend_port}"
    workload_path = run_dir / "workload.json"
    intervention_path = run_dir / "intervention.json"
    fault_cancel = threading.Event()
    fault_thread: threading.Thread | None = None
    fault_result: dict = {}
    fault_errors: list[str] = []
    try:
        command(compose(source, project, "config"), output=run_dir / "compose-rendered.yml", env=env)
        command(compose(source, project, "up", "-d", "--no-build", *SERVICES),
                output=run_dir / "up.log", env=env)
        wait_ready(base_url + "/hotels?inDate=2015-04-10&outDate=2015-04-11&lat=38.0235&lon=-122.095")
        images = image_receipt(project)
        validate_app_image_binding(images, build_proof)
        validate_published_ports(images, frontend_port, jaeger_port)
        (run_dir / "images.json").write_text(json.dumps(images, indent=2, sort_keys=True) + "\n")
        proof = posture_proof(project, posture, images)
        (run_dir / "posture-proof.json").write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
        command([sys.executable, str(MODULE / "workload/fixed_search.py"), "--base-url", base_url,
                 "--rate", str(rate), "--duration", str(warmup), "--concurrency", str(concurrency),
                 "--output", str(run_dir / "warmup.json")])
        if posture == "full":
            probe = base_url + "/hotels?inDate=2015-04-10&outDate=2015-04-11&lat=38.0235&lon=-122.095"
            adapter = load("hotel_smoke_fault", MODULE / "faults/compose_pause.py")

            def apply_fault() -> None:
                try:
                    fault_result.update(adapter.inject(
                        source, project, "search-pause", fault_at, outage,
                        probe, intervention_path, fault_cancel, env=env))
                except Exception as exc:  # retain unexpected worker failure
                    fault_errors.append(f"{type(exc).__name__}: {exc}")

            fault_thread = threading.Thread(target=apply_fault, daemon=True)
            fault_thread.start()
        workload_result = command([
            sys.executable, str(MODULE / "workload/fixed_search.py"), "--base-url", base_url,
            "--rate", str(rate), "--duration", str(duration),
            "--concurrency", str(concurrency), "--output", str(workload_path)], check=False)
        (run_dir / "workload.log").write_text(workload_result.stdout + workload_result.stderr)
        if fault_thread is not None:
            fault_thread.join(timeout=duration + outage + 180)
            if fault_thread.is_alive():
                raise RuntimeError("fault worker exceeded its lifecycle bound")
            if fault_errors:
                raise RuntimeError(f"fault worker failed: {fault_errors}")
        time.sleep(5)
        workload = json.loads(workload_path.read_text())
        _, normalized = collect_evidence(run_dir, frontend_port, jaeger_port, workload)
        intervention = fault_result or (
            json.loads(intervention_path.read_text()) if intervention_path.exists() else None)
        blockers = []
        visibility = None
        if posture == "full":
            validator = load("hotel_smoke_validator", MODULE / "validation/path_visibility.py")
            goal = json.loads((MODULE / "goals/search-path.json").read_text())
            visibility = validator.validate(normalized, goal, intervention)
            (run_dir / "visibility.json").write_text(json.dumps(visibility, indent=2, sort_keys=True) + "\n")
            if visibility["verdict"] != "pass":
                blockers.append("full posture did not retain explicit required path")
            if not intervention or not intervention.get("successful"):
                blockers.append("pause/outage/recovery was not proven")
        elif normalized["spanCount"] != 0:
            blockers.append(f"{posture} unexpectedly retained {normalized['spanCount']} spans")
        command(compose(source, project, "logs", "--no-color"),
                output=run_dir / "compose.log", check=False, env=env)
        receipt = {
            "schemaVersion": 1, "runId": run_id, "block": block,
            "sut": "hotel-reservation", "posture": posture,
            "completedAt": now(), "project": project,
            "workload": {key: workload[key] for key in ("offered", "completed", "failed", "bytesReceived")},
            "telemetry": {"uniqueTraceCount": normalized["uniqueTraceCount"],
                          "spanCount": normalized["spanCount"],
                          "uniqueSpanSignatureCount": normalized["uniqueSpanSignatureCount"]},
            "intervention": intervention, "visibility": visibility,
            "images": images, "buildProof": build_proof, "postureProof": proof,
            "campaignProof": campaign_proof,
            "canonicality": {"label": "noncanonical-functional-smoke",
                              "blockers": ["foreign workload shares host",
                                           "sampling-zero is not source-off", "no cost/latency inference"] + blockers},
            "functionalVerdict": "pass" if not blockers else "blocked",
        }
        (run_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        return receipt
    finally:
        fault_cancel.set()
        if fault_thread is not None:
            fault_thread.join(timeout=45)
            if fault_thread.is_alive():
                # A final ownership-scoped recovery attempt precedes teardown.
                command(compose(source, project, "unpause", "search"), check=False, env=env)
        command(compose(source, project, "down", "-v", "--remove-orphans"),
                output=run_dir / "down.log", check=False, env=env)
        resources = project_resources(project)
        (run_dir / "teardown.json").write_text(json.dumps(resources, indent=2, sort_keys=True) + "\n")


def validate_completed_campaign(root: Path, schedule: dict, campaign_proof: dict,
                                final_hygiene: dict) -> dict:
    """Re-read receipts and fail closed on stale, tampered, or incomplete output."""
    errors = []
    expected = {row["runId"]: row for row in schedule["runs"]}
    parameters = schedule["configuration"].get("parameters", {})
    try:
        expected_offered = math.ceil(
            parameters["requests_per_second"] * parameters["measurement_seconds"])
    except (KeyError, TypeError, ValueError, OverflowError):
        expected_offered = -1
        errors.append({"kind": "invalid-scheduled-workload"})
    expected_build = schedule["configuration"].get("runtime", {}).get("buildProof")
    actual_paths = {path.parent.name: path for path in root.glob("*/receipt.json")}
    if set(actual_paths) != set(expected):
        errors.append({"kind": "receipt-set-mismatch",
                       "missing": sorted(set(expected) - set(actual_paths)),
                       "unexpected": sorted(set(actual_paths) - set(expected))})
    for run_id in sorted(set(expected) & set(actual_paths)):
        try:
            receipt = json.loads(actual_paths[run_id].read_text())
        except (OSError, json.JSONDecodeError) as exc:
            errors.append({"kind": "invalid-receipt", "runId": run_id, "error": str(exc)})
            continue
        row = expected[run_id]
        if any(receipt.get(key) != row[key] for key in ("runId", "block", "posture")):
            errors.append({"kind": "schedule-receipt-mismatch", "runId": run_id})
        if receipt.get("campaignProof") != campaign_proof:
            errors.append({"kind": "campaign-proof-mismatch", "runId": run_id})
        build = receipt.get("buildProof")
        if build != expected_build or not isinstance(build, dict) or (
                build.get("imageId") != campaign_proof.get("buildImageId") or
                build.get("materializedSourceSha256") !=
                campaign_proof.get("materializedSourceSha256")):
            errors.append({"kind": "build-proof-mismatch", "runId": run_id})
        image_rows = receipt.get("images")
        app_images = ({item.get("service"): item.get("imageId") for item in image_rows
                       if isinstance(item, dict) and item.get("service") in APP_SERVICES}
                      if isinstance(image_rows, list) else {})
        if set(app_images) != set(APP_SERVICES) or any(
                image_id != campaign_proof.get("buildImageId")
                for image_id in app_images.values()):
            errors.append({"kind": "application-image-binding-mismatch", "runId": run_id})
        posture = receipt.get("postureProof")
        expected_env = POSTURE_ENV.get(row["posture"])
        if (not isinstance(posture, dict) or posture.get("requested") != row["posture"] or
                expected_env is None or posture.get("expectedEnvironment") != expected_env or
                posture.get("sourceWorkDisabled") is not False or
                set(posture.get("services", {})) != set(APP_SERVICES) or
                any(value != expected_env for value in posture.get("services", {}).values())):
            errors.append({"kind": "posture-proof-mismatch", "runId": run_id})
        workload = receipt.get("workload", {})
        workload_path = actual_paths[run_id].parent / "workload.json"
        try:
            raw_workload = json.loads(workload_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            errors.append({"kind": "invalid-workload", "runId": run_id, "error": str(exc)})
            raw_workload = {}
        aggregate_keys = ("offered", "completed", "failed", "bytesReceived")
        if (not isinstance(workload, dict) or
                any(workload.get(key) != raw_workload.get(key) for key in aggregate_keys)):
            errors.append({"kind": "workload-receipt-mismatch", "runId": run_id})
        offered = raw_workload.get("offered")
        completed = raw_workload.get("completed")
        failed = raw_workload.get("failed")
        requests = raw_workload.get("requests")
        if (offered != expected_offered or not isinstance(completed, int) or
                isinstance(completed, bool) or not isinstance(failed, int) or
                isinstance(failed, bool) or completed <= 0 or completed + failed != offered or
                not isinstance(requests, list) or len(requests) != offered):
            errors.append({"kind": "workload-denominator-mismatch", "runId": run_id,
                           "expectedOffered": expected_offered, "actualOffered": offered})
        if receipt.get("functionalVerdict") != "pass":
            errors.append({"kind": "functional-verdict", "runId": run_id})
        if row["posture"] in ("none", "sample-zero"):
            posture = row["posture"]
            if completed != offered:
                errors.append({"kind": f"{posture}-request-failure", "runId": run_id})
            if receipt.get("telemetry", {}).get("spanCount") != 0:
                errors.append({"kind": f"{posture}-retained-spans", "runId": run_id})
            if receipt.get("intervention") is not None:
                errors.append({"kind": f"unexpected-{posture}-intervention", "runId": run_id})
        else:
            if receipt.get("intervention", {}).get("successful") is not True:
                errors.append({"kind": "unproven-full-intervention", "runId": run_id})
            if receipt.get("visibility", {}).get("verdict") != "pass":
                errors.append({"kind": "unproven-full-visibility", "runId": run_id})
    if campaign_proof.get("scheduleSha256") != sha256(root / "schedule.json"):
        errors.append({"kind": "schedule-digest-mismatch"})
    if campaign_proof.get("configurationSha256") != json_sha256(schedule["configuration"]):
        errors.append({"kind": "configuration-digest-mismatch"})
    if final_hygiene.get("protectedProjectUnchanged") is not True:
        errors.append({"kind": "protected-project-changed"})
    if any(final_hygiene.get("projectResources", {}).values()):
        errors.append({"kind": "owned-project-not-clean"})
    return {"schemaVersion": 1, "successful": not errors,
            "expectedReceiptCount": len(expected), "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--frontend-port", required=True, type=int)
    parser.add_argument("--jaeger-port", required=True, type=int)
    parser.add_argument("--protect-project", default="dps_training_k")
    parser.add_argument("--framework-commit", required=True)
    parser.add_argument("--framework-bundle-sha256", required=True)
    parser.add_argument("--blocks", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260809)
    parser.add_argument("--warmup", type=float, default=5)
    parser.add_argument("--rate", type=float, default=1)
    parser.add_argument("--duration", type=float, default=20)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--fault-at", type=float, default=5)
    parser.add_argument("--outage", type=float, default=3)
    args = parser.parse_args()
    try:
        source_proof = validate(args.source.resolve(), args.output.resolve(), args.project,
                                args.frontend_port, args.jaeger_port, args.rate, args.duration,
                                args.concurrency, args.fault_at, args.outage,
                                args.blocks, args.seed, args.warmup)
        if not re.fullmatch(r"[0-9a-f]{40}", args.framework_commit):
            raise ValueError("framework-commit must be a full lowercase Git SHA")
        if not re.fullmatch(r"[0-9a-f]{64}", args.framework_bundle_sha256):
            raise ValueError("framework-bundle-sha256 must be a lowercase SHA-256")
        resources = project_resources(args.project)
        if any(resources.values()):
            raise RuntimeError(f"project namespace collision: {resources}")
        assert_port_free(args.frontend_port)
        assert_port_free(args.jaeger_port)
    except (ValueError, RuntimeError, OSError) as exc:
        parser.error(str(exc))
    args.output.mkdir(parents=True)
    app_image = ("obsplacement/hotel-reservation:"
                 + source_proof["materializedSourceSha256"][:16])
    before = foreign_fingerprint(args.protect_project)
    preflight = {"schemaVersion": 1, "capturedAt": now(), "project": args.project,
                 "ports": [args.frontend_port, args.jaeger_port], "projectResources": resources,
                 "protectedProjectBefore": before, "sourceProof": source_proof,
                 "runnerSha256": sha256(Path(__file__)), "overlaySha256": sha256(OVERLAY),
                 "appImage": app_image}
    (args.output / "preflight.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n")
    receipts = []
    final = None
    try:
        build_proof = build_images(
            args.source.resolve(), args.project,
            environment("full", args.frontend_port, args.jaeger_port, app_image,
                        source_proof["materializedSourceSha256"]),
            source_proof, args.output / "build.log")
        (args.output / "build-proof.json").write_text(
            json.dumps(build_proof, indent=2, sort_keys=True) + "\n")
        campaign = load("hotel_smoke_campaign", MODULE / "execution/campaign.py")
        parameters = campaign.CampaignParameters(
            blocks=args.blocks, seed=args.seed, warmup_seconds=args.warmup,
            measurement_seconds=args.duration, requests_per_second=args.rate,
            concurrency=args.concurrency, fault_at_seconds=args.fault_at,
            outage_seconds=args.outage,
            base_url=f"http://127.0.0.1:{args.frontend_port}",
        )
        schedule = {
            "configuration": {
                **campaign.configuration(parameters, source_proof, args.framework_commit),
                "runtime": {
                    "project": args.project,
                    "protectedProject": args.protect_project,
                    "frontendPort": args.frontend_port,
                    "jaegerPort": args.jaeger_port,
                    "runnerSha256": sha256(Path(__file__)),
                    "overlaySha256": sha256(OVERLAY),
                    "appImage": app_image,
                    "buildProof": build_proof,
                    "frameworkBundleSha256": args.framework_bundle_sha256,
                    "frameworkBundleKind": "clean-export-with-pinned-top-level-submodules",
                },
            },
            "runs": campaign.schedule(parameters),
        }
        campaign.write_schedule(args.output / "schedule.json",
                                schedule["configuration"], schedule["runs"])
        campaign_proof = {
            "schemaVersion": 1,
            "frameworkCommit": args.framework_commit,
            "frameworkBundleSha256": args.framework_bundle_sha256,
            "scheduleSha256": sha256(args.output / "schedule.json"),
            "configurationSha256": json_sha256(schedule["configuration"]),
            "runnerSha256": sha256(Path(__file__)),
            "overlaySha256": sha256(OVERLAY),
            "materializedSourceSha256": source_proof["materializedSourceSha256"],
            "buildImageId": build_proof["imageId"],
        }
        (args.output / "campaign-proof.json").write_text(
            json.dumps(campaign_proof, indent=2, sort_keys=True) + "\n")
        for row in schedule["runs"]:
            posture = row["posture"]
            if any(project_resources(args.project).values()):
                raise RuntimeError(f"project not clean before {row['runId']}")
            receipts.append(run_posture(args.output, args.source.resolve(), args.project, posture,
                                        args.frontend_port, args.jaeger_port, args.rate, args.duration,
                                        args.concurrency, args.fault_at, args.outage,
                                        app_image, build_proof, run_id=row["runId"],
                                        block=row["block"], warmup=args.warmup,
                                        campaign_proof=campaign_proof))
    finally:
        after = foreign_fingerprint(args.protect_project)
        final = {"schemaVersion": 1, "capturedAt": now(),
                 "projectResources": project_resources(args.project),
                 "protectedProjectBefore": before, "protectedProjectAfter": after,
                 "protectedProjectUnchanged": before["sha256"] == after["sha256"]}
        (args.output / "final-hygiene.json").write_text(json.dumps(final, indent=2, sort_keys=True) + "\n")
    assert final is not None
    completion = validate_completed_campaign(args.output, schedule, campaign_proof, final)
    (args.output / "completion-validation.json").write_text(
        json.dumps(completion, indent=2, sort_keys=True) + "\n")
    summary = {"schemaVersion": 1, "label": "noncanonical-functional-smoke",
               "receipts": [{"runId": item["runId"], "block": item["block"],
                             "posture": item["posture"],
                             "functionalVerdict": item["functionalVerdict"]} for item in receipts],
               "protectedProjectUnchanged": before["sha256"] == after["sha256"],
               "projectClean": not any(final["projectResources"].values()),
               "completionValidation": completion}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    evidence = load("hotel_smoke_evidence", ROOT / "src/obsplacement/evidence.py")
    manifest = evidence.build_manifest(args.output)
    (args.output / evidence.MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if (all(item["functionalVerdict"] == "pass" for item in receipts) and
                 summary["protectedProjectUnchanged"] and summary["projectClean"] and
                 completion["successful"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
