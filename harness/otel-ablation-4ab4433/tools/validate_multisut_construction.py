#!/usr/bin/env python3
"""Validate one or more root-admitted multi-SUT construction children.

The validator is deliberately local and construction-only.  It replays pure
descriptor compilers after their bytes have been matched to root-owned source
bindings.  It never launches a SUT, opens a transport, authorizes a run, reads
held-out outcomes, or promotes evidence.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import types
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, NoReturn

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


ROOT = Path(__file__).resolve().parents[1]
CONTROL_SCHEMA_PATH = "contracts/multisut-construction-control.schema.json"
CONTROL_SCHEMA_ID = (
    "https://observability-placement.local/contracts/"
    "multisut-construction-control.schema.json"
)
REGISTRY_PATH = "contracts/multisut-construction-registry.json"
CHECK_IDS = (
    "construction-schema",
    "parent-and-source",
    "source-bindings",
    "delivery-ownership",
    "protocol-replay",
    "artifact-completeness",
    "abstention-boundary",
    "gate-boundary",
)
EXPECTED_PERMISSIONS = {
    "runtimeAllowed": False,
    "externalMutationAllowed": False,
    "heldOutOutcomeAccessAllowed": False,
    "aiSelectorAllowed": False,
    "evidencePromotionAllowed": False,
}
EXPECTED_CHECKPOINTS = [
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
FINDINGS_HEADER = (
    "finding_id",
    "change_id",
    "reviewer_context",
    "kind",
    "severity",
    "status",
    "artifact",
    "summary",
    "evidence",
    "disposition",
)
HEX_COMMIT = re.compile(r"^[0-9a-f]{40}$")
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
ROOT_COMMIT_SENTINEL = "{{ROOT_TRANSITION_COMMIT}}"
ROOT_TREE_SENTINEL = "{{ROOT_TRANSITION_TREE}}"
RESERVED_FALSE_AUTHORITY_FIELDS = {
    "actionsAuthorized",
    "aiSelectorAllowed",
    "candidateCellEligible",
    "candidateEvidenceAuthorized",
    "candidateEvidenceAllowed",
    "candidateEvidenceEligible",
    "candidateExecutionEnabled",
    "canonical",
    "canonicalEvidenceEligible",
    "canonicalEvidenceAuthorized",
    "comparativeEligible",
    "deletionActionsAuthorized",
    "evidencePromotionAllowed",
    "externalMutationAllowed",
    "externalMutationAuthorized",
    "externalMutationEnabled",
    "heldOutAccessAuthorized",
    "heldOutOutcomeAccessAllowed",
    "heldOutOutcomeAccessAuthorized",
    "kindEvidenceTransferAllowed",
    "pairedContrastEligibleInitially",
    "placementOrSourceCostEligible",
    "promotionAuthorized",
    "promotionAllowed",
    "promotionEligible",
    "runtimeAllowed",
    "runtimeAuthorized",
    "runtimeExecutionAllowed",
    "runtimeExecutionAuthorized",
    "runtimeReady",
}
CURRENT_EVIDENCE_FIELDS = {
    "designEvidenceLabel",
    "evidenceLabel",
    "maximumRunEvidenceLabel",
}
CONSTRUCTION_EVIDENCE_VOCABULARY = {
    "none",
    "method-design-only",
    "construction-only",
    "construction-blocked",
}
CONSTRUCTION_VERDICT_VOCABULARY = {
    "abstain",
    "blocked",
    "construction-fail",
    "construction-pass-runtime-blocked",
}
FORBIDDEN_COMPILER_IMPORTS = {
    "asyncio",
    "docker",
    "http",
    "kubernetes",
    "paramiko",
    "requests",
    "socket",
    "subprocess",
    "urllib",
}


class DuplicateKeyError(ValueError):
    """Reject ambiguous JSON members."""


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise DuplicateKeyError(f"duplicate JSON member: {key}")
        value[key] = item
    return value


def _constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON number: {value}")


def load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_pairs,
        parse_constant=_constant,
    )


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _canonical_file(value: Any) -> str:
    if not isinstance(value, str) or not value or value.endswith("/"):
        raise ValueError(f"not an exact repository file: {value!r}")
    pure = PurePosixPath(value)
    if (
        pure.is_absolute()
        or pure.as_posix() != value
        or any(part in {"", ".", ".."} for part in pure.parts)
        or "\\" in value
        or "//" in value
        or "\x00" in value
    ):
        raise ValueError(f"not a canonical repository file: {value!r}")
    return value


def _safe_file(root: Path, relative: Any) -> Path:
    canonical = _canonical_file(relative)
    current = root.resolve()
    for part in PurePosixPath(canonical).parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError as exc:
            raise ValueError(f"missing repository file: {canonical}") from exc
        if stat.S_ISLNK(mode):
            raise ValueError(f"repository path contains a symlink: {canonical}")
    resolved = current.resolve()
    if root.resolve() not in resolved.parents or not current.is_file():
        raise ValueError(f"repository file escapes root: {canonical}")
    return current


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(root), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "HOME": "/tmp/observability-placement-multisut-git-home",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_NO_REPLACE_OBJECTS": "1",
        },
    )


def _git_output(result: subprocess.CompletedProcess[bytes]) -> str:
    return (result.stdout + result.stderr).decode("utf-8", errors="replace").strip()


@dataclass(frozen=True)
class GitEntry:
    mode: str
    object_type: str
    object_id: str
    path: str

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.mode, self.object_type, self.object_id)


def _tree_entry(root: Path, commit: str, relative: str) -> GitEntry:
    result = _git(root, "ls-tree", "-z", commit, "--", relative)
    if result.returncode != 0:
        raise ValueError(
            f"cannot inspect Git entry {commit}:{relative}: {_git_output(result)}"
        )
    rows = [item for item in result.stdout.split(b"\0") if item]
    if len(rows) != 1:
        raise ValueError(f"Git entry is not one exact path: {commit}:{relative}")
    try:
        metadata, raw_path = rows[0].split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"Git entry cannot be decoded: {commit}:{relative}: {exc}") from exc
    if path != relative or object_type != "blob":
        raise ValueError(
            f"Git entry is not the expected regular blob: {commit}:{relative}"
        )
    return GitEntry(mode, object_type, object_id, path)


def _index_entry(root: Path, relative: str) -> GitEntry:
    result = _git(root, "ls-files", "--stage", "-z", "--", relative)
    if result.returncode != 0:
        raise ValueError(f"cannot inspect index entry {relative}: {_git_output(result)}")
    rows = [item for item in result.stdout.split(b"\0") if item]
    if len(rows) != 1:
        raise ValueError(f"index does not contain one stage-0 entry: {relative}")
    try:
        metadata, raw_path = rows[0].split(b"\t", 1)
        mode, object_id, stage = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"index entry cannot be decoded: {relative}: {exc}") from exc
    if path != relative or stage != "0":
        raise ValueError(f"index does not contain the expected stage-0 path: {relative}")
    return GitEntry(mode, "blob", object_id, path)


def _working_git_mode(path: Path) -> str:
    mode = path.lstat().st_mode
    if not stat.S_ISREG(mode):
        raise ValueError(f"working path is not a regular file: {path}")
    return "100755" if mode & 0o111 else "100644"


def _git_blob_id(payload: bytes, object_id_length: int) -> str:
    framed = b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
    if object_id_length == 40:
        return hashlib.sha1(framed).hexdigest()
    if object_id_length == 64:
        return hashlib.sha256(framed).hexdigest()
    raise ValueError(f"unsupported Git object id length: {object_id_length}")


def _nested_repository_control_errors(root: Path) -> list[str]:
    errors: list[str] = []
    concealment = _git(
        root,
        "config",
        "--local",
        "--get-regexp",
        (
            r"^(include(if)?\.|filter\.|diff\.|core\.attributesfile$|"
            r"core\.excludesfile$|core\.fsmonitor$|"
            r"core\.ignorestat$|core\.untrackedcache$|"
            r"submodule\..*\.ignore$)"
        ),
    )
    if concealment.returncode == 0 and concealment.stdout.strip():
        errors.append(
            "nested local Git configuration can execute or conceal delivery: "
            f"{_git_output(concealment)}"
        )
    elif concealment.returncode not in {0, 1}:
        errors.append(
            f"cannot inspect nested local Git configuration: {_git_output(concealment)}"
        )
    file_mode = _git(root, "config", "--local", "--type=bool", "--get", "core.fileMode")
    if file_mode.returncode != 0 or file_mode.stdout.strip().lower() != b"true":
        errors.append("nested core.fileMode must be explicitly true")
    worktree_config = _git(
        root,
        "config",
        "--local",
        "--type=bool",
        "--get",
        "extensions.worktreeConfig",
    )
    if worktree_config.returncode == 0:
        errors.append("nested extensions.worktreeConfig is not allowed")
    elif worktree_config.returncode not in {0, 1}:
        errors.append(
            "cannot inspect nested extensions.worktreeConfig: "
            f"{_git_output(worktree_config)}"
        )
    bare = _git(root, "config", "--local", "--type=bool", "--get", "core.bare")
    if bare.returncode == 0 and bare.stdout.strip().lower() != b"false":
        errors.append("nested core.bare must remain false")
    elif bare.returncode not in {0, 1}:
        errors.append(f"cannot inspect nested core.bare: {_git_output(bare)}")
    return errors


def _audit_gitlink(
    path: Path,
    expected_commit: str,
    visited: set[Path],
    repository_relative: str,
) -> tuple[bool, list[str]]:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False, []
    except OSError as exc:
        return True, [f"cannot inspect gitlink path: {exc}"]
    if not stat.S_ISDIR(mode):
        return True, ["gitlink working path is not a directory"]
    try:
        contents = list(path.iterdir())
    except OSError as exc:
        return True, [f"cannot enumerate gitlink path: {exc}"]
    top = _git(path, "rev-parse", "--show-toplevel")
    try:
        observed_top = (
            Path(top.stdout.decode("utf-8", errors="strict").strip()).resolve()
            if top.returncode == 0
            else None
        )
    except (OSError, UnicodeDecodeError, ValueError):
        observed_top = None
    resolved = path.resolve()
    if observed_top != resolved:
        if contents:
            return True, ["uninitialized gitlink contains unreviewed payload"]
        return False, []
    if resolved in visited:
        return True, ["recursive gitlink cycle detected"]
    nested_visited = {*visited, resolved}
    errors = _nested_repository_control_errors(path)
    head = _git(path, "rev-parse", "--verify", "HEAD^{commit}")
    observed_head = head.stdout.decode("ascii", errors="replace").strip()
    if head.returncode != 0 or observed_head != expected_commit:
        errors.append(
            "initialized gitlink HEAD differs from the recorded object: "
            f"observed={observed_head!r}, expected={expected_commit}"
        )
    errors.extend(_index_flag_errors(path))
    nested_changed, nested_errors = _raw_index_changes(
        path, nested_visited, repository_relative
    )
    if nested_changed:
        errors.append(
            f"initialized gitlink raw tracked delivery differs: {sorted(nested_changed)}"
        )
    errors.extend(nested_errors)
    if errors:
        return True, errors
    commands = (
        (
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
            "--name-only",
            "-z",
            "--cached",
            "--",
        ),
        ("ls-files", "--others", "--exclude-standard", "-z", "--"),
    )
    for command in commands:
        result = _git(path, *command)
        if result.returncode != 0:
            errors.append(
                f"cannot inspect initialized gitlink delivery ({' '.join(command)}): "
                f"{_git_output(result)}"
            )
            continue
        try:
            observed = sorted(
                item.decode("utf-8")
                for item in result.stdout.split(b"\0")
                if item
            )
        except UnicodeDecodeError as exc:
            errors.append(f"initialized gitlink path is not UTF-8: {exc}")
            continue
        if observed:
            errors.append(
                f"initialized gitlink has staged, working, or untracked delivery: {observed}"
            )
    ignored = _git(
        path,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "--directory",
        "-z",
        "--",
    )
    if ignored.returncode != 0:
        errors.append(f"cannot inspect initialized gitlink ignored delivery: {_git_output(ignored)}")
    else:
        for raw in (item for item in ignored.stdout.split(b"\0") if item):
            try:
                relative = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                errors.append(f"initialized gitlink ignored path is not UTF-8: {exc}")
                continue
            rooted_relative = f"{repository_relative}/{relative}"
            if not _ignored_path_is_cache(rooted_relative):
                errors.append(
                    "initialized gitlink ignored delivery is forbidden: "
                    f"{rooted_relative}"
                )
    return bool(errors), errors


def _raw_index_changes(
    root: Path,
    visited: set[Path] | None = None,
    repository_prefix: str = "",
) -> tuple[set[str], list[str]]:
    if visited is None:
        visited = {root.resolve()}
    result = _git(root, "ls-files", "--stage", "-z", "--")
    if result.returncode != 0:
        return set(), [f"cannot inspect raw tracked delivery: {_git_output(result)}"]
    changed: set[str] = set()
    errors: list[str] = []
    for row in (item for item in result.stdout.split(b"\0") if item):
        try:
            metadata, raw_path = row.split(b"\t", 1)
            mode, object_id, stage = metadata.decode("ascii").split()
            relative = _canonical_file(raw_path.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            errors.append(f"cannot decode raw index entry: {exc}")
            continue
        if stage != "0":
            errors.append(f"raw index entry is not stage 0: {relative}")
            continue
        path = root / relative
        if mode == "160000":
            repository_relative = (
                f"{repository_prefix}/{relative}"
                if repository_prefix
                else relative
            )
            gitlink_changed, gitlink_errors = _audit_gitlink(
                path, object_id, visited, repository_relative
            )
            if gitlink_changed:
                changed.add(relative)
            errors.extend(f"gitlink {relative}: {error}" for error in gitlink_errors)
            continue
        try:
            working_mode = path.lstat().st_mode
            if mode == "120000":
                if not stat.S_ISLNK(working_mode):
                    changed.add(relative)
                    continue
                payload = os.readlink(path).encode("utf-8", errors="surrogateescape")
            elif mode in {"100644", "100755"}:
                if not stat.S_ISREG(working_mode):
                    changed.add(relative)
                    continue
                observed_mode = "100755" if working_mode & 0o111 else "100644"
                if observed_mode != mode:
                    changed.add(relative)
                payload = path.read_bytes()
            else:
                errors.append(f"unsupported raw index mode for {relative}: {mode}")
                continue
        except (OSError, UnicodeError):
            changed.add(relative)
            continue
        try:
            if _git_blob_id(payload, len(object_id)) != object_id:
                changed.add(relative)
        except ValueError as exc:
            errors.append(f"cannot hash raw tracked delivery {relative}: {exc}")
    return changed, errors


def _index_flag_errors(root: Path, watched: set[str] | None = None) -> list[str]:
    result = _git(root, "ls-files", "-v", "-z", "--")
    if result.returncode != 0:
        return [f"cannot inspect index concealment flags: {_git_output(result)}"]
    errors: list[str] = []
    for row in (item for item in result.stdout.split(b"\0") if item):
        try:
            decoded = row.decode("utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"index path is not UTF-8: {exc}")
            continue
        if len(decoded) < 3 or decoded[1] != " ":
            errors.append(f"cannot decode index flag row: {decoded!r}")
            continue
        flag, relative = decoded[0], decoded[2:]
        if watched is not None and relative not in watched:
            continue
        if flag.islower() or flag.upper() == "S":
            errors.append(
                f"index concealment flag is forbidden for {relative}: {flag}"
            )
    return errors


def _ignored_path_is_cache(relative: str) -> bool:
    if any(
        relative == root.rstrip("/") or relative.startswith(root)
        for root in (".local/", "upstream/")
    ):
        return False
    return (
        relative == ".pytest_cache/"
        or relative.startswith(".pytest_cache/")
        or relative == ".venv/"
        or relative.startswith(".venv/")
        or relative == "node_modules/"
        or relative.startswith("node_modules/")
        or "/__pycache__/" in f"/{relative}"
        or relative.endswith((".pyc", ".pyo"))
    )


def changed_paths(root: Path, base_commit: str) -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    errors: list[str] = []
    raw_changed, raw_errors = _raw_index_changes(root)
    changed.update(raw_changed)
    errors.extend(raw_errors)
    commands = (
        (
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
            "--name-only",
            "-z",
            f"{base_commit}..HEAD",
            "--",
        ),
        (
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
            "--name-only",
            "-z",
            "--cached",
            "--",
        ),
        ("ls-files", "--others", "--exclude-standard", "-z", "--"),
    )
    for command in commands:
        result = _git(root, *command)
        if result.returncode != 0:
            errors.append(
                f"cannot enumerate construction delivery ({' '.join(command)}): "
                + (result.stderr.decode("utf-8", errors="replace").strip() or "git failed")
            )
            continue
        try:
            changed.update(
                item.decode("utf-8") for item in result.stdout.split(b"\0") if item
            )
        except UnicodeDecodeError as exc:
            errors.append(f"construction path is not UTF-8: {exc}")
    ignored = _git(
        root,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "--directory",
        "-z",
        "--",
    )
    if ignored.returncode != 0:
        errors.append(f"cannot enumerate ignored delivery: {_git_output(ignored)}")
    else:
        for item in (raw for raw in ignored.stdout.split(b"\0") if raw):
            try:
                relative = item.decode("utf-8")
            except UnicodeDecodeError as exc:
                errors.append(f"ignored construction path is not UTF-8: {exc}")
                continue
            if not _ignored_path_is_cache(relative):
                errors.append(f"ignored construction delivery is forbidden: {relative}")
    errors.extend(_index_flag_errors(root))
    return changed, errors


def _artifact_binding_paths(entry: dict[str, Any]) -> list[str]:
    bindings = entry.get("artifactBindings")
    if not isinstance(bindings, list):
        raise ValueError("artifact bindings are not a list")
    paths: list[str] = []
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ValueError("artifact binding is not an object")
        paths.append(_canonical_file(binding.get("path")))
    if len(paths) != len(set(paths)):
        raise ValueError("artifact binding paths contain duplicates")
    return paths


def derive_admission_commit(
    root: Path, entry: dict[str, Any], transition_commit: str
) -> tuple[str | None, list[str]]:
    """Derive, rather than trust, the child merge from all bound artifact anchors."""

    errors: list[str] = []
    try:
        anchors = _artifact_binding_paths(entry)
    except (TypeError, ValueError) as exc:
        return None, [f"cannot derive child admission anchors: {exc}"]
    commits: set[str] = set()
    for relative in anchors:
        result = _git(root, "log", "-1", "--format=%H", "--", relative)
        commit = result.stdout.decode("ascii", errors="replace").strip()
        if result.returncode != 0 or not HEX_COMMIT.fullmatch(commit):
            errors.append(
                f"cannot derive child admission from {relative}: {_git_output(result)}"
            )
        else:
            commits.add(commit)
    if len(commits) != 1:
        errors.append(
            "bound child artifacts were not introduced by one admission commit: "
            f"{sorted(commits)}"
        )
        return None, errors
    admission = next(iter(commits))
    source = entry.get("adoptedSource")
    source_commit = source.get("commit") if isinstance(source, dict) else None
    parents = _git(root, "rev-list", "--parents", "-n", "1", admission)
    observed_parents = parents.stdout.decode("ascii", errors="replace").split()
    expected_parents = [admission, transition_commit, source_commit]
    if parents.returncode != 0 or observed_parents != expected_parents:
        errors.append(
            "child admission parents differ from ordered [root transition, source]: "
            f"observed={observed_parents}, expected={expected_parents}"
        )
    changed = _git(
        root,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        "-z",
        "--no-renames",
        transition_commit,
        admission,
        "--",
    )
    observed_paths: set[str] = set()
    if changed.returncode != 0:
        errors.append(f"cannot inspect child admission diff: {_git_output(changed)}")
    else:
        try:
            observed_paths = {
                item.decode("utf-8")
                for item in changed.stdout.split(b"\0")
                if item
            }
        except UnicodeDecodeError as exc:
            errors.append(f"child admission path is not UTF-8: {exc}")
    allowed_value = entry.get("allowedPaths")
    allowed = set(allowed_value) if isinstance(allowed_value, list) else set()
    if observed_paths != allowed:
        errors.append(
            "child admission diff differs from exact root ownership: "
            f"missing={sorted(allowed - observed_paths)}, "
            f"extra={sorted(observed_paths - allowed)}"
        )
    return admission, errors


def _artifact_projection(
    raw: bytes, transition_commit: str, transition_tree: str, relative: str
) -> bytes:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"artifact is not UTF-8: {relative}: {exc}") from exc
    if ROOT_COMMIT_SENTINEL in text or ROOT_TREE_SENTINEL in text:
        raise ValueError(f"artifact contains a reserved root projection sentinel: {relative}")
    for identity_name, identity in (
        ("commit", transition_commit),
        ("tree", transition_tree),
    ):
        for length in range(7, len(identity)):
            abbreviation = identity[:length]
            if re.search(
                rf"(?<![0-9a-fA-F]){re.escape(abbreviation)}(?![0-9a-fA-F])",
                text,
                flags=re.IGNORECASE,
            ):
                raise ValueError(
                    f"artifact contains abbreviated root transition {identity_name} "
                    f"identity {abbreviation}: {relative}"
                )
    return (
        text.replace(transition_commit, ROOT_COMMIT_SENTINEL)
        .replace(transition_tree, ROOT_TREE_SENTINEL)
        .encode("utf-8")
    )


@dataclass(frozen=True)
class Check:
    check_id: str
    diagnostics: tuple[str, ...]

    @property
    def status(self) -> str:
        return "pass" if not self.diagnostics else "fail"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.check_id,
            "status": self.status,
            "diagnostics": list(self.diagnostics),
        }


def _check(check_id: str, errors: list[str]) -> Check:
    return Check(check_id, tuple(errors))


def _is_exact_false_mapping(value: Any, expected: dict[str, bool]) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == set(expected)
        and all(value[key] is False for key in expected)
    )


def check_schema(root: Path, manifest: dict[str, Any], _entry: dict[str, Any]) -> Check:
    errors: list[str] = []
    try:
        schema = load_json(_safe_file(root, CONTROL_SCHEMA_PATH))
        if not isinstance(schema, dict) or schema.get("$id") != CONTROL_SCHEMA_ID:
            errors.append("construction schema id differs")
        else:
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
            for failure in sorted(
                validator.iter_errors(manifest), key=lambda item: list(item.absolute_path)
            ):
                location = ".".join(str(item) for item in failure.absolute_path) or "$"
                errors.append(f"{location}: {failure.message}")
    except (OSError, UnicodeDecodeError, ValueError, DuplicateKeyError, SchemaError) as exc:
        errors.append(f"construction schema cannot be checked: {exc}")
    return _check("construction-schema", errors)


def check_parent_and_source(
    root: Path, manifest: dict[str, Any], entry: dict[str, Any]
) -> Check:
    errors: list[str] = []
    expected_parent = entry.get("parentEpoch")
    expected_source = entry.get("adoptedSource")
    if manifest.get("id") != entry.get("changeId"):
        errors.append("change id differs from the root route")
    if manifest.get("parentEpoch") != expected_parent:
        errors.append("parent epoch differs from the root route")
    if manifest.get("adoptedSource") != expected_source:
        errors.append("adopted source differs from the root route")
    if manifest.get("module") != entry.get("module"):
        errors.append("module/family/channel identity differs from the root route")
    workflow = manifest.get("workflow")
    observed_blockers = workflow.get("blockers") if isinstance(workflow, dict) else None
    if observed_blockers != entry.get("blockers"):
        errors.append("construction blockers differ from the root route")
    if isinstance(expected_source, dict):
        commit = expected_source.get("commit")
        tree = _git(root, "show", "-s", "--format=%T", str(commit))
        observed = tree.stdout.decode("ascii", errors="replace").strip()
        if tree.returncode != 0 or observed != expected_source.get("tree"):
            errors.append("adopted source commit/tree cannot be reproduced")
        parents = _git(root, "rev-list", "--parents", "-n", "1", str(commit))
        parts = parents.stdout.decode("ascii", errors="replace").split()
        parent_commit = expected_parent.get("commit") if isinstance(expected_parent, dict) else None
        if parents.returncode != 0 or parts != [commit, parent_commit]:
            errors.append("adopted source is not one commit directly after the parent epoch")
    transition_commit = (
        manifest.get("pathOwnership", {}).get("baseCommit")
        if isinstance(manifest.get("pathOwnership"), dict)
        else None
    )
    if not isinstance(transition_commit, str) or not HEX_COMMIT.fullmatch(
        transition_commit
    ):
        errors.append("derived root transition is missing from path ownership")
    else:
        _, admission_errors = derive_admission_commit(root, entry, transition_commit)
        errors.extend(admission_errors)
    return _check("parent-and-source", errors)


def check_source_bindings(
    root: Path, manifest: dict[str, Any], entry: dict[str, Any]
) -> Check:
    errors: list[str] = []
    expected = entry.get("sourceBindings")
    observed = manifest.get("sourceBindings")
    if observed != expected:
        errors.append("source binding set differs from the root route")
        return _check("source-bindings", errors)
    transition_commit = (
        manifest.get("pathOwnership", {}).get("baseCommit")
        if isinstance(manifest.get("pathOwnership"), dict)
        else None
    )
    admission: str | None = None
    if isinstance(transition_commit, str) and HEX_COMMIT.fullmatch(transition_commit):
        admission, admission_errors = derive_admission_commit(
            root, entry, transition_commit
        )
        errors.extend(admission_errors)
    else:
        errors.append("cannot compare source entries without a derived root transition")
    source = entry.get("adoptedSource")
    adopted_commit = source.get("commit") if isinstance(source, dict) else None
    identities: set[tuple[str, str]] = set()
    for binding in observed if isinstance(observed, list) else []:
        if not isinstance(binding, dict):
            errors.append("source binding is not an object")
            continue
        relative = binding.get("path")
        commit = binding.get("sourceCommit")
        identity = (str(commit), str(relative))
        if identity in identities:
            errors.append(f"duplicate source binding: {identity}")
        identities.add(identity)
        source_bytes = _git(root, "show", f"{commit}:{relative}")
        if (
            source_bytes.returncode != 0
            or sha256_bytes(source_bytes.stdout) != binding.get("sha256")
        ):
            errors.append(f"source bytes differ for {relative}")
            continue
        if commit == adopted_commit and admission is not None:
            try:
                source_entry = _tree_entry(root, str(commit), str(relative))
                admission_entry = _tree_entry(root, admission, str(relative))
            except (TypeError, ValueError) as exc:
                errors.append(str(exc))
                continue
            if source_entry.identity != admission_entry.identity:
                errors.append(
                    f"adopted Git entry differs source-to-admission for {relative}: "
                    f"source={source_entry.identity}, admission={admission_entry.identity}"
                )
    return _check("source-bindings", errors)


def check_delivery(
    root: Path, manifest: dict[str, Any], entry: dict[str, Any]
) -> Check:
    errors: list[str] = []
    ownership = manifest.get("pathOwnership")
    expected = entry.get("allowedPaths")
    if not isinstance(ownership, dict):
        errors.append("path ownership is not an object")
    else:
        if ownership.get("allowed") != expected:
            errors.append("allowed path set differs from the root route")
        if ownership.get("forbidden") != [".local/", "upstream/"]:
            errors.append("forbidden path roots differ")
    try:
        paths = [_canonical_file(item) for item in expected]
    except (TypeError, ValueError) as exc:
        errors.append(f"root-owned allowed path is invalid: {exc}")
        paths = []
    if len(paths) != len(set(paths)):
        errors.append("root-owned allowed path set has duplicates")
    if any(path.startswith((".local/", "upstream/")) for path in paths):
        errors.append("root-owned path set enters a forbidden runtime/upstream root")
    transition_commit = (
        ownership.get("baseCommit") if isinstance(ownership, dict) else None
    )
    admission: str | None = None
    if isinstance(transition_commit, str) and HEX_COMMIT.fullmatch(transition_commit):
        admission, admission_errors = derive_admission_commit(
            root, entry, transition_commit
        )
        errors.extend(admission_errors)
    else:
        errors.append("cannot compare delivered entries without a derived root transition")
    errors.extend(_index_flag_errors(root, set(paths)))
    if admission is not None:
        for relative in paths:
            try:
                admission_entry = _tree_entry(root, admission, relative)
                index_entry = _index_entry(root, relative)
                current = _safe_file(root, relative)
                working_mode = _working_git_mode(current)
                blob = _git(root, "cat-file", "blob", admission_entry.object_id)
                if blob.returncode != 0:
                    raise ValueError(
                        f"cannot read admission blob for {relative}: {_git_output(blob)}"
                    )
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
                continue
            if index_entry.identity != admission_entry.identity:
                errors.append(
                    f"index entry differs from child admission for {relative}: "
                    f"index={index_entry.identity}, admission={admission_entry.identity}"
                )
            if working_mode != admission_entry.mode:
                errors.append(
                    f"working mode differs from child admission for {relative}: "
                    f"working={working_mode}, admission={admission_entry.mode}"
                )
            if current.read_bytes() != blob.stdout:
                errors.append(f"working bytes differ from child admission for {relative}")
    return _check("delivery-ownership", errors)


def _load_protocol(root: Path, relative: str, change_id: str):
    path = _safe_file(root, relative)
    name = "multisut_protocol_" + change_id.replace("-", "_")
    source = path.read_bytes()
    source.decode("utf-8")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = None
    module.__loader__ = None
    module.__spec__ = None
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


@contextmanager
def _isolated_repository_bytecode():
    """Force nested source loaders away from ignored repository bytecode caches."""

    previous_prefix = sys.pycache_prefix
    previous_dont_write = sys.dont_write_bytecode
    with tempfile.TemporaryDirectory(prefix="multisut-bytecode-") as raw:
        sys.pycache_prefix = raw
        sys.dont_write_bytecode = True
        try:
            yield
        finally:
            sys.pycache_prefix = previous_prefix
            sys.dont_write_bytecode = previous_dont_write


def _compiler_import_errors(path: Path) -> list[str]:
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    forbidden = sorted(imports & FORBIDDEN_COMPILER_IMPORTS)
    return [f"protocol compiler imports forbidden runtime surface: {forbidden}"] if forbidden else []


def _plan_digest(module: Any, plan: dict[str, Any]) -> tuple[str, list[str]]:
    """Return the compiler's own plan identity, supporting a bound self-digest."""

    errors: list[str] = []
    declared = plan.get("planCanonicalSha256")
    if declared is not None:
        body = {
            key: value for key, value in plan.items() if key != "planCanonicalSha256"
        }
        recomputed = module.canonical_sha256(body)
        if declared != recomputed:
            errors.append("compiled plan self-digest does not recompute")
        return str(declared), errors
    runs_digest = plan.get("runsSha256")
    if runs_digest is not None:
        if not isinstance(plan.get("runs"), list):
            errors.append("runsSha256 exists without a typed run list")
        elif runs_digest != module.canonical_sha256(plan["runs"]):
            errors.append("compiled run-list digest does not recompute")
        return str(runs_digest), errors
    return module.canonical_sha256(plan), errors


def _true_authority_errors(value: Any, prefix: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            location = f"{prefix}.{key}"
            if key in RESERVED_FALSE_AUTHORITY_FIELDS and item is not False:
                errors.append(
                    f"{location} must be the exact JSON boolean false, observed={item!r}"
                )
            if (
                key in CURRENT_EVIDENCE_FIELDS
                and item not in CONSTRUCTION_EVIDENCE_VOCABULARY
            ):
                errors.append(
                    f"{location} exceeds the construction-only evidence vocabulary: "
                    f"{item!r}"
                )
            if key == "verdict" and item not in CONSTRUCTION_VERDICT_VOCABULARY:
                errors.append(
                    f"{location} exceeds the blocked/construction verdict vocabulary: "
                    f"{item!r}"
                )
            errors.extend(_true_authority_errors(item, location))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(_true_authority_errors(item, f"{prefix}[{index}]"))
    return errors


def check_protocol(
    root: Path, manifest: dict[str, Any], entry: dict[str, Any]
) -> Check:
    errors: list[str] = []
    expected = entry.get("protocolBindings")
    observed = manifest.get("protocolBindings")
    if observed != expected:
        errors.append("protocol binding differs from the root route")
        return _check("protocol-replay", errors)
    try:
        descriptor_binding = expected["descriptor"]
        compiler_binding = expected["compiler"]
        descriptor_path = _safe_file(root, descriptor_binding["path"])
        compiler_path = _safe_file(root, compiler_binding["path"])
        if sha256_file(descriptor_path) != descriptor_binding["byteSha256"]:
            errors.append("descriptor bytes differ")
        if sha256_file(compiler_path) != compiler_binding["sha256"]:
            errors.append("protocol compiler bytes differ")
        errors.extend(_compiler_import_errors(compiler_path))
        if errors:
            return _check("protocol-replay", errors)
        with _isolated_repository_bytecode():
            module = _load_protocol(
                root, compiler_binding["path"], entry["changeId"]
            )
            required = (
                "load_descriptor",
                "compile_plan",
                "readiness_report",
                "canonical_sha256",
            )
            missing = [
                name for name in required if not callable(getattr(module, name, None))
            ]
            if missing:
                errors.append(f"pure construction API is incomplete: {missing}")
                return _check("protocol-replay", errors)
            document = module.load_descriptor(descriptor_path)
            plan = module.compile_plan(document)
            report = module.readiness_report(document, plan)
        if module.canonical_sha256(document) != descriptor_binding["canonicalSha256"]:
            errors.append("canonical descriptor replay differs")
        plan_binding = expected["compiledPlan"]
        observed_plan_digest, digest_errors = _plan_digest(module, plan)
        errors.extend(digest_errors)
        if observed_plan_digest != plan_binding["canonicalSha256"]:
            errors.append("canonical plan replay differs")
        observed_run_count = plan.get("runCount")
        if (
            type(observed_run_count) is not int
            or observed_run_count != plan_binding["runCount"]
        ):
            errors.append("compiled run count is not the exact registered integer")
        errors.extend(_true_authority_errors(plan, "$.plan"))
        errors.extend(_true_authority_errors(report, "$.receipt"))
        positive = [
            report.get("constructionValid"),
            report.get("constructionReady"),
            report.get("valid"),
        ]
        construction_check = any(
            isinstance(item, dict)
            and item.get("id") == "construction-contract"
            and item.get("status") in {"pass", "passed"}
            for item in report.get("checks", [])
        ) if isinstance(report.get("checks"), list) else False
        if not any(item is True for item in positive) and not construction_check:
            errors.append("construction receipt has no positive structural-validity field")
        if report.get("blockers") != entry.get("blockers"):
            errors.append("construction receipt blockers differ from the root route")
    except (
        AttributeError,
        ImportError,
        OSError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
    ) as exc:
        errors.append(f"protocol replay cannot run: {exc}")
    return _check("protocol-replay", errors)


def _expected_artifacts(change_id: str) -> dict[str, Any]:
    root = f"openspec/changes/{change_id}"
    return {
        "proposal": f"{root}/proposal.md",
        "authority": f"{root}/authority.md",
        "specs": [f"{root}/specs/{change_id}/spec.md"],
        "design": f"{root}/design.md",
        "tasks": f"{root}/tasks.md",
        "verification": f"{root}/verification.md",
        "governance": f"{root}/governance.json",
        "findings": f"findings/{change_id}.csv",
    }


def check_artifacts(
    root: Path, manifest: dict[str, Any], entry: dict[str, Any]
) -> Check:
    errors: list[str] = []
    change_id = entry["changeId"]
    expected = _expected_artifacts(change_id)
    if manifest.get("artifacts") != expected:
        errors.append("artifact map differs from the closed change layout")
        return _check("artifact-completeness", errors)
    marker = f"openspec/changes/{change_id}/.openspec.yaml"
    artifact_paths = {
        marker,
        expected["authority"],
        expected["design"],
        expected["governance"],
        expected["proposal"],
        expected["specs"][0],
        expected["tasks"],
        expected["verification"],
    }
    bindings_value = entry.get("artifactBindings")
    bindings: dict[str, dict[str, Any]] = {}
    if not isinstance(bindings_value, list):
        errors.append("artifact bindings are not a list")
    else:
        for binding in bindings_value:
            if not isinstance(binding, dict) or not isinstance(binding.get("path"), str):
                errors.append("artifact binding is not a typed object")
                continue
            relative = binding["path"]
            if relative in bindings:
                errors.append(f"duplicate artifact binding: {relative}")
            bindings[relative] = binding
    if set(bindings) != artifact_paths:
        errors.append(
            "artifact binding coverage differs from the immutable OpenSpec set: "
            f"missing={sorted(artifact_paths - set(bindings))}, "
            f"extra={sorted(set(bindings) - artifact_paths)}"
        )

    all_artifact_paths = [
        marker,
        *[
            item
            for value in expected.values()
            for item in (value if isinstance(value, list) else [value])
        ],
    ]
    for relative in all_artifact_paths:
        try:
            path = _safe_file(root, relative)
            if path.stat().st_size == 0:
                errors.append(f"artifact is empty: {relative}")
            if relative != expected["findings"]:
                path.read_bytes().decode("utf-8")
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
        except UnicodeDecodeError as exc:
            errors.append(f"artifact is not UTF-8: {relative}: {exc}")

    transition_commit = (
        manifest.get("pathOwnership", {}).get("baseCommit")
        if isinstance(manifest.get("pathOwnership"), dict)
        else None
    )
    transition_tree: str | None = None
    if isinstance(transition_commit, str) and HEX_COMMIT.fullmatch(transition_commit):
        tree = _git(root, "show", "-s", "--format=%T", transition_commit)
        observed_tree = tree.stdout.decode("ascii", errors="replace").strip()
        if tree.returncode != 0 or not HEX_COMMIT.fullmatch(observed_tree):
            errors.append(
                f"cannot derive root transition tree for artifact projection: "
                f"{_git_output(tree)}"
            )
        else:
            transition_tree = observed_tree
    else:
        errors.append("cannot project artifact bindings without a root transition")
    if transition_tree is not None:
        for relative in sorted(artifact_paths):
            binding = bindings.get(relative)
            if binding is None:
                continue
            if binding.get("mode") != "100644":
                errors.append(f"artifact binding mode is not 100644: {relative}")
            try:
                path = _safe_file(root, relative)
                if _working_git_mode(path) != "100644":
                    errors.append(f"artifact working mode is not 100644: {relative}")
                projected = _artifact_projection(
                    path.read_bytes(), transition_commit, transition_tree, relative
                )
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
                continue
            if sha256_bytes(projected) != binding.get("sha256"):
                errors.append(f"canonical artifact projection differs for {relative}")
    try:
        marker_text = _safe_file(root, marker).read_text(encoding="utf-8")
        if "schema: scientific-change" not in marker_text.splitlines():
            errors.append("OpenSpec marker does not select scientific-change")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        errors.append(f"OpenSpec marker cannot be decoded: {exc}")
    try:
        raw_findings = _safe_file(root, expected["findings"]).read_bytes()
        text_findings = raw_findings.decode("utf-8")
        rows = list(csv.reader(io.StringIO(text_findings, newline=""), strict=True))
        expected_findings = (",".join(FINDINGS_HEADER) + "\n").encode("utf-8")
        if raw_findings != expected_findings:
            errors.append(
                "not-run findings ledger must be the exact root-owned header-only bytes"
            )
        if rows != [list(FINDINGS_HEADER)]:
            errors.append("findings ledger does not decode as one exact header row")
    except (OSError, UnicodeDecodeError, ValueError, csv.Error) as exc:
        errors.append(f"findings ledger cannot be decoded: {exc}")
    return _check("artifact-completeness", errors)


def check_abstention(
    _root: Path, manifest: dict[str, Any], entry: dict[str, Any]
) -> Check:
    errors: list[str] = []
    workflow = manifest.get("workflow")
    protocol = manifest.get("protocolBindings")
    verification = manifest.get("verification")
    if workflow != {"state": "construction-blocked", "blockers": entry.get("blockers")}:
        errors.append("workflow does not preserve the root-owned blocked state")
    if not isinstance(protocol, dict) or protocol.get("canonical") is not False:
        errors.append("construction protocol is mislabeled canonical")
    if not isinstance(protocol, dict) or protocol.get("maximumFutureRunEvidenceLabel") not in {
        "smoke-validation",
        "candidate-evidence",
    }:
        errors.append("future evidence ceiling is missing or unknown")
    if verification != {
        "status": "not-run",
        "independentReviewerRequired": True,
        "reportBinding": None,
    }:
        errors.append("verification/review state is not a typed abstention")
    return _check("abstention-boundary", errors)


def check_gates(
    _root: Path, manifest: dict[str, Any], _entry: dict[str, Any]
) -> Check:
    errors: list[str] = []
    if not _is_exact_false_mapping(manifest.get("permissions"), EXPECTED_PERMISSIONS):
        errors.append("dangerous permissions are not all false")
    if manifest.get("humanCheckpoints") != EXPECTED_CHECKPOINTS:
        errors.append("human checkpoints differ from pending/not-requested state")
    if manifest.get("checkIds") != list(CHECK_IDS):
        errors.append("typed check registry differs")
    return _check("gate-boundary", errors)


CHECKS: tuple[Callable[[Path, dict[str, Any], dict[str, Any]], Check], ...] = (
    check_schema,
    check_parent_and_source,
    check_source_bindings,
    check_delivery,
    check_protocol,
    check_artifacts,
    check_abstention,
    check_gates,
)


def validate_change(
    root: Path,
    entry: dict[str, Any],
    *,
    delivery_base_commit: str,
    repository_delivery_errors: tuple[str, ...] = (),
) -> dict[str, Any]:
    change_id = entry.get("changeId")
    errors: list[str] = []
    try:
        manifest_value = load_json(
            _safe_file(root, f"openspec/changes/{change_id}/governance.json")
        )
        if not isinstance(manifest_value, dict):
            raise ValueError("governance is not an object")
        manifest = manifest_value
    except (OSError, UnicodeDecodeError, ValueError, DuplicateKeyError) as exc:
        manifest = {}
        errors.append(f"governance cannot be parsed: {exc}")
    ownership = manifest.get("pathOwnership")
    if not isinstance(ownership, dict) or ownership.get("baseCommit") != delivery_base_commit:
        errors.append("path ownership base differs from the derived root transition")
    by_id: dict[str, Check] = {}
    for expected_check_id, checker in zip(CHECK_IDS, CHECKS):
        if expected_check_id == "protocol-replay":
            continue
        try:
            result = checker(root, manifest, entry)
        except Exception as exc:
            result = Check(
                expected_check_id,
                (
                    "non-executable admission check failed closed: "
                    f"{type(exc).__name__}: {exc}",
                ),
            )
        if result.check_id != expected_check_id:
            result = Check(
                expected_check_id,
                (
                    "registered checker returned the wrong id: "
                    f"observed={result.check_id}, expected={expected_check_id}",
                    *result.diagnostics,
                ),
            )
        by_id[expected_check_id] = result
    if errors:
        schema_check = by_id.get("construction-schema", Check("construction-schema", ()))
        by_id["construction-schema"] = Check(
            "construction-schema", (*schema_check.diagnostics, *errors)
        )
    failed_admission_checks = [
        check_id
        for check_id in CHECK_IDS
        if check_id != "protocol-replay"
        and (
            check_id not in by_id
            or by_id[check_id].status != "pass"
        )
    ]
    protocol_diagnostics: list[str] = []
    if failed_admission_checks:
        protocol_diagnostics.append(
            "not executed because non-executable admission checks failed: "
            f"{failed_admission_checks}"
        )
    if repository_delivery_errors:
        protocol_diagnostics.append(
            "not executed because the repository-wide delivery gate failed: "
            f"{list(repository_delivery_errors)}"
        )
    if protocol_diagnostics:
        by_id["protocol-replay"] = Check(
            "protocol-replay",
            tuple(protocol_diagnostics),
        )
    else:
        try:
            by_id["protocol-replay"] = check_protocol(root, manifest, entry)
        except Exception as exc:
            by_id["protocol-replay"] = Check(
                "protocol-replay",
                (f"protocol replay failed closed: {type(exc).__name__}: {exc}",),
            )
    checks = [
        by_id.get(
            check_id,
            Check(check_id, ("registered check did not produce a result",)),
        )
        for check_id in CHECK_IDS
    ]
    status = "pass" if all(item.status == "pass" for item in checks) else "fail"
    admission_commit, _ = derive_admission_commit(
        root, entry, delivery_base_commit
    )
    return {
        "schemaVersion": 3,
        "changeId": change_id,
        "admissionCommit": admission_commit,
        "status": status,
        "constructionControlValid": status == "pass",
        "runtimeAuthorized": False,
        "promotionEligible": False,
        "checks": [item.as_dict() for item in checks],
        "claimBoundary": (
            "Local deterministic construction replay only; no SUT execution, "
            "external mutation, candidate qualification, canonical evidence, or promotion."
        ),
    }


def validate_repository(
    root: Path,
    entries: list[dict[str, Any]],
    *,
    delivery_base_commit: str,
) -> dict[str, Any]:
    changed, delivery_errors = changed_paths(root, delivery_base_commit)
    allowed_sets = [set(entry.get("allowedPaths", [])) for entry in entries]
    allowed = set().union(*allowed_sets) if allowed_sets else set()
    overlaps: set[str] = set()
    seen: set[str] = set()
    for paths in allowed_sets:
        overlaps.update(seen & paths)
        seen.update(paths)
    if overlaps:
        delivery_errors.append(f"active child ownership overlaps: {sorted(overlaps)}")
    if changed != allowed:
        delivery_errors.append(
            "active child delivery differs from exact root ownership: "
            f"missing={sorted(allowed - changed)}, extra={sorted(changed - allowed)}"
        )
    repository_delivery_errors = tuple(delivery_errors)
    reports = [
        validate_change(
            root,
            entry,
            delivery_base_commit=delivery_base_commit,
            repository_delivery_errors=repository_delivery_errors,
        )
        for entry in entries
    ]
    status = (
        "pass"
        if not delivery_errors and all(item["status"] == "pass" for item in reports)
        else "fail"
    )
    return {
        "schemaVersion": 3,
        "status": status,
        "constructionControlValid": status == "pass",
        "runtimeAuthorized": False,
        "promotionEligible": False,
        "changeReports": reports,
        "deliveryDiagnostics": delivery_errors,
    }


__all__ = [
    "CHECKS",
    "CHECK_IDS",
    "Check",
    "EXPECTED_CHECKPOINTS",
    "EXPECTED_PERMISSIONS",
    "ROOT_COMMIT_SENTINEL",
    "ROOT_TREE_SENTINEL",
    "changed_paths",
    "check_abstention",
    "check_artifacts",
    "check_delivery",
    "check_gates",
    "check_parent_and_source",
    "check_protocol",
    "check_schema",
    "check_source_bindings",
    "derive_admission_commit",
    "load_json",
    "validate_change",
    "validate_repository",
]
