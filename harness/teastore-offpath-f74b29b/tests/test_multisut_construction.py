from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import py_compile
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


VALIDATOR = _module(
    "validate_multisut_construction_tests",
    "tools/validate_multisut_construction.py",
)


def registry() -> dict:
    return json.loads((ROOT / VALIDATOR.REGISTRY_PATH).read_text(encoding="utf-8"))


def entry(change_id: str = "adopt-otel-demo-candidate-harness") -> dict:
    return next(
        copy.deepcopy(item)
        for item in registry()["children"]
        if item["changeId"] == change_id
    )


def manifest(route: dict, base_commit: str = "a" * 40) -> dict:
    change_id = route["changeId"]
    root = f"openspec/changes/{change_id}"
    return {
        "$schema": VALIDATOR.CONTROL_SCHEMA_ID,
        "schemaVersion": 3,
        "id": change_id,
        "claimCeiling": "candidate-harness-construction",
        "parentEpoch": copy.deepcopy(route["parentEpoch"]),
        "adoptedSource": copy.deepcopy(route["adoptedSource"]),
        "module": copy.deepcopy(route["module"]),
        "workflow": {
            "state": "construction-blocked",
            "blockers": copy.deepcopy(route["blockers"]),
        },
        "openSpec": {
            "configPath": "openspec/config.yaml",
            "schemaName": "scientific-change",
            "packageName": "@fission-ai/openspec",
            "version": "1.11.0",
        },
        "artifacts": {
            "proposal": f"{root}/proposal.md",
            "authority": f"{root}/authority.md",
            "specs": [f"{root}/specs/{change_id}/spec.md"],
            "design": f"{root}/design.md",
            "tasks": f"{root}/tasks.md",
            "verification": f"{root}/verification.md",
            "governance": f"{root}/governance.json",
            "findings": f"findings/{change_id}.csv",
        },
        "sourceBindings": copy.deepcopy(route["sourceBindings"]),
        "protocolBindings": copy.deepcopy(route["protocolBindings"]),
        "permissions": copy.deepcopy(VALIDATOR.EXPECTED_PERMISSIONS),
        "checkIds": list(VALIDATOR.CHECK_IDS),
        "humanCheckpoints": copy.deepcopy(VALIDATOR.EXPECTED_CHECKPOINTS),
        "pathOwnership": {
            "baseCommit": base_commit,
            "allowed": copy.deepcopy(route["allowedPaths"]),
            "forbidden": [".local/", "upstream/"],
        },
        "verification": {
            "status": "not-run",
            "independentReviewerRequired": True,
            "reportBinding": None,
        },
    }


def _git_show(commit: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{relative}"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def _materialize_binding(root: Path, binding: dict) -> None:
    path = root / binding["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_git_show(binding["sourceCommit"], binding["path"]))


def _repo_git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _write(root: Path, relative: str, value: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(value)


def _synthetic_admission(tmp_path: Path) -> tuple[Path, dict, dict, str, str]:
    root = tmp_path / "repository"
    root.mkdir()
    _repo_git(root, "init", "-q")
    _repo_git(root, "config", "user.name", "Root Test")
    _repo_git(root, "config", "user.email", "root-test@example.invalid")
    _write(root, ".gitignore", b".local/\n")
    _repo_git(root, "add", ".gitignore")
    _repo_git(root, "commit", "-q", "-m", "base")
    base = _repo_git(root, "rev-parse", "HEAD")
    base_tree = _repo_git(root, "show", "-s", "--format=%T", base)

    _repo_git(root, "checkout", "-q", "-b", "transition")
    _write(root, "root-control.txt", b"root transition\n")
    _repo_git(root, "add", "root-control.txt")
    _repo_git(root, "commit", "-q", "-m", "root transition")
    transition = _repo_git(root, "rev-parse", "HEAD")
    transition_tree = _repo_git(root, "show", "-s", "--format=%T", transition)

    _repo_git(root, "checkout", "-q", "-b", "source", base)
    source_path = "module/source.py"
    source_bytes = b"VALUE = 1\n"
    _write(root, source_path, source_bytes)
    _repo_git(root, "add", source_path)
    _repo_git(root, "commit", "-q", "-m", "source")
    source = _repo_git(root, "rev-parse", "HEAD")
    source_tree = _repo_git(root, "show", "-s", "--format=%T", source)

    _repo_git(root, "checkout", "-q", "transition")
    _repo_git(root, "merge", "--no-ff", "--no-commit", "source")
    change_id = "synthetic-child"
    change_root = f"openspec/changes/{change_id}"
    artifact_values = {
        f"{change_root}/.openspec.yaml": (
            f"schema: scientific-change\nroot: {transition}\ntree: {transition_tree}\n"
        ).encode(),
        f"{change_root}/authority.md": f"root {transition}\n".encode(),
        f"{change_root}/design.md": f"tree {transition_tree}\n".encode(),
        f"{change_root}/governance.json": (
            json.dumps({"rootCommit": transition, "rootTree": transition_tree}) + "\n"
        ).encode(),
        f"{change_root}/proposal.md": b"construction proposal\n",
        f"{change_root}/specs/{change_id}/spec.md": b"construction spec\n",
        f"{change_root}/tasks.md": b"construction tasks\n",
        f"{change_root}/verification.md": b"verification: not-run\n",
    }
    for relative, raw in artifact_values.items():
        _write(root, relative, raw)
    findings = f"findings/{change_id}.csv"
    _write(root, findings, (",".join(VALIDATOR.FINDINGS_HEADER) + "\n").encode())
    _repo_git(root, "add", source_path, change_root, findings)
    _repo_git(root, "commit", "-q", "-m", "admit child")
    admission = _repo_git(root, "rev-parse", "HEAD")

    artifact_bindings = [
        {
            "path": relative,
            "sha256": hashlib.sha256(
                VALIDATOR._artifact_projection(
                    raw, transition, transition_tree, relative
                )
            ).hexdigest(),
            "mode": "100644",
        }
        for relative, raw in artifact_values.items()
    ]
    allowed = sorted([source_path, findings, *artifact_values])
    route = {
        "changeId": change_id,
        "parentEpoch": {
            "changeId": "base",
            "commit": base,
            "tree": base_tree,
        },
        "adoptedSource": {
            "kind": "candidate-construction-source",
            "commit": source,
            "tree": source_tree,
            "qualification": "local-construction-only",
        },
        "module": {
            "id": "synthetic",
            "applicationFamily": "synthetic",
            "channel": "local",
            "replicationContribution": "application-family",
        },
        "blockers": [],
        "sourceBindings": [
            {
                "path": source_path,
                "sourceCommit": source,
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "role": "synthetic source",
                "qualification": "local-construction-source",
            }
        ],
        "artifactBindings": artifact_bindings,
        "protocolBindings": {},
        "allowedPaths": allowed,
    }
    return root, route, manifest(route, transition), transition, admission


def test_schema_and_static_boundaries_accept_every_registered_manifest() -> None:
    for route in registry()["children"]:
        value = manifest(route)
        assert VALIDATOR.check_schema(ROOT, value, route).status == "pass"
        assert VALIDATOR.check_abstention(ROOT, value, route).status == "pass"
        assert VALIDATOR.check_gates(ROOT, value, route).status == "pass"


def test_child_admission_binds_ordered_lineage_entries_and_artifacts(
    tmp_path: Path,
) -> None:
    root, route, value, _, admission = _synthetic_admission(tmp_path)

    assert VALIDATOR.derive_admission_commit(
        root, route, value["pathOwnership"]["baseCommit"]
    ) == (admission, [])
    for checker in (
        VALIDATOR.check_parent_and_source,
        VALIDATOR.check_source_bindings,
        VALIDATOR.check_delivery,
        VALIDATOR.check_artifacts,
    ):
        result = checker(root, value, route)
        assert result.status == "pass", (result.check_id, result.diagnostics)


def test_root_bound_pure_protocol_replays_without_runtime_surface(tmp_path: Path) -> None:
    route = entry()
    protocol = route["protocolBindings"]
    source_commit = route["adoptedSource"]["commit"]
    bindings = {item["path"]: item for item in route["sourceBindings"]}
    for relative in (protocol["descriptor"]["path"], protocol["compiler"]["path"]):
        binding = bindings[relative]
        assert binding["sourceCommit"] == source_commit
        _materialize_binding(tmp_path, binding)

    result = VALIDATOR.check_protocol(tmp_path, manifest(route), route)

    assert result.status == "pass", result.diagnostics


def test_committed_document_tamper_and_one_parent_rebuild_are_rejected(
    tmp_path: Path,
) -> None:
    root, route, value, transition, admission = _synthetic_admission(tmp_path)
    authority = f"openspec/changes/{route['changeId']}/authority.md"
    _write(root, authority, b"runtime approved\n")
    _repo_git(root, "add", authority)
    _repo_git(root, "commit", "-q", "-m", "tamper authority")
    tampered = VALIDATOR.check_parent_and_source(root, value, route)
    assert tampered.status == "fail"
    assert any("one admission commit" in item for item in tampered.diagnostics)

    _repo_git(root, "checkout", "-q", "-b", "one-parent-rebuild", transition)
    _repo_git(root, "checkout", admission, "--", *route["allowedPaths"])
    _repo_git(root, "commit", "-q", "-m", "one parent rebuild")
    rebuilt = VALIDATOR.check_parent_and_source(root, value, route)
    assert rebuilt.status == "fail"
    assert any("ordered [root transition, source]" in item for item in rebuilt.diagnostics)


def test_marker_removal_with_other_child_files_remaining_fails_closed(
    tmp_path: Path,
) -> None:
    root, route, _, transition, _ = _synthetic_admission(tmp_path)
    marker = f"openspec/changes/{route['changeId']}/.openspec.yaml"
    _repo_git(root, "rm", "-q", marker)
    _repo_git(root, "commit", "-q", "-m", "remove optional marker")

    report = VALIDATOR.validate_repository(
        root, [], delivery_base_commit=transition
    )

    assert report["status"] == "fail"
    assert any(
        "active child delivery differs" in item
        for item in report["deliveryDiagnostics"]
    )


def test_source_and_current_git_entries_bind_modes_and_blobs(tmp_path: Path) -> None:
    root, route, value, _, _ = _synthetic_admission(tmp_path)
    source_path = route["sourceBindings"][0]["path"]
    source_file = root / source_path
    source_file.chmod(0o755)
    _repo_git(root, "update-index", "--chmod=+x", source_path)
    _repo_git(root, "commit", "-q", "--amend", "--no-edit")

    source_result = VALIDATOR.check_source_bindings(root, value, route)
    assert source_result.status == "fail"
    assert any("source-to-admission" in item for item in source_result.diagnostics)

    source_file.chmod(0o644)
    delivery_result = VALIDATOR.check_delivery(root, value, route)
    assert delivery_result.status == "fail"
    assert any("working mode differs" in item for item in delivery_result.diagnostics)

    source_file.chmod(0o755)
    source_file.write_bytes(b"VALUE = 2\n")
    byte_result = VALIDATOR.check_delivery(root, value, route)
    assert byte_result.status == "fail"
    assert any("working bytes differ" in item for item in byte_result.diagnostics)


def test_admission_diff_rejects_unregistered_path(tmp_path: Path) -> None:
    root, route, value, _, _ = _synthetic_admission(tmp_path)
    _write(root, "unregistered/runtime.json", b"{}\n")
    _repo_git(root, "add", "unregistered/runtime.json")
    _repo_git(root, "commit", "-q", "--amend", "--no-edit")

    result = VALIDATOR.check_parent_and_source(root, value, route)

    assert result.status == "fail"
    assert any("admission diff differs" in item for item in result.diagnostics)
    assert any("unregistered/runtime.json" in item for item in result.diagnostics)


def test_delivery_drift_prevents_dynamic_child_import(
    tmp_path: Path, monkeypatch,
) -> None:
    change_id = "side-effect-child"
    transition = "a" * 40
    sentinel = tmp_path / "IMPORT_SIDE_EFFECT"
    validator_path = "module/tampered_validator.py"
    compiler_path = "module/compiler.py"
    descriptor_path = "descriptor.json"
    _write(
        tmp_path,
        validator_path,
        (
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('executed', encoding='utf-8')\n"
        ).encode(),
    )
    compiler_bytes = (
        "import hashlib\n"
        "import importlib.util\n"
        "import json\n"
        "from pathlib import Path\n"
        f"_validator = Path(__file__).parents[1] / {validator_path!r}\n"
        "_spec = importlib.util.spec_from_file_location('tampered_validator', _validator)\n"
        "_module = importlib.util.module_from_spec(_spec)\n"
        "_spec.loader.exec_module(_module)\n"
        "def canonical_sha256(value):\n"
        "    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()\n"
        "def load_descriptor(path):\n"
        "    return json.loads(path.read_text())\n"
        "def compile_plan(document):\n"
        "    return {'runCount': 1}\n"
        "def readiness_report(document, plan):\n"
        "    return {'constructionReady': True, 'blockers': []}\n"
    ).encode()
    _write(tmp_path, compiler_path, compiler_bytes)
    descriptor_bytes = b"{}\n"
    _write(tmp_path, descriptor_path, descriptor_bytes)
    protocol = {
        "descriptor": {
            "path": descriptor_path,
            "byteSha256": hashlib.sha256(descriptor_bytes).hexdigest(),
            "canonicalSha256": hashlib.sha256(b"{}").hexdigest(),
        },
        "compiler": {
            "path": compiler_path,
            "sha256": hashlib.sha256(compiler_bytes).hexdigest(),
        },
        "compiledPlan": {"canonicalSha256": "0" * 64, "runCount": 1},
    }
    governance = {
        "pathOwnership": {"baseCommit": transition},
        "protocolBindings": protocol,
    }
    governance_path = f"openspec/changes/{change_id}/governance.json"
    _write(tmp_path, governance_path, (json.dumps(governance) + "\n").encode())
    route = {
        "changeId": change_id,
        "artifactBindings": [],
        "protocolBindings": protocol,
    }

    def result(check_id: str, *diagnostics: str):
        def checker(_root: Path, _manifest: dict, _entry: dict):
            return VALIDATOR.Check(check_id, diagnostics)

        return checker

    monkeypatch.setattr(
        VALIDATOR,
        "CHECKS",
        (
            result("construction-schema"),
            result("parent-and-source"),
            result("source-bindings"),
            result("delivery-ownership", "working bytes differ from child admission"),
            VALIDATOR.check_protocol,
            result("artifact-completeness"),
            result("abstention-boundary"),
            result("gate-boundary"),
        ),
    )

    report = VALIDATOR.validate_change(
        tmp_path, route, delivery_base_commit=transition
    )

    assert report["status"] == "fail"
    protocol_check = next(
        item for item in report["checks"] if item["id"] == "protocol-replay"
    )
    assert protocol_check["status"] == "fail"
    assert "not executed" in protocol_check["diagnostics"][0]
    assert not sentinel.exists()


def test_zero_active_children_require_zero_delivery_and_concealment_is_rejected(
    tmp_path: Path,
) -> None:
    root, route, _, transition, admission = _synthetic_admission(tmp_path)
    _repo_git(root, "checkout", "-q", "--detach", transition)
    assert VALIDATOR.validate_repository(
        root, [], delivery_base_commit=transition
    )["status"] == "pass"

    _repo_git(root, "checkout", "-q", "--detach", admission)
    source_path = route["sourceBindings"][0]["path"]
    _repo_git(root, "update-index", "--assume-unchanged", source_path)
    _, flag_errors = VALIDATOR.changed_paths(root, transition)
    assert any("index concealment flag" in item for item in flag_errors)
    _repo_git(root, "update-index", "--no-assume-unchanged", source_path)

    _repo_git(root, "update-index", "--skip-worktree", source_path)
    _, skip_errors = VALIDATOR.changed_paths(root, transition)
    assert any("index concealment flag" in item for item in skip_errors)
    _repo_git(root, "update-index", "--no-skip-worktree", source_path)

    _write(root, ".local/review-hidden.txt", b"hidden delivery\n")
    _, ignored_errors = VALIDATOR.changed_paths(root, transition)
    assert any("ignored construction delivery" in item for item in ignored_errors)


def test_ignored_cache_allowlist_preserves_forbidden_root_precedence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _repo_git(root, "init", "-q")
    _repo_git(root, "config", "user.name", "Root Test")
    _repo_git(root, "config", "user.email", "root-test@example.invalid")
    _write(
        root,
        ".gitignore",
        b"node_modules/\nresults/generated/\n*.pyc\n",
    )
    _repo_git(root, "add", ".gitignore")
    _repo_git(root, "commit", "-q", "-m", "base")
    base = _repo_git(root, "rev-parse", "HEAD")

    _write(root, "node_modules/package/cache.js", b"cache\n")
    changed, cache_errors = VALIDATOR.changed_paths(root, base)
    assert changed == set()
    assert cache_errors == []

    _write(root, "results/generated/hidden.json", b"{}\n")
    _write(root, ".local/__pycache__/hidden.pyc", b"bytecode\n")
    _write(root, ".local/hidden.pyc", b"bytecode\n")
    _, hidden_errors = VALIDATOR.changed_paths(root, base)
    assert any("results/generated/" in item for item in hidden_errors)
    assert any(".local/" in item for item in hidden_errors)
    assert VALIDATOR._ignored_path_is_cache(".local/__pycache__/hidden.pyc") is False
    assert VALIDATOR._ignored_path_is_cache(".local/hidden.pyc") is False
    assert VALIDATOR._ignored_path_is_cache("upstream/pkg/__pycache__/hidden.pyc") is False


def test_raw_index_scan_catches_stat_cache_hidden_unowned_edit(
    tmp_path: Path,
) -> None:
    root, _, _, transition, _ = _synthetic_admission(tmp_path)
    target = root / ".gitignore"
    original = target.read_bytes()
    replacement = original.replace(b"local", b"locxl")
    assert replacement != original and len(replacement) == len(original)
    _repo_git(root, "config", "core.trustctime", "false")
    _repo_git(root, "config", "core.checkStat", "minimal")
    past_ns = 1_600_000_000_000_000_000
    os.utime(target, ns=(past_ns, past_ns))
    _repo_git(root, "update-index", "--refresh")
    original_stat = target.stat()
    target.write_bytes(replacement)
    os.utime(
        target,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )

    visible = _repo_git(
        root,
        "diff",
        "--ignore-submodules=none",
        "--name-only",
        "--",
        ".gitignore",
    )
    assert visible == ""
    changed, errors = VALIDATOR.changed_paths(root, transition)
    assert errors == []
    assert ".gitignore" in changed


def test_uninitialized_gitlink_must_be_absent_or_empty(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _repo_git(root, "init", "-q")
    _repo_git(root, "config", "user.name", "Root Test")
    _repo_git(root, "config", "user.email", "root-test@example.invalid")
    _write(root, ".gitignore", b"upstream/\n")
    _repo_git(root, "add", ".gitignore")
    _repo_git(root, "commit", "-q", "-m", "base")
    gitlink_commit = _repo_git(root, "rev-parse", "HEAD")
    _repo_git(
        root,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{gitlink_commit},upstream/sample",
    )
    _repo_git(root, "commit", "-q", "-m", "record gitlink")
    base = _repo_git(root, "rev-parse", "HEAD")
    gitlink = root / "upstream" / "sample"
    gitlink.mkdir(parents=True)

    assert VALIDATOR.changed_paths(root, base) == (set(), [])

    _write(root, "upstream/sample/hidden.bin", b"unreviewed\n")
    changed, errors = VALIDATOR.changed_paths(root, base)
    assert "upstream/sample" in changed
    assert any("uninitialized gitlink contains unreviewed payload" in item for item in errors)


def test_initialized_gitlink_requires_exact_clean_recursive_delivery(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _repo_git(root, "init", "-q")
    _repo_git(root, "config", "user.name", "Root Test")
    _repo_git(root, "config", "user.email", "root-test@example.invalid")
    nested = root / "upstream" / "sample"
    nested.mkdir(parents=True)
    _repo_git(nested, "init", "-q")
    _repo_git(nested, "config", "user.name", "Nested Test")
    _repo_git(nested, "config", "user.email", "nested-test@example.invalid")
    _write(nested, "tracked.txt", b"reviewed\n")
    _write(nested, ".gitignore", b"node_modules/\n")
    _repo_git(nested, "add", "tracked.txt", ".gitignore")
    _repo_git(nested, "commit", "-q", "-m", "nested base")
    # Initialized submodules, especially those attached to a linked worktree,
    # legitimately carry a local core.worktree.  The effective-top equality in
    # _audit_gitlink is the authority; merely having this key is not concealment.
    _repo_git(nested, "config", "core.worktree", "..")
    nested_commit = _repo_git(nested, "rev-parse", "HEAD")
    _repo_git(
        root,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{nested_commit},upstream/sample",
    )
    _repo_git(root, "commit", "-q", "-m", "record initialized gitlink")
    base = _repo_git(root, "rev-parse", "HEAD")

    assert VALIDATOR.changed_paths(root, base) == (set(), [])

    _write(nested, "tracked.txt", b"tampered\n")
    changed, errors = VALIDATOR.changed_paths(root, base)
    assert "upstream/sample" in changed
    assert any("raw tracked delivery differs" in item for item in errors)

    _write(nested, "tracked.txt", b"reviewed\n")
    _write(nested, "untracked.txt", b"unreviewed\n")
    changed, errors = VALIDATOR.changed_paths(root, base)
    assert "upstream/sample" in changed
    assert any("untracked delivery" in item for item in errors)

    (nested / "untracked.txt").unlink()
    _write(nested, "node_modules/pkg/evil.js", b"unreviewed ignored cache-shape\n")
    changed, errors = VALIDATOR.changed_paths(root, base)
    assert "upstream/sample" in changed
    assert any(
        "upstream/sample/node_modules/" in item
        and "ignored delivery is forbidden" in item
        for item in errors
    )


def test_nested_filter_configuration_cannot_execute_before_rejection(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _repo_git(root, "init", "-q")
    _repo_git(root, "config", "user.name", "Root Test")
    _repo_git(root, "config", "user.email", "root-test@example.invalid")
    nested = root / "upstream" / "sample"
    nested.mkdir(parents=True)
    _repo_git(nested, "init", "-q")
    _repo_git(nested, "config", "user.name", "Nested Test")
    _repo_git(nested, "config", "user.email", "nested-test@example.invalid")
    _write(nested, ".gitattributes", b"tracked.txt filter=evil\n")
    _write(nested, "tracked.txt", b"reviewed\n")
    _repo_git(nested, "add", ".gitattributes", "tracked.txt")
    _repo_git(nested, "commit", "-q", "-m", "nested base")
    nested_commit = _repo_git(nested, "rev-parse", "HEAD")
    _repo_git(
        root,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{nested_commit},upstream/sample",
    )
    _repo_git(root, "commit", "-q", "-m", "record initialized gitlink")
    base = _repo_git(root, "rev-parse", "HEAD")
    sentinel = tmp_path / "NESTED_FILTER_EXECUTED"
    helper = tmp_path / "filter_helper.py"
    helper.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        f"Path({str(sentinel)!r}).write_text('executed', encoding='utf-8')\n"
        "sys.stdout.buffer.write(sys.stdin.buffer.read())\n",
        encoding="utf-8",
    )
    _repo_git(nested, "config", "filter.evil.clean", f"{sys.executable} {helper}")
    _write(nested, "tracked.txt", b"tampered\n")

    changed, errors = VALIDATOR.changed_paths(root, base)

    assert "upstream/sample" in changed
    assert any("nested local Git configuration" in item for item in errors)
    assert not sentinel.exists()


def test_repository_delivery_gate_prevents_every_protocol_replay(
    tmp_path: Path, monkeypatch,
) -> None:
    root, route, _, transition, _ = _synthetic_admission(tmp_path)
    sentinel = tmp_path / "GLOBAL_PROTOCOL_SIDE_EFFECT"

    def static(check_id: str):
        def checker(_root: Path, _manifest: dict, _entry: dict):
            return VALIDATOR.Check(check_id, ())

        return checker

    def protocol(_root: Path, _manifest: dict, _entry: dict):
        sentinel.write_text("executed", encoding="utf-8")
        return VALIDATOR.Check("protocol-replay", ())

    monkeypatch.setattr(VALIDATOR, "check_protocol", protocol)
    monkeypatch.setattr(
        VALIDATOR,
        "CHECKS",
        (
            static("construction-schema"),
            static("parent-and-source"),
            static("source-bindings"),
            static("delivery-ownership"),
            protocol,
            static("artifact-completeness"),
            static("abstention-boundary"),
            static("gate-boundary"),
        ),
    )
    _write(root, ".local/ignored-extra.pyc", b"concealed\n")

    report = VALIDATOR.validate_repository(
        root, [route], delivery_base_commit=transition
    )

    assert report["status"] == "fail"
    assert any("ignored construction delivery" in item for item in report["deliveryDiagnostics"])
    protocol_check = next(
        item
        for item in report["changeReports"][0]["checks"]
        if item["id"] == "protocol-replay"
    )
    assert protocol_check["status"] == "fail"
    assert any(
        "repository-wide delivery gate failed" in diagnostic
        for diagnostic in protocol_check["diagnostics"]
    )
    assert not sentinel.exists()


def test_malformed_governance_fails_typed_checks_without_protocol_execution(
    tmp_path: Path, monkeypatch,
) -> None:
    root, route, _, transition, _ = _synthetic_admission(tmp_path)
    governance_path = (
        root / "openspec" / "changes" / route["changeId"] / "governance.json"
    )
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    governance["workflow"] = []
    governance_path.write_text(json.dumps(governance) + "\n", encoding="utf-8")
    sentinel = tmp_path / "MALFORMED_PROTOCOL_SIDE_EFFECT"

    def protocol(_root: Path, _manifest: dict, _entry: dict):
        sentinel.write_text("executed", encoding="utf-8")
        return VALIDATOR.Check("protocol-replay", ())

    monkeypatch.setattr(VALIDATOR, "check_protocol", protocol)
    report = VALIDATOR.validate_change(
        root, route, delivery_base_commit=transition
    )

    assert report["status"] == "fail"
    parent_check = next(
        item for item in report["checks"] if item["id"] == "parent-and-source"
    )
    assert parent_check["status"] == "fail"
    protocol_check = next(
        item for item in report["checks"] if item["id"] == "protocol-replay"
    )
    assert protocol_check["status"] == "fail"
    assert any("not executed" in item for item in protocol_check["diagnostics"])
    assert not sentinel.exists()


def test_strict_registry_json_rejects_duplicate_members(tmp_path: Path) -> None:
    planted = tmp_path / "duplicate.json"
    planted.write_text(
        '{"role":"compiler","role":"compiler"}\n', encoding="utf-8"
    )

    with pytest.raises(VALIDATOR.DuplicateKeyError, match="duplicate JSON member: role"):
        VALIDATOR.load_json(planted)


def test_artifact_decode_and_nonempty_not_run_findings_fail_with_diagnostics(
    tmp_path: Path,
) -> None:
    root, route, value, _, _ = _synthetic_admission(tmp_path)
    marker = f"openspec/changes/{route['changeId']}/.openspec.yaml"
    _write(root, marker, b"\xff\xfe")
    authority = value["artifacts"]["authority"]
    _write(
        root,
        authority,
        (VALIDATOR.ROOT_COMMIT_SENTINEL + "\n").encode(),
    )
    findings = value["artifacts"]["findings"]
    _write(
        root,
        findings,
        (",".join(VALIDATOR.FINDINGS_HEADER) + "\nrow,that,is,not,header-only\n").encode(),
    )

    result = VALIDATOR.check_artifacts(root, value, route)

    assert result.status == "fail"
    assert any("not UTF-8" in item for item in result.diagnostics)
    assert any("reserved root projection sentinel" in item for item in result.diagnostics)
    assert any("header-only" in item for item in result.diagnostics)

    _write(root, findings, b'"unterminated\n')
    malformed_csv = VALIDATOR.check_artifacts(root, value, route)
    assert any(
        "findings ledger cannot be decoded" in item
        for item in malformed_csv.diagnostics
    )


def test_protocol_receipt_requires_exact_boolean_structural_validity(
    tmp_path: Path,
) -> None:
    descriptor_path = "descriptor.json"
    compiler_path = "compiler.py"
    descriptor = b"{}\n"
    compiler = (
        "import hashlib\n"
        "import json\n"
        "def canonical_sha256(value):\n"
        "    raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode()\n"
        "    return hashlib.sha256(raw).hexdigest()\n"
        "def load_descriptor(path):\n"
        "    return json.loads(path.read_text())\n"
        "def compile_plan(document):\n"
        "    return {'runCount': 1}\n"
        "def readiness_report(document, plan):\n"
        "    return {'constructionReady': 1, 'blockers': []}\n"
    ).encode()
    _write(tmp_path, descriptor_path, descriptor)
    _write(tmp_path, compiler_path, compiler)
    protocol = {
        "descriptor": {
            "path": descriptor_path,
            "byteSha256": hashlib.sha256(descriptor).hexdigest(),
            "canonicalSha256": hashlib.sha256(b"{}").hexdigest(),
        },
        "compiler": {
            "path": compiler_path,
            "sha256": hashlib.sha256(compiler).hexdigest(),
        },
        "compiledPlan": {
            "canonicalSha256": hashlib.sha256(b'{"runCount":1}').hexdigest(),
            "runCount": 1,
        },
    }
    route = {
        "changeId": "typed-receipt",
        "blockers": [],
        "protocolBindings": protocol,
    }

    result = VALIDATOR.check_protocol(
        tmp_path, {"protocolBindings": copy.deepcopy(protocol)}, route
    )

    assert result.status == "fail"
    assert result.diagnostics == (
        "construction receipt has no positive structural-validity field",
    )

    for literal, value in (("True", True), ("1.0", 1.0)):
        planted_compiler = compiler.replace(
            b"return {'runCount': 1}\n",
            f"return {{'runCount': {literal}}}\n".encode(),
        ).replace(
            b"'constructionReady': 1",
            b"'constructionReady': True",
        )
        _write(tmp_path, compiler_path, planted_compiler)
        planted_protocol = copy.deepcopy(protocol)
        planted_protocol["compiler"]["sha256"] = hashlib.sha256(
            planted_compiler
        ).hexdigest()
        planted_protocol["compiledPlan"]["canonicalSha256"] = hashlib.sha256(
            json.dumps(
                {"runCount": value}, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        planted = VALIDATOR.check_protocol(
            tmp_path,
            {"protocolBindings": copy.deepcopy(planted_protocol)},
            {
                "changeId": "typed-run-count",
                "blockers": [],
                "protocolBindings": planted_protocol,
            },
        )
        assert planted.status == "fail"
        assert "compiled run count is not the exact registered integer" in planted.diagnostics


def test_artifact_projection_rejects_short_transition_identity() -> None:
    commit = "1" * 40
    tree = "2" * 40
    projected = VALIDATOR._artifact_projection(
        f"root={commit}\ntree={tree}\n".encode(), commit, tree, "artifact.md"
    )
    assert VALIDATOR.ROOT_COMMIT_SENTINEL.encode() in projected
    assert VALIDATOR.ROOT_TREE_SENTINEL.encode() in projected

    with pytest.raises(ValueError, match="abbreviated root transition commit"):
        VALIDATOR._artifact_projection(
            f"root={commit}\nshort={commit[:7]}\n".encode(),
            commit,
            tree,
            "artifact.md",
        )
    with pytest.raises(ValueError, match="abbreviated root transition tree"):
        VALIDATOR._artifact_projection(
            f"root={commit}\nshort-tree={tree[:12]}\n".encode(),
            commit,
            tree,
            "artifact.md",
        )


def test_every_registered_checker_is_watched_rejecting_a_planted_defect() -> None:
    route = entry()
    clean = manifest(route)

    wrong_schema = copy.deepcopy(clean)
    wrong_schema["permissions"]["runtimeAllowed"] = True

    wrong_parent = copy.deepcopy(clean)
    wrong_parent["parentEpoch"]["tree"] = "0" * 40

    wrong_sources = copy.deepcopy(clean)
    wrong_sources["sourceBindings"].pop()

    wrong_delivery = copy.deepcopy(clean)
    wrong_delivery["pathOwnership"]["allowed"].append("unregistered/result.json")

    wrong_protocol = copy.deepcopy(clean)
    wrong_protocol["protocolBindings"]["compiledPlan"]["canonicalSha256"] = "0" * 64

    wrong_artifacts = copy.deepcopy(clean)
    wrong_artifacts["artifacts"]["proposal"] = "missing/proposal.md"

    wrong_abstention = copy.deepcopy(clean)
    wrong_abstention["workflow"]["state"] = "ready"

    wrong_gate = copy.deepcopy(clean)
    wrong_gate["humanCheckpoints"][1]["status"] = "pending"

    defects = {
        "construction-schema": (VALIDATOR.check_schema, wrong_schema),
        "parent-and-source": (VALIDATOR.check_parent_and_source, wrong_parent),
        "source-bindings": (VALIDATOR.check_source_bindings, wrong_sources),
        "delivery-ownership": (VALIDATOR.check_delivery, wrong_delivery),
        "protocol-replay": (VALIDATOR.check_protocol, wrong_protocol),
        "artifact-completeness": (VALIDATOR.check_artifacts, wrong_artifacts),
        "abstention-boundary": (VALIDATOR.check_abstention, wrong_abstention),
        "gate-boundary": (VALIDATOR.check_gates, wrong_gate),
    }

    assert tuple(defects) == VALIDATOR.CHECK_IDS
    for check_id, (checker, planted) in defects.items():
        result = checker(ROOT, planted, route)
        assert result.check_id == check_id
        assert result.status == "fail", check_id


def test_reserved_authority_requires_typed_false_and_current_claims_stay_blocked() -> None:
    planted = {
        "plan": {
            "runtimeAuthorized": 0,
            "maximumFutureRunEvidenceLabel": "candidate-evidence",
            "maximumRunEvidenceLabel": "candidate-evidence",
        },
        "receipt": [
            {"canonicalEvidenceEligible": True, "verdict": "ready"}
        ],
    }
    errors = VALIDATOR._true_authority_errors(planted)
    assert any("$.plan.runtimeAuthorized must be the exact JSON boolean false" in item for item in errors)
    assert not any("maximumFutureRunEvidenceLabel" in item for item in errors)
    assert any("$.plan.maximumRunEvidenceLabel exceeds" in item for item in errors)
    assert any("$.receipt[0].canonicalEvidenceEligible must be" in item for item in errors)
    assert any("$.receipt[0].verdict exceeds" in item for item in errors)

    route = entry()
    untyped_permissions = manifest(route)
    untyped_permissions["permissions"]["runtimeAllowed"] = 0
    assert VALIDATOR.check_gates(
        ROOT, untyped_permissions, route
    ).status == "fail"


def test_importfrom_module_is_checked_for_runtime_surface(tmp_path: Path) -> None:
    compiler = tmp_path / "compiler.py"
    compiler.write_text("from subprocess import run\n", encoding="utf-8")

    assert VALIDATOR._compiler_import_errors(compiler) == [
        "protocol compiler imports forbidden runtime surface: ['subprocess']"
    ]


def test_protocol_replay_bypasses_ignored_repository_bytecode(tmp_path: Path) -> None:
    compiler = tmp_path / "compiler.py"
    compiler.write_text('VALUE = "evil"\n', encoding="utf-8")
    original = compiler.stat().st_mtime_ns
    py_compile.compile(str(compiler), doraise=True)
    compiler.write_text('VALUE = "safe"\n', encoding="utf-8")
    os.utime(compiler, ns=(original, original))

    direct = VALIDATOR._load_protocol(tmp_path, "compiler.py", "cache-test")
    assert direct.VALUE == "safe"

    with VALIDATOR._isolated_repository_bytecode():
        spec = importlib.util.spec_from_file_location("nested_cache_test", compiler)
        assert spec is not None and spec.loader is not None
        nested = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(nested)
    assert nested.VALUE == "safe"
