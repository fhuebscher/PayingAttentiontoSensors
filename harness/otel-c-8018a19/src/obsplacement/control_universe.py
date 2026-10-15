"""Fail-closed evaluation of backend-neutral control-universe microtests.

The evaluator deliberately stops at a structural map of controllable stages.
It does not rank configurations, infer unsupported controls, or establish that
controls with similar names are equivalent across application families.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Callable


STAGES = (
    "declared",
    "enabled",
    "emitted",
    "transported",
    "retained",
)
TRANSITIONS = tuple(zip(STAGES, STAGES[1:]))
CONTROL_KINDS = (
    "full-reference",
    "true-source-off",
    "emission-off",
    "transport-off",
    "retention-off",
    "one-group-perturbation",
)
STATES = {"on", "off", "unknown", "unsupported", "not-applicable"}
TARGET_STATES = STATES | {"observe"}
RELATIONS = {
    "preserved",
    "reduced",
    "eliminated",
    "amplified",
    "not-comparable",
    "indeterminate",
    "unsupported",
    "not-applicable",
}
SUPPORT_STATES = {"supported", "unsupported", "unknown"}
STAGE_EFFECTS = {
    "direct-control",
    "indirect-coupling",
    "no-known-effect",
    "unknown",
    "unsupported",
}
TARGET_SCOPES = {"target-set", "background-set", "combined", "global"}
BACKGROUND_MODES = {"forbid", "exclude", "separate", "include"}
MECHANISMS = {
    "source-weaving",
    "source-sdk",
    "runtime-monitor",
    "runtime-configuration",
    "export-filter",
    "transport-route",
    "collector-filter",
    "backend-retention",
    "mixed",
    "other",
}
LOCI = {"source", "process-runtime", "transport", "collector", "backend", "mixed"}
EVIDENCE_KINDS = {
    "source-inspection",
    "configuration",
    "runtime-receipt",
    "collector-output",
    "backend-query",
    "test",
    "other",
}
STAGE_EVIDENCE_KINDS = {
    "declared": {"source-inspection", "configuration", "runtime-receipt"},
    "enabled": {"runtime-receipt"},
    "emitted": {"runtime-receipt", "collector-output"},
    "transported": {"collector-output"},
    "retained": {"backend-query", "collector-output"},
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
EvidenceVerifier = Callable[[dict[str, Any]], bool]


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def artifact_identity(items: list[dict[str, Any]]) -> str:
    bindings: list[dict[str, str]] = []
    for item in items:
        identifier, digest = item.get("id"), item.get("sha256")
        if (not _nonempty_string(identifier) or not isinstance(digest, str) or
                not SHA256_RE.fullmatch(digest)):
            raise ValueError("artifact identity requires valid evidence ids and digests")
        bindings.append({"id": identifier, "sha256": digest})
    if len({item["id"] for item in bindings}) != len(bindings):
        raise ValueError("artifact identity requires unique evidence ids")
    bindings.sort(key=lambda item: (item["id"], item["sha256"]))
    payload = json.dumps(bindings, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def _portable_relative_locator(value: Any) -> bool:
    if not _nonempty_string(value) or "\\" in value or WINDOWS_DRIVE_RE.match(value):
        return False
    relative = PurePosixPath(value)
    return (not relative.is_absolute() and relative != PurePosixPath(".") and
            ".." not in relative.parts)


def _json_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _same_value(left: Any, right: Any) -> bool:
    """Compare JSON scalar settings without treating bool as an integer."""
    return type(left) is type(right) and left == right


def _contains_value(values: list[Any], candidate: Any) -> bool:
    return any(_same_value(item, candidate) for item in values)


def _validate_evidence_items(
    items: Any,
    prefix: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        errors.append(f"{prefix}.evidenceItems must be a list")
        return {}
    by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        where = f"{prefix}.evidenceItems[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where} must be an object")
            continue
        identifier = item.get("id")
        if not _nonempty_string(identifier):
            errors.append(f"{where}.id must be a non-empty string")
            continue
        if identifier in by_id:
            errors.append(f"{prefix} contains duplicate evidence id {identifier!r}")
            continue
        if item.get("kind") not in EVIDENCE_KINDS:
            errors.append(f"{where}.kind is unsupported")
        locator = item.get("locator")
        if not _nonempty_string(locator):
            errors.append(f"{where}.locator must be a non-empty string")
        elif not _portable_relative_locator(locator):
            errors.append(
                f"{where}.locator must be evidence-root-relative without parent traversal")
        if not isinstance(item.get("sha256"), str) or not SHA256_RE.fullmatch(item["sha256"]):
            errors.append(f"{where}.sha256 must be a lowercase 64-character digest")
        if not _nonempty_string(item.get("capturedAt")):
            errors.append(f"{where}.capturedAt must be recorded")
        by_id[identifier] = item
    return by_id


def _validate_refs(
    refs: Any,
    available: set[str],
    where: str,
    errors: list[str],
    *,
    require_nonempty: bool = True,
) -> list[str]:
    if not isinstance(refs, list) or any(not _nonempty_string(item) for item in refs):
        errors.append(f"{where} must be a list of evidence ids")
        return []
    if require_nonempty and not refs:
        errors.append(f"{where} must not be empty")
    if len(refs) != len(set(refs)):
        errors.append(f"{where} must not contain duplicates")
    missing = sorted(set(refs) - available)
    if missing:
        errors.append(f"{where} references unknown evidence ids: {missing}")
    return refs


def _validate_support(
    support: Any,
    evidence_ids: set[str],
    abstentions: dict[str, dict[str, Any]],
    where: str,
    errors: list[str],
    expected_subject_type: str,
    expected_subject_id: str,
) -> str | None:
    if not isinstance(support, dict):
        errors.append(f"{where} must be an object")
        return None
    status = support.get("status")
    if status not in SUPPORT_STATES:
        errors.append(f"{where}.status is unsupported")
        return None
    _validate_refs(support.get("evidenceItems"), evidence_ids, f"{where}.evidenceItems", errors)
    abstention_id = support.get("abstentionId")
    if status == "supported":
        if abstention_id is not None:
            errors.append(f"{where}.abstentionId must be null for supported controls")
    elif not _nonempty_string(abstention_id) or abstention_id not in abstentions:
        errors.append(f"{where}.abstentionId must reference an explicit abstention")
    else:
        abstention = abstentions[abstention_id]
        if (abstention.get("subjectType"), abstention.get("subjectId")) != (
            expected_subject_type,
            expected_subject_id,
        ):
            errors.append(
                f"{where}.abstentionId does not match "
                f"{expected_subject_type} {expected_subject_id!r}"
            )
    return status


def _parse_timestamp(value: Any) -> datetime | None:
    if not _nonempty_string(value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _verify_items(
    evidence: dict[str, dict[str, Any]],
    verifier: EvidenceVerifier | None,
    where: str,
    errors: list[str],
    blockers: list[str],
) -> None:
    if verifier is None:
        blockers.append(f"{where} evidence is not bound: no evidence_verifier was provided")
        return
    for identifier, item in evidence.items():
        try:
            verified = verifier(item)
        except Exception as exc:  # pragma: no cover - defensive boundary
            errors.append(f"{where} evidence verifier failed for {identifier!r}: {exc}")
            continue
        if verified is not True:
            blockers.append(
                f"{where} evidence {identifier!r} was not bound to locator and digest"
            )


def _expected_relation(
    source: dict[str, Any],
    target: dict[str, Any],
    target_stage: str,
) -> str:
    source_state = source.get("state")
    target_state = target.get("state")
    if "unsupported" in {source_state, target_state}:
        return "unsupported"
    if "not-applicable" in {source_state, target_state}:
        return "not-applicable"
    if "unknown" in {source_state, target_state}:
        return "indeterminate"
    comparable_fields = (
        "semanticUnit",
        "identityNamespace",
        "identityPolicy",
        "denominatorKind",
        "targetScope",
        "targetPopulation",
    )
    if any(source.get(field) != target.get(field) for field in comparable_fields):
        return "not-comparable"
    source_count = source.get("count")
    target_count = target.get("count")
    if not isinstance(source_count, int) or not isinstance(target_count, int):
        return "indeterminate"
    if target_count == source_count:
        return "preserved"
    if source_count > 0 and target_count == 0:
        return "eliminated"
    if target_count < source_count:
        return "reduced"
    return "amplified"


def _validate_stage_record(
    record: Any,
    stage: str,
    evidence: dict[str, dict[str, Any]],
    semantic_context: dict[str, Any],
    where: str,
    errors: list[str],
    blockers: list[str],
) -> None:
    if not isinstance(record, dict):
        errors.append(f"{where} must be an object")
        return
    state = record.get("state")
    count = record.get("count")
    if state not in STATES:
        errors.append(f"{where}.state is unsupported")
    if state in {"on", "off"}:
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            errors.append(f"{where}.count must be a non-negative integer for observed stages")
        elif state == "on" and count == 0:
            errors.append(f"{where} cannot be on with a zero count")
        elif state == "off" and count != 0:
            errors.append(f"{where} cannot be off with a non-zero count")
    elif count is not None:
        errors.append(f"{where}.count must be null when stage state is not observed")
    refs = _validate_refs(
        record.get("evidenceItems"), set(evidence), f"{where}.evidenceItems", errors
    )
    for field in (
        "semanticUnit", "identityNamespace", "identityPolicy",
        "denominatorKind", "measurementPoint",
    ):
        if not _nonempty_string(record.get(field)):
            errors.append(f"{where}.{field} must be a non-empty string")
    target_scope = record.get("targetScope")
    if target_scope not in TARGET_SCOPES:
        errors.append(f"{where}.targetScope is unsupported")
    population = record.get("targetPopulation")
    if (not isinstance(population, list) or not population or
            len(population) != len(set(population)) or
            any(not _nonempty_string(item) for item in population)):
        errors.append(f"{where}.targetPopulation must be a non-empty unique list")
        population = []
    target_set = semantic_context.get("targetSet", [])
    background_policy = semantic_context.get("backgroundPolicy", {})
    background_set = background_policy.get("backgroundSet", []) if isinstance(background_policy, dict) else []
    background_mode = background_policy.get("mode") if isinstance(background_policy, dict) else None
    if target_scope == "target-set" and set(population) != set(target_set):
        errors.append(f"{where}.targetPopulation differs from semanticContext.targetSet")
    elif target_scope == "background-set" and set(population) != set(background_set):
        errors.append(f"{where}.targetPopulation differs from the declared background set")
    elif target_scope == "combined":
        if background_mode != "include" or set(population) != set(target_set) | set(background_set):
            errors.append(f"{where} combines target/background without an include policy")
    if state in {"on", "off"}:
        observed_kinds = {evidence[item].get("kind") for item in refs if item in evidence}
        if not observed_kinds & STAGE_EVIDENCE_KINDS[stage]:
            blockers.append(
                f"{where} lacks stage-appropriate runtime evidence; "
                f"generic test evidence cannot prove {stage!r}"
            )


def _validate_observation(
    observation: dict[str, Any],
    catalog_id: str,
    microtest: dict[str, Any],
    groups: dict[str, dict[str, Any]],
    catalog_abstentions: dict[str, dict[str, Any]],
    semantic_context: dict[str, Any],
    evidence_verifier: EvidenceVerifier | None,
    errors: list[str],
    blockers: list[str],
) -> dict[str, Any]:
    obs_id = observation.get("id", "<unknown>")
    where = f"observation {obs_id!r}"
    if observation.get("controlUniverseId") != catalog_id:
        errors.append(f"{where} targets a different control universe")
    if observation.get("microtestId") != microtest.get("id"):
        errors.append(f"{where} targets a different microtest")
    if observation.get("terminal") is not True:
        errors.append(f"{where} is not terminal")
    if observation.get("teardownClean") is not True:
        errors.append(f"{where} lacks clean teardown proof")

    identity = observation.get("runIdentity")
    if not isinstance(identity, dict):
        errors.append(f"{where}.runIdentity must be an object")
    else:
        if not isinstance(identity.get("frameworkCommit"), str) or not COMMIT_RE.fullmatch(identity["frameworkCommit"]):
            errors.append(f"{where}.runIdentity.frameworkCommit must be an exact commit")
        if not isinstance(identity.get("sutCommit"), str) or not COMMIT_RE.fullmatch(identity["sutCommit"]):
            errors.append(f"{where}.runIdentity.sutCommit must be an exact commit")
        started = _parse_timestamp(identity.get("startedAt"))
        ended = _parse_timestamp(identity.get("endedAt"))
        if started is None or ended is None:
            errors.append(f"{where}.runIdentity must record valid ISO start and end timestamps")
        elif started.tzinfo is None or ended.tzinfo is None:
            errors.append(f"{where}.runIdentity timestamps must include a timezone")
        elif ended <= started:
            errors.append(f"{where}.runIdentity endedAt must be after startedAt")
        artifact_root = identity.get("artifactRoot")
        if not _nonempty_string(artifact_root):
            errors.append(f"{where}.runIdentity.artifactRoot must be recorded")
        elif not _portable_relative_locator(artifact_root):
            errors.append(
                f"{where}.runIdentity.artifactRoot must be evidence-root-relative "
                "without parent traversal")
        if not isinstance(identity.get("artifactSha256"), str) or not SHA256_RE.fullmatch(identity["artifactSha256"]):
            errors.append(f"{where}.runIdentity.artifactSha256 must be an exact digest")

    observation_evidence = _validate_evidence_items(observation.get("evidenceItems"), where, errors)
    evidence_ids = set(observation_evidence)
    if isinstance(identity, dict):
        try:
            expected_artifact = artifact_identity(list(observation_evidence.values()))
        except ValueError:
            expected_artifact = None
        recorded_artifact = identity.get("artifactSha256")
        if (expected_artifact is not None and isinstance(recorded_artifact, str) and
                SHA256_RE.fullmatch(recorded_artifact) and
                recorded_artifact != expected_artifact):
            errors.append(
                f"{where}.runIdentity.artifactSha256 differs from the sorted evidence identity")
    _verify_items(observation_evidence, evidence_verifier, where, errors, blockers)

    semantic_binding = observation.get("semanticBinding")
    if not isinstance(semantic_binding, dict):
        errors.append(f"{where}.semanticBinding must be an object")
    else:
        for key in (
            "contextId", "scenarioId", "channelId", "nativeSemanticUnit",
            "nativeIdentityFields", "targetSet",
        ):
            if semantic_binding.get(key) != semantic_context.get(key):
                errors.append(f"{where}.semanticBinding.{key} differs from the frozen context")
        refs = _validate_refs(
            semantic_binding.get("evidenceItems"), evidence_ids,
            f"{where}.semanticBinding.evidenceItems", errors,
        )
        if semantic_binding.get("completeness") != "complete":
            blockers.append(f"{where} acquisition completeness is not terminally complete")
        kinds = {
            observation_evidence[item].get("kind")
            for item in refs if item in observation_evidence
        }
        if not kinds & {"runtime-receipt", "collector-output", "backend-query"}:
            blockers.append(f"{where} completeness lacks runtime-channel evidence")
        binding_background = semantic_binding.get("backgroundPolicy")
        catalog_background = semantic_context.get("backgroundPolicy")
        if not isinstance(binding_background, dict):
            errors.append(f"{where}.semanticBinding.backgroundPolicy must be an object")
        else:
            for key in ("mode", "backgroundSet"):
                expected = catalog_background.get(key) if isinstance(catalog_background, dict) else None
                if binding_background.get(key) != expected:
                    errors.append(
                        f"{where}.semanticBinding.backgroundPolicy.{key} differs "
                        "from the frozen context"
                    )
            _validate_refs(
                binding_background.get("evidenceItems"), evidence_ids,
                f"{where}.semanticBinding.backgroundPolicy.evidenceItems", errors,
            )
    settings = observation.get("activationSettings")
    if not isinstance(settings, dict):
        errors.append(f"{where}.activationSettings must be an object")
        settings = {}
    expected_settings = microtest.get("settings", {})
    if settings != expected_settings:
        blockers.append(f"{where} activation settings differ from the frozen microtest target")
    for group_id, value in settings.items():
        if group_id not in groups:
            errors.append(f"{where} sets unknown activation group {group_id!r}")
            continue
        domain = groups[group_id].get("settingDomain", {})
        values = domain.get("values", []) if isinstance(domain, dict) else []
        if not isinstance(values, list) or not _contains_value(values, value):
            errors.append(f"{where} uses an out-of-domain value for {group_id!r}")
    for group_id, group in groups.items():
        group_value = settings.get(group_id)
        group_off = group.get("settingDomain", {}).get("offValue")
        if group_id not in settings or _same_value(group_value, group_off):
            continue
        for dependency in group.get("dependencies", []):
            dependency_off = groups.get(dependency, {}).get("settingDomain", {}).get("offValue")
            if dependency in settings and _same_value(settings[dependency], dependency_off):
                errors.append(
                    f"{where} enables dependent group {group_id!r} while dependency "
                    f"{dependency!r} is off"
                )

    stages = observation.get("stages")
    if not isinstance(stages, dict):
        errors.append(f"{where}.stages must be an object")
        stages = {}
    if set(stages) != set(STAGES):
        errors.append(f"{where}.stages must contain exactly {list(STAGES)}")
    for stage in STAGES:
        _validate_stage_record(
            stages.get(stage), stage, observation_evidence, semantic_context,
            f"{where}.stages.{stage}", errors, blockers,
        )
        record = stages.get(stage)
        if isinstance(record, dict) and record.get("state") not in {"on", "off"}:
            blockers.append(f"{where} stage {stage!r} is not empirically observed")

    if microtest.get("kind") == "full-reference":
        for stage in STAGES:
            record = stages.get(stage)
            if not isinstance(record, dict) or record.get("state") != "on":
                blockers.append(f"{where} full reference does not establish stage {stage!r}")

    transition_rows = observation.get("transitions")
    transitions: dict[tuple[str, str], dict[str, Any]] = {}
    if not isinstance(transition_rows, list):
        errors.append(f"{where}.transitions must be a list")
        transition_rows = []
    for index, row in enumerate(transition_rows):
        path = f"{where}.transitions[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{path} must be an object")
            continue
        edge = (row.get("from"), row.get("to"))
        if edge in transitions:
            errors.append(f"{where} contains duplicate transition {edge}")
            continue
        transitions[edge] = row
        if edge not in TRANSITIONS:
            errors.append(f"{path} is not an adjacent stage transition")
        if row.get("relation") not in RELATIONS:
            errors.append(f"{path}.relation is unsupported")
        _validate_refs(row.get("evidenceItems"), evidence_ids, f"{path}.evidenceItems", errors)
    if set(transitions) != set(TRANSITIONS):
        errors.append(f"{where} must report every adjacent stage transition exactly once")
    for source, target in TRANSITIONS:
        row = transitions.get((source, target))
        if row is None or source not in stages or target not in stages:
            continue
        expected = _expected_relation(stages[source], stages[target], target)
        if row.get("relation") != expected:
            errors.append(
                f"{where} transition {source}->{target} reports {row.get('relation')!r}; "
                f"reconciled stage state requires {expected!r}"
            )

    target_stages = microtest.get("targetStages", {})
    if isinstance(target_stages, dict):
        for stage in STAGES:
            target = target_stages.get(stage)
            observed = stages.get(stage, {}).get("state") if isinstance(stages.get(stage), dict) else None
            if target not in {None, "observe"} and observed != target:
                blockers.append(
                    f"{where} stage {stage!r} observed {observed!r}, expected {target!r}"
                )

    blind_rows = observation.get("blindRegions")
    blind_stages: set[str] = set()
    if not isinstance(blind_rows, list):
        errors.append(f"{where}.blindRegions must be a list")
        blind_rows = []
    for index, row in enumerate(blind_rows):
        path = f"{where}.blindRegions[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{path} must be an object")
            continue
        row_stages = row.get("stages")
        if not isinstance(row_stages, list) or not row_stages or any(stage not in STAGES for stage in row_stages):
            errors.append(f"{path}.stages must name one or more known stages")
            row_stages = []
        blind_stages.update(row_stages)
        if not _nonempty_string(row.get("reason")):
            errors.append(f"{path}.reason must be recorded")
        evidence_refs = row.get("evidenceItems")
        abstention_id = row.get("abstentionId")
        if evidence_refs:
            _validate_refs(evidence_refs, evidence_ids, f"{path}.evidenceItems", errors)
        elif not _nonempty_string(abstention_id) or abstention_id not in catalog_abstentions:
            errors.append(f"{path} needs evidence or a catalog abstention")
    for stage, record in stages.items():
        if isinstance(record, dict) and record.get("state") in {"unknown", "unsupported"} and stage not in blind_stages:
            errors.append(f"{where} leaves stage {stage!r} blind without a blind-region record")

    coupling_rows = observation.get("couplings")
    if not isinstance(coupling_rows, list):
        errors.append(f"{where}.couplings must be a list")
        coupling_rows = []
    for index, row in enumerate(coupling_rows):
        path = f"{where}.couplings[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{path} must be an object")
            continue
        group_ids = row.get("groupIds")
        if (not isinstance(group_ids, list) or len(group_ids) < 2 or
                len(group_ids) != len(set(group_ids)) or any(group_id not in groups for group_id in group_ids)):
            errors.append(f"{path}.groupIds must name at least two known activation groups")
        row_stages = row.get("stages")
        if not isinstance(row_stages, list) or not row_stages or any(stage not in STAGES for stage in row_stages):
            errors.append(f"{path}.stages must name one or more known stages")
        if not _nonempty_string(row.get("reason")):
            errors.append(f"{path}.reason must be recorded")
        _validate_refs(row.get("evidenceItems"), evidence_ids, f"{path}.evidenceItems", errors)

    return {
        "blindRegions": blind_rows,
        "couplings": coupling_rows,
        "stages": stages,
        "evidence": observation_evidence,
    }


def evaluate_control_universe(
    catalog: dict[str, Any],
    observations: list[dict[str, Any]],
    *,
    evidence_verifier: EvidenceVerifier | None = None,
) -> dict[str, Any]:
    """Validate Phase 1 evidence and return a structural mapping ``Phi``.

    Inputs are not mutated. Any missing target, provenance item, terminal stage,
    or explicit abstention lowers the claim ceiling to ``descriptive-only``.
    Even a complete result is only a structural control map. Empirical promotion
    requires a module adapter's semantic validator and curated readiness gate.
    """
    errors: list[str] = []
    blockers: list[str] = []
    if not isinstance(catalog, dict):
        catalog = {}
        errors.append("control universe must be an object")
    if catalog.get("schemaVersion") != 1:
        errors.append("control universe schemaVersion must be 1")
    catalog_id = catalog.get("id")
    if not _nonempty_string(catalog_id):
        errors.append("control universe id must be a non-empty string")
        catalog_id = "<unknown>"
    family = catalog.get("family")
    if not _nonempty_string(family):
        errors.append("control universe family must be a non-empty string")

    policy = catalog.get("claimPolicy")
    required_policy = {
        "phase": "control-universe-characterization",
        "completeClaimCeiling": "phase-1-structural-control-map",
        "incompleteClaimCeiling": "descriptive-only",
        "empiricalClaimsAllowed": False,
        "optimizationClaimsAllowed": False,
        "crossFamilyEquivalenceAllowed": False,
    }
    if policy != required_policy:
        errors.append("claimPolicy must preserve the fail-closed Phase 1 ceiling")

    evidence = _validate_evidence_items(catalog.get("evidenceItems"), "catalog", errors)
    evidence_ids = set(evidence)
    _verify_items(evidence, evidence_verifier, "catalog", errors, blockers)

    semantic_context = catalog.get("semanticContext")
    if not isinstance(semantic_context, dict):
        errors.append("catalog.semanticContext must be an object")
        semantic_context = {}
    else:
        for key in ("contextId", "scenarioId", "channelId", "nativeSemanticUnit"):
            if not _nonempty_string(semantic_context.get(key)):
                errors.append(f"catalog.semanticContext.{key} must be a non-empty string")
        identity_fields = semantic_context.get("nativeIdentityFields")
        if (not isinstance(identity_fields, list) or not identity_fields or
                len(identity_fields) != len(set(identity_fields)) or
                any(not _nonempty_string(item) for item in identity_fields)):
            errors.append(
                "catalog.semanticContext.nativeIdentityFields must be a non-empty unique list"
            )
        target_set = semantic_context.get("targetSet")
        if (not isinstance(target_set, list) or not target_set or
                len(target_set) != len(set(target_set)) or
                any(not _nonempty_string(item) for item in target_set)):
            errors.append("catalog.semanticContext.targetSet must be a non-empty unique list")
        background_policy = semantic_context.get("backgroundPolicy")
        if not isinstance(background_policy, dict):
            errors.append("catalog.semanticContext.backgroundPolicy must be an object")
        else:
            if background_policy.get("mode") not in BACKGROUND_MODES:
                errors.append("catalog.semanticContext.backgroundPolicy.mode is unsupported")
            background_set = background_policy.get("backgroundSet")
            if (not isinstance(background_set, list) or
                    len(background_set) != len(set(background_set)) or
                    any(not _nonempty_string(item) for item in background_set)):
                errors.append(
                    "catalog.semanticContext.backgroundPolicy.backgroundSet must be a unique list"
                )
            _validate_refs(
                background_policy.get("evidenceItems"), evidence_ids,
                "catalog.semanticContext.backgroundPolicy.evidenceItems", errors,
            )
        if not _nonempty_string(semantic_context.get("completenessCriterion")):
            errors.append("catalog.semanticContext.completenessCriterion must be recorded")
        _validate_refs(
            semantic_context.get("evidenceItems"), evidence_ids,
            "catalog.semanticContext.evidenceItems", errors,
        )

    abstention_rows = catalog.get("abstentions")
    abstentions: dict[str, dict[str, Any]] = {}
    if not isinstance(abstention_rows, list):
        errors.append("catalog.abstentions must be a list")
        abstention_rows = []
    for index, item in enumerate(abstention_rows):
        where = f"catalog.abstentions[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where} must be an object")
            continue
        identifier = item.get("id")
        if not _nonempty_string(identifier):
            errors.append(f"{where}.id must be a non-empty string")
            continue
        if identifier in abstentions:
            errors.append(f"catalog contains duplicate abstention id {identifier!r}")
        abstentions[identifier] = item
        if item.get("subjectType") not in {"activation-group", "microtest", "stage", "claim"}:
            errors.append(f"{where}.subjectType is unsupported")
        if not _nonempty_string(item.get("subjectId")) or not _nonempty_string(item.get("reason")):
            errors.append(f"{where} must record subjectId and reason")
        _validate_refs(item.get("evidenceItems"), evidence_ids, f"{where}.evidenceItems", errors)

    group_rows = catalog.get("activationGroups")
    groups: dict[str, dict[str, Any]] = {}
    group_support: dict[str, str | None] = {}
    if not isinstance(group_rows, list) or not group_rows:
        errors.append("catalog.activationGroups must be a non-empty list")
        group_rows = []
    for index, group in enumerate(group_rows):
        where = f"catalog.activationGroups[{index}]"
        if not isinstance(group, dict):
            errors.append(f"{where} must be an object")
            continue
        identifier = group.get("id")
        if not _nonempty_string(identifier):
            errors.append(f"{where}.id must be a non-empty string")
            continue
        if identifier in groups:
            errors.append(f"catalog contains duplicate activation group id {identifier!r}")
        groups[identifier] = group
        if group.get("mechanism") not in MECHANISMS:
            errors.append(f"{where}.mechanism is unsupported")
        if group.get("locus") not in LOCI:
            errors.append(f"{where}.locus is unsupported")
        dependencies = group.get("dependencies")
        if not isinstance(dependencies, list) or any(not _nonempty_string(item) for item in dependencies):
            errors.append(f"{where}.dependencies must be a list of activation group ids")
        elif len(dependencies) != len(set(dependencies)):
            errors.append(f"{where}.dependencies must not contain duplicates")
        _validate_refs(group.get("evidenceItems"), evidence_ids, f"{where}.evidenceItems", errors)
        domain = group.get("settingDomain")
        if not isinstance(domain, dict):
            errors.append(f"{where}.settingDomain must be an object")
        else:
            values = domain.get("values")
            if not isinstance(values, list) or len(values) < 2 or any(not _json_scalar(value) for value in values):
                errors.append(f"{where}.settingDomain.values must contain at least two JSON scalar settings")
                values = []
            if any(_same_value(left, right) for pos, left in enumerate(values) for right in values[pos + 1:]):
                errors.append(f"{where}.settingDomain.values must be unique")
            for key in ("referenceValue", "offValue"):
                if not _contains_value(values, domain.get(key)):
                    errors.append(f"{where}.settingDomain.{key} must be in values")
        effects = group.get("stageEffects")
        if not isinstance(effects, dict) or set(effects) != set(STAGES):
            errors.append(f"{where}.stageEffects must contain exactly {list(STAGES)}")
        elif any(effect not in STAGE_EFFECTS for effect in effects.values()):
            errors.append(f"{where}.stageEffects contains an unsupported effect")
        group_support[identifier] = _validate_support(
            group.get("support"), evidence_ids, abstentions, f"{where}.support", errors,
            "activation-group", identifier,
        )

    for group_id, group in groups.items():
        for dependency in group.get("dependencies", []):
            if dependency == group_id:
                errors.append(f"activation group {group_id!r} depends on itself")
            elif dependency not in groups:
                errors.append(f"activation group {group_id!r} depends on unknown group {dependency!r}")

    visit_state: dict[str, int] = {}

    def visit(group_id: str, path: tuple[str, ...]) -> None:
        state = visit_state.get(group_id, 0)
        if state == 1:
            errors.append(
                "activation group dependency cycle: " + " -> ".join((*path, group_id))
            )
            return
        if state == 2:
            return
        visit_state[group_id] = 1
        for dependency in groups[group_id].get("dependencies", []):
            if dependency in groups:
                visit(dependency, (*path, group_id))
        visit_state[group_id] = 2

    for group_id in groups:
        visit(group_id, ())

    tests = catalog.get("microtests")
    microtests: dict[str, dict[str, Any]] = {}
    kind_counts: Counter[str] = Counter()
    group_test_counts: Counter[str] = Counter()
    if not isinstance(tests, list):
        errors.append("catalog.microtests must be a list")
        tests = []
    for index, test in enumerate(tests):
        where = f"catalog.microtests[{index}]"
        if not isinstance(test, dict):
            errors.append(f"{where} must be an object")
            continue
        identifier = test.get("id")
        if not _nonempty_string(identifier):
            errors.append(f"{where}.id must be a non-empty string")
            continue
        if identifier in microtests:
            errors.append(f"catalog contains duplicate microtest id {identifier!r}")
        microtests[identifier] = test
        kind = test.get("kind")
        if kind not in CONTROL_KINDS:
            errors.append(f"{where}.kind is unsupported")
            continue
        kind_counts[kind] += 1
        status = _validate_support(
            test.get("support"), evidence_ids, abstentions, f"{where}.support", errors,
            "microtest", identifier,
        )
        settings = test.get("settings")
        if not isinstance(settings, dict):
            errors.append(f"{where}.settings must be an object")
            settings = {}
        target_stages = test.get("targetStages")
        if not isinstance(target_stages, dict) or set(target_stages) != set(STAGES):
            errors.append(f"{where}.targetStages must contain exactly {list(STAGES)}")
        elif any(target not in TARGET_STATES for target in target_stages.values()):
            errors.append(f"{where}.targetStages contains an unsupported target")
        if status == "supported":
            supported_groups = {group_id for group_id, support in group_support.items() if support == "supported"}
            if set(settings) != supported_groups:
                errors.append(f"{where}.settings must freeze every supported activation group exactly once")
            for group_id, value in settings.items():
                domain = groups.get(group_id, {}).get("settingDomain", {})
                if not _contains_value(domain.get("values", []), value):
                    errors.append(f"{where}.settings uses an out-of-domain value for {group_id!r}")
        elif settings:
            errors.append(f"{where}.settings must be empty when the microtest is unsupported or unknown")
        if kind == "one-group-perturbation":
            group_id = test.get("activationGroupId")
            if group_id not in groups:
                errors.append(f"{where}.activationGroupId must reference a known group")
            else:
                group_test_counts[group_id] += 1
            if not _nonempty_string(test.get("baselineTestId")):
                errors.append(f"{where}.baselineTestId must be recorded")

    for kind in CONTROL_KINDS[:-1]:
        if kind_counts[kind] == 0:
            blockers.append(f"microtest plan omits {kind!r}; add a supported test or explicit abstention")
    for group_id in groups:
        if group_test_counts[group_id] != 1:
            blockers.append(
                f"activation group {group_id!r} needs exactly one one-group perturbation or abstention"
            )

    supported_full = [test for test in microtests.values()
                      if test.get("kind") == "full-reference" and
                      isinstance(test.get("support"), dict) and
                      test["support"].get("status") == "supported"]
    if len(supported_full) != 1:
        blockers.append("Phase 1 requires exactly one supported full-reference microtest")
    baseline = supported_full[0] if len(supported_full) == 1 else None
    if baseline is not None:
        baseline_id = baseline.get("id")
        baseline_settings = baseline.get("settings", {})
        for test in microtests.values():
            if test.get("kind") != "one-group-perturbation":
                continue
            support = test.get("support", {})
            if not isinstance(support, dict) or support.get("status") != "supported":
                continue
            if test.get("baselineTestId") != baseline_id:
                errors.append(f"microtest {test.get('id')!r} does not reference the full-reference baseline")
                continue
            differences = {
                key for key in set(baseline_settings) | set(test.get("settings", {}))
                if not _same_value(baseline_settings.get(key), test.get("settings", {}).get(key))
            }
            if differences != {test.get("activationGroupId")}:
                errors.append(
                    f"microtest {test.get('id')!r} must change only its named activation group"
                )

    if not isinstance(observations, list):
        errors.append("observations must be a list")
        observations = []
    observations_by_test: dict[str, list[dict[str, Any]]] = defaultdict(list)
    observation_ids: set[str] = set()
    artifact_roots: set[str] = set()
    artifact_digests: set[str] = set()
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            errors.append(f"observations[{index}] must be an object")
            continue
        obs_id = observation.get("id")
        if not _nonempty_string(obs_id):
            errors.append(f"observations[{index}].id must be a non-empty string")
        elif obs_id in observation_ids:
            errors.append(f"observations contain duplicate id {obs_id!r}")
        else:
            observation_ids.add(obs_id)
        identity = observation.get("runIdentity")
        if isinstance(identity, dict):
            artifact_root = identity.get("artifactRoot")
            artifact_digest = identity.get("artifactSha256")
            if _nonempty_string(artifact_root):
                if artifact_root in artifact_roots:
                    errors.append(f"observation {obs_id!r} replays artifact root {artifact_root!r}")
                artifact_roots.add(artifact_root)
            if isinstance(artifact_digest, str) and SHA256_RE.fullmatch(artifact_digest):
                if artifact_digest in artifact_digests:
                    errors.append(f"observation {obs_id!r} replays artifact digest {artifact_digest!r}")
                artifact_digests.add(artifact_digest)
        microtest_id = observation.get("microtestId")
        if microtest_id not in microtests:
            errors.append(f"observation {obs_id!r} references unknown microtest {microtest_id!r}")
            continue
        support = microtests[microtest_id].get("support", {})
        if not isinstance(support, dict) or support.get("status") != "supported":
            errors.append(f"observation {obs_id!r} was supplied for a non-supported microtest")
            continue
        observations_by_test[microtest_id].append(observation)

    phi_groups: list[dict[str, Any]] = []
    coupling_regions: list[dict[str, Any]] = []
    blind_regions: list[dict[str, Any]] = []
    validated_observations: dict[str, dict[str, Any]] = {}
    for test_id, test in microtests.items():
        support = test.get("support", {})
        status = support.get("status") if isinstance(support, dict) else None
        rows = observations_by_test.get(test_id, [])
        if status == "supported" and not rows:
            blockers.append(f"supported microtest {test_id!r} lacks a terminal observation")
        if status != "supported":
            abstention = abstentions.get(support.get("abstentionId")) if isinstance(support, dict) else None
            blind_regions.append({
                "microtestId": test_id,
                "kind": test.get("kind"),
                "reason": abstention.get("reason") if abstention else "unresolved support",
                "abstentionId": support.get("abstentionId") if isinstance(support, dict) else None,
            })
            continue
        for row in rows:
            evidence_summary = _validate_observation(
                row, catalog_id, test, groups, abstentions, semantic_context,
                evidence_verifier, errors, blockers,
            )
            validated_observations[row.get("id", "<unknown>")] = evidence_summary
            for region in evidence_summary["couplings"]:
                coupling_regions.append({"microtestId": test_id, **region})
            for region in evidence_summary["blindRegions"]:
                blind_regions.append({"microtestId": test_id, **region})

    observed_effects: dict[str, list[dict[str, Any]]] = defaultdict(list)
    baseline_observation_ids = {
        row.get("id") for row in observations_by_test.get(baseline.get("id"), [])
    } if baseline else set()

    def stage_signature(summary: dict[str, Any], stage: str) -> tuple[Any, Any]:
        record = summary.get("stages", {}).get(stage)
        if not isinstance(record, dict):
            return None, None
        return record.get("state"), record.get("count")

    for test in microtests.values():
        if test.get("kind") != "one-group-perturbation":
            continue
        group_id = test.get("activationGroupId")
        for row in observations_by_test.get(test.get("id"), []):
            row_id = row.get("id", "<unknown>")
            assessment = row.get("perturbationAssessment")
            if not isinstance(assessment, dict):
                errors.append(f"observation {row_id!r} lacks a perturbationAssessment")
                continue
            baseline_id = assessment.get("baselineObservationId")
            if baseline_id not in baseline_observation_ids:
                errors.append(
                    f"observation {row_id!r} perturbationAssessment references an invalid baseline"
                )
                continue
            current = validated_observations.get(row_id, {})
            prior = validated_observations.get(baseline_id, {})
            # Evidence identifiers are intentionally excluded from stage-value comparison.
            changed_stages = [
                stage for stage in STAGES
                if stage_signature(current, stage) != stage_signature(prior, stage)
            ]
            expected_classification = "observed-delta" if changed_stages else "structured-no-effect"
            if assessment.get("classification") != expected_classification:
                errors.append(
                    f"observation {row_id!r} perturbation classification must be "
                    f"{expected_classification!r}"
                )
            if assessment.get("changedStages") != changed_stages:
                errors.append(
                    f"observation {row_id!r} perturbation changedStages does not match "
                    "the baseline delta"
                )
            if not _nonempty_string(assessment.get("reason")):
                errors.append(f"observation {row_id!r} perturbation reason must be recorded")
            _validate_refs(
                assessment.get("evidenceItems"), set(current.get("evidence", {})),
                f"observation {row_id!r}.perturbationAssessment.evidenceItems", errors,
            )
            observed_effects[group_id].append({
                "observationId": row_id,
                "baselineObservationId": baseline_id,
                "classification": expected_classification,
                "changedStages": changed_stages,
                "reason": assessment.get("reason"),
            })

    for group_id, group in groups.items():
        perturbation = next(
            (test for test in microtests.values()
             if test.get("kind") == "one-group-perturbation" and
             test.get("activationGroupId") == group_id),
            None,
        )
        phi_groups.append({
            "id": group_id,
            "support": group_support.get(group_id),
            "mechanism": group.get("mechanism"),
            "locus": group.get("locus"),
            "dependencies": group.get("dependencies", []),
            "declaredStageEffects": group.get("stageEffects", {}),
            "microtestId": perturbation.get("id") if perturbation else None,
            "terminalObservationCount": len(observations_by_test.get(perturbation.get("id"), []))
            if perturbation else 0,
            "observedPerturbationEffects": observed_effects.get(group_id, []),
        })

    structurally_valid = not errors
    complete = structurally_valid and not blockers
    return {
        "schemaVersion": 1,
        "valid": structurally_valid,
        "complete": complete,
        "claimCeiling": "phase-1-structural-control-map" if complete else "descriptive-only",
        "errors": errors,
        "blockers": blockers,
        "policy": {
            "optimizationClaimsAllowed": False,
            "empiricalClaimsAllowed": False,
            "crossFamilyEquivalenceAllowed": False,
            "unsupportedControlsRemainAbstentions": True,
            "missingStagesRemainUnknown": True,
            "empiricalPromotionRequires": [
                "module-adapter-semantic-validator",
                "curated-readiness-gate",
            ],
        },
        "coverage": {
            "activationGroupCount": len(groups),
            "microtestCount": len(microtests),
            "supportedMicrotestCount": sum(
                1 for test in microtests.values()
                if isinstance(test.get("support"), dict) and test["support"].get("status") == "supported"
            ),
            "observedMicrotestCount": len(observations_by_test),
            "controlKinds": {kind: kind_counts[kind] for kind in CONTROL_KINDS},
        },
        "phi": {
            "controlUniverseId": catalog_id,
            "family": family,
            "stages": list(STAGES),
            "activationGroups": phi_groups,
            "couplingRegions": coupling_regions,
            "blindRegions": blind_regions,
        },
    }
