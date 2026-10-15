from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)
FRAMEWORK_COMMIT = "a" * 40
FRAMEWORK_TREE = "b" * 40


def _load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load(
    "candidate_runtime_adapter_tests",
    "modules/teastore/execution/candidate_runtime_adapter.py",
)
orchestrator = _load(
    "candidate_orchestrator_for_runtime_tests",
    "modules/teastore/execution/candidate_orchestrator.py",
)
def _git_state(
    *,
    commit: str = FRAMEWORK_COMMIT,
    head_tree: str = FRAMEWORK_TREE,
    commit_tree: str = FRAMEWORK_TREE,
    tracked_dirty: bool = False,
    status: bytes = b"",
    concealment_config: bytes = b"",
    index_concealment: tuple[str, ...] = (),
):
    return runtime.GitRepositoryState(
        commit=commit,
        head_tree=head_tree,
        commit_tree=commit_tree,
        tracked_dirty=tracked_dirty,
        status=status,
        concealment_config=concealment_config,
        index_concealment=index_concealment,
    )


def _write(path: Path, document: dict) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


@pytest.fixture
def bindings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Campaign unit tests operate on a synthetic root and explicitly isolate
    # production Git discovery. Dedicated tests below exercise its fail-closed
    # boundary rather than weakening inspect_campaign for tests.
    monkeypatch.setattr(runtime, "_git_repository_state", _git_state)
    root = tmp_path / "campaign"
    orchestrator.materialize_campaign(root)
    return runtime.inspect_campaign(root, FRAMEWORK_COMMIT)


def test_git_query_uses_controlled_noninteractive_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def planted_run(command, **kwargs):
        observed["command"] = command
        observed["environment"] = kwargs["env"]
        return type("Result", (), {"returncode": 0, "stdout": b"ok\n", "stderr": b""})()

    monkeypatch.setattr(runtime.subprocess, "run", planted_run)
    monkeypatch.setenv("GIT_DIR", "/planted/alternate/repository")
    monkeypatch.setenv("GIT_REPLACE_REF_BASE", "refs/planted/")
    monkeypatch.setenv("PATH", "/planted/poisoned/path")
    assert runtime._git(("rev-parse", "HEAD")) == b"ok\n"
    environment = observed["environment"]
    assert "GIT_DIR" not in environment
    assert "GIT_REPLACE_REF_BASE" not in environment
    assert environment["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert environment["GIT_CONFIG_SYSTEM"] == "/dev/null"
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["PATH"] == "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"


def test_arbitrary_full_hex_framework_commit_cannot_be_echoed_into_gate_binding(
    bindings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime, "_git_repository_state", _git_state)
    with pytest.raises(runtime.GateError, match="exact current Git HEAD"):
        runtime.inspect_campaign(bindings.root, "c" * 40)


def test_dirty_worktree_rejects_before_gate_plan_binding(
    bindings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime,
        "_git_repository_state",
        lambda: _git_state(status=b" M modules/teastore/execution/candidate_pilot.py\0"),
    )
    with pytest.raises(runtime.GateError, match="worktree is not clean"):
        runtime.inspect_campaign(bindings.root, FRAMEWORK_COMMIT)


def test_dirty_submodule_rejects_before_gate_plan_binding(
    bindings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime,
        "_git_repository_state",
        lambda: _git_state(status=b" m upstream/teastore\0"),
    )
    with pytest.raises(runtime.GateError, match="worktree is not clean"):
        runtime.inspect_campaign(bindings.root, FRAMEWORK_COMMIT)


def test_local_submodule_ignore_config_rejects_before_gate_plan_binding(
    bindings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime,
        "_git_repository_state",
        lambda: _git_state(
            concealment_config=(
                b"file:.git/config\tsubmodule.upstream/teastore.ignore all\n"
            )
        ),
    )
    with pytest.raises(runtime.GateError, match="configuration can conceal"):
        runtime.inspect_campaign(bindings.root, FRAMEWORK_COMMIT)


@pytest.mark.parametrize(
    "relative",
    (
        "modules/teastore/execution/candidate_pilot.py",
        "modules/teastore/execution/candidate_runtime_adapter.py",
    ),
)
def test_index_concealment_flag_rejects_before_gate_plan_binding(
    bindings,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    monkeypatch.setattr(
        runtime,
        "_git_repository_state",
        lambda: _git_state(index_concealment=(relative,)),
    )
    with pytest.raises(runtime.GateError, match="index flags can conceal"):
        runtime.inspect_campaign(bindings.root, FRAMEWORK_COMMIT)


def test_git_cleanliness_queries_force_submodule_visibility_and_parse_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def planted_git(arguments: tuple[str, ...]) -> bytes:
        calls.append(arguments)
        if arguments == ("rev-parse", "--show-toplevel"):
            return f"{ROOT}\n".encode()
        if arguments == ("rev-parse", "--verify", "HEAD^{commit}"):
            return f"{FRAMEWORK_COMMIT}\n".encode()
        if arguments in {
            ("rev-parse", "--verify", "HEAD^{tree}"),
            ("rev-parse", "--verify", f"{FRAMEWORK_COMMIT}^{{tree}}"),
        }:
            return f"{FRAMEWORK_TREE}\n".encode()
        if arguments[0] == "status":
            return b" m upstream/teastore\0"
        if arguments[0] == "ls-files":
            return (
                b"h modules/teastore/execution/candidate_pilot.py\0"
                b"S modules/teastore/execution/candidate_runtime_adapter.py\0"
            )
        raise AssertionError(arguments)

    def planted_result(
        arguments: tuple[str, ...], *, allowed_returncodes: tuple[int, ...] = (0,),
    ):
        calls.append(arguments)
        if arguments[0] == "diff-index":
            return type(
                "Result", (), {"returncode": 1, "stdout": b"", "stderr": b""}
            )()
        if arguments[0] == "config":
            assert 1 in allowed_returncodes
            return type(
                "Result", (), {"returncode": 1, "stdout": b"", "stderr": b""}
            )()
        raise AssertionError(arguments)

    monkeypatch.setattr(runtime, "_git", planted_git)
    monkeypatch.setattr(runtime, "_git_result", planted_result)
    state = runtime._git_repository_state()
    diff_call = next(row for row in calls if row[0] == "diff-index")
    status_call = next(row for row in calls if row[0] == "status")
    assert "--ignore-submodules=none" in diff_call
    assert "--ignore-submodules=none" in status_call
    assert state.tracked_dirty is True
    assert state.status == b" m upstream/teastore\0"
    assert state.index_concealment == (
        "modules/teastore/execution/candidate_pilot.py",
        "modules/teastore/execution/candidate_runtime_adapter.py",
    )


def test_commit_tree_mismatch_rejects_before_gate_plan_binding(
    bindings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime,
        "_git_repository_state",
        lambda: _git_state(commit_tree="c" * 40),
    )
    with pytest.raises(runtime.GateError, match="HEAD tree differs"):
        runtime.inspect_campaign(bindings.root, FRAMEWORK_COMMIT)


@pytest.mark.parametrize(
    "controller_name,relative_path",
    tuple(sorted(runtime.CONTROLLER_PATHS.items())),
)
def test_each_digest_bound_runtime_input_drift_rejects_during_binding_inspection(
    bindings,
    monkeypatch: pytest.MonkeyPatch,
    controller_name: str,
    relative_path: str,
) -> None:
    assert runtime.CONTROLLER_PATHS[controller_name] == relative_path
    states = iter(
        (
            _git_state(),
            _git_state(status=f" M {relative_path}\0".encode()),
        )
    )
    monkeypatch.setattr(runtime, "_git_repository_state", lambda: next(states))
    with pytest.raises(runtime.GateError, match="worktree is not clean"):
        runtime.inspect_campaign(bindings.root, FRAMEWORK_COMMIT)


def test_head_or_tree_change_during_controller_read_rejects_binding(
    bindings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    states = iter((_git_state(), _git_state(commit="c" * 40, head_tree="d" * 40,
                                             commit_tree="d" * 40)))
    monkeypatch.setattr(runtime, "_git_repository_state", lambda: next(states))
    with pytest.raises(runtime.GateError, match="exact current Git HEAD"):
        runtime.inspect_campaign(bindings.root, FRAMEWORK_COMMIT)


def test_immediate_runtime_and_evidence_inputs_are_in_digest_closure() -> None:
    required = {
        "performance-receipt-validator",
        "native-kieker-validator",
        "performance-probe-v3",
        "native-token-correlation-schema",
        "server-policy",
        "compose-kieker",
        "compose-rabbitmq",
        "compose-isolation",
        "compose-selected",
        "posture-none",
        "posture-full",
        "auth-selection",
        "activation-catalog",
        "fault-qualification",
        "patched-image-inputs",
        "patched-image-lock-schema",
        "patched-image-auth-dockerfile",
        "patched-image-persistence-dockerfile",
        "patched-image-webui-dockerfile",
        "teastore-source-lock",
        "application-witness-v2-manifest",
        "application-witness-v2-patch",
    }
    assert required <= set(runtime.CONTROLLER_PATHS)


def _gate_plan(bindings) -> dict:
    return {
        "schemaVersion": 1,
        "kind": runtime.PLAN_KIND,
        "gate": "GATE-PLAN",
        "decision": "approve-exact-plan",
        "typedApproval": runtime.expected_gate_plan_text(bindings),
        "approvedBy": "external-human-reviewer",
        "approvedAt": (NOW - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "bindings": runtime.plan_binding(bindings),
        "runtimeAuthorized": False,
        "promotionAuthorized": False,
    }


def _readiness(bindings, parent: Path) -> dict:
    controllers = copy.deepcopy(bindings.controller_sha256)
    artifact_root = parent / "runtime-readiness-artifacts"
    artifact_root.mkdir()
    seams = {}
    validator_sha = controllers["candidate-runtime-adapter"]
    for index, name in enumerate(runtime.READINESS_SEAMS):
        evidence_path = f"seams/{index:02d}-{name}-pass.json"
        witness_path = f"seams/{index:02d}-{name}-failure.json"
        (artifact_root / "seams").mkdir(exist_ok=True)
        _write(artifact_root / evidence_path, {
            "schemaVersion": 1,
            "kind": runtime.READINESS_EVIDENCE_KIND,
            "seam": name,
            "status": "pass",
            "validatorSha256": validator_sha,
            "observations": {"fixture": True},
        })
        _write(artifact_root / witness_path, {
            "schemaVersion": 1,
            "kind": runtime.FAILURE_WITNESS_KIND,
            "seam": name,
            "status": "detected",
            "plantedDefect": f"planted-{name}",
            "checkerExitCode": 2,
            "validatorSha256": validator_sha,
            "observations": {"fixture": True},
        })
        seams[name] = {
            "status": "pass",
            "evidencePath": evidence_path,
            "evidenceSha256": hashlib.sha256(
                (artifact_root / evidence_path).read_bytes()
            ).hexdigest(),
            "failureWitnessPath": witness_path,
            "failureWitnessSha256": hashlib.sha256(
                (artifact_root / witness_path).read_bytes()
            ).hexdigest(),
        }
    implementation_path = "transport/candidate_transport.py"
    (artifact_root / "transport").mkdir()
    (artifact_root / implementation_path).write_text(
        "# synthetic bounded transport fixture; never imported\n"
    )
    transport = {
        "schemaVersion": 1,
        "contract": runtime.TRANSPORT_CONTRACT,
        "target": runtime.TARGET,
        "evidenceLabel": runtime.EVIDENCE_LABEL,
        "outerLeasePath": runtime.LEASE_PATH,
        "outerLeaseScope": "entire-27-cell-one-shot",
        "deadlineEnforced": True,
        "cleanupEnforced": True,
        "candidateDescriptorAccepted": True,
        "controllerDigests": controllers,
        "implementationPath": implementation_path,
        "implementationSha256": hashlib.sha256(
            (artifact_root / implementation_path).read_bytes()
        ).hexdigest(),
    }
    return {
        "schemaVersion": 1,
        "kind": runtime.READINESS_KIND,
        "studyEpoch": runtime.STUDY_EPOCH,
        "frameworkCommit": FRAMEWORK_COMMIT,
        "descriptorCanonicalSha256": bindings.descriptor_sha256,
        "compiledPlanCanonicalSha256": bindings.plan_sha256,
        "target": runtime.TARGET,
        "runCount": 27,
        "artifactRoot": artifact_root.name,
        "controllerDigests": controllers,
        "imageDigests": {
            name: f"candidate/{name}@sha256:{index:064x}"
            for index, name in enumerate(runtime.IMAGE_SERVICES, 1)
        },
        "patchedServices": list(runtime.PATCHED_SERVICES),
        "seams": seams,
        "transport": transport,
        "runtimeReady": True,
        "candidateEvidenceAuthorized": False,
        "promotionAuthorized": False,
    }


def _gate_run(bindings, gate_plan: dict, readiness: dict, *, hours: int = 9) -> dict:
    plan_sha = runtime.validate_gate_plan(gate_plan, bindings)
    readiness_sha = runtime.canonical_sha256(readiness)
    authorization = runtime.run_authorization(
        bindings,
        plan_sha,
        readiness_sha,
        campaign_id="candidate-pilot-20260829-a",
        not_before=NOW.isoformat().replace("+00:00", "Z"),
        authorization_deadline=(NOW + timedelta(hours=hours)).isoformat().replace(
            "+00:00", "Z"
        ),
    )
    return {
        "schemaVersion": 1,
        "kind": runtime.RUN_KIND,
        "gate": "GATE-RUN",
        "decision": "authorize-one-shot-exact-run",
        "typedApproval": runtime.expected_gate_run_text(authorization),
        "approvedBy": "external-human-operator",
        "approvedAt": NOW.isoformat().replace("+00:00", "Z"),
        "authorization": authorization,
        "promotionAuthorized": False,
    }


def _package(tmp_path: Path, bindings):
    """Build a synthetic package for pure contract-construction tests only.

    This deliberately does not call ``authorize_from_files``: retained seam
    receipts are construction fixtures and the production readiness replay is
    intentionally unavailable.
    """

    plan = _gate_plan(bindings)
    readiness = _readiness(bindings, tmp_path)
    run = _gate_run(bindings, plan, readiness)
    plan_sha = runtime.validate_gate_plan(plan, bindings)
    readiness_sha = runtime.canonical_sha256(readiness)
    run_sha = runtime.validate_gate_run(
        run, bindings, plan, plan_sha, readiness_sha, now=NOW,
    )
    package = runtime.RuntimePackage(
        bindings=bindings,
        gate_plan=copy.deepcopy(plan),
        gate_plan_sha256=plan_sha,
        readiness=copy.deepcopy(readiness),
        readiness_sha256=readiness_sha,
        gate_run=copy.deepcopy(run),
        gate_run_sha256=run_sha,
        validated_at=NOW,
    )
    return package


def test_adapter_has_no_builtin_process_or_network_transport() -> None:
    source = (ROOT / "modules/teastore/execution/candidate_runtime_adapter.py").read_text()
    tree = ast.parse(source)
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not ({"socket", "paramiko"} & imported)
    assert source.count("subprocess.run(") == 1
    assert "subprocess.Popen(" not in source
    assert "subprocess.check_" not in source
    assert not hasattr(runtime, "main")


def test_exact_plan_replays_but_self_declared_readiness_is_construction_blocked(
    tmp_path: Path, bindings,
) -> None:
    plan = _gate_plan(bindings)
    readiness = _readiness(bindings, tmp_path)
    assert runtime.validate_gate_plan(plan, bindings) == runtime.canonical_sha256(plan)
    with pytest.raises(runtime.GateError, match="construction blocked"):
        runtime.validate_readiness(
            readiness, bindings, readiness_parent=tmp_path,
        )
    assert plan["runtimeAuthorized"] is False
    assert readiness["candidateEvidenceAuthorized"] is False
    assert len(bindings.cells) == 27


@pytest.mark.parametrize(
    "plant",
    (
        "generic-plan-approval",
        "plan-schema-bool",
        "plan-binding-run-count-float",
        "plan-runtime-authority",
        "readiness-schema-bool",
        "readiness-run-count-float",
        "blocked-readiness-seam",
        "controller-byte-drift",
        "diagnostic-only-transport",
        "missing-readiness-evidence",
        "tampered-failure-witness",
        "symlinked-transport-implementation",
        "readiness-path-escape",
    ),
)
def test_planted_gate_and_readiness_defects_fail_before_transport(
    tmp_path: Path, bindings, plant: str,
) -> None:
    plan = _gate_plan(bindings)
    readiness = _readiness(bindings, tmp_path)
    run = _gate_run(bindings, plan, readiness)
    if plant == "generic-plan-approval":
        plan["typedApproval"] = "yes"
    elif plant == "plan-schema-bool":
        plan["schemaVersion"] = True
    elif plant == "plan-binding-run-count-float":
        plan["bindings"]["runCount"] = 27.0
    elif plant == "plan-runtime-authority":
        plan["runtimeAuthorized"] = True
    elif plant == "readiness-schema-bool":
        readiness["schemaVersion"] = True
    elif plant == "readiness-run-count-float":
        readiness["runCount"] = 27.0
    elif plant == "blocked-readiness-seam":
        readiness["seams"][runtime.READINESS_SEAMS[0]]["status"] = "blocked"
    elif plant == "controller-byte-drift":
        readiness["controllerDigests"]["candidate-validator"] = "0" * 64
    elif plant == "diagnostic-only-transport":
        readiness["transport"]["candidateDescriptorAccepted"] = False
    elif plant == "missing-readiness-evidence":
        row = readiness["seams"][runtime.READINESS_SEAMS[0]]
        (tmp_path / readiness["artifactRoot"] / row["evidencePath"]).unlink()
    elif plant == "tampered-failure-witness":
        row = readiness["seams"][runtime.READINESS_SEAMS[0]]
        path = tmp_path / readiness["artifactRoot"] / row["failureWitnessPath"]
        path.write_text(path.read_text() + "tampered\n")
    elif plant == "symlinked-transport-implementation":
        path = tmp_path / readiness["artifactRoot"] / readiness["transport"][
            "implementationPath"
        ]
        path.unlink()
        path.symlink_to(tmp_path / readiness["artifactRoot"] / readiness["seams"][
            runtime.READINESS_SEAMS[0]
        ]["evidencePath"])
    elif plant == "readiness-path-escape":
        readiness["seams"][runtime.READINESS_SEAMS[0]]["evidencePath"] = "../escape.json"
    paths = [tmp_path / name for name in ("gate-plan.json", "readiness.json", "gate-run.json")]
    for path, document in zip(paths, (plan, readiness, run)):
        _write(path, document)
    with pytest.raises(runtime.GateError):
        runtime.authorize_from_files(
            bindings.root,
            paths[0],
            paths[1],
            paths[2],
            framework_commit=FRAMEWORK_COMMIT,
            clock=lambda: NOW,
        )


@pytest.mark.parametrize(
    "plant",
    (
        "retry-enabled", "cell-order-substitution", "stale-run-gate",
        "five-hour-window", "bool-attempt", "float-run-count",
        "integer-one-shot", "float-cleanup-reserve",
    ),
)
def test_planted_gate_run_defects_fail_independent_of_unimplemented_readiness(
    tmp_path: Path, bindings, plant: str,
) -> None:
    plan = _gate_plan(bindings)
    readiness = _readiness(bindings, tmp_path)
    plan_sha = runtime.validate_gate_plan(plan, bindings)
    readiness_sha = runtime.canonical_sha256(readiness)
    run = _gate_run(bindings, plan, readiness)
    if plant == "retry-enabled":
        run["authorization"]["retryAllowed"] = True
    elif plant == "cell-order-substitution":
        run["authorization"]["authorizedRunIds"][:2] = reversed(
            run["authorization"]["authorizedRunIds"][:2]
        )
    elif plant == "stale-run-gate":
        run["approvedAt"] = (NOW - timedelta(minutes=16)).isoformat().replace(
            "+00:00", "Z"
        )
    elif plant == "five-hour-window":
        authorization = run["authorization"]
        authorization["authorizationDeadline"] = (
            NOW + timedelta(hours=5)
        ).isoformat().replace("+00:00", "Z")
        run["typedApproval"] = runtime.expected_gate_run_text(authorization)
    elif plant == "bool-attempt":
        run["authorization"]["attempt"] = True
    elif plant == "float-run-count":
        run["authorization"]["runCount"] = 27.0
    elif plant == "integer-one-shot":
        run["authorization"]["oneShot"] = 1
    elif plant == "float-cleanup-reserve":
        run["authorization"]["cleanupReserveSeconds"] = 300.0
    with pytest.raises(runtime.GateError):
        runtime.validate_gate_run(
            run, bindings, plan, plan_sha, readiness_sha, now=NOW,
        )


def test_cell_contracts_preserve_all_27_cells_and_separate_claim_windows(
    tmp_path: Path, bindings,
) -> None:
    package = _package(tmp_path, bindings)
    contracts = [runtime.build_cell_contract(package, cell) for cell in bindings.cells]
    assert [row["runId"] for row in contracts] == list(bindings.run_ids)
    assert all(row["attemptPolicy"] == {
        "attempt": 1,
        "startedBeforeFirstExternalMutation": True,
        "retryAllowed": False,
        "substitutionAllowed": False,
        "rerandomizationAllowed": False,
    } for row in contracts)
    cost = [row for row in contracts if row["window"]["analysisKind"] == "cost"]
    effect = [row for row in contracts if row["window"]["analysisKind"] == "effect"]
    assert len(cost) == 9 and len(effect) == 18
    assert all("resources.json" in row["requiredArtifacts"] for row in cost)
    assert all("intervention.json" not in row["requiredArtifacts"] for row in cost)
    assert all("intervention.json" in row["requiredArtifacts"] for row in effect)
    assert all("resources.json" not in row["requiredArtifacts"] for row in effect)
    assert all(row["pathGroundTruth"]["crossTraceAssemblyAllowed"] is False for row in contracts)
    assert all(row["pathGroundTruth"]["executedDenominatorSource"] == "app-witness.jsonl"
               for row in contracts)
    assert all(row["pathGroundTruth"]["nativeEventsCarryWorkloadTokens"] is False
               for row in contracts)
    assert all("native-token-correlation.json" in row["requiredArtifacts"]
               for row in contracts)
    assert all("native-token-correlation-extraction.json" in row["requiredArtifacts"]
               for row in contracts)
    assert all("service-log-capture.json" in row["requiredArtifacts"]
               for row in contracts)
    assert all(row["pathGroundTruth"]["parameterLoggingRequirement"]
               == "LOG_PARAMETERS-absent-or-false" for row in contracts)
    assert all(row["window"]["warmupSeconds"] == 120 for row in contracts)
    assert all(row["window"]["measurementSeconds"] == 600 for row in contracts)
    assert all(row["workload"]["journeysPerSecond"] == 0.15 for row in contracts)
    assert all(row["workload"]["concurrency"] == 8 for row in contracts)
    assert all(row["workload"]["offeredJourneys"] == 90 for row in contracts)
    assert all(row["faultGroundTruth"]["faultOnsetSeconds"] == 180 for row in effect)
    assert all(row["faultGroundTruth"]["holdSeconds"] == 150 for row in effect)


def test_diagnostic_240_30_fault_timing_cannot_enter_a_candidate_cell_contract(
    tmp_path: Path, bindings,
) -> None:
    package = _package(tmp_path, bindings)
    package.bindings.descriptor["timing"]["faultOnsetSeconds"] = 240
    package.bindings.descriptor["timing"]["interventionHoldSeconds"] = 30
    effect = next(
        cell for cell in package.bindings.cells
        if cell["runKey"]["regime"] == "auth-freeze-effect"
    )
    with pytest.raises(runtime.GateError, match="timing"):
        runtime.build_cell_contract(package, effect)


@pytest.mark.parametrize("field", ("block", "attempt"))
def test_campaign_manifest_bool_identity_cannot_alias_integer_cell_identity(
    bindings, field: str,
) -> None:
    campaign_path = bindings.root / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    campaign["runs"][0][field] = True
    _write(campaign_path, campaign)
    with pytest.raises(runtime.GateError, match="campaign cell order, identity"):
        runtime.inspect_campaign(bindings.root, FRAMEWORK_COMMIT)


def test_campaign_manifest_float_run_count_does_not_equal_integer_scope(bindings) -> None:
    campaign_path = bindings.root / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    campaign["runCount"] = 27.0
    _write(campaign_path, campaign)
    with pytest.raises(runtime.GateError, match="exactly 27"):
        runtime.inspect_campaign(bindings.root, FRAMEWORK_COMMIT)


def test_campaign_manifest_boolean_schema_does_not_equal_version_one(bindings) -> None:
    campaign_path = bindings.root / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    campaign["schemaVersion"] = True
    _write(campaign_path, campaign)
    with pytest.raises(runtime.GateError, match="bindings"):
        runtime.inspect_campaign(bindings.root, FRAMEWORK_COMMIT)


@pytest.mark.parametrize("field", ("block", "attempt"))
def test_cell_contract_bool_identity_cannot_alias_integer_schedule(
    tmp_path: Path, bindings, field: str,
) -> None:
    package = _package(tmp_path, bindings)
    cell = copy.deepcopy(bindings.cells[0])
    cell["runKey"][field] = True
    with pytest.raises(runtime.GateError, match="immutable compiled schedule"):
        runtime.build_cell_contract(package, cell)


@pytest.mark.parametrize(
    "field,value",
    (("warmupSeconds", 120.0), ("faultOnsetSeconds", 180.0)),
)
def test_numeric_timing_scope_requires_exact_integer_type(
    tmp_path: Path, bindings, field: str, value: float,
) -> None:
    package = _package(tmp_path, bindings)
    package.bindings.descriptor["timing"][field] = value
    with pytest.raises(runtime.GateError, match="timing"):
        runtime.build_cell_contract(package, bindings.cells[0])


class FakeTransport:
    """A deliberately tempting fake that must never be called."""

    def __init__(self, capability: dict):
        self.capability = copy.deepcopy(capability)
        self.describe_calls = 0
        self.execute_calls = 0

    def describe(self):
        self.describe_calls += 1
        return copy.deepcopy(self.capability)

    def execute(self, contract, root: Path):
        del contract, root
        self.execute_calls += 1
        raise AssertionError("construction-only adapter crossed the fake transport")


def test_fake_transport_attempting_valid_is_blocked_before_any_injected_call(
    tmp_path: Path, bindings,
) -> None:
    package = _package(tmp_path, bindings)
    transport = FakeTransport(package.readiness["transport"])
    factory_calls = []
    adapter = runtime.CandidateCellAdapter(
        package,
        transport,
        lambda *values: factory_calls.append(values),
        clock=lambda: NOW,
    )
    artifacts = tmp_path / "never-launched"
    artifacts.mkdir()
    with pytest.raises(runtime.GateError, match="construction blocked"):
        adapter(copy.deepcopy(bindings.cells[0]), artifacts)
    assert transport.describe_calls == 0
    assert transport.execute_calls == 0
    assert factory_calls == []
    assert list(artifacts.iterdir()) == []


def _closed_manifest(root: Path, required_artifacts: list[str]) -> None:
    for name in required_artifacts:
        if name != "content-manifest.json":
            (root / name).write_bytes(f"immutable fixture for {name}\n".encode())
    rows = []
    for name in sorted(set(required_artifacts) - {"content-manifest.json"}):
        payload = (root / name).read_bytes()
        rows.append({
            "path": name,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
    _write(root / "content-manifest.json", {
        "schemaVersion": 1,
        "algorithm": "sha256",
        "files": rows,
    })


def _cost_required() -> list[str]:
    return sorted((*runtime.COMMON_ARTIFACTS, "resources.json"))


@pytest.mark.parametrize(
    "plant",
    (
        "trivial-manifest", "boolean-schema", "missing", "extra", "tampered",
        "symlink", "hardlinked-artifact", "hardlinked-manifest",
    ),
)
def test_closed_content_manifest_watches_each_planted_artifact_defect(
    tmp_path: Path, plant: str,
) -> None:
    root = tmp_path / plant
    root.mkdir()
    required = _cost_required()
    _closed_manifest(root, required)
    victim = root / "receipt.json"
    if plant == "trivial-manifest":
        _write(root / "content-manifest.json", {"runId": "self-declared", "complete": True})
    elif plant == "boolean-schema":
        manifest = json.loads((root / "content-manifest.json").read_text())
        manifest["schemaVersion"] = True
        _write(root / "content-manifest.json", manifest)
    elif plant == "missing":
        victim.unlink()
    elif plant == "extra":
        (root / "unreviewed-extra.txt").write_text("extra\n")
    elif plant == "tampered":
        victim.write_bytes(victim.read_bytes() + b"tampered\n")
    elif plant == "symlink":
        outside = tmp_path / "outside.json"
        outside.write_text("outside\n")
        victim.unlink()
        victim.symlink_to(outside)
    elif plant == "hardlinked-artifact":
        os.link(victim, tmp_path / "receipt-hardlink.json")
    elif plant == "hardlinked-manifest":
        os.link(
            root / "content-manifest.json",
            tmp_path / "manifest-hardlink.json",
        )
    with pytest.raises(runtime.GateError):
        runtime._validate_content_manifest(root, required)


def test_closed_content_manifest_recomputes_exact_sizes_and_hashes(tmp_path: Path) -> None:
    root = tmp_path / "complete"
    root.mkdir()
    required = _cost_required()
    _closed_manifest(root, required)
    snapshot = runtime._validate_content_manifest(root, required)
    assert set(snapshot.artifact_sha256) == set(required) - {"content-manifest.json"}
    assert snapshot.manifest_sha256 == hashlib.sha256(
        (root / "content-manifest.json").read_bytes()
    ).hexdigest()


def _nominal_valid_outcome(contract: dict, digest: str = "0" * 64):
    return runtime.TransportOutcome(
        run_id=contract["runId"],
        run_key=copy.deepcopy(contract["runKey"]),
        state="valid",
        safe_to_continue=True,
        evidence_sha256=digest,
        candidate_validation_sha256=digest,
        fault_ground_truth_sha256=None,
        path_ground_truth_sha256=digest,
        native_token_correlation_sha256=digest,
        native_token_extraction_sha256=digest,
        service_log_capture_sha256=digest,
        posture_proof_sha256=digest,
        queue_proof_sha256=digest,
        resource_evidence_sha256=digest,
        cleanup_proof_sha256=digest,
        outer_lease_held=True,
        deadline_controller_settled=True,
        owned_resources_clean=True,
    )


@pytest.mark.parametrize("field", ("block", "attempt"))
def test_outcome_bool_identity_cannot_alias_integer_contract(
    tmp_path: Path, bindings, field: str,
) -> None:
    package = _package(tmp_path, bindings)
    contract = runtime.build_cell_contract(package, bindings.cells[0])
    outcome = _nominal_valid_outcome(contract)
    run_key = copy.deepcopy(outcome.run_key)
    run_key[field] = True
    outcome = runtime.TransportOutcome(**{**outcome.__dict__, "run_key": run_key})
    with pytest.raises(runtime.GateError, match="identity"):
        runtime.CandidateCellAdapter._validate_outcome(contract, tmp_path, outcome)


def test_outcome_validator_actually_invokes_closed_manifest_checker(
    tmp_path: Path, bindings, monkeypatch,
) -> None:
    package = _package(tmp_path, bindings)
    contract = runtime.build_cell_contract(package, bindings.cells[0])

    def watched(*_args, **_kwargs):
        raise runtime.GateError("watched planted manifest defect")

    monkeypatch.setattr(runtime, "_validate_content_manifest", watched)
    with pytest.raises(runtime.GateError, match="watched planted manifest defect"):
        runtime.CandidateCellAdapter._validate_outcome(
            contract, tmp_path, _nominal_valid_outcome(contract),
        )


def test_even_fully_reconciled_local_outcome_hits_missing_terminal_ceiling(
    tmp_path: Path, bindings, monkeypatch,
) -> None:
    package = _package(tmp_path, bindings)
    contract = runtime.build_cell_contract(package, bindings.cells[0])
    digest = "1" * 64
    snapshot = runtime.ContentManifestSnapshot(
        manifest_sha256=digest,
        artifact_sha256={name: digest for name in contract["requiredArtifacts"]
                         if name != "content-manifest.json"},
        artifact_bytes={name: 1 for name in contract["requiredArtifacts"]
                        if name != "content-manifest.json"},
    )
    report = {"verdict": "pass"}

    class LocalOnlyValidator:
        @staticmethod
        def validate_run(_root, expected=None):
            assert expected == contract["runKey"]
            return report

    monkeypatch.setattr(runtime, "_validate_content_manifest", lambda *_: snapshot)
    monkeypatch.setattr(runtime, "_artifact_sha", lambda *_: digest)
    monkeypatch.setattr(runtime, "_json_file", lambda *_: report)
    monkeypatch.setattr(runtime, "_candidate_validator_module", LocalOnlyValidator)
    monkeypatch.setattr(runtime, "_candidate_terminal_validator_module", lambda *_: None)
    with pytest.raises(runtime.GateError, match="construction blocked"):
        runtime.CandidateCellAdapter._validate_outcome(
            contract, tmp_path, _nominal_valid_outcome(contract, digest),
        )


def test_fabricated_seam_observations_cannot_establish_runtime_readiness(
    tmp_path: Path, bindings,
) -> None:
    readiness = _readiness(bindings, tmp_path)
    assert all(
        row["observations"] == {"fixture": True}
        for row in (
            json.loads((tmp_path / readiness["artifactRoot"] / seam["evidencePath"]).read_text())
            for seam in readiness["seams"].values()
        )
    )
    with pytest.raises(runtime.GateError, match="self-declared"):
        runtime.validate_readiness(readiness, bindings, readiness_parent=tmp_path)


def test_file_authorization_path_invokes_and_stops_at_readiness_replay_ceiling(
    tmp_path: Path, bindings,
) -> None:
    plan = _gate_plan(bindings)
    readiness = _readiness(bindings, tmp_path)
    run = _gate_run(bindings, plan, readiness)
    plan_path = tmp_path / "gate-plan.json"
    readiness_path = tmp_path / "readiness.json"
    run_path = tmp_path / "gate-run.json"
    for path, document in (
        (plan_path, plan), (readiness_path, readiness), (run_path, run),
    ):
        _write(path, document)
    with pytest.raises(runtime.GateError, match="self-declared"):
        runtime.authorize_from_files(
            bindings.root,
            plan_path,
            readiness_path,
            run_path,
            framework_commit=FRAMEWORK_COMMIT,
            clock=lambda: NOW,
        )


@pytest.mark.parametrize(
    "plant",
    (
        "missing-plan", "missing-readiness", "missing-run",
        "invalid-plan", "invalid-readiness", "invalid-run",
        "mismatched-plan", "mismatched-readiness", "mismatched-run",
    ),
)
def test_invalid_missing_or_mismatched_local_gate_inputs_never_invoke_caller_clock(
    tmp_path: Path, bindings, plant: str,
) -> None:
    plan_path = tmp_path / "gate-plan.json"
    readiness_path = tmp_path / "readiness.json"
    run_path = tmp_path / "gate-run.json"
    documents = {
        "plan": _gate_plan(bindings),
        "readiness": _readiness(bindings, tmp_path),
    }
    documents["run"] = _gate_run(
        bindings, documents["plan"], documents["readiness"],
    )
    if plant == "mismatched-plan":
        documents["plan"]["decision"] = "deny"
    elif plant == "mismatched-readiness":
        documents["readiness"]["target"] = "unreviewed-target"
    elif plant == "mismatched-run":
        documents["run"]["decision"] = "deny"
    paths = {"plan": plan_path, "readiness": readiness_path, "run": run_path}
    for name, path in paths.items():
        if plant == f"missing-{name}":
            continue
        if plant == f"invalid-{name}":
            path.write_text("{not-json\n")
        else:
            _write(path, documents[name])

    clock_calls: list[str] = []

    def planted_clock() -> datetime:
        clock_calls.append("clock")
        raise AssertionError("caller clock ran before local replay failed")

    with pytest.raises(runtime.GateError):
        runtime.authorize_from_files(
            bindings.root,
            plan_path,
            readiness_path,
            run_path,
            framework_commit=FRAMEWORK_COMMIT,
            clock=planted_clock,
        )
    assert clock_calls == []
