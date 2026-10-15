from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modules/otel-demo/execution/candidate_pilot.py"
SPEC = importlib.util.spec_from_file_location("otel_candidate_pilot_tests", MODULE)
assert SPEC is not None and SPEC.loader is not None
pilot = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pilot
SPEC.loader.exec_module(pilot)


V1 = "otel-demo-candidate-pilot-v1"
V2 = "otel-demo-candidate-pilot-v2"
V3 = "otel-demo-candidate-pilot-v3"
# v2 identities that must survive v3 unchanged: the admission plan (attempt 1,
# governance protocolBindings) and the run-3 frozen plan (attempt 3, the
# run-3 launcher's FROZEN_PLAN).
V2_DESCRIPTOR_BYTE_SHA256 = "2fd3ee5501c3f65f3059b4adc55a650ee15643d9b6466f32d97ea9466df41299"
V2_DESCRIPTOR_CANONICAL_SHA256 = "c86874e0001544ae3c8289ba76cd54d3432112fcea2b01368775e27d9cc002b2"
V2_ADMISSION_PLAN_SHA256 = "4ce8eede3cd86b90f6a3a62aa13d933806c27a75e3e087abcbe60b641c16c22c"
V2_RUN3_PLAN_SHA256 = "2d016ed59336fe7ea2a2169f65b9d32ed538e6cab55439d1b86546eca5485171"
# The v3 attempt-1 plan the launcher (main repo scratchpad/gate-drivers/launch_otel.sh) pins.
V3_ATTEMPT1_PLAN_SHA256 = "d445a0543694c6475fb657915c47840a7e319cd9610f0135aa6dc87f8bb78ab6"
V3_DESCRIPTOR_CANONICAL_SHA256 = "1231208d0ce21230804aea042569b7b8078e237be20a46f16fa763e10d3d7a28"
FOUR = ("none", "selected", "async", "full")
OFFPATH = "otel-demo-offpath-v1"
# The offpath descriptor and attempt-1 plan the launcher
# (main repo scratchpad/gate-drivers/launch_otel_offpath.sh) pins.
OFFPATH_DESCRIPTOR_CANONICAL_SHA256 = "1491657d8d3c2a3271aa37e837f28f73c4c4bad297e37cb899a28d9efd2742f6"
OFFPATH_ATTEMPT1_PLAN_SHA256 = "168699c4d78a50766655254a58612b9ef0caf1ad91480b79852752bc933a47cc"
V3_DESCRIPTOR_BYTE_SHA256 = "f37fb9873f4dfdaf48951cda6fb27b91b1bab77967091e68d88190b8133bfd2e"
# Identities frozen before this file changed: the v1 descriptor's bytes and
# canonical digest, and the 18-cell plan digest the v1 UNSUPPORTED ledger and
# the v1 governance/registry pins were written against.
V1_DESCRIPTOR_BYTE_SHA256 = "fb43212b38ce0cd53538ee654b825574ee415dc4624fc2cc32bcc6d82504cbaa"
V1_DESCRIPTOR_CANONICAL_SHA256 = "daffe1cafc502bc0ff79da25d8233cd69c5882091628c2d83fb82e851be5307e"
V1_PLAN_CANONICAL_SHA256 = "53b0ac1b6a43c3070dfe8148ec391ef0cc278eca38250f4f926bb14862597e67"


def descriptor(epoch: str = pilot.EPOCH) -> dict:
    return pilot.load_descriptor(pilot.EPOCHS[epoch]["descriptor"])


def plan(epoch: str = pilot.EPOCH) -> dict:
    document = descriptor(epoch)
    return pilot.compile_plan(document)


def test_frozen_descriptor_and_plan_compile_exact_geometry() -> None:
    document = descriptor()
    compiled = pilot.compile_plan(document)
    assert pilot.EPOCH == OFFPATH and pilot.FROZEN_EPOCH == V1 and pilot.PREVIOUS_EPOCH == V2
    assert pilot.V3_EPOCH == pilot.OFFPATH_PREDECESSOR_EPOCH == V3
    assert pilot.canonical_sha256(document) == pilot.EXPECTED_DESCRIPTOR_SHA256
    assert compiled["studyEpoch"] == OFFPATH
    assert compiled["runCount"] == compiled["uniqueRunCount"] == 36 == pilot.TOTAL_RUNS
    assert document["design"]["postures"] == list(FOUR)
    assert [row["id"] for row in document["design"]["regimes"]] == [
        "no-fault-cost", "fraud-pause-effect", "frontend-pause-effect",
    ]
    assert pilot.canonical_sha256(document) == OFFPATH_DESCRIPTOR_CANONICAL_SHA256
    assert pilot.canonical_sha256(pilot.compile_plan(document, 1)) == OFFPATH_ATTEMPT1_PLAN_SHA256
    assert compiled["runtimeReady"] is False
    assert compiled["runtimeAuthorized"] is False
    assert compiled["candidateExecutionEnabled"] is False


def test_superseded_v1_epoch_replays_its_frozen_identity_byte_for_byte() -> None:
    """Introducing v2 moved nothing about v1: same bytes, same digest, same
    18 cell identities (the UNSUPPORTED ledger and the v1 pins depend on it)."""
    path = pilot.EPOCHS[V1]["descriptor"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == V1_DESCRIPTOR_BYTE_SHA256
    document = descriptor(V1)
    assert pilot.canonical_sha256(document) == V1_DESCRIPTOR_CANONICAL_SHA256
    assert pilot.EPOCHS[V1]["expectedDescriptorSha256"] == V1_DESCRIPTOR_CANONICAL_SHA256
    compiled = pilot.compile_plan(document)
    assert compiled["studyEpoch"] == V1
    assert pilot.canonical_sha256(compiled) == V1_PLAN_CANONICAL_SHA256
    assert all(
        cell["runKey"]["studyEpoch"] == V1
        for regime in compiled["regimeRoots"]
        for block in regime["blocks"]
        for cell in block["cells"]
    )
    # v2 records exactly that identity as the design it supersedes.
    supersedes = descriptor(V2)["supersedes"]
    assert supersedes["studyEpoch"] == V1
    assert supersedes["descriptorByteSha256"] == V1_DESCRIPTOR_BYTE_SHA256
    assert supersedes["descriptorCanonicalSha256"] == V1_DESCRIPTOR_CANONICAL_SHA256


def test_v2_schedule_is_a_fresh_randomization_seeded_by_its_own_epoch_id() -> None:
    first, second = plan(V1), plan(V2)
    selectors = lambda compiled: {root["id"]: root["selectorSha256"] for root in compiled["regimeRoots"]}
    assert set(selectors(first).values()).isdisjoint(selectors(second).values())
    orders = lambda compiled: [block["order"] for root in compiled["regimeRoots"] for block in root["blocks"]]
    assert orders(first) != orders(second)
    ids = lambda compiled: {cell["runId"] for root in compiled["regimeRoots"] for block in root["blocks"] for cell in block["cells"]}
    assert ids(first).isdisjoint(ids(second))
    third = plan(V3)
    assert set(selectors(third).values()).isdisjoint(selectors(second).values())
    assert ids(third).isdisjoint(ids(second))
    fourth = plan(OFFPATH)
    assert set(selectors(fourth).values()).isdisjoint(selectors(third).values())
    assert ids(fourth).isdisjoint(ids(third))
    with pytest.raises(pilot.ProtocolError, match="unknown study epoch"):
        pilot.allocate_schedules("otel-demo-candidate-pilot-v9")


def test_each_regime_has_three_balanced_randomized_blocks() -> None:
    compiled = plan()
    selector_digests = set()
    for regime in compiled["regimeRoots"]:
        assert len(regime["blocks"]) == 3
        selector_digests.add(regime["selectorSha256"])
        for block in regime["blocks"]:
            assert len(block["cells"]) == 4
            assert set(block["order"]) == set(FOUR)
            assert [cell["runKey"]["posture"] for cell in block["cells"]] == block[
                "order"
            ]
        # 3x4 Latin rectangle: no posture twice in one ordinal position, so
        # each posture sees exactly 3 of the 4 positions (declared, not a square).
        positions = {posture: [block["order"].index(posture) + 1 for block in regime["blocks"]] for posture in FOUR}
        assert all(len(set(seen)) == 3 for seen in positions.values()), positions
    assert len(selector_digests) == 3


def test_v3_plans_replay_unchanged_after_offpath() -> None:
    """offpath must not move a byte of v3: its descriptor and the attempt-1 plan
    v3r1 executed under (and the plan v3 attempt 2 is running under)."""
    path = pilot.EPOCHS[V3]["descriptor"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == V3_DESCRIPTOR_BYTE_SHA256
    document = descriptor(V3)
    assert pilot.canonical_sha256(document) == V3_DESCRIPTOR_CANONICAL_SHA256
    assert pilot.canonical_sha256(pilot.compile_plan(document, 1)) == V3_ATTEMPT1_PLAN_SHA256
    assert [root["id"] for root in pilot.compile_plan(document)["regimeRoots"]] == list(pilot.TWO_REGIMES)
    assert pilot.derive_v3_descriptor() == document


def test_offpath_descriptor_is_generated_from_v3_never_hand_edited() -> None:
    path = pilot.EPOCHS[OFFPATH]["descriptor"]
    derived = pilot.derive_offpath_descriptor()
    assert path.read_bytes() == pilot._pretty_bytes(derived)
    assert pilot.canonical_sha256(derived) == pilot.EPOCHS[OFFPATH]["expectedDescriptorSha256"]
    assert derived["supersedes"]["studyEpoch"] == V3
    assert derived["supersedes"]["descriptorByteSha256"] == V3_DESCRIPTOR_BYTE_SHA256
    v3 = descriptor(V3)
    for key in ("analysis", "evidence", "missingness", "outcomes", "runIdentity",
                "setupPreconditions", "source", "status", "target", "workflow", "schedule"):
        assert derived[key] == v3[key], key
    assert derived["postureRealization"]["none"] == v3["postureRealization"]["none"]
    assert derived["postureRealization"]["full"] == v3["postureRealization"]["full"]
    # The fault design: declared defaults (DECLARATION.md; erratum 2 parameters).
    design = derived["faultDesign"]
    assert (design["targetScenarios"], design["controlScenarios"]) == (["fraud-pause"], ["frontend-pause"])
    assert (design["onsetSeconds"], design["holdSeconds"]) == (45, 15)
    assert design["metricExportIntervalMilliseconds"] is None
    assert (derived["timing"]["faultOnsetSeconds"], derived["timing"]["interventionHoldSeconds"]) == (45, 15)
    contracts = {row["scenario"]: row for row in derived["groundTruth"]["fault"]["scenarioContracts"]}
    assert contracts["fraud-pause"]["service"] == "frauddetectionservice"
    assert contracts["frontend-pause"]["entryRouteDuringFault"] == "must-be-unavailable"
    # The selected literal and its recorded derivation.
    selected = derived["postureRealization"]["selected"]
    assert selected["closure"] == sorted(pilot.OFFPATH_SYNC_PATH)
    assert "flagd" in selected["closure"] and "recommendationservice" not in selected["closure"]
    assert derived["postureRealization"]["async"]["closure"] == sorted(
        selected["closure"] + ["accountingservice", "frauddetectionservice", "kafka"]
    )
    assert derived["groundTruth"]["path"]["expectedNoFaultPath"] == list(pilot.OFFPATH_SYNC_PATH)
    assert derived["workload"]["pathCheck"]["cell"].startswith("the first no-fault-cost full cell")


def test_offpath_fault_design_is_a_parameter_and_a_fourth_regime_is_one_table_row(monkeypatch) -> None:
    """Erratum 2: hold, scenario and export interval are parameters. A fourth
    regime (here an emailservice stop) is one entry in the design; the
    derivation follows without code changes, and the frozen digest then refuses
    the changed descriptor until it is re-pinned."""
    design = dict(pilot.OFFPATH_FAULT_DESIGN, targetScenarios=["fraud-pause", "email-stop"], holdSeconds=75)
    monkeypatch.setattr(pilot, "OFFPATH_FAULT_DESIGN", design)
    derived = pilot.derive_offpath_descriptor()
    assert [row["id"] for row in derived["design"]["regimes"]] == [
        "no-fault-cost", "fraud-pause-effect", "email-stop-effect", "frontend-pause-effect",
    ]
    assert derived["design"]["totalRuns"] == 48
    assert derived["timing"]["interventionHoldSeconds"] == 75
    stop = next(row for row in derived["groundTruth"]["fault"]["scenarioContracts"] if row["scenario"] == "email-stop")
    assert (stop["service"], stop["commandFamily"], stop["duringPredicate"]) == (
        "emailservice", "container-stop-start", "not-running",
    )
    with pytest.raises(pilot.ProtocolError):
        pilot.validate_descriptor(derived)


@pytest.mark.parametrize(
    "change, diagnostic",
    (
        ({"targetScenarios": ["kafka-queue-problems"]}, "declared but not implemented"),
        ({"targetScenarios": ["no-such-fault"]}, "unknown, repeated or empty"),
        ({"targetScenarios": []}, "unknown, repeated or empty"),
        ({"controlScenarios": ["fraud-pause"]}, "unknown, repeated or empty"),
        ({"holdSeconds": 500}, "does not fit the measurement window"),
        ({"onsetSeconds": 10}, "does not fit the measurement window"),
        ({"metricExportIntervalMilliseconds": 5000}, "emission change the user must approve"),
    ),
)
def test_offpath_fault_design_defects_fail_closed(change, diagnostic) -> None:
    with pytest.raises(pilot.ProtocolError, match=diagnostic):
        pilot.validate_fault_design(dict(pilot.OFFPATH_FAULT_DESIGN, **change))


def test_v2_plans_replay_unchanged_after_v3() -> None:
    """v3 must not move a byte of v2: its descriptor, its admission plan and
    the plan run 3 executed under (attempt 3)."""
    path = pilot.EPOCHS[V2]["descriptor"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == V2_DESCRIPTOR_BYTE_SHA256
    document = descriptor(V2)
    assert pilot.canonical_sha256(document) == V2_DESCRIPTOR_CANONICAL_SHA256
    assert pilot.canonical_sha256(pilot.compile_plan(document)) == V2_ADMISSION_PLAN_SHA256
    run3 = pilot.compile_plan(document, 3)
    assert pilot.canonical_sha256(run3) == V2_RUN3_PLAN_SHA256
    assert run3["runCount"] == 18


def test_v3_descriptor_is_generated_from_v2_never_hand_edited() -> None:
    path = pilot.EPOCHS[V3]["descriptor"]
    derived = pilot.derive_v3_descriptor()
    assert path.read_bytes() == pilot._pretty_bytes(derived)
    assert pilot.canonical_sha256(derived) == pilot.EPOCHS[V3]["expectedDescriptorSha256"]
    supersedes = derived["supersedes"]
    assert supersedes["studyEpoch"] == V2
    assert supersedes["descriptorByteSha256"] == V2_DESCRIPTOR_BYTE_SHA256
    assert supersedes["descriptorCanonicalSha256"] == V2_DESCRIPTOR_CANONICAL_SHA256
    # Everything but geometry, the async realization and the supersession is v2's.
    v2 = descriptor(V2)
    for key in ("analysis", "evidence", "groundTruth", "missingness", "outcomes",
                "runIdentity", "setupPreconditions", "source", "status", "target",
                "timing", "workflow"):
        assert derived[key] == v2[key], key
    assert derived["design"]["regimes"] == v2["design"]["regimes"]


def test_v3_realizes_four_nested_postures_with_the_d13_boundary_below_full() -> None:
    document = descriptor(V3)
    report = pilot.readiness_report(document, pilot.compile_plan(document))
    assert report["studyEpoch"] == V3 and report["runCount"] == 24
    assert report["unsupportedPostures"] == []
    realization = document["postureRealization"]
    assert {posture: row["status"] for posture, row in realization.items()} == dict.fromkeys(FOUR, "implemented")
    for posture in ("none", "selected", "async"):
        assert realization[posture]["claimBoundary"]["loadedButSilencedServices"] == [
            "emailservice", "flagd", "flagd-ui", "loadgenerator",
        ]
    assert realization["full"]["claimBoundary"] is None
    assert realization["async"]["currentControl"] == "materialized-posture-controls-async-closure"
    assert document["schedule"]["postureCodes"] == {"N": "none", "S": "selected", "A": "async", "F": "full"}


def test_a_schedule_that_repeats_a_position_is_refused(monkeypatch) -> None:
    """Planted defect: blocks that are the same row (no rotation) keep each block
    complete but put one posture in the same position three times."""
    def unrotated(epoch=pilot.EPOCH):
        codes = pilot.EPOCHS[epoch]["postureCodes"]
        row = tuple(codes.values())
        return tuple((row,) * pilot.BLOCKS_PER_REGIME for _ in range(24))
    monkeypatch.setattr(pilot, "schedule_candidates", unrotated)
    with pytest.raises(pilot.ProtocolError, match="repeats an ordinal position"):
        pilot.compile_plan(descriptor(V3))


def test_cost_and_effect_windows_are_separate_and_never_pooled() -> None:
    document = descriptor()
    compiled = pilot.compile_plan(document)
    assert document["analysis"]["costAndEffectPoolable"] is False
    assert document["outcomes"]["costRegimeOnly"] == "no-fault-cost"
    roots = {row["id"]: row for row in compiled["regimeRoots"]}
    assert roots["no-fault-cost"]["kind"] == "cost"
    assert roots["no-fault-cost"]["fault"] is None
    assert roots["frontend-pause-effect"]["kind"] == "effect"
    assert roots["frontend-pause-effect"]["fault"] == "frontend-pause"
    assert all(
        cell["fault"] is None
        for block in roots["no-fault-cost"]["blocks"]
        for cell in block["cells"]
    )
    assert all(
        cell["fault"] == "frontend-pause"
        for block in roots["frontend-pause-effect"]["blocks"]
        for cell in block["cells"]
    )


def test_v1_unsupported_controls_abstain_instead_of_relabelling_source_off() -> None:
    document = descriptor(V1)
    compiled = pilot.compile_plan(document)
    report = pilot.readiness_report(document, compiled)
    assert report["studyEpoch"] == V1
    assert report["unsupportedPostures"] == ["none", "selected"]
    assert report["constructionValid"] is True
    assert report["runtimeReady"] is False
    assert "none-posture-not-realized" in report["blockers"]
    assert document["postureRealization"]["none"]["currentControl"] == (
        "legacy-source-off"
    )
    assert document["postureRealization"]["none"]["status"] == "unsupported"


def test_v2_realizes_every_posture_under_the_d13_emitted_reading_with_a_named_boundary() -> None:
    document = descriptor(V2)
    compiled = pilot.compile_plan(document)
    report = pilot.readiness_report(document, compiled)
    assert report["studyEpoch"] == V2
    assert report["unsupportedPostures"] == []
    assert report["runtimeReady"] is False and report["runtimeAuthorized"] is False
    # Compiling the design still does not authorize anything: the remaining
    # blockers are gate- and target-resolved, never edit-resolved.
    assert report["blockers"] == [
        "amd64-source-guard-images-not-built-on-target",
        "posture-connection-probe-receipt-not-recorded",
        "gate-plan-pending",
        "gate-run-not-requested",
    ]
    realization = document["postureRealization"]
    assert {posture: row["status"] for posture, row in realization.items()} == {
        "none": "implemented", "selected": "implemented", "full": "implemented",
    }
    assert realization["none"]["currentControl"] == "materialized-posture-controls"
    for posture in ("none", "selected"):
        boundary = realization[posture]["claimBoundary"]
        assert boundary["label"] == pilot.D13_CLAIM_BOUNDARY_LABEL
        assert boundary["semantics"] == "no-telemetry-emitted"
        assert boundary["loadedButSilencedServices"] == [
            "emailservice", "flagd", "flagd-ui", "loadgenerator",
        ]
    assert realization["full"]["claimBoundary"] is None
    # The srv6 identities and the GATE-SETUP preconditions are part of the frozen design.
    assert document["target"] == pilot.SRV6_TARGET
    assert document["target"]["executionUser"] == "stig"
    assert [item["id"] for item in document["setupPreconditions"]] == list(pilot.SETUP_PRECONDITION_IDS)
    probe = document["setupPreconditions"][0]
    assert probe["tool"] == "modules/otel-demo/tools/posture_connection_probe.sh"
    assert probe["requiredOutput"] == "PROBE OK"
    teardown = document["setupPreconditions"][1]
    assert teardown["ports"] == [8080, 3306]
    assert "docker compose -p teastore-demo down" in teardown["detail"]


def test_path_truth_uses_offered_request_witness_and_fault_specific_phases() -> None:
    path = descriptor()["groundTruth"]["path"]
    assert path["executedDenominator"] == "application-side-request-witness"
    assert path["crossTraceAssemblyAllowed"] is False
    assert path["scoredPhases"] == ["pre-fault", "during-fault", "post-readiness"]
    truth = path["faultSpecificTruth"]["frontend-pause"]
    assert truth["duringFaultFullPathRequired"] is False
    assert truth["preFaultFullPathRequired"] is True
    assert truth["postRecoveryFullPathRequired"] is True


@pytest.mark.parametrize(
    ("mutation", "diagnostic"),
    (
        (
            lambda value: value["design"]["regimes"][0].update(
                {"fault": "frontend-pause"}
            ),
            "cost/effect regime separation differs",
        ),
        (
            lambda value: value["postureRealization"]["none"].update(
                {"status": "unsupported"}
            ),
            "posture realization boundary differs",
        ),
        (
            lambda value: value["postureRealization"]["none"].update(
                {"currentControl": "legacy-source-off"}
            ),
            "posture realization boundary differs",
        ),
        (
            lambda value: value["postureRealization"]["selected"]["claimBoundary"][
                "loadedButSilencedServices"
            ].remove("flagd-ui"),
            "D13 claim boundary differs",
        ),
        (
            lambda value: value["postureRealization"]["async"]["claimBoundary"][
                "loadedButSilencedServices"
            ].remove("flagd-ui"),
            "D13 claim boundary differs",
        ),
        (
            lambda value: value["postureRealization"]["selected"]["claimBoundary"][
                "loadedButSilencedServices"
            ].append("emailservice"),
            "D13 claim boundary differs",
        ),
        (
            lambda value: value["faultDesign"].update({"holdSeconds": 60}),
            "timing differs from the fault design",
        ),
        (
            lambda value: value["faultDesign"].update({"targetScenarios": ["kafka-queue-problems"]}),
            "declared but not implemented",
        ),
        (
            lambda value: value["faultDesign"]["scenarios"]["fraud-pause"].update({"service": "kafka"}),
            "scenario table differs",
        ),
        (
            lambda value: value["design"]["regimes"].pop(1),
            "regime separation differs",
        ),
        (
            lambda value: value["postureRealization"].pop("async"),
            "posture realization boundary differs",
        ),
        (
            lambda value: value["schedule"]["postureCodes"].pop("A"),
            "identity or run geometry differs",
        ),
        (
            lambda value: value["design"].update({"totalRuns": 18}),
            "identity or run geometry differs",
        ),
        (
            lambda value: value["postureRealization"]["full"].update(
                {"claimBoundary": value["postureRealization"]["none"]["claimBoundary"]}
            ),
            "D13 claim boundary differs",
        ),
        (
            lambda value: value["target"].update({"executionUser": "fhuebscher"}),
            "target identity differs",
        ),
        (
            lambda value: value["supersedes"].update(
                {"descriptorCanonicalSha256": "0" * 64}
            ),
            "supersession record differs",
        ),
        (
            lambda value: value["setupPreconditions"].reverse(),
            "GATE-SETUP preconditions differ",
        ),
        (
            lambda value: value.update({"id": "otel-demo-candidate-pilot-v9"}),
            "identity or run geometry differs",
        ),
        (
            lambda value: value["workflow"].update({"runtimeAuthorized": True}),
            "construction/runtime denial differs",
        ),
        (
            lambda value: value["groundTruth"]["fault"].update(
                {"independentOfScoredTelemetry": False}
            ),
            "fault truth is not independent",
        ),
        (
            lambda value: value["groundTruth"]["path"].update(
                {"executedDenominator": "completed-requests"}
            ),
            "path/opportunity ground-truth contract differs",
        ),
        (
            lambda value: value["outcomes"].update(
                {"effectResourcesAreCostEstimates": True}
            ),
            "cost/effect outcome boundary differs",
        ),
    ),
)
def test_planted_descriptor_defects_fail_closed(mutation, diagnostic: str) -> None:
    document = descriptor()
    mutation(document)
    with pytest.raises(pilot.ProtocolError, match=diagnostic):
        pilot.validate_descriptor(document)


def test_unclassified_descriptor_drift_fails_final_digest_binding() -> None:
    for epoch in (V1, V2, V3):
        document = descriptor(epoch)
        document["analysis"]["report"].append("invented-result")
        with pytest.raises(pilot.ProtocolError, match="frozen design"):
            pilot.validate_descriptor(document)


def test_v1_descriptor_cannot_be_promoted_in_place_to_implemented() -> None:
    """The v1 contract is frozen: the only way to realize none/selected is the
    v2 epoch, never an edit of the v1 bytes."""
    document = descriptor(V1)
    document["postureRealization"]["none"]["status"] = "implemented"
    with pytest.raises(pilot.ProtocolError, match="posture realization boundary differs"):
        pilot.validate_descriptor(document)
    document = descriptor(V1)
    document["id"] = V2
    with pytest.raises(pilot.ProtocolError, match="candidate descriptor keys differ"):
        pilot.validate_descriptor(document)


def test_duplicate_keys_and_nonfinite_json_are_rejected() -> None:
    with pytest.raises(pilot.ProtocolError, match="duplicate JSON key"):
        pilot.strict_json_loads('{"id": 1, "id": 2}')
    with pytest.raises(pilot.ProtocolError, match="non-finite"):
        pilot.strict_json_loads('{"value": NaN}')


def test_changed_cell_order_or_runtime_flag_rejects_compiled_plan() -> None:
    document = descriptor()
    compiled = pilot.compile_plan(document)
    changed = copy.deepcopy(compiled)
    changed["regimeRoots"][0]["blocks"][0]["order"].reverse()
    with pytest.raises(pilot.ProtocolError, match="compiled plan differs"):
        pilot.validate_plan(document, changed)
    changed = copy.deepcopy(compiled)
    changed["runtimeReady"] = True
    with pytest.raises(pilot.ProtocolError, match="compiled plan differs"):
        pilot.validate_plan(document, changed)


def test_materialization_is_immutable_and_contains_no_run_root(tmp_path: Path) -> None:
    root = tmp_path / "candidate"
    first = pilot.materialize(root)
    second = pilot.materialize(root)
    assert first == second
    assert sorted(path.name for path in root.iterdir()) == [
        "campaign-descriptor.json",
        "compiled-plan.json",
        "construction-receipt.json",
    ]
    assert not (root / "runs").exists()
    assert first["runtimeReady"] is False


def test_materialization_rejects_retained_plan_drift(tmp_path: Path) -> None:
    root = tmp_path / "candidate"
    pilot.materialize(root)
    retained = json.loads((root / "compiled-plan.json").read_text())
    retained["runtimeAuthorized"] = True
    (root / "compiled-plan.json").write_text(json.dumps(retained))
    with pytest.raises(pilot.ProtocolError, match="retained compiled-plan.json differs"):
        pilot.materialize(root)


def test_materializer_has_no_executor_or_process_surface() -> None:
    source = MODULE.read_text()
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not ({"subprocess", "socket", "paramiko"} & imported)
    assert set(inspect.signature(pilot.materialize).parameters) == {
        "root",
        "descriptor_path",
        "attempt",
    }


def test_application_family_is_not_an_online_boutique_channel_alias() -> None:
    document = descriptor()
    assert document["source"]["applicationFamily"] == "otel-demo"
    assert document["source"]["channel"] == "compose-otel-collector"


def test_an_offpath_schedule_that_repeats_a_position_is_refused(monkeypatch) -> None:
    """Planted defect on the 36-cell offpath plan: unrotated blocks keep each
    block complete but repeat a posture in one ordinal position."""
    def unrotated(epoch=pilot.EPOCH):
        codes = pilot.EPOCHS[epoch]["postureCodes"]
        row = tuple(codes.values())
        return tuple((row,) * pilot.BLOCKS_PER_REGIME for _ in range(24))
    monkeypatch.setattr(pilot, "schedule_candidates", unrotated)
    with pytest.raises(pilot.ProtocolError, match="repeats an ordinal position"):
        pilot.compile_plan(descriptor(OFFPATH))
