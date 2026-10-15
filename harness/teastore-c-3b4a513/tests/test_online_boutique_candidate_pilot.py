from __future__ import annotations

import ast
import copy
import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
DESCRIPTOR = ROOT / "pipelines/campaigns/online-boutique-candidate-pilot-v1.json"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


compiler = load(
    "online_boutique_candidate_pilot_test",
    ROOT / "modules/online-boutique/execution/candidate_pilot.py",
)
validator = load(
    "online_boutique_candidate_validator_test",
    ROOT / "modules/online-boutique/validation/candidate_pilot.py",
)
orchestrator = load(
    "online_boutique_candidate_orchestrator_test",
    ROOT / "modules/online-boutique/execution/candidate_orchestrator.py",
)


def descriptor() -> dict:
    return compiler.strict_json_file(DESCRIPTOR)


def plan() -> dict:
    return compiler.compile_plan(descriptor())


def compiled_cells() -> list[dict]:
    return [
        cell
        for regime in plan()["regimeRoots"]
        for block in regime["blocks"]
        for cell in block["cells"]
    ]


def report(document: dict | None = None, compiled: dict | None = None) -> dict:
    document = descriptor() if document is None else document
    compiled = compiler.compile_plan(descriptor()) if compiled is None else compiled
    return validator.validate_bundle(document, compiled, root=ROOT)


def row_status(result: dict) -> dict[str, str]:
    return {row["check"]: row["status"] for row in result["checks"]}


def set_path(value: dict, path: tuple[object, ...], replacement: object) -> dict:
    attacked = copy.deepcopy(value)
    cursor: object = attacked
    for part in path[:-1]:
        cursor = cursor[part]  # type: ignore[index]
    cursor[path[-1]] = replacement  # type: ignore[index]
    return attacked


def journal_rows(root: Path) -> list[dict]:
    path = root / orchestrator.SIMULATION_JOURNAL
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def write_rehashed_journal(root: Path, rows: list[dict]) -> None:
    previous = "0" * 64
    encoded: list[str] = []
    for index, item in enumerate(rows):
        item["recordSequence"] = index
        item["previousRecordSha256"] = previous
        item["recordSha256"] = orchestrator._sha256_value(
            orchestrator._record_without_hash(item)
        )
        previous = item["recordSha256"]
        encoded.append(json.dumps(item, separators=(",", ":"), sort_keys=True) + "\n")
    (root / orchestrator.SIMULATION_JOURNAL).write_text("".join(encoded))


def test_descriptor_is_exact_and_schedules_are_recomputed_not_seed_claims():
    document = descriptor()
    assert document == compiler.frozen_descriptor()
    assert compiler.load_descriptor() == document
    assert compiler.validate_descriptor(document) is document
    assert compiler.canonical_sha256(document) == compiler.EXPECTED_DESCRIPTOR_SHA256
    allocation = compiler.allocate_schedules()
    assert allocation["no-fault-cost"]["selectorSha256"] == (
        "1103d3c7321438aa5f98b7c61648b1b91f7c621f0a5e6b565724a50240136a98"
    )
    assert allocation["productcatalog-pause-effect"]["selectorSha256"] == (
        "1df2d6fd45cfe4a9189d4be4fae55cbf84941147682352d82ebb23e6609fd3be"
    )
    assert allocation["no-fault-cost"]["blocks"] == [
        ["selected", "none", "full"],
        ["none", "full", "selected"],
        ["full", "selected", "none"],
    ]
    assert allocation["productcatalog-pause-effect"]["blocks"] == [
        ["none", "full", "selected"],
        ["full", "selected", "none"],
        ["selected", "none", "full"],
    ]


def test_compiler_emits_18_unique_balanced_cells_in_disjoint_windows():
    compiled = plan()
    cells = [
        cell
        for regime in compiled["regimeRoots"]
        for block in regime["blocks"]
        for cell in block["cells"]
    ]
    assert compiled["runCount"] == 18
    assert len(cells) == len({cell["runId"] for cell in cells}) == 18
    assert len({json.dumps(cell["runKey"], sort_keys=True) for cell in cells}) == 18
    assert compiled["minimumTimedSeconds"] == 3240
    assert all(cell["runtimeAuthorized"] is False for cell in cells)
    assert all(cell["candidateEvidenceAuthorized"] is False for cell in cells)
    for root in compiled["regimeRoots"]:
        assert len(root["blocks"]) == 3
        for position in range(3):
            assert {block["order"][position] for block in root["blocks"]} == set(
                compiler.POSTURES
            )
    roots = {item["regime"]: item for item in compiled["regimeRoots"]}
    assert roots["no-fault-cost"]["fault"] is None
    assert roots["no-fault-cost"]["artifactRootClass"] == "cost"
    assert roots["productcatalog-pause-effect"]["fault"] == "productcatalog-pause"
    assert roots["productcatalog-pause-effect"]["artifactRootClass"] == (
        "effect/productcatalog-pause"
    )


def test_effect_phases_have_exact_positive_start_slack_and_accounting():
    document = descriptor()
    workload = document["workload"]
    effect = document["windows"]["effect"]
    nominal = effect["nominalScheduledStartsByPhase"]
    expected = {
        "pre": effect["faultOnsetSeconds"] * workload["requestsPerSecond"],
        "during": effect["faultHoldSeconds"] * workload["requestsPerSecond"],
        "post-readiness": (
            workload["measurementSeconds"]
            - effect["faultOnsetSeconds"]
            - effect["faultHoldSeconds"]
        ) * workload["requestsPerSecond"],
    }
    assert workload["measurementSeconds"] == 150
    assert workload["offeredRequestsPerRun"] == 150
    assert workload["offeredRequestsTotal"] == 2700
    assert effect["faultOnsetSeconds"] == effect["faultHoldSeconds"] == 50
    assert nominal == expected == {
        "pre": 50,
        "during": 50,
        "post-readiness": 50,
    }
    assert sum(nominal.values()) == workload["offeredRequestsPerRun"]
    assert effect["minimumActualRequestStartsPerPhase"] == 40
    assert effect["minimumNominalStartSlackPerPhase"] == 10
    assert all(
        starts - effect["minimumActualRequestStartsPerPhase"]
        >= effect["minimumNominalStartSlackPerPhase"]
        for starts in nominal.values()
    )
    assert effect["phaseBoundaryInclusivity"] == compiler.PHASE_BOUNDARY_INCLUSIVITY
    assert effect["controllerProbeAccounting"] == compiler.CONTROLLER_PROBE_ACCOUNTING
    assert effect["readinessAccounting"] == compiler.READINESS_ACCOUNTING


def test_clean_validator_is_construction_green_but_runtime_and_evidence_blocked():
    result = report()
    assert compiler.readiness_report(descriptor(), plan()) == result
    assert result["valid"] is True
    assert result["verdict"] == "construction-pass-runtime-blocked"
    assert result["checkCounts"] == {"pass": 14, "fail": 0}
    assert result["runtimeReady"] is False
    assert result["candidateEvidenceEligible"] is False
    assert result["canonicalEvidenceEligible"] is False
    assert result["integrationBoundary"] == "local-construction-only"
    assert "request-trace-correlation-not-implemented" in result["blockers"]
    assert result["blockers"] == [
        "request-trace-correlation-not-implemented",
        "runtime-readiness-not-implemented",
    ]
    assert descriptor()["authority"]["runtimePlanDecisionRequired"] is True
    assert descriptor()["authority"]["freshRuntimeGateRequired"] is True


def plant_for_check(check: str) -> tuple[dict, dict]:
    document = descriptor()
    compiled = plan()
    if check == "descriptor-exact":
        document["status"] = "candidate-ready"
    elif check == "compiled-plan-exact":
        compiled["runCount"] = 17
    elif check == "source-bindings":
        document["source"]["bindings"][0]["sha256"] = "0" * 64
    elif check == "schedule-recomputed":
        document["schedule"]["receipts"][0]["selectorSha256"] = "0" * 64
    elif check == "complete-randomized-blocks":
        compiled["regimeRoots"][0]["blocks"][0]["order"] = ["none", "none", "full"]
    elif check == "regime-window-separation":
        compiled["regimeRoots"][0]["fault"] = "productcatalog-pause"
    elif check == "effect-phase-slack":
        document["workload"]["measurementSeconds"] = 120
        document["workload"]["offeredRequestsPerRun"] = 120
        document["workload"]["offeredRequestsTotal"] = 2160
        document["windows"]["sharedMeasurementSeconds"] = 120
        document["windows"]["minimumTimedSeconds"] = 2700
        effect = document["windows"]["effect"]
        effect["faultOnsetSeconds"] = 40
        effect["faultHoldSeconds"] = 40
        effect["minimumNominalStartSlackPerPhase"] = 0
        effect["nominalScheduledStartsByPhase"] = {
            "pre": 40,
            "during": 40,
            "post-readiness": 40,
        }
    elif check == "request-ground-truth":
        document["groundTruth"]["request"]["scheduledRowIsExecutionProof"] = True
    elif check == "fault-ground-truth":
        document["groundTruth"]["fault"]["commandSuccessAloneEstablishesTruth"] = True
    elif check == "path-ground-truth":
        document["groundTruth"]["path"]["crossTraceAssemblyAllowed"] = True
    elif check == "typed-missingness":
        document["missingness"]["numericMissingValue"] = 0
    elif check == "runtime-firewall":
        document["authority"]["runtimeAuthorized"] = True
    elif check == "immutable-run-identity":
        compiled["regimeRoots"][0]["blocks"][0]["cells"][1]["runId"] = (
            compiled["regimeRoots"][0]["blocks"][0]["cells"][0]["runId"]
        )
    elif check == "unsupported-abstention":
        document["missingness"]["unsupported"].pop()
    else:  # pragma: no cover - keeps the watched-check registry fail closed
        raise AssertionError(f"no planted defect for checker {check}")
    return document, compiled


@pytest.mark.parametrize(
    "check",
    [
        "descriptor-exact",
        "compiled-plan-exact",
        "source-bindings",
        "schedule-recomputed",
        "complete-randomized-blocks",
        "regime-window-separation",
        "effect-phase-slack",
        "request-ground-truth",
        "fault-ground-truth",
        "path-ground-truth",
        "typed-missingness",
        "runtime-firewall",
        "immutable-run-identity",
        "unsupported-abstention",
    ],
)
def test_every_checker_is_watched_rejecting_its_own_planted_defect(check: str):
    document, compiled = plant_for_check(check)
    result = report(document, compiled)
    assert row_status(result)[check] == "fail"
    assert result["valid"] is False
    assert result["verdict"] == "construction-fail"


def test_watched_checker_registry_exactly_covers_the_clean_validation_table():
    clean_checks = set(row_status(report()))
    planted_checks = {
        "descriptor-exact", "compiled-plan-exact", "source-bindings",
        "schedule-recomputed", "complete-randomized-blocks",
        "regime-window-separation", "effect-phase-slack", "request-ground-truth",
        "fault-ground-truth",
        "path-ground-truth", "typed-missingness", "runtime-firewall",
        "immutable-run-identity", "unsupported-abstention",
    }
    assert clean_checks == planted_checks


@pytest.mark.parametrize(
    "payload",
    [
        '{"schemaVersion":1,"schemaVersion":1}',
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":-Infinity}',
        '{"value":1} {"value":2}',
        '{"unterminated":',
    ],
)
def test_strict_json_rejects_duplicate_nonfinite_and_malformed_values(payload: str):
    with pytest.raises(compiler.ProtocolError):
        compiler.strict_json_loads(payload)


@pytest.mark.parametrize(
    ("path", "defect"),
    [
        (("authority", "runtimeAuthorized"), True),
        (("authority", "executorImplemented"), True),
        (("design", "costAndEffectPoolable"), True),
        (("design", "failedCellReplacementAllowed"), True),
        (("groundTruth", "request", "missingOrUnsettledValue"), 0),
        (("groundTruth", "path", "missingCorrelationValue"), 0),
        (("groundTruth", "path", "currentRuntimeSupport"), "supported"),
        (("missingness", "abstentions", 0, "state"), "valid"),
        (("continuation", "outcomeTriggeredExtensionAllowed"), True),
        (("evidence", "canonical"), True),
    ],
)
def test_descriptor_exact_validator_fails_closed_on_authority_and_science_drift(path, defect):
    with pytest.raises(compiler.ProtocolError):
        compiler.validate_descriptor(set_path(descriptor(), path, defect))


@pytest.mark.parametrize(
    ("path", "defect"),
    [
        (("runCount",), 17),
        (("runtimeAuthorized",), True),
        (("scheduleAllocation", "no-fault-cost", "selectedCandidateIndex"), 5),
        (("regimeRoots", 0, "blocks", 0, "cells", 0, "runId"), "relabeled"),
        (("regimeRoots", 0, "blocks", 0, "cells", 0, "runKey", "attempt"), 2),
        (("regimeRoots", 0, "blocks", 0, "cells", 0, "artifactRoot"), "shared"),
        (("missingnessBoundary", "numericMissingValue"), 0),
    ],
)
def test_compiled_plan_mutations_fail_exact_replay(path, defect):
    document = descriptor()
    with pytest.raises(compiler.ProtocolError):
        compiler.validate_plan(document, set_path(compiler.compile_plan(document), path, defect))


def test_cli_surface_has_compile_and_validate_only_and_output_is_exclusive(tmp_path: Path):
    parser = compiler._parser()
    subparser_action = next(action for action in parser._actions if action.dest == "command")
    assert set(subparser_action.choices) == {"compile", "validate"}
    output = tmp_path / "compiled.json"
    assert compiler.main(["compile", "--descriptor", str(DESCRIPTOR), "--output", str(output)]) == 0
    before = output.read_bytes()
    assert compiler.main(["compile", "--descriptor", str(DESCRIPTOR), "--output", str(output)]) == 2
    assert output.read_bytes() == before


def test_public_orchestrator_has_no_callback_executor_or_transport_seam(tmp_path: Path):
    root = tmp_path / "campaign"
    calls: list[str] = []

    def planted_executor(*_args, **_kwargs):
        calls.append("called")

    with pytest.raises(TypeError):
        orchestrator.run_local_schedule(root, planted_executor, descriptor_path=DESCRIPTOR)
    with pytest.raises(TypeError):
        orchestrator.run_local_schedule(
            root, descriptor_path=DESCRIPTOR, executor=planted_executor
        )
    assert calls == []
    assert not root.exists()
    assert list(inspect.signature(orchestrator.run_local_schedule).parameters) == [
        "root", "descriptor_path"
    ]

    forbidden_imports = {"subprocess", "socket", "paramiko", "docker"}
    for path in (
        ROOT / "modules/online-boutique/execution/candidate_pilot.py",
        ROOT / "modules/online-boutique/execution/candidate_orchestrator.py",
        ROOT / "modules/online-boutique/validation/candidate_pilot.py",
    ):
        tree = ast.parse(path.read_text())
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")])
        }
        assert imports.isdisjoint(forbidden_imports)


def test_materialization_is_exactly_replayable_and_creates_no_artifact_root_or_journal(
    tmp_path: Path,
):
    root = tmp_path / "campaign"
    first = orchestrator.run_local_schedule(root, descriptor_path=DESCRIPTOR)
    retained = {
        name: (root / name).read_bytes()
        for name in (
            orchestrator.DESCRIPTOR_COPY,
            orchestrator.PLAN_COPY,
            orchestrator.CAMPAIGN_MANIFEST,
        )
    }
    second = orchestrator.run_local_schedule(root, descriptor_path=DESCRIPTOR)
    assert first == second
    assert first["scheduledCells"] == 18
    assert first["runtimeAuthorized"] is False
    assert first["candidateExecutionEnabled"] is False
    assert first["retainedSimulationRecords"] == 0
    assert retained == {name: (root / name).read_bytes() for name in retained}
    materialized = orchestrator.materialize_campaign(root, DESCRIPTOR)
    for cell, row in zip(materialized["cells"], materialized["campaign"]["runs"]):
        assert row["artifactRoot"] == cell["artifactRoot"]
        assert "path" not in row
        assert "compiledArtifactRoot" not in row
        assert not (root / cell["artifactRoot"]).exists()
    assert not (root / orchestrator.SIMULATION_JOURNAL).exists()


def test_fixture_simulation_pauses_resumes_all_18_and_never_becomes_evidence(tmp_path: Path):
    root = tmp_path / "campaign"
    first = orchestrator.simulate_compiled_schedule(
        root, descriptor_path=DESCRIPTOR, max_cells=2
    )
    immutable = {
        name: (root / name).read_bytes()
        for name in (
            orchestrator.DESCRIPTOR_COPY,
            orchestrator.PLAN_COPY,
            orchestrator.CAMPAIGN_MANIFEST,
        )
    }
    prefix = (root / orchestrator.SIMULATION_JOURNAL).read_bytes()
    second = orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR)
    replay = orchestrator.replay_simulation_journal(
        root, orchestrator.materialize_campaign(root, DESCRIPTOR)
    )
    assert first["status"] == "paused"
    assert first["simulatedCells"] == 2
    assert second["status"] == "complete"
    assert second["scheduledCells"] == second["simulatedCells"] == 18
    assert len(second["simulatedThisCall"]) == 16
    assert len(replay["records"]) == 18
    assert (root / orchestrator.SIMULATION_JOURNAL).read_bytes().startswith(prefix)
    assert immutable == {name: (root / name).read_bytes() for name in immutable}
    assert all(
        not (root / cell["artifactRoot"]).exists()
        for cell in orchestrator.materialize_campaign(root, DESCRIPTOR)["cells"]
    )
    serialized = json.dumps(second, sort_keys=True)
    assert "evidenceSha256" not in serialized
    assert '"runtimeAuthorized": true' not in serialized
    assert second["promotionAuthorized"] is False


@pytest.mark.parametrize(
    "artifact",
    [orchestrator.DESCRIPTOR_COPY, orchestrator.PLAN_COPY, orchestrator.CAMPAIGN_MANIFEST],
)
def test_watched_retained_artifact_tamper_is_rejected(artifact: str, tmp_path: Path):
    root = tmp_path / "campaign"
    orchestrator.run_local_schedule(root, descriptor_path=DESCRIPTOR)
    path = root / artifact
    value = json.loads(path.read_text())
    if artifact == orchestrator.DESCRIPTOR_COPY:
        value["status"] = "runtime-ready"
    elif artifact == orchestrator.PLAN_COPY:
        value["runCount"] = 17
    else:
        value["compiledPlanCanonicalSha256"] = "0" * 64
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    with pytest.raises(orchestrator.ScheduleError):
        orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR)
    assert all(
        not (root / cell["artifactRoot"]).exists()
        for cell in compiled_cells()
    )


@pytest.mark.parametrize("plant", ["missing", "duplicate", "reorder", "fixture"])
def test_watched_rehashed_journal_population_and_fixture_defects_are_rejected(
    plant: str, tmp_path: Path,
):
    root = tmp_path / "campaign"
    orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR, max_cells=3)
    rows = journal_rows(root)
    if plant == "missing":
        rows.pop(0)
    elif plant == "duplicate":
        rows[1] = copy.deepcopy(rows[0])
    elif plant == "reorder":
        rows[0], rows[1] = rows[1], rows[0]
    else:
        rows[0]["fixtureSha256"] = "0" * 64
    write_rehashed_journal(root, rows)
    with pytest.raises(orchestrator.ScheduleError):
        orchestrator.run_local_schedule(root, descriptor_path=DESCRIPTOR)
    assert all(
        not (root / cell["artifactRoot"]).exists()
        for cell in compiled_cells()
    )


@pytest.mark.parametrize(
    "payload",
    [
        b'{"schemaVersion":1,"schemaVersion":1}\n',
        b'{"value":NaN}\n',
        b'{"unterminated":\n',
        b'{"truncated":true}',
    ],
)
def test_watched_journal_concealment_defects_are_rejected(payload: bytes, tmp_path: Path):
    root = tmp_path / "campaign"
    orchestrator.run_local_schedule(root, descriptor_path=DESCRIPTOR)
    (root / orchestrator.SIMULATION_JOURNAL).write_bytes(payload)
    with pytest.raises(orchestrator.ScheduleError):
        orchestrator.run_local_schedule(root, descriptor_path=DESCRIPTOR)


@pytest.mark.parametrize("conflict_index", [0, 10])
def test_preexisting_compiler_artifact_root_stops_before_any_fixture(
    conflict_index: int, tmp_path: Path,
):
    root = tmp_path / "campaign"
    orchestrator.run_local_schedule(root, descriptor_path=DESCRIPTOR)
    materialized = orchestrator.materialize_campaign(root, DESCRIPTOR)
    conflict = materialized["cells"][conflict_index]
    conflict_path = root / conflict["artifactRoot"]
    conflict_path.mkdir(parents=True)
    first = orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR)
    before = (root / orchestrator.SIMULATION_JOURNAL).read_bytes()
    second = orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR)
    rows = journal_rows(root)
    assert first["status"] == second["status"] == "stopped"
    assert first["simulatedCells"] == 0
    assert rows[0]["event"] == "simulation-stop"
    assert rows[0]["fixtureSha256"] is None
    assert conflict["runId"] in rows[0]["reason"]
    assert conflict["artifactRoot"] in rows[0]["reason"]
    assert (root / orchestrator.SIMULATION_JOURNAL).read_bytes() == before
    assert all(
        not (root / cell["artifactRoot"]).exists()
        for index, cell in enumerate(materialized["cells"])
        if index != conflict_index
    )
