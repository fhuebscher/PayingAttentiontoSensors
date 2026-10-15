#!/usr/bin/env python3
"""Replay TeaStore candidate-runtime readiness and its watched defects.

Readiness is not a collection of asserted booleans.  For every admitted seam
this checker re-reads a hash-bound input, deterministically regenerates the
retained report, and then repeats the same operation for a planted defect that
must be rejected.  Target-side ``probe`` mode performs bounded inspection of
the installed checkout and exact Docker image identities, but never promotes
cell-only broker, log-capture, or terminal outcomes into setup observations.
This module performs no SSH, image build, campaign launch, or empirical cell.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, NoReturn


INPUT_KIND = "teastore-candidate-readiness-input-v1"
REPORT_KIND = "teastore-candidate-readiness-check-v1"
TARGET = "fb14srv5"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*@sha256:[0-9a-f]{64}$")
IMAGE_SERVICES = {
    "registry", "db", "persistence", "auth", "image", "recommender", "webui", "rabbitmq",
}
PROBE_CONTEXT_KEYS = {
    "frameworkCommit", "descriptorCanonicalSha256",
    "compiledPlanCanonicalSha256", "imageDigests",
}


class ReadinessError(ValueError):
    """A retained readiness observation cannot be independently replayed."""


# Expected values are checker contracts, never accepted input projections.  The
# input contains retained raw stdout/stderr and argv for each checker; facts are
# derived below only after that raw record replays.
SEAM_EXPECTED_VALUES: dict[str, dict[str, Any]] = {
    "patched-sut-images": {
        "inputContract": "pass", "platform": "linux/amd64",
        "services": ["auth", "persistence", "webui"],
        "remoteImageInspection": "pass", "runtimeReady": False,
    },
    "application-witness-finalization": {
        "manifestSchemaVersion": 3, "patchDigestBound": True,
        "authEvent": "login-persistence-request",
        "persistenceEvent": "login-user-lookup",
    },
    "measurement-scoped-auth-log-capture": {
        "captureContract": "measurement-window",
        "runtimeCapture": "not-measured",
        "postRunValidationRequired": True,
    },
    "parameter-logging-disabled": {
        "composeContract": "LOG_PARAMETERS-absent",
        "runtimeEnvironment": "not-measured",
        "postRunValidationRequired": True,
    },
    "native-token-correlation": {
        "validatorAst": "pass", "reconcileEntryPoint": "present",
        "runtimeMapping": "not-measured", "postRunValidationRequired": True,
    },
    "cross-message-parent-and-service-attribution": {
        "collectorSelfCheck": "4/4-pass",
        "parentTree": "eoi/ess-correct", "fieldRoundTrip": "exact",
        "runtimeAttribution": "not-measured",
    },
    "none-selected-full-materialization": {
        "descriptorValidation": "pass", "compiledRunCount": 27,
        "regimes": ["auth-freeze-effect", "no-fault-cost", "persistence-crash-effect"],
        "postures": ["full", "none", "selected"],
    },
    "queue-and-capture-reconciliation": {
        "brokerState": "not-measured",
        "reason": "requires-running-cell",
        "postRunValidationRequired": True,
    },
    "candidate-cell-validation": {
        "validatorLoad": "pass", "emptyArtifactFixture": "blocked",
        "runtimeCell": "not-measured", "postRunValidationRequired": True,
    },
    "candidate-terminal-validation": {
        "validatorLoad": "pass", "expectedRunRoots": 27,
        "runtimeTerminal": "not-measured", "postRunValidationRequired": True,
    },
    "bounded-transport": {
        "implementationAst": "pass", "subprocessCalls": "argv-only",
        "shellEvaluationAllowed": False, "runtimeTransport": "not-measured",
        "target": TARGET,
    },
    "outer-lease-deadline-and-cleanup": {
        "controllerAst": "pass", "leaseGuard": "present",
        "deadlineGuard": "present", "cleanupGuard": "present",
        "runtimeLifecycle": "not-measured", "postRunValidationRequired": True,
    },
}


def _study_epoch_module():
    """The tree's study-epoch selector (execution/study_epoch.py), loaded by path (python3 -I)."""
    path = Path(__file__).resolve().parents[1] / "execution/study_epoch.py"
    name = "teastore_study_epoch_" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:  # pragma: no cover - install defect
            raise ReadinessError(f"cannot load the study-epoch selector: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


# With no selector: 27 cells, three regimes, three postures (the frozen epoch's c1724b1 literals above).
EPOCH = _study_epoch_module().active(Path(__file__).resolve().parents[3])
if EPOCH["sweep"]:
    SEAM_EXPECTED_VALUES["none-selected-full-materialization"] = {
        "descriptorValidation": "pass", "compiledRunCount": EPOCH["runCount"],
        "regimes": sorted(EPOCH["regimes"]),
        "postures": sorted(EPOCH["postures"]),
    }
    SEAM_EXPECTED_VALUES["candidate-terminal-validation"] = {
        **SEAM_EXPECTED_VALUES["candidate-terminal-validation"],
        "expectedRunRoots": EPOCH["runCount"],
    }


def _derive_raw_observations(value: Any, *, seam: str) -> tuple[dict[str, Any], list[str]]:
    expected = SEAM_EXPECTED_VALUES.get(seam)
    if expected is None:
        return {}, ["readiness seam is not registered"]
    if not isinstance(value, dict) or set(value) != {
        "checker", "argv", "exitCode", "stdout", "stderr", "inputSha256",
    }:
        return {}, ["raw readiness observation fields differ"]
    blockers: list[str] = []
    validator = "modules/teastore/validation/candidate_readiness.py"
    checker = f"candidate-readiness-v2:{seam}"
    argv = ["/usr/bin/python3", "-I", validator, "probe", seam]
    if (
        value.get("checker") != checker or value.get("argv") != argv
        or type(value.get("exitCode")) is not int or value.get("exitCode") != 0
        or value.get("stderr") != ""
        or not isinstance(value.get("inputSha256"), str)
        or SHA256_RE.fullmatch(value["inputSha256"]) is None
        or not isinstance(value.get("stdout"), str)
        or not value["stdout"].endswith("\n") or value["stdout"].count("\n") != 1
    ):
        return {}, ["raw readiness checker execution differs"]
    try:
        projection = json.loads(
            value["stdout"], object_pairs_hook=_no_duplicates,
            parse_constant=_reject_constant,
        )
    except (ReadinessError, json.JSONDecodeError) as exc:
        return {}, [f"raw readiness checker output is invalid: {exc}"]
    if not isinstance(projection, dict) or set(projection) != {"facts"}:
        return {}, ["raw readiness checker projection differs"]
    derived = projection["facts"]
    if not _same(derived, expected):
        blockers.append("derived readiness seam facts differ")
    return derived, blockers


def _reject_constant(value: str) -> NoReturn:
    raise ReadinessError(f"non-finite JSON value is forbidden: {value}")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ReadinessError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, allow_nan=False, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReadinessError(f"value is not canonical JSON: {exc}") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _same(left: Any, right: Any) -> bool:
    try:
        return _canonical(left) == _canonical(right)
    except ReadinessError:
        return False


def _explicit_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (
        parsed.tzinfo is not None
        and parsed.utcoffset() is not None
        and parsed.utcoffset() == timezone.utc.utcoffset(parsed)
    )


def _safe_relative(value: Any, where: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ReadinessError(f"{where} is not a safe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise ReadinessError(f"{where} is not a normalized relative path")
    return path


def _file(root: Path, relative: Any, where: str) -> tuple[Path, bytes]:
    path = _safe_relative(relative, where)
    current = root
    try:
        for part in path.parts[:-1]:
            current = current / part
            metadata = current.lstat()
            if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
                raise ReadinessError(f"{where} crosses a symlink or non-directory")
        candidate = current / path.parts[-1]
        before = candidate.lstat()
        if candidate.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise ReadinessError(f"{where} is not a regular non-symlink file")
        payload = candidate.read_bytes()
        after = candidate.lstat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ) or len(payload) != before.st_size:
            raise ReadinessError(f"{where} changed while being read")
        return candidate, payload
    except ReadinessError:
        raise
    except OSError as exc:
        raise ReadinessError(f"cannot read {where}: {exc}") from exc


def _json(payload: bytes, where: str) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_no_duplicates, parse_constant=_reject_constant,
        )
    except ReadinessError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"invalid JSON in {where}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReadinessError(f"{where} must contain one object")
    return value


def check_input(
    document: Any,
    *,
    seam: str,
    framework_commit: str,
    descriptor_sha256: str,
    plan_sha256: str,
    image_digests: Mapping[str, str],
) -> dict[str, Any]:
    """Return the deterministic verdict for one captured readiness input."""

    blockers: list[str] = []
    expected_keys = {
        "schemaVersion", "kind", "seam", "target", "frameworkCommit",
        "descriptorCanonicalSha256", "compiledPlanCanonicalSha256",
        "imageDigests", "capturedAt", "rawObservations",
    }
    if not isinstance(document, dict) or set(document) != expected_keys:
        blockers.append("readiness input fields differ")
        document = document if isinstance(document, dict) else {}
    if type(document.get("schemaVersion")) is not int or document.get("schemaVersion") != 1:
        blockers.append("readiness input schemaVersion differs")
    if document.get("kind") != INPUT_KIND or document.get("seam") != seam:
        blockers.append("readiness input kind or seam differs")
    if document.get("target") != TARGET:
        blockers.append("readiness input target differs")
    if document.get("frameworkCommit") != framework_commit:
        blockers.append("readiness input framework commit differs")
    if document.get("descriptorCanonicalSha256") != descriptor_sha256:
        blockers.append("readiness input descriptor digest differs")
    if document.get("compiledPlanCanonicalSha256") != plan_sha256:
        blockers.append("readiness input plan digest differs")
    observed_images = document.get("imageDigests")
    if not _same(observed_images, dict(image_digests)) or any(
        not isinstance(value, str) or IMAGE_RE.fullmatch(value) is None
        for value in (observed_images.values() if isinstance(observed_images, dict) else ())
    ):
        blockers.append("readiness input image digests differ")
    captured = document.get("capturedAt")
    if not _explicit_utc_timestamp(captured):
        blockers.append("readiness input capture time is not explicit UTC")
    derived_facts, raw_blockers = _derive_raw_observations(
        document.get("rawObservations"), seam=seam,
    )
    probe_context = {
        "frameworkCommit": framework_commit,
        "descriptorCanonicalSha256": descriptor_sha256,
        "compiledPlanCanonicalSha256": plan_sha256,
        "imageDigests": dict(image_digests),
    }
    expected_input_sha = canonical_sha256(probe_context)
    if not isinstance(document.get("rawObservations"), dict) or document[
        "rawObservations"
    ].get("inputSha256") != expected_input_sha:
        blockers.append("raw readiness probe input digest differs")
    blockers.extend(raw_blockers)
    observations = {
        "inputSha256": canonical_sha256(document),
        "target": document.get("target"),
        "rawObservationsSha256": canonical_sha256(document.get("rawObservations")),
        "derivedFactsSha256": canonical_sha256(derived_facts),
    }
    return {
        "schemaVersion": 1,
        "kind": REPORT_KIND,
        "seam": seam,
        "verdict": "pass" if not blockers else "blocked",
        "blockers": blockers,
        "observations": observations,
    }


def _load_installed(root: Path, relative: str, name: str) -> Any:
    path = root / relative
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ReadinessError(f"installed module cannot be loaded: {relative}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def _validator_rejects_empty(
    module: Any, function: str, **keyword_arguments: Any,
) -> bool:
    validator = getattr(module, function, None)
    if not callable(validator):
        return False
    with tempfile.TemporaryDirectory(prefix="teastore-readiness-defect-") as temporary:
        try:
            report = validator(Path(temporary), **keyword_arguments)
        except Exception:
            return True
    if not isinstance(report, dict):
        return False
    return report.get("verdict") in {"blocked", "fail"}


def _subprocess_calls_are_argv_only(payload: bytes) -> bool:
    tree = ast.parse(payload.decode("utf-8", errors="strict"))
    observed = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == "subprocess"
            and function.attr in {"run", "Popen"}
        ):
            continue
        observed += 1
        for keyword in node.keywords:
            if keyword.arg == "shell" and not (
                isinstance(keyword.value, ast.Constant)
                and keyword.value.value is False
            ):
                return False
    return observed > 0


def _defined_functions(payload: bytes) -> set[str]:
    tree = ast.parse(payload.decode("utf-8", errors="strict"))
    return {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _patched_image_facts(payload: bytes) -> dict[str, Any]:
    report = _json(payload, "patched-image input report")
    return {
        "inputContract": report.get("outcome"),
        "platform": report.get("platform"),
        "services": report.get("services"),
        "remoteImageInspection": "pass",
        "runtimeReady": report.get("runtimeReady"),
    }


def _witness_facts(root: Path, manifest_payload: bytes) -> dict[str, Any]:
    manifest = _json(manifest_payload, "application witness manifest")
    patch = manifest.get("patch", {})
    patch_path = root / str(patch.get("path"))
    patch_payload = patch_path.read_bytes()
    observations = manifest.get("observations", {}).get("applicationWitness", {})
    events = observations.get("events", {})
    return {
        "manifestSchemaVersion": manifest.get("schemaVersion"),
        "patchDigestBound": hashlib.sha256(patch_payload).hexdigest() == patch.get("sha256"),
        "authEvent": events.get("auth"),
        "persistenceEvent": events.get("persistence"),
    }


def _parameter_contract_facts(payload: bytes) -> dict[str, Any]:
    compose = payload.decode("utf-8", errors="strict")
    return {
        "composeContract": (
            "LOG_PARAMETERS-absent" if "LOG_PARAMETERS" not in compose else "LOG_PARAMETERS-present"
        ),
        "runtimeEnvironment": "not-measured",
        "postRunValidationRequired": True,
    }


def _correlation_facts(payload: bytes) -> dict[str, Any]:
    functions = _defined_functions(payload)
    return {
        "validatorAst": "pass",
        "reconcileEntryPoint": "present" if "validate_retained" in functions else "missing",
        "runtimeMapping": "not-measured",
        "postRunValidationRequired": True,
    }


def _cross_message_facts(payload: bytes) -> dict[str, Any]:
    expected = (
        "SELF-CHECK PASSED: 4/4 records, eoi/ess parent tree correct, "
        "field round-trip exact, unified schema valid (real trace ids), "
        "malformed frames handled.\n"
    ).encode()
    matched = payload == expected
    return {
        "collectorSelfCheck": "4/4-pass" if matched else "blocked",
        "parentTree": "eoi/ess-correct" if matched else "blocked",
        "fieldRoundTrip": "exact" if matched else "blocked",
        "runtimeAttribution": "not-measured",
    }


def _enforce_expected_facts(seam: str, facts: Mapping[str, Any]) -> None:
    if not _same(dict(facts), SEAM_EXPECTED_VALUES[seam]):
        raise ReadinessError(f"installed operational probe blocked: {seam}")


def probe(seam: str, context: Any) -> dict[str, Any]:
    """Execute one allow-listed installed-readiness fact projection.

    The root supervisor supplies the context through stdin.  This entry point
    accepts no command, path, or expected value from that context; its complete
    output domain is the compiled seam registry below.
    """
    if seam not in SEAM_EXPECTED_VALUES:
        raise ReadinessError("probe seam is not allow-listed")
    if not isinstance(context, dict) or set(context) != PROBE_CONTEXT_KEYS:
        raise ReadinessError("probe context fields differ")
    if (
        not isinstance(context.get("imageDigests"), dict)
        or set(context["imageDigests"]) != IMAGE_SERVICES
        or any(not isinstance(value, str) or IMAGE_RE.fullmatch(value) is None
               for value in context["imageDigests"].values())
    ):
        raise ReadinessError("probe image context differs")
    root = Path(__file__).resolve().parents[3]
    git = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C", "LC_ALL": "C"},
    )
    if git.returncode or git.stdout.decode("ascii", errors="strict").strip() != context["frameworkCommit"]:
        raise ReadinessError("probe framework commit differs from installed HEAD")
    pilot_path = root / EPOCH["compilerRelative"]
    pilot_spec = importlib.util.spec_from_file_location("teastore_readiness_probe_pilot", pilot_path)
    if pilot_spec is None or pilot_spec.loader is None:
        raise ReadinessError("installed candidate compiler is unavailable")
    pilot = importlib.util.module_from_spec(pilot_spec)
    sys.modules[pilot_spec.name] = pilot
    pilot_spec.loader.exec_module(pilot)
    descriptor = pilot.strict_json_file(root / EPOCH["descriptorRelative"])
    pilot.validate_descriptor(descriptor)
    plan = pilot.compile_plan(descriptor)
    pilot.validate_plan(descriptor, plan)
    if (
        pilot.canonical_sha256(descriptor) != context["descriptorCanonicalSha256"]
        or pilot.canonical_sha256(plan) != context["compiledPlanCanonicalSha256"]
        or plan.get("runCount") != EPOCH["runCount"]
    ):
        raise ReadinessError("probe descriptor or compiled plan identity differs")
    probe_files = {
        "patched-sut-images": ("modules/teastore/images/patched-image-inputs.json",),
        "application-witness-finalization": ("modules/teastore/witness/patch-manifest-v3.json",),
        "measurement-scoped-auth-log-capture": ("modules/teastore/execution/performance_campaign.py",),
        "parameter-logging-disabled": ("modules/teastore/deployment/compose/docker-compose_kieker.yaml",),
        "native-token-correlation": ("modules/teastore/validation/native_token_correlation.py",),
        "cross-message-parent-and-service-attribution": ("modules/teastore/collectors/kieker_native.py",),
        "none-selected-full-materialization": ("modules/teastore/execution/candidate_orchestrator.py",),
        "queue-and-capture-reconciliation": ("modules/teastore/execution/performance_campaign.py",),
        "candidate-cell-validation": ("modules/teastore/validation/candidate_pilot.py",),
        "candidate-terminal-validation": ("modules/teastore/validation/candidate_terminal.py",),
        "bounded-transport": ("modules/teastore/execution/candidate_transport.py",),
        "outer-lease-deadline-and-cleanup": (
            "modules/teastore/execution/candidate_remote_controller.py",
            "modules/teastore/execution/candidate_release_installer.py",
        ),
    }
    installed_payloads: dict[str, bytes] = {}
    for relative in probe_files[seam]:
        path = root / relative
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise ReadinessError("installed seam artifact is not a regular file")
        payload = path.read_bytes()
        if not payload:
            raise ReadinessError("installed seam artifact is empty")
        installed_payloads[relative] = payload
        if path.suffix == ".py":
            compile(payload.decode("utf-8", errors="strict"), str(path), "exec")
    # Docker-backed seams additionally prove the exact image population is
    # inspectable through the live daemon. RabbitMQ is the exact frozen image
    # member, rather than a caller-selected broker endpoint.
    for service, reference in sorted(context["imageDigests"].items()):
        repository, _, image_id = reference.partition("@")
        # The bound value is the image config ID, not a repo digest, so
        # "repository@<config id>" is a reference form Docker cannot resolve:
        # locally built images carry no repo digest at all, and for pulled
        # images the repo digest is the manifest digest, which never equals the
        # config ID. Inspect the content ID directly, then confirm the
        # repository the runtime will actually name resolves to that same
        # content, so the check still binds repository to bytes.
        result = subprocess.run(
            ["docker", "image", "inspect", "--format",
             "{{.Id}}\t{{json .RepoTags}}", image_id],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=30,
        )
        if result.returncode != 0:
            raise ReadinessError(f"live Docker image inspection failed: {service}")
        observed, _, tags = result.stdout.decode(
            "utf-8", errors="strict"
        ).strip().partition("\t")
        try:
            repositories = {
                str(tag).rsplit(":", 1)[0] for tag in (json.loads(tags) or ())
            }
        except json.JSONDecodeError as exc:
            raise ReadinessError(
                f"live Docker image tags are unreadable: {service}"
            ) from exc
        if observed != image_id or repository not in repositories:
            raise ReadinessError(f"live Docker image inspection failed: {service}")
    fixed_commands = {
        "patched-sut-images": [sys.executable, "-I", "modules/teastore/validation/patched_images.py", "inputs"],
        "cross-message-parent-and-service-attribution": [
            sys.executable, "-I", "modules/teastore/collectors/kieker_native.py", "--self-check",
        ],
    }
    command = fixed_commands.get(seam)
    command_stdout: bytes | None = None
    if command is not None:
        result = subprocess.run(
            command, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=300,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C", "LC_ALL": "C"},
        )
        if result.returncode != 0:
            raise ReadinessError(f"installed seam executable self-test failed: {seam}")
        command_stdout = result.stdout
    facts = dict(SEAM_EXPECTED_VALUES[seam])
    if seam == "patched-sut-images":
        if command_stdout is None:
            raise ReadinessError("patched-image input report is missing")
        facts = _patched_image_facts(command_stdout)
    elif seam == "application-witness-finalization":
        facts = _witness_facts(
            root,
            installed_payloads["modules/teastore/witness/patch-manifest-v3.json"],
        )
    elif seam == "parameter-logging-disabled":
        facts = _parameter_contract_facts(installed_payloads[
            "modules/teastore/deployment/compose/docker-compose_kieker.yaml"
        ])
    elif seam == "native-token-correlation":
        facts = _correlation_facts(installed_payloads[
            "modules/teastore/validation/native_token_correlation.py"
        ])
    elif seam == "cross-message-parent-and-service-attribution":
        facts = _cross_message_facts(command_stdout or b"")
    elif seam == "none-selected-full-materialization":
        allocations = plan.get("scheduleAllocation")
        if not isinstance(allocations, dict):
            raise ReadinessError("compiled schedule allocation is unavailable")
        postures = sorted({
            posture
            for allocation in allocations.values()
            for block in allocation.get("blocks", [])
            for posture in block
        })
        facts = {
            "descriptorValidation": "pass",
            "compiledRunCount": plan.get("runCount"),
            "regimes": sorted(allocations),
            "postures": postures,
        }
    elif seam == "candidate-cell-validation":
        validator = _load_installed(
            root, "modules/teastore/validation/candidate_pilot.py",
            "teastore_readiness_candidate_cell_validator",
        )
        facts = {
            "validatorLoad": "pass",
            "emptyArtifactFixture": (
                "blocked" if _validator_rejects_empty(validator, "validate_run") else "escaped"
            ),
            "runtimeCell": "not-measured",
            "postRunValidationRequired": True,
        }
    elif seam == "candidate-terminal-validation":
        validator = _load_installed(
            root, "modules/teastore/validation/candidate_terminal.py",
            "teastore_readiness_candidate_terminal_validator",
        )
        facts = {
            "validatorLoad": "pass",
            "expectedRunRoots": plan.get("runCount"),
            "runtimeTerminal": "not-measured",
            "postRunValidationRequired": True,
        }
        if not _validator_rejects_empty(
            validator, "validate_candidate_campaign",
            expected_campaign_sha256="0" * 64, manifest_anchors={},
        ):
            raise ReadinessError("terminal validator accepted empty planted fixture")
    elif seam == "bounded-transport":
        payload = installed_payloads[
            "modules/teastore/execution/candidate_transport.py"
        ]
        argv_only = _subprocess_calls_are_argv_only(payload)
        facts = {
            "implementationAst": "pass" if argv_only else "blocked",
            "subprocessCalls": "argv-only" if argv_only else "shell-capable",
            "shellEvaluationAllowed": not argv_only,
            "runtimeTransport": "not-measured",
            "target": TARGET,
        }
    elif seam == "outer-lease-deadline-and-cleanup":
        controller = installed_payloads[
            "modules/teastore/execution/candidate_remote_controller.py"
        ]
        installer_payload = installed_payloads[
            "modules/teastore/execution/candidate_release_installer.py"
        ]
        functions = _defined_functions(controller) | _defined_functions(installer_payload)
        facts = {
            "controllerAst": "pass",
            "leaseGuard": "present" if "execute_package" in functions else "missing",
            "deadlineGuard": "present" if "launch_campaign" in functions else "missing",
            "cleanupGuard": "present" if "subprocess_cleanup_executor" in functions else "missing",
            "runtimeLifecycle": "not-measured",
            "postRunValidationRequired": True,
        }
    _enforce_expected_facts(seam, facts)
    return {"facts": facts}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("probe",))
    parser.add_argument("seam")
    args = parser.parse_args(argv)
    try:
        context = json.load(__import__("sys").stdin)
        print(json.dumps(probe(args.seam, context), sort_keys=True))
        return 0
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=__import__("sys").stderr)
        return 2


def _digest_bound_file(
    root: Path, relative: Any, expected: Any, where: str,
) -> tuple[Path, bytes]:
    path, payload = _file(root, relative, where)
    if (
        not isinstance(expected, str)
        or SHA256_RE.fullmatch(expected) is None
        or hashlib.sha256(payload).hexdigest() != expected
    ):
        raise ReadinessError(f"{where} digest differs")
    return path, payload


def validate_seam_pair(
    artifact_root: Path,
    *,
    seam: str,
    evidence: Mapping[str, Any],
    failure_witness: Mapping[str, Any],
    framework_commit: str,
    descriptor_sha256: str,
    plan_sha256: str,
    image_digests: Mapping[str, str],
    validator_sha256: str,
) -> dict[str, Any]:
    """Replay one positive capture and one watched planted-defect capture."""

    if seam not in SEAM_EXPECTED_VALUES:
        raise ReadinessError(f"unregistered readiness seam: {seam}")
    expected_observation_keys = {
        "inputPath", "inputSha256", "reportPath", "reportSha256",
    }
    if not isinstance(evidence, Mapping) or set(evidence) != {
        "schemaVersion", "kind", "seam", "status", "validatorSha256", "observations",
    }:
        raise ReadinessError(f"positive evidence fields differ for {seam}")
    if not isinstance(failure_witness, Mapping) or set(failure_witness) != {
        "schemaVersion", "kind", "seam", "status", "plantedDefect",
        "checkerExitCode", "validatorSha256", "observations",
    }:
        raise ReadinessError(f"failure witness fields differ for {seam}")
    positive_observations = evidence.get("observations")
    defect_observations = failure_witness.get("observations")
    if (
        set(positive_observations) != expected_observation_keys
        if isinstance(positive_observations, Mapping) else True
    ) or (
        set(defect_observations) != expected_observation_keys
        if isinstance(defect_observations, Mapping) else True
    ):
        raise ReadinessError(f"readiness observation paths differ for {seam}")
    if (
        evidence.get("schemaVersion") != 1
        or evidence.get("seam") != seam
        or evidence.get("status") != "pass"
        or evidence.get("validatorSha256") != validator_sha256
        or failure_witness.get("schemaVersion") != 1
        or failure_witness.get("seam") != seam
        or failure_witness.get("status") != "detected"
        or failure_witness.get("validatorSha256") != validator_sha256
        or type(failure_witness.get("checkerExitCode")) is not int
        or failure_witness.get("checkerExitCode") != 2
        or not isinstance(failure_witness.get("plantedDefect"), str)
        or not failure_witness["plantedDefect"].strip()
    ):
        raise ReadinessError(f"readiness evidence identity differs for {seam}")

    replayed: list[dict[str, Any]] = []
    used_paths: set[str] = set()
    for label, observations, expected_verdict in (
        ("positive", positive_observations, "pass"),
        ("planted defect", defect_observations, "blocked"),
    ):
        assert isinstance(observations, Mapping)
        paths = (observations["inputPath"], observations["reportPath"])
        if paths[0] == paths[1] or any(path in used_paths for path in paths):
            raise ReadinessError(f"{seam} readiness artifacts alias")
        used_paths.update(paths)
        _, input_payload = _digest_bound_file(
            artifact_root, observations["inputPath"], observations["inputSha256"],
            f"{seam} {label} input",
        )
        _, report_payload = _digest_bound_file(
            artifact_root, observations["reportPath"], observations["reportSha256"],
            f"{seam} {label} report",
        )
        input_document = _json(input_payload, f"{seam} {label} input")
        retained_report = _json(report_payload, f"{seam} {label} report")
        report = check_input(
            input_document, seam=seam, framework_commit=framework_commit,
            descriptor_sha256=descriptor_sha256, plan_sha256=plan_sha256,
            image_digests=image_digests,
        )
        if not _same(retained_report, report) or report["verdict"] != expected_verdict:
            raise ReadinessError(
                f"{seam} {label} report differs from deterministic replay"
            )
        if expected_verdict == "blocked" and not report["blockers"]:
            raise ReadinessError(f"{seam} planted defect was not detected")
        replayed.append(report)
    return {"positive": replayed[0], "plantedDefect": replayed[1]}


__all__ = [
    "INPUT_KIND", "REPORT_KIND", "ReadinessError", "SEAM_EXPECTED_VALUES",
    "canonical_sha256", "check_input", "validate_seam_pair",
]


if __name__ == "__main__":
    raise SystemExit(main())
