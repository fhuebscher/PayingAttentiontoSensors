from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from obsplacement.configuration_oracle import (
    OracleContractError,
    enumerate_space,
    evaluate_registry,
)
from obsplacement.selection import compile_selection


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "research" / "exact-configuration-spaces.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def report() -> dict:
    return evaluate_registry(load(REGISTRY), ROOT)


def by_space(document: dict) -> dict[str, dict]:
    return {space["spaceId"]: space for space in document["spaces"]}


def test_exact_spaces_have_golden_counts_and_configuration_digests() -> None:
    spaces = by_space(report())
    tea = spaces["teastore-kieker-small-v1"]
    boutique = spaces["online-boutique-v0.10.6-small-v1"]

    assert tea["candidateAssignmentCount"] == tea["feasibleConfigurationCount"] == 32
    assert boutique["candidateAssignmentCount"] == boutique["feasibleConfigurationCount"] == 8
    assert tea["configurationDigest"] == (
        "a28e9f485a3aa5292fe50c3aa9cf844b69972dcb7bd3fb68b24c015823935336"
    )
    assert boutique["configurationDigest"] == (
        "f904bb3ca8b610377e7ba8668419758c9c8d80c735b157063c06261373d059f8"
    )
    assert tea["exactness"] == {
        "kind": "exhaustive-finite-structural-enumeration",
        "compatibilityFieldNote": (
            "feasibleConfigurationCount is a legacy field name bounded to "
            "catalog-admissible structural assignments; it does not assert "
            "operational deployability."
        ),
        "catalogDigest": "062fc23b515fd7914f5169b25b6f85c9e2cae0b24afa20327c53866a86f43688",
        "runtimeOutcomesUsed": False,
        "noiseEliminated": False,
        "globalDeploymentOptimalityClaimed": False,
    }
    assert tea["feasibleConfigurationCount"] == 32
    assert "catalog-admissible" in tea["exactness"]["compatibilityFieldNote"]


def test_fixed_and_unsupported_groups_are_not_silently_decision_variables() -> None:
    spaces = by_space(report())
    for configuration in spaces["teastore-kieker-small-v1"]["configurations"]:
        assert configuration["assignment"]["manual:registry-client"] is True
        assert "manual:registry-client" not in configuration["decisionSet"]
    for configuration in spaces["online-boutique-v0.10.6-small-v1"]["configurations"]:
        assert configuration["assignment"]["cart-no-stock-tracing"] is False
        assert configuration["assignment"]["ad-no-stock-tracing"] is False
        assert "cart-no-stock-tracing" not in configuration["decisionSet"]
        assert "ad-no-stock-tracing" not in configuration["decisionSet"]


def test_minimum_structural_sets_match_the_existing_dependency_compiler() -> None:
    registry = load(REGISTRY)
    tea_spec = next(space for space in registry["spaces"] if space["module"] == "teastore")
    tea_catalog = load(ROOT / tea_spec["catalogBinding"]["path"])
    tea_goals = [load(ROOT / binding["path"]) for binding in tea_spec["goalBindings"]]
    tea_report = enumerate_space(tea_spec, tea_catalog, tea_goals)

    goal = next(item for item in tea_goals if item["id"] == "teastore-auth-persistence-fault-v1")
    compiled = compile_selection(tea_catalog, goal["evidenceRequirements"]["required"])
    minimum_id = tea_report["goals"][goal["id"]]["minimumStructuralConfigurationIds"]
    assert minimum_id == ["cfg-10100"]
    minimum = next(row for row in tea_report["configurations"] if row["id"] == minimum_id[0])
    assert minimum["activeGroups"] == compiled["selectedActivationGroups"]
    assert minimum["declaredEvidence"] == compiled["expectedLogicalSensors"]

    boutique = by_space(report())["online-boutique-v0.10.6-small-v1"]
    assert boutique["goals"]["online-boutique-product-catalog-subpath-v1"][
        "minimumStructuralConfigurationIds"
    ] == ["cfg-110"]
    assert boutique["goals"]["online-boutique-currency-subpath-v1"][
        "minimumStructuralConfigurationIds"
    ] == ["cfg-101"]


def test_diminishing_returns_hooks_separate_coverage_from_complementarity() -> None:
    for space in report()["spaces"]:
        for goal in space["goals"].values():
            diagnostics = {
                row["objective"]: row for row in goal["diminishingReturnsDiagnostics"]
            }
            coverage = diagnostics["requiredEvidenceCoverage"]
            threshold = diagnostics["structuralRequiredSetCovered"]
            assert coverage["classification"] == (
                "no-violation-in-enumerated-structural-domain"
            )
            assert coverage["violationCount"] == 0
            assert threshold["classification"] == (
                "violation-in-enumerated-structural-domain"
            )
            assert threshold["violationCount"] > 0
            assert threshold["counterexamples"]
            assert "no runtime" in threshold["claimBoundary"]


def test_runtime_relations_remain_unevaluated_by_the_static_oracle() -> None:
    spaces = by_space(report())
    goal_id = "online-boutique-product-catalog-subpath-v1"
    selected = next(
        row for row in spaces["online-boutique-v0.10.6-small-v1"]["configurations"]
        if row["id"] == "cfg-110"
    )
    assert selected["goals"][goal_id]["structuralRequiredSetCovered"] is True
    assert selected["goals"][goal_id]["runtimeRelationsUnevaluated"] == [
        "frontend->productcatalogservice:ListProducts"
    ]


def test_digest_or_catalog_projection_tampering_fails_closed() -> None:
    registry = load(REGISTRY)
    stale = copy.deepcopy(registry)
    stale["spaces"][0]["catalogBinding"]["sha256"] = "0" * 64
    with pytest.raises(OracleContractError, match="digest mismatch"):
        evaluate_registry(stale, ROOT)

    spec = copy.deepcopy(registry["spaces"][0])
    catalog = load(ROOT / spec["catalogBinding"]["path"])
    goals = [load(ROOT / binding["path"]) for binding in spec["goalBindings"]]
    spec["evidenceByGroup"]["aspectj:auth"] = ["operation:persistence"]
    with pytest.raises(OracleContractError, match="golden projection"):
        enumerate_space(spec, catalog, goals)


def test_unbound_catalog_group_or_missing_dependency_fails_closed() -> None:
    registry = load(REGISTRY)
    spec = copy.deepcopy(registry["spaces"][0])
    catalog = load(ROOT / spec["catalogBinding"]["path"])
    goals = [load(ROOT / binding["path"]) for binding in spec["goalBindings"]]
    spec["fixedAssignments"] = {}
    with pytest.raises(OracleContractError, match="variables differ from catalog"):
        enumerate_space(spec, catalog, goals)

    spec = copy.deepcopy(registry["spaces"][0])
    spec["constraints"] = spec["constraints"][:-1]
    with pytest.raises(OracleContractError, match="requires constraints differ"):
        enumerate_space(spec, catalog, goals)


def test_runtime_oracle_enforces_registry_and_bound_goal_schemas(tmp_path: Path) -> None:
    registry = load(REGISTRY)
    forged_registry = copy.deepcopy(registry)
    forged_registry["unexpected"] = "schema bypass"
    with pytest.raises(OracleContractError, match="schema validation failed"):
        evaluate_registry(forged_registry, ROOT)

    # Rebind one invalid goal in a temporary repository-shaped root. Updating
    # the digest proves that byte binding cannot substitute for schema binding.
    reduced = copy.deepcopy(registry)
    reduced["spaces"] = [reduced["spaces"][0]]
    space = reduced["spaces"][0]
    for name in (
        "finite-configuration-space.schema.json",
        "optimization-goal.schema.json",
    ):
        destination = tmp_path / "contracts" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / "contracts" / name).read_bytes())
    catalog_path = tmp_path / space["catalogBinding"]["path"]
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_bytes((ROOT / space["catalogBinding"]["path"]).read_bytes())
    for index, binding in enumerate(space["goalBindings"]):
        goal = load(ROOT / binding["path"])
        if index == 0:
            goal["unexpected"] = "digest-bound but schema-invalid"
        raw = json.dumps(goal, indent=2).encode("utf-8") + b"\n"
        goal_path = tmp_path / binding["path"]
        goal_path.parent.mkdir(parents=True, exist_ok=True)
        goal_path.write_bytes(raw)
        binding["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(OracleContractError, match="schema validation failed"):
        evaluate_registry(reduced, tmp_path)
