#!/usr/bin/env python3
"""Validate the repository's fail-closed OpenSpec science supplement.

The validator executes only code-owned, typed checks.  No command, argument
vector, or executable path is read from a change artifact.  A passing report
establishes repository-local governance consistency only; runtime authorization
and evidence-promotion eligibility remain false in every outcome.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import pwd
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Sequence

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_BASE_COMMIT = "0b968dafd033e24eb9bba78ee18ef58a65fcc284"
SCHEMA_ID = (
    "https://observability-placement.local/contracts/"
    "science-change-control.schema.json"
)
SCHEMA_PATH = "contracts/science-change-control.schema.json"
CONFIG_PATH = "openspec/config.yaml"
OPEN_SPEC_SCHEMA_PATH = "openspec/schemas/scientific-change/schema.yaml"
OPEN_SPEC_PACKAGE = "@fission-ai/openspec"
OPEN_SPEC_VERSION = "1.11.0"
OPEN_SPEC_INTEGRITY = (
    "sha512-P9h8H4Snit8I7tHmCopjg3QDwBllIlObxb+/DebvBwhWTj6YEPPYRYkC4n5GqG4P"
    "dQnKMA6E1AlEOI9FT4G7FA=="
)
PACKAGE_JSON_SHA256 = "172fe9b976d30c54fbe45ae6dd0de87c7fed2f6b9965448871404d882871c4b2"
PACKAGE_LOCK_SHA256 = "2bafb850b9074f710f5b18a259ed30ceeb980473aa53a4bf667eeea8dfc97ef0"
PINNED_CONTROL_FILE_DIGESTS = {
    "contracts/science-change-control.schema.json": "5422b177f8fd378c630c20a522407c9e5c254b03bc2340f65d48da06df9073eb",
    "openspec/config.yaml": "61c2488c73a6aa59ce791ae18b0ffb6f61093cd710ced7517c71ffe3c6c86fd7",
    "openspec/schemas/scientific-change/schema.yaml": "2a3ad4e1201884cedce712aa6ea684c48f78a9270fe1c2d4b03f87dbb09f225c",
    "openspec/schemas/scientific-change/templates/authority.md": "dcd5f650513730f146802e605ec6110fdf0f3ee0af7d3e6a42a24a5157b05bf5",
    "openspec/schemas/scientific-change/templates/design.md": "5992cdeb0a863ab0877e89bb9791a78936f2bdaacef7387352b7b276e35794c2",
    "openspec/schemas/scientific-change/templates/governance.json": "4e50f76e8172168e3a25724e4dd02f701fe15433fec6363f477a6fc49d83ddbc",
    "openspec/schemas/scientific-change/templates/proposal.md": "173bbb2a0f540f47912e86c85b0e0eea9cf1fc882817d532c7dcccf21d1f0e40",
    "openspec/schemas/scientific-change/templates/spec.md": "cbc96f4e0444bef671141eda2a6155b68fbf6826bb27f6e4c811b82f6902f16e",
    "openspec/schemas/scientific-change/templates/tasks.md": "fc079ee096de358fed084d2dd757472df48d8e51aa870de65d37b36597fedfe9",
    "openspec/schemas/scientific-change/templates/verification.md": "e402a6a1cb4653918806aebe3eb2b223b1badd63eab5001d7674df18eba0f033",
}
PINNED_POLICY_DIGESTS = {
    "adopt-scientific-openspec": {
        "authorityBindings": "0fa89c53e59676cae9bdab0bce635e2ec50cb1a7cc971dd8a0cc6b311f859aff",
        "pathOwnership": "c701b1568133bfd3ac250e12e4a5d1c9f1d40e7f65fa6af5db1ded1435b4f0f6",
        "workflow": "41f92fff7776e721808bbf6f643cd8db24e872ae3ac2c96edc456ff19fafa79c",
    },
    "phase2-method-freeze": {
        "authorityBindings": "aba3004b3a94a928c7a279b00a5332e3b0f9ce08271ce7f31813e92a48fa7899",
        "pathOwnership": "7397208c6149de1e3f277f67f7b244783d56eab7f2aaad544242c8f7e2e8a4d0",
        "workflow": "daf89775b2a2be0ade608baed5198db5ff6366b5b75060417be5fa1dbcff9446",
    },
    "teastore-candidate-pilot-freeze": {
        "authorityBindings": "ffa276db6aadb03c8f955e9f459b9031a96ac28e4c08459ea3b409bd92d08662",
        "pathOwnership": "bfe7f7737a8506594ed6b99be59e95a9604b654187769cab361cebee2bd599ce",
        "workflow": "ceedd1606c66357335b497da46c5f20244d275c49c061867391542805b9d4cad",
    },
}
PINNED_LEDGER_PREFIXES: dict[str, dict[str, int | str]] = {
    "adopt-scientific-openspec": {
        "length": 11669,
        "sha256": "daa45b3d3880163530308e218c39347395fd1c6148b09d1b0de2808b1ee27765",
    },
    "phase2-method-freeze": {
        "length": 7667,
        "sha256": "61e92a36eb6bd3664b03661bbe336edb439097362f2db73a5aa5c2b07953144c",
    },
    "teastore-candidate-pilot-freeze": {
        "length": 9388,
        "sha256": "0dceda78306e523c63b79aa16ae6710e0a1ca55868e247bc7ff85e14ddd7c25b",
    },
}
PINNED_DELIVERY_TREE_SHA256 = "ca24f0b2ad31d98a8bc2ef2cdac49b088f4d47231382d5616f76f0a694d9f748"
CHECK_IDS = (
    "openspec-config",
    "openspec-tool-pin",
    "change-artifacts",
    "governance-schema",
    "authority-bindings",
    "path-ownership",
    "findings-ledger",
    "runtime-boundary",
)
CHECK_STATUSES = {"pass", "fail", "cannot_run"}
FINDINGS_HEADER = (
    "finding_id",
    "change_id",
    "reviewer_context",
    "classification",
    "severity",
    "status",
    "artifact_path",
    "summary",
    "evidence",
    "disposition",
)
EXPECTED_ARTIFACT_NAMES = {
    "proposal": "proposal.md",
    "authority": "authority.md",
    "design": "design.md",
    "tasks": "tasks.md",
    "verification": "verification.md",
    "governance": "governance.json",
}
EXPECTED_TEMPLATE_NAMES = {
    "proposal.md",
    "authority.md",
    "spec.md",
    "design.md",
    "tasks.md",
    "verification.md",
    "governance.json",
}
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEX_COMMIT = re.compile(r"^[0-9a-f]{40}$")
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
FINDING_ID = re.compile(r"^F-[A-Z0-9]+(?:-[A-Z0-9]+)*$")


class DuplicateKeyError(ValueError):
    """Raised when JSON contains an ambiguous duplicate object member."""


Runner = Callable[..., subprocess.CompletedProcess[bytes]]


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    status: str
    summary: str
    diagnostics: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.check_id not in CHECK_IDS:
            raise ValueError(f"unregistered check id: {self.check_id}")
        if self.status not in CHECK_STATUSES:
            raise ValueError(f"unregistered check status: {self.status}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.check_id,
            "status": self.status,
            "summary": self.summary,
            "diagnostics": list(self.diagnostics),
        }


@dataclass
class ValidationContext:
    root: Path
    change_directories: list[Path]
    manifests: dict[str, dict[str, Any]]
    manifest_errors: list[str]
    runner: Runner
    expected_base_commit: str
    openspec_install_root: Path
    expected_policy_digests: dict[str, dict[str, str]]
    expected_ledger_prefixes: dict[str, dict[str, int | str]]
    expected_delivery_tree_sha256: str
    openspec_tool: Path | None = None


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(payload)


def delivery_tree_digest(
    root: Path,
    changed_paths: Iterable[str],
    indexed_objects: dict[str, tuple[str, str]] | None = None,
) -> str:
    """Bind the exact reviewed delivery set, modes, and raw bytes.

    Findings CSV files are governed by append-only checkpoints. The validator
    and wrapper are the local code root and are excluded to avoid a cyclic hash
    dependency; the wrapper separately pins the validator before operations.
    """

    excluded = {"tools/run_openspec.py", "tools/validate_openspec_science.py"}
    index = {} if indexed_objects is None else indexed_objects
    records: list[bytes] = []
    for relative in sorted(set(changed_paths)):
        if relative in excluded or (
            relative.startswith("findings/") and relative.endswith(".csv")
        ):
            continue
        canonical = _canonical_relative(relative, directory=False)
        indexed = index.get(canonical)
        if indexed is not None and indexed[0] == "160000":
            records.append(
                b"G\0"
                + indexed[0].encode("ascii")
                + b"\0"
                + canonical.encode("utf-8")
                + b"\0"
                + indexed[1].encode("ascii")
                + b"\0"
            )
            continue
        path = root / canonical
        try:
            observed = path.lstat()
        except FileNotFoundError:
            records.append(b"D\0" + canonical.encode("utf-8") + b"\0")
            continue
        mode = stat.S_IMODE(observed.st_mode)
        if stat.S_ISLNK(observed.st_mode):
            payload = os.readlink(path).encode("utf-8", errors="surrogateescape")
            kind = b"L"
        elif stat.S_ISREG(observed.st_mode):
            payload = path.read_bytes()
            kind = b"F"
        elif stat.S_ISDIR(observed.st_mode):
            payload = b""
            kind = b"T"
        else:
            payload = b""
            kind = b"O"
        records.append(
            kind
            + b"\0"
            + format(mode, "o").encode("ascii")
            + b"\0"
            + canonical.encode("utf-8")
            + b"\0"
            + hashlib.sha256(payload).hexdigest().encode("ascii")
            + b"\0"
        )
    return sha256_bytes(b"".join(records))


def _canonical_relative(relative: str, *, directory: bool | None = None) -> str:
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"path is not a non-empty repository-relative string: {relative!r}")
    if "\\" in relative or "//" in relative or "\x00" in relative:
        raise ValueError(f"path is not lexically canonical: {relative}")
    requested_directory = relative.endswith("/")
    raw = relative[:-1] if requested_directory else relative
    pure = PurePosixPath(raw)
    if (
        pure.is_absolute()
        or raw in {"", "."}
        or any(part in {"", ".", ".."} for part in pure.parts)
        or pure.as_posix() != raw
    ):
        raise ValueError(f"path is not repository-relative: {relative}")
    if directory is False and requested_directory:
        raise ValueError(f"expected a file path, got a directory scope: {relative}")
    if directory is True or requested_directory:
        return f"{raw}/"
    return raw


def _path_without_symlinks(root: Path, relative: str, *, file: bool) -> Path:
    canonical = _canonical_relative(relative, directory=False if file else None)
    current = root
    for part in PurePosixPath(canonical.rstrip("/")).parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError as error:
            raise ValueError(f"repository path does not exist: {canonical}") from error
        if stat.S_ISLNK(mode):
            raise ValueError(f"repository path contains a symlink: {canonical}")
    resolved = current.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"repository path escapes the root: {canonical}")
    if file and not current.is_file():
        raise ValueError(f"repository path is not a regular file: {canonical}")
    return current


def _scope_contains(scope: str, relative: str) -> bool:
    if scope.endswith("/"):
        return relative.startswith(scope)
    return relative == scope


def _scopes_overlap(left: str, right: str) -> bool:
    left_probe = left if not left.endswith("/") else f"{left}__probe__"
    right_probe = right if not right.endswith("/") else f"{right}__probe__"
    return (
        _scope_contains(left, right.rstrip("/"))
        or _scope_contains(right, left.rstrip("/"))
        or _scope_contains(left, right_probe)
        or _scope_contains(right, left_probe)
    )


def _default_runner(
    argv: Sequence[str], *, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _trusted_host_executable(name: str, root: Path) -> Path:
    """Resolve a host tool without consulting caller-controlled PATH."""

    candidates = [
        Path("/opt/homebrew/bin") / name,
        Path("/usr/local/bin") / name,
        Path("/usr/bin") / name,
        Path("/bin") / name,
    ]
    user_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    candidates.extend(
        sorted(
            (user_home / ".nvm" / "versions" / "node").glob(f"*/bin/{name}"),
            reverse=True,
        )
    )
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if root == resolved or root in resolved.parents:
            continue
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise OSError(f"required trusted host executable is unavailable: {name}")


def _run_fixed(
    context: ValidationContext, argv: Sequence[str]
) -> subprocess.CompletedProcess[bytes]:
    return _run_fixed_at(context, argv, cwd=context.root)


def _run_fixed_at(
    context: ValidationContext, argv: Sequence[str], *, cwd: Path
) -> subprocess.CompletedProcess[bytes]:
    command = list(argv)
    path_entries: list[str] = []
    if command[0] in {"git", "npm"}:
        executable = _trusted_host_executable(command[0], context.root)
        command[0] = str(executable)
        path_entries.append(str(executable.parent))
        if executable.name == "git" and command[1:2] == ["-C"] and len(command) >= 3:
            # Disable fsmonitor before any query can consult a repository hook.
            command[3:3] = ["-c", "core.fsmonitor=false"]

    try:
        node_path = _trusted_host_executable("node", context.root)
        path_entries.append(str(node_path.parent))
    except OSError:
        # Git-only checks do not need Node; npm/OpenSpec checks fail closed later.
        pass
    path_entries.extend(("/usr/bin", "/bin"))
    controlled_home = context.openspec_install_root / "home"
    controlled_home.mkdir(exist_ok=True)
    user_config = controlled_home / ".npmrc"
    user_config.touch(exist_ok=True)
    npm_cache = (Path(pwd.getpwuid(os.getuid()).pw_dir) / ".npm").resolve()
    env = {
        "PATH": os.pathsep.join(dict.fromkeys(path_entries)),
        "HOME": str(controlled_home),
        "OPENSPEC_TELEMETRY": "0",
        "OPENSPEC_NO_UPDATE_CHECK": "1",
        "npm_config_cache": str(npm_cache),
        "npm_config_userconfig": str(user_config),
        "npm_config_globalconfig": "/dev/null",
        "npm_config_ignore_scripts": "true",
        "npm_config_offline": "true",
        "npm_config_audit": "false",
        "npm_config_fund": "false",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    return context.runner(tuple(command), cwd=cwd, env=env)


def _decode_output(result: subprocess.CompletedProcess[bytes]) -> str:
    combined = result.stdout + result.stderr
    return combined.decode("utf-8", errors="replace").strip()


def _result(
    check_id: str,
    errors: Iterable[str],
    *,
    cannot_run: Iterable[str] = (),
    passed_summary: str,
) -> CheckResult:
    failures = tuple(errors)
    unavailable = tuple(cannot_run)
    if failures:
        return CheckResult(check_id, "fail", f"{len(failures)} defect(s) detected", failures)
    if unavailable:
        return CheckResult(
            check_id,
            "cannot_run",
            f"{len(unavailable)} required operation(s) could not run",
            unavailable,
        )
    return CheckResult(check_id, "pass", passed_summary)


def _discover_context(
    root: Path,
    runner: Runner,
    expected_base_commit: str,
    openspec_install_root: Path,
    expected_policy_digests: dict[str, dict[str, str]],
    expected_ledger_prefixes: dict[str, dict[str, int | str]],
    expected_delivery_tree_sha256: str,
) -> ValidationContext:
    root = root.resolve()
    changes_root = root / "openspec" / "changes"
    change_directories: list[Path] = []
    errors: list[str] = []
    manifests: dict[str, dict[str, Any]] = {}
    if changes_root.is_dir():
        for marker in sorted(changes_root.glob("*/.openspec.yaml")):
            directory = marker.parent
            change_directories.append(directory)
            change_id = directory.name
            manifest_path = directory / "governance.json"
            if not manifest_path.is_file():
                errors.append(f"{change_id}: missing governance.json")
                continue
            try:
                value = load_json(manifest_path)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError) as error:
                errors.append(f"{change_id}: cannot parse governance.json: {error}")
                continue
            if not isinstance(value, dict):
                errors.append(f"{change_id}: governance.json is not a JSON object")
                continue
            if change_id in manifests:
                errors.append(f"duplicate change id: {change_id}")
                continue
            manifests[change_id] = value
    else:
        errors.append("openspec/changes directory does not exist")
    if not change_directories:
        errors.append("no OpenSpec changes were discovered")
    return ValidationContext(
        root,
        change_directories,
        manifests,
        errors,
        runner,
        expected_base_commit,
        openspec_install_root,
        expected_policy_digests,
        expected_ledger_prefixes,
        expected_delivery_tree_sha256,
    )


def check_openspec_config(context: ValidationContext) -> CheckResult:
    errors: list[str] = []
    for relative, expected_digest in PINNED_CONTROL_FILE_DIGESTS.items():
        try:
            path = _path_without_symlinks(context.root, relative, file=True)
            observed_digest = sha256_file(path)
        except (OSError, ValueError) as error:
            errors.append(f"cannot verify pinned control file {relative}: {error}")
            continue
        if observed_digest != expected_digest:
            errors.append(
                f"pinned control file bytes differ: {relative}: "
                f"observed={observed_digest}, expected={expected_digest}"
            )
    try:
        config = _path_without_symlinks(context.root, CONFIG_PATH, file=True)
        config_text = config.read_text(encoding="utf-8")
        schema_declarations = re.findall(
            r"^schema:[ \t]*([^#\r\n]+?)[ \t]*$", config_text, re.MULTILINE
        )
        if schema_declarations != ["scientific-change"]:
            errors.append(
                "openspec/config.yaml must declare exactly `schema: scientific-change`"
            )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        errors.append(f"cannot validate {CONFIG_PATH}: {error}")

    try:
        schema_path = _path_without_symlinks(
            context.root, OPEN_SPEC_SCHEMA_PATH, file=True
        )
        schema_text = schema_path.read_text(encoding="utf-8")
        names = re.findall(r"^name:[ \t]*([^#\r\n]+?)[ \t]*$", schema_text, re.MULTILINE)
        versions = re.findall(
            r"^version:[ \t]*([^#\r\n]+?)[ \t]*$", schema_text, re.MULTILINE
        )
        if names != ["scientific-change"]:
            errors.append("scientific-change schema must declare its exact name once")
        if versions != ["1"]:
            errors.append("scientific-change schema must declare exact version 1")
        template_root = schema_path.parent / "templates"
        actual_templates = {
            item.name for item in template_root.iterdir() if item.is_file()
        }
        if actual_templates != EXPECTED_TEMPLATE_NAMES:
            errors.append(
                "scientific-change templates differ: "
                f"observed={sorted(actual_templates)}, "
                f"expected={sorted(EXPECTED_TEMPLATE_NAMES)}"
            )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        errors.append(f"cannot validate {OPEN_SPEC_SCHEMA_PATH}: {error}")

    return _result(
        "openspec-config",
        errors,
        passed_summary="OpenSpec config and scientific-change schema are exact",
    )


def check_openspec_tool_pin(context: ValidationContext) -> CheckResult:
    errors: list[str] = []
    cannot_run: list[str] = []
    try:
        package_path = _path_without_symlinks(context.root, "package.json", file=True)
        package = load_json(package_path)
        if sha256_file(package_path) != PACKAGE_JSON_SHA256:
            errors.append("package.json bytes differ from the reviewed OpenSpec tool pin")
        observed = package.get("devDependencies", {}).get(OPEN_SPEC_PACKAGE)
        if observed != OPEN_SPEC_VERSION:
            errors.append(
                f"package.json must pin {OPEN_SPEC_PACKAGE} exactly to {OPEN_SPEC_VERSION}"
            )
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"cannot validate package.json: {error}")

    try:
        lock_path = _path_without_symlinks(context.root, "package-lock.json", file=True)
        lock = load_json(lock_path)
        if sha256_file(lock_path) != PACKAGE_LOCK_SHA256:
            errors.append("package-lock.json bytes differ from the reviewed dependency graph")
        root_pin = (
            lock.get("packages", {}).get("", {}).get("devDependencies", {}).get(OPEN_SPEC_PACKAGE)
        )
        installed = lock.get("packages", {}).get(
            f"node_modules/{OPEN_SPEC_PACKAGE}", {}
        )
        if lock.get("lockfileVersion") != 3:
            errors.append("package-lock.json must use lockfileVersion 3")
        if root_pin != OPEN_SPEC_VERSION:
            errors.append(
                f"package-lock.json root must pin {OPEN_SPEC_PACKAGE} to {OPEN_SPEC_VERSION}"
            )
        if installed.get("version") != OPEN_SPEC_VERSION:
            errors.append(
                f"package-lock.json resolved {OPEN_SPEC_PACKAGE} version is not {OPEN_SPEC_VERSION}"
            )
        if installed.get("integrity") != OPEN_SPEC_INTEGRITY:
            errors.append(f"package-lock.json integrity differs for {OPEN_SPEC_PACKAGE}")
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"cannot validate package-lock.json: {error}")

    if not errors:
        try:
            shutil.copyfile(
                context.root / "package.json",
                context.openspec_install_root / "package.json",
            )
            shutil.copyfile(
                context.root / "package-lock.json",
                context.openspec_install_root / "package-lock.json",
            )
            install = _run_fixed_at(
                context,
                (
                    "npm",
                    "ci",
                    "--ignore-scripts",
                    "--offline",
                    "--no-audit",
                    "--no-fund",
                ),
                cwd=context.openspec_install_root,
            )
            if install.returncode != 0:
                cannot_run.append(
                    "isolated lockfile install failed: " + _decode_output(install)
                )
                return _result(
                    "openspec-tool-pin",
                    errors,
                    cannot_run=cannot_run,
                    passed_summary="unreachable",
                )
            tool = context.openspec_install_root / "node_modules" / ".bin" / "openspec"
            if not tool.exists() or not os.access(tool, os.X_OK):
                cannot_run.append("isolated OpenSpec executable was not installed")
                return _result(
                    "openspec-tool-pin",
                    errors,
                    cannot_run=cannot_run,
                    passed_summary="unreachable",
                )
            resolved = tool.resolve(strict=True)
            if (
                context.openspec_install_root != resolved
                and context.openspec_install_root not in resolved.parents
            ):
                errors.append("isolated OpenSpec executable escapes its temporary install")
            result = _run_fixed(context, (str(tool), "--version"))
            if result.returncode != 0:
                cannot_run.append(
                    f"OpenSpec --version exited {result.returncode}: {_decode_output(result)}"
                )
            elif result.stdout.decode("utf-8", errors="replace").strip() != OPEN_SPEC_VERSION:
                errors.append(
                    "OpenSpec executable version differs: "
                    f"{result.stdout.decode('utf-8', errors='replace').strip()!r}"
                )
            if not errors and not cannot_run:
                context.openspec_tool = tool
        except (OSError, subprocess.SubprocessError) as error:
            cannot_run.append(f"isolated OpenSpec preparation could not run: {error}")

    return _result(
        "openspec-tool-pin",
        errors,
        cannot_run=cannot_run,
        passed_summary=(
            f"OpenSpec {OPEN_SPEC_VERSION} runs from a fresh offline lockfile install"
        ),
    )


def _expected_artifact_paths(change_id: str, manifest: dict[str, Any]) -> tuple[set[str], list[str]]:
    errors: list[str] = []
    expected: set[str] = {f"openspec/changes/{change_id}/.openspec.yaml"}
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return expected, [f"{change_id}: artifacts is not an object"]
    change_prefix = f"openspec/changes/{change_id}/"
    for key, filename in EXPECTED_ARTIFACT_NAMES.items():
        observed = artifacts.get(key)
        exact = f"{change_prefix}{filename}"
        if observed != exact:
            errors.append(f"{change_id}: artifacts.{key} must be {exact}")
        if isinstance(observed, str):
            expected.add(observed)
    specs = artifacts.get("specs")
    if not isinstance(specs, list) or not specs:
        errors.append(f"{change_id}: artifacts.specs must be a non-empty list")
    else:
        for relative in specs:
            if not isinstance(relative, str):
                errors.append(f"{change_id}: non-string spec artifact")
                continue
            if not relative.startswith(f"{change_prefix}specs/") or not relative.endswith(
                "/spec.md"
            ):
                errors.append(f"{change_id}: spec artifact is outside the exact spec tree: {relative}")
            expected.add(relative)
    findings = artifacts.get("findings")
    exact_findings = f"findings/{change_id}.csv"
    if findings != exact_findings:
        errors.append(f"{change_id}: artifacts.findings must be {exact_findings}")
    return expected, errors


def check_change_artifacts(context: ValidationContext) -> CheckResult:
    errors: list[str] = list(context.manifest_errors)
    cannot_run: list[str] = []
    tool = context.openspec_tool
    for directory in context.change_directories:
        change_id = directory.name
        if not SLUG.fullmatch(change_id):
            errors.append(f"invalid OpenSpec change directory name: {change_id}")
            continue
        marker = directory / ".openspec.yaml"
        try:
            marker_text = marker.read_text(encoding="utf-8")
            declarations = re.findall(
                r"^schema:[ \t]*([^#\r\n]+?)[ \t]*$", marker_text, re.MULTILINE
            )
            if declarations != ["scientific-change"]:
                errors.append(f"{change_id}: marker must select scientific-change exactly")
        except (OSError, UnicodeDecodeError) as error:
            errors.append(f"{change_id}: cannot read .openspec.yaml: {error}")

        manifest = context.manifests.get(change_id)
        if manifest is None:
            continue
        expected, expected_errors = _expected_artifact_paths(change_id, manifest)
        errors.extend(expected_errors)
        for relative in sorted(expected):
            try:
                path = _path_without_symlinks(context.root, relative, file=True)
                if path.stat().st_size == 0:
                    errors.append(f"{change_id}: artifact is empty: {relative}")
            except (OSError, ValueError) as error:
                errors.append(f"{change_id}: invalid artifact {relative}: {error}")

        actual: set[str] = set()
        for path in directory.rglob("*"):
            if path.is_file() or path.is_symlink():
                actual.add(path.relative_to(context.root).as_posix())
        unexpected = sorted(actual - expected)
        missing = sorted(expected - actual)
        if unexpected:
            errors.append(f"{change_id}: undeclared change artifacts: {unexpected}")
        if missing:
            errors.append(f"{change_id}: missing change artifacts: {missing}")

        if tool is None:
            cannot_run.append(f"{change_id}: isolated OpenSpec validation is unavailable")
        else:
            try:
                result = _run_fixed(
                    context,
                    (
                        str(tool),
                        "validate",
                        change_id,
                        "--type",
                        "change",
                        "--strict",
                        "--no-interactive",
                    ),
                )
                if result.returncode != 0:
                    errors.append(
                        f"{change_id}: OpenSpec native validation failed: {_decode_output(result)}"
                    )
            except (OSError, subprocess.SubprocessError) as error:
                cannot_run.append(f"{change_id}: OpenSpec validation could not run: {error}")

    return _result(
        "change-artifacts",
        errors,
        cannot_run=cannot_run,
        passed_summary="Every change has the exact artifact set and passes native validation",
    )


def check_governance_schema(context: ValidationContext) -> CheckResult:
    errors: list[str] = list(context.manifest_errors)
    if set(context.manifests) != set(context.expected_policy_digests):
        errors.append(
            "active change set differs from the pinned policy registry: "
            f"observed={sorted(context.manifests)}, "
            f"expected={sorted(context.expected_policy_digests)}"
        )
    try:
        schema_path = _path_without_symlinks(context.root, SCHEMA_PATH, file=True)
        schema = load_json(schema_path)
        if not isinstance(schema, dict):
            raise ValueError("schema is not a JSON object")
        if schema.get("$id") != SCHEMA_ID:
            errors.append(f"science-control schema $id must be {SCHEMA_ID}")
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        json.JSONDecodeError,
        DuplicateKeyError,
        SchemaError,
    ) as error:
        errors.append(f"cannot validate science-control schema: {error}")
        validator = None

    for change_id, manifest in sorted(context.manifests.items()):
        if manifest.get("id") != change_id:
            errors.append(f"{change_id}: manifest id must match its change directory")
        if manifest.get("$schema") != SCHEMA_ID:
            errors.append(f"{change_id}: governance schema reference is not exact")
        if validator is not None:
            validation_errors = sorted(
                validator.iter_errors(manifest), key=lambda item: list(item.absolute_path)
            )
            for error in validation_errors:
                location = ".".join(str(part) for part in error.absolute_path) or "$"
                errors.append(f"{change_id}: {location}: {error.message}")

    return _result(
        "governance-schema",
        errors,
        passed_summary="Every governance envelope validates against schema version 1",
    )


def _git_result(
    context: ValidationContext, *args: str
) -> tuple[subprocess.CompletedProcess[bytes] | None, str | None]:
    try:
        result = _run_fixed(context, ("git", "-C", str(context.root), *args))
    except (OSError, subprocess.SubprocessError) as error:
        return None, str(error)
    return result, None


def check_authority_bindings(context: ValidationContext) -> CheckResult:
    errors: list[str] = []
    cannot_run: list[str] = []
    bases = {
        manifest.get("baseCommit")
        for manifest in context.manifests.values()
        if isinstance(manifest.get("baseCommit"), str)
    }
    if len(bases) != 1:
        errors.append(f"all changes must bind one exact base commit, observed={sorted(bases)}")
    elif bases != {context.expected_base_commit}:
        errors.append(
            "change base differs from the validator's reviewed bootstrap base: "
            f"observed={sorted(bases)}, expected={context.expected_base_commit}"
        )

    seen_paths: dict[str, str] = {}
    for change_id, manifest in sorted(context.manifests.items()):
        expected_policy = context.expected_policy_digests.get(change_id)
        observed_bindings = manifest.get("authorityBindings")
        if expected_policy is None:
            errors.append(f"{change_id}: no trusted authority policy is registered")
        elif canonical_json_digest(observed_bindings) != expected_policy["authorityBindings"]:
            errors.append(f"{change_id}: authority policy differs from the trusted registry")
        base = manifest.get("baseCommit")
        if not isinstance(base, str) or not HEX_COMMIT.fullmatch(base):
            errors.append(f"{change_id}: baseCommit is not a full lowercase Git commit")
            continue
        exists, unavailable = _git_result(context, "cat-file", "-e", f"{base}^{{commit}}")
        if unavailable:
            cannot_run.append(f"{change_id}: Git could not check base commit: {unavailable}")
        elif exists is not None and exists.returncode != 0:
            errors.append(f"{change_id}: base commit does not exist: {base}")
        ancestor, unavailable = _git_result(
            context, "merge-base", "--is-ancestor", base, "HEAD"
        )
        if unavailable:
            cannot_run.append(f"{change_id}: Git could not compare base commit: {unavailable}")
        elif ancestor is not None and ancestor.returncode == 1:
            errors.append(f"{change_id}: base commit is not an ancestor of HEAD")
        elif ancestor is not None and ancestor.returncode not in {0, 1}:
            cannot_run.append(
                f"{change_id}: Git could not establish ancestry: {_decode_output(ancestor)}"
            )

        bindings = manifest.get("authorityBindings")
        if not isinstance(bindings, list) or not bindings:
            errors.append(f"{change_id}: authorityBindings must be non-empty")
            continue
        local_paths: set[str] = set()
        for binding in bindings:
            if not isinstance(binding, dict):
                errors.append(f"{change_id}: authority binding is not an object")
                continue
            relative = binding.get("path")
            declared = binding.get("sha256")
            if not isinstance(relative, str):
                errors.append(f"{change_id}: authority path is not a string")
                continue
            try:
                canonical = _canonical_relative(relative, directory=False)
            except ValueError as error:
                errors.append(f"{change_id}: {error}")
                continue
            if canonical in local_paths:
                errors.append(f"{change_id}: duplicate authority path: {canonical}")
            local_paths.add(canonical)
            prior_digest = seen_paths.get(canonical)
            if prior_digest is not None and prior_digest != declared:
                errors.append(f"authority path has conflicting digests: {canonical}")
            if isinstance(declared, str):
                seen_paths[canonical] = declared
            if not isinstance(declared, str) or not HEX_SHA256.fullmatch(declared):
                errors.append(f"{change_id}: authority digest is not SHA-256: {canonical}")
                continue
            try:
                current_path = _path_without_symlinks(
                    context.root, canonical, file=True
                )
                current_digest = sha256_file(current_path)
                if current_digest != declared:
                    errors.append(
                        f"{change_id}: authority digest mismatch for {canonical}: {current_digest}"
                    )
            except (OSError, ValueError) as error:
                errors.append(f"{change_id}: invalid authority {canonical}: {error}")
                continue

            show, unavailable = _git_result(context, "show", f"{base}:{canonical}")
            if unavailable:
                cannot_run.append(
                    f"{change_id}: Git could not read base authority {canonical}: {unavailable}"
                )
            elif show is not None and show.returncode != 0:
                errors.append(f"{change_id}: authority is absent from base commit: {canonical}")
            elif show is not None and sha256_bytes(show.stdout) != declared:
                errors.append(
                    f"{change_id}: base-commit authority bytes differ for {canonical}"
                )

    return _result(
        "authority-bindings",
        errors,
        cannot_run=cannot_run,
        passed_summary="Authority files match both the declared bytes and pinned base",
    )


def _nul_paths(result: subprocess.CompletedProcess[bytes]) -> set[str]:
    return {
        item.decode("utf-8", errors="strict")
        for item in result.stdout.split(b"\0")
        if item
    }


def _changed_paths(
    context: ValidationContext, base: str
) -> tuple[set[str], list[str], list[str]]:
    paths: set[str] = set()
    errors: list[str] = []
    cannot_run: list[str] = []
    commands = (
        (
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "-z",
            "--no-renames",
            base,
            "HEAD",
            "--",
        ),
        (
            "diff-index",
            "--cached",
            "--name-only",
            "-z",
            "--no-renames",
            "HEAD",
            "--",
        ),
        ("ls-files", "--others", "--exclude-standard", "-z", "--"),
    )
    for command in commands:
        result, unavailable = _git_result(context, *command)
        if unavailable:
            cannot_run.append(f"Git {' '.join(command)} could not run: {unavailable}")
            continue
        assert result is not None
        if result.returncode != 0:
            cannot_run.append(
                f"Git {' '.join(command)} exited {result.returncode}: {_decode_output(result)}"
            )
            continue
        try:
            paths.update(_nul_paths(result))
        except UnicodeDecodeError as error:
            errors.append(f"Git returned a non-UTF-8 path: {error}")
    return paths, errors, cannot_run


def _active_info_exclude_patterns(context: ValidationContext) -> list[str]:
    git_path, unavailable = _git_result(context, "rev-parse", "--git-path", "info/exclude")
    if unavailable or git_path is None or git_path.returncode != 0:
        return []
    relative_or_absolute = git_path.stdout.decode("utf-8", errors="replace").strip()
    path = Path(relative_or_absolute)
    if not path.is_absolute():
        path = context.root / path
    try:
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except OSError:
        return []


def _git_at_result(
    context: ValidationContext, repository: Path, *args: str
) -> tuple[subprocess.CompletedProcess[bytes] | None, str | None]:
    try:
        result = _run_fixed(context, ("git", "-C", str(repository), *args))
    except (OSError, subprocess.SubprocessError) as error:
        return None, str(error)
    return result, None


def _active_git_metadata_lines(
    context: ValidationContext, *git_path_parts: str
) -> tuple[list[str], str | None]:
    result, unavailable = _git_result(context, "rev-parse", "--git-path", *git_path_parts)
    if unavailable or result is None:
        return [], unavailable or "Git did not return a path"
    if result.returncode != 0:
        return [], _decode_output(result)
    raw = result.stdout.decode("utf-8", errors="replace").strip()
    path = Path(raw)
    if not path.is_absolute():
        path = context.root / path
    if not path.exists():
        return [], None
    try:
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except (OSError, UnicodeDecodeError) as error:
        return [], str(error)
    return lines, None


def _parse_stage_entries(payload: bytes) -> tuple[list[tuple[str, str, str]], list[str]]:
    entries: list[tuple[str, str, str]] = []
    errors: list[str] = []
    for raw in payload.split(b"\0"):
        if not raw:
            continue
        try:
            metadata, path_bytes = raw.split(b"\t", 1)
            mode, object_id, stage = metadata.decode("ascii").split(" ")
            path = path_bytes.decode("utf-8", errors="strict")
        except (ValueError, UnicodeDecodeError) as error:
            errors.append(f"cannot parse Git index entry: {error}")
            continue
        if stage != "0":
            errors.append(f"unmerged Git index entry: {path} (stage {stage})")
        entries.append((mode, object_id, path))
    return entries, errors


def _indexed_objects(
    context: ValidationContext, repository: Path, label: str
) -> tuple[dict[str, tuple[str, str]], list[str], list[str]]:
    result, unavailable = _git_at_result(
        context, repository, "ls-files", "--stage", "-z"
    )
    if unavailable:
        return {}, [], [f"{label}: cannot inspect index identities: {unavailable}"]
    assert result is not None
    if result.returncode != 0:
        return {}, [], [
            f"{label}: cannot inspect index identities: {_decode_output(result)}"
        ]
    entries, parse_errors = _parse_stage_entries(result.stdout)
    return (
        {relative: (mode, object_id) for mode, object_id, relative in entries},
        [f"{label}: {error}" for error in parse_errors],
        [],
    )


def _git_blob_id(payload: bytes, object_id_length: int) -> str:
    framed = b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
    if object_id_length == 40:
        return hashlib.sha1(framed).hexdigest()
    if object_id_length == 64:
        return hashlib.sha256(framed).hexdigest()
    raise ValueError(f"unsupported Git object id length: {object_id_length}")


def _raw_tracked_changes(
    context: ValidationContext, repository: Path, label: str
) -> tuple[set[str], list[str], list[str]]:
    changed: set[str] = set()
    errors: list[str] = []
    cannot_run: list[str] = []
    result, unavailable = _git_at_result(
        context, repository, "ls-files", "--stage", "-z"
    )
    if unavailable:
        return changed, errors, [f"{label}: cannot inspect raw tracked bytes: {unavailable}"]
    assert result is not None
    if result.returncode != 0:
        return changed, errors, [
            f"{label}: cannot inspect raw tracked bytes: {_decode_output(result)}"
        ]
    entries, parse_errors = _parse_stage_entries(result.stdout)
    errors.extend(f"{label}: {error}" for error in parse_errors)
    for mode, object_id, relative in entries:
        if mode == "160000":
            continue
        path = repository / relative
        try:
            if mode == "120000":
                payload = os.readlink(path).encode("utf-8", errors="surrogateescape")
            elif mode in {"100644", "100755"}:
                payload = path.read_bytes()
            else:
                continue
        except (OSError, UnicodeError):
            changed.add(relative)
            continue
        try:
            observed = _git_blob_id(payload, len(object_id))
        except ValueError as error:
            cannot_run.append(f"{label}: {error}")
            continue
        if observed != object_id:
            changed.add(relative)
    return changed, errors, cannot_run


def _index_flag_errors(
    context: ValidationContext, repository: Path, label: str
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    cannot_run: list[str] = []
    result, unavailable = _git_at_result(context, repository, "ls-files", "-v", "-z")
    if unavailable:
        return errors, [f"{label}: cannot inspect index flags: {unavailable}"]
    assert result is not None
    if result.returncode != 0:
        return errors, [f"{label}: cannot inspect index flags: {_decode_output(result)}"]
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            entry = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            errors.append(f"{label}: non-UTF-8 Git index entry: {error}")
            continue
        if len(entry) < 3 or entry[1] != " ":
            errors.append(f"{label}: malformed Git index flag record")
            continue
        tag, relative = entry[0], entry[2:]
        if tag.islower() or tag == "S":
            errors.append(
                f"{label}: assume-unchanged or skip-worktree index flag: {relative}"
            )
    return errors, cannot_run


def _local_git_configuration_errors(
    context: ValidationContext, repository: Path, label: str
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    cannot_run: list[str] = []
    queries = (
        ("filter configuration", ("config", "--local", "--get-regexp", r"^filter\.")),
        (
            "submodule ignore configuration",
            ("config", "--local", "--get-regexp", r"^submodule\..*\.ignore$"),
        ),
        (
            "local attributes file",
            ("config", "--local", "--get", "core.attributesFile"),
        ),
        (
            "local excludes file",
            ("config", "--local", "--get", "core.excludesFile"),
        ),
    )
    for description, args in queries:
        result, unavailable = _git_at_result(context, repository, *args)
        if unavailable:
            cannot_run.append(f"{label}: cannot inspect {description}: {unavailable}")
            continue
        assert result is not None
        if result.returncode == 0 and result.stdout.strip():
            rendered = result.stdout.decode("utf-8", errors="replace").strip()
            errors.append(f"{label}: {description} can conceal bytes: {rendered}")
        elif result.returncode not in {0, 1}:
            cannot_run.append(
                f"{label}: cannot inspect {description}: {_decode_output(result)}"
            )
    worktree_mode, unavailable = _git_at_result(
        context, repository, "config", "--local", "--get", "extensions.worktreeConfig"
    )
    if unavailable:
        cannot_run.append(f"{label}: cannot inspect worktree config mode: {unavailable}")
    elif worktree_mode is not None and worktree_mode.returncode == 0:
        errors.append(f"{label}: extensions.worktreeConfig is not allowed")
    elif worktree_mode is not None and worktree_mode.returncode not in {0, 1}:
        cannot_run.append(
            f"{label}: cannot inspect worktree config mode: {_decode_output(worktree_mode)}"
        )

    effective, unavailable = _git_at_result(
        context,
        repository,
        "config",
        "--local",
        "--show-origin",
        "--get-regexp",
        (
            r"^(filter\.|core\.attributesfile$|core\.excludesfile$|"
            r"core\.fsmonitor$|"
            r"core\.fsmonitorhookversion$|core\.ignorestat$|"
            r"core\.untrackedcache$|submodule\..*\.ignore$)"
        ),
    )
    if unavailable:
        cannot_run.append(f"{label}: cannot inspect effective concealment config: {unavailable}")
    elif effective is not None and effective.returncode == 0 and effective.stdout.strip():
        rendered = effective.stdout.decode("utf-8", errors="replace").strip()
        errors.append(f"{label}: effective Git config can conceal bytes: {rendered}")
    elif effective is not None and effective.returncode not in {0, 1}:
        cannot_run.append(
            f"{label}: cannot inspect effective concealment config: {_decode_output(effective)}"
        )
    bare, unavailable = _git_at_result(
        context, repository, "config", "--local", "--get", "core.bare"
    )
    if unavailable:
        cannot_run.append(f"{label}: cannot inspect core.bare: {unavailable}")
    elif bare is not None and bare.returncode == 0:
        value = bare.stdout.decode("ascii", errors="replace").strip().lower()
        if value != "false":
            errors.append(f"{label}: core.bare must remain false")
    elif bare is not None and bare.returncode not in {0, 1}:
        cannot_run.append(
            f"{label}: cannot inspect core.bare: {_decode_output(bare)}"
        )
    top, unavailable = _git_at_result(
        context, repository, "rev-parse", "--show-toplevel"
    )
    if unavailable:
        cannot_run.append(f"{label}: cannot inspect effective worktree: {unavailable}")
    elif top is None or top.returncode != 0:
        cannot_run.append(
            f"{label}: cannot inspect effective worktree: "
            f"{_decode_output(top) if top is not None else 'no result'}"
        )
    else:
        observed_top = Path(
            top.stdout.decode("utf-8", errors="surrogateescape").strip()
        ).resolve()
        if observed_top != repository.resolve():
            errors.append(
                f"{label}: effective Git worktree differs: "
                f"observed={observed_top}, expected={repository.resolve()}"
            )
    return errors, cannot_run


def _object_type_and_mode_errors(
    context: ValidationContext,
    repository: Path,
    label: str,
    *,
    root_boundary: Path,
    visible_deletions: set[str] | None = None,
) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    errors: list[str] = []
    cannot_run: list[str] = []
    gitlinks: list[tuple[str, str]] = []
    result, unavailable = _git_at_result(context, repository, "ls-files", "--stage", "-z")
    if unavailable:
        return errors, [f"{label}: cannot inspect index object types: {unavailable}"], gitlinks
    assert result is not None
    if result.returncode != 0:
        return (
            errors,
            [f"{label}: cannot inspect index object types: {_decode_output(result)}"],
            gitlinks,
        )
    entries, parse_errors = _parse_stage_entries(result.stdout)
    errors.extend(f"{label}: {error}" for error in parse_errors)
    for mode, object_id, relative in entries:
        try:
            canonical = _canonical_relative(relative, directory=False)
        except ValueError as error:
            errors.append(f"{label}: {error}")
            continue
        path = repository / canonical
        try:
            observed_mode = path.lstat().st_mode
        except FileNotFoundError:
            if visible_deletions is None or canonical not in visible_deletions:
                errors.append(
                    f"{label}: tracked path is absent but not visible as a change: {canonical}"
                )
            continue
        if mode == "160000":
            gitlinks.append((canonical, object_id))
            if not stat.S_ISDIR(observed_mode) or stat.S_ISLNK(observed_mode):
                errors.append(f"{label}: gitlink is not a real directory: {canonical}")
            continue
        if mode == "120000":
            if not stat.S_ISLNK(observed_mode):
                errors.append(f"{label}: tracked symlink changed object type: {canonical}")
                continue
            try:
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError) as error:
                errors.append(f"{label}: tracked symlink cannot resolve: {canonical}: {error}")
                continue
            if root_boundary != resolved and root_boundary not in resolved.parents:
                errors.append(f"{label}: tracked symlink escapes repository: {canonical}")
            continue
        if mode not in {"100644", "100755"}:
            errors.append(f"{label}: unsupported tracked object mode {mode}: {canonical}")
            continue
        if not stat.S_ISREG(observed_mode) or stat.S_ISLNK(observed_mode):
            errors.append(f"{label}: tracked file changed object type: {canonical}")
            continue
        expected_executable = mode == "100755"
        observed_executable = bool(observed_mode & stat.S_IXUSR)
        if expected_executable != observed_executable:
            errors.append(
                f"{label}: tracked executable mode differs from index: {canonical}"
            )
    return errors, cannot_run, gitlinks


def _submodule_errors(
    context: ValidationContext,
    repository: Path,
    label: str,
    gitlinks: list[tuple[str, str]],
    *,
    root_boundary: Path,
    visited: set[Path],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    cannot_run: list[str] = []
    for relative, expected_object in gitlinks:
        submodule = (repository / relative).resolve()
        submodule_label = f"{label} submodule {relative}"
        if root_boundary != submodule and root_boundary not in submodule.parents:
            errors.append(f"{submodule_label}: path escapes repository")
            continue
        if submodule in visited:
            errors.append(f"{submodule_label}: recursive submodule path")
            continue
        if not (submodule / ".git").exists():
            # An uninitialized gitlink has no nested index, so only an empty
            # placeholder directory is admissible.
            try:
                unexpected = sorted(item.name for item in submodule.iterdir())
            except OSError as error:
                cannot_run.append(
                    f"{submodule_label}: cannot inspect uninitialized directory: {error}"
                )
                continue
            if unexpected:
                errors.append(
                    f"{submodule_label}: uninitialized gitlink contains untracked bytes: "
                    f"{unexpected}"
                )
            continue
        visited.add(submodule)
        config_errors, config_unavailable = _local_git_configuration_errors(
            context, submodule, submodule_label
        )
        errors.extend(config_errors)
        cannot_run.extend(config_unavailable)
        if config_errors or config_unavailable:
            # Never run worktree-aware inspection after detecting a hook/filter
            # configuration or after being unable to prove that it is absent.
            continue
        head, unavailable = _git_at_result(context, submodule, "rev-parse", "HEAD")
        if unavailable:
            cannot_run.append(f"{submodule_label}: cannot inspect HEAD: {unavailable}")
        elif head is not None and head.returncode != 0:
            cannot_run.append(f"{submodule_label}: cannot inspect HEAD: {_decode_output(head)}")
        elif head is not None:
            observed = head.stdout.decode("ascii", errors="replace").strip()
            if observed != expected_object:
                errors.append(
                    f"{submodule_label}: checked-out commit differs from gitlink: {observed}"
                )
        nested_change_commands = (
            ("diff-index", "--cached", "--name-only", "-z", "HEAD", "--"),
            ("ls-files", "--others", "--exclude-standard", "-z", "--"),
            (
                "ls-files",
                "--others",
                "--ignored",
                "--exclude-standard",
                "-z",
                "--",
            ),
        )
        for command in nested_change_commands:
            nested_result, unavailable = _git_at_result(context, submodule, *command)
            if unavailable:
                cannot_run.append(
                    f"{submodule_label}: cannot inspect nested changes: {unavailable}"
                )
                continue
            assert nested_result is not None
            if nested_result.returncode != 0:
                cannot_run.append(
                    f"{submodule_label}: cannot inspect nested changes: "
                    f"{_decode_output(nested_result)}"
                )
                continue
            try:
                nested_paths = _nul_paths(nested_result)
            except UnicodeDecodeError as error:
                errors.append(f"{submodule_label}: non-UTF-8 nested path: {error}")
                continue
            if nested_paths:
                errors.append(
                    f"{submodule_label}: staged or untracked paths: {sorted(nested_paths)}"
                )
        raw_changed, raw_errors, raw_unavailable = _raw_tracked_changes(
            context, submodule, submodule_label
        )
        errors.extend(raw_errors)
        cannot_run.extend(raw_unavailable)
        if raw_changed:
            errors.append(
                f"{submodule_label}: raw tracked bytes differ from the nested index: "
                f"{sorted(raw_changed)}"
            )
        flag_errors, flag_unavailable = _index_flag_errors(
            context, submodule, submodule_label
        )
        errors.extend(flag_errors)
        cannot_run.extend(flag_unavailable)
        object_errors, object_unavailable, nested_gitlinks = _object_type_and_mode_errors(
            context,
            submodule,
            submodule_label,
            root_boundary=root_boundary,
        )
        errors.extend(object_errors)
        cannot_run.extend(object_unavailable)
        nested_errors, nested_unavailable = _submodule_errors(
            context,
            submodule,
            submodule_label,
            nested_gitlinks,
            root_boundary=root_boundary,
            visited=visited,
        )
        errors.extend(nested_errors)
        cannot_run.extend(nested_unavailable)
    return errors, cannot_run


def _git_environment_override_errors() -> list[str]:
    errors: list[str] = []
    for variable in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_NAMESPACE",
        "GIT_REPLACE_REF_BASE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_GRAFT_FILE",
    ):
        if os.environ.get(variable):
            errors.append(f"Git environment override is forbidden: {variable}")
    return errors


def _git_concealment_checks(
    context: ValidationContext,
    visible_changes: set[str],
) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    errors: list[str] = []
    cannot_run: list[str] = []
    label = "repository"
    errors.extend(_git_environment_override_errors())

    replace_result, unavailable = _git_result(context, "replace", "-l")
    if unavailable:
        cannot_run.append(f"cannot inspect Git replacements: {unavailable}")
    elif replace_result is not None and replace_result.returncode != 0:
        cannot_run.append(f"cannot inspect Git replacements: {_decode_output(replace_result)}")
    elif replace_result is not None and replace_result.stdout.strip():
        errors.append(
            "Git replacement refs can rewrite the pinned base: "
            f"{replace_result.stdout.decode('ascii', errors='replace').strip()}"
        )

    graft_lines, graft_error = _active_git_metadata_lines(context, "info/grafts")
    if graft_error:
        cannot_run.append(f"cannot inspect Git grafts: {graft_error}")
    elif graft_lines:
        errors.append(f"Git grafts can rewrite the pinned base: {graft_lines}")

    attribute_lines, attribute_error = _active_git_metadata_lines(
        context, "info/attributes"
    )
    if attribute_error:
        cannot_run.append(f"cannot inspect worktree-local attributes: {attribute_error}")
    elif attribute_lines:
        errors.append(
            f"worktree-local Git attributes can conceal bytes: {attribute_lines}"
        )

    core_mode, unavailable = _git_result(context, "config", "--get", "core.fileMode")
    if unavailable:
        cannot_run.append(f"cannot inspect core.fileMode: {unavailable}")
    elif core_mode is None or core_mode.returncode != 0:
        errors.append("core.fileMode must be explicitly true")
    elif core_mode.stdout.decode("ascii", errors="replace").strip().lower() != "true":
        errors.append("core.fileMode must remain true")

    config_errors, config_unavailable = _local_git_configuration_errors(
        context, context.root, label
    )
    errors.extend(config_errors)
    cannot_run.extend(config_unavailable)
    flag_errors, flag_unavailable = _index_flag_errors(context, context.root, label)
    errors.extend(flag_errors)
    cannot_run.extend(flag_unavailable)
    object_errors, object_unavailable, gitlinks = _object_type_and_mode_errors(
        context,
        context.root,
        label,
        root_boundary=context.root,
        visible_deletions=visible_changes,
    )
    errors.extend(object_errors)
    cannot_run.extend(object_unavailable)

    if (context.root / ".gitmodules").is_file():
        ignore_result, unavailable = _git_result(
            context,
            "config",
            "-f",
            ".gitmodules",
            "--get-regexp",
            r"^submodule\..*\.ignore$",
        )
        if unavailable:
            cannot_run.append(f"cannot inspect .gitmodules ignore policy: {unavailable}")
        elif ignore_result is not None and ignore_result.returncode == 0 and ignore_result.stdout.strip():
            errors.append(
                ".gitmodules ignore configuration can conceal submodule edits: "
                f"{ignore_result.stdout.decode('utf-8', errors='replace').strip()}"
            )
        elif ignore_result is not None and ignore_result.returncode not in {0, 1}:
            cannot_run.append(
                f"cannot inspect .gitmodules ignore policy: {_decode_output(ignore_result)}"
            )
    submodule_errors, submodule_unavailable = _submodule_errors(
        context,
        context.root,
        label,
        gitlinks,
        root_boundary=context.root,
        visited={context.root},
    )
    errors.extend(submodule_errors)
    cannot_run.extend(submodule_unavailable)
    return errors, cannot_run, gitlinks


def check_path_ownership(context: ValidationContext) -> CheckResult:
    errors: list[str] = []
    cannot_run: list[str] = []
    errors.extend(_git_environment_override_errors())
    config_errors, config_unavailable = _local_git_configuration_errors(
        context, context.root, "repository"
    )
    errors.extend(config_errors)
    cannot_run.extend(config_unavailable)
    attribute_lines, attribute_error = _active_git_metadata_lines(
        context, "info/attributes"
    )
    if attribute_error:
        cannot_run.append(f"cannot inspect worktree-local attributes: {attribute_error}")
    elif attribute_lines:
        errors.append(
            f"worktree-local Git attributes can conceal bytes: {attribute_lines}"
        )
    active_excludes = _active_info_exclude_patterns(context)
    if active_excludes:
        errors.append(f"worktree-local Git excludes are not allowed: {active_excludes}")
    if errors or cannot_run:
        return _result(
            "path-ownership",
            errors,
            cannot_run=cannot_run,
            passed_summary="unreachable",
        )
    changed, change_errors, change_unavailable = _changed_paths(
        context, context.expected_base_commit
    )
    errors.extend(change_errors)
    cannot_run.extend(change_unavailable)
    raw_changed, raw_errors, raw_unavailable = _raw_tracked_changes(
        context, context.root, "repository"
    )
    changed.update(raw_changed)
    errors.extend(raw_errors)
    cannot_run.extend(raw_unavailable)
    indexed, index_errors, index_unavailable = _indexed_objects(
        context, context.root, "repository"
    )
    errors.extend(index_errors)
    cannot_run.extend(index_unavailable)
    if not HEX_SHA256.fullmatch(context.expected_delivery_tree_sha256):
        errors.append("code-owned delivery-tree checkpoint is not a SHA-256 digest")
    else:
        try:
            observed_delivery = delivery_tree_digest(context.root, changed, indexed)
        except (OSError, UnicodeError, ValueError) as error:
            errors.append(f"cannot compute reviewed delivery-tree digest: {error}")
        else:
            if observed_delivery != context.expected_delivery_tree_sha256:
                errors.append(
                    "reviewed delivery path/mode/byte set differs from the code-owned "
                    f"checkpoint: observed={observed_delivery}, "
                    f"expected={context.expected_delivery_tree_sha256}"
                )
    concealment_errors, concealment_unavailable, _ = _git_concealment_checks(
        context, changed
    )
    errors.extend(concealment_errors)
    cannot_run.extend(concealment_unavailable)
    owner_scopes: dict[str, list[str]] = {}
    bases: set[str] = set()
    forbidden: set[str] = set()
    for change_id, manifest in sorted(context.manifests.items()):
        expected_policy = context.expected_policy_digests.get(change_id)
        if expected_policy is None:
            errors.append(f"{change_id}: no trusted ownership policy is registered")
        elif canonical_json_digest(manifest.get("pathOwnership")) != expected_policy["pathOwnership"]:
            errors.append(f"{change_id}: path ownership differs from the trusted registry")
        base = manifest.get("baseCommit")
        if isinstance(base, str) and HEX_COMMIT.fullmatch(base):
            bases.add(base)
        ownership = manifest.get("pathOwnership")
        if not isinstance(ownership, dict):
            errors.append(f"{change_id}: pathOwnership is not an object")
            continue
        allowed = ownership.get("allowed")
        denied = ownership.get("forbidden")
        if not isinstance(allowed, list) or not allowed:
            errors.append(f"{change_id}: allowed path ownership is empty")
            allowed = []
        if not isinstance(denied, list):
            errors.append(f"{change_id}: forbidden path ownership is not a list")
            denied = []
        normalized_allowed: list[str] = []
        for scope in allowed:
            try:
                canonical = _canonical_relative(scope)
                normalized_allowed.append(canonical)
                owner_scopes.setdefault(change_id, []).append(canonical)
            except ValueError as error:
                errors.append(f"{change_id}: {error}")
        normalized_denied: list[str] = []
        for scope in denied:
            try:
                canonical = _canonical_relative(scope)
                normalized_denied.append(canonical)
                forbidden.add(canonical)
            except ValueError as error:
                errors.append(f"{change_id}: {error}")
        for allowed_scope in normalized_allowed:
            for denied_scope in normalized_denied:
                if _scopes_overlap(allowed_scope, denied_scope):
                    errors.append(
                        f"{change_id}: allowed scope overlaps forbidden scope: "
                        f"{allowed_scope} vs {denied_scope}"
                    )

        artifacts = manifest.get("artifacts", {})
        artifact_paths: list[str] = []
        if isinstance(artifacts, dict):
            for key, value in artifacts.items():
                values = value if key == "specs" and isinstance(value, list) else [value]
                artifact_paths.extend(item for item in values if isinstance(item, str))
        artifact_paths.append(f"openspec/changes/{change_id}/.openspec.yaml")
        for relative in artifact_paths:
            if not any(_scope_contains(scope, relative) for scope in normalized_allowed):
                errors.append(f"{change_id}: artifact is not owned by its change: {relative}")

    owner_ids = sorted(owner_scopes)
    for index, left_id in enumerate(owner_ids):
        for right_id in owner_ids[index + 1 :]:
            for left in owner_scopes[left_id]:
                for right in owner_scopes[right_id]:
                    if _scopes_overlap(left, right):
                        errors.append(
                            f"path ownership overlaps between {left_id} and {right_id}: "
                            f"{left} vs {right}"
                        )

    all_owned_scopes = [scope for scopes in owner_scopes.values() for scope in scopes]
    ignored, unavailable = _git_result(
        context,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "-z",
        "--",
    )
    if unavailable:
        cannot_run.append(f"Git could not inspect ignored untracked paths: {unavailable}")
    elif ignored is None or ignored.returncode != 0:
        cannot_run.append(
            "Git could not inspect ignored untracked paths: "
            f"{_decode_output(ignored) if ignored is not None else 'no result'}"
        )
    else:
        try:
            ignored_paths = _nul_paths(ignored)
        except UnicodeDecodeError as error:
            errors.append(f"Git returned a non-UTF-8 ignored path: {error}")
            ignored_paths = set()
        for relative in sorted(ignored_paths):
            parts = PurePosixPath(relative.rstrip("/")).parts
            try:
                canonical = _canonical_relative(
                    relative, directory=relative.endswith("/")
                )
            except ValueError as error:
                errors.append(str(error))
                continue
            forbidden_overlap = any(
                _scopes_overlap(scope, canonical) for scope in forbidden
            )
            if forbidden_overlap:
                errors.append(
                    "ignored untracked path overlaps forbidden scope: " + canonical
                )
                continue
            cache_exception = (
                canonical.startswith((".pytest_cache/", ".venv/", "node_modules/"))
                or "__pycache__" in parts
                or relative.endswith(".pyc")
            )
            if cache_exception:
                continue
            if (
                any(
                _scopes_overlap(scope, canonical) for scope in all_owned_scopes
                )
            ):
                errors.append(
                    "ignored untracked path overlaps owned scope: " + canonical
                )
            else:
                errors.append(
                    "ignored untracked path is outside reviewed cache exceptions: "
                    + canonical
                )
    if len(bases) != 1:
        errors.append(f"path ownership needs one shared base commit, observed={sorted(bases)}")
    else:
        base = next(iter(bases))
        if base != context.expected_base_commit:
            errors.append(
                "path ownership base moved from reviewed bootstrap: "
                f"observed={base}, expected={context.expected_base_commit}"
            )
        for relative in sorted(changed):
            try:
                canonical = _canonical_relative(relative, directory=False)
            except ValueError as error:
                errors.append(str(error))
                continue
            owners = [
                change_id
                for change_id, scopes in owner_scopes.items()
                if any(_scope_contains(scope, canonical) for scope in scopes)
            ]
            if len(owners) != 1:
                errors.append(
                    f"changed path must have exactly one owner: {canonical}: {owners}"
                )
            if any(_scope_contains(scope, canonical) for scope in forbidden):
                errors.append(f"changed path is forbidden: {canonical}")
            current = context.root
            parts = PurePosixPath(canonical).parts
            for index, part in enumerate(parts):
                current = current / part
                try:
                    observed_mode = current.lstat().st_mode
                except FileNotFoundError:
                    # A deleted path is already visible in the Git change set.
                    break
                if stat.S_ISLNK(observed_mode):
                    errors.append(
                        "changed path contains a symlink or object-type escape: "
                        f"{'/'.join(parts[: index + 1])}"
                    )
                    break

    active_excludes = _active_info_exclude_patterns(context)
    if active_excludes:
        errors.append(f"worktree-local Git excludes are not allowed: {active_excludes}")
    global_excludes, unavailable = _git_result(context, "config", "--get", "core.excludesFile")
    if unavailable:
        cannot_run.append(f"Git could not inspect core.excludesFile: {unavailable}")
    elif global_excludes is not None and global_excludes.returncode == 0:
        value = global_excludes.stdout.decode("utf-8", errors="replace").strip()
        if value:
            errors.append(f"core.excludesFile can conceal untracked paths: {value}")
    elif global_excludes is not None and global_excludes.returncode not in {0, 1}:
        cannot_run.append(f"Git could not inspect core.excludesFile: {_decode_output(global_excludes)}")

    return _result(
        "path-ownership",
        errors,
        cannot_run=cannot_run,
        passed_summary="Every changed path has one disjoint owner and no forbidden overlap",
    )


def check_findings_ledgers(context: ValidationContext) -> CheckResult:
    errors: list[str] = []
    cannot_run: list[str] = []
    if set(context.manifests) != set(context.expected_ledger_prefixes):
        errors.append(
            "active change set differs from the code-owned ledger checkpoint registry: "
            f"observed={sorted(context.manifests)}, "
            f"expected={sorted(context.expected_ledger_prefixes)}"
        )
    for change_id in sorted(set(context.manifests) | set(context.expected_ledger_prefixes)):
        manifest = context.manifests.get(change_id)
        if not isinstance(manifest, dict):
            errors.append(f"{change_id}: active governance is missing for ledger validation")
            relative = f"findings/{change_id}.csv"
        else:
            artifacts = manifest.get("artifacts")
            relative = artifacts.get("findings") if isinstance(artifacts, dict) else None
        if relative != f"findings/{change_id}.csv":
            errors.append(
                f"{change_id}: findings ledger must be findings/{change_id}.csv"
            )
            continue
        try:
            path = _path_without_symlinks(context.root, relative, file=True)
            current_bytes = path.read_bytes()
            text = current_bytes.decode("utf-8")
            reader = csv.reader(io.StringIO(text, newline=""), strict=True)
            rows = list(reader)
        except (OSError, UnicodeDecodeError, ValueError, csv.Error) as error:
            errors.append(f"{change_id}: cannot read findings ledger: {error}")
            continue
        if not rows or tuple(rows[0]) != FINDINGS_HEADER:
            observed = tuple(rows[0]) if rows else ()
            errors.append(
                f"{change_id}: findings header differs: observed={observed}, "
                f"expected={FINDINGS_HEADER}"
            )
            continue

        checkpoint = context.expected_ledger_prefixes.get(change_id)
        if not isinstance(checkpoint, dict):
            errors.append(f"{change_id}: no code-owned ledger checkpoint is registered")
        else:
            expected_length = checkpoint.get("length")
            expected_digest = checkpoint.get("sha256")
            if (
                not isinstance(expected_length, int)
                or isinstance(expected_length, bool)
                or expected_length <= 0
                or not isinstance(expected_digest, str)
                or not HEX_SHA256.fullmatch(expected_digest)
            ):
                errors.append(f"{change_id}: ledger checkpoint registry entry is invalid")
            elif len(current_bytes) < expected_length:
                errors.append(
                    f"{change_id}: findings ledger is shorter than its code-owned checkpoint"
                )
            elif sha256_bytes(current_bytes[:expected_length]) != expected_digest:
                errors.append(
                    f"{change_id}: findings ledger rewrites bytes retained at the "
                    "code-owned checkpoint"
                )
        seen_ids: set[str] = set()
        for row_number, row in enumerate(rows[1:], start=2):
            if not row or not any(row):
                errors.append(f"{change_id}: blank findings row {row_number}")
                continue
            if len(row) != len(FINDINGS_HEADER):
                errors.append(
                    f"{change_id}: findings row {row_number} has {len(row)} fields"
                )
                continue
            record = dict(zip(FINDINGS_HEADER, row, strict=True))
            for column, value in record.items():
                if value != value.strip():
                    errors.append(
                        f"{change_id}: findings row {row_number} has surrounding whitespace in {column}"
                    )
                if value.startswith(("=", "+", "-", "@")):
                    errors.append(
                        f"{change_id}: findings row {row_number} has spreadsheet-active {column}"
                    )
            finding_id = record["finding_id"]
            if not FINDING_ID.fullmatch(finding_id):
                errors.append(f"{change_id}: invalid finding id on row {row_number}")
            if finding_id in seen_ids:
                errors.append(f"{change_id}: duplicate finding id: {finding_id}")
            seen_ids.add(finding_id)
            if record["change_id"] != change_id:
                errors.append(f"{change_id}: row {row_number} names another change")
            if record["reviewer_context"] not in {
                "separate-instance",
                "fresh-subagent",
                "human",
            }:
                errors.append(f"{change_id}: invalid reviewer_context on row {row_number}")
            if record["classification"] not in {"DECISION", "RECORD"}:
                errors.append(f"{change_id}: invalid classification on row {row_number}")
            if record["severity"] not in {"blocker", "major", "minor", "note"}:
                errors.append(f"{change_id}: invalid severity on row {row_number}")
            if record["status"] not in {
                "open",
                "resolved",
                "accepted-risk",
                "not-applicable",
            }:
                errors.append(f"{change_id}: invalid status on row {row_number}")
            for column in ("summary", "evidence", "disposition"):
                if not record[column]:
                    errors.append(
                        f"{change_id}: findings row {row_number} has empty {column}"
                    )
            artifact_path = record["artifact_path"]
            try:
                _path_without_symlinks(context.root, artifact_path, file=True)
            except (OSError, ValueError) as error:
                errors.append(
                    f"{change_id}: invalid artifact_path on row {row_number}: {error}"
                )

        baseline, unavailable = _git_result(
            context,
            "ls-tree",
            "-z",
            "--name-only",
            context.expected_base_commit,
            "--",
            relative,
        )
        if unavailable:
            cannot_run.append(
                f"{change_id}: Git could not inspect findings history: {unavailable}"
            )
        elif baseline is None or baseline.returncode != 0:
            cannot_run.append(
                f"{change_id}: Git could not inspect findings history: "
                f"{_decode_output(baseline) if baseline is not None else 'no result'}"
            )
        elif baseline.stdout:
            prior, unavailable = _git_result(
                context, "show", f"{context.expected_base_commit}:{relative}"
            )
            if unavailable:
                cannot_run.append(
                    f"{change_id}: Git could not read prior findings bytes: {unavailable}"
                )
            elif prior is None or prior.returncode != 0:
                cannot_run.append(
                    f"{change_id}: Git could not read prior findings bytes: "
                    f"{_decode_output(prior) if prior is not None else 'no result'}"
                )
            elif not current_bytes.startswith(prior.stdout):
                errors.append(
                    f"{change_id}: findings ledger rewrites bytes retained at the pinned base"
                )

    return _result(
        "findings-ledger",
        errors,
        cannot_run=cannot_run,
        passed_summary=(
            "Every findings ledger is parseable, typed, change-bound, and preserves "
            "its code-owned checkpoint plus any base-ledger byte prefix"
        ),
    )


def _forbidden_execution_keys(value: Any, prefix: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            location = f"{prefix}.{key}"
            if key.lower() in {
                "command",
                "commands",
                "shell",
                "argv",
                "script",
                "executable",
            }:
                findings.append(location)
            findings.extend(_forbidden_execution_keys(child, location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_forbidden_execution_keys(child, f"{prefix}[{index}]"))
    return findings


def check_runtime_boundary(context: ValidationContext) -> CheckResult:
    errors: list[str] = []
    expected_permissions = {
        "runtimeAllowed": False,
        "externalMutationAllowed": False,
        "heldOutOutcomeAccessAllowed": False,
        "aiSelectorAllowed": False,
        "evidencePromotionAllowed": False,
    }
    expected_checkpoints = [
        {
            "id": "GATE-PLAN",
            "scope": "plan-approval",
            "status": "pending",
            "decisionBinding": None,
        },
        {
            "id": "GATE-RUN",
            "scope": "run-authorization",
            "status": "not-requested",
            "decisionBinding": None,
        },
        {
            "id": "GATE-PROMOTION",
            "scope": "evidence-promotion",
            "status": "not-requested",
            "decisionBinding": None,
        },
    ]
    expected_toolchain = {
        "configPath": CONFIG_PATH,
        "schemaName": "scientific-change",
        "schemaPath": OPEN_SPEC_SCHEMA_PATH,
        "packageJsonPath": "package.json",
        "lockFilePath": "package-lock.json",
        "packageName": OPEN_SPEC_PACKAGE,
        "version": OPEN_SPEC_VERSION,
    }
    for change_id, manifest in sorted(context.manifests.items()):
        expected_policy = context.expected_policy_digests.get(change_id)
        if expected_policy is None:
            errors.append(f"{change_id}: no trusted workflow policy is registered")
        elif canonical_json_digest(manifest.get("workflow")) != expected_policy["workflow"]:
            errors.append(f"{change_id}: workflow state differs from the trusted registry")
        if manifest.get("permissions") != expected_permissions:
            errors.append(f"{change_id}: every dangerous permission must remain false")
        if manifest.get("checkIds") != list(CHECK_IDS):
            errors.append(f"{change_id}: typed check registry is not exact")
        if manifest.get("humanCheckpoints") != expected_checkpoints:
            errors.append(f"{change_id}: human checkpoints exceed the v1 design boundary")
        if manifest.get("openSpec") != expected_toolchain:
            errors.append(f"{change_id}: OpenSpec toolchain declaration is not exact")
        verification = manifest.get("verification")
        if verification != {
            "status": "not-run",
            "independentReviewerRequired": True,
            "reportBinding": None,
        }:
            errors.append(f"{change_id}: verification cannot self-assert completion")
        executable_keys = _forbidden_execution_keys(manifest)
        if executable_keys:
            errors.append(
                f"{change_id}: free-form execution fields are forbidden: {executable_keys}"
            )

    return _result(
        "runtime-boundary",
        errors,
        passed_summary="Runtime and promotion remain unrequested, unauthorized, and ineligible",
    )


CHECK_REGISTRY: dict[str, Callable[[ValidationContext], CheckResult]] = {
    "openspec-config": check_openspec_config,
    "openspec-tool-pin": check_openspec_tool_pin,
    "change-artifacts": check_change_artifacts,
    "governance-schema": check_governance_schema,
    "authority-bindings": check_authority_bindings,
    "path-ownership": check_path_ownership,
    "findings-ledger": check_findings_ledgers,
    "runtime-boundary": check_runtime_boundary,
}


def validate_repository(
    root: Path = DEFAULT_ROOT,
    *,
    runner: Runner = _default_runner,
    expected_base_commit: str = BOOTSTRAP_BASE_COMMIT,
    expected_policy_digests: dict[str, dict[str, str]] | None = None,
    expected_ledger_prefixes: dict[str, dict[str, int | str]] | None = None,
    expected_delivery_tree_sha256: str | None = None,
) -> dict[str, Any]:
    if not HEX_COMMIT.fullmatch(expected_base_commit):
        raise ValueError("expected_base_commit must be a full lowercase Git commit")
    trusted_policies = (
        PINNED_POLICY_DIGESTS
        if expected_policy_digests is None
        else expected_policy_digests
    )
    trusted_ledgers = (
        PINNED_LEDGER_PREFIXES
        if expected_ledger_prefixes is None
        else expected_ledger_prefixes
    )
    trusted_delivery = (
        PINNED_DELIVERY_TREE_SHA256
        if expected_delivery_tree_sha256 is None
        else expected_delivery_tree_sha256
    )
    with tempfile.TemporaryDirectory(prefix="observability-placement-openspec-") as raw:
        context = _discover_context(
            root,
            runner,
            expected_base_commit,
            Path(raw).resolve(),
            trusted_policies,
            trusted_ledgers,
            trusted_delivery,
        )
        checks = [CHECK_REGISTRY[check_id](context) for check_id in CHECK_IDS]
        if any(check.status == "fail" for check in checks):
            status = "fail"
        elif any(check.status == "cannot_run" for check in checks):
            status = "cannot_run"
        else:
            status = "pass"
        return {
            "schemaVersion": 1,
            "status": status,
            "scienceControlValid": status == "pass",
            "runtimeAuthorized": False,
            "promotionEligible": False,
            "changeIds": sorted(context.manifests),
            "checks": [check.as_dict() for check in checks],
            "claimBoundary": (
                "This report checks local OpenSpec structure, an isolated lockfile "
                "tool run, authority bytes, path ownership, and findings format. It "
                "cannot authorize runtime work, inspect held-out outcomes, qualify "
                "evidence, or promote a claim."
            ),
        }


def operation_preflight(
    report: dict[str, Any], root: Path, operation: str, change_id: str
) -> dict[str, Any]:
    diagnostics: list[str] = []
    if operation not in {"apply", "archive"}:
        raise ValueError(f"unsupported governed operation: {operation}")
    if report.get("status") != "pass":
        diagnostics.append(
            f"science-control validation is {report.get('status', 'unknown')}"
        )
    manifest_path = root / "openspec" / "changes" / change_id / "governance.json"
    try:
        manifest = load_json(manifest_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError) as error:
        diagnostics.append(f"cannot read active change governance: {error}")
        manifest = {}
    workflow = manifest.get("workflow") if isinstance(manifest, dict) else None
    state = workflow.get("state") if isinstance(workflow, dict) else None
    if operation == "apply" and state != "local-implementation":
        diagnostics.append(f"change workflow state is {state!r}, not local-implementation")
    if operation == "archive":
        tasks_path = root / "openspec" / "changes" / change_id / "tasks.md"
        try:
            pending = len(
                re.findall(r"^[ \t]*-[ \t]+\[[ \t]\]", tasks_path.read_text(encoding="utf-8"), re.MULTILINE)
            )
        except (OSError, UnicodeDecodeError) as error:
            diagnostics.append(f"cannot inspect archive tasks: {error}")
            pending = 0
        if pending:
            diagnostics.append(f"archive has {pending} incomplete task(s)")
        diagnostics.append(
            "schema version 1 has no external review/approval receipt binding; archive is denied"
        )
    return {
        "operation": operation,
        "changeId": change_id,
        "allowed": not diagnostics,
        "diagnostics": diagnostics,
        "runtimeAuthorized": False,
        "promotionEligible": False,
    }


def run_pinned_openspec(
    root: Path,
    arguments: Sequence[str],
    *,
    runner: Runner = _default_runner,
) -> subprocess.CompletedProcess[bytes]:
    """Run the reviewed OpenSpec package from a fresh offline lockfile install."""

    with tempfile.TemporaryDirectory(prefix="observability-placement-openspec-cli-") as raw:
        context = _discover_context(
            root.resolve(),
            runner,
            BOOTSTRAP_BASE_COMMIT,
            Path(raw).resolve(),
            PINNED_POLICY_DIGESTS,
            PINNED_LEDGER_PREFIXES,
            PINNED_DELIVERY_TREE_SHA256,
        )
        pin = check_openspec_tool_pin(context)
        if pin.status != "pass" or context.openspec_tool is None:
            detail = "; ".join(pin.diagnostics) or pin.summary
            raise RuntimeError(f"pinned OpenSpec preparation is {pin.status}: {detail}")
        return _run_fixed(context, (str(context.openspec_tool), *arguments))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--operation", choices=("validate", "apply", "archive"), default="validate")
    parser.add_argument("--change")
    args = parser.parse_args()
    report = validate_repository(args.root)
    if args.operation != "validate":
        if not args.change or not SLUG.fullmatch(args.change):
            parser.error("--change with a canonical slug is required for operation preflight")
        preflight = operation_preflight(report, args.root.resolve(), args.operation, args.change)
        print(json.dumps(preflight, indent=2, sort_keys=True))
        return 0 if preflight["allowed"] else 4
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] == "pass":
        return 0
    if report["status"] == "cannot_run":
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
