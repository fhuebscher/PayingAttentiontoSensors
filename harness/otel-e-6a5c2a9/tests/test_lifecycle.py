import pytest
import json
from pathlib import Path

from obsplacement.execution.lifecycle import LifecycleJournal, OperationReceipt, State


def receipt(operation, before, after, *, number=1, successful=True, errors=()):
    return OperationReceipt(
        run_id="run-1", operation_id=f"op-{number}", operation=operation,
        state_before=before, state_after=after, status="ok" if successful else "failed",
        started_at=f"2026-08-08T00:00:{number * 2 - 2:02d}Z",
        ended_at=f"2026-08-08T00:00:{number * 2 - 1:02d}Z",
        executor="test", target="test-host",
        source={"frameworkCommit": "a" * 40, "sutCommit": "b" * 40,
                "dirty": False, "patchSha256": None},
        parent_operation_id=None if number == 1 else f"op-{number - 1}", errors=errors,
    )


def test_valid_executor_neutral_lifecycle():
    journal = LifecycleJournal()
    sequence = [
        ("preflight", State.UNKNOWN, State.INVENTORIED),
        ("stop", State.INVENTORIED, State.STOPPED),
        ("materialize", State.STOPPED, State.MATERIALIZED),
        ("deploy", State.MATERIALIZED, State.DEPLOYED),
        ("start", State.DEPLOYED, State.READY),
        ("apply_posture", State.READY, State.POSTURE_PROVEN),
        ("run_workload", State.POSTURE_PROVEN, State.RUNNING),
        ("inject", State.RUNNING, State.RUNNING),
        ("collect", State.RUNNING, State.COLLECTED),
        ("teardown", State.COLLECTED, State.STOPPED),
        ("fetch", State.STOPPED, State.FETCHED),
        ("validate", State.FETCHED, State.VALIDATED),
    ]
    for number, (operation, before, after) in enumerate(sequence, 1):
        journal.accept(receipt(operation, before, after, number=number))
    assert journal.state is State.VALIDATED
    assert len(journal.receipts) == len(sequence)


def test_unknown_to_deploy_is_rejected():
    journal = LifecycleJournal()
    with pytest.raises(ValueError, match="not allowed"):
        journal.accept(receipt("deploy", State.UNKNOWN, State.DEPLOYED))


def test_failure_requires_error_and_can_teardown():
    journal = LifecycleJournal()
    journal.accept(receipt("preflight", State.UNKNOWN, State.FAILED,
                           successful=False, errors=("foreign workload",)))
    assert journal.state is State.FAILED
    journal.accept(receipt("teardown", State.FAILED, State.STOPPED, number=2))
    assert journal.state is State.STOPPED


def test_success_cannot_hide_errors():
    with pytest.raises(ValueError, match="cannot contain errors"):
        LifecycleJournal().accept(receipt(
            "preflight", State.UNKNOWN, State.INVENTORIED, errors=("warning",)))


def test_unknown_status_is_rejected():
    changed = receipt("preflight", State.UNKNOWN, State.FAILED,
                      successful=False, errors=("unknown outcome",))
    object.__setattr__(changed, "status", "maybe")
    with pytest.raises(ValueError, match="invalid lifecycle status"):
        LifecycleJournal().accept(changed)


def test_receipt_serializes_to_canonical_contract_shape():
    value = receipt("preflight", State.UNKNOWN, State.INVENTORIED).as_json()
    assert value["schemaVersion"] == 1
    assert value["operationId"] == "op-1"
    assert value["status"] == "ok"
    assert value["source"]["dirty"] is False
    assert isinstance(value["artifacts"], list)


def test_journal_rejects_run_provenance_and_time_drift():
    journal = LifecycleJournal()
    journal.accept(receipt("preflight", State.UNKNOWN, State.INVENTORIED))
    changed_run = receipt("stop", State.INVENTORIED, State.STOPPED, number=2)
    object.__setattr__(changed_run, "run_id", "other")
    with pytest.raises(ValueError, match="run ID"):
        journal.accept(changed_run)

    changed_source = receipt("stop", State.INVENTORIED, State.STOPPED, number=2)
    object.__setattr__(changed_source, "source", {**changed_source.source,
                                                  "sutCommit": "c" * 40})
    with pytest.raises(ValueError, match="provenance"):
        journal.accept(changed_source)

    reversed_time = receipt("stop", State.INVENTORIED, State.STOPPED, number=2)
    object.__setattr__(reversed_time, "started_at", "2026-08-07T23:59:59Z")
    with pytest.raises(ValueError, match="overlap"):
        journal.accept(reversed_time)


def test_execution_schema_requires_the_lifecycle_contract_shape():
    schema = json.loads((Path(__file__).parents[1] /
                         "contracts/execution-receipt.schema.json").read_text())
    required = set(schema["required"])
    assert {"executor", "requested", "observed", "errors",
            "stateBefore", "stateAfter"} <= required
    assert schema["additionalProperties"] is False
    assert schema["properties"]["source"]["properties"]["frameworkCommit"]["pattern"]
    dirty_rule = schema["properties"]["source"]["allOf"][0]
    assert "patchSha256" in dirty_rule["then"]["required"]
