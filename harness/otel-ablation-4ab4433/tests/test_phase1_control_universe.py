"""Fail closed when the Phase 1 control map becomes stale or overclaims controls."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


binding_checker = _load(
    "phase1_control_universe_binding_checker",
    "tools/validate_phase1_control_universe_binding.py",
)
MATRIX = ROOT / "research" / "phase1-control-universe.json"
PLAN = ROOT / "research" / "phase1-control-microtests.json"
READINESS = ROOT / "research" / "five-module-readiness.json"
CHARACTERIZATION = (
    ROOT
    / "research"
    / "phase1-characterizations"
    / "online-boutique-compose-frontend-239e306-20260817.json"
)
STATUSES = {"tested", "transitively-covered", "unsupported", "deferred"}
CONTROLS = {
    "full-reference",
    "true-source-off",
    "emission-off",
    "transport-off",
    "retention-off",
}
STAGES = ["declared", "enabled", "emitted", "transported", "retained"]
CEILING = "noncanonical-functional-characterization"
CONTROL_ORIGINS = {"upstream-native", "existing-adapter-guard", "research-added"}

# The externally sealed Online Boutique Compose frontend Phase 1 cell. Every
# value below is transcribed from the sealed archive and must never drift.
OB_FRAMEWORK_COMMIT = "239e3068b264560e990298ebd40ddd4821674dee"
OB_UPSTREAM_COMMIT = "9a4616e77f0f9cbcbecaf27d711c38890dda1404"
OB_ARCHIVE_SHA256 = (
    "08a80d5f53b5eb0dec97ab0100f31815987919151c7a09b6871e742f8281c3e9"
)
OB_EVIDENCE_CONTENT_SHA256 = (
    "68d24db18916f8c481a4b3b36ebf331725f74cb8f9c8f11b142cd060894fbefb"
)
OB_EVIDENCE_MANIFEST_FILE_SHA256 = (
    "eb7ccd280a6a11b2f29d6ef550a20502a9300e3174934990bc9225580279164f"
)
OB_MANIFEST_FILE_COUNT = 86
# posture -> (in-window target spans, total carrier spans)
OB_POSTURE_COUNTS = {
    "full-reference": (762, 766),
    "frontend-off": (336, 338),
    "source-off": (0, 0),
}
OB_IN_WINDOW_SERVICE_COUNTS = {
    "full-reference": {
        "frontend": 426,
        "currencyservice": 300,
        "productcatalogservice": 36,
    },
    "frontend-off": {
        "frontend": 0,
        "currencyservice": 300,
        "productcatalogservice": 36,
    },
    "source-off": {
        "frontend": 0,
        "currencyservice": 0,
        "productcatalogservice": 0,
    },
}
OB_UNSUPPORTED_STAGES = {"emitted", "transported"}
OB_HELD_SIBLING_GROUPS = {
    "productcatalog-source-tracing",
    "currency-source-tracing",
}
OB_TESTED_STAGES = {"declared", "enabled", "retained"}
OB_RUNTIME_BINDING_IDS = {
    "ob-compose-frontend-239e306-declared",
    "ob-compose-frontend-239e306-enabled",
    "ob-compose-frontend-239e306-retained",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def by_module(document: dict) -> dict[str, dict]:
    rows = document["modules"]
    result = {row["module"]: row for row in rows}
    assert len(result) == len(rows), "duplicate module row"
    return result


def test_matrix_is_bound_to_current_authoritative_sources() -> None:
    matrix = load(MATRIX)
    bindings = matrix["sourceBindings"]
    assert len({row["id"] for row in bindings}) == len(bindings)
    for binding in bindings:
        path = ROOT / binding["path"]
        assert path.is_file() and not path.is_symlink(), binding
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"], binding
    runtime = matrix["runtimeEvidenceBindings"]
    assert len({row["id"] for row in runtime}) == len(runtime)
    for binding in runtime:
        path = ROOT / binding["path"]
        assert binding["stage"] in STAGES, binding
        assert path.is_file() and not path.is_symlink(), binding
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"], binding


def _synthetic_reader(files: dict[str, bytes]):
    return lambda relative: files.get(relative)


def _matrix_with(paths: dict[str, str]) -> bytes:
    document = json.loads(MATRIX.read_text(encoding="utf-8"))
    for _, binding in binding_checker.iter_bindings(document):
        if binding["path"] in paths:
            binding["sha256"] = paths[binding["path"]]
    return json.dumps(document).encode("utf-8")


def test_binding_checker_enumerates_every_bound_path_in_the_matrix() -> None:
    # Guards against the checker being narrowed to one module's entry: it must see
    # exactly the same population the digest test walks.
    document = json.loads(MATRIX.read_text(encoding="utf-8"))
    walked = {binding["path"] for _, binding in binding_checker.iter_bindings(document)}
    declared = {
        row["path"]
        for key in ("sourceBindings", "runtimeEvidenceBindings")
        for row in document[key]
    }
    assert walked == declared
    assert len(list(binding_checker.iter_bindings(document))) == (
        len(document["sourceBindings"]) + len(document["runtimeEvidenceBindings"])
    )


def test_binding_checker_accepts_an_atomic_commit() -> None:
    # Both the materializer and the matrix that records its digest are present with
    # agreeing bytes: this is what a correct commit looks like.
    document = json.loads(MATRIX.read_text(encoding="utf-8"))
    files = {
        binding["path"]: (ROOT / binding["path"]).read_bytes()
        for _, binding in binding_checker.iter_bindings(document)
    }
    assert binding_checker.evaluate(
        MATRIX.read_bytes(), _synthetic_reader(files)
    ) == []


def test_binding_checker_rejects_a_split_commit_of_the_otel_materializer() -> None:
    # The exact hazard: the materializer's bytes move but the matrix that records
    # their digest does not (or the reverse). Either way the binding is a lie and the
    # commit must be blocked.
    document = json.loads(MATRIX.read_text(encoding="utf-8"))
    files = {
        binding["path"]: (ROOT / binding["path"]).read_bytes()
        for _, binding in binding_checker.iter_bindings(document)
    }
    files["modules/otel-demo/materialize.py"] = b"# a different materializer\n"
    problems = binding_checker.evaluate(MATRIX.read_bytes(), _synthetic_reader(files))
    assert len(problems) == 1
    assert "modules/otel-demo/materialize.py" in problems[0]
    assert "research/phase1-control-universe.json" in problems[0]

    stale_matrix = _matrix_with({"modules/otel-demo/materialize.py": "0" * 64})
    problems = binding_checker.evaluate(stale_matrix, _synthetic_reader(files))
    assert len(problems) == 1
    assert "modules/otel-demo/materialize.py" in problems[0]


def test_binding_checker_reports_every_disagreement_not_just_the_first() -> None:
    document = json.loads(MATRIX.read_text(encoding="utf-8"))
    files = {
        binding["path"]: (ROOT / binding["path"]).read_bytes()
        for _, binding in binding_checker.iter_bindings(document)
    }
    stale_matrix = _matrix_with({
        "modules/otel-demo/materialize.py": "0" * 64,
        "modules/otel-demo/README.md": "1" * 64,
    })
    problems = binding_checker.evaluate(stale_matrix, _synthetic_reader(files))
    assert len(problems) == 2


def test_binding_checker_rejects_an_absent_bound_file() -> None:
    document = json.loads(MATRIX.read_text(encoding="utf-8"))
    files = {
        binding["path"]: (ROOT / binding["path"]).read_bytes()
        for _, binding in binding_checker.iter_bindings(document)
    }
    del files["modules/otel-demo/materialize.py"]
    problems = binding_checker.evaluate(MATRIX.read_bytes(), _synthetic_reader(files))
    assert problems == [
        "$.sourceBindings[8] modules/otel-demo/materialize.py: bound file is absent"
    ]


def test_binding_checker_worktree_mode_agrees_with_the_digest_test() -> None:
    assert binding_checker.main(["--root", str(ROOT)]) == 0


def test_matrix_covers_authoritative_module_and_family_universe() -> None:
    matrix = load(MATRIX)
    readiness = load(READINESS)
    actual = by_module(matrix)
    expected = {row["module"]: row for row in readiness["modules"]}
    assert set(actual) == set(expected)
    assert len(actual) == readiness["scope"]["moduleCount"] == 5
    assert len({row["applicationFamily"] for row in actual.values()}) == (
        readiness["scope"]["applicationFamilyCount"]
    ) == 4
    for module, row in actual.items():
        assert row["applicationFamily"] == expected[module]["applicationFamily"]
        assert row["channel"] == expected[module]["channel"]


def test_every_module_has_explicit_controls_groups_and_stage_reconciliation() -> None:
    matrix = load(MATRIX)
    binding_ids = {row["id"] for row in matrix["sourceBindings"]}
    runtime_binding_ids = {row["id"] for row in matrix["runtimeEvidenceBindings"]}
    assert matrix["qualificationCeiling"] == CEILING
    assert matrix["planningOnly"] is True
    assert set(matrix["controlOriginVocabulary"]) == CONTROL_ORIGINS
    assert matrix["locatorPolicy"]["verification"] == "source-file-sha256-only"
    assert "goal-sufficiency" in matrix["outOfScope"]
    assert "does not decide" in matrix["goalSufficiencyPolicy"]
    assert matrix["stageVocabulary"] == STAGES
    for row in matrix["modules"]:
        controls = {item["controlId"]: item for item in row["controls"]}
        assert set(controls) == CONTROLS
        assert all(item["controlOrigin"] in CONTROL_ORIGINS for item in controls.values())
        assert row["activationGroups"], row["module"]
        assert row["blindRegions"], row["module"]
        assert row["coupling"], row["module"]
        for item in [*row["controls"], *row["activationGroups"], *row["reconciliation"]["stages"]]:
            assert item["status"] in STATUSES, item
            assert item["evidenceRefs"], item
            for reference in item["evidenceRefs"]:
                source_id = reference.get("sourceBindingId")
                runtime_id = reference.get("runtimeEvidenceBindingId")
                assert (source_id is None) != (runtime_id is None), reference
                if source_id is not None:
                    assert source_id in binding_ids, reference
                else:
                    assert runtime_id in runtime_binding_ids, reference
                assert reference["locator"], reference
        stages = row["reconciliation"]["stages"]
        assert [stage["stage"] for stage in stages] == STAGES
        assert row["reconciliation"]["exactVectorStatus"] in STATUSES


def test_tested_stage_requires_direct_stage_appropriate_runtime_artifact() -> None:
    matrix = load(MATRIX)
    runtime = {row["id"]: row for row in matrix["runtimeEvidenceBindings"]}
    for module in matrix["modules"]:
        for stage in module["reconciliation"]["stages"]:
            if stage["status"] != "tested":
                continue
            direct = [
                runtime[reference["runtimeEvidenceBindingId"]]
                for reference in stage["evidenceRefs"]
                if reference.get("runtimeEvidenceBindingId") in runtime
            ]
            assert direct, (module["module"], stage["stage"])
            assert any(
                binding["module"] == module["module"]
                and binding["stage"] == stage["stage"]
                for binding in direct
            ), (module["module"], stage["stage"], direct)


def test_source_off_is_never_inferred_from_another_layer() -> None:
    matrix = load(MATRIX)
    for row in matrix["modules"]:
        source_off = next(
            item for item in row["controls"] if item["controlId"] == "true-source-off"
        )
        if source_off["status"] in {"tested", "transitively-covered"}:
            assert source_off["sourceWorkDisabled"] is True, row["module"]
            assert source_off["claimScope"] in {"targeted", "global"}, row["module"]
        else:
            assert source_off["sourceWorkDisabled"] is False, row["module"]
        for control in row["controls"]:
            if control["controlId"] in {"emission-off", "transport-off", "retention-off"}:
                assert control["sourceWorkDisabled"] is False, (row["module"], control)


def test_microtest_plan_matches_matrix_without_promotion() -> None:
    matrix = by_module(load(MATRIX))
    plan_document = load(PLAN)
    plan = by_module(plan_document)
    assert set(plan) == set(matrix)
    assert plan_document["matrix"] == "research/phase1-control-universe.json"
    assert plan_document["qualificationCeiling"] == CEILING
    assert plan_document["registersAsEvidence"] is False
    assert [row["stage"] for row in plan_document["commonProtocol"]["requiredStageRecord"]] == STAGES
    for module, row in plan.items():
        controls = {item["controlId"]: item for item in row["controlMicrotests"]}
        matrix_controls = {item["controlId"]: item for item in matrix[module]["controls"]}
        assert set(controls) == CONTROLS
        for control_id, item in controls.items():
            assert item["status"] == matrix_controls[control_id]["status"]
            assert item["phase1Disposition"]
            assert item["assertion"]
        groups = {item["activationGroup"]: item for item in row["oneGroupPerturbations"]}
        matrix_groups = {item["id"]: item for item in matrix[module]["activationGroups"]}
        assert set(groups) == set(matrix_groups)
        for group_id, item in groups.items():
            assert item["status"] == matrix_groups[group_id]["status"]
            assert item["phase1Disposition"]


def ob_module(document: dict) -> dict:
    return by_module(document)["online-boutique"]


def test_characterization_record_binds_exact_sealed_digests_and_identities() -> None:
    record = load(CHARACTERIZATION)
    assert record["qualificationCeiling"] == CEILING
    assert record["module"] == "online-boutique"
    assert record["cell"] == "frontend-source-tracing"

    identities = record["identities"]
    assert identities["frameworkCommit"] == OB_FRAMEWORK_COMMIT
    assert identities["frameworkDirty"] is False
    assert identities["upstreamCommit"] == OB_UPSTREAM_COMMIT
    assert identities["upstreamCheckoutClean"] is True

    digests = record["digests"]
    assert digests["archiveSha256"] == OB_ARCHIVE_SHA256
    assert digests["evidenceContentSha256"] == OB_EVIDENCE_CONTENT_SHA256
    assert digests["evidenceManifestFileSha256"] == OB_EVIDENCE_MANIFEST_FILE_SHA256
    assert digests["manifestFileCount"] == OB_MANIFEST_FILE_COUNT
    # The three digests are distinct objects and must never be conflated.
    assert len({digests[key] for key in
                ("archiveSha256", "evidenceContentSha256",
                 "evidenceManifestFileSha256")}) == 3

    finalization = record["finalization"]["booleans"]
    assert finalization["valid"] is True
    assert finalization["internalValid"] is True
    assert finalization["externalSealProvided"] is True
    assert finalization["externalSealValid"] is True
    assert finalization["finalizationEligible"] is True
    assert record["finalization"]["validationMode"] == "external-finalization"
    assert record["finalization"]["externalSealType"] == "evidence-manifest-file-sha256"
    assert record["finalization"]["terminalObservationCount"] == 3
    assert record["finalization"]["genericClaimCeiling"] == "descriptive-only"
    assert record["finalization"]["empiricalClaimsAllowed"] is False
    assert record["finalization"]["optimizationClaimsAllowed"] is False


def test_characterization_posture_counts_and_protocol_are_exact() -> None:
    record = load(CHARACTERIZATION)
    protocol = record["protocol"]
    assert protocol["seed"] == 20260817
    assert protocol["warmupSeconds"] == 15.0
    assert protocol["measurementSeconds"] == 30.0
    assert protocol["requestsPerSecond"] == 1.0
    assert protocol["concurrency"] == 4
    assert protocol["expectedOfferedRequests"] == 30
    assert protocol["faultInjected"] is None
    assert protocol["regime"] == "no-fault"

    rows = {row["posture"]: row for row in record["postureResults"]}
    assert set(rows) == set(OB_POSTURE_COUNTS)
    for posture, (in_window, carrier) in OB_POSTURE_COUNTS.items():
        row = rows[posture]
        assert row["retainedTargetSpansInWindow"] == in_window, posture
        assert row["carrierRetainedCount"] == carrier, posture
        assert row["outOfWindowCarrierSpans"] == carrier - in_window, posture
        assert row["inWindowServiceCounts"] == OB_IN_WINDOW_SERVICE_COUNTS[posture]
        # Every warm-up 15/15 and every measurement 30/30 with zero failures.
        assert row["warmup"] == {"offered": 15, "completed": 15, "failed": 0}, posture
        assert row["measurement"] == {
            "offered": 30, "completed": 30, "failed": 0}, posture
        assert row["functionalVerdict"] == "pass", posture
        assert row["technicalBlockers"] == [], posture
        assert row["controlEvaluationBlockers"] == [], posture
        assert row["teardownClean"] is True, posture
        assert row["duplicateSpanIdentityCount"] == 0, posture
        assert row["malformedSpanRecordCount"] == 0, posture

    # The perturbation must move only the frontend service count.
    full = rows["full-reference"]["inWindowServiceCounts"]
    off = rows["frontend-off"]["inWindowServiceCounts"]
    assert full["frontend"] > 0 and off["frontend"] == 0
    assert full["currencyservice"] == off["currencyservice"]
    assert full["productcatalogservice"] == off["productcatalogservice"]
    # True source-off retains nothing from any target service.
    assert set(rows["source-off"]["inWindowServiceCounts"].values()) == {0}

    integrity = record["protocolIntegrity"]
    assert integrity["zeroWorkloadFailures"] is True
    assert integrity["cleanTeardown"] is True
    assert integrity["bothAllocatedProjectsCleanAtExit"] is True
    assert integrity["unscheduledAttemptDirectories"] == 0
    assert integrity["unscheduledReceipts"] == 0
    assert record["acquisitionCanary"]["passed"] is True
    assert record["acquisitionCanary"]["blockers"] == []


def test_characterization_discloses_count_semantics_and_non_converged_polls() -> None:
    """The anti-overclaim disclosures are load-bearing and must not be deletable."""
    record = load(CHARACTERIZATION)
    semantics = record["countSemantics"]
    required = {
        "retainedTargetSpansInWindow",
        "carrierRetainedCount",
        "outOfWindowCarrierSpans",
        "nonConvergedPollWarning",
        "prohibitedInference",
    }
    assert required <= set(semantics), sorted(required - set(semantics))

    # The intermediate, non-converged poll projections must stay disclosed by
    # value, so a reader can never mistake them for the citable figures.
    warning = semantics["nonConvergedPollWarning"]
    assert "715" in warning and "304" in warning, warning
    assert "terminal" in warning.lower()

    # The record must keep saying, in the record itself, that these counts are
    # not effect, volume or cost evidence.
    prohibited = semantics["prohibitedInference"].lower()
    for phrase in ("not volume evidence", "not an effect estimate"):
        assert phrase in prohibited, prohibited
    assert "fixed offered-load denominator" in semantics[
        "retainedTargetSpansInWindow"].lower() or "fixed offered-load denominator" in prohibited

    # Carrier totals must remain marked capture-time-dependent, never comparable.
    assert "capture-time-dependent" in record["claimBoundary"]["interferenceLimit"].lower()
    assert record["claimBoundary"]["singleBlockLimit"]
    assert "not independent" in record["claimBoundary"]["familyLimit"].lower() or \
        "not an independent" in record["claimBoundary"]["familyLimit"].lower()


def test_characterization_pins_carrier_and_required_sensor_counts() -> None:
    """Per-service carrier counts and required-sensor counts must not drift."""
    record = load(CHARACTERIZATION)
    rows = {row["posture"]: row for row in record["postureResults"]}
    assert rows["full-reference"]["carrierServiceCounts"] == {
        "frontend": 428, "currencyservice": 300, "productcatalogservice": 38}
    assert rows["frontend-off"]["carrierServiceCounts"] == {
        "frontend": 0, "currencyservice": 300, "productcatalogservice": 38}
    assert rows["source-off"]["carrierServiceCounts"] == {
        "frontend": 0, "currencyservice": 0, "productcatalogservice": 0}
    assert rows["full-reference"]["requiredSensorCounts"] == {
        "span:frontend:GET": 30,
        "span:frontend:grpc ListProducts": 30,
        "span:frontend:grpc Convert": 270,
        "span:frontend:grpc GetSupportedCurrencies": 30,
        "span:productcatalog:ListProducts": 30,
        "span:currency:Convert": 270,
        "span:currency:GetSupportedCurrencies": 30,
    }
    # Disabling the frontend source guard removes exactly the frontend sensors.
    assert rows["frontend-off"]["requiredSensorCounts"] == {
        "span:productcatalog:ListProducts": 30,
        "span:currency:Convert": 270,
        "span:currency:GetSupportedCurrencies": 30,
    }
    assert rows["source-off"]["requiredSensorCounts"] == {}
    # Carrier totals always bound the in-window figure they contain.
    for posture, row in rows.items():
        assert row["carrierRetainedCount"] >= row["retainedTargetSpansInWindow"], posture
        assert sum(row["carrierServiceCounts"].values()) == row["carrierRetainedCount"], posture
        assert sum(row["inWindowServiceCounts"].values()) == row[
            "retainedTargetSpansInWindow"], posture


def test_characterization_ceiling_registers_no_promotable_evidence() -> None:
    record = load(CHARACTERIZATION)
    boundary = record["claimBoundary"]
    assert record["registersAsEvidence"] is False
    assert boundary["ceiling"] == CEILING
    assert boundary["portfolioComplete"] is False
    assert boundary["promotionAllowed"] is False
    assert boundary["optimizationAllowed"] is False
    forbidden = {
        "effect evidence",
        "cost evidence",
        "volume evidence",
        "candidate evidence",
        "canonical evidence",
        "optimization evidence",
    }
    assert forbidden <= set(boundary["registersNo"]), boundary["registersNo"]
    assert record["phase1PortfolioStatus"]["portfolioComplete"] is False
    assert record["phase1PortfolioStatus"]["remainingInThisModule"]
    assert record["stage3Status"].startswith("NO-GO")


def test_runtime_bindings_carry_the_external_seal_chain() -> None:
    matrix = load(MATRIX)
    record = load(CHARACTERIZATION)
    runtime = {row["id"]: row for row in matrix["runtimeEvidenceBindings"]}
    assert set(runtime) == OB_RUNTIME_BINDING_IDS
    record_sha = hashlib.sha256(CHARACTERIZATION.read_bytes()).hexdigest()
    for binding in runtime.values():
        assert binding["module"] == "online-boutique"
        assert binding["stage"] in OB_TESTED_STAGES
        assert (ROOT / binding["path"]) == CHARACTERIZATION
        assert binding["sha256"] == record_sha, binding["id"]
        assert binding["qualificationCeiling"] == CEILING
        assert binding["registersAsEvidence"] is False
        seal = binding["externalSeal"]
        assert seal["archiveSha256"] == record["digests"]["archiveSha256"]
        assert seal["evidenceContentSha256"] == record["digests"]["evidenceContentSha256"]
        assert (seal["evidenceManifestFileSha256"]
                == record["digests"]["evidenceManifestFileSha256"])
    # Exactly one binding per tested stage.
    assert {row["stage"] for row in runtime.values()} == OB_TESTED_STAGES
    # The policy must state the promotion boundary, not merely be non-empty.
    policy = matrix["runtimeEvidenceBindingPolicy"]
    boundary = policy["promotionBoundary"].lower()
    assert "never promotes readiness" in boundary, boundary
    assert "never" in boundary and "optimization" in boundary, boundary
    assert "candidate" in boundary and "canonical" in boundary, boundary
    assert policy["verification"] == "record-file-sha256-plus-external-seal-digests"
    assert "archivesha256" in policy["sealChain"].lower().replace(" ", "")


def test_online_boutique_unsupported_stages_are_never_filled_by_inference() -> None:
    matrix = load(MATRIX)
    record = load(CHARACTERIZATION)
    stages = {row["stage"]: row for row in ob_module(matrix)["reconciliation"]["stages"]}
    for stage in OB_UNSUPPORTED_STAGES:
        assert stages[stage]["status"] == "unsupported", stage
        # An unsupported stage may never cite runtime evidence.
        assert all(
            reference.get("runtimeEvidenceBindingId") is None
            for reference in stages[stage]["evidenceRefs"]
        ), stage
    assert {row["stage"] for row in record["stages"]["unsupported"]} == OB_UNSUPPORTED_STAGES
    assert all(row["status"] == "unsupported" for row in record["stages"]["unsupported"])
    assert set(record["finalization"]["blindStages"]) == OB_UNSUPPORTED_STAGES
    # The stage vector stays open precisely because two stages are unsupported.
    assert record["stages"]["exactVectorComplete"] is False
    assert record["stages"]["exactVectorStatus"] == "deferred"
    assert ob_module(matrix)["reconciliation"]["exactVectorStatus"] == "deferred"
    assert {row["stage"] for row in record["stages"]["tested"]} == OB_TESTED_STAGES


def test_online_boutique_held_siblings_are_not_promoted_by_the_frontend_cell() -> None:
    matrix = load(MATRIX)
    plan = load(PLAN)
    record = load(CHARACTERIZATION)
    groups = {row["id"]: row for row in ob_module(matrix)["activationGroups"]}
    assert groups["frontend-source-tracing"]["status"] == "tested"
    for group_id in OB_HELD_SIBLING_GROUPS:
        assert groups[group_id]["status"] == "transitively-covered", group_id
        # A held sibling must not borrow the frontend cell's runtime evidence.
        assert all(
            reference.get("runtimeEvidenceBindingId") is None
            for reference in groups[group_id]["evidenceRefs"]
        ), group_id
    for group_id in ("cart-no-stock-tracing", "ad-no-stock-tracing"):
        assert groups[group_id]["status"] == "unsupported", group_id

    plan_groups = {
        row["activationGroup"]: row
        for row in ob_module(plan)["oneGroupPerturbations"]
    }
    assert plan_groups["frontend-source-tracing"]["status"] == "tested"
    for group_id in OB_HELD_SIBLING_GROUPS:
        assert plan_groups[group_id]["status"] == "transitively-covered", group_id

    held = {row["id"] for row in record["activationGroups"]["heldTransitivelyCovered"]}
    assert held == OB_HELD_SIBLING_GROUPS
    assert {row["id"] for row in record["activationGroups"]["tested"]} == {
        "frontend-source-tracing"
    }
    # 011 holds both siblings enabled, so it cannot perturb them.
    frontend_off = next(row for row in record["postureResults"]
                        if row["posture"] == "frontend-off")
    assert frontend_off["runtimeEnabledControls"]["productcatalog"] == "1"
    assert frontend_off["runtimeEnabledControls"]["currency"] == "1"
    assert frontend_off["runtimeEnabledControls"]["frontend"] == "0"


def test_frontend_cell_promotes_nothing_beyond_its_own_cell() -> None:
    matrix = load(MATRIX)
    plan = load(PLAN)
    readiness = load(READINESS)

    # The matrix stays planning-only at the fixed ceiling and the exit gate is shut.
    assert matrix["planningOnly"] is True
    assert matrix["qualificationCeiling"] == CEILING
    assert matrix["phase1ExitGate"]["promotionAllowed"] is False
    assert matrix["phase1ExitGate"]["optimizationAllowed"] is False
    assert plan["qualificationCeiling"] == CEILING
    assert plan["registersAsEvidence"] is False

    # Readiness is untouched: the matrix still binds the readiness bytes it was
    # reviewed against, so a silent readiness promotion fails this test.
    readiness_binding = next(
        row for row in matrix["sourceBindings"] if row["id"] == "readiness"
    )
    assert (hashlib.sha256(READINESS.read_bytes()).hexdigest()
            == readiness_binding["sha256"])
    assert ob_module(matrix)["currentQualification"] == "smoke-validation"

    # Phase 1 is not complete: deferred and transitively-covered rows remain.
    ob_controls = {row["controlId"]: row for row in ob_module(matrix)["controls"]}
    assert ob_controls["full-reference"]["status"] == "tested"
    assert ob_controls["true-source-off"]["status"] == "tested"
    for control_id in ("emission-off", "transport-off", "retention-off"):
        assert ob_controls[control_id]["status"] == "deferred", control_id
        assert ob_controls[control_id]["sourceWorkDisabled"] is False, control_id
    # true-source-off remains targeted, never a global application claim, in the
    # matrix and in the characterization record itself.
    assert ob_controls["true-source-off"]["claimScope"] == "targeted"
    record = load(CHARACTERIZATION)
    record_source_off = next(
        row for row in record["controls"]["tested"]
        if row["controlId"] == "true-source-off"
    )
    assert record_source_off["claimScope"] == "targeted"
    assert record_source_off["sourceWorkDisabled"] is True
    scope_limit = record_source_off["scopeLimit"].lower()
    assert "cart" in scope_limit and "ad" in scope_limit, scope_limit
    assert "not a global" in scope_limit, scope_limit
    assert {row["controlId"] for row in record["controls"]["notEstablished"]} == {
        "emission-off", "transport-off", "retention-off"
    }

    remaining = [
        (row["module"], item["controlId"], item["status"])
        for row in matrix["modules"]
        for item in row["controls"]
        if item["status"] in {"deferred", "transitively-covered"}
    ]
    assert remaining, "portfolio must not be marked complete"
    assert readiness["scope"]["moduleCount"] == 5
