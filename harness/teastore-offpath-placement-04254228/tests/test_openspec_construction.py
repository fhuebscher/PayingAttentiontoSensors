from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_openspec_construction",
    ROOT / "tools" / "validate_openspec_construction.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)

DELIVERY_BASE_COMMIT = "f92ac3c228fe5f6c8ca6f1f4802857f405edf0d3"
PROTOCOL_MODULE_SHA256 = (
    "9105d2c59657c84a606dd7f2c55457b563cb06047fa55911c47955760acc1d37"
)


def manifest() -> dict:
    return json.loads(
        (ROOT / "openspec/changes/adopt-teastore-diagnostic-harness/governance.json")
        .read_text(encoding="utf-8")
    )


def test_schema_and_clean_closed_boundaries() -> None:
    value = manifest()
    assert VALIDATOR.check_schema(ROOT, value).status == "pass"
    assert VALIDATOR.check_parent(ROOT, value).status == "pass"
    assert VALIDATOR.check_sources(ROOT, value).status == "pass"
    delivery = VALIDATOR.check_delivery(ROOT, value, DELIVERY_BASE_COMMIT)
    if (ROOT / "tools/validate_science_epochs_v3.py").is_file():
        # The v2 validator is replayed at bb29cf by the v3 router.  It must fail
        # closed against the later root/child delivery in the current tree.
        assert delivery.status == "fail"
    else:
        assert delivery.status == "pass"
    assert (
        VALIDATOR.check_protocol(ROOT, value, PROTOCOL_MODULE_SHA256).status
        == "pass"
    )
    assert VALIDATOR.check_observations(ROOT, value).status == "pass"
    assert VALIDATOR.check_artifacts(ROOT, value).status == "pass"
    assert VALIDATOR.check_gates(ROOT, value).status == "pass"


def test_every_construction_checker_is_watched_rejecting_a_planted_defect() -> None:
    clean = manifest()
    defects: dict[str, tuple[callable, dict]] = {}

    wrong_schema = copy.deepcopy(clean)
    wrong_schema["schemaVersion"] = 1
    defects["construction-schema"] = (VALIDATOR.check_schema, wrong_schema)

    wrong_parent = copy.deepcopy(clean)
    wrong_parent["parentEpoch"]["tree"] = "0" * 40
    defects["parent-epoch"] = (VALIDATOR.check_parent, wrong_parent)

    stale_source = copy.deepcopy(clean)
    stale_source["sourceBindings"][0]["sha256"] = "0" * 64
    defects["source-bindings"] = (VALIDATOR.check_sources, stale_source)

    wrong_delivery = copy.deepcopy(clean)
    wrong_delivery["pathOwnership"]["baseCommit"] = "0" * 40
    defects["delivery-ownership"] = (
        lambda root, value: VALIDATOR.check_delivery(
            root, value, DELIVERY_BASE_COMMIT
        ),
        wrong_delivery,
    )

    protocol_drift = copy.deepcopy(clean)
    protocol_drift["protocolBindings"]["compiledPlan"]["runCount"] = 26
    defects["protocol-bindings"] = (
        lambda root, value: VALIDATOR.check_protocol(
            root, value, PROTOCOL_MODULE_SHA256
        ),
        protocol_drift,
    )

    overclaim = copy.deepcopy(clean)
    overclaim["diagnosticObservations"][0]["candidateCellEligible"] = True
    defects["observation-ceiling"] = (VALIDATOR.check_observations, overclaim)

    missing_artifact = copy.deepcopy(clean)
    missing_artifact["artifacts"]["proposal"] = "missing/proposal.md"
    defects["artifact-completeness"] = (VALIDATOR.check_artifacts, missing_artifact)

    self_approved = copy.deepcopy(clean)
    self_approved["permissions"]["runtimeAllowed"] = True
    defects["gate-boundary"] = (VALIDATOR.check_gates, self_approved)

    for check_id, (checker, planted) in defects.items():
        result = checker(ROOT, planted)
        assert result.check_id == check_id
        assert result.status == "fail", check_id

    allowed = clean["pathOwnership"]["allowed"]
    errors = VALIDATOR.delivery_errors(set(allowed) | {"unowned/result.json"}, allowed)
    assert errors and "unowned/result.json" in errors[0]


def test_delivery_checker_rejects_scope_that_exceeds_actual_paths() -> None:
    errors = VALIDATOR.delivery_errors({"one.txt"}, ["one.txt", "two.txt"])
    assert errors == ["declared ownership exceeds the actual delivery: ['two.txt']"]


def test_full_construction_report_never_authorizes_runtime_or_promotion() -> None:
    report = VALIDATOR.validate_repository(
        ROOT,
        delivery_base_commit=DELIVERY_BASE_COMMIT,
        protocol_module_sha256=PROTOCOL_MODULE_SHA256,
    )
    assert report["runtimeAuthorized"] is False
    assert report["promotionEligible"] is False
    assert [item["id"] for item in report["checks"]] == list(VALIDATOR.CHECK_IDS)


def test_full_report_actually_invokes_every_registered_checker(monkeypatch) -> None:
    calls: list[str] = []

    def watched(check_id: str):
        def check(_root: Path, _manifest: dict) -> object:
            calls.append(check_id)
            return VALIDATOR.Check(check_id, ())

        return check

    monkeypatch.setattr(
        VALIDATOR,
        "CHECKS",
        tuple(watched(check_id) for check_id in VALIDATOR.CHECK_IDS),
    )
    report = VALIDATOR.validate_repository(ROOT)
    assert calls == list(VALIDATOR.CHECK_IDS)
    assert [item["id"] for item in report["checks"]] == calls
