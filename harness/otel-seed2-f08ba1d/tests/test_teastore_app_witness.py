import hashlib
import importlib.util
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]


def _nested_secret_log(layers: int) -> str:
    value = '{"password":"planted-not-a-real-secret"}'
    for _ in range(layers):
        value = json.dumps(value)
    return "normal-log-prefix " + value + "\n"
MODULE = ROOT / "modules/teastore/witness/extract_app_witness.py"
SPEC = importlib.util.spec_from_file_location("extract_app_witness", MODULE)
witness = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(witness)


START = datetime(2026, 8, 29, 0, 0, tzinfo=timezone.utc)


def _time(seconds: float) -> str:
    return (START + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _log(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join("container-prefix " + witness.MARKER + json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_valid_ledger(path: Path, journeys: list[dict]) -> None:
    fixed_load = witness._FIXED_LOAD
    plan_path = fixed_load.journey_plan_path(path)
    opportunities = []
    for index, journey in enumerate(journeys):
        journey["opportunityId"] = f"login-browse-v1:{index:06d}"
        opportunities.append({
            "sequence": index,
            "journeyId": journey["opaqueToken"],
            "opportunityId": journey["opportunityId"],
            "opaqueToken": journey["opaqueToken"],
            "tokenAllocatedAt": _time(-0.5),
            "scheduledAt": _time(index),
            "scheduledMonotonicOffsetSeconds": float(index),
        })
    plan = {
        "artifactType": fixed_load.PLAN_ARTIFACT_TYPE,
        "schemaVersion": fixed_load.LEDGER_SCHEMA_VERSION,
        "workloadId": fixed_load.WORKLOAD_ID,
        "barrierId": "barrier-app-witness-test",
        "controllerStartedAt": _time(-1),
        "barrierAt": _time(0),
        "clock": fixed_load.CLOCK_CONTRACT,
        "schedule": {
            "kind": "fixed-open-loop",
            "journeysPerSecond": 1.0,
            "durationSeconds": float(len(journeys)),
            "offered": len(journeys),
        },
        "expectedPath": fixed_load.EXPECTED_PATH,
        "tokenContract": fixed_load.TOKEN_CONTRACT,
        "opportunities": opportunities,
    }
    plan_path.write_text(json.dumps(plan, sort_keys=True) + "\n", encoding="utf-8")
    plan_sha = fixed_load._sha256(plan)
    records = []
    previous = fixed_load.GENESIS_HASH
    for index, (journey, planned) in enumerate(zip(journeys, opportunities)):
        start_mono = float(journey["actualStartMonotonic"])
        record = {
            "artifactType": fixed_load.LEDGER_ARTIFACT_TYPE,
            "schemaVersion": fixed_load.LEDGER_SCHEMA_VERSION,
            "recordType": "journey-terminal",
            "recordSequence": index,
            "previousRecordSha256": previous,
            "planSha256": plan_sha,
            "workloadId": fixed_load.WORKLOAD_ID,
            "barrierId": plan["barrierId"],
            **planned,
            "actualStartMonotonic": start_mono,
            "actualEndMonotonic": start_mono + 2,
            "startedAt": journey["startedAt"],
            "endedAt": journey["endedAt"],
            "expectedPath": fixed_load.EXPECTED_PATH,
            "requests": [{
                "sequence": 0,
                "step": "login",
                "routeId": "login-action",
                "target": "/loginAction",
                "actualStartMonotonic": start_mono,
                "actualEndMonotonic": start_mono + 1,
                "startedAt": journey["startedAt"],
                "endedAt": _time(
                    (datetime.fromisoformat(journey["startedAt"].replace("Z", "+00:00"))
                     - START).total_seconds() + 1),
                "latencyMs": 1000.0,
                "statusCode": 200,
                "outcome": "succeeded",
                "error": None,
            }],
            "requestCount": 1,
            "outcome": "succeeded",
            "errors": [],
            "terminalSettled": True,
            "endedAfterNominalWindow": start_mono + 2 > len(journeys),
        }
        record["recordSha256"] = fixed_load._record_sha256(record)
        previous = record["recordSha256"]
        records.append(record)
    reconciliation = {
        "artifactType": fixed_load.LEDGER_ARTIFACT_TYPE,
        "schemaVersion": fixed_load.LEDGER_SCHEMA_VERSION,
        "recordType": "reconciliation",
        "recordSequence": len(records),
        "previousRecordSha256": previous,
        "planSha256": plan_sha,
        "workloadId": fixed_load.WORKLOAD_ID,
        "barrierId": plan["barrierId"],
        "state": "completed",
        "terminalReason": None,
        "expectedJourneys": len(journeys),
        "terminalJourneys": len(journeys),
        "terminalJourneyIdsSha256": fixed_load._id_set_sha256(
            [row["journeyId"] for row in opportunities]),
        "terminalOpportunityIdsSha256": fixed_load._id_set_sha256(
            [row["opportunityId"] for row in opportunities]),
        "finalizedAt": _time(599),
        "terminalSettled": True,
    }
    reconciliation["recordSha256"] = fixed_load._record_sha256(reconciliation)
    records.append(reconciliation)
    path.write_bytes(b"".join(fixed_load._canonical(row) + b"\n" for row in records))
    assert fixed_load.validate_journey_ledger(plan_path, path)["verdict"] == "pass"


def _journey(index: int, wall_second: float, monotonic: float) -> dict:
    token = f"journey-{index:032x}"
    return {
        "journeyId": token,
        "opportunityId": f"login-browse-v1:{index:06d}",
        "opaqueToken": token,
        "startedAt": _time(wall_second),
        "endedAt": _time(wall_second + 2),
        "actualStartMonotonic": monotonic,
    }


def _observation(journey: dict, service: str, wall_second: float) -> dict:
    return {
        "schema": witness.OBSERVATION_SCHEMA,
        "schemaVersion": 1,
        "observedAtUtc": _time(wall_second),
        "journeyId": journey["opaqueToken"],
        "service": service,
        "event": witness.SERVICES[service],
    }


def _fixture(tmp_path: Path, *, regime: str = "no-fault-cost", journeys=None):
    journeys = journeys or [_journey(1, 10, 10)]
    ledger = tmp_path / "journey-ledger.jsonl"
    auth = tmp_path / "auth.log"
    persistence = tmp_path / "persistence.log"
    run_receipt = tmp_path / "receipt.json"
    output = tmp_path / "app-witness.jsonl"
    extraction_receipt = tmp_path / "app-witness-extraction.json"
    _write_valid_ledger(ledger, journeys)
    intervention = None
    if regime != "no-fault-cost":
        intervention = {
            "actualOnsetMonotonicOffsetSeconds": 300.0,
            "actualOffsetMonotonicOffsetSeconds": 400.0,
            "readiness": {"observedAtMonotonicOffsetSeconds": 450.0},
        }
    run_receipt.write_text(json.dumps({
        "run": {"regime": regime},
        "window": {
            "measurementStartedAt": _time(0),
            "measurementEndedAt": _time(600),
        },
        "intervention": intervention,
    }), encoding="utf-8")
    auth_rows = [_observation(row, "auth", 10 + index * 10 + 0.25)
                 for index, row in enumerate(journeys)]
    persistence_rows = [_observation(row, "persistence", 10 + index * 10 + 0.5)
                        for index, row in enumerate(journeys)]
    # Default one-row fixtures start at wall second 10. Multi-row tests replace logs.
    _log(auth, auth_rows)
    _log(persistence, persistence_rows)
    return {
        "auth_log": auth,
        "persistence_log": persistence,
        "journey_ledger": ledger,
        "run_receipt": run_receipt,
        "output": output,
        "extraction_receipt": extraction_receipt,
    }


def _run(paths: dict):
    return witness.extract(**paths)


def test_positive_pair_is_exact_hash_bound_application_witness(tmp_path):
    paths = _fixture(tmp_path)
    terminal = _run(paths)
    rows = [json.loads(line) for line in paths["output"].read_text().splitlines()]

    assert len(rows) == 1
    assert rows[0] == {
        "schema": "teastore.app-witness",
        "schemaVersion": 1,
        "journeyId": "journey-00000000000000000000000000000001",
        "opportunityId": "login-browse-v1:000000",
        "opaqueToken": "journey-00000000000000000000000000000001",
        "source": "application-side",
        "independentOfKieker": True,
        "observedAt": _time(10.5),
        "authObservedAtUtc": _time(10.25),
        "persistenceObservedAtUtc": _time(10.5),
        "authTraversed": True,
        "persistenceTraversed": True,
        "executedPath": ["auth", "persistence"],
    }
    assert terminal["status"] == "complete"
    assert terminal["counts"]["requiredScoredOpportunities"] == 1
    assert terminal["appWitnessSha256"] == hashlib.sha256(
        paths["output"].read_bytes()).hexdigest()
    assert json.loads(paths["extraction_receipt"].read_text()) == terminal


def test_patch_is_bound_to_pin_and_applies_cleanly():
    manifest_path = ROOT / "modules/teastore/witness/patch-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    patch = ROOT / manifest["patch"]["path"]

    assert subprocess.run(
        ["git", "-C", str(ROOT / "upstream/teastore"), "rev-parse", "HEAD"],
        text=True, capture_output=True, check=True,
    ).stdout.strip() == manifest["source"]["commit"] == witness.BASE_COMMIT
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == manifest["patch"]["sha256"]
    subprocess.run(
        ["git", "-C", str(ROOT / "upstream/teastore"), "apply", "--check", str(patch)],
        text=True, capture_output=True, check=True,
    )
    patch_text = patch.read_text()
    assert manifest["patchedPaths"] == sorted(manifest["patchedPaths"])
    assert all(f"a/{path}" in patch_text or f"b/{path}" in patch_text
               for path in manifest["patchedPaths"])


def test_missing_service_log_blocks_without_artifact(tmp_path):
    paths = _fixture(tmp_path)
    paths["persistence_log"] = tmp_path / "absent-persistence.log"

    with pytest.raises(witness.WitnessError, match="missing persistence service log"):
        _run(paths)
    assert not paths["output"].exists()


def test_duplicate_token_service_blocks_without_artifact(tmp_path):
    paths = _fixture(tmp_path)
    original = paths["auth_log"].read_text()
    paths["auth_log"].write_text(original + original)

    with pytest.raises(witness.WitnessError, match="duplicate token/service"):
        _run(paths)
    assert not paths["output"].exists()


@pytest.mark.parametrize("kind", ["malformed", "secret-bearing"])
def test_malformed_or_secret_bearing_witness_row_blocks(tmp_path, kind):
    paths = _fixture(tmp_path)
    if kind == "malformed":
        payload = "{not-json}"
        expected = "malformed JSON"
    else:
        row = _observation(_journey(1, 10, 10), "auth", 10.25)
        row["password"] = "hunter2"
        payload = json.dumps(row)
        expected = "secret-bearing"
    paths["auth_log"].write_text(witness.MARKER + payload + "\n")

    with pytest.raises(witness.WitnessError, match=expected):
        _run(paths)
    assert "hunter2" not in paths["output"].read_text() if paths["output"].exists() else True


def test_out_of_window_observation_blocks(tmp_path):
    paths = _fixture(tmp_path)
    row = _observation(_journey(1, 10, 10), "auth", 601)
    _log(paths["auth_log"], [row])

    with pytest.raises(witness.WitnessError, match="out-of-window"):
        _run(paths)
    assert not paths["output"].exists()


def test_old_intervention_monotonic_key_names_are_rejected(tmp_path):
    before = _journey(1, 10, 100)
    after = _journey(2, 20, 500)
    paths = _fixture(
        tmp_path,
        regime="auth-freeze-effect",
        journeys=[before, after],
    )
    receipt = json.loads(paths["run_receipt"].read_text())
    receipt["intervention"] = {
        "startedMonotonic": 300.0,
        "endedMonotonic": 400.0,
        "readinessMonotonic": 450.0,
    }
    paths["run_receipt"].write_text(json.dumps(receipt))

    with pytest.raises(witness.WitnessError, match="monotonic bounds are invalid"):
        _run(paths)
    assert not paths["output"].exists()


def test_missing_final_ledger_reconciliation_blocks(tmp_path):
    paths = _fixture(tmp_path)
    lines = paths["journey_ledger"].read_text().splitlines(keepends=True)
    paths["journey_ledger"].write_text("".join(lines[:-1]))

    with pytest.raises(witness.WitnessError, match="lacks final reconciliation"):
        _run(paths)
    assert not paths["output"].exists()


def test_incomplete_path_blocks_instead_of_guessing_negative(tmp_path):
    paths = _fixture(tmp_path)
    paths["persistence_log"].write_text("ordinary service line\n")

    with pytest.raises(witness.WitnessError, match="incomplete auth->persistence path"):
        _run(paths)
    assert not paths["output"].exists()


def test_missing_scored_pair_is_unsupported_not_zero(tmp_path):
    paths = _fixture(tmp_path)
    paths["auth_log"].write_text("ordinary service line\n")
    paths["persistence_log"].write_text("ordinary service line\n")

    with pytest.raises(witness.WitnessError, match="missing service observations"):
        _run(paths)
    assert not paths["output"].exists()


def test_non_marker_secret_bearing_raw_log_line_is_rejected(tmp_path):
    paths = _fixture(tmp_path)
    paths["auth_log"].write_text(
        "password=planted-not-a-real-secret\n" + paths["auth_log"].read_text(),
        encoding="utf-8",
    )

    with pytest.raises(witness.WitnessError, match="secret-bearing raw text"):
        _run(paths)
    assert not paths["output"].exists()


def test_quoted_json_secret_bearing_raw_log_line_is_rejected(tmp_path):
    paths = _fixture(tmp_path)
    paths["auth_log"].write_text(
        '{"password":"planted-not-a-real-secret"}\n'
        + paths["auth_log"].read_text(),
        encoding="utf-8",
    )

    with pytest.raises(witness.WitnessError, match="secret-bearing raw text"):
        _run(paths)
    assert not paths["output"].exists()


@pytest.mark.parametrize("planted", [
    '{"pass\\u0077ord":"planted-not-a-real-secret"}\n',
    '{"message":"{\\"password\\":\\"planted-not-a-real-secret\\"}"}\n',
    'prefix {"password"\n : "planted-not-a-real-secret"}\n',
    "normal-log-prefix " + json.dumps(json.dumps(
        '{"pass\\u0077ord":"planted-not-a-real-secret"}')) + "\n",
    _nested_secret_log(10),
    'normal-log-prefix {"pass_word":"planted-not-a-real-secret"}\n',
    'normal-log-prefix {"db_password":"planted-not-a-real-secret"}\n',
    'normal-log-prefix {"_password_":"planted-not-a-real-secret"}\n',
    'normal-log-prefix {"paßword":"planted-not-a-real-secret"}\n',
])
def test_encoded_or_multiline_secret_bearing_raw_log_is_rejected(
        tmp_path, planted):
    paths = _fixture(tmp_path)
    paths["auth_log"].write_text(
        planted + paths["auth_log"].read_text(), encoding="utf-8")

    with pytest.raises(witness.WitnessError, match="secret-bearing raw text"):
        _run(paths)
    assert not paths["output"].exists()


def test_effect_allows_no_during_pair_but_requires_before_and_after(tmp_path):
    before = _journey(1, 10, 100)
    during = _journey(2, 20, 350)
    after = _journey(3, 30, 500)
    paths = _fixture(
        tmp_path,
        regime="auth-freeze-effect",
        journeys=[before, during, after],
    )
    _log(paths["auth_log"], [
        _observation(before, "auth", 10.25),
        _observation(after, "auth", 30.25),
    ])
    _log(paths["persistence_log"], [
        _observation(before, "persistence", 10.5),
        _observation(after, "persistence", 30.5),
    ])

    terminal = _run(paths)
    rows = [json.loads(line) for line in paths["output"].read_text().splitlines()]

    assert [row["opportunityId"] for row in rows] == [
        before["opportunityId"], after["opportunityId"],
    ]
    assert terminal["counts"]["phases"] == {"after": 1, "before": 1, "during": 1}
    assert terminal["counts"]["requiredScoredOpportunities"] == 2


def test_effect_omits_partial_during_path_without_guessing_negative(tmp_path):
    before = _journey(1, 10, 100)
    during = _journey(2, 20, 350)
    after = _journey(3, 30, 500)
    paths = _fixture(
        tmp_path,
        regime="persistence-crash-effect",
        journeys=[before, during, after],
    )
    _log(paths["auth_log"], [
        _observation(before, "auth", 10.25),
        _observation(during, "auth", 20.25),
        _observation(after, "auth", 30.25),
    ])
    _log(paths["persistence_log"], [
        _observation(before, "persistence", 10.5),
        _observation(after, "persistence", 30.5),
    ])

    terminal = _run(paths)
    rows = [json.loads(line) for line in paths["output"].read_text().splitlines()]

    assert len(rows) == 2
    assert terminal["counts"]["partialOptionalObservations"] == 1
    assert all(row["opaqueToken"] != during["opaqueToken"] for row in rows)


def test_refuses_to_overwrite_evidence(tmp_path):
    paths = _fixture(tmp_path)
    paths["output"].write_text("retained\n")

    with pytest.raises(FileExistsError, match="overwrite"):
        _run(paths)
    assert paths["output"].read_text() == "retained\n"
    assert not paths["extraction_receipt"].exists()
