#!/usr/bin/env python3
"""Route every active OpenSpec change through one root-owned science epoch.

The router is an aggregate, never an authorization surface.  It replays the
legacy v1 epoch from its frozen b331 tree and dispatches the required TeaStore
construction successor only after verifying the independently committed root
transition, exact schema/validator bytes, typed supersessions, and delivery
base.  No executable path or argument is read from registry data.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pwd
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = "contracts/science-epoch-registry.json"
REGISTRY_SCHEMA_PATH = "contracts/science-epoch-registry.schema.json"
REGISTRY_SCHEMA_ID = (
    "https://observability-placement.local/contracts/"
    "science-epoch-registry.schema.json"
)
# Updated only by the independently reviewed root transition after registry
# bytes are final.  The wrapper separately pins this router.
REGISTRY_SHA256 = "afd033eca146536e1490bd7ccffed1bbc652cb246bfaf01356f2b1c5c53751d0"
REGISTRY_SCHEMA_SHA256 = "f4d6cce59b5620f764c6ef6952fe7820b3f5752015b47c7a1740313133f8349c"
EXPECTED_V2_ALLOWED_PATHS_SHA256 = "85d686d6ad0c9c37b57ddc335570a64d834a9374755a950e23b0227951d8ece9"
EXPECTED_V2_SOURCE_BINDINGS_SHA256 = "565258b6e285dad8d2da48c6010d0fc107d30ed166b01c88019c0bd9ce6b16c6"
PARENT_COMMIT = "b331aa4d365d7d41accc7d7cf1c20904fab2f622"
PARENT_TREE = "998aaba29c8ba43f5f3929aacd9b235ff51b9028"
V1_EPOCH_ID = "scientific-change-v1"
V2_EPOCH_ID = "teastore-construction-v2"
V1_CHANGE_IDS = (
    "adopt-scientific-openspec",
    "phase2-method-freeze",
    "teastore-candidate-pilot-freeze",
)
V2_CHANGE_IDS = ("adopt-teastore-diagnostic-harness",)
ROOT_TRANSITION_PATHS = (
    "contracts/science-construction-control.schema.json",
    "contracts/science-epoch-registry.json",
    "contracts/science-epoch-registry.schema.json",
    "pyproject.toml",
    "tests/test_openspec_science.py",
    "tests/test_science_epoch_router.py",
    "tools/run_openspec.py",
    "tools/validate_openspec_construction.py",
    "tools/validate_science_epochs.py",
    "uv.lock",
)
EXPECTED_PERMISSIONS = {
    "runtimeAllowed": False,
    "externalMutationAllowed": False,
    "heldOutOutcomeAccessAllowed": False,
    "aiSelectorAllowed": False,
    "evidencePromotionAllowed": False,
}
EXPECTED_DIAGNOSTIC_ANCHORS = (
    (
        "canddiag-20260829-1813",
        "pass",
        "8c3bdeded3ada824b2c51509680dd3db46eafee02674b95863062dad1f549f05",
        "6aeed088f344b2b11e2a123bf706080e4e1cf8e7156fb01c3690be8d0b741ae9",
        "ca2df4a8c42bf59f184bcc316c64c3015cfb7ee7",
    ),
    (
        "canddiag-effect-20260829-1854",
        "blocked",
        "77abd456856673858e138be3c0b635707afcb1bfdaaf8d8126634a761195c8ae",
        "9739b2bd8df3c77dc85757f74d44b37188dddac5a1b348885923d08c39ec7255",
        "0cdfc2b4a47419e0a59d7d9be3e5f98817e29710",
    ),
    (
        "canddiag-effect2-20260829-1931",
        "pass",
        "bf1e42e37062c076ba775eaa401c4f69e7126919a18fdf5eded5828e9da5c37b",
        "63782828e4ef0e0cf1b5c68396f44c7c4cd941567a5a94723cf9dd00c31d2729",
        "b4a6e053afbd9d2de322e2df6ad43e847a20979a",
    ),
)
EXPECTED_AUTHORITY_SUPERSESSIONS = (
    "modules/teastore/collectors/kieker_native.py",
    "modules/teastore/collectors/performance_probe.py",
    "modules/teastore/deployment/srv5.yaml",
    "modules/teastore/execution/performance_campaign.py",
    "modules/teastore/extension-ledger.yaml",
    "modules/teastore/validation/performance_receipt.py",
    "modules/teastore/workload/fixed_load.py",
)
EXPECTED_LEDGER_SUPERSESSION = "findings/teastore-candidate-pilot-freeze.csv"
HEX_COMMIT = re.compile(r"^[0-9a-f]{40}$")
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DuplicateKeyError(ValueError):
    """Reject ambiguous JSON members."""


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


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


def canonical_json_sha256(value: Any) -> str:
    return sha256_bytes(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


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


def _trusted_executable(name: str, root: Path) -> Path:
    candidates = [
        Path(prefix) / name
        for prefix in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin")
    ]
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if (root == resolved or root in resolved.parents) or not os.access(candidate, os.X_OK):
            continue
        return candidate
    raise OSError(f"trusted host executable is unavailable: {name}")


def _environment(root: Path, controlled_home: Path) -> dict[str, str]:
    git = _trusted_executable("git", root)
    return {
        "PATH": os.pathsep.join((str(git.parent), "/usr/bin", "/bin")),
        "HOME": str(controlled_home),
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    git = _trusted_executable("git", root)
    with tempfile.TemporaryDirectory(prefix="science-router-git-home-") as raw:
        return subprocess.run(
            [str(git), "-c", "core.fsmonitor=false", "-C", str(root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=_environment(root, Path(raw).resolve()),
        )


def _output(result: subprocess.CompletedProcess[bytes]) -> str:
    return (result.stdout + result.stderr).decode("utf-8", errors="replace").strip()


def repository_control_errors(root: Path) -> list[str]:
    """Reject Git mechanisms that could rewrite or conceal routed bytes."""

    errors: list[str] = []
    replacements = _git(root, "replace", "-l")
    if replacements.returncode != 0:
        errors.append(f"cannot inspect Git replacement refs: {_output(replacements)}")
    elif replacements.stdout.strip():
        errors.append(
            "Git replacement refs are forbidden: "
            + replacements.stdout.decode("ascii", errors="replace").strip()
        )
    concealment = _git(
        root,
        "config",
        "--local",
        "--get-regexp",
        (
            r"^(filter\.|core\.attributesfile$|core\.excludesfile$|"
            r"core\.fsmonitor$|core\.fsmonitorhookversion$|"
            r"core\.ignorestat$|core\.untrackedcache$|"
            r"submodule\..*\.ignore$)"
        ),
    )
    if concealment.returncode == 0 and concealment.stdout.strip():
        errors.append(
            "local Git configuration can conceal routed bytes: "
            + concealment.stdout.decode("utf-8", errors="replace").strip()
        )
    elif concealment.returncode not in {0, 1}:
        errors.append(f"cannot inspect local Git configuration: {_output(concealment)}")
    return errors


def _epoch_map(registry: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    epochs = registry.get("epochs")
    errors: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    if not isinstance(epochs, list):
        return {}, ["epochs is not a list"]
    for index, epoch in enumerate(epochs):
        if not isinstance(epoch, dict) or not isinstance(epoch.get("id"), str):
            errors.append(f"epoch {index} has no typed id")
            continue
        epoch_id = epoch["id"]
        if epoch_id in by_id:
            errors.append(f"duplicate epoch id: {epoch_id}")
        by_id[epoch_id] = epoch
    return by_id, errors


def validate_registry(root: Path, registry: dict[str, Any], *, pin_bytes: bool = True) -> list[str]:
    errors: list[str] = []
    try:
        schema_path = _safe_file(root, REGISTRY_SCHEMA_PATH)
        registry_path = _safe_file(root, REGISTRY_PATH)
        if pin_bytes and sha256_file(schema_path) != REGISTRY_SCHEMA_SHA256:
            errors.append("root registry schema bytes differ from the router pin")
        if pin_bytes and sha256_file(registry_path) != REGISTRY_SHA256:
            errors.append("root epoch registry bytes differ from the router pin")
        schema = load_json(schema_path)
        if not isinstance(schema, dict) or schema.get("$id") != REGISTRY_SCHEMA_ID:
            errors.append("root registry schema id differs")
            validator = None
        else:
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
        if validator is not None:
            for failure in sorted(
                validator.iter_errors(registry), key=lambda item: list(item.absolute_path)
            ):
                location = ".".join(str(item) for item in failure.absolute_path) or "$"
                errors.append(f"registry {location}: {failure.message}")
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        json.JSONDecodeError,
        DuplicateKeyError,
        SchemaError,
    ) as exc:
        return [f"root registry cannot be validated: {exc}"]

    if registry.get("permissions") != EXPECTED_PERMISSIONS:
        errors.append("root registry permissions are not all false")
    transition = registry.get("transition")
    expected_transition = {
        "parentCommit": PARENT_COMMIT,
        "parentTree": PARENT_TREE,
        "ownedPaths": list(ROOT_TRANSITION_PATHS),
        "commitDerivation": "single-commit-last-change-of-every-owned-path",
    }
    if transition != expected_transition:
        errors.append("root transition identity or ownership differs")

    by_id, epoch_errors = _epoch_map(registry)
    errors.extend(epoch_errors)
    if set(by_id) != {V1_EPOCH_ID, V2_EPOCH_ID}:
        errors.append(f"epoch id set differs: {sorted(by_id)}")
        return errors
    v1, v2 = by_id[V1_EPOCH_ID], by_id[V2_EPOCH_ID]
    if v1.get("required") is not True or tuple(v1.get("changeIds", ())) != V1_CHANGE_IDS:
        errors.append("v1 route or required state differs")
    if v1.get("snapshot") != {"commit": PARENT_COMMIT, "tree": PARENT_TREE}:
        errors.append("v1 frozen snapshot differs")
    if v1.get("parent") is not None:
        errors.append("v1 root epoch unexpectedly has a parent")
    if (
        v1.get("allowedPaths") != []
        or v1.get("sourceBindings") != []
        or v1.get("protocolModule") is not None
    ):
        errors.append("v1 frozen route unexpectedly declares successor inputs")
    if v2.get("required") is not True or tuple(v2.get("changeIds", ())) != V2_CHANGE_IDS:
        errors.append("v2 successor route or required state differs")
    if v2.get("snapshot") is not None:
        errors.append("active v2 successor must validate current reviewed bytes")
    if v2.get("parent") != {
        "epochId": V1_EPOCH_ID,
        "changeId": "teastore-candidate-pilot-freeze",
        "commit": PARENT_COMMIT,
        "tree": PARENT_TREE,
    }:
        errors.append("v2 parent commit/tree differs from the frozen v1 transition")
    allowed_paths = v2.get("allowedPaths")
    if not isinstance(allowed_paths, list) or not allowed_paths:
        errors.append("v2 root-owned allowed path set is empty")
    else:
        try:
            canonical_allowed = [_canonical_file(item) for item in allowed_paths]
        except ValueError as exc:
            errors.append(f"v2 allowed path is invalid: {exc}")
        else:
            if len(canonical_allowed) != len(set(canonical_allowed)):
                errors.append("v2 root-owned allowed path set has duplicates")
    if canonical_json_sha256(allowed_paths) != EXPECTED_V2_ALLOWED_PATHS_SHA256:
        errors.append("v2 complete allowed path identity set differs")
    protocol_module = v2.get("protocolModule")
    if not isinstance(protocol_module, dict) or (
        protocol_module.get("id"), protocol_module.get("path")
    ) != (
        "teastore-candidate-pilot-v1-compiler",
        "modules/teastore/execution/candidate_pilot.py",
    ):
        errors.append("v2 protocol module identity/path differs")
    elif not isinstance(protocol_module.get("sha256"), str) or not HEX_SHA256.fullmatch(
        protocol_module["sha256"]
    ):
        errors.append("v2 protocol module digest is not SHA-256")

    source_bindings = v2.get("sourceBindings")
    if not isinstance(source_bindings, list) or not source_bindings:
        errors.append("v2 root-owned source binding set is empty")
        source_bindings = []
    if canonical_json_sha256(source_bindings) != EXPECTED_V2_SOURCE_BINDINGS_SHA256:
        errors.append("v2 complete source binding identity set differs")
    source_identities: set[tuple[str, str]] = set()
    for binding in source_bindings:
        if not isinstance(binding, dict):
            errors.append("v2 source binding is not an object")
            continue
        relative = binding.get("path")
        commit = binding.get("sourceCommit")
        identity = (str(commit), str(relative))
        if identity in source_identities:
            errors.append(f"duplicate v2 source binding: {identity}")
        source_identities.add(identity)
        if commit not in {PARENT_COMMIT, "b4a6e053afbd9d2de322e2df6ad43e847a20979a"}:
            errors.append(f"v2 source binding has an unregistered commit: {relative}")
            continue
        source = _git(root, "show", f"{commit}:{relative}")
        if source.returncode != 0 or sha256_bytes(source.stdout) != binding.get("sha256"):
            errors.append(f"v2 root-owned source binding differs: {relative}")
    anchors = tuple(
        (
            item.get("campaignId"),
            item.get("terminalStatus"),
            item.get("manifestSha256"),
            item.get("externalSealSha256"),
            item.get("frameworkCommit"),
        )
        for item in v2.get("diagnosticObservations", [])
        if isinstance(item, dict)
    )
    if anchors != EXPECTED_DIAGNOSTIC_ANCHORS:
        errors.append("v2 diagnostic anchors differ from independently recomputed seals")

    supersessions = v2.get("supersessions")
    authority_paths = tuple(
        item.get("path")
        for item in supersessions
        if isinstance(supersessions, list)
        and isinstance(item, dict)
        and item.get("kind") == "authority-source"
    ) if isinstance(supersessions, list) else ()
    ledger_paths = tuple(
        item.get("path")
        for item in supersessions
        if isinstance(supersessions, list)
        and isinstance(item, dict)
        and item.get("kind") == "append-only-ledger"
    ) if isinstance(supersessions, list) else ()
    if authority_paths != EXPECTED_AUTHORITY_SUPERSESSIONS:
        errors.append("v2 authority supersession registry differs")
    if ledger_paths != (EXPECTED_LEDGER_SUPERSESSION,):
        errors.append("v2 ledger supersession registry differs")
    for item in supersessions if isinstance(supersessions, list) else []:
        if not isinstance(item, dict):
            continue
        relative = item.get("path")
        predecessor = _git(root, "show", f"{item.get('predecessorCommit')}:{relative}")
        if predecessor.returncode != 0 or sha256_bytes(predecessor.stdout) != item.get("predecessorSha256"):
            errors.append(f"root supersession predecessor bytes differ: {relative}")
        if item.get("kind") == "authority-source":
            source = _git(root, "show", f"{item.get('successorSourceCommit')}:{relative}")
            if source.returncode != 0 or sha256_bytes(source.stdout) != item.get("successorSourceSha256"):
                errors.append(f"root supersession source bytes differ: {relative}")
        elif item.get("kind") == "append-only-ledger":
            length = item.get("predecessorLength")
            if not isinstance(length, int) or isinstance(length, bool) or length != len(predecessor.stdout):
                errors.append(f"root ledger supersession length differs: {relative}")

    expected_bindings = {
        V1_EPOCH_ID: {
            "schema": (
                "https://observability-placement.local/contracts/"
                "science-change-control.schema.json",
                "contracts/science-change-control.schema.json",
            ),
            "validator": (
                "scientific-change-v1-validator",
                "tools/validate_openspec_science.py",
            ),
        },
        V2_EPOCH_ID: {
            "schema": (
                "https://observability-placement.local/contracts/"
                "science-construction-control.schema.json",
                "contracts/science-construction-control.schema.json",
            ),
            "validator": (
                "teastore-construction-v2-validator",
                "tools/validate_openspec_construction.py",
            ),
        },
    }
    for epoch_id, fields in expected_bindings.items():
        epoch = by_id[epoch_id]
        for kind, (binding_id, relative) in fields.items():
            binding = epoch.get(kind)
            if not isinstance(binding, dict) or (
                binding.get("id"), binding.get("path")
            ) != (binding_id, relative):
                errors.append(f"{epoch_id}: {kind} identity/path differs")
                continue
            declared = binding.get("sha256")
            if not isinstance(declared, str) or not HEX_SHA256.fullmatch(declared):
                errors.append(f"{epoch_id}: {kind} digest is not SHA-256")
                continue
            try:
                observed = sha256_file(_safe_file(root, relative))
            except (OSError, ValueError) as exc:
                errors.append(f"{epoch_id}: cannot verify {kind}: {exc}")
                continue
            if observed != declared:
                errors.append(f"{epoch_id}: {kind} bytes differ from root registry")
    return errors


def route_markers(root: Path, registry: dict[str, Any]) -> tuple[dict[str, list[str]], list[str]]:
    errors: list[str] = []
    by_id, epoch_errors = _epoch_map(registry)
    errors.extend(epoch_errors)
    routes: dict[str, list[str]] = {epoch_id: [] for epoch_id in by_id}
    owners: dict[str, list[str]] = {}
    for epoch_id, epoch in by_id.items():
        change_ids = epoch.get("changeIds")
        if not isinstance(change_ids, list):
            errors.append(f"{epoch_id}: changeIds is not a list")
            continue
        for change_id in change_ids:
            if isinstance(change_id, str):
                owners.setdefault(change_id, []).append(epoch_id)
    duplicates = {key: value for key, value in owners.items() if len(value) != 1}
    if duplicates:
        errors.append(f"change ids do not route exactly once: {duplicates}")

    changes_root = root / "openspec" / "changes"
    markers: set[str] = set()
    if not changes_root.is_dir():
        return routes, [*errors, "openspec/changes directory is missing"]
    for marker in sorted(changes_root.glob("*/.openspec.yaml")):
        try:
            _safe_file(root, marker.relative_to(root).as_posix())
        except ValueError as exc:
            errors.append(str(exc))
            continue
        markers.add(marker.parent.name)
    unknown = sorted(markers - set(owners))
    if unknown:
        errors.append(f"active markers have no root-owned route: {unknown}")
    for change_id in sorted(markers & set(owners)):
        if len(owners[change_id]) == 1:
            routes[owners[change_id][0]].append(change_id)
    for epoch_id, epoch in by_id.items():
        expected = set(epoch.get("changeIds", []))
        observed = set(routes.get(epoch_id, []))
        if epoch.get("required") is True and observed != expected:
            errors.append(
                f"required epoch {epoch_id} is incomplete: "
                f"observed={sorted(observed)}, expected={sorted(expected)}"
            )
        if epoch.get("required") is False and observed not in (set(), expected):
            errors.append(f"optional epoch {epoch_id} is only partially active")
    routed = [change for values in routes.values() for change in values]
    if len(routed) != len(set(routed)) or set(routed) != markers:
        errors.append("active marker routing is not total and exactly once")
    return routes, errors


def derive_transition_commit(root: Path, registry: dict[str, Any]) -> tuple[str | None, list[str]]:
    errors: list[str] = []
    transition = registry.get("transition")
    paths = transition.get("ownedPaths") if isinstance(transition, dict) else None
    if paths != list(ROOT_TRANSITION_PATHS):
        return None, ["cannot derive a transition from an untrusted owned path set"]
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
    parts = parents.stdout.decode("ascii", errors="replace").split()
    if parents.returncode != 0 or parts != [commit, PARENT_COMMIT]:
        errors.append("root transition is not a single commit directly after b331aa4")
    parent_tree = _git(root, "show", "-s", "--format=%T", PARENT_COMMIT)
    if parent_tree.stdout.decode("ascii", errors="replace").strip() != PARENT_TREE:
        errors.append("root transition parent tree differs from the frozen v1 tree")
    changed = _git(
        root,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        "-z",
        "--no-renames",
        PARENT_COMMIT,
        commit,
        "--",
    )
    if changed.returncode != 0:
        errors.append(f"cannot inspect root transition delivery: {_output(changed)}")
    else:
        observed = {
            item.decode("utf-8") for item in changed.stdout.split(b"\0") if item
        }
        if observed != set(ROOT_TRANSITION_PATHS):
            errors.append(
                "root transition path set differs: "
                f"observed={sorted(observed)}, expected={sorted(ROOT_TRANSITION_PATHS)}"
            )
    for relative in ROOT_TRANSITION_PATHS:
        result = _git(root, "diff", "--quiet", commit, "--", relative)
        if result.returncode != 0:
            errors.append(f"root-owned control bytes differ from transition: {relative}")
    return commit, errors


def _load_fixed_module(root: Path, relative: str, name: str):
    source = _safe_file(root, relative)
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load fixed validator: {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _run_v1_snapshot(root: Path, epoch: dict[str, Any]) -> dict[str, Any]:
    snapshot = epoch["snapshot"]
    with tempfile.TemporaryDirectory(prefix="science-v1-snapshot-") as raw:
        temporary = Path(raw).resolve()
        checkout = temporary / "repository"
        git = _trusted_executable("git", root)
        environment = _environment(root, temporary / "home")
        (temporary / "home").mkdir()
        clone = subprocess.run(
            [str(git), "clone", "--no-local", "--no-checkout", "--quiet", str(root), str(checkout)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )
        if clone.returncode != 0:
            return {"status": "cannot_run", "diagnostics": [f"v1 snapshot clone failed: {_output(clone)}"]}
        detached = subprocess.run(
            [str(git), "-c", "core.fsmonitor=false", "-C", str(checkout), "checkout", "--detach", "--quiet", snapshot["commit"]],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )
        if detached.returncode != 0:
            return {"status": "cannot_run", "diagnostics": [f"v1 snapshot checkout failed: {_output(detached)}"]}
        tree = subprocess.run(
            [str(git), "-C", str(checkout), "show", "-s", "--format=%T", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )
        if tree.returncode != 0 or tree.stdout.decode("ascii", errors="replace").strip() != snapshot["tree"]:
            return {"status": "fail", "diagnostics": ["v1 snapshot tree differs"]}
        validator = checkout / "tools" / "validate_openspec_science.py"
        if sha256_file(validator) != epoch["validator"]["sha256"]:
            return {"status": "fail", "diagnostics": ["v1 snapshot validator bytes differ"]}
        result = subprocess.run(
            [sys.executable, "-I", str(validator), "--root", str(checkout)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )
        try:
            report = json.loads(result.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return {"status": "cannot_run", "diagnostics": [f"v1 report is not JSON: {exc}; {_output(result)}"]}
        if result.returncode != 0 and report.get("status") == "pass":
            return {"status": "fail", "diagnostics": ["v1 process/report status contradiction"]}
        return report


def successor_manifest_contract_errors(
    manifest: dict[str, Any], epoch: dict[str, Any], transition_commit: str
) -> list[str]:
    """Compare child-controlled declarations to the exact root-owned route."""

    errors: list[str] = []
    parent = epoch.get("parent")
    if manifest.get("parentEpoch") != {
        "changeId": parent.get("changeId") if isinstance(parent, dict) else None,
        "commit": parent.get("commit") if isinstance(parent, dict) else None,
        "tree": parent.get("tree") if isinstance(parent, dict) else None,
    }:
        errors.append("v2 governance parent commit/tree differs from root route")
    ownership = manifest.get("pathOwnership")
    if not isinstance(ownership, dict) or ownership.get("baseCommit") != transition_commit:
        errors.append("v2 ownership base does not equal the derived root transition")
    expected_allowed = epoch.get("allowedPaths")
    observed_allowed = ownership.get("allowed") if isinstance(ownership, dict) else None
    if observed_allowed != expected_allowed:
        errors.append("v2 allowed path set differs from the root-owned registry")

    expected_observations = [
        {
            "campaignId": item["campaignId"],
            "terminalStatus": item["terminalStatus"],
            "manifestSha256": item["manifestSha256"],
            "qualification": "diagnostic-only",
            "canonical": False,
            "candidateCellEligible": False,
        }
        for item in epoch.get("diagnosticObservations", [])
    ]
    if manifest.get("diagnosticObservations") != expected_observations:
        errors.append("v2 diagnostic observations differ from root-owned external anchors")
    if manifest.get("sourceBindings") != epoch.get("sourceBindings"):
        errors.append("v2 source bindings differ from the complete root-owned registry")
    return errors


def _v2_route_errors(root: Path, epoch: dict[str, Any], transition_commit: str) -> list[str]:
    errors: list[str] = []
    change_id = V2_CHANGE_IDS[0]
    try:
        manifest = load_json(root / "openspec" / "changes" / change_id / "governance.json")
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError, DuplicateKeyError) as exc:
        return [f"v2 governance cannot be parsed: {exc}"]
    if not isinstance(manifest, dict):
        return ["v2 governance is not an object"]
    errors.extend(successor_manifest_contract_errors(manifest, epoch, transition_commit))
    ownership = manifest.get("pathOwnership")
    allowed_value = ownership.get("allowed") if isinstance(ownership, dict) else None
    if not isinstance(allowed_value, list):
        errors.append("v2 pathOwnership.allowed is not a list")
        allowed: set[str] = set()
    else:
        allowed = {item for item in allowed_value if isinstance(item, str)}

    source_bindings = manifest.get("sourceBindings")
    source_identities = {
        (item.get("path"), item.get("sourceCommit"), item.get("sha256"))
        for item in source_bindings
        if isinstance(source_bindings, list) and isinstance(item, dict)
    } if isinstance(source_bindings, list) else set()
    for item in epoch.get("supersessions", []):
        if not isinstance(item, dict):
            errors.append("v2 supersession is not an object")
            continue
        relative = item.get("path")
        if relative not in allowed:
            errors.append(f"v2 superseded path lacks successor ownership: {relative}")
        predecessor = _git(root, "show", f"{item.get('predecessorCommit')}:{relative}")
        if predecessor.returncode != 0 or sha256_bytes(predecessor.stdout) != item.get("predecessorSha256"):
            errors.append(f"v2 predecessor bytes differ for supersession: {relative}")
        if item.get("kind") == "authority-source":
            source = _git(root, "show", f"{item.get('successorSourceCommit')}:{relative}")
            if source.returncode != 0 or sha256_bytes(source.stdout) != item.get("successorSourceSha256"):
                errors.append(f"v2 successor source bytes differ: {relative}")
            identity = (relative, item.get("successorSourceCommit"), item.get("successorSourceSha256"))
            if identity not in source_identities:
                errors.append(f"v2 governance omits typed source supersession: {relative}")
        elif item.get("kind") == "append-only-ledger":
            try:
                current = _safe_file(root, relative).read_bytes()
                length = item.get("predecessorLength")
                if not isinstance(length, int) or isinstance(length, bool):
                    raise ValueError("predecessor length is not an integer")
                if len(current) < length or sha256_bytes(current[:length]) != item.get("predecessorSha256"):
                    errors.append(f"v2 ledger supersession rewrites the frozen prefix: {relative}")
            except (OSError, ValueError) as exc:
                errors.append(f"cannot verify v2 ledger supersession {relative}: {exc}")
        else:
            errors.append(f"unknown v2 supersession kind for {relative}")

    changed: set[str] = set()
    for arguments in (
        ("diff", "--name-only", "-z", f"{transition_commit}..HEAD", "--"),
        ("diff", "--name-only", "-z", "--cached", "--"),
        ("diff", "--name-only", "-z", "--"),
        ("ls-files", "--others", "--exclude-standard", "-z", "--"),
    ):
        result = _git(root, *arguments)
        if result.returncode != 0:
            errors.append(f"cannot enumerate successor paths: {_output(result)}")
            continue
        try:
            changed.update(
                item.decode("utf-8") for item in result.stdout.split(b"\0") if item
            )
        except UnicodeDecodeError as exc:
            errors.append(f"successor path is not UTF-8: {exc}")

    frozen_authorities: set[str] = set()
    for frozen_change in V1_CHANGE_IDS:
        result = _git(
            root,
            "show",
            f"{PARENT_COMMIT}:openspec/changes/{frozen_change}/governance.json",
        )
        try:
            frozen = json.loads(result.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"cannot replay frozen v1 authority {frozen_change}: {exc}")
            continue
        frozen_authorities.update(
            item["path"]
            for item in frozen.get("authorityBindings", [])
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        )
    observed_overlaps = changed & frozen_authorities
    if observed_overlaps != set(EXPECTED_AUTHORITY_SUPERSESSIONS):
        errors.append(
            "post-transition v1 authority overlaps lack an exact typed supersession: "
            f"observed={sorted(observed_overlaps)}, "
            f"expected={sorted(EXPECTED_AUTHORITY_SUPERSESSIONS)}"
        )
    return errors


def _run_v2_current(root: Path, epoch: dict[str, Any], transition_commit: str) -> dict[str, Any]:
    errors = _v2_route_errors(root, epoch, transition_commit)
    try:
        module = _load_fixed_module(
            root, "tools/validate_openspec_construction.py", "root_owned_construction_validator"
        )
        protocol_module = epoch.get("protocolModule")
        protocol_sha256 = (
            protocol_module.get("sha256")
            if isinstance(protocol_module, dict)
            else None
        )
        report = module.validate_repository(
            root,
            delivery_base_commit=transition_commit,
            protocol_module_sha256=protocol_sha256,
        )
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        report = {"status": "cannot_run", "checks": [], "diagnostics": [str(exc)]}
    if errors:
        return {
            "schemaVersion": 2,
            "status": "fail",
            "constructionControlValid": False,
            "runtimeAuthorized": False,
            "promotionEligible": False,
            "checks": report.get("checks", []),
            "diagnostics": errors,
        }
    return report


def aggregate_status(reports: list[dict[str, Any]]) -> str:
    statuses = [item.get("status") for item in reports]
    if any(status == "fail" for status in statuses):
        return "fail"
    if any(status != "pass" for status in statuses):
        return "cannot_run"
    return "pass"


def validate_repository(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    control_errors: list[str] = repository_control_errors(root)
    try:
        registry_value = load_json(_safe_file(root, REGISTRY_PATH))
        if not isinstance(registry_value, dict):
            raise ValueError("root epoch registry is not an object")
        registry = registry_value
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError, DuplicateKeyError) as exc:
        registry = {}
        control_errors.append(f"root epoch registry cannot be read: {exc}")
    control_errors.extend(validate_registry(root, registry))
    routes, route_errors = route_markers(root, registry)
    control_errors.extend(route_errors)
    transition_commit, transition_errors = derive_transition_commit(root, registry)
    control_errors.extend(transition_errors)

    epoch_reports: list[dict[str, Any]] = []
    by_id, _ = _epoch_map(registry)
    if not control_errors and transition_commit is not None:
        v1 = _run_v1_snapshot(root, by_id[V1_EPOCH_ID])
        epoch_reports.append({"epochId": V1_EPOCH_ID, "changeIds": routes[V1_EPOCH_ID], "report": v1})
        if routes[V2_EPOCH_ID]:
            v2 = _run_v2_current(root, by_id[V2_EPOCH_ID], transition_commit)
            epoch_reports.append({"epochId": V2_EPOCH_ID, "changeIds": routes[V2_EPOCH_ID], "report": v2})
    reports = [item["report"] for item in epoch_reports]
    if control_errors:
        status = "fail"
    else:
        status = aggregate_status(reports)
    return {
        "schemaVersion": 1,
        "status": status,
        "scienceControlValid": status == "pass",
        "runtimeAuthorized": False,
        "promotionEligible": False,
        "transitionCommit": transition_commit,
        "activeChangeIds": sorted(change for values in routes.values() for change in values),
        "routes": routes,
        "controlDiagnostics": control_errors,
        "epochReports": epoch_reports,
        "claimBoundary": (
            "The root router replays frozen v1 governance and validates a required "
            "construction successor. It cannot authorize runtime, inspect held-out "
            "outcomes, qualify evidence, or promote a claim."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--operation", choices=("validate", "apply", "archive"), default="validate")
    parser.add_argument("--change")
    arguments = parser.parse_args()
    report = validate_repository(arguments.root)
    if arguments.operation != "validate":
        report["operationPreflight"] = {
            "operation": arguments.operation,
            "changeId": arguments.change,
            "allowed": False,
            "diagnostics": [
                "the root epoch registry has no typed cross-epoch operation receipt"
            ],
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
