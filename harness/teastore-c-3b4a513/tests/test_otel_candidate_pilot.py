from __future__ import annotations

import ast
import copy
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


def descriptor() -> dict:
    return pilot.load_descriptor()


def plan() -> dict:
    document = descriptor()
    return pilot.compile_plan(document)


def test_frozen_descriptor_and_plan_compile_exact_geometry() -> None:
    document = descriptor()
    compiled = pilot.compile_plan(document)
    assert pilot.canonical_sha256(document) == pilot.EXPECTED_DESCRIPTOR_SHA256
    assert compiled["studyEpoch"] == "otel-demo-candidate-pilot-v1"
    assert compiled["runCount"] == compiled["uniqueRunCount"] == 18
    assert compiled["runtimeReady"] is False
    assert compiled["runtimeAuthorized"] is False
    assert compiled["candidateExecutionEnabled"] is False


def test_each_regime_has_three_balanced_randomized_blocks() -> None:
    compiled = plan()
    selector_digests = set()
    for regime in compiled["regimeRoots"]:
        assert len(regime["blocks"]) == 3
        selector_digests.add(regime["selectorSha256"])
        for block in regime["blocks"]:
            assert len(block["cells"]) == 3
            assert set(block["order"]) == {"none", "selected", "full"}
            assert [cell["runKey"]["posture"] for cell in block["cells"]] == block[
                "order"
            ]
    assert len(selector_digests) == 2


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


def test_unsupported_controls_abstain_instead_of_relabelling_source_off() -> None:
    document = descriptor()
    compiled = pilot.compile_plan(document)
    report = pilot.readiness_report(document, compiled)
    assert report["unsupportedPostures"] == ["none", "selected"]
    assert report["constructionValid"] is True
    assert report["runtimeReady"] is False
    assert "none-posture-not-realized" in report["blockers"]
    assert document["postureRealization"]["none"]["currentControl"] == (
        "legacy-source-off"
    )
    assert document["postureRealization"]["none"]["status"] == "unsupported"


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
                {"status": "implemented"}
            ),
            "posture realization boundary differs",
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
    document = descriptor()
    document["analysis"]["report"].append("invented-result")
    with pytest.raises(pilot.ProtocolError, match="frozen design"):
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
    }


def test_application_family_is_not_an_online_boutique_channel_alias() -> None:
    document = descriptor()
    assert document["source"]["applicationFamily"] == "otel-demo"
    assert document["source"]["channel"] == "compose-otel-collector"
