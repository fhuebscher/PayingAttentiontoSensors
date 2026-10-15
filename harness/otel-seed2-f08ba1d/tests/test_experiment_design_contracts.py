from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[1]


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def assert_binding(binding: dict) -> None:
    candidate = ROOT / binding["path"]
    path = candidate.resolve()
    assert path == ROOT or ROOT in path.parents, binding
    assert candidate.is_file() and not candidate.is_symlink(), binding
    assert hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"], binding


SCHEMA_NAMES = {
    "probe-design.schema.json",
    "context-regime.schema.json",
    "knowledge-policy.schema.json",
    "optimization-goal.schema.json",
    "finite-configuration-space.schema.json",
}


def validate(name: str, document: dict) -> None:
    schema = load(f"contracts/{name}")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(document)


def assert_probe_references(registry: dict) -> None:
    seen: set[str] = set()
    for design in registry["designs"]:
        assert design["id"] not in seen
        seen.add(design["id"])
        assert len(design["sourceBindings"]) == 1
        binding = design["sourceBindings"][0]
        assert_binding(binding)
        catalog = load(binding["path"])
        groups = {row["id"] for row in catalog["activationGroups"]}
        sensors = {row["id"]: row["activationGroup"] for row in catalog["logicalSensors"]}
        assert set(design["activationGroups"]) <= groups
        assert set(design["logicalEvidence"]) <= set(sensors)
        assert all(
            sensors[evidence] in design["activationGroups"]
            for evidence in design["logicalEvidence"]
        )


def assert_context_references(registry: dict) -> None:
    contexts = {item["id"]: item for item in registry["contexts"]}
    assert len(contexts) == len(registry["contexts"])
    regime_ids = {item["id"] for item in registry["regimes"]}
    assert len(regime_ids) == len(registry["regimes"])
    for regime in registry["regimes"]:
        assert regime["contextId"] in contexts


def test_contract_schemas_and_instances_are_local_and_parseable() -> None:
    for name in SCHEMA_NAMES:
        schema = load(f"contracts/{name}")
        assert schema["$id"].endswith(f"/{name}")
        assert schema["additionalProperties"] is False
        Draft202012Validator.check_schema(schema)

    instances = [
        load("research/probe-designs.json"),
        load("research/context-regimes.json"),
        load("research/knowledge-policy.json"),
        load("research/exact-configuration-spaces.json"),
    ]
    for document in instances:
        schema_name = document["$schema"].rsplit("/", 1)[-1]
        assert schema_name in SCHEMA_NAMES
        validate(schema_name, document)

    goal_registry = load("research/exact-configuration-spaces.json")
    for space in goal_registry["spaces"]:
        for binding in space["goalBindings"]:
            validate("optimization-goal.schema.json", load(binding["path"]))


def test_probe_designs_keep_mechanisms_and_control_purity_explicit() -> None:
    registry = load("research/probe-designs.json")
    designs = {item["id"]: item for item in registry["designs"]}
    assert len(designs) == len(registry["designs"]) == 5
    assert {item["applicationFamily"] for item in designs.values()} == {
        "teastore", "online-boutique"
    }
    assert {item["mechanism"]["kind"] for item in designs.values()} == {
        "aspectj-kieker", "manual-propagation", "otel-go-sdk", "otel-node-sdk"
    }
    assert registry["status"] == "catalog-bound-source-inspection-method-draft"
    assert "do not bind upstream implementation source" in registry["claimBoundary"]
    manual = designs["teastore-manual-registry-propagation-v1"]
    woven = designs["teastore-aspectj-operation-execution-v1"]
    assert woven["placementLocus"] == "load-time-weave"
    assert "aop.xml loaded at service start" in woven["mechanism"]["implementation"]
    assert manual["settingDomain"]["controllability"] == "fixed-on"
    assert manual["controlPurity"]["sourceWorkOff"] == "unsupported"
    for design in designs.values():
        for binding in design["sourceBindings"]:
            assert_binding(binding)
    assert_probe_references(registry)


def test_contexts_do_not_pool_channels_or_held_out_regimes() -> None:
    registry = load("research/context-regimes.json")
    contexts = {item["id"]: item for item in registry["contexts"]}
    regimes = {item["id"]: item for item in registry["regimes"]}
    assert len(contexts) == 2
    assert registry["status"] == "source-inspection-method-draft"
    assert "does not itself prove" in registry["claimBoundary"]
    assert len({item["compatibilityKey"] for item in contexts.values()}) == 2
    assert "Orchestration" in registry["poolingPolicy"]
    assert regimes["teastore-full-journey-transfer-v1"]["heldOut"] is True
    assert regimes["online-boutique-currency-transfer-v1"]["heldOut"] is True
    assert regimes["online-boutique-productcatalog-exploration-v1"]["heldOut"] is False
    assert all(item["contextId"] in contexts for item in regimes.values())
    assert_context_references(registry)


def test_knowledge_policies_define_equal_budget_boundary_without_false_freeze() -> None:
    bundle = load("research/knowledge-policy.json")
    policies = {item["id"]: item for item in bundle["policies"]}
    assert set(policies) == {"K0", "K1", "K2", "K3", "K4"}
    assert bundle["status"] == "method-contract"
    assert bundle["sharedBudget"]["value"] is None
    assert bundle["freezeGate"]["unresolved"]
    assert policies["K4"]["selectionEligible"] is False
    assert policies["K4"]["scoringOnly"] is True
    assert all(item["abstentionAllowed"] for item in policies.values())
    assert "target family held out" in " ".join(policies["K1"]["allowedKnowledge"])


def test_exactly_two_frozen_goals_per_depth_family_are_catalog_bound() -> None:
    registry = load("research/exact-configuration-spaces.json")
    expected = {"teastore": 2, "online-boutique": 2}
    observed: dict[str, int] = {}
    context_ids = {row["id"] for row in load("research/context-regimes.json")["contexts"]}
    for space in registry["spaces"]:
        observed[space["module"]] = len(space["goalBindings"])
        assert_binding(space["catalogBinding"])
        for binding in space["goalBindings"]:
            assert_binding(binding)
            goal = load(binding["path"])
            assert goal["status"] == "frozen-for-structural-oracle"
            assert goal["operationalFreezeStatus"] == "open"
            assert "structural goal skeleton" in goal["claimBoundary"].lower()
            assert "freeze remains open" in goal["claimBoundary"].lower()
            assert goal["catalogBinding"] == space["catalogBinding"]
            assert set(goal["compatibleContextIds"]) <= context_ids
            assert goal["structuralObjectives"][1]["id"] == (
                "structural-required-set-covered"
            )
            assert "runtime" in goal["claimBoundary"].lower() or (
                "diagnostic" in goal["claimBoundary"].lower()
            )
    assert observed == expected


def test_draft_schemas_reject_status_drift_and_goal_freeze_overclaim() -> None:
    probe = load("research/probe-designs.json")
    probe["status"] = "design-freeze"
    with pytest.raises(ValidationError):
        validate("probe-design.schema.json", probe)

    context = load("research/context-regimes.json")
    context.pop("claimBoundary")
    with pytest.raises(ValidationError):
        validate("context-regime.schema.json", context)

    registry = load("research/exact-configuration-spaces.json")
    goal = load(registry["spaces"][0]["goalBindings"][0]["path"])
    goal["operationalFreezeStatus"] = "frozen"
    with pytest.raises(ValidationError):
        validate("optimization-goal.schema.json", goal)

    knowledge = load("research/knowledge-policy.json")
    knowledge["status"] = "preregistered"
    with pytest.raises(ValidationError):
        validate("knowledge-policy.schema.json", knowledge)
    knowledge["sharedBudget"]["value"] = 12
    knowledge["freezeGate"]["unresolved"] = []
    validate("knowledge-policy.schema.json", knowledge)

    duplicate_policy = load("research/knowledge-policy.json")
    duplicate_policy["policies"][1]["id"] = "K0"
    with pytest.raises(ValidationError):
        validate("knowledge-policy.schema.json", duplicate_policy)

    scoring_leak = load("research/knowledge-policy.json")
    scoring_leak["policies"][-1]["selectionEligible"] = True
    with pytest.raises(ValidationError):
        validate("knowledge-policy.schema.json", scoring_leak)


def test_referential_and_digest_tampering_fails_closed() -> None:
    probe = load("research/probe-designs.json")
    forged_group = copy.deepcopy(probe)
    forged_group["designs"][0]["activationGroups"][0] = "not-in-catalog"
    with pytest.raises(AssertionError):
        assert_probe_references(forged_group)

    forged_digest = copy.deepcopy(probe)
    forged_digest["designs"][0]["sourceBindings"][0]["sha256"] = "0" * 64
    with pytest.raises(AssertionError):
        assert_probe_references(forged_digest)

    context = load("research/context-regimes.json")
    forged_context = copy.deepcopy(context)
    forged_context["regimes"][0]["contextId"] = "missing-context"
    with pytest.raises(AssertionError):
        assert_context_references(forged_context)
