from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load(
    "otel_candidate_unsupported_runtime_tests",
    "modules/otel-demo/execution/candidate_runtime.py",
)
validator = _load(
    "otel_candidate_unsupported_validator_tests",
    "modules/otel-demo/validation/candidate_unsupported.py",
)


def test_v1_ledger_is_scoped_to_v1_and_names_v2_as_its_successor():
    evidence = runtime.unsupported_evidence()
    assert evidence["scope"] == runtime.UNSUPPORTED_LEDGER_SCOPE
    assert evidence["scope"]["appliesToStudyEpochs"] == ["otel-demo-candidate-pilot-v1"]
    # v2 superseded v1; v3 superseded v2 and does not rewrite v1's ledger.
    assert evidence["scope"]["supersededBy"]["studyEpoch"] == runtime.UNSUPPORTED_SUCCESSOR_EPOCH == "otel-demo-candidate-pilot-v2"
    assert runtime.STUDY_EPOCH == "otel-demo-offpath-v1"
    assert evidence["frozenDesign"]["descriptorCanonicalSha256"] == (
        "daffe1cafc502bc0ff79da25d8233cd69c5882091628c2d83fb82e851be5307e"
    )
    assert {row["runKey"]["studyEpoch"] for row in evidence["cellLedger"]} == {"otel-demo-candidate-pilot-v1"}
    # Pointing the ledger at the v2 epoch is drift, not a re-scoring.
    forged = copy.deepcopy(evidence)
    forged["studyEpoch"] = "otel-demo-candidate-pilot-v2"
    with pytest.raises(validator.UnsupportedValidationError):
        validator.validate_unsupported_disposition(forged)


def test_dedicated_unsupported_disposition_is_bound_next_to_the_real_terminal():
    # The real terminal (candidate_terminal.py) is the route-bound terminal and
    # refuses through the descriptor-driven refuse_unsupported; the v1 UNSUPPORTED
    # ledger stays bound as its own controller so its digest is still installed
    # and replayed.
    assert runtime.CONTROLLER_PATHS["candidate-terminal"] == (
        "modules/otel-demo/validation/candidate_terminal.py"
    )
    assert runtime.CONTROLLER_PATHS["unsupported-disposition"] == (
        "modules/otel-demo/validation/candidate_unsupported.py"
    )
    # Under the v2 descriptor the posture half of the refusal is lifted; the
    # v1 ledger below is still replayed against the v1 descriptor's bytes.
    assert runtime.unsupported_postures() == []
    report = validator.terminal_report()
    assert report["studyEpoch"] == "otel-demo-candidate-pilot-v1"
    assert report["kind"] == "otel-demo-candidate-unsupported-terminal-v1"
    assert (report["executionDisposition"], report["empiricalResultState"]) == (
        "unsupported", "UNSUPPORTED",
    )
    assert report["expectedCells"] == report["unsupportedCells"] == 18
    assert report["observedCells"] == report["validCells"] == 0
    assert report["verdict"] == "unsupported"
    assert report["maximumEvidenceLabel"] is None
    assert report["promotionAuthorized"] is False
    assert len({row["runId"] for row in report["cells"]}) == 18
    assert all(row["state"] == "UNSUPPORTED" for row in report["cells"])
    assert all(row["externalAttempt"] is False for row in report["cells"])
    assert all(row["numericResults"] is None for row in report["cells"])
    assert validator.validate_campaign() == report


@pytest.mark.parametrize(
    "plant",
    (
        "numeric-result", "attempted-cell", "mutation-permission",
        "target-authority", "design-drift", "ledger-drift", "full-only",
    ),
)
def test_dedicated_unsupported_validator_is_watched_failing_on_drift(plant):
    evidence = copy.deepcopy(runtime.unsupported_evidence())
    if plant == "numeric-result":
        evidence["cellLedger"][0]["numericResults"] = {"coverage": 0.5}
    elif plant == "attempted-cell":
        evidence["cellLedger"][0]["externalAttempt"] = True
    elif plant == "mutation-permission":
        evidence["permissions"]["externalMutationAllowed"] = True
    elif plant == "target-authority":
        evidence["targetBinding"]["runtimeAuthority"] = True
    elif plant == "design-drift":
        evidence["frozenDesign"]["cellCount"] = 17
    elif plant == "ledger-drift":
        evidence["cellLedger"][0]["runId"] = "0" * 24
    else:
        evidence["comparativePolicy"]["fullOnlyExecutionAllowed"] = True
    with pytest.raises(validator.UnsupportedValidationError):
        validator.validate_unsupported_disposition(evidence)


def test_dedicated_terminal_rejects_empirical_roots_and_gate_objects():
    with pytest.raises(
        validator.UnsupportedValidationError, match="accepts no empirical root"
    ):
        validator.validate_campaign(
            Path("/must/not/be/read"), Path("/must/not/be/read"), object()
        )
