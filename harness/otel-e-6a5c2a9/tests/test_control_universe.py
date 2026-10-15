from __future__ import annotations

import copy
import hashlib

from obsplacement.control_universe import (
    STAGES, TRANSITIONS, artifact_identity, evaluate_control_universe,
)


COMMIT = "b" * 40
OBS_SCHEMA = "https://observability-placement.local/contracts/control-observation.schema.json"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _evidence(identifier: str = "e", kind: str = "test") -> dict:
    return {
        "id": identifier,
        "kind": kind,
        "locator": f"evidence/{identifier}.json",
        "sha256": _digest(identifier),
        "capturedAt": "2026-08-17T00:00:00Z",
    }


def _targets(**overrides: str) -> dict[str, str]:
    result = {stage: "observe" for stage in STAGES}
    result.update(overrides)
    return result


def _support(status: str = "supported", abstention_id: str | None = None) -> dict:
    return {"status": status, "evidenceItems": ["catalog-e"], "abstentionId": abstention_id}


def _catalog() -> dict:
    effects = {
        "declared": "direct-control", "enabled": "direct-control",
        "emitted": "indirect-coupling", "transported": "indirect-coupling",
        "retained": "indirect-coupling",
    }
    groups = [
        {
            "id": group_id, "evidenceItems": ["catalog-e"], "dependencies": [],
            "mechanism": "runtime-configuration", "locus": "process-runtime",
            "settingDomain": {"values": [True, False], "referenceValue": True, "offValue": False},
            "stageEffects": effects, "support": _support(),
        }
        for group_id in ("checkout", "catalog")
    ]
    abstentions = [
        {
            "id": f"no-{kind}", "subjectType": "microtest", "subjectId": test_id,
            "reason": f"{kind} is not independently controllable in this family",
            "evidenceItems": ["catalog-e"],
        }
        for kind, test_id in (
            ("true-source-off", "source-off"),
            ("transport-off", "transport-off"),
            ("retention-off", "retention-off"),
        )
    ]
    settings = {"checkout": True, "catalog": True}
    tests = [
        {"id": "full", "kind": "full-reference", "support": _support(),
         "settings": settings, "targetStages": _targets()},
        {"id": "source-off", "kind": "true-source-off",
         "support": _support("unsupported", "no-true-source-off"),
         "settings": {}, "targetStages": _targets()},
        {"id": "emission-off", "kind": "emission-off", "support": _support(),
         "settings": {"checkout": False, "catalog": False},
         "targetStages": _targets(emitted="off", transported="off", retained="off")},
        {"id": "transport-off", "kind": "transport-off",
         "support": _support("unsupported", "no-transport-off"),
         "settings": {}, "targetStages": _targets()},
        {"id": "retention-off", "kind": "retention-off",
         "support": _support("unsupported", "no-retention-off"),
         "settings": {}, "targetStages": _targets()},
        {"id": "perturb-checkout", "kind": "one-group-perturbation", "support": _support(),
         "settings": {"checkout": False, "catalog": True}, "targetStages": _targets(),
         "activationGroupId": "checkout", "baselineTestId": "full"},
        {"id": "perturb-catalog", "kind": "one-group-perturbation", "support": _support(),
         "settings": {"checkout": True, "catalog": False}, "targetStages": _targets(),
         "activationGroupId": "catalog", "baselineTestId": "full"},
    ]
    return {
        "$schema": "https://observability-placement.local/contracts/control-universe.schema.json",
        "schemaVersion": 1, "id": "family-controls-v1", "family": "example-family",
        "claimPolicy": {
            "phase": "control-universe-characterization",
            "completeClaimCeiling": "phase-1-structural-control-map",
            "incompleteClaimCeiling": "descriptive-only",
            "empiricalClaimsAllowed": False,
            "optimizationClaimsAllowed": False,
            "crossFamilyEquivalenceAllowed": False,
        },
        "semanticContext": {
            "contextId": "checkout-context-v1", "scenarioId": "checkout",
            "channelId": "otlp-traces", "nativeSemanticUnit": "span",
            "nativeIdentityFields": ["trace_id", "span_id"],
            "targetSet": ["frontend", "catalog"],
            "backgroundPolicy": {
                "mode": "separate", "backgroundSet": ["loadgenerator"],
                "evidenceItems": ["catalog-e"],
            },
            "completenessCriterion": "terminal stable acquisition with reconciled identities",
            "evidenceItems": ["catalog-e"],
        },
        "evidenceItems": [_evidence("catalog-e")],
        "abstentions": abstentions, "activationGroups": groups, "microtests": tests,
    }


def _observation(
    microtest_id: str,
    settings: dict[str, bool],
    counts: tuple[int, int, int, int, int],
    *,
    coupling: bool = False,
) -> dict:
    evidence_items = [
        _evidence("run-config", "configuration"),
        _evidence("run-runtime", "runtime-receipt"),
        _evidence("run-collector", "collector-output"),
        _evidence("run-backend", "backend-query"),
    ]
    for item in evidence_items:
        item["locator"] = f"evidence/{microtest_id}/{item['id']}.json"
        item["sha256"] = _digest(f"{microtest_id}:{item['id']}")
    stage_evidence = {
        "declared": ["run-config"], "enabled": ["run-runtime"],
        "emitted": ["run-runtime"], "transported": ["run-collector"],
        "retained": ["run-backend"],
    }
    stage_semantics = {
        "declared": ("activation-group", "activation-group-id", "exact", "configured-groups"),
        "enabled": ("activation-group", "activation-group-id", "exact", "configured-groups"),
        "emitted": ("span", "otlp-span-id", "trace_id+span_id", "native-spans"),
        "transported": ("span", "otlp-span-id", "trace_id+span_id", "native-spans"),
        "retained": ("span", "otlp-span-id", "trace_id+span_id", "native-spans"),
    }
    stage_rows = {
        stage: {"state": "on" if count else "off", "count": count,
                "semanticUnit": stage_semantics[stage][0],
                "identityNamespace": stage_semantics[stage][1],
                "identityPolicy": stage_semantics[stage][2],
                "denominatorKind": stage_semantics[stage][3],
                "targetScope": "target-set",
                "targetPopulation": ["frontend", "catalog"],
                "measurementPoint": f"{stage}-probe",
                "evidenceItems": stage_evidence[stage]}
        for stage, count in zip(STAGES, counts, strict=True)
    }
    transitions = []
    for source, target in TRANSITIONS:
        before, after = stage_rows[source]["count"], stage_rows[target]["count"]
        compatible = all(
            stage_rows[source][field] == stage_rows[target][field]
            for field in (
                "semanticUnit", "identityNamespace", "identityPolicy",
                "denominatorKind", "targetScope", "targetPopulation",
            )
        )
        if not compatible:
            relation = "not-comparable"
        elif after == before:
            relation = "preserved"
        elif before and after == 0:
            relation = "eliminated"
        elif after < before:
            relation = "reduced"
        else:
            relation = "amplified"
        transitions.append({"from": source, "to": target, "relation": relation,
                            "evidenceItems": ["run-runtime"]})
    couplings = ([{
        "groupIds": ["checkout", "catalog"], "stages": ["enabled", "emitted"],
        "reason": "the runtime switch changes both groups", "evidenceItems": ["run-runtime"],
    }] if coupling else [])
    perturbation_assessment = None
    if microtest_id.startswith("perturb-"):
        baseline = (2, 2, 10, 10, 10)
        changed = [stage for stage, before, after in zip(STAGES, baseline, counts, strict=True)
                   if before != after]
        perturbation_assessment = {
            "baselineObservationId": "obs-full",
            "classification": "observed-delta" if changed else "structured-no-effect",
            "changedStages": changed,
            "reason": "terminal comparison against the frozen full reference",
            "evidenceItems": ["run-runtime", "run-collector", "run-backend"],
        }
    return {
        "$schema": OBS_SCHEMA, "schemaVersion": 1,
        "id": f"obs-{microtest_id}", "controlUniverseId": "family-controls-v1",
        "microtestId": microtest_id, "terminal": True, "teardownClean": True,
        "runIdentity": {
            "frameworkCommit": COMMIT, "sutCommit": COMMIT,
            "startedAt": "2026-08-17T00:00:00Z", "endedAt": "2026-08-17T00:01:00Z",
            "artifactRoot": f"evidence/{microtest_id}",
            "artifactSha256": artifact_identity(evidence_items),
        },
        "semanticBinding": {
            "contextId": "checkout-context-v1", "scenarioId": "checkout",
            "channelId": "otlp-traces", "nativeSemanticUnit": "span",
            "nativeIdentityFields": ["trace_id", "span_id"],
            "targetSet": ["frontend", "catalog"],
            "backgroundPolicy": {
                "mode": "separate", "backgroundSet": ["loadgenerator"],
                "evidenceItems": ["run-runtime"],
            },
            "completeness": "complete",
            "evidenceItems": ["run-runtime", "run-collector", "run-backend"],
        },
        "evidenceItems": evidence_items,
        "activationSettings": settings,
        "stages": stage_rows, "transitions": transitions,
        "couplings": couplings, "blindRegions": [],
        "perturbationAssessment": perturbation_assessment,
    }


def _observations() -> list[dict]:
    return [
        _observation("full", {"checkout": True, "catalog": True}, (2, 2, 10, 10, 10)),
        _observation("emission-off", {"checkout": False, "catalog": False}, (2, 2, 0, 0, 0)),
        _observation("perturb-checkout", {"checkout": False, "catalog": True}, (2, 1, 5, 5, 5), coupling=True),
        _observation("perturb-catalog", {"checkout": True, "catalog": False}, (2, 1, 5, 5, 5)),
    ]


def test_complete_phase_one_map_preserves_ceiling_coupling_and_abstentions() -> None:
    report = evaluate_control_universe(_catalog(), _observations(), evidence_verifier=lambda item: True)

    assert report["valid"], report
    assert report["complete"], report
    assert report["claimCeiling"] == "phase-1-structural-control-map"
    assert report["policy"]["empiricalClaimsAllowed"] is False
    assert report["policy"]["optimizationClaimsAllowed"] is False
    assert report["policy"]["crossFamilyEquivalenceAllowed"] is False
    assert report["phi"]["couplingRegions"][0]["microtestId"] == "perturb-checkout"
    checkout = next(row for row in report["phi"]["activationGroups"] if row["id"] == "checkout")
    assert checkout["observedPerturbationEffects"][0]["classification"] == "observed-delta"
    assert checkout["observedPerturbationEffects"][0]["changedStages"] == [
        "enabled", "emitted", "transported", "retained",
    ]
    assert {item["microtestId"] for item in report["phi"]["blindRegions"]} == {
        "source-off", "transport-off", "retention-off",
    }


def test_missing_supported_microtest_observation_falls_back_to_descriptive_only() -> None:
    report = evaluate_control_universe(
        _catalog(), _observations()[:-1], evidence_verifier=lambda item: True,
    )

    assert report["valid"], report
    assert not report["complete"]
    assert report["claimCeiling"] == "descriptive-only"
    assert any("perturb-catalog" in blocker for blocker in report["blockers"])


def test_transition_is_recomputed_instead_of_trusted() -> None:
    observations = _observations()
    observations[0]["transitions"][0]["relation"] = "amplified"

    report = evaluate_control_universe(_catalog(), observations, evidence_verifier=lambda item: True)

    assert not report["valid"]
    assert report["claimCeiling"] == "descriptive-only"
    assert any("reconciled stage state requires" in error for error in report["errors"])


def test_target_mismatch_blocks_empirical_map_without_relabeling_observation() -> None:
    observations = _observations()
    observations[1]["stages"]["emitted"].update({"state": "on", "count": 1})
    observations[1]["transitions"][2]["relation"] = "eliminated"

    report = evaluate_control_universe(_catalog(), observations, evidence_verifier=lambda item: True)

    assert report["valid"], report
    assert not report["complete"]
    assert any("expected 'off'" in blocker for blocker in report["blockers"])


def test_one_group_microtest_cannot_hide_a_second_setting_change() -> None:
    catalog = copy.deepcopy(_catalog())
    perturbation = next(row for row in catalog["microtests"] if row["id"] == "perturb-checkout")
    perturbation["settings"]["catalog"] = False

    report = evaluate_control_universe(catalog, _observations(), evidence_verifier=lambda item: True)

    assert not report["valid"]
    assert any("must change only its named activation group" in error for error in report["errors"])


def test_full_reference_with_every_stage_off_cannot_complete() -> None:
    observations = _observations()
    observations[0] = _observation(
        "full", {"checkout": True, "catalog": True}, (0, 0, 0, 0, 0),
    )

    report = evaluate_control_universe(
        _catalog(), observations, evidence_verifier=lambda item: True,
    )

    assert not report["complete"]
    assert report["claimCeiling"] == "descriptive-only"
    assert any("full reference does not establish" in blocker for blocker in report["blockers"])


def test_unknown_pipeline_with_blind_record_stays_descriptive() -> None:
    observations = _observations()
    full = observations[0]
    for stage in STAGES:
        full["stages"][stage] = {
            "state": "unknown", "count": None,
            "evidenceItems": ["run-runtime"],
        }
    for transition in full["transitions"]:
        transition["relation"] = "indeterminate"
    full["blindRegions"] = [{
        "stages": list(STAGES), "reason": "the channel cannot expose these stages",
        "evidenceItems": ["run-runtime"], "abstentionId": None,
    }]

    report = evaluate_control_universe(
        _catalog(), observations, evidence_verifier=lambda item: True,
    )

    assert not report["complete"]
    assert report["claimCeiling"] == "descriptive-only"
    assert any("not empirically observed" in blocker for blocker in report["blockers"])


def test_enabled_dependent_group_requires_enabled_dependency() -> None:
    catalog = _catalog()
    catalog["activationGroups"][1]["dependencies"] = ["checkout"]

    report = evaluate_control_universe(
        catalog, _observations(), evidence_verifier=lambda item: True,
    )

    assert not report["valid"]
    assert any("dependent group 'catalog'" in error for error in report["errors"])


def test_dependency_cycle_is_rejected() -> None:
    catalog = _catalog()
    catalog["activationGroups"][0]["dependencies"] = ["catalog"]
    catalog["activationGroups"][1]["dependencies"] = ["checkout"]

    report = evaluate_control_universe(
        catalog, _observations(), evidence_verifier=lambda item: True,
    )

    assert not report["valid"]
    assert any("dependency cycle" in error for error in report["errors"])


def test_abstention_must_match_the_exact_subject() -> None:
    catalog = _catalog()
    catalog["abstentions"][0]["subjectId"] = "some-other-test"

    report = evaluate_control_universe(
        catalog, _observations(), evidence_verifier=lambda item: True,
    )

    assert not report["valid"]
    assert any("does not match microtest 'source-off'" in error for error in report["errors"])


def test_artifact_replay_and_end_before_start_are_rejected() -> None:
    observations = _observations()
    replay = copy.deepcopy(observations[0])
    replay["id"] = "obs-full-replay"
    observations.append(replay)
    observations[1]["runIdentity"]["endedAt"] = "2026-08-16T23:59:00Z"

    report = evaluate_control_universe(
        _catalog(), observations, evidence_verifier=lambda item: True,
    )

    assert not report["valid"]
    assert any("replays artifact" in error for error in report["errors"])
    assert any("endedAt must be after startedAt" in error for error in report["errors"])


def test_unbound_evidence_and_generic_test_evidence_cannot_complete() -> None:
    observations = _observations()
    full = observations[0]
    full["evidenceItems"].append(_evidence("run-generic", "test"))
    full["runIdentity"]["artifactSha256"] = artifact_identity(full["evidenceItems"])
    for stage in STAGES:
        full["stages"][stage]["evidenceItems"] = ["run-generic"]

    no_verifier = evaluate_control_universe(_catalog(), observations)
    failed_binding = evaluate_control_universe(
        _catalog(), observations, evidence_verifier=lambda item: False,
    )
    generic_only = evaluate_control_universe(
        _catalog(), observations, evidence_verifier=lambda item: True,
    )

    assert not no_verifier["complete"]
    assert any("no evidence_verifier" in blocker for blocker in no_verifier["blockers"])
    assert not failed_binding["complete"]
    assert any("not bound to locator and digest" in blocker for blocker in failed_binding["blockers"])
    assert not generic_only["complete"]
    assert any("generic test evidence cannot prove" in blocker for blocker in generic_only["blockers"])


def test_identical_perturbation_requires_structured_no_effect_and_is_reported() -> None:
    observations = _observations()
    observations[2] = _observation(
        "perturb-checkout", {"checkout": False, "catalog": True},
        (2, 2, 10, 10, 10),
    )
    observations[2]["perturbationAssessment"]["classification"] = "structured-no-effect"
    observations[2]["perturbationAssessment"]["changedStages"] = []

    report = evaluate_control_universe(
        _catalog(), observations, evidence_verifier=lambda item: True,
    )

    assert report["complete"], report
    checkout = next(row for row in report["phi"]["activationGroups"] if row["id"] == "checkout")
    assert checkout["observedPerturbationEffects"][0]["classification"] == "structured-no-effect"
    assert report["claimCeiling"] == "phase-1-structural-control-map"
    assert report["policy"]["empiricalClaimsAllowed"] is False


def test_semantic_context_and_completeness_are_not_inferred() -> None:
    observations = _observations()
    observations[0]["semanticBinding"]["channelId"] = "different-channel"
    observations[1]["semanticBinding"]["completeness"] = "unknown"

    report = evaluate_control_universe(
        _catalog(), observations, evidence_verifier=lambda item: True,
    )

    assert not report["valid"]
    assert not report["complete"]
    assert any("differs from the frozen context" in error for error in report["errors"])
    assert any("completeness is not terminally complete" in blocker for blocker in report["blockers"])


def test_cross_unit_transition_cannot_claim_numeric_reduction_or_amplification() -> None:
    observations = _observations()
    # enabled counts activation groups; emitted counts native spans.
    observations[0]["transitions"][1]["relation"] = "amplified"

    report = evaluate_control_universe(
        _catalog(), observations, evidence_verifier=lambda item: True,
    )

    assert not report["valid"]
    assert any("requires 'not-comparable'" in error for error in report["errors"])


def test_target_and_background_cannot_be_mixed_without_bound_include_policy() -> None:
    observations = _observations()
    stage = observations[0]["stages"]["transported"]
    stage["targetScope"] = "combined"
    stage["targetPopulation"] = ["frontend", "catalog", "loadgenerator"]
    observations[0]["semanticBinding"]["backgroundPolicy"]["evidenceItems"] = []

    report = evaluate_control_universe(
        _catalog(), observations, evidence_verifier=lambda item: True,
    )

    assert not report["valid"]
    assert any("combines target/background without an include policy" in error
               for error in report["errors"])
    assert any("backgroundPolicy.evidenceItems must not be empty" in error
               for error in report["errors"])


def test_artifact_identity_is_order_and_path_independent() -> None:
    items = [_evidence("b", "collector-output"), _evidence("a", "runtime-receipt")]
    moved = copy.deepcopy(list(reversed(items)))
    for index, item in enumerate(moved):
        item["locator"] = f"a-different/root/{index}.json"
        item["capturedAt"] = "not-recorded"
    assert artifact_identity(items) == artifact_identity(moved)
    moved[0]["sha256"] = _digest("changed bytes")
    assert artifact_identity(items) != artifact_identity(moved)


def test_retained_accepts_collector_output_but_not_a_derived_test_alone() -> None:
    observations = _observations()
    full = observations[0]
    full["stages"]["retained"]["evidenceItems"] = ["run-collector"]
    raw = evaluate_control_universe(_catalog(), observations, evidence_verifier=lambda item: True)
    assert raw["complete"], raw
    full["stages"]["retained"]["evidenceItems"] = ["run-backend"]
    next(item for item in full["evidenceItems"] if item["id"] == "run-backend")["kind"] = "test"
    derived = evaluate_control_universe(
        _catalog(), observations, evidence_verifier=lambda item: True)
    assert derived["valid"], derived
    assert not derived["complete"]
    assert any("generic test evidence cannot prove 'retained'" in item
               for item in derived["blockers"])


def test_evidence_paths_cannot_be_absolute_or_escape_the_supplied_root() -> None:
    observations = _observations()
    observations[0]["evidenceItems"][0]["locator"] = "/tmp/outside.json"
    observations[1]["evidenceItems"][0]["locator"] = "../outside.json"
    observations[2]["runIdentity"]["artifactRoot"] = "C:\\outside"
    report = evaluate_control_universe(
        _catalog(), observations, evidence_verifier=lambda item: True)
    assert not report["valid"]
    assert sum("evidence-root-relative" in item for item in report["errors"]) >= 3
