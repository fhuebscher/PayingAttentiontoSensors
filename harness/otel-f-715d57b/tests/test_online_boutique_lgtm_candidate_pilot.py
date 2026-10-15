import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = (
    ROOT
    / "modules"
    / "online-boutique-lgtm"
    / "validation"
    / "candidate_pilot.py"
)
DESCRIPTOR = (
    ROOT
    / "pipelines"
    / "campaigns"
    / "online-boutique-aws-eks-candidate-pilot-v1.json"
)
SPEC = importlib.util.spec_from_file_location("ob_lgtm_candidate_pilot", MODULE)
candidate_pilot = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(candidate_pilot)


def descriptor():
    return json.loads(DESCRIPTOR.read_text())


def canonical_digest(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def test_frozen_descriptor_reproduces_exact_construction_contract():
    document = descriptor()
    assert candidate_pilot.validate_contract(document) == document
    assert candidate_pilot.build_contract() == document
    assert candidate_pilot.load_descriptor() == document
    assert candidate_pilot.canonical_sha256(document) == (
        candidate_pilot.EXPECTED_DESCRIPTOR_SHA256
    )
    assert document["status"] == "construction-only"
    assert document["design"]["totalRuns"] == 18

    schedules = document["randomization"]["schedule"]
    assert [row["regime"] for row in schedules] == list(candidate_pilot.REGIMES)
    assert len({row["selectorSha256"] for row in schedules}) == 2
    for schedule in schedules:
        assert schedule["scheduleSha256"] == canonical_digest(schedule["blocks"])
        assert [row["block"] for row in schedule["blocks"]] == [1, 2, 3]
        assert all(
            sorted(row["order"]) == sorted(candidate_pilot.POSTURES)
            for row in schedule["blocks"]
        )
        for position in range(3):
            assert sorted(
                row["order"][position] for row in schedule["blocks"]
            ) == sorted(candidate_pilot.POSTURES)


def test_cost_and_fault_effect_windows_are_disjoint_and_typed():
    document = descriptor()
    cost, effect = document["design"]["regimes"]
    assert cost["id"] == "no-fault-cost"
    assert cost["fault"] is None
    assert cost["costProjectionAllowed"] is True
    assert all(window["faultAllowed"] is False for window in cost["windows"])
    assert effect["id"] == "productcatalog-scale-zero-effect"
    assert effect["fault"] == "productcatalog-kubernetes-scale-zero"
    assert effect["costProjectionAllowed"] is False
    assert [
        window["id"]
        for window in effect["windows"]
        if window["faultAllowed"] and window["scored"]
    ] == ["fault-effect"]
    assert next(
        window for window in effect["windows"] if window["id"] == "fault-effect"
    )["startsWhen"] == "five-consecutive-zero-ready-samples"
    assert next(
        window
        for window in effect["windows"]
        if window["id"] == "post-recovery-effect"
    )["startsWhen"] == "same-deployment-ready-and-independent-probe-success"
    assert document["design"]["costAndEffectPoolable"] is False
    assert document["design"]["artifactRootsDisjoint"] is True


def test_compiler_emits_18_immutable_non_authorized_cells():
    plan = candidate_pilot.compile_plan(descriptor())
    assert plan == candidate_pilot.compile_plan(descriptor())
    assert plan["status"] == "abstain"
    assert plan["runtimeAuthorized"] is False
    assert plan["runCount"] == len(plan["runs"]) == 18
    assert plan["runsSha256"] == canonical_digest(plan["runs"])
    assert len({run["runId"] for run in plan["runs"]}) == 18
    assert all(run["targetEnvironment"] == "aws-eks" for run in plan["runs"])
    assert all(run["channel"] == "aws-eks-lgtm" for run in plan["runs"])
    assert all(run["runtimeAuthorized"] is False for run in plan["runs"])
    for regime in candidate_pilot.REGIMES:
        cells = [run for run in plan["runs"] if run["regime"] == regime]
        assert len(cells) == 9
        for block in (1, 2, 3):
            block_cells = [run for run in cells if run["block"] == block]
            assert sorted(run["posture"] for run in block_cells) == sorted(
                candidate_pilot.POSTURES
            )


def test_workload_and_denominators_are_frozen_before_outcomes():
    workload = descriptor()["workload"]
    assert workload["correlationAdapterStatus"] == "not-implemented"
    assert workload["method"] == "GET" and workload["path"] == "/"
    assert workload["ratePerSecond"] == 1
    assert workload["concurrency"] == 4
    assert workload["timeoutSeconds"] == 15
    assert workload["retryCount"] == 0
    assert workload["phaseSchedules"] == {
        "warmup": 120,
        "cost-measurement": 600,
        "pre-fault-effect": 180,
        "fault-effect": 120,
        "post-recovery-effect": 180,
    }
    assert workload["exactOfferedCountRequired"] is True
    assert workload["terminalReconciliation"][
        "traceparentMustMatchTraceIdAndSentParentSpanId"
    ] is True
    assert workload["terminalReconciliation"][
        "oneOpportunityAndOneOutcomePerOrdinal"
    ] is True


def test_request_fault_and_path_truth_are_independent_and_fail_closed():
    truth = descriptor()["groundTruth"]
    opportunity = truth["requestOpportunity"]
    assert opportunity["independentOfTelemetryBackend"] is True
    assert opportunity["createdBeforeTelemetryQuery"] is True
    assert {"traceparent", "traceId", "sentParentSpanId", "traceparentSha256"} <= set(
        opportunity["requiredFields"]
    )
    assert opportunity["expectedOpportunityIsExecutionProof"] is False
    assert opportunity["missingReceiptState"] == "unsupported"

    fault = truth["fault"]
    assert fault["independentOfTempoAndLoki"] is True
    assert fault["commandSuccessAloneEstablishesTruth"] is False
    assert fault["missingManifestationOrRecovery"] == "invalid-and-safety-stop"
    assert fault["phaseAssignmentSource"] == (
        "observed-state-barriers-not-nominal-offsets"
    )
    assert fault["stateSampleCadenceSeconds"] == 1
    assert fault["requiredConsecutiveZeroReadySamples"] == 5

    path = truth["path"]
    assert path["opportunityJoin"] == "exact-client-issued-trace-id"
    assert path["sameTraceRequired"] is True
    assert path["directParentRequired"] is True
    assert path["rootParentEqualsSentParentSpanId"] is True
    assert path["crossTraceAssemblyAllowed"] is False
    assert path["missingOpportunityOrTraceState"] == "unsupported"
    assert path["numericMissingValue"] is None
    assert path["postureOutcomeClassification"]["none"][
        "missingOpportunityOrAcquisitionState"
    ] == "unsupported"
    assert "zero-target-source-spans-for-issued-trace-id" in path[
        "postureOutcomeClassification"
    ]["none"]["validZeroRequires"]
    assert path["postureOutcomeClassification"]["selected"][
        "completeAcquisitionMissingRequiredPathValue"
    ] == 0


def test_source_bindings_replay_current_exact_bytes():
    document = descriptor()
    assert candidate_pilot.source_binding_errors(document) == []
    assert {row["role"] for row in document["source"]["bindings"]} >= {
        "deployment-source-pin",
        "shared-goal",
        "shared-activation-catalog",
        "workload-prior-art-requiring-correlation-adapter",
        "none-posture",
        "selected-posture",
        "full-posture",
    }


def test_actual_eks_is_typed_and_kind_can_never_substitute():
    target = descriptor()["targetEnvironment"]
    assert target["id"] == "aws-eks"
    assert target["kind"] == "managed-cloud-kubernetes"
    assert target["executorStatus"] == "not-implemented"
    assert target["aliasesAccepted"] == []
    assert target["kindReference"]["maySubstituteForTarget"] is False
    assert target["kindReference"]["mayProveTarget"] is False
    assert "emailservice-selector-does-not-match-deployment" in target[
        "knownImplementationBlockers"
    ]


def test_cost_ownership_and_cleanup_claims_require_receipts():
    document = descriptor()
    cost = document["cost"]
    assert cost["eligibleRegime"] == "no-fault-cost"
    assert cost["windowMembership"] == "cost-measurement"
    assert cost["collectorTailExcluded"] is True
    assert cost["effectResourcesAreCostEstimates"] is False
    assert cost["billedAwsCostRequiresLaterTagScopedBillingEvidence"] is True
    assert cost["implementationStatus"] == "not-implemented"
    assert cost["currentOutcomeState"] == "unsupported"
    assert cost["resourceSampling"]["missingOrDuplicateSampleState"] == "unsupported"

    ownership = document["ownership"]
    assert ownership["ownerTokenRequired"] is True
    assert ownership["implementationStatus"] == "not-implemented"
    assert ownership["deletionActionsAuthorized"] is False
    assert ownership["clusterLifetime"] == "one-cluster-per-complete-18-cell-campaign"
    assert ownership["authorizedDeletionKinds"] == []
    assert ownership["terraformStateDisposition"] == (
        "retain-content-addressed-audit-evidence"
    )
    assert ownership["baselineOrForeignDeletionAllowed"] is False
    assert ownership["wholeAccountCleanupAllowed"] is False
    assert ownership["wholeRegionCleanupAllowed"] is False
    assert ownership["unknownOwnershipAction"] == "abstain-without-deletion"

    cleanup = document["cleanup"]
    assert cleanup["implementationStatus"] == "not-implemented"
    assert cleanup["actionsAuthorized"] is False
    assert cleanup["runsOnSuccessFailureAndCancellation"] is True
    assert cleanup["joinsWorkloadCollectorAndInterventionBeforeDeletion"] is True
    assert cleanup["deletesOnlyExactOwnedIdentities"] is True
    assert cleanup["verifiesAbsenceByIndependentPostInventory"] is True
    assert cleanup["cleanupFailureInvalidatesRun"] is True
    assert cleanup["cleanupFailureStopsCampaign"] is True

    replication = document["replication"]
    assert replication["sameFamilyAs"] == [
        "compose-native-otel",
        "kind-lgtm-tempo-loki",
    ]
    assert replication["applicationFamilyCountContribution"] == 0
    assert replication["currentChannelStratumCountContribution"] == 0
    assert replication["futureValidCandidateChannelStratumContribution"] == 1


def test_readiness_abstains_without_executor_cloud_pins_or_gate():
    document = descriptor()
    plan = candidate_pilot.compile_plan(document)
    report = candidate_pilot.readiness_report(document, plan)
    assert report["verdict"] == "abstain"
    assert report["runtimeAuthorized"] is False
    assert report["evidenceLabel"] == "method-design-only"
    assert {row["id"] for row in report["checks"] if row["status"] == "blocked"} == {
        "aws-eks-executor",
        "request-trace-correlation",
        "aws-ownership-cost-cleanup",
        "immutable-cloud-inputs",
        "human-runtime-gate",
    }
    assert report["contractSha256"] == canonical_digest(descriptor())
    assert report["plannedRuns"] == 18


def test_readiness_recomputes_and_rejects_a_forged_compiled_plan():
    document = descriptor()
    plan = candidate_pilot.compile_plan(document)
    plan["runs"][0]["posture"] = "not-a-posture"
    plan["runsSha256"] = canonical_digest(plan["runs"])
    report = candidate_pilot.readiness_report(document, plan)
    assert report["verdict"] == "blocked"
    assert report["runtimeAuthorized"] is False
    assert report["checks"] == [
        {
            "id": "plan-drift",
            "status": "failed",
            "detail": "supplied plan differs from deterministic compilation",
        }
    ]


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("runtimeAuthorized",), 0),
        (("runCount",), 18.0),
        (("runs", 0, "attempt"), True),
        (("runs", 0, "block"), True),
        (("runs", 0, "windows", 0, "seconds"), 120.0),
    ],
    ids=[
        "runtime-false-as-int-zero",
        "run-count-int-as-float",
        "attempt-int-as-bool",
        "block-int-as-bool",
        "window-seconds-int-as-float",
    ],
)
def test_readiness_rejects_type_confused_compiled_plan(path, replacement):
    document = descriptor()
    plan = candidate_pilot.compile_plan(document)
    cursor = plan
    for component in path[:-1]:
        cursor = cursor[component]
    original = cursor[path[-1]]
    assert original == replacement
    assert type(original) is not type(replacement)
    cursor[path[-1]] = replacement

    report = candidate_pilot.readiness_report(document, plan)
    assert report["verdict"] == "blocked"
    assert report["runtimeAuthorized"] is False
    assert report["evidenceLabel"] == "none"
    assert report["checks"] == [
        {
            "id": "plan-drift",
            "status": "failed",
            "detail": "supplied plan differs from deterministic compilation",
        }
    ]


def _environment_alias(document):
    document["targetEnvironment"]["id"] = "eks"


def _kind_alias(document):
    document["targetEnvironment"]["id"] = "kind"


def _accepted_alias(document):
    document["targetEnvironment"]["aliasesAccepted"] = ["eks"]


def _schedule_drift(document):
    schedule = document["randomization"]["schedule"][0]
    schedule["blocks"][0]["order"][:2] = reversed(
        schedule["blocks"][0]["order"][:2]
    )
    schedule["scheduleSha256"] = canonical_digest(schedule["blocks"])


def _position_imbalance(document):
    schedule = document["randomization"]["schedule"][0]
    first = schedule["blocks"][0]["order"]
    for block in schedule["blocks"]:
        block["order"] = list(first)
    schedule["scheduleSha256"] = canonical_digest(schedule["blocks"])


def _cost_window_drift(document):
    document["design"]["regimes"][0]["windows"][1]["faultAllowed"] = True


def _effect_window_drift(document):
    document["design"]["regimes"][1]["artifactRoot"] = "cost"


def _nominal_fault_phase(document):
    document["groundTruth"]["fault"]["phaseAssignmentSource"] = "nominal-offsets"


def _none_missing_as_zero(document):
    document["groundTruth"]["path"]["postureOutcomeClassification"]["none"][
        "missingOpportunityOrAcquisitionState"
    ] = "zero"


def _missing_trace_opportunity(document):
    document["groundTruth"]["requestOpportunity"]["requiredFields"].remove(
        "traceId"
    )


def _expected_is_execution(document):
    document["groundTruth"]["requestOpportunity"][
        "expectedOpportunityIsExecutionProof"
    ] = True


def _workload_retry(document):
    document["workload"]["retryCount"] = 1


def _workload_denominator_drift(document):
    document["workload"]["phaseSchedules"]["cost-measurement"] = 599


def _source_binding_drift(document):
    document["source"]["bindings"][2]["sha256"] = "0" * 64


def _mutable_head(document):
    document["cloudInputs"]["pinnedConstructionInputs"][
        "deploymentCommit"
    ] = "HEAD"


def _floating_cloud_policy(document):
    document["cloudInputs"]["forbidFloatingRefs"] = False


def _known_blocker_removed(document):
    document["targetEnvironment"]["knownImplementationBlockers"].remove(
        "emailservice-selector-does-not-match-deployment"
    )


def _self_authorize(document):
    document["governance"]["runtimeAuthorized"] = True


def _effect_as_cost(document):
    document["cost"]["effectResourcesAreCostEstimates"] = True


def _whole_account_cleanup(document):
    document["ownership"]["wholeAccountCleanupAllowed"] = True


def _cleanup_failure_allowed(document):
    document["cleanup"]["cleanupFailureInvalidatesRun"] = False


def _same_family_claim(document):
    document["replication"]["independentApplicationReplication"] = True


def _family_count_inflation(document):
    document["replication"]["applicationFamilyCountContribution"] = 1


def _current_channel_count_inflation(document):
    document["replication"]["currentChannelStratumCountContribution"] = 1


@pytest.mark.parametrize(
    ("plant", "expected_code"),
    [
        (_environment_alias, "environment-alias"),
        (_kind_alias, "environment-alias"),
        (_accepted_alias, "environment-alias"),
        (_schedule_drift, "schedule-drift"),
        (_position_imbalance, "schedule-drift"),
        (_cost_window_drift, "window-drift"),
        (_effect_window_drift, "window-drift"),
        (_nominal_fault_phase, "trace-opportunity-truth"),
        (_none_missing_as_zero, "trace-opportunity-truth"),
        (_missing_trace_opportunity, "trace-opportunity-truth"),
        (_expected_is_execution, "trace-opportunity-truth"),
        (_workload_retry, "workload-denominator"),
        (_workload_denominator_drift, "workload-denominator"),
        (_source_binding_drift, "source-bindings"),
        (_mutable_head, "mutable-cloud-input"),
        (_floating_cloud_policy, "mutable-cloud-input"),
        (_known_blocker_removed, "environment-alias"),
        (_self_authorize, "gate-boundary"),
        (_effect_as_cost, "cost-boundary"),
        (_whole_account_cleanup, "ownership-cleanup"),
        (_cleanup_failure_allowed, "ownership-cleanup"),
        (_same_family_claim, "same-family-inflation"),
        (_family_count_inflation, "same-family-inflation"),
        (_current_channel_count_inflation, "same-family-inflation"),
    ],
    ids=[
        "eks-alias",
        "kind-substitution",
        "accepted-alias",
        "coordinated-schedule-drift",
        "position-imbalance",
        "fault-in-cost-window",
        "cost-effect-root-alias",
        "nominal-fault-phase",
        "none-missing-as-zero",
        "missing-trace-opportunity",
        "offered-is-executed",
        "workload-retry",
        "workload-denominator-drift",
        "source-binding-drift",
        "head-cloud-input",
        "floating-cloud-policy",
        "known-blocker-removal",
        "self-authorized-runtime",
        "effect-resource-cost",
        "whole-account-cleanup",
        "cleanup-failure-ignored",
        "independent-family-claim",
        "family-count-inflation",
        "current-channel-count-inflation",
    ],
)
def test_required_planted_defects_are_watched_failing(plant, expected_code):
    document = copy.deepcopy(descriptor())
    plant(document)
    with pytest.raises(candidate_pilot.ProtocolError) as caught:
        candidate_pilot.validate_contract(document)
    assert caught.value.code == expected_code
    report = candidate_pilot.readiness(document)
    assert report["verdict"] == "blocked"
    assert report["runtimeAuthorized"] is False
    assert report["checks"][0]["id"] == expected_code


def test_unknown_contract_extension_requires_a_new_epoch():
    document = descriptor()
    document["helpfulRuntimeOverride"] = True
    with pytest.raises(candidate_pilot.ProtocolError) as caught:
        candidate_pilot.validate_contract(document)
    assert caught.value.code == "contract-drift"


def test_nested_contract_objects_are_closed():
    document = descriptor()
    document["workload"]["helpfulRuntimeOverride"] = False
    with pytest.raises(candidate_pilot.ProtocolError) as caught:
        candidate_pilot.validate_contract(document)
    assert caught.value.code == "workload-denominator"


@pytest.mark.parametrize(
    ("section", "field", "value", "expected_code"),
    [
        ("workload", "ratePerSecond", True, "workload-denominator"),
        ("workload", "ratePerSecond", 1.0, "workload-denominator"),
        ("workload", "ratePerSecond", "1", "workload-denominator"),
        ("workload", "ratePerSecond", "true", "workload-denominator"),
        ("workload", "exactOfferedCountRequired", 1, "workload-denominator"),
        ("workload", "exactOfferedCountRequired", 1.0, "workload-denominator"),
        (
            "workload",
            "exactOfferedCountRequired",
            "1",
            "workload-denominator",
        ),
        (
            "workload",
            "exactOfferedCountRequired",
            "true",
            "workload-denominator",
        ),
        ("governance", "runtimeAuthorized", 0, "gate-boundary"),
        ("governance", "runtimeAuthorized", 0.0, "gate-boundary"),
        ("governance", "runtimeAuthorized", 1, "gate-boundary"),
        ("governance", "runtimeAuthorized", 1.0, "gate-boundary"),
        ("governance", "runtimeAuthorized", "1", "gate-boundary"),
        ("governance", "runtimeAuthorized", "false", "gate-boundary"),
        ("governance", "runtimeAuthorized", "true", "gate-boundary"),
    ],
    ids=[
        "rate-bool-true",
        "rate-float-one",
        "rate-string-one",
        "rate-string-true",
        "exact-count-int-one",
        "exact-count-float-one",
        "exact-count-string-one",
        "exact-count-string-true",
        "runtime-int-zero",
        "runtime-float-zero",
        "runtime-int-one",
        "runtime-float-one",
        "runtime-string-one",
        "runtime-string-false",
        "runtime-string-true",
    ],
)
def test_json_type_confusion_fails_closed_through_every_public_path(
    tmp_path, section, field, value, expected_code
):
    document = descriptor()
    document[section][field] = value
    assert candidate_pilot.canonical_sha256(document) != (
        candidate_pilot.EXPECTED_DESCRIPTOR_SHA256
    )

    for operation in (
        candidate_pilot.validate_contract,
        candidate_pilot.compile_plan,
    ):
        with pytest.raises(candidate_pilot.ProtocolError) as caught:
            operation(copy.deepcopy(document))
        assert caught.value.code == expected_code

    for operation in (
        candidate_pilot.readiness_report,
        candidate_pilot.readiness,
    ):
        report = operation(copy.deepcopy(document))
        assert report["verdict"] == "blocked"
        assert report["runtimeAuthorized"] is False
        assert report["checks"][0]["id"] == expected_code

    path = tmp_path / "contract.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    for operation in (
        candidate_pilot.load_descriptor,
        candidate_pilot.load_contract,
    ):
        with pytest.raises(candidate_pilot.ProtocolError) as caught:
            operation(path)
        assert caught.value.code == expected_code


@pytest.mark.parametrize(
    "plant",
    [
        lambda text: text.replace(
            "{", '{"schemaVersion": 1,', 1
        ),
        lambda text: text.replace(
            '"schemaVersion": 1', '"schemaVersion": NaN', 1
        ),
    ],
    ids=["duplicate-key", "non-finite-number"],
)
def test_strict_json_reader_rejects_ambiguous_or_nonstandard_json(tmp_path, plant):
    path = tmp_path / "contract.json"
    path.write_text(plant(DESCRIPTOR.read_text()))
    with pytest.raises(candidate_pilot.ProtocolError) as caught:
        candidate_pilot.load_contract(path)
    assert caught.value.code == "contract-read"


def test_validator_has_no_runtime_or_network_import_surface():
    tree = ast.parse(MODULE.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(
        {"boto3", "botocore", "docker", "kubernetes", "socket", "subprocess"}
    )


def test_cli_returns_nonzero_for_intentional_runtime_abstention(capsys):
    assert candidate_pilot.main([str(DESCRIPTOR)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["verdict"] == "abstain"
    assert report["runtimeAuthorized"] is False
