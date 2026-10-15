#!/usr/bin/env python3
"""Run reviewed OpenSpec bytes without trusting the ignored project install."""

from __future__ import annotations

import hashlib
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_JSON_SHA256 = "172fe9b976d30c54fbe45ae6dd0de87c7fed2f6b9965448871404d882871c4b2"
PACKAGE_LOCK_SHA256 = "2bafb850b9074f710f5b18a259ed30ceeb980473aa53a4bf667eeea8dfc97ef0"
PYPROJECT_SHA256 = "0841491ffb92e4931b8629683ac61df6d3fe04235bba3ec11270d26ac58cc020"
UV_LOCK_SHA256 = "f8dd0f695bfdfc8e556e857f2a190f97355ad1c2fb9f7bd3b30e5ba96cde8b2b"
ROUTER_SHA256 = "62dd0a9781f6509688448f38565627c400769d6a03716512f252be067c8c9a72"
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
GLOBAL_FLAGS = {"--no-color", "-V", "--version", "-h", "--help"}
DENIED_TOP_LEVEL = {
    "completion",
    "config",
    "feedback",
    "init",
    "new",
    "store",
    "update",
    "workset",
}
READ_ONLY_TOP_LEVEL = {
    "change",
    "context",
    "doctor",
    "help",
    "instructions",
    "list",
    "schema",
    "schemas",
    "show",
    "spec",
    "status",
    "templates",
    "validate",
}
READ_ONLY_NESTED = {
    "change": {"help", "list", "show", "validate"},
    "schema": {"help", "validate", "which"},
    "spec": {"help", "list", "show", "validate"},
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _option(arguments: List[str], name: str) -> Optional[str]:
    try:
        index = arguments.index(name)
    except ValueError:
        return None
    if index + 1 >= len(arguments):
        return None
    return arguments[index + 1]


def _command_tokens(arguments: List[str]) -> List[str]:
    """Remove only the exact no-argument global flags supported by OpenSpec 1.11."""

    tokens = [argument for argument in arguments if argument not in GLOBAL_FLAGS]
    if tokens and tokens[0].startswith("-"):
        raise ValueError(f"unsupported leading global option: {tokens[0]}")
    return tokens


def _preflight_request(arguments: List[str]) -> Optional[Tuple[str, str]]:
    tokens = _command_tokens(arguments)
    if not tokens:
        return None
    if tokens[0] == "archive":
        change_id = next(
            (value for value in tokens[1:] if not value.startswith("-")), None
        )
        return ("archive", change_id or "")
    if tokens[0] == "instructions":
        operation = next(
            (value for value in tokens[1:] if value in {"apply", "archive"}),
            None,
        )
        if operation is not None:
            return (operation, _option(tokens, "--change") or "")
    return None


def _enforce_command_allowlist(arguments: List[str]) -> None:
    tokens = _command_tokens(arguments)
    if not tokens:
        return
    forbidden_options = {
        "--code-workspace",
        "--fix",
        "--force",
        "--output",
        "--schema",
        "--store",
        "--write",
    }
    option_names = {
        token.partition("=")[0] for token in tokens if token.startswith("-")
    }
    observed_forbidden = sorted(forbidden_options.intersection(option_names))
    if observed_forbidden:
        raise ValueError(
            "OpenSpec option can mutate repository or external state and is denied: "
            + ", ".join(observed_forbidden)
        )
    command = tokens[0]
    if command in DENIED_TOP_LEVEL:
        raise ValueError(f"mutating or external OpenSpec command is denied: {command}")
    if command == "archive":
        return
    if command not in READ_ONLY_TOP_LEVEL:
        raise ValueError(f"OpenSpec command is not in the reviewed allowlist: {command}")
    allowed_nested = READ_ONLY_NESTED.get(command)
    if allowed_nested is not None:
        nested = next(
            (value for value in tokens[1:] if not value.startswith("-")), None
        )
        if nested is not None and nested not in allowed_nested:
            raise ValueError(
                f"OpenSpec {command} subcommand is not read-only: {nested}"
            )


def _trusted_executable(name: str) -> Path:
    candidates = [
        str(Path(prefix) / name)
        for prefix in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin")
    ]
    user_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    candidates.extend(
        str(path)
        for path in sorted(
            (user_home / ".nvm" / "versions" / "node").glob("*/bin/{0}".format(name)),
            reverse=True,
        )
    )
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            continue
        if ROOT == resolved or ROOT in resolved.parents:
            continue
        if os.access(path, os.X_OK):
            return path
    raise RuntimeError("trusted host executable is unavailable: {0}".format(name))


def _run_science_preflight(
    operation: str, change_id: str = ""
) -> subprocess.CompletedProcess:
    pinned_files = {
        ROOT / "pyproject.toml": PYPROJECT_SHA256,
        ROOT / "uv.lock": UV_LOCK_SHA256,
        ROOT / "tools" / "validate_science_epochs_v3.py": ROUTER_SHA256,
    }
    for path, expected in pinned_files.items():
        if _sha256(path) != expected:
            raise RuntimeError(
                "science preflight input differs from reviewed bytes: {0}".format(
                    path.relative_to(ROOT)
                )
            )
    uv = _trusted_executable("uv")
    user_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    with tempfile.TemporaryDirectory(prefix="observability-placement-science-preflight-") as raw:
        controlled_home = Path(raw).resolve()
        environment = {
            "PATH": os.pathsep.join((str(uv.parent), "/usr/bin", "/bin")),
            "HOME": str(controlled_home),
            "PYTHONDONTWRITEBYTECODE": "1",
            "UV_CACHE_DIR": str(user_home / ".cache" / "uv"),
            "UV_OFFLINE": "1",
            "UV_FROZEN": "1",
        }
        command = [
                str(uv),
                "run",
                "--project",
                str(ROOT),
                "--isolated",
                "--frozen",
                "--offline",
                "--no-dev",
                "--no-editable",
                "--no-env-file",
                "--no-config",
                "python",
                "-I",
                str(ROOT / "tools" / "validate_science_epochs_v3.py"),
                "--root",
                str(ROOT),
        ]
        if operation != "validate":
            command.extend(("--operation", operation, "--change", change_id))
        return subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )


def _controlled_environment(install_root: Path, npm: Path, node: Path) -> Dict[str, str]:
    controlled_home = install_root / "home"
    controlled_home.mkdir()
    user_config = controlled_home / ".npmrc"
    user_config.touch()
    cache = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".npm"
    path = os.pathsep.join(
        dict.fromkeys([str(npm.parent), str(node.parent), "/usr/bin", "/bin"])
    )
    return {
        "PATH": path,
        "HOME": str(controlled_home),
        "OPENSPEC_TELEMETRY": "0",
        "OPENSPEC_NO_UPDATE_CHECK": "1",
        "npm_config_cache": str(cache),
        "npm_config_userconfig": str(user_config),
        "npm_config_globalconfig": "/dev/null",
        "npm_config_ignore_scripts": "true",
        "npm_config_offline": "true",
        "npm_config_audit": "false",
        "npm_config_fund": "false",
    }


def _run_pinned(arguments: Sequence[str]) -> subprocess.CompletedProcess:
    package = ROOT / "package.json"
    lock = ROOT / "package-lock.json"
    if _sha256(package) != PACKAGE_JSON_SHA256:
        raise RuntimeError("package.json differs from the reviewed tool pin")
    if _sha256(lock) != PACKAGE_LOCK_SHA256:
        raise RuntimeError("package-lock.json differs from the reviewed dependency graph")
    npm = _trusted_executable("npm")
    node = _trusted_executable("node")
    with tempfile.TemporaryDirectory(
        prefix="observability-placement-openspec-cli-"
    ) as raw:
        install_root = Path(raw).resolve()
        shutil.copyfile(package, install_root / "package.json")
        shutil.copyfile(lock, install_root / "package-lock.json")
        environment = _controlled_environment(install_root, npm, node)
        install = subprocess.run(
            [
                str(npm),
                "ci",
                "--ignore-scripts",
                "--offline",
                "--no-audit",
                "--no-fund",
            ],
            cwd=install_root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if install.returncode != 0:
            detail = (install.stdout + install.stderr).decode(
                "utf-8", errors="replace"
            )
            raise RuntimeError("isolated lockfile install failed: " + detail.strip())
        tool = install_root / "node_modules" / ".bin" / "openspec"
        resolved = tool.resolve(strict=True)
        if install_root != resolved and install_root not in resolved.parents:
            raise RuntimeError("isolated OpenSpec executable escapes its install")
        return subprocess.run(
            [str(tool), *arguments],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )


def main() -> int:
    arguments = sys.argv[1:]
    if not arguments:
        print("usage: run_openspec.py <openspec arguments>", file=sys.stderr)
        return 64
    if arguments == ["science-validate"]:
        try:
            validation = _run_science_preflight("validate")
        except (OSError, RuntimeError) as error:
            print("science validation could not run: {0}".format(error), file=sys.stderr)
            return 3
        sys.stdout.buffer.write(validation.stdout)
        sys.stderr.buffer.write(validation.stderr)
        return validation.returncode
    try:
        _enforce_command_allowlist(arguments)
        requested = _preflight_request(arguments)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 64
    if requested is not None:
        operation, change_id = requested
        if not SLUG.fullmatch(change_id):
            print(
                "invalid or missing change id for {0}".format(operation),
                file=sys.stderr,
            )
            return 64
        try:
            preflight = _run_science_preflight(operation, change_id)
        except (OSError, RuntimeError) as error:
            print("science preflight could not run: {0}".format(error), file=sys.stderr)
            return 3
        if preflight.returncode != 0:
            print(
                "DENY {0}: full science-control preflight did not authorize the "
                "operation".format(operation),
                file=sys.stderr,
            )
            sys.stderr.buffer.write(preflight.stdout)
            sys.stderr.buffer.write(preflight.stderr)
            return 4

    try:
        result = _run_pinned(arguments)
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 3
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
