import copy
import importlib.util
import subprocess
from pathlib import Path

import pytest


MODULE = Path(__file__).parents[1] / "modules/teastore/collectors/performance_probe_v3.py"
SPEC = importlib.util.spec_from_file_location("performance_probe_v3", MODULE)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(probe)

TERMINAL_MODULE = Path(__file__).parents[1] / "modules/teastore/validation/srv5_terminal.py"
TERMINAL_SPEC = importlib.util.spec_from_file_location("srv5_terminal_resource_v3", TERMINAL_MODULE)
terminal = importlib.util.module_from_spec(TERMINAL_SPEC)
assert TERMINAL_SPEC.loader
TERMINAL_SPEC.loader.exec_module(terminal)


SERVICES = ["auth", "image", "persistence", "recommender", "webui"]
BARRIER = "barrier-" + "a" * 32


def resource_document():
    identities = {service: f"{index + 1:064x}" for index, service in enumerate(SERVICES)}
    samples = []
    for slot, scheduled in enumerate((1000.0, 1005.0)):
        rows = [
            {
                "service": service,
                "containerId": identities[service],
                "name": f"obst-test-{service}-1",
                "cpuPercent": 1.0,
                "memoryBytes": 100.0,
            }
            for service in SERVICES
        ]
        samples.append({
            "slot": slot,
            "scheduledAtEpoch": scheduled,
            "startedAtEpoch": scheduled + 0.1,
            "completedAtEpoch": scheduled + 2.0,
            "scheduledMonotonicOffsetSeconds": slot * 5.0,
            "startedMonotonicOffsetSeconds": slot * 5.0 + 0.1,
            "completedMonotonicOffsetSeconds": slot * 5.0 + 2.0,
            "startLatenessSeconds": 0.1,
            "integrationWeightSeconds": 5.0,
            "applicationCpuPercent": 5.0,
            "applicationCpuSecondsContribution": 0.25,
            "applicationMemoryBytes": 500.0,
            "containers": rows,
        })
    return {
        "schemaVersion": 3,
        "contract": probe.CONTRACT,
        "barrierId": BARRIER,
        "requestedStartAtEpoch": 1000.0,
        "nominalStartAtEpoch": 1000.0,
        "nominalEndAtEpoch": 1010.0,
        "measurementDurationSeconds": 10.0,
        "collectorStartedAtEpoch": 999.0,
        "collectorEndedAtEpoch": 1010.1,
        "clock": {
            "semantics": probe.CLOCK_SEMANTICS,
            "anchorWallEpoch": 999.0,
            "anchorMonotonicSeconds": 500.0,
            "barrierMonotonicSeconds": 501.0,
            "collectorStartedMonotonicOffsetSeconds": -1.0,
            "collectorEndedMonotonicOffsetSeconds": 10.1,
        },
        "sampling": {
            "semantics": probe.SAMPLING_SEMANTICS,
            "intervalSeconds": 5.0,
            "commandTimeoutSeconds": 4.0,
            "expectedSlots": 2,
            "completedSlots": 2,
            "missedSlots": [],
            "maximumStartLatenessSeconds": 1.0,
        },
        "excludedServices": ["db", "rabbitmq", "registry"],
        "requiredServices": SERVICES,
        "containerIdentity": identities,
        "samples": samples,
        "applicationCpuSeconds": 0.5,
        "applicationMemoryPeakBytes": 500.0,
        "hostCpuSeconds": 1.0,
        "hostCpuScope": probe.HOST_CPU_SCOPE,
        "hostCpuAccounting": {
            "tickRateHz": 100,
            "start": {
                "totalTicks": 1000,
                "idleTicks": 500,
                "monotonicOffsetSeconds": 0.0,
            },
            "end": {
                "totalTicks": 1200,
                "idleTicks": 600,
                "monotonicOffsetSeconds": 10.0,
            },
            "busyTicks": 100,
        },
    }


def replay(document):
    return probe.validate_resource_evidence(
        document,
        required_services=set(SERVICES),
        expected_barrier_id=BARRIER,
        expected_start_epoch=1000.0,
        expected_duration_seconds=10.0,
    )


def receipt_projection(document, artifact_sha256="d" * 64, offered=2):
    return {"resources": {
        "applicationCpuSeconds": document["applicationCpuSeconds"],
        "applicationMemoryPeakBytes": document["applicationMemoryPeakBytes"],
        "hostCpuSeconds": document["hostCpuSeconds"],
        "contract": document["contract"],
        "artifactSha256": artifact_sha256,
        "nominalStartAtEpoch": document["nominalStartAtEpoch"],
        "nominalEndAtEpoch": document["nominalEndAtEpoch"],
        "measurementDurationSeconds": document["measurementDurationSeconds"],
        "samplingIntervalSeconds": document["sampling"]["intervalSeconds"],
        "offeredJourneys": offered,
        "applicationCpuSecondsPerOfferedJourney": (
            document["applicationCpuSeconds"] / offered),
    }}


def test_valid_resource_document_replays_exactly():
    report = replay(resource_document())
    assert report == {
        "verdict": "pass",
        "blockers": [],
        "applicationCpuSeconds": 0.5,
        "applicationMemoryPeakBytes": 500.0,
        "integrationWeightSeconds": 10.0,
    }


@pytest.mark.parametrize("location", ["top", "clock", "host", "host-start", "sample"])
def test_replay_rejects_unknown_fields_at_every_new_schema_boundary(location):
    document = resource_document()
    targets = {
        "top": document,
        "clock": document["clock"],
        "host": document["hostCpuAccounting"],
        "host-start": document["hostCpuAccounting"]["start"],
        "sample": document["samples"][0],
    }
    targets[location]["unreviewedField"] = 1
    assert replay(document)["verdict"] == "blocked"


def test_terminal_uses_shared_v3_replay_and_exact_cost_projection():
    document = resource_document()
    blockers = terminal._resources_artifact_blockers(
        document,
        receipt=receipt_projection(document),
        where="planted",
        resource_validator=probe,
        expected_barrier_id=BARRIER,
        expected_start_epoch=1000.0,
        expected_duration_seconds=10.0,
        artifact_sha256="d" * 64,
        offered_journeys=2,
    )
    assert blockers == []


def test_terminal_rejects_forged_cpu_even_when_receipt_is_changed_to_match():
    document = resource_document()
    document["applicationCpuSeconds"] = 999.0
    blockers = terminal._resources_artifact_blockers(
        document,
        receipt=receipt_projection(document),
        where="planted",
        resource_validator=probe,
        expected_barrier_id=BARRIER,
        expected_start_epoch=1000.0,
        expected_duration_seconds=10.0,
        artifact_sha256="d" * 64,
        offered_journeys=2,
    )
    assert any("v3 replay blocked" in blocker for blocker in blockers)


@pytest.mark.parametrize("defect", [
    "forged-cpu",
    "empty-containers",
    "one-sample",
    "monotonic-overrun",
    "changed-container",
    "row-sum",
    "unclipped-weight",
    "missed-slot",
    "sampling-interval",
    "command-timeout",
    "start-lateness-policy",
    "monotonic-schedule-diverges",
    "monotonic-start-before-slot",
    "monotonic-lateness-summary",
    "clock-barrier-binding",
    "forged-host-matching-summary",
])
def test_replay_watches_planted_resource_defects(defect):
    document = resource_document()
    if defect == "forged-cpu":
        document["applicationCpuSeconds"] = 999.0
    elif defect == "empty-containers":
        document["samples"][0]["containers"] = []
    elif defect == "one-sample":
        document["samples"] = document["samples"][:1]
        document["sampling"]["completedSlots"] = 1
    elif defect == "monotonic-overrun":
        document["samples"][0]["completedMonotonicOffsetSeconds"] = 5.000001
    elif defect == "changed-container":
        document["samples"][0]["containers"][0]["containerId"] = "f" * 64
    elif defect == "row-sum":
        document["samples"][0]["containers"][0]["cpuPercent"] = 10.0
    elif defect == "unclipped-weight":
        document["samples"][1]["integrationWeightSeconds"] = 6.0
        document["samples"][1]["applicationCpuSecondsContribution"] = 0.3
        document["applicationCpuSeconds"] = 0.55
    elif defect == "missed-slot":
        document["sampling"]["missedSlots"] = [1]
    elif defect == "sampling-interval":
        document["sampling"]["intervalSeconds"] = 4.0
    elif defect == "command-timeout":
        document["sampling"]["commandTimeoutSeconds"] = 3.0
    elif defect == "start-lateness-policy":
        document["sampling"]["maximumStartLatenessSeconds"] = 0.5
    elif defect == "monotonic-schedule-diverges":
        document["samples"][1]["scheduledMonotonicOffsetSeconds"] = 4.9
    elif defect == "monotonic-start-before-slot":
        document["samples"][0]["startedMonotonicOffsetSeconds"] = -0.1
    elif defect == "monotonic-lateness-summary":
        document["samples"][0]["startLatenessSeconds"] = 0.2
    elif defect == "clock-barrier-binding":
        document["clock"]["barrierMonotonicSeconds"] = 502.0
    else:
        document["hostCpuSeconds"] = 9.0
        document["hostCpuAccounting"]["busyTicks"] = 900
    report = replay(document)
    assert report["verdict"] == "blocked"
    assert report["blockers"]


class Clock:
    def __init__(self, wall, monotonic):
        self.wall = wall
        self.monotonic_value = monotonic

    def time(self):
        return self.wall

    def monotonic(self):
        return self.monotonic_value

    def sleep(self, seconds):
        self.wall += seconds
        self.monotonic_value += seconds

    def advance(self, monotonic_seconds, *, wall_seconds=None):
        self.monotonic_value += monotonic_seconds
        self.wall += monotonic_seconds if wall_seconds is None else wall_seconds


def test_producer_uses_absolute_slots_and_nominal_window(monkeypatch):
    clock = Clock(995.0, 495.0)
    identities = {service: f"{index + 1:064x}" for index, service in enumerate(SERVICES)}
    monkeypatch.setattr(probe.time, "time", clock.time)
    monkeypatch.setattr(probe.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(probe.time, "sleep", clock.sleep)
    monkeypatch.setattr(probe, "resolve_containers", lambda *_args: identities)
    ticks = iter(((1000, 500), (1200, 600)))
    monkeypatch.setattr(probe, "host_ticks", lambda: next(ticks))
    monkeypatch.setattr(probe.os, "sysconf", lambda _name: 100)

    def collect(_identity, _timeout):
        clock.advance(2.0)
        rows = [
            {"service": service, "containerId": identities[service],
             "name": service, "cpuPercent": 1.0, "memoryBytes": 100.0}
            for service in SERVICES
        ]
        return 5.0, 500.0, rows

    monkeypatch.setattr(probe, "collect_slot", collect)
    result = probe.sample(
        "obst-test", 10.0, 5.0, {"db", "rabbitmq", "registry"}, set(SERVICES),
        1000.0, BARRIER, 4.0, 1.0,
    )
    assert [row["scheduledAtEpoch"] for row in result["samples"]] == [1000.0, 1005.0]
    assert [row["scheduledMonotonicOffsetSeconds"] for row in result["samples"]] == [0.0, 5.0]
    assert result["collectorEndedAtEpoch"] == 1010.0
    assert result["applicationCpuSeconds"] == 0.5
    assert replay(result)["verdict"] == "pass"


def test_producer_keeps_monotonic_slots_when_wall_clock_diverges(monkeypatch):
    clock = Clock(995.0, 495.0)
    identities = {service: f"{index + 1:064x}" for index, service in enumerate(SERVICES)}
    monkeypatch.setattr(probe.time, "time", clock.time)
    monkeypatch.setattr(probe.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(probe.time, "sleep", clock.sleep)
    monkeypatch.setattr(probe, "resolve_containers", lambda *_args: identities)
    ticks = iter(((1000, 500), (1200, 600)))
    monkeypatch.setattr(probe, "host_ticks", lambda: next(ticks))
    monkeypatch.setattr(probe.os, "sysconf", lambda _name: 100)
    calls = 0

    def collect(_identity, _timeout):
        nonlocal calls
        calls += 1
        clock.advance(2.0, wall_seconds=102.0 if calls == 1 else 2.0)
        rows = [
            {"service": service, "containerId": identities[service],
             "name": service, "cpuPercent": 1.0, "memoryBytes": 100.0}
            for service in SERVICES
        ]
        return 5.0, 500.0, rows

    monkeypatch.setattr(probe, "collect_slot", collect)
    result = probe.sample(
        "obst-test", 10.0, 5.0, {"db", "rabbitmq", "registry"}, set(SERVICES),
        1000.0, BARRIER, 4.0, 1.0,
    )
    assert result["samples"][1]["startedAtEpoch"] == 1105.0
    assert result["samples"][1]["startedMonotonicOffsetSeconds"] == 5.0
    assert replay(result)["verdict"] == "pass"


@pytest.mark.parametrize("interval,timeout,lateness", [
    (4.0, 4.0, 1.0),
    (5.0, 3.0, 1.0),
    (5.0, 4.0, 0.5),
])
def test_producer_rejects_noncontract_sampling_policy(interval, timeout, lateness):
    with pytest.raises(ValueError, match="cadence, timeout, or lateness"):
        probe.sample(
            "obst-test", 10.0, interval, {"db", "rabbitmq", "registry"},
            set(SERVICES), 1000.0, BARRIER, timeout, lateness,
        )


def test_producer_fails_when_collection_overruns_slot(monkeypatch):
    clock = Clock(995.0, 495.0)
    identities = {service: f"{index + 1:064x}" for index, service in enumerate(SERVICES)}
    monkeypatch.setattr(probe.time, "time", clock.time)
    monkeypatch.setattr(probe.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(probe.time, "sleep", clock.sleep)
    monkeypatch.setattr(probe, "resolve_containers", lambda *_args: identities)
    monkeypatch.setattr(probe, "host_ticks", lambda: (1000, 500))
    monkeypatch.setattr(probe.os, "sysconf", lambda _name: 100)

    def collect(_identity, _timeout):
        clock.advance(5.1)
        return 0.0, 0.0, []

    monkeypatch.setattr(probe, "collect_slot", collect)
    with pytest.raises(RuntimeError, match="overran"):
        probe.sample(
            "obst-test", 10.0, 5.0, {"db", "rabbitmq", "registry"}, set(SERVICES),
            1000.0, BARRIER, 4.0, 1.0,
        )


def test_docker_commands_are_bounded(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(probe.subprocess, "run", run)
    probe._run(["docker", "ps"], 4.0)
    assert calls[0][1]["timeout"] == 4.0
    assert calls[0][1]["check"] is True


def test_collect_slot_rejects_missing_service(monkeypatch):
    identities = {"auth": "a" * 64, "webui": "b" * 64}
    row = '{"ID":"aaaaaaaaaaaa","Name":"auth","CPUPerc":"1%","MemUsage":"1MiB / 2GiB"}\n'
    monkeypatch.setattr(
        probe, "_run", lambda command, timeout: subprocess.CompletedProcess(
            command, 0, row, ""))
    with pytest.raises(RuntimeError, match="missing=.*webui"):
        probe.collect_slot(identities, 4.0)


def test_resource_fixture_isolation():
    assert resource_document() == copy.deepcopy(resource_document())
