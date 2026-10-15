"""Exact structural enumeration for small, digest-bound activation catalogs.

"Exact" here means that every catalog-admissible Boolean structural assignment
is enumerated under the frozen catalog's declared constraints. The oracle does
not prove operational deployability, invent runtime evidence, remove measurement
noise, or claim an optimum outside the pinned structural model.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


class OracleContractError(ValueError):
    """Raised when a supposedly frozen oracle input is stale or ambiguous."""


def _schema_validator(root: Path, name: str) -> Draft202012Validator:
    path = (root / "contracts" / name).resolve()
    contracts = (root / "contracts").resolve()
    if contracts not in path.parents or not path.is_file() or path.is_symlink():
        raise OracleContractError(f"schema is not a regular repository contract: {name}")
    try:
        schema = json.loads(path.read_bytes())
        Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, SchemaError) as error:
        raise OracleContractError(f"invalid repository schema {name}: {error}") from error
    return Draft202012Validator(schema)


def _validate_schema_instance(
    root: Path,
    name: str,
    document: dict[str, Any],
    label: str,
) -> None:
    try:
        _schema_validator(root, name).validate(document)
    except ValidationError as error:
        location = ".".join(str(item) for item in error.absolute_path) or "<root>"
        raise OracleContractError(
            f"schema validation failed for {label} at {location}: {error.message}"
        ) from error


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bound_json(
    root: Path,
    binding: dict[str, Any],
    *,
    schema_name: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    path = (root / binding["path"]).resolve()
    if root != path and root not in path.parents:
        raise OracleContractError(f"binding escapes repository root: {binding['path']}")
    if not path.is_file() or path.is_symlink():
        raise OracleContractError(f"binding is not a regular repository file: {binding['path']}")
    raw = path.read_bytes()
    actual = _sha256_bytes(raw)
    if actual != binding["sha256"]:
        raise OracleContractError(
            f"digest mismatch for {binding['path']}: expected {binding['sha256']}, got {actual}"
        )
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise OracleContractError(f"invalid JSON for {binding['path']}: {error}") from error
    if not isinstance(document, dict):
        raise OracleContractError(f"bound document must be an object: {binding['path']}")
    if schema_name is not None:
        _validate_schema_instance(root, schema_name, document, binding["path"])
    if document.get("id") != binding["id"]:
        raise OracleContractError(
            f"id mismatch for {binding['path']}: expected {binding['id']!r}, "
            f"got {document.get('id')!r}"
        )
    return document


def _catalog_projection(catalog: dict[str, Any]) -> tuple[set[str], dict[str, list[str]], set[tuple[str, str]]]:
    groups = catalog.get("activationGroups")
    sensors = catalog.get("logicalSensors")
    if not isinstance(groups, list) or not isinstance(sensors, list):
        raise OracleContractError("catalog must declare activationGroups and logicalSensors")
    group_ids = [row.get("id") for row in groups]
    if any(not isinstance(item, str) or not item for item in group_ids):
        raise OracleContractError("catalog activation group ids must be non-empty strings")
    if len(group_ids) != len(set(group_ids)):
        raise OracleContractError("catalog contains duplicate activation groups")
    evidence_by_group = {group_id: [] for group_id in group_ids}
    for sensor in sensors:
        sensor_id, group_id = sensor.get("id"), sensor.get("activationGroup")
        if not isinstance(sensor_id, str) or group_id not in evidence_by_group:
            raise OracleContractError("logical sensor references an invalid activation group")
        evidence_by_group[group_id].append(sensor_id)
    for values in evidence_by_group.values():
        values.sort()
    requires = {
        (row["id"], dependency)
        for row in groups
        for dependency in row.get("requires", [])
    }
    if any(left not in evidence_by_group or right not in evidence_by_group for left, right in requires):
        raise OracleContractError("catalog dependency references an unknown group")
    return set(group_ids), evidence_by_group, requires


def _validate_space(
    space: dict[str, Any],
    catalog: dict[str, Any],
    goals: list[dict[str, Any]],
) -> None:
    groups, catalog_evidence, catalog_requires = _catalog_projection(catalog)
    decisions = space.get("decisionGroups")
    fixed = space.get("fixedAssignments")
    if not isinstance(decisions, list) or not decisions or len(decisions) != len(set(decisions)):
        raise OracleContractError(f"{space.get('id')}: decisionGroups must be unique and non-empty")
    if not isinstance(fixed, dict) or any(type(value) is not bool for value in fixed.values()):
        raise OracleContractError(f"{space.get('id')}: fixedAssignments must contain Booleans")
    if set(decisions) & set(fixed):
        raise OracleContractError(f"{space.get('id')}: decision and fixed groups overlap")
    if set(decisions) | set(fixed) != groups:
        missing = sorted(groups - (set(decisions) | set(fixed)))
        extra = sorted((set(decisions) | set(fixed)) - groups)
        raise OracleContractError(
            f"{space.get('id')}: oracle variables differ from catalog; missing={missing}, extra={extra}"
        )
    declared_evidence = space.get("evidenceByGroup")
    if not isinstance(declared_evidence, dict):
        raise OracleContractError(f"{space.get('id')}: evidenceByGroup must be an object")
    normalized_evidence = {
        group: sorted(values) if isinstance(values, list) else values
        for group, values in declared_evidence.items()
    }
    if normalized_evidence != catalog_evidence:
        raise OracleContractError(
            f"{space.get('id')}: evidenceByGroup is not a golden projection of the bound catalog"
        )
    constraints = space.get("constraints")
    if not isinstance(constraints, list):
        raise OracleContractError(f"{space.get('id')}: constraints must be a list")
    declared_requires: set[tuple[str, str]] = set()
    for row in constraints:
        if not isinstance(row, dict) or row.get("kind") not in {"requires", "mutex"}:
            raise OracleContractError(f"{space.get('id')}: unsupported constraint")
        left, right = row.get("left"), row.get("right")
        if left not in groups or right not in groups or left == right:
            raise OracleContractError(f"{space.get('id')}: invalid constraint endpoints")
        if row["kind"] == "requires":
            declared_requires.add((left, right))
    if declared_requires != catalog_requires:
        raise OracleContractError(
            f"{space.get('id')}: requires constraints differ from the bound catalog"
        )
    known_evidence = {item for values in catalog_evidence.values() for item in values}
    goal_ids: set[str] = set()
    for goal in goals:
        if goal.get("id") in goal_ids:
            raise OracleContractError(f"{space.get('id')}: duplicate goal binding")
        goal_ids.add(goal.get("id"))
        if goal.get("module") != space.get("module") or goal.get("applicationFamily") != space.get("applicationFamily"):
            raise OracleContractError(f"{space.get('id')}: goal belongs to another module or family")
        binding = goal.get("catalogBinding", {})
        if binding != space.get("catalogBinding"):
            raise OracleContractError(f"{space.get('id')}: goal is not bound to the same catalog")
        requirements = goal.get("evidenceRequirements", {})
        required = requirements.get("required")
        optional = requirements.get("optional")
        if not isinstance(required, list) or not required or len(required) != len(set(required)):
            raise OracleContractError(f"{goal.get('id')}: required evidence must be unique and non-empty")
        if not isinstance(optional, list) or len(optional) != len(set(optional)):
            raise OracleContractError(f"{goal.get('id')}: optional evidence must be unique")
        if set(required) & set(optional):
            raise OracleContractError(f"{goal.get('id')}: required and optional evidence overlap")
        unknown = (set(required) | set(optional)) - known_evidence
        if unknown:
            raise OracleContractError(f"{goal.get('id')}: evidence absent from catalog: {sorted(unknown)}")


def _catalog_admissible(
    assignment: dict[str, bool], constraints: list[dict[str, Any]]
) -> bool:
    for constraint in constraints:
        left, right = constraint["left"], constraint["right"]
        if constraint["kind"] == "requires" and assignment[left] and not assignment[right]:
            return False
        if constraint["kind"] == "mutex" and assignment[left] and assignment[right]:
            return False
    return True


def _goal_values(
    evidence: set[str],
    assignment: dict[str, bool],
    decision_groups: list[str],
    goal: dict[str, Any],
) -> dict[str, Any]:
    requirements = goal["evidenceRequirements"]
    required = set(requirements["required"])
    optional = set(requirements["optional"])
    covered_required = sorted(required & evidence)
    covered_optional = sorted(optional & evidence)
    return {
        "requiredEvidenceCoverage": len(covered_required) / len(required),
        "structuralRequiredSetCovered": len(covered_required) == len(required),
        "structuralActivationCount": sum(assignment[group] for group in decision_groups),
        "totalActiveGroupCount": sum(assignment.values()),
        "coveredRequiredEvidence": covered_required,
        "missingRequiredEvidence": sorted(required - evidence),
        "coveredOptionalEvidence": covered_optional,
        "runtimeRelationsUnevaluated": list(requirements["requiredRelations"]),
    }


def _dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    better_or_equal = (
        left["requiredEvidenceCoverage"] >= right["requiredEvidenceCoverage"]
        and int(left["structuralRequiredSetCovered"]) >= int(right["structuralRequiredSetCovered"])
        and left["structuralActivationCount"] <= right["structuralActivationCount"]
    )
    strictly_better = (
        left["requiredEvidenceCoverage"] > right["requiredEvidenceCoverage"]
        or int(left["structuralRequiredSetCovered"]) > int(right["structuralRequiredSetCovered"])
        or left["structuralActivationCount"] < right["structuralActivationCount"]
    )
    return better_or_equal and strictly_better


def _diagnose_diminishing_returns(
    configurations: list[dict[str, Any]],
    goal_id: str,
    objective: str,
) -> dict[str, Any]:
    """Check diminishing returns on the enumerated catalog-admissible domain.

    This diagnostic is a finite counterexample search, not a theorem about the
    runtime system or a guarantee outside the frozen catalog.
    """
    by_seed = {frozenset(row["decisionSet"]): row for row in configurations}
    ground = sorted({item for seed in by_seed for item in seed})

    def value(seed: frozenset[str]) -> float:
        raw = by_seed[seed]["goals"][goal_id][objective]
        return float(raw)

    checks = 0
    violation_count = 0
    examples: list[dict[str, Any]] = []
    seeds = sorted(by_seed, key=lambda item: (len(item), sorted(item)))
    for small in seeds:
        for large in seeds:
            if not small.issubset(large):
                continue
            for element in ground:
                if element in large:
                    continue
                small_plus = small | {element}
                large_plus = large | {element}
                if small_plus not in by_seed or large_plus not in by_seed:
                    continue
                checks += 1
                small_delta = value(small_plus) - value(small)
                large_delta = value(large_plus) - value(large)
                if small_delta + 1e-12 < large_delta:
                    violation_count += 1
                    if len(examples) < 8:
                        examples.append({
                            "A": sorted(small),
                            "B": sorted(large),
                            "element": element,
                            "marginalAtA": small_delta,
                            "marginalAtB": large_delta,
                        })
    if not checks:
        classification = "not-assessable-on-enumerated-domain"
    elif violation_count:
        classification = "violation-in-enumerated-structural-domain"
    else:
        classification = "no-violation-in-enumerated-structural-domain"
    return {
        "objective": objective,
        "classification": classification,
        "checkedInequalities": checks,
        "violationCount": violation_count,
        "counterexamples": examples,
        "claimBoundary": (
            "Finite diagnostic over catalog-admissible structural assignments only; no runtime, "
            "noise, general submodularity, or approximation guarantee is inferred."
        ),
    }


def enumerate_space(
    space: dict[str, Any],
    catalog: dict[str, Any],
    goals: list[dict[str, Any]],
) -> dict[str, Any]:
    """Enumerate every structural assignment admitted by one frozen catalog."""
    _validate_space(space, catalog, goals)
    decisions = list(space["decisionGroups"])
    fixed = dict(space["fixedAssignments"])
    evidence_by_group = space["evidenceByGroup"]
    configurations: list[dict[str, Any]] = []
    for bits in itertools.product((False, True), repeat=len(decisions)):
        assignment = {**fixed, **dict(zip(decisions, bits, strict=True))}
        if not _catalog_admissible(assignment, space["constraints"]):
            continue
        active = sorted(group for group, enabled in assignment.items() if enabled)
        evidence = sorted({item for group in active for item in evidence_by_group[group]})
        decision_set = sorted(group for group in decisions if assignment[group])
        row = {
            "id": "cfg-" + "".join("1" if assignment[group] else "0" for group in decisions),
            "assignment": {group: assignment[group] for group in sorted(assignment)},
            "decisionSet": decision_set,
            "activeGroups": active,
            "declaredEvidence": evidence,
            "goals": {
                goal["id"]: _goal_values(set(evidence), assignment, decisions, goal)
                for goal in goals
            },
        }
        configurations.append(row)
    configurations.sort(key=lambda row: row["id"])
    goal_reports: dict[str, Any] = {}
    for goal in goals:
        goal_id = goal["id"]
        covered = [
            row for row in configurations
            if row["goals"][goal_id]["structuralRequiredSetCovered"]
        ]
        minimum = min(
            (row["goals"][goal_id]["structuralActivationCount"] for row in covered),
            default=None,
        )
        minimum_ids = [
            row["id"] for row in covered
            if row["goals"][goal_id]["structuralActivationCount"] == minimum
        ]
        nondominated = [
            row["id"]
            for row in configurations
            if not any(
                other is not row
                and _dominates(other["goals"][goal_id], row["goals"][goal_id])
                for other in configurations
            )
        ]
        goal_reports[goal_id] = {
            "structurallyCoveringConfigurationCount": len(covered),
            "minimumDecisionActivationCount": minimum,
            "minimumStructuralConfigurationIds": minimum_ids,
            "nondominatedConfigurationIds": nondominated,
            "diminishingReturnsDiagnostics": [
                _diagnose_diminishing_returns(
                    configurations, goal_id, "requiredEvidenceCoverage"
                ),
                _diagnose_diminishing_returns(
                    configurations, goal_id, "structuralRequiredSetCovered"
                ),
            ],
        }
    return {
        "schemaVersion": 1,
        "spaceId": space["id"],
        "module": space["module"],
        "applicationFamily": space["applicationFamily"],
        "decisionGroupCount": len(decisions),
        "candidateAssignmentCount": 2 ** len(decisions),
        "feasibleConfigurationCount": len(configurations),
        "configurations": configurations,
        "configurationDigest": _sha256_bytes(_canonical(configurations)),
        "goals": goal_reports,
        "exactness": {
            "kind": "exhaustive-finite-structural-enumeration",
            "compatibilityFieldNote": "feasibleConfigurationCount is a legacy field name bounded to catalog-admissible structural assignments; it does not assert operational deployability.",
            "catalogDigest": space["catalogBinding"]["sha256"],
            "runtimeOutcomesUsed": False,
            "noiseEliminated": False,
            "globalDeploymentOptimalityClaimed": False,
        },
    }


def evaluate_registry(registry: dict[str, Any], root: Path) -> dict[str, Any]:
    root = root.resolve()
    _validate_schema_instance(
        root,
        "finite-configuration-space.schema.json",
        registry,
        "configuration-space registry",
    )
    if registry.get("status") != "frozen-for-exact-structural-enumeration":
        raise OracleContractError("registry is not frozen for exact structural enumeration")
    spaces: list[dict[str, Any]] = []
    seen: set[str] = set()
    for space in registry.get("spaces", []):
        if space.get("id") in seen:
            raise OracleContractError(f"duplicate space id: {space.get('id')}")
        seen.add(space.get("id"))
        catalog = _bound_json(root, space["catalogBinding"])
        goals = [
            _bound_json(root, binding, schema_name="optimization-goal.schema.json")
            for binding in space["goalBindings"]
        ]
        spaces.append(enumerate_space(space, catalog, goals))
    return {
        "schemaVersion": 1,
        "registryId": registry["id"],
        "spaceCount": len(spaces),
        "spaces": spaces,
        "claimBoundary": registry["claimBoundary"],
    }


def evaluate_registry_path(path: Path, root: Path | None = None) -> dict[str, Any]:
    path = path.resolve()
    repository_root = (root or path.parent.parent).resolve()
    return evaluate_registry(json.loads(path.read_text(encoding="utf-8")), repository_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "registry", type=Path, nargs="?", default=Path("research/exact-configuration-spaces.json")
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate_registry_path(args.registry, args.root)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
