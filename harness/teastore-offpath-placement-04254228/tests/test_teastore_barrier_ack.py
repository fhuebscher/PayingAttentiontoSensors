"""Kieker-queue barrier race (BUDGET_OVERNIGHT_20261014.md item 3): the barrier acknowledgement polls the queue.

The cell function raised "candidate queue was non-empty at the measurement barrier" when the one queue read that
acknowledges the barrier saw a message.  The acknowledgement query starts at the barrier, which is also when the workload
starts, and docker exec took 1.4 s in the blocked off-path cell, so the workload's own first Kieker message was in flight:
messages 1, consumers 1 at +0.015 s, the next depth sample 0 at +1.3 s.  The acknowledgement now re-queries every second
until the queue reads empty and gives up when the next probe could not complete within QUEUE_BARRIER_ACK_BOUND_SECONDS of
the barrier; every probe is kept in queue-proof.json (measurement.barrierProbes).  The barrier and the window do not move.

Every test runs the real functions of performance_campaign against a fake queue and a fake clock, so nothing waits for
real and the number of probes is the code's own.
"""
from __future__ import annotations

import json
import types

import pytest

import test_performance_campaign_lifecycle as lc
import test_teastore_traffic_sweep as sw


MODULE = sw.MODULE
COST = 0.4          # seconds one faked queue query takes


@pytest.fixture
def producer():
    return sw.load("teastore_barrier_ack_performance_campaign", MODULE / "execution/performance_campaign.py")


class FakeQueue:
    """queue_state() that reads a script of (messages, consumers), then repeats its last entry; every call costs COST."""

    def __init__(self, clock, script, cost=COST):
        self.clock, self.script, self.cost, self.calls = clock, list(script), cost, 0

    def __call__(self, posture):
        messages, consumers = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        self.clock.advance(self.cost)
        return lc.queue_state_fixture(messages, consumers)


def _kit(producer, monkeypatch, script, cost=COST):
    clock = sw.FakeClock()
    monkeypatch.setattr(producer, "time", clock)
    queue = FakeQueue(clock, script, cost)
    monkeypatch.setattr(producer, "queue_state", queue)
    return clock, queue


def _acknowledge(producer, clock, **kwargs):
    probes: list = []
    barrier = clock.monotonic()
    acknowledgement = producer.collector_barrier_acknowledgement("full", barrier, probes=probes, **kwargs)
    return acknowledgement, probes


def _proof(producer, monkeypatch, acknowledgement, probes):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    proof = lc.queue_proof_fixture()
    proof["measurement"]["consumerAtStart"] = acknowledgement["queueState"]
    proof["measurement"]["barrierProbes"] = probes
    return proof


# ------------------------------------------------------------------------------------------- the acknowledgement
def test_a_queue_that_drains_on_the_third_probe_is_acknowledged_empty(producer, monkeypatch):
    clock, queue = _kit(producer, monkeypatch, [(1, 1), (1, 1), (0, 1)])
    acknowledgement, probes = _acknowledge(producer, clock)
    assert queue.calls == 3
    assert acknowledgement["queueState"]["messages"] == 0 and acknowledgement["queueState"]["consumers"] == 1
    assert [(row["messages"], row["consumers"]) for row in probes] == [(1, 1), (1, 1), (0, 1)]
    # One second between the end of a probe and the start of the next; the acknowledgement is the third probe's bracket.
    starts = [row["queryStartedMonotonicOffsetSeconds"] for row in probes]
    assert starts == pytest.approx([0.0, COST + 1.0, 2 * (COST + 1.0)])
    assert acknowledgement["queryStartedMonotonicOffsetSeconds"] == starts[2]
    assert acknowledgement["queryCompletedMonotonicOffsetSeconds"] == probes[2]["queryCompletedMonotonicOffsetSeconds"]


def test_an_empty_queue_costs_one_probe_and_no_wait(producer, monkeypatch):
    clock, queue = _kit(producer, monkeypatch, [(0, 1)])
    acknowledgement, probes = _acknowledge(producer, clock)
    assert queue.calls == 1 and len(probes) == 1
    assert clock.monotonic() == pytest.approx(1000.0 + COST)       # no sleep: the barrier is not delayed on the happy path


def test_a_queue_that_never_drains_stops_at_the_bound_and_stays_non_empty(producer, monkeypatch):
    clock, queue = _kit(producer, monkeypatch, [(3, 1)])
    acknowledgement, probes = _acknowledge(producer, clock)
    assert acknowledgement["queueState"]["messages"] == 3          # the terminal still refuses it (test below)
    assert len(probes) == 4                                        # starts 0, 1.4, 2.8, 4.2; a fifth could not finish by 5 s
    bound = producer.QUEUE_BARRIER_ACK_BOUND_SECONDS
    assert all(row["queryStartedMonotonicOffsetSeconds"] <= bound for row in probes)
    assert probes[-1]["queryCompletedMonotonicOffsetSeconds"] <= bound
    assert acknowledgement["queryCompletedMonotonicOffsetSeconds"] <= bound


@pytest.mark.parametrize("cost", [0.05, 0.4, 1.4, 2.4])
def test_no_probe_is_started_that_cannot_finish_inside_the_bound(producer, monkeypatch, cost):
    clock, queue = _kit(producer, monkeypatch, [(1, 1)], cost=cost)
    _, probes = _acknowledge(producer, clock)
    bound = producer.QUEUE_BARRIER_ACK_BOUND_SECONDS
    assert probes and probes[0]["queryStartedMonotonicOffsetSeconds"] == 0.0
    assert all(row["queryCompletedMonotonicOffsetSeconds"] <= bound for row in probes[1:])
    # With a constant query cost the next probe would have overrun: the stop is the bound's, not a probe-count cap.
    last = probes[-1]["queryCompletedMonotonicOffsetSeconds"]
    assert last + producer.QUEUE_BARRIER_ACK_POLL_SECONDS + cost > bound


def test_the_frozen_acknowledgement_fields_are_unchanged(producer, monkeypatch):
    """The srv5 terminal validator replays exactly these fields and the queue state against queue-proof.json."""
    clock, _ = _kit(producer, monkeypatch, [(1, 1), (0, 1)])
    acknowledgement, _ = _acknowledge(producer, clock)
    assert set(acknowledgement) == {"queryStartedAtWall", "queryStartedMonotonicOffsetSeconds",
                                    "queryCompletedAtWall", "queryCompletedMonotonicOffsetSeconds", "queueState"}


# ---------------------------------------------------------------------------------------------- the probe record
def test_every_probe_is_recorded_in_a_proof_the_checker_accepts(producer, monkeypatch):
    clock, _ = _kit(producer, monkeypatch, [(1, 1), (1, 1), (0, 1)])
    acknowledgement, probes = _acknowledge(producer, clock)
    proof = _proof(producer, monkeypatch, acknowledgement, probes)
    producer.validate_queue_proof(proof)
    assert len(proof["measurement"]["barrierProbes"]) == 3
    json.dumps(proof)                                               # serialisable as written to queue-proof.json


def test_a_proof_without_the_probe_log_is_still_accepted(producer, monkeypatch):
    """Retained proofs of earlier campaigns have no barrierProbes and replay as before."""
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    proof = lc.queue_proof_fixture()
    assert "barrierProbes" not in proof["measurement"]
    producer.validate_queue_proof(proof)


@pytest.mark.parametrize("plant,diagnostic", [
    (lambda probes: probes.clear(), "missing"),
    (lambda probes: probes[0].update(messages=0), "continued after the queue read empty"),
    (lambda probes: probes[-1].update(messages=9), "do not end in the acknowledged state"),
    (lambda probes: probes[1].update(queryStartedMonotonicOffsetSeconds=0.1), "not ordered in time"),
    (lambda probes: probes[-1].update(queryStartedMonotonicOffsetSeconds=9.0,
                                      queryCompletedMonotonicOffsetSeconds=9.4), "after the acknowledgement bound"),
    (lambda probes: probes[0].update(extra=1), "fields differ"),
    (lambda probes: probes[0].update(consumers=-1), "fields differ"),
])
def test_the_checker_sees_a_planted_defect_in_the_probe_log(producer, monkeypatch, plant, diagnostic):
    clock, _ = _kit(producer, monkeypatch, [(1, 1), (1, 1), (0, 1)])
    acknowledgement, probes = _acknowledge(producer, clock)
    proof = _proof(producer, monkeypatch, acknowledgement, probes)
    producer.validate_queue_proof(proof)                            # the unplanted proof passes
    plant(proof["measurement"]["barrierProbes"])
    with pytest.raises(RuntimeError, match=diagnostic):
        producer.validate_queue_proof(proof)


# ------------------------------------------------------------------------- the terminal decision is still refused
def _terminal(producer, monkeypatch, tmp_path, acknowledgement, probes):
    (tmp_path / "traces.json").write_text("[]")
    monkeypatch.setattr(producer, "_candidate_module", lambda *args, **kwargs: types.SimpleNamespace(
        _native_time=lambda event: None, _original_native_trace_id=lambda event: None))
    receipt = {"window": {"measurementStartedAt": "2026-10-14T08:11:05+00:00",
                          "measurementEndedAt": "2026-10-14T08:21:05+00:00"},
               "telemetry": {"collectorStats": {"spool": {"complete": True, "duplicateBodyCount": 0}}}}
    return producer._candidate_capture_terminal(
        tmp_path, receipt, _proof(producer, monkeypatch, acknowledgement, probes), {})


def test_a_queue_that_drains_inside_the_bound_passes_the_terminal(producer, monkeypatch, tmp_path):
    clock, _ = _kit(producer, monkeypatch, [(1, 1), (1, 1), (0, 1)])
    acknowledgement, probes = _acknowledge(producer, clock)
    result = _terminal(producer, monkeypatch, tmp_path, acknowledgement, probes)
    assert result["queueMessagesAtBarrier"] == 0 and result["exclusiveCollector"] is True


def test_a_queue_that_never_drains_is_refused_by_the_terminal_as_before(producer, monkeypatch, tmp_path):
    clock, _ = _kit(producer, monkeypatch, [(1, 1)])
    acknowledgement, probes = _acknowledge(producer, clock)
    with pytest.raises(RuntimeError, match="candidate queue was non-empty at the measurement barrier"):
        _terminal(producer, monkeypatch, tmp_path, acknowledgement, probes)


def test_the_race_planted_back_in_is_seen(producer, monkeypatch, tmp_path):
    """Planted defect: with the bound at zero the acknowledgement is the old single read, and the race (1, 1, then 0)
    is refused again.  This is the cell that was blocked; the unplanted run above passes it."""
    clock, _ = _kit(producer, monkeypatch, [(1, 1), (0, 1)])
    acknowledgement, probes = _acknowledge(producer, clock, bound_seconds=0.0)
    assert len(probes) == 1
    with pytest.raises(RuntimeError, match="candidate queue was non-empty at the measurement barrier"):
        _terminal(producer, monkeypatch, tmp_path, acknowledgement, probes)


# ------------------------------------------------------------------------------------------- the cell function
def test_the_cell_function_wires_the_probe_log_into_the_proof_and_keeps_the_barrier():
    """Source-level wiring of the host-only cell function, which the suite never executes (CLAUDE.md, 'Traps'):
    the thread's probe list is the one written to queue-proof.json, and the barrier is fixed before the thread starts."""
    source = (MODULE / "execution/performance_campaign.py").read_text()
    assert source.count("barrier_probes: list[dict] = []") == 1
    assert source.count("probes=barrier_probes") == 1
    assert source.count('"barrierProbes": barrier_probes') == 1
    assert source.index("barrier_probes: list[dict] = []") < source.index("def acknowledge_collector_barrier")
    assert source.index("measurement_barrier_epoch = time.time() + MEASUREMENT_BARRIER_LEAD_SECONDS") < source.index(
        "def acknowledge_collector_barrier")
