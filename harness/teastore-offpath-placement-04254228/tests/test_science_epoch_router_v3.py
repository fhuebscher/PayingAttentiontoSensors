from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ROUTER = _module("validate_science_epochs_v3_tests", "tools/validate_science_epochs_v3.py")


def registry() -> dict:
    return json.loads((ROOT / ROUTER.REGISTRY_PATH).read_text(encoding="utf-8"))


def _markers(root: Path, change_ids: tuple[str, ...] | list[str]) -> None:
    for change_id in change_ids:
        target = root / "openspec" / "changes" / change_id
        target.mkdir(parents=True)
        (target / ".openspec.yaml").write_text(
            "schema: scientific-change\n", encoding="utf-8"
        )


def _repo_git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def test_root_registry_schema_bindings_and_source_commits_are_exact() -> None:
    value = registry()
    assert ROUTER.validate_registry(ROOT, value) == []
    assert value["permissions"] == ROUTER.EXPECTED_PERMISSIONS
    assert tuple(item["changeId"] for item in value["children"]) == ROUTER.CHILD_CHANGE_IDS


def test_registry_rejects_planted_authority_identity_and_replication_defects() -> None:
    clean = registry()
    mutations = []

    permission = copy.deepcopy(clean)
    permission["permissions"]["runtimeAllowed"] = 0
    mutations.append(permission)

    source = copy.deepcopy(clean)
    source["children"][0]["adoptedSource"]["tree"] = "0" * 40
    mutations.append(source)

    digest = copy.deepcopy(clean)
    digest["children"][1]["protocolBindings"]["compiler"]["sha256"] = "0" * 64
    mutations.append(digest)

    artifact_gap = copy.deepcopy(clean)
    artifact_gap["children"][0]["artifactBindings"].pop()
    mutations.append(artifact_gap)

    family_alias = copy.deepcopy(clean)
    family_alias["children"][2]["module"]["replicationContribution"] = "application-family"
    mutations.append(family_alias)

    overlap = copy.deepcopy(clean)
    overlap["children"][3]["allowedPaths"].append(
        clean["children"][0]["allowedPaths"][0]
    )
    mutations.append(overlap)

    transition_extension = copy.deepcopy(clean)
    transition_extension["transition"]["ownedPaths"].append("unowned/root.py")
    mutations.append(transition_extension)

    malformed_module = copy.deepcopy(clean)
    malformed_module["children"][0]["module"] = []
    mutations.append(malformed_module)

    for planted in mutations:
        assert ROUTER.validate_registry(ROOT, planted, pin_bytes=False)


def test_base_markers_are_required_and_each_optional_child_routes_once(
    tmp_path: Path,
) -> None:
    value = registry()
    _markers(tmp_path, list(ROUTER.BASE_CHANGE_IDS) + [ROUTER.CHILD_CHANGE_IDS[2]])

    entries, errors = ROUTER.route_markers(tmp_path, value)

    assert errors == []
    assert [item["changeId"] for item in entries] == [ROUTER.CHILD_CHANGE_IDS[2]]


def test_router_rejects_unknown_child_and_missing_base_marker(tmp_path: Path) -> None:
    value = registry()
    _markers(tmp_path, ROUTER.BASE_CHANGE_IDS[:-1])
    unknown = tmp_path / "openspec" / "changes" / "unregistered-candidate"
    unknown.mkdir(parents=True)
    (unknown / ".openspec.yaml").write_text(
        "schema: scientific-change\n", encoding="utf-8"
    )

    _, errors = ROUTER.route_markers(tmp_path, value)

    assert any("frozen v2 active markers are missing" in item for item in errors)
    assert any("no root-owned route" in item for item in errors)


def test_repository_controls_reject_mode_submodule_and_worktree_concealment(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _repo_git(root, "init", "-q")
    _repo_git(root, "config", "user.name", "Root Test")
    _repo_git(root, "config", "user.email", "root-test@example.invalid")
    (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _repo_git(root, "add", "tracked.txt")
    _repo_git(root, "commit", "-q", "-m", "base")

    _repo_git(root, "config", "core.fileMode", "false")
    mode_errors = ROUTER.repository_control_errors(root)
    assert any("core.fileMode must remain true" in item for item in mode_errors)

    _repo_git(root, "config", "core.fileMode", "true")
    _repo_git(root, "config", "diff.ignoreSubmodules", "all")
    submodule_errors = ROUTER.repository_control_errors(root)
    assert any("local Git configuration can conceal" in item for item in submodule_errors)

    _repo_git(root, "config", "--unset-all", "diff.ignoreSubmodules")
    included = tmp_path / "included-git-config"
    included.write_text("[core]\n\tignoreStat = true\n", encoding="utf-8")
    _repo_git(root, "config", "include.path", str(included))
    include_errors = ROUTER.repository_control_errors(root)
    assert any("local Git configuration can conceal" in item for item in include_errors)

    _repo_git(root, "config", "--unset-all", "include.path")
    _repo_git(root, "config", "extensions.worktreeConfig", "true")
    _repo_git(root, "config", "--worktree", "diff.ignoreSubmodules", "all")
    worktree_errors = ROUTER.repository_control_errors(root)
    assert any("extensions.worktreeConfig is not allowed" in item for item in worktree_errors)


def test_repository_controls_reject_redirected_effective_worktree(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _repo_git(root, "init", "-q")
    _repo_git(root, "config", "user.name", "Root Test")
    _repo_git(root, "config", "user.email", "root-test@example.invalid")
    (root / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    _repo_git(root, "add", "tracked.txt")
    _repo_git(root, "commit", "-q", "-m", "base")
    alternate = tmp_path / "alternate-worktree"
    alternate.mkdir()
    (alternate / "tracked.txt").write_text("reviewed\n", encoding="utf-8")

    _repo_git(root, "config", "core.worktree", str(alternate))
    (root / "tracked.txt").write_text("unreviewed requested-root drift\n", encoding="utf-8")

    errors = ROUTER.repository_control_errors(root)
    assert any("local Git configuration can conceal" in item for item in errors)
    assert any("effective Git worktree differs" in item for item in errors)


def test_repository_controls_reject_legacy_git_grafts(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _repo_git(root, "init", "-q")
    _repo_git(root, "config", "user.name", "Root Test")
    _repo_git(root, "config", "user.email", "root-test@example.invalid")
    (root / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    _repo_git(root, "add", "tracked.txt")
    _repo_git(root, "commit", "-q", "-m", "base")
    commit = _repo_git(root, "rev-parse", "HEAD")
    graft = Path(_repo_git(root, "rev-parse", "--git-path", "info/grafts"))
    if not graft.is_absolute():
        graft = root / graft
    graft.parent.mkdir(parents=True, exist_ok=True)
    graft.write_text(f"{commit} {commit}\n", encoding="utf-8")

    errors = ROUTER.repository_control_errors(root)

    assert any("Git grafts can rewrite routed topology" in item for item in errors)


def test_root_filter_configuration_fails_before_history_or_child_loading(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _repo_git(root, "init", "-q")
    _repo_git(root, "config", "user.name", "Root Test")
    _repo_git(root, "config", "user.email", "root-test@example.invalid")
    (root / ".gitattributes").write_text(
        "tracked.txt filter=evil\n", encoding="utf-8"
    )
    (root / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    _repo_git(root, "add", ".gitattributes", "tracked.txt")
    _repo_git(root, "commit", "-q", "-m", "base")
    sentinel = tmp_path / "ROOT_FILTER_EXECUTED"
    helper = tmp_path / "root_filter_helper.py"
    helper.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        f"Path({str(sentinel)!r}).write_text('executed', encoding='utf-8')\n"
        "sys.stdout.buffer.write(sys.stdin.buffer.read())\n",
        encoding="utf-8",
    )
    _repo_git(root, "config", "filter.evil.clean", f"{sys.executable} {helper}")
    (root / "tracked.txt").write_text("tampered\n", encoding="utf-8")

    report = ROUTER.validate_repository(root)

    assert report["status"] == "fail"
    assert any(
        "local Git configuration can conceal" in item
        for item in report["controlDiagnostics"]
    )
    assert report["epochReports"] == []
    assert not sentinel.exists()


def test_root_transition_is_one_exact_commit_after_frozen_v2() -> None:
    transition, errors = ROUTER.derive_transition_commit(ROOT, registry())
    assert errors == []
    assert transition is not None and transition != ROUTER.BASE_COMMIT


def test_full_v3_report_replays_v2_and_keeps_all_dangerous_authority_false() -> None:
    report = ROUTER.validate_repository(ROOT)
    expected_children = [
        change_id
        for change_id in ROUTER.CHILD_CHANGE_IDS
        if (
            ROOT
            / "openspec"
            / "changes"
            / change_id
            / ".openspec.yaml"
        ).is_file()
    ]

    assert report["status"] == "pass", report
    assert report["scienceControlValid"] is True
    assert report["runtimeAuthorized"] is False
    assert report["promotionEligible"] is False
    assert report["activeChildChangeIds"] == expected_children
    expected_epochs = ["teastore-construction-v2", "multisut-construction-v3"]
    assert [item["epochId"] for item in report["epochReports"]] == expected_epochs
    assert report["epochReports"][0]["report"]["status"] == "pass"


def test_apply_and_archive_preflights_execute_and_deny() -> None:
    router = ROOT / "tools/validate_science_epochs_v3.py"
    for operation in ("apply", "archive"):
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(router),
                "--root",
                str(ROOT),
                "--operation",
                operation,
                "--change",
                ROUTER.CHILD_CHANGE_IDS[0],
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        report = json.loads(result.stdout)
        assert result.returncode == 2
        assert report["status"] == "fail"
        assert report["scienceControlValid"] is False
        assert report["operationPreflight"] == {
            "operation": operation,
            "changeId": ROUTER.CHILD_CHANGE_IDS[0],
            "allowed": False,
            "diagnostics": ["v3 has no human-bound cross-epoch operation receipt"],
            "runtimeAuthorized": False,
            "promotionEligible": False,
        }
