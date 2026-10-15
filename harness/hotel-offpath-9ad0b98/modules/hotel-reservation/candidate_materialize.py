#!/usr/bin/env python3
"""Materialize the pinned Hotel source and apply the reviewed candidate patch."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, NoReturn


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "modules" / "hotel-reservation"
BASE_MATERIALIZER = MODULE / "materialize.py"
PATCH_MANIFEST = MODULE / "witness" / "patch-manifest.json"
RUNTIME_INPUTS = MODULE / "deployment" / "runtime-inputs.lock.json"
DEFAULT_OUT = ROOT / ".local" / "hotel-reservation-candidate"
SENTINEL = ".obsplacement-materialized"
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class MaterializationError(RuntimeError):
    """Candidate source identity or patch application failed closed."""


def _reject_constant(value: str) -> NoReturn:
    raise MaterializationError(f"non-finite JSON value is forbidden: {value}")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise MaterializationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MaterializationError(f"cannot read strict JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MaterializationError(f"{path} must contain one JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_base():
    spec = importlib.util.spec_from_file_location("hotel_base_materializer", BASE_MATERIALIZER)
    if spec is None or spec.loader is None:
        raise MaterializationError("cannot load the base Hotel materializer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _safe_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise MaterializationError("patch file path is not a POSIX relative file")
    candidate = root.joinpath(*relative.split("/"))
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise MaterializationError(f"cannot resolve patch input {relative}: {exc}") from exc
    if resolved_root not in resolved.parents or candidate.is_symlink() or not candidate.is_file():
        raise MaterializationError(f"patch input escapes candidate source: {relative}")
    return candidate


def _verify_lock(document: dict[str, Any]) -> None:
    if set(document) != {
        "schemaVersion", "sourceCommit", "images", "applicationEnvironment", "policy"
    }:
        raise MaterializationError("runtime input lock fields differ")
    if document["schemaVersion"] != 1 or document["sourceCommit"] != (
        "6ecb09706140f8730b5385c08f1386c654c3c526"
    ):
        raise MaterializationError("runtime input lock source identity differs")
    images = document.get("images")
    if not isinstance(images, dict) or set(images) != {
        "builder", "consul", "jaeger", "memcached", "mongo"
    }:
        raise MaterializationError("runtime image lock set differs")
    for name, reference in images.items():
        if not isinstance(reference, str) or re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}", reference
        ) is None:
            raise MaterializationError(f"runtime image {name} is not digest pinned")
    if document["applicationEnvironment"] != {
        "TLS": "0", "GC": "100", "LOG_LEVEL": "info", "MEMC_TIMEOUT": "2",
    }:
        raise MaterializationError("application environment inputs differ")
    if document["policy"] != {
        "pullByDigestOnly": True,
        "mutableTagFallbackAllowed": False,
        "builtApplicationImageMustBindPatchedTreeSha256": True,
    }:
        raise MaterializationError("runtime input lock policy differs")


def validate_patch_inputs(source: Path) -> tuple[dict[str, Any], dict[str, Any], Path]:
    manifest = _json(PATCH_MANIFEST)
    lock = _json(RUNTIME_INPUTS)
    _verify_lock(lock)
    expected_keys = {
        "schemaVersion", "id", "upstreamCommit", "patch", "patchSha256",
        "files", "claims",
    }
    if set(manifest) != expected_keys or manifest.get("schemaVersion") != 1:
        raise MaterializationError("patch manifest fields differ")
    if manifest.get("upstreamCommit") != lock["sourceCommit"]:
        raise MaterializationError("patch and runtime lock source commits differ")
    patch_value = manifest.get("patch")
    if patch_value != "modules/hotel-reservation/witness/hotel-candidate-witness.patch":
        raise MaterializationError("patch manifest path differs")
    patch = ROOT / patch_value
    digest = _sha256(patch)
    if manifest.get("patchSha256") != digest or HEX_SHA256.fullmatch(digest) is None:
        raise MaterializationError("candidate patch SHA-256 differs")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 4:
        raise MaterializationError("patch manifest must bind exactly four files")
    seen: set[str] = set()
    for row in files:
        if not isinstance(row, dict) or set(row) != {
            "path", "beforeSha256", "afterSha256"
        }:
            raise MaterializationError("patch file binding fields differ")
        relative = row.get("path")
        if relative in seen:
            raise MaterializationError("patch manifest repeats a file")
        seen.add(relative)
        before = _safe_file(source, relative)
        if _sha256(before) != row.get("beforeSha256"):
            raise MaterializationError(f"patch preimage differs: {relative}")
        if HEX_SHA256.fullmatch(str(row.get("afterSha256"))) is None:
            raise MaterializationError(f"patch postimage digest is invalid: {relative}")
    if seen != {"Dockerfile", "tracing/mux.go", "tracing/tracer.go", "tune/setting.go"}:
        raise MaterializationError("patch manifest file set differs")
    return manifest, lock, patch


def _apply_patch(source: Path, patch: Path) -> None:
    environment = {
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": "/nonexistent-hotel-candidate-materializer-home",
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    # The checked-in patch deliberately uses zero-context hunks so the outer
    # repository's whitespace checker can inspect the patch artifact cleanly.
    # Exact per-file preimage SHA-256 bindings make this stricter than fuzzy
    # contextual application.
    # ``--no-index`` makes the exact digest-bound patch work in the reviewed
    # installed payload as well as in a Git checkout; pre/postimage hashes are
    # the authority, not repository discovery above the materialized tree.
    command = ["git", "apply", "--no-index", "--unidiff-zero", "-p2", str(patch)]
    check = subprocess.run(
        [*command[:2], "--check", *command[2:]], cwd=source, env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if check.returncode:
        raise MaterializationError(
            "candidate patch dry-run failed: "
            + check.stderr.decode("utf-8", errors="replace").strip()
        )
    applied = subprocess.run(
        command, cwd=source, env=environment, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if applied.returncode:
        raise MaterializationError(
            "candidate patch application failed: "
            + applied.stderr.decode("utf-8", errors="replace").strip()
        )


def _safe_target(path: Path) -> Path:
    target = path.resolve()
    forbidden = {Path("/"), Path.home().resolve(), ROOT.resolve(), MODULE.resolve()}
    if target in forbidden or target in ROOT.resolve().parents or target.is_relative_to(MODULE):
        raise MaterializationError(f"refusing unsafe candidate target: {target}")
    return target


def materialize(out: Path = DEFAULT_OUT) -> dict[str, Any]:
    target = _safe_target(Path(out))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        sentinel = target / SENTINEL
        if not sentinel.is_file() or _json(sentinel).get("candidatePatchId") != (
            "hotel-lmt-pilot-witness-and-log-fatal-v1"
        ):
            raise MaterializationError(f"refusing to replace non-candidate directory: {target}")
    staging = Path(tempfile.mkdtemp(prefix=".hotel-candidate-", dir=target.parent))
    shutil.rmtree(staging)
    base = _load_base()
    try:
        proof = base.materialize(staging)
        manifest, lock, patch = validate_patch_inputs(staging)
        _apply_patch(staging, patch)
        for row in manifest["files"]:
            actual = _sha256(_safe_file(staging, row["path"]))
            if actual != row["afterSha256"]:
                raise MaterializationError(f"patch postimage differs: {row['path']}")
        proof = {
            **proof,
            "candidatePatchId": manifest["id"],
            "candidatePatchSha256": manifest["patchSha256"],
            "patchManifestSha256": _sha256(PATCH_MANIFEST),
            "runtimeInputsSha256": _sha256(RUNTIME_INPUTS),
            "runtimeImages": lock["images"],
            "transformations": [
                *proof["transformations"],
                "apply-reviewed-request-witness-and-emitted-span-byte-patch",
                "add-log-level-fatal-case",
                "pin-go-builder-by-manifest-digest",
            ],
        }
        proof["materializedSourceSha256"] = base.tree_sha256(staging)
        (staging / base.SENTINEL).write_text(
            json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (staging / ".source.sha256").write_text(
            proof["materializedSourceSha256"] + "\n", encoding="ascii"
        )
        if target.exists():
            shutil.rmtree(target)
        staging.rename(target)
        return proof
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    try:
        proof = materialize(args.out)
    except MaterializationError as exc:
        parser.error(str(exc))
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
