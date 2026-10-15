from __future__ import annotations

import copy
import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest


MODULE = Path(__file__).parents[1] / "modules/teastore/execution/candidate_orchestrator.py"
SPEC = importlib.util.spec_from_file_location("teastore_candidate_orchestrator", MODULE)
orchestrator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = orchestrator
SPEC.loader.exec_module(orchestrator)

DESCRIPTOR = Path(__file__).parents[1] / "pipelines/campaigns/teastore-candidate-pilot-sys-v1.json"


def _journal_rows(root: Path) -> list[dict]:
    path = root / orchestrator.SIMULATION_JOURNAL
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_rehashed_journal(root: Path, records: list[dict]) -> None:
    previous = "0" * 64
    encoded: list[str] = []
    for index, record in enumerate(records):
        record["recordSequence"] = index
        record["previousRecordSha256"] = previous
        record["recordSha256"] = orchestrator._sha256_value(
            orchestrator._record_without_hash(record)
        )
        previous = record["recordSha256"]
        encoded.append(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
    (root / orchestrator.SIMULATION_JOURNAL).write_text("".join(encoded), encoding="utf-8")


def _materialize(root: Path) -> dict:
    return orchestrator.run_local_schedule(root, descriptor_path=DESCRIPTOR)


def test_public_path_rejects_callback_before_any_root_or_side_effect(tmp_path: Path):
    root = tmp_path / "candidate"
    side_effect = tmp_path / "ssh-would-have-run"
    calls: list[str] = []

    def planted_callback(*_args, **_kwargs):
        calls.append("called")
        side_effect.write_text("external mutation", encoding="utf-8")

    with pytest.raises(TypeError):
        orchestrator.run_local_schedule(root, planted_callback, descriptor_path=DESCRIPTOR)

    assert calls == []
    assert not side_effect.exists()
    assert not root.exists()

    keyword_root = tmp_path / "keyword-candidate"
    with pytest.raises(TypeError):
        orchestrator.run_local_schedule(
            keyword_root, descriptor_path=DESCRIPTOR, executor=planted_callback
        )
    assert calls == []
    assert not keyword_root.exists()
    assert "CellExecutor" not in orchestrator.__dict__
    assert "CellResult" not in orchestrator.__dict__
    assert list(inspect.signature(orchestrator.run_local_schedule).parameters) == [
        "root", "descriptor_path"
    ]


def test_public_path_materializes_and_replays_without_run_artifacts(tmp_path: Path):
    root = tmp_path / "candidate"
    first = _materialize(root)
    immutable = {
        name: (root / name).read_bytes()
        for name in (
            orchestrator.DESCRIPTOR_COPY,
            orchestrator.PLAN_COPY,
            orchestrator.CAMPAIGN_MANIFEST,
        )
    }
    second = _materialize(root)

    assert first == second
    assert first["status"] == "materialized"
    assert first["scheduledCells"] == 27
    assert first["runtimeAuthorized"] is False
    assert first["candidateExecutionEnabled"] is False
    assert first["retainedSimulationRecords"] == 0
    assert immutable == {name: (root / name).read_bytes() for name in immutable}
    assert not (root / "runs").exists()
    assert not (root / orchestrator.SIMULATION_JOURNAL).exists()


def test_exact_compiled_27_cell_simulation_is_explicitly_non_evidentiary(
    tmp_path: Path,
):
    root = tmp_path / "candidate"
    result = orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR)
    retained = orchestrator.materialize_campaign(root, DESCRIPTOR)
    replay = orchestrator.replay_simulation_journal(root, retained)
    expected = retained["cells"]

    assert result["status"] == "complete"
    assert result["simulationOnly"] is True
    assert result["runtimeAuthorized"] is False
    assert result["candidateExecutionEnabled"] is False
    assert result["promotionAuthorized"] is False
    assert result["scheduledCells"] == result["simulatedCells"] == 27
    assert result["stateCounts"] == {"simulated": 27}
    assert result["simulatedThisCall"] == [cell["runId"] for cell in expected]
    assert len(replay["records"]) == 27
    assert [row["runId"] for row in replay["records"]] == [
        cell["runId"] for cell in expected
    ]
    assert {row["event"] for row in replay["records"]} == {"cell-simulated"}
    assert {row["state"] for row in replay["records"]} == {"simulated"}
    assert all(len(row["fixtureSha256"]) == 64 for row in replay["records"])
    assert not (root / "runs").exists()

    serialized = json.dumps(result, sort_keys=True) + "\n" + json.dumps(replay, sort_keys=True)
    assert "evidenceSha256" not in serialized
    assert "comparativeEligible" not in serialized
    assert '"valid"' not in serialized

    campaign = retained["campaign"]
    assert campaign["runtimeEnabledByThisManifest"] is False
    assert campaign["canonical"] is False
    assert campaign["runCount"] == 27
    assert [row["posture"] for row in campaign["runs"][:9]] == [
        "full", "none", "selected",
        "selected", "full", "none",
        "none", "selected", "full",
    ]


def test_materialized_manifest_crosses_schedule_but_not_evidence_gates(tmp_path: Path):
    root = tmp_path / "candidate"
    _materialize(root)
    validator_path = Path(__file__).parents[1] / "modules/teastore/validation/candidate_pilot.py"
    validator_spec = importlib.util.spec_from_file_location(
        "teastore_candidate_validator_for_orchestrator", validator_path
    )
    validator = importlib.util.module_from_spec(validator_spec)
    assert validator_spec.loader is not None
    validator_spec.loader.exec_module(validator)

    report = validator.validate_campaign(root)
    schedule_rows = {row["gate"]: row["status"] for row in report["validationTable"]}
    assert schedule_rows["frozen-schedule-recomputation"] == "pass"
    assert schedule_rows["scheduled-cell-population"] == "pass"
    assert schedule_rows["separate-regime-artifact-roots"] == "pass"
    assert schedule_rows["all-run-evidence"] == "fail"
    assert report["verdict"] == "blocked"


def test_clean_pause_resumes_only_unsimulated_cells_without_rerandomizing(
    tmp_path: Path,
):
    root = tmp_path / "candidate"
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
    retained = orchestrator.materialize_campaign(root, DESCRIPTOR)
    rows = _journal_rows(root)

    assert first["status"] == "paused"
    assert first["simulatedCells"] == 2
    assert second["status"] == "complete"
    assert second["simulatedCells"] == 27
    assert len(second["simulatedThisCall"]) == 25
    assert [row["runId"] for row in rows] == [
        cell["runId"] for cell in retained["cells"]
    ]
    assert (root / orchestrator.SIMULATION_JOURNAL).read_bytes().startswith(prefix)
    assert immutable == {name: (root / name).read_bytes() for name in immutable}
    assert not (root / "runs").exists()


@pytest.mark.parametrize("artifact", [
    orchestrator.DESCRIPTOR_COPY,
    orchestrator.PLAN_COPY,
    orchestrator.CAMPAIGN_MANIFEST,
])
def test_retained_descriptor_plan_and_campaign_bytes_are_immutable(
    tmp_path: Path, artifact: str,
):
    root = tmp_path / "candidate"
    _materialize(root)
    path = root / artifact
    value = json.loads(path.read_text(encoding="utf-8"))
    if artifact == orchestrator.DESCRIPTOR_COPY:
        value["id"] = "teastore-candidate-pilot-v2"
    elif artifact == orchestrator.PLAN_COPY:
        value["runCount"] = 26
    else:
        value["compiledPlanCanonicalSha256"] = "0" * 64
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(orchestrator.ScheduleError):
        orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR)
    assert not (root / "runs").exists()


@pytest.mark.parametrize("mutation", ["missing-cell", "duplicate-cell", "reorder"])
def test_campaign_population_mutations_cannot_be_used_for_simulation(
    tmp_path: Path, mutation: str,
):
    root = tmp_path / "candidate"
    orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR, max_cells=0)
    path = root / orchestrator.CAMPAIGN_MANIFEST
    campaign = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "missing-cell":
        campaign["runs"].pop()
    elif mutation == "duplicate-cell":
        campaign["runs"][-1] = copy.deepcopy(campaign["runs"][0])
    else:
        campaign["runs"][0], campaign["runs"][1] = campaign["runs"][1], campaign["runs"][0]
    path.write_text(json.dumps(campaign, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(orchestrator.ScheduleError):
        orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR)
    assert not (root / orchestrator.SIMULATION_JOURNAL).exists()
    assert not (root / "runs").exists()


def test_source_descriptor_semantic_drift_is_rejected_without_simulation(tmp_path: Path):
    descriptor = tmp_path / "descriptor.json"
    document = json.loads(DESCRIPTOR.read_text(encoding="utf-8"))
    document["timing"]["measurementSeconds"] = 599
    descriptor.write_text(json.dumps(document), encoding="utf-8")
    root = tmp_path / "candidate"

    with pytest.raises(orchestrator.ScheduleError, match="not frozen"):
        orchestrator.simulate_compiled_schedule(root, descriptor_path=descriptor)
    assert not (root / orchestrator.SIMULATION_JOURNAL).exists()
    assert not (root / "runs").exists()


def test_rehashed_attempt_two_simulation_injection_is_rejected(tmp_path: Path):
    root = tmp_path / "candidate"
    orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR, max_cells=1)
    records = _journal_rows(root)
    records[0]["runKey"]["attempt"] = 2
    _write_rehashed_journal(root, records)

    with pytest.raises(orchestrator.ScheduleError, match="relabelled"):
        _materialize(root)


@pytest.mark.parametrize("plant", ["attempt-bool", "block-bool", "schema-bool", "sequence-bool"])
def test_rehashed_boolean_integer_simulation_injection_is_rejected(
    tmp_path: Path, plant: str,
):
    root = tmp_path / "candidate"
    orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR, max_cells=1)
    records = _journal_rows(root)
    if plant == "attempt-bool":
        records[0]["runKey"]["attempt"] = True
    elif plant == "block-bool":
        records[0]["runKey"]["block"] = True
    elif plant == "schema-bool":
        records[0]["schemaVersion"] = True
    else:
        records[0]["recordSequence"] = True
        records[0]["recordSha256"] = orchestrator._sha256_value(
            orchestrator._record_without_hash(records[0])
        )
        (root / orchestrator.SIMULATION_JOURNAL).write_text(
            json.dumps(records[0], separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(orchestrator.ScheduleError):
            _materialize(root)
        return
    _write_rehashed_journal(root, records)

    with pytest.raises(orchestrator.ScheduleError):
        _materialize(root)


def test_materialized_campaign_rejects_boolean_schema_version(tmp_path: Path):
    root = tmp_path / "candidate"
    _materialize(root)
    path = root / orchestrator.CAMPAIGN_MANIFEST
    campaign = json.loads(path.read_text(encoding="utf-8"))
    campaign["schemaVersion"] = True
    path.write_text(json.dumps(campaign, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(orchestrator.ScheduleError):
        orchestrator.materialize_campaign(root, DESCRIPTOR)


@pytest.mark.parametrize("plant", ["missing", "duplicate", "reorder"])
def test_rehashed_simulation_population_defects_fail_closed(
    tmp_path: Path, plant: str,
):
    root = tmp_path / "candidate"
    orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR, max_cells=3)
    records = _journal_rows(root)
    if plant == "missing":
        records.pop(0)
    elif plant == "duplicate":
        records[1] = copy.deepcopy(records[0])
    else:
        records[0], records[1] = records[1], records[0]
    _write_rehashed_journal(root, records)

    with pytest.raises(orchestrator.ScheduleError, match="reordered|relabelled"):
        _materialize(root)


def test_rehashed_fixture_digest_substitution_is_rejected(tmp_path: Path):
    root = tmp_path / "candidate"
    orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR, max_cells=1)
    records = _journal_rows(root)
    records[0]["fixtureSha256"] = "0" * 64
    _write_rehashed_journal(root, records)

    with pytest.raises(orchestrator.ScheduleError, match="invalid simulation"):
        _materialize(root)


def test_preexisting_run_root_stops_simulation_without_creating_another(tmp_path: Path):
    root = tmp_path / "candidate"
    _materialize(root)
    retained = orchestrator.materialize_campaign(root, DESCRIPTOR)
    first_path = root / retained["campaign"]["runs"][0]["path"]
    first_path.mkdir(parents=True)

    first = orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR)
    journal_before = (root / orchestrator.SIMULATION_JOURNAL).read_bytes()
    second = orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR)
    rows = _journal_rows(root)

    assert first["status"] == second["status"] == "stopped"
    assert first["simulatedCells"] == 0
    assert rows[0]["event"] == "simulation-stop"
    assert rows[0]["state"] == "stopped"
    assert rows[0]["fixtureSha256"] is None
    assert (root / orchestrator.SIMULATION_JOURNAL).read_bytes() == journal_before
    assert not (root / retained["campaign"]["runs"][1]["path"]).exists()


def test_public_replay_never_appends_simulation_rows(tmp_path: Path):
    root = tmp_path / "candidate"
    orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR, max_cells=2)
    before = (root / orchestrator.SIMULATION_JOURNAL).read_bytes()

    receipt = _materialize(root)

    assert receipt["retainedSimulationRecords"] == 2
    assert (root / orchestrator.SIMULATION_JOURNAL).read_bytes() == before
    assert not (root / "runs").exists()


@pytest.mark.parametrize("payload", [
    b'{"schemaVersion":1,"schemaVersion":1}\n',
    b'{"value":NaN}\n',
    b'{"unterminated":\n',
    b'{"truncated":true}',
])
def test_simulation_journal_strict_parser_rejects_concealment(
    tmp_path: Path, payload: bytes,
):
    root = tmp_path / "candidate"
    _materialize(root)
    (root / orchestrator.SIMULATION_JOURNAL).write_bytes(payload)

    with pytest.raises(orchestrator.ScheduleError):
        _materialize(root)
    assert not (root / "runs").exists()


def test_simulation_limit_is_typed_and_accepts_no_callback(tmp_path: Path):
    root = tmp_path / "candidate"
    with pytest.raises(orchestrator.ScheduleError):
        orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR, max_cells=True)
    assert not root.exists()

    calls: list[str] = []

    def planted_callback(*_args):
        calls.append("called")

    with pytest.raises(TypeError):
        orchestrator.simulate_compiled_schedule(root, planted_callback, descriptor_path=DESCRIPTOR)
    assert calls == []
    assert not root.exists()


def test_simulation_journal_hash_chain_tamper_is_rejected(tmp_path: Path):
    root = tmp_path / "candidate"
    orchestrator.simulate_compiled_schedule(root, descriptor_path=DESCRIPTOR, max_cells=2)
    records = _journal_rows(root)
    records[0]["reason"] = "planted"
    (root / orchestrator.SIMULATION_JOURNAL).write_text(
        "".join(
            json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n"
            for row in records
        ),
        encoding="utf-8",
    )

    with pytest.raises(orchestrator.ScheduleError, match="self hash"):
        _materialize(root)
