import copy
import importlib.util
import json
import threading
import time
from pathlib import Path

import pytest


MODULE = Path(__file__).parents[1] / "modules/teastore/workload/fixed_load.py"
SPEC = importlib.util.spec_from_file_location("fixed_load", MODULE)
fixed_load = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(fixed_load)


class _Response:
    def __init__(self, body: str, status: int = 200) -> None:
        self.body = body.encode()
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.body


class _Opener:
    def __init__(self) -> None:
        self.requests = []

    def open(self, request, timeout):  # noqa: ARG002 - mirrors urllib opener
        self.requests.append(request)
        path = request.full_url.split("/tools.descartes.teastore.webui", 1)[1]
        if path.startswith("/category?"):
            return _Response('<a href="product?id=7">product</a>')
        if path == "/":
            return _Response('<a href="/category?category=3">category</a>')
        return _Response("ok")


def _run_valid(tmp_path: Path, monkeypatch, **kwargs):
    opener = _Opener()
    monkeypatch.setattr(fixed_load.urllib.request, "build_opener", lambda *_args: opener)
    ledger_path = tmp_path / "journey-ledger.jsonl"
    result = fixed_load.run(
        "http://teastore/tools.descartes.teastore.webui",
        kwargs.pop("rate", 10.0),
        kwargs.pop("duration", 0.01),
        kwargs.pop("concurrency", 1),
        kwargs.pop("timeout", 1.0),
        ledger_path,
        kwargs.pop("start_at_epoch", None),
        kwargs.pop("barrier_id", "barrier-test-v1"),
    )
    assert not kwargs
    plan_path = fixed_load.journey_plan_path(ledger_path)
    return result, json.loads(plan_path.read_text()), opener, plan_path, ledger_path


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def _rewrite_chain(path: Path, records: list[dict]) -> None:
    previous = fixed_load.GENESIS_HASH
    for index, record in enumerate(records):
        record["recordSequence"] = index
        record["previousRecordSha256"] = previous
        record["recordSha256"] = fixed_load._record_sha256(record)
        previous = record["recordSha256"]
    path.write_text("".join(
        fixed_load._canonical(record).decode() + "\n" for record in records
    ))


def test_percentile_interpolates_and_empty_is_null():
    assert fixed_load.percentile([], 0.95) is None
    assert fixed_load.percentile([1, 2, 3], 0.5) == 2
    assert fixed_load.percentile([0, 10], 0.95) == 9.5


def test_run_writes_v2_aggregate_immutable_plan_and_append_only_ledger(tmp_path, monkeypatch):
    result, plan, opener, plan_path, ledger_path = _run_valid(tmp_path, monkeypatch)
    validation = fixed_load.validate_journey_ledger(plan_path, ledger_path)
    records = _records(ledger_path)

    assert result["schemaVersion"] == 2
    assert result["startedAtEpoch"] == result["schedule"]["barrierAtEpoch"]
    assert result["schedule"]["barrierId"] == "barrier-test-v1"
    assert result["offered"] == result["successful"] == result["completed"] == 1
    assert result["failed"] == result["timedOut"] == 0
    assert result["settled"] == 1
    assert result["requests"] == 5
    assert result["latencyMs"]["denominator"] == "successful-journeys"
    assert validation["verdict"] == "pass"
    assert validation["terminalJourneys"] == 1
    assert plan["artifactType"] == "teastore-expected-opportunity-plan"
    assert plan["workloadId"] == "login-browse-v1"
    assert plan["expectedPath"] == fixed_load.EXPECTED_PATH
    opportunity = plan["opportunities"][0]
    assert opportunity["opportunityId"] == "login-browse-v1:000000"
    assert opportunity["journeyId"] == opportunity["opaqueToken"]
    assert [record["recordType"] for record in records] == [
        "journey-terminal", "reconciliation",
    ]
    terminal = records[0]
    assert terminal["terminalSettled"] is True
    assert terminal["requestCount"] == 5
    assert terminal["outcome"] == "succeeded"
    assert [request["routeId"] for request in terminal["requests"]] == [
        "login-action", "home", "category", "product", "home",
    ]
    assert records[-1]["recordSequence"] == 1
    assert records[-1]["previousRecordSha256"] == records[0]["recordSha256"]
    assert result["journeyEvidence"]["plan"] == plan_path.name
    assert result["journeyEvidence"]["ledger"] == ledger_path.name
    header_values = [
        value
        for request in opener.requests
        for key, value in request.header_items()
        if key.casefold() == fixed_load.CORRELATION_HEADER.casefold()
    ]
    assert header_values == [opportunity["opaqueToken"]]


def test_plan_precedes_outcomes_and_jsonl_only_appends_terminal_rows(tmp_path, monkeypatch):
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    release_second = threading.Event()
    original = fixed_load.journey
    calls = 0
    calls_lock = threading.Lock()

    def paused(*args, **kwargs):
        nonlocal calls
        with calls_lock:
            call = calls
            calls += 1
        if call == 0:
            first_entered.set()
            assert release_first.wait(2)
        else:
            second_entered.set()
            assert release_second.wait(2)
        return original(*args, **kwargs)

    opener = _Opener()
    monkeypatch.setattr(fixed_load.urllib.request, "build_opener", lambda *_args: opener)
    monkeypatch.setattr(fixed_load, "journey", paused)
    ledger_path = tmp_path / "journey-ledger.jsonl"
    plan_path = fixed_load.journey_plan_path(ledger_path)
    failure = []

    def invoke():
        try:
            fixed_load.run(
                "http://teastore/tools.descartes.teastore.webui",
                100.0,
                0.02,
                1,
                1.0,
                ledger_path,
                barrier_id="barrier-append-test",
            )
        except BaseException as exc:  # pragma: no cover - surfaced below
            failure.append(exc)

    thread = threading.Thread(target=invoke)
    thread.start()
    assert first_entered.wait(2)
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    assert len(plan["opportunities"]) == 2
    assert ledger_path.read_bytes() == b""
    release_first.set()
    assert second_entered.wait(2)
    prefix = ledger_path.read_bytes()
    assert len(prefix.splitlines()) == 1
    assert json.loads(prefix)["recordType"] == "journey-terminal"
    release_second.set()
    thread.join(2)
    assert not thread.is_alive()
    assert failure == []
    assert plan_path.read_bytes() == plan_bytes
    assert ledger_path.read_bytes().startswith(prefix)
    assert [row["recordType"] for row in _records(ledger_path)] == [
        "journey-terminal", "journey-terminal", "reconciliation",
    ]


@pytest.mark.parametrize("existing", ["ledger", "plan"])
def test_evidence_paths_refuse_overwrite_and_preserve_existing_bytes(tmp_path, existing):
    ledger_path = tmp_path / "journey-ledger.jsonl"
    plan_path = fixed_load.journey_plan_path(ledger_path)
    occupied = ledger_path if existing == "ledger" else plan_path
    occupied.write_text("retained evidence\n")

    with pytest.raises(FileExistsError):
        fixed_load.run("http://unused", 1, 1, 1, 1, ledger_path)

    assert occupied.read_text() == "retained evidence\n"
    if existing == "plan":
        assert not ledger_path.exists()


def test_duplicate_generated_ids_fail_before_creating_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(
        fixed_load,
        "_new_journey_id",
        lambda: "journey-00000000000000000000000000000000",
    )
    ledger_path = tmp_path / "journey-ledger.jsonl"

    with pytest.raises(RuntimeError, match="duplicate journey IDs"):
        fixed_load.run("http://unused", 200, 0.01, 1, 1, ledger_path)

    assert not ledger_path.exists()
    assert not fixed_load.journey_plan_path(ledger_path).exists()


def test_explicit_future_barrier_controls_schedule_and_relative_monotonic_time(tmp_path, monkeypatch):
    barrier = time.time() + 0.03
    result, plan, _opener, _plan_path, ledger_path = _run_valid(
        tmp_path,
        monkeypatch,
        start_at_epoch=barrier,
        barrier_id="barrier-shared-42",
    )
    terminal = _records(ledger_path)[0]

    assert result["startedAtEpoch"] == barrier
    assert result["controllerStartedAtEpoch"] < barrier
    assert plan["barrierId"] == "barrier-shared-42"
    assert plan["opportunities"][0]["scheduledMonotonicOffsetSeconds"] == 0
    assert terminal["actualStartMonotonic"] >= 0


def test_explicit_barrier_too_far_in_past_is_rejected_before_artifacts(tmp_path):
    ledger_path = tmp_path / "journey-ledger.jsonl"

    with pytest.raises(ValueError, match="more than one second in the past"):
        fixed_load.run(
            "http://unused",
            1,
            1,
            1,
            1,
            ledger_path,
            start_at_epoch=time.time() - 2,
        )

    assert not ledger_path.exists()


def test_interruption_appends_terminal_rows_and_reconciliation(tmp_path, monkeypatch):
    def interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(fixed_load, "journey", interrupt)
    ledger_path = tmp_path / "journey-ledger.jsonl"

    with pytest.raises(KeyboardInterrupt):
        fixed_load.run(
            "http://unused", 10, 0.01, 1, 1, ledger_path,
            barrier_id="barrier-interrupt",
        )

    validation = fixed_load.validate_journey_ledger(
        fixed_load.journey_plan_path(ledger_path), ledger_path)
    records = _records(ledger_path)
    assert validation["state"] == "interrupted"
    assert records[0]["outcome"] == "interrupted"
    assert records[0]["terminalSettled"] is True
    assert records[-1]["state"] == "interrupted"
    assert records[-1]["terminalReason"] == "KeyboardInterrupt"


def test_unexpected_failure_is_safe_terminal_and_empty_latency_is_null(tmp_path, monkeypatch):
    def fail(*_args, **_kwargs):
        raise ValueError("credential=hunter2")

    monkeypatch.setattr(fixed_load, "journey", fail)
    ledger_path = tmp_path / "journey-ledger.jsonl"
    result = fixed_load.run(
        "http://unused", 10, 0.01, 1, 1, ledger_path,
        barrier_id="barrier-failure",
    )
    retained = ledger_path.read_text()

    assert result["successful"] == result["timedOut"] == 0
    assert result["failed"] == 1
    assert result["latencyMs"] == {
        "denominator": "successful-journeys",
        "count": 0,
        "p50": None,
        "p95": None,
        "p99": None,
        "mean": None,
    }
    assert _records(ledger_path)[0]["outcome"] == "failed"
    assert "hunter2" not in retained
    fixed_load.validate_journey_ledger(
        fixed_load.journey_plan_path(ledger_path), ledger_path)


def test_timeout_has_disjoint_aggregate_and_terminal_outcome(tmp_path, monkeypatch):
    def timeout(*_args, **_kwargs):
        raise TimeoutError("secret response")

    monkeypatch.setattr(fixed_load, "journey", timeout)
    ledger_path = tmp_path / "journey-ledger.jsonl"
    result = fixed_load.run(
        "http://unused", 10, 0.01, 1, 1, ledger_path,
        barrier_id="barrier-timeout",
    )

    assert result["successful"] == result["failed"] == 0
    assert result["timedOut"] == 1
    assert result["offered"] == result["settled"] == 1
    assert _records(ledger_path)[0]["outcome"] == "timeout"


def test_evidence_contains_no_login_credentials_or_usernames(tmp_path, monkeypatch):
    _result, plan, _opener, _plan_path, ledger_path = _run_valid(tmp_path, monkeypatch)
    serialized = json.dumps(plan) + ledger_path.read_text()

    assert '"password"' not in serialized
    assert "user2" not in serialized
    assert "Sign in" not in serialized


def test_validator_rejects_truncated_ledger_without_reconciliation(tmp_path, monkeypatch):
    _result, _plan, _opener, plan_path, ledger_path = _run_valid(tmp_path, monkeypatch)
    terminal_only = _records(ledger_path)[:-1]
    _rewrite_chain(ledger_path, terminal_only)

    with pytest.raises(ValueError, match="lacks final reconciliation"):
        fixed_load.validate_journey_ledger(plan_path, ledger_path)


def test_validator_rejects_reordered_records_planted_defect(tmp_path, monkeypatch):
    _result, _plan, _opener, plan_path, ledger_path = _run_valid(
        tmp_path, monkeypatch, rate=200, duration=0.01)
    records = _records(ledger_path)
    records[0], records[1] = records[1], records[0]
    ledger_path.write_text("".join(json.dumps(row) + "\n" for row in records))

    with pytest.raises(ValueError, match="recordSequence|hash chain"):
        fixed_load.validate_journey_ledger(plan_path, ledger_path)


def test_validator_rejects_hash_chain_mutation_planted_defect(tmp_path, monkeypatch):
    _result, _plan, _opener, plan_path, ledger_path = _run_valid(tmp_path, monkeypatch)
    records = _records(ledger_path)
    records[0]["requests"][0]["target"] = "/tampered"
    ledger_path.write_text("".join(json.dumps(row) + "\n" for row in records))

    with pytest.raises(ValueError, match="record hash differs"):
        fixed_load.validate_journey_ledger(plan_path, ledger_path)


def test_validator_rejects_duplicate_terminal_row_planted_defect(tmp_path, monkeypatch):
    _result, _plan, _opener, plan_path, ledger_path = _run_valid(
        tmp_path, monkeypatch, rate=200, duration=0.01)
    records = _records(ledger_path)
    records[1] = copy.deepcopy(records[0])
    _rewrite_chain(ledger_path, records)

    with pytest.raises(ValueError, match="duplicate journey IDs"):
        fixed_load.validate_journey_ledger(plan_path, ledger_path)


def test_validator_rejects_partial_terminal_set_planted_defect(tmp_path, monkeypatch):
    _result, _plan, _opener, plan_path, ledger_path = _run_valid(
        tmp_path, monkeypatch, rate=200, duration=0.01)
    records = _records(ledger_path)
    del records[1]
    _rewrite_chain(ledger_path, records)

    with pytest.raises(ValueError, match="row count differs"):
        fixed_load.validate_journey_ledger(plan_path, ledger_path)


def test_validator_rejects_missing_terminal_field_planted_defect(tmp_path, monkeypatch):
    _result, _plan, _opener, plan_path, ledger_path = _run_valid(tmp_path, monkeypatch)
    records = _records(ledger_path)
    records[0].pop("endedAt")
    _rewrite_chain(ledger_path, records)

    with pytest.raises(ValueError, match="keys differ"):
        fixed_load.validate_journey_ledger(plan_path, ledger_path)


def test_validator_rejects_secret_query_even_with_rehashed_chain(tmp_path, monkeypatch):
    _result, _plan, _opener, plan_path, ledger_path = _run_valid(tmp_path, monkeypatch)
    records = _records(ledger_path)
    records[0]["requests"][0]["target"] = "/login?token=hunter2"
    _rewrite_chain(ledger_path, records)

    with pytest.raises(ValueError, match="sensitive query key"):
        fixed_load.validate_journey_ledger(plan_path, ledger_path)


def test_validator_rejects_free_form_error_even_with_rehashed_chain(tmp_path, monkeypatch):
    _result, _plan, _opener, plan_path, ledger_path = _run_valid(tmp_path, monkeypatch)
    records = _records(ledger_path)
    request = records[0]["requests"][0]
    request["outcome"] = "failed"
    request["error"] = {"type": "TimeoutError", "message": "password=hunter2"}
    _rewrite_chain(ledger_path, records)

    with pytest.raises(ValueError, match="keys differ"):
        fixed_load.validate_journey_ledger(plan_path, ledger_path)


def test_validator_rejects_false_reconciliation_id_hash(tmp_path, monkeypatch):
    _result, _plan, _opener, plan_path, ledger_path = _run_valid(tmp_path, monkeypatch)
    records = _records(ledger_path)
    records[-1]["terminalJourneyIdsSha256"] = "0" * 64
    _rewrite_chain(ledger_path, records)

    with pytest.raises(ValueError, match="journey ID hash differs"):
        fixed_load.validate_journey_ledger(plan_path, ledger_path)
