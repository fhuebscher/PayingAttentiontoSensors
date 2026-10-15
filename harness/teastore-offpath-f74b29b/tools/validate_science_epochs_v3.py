#!/usr/bin/env python3
"""Route optional multi-SUT construction children after the reviewed v2 epoch.

The v3 transition replays the complete v2 repository at its frozen commit, then
admits only four root-registered construction children.  The router aggregates
local validation; it cannot authorize runtime, held-out access, qualification,
or evidence promotion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import types
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = "contracts/multisut-construction-registry.json"
REGISTRY_SCHEMA_PATH = "contracts/multisut-construction-registry.schema.json"
CONTROL_SCHEMA_PATH = "contracts/multisut-construction-control.schema.json"
VALIDATOR_PATH = "tools/validate_multisut_construction.py"
REGISTRY_SCHEMA_ID = (
    "https://observability-placement.local/contracts/"
    "multisut-construction-registry.schema.json"
)
# Finalized only after the root-transition bytes are complete.
REGISTRY_SHA256 = "8047fe45627a56d1d5ea9c50669a1c80e94f95d8b4047d92702841eab15b3cdf"
REGISTRY_SCHEMA_SHA256 = "e87e77b80790a7788b67b9e64446dd6d6d95b61733dbfeb7c6dc8f2a91471767"
CONTROL_SCHEMA_SHA256 = "76f91ab077b64bf65c5057ac9c8247a77ba863b665140445223f41ed6d638fa3"
VALIDATOR_SHA256 = "579cd33f81c6f8bca3c1d7968e49ce3c97e774afba2441acee796dfc6f1e18f4"
BASE_COMMIT = "bb29cfb068224173fe05a58a3fd750988f0de004"
BASE_TREE = "034303c37785e29ea5ea6595c18b6411d55525ff"
BASE_ROUTER_PATH = "tools/validate_science_epochs.py"
BASE_ROUTER_SHA256 = "bc30b5e7679450d5e6ae10382f1dc31691ee795374e8f2531409792ac7e2ad57"
BASE_CHANGE_IDS = (
    "adopt-scientific-openspec",
    "adopt-teastore-diagnostic-harness",
    "phase2-method-freeze",
    "teastore-candidate-pilot-freeze",
)
CHILD_CHANGE_IDS = (
    "adopt-hotel-reservation-candidate-harness",
    "adopt-online-boutique-candidate-harness",
    "adopt-online-boutique-lgtm-candidate-harness",
    "adopt-otel-demo-candidate-harness",
)
ROOT_TRANSITION_PATHS = (
    CONTROL_SCHEMA_PATH,
    REGISTRY_PATH,
    REGISTRY_SCHEMA_PATH,
    "tests/test_multisut_construction.py",
    "tests/test_openspec_construction.py",
    "tests/test_science_epoch_router.py",
    "tests/test_science_epoch_router_v3.py",
    "tools/run_openspec.py",
    VALIDATOR_PATH,
    "tools/validate_science_epochs_v3.py",
)
EXPECTED_PERMISSIONS = {
    "runtimeAllowed": False,
    "externalMutationAllowed": False,
    "heldOutOutcomeAccessAllowed": False,
    "aiSelectorAllowed": False,
    "evidencePromotionAllowed": False,
}
EXPECTED_MODULE_IDENTITIES = {
    "adopt-hotel-reservation-candidate-harness": {
        "id": "hotel-reservation",
        "applicationFamily": "deathstarbench-hotel-reservation",
        "channel": "compose-jaeger",
        "replicationContribution": "application-family",
    },
    "adopt-online-boutique-candidate-harness": {
        "id": "online-boutique",
        "applicationFamily": "google-online-boutique",
        "channel": "compose-native-otel",
        "replicationContribution": "application-family",
    },
    "adopt-online-boutique-lgtm-candidate-harness": {
        "id": "online-boutique-lgtm",
        "applicationFamily": "google-online-boutique",
        "channel": "aws-eks-lgtm",
        "replicationContribution": "execution-channel-only",
    },
    "adopt-otel-demo-candidate-harness": {
        "id": "otel-demo",
        "applicationFamily": "otel-demo",
        "channel": "compose-otel-collector",
        "replicationContribution": "application-family",
    },
}
HEX_COMMIT = re.compile(r"^[0-9a-f]{40}$")


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


def _environment(home: Path) -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "HOME": str(home),
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    with tempfile.TemporaryDirectory(prefix="multisut-router-git-home-") as raw:
        return subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-C", str(root), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=_environment(Path(raw)),
        )


def _output(result: subprocess.CompletedProcess[bytes]) -> str:
    return (result.stdout + result.stderr).decode("utf-8", errors="replace").strip()


def _is_exact_false_mapping(value: Any, expected: dict[str, bool]) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == set(expected)
        and all(value[key] is False for key in expected)
    )


def _active_git_metadata_lines(
    root: Path, *git_path_parts: str
) -> tuple[list[str], str | None]:
    result = _git(root, "rev-parse", "--git-path", *git_path_parts)
    if result.returncode != 0:
        return [], _output(result)
    try:
        raw = result.stdout.decode("utf-8", errors="strict").strip()
        if not raw:
            raise ValueError("Git returned an empty metadata path")
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        if not path.exists():
            return [], None
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return [], str(exc)
    return lines, None


def repository_control_errors(root: Path) -> list[str]:
    errors: list[str] = []
    replacements = _git(root, "replace", "-l")
    if replacements.returncode != 0:
        errors.append(f"cannot inspect Git replacement refs: {_output(replacements)}")
    elif replacements.stdout.strip():
        errors.append("Git replacement refs are forbidden")
    grafts, graft_error = _active_git_metadata_lines(root, "info/grafts")
    if graft_error:
        errors.append(f"cannot inspect Git grafts: {graft_error}")
    elif grafts:
        errors.append(f"Git grafts can rewrite routed topology: {grafts}")
    concealment = _git(
        root,
        "config",
        "--local",
        "--get-regexp",
        (
            r"^(include(if)?\.|filter\.|core\.attributesfile$|"
            r"core\.excludesfile$|core\.worktree$|"
            r"core\.fsmonitor$|core\.ignorestat$|core\.untrackedcache$|"
            r"diff\.|submodule\..*\.ignore$)"
        ),
    )
    if concealment.returncode == 0 and concealment.stdout.strip():
        errors.append("local Git configuration can conceal routed bytes")
    elif concealment.returncode not in {0, 1}:
        errors.append(f"cannot inspect local Git configuration: {_output(concealment)}")
    file_mode = _git(root, "config", "--local", "--type=bool", "--get", "core.fileMode")
    if file_mode.returncode == 0:
        if file_mode.stdout.strip().lower() != b"true":
            errors.append("core.fileMode must remain true")
    elif file_mode.returncode == 1:
        errors.append("core.fileMode must be explicitly true")
    else:
        errors.append(f"cannot inspect core.fileMode: {_output(file_mode)}")
    worktree_config = _git(
        root,
        "config",
        "--local",
        "--type=bool",
        "--get",
        "extensions.worktreeConfig",
    )
    if worktree_config.returncode == 0:
        errors.append("extensions.worktreeConfig is not allowed")
    elif worktree_config.returncode not in {0, 1}:
        errors.append(
            f"cannot inspect extensions.worktreeConfig: {_output(worktree_config)}"
        )
    bare = _git(root, "config", "--local", "--type=bool", "--get", "core.bare")
    if bare.returncode == 0:
        if bare.stdout.strip().lower() != b"false":
            errors.append("core.bare must remain false")
    elif bare.returncode not in {0, 1}:
        errors.append(f"cannot inspect core.bare: {_output(bare)}")
    top = _git(root, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        errors.append(f"cannot inspect effective Git worktree: {_output(top)}")
    else:
        try:
            observed_top = Path(top.stdout.decode("utf-8", errors="strict").strip()).resolve()
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            errors.append(f"cannot decode effective Git worktree: {exc}")
        else:
            if observed_top != root.resolve():
                errors.append(
                    "effective Git worktree differs from requested root: "
                    f"observed={observed_top}, expected={root.resolve()}"
                )
    return errors


def _children(registry: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    children = registry.get("children")
    if not isinstance(children, list):
        return {}, ["children is not a list"]
    for index, child in enumerate(children):
        if not isinstance(child, dict) or not isinstance(child.get("changeId"), str):
            errors.append(f"child {index} has no typed change id")
            continue
        change_id = child["changeId"]
        if change_id in by_id:
            errors.append(f"duplicate child change id: {change_id}")
        by_id[change_id] = child
    return by_id, errors


def validate_registry(
    root: Path, registry: dict[str, Any], *, pin_bytes: bool = True
) -> list[str]:
    errors: list[str] = []
    structural_errors: list[str] = []
    try:
        schema_path = _safe_file(root, REGISTRY_SCHEMA_PATH)
        registry_path = _safe_file(root, REGISTRY_PATH)
        control_schema = _safe_file(root, CONTROL_SCHEMA_PATH)
        validator_path = _safe_file(root, VALIDATOR_PATH)
        if pin_bytes and sha256_file(schema_path) != REGISTRY_SCHEMA_SHA256:
            errors.append("multi-SUT registry schema bytes differ from the router pin")
        if pin_bytes and sha256_file(registry_path) != REGISTRY_SHA256:
            errors.append("multi-SUT registry bytes differ from the router pin")
        if pin_bytes and sha256_file(control_schema) != CONTROL_SCHEMA_SHA256:
            errors.append("multi-SUT control schema bytes differ from the router pin")
        if pin_bytes and sha256_file(validator_path) != VALIDATOR_SHA256:
            errors.append("multi-SUT validator bytes differ from the router pin")
        schema = load_json(schema_path)
        if not isinstance(schema, dict) or schema.get("$id") != REGISTRY_SCHEMA_ID:
            structural_errors.append("multi-SUT registry schema id differs")
        else:
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
            for failure in sorted(
                validator.iter_errors(registry), key=lambda item: list(item.absolute_path)
            ):
                location = ".".join(str(item) for item in failure.absolute_path) or "$"
                structural_errors.append(f"registry {location}: {failure.message}")
    except (OSError, UnicodeDecodeError, ValueError, DuplicateKeyError, SchemaError) as exc:
        return [f"multi-SUT registry cannot be validated: {exc}"]
    errors.extend(structural_errors)
    if structural_errors:
        return errors

    if not _is_exact_false_mapping(registry.get("permissions"), EXPECTED_PERMISSIONS):
        errors.append("multi-SUT registry permissions are not all false")
    expected_transition = {
        "parentCommit": BASE_COMMIT,
        "parentTree": BASE_TREE,
        "ownedPaths": list(ROOT_TRANSITION_PATHS),
        "commitDerivation": "single-commit-last-change-of-every-owned-path",
    }
    if registry.get("transition") != expected_transition:
        errors.append("multi-SUT root transition identity/ownership differs")
    expected_base = {
        "id": "teastore-construction-v2",
        "commit": BASE_COMMIT,
        "tree": BASE_TREE,
        "router": {"path": BASE_ROUTER_PATH, "sha256": BASE_ROUTER_SHA256},
        "activeChangeIds": list(BASE_CHANGE_IDS),
    }
    if registry.get("baseEpoch") != expected_base:
        errors.append("frozen v2 base epoch differs")

    by_id, child_errors = _children(registry)
    errors.extend(child_errors)
    if tuple(by_id) != CHILD_CHANGE_IDS:
        errors.append(f"child route order/set differs: {tuple(by_id)}")
    all_allowed: set[str] = set()
    family_contributors: set[str] = set()
    for change_id in CHILD_CHANGE_IDS:
        child = by_id.get(change_id)
        if child is None:
            continue
        if child.get("required") is not False:
            errors.append(f"{change_id}: child must remain optional")
        if child.get("module") != EXPECTED_MODULE_IDENTITIES[change_id]:
            errors.append(f"{change_id}: module/family/channel identity differs")
        module = child.get("module")
        if not isinstance(module, dict):
            errors.append(f"{change_id}: module identity is not an object")
            continue
        if module.get("replicationContribution") == "application-family":
            family = module.get("applicationFamily")
            if family in family_contributors:
                errors.append(f"{change_id}: duplicates an application-family contribution")
            family_contributors.add(family)
        source = child.get("adoptedSource")
        parent = child.get("parentEpoch")
        if parent != {
            "changeId": "adopt-teastore-diagnostic-harness",
            "commit": BASE_COMMIT,
            "tree": BASE_TREE,
        }:
            errors.append(f"{change_id}: parent epoch differs")
        if not isinstance(source, dict):
            errors.append(f"{change_id}: adopted source is not an object")
            continue
        source_commit = source.get("commit")
        tree = _git(root, "show", "-s", "--format=%T", str(source_commit))
        if tree.returncode != 0 or tree.stdout.decode("ascii", errors="replace").strip() != source.get("tree"):
            errors.append(f"{change_id}: source commit/tree differs")
        parents = _git(root, "rev-list", "--parents", "-n", "1", str(source_commit))
        if parents.returncode != 0 or parents.stdout.decode("ascii", errors="replace").split() != [source_commit, BASE_COMMIT]:
            errors.append(f"{change_id}: source is not one commit directly after v2")
        allowed = child.get("allowedPaths")
        if not isinstance(allowed, list):
            errors.append(f"{change_id}: allowed paths are not a list")
            allowed = []
        try:
            canonical = [_canonical_file(item) for item in allowed]
        except ValueError as exc:
            errors.append(f"{change_id}: invalid allowed path: {exc}")
            canonical = []
        overlap = all_allowed & set(canonical)
        if overlap:
            errors.append(f"{change_id}: ownership overlaps earlier child: {sorted(overlap)}")
        all_allowed.update(canonical)
        if any(path.startswith((".local/", "upstream/")) for path in canonical):
            errors.append(f"{change_id}: ownership enters a forbidden root")
        source_bindings = child.get("sourceBindings")
        if not isinstance(source_bindings, list):
            errors.append(f"{change_id}: source bindings are not a list")
            source_bindings = []
        identities: set[tuple[str, str]] = set()
        for binding in source_bindings:
            if not isinstance(binding, dict):
                errors.append(f"{change_id}: source binding is not an object")
                continue
            relative = binding.get("path")
            commit = binding.get("sourceCommit")
            identity = (str(commit), str(relative))
            if identity in identities:
                errors.append(f"{change_id}: duplicate source binding {identity}")
            identities.add(identity)
            if commit not in {BASE_COMMIT, source_commit}:
                errors.append(f"{change_id}: source binding uses an unregistered commit")
                continue
            result = _git(root, "show", f"{commit}:{relative}")
            if result.returncode != 0 or sha256_bytes(result.stdout) != binding.get("sha256"):
                errors.append(f"{change_id}: source binding bytes differ for {relative}")
        protocol = child.get("protocolBindings")
        if not isinstance(protocol, dict):
            errors.append(f"{change_id}: protocol binding is not an object")
            continue
        descriptor = protocol.get("descriptor", {})
        compiler = protocol.get("compiler", {})
        bound = {
            (item.get("path"), item.get("sha256"))
            for item in source_bindings
            if isinstance(item, dict) and item.get("sourceCommit") == source_commit
        }
        if (descriptor.get("path"), descriptor.get("byteSha256")) not in bound:
            errors.append(f"{change_id}: descriptor lacks exact adopted-source binding")
        if (compiler.get("path"), compiler.get("sha256")) not in bound:
            errors.append(f"{change_id}: compiler lacks exact adopted-source binding")
        required_artifacts = {
            f"findings/{change_id}.csv",
            f"openspec/changes/{change_id}/.openspec.yaml",
            f"openspec/changes/{change_id}/authority.md",
            f"openspec/changes/{change_id}/design.md",
            f"openspec/changes/{change_id}/governance.json",
            f"openspec/changes/{change_id}/proposal.md",
            f"openspec/changes/{change_id}/specs/{change_id}/spec.md",
            f"openspec/changes/{change_id}/tasks.md",
            f"openspec/changes/{change_id}/verification.md",
        }
        if not required_artifacts.issubset(set(canonical)):
            errors.append(f"{change_id}: allowed paths omit required change artifacts")
        artifact_bindings = child.get("artifactBindings")
        if not isinstance(artifact_bindings, list):
            errors.append(f"{change_id}: artifact bindings are not a list")
            artifact_bindings = []
        artifact_paths: list[str] = []
        for binding in artifact_bindings:
            if not isinstance(binding, dict):
                errors.append(f"{change_id}: artifact binding is not an object")
                continue
            try:
                relative = _canonical_file(binding.get("path"))
            except (TypeError, ValueError) as exc:
                errors.append(f"{change_id}: invalid artifact binding path: {exc}")
                continue
            artifact_paths.append(relative)
            if binding.get("mode") != "100644":
                errors.append(f"{change_id}: artifact binding mode differs for {relative}")
        if len(artifact_paths) != len(set(artifact_paths)):
            errors.append(f"{change_id}: artifact binding paths contain duplicates")
        expected_bound_artifacts = required_artifacts - {f"findings/{change_id}.csv"}
        if set(artifact_paths) != expected_bound_artifacts:
            errors.append(
                f"{change_id}: artifact binding coverage differs: "
                f"missing={sorted(expected_bound_artifacts - set(artifact_paths))}, "
                f"extra={sorted(set(artifact_paths) - expected_bound_artifacts)}"
            )
        adopted_paths = {
            item.get("path")
            for item in source_bindings
            if isinstance(item, dict) and item.get("sourceCommit") == source_commit
        }
        if not adopted_paths.issubset(set(canonical)):
            errors.append(f"{change_id}: allowed paths omit adopted source files")
        covered = adopted_paths | set(artifact_paths) | {f"findings/{change_id}.csv"}
        if covered != set(canonical):
            errors.append(
                f"{change_id}: source/artifact/findings bindings do not exactly cover "
                f"allowed paths: missing={sorted(set(canonical) - covered)}, "
                f"extra={sorted(covered - set(canonical))}"
            )
    if family_contributors != {
        "deathstarbench-hotel-reservation",
        "google-online-boutique",
        "otel-demo",
    }:
        errors.append("application-family contribution set differs")
    return errors


def route_markers(
    root: Path, registry: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    by_id, child_errors = _children(registry)
    errors.extend(child_errors)
    changes_root = root / "openspec" / "changes"
    markers: set[str] = set()
    if not changes_root.is_dir():
        return [], [*errors, "openspec/changes directory is missing"]
    for marker in sorted(changes_root.glob("*/.openspec.yaml")):
        try:
            _safe_file(root, marker.relative_to(root).as_posix())
        except ValueError as exc:
            errors.append(str(exc))
            continue
        markers.add(marker.parent.name)
    missing_base = sorted(set(BASE_CHANGE_IDS) - markers)
    if missing_base:
        errors.append(f"frozen v2 active markers are missing: {missing_base}")
    known = set(BASE_CHANGE_IDS) | set(CHILD_CHANGE_IDS)
    unknown = sorted(markers - known)
    if unknown:
        errors.append(f"active markers have no root-owned route: {unknown}")
    active_ids = [change_id for change_id in CHILD_CHANGE_IDS if change_id in markers]
    return [by_id[item] for item in active_ids if item in by_id], errors


def derive_transition_commit(
    root: Path, registry: dict[str, Any]
) -> tuple[str | None, list[str]]:
    errors: list[str] = []
    transition = registry.get("transition")
    if not isinstance(transition, dict) or transition.get("ownedPaths") != list(ROOT_TRANSITION_PATHS):
        return None, ["cannot derive transition from an untrusted owned path set"]
    commits: set[str] = set()
    for relative in ROOT_TRANSITION_PATHS:
        result = _git(root, "log", "-1", "--format=%H", "--", relative)
        commit = result.stdout.decode("ascii", errors="replace").strip()
        if result.returncode != 0 or not HEX_COMMIT.fullmatch(commit):
            errors.append(f"cannot derive transition commit from {relative}: {_output(result)}")
        else:
            commits.add(commit)
    if len(commits) != 1:
        errors.append(f"root-owned paths were not introduced by one transition commit: {sorted(commits)}")
        return None, errors
    commit = next(iter(commits))
    parents = _git(root, "rev-list", "--parents", "-n", "1", commit)
    if parents.returncode != 0 or parents.stdout.decode("ascii", errors="replace").split() != [commit, BASE_COMMIT]:
        errors.append("multi-SUT root transition is not one commit directly after v2")
    changed = _git(
        root,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        "-z",
        "--no-renames",
        BASE_COMMIT,
        commit,
        "--",
    )
    observed = {
        item.decode("utf-8") for item in changed.stdout.split(b"\0") if item
    } if changed.returncode == 0 else set()
    if changed.returncode != 0 or observed != set(ROOT_TRANSITION_PATHS):
        errors.append(
            "multi-SUT root transition path set differs: "
            f"observed={sorted(observed)}, expected={sorted(ROOT_TRANSITION_PATHS)}"
        )
    for relative in ROOT_TRANSITION_PATHS:
        tree_entry = _git(root, "ls-tree", "-z", commit, "--", relative)
        index_entry = _git(root, "ls-files", "--stage", "-z", "--", relative)
        blob = _git(root, "show", f"{commit}:{relative}")
        try:
            tree_rows = [item for item in tree_entry.stdout.split(b"\0") if item]
            index_rows = [item for item in index_entry.stdout.split(b"\0") if item]
            if len(tree_rows) != 1 or len(index_rows) != 1:
                raise ValueError("transition/index entry is not singular")
            tree_metadata, tree_path = tree_rows[0].split(b"\t", 1)
            tree_mode, object_type, object_id = tree_metadata.decode("ascii").split()
            index_metadata, index_path = index_rows[0].split(b"\t", 1)
            index_mode, index_id, stage = index_metadata.decode("ascii").split()
            if (
                tree_entry.returncode != 0
                or index_entry.returncode != 0
                or blob.returncode != 0
                or object_type != "blob"
                or stage != "0"
                or tree_path.decode("utf-8") != relative
                or index_path.decode("utf-8") != relative
                or (tree_mode, object_id) != (index_mode, index_id)
            ):
                raise ValueError("transition, index, and blob identities differ")
            path = _safe_file(root, relative)
            working_mode = "100755" if path.lstat().st_mode & 0o111 else "100644"
            if working_mode != tree_mode or path.read_bytes() != blob.stdout:
                raise ValueError("working bytes or mode differ")
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            errors.append(
                f"root-owned control bytes differ from transition: {relative}: {exc}"
            )
    return commit, errors


def _run_base_snapshot(root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="multisut-v2-snapshot-") as raw:
        temporary = Path(raw).resolve()
        checkout = temporary / "repository"
        environment = _environment(temporary / "home")
        (temporary / "home").mkdir()
        clone = subprocess.run(
            ["git", "clone", "--no-local", "--no-checkout", "--quiet", str(root), str(checkout)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )
        if clone.returncode != 0:
            return {"status": "cannot_run", "diagnostics": [f"v2 snapshot clone failed: {_output(clone)}"]}
        detached = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-C", str(checkout), "checkout", "--detach", "--quiet", BASE_COMMIT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )
        if detached.returncode != 0:
            return {"status": "cannot_run", "diagnostics": [f"v2 snapshot checkout failed: {_output(detached)}"]}
        tree = subprocess.run(
            ["git", "-C", str(checkout), "show", "-s", "--format=%T", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )
        if tree.returncode != 0 or tree.stdout.decode("ascii", errors="replace").strip() != BASE_TREE:
            return {"status": "fail", "diagnostics": ["v2 snapshot tree differs"]}
        router = checkout / BASE_ROUTER_PATH
        if sha256_file(router) != BASE_ROUTER_SHA256:
            return {"status": "fail", "diagnostics": ["v2 snapshot router bytes differ"]}
        result = subprocess.run(
            [sys.executable, "-I", str(router), "--root", str(checkout)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )
        try:
            report = json.loads(result.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return {"status": "cannot_run", "diagnostics": [f"v2 report is not JSON: {exc}; {_output(result)}"]}
        if result.returncode != 0 and report.get("status") == "pass":
            return {"status": "fail", "diagnostics": ["v2 process/report status contradiction"]}
        return report


def _load_validator(root: Path):
    path = _safe_file(root, VALIDATOR_PATH)
    source = path.read_bytes()
    source.decode("utf-8")
    name = "root_owned_multisut_validator"
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = None
    module.__loader__ = None
    module.__spec__ = None
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def aggregate_status(reports: list[dict[str, Any]]) -> str:
    statuses = [item.get("status") for item in reports]
    if any(status == "fail" for status in statuses):
        return "fail"
    if any(status != "pass" for status in statuses):
        return "cannot_run"
    return "pass"


def validate_repository(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    control_errors = repository_control_errors(root)
    registry: dict[str, Any] = {}
    active_entries: list[dict[str, Any]] = []
    transition_commit: str | None = None
    if not control_errors:
        try:
            value = load_json(_safe_file(root, REGISTRY_PATH))
            if not isinstance(value, dict):
                raise ValueError("multi-SUT registry is not an object")
            registry = value
        except (OSError, UnicodeDecodeError, ValueError, DuplicateKeyError) as exc:
            control_errors.append(f"multi-SUT registry cannot be read: {exc}")
    if not control_errors:
        control_errors.extend(validate_registry(root, registry))
    if not control_errors:
        active_entries, route_errors = route_markers(root, registry)
        control_errors.extend(route_errors)
    if not control_errors:
        transition_commit, transition_errors = derive_transition_commit(root, registry)
        control_errors.extend(transition_errors)

    reports: list[dict[str, Any]] = []
    if not control_errors and transition_commit is not None:
        reports.append({"epochId": "teastore-construction-v2", "report": _run_base_snapshot(root)})
        try:
            validator = _load_validator(root)
            child_report = validator.validate_repository(
                root,
                active_entries,
                delivery_base_commit=transition_commit,
            )
        except Exception as exc:
            child_report = {"status": "cannot_run", "diagnostics": [str(exc)]}
        reports.append({"epochId": "multisut-construction-v3", "report": child_report})
    status = "fail" if control_errors else aggregate_status([item["report"] for item in reports])
    return {
        "schemaVersion": 1,
        "status": status,
        "scienceControlValid": status == "pass",
        "runtimeAuthorized": False,
        "promotionEligible": False,
        "transitionCommit": transition_commit,
        "activeChildChangeIds": [item.get("changeId") for item in active_entries],
        "controlDiagnostics": control_errors,
        "epochReports": reports,
        "claimBoundary": (
            "The v3 router replays the frozen v2 epoch and validates optional "
            "multi-SUT construction children. It cannot authorize runtime, inspect "
            "held-out outcomes, qualify evidence, count execution channels as new "
            "application families, or promote a claim."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--operation", choices=("validate", "apply", "archive"), default="validate"
    )
    parser.add_argument("--change")
    arguments = parser.parse_args()
    report = validate_repository(arguments.root)
    if arguments.operation != "validate":
        report["operationPreflight"] = {
            "operation": arguments.operation,
            "changeId": arguments.change,
            "allowed": False,
            "diagnostics": ["v3 has no human-bound cross-epoch operation receipt"],
            "runtimeAuthorized": False,
            "promotionEligible": False,
        }
        report["status"] = "fail"
        report["scienceControlValid"] = False
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] == "pass":
        return 0
    if report["status"] == "cannot_run":
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BASE_CHANGE_IDS",
    "BASE_COMMIT",
    "BASE_TREE",
    "CHILD_CHANGE_IDS",
    "EXPECTED_MODULE_IDENTITIES",
    "ROOT_TRANSITION_PATHS",
    "derive_transition_commit",
    "load_json",
    "route_markers",
    "validate_registry",
    "validate_repository",
]
