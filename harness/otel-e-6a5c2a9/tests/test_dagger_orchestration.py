from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from obsplacement.execution.orchestration import (
    ContractError,
    PHASE_ORDER,
    compare_plans,
    load_repo_json,
    render_plan,
    validate_plan,
)


ROOT = Path(__file__).resolve().parents[1]
BACKENDS = {
    path.stem: json.loads(path.read_text())
    for path in sorted((ROOT / "pipelines/executors").glob("*.json"))
}
COMMON_CAPABILITIES = [
    "cancel-join",
    "compose",
    "immutable-inputs",
    "lifecycle-v1",
    "per-phase-receipts",
    "scoped-cleanup",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_plan(tmp_path: Path, backend_name: str) -> tuple[dict, dict, Path]:
    repo = tmp_path
    (repo / "contracts").mkdir(parents=True)
    (repo / "modules/example/execution").mkdir(parents=True)
    (repo / "campaigns").mkdir()
    (repo / "launchers").mkdir()
    schema = repo / "contracts/execution-receipt.schema.json"
    adapter = repo / "modules/example/execution/campaign.py"
    campaign = repo / "campaigns/smoke.json"
    launcher = repo / f"launchers/{backend_name}.sh"
    schema.write_text('{"schemaVersion":1}\n')
    adapter.write_text("# adapter boundary\n")
    campaign.write_text('{"durationSeconds":30}\n')
    launcher.write_text("#!/bin/sh\nexit 0\n")

    phases = list(PHASE_ORDER)
    invocation_phases = [phases[:3], phases[3:10], phases[10:]]
    backend = copy.deepcopy(BACKENDS[backend_name])
    ownership_kind = backend["cleanupContract"]["allowedOwnershipKinds"][0]
    plan = {
        "schemaVersion": 1,
        "runId": "run-001",
        "module": "example-module",
        "backend": backend["backend"],
        "target": f"target-{backend_name}",
        "source": {
            "frameworkCommit": "a" * 40,
            "sutCommit": "b" * 40,
            "dirty": False,
            "patchSha256": None,
        },
        "requested": {
            "campaign": "smoke",
            "goal": "latency-budget",
            "postures": ["source-off", "selected"],
        },
        "requiredCapabilities": list(COMMON_CAPABILITIES),
        "immutableInputs": {
            "experiment": [
                {"role": "campaign", "path": "campaigns/smoke.json", "sha256": digest(campaign)},
                {
                    "role": "module-adapter",
                    "path": "modules/example/execution/campaign.py",
                    "sha256": digest(adapter),
                },
            ],
            "executor": [
                {"role": "launcher", "path": f"launchers/{backend_name}.sh", "sha256": digest(launcher)}
            ],
        },
        "adapter": {
            "entrypoint": {
                "path": "modules/example/execution/campaign.py",
                "sha256": digest(adapter),
            },
            "supportedPostures": ["source-off", "selected", "full"],
            "capabilities": list(COMMON_CAPABILITIES),
            "invocations": [
                {
                    "id": f"stage-{index}",
                    "phases": covered,
                    "argv": ["python3", "modules/example/execution/campaign.py", f"stage-{index}"],
                    "receiptPhases": covered,
                }
                for index, covered in enumerate(invocation_phases)
            ],
        },
        "receiptContract": {
            "schemaPath": "contracts/execution-receipt.schema.json",
            "schemaSha256": digest(schema),
            "perPhase": True,
            "immutableFinalManifest": True,
            "outputRoot": ".local/evidence/run-001",
        },
        "cleanup": {
            "ownership": [{"kind": ownership_kind, "id": f"owned-{backend_name}-run-001"}],
            "allowWholeHost": False,
            "cancelJoin": {"mode": "adapter-internal", "argv": [], "evidenceRequired": True},
            "evidencePath": ".local/evidence/run-001/cleanup.json",
        },
    }
    return plan, backend, repo


def test_dagger_is_explicitly_pinned_and_validation_only() -> None:
    config = json.loads((ROOT / "dagger.json").read_text())
    assert config == {
        "name": "obsplacement",
        "engineVersion": "v0.21.7",
        "sdk": {"source": "python"},
        "source": "dagger",
    }
    pyproject = (ROOT / "dagger/pyproject.toml").read_text()
    assert 'dagger-io==0.21.7' in pyproject
    source = (ROOT / "dagger/src/obsplacement/main.py").read_text().lower()
    assert all(name not in source for name in ("teastore", "otel-demo", "online-boutique", "hotel-reservation"))
    assert "with_exec" in source
    assert "launch" not in source and "deploy" not in source


@pytest.mark.parametrize("backend_name", sorted(BACKENDS))
def test_backends_share_phase_receipt_and_delegation_contract(backend_name: str) -> None:
    backend = BACKENDS[backend_name]
    assert backend["phaseContract"] == list(PHASE_ORDER)
    assert backend["receiptContract"] == {
        "schemaPath": "contracts/execution-receipt.schema.json",
        "perPhase": True,
        "immutableFinalManifest": True,
    }
    assert backend["delegation"] == {
        "adapterCommands": True,
        "argvOnly": True,
        "sutBranches": False,
    }
    assert backend["cleanupContract"]["allowWholeHost"] is False
    assert backend["cleanupContract"]["joinBeforeTeardown"] is True


@pytest.mark.parametrize("backend_name", sorted(BACKENDS))
def test_each_backend_validates_and_renders_same_lifecycle(tmp_path: Path, backend_name: str) -> None:
    plan, backend, repo = fixture_plan(tmp_path, backend_name)
    normalized = validate_plan(plan, backend, repo)
    rendered = render_plan(plan, backend, repo)
    assert normalized["phaseContract"] == list(PHASE_ORDER)
    covered = [phase for step in rendered["steps"] if step["kind"] == "adapter-invocation" for phase in step["phases"]]
    assert covered == list(PHASE_ORDER)
    teardown_index = next(i for i, step in enumerate(rendered["steps"]) if "teardown" in step.get("phases", []))
    assert rendered["steps"][teardown_index - 1]["kind"] == "cancel-join-boundary"
    assert rendered["mode"] == "render-only"


def test_tampered_immutable_input_fails_closed(tmp_path: Path) -> None:
    plan, backend, repo = fixture_plan(tmp_path, "local-compose")
    (repo / "campaigns/smoke.json").write_text('{"durationSeconds":31}\n')
    with pytest.raises(ContractError, match="sha256 mismatch"):
        validate_plan(plan, backend, repo)


def test_source_patch_posture_and_capabilities_fail_closed(tmp_path: Path) -> None:
    plan, backend, repo = fixture_plan(tmp_path, "local-compose")
    plan["source"]["dirty"] = True
    with pytest.raises(ContractError, match="dirty source"):
        validate_plan(plan, backend, repo)
    plan["source"]["patchSha256"] = "c" * 64
    plan["requested"]["postures"] = ["unsupported"]
    with pytest.raises(ContractError, match="does not support"):
        validate_plan(plan, backend, repo)
    plan["requested"]["postures"] = ["selected"]
    plan["requiredCapabilities"].append("missing-capability")
    with pytest.raises(ContractError, match="unsupported required capabilities"):
        validate_plan(plan, backend, repo)


@pytest.mark.parametrize("identity", ["*", "/", "all", "host", "run/../other", "run//other"])
def test_broad_cleanup_ownership_is_rejected(tmp_path: Path, identity: str) -> None:
    plan, backend, repo = fixture_plan(tmp_path, "ssh-compose")
    plan["cleanup"]["ownership"][0]["id"] = identity
    with pytest.raises(ContractError, match="exact executor-owned resource"):
        validate_plan(plan, backend, repo)


def test_cli_json_inputs_cannot_escape_or_symlink_outside_repo(tmp_path: Path) -> None:
    inside = tmp_path / "plan.json"
    inside.write_text('{"schemaVersion":1}\n')
    assert load_repo_json(tmp_path, Path("plan.json"), where="plan")["schemaVersion"] == 1
    with pytest.raises(ContractError, match="repository-relative"):
        load_repo_json(tmp_path, Path("../plan.json"), where="plan")
    outside = tmp_path.parent / "outside-plan.json"
    outside.write_text('{}\n')
    link = tmp_path / "link.json"
    link.symlink_to(outside)
    with pytest.raises(ContractError, match="inside the repository"):
        load_repo_json(tmp_path, Path("link.json"), where="plan")


def test_cleanup_needs_join_evidence_and_local_output(tmp_path: Path) -> None:
    plan, backend, repo = fixture_plan(tmp_path, "aws-cloudformation")
    plan["cleanup"]["cancelJoin"]["evidenceRequired"] = False
    with pytest.raises(ContractError, match="evidence is required"):
        validate_plan(plan, backend, repo)
    plan["cleanup"]["cancelJoin"]["evidenceRequired"] = True
    plan["receiptContract"]["outputRoot"] = "results/generated/run-001"
    with pytest.raises(ContractError, match="under ignored .local"):
        validate_plan(plan, backend, repo)


def test_backend_equivalence_uses_experimental_inputs_not_transport(tmp_path: Path) -> None:
    local, local_backend, repo = fixture_plan(tmp_path, "local-compose")
    # Add a second backend launcher into the same synthetic repository.
    remote_launcher = repo / "launchers/ssh-compose.sh"
    remote_launcher.write_text("#!/bin/sh\nexit 0\n")
    remote = copy.deepcopy(local)
    remote["backend"] = "ssh-compose"
    remote["target"] = "remote-host"
    remote["immutableInputs"]["executor"] = [{
        "role": "launcher", "path": "launchers/ssh-compose.sh", "sha256": digest(remote_launcher)
    }]
    remote["cleanup"]["ownership"] = [{"kind": "compose-project", "id": "remote-project-001"}]
    result = compare_plans(local, local_backend, remote, BACKENDS["ssh-compose"], repo)
    assert result["equivalent"] is True
    assert "does not prove" in result["claimBoundary"]

    second_campaign = repo / "campaigns/other.json"
    second_campaign.write_text('{"durationSeconds":60}\n')
    remote["immutableInputs"]["experiment"][0] = {
        "role": "campaign", "path": "campaigns/other.json", "sha256": digest(second_campaign)
    }
    assert compare_plans(local, local_backend, remote, BACKENDS["ssh-compose"], repo)["equivalent"] is False


def test_shell_command_strings_and_incomplete_phase_receipts_are_rejected(tmp_path: Path) -> None:
    plan, backend, repo = fixture_plan(tmp_path, "local-compose")
    plan["adapter"]["invocations"][0]["argv"] = ["bash", "-c", "do something"]
    with pytest.raises(ContractError, match="argv"):
        validate_plan(plan, backend, repo)
    plan, backend, repo = fixture_plan(tmp_path / "second", "local-compose")
    plan["adapter"]["invocations"][1]["receiptPhases"] = ["materialize"]
    with pytest.raises(ContractError, match="one receipt"):
        validate_plan(plan, backend, repo)
